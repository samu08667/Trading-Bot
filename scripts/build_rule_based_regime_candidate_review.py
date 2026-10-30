"""Build an offline review for an already replayed rule-based regime candidate.

This script reads existing rule-replay CSV outputs and summarizes robustness
diagnostics. It does not reconstruct entries, query the database, rerun a
replay, change TP/SL assumptions, or add filters.
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
        normalize_warning_severity,
        warning_row,
        with_common_summary_fields,
        with_common_warning_fields,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.candidate_audit_schema import (
        add_common_summary_fields,
        normalize_warning_severity,
        warning_row,
        with_common_summary_fields,
        with_common_warning_fields,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "rule_based_regime_candidate_review"

INPUT_SUMMARY_FILE = "rule_based_backtest_summary.csv"
INPUT_COMPARISON_FILE = "rule_based_comparison_to_stress_validation.csv"
INPUT_BASE_TRADE_LOG_FILE = "rule_based_trade_log_base.csv"
INPUT_STRESS_TRADE_LOG_FILE = "rule_based_trade_log_stress.csv"
INPUT_BASE_EQUITY_FILE = "rule_based_equity_curve_base.csv"
INPUT_STRESS_EQUITY_FILE = "rule_based_equity_curve_stress.csv"
INPUT_WARNINGS_FILE = "rule_based_warnings.csv"

SUMMARY_FILE = "rule_based_review_summary.csv"
REPORT_FILE = "rule_based_review_report.md"
WARNINGS_FILE = "rule_based_review_warnings.csv"
MONTHLY_FILE = "rule_based_review_monthly.csv"
YEARLY_FILE = "rule_based_review_yearly.csv"
ROLLING_FILE = "rule_based_review_rolling_windows.csv"
EXIT_PROFILE_FILE = "rule_based_review_exit_profile.csv"
ENTRY_HOUR_FILE = "rule_based_review_entry_hour.csv"
DRAWDOWN_SEQUENCE_FILE = "rule_based_review_drawdown_sequences.csv"

OUTPUT_FILES = (
    SUMMARY_FILE,
    REPORT_FILE,
    WARNINGS_FILE,
    MONTHLY_FILE,
    YEARLY_FILE,
    ROLLING_FILE,
    EXIT_PROFILE_FILE,
    ENTRY_HOUR_FILE,
    DRAWDOWN_SEQUENCE_FILE,
)

INPUT_MATCHED_LABEL = "RULE_REPLAY_MATCHED_STRESS_VALIDATION"
REJECTED_LABEL = "RULE_BASED_REVIEW_REJECTED"
RETAINED_LABEL = "RULE_BASED_REVIEW_RETAINED"
READY_LABEL = "READY_FOR_CONTROLLED_RULE_RESEARCH_BACKTEST_EXPANSION"

MIN_TRADES = 100
MONTHLY_POSITIVE_RATIO_MIN = 0.65
TOP_MONTH_CONTRIBUTION_MAX_PCT = 25.0
TOP_5_TRADE_CONTRIBUTION_MAX_PCT = 35.0
DRAWDOWN_TO_CUMULATIVE_MAX = 0.25
TIMEOUT_MEAN_R_MIN = -0.25

WARNING_FIELDNAMES = with_common_warning_fields(["severity", "check", "blocks_ready", "message"])
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
    "rule_replay_dir",
    "review_output_dir",
    "final_research_only_classification",
    "ready_for_controlled_rule_research_backtest_expansion",
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
    "atr_column",
    "same_bar_policy",
    "bar_level_no_overlap",
    "stress_spread_policy",
    "input_rule_replay_classification",
    "generated_logs_match_stress_validation",
    "comparison_logs_match_all",
    "inherited_warnings_count",
    "inherited_blocking_warnings_count",
    "base_trades_count",
    "stress_trades_count",
    "base_mean_R",
    "stress_mean_R",
    "base_median_R",
    "stress_median_R",
    "base_profit_factor_R",
    "stress_profit_factor_R",
    "base_cumulative_R",
    "stress_cumulative_R",
    "base_max_drawdown_R",
    "stress_max_drawdown_R",
    "base_win_rate",
    "stress_win_rate",
    "base_tp_hit_rate",
    "stress_tp_hit_rate",
    "base_sl_hit_rate",
    "stress_sl_hit_rate",
    "base_timeout_rate",
    "stress_timeout_rate",
    "base_equity_final_cumulative_R",
    "stress_equity_final_cumulative_R",
    "base_equity_max_drawdown_R",
    "stress_equity_max_drawdown_R",
    "mean_R_delta",
    "profit_factor_R_delta",
    "cumulative_R_delta",
    "max_drawdown_R_delta",
    "timeout_mean_R_delta",
    "stress_month_count",
    "stress_monthly_positive_ratio",
    "stress_worst_month",
    "stress_worst_month_cumulative_R",
    "stress_best_month",
    "stress_best_month_cumulative_R",
    "stress_year_count",
    "stress_yearly_positive_ratio",
    "stress_negative_year_count",
    "stress_rolling_50_windows_count",
    "stress_rolling_50_min_cumulative_R",
    "stress_rolling_50_min_running_cumulative_R",
    "stress_rolling_100_windows_count",
    "stress_rolling_100_min_cumulative_R",
    "stress_rolling_100_min_running_cumulative_R",
    "stress_longest_losing_streak",
    "stress_longest_non_positive_streak",
    "stress_largest_drawdown_sequence_R",
    "stress_largest_drawdown_sequence_trades",
    "stress_timeout_mean_R",
    "stress_timeout_cumulative_R",
    "top_month_contribution_pct",
    "top_5_percent_contribution_pct",
    "stress_drawdown_to_cumulative_R",
]
SUMMARY_FIELDNAMES = with_common_summary_fields(SUMMARY_FIELDNAMES)

PERIOD_FIELDNAMES = [
    "scope",
    "period",
    "trades_count",
    "mean_R",
    "median_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
    "positive",
    "tp_hit_rate",
    "sl_hit_rate",
    "timeout_rate",
]

ROLLING_FIELDNAMES = [
    "scope",
    "window_size",
    "start_trade_index",
    "end_trade_index",
    "start_time",
    "end_time",
    "trades_count",
    "mean_R",
    "cumulative_R",
    "min_cumulative_R",
    "max_drawdown_R",
    "positive",
]

EXIT_PROFILE_FIELDNAMES = [
    "scope",
    "exit_reason",
    "trades_count",
    "hit_rate",
    "mean_R",
    "cumulative_R",
    "mean_cost_R",
    "mean_net_R",
]

ENTRY_HOUR_FIELDNAMES = [
    "scope",
    "entry_hour",
    "trades_count",
    "trade_pct",
    "mean_R",
    "cumulative_R",
]

DRAWDOWN_SEQUENCE_FIELDNAMES = [
    "scope",
    "sequence_id",
    "start_trade_index",
    "trough_trade_index",
    "end_trade_index",
    "start_time",
    "trough_time",
    "end_time",
    "max_drawdown_R",
    "duration_trades",
    "recovered",
]


@dataclass(frozen=True)
class ReviewInputs:
    rule_replay_dir: Path
    replay_summary: dict[str, str]
    comparison_rows: list[dict[str, str]]
    base_trade_rows: list[dict[str, str]]
    stress_trade_rows: list[dict[str, str]]
    base_equity_rows: list[dict[str, str]]
    stress_equity_rows: list[dict[str, str]]
    replay_warning_rows: list[dict[str, str]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only review from existing rule-replay CSV outputs."
    )
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
    try:
        parsed = float(value) if value is not None and str(value).strip() != "" else None
    except (TypeError, ValueError):
        return None
    if parsed is None or math.isnan(parsed):
        return None
    return parsed


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


def period_label(timestamp: datetime, period: str) -> str:
    if period == "month":
        return f"{timestamp.year:04d}-{timestamp.month:02d}"
    if period == "year":
        return f"{timestamp.year:04d}"
    raise ValueError(f"Unsupported period: {period}")


def normalize_exit_reason(row: dict[str, str]) -> str:
    reason = str(row.get("exit_reason") or "OTHER").strip().upper()
    return reason or "OTHER"


def rate(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return count / total


def trade_metrics(rows: list[dict[str, str]]) -> dict[str, object]:
    values = [trade_r(row) for row in rows]
    total = len(values)
    exit_reasons = [normalize_exit_reason(row) for row in rows]
    return {
        "trades_count": total,
        "mean_R": mean(values),
        "median_R": median(values),
        "profit_factor_R": profit_factor(values),
        "cumulative_R": sum(values),
        "max_drawdown_R": max_drawdown(values),
        "win_rate": rate(sum(1 for value in values if value > 0), total),
        "tp_hit_rate": rate(sum(1 for reason in exit_reasons if reason == "TP"), total),
        "sl_hit_rate": rate(sum(1 for reason in exit_reasons if reason == "SL"), total),
        "timeout_rate": rate(sum(1 for reason in exit_reasons if reason == "TIMEOUT"), total),
        "longest_losing_streak": longest_streak(values, lambda value: value < 0),
        "longest_non_positive_streak": longest_streak(values, lambda value: value <= 0),
    }


def longest_streak(values: list[float], predicate: object) -> int:
    current = 0
    maximum = 0
    for value in values:
        if predicate(value):  # type: ignore[operator]
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def group_period_rows(rows: list[dict[str, str]], scope: str, period: str) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        timestamp = row_timestamp(row, prefer_exit=True)
        if timestamp is None:
            continue
        grouped.setdefault(period_label(timestamp, period), []).append(row)
    output: list[dict[str, object]] = []
    for label in sorted(grouped):
        period_rows = grouped[label]
        metrics = trade_metrics(period_rows)
        output.append(
            {
                "scope": scope,
                "period": label,
                "trades_count": metrics["trades_count"],
                "mean_R": metrics["mean_R"],
                "median_R": metrics["median_R"],
                "profit_factor_R": metrics["profit_factor_R"],
                "cumulative_R": metrics["cumulative_R"],
                "max_drawdown_R": metrics["max_drawdown_R"],
                "positive": (metrics["cumulative_R"] or 0.0) > 0,
                "tp_hit_rate": metrics["tp_hit_rate"],
                "sl_hit_rate": metrics["sl_hit_rate"],
                "timeout_rate": metrics["timeout_rate"],
            }
        )
    return output


def rolling_rows(rows: list[dict[str, str]], scope: str, window_size: int) -> list[dict[str, object]]:
    values = [trade_r(row) for row in rows]
    if len(values) < window_size:
        return []
    output: list[dict[str, object]] = []
    for start in range(0, len(values) - window_size + 1):
        end = start + window_size
        window = values[start:end]
        cumulative = 0.0
        min_running = 0.0
        for value in window:
            cumulative += value
            min_running = min(min_running, cumulative)
        start_time = row_timestamp(rows[start], prefer_exit=False)
        end_time = row_timestamp(rows[end - 1], prefer_exit=False)
        output.append(
            {
                "scope": scope,
                "window_size": window_size,
                "start_trade_index": start + 1,
                "end_trade_index": end,
                "start_time": start_time.isoformat(sep=" ") if start_time else "",
                "end_time": end_time.isoformat(sep=" ") if end_time else "",
                "trades_count": window_size,
                "mean_R": mean(window),
                "cumulative_R": sum(window),
                "min_cumulative_R": min_running,
                "max_drawdown_R": max_drawdown(window),
                "positive": sum(window) > 0,
            }
        )
    return output


def exit_profile_rows(rows: list[dict[str, str]], scope: str) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(normalize_exit_reason(row), []).append(row)
    total = len(rows)
    output: list[dict[str, object]] = []
    for reason in sorted(grouped):
        reason_rows = grouped[reason]
        values = [trade_r(row) for row in reason_rows]
        costs = [value for value in (cost_r(row) for row in reason_rows) if value is not None]
        nets = [value for value in (net_r(row) for row in reason_rows) if value is not None]
        output.append(
            {
                "scope": scope,
                "exit_reason": reason,
                "trades_count": len(reason_rows),
                "hit_rate": rate(len(reason_rows), total),
                "mean_R": mean(values),
                "cumulative_R": sum(values),
                "mean_cost_R": mean(costs),
                "mean_net_R": mean(nets),
            }
        )
    return output


def entry_hour_rows(rows: list[dict[str, str]], scope: str) -> list[dict[str, object]]:
    grouped: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        timestamp = row_timestamp(row, prefer_exit=False)
        if timestamp is None:
            continue
        grouped.setdefault(timestamp.hour, []).append(row)
    total = len(rows)
    output: list[dict[str, object]] = []
    for hour in sorted(grouped):
        hour_rows = grouped[hour]
        values = [trade_r(row) for row in hour_rows]
        output.append(
            {
                "scope": scope,
                "entry_hour": hour,
                "trades_count": len(hour_rows),
                "trade_pct": rate(len(hour_rows), total),
                "mean_R": mean(values),
                "cumulative_R": sum(values),
            }
        )
    return output


def drawdown_sequence_rows(rows: list[dict[str, str]], scope: str) -> list[dict[str, object]]:
    values = [trade_r(row) for row in rows]
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
                    drawdown_sequence_record(
                        rows,
                        scope,
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
            drawdown_sequence_record(
                rows,
                scope,
                sequence_id,
                start_index,
                trough_index,
                len(values),
                trough_drawdown,
                recovered=False,
            )
        )
    return output


def drawdown_sequence_record(
    rows: list[dict[str, str]],
    scope: str,
    sequence_id: int,
    start_index: int,
    trough_index: int,
    end_index: int,
    drawdown: float,
    *,
    recovered: bool,
) -> dict[str, object]:
    def timestamp_at(index: int) -> str:
        if index < 1 or index > len(rows):
            return ""
        timestamp = row_timestamp(rows[index - 1], prefer_exit=False)
        return timestamp.isoformat(sep=" ") if timestamp else ""

    return {
        "scope": scope,
        "sequence_id": sequence_id,
        "start_trade_index": start_index,
        "trough_trade_index": trough_index,
        "end_trade_index": end_index,
        "start_time": timestamp_at(start_index),
        "trough_time": timestamp_at(trough_index),
        "end_time": timestamp_at(end_index),
        "max_drawdown_R": drawdown,
        "duration_trades": max(0, end_index - start_index + 1),
        "recovered": recovered,
    }


def equity_summary(rows: list[dict[str, str]], scope: str) -> dict[str, object]:
    cumulative_values = [finite_float(row.get("cumulative_R")) for row in rows]
    drawdown_values = [finite_float(row.get("drawdown_R")) for row in rows]
    finite_cumulative = [value for value in cumulative_values if value is not None]
    finite_drawdown = [value for value in drawdown_values if value is not None]
    return {
        f"{scope}_equity_final_cumulative_R": finite_cumulative[-1] if finite_cumulative else None,
        f"{scope}_equity_max_drawdown_R": max(finite_drawdown) if finite_drawdown else None,
    }


def top_month_contribution_pct(monthly_rows: list[dict[str, object]], total_cumulative: float | None) -> float | None:
    if total_cumulative is None or total_cumulative <= 0:
        return None
    positive_months = [
        finite_float(row.get("cumulative_R"))
        for row in monthly_rows
        if str(row.get("scope") or "") == "stress"
    ]
    selected = [value for value in positive_months if value is not None and value > 0]
    if not selected:
        return None
    return max(selected) / total_cumulative * 100.0


def top_5_trade_contribution_pct(rows: list[dict[str, str]], total_cumulative: float | None) -> float | None:
    if total_cumulative is None or total_cumulative <= 0 or not rows:
        return None
    values = sorted((trade_r(row) for row in rows), reverse=True)
    count = max(1, math.ceil(len(values) * 0.05))
    return sum(values[:count]) / total_cumulative * 100.0


def positive_ratio(rows: list[dict[str, object]]) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if bool_value(row.get("positive"))) / len(rows)


def min_numeric(rows: list[dict[str, object]], key: str) -> float | None:
    values = [finite_float(row.get(key)) for row in rows]
    finite = [value for value in values if value is not None]
    return min(finite) if finite else None


def add_warning(
    warnings: list[dict[str, object]],
    *,
    severity: str,
    check: str,
    message: str,
    blocks_ready: bool = True,
) -> None:
    normalized_severity = normalize_warning_severity(severity)
    warnings.append(
        warning_row(
            warning_code=check,
            severity=normalized_severity,
            blocking=blocks_ready,
            message=message,
            related_stage="rule_review",
            related_metric=check,
            check=check,
            blocks_ready=bool(blocks_ready),
        )
    )


def next_action_for_classification(classification: str) -> str:
    if classification == READY_LABEL:
        return "Candidate can continue to controlled offline rule research expansion."
    if classification == RETAINED_LABEL:
        return "Candidate remains in offline rule review before controlled expansion."
    return "Candidate should not continue to controlled offline rule research expansion under current evidence."


def missing_candidate_metadata(row: dict[str, object]) -> list[str]:
    return [field for field in REQUIRED_CANDIDATE_METADATA_FIELDS if not str(row.get(field) or "").strip()]


def load_inputs(rule_replay_dir: Path) -> ReviewInputs:
    if not rule_replay_dir.exists():
        raise FileNotFoundError(f"Rule replay directory does not exist: {rule_replay_dir}")
    return ReviewInputs(
        rule_replay_dir=rule_replay_dir,
        replay_summary=first_csv_row(rule_replay_dir / INPUT_SUMMARY_FILE),
        comparison_rows=read_csv_rows(rule_replay_dir / INPUT_COMPARISON_FILE),
        base_trade_rows=read_csv_rows(rule_replay_dir / INPUT_BASE_TRADE_LOG_FILE),
        stress_trade_rows=read_csv_rows(rule_replay_dir / INPUT_STRESS_TRADE_LOG_FILE),
        base_equity_rows=read_csv_rows(rule_replay_dir / INPUT_BASE_EQUITY_FILE),
        stress_equity_rows=read_csv_rows(rule_replay_dir / INPUT_STRESS_EQUITY_FILE),
        replay_warning_rows=read_csv_rows(rule_replay_dir / INPUT_WARNINGS_FILE),
    )


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "output_dir": output_dir,
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "monthly": output_dir / MONTHLY_FILE,
        "yearly": output_dir / YEARLY_FILE,
        "rolling": output_dir / ROLLING_FILE,
        "exit_profile": output_dir / EXIT_PROFILE_FILE,
        "entry_hour": output_dir / ENTRY_HOUR_FILE,
        "drawdown_sequences": output_dir / DRAWDOWN_SEQUENCE_FILE,
    }


def ensure_can_write(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for key, path in paths.items() if key != "output_dir" and path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Rule-based review outputs already exist; pass --overwrite to replace: {joined}")


def inherited_blocking_warnings(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if bool_value(row.get("blocks_match"))
        or bool_value(row.get("blocks_ready"))
        or str(row.get("severity") or "").strip().lower() in {"error", "blocking"}
    ]


def build_review_outputs(
    *,
    run_id: str,
    output_dir: Path,
    inputs: ReviewInputs,
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    source = inputs.replay_summary
    base_metrics = trade_metrics(inputs.base_trade_rows)
    stress_metrics = trade_metrics(inputs.stress_trade_rows)
    base_exit_rows = exit_profile_rows(inputs.base_trade_rows, "base")
    stress_exit_rows = exit_profile_rows(inputs.stress_trade_rows, "stress")
    monthly_rows = [
        *group_period_rows(inputs.base_trade_rows, "base", "month"),
        *group_period_rows(inputs.stress_trade_rows, "stress", "month"),
    ]
    yearly_rows = [
        *group_period_rows(inputs.base_trade_rows, "base", "year"),
        *group_period_rows(inputs.stress_trade_rows, "stress", "year"),
    ]
    rolling_output_rows = [
        *rolling_rows(inputs.base_trade_rows, "base", 50),
        *rolling_rows(inputs.stress_trade_rows, "stress", 50),
        *rolling_rows(inputs.base_trade_rows, "base", 100),
        *rolling_rows(inputs.stress_trade_rows, "stress", 100),
    ]
    entry_rows = [
        *entry_hour_rows(inputs.base_trade_rows, "base"),
        *entry_hour_rows(inputs.stress_trade_rows, "stress"),
    ]
    drawdown_rows = [
        *drawdown_sequence_rows(inputs.base_trade_rows, "base"),
        *drawdown_sequence_rows(inputs.stress_trade_rows, "stress"),
    ]

    warnings: list[dict[str, object]] = []
    missing_metadata = missing_candidate_metadata(source)
    if missing_metadata:
        add_warning(
            warnings,
            severity="warning",
            check="candidate_metadata_missing",
            message="Candidate metadata is missing required field(s): " + ", ".join(missing_metadata),
        )
    replay_classification = str(source.get("final_rule_replay_classification") or "")
    logs_matched = bool_value(source.get("generated_logs_match_stress_validation"))
    comparison_logs_match = all(bool_value(row.get("trade_logs_match_within_tolerance")) for row in inputs.comparison_rows)
    if replay_classification != INPUT_MATCHED_LABEL:
        add_warning(
            warnings,
            severity="error",
            check="rule_replay_classification",
            message=f"Input rule replay classification is {replay_classification or 'missing'}, not {INPUT_MATCHED_LABEL}.",
        )
    if not logs_matched or not comparison_logs_match:
        add_warning(
            warnings,
            severity="error",
            check="generated_logs_match_stress_validation",
            message="Generated replay logs did not fully match the previous stress-validation logs.",
        )
    inherited_blocking = inherited_blocking_warnings(inputs.replay_warning_rows)
    for warning in inherited_blocking:
        add_warning(
            warnings,
            severity="error",
            check=f"inherited_{warning.get('check') or 'rule_replay_warning'}",
            message=f"Inherited blocking replay warning: {warning.get('message') or warning}.",
        )
    for warning in inputs.replay_warning_rows:
        if warning not in inherited_blocking:
            add_warning(
                warnings,
                severity="warning",
                check=f"inherited_{warning.get('check') or 'rule_replay_warning'}",
                message=f"Inherited non-blocking replay warning: {warning.get('message') or warning}.",
                blocks_ready=False,
            )

    stress_mean = finite_float(stress_metrics.get("mean_R"))
    stress_pf = finite_float(stress_metrics.get("profit_factor_R"))
    stress_cumulative = finite_float(stress_metrics.get("cumulative_R"))
    stress_drawdown = finite_float(stress_metrics.get("max_drawdown_R"))
    if stress_mean is None or stress_mean <= 0:
        add_warning(
            warnings,
            severity="error",
            check="stress_mean_R",
            message="Stress mean_R is not positive.",
        )
    if stress_pf is None or stress_pf <= 1:
        add_warning(
            warnings,
            severity="error",
            check="stress_profit_factor_R",
            message="Stress profit_factor_R is not greater than 1.",
        )
    if stress_cumulative is None or stress_cumulative <= 0:
        add_warning(
            warnings,
            severity="error",
            check="stress_cumulative_R",
            message="Stress cumulative_R is not positive.",
        )
    if stress_drawdown is None:
        add_warning(
            warnings,
            severity="error",
            check="stress_max_drawdown_R",
            message="Stress max_drawdown_R could not be reported from the trade log.",
        )
    if int(stress_metrics.get("trades_count") or 0) < MIN_TRADES:
        add_warning(
            warnings,
            severity="warning",
            check="too_few_trades",
            message=f"Stress replay has fewer than {MIN_TRADES} trades.",
        )

    stress_months = [row for row in monthly_rows if row.get("scope") == "stress"]
    stress_years = [row for row in yearly_rows if row.get("scope") == "stress"]
    stress_month_ratio = positive_ratio(stress_months)
    stress_year_ratio = positive_ratio(stress_years)
    negative_years = [row for row in stress_years if (finite_float(row.get("cumulative_R")) or 0.0) < 0]
    if stress_month_ratio is not None and stress_month_ratio < MONTHLY_POSITIVE_RATIO_MIN:
        add_warning(
            warnings,
            severity="warning",
            check="monthly_positive_ratio",
            message=f"Stress monthly positive ratio is below {MONTHLY_POSITIVE_RATIO_MIN}.",
        )
    if stress_year_ratio is None or not math.isclose(stress_year_ratio, 1.0, rel_tol=0.0, abs_tol=1e-12):
        add_warning(
            warnings,
            severity="warning",
            check="yearly_positive_ratio",
            message="Stress yearly positive ratio is below 1.0.",
        )
    if negative_years:
        add_warning(
            warnings,
            severity="warning",
            check="negative_year",
            message="At least one stress year has negative cumulative_R.",
        )

    stress_rolling_50 = [
        row for row in rolling_output_rows if row.get("scope") == "stress" and int(row.get("window_size") or 0) == 50
    ]
    stress_rolling_100 = [
        row for row in rolling_output_rows if row.get("scope") == "stress" and int(row.get("window_size") or 0) == 100
    ]
    if any((finite_float(row.get("cumulative_R")) or 0.0) <= 0 for row in stress_rolling_50):
        add_warning(
            warnings,
            severity="error",
            check="rolling_50_cumulative_R",
            message="At least one stress rolling 50-trade window has non-positive cumulative_R.",
        )
    if stress_rolling_100 and any((finite_float(row.get("cumulative_R")) or 0.0) <= 0 for row in stress_rolling_100):
        add_warning(
            warnings,
            severity="error",
            check="rolling_100_cumulative_R",
            message="At least one stress rolling 100-trade window has non-positive cumulative_R.",
        )

    stress_timeout = next((row for row in stress_exit_rows if row.get("exit_reason") == "TIMEOUT"), None)
    base_timeout = next((row for row in base_exit_rows if row.get("exit_reason") == "TIMEOUT"), None)
    stress_timeout_mean = finite_float(stress_timeout.get("mean_R")) if stress_timeout else None
    if stress_timeout_mean is not None and stress_timeout_mean <= TIMEOUT_MEAN_R_MIN:
        add_warning(
            warnings,
            severity="error",
            check="timeout_fragility",
            message=f"Stress TIMEOUT mean_R is <= {TIMEOUT_MEAN_R_MIN}.",
        )

    top_month_pct = top_month_contribution_pct(monthly_rows, stress_cumulative)
    top_5_pct = top_5_trade_contribution_pct(inputs.stress_trade_rows, stress_cumulative)
    if top_month_pct is not None and top_month_pct > TOP_MONTH_CONTRIBUTION_MAX_PCT:
        add_warning(
            warnings,
            severity="error",
            check="severe_top_month_contribution",
            message=f"Top stress month contribution exceeds {TOP_MONTH_CONTRIBUTION_MAX_PCT} percent.",
        )
    if top_5_pct is not None and top_5_pct > TOP_5_TRADE_CONTRIBUTION_MAX_PCT:
        add_warning(
            warnings,
            severity="error",
            check="severe_top_5_percent_contribution",
            message=f"Top 5 percent stress trade contribution exceeds {TOP_5_TRADE_CONTRIBUTION_MAX_PCT} percent.",
        )
    drawdown_to_cumulative = None
    if stress_drawdown is not None and stress_cumulative is not None and stress_cumulative > 0:
        drawdown_to_cumulative = stress_drawdown / stress_cumulative
        if drawdown_to_cumulative > DRAWDOWN_TO_CUMULATIVE_MAX:
            add_warning(
                warnings,
                severity="error",
                check="drawdown_to_cumulative_R",
                message=f"Stress max_drawdown_R/cumulative_R exceeds {DRAWDOWN_TO_CUMULATIVE_MAX}.",
            )

    blocking_count = sum(1 for warning in warnings if bool_value(warning.get("blocks_ready")))
    has_error = any(str(warning.get("severity") or "").lower() == "blocking" for warning in warnings)
    ready = blocking_count == 0
    if ready:
        classification = READY_LABEL
    elif has_error:
        classification = REJECTED_LABEL
    else:
        classification = RETAINED_LABEL

    base_timeout_mean = finite_float(base_timeout.get("mean_R")) if base_timeout else None
    stress_drawdown_sequences = [row for row in drawdown_rows if row.get("scope") == "stress"]
    largest_drawdown_sequence = max(
        (finite_float(row.get("max_drawdown_R")) or 0.0 for row in stress_drawdown_sequences),
        default=0.0,
    )
    largest_sequence_trades = max(
        (
            int(row.get("duration_trades") or 0)
            for row in stress_drawdown_sequences
            if (finite_float(row.get("max_drawdown_R")) or 0.0) == largest_drawdown_sequence
        ),
        default=0,
    )
    worst_month = min(stress_months, key=lambda row: finite_float(row.get("cumulative_R")) or 0.0, default={})
    best_month = max(stress_months, key=lambda row: finite_float(row.get("cumulative_R")) or 0.0, default={})

    base_equity = equity_summary(inputs.base_equity_rows, "base")
    stress_equity = equity_summary(inputs.stress_equity_rows, "stress")
    summary: dict[str, object] = {
        "run_id": run_id,
        "rule_replay_dir": str(inputs.rule_replay_dir),
        "review_output_dir": str(output_dir),
        "final_research_only_classification": classification,
        "ready_for_controlled_rule_research_backtest_expansion": ready,
        "warnings_count": len(warnings),
        "blocking_warnings_count": blocking_count,
        "symbol": source.get("symbol", ""),
        "direction": source.get("direction", ""),
        "timeframe": source.get("timeframe", ""),
        "horizon": source.get("horizon", ""),
        "target_family": source.get("target_family", ""),
        "regime_column": source.get("regime_column", ""),
        "regime_value": source.get("regime_value", ""),
        "feature_condition": source.get("feature_condition", ""),
        "tp_atr": source.get("tp_atr", ""),
        "sl_atr": source.get("sl_atr", ""),
        "atr_column": source.get("atr_column", ""),
        "same_bar_policy": source.get("same_bar_policy", ""),
        "bar_level_no_overlap": source.get("bar_level_no_overlap", ""),
        "stress_spread_policy": source.get("stress_spread_policy", ""),
        "input_rule_replay_classification": replay_classification,
        "generated_logs_match_stress_validation": logs_matched,
        "comparison_logs_match_all": comparison_logs_match,
        "inherited_warnings_count": len(inputs.replay_warning_rows),
        "inherited_blocking_warnings_count": len(inherited_blocking),
        "base_trades_count": base_metrics.get("trades_count"),
        "stress_trades_count": stress_metrics.get("trades_count"),
        "base_mean_R": base_metrics.get("mean_R"),
        "stress_mean_R": stress_metrics.get("mean_R"),
        "base_median_R": base_metrics.get("median_R"),
        "stress_median_R": stress_metrics.get("median_R"),
        "base_profit_factor_R": base_metrics.get("profit_factor_R"),
        "stress_profit_factor_R": stress_metrics.get("profit_factor_R"),
        "base_cumulative_R": base_metrics.get("cumulative_R"),
        "stress_cumulative_R": stress_metrics.get("cumulative_R"),
        "base_max_drawdown_R": base_metrics.get("max_drawdown_R"),
        "stress_max_drawdown_R": stress_metrics.get("max_drawdown_R"),
        "base_win_rate": base_metrics.get("win_rate"),
        "stress_win_rate": stress_metrics.get("win_rate"),
        "base_tp_hit_rate": base_metrics.get("tp_hit_rate"),
        "stress_tp_hit_rate": stress_metrics.get("tp_hit_rate"),
        "base_sl_hit_rate": base_metrics.get("sl_hit_rate"),
        "stress_sl_hit_rate": stress_metrics.get("sl_hit_rate"),
        "base_timeout_rate": base_metrics.get("timeout_rate"),
        "stress_timeout_rate": stress_metrics.get("timeout_rate"),
        **base_equity,
        **stress_equity,
        "mean_R_delta": numeric_delta(stress_metrics.get("mean_R"), base_metrics.get("mean_R")),
        "profit_factor_R_delta": numeric_delta(stress_metrics.get("profit_factor_R"), base_metrics.get("profit_factor_R")),
        "cumulative_R_delta": numeric_delta(stress_metrics.get("cumulative_R"), base_metrics.get("cumulative_R")),
        "max_drawdown_R_delta": numeric_delta(stress_metrics.get("max_drawdown_R"), base_metrics.get("max_drawdown_R")),
        "timeout_mean_R_delta": numeric_delta(stress_timeout_mean, base_timeout_mean),
        "stress_month_count": len(stress_months),
        "stress_monthly_positive_ratio": stress_month_ratio,
        "stress_worst_month": worst_month.get("period", ""),
        "stress_worst_month_cumulative_R": worst_month.get("cumulative_R", ""),
        "stress_best_month": best_month.get("period", ""),
        "stress_best_month_cumulative_R": best_month.get("cumulative_R", ""),
        "stress_year_count": len(stress_years),
        "stress_yearly_positive_ratio": stress_year_ratio,
        "stress_negative_year_count": len(negative_years),
        "stress_rolling_50_windows_count": len(stress_rolling_50),
        "stress_rolling_50_min_cumulative_R": min_numeric(stress_rolling_50, "cumulative_R"),
        "stress_rolling_50_min_running_cumulative_R": min_numeric(stress_rolling_50, "min_cumulative_R"),
        "stress_rolling_100_windows_count": len(stress_rolling_100),
        "stress_rolling_100_min_cumulative_R": min_numeric(stress_rolling_100, "cumulative_R"),
        "stress_rolling_100_min_running_cumulative_R": min_numeric(stress_rolling_100, "min_cumulative_R"),
        "stress_longest_losing_streak": stress_metrics.get("longest_losing_streak"),
        "stress_longest_non_positive_streak": stress_metrics.get("longest_non_positive_streak"),
        "stress_largest_drawdown_sequence_R": largest_drawdown_sequence,
        "stress_largest_drawdown_sequence_trades": largest_sequence_trades,
        "stress_timeout_mean_R": stress_timeout_mean,
        "stress_timeout_cumulative_R": finite_float(stress_timeout.get("cumulative_R")) if stress_timeout else None,
        "top_month_contribution_pct": top_month_pct,
        "top_5_percent_contribution_pct": top_5_pct,
        "stress_drawdown_to_cumulative_R": drawdown_to_cumulative,
    }
    add_common_summary_fields(
        summary,
        decision_scope="rule_review",
        final_classification=classification,
        next_action=next_action_for_classification(classification),
    )
    return summary, warnings, monthly_rows, yearly_rows, rolling_output_rows, [*base_exit_rows, *stress_exit_rows], entry_rows, drawdown_rows


def numeric_delta(left: object, right: object) -> float | None:
    left_number = finite_float(left)
    right_number = finite_float(right)
    if left_number is None or right_number is None:
        return None
    if math.isinf(left_number) or math.isinf(right_number):
        return 0.0 if left_number == right_number else float("inf")
    return left_number - right_number


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
    monthly_rows: list[dict[str, object]],
    yearly_rows: list[dict[str, object]],
    rolling_rows_for_report: list[dict[str, object]],
    exit_rows: list[dict[str, object]],
    entry_rows: list[dict[str, object]],
    drawdown_rows: list[dict[str, object]],
) -> str:
    warning_lines = [
        f"- {warning['severity']} `{warning['check']}`: {warning['message']}"
        for warning in warnings
    ] or ["No warnings."]
    stress_months = [row for row in monthly_rows if row.get("scope") == "stress"]
    stress_years = [row for row in yearly_rows if row.get("scope") == "stress"]
    stress_rolling = [row for row in rolling_rows_for_report if row.get("scope") == "stress"]
    stress_exits = [row for row in exit_rows if row.get("scope") == "stress"]
    stress_hours = [row for row in entry_rows if row.get("scope") == "stress"]
    stress_drawdowns = [row for row in drawdown_rows if row.get("scope") == "stress"]
    return "\n".join(
        [
            "# Rule-Based Regime Candidate Review",
            "",
            "## Research-Only Warning",
            "",
            "This is an offline review of already generated replay CSVs. It reads existing files only and does not rerun the replay, recompute entries, change assumptions, or create operational instructions.",
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
            f"- Rule replay dir: `{summary.get('rule_replay_dir')}`",
            f"- Review output dir: `{summary.get('review_output_dir')}`",
            "",
            "## Replay Consistency Summary",
            "",
            f"- Input classification: `{summary.get('input_rule_replay_classification')}`",
            f"- Generated logs matched previous stress validation: `{summary.get('generated_logs_match_stress_validation')}`",
            f"- Comparison rows all matched: `{summary.get('comparison_logs_match_all')}`",
            f"- Inherited warnings / blocking inherited warnings: `{summary.get('inherited_warnings_count')}` / `{summary.get('inherited_blocking_warnings_count')}`",
            "",
            "## Base vs Stress Summary",
            "",
            f"- Base mean_R / PF / cumulative_R / max_drawdown_R: `{summary.get('base_mean_R')}` / `{summary.get('base_profit_factor_R')}` / `{summary.get('base_cumulative_R')}` / `{summary.get('base_max_drawdown_R')}`",
            f"- Stress mean_R / PF / cumulative_R / max_drawdown_R: `{summary.get('stress_mean_R')}` / `{summary.get('stress_profit_factor_R')}` / `{summary.get('stress_cumulative_R')}` / `{summary.get('stress_max_drawdown_R')}`",
            f"- Stress minus base mean_R / PF / cumulative_R / max_drawdown_R: `{summary.get('mean_R_delta')}` / `{summary.get('profit_factor_R_delta')}` / `{summary.get('cumulative_R_delta')}` / `{summary.get('max_drawdown_R_delta')}`",
            f"- Timeout mean_R delta: `{summary.get('timeout_mean_R_delta')}`",
            "",
            "## Stress Monthly Diagnostics",
            "",
            f"- Monthly positive ratio: `{summary.get('stress_monthly_positive_ratio')}`",
            f"- Worst month: `{summary.get('stress_worst_month')}` (`{summary.get('stress_worst_month_cumulative_R')}` R)",
            f"- Best month: `{summary.get('stress_best_month')}` (`{summary.get('stress_best_month_cumulative_R')}` R)",
            "",
            *table_lines(stress_months, ["period", "trades_count", "mean_R", "cumulative_R", "positive"], limit=12),
            "",
            "## Stress Yearly Diagnostics",
            "",
            f"- Yearly positive ratio: `{summary.get('stress_yearly_positive_ratio')}`",
            f"- Negative year count: `{summary.get('stress_negative_year_count')}`",
            "",
            *table_lines(stress_years, ["period", "trades_count", "mean_R", "profit_factor_R", "cumulative_R", "max_drawdown_R"]),
            "",
            "## Rolling-Window Diagnostics",
            "",
            f"- Rolling 50 windows / min cumulative_R: `{summary.get('stress_rolling_50_windows_count')}` / `{summary.get('stress_rolling_50_min_cumulative_R')}`",
            f"- Rolling 100 windows / min cumulative_R: `{summary.get('stress_rolling_100_windows_count')}` / `{summary.get('stress_rolling_100_min_cumulative_R')}`",
            "",
            *table_lines(stress_rolling, ["window_size", "start_trade_index", "end_trade_index", "mean_R", "cumulative_R"], limit=12),
            "",
            "## Exit Profile And Timeout Fragility",
            "",
            f"- Stress TP/SL/TIMEOUT rates: `{summary.get('stress_tp_hit_rate')}` / `{summary.get('stress_sl_hit_rate')}` / `{summary.get('stress_timeout_rate')}`",
            f"- Stress TIMEOUT mean_R / cumulative_R: `{summary.get('stress_timeout_mean_R')}` / `{summary.get('stress_timeout_cumulative_R')}`",
            "",
            *table_lines(stress_exits, ["exit_reason", "trades_count", "hit_rate", "mean_R", "cumulative_R"]),
            "",
            "## Entry-Hour Distribution",
            "",
            *table_lines(stress_hours, ["entry_hour", "trades_count", "trade_pct", "mean_R", "cumulative_R"]),
            "",
            "## Drawdown Sequence Diagnostics",
            "",
            f"- Largest stress drawdown sequence: `{summary.get('stress_largest_drawdown_sequence_R')}` R across `{summary.get('stress_largest_drawdown_sequence_trades')}` trades",
            f"- Longest losing / non-positive streak: `{summary.get('stress_longest_losing_streak')}` / `{summary.get('stress_longest_non_positive_streak')}`",
            "",
            *table_lines(stress_drawdowns, ["sequence_id", "start_trade_index", "trough_trade_index", "max_drawdown_R", "duration_trades", "recovered"], limit=12),
            "",
            "## Concentration Diagnostics",
            "",
            f"- Top month contribution pct: `{summary.get('top_month_contribution_pct')}`",
            f"- Top 5 percent trade contribution pct: `{summary.get('top_5_percent_contribution_pct')}`",
            f"- Stress max_drawdown_R / cumulative_R: `{summary.get('stress_drawdown_to_cumulative_R')}`",
            "",
            "## Warnings",
            "",
            *warning_lines,
            "",
            "## Final Research-Only Classification",
            "",
            f"`{summary.get('final_research_only_classification')}`",
            "",
            "## Explicit Next Action",
            "",
            str(summary.get("next_action") or ""),
            "",
        ]
    )


def run_rule_based_review(args: argparse.Namespace) -> dict[str, Path]:
    rule_replay_dir = Path(args.rule_replay_dir)
    run_id = str(args.run_id or rule_replay_dir.name).strip()
    if not run_id:
        raise ValueError("--run-id is required when --rule-replay-dir has no final path name")
    paths = output_paths(Path(args.output_root), run_id)
    ensure_can_write(paths, bool(args.overwrite))
    inputs = load_inputs(rule_replay_dir)
    (
        summary,
        warnings,
        monthly_rows,
        yearly_rows,
        rolling_output_rows,
        exit_rows,
        entry_rows,
        drawdown_rows,
    ) = build_review_outputs(run_id=run_id, output_dir=paths["output_dir"], inputs=inputs)

    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_csv(paths["summary"], [summary], SUMMARY_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["monthly"], monthly_rows, PERIOD_FIELDNAMES)
    write_csv(paths["yearly"], yearly_rows, PERIOD_FIELDNAMES)
    write_csv(paths["rolling"], rolling_output_rows, ROLLING_FIELDNAMES)
    write_csv(paths["exit_profile"], exit_rows, EXIT_PROFILE_FIELDNAMES)
    write_csv(paths["entry_hour"], entry_rows, ENTRY_HOUR_FIELDNAMES)
    write_csv(paths["drawdown_sequences"], drawdown_rows, DRAWDOWN_SEQUENCE_FIELDNAMES)
    paths["report"].write_text(
        report_text(
            summary=summary,
            warnings=warnings,
            monthly_rows=monthly_rows,
            yearly_rows=yearly_rows,
            rolling_rows_for_report=rolling_output_rows,
            exit_rows=exit_rows,
            entry_rows=entry_rows,
            drawdown_rows=drawdown_rows,
        ),
        encoding="utf-8",
    )
    return paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        paths = run_rule_based_review(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Rule-based review written to {paths['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
