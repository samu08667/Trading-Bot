"""Build a focused timeout sequence drilldown from existing research outputs.

This script reads an existing timeout root-cause review, timeout audit, and
rule-replay trade logs. It analyzes the largest TIMEOUT drawdown sequence in
detail without rerunning replay, recomputing entries, changing TP/SL settings,
adding filters, or changing candidate assumptions.
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
        add_common_summary_fields,
        forbidden_actions_text,
        next_action_row,
        warning_row,
        with_common_next_action_fields,
        with_common_summary_fields,
        with_common_warning_fields,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "timeout_sequence_drilldown_review"

ROOT_SUMMARY_FILE = "timeout_root_cause_summary.csv"
ROOT_LARGEST_SEQUENCE_FILE = "timeout_root_cause_largest_sequence_trades.csv"
ROOT_NEGATIVE_TIMEOUT_FILE = "timeout_root_cause_negative_timeout_trades.csv"
ROOT_POSITIVE_NEGATIVE_FILE = "timeout_root_cause_positive_vs_negative_timeout.csv"
ROOT_FEATURE_CONTEXT_FILE = "timeout_root_cause_feature_context.csv"
ROOT_WARNINGS_FILE = "timeout_root_cause_warnings.csv"

AUDIT_SEQUENCES_FILE = "timeout_fragility_audit_sequences.csv"
AUDIT_MONTHLY_FILE = "timeout_fragility_audit_monthly.csv"
AUDIT_YEARLY_FILE = "timeout_fragility_audit_yearly.csv"
AUDIT_ENTRY_HOUR_FILE = "timeout_fragility_audit_entry_hour.csv"

REPLAY_STRESS_TRADE_LOG_FILE = "rule_based_trade_log_stress.csv"
REPLAY_BASE_TRADE_LOG_FILE = "rule_based_trade_log_base.csv"
REPLAY_SUMMARY_FILE = "rule_based_backtest_summary.csv"

SUMMARY_FILE = "timeout_sequence_drilldown_summary.csv"
REPORT_FILE = "timeout_sequence_drilldown_report.md"
WARNINGS_FILE = "timeout_sequence_drilldown_warnings.csv"
TRADES_FILE = "timeout_sequence_drilldown_trades.csv"
CALENDAR_FILE = "timeout_sequence_drilldown_calendar.csv"
ENTRY_HOUR_FILE = "timeout_sequence_drilldown_entry_hour.csv"
COST_PROFILE_FILE = "timeout_sequence_drilldown_cost_profile.csv"
FEATURE_CONTEXT_FILE = "timeout_sequence_drilldown_feature_context.csv"
NEXT_ACTION_FILE = "timeout_sequence_drilldown_next_action.csv"

ROOT_CLEARED_LABEL = "TIMEOUT_ROOT_CAUSE_CLEARED"
ROOT_RETAINED_LABEL = "TIMEOUT_ROOT_CAUSE_RETAINED_FOR_REVIEW"
ROOT_FAILED_LABEL = "TIMEOUT_ROOT_CAUSE_FAILED"
ALLOWED_ROOT_LABELS = {ROOT_CLEARED_LABEL, ROOT_RETAINED_LABEL}

CLEARED_LABEL = "TIMEOUT_SEQUENCE_CLEARED"
RETAINED_LABEL = "TIMEOUT_SEQUENCE_RETAINED_FOR_REVIEW"
FAILED_LABEL = "TIMEOUT_SEQUENCE_FAILED"

SEQUENCE_FAIL_STRESS_RATIO = 0.10
SEQUENCE_REVIEW_STRESS_RATIO = 0.05
SEQUENCE_CLEARED_STRESS_RATIO = 0.025
SEQUENCE_LOSS_CONCENTRATION_REVIEW_PCT = 50.0
SEQUENCE_SHARE_TIMEOUT_LOSS_REVIEW_PCT = 75.0
SEQUENCE_CALENDAR_BROAD_YEAR_COUNT = 4
SEQUENCE_ENTRY_HOUR_SHARE_REVIEW = 0.70
SEQUENCE_COST_PRIMARY_SHARE = 0.50
SEQUENCE_CONTEXT_CONCENTRATION_SHARE = 0.70
SEQUENCE_CONTEXT_MIN_COUNT = 5

BASE_DB_ENRICHMENT_FIELDS = [
    "spread",
    "atr_20",
    "range_regime",
    "volatility_regime",
    "volume_liquidity_regime",
    "spread_liquidity_regime",
    "session",
    "hour",
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
    "timeout_root_cause_dir",
    "timeout_audit_dir",
    "rule_replay_dir",
    "db_path",
    "drilldown_output_dir",
    "final_timeout_sequence_classification",
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
    "input_timeout_root_cause_classification",
    "input_timeout_root_cause_warnings_count",
    "input_timeout_root_cause_blocking_warnings_count",
    "input_rule_replay_classification",
    "stress_trades_count",
    "stress_cumulative_R",
    "all_timeout_count",
    "all_timeout_cumulative_R",
    "sequence_start_timeout_index",
    "sequence_end_timeout_index",
    "sequence_trade_count",
    "sequence_cumulative_R",
    "sequence_mean_R",
    "sequence_median_R",
    "sequence_max_drawdown_R",
    "sequence_loss_R",
    "sequence_gain_R",
    "sequence_profit_factor_R",
    "sequence_negative_trade_count",
    "sequence_positive_trade_count",
    "sequence_negative_share",
    "sequence_worst_trade_R",
    "sequence_best_trade_R",
    "sequence_loss_concentration_top_5_pct",
    "sequence_loss_concentration_top_10_pct",
    "sequence_calendar_span_days",
    "sequence_years_distribution",
    "sequence_months_distribution",
    "sequence_entry_hour_distribution",
    "sequence_dominant_entry_hour",
    "sequence_dominant_entry_hour_share",
    "sequence_mean_cost_R",
    "sequence_median_cost_R",
    "sequence_mean_net_R",
    "sequence_median_net_R",
    "sequence_mean_gross_R_proxy",
    "sequence_median_gross_R_proxy",
    "sequence_negative_timeout_mean_cost_R",
    "sequence_positive_timeout_mean_cost_R",
    "sequence_negative_timeout_mean_gross_R_proxy",
    "sequence_positive_timeout_mean_gross_R_proxy",
    "sequence_share_of_total_timeout_loss",
    "sequence_share_of_total_stress_cumulative_R",
    "sequence_cost_share_of_abs_loss",
    "sequence_cost_primary_driver",
    "sequence_vs_all_timeout_mean_R_delta",
    "sequence_negative_vs_non_sequence_negative_mean_R_delta",
    "sequence_positive_vs_non_sequence_positive_mean_R_delta",
    "db_enrichment_requested",
    "db_enrichment_available",
    "db_enrichment_rows_matched",
    "db_context_concentration_field",
    "db_context_concentration_value",
    "db_context_concentration_share",
]
SUMMARY_FIELDNAMES = with_common_summary_fields(SUMMARY_FIELDNAMES)

TRADE_FIELDNAMES = [
    "stress_trade_index",
    "timeout_trade_index",
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
    "loss_rank",
    "running_sequence_R",
    "running_sequence_drawdown_R",
]

BREAKDOWN_FIELDNAMES = [
    "breakdown_type",
    "bucket",
    "period",
    "count",
    "share_of_sequence",
    "mean_R",
    "median_R",
    "cumulative_R",
    "mean_cost_R",
    "cumulative_cost_R",
    "mean_gross_R_proxy",
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
    "mean_bars_held",
    "median_bars_held",
]

FEATURE_CONTEXT_FIELDNAMES = [
    "context_field",
    "context_value",
    "sequence_bucket",
    "count",
    "trade_share",
    "mean_R",
    "cumulative_R",
    "mean_cost_R",
    "mean_gross_R_proxy",
    "mean_value",
    "median_value",
]

NEXT_ACTION_FIELDNAMES = with_common_next_action_fields(["plan_item", "status", "rationale"])


@dataclass(frozen=True)
class DrilldownInputs:
    timeout_root_cause_dir: Path
    root_summary: dict[str, str]
    root_largest_sequence: list[dict[str, str]]
    root_negative_timeout: list[dict[str, str]]
    root_positive_negative: list[dict[str, str]]
    root_feature_context: list[dict[str, str]]
    root_warnings: list[dict[str, str]]
    timeout_audit_dir: Path
    audit_sequences: list[dict[str, str]]
    audit_monthly: list[dict[str, str]]
    audit_yearly: list[dict[str, str]]
    audit_entry_hour: list[dict[str, str]]
    rule_replay_dir: Path
    stress_trade_rows: list[dict[str, str]]
    base_trade_rows: list[dict[str, str]]
    replay_summary: dict[str, str]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only drilldown for the largest timeout drawdown sequence."
    )
    parser.add_argument("--timeout-root-cause-dir", required=True, type=Path)
    parser.add_argument("--timeout-audit-dir", required=True, type=Path)
    parser.add_argument("--rule-replay-dir", required=True, type=Path)
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


def trade_r(row: dict[str, object]) -> float:
    return finite_float(row.get("R")) or 0.0


def cost_r(row: dict[str, object]) -> float | None:
    return finite_float(row.get("cost_R"))


def net_r(row: dict[str, object]) -> float | None:
    return finite_float(row.get("net_R"))


def bars_held(row: dict[str, object]) -> float | None:
    return finite_float(row.get("bars_held"))


def gross_R_proxy(row: dict[str, object]) -> float | None:
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


def row_timestamp(row: dict[str, object], *, prefer_exit: bool) -> datetime | None:
    primary = "exit_time" if prefer_exit else "entry_time"
    fallback = "entry_time" if prefer_exit else "exit_time"
    return parse_timestamp(row.get(primary)) or parse_timestamp(row.get(fallback))


def normalize_exit_reason(row: dict[str, object]) -> str:
    reason = str(row.get("exit_reason") or "OTHER").strip().upper()
    return reason or "OTHER"


def is_timeout(row: dict[str, object]) -> bool:
    return normalize_exit_reason(row) == "TIMEOUT"


def rate(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return count / total


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "output_dir": output_dir,
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "trades": output_dir / TRADES_FILE,
        "calendar": output_dir / CALENDAR_FILE,
        "entry_hour": output_dir / ENTRY_HOUR_FILE,
        "cost_profile": output_dir / COST_PROFILE_FILE,
        "feature_context": output_dir / FEATURE_CONTEXT_FILE,
        "next_action": output_dir / NEXT_ACTION_FILE,
    }


def ensure_can_write(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for key, path in paths.items() if key != "output_dir" and path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Timeout sequence drilldown outputs already exist; pass --overwrite to replace: {joined}")


def load_inputs(timeout_root_cause_dir: Path, timeout_audit_dir: Path, rule_replay_dir: Path) -> DrilldownInputs:
    if not timeout_root_cause_dir.exists():
        raise FileNotFoundError(f"Timeout root-cause directory does not exist: {timeout_root_cause_dir}")
    if not timeout_audit_dir.exists():
        raise FileNotFoundError(f"Timeout audit directory does not exist: {timeout_audit_dir}")
    if not rule_replay_dir.exists():
        raise FileNotFoundError(f"Rule replay directory does not exist: {rule_replay_dir}")
    for filename in (
        ROOT_SUMMARY_FILE,
        ROOT_LARGEST_SEQUENCE_FILE,
        ROOT_NEGATIVE_TIMEOUT_FILE,
        ROOT_POSITIVE_NEGATIVE_FILE,
        ROOT_WARNINGS_FILE,
    ):
        path = timeout_root_cause_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required input file: {path}")
    for filename in (AUDIT_SEQUENCES_FILE, AUDIT_MONTHLY_FILE, AUDIT_YEARLY_FILE, AUDIT_ENTRY_HOUR_FILE):
        path = timeout_audit_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required input file: {path}")
    for filename in (REPLAY_STRESS_TRADE_LOG_FILE, REPLAY_BASE_TRADE_LOG_FILE, REPLAY_SUMMARY_FILE):
        path = rule_replay_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required input file: {path}")
    feature_context_path = timeout_root_cause_dir / ROOT_FEATURE_CONTEXT_FILE
    return DrilldownInputs(
        timeout_root_cause_dir=timeout_root_cause_dir,
        root_summary=first_csv_row(timeout_root_cause_dir / ROOT_SUMMARY_FILE),
        root_largest_sequence=read_csv_rows(timeout_root_cause_dir / ROOT_LARGEST_SEQUENCE_FILE),
        root_negative_timeout=read_csv_rows(timeout_root_cause_dir / ROOT_NEGATIVE_TIMEOUT_FILE),
        root_positive_negative=read_csv_rows(timeout_root_cause_dir / ROOT_POSITIVE_NEGATIVE_FILE),
        root_feature_context=read_csv_rows(feature_context_path) if feature_context_path.exists() else [],
        root_warnings=read_csv_rows(timeout_root_cause_dir / ROOT_WARNINGS_FILE),
        timeout_audit_dir=timeout_audit_dir,
        audit_sequences=read_csv_rows(timeout_audit_dir / AUDIT_SEQUENCES_FILE),
        audit_monthly=read_csv_rows(timeout_audit_dir / AUDIT_MONTHLY_FILE),
        audit_yearly=read_csv_rows(timeout_audit_dir / AUDIT_YEARLY_FILE),
        audit_entry_hour=read_csv_rows(timeout_audit_dir / AUDIT_ENTRY_HOUR_FILE),
        rule_replay_dir=rule_replay_dir,
        stress_trade_rows=read_csv_rows(rule_replay_dir / REPLAY_STRESS_TRADE_LOG_FILE),
        base_trade_rows=read_csv_rows(rule_replay_dir / REPLAY_BASE_TRADE_LOG_FILE),
        replay_summary=first_csv_row(rule_replay_dir / REPLAY_SUMMARY_FILE),
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
            related_stage="timeout_sequence",
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
        timeout_row = is_timeout(row)
        if timeout_row:
            timeout_index += 1
        timestamp = row_timestamp(row, prefer_exit=False)
        output.append(
            {
                **row,
                "_stress_trade_index": stress_index,
                "_timeout_trade_index": timeout_index if timeout_row else "",
                "_entry_hour": timestamp.hour if timestamp else "",
                "_year": timestamp.year if timestamp else "",
                "_month": f"{timestamp.year:04d}-{timestamp.month:02d}" if timestamp else "",
            }
        )
    return output


def timeout_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if is_timeout(row)]


def sequence_range_from_inputs(inputs: DrilldownInputs) -> tuple[int, int]:
    indexes = [int_value(row.get("timeout_trade_index")) for row in inputs.root_largest_sequence]
    indexes = [index for index in indexes if index > 0]
    if indexes:
        return min(indexes), max(indexes)
    sequence_row = next((row for row in inputs.audit_sequences if row.get("diagnostic_type") == "largest_timeout_drawdown_sequence"), {})
    return int_value(sequence_row.get("start_trade_index")), int_value(sequence_row.get("end_trade_index"))


def sequence_timeout_rows(all_timeouts: list[dict[str, object]], start: int, end: int) -> list[dict[str, object]]:
    if start <= 0 or end < start:
        return []
    return [row for row in all_timeouts if start <= int_value(row.get("_timeout_trade_index")) <= end]


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


def bucket_metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    values = numeric_values(rows, "R")
    costs = numeric_values(rows, "cost_R")
    nets = numeric_values(rows, "net_R")
    gross = numeric_values(rows, "gross_R_proxy")
    held = numeric_values(rows, "bars_held")
    return {
        "count": len(rows),
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
    }


def distribution(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "").strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts


def distribution_text(rows: list[dict[str, object]], key: str) -> str:
    return ";".join(f"{value}:{count}" for value, count in sorted(distribution(rows, key).items()))


def dominant_distribution(rows: list[dict[str, object]], key: str) -> tuple[str, float | None]:
    counts = distribution(rows, key)
    if not counts:
        return "", None
    value, count = max(counts.items(), key=lambda item: (item[1], item[0]))
    return value, count / len(rows) if rows else None


def trade_output_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    negative_sorted = sorted([row for row in rows if trade_r(row) < 0], key=lambda row: trade_r(row))
    ranks = {int_value(row.get("_timeout_trade_index")): index for index, row in enumerate(negative_sorted, start=1)}
    output: list[dict[str, object]] = []
    running = 0.0
    peak = 0.0
    for row in rows:
        running += trade_r(row)
        peak = max(peak, running)
        output.append(
            {
                "stress_trade_index": row.get("_stress_trade_index", ""),
                "timeout_trade_index": row.get("_timeout_trade_index", ""),
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
                "loss_rank": ranks.get(int_value(row.get("_timeout_trade_index")), ""),
                "running_sequence_R": running,
                "running_sequence_drawdown_R": peak - running,
            }
        )
    return output


def breakdown_rows(rows: list[dict[str, object]], key: str, breakdown_type: str) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    buckets = {
        "sequence_all": rows,
        "sequence_negative": [row for row in rows if trade_r(row) < 0],
        "sequence_positive": [row for row in rows if trade_r(row) > 0],
    }
    for bucket, bucket_rows in buckets.items():
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in bucket_rows:
            value = str(row.get(key) or "").strip()
            if value:
                grouped.setdefault(value, []).append(row)
        for period in sorted(grouped):
            selected = grouped[period]
            metrics = bucket_metrics(selected)
            output.append(
                {
                    "breakdown_type": breakdown_type,
                    "bucket": bucket,
                    "period": period,
                    "count": len(selected),
                    "share_of_sequence": rate(len(selected), len(rows)),
                    "mean_R": metrics["mean_R"],
                    "median_R": metrics["median_R"],
                    "cumulative_R": metrics["cumulative_R"],
                    "mean_cost_R": metrics["mean_cost_R"],
                    "cumulative_cost_R": metrics["cumulative_cost_R"],
                    "mean_gross_R_proxy": metrics["mean_gross_R_proxy"],
                }
            )
    return output


def cost_profile_rows(
    sequence_rows: list[dict[str, object]],
    all_timeout_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    sequence_indexes = {int_value(row.get("_timeout_trade_index")) for row in sequence_rows}
    non_sequence = [row for row in all_timeout_rows if int_value(row.get("_timeout_trade_index")) not in sequence_indexes]
    buckets = {
        "sequence_all": sequence_rows,
        "sequence_negative": [row for row in sequence_rows if trade_r(row) < 0],
        "sequence_positive": [row for row in sequence_rows if trade_r(row) > 0],
        "all_timeout": all_timeout_rows,
        "non_sequence_timeout": non_sequence,
        "non_sequence_negative_timeout": [row for row in non_sequence if trade_r(row) < 0],
        "non_sequence_positive_timeout": [row for row in non_sequence if trade_r(row) > 0],
    }
    output: list[dict[str, object]] = []
    for bucket, rows in buckets.items():
        metrics = bucket_metrics(rows)
        output.append({"bucket": bucket, **metrics})
    return output


def add_input_warnings(inputs: DrilldownInputs, warnings: list[dict[str, object]]) -> None:
    root_label = str(inputs.root_summary.get("final_timeout_root_cause_classification") or "")
    if root_label == ROOT_FAILED_LABEL:
        add_warning(
            warnings,
            warning_code="input_timeout_root_cause_failed",
            severity="blocking",
            blocking=True,
            message="Input timeout root-cause review failed; sequence drilldown cannot clear the candidate.",
            related_metric="final_timeout_root_cause_classification",
            metric_value=root_label,
            threshold="not TIMEOUT_ROOT_CAUSE_FAILED",
        )
    elif root_label not in ALLOWED_ROOT_LABELS:
        add_warning(
            warnings,
            warning_code="input_timeout_root_cause_classification",
            severity="blocking",
            blocking=True,
            message="Input timeout root-cause classification is not an allowed drilldown state.",
            related_metric="final_timeout_root_cause_classification",
            metric_value=root_label,
            threshold="|".join(sorted(ALLOWED_ROOT_LABELS)),
        )
    for warning in inherited_blocking_warnings(inputs.root_warnings):
        add_warning(
            warnings,
            warning_code=f"inherited_root_cause_{warning.get('warning_code') or 'warning'}",
            severity="blocking",
            blocking=True,
            message=f"Inherited root-cause blocking warning: {warning.get('message') or warning}.",
            related_metric=str(warning.get("related_metric") or ""),
            metric_value=warning.get("metric_value", ""),
            threshold=warning.get("threshold", ""),
        )


def add_metric_warnings(summary: dict[str, object], warnings: list[dict[str, object]]) -> None:
    stress_ratio = finite_float(summary.get("sequence_share_of_total_stress_cumulative_R")) or 0.0
    timeout_loss_share = finite_float(summary.get("sequence_share_of_total_timeout_loss")) or 0.0
    top_5 = finite_float(summary.get("sequence_loss_concentration_top_5_pct")) or 0.0
    top_10 = finite_float(summary.get("sequence_loss_concentration_top_10_pct")) or 0.0
    years = [item for item in str(summary.get("sequence_years_distribution") or "").split(";") if item]
    dominant_hour_share = finite_float(summary.get("sequence_dominant_entry_hour_share")) or 0.0
    context_share = finite_float(summary.get("db_context_concentration_share")) or 0.0

    if stress_ratio > SEQUENCE_FAIL_STRESS_RATIO:
        add_warning(
            warnings,
            warning_code="sequence_blocking_failure",
            severity="blocking",
            blocking=True,
            message="Largest timeout sequence loss is severe relative to stress cumulative_R.",
            related_metric="sequence_share_of_total_stress_cumulative_R",
            metric_value=stress_ratio,
            threshold=f"<= {SEQUENCE_FAIL_STRESS_RATIO}",
        )
    elif stress_ratio > SEQUENCE_REVIEW_STRESS_RATIO:
        add_warning(
            warnings,
            warning_code="sequence_loss_concentration_review",
            severity="review",
            blocking=False,
            message="Largest timeout sequence remains material relative to stress cumulative_R.",
            related_metric="sequence_share_of_total_stress_cumulative_R",
            metric_value=stress_ratio,
            threshold=f"<= {SEQUENCE_REVIEW_STRESS_RATIO}",
        )
    if timeout_loss_share >= SEQUENCE_SHARE_TIMEOUT_LOSS_REVIEW_PCT:
        add_warning(
            warnings,
            warning_code="sequence_loss_concentration_review",
            severity="review",
            blocking=False,
            message="Largest sequence explains most timeout losses.",
            related_metric="sequence_share_of_total_timeout_loss",
            metric_value=timeout_loss_share,
            threshold=f"< {SEQUENCE_SHARE_TIMEOUT_LOSS_REVIEW_PCT}",
        )
    if top_5 > SEQUENCE_LOSS_CONCENTRATION_REVIEW_PCT or top_10 > SEQUENCE_LOSS_CONCENTRATION_REVIEW_PCT:
        add_warning(
            warnings,
            warning_code="sequence_loss_concentration_review",
            severity="review",
            blocking=False,
            message="Sequence losses are concentrated in the largest negative sequence trades.",
            related_metric="sequence_loss_concentration_top_5_pct|sequence_loss_concentration_top_10_pct",
            metric_value=f"{top_5}|{top_10}",
            threshold=f"<= {SEQUENCE_LOSS_CONCENTRATION_REVIEW_PCT}",
        )
    if len(years) >= SEQUENCE_CALENDAR_BROAD_YEAR_COUNT and timeout_loss_share >= SEQUENCE_SHARE_TIMEOUT_LOSS_REVIEW_PCT:
        add_warning(
            warnings,
            warning_code="sequence_calendar_broadness_review",
            severity="review",
            blocking=False,
            message="Largest sequence spans several years while explaining most timeout loss.",
            related_metric="sequence_year_count|sequence_share_of_total_timeout_loss",
            metric_value=f"{len(years)}|{timeout_loss_share}",
            threshold=f"< {SEQUENCE_CALENDAR_BROAD_YEAR_COUNT} years or < {SEQUENCE_SHARE_TIMEOUT_LOSS_REVIEW_PCT}% loss share",
        )
    if dominant_hour_share >= SEQUENCE_ENTRY_HOUR_SHARE_REVIEW:
        add_warning(
            warnings,
            warning_code="sequence_entry_hour_review",
            severity="review",
            blocking=False,
            message="Largest sequence is concentrated in one entry hour.",
            related_metric="sequence_dominant_entry_hour_share",
            metric_value=dominant_hour_share,
            threshold=f"< {SEQUENCE_ENTRY_HOUR_SHARE_REVIEW}",
        )
    if bool_value(summary.get("sequence_cost_primary_driver")):
        add_warning(
            warnings,
            warning_code="sequence_cost_driver_review",
            severity="review",
            blocking=False,
            message="Sequence cost_R is large enough to be a primary contributor to absolute sequence loss.",
            related_metric="sequence_cost_share_of_abs_loss",
            metric_value=summary.get("sequence_cost_share_of_abs_loss"),
            threshold=f"< {SEQUENCE_COST_PRIMARY_SHARE}",
        )
    else:
        add_warning(
            warnings,
            warning_code="sequence_cost_not_primary_info",
            severity="info",
            blocking=False,
            message="Sequence losses are not primarily explained by cost_R under the gross_R proxy diagnostic.",
            related_metric="sequence_cost_share_of_abs_loss",
            metric_value=summary.get("sequence_cost_share_of_abs_loss"),
            threshold=f">= {SEQUENCE_COST_PRIMARY_SHARE} for cost-primary review",
        )
    if context_share >= SEQUENCE_CONTEXT_CONCENTRATION_SHARE:
        add_warning(
            warnings,
            warning_code="sequence_context_concentration_review",
            severity="review",
            blocking=False,
            message="Optional DB enrichment found a recurring context dominating sequence losses.",
            related_metric="db_context_concentration_share",
            metric_value=context_share,
            threshold=f"< {SEQUENCE_CONTEXT_CONCENTRATION_SHARE}",
        )


def classify_sequence(summary: dict[str, object], warnings: list[dict[str, object]]) -> str:
    if any(bool_value(warning.get("blocking")) for warning in warnings):
        return FAILED_LABEL
    has_review = any(str(warning.get("severity") or "").lower() in {"review", "severe"} for warning in warnings)
    stress_ratio = finite_float(summary.get("sequence_share_of_total_stress_cumulative_R")) or 0.0
    if has_review or stress_ratio > SEQUENCE_CLEARED_STRESS_RATIO:
        return RETAINED_LABEL
    return CLEARED_LABEL


def load_db_context(
    db_path: Path | None,
    *,
    symbol: str,
    timeframe: str,
    feature_condition: str,
    sequence_rows: list[dict[str, object]],
    warnings: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if db_path is None:
        add_warning(
            warnings,
            warning_code="db_enrichment_unavailable",
            severity="info",
            blocking=False,
            message="No --db-path was provided; sequence feature-context enrichment was skipped.",
            related_metric="db_path",
            metric_value="",
            threshold="provided for optional enrichment",
        )
        return [], {"available": False, "matched_rows": 0}
    if not db_path.exists():
        add_warning(
            warnings,
            warning_code="db_enrichment_unavailable",
            severity="review",
            blocking=False,
            message="Provided --db-path does not exist; sequence feature-context enrichment was skipped.",
            related_metric="db_path",
            metric_value=str(db_path),
            threshold="existing SQLite database",
        )
        return [], {"available": False, "matched_rows": 0}
    try:
        with sqlite3.connect(db_path) as connection:
            table_rows = connection.execute("PRAGMA table_info(ml_dataset)").fetchall()
            columns = {str(row[1]) for row in table_rows}
            if not {"symbol", "timeframe", "time_server"}.issubset(columns):
                add_warning(
                    warnings,
                    warning_code="db_enrichment_unavailable",
                    severity="review",
                    blocking=False,
                    message="ml_dataset is missing required join columns; sequence enrichment was skipped.",
                    related_metric="ml_dataset_columns",
                    metric_value=",".join(sorted(columns)),
                    threshold="symbol,timeframe,time_server",
                )
                return [], {"available": False, "matched_rows": 0}
            selected_fields = [
                field
                for field in db_enrichment_fields(feature_condition)
                if field in columns and field not in {"symbol", "timeframe", "time_server"}
            ]
            if not selected_fields:
                add_warning(
                    warnings,
                    warning_code="db_enrichment_unavailable",
                    severity="review",
                    blocking=False,
                    message="ml_dataset has no supported sequence enrichment fields.",
                    related_metric="ml_dataset_columns",
                    metric_value=",".join(sorted(columns)),
                    threshold="at least one supported field",
                )
                return [], {"available": False, "matched_rows": 0}
            entry_times = sorted({str(row.get("entry_time") or "") for row in sequence_rows if row.get("entry_time")})
            if not entry_times:
                return [], {"available": False, "matched_rows": 0}
            placeholders = ",".join("?" for _ in entry_times)
            query = (
                f"SELECT {', '.join(['time_server', *selected_fields])} "
                f"FROM ml_dataset WHERE symbol = ? AND timeframe = ? AND time_server IN ({placeholders})"
            )
            fetched = connection.execute(query, [symbol, timeframe, *entry_times]).fetchall()
    except sqlite3.Error as exc:
        add_warning(
            warnings,
            warning_code="db_enrichment_unavailable",
            severity="review",
            blocking=False,
            message=f"SQLite sequence enrichment failed: {exc}",
            related_metric="db_path",
            metric_value=str(db_path),
            threshold="readable ml_dataset",
        )
        return [], {"available": False, "matched_rows": 0}
    query_columns = ["time_server", *selected_fields]
    by_time = {str(row[0]): dict(zip(query_columns, row)) for row in fetched if row and row[0]}
    if not by_time:
        add_warning(
            warnings,
            warning_code="db_enrichment_unavailable",
            severity="review",
            blocking=False,
            message="No ml_dataset rows matched sequence entry times.",
            related_metric="matched_rows",
            metric_value=0,
            threshold="> 0",
        )
        return [], {"available": False, "matched_rows": 0}
    context_rows, dominance = feature_context_rows(sequence_rows, by_time, selected_fields)
    return context_rows, {"available": bool(context_rows), "matched_rows": len(by_time), **dominance}


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


def sequence_bucket(row: dict[str, object]) -> str:
    value = trade_r(row)
    if value < 0:
        return "sequence_negative"
    if value > 0:
        return "sequence_positive"
    return "sequence_flat"


def feature_context_rows(
    sequence_rows: list[dict[str, object]],
    db_rows_by_time: dict[str, dict[str, object]],
    selected_fields: list[str],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    pairs = [
        (row, db_rows_by_time.get(str(row.get("entry_time") or "")))
        for row in sequence_rows
        if db_rows_by_time.get(str(row.get("entry_time") or ""))
    ]
    numeric_context_fields = {"spread", "atr_20", "hour", "month", "year"}
    categorical_fields = [
        field
        for field in selected_fields
        if not is_numeric_context_field(field, pairs, numeric_context_fields)
    ]
    output: list[dict[str, object]] = []
    for field in selected_fields:
        if field == "time_server":
            continue
        for bucket in ("sequence_all", "sequence_negative", "sequence_positive"):
            selected = [
                (trade, db_row)
                for trade, db_row in pairs
                if bucket == "sequence_all" or sequence_bucket(trade) == bucket
            ]
            if not selected:
                continue
            trades = [trade for trade, _db_row in selected]
            if is_numeric_context_field(field, selected, numeric_context_fields):
                values = [finite_float(db_row.get(field)) for _trade, db_row in selected]
                finite_values = [value for value in values if value is not None]
                output.append(
                    {
                        "context_field": field,
                        "context_value": "numeric_summary",
                        "sequence_bucket": bucket,
                        "count": len(finite_values),
                        "trade_share": rate(len(finite_values), len(selected)),
                        "mean_R": mean(numeric_values(trades, "R")),
                        "cumulative_R": sum(numeric_values(trades, "R")),
                        "mean_cost_R": mean(numeric_values(trades, "cost_R")),
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
                    trades_for_value = grouped[value]
                    output.append(
                        {
                            "context_field": field,
                            "context_value": value,
                            "sequence_bucket": bucket,
                            "count": len(trades_for_value),
                            "trade_share": rate(len(trades_for_value), len(selected)),
                            "mean_R": mean(numeric_values(trades_for_value, "R")),
                            "cumulative_R": sum(numeric_values(trades_for_value, "R")),
                            "mean_cost_R": mean(numeric_values(trades_for_value, "cost_R")),
                            "mean_gross_R_proxy": mean(numeric_values(trades_for_value, "gross_R_proxy")),
                            "mean_value": "",
                            "median_value": "",
                        }
                    )
    negative_count = sum(1 for trade, _db_row in pairs if sequence_bucket(trade) == "sequence_negative")
    dominance = {
        "db_context_concentration_field": "",
        "db_context_concentration_value": "",
        "db_context_concentration_share": "",
    }
    if negative_count >= SEQUENCE_CONTEXT_MIN_COUNT:
        best_field = ""
        best_value = ""
        best_share = 0.0
        for field in categorical_fields:
            grouped: dict[str, int] = {}
            for trade, db_row in pairs:
                if sequence_bucket(trade) != "sequence_negative":
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
        if best_share >= SEQUENCE_CONTEXT_CONCENTRATION_SHARE:
            dominance = {
                "db_context_concentration_field": best_field,
                "db_context_concentration_value": best_value,
                "db_context_concentration_share": best_share,
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
    inputs: DrilldownInputs,
    all_timeout_rows: list[dict[str, object]],
    sequence_rows: list[dict[str, object]],
    db_path: Path | None,
    context_status: dict[str, object],
) -> dict[str, object]:
    values = numeric_values(sequence_rows, "R")
    all_timeout_values = numeric_values(all_timeout_rows, "R")
    negative = [row for row in sequence_rows if trade_r(row) < 0]
    positive = [row for row in sequence_rows if trade_r(row) > 0]
    non_sequence = [
        row
        for row in all_timeout_rows
        if int_value(row.get("_timeout_trade_index")) not in {int_value(item.get("_timeout_trade_index")) for item in sequence_rows}
    ]
    non_sequence_negative = [row for row in non_sequence if trade_r(row) < 0]
    non_sequence_positive = [row for row in non_sequence if trade_r(row) > 0]
    metrics = bucket_metrics(sequence_rows)
    negative_metrics = bucket_metrics(negative)
    positive_metrics = bucket_metrics(positive)
    all_timeout_metrics = bucket_metrics(all_timeout_rows)
    non_sequence_negative_metrics = bucket_metrics(non_sequence_negative)
    non_sequence_positive_metrics = bucket_metrics(non_sequence_positive)
    stress_cumulative = finite_float(inputs.root_summary.get("stress_cumulative_R"))
    if stress_cumulative is None:
        stress_cumulative = sum(trade_r(row) for row in inputs.stress_trade_rows)
    timeout_loss_abs = sum(abs(value) for value in all_timeout_values if value < 0)
    sequence_loss_abs = sum(abs(value) for value in values if value < 0)
    sequence_cumulative = sum(values)
    sequence_cost_total = sum(numeric_values(sequence_rows, "cost_R"))
    dominant_hour, dominant_hour_share = dominant_distribution(sequence_rows, "_entry_hour")
    timestamps = [row_timestamp(row, prefer_exit=False) for row in sequence_rows]
    timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    start_index = min((int_value(row.get("_timeout_trade_index")) for row in sequence_rows), default="")
    end_index = max((int_value(row.get("_timeout_trade_index")) for row in sequence_rows), default="")
    return {
        "run_id": run_id,
        "timeout_root_cause_dir": str(inputs.timeout_root_cause_dir),
        "timeout_audit_dir": str(inputs.timeout_audit_dir),
        "rule_replay_dir": str(inputs.rule_replay_dir),
        "db_path": str(db_path or ""),
        "drilldown_output_dir": str(output_dir),
        "final_timeout_sequence_classification": "",
        "can_return_to_baseline_and_cost_sensitivity_review": False,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "symbol": inputs.root_summary.get("symbol", inputs.replay_summary.get("symbol", "")),
        "direction": inputs.root_summary.get("direction", inputs.replay_summary.get("direction", "")),
        "timeframe": inputs.root_summary.get("timeframe", inputs.replay_summary.get("timeframe", "")),
        "horizon": inputs.root_summary.get("horizon", inputs.replay_summary.get("horizon", "")),
        "target_family": inputs.root_summary.get("target_family", inputs.replay_summary.get("target_family", "")),
        "regime_column": inputs.root_summary.get("regime_column", inputs.replay_summary.get("regime_column", "")),
        "regime_value": inputs.root_summary.get("regime_value", inputs.replay_summary.get("regime_value", "")),
        "feature_condition": inputs.root_summary.get("feature_condition", inputs.replay_summary.get("feature_condition", "")),
        "tp_atr": inputs.root_summary.get("tp_atr", inputs.replay_summary.get("tp_atr", "")),
        "sl_atr": inputs.root_summary.get("sl_atr", inputs.replay_summary.get("sl_atr", "")),
        "same_bar_policy": inputs.root_summary.get("same_bar_policy", inputs.replay_summary.get("same_bar_policy", "")),
        "candidate_scope": inputs.root_summary.get("candidate_scope", inputs.replay_summary.get("candidate_scope", "")),
        "stress_spread_policy": inputs.root_summary.get("stress_spread_policy", inputs.replay_summary.get("stress_spread_policy", "")),
        "input_timeout_root_cause_classification": inputs.root_summary.get("final_timeout_root_cause_classification", ""),
        "input_timeout_root_cause_warnings_count": inputs.root_summary.get("warnings_count", ""),
        "input_timeout_root_cause_blocking_warnings_count": inputs.root_summary.get("blocking_warnings_count", ""),
        "input_rule_replay_classification": inputs.replay_summary.get("final_rule_replay_classification", ""),
        "stress_trades_count": len(inputs.stress_trade_rows),
        "stress_cumulative_R": stress_cumulative,
        "all_timeout_count": len(all_timeout_rows),
        "all_timeout_cumulative_R": all_timeout_metrics["cumulative_R"],
        "sequence_start_timeout_index": start_index,
        "sequence_end_timeout_index": end_index,
        "sequence_trade_count": len(sequence_rows),
        "sequence_cumulative_R": sequence_cumulative,
        "sequence_mean_R": metrics["mean_R"],
        "sequence_median_R": metrics["median_R"],
        "sequence_max_drawdown_R": max_drawdown(values),
        "sequence_loss_R": -sequence_loss_abs,
        "sequence_gain_R": sum(value for value in values if value > 0),
        "sequence_profit_factor_R": profit_factor(values),
        "sequence_negative_trade_count": len(negative),
        "sequence_positive_trade_count": len(positive),
        "sequence_negative_share": rate(len(negative), len(sequence_rows)),
        "sequence_worst_trade_R": min(values) if values else None,
        "sequence_best_trade_R": max(values) if values else None,
        "sequence_loss_concentration_top_5_pct": loss_concentration_pct(sequence_rows, 0.05),
        "sequence_loss_concentration_top_10_pct": loss_concentration_pct(sequence_rows, 0.10),
        "sequence_calendar_span_days": (max(timestamps) - min(timestamps)).days if timestamps else "",
        "sequence_years_distribution": distribution_text(sequence_rows, "_year"),
        "sequence_months_distribution": distribution_text(sequence_rows, "_month"),
        "sequence_entry_hour_distribution": distribution_text(sequence_rows, "_entry_hour"),
        "sequence_dominant_entry_hour": dominant_hour,
        "sequence_dominant_entry_hour_share": dominant_hour_share,
        "sequence_mean_cost_R": metrics["mean_cost_R"],
        "sequence_median_cost_R": metrics["median_cost_R"],
        "sequence_mean_net_R": metrics["mean_net_R"],
        "sequence_median_net_R": metrics["median_net_R"],
        "sequence_mean_gross_R_proxy": metrics["mean_gross_R_proxy"],
        "sequence_median_gross_R_proxy": metrics["median_gross_R_proxy"],
        "sequence_negative_timeout_mean_cost_R": negative_metrics["mean_cost_R"],
        "sequence_positive_timeout_mean_cost_R": positive_metrics["mean_cost_R"],
        "sequence_negative_timeout_mean_gross_R_proxy": negative_metrics["mean_gross_R_proxy"],
        "sequence_positive_timeout_mean_gross_R_proxy": positive_metrics["mean_gross_R_proxy"],
        "sequence_share_of_total_timeout_loss": (sequence_loss_abs / timeout_loss_abs * 100.0 if timeout_loss_abs > 0 else None),
        "sequence_share_of_total_stress_cumulative_R": (abs(sequence_cumulative) / stress_cumulative if sequence_cumulative < 0 and stress_cumulative and stress_cumulative > 0 else 0.0),
        "sequence_cost_share_of_abs_loss": (sequence_cost_total / sequence_loss_abs if sequence_loss_abs > 0 else 0.0),
        "sequence_cost_primary_driver": bool(sequence_loss_abs > 0 and sequence_cost_total / sequence_loss_abs >= SEQUENCE_COST_PRIMARY_SHARE),
        "sequence_vs_all_timeout_mean_R_delta": numeric_delta(metrics["mean_R"], all_timeout_metrics["mean_R"]),
        "sequence_negative_vs_non_sequence_negative_mean_R_delta": numeric_delta(negative_metrics["mean_R"], non_sequence_negative_metrics["mean_R"]),
        "sequence_positive_vs_non_sequence_positive_mean_R_delta": numeric_delta(positive_metrics["mean_R"], non_sequence_positive_metrics["mean_R"]),
        "db_enrichment_requested": db_path is not None,
        "db_enrichment_available": bool(context_status.get("available")),
        "db_enrichment_rows_matched": context_status.get("matched_rows", 0),
        "db_context_concentration_field": context_status.get("db_context_concentration_field", ""),
        "db_context_concentration_value": context_status.get("db_context_concentration_value", ""),
        "db_context_concentration_share": context_status.get("db_context_concentration_share", ""),
    }


def numeric_delta(left: object, right: object) -> float | None:
    left_number = finite_float(left)
    right_number = finite_float(right)
    if left_number is None or right_number is None:
        return None
    return left_number - right_number


def next_action_rows(classification: str, warnings: list[dict[str, object]]) -> list[dict[str, object]]:
    forbidden = forbidden_actions_text()
    if classification == CLEARED_LABEL:
        return [
            next_action_row(
                action_type="controlled_baseline_and_cost_sensitivity_review",
                status="ready_for_research_review",
                message="Timeout sequence drilldown did not find blocking or material sequence-level fragility.",
                forbidden_actions=forbidden,
                plan_item="controlled_baseline_and_cost_sensitivity_review",
                rationale="Timeout sequence drilldown did not find blocking or material sequence-level fragility.",
            )
        ]
    if classification == FAILED_LABEL:
        return [
            next_action_row(
                action_type="stop_baseline_and_cost_sensitivity_review",
                status="blocked",
                message="Timeout sequence evidence crosses blocking thresholds under current assumptions.",
                forbidden_actions=forbidden,
                plan_item="stop_baseline_and_cost_sensitivity_review",
                rationale="Timeout sequence evidence crosses blocking thresholds under current assumptions.",
            )
        ]
    warning_codes = ";".join(str(warning.get("warning_code")) for warning in warnings if str(warning.get("severity")) == "review")
    return [
        next_action_row(
            action_type="continue_timeout_sequence_review",
            status="retained_for_review",
            message=f"Review-level sequence evidence remains: {warning_codes or 'sequence evidence remains material'}.",
            forbidden_actions=forbidden,
            plan_item="continue_timeout_sequence_review",
            rationale=f"Review-level sequence evidence remains: {warning_codes or 'sequence evidence remains material'}.",
        )
    ]


def next_action_text(classification: str) -> str:
    if classification == CLEARED_LABEL:
        return "Candidate can return to controlled baseline and cost-sensitivity review."
    if classification == RETAINED_LABEL:
        return "Candidate should remain in timeout sequence review before baseline and cost-sensitivity expansion."
    return "Candidate should not continue to baseline and cost-sensitivity review under current timeout sequence evidence."


def interpretation_text(classification: str) -> str:
    if classification == CLEARED_LABEL:
        return "The largest timeout sequence appears bounded under the current research thresholds."
    if classification == RETAINED_LABEL:
        return "The largest timeout sequence is not catastrophic, but sequence concentration, calendar spread, entry-hour behavior, cost, or context evidence remains material."
    return "The largest timeout sequence crosses one or more blocking research thresholds."


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
    trade_rows: list[dict[str, object]],
    calendar_rows: list[dict[str, object]],
    entry_hour_rows: list[dict[str, object]],
    cost_rows: list[dict[str, object]],
    feature_context_rows_for_report: list[dict[str, object]],
    action_rows: list[dict[str, object]],
) -> str:
    warning_lines = [
        f"- {warning['severity']} `{warning['warning_code']}`: {warning['message']}"
        for warning in warnings
    ] or ["No warnings."]
    return "\n".join(
        [
            "# Timeout Sequence Drilldown Review",
            "",
            "## Research-Only Warning",
            "",
            "This review reads existing timeout root-cause, timeout audit, and rule-replay outputs only. Optional database enrichment is read-only and diagnostic. It does not rerun replay, recompute entries, add filters, change assumptions, optimize TP/SL, or provide operational instructions.",
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
            "",
            "## Input Sources",
            "",
            f"- Timeout root-cause dir: `{summary.get('timeout_root_cause_dir')}`",
            f"- Timeout audit dir: `{summary.get('timeout_audit_dir')}`",
            f"- Rule replay dir: `{summary.get('rule_replay_dir')}`",
            f"- DB path: `{summary.get('db_path')}`",
            "",
            "## Prior Timeout Root-Cause State",
            "",
            f"- Input root-cause classification: `{summary.get('input_timeout_root_cause_classification')}`",
            f"- Input root-cause warnings/blocking warnings: `{summary.get('input_timeout_root_cause_warnings_count')}` / `{summary.get('input_timeout_root_cause_blocking_warnings_count')}`",
            "",
            "## Largest Timeout Sequence Summary",
            "",
            f"- Timeout index range: `{summary.get('sequence_start_timeout_index')}` to `{summary.get('sequence_end_timeout_index')}`",
            f"- Count / cumulative_R / max_drawdown_R: `{summary.get('sequence_trade_count')}` / `{summary.get('sequence_cumulative_R')}` / `{summary.get('sequence_max_drawdown_R')}`",
            f"- Mean_R / median_R / PF: `{summary.get('sequence_mean_R')}` / `{summary.get('sequence_median_R')}` / `{summary.get('sequence_profit_factor_R')}`",
            f"- Negative/positive count: `{summary.get('sequence_negative_trade_count')}` / `{summary.get('sequence_positive_trade_count')}`",
            f"- Worst/best trade R: `{summary.get('sequence_worst_trade_R')}` / `{summary.get('sequence_best_trade_R')}`",
            f"- Share of total timeout loss / stress cumulative_R: `{summary.get('sequence_share_of_total_timeout_loss')}` / `{summary.get('sequence_share_of_total_stress_cumulative_R')}`",
            "",
            *table_lines(trade_rows, ["timeout_trade_index", "entry_time", "R", "cost_R", "gross_R_proxy", "running_sequence_drawdown_R"], limit=15),
            "",
            "## Calendar Distribution",
            "",
            f"- Calendar span days: `{summary.get('sequence_calendar_span_days')}`",
            f"- Years: `{summary.get('sequence_years_distribution')}`",
            f"- Months: `{summary.get('sequence_months_distribution')}`",
            "",
            *table_lines(calendar_rows, ["breakdown_type", "bucket", "period", "count", "mean_R", "cumulative_R"], limit=18),
            "",
            "## Entry-Hour Distribution",
            "",
            f"- Entry hours: `{summary.get('sequence_entry_hour_distribution')}`",
            f"- Dominant entry hour/share: `{summary.get('sequence_dominant_entry_hour')}` / `{summary.get('sequence_dominant_entry_hour_share')}`",
            "",
            *table_lines(entry_hour_rows, ["bucket", "period", "count", "mean_R", "cumulative_R"], limit=12),
            "",
            "## Cost Profile And Gross_R Proxy",
            "",
            "When `cost_R` is available, `gross_R_proxy` is calculated as `R + cost_R` for diagnostic comparison only.",
            "",
            *table_lines(cost_rows, ["bucket", "count", "mean_R", "mean_cost_R", "mean_gross_R_proxy", "cumulative_R"], limit=10),
            "",
            "## Sequence Vs All-Timeout Comparison",
            "",
            f"- Sequence mean_R delta vs all timeout: `{summary.get('sequence_vs_all_timeout_mean_R_delta')}`",
            f"- Sequence negative mean_R delta vs non-sequence negative timeout: `{summary.get('sequence_negative_vs_non_sequence_negative_mean_R_delta')}`",
            f"- Sequence positive mean_R delta vs non-sequence positive timeout: `{summary.get('sequence_positive_vs_non_sequence_positive_mean_R_delta')}`",
            "",
            "## Optional DB Enrichment Context",
            "",
            f"- Requested / available / matched rows: `{summary.get('db_enrichment_requested')}` / `{summary.get('db_enrichment_available')}` / `{summary.get('db_enrichment_rows_matched')}`",
            f"- Context concentration: `{summary.get('db_context_concentration_field')}`=`{summary.get('db_context_concentration_value')}` share `{summary.get('db_context_concentration_share')}`",
            "",
            *table_lines(feature_context_rows_for_report, ["context_field", "context_value", "sequence_bucket", "count", "mean_R", "mean_value"], limit=18),
            "",
            "## Root-Cause Interpretation",
            "",
            interpretation_text(str(summary.get("final_timeout_sequence_classification") or "")),
            "",
            "## Warnings",
            "",
            *warning_lines,
            "",
            "## Final Timeout Sequence Classification",
            "",
            f"`{summary.get('final_timeout_sequence_classification')}`",
            "",
            "## Explicit Next Action",
            "",
            next_action_text(str(summary.get("final_timeout_sequence_classification") or "")),
            "",
            *table_lines(action_rows, ["plan_item", "status", "rationale"]),
            "",
        ]
    )


def build_timeout_sequence_drilldown_review(args: argparse.Namespace) -> dict[str, Path]:
    root_dir = Path(args.timeout_root_cause_dir)
    run_id = str(args.run_id or root_dir.name).strip()
    if not run_id:
        raise ValueError("--run-id is required when --timeout-root-cause-dir has no final path name")
    paths = output_paths(Path(args.output_root), run_id)
    ensure_can_write(paths, bool(args.overwrite))
    inputs = load_inputs(root_dir, Path(args.timeout_audit_dir), Path(args.rule_replay_dir))

    warnings: list[dict[str, object]] = []
    add_input_warnings(inputs, warnings)
    annotated = annotated_stress_rows(inputs.stress_trade_rows)
    all_timeouts = timeout_rows(annotated)
    start, end = sequence_range_from_inputs(inputs)
    sequence_rows = sequence_timeout_rows(all_timeouts, start, end)
    symbol = str(inputs.root_summary.get("symbol") or inputs.replay_summary.get("symbol") or "").strip().upper()
    timeframe = str(inputs.root_summary.get("timeframe") or inputs.replay_summary.get("timeframe") or "").strip().upper()
    db_context_rows, db_status = load_db_context(
        Path(args.db_path) if args.db_path else None,
        symbol=symbol,
        timeframe=timeframe,
        feature_condition=str(inputs.root_summary.get("feature_condition") or inputs.replay_summary.get("feature_condition") or ""),
        sequence_rows=sequence_rows,
        warnings=warnings,
    )
    summary = build_summary(
        run_id=run_id,
        output_dir=paths["output_dir"],
        inputs=inputs,
        all_timeout_rows=all_timeouts,
        sequence_rows=sequence_rows,
        db_path=Path(args.db_path) if args.db_path else None,
        context_status=db_status,
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
    add_metric_warnings(summary, warnings)
    classification = classify_sequence(summary, warnings)
    blocking_count = sum(1 for warning in warnings if bool_value(warning.get("blocking")))
    summary.update(
        {
            "final_timeout_sequence_classification": classification,
            "can_return_to_baseline_and_cost_sensitivity_review": classification == CLEARED_LABEL,
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_count,
        }
    )
    add_common_summary_fields(
        summary,
        decision_scope="timeout_sequence",
        final_classification=classification,
        next_action=next_action_text(classification),
    )

    trade_rows = trade_output_rows(sequence_rows)
    calendar_rows = [
        *breakdown_rows(sequence_rows, "_year", "year"),
        *breakdown_rows(sequence_rows, "_month", "month"),
    ]
    entry_hour_rows = breakdown_rows(sequence_rows, "_entry_hour", "entry_hour")
    cost_rows = cost_profile_rows(sequence_rows, all_timeouts)
    action_rows = next_action_rows(classification, warnings)

    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_csv(paths["summary"], [summary], SUMMARY_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["trades"], trade_rows, TRADE_FIELDNAMES)
    write_csv(paths["calendar"], calendar_rows, BREAKDOWN_FIELDNAMES)
    write_csv(paths["entry_hour"], entry_hour_rows, BREAKDOWN_FIELDNAMES)
    write_csv(paths["cost_profile"], cost_rows, COST_PROFILE_FIELDNAMES)
    if db_context_rows:
        write_csv(paths["feature_context"], db_context_rows, FEATURE_CONTEXT_FIELDNAMES)
    write_csv(paths["next_action"], action_rows, NEXT_ACTION_FIELDNAMES)
    paths["report"].write_text(
        report_text(
            summary=summary,
            warnings=warnings,
            trade_rows=trade_rows,
            calendar_rows=calendar_rows,
            entry_hour_rows=entry_hour_rows,
            cost_rows=cost_rows,
            feature_context_rows_for_report=db_context_rows,
            action_rows=action_rows,
        ),
        encoding="utf-8",
    )
    return paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        paths = build_timeout_sequence_drilldown_review(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Timeout sequence drilldown review written to {paths['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
