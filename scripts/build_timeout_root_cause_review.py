"""Build a timeout root-cause review from existing research outputs.

This script reads an existing timeout fragility audit and existing rule-replay
trade logs. It diagnoses why TIMEOUT trades are fragile without rerunning
replay, recomputing entries, changing candidate assumptions, adding filters, or
changing TP/SL settings.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import re
import sqlite3
import statistics
import sys
from typing import Iterable

try:
    from candidate_audit_schema import (
        RESEARCH_ONLY_FORBIDDEN_ACTIONS,
        add_common_summary_fields,
        forbidden_actions_text,
        next_action_row,
        warning_row,
        with_common_next_action_fields,
        with_common_summary_fields,
        with_common_warning_fields,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.candidate_audit_schema import (
        RESEARCH_ONLY_FORBIDDEN_ACTIONS,
        add_common_summary_fields,
        forbidden_actions_text,
        next_action_row,
        warning_row,
        with_common_next_action_fields,
        with_common_summary_fields,
        with_common_warning_fields,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "timeout_root_cause_review"

AUDIT_SUMMARY_FILE = "timeout_fragility_audit_summary.csv"
AUDIT_REPORT_FILE = "timeout_fragility_audit_report.md"
AUDIT_WARNINGS_FILE = "timeout_fragility_audit_warnings.csv"
AUDIT_YEARLY_FILE = "timeout_fragility_audit_yearly.csv"
AUDIT_MONTHLY_FILE = "timeout_fragility_audit_monthly.csv"
AUDIT_ENTRY_HOUR_FILE = "timeout_fragility_audit_entry_hour.csv"
AUDIT_SUBPERIODS_FILE = "timeout_fragility_audit_subperiods.csv"
AUDIT_SEQUENCES_FILE = "timeout_fragility_audit_sequences.csv"
AUDIT_COMPARISON_FILE = "timeout_fragility_audit_non_timeout_comparison.csv"

REPLAY_STRESS_TRADE_LOG_FILE = "rule_based_trade_log_stress.csv"
REPLAY_BASE_TRADE_LOG_FILE = "rule_based_trade_log_base.csv"
REPLAY_STRESS_EQUITY_FILE = "rule_based_equity_curve_stress.csv"
REPLAY_SUMMARY_FILE = "rule_based_backtest_summary.csv"
REPLAY_WARNINGS_FILE = "rule_based_warnings.csv"

CONTROLLED_SUMMARY_FILE = "controlled_rule_expansion_summary.csv"
CONTROLLED_WARNINGS_FILE = "controlled_rule_expansion_warnings.csv"

SUMMARY_FILE = "timeout_root_cause_summary.csv"
REPORT_FILE = "timeout_root_cause_report.md"
WARNINGS_FILE = "timeout_root_cause_warnings.csv"
LARGEST_SEQUENCE_TRADES_FILE = "timeout_root_cause_largest_sequence_trades.csv"
NEGATIVE_TIMEOUT_TRADES_FILE = "timeout_root_cause_negative_timeout_trades.csv"
POSITIVE_VS_NEGATIVE_FILE = "timeout_root_cause_positive_vs_negative_timeout.csv"
YEAR_MONTH_BREAKDOWN_FILE = "timeout_root_cause_year_month_breakdown.csv"
ENTRY_HOUR_BREAKDOWN_FILE = "timeout_root_cause_entry_hour_breakdown.csv"
COST_PROFILE_FILE = "timeout_root_cause_cost_profile.csv"
FEATURE_CONTEXT_FILE = "timeout_root_cause_feature_context.csv"
NEXT_REVIEW_PLAN_FILE = "timeout_root_cause_next_review_plan.csv"

AUDIT_PASSED_LABEL = "TIMEOUT_AUDIT_PASSED"
AUDIT_RETAINED_LABEL = "TIMEOUT_AUDIT_RETAINED_FOR_REVIEW"
AUDIT_FAILED_LABEL = "TIMEOUT_AUDIT_FAILED"
ALLOWED_AUDIT_LABELS = {AUDIT_PASSED_LABEL, AUDIT_RETAINED_LABEL}

CLEARED_LABEL = "TIMEOUT_ROOT_CAUSE_CLEARED"
RETAINED_LABEL = "TIMEOUT_ROOT_CAUSE_RETAINED_FOR_REVIEW"
FAILED_LABEL = "TIMEOUT_ROOT_CAUSE_FAILED"

ROOT_TIMEOUT_LOSS_FAIL_RATIO = 0.10
ROOT_SEQUENCE_FAIL_RATIO = 0.10
ROOT_SEQUENCE_REVIEW_RATIO = 0.05
ROOT_SEQUENCE_CLEARED_RATIO = 0.025
ROOT_MIDDLE_SUBPERIOD_REVIEW_RATIO = 0.025
ROOT_ENTRY_HOUR_REVIEW_RATIO = 0.025
ROOT_LOSS_CONCENTRATION_REVIEW_PCT = 50.0
ROOT_COST_ABSOLUTE_REVIEW_DIFF = 0.02
ROOT_COST_RELATIVE_REVIEW_DIFF = 0.50
ROOT_CONTEXT_DOMINANCE_REVIEW_SHARE = 0.70
ROOT_CONTEXT_DOMINANCE_MIN_COUNT = 5

BASE_DB_ENRICHMENT_FIELDS = [
    "spread",
    "atr_20",
    "range_regime",
    "volatility_regime",
    "volume_liquidity_regime",
    "spread_liquidity_regime",
    "session",
    "hour",
    "day_of_week",
    "month",
    "year",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "blocking",
    "message",
    "related_metric",
    "metric_value",
    "threshold",
]
WARNING_FIELDNAMES = with_common_warning_fields(WARNING_FIELDNAMES)
REQUIRED_CANDIDATE_METADATA_FIELDS = (
    "symbol",
    "direction",
    "timeframe",
    "horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "feature_condition",
)

SUMMARY_FIELDNAMES = [
    "run_id",
    "timeout_audit_dir",
    "rule_replay_dir",
    "controlled_expansion_dir",
    "db_path",
    "root_cause_output_dir",
    "final_timeout_root_cause_classification",
    "can_return_to_baseline_and_cost_sensitivity_review",
    "warnings_count",
    "blocking_warnings_count",
    "symbol",
    "direction",
    "timeframe",
    "horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "feature_condition",
    "tp_atr",
    "sl_atr",
    "same_bar_policy",
    "candidate_scope",
    "stress_spread_policy",
    "input_timeout_audit_classification",
    "input_timeout_audit_warnings_count",
    "input_timeout_audit_blocking_warnings_count",
    "input_rule_replay_classification",
    "stress_trades_count",
    "stress_cumulative_R",
    "timeout_count",
    "timeout_cumulative_R",
    "timeout_mean_R",
    "timeout_median_R",
    "timeout_negative_count",
    "timeout_positive_count",
    "timeout_negative_share",
    "timeout_total_loss_R",
    "timeout_total_gain_R",
    "timeout_profit_factor_R",
    "timeout_largest_loss_R",
    "timeout_largest_gain_R",
    "timeout_loss_concentration_top_5_pct",
    "timeout_loss_concentration_top_10_pct",
    "timeout_loss_ratio_of_stress_cumulative_R",
    "largest_timeout_drawdown_sequence_start_trade_index",
    "largest_timeout_drawdown_sequence_end_trade_index",
    "sequence_timeout_count",
    "sequence_cumulative_R",
    "sequence_max_drawdown_R",
    "sequence_max_drawdown_ratio_of_stress_cumulative_R",
    "sequence_start_time",
    "sequence_end_time",
    "sequence_years",
    "sequence_months",
    "sequence_entry_hours",
    "sequence_negative_timeout_count",
    "sequence_positive_timeout_count",
    "sequence_share_of_total_timeout_loss",
    "negative_timeout_mean_R",
    "positive_timeout_mean_R",
    "negative_timeout_mean_cost_R",
    "positive_timeout_mean_cost_R",
    "negative_timeout_mean_net_R",
    "positive_timeout_mean_net_R",
    "negative_timeout_mean_gross_R_proxy",
    "positive_timeout_mean_gross_R_proxy",
    "negative_timeout_mean_bars_held",
    "positive_timeout_mean_bars_held",
    "cost_R_difference_negative_vs_positive_timeout",
    "negative_timeout_cost_materially_higher",
    "middle_subperiod_timeout_cumulative_R",
    "middle_subperiod_loss_ratio_of_stress_cumulative_R",
    "worst_entry_hour",
    "worst_entry_hour_timeout_cumulative_R",
    "worst_entry_hour_loss_ratio_of_stress_cumulative_R",
    "worst_month",
    "worst_month_timeout_cumulative_R",
    "worst_month_loss_ratio_of_stress_cumulative_R",
    "db_enrichment_requested",
    "db_enrichment_available",
    "db_enrichment_rows_matched",
    "db_enrichment_context_dominance_field",
    "db_enrichment_context_dominance_value",
    "db_enrichment_context_dominance_share",
]
SUMMARY_FIELDNAMES = with_common_summary_fields(SUMMARY_FIELDNAMES)

TRADE_OUTPUT_FIELDNAMES = [
    "stress_trade_index",
    "timeout_trade_index",
    "in_largest_sequence",
    "loss_rank",
    "entry_time",
    "exit_time",
    "symbol",
    "direction",
    "exit_reason",
    "bars_held",
    "R",
    "cost_R",
    "net_R",
    "gross_R_proxy",
    "entry_hour",
    "year",
    "month",
]

BUCKET_FIELDNAMES = [
    "bucket",
    "count",
    "share_of_timeout_trades",
    "mean_R",
    "median_R",
    "cumulative_R",
    "mean_cost_R",
    "median_cost_R",
    "cumulative_cost_R",
    "mean_net_R",
    "median_net_R",
    "cumulative_net_R",
    "mean_gross_R_proxy",
    "median_gross_R_proxy",
    "cumulative_gross_R_proxy",
    "mean_bars_held",
    "median_bars_held",
    "largest_loss_R",
    "largest_gain_R",
    "top_entry_hours",
    "top_year_months",
]

BREAKDOWN_FIELDNAMES = [
    "breakdown_type",
    "period",
    "bucket",
    "count",
    "share_of_bucket",
    "mean_R",
    "cumulative_R",
    "mean_cost_R",
    "cumulative_cost_R",
    "mean_net_R",
    "cumulative_net_R",
    "mean_bars_held",
]

COST_PROFILE_FIELDNAMES = [
    "bucket",
    "count",
    "mean_R",
    "median_R",
    "cumulative_R",
    "mean_cost_R",
    "median_cost_R",
    "cumulative_cost_R",
    "mean_net_R",
    "median_net_R",
    "cumulative_net_R",
    "mean_gross_R_proxy",
    "median_gross_R_proxy",
    "cumulative_gross_R_proxy",
    "cost_R_difference_vs_positive_timeout",
    "cost_R_difference_vs_non_timeout",
]

FEATURE_CONTEXT_FIELDNAMES = [
    "context_field",
    "context_value",
    "timeout_sign",
    "count",
    "trade_share",
    "mean_R",
    "cumulative_R",
    "mean_cost_R",
    "mean_net_R",
    "mean_gross_R_proxy",
    "mean_value",
    "median_value",
]

PLAN_FIELDNAMES = with_common_next_action_fields(["plan_item", "status", "rationale"])


@dataclass(frozen=True)
class RootCauseInputs:
    timeout_audit_dir: Path
    timeout_audit_summary: dict[str, str]
    timeout_audit_report_text: str
    timeout_audit_warnings: list[dict[str, str]]
    timeout_audit_yearly: list[dict[str, str]]
    timeout_audit_monthly: list[dict[str, str]]
    timeout_audit_entry_hour: list[dict[str, str]]
    timeout_audit_subperiods: list[dict[str, str]]
    timeout_audit_sequences: list[dict[str, str]]
    timeout_audit_comparison: list[dict[str, str]]
    rule_replay_dir: Path
    stress_trade_rows: list[dict[str, str]]
    base_trade_rows: list[dict[str, str]]
    stress_equity_rows: list[dict[str, str]]
    rule_replay_summary: dict[str, str]
    rule_replay_warnings: list[dict[str, str]]
    controlled_expansion_dir: Path | None
    controlled_summary: dict[str, str] | None
    controlled_warnings: list[dict[str, str]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only timeout root-cause review from existing timeout audit and rule-replay CSVs."
    )
    parser.add_argument("--timeout-audit-dir", required=True, type=Path)
    parser.add_argument("--rule-replay-dir", required=True, type=Path)
    parser.add_argument("--controlled-expansion-dir", type=Path)
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, type=Path)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input file: {path}")
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def first_csv_row(path: Path) -> dict[str, str]:
    rows = read_csv_rows(path)
    if not rows:
        raise ValueError(f"Input CSV contains no rows: {path}")
    return rows[0]


def csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
    return value


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def finite_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if math.isnan(parsed):
        return None
    return parsed


def int_value(value: object) -> int:
    number = finite_float(value)
    if number is None:
        return 0
    return int(number)


def mean(values: Iterable[float]) -> float | None:
    selected = list(values)
    if not selected:
        return None
    return sum(selected) / len(selected)


def median(values: Iterable[float]) -> float | None:
    selected = list(values)
    if not selected:
        return None
    return float(statistics.median(selected))


def trade_r(row: dict[str, str]) -> float:
    return finite_float(row.get("R")) or 0.0


def cost_r(row: dict[str, str]) -> float | None:
    return finite_float(row.get("cost_R"))


def net_r(row: dict[str, str]) -> float | None:
    return finite_float(row.get("net_R"))


def bars_held(row: dict[str, str]) -> float | None:
    return finite_float(row.get("bars_held"))


def gross_R_proxy(row: dict[str, str]) -> float | None:
    value = finite_float(row.get("R"))
    cost = finite_float(row.get("cost_R"))
    if value is None:
        return None
    return value + (cost or 0.0)


def parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def row_timestamp(row: dict[str, str], *, prefer_exit: bool) -> datetime | None:
    primary = "exit_time" if prefer_exit else "entry_time"
    fallback = "entry_time" if prefer_exit else "exit_time"
    return parse_timestamp(row.get(primary)) or parse_timestamp(row.get(fallback))


def timestamp_text(row: dict[str, str], *, prefer_exit: bool) -> str:
    timestamp = row_timestamp(row, prefer_exit=prefer_exit)
    return timestamp.isoformat(sep=" ") if timestamp else ""


def normalize_exit_reason(row: dict[str, str]) -> str:
    reason = str(row.get("exit_reason") or "OTHER").strip().upper()
    return reason or "OTHER"


def is_timeout(row: dict[str, str]) -> bool:
    return normalize_exit_reason(row) == "TIMEOUT"


def period_label(timestamp: datetime, period_type: str) -> str:
    if period_type == "year":
        return f"{timestamp.year:04d}"
    if period_type == "month":
        return f"{timestamp.year:04d}-{timestamp.month:02d}"
    raise ValueError(f"Unsupported period type: {period_type}")


def rate(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return count / total


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "output_dir": output_dir,
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "largest_sequence_trades": output_dir / LARGEST_SEQUENCE_TRADES_FILE,
        "negative_timeout_trades": output_dir / NEGATIVE_TIMEOUT_TRADES_FILE,
        "positive_vs_negative": output_dir / POSITIVE_VS_NEGATIVE_FILE,
        "year_month_breakdown": output_dir / YEAR_MONTH_BREAKDOWN_FILE,
        "entry_hour_breakdown": output_dir / ENTRY_HOUR_BREAKDOWN_FILE,
        "cost_profile": output_dir / COST_PROFILE_FILE,
        "feature_context": output_dir / FEATURE_CONTEXT_FILE,
        "next_review_plan": output_dir / NEXT_REVIEW_PLAN_FILE,
    }


def ensure_can_write(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for key, path in paths.items() if key != "output_dir" and path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Timeout root-cause review outputs already exist; pass --overwrite to replace: {joined}")


def load_inputs(
    timeout_audit_dir: Path,
    rule_replay_dir: Path,
    controlled_expansion_dir: Path | None,
) -> RootCauseInputs:
    if not timeout_audit_dir.exists():
        raise FileNotFoundError(f"Timeout audit directory does not exist: {timeout_audit_dir}")
    if not rule_replay_dir.exists():
        raise FileNotFoundError(f"Rule replay directory does not exist: {rule_replay_dir}")
    for filename in (
        AUDIT_SUMMARY_FILE,
        AUDIT_REPORT_FILE,
        AUDIT_WARNINGS_FILE,
        AUDIT_YEARLY_FILE,
        AUDIT_MONTHLY_FILE,
        AUDIT_ENTRY_HOUR_FILE,
        AUDIT_SUBPERIODS_FILE,
        AUDIT_SEQUENCES_FILE,
        AUDIT_COMPARISON_FILE,
    ):
        path = timeout_audit_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required input file: {path}")
    for filename in (
        REPLAY_STRESS_TRADE_LOG_FILE,
        REPLAY_BASE_TRADE_LOG_FILE,
        REPLAY_STRESS_EQUITY_FILE,
        REPLAY_SUMMARY_FILE,
        REPLAY_WARNINGS_FILE,
    ):
        path = rule_replay_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required input file: {path}")

    controlled_summary = None
    controlled_warnings: list[dict[str, str]] = []
    if controlled_expansion_dir is not None:
        summary_path = controlled_expansion_dir / CONTROLLED_SUMMARY_FILE
        warnings_path = controlled_expansion_dir / CONTROLLED_WARNINGS_FILE
        if summary_path.exists():
            controlled_summary = first_csv_row(summary_path)
        if warnings_path.exists():
            controlled_warnings = read_csv_rows(warnings_path)

    return RootCauseInputs(
        timeout_audit_dir=timeout_audit_dir,
        timeout_audit_summary=first_csv_row(timeout_audit_dir / AUDIT_SUMMARY_FILE),
        timeout_audit_report_text=(timeout_audit_dir / AUDIT_REPORT_FILE).read_text(encoding="utf-8"),
        timeout_audit_warnings=read_csv_rows(timeout_audit_dir / AUDIT_WARNINGS_FILE),
        timeout_audit_yearly=read_csv_rows(timeout_audit_dir / AUDIT_YEARLY_FILE),
        timeout_audit_monthly=read_csv_rows(timeout_audit_dir / AUDIT_MONTHLY_FILE),
        timeout_audit_entry_hour=read_csv_rows(timeout_audit_dir / AUDIT_ENTRY_HOUR_FILE),
        timeout_audit_subperiods=read_csv_rows(timeout_audit_dir / AUDIT_SUBPERIODS_FILE),
        timeout_audit_sequences=read_csv_rows(timeout_audit_dir / AUDIT_SEQUENCES_FILE),
        timeout_audit_comparison=read_csv_rows(timeout_audit_dir / AUDIT_COMPARISON_FILE),
        rule_replay_dir=rule_replay_dir,
        stress_trade_rows=read_csv_rows(rule_replay_dir / REPLAY_STRESS_TRADE_LOG_FILE),
        base_trade_rows=read_csv_rows(rule_replay_dir / REPLAY_BASE_TRADE_LOG_FILE),
        stress_equity_rows=read_csv_rows(rule_replay_dir / REPLAY_STRESS_EQUITY_FILE),
        rule_replay_summary=first_csv_row(rule_replay_dir / REPLAY_SUMMARY_FILE),
        rule_replay_warnings=read_csv_rows(rule_replay_dir / REPLAY_WARNINGS_FILE),
        controlled_expansion_dir=controlled_expansion_dir,
        controlled_summary=controlled_summary,
        controlled_warnings=controlled_warnings,
    )


def add_warning(
    warnings: list[dict[str, object]],
    *,
    warning_code: str,
    severity: str,
    message: str,
    blocking: bool = False,
    related_metric: str = "",
    metric_value: object = "",
    threshold: object = "",
) -> None:
    warnings.append(
        warning_row(
            warning_code=warning_code,
            severity=severity,
            blocking=blocking,
            message=message,
            related_stage="timeout_root_cause",
            related_metric=related_metric,
            metric_value=metric_value,
            threshold=threshold,
        )
    )


def missing_candidate_metadata(row: dict[str, object]) -> list[str]:
    return [field for field in REQUIRED_CANDIDATE_METADATA_FIELDS if not str(row.get(field) or "").strip()]


def inherited_blocking_warnings(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if bool_value(row.get("blocking"))
        or bool_value(row.get("blocks_ready"))
        or bool_value(row.get("blocks_match"))
        or str(row.get("severity") or "").strip().lower() in {"blocking", "error"}
    ]


def annotated_stress_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    timeout_index = 0
    output: list[dict[str, object]] = []
    for stress_index, row in enumerate(
        sorted(rows, key=lambda item: row_timestamp(item, prefer_exit=False) or datetime.max),
        start=1,
    ):
        is_timeout_row = is_timeout(row)
        if is_timeout_row:
            timeout_index += 1
        timestamp = row_timestamp(row, prefer_exit=False)
        annotated = {
            **row,
            "_stress_trade_index": stress_index,
            "_timeout_trade_index": timeout_index if is_timeout_row else "",
            "_entry_hour": timestamp.hour if timestamp else "",
            "_year": timestamp.year if timestamp else "",
            "_month": f"{timestamp.year:04d}-{timestamp.month:02d}" if timestamp else "",
        }
        output.append(annotated)
    return output


def timeout_rows_from_annotated(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if normalize_exit_reason(row) == "TIMEOUT"]


def split_timeout_sign(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    negative = [row for row in rows if trade_r(row) < 0]
    positive = [row for row in rows if trade_r(row) > 0]
    return negative, positive


def numeric_values(rows: list[dict[str, object]], key: str) -> list[float]:
    if key == "R":
        return [trade_r(row) for row in rows]
    if key == "cost_R":
        return [value for value in (cost_r(row) for row in rows) if value is not None]
    if key == "net_R":
        return [value for value in (net_r(row) for row in rows) if value is not None]
    if key == "gross_R_proxy":
        return [value for value in (gross_R_proxy(row) for row in rows) if value is not None]
    if key == "bars_held":
        return [value for value in (bars_held(row) for row in rows) if value is not None]
    return [value for value in (finite_float(row.get(key)) for row in rows) if value is not None]


def bucket_metrics(rows: list[dict[str, object]], total_timeout_count: int | None = None) -> dict[str, object]:
    values = numeric_values(rows, "R")
    costs = numeric_values(rows, "cost_R")
    nets = numeric_values(rows, "net_R")
    gross = numeric_values(rows, "gross_R_proxy")
    held = numeric_values(rows, "bars_held")
    return {
        "count": len(rows),
        "share_of_timeout_trades": rate(len(rows), total_timeout_count or 0) if total_timeout_count is not None else None,
        "mean_R": mean(values),
        "median_R": median(values),
        "cumulative_R": sum(values),
        "mean_cost_R": mean(costs),
        "median_cost_R": median(costs),
        "cumulative_cost_R": sum(costs) if costs else None,
        "mean_net_R": mean(nets),
        "median_net_R": median(nets),
        "cumulative_net_R": sum(nets) if nets else None,
        "mean_gross_R_proxy": mean(gross),
        "median_gross_R_proxy": median(gross),
        "cumulative_gross_R_proxy": sum(gross) if gross else None,
        "mean_bars_held": mean(held),
        "median_bars_held": median(held),
        "largest_loss_R": min(values) if values else None,
        "largest_gain_R": max(values) if values else None,
    }


def profit_factor(values: list[float]) -> float | None:
    profit = sum(value for value in values if value > 0)
    loss = sum(abs(value) for value in values if value < 0)
    if loss == 0:
        return None if profit == 0 else float("inf")
    return profit / loss


def max_drawdown(values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    maximum = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    return maximum


def loss_concentration_pct(rows: list[dict[str, object]], fraction: float) -> float | None:
    losses = sorted((abs(trade_r(row)) for row in rows if trade_r(row) < 0), reverse=True)
    if not losses:
        return None
    take = max(1, math.ceil(len(losses) * fraction))
    return sum(losses[:take]) / sum(losses) * 100.0


def top_distribution(rows: list[dict[str, object]], key: str, limit: int = 3) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "").strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    selected = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return ";".join(f"{key}={count}" for key, count in selected)


def compact_distribution(rows: list[dict[str, object]], key: str) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "").strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return ";".join(f"{value}:{count}" for value, count in sorted(counts.items()))


def largest_sequence_audit_row(rows: list[dict[str, str]]) -> dict[str, str]:
    selected = next((row for row in rows if row.get("diagnostic_type") == "largest_timeout_drawdown_sequence"), None)
    if selected is not None:
        return selected
    return max(rows, key=lambda row: finite_float(row.get("max_drawdown_R")) or 0.0, default={})


def largest_sequence_trades(timeout_rows: list[dict[str, object]], audit_sequences: list[dict[str, str]]) -> list[dict[str, object]]:
    sequence = largest_sequence_audit_row(audit_sequences)
    start = int_value(sequence.get("start_trade_index")) or 1
    end = int_value(sequence.get("end_trade_index")) or 0
    if end < start:
        return []
    return [
        row
        for row in timeout_rows
        if start <= int_value(row.get("_timeout_trade_index")) <= end
    ]


def trade_output_rows(rows: list[dict[str, object]], largest_sequence_indexes: set[int]) -> list[dict[str, object]]:
    negative_rows = sorted([row for row in rows if trade_r(row) < 0], key=lambda row: trade_r(row))
    ranks = {int_value(row.get("_timeout_trade_index")): index for index, row in enumerate(negative_rows, start=1)}
    output: list[dict[str, object]] = []
    for row in rows:
        timeout_index = int_value(row.get("_timeout_trade_index"))
        output.append(
            {
                "stress_trade_index": row.get("_stress_trade_index", ""),
                "timeout_trade_index": timeout_index,
                "in_largest_sequence": timeout_index in largest_sequence_indexes,
                "loss_rank": ranks.get(timeout_index, ""),
                "entry_time": row.get("entry_time", ""),
                "exit_time": row.get("exit_time", ""),
                "symbol": row.get("symbol", ""),
                "direction": row.get("direction", ""),
                "exit_reason": row.get("exit_reason", ""),
                "bars_held": row.get("bars_held", ""),
                "R": row.get("R", ""),
                "cost_R": row.get("cost_R", ""),
                "net_R": row.get("net_R", ""),
                "gross_R_proxy": gross_R_proxy(row),
                "entry_hour": row.get("_entry_hour", ""),
                "year": row.get("_year", ""),
                "month": row.get("_month", ""),
            }
        )
    return output


def positive_vs_negative_rows(timeout_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    negative, positive = split_timeout_sign(timeout_rows)
    buckets = [
        ("all_timeout", timeout_rows),
        ("negative_timeout", negative),
        ("positive_timeout", positive),
        ("near_zero_timeout", [row for row in timeout_rows if math.isclose(trade_r(row), 0.0, abs_tol=0.025)]),
    ]
    output: list[dict[str, object]] = []
    for bucket, rows in buckets:
        metrics = bucket_metrics(rows, len(timeout_rows))
        output.append(
            {
                "bucket": bucket,
                **metrics,
                "top_entry_hours": top_distribution(rows, "_entry_hour"),
                "top_year_months": top_distribution(rows, "_month"),
            }
        )
    return output


def breakdown_rows(timeout_rows: list[dict[str, object]], key: str, breakdown_type: str) -> list[dict[str, object]]:
    buckets = {
        "all_timeout": timeout_rows,
        "negative_timeout": [row for row in timeout_rows if trade_r(row) < 0],
        "positive_timeout": [row for row in timeout_rows if trade_r(row) > 0],
    }
    output: list[dict[str, object]] = []
    for bucket, rows in buckets.items():
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            value = str(row.get(key) or "").strip()
            if value:
                grouped.setdefault(value, []).append(row)
        for period in sorted(grouped):
            period_rows = grouped[period]
            metrics = bucket_metrics(period_rows, len(rows))
            output.append(
                {
                    "breakdown_type": breakdown_type,
                    "period": period,
                    "bucket": bucket,
                    "count": len(period_rows),
                    "share_of_bucket": rate(len(period_rows), len(rows)),
                    "mean_R": metrics["mean_R"],
                    "cumulative_R": metrics["cumulative_R"],
                    "mean_cost_R": metrics["mean_cost_R"],
                    "cumulative_cost_R": metrics["cumulative_cost_R"],
                    "mean_net_R": metrics["mean_net_R"],
                    "cumulative_net_R": metrics["cumulative_net_R"],
                    "mean_bars_held": metrics["mean_bars_held"],
                }
            )
    return output


def cost_profile_rows(
    timeout_rows: list[dict[str, object]],
    non_timeout_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    negative, positive = split_timeout_sign(timeout_rows)
    positive_mean_cost = mean(numeric_values(positive, "cost_R"))
    non_timeout_mean_cost = mean(numeric_values(non_timeout_rows, "cost_R"))
    buckets = [
        ("all_timeout", timeout_rows),
        ("negative_timeout", negative),
        ("positive_timeout", positive),
        ("non_timeout", non_timeout_rows),
    ]
    output: list[dict[str, object]] = []
    for bucket, rows in buckets:
        metrics = bucket_metrics(rows)
        mean_cost = finite_float(metrics.get("mean_cost_R"))
        output.append(
            {
                "bucket": bucket,
                "count": metrics["count"],
                "mean_R": metrics["mean_R"],
                "median_R": metrics["median_R"],
                "cumulative_R": metrics["cumulative_R"],
                "mean_cost_R": metrics["mean_cost_R"],
                "median_cost_R": metrics["median_cost_R"],
                "cumulative_cost_R": metrics["cumulative_cost_R"],
                "mean_net_R": metrics["mean_net_R"],
                "median_net_R": metrics["median_net_R"],
                "cumulative_net_R": metrics["cumulative_net_R"],
                "mean_gross_R_proxy": metrics["mean_gross_R_proxy"],
                "median_gross_R_proxy": metrics["median_gross_R_proxy"],
                "cumulative_gross_R_proxy": metrics["cumulative_gross_R_proxy"],
                "cost_R_difference_vs_positive_timeout": (
                    mean_cost - positive_mean_cost if mean_cost is not None and positive_mean_cost is not None else None
                ),
                "cost_R_difference_vs_non_timeout": (
                    mean_cost - non_timeout_mean_cost if mean_cost is not None and non_timeout_mean_cost is not None else None
                ),
            }
        )
    return output


def add_input_warnings(inputs: RootCauseInputs, warnings: list[dict[str, object]]) -> None:
    audit_label = str(inputs.timeout_audit_summary.get("final_timeout_audit_classification") or "")
    if audit_label == AUDIT_FAILED_LABEL:
        add_warning(
            warnings,
            warning_code="input_timeout_audit_failed",
            severity="blocking",
            blocking=True,
            message="Input timeout audit failed; root-cause review cannot clear the candidate.",
            related_metric="final_timeout_audit_classification",
            metric_value=audit_label,
            threshold="not TIMEOUT_AUDIT_FAILED",
        )
    elif audit_label not in ALLOWED_AUDIT_LABELS:
        add_warning(
            warnings,
            warning_code="input_timeout_audit_classification",
            severity="blocking",
            blocking=True,
            message=f"Input timeout audit classification is {audit_label or 'missing'}, not an allowed audit state.",
            related_metric="final_timeout_audit_classification",
            metric_value=audit_label,
            threshold="|".join(sorted(ALLOWED_AUDIT_LABELS)),
        )

    for warning in inherited_blocking_warnings(inputs.timeout_audit_warnings):
        add_warning(
            warnings,
            warning_code=f"inherited_timeout_audit_{warning.get('warning_code') or 'warning'}",
            severity="blocking",
            blocking=True,
            message=f"Inherited timeout audit blocking warning: {warning.get('message') or warning}.",
            related_metric=str(warning.get("related_metric") or ""),
            metric_value=warning.get("metric_value", ""),
            threshold=warning.get("threshold", ""),
        )
    for warning in inherited_blocking_warnings(inputs.rule_replay_warnings):
        add_warning(
            warnings,
            warning_code=f"inherited_rule_replay_{warning.get('check') or warning.get('warning_code') or 'warning'}",
            severity="blocking",
            blocking=True,
            message=f"Inherited rule replay blocking warning: {warning.get('message') or warning}.",
            related_metric=str(warning.get("related_metric") or warning.get("check") or ""),
            metric_value=warning.get("metric_value", ""),
            threshold=warning.get("threshold", ""),
        )
    for warning in inherited_blocking_warnings(inputs.controlled_warnings):
        add_warning(
            warnings,
            warning_code=f"inherited_controlled_{warning.get('warning_code') or warning.get('check') or 'warning'}",
            severity="blocking",
            blocking=True,
            message=f"Inherited controlled expansion blocking warning: {warning.get('message') or warning}.",
            related_metric=str(warning.get("related_metric") or warning.get("check") or ""),
            metric_value=warning.get("metric_value", ""),
            threshold=warning.get("threshold", ""),
        )


def add_root_cause_warnings(summary: dict[str, object], warnings: list[dict[str, object]]) -> None:
    stress_cumulative = finite_float(summary.get("stress_cumulative_R"))
    timeout_loss_ratio = finite_float(summary.get("timeout_loss_ratio_of_stress_cumulative_R")) or 0.0
    sequence_ratio = finite_float(summary.get("sequence_max_drawdown_ratio_of_stress_cumulative_R")) or 0.0
    middle_ratio = finite_float(summary.get("middle_subperiod_loss_ratio_of_stress_cumulative_R")) or 0.0
    entry_hour_ratio = finite_float(summary.get("worst_entry_hour_loss_ratio_of_stress_cumulative_R")) or 0.0
    top_5_loss_pct = finite_float(summary.get("timeout_loss_concentration_top_5_pct")) or 0.0
    top_10_loss_pct = finite_float(summary.get("timeout_loss_concentration_top_10_pct")) or 0.0
    cost_diff = finite_float(summary.get("cost_R_difference_negative_vs_positive_timeout"))
    positive_cost = finite_float(summary.get("positive_timeout_mean_cost_R")) or 0.0
    context_share = finite_float(summary.get("db_enrichment_context_dominance_share")) or 0.0

    if stress_cumulative is None or stress_cumulative <= 0:
        add_warning(
            warnings,
            warning_code="stress_cumulative_R_blocking",
            severity="blocking",
            blocking=True,
            message="Stress cumulative_R is unavailable or non-positive in the existing inputs.",
            related_metric="stress_cumulative_R",
            metric_value=stress_cumulative,
            threshold="> 0",
        )
        return
    if timeout_loss_ratio > ROOT_TIMEOUT_LOSS_FAIL_RATIO:
        add_warning(
            warnings,
            warning_code="timeout_root_cause_blocking",
            severity="blocking",
            blocking=True,
            message="Timeout loss is structurally large relative to stress cumulative_R.",
            related_metric="timeout_loss_ratio_of_stress_cumulative_R",
            metric_value=timeout_loss_ratio,
            threshold=f"<= {ROOT_TIMEOUT_LOSS_FAIL_RATIO}",
        )
    if sequence_ratio > ROOT_SEQUENCE_FAIL_RATIO:
        add_warning(
            warnings,
            warning_code="largest_sequence_blocking",
            severity="blocking",
            blocking=True,
            message="Largest timeout drawdown sequence is severe relative to stress cumulative_R.",
            related_metric="sequence_max_drawdown_ratio_of_stress_cumulative_R",
            metric_value=sequence_ratio,
            threshold=f"<= {ROOT_SEQUENCE_FAIL_RATIO}",
        )
    elif sequence_ratio > ROOT_SEQUENCE_REVIEW_RATIO:
        add_warning(
            warnings,
            warning_code="largest_sequence_review",
            severity="review",
            blocking=False,
            message="Largest timeout drawdown sequence remains material enough for timeout review.",
            related_metric="sequence_max_drawdown_ratio_of_stress_cumulative_R",
            metric_value=sequence_ratio,
            threshold=f"<= {ROOT_SEQUENCE_REVIEW_RATIO}",
        )
    if middle_ratio > ROOT_MIDDLE_SUBPERIOD_REVIEW_RATIO:
        add_warning(
            warnings,
            warning_code="middle_subperiod_timeout_review",
            severity="review",
            blocking=False,
            message="Middle timeout subperiod loss is material relative to stress cumulative_R.",
            related_metric="middle_subperiod_loss_ratio_of_stress_cumulative_R",
            metric_value=middle_ratio,
            threshold=f"<= {ROOT_MIDDLE_SUBPERIOD_REVIEW_RATIO}",
        )
    if entry_hour_ratio > ROOT_ENTRY_HOUR_REVIEW_RATIO:
        add_warning(
            warnings,
            warning_code="entry_hour_timeout_review",
            severity="review",
            blocking=False,
            message="Worst timeout entry hour has material negative contribution.",
            related_metric="worst_entry_hour_loss_ratio_of_stress_cumulative_R",
            metric_value=entry_hour_ratio,
            threshold=f"<= {ROOT_ENTRY_HOUR_REVIEW_RATIO}",
        )
    if top_5_loss_pct > ROOT_LOSS_CONCENTRATION_REVIEW_PCT or top_10_loss_pct > ROOT_LOSS_CONCENTRATION_REVIEW_PCT:
        add_warning(
            warnings,
            warning_code="timeout_loss_concentration_review",
            severity="review",
            blocking=False,
            message="Timeout losses are meaningfully concentrated in the largest negative timeout trades.",
            related_metric="timeout_loss_concentration_top_5_pct|timeout_loss_concentration_top_10_pct",
            metric_value=f"{top_5_loss_pct}|{top_10_loss_pct}",
            threshold=f"<= {ROOT_LOSS_CONCENTRATION_REVIEW_PCT}",
        )
    if cost_diff is not None:
        material_cost_threshold = max(ROOT_COST_ABSOLUTE_REVIEW_DIFF, positive_cost * ROOT_COST_RELATIVE_REVIEW_DIFF)
        if cost_diff > material_cost_threshold:
            add_warning(
                warnings,
                warning_code="negative_timeout_cost_review",
                severity="review",
                blocking=False,
                message="Negative timeout trades have materially higher cost_R than positive timeout trades.",
                related_metric="cost_R_difference_negative_vs_positive_timeout",
                metric_value=cost_diff,
                threshold=f"<= {material_cost_threshold}",
            )
    if context_share >= ROOT_CONTEXT_DOMINANCE_REVIEW_SHARE:
        add_warning(
            warnings,
            warning_code="db_context_dominance_review",
            severity="review",
            blocking=False,
            message="Optional DB enrichment found a recurring context dominating negative timeout outcomes.",
            related_metric="db_enrichment_context_dominance_share",
            metric_value=context_share,
            threshold=f"< {ROOT_CONTEXT_DOMINANCE_REVIEW_SHARE}",
        )


def classify_root_cause(summary: dict[str, object], warnings: list[dict[str, object]]) -> str:
    if any(bool_value(warning.get("blocking")) for warning in warnings):
        return FAILED_LABEL
    has_review_warning = any(str(warning.get("severity") or "").lower() in {"review", "severe"} for warning in warnings)
    sequence_ratio = finite_float(summary.get("sequence_max_drawdown_ratio_of_stress_cumulative_R")) or 0.0
    cost_material = bool_value(summary.get("negative_timeout_cost_materially_higher"))
    if has_review_warning or cost_material or sequence_ratio > ROOT_SEQUENCE_CLEARED_RATIO:
        return RETAINED_LABEL
    return CLEARED_LABEL


def next_action_for_classification(classification: str) -> str:
    if classification == CLEARED_LABEL:
        return "Candidate can return to controlled baseline and cost-sensitivity review."
    if classification == RETAINED_LABEL:
        return "Candidate should remain in timeout review before baseline and cost-sensitivity expansion."
    return "Candidate should not continue to baseline and cost-sensitivity review under current timeout evidence."


def load_db_enrichment(
    db_path: Path | None,
    *,
    symbol: str,
    timeframe: str,
    feature_condition: str,
    timeout_rows: list[dict[str, object]],
    warnings: list[dict[str, object]],
) -> tuple[dict[str, dict[str, object]], list[dict[str, object]], dict[str, object]]:
    if db_path is None:
        add_warning(
            warnings,
            warning_code="db_enrichment_unavailable",
            severity="info",
            blocking=False,
            message="No --db-path was provided; feature context enrichment was skipped.",
            related_metric="db_path",
            metric_value="",
            threshold="provided for optional enrichment",
        )
        return {}, [], {"available": False, "matched_rows": 0}
    if not db_path.exists():
        add_warning(
            warnings,
            warning_code="db_enrichment_unavailable",
            severity="review",
            blocking=False,
            message="Provided --db-path does not exist; feature context enrichment was skipped.",
            related_metric="db_path",
            metric_value=str(db_path),
            threshold="existing SQLite database",
        )
        return {}, [], {"available": False, "matched_rows": 0}
    try:
        with sqlite3.connect(db_path) as connection:
            table_rows = connection.execute("PRAGMA table_info(ml_dataset)").fetchall()
            columns = {str(row[1]) for row in table_rows}
            required = {"symbol", "timeframe", "time_server"}
            if not required.issubset(columns):
                add_warning(
                    warnings,
                    warning_code="db_enrichment_unavailable",
                    severity="review",
                    blocking=False,
                    message="ml_dataset is missing required join columns; feature context enrichment was skipped.",
                    related_metric="ml_dataset_columns",
                    metric_value=",".join(sorted(columns)),
                    threshold="symbol,timeframe,time_server",
                )
                return {}, [], {"available": False, "matched_rows": 0}
            selected_fields = [
                field
                for field in db_enrichment_fields(feature_condition)
                if field in columns and field not in required
            ]
            if not selected_fields:
                add_warning(
                    warnings,
                    warning_code="db_enrichment_unavailable",
                    severity="review",
                    blocking=False,
                    message="ml_dataset does not contain any supported enrichment fields.",
                    related_metric="ml_dataset_columns",
                    metric_value=",".join(sorted(columns)),
                    threshold="at least one supported enrichment field",
                )
                return {}, [], {"available": False, "matched_rows": 0}
            entry_times = sorted({str(row.get("entry_time") or "") for row in timeout_rows if row.get("entry_time")})
            if not entry_times:
                return {}, [], {"available": False, "matched_rows": 0}
            placeholders = ",".join("?" for _ in entry_times)
            query = (
                f"SELECT {', '.join(['symbol', 'timeframe', 'time_server', *selected_fields])} "
                f"FROM ml_dataset WHERE symbol = ? AND timeframe = ? AND time_server IN ({placeholders})"
            )
            rows = connection.execute(query, [symbol, timeframe, *entry_times]).fetchall()
    except sqlite3.Error as exc:
        add_warning(
            warnings,
            warning_code="db_enrichment_unavailable",
            severity="review",
            blocking=False,
            message=f"SQLite enrichment failed: {exc}",
            related_metric="db_path",
            metric_value=str(db_path),
            threshold="readable ml_dataset",
        )
        return {}, [], {"available": False, "matched_rows": 0}

    query_columns = ["symbol", "timeframe", "time_server", *selected_fields]
    by_time: dict[str, dict[str, object]] = {}
    for row_values in rows:
        row = dict(zip(query_columns, row_values))
        time_value = str(row.get("time_server") or "")
        if time_value:
            by_time[time_value] = row
    if not by_time:
        add_warning(
            warnings,
            warning_code="db_enrichment_unavailable",
            severity="review",
            blocking=False,
            message="No ml_dataset rows matched timeout entry times; feature context enrichment was skipped.",
            related_metric="matched_rows",
            metric_value=0,
            threshold="> 0",
        )
        return {}, [], {"available": False, "matched_rows": 0}
    context_rows, dominance = feature_context_rows(timeout_rows, by_time, selected_fields)
    return by_time, context_rows, {"available": bool(context_rows), "matched_rows": len(by_time), **dominance}


def db_enrichment_fields(feature_condition: str) -> list[str]:
    fields: list[str] = []
    for field in [*BASE_DB_ENRICHMENT_FIELDS, *extract_condition_feature_fields(feature_condition)]:
        if field and field not in fields:
            fields.append(field)
    return fields


def extract_condition_feature_fields(feature_condition: str) -> list[str]:
    fields: list[str] = []
    for condition in re.split(r"\s+AND\s+", str(feature_condition or "").strip(), flags=re.IGNORECASE):
        parts = [part.strip() for part in condition.split(":") if part.strip()]
        if not parts:
            continue
        field = ""
        if len(parts) == 2:
            field = "hour" if parts[0] == "hour_session" else parts[0]
        elif len(parts) >= 3:
            field = "day_of_week" if parts[0] == "day_of_week" else "hour" if parts[0] == "hour_session" else parts[1]
        if field and field not in fields:
            fields.append(field)
    return fields


def timeout_sign(row: dict[str, object]) -> str:
    value = trade_r(row)
    if value < 0:
        return "negative_timeout"
    if value > 0:
        return "positive_timeout"
    return "flat_timeout"


def feature_context_rows(
    timeout_rows: list[dict[str, object]],
    db_rows_by_time: dict[str, dict[str, object]],
    selected_fields: list[str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    enriched_pairs = [
        (row, db_rows_by_time.get(str(row.get("entry_time") or "")))
        for row in timeout_rows
        if db_rows_by_time.get(str(row.get("entry_time") or ""))
    ]
    output: list[dict[str, object]] = []
    numeric_context_fields = {"spread", "atr_20", "hour", "day_of_week", "month", "year"}
    categorical_fields = [
        field
        for field in selected_fields
        if not is_numeric_context_field(field, enriched_pairs, numeric_context_fields)
    ]
    dominance = {
        "db_enrichment_context_dominance_field": "",
        "db_enrichment_context_dominance_value": "",
        "db_enrichment_context_dominance_share": "",
    }
    for field in selected_fields:
        if field == "time_server":
            continue
        for sign in ("all_timeout", "negative_timeout", "positive_timeout"):
            selected = [
                (trade, db_row)
                for trade, db_row in enriched_pairs
                if sign == "all_timeout" or timeout_sign(trade) == sign
            ]
            if not selected:
                continue
            if is_numeric_context_field(field, selected, numeric_context_fields):
                values = [finite_float(db_row.get(field)) for _trade, db_row in selected]
                finite_values = [value for value in values if value is not None]
                trades = [trade for trade, _db_row in selected]
                output.append(
                    {
                        "context_field": field,
                        "context_value": "numeric_summary",
                        "timeout_sign": sign,
                        "count": len(finite_values),
                        "trade_share": rate(len(finite_values), len(selected)),
                        "mean_R": mean(numeric_values(trades, "R")),
                        "cumulative_R": sum(numeric_values(trades, "R")),
                        "mean_cost_R": mean(numeric_values(trades, "cost_R")),
                        "mean_net_R": mean(numeric_values(trades, "net_R")),
                        "mean_gross_R_proxy": mean(numeric_values(trades, "gross_R_proxy")),
                        "mean_value": mean(finite_values),
                        "median_value": median(finite_values),
                    }
                )
            else:
                grouped: dict[str, list[dict[str, object]]] = {}
                for trade, db_row in selected:
                    value = str(db_row.get(field) or "").strip()
                    if value:
                        grouped.setdefault(value, []).append(trade)
                for value in sorted(grouped):
                    trades = grouped[value]
                    output.append(
                        {
                            "context_field": field,
                            "context_value": value,
                            "timeout_sign": sign,
                            "count": len(trades),
                            "trade_share": rate(len(trades), len(selected)),
                            "mean_R": mean(numeric_values(trades, "R")),
                            "cumulative_R": sum(numeric_values(trades, "R")),
                            "mean_cost_R": mean(numeric_values(trades, "cost_R")),
                            "mean_net_R": mean(numeric_values(trades, "net_R")),
                            "mean_gross_R_proxy": mean(numeric_values(trades, "gross_R_proxy")),
                            "mean_value": "",
                            "median_value": "",
                        }
                    )

    negative_count = sum(1 for trade, _db_row in enriched_pairs if timeout_sign(trade) == "negative_timeout")
    if negative_count >= ROOT_CONTEXT_DOMINANCE_MIN_COUNT:
        best_field = ""
        best_value = ""
        best_share = 0.0
        for field in categorical_fields:
            grouped: dict[str, int] = {}
            for trade, db_row in enriched_pairs:
                if timeout_sign(trade) != "negative_timeout":
                    continue
                value = str(db_row.get(field) or "").strip()
                if value:
                    grouped[value] = grouped.get(value, 0) + 1
            for value, count in grouped.items():
                share = count / negative_count
                if share > best_share:
                    best_field = field
                    best_value = value
                    best_share = share
        if best_share >= ROOT_CONTEXT_DOMINANCE_REVIEW_SHARE:
            dominance = {
                "db_enrichment_context_dominance_field": best_field,
                "db_enrichment_context_dominance_value": best_value,
                "db_enrichment_context_dominance_share": best_share,
            }
    return output, dominance


def is_numeric_context_field(
    field: str,
    selected: list[tuple[dict[str, object], dict[str, object]]],
    numeric_context_fields: set[str],
) -> bool:
    if field in numeric_context_fields:
        return True
    return any(finite_float(db_row.get(field)) is not None for _trade, db_row in selected)


def build_summary(
    *,
    run_id: str,
    output_dir: Path,
    inputs: RootCauseInputs,
    timeout_rows: list[dict[str, object]],
    non_timeout_rows: list[dict[str, object]],
    sequence_rows: list[dict[str, object]],
    context_status: dict[str, object],
    db_path: Path | None,
) -> dict[str, object]:
    negative_timeout, positive_timeout = split_timeout_sign(timeout_rows)
    timeout_values = numeric_values(timeout_rows, "R")
    timeout_metrics = bucket_metrics(timeout_rows, len(timeout_rows))
    negative_metrics = bucket_metrics(negative_timeout, len(timeout_rows))
    positive_metrics = bucket_metrics(positive_timeout, len(timeout_rows))
    stress_values = [trade_r(row) for row in inputs.stress_trade_rows]
    stress_cumulative = finite_float(inputs.timeout_audit_summary.get("stress_cumulative_R"))
    if stress_cumulative is None:
        stress_cumulative = sum(stress_values)

    sequence_values = numeric_values(sequence_rows, "R")
    sequence_negative = [row for row in sequence_rows if trade_r(row) < 0]
    sequence_positive = [row for row in sequence_rows if trade_r(row) > 0]
    sequence_loss_abs = sum(abs(trade_r(row)) for row in sequence_negative)
    timeout_loss_abs = sum(abs(trade_r(row)) for row in negative_timeout)
    sequence_cumulative = sum(sequence_values) if sequence_values else finite_float(inputs.timeout_audit_summary.get("sequence_cumulative_R"))
    sequence_drawdown = max_drawdown(sequence_values) if sequence_values else finite_float(inputs.timeout_audit_summary.get("largest_timeout_drawdown_sequence_R"))
    first_sequence = sequence_rows[0] if sequence_rows else {}
    last_sequence = sequence_rows[-1] if sequence_rows else {}

    middle_row = next((row for row in inputs.timeout_audit_subperiods if row.get("subperiod") == "middle"), {})
    middle_cumulative = finite_float(middle_row.get("timeout_cumulative_R"))
    worst_hour = min(
        inputs.timeout_audit_entry_hour,
        key=lambda row: finite_float(row.get("timeout_cumulative_R")) or 0.0,
        default={},
    )
    worst_month = min(
        inputs.timeout_audit_monthly,
        key=lambda row: finite_float(row.get("timeout_cumulative_R")) or 0.0,
        default={},
    )
    cost_diff = None
    negative_mean_cost = finite_float(negative_metrics.get("mean_cost_R"))
    positive_mean_cost = finite_float(positive_metrics.get("mean_cost_R"))
    if negative_mean_cost is not None and positive_mean_cost is not None:
        cost_diff = negative_mean_cost - positive_mean_cost
    material_cost_threshold = max(ROOT_COST_ABSOLUTE_REVIEW_DIFF, (positive_mean_cost or 0.0) * ROOT_COST_RELATIVE_REVIEW_DIFF)

    return {
        "run_id": run_id,
        "timeout_audit_dir": str(inputs.timeout_audit_dir),
        "rule_replay_dir": str(inputs.rule_replay_dir),
        "controlled_expansion_dir": str(inputs.controlled_expansion_dir or ""),
        "db_path": str(db_path or ""),
        "root_cause_output_dir": str(output_dir),
        "final_timeout_root_cause_classification": "",
        "can_return_to_baseline_and_cost_sensitivity_review": False,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "symbol": inputs.timeout_audit_summary.get("symbol", inputs.rule_replay_summary.get("symbol", "")),
        "direction": inputs.timeout_audit_summary.get("direction", inputs.rule_replay_summary.get("direction", "")),
        "timeframe": inputs.timeout_audit_summary.get("timeframe", inputs.rule_replay_summary.get("timeframe", "")),
        "horizon": inputs.timeout_audit_summary.get("horizon", inputs.rule_replay_summary.get("horizon", "")),
        "target_family": inputs.timeout_audit_summary.get("target_family", inputs.rule_replay_summary.get("target_family", "")),
        "regime_column": inputs.timeout_audit_summary.get("regime_column", inputs.rule_replay_summary.get("regime_column", "")),
        "regime_value": inputs.timeout_audit_summary.get("regime_value", inputs.rule_replay_summary.get("regime_value", "")),
        "feature_condition": inputs.timeout_audit_summary.get("feature_condition", inputs.rule_replay_summary.get("feature_condition", "")),
        "tp_atr": inputs.timeout_audit_summary.get("tp_atr", inputs.rule_replay_summary.get("tp_atr", "")),
        "sl_atr": inputs.timeout_audit_summary.get("sl_atr", inputs.rule_replay_summary.get("sl_atr", "")),
        "same_bar_policy": inputs.timeout_audit_summary.get("same_bar_policy", inputs.rule_replay_summary.get("same_bar_policy", "")),
        "candidate_scope": inputs.timeout_audit_summary.get("candidate_scope", inputs.rule_replay_summary.get("candidate_scope", "")),
        "stress_spread_policy": inputs.timeout_audit_summary.get("stress_spread_policy", inputs.rule_replay_summary.get("stress_spread_policy", "")),
        "input_timeout_audit_classification": inputs.timeout_audit_summary.get("final_timeout_audit_classification", ""),
        "input_timeout_audit_warnings_count": inputs.timeout_audit_summary.get("warnings_count", ""),
        "input_timeout_audit_blocking_warnings_count": inputs.timeout_audit_summary.get("blocking_warnings_count", ""),
        "input_rule_replay_classification": inputs.rule_replay_summary.get("final_rule_replay_classification", ""),
        "stress_trades_count": len(inputs.stress_trade_rows),
        "stress_cumulative_R": stress_cumulative,
        "timeout_count": len(timeout_rows),
        "timeout_cumulative_R": timeout_metrics["cumulative_R"],
        "timeout_mean_R": timeout_metrics["mean_R"],
        "timeout_median_R": timeout_metrics["median_R"],
        "timeout_negative_count": len(negative_timeout),
        "timeout_positive_count": len(positive_timeout),
        "timeout_negative_share": rate(len(negative_timeout), len(timeout_rows)),
        "timeout_total_loss_R": -timeout_loss_abs,
        "timeout_total_gain_R": sum(value for value in timeout_values if value > 0),
        "timeout_profit_factor_R": profit_factor(timeout_values),
        "timeout_largest_loss_R": min(timeout_values) if timeout_values else None,
        "timeout_largest_gain_R": max(timeout_values) if timeout_values else None,
        "timeout_loss_concentration_top_5_pct": loss_concentration_pct(timeout_rows, 0.05),
        "timeout_loss_concentration_top_10_pct": loss_concentration_pct(timeout_rows, 0.10),
        "timeout_loss_ratio_of_stress_cumulative_R": (
            abs(sum(timeout_values)) / stress_cumulative if stress_cumulative and sum(timeout_values) < 0 else 0.0
        ),
        "largest_timeout_drawdown_sequence_start_trade_index": (
            sequence_rows[0].get("_timeout_trade_index", "") if sequence_rows else ""
        ),
        "largest_timeout_drawdown_sequence_end_trade_index": (
            sequence_rows[-1].get("_timeout_trade_index", "") if sequence_rows else ""
        ),
        "sequence_timeout_count": len(sequence_rows),
        "sequence_cumulative_R": sequence_cumulative,
        "sequence_max_drawdown_R": sequence_drawdown,
        "sequence_max_drawdown_ratio_of_stress_cumulative_R": (
            sequence_drawdown / stress_cumulative if sequence_drawdown is not None and stress_cumulative and stress_cumulative > 0 else None
        ),
        "sequence_start_time": first_sequence.get("entry_time", ""),
        "sequence_end_time": last_sequence.get("entry_time", ""),
        "sequence_years": compact_distribution(sequence_rows, "_year"),
        "sequence_months": compact_distribution(sequence_rows, "_month"),
        "sequence_entry_hours": compact_distribution(sequence_rows, "_entry_hour"),
        "sequence_negative_timeout_count": len(sequence_negative),
        "sequence_positive_timeout_count": len(sequence_positive),
        "sequence_share_of_total_timeout_loss": (
            sequence_loss_abs / timeout_loss_abs * 100.0 if timeout_loss_abs > 0 else None
        ),
        "negative_timeout_mean_R": negative_metrics["mean_R"],
        "positive_timeout_mean_R": positive_metrics["mean_R"],
        "negative_timeout_mean_cost_R": negative_metrics["mean_cost_R"],
        "positive_timeout_mean_cost_R": positive_metrics["mean_cost_R"],
        "negative_timeout_mean_net_R": negative_metrics["mean_net_R"],
        "positive_timeout_mean_net_R": positive_metrics["mean_net_R"],
        "negative_timeout_mean_gross_R_proxy": negative_metrics["mean_gross_R_proxy"],
        "positive_timeout_mean_gross_R_proxy": positive_metrics["mean_gross_R_proxy"],
        "negative_timeout_mean_bars_held": negative_metrics["mean_bars_held"],
        "positive_timeout_mean_bars_held": positive_metrics["mean_bars_held"],
        "cost_R_difference_negative_vs_positive_timeout": cost_diff,
        "negative_timeout_cost_materially_higher": bool(cost_diff is not None and cost_diff > material_cost_threshold),
        "middle_subperiod_timeout_cumulative_R": middle_cumulative,
        "middle_subperiod_loss_ratio_of_stress_cumulative_R": (
            abs(middle_cumulative) / stress_cumulative if middle_cumulative is not None and middle_cumulative < 0 and stress_cumulative and stress_cumulative > 0 else 0.0
        ),
        "worst_entry_hour": worst_hour.get("entry_hour", ""),
        "worst_entry_hour_timeout_cumulative_R": worst_hour.get("timeout_cumulative_R", ""),
        "worst_entry_hour_loss_ratio_of_stress_cumulative_R": (
            abs(finite_float(worst_hour.get("timeout_cumulative_R")) or 0.0) / stress_cumulative
            if (finite_float(worst_hour.get("timeout_cumulative_R")) or 0.0) < 0 and stress_cumulative and stress_cumulative > 0
            else 0.0
        ),
        "worst_month": worst_month.get("period", ""),
        "worst_month_timeout_cumulative_R": worst_month.get("timeout_cumulative_R", ""),
        "worst_month_loss_ratio_of_stress_cumulative_R": (
            abs(finite_float(worst_month.get("timeout_cumulative_R")) or 0.0) / stress_cumulative
            if (finite_float(worst_month.get("timeout_cumulative_R")) or 0.0) < 0 and stress_cumulative and stress_cumulative > 0
            else 0.0
        ),
        "db_enrichment_requested": db_path is not None,
        "db_enrichment_available": bool(context_status.get("available")),
        "db_enrichment_rows_matched": context_status.get("matched_rows", 0),
        "db_enrichment_context_dominance_field": context_status.get("db_enrichment_context_dominance_field", ""),
        "db_enrichment_context_dominance_value": context_status.get("db_enrichment_context_dominance_value", ""),
        "db_enrichment_context_dominance_share": context_status.get("db_enrichment_context_dominance_share", ""),
    }


def next_review_plan_rows(classification: str, warnings: list[dict[str, object]]) -> list[dict[str, object]]:
    forbidden = forbidden_actions_text()
    if classification == CLEARED_LABEL:
        return [
            next_action_row(
                action_type="controlled_baseline_and_cost_sensitivity_review",
                status="ready_for_research_review",
                message="Timeout root-cause review did not find blocking or material review-level fragility.",
                forbidden_actions=forbidden,
                plan_item="controlled_baseline_and_cost_sensitivity_review",
                rationale="Timeout root-cause review did not find blocking or material review-level fragility.",
            )
        ]
    if classification == FAILED_LABEL:
        return [
            next_action_row(
                action_type="stop_baseline_and_cost_sensitivity_review",
                status="blocked",
                message="Timeout root-cause review found blocking timeout evidence under current assumptions.",
                forbidden_actions=forbidden,
                plan_item="stop_baseline_and_cost_sensitivity_review",
                rationale="Timeout root-cause review found blocking timeout evidence under current assumptions.",
            )
        ]
    warning_codes = ";".join(str(warning.get("warning_code")) for warning in warnings if str(warning.get("severity")) == "review")
    return [
        next_action_row(
            action_type="sequence_calendar_cluster_review",
            status="continue_timeout_review",
            message=f"Review-level warnings remain: {warning_codes or 'timeout root-cause evidence remains material'}.",
            forbidden_actions=forbidden,
            plan_item="sequence_calendar_cluster_review",
            rationale=f"Review-level warnings remain: {warning_codes or 'timeout root-cause evidence remains material'}.",
        ),
        next_action_row(
            action_type="baseline_and_cost_sensitivity_review",
            status="deferred",
            message="Baseline and cost-sensitivity expansion should wait until timeout concentration is explained.",
            forbidden_actions=forbidden,
            plan_item="baseline_and_cost_sensitivity_review",
            rationale="Baseline and cost-sensitivity expansion should wait until timeout concentration is explained.",
        ),
    ]


def table_lines(rows: list[dict[str, object]], columns: list[str], limit: int | None = None) -> list[str]:
    selected = rows[:limit] if limit is not None else rows
    if not selected:
        return ["No rows available."]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in selected:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return lines


def report_text(
    *,
    summary: dict[str, object],
    warnings: list[dict[str, object]],
    largest_sequence_rows: list[dict[str, object]],
    positive_vs_negative_rows_for_report: list[dict[str, object]],
    year_month_rows: list[dict[str, object]],
    entry_hour_rows_for_report: list[dict[str, object]],
    cost_rows: list[dict[str, object]],
    feature_context_rows_for_report: list[dict[str, object]],
    plan_rows: list[dict[str, object]],
) -> str:
    warning_lines = [
        f"- {warning['severity']} `{warning['warning_code']}`: {warning['message']}"
        for warning in warnings
    ] or ["No warnings."]
    next_action = next_action_for_classification(str(summary.get("final_timeout_root_cause_classification") or ""))
    return "\n".join(
        [
            "# Timeout Root-Cause Review",
            "",
            "## Research-Only Warning",
            "",
            "This review reads existing timeout audit and rule-replay outputs only. Optional database enrichment is read-only and diagnostic. It does not rerun replay, recompute entries, add filters, change candidate assumptions, optimize TP/SL settings, or provide operational instructions.",
            "",
            "## Candidate Definition",
            "",
            f"- Symbol: `{summary.get('symbol')}`",
            f"- Direction: `{summary.get('direction')}`",
            f"- Timeframe: `{summary.get('timeframe')}`",
            f"- Horizon: `{summary.get('horizon')}`",
            f"- Target family: `{summary.get('target_family')}`",
            f"- Regime: `{summary.get('regime_column')}={summary.get('regime_value')}`",
            f"- Feature condition: `{summary.get('feature_condition')}`",
            f"- TP/SL ATR: `{summary.get('tp_atr')}` / `{summary.get('sl_atr')}`",
            f"- Same-bar policy: `{summary.get('same_bar_policy')}`",
            f"- Candidate scope: `{summary.get('candidate_scope')}`",
            "",
            "## Input Sources",
            "",
            f"- Timeout audit dir: `{summary.get('timeout_audit_dir')}`",
            f"- Rule replay dir: `{summary.get('rule_replay_dir')}`",
            f"- Controlled expansion dir: `{summary.get('controlled_expansion_dir')}`",
            f"- DB path: `{summary.get('db_path')}`",
            "",
            "## Prior Timeout Audit State",
            "",
            f"- Input timeout audit classification: `{summary.get('input_timeout_audit_classification')}`",
            f"- Input timeout audit warnings/blocking warnings: `{summary.get('input_timeout_audit_warnings_count')}` / `{summary.get('input_timeout_audit_blocking_warnings_count')}`",
            f"- Rule replay classification: `{summary.get('input_rule_replay_classification')}`",
            "",
            "## Overall Timeout Root-Cause Summary",
            "",
            f"- Stress trades / stress cumulative_R: `{summary.get('stress_trades_count')}` / `{summary.get('stress_cumulative_R')}`",
            f"- Timeout count / cumulative_R / mean_R / median_R: `{summary.get('timeout_count')}` / `{summary.get('timeout_cumulative_R')}` / `{summary.get('timeout_mean_R')}` / `{summary.get('timeout_median_R')}`",
            f"- Negative/positive timeout count: `{summary.get('timeout_negative_count')}` / `{summary.get('timeout_positive_count')}`",
            f"- Timeout total loss_R / gain_R / PF: `{summary.get('timeout_total_loss_R')}` / `{summary.get('timeout_total_gain_R')}` / `{summary.get('timeout_profit_factor_R')}`",
            f"- Largest timeout loss/gain R: `{summary.get('timeout_largest_loss_R')}` / `{summary.get('timeout_largest_gain_R')}`",
            f"- Timeout loss concentration top 5/10 pct: `{summary.get('timeout_loss_concentration_top_5_pct')}` / `{summary.get('timeout_loss_concentration_top_10_pct')}`",
            "",
            "## Largest Timeout Drawdown Sequence",
            "",
            f"- Timeout index range: `{summary.get('largest_timeout_drawdown_sequence_start_trade_index')}` to `{summary.get('largest_timeout_drawdown_sequence_end_trade_index')}`",
            f"- Count / cumulative_R / max_drawdown_R: `{summary.get('sequence_timeout_count')}` / `{summary.get('sequence_cumulative_R')}` / `{summary.get('sequence_max_drawdown_R')}`",
            f"- Years: `{summary.get('sequence_years')}`",
            f"- Months: `{summary.get('sequence_months')}`",
            f"- Entry hours: `{summary.get('sequence_entry_hours')}`",
            f"- Sequence share of total timeout loss: `{summary.get('sequence_share_of_total_timeout_loss')}`",
            "",
            *table_lines(largest_sequence_rows, ["timeout_trade_index", "entry_time", "R", "cost_R", "net_R", "gross_R_proxy", "month"], limit=15),
            "",
            "## Negative Vs Positive Timeout Comparison",
            "",
            *table_lines(positive_vs_negative_rows_for_report, ["bucket", "count", "mean_R", "cumulative_R", "mean_cost_R", "mean_net_R", "mean_gross_R_proxy", "mean_bars_held"]),
            "",
            "## Cost Profile And Gross_R Proxy Interpretation",
            "",
            "When `cost_R` is available, `gross_R_proxy` is calculated as `R + cost_R` for diagnostic comparison only.",
            "",
            *table_lines(cost_rows, ["bucket", "count", "mean_cost_R", "median_cost_R", "mean_R", "mean_gross_R_proxy", "cost_R_difference_vs_positive_timeout"]),
            "",
            "## Calendar Concentration: Year/Month/Subperiod",
            "",
            f"- Middle subperiod timeout cumulative_R: `{summary.get('middle_subperiod_timeout_cumulative_R')}`",
            f"- Worst month / timeout cumulative_R: `{summary.get('worst_month')}` / `{summary.get('worst_month_timeout_cumulative_R')}`",
            "",
            *table_lines(year_month_rows, ["breakdown_type", "period", "bucket", "count", "mean_R", "cumulative_R"], limit=18),
            "",
            "## Entry-Hour Timeout Behavior",
            "",
            f"- Worst entry hour / timeout cumulative_R: `{summary.get('worst_entry_hour')}` / `{summary.get('worst_entry_hour_timeout_cumulative_R')}`",
            "",
            *table_lines(entry_hour_rows_for_report, ["period", "bucket", "count", "mean_R", "cumulative_R"], limit=18),
            "",
            "## Optional DB Feature/Regime Context Enrichment",
            "",
            f"- Requested / available / rows matched: `{summary.get('db_enrichment_requested')}` / `{summary.get('db_enrichment_available')}` / `{summary.get('db_enrichment_rows_matched')}`",
            f"- Dominant negative-timeout context: `{summary.get('db_enrichment_context_dominance_field')}`=`{summary.get('db_enrichment_context_dominance_value')}` share `{summary.get('db_enrichment_context_dominance_share')}`",
            "",
            *table_lines(feature_context_rows_for_report, ["context_field", "context_value", "timeout_sign", "count", "mean_R", "mean_value"], limit=18),
            "",
            "## Root-Cause Interpretation",
            "",
            interpretation_text(str(summary.get("final_timeout_root_cause_classification") or "")),
            "",
            "## Warnings",
            "",
            *warning_lines,
            "",
            "## Final Timeout Root-Cause Classification",
            "",
            f"`{summary.get('final_timeout_root_cause_classification')}`",
            "",
            "## Explicit Next Action",
            "",
            next_action,
            "",
            "## Next Review Plan",
            "",
            *table_lines(plan_rows, ["plan_item", "status", "rationale"]),
            "",
        ]
    )


def interpretation_text(classification: str) -> str:
    if classification == CLEARED_LABEL:
        return "Timeout root-cause evidence is bounded under the current research thresholds and does not block the next controlled review step."
    if classification == RETAINED_LABEL:
        return "Timeout root-cause evidence is not catastrophic, but concentration, sequence, cost, or context differences remain material."
    return "Timeout root-cause evidence crosses one or more blocking thresholds under the current research evidence."


def build_timeout_root_cause_review(args: argparse.Namespace) -> dict[str, Path]:
    timeout_audit_dir = Path(args.timeout_audit_dir)
    run_id = str(args.run_id or timeout_audit_dir.name).strip()
    if not run_id:
        raise ValueError("--run-id is required when --timeout-audit-dir has no final path name")
    paths = output_paths(Path(args.output_root), run_id)
    ensure_can_write(paths, bool(args.overwrite))
    inputs = load_inputs(
        timeout_audit_dir,
        Path(args.rule_replay_dir),
        Path(args.controlled_expansion_dir) if args.controlled_expansion_dir else None,
    )

    annotated_rows = annotated_stress_rows(inputs.stress_trade_rows)
    timeout_rows = timeout_rows_from_annotated(annotated_rows)
    non_timeout_rows = [row for row in annotated_rows if not is_timeout(row)]
    sequence_rows = largest_sequence_trades(timeout_rows, inputs.timeout_audit_sequences)
    largest_sequence_indexes = {int_value(row.get("_timeout_trade_index")) for row in sequence_rows}

    warnings: list[dict[str, object]] = []
    add_input_warnings(inputs, warnings)
    symbol = str(inputs.timeout_audit_summary.get("symbol") or inputs.rule_replay_summary.get("symbol") or "").strip().upper()
    timeframe = str(inputs.timeout_audit_summary.get("timeframe") or inputs.rule_replay_summary.get("timeframe") or "").strip().upper()
    _db_rows, feature_context, context_status = load_db_enrichment(
        Path(args.db_path) if args.db_path else None,
        symbol=symbol,
        timeframe=timeframe,
        feature_condition=str(inputs.timeout_audit_summary.get("feature_condition") or inputs.rule_replay_summary.get("feature_condition") or ""),
        timeout_rows=timeout_rows,
        warnings=warnings,
    )

    summary = build_summary(
        run_id=run_id,
        output_dir=paths["output_dir"],
        inputs=inputs,
        timeout_rows=timeout_rows,
        non_timeout_rows=non_timeout_rows,
        sequence_rows=sequence_rows,
        context_status=context_status,
        db_path=Path(args.db_path) if args.db_path else None,
    )
    missing_metadata = missing_candidate_metadata(summary)
    if missing_metadata:
        add_warning(
            warnings,
            warning_code="candidate_metadata_missing",
            severity="review",
            blocking=False,
            message="Candidate metadata is missing required field(s): " + ", ".join(missing_metadata),
            related_metric="candidate_metadata",
            metric_value=",".join(missing_metadata),
            threshold="all required metadata fields populated",
        )
    add_root_cause_warnings(summary, warnings)
    classification = classify_root_cause(summary, warnings)
    blocking_count = sum(1 for warning in warnings if bool_value(warning.get("blocking")))
    summary.update(
        {
            "final_timeout_root_cause_classification": classification,
            "can_return_to_baseline_and_cost_sensitivity_review": classification == CLEARED_LABEL,
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_count,
        }
    )
    add_common_summary_fields(
        summary,
        decision_scope="timeout_root_cause",
        final_classification=classification,
        next_action=next_action_for_classification(classification),
    )

    largest_sequence_output = trade_output_rows(sequence_rows, largest_sequence_indexes)
    negative_timeout_output = trade_output_rows([row for row in timeout_rows if trade_r(row) < 0], largest_sequence_indexes)
    positive_vs_negative = positive_vs_negative_rows(timeout_rows)
    year_month = [
        *breakdown_rows(timeout_rows, "_year", "year"),
        *breakdown_rows(timeout_rows, "_month", "month"),
    ]
    entry_hour = breakdown_rows(timeout_rows, "_entry_hour", "entry_hour")
    cost_profile = cost_profile_rows(timeout_rows, non_timeout_rows)
    plan_rows = next_review_plan_rows(classification, warnings)

    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_csv(paths["summary"], [summary], SUMMARY_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["largest_sequence_trades"], largest_sequence_output, TRADE_OUTPUT_FIELDNAMES)
    write_csv(paths["negative_timeout_trades"], negative_timeout_output, TRADE_OUTPUT_FIELDNAMES)
    write_csv(paths["positive_vs_negative"], positive_vs_negative, BUCKET_FIELDNAMES)
    write_csv(paths["year_month_breakdown"], year_month, BREAKDOWN_FIELDNAMES)
    write_csv(paths["entry_hour_breakdown"], entry_hour, BREAKDOWN_FIELDNAMES)
    write_csv(paths["cost_profile"], cost_profile, COST_PROFILE_FIELDNAMES)
    if feature_context:
        write_csv(paths["feature_context"], feature_context, FEATURE_CONTEXT_FIELDNAMES)
    write_csv(paths["next_review_plan"], plan_rows, PLAN_FIELDNAMES)
    paths["report"].write_text(
        report_text(
            summary=summary,
            warnings=warnings,
            largest_sequence_rows=largest_sequence_output,
            positive_vs_negative_rows_for_report=positive_vs_negative,
            year_month_rows=year_month,
            entry_hour_rows_for_report=entry_hour,
            cost_rows=cost_profile,
            feature_context_rows_for_report=feature_context,
            plan_rows=plan_rows,
        ),
        encoding="utf-8",
    )
    return paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        paths = build_timeout_root_cause_review(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Timeout root-cause review written to {paths['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
