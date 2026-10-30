"""Replay one reviewed regime candidate as an offline rule-replay audit.

This script reconstructs one exact reviewed candidate from existing review or
stress CSV outputs, replays it on historical ``ml_dataset`` rows, and compares
the generated sequence with the prior stress-validation files.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import math
from pathlib import Path
import sys
from typing import Any, Callable


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from validate_regime_candidate_stress import (
        CandidateScope,
        CandidateSpec,
        EQUITY_FIELDNAMES,
        STRESS_SPREAD_POLICIES,
        STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK,
        TRADE_LOG_FIELDNAMES,
        ReplayAudit,
        apply_bar_level_no_overlap,
        collect_replay_events,
        condition_text_from_filter_sets,
        equity_curve_rows,
        finite_or_infinite,
        finite_value,
        load_cost_config,
        load_path_rows,
        parse_horizon,
        path_config_for_spec,
        prepare_scope_predicate,
        replay_metrics,
        split_filter_text,
        trade_log_rows,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.validate_regime_candidate_stress import (
        CandidateScope,
        CandidateSpec,
        EQUITY_FIELDNAMES,
        STRESS_SPREAD_POLICIES,
        STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK,
        TRADE_LOG_FIELDNAMES,
        ReplayAudit,
        apply_bar_level_no_overlap,
        collect_replay_events,
        condition_text_from_filter_sets,
        equity_curve_rows,
        finite_or_infinite,
        finite_value,
        load_cost_config,
        load_path_rows,
        parse_horizon,
        path_config_for_spec,
        prepare_scope_predicate,
        replay_metrics,
        split_filter_text,
        trade_log_rows,
    )

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


DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "rule_based_regime_candidate_backtests"
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"

REVIEW_SUMMARY_FILE = "candidate_review_summary.csv"
STRESS_SUMMARY_FILE = "candidate_stress_summary.csv"
BASE_TRADE_LOG_FILE = "trade_log_base.csv"
STRESS_TRADE_LOG_FILE = "trade_log_stress.csv"
BASE_EQUITY_FILE = "equity_curve_base.csv"
STRESS_EQUITY_FILE = "equity_curve_stress.csv"

SUMMARY_FILE = "rule_based_backtest_summary.csv"
REPORT_FILE = "rule_based_backtest_report.md"
BASE_RULE_TRADE_LOG_FILE = "rule_based_trade_log_base.csv"
STRESS_RULE_TRADE_LOG_FILE = "rule_based_trade_log_stress.csv"
BASE_RULE_EQUITY_FILE = "rule_based_equity_curve_base.csv"
STRESS_RULE_EQUITY_FILE = "rule_based_equity_curve_stress.csv"
COMPARISON_FILE = "rule_based_comparison_to_stress_validation.csv"
WARNINGS_FILE = "rule_based_warnings.csv"
OUTPUT_FILES = (
    SUMMARY_FILE,
    REPORT_FILE,
    BASE_RULE_TRADE_LOG_FILE,
    STRESS_RULE_TRADE_LOG_FILE,
    BASE_RULE_EQUITY_FILE,
    STRESS_RULE_EQUITY_FILE,
    COMPARISON_FILE,
    WARNINGS_FILE,
)

READY_REVIEW_LABEL = "READY_FOR_RULE_BASED_RESEARCH_BACKTEST_REVIEW"
READY_STRESS_LABEL = "NEEDS_WALK_FORWARD_REVIEW"
MATCHED_LABEL = "RULE_REPLAY_MATCHED_STRESS_VALIDATION"
MINOR_LABEL = "RULE_REPLAY_MINOR_DIFFERENCES_REVIEW"
REJECTED_LABEL = "RULE_REPLAY_MISMATCH_REJECTED"
NUMERIC_TOLERANCE = 1e-9

WARNING_FIELDNAMES = with_common_warning_fields(["severity", "check", "blocks_match", "message"])
REQUIRED_CANDIDATE_METADATA_FIELDS = (
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
)

SUMMARY_FIELDNAMES = [
    "run_id",
    "review_package_dir",
    "stress_output_dir",
    "db_path",
    "final_rule_replay_classification",
    "generated_logs_match_stress_validation",
    "blocking_warnings_count",
    "warnings_count",
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
    "candidate_scope",
    "stress_spread_policy",
    "source_rows_loaded",
    "rows_matching_symbol_direction_regime",
    "rows_matching_feature_condition",
    "candidate_entries_before_no_overlap",
    "base_trades_count",
    "stress_trades_count",
    "base_mean_R",
    "stress_mean_R",
    "base_profit_factor_R",
    "stress_profit_factor_R",
    "base_cumulative_R",
    "stress_cumulative_R",
    "base_max_drawdown_R",
    "stress_max_drawdown_R",
    "base_trade_count_difference",
    "stress_trade_count_difference",
    "base_mean_R_difference",
    "stress_mean_R_difference",
    "base_cumulative_R_difference",
    "stress_cumulative_R_difference",
    "base_max_drawdown_R_difference",
    "stress_max_drawdown_R_difference",
    "first_mismatching_trade_timestamp",
    "missing_trades_count",
    "extra_trades_count",
]
SUMMARY_FIELDNAMES = with_common_summary_fields(SUMMARY_FIELDNAMES)

COMPARISON_FIELDNAMES = [
    "comparison_scope",
    "generated_trade_count",
    "previous_trade_count",
    "trade_count_difference",
    "mean_R_generated",
    "mean_R_previous",
    "mean_R_difference",
    "cumulative_R_generated",
    "cumulative_R_previous",
    "cumulative_R_difference",
    "max_drawdown_R_generated",
    "max_drawdown_R_previous",
    "max_drawdown_R_difference",
    "trade_logs_match_within_tolerance",
    "first_mismatching_trade_timestamp",
    "missing_trades",
    "extra_trades",
]


@dataclass(frozen=True)
class CandidateInputs:
    review_summary: dict[str, str] | None
    stress_summary: dict[str, str]
    review_package_dir: Path | None
    stress_output_dir: Path


RowLoader = Callable[[Path, str, str], list[dict[str, object]]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay one reviewed regime candidate and compare it with existing stress outputs."
    )
    parser.add_argument("--review-package-dir", type=Path)
    parser.add_argument("--stress-output-dir", type=Path)
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, type=Path)
    parser.add_argument("--cost-config", required=True, type=Path)
    parser.add_argument("--stress-cost-config", required=True, type=Path)
    parser.add_argument(
        "--stress-spread-policy",
        choices=STRESS_SPREAD_POLICIES,
        default=STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK,
    )
    parser.add_argument("--bar-level-no-overlap", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if not args.review_package_dir and not args.stress_output_dir:
        parser.error("one of --review-package-dir or --stress-output-dir is required")
    return args


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


def text_value(row: dict[str, str], key: str, default: str = "") -> str:
    return str(row.get(key) or default).strip()


def missing_candidate_metadata(row: dict[str, object]) -> list[str]:
    return [field for field in REQUIRED_CANDIDATE_METADATA_FIELDS if not str(row.get(field) or "").strip()]


def load_candidate_inputs(args: argparse.Namespace) -> CandidateInputs:
    review_summary: dict[str, str] | None = None
    review_dir = Path(args.review_package_dir) if args.review_package_dir else None
    stress_dir = Path(args.stress_output_dir) if args.stress_output_dir else None

    if review_dir is not None:
        review_summary = first_csv_row(review_dir / REVIEW_SUMMARY_FILE)
        if stress_dir is None:
            summary_stress_dir = text_value(review_summary, "stress_output_dir")
            if summary_stress_dir:
                stress_dir = Path(summary_stress_dir)
    if stress_dir is None:
        raise ValueError("--stress-output-dir is required when the review package does not reference it")
    stress_summary = first_csv_row(stress_dir / STRESS_SUMMARY_FILE)
    return CandidateInputs(
        review_summary=review_summary,
        stress_summary=stress_summary,
        review_package_dir=review_dir,
        stress_output_dir=stress_dir,
    )


def build_spec(source: dict[str, str]) -> CandidateSpec:
    missing_metadata = missing_candidate_metadata(source)
    if missing_metadata:
        raise ValueError("Candidate metadata is missing required field(s): " + ", ".join(missing_metadata))
    condition = text_value(source, "feature_condition")
    if not split_filter_text(condition):
        raise ValueError("Exact feature condition is required for rule replay.")
    return CandidateSpec(
        symbol=text_value(source, "symbol").upper(),
        direction=text_value(source, "direction").lower(),
        timeframe=text_value(source, "timeframe").upper(),
        horizon=parse_horizon(source.get("horizon")),
        target_family=text_value(source, "target_family"),
        regime_column=text_value(source, "regime_column"),
        regime_value=text_value(source, "regime_value"),
        tp_atr=float(text_value(source, "tp_atr")),
        sl_atr=float(text_value(source, "sl_atr")),
        atr_column=text_value(source, "atr_column", "atr_20"),
        same_bar_policy=text_value(source, "same_bar_policy", "stop_first"),
    )


def add_warning(
    warnings: list[dict[str, object]],
    *,
    severity: str,
    check: str,
    message: str,
    blocks_match: bool = True,
) -> None:
    normalized_severity = normalize_warning_severity(severity)
    warnings.append(
        warning_row(
            warning_code=check,
            severity=normalized_severity,
            blocking=blocks_match,
            message=message,
            related_stage="rule_replay",
            related_metric=check,
            check=check,
            blocks_match=bool(blocks_match),
        )
    )


def next_action_for_classification(classification: str) -> str:
    if classification == MATCHED_LABEL:
        return "Candidate can continue to offline rule-based research review."
    if classification == MINOR_LABEL:
        return "Candidate needs replay-difference review before continuing to offline rule-based research review."
    return "Candidate should not continue to offline rule-based research review under current replay evidence."


def validate_readiness(
    inputs: CandidateInputs,
    *,
    stress_spread_policy: str,
) -> None:
    stress = inputs.stress_summary
    if inputs.review_summary is not None:
        review_label = text_value(inputs.review_summary, "final_research_only_classification")
        if review_label != READY_REVIEW_LABEL:
            raise ValueError(f"Review package is not ready for rule replay: {review_label or 'missing'}")
    checks = {
        "candidate_scope": text_value(stress, "candidate_scope") == "exact_feature_combination",
        "exact_candidate_not_available_reason": text_value(stress, "exact_candidate_not_available_reason") == "",
        "stress_spread_policy": text_value(stress, "stress_spread_policy") == STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK,
        "stress_applied": bool_value(stress.get("stress_applied")),
        "stress_changed_cost_R": bool_value(
            stress.get("stress_changed_cost_R")
            if stress.get("stress_changed_cost_R") not in {None, ""}
            else stress.get("stress_cost_R_changed")
        ),
        "stress_cost_no_effect_warning": not bool_value(stress.get("stress_cost_no_effect_warning")),
        "stress_mean_R": (finite_value(stress.get("stress_mean_R")) or 0.0) > 0,
        "stress_profit_factor_R": (finite_or_infinite(stress.get("stress_profit_factor_R")) or 0.0) > 1,
        "random_baseline_available": bool_value(stress.get("random_baseline_available")),
        "candidate_mean_R_vs_random_p95": (finite_value(stress.get("candidate_mean_R_vs_random_p95")) or 0.0) > 0,
        "candidate_profit_factor_R_vs_random_p95": (
            finite_value(stress.get("candidate_profit_factor_R_vs_random_p95")) or 0.0
        )
        > 0,
        "yearly_positive_ratio": math.isclose(
            finite_value(stress.get("yearly_positive_ratio")) or -1.0,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        "final_research_label": text_value(stress, "final_research_label") == READY_STRESS_LABEL,
        "requested_policy": stress_spread_policy == STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("Rule replay readiness checks failed: " + ", ".join(failed))


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "output_dir": output_dir,
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "base_trade_log": output_dir / BASE_RULE_TRADE_LOG_FILE,
        "stress_trade_log": output_dir / STRESS_RULE_TRADE_LOG_FILE,
        "base_equity": output_dir / BASE_RULE_EQUITY_FILE,
        "stress_equity": output_dir / STRESS_RULE_EQUITY_FILE,
        "comparison": output_dir / COMPARISON_FILE,
        "warnings": output_dir / WARNINGS_FILE,
    }


def ensure_can_write(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for key, path in paths.items() if key != "output_dir" and path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Rule replay outputs already exist; pass --overwrite to replace: {joined}")


def event_metrics(events: list[Any], skipped: int = 0) -> dict[str, object]:
    return replay_metrics(events, skipped)


def numeric_difference(left: object, right: object) -> float | None:
    left_number = finite_or_infinite(left)
    right_number = finite_or_infinite(right)
    if left_number is None or right_number is None:
        return None
    if math.isinf(left_number) or math.isinf(right_number):
        return 0.0 if left_number == right_number else float("inf")
    return float(left_number) - float(right_number)


def previous_metric(stress_summary: dict[str, str], scope: str, key: str) -> object:
    if scope == "base":
        return stress_summary.get(key)
    prefixed = f"stress_{key}"
    return stress_summary.get(prefixed)


def row_key(row: dict[str, str]) -> str:
    return str(row.get("entry_time") or "").strip()


def compare_trade_logs(
    generated_rows: list[dict[str, object]],
    previous_rows: list[dict[str, str]],
) -> dict[str, object]:
    generated_by_key = {str(row.get("entry_time") or "").strip(): row for row in generated_rows}
    previous_by_key = {row_key(row): row for row in previous_rows}
    generated_keys = [str(row.get("entry_time") or "").strip() for row in generated_rows]
    previous_keys = [row_key(row) for row in previous_rows]
    missing = [key for key in previous_keys if key and key not in generated_by_key]
    extra = [key for key in generated_keys if key and key not in previous_by_key]
    first_mismatch = ""
    logs_match = len(generated_rows) == len(previous_rows)
    compare_fields = ("entry_time", "exit_time", "exit_reason")
    numeric_fields = ("entry_price", "exit_price", "R", "cost_R", "net_R")
    for index, generated_row in enumerate(generated_rows):
        if index >= len(previous_rows):
            first_mismatch = str(generated_row.get("entry_time") or "")
            logs_match = False
            break
        previous_row = previous_rows[index]
        for field in compare_fields:
            if str(generated_row.get(field) or "").strip().lower() != str(previous_row.get(field) or "").strip().lower():
                first_mismatch = str(generated_row.get("entry_time") or "")
                logs_match = False
                break
        if not logs_match:
            break
        for field in numeric_fields:
            delta = numeric_difference(generated_row.get(field), previous_row.get(field))
            if delta is None or abs(delta) > NUMERIC_TOLERANCE:
                first_mismatch = str(generated_row.get("entry_time") or "")
                logs_match = False
                break
        if not logs_match:
            break
    if not first_mismatch and missing:
        first_mismatch = missing[0]
    if not first_mismatch and extra:
        first_mismatch = extra[0]
    return {
        "trade_logs_match_within_tolerance": logs_match and not missing and not extra,
        "first_mismatching_trade_timestamp": first_mismatch,
        "missing_trades": ";".join(missing),
        "extra_trades": ";".join(extra),
        "missing_trades_count": len(missing),
        "extra_trades_count": len(extra),
    }


def comparison_row(
    *,
    scope: str,
    generated_metrics: dict[str, object],
    generated_rows: list[dict[str, object]],
    previous_rows: list[dict[str, str]],
    stress_summary: dict[str, str],
) -> dict[str, object]:
    log_comparison = compare_trade_logs(generated_rows, previous_rows)
    previous_count = finite_value(previous_metric(stress_summary, scope, "sequential_trades_count"))
    if previous_count is None:
        previous_count = float(len(previous_rows))
    generated_count = float(generated_metrics.get("sequential_trades_count") or 0)
    mean_previous = previous_metric(stress_summary, scope, "mean_R")
    cumulative_previous = previous_metric(stress_summary, scope, "cumulative_R")
    drawdown_previous = previous_metric(stress_summary, scope, "max_drawdown_R")
    return {
        "comparison_scope": scope,
        "generated_trade_count": int(generated_count),
        "previous_trade_count": int(previous_count),
        "trade_count_difference": int(generated_count - previous_count),
        "mean_R_generated": generated_metrics.get("mean_R"),
        "mean_R_previous": mean_previous,
        "mean_R_difference": numeric_difference(generated_metrics.get("mean_R"), mean_previous),
        "cumulative_R_generated": generated_metrics.get("cumulative_R"),
        "cumulative_R_previous": cumulative_previous,
        "cumulative_R_difference": numeric_difference(generated_metrics.get("cumulative_R"), cumulative_previous),
        "max_drawdown_R_generated": generated_metrics.get("max_drawdown_R"),
        "max_drawdown_R_previous": drawdown_previous,
        "max_drawdown_R_difference": numeric_difference(generated_metrics.get("max_drawdown_R"), drawdown_previous),
        **log_comparison,
    }


def blocking_metric_mismatch(row: dict[str, object]) -> bool:
    for key in ("mean_R_difference", "cumulative_R_difference", "max_drawdown_R_difference"):
        value = finite_or_infinite(row.get(key))
        if value is None or abs(value) > NUMERIC_TOLERANCE:
            return True
    return False


def classify_replay(
    comparison_rows: list[dict[str, object]],
    warnings: list[dict[str, object]],
    stress_metrics: dict[str, object],
) -> str:
    blocking = any(bool(warning.get("blocks_match")) for warning in warnings)
    stress_mean = finite_value(stress_metrics.get("mean_R"))
    stress_pf = finite_or_infinite(stress_metrics.get("profit_factor_R"))
    if blocking or stress_mean is None or stress_mean <= 0 or stress_pf is None or stress_pf <= 1:
        return REJECTED_LABEL
    if any(blocking_metric_mismatch(row) for row in comparison_rows):
        return REJECTED_LABEL
    all_logs_match = all(bool(row.get("trade_logs_match_within_tolerance")) for row in comparison_rows)
    count_diffs = [abs(int(row.get("trade_count_difference") or 0)) for row in comparison_rows]
    if all_logs_match and not any(count_diffs):
        return MATCHED_LABEL
    if max(count_diffs, default=0) <= 2:
        return MINOR_LABEL
    return REJECTED_LABEL


def report_text(
    *,
    summary: dict[str, object],
    comparison_rows: list[dict[str, object]],
    warnings: list[dict[str, object]],
) -> str:
    warning_lines = [
        f"- {warning['severity']} `{warning['check']}`: {warning['message']}"
        for warning in warnings
    ] or ["No warnings."]
    comparison_lines = [
        (
            "- {scope}: trade_delta={trade_delta}, mean_delta={mean_delta}, cumulative_delta={cum_delta}, "
            "drawdown_delta={dd_delta}, logs_match={logs_match}, first_mismatch={first_mismatch}"
        ).format(
            scope=row.get("comparison_scope"),
            trade_delta=row.get("trade_count_difference"),
            mean_delta=row.get("mean_R_difference"),
            cum_delta=row.get("cumulative_R_difference"),
            dd_delta=row.get("max_drawdown_R_difference"),
            logs_match=row.get("trade_logs_match_within_tolerance"),
            first_mismatch=row.get("first_mismatching_trade_timestamp"),
        )
        for row in comparison_rows
    ]
    return "\n".join(
        [
            "# Rule-Based Regime Candidate Replay Report",
            "",
            "## Research-Only Warning",
            "",
            "This is an offline replay audit for one reviewed candidate. It does not change the candidate, tune TP/SL, add filters, or create operational instructions.",
            "",
            "## Candidate Definition",
            "",
            f"- Symbol: `{summary.get('symbol')}`",
            f"- Direction: `{summary.get('direction')}`",
            f"- Timeframe: `{summary.get('timeframe')}`",
            f"- Horizon: `h{summary.get('horizon')}`",
            f"- Target family: `{summary.get('target_family')}`",
            f"- Regime: `{summary.get('regime_column')}={summary.get('regime_value')}`",
            f"- Feature condition: `{summary.get('feature_condition')}`",
            f"- TP/SL ATR: `{summary.get('tp_atr')}` / `{summary.get('sl_atr')}`",
            f"- Same-bar policy: `{summary.get('same_bar_policy')}`",
            "",
            "## Input Sources",
            "",
            f"- Review package dir: `{summary.get('review_package_dir')}`",
            f"- Stress output dir: `{summary.get('stress_output_dir')}`",
            f"- DB path: `{summary.get('db_path')}`",
            "",
            "## Rule Reconstruction",
            "",
            f"- Candidate scope: `{summary.get('candidate_scope')}`",
            f"- Source rows loaded: `{summary.get('source_rows_loaded')}`",
            f"- Rows matching symbol/direction/regime: `{summary.get('rows_matching_symbol_direction_regime')}`",
            f"- Rows matching feature condition: `{summary.get('rows_matching_feature_condition')}`",
            f"- Entries before no-overlap: `{summary.get('candidate_entries_before_no_overlap')}`",
            f"- Bar-level no-overlap: `{summary.get('bar_level_no_overlap')}`",
            "",
            "## Base Replay Metrics",
            "",
            f"- Trades: `{summary.get('base_trades_count')}`",
            f"- Mean R: `{summary.get('base_mean_R')}`",
            f"- PF R: `{summary.get('base_profit_factor_R')}`",
            f"- Cumulative R: `{summary.get('base_cumulative_R')}`",
            f"- Max drawdown R: `{summary.get('base_max_drawdown_R')}`",
            "",
            "## Stress Replay Metrics",
            "",
            f"- Trades: `{summary.get('stress_trades_count')}`",
            f"- Mean R: `{summary.get('stress_mean_R')}`",
            f"- PF R: `{summary.get('stress_profit_factor_R')}`",
            f"- Cumulative R: `{summary.get('stress_cumulative_R')}`",
            f"- Max drawdown R: `{summary.get('stress_max_drawdown_R')}`",
            f"- Stress spread policy: `{summary.get('stress_spread_policy')}`",
            "",
            "## Comparison To Previous Stress Validation",
            "",
            *comparison_lines,
            "",
            "## Trade-Log Matching Diagnostics",
            "",
            f"- Generated logs match previous files: `{summary.get('generated_logs_match_stress_validation')}`",
            f"- First mismatching timestamp: `{summary.get('first_mismatching_trade_timestamp')}`",
            f"- Missing trades count: `{summary.get('missing_trades_count')}`",
            f"- Extra trades count: `{summary.get('extra_trades_count')}`",
            "",
            "## Equity/Drawdown Diagnostics",
            "",
            f"- Base cumulative difference: `{summary.get('base_cumulative_R_difference')}`",
            f"- Stress cumulative difference: `{summary.get('stress_cumulative_R_difference')}`",
            f"- Base drawdown difference: `{summary.get('base_max_drawdown_R_difference')}`",
            f"- Stress drawdown difference: `{summary.get('stress_max_drawdown_R_difference')}`",
            "",
            "## Warnings",
            "",
            *warning_lines,
            "",
            "## Final Rule-Replay Classification",
            "",
            f"`{summary.get('final_rule_replay_classification')}`",
            "",
            "## Explicit Next Action",
            "",
            str(summary.get("next_action") or ""),
            "",
        ]
    )


def run_rule_replay(args: argparse.Namespace, *, row_loader: RowLoader = load_path_rows) -> dict[str, Path]:
    inputs = load_candidate_inputs(args)
    validate_readiness(inputs, stress_spread_policy=str(args.stress_spread_policy))
    spec = build_spec(inputs.stress_summary)
    filter_set = split_filter_text(inputs.stress_summary.get("feature_condition"))
    scope = CandidateScope(
        name="exact_feature_combination",
        filter_sets=(filter_set,),
        condition_text=condition_text_from_filter_sets((filter_set,)),
    )
    run_id = str(args.run_id or inputs.stress_output_dir.name).strip()
    if not run_id:
        raise ValueError("--run-id is required when input folders have no final path name")
    paths = output_paths(Path(args.output_root), run_id)
    ensure_can_write(paths, bool(args.overwrite))

    rows = row_loader(Path(args.db_path), spec.symbol, spec.timeframe)
    prepared_scope, scope_predicate = prepare_scope_predicate(rows, scope)
    if prepared_scope.exact_candidate_not_available_reason:
        raise ValueError(prepared_scope.exact_candidate_not_available_reason)

    base_cost_config = load_cost_config(Path(args.cost_config))
    stress_cost_config = load_cost_config(Path(args.stress_cost_config))
    no_overlap = bool(args.bar_level_no_overlap) or bool_value(inputs.stress_summary.get("bar_level_no_overlap"))

    audit = ReplayAudit(source_rows_loaded=len(rows))
    base_events = collect_replay_events(
        rows,
        spec,
        config=path_config_for_spec(spec, cost_mode="estimated", return_mode="net"),
        cost_config=base_cost_config,
        scope=prepared_scope,
        scope_predicate=scope_predicate,
        audit=audit,
    )
    base_result = apply_bar_level_no_overlap(base_events, no_overlap)
    stress_events = collect_replay_events(
        rows,
        spec,
        config=path_config_for_spec(spec, cost_mode="estimated", return_mode="net"),
        cost_config=stress_cost_config,
        scope=prepared_scope,
        scope_predicate=scope_predicate,
        stress_spread_policy=str(args.stress_spread_policy),
    )
    stress_result = apply_bar_level_no_overlap(stress_events, no_overlap)

    base_metrics = event_metrics(base_result.events, base_result.skipped_due_to_overlap)
    stress_metrics = event_metrics(stress_result.events, stress_result.skipped_due_to_overlap)
    base_trade_rows = trade_log_rows(base_result.events)
    stress_trade_rows = trade_log_rows(stress_result.events)
    previous_base_rows = read_csv_rows(inputs.stress_output_dir / BASE_TRADE_LOG_FILE)
    previous_stress_rows = read_csv_rows(inputs.stress_output_dir / STRESS_TRADE_LOG_FILE)
    read_csv_rows(inputs.stress_output_dir / BASE_EQUITY_FILE)
    read_csv_rows(inputs.stress_output_dir / STRESS_EQUITY_FILE)

    comparison_rows = [
        comparison_row(
            scope="base",
            generated_metrics=base_metrics,
            generated_rows=base_trade_rows,
            previous_rows=previous_base_rows,
            stress_summary=inputs.stress_summary,
        ),
        comparison_row(
            scope="stress",
            generated_metrics=stress_metrics,
            generated_rows=stress_trade_rows,
            previous_rows=previous_stress_rows,
            stress_summary=inputs.stress_summary,
        ),
    ]
    warnings: list[dict[str, object]] = []
    for row in comparison_rows:
        if blocking_metric_mismatch(row):
            add_warning(
                warnings,
                severity="error",
                check=f"{row.get('comparison_scope')}_metric_mismatch",
                message="Generated replay metrics differ from previous stress-validation metrics above tolerance.",
            )
    first_mismatch = next(
        (str(row.get("first_mismatching_trade_timestamp") or "") for row in comparison_rows if row.get("first_mismatching_trade_timestamp")),
        "",
    )
    missing_count = sum(int(row.get("missing_trades_count") or 0) for row in comparison_rows)
    extra_count = sum(int(row.get("extra_trades_count") or 0) for row in comparison_rows)
    logs_match = all(bool(row.get("trade_logs_match_within_tolerance")) for row in comparison_rows)
    classification = classify_replay(comparison_rows, warnings, stress_metrics)
    blocking_count = sum(1 for warning in warnings if bool(warning.get("blocks_match")))
    summary = {
        "run_id": run_id,
        "review_package_dir": str(inputs.review_package_dir or ""),
        "stress_output_dir": str(inputs.stress_output_dir),
        "db_path": str(args.db_path),
        "final_rule_replay_classification": classification,
        "generated_logs_match_stress_validation": logs_match,
        "blocking_warnings_count": blocking_count,
        "warnings_count": len(warnings),
        "symbol": spec.symbol,
        "direction": spec.direction,
        "timeframe": spec.timeframe,
        "horizon": spec.horizon,
        "target_family": spec.target_family,
        "regime_column": spec.regime_column,
        "regime_value": spec.regime_value,
        "feature_condition": prepared_scope.condition_text,
        "tp_atr": spec.tp_atr,
        "sl_atr": spec.sl_atr,
        "atr_column": spec.atr_column,
        "same_bar_policy": spec.same_bar_policy,
        "bar_level_no_overlap": no_overlap,
        "candidate_scope": prepared_scope.name,
        "stress_spread_policy": str(args.stress_spread_policy),
        **audit.as_summary_fields(),
        "base_trades_count": base_metrics.get("sequential_trades_count"),
        "stress_trades_count": stress_metrics.get("sequential_trades_count"),
        "base_mean_R": base_metrics.get("mean_R"),
        "stress_mean_R": stress_metrics.get("mean_R"),
        "base_profit_factor_R": base_metrics.get("profit_factor_R"),
        "stress_profit_factor_R": stress_metrics.get("profit_factor_R"),
        "base_cumulative_R": base_metrics.get("cumulative_R"),
        "stress_cumulative_R": stress_metrics.get("cumulative_R"),
        "base_max_drawdown_R": base_metrics.get("max_drawdown_R"),
        "stress_max_drawdown_R": stress_metrics.get("max_drawdown_R"),
        "base_trade_count_difference": comparison_rows[0].get("trade_count_difference"),
        "stress_trade_count_difference": comparison_rows[1].get("trade_count_difference"),
        "base_mean_R_difference": comparison_rows[0].get("mean_R_difference"),
        "stress_mean_R_difference": comparison_rows[1].get("mean_R_difference"),
        "base_cumulative_R_difference": comparison_rows[0].get("cumulative_R_difference"),
        "stress_cumulative_R_difference": comparison_rows[1].get("cumulative_R_difference"),
        "base_max_drawdown_R_difference": comparison_rows[0].get("max_drawdown_R_difference"),
        "stress_max_drawdown_R_difference": comparison_rows[1].get("max_drawdown_R_difference"),
        "first_mismatching_trade_timestamp": first_mismatch,
        "missing_trades_count": missing_count,
        "extra_trades_count": extra_count,
    }
    add_common_summary_fields(
        summary,
        decision_scope="rule_replay",
        final_classification=classification,
        next_action=next_action_for_classification(classification),
    )

    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_csv(paths["summary"], [summary], SUMMARY_FIELDNAMES)
    write_csv(paths["base_trade_log"], base_trade_rows, TRADE_LOG_FIELDNAMES)
    write_csv(paths["stress_trade_log"], stress_trade_rows, TRADE_LOG_FIELDNAMES)
    write_csv(paths["base_equity"], equity_curve_rows(base_result.events), EQUITY_FIELDNAMES)
    write_csv(paths["stress_equity"], equity_curve_rows(stress_result.events), EQUITY_FIELDNAMES)
    write_csv(paths["comparison"], comparison_rows, COMPARISON_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    paths["report"].write_text(
        report_text(summary=summary, comparison_rows=comparison_rows, warnings=warnings),
        encoding="utf-8",
    )
    return paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        paths = run_rule_replay(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Rule replay outputs written to {paths['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
