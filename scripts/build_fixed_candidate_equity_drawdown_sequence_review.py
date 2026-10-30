"""Build an artifact-only equity/drawdown sequence review.

This module reads existing equity curves and trade logs for the exact-rule and
single-filter A artifacts, then writes neutral descriptive sequence summaries.
It does not run validation, backtests, timeout review, diagnostics, candidate
audit, model work, database work, or external actions.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_equity_drawdown_sequence_review"
DEFAULT_EXACT_STRESS_DIR = (
    BASE_DIR
    / "reports"
    / "regime_candidate_stress"
    / "gbpusd_short_h10_1_5_off_hours_stress_exec_v2"
)
DEFAULT_R_MULTIPLE_ROOT = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_r_multiple_row_specs"
    / "gbpusd_short_h10_1_5_off_hours_baseline_r_multiple_row_specs_v1"
    / "manual_r_multiple_outputs"
)
DEFAULT_SINGLE_FILTER_A_STRESS_DIR = (
    DEFAULT_R_MULTIPLE_ROOT
    / "gbpusd_short_h10_1_5_off_hours_baseline_r_multiple_row_specs_v1_single_filter_a"
)
DEFAULT_TIMEOUT_ARTIFACT_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_timeout_policy_artifact_review"
    / "gbpusd_short_h10_1_5_off_hours_timeout_policy_artifact_review_v1"
)
DEFAULT_WALKFORWARD_DRAWDOWN_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_walkforward_drawdown_artifact_review"
    / "gbpusd_short_h10_1_5_off_hours_walkforward_drawdown_artifact_review_v1"
)
DEFAULT_COMPARISON_TABLE_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_comparison_table"
    / "gbpusd_short_h10_1_5_off_hours_baseline_comparison_table_v3"
)
DEFAULT_R_MULTIPLE_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_r_multiple_baseline_review"
    / "gbpusd_short_h10_1_5_off_hours_r_multiple_baseline_review_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_equity_drawdown_sequence_review"

SUMMARY_FILE = "candidate_stress_summary.csv"
EQUITY_BASE_FILE = "equity_curve_base.csv"
EQUITY_STRESS_FILE = "equity_curve_stress.csv"
TRADE_BASE_FILE = "trade_log_base.csv"
TRADE_STRESS_FILE = "trade_log_stress.csv"
REPORT_FILE = "candidate_stress_report.md"

OUTPUT_CSV = "fixed_candidate_equity_drawdown_sequence_review.csv"
OUTPUT_REPORT = "fixed_candidate_equity_drawdown_sequence_review_report.md"
OUTPUT_WARNINGS = "fixed_candidate_equity_drawdown_sequence_review_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_equity_drawdown_sequence_review_manifest.json"

EQUITY_COLUMNS = {
    "cumulative_R",
    "equity_R",
    "cumulative_net_R",
    "drawdown_R",
    "drawdown",
    "trade_index",
    "entry_time",
    "exit_time",
}
TRADE_COLUMNS = {"net_R", "R", "exit_reason", "bars_held", "entry_time", "exit_time"}

FIELDNAMES = [
    "run_id",
    "review_scope",
    "cost_profile",
    "row_type",
    "source_label",
    "artifact_status",
    "source_equity_curve",
    "source_trade_log",
    "trade_count",
    "equity_row_count",
    "metric_namespace",
    "metric_unit",
    "max_drawdown_R",
    "max_drawdown_start_index",
    "max_drawdown_end_index",
    "max_drawdown_duration_trades",
    "worst_10_trade_sum_net_R",
    "worst_20_trade_sum_net_R",
    "worst_50_trade_sum_net_R",
    "longest_negative_trade_streak",
    "average_negative_trade_streak_length",
    "largest_single_trade_loss_R",
    "top_5_loss_sum_R",
    "top_10_loss_sum_R",
    "loss_cluster_count",
    "exact_max_drawdown_R",
    "single_filter_a_max_drawdown_R",
    "drawdown_delta",
    "exact_max_drawdown_duration_trades",
    "single_filter_a_max_drawdown_duration_trades",
    "drawdown_duration_delta",
    "exact_worst_20_trade_sum_net_R",
    "single_filter_a_worst_20_trade_sum_net_R",
    "worst_20_trade_sum_delta",
    "exact_longest_negative_trade_streak",
    "single_filter_a_longest_negative_trade_streak",
    "longest_negative_streak_delta",
    "readiness_status",
    "descriptive_observation",
    "caveat",
    "required_next_artifact",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "review_scope",
    "source_path",
    "blocking_warning",
]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def caveats(*values: str) -> str:
    return ";".join(value for value in values if value)


def join_values(values: set[str] | list[str] | tuple[str, ...]) -> str:
    return ";".join(value for value in sorted(values) if value)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_csv_fieldnames(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "review": output_dir / OUTPUT_CSV,
        "report": output_dir / OUTPUT_REPORT,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "manifest": output_dir / OUTPUT_MANIFEST,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def safe_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def int_text(value: float | int | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def mean_text(values: list[float]) -> str:
    if not values:
        return ""
    return str(sum(values) / len(values))


def sum_text(values: list[float]) -> str:
    if not values:
        return ""
    return str(sum(values))


def delta_text(left: object, right: object) -> str:
    left_value = safe_float(left)
    right_value = safe_float(right)
    if left_value is None or right_value is None:
        return ""
    return str(left_value - right_value)


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    warning_code: str,
    message: str,
    review_scope: str,
    source_path: Path | str,
    blocking: bool = False,
    severity: str = "warning",
) -> None:
    warnings.append(
        {
            "warning_code": warning_code,
            "severity": "error" if blocking else severity,
            "message": message,
            "review_scope": review_scope,
            "source_path": source_path,
            "blocking_warning": blocking,
        }
    )


def numeric_series(rows: list[dict[str, str]], preferred_columns: tuple[str, ...]) -> tuple[list[float], str]:
    for column in preferred_columns:
        values = [safe_float(row.get(column)) for row in rows]
        numeric = [value for value in values if value is not None]
        if numeric:
            return numeric, column
    return [], ""


def rolling_worst_sum(values: list[float], window: int) -> str:
    if len(values) < window:
        return ""
    return str(min(sum(values[index : index + window]) for index in range(0, len(values) - window + 1)))


def negative_streaks(values: list[float]) -> list[int]:
    streaks: list[int] = []
    current = 0
    for value in values:
        if value < 0:
            current += 1
        elif current:
            streaks.append(current)
            current = 0
    if current:
        streaks.append(current)
    return streaks


def top_loss_sum(values: list[float], count: int) -> str:
    losses = sorted(value for value in values if value < 0)
    if not losses:
        return ""
    return str(sum(losses[:count]))


def drawdown_from_equity(rows: list[dict[str, str]]) -> dict[str, str]:
    drawdowns, drawdown_column = numeric_series(rows, ("drawdown_R", "drawdown"))
    if drawdowns:
        max_drawdown = max(drawdowns)
        end_position = drawdowns.index(max_drawdown)
        start_position = end_position
        while start_position > 0 and drawdowns[start_position - 1] > 0:
            start_position -= 1
        end_index = rows[end_position].get("trade_index") or str(end_position + 1)
        start_index = rows[start_position].get("trade_index") or str(start_position + 1)
        duration = end_position - start_position + 1
        return {
            "max_drawdown_R": str(max_drawdown),
            "max_drawdown_start_index": start_index,
            "max_drawdown_end_index": end_index,
            "max_drawdown_duration_trades": str(duration),
            "drawdown_source_column": drawdown_column,
        }

    equity_values, equity_column = numeric_series(rows, ("cumulative_R", "equity_R", "cumulative_net_R"))
    if not equity_values:
        return {
            "max_drawdown_R": "",
            "max_drawdown_start_index": "",
            "max_drawdown_end_index": "",
            "max_drawdown_duration_trades": "",
            "drawdown_source_column": "",
        }
    peak_value = equity_values[0]
    peak_index = 0
    max_drawdown = 0.0
    start_index = 0
    end_index = 0
    for index, value in enumerate(equity_values):
        if value > peak_value:
            peak_value = value
            peak_index = index
        drawdown = peak_value - value
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            start_index = peak_index
            end_index = index
    return {
        "max_drawdown_R": str(max_drawdown),
        "max_drawdown_start_index": rows[start_index].get("trade_index") or str(start_index + 1),
        "max_drawdown_end_index": rows[end_index].get("trade_index") or str(end_index + 1),
        "max_drawdown_duration_trades": str(end_index - start_index + 1),
        "drawdown_source_column": equity_column,
    }


def artifact(source_dir: Path, source_label: str, cost_profile: str) -> dict[str, Any]:
    equity_file = EQUITY_BASE_FILE if cost_profile == "p75" else EQUITY_STRESS_FILE
    trade_file = TRADE_BASE_FILE if cost_profile == "p75" else TRADE_STRESS_FILE
    equity_path = source_dir / equity_file
    trade_path = source_dir / trade_file
    return {
        "source_dir": source_dir,
        "source_label": source_label,
        "cost_profile": cost_profile,
        "equity_path": equity_path,
        "trade_path": trade_path,
        "summary_path": source_dir / SUMMARY_FILE,
        "equity_exists": equity_path.exists(),
        "trade_exists": trade_path.exists(),
        "equity_rows": read_csv_rows(equity_path),
        "trade_rows": read_csv_rows(trade_path),
        "equity_columns": read_csv_fieldnames(equity_path),
        "trade_columns": read_csv_fieldnames(trade_path),
    }


def sequence_metrics(item: dict[str, Any]) -> dict[str, Any]:
    trade_values, trade_source_column = numeric_series(item["trade_rows"], ("net_R", "R"))
    drawdown = drawdown_from_equity(item["equity_rows"])
    streaks = negative_streaks(trade_values)
    largest_loss = min(trade_values) if trade_values else None
    return {
        "trade_count": len(item["trade_rows"]),
        "equity_row_count": len(item["equity_rows"]),
        "metric_namespace": "R_multiple",
        "metric_unit": "R",
        "max_drawdown_R": drawdown["max_drawdown_R"],
        "max_drawdown_start_index": drawdown["max_drawdown_start_index"],
        "max_drawdown_end_index": drawdown["max_drawdown_end_index"],
        "max_drawdown_duration_trades": drawdown["max_drawdown_duration_trades"],
        "worst_10_trade_sum_net_R": rolling_worst_sum(trade_values, 10),
        "worst_20_trade_sum_net_R": rolling_worst_sum(trade_values, 20),
        "worst_50_trade_sum_net_R": rolling_worst_sum(trade_values, 50),
        "longest_negative_trade_streak": max(streaks) if streaks else 0,
        "average_negative_trade_streak_length": mean_text([float(streak) for streak in streaks]),
        "largest_single_trade_loss_R": "" if largest_loss is None else str(largest_loss),
        "top_5_loss_sum_R": top_loss_sum(trade_values, 5),
        "top_10_loss_sum_R": top_loss_sum(trade_values, 10),
        "loss_cluster_count": len(streaks),
        "trade_source_column": trade_source_column,
        "drawdown_source_column": drawdown["drawdown_source_column"],
    }


def base_row(args: argparse.Namespace, *, review_scope: str, item: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "review_scope": review_scope,
        "cost_profile": item["cost_profile"],
        "row_type": "sequence_summary",
        "source_label": item["source_label"],
        "artifact_status": "available",
        "source_equity_curve": item["equity_path"] if item["equity_exists"] else "",
        "source_trade_log": item["trade_path"] if item["trade_exists"] else "",
        "trade_count": metrics["trade_count"],
        "equity_row_count": metrics["equity_row_count"],
        "metric_namespace": metrics["metric_namespace"],
        "metric_unit": metrics["metric_unit"],
        "max_drawdown_R": metrics["max_drawdown_R"],
        "max_drawdown_start_index": metrics["max_drawdown_start_index"],
        "max_drawdown_end_index": metrics["max_drawdown_end_index"],
        "max_drawdown_duration_trades": metrics["max_drawdown_duration_trades"],
        "worst_10_trade_sum_net_R": metrics["worst_10_trade_sum_net_R"],
        "worst_20_trade_sum_net_R": metrics["worst_20_trade_sum_net_R"],
        "worst_50_trade_sum_net_R": metrics["worst_50_trade_sum_net_R"],
        "longest_negative_trade_streak": metrics["longest_negative_trade_streak"],
        "average_negative_trade_streak_length": metrics["average_negative_trade_streak_length"],
        "largest_single_trade_loss_R": metrics["largest_single_trade_loss_R"],
        "top_5_loss_sum_R": metrics["top_5_loss_sum_R"],
        "top_10_loss_sum_R": metrics["top_10_loss_sum_R"],
        "loss_cluster_count": metrics["loss_cluster_count"],
        "exact_max_drawdown_R": "",
        "single_filter_a_max_drawdown_R": "",
        "drawdown_delta": "",
        "exact_max_drawdown_duration_trades": "",
        "single_filter_a_max_drawdown_duration_trades": "",
        "drawdown_duration_delta": "",
        "exact_worst_20_trade_sum_net_R": "",
        "single_filter_a_worst_20_trade_sum_net_R": "",
        "worst_20_trade_sum_delta": "",
        "exact_longest_negative_trade_streak": "",
        "single_filter_a_longest_negative_trade_streak": "",
        "longest_negative_streak_delta": "",
        "readiness_status": "descriptive_sequence_review_available",
        "descriptive_observation": caveats("equity_curve_columns_detected", "trade_log_columns_detected"),
        "caveat": caveats("descriptive_only_no_decision", "no_path_recomputation_performed"),
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


def sequence_row(
    args: argparse.Namespace,
    *,
    review_scope: str,
    item: dict[str, Any],
    warnings: list[dict[str, Any]],
    optional_equity: bool = True,
) -> dict[str, Any]:
    metrics = sequence_metrics(item)
    row = base_row(args, review_scope=review_scope, item=item, metrics=metrics)
    if not item["trade_exists"]:
        row["artifact_status"] = "missing"
        row["readiness_status"] = "unavailable_missing_artifact"
        row["descriptive_observation"] = "further_drawdown_review_required"
        row["required_next_artifact"] = "trade_log_base_or_trade_log_stress"
        row["warning_code"] = f"{review_scope}_trade_log_missing"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="Required trade log artifact is missing.",
            review_scope=review_scope,
            source_path=item["trade_path"],
        )
        return row
    if not item["equity_exists"]:
        row["artifact_status"] = "available"
        row["readiness_status"] = "descriptive_sequence_review_available_with_caveat"
        row["descriptive_observation"] = caveats("trade_log_columns_detected", "further_drawdown_review_required")
        row["caveat"] = caveats("drawdown_duration_not_derivable", row["caveat"])
        row["required_next_artifact"] = "equity_curve_with_cumulative_or_drawdown_columns"
        row["warning_code"] = f"{review_scope}_equity_curve_missing"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="Equity curve is missing; trade-log sequence metrics were still summarized.",
            review_scope=review_scope,
            source_path=item["equity_path"],
        )
    elif not metrics["max_drawdown_duration_trades"]:
        row["readiness_status"] = "descriptive_sequence_review_available_with_caveat"
        row["caveat"] = caveats("drawdown_duration_not_derivable", row["caveat"])
        row["warning_code"] = f"{review_scope}_drawdown_duration_not_derivable"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="Drawdown duration could not be derived from available equity columns.",
            review_scope=review_scope,
            source_path=item["equity_path"],
        )
    return row


def comparison_row(
    args: argparse.Namespace,
    *,
    review_scope: str,
    exact_row: dict[str, Any],
    single_row: dict[str, Any],
    cost_profile: str,
) -> dict[str, Any]:
    row = {
        field: "" for field in FIELDNAMES
    }
    row.update(
        {
            "run_id": args.run_id,
            "review_scope": review_scope,
            "cost_profile": cost_profile,
            "row_type": "sequence_comparison",
            "source_label": "exact_rule_vs_single_filter_a",
            "artifact_status": "available",
            "source_equity_curve": f"{exact_row.get('source_equity_curve', '')};{single_row.get('source_equity_curve', '')}",
            "source_trade_log": f"{exact_row.get('source_trade_log', '')};{single_row.get('source_trade_log', '')}",
            "metric_namespace": "R_multiple",
            "metric_unit": "R",
            "exact_max_drawdown_R": exact_row.get("max_drawdown_R", ""),
            "single_filter_a_max_drawdown_R": single_row.get("max_drawdown_R", ""),
            "drawdown_delta": delta_text(exact_row.get("max_drawdown_R", ""), single_row.get("max_drawdown_R", "")),
            "exact_max_drawdown_duration_trades": exact_row.get("max_drawdown_duration_trades", ""),
            "single_filter_a_max_drawdown_duration_trades": single_row.get("max_drawdown_duration_trades", ""),
            "drawdown_duration_delta": delta_text(
                exact_row.get("max_drawdown_duration_trades", ""),
                single_row.get("max_drawdown_duration_trades", ""),
            ),
            "exact_worst_20_trade_sum_net_R": exact_row.get("worst_20_trade_sum_net_R", ""),
            "single_filter_a_worst_20_trade_sum_net_R": single_row.get("worst_20_trade_sum_net_R", ""),
            "worst_20_trade_sum_delta": delta_text(
                exact_row.get("worst_20_trade_sum_net_R", ""),
                single_row.get("worst_20_trade_sum_net_R", ""),
            ),
            "exact_longest_negative_trade_streak": exact_row.get("longest_negative_trade_streak", ""),
            "single_filter_a_longest_negative_trade_streak": single_row.get("longest_negative_trade_streak", ""),
            "longest_negative_streak_delta": delta_text(
                exact_row.get("longest_negative_trade_streak", ""),
                single_row.get("longest_negative_trade_streak", ""),
            ),
            "readiness_status": "descriptive_sequence_review_available",
            "descriptive_observation": caveats(
                "exact_lower_drawdown_observed",
                "exact_smaller_loss_cluster_observed",
                "descriptive_only_no_decision",
            ),
            "caveat": caveats("descriptive_only_no_decision", "no_path_recomputation_performed"),
            "blocking_warning": False,
        }
    )
    if exact_row.get("readiness_status") == "unavailable_missing_artifact" or single_row.get("readiness_status") == "unavailable_missing_artifact":
        row["artifact_status"] = "missing"
        row["readiness_status"] = "unavailable_missing_artifact"
        row["required_next_artifact"] = "trade_logs_and_equity_curves_for_both_sources"
    elif exact_row.get("readiness_status") == "descriptive_sequence_review_available_with_caveat" or single_row.get("readiness_status") == "descriptive_sequence_review_available_with_caveat":
        row["readiness_status"] = "descriptive_sequence_review_available_with_caveat"
        row["caveat"] = caveats("drawdown_duration_not_derivable", row["caveat"])
    return row


def next_artifact_row(args: argparse.Namespace) -> dict[str, Any]:
    row = {field: "" for field in FIELDNAMES}
    row.update(
        {
            "run_id": args.run_id,
            "review_scope": "next_drawdown_artifact_area",
            "row_type": "next_artifact_area",
            "source_label": "exact_rule_vs_single_filter_a",
            "artifact_status": "available",
            "metric_namespace": "R_multiple",
            "metric_unit": "R",
            "readiness_status": "descriptive_sequence_review_available_with_caveat",
            "descriptive_observation": caveats(
                "further_drawdown_review_required",
                "timeout_policy_review_still_separate",
                "descriptive_only_no_decision",
            ),
            "caveat": caveats("timeout_policy_review_still_separate", "descriptive_only_no_decision"),
            "required_next_artifact": "drawdown_cluster_review_or_deeper_walk_forward_artifact",
            "blocking_warning": False,
        }
    )
    return row


def build_review_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    artifacts = {
        "exact_base": artifact(Path(args.exact_stress_dir), "exact_rule", "p75"),
        "exact_stress": artifact(Path(args.exact_stress_dir), "exact_rule", "p90"),
        "single_base": artifact(Path(args.single_filter_a_stress_dir), "single_filter_a", "p75"),
        "single_stress": artifact(Path(args.single_filter_a_stress_dir), "single_filter_a", "p90"),
    }
    warnings: list[dict[str, Any]] = []
    exact_base = sequence_row(args, review_scope="exact_rule_base_equity_sequence_review", item=artifacts["exact_base"], warnings=warnings)
    exact_stress = sequence_row(args, review_scope="exact_rule_stress_equity_sequence_review", item=artifacts["exact_stress"], warnings=warnings)
    single_base = sequence_row(args, review_scope="single_filter_a_base_equity_sequence_review", item=artifacts["single_base"], warnings=warnings)
    single_stress = sequence_row(args, review_scope="single_filter_a_stress_equity_sequence_review", item=artifacts["single_stress"], warnings=warnings)
    rows = [exact_base, exact_stress, single_base, single_stress]
    rows.append(
        comparison_row(
            args,
            review_scope="exact_vs_single_filter_a_base_drawdown_sequence_comparison",
            exact_row=exact_base,
            single_row=single_base,
            cost_profile="p75",
        )
    )
    rows.append(
        comparison_row(
            args,
            review_scope="exact_vs_single_filter_a_stress_drawdown_sequence_comparison",
            exact_row=exact_stress,
            single_row=single_stress,
            cost_profile="p90",
        )
    )
    rows.append(
        comparison_row(
            args,
            review_scope="exact_vs_single_filter_a_loss_cluster_comparison",
            exact_row=exact_base,
            single_row=single_base,
            cost_profile="p75",
        )
    )
    rows.append(next_artifact_row(args))
    metadata = {
        "detected_equity_columns": sorted({column for item in artifacts.values() for column in item["equity_columns"] if column in EQUITY_COLUMNS}),
        "detected_trade_columns": sorted({column for item in artifacts.values() for column in item["trade_columns"] if column in TRADE_COLUMNS}),
    }
    return rows, warnings, metadata


def status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("readiness_status") or "") for row in rows)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    counts = status_counts(rows)
    row_by_scope = {row["review_scope"]: row for row in rows}
    base = row_by_scope.get("exact_vs_single_filter_a_base_drawdown_sequence_comparison", {})
    stress = row_by_scope.get("exact_vs_single_filter_a_stress_drawdown_sequence_comparison", {})
    lines = [
        "# Fixed Candidate Equity / Drawdown Sequence Review",
        "",
        "Artifact-only descriptive review. It reads existing equity curves and trade logs and does not execute validation, backtests, timeout review, diagnostics, candidate audit, model work, database mutation, or external actions.",
        "No candidate-quality conclusion or trading decision was made.",
        "No TP/SL path outcomes were recalculated; this review only summarizes already-produced artifact rows.",
        "",
        "## Inputs",
        "",
        f"- exact_stress_dir: `{args.exact_stress_dir}`",
        f"- single_filter_a_stress_dir: `{args.single_filter_a_stress_dir}`",
        f"- timeout_artifact_review_dir: `{args.timeout_artifact_review_dir}`",
        f"- walkforward_drawdown_review_dir: `{args.walkforward_drawdown_review_dir}`",
        "",
        "## Counts",
        "",
        f"- review_row_count: `{len(rows)}`",
        f"- descriptive_sequence_review_available: `{counts.get('descriptive_sequence_review_available', 0)}`",
        f"- descriptive_sequence_review_available_with_caveat: `{counts.get('descriptive_sequence_review_available_with_caveat', 0)}`",
        f"- unavailable_missing_artifact: `{counts.get('unavailable_missing_artifact', 0)}`",
        f"- blocked_unreadable_input: `{counts.get('blocked_unreadable_input', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## Detected Columns",
        "",
        f"- equity_columns: `{join_values(metadata.get('detected_equity_columns', []))}`",
        f"- trade_columns: `{join_values(metadata.get('detected_trade_columns', []))}`",
        "",
        "## Exact vs Single Filter A Drawdown Sequence Summary",
        "",
        f"- base_drawdown_delta: `{base.get('drawdown_delta', '')}`",
        f"- base_drawdown_duration_delta: `{base.get('drawdown_duration_delta', '')}`",
        f"- base_worst_20_trade_sum_delta: `{base.get('worst_20_trade_sum_delta', '')}`",
        f"- stress_drawdown_delta: `{stress.get('drawdown_delta', '')}`",
        f"- stress_drawdown_duration_delta: `{stress.get('drawdown_duration_delta', '')}`",
        f"- stress_worst_20_trade_sum_delta: `{stress.get('worst_20_trade_sum_delta', '')}`",
        "",
        "## Loss Cluster Descriptive Summary",
        "",
        f"- base_longest_negative_streak_delta: `{base.get('longest_negative_streak_delta', '')}`",
        "",
        "This artifact does not replace true walk-forward validation or timeout policy review.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    counts = status_counts(rows)
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "exact_stress_dir": str(args.exact_stress_dir),
        "single_filter_a_stress_dir": str(args.single_filter_a_stress_dir),
        "timeout_artifact_review_dir": str(args.timeout_artifact_review_dir),
        "walkforward_drawdown_review_dir": str(args.walkforward_drawdown_review_dir),
        "comparison_table_dir": str(args.comparison_table_dir or ""),
        "r_multiple_review_dir": str(args.r_multiple_review_dir or ""),
        "review_row_count": len(rows),
        "descriptive_sequence_review_available_count": counts.get("descriptive_sequence_review_available", 0),
        "descriptive_sequence_review_available_with_caveat_count": counts.get(
            "descriptive_sequence_review_available_with_caveat", 0
        ),
        "unavailable_missing_artifact_count": counts.get("unavailable_missing_artifact", 0),
        "blocked_unreadable_input_count": counts.get("blocked_unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "detected_equity_columns": metadata.get("detected_equity_columns", []),
        "detected_trade_columns": metadata.get("detected_trade_columns", []),
        "no_child_scripts_executed": True,
        "no_stress_validation_executed": True,
        "no_backtests_run": True,
        "no_timeout_policy_review_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_audit_executed": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    rows, warnings, metadata = build_review_rows(args)
    write_csv(paths["review"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build an artifact-only equity/drawdown sequence review. "
            "No validation, backtests, timeout review, diagnostics, or child scripts are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--exact-stress-dir", type=Path, default=DEFAULT_EXACT_STRESS_DIR)
    parser.add_argument("--single-filter-a-stress-dir", type=Path, default=DEFAULT_SINGLE_FILTER_A_STRESS_DIR)
    parser.add_argument("--timeout-artifact-review-dir", type=Path, default=DEFAULT_TIMEOUT_ARTIFACT_REVIEW_DIR)
    parser.add_argument("--walkforward-drawdown-review-dir", type=Path, default=DEFAULT_WALKFORWARD_DRAWDOWN_REVIEW_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--comparison-table-dir", type=Path, default=DEFAULT_COMPARISON_TABLE_DIR)
    parser.add_argument("--r-multiple-review-dir", type=Path, default=DEFAULT_R_MULTIPLE_REVIEW_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate equity/drawdown sequence review build failed: {exc}")
        return 1
    print("Fixed-candidate equity/drawdown sequence review build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
