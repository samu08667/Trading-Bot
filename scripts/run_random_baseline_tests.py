"""Run random baseline robustness checks for final research candidates.

This script is an offline research validation step. It only evaluates final
candidate combinations against random same-size samples from the same dataset
universe. It does not search for new strategies, create live signals, connect
to MetaTrader5, or send orders.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
import random
import sqlite3
from statistics import mean, median
from typing import Any, Iterable

try:
    from condition_utils import (
        NUMERIC_TERCILE_SKIP_REASON,
        RAW_PRICE_SKIP_REASON,
        build_predicate,
        precheck_combination_skip_reason,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_random_baseline_tests
    from scripts.condition_utils import (
        NUMERIC_TERCILE_SKIP_REASON,
        RAW_PRICE_SKIP_REASON,
        build_predicate,
        precheck_combination_skip_reason,
    )

try:
    from research_costs import (
        cost_report_fields,
        cost_report_warnings,
        load_cost_config,
        strategy_return_components,
        validate_cost_args,
        validate_estimated_cost_config,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_random_baseline_tests
    from scripts.research_costs import (
        cost_report_fields,
        cost_report_warnings,
        load_cost_config,
        strategy_return_components,
        validate_cost_args,
        validate_estimated_cost_config,
    )

try:
    from research_metrics import (
        calculate_performance_concentration_metrics,
        calculate_return_metrics,
        csv_safe_value,
        normalize_direction,
        safe_float,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_random_baseline_tests
    from scripts.research_metrics import (
        calculate_performance_concentration_metrics,
        calculate_return_metrics,
        csv_safe_value,
        normalize_direction,
        safe_float,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_VALIDATION_DIR = BASE_DIR / "reports" / "validation" / "by_year"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "random_baseline"
DEFAULT_COST_CONFIG = BASE_DIR / "config" / "cost_model.example.json"
TABLE_NAME = "ml_dataset"

FINAL_CANDIDATES_FILE = "final_research_candidates.csv"
PAIR_SPECIFIC_CANDIDATES_FILE = "pair_specific_candidates.csv"

DETAIL_OUTPUT = "random_baseline_detail.csv"
SUMMARY_OUTPUT = "random_baseline_summary.csv"
REPORT_OUTPUT = "random_baseline_report.md"
SKIPPED_OUTPUT = "skipped_random_baseline_candidates.csv"

RANDOM_METRICS = [
    "cumulative_return",
    "profit_factor",
    "max_drawdown",
    "win_rate",
    "mean_return",
    "payoff_ratio",
    "breakeven_winrate",
    "breakeven_winrate_margin",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "top_5_percent_trades_contribution_pct",
]

HIGHER_IS_BETTER_METRICS = {
    "cumulative_return",
    "profit_factor",
    "win_rate",
    "mean_return",
    "payoff_ratio",
    "breakeven_winrate_margin",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
}

LOWER_IS_BETTER_METRICS = {"breakeven_winrate", "top_5_percent_trades_contribution_pct"}
LOWER_ABS_IS_BETTER_METRICS = {"max_drawdown"}


def normalize_symbols(values: list[str] | None) -> list[str]:
    symbols: list[str] = []
    for value in values or []:
        for token in value.split(","):
            symbol = token.strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols


def comparable_float(value: object) -> float | None:
    parsed = safe_float(value)
    if parsed is None:
        return None
    return None if parsed != parsed else parsed


def finite_or_comparable_values(values: Iterable[object]) -> list[float]:
    parsed_values: list[float] = []
    for value in values:
        parsed = comparable_float(value)
        if parsed is not None:
            parsed_values.append(parsed)
    return parsed_values


def percentile_higher_is_better(candidate_value: object, random_values: Iterable[object]) -> float | None:
    candidate = comparable_float(candidate_value)
    values = finite_or_comparable_values(random_values)
    if candidate is None or not values:
        return None
    return sum(1 for value in values if value <= candidate) / len(values) * 100


def percentile_lower_is_better(candidate_value: object, random_values: Iterable[object]) -> float | None:
    candidate = comparable_float(candidate_value)
    values = finite_or_comparable_values(random_values)
    if candidate is None or not values:
        return None
    return sum(1 for value in values if value >= candidate) / len(values) * 100


def percentile_lower_abs_is_better(candidate_value: object, random_values: Iterable[object]) -> float | None:
    candidate = comparable_float(candidate_value)
    values = finite_or_comparable_values(random_values)
    if candidate is None or not values:
        return None
    candidate_abs = abs(candidate)
    return sum(1 for value in values if abs(value) >= candidate_abs) / len(values) * 100


def empirical_p_value_higher_is_better(candidate_value: object, random_values: Iterable[object]) -> float | None:
    candidate = comparable_float(candidate_value)
    values = finite_or_comparable_values(random_values)
    if candidate is None or not values:
        return None
    return (1 + sum(1 for value in values if value >= candidate)) / (len(values) + 1)


def empirical_p_value_lower_is_better(candidate_value: object, random_values: Iterable[object]) -> float | None:
    candidate = comparable_float(candidate_value)
    values = finite_or_comparable_values(random_values)
    if candidate is None or not values:
        return None
    return (1 + sum(1 for value in values if value <= candidate)) / (len(values) + 1)


def empirical_p_value_lower_abs_is_better(candidate_value: object, random_values: Iterable[object]) -> float | None:
    candidate = comparable_float(candidate_value)
    values = finite_or_comparable_values(random_values)
    if candidate is None or not values:
        return None
    candidate_abs = abs(candidate)
    return (1 + sum(1 for value in values if abs(value) <= candidate_abs)) / (len(values) + 1)


def random_sample_rows(rows: list[dict[str, object]], sample_size: int, rng: random.Random) -> list[dict[str, object]]:
    if sample_size < 0:
        raise ValueError("sample_size cannot be negative.")
    if sample_size > len(rows):
        raise ValueError("sample_size cannot be greater than the available universe.")
    if sample_size == len(rows):
        return list(rows)
    return rng.sample(rows, sample_size)


def metric_percentile(metric_name: str, candidate_value: object, random_values: Iterable[object]) -> float | None:
    if metric_name in HIGHER_IS_BETTER_METRICS:
        return percentile_higher_is_better(candidate_value, random_values)
    if metric_name in LOWER_ABS_IS_BETTER_METRICS:
        return percentile_lower_abs_is_better(candidate_value, random_values)
    if metric_name in LOWER_IS_BETTER_METRICS:
        return percentile_lower_is_better(candidate_value, random_values)
    raise ValueError(f"Unsupported random baseline metric: {metric_name}")


def metric_empirical_p_value(metric_name: str, candidate_value: object, random_values: Iterable[object]) -> float | None:
    if metric_name in HIGHER_IS_BETTER_METRICS:
        return empirical_p_value_higher_is_better(candidate_value, random_values)
    if metric_name in LOWER_ABS_IS_BETTER_METRICS:
        return empirical_p_value_lower_abs_is_better(candidate_value, random_values)
    if metric_name in LOWER_IS_BETTER_METRICS:
        return empirical_p_value_lower_is_better(candidate_value, random_values)
    raise ValueError(f"Unsupported random baseline metric: {metric_name}")


def random_distribution_stats(values: Iterable[object]) -> dict[str, object]:
    parsed = finite_or_comparable_values(values)
    if not parsed:
        return {"mean": None, "median": None, "p05": None, "p95": None}
    sorted_values = sorted(parsed)
    p05_index = int((len(sorted_values) - 1) * 0.05)
    p95_index = int((len(sorted_values) - 1) * 0.95)
    return {
        "mean": mean(parsed),
        "median": median(parsed),
        "p05": sorted_values[p05_index],
        "p95": sorted_values[p95_index],
    }


def selected_return_metrics(
    rows: list[dict[str, object]],
    *,
    return_column: str,
    direction: str,
    cost_config: dict[str, Any],
    cost_mode: str,
    return_mode: str,
    fallback_symbol: str | None = None,
) -> dict[str, object]:
    selected_returns: list[float] = []
    timestamps: list[object] = []
    for row in rows:
        symbol = str(row.get("symbol") or fallback_symbol or "").upper()
        gross, _estimated_cost, net = strategy_return_components(
            row,
            symbol=symbol,
            return_column=return_column,
            direction=direction,
            cost_config=cost_config,
            cost_mode=cost_mode,
        )
        selected = gross if return_mode == "gross" else net
        if selected is None:
            continue
        selected_returns.append(selected)
        timestamps.append(row.get("time_server"))

    return {
        **calculate_return_metrics(selected_returns),
        **calculate_performance_concentration_metrics(selected_returns, timestamps),
    }


def table_exists(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    )
    return cursor.fetchone() is not None


def load_universe_rows(
    db_path: Path,
    symbols: list[str],
    timeframe: str,
    return_column: str,
) -> list[dict[str, object]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    if not symbols:
        raise ValueError("--symbols must include at least one symbol.")
    placeholders = ",".join("?" for _ in symbols)
    params = [*symbols, timeframe]
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        if not table_exists(connection):
            raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")
        columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})")}
        if return_column not in columns:
            raise ValueError(f"Column {return_column!r} not found in {TABLE_NAME}.")
        rows = connection.execute(
            f"""
            SELECT *
            FROM {TABLE_NAME}
            WHERE symbol IN ({placeholders})
              AND timeframe = ?
              AND {return_column} IS NOT NULL
              AND time_server IS NOT NULL
            ORDER BY symbol ASC, time_server ASC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return [dict(row) for row in reader]


