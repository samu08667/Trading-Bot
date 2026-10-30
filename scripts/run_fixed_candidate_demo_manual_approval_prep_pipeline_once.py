"""Run one fixed-candidate demo manual approval preparation pipeline.

This orchestrator is single-shot. It can run the artifact/read-only/manual
approval preparation chain from an existing live-data shadow signal artifact to
manual approval record creation dry-run, and optionally to real approval record
creation only when explicitly allowed. It does not construct broker requests,
broker payloads, or executable order objects, execute orders, mutate databases,
run replay/backtest/paper workflows, add schedulers, or make trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_prep_pipeline"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_manual_approval_prep_pipeline"
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_DEMO_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR / "state" / "fixed_candidate_demo_state" / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_FUTURE_APPROVAL_RECORD_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record.json"
)

SCRIPT_PATHS = {
    "would_signal_review": BASE_DIR / "scripts" / "build_fixed_candidate_demo_would_signal_review.py",
    "order_shadow_plan": BASE_DIR / "scripts" / "build_fixed_candidate_demo_order_shadow_plan.py",
    "order_request_shadow_design": BASE_DIR / "scripts" / "build_fixed_candidate_demo_order_request_shadow_design.py",
    "risk_volume_shadow_plan": BASE_DIR / "scripts" / "build_fixed_candidate_demo_risk_volume_shadow_plan.py",
    "margin_feasibility_plan": BASE_DIR / "scripts" / "build_fixed_candidate_demo_margin_feasibility_plan.py",
    "broker_safe_margin_validation": BASE_DIR / "scripts" / "check_fixed_candidate_demo_broker_safe_margin_validation.py",
    "state_reconciliation_plan": BASE_DIR / "scripts" / "build_fixed_candidate_demo_state_reconciliation_plan.py",
    "duplicate_protection_plan": BASE_DIR / "scripts" / "build_fixed_candidate_demo_duplicate_protection_plan.py",
    "manual_approval_kill_switch_plan": BASE_DIR / "scripts" / "build_fixed_candidate_demo_manual_approval_kill_switch_plan.py",
    "future_broker_state_reconciliation_check_plan": BASE_DIR
    / "scripts"
    / "build_fixed_candidate_demo_future_broker_state_reconciliation_check_plan.py",
    "future_request_construction_readiness_plan": BASE_DIR
    / "scripts"
    / "build_fixed_candidate_demo_future_request_construction_readiness_plan.py",
    "broker_local_reconciliation": BASE_DIR / "scripts" / "check_fixed_candidate_demo_broker_local_state_reconciliation.py",
    "live_signal_freshness": BASE_DIR / "scripts" / "check_fixed_candidate_demo_live_signal_freshness.py",
    "manual_approval_gate_dry_run": BASE_DIR / "scripts" / "check_fixed_candidate_demo_manual_approval_gate_dry_run.py",
    "approval_record_creation": BASE_DIR / "scripts" / "create_fixed_candidate_demo_manual_approval_record.py",
}
ALLOWED_CHILD_SCRIPTS = frozenset(path.resolve() for path in SCRIPT_PATHS.values())
DISALLOWED_CHILD_NAME_PARTS = (
    "paper_signal_logger",
    "paper_trade_tracker",
    "local_paper_cycle",
    "replay",
    "backtest",
    "cost_sensitivity",
    "holdout",
    "stress",
    "walk_forward",
    "walk-forward",
    "baseline",
    "import_price_bars",
    "generate_price_features",
    "shadow_signal_once",
    "scheduler",
)

SHADOW_MANIFEST = "fixed_candidate_demo_shadow_signal_once_manifest.json"
OUTPUT_MANIFEST = "fixed_candidate_demo_manual_approval_prep_pipeline_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_manual_approval_prep_pipeline_report.md"
OUTPUT_STEPS = "fixed_candidate_demo_manual_approval_prep_pipeline_steps.csv"
OUTPUT_CHILD_COMMANDS = "fixed_candidate_demo_manual_approval_prep_pipeline_child_commands.csv"
OUTPUT_CHILD_RESULTS = "fixed_candidate_demo_manual_approval_prep_pipeline_child_results.csv"
OUTPUT_STATUS = "fixed_candidate_demo_manual_approval_prep_pipeline_status.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_manual_approval_prep_pipeline_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_manual_approval_prep_pipeline_no_order_evidence.csv"

MAIN_FIELDNAMES = [
    "run_id",
    "step_index",
    "step_key",
    "step_label",
    "pipeline_status",
    "child_status",
    "manifest_path",
    "status_field",
    "status_value",
    "expected_status",
    "blocking_warning",
    "caveat",
]
COMMAND_FIELDNAMES = [
    "run_id",
    "step_index",
    "step_key",
    "command_executable",
    "command_args_json",
    "output_dir",
    "expected_manifest_path",
    "allowed_child_script",
    "broker_read_step",
    "allow_broker_read_forwarded",
    "allow_order_calc_margin_forwarded",
    "planned_only",
    "caveat",
]
CHILD_RESULT_FIELDNAMES = [
    "run_id",
    "step_key",
    "return_code",
    "started_at",
    "completed_at",
    "duration_seconds",
    "stdout_tail",
    "stderr_tail",
    "child_status",
    "blocking_warning",
]
STATUS_FIELDNAMES = [
    "run_id",
    "pipeline_status",
    "final_step_completed",
    "failed_step",
    "approval_record_created",
    "approval_record_json_written",
    "blocking_warnings_count",
    "recommended_next_step",
]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
NO_ORDER_FIELDNAMES = [
    "run_id",
    "request_construction_performed",
    "broker_payload_constructed",
    "order_object_constructed",
    "order_check_called",
    "order_send_called",
    "order_execution_performed",
    "future_state_json_written",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "no_trading_decision_performed",
    "evidence_label",
    "caveat",
]

MUST_BE_TRUE_WHEN_PRESENT = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_profit_called",
    "no_history_orders_get_called",
    "no_history_deals_get_called",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "no_trading_decision_performed",
    "no_demo_broker_approval_performed",
)
MUST_BE_FALSE_WHEN_PRESENT = (
    "request_construction_allowed_now",
    "broker_request_constructed",
    "broker_payload_constructed",
    "order_object_constructed",
    "order_execution_allowed",
    "future_state_json_written",
)
HARD_MARGIN_CAP_RATIO = 0.70


@dataclass(frozen=True)
class StepSpec:
    index: int
    key: str
    label: str
    script: Path
    output_subdir: str
    manifest_name: str
    status_field: str
    acceptable_statuses: tuple[str, ...]
    timeout_seconds: int = 120
    broker_read_step: bool = False
    real_approval_step: bool = False


BASE_STEPS = (
    StepSpec(
        1,
        "would_signal_review",
        "would-signal review",
        SCRIPT_PATHS["would_signal_review"],
        "01_would_signal_review",
        "fixed_candidate_demo_would_signal_review_manifest.json",
        "review_status",
        ("would_signal_review_available_no_order",),
    ),
    StepSpec(
        2,
        "order_shadow_plan",
        "order shadow plan",
        SCRIPT_PATHS["order_shadow_plan"],
        "02_order_shadow_plan",
        "fixed_candidate_demo_order_shadow_plan_manifest.json",
        "plan_status",
        ("order_shadow_plan_available_no_order",),
    ),
    StepSpec(
        3,
        "order_request_shadow_design",
        "order request shadow design",
        SCRIPT_PATHS["order_request_shadow_design"],
        "03_order_request_shadow_design",
        "fixed_candidate_demo_order_request_shadow_design_manifest.json",
        "design_status",
        ("order_request_shadow_design_available_no_order",),
    ),
    StepSpec(
        4,
        "risk_volume_shadow_plan",
        "risk/volume shadow plan",
        SCRIPT_PATHS["risk_volume_shadow_plan"],
        "04_risk_volume_shadow_plan",
        "fixed_candidate_demo_risk_volume_shadow_plan_manifest.json",
        "plan_status",
        ("risk_volume_shadow_plan_available_no_order",),
    ),
    StepSpec(
        5,
        "margin_feasibility_plan",
        "margin feasibility plan",
        SCRIPT_PATHS["margin_feasibility_plan"],
        "05_margin_feasibility_plan",
        "fixed_candidate_demo_margin_feasibility_plan_manifest.json",
        "plan_status",
        ("margin_feasibility_plan_available_no_order",),
    ),
    StepSpec(
        6,
        "broker_safe_margin_validation",
        "broker-safe margin validation",
        SCRIPT_PATHS["broker_safe_margin_validation"],
        "06_broker_safe_margin_validation",
        "fixed_candidate_demo_broker_safe_margin_validation_manifest.json",
        "validation_status",
        ("broker_safe_margin_validation_available", "broker_safe_margin_validation_available_with_margin_warning"),
        broker_read_step=True,
    ),
    StepSpec(
        7,
        "state_reconciliation_plan",
        "state reconciliation plan",
        SCRIPT_PATHS["state_reconciliation_plan"],
        "07_state_reconciliation_plan",
        "fixed_candidate_demo_state_reconciliation_plan_manifest.json",
        "plan_status",
        ("state_reconciliation_plan_available_no_order",),
    ),
    StepSpec(
        8,
        "duplicate_protection_plan",
        "duplicate protection plan",
        SCRIPT_PATHS["duplicate_protection_plan"],
        "08_duplicate_protection_plan",
        "fixed_candidate_demo_duplicate_protection_plan_manifest.json",
        "plan_status",
        ("duplicate_protection_plan_available_no_order",),
    ),
    StepSpec(
        9,
        "manual_approval_kill_switch_plan",
        "manual approval / kill-switch plan",
        SCRIPT_PATHS["manual_approval_kill_switch_plan"],
        "09_manual_approval_kill_switch_plan",
        "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json",
        "plan_status",
        ("manual_approval_kill_switch_plan_available_no_order",),
    ),
    StepSpec(
        10,
        "future_broker_state_reconciliation_check_plan",
        "future broker/local reconciliation check plan",
        SCRIPT_PATHS["future_broker_state_reconciliation_check_plan"],
        "10_future_broker_state_reconciliation_check_plan",
        "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_manifest.json",
        "plan_status",
        ("future_broker_state_reconciliation_check_plan_available_no_order",),
    ),
    StepSpec(
        11,
        "future_request_construction_readiness_plan",
        "future request construction readiness plan",
        SCRIPT_PATHS["future_request_construction_readiness_plan"],
        "11_future_request_construction_readiness_plan",
        "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json",
        "plan_status",
        ("future_request_construction_readiness_plan_available_no_order",),
    ),
    StepSpec(
        12,
        "broker_local_reconciliation",
        "broker/local state reconciliation",
        SCRIPT_PATHS["broker_local_reconciliation"],
        "12_broker_local_reconciliation",
        "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json",
        "reconciliation_status",
        ("broker_local_reconciliation_clean_no_local_no_broker",),
        broker_read_step=True,
    ),
    StepSpec(
        13,
        "live_signal_freshness",
        "live signal freshness",
        SCRIPT_PATHS["live_signal_freshness"],
        "13_live_signal_freshness",
        "fixed_candidate_demo_live_signal_freshness_manifest.json",
        "freshness_status",
        ("live_signal_freshness_fresh_current_or_latest_signal", "live_signal_freshness_fresh_within_horizon"),
    ),
    StepSpec(
        14,
        "manual_approval_gate_dry_run",
        "manual approval gate dry-run",
        SCRIPT_PATHS["manual_approval_gate_dry_run"],
        "14_manual_approval_gate_dry_run",
        "fixed_candidate_demo_manual_approval_gate_dry_run_manifest.json",
        "gate_status",
        ("manual_approval_gate_dry_run_passed_non_actionable",),
    ),
    StepSpec(
        15,
        "approval_record_creation_dry_run",
        "approval record creation dry-run",
        SCRIPT_PATHS["approval_record_creation"],
        "15_approval_record_creation_dry_run",
        "fixed_candidate_demo_manual_approval_record_creation_manifest.json",
        "creation_status",
        ("manual_approval_record_creation_dry_run_no_record_created",),
    ),
)
REAL_APPROVAL_STEP = StepSpec(
    16,
    "approval_record_creation_real",
    "approval record creation real",
    SCRIPT_PATHS["approval_record_creation"],
    "16_approval_record_creation_real",
    "fixed_candidate_demo_manual_approval_record_creation_manifest.json",
    "creation_status",
    ("manual_approval_record_created_for_future_request_construction_only",),
    real_approval_step=True,
)


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(value, dict):
        return {}, "JSON root must be an object"
    return value, ""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def warning_row(
    *,
    run_id: str,
    warning_code: str,
    message: str,
    source: Path | str,
    blocking_warning: bool,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "warning_code": warning_code,
        "severity": "error" if blocking_warning else severity,
        "message": message,
        "source": str(source),
        "blocking_warning": bool_text(blocking_warning),
    }


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
    warning_code: str,
    message: str,
    source: Path | str,
    blocking_warning: bool,
    severity: str = "warning",
) -> None:
    warnings.append(
        warning_row(
            run_id=args.run_id,
            warning_code=warning_code,
            message=message,
            source=source,
            blocking_warning=blocking_warning,
            severity=severity,
        )
    )


def output_dir_for(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "steps": output_dir / OUTPUT_STEPS,
        "child_commands": output_dir / OUTPUT_CHILD_COMMANDS,
        "child_results": output_dir / OUTPUT_CHILD_RESULTS,
        "status": output_dir / OUTPUT_STATUS,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
    }


def ensure_outputs_writable(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)


def step_output_dir(output_dir: Path, step: StepSpec) -> Path:
    return output_dir / step.output_subdir


def expected_manifest_path(output_dir: Path, step: StepSpec) -> Path:
    return step_output_dir(output_dir, step) / step.manifest_name


def child_script_allowed(path: Path) -> bool:
    resolved = path.resolve()
    lowered = path.name.lower()
    return resolved in ALLOWED_CHILD_SCRIPTS and not any(part in lowered for part in DISALLOWED_CHILD_NAME_PARTS)


def append_common_args(command: list[str], args: argparse.Namespace, output_dir: Path) -> None:
    command.extend(["--canonical-registry", str(args.canonical_registry)])
    command.extend(["--output-dir", str(output_dir)])
    if args.overwrite:
        command.append("--overwrite")


def forwards_allow_broker_read(step: StepSpec, args: argparse.Namespace) -> bool:
    return bool(args.allow_broker_read_checks and step.broker_read_step)


def forwards_allow_order_calc_margin(step: StepSpec, args: argparse.Namespace) -> bool:
    return bool(args.allow_broker_read_checks and step.key == "broker_safe_margin_validation")


def append_broker_read_child_flags(command: list[str], step: StepSpec, args: argparse.Namespace) -> None:
    if forwards_allow_broker_read(step, args):
        command.append("--allow-broker-read")
    if forwards_allow_order_calc_margin(step, args):
        command.append("--allow-order-calc-margin")


def child_command_for(step: StepSpec, args: argparse.Namespace, output_dir: Path) -> list[str]:
    command = ["python", str(step.script), "--run-id", f"{args.run_id}_{step.key}"]
    step_dir = step_output_dir(output_dir, step)
    dirs = {spec.key: step_output_dir(output_dir, spec) for spec in BASE_STEPS}
    dirs[REAL_APPROVAL_STEP.key] = step_output_dir(output_dir, REAL_APPROVAL_STEP)

    if step.key == "would_signal_review":
        command.extend(["--shadow-signal-dir", str(args.shadow_signal_dir)])
        append_common_args(command, args, step_dir)
    elif step.key == "order_shadow_plan":
        command.extend(["--would-signal-review-dir", str(dirs["would_signal_review"])])
        append_common_args(command, args, step_dir)
    elif step.key == "order_request_shadow_design":
        command.extend(["--order-shadow-plan-dir", str(dirs["order_shadow_plan"])])
        append_common_args(command, args, step_dir)
    elif step.key == "risk_volume_shadow_plan":
        command.extend(["--order-request-shadow-design-dir", str(dirs["order_request_shadow_design"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        append_common_args(command, args, step_dir)
    elif step.key == "margin_feasibility_plan":
        command.extend(["--risk-volume-shadow-plan-dir", str(dirs["risk_volume_shadow_plan"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        append_common_args(command, args, step_dir)
    elif step.key == "broker_safe_margin_validation":
        command.extend(["--risk-volume-shadow-plan-dir", str(dirs["risk_volume_shadow_plan"])])
        command.extend(["--margin-feasibility-plan-dir", str(dirs["margin_feasibility_plan"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        append_common_args(command, args, step_dir)
        append_broker_read_child_flags(command, step, args)
    elif step.key == "state_reconciliation_plan":
        command.extend(["--broker-safe-margin-validation-dir", str(dirs["broker_safe_margin_validation"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        command.extend(["--future-state-json", str(args.future_state_json)])
        append_common_args(command, args, step_dir)
    elif step.key == "duplicate_protection_plan":
        command.extend(["--state-reconciliation-plan-dir", str(dirs["state_reconciliation_plan"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        command.extend(["--future-state-json", str(args.future_state_json)])
        append_common_args(command, args, step_dir)
    elif step.key == "manual_approval_kill_switch_plan":
        command.extend(["--duplicate-protection-plan-dir", str(dirs["duplicate_protection_plan"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        command.extend(["--future-state-json", str(args.future_state_json)])
        append_common_args(command, args, step_dir)
    elif step.key == "future_broker_state_reconciliation_check_plan":
        command.extend(["--manual-approval-kill-switch-plan-dir", str(dirs["manual_approval_kill_switch_plan"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        command.extend(["--future-state-json", str(args.future_state_json)])
        append_common_args(command, args, step_dir)
    elif step.key == "future_request_construction_readiness_plan":
        command.extend(
            [
                "--future-broker-state-reconciliation-check-plan-dir",
                str(dirs["future_broker_state_reconciliation_check_plan"]),
            ]
        )
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        command.extend(["--future-state-json", str(args.future_state_json)])
        append_common_args(command, args, step_dir)
    elif step.key == "broker_local_reconciliation":
        command.extend(["--future-request-construction-readiness-plan-dir", str(dirs["future_request_construction_readiness_plan"])])
        command.extend(["--broker-safe-margin-validation-dir", str(dirs["broker_safe_margin_validation"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        command.extend(["--future-state-json", str(args.future_state_json)])
        append_common_args(command, args, step_dir)
        append_broker_read_child_flags(command, step, args)
    elif step.key == "live_signal_freshness":
        command.extend(["--would-signal-review-dir", str(dirs["would_signal_review"])])
        command.extend(["--broker-local-reconciliation-dir", str(dirs["broker_local_reconciliation"])])
        command.extend(["--future-request-readiness-plan-dir", str(dirs["future_request_construction_readiness_plan"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        append_common_args(command, args, step_dir)
    elif step.key == "manual_approval_gate_dry_run":
        command.extend(["--would-signal-review-dir", str(dirs["would_signal_review"])])
        command.extend(["--broker-safe-margin-validation-dir", str(dirs["broker_safe_margin_validation"])])
        command.extend(["--duplicate-protection-plan-dir", str(dirs["duplicate_protection_plan"])])
        command.extend(["--manual-approval-kill-switch-plan-dir", str(dirs["manual_approval_kill_switch_plan"])])
        command.extend(["--future-request-readiness-plan-dir", str(dirs["future_request_construction_readiness_plan"])])
        command.extend(["--broker-local-reconciliation-dir", str(dirs["broker_local_reconciliation"])])
        command.extend(["--live-signal-freshness-dir", str(dirs["live_signal_freshness"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        command.extend(["--future-state-json", str(args.future_state_json)])
        append_common_args(command, args, step_dir)
    elif step.key in {"approval_record_creation_dry_run", "approval_record_creation_real"}:
        command.extend(["--manual-approval-gate-dry-run-dir", str(dirs["manual_approval_gate_dry_run"])])
        command.extend(["--would-signal-review-dir", str(dirs["would_signal_review"])])
        command.extend(["--live-signal-freshness-dir", str(dirs["live_signal_freshness"])])
        command.extend(["--broker-local-reconciliation-dir", str(dirs["broker_local_reconciliation"])])
        command.extend(["--broker-safe-margin-validation-dir", str(dirs["broker_safe_margin_validation"])])
        command.extend(["--duplicate-protection-plan-dir", str(dirs["duplicate_protection_plan"])])
        command.extend(["--manual-approval-kill-switch-plan-dir", str(dirs["manual_approval_kill_switch_plan"])])
        command.extend(["--future-request-readiness-plan-dir", str(dirs["future_request_construction_readiness_plan"])])
        command.extend(["--demo-execution-policy", str(args.demo_execution_policy)])
        command.extend(["--future-approval-record-json", str(args.future_approval_record_json)])
        command.extend(["--future-state-json", str(args.future_state_json)])
        if args.operator_decision_label:
            command.extend(["--operator-decision-label", args.operator_decision_label])
        if args.operator_identity_ref:
            command.extend(["--operator-identity-ref", args.operator_identity_ref])
        if args.operator_warning_acknowledgment:
            command.extend(["--operator-warning-acknowledgment", args.operator_warning_acknowledgment])
        if args.approval_note:
            command.extend(["--approval-note", args.approval_note])
        if args.module_validation_demo_execution:
            command.append("--module-validation-demo-execution")
        if args.allow_expired_signal_for_demo_module_validation:
            command.append("--allow-expired-signal-for-demo-module-validation")
        if args.expired_signal_override_acknowledgment:
            command.extend(
                [
                    "--expired-signal-override-acknowledgment",
                    args.expired_signal_override_acknowledgment,
                ]
            )
        if step.key == "approval_record_creation_dry_run":
            command.append("--dry-run")
        append_common_args(command, args, step_dir)
    else:
        raise ValueError(f"Unhandled step {step.key}")
    return command


def command_rows(args: argparse.Namespace, output_dir: Path, steps: tuple[StepSpec, ...]) -> list[dict[str, Any]]:
    rows = []
    for step in steps:
        command = child_command_for(step, args, output_dir)
        rows.append(
            {
                "run_id": args.run_id,
                "step_index": step.index,
                "step_key": step.key,
                "command_executable": command[0],
                "command_args_json": command[1:],
                "output_dir": str(step_output_dir(output_dir, step)),
                "expected_manifest_path": str(expected_manifest_path(output_dir, step)),
                "allowed_child_script": child_script_allowed(step.script),
                "broker_read_step": step.broker_read_step,
                "allow_broker_read_forwarded": forwards_allow_broker_read(step, args),
                "allow_order_calc_margin_forwarded": forwards_allow_order_calc_margin(step, args),
                "planned_only": False,
                "caveat": "broker reads require explicit allow flag" if step.broker_read_step else "no request/no execution child",
            }
        )
    return rows


def value_is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def value_is_false(value: Any) -> bool:
    return value is False or str(value).strip().lower() == "false"


def shadow_signal_validation_failures(manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if manifest.get("shadow_status") != "shadow_signal_detected":
        failures.append("shadow_status")
    if manifest.get("manual_review_required") is not True:
        failures.append("manual_review_required")
    if manifest.get("cycle_status") != "demo_no_order_cycle_completed_would_signal":
        failures.append("cycle_status")
    if (safe_int(manifest.get("blocking_warnings_count")) or 0) != 0:
        failures.append("blocking_warnings_count")
    if (safe_int(manifest.get("unsafe_no_order_flag_count")) or 0) != 0:
        failures.append("unsafe_no_order_flag_count")
    if (safe_int(manifest.get("missing_no_order_flag_count")) or 0) != 0:
        failures.append("missing_no_order_flag_count")

    for flag in (
        "no_order_boundary_confirmed",
        "no_order_execution_performed",
        "no_order_check_called",
        "no_order_send_called",
        "no_order_request_constructed",
    ):
        if not value_is_true(manifest.get(flag)):
            failures.append(flag)

    for flag in ("order_request_construction_allowed", "order_execution_allowed"):
        if not value_is_false(manifest.get(flag)):
            failures.append(flag)

    for flag in (
        "order_execution_performed",
        "order_check_called",
        "order_send_called",
        "order_request_constructed",
        "demo_broker_approval_performed",
    ):
        if value_is_true(manifest.get(flag)):
            failures.append(flag)

    if manifest.get("live_alignment_status") != "live_data_aligned_with_mt5_latest_bar":
        failures.append("live_alignment_status")
    if manifest.get("live_spread_gate_status") != "live_spread_within_policy":
        failures.append("live_spread_gate_status")
    if manifest.get("current_broker_spread_points") in ("", None):
        failures.append("current_broker_spread_points")
    if not value_is_true(manifest.get("current_broker_spread_within_policy")):
        failures.append("current_broker_spread_within_policy")
    return failures


def load_shadow(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> tuple[dict[str, Any], str | None]:
    path = Path(args.shadow_signal_dir) / SHADOW_MANIFEST
    manifest, error = read_json(path)
    if error:
        add_warning(
            warnings,
            args=args,
            warning_code="shadow_signal_manifest_missing_or_unreadable",
            message=error,
            source=path,
            blocking_warning=True,
        )
        return manifest, "manual_approval_prep_pipeline_blocked_shadow_signal_not_detected"
    failures = shadow_signal_validation_failures(manifest)
    if failures:
        add_warning(
            warnings,
            args=args,
            warning_code="shadow_signal_not_detected",
            message="Shadow signal source did not satisfy detected/manual-review/no-order/live-gate requirements: "
            + ", ".join(failures),
            source=path,
            blocking_warning=True,
        )
        return manifest, "manual_approval_prep_pipeline_blocked_shadow_signal_not_detected"
    return manifest, None


def run_child(command: list[str], step: StepSpec) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, shell=False, timeout=step.timeout_seconds)
        return_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        child_status = "success" if return_code == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        return_code = -1
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else "child command timed out"
        child_status = "failed"
    finished = datetime.now(timezone.utc)
    return {
        "step_key": step.key,
        "return_code": return_code,
        "started_at": started.isoformat(),
        "completed_at": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "stdout_tail": stdout[-1000:],
        "stderr_tail": stderr[-1000:],
        "child_status": child_status,
        "blocking_warning": child_status != "success",
    }


def not_executed_result(step: StepSpec, status: str, run_id: str = "") -> dict[str, Any]:
    return {
        "run_id": run_id,
        "step_key": step.key,
        "return_code": "",
        "started_at": "",
        "completed_at": "",
        "duration_seconds": "",
        "stdout_tail": "",
        "stderr_tail": "",
        "child_status": status,
        "blocking_warning": status != "not_executed_after_pipeline_completion",
    }


def status_from_step_failure(step: StepSpec, manifest: dict[str, Any]) -> str:
    status = str(manifest.get(step.status_field) or "")
    if step.key == "live_signal_freshness" or "stale" in status:
        return "manual_approval_prep_pipeline_blocked_stale_signal"
    if step.key == "broker_safe_margin_validation":
        return "manual_approval_prep_pipeline_blocked_margin"
    if step.key == "broker_local_reconciliation":
        return "manual_approval_prep_pipeline_blocked_broker_local_reconciliation"
    if step.key == "approval_record_creation_dry_run":
        return "manual_approval_prep_pipeline_blocked_approval_dry_run"
    return "manual_approval_prep_pipeline_blocked_step_status"


def acceptable_status(step: StepSpec, manifest: dict[str, Any]) -> bool:
    status = str(manifest.get(step.status_field) or "")
    if status not in step.acceptable_statuses:
        return False
    if step.key == "broker_safe_margin_validation":
        ratio = safe_float(manifest.get("broker_margin_usage_ratio") or manifest.get("margin_usage_ratio"))
        if ratio is not None and ratio > HARD_MARGIN_CAP_RATIO:
            return False
        if status == "broker_safe_margin_validation_available_with_margin_warning" and ratio is None:
            return False
    if step.key == "approval_record_creation_dry_run":
        return (safe_int(manifest.get("blocking_warnings_count")) or 0) == 0
    return True


def safety_boundary_violations(step: StepSpec, manifest: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for flag in MUST_BE_TRUE_WHEN_PRESENT:
        if flag in manifest and manifest.get(flag) is not True:
            violations.append(flag)
    if step.key != "broker_safe_margin_validation" and "no_order_calc_margin_called" in manifest and manifest.get("no_order_calc_margin_called") is not True:
        violations.append("no_order_calc_margin_called")
    if step.key != "broker_local_reconciliation":
        for flag in ("no_positions_get_called", "no_orders_get_called"):
            if flag in manifest and manifest.get(flag) is not True:
                violations.append(flag)
    for flag in MUST_BE_FALSE_WHEN_PRESENT:
        if flag in manifest and manifest.get(flag) is not False:
            violations.append(flag)
    return violations


def real_approval_preconditions(args: argparse.Namespace, dry_manifest: dict[str, Any]) -> tuple[bool, str]:
    if not args.allow_real_approval_record:
        return False, "manual_approval_prep_pipeline_blocked_real_approval_not_allowed"
    if args.operator_decision_label != "approve_for_future_request_construction_only":
        return False, "manual_approval_prep_pipeline_blocked_real_approval_not_allowed"
    if not args.operator_identity_ref:
        return False, "manual_approval_prep_pipeline_blocked_real_approval_not_allowed"
    if not args.operator_warning_acknowledgment:
        return False, "manual_approval_prep_pipeline_blocked_real_approval_not_allowed"
    if (safe_int(dry_manifest.get("blocking_warnings_count")) or 0) != 0:
        return False, "manual_approval_prep_pipeline_blocked_approval_dry_run"
    return True, ""


def execute_pipeline(
    args: argparse.Namespace,
    output_dir: Path,
    warnings: list[dict[str, Any]],
    shadow_manifest: dict[str, Any],
    initial_status: str | None,
) -> dict[str, Any]:
    steps: list[StepSpec] = list(BASE_STEPS)
    executed_manifests: dict[str, dict[str, Any]] = {}
    child_results: list[dict[str, Any]] = []
    final_step_completed = ""
    failed_step = ""
    pipeline_status = initial_status or ""

    if initial_status:
        child_results = [not_executed_result(step, "not_executed_blocked", args.run_id) for step in BASE_STEPS]
        return {
            "pipeline_status": pipeline_status,
            "child_results": child_results,
            "executed_manifests": executed_manifests,
            "steps": tuple(BASE_STEPS),
            "final_step_completed": final_step_completed,
            "failed_step": "shadow_signal",
        }

    if not all(child_script_allowed(step.script) for step in BASE_STEPS + (REAL_APPROVAL_STEP,)):
        add_warning(
            warnings,
            args=args,
            warning_code="child_script_not_allowlisted",
            message="At least one child script is outside the approval prep allowlist.",
            source="child_allowlist",
            blocking_warning=True,
        )
        child_results = [not_executed_result(step, "not_executed_blocked", args.run_id) for step in BASE_STEPS]
        return {
            "pipeline_status": "manual_approval_prep_pipeline_blocked_child_failure",
            "child_results": child_results,
            "executed_manifests": executed_manifests,
            "steps": tuple(BASE_STEPS),
            "final_step_completed": final_step_completed,
            "failed_step": "child_allowlist",
        }

    for index, step in enumerate(BASE_STEPS):
        if step.broker_read_step and not args.allow_broker_read_checks:
            failed_step = step.key
            pipeline_status = "manual_approval_prep_pipeline_blocked_broker_reads_not_allowed"
            add_warning(
                warnings,
                args=args,
                warning_code="broker_reads_not_allowed",
                message=f"Step {step.key} requires explicit broker-read permission.",
                source=step.script,
                blocking_warning=True,
            )
            child_results.append(not_executed_result(step, "not_executed_blocked", args.run_id))
            child_results.extend(not_executed_result(later, "not_executed_after_failure", args.run_id) for later in BASE_STEPS[index + 1 :])
            return {
                "pipeline_status": pipeline_status,
                "child_results": child_results,
                "executed_manifests": executed_manifests,
                "steps": tuple(BASE_STEPS),
                "final_step_completed": final_step_completed,
                "failed_step": failed_step,
            }

        command = child_command_for(step, args, output_dir)
        result = run_child(command, step)
        result["run_id"] = args.run_id
        child_results.append(result)
        if result["child_status"] != "success":
            failed_step = step.key
            pipeline_status = "manual_approval_prep_pipeline_blocked_child_failure"
            add_warning(
                warnings,
                args=args,
                warning_code="child_command_failed",
                message=f"Child step {step.key} returned {result['return_code']}.",
                source=step.script,
                blocking_warning=True,
            )
            child_results.extend(not_executed_result(later, "not_executed_after_failure", args.run_id) for later in BASE_STEPS[index + 1 :])
            return {
                "pipeline_status": pipeline_status,
                "child_results": child_results,
                "executed_manifests": executed_manifests,
                "steps": tuple(BASE_STEPS),
                "final_step_completed": final_step_completed,
                "failed_step": failed_step,
            }

        manifest_path = expected_manifest_path(output_dir, step)
        manifest, error = read_json(manifest_path)
        if error:
            failed_step = step.key
            pipeline_status = "manual_approval_prep_pipeline_blocked_missing_manifest"
            add_warning(
                warnings,
                args=args,
                warning_code="child_manifest_missing",
                message=f"Child manifest missing or unreadable: {error}",
                source=manifest_path,
                blocking_warning=True,
            )
            child_results.extend(not_executed_result(later, "not_executed_after_failure", args.run_id) for later in BASE_STEPS[index + 1 :])
            return {
                "pipeline_status": pipeline_status,
                "child_results": child_results,
                "executed_manifests": executed_manifests,
                "steps": tuple(BASE_STEPS),
                "final_step_completed": final_step_completed,
                "failed_step": failed_step,
            }

        executed_manifests[step.key] = manifest
        violations = safety_boundary_violations(step, manifest)
        if violations:
            failed_step = step.key
            pipeline_status = "manual_approval_prep_pipeline_blocked_safety_boundary_violation"
            add_warning(
                warnings,
                args=args,
                warning_code="child_safety_boundary_violation",
                message=f"Child step {step.key} unsafe flags: {', '.join(violations)}.",
                source=manifest_path,
                blocking_warning=True,
            )
            child_results.extend(not_executed_result(later, "not_executed_after_failure", args.run_id) for later in BASE_STEPS[index + 1 :])
            return {
                "pipeline_status": pipeline_status,
                "child_results": child_results,
                "executed_manifests": executed_manifests,
                "steps": tuple(BASE_STEPS),
                "final_step_completed": final_step_completed,
                "failed_step": failed_step,
            }

        if not acceptable_status(step, manifest):
            failed_step = step.key
            pipeline_status = status_from_step_failure(step, manifest)
            add_warning(
                warnings,
                args=args,
                warning_code="child_step_status_blocked",
                message=f"Child step {step.key} status {manifest.get(step.status_field)!r} is not acceptable.",
                source=manifest_path,
                blocking_warning=True,
            )
            child_results.extend(not_executed_result(later, "not_executed_after_failure", args.run_id) for later in BASE_STEPS[index + 1 :])
            return {
                "pipeline_status": pipeline_status,
                "child_results": child_results,
                "executed_manifests": executed_manifests,
                "steps": tuple(BASE_STEPS),
                "final_step_completed": final_step_completed,
                "failed_step": failed_step,
            }
        final_step_completed = step.key

    dry_manifest = executed_manifests["approval_record_creation_dry_run"]
    can_run_real, real_block_status = real_approval_preconditions(args, dry_manifest)
    if not args.allow_real_approval_record:
        pipeline_status = "manual_approval_prep_pipeline_completed_dry_run_ready_for_manual_real_approval_decision"
        return {
            "pipeline_status": pipeline_status,
            "child_results": child_results,
            "executed_manifests": executed_manifests,
            "steps": tuple(BASE_STEPS),
            "final_step_completed": final_step_completed,
            "failed_step": failed_step,
        }
    if not can_run_real:
        add_warning(
            warnings,
            args=args,
            warning_code="real_approval_precondition_failed",
            message="Real approval record creation was requested but preconditions were not satisfied.",
            source=expected_manifest_path(output_dir, BASE_STEPS[-1]),
            blocking_warning=True,
        )
        return {
            "pipeline_status": real_block_status,
            "child_results": child_results,
            "executed_manifests": executed_manifests,
            "steps": tuple(BASE_STEPS),
            "final_step_completed": final_step_completed,
            "failed_step": "approval_record_creation_real",
        }

    real_step = REAL_APPROVAL_STEP
    steps.append(real_step)
    result = run_child(child_command_for(real_step, args, output_dir), real_step)
    result["run_id"] = args.run_id
    child_results.append(result)
    if result["child_status"] != "success":
        add_warning(
            warnings,
            args=args,
            warning_code="child_command_failed",
            message=f"Real approval child returned {result['return_code']}.",
            source=real_step.script,
            blocking_warning=True,
        )
        return {
            "pipeline_status": "manual_approval_prep_pipeline_blocked_child_failure",
            "child_results": child_results,
            "executed_manifests": executed_manifests,
            "steps": tuple(steps),
            "final_step_completed": final_step_completed,
            "failed_step": real_step.key,
        }
    manifest_path = expected_manifest_path(output_dir, real_step)
    manifest, error = read_json(manifest_path)
    if error:
        add_warning(
            warnings,
            args=args,
            warning_code="child_manifest_missing",
            message=f"Real approval manifest missing or unreadable: {error}",
            source=manifest_path,
            blocking_warning=True,
        )
        return {
            "pipeline_status": "manual_approval_prep_pipeline_blocked_missing_manifest",
            "child_results": child_results,
            "executed_manifests": executed_manifests,
            "steps": tuple(steps),
            "final_step_completed": final_step_completed,
            "failed_step": real_step.key,
        }
    executed_manifests[real_step.key] = manifest
    violations = safety_boundary_violations(real_step, manifest)
    if violations:
        add_warning(
            warnings,
            args=args,
            warning_code="child_safety_boundary_violation",
            message=f"Real approval unsafe flags: {', '.join(violations)}.",
            source=manifest_path,
            blocking_warning=True,
        )
        return {
            "pipeline_status": "manual_approval_prep_pipeline_blocked_safety_boundary_violation",
            "child_results": child_results,
            "executed_manifests": executed_manifests,
            "steps": tuple(steps),
            "final_step_completed": final_step_completed,
            "failed_step": real_step.key,
        }
    if not acceptable_status(real_step, manifest):
        add_warning(
            warnings,
            args=args,
            warning_code="child_step_status_blocked",
            message=f"Real approval status {manifest.get(real_step.status_field)!r} is not acceptable.",
            source=manifest_path,
            blocking_warning=True,
        )
        return {
            "pipeline_status": "manual_approval_prep_pipeline_blocked_step_status",
            "child_results": child_results,
            "executed_manifests": executed_manifests,
            "steps": tuple(steps),
            "final_step_completed": final_step_completed,
            "failed_step": real_step.key,
        }
    return {
        "pipeline_status": "manual_approval_prep_pipeline_completed_real_approval_record_created_no_request",
        "child_results": child_results,
        "executed_manifests": executed_manifests,
        "steps": tuple(steps),
        "final_step_completed": real_step.key,
        "failed_step": "",
    }


def recommended_next_step(status: str) -> str:
    if status == "manual_approval_prep_pipeline_completed_dry_run_ready_for_manual_real_approval_decision":
        return "review_dry_run_artifacts_before_any_manual_real_approval_record_creation"
    if status == "manual_approval_prep_pipeline_completed_real_approval_record_created_no_request":
        return "stop_and_run_post_approval_pre_request_recheck_before_any_future_request_construction"
    if status == "manual_approval_prep_pipeline_blocked_broker_reads_not_allowed":
        return "rerun_with_allow_broker_read_checks_only_when_demo_terminal_ready"
    return "fix_blocking_manual_approval_prep_pipeline_input_or_step"


def step_rows(args: argparse.Namespace, output_dir: Path, pipeline: dict[str, Any]) -> list[dict[str, Any]]:
    manifests = pipeline["executed_manifests"]
    rows = []
    for step in pipeline["steps"]:
        manifest_path = expected_manifest_path(output_dir, step)
        manifest = manifests.get(step.key, {})
        rows.append(
            {
                "run_id": args.run_id,
                "step_index": step.index,
                "step_key": step.key,
                "step_label": step.label,
                "pipeline_status": pipeline["pipeline_status"],
                "child_status": "completed" if step.key in manifests else "not_completed",
                "manifest_path": str(manifest_path),
                "status_field": step.status_field,
                "status_value": manifest.get(step.status_field, ""),
                "expected_status": ";".join(step.acceptable_statuses),
                "blocking_warning": bool_text(step.key == pipeline.get("failed_step")),
                "caveat": "broker read step" if step.broker_read_step else "no request/no execution step",
            }
        )
    return rows


def status_row(args: argparse.Namespace, pipeline: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    real_manifest = pipeline["executed_manifests"].get("approval_record_creation_real", {})
    return {
        "run_id": args.run_id,
        "pipeline_status": pipeline["pipeline_status"],
        "final_step_completed": pipeline["final_step_completed"],
        "failed_step": pipeline["failed_step"],
        "approval_record_created": real_manifest.get("approval_record_created", False),
        "approval_record_json_written": real_manifest.get("future_approval_record_written", False),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "recommended_next_step": recommended_next_step(pipeline["pipeline_status"]),
    }


def no_order_evidence_row(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "request_construction_performed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
        "order_check_called": False,
        "order_send_called": False,
        "order_execution_performed": False,
        "future_state_json_written": False,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "evidence_label": "manual_approval_prep_pipeline_no_order_boundary",
        "caveat": "broker read child steps require explicit allow flag; no request/no execution still enforced",
    }


def write_report(path: Path, args: argparse.Namespace, pipeline: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed-Candidate Demo Manual Approval Prep Pipeline",
        "",
        "Single-shot manual approval preparation pipeline. This is not a scheduler, live loop, execution module, request construction module, or trading decision.",
        "",
        "No broker request dictionaries, broker payloads, executable order objects, order sends, order checks, order-calc profit calls, database mutations, future trading state writes, replay/backtest/cost/holdout/paper workflows, schedulers, loops, or background tasks are performed by this orchestrator.",
        "",
        "Broker-read child steps are gated by `--allow-broker-read-checks`; the orchestrator itself does not import MT5 or call broker APIs directly.",
        "",
        "## Result",
        "",
        f"- pipeline_status: `{pipeline['pipeline_status']}`",
        f"- final_step_completed: `{pipeline['final_step_completed']}`",
        f"- failed_step: `{pipeline['failed_step']}`",
        f"- allow_broker_read_checks: `{bool_text(args.allow_broker_read_checks)}`",
        f"- allow_real_approval_record: `{bool_text(args.allow_real_approval_record)}`",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{sum(1 for warning in warnings if warning.get('blocking_warning') == 'true')}`",
        "",
        "## Child Steps",
        "",
    ]
    for step in pipeline["steps"]:
        manifest = pipeline["executed_manifests"].get(step.key, {})
        lines.append(f"- {step.index}. {step.key}: `{manifest.get(step.status_field, 'not_completed')}`")
    lines.extend(
        [
            "",
            "## Recommended Next Step",
            "",
            f"`{recommended_next_step(pipeline['pipeline_status'])}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    args: argparse.Namespace,
    output_dir: Path,
    pipeline: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> None:
    manifests = pipeline["executed_manifests"]
    real_manifest = manifests.get("approval_record_creation_real", {})
    manifest = {
        "run_id": args.run_id,
        "pipeline_status": pipeline["pipeline_status"],
        "shadow_signal_dir": str(args.shadow_signal_dir),
        "final_step_completed": pipeline["final_step_completed"],
        "failed_step": pipeline["failed_step"],
        "would_signal_review_dir": str(step_output_dir(output_dir, BASE_STEPS[0])),
        "order_shadow_plan_dir": str(step_output_dir(output_dir, BASE_STEPS[1])),
        "order_request_shadow_design_dir": str(step_output_dir(output_dir, BASE_STEPS[2])),
        "risk_volume_shadow_plan_dir": str(step_output_dir(output_dir, BASE_STEPS[3])),
        "margin_feasibility_plan_dir": str(step_output_dir(output_dir, BASE_STEPS[4])),
        "broker_safe_margin_validation_dir": str(step_output_dir(output_dir, BASE_STEPS[5])),
        "state_reconciliation_plan_dir": str(step_output_dir(output_dir, BASE_STEPS[6])),
        "duplicate_protection_plan_dir": str(step_output_dir(output_dir, BASE_STEPS[7])),
        "manual_approval_kill_switch_plan_dir": str(step_output_dir(output_dir, BASE_STEPS[8])),
        "future_broker_state_reconciliation_check_plan_dir": str(step_output_dir(output_dir, BASE_STEPS[9])),
        "future_request_construction_readiness_plan_dir": str(step_output_dir(output_dir, BASE_STEPS[10])),
        "broker_local_reconciliation_dir": str(step_output_dir(output_dir, BASE_STEPS[11])),
        "live_signal_freshness_dir": str(step_output_dir(output_dir, BASE_STEPS[12])),
        "manual_approval_gate_dry_run_dir": str(step_output_dir(output_dir, BASE_STEPS[13])),
        "approval_record_creation_dry_run_dir": str(step_output_dir(output_dir, BASE_STEPS[14])),
        "approval_record_creation_real_dir": str(step_output_dir(output_dir, REAL_APPROVAL_STEP)) if "approval_record_creation_real" in manifests else "",
        "approval_record_created": bool(real_manifest.get("approval_record_created", False)),
        "approval_record_json_written": bool(real_manifest.get("future_approval_record_written", False)),
        "future_state_json_written": False,
        "request_construction_performed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
        "order_check_called": False,
        "order_send_called": False,
        "order_execution_performed": False,
        "allow_broker_read_checks": bool(args.allow_broker_read_checks),
        "broker_child_allow_broker_read_forwarded": any(
            forwards_allow_broker_read(step, args) for step in pipeline["steps"]
        ),
        "broker_child_allow_order_calc_margin_forwarded": any(
            forwards_allow_order_calc_margin(step, args) for step in pipeline["steps"]
        ),
        "broker_read_children_require_explicit_flags": True,
        "allow_real_approval_record": bool(args.allow_real_approval_record),
        "dry_run_approval_only": bool(args.dry_run_approval_only),
        "module_validation_demo_execution": bool(args.module_validation_demo_execution),
        "expired_signal_override_requested": bool(
            args.allow_expired_signal_for_demo_module_validation
            or args.expired_signal_override_acknowledgment
        ),
        "expired_signal_override_used": any(
            bool(manifest.get("expired_signal_override_used"))
            for manifest in manifests.values()
            if isinstance(manifest, dict)
        ),
        "created_at_utc": utc_now_text(),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "child_command_count": len(pipeline["steps"]),
        "child_success_count": sum(1 for result in pipeline["child_results"] if result.get("child_status") == "success"),
        "child_failure_count": sum(1 for result in pipeline["child_results"] if result.get("child_status") == "failed"),
        "recommended_next_step": recommended_next_step(pipeline["pipeline_status"]),
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_candidate_quality_final_decision_performed": True,
    }
    write_json(path, manifest)


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    if args.allow_real_approval_record:
        args.dry_run_approval_only = False
    output_dir = output_dir_for(args)
    paths = output_paths(output_dir)
    ensure_outputs_writable(paths, bool(args.overwrite))
    warnings: list[dict[str, Any]] = []
    shadow_manifest, initial_status = load_shadow(args, warnings)
    pipeline = execute_pipeline(args, output_dir, warnings, shadow_manifest, initial_status)
    all_steps = pipeline["steps"]

    write_csv(paths["steps"], step_rows(args, output_dir, pipeline), MAIN_FIELDNAMES)
    write_csv(paths["child_commands"], command_rows(args, output_dir, all_steps), COMMAND_FIELDNAMES)
    write_csv(paths["child_results"], pipeline["child_results"], CHILD_RESULT_FIELDNAMES)
    write_csv(paths["status"], [status_row(args, pipeline, warnings)], STATUS_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["no_order"], [no_order_evidence_row(args)], NO_ORDER_FIELDNAMES)
    write_report(paths["report"], args, pipeline, warnings)
    write_manifest(paths["manifest"], args, output_dir, pipeline, warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one fixed-candidate demo manual approval preparation pipeline.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--shadow-signal-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_DEMO_EXECUTION_POLICY)
    parser.add_argument("--future-state-json", type=Path, default=DEFAULT_FUTURE_STATE_JSON)
    parser.add_argument("--future-approval-record-json", type=Path, default=DEFAULT_FUTURE_APPROVAL_RECORD_JSON)
    parser.add_argument("--operator-decision-label")
    parser.add_argument("--operator-identity-ref")
    parser.add_argument("--operator-warning-acknowledgment")
    parser.add_argument("--approval-note", default="")
    parser.add_argument("--allow-broker-read-checks", action="store_true")
    parser.add_argument("--module-validation-demo-execution", action="store_true")
    parser.add_argument("--allow-expired-signal-for-demo-module-validation", action="store_true")
    parser.add_argument("--expired-signal-override-acknowledgment", default="")
    parser.add_argument("--allow-real-approval-record", action="store_true")
    parser.add_argument("--dry-run-approval-only", action="store_true", default=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = build_outputs(args)
    print("Fixed-candidate demo manual approval prep pipeline complete.")
    for key, path in paths.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
