"""Dry-run the fixed-candidate manual approval gate.

This module reads existing no-order artifacts and determines whether the future
manual approval gate prerequisites are currently satisfied. It does not perform
manual approval, ask for operator input, write future state, query broker/API
state, construct broker payloads, execute orders, mutate databases, run child
scripts, schedule work, or make trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
CANDIDATE_SYMBOL = "GBPUSD"
CANDIDATE_TIMEFRAME = "M15"
CANDIDATE_DIRECTION = "short"
MAX_SPREAD_POINTS = 15.0
MAX_OPEN_POSITIONS = 1
HORIZON_BARS = 10
HARD_MARGIN_CAP_RATIO = 0.70
ACCEPTABLE_MARGIN_VALIDATION_STATUSES = {
    "broker_safe_margin_validation_available",
    "broker_safe_margin_validation_available_with_margin_warning",
}
VOLUME_TOLERANCE = 1e-9

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_gate_dry_run"
DEFAULT_WOULD_SIGNAL_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_would_signal_review"
    / "gbpusd_short_h10_1_5_off_hours_demo_would_signal_review_live_v1"
)
DEFAULT_BROKER_SAFE_MARGIN_VALIDATION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_broker_safe_margin_validation"
    / "gbpusd_short_h10_1_5_off_hours_demo_broker_safe_margin_validation_live_v1"
)
DEFAULT_DUPLICATE_PROTECTION_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_duplicate_protection_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_duplicate_protection_plan_live_v1"
)
DEFAULT_MANUAL_APPROVAL_KILL_SWITCH_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_manual_approval_kill_switch_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_kill_switch_plan_live_v1"
)
DEFAULT_FUTURE_REQUEST_READINESS_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_future_request_construction_readiness_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_future_request_construction_readiness_plan_live_v1"
)
DEFAULT_BROKER_LOCAL_RECONCILIATION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_broker_local_state_reconciliation"
    / "gbpusd_short_h10_1_5_off_hours_demo_broker_local_state_reconciliation_real_v1"
)
DEFAULT_LIVE_SIGNAL_FRESHNESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_live_signal_freshness"
    / "gbpusd_short_h10_1_5_off_hours_demo_live_signal_freshness_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_DEMO_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE_JSON = BASE_DIR / "state" / "fixed_candidate_demo_state" / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_manual_approval_gate_dry_run"

WOULD_SIGNAL_MANIFEST = "fixed_candidate_demo_would_signal_review_manifest.json"
MARGIN_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"
DUPLICATE_MANIFEST = "fixed_candidate_demo_duplicate_protection_plan_manifest.json"
MANUAL_PLAN_MANIFEST = "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json"
FUTURE_REQUEST_MANIFEST = "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json"
BROKER_RECON_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
FRESHNESS_MANIFEST = "fixed_candidate_demo_live_signal_freshness_manifest.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_manual_approval_gate_dry_run_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_manual_approval_gate_dry_run_report.md"
OUTPUT_GATE_CHECKS = "fixed_candidate_demo_manual_approval_gate_dry_run_gate_checks.csv"
OUTPUT_UPSTREAM = "fixed_candidate_demo_manual_approval_gate_dry_run_upstream_evidence.csv"
OUTPUT_OPERATOR_CHECKLIST = "fixed_candidate_demo_manual_approval_gate_dry_run_operator_checklist_preview.csv"
OUTPUT_BLOCK_CONDITIONS = "fixed_candidate_demo_manual_approval_gate_dry_run_block_conditions.csv"
OUTPUT_AUDIT_PREVIEW = "fixed_candidate_demo_manual_approval_gate_dry_run_audit_preview.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_manual_approval_gate_dry_run_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_manual_approval_gate_dry_run_no_order_evidence.csv"

GATE_FIELDNAMES = [
    "run_id",
    "gate_name",
    "gate_status",
    "observed_value",
    "expected_value",
    "blocking_if_failed",
    "source_path",
    "caveat",
    "warning_code",
]
UPSTREAM_FIELDNAMES = [
    "run_id",
    "source_area",
    "source_path",
    "source_run_id",
    "source_status",
    "observed_value",
    "expected_value",
    "evidence_label",
    "blocking_if_failed",
]
OPERATOR_FIELDNAMES = [
    "run_id",
    "checklist_item",
    "preview_status",
    "observed_value",
    "required_before",
    "operator_input_requested",
    "caveat",
]
BLOCK_FIELDNAMES = [
    "run_id",
    "block_condition",
    "condition_present",
    "blocking_if_present",
    "observed_value",
    "source_path",
    "caveat",
]
AUDIT_FIELDNAMES = [
    "run_id",
    "audit_field",
    "audit_value",
    "source_path",
    "audit_preview_only",
    "caveat",
]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
NO_ORDER_FIELDNAMES = [
    "run_id",
    "no_mt5_import_performed",
    "no_mt5_connection_performed",
    "no_broker_api_query_performed",
    "no_positions_get_called",
    "no_orders_get_called",
    "no_history_orders_get_called",
    "no_history_deals_get_called",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_broker_payload_constructed",
    "no_executable_order_object_constructed",
    "no_db_mutation_performed",
    "no_future_state_json_written",
    "no_child_scripts_executed",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "no_trading_decision_performed",
    "no_manual_approval_performed",
    "no_demo_broker_approval_performed",
    "evidence_label",
    "caveat",
]


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


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [warning for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"]


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "gate_checks": output_dir / OUTPUT_GATE_CHECKS,
        "upstream": output_dir / OUTPUT_UPSTREAM,
        "operator_checklist": output_dir / OUTPUT_OPERATOR_CHECKLIST,
        "block_conditions": output_dir / OUTPUT_BLOCK_CONDITIONS,
        "audit_preview": output_dir / OUTPUT_AUDIT_PREVIEW,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def validate_canonical_registry(registry: dict[str, Any]) -> bool:
    horizon = registry.get("horizon_bars")
    return (
        registry.get("candidate_id") == CANDIDATE_ID
        and registry.get("symbol") == CANDIDATE_SYMBOL
        and registry.get("timeframe") == CANDIDATE_TIMEFRAME
        and registry.get("direction") == CANDIDATE_DIRECTION
        and registry.get("spread_unit") == "broker_points"
        and safe_float(registry.get("max_spread_points")) == MAX_SPREAD_POINTS
        and safe_float(registry.get("max_open_positions")) in (None, float(MAX_OPEN_POSITIONS))
        and (horizon in ("", None) or safe_float(horizon) == float(HORIZON_BARS))
    )


def validate_demo_policy(policy: dict[str, Any]) -> bool:
    boundaries = policy.get("safety_boundaries")
    if not isinstance(boundaries, dict):
        return False
    return (
        policy.get("candidate_id") == CANDIDATE_ID
        and policy.get("symbol") == CANDIDATE_SYMBOL
        and policy.get("timeframe") == CANDIDATE_TIMEFRAME
        and policy.get("direction") == CANDIDATE_DIRECTION
        and policy.get("spread_unit") == "broker_points"
        and safe_float(policy.get("max_spread_points")) == MAX_SPREAD_POINTS
        and safe_float(policy.get("max_open_positions")) == float(MAX_OPEN_POSITIONS)
        and safe_float(policy.get("max_margin_usage_ratio")) == HARD_MARGIN_CAP_RATIO
        and boundaries.get("real_money_allowed") is False
        and boundaries.get("order_execution_allowed") is False
        and boundaries.get("order_request_construction_allowed") is False
        and boundaries.get("order_check_allowed") is False
        and boundaries.get("order_calc_allowed") is False
        and boundaries.get("manual_approval_required_before_any_future_demo_order") is True
    )


def no_order_flags_ok(manifest: dict[str, Any]) -> bool:
    for flag in ("no_order_execution_performed", "no_order_request_constructed"):
        if flag in manifest and manifest.get(flag) is not True:
            return False
    return True


def validate_would_signal(manifest: dict[str, Any]) -> tuple[bool, str]:
    checks = (
        manifest.get("review_status") == "would_signal_review_available_no_order",
        manifest.get("source_nature") == "live_data_shadow_signal",
        manifest.get("shadow_status") == "shadow_signal_detected",
        manifest.get("manual_review_required") is True,
        manifest.get("actionable_signal") is False,
        manifest.get("order_execution_allowed") is False,
        manifest.get("order_request_construction_allowed") is False,
    )
    return (all(checks), "" if all(checks) else "would_signal_review")


def validate_margin(manifest: dict[str, Any], snapshot: dict[str, Any]) -> tuple[bool, str]:
    manifest_status = manifest.get("validation_status")
    snapshot_status = snapshot.get("validation_status")
    usage = safe_float(manifest.get("broker_margin_usage_ratio"))
    snapshot_usage = safe_float(snapshot.get("broker_margin_usage_ratio"))
    manifest_volume = safe_float(manifest.get("stepped_volume_lots"))
    snapshot_volume = safe_float(snapshot.get("margin_calc_volume_lots"))
    volume_matches = (
        manifest_volume is not None
        and manifest_volume > 0
        and snapshot_volume is not None
        and snapshot_volume > 0
        and abs(manifest_volume - snapshot_volume) <= VOLUME_TOLERANCE
    )
    checks = (
        manifest_status in ACCEPTABLE_MARGIN_VALIDATION_STATUSES,
        manifest.get("source_nature") == "live_data_shadow_signal",
        manifest.get("account_mode_label") == "demo",
        manifest.get("account_currency") == "EUR",
        manifest.get("account_equity_policy_status") == "within_10pct",
        usage is not None and usage <= HARD_MARGIN_CAP_RATIO,
        manifest.get("spread_within_policy") is True,
        volume_matches,
        snapshot_status in ("", None) or snapshot_status in ACCEPTABLE_MARGIN_VALIDATION_STATUSES,
        snapshot_usage is None or snapshot_usage <= HARD_MARGIN_CAP_RATIO,
    )
    return (all(checks), "" if all(checks) else "broker_safe_margin")


def validate_duplicate(manifest: dict[str, Any]) -> tuple[bool, str]:
    checks = (
        manifest.get("plan_status") == "duplicate_protection_plan_available_no_order",
        manifest.get("source_nature") == "live_data_shadow_signal",
        safe_float(manifest.get("max_open_positions")) == float(MAX_OPEN_POSITIONS),
        manifest.get("plan_actionable") is False,
    )
    return (all(checks), "" if all(checks) else "duplicate_protection")


def validate_manual_plan(manifest: dict[str, Any]) -> tuple[bool, str]:
    checks = (
        manifest.get("plan_status") == "manual_approval_kill_switch_plan_available_no_order",
        manifest.get("source_nature") == "live_data_shadow_signal",
        manifest.get("manual_approval_performed") is False,
        manifest.get("kill_switch_executed") is False,
        manifest.get("plan_actionable") is False,
    )
    return (all(checks), "" if all(checks) else "manual_approval_plan")


def validate_future_request(manifest: dict[str, Any]) -> tuple[bool, str]:
    false_flags = (
        "request_construction_allowed_now",
        "broker_request_constructed",
        "broker_payload_constructed",
        "order_object_constructed",
    )
    checks = (
        manifest.get("plan_status") == "future_request_construction_readiness_plan_available_no_order",
        manifest.get("source_nature") == "live_data_shadow_signal",
        all(manifest.get(flag) in (False, None) for flag in false_flags),
    )
    return (all(checks), "" if all(checks) else "future_request_readiness")


def validate_reconciliation(manifest: dict[str, Any]) -> tuple[bool, str]:
    checks = (
        manifest.get("reconciliation_status") == "broker_local_reconciliation_clean_no_local_no_broker",
        manifest.get("source_nature") == "live_data_shadow_signal",
        int(manifest.get("broker_position_count_symbol", -1)) == 0,
        int(manifest.get("broker_pending_order_count_symbol", -1)) == 0,
        manifest.get("request_construction_allowed_now") is False,
    )
    return (all(checks), "" if all(checks) else "broker_local_reconciliation")


def validate_freshness(manifest: dict[str, Any]) -> tuple[bool, str]:
    allowed = {
        "live_signal_freshness_fresh_current_or_latest_signal",
        "live_signal_freshness_fresh_within_horizon",
    }
    checks = (
        manifest.get("freshness_status") in allowed,
        manifest.get("source_nature") in ("", None, "live_data_shadow_signal"),
        manifest.get("is_fresh") is True,
        manifest.get("is_stale") is False,
        safe_float(manifest.get("bars_elapsed")) is not None and safe_float(manifest.get("bars_elapsed")) <= HORIZON_BARS,
        manifest.get("future_manual_approval_allowed_now") is False,
        manifest.get("request_construction_allowed_now") is False,
    )
    return (all(checks), "" if all(checks) else "signal_freshness")


def source_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "registry": Path(args.canonical_registry),
        "policy": Path(args.demo_execution_policy),
        "would_signal": Path(args.would_signal_review_dir) / WOULD_SIGNAL_MANIFEST,
        "margin": Path(args.broker_safe_margin_validation_dir) / MARGIN_MANIFEST,
        "margin_snapshot": Path(args.broker_safe_margin_validation_dir) / MARGIN_SNAPSHOT,
        "duplicate": Path(args.duplicate_protection_plan_dir) / DUPLICATE_MANIFEST,
        "manual_plan": Path(args.manual_approval_kill_switch_plan_dir) / MANUAL_PLAN_MANIFEST,
        "future_request": Path(args.future_request_readiness_plan_dir) / FUTURE_REQUEST_MANIFEST,
        "reconciliation": Path(args.broker_local_reconciliation_dir) / BROKER_RECON_MANIFEST,
        "freshness": Path(args.live_signal_freshness_dir) / FRESHNESS_MANIFEST,
    }


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    paths = source_paths(args)
    inputs: dict[str, Any] = {"paths": paths, "errors": {}}
    for key, path in paths.items():
        data, error = read_json(path)
        inputs[key] = data
        inputs["errors"][key] = error
        if error:
            warnings.append(
                warning_row(
                    run_id=args.run_id,
                    warning_code=f"{key}_unreadable",
                    message=error,
                    source=path,
                    blocking_warning=True,
                )
            )
    return inputs


def gate_row(args: argparse.Namespace, name: str, passed: bool, observed: Any, expected: Any, source: Path | str, warning_code: str, caveat: str = "gate_only_non_actionable") -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "gate_name": name,
        "gate_status": "passed" if passed else "failed_blocking",
        "observed_value": observed,
        "expected_value": expected,
        "blocking_if_failed": not passed,
        "source_path": source,
        "caveat": caveat,
        "warning_code": "" if passed else warning_code,
    }


def evaluate_gates(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    paths = inputs["paths"]
    margin_ok, _ = validate_margin(inputs["margin"], inputs["margin_snapshot"])
    manual_ok, _ = validate_manual_plan(inputs["manual_plan"])
    return [
        gate_row(args, "gate_live_signal_review", validate_would_signal(inputs["would_signal"])[0], inputs["would_signal"].get("review_status"), "would_signal_review_available_no_order", paths["would_signal"], "would_signal_review_failed"),
        gate_row(args, "gate_broker_safe_margin", margin_ok, inputs["margin"].get("broker_margin_usage_ratio"), f"<= {HARD_MARGIN_CAP_RATIO} and coherent margin volume", paths["margin"], "broker_safe_margin_failed"),
        gate_row(args, "gate_duplicate_protection", validate_duplicate(inputs["duplicate"])[0], inputs["duplicate"].get("plan_status"), "duplicate_protection_plan_available_no_order", paths["duplicate"], "duplicate_protection_failed"),
        gate_row(args, "gate_manual_approval_plan", manual_ok, inputs["manual_plan"].get("plan_status"), "manual_approval_kill_switch_plan_available_no_order", paths["manual_plan"], "manual_plan_failed"),
        gate_row(args, "gate_kill_switch_plan", manual_ok and inputs["manual_plan"].get("kill_switch_executed") is False, inputs["manual_plan"].get("kill_switch_executed"), False, paths["manual_plan"], "kill_switch_plan_failed"),
        gate_row(args, "gate_future_request_readiness", validate_future_request(inputs["future_request"])[0], inputs["future_request"].get("plan_status"), "future_request_construction_readiness_plan_available_no_order", paths["future_request"], "future_request_readiness_failed"),
        gate_row(args, "gate_broker_local_reconciliation", validate_reconciliation(inputs["reconciliation"])[0], inputs["reconciliation"].get("reconciliation_status"), "broker_local_reconciliation_clean_no_local_no_broker", paths["reconciliation"], "reconciliation_failed"),
        gate_row(args, "gate_signal_freshness", validate_freshness(inputs["freshness"])[0], inputs["freshness"].get("freshness_status"), "fresh and within h10", paths["freshness"], "freshness_failed"),
        gate_row(args, "gate_demo_policy", validate_demo_policy(inputs["policy"]), inputs["policy"].get("policy_id"), "no request/no execution policy", paths["policy"], "demo_policy_failed"),
        gate_row(args, "gate_no_request_boundary", no_order_flags_ok(inputs["future_request"]) and inputs["future_request"].get("request_construction_allowed_now") is False, inputs["future_request"].get("request_construction_allowed_now"), False, paths["future_request"], "request_boundary_failed"),
        gate_row(args, "gate_future_state_not_mutated", True, Path(args.future_state_json).exists(), "existence observed only; no write", args.future_state_json, "future_state_mutation_attempted"),
        gate_row(args, "gate_no_scheduler", True, "no scheduler/loop/background behavior", "none", __file__, "scheduler_detected"),
    ]


def determine_status(inputs: dict[str, Any], gates: list[dict[str, Any]]) -> str:
    errors = inputs["errors"]
    if any(error == "missing" for error in errors.values()):
        return "manual_approval_gate_dry_run_blocked_missing_upstream_artifact"
    if errors["registry"] or not validate_canonical_registry(inputs["registry"]):
        return "manual_approval_gate_dry_run_blocked_noncanonical_candidate"
    if errors["policy"] or not validate_demo_policy(inputs["policy"]):
        return "manual_approval_gate_dry_run_blocked_noncanonical_demo_execution_policy"
    if not validate_freshness(inputs["freshness"])[0]:
        if inputs["freshness"].get("freshness_status") == "live_signal_freshness_stale_beyond_horizon":
            return "manual_approval_gate_dry_run_blocked_stale_signal"
        return "manual_approval_gate_dry_run_blocked_unacceptable_upstream_status"
    if not validate_reconciliation(inputs["reconciliation"])[0]:
        return "manual_approval_gate_dry_run_blocked_broker_local_reconciliation"
    if not validate_margin(inputs["margin"], inputs["margin_snapshot"])[0]:
        return "manual_approval_gate_dry_run_blocked_margin_policy"
    if not validate_duplicate(inputs["duplicate"])[0]:
        return "manual_approval_gate_dry_run_blocked_duplicate_protection"
    if not validate_would_signal(inputs["would_signal"])[0] or not validate_manual_plan(inputs["manual_plan"])[0] or not validate_future_request(inputs["future_request"])[0]:
        return "manual_approval_gate_dry_run_blocked_unacceptable_upstream_status"
    if any(row["gate_status"] == "failed_blocking" for row in gates):
        return "manual_approval_gate_dry_run_blocked_unacceptable_upstream_status"
    return "manual_approval_gate_dry_run_passed_non_actionable"


def add_status_warning(args: argparse.Namespace, warnings: list[dict[str, Any]], status: str) -> None:
    if status == "manual_approval_gate_dry_run_passed_non_actionable":
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="manual_approval_gate_passed_but_non_actionable",
                message="All required dry-run gates passed, but manual approval, request construction, and execution remain blocked.",
                source=args.output_dir or DEFAULT_OUTPUT_ROOT,
                blocking_warning=False,
            )
        )
    else:
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code=status,
                message="Manual approval gate dry-run is blocked by one or more prerequisites.",
                source=args.output_dir or DEFAULT_OUTPUT_ROOT,
                blocking_warning=True,
            )
        )


def upstream_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    specs = [
        ("canonical_registry", "registry", inputs["registry"].get("candidate_id"), CANDIDATE_ID, "canonical_candidate_confirmed", validate_canonical_registry(inputs["registry"])),
        ("demo_execution_policy", "policy", inputs["policy"].get("policy_id"), "no request/no execution policy", "demo_policy_confirmed", validate_demo_policy(inputs["policy"])),
        ("would_signal_review", "would_signal", inputs["would_signal"].get("review_status"), "would_signal_review_available_no_order", "would_signal_confirmed", validate_would_signal(inputs["would_signal"])[0]),
        ("broker_safe_margin_validation", "margin", inputs["margin"].get("validation_status"), "available margin validation status", "margin_validation_confirmed", validate_margin(inputs["margin"], inputs["margin_snapshot"])[0]),
        ("duplicate_protection_plan", "duplicate", inputs["duplicate"].get("plan_status"), "duplicate_protection_plan_available_no_order", "duplicate_protection_confirmed", validate_duplicate(inputs["duplicate"])[0]),
        ("manual_approval_kill_switch_plan", "manual_plan", inputs["manual_plan"].get("plan_status"), "manual_approval_kill_switch_plan_available_no_order", "manual_plan_confirmed", validate_manual_plan(inputs["manual_plan"])[0]),
        ("future_request_readiness", "future_request", inputs["future_request"].get("plan_status"), "future_request_construction_readiness_plan_available_no_order", "future_request_readiness_confirmed", validate_future_request(inputs["future_request"])[0]),
        ("broker_local_reconciliation", "reconciliation", inputs["reconciliation"].get("reconciliation_status"), "broker_local_reconciliation_clean_no_local_no_broker", "reconciliation_confirmed", validate_reconciliation(inputs["reconciliation"])[0]),
        ("live_signal_freshness", "freshness", inputs["freshness"].get("freshness_status"), "fresh within h10", "freshness_confirmed", validate_freshness(inputs["freshness"])[0]),
    ]
    rows = []
    for area, key, observed, expected, label, passed in specs:
        rows.append(
            {
                "run_id": args.run_id,
                "source_area": area,
                "source_path": inputs["paths"][key],
                "source_run_id": inputs[key].get("run_id", ""),
                "source_status": "passed" if passed else "failed",
                "observed_value": observed,
                "expected_value": expected,
                "evidence_label": label,
                "blocking_if_failed": not passed,
            }
        )
    return rows


def operator_checklist_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    items = [
        ("confirm demo account only", inputs["margin"].get("account_mode_label"), "before any future manual approval schema"),
        ("confirm source is live-data no-order signal", inputs["would_signal"].get("source_nature"), "before any future manual approval schema"),
        ("confirm signal freshness", inputs["freshness"].get("freshness_status"), "before any future manual approval schema"),
        ("confirm broker/local reconciliation clean", inputs["reconciliation"].get("reconciliation_status"), "before any future manual approval schema"),
        ("confirm broker margin below hard cap", inputs["margin"].get("broker_margin_usage_ratio"), "before any future manual approval schema"),
        ("confirm spread within policy", inputs["margin"].get("spread_within_policy"), "before any future manual approval schema"),
        ("confirm max_open_positions = 1", inputs["duplicate"].get("max_open_positions"), "before any future manual approval schema"),
        ("confirm no local state mutation", Path(args.future_state_json).exists(), "future_state_existence_check_only"),
        ("confirm no request construction", False, "always false in this dry-run"),
        ("confirm no order execution", False, "always false in this dry-run"),
    ]
    return [
        {
            "run_id": args.run_id,
            "checklist_item": item,
            "preview_status": "preview_only_not_requested",
            "observed_value": observed,
            "required_before": required_before,
            "operator_input_requested": False,
            "caveat": "operator_preview_only_no_approval_record",
        }
        for item, observed, required_before in items
    ]


def block_condition_rows(args: argparse.Namespace, inputs: dict[str, Any], status: str) -> list[dict[str, Any]]:
    stale = inputs["freshness"].get("freshness_status") == "live_signal_freshness_stale_beyond_horizon"
    usage = safe_float(inputs["margin"].get("broker_margin_usage_ratio"))
    block_specs = [
        ("stale signal", stale, inputs["freshness"].get("freshness_status"), inputs["paths"]["freshness"]),
        ("missing live signal", inputs["errors"].get("would_signal") == "missing", inputs["errors"].get("would_signal"), inputs["paths"]["would_signal"]),
        ("fixture source", inputs["would_signal"].get("fixture_not_live_market_data") is True, inputs["would_signal"].get("fixture_not_live_market_data"), inputs["paths"]["would_signal"]),
        ("margin above hard cap", usage is None or usage > HARD_MARGIN_CAP_RATIO, usage, inputs["paths"]["margin"]),
        ("spread above policy", inputs["margin"].get("spread_within_policy") is not True, inputs["margin"].get("spread_within_policy"), inputs["paths"]["margin"]),
        ("broker/local reconciliation not clean", not validate_reconciliation(inputs["reconciliation"])[0], inputs["reconciliation"].get("reconciliation_status"), inputs["paths"]["reconciliation"]),
        ("duplicate protection not available", not validate_duplicate(inputs["duplicate"])[0], inputs["duplicate"].get("plan_status"), inputs["paths"]["duplicate"]),
        ("unsafe demo policy", not validate_demo_policy(inputs["policy"]), inputs["policy"].get("policy_id"), inputs["paths"]["policy"]),
        ("future request readiness boundary unsafe", not validate_future_request(inputs["future_request"])[0], inputs["future_request"].get("plan_status"), inputs["paths"]["future_request"]),
        ("local state already exists and is not explicitly handled", Path(args.future_state_json).exists(), Path(args.future_state_json).exists(), args.future_state_json),
        ("future state mutation attempted", False, False, args.future_state_json),
        ("scheduler/loop/background detected", False, False, __file__),
    ]
    return [
        {
            "run_id": args.run_id,
            "block_condition": name,
            "condition_present": bool(present),
            "blocking_if_present": name != "local state already exists and is not explicitly handled" or status != "manual_approval_gate_dry_run_passed_non_actionable",
            "observed_value": observed,
            "source_path": source,
            "caveat": "block_condition_preview_no_action_taken",
        }
        for name, present, observed, source in block_specs
    ]


def audit_preview_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    values = {
        "would_signal_review_run_id": inputs["would_signal"].get("run_id"),
        "signal_time_server": inputs["would_signal"].get("signal_time_server") or inputs["would_signal"].get("time_server"),
        "idempotency_reference": inputs["would_signal"].get("idempotency_reference", ""),
        "broker_margin_validation_run_id": inputs["margin"].get("run_id"),
        "broker_local_reconciliation_run_id": inputs["reconciliation"].get("run_id"),
        "freshness_run_id": inputs["freshness"].get("run_id"),
        "gate_dry_run_run_id": args.run_id,
        "manual_approval_performed": False,
        "request_constructed": False,
        "execution_performed": False,
    }
    source_map = {
        "would_signal_review_run_id": inputs["paths"]["would_signal"],
        "signal_time_server": inputs["paths"]["would_signal"],
        "idempotency_reference": inputs["paths"]["would_signal"],
        "broker_margin_validation_run_id": inputs["paths"]["margin"],
        "broker_local_reconciliation_run_id": inputs["paths"]["reconciliation"],
        "freshness_run_id": inputs["paths"]["freshness"],
        "gate_dry_run_run_id": args.output_dir or DEFAULT_OUTPUT_ROOT,
        "manual_approval_performed": args.output_dir or DEFAULT_OUTPUT_ROOT,
        "request_constructed": args.output_dir or DEFAULT_OUTPUT_ROOT,
        "execution_performed": args.output_dir or DEFAULT_OUTPUT_ROOT,
    }
    return [
        {
            "run_id": args.run_id,
            "audit_field": key,
            "audit_value": value,
            "source_path": source_map[key],
            "audit_preview_only": True,
            "caveat": "no_approval_audit_record_created",
        }
        for key, value in values.items()
    ]


def no_order_evidence_row(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "no_mt5_import_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_api_query_performed": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_broker_payload_constructed": True,
        "no_executable_order_object_constructed": True,
        "no_db_mutation_performed": True,
        "no_future_state_json_written": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_manual_approval_performed": True,
        "no_demo_broker_approval_performed": True,
        "evidence_label": "manual_approval_gate_dry_run_no_order_boundary",
        "caveat": "gate_only_no_operator_input_no_request_no_execution",
    }


def recommended_next_step(status: str) -> str:
    if status == "manual_approval_gate_dry_run_passed_non_actionable":
        return "design_explicit_manual_approval_record_schema_or_stop_before_real_approval"
    if status == "manual_approval_gate_dry_run_blocked_stale_signal":
        return "wait_for_new_live_data_would_signal"
    return "resolve_blocking_gate_before_any_manual_approval_path"


def write_report(path: Path, args: argparse.Namespace, status: str, inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Manual Approval Gate Dry-Run",
        "",
        "Gate-only dry-run for future manual approval prerequisites.",
        "No manual approval was performed.",
        "No operator input was requested.",
        "No approval record was created.",
        "No future state JSON was written or created.",
        "No MT5 import or connection was performed.",
        "No broker/API query or broker state read was performed.",
        "No request, broker payload, or executable order object was constructed.",
        "No order send, check, calc, or history function was called.",
        "No order execution was performed.",
        "No database mutation, child script, scheduler, loop, or background task was performed.",
        "No strategy optimization or threshold tuning was performed.",
        "This dry-run is not demo approval and not a trading decision.",
        "",
        "## Inputs",
        "",
        f"- would_signal_review_dir: `{args.would_signal_review_dir}`",
        f"- broker_safe_margin_validation_dir: `{args.broker_safe_margin_validation_dir}`",
        f"- duplicate_protection_plan_dir: `{args.duplicate_protection_plan_dir}`",
        f"- manual_approval_kill_switch_plan_dir: `{args.manual_approval_kill_switch_plan_dir}`",
        f"- future_request_readiness_plan_dir: `{args.future_request_readiness_plan_dir}`",
        f"- broker_local_reconciliation_dir: `{args.broker_local_reconciliation_dir}`",
        f"- live_signal_freshness_dir: `{args.live_signal_freshness_dir}`",
        "",
        "## Gate Result",
        "",
        f"- gate_status: `{status}`",
        f"- signal_time_server: `{inputs['would_signal'].get('signal_time_server') or inputs['would_signal'].get('time_server', '')}`",
        f"- freshness_status: `{inputs['freshness'].get('freshness_status', '')}`",
        f"- broker_local_reconciliation_status: `{inputs['reconciliation'].get('reconciliation_status', '')}`",
        f"- broker_margin_validation_status: `{inputs['margin'].get('validation_status', '')}`",
        f"- broker_margin_usage_ratio: `{inputs['margin'].get('broker_margin_usage_ratio', '')}`",
        "",
        "## Boundary",
        "",
        "- manual_approval_allowed_now: `false`",
        "- request_construction_allowed_now: `false`",
        "- order_execution_allowed: `false`",
        "",
        "## Warnings",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{recommended_next_step(status)}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(path: Path, args: argparse.Namespace, output_dir: Path, status: str, inputs: dict[str, Any], paths: dict[str, Path], warnings: list[dict[str, Any]]) -> None:
    manifest = {
        "run_id": args.run_id,
        "created_at_utc": utc_now_text(),
        "output_dir": str(output_dir),
        "gate_status": status,
        "candidate_id": inputs["registry"].get("candidate_id", CANDIDATE_ID),
        "symbol": inputs["registry"].get("symbol", CANDIDATE_SYMBOL),
        "timeframe": inputs["registry"].get("timeframe", CANDIDATE_TIMEFRAME),
        "direction": inputs["registry"].get("direction", CANDIDATE_DIRECTION),
        "source_nature": inputs["would_signal"].get("source_nature", ""),
        "signal_time_server": inputs["would_signal"].get("signal_time_server") or inputs["would_signal"].get("time_server", ""),
        "freshness_status": inputs["freshness"].get("freshness_status", ""),
        "broker_local_reconciliation_status": inputs["reconciliation"].get("reconciliation_status", ""),
        "broker_margin_validation_status": inputs["margin"].get("validation_status", ""),
        "broker_margin_usage_ratio": safe_float(inputs["margin"].get("broker_margin_usage_ratio")),
        "duplicate_protection_status": inputs["duplicate"].get("plan_status", ""),
        "future_request_readiness_status": inputs["future_request"].get("plan_status", ""),
        "manual_approval_allowed_now": False,
        "manual_approval_performed": False,
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
        "order_execution_allowed": False,
        "demo_approval_performed": False,
        "future_state_json": str(args.future_state_json),
        "future_state_json_exists": Path(args.future_state_json).exists(),
        "future_state_json_written": False,
        "recommended_next_step": recommended_next_step(status),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "output_files": {key: str(value) for key, value in paths.items()},
        "no_mt5_import_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_api_query_performed": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_broker_payload_constructed": True,
        "no_executable_order_object_constructed": True,
        "no_db_mutation_performed": True,
        "no_future_state_json_written": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_manual_approval_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_artifacts(args: argparse.Namespace, paths: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    inputs = load_inputs(args, warnings)
    gates = evaluate_gates(args, inputs)
    status = determine_status(inputs, gates)
    add_status_warning(args, warnings, status)
    upstream = upstream_rows(args, inputs)
    operator = operator_checklist_rows(args, inputs)
    blocks = block_condition_rows(args, inputs, status)
    audit = audit_preview_rows(args, inputs)
    write_csv(paths["gate_checks"], gates, GATE_FIELDNAMES)
    write_csv(paths["upstream"], upstream, UPSTREAM_FIELDNAMES)
    write_csv(paths["operator_checklist"], operator, OPERATOR_FIELDNAMES)
    write_csv(paths["block_conditions"], blocks, BLOCK_FIELDNAMES)
    write_csv(paths["audit_preview"], audit, AUDIT_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["no_order"], [no_order_evidence_row(args)], NO_ORDER_FIELDNAMES)
    write_report(paths["report"], args, status, inputs, warnings)
    write_manifest(paths["manifest"], args, output_dir, status, inputs, paths, warnings)
    return {"status": status, "warnings": warnings}


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    build_artifacts(args, paths, output_dir)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run fixed-candidate demo manual approval gate prerequisites without approving or constructing requests.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--would-signal-review-dir", type=Path, default=DEFAULT_WOULD_SIGNAL_REVIEW_DIR)
    parser.add_argument("--broker-safe-margin-validation-dir", type=Path, default=DEFAULT_BROKER_SAFE_MARGIN_VALIDATION_DIR)
    parser.add_argument("--duplicate-protection-plan-dir", type=Path, default=DEFAULT_DUPLICATE_PROTECTION_PLAN_DIR)
    parser.add_argument("--manual-approval-kill-switch-plan-dir", type=Path, default=DEFAULT_MANUAL_APPROVAL_KILL_SWITCH_PLAN_DIR)
    parser.add_argument("--future-request-readiness-plan-dir", type=Path, default=DEFAULT_FUTURE_REQUEST_READINESS_PLAN_DIR)
    parser.add_argument("--broker-local-reconciliation-dir", type=Path, default=DEFAULT_BROKER_LOCAL_RECONCILIATION_DIR)
    parser.add_argument("--live-signal-freshness-dir", type=Path, default=DEFAULT_LIVE_SIGNAL_FRESHNESS_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_DEMO_EXECUTION_POLICY)
    parser.add_argument("--future-state-json", type=Path, default=DEFAULT_FUTURE_STATE_JSON)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, csv.Error) as exc:
        print(f"Fixed-candidate manual approval gate dry-run failed: {exc}")
        return 1
    print("Fixed-candidate manual approval gate dry-run complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