def candidate_file_path(validation_dir: Path, run_id: str, direction: str, candidate_type: str) -> Path:
    filename = FINAL_CANDIDATES_FILE if candidate_type == "cross_pair" else PAIR_SPECIFIC_CANDIDATES_FILE
    return validation_dir / run_id / direction / filename


def candidate_is_final(row: dict[str, str], candidate_type: str) -> bool:
    if candidate_type == "cross_pair":
        classification = str(row.get("final_classification") or "").strip()
        return classification in {"", "select", "watchlist"}
    classification = str(row.get("pair_specific_classification") or "").strip()
    return classification in {"select_pair_specific", "watchlist_pair_specific"}


def load_candidate_file(path: Path, candidate_type: str, direction: str, cost_mode: str, return_mode: str) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"Candidate file not found: {path}")
    candidates: list[dict[str, object]] = []
    for row in read_csv_rows(path):
        combination_key = str(row.get("combination_key") or "").strip()
        if not combination_key:
            continue
        if not candidate_is_final(row, candidate_type):
            continue
        row_direction = str(row.get("direction") or direction).strip().lower()
        row_cost_mode = str(row.get("cost_mode") or cost_mode).strip().lower()
        row_return_mode = str(row.get("return_mode") or return_mode).strip().lower()
        if row_direction != direction or row_cost_mode != cost_mode or row_return_mode != return_mode:
            continue
        candidate = dict(row)
        candidate["candidate_type"] = candidate_type
        candidate["source_file"] = str(path)
        candidates.append(candidate)
    return candidates


