"""Build a research-only gate decision report for one validated rule candidate.

This script reads existing candidate review, rule replay, rule review,
controlled expansion, timeout audit, timeout root-cause, and timeout sequence
outputs. It does not rerun validation or replay, recompute entries, add
filters, change TP/SL settings, search for features, or create operational
instructions.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import math
from pathlib import Path
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
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "rule_candidate_gate_decisions"

CANDIDATE_REVIEW_SUMMARY_FILE = "candidate_review_summary.csv"
CANDIDATE_REVIEW_WARNINGS_FILE = "candidate_review_warnings.csv"
CANDIDATE_REVIEW_REPORT_FILE = "candidate_review_report.md"

RULE_REPLAY_SUMMARY_FILE = "rule_based_backtest_summary.csv"
RULE_REPLAY_COMPARISON_FILE = "rule_based_comparison_to_stress_validation.csv"
RULE_REPLAY_WARNINGS_FILE = "rule_based_warnings.csv"
RULE_REPLAY_REPORT_FILE = "rule_based_backtest_report.md"

RULE_REVIEW_SUMMARY_FILE = "rule_based_review_summary.csv"
RULE_REVIEW_WARNINGS_FILE = "rule_based_review_warnings.csv"
RULE_REVIEW_REPORT_FILE = "rule_based_review_report.md"

CONTROLLED_SUMMARY_FILE = "controlled_rule_expansion_summary.csv"
CONTROLLED_WARNINGS_FILE = "controlled_rule_expansion_warnings.csv"
CONTROLLED_REPORT_FILE = "controlled_rule_expansion_report.md"

TIMEOUT_AUDIT_SUMMARY_FILE = "timeout_fragility_audit_summary.csv"
TIMEOUT_AUDIT_WARNINGS_FILE = "timeout_fragility_audit_warnings.csv"
TIMEOUT_AUDIT_REPORT_FILE = "timeout_fragility_audit_report.md"

TIMEOUT_ROOT_SUMMARY_FILE = "timeout_root_cause_summary.csv"
TIMEOUT_ROOT_WARNINGS_FILE = "timeout_root_cause_warnings.csv"
TIMEOUT_ROOT_REPORT_FILE = "timeout_root_cause_report.md"

TIMEOUT_SEQUENCE_SUMMARY_FILE = "timeout_sequence_drilldown_summary.csv"
TIMEOUT_SEQUENCE_WARNINGS_FILE = "timeout_sequence_drilldown_warnings.csv"
TIMEOUT_SEQUENCE_REPORT_FILE = "timeout_sequence_drilldown_report.md"

TIMEOUT_POLICY_SUMMARY_FILE = "timeout_policy_sensitivity_summary.csv"
TIMEOUT_POLICY_WARNINGS_FILE = "timeout_policy_sensitivity_warnings.csv"
TIMEOUT_POLICY_REPORT_FILE = "timeout_policy_sensitivity_report.md"

SUMMARY_FILE = "rule_candidate_gate_decision_summary.csv"
REPORT_FILE = "rule_candidate_gate_decision_report.md"
WARNINGS_FILE = "rule_candidate_gate_decision_warnings.csv"
CHAIN_FILE = "rule_candidate_gate_decision_chain.csv"
NEXT_ACTIONS_FILE = "rule_candidate_gate_decision_next_actions.csv"

OUTPUT_FILES = (
    SUMMARY_FILE,
    REPORT_FILE,
    WARNINGS_FILE,
    CHAIN_FILE,
    NEXT_ACTIONS_FILE,
)

CANDIDATE_REVIEW_READY_LABEL = "READY_FOR_RULE_BASED_RESEARCH_BACKTEST_REVIEW"
CANDIDATE_REVIEW_REJECTED_LABEL = "REVIEW_PACKAGE_REJECTED"
RULE_REPLAY_MATCHED_LABEL = "RULE_REPLAY_MATCHED_STRESS_VALIDATION"
RULE_REVIEW_READY_LABEL = "READY_FOR_CONTROLLED_RULE_RESEARCH_BACKTEST_EXPANSION"
RULE_REVIEW_REJECTED_LABEL = "RULE_BASED_REVIEW_REJECTED"
CONTROLLED_TIMEOUT_REVIEW_LABEL = "CONTROLLED_EXPANSION_RETAINED_FOR_TIMEOUT_REVIEW"
CONTROLLED_READY_LABEL = "READY_FOR_BASELINE_AND_COST_SENSITIVITY_REVIEW"
CONTROLLED_REJECTED_LABEL = "CONTROLLED_EXPANSION_REJECTED"
TIMEOUT_AUDIT_FAILED_LABEL = "TIMEOUT_AUDIT_FAILED"
TIMEOUT_ROOT_FAILED_LABEL = "TIMEOUT_ROOT_CAUSE_FAILED"
TIMEOUT_SEQUENCE_FAILED_LABEL = "TIMEOUT_SEQUENCE_FAILED"
TIMEOUT_AUDIT_RETAINED_LABEL = "TIMEOUT_AUDIT_RETAINED_FOR_REVIEW"
TIMEOUT_ROOT_RETAINED_LABEL = "TIMEOUT_ROOT_CAUSE_RETAINED_FOR_REVIEW"
TIMEOUT_SEQUENCE_RETAINED_LABEL = "TIMEOUT_SEQUENCE_RETAINED_FOR_REVIEW"
TIMEOUT_POLICY_CLEARED_LABEL = "TIMEOUT_POLICY_SENSITIVITY_CLEARED_FOR_LIMITED_BASELINE_COST_REVIEW"
TIMEOUT_POLICY_RETAINED_LABEL = "TIMEOUT_POLICY_SENSITIVITY_RETAINED_FOR_TIMEOUT_REVIEW"
TIMEOUT_POLICY_REJECTED_LABEL = "TIMEOUT_POLICY_SENSITIVITY_REJECTED"

GATE_REJECT_LABEL = "GATE_REJECT_CANDIDATE"
GATE_RETAIN_LABEL = "GATE_RETAIN_TIMEOUT_REVIEW"
GATE_ALLOW_LIMITED_LABEL = "GATE_ALLOW_LIMITED_BASELINE_COST_REVIEW_WITH_TIMEOUT_CAVEAT"

TIMEOUT_LOSS_SMALL_STRESS_RATIO_MAX = 0.05
SEQUENCE_RETAIN_STRESS_RATIO_MIN = 0.05
SEQUENCE_REJECT_STRESS_RATIO_MIN = 0.10
SEQUENCE_MATERIAL_STRESS_RATIO_MIN = 0.025

ALTERNATIVE_TIMEOUT_POLICY_WARNING_CODES = {
    "timeout_policy_blocking_failure",
    "timeout_excluded_bias_warning",
    "extended_horizon_not_validated_rule",
    "extended_horizon_sl_dominance_warning",
    "extended_horizon_drawdown_warning",
}

FORBIDDEN_NEXT_ACTIONS = [
    "live trading",
    "trading signal",
    "broker execution",
    "position sizing",
    "TP/SL optimization",
    "new feature search",
    "new filters",
    "live readiness",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "blocking",
    "message",
    "related_stage",
    "related_metric",
    "metric_value",
    "threshold",
]
WARNING_FIELDNAMES = with_common_warning_fields(WARNING_FIELDNAMES)

SUMMARY_FIELDNAMES = [
    "run_id",
    "candidate_review_dir",
    "rule_replay_dir",
    "rule_review_dir",
    "controlled_expansion_dir",
    "timeout_audit_dir",
    "timeout_root_cause_dir",
    "timeout_sequence_dir",
    "timeout_policy_sensitivity_dir",
    "gate_output_dir",
    "final_gate_decision",
    "limited_baseline_cost_review_allowed",
    "timeout_issue_unresolved",
    "timeout_caveat_unresolved",
    "timeout_policy_sensitivity_classification",
    "timeout_audit_status",
    "timeout_root_cause_status",
    "timeout_sequence_status",
    "timeout_policy_sensitivity_status",
    "missing_required_timeout_stage_count",
    "alternative_timeout_policies_rejected",
    "h10_timeout_policy_required",
    "timeout_excluded_diagnostic_biased",
    "extended_horizon_timeout_policy_rejected",
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
    "candidate_review_classification",
    "rule_replay_classification",
    "rule_replay_logs_match",
    "rule_replay_comparison_match_all",
    "rule_review_classification",
    "controlled_expansion_classification",
    "timeout_audit_classification",
    "timeout_root_cause_classification",
    "timeout_sequence_classification",
    "candidate_review_warnings_count",
    "candidate_review_blocking_warnings_count",
    "rule_replay_warnings_count",
    "rule_replay_blocking_warnings_count",
    "rule_review_warnings_count",
    "rule_review_blocking_warnings_count",
    "controlled_expansion_warnings_count",
    "controlled_expansion_blocking_warnings_count",
    "timeout_audit_warnings_count",
    "timeout_audit_blocking_warnings_count",
    "timeout_root_cause_warnings_count",
    "timeout_root_cause_blocking_warnings_count",
    "timeout_sequence_warnings_count",
    "timeout_sequence_blocking_warnings_count",
    "timeout_policy_warnings_count",
    "timeout_policy_blocking_warnings_count",
    "timeout_policy_alternative_blocking_warnings_count",
    "prior_blocking_warnings_count",
    "stress_mean_R",
    "stress_profit_factor_R",
    "stress_cumulative_R",
    "stress_max_drawdown_R",
    "timeout_cumulative_R",
    "timeout_cumulative_R_pct_of_stress_cumulative_R",
    "timeout_loss_ratio_of_stress_cumulative_R",
    "timeout_sequence_cumulative_R",
    "timeout_sequence_max_drawdown_R",
    "timeout_sequence_share_of_total_timeout_loss",
    "timeout_sequence_share_of_total_stress_cumulative_R",
    "current_h10_timeout_cumulative_R",
    "current_h10_timeout_mean_R",
    "current_h10_timeout_profit_factor_R",
    "current_h10_policy_cumulative_R",
    "current_h10_policy_mean_R",
    "current_h10_policy_profit_factor_R",
    "h20_timeout_subset_cumulative_R",
    "h40_timeout_subset_cumulative_R",
    "h80_timeout_subset_cumulative_R",
    "h20_delta_vs_original_h10_timeout_R",
    "h40_delta_vs_original_h10_timeout_R",
    "h80_delta_vs_original_h10_timeout_R",
]
SUMMARY_FIELDNAMES = with_common_summary_fields(SUMMARY_FIELDNAMES)

CHAIN_FIELDNAMES = [
    "stage_order",
    "stage",
    "input_dir",
    "summary_file",
    "report_file",
    "final_label",
    "expected_label_or_state",
    "stage_status",
    "warnings_count",
    "blocking_warnings_count",
    "key_metric",
    "key_metric_value",
]

NEXT_ACTION_FIELDNAMES = [
    "action_type",
    "status",
    "message",
]
NEXT_ACTION_FIELDNAMES = with_common_next_action_fields(NEXT_ACTION_FIELDNAMES)


@dataclass(frozen=True)
class StageInputs:
    name: str
    directory: Path
    summary_file: str
    warnings_file: str
    report_file: str
    summary: dict[str, str]
    warnings: list[dict[str, str]]
    stage_status: str = "ready"
    missing_reason: str = ""


@dataclass(frozen=True)
class GateInputs:
    candidate_review: StageInputs
    rule_replay: StageInputs
    rule_review: StageInputs
    controlled_expansion: StageInputs
    timeout_audit: StageInputs | None
    timeout_root_cause: StageInputs | None
    timeout_sequence: StageInputs | None
    timeout_policy_sensitivity: StageInputs | None
    replay_comparison_rows: list[dict[str, str]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only final gate decision report from existing rule-candidate outputs."
    )
    parser.add_argument("--candidate-review-dir", required=True)
    parser.add_argument("--rule-replay-dir", required=True)
    parser.add_argument("--rule-review-dir", required=True)
    parser.add_argument("--controlled-expansion-dir", required=True)
    parser.add_argument("--timeout-audit-dir")
    parser.add_argument("--timeout-root-cause-dir")
    parser.add_argument("--timeout-sequence-dir")
    parser.add_argument("--timeout-policy-sensitivity-dir")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-id")
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
        raise ValueError(f"Required summary CSV is empty: {path}")
    return rows[0]


def check_report(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input file: {path}")


def load_stage(directory: Path, name: str, summary_file: str, warnings_file: str, report_file: str) -> StageInputs:
    if not directory.exists():
        raise FileNotFoundError(f"Input directory does not exist for {name}: {directory}")
    summary_path = directory / summary_file
    warnings_path = directory / warnings_file
    report_path = directory / report_file
    summary = first_csv_row(summary_path)
    warnings = read_csv_rows(warnings_path)
    check_report(report_path)
    return StageInputs(
        name=name,
        directory=directory,
        summary_file=summary_file,
        warnings_file=warnings_file,
        report_file=report_file,
        summary=summary,
        warnings=warnings,
    )


def load_optional_stage(
    directory: str | None,
    name: str,
    summary_file: str,
    warnings_file: str,
    report_file: str,
) -> StageInputs | None:
    if not directory:
        return None
    return load_stage(Path(directory), name, summary_file, warnings_file, report_file)


def load_inputs(args: argparse.Namespace) -> GateInputs:
    rule_replay_dir = Path(args.rule_replay_dir)
    comparison_path = rule_replay_dir / RULE_REPLAY_COMPARISON_FILE
    timeout_policy_sensitivity = None
    if args.timeout_policy_sensitivity_dir:
        timeout_policy_sensitivity = load_stage(
            Path(args.timeout_policy_sensitivity_dir),
            "timeout_policy_sensitivity",
            TIMEOUT_POLICY_SUMMARY_FILE,
            TIMEOUT_POLICY_WARNINGS_FILE,
            TIMEOUT_POLICY_REPORT_FILE,
        )
    return GateInputs(
        candidate_review=load_stage(
            Path(args.candidate_review_dir),
            "candidate_review",
            CANDIDATE_REVIEW_SUMMARY_FILE,
            CANDIDATE_REVIEW_WARNINGS_FILE,
            CANDIDATE_REVIEW_REPORT_FILE,
        ),
        rule_replay=load_stage(
            rule_replay_dir,
            "rule_replay",
            RULE_REPLAY_SUMMARY_FILE,
            RULE_REPLAY_WARNINGS_FILE,
            RULE_REPLAY_REPORT_FILE,
        ),
        rule_review=load_stage(
            Path(args.rule_review_dir),
            "rule_review",
            RULE_REVIEW_SUMMARY_FILE,
            RULE_REVIEW_WARNINGS_FILE,
            RULE_REVIEW_REPORT_FILE,
        ),
        controlled_expansion=load_stage(
            Path(args.controlled_expansion_dir),
            "controlled_expansion",
            CONTROLLED_SUMMARY_FILE,
            CONTROLLED_WARNINGS_FILE,
            CONTROLLED_REPORT_FILE,
        ),
        timeout_audit=load_optional_stage(
            args.timeout_audit_dir,
            "timeout_audit",
            TIMEOUT_AUDIT_SUMMARY_FILE,
            TIMEOUT_AUDIT_WARNINGS_FILE,
            TIMEOUT_AUDIT_REPORT_FILE,
        ),
        timeout_root_cause=load_optional_stage(
            args.timeout_root_cause_dir,
            "timeout_root_cause",
            TIMEOUT_ROOT_SUMMARY_FILE,
            TIMEOUT_ROOT_WARNINGS_FILE,
            TIMEOUT_ROOT_REPORT_FILE,
        ),
        timeout_sequence=load_optional_stage(
            args.timeout_sequence_dir,
            "timeout_sequence",
            TIMEOUT_SEQUENCE_SUMMARY_FILE,
            TIMEOUT_SEQUENCE_WARNINGS_FILE,
            TIMEOUT_SEQUENCE_REPORT_FILE,
        ),
        timeout_policy_sensitivity=timeout_policy_sensitivity,
        replay_comparison_rows=read_csv_rows(comparison_path),
    )


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "output_dir": output_dir,
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "chain": output_dir / CHAIN_FILE,
        "next_actions": output_dir / NEXT_ACTIONS_FILE,
    }


def ensure_can_write(paths: dict[str, Path], overwrite: bool) -> None:
    output_dir = paths["output_dir"]
    if not output_dir.exists():
        return
    existing = [path for key, path in paths.items() if key != "output_dir" and path.exists()]
    if existing and not overwrite:
        formatted = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist; pass --overwrite to replace them: {formatted}")


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def finite_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return parsed
    return parsed


def positive_metric(value: object) -> bool:
    parsed = finite_float(value)
    return parsed is not None and parsed > 0


def profit_factor_positive(value: object) -> bool:
    parsed = finite_float(value)
    return parsed is not None and parsed > 1


def metric_or(primary: object, fallback: object) -> object:
    if primary is None:
        return fallback
    if isinstance(primary, str) and not primary.strip():
        return fallback
    return primary


def stage_warning_count(stage: StageInputs | None) -> int:
    if stage is None:
        return 0
    summary_count = finite_float(stage.summary.get("warnings_count"))
    if summary_count is not None and math.isfinite(summary_count):
        return int(summary_count)
    return len(stage.warnings)


def warning_is_blocking(row: dict[str, object]) -> bool:
    severity = str(row.get("severity") or "").strip().lower()
    return (
        bool_value(row.get("blocking"))
        or bool_value(row.get("blocks_ready"))
        or bool_value(row.get("blocks_match"))
        or severity in {"blocking", "error"}
    )


def stage_blocking_count(stage: StageInputs | None) -> int:
    if stage is None:
        return 0
    summary_count = finite_float(stage.summary.get("blocking_warnings_count"))
    if summary_count is not None and math.isfinite(summary_count):
        return int(summary_count)
    return sum(1 for row in stage.warnings if warning_is_blocking(row))


def alternative_policy_blocking_count(stage: StageInputs | None) -> int:
    if stage is None:
        return 0
    count = 0
    for row in stage.warnings:
        warning_code = str(row.get("warning_code") or row.get("check") or "").strip()
        if warning_is_blocking(row) and warning_code in ALTERNATIVE_TIMEOUT_POLICY_WARNING_CODES:
            count += 1
    if count:
        return count
    policy_label = str(stage.summary.get("final_timeout_policy_sensitivity_classification") or "")
    if policy_label == TIMEOUT_POLICY_REJECTED_LABEL:
        return stage_blocking_count(stage)
    return 0


def optional_stage_status(
    stage: StageInputs | None,
    *,
    required: bool,
    failed: bool = False,
    alternative_policy_rejected: bool = False,
    not_run_when_required: bool = False,
) -> str:
    if stage is None:
        if required and not_run_when_required:
            return "not_run"
        return "missing_required" if required else "skipped_not_required"
    if failed:
        return "failed"
    if alternative_policy_rejected:
        return "alternative_policy_rejected"
    return "ready"


def timeout_stage_requirements(
    *,
    controlled_label: str,
    audit_label: str,
    root_label: str,
    sequence_label: str,
) -> dict[str, bool]:
    return {
        "timeout_audit": controlled_label == CONTROLLED_TIMEOUT_REVIEW_LABEL,
        "timeout_root_cause": audit_label == TIMEOUT_AUDIT_RETAINED_LABEL,
        "timeout_sequence": root_label == TIMEOUT_ROOT_RETAINED_LABEL,
        "timeout_policy_sensitivity": sequence_label == TIMEOUT_SEQUENCE_RETAINED_LABEL,
    }


def missing_required_timeout_stage_count(summary: dict[str, object]) -> int:
    return sum(
        1
        for key in [
            "timeout_audit_status",
            "timeout_root_cause_status",
            "timeout_sequence_status",
        ]
        if summary.get(key) == "missing_required"
    )


def timeout_policy_stage_status(
    stage: StageInputs | None,
    *,
    required: bool,
    policy_label: str,
    alternative_policy_rejected: bool,
) -> str:
    if stage is None:
        return "not_run" if required else "skipped_not_required"
    if alternative_policy_rejected:
        return "alternative_policy_rejected"
    if policy_label == TIMEOUT_POLICY_REJECTED_LABEL:
        return "failed"
    if policy_label == TIMEOUT_POLICY_RETAINED_LABEL:
        return "review"
    return "ready"


def first_value(key: str, *sources: dict[str, str]) -> str:
    for source in sources:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


def first_float(key: str, *sources: dict[str, str]) -> float | None:
    for source in sources:
        parsed = finite_float(source.get(key))
        if parsed is not None:
            return parsed
    return None


def first_value_any(source: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


def first_float_any(source: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        parsed = finite_float(source.get(key))
        if parsed is not None:
            return parsed
    return None


def ratio_from_value(value: object) -> float | None:
    parsed = finite_float(value)
    if parsed is None:
        return None
    if abs(parsed) > 1.0:
        return parsed / 100.0
    return parsed


def timeout_loss_ratio(audit_summary: dict[str, str]) -> float | None:
    direct = ratio_from_value(audit_summary.get("timeout_loss_ratio_of_stress_cumulative_R"))
    if direct is not None:
        return direct
    pct = ratio_from_value(audit_summary.get("timeout_cumulative_R_pct_of_stress_cumulative_R"))
    if pct is None:
        return None
    return abs(pct)


def replay_comparison_match_all(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and all(bool_value(row.get("trade_logs_match_within_tolerance")) for row in rows)


def add_warning(
    warnings: list[dict[str, object]],
    *,
    warning_code: str,
    severity: str,
    blocking: bool,
    message: str,
    related_stage: str = "",
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
            related_stage=related_stage,
            related_metric=related_metric,
            metric_value=metric_value,
            threshold=threshold,
        )
    )


def build_summary(run_id: str, output_dir: Path, inputs: GateInputs) -> dict[str, object]:
    candidate = inputs.candidate_review.summary
    replay = inputs.rule_replay.summary
    rule_review = inputs.rule_review.summary
    controlled = inputs.controlled_expansion.summary
    audit = inputs.timeout_audit.summary if inputs.timeout_audit else {}
    root = inputs.timeout_root_cause.summary if inputs.timeout_root_cause else {}
    sequence = inputs.timeout_sequence.summary if inputs.timeout_sequence else {}
    policy_stage = inputs.timeout_policy_sensitivity
    policy = policy_stage.summary if policy_stage else {}
    sources = [sequence, root, audit, controlled, rule_review, replay, candidate]
    controlled_label = str(controlled.get("final_research_only_classification") or "")
    audit_label = str(audit.get("final_timeout_audit_classification") or "")
    root_label = str(root.get("final_timeout_root_cause_classification") or "")
    sequence_label = str(sequence.get("final_timeout_sequence_classification") or "")
    policy_label = first_value_any(policy, "final_timeout_policy_sensitivity_classification")
    timeout_requirements = timeout_stage_requirements(
        controlled_label=controlled_label,
        audit_label=audit_label,
        root_label=root_label,
        sequence_label=sequence_label,
    )
    timeout_audit_status = optional_stage_status(
        inputs.timeout_audit,
        required=timeout_requirements["timeout_audit"],
        failed=audit_label == TIMEOUT_AUDIT_FAILED_LABEL,
    )
    timeout_root_status = optional_stage_status(
        inputs.timeout_root_cause,
        required=timeout_requirements["timeout_root_cause"],
        failed=root_label == TIMEOUT_ROOT_FAILED_LABEL,
    )
    timeout_sequence_status = optional_stage_status(
        inputs.timeout_sequence,
        required=timeout_requirements["timeout_sequence"],
        failed=sequence_label == TIMEOUT_SEQUENCE_FAILED_LABEL,
    )

    stress_mean = first_float("stress_mean_R", audit, controlled, rule_review, replay, candidate)
    stress_pf = first_float("stress_profit_factor_R", audit, controlled, rule_review, replay, candidate)
    stress_cumulative = first_float("stress_cumulative_R", sequence, root, audit, controlled, rule_review, replay, candidate)
    stress_drawdown = first_float("stress_max_drawdown_R", controlled, rule_review, replay, candidate)
    current_h10_cumulative = first_float_any(policy, "current_h10_timeout_cumulative_R", "stress_cumulative_R")
    current_h10_mean = first_float_any(policy, "current_h10_timeout_mean_R", "stress_mean_R")
    current_h10_pf = first_float_any(policy, "current_h10_timeout_profit_factor_R", "stress_profit_factor_R")
    policy_warning_count = stage_warning_count(policy_stage) if policy_stage else 0
    policy_blocking_count = stage_blocking_count(policy_stage) if policy_stage else 0
    policy_alternative_blocking_count = alternative_policy_blocking_count(policy_stage)
    sequence_stress_ratio = ratio_from_value(sequence.get("sequence_share_of_total_stress_cumulative_R"))
    timeout_ratio = timeout_loss_ratio(audit)
    prior_blocking = sum(
        stage_blocking_count(stage)
        for stage in (
            inputs.candidate_review,
            inputs.rule_replay,
            inputs.rule_review,
            inputs.controlled_expansion,
            inputs.timeout_audit,
            inputs.timeout_root_cause,
            inputs.timeout_sequence,
        )
    )
    timeout_issue_unresolved = any(
        label in {
            TIMEOUT_AUDIT_RETAINED_LABEL,
            TIMEOUT_ROOT_RETAINED_LABEL,
            TIMEOUT_SEQUENCE_RETAINED_LABEL,
            CONTROLLED_TIMEOUT_REVIEW_LABEL,
        }
        for label in (
            controlled_label,
            audit_label,
            root_label,
            sequence_label,
        )
    )
    policy_h10_positive = (
        positive_metric(current_h10_mean if current_h10_mean is not None else stress_mean)
        and profit_factor_positive(current_h10_pf if current_h10_pf is not None else stress_pf)
        and positive_metric(current_h10_cumulative if current_h10_cumulative is not None else stress_cumulative)
    )
    alternative_timeout_policies_rejected = policy_label == TIMEOUT_POLICY_REJECTED_LABEL and policy_h10_positive
    policy_status = timeout_policy_stage_status(
        policy_stage,
        required=timeout_requirements["timeout_policy_sensitivity"],
        policy_label=policy_label,
        alternative_policy_rejected=alternative_timeout_policies_rejected,
    )
    timeout_policy_present = policy_stage is not None
    timeout_caveat_unresolved = timeout_issue_unresolved or timeout_policy_present
    missing_timeout_count = missing_required_timeout_stage_count(
        {
            "timeout_audit_status": timeout_audit_status,
            "timeout_root_cause_status": timeout_root_status,
            "timeout_sequence_status": timeout_sequence_status,
        }
    )

    return {
        "run_id": run_id,
        "candidate_review_dir": str(inputs.candidate_review.directory),
        "rule_replay_dir": str(inputs.rule_replay.directory),
        "rule_review_dir": str(inputs.rule_review.directory),
        "controlled_expansion_dir": str(inputs.controlled_expansion.directory),
        "timeout_audit_dir": str(inputs.timeout_audit.directory) if inputs.timeout_audit else "",
        "timeout_root_cause_dir": str(inputs.timeout_root_cause.directory) if inputs.timeout_root_cause else "",
        "timeout_sequence_dir": str(inputs.timeout_sequence.directory) if inputs.timeout_sequence else "",
        "timeout_policy_sensitivity_dir": str(policy_stage.directory) if policy_stage else "",
        "gate_output_dir": str(output_dir),
        "final_gate_decision": "",
        "limited_baseline_cost_review_allowed": False,
        "timeout_issue_unresolved": timeout_issue_unresolved,
        "timeout_caveat_unresolved": timeout_caveat_unresolved,
        "timeout_policy_sensitivity_classification": policy_label,
        "timeout_audit_status": timeout_audit_status,
        "timeout_root_cause_status": timeout_root_status,
        "timeout_sequence_status": timeout_sequence_status,
        "timeout_policy_sensitivity_status": policy_status,
        "missing_required_timeout_stage_count": missing_timeout_count,
        "alternative_timeout_policies_rejected": alternative_timeout_policies_rejected,
        "h10_timeout_policy_required": alternative_timeout_policies_rejected,
        "timeout_excluded_diagnostic_biased": timeout_policy_present,
        "extended_horizon_timeout_policy_rejected": policy_label == TIMEOUT_POLICY_REJECTED_LABEL,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "symbol": first_value("symbol", *sources),
        "direction": first_value("direction", *sources),
        "timeframe": first_value("timeframe", *sources),
        "horizon": first_value("horizon", *sources),
        "target_family": first_value("target_family", *sources),
        "regime_column": first_value("regime_column", *sources),
        "regime_value": first_value("regime_value", *sources),
        "feature_condition": first_value("feature_condition", *sources),
        "candidate_scope": first_value("candidate_scope", *sources),
        "tp_atr": first_value("tp_atr", *sources),
        "sl_atr": first_value("sl_atr", *sources),
        "same_bar_policy": first_value("same_bar_policy", *sources),
        "candidate_review_classification": candidate.get("final_research_only_classification", ""),
        "rule_replay_classification": replay.get("final_rule_replay_classification", ""),
        "rule_replay_logs_match": bool_value(replay.get("generated_logs_match_stress_validation")),
        "rule_replay_comparison_match_all": replay_comparison_match_all(inputs.replay_comparison_rows),
        "rule_review_classification": rule_review.get("final_research_only_classification", ""),
        "controlled_expansion_classification": controlled_label,
        "timeout_audit_classification": audit_label,
        "timeout_root_cause_classification": root_label,
        "timeout_sequence_classification": sequence_label,
        "candidate_review_warnings_count": stage_warning_count(inputs.candidate_review),
        "candidate_review_blocking_warnings_count": stage_blocking_count(inputs.candidate_review),
        "rule_replay_warnings_count": stage_warning_count(inputs.rule_replay),
        "rule_replay_blocking_warnings_count": stage_blocking_count(inputs.rule_replay),
        "rule_review_warnings_count": stage_warning_count(inputs.rule_review),
        "rule_review_blocking_warnings_count": stage_blocking_count(inputs.rule_review),
        "controlled_expansion_warnings_count": stage_warning_count(inputs.controlled_expansion),
        "controlled_expansion_blocking_warnings_count": stage_blocking_count(inputs.controlled_expansion),
        "timeout_audit_warnings_count": stage_warning_count(inputs.timeout_audit),
        "timeout_audit_blocking_warnings_count": stage_blocking_count(inputs.timeout_audit),
        "timeout_root_cause_warnings_count": stage_warning_count(inputs.timeout_root_cause),
        "timeout_root_cause_blocking_warnings_count": stage_blocking_count(inputs.timeout_root_cause),
        "timeout_sequence_warnings_count": stage_warning_count(inputs.timeout_sequence),
        "timeout_sequence_blocking_warnings_count": stage_blocking_count(inputs.timeout_sequence),
        "timeout_policy_warnings_count": policy_warning_count,
        "timeout_policy_blocking_warnings_count": policy_blocking_count,
        "timeout_policy_alternative_blocking_warnings_count": policy_alternative_blocking_count,
        "prior_blocking_warnings_count": prior_blocking,
        "stress_mean_R": stress_mean,
        "stress_profit_factor_R": stress_pf,
        "stress_cumulative_R": stress_cumulative,
        "stress_max_drawdown_R": stress_drawdown,
        "timeout_cumulative_R": first_float("timeout_cumulative_R", audit, controlled),
        "timeout_cumulative_R_pct_of_stress_cumulative_R": audit.get("timeout_cumulative_R_pct_of_stress_cumulative_R", controlled.get("timeout_cumulative_R_pct_of_stress_cumulative_R", "")),
        "timeout_loss_ratio_of_stress_cumulative_R": timeout_ratio,
        "timeout_sequence_cumulative_R": sequence.get("sequence_cumulative_R", ""),
        "timeout_sequence_max_drawdown_R": sequence.get("sequence_max_drawdown_R", ""),
        "timeout_sequence_share_of_total_timeout_loss": sequence.get("sequence_share_of_total_timeout_loss", ""),
        "timeout_sequence_share_of_total_stress_cumulative_R": sequence_stress_ratio,
        "current_h10_timeout_cumulative_R": current_h10_cumulative,
        "current_h10_timeout_mean_R": current_h10_mean,
        "current_h10_timeout_profit_factor_R": current_h10_pf,
        "current_h10_policy_cumulative_R": current_h10_cumulative,
        "current_h10_policy_mean_R": current_h10_mean,
        "current_h10_policy_profit_factor_R": current_h10_pf,
        "h20_timeout_subset_cumulative_R": first_float_any(
            policy,
            "h20_timeout_subset_cumulative_R",
            "extended_h20_timeout_subset_cumulative_R",
        ),
        "h40_timeout_subset_cumulative_R": first_float_any(
            policy,
            "h40_timeout_subset_cumulative_R",
            "extended_h40_timeout_subset_cumulative_R",
        ),
        "h80_timeout_subset_cumulative_R": first_float_any(
            policy,
            "h80_timeout_subset_cumulative_R",
            "extended_h80_timeout_subset_cumulative_R",
        ),
        "h20_delta_vs_original_h10_timeout_R": first_float_any(
            policy,
            "h20_delta_vs_original_h10_timeout_R",
            "extended_h20_delta_vs_h10_timeout_R",
        ),
        "h40_delta_vs_original_h10_timeout_R": first_float_any(
            policy,
            "h40_delta_vs_original_h10_timeout_R",
            "extended_h40_delta_vs_h10_timeout_R",
        ),
        "h80_delta_vs_original_h10_timeout_R": first_float_any(
            policy,
            "h80_delta_vs_original_h10_timeout_R",
            "extended_h80_delta_vs_h10_timeout_R",
        ),
    }


def reject_reasons(summary: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    if int(summary.get("prior_blocking_warnings_count") or 0) > 0:
        reasons.append("one or more prior stages have blocking warnings")
    if int(summary.get("missing_required_timeout_stage_count") or 0) > 0:
        reasons.append("required timeout review stage outputs are missing")
    if summary.get("rule_replay_classification") != RULE_REPLAY_MATCHED_LABEL:
        reasons.append("rule replay did not match stress validation")
    if not bool_value(summary.get("rule_replay_logs_match")) or not bool_value(summary.get("rule_replay_comparison_match_all")):
        reasons.append("rule replay comparison did not match all prior stress outputs")
    if summary.get("candidate_review_classification") == CANDIDATE_REVIEW_REJECTED_LABEL:
        reasons.append("candidate review was rejected")
    if summary.get("rule_review_classification") == RULE_REVIEW_REJECTED_LABEL:
        reasons.append("rule-based review was rejected")
    if summary.get("controlled_expansion_classification") == CONTROLLED_REJECTED_LABEL:
        reasons.append("controlled expansion was rejected")
    if not positive_metric(summary.get("stress_mean_R")):
        reasons.append("stress mean_R is not positive")
    if not profit_factor_positive(summary.get("stress_profit_factor_R")):
        reasons.append("stress profit factor is not above 1")
    if not positive_metric(summary.get("stress_cumulative_R")):
        reasons.append("stress cumulative_R is not positive")
    if summary.get("timeout_policy_sensitivity_classification"):
        current_h10_mean = metric_or(summary.get("current_h10_timeout_mean_R"), summary.get("stress_mean_R"))
        current_h10_pf = metric_or(
            summary.get("current_h10_timeout_profit_factor_R"),
            summary.get("stress_profit_factor_R"),
        )
        current_h10_cumulative = metric_or(
            summary.get("current_h10_timeout_cumulative_R"),
            summary.get("stress_cumulative_R"),
        )
        if not positive_metric(current_h10_mean):
            reasons.append("timeout policy sensitivity current h10 mean_R is not positive")
        if not profit_factor_positive(current_h10_pf):
            reasons.append("timeout policy sensitivity current h10 profit factor is not above 1")
        if not positive_metric(current_h10_cumulative):
            reasons.append("timeout policy sensitivity current h10 cumulative_R is not positive")
    if summary.get("timeout_audit_classification") == TIMEOUT_AUDIT_FAILED_LABEL:
        reasons.append("timeout fragility audit failed")
    if summary.get("timeout_root_cause_classification") == TIMEOUT_ROOT_FAILED_LABEL:
        reasons.append("timeout root-cause review failed")
    if summary.get("timeout_sequence_classification") == TIMEOUT_SEQUENCE_FAILED_LABEL:
        reasons.append("timeout sequence drilldown failed")
    sequence_ratio = finite_float(summary.get("timeout_sequence_share_of_total_stress_cumulative_R")) or 0.0
    if sequence_ratio >= SEQUENCE_REJECT_STRESS_RATIO_MIN:
        reasons.append("timeout sequence issue is catastrophic relative to stress cumulative_R")
    return reasons


def allow_limited_review(summary: dict[str, object]) -> bool:
    timeout_ratio = finite_float(summary.get("timeout_loss_ratio_of_stress_cumulative_R")) or 0.0
    sequence_ratio = finite_float(summary.get("timeout_sequence_share_of_total_stress_cumulative_R")) or 0.0
    policy_label = str(summary.get("timeout_policy_sensitivity_classification") or "")
    policy_compatible = (
        not policy_label
        or policy_label in {TIMEOUT_POLICY_CLEARED_LABEL, TIMEOUT_POLICY_RETAINED_LABEL}
        or bool_value(summary.get("alternative_timeout_policies_rejected"))
    )
    policy_h10_metrics_positive = (
        not policy_label
        or (
            positive_metric(metric_or(summary.get("current_h10_timeout_mean_R"), summary.get("stress_mean_R")))
            and profit_factor_positive(
                metric_or(
                    summary.get("current_h10_timeout_profit_factor_R"),
                    summary.get("stress_profit_factor_R"),
                )
            )
            and positive_metric(
                metric_or(
                    summary.get("current_h10_timeout_cumulative_R"),
                    summary.get("stress_cumulative_R"),
                )
            )
        )
    )
    return (
        summary.get("candidate_review_classification") == CANDIDATE_REVIEW_READY_LABEL
        and summary.get("rule_replay_classification") == RULE_REPLAY_MATCHED_LABEL
        and bool_value(summary.get("rule_replay_logs_match"))
        and bool_value(summary.get("rule_replay_comparison_match_all"))
        and summary.get("rule_review_classification") == RULE_REVIEW_READY_LABEL
        and summary.get("controlled_expansion_classification") in {CONTROLLED_TIMEOUT_REVIEW_LABEL, CONTROLLED_READY_LABEL}
        and summary.get("timeout_audit_classification") != TIMEOUT_AUDIT_FAILED_LABEL
        and summary.get("timeout_root_cause_classification") != TIMEOUT_ROOT_FAILED_LABEL
        and summary.get("timeout_sequence_classification") != TIMEOUT_SEQUENCE_FAILED_LABEL
        and int(summary.get("prior_blocking_warnings_count") or 0) == 0
        and int(summary.get("missing_required_timeout_stage_count") or 0) == 0
        and positive_metric(summary.get("stress_mean_R"))
        and profit_factor_positive(summary.get("stress_profit_factor_R"))
        and positive_metric(summary.get("stress_cumulative_R"))
        and policy_compatible
        and policy_h10_metrics_positive
        and timeout_ratio <= TIMEOUT_LOSS_SMALL_STRESS_RATIO_MAX
        and sequence_ratio < SEQUENCE_RETAIN_STRESS_RATIO_MIN
    )


def classify_gate(summary: dict[str, object]) -> tuple[str, list[str]]:
    reasons = reject_reasons(summary)
    if reasons:
        return GATE_REJECT_LABEL, reasons
    if allow_limited_review(summary):
        return GATE_ALLOW_LIMITED_LABEL, []
    return GATE_RETAIN_LABEL, []


def add_gate_warnings(summary: dict[str, object], warnings: list[dict[str, object]], rejection_reasons: list[str]) -> None:
    optional_statuses = {
        "timeout_audit": summary.get("timeout_audit_status"),
        "timeout_root_cause": summary.get("timeout_root_cause_status"),
        "timeout_sequence": summary.get("timeout_sequence_status"),
    }
    for stage, status in optional_statuses.items():
        if status == "skipped_not_required":
            add_warning(
                warnings,
                warning_code="optional_timeout_stage_skipped",
                severity="info",
                blocking=False,
                message=f"{stage} was not provided because upstream evidence did not require it.",
                related_stage=stage,
                related_metric=f"{stage}_status",
                metric_value=status,
                threshold="required only when upstream timeout review label requires it",
            )
            add_warning(
                warnings,
                warning_code="gate_optional_input_missing",
                severity="info",
                blocking=False,
                message=f"Optional gate input for {stage} is absent and treated as skipped_not_required.",
                related_stage=stage,
                related_metric=f"{stage}_dir",
                metric_value="",
                threshold="optional when not required",
            )
        elif status == "missing_required":
            add_warning(
                warnings,
                warning_code="missing_required_timeout_stage",
                severity="blocking",
                blocking=True,
                message=f"{stage} output is required by upstream timeout review evidence but was not provided.",
                related_stage=stage,
                related_metric=f"{stage}_status",
                metric_value=status,
                threshold="ready or review output required",
            )

    policy_status = str(summary.get("timeout_policy_sensitivity_status") or "")
    if policy_status == "not_run":
        add_warning(
            warnings,
            warning_code="timeout_policy_sensitivity_not_run",
            severity="review",
            blocking=False,
            message=(
                "Timeout policy sensitivity was not provided. Alternative timeout policies are not "
                "treated as rejected, and the timeout caveat remains unresolved."
            ),
            related_stage="timeout_policy_sensitivity",
            related_metric="timeout_policy_sensitivity_status",
            metric_value=policy_status,
            threshold="optional but useful when timeout sequence remains retained",
        )
    elif policy_status == "skipped_not_required":
        add_warning(
            warnings,
            warning_code="timeout_policy_sensitivity_optional",
            severity="info",
            blocking=False,
            message="Timeout policy sensitivity was not required by the available timeout-review evidence.",
            related_stage="timeout_policy_sensitivity",
            related_metric="timeout_policy_sensitivity_status",
            metric_value=policy_status,
            threshold="not required",
        )

    if int(summary.get("prior_blocking_warnings_count") or 0) > 0:
        add_warning(
            warnings,
            warning_code="prior_blocking_warning",
            severity="blocking",
            blocking=True,
            message="At least one prior stage has a blocking warning.",
            related_stage="validation_chain",
            related_metric="prior_blocking_warnings_count",
            metric_value=summary.get("prior_blocking_warnings_count"),
            threshold=0,
        )
    if rejection_reasons:
        add_warning(
            warnings,
            warning_code="gate_rejected",
            severity="blocking",
            blocking=True,
            message="Gate rejected candidate: " + "; ".join(rejection_reasons) + ".",
            related_stage="gate_decision",
            related_metric="reject_reasons",
            metric_value="; ".join(rejection_reasons),
            threshold="no reject reason",
        )
        return

    timeout_unresolved = bool_value(summary.get("timeout_caveat_unresolved"))
    sequence_classification = str(summary.get("timeout_sequence_classification") or "")
    sequence_ratio = finite_float(summary.get("timeout_sequence_share_of_total_stress_cumulative_R")) or 0.0
    decision = str(summary.get("final_gate_decision") or "")
    policy_label = str(summary.get("timeout_policy_sensitivity_classification") or "")

    if timeout_unresolved:
        add_warning(
            warnings,
            warning_code="timeout_caveat_unresolved",
            severity="review",
            blocking=False,
            message="Timeout evidence remains unresolved and must stay explicit in the next offline review stage.",
            related_stage="timeout_reviews",
            related_metric="timeout_caveat_unresolved",
            metric_value=True,
            threshold=False,
        )
    if sequence_classification == TIMEOUT_SEQUENCE_RETAINED_LABEL or sequence_ratio >= SEQUENCE_MATERIAL_STRESS_RATIO_MIN:
        add_warning(
            warnings,
            warning_code="sequence_review_required",
            severity="review",
            blocking=False,
            message="The timeout sequence remains material enough to require a caveat in the gate decision.",
            related_stage="timeout_sequence",
            related_metric="timeout_sequence_share_of_total_stress_cumulative_R",
            metric_value=sequence_ratio,
            threshold=f"< {SEQUENCE_MATERIAL_STRESS_RATIO_MIN} for no caveat",
        )
    if bool_value(summary.get("alternative_timeout_policies_rejected")):
        add_warning(
            warnings,
            warning_code="alternative_timeout_policies_rejected",
            severity="review",
            blocking=False,
            message=(
                "Timeout policy sensitivity rejected alternative timeout policies; this is not "
                "candidate-level rejection while the original h10 policy remains positive."
            ),
            related_stage="timeout_policy_sensitivity",
            related_metric="final_timeout_policy_sensitivity_classification",
            metric_value=policy_label,
            threshold="alternative policy rejection only",
        )
    if int(summary.get("timeout_policy_alternative_blocking_warnings_count") or 0) > 0:
        add_warning(
            warnings,
            warning_code="alternative_timeout_policy_blocking_warning",
            severity="review",
            blocking=False,
            message=(
                "A timeout policy sensitivity blocking warning is scoped to alternative timeout "
                "policies and is not counted as a candidate-level blocking warning."
            ),
            related_stage="timeout_policy_sensitivity",
            related_metric="timeout_policy_alternative_blocking_warnings_count",
            metric_value=summary.get("timeout_policy_alternative_blocking_warnings_count"),
            threshold="candidate-level blocking count remains zero",
        )
    if bool_value(summary.get("h10_timeout_policy_required")):
        add_warning(
            warnings,
            warning_code="h10_timeout_policy_required",
            severity="review",
            blocking=False,
            message="The validated h10 timeout boundary remains required for any limited offline next review.",
            related_stage="timeout_policy_sensitivity",
            related_metric="h10_timeout_policy_required",
            metric_value=True,
            threshold=True,
        )
    if decision == GATE_ALLOW_LIMITED_LABEL:
        add_warning(
            warnings,
            warning_code="limited_review_only",
            severity="info",
            blocking=False,
            message=(
                "The allowed next step is limited to offline baseline and cost-sensitivity review "
                "under the original h10 timeout policy."
            ),
            related_stage="gate_decision",
            related_metric="final_gate_decision",
            metric_value=decision,
            threshold=GATE_ALLOW_LIMITED_LABEL,
        )
        add_warning(
            warnings,
            warning_code="baseline_cost_review_allowed_with_caveat",
            severity="info",
            blocking=False,
            message=(
                "Baseline and cost-sensitivity review is allowed only with the timeout caveat "
                "and original h10 timeout rule preserved."
            ),
            related_stage="gate_decision",
            related_metric="timeout_caveat_unresolved",
            metric_value=timeout_unresolved,
            threshold="caveat documented",
        )


def stage_status(label: str, reject_labels: set[str], ready_labels: set[str]) -> str:
    if label in reject_labels:
        return "failed"
    if label in ready_labels:
        return "ready"
    return "review"


def build_chain_rows(inputs: GateInputs, summary: dict[str, object]) -> list[dict[str, object]]:
    def row(
        *,
        order: int,
        stage_name: str,
        stage: StageInputs | None,
        label: str,
        expected: str,
        status: str,
        key_metric: str,
        key_value: object,
    ) -> dict[str, object]:
        return {
            "stage_order": order,
            "stage": stage_name,
            "input_dir": str(stage.directory) if stage else "",
            "summary_file": stage.summary_file if stage else "",
            "report_file": stage.report_file if stage else "",
            "final_label": label,
            "expected_label_or_state": expected,
            "stage_status": status,
            "warnings_count": stage_warning_count(stage),
            "blocking_warnings_count": stage_blocking_count(stage),
            "key_metric": key_metric,
            "key_metric_value": key_value,
        }

    policy_label = str(summary.get("timeout_policy_sensitivity_classification") or "")
    policy_status = str(summary.get("timeout_policy_sensitivity_status") or "")
    if bool_value(summary.get("alternative_timeout_policies_rejected")):
        policy_status = "alternative_policy_rejected"
    elif inputs.timeout_policy_sensitivity is not None:
        policy_status = stage_status(policy_label, {TIMEOUT_POLICY_REJECTED_LABEL}, {TIMEOUT_POLICY_CLEARED_LABEL})

    return [
        row(
            order=1,
            stage_name="candidate_review",
            stage=inputs.candidate_review,
            label=str(summary.get("candidate_review_classification") or ""),
            expected=CANDIDATE_REVIEW_READY_LABEL,
            status=stage_status(
                str(summary.get("candidate_review_classification") or ""),
                {CANDIDATE_REVIEW_REJECTED_LABEL},
                {CANDIDATE_REVIEW_READY_LABEL},
            ),
            key_metric="ready_for_rule_based_research_backtest_review",
            key_value=inputs.candidate_review.summary.get("ready_for_rule_based_research_backtest_review", ""),
        ),
        row(
            order=2,
            stage_name="rule_replay",
            stage=inputs.rule_replay,
            label=str(summary.get("rule_replay_classification") or ""),
            expected=RULE_REPLAY_MATCHED_LABEL,
            status="ready" if summary.get("rule_replay_classification") == RULE_REPLAY_MATCHED_LABEL and bool_value(summary.get("rule_replay_comparison_match_all")) else "failed",
            key_metric="generated_logs_match_stress_validation",
            key_value=summary.get("rule_replay_logs_match"),
        ),
        row(
            order=3,
            stage_name="rule_review",
            stage=inputs.rule_review,
            label=str(summary.get("rule_review_classification") or ""),
            expected=RULE_REVIEW_READY_LABEL,
            status=stage_status(str(summary.get("rule_review_classification") or ""), {RULE_REVIEW_REJECTED_LABEL}, {RULE_REVIEW_READY_LABEL}),
            key_metric="ready_for_controlled_rule_research_backtest_expansion",
            key_value=inputs.rule_review.summary.get("ready_for_controlled_rule_research_backtest_expansion", ""),
        ),
        row(
            order=4,
            stage_name="controlled_expansion",
            stage=inputs.controlled_expansion,
            label=str(summary.get("controlled_expansion_classification") or ""),
            expected=f"{CONTROLLED_READY_LABEL} or {CONTROLLED_TIMEOUT_REVIEW_LABEL}",
            status=stage_status(
                str(summary.get("controlled_expansion_classification") or ""),
                {CONTROLLED_REJECTED_LABEL},
                {CONTROLLED_READY_LABEL, CONTROLLED_TIMEOUT_REVIEW_LABEL},
            ),
            key_metric="timeout_cumulative_R_pct_of_stress_cumulative_R",
            key_value=summary.get("timeout_cumulative_R_pct_of_stress_cumulative_R"),
        ),
        row(
            order=5,
            stage_name="timeout_audit",
            stage=inputs.timeout_audit,
            label=str(summary.get("timeout_audit_classification") or ""),
            expected="required only if controlled expansion retains timeout review",
            status=str(summary.get("timeout_audit_status") or ""),
            key_metric="timeout_loss_ratio_of_stress_cumulative_R",
            key_value=summary.get("timeout_loss_ratio_of_stress_cumulative_R"),
        ),
        row(
            order=6,
            stage_name="timeout_root_cause",
            stage=inputs.timeout_root_cause,
            label=str(summary.get("timeout_root_cause_classification") or ""),
            expected="required only if timeout audit retains review",
            status=str(summary.get("timeout_root_cause_status") or ""),
            key_metric="timeout_issue_unresolved",
            key_value=summary.get("timeout_issue_unresolved"),
        ),
        row(
            order=7,
            stage_name="timeout_sequence",
            stage=inputs.timeout_sequence,
            label=str(summary.get("timeout_sequence_classification") or ""),
            expected="required only if timeout root cause retains review",
            status=str(summary.get("timeout_sequence_status") or ""),
            key_metric="timeout_sequence_share_of_total_stress_cumulative_R",
            key_value=summary.get("timeout_sequence_share_of_total_stress_cumulative_R"),
        ),
        row(
            order=8,
            stage_name="timeout_policy_sensitivity",
            stage=inputs.timeout_policy_sensitivity,
            label=policy_label,
            expected="optional sensitivity; absence does not reject original h10 candidate",
            status=policy_status,
            key_metric="h20/h40/h80_delta_vs_original_h10_timeout_R",
            key_value=(
                f"{summary.get('h20_delta_vs_original_h10_timeout_R')}/"
                f"{summary.get('h40_delta_vs_original_h10_timeout_R')}/"
                f"{summary.get('h80_delta_vs_original_h10_timeout_R')}"
            ),
        ),
    ]


def allowed_next_action(decision: str) -> str:
    if decision == GATE_ALLOW_LIMITED_LABEL:
        return (
            "Candidate may proceed only to limited offline baseline and cost-sensitivity review "
            "under the original validated h10 timeout rule. Timeout caveat remains unresolved "
            "and must not be converted into new filters, TP/SL optimization, live signals, or "
            "execution logic."
        )
    if decision == GATE_RETAIN_LABEL:
        return "Candidate should remain in timeout review before any baseline or cost-sensitivity expansion."
    return "Candidate should not continue to baseline or cost-sensitivity review under current evidence."


def build_next_actions(decision: str) -> list[dict[str, object]]:
    forbidden = forbidden_actions_text(FORBIDDEN_NEXT_ACTIONS)
    rows = [
        next_action_row(
            action_type="allowed_next_action",
            status=decision,
            message=allowed_next_action(decision),
            forbidden_actions=forbidden,
        )
    ]
    rows.extend(
        next_action_row(
            action_type="forbidden_next_action",
            status="forbidden",
            message=action,
            forbidden_actions=forbidden,
        )
        for action in FORBIDDEN_NEXT_ACTIONS
    )
    return rows


def warning_lines(warnings: list[dict[str, object]]) -> list[str]:
    if not warnings:
        return ["- None."]
    return [
        f"- {warning.get('severity')} `{warning.get('warning_code')}`: {warning.get('message')}"
        for warning in warnings
    ]


def table_lines(rows: list[dict[str, object]], columns: list[str], *, limit: int | None = None) -> list[str]:
    selected = rows[:limit] if limit else rows
    if not selected:
        return ["_No rows._"]
    output = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in selected:
        output.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    if limit and len(rows) > limit:
        output.append(f"_Showing {limit} of {len(rows)} rows._")
    return output


def gate_rationale(summary: dict[str, object]) -> str:
    decision = str(summary.get("final_gate_decision") or "")
    if decision == GATE_ALLOW_LIMITED_LABEL:
        if bool_value(summary.get("alternative_timeout_policies_rejected")):
            return (
                "The prior candidate review, replay, and rule review stages are ready or matched, "
                "stress metrics for the original h10 policy remain positive, and timeout reviews "
                "are retained rather than failed. Timeout policy sensitivity rejected only the "
                "alternative timeout policies, so limited review is allowed only with the original "
                "h10 timeout boundary preserved."
            )
        return (
            "The prior candidate review, replay, and rule review stages are ready or matched, "
            "stress metrics remain positive, and timeout reviews are retained rather than failed. "
            "The timeout sequence remains material, so the next step is limited and caveated."
        )
    if decision == GATE_RETAIN_LABEL:
        return (
            "The candidate is not rejected, but the timeout evidence is still too material or "
            "insufficiently cleared for even limited baseline and cost-sensitivity expansion."
        )
    return "One or more required gate checks failed or crossed a blocking threshold."


def timeout_policy_report_lines(summary: dict[str, object]) -> list[str]:
    if not str(summary.get("timeout_policy_sensitivity_classification") or "").strip():
        return [
            "## Timeout Policy Sensitivity Summary",
            "",
            "- Timeout policy sensitivity input was not provided.",
            "",
        ]
    return [
        "## Timeout Policy Sensitivity Summary",
        "",
        f"- Timeout policy sensitivity classification: `{summary.get('timeout_policy_sensitivity_classification')}`",
        f"- Alternative timeout policies rejected: `{summary.get('alternative_timeout_policies_rejected')}`",
        f"- Validated h10 timeout policy required: `{summary.get('h10_timeout_policy_required')}`",
        f"- Timeout-excluded diagnostic biased: `{summary.get('timeout_excluded_diagnostic_biased')}`",
        f"- Extended h20/h40/h80 timeout policies rejected: `{summary.get('extended_horizon_timeout_policy_rejected')}`",
        f"- Current h10 policy cumulative_R/mean_R/PF: `{summary.get('current_h10_policy_cumulative_R')}` / `{summary.get('current_h10_policy_mean_R')}` / `{summary.get('current_h10_policy_profit_factor_R')}`",
        "- `current_h10_policy_*` fields refer to the full validated h10 policy; `timeout_cumulative_R` refers only to the timeout bucket.",
        f"- h20/h40/h80 timeout subset cumulative_R: `{summary.get('h20_timeout_subset_cumulative_R')}` / `{summary.get('h40_timeout_subset_cumulative_R')}` / `{summary.get('h80_timeout_subset_cumulative_R')}`",
        f"- h20/h40/h80 delta vs original h10 timeout R: `{summary.get('h20_delta_vs_original_h10_timeout_R')}` / `{summary.get('h40_delta_vs_original_h10_timeout_R')}` / `{summary.get('h80_delta_vs_original_h10_timeout_R')}`",
        "",
        "The validated h10 timeout policy remains required. Timeout-excluded diagnostics are biased and are not valid performance. Extended h20/h40/h80 timeout policies are rejected when the sensitivity stage rejects alternatives, while the original h10 candidate can remain eligible for limited offline baseline and cost-sensitivity review if candidate-level metrics stay positive.",
        "",
    ]


def report_text(
    *,
    summary: dict[str, object],
    warnings: list[dict[str, object]],
    chain_rows: list[dict[str, object]],
    next_actions: list[dict[str, object]],
) -> str:
    forbidden_rows = [row for row in next_actions if row["action_type"] == "forbidden_next_action"]
    return "\n".join(
        [
            "# Rule Candidate Gate Decision Report",
            "",
            "## Research-Only Warning",
            "",
            "This report reads existing offline research outputs only. It does not rerun replay or validation, recompute entries, add filters, change TP/SL settings, search features, or provide operational instructions.",
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
            f"- Candidate review: `{summary.get('candidate_review_dir')}`",
            f"- Rule replay: `{summary.get('rule_replay_dir')}`",
            f"- Rule review: `{summary.get('rule_review_dir')}`",
            f"- Controlled expansion: `{summary.get('controlled_expansion_dir')}`",
            f"- Timeout audit: `{summary.get('timeout_audit_dir')}`",
            f"- Timeout root cause: `{summary.get('timeout_root_cause_dir')}`",
            f"- Timeout sequence: `{summary.get('timeout_sequence_dir')}`",
            f"- Timeout policy sensitivity: `{summary.get('timeout_policy_sensitivity_dir')}`",
            "",
            "## Validation Chain Table",
            "",
            *table_lines(
                chain_rows,
                ["stage_order", "stage", "final_label", "stage_status", "warnings_count", "blocking_warnings_count"],
            ),
            "",
            "## Core Stress Metrics",
            "",
            f"- Stress mean_R: `{summary.get('stress_mean_R')}`",
            f"- Stress profit_factor_R: `{summary.get('stress_profit_factor_R')}`",
            f"- Stress cumulative_R: `{summary.get('stress_cumulative_R')}`",
            f"- Stress max_drawdown_R: `{summary.get('stress_max_drawdown_R')}`",
            "",
            "## Rule Replay Consistency",
            "",
            f"- Replay classification: `{summary.get('rule_replay_classification')}`",
            f"- Generated logs match stress validation: `{summary.get('rule_replay_logs_match')}`",
            f"- Comparison rows all match: `{summary.get('rule_replay_comparison_match_all')}`",
            "",
            "## Controlled Expansion Summary",
            "",
            f"- Controlled expansion classification: `{summary.get('controlled_expansion_classification')}`",
            f"- Timeout cumulative_R: `{summary.get('timeout_cumulative_R')}`",
            f"- Timeout cumulative_R pct/ratio of stress cumulative_R: `{summary.get('timeout_cumulative_R_pct_of_stress_cumulative_R')}` / `{summary.get('timeout_loss_ratio_of_stress_cumulative_R')}`",
            "",
            "## Timeout Audit/Root-Cause/Sequence Summary",
            "",
            f"- Timeout audit classification: `{summary.get('timeout_audit_classification')}`",
            f"- Timeout root-cause classification: `{summary.get('timeout_root_cause_classification')}`",
            f"- Timeout sequence classification: `{summary.get('timeout_sequence_classification')}`",
            f"- Sequence cumulative_R: `{summary.get('timeout_sequence_cumulative_R')}`",
            f"- Sequence max_drawdown_R: `{summary.get('timeout_sequence_max_drawdown_R')}`",
            f"- Sequence share of total timeout loss: `{summary.get('timeout_sequence_share_of_total_timeout_loss')}`",
            f"- Sequence share of stress cumulative_R: `{summary.get('timeout_sequence_share_of_total_stress_cumulative_R')}`",
            f"- Timeout issue unresolved: `{summary.get('timeout_issue_unresolved')}`",
            "",
            *timeout_policy_report_lines(summary),
            "## Gate Decision Rationale",
            "",
            gate_rationale(summary),
            "",
            "## Warnings And Caveats",
            "",
            *warning_lines(warnings),
            "",
            "## Final Gate Decision",
            "",
            f"`{summary.get('final_gate_decision')}`",
            "",
            "## Allowed Next Action",
            "",
            allowed_next_action(str(summary.get("final_gate_decision") or "")),
            "",
            "## Forbidden Next Actions",
            "",
            *table_lines(forbidden_rows, ["message"]),
            "",
        ]
    )


def build_rule_candidate_gate_decision_report(args: argparse.Namespace) -> dict[str, Path]:
    fallback_input_dirs = [
        args.timeout_sequence_dir,
        args.timeout_root_cause_dir,
        args.timeout_audit_dir,
        args.controlled_expansion_dir,
        args.rule_review_dir,
        args.rule_replay_dir,
        args.candidate_review_dir,
    ]
    fallback_run_id = next((Path(path).name for path in fallback_input_dirs if path), "")
    run_id = str(args.run_id or fallback_run_id).strip()
    if not run_id:
        raise ValueError("--run-id is required when input directories have no final path name")
    paths = output_paths(Path(args.output_root), run_id)
    ensure_can_write(paths, bool(args.overwrite))
    inputs = load_inputs(args)
    summary = build_summary(run_id, paths["output_dir"], inputs)
    decision, reasons = classify_gate(summary)
    summary.update(
        {
            "final_gate_decision": decision,
            "limited_baseline_cost_review_allowed": decision == GATE_ALLOW_LIMITED_LABEL,
        }
    )
    warnings: list[dict[str, object]] = []
    add_gate_warnings(summary, warnings, reasons)
    blocking_count = sum(1 for warning in warnings if bool_value(warning.get("blocking")))
    summary.update(
        {
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_count,
        }
    )
    chain_rows = build_chain_rows(inputs, summary)
    next_actions = build_next_actions(decision)
    add_common_summary_fields(
        summary,
        decision_scope="gate_decision",
        final_classification=decision,
        next_action=next_actions[0]["message"] if next_actions else "",
    )

    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_csv(paths["summary"], [summary], SUMMARY_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["chain"], chain_rows, CHAIN_FIELDNAMES)
    write_csv(paths["next_actions"], next_actions, NEXT_ACTION_FIELDNAMES)
    paths["report"].write_text(
        report_text(summary=summary, warnings=warnings, chain_rows=chain_rows, next_actions=next_actions),
        encoding="utf-8",
    )
    return paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outputs = build_rule_candidate_gate_decision_report(args)
    print(f"Wrote rule candidate gate decision report to {outputs['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
