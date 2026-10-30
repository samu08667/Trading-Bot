"""Compare gross and estimated-net preferred feature backtest reports.

This diagnostic compares already-generated preferred feature backtest summary
rows. It does not run backtests, change costs, create strategies, or provide
operational guidance.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from research_metrics import csv_safe_value, normalize_direction
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.compare_preferred_feature_backtest_cost_modes
    from scripts.research_metrics import csv_safe_value, normalize_direction


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_ROOT = BASE_DIR / "reports" / "preferred_feature_backtests"
DEFAULT_OUTPUT_ROOT = DEFAULT_REPORTS_ROOT / "cost_mode_comparison"
DEFAULT_DIRECTIONS = ("long", "short")
SUMMARY_FILE = "preferred_feature_backtest_summary.csv"
SKIPPED_FILE = "skipped_features.csv"
OUTPUT_CSV = "cost_mode_comparison.csv"
OUTPUT_REPORT = "cost_mode_comparison_report.md"
METADATA_FIELDNAMES = [
    "scenario_source",
    "feature_in_shortlist",
    "is_preferred_shortlist_feature",
    "feature_family",
]
SOURCE_PRIORITY = {
    "unknown": 0,
    "extra_default_scenario": 1,
    "standard_context_scenario": 2,
    "preferred_shortlist_feature": 3,
}

FIELDNAMES = [
    "symbol",
    "direction",
    "feature",
    "feature_family",
    "scenario",
    "scenario_source",
    "is_preferred_shortlist_feature",
    "feature_in_shortlist",
    "condition_type",
    "condition_value",
    "gross_trades_count",
    "gross_mean_return",
    "gross_profit_factor",
    "gross_win_rate",
    "gross_max_drawdown",
    "net_trades_count",
    "net_mean_return",
    "net_profit_factor",
    "net_win_rate",
    "net_max_drawdown",
    "estimated_cost_drag_mean_return",
    "profit_factor_drop",
    "gross_positive",
    "net_positive",
    "cost_erased_edge",
    "less_bad_than_baseline_net",
    "notes",
]


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def bool_from_text(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def first_nonempty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def normalize_source(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "unknown"


def preferred_source(*values: object) -> str:
    sources = [normalize_source(value) for value in values]
    return max(sources or ["unknown"], key=lambda source: SOURCE_PRIORITY.get(source, 1))


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


def metric_delta(value: object, baseline: object) -> float | None:
    parsed_value = safe_float(value)
    parsed_baseline = safe_float(baseline)
    if parsed_value is None or parsed_baseline is None:
        return None
    return parsed_value - parsed_baseline


def csv_value(value: object) -> object:
    return csv_safe_value(value)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def read_csv_rows_and_fieldnames(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader), list(reader.fieldnames or [])


def metadata_warnings(
    *,
    rows: list[dict[str, str]],
    fieldnames: list[str],
    label: str,
) -> list[str]:
    warnings: list[str] = []
    fieldname_set = set(fieldnames)
    for column in METADATA_FIELDNAMES:
        if column not in fieldname_set:
            warnings.append(
                f"{label} input is missing `{column}`; comparison output used deterministic fallback values."
            )
            continue
        blank_count = sum(1 for row in rows if not str(row.get(column) or "").strip())
        if blank_count:
            warnings.append(
                f"{label} input has {blank_count}/{len(rows)} blank `{column}` values; comparison output resolved from gross/net rows where possible."
            )
    return warnings


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def summary_path(reports_root: Path, run_id: str, direction: str) -> Path:
    return reports_root / run_id / direction / SUMMARY_FILE


def skipped_path(reports_root: Path, run_id: str, direction: str) -> Path:
    return reports_root / run_id / direction / SKIPPED_FILE


def output_dir(output_root: Path, gross_run_id: str, net_run_id: str, direction: str) -> Path:
    return output_root / f"{gross_run_id}_vs_{net_run_id}" / direction


def row_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(row.get("symbol") or ""),
        str(row.get("direction") or ""),
        str(row.get("feature") or ""),
        str(row.get("scenario") or row.get("scenario_condition_tested") or ""),
        str(row.get("condition_type") or ""),
        str(row.get("condition_value") or row.get("bucket") or ""),
    )


def is_positive(row: dict[str, Any]) -> bool:
    profit_factor = safe_float(row.get("profit_factor"))
    mean_return = safe_float(row.get("mean_return"))
    return profit_factor is not None and mean_return is not None and profit_factor > 1 and mean_return > 0


def less_bad_than_baseline(row: dict[str, Any]) -> str:
    values = [
        safe_float(row.get("mean_return_vs_baseline")),
        safe_float(row.get("profit_factor_vs_baseline")),
        safe_float(row.get("win_rate_vs_baseline")),
    ]
    if all(value is None for value in values):
        return ""
    return bool_text(any(value is not None and value > 0 for value in values))


def has_normal_trade_counts(gross_row: dict[str, Any], net_row: dict[str, Any]) -> bool:
    return safe_int(gross_row.get("trades_count")) > 0 and safe_int(net_row.get("trades_count")) > 0


def preferred_flags(gross_row: dict[str, Any], net_row: dict[str, Any]) -> tuple[str, str, str, str]:
    gross_source = normalize_source(gross_row.get("scenario_source"))
    net_source = normalize_source(net_row.get("scenario_source"))
    scenario_source = preferred_source(net_source, gross_source)
    feature_in_shortlist = (
        bool_from_text(net_row.get("feature_in_shortlist"))
        or bool_from_text(gross_row.get("feature_in_shortlist"))
        or scenario_source == "preferred_shortlist_feature"
    )
    is_preferred_shortlist_feature = (
        bool_from_text(net_row.get("is_preferred_shortlist_feature"))
        or bool_from_text(gross_row.get("is_preferred_shortlist_feature"))
        or scenario_source == "preferred_shortlist_feature"
    )
    if scenario_source == "unknown" and (feature_in_shortlist or is_preferred_shortlist_feature):
        scenario_source = "preferred_shortlist_feature"
    note = ""
    if gross_source != net_source and {gross_source, net_source} != {"unknown"}:
        note = f"source tag resolved from gross={gross_source}, net={net_source}"
    return scenario_source, bool_text(is_preferred_shortlist_feature), bool_text(feature_in_shortlist), note


def build_comparison_rows(gross_rows: list[dict[str, str]], net_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    gross_by_key = {row_key(row): row for row in gross_rows}
    rows: list[dict[str, object]] = []
    for net_row in net_rows:
        gross_row = gross_by_key.get(row_key(net_row))
        if gross_row is None:
            continue
        if not has_normal_trade_counts(gross_row, net_row):
            continue
        gross_positive = is_positive(gross_row)
        net_positive = is_positive(net_row)
        scenario_source, is_preferred_shortlist_feature, feature_in_shortlist, metadata_note = preferred_flags(
            gross_row,
            net_row,
        )
        feature_family = first_nonempty(net_row.get("feature_family"), gross_row.get("feature_family"), "unknown")
        notes = "matched gross/none and estimated/net preferred feature rows"
        if metadata_note:
            notes = f"{notes}; {metadata_note}"
        rows.append(
            {
                "symbol": net_row.get("symbol", ""),
                "direction": net_row.get("direction", ""),
                "feature": net_row.get("feature", ""),
                "feature_family": feature_family,
                "scenario": net_row.get("scenario") or net_row.get("scenario_condition_tested", ""),
                "scenario_source": scenario_source,
                "is_preferred_shortlist_feature": is_preferred_shortlist_feature,
                "feature_in_shortlist": feature_in_shortlist,
                "condition_type": net_row.get("condition_type", ""),
                "condition_value": net_row.get("condition_value") or net_row.get("bucket", ""),
                "gross_trades_count": safe_int(gross_row.get("trades_count")),
                "gross_mean_return": gross_row.get("mean_return", ""),
                "gross_profit_factor": gross_row.get("profit_factor", ""),
                "gross_win_rate": gross_row.get("win_rate", ""),
                "gross_max_drawdown": gross_row.get("max_drawdown", ""),
                "net_trades_count": safe_int(net_row.get("trades_count")),
                "net_mean_return": net_row.get("mean_return", ""),
                "net_profit_factor": net_row.get("profit_factor", ""),
                "net_win_rate": net_row.get("win_rate", ""),
                "net_max_drawdown": net_row.get("max_drawdown", ""),
                "estimated_cost_drag_mean_return": metric_delta(gross_row.get("mean_return"), net_row.get("mean_return")),
                "profit_factor_drop": metric_delta(gross_row.get("profit_factor"), net_row.get("profit_factor")),
                "gross_positive": bool_text(gross_positive),
                "net_positive": bool_text(net_positive),
                "cost_erased_edge": bool_text(gross_positive and not net_positive),
                "less_bad_than_baseline_net": less_bad_than_baseline(net_row),
                "notes": notes,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            str(row["cost_erased_edge"]) != "true",
            str(row["net_positive"]) != "true",
            str(row["symbol"]),
            str(row["feature"]),
            str(row["scenario"]),
        ),
    )


def markdown_lines(rows: list[dict[str, object]], predicate, limit: int = 20) -> list[str]:
    selected = [row for row in rows if predicate(row)]
    if not selected:
        return ["- None."]
    return [
        "- {symbol} `{feature}` `{scenario}`: gross_pf={gross_pf}, net_pf={net_pf}, drag={drag}".format(
            symbol=row.get("symbol", ""),
            feature=row.get("feature", ""),
            scenario=row.get("scenario", ""),
            gross_pf=row.get("gross_profit_factor", ""),
            net_pf=row.get("net_profit_factor", ""),
            drag=row.get("estimated_cost_drag_mean_return", ""),
        )
        for row in selected[:limit]
    ]


def count_lines(counter: Counter[str]) -> list[str]:
    if not counter:
        return ["- None."]
    return [f"- `{key}`: {count}" for key, count in sorted(counter.items())]


def source_tag_diagnostic_lines(rows: list[dict[str, object]]) -> list[str]:
    scenario_counts = Counter(str(row.get("scenario_source") or "unknown") for row in rows)
    shortlist_counts = Counter(str(row.get("feature_in_shortlist") or "false") for row in rows)
    preferred_counts = Counter(str(row.get("is_preferred_shortlist_feature") or "false") for row in rows)
    gross_positive_by_source = Counter(
        str(row.get("scenario_source") or "unknown") for row in rows if row.get("gross_positive") == "true"
    )
    gross_positive_preferred = sum(
        1
        for row in rows
        if row.get("gross_positive") == "true" and row.get("scenario_source") == "preferred_shortlist_feature"
    )
    return [
        f"- Total comparison rows: {len(rows)}",
        "",
        "### scenario_source counts",
        *count_lines(scenario_counts),
        "",
        "### feature_in_shortlist counts",
        *count_lines(shortlist_counts),
        "",
        "### is_preferred_shortlist_feature counts",
        *count_lines(preferred_counts),
        "",
        "### gross_positive count by scenario_source",
        *count_lines(gross_positive_by_source),
        "",
        f"- gross_positive + preferred_shortlist_feature count: {gross_positive_preferred}",
    ]


def skipped_lines(reports_root: Path, gross_run_id: str, net_run_id: str, direction: str, limit: int = 20) -> list[str]:
    lines: list[str] = []
    for label, run_id in (("gross", gross_run_id), ("net", net_run_id)):
        path = skipped_path(reports_root, run_id, direction)
        if not path.exists():
            continue
        for row in read_csv_rows(path)[:limit]:
            lines.append(
                "- {label} {symbol} `{feature}` `{scenario}`: {reason}".format(
                    label=label,
                    symbol=row.get("symbol", ""),
                    feature=row.get("feature", ""),
                    scenario=row.get("scenario") or row.get("scenario_condition_tested", ""),
                    reason=row.get("skip_reason", ""),
                )
            )
    return lines or ["- None."]


def write_report(
    path: Path,
    *,
    rows: list[dict[str, object]],
    reports_root: Path,
    gross_run_id: str,
    net_run_id: str,
    direction: str,
    warnings: list[str],
) -> None:
    lines = [
        "# Preferred Feature Cost Mode Comparison",
        "",
        "This report is research-only. Gross/none rows are diagnostic context; estimated/net rows are required for serious evaluation.",
        "",
        f"- Gross run ID: `{gross_run_id}`",
        f"- Net run ID: `{net_run_id}`",
        f"- Direction: `{direction}`",
        "",
        "## Source Tag Diagnostics",
        "",
        *source_tag_diagnostic_lines(rows),
        "",
        "## Gross Edge Candidates",
        "",
        *markdown_lines(rows, lambda row: row.get("gross_positive") == "true"),
        "",
        "## Cost-Erased Candidates",
        "",
        *markdown_lines(rows, lambda row: row.get("cost_erased_edge") == "true"),
        "",
        "## Net Survivors",
        "",
        *markdown_lines(rows, lambda row: row.get("net_positive") == "true"),
        "",
        "## Less Bad Than Baseline",
        "",
        *markdown_lines(rows, lambda row: row.get("less_bad_than_baseline_net") == "true"),
        "",
        "## Skipped / Untestable Features",
        "",
        *skipped_lines(reports_root, gross_run_id, net_run_id, direction),
        "",
        "## Scenario Source Warning",
        "",
        "- `preferred_shortlist_feature` rows come from the preferred feature shortlist.",
        "- Other scenario sources come from standard/default backtest context and should be interpreted separately.",
        "- A gross edge erased by estimated costs is not a net survivor.",
        "",
    ]
    if warnings:
        lines.extend(
            [
                "## Metadata Warnings",
                "",
                *[f"- {warning}" for warning in warnings],
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def compare_direction(
    *,
    reports_root: Path,
    output_root: Path,
    gross_run_id: str,
    net_run_id: str,
    direction: str,
) -> dict[str, Path]:
    normalized_direction = normalize_direction(direction)
    gross_path = summary_path(reports_root, gross_run_id, normalized_direction)
    net_path = summary_path(reports_root, net_run_id, normalized_direction)
    if not gross_path.exists():
        raise FileNotFoundError(f"Gross summary not found: {gross_path}")
    if not net_path.exists():
        raise FileNotFoundError(f"Net summary not found: {net_path}")
    gross_rows, gross_fieldnames = read_csv_rows_and_fieldnames(gross_path)
    net_rows, net_fieldnames = read_csv_rows_and_fieldnames(net_path)
    warnings = [
        *metadata_warnings(rows=gross_rows, fieldnames=gross_fieldnames, label="gross"),
        *metadata_warnings(rows=net_rows, fieldnames=net_fieldnames, label="net"),
    ]
    rows = build_comparison_rows(gross_rows, net_rows)
    out_dir = output_dir(output_root, gross_run_id, net_run_id, normalized_direction)
    csv_path = out_dir / OUTPUT_CSV
    report_path = out_dir / OUTPUT_REPORT
    write_csv(csv_path, rows, FIELDNAMES)
    write_report(
        report_path,
        rows=rows,
        reports_root=reports_root,
        gross_run_id=gross_run_id,
        net_run_id=net_run_id,
        direction=normalized_direction,
        warnings=warnings,
    )
    return {"cost_mode_comparison_csv": csv_path, "cost_mode_comparison_report": report_path}


def compare_cost_modes(args: argparse.Namespace) -> dict[str, dict[str, Path]]:
    outputs: dict[str, dict[str, Path]] = {}
    for direction in args.directions:
        normalized = normalize_direction(direction)
        outputs[normalized] = compare_direction(
            reports_root=Path(args.reports_root),
            output_root=Path(args.output_root),
            gross_run_id=str(args.gross_run_id),
            net_run_id=str(args.net_run_id),
            direction=normalized,
        )
    return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare research-only preferred feature backtests across gross/none and estimated/net runs."
    )
    parser.add_argument("--gross-run-id", required=True)
    parser.add_argument("--net-run-id", required=True)
    parser.add_argument("--directions", nargs="+", choices=DEFAULT_DIRECTIONS, default=list(DEFAULT_DIRECTIONS))
    parser.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT, help=f"Default: {DEFAULT_REPORTS_ROOT}")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=f"Default: {DEFAULT_OUTPUT_ROOT}")
    return parser.parse_args(argv)


def main() -> int:
    try:
        outputs = compare_cost_modes(parse_args())
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Preferred feature cost-mode comparison failed: {exc}")
        return 1
    print("Preferred feature cost-mode comparison complete.")
    for direction, paths in outputs.items():
        print(f"Direction: {direction}")
        for label, path in paths.items():
            print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