def load_candidates(
    validation_dir: Path,
    run_id: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
    include_cross_pair: bool,
    include_pair_specific: bool,
    max_candidates: int,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    if include_cross_pair:
        candidates.extend(
            load_candidate_file(
                candidate_file_path(validation_dir, run_id, direction, "cross_pair"),
                "cross_pair",
                direction,
                cost_mode,
                return_mode,
            )
        )
    if include_pair_specific:
        candidates.extend(
            load_candidate_file(
                candidate_file_path(validation_dir, run_id, direction, "pair_specific"),
                "pair_specific",
                direction,
                cost_mode,
                return_mode,
            )
        )
    return candidates[:max_candidates]


def candidate_classification(row: dict[str, object]) -> str:
    return str(row.get("final_classification") or row.get("pair_specific_classification") or "")


def candidate_symbol(row: dict[str, object]) -> str:
    return str(row.get("symbol") or "").strip().upper()


def skip_record(row: dict[str, object], skip_reason: str, detail: str = "") -> dict[str, object]:
    return {
        "candidate_type": row.get("candidate_type", ""),
        "combination_key": row.get("combination_key", ""),
        "symbol": row.get("symbol", ""),
        "direction": row.get("direction", ""),
        "cost_mode": row.get("cost_mode", ""),
        "return_mode": row.get("return_mode", ""),
        "skip_reason": skip_reason,
        "detail": detail,
        "source_file": row.get("source_file", ""),
    }


def classify_vs_random(row: dict[str, object], min_trades: int) -> str:
    trades_count = int(row.get("trades_count") or 0)
    if trades_count < min_trades:
        return "low_sample"

    primary_percentiles = [
        comparable_float(row.get("cumulative_return_percentile")),
        comparable_float(row.get("profit_factor_percentile")),
        comparable_float(row.get("mean_return_percentile")),
        comparable_float(row.get("win_rate_percentile")),
        comparable_float(row.get("max_drawdown_percentile")),
    ]
    usable = [value for value in primary_percentiles if value is not None]
    avg_primary = mean(usable) if usable else 0.0
    strong_count = sum(1 for value in usable if value >= 90)
    moderate_count = sum(1 for value in usable if value >= 75)
    cumulative_p = comparable_float(row.get("cumulative_return_empirical_p_value"))
    mean_p = comparable_float(row.get("mean_return_empirical_p_value"))

    if strong_count >= 4 and avg_primary >= 88 and cumulative_p is not None and cumulative_p <= 0.05:
        return "robust_vs_random"
    if moderate_count >= 3 and avg_primary >= 72 and (
        (cumulative_p is not None and cumulative_p <= 0.10) or (mean_p is not None and mean_p <= 0.10)
    ):
        return "interesting_vs_random"
    if avg_primary >= 55 or moderate_count >= 2:
        return "weak_vs_random"
    return "not_better_than_random"


def evaluate_candidate(
    candidate: dict[str, object],
    universe_rows: list[dict[str, object]],
    *,
    symbols: list[str],
    return_column: str,
    direction: str,
    cost_config: dict[str, Any],
    cost_mode: str,
    return_mode: str,
    random_runs: int,
    rng: random.Random,
    min_trades: int,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    combination_key = str(candidate.get("combination_key") or "").strip()
    if not combination_key:
        return None, skip_record(candidate, "empty_combination_key")

    precheck_skip = precheck_combination_skip_reason(combination_key)
    if precheck_skip is not None:
        return None, skip_record(candidate, precheck_skip)

    candidate_type = str(candidate.get("candidate_type") or "")
    symbol = candidate_symbol(candidate)
    if candidate_type == "pair_specific":
        if not symbol:
            return None, skip_record(candidate, "missing_pair_specific_symbol")
        if symbol not in symbols:
            return None, skip_record(candidate, "symbol_not_requested", f"{symbol} not in --symbols")
        candidate_universe = [row for row in universe_rows if str(row.get("symbol") or "").upper() == symbol]
    else:
        candidate_universe = list(universe_rows)
        symbol = ""

    if not candidate_universe:
        return None, skip_record(candidate, "empty_universe")

    try:
        predicate = build_predicate(candidate_universe, combination_key, TABLE_NAME)
    except ValueError as exc:
        return None, skip_record(candidate, "unparsable_condition", str(exc))

    candidate_rows = [row for row in candidate_universe if predicate(row)]
    candidate_metrics = selected_return_metrics(
        candidate_rows,
        return_column=return_column,
        direction=direction,
        cost_config=cost_config,
        cost_mode=cost_mode,
        return_mode=return_mode,
        fallback_symbol=symbol or None,
    )
    trades_count = int(candidate_metrics.get("trades_count") or 0)
    if trades_count == 0:
        return None, skip_record(candidate, "zero_candidate_trades")
    if trades_count > len(candidate_universe):
        return None, skip_record(candidate, "candidate_trades_exceed_universe")

    random_metrics: list[dict[str, object]] = []
    for _index in range(random_runs):
        sample = random_sample_rows(candidate_universe, trades_count, rng)
        random_metrics.append(
            selected_return_metrics(
                sample,
                return_column=return_column,
                direction=direction,
                cost_config=cost_config,
                cost_mode=cost_mode,
                return_mode=return_mode,
                fallback_symbol=symbol or None,
            )
        )

    result: dict[str, object] = {
        "candidate_type": candidate_type,
        "combination_key": combination_key,
        "symbol": symbol,
        "symbols_universe": " ".join(symbols) if candidate_type == "cross_pair" else symbol,
        "direction": direction,
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "candidate_classification": candidate_classification(candidate),
        "universe_trades_count": len(candidate_universe),
        "trades_count": trades_count,
        "random_runs": random_runs,
    }
    for metric in RANDOM_METRICS:
        result[metric] = candidate_metrics.get(metric)
        random_values = [row.get(metric) for row in random_metrics]
        stats = random_distribution_stats(random_values)
        result[f"{metric}_random_mean"] = stats["mean"]
        result[f"{metric}_random_median"] = stats["median"]
        result[f"{metric}_random_p05"] = stats["p05"]
        result[f"{metric}_random_p95"] = stats["p95"]
        result[f"{metric}_percentile"] = metric_percentile(metric, candidate_metrics.get(metric), random_values)
        result[f"{metric}_empirical_p_value"] = metric_empirical_p_value(
            metric,
            candidate_metrics.get(metric),
            random_values,
        )
    result["random_baseline_classification"] = classify_vs_random(result, min_trades)
    return result, None


def detail_fieldnames() -> list[str]:
    base = [
        "candidate_type",
        "combination_key",
        "symbol",
        "symbols_universe",
        "direction",
        "cost_mode",
        "return_mode",
        "candidate_classification",
        "random_baseline_classification",
        "universe_trades_count",
        "trades_count",
        "random_runs",
    ]
    metric_fields: list[str] = []
    for metric in RANDOM_METRICS:
        metric_fields.extend(
            [
                metric,
                f"{metric}_random_mean",
                f"{metric}_random_median",
                f"{metric}_random_p05",
                f"{metric}_random_p95",
                f"{metric}_percentile",
                f"{metric}_empirical_p_value",
            ]
        )
    return [*base, *metric_fields]


def skipped_fieldnames() -> list[str]:
    return [
        "candidate_type",
        "combination_key",
        "symbol",
        "direction",
        "cost_mode",
        "return_mode",
        "skip_reason",
        "detail",
        "source_file",
    ]


def summary_fieldnames() -> list[str]:
    return [
        "candidate_type",
        "direction",
        "cost_mode",
        "return_mode",
        "candidates_tested",
        "robust_vs_random",
        "interesting_vs_random",
        "weak_vs_random",
        "not_better_than_random",
        "low_sample",
        "avg_cumulative_return_percentile",
        "avg_profit_factor_percentile",
        "avg_max_drawdown_percentile",
        "avg_mean_return_percentile",
        "avg_payoff_ratio_percentile",
        "avg_breakeven_winrate_percentile",
        "avg_breakeven_winrate_margin_percentile",
    ]


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe_value(row.get(key)) for key in fieldnames})


