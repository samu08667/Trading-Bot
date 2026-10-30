"""Build a focused timeout fragility audit from existing research CSV outputs.

The script reads an existing controlled expansion folder and an existing
rule-replay folder for one already validated candidate. It analyzes TIMEOUT
bucket behavior under stress only. It does not rerun replay, query the
database, recompute entries, add filters, change assumptions, or change TP/SL
settings.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import statistics
import sys
from typing import Iterable

try:
    from candidate_audit_schema import (
        add_common_summary_fields,
        warning_row,
        with_common_summary_fields,
        with_common_warning_fields,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.candidate_audit_schema import (
        add_common_summary_fields,
        warning_row,
        with_common_summary_fields,
        with_common_warning_fields,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "timeout_fragility_audit"

CONTROLLED_SUMMARY_FILE = "controlled_rule_expansion_summary.csv"
CONTROLLED_REPORT_FILE = "controlled_rule_expansion_report.md"
CONTROLLED_TIMEOUT_FILE = "controlled_rule_expansion_timeout_fragility.csv"
CONTROLLED_WARNINGS_FILE = "controlled_rule_expansion_warnings.csv"
CONTROLLED_SUBPERIODS_FILE = "controlled_rule_expansion_subperiods.csv"
CONTROLLED_ENTRY_HOUR_FILE = "controlled_rule_expansion_entry_hour.csv"

REPLAY_STRESS_TRADE_LOG_FILE = "rule_based_trade_log_stress.csv"
REPLAY_BASE_TRADE_LOG_FILE = "rule_based_trade_log_base.csv"
REPLAY_STRESS_EQUITY_FILE = "rule_based_equity_curve_stress.csv"
REPLAY_SUMMARY_FILE = "rule_based_backtest_summary.csv"
REPLAY_WARNINGS_FILE = "rule_based_warnings.csv"

SUMMARY_FILE = "timeout_fragility_audit_summary.csv"
REPORT_FILE = "timeout_fragility_audit_report.md"
WARNINGS_FILE = "timeout_fragility_audit_warnings.csv"
YEARLY_FILE = "timeout_fragility_audit_yearly.csv"
MONTHLY_FILE = "timeout_fragility_audit_monthly.csv"
ENTRY_HOUR_FILE = "timeout_fragility_audit_entry_hour.csv"
SUBPERIODS_FILE = "timeout_fragility_audit_subperiods.csv"
SEQUENCES_FILE = "timeout_fragility_audit_sequences.csv"
NON_TIMEOUT_COMPARISON_FILE = "timeout_fragility_audit_non_timeout_comparison.csv"

CONTROLLED_TIMEOUT_REVIEW_LABEL = "CONTROLLED_EXPANSION_RETAINED_FOR_TIMEOUT_REVIEW"
CONTROLLED_READY_LABEL = "READY_FOR_BASELINE_AND_COST_SENSITIVITY_REVIEW"
ALLOWED_CONTROLLED_LABELS = {CONTROLLED_TIMEOUT_REVIEW_LABEL, CONTROLLED_READY_LABEL}

PASSED_LABEL = "TIMEOUT_AUDIT_PASSED"
RETAINED_LABEL = "TIMEOUT_AUDIT_RETAINED_FOR_REVIEW"
FAILED_LABEL = "TIMEOUT_AUDIT_FAILED"

PASS_TIMEOUT_LOSS_RATIO_MAX = 0.025
PASS_NEGATIVE_YEAR_MAX = 2
PASS_WORST_YEAR_LOSS_RATIO_MAX = 0.05
RETAINED_TIMEOUT_LOSS_RATIO_MAX = 0.10
RETAINED_NEGATIVE_YEAR_MAX = 3
RETAINED_WORST_YEAR_LOSS_RATIO_MAX = 0.10
FAIL_TIMEOUT_LOSS_RATIO_MIN = 0.10
FAIL_NEGATIVE_YEAR_MIN = 4
FAIL_WORST_YEAR_LOSS_RATIO_MIN = 0.10
FAIL_TOTAL_POSITIVE_LOSS_RATIO_MIN = 0.25
ROLLING_REVIEW_LOSS_RATIO_MIN = 0.05
ROLLING_FAIL_LOSS_RATIO_MIN = 0.10
SEQUENCE_REVIEW_DRAWDOWN_RATIO_MIN = 0.05
SEQUENCE_FAIL_DRAWDOWN_RATIO_MIN = 0.10
MONTH_CLUSTER_REVIEW_LOSS_RATIO_MIN = 0.05

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
    "controlled_expansion_dir",
    "rule_replay_dir",
    "audit_output_dir",
    "final_timeout_audit_classification",
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
    "input_controlled_expansion_classification",
    "input_controlled_timeout_severity",
    "input_controlled_timeout_count",
    "input_controlled_timeout_trade_share",
    "input_controlled_timeout_cumulative_R",
    "input_controlled_blocking_warnings_count",
    "input_rule_replay_classification",
    "base_trades_count",
    "base_timeout_trades",
    "base_timeout_cumulative_R",
    "stress_total_trades",
    "stress_mean_R",
    "stress_profit_factor_R",
    "stress_cumulative_R",
    "stress_total_positive_R",
    "stress_total_negative_R",
    "timeout_trades",
    "timeout_trade_share",
    "timeout_mean_R",
    "timeout_median_R",
    "timeout_cumulative_R",
    "timeout_mean_cost_R",
    "timeout_cumulative_cost_R",
    "timeout_mean_net_R",
    "timeout_cumulative_net_R",
    "timeout_cumulative_R_pct_of_stress_cumulative_R",
    "timeout_loss_ratio_of_stress_cumulative_R",
    "timeout_loss_vs_total_positive_R_pct",
    "timeout_negative_trade_count",
    "timeout_positive_trade_count",
    "timeout_win_rate",
    "timeout_worst_trade_R",
    "timeout_best_trade_R",
    "timeout_p10_R",
    "timeout_p25_R",
    "timeout_p50_R",
    "timeout_p75_R",
    "timeout_p90_R",
    "timeout_yearly_positive_ratio",
    "timeout_negative_year_count",
    "timeout_worst_year",
    "timeout_worst_year_cumulative_R",
    "timeout_worst_year_loss_ratio",
    "timeout_monthly_positive_ratio",
    "timeout_worst_month",
    "timeout_worst_month_cumulative_R",
    "timeout_worst_month_loss_ratio",
    "timeout_worst_entry_hour",
    "timeout_worst_entry_hour_cumulative_R",
    "timeout_subperiod_min_cumulative_R",
    "timeout_subperiod_early_cumulative_R",
    "timeout_subperiod_middle_cumulative_R",
    "timeout_subperiod_recent_cumulative_R",
    "timeout_rolling_20_windows_count",
    "timeout_rolling_20_min_cumulative_R",
    "timeout_rolling_20_min_loss_ratio",
    "timeout_rolling_50_windows_count",
    "timeout_rolling_50_min_cumulative_R",
    "timeout_rolling_50_min_loss_ratio",
    "longest_consecutive_timeout_sequence",
    "longest_consecutive_negative_timeout_sequence",
    "largest_timeout_drawdown_sequence_R",
    "largest_timeout_drawdown_sequence_loss_ratio",
    "timeout_count_vs_tp_count",
    "timeout_count_vs_sl_count",
    "non_timeout_trades",
    "non_timeout_mean_R",
    "non_timeout_cumulative_R",
    "timeout_contribution_pct",
    "timeout_negative_contribution_pct",
]
SUMMARY_FIELDNAMES = with_common_summary_fields(SUMMARY_FIELDNAMES)

PERIOD_FIELDNAMES = [
    "period_type",
    "period",
    "period_total_trades",
    "timeout_count",
    "timeout_trade_share",
    "timeout_mean_R",
    "timeout_median_R",
    "timeout_cumulative_R",
    "timeout_mean_cost_R",
    "timeout_cumulative_cost_R",
    "timeout_mean_net_R",
    "timeout_cumulative_net_R",
    "timeout_positive_ratio",
    "timeout_negative_trade_count",
    "timeout_positive_trade_count",
    "period_total_cumulative_R",
    "period_cumulative_R_without_timeout",
    "timeout_contribution_pct",
    "timeout_loss_vs_period_positive_R_pct",
]

ENTRY_HOUR_FIELDNAMES = [
    "entry_hour",
    "total_trades_at_hour",
    "timeout_count",
    "timeout_trade_share",
    "timeout_mean_R",
    "timeout_cumulative_R",
    "timeout_mean_cost_R",
    "timeout_cumulative_cost_R",
    "timeout_mean_net_R",
    "timeout_cumulative_net_R",
    "timeout_positive_ratio",
    "timeout_negative_trade_count",
    "timeout_positive_trade_count",
    "total_cumulative_R_at_hour",
    "non_timeout_cumulative_R_at_hour",
]

SUBPERIOD_FIELDNAMES = [
    "subperiod",
    "start_time",
    "end_time",
    "timeout_count",
    "timeout_mean_R",
    "timeout_median_R",
    "timeout_cumulative_R",
    "timeout_mean_cost_R",
    "timeout_cumulative_cost_R",
    "timeout_mean_net_R",
    "timeout_cumulative_net_R",
    "timeout_positive_ratio",
    "max_drawdown_R",
]

SEQUENCE_FIELDNAMES = [
    "diagnostic_type",
    "sequence_id",
    "window_size",
    "start_trade_index",
    "end_trade_index",
    "start_time",
    "end_time",
    "timeout_count",
    "negative_timeout_count",
    "mean_R",
    "cumulative_R",
    "min_running_cumulative_R",
    "max_drawdown_R",
    "duration_trades",
    "recovered",
    "notes",
]

COMPARISON_FIELDNAMES = [
    "scope",
    "period_type",
    "period",
    "total_trades",
    "timeout_count",
    "tp_count",
    "sl_count",
    "other_count",
    "non_timeout_count",
    "total_cumulative_R",
    "total_positive_R",
    "total_negative_R",
    "timeout_mean_R",
    "timeout_cumulative_R",
    "timeout_mean_cost_R",
    "timeout_cumulative_cost_R",
    "timeout_mean_net_R",
    "timeout_cumulative_net_R",
    "non_timeout_mean_R",
    "non_timeout_cumulative_R",
    "non_timeout_mean_cost_R",
    "non_timeout_cumulative_cost_R",
    "non_timeout_mean_net_R",
    "non_timeout_cumulative_net_R",
    "timeout_contribution_pct",
    "timeout_negative_contribution_pct",
    "total_R_without_timeout",
]


@dataclass(frozen=True)
class AuditInputs:
    controlled_expansion_dir: Path
    controlled_summary: dict[str, str]
    controlled_report_text: str
    controlled_timeout_rows: list[dict[str, str]]
    controlled_warnings: list[dict[str, str]]
    controlled_subperiods: list[dict[str, str]]
    controlled_entry_hour: list[dict[str, str]]
    rule_replay_dir: Path
    stress_trade_rows: list[dict[str, str]]
    base_trade_rows: list[dict[str, str]]
    stress_equity_rows: list[dict[str, str]]
    replay_summary: dict[str, str]
    replay_warnings: list[dict[str, str]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only timeout fragility audit from existing controlled expansion and replay CSVs."
    )
    parser.add_argument("--controlled-expansion-dir", required=True, type=Path)
    parser.add_argument("--rule-replay-dir", required=True, type=Path)
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


def trade_r(row: dict[str, str]) -> float:
    return finite_float(row.get("R")) or 0.0


def cost_r(row: dict[str, str]) -> float | None:
    return finite_float(row.get("cost_R"))


def net_r(row: dict[str, str]) -> float | None:
    return finite_float(row.get("net_R"))


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


def percentile(values: Iterable[float], fraction: float) -> float | None:
    selected = sorted(values)
    if not selected:
        return None
    if len(selected) == 1:
        return selected[0]
    index = (len(selected) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return selected[int(index)]
    lower_value = selected[lower]
    upper_value = selected[upper]
    return lower_value + (upper_value - lower_value) * (index - lower)


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


def ratio_pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator * 100.0


def negative_loss_ratio(value: float | None, denominator: float | None) -> float | None:
    if value is None or value >= 0 or denominator is None or denominator <= 0:
        return 0.0 if value is not None and value >= 0 else None
    return abs(value) / denominator


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "output_dir": output_dir,
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "yearly": output_dir / YEARLY_FILE,
        "monthly": output_dir / MONTHLY_FILE,
        "entry_hour": output_dir / ENTRY_HOUR_FILE,
        "subperiods": output_dir / SUBPERIODS_FILE,
        "sequences": output_dir / SEQUENCES_FILE,
        "non_timeout_comparison": output_dir / NON_TIMEOUT_COMPARISON_FILE,
    }


def ensure_can_write(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for key, path in paths.items() if key != "output_dir" and path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Timeout fragility audit outputs already exist; pass --overwrite to replace: {joined}")


def load_inputs(controlled_expansion_dir: Path, rule_replay_dir: Path) -> AuditInputs:
    if not controlled_expansion_dir.exists():
        raise FileNotFoundError(f"Controlled expansion directory does not exist: {controlled_expansion_dir}")
    if not rule_replay_dir.exists():
        raise FileNotFoundError(f"Rule replay directory does not exist: {rule_replay_dir}")

    controlled_files = (
        CONTROLLED_SUMMARY_FILE,
        CONTROLLED_REPORT_FILE,
        CONTROLLED_TIMEOUT_FILE,
        CONTROLLED_WARNINGS_FILE,
        CONTROLLED_SUBPERIODS_FILE,
        CONTROLLED_ENTRY_HOUR_FILE,
    )
    replay_files = (
        REPLAY_STRESS_TRADE_LOG_FILE,
        REPLAY_BASE_TRADE_LOG_FILE,
        REPLAY_STRESS_EQUITY_FILE,
        REPLAY_SUMMARY_FILE,
        REPLAY_WARNINGS_FILE,
    )
    for filename in controlled_files:
        path = controlled_expansion_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required input file: {path}")
    for filename in replay_files:
        path = rule_replay_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required input file: {path}")

    return AuditInputs(
        controlled_expansion_dir=controlled_expansion_dir,
        controlled_summary=first_csv_row(controlled_expansion_dir / CONTROLLED_SUMMARY_FILE),
        controlled_report_text=(controlled_expansion_dir / CONTROLLED_REPORT_FILE).read_text(encoding="utf-8"),
        controlled_timeout_rows=read_csv_rows(controlled_expansion_dir / CONTROLLED_TIMEOUT_FILE),
        controlled_warnings=read_csv_rows(controlled_expansion_dir / CONTROLLED_WARNINGS_FILE),
        controlled_subperiods=read_csv_rows(controlled_expansion_dir / CONTROLLED_SUBPERIODS_FILE),
        controlled_entry_hour=read_csv_rows(controlled_expansion_dir / CONTROLLED_ENTRY_HOUR_FILE),
        rule_replay_dir=rule_replay_dir,
        stress_trade_rows=read_csv_rows(rule_replay_dir / REPLAY_STRESS_TRADE_LOG_FILE),
        base_trade_rows=read_csv_rows(rule_replay_dir / REPLAY_BASE_TRADE_LOG_FILE),
        stress_equity_rows=read_csv_rows(rule_replay_dir / REPLAY_STRESS_EQUITY_FILE),
        replay_summary=first_csv_row(rule_replay_dir / REPLAY_SUMMARY_FILE),
        replay_warnings=read_csv_rows(rule_replay_dir / REPLAY_WARNINGS_FILE),
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
            related_stage="timeout_audit",
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


def component_values(rows: list[dict[str, str]], component: str) -> list[float]:
    if component == "R":
        return [trade_r(row) for row in rows]
    if component == "cost_R":
        return [value for value in (cost_r(row) for row in rows) if value is not None]
    if component == "net_R":
        return [value for value in (net_r(row) for row in rows) if value is not None]
    raise ValueError(f"Unsupported component: {component}")


def bucket_metrics(rows: list[dict[str, str]], total_trades: int | None = None) -> dict[str, object]:
    values = component_values(rows, "R")
    costs = component_values(rows, "cost_R")
    nets = component_values(rows, "net_R")
    count = len(values)
    return {
        "count": count,
        "trade_share": rate(count, total_trades or 0) if total_trades is not None else None,
        "mean_R": mean(values),
        "median_R": median(values),
        "cumulative_R": sum(values),
        "mean_cost_R": mean(costs),
        "cumulative_cost_R": sum(costs) if costs else None,
        "mean_net_R": mean(nets),
        "cumulative_net_R": sum(nets) if nets else None,
        "positive_count": sum(1 for value in values if value > 0),
        "negative_count": sum(1 for value in values if value < 0),
        "positive_ratio": rate(sum(1 for value in values if value > 0), count),
        "worst_R": min(values) if values else None,
        "best_R": max(values) if values else None,
        "p10_R": percentile(values, 0.10),
        "p25_R": percentile(values, 0.25),
        "p50_R": percentile(values, 0.50),
        "p75_R": percentile(values, 0.75),
        "p90_R": percentile(values, 0.90),
        "max_drawdown_R": max_drawdown(values),
    }


def total_positive_R(rows: list[dict[str, str]]) -> float:
    return sum(value for value in (trade_r(row) for row in rows) if value > 0)


def total_negative_R(rows: list[dict[str, str]]) -> float:
    return sum(value for value in (trade_r(row) for row in rows) if value < 0)


def period_rows(rows: list[dict[str, str]], period_type: str) -> list[dict[str, object]]:
    grouped_total: dict[str, list[dict[str, str]]] = {}
    grouped_timeout: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        timestamp = row_timestamp(row, prefer_exit=True)
        if timestamp is None:
            continue
        label = period_label(timestamp, period_type)
        grouped_total.setdefault(label, []).append(row)
        if is_timeout(row):
            grouped_timeout.setdefault(label, []).append(row)

    output: list[dict[str, object]] = []
    for label in sorted(grouped_total):
        total_rows = grouped_total[label]
        timeout_rows = grouped_timeout.get(label, [])
        timeout_metrics = bucket_metrics(timeout_rows, len(total_rows))
        total_cumulative = sum(trade_r(row) for row in total_rows)
        non_timeout_cumulative = sum(trade_r(row) for row in total_rows if not is_timeout(row))
        period_positive = total_positive_R(total_rows)
        timeout_cumulative = finite_float(timeout_metrics.get("cumulative_R")) or 0.0
        timeout_loss_vs_positive = None
        if timeout_cumulative < 0 and period_positive > 0:
            timeout_loss_vs_positive = abs(timeout_cumulative) / period_positive * 100.0
        output.append(
            {
                "period_type": period_type,
                "period": label,
                "period_total_trades": len(total_rows),
                "timeout_count": timeout_metrics["count"],
                "timeout_trade_share": timeout_metrics["trade_share"],
                "timeout_mean_R": timeout_metrics["mean_R"],
                "timeout_median_R": timeout_metrics["median_R"],
                "timeout_cumulative_R": timeout_metrics["cumulative_R"],
                "timeout_mean_cost_R": timeout_metrics["mean_cost_R"],
                "timeout_cumulative_cost_R": timeout_metrics["cumulative_cost_R"],
                "timeout_mean_net_R": timeout_metrics["mean_net_R"],
                "timeout_cumulative_net_R": timeout_metrics["cumulative_net_R"],
                "timeout_positive_ratio": timeout_metrics["positive_ratio"],
                "timeout_negative_trade_count": timeout_metrics["negative_count"],
                "timeout_positive_trade_count": timeout_metrics["positive_count"],
                "period_total_cumulative_R": total_cumulative,
                "period_cumulative_R_without_timeout": non_timeout_cumulative,
                "timeout_contribution_pct": ratio_pct(timeout_cumulative, total_cumulative),
                "timeout_loss_vs_period_positive_R_pct": timeout_loss_vs_positive,
            }
        )
    return output


def positive_period_ratio(rows: list[dict[str, object]]) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if (finite_float(row.get("timeout_cumulative_R")) or 0.0) > 0) / len(rows)


def entry_hour_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped_total: dict[int, list[dict[str, str]]] = {}
    grouped_timeout: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        timestamp = row_timestamp(row, prefer_exit=False)
        if timestamp is None:
            continue
        grouped_total.setdefault(timestamp.hour, []).append(row)
        if is_timeout(row):
            grouped_timeout.setdefault(timestamp.hour, []).append(row)

    output: list[dict[str, object]] = []
    for hour in sorted(grouped_total):
        total_rows = grouped_total[hour]
        timeout_rows = grouped_timeout.get(hour, [])
        timeout_metrics = bucket_metrics(timeout_rows, len(total_rows))
        output.append(
            {
                "entry_hour": hour,
                "total_trades_at_hour": len(total_rows),
                "timeout_count": timeout_metrics["count"],
                "timeout_trade_share": timeout_metrics["trade_share"],
                "timeout_mean_R": timeout_metrics["mean_R"],
                "timeout_cumulative_R": timeout_metrics["cumulative_R"],
                "timeout_mean_cost_R": timeout_metrics["mean_cost_R"],
                "timeout_cumulative_cost_R": timeout_metrics["cumulative_cost_R"],
                "timeout_mean_net_R": timeout_metrics["mean_net_R"],
                "timeout_cumulative_net_R": timeout_metrics["cumulative_net_R"],
                "timeout_positive_ratio": timeout_metrics["positive_ratio"],
                "timeout_negative_trade_count": timeout_metrics["negative_count"],
                "timeout_positive_trade_count": timeout_metrics["positive_count"],
                "total_cumulative_R_at_hour": sum(trade_r(row) for row in total_rows),
                "non_timeout_cumulative_R_at_hour": sum(trade_r(row) for row in total_rows if not is_timeout(row)),
            }
        )
    return output


def subperiod_rows(timeout_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    sorted_rows = sorted(timeout_rows, key=lambda row: row_timestamp(row, prefer_exit=False) or datetime.max)
    if not sorted_rows:
        return []
    labels = ("early", "middle", "recent")
    total = len(sorted_rows)
    output: list[dict[str, object]] = []
    for index, label in enumerate(labels):
        start = math.floor(index * total / 3)
        end = math.floor((index + 1) * total / 3)
        subset = sorted_rows[start:end]
        if not subset:
            continue
        metrics = bucket_metrics(subset)
        output.append(
            {
                "subperiod": label,
                "start_time": timestamp_text(subset[0], prefer_exit=False),
                "end_time": timestamp_text(subset[-1], prefer_exit=False),
                "timeout_count": len(subset),
                "timeout_mean_R": metrics["mean_R"],
                "timeout_median_R": metrics["median_R"],
                "timeout_cumulative_R": metrics["cumulative_R"],
                "timeout_mean_cost_R": metrics["mean_cost_R"],
                "timeout_cumulative_cost_R": metrics["cumulative_cost_R"],
                "timeout_mean_net_R": metrics["mean_net_R"],
                "timeout_cumulative_net_R": metrics["cumulative_net_R"],
                "timeout_positive_ratio": metrics["positive_ratio"],
                "max_drawdown_R": metrics["max_drawdown_R"],
            }
        )
    return output


def rolling_timeout_rows(timeout_rows: list[dict[str, str]], window_size: int) -> list[dict[str, object]]:
    sorted_rows = sorted(timeout_rows, key=lambda row: row_timestamp(row, prefer_exit=False) or datetime.max)
    if len(sorted_rows) < window_size:
        return []
    output: list[dict[str, object]] = []
    for start in range(0, len(sorted_rows) - window_size + 1):
        end = start + window_size
        window = sorted_rows[start:end]
        values = [trade_r(row) for row in window]
        cumulative = 0.0
        min_running = 0.0
        for value in values:
            cumulative += value
            min_running = min(min_running, cumulative)
        output.append(
            {
                "diagnostic_type": "rolling_timeout_window",
                "sequence_id": start + 1,
                "window_size": window_size,
                "start_trade_index": start + 1,
                "end_trade_index": end,
                "start_time": timestamp_text(window[0], prefer_exit=False),
                "end_time": timestamp_text(window[-1], prefer_exit=False),
                "timeout_count": window_size,
                "negative_timeout_count": sum(1 for value in values if value < 0),
                "mean_R": mean(values),
                "cumulative_R": sum(values),
                "min_running_cumulative_R": min_running,
                "max_drawdown_R": max_drawdown(values),
                "duration_trades": window_size,
                "recovered": "",
                "notes": "rolling timeout-trade window",
            }
        )
    return output


def longest_consecutive_sequence(
    rows: list[dict[str, str]],
    predicate: object,
    diagnostic_type: str,
) -> dict[str, object]:
    best_start = 0
    best_end = 0
    best_rows: list[dict[str, str]] = []
    current_start = 0
    current_rows: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        if predicate(row):  # type: ignore[operator]
            if not current_rows:
                current_start = index
            current_rows.append(row)
            if len(current_rows) > len(best_rows):
                best_rows = list(current_rows)
                best_start = current_start
                best_end = index
        else:
            current_rows = []
    values = [trade_r(row) for row in best_rows]
    return {
        "diagnostic_type": diagnostic_type,
        "sequence_id": 1,
        "window_size": "",
        "start_trade_index": best_start if best_rows else "",
        "end_trade_index": best_end if best_rows else "",
        "start_time": timestamp_text(best_rows[0], prefer_exit=False) if best_rows else "",
        "end_time": timestamp_text(best_rows[-1], prefer_exit=False) if best_rows else "",
        "timeout_count": len(best_rows),
        "negative_timeout_count": sum(1 for value in values if value < 0),
        "mean_R": mean(values),
        "cumulative_R": sum(values) if values else None,
        "min_running_cumulative_R": min_running_cumulative(values),
        "max_drawdown_R": max_drawdown(values),
        "duration_trades": len(best_rows),
        "recovered": "",
        "notes": "consecutive sequence in full stress trade order",
    }


def min_running_cumulative(values: list[float]) -> float | None:
    if not values:
        return None
    cumulative = 0.0
    minimum = 0.0
    for value in values:
        cumulative += value
        minimum = min(minimum, cumulative)
    return minimum


def timeout_drawdown_sequences(timeout_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    sorted_rows = sorted(timeout_rows, key=lambda row: row_timestamp(row, prefer_exit=False) or datetime.max)
    values = [trade_r(row) for row in sorted_rows]
    output: list[dict[str, object]] = []
    cumulative = 0.0
    peak = 0.0
    peak_index = 0
    in_sequence = False
    sequence_id = 0
    start_index = 0
    trough_index = 0
    trough_drawdown = 0.0
    for index, value in enumerate(values, start=1):
        cumulative += value
        if cumulative >= peak:
            if in_sequence:
                output.append(
                    timeout_drawdown_record(
                        sorted_rows,
                        sequence_id,
                        start_index,
                        trough_index,
                        index,
                        trough_drawdown,
                        recovered=True,
                    )
                )
                in_sequence = False
            peak = cumulative
            peak_index = index
            continue
        drawdown = peak - cumulative
        if not in_sequence:
            sequence_id += 1
            start_index = min(index, max(peak_index + 1, 1))
            trough_index = index
            trough_drawdown = drawdown
            in_sequence = True
        elif drawdown > trough_drawdown:
            trough_index = index
            trough_drawdown = drawdown
    if in_sequence:
        output.append(
            timeout_drawdown_record(
                sorted_rows,
                sequence_id,
                start_index,
                trough_index,
                len(values),
                trough_drawdown,
                recovered=False,
            )
        )
    return output


def timeout_drawdown_record(
    rows: list[dict[str, str]],
    sequence_id: int,
    start_index: int,
    trough_index: int,
    end_index: int,
    drawdown: float,
    *,
    recovered: bool,
) -> dict[str, object]:
    subset = rows[start_index - 1 : end_index]
    values = [trade_r(row) for row in subset]
    return {
        "diagnostic_type": "timeout_drawdown_sequence",
        "sequence_id": sequence_id,
        "window_size": "",
        "start_trade_index": start_index,
        "end_trade_index": end_index,
        "start_time": timestamp_text(rows[start_index - 1], prefer_exit=False) if rows and start_index >= 1 else "",
        "end_time": timestamp_text(rows[end_index - 1], prefer_exit=False) if rows and end_index >= 1 else "",
        "timeout_count": len(subset),
        "negative_timeout_count": sum(1 for value in values if value < 0),
        "mean_R": mean(values),
        "cumulative_R": sum(values) if values else None,
        "min_running_cumulative_R": min_running_cumulative(values),
        "max_drawdown_R": drawdown,
        "duration_trades": max(0, end_index - start_index + 1),
        "recovered": recovered,
        "notes": f"trough_timeout_trade_index={trough_index}",
    }


def sequence_rows(rows: list[dict[str, str]], timeout_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    sorted_rows = sorted(rows, key=lambda row: row_timestamp(row, prefer_exit=False) or datetime.max)
    output = [
        *rolling_timeout_rows(timeout_rows, 20),
        *rolling_timeout_rows(timeout_rows, 50),
        longest_consecutive_sequence(sorted_rows, is_timeout, "longest_consecutive_timeout_sequence"),
        longest_consecutive_sequence(
            sorted_rows,
            lambda row: is_timeout(row) and trade_r(row) < 0,
            "longest_consecutive_negative_timeout_sequence",
        ),
    ]
    drawdowns = timeout_drawdown_sequences(timeout_rows)
    if drawdowns:
        largest = max(drawdowns, key=lambda row: finite_float(row.get("max_drawdown_R")) or 0.0)
        output.append({**largest, "diagnostic_type": "largest_timeout_drawdown_sequence"})
    return output


def comparison_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    output = [comparison_record("overall", "overall", "all", rows)]
    for period_type in ("year", "month"):
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            timestamp = row_timestamp(row, prefer_exit=True)
            if timestamp is None:
                continue
            grouped.setdefault(period_label(timestamp, period_type), []).append(row)
        for label in sorted(grouped):
            output.append(comparison_record("stress_period", period_type, label, grouped[label]))
    return output


def comparison_record(scope: str, period_type: str, period: str, rows: list[dict[str, str]]) -> dict[str, object]:
    timeout_rows = [row for row in rows if is_timeout(row)]
    non_timeout_rows = [row for row in rows if not is_timeout(row)]
    timeout_metrics = bucket_metrics(timeout_rows, len(rows))
    non_timeout_metrics = bucket_metrics(non_timeout_rows, len(rows))
    exit_reasons = [normalize_exit_reason(row) for row in rows]
    total_cumulative = sum(trade_r(row) for row in rows)
    total_negative = total_negative_R(rows)
    timeout_negative = sum(trade_r(row) for row in timeout_rows if trade_r(row) < 0)
    timeout_cumulative = finite_float(timeout_metrics.get("cumulative_R")) or 0.0
    return {
        "scope": scope,
        "period_type": period_type,
        "period": period,
        "total_trades": len(rows),
        "timeout_count": len(timeout_rows),
        "tp_count": sum(1 for reason in exit_reasons if reason == "TP"),
        "sl_count": sum(1 for reason in exit_reasons if reason == "SL"),
        "other_count": sum(1 for reason in exit_reasons if reason not in {"TP", "SL", "TIMEOUT"}),
        "non_timeout_count": len(non_timeout_rows),
        "total_cumulative_R": total_cumulative,
        "total_positive_R": total_positive_R(rows),
        "total_negative_R": total_negative,
        "timeout_mean_R": timeout_metrics["mean_R"],
        "timeout_cumulative_R": timeout_metrics["cumulative_R"],
        "timeout_mean_cost_R": timeout_metrics["mean_cost_R"],
        "timeout_cumulative_cost_R": timeout_metrics["cumulative_cost_R"],
        "timeout_mean_net_R": timeout_metrics["mean_net_R"],
        "timeout_cumulative_net_R": timeout_metrics["cumulative_net_R"],
        "non_timeout_mean_R": non_timeout_metrics["mean_R"],
        "non_timeout_cumulative_R": non_timeout_metrics["cumulative_R"],
        "non_timeout_mean_cost_R": non_timeout_metrics["mean_cost_R"],
        "non_timeout_cumulative_cost_R": non_timeout_metrics["cumulative_cost_R"],
        "non_timeout_mean_net_R": non_timeout_metrics["mean_net_R"],
        "non_timeout_cumulative_net_R": non_timeout_metrics["cumulative_net_R"],
        "timeout_contribution_pct": ratio_pct(timeout_cumulative, total_cumulative),
        "timeout_negative_contribution_pct": (
            abs(timeout_negative) / abs(total_negative) * 100.0 if total_negative < 0 and timeout_negative < 0 else None
        ),
        "total_R_without_timeout": sum(trade_r(row) for row in non_timeout_rows),
    }


def first_controlled_timeout_overall(inputs: AuditInputs) -> dict[str, str]:
    return next(
        (
            row
            for row in inputs.controlled_timeout_rows
            if str(row.get("scope") or "").strip() == "stress"
            and str(row.get("period_type") or "").strip() == "overall"
        ),
        {},
    )


def add_input_warnings(inputs: AuditInputs, warnings: list[dict[str, object]]) -> None:
    controlled_label = str(inputs.controlled_summary.get("final_research_only_classification") or "")
    if controlled_label not in ALLOWED_CONTROLLED_LABELS:
        add_warning(
            warnings,
            warning_code="input_controlled_expansion_classification",
            severity="blocking",
            blocking=True,
            message=(
                f"Input controlled expansion classification is {controlled_label or 'missing'}, "
                f"not one of {', '.join(sorted(ALLOWED_CONTROLLED_LABELS))}."
            ),
            related_metric="final_research_only_classification",
            metric_value=controlled_label,
            threshold="|".join(sorted(ALLOWED_CONTROLLED_LABELS)),
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
    for warning in inherited_blocking_warnings(inputs.replay_warnings):
        add_warning(
            warnings,
            warning_code=f"inherited_rule_replay_{warning.get('warning_code') or warning.get('check') or 'warning'}",
            severity="blocking",
            blocking=True,
            message=f"Inherited rule replay blocking warning: {warning.get('message') or warning}.",
            related_metric=str(warning.get("related_metric") or warning.get("check") or ""),
            metric_value=warning.get("metric_value", ""),
            threshold=warning.get("threshold", ""),
        )


def add_metric_warnings(summary: dict[str, object], warnings: list[dict[str, object]]) -> None:
    stress_cumulative = finite_float(summary.get("stress_cumulative_R"))
    stress_mean = finite_float(summary.get("stress_mean_R"))
    stress_pf = finite_float(summary.get("stress_profit_factor_R"))
    if stress_mean is None or stress_mean <= 0:
        add_warning(
            warnings,
            warning_code="stress_mean_R_blocking",
            severity="blocking",
            blocking=True,
            message="Stress mean_R from the existing trade log is not positive.",
            related_metric="stress_mean_R",
            metric_value=stress_mean,
            threshold="> 0",
        )
    if stress_pf is None or stress_pf <= 1:
        add_warning(
            warnings,
            warning_code="stress_profit_factor_R_blocking",
            severity="blocking",
            blocking=True,
            message="Stress profit_factor_R from the existing trade log is not greater than 1.",
            related_metric="stress_profit_factor_R",
            metric_value=stress_pf,
            threshold="> 1",
        )
    if stress_cumulative is None or stress_cumulative <= 0:
        add_warning(
            warnings,
            warning_code="stress_cumulative_R_blocking",
            severity="blocking",
            blocking=True,
            message="Stress cumulative_R from the existing trade log is not positive.",
            related_metric="stress_cumulative_R",
            metric_value=stress_cumulative,
            threshold="> 0",
        )
        return

    timeout_cumulative = finite_float(summary.get("timeout_cumulative_R"))
    timeout_loss_ratio = finite_float(summary.get("timeout_loss_ratio_of_stress_cumulative_R"))
    total_positive_loss_pct = finite_float(summary.get("timeout_loss_vs_total_positive_R_pct"))
    negative_year_count = int_value(summary.get("timeout_negative_year_count"))
    worst_year_loss_ratio = finite_float(summary.get("timeout_worst_year_loss_ratio"))
    worst_month_loss_ratio = finite_float(summary.get("timeout_worst_month_loss_ratio"))
    rolling_20_loss_ratio = finite_float(summary.get("timeout_rolling_20_min_loss_ratio")) or 0.0
    rolling_50_loss_ratio = finite_float(summary.get("timeout_rolling_50_min_loss_ratio")) or 0.0
    largest_drawdown_ratio = finite_float(summary.get("largest_timeout_drawdown_sequence_loss_ratio")) or 0.0

    if timeout_cumulative is not None and timeout_cumulative < 0:
        if timeout_loss_ratio is not None and timeout_loss_ratio <= PASS_TIMEOUT_LOSS_RATIO_MAX:
            add_warning(
                warnings,
                warning_code="timeout_negative_but_small",
                severity="info",
                blocking=False,
                message="Timeout cumulative_R is negative but small relative to total stress cumulative_R.",
                related_metric="timeout_loss_ratio_of_stress_cumulative_R",
                metric_value=timeout_loss_ratio,
                threshold=f"<= {PASS_TIMEOUT_LOSS_RATIO_MAX}",
            )
        elif timeout_loss_ratio is not None and timeout_loss_ratio <= FAIL_TIMEOUT_LOSS_RATIO_MIN:
            add_warning(
                warnings,
                warning_code="timeout_loss_review",
                severity="review",
                blocking=False,
                message="Timeout cumulative_R is negative and requires continued research review.",
                related_metric="timeout_loss_ratio_of_stress_cumulative_R",
                metric_value=timeout_loss_ratio,
                threshold=f"<= {FAIL_TIMEOUT_LOSS_RATIO_MIN}",
            )

    if timeout_loss_ratio is not None and timeout_loss_ratio > FAIL_TIMEOUT_LOSS_RATIO_MIN:
        add_warning(
            warnings,
            warning_code="timeout_total_loss_blocking",
            severity="blocking",
            blocking=True,
            message="Timeout loss is greater than 10 percent of total stress cumulative_R.",
            related_metric="timeout_loss_ratio_of_stress_cumulative_R",
            metric_value=timeout_loss_ratio,
            threshold=f"<= {FAIL_TIMEOUT_LOSS_RATIO_MIN}",
        )
    if negative_year_count >= FAIL_NEGATIVE_YEAR_MIN:
        add_warning(
            warnings,
            warning_code="timeout_negative_years_blocking",
            severity="blocking",
            blocking=True,
            message="Timeout losses occur in four or more negative years.",
            related_metric="timeout_negative_year_count",
            metric_value=negative_year_count,
            threshold=f"< {FAIL_NEGATIVE_YEAR_MIN}",
        )
    if worst_year_loss_ratio is not None and worst_year_loss_ratio > FAIL_WORST_YEAR_LOSS_RATIO_MIN:
        add_warning(
            warnings,
            warning_code="timeout_worst_year_blocking",
            severity="blocking",
            blocking=True,
            message="Worst timeout year loss is greater than 10 percent of total stress cumulative_R.",
            related_metric="timeout_worst_year_loss_ratio",
            metric_value=worst_year_loss_ratio,
            threshold=f"<= {FAIL_WORST_YEAR_LOSS_RATIO_MIN}",
        )
    elif worst_year_loss_ratio is not None and worst_year_loss_ratio > PASS_WORST_YEAR_LOSS_RATIO_MAX:
        add_warning(
            warnings,
            warning_code="timeout_worst_year_review",
            severity="review",
            blocking=False,
            message="Worst timeout year loss is above the pass threshold but below the blocking threshold.",
            related_metric="timeout_worst_year_loss_ratio",
            metric_value=worst_year_loss_ratio,
            threshold=f"<= {PASS_WORST_YEAR_LOSS_RATIO_MAX}",
        )
    if total_positive_loss_pct is not None and total_positive_loss_pct >= FAIL_TOTAL_POSITIVE_LOSS_RATIO_MIN * 100.0:
        add_warning(
            warnings,
            warning_code="timeout_loss_vs_positive_R_blocking",
            severity="blocking",
            blocking=True,
            message="Timeout loss is at least 25 percent of total positive_R.",
            related_metric="timeout_loss_vs_total_positive_R_pct",
            metric_value=total_positive_loss_pct,
            threshold=f"< {FAIL_TOTAL_POSITIVE_LOSS_RATIO_MIN * 100.0}",
        )
    if worst_month_loss_ratio is not None and worst_month_loss_ratio > MONTH_CLUSTER_REVIEW_LOSS_RATIO_MIN:
        add_warning(
            warnings,
            warning_code="timeout_month_cluster_review",
            severity="review",
            blocking=False,
            message="Worst timeout month loss is concentrated enough to require review.",
            related_metric="timeout_worst_month_loss_ratio",
            metric_value=worst_month_loss_ratio,
            threshold=f"<= {MONTH_CLUSTER_REVIEW_LOSS_RATIO_MIN}",
        )

    max_rolling_loss_ratio = max(rolling_20_loss_ratio, rolling_50_loss_ratio)
    if max_rolling_loss_ratio > ROLLING_FAIL_LOSS_RATIO_MIN:
        add_warning(
            warnings,
            warning_code="timeout_rolling_window_blocking",
            severity="blocking",
            blocking=True,
            message="Timeout rolling windows show severe repeated degradation.",
            related_metric="max_timeout_rolling_loss_ratio",
            metric_value=max_rolling_loss_ratio,
            threshold=f"<= {ROLLING_FAIL_LOSS_RATIO_MIN}",
        )
    elif max_rolling_loss_ratio > ROLLING_REVIEW_LOSS_RATIO_MIN:
        add_warning(
            warnings,
            warning_code="timeout_rolling_window_review",
            severity="review",
            blocking=False,
            message="Timeout rolling windows are negative enough to keep the candidate in review.",
            related_metric="max_timeout_rolling_loss_ratio",
            metric_value=max_rolling_loss_ratio,
            threshold=f"<= {ROLLING_REVIEW_LOSS_RATIO_MIN}",
        )

    if largest_drawdown_ratio > SEQUENCE_FAIL_DRAWDOWN_RATIO_MIN:
        add_warning(
            warnings,
            warning_code="timeout_sequence_blocking",
            severity="blocking",
            blocking=True,
            message="Largest timeout drawdown sequence is severe relative to total stress cumulative_R.",
            related_metric="largest_timeout_drawdown_sequence_loss_ratio",
            metric_value=largest_drawdown_ratio,
            threshold=f"<= {SEQUENCE_FAIL_DRAWDOWN_RATIO_MIN}",
        )
    elif largest_drawdown_ratio > SEQUENCE_REVIEW_DRAWDOWN_RATIO_MIN:
        add_warning(
            warnings,
            warning_code="timeout_sequence_review",
            severity="review",
            blocking=False,
            message="Largest timeout drawdown sequence requires continued timeout review.",
            related_metric="largest_timeout_drawdown_sequence_loss_ratio",
            metric_value=largest_drawdown_ratio,
            threshold=f"<= {SEQUENCE_REVIEW_DRAWDOWN_RATIO_MIN}",
        )

    if any(bool_value(warning.get("blocking")) for warning in warnings):
        add_warning(
            warnings,
            warning_code="timeout_blocking_fragility",
            severity="blocking",
            blocking=True,
            message="One or more timeout audit blocking conditions are present.",
            related_metric="blocking_warnings_count",
            metric_value=sum(1 for warning in warnings if bool_value(warning.get("blocking"))),
            threshold="0",
        )


def classify_timeout_audit(summary: dict[str, object], warnings: list[dict[str, object]]) -> str:
    if any(bool_value(warning.get("blocking")) for warning in warnings):
        return FAILED_LABEL
    timeout_cumulative = finite_float(summary.get("timeout_cumulative_R"))
    if timeout_cumulative is None:
        return RETAINED_LABEL
    if timeout_cumulative >= 0:
        if has_review_fragility(summary):
            return RETAINED_LABEL
        return PASSED_LABEL

    timeout_loss_ratio = finite_float(summary.get("timeout_loss_ratio_of_stress_cumulative_R"))
    negative_year_count = int_value(summary.get("timeout_negative_year_count"))
    worst_year_loss_ratio = finite_float(summary.get("timeout_worst_year_loss_ratio")) or 0.0
    worst_month_loss_ratio = finite_float(summary.get("timeout_worst_month_loss_ratio")) or 0.0
    rolling_20_loss_ratio = finite_float(summary.get("timeout_rolling_20_min_loss_ratio")) or 0.0
    rolling_50_loss_ratio = finite_float(summary.get("timeout_rolling_50_min_loss_ratio")) or 0.0
    largest_drawdown_ratio = finite_float(summary.get("largest_timeout_drawdown_sequence_loss_ratio")) or 0.0

    if (
        timeout_loss_ratio is not None
        and timeout_loss_ratio <= PASS_TIMEOUT_LOSS_RATIO_MAX
        and negative_year_count <= PASS_NEGATIVE_YEAR_MAX
        and worst_year_loss_ratio <= PASS_WORST_YEAR_LOSS_RATIO_MAX
        and worst_month_loss_ratio <= MONTH_CLUSTER_REVIEW_LOSS_RATIO_MIN
        and max(rolling_20_loss_ratio, rolling_50_loss_ratio) <= ROLLING_REVIEW_LOSS_RATIO_MIN
        and largest_drawdown_ratio <= SEQUENCE_REVIEW_DRAWDOWN_RATIO_MIN
    ):
        return PASSED_LABEL

    if (
        timeout_loss_ratio is not None
        and timeout_loss_ratio <= RETAINED_TIMEOUT_LOSS_RATIO_MAX
        and negative_year_count <= RETAINED_NEGATIVE_YEAR_MAX
        and worst_year_loss_ratio <= RETAINED_WORST_YEAR_LOSS_RATIO_MAX
        and max(rolling_20_loss_ratio, rolling_50_loss_ratio) <= ROLLING_FAIL_LOSS_RATIO_MIN
        and largest_drawdown_ratio <= SEQUENCE_FAIL_DRAWDOWN_RATIO_MIN
    ):
        return RETAINED_LABEL
    return FAILED_LABEL


def has_review_fragility(summary: dict[str, object]) -> bool:
    return any(
        (finite_float(summary.get(key)) or 0.0) > threshold
        for key, threshold in (
            ("timeout_rolling_20_min_loss_ratio", ROLLING_REVIEW_LOSS_RATIO_MIN),
            ("timeout_rolling_50_min_loss_ratio", ROLLING_REVIEW_LOSS_RATIO_MIN),
            ("largest_timeout_drawdown_sequence_loss_ratio", SEQUENCE_REVIEW_DRAWDOWN_RATIO_MIN),
            ("timeout_worst_month_loss_ratio", MONTH_CLUSTER_REVIEW_LOSS_RATIO_MIN),
        )
    )


def next_action_for_classification(classification: str) -> str:
    if classification == PASSED_LABEL:
        return "Candidate can return to controlled baseline and cost-sensitivity review."
    if classification == RETAINED_LABEL:
        return "Candidate should remain in timeout review before baseline and cost-sensitivity expansion."
    return "Candidate should not continue to baseline and cost-sensitivity review under current timeout evidence."


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


def build_summary(
    *,
    run_id: str,
    output_dir: Path,
    inputs: AuditInputs,
    yearly_rows: list[dict[str, object]],
    monthly_rows: list[dict[str, object]],
    entry_rows: list[dict[str, object]],
    subperiod_output_rows: list[dict[str, object]],
    sequence_output_rows: list[dict[str, object]],
    comparison_output_rows: list[dict[str, object]],
) -> dict[str, object]:
    stress_rows = inputs.stress_trade_rows
    base_rows = inputs.base_trade_rows
    timeout_rows = [row for row in stress_rows if is_timeout(row)]
    non_timeout_rows = [row for row in stress_rows if not is_timeout(row)]
    timeout_metrics = bucket_metrics(timeout_rows, len(stress_rows))
    non_timeout_metrics = bucket_metrics(non_timeout_rows, len(stress_rows))
    stress_values = [trade_r(row) for row in stress_rows]
    stress_cumulative = sum(stress_values)
    stress_positive = total_positive_R(stress_rows)
    stress_negative = total_negative_R(stress_rows)
    timeout_cumulative = finite_float(timeout_metrics.get("cumulative_R")) or 0.0
    base_timeout_rows = [row for row in base_rows if is_timeout(row)]
    base_timeout_metrics = bucket_metrics(base_timeout_rows, len(base_rows))
    controlled_timeout = first_controlled_timeout_overall(inputs)

    negative_years = [row for row in yearly_rows if (finite_float(row.get("timeout_cumulative_R")) or 0.0) < 0]
    worst_year = min(yearly_rows, key=lambda row: finite_float(row.get("timeout_cumulative_R")) or 0.0, default={})
    worst_month = min(monthly_rows, key=lambda row: finite_float(row.get("timeout_cumulative_R")) or 0.0, default={})
    worst_entry_hour = min(entry_rows, key=lambda row: finite_float(row.get("timeout_cumulative_R")) or 0.0, default={})

    subperiod_by_name = {str(row.get("subperiod")): row for row in subperiod_output_rows}
    rolling_20 = [
        row
        for row in sequence_output_rows
        if row.get("diagnostic_type") == "rolling_timeout_window" and int_value(row.get("window_size")) == 20
    ]
    rolling_50 = [
        row
        for row in sequence_output_rows
        if row.get("diagnostic_type") == "rolling_timeout_window" and int_value(row.get("window_size")) == 50
    ]
    rolling_20_min = min((finite_float(row.get("cumulative_R")) or 0.0 for row in rolling_20), default=None)
    rolling_50_min = min((finite_float(row.get("cumulative_R")) or 0.0 for row in rolling_50), default=None)
    longest_timeout = next(
        (row for row in sequence_output_rows if row.get("diagnostic_type") == "longest_consecutive_timeout_sequence"),
        {},
    )
    longest_negative_timeout = next(
        (
            row
            for row in sequence_output_rows
            if row.get("diagnostic_type") == "longest_consecutive_negative_timeout_sequence"
        ),
        {},
    )
    largest_drawdown = next(
        (row for row in sequence_output_rows if row.get("diagnostic_type") == "largest_timeout_drawdown_sequence"),
        {},
    )
    overall_comparison = next((row for row in comparison_output_rows if row.get("scope") == "overall"), {})
    exit_reasons = [normalize_exit_reason(row) for row in stress_rows]
    timeout_negative = sum(trade_r(row) for row in timeout_rows if trade_r(row) < 0)
    timeout_loss_vs_positive = abs(timeout_cumulative) / stress_positive * 100.0 if timeout_cumulative < 0 and stress_positive > 0 else None
    worst_year_cumulative = finite_float(worst_year.get("timeout_cumulative_R"))
    worst_month_cumulative = finite_float(worst_month.get("timeout_cumulative_R"))
    largest_drawdown_R = finite_float(largest_drawdown.get("max_drawdown_R")) or 0.0

    return {
        "run_id": run_id,
        "controlled_expansion_dir": str(inputs.controlled_expansion_dir),
        "rule_replay_dir": str(inputs.rule_replay_dir),
        "audit_output_dir": str(output_dir),
        "final_timeout_audit_classification": "",
        "can_return_to_baseline_and_cost_sensitivity_review": False,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "symbol": inputs.controlled_summary.get("symbol", inputs.replay_summary.get("symbol", "")),
        "direction": inputs.controlled_summary.get("direction", inputs.replay_summary.get("direction", "")),
        "timeframe": inputs.controlled_summary.get("timeframe", inputs.replay_summary.get("timeframe", "")),
        "horizon": inputs.controlled_summary.get("horizon", inputs.replay_summary.get("horizon", "")),
        "target_family": inputs.controlled_summary.get("target_family", inputs.replay_summary.get("target_family", "")),
        "regime_column": inputs.controlled_summary.get("regime_column", inputs.replay_summary.get("regime_column", "")),
        "regime_value": inputs.controlled_summary.get("regime_value", inputs.replay_summary.get("regime_value", "")),
        "feature_condition": inputs.controlled_summary.get("feature_condition", inputs.replay_summary.get("feature_condition", "")),
        "tp_atr": inputs.controlled_summary.get("tp_atr", inputs.replay_summary.get("tp_atr", "")),
        "sl_atr": inputs.controlled_summary.get("sl_atr", inputs.replay_summary.get("sl_atr", "")),
        "same_bar_policy": inputs.controlled_summary.get("same_bar_policy", inputs.replay_summary.get("same_bar_policy", "")),
        "candidate_scope": inputs.controlled_summary.get("candidate_scope", inputs.replay_summary.get("candidate_scope", "")),
        "stress_spread_policy": inputs.controlled_summary.get("stress_spread_policy", inputs.replay_summary.get("stress_spread_policy", "")),
        "input_controlled_expansion_classification": inputs.controlled_summary.get("final_research_only_classification", ""),
        "input_controlled_timeout_severity": inputs.controlled_summary.get("timeout_severity", ""),
        "input_controlled_timeout_count": controlled_timeout.get("timeout_count", inputs.controlled_summary.get("timeout_count", "")),
        "input_controlled_timeout_trade_share": controlled_timeout.get(
            "timeout_trade_pct",
            inputs.controlled_summary.get("timeout_trade_share", ""),
        ),
        "input_controlled_timeout_cumulative_R": controlled_timeout.get(
            "timeout_cumulative_R",
            inputs.controlled_summary.get("timeout_cumulative_R", ""),
        ),
        "input_controlled_blocking_warnings_count": inputs.controlled_summary.get("blocking_warnings_count", ""),
        "input_rule_replay_classification": inputs.replay_summary.get("final_rule_replay_classification", ""),
        "base_trades_count": len(base_rows),
        "base_timeout_trades": len(base_timeout_rows),
        "base_timeout_cumulative_R": base_timeout_metrics["cumulative_R"],
        "stress_total_trades": len(stress_rows),
        "stress_mean_R": mean(stress_values),
        "stress_profit_factor_R": profit_factor(stress_values),
        "stress_cumulative_R": stress_cumulative,
        "stress_total_positive_R": stress_positive,
        "stress_total_negative_R": stress_negative,
        "timeout_trades": timeout_metrics["count"],
        "timeout_trade_share": timeout_metrics["trade_share"],
        "timeout_mean_R": timeout_metrics["mean_R"],
        "timeout_median_R": timeout_metrics["median_R"],
        "timeout_cumulative_R": timeout_metrics["cumulative_R"],
        "timeout_mean_cost_R": timeout_metrics["mean_cost_R"],
        "timeout_cumulative_cost_R": timeout_metrics["cumulative_cost_R"],
        "timeout_mean_net_R": timeout_metrics["mean_net_R"],
        "timeout_cumulative_net_R": timeout_metrics["cumulative_net_R"],
        "timeout_cumulative_R_pct_of_stress_cumulative_R": ratio_pct(timeout_cumulative, stress_cumulative),
        "timeout_loss_ratio_of_stress_cumulative_R": negative_loss_ratio(timeout_cumulative, stress_cumulative),
        "timeout_loss_vs_total_positive_R_pct": timeout_loss_vs_positive,
        "timeout_negative_trade_count": timeout_metrics["negative_count"],
        "timeout_positive_trade_count": timeout_metrics["positive_count"],
        "timeout_win_rate": timeout_metrics["positive_ratio"],
        "timeout_worst_trade_R": timeout_metrics["worst_R"],
        "timeout_best_trade_R": timeout_metrics["best_R"],
        "timeout_p10_R": timeout_metrics["p10_R"],
        "timeout_p25_R": timeout_metrics["p25_R"],
        "timeout_p50_R": timeout_metrics["p50_R"],
        "timeout_p75_R": timeout_metrics["p75_R"],
        "timeout_p90_R": timeout_metrics["p90_R"],
        "timeout_yearly_positive_ratio": positive_period_ratio(yearly_rows),
        "timeout_negative_year_count": len(negative_years),
        "timeout_worst_year": worst_year.get("period", ""),
        "timeout_worst_year_cumulative_R": worst_year_cumulative,
        "timeout_worst_year_loss_ratio": negative_loss_ratio(worst_year_cumulative, stress_cumulative),
        "timeout_monthly_positive_ratio": positive_period_ratio(monthly_rows),
        "timeout_worst_month": worst_month.get("period", ""),
        "timeout_worst_month_cumulative_R": worst_month_cumulative,
        "timeout_worst_month_loss_ratio": negative_loss_ratio(worst_month_cumulative, stress_cumulative),
        "timeout_worst_entry_hour": worst_entry_hour.get("entry_hour", ""),
        "timeout_worst_entry_hour_cumulative_R": worst_entry_hour.get("timeout_cumulative_R", ""),
        "timeout_subperiod_min_cumulative_R": min(
            (finite_float(row.get("timeout_cumulative_R")) or 0.0 for row in subperiod_output_rows),
            default=None,
        ),
        "timeout_subperiod_early_cumulative_R": subperiod_by_name.get("early", {}).get("timeout_cumulative_R", ""),
        "timeout_subperiod_middle_cumulative_R": subperiod_by_name.get("middle", {}).get("timeout_cumulative_R", ""),
        "timeout_subperiod_recent_cumulative_R": subperiod_by_name.get("recent", {}).get("timeout_cumulative_R", ""),
        "timeout_rolling_20_windows_count": len(rolling_20),
        "timeout_rolling_20_min_cumulative_R": rolling_20_min,
        "timeout_rolling_20_min_loss_ratio": negative_loss_ratio(rolling_20_min, stress_cumulative),
        "timeout_rolling_50_windows_count": len(rolling_50),
        "timeout_rolling_50_min_cumulative_R": rolling_50_min,
        "timeout_rolling_50_min_loss_ratio": negative_loss_ratio(rolling_50_min, stress_cumulative),
        "longest_consecutive_timeout_sequence": longest_timeout.get("timeout_count", ""),
        "longest_consecutive_negative_timeout_sequence": longest_negative_timeout.get("timeout_count", ""),
        "largest_timeout_drawdown_sequence_R": largest_drawdown_R,
        "largest_timeout_drawdown_sequence_loss_ratio": (
            largest_drawdown_R / stress_cumulative if stress_cumulative > 0 else None
        ),
        "timeout_count_vs_tp_count": f"{len(timeout_rows)}:{sum(1 for reason in exit_reasons if reason == 'TP')}",
        "timeout_count_vs_sl_count": f"{len(timeout_rows)}:{sum(1 for reason in exit_reasons if reason == 'SL')}",
        "non_timeout_trades": len(non_timeout_rows),
        "non_timeout_mean_R": non_timeout_metrics["mean_R"],
        "non_timeout_cumulative_R": non_timeout_metrics["cumulative_R"],
        "timeout_contribution_pct": overall_comparison.get("timeout_contribution_pct"),
        "timeout_negative_contribution_pct": (
            abs(timeout_negative) / abs(stress_negative) * 100.0 if stress_negative < 0 and timeout_negative < 0 else None
        ),
    }


def report_text(
    *,
    summary: dict[str, object],
    warnings: list[dict[str, object]],
    yearly_rows: list[dict[str, object]],
    monthly_rows: list[dict[str, object]],
    entry_rows: list[dict[str, object]],
    subperiod_rows: list[dict[str, object]],
    sequence_rows_for_report: list[dict[str, object]],
    comparison_rows_for_report: list[dict[str, object]],
) -> str:
    warning_lines = [
        f"- {warning['severity']} `{warning['warning_code']}`: {warning['message']}"
        for warning in warnings
    ] or ["No warnings."]
    rolling_rows = [row for row in sequence_rows_for_report if row.get("diagnostic_type") == "rolling_timeout_window"]
    sequence_rows_only = [
        row for row in sequence_rows_for_report if row.get("diagnostic_type") != "rolling_timeout_window"
    ]
    next_action = next_action_for_classification(str(summary.get("final_timeout_audit_classification") or ""))
    return "\n".join(
        [
            "# Timeout Fragility Audit",
            "",
            "## Research-Only Warning",
            "",
            "This audit reads existing controlled expansion and rule-replay CSV outputs only. It does not rerun replay, recompute entries, add filters, change assumptions, change TP/SL settings, or provide operational instructions.",
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
            f"- Controlled expansion dir: `{summary.get('controlled_expansion_dir')}`",
            f"- Rule replay dir: `{summary.get('rule_replay_dir')}`",
            f"- Audit output dir: `{summary.get('audit_output_dir')}`",
            "",
            "## Prior Controlled Expansion State",
            "",
            f"- Controlled expansion classification: `{summary.get('input_controlled_expansion_classification')}`",
            f"- Controlled timeout severity: `{summary.get('input_controlled_timeout_severity')}`",
            f"- Controlled timeout count / share / cumulative_R: `{summary.get('input_controlled_timeout_count')}` / `{summary.get('input_controlled_timeout_trade_share')}` / `{summary.get('input_controlled_timeout_cumulative_R')}`",
            f"- Rule replay classification: `{summary.get('input_rule_replay_classification')}`",
            "",
            "## Overall Timeout Bucket Summary",
            "",
            f"- Stress trades / cumulative_R / mean_R / PF: `{summary.get('stress_total_trades')}` / `{summary.get('stress_cumulative_R')}` / `{summary.get('stress_mean_R')}` / `{summary.get('stress_profit_factor_R')}`",
            f"- Timeout trades / share: `{summary.get('timeout_trades')}` / `{summary.get('timeout_trade_share')}`",
            f"- Timeout mean_R / median_R / cumulative_R: `{summary.get('timeout_mean_R')}` / `{summary.get('timeout_median_R')}` / `{summary.get('timeout_cumulative_R')}`",
            f"- Timeout cost_R mean/cumulative: `{summary.get('timeout_mean_cost_R')}` / `{summary.get('timeout_cumulative_cost_R')}`",
            f"- Timeout net_R mean/cumulative: `{summary.get('timeout_mean_net_R')}` / `{summary.get('timeout_cumulative_net_R')}`",
            f"- Timeout cumulative_R pct of stress cumulative_R: `{summary.get('timeout_cumulative_R_pct_of_stress_cumulative_R')}`",
            f"- Timeout loss vs total positive_R pct: `{summary.get('timeout_loss_vs_total_positive_R_pct')}`",
            f"- Timeout win rate / negative count / positive count: `{summary.get('timeout_win_rate')}` / `{summary.get('timeout_negative_trade_count')}` / `{summary.get('timeout_positive_trade_count')}`",
            f"- Timeout p10/p25/p50/p75/p90 R: `{summary.get('timeout_p10_R')}` / `{summary.get('timeout_p25_R')}` / `{summary.get('timeout_p50_R')}` / `{summary.get('timeout_p75_R')}` / `{summary.get('timeout_p90_R')}`",
            "",
            "## Timeout Yearly Diagnostics",
            "",
            f"- Negative timeout years: `{summary.get('timeout_negative_year_count')}`",
            f"- Worst timeout year / cumulative_R: `{summary.get('timeout_worst_year')}` / `{summary.get('timeout_worst_year_cumulative_R')}`",
            f"- Yearly positive ratio: `{summary.get('timeout_yearly_positive_ratio')}`",
            "",
            *table_lines(yearly_rows, ["period", "timeout_count", "timeout_mean_R", "timeout_cumulative_R", "period_cumulative_R_without_timeout"], limit=12),
            "",
            "## Timeout Monthly Diagnostics",
            "",
            f"- Worst timeout month / cumulative_R: `{summary.get('timeout_worst_month')}` / `{summary.get('timeout_worst_month_cumulative_R')}`",
            f"- Monthly positive ratio: `{summary.get('timeout_monthly_positive_ratio')}`",
            "",
            *table_lines(monthly_rows, ["period", "timeout_count", "timeout_mean_R", "timeout_cumulative_R", "period_cumulative_R_without_timeout"], limit=12),
            "",
            "## Timeout Entry-Hour Diagnostics",
            "",
            f"- Worst entry hour / cumulative_R: `{summary.get('timeout_worst_entry_hour')}` / `{summary.get('timeout_worst_entry_hour_cumulative_R')}`",
            "",
            *table_lines(entry_rows, ["entry_hour", "timeout_count", "timeout_mean_R", "timeout_cumulative_R", "non_timeout_cumulative_R_at_hour"], limit=12),
            "",
            "## Timeout Subperiod Diagnostics",
            "",
            f"- Early/middle/recent timeout cumulative_R: `{summary.get('timeout_subperiod_early_cumulative_R')}` / `{summary.get('timeout_subperiod_middle_cumulative_R')}` / `{summary.get('timeout_subperiod_recent_cumulative_R')}`",
            "",
            *table_lines(subperiod_rows, ["subperiod", "timeout_count", "timeout_mean_R", "timeout_cumulative_R", "max_drawdown_R"]),
            "",
            "## Timeout Rolling-Window Diagnostics",
            "",
            f"- Rolling 20 windows / min cumulative_R: `{summary.get('timeout_rolling_20_windows_count')}` / `{summary.get('timeout_rolling_20_min_cumulative_R')}`",
            f"- Rolling 50 windows / min cumulative_R: `{summary.get('timeout_rolling_50_windows_count')}` / `{summary.get('timeout_rolling_50_min_cumulative_R')}`",
            "",
            *table_lines(rolling_rows, ["window_size", "start_trade_index", "end_trade_index", "mean_R", "cumulative_R", "max_drawdown_R"], limit=12),
            "",
            "## Timeout Sequence Diagnostics",
            "",
            f"- Longest consecutive timeout sequence: `{summary.get('longest_consecutive_timeout_sequence')}`",
            f"- Longest consecutive negative-timeout sequence: `{summary.get('longest_consecutive_negative_timeout_sequence')}`",
            f"- Largest timeout drawdown sequence R: `{summary.get('largest_timeout_drawdown_sequence_R')}`",
            "",
            *table_lines(sequence_rows_only, ["diagnostic_type", "start_trade_index", "end_trade_index", "timeout_count", "cumulative_R", "max_drawdown_R"], limit=12),
            "",
            "## Timeout Vs Non-Timeout Comparison",
            "",
            f"- Timeout vs TP count: `{summary.get('timeout_count_vs_tp_count')}`",
            f"- Timeout vs SL count: `{summary.get('timeout_count_vs_sl_count')}`",
            f"- Timeout mean_R / non-timeout mean_R: `{summary.get('timeout_mean_R')}` / `{summary.get('non_timeout_mean_R')}`",
            f"- Timeout cumulative_R / non-timeout cumulative_R: `{summary.get('timeout_cumulative_R')}` / `{summary.get('non_timeout_cumulative_R')}`",
            f"- Timeout contribution pct: `{summary.get('timeout_contribution_pct')}`",
            f"- Timeout negative contribution pct: `{summary.get('timeout_negative_contribution_pct')}`",
            "",
            *table_lines(comparison_rows_for_report, ["period_type", "period", "timeout_count", "timeout_cumulative_R", "non_timeout_cumulative_R", "total_R_without_timeout"], limit=12),
            "",
            "## Interpretation",
            "",
            interpretation_text(str(summary.get("final_timeout_audit_classification") or "")),
            "",
            "## Warnings",
            "",
            *warning_lines,
            "",
            "## Final Timeout Audit Classification",
            "",
            f"`{summary.get('final_timeout_audit_classification')}`",
            "",
            "## Explicit Next Action",
            "",
            next_action,
            "",
        ]
    )


def interpretation_text(classification: str) -> str:
    if classification == PASSED_LABEL:
        return "Timeout behavior is negative at most mildly under the current research thresholds and does not block the next controlled review step."
    if classification == RETAINED_LABEL:
        return "Timeout behavior is not catastrophic, but concentration or sequence evidence is strong enough to keep the candidate in focused timeout review."
    return "Timeout behavior crosses one or more blocking fragility thresholds under the current research-only evidence."


def build_timeout_fragility_audit(args: argparse.Namespace) -> dict[str, Path]:
    controlled_dir = Path(args.controlled_expansion_dir)
    run_id = str(args.run_id or controlled_dir.name).strip()
    if not run_id:
        raise ValueError("--run-id is required when --controlled-expansion-dir has no final path name")
    paths = output_paths(Path(args.output_root), run_id)
    ensure_can_write(paths, bool(args.overwrite))
    inputs = load_inputs(controlled_dir, Path(args.rule_replay_dir))

    stress_rows = sorted(inputs.stress_trade_rows, key=lambda row: row_timestamp(row, prefer_exit=False) or datetime.max)
    timeout_rows = [row for row in stress_rows if is_timeout(row)]
    yearly_output_rows = period_rows(stress_rows, "year")
    monthly_output_rows = period_rows(stress_rows, "month")
    entry_output_rows = entry_hour_rows(stress_rows)
    subperiod_output_rows = subperiod_rows(timeout_rows)
    sequence_output_rows = sequence_rows(stress_rows, timeout_rows)
    comparison_output_rows = comparison_rows(stress_rows)
    summary = build_summary(
        run_id=run_id,
        output_dir=paths["output_dir"],
        inputs=inputs,
        yearly_rows=yearly_output_rows,
        monthly_rows=monthly_output_rows,
        entry_rows=entry_output_rows,
        subperiod_output_rows=subperiod_output_rows,
        sequence_output_rows=sequence_output_rows,
        comparison_output_rows=comparison_output_rows,
    )
    warnings: list[dict[str, object]] = []
    add_input_warnings(inputs, warnings)
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
    classification = classify_timeout_audit(summary, warnings)
    blocking_count = sum(1 for warning in warnings if bool_value(warning.get("blocking")))
    summary.update(
        {
            "final_timeout_audit_classification": classification,
            "can_return_to_baseline_and_cost_sensitivity_review": classification == PASSED_LABEL,
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_count,
        }
    )
    add_common_summary_fields(
        summary,
        decision_scope="timeout_audit",
        final_classification=classification,
        next_action=next_action_for_classification(classification),
    )

    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_csv(paths["summary"], [summary], SUMMARY_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["yearly"], yearly_output_rows, PERIOD_FIELDNAMES)
    write_csv(paths["monthly"], monthly_output_rows, PERIOD_FIELDNAMES)
    write_csv(paths["entry_hour"], entry_output_rows, ENTRY_HOUR_FIELDNAMES)
    write_csv(paths["subperiods"], subperiod_output_rows, SUBPERIOD_FIELDNAMES)
    write_csv(paths["sequences"], sequence_output_rows, SEQUENCE_FIELDNAMES)
    write_csv(paths["non_timeout_comparison"], comparison_output_rows, COMPARISON_FIELDNAMES)
    paths["report"].write_text(
        report_text(
            summary=summary,
            warnings=warnings,
            yearly_rows=yearly_output_rows,
            monthly_rows=monthly_output_rows,
            entry_rows=entry_output_rows,
            subperiod_rows=subperiod_output_rows,
            sequence_rows_for_report=sequence_output_rows,
            comparison_rows_for_report=comparison_output_rows,
        ),
        encoding="utf-8",
    )
    return paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        paths = build_timeout_fragility_audit(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Timeout fragility audit written to {paths['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
