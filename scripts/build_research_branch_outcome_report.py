"""Build a research-only branch outcome report from existing diagnostics.

The report records the closure of an offline research branch using already
generated TP/SL path diagnostic outputs. It does not run backtests, search
combinations, optimize TP/SL, connect to MetaTrader5, or add execution logic.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path
import sys
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from research_costs import validate_cost_args
    from research_metrics import csv_safe_value, normalize_direction, safe_float
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_research_branch_outcome_report
    from scripts.research_costs import validate_cost_args
    from scripts.research_metrics import csv_safe_value, normalize_direction, safe_float


DEFAULT_TP_SL_ROOT = BASE_DIR / "reports" / "tp_sl_path_backtests"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "research_branch_outcomes"

REPORT_FILE = "branch_outcome_report.md"
SUMMARY_FILE = "branch_outcome_summary.csv"
REJECTED_FILE = "rejected_combinations.csv"
OUTPUT_FILES = (REPORT_FILE, SUMMARY_FILE, REJECTED_FILE)

DECISION_CLOSED_NO_SURVIVOR = "CLOSED_NO_SURVIVOR"
DECISION_NO_TESTED_COMBINATIONS = "NO_TESTED_COMBINATIONS"
DECISION_NEEDS_REVIEW = "NEEDS_REVIEW"
DECISION_CANDIDATES_FOUND = "CANDIDATES_FOUND"
SUPPORTED_DECISIONS = (
    DECISION_CLOSED_NO_SURVIVOR,
    DECISION_NO_TESTED_COMBINATIONS,
    DECISION_NEEDS_REVIEW,
    DECISION_CANDIDATES_FOUND,
)
CLASSIFICATIONS = ("SCARTARE", "DA_APPROFONDIRE", "CANDIDATA_A_TEST_SUCCESSIVI")
CONCENTRATION_WARNING_THRESHOLD = 50.0

SUMMARY_FIELDNAMES = [
    "run_id",
    "branch_id",
    "branch_title",
    "timeframe",
    "horizon",
    "target_family",
    "cost_mode",
    "return_mode",
    "symbols",
    "directions",
    "decision",
    "long_tested_count",
    "long_SCARTARE_count",
    "long_DA_APPROFONDIRE_count",
    "long_CANDIDATA_A_TEST_SUCCESSIVI_count",
    "short_tested_count",
    "short_SCARTARE_count",
    "short_DA_APPROFONDIRE_count",
    "short_CANDIDATA_A_TEST_SUCCESSIVI_count",
    "notes",
]

REJECTED_FIELDNAMES = [
    "symbol",
    "direction",
    "source_combination_id",
    "source_feature_1",
    "source_scenario_1",
    "source_feature_family_1",
    "source_feature_2",
    "source_scenario_2",
    "source_feature_family_2",
    "trades_count",
    "tp_hit_rate",
    "sl_hit_rate",
    "timeout_rate",
    "mean_R",
    "profit_factor_R",
    "expectancy_R",
    "max_drawdown_R",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "baseline_mean_R",
    "baseline_profit_factor_R",
    "mean_R_vs_baseline",
    "profit_factor_R_vs_baseline",
    "classification",
    "rejection_reason",
]


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def to_float(value: object) -> float | None:
    return safe_float(value)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return [dict(row) for row in csv.DictReader(csv_file)]


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe_value(row.get(field)) for field in fieldnames})


def output_dir_for(output_root: Path, run_id: str) -> Path:
    return output_root / run_id


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_dir_for(output_root, run_id)
    return {
        "branch_outcome_report": output_dir / REPORT_FILE,
        "branch_outcome_summary": output_dir / SUMMARY_FILE,
        "rejected_combinations": output_dir / REJECTED_FILE,
    }


def ensure_outputs_writable(paths: Iterable[Path], overwrite: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Research branch outcome outputs already exist. Pass --overwrite to regenerate: "
            + ", ".join(str(path) for path in existing)
        )


def tp_sl_paths(tp_sl_root: Path, run_id: str, direction: str) -> dict[str, Path]:
    base = tp_sl_root / run_id / direction
    return {
        "summary": base / "tp_sl_path_backtest_summary.csv",
        "detail": base / "tp_sl_path_backtest_detail.csv",
    }


def require_input_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required TP/SL path {label} not found: {path}")


def run_id_for_direction(args: argparse.Namespace, direction: str) -> str:
    value = getattr(args, f"{direction}_tp_sl_run_id", None)
    if not value:
        raise ValueError(f"--{direction}-tp-sl-run-id is required when direction {direction!r} is requested.")
    return str(value)


def load_direction_rows(args: argparse.Namespace, direction: str) -> tuple[list[dict[str, str]], dict[str, Path]]:
    run_id = run_id_for_direction(args, direction)
    paths = tp_sl_paths(Path(args.tp_sl_root), run_id, direction)
    require_input_file(paths["summary"], f"summary for {direction}")
    require_input_file(paths["detail"], f"detail for {direction}")
    _detail_rows = read_csv_rows(paths["detail"])
    return read_csv_rows(paths["summary"]), paths


def classification_counts(rows: list[dict[str, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        label = str(row.get("classification") or "").strip()
        if label:
            counts[label] += 1
    return counts


def format_count_lines(rows_by_direction: dict[str, list[dict[str, str]]]) -> list[str]:
    lines: list[str] = []
    for direction in ("long", "short"):
        if direction not in rows_by_direction:
            continue
        rows = rows_by_direction[direction]
        counts = classification_counts(rows)
        lines.append(f"- {direction}: tested `{len(rows)}`")
        for label in CLASSIFICATIONS:
            lines.append(f"- {direction} {label}: `{counts.get(label, 0)}`")
    return lines or ["- No direction rows loaded."]


def numeric_sort_value(row: dict[str, str], column: str) -> float:
    value = to_float(row.get(column))
    return value if value is not None else float("-inf")


def best_row(rows: list[dict[str, str]], column: str) -> dict[str, str] | None:
    if not rows:
        return None
    return max(rows, key=lambda row: numeric_sort_value(row, column))


def num_text(value: object, digits: int = 6) -> str:
    parsed = to_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.{digits}f}"


def best_row_lines(rows_by_direction: dict[str, list[dict[str, str]]], column: str) -> list[str]:
    lines: list[str] = []
    for direction in ("long", "short"):
        row = best_row(rows_by_direction.get(direction, []), column)
        if row is None:
            lines.append(f"- {direction}: none")
            continue
        lines.append(
            "- {direction}: {symbol} `{combo}` trades={trades}, mean_R={mean_R}, profit_factor_R={pf}, classification={classification}".format(
                direction=direction,
                symbol=row.get("symbol", ""),
                combo=row.get("source_combination_id", ""),
                trades=row.get("trades_count", ""),
                mean_R=num_text(row.get("mean_R")),
                pf=num_text(row.get("profit_factor_R")),
                classification=row.get("classification", ""),
            )
        )
    return lines


def rejection_reason(row: dict[str, str]) -> str:
    reasons: list[str] = []
    mean_r = to_float(row.get("mean_R"))
    profit_factor = to_float(row.get("profit_factor_R"))
    mean_delta = to_float(row.get("mean_R_vs_baseline"))
    profit_delta = to_float(row.get("profit_factor_R_vs_baseline"))
    concentration = to_float(row.get("top_5_percent_trades_contribution_pct"))

    if mean_r is None or mean_r <= 0:
        reasons.append("mean_R <= 0")
    if profit_factor is None or profit_factor <= 1:
        reasons.append("profit_factor_R <= 1")
    if mean_delta is None or profit_delta is None or mean_delta <= 0 or profit_delta <= 0:
        reasons.append("baseline_not_beaten")
    if concentration is not None and concentration > CONCENTRATION_WARNING_THRESHOLD:
        reasons.append("concentration_warning")
    return "; ".join(reasons) or "classified_SCARTARE"


def rejected_row(row: dict[str, str]) -> dict[str, object]:
    return {
        "symbol": row.get("symbol", ""),
        "direction": row.get("direction", ""),
        "source_combination_id": row.get("source_combination_id", ""),
        "source_feature_1": row.get("source_feature_1", ""),
        "source_scenario_1": row.get("source_scenario_1", ""),
        "source_feature_family_1": row.get("source_feature_family_1", ""),
        "source_feature_2": row.get("source_feature_2", ""),
        "source_scenario_2": row.get("source_scenario_2", ""),
        "source_feature_family_2": row.get("source_feature_family_2", ""),
        "trades_count": row.get("trades_count", ""),
        "tp_hit_rate": row.get("tp_hit_rate", ""),
        "sl_hit_rate": row.get("sl_hit_rate", ""),
        "timeout_rate": row.get("timeout_rate", ""),
        "mean_R": row.get("mean_R", ""),
        "profit_factor_R": row.get("profit_factor_R", ""),
        "expectancy_R": row.get("expectancy_R", ""),
        "max_drawdown_R": row.get("max_drawdown_R", ""),
        "monthly_positive_ratio": row.get("monthly_positive_ratio", ""),
        "quarterly_positive_ratio": row.get("quarterly_positive_ratio", ""),
        "baseline_mean_R": row.get("baseline_mean_R", ""),
        "baseline_profit_factor_R": row.get("baseline_profit_factor_R", ""),
        "mean_R_vs_baseline": row.get("mean_R_vs_baseline", ""),
        "profit_factor_R_vs_baseline": row.get("profit_factor_R_vs_baseline", ""),
        "classification": row.get("classification", ""),
        "rejection_reason": rejection_reason(row),
    }


def rejected_rows(rows_by_direction: dict[str, list[dict[str, str]]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for direction in ("long", "short"):
        rows.extend(
            rejected_row(row)
            for row in rows_by_direction.get(direction, [])
            if str(row.get("classification") or "") == "SCARTARE"
        )
    return rows


def summary_row(
    *,
    run_id: str,
    args: argparse.Namespace,
    rows_by_direction: dict[str, list[dict[str, str]]],
) -> dict[str, object]:
    row: dict[str, object] = {
        "run_id": run_id,
        "branch_id": args.branch_id,
        "branch_title": args.branch_title,
        "timeframe": args.timeframe,
        "horizon": args.horizon,
        "target_family": args.target_family,
        "cost_mode": args.cost_mode,
        "return_mode": args.return_mode,
        "symbols": " ".join(args.symbols),
        "directions": " ".join(args.directions),
        "decision": args.decision,
        "notes": "Branch closed for current feature set and cost assumptions.",
    }
    for direction in ("long", "short"):
        rows = rows_by_direction.get(direction, [])
        counts = classification_counts(rows)
        row[f"{direction}_tested_count"] = len(rows)
        for label in CLASSIFICATIONS:
            row[f"{direction}_{label}_count"] = counts.get(label, 0)
    return row


def write_report(
    path: Path,
    *,
    run_id: str,
    args: argparse.Namespace,
    rows_by_direction: dict[str, list[dict[str, str]]],
    input_paths: dict[str, dict[str, Path]],
) -> None:
    if args.decision == DECISION_CLOSED_NO_SURVIVOR:
        evidence_lines = [
            "- No single-feature estimated/net survivor.",
            "- No robust controlled 2-filter survivor.",
            "- No TP/SL path-exit survivor.",
            "- All tested TP/SL path-exit combinations were classified as `SCARTARE`.",
            "- Branch closed for current feature set and cost assumptions.",
        ]
    elif args.decision == DECISION_NO_TESTED_COMBINATIONS:
        evidence_lines = [
            "- No TP/SL path-exit rows were tested for this branch.",
            "- Branch cannot be classified as closed or reviewable from path-exit results.",
            "- Review skipped and child-output diagnostics before interpreting this branch.",
        ]
    elif args.decision == DECISION_NEEDS_REVIEW:
        evidence_lines = [
            "- At least one TP/SL path-exit row was classified as `DA_APPROFONDIRE`.",
            "- No TP/SL path-exit row was classified as `CANDIDATA_A_TEST_SUCCESSIVI`.",
            "- Branch remains research-only and needs further offline review.",
        ]
    else:
        evidence_lines = [
            "- At least one TP/SL path-exit row was classified as `CANDIDATA_A_TEST_SUCCESSIVI`.",
            "- Branch remains research-only and requires later offline validation before any broader design work.",
        ]

    lines = [
        "# Research Branch Outcome Report",
        "",
        "## Research-only warning",
        "",
        "- Offline closure record built from already-generated diagnostic outputs.",
        "- Not operational guidance, not broker execution, and not deployment-ready.",
        "",
        "## Branch metadata",
        "",
        f"- Run ID: `{run_id}`",
        f"- Branch ID: `{args.branch_id}`",
        f"- Branch title: `{args.branch_title}`",
        f"- Symbols: `{', '.join(args.symbols)}`",
        f"- Directions: `{', '.join(args.directions)}`",
        f"- Timeframe: `{args.timeframe}`",
        f"- Horizon: `{args.horizon}`",
        f"- Target family: `{args.target_family}`",
        f"- Cost mode: `{args.cost_mode}`",
        f"- Return mode: `{args.return_mode}`",
        "",
        "## Decision",
        "",
        f"- `{args.decision}`",
        "",
        "## Evidence",
        "",
        *evidence_lines,
        "",
        "## Long/short classification counts",
        "",
        *format_count_lines(rows_by_direction),
        "",
        "## Best mean_R rows",
        "",
        *best_row_lines(rows_by_direction, "mean_R"),
        "",
        "## Best profit_factor_R rows",
        "",
        *best_row_lines(rows_by_direction, "profit_factor_R"),
        "",
        "## Rejected combinations reference",
        "",
        "- See `rejected_combinations.csv` in this output folder.",
        "",
        "## Input references",
        "",
    ]
    for direction in args.directions:
        paths = input_paths.get(direction, {})
        lines.append(f"- {direction} summary: `{paths.get('summary', '')}`")
        lines.append(f"- {direction} detail: `{paths.get('detail', '')}`")
    lines.extend(
        [
            "",
            "## Methodology guardrails",
            "",
            "- Fixed TP=2ATR, SL=1ATR, horizon=10.",
            "- No TP/SL optimization.",
            "- No new features.",
            "- No new combinations searched.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_symbols(values: list[str]) -> list[str]:
    symbols = []
    seen = set()
    for value in values:
        symbol = str(value or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    if not symbols:
        raise ValueError("--symbols must include at least one symbol.")
    return symbols


def normalize_directions(values: list[str]) -> list[str]:
    directions = []
    seen = set()
    for value in values:
        direction = normalize_direction(value)
        if direction not in seen:
            seen.add(direction)
            directions.append(direction)
    if not directions:
        raise ValueError("--directions must include at least one direction.")
    return directions


def run_branch_outcome_report(args: argparse.Namespace) -> dict[str, Path]:
    args.symbols = normalize_symbols(list(args.symbols))
    args.directions = normalize_directions(list(args.directions))
    args.cost_mode, args.return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    if args.decision not in SUPPORTED_DECISIONS:
        raise ValueError(f"Unsupported branch decision: {args.decision!r}")

    run_id = str(args.run_id or current_run_id())
    outputs = output_paths(Path(args.output_root), run_id)
    ensure_outputs_writable(outputs.values(), bool(args.overwrite))

    rows_by_direction: dict[str, list[dict[str, str]]] = {}
    input_paths: dict[str, dict[str, Path]] = {}
    for direction in args.directions:
        rows, paths = load_direction_rows(args, direction)
        rows_by_direction[direction] = rows
        input_paths[direction] = paths

    summary_rows = [summary_row(run_id=run_id, args=args, rows_by_direction=rows_by_direction)]
    rejected = rejected_rows(rows_by_direction)

    write_csv(outputs["branch_outcome_summary"], summary_rows, SUMMARY_FIELDNAMES)
    write_csv(outputs["rejected_combinations"], rejected, REJECTED_FIELDNAMES)
    write_report(
        outputs["branch_outcome_report"],
        run_id=run_id,
        args=args,
        rows_by_direction=rows_by_direction,
        input_paths=input_paths,
    )
    return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only branch closure record from existing TP/SL path diagnostics."
    )
    parser.add_argument("--branch-id", required=True)
    parser.add_argument("--branch-title", required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--directions", nargs="+", choices=("long", "short"), required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--horizon", type=int, required=True)
    parser.add_argument("--target-family", required=True)
    parser.add_argument("--cost-mode", choices=("none", "estimated"), required=True)
    parser.add_argument("--return-mode", choices=("gross", "net"), required=True)
    parser.add_argument("--long-tp-sl-run-id")
    parser.add_argument("--short-tp-sl-run-id")
    parser.add_argument("--decision", choices=SUPPORTED_DECISIONS, required=True)
    parser.add_argument("--tp-sl-root", type=Path, default=DEFAULT_TP_SL_ROOT, help=f"Default: {DEFAULT_TP_SL_ROOT}")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=f"Default: {DEFAULT_OUTPUT_ROOT}")
    parser.add_argument("--run-id")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    try:
        outputs = run_branch_outcome_report(parse_args())
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"Research branch outcome report failed: {exc}")
        return 1
    print("Research branch outcome report complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