def average_field(rows: list[dict[str, object]], field: str) -> float | None:
    values = [value for value in (comparable_float(row.get(field)) for row in rows) if value is not None]
    return mean(values) if values else None


def summarize_results(results: list[dict[str, object]], direction: str, cost_mode: str, return_mode: str) -> list[dict[str, object]]:
    if not results:
        return [
            {
                "candidate_type": "all",
                "direction": direction,
                "cost_mode": cost_mode,
                "return_mode": return_mode,
                "candidates_tested": 0,
                "robust_vs_random": 0,
                "interesting_vs_random": 0,
                "weak_vs_random": 0,
                "not_better_than_random": 0,
                "low_sample": 0,
                "avg_cumulative_return_percentile": None,
                "avg_profit_factor_percentile": None,
                "avg_max_drawdown_percentile": None,
                "avg_mean_return_percentile": None,
                "avg_payoff_ratio_percentile": None,
                "avg_breakeven_winrate_percentile": None,
                "avg_breakeven_winrate_margin_percentile": None,
            }
        ]

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    grouped["all"] = list(results)
    for row in results:
        grouped[str(row.get("candidate_type") or "unknown")].append(row)

    summary_rows: list[dict[str, object]] = []
    for candidate_type in sorted(grouped):
        rows = grouped[candidate_type]
        classifications = Counter(str(row.get("random_baseline_classification") or "") for row in rows)
        summary_rows.append(
            {
                "candidate_type": candidate_type,
                "direction": direction,
                "cost_mode": cost_mode,
                "return_mode": return_mode,
                "candidates_tested": len(rows),
                "robust_vs_random": classifications.get("robust_vs_random", 0),
                "interesting_vs_random": classifications.get("interesting_vs_random", 0),
                "weak_vs_random": classifications.get("weak_vs_random", 0),
                "not_better_than_random": classifications.get("not_better_than_random", 0),
                "low_sample": classifications.get("low_sample", 0),
                "avg_cumulative_return_percentile": average_field(rows, "cumulative_return_percentile"),
                "avg_profit_factor_percentile": average_field(rows, "profit_factor_percentile"),
                "avg_max_drawdown_percentile": average_field(rows, "max_drawdown_percentile"),
                "avg_mean_return_percentile": average_field(rows, "mean_return_percentile"),
                "avg_payoff_ratio_percentile": average_field(rows, "payoff_ratio_percentile"),
                "avg_breakeven_winrate_percentile": average_field(rows, "breakeven_winrate_percentile"),
                "avg_breakeven_winrate_margin_percentile": average_field(rows, "breakeven_winrate_margin_percentile"),
            }
        )
    return summary_rows


