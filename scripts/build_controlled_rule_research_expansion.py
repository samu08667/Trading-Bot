"""Build a controlled research expansion package from existing rule reviews.

The script reads previously generated rule-review outputs and optional
rule-replay CSVs. It does not query the database, rerun a replay, add filters,
change TP/SL settings, or create operational instructions.
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
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "controlled_rule_research_expansion"

REVIEW_SUMMARY_FILE = "rule_based_review_summary.csv"
REVIEW_REPORT_FILE = "rule_based_review_report.md"
REVIEW_WARNINGS_FILE = "rule_based_review_warnings.csv"
REVIEW_MONTHLY_FILE = "rule_based_review_monthly.csv"
REVIEW_YEARLY_FILE = "rule_based_review_yearly.csv"
REVIEW_ROLLING_FILE = "rule_based_review_rolling_windows.csv"
REVIEW_EXIT_PROFILE_FILE = "rule_based_review_exit_profile.csv"
REVIEW_ENTRY_HOUR_FILE = "rule_based_review_entry_hour.csv"
REVIEW_DRAWDOWN_SEQUENCE_FILE = "rule_based_review_drawdown_sequences.csv"

REPLAY_SUMMARY_FILE = "rule_based_backtest_summary.csv"
REPLAY_BASE_TRADE_LOG_FILE = "rule_based_trade_log_base.csv"
REPLAY_STRESS_TRADE_LOG_FILE = "rule_based_trade_log_stress.csv"
REPLAY_BASE_EQUITY_FILE = "rule_based_equity_curve_base.csv"
REPLAY_STRESS_EQUITY_FILE = "rule_based_equity_curve_stress.csv"
REPLAY_COMPARISON_FILE = "rule_based_comparison_to_stress_validation.csv"
REPLAY_WARNINGS_FILE = "rule_based_warnings.csv"

SUMMARY_FILE = "controlled_rule_expansion_summary.csv"
REPORT_FILE = "controlled_rule_expansion_report.md"
WARNINGS_FILE = "controlled_rule_expansion_warnings.csv"
ENTRY_HOUR_FILE = "controlled_rule_expansion_entry_hour.csv"
SUBPERIODS_FILE = "controlled_rule_expansion_subperiods.csv"
TIMEOUT_FRAGILITY_FILE = "controlled_rule_expansion_timeout_fragility.csv"
COST_SENSITIVITY_PLAN_FILE = "controlled_rule_expansion_cost_sensitivity_plan.csv"
BASELINE_PLAN_FILE = "controlled_rule_expansion_baseline_plan.csv"

READY_INPUT_REVIEW_LABEL = "READY_FOR_CONTROLLED_RULE_RESEARCH_BACKTEST_EXPANSION"
MATCHED_REPLAY_LABEL = "RULE_REPLAY_MATCHED_STRESS_VALIDATION"
REJECTED_LABEL = "CONTROLLED_EXPANSION_REJECTED"
RETAINED_LABEL = "CONTROLLED_EXPANSION_RETAINED"
TIMEOUT_REVIEW_LABEL = "CONTROLLED_EXPANSION_RETAINED_FOR_TIMEOUT_REVIEW"
READY_LABEL = "READY_FOR_BASELINE_AND_COST_SENSITIVITY_REVIEW"

TOP_MONTH_CONTRIBUTION_MAX_PCT = 25.0
TOP_5_TRADE_CONTRIBUTION_MAX_PCT = 35.0
ENTRY_HOUR_DOMINANCE_MIN = 0.70
ENTRY_HOUR_MINORITY_MIN_TRADES = 10
TIMEOUT_MILD_LOSS_RATIO_MAX = 0.025
TIMEOUT_MILD_WORST_YEAR_LOSS_RATIO_MAX = 0.025
TIMEOUT_REVIEW_LOSS_RATIO_MAX = 0.05
TIMEOUT_REVIEW_NEGATIVE_YEAR_MAX = 3
TIMEOUT_SEVERE_LOSS_RATIO_MIN = 0.05
TIMEOUT_SEVERE_NEGATIVE_YEAR_MIN = 4
TIMEOUT_SEVERE_WORST_YEAR_LOSS_RATIO_MIN = 0.10
TIMEOUT_BLOCKING_LOSS_RATIO_MIN = 0.10
TIMEOUT_BLOCKING_NEGATIVE_YEAR_MIN = 4
TIMEOUT_BLOCKING_TOTAL_PROFIT_LOSS_RATIO_MIN = 0.25
DRAWDOWN_SEQUENCE_TO_CUMULATIVE_MAX = 0.20

REQUIRED_REVIEW_FILES = (
    REVIEW_SUMMARY_FILE,
    REVIEW_REPORT_FILE,
    REVIEW_WARNINGS_FILE,
    REVIEW_MONTHLY_FILE,
    REVIEW_YEARLY_FILE,
    REVIEW_ROLLING_FILE,
    REVIEW_EXIT_PROFILE_FILE,
    REVIEW_ENTRY_HOUR_FILE,
    REVIEW_DRAWDOWN_SEQUENCE_FILE,
)

REQUIRED_REPLAY_FILES = (
    REPLAY_SUMMARY_FILE,
    REPLAY_BASE_TRADE_LOG_FILE,
    REPLAY_STRESS_TRADE_LOG_FILE,
    REPLAY_BASE_EQUITY_FILE,
    REPLAY_STRESS_EQUITY_FILE,
    REPLAY_COMPARISON_FILE,
    REPLAY_WARNINGS_FILE,
)
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

WARNING_FIELDNAMES = [
    "warning_code",
    "check",
    "severity",
    "blocking",
    "blocks_ready",
    "message",
    "related_metric",
    "metric_value",
    "threshold",
]
WARNING_FIELDNAMES = with_common_warning_fields(WARNING_FIELDNAMES)

SUMMARY_FIELDNAMES = [
    "run_id",
    "rule_review_dir",
    "rule_replay_dir",
    "expansion_output_dir",
    "final_research_only_classification",
    "ready_for_baseline_and_cost_sensitivity_review",
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
    "stress_spread_policy",
    "input_review_classification",
    "input_rule_replay_classification",
    "generated_logs_match_stress_validation",
    "review_blocking_warnings_count",
    "stress_trades_count",
    "stress_mean_R",
    "stress_median_R",
    "stress_profit_factor_R",
    "stress_cumulative_R",
    "stress_max_drawdown_R",
    "yearly_positive_ratio",
    "monthly_positive_ratio",
    "rolling_50_min_cumulative_R",
    "rolling_100_min_cumulative_R",
    "top_month_contribution_pct",
    "top_5_percent_contribution_pct",
    "worst_month",
    "worst_month_cumulative_R",
    "worst_rolling_window",
    "worst_rolling_window_cumulative_R",
    "timeout_count",
    "timeout_trade_share",
    "timeout_mean_R",
    "timeout_cumulative_R",
    "timeout_cumulative_R_pct_of_stress_cumulative_R",
    "timeout_loss_vs_total_profit_pct",
    "timeout_negative_year_count",
    "timeout_worst_year",
    "timeout_worst_year_cumulative_R",
    "timeout_worst_month",
    "timeout_worst_month_cumulative_R",
    "timeout_positive_year_ratio",
    "timeout_positive_month_ratio",
    "timeout_severity",
    "largest_drawdown_sequence_R",
    "longest_losing_streak",
    "longest_non_positive_streak",
    "entry_hour_22_trades",
    "entry_hour_22_mean_R",
    "entry_hour_22_cumulative_R",
    "entry_hour_22_contribution_pct",
    "entry_hour_23_trades",
    "entry_hour_23_mean_R",
    "entry_hour_23_cumulative_R",
    "entry_hour_23_contribution_pct",
    "entry_hour_dominant_hour",
    "entry_hour_dominant_trade_share",
    "stress_subperiod_min_cumulative_R",
    "stress_subperiod_min_mean_R",
]
SUMMARY_FIELDNAMES = with_common_summary_fields(SUMMARY_FIELDNAMES)

ENTRY_HOUR_FIELDNAMES = [
    "scope",
    "entry_hour",
    "trades_count",
    "trade_pct",
    "mean_R",
    "cumulative_R",
    "contribution_pct",
    "is_22_23_pair",
    "dominance_role",
]

SUBPERIOD_FIELDNAMES = [
    "scope",
    "subperiod",
    "start_time",
    "end_time",
    "trades_count",
    "mean_R",
    "median_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
]

TIMEOUT_FIELDNAMES = [
    "scope",
    "period_type",
    "period",
    "timeout_count",
    "timeout_trade_pct",
    "timeout_mean_R",
    "timeout_cumulative_R",
    "timeout_cumulative_R_pct_of_stress_cumulative_R",
    "timeout_loss_vs_total_profit_pct",
    "timeout_negative_year_count",
    "timeout_worst_year",
    "timeout_worst_year_cumulative_R",
    "timeout_worst_month",
    "timeout_worst_month_cumulative_R",
    "timeout_positive_year_ratio",
    "timeout_positive_month_ratio",
    "timeout_severity",
]

PLAN_FIELDNAMES = ["plan_item", "comparison", "status", "existing_file_used", "notes"]


@dataclass(frozen=True)
class ReviewInputs:
    rule_review_dir: Path
    summary: dict[str, str]
    report_text: str
    warnings: list[dict[str, str]]
    monthly_rows: list[dict[str, str]]
    yearly_rows: list[dict[str, str]]
    rolling_rows: list[dict[str, str]]
    exit_rows: list[dict[str, str]]
    entry_hour_rows: list[dict[str, str]]
    drawdown_rows: list[dict[str, str]]


@dataclass(frozen=True)
class ReplayInputs:
    rule_replay_dir: Path
    summary: dict[str, str]
    base_trade_rows: list[dict[str, str]]
    stress_trade_rows: list[dict[str, str]]
    base_equity_rows: list[dict[str, str]]
    stress_equity_rows: list[dict[str, str]]
    comparison_rows: list[dict[str, str]]
    warnings: list[dict[str, str]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a controlled research expansion package from existing rule-review outputs."
    )
    parser.add_argument("--rule-review-dir", required=True, type=Path)
    parser.add_argument("--rule-replay-dir", type=Path)
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


def trade_r(row: dict[str, str]) -> float:
    return finite_float(row.get("R")) or 0.0


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
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def row_timestamp(row: dict[str, str]) -> datetime | None:
    return parse_timestamp(row.get("entry_time")) or parse_timestamp(row.get("exit_time"))


def add_warning(
    warnings: list[dict[str, object]],
    *,
    severity: str,
    check: str,
    message: str,
    blocks_ready: bool = True,
    warning_code: str | None = None,
    related_metric: str = "",
    metric_value: object = "",
    threshold: object = "",
) -> None:
    normalized_severity = normalize_warning_severity(severity)
    blocking = bool(blocks_ready) or normalized_severity == "blocking"
    warnings.append(
        warning_row(
            warning_code=warning_code or check,
            severity=normalized_severity,
            blocking=blocking,
            message=message,
            related_stage="controlled_expansion",
            related_metric=related_metric or check,
            metric_value=metric_value,
            threshold=threshold,
            check=check,
            blocks_ready=blocking,
        )
    )


def missing_candidate_metadata(row: dict[str, object]) -> list[str]:
    return [field for field in REQUIRED_CANDIDATE_METADATA_FIELDS if not str(row.get(field) or "").strip()]


def load_review_inputs(rule_review_dir: Path) -> ReviewInputs:
    if not rule_review_dir.exists():
        raise FileNotFoundError(f"Rule review directory does not exist: {rule_review_dir}")
    for filename in REQUIRED_REVIEW_FILES:
        path = rule_review_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required input file: {path}")
    return ReviewInputs(
        rule_review_dir=rule_review_dir,
        summary=first_csv_row(rule_review_dir / REVIEW_SUMMARY_FILE),
        report_text=(rule_review_dir / REVIEW_REPORT_FILE).read_text(encoding="utf-8"),
        warnings=read_csv_rows(rule_review_dir / REVIEW_WARNINGS_FILE),
        monthly_rows=read_csv_rows(rule_review_dir / REVIEW_MONTHLY_FILE),
        yearly_rows=read_csv_rows(rule_review_dir / REVIEW_YEARLY_FILE),
        rolling_rows=read_csv_rows(rule_review_dir / REVIEW_ROLLING_FILE),
        exit_rows=read_csv_rows(rule_review_dir / REVIEW_EXIT_PROFILE_FILE),
        entry_hour_rows=read_csv_rows(rule_review_dir / REVIEW_ENTRY_HOUR_FILE),
        drawdown_rows=read_csv_rows(rule_review_dir / REVIEW_DRAWDOWN_SEQUENCE_FILE),
    )


def load_replay_inputs(rule_replay_dir: Path | None) -> ReplayInputs | None:
    if rule_replay_dir is None:
        return None
    if not rule_replay_dir.exists():
        raise FileNotFoundError(f"Rule replay directory does not exist: {rule_replay_dir}")
    for filename in REQUIRED_REPLAY_FILES:
        path = rule_replay_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required input file: {path}")
    return ReplayInputs(
        rule_replay_dir=rule_replay_dir,
        summary=first_csv_row(rule_replay_dir / REPLAY_SUMMARY_FILE),
        base_trade_rows=read_csv_rows(rule_replay_dir / REPLAY_BASE_TRADE_LOG_FILE),
        stress_trade_rows=read_csv_rows(rule_replay_dir / REPLAY_STRESS_TRADE_LOG_FILE),
        base_equity_rows=read_csv_rows(rule_replay_dir / REPLAY_BASE_EQUITY_FILE),
        stress_equity_rows=read_csv_rows(rule_replay_dir / REPLAY_STRESS_EQUITY_FILE),
        comparison_rows=read_csv_rows(rule_replay_dir / REPLAY_COMPARISON_FILE),
        warnings=read_csv_rows(rule_replay_dir / REPLAY_WARNINGS_FILE),
    )


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "output_dir": output_dir,
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "entry_hour": output_dir / ENTRY_HOUR_FILE,
        "subperiods": output_dir / SUBPERIODS_FILE,
        "timeout_fragility": output_dir / TIMEOUT_FRAGILITY_FILE,
        "cost_sensitivity_plan": output_dir / COST_SENSITIVITY_PLAN_FILE,
        "baseline_plan": output_dir / BASELINE_PLAN_FILE,
    }


def ensure_can_write(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for key, path in paths.items() if key != "output_dir" and path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Controlled expansion outputs already exist; pass --overwrite to replace: {joined}")


def inherited_blocking_warnings(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if bool_value(row.get("blocking"))
        or bool_value(row.get("blocks_ready"))
        or bool_value(row.get("blocks_match"))
        or str(row.get("severity") or "").strip().lower() in {"error", "blocking"}
    ]


def entry_hour_expansion_rows(
    review_rows: list[dict[str, str]],
    stress_cumulative: float | None,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for row in review_rows:
        cumulative = finite_float(row.get("cumulative_R"))
        contribution = None
        if stress_cumulative is not None and stress_cumulative > 0 and str(row.get("scope")) == "stress":
            contribution = (cumulative or 0.0) / stress_cumulative * 100.0
        hour = str(row.get("entry_hour") or "").strip()
        selected.append(
            {
                "scope": row.get("scope", ""),
                "entry_hour": hour,
                "trades_count": row.get("trades_count", ""),
                "trade_pct": row.get("trade_pct", ""),
                "mean_R": row.get("mean_R", ""),
                "cumulative_R": row.get("cumulative_R", ""),
                "contribution_pct": contribution,
                "is_22_23_pair": hour in {"22", "23"},
                "dominance_role": "",
            }
        )
    stress_pair = [row for row in selected if row.get("scope") == "stress" and str(row.get("entry_hour")) in {"22", "23"}]
    if stress_pair:
        max_count = max(int(finite_float(row.get("trades_count")) or 0) for row in stress_pair)
        for row in stress_pair:
            count = int(finite_float(row.get("trades_count")) or 0)
            row["dominance_role"] = "dominant" if count == max_count else "minority"
    return selected


def hour_row(rows: list[dict[str, object]], hour: str) -> dict[str, object]:
    return next((row for row in rows if row.get("scope") == "stress" and str(row.get("entry_hour")) == hour), {})


def subperiod_rows_from_trades(rows: list[dict[str, str]], scope: str) -> list[dict[str, object]]:
    sorted_rows = sorted(rows, key=lambda row: row_timestamp(row) or datetime.max)
    if not sorted_rows:
        return []
    labels = ("early", "middle", "recent")
    output: list[dict[str, object]] = []
    total = len(sorted_rows)
    for index, label in enumerate(labels):
        start = math.floor(index * total / 3)
        end = math.floor((index + 1) * total / 3)
        subset = sorted_rows[start:end]
        if not subset:
            continue
        values = [trade_r(row) for row in subset]
        start_time = row_timestamp(subset[0])
        end_time = row_timestamp(subset[-1])
        output.append(
            {
                "scope": scope,
                "subperiod": label,
                "start_time": start_time.isoformat(sep=" ") if start_time else "",
                "end_time": end_time.isoformat(sep=" ") if end_time else "",
                "trades_count": len(subset),
                "mean_R": mean(values),
                "median_R": median(values),
                "profit_factor_R": profit_factor(values),
                "cumulative_R": sum(values),
                "max_drawdown_R": max_drawdown(values),
            }
        )
    return output


def timeout_rows_from_trades(rows: list[dict[str, str]], scope: str) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    timeout_rows = [row for row in rows if str(row.get("exit_reason") or "").strip().upper() == "TIMEOUT"]
    output.append(timeout_record(scope, "overall", "all", timeout_rows, len(rows)))
    by_year: dict[str, list[dict[str, str]]] = {}
    by_month: dict[str, list[dict[str, str]]] = {}
    for row in timeout_rows:
        timestamp = row_timestamp(row)
        if timestamp is None:
            continue
        by_year.setdefault(f"{timestamp.year:04d}", []).append(row)
        by_month.setdefault(f"{timestamp.year:04d}-{timestamp.month:02d}", []).append(row)
    for period in sorted(by_year):
        output.append(timeout_record(scope, "year", period, by_year[period], len(rows)))
    for period in sorted(by_month):
        output.append(timeout_record(scope, "month", period, by_month[period], len(rows)))
    return output


def timeout_record(
    scope: str,
    period_type: str,
    period: str,
    rows: list[dict[str, str]],
    total_trades: int,
) -> dict[str, object]:
    values = [trade_r(row) for row in rows]
    return {
        "scope": scope,
        "period_type": period_type,
        "period": period,
        "timeout_count": len(rows),
        "timeout_trade_pct": len(rows) / total_trades if total_trades else None,
        "timeout_mean_R": mean(values),
        "timeout_cumulative_R": sum(values),
    }


def fallback_timeout_rows(exit_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in exit_rows:
        if str(row.get("exit_reason") or "").strip().upper() != "TIMEOUT":
            continue
        output.append(
            {
                "scope": row.get("scope", ""),
                "period_type": "overall",
                "period": "all",
                "timeout_count": row.get("trades_count", ""),
                "timeout_trade_pct": row.get("hit_rate", ""),
                "timeout_mean_R": row.get("mean_R", ""),
                "timeout_cumulative_R": row.get("cumulative_R", ""),
            }
        )
    return output


def total_positive_R_from_trades(rows: list[dict[str, str]]) -> float | None:
    if not rows:
        return None
    return sum(value for value in (trade_r(row) for row in rows) if value > 0)


def timeout_period_diagnostics(
    timeout_rows: list[dict[str, object]],
    *,
    stress_cumulative: float | None,
    total_positive_R: float | None,
) -> dict[str, object]:
    stress_rows = [row for row in timeout_rows if row.get("scope") == "stress"]
    overall = next((row for row in stress_rows if row.get("period_type") == "overall"), {})
    year_rows = [row for row in stress_rows if row.get("period_type") == "year"]
    month_rows = [row for row in stress_rows if row.get("period_type") == "month"]
    timeout_count = int(finite_float(overall.get("timeout_count")) or 0)
    timeout_trade_share = finite_float(overall.get("timeout_trade_pct"))
    timeout_mean = finite_float(overall.get("timeout_mean_R"))
    timeout_cumulative = finite_float(overall.get("timeout_cumulative_R"))
    timeout_pct_of_stress = ratio_pct(timeout_cumulative, stress_cumulative)
    timeout_loss_vs_profit = None
    if timeout_cumulative is not None and timeout_cumulative < 0 and total_positive_R is not None and total_positive_R > 0:
        timeout_loss_vs_profit = abs(timeout_cumulative) / total_positive_R * 100.0
    negative_years = [row for row in year_rows if (finite_float(row.get("timeout_cumulative_R")) or 0.0) < 0]
    positive_year_ratio = positive_period_ratio(year_rows)
    positive_month_ratio = positive_period_ratio(month_rows)
    worst_year = min(
        year_rows,
        key=lambda row: finite_float(row.get("timeout_cumulative_R")) or 0.0,
        default={},
    )
    worst_month = min(
        month_rows,
        key=lambda row: finite_float(row.get("timeout_cumulative_R")) or 0.0,
        default={},
    )
    timeout_severity = classify_timeout_severity(
        timeout_cumulative=timeout_cumulative,
        stress_cumulative=stress_cumulative,
        total_positive_R=total_positive_R,
        negative_year_count=len(negative_years),
        worst_year_cumulative=finite_float(worst_year.get("timeout_cumulative_R")),
    )
    return {
        "timeout_count": timeout_count,
        "timeout_trade_share": timeout_trade_share,
        "timeout_mean_R": timeout_mean,
        "timeout_cumulative_R": timeout_cumulative,
        "timeout_cumulative_R_pct_of_stress_cumulative_R": timeout_pct_of_stress,
        "timeout_loss_vs_total_profit_pct": timeout_loss_vs_profit,
        "timeout_negative_year_count": len(negative_years),
        "timeout_worst_year": worst_year.get("period", ""),
        "timeout_worst_year_cumulative_R": finite_float(worst_year.get("timeout_cumulative_R")),
        "timeout_worst_month": worst_month.get("period", ""),
        "timeout_worst_month_cumulative_R": finite_float(worst_month.get("timeout_cumulative_R")),
        "timeout_positive_year_ratio": positive_year_ratio,
        "timeout_positive_month_ratio": positive_month_ratio,
        "timeout_severity": timeout_severity,
    }


def ratio_pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator * 100.0


def positive_period_ratio(rows: list[dict[str, object]]) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if (finite_float(row.get("timeout_cumulative_R")) or 0.0) > 0) / len(rows)


def classify_timeout_severity(
    *,
    timeout_cumulative: float | None,
    stress_cumulative: float | None,
    total_positive_R: float | None,
    negative_year_count: int,
    worst_year_cumulative: float | None,
) -> str:
    if timeout_cumulative is None or timeout_cumulative >= 0:
        return "timeout_ok"
    if stress_cumulative is None or stress_cumulative <= 0:
        return "timeout_review"
    loss_ratio = abs(timeout_cumulative) / stress_cumulative
    worst_year_loss_ratio = abs(worst_year_cumulative or 0.0) / stress_cumulative
    total_profit_loss_ratio = (
        abs(timeout_cumulative) / total_positive_R
        if total_positive_R is not None and total_positive_R > 0
        else None
    )
    if (
        loss_ratio > TIMEOUT_BLOCKING_LOSS_RATIO_MIN
        or negative_year_count >= TIMEOUT_BLOCKING_NEGATIVE_YEAR_MIN
        or (
            total_profit_loss_ratio is not None
            and total_profit_loss_ratio >= TIMEOUT_BLOCKING_TOTAL_PROFIT_LOSS_RATIO_MIN
        )
    ):
        return "timeout_blocking"
    if (
        loss_ratio > TIMEOUT_SEVERE_LOSS_RATIO_MIN
        or negative_year_count >= TIMEOUT_SEVERE_NEGATIVE_YEAR_MIN
        or worst_year_loss_ratio >= TIMEOUT_SEVERE_WORST_YEAR_LOSS_RATIO_MIN
    ):
        return "timeout_severe"
    if (
        loss_ratio <= TIMEOUT_MILD_LOSS_RATIO_MAX
        and negative_year_count <= 2
        and worst_year_loss_ratio <= TIMEOUT_MILD_WORST_YEAR_LOSS_RATIO_MAX
    ):
        return "timeout_mild_negative"
    if loss_ratio <= TIMEOUT_REVIEW_LOSS_RATIO_MAX and negative_year_count <= TIMEOUT_REVIEW_NEGATIVE_YEAR_MAX:
        return "timeout_review"
    return "timeout_severe"


def enrich_timeout_rows(
    timeout_rows: list[dict[str, object]],
    diagnostics: dict[str, object],
    *,
    stress_cumulative: float | None,
    total_positive_R: float | None,
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for row in timeout_rows:
        row_cumulative = finite_float(row.get("timeout_cumulative_R"))
        row_loss_vs_profit = None
        if row_cumulative is not None and row_cumulative < 0 and total_positive_R is not None and total_positive_R > 0:
            row_loss_vs_profit = abs(row_cumulative) / total_positive_R * 100.0
        enriched.append(
            {
                **row,
                "timeout_cumulative_R_pct_of_stress_cumulative_R": ratio_pct(row_cumulative, stress_cumulative),
                "timeout_loss_vs_total_profit_pct": row_loss_vs_profit,
                "timeout_negative_year_count": diagnostics.get("timeout_negative_year_count"),
                "timeout_worst_year": diagnostics.get("timeout_worst_year"),
                "timeout_worst_year_cumulative_R": diagnostics.get("timeout_worst_year_cumulative_R"),
                "timeout_worst_month": diagnostics.get("timeout_worst_month"),
                "timeout_worst_month_cumulative_R": diagnostics.get("timeout_worst_month_cumulative_R"),
                "timeout_positive_year_ratio": diagnostics.get("timeout_positive_year_ratio"),
                "timeout_positive_month_ratio": diagnostics.get("timeout_positive_month_ratio"),
                "timeout_severity": diagnostics.get("timeout_severity"),
            }
        )
    return enriched


def baseline_plan_rows(feature_condition: str, regime_column: str, regime_value: str) -> list[dict[str, object]]:
    filters = [part.strip() for part in str(feature_condition or "").split(" AND ") if part.strip()]
    filter_a = filters[0] if len(filters) >= 1 else "first exact filter"
    filter_b = filters[1] if len(filters) >= 2 else "second exact filter"
    regime_label = f"{regime_column}={regime_value}" if regime_column and regime_value else "same regime"
    return [
        {
            "plan_item": "broad_regime_baseline",
            "comparison": "exact rule vs broad regime baseline",
            "status": "planned_not_run",
            "existing_file_used": "",
            "notes": "Compare the exact reviewed condition with the same regime without exact feature filters.",
        },
        {
            "plan_item": "single_filter_baseline_a",
            "comparison": f"exact rule vs single-filter baseline A ({filter_a})",
            "status": "planned_not_run",
            "existing_file_used": "",
            "notes": "Use the first validated filter alone in a future controlled baseline review.",
        },
        {
            "plan_item": "single_filter_baseline_b",
            "comparison": f"exact rule vs single-filter baseline B ({filter_b})",
            "status": "planned_not_run",
            "existing_file_used": "",
            "notes": "Use the second validated filter alone in a future controlled baseline review.",
        },
        {
            "plan_item": "regime_no_feature_baseline",
            "comparison": f"exact rule vs no-feature {regime_label} baseline",
            "status": "planned_not_run",
            "existing_file_used": "",
            "notes": "Compare against the same regime context without feature filters in a future review.",
        },
    ]


def cost_plan_rows(stress_spread_policy: str) -> list[dict[str, object]]:
    return [
        {
            "plan_item": "current_conservative_stress",
            "comparison": "current max_row_or_fallback p90 stress",
            "status": "documented_existing_review",
            "existing_file_used": "",
            "notes": f"Current reviewed stress spread policy: {stress_spread_policy}.",
        },
        {
            "plan_item": "optional_p95_fallback_stress",
            "comparison": "optional p95 fallback spread stress",
            "status": "planned_not_run",
            "existing_file_used": "",
            "notes": "Future sensitivity only; do not alter the validated rule condition.",
        },
        {
            "plan_item": "optional_spread_multiplier_stress",
            "comparison": "optional spread multiplier stress",
            "status": "planned_not_run",
            "existing_file_used": "",
            "notes": "Future cost sensitivity only; keep base and stress outputs separate.",
        },
    ]


def build_expansion_outputs(
    *,
    run_id: str,
    output_dir: Path,
    review: ReviewInputs,
    replay: ReplayInputs | None,
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    source = review.summary
    warnings: list[dict[str, object]] = []
    missing_metadata = missing_candidate_metadata(source)
    if missing_metadata:
        add_warning(
            warnings,
            severity="review",
            check="candidate_metadata_missing",
            message="Candidate metadata is missing required field(s): " + ", ".join(missing_metadata),
            related_metric="candidate_metadata",
            metric_value=",".join(missing_metadata),
            threshold="all required metadata fields populated",
        )
    review_label = str(source.get("final_research_only_classification") or "")
    if review_label != READY_INPUT_REVIEW_LABEL:
        add_warning(
            warnings,
            severity="blocking",
            check="input_review_classification",
            message=f"Input review classification is {review_label or 'missing'}, not {READY_INPUT_REVIEW_LABEL}.",
            related_metric="final_research_only_classification",
            metric_value=review_label,
            threshold=READY_INPUT_REVIEW_LABEL,
        )
    review_blocking = inherited_blocking_warnings(review.warnings)
    for warning in review_blocking:
        add_warning(
            warnings,
            severity="blocking",
            check=f"inherited_review_{warning.get('check') or 'warning'}",
            message=f"Input review has a blocking warning: {warning.get('message') or warning}.",
            related_metric=str(warning.get("related_metric") or warning.get("check") or ""),
            metric_value=warning.get("metric_value", ""),
            threshold=warning.get("threshold", ""),
        )

    replay_label = str(source.get("input_rule_replay_classification") or "")
    logs_match = bool_value(source.get("generated_logs_match_stress_validation"))
    if replay is not None:
        replay_label = str(replay.summary.get("final_rule_replay_classification") or replay_label)
        logs_match = logs_match and bool_value(replay.summary.get("generated_logs_match_stress_validation"))
    if replay_label != MATCHED_REPLAY_LABEL:
        add_warning(
            warnings,
            severity="blocking",
            check="rule_replay_classification",
            message=f"Rule replay classification is {replay_label or 'missing'}, not {MATCHED_REPLAY_LABEL}.",
            related_metric="final_rule_replay_classification",
            metric_value=replay_label,
            threshold=MATCHED_REPLAY_LABEL,
        )
    if not logs_match:
        add_warning(
            warnings,
            severity="blocking",
            check="generated_logs_match_stress_validation",
            message="Rule replay logs were not confirmed as matching previous stress validation.",
            related_metric="generated_logs_match_stress_validation",
            metric_value=logs_match,
            threshold=True,
        )

    stress_mean = finite_float(source.get("stress_mean_R"))
    stress_pf = finite_float(source.get("stress_profit_factor_R"))
    stress_cumulative = finite_float(source.get("stress_cumulative_R"))
    stress_drawdown = finite_float(source.get("stress_max_drawdown_R"))
    yearly_ratio = finite_float(source.get("stress_yearly_positive_ratio") or source.get("yearly_positive_ratio"))
    monthly_ratio = finite_float(source.get("stress_monthly_positive_ratio") or source.get("monthly_positive_ratio"))
    rolling_50_min = finite_float(source.get("stress_rolling_50_min_cumulative_R") or source.get("rolling_50_min_cumulative_R"))
    rolling_100_min = finite_float(source.get("stress_rolling_100_min_cumulative_R") or source.get("rolling_100_min_cumulative_R"))
    top_month_pct = finite_float(source.get("top_month_contribution_pct"))
    top_5_pct = finite_float(source.get("top_5_percent_contribution_pct"))
    largest_dd_sequence = finite_float(source.get("stress_largest_drawdown_sequence_R") or source.get("largest_drawdown_sequence_R"))

    if stress_mean is None or stress_mean <= 0:
        add_warning(
            warnings,
            severity="blocking",
            check="stress_mean_R",
            message="Stress mean_R is not positive.",
            related_metric="stress_mean_R",
            metric_value=stress_mean,
            threshold="> 0",
        )
    if stress_pf is None or stress_pf <= 1:
        add_warning(
            warnings,
            severity="blocking",
            check="stress_profit_factor_R",
            message="Stress profit_factor_R is not greater than 1.",
            related_metric="stress_profit_factor_R",
            metric_value=stress_pf,
            threshold="> 1",
        )
    if stress_cumulative is None or stress_cumulative <= 0:
        add_warning(
            warnings,
            severity="blocking",
            check="stress_cumulative_R",
            message="Stress cumulative_R is not positive.",
            related_metric="stress_cumulative_R",
            metric_value=stress_cumulative,
            threshold="> 0",
        )
    if yearly_ratio is None or not math.isclose(yearly_ratio, 1.0, rel_tol=0.0, abs_tol=1e-12):
        add_warning(
            warnings,
            severity="blocking",
            check="yearly_positive_ratio",
            message="Stress yearly positive ratio is below 1.0.",
            related_metric="yearly_positive_ratio",
            metric_value=yearly_ratio,
            threshold="1.0",
        )
    if rolling_50_min is None or rolling_50_min <= 0:
        add_warning(
            warnings,
            severity="blocking",
            check="rolling_50_min_cumulative_R",
            message="Stress rolling 50-trade min cumulative_R is not positive.",
            related_metric="rolling_50_min_cumulative_R",
            metric_value=rolling_50_min,
            threshold="> 0",
        )
    if rolling_100_min is None or rolling_100_min <= 0:
        add_warning(
            warnings,
            severity="blocking",
            check="rolling_100_min_cumulative_R",
            message="Stress rolling 100-trade min cumulative_R is not positive.",
            related_metric="rolling_100_min_cumulative_R",
            metric_value=rolling_100_min,
            threshold="> 0",
        )
    if top_month_pct is not None and top_month_pct > TOP_MONTH_CONTRIBUTION_MAX_PCT:
        add_warning(
            warnings,
            severity="blocking",
            check="severe_top_month_contribution",
            message="Top month contribution is above the controlled threshold.",
            related_metric="top_month_contribution_pct",
            metric_value=top_month_pct,
            threshold=f"<= {TOP_MONTH_CONTRIBUTION_MAX_PCT}",
        )
    if top_5_pct is not None and top_5_pct > TOP_5_TRADE_CONTRIBUTION_MAX_PCT:
        add_warning(
            warnings,
            severity="blocking",
            check="severe_top_5_percent_contribution",
            message="Top 5 percent trade contribution is above the controlled threshold.",
            related_metric="top_5_percent_contribution_pct",
            metric_value=top_5_pct,
            threshold=f"<= {TOP_5_TRADE_CONTRIBUTION_MAX_PCT}",
        )
    if (
        largest_dd_sequence is not None
        and stress_cumulative is not None
        and stress_cumulative > 0
        and largest_dd_sequence / stress_cumulative > DRAWDOWN_SEQUENCE_TO_CUMULATIVE_MAX
    ):
        add_warning(
            warnings,
            severity="blocking",
            check="severe_drawdown_sequence",
            message="Largest drawdown sequence is too large relative to stress cumulative_R.",
            related_metric="largest_drawdown_sequence_R / stress_cumulative_R",
            metric_value=largest_dd_sequence / stress_cumulative,
            threshold=f"<= {DRAWDOWN_SEQUENCE_TO_CUMULATIVE_MAX}",
        )

    stress_year_rows = [row for row in review.yearly_rows if row.get("scope") == "stress"]
    if any((finite_float(row.get("cumulative_R")) or 0.0) < 0 for row in stress_year_rows):
        add_warning(
            warnings,
            severity="blocking",
            check="negative_year",
            message="At least one stress yearly row is negative.",
            related_metric="yearly cumulative_R",
            metric_value=min((finite_float(row.get("cumulative_R")) or 0.0 for row in stress_year_rows), default=""),
            threshold=">= 0",
        )

    worst_month = min(
        (row for row in review.monthly_rows if row.get("scope") == "stress"),
        key=lambda row: finite_float(row.get("cumulative_R")) or 0.0,
        default={},
    )
    worst_rolling = min(
        (row for row in review.rolling_rows if row.get("scope") == "stress"),
        key=lambda row: finite_float(row.get("cumulative_R")) or 0.0,
        default={},
    )

    entry_rows = entry_hour_expansion_rows(review.entry_hour_rows, stress_cumulative)
    hour_22 = hour_row(entry_rows, "22")
    hour_23 = hour_row(entry_rows, "23")
    hour_pair = [row for row in (hour_22, hour_23) if row]
    dominant_hour = ""
    dominant_share = None
    if len(hour_pair) == 2:
        counts = [(str(row.get("entry_hour")), int(finite_float(row.get("trades_count")) or 0)) for row in hour_pair]
        total_pair_count = sum(count for _hour, count in counts)
        if total_pair_count > 0:
            dominant_hour, dominant_count = max(counts, key=lambda item: item[1])
            dominant_share = dominant_count / total_pair_count
            minority_row = hour_22 if dominant_hour == "23" else hour_23
            minority_count = int(finite_float(minority_row.get("trades_count")) or 0)
            minority_mean = finite_float(minority_row.get("mean_R"))
            minority_cumulative = finite_float(minority_row.get("cumulative_R"))
            if (
                dominant_share >= ENTRY_HOUR_DOMINANCE_MIN
                and minority_count >= ENTRY_HOUR_MINORITY_MIN_TRADES
                and ((minority_mean is not None and minority_mean <= 0) or (minority_cumulative is not None and minority_cumulative <= 0))
            ):
                add_warning(
                    warnings,
                    severity="severe",
                    check="severe_entry_hour_fragility",
                    message="Hour 22/23 distribution is dominated by one hour while the other hour is weak or negative.",
                    blocks_ready=False,
                    related_metric="entry_hour_dominant_trade_share",
                    metric_value=dominant_share,
                    threshold=f"< {ENTRY_HOUR_DOMINANCE_MIN} or minority hour positive",
                )

    subperiod_rows: list[dict[str, object]] = []
    timeout_rows: list[dict[str, object]]
    if replay is not None:
        subperiod_rows = [
            *subperiod_rows_from_trades(replay.base_trade_rows, "base"),
            *subperiod_rows_from_trades(replay.stress_trade_rows, "stress"),
        ]
        timeout_rows = [
            *timeout_rows_from_trades(replay.base_trade_rows, "base"),
            *timeout_rows_from_trades(replay.stress_trade_rows, "stress"),
        ]
    else:
        timeout_rows = fallback_timeout_rows(review.exit_rows)
        add_warning(
            warnings,
            severity="info",
            check="rule_replay_dir_not_provided",
            message="Subperiod thirds were not computed because no rule replay folder was provided.",
            blocks_ready=False,
            related_metric="rule_replay_dir",
            metric_value="",
            threshold="provided for subperiod thirds",
        )
    stress_subperiods = [row for row in subperiod_rows if row.get("scope") == "stress"]
    stress_subperiod_min_cumulative = min(
        (finite_float(row.get("cumulative_R")) or 0.0 for row in stress_subperiods),
        default=None,
    )
    stress_subperiod_min_mean = min(
        (finite_float(row.get("mean_R")) or 0.0 for row in stress_subperiods),
        default=None,
    )

    total_positive_R = total_positive_R_from_trades(replay.stress_trade_rows) if replay is not None else None
    timeout_diagnostics = timeout_period_diagnostics(
        timeout_rows,
        stress_cumulative=stress_cumulative,
        total_positive_R=total_positive_R,
    )
    timeout_rows = enrich_timeout_rows(
        timeout_rows,
        timeout_diagnostics,
        stress_cumulative=stress_cumulative,
        total_positive_R=total_positive_R,
    )
    timeout_severity = str(timeout_diagnostics.get("timeout_severity") or "timeout_ok")
    timeout_cumulative = finite_float(timeout_diagnostics.get("timeout_cumulative_R"))
    timeout_pct = finite_float(timeout_diagnostics.get("timeout_cumulative_R_pct_of_stress_cumulative_R"))
    timeout_warning_metric = "timeout_cumulative_R_pct_of_stress_cumulative_R"
    timeout_warning_value = timeout_pct
    timeout_review_threshold = (
        f"mild <= {TIMEOUT_MILD_LOSS_RATIO_MAX * 100:.1f}% overall and "
        f"worst year <= {TIMEOUT_MILD_WORST_YEAR_LOSS_RATIO_MAX * 100:.1f}% of stress cumulative_R"
    )
    if timeout_severity == "timeout_mild_negative":
        add_warning(
            warnings,
            severity="info",
            check="timeout_mild_negative",
            message="Timeout cumulative_R is slightly negative but inside the mild research threshold.",
            blocks_ready=False,
            related_metric=timeout_warning_metric,
            metric_value=timeout_warning_value,
            threshold=timeout_review_threshold,
        )
    elif timeout_severity == "timeout_review":
        add_warning(
            warnings,
            severity="review",
            check="timeout_review_required",
            message="Timeout losses are not catastrophic, but they require a focused timeout fragility audit before expansion.",
            blocks_ready=False,
            related_metric=timeout_warning_metric,
            metric_value=timeout_warning_value,
            threshold=f"review if absolute loss <= {TIMEOUT_REVIEW_LOSS_RATIO_MAX * 100:.1f}% and negative years <= {TIMEOUT_REVIEW_NEGATIVE_YEAR_MAX}",
        )
    elif timeout_severity == "timeout_severe":
        add_warning(
            warnings,
            severity="severe",
            check="severe_timeout_fragility",
            message="Timeout fragility is severe but below catastrophic blocking thresholds.",
            blocks_ready=False,
            related_metric=timeout_warning_metric,
            metric_value=timeout_warning_value,
            threshold=(
                f"severe above {TIMEOUT_SEVERE_LOSS_RATIO_MIN * 100:.1f}% loss, "
                f"or worst year <= {TIMEOUT_SEVERE_WORST_YEAR_LOSS_RATIO_MIN * 100:.1f}% of stress cumulative_R"
            ),
        )
    elif timeout_severity == "timeout_blocking":
        add_warning(
            warnings,
            severity="blocking",
            check="timeout_blocking_fragility",
            message="Timeout fragility crosses catastrophic blocking thresholds.",
            related_metric=timeout_warning_metric,
            metric_value=timeout_warning_value,
            threshold=(
                f"blocking above {TIMEOUT_BLOCKING_LOSS_RATIO_MIN * 100:.1f}% stress cumulative_R, "
                f"negative years >= {TIMEOUT_BLOCKING_NEGATIVE_YEAR_MIN}, "
                f"or timeout loss >= {TIMEOUT_BLOCKING_TOTAL_PROFIT_LOSS_RATIO_MIN * 100:.1f}% of total positive_R"
            ),
        )

    baseline_plan = baseline_plan_rows(
        str(source.get("feature_condition") or ""),
        str(source.get("regime_column") or ""),
        str(source.get("regime_value") or ""),
    )
    cost_plan = cost_plan_rows(str(source.get("stress_spread_policy") or ""))

    blocking_count = sum(1 for warning in warnings if bool_value(warning.get("blocking")) or bool_value(warning.get("blocks_ready")))
    has_review_warning = any(str(warning.get("severity") or "").lower() in {"review", "severe"} for warning in warnings)
    ready = blocking_count == 0 and timeout_severity in {"timeout_ok", "timeout_mild_negative"} and not has_review_warning
    if ready:
        classification = READY_LABEL
    elif blocking_count > 0:
        classification = REJECTED_LABEL
    elif timeout_severity in {"timeout_review", "timeout_severe"}:
        classification = TIMEOUT_REVIEW_LABEL
    else:
        classification = RETAINED_LABEL

    summary: dict[str, object] = {
        "run_id": run_id,
        "rule_review_dir": str(review.rule_review_dir),
        "rule_replay_dir": str(replay.rule_replay_dir) if replay is not None else "",
        "expansion_output_dir": str(output_dir),
        "final_research_only_classification": classification,
        "ready_for_baseline_and_cost_sensitivity_review": ready,
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
        "same_bar_policy": source.get("same_bar_policy", ""),
        "stress_spread_policy": source.get("stress_spread_policy", ""),
        "input_review_classification": review_label,
        "input_rule_replay_classification": replay_label,
        "generated_logs_match_stress_validation": logs_match,
        "review_blocking_warnings_count": len(review_blocking),
        "stress_trades_count": source.get("stress_trades_count", ""),
        "stress_mean_R": stress_mean,
        "stress_median_R": finite_float(source.get("stress_median_R")),
        "stress_profit_factor_R": stress_pf,
        "stress_cumulative_R": stress_cumulative,
        "stress_max_drawdown_R": stress_drawdown,
        "yearly_positive_ratio": yearly_ratio,
        "monthly_positive_ratio": monthly_ratio,
        "rolling_50_min_cumulative_R": rolling_50_min,
        "rolling_100_min_cumulative_R": rolling_100_min,
        "top_month_contribution_pct": top_month_pct,
        "top_5_percent_contribution_pct": top_5_pct,
        "worst_month": worst_month.get("period", source.get("stress_worst_month", "")),
        "worst_month_cumulative_R": worst_month.get("cumulative_R", source.get("stress_worst_month_cumulative_R", "")),
        "worst_rolling_window": worst_rolling.get("start_trade_index", ""),
        "worst_rolling_window_cumulative_R": worst_rolling.get("cumulative_R", ""),
        "timeout_count": timeout_diagnostics.get("timeout_count"),
        "timeout_trade_share": timeout_diagnostics.get("timeout_trade_share"),
        "timeout_mean_R": timeout_diagnostics.get("timeout_mean_R"),
        "timeout_cumulative_R": timeout_diagnostics.get("timeout_cumulative_R"),
        "timeout_cumulative_R_pct_of_stress_cumulative_R": timeout_diagnostics.get("timeout_cumulative_R_pct_of_stress_cumulative_R"),
        "timeout_loss_vs_total_profit_pct": timeout_diagnostics.get("timeout_loss_vs_total_profit_pct"),
        "timeout_negative_year_count": timeout_diagnostics.get("timeout_negative_year_count"),
        "timeout_worst_year": timeout_diagnostics.get("timeout_worst_year"),
        "timeout_worst_year_cumulative_R": timeout_diagnostics.get("timeout_worst_year_cumulative_R"),
        "timeout_worst_month": timeout_diagnostics.get("timeout_worst_month"),
        "timeout_worst_month_cumulative_R": timeout_diagnostics.get("timeout_worst_month_cumulative_R"),
        "timeout_positive_year_ratio": timeout_diagnostics.get("timeout_positive_year_ratio"),
        "timeout_positive_month_ratio": timeout_diagnostics.get("timeout_positive_month_ratio"),
        "timeout_severity": timeout_severity,
        "largest_drawdown_sequence_R": largest_dd_sequence,
        "longest_losing_streak": source.get("stress_longest_losing_streak", ""),
        "longest_non_positive_streak": source.get("stress_longest_non_positive_streak", ""),
        "entry_hour_22_trades": hour_22.get("trades_count", ""),
        "entry_hour_22_mean_R": hour_22.get("mean_R", ""),
        "entry_hour_22_cumulative_R": hour_22.get("cumulative_R", ""),
        "entry_hour_22_contribution_pct": hour_22.get("contribution_pct", ""),
        "entry_hour_23_trades": hour_23.get("trades_count", ""),
        "entry_hour_23_mean_R": hour_23.get("mean_R", ""),
        "entry_hour_23_cumulative_R": hour_23.get("cumulative_R", ""),
        "entry_hour_23_contribution_pct": hour_23.get("contribution_pct", ""),
        "entry_hour_dominant_hour": dominant_hour,
        "entry_hour_dominant_trade_share": dominant_share,
        "stress_subperiod_min_cumulative_R": stress_subperiod_min_cumulative,
        "stress_subperiod_min_mean_R": stress_subperiod_min_mean,
    }
    add_common_summary_fields(
        summary,
        decision_scope="controlled_expansion",
        final_classification=classification,
        next_action=next_action_for_classification(classification),
    )
    return summary, warnings, entry_rows, subperiod_rows, timeout_rows, cost_plan, baseline_plan


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


def next_action_for_classification(classification: object) -> str:
    label = str(classification or "")
    if label == READY_LABEL:
        return "Candidate can continue to baseline and cost-sensitivity review."
    if label == TIMEOUT_REVIEW_LABEL:
        return "Candidate should remain in research review and receive a focused timeout fragility audit before baseline and cost-sensitivity expansion."
    if label == RETAINED_LABEL:
        return "Candidate should remain in controlled research review before further expansion."
    return "Candidate should not continue to baseline and cost-sensitivity review under current evidence."


def timeout_interpretation(summary: dict[str, object]) -> str:
    severity = str(summary.get("timeout_severity") or "timeout_ok")
    if severity in {"timeout_ok", "timeout_mild_negative"}:
        return "Timeout behavior does not block this expansion gate under the current thresholds."
    if severity in {"timeout_review", "timeout_severe"}:
        return "Timeout behavior does not force rejection, but it blocks promotion until a focused timeout audit is reviewed."
    return "Timeout behavior crosses catastrophic thresholds and blocks further expansion under current evidence."


def report_text(
    *,
    summary: dict[str, object],
    warnings: list[dict[str, object]],
    entry_rows: list[dict[str, object]],
    subperiod_rows: list[dict[str, object]],
    timeout_rows: list[dict[str, object]],
    cost_plan: list[dict[str, object]],
    baseline_plan: list[dict[str, object]],
) -> str:
    warning_lines = [
        f"- {warning['severity']} `{warning['check']}`: {warning['message']}"
        for warning in warnings
    ] or ["No warnings."]
    stress_hours = [row for row in entry_rows if row.get("scope") == "stress"]
    stress_subperiods = [row for row in subperiod_rows if row.get("scope") == "stress"]
    stress_timeouts = [row for row in timeout_rows if row.get("scope") == "stress"]
    next_action = next_action_for_classification(summary.get("final_research_only_classification"))
    return "\n".join(
        [
            "# Controlled Rule Research Expansion",
            "",
            "## Research-Only Warning",
            "",
            "This package reads existing rule-review and replay CSVs only. It does not rerun the replay, recompute entries, add filters, change TP/SL settings, or create operational instructions.",
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
            f"- Rule review dir: `{summary.get('rule_review_dir')}`",
            f"- Rule replay dir: `{summary.get('rule_replay_dir')}`",
            "",
            "## Previous Validation Chain Summary",
            "",
            f"- Input review classification: `{summary.get('input_review_classification')}`",
            f"- Input replay classification: `{summary.get('input_rule_replay_classification')}`",
            f"- Replay logs matched stress validation: `{summary.get('generated_logs_match_stress_validation')}`",
            f"- Review blocking warnings: `{summary.get('review_blocking_warnings_count')}`",
            "",
            "## Stress Robustness Recap",
            "",
            f"- Trades / mean_R / PF / cumulative_R: `{summary.get('stress_trades_count')}` / `{summary.get('stress_mean_R')}` / `{summary.get('stress_profit_factor_R')}` / `{summary.get('stress_cumulative_R')}`",
            f"- Max drawdown_R: `{summary.get('stress_max_drawdown_R')}`",
            f"- Yearly and monthly positive ratios: `{summary.get('yearly_positive_ratio')}` / `{summary.get('monthly_positive_ratio')}`",
            f"- Rolling 50/100 min cumulative_R: `{summary.get('rolling_50_min_cumulative_R')}` / `{summary.get('rolling_100_min_cumulative_R')}`",
            "",
            "## Entry-Hour Dependence",
            "",
            f"- Hour 22 trades / mean_R / cumulative_R / contribution pct: `{summary.get('entry_hour_22_trades')}` / `{summary.get('entry_hour_22_mean_R')}` / `{summary.get('entry_hour_22_cumulative_R')}` / `{summary.get('entry_hour_22_contribution_pct')}`",
            f"- Hour 23 trades / mean_R / cumulative_R / contribution pct: `{summary.get('entry_hour_23_trades')}` / `{summary.get('entry_hour_23_mean_R')}` / `{summary.get('entry_hour_23_cumulative_R')}` / `{summary.get('entry_hour_23_contribution_pct')}`",
            f"- Dominant hour / pair trade share: `{summary.get('entry_hour_dominant_hour')}` / `{summary.get('entry_hour_dominant_trade_share')}`",
            "",
            *table_lines(stress_hours, ["entry_hour", "trades_count", "mean_R", "cumulative_R", "contribution_pct"], limit=12),
            "",
            "## Subperiod Dependence",
            "",
            f"- Stress subperiod min cumulative_R / min mean_R: `{summary.get('stress_subperiod_min_cumulative_R')}` / `{summary.get('stress_subperiod_min_mean_R')}`",
            "",
            *table_lines(stress_subperiods, ["subperiod", "trades_count", "mean_R", "profit_factor_R", "cumulative_R", "max_drawdown_R"]),
            "",
            "## Timeout Fragility",
            "",
            f"- Timeout count / mean_R / cumulative_R: `{summary.get('timeout_count')}` / `{summary.get('timeout_mean_R')}` / `{summary.get('timeout_cumulative_R')}`",
            f"- Timeout trade share: `{summary.get('timeout_trade_share')}`",
            "",
            *table_lines(stress_timeouts, ["period_type", "period", "timeout_count", "timeout_mean_R", "timeout_cumulative_R", "timeout_cumulative_R_pct_of_stress_cumulative_R"], limit=14),
            "",
            "## Timeout Fragility Severity",
            "",
            f"- Timeout severity label: `{summary.get('timeout_severity')}`",
            f"- Timeout cumulative_R pct of stress cumulative_R: `{summary.get('timeout_cumulative_R_pct_of_stress_cumulative_R')}`",
            f"- Timeout loss vs total positive_R pct: `{summary.get('timeout_loss_vs_total_profit_pct')}`",
            f"- Negative timeout years: `{summary.get('timeout_negative_year_count')}`",
            f"- Worst timeout year / cumulative_R: `{summary.get('timeout_worst_year')}` / `{summary.get('timeout_worst_year_cumulative_R')}`",
            f"- Worst timeout month / cumulative_R: `{summary.get('timeout_worst_month')}` / `{summary.get('timeout_worst_month_cumulative_R')}`",
            f"- Positive timeout year/month ratios: `{summary.get('timeout_positive_year_ratio')}` / `{summary.get('timeout_positive_month_ratio')}`",
            f"- Interpretation: {timeout_interpretation(summary)}",
            "",
            "Threshold notes: `timeout_mild_negative` requires total timeout loss <= 2.5% of stress cumulative_R and worst-year timeout loss <= 2.5%; `timeout_review` allows total timeout loss <= 5% with at most 3 negative timeout years; `timeout_blocking` starts above 10% total timeout loss, 4 or more negative timeout years, or timeout loss >= 25% of total positive_R.",
            "",
            "## Drawdown And Recovery Behavior",
            "",
            f"- Largest drawdown sequence R: `{summary.get('largest_drawdown_sequence_R')}`",
            f"- Longest losing / non-positive streak: `{summary.get('longest_losing_streak')}` / `{summary.get('longest_non_positive_streak')}`",
            f"- Worst rolling window cumulative_R: `{summary.get('worst_rolling_window_cumulative_R')}`",
            "",
            "## Concentration Diagnostics",
            "",
            f"- Top month contribution pct: `{summary.get('top_month_contribution_pct')}`",
            f"- Top 5 percent trade contribution pct: `{summary.get('top_5_percent_contribution_pct')}`",
            f"- Worst month / cumulative_R: `{summary.get('worst_month')}` / `{summary.get('worst_month_cumulative_R')}`",
            "",
            "## Baseline Review Plan",
            "",
            *table_lines(baseline_plan, ["plan_item", "comparison", "status", "notes"]),
            "",
            "## Cost Sensitivity Review Plan",
            "",
            *table_lines(cost_plan, ["plan_item", "comparison", "status", "notes"]),
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
            next_action,
            "",
        ]
    )


def run_controlled_expansion(args: argparse.Namespace) -> dict[str, Path]:
    rule_review_dir = Path(args.rule_review_dir)
    run_id = str(args.run_id or rule_review_dir.name).strip()
    if not run_id:
        raise ValueError("--run-id is required when --rule-review-dir has no final path name")
    paths = output_paths(Path(args.output_root), run_id)
    ensure_can_write(paths, bool(args.overwrite))

    review = load_review_inputs(rule_review_dir)
    replay = load_replay_inputs(Path(args.rule_replay_dir) if args.rule_replay_dir else None)
    summary, warnings, entry_rows, subperiod_rows, timeout_rows, cost_plan, baseline_plan = build_expansion_outputs(
        run_id=run_id,
        output_dir=paths["output_dir"],
        review=review,
        replay=replay,
    )

    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_csv(paths["summary"], [summary], SUMMARY_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["entry_hour"], entry_rows, ENTRY_HOUR_FIELDNAMES)
    write_csv(paths["subperiods"], subperiod_rows, SUBPERIOD_FIELDNAMES)
    write_csv(paths["timeout_fragility"], timeout_rows, TIMEOUT_FIELDNAMES)
    write_csv(paths["cost_sensitivity_plan"], cost_plan, PLAN_FIELDNAMES)
    write_csv(paths["baseline_plan"], baseline_plan, PLAN_FIELDNAMES)
    paths["report"].write_text(
        report_text(
            summary=summary,
            warnings=warnings,
            entry_rows=entry_rows,
            subperiod_rows=subperiod_rows,
            timeout_rows=timeout_rows,
            cost_plan=cost_plan,
            baseline_plan=baseline_plan,
        ),
        encoding="utf-8",
    )
    return paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        paths = run_controlled_expansion(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Controlled expansion written to {paths['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
