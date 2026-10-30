"""Build paired attribution between two fixed-candidate exit policies.

This script reads a previously generated offline exit-policy comparison report
and joins trades entry-by-entry. It does not import MT5, connect to a broker,
construct broker requests, mutate strategy specs, or touch execution code.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_REPORT_DIR = (
    BASE_DIR
    / "reports"
    / "exit_policy_comparison"
    / "gbpusd_exit_policy_comparison_20260706_215309"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "exit_policy_attribution"

DEFAULT_CURRENT_POLICY = "current_10_bars"
DEFAULT_COMPARISON_POLICY = "max_holding_30"
DEFAULT_COMPARISON_LABEL = "max30"
BAR_HOURS = 0.25
EPSILON = 1e-9

TRADES_FILE = "exit_policy_trades.csv"
SUMMARY_FILE = "exit_policy_summary.csv"
BY_MONTH_FILE = "exit_policy_by_month.csv"
WALK_FORWARD_FILE = "exit_policy_walk_forward_blocks.csv"

PAIRED_FILE = "paired_trade_attribution.csv"
ATTRIBUTION_SUMMARY_FILE = "paired_trade_attribution_summary.csv"
ATTRIBUTION_BY_MONTH_FILE = "paired_trade_attribution_by_month.csv"
ATTRIBUTION_BY_QUARTER_FILE = "paired_trade_attribution_by_quarter.csv"
ATTRIBUTION_BY_YEAR_FILE = "paired_trade_attribution_by_year.csv"
ATTRIBUTION_MANIFEST_FILE = "paired_trade_attribution_manifest.json"

STATUS_AVAILABLE = "exit_policy_paired_attribution_available"
STATUS_OUTPUT_EXISTS = "exit_policy_paired_attribution_blocked_output_exists_without_overwrite"

CATEGORY_ORDER = [
    "same_result",
    "current_time_exit_then_max30_tp",
    "current_time_exit_then_max30_sl",
    "current_time_exit_then_max30_better_non_tp",
    "current_time_exit_then_max30_worse_non_sl",
    "current_better",
    "max30_better",
    "same_exit_reason_different_timing",
    "friday_interaction",
]

CATEGORY_COUNT_FIELDS = [
    "count_same_result",
    "count_current_time_exit_then_max30_tp",
    "count_current_time_exit_then_max30_sl",
    "count_current_time_exit_then_max30_better_non_tp",
    "count_current_time_exit_then_max30_worse_non_sl",
    "count_same_exit_reason_different_timing",
    "count_friday_interaction",
]

PAIRED_FIELDS = [
    "run_id",
    "source_run_id",
    "pair_index",
    "pair_key",
    "raw_signal_index",
    "signal_id",
    "entry_time",
    "entry_price",
    "sl_price",
    "tp_price",
    "current_exit_time",
    "current_exit_reason",
    "current_R",
    "current_pips",
    "current_holding_bars",
    "max30_exit_time",
    "max30_exit_reason",
    "max30_R",
    "max30_pips",
    "max30_holding_bars",
    "delta_R",
    "delta_pips",
    "delta_holding_bars",
    "extra_exposure_hours",
    "month",
    "quarter",
    "year",
    "walk_forward_block",
    "category",
    "current_missed_tp_after_time_exit",
    "current_would_have_hit_tp_after_time_exit",
    "current_would_have_hit_sl_after_time_exit",
    "max30_missed_tp_after_time_exit",
    "max30_would_have_hit_tp_after_time_exit",
    "max30_would_have_hit_sl_after_time_exit",
]

SUMMARY_FIELDS = [
    "run_id",
    "source_run_id",
    "scope",
    "period",
    "category",
    "trade_count",
    "sum_delta_R",
    "avg_delta_R",
    "median_delta_R",
    "max_positive_delta_R",
    "max_negative_delta_R",
    "count_max30_better",
    "count_current_better",
    "count_same_result",
    "count_current_time_exit_then_max30_tp",
    "count_current_time_exit_then_max30_sl",
    "count_current_time_exit_then_max30_better_non_tp",
    "count_current_time_exit_then_max30_worse_non_sl",
    "count_same_exit_reason_different_timing",
    "count_friday_interaction",
    "sum_delta_R_by_category",
    "avg_delta_R_by_category",
    "extra_exposure_hours",
    "delta_R_per_extra_exposure_hour",
]

NO_EXECUTION_EVIDENCE = {
    "no_mt5_import_performed": True,
    "no_mt5_connection_performed": True,
    "no_broker_api_query_performed": True,
    "no_order_check_called": True,
    "no_order_send_called": True,
    "no_order_execution_performed": True,
    "no_broker_payload_constructed": True,
    "strategy_spec_not_modified": True,
    "demo_live_config_not_modified": True,
    "ea_not_modified": True,
}


class AttributionError(RuntimeError):
    """Raised when the source report cannot support paired attribution."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build paired trade attribution between current_10_bars and max_holding_30.",
    )
    parser.add_argument(
        "--source-report-dir",
        type=Path,
        default=DEFAULT_SOURCE_REPORT_DIR,
        help="Directory containing exit_policy_*.csv files from the comparison run.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root directory for attribution reports.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Explicit output directory. Overrides --output-root/--run-id.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run id for the attribution report. Defaults to a timestamped id.",
    )
    parser.add_argument(
        "--current-policy",
        default=DEFAULT_CURRENT_POLICY,
        help="Baseline policy id to pair from the source trades CSV.",
    )
    parser.add_argument(
        "--comparison-policy",
        default=DEFAULT_COMPARISON_POLICY,
        help="Comparison policy id to pair from the source trades CSV.",
    )
    parser.add_argument(
        "--comparison-label",
        default=DEFAULT_COMPARISON_LABEL,
        help="Short label used in paired output column names for the comparison policy.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing attribution output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except FileExistsError as exc:
        print(f"{STATUS_OUTPUT_EXISTS}: {exc}", file=sys.stderr)
        return 2
    except AttributionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps({key: str(path) for key, path in outputs.items()}, indent=2, sort_keys=True))
    return 0


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    run_id = args.run_id or f"gbpusd_exit_policy_attribution_{datetime.now():%Y%m%d_%H%M%S}"
    output_dir = args.output_dir or args.output_root / run_id
    if output_dir.exists() and not args.overwrite:
        raise FileExistsError(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_report_dir = args.source_report_dir
    trades_path = source_report_dir / TRADES_FILE
    summary_path = source_report_dir / SUMMARY_FILE
    by_month_path = source_report_dir / BY_MONTH_FILE
    walk_forward_path = source_report_dir / WALK_FORWARD_FILE

    trades = _read_csv(trades_path)
    summary_rows = _read_csv(summary_path)
    source_run_id = _source_run_id(summary_rows, trades)

    current_rows = [row for row in trades if row.get("policy_id") == args.current_policy]
    comparison_rows = [row for row in trades if row.get("policy_id") == args.comparison_policy]
    paired_source_rows = pair_trades(current_rows, comparison_rows)
    blocks = load_walk_forward_blocks(walk_forward_path, args.current_policy)
    paired_rows = build_paired_rows(
        paired_source_rows,
        blocks,
        run_id=run_id,
        source_run_id=source_run_id,
        comparison_label=args.comparison_label,
    )

    overall_summary = [build_summary_row(paired_rows, run_id, source_run_id, "overall", "all", "all")]
    category_summaries = [
        build_summary_row(category_rows, run_id, source_run_id, "category", "all", category)
        for category, category_rows in grouped_rows(paired_rows, "category").items()
    ]
    summary_output_rows = overall_summary + sorted(category_summaries, key=lambda row: row["category"])

    by_month_rows = build_period_rows(paired_rows, run_id, source_run_id, "month")
    by_quarter_rows = build_period_rows(paired_rows, run_id, source_run_id, "quarter")
    by_year_rows = build_period_rows(paired_rows, run_id, source_run_id, "year")

    outputs = {
        "paired_trades": output_dir / PAIRED_FILE,
        "summary": output_dir / ATTRIBUTION_SUMMARY_FILE,
        "by_month": output_dir / ATTRIBUTION_BY_MONTH_FILE,
        "by_quarter": output_dir / ATTRIBUTION_BY_QUARTER_FILE,
        "by_year": output_dir / ATTRIBUTION_BY_YEAR_FILE,
        "manifest": output_dir / ATTRIBUTION_MANIFEST_FILE,
    }
    _write_csv(outputs["paired_trades"], PAIRED_FIELDS, paired_rows)
    _write_csv(outputs["summary"], SUMMARY_FIELDS, summary_output_rows)
    _write_csv(outputs["by_month"], SUMMARY_FIELDS, by_month_rows)
    _write_csv(outputs["by_quarter"], SUMMARY_FIELDS, by_quarter_rows)
    _write_csv(outputs["by_year"], SUMMARY_FIELDS, by_year_rows)

    manifest = build_manifest(
        run_id=run_id,
        source_run_id=source_run_id,
        source_report_dir=source_report_dir,
        output_dir=output_dir,
        outputs=outputs,
        current_policy=args.current_policy,
        comparison_policy=args.comparison_policy,
        source_counts={
            args.current_policy: len(current_rows),
            args.comparison_policy: len(comparison_rows),
            "paired": len(paired_rows),
        },
        input_files={
            "trades": trades_path,
            "summary": summary_path,
            "by_month": by_month_path,
            "walk_forward_blocks": walk_forward_path,
        },
    )
    outputs["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return outputs


def pair_trades(
    current_rows: list[dict[str, str]],
    comparison_rows: list[dict[str, str]],
) -> list[tuple[dict[str, str], dict[str, str]]]:
    current_by_key = rows_by_pair_key(current_rows, "current")
    comparison_by_key = rows_by_pair_key(comparison_rows, "comparison")
    current_keys = set(current_by_key)
    comparison_keys = set(comparison_by_key)
    if current_keys != comparison_keys:
        missing_from_comparison = sorted(current_keys - comparison_keys)[:5]
        missing_from_current = sorted(comparison_keys - current_keys)[:5]
        raise AttributionError(
            "Cannot pair policies with different entry keys: "
            f"current_only={missing_from_comparison} comparison_only={missing_from_current}"
        )

    return [
        (current_by_key[key], comparison_by_key[key])
        for key in sorted(current_keys, key=lambda item: (_parse_datetime(item[1]), _parse_int(item[0])))
    ]


def rows_by_pair_key(rows: list[dict[str, str]], label: str) -> dict[tuple[str, str], dict[str, str]]:
    keyed: dict[tuple[str, str], dict[str, str]] = {}
    duplicates: list[tuple[str, str]] = []
    for row in rows:
        key = pair_key(row)
        if key in keyed:
            duplicates.append(key)
        keyed[key] = row
    if duplicates:
        raise AttributionError(f"Duplicate {label} pair keys found: {duplicates[:5]}")
    return keyed


def pair_key(row: dict[str, str]) -> tuple[str, str]:
    raw_signal_index = row.get("raw_signal_index", "")
    entry_time = row.get("entry_time_server", "")
    if not raw_signal_index or not entry_time:
        raise AttributionError("Trades CSV must contain raw_signal_index and entry_time_server for paired attribution")
    return raw_signal_index, entry_time


def build_paired_rows(
    paired_source_rows: list[tuple[dict[str, str], dict[str, str]]],
    blocks: list[dict[str, Any]],
    *,
    run_id: str,
    source_run_id: str,
    comparison_label: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pair_index, (current, comparison) in enumerate(paired_source_rows, start=1):
        entry_dt = _parse_datetime(current["entry_time_server"])
        current_r = _parse_float(current["R_multiple"])
        comparison_r = _parse_float(comparison["R_multiple"])
        current_pips = _parse_float(current["pips"])
        comparison_pips = _parse_float(comparison["pips"])
        current_holding = _parse_int(current["holding_bars"])
        comparison_holding = _parse_int(comparison["holding_bars"])
        delta_r = comparison_r - current_r
        delta_pips = comparison_pips - current_pips
        delta_holding = comparison_holding - current_holding
        category = classify_pair(current, comparison, delta_r, delta_holding)
        key = pair_key(current)
        rows.append(
            {
                "run_id": run_id,
                "source_run_id": source_run_id,
                "pair_index": pair_index,
                "pair_key": f"{key[0]}|{key[1]}",
                "raw_signal_index": current.get("raw_signal_index", ""),
                "signal_id": current.get("signal_id", ""),
                "entry_time": current.get("entry_time_server", ""),
                "entry_price": current.get("entry_price", ""),
                "sl_price": current.get("sl_price", ""),
                "tp_price": current.get("tp_price", ""),
                "current_exit_time": current.get("exit_time_server", ""),
                "current_exit_reason": current.get("exit_reason", ""),
                "current_R": current_r,
                "current_pips": current_pips,
                "current_holding_bars": current_holding,
                f"{comparison_label}_exit_time": comparison.get("exit_time_server", ""),
                f"{comparison_label}_exit_reason": comparison.get("exit_reason", ""),
                f"{comparison_label}_R": comparison_r,
                f"{comparison_label}_pips": comparison_pips,
                f"{comparison_label}_holding_bars": comparison_holding,
                "delta_R": delta_r,
                "delta_pips": delta_pips,
                "delta_holding_bars": delta_holding,
                "extra_exposure_hours": delta_holding * BAR_HOURS,
                "month": entry_dt.strftime("%Y-%m"),
                "quarter": f"{entry_dt.year}-Q{((entry_dt.month - 1) // 3) + 1}",
                "year": str(entry_dt.year),
                "walk_forward_block": find_walk_forward_block(entry_dt, blocks),
                "category": category,
                "current_missed_tp_after_time_exit": current.get("missed_tp_after_time_exit", ""),
                "current_would_have_hit_tp_after_time_exit": current.get(
                    "would_have_hit_tp_after_time_exit", ""
                ),
                "current_would_have_hit_sl_after_time_exit": current.get(
                    "would_have_hit_sl_after_time_exit", ""
                ),
                f"{comparison_label}_missed_tp_after_time_exit": comparison.get(
                    "missed_tp_after_time_exit", ""
                ),
                f"{comparison_label}_would_have_hit_tp_after_time_exit": comparison.get(
                    "would_have_hit_tp_after_time_exit", ""
                ),
                f"{comparison_label}_would_have_hit_sl_after_time_exit": comparison.get(
                    "would_have_hit_sl_after_time_exit", ""
                ),
            }
        )
    return rows


def classify_pair(
    current: dict[str, str],
    comparison: dict[str, str],
    delta_r: float,
    delta_holding: int,
) -> str:
    current_reason = current.get("exit_reason", "")
    comparison_reason = comparison.get("exit_reason", "")
    same_exit_time = current.get("exit_time_server") == comparison.get("exit_time_server")
    same_reason = current_reason == comparison_reason
    if same_reason and same_exit_time and abs(delta_r) <= EPSILON and delta_holding == 0:
        return "same_result"
    if current_reason == "time_exit" and comparison_reason == "tp":
        return "current_time_exit_then_max30_tp"
    if current_reason == "time_exit" and comparison_reason == "sl":
        return "current_time_exit_then_max30_sl"
    if "friday_forced_flat" in {current_reason, comparison_reason}:
        return "friday_interaction"
    if current_reason == "time_exit" and delta_r > EPSILON:
        return "current_time_exit_then_max30_better_non_tp"
    if current_reason == "time_exit" and delta_r < -EPSILON:
        return "current_time_exit_then_max30_worse_non_sl"
    if same_reason:
        return "same_exit_reason_different_timing"
    if delta_r > EPSILON:
        return "max30_better"
    if delta_r < -EPSILON:
        return "current_better"
    return "same_result"


def build_period_rows(
    rows: list[dict[str, Any]],
    run_id: str,
    source_run_id: str,
    period_field: str,
) -> list[dict[str, Any]]:
    return [
        build_summary_row(period_rows, run_id, source_run_id, period_field, period, "all")
        for period, period_rows in sorted(grouped_rows(rows, period_field).items())
    ]


def build_summary_row(
    rows: list[dict[str, Any]],
    run_id: str,
    source_run_id: str,
    scope: str,
    period: str,
    category: str,
) -> dict[str, Any]:
    deltas = [_parse_float_value(row["delta_R"]) for row in rows]
    category_counts = Counter(str(row["category"]) for row in rows)
    extra_exposure_hours = sum(_parse_float_value(row["extra_exposure_hours"]) for row in rows)
    sum_delta = sum(deltas)
    positive_deltas = [delta for delta in deltas if delta > EPSILON]
    negative_deltas = [delta for delta in deltas if delta < -EPSILON]
    row: dict[str, Any] = {
        "run_id": run_id,
        "source_run_id": source_run_id,
        "scope": scope,
        "period": period,
        "category": category,
        "trade_count": len(rows),
        "sum_delta_R": sum_delta,
        "avg_delta_R": _safe_mean(deltas),
        "median_delta_R": statistics.median(deltas) if deltas else 0.0,
        "max_positive_delta_R": max(positive_deltas) if positive_deltas else 0.0,
        "max_negative_delta_R": min(negative_deltas) if negative_deltas else 0.0,
        "count_max30_better": sum(1 for delta in deltas if delta > EPSILON),
        "count_current_better": sum(1 for delta in deltas if delta < -EPSILON),
        "sum_delta_R_by_category": format_category_metric(rows, "sum"),
        "avg_delta_R_by_category": format_category_metric(rows, "avg"),
        "extra_exposure_hours": extra_exposure_hours,
        "delta_R_per_extra_exposure_hour": (
            sum_delta / extra_exposure_hours if abs(extra_exposure_hours) > EPSILON else 0.0
        ),
    }
    for count_field in CATEGORY_COUNT_FIELDS:
        category_name = count_field.removeprefix("count_")
        row[count_field] = category_counts[category_name]
    return row


def format_category_metric(rows: list[dict[str, Any]], metric: str) -> str:
    by_category = grouped_rows(rows, "category")
    chunks: list[str] = []
    for category in CATEGORY_ORDER:
        category_rows = by_category.get(category, [])
        if not category_rows:
            continue
        deltas = [_parse_float_value(row["delta_R"]) for row in category_rows]
        value = sum(deltas) if metric == "sum" else _safe_mean(deltas)
        chunks.append(f"{category}={_format_float(value)}")
    return ";".join(chunks)


def grouped_rows(rows: list[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[field])].append(row)
    return dict(grouped)


def load_walk_forward_blocks(path: Path, policy_id: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    blocks: list[dict[str, Any]] = []
    for row in _read_csv(path):
        if row.get("policy_id") != policy_id:
            continue
        blocks.append(
            {
                "period": row["period"],
                "period_start": _parse_datetime(row["period_start"]),
                "period_end": _parse_datetime(row["period_end"]),
            }
        )
    return blocks


def find_walk_forward_block(entry_dt: datetime, blocks: list[dict[str, Any]]) -> str:
    for block in blocks:
        if block["period_start"] <= entry_dt <= block["period_end"]:
            return str(block["period"])
    return "unmapped"


def build_manifest(
    *,
    run_id: str,
    source_run_id: str,
    source_report_dir: Path,
    output_dir: Path,
    outputs: dict[str, Path],
    current_policy: str,
    comparison_policy: str,
    source_counts: dict[str, int],
    input_files: dict[str, Path],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "source_run_id": source_run_id,
        "comparison_status": STATUS_AVAILABLE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_report_dir": str(source_report_dir),
        "output_dir": str(output_dir),
        "current_policy": current_policy,
        "comparison_policy": comparison_policy,
        "pair_key": ["raw_signal_index", "entry_time_server"],
        "bar_hours_assumption": BAR_HOURS,
        "source_counts": source_counts,
        "input_files": {key: str(path) for key, path in input_files.items()},
        "output_files": {key: str(path) for key, path in outputs.items()},
        "no_execution_evidence": NO_EXECUTION_EVIDENCE,
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise AttributionError(f"Missing required source file: {path}")
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format_cell(row.get(field, "")) for field in fieldnames})


def _source_run_id(summary_rows: list[dict[str, str]], trades: list[dict[str, str]]) -> str:
    for rows in (summary_rows, trades):
        if rows and rows[0].get("run_id"):
            return rows[0]["run_id"]
    return ""


def _parse_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise AttributionError(f"Unsupported datetime value: {value!r}")


def _parse_float(value: str) -> float:
    if value == "":
        raise AttributionError("Missing numeric value in source report")
    return float(value)


def _parse_float_value(value: Any) -> float:
    if value in ("", None):
        return 0.0
    return float(value)


def _parse_int(value: str) -> int:
    if value == "":
        return 0
    return int(float(value))


def _safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _format_cell(value: Any) -> Any:
    if isinstance(value, float):
        return _format_float(value)
    return value


def _format_float(value: float) -> str:
    if abs(value) < EPSILON:
        value = 0.0
    return f"{value:.10f}".rstrip("0").rstrip(".")


if __name__ == "__main__":
    raise SystemExit(main())