def write_report(
    path: Path,
    *,
    run_id: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
    symbols: list[str],
    timeframe: str,
    target_horizon: int,
    random_runs: int,
    seed: int,
    results: list[dict[str, object]],
    skipped: list[dict[str, object]],
    warnings: list[str],
) -> None:
    classifications = Counter(str(row.get("random_baseline_classification") or "") for row in results)
    lines = [
        "# Random Baseline Robustness Report",
        "",
        "This report is research-only. It compares final validated candidates against random same-size samples; it does not create live trading signals or trading recommendations.",
        "",
        "## Run Context",
        "",
        f"- Run ID: {run_id}",
        f"- Direction: {direction}",
        f"- Cost mode: {cost_mode}",
        f"- Return mode: {return_mode}",
        f"- Symbols: {' '.join(symbols)}",
        f"- Timeframe: {timeframe}",
        f"- Target horizon: {target_horizon}",
        f"- Random runs per candidate: {random_runs}",
        f"- Seed: {seed}",
        "",
        "## Summary",
        "",
        f"- Candidates tested: {len(results)}",
        f"- Skipped candidates: {len(skipped)}",
        f"- Robust vs random: {classifications.get('robust_vs_random', 0)}",
        f"- Interesting vs random: {classifications.get('interesting_vs_random', 0)}",
        f"- Weak vs random: {classifications.get('weak_vs_random', 0)}",
        f"- Not better than random: {classifications.get('not_better_than_random', 0)}",
        f"- Low sample: {classifications.get('low_sample', 0)}",
        "",
        "## Method",
        "",
        "- Only final validation candidates are tested.",
        "- Each candidate is applied to `ml_dataset` using the stored `combination_key`.",
        "- Random baselines sample without replacement from the same symbol universe and use the same number of trades as the candidate.",
        "- Long and short, gross and net, cross-pair and pair-specific candidates remain separate.",
        "- `numeric_tercile` and raw price-level conditions are skipped because they are not time-safe final-validation conditions.",
    ]
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_output_dir(base_output_dir: Path, run_id: str, direction: str, overwrite: bool) -> Path:
    output_dir = base_output_dir / run_id / direction
    protected = [DETAIL_OUTPUT, SUMMARY_OUTPUT, REPORT_OUTPUT, SKIPPED_OUTPUT]
    existing = [output_dir / filename for filename in protected if (output_dir / filename).exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Random baseline output already exists under {output_dir}. Pass --overwrite to regenerate it.")
    return output_dir


def rows_by_symbol(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("symbol") or "").upper()].append(row)
    return dict(grouped)


