"""Run controlled two-filter backtests from preferred feature candidates.

This script is research-only. It reads preferred-feature cost-mode comparison
rows, builds a small controlled set of two-filter combinations, and evaluates
them on historical ``ml_dataset`` rows with existing offline metric helpers.
It does not connect to a broker or add execution, sizing, stop, or target
logic.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Callable

BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from backtest_combined_hypotheses import build_condition, load_ml_rows, metrics
    from backtest_research import DATABASE_PATH, MIN_TRADES
    from research_costs import (
        cost_report_warnings,
        load_cost_config,
        validate_cost_args,
        validate_estimated_cost_config,
    )
    from research_metrics import csv_safe_value, normalize_direction
    from run_preferred_feature_backtests import fallback_feature_family
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_preferred_feature_combination_backtests
    from scripts.backtest_combined_hypotheses import build_condition, load_ml_rows, metrics
    from scripts.backtest_research import DATABASE_PATH, MIN_TRADES
    from scripts.research_costs import (
        cost_report_warnings,
        load_cost_config,
        validate_cost_args,
        validate_estimated_cost_config,
    )
    from scripts.research_metrics import csv_safe_value, normalize_direction
    from scripts.run_preferred_feature_backtests import fallback_feature_family


DEFAULT_REPORTS_ROOT = BASE_DIR / "reports" / "preferred_feature_backtests"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "preferred_feature_combination_backtests"
DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY")
DEFAULT_DIRECTIONS = ("long", "short")

DETAIL_FILE = "combination_backtest_detail.csv"
SUMMARY_FILE = "combination_backtest_summary.csv"
REPORT_FILE = "combination_backtest_report.md"
SKIPPED_FILE = "skipped_combinations.csv"
DIAGNOSTIC_FILE = "candidate_diagnostics.csv"
OUTPUT_FILES = (DETAIL_FILE, SUMMARY_FILE, REPORT_FILE, SKIPPED_FILE, DIAGNOSTIC_FILE)

PRIMARY_FAMILIES = {"momentum/returns", "trend/ma"}
SECONDARY_FAMILIES = {"volume/liquidity", "volatility/range", "spread/liquidity"}
CONCENTRATION_TOP_TRADE_PCT_LIMIT = 60.0
SOURCE_COLUMNS = ("scenario_source", "feature_in_shortlist", "is_preferred_shortlist_feature")
REQUIRED_COMPARISON_COLUMNS = [
    "symbol",
    "direction",
    "feature",
    "feature_family",
    "scenario",
    "scenario_source",
    "feature_in_shortlist",
    "is_preferred_shortlist_feature",
    "gross_positive",
    "net_positive",
    "cost_erased_edge",
    "gross_trades_count",
    "net_trades_count",
    "gross_mean_return",
    "gross_profit_factor",
    "net_mean_return",
    "net_profit_factor",
]

RESULT_FIELDNAMES = [
    "symbol",
    "direction",
    "combination_id",
    "feature_1",
    "scenario_1",
    "feature_family_1",
    "feature_2",
    "scenario_2",
    "feature_family_2",
    "trades_count",
    "mean_return",
    "median_return",
    "win_rate",
    "profit_factor",
    "max_drawdown",
    "cumulative_return",
    "payoff_ratio",
    "breakeven_winrate_margin",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "top_5_percent_trades_contribution_pct",
    "cost_mode",
    "return_mode",
    "baseline_mean_return",
    "baseline_profit_factor",
    "mean_return_vs_baseline",
    "profit_factor_vs_baseline",
    "notes",
]

SKIPPED_FIELDNAMES = [
    "symbol",
    "direction",
    "combination_id",
    "feature_1",
    "scenario_1",
    "feature_family_1",
    "feature_2",
    "scenario_2",
    "feature_family_2",
    "cost_mode",
    "return_mode",
    "skip_reason",
    "notes",
]

DIAGNOSTIC_FIELDNAMES = [
    "direction",
    "symbol",
    "input_rows_loaded",
    "rows_after_symbol_filter",
    "rows_after_gross_filter",
    "rows_after_net_filter",
    "rows_after_shortlist_filter",
    "eligible_candidates_total",
    "primary_candidates",
    "secondary_candidates",
    "candidates_excluded_by_family",
    "combinations_built",
    "combinations_evaluated",
    "result_rows",
    "skipped_rows",
    "notes",
]


RowLoader = Callable[[Path, str, str, str], list[dict[str, object]]]


@dataclass(frozen=True)
class PreferredCandidate:
    symbol: str
    direction: str
    feature: str
    feature_family: str
    scenario: str
    condition_type: str
    condition_value: str
    gross_trades_count: int
    net_trades_count: int
    gross_mean_return: float | None
    gross_profit_factor: float | None
    source_rank: int


@dataclass(frozen=True)
class CandidatePair:
    primary: PreferredCandidate
    secondary: PreferredCandidate

    @property
    def combination_id(self) -> str:
        return f"{self.primary.scenario} AND {self.secondary.scenario}"


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def safe_int(value: object) -> int:
    parsed = safe_float(value)
    return int(parsed) if parsed is not None else 0


def bool_from_text(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def csv_value(value: object) -> object:
    return csv_safe_value(value)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def read_csv_with_headers(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def normalize_symbols(symbols: list[object]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in symbols:
        symbol = str(value or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    if not normalized:
        raise ValueError("--symbols must include at least one symbol.")
    return normalized


def direction_output_dir(output_root: Path, run_id: str, direction: str) -> Path:
    return output_root / run_id / direction


def cost_mode_comparison_path(reports_root: Path, gross_run_id: str, net_run_id: str, direction: str) -> Path:
    return reports_root / "cost_mode_comparison" / f"{gross_run_id}_vs_{net_run_id}" / direction / "cost_mode_comparison.csv"


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> None:
    existing = [output_dir / file_name for file_name in OUTPUT_FILES if (output_dir / file_name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Preferred feature combination outputs already exist under {output_dir}. Pass --overwrite to regenerate them."
        )


def first_nonempty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def scenario_key_from_row(row: dict[str, str]) -> str:
    scenario = first_nonempty(row.get("scenario"), row.get("scenario_condition_tested"))
    if scenario:
        return scenario
    condition_type = str(row.get("condition_type") or "").strip()
    feature = str(row.get("feature") or "").strip()
    condition_value = first_nonempty(row.get("condition_value"), row.get("bucket"))
    if condition_type and feature and condition_value:
        return f"{condition_type}:{feature}:{condition_value}"
    return ""


def candidate_trade_count(row: dict[str, str], prefix: str) -> int:
    return safe_int(first_nonempty(row.get(f"{prefix}_trades_count"), row.get("trades_count")))


def gross_positive(row: dict[str, str], min_profit_factor: float, min_mean_return: float) -> bool:
    if "gross_positive" in row and str(row.get("gross_positive") or "").strip():
        if not bool_from_text(row.get("gross_positive")):
            return False
    gross_mean = safe_float(row.get("gross_mean_return"))
    gross_pf = safe_float(row.get("gross_profit_factor"))
    return (
        gross_mean is not None
        and gross_pf is not None
        and gross_mean > min_mean_return
        and gross_pf >= min_profit_factor
    )


def candidate_is_cost_erased_or_not_net_positive(row: dict[str, str]) -> bool:
    cost_erased = bool_from_text(row.get("cost_erased_edge"))
    if cost_erased:
        return True
    if "net_positive" in row and str(row.get("net_positive") or "").strip():
        return not bool_from_text(row.get("net_positive"))
    net_mean = safe_float(row.get("net_mean_return"))
    net_pf = safe_float(row.get("net_profit_factor"))
    if net_mean is None or net_pf is None:
        return False
    return not (net_mean > 0 and net_pf > 1)


def candidate_is_shortlist_feature(row: dict[str, str], *, allow_unknown_source: bool = False) -> bool:
    scenario_source = str(row.get("scenario_source") or "").strip()
    feature_in_shortlist = bool_from_text(row.get("feature_in_shortlist"))
    is_preferred = bool_from_text(row.get("is_preferred_shortlist_feature"))
    if scenario_source and scenario_source not in {"preferred_shortlist_feature", "unknown"}:
        return False
    return (
        feature_in_shortlist
        or is_preferred
        or scenario_source == "preferred_shortlist_feature"
        or (allow_unknown_source and not scenario_source)
        or (allow_unknown_source and scenario_source == "unknown")
    )


def candidate_from_row(
    row: dict[str, str],
    *,
    source_rank: int,
    min_profit_factor: float,
    min_mean_return: float,
    allow_unknown_source: bool = False,
) -> PreferredCandidate | None:
    symbol = str(row.get("symbol") or "").strip().upper()
    direction = normalize_direction(row.get("direction") or "long")
    feature = str(row.get("feature") or "").strip()
    scenario = scenario_key_from_row(row)
    if not symbol or symbol == "ALL" or not feature or not scenario:
        return None
    gross_trades_count = candidate_trade_count(row, "gross")
    net_trades_count = candidate_trade_count(row, "net")
    if gross_trades_count <= 0 or net_trades_count <= 0:
        return None
    if not candidate_is_shortlist_feature(row, allow_unknown_source=allow_unknown_source):
        return None
    if not gross_positive(row, min_profit_factor, min_mean_return):
        return None
    if not candidate_is_cost_erased_or_not_net_positive(row):
        return None
    condition_type = str(row.get("condition_type") or "").strip()
    condition_value = first_nonempty(row.get("condition_value"), row.get("bucket"))
    feature_family = str(row.get("feature_family") or "").strip() or fallback_feature_family(feature, condition_type)
    return PreferredCandidate(
        symbol=symbol,
        direction=direction,
        feature=feature,
        feature_family=feature_family,
        scenario=scenario,
        condition_type=condition_type,
        condition_value=condition_value,
        gross_trades_count=gross_trades_count,
        net_trades_count=net_trades_count,
        gross_mean_return=safe_float(row.get("gross_mean_return")),
        gross_profit_factor=safe_float(row.get("gross_profit_factor")),
        source_rank=source_rank,
    )


def source_metadata_populated(rows: list[dict[str, str]], headers: list[str]) -> bool:
    return any(
        str(row.get(column) or "").strip()
        for column in SOURCE_COLUMNS
        if column in headers
        for row in rows
    )


def comparison_source_warnings(rows: list[dict[str, str]], headers: list[str]) -> tuple[list[str], bool]:
    warnings: list[str] = []
    missing_columns = [column for column in REQUIRED_COMPARISON_COLUMNS if column not in headers]
    if missing_columns:
        warnings.append(
            "cost_mode_comparison.csv is missing expected columns: " + ", ".join(missing_columns)
        )
    blank_columns = [
        column
        for column in REQUIRED_COMPARISON_COLUMNS
        if column in headers and rows and not any(str(row.get(column) or "").strip() for row in rows)
    ]
    if blank_columns:
        warnings.append(
            "cost_mode_comparison.csv has expected columns with no populated values: "
            + ", ".join(blank_columns)
        )
    allow_unknown_source = not source_metadata_populated(rows, headers)
    if allow_unknown_source and rows:
        warnings.append(
            "Preferred shortlist source metadata is unavailable or blank; accepting unknown-source legacy rows "
            "for diagnostics. Regenerate the cost-mode comparison for strict source tags."
        )
    return warnings, allow_unknown_source


def load_comparison_source(
    *,
    reports_root: Path,
    gross_run_id: str | None,
    net_run_id: str | None,
    direction: str,
) -> tuple[list[dict[str, str]], list[str], bool]:
    if bool(gross_run_id) != bool(net_run_id):
        raise ValueError("--gross-run-id and --net-run-id must be provided together.")
    if not gross_run_id or not net_run_id:
        return [], ["Gross/net run IDs were not provided, so no cost-mode comparison rows were loaded."], False

    path = cost_mode_comparison_path(reports_root, gross_run_id, net_run_id, direction)
    if not path.exists():
        raise FileNotFoundError(f"Cost-mode comparison CSV not found: {path}")

    rows, headers = read_csv_with_headers(path)
    warnings, allow_unknown_source = comparison_source_warnings(rows, headers)
    return rows, warnings, allow_unknown_source


def candidate_sort_key(candidate: PreferredCandidate) -> tuple[float, float, int, str, str]:
    pf = candidate.gross_profit_factor if candidate.gross_profit_factor is not None else float("-inf")
    mean_return = candidate.gross_mean_return if candidate.gross_mean_return is not None else float("-inf")
    return (-pf, -mean_return, candidate.source_rank, candidate.feature, candidate.scenario)


def row_matches_direction(row: dict[str, str], direction: str) -> bool:
    try:
        return normalize_direction(row.get("direction") or direction) == direction
    except ValueError:
        return False


def has_positive_trade_counts(row: dict[str, str]) -> bool:
    return candidate_trade_count(row, "gross") > 0 and candidate_trade_count(row, "net") > 0


def empty_diagnostics(*, direction: str, symbol: str, input_rows_loaded: int) -> dict[str, object]:
    return {
        "direction": direction,
        "symbol": symbol,
        "input_rows_loaded": input_rows_loaded,
        "rows_after_symbol_filter": 0,
        "rows_after_gross_filter": 0,
        "rows_after_net_filter": 0,
        "rows_after_shortlist_filter": 0,
        "eligible_candidates_total": 0,
        "primary_candidates": 0,
        "secondary_candidates": 0,
        "candidates_excluded_by_family": 0,
        "combinations_built": 0,
        "combinations_evaluated": 0,
        "result_rows": 0,
        "skipped_rows": 0,
        "notes": "",
    }


def diagnostic_note(diagnostics: dict[str, object]) -> str:
    if safe_int(diagnostics.get("input_rows_loaded")) == 0:
        return "empty cost_mode_comparison.csv"
    if safe_int(diagnostics.get("rows_after_symbol_filter")) == 0:
        return "no rows for requested symbol"
    if safe_int(diagnostics.get("rows_after_gross_filter")) == 0:
        return "no rows passed gross_positive criteria"
    if safe_int(diagnostics.get("rows_after_net_filter")) == 0:
        return "no rows were cost-erased or net-non-positive"
    if safe_int(diagnostics.get("rows_after_shortlist_filter")) == 0:
        return "no rows passed preferred shortlist/source criteria"
    if safe_int(diagnostics.get("eligible_candidates_total")) == 0:
        return "no eligible candidates after trade-count and scenario validation"
    if safe_int(diagnostics.get("primary_candidates")) == 0:
        return "no primary family candidates"
    if safe_int(diagnostics.get("secondary_candidates")) == 0:
        return "no secondary family candidates"
    if safe_int(diagnostics.get("combinations_built")) == 0:
        return "no compatible controlled pairs built"
    return ""


def aggregate_diagnostics(rows: list[dict[str, object]], direction: str) -> dict[str, object]:
    if not rows:
        return empty_diagnostics(direction=direction, symbol="ALL", input_rows_loaded=0)
    aggregate = empty_diagnostics(
        direction=direction,
        symbol="ALL",
        input_rows_loaded=max(safe_int(row.get("input_rows_loaded")) for row in rows),
    )
    summed_columns = [
        "rows_after_symbol_filter",
        "rows_after_gross_filter",
        "rows_after_net_filter",
        "rows_after_shortlist_filter",
        "eligible_candidates_total",
        "primary_candidates",
        "secondary_candidates",
        "candidates_excluded_by_family",
        "combinations_built",
        "combinations_evaluated",
        "result_rows",
        "skipped_rows",
    ]
    for column in summed_columns:
        aggregate[column] = sum(safe_int(row.get(column)) for row in rows)
    notes = sorted({str(row.get("notes") or "") for row in rows if str(row.get("notes") or "").strip()})
    aggregate["notes"] = "; ".join(notes)
    return aggregate


def diagnostic_lines(diagnostics_rows: list[dict[str, object]], direction: str) -> list[str]:
    diagnostics = aggregate_diagnostics(diagnostics_rows, direction)
    lines = [
        f"- cost_mode_comparison rows loaded: {diagnostics['input_rows_loaded']}",
        f"- rows after symbol filter: {diagnostics['rows_after_symbol_filter']}",
        f"- rows after gross_positive filter: {diagnostics['rows_after_gross_filter']}",
        f"- rows after cost_erased_or_not_net_positive filter: {diagnostics['rows_after_net_filter']}",
        f"- rows after preferred shortlist filter: {diagnostics['rows_after_shortlist_filter']}",
        f"- eligible candidates total: {diagnostics['eligible_candidates_total']}",
        f"- primary family candidates count: {diagnostics['primary_candidates']}",
        f"- secondary family candidates count: {diagnostics['secondary_candidates']}",
        f"- candidates excluded by family: {diagnostics['candidates_excluded_by_family']}",
        f"- combinations built: {diagnostics['combinations_built']}",
        f"- combinations evaluated: {diagnostics['combinations_evaluated']}",
        f"- result rows count: {diagnostics['result_rows']}",
        f"- skipped rows count: {diagnostics['skipped_rows']}",
    ]
    if safe_int(diagnostics.get("eligible_candidates_total")) == 0:
        lines.append("- No eligible candidates loaded from cost_mode_comparison.csv.")
    notes = str(diagnostics.get("notes") or "").strip()
    if notes:
        lines.append(f"- Diagnostic notes: {notes}")
    return lines


def is_allowed_family_pair(first: PreferredCandidate, second: PreferredCandidate) -> bool:
    families = {first.feature_family, second.feature_family}
    return bool(families & PRIMARY_FAMILIES) and bool(families & SECONDARY_FAMILIES)


def orient_pair(first: PreferredCandidate, second: PreferredCandidate) -> CandidatePair | None:
    if first.feature_family in PRIMARY_FAMILIES and second.feature_family in SECONDARY_FAMILIES:
        return CandidatePair(primary=first, secondary=second)
    if second.feature_family in PRIMARY_FAMILIES and first.feature_family in SECONDARY_FAMILIES:
        return CandidatePair(primary=second, secondary=first)
    return None


def build_controlled_combinations(
    candidates: list[PreferredCandidate],
    *,
    max_combinations: int,
) -> tuple[list[CandidatePair], list[dict[str, object]]]:
    if max_combinations <= 0:
        raise ValueError("--max-combinations-per-symbol-direction must be greater than zero.")

    primary = sorted(
        [candidate for candidate in candidates if candidate.feature_family in PRIMARY_FAMILIES],
        key=candidate_sort_key,
    )
    secondary = sorted(
        [candidate for candidate in candidates if candidate.feature_family in SECONDARY_FAMILIES],
        key=candidate_sort_key,
    )
    skipped = [
        skipped_from_single_candidate(candidate, "candidate_family_not_allowed_for_controlled_pairing")
        for candidate in candidates
        if candidate.feature_family not in PRIMARY_FAMILIES | SECONDARY_FAMILIES
    ]
    if not primary or not secondary:
        if not primary:
            skipped.extend(
                skipped_from_single_candidate(candidate, "no_primary_family_candidates")
                for candidate in secondary
            )
        if not secondary:
            skipped.extend(
                skipped_from_single_candidate(candidate, "no_secondary_family_candidates")
                for candidate in primary
            )
        if primary and secondary:
            skipped.extend(
                skipped_from_single_candidate(candidate, "no_compatible_family_counterpart")
                for candidate in candidates
                if candidate.feature_family in PRIMARY_FAMILIES | SECONDARY_FAMILIES
            )
        return [], skipped

    target_count = min(max_combinations, max(1, min(len(primary), len(secondary))))
    pairs: list[CandidatePair] = []
    seen: set[tuple[str, str]] = set()
    for index in range(target_count):
        first = primary[index % len(primary)]
        second = secondary[index % len(secondary)]
        pair = orient_pair(first, second)
        if pair is None:
            skipped.append(skipped_from_pair(first, second, "family_pairing_not_allowed"))
            continue
        key = (pair.primary.scenario, pair.secondary.scenario)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(pair)
    if not pairs:
        skipped.extend(
            skipped_from_single_candidate(candidate, "no_compatible_family_counterpart")
            for candidate in candidates
            if candidate.feature_family in PRIMARY_FAMILIES | SECONDARY_FAMILIES
        )
    return pairs, skipped


def skipped_from_single_candidate(candidate: PreferredCandidate, reason: str) -> dict[str, object]:
    return {
        "symbol": candidate.symbol,
        "direction": candidate.direction,
        "combination_id": "",
        "feature_1": candidate.feature,
        "scenario_1": candidate.scenario,
        "feature_family_1": candidate.feature_family,
        "feature_2": "",
        "scenario_2": "",
        "feature_family_2": "",
        "skip_reason": reason,
        "notes": "candidate was not eligible for the controlled family-pairing rules",
    }


def skipped_from_source_row(row: dict[str, str], *, direction: str, symbol: str, reason: str) -> dict[str, object]:
    feature = str(row.get("feature") or "").strip()
    condition_type = str(row.get("condition_type") or "").strip()
    return {
        "symbol": str(row.get("symbol") or symbol).strip().upper(),
        "direction": normalize_direction(row.get("direction") or direction),
        "combination_id": "",
        "feature_1": feature,
        "scenario_1": scenario_key_from_row(row),
        "feature_family_1": str(row.get("feature_family") or "").strip() or fallback_feature_family(feature, condition_type),
        "feature_2": "",
        "scenario_2": "",
        "feature_family_2": "",
        "skip_reason": reason,
        "notes": "source row was not eligible for controlled pair evaluation",
    }


def skipped_from_pair(first: PreferredCandidate, second: PreferredCandidate, reason: str) -> dict[str, object]:
    pair = orient_pair(first, second) or CandidatePair(primary=first, secondary=second)
    return {
        "symbol": pair.primary.symbol,
        "direction": pair.primary.direction,
        "combination_id": pair.combination_id,
        "feature_1": pair.primary.feature,
        "scenario_1": pair.primary.scenario,
        "feature_family_1": pair.primary.feature_family,
        "feature_2": pair.secondary.feature,
        "scenario_2": pair.secondary.scenario,
        "feature_family_2": pair.secondary.feature_family,
        "skip_reason": reason,
        "notes": "combination was not evaluated as a normal result",
    }


def metric_delta(value: object, baseline: object) -> float | None:
    parsed_value = safe_float(value)
    parsed_baseline = safe_float(baseline)
    if parsed_value is None or parsed_baseline is None:
        return None
    return parsed_value - parsed_baseline


def gross_positive_result(row: dict[str, object], min_profit_factor: float, min_mean_return: float) -> bool:
    gross_mean = safe_float(row.get("gross_mean_return"))
    gross_pf = safe_float(row.get("gross_profit_factor"))
    return (
        gross_mean is not None
        and gross_pf is not None
        and gross_mean > min_mean_return
        and gross_pf >= min_profit_factor
    )


def net_positive_result(row: dict[str, object]) -> bool:
    net_mean = safe_float(row.get("net_mean_return"))
    net_pf = safe_float(row.get("net_profit_factor"))
    return net_mean is not None and net_pf is not None and net_mean > 0 and net_pf > 1


def concentration_dominated(row: dict[str, object]) -> bool:
    top_trade_contribution = safe_float(row.get("top_5_percent_trades_contribution_pct"))
    return top_trade_contribution is not None and top_trade_contribution > CONCENTRATION_TOP_TRADE_PCT_LIMIT


def is_net_survivor(row: dict[str, object]) -> bool:
    return (
        row.get("cost_mode") == "estimated"
        and net_positive_result(row)
        and safe_int(row.get("trades_count")) >= MIN_TRADES
        and not concentration_dominated(row)
    )


def is_cost_erased(row: dict[str, object], min_profit_factor: float, min_mean_return: float) -> bool:
    return gross_positive_result(row, min_profit_factor, min_mean_return) and not net_positive_result(row)


def is_less_bad_than_baseline(row: dict[str, object]) -> bool:
    mean_return = safe_float(row.get("mean_return"))
    profit_factor = safe_float(row.get("profit_factor"))
    mean_delta = safe_float(row.get("mean_return_vs_baseline"))
    pf_delta = safe_float(row.get("profit_factor_vs_baseline"))
    still_fails = (mean_return is not None and mean_return <= 0) or (profit_factor is not None and profit_factor <= 1)
    improved = (mean_delta is not None and mean_delta > 0) or (pf_delta is not None and pf_delta > 0)
    return still_fails and improved


def notes_for_result(row: dict[str, object], *, min_profit_factor: float, min_mean_return: float) -> str:
    if is_net_survivor(row):
        return "net survivor by conservative research criteria"
    if concentration_dominated(row):
        return "positive-looking row is concentration dominated"
    if is_cost_erased(row, min_profit_factor, min_mean_return):
        return "gross-positive combination was erased after estimated costs"
    if is_less_bad_than_baseline(row):
        return "less bad than baseline but not a survivor"
    if gross_positive_result(row, min_profit_factor, min_mean_return) and not net_positive_result(row):
        return "gross-only candidate; not a net survivor"
    return "controlled two-filter research row"


def result_row_from_metrics(
    pair: CandidatePair,
    result_metrics: dict[str, object],
    baseline_metrics: dict[str, object],
    *,
    cost_mode: str,
    return_mode: str,
    min_profit_factor: float,
    min_mean_return: float,
) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": pair.primary.symbol,
        "direction": pair.primary.direction,
        "combination_id": pair.combination_id,
        "feature_1": pair.primary.feature,
        "scenario_1": pair.primary.scenario,
        "feature_family_1": pair.primary.feature_family,
        "feature_2": pair.secondary.feature,
        "scenario_2": pair.secondary.scenario,
        "feature_family_2": pair.secondary.feature_family,
        "trades_count": result_metrics.get("trades_count", 0),
        "mean_return": result_metrics.get("mean_return"),
        "median_return": result_metrics.get("median_return"),
        "win_rate": result_metrics.get("win_rate"),
        "profit_factor": result_metrics.get("profit_factor"),
        "max_drawdown": result_metrics.get("max_drawdown"),
        "cumulative_return": result_metrics.get("cumulative_return"),
        "payoff_ratio": result_metrics.get("payoff_ratio"),
        "breakeven_winrate_margin": result_metrics.get("breakeven_winrate_margin"),
        "monthly_positive_ratio": result_metrics.get("monthly_positive_ratio"),
        "quarterly_positive_ratio": result_metrics.get("quarterly_positive_ratio"),
        "top_5_percent_trades_contribution_pct": result_metrics.get("top_5_percent_trades_contribution_pct"),
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "baseline_mean_return": baseline_metrics.get("mean_return"),
        "baseline_profit_factor": baseline_metrics.get("profit_factor"),
        "mean_return_vs_baseline": metric_delta(result_metrics.get("mean_return"), baseline_metrics.get("mean_return")),
        "profit_factor_vs_baseline": metric_delta(
            result_metrics.get("profit_factor"),
            baseline_metrics.get("profit_factor"),
        ),
        "gross_mean_return": result_metrics.get("gross_mean_return"),
        "gross_profit_factor": result_metrics.get("gross_profit_factor"),
        "net_mean_return": result_metrics.get("net_mean_return"),
        "net_profit_factor": result_metrics.get("net_profit_factor"),
    }
    row["notes"] = notes_for_result(row, min_profit_factor=min_profit_factor, min_mean_return=min_mean_return)
    return row


def evaluate_pair(
    pair: CandidatePair,
    rows: list[dict[str, object]],
    *,
    return_column: str,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
    min_profit_factor: float,
    min_mean_return: float,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    condition_1 = build_condition(rows, pair.primary.scenario)
    if condition_1 is None:
        return None, skipped_from_pair(pair.primary, pair.secondary, "condition_1_unavailable_or_unsupported")
    condition_2 = build_condition(rows, pair.secondary.scenario)
    if condition_2 is None:
        return None, skipped_from_pair(pair.primary, pair.secondary, "condition_2_unavailable_or_unsupported")

    filtered_rows = [row for row in rows if condition_1["predicate"](row) and condition_2["predicate"](row)]
    result_metrics = metrics(
        filtered_rows,
        return_column,
        pair.primary.direction,
        pair.primary.symbol,
        cost_config,
        cost_mode,
        return_mode,
    )
    if safe_int(result_metrics.get("trades_count")) == 0:
        return None, skipped_from_pair(pair.primary, pair.secondary, "zero_trades_for_combination")
    baseline_metrics = metrics(
        rows,
        return_column,
        pair.primary.direction,
        pair.primary.symbol,
        cost_config,
        cost_mode,
        return_mode,
    )
    return (
        result_row_from_metrics(
            pair,
            result_metrics,
            baseline_metrics,
            cost_mode=cost_mode,
            return_mode=return_mode,
            min_profit_factor=min_profit_factor,
            min_mean_return=min_mean_return,
        ),
        None,
    )


def sort_result_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    def numeric_sort_value(row: dict[str, object], column: str, fallback: float) -> float:
        value = safe_float(row.get(column))
        return value if value is not None else fallback

    return sorted(
        rows,
        key=lambda row: (
            str(row.get("notes")) != "net survivor by conservative research criteria",
            -numeric_sort_value(row, "profit_factor", -1.0),
            -numeric_sort_value(row, "mean_return", float("-inf")),
            -safe_int(row.get("trades_count")),
            str(row.get("symbol")),
            str(row.get("combination_id")),
        ),
    )


def line_rows(rows: list[dict[str, object]], predicate, limit: int = 15) -> list[str]:
    selected = [row for row in rows if predicate(row)]
    if not selected:
        return ["- None."]
    return [
        "- {symbol} `{combo}`: trades={trades}, mean={mean}, pf={pf}, notes={notes}".format(
            symbol=row.get("symbol", ""),
            combo=row.get("combination_id", ""),
            trades=row.get("trades_count", ""),
            mean=row.get("mean_return", ""),
            pf=row.get("profit_factor", ""),
            notes=row.get("notes", ""),
        )
        for row in selected[:limit]
    ]


def skipped_lines(rows: list[dict[str, object]], limit: int = 20) -> list[str]:
    if not rows:
        return ["- None."]
    return [
        "- {symbol} `{combo}`: {reason}".format(
            symbol=row.get("symbol", ""),
            combo=row.get("combination_id", "") or row.get("scenario_1", ""),
            reason=row.get("skip_reason", ""),
        )
        for row in rows[:limit]
    ]


def select_symbol_candidates(
    *,
    source_rows: list[dict[str, str]],
    input_rows_loaded: int,
    symbol: str,
    direction: str,
    min_profit_factor: float,
    min_mean_return: float,
    allow_unknown_source: bool,
) -> tuple[list[PreferredCandidate], list[dict[str, object]], dict[str, object]]:
    diagnostics = empty_diagnostics(direction=direction, symbol=symbol, input_rows_loaded=input_rows_loaded)
    symbol_rows = [
        row
        for row in source_rows
        if str(row.get("symbol") or "").strip().upper() == symbol and row_matches_direction(row, direction)
    ]
    gross_rows = [
        row
        for row in symbol_rows
        if gross_positive(row, min_profit_factor, min_mean_return)
    ]
    net_rows = [
        row
        for row in gross_rows
        if candidate_is_cost_erased_or_not_net_positive(row)
    ]
    shortlist_rows = [
        row
        for row in net_rows
        if candidate_is_shortlist_feature(row, allow_unknown_source=allow_unknown_source)
    ]

    diagnostics["rows_after_symbol_filter"] = len(symbol_rows)
    diagnostics["rows_after_gross_filter"] = len(gross_rows)
    diagnostics["rows_after_net_filter"] = len(net_rows)
    diagnostics["rows_after_shortlist_filter"] = len(shortlist_rows)

    candidates: list[PreferredCandidate] = []
    skipped_rows: list[dict[str, object]] = []
    for index, row in enumerate(shortlist_rows):
        if not has_positive_trade_counts(row):
            skipped_rows.append(
                skipped_from_source_row(
                    row,
                    direction=direction,
                    symbol=symbol,
                    reason="zero_trades_in_cost_mode_comparison_row",
                )
            )
            continue
        candidate = candidate_from_row(
            row,
            source_rank=index,
            min_profit_factor=min_profit_factor,
            min_mean_return=min_mean_return,
            allow_unknown_source=allow_unknown_source,
        )
        if candidate is None:
            skipped_rows.append(
                skipped_from_source_row(
                    row,
                    direction=direction,
                    symbol=symbol,
                    reason="missing_required_candidate_fields",
                )
            )
            continue
        candidates.append(candidate)

    diagnostics["eligible_candidates_total"] = len(candidates)
    diagnostics["primary_candidates"] = sum(1 for candidate in candidates if candidate.feature_family in PRIMARY_FAMILIES)
    diagnostics["secondary_candidates"] = sum(1 for candidate in candidates if candidate.feature_family in SECONDARY_FAMILIES)
    diagnostics["candidates_excluded_by_family"] = sum(
        1
        for candidate in candidates
        if candidate.feature_family not in PRIMARY_FAMILIES | SECONDARY_FAMILIES
    )
    diagnostics["skipped_rows"] = len(skipped_rows)
    diagnostics["notes"] = diagnostic_note(diagnostics)
    return candidates, skipped_rows, diagnostics


def write_report(
    path: Path,
    *,
    direction: str,
    symbols: list[str],
    timeframe: str,
    horizon: int,
    cost_mode: str,
    return_mode: str,
    gross_run_id: str | None,
    net_run_id: str | None,
    result_rows: list[dict[str, object]],
    skipped_rows: list[dict[str, object]],
    diagnostics_rows: list[dict[str, object]],
    warnings: list[str],
    min_profit_factor: float,
    min_mean_return: float,
    max_combinations: int,
) -> None:
    direction_title = "Long" if direction == "long" else "Short"
    lines = [
        f"# Preferred Feature Combination Backtest Report - {direction_title}",
        "",
        "## Research-only warning",
        "",
        "- This report is offline research triage for historical feature filters only.",
        "- Rows are not operational guidance and are not deployment-ready.",
        "",
        "## Candidate selection logic",
        "",
        f"- Symbols: {', '.join(symbols)}",
        f"- Timeframe: `{timeframe}`; horizon: `{horizon}`; direction: `{direction}`",
        f"- Cost mode: `{cost_mode}`; return mode: `{return_mode}`",
        f"- Gross run ID: `{gross_run_id or ''}`; net run ID: `{net_run_id or ''}`",
        f"- Candidate gross minimums: profit factor >= `{min_profit_factor}`, mean return > `{min_mean_return}`",
        "- Candidates must be preferred-shortlist rows with positive gross evidence and cost-erased or non-positive net evidence.",
        "- Pairing is rank-aligned between momentum/returns or trend/ma and volume/liquidity, volatility/range, or spread/liquidity.",
        f"- Maximum controlled combinations per symbol and direction: `{max_combinations}`.",
        "",
        "## Candidate diagnostics",
        "",
        *diagnostic_lines(diagnostics_rows, direction),
        "",
        "## Net survivors",
        "",
        *line_rows(result_rows, is_net_survivor),
        "",
        "## Gross-only candidates",
        "",
        *line_rows(
            result_rows,
            lambda row: gross_positive_result(row, min_profit_factor, min_mean_return)
            and not net_positive_result(row),
        ),
        "",
        "## Cost-erased combinations",
        "",
        *line_rows(result_rows, lambda row: is_cost_erased(row, min_profit_factor, min_mean_return)),
        "",
        "## Less bad than baseline",
        "",
        *line_rows(result_rows, is_less_bad_than_baseline),
        "",
        "## Skipped combinations",
        "",
        *skipped_lines(skipped_rows),
        "",
        "## Methodology warnings",
        "",
        "- This is a small controlled pairing pass, not an exhaustive search.",
        "- Long and short are kept separate, and symbols are evaluated separately.",
        "- Net interpretation depends on the configured cost assumptions and point-size quality.",
        "- Positive-looking rows are downgraded when trade count is low or top-trade concentration is high.",
        "- No position sizing, stop, target, or multi-timeframe logic is added here.",
    ]
    if warnings:
        lines.extend(["", "## Input warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate_symbol_direction(
    *,
    db_path: Path,
    row_loader: RowLoader,
    symbol: str,
    timeframe: str,
    horizon: int,
    direction: str,
    source_rows: list[dict[str, str]],
    input_rows_loaded: int,
    allow_unknown_source: bool,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
    min_profit_factor: float,
    min_mean_return: float,
    max_combinations: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[str], dict[str, object]]:
    warnings: list[str] = []
    symbol_candidates, skipped_rows, diagnostics = select_symbol_candidates(
        source_rows=source_rows,
        input_rows_loaded=input_rows_loaded,
        symbol=symbol,
        direction=direction,
        min_profit_factor=min_profit_factor,
        min_mean_return=min_mean_return,
        allow_unknown_source=allow_unknown_source,
    )
    pairs, pairing_skipped_rows = build_controlled_combinations(
        symbol_candidates,
        max_combinations=max_combinations,
    )
    skipped_rows.extend(pairing_skipped_rows)
    diagnostics["combinations_built"] = len(pairs)
    if not pairs:
        diagnostics["skipped_rows"] = len(skipped_rows)
        diagnostics["notes"] = diagnostic_note(diagnostics)
        return [], skipped_rows, warnings, diagnostics

    return_column = f"future_return_{horizon}"
    rows = row_loader(db_path, symbol, timeframe, return_column)
    if not rows:
        skipped_rows.extend(
            skipped_from_pair(pair.primary, pair.secondary, "no_ml_dataset_rows_for_symbol_timeframe_horizon")
            for pair in pairs
        )
        diagnostics["skipped_rows"] = len(skipped_rows)
        diagnostics["notes"] = diagnostic_note(diagnostics)
        return [], skipped_rows, warnings, diagnostics

    if cost_mode == "estimated":
        cost_report = validate_estimated_cost_config(
            symbols=[symbol],
            rows_by_symbol={symbol: rows},
            config=cost_config,
            strict=False,
        )
        warnings.extend(cost_report_warnings(cost_report))

    result_rows: list[dict[str, object]] = []
    for pair in pairs:
        diagnostics["combinations_evaluated"] = safe_int(diagnostics.get("combinations_evaluated")) + 1
        result_row, skipped_row = evaluate_pair(
            pair,
            rows,
            return_column=return_column,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
            min_profit_factor=min_profit_factor,
            min_mean_return=min_mean_return,
        )
        if result_row is not None:
            result_rows.append(result_row)
        if skipped_row is not None:
            skipped_rows.append(skipped_row)
    diagnostics["result_rows"] = len(result_rows)
    diagnostics["skipped_rows"] = len(skipped_rows)
    diagnostics["notes"] = diagnostic_note(diagnostics)
    return result_rows, skipped_rows, warnings, diagnostics


def build_direction_outputs(
    *,
    reports_root: Path,
    output_root: Path,
    run_id: str,
    gross_run_id: str | None,
    net_run_id: str | None,
    symbols: list[str],
    timeframe: str,
    horizon: int,
    direction: str,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
    db_path: Path,
    min_profit_factor: float,
    min_mean_return: float,
    max_combinations: int,
    overwrite: bool,
    row_loader: RowLoader,
) -> dict[str, Path]:
    output_dir = direction_output_dir(output_root, run_id, direction)
    ensure_outputs_writable(output_dir, overwrite)
    source_rows, warnings, allow_unknown_source = load_comparison_source(
        reports_root=reports_root,
        gross_run_id=gross_run_id,
        net_run_id=net_run_id,
        direction=direction,
    )

    result_rows: list[dict[str, object]] = []
    skipped_rows: list[dict[str, object]] = []
    diagnostics_rows: list[dict[str, object]] = []
    for symbol in symbols:
        symbol_results, symbol_skipped, symbol_warnings, symbol_diagnostics = evaluate_symbol_direction(
            db_path=db_path,
            row_loader=row_loader,
            symbol=symbol,
            timeframe=timeframe,
            horizon=horizon,
            direction=direction,
            source_rows=source_rows,
            input_rows_loaded=len(source_rows),
            allow_unknown_source=allow_unknown_source,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
            min_profit_factor=min_profit_factor,
            min_mean_return=min_mean_return,
            max_combinations=max_combinations,
        )
        result_rows.extend(symbol_results)
        skipped_rows.extend(symbol_skipped)
        warnings.extend(symbol_warnings)
        diagnostics_rows.append(symbol_diagnostics)

    sorted_results = sort_result_rows(result_rows)
    diagnostics_with_total = diagnostics_rows + [aggregate_diagnostics(diagnostics_rows, direction)]
    detail_path = output_dir / DETAIL_FILE
    summary_path = output_dir / SUMMARY_FILE
    skipped_path = output_dir / SKIPPED_FILE
    diagnostic_path = output_dir / DIAGNOSTIC_FILE
    report_path = output_dir / REPORT_FILE
    write_csv(detail_path, sorted_results, RESULT_FIELDNAMES)
    write_csv(summary_path, sorted_results, RESULT_FIELDNAMES)
    write_csv(
        skipped_path,
        [
            {
                **row,
                "cost_mode": cost_mode,
                "return_mode": return_mode,
            }
            for row in skipped_rows
        ],
        SKIPPED_FIELDNAMES,
    )
    write_csv(diagnostic_path, diagnostics_with_total, DIAGNOSTIC_FIELDNAMES)
    write_report(
        report_path,
        direction=direction,
        symbols=symbols,
        timeframe=timeframe,
        horizon=horizon,
        cost_mode=cost_mode,
        return_mode=return_mode,
        gross_run_id=gross_run_id,
        net_run_id=net_run_id,
        result_rows=sorted_results,
        skipped_rows=skipped_rows,
        diagnostics_rows=diagnostics_rows,
        warnings=warnings,
        min_profit_factor=min_profit_factor,
        min_mean_return=min_mean_return,
        max_combinations=max_combinations,
    )
    return {
        "combination_backtest_detail": detail_path,
        "combination_backtest_summary": summary_path,
        "combination_backtest_report": report_path,
        "skipped_combinations": skipped_path,
        "candidate_diagnostics": diagnostic_path,
    }


def run_preferred_feature_combination_backtests(
    args: argparse.Namespace,
    *,
    row_loader: RowLoader = load_ml_rows,
) -> dict[str, dict[str, Path]]:
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    symbols = normalize_symbols(list(args.symbols))
    directions = [normalize_direction(direction) for direction in args.directions]
    timeframe = str(args.timeframe).strip().upper()
    if not timeframe:
        raise ValueError("--timeframe cannot be empty.")
    horizon = int(args.horizon)
    min_profit_factor = float(args.min_gross_profit_factor)
    min_mean_return = float(args.min_gross_mean_return)
    max_combinations = int(args.max_combinations_per_symbol_direction)
    run_id = str(getattr(args, "run_id", "") or current_run_id())
    cost_config = load_cost_config(args.cost_config)
    if cost_mode == "estimated" and bool(args.strict_cost_config):
        for symbol in symbols:
            rows = row_loader(Path(args.db_path), symbol, timeframe, f"future_return_{horizon}")
            validate_estimated_cost_config(
                symbols=[symbol],
                rows_by_symbol={symbol: rows},
                config=cost_config,
                strict=True,
            )

    outputs: dict[str, dict[str, Path]] = {}
    for direction in directions:
        outputs[direction] = build_direction_outputs(
            reports_root=Path(args.reports_root),
            output_root=Path(args.output_root),
            run_id=run_id,
            gross_run_id=getattr(args, "gross_run_id", None),
            net_run_id=getattr(args, "net_run_id", None),
            symbols=symbols,
            timeframe=timeframe,
            horizon=horizon,
            direction=direction,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
            db_path=Path(args.db_path),
            min_profit_factor=min_profit_factor,
            min_mean_return=min_mean_return,
            max_combinations=max_combinations,
            overwrite=bool(args.overwrite),
            row_loader=row_loader,
        )
    return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run research-only controlled two-filter preferred feature combination backtests."
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--directions", nargs="+", choices=DEFAULT_DIRECTIONS, default=list(DEFAULT_DIRECTIONS))
    parser.add_argument("--gross-run-id")
    parser.add_argument("--net-run-id")
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--min-gross-profit-factor", type=float, default=1.02)
    parser.add_argument("--min-gross-mean-return", type=float, default=0.0)
    parser.add_argument("--max-combinations-per-symbol-direction", type=int, default=30)
    parser.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT, help=f"Default: {DEFAULT_REPORTS_ROOT}")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=f"Default: {DEFAULT_OUTPUT_ROOT}")
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    parser.add_argument("--run-id")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    try:
        outputs = run_preferred_feature_combination_backtests(parse_args())
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"Preferred feature combination backtests failed: {exc}")
        return 1
    print("Preferred feature combination backtests complete.")
    for direction, paths in outputs.items():
        print(f"Direction: {direction}")
        for label, path in paths.items():
            print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