def run_random_baseline_tests(args: argparse.Namespace) -> dict[str, Path]:
    if args.random_runs <= 0:
        raise ValueError("--random-runs must be greater than zero.")
    if args.max_candidates <= 0:
        raise ValueError("--max-candidates must be greater than zero.")
    if args.min_trades <= 0:
        raise ValueError("--min-trades must be greater than zero.")
    if not args.include_cross_pair and not args.include_pair_specific:
        raise ValueError("At least one of --include-cross-pair or --include-pair-specific must be enabled.")

    direction = normalize_direction(args.direction)
    symbols = normalize_symbols(args.symbols)
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    return_column = f"future_return_{args.target_horizon}"
    output_dir = resolve_output_dir(args.output_dir, args.run_id, direction, args.overwrite)

    universe_rows = load_universe_rows(args.db_path, symbols, args.timeframe, return_column)
    cost_config = load_cost_config(args.cost_config)
    cost_report = {}
    warnings: list[str] = []
    if cost_mode == "estimated":
        cost_report = validate_estimated_cost_config(
            symbols=symbols,
            rows_by_symbol=rows_by_symbol(universe_rows),
            config=cost_config,
            strict=args.strict_cost_config,
        )
        warnings.extend(cost_report_warnings(cost_report))

    candidates = load_candidates(
        args.validation_dir,
        args.run_id,
        direction,
        cost_mode,
        return_mode,
        args.include_cross_pair,
        args.include_pair_specific,
        args.max_candidates,
    )

    rng = random.Random(args.seed)
    results: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for candidate in candidates:
        result, skip = evaluate_candidate(
            candidate,
            universe_rows,
            symbols=symbols,
            return_column=return_column,
            direction=direction,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
            random_runs=args.random_runs,
            rng=rng,
            min_trades=args.min_trades,
        )
        if result is not None:
            result.update(cost_report_fields(cost_report, result.get("symbol") or None))
            result["seed"] = args.seed
            results.append(result)
        if skip is not None:
            skipped.append(skip)

    summary_rows = summarize_results(results, direction, cost_mode, return_mode)
    detail_path = output_dir / DETAIL_OUTPUT
    summary_path = output_dir / SUMMARY_OUTPUT
    report_path = output_dir / REPORT_OUTPUT
    skipped_path = output_dir / SKIPPED_OUTPUT
    write_csv(detail_path, results, [*detail_fieldnames(), "seed", "cost_config_source", "point_size_source", "spread_source_used", "symbols_using_default_costs"])
    write_csv(summary_path, summary_rows, summary_fieldnames())
    write_csv(skipped_path, skipped, skipped_fieldnames())
    write_report(
        report_path,
        run_id=args.run_id,
        direction=direction,
        cost_mode=cost_mode,
        return_mode=return_mode,
        symbols=symbols,
        timeframe=args.timeframe,
        target_horizon=args.target_horizon,
        random_runs=args.random_runs,
        seed=args.seed,
        results=results,
        skipped=skipped,
        warnings=warnings,
    )

    print(f"Output directory: {output_dir.resolve()}")
    print(f"Random baseline detail written: {detail_path.resolve()}")
    print(f"Random baseline summary written: {summary_path.resolve()}")
    print(f"Random baseline report written: {report_path.resolve()}")
    print(f"Skipped candidates written: {skipped_path.resolve()}")
    print(f"Candidates tested: {len(results)}")
    print(f"Skipped candidates: {len(skipped)}")

    return {
        "detail": detail_path,
        "summary": summary_path,
        "report": report_path,
        "skipped": skipped_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare final research candidates against random same-trade-count baselines."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--target-horizon", type=int, default=10)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--validation-dir", type=Path, default=DEFAULT_VALIDATION_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--cost-config", type=Path, default=DEFAULT_COST_CONFIG)
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--random-runs", type=int, default=250)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-candidates", type=int, default=50)
    parser.add_argument("--include-cross-pair", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-pair-specific", action="store_true")
    parser.add_argument("--min-trades", type=int, default=100)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        run_random_baseline_tests(parse_args())
    except (FileNotFoundError, FileExistsError, ValueError, sqlite3.Error, OSError) as exc:
        print(f"Random baseline tests failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
