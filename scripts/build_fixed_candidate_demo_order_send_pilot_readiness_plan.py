"""Build an artifact-only readiness plan for a future demo order-send pilot.

This planner reads the fixed-candidate order-check artifact and upstream safety
artifacts, then writes a non-executable contract for a later send pilot module.
It does not import/connect to MT5, query broker/API state, call order-check or
send paths, construct or write an executable broker payload/order object,
execute orders, mutate databases, write future trading state, or run child
scripts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts import fixed_candidate_demo_state_contracts as state_contracts
except ModuleNotFoundError:
    import fixed_candidate_demo_state_contracts as state_contracts


BASE_DIR = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
SYMBOL = "GBPUSD"
TIMEFRAME = "M15"
DIRECTION = "short"
SIDE_INTENT = "sell"
ORDER_TYPE_INTENT = "market_sell"
MAX_SPREAD_POINTS = 15.0
MAX_OPEN_POSITIONS = 1
HORIZON_BARS = 10
HARD_MARGIN_CAP_RATIO = 0.70
ACCOUNT_CURRENCY = "EUR"
ACCEPTABLE_MARGIN_VALIDATION_STATUSES = {
    "broker_safe_margin_validation_available",
    "broker_safe_margin_validation_available_with_margin_warning",
}
REQUEST_CONSTRUCTION_AVAILABLE_STATUS = "request_construction_dry_run_available_non_executable"
REQUEST_CONSTRUCTION_STALE_OVERRIDE_STATUS = (
    "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
)
MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT = (
    "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only"
)
EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT = "acknowledge_expired_signal_for_demo_module_validation_only"
CLIENT_REJECT_RESEND_ACKNOWLEDGMENT = state_contracts.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT
VOLUME_TOLERANCE = 1e-9

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_order_send_pilot_readiness_plan"
DEFAULT_ORDER_CHECK_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_order_check"
    / "gbpusd_short_h10_1_5_off_hours_demo_order_check_dry_run_fixture_v1"
)
DEFAULT_ORDER_CHECK_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_order_check_readiness_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_order_check_readiness_plan_fixture_v1"
)
DEFAULT_REQUEST_CONSTRUCTION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_request_construction_dry_run"
    / "gbpusd_short_h10_1_5_off_hours_demo_request_construction_dry_run_fixture_v1"
)
DEFAULT_APPROVAL_RECORD_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record.json"
)
DEFAULT_SCHEMA_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_manual_approval_record_schema"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record_schema_v1"
)
DEFAULT_BROKER_LOCAL_RECONCILIATION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_broker_local_state_reconciliation"
    / "gbpusd_short_h10_1_5_off_hours_demo_broker_local_state_reconciliation_real_v1"
)
DEFAULT_BROKER_SAFE_MARGIN_VALIDATION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_broker_safe_margin_validation"
    / "gbpusd_short_h10_1_5_off_hours_demo_broker_safe_margin_validation_live_v1"
)
DEFAULT_LIVE_SIGNAL_FRESHNESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_live_signal_freshness"
    / "gbpusd_short_h10_1_5_off_hours_demo_live_signal_freshness_v1"
)
DEFAULT_DUPLICATE_PROTECTION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_duplicate_protection_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_duplicate_protection_plan_live_v1"
)
DEFAULT_MANUAL_APPROVAL_KILL_SWITCH_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_manual_approval_kill_switch_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_kill_switch_plan_live_v1"
)
DEFAULT_FUTURE_REQUEST_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_future_request_construction_readiness_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_future_request_construction_readiness_plan_live_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_DEMO_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR / "state" / "fixed_candidate_demo_state" / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_order_send_pilot_readiness_plan"

ORDER_CHECK_MANIFEST = "fixed_candidate_demo_order_check_manifest.json"
ORDER_CHECK_STATUS = "fixed_candidate_demo_order_check_status.csv"
ORDER_CHECK_GATES = "fixed_candidate_demo_order_check_gate_checks.csv"
ORDER_CHECK_BOUND_INTENT = "fixed_candidate_demo_order_check_bound_request_intent.csv"
ORDER_CHECK_PREVIEW = "fixed_candidate_demo_order_check_order_check_payload_preview.csv"
ORDER_CHECK_RESULT = "fixed_candidate_demo_order_check_result_snapshot.json"
READINESS_MANIFEST = "fixed_candidate_demo_order_check_readiness_plan_manifest.json"
REQUEST_MANIFEST = "fixed_candidate_demo_request_construction_dry_run_manifest.json"
SCHEMA_MANIFEST = "fixed_candidate_demo_manual_approval_record_schema_manifest.json"
BROKER_RECON_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
MARGIN_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"
FRESHNESS_MANIFEST = "fixed_candidate_demo_live_signal_freshness_manifest.json"
DUPLICATE_MANIFEST = "fixed_candidate_demo_duplicate_protection_plan_manifest.json"
MANUAL_PLAN_MANIFEST = "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json"
FUTURE_REQUEST_MANIFEST = "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_order_send_pilot_readiness_plan_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_order_send_pilot_readiness_plan_report.md"
OUTPUT_GATES = "fixed_candidate_demo_order_send_pilot_readiness_plan_gate_checks.csv"
OUTPUT_SEND_INPUTS = "fixed_candidate_demo_order_send_pilot_readiness_plan_future_order_send_inputs.csv"
OUTPUT_BROKER_SEND_FIELDS = "fixed_candidate_demo_order_send_pilot_readiness_plan_future_broker_send_fields.csv"
OUTPUT_PRE_SEND_RECHECKS = "fixed_candidate_demo_order_send_pilot_readiness_plan_pre_send_rechecks.csv"
OUTPUT_STATE_TRANSITIONS = "fixed_candidate_demo_order_send_pilot_readiness_plan_state_transition_plan.csv"
OUTPUT_RETCODES = "fixed_candidate_demo_order_send_pilot_readiness_plan_retcode_handling.csv"
OUTPUT_POST_SEND_RECON = "fixed_candidate_demo_order_send_pilot_readiness_plan_post_send_reconciliation.csv"
OUTPUT_CRASH_RECOVERY = "fixed_candidate_demo_order_send_pilot_readiness_plan_crash_recovery.csv"
OUTPUT_BLOCKS = "fixed_candidate_demo_order_send_pilot_readiness_plan_block_conditions.csv"
OUTPUT_BOUND_ORDER_CHECK = "fixed_candidate_demo_order_send_pilot_readiness_plan_bound_order_check.csv"
OUTPUT_BOUND_UPSTREAM = "fixed_candidate_demo_order_send_pilot_readiness_plan_bound_upstream_artifacts.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_order_send_pilot_readiness_plan_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_order_send_pilot_readiness_plan_no_order_evidence.csv"
OUTPUT_FUTURE_SEND_CLI = "fixed_candidate_demo_order_send_pilot_readiness_plan_future_send_cli_contract.csv"
OUTPUT_FINAL_CONFIRMATION = "fixed_candidate_demo_order_send_pilot_readiness_plan_final_operator_confirmation_contract.csv"
OUTPUT_BINDING = "fixed_candidate_demo_order_send_pilot_readiness_plan_request_order_check_send_binding.csv"
OUTPUT_ATOMIC_STATE = "fixed_candidate_demo_order_send_pilot_readiness_plan_atomic_state_contract.csv"
OUTPUT_POST_SEND_STATE = "fixed_candidate_demo_order_send_pilot_readiness_plan_post_send_state_update_contract.csv"
OUTPUT_FUTURE_SEND_TESTS = "fixed_candidate_demo_order_send_pilot_readiness_plan_future_send_test_contract.csv"
OUTPUT_FUTURE_SEND_SAFETY = "fixed_candidate_demo_order_send_pilot_readiness_plan_future_send_safety_grep_contract.csv"

WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
GATE_FIELDNAMES = [
    "run_id",
    "gate_name",
    "gate_status",
    "observed_value",
    "expected_value",
    "source_path",
    "blocking_if_failed",
    "warning_code",
]
SEND_INPUT_FIELDNAMES = [
    "run_id",
    "field_name",
    "intended_value",
    "source",
    "required_for_future_order_send",
    "must_be_rechecked_before_order_send",
    "broker_payload_field_now",
    "executable_now",
    "safety_note",
]
BROKER_SEND_FIELDNAMES = [
    "run_id",
    "future_mt5_field",
    "mapping_description",
    "source_or_future_source",
    "available_now",
    "requires_broker_read_at_send_time",
    "executable_now",
    "safety_note",
]
PRE_SEND_FIELDNAMES = [
    "run_id",
    "recheck_name",
    "timing",
    "required",
    "blocking_if_failed",
    "expected_value",
    "safety_note",
]
STATE_FIELDNAMES = ["run_id", "state_name", "meaning", "entered_by_future_module", "allowed_next_states", "blocking_for_new_order", "safety_note"]
RETCODE_FIELDNAMES = [
    "run_id",
    "retcode_category",
    "symbolic_retcode",
    "numeric_retcode_policy",
    "future_expected_action",
    "state_transition",
    "retry_allowed",
    "retry_allowed_default",
    "manual_review_required",
    "broker_local_reconciliation_required",
    "duplicate_rerun_behavior",
    "safety_note",
]
POST_SEND_FIELDNAMES = [
    "run_id",
    "requirement_name",
    "expected_future_behavior",
    "allowed_read",
    "max_call_count",
    "history_reads_allowed",
    "polling_allowed",
    "scheduler_allowed",
    "scope",
    "blocking_if_failed",
    "safety_note",
]
CRASH_FIELDNAMES = ["run_id", "crash_case", "future_recovery_action", "state_transition", "manual_review_required", "safety_note"]
BLOCK_FIELDNAMES = ["run_id", "block_condition", "condition_status", "observed_value", "expected_value", "blocking_if_failed", "caveat"]
BOUND_ORDER_CHECK_FIELDNAMES = [
    "run_id",
    "order_check_dir",
    "order_check_manifest_path",
    "order_check_status",
    "order_check_passed",
    "order_check_run_id",
    "binding_status",
    "sha256_digest",
]
BOUND_UPSTREAM_FIELDNAMES = [
    "run_id",
    "upstream_name",
    "upstream_path",
    "upstream_status_field",
    "upstream_status_value",
    "sha256_digest",
    "binding_status",
]
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
    "no_broker_payload_constructed",
    "no_executable_order_object_constructed",
    "no_future_state_json_written",
    "no_db_mutation_performed",
    "no_child_scripts_executed",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "no_trading_decision_performed",
    "no_demo_broker_approval_performed",
    "evidence_label",
    "caveat",
]
CLI_CONTRACT_FIELDNAMES = [
    "run_id",
    "future_script",
    "cli_flag",
    "required",
    "default_value",
    "purpose",
    "blocking_rule",
    "safety_note",
]
FINAL_CONFIRMATION_FIELDNAMES = [
    "run_id",
    "contract_item",
    "item_type",
    "required",
    "allowed_value",
    "allowed",
    "binding_scope",
    "blocking_if_failed",
    "safety_note",
]
BINDING_FIELDNAMES = [
    "run_id",
    "binding_name",
    "source_artifact",
    "digest_field",
    "recompute_immediately_before_send",
    "required_match",
    "blocking_if_mismatch",
    "safety_note",
]
ATOMIC_STATE_FIELDNAMES = [
    "run_id",
    "requirement_name",
    "required_fields",
    "timing",
    "atomicity_requirement",
    "blocking_if_failed",
    "state_on_failure",
    "safety_note",
]
POST_SEND_STATE_FIELDNAMES = [
    "run_id",
    "sequence_index",
    "requirement_name",
    "expected_future_behavior",
    "state_on_failure",
    "blocking_if_failed",
    "safety_note",
]
FUTURE_SEND_TEST_FIELDNAMES = [
    "run_id",
    "test_name",
    "scenario",
    "expected_result",
    "mocked_mt5_required",
    "exactly_once_send_expected",
    "no_send_expected",
    "safety_note",
]
FUTURE_SEND_SAFETY_FIELDNAMES = [
    "run_id",
    "rule_name",
    "expectation",
    "allowed_occurrence_count",
    "applies_to",
    "blocking_if_failed",
    "safety_note",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_text() -> str:
    return utc_now().isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


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


def parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
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


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], "missing"
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), ""
    except OSError as exc:
        return [], str(exc)


def write_json(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def output_dir_for(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "gate_checks": output_dir / OUTPUT_GATES,
        "send_inputs": output_dir / OUTPUT_SEND_INPUTS,
        "broker_send_fields": output_dir / OUTPUT_BROKER_SEND_FIELDS,
        "pre_send_rechecks": output_dir / OUTPUT_PRE_SEND_RECHECKS,
        "state_transitions": output_dir / OUTPUT_STATE_TRANSITIONS,
        "retcodes": output_dir / OUTPUT_RETCODES,
        "post_send_reconciliation": output_dir / OUTPUT_POST_SEND_RECON,
        "crash_recovery": output_dir / OUTPUT_CRASH_RECOVERY,
        "blocks": output_dir / OUTPUT_BLOCKS,
        "bound_order_check": output_dir / OUTPUT_BOUND_ORDER_CHECK,
        "bound_upstream": output_dir / OUTPUT_BOUND_UPSTREAM,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
        "future_send_cli_contract": output_dir / OUTPUT_FUTURE_SEND_CLI,
        "final_operator_confirmation_contract": output_dir / OUTPUT_FINAL_CONFIRMATION,
        "request_order_check_send_binding": output_dir / OUTPUT_BINDING,
        "atomic_state_contract": output_dir / OUTPUT_ATOMIC_STATE,
        "post_send_state_update_contract": output_dir / OUTPUT_POST_SEND_STATE,
        "future_send_test_contract": output_dir / OUTPUT_FUTURE_SEND_TESTS,
        "future_send_safety_grep_contract": output_dir / OUTPUT_FUTURE_SEND_SAFETY,
    }


def ensure_outputs_writable(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError("Output files already exist. Use --overwrite to replace them.")
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)


def source_paths(args: argparse.Namespace) -> dict[str, Path]:
    order_check_dir = Path(args.order_check_dir)
    readiness_dir = Path(args.order_check_readiness_plan_dir)
    request_dir = Path(args.request_construction_dry_run_dir)
    schema_dir = Path(args.manual_approval_record_schema_dir)
    return {
        "order_check_dir": order_check_dir,
        "order_check_manifest": order_check_dir / ORDER_CHECK_MANIFEST,
        "order_check_status": order_check_dir / ORDER_CHECK_STATUS,
        "order_check_gates": order_check_dir / ORDER_CHECK_GATES,
        "order_check_bound_intent": order_check_dir / ORDER_CHECK_BOUND_INTENT,
        "order_check_preview": order_check_dir / ORDER_CHECK_PREVIEW,
        "order_check_result": order_check_dir / ORDER_CHECK_RESULT,
        "readiness_manifest": readiness_dir / READINESS_MANIFEST,
        "request_manifest": request_dir / REQUEST_MANIFEST,
        "approval_record": Path(args.manual_approval_record_json),
        "schema_manifest": schema_dir / SCHEMA_MANIFEST,
        "reconciliation": Path(args.broker_local_reconciliation_dir) / BROKER_RECON_MANIFEST,
        "margin": Path(args.broker_safe_margin_validation_dir) / MARGIN_MANIFEST,
        "margin_snapshot": Path(args.broker_safe_margin_validation_dir) / MARGIN_SNAPSHOT,
        "freshness": Path(args.live_signal_freshness_dir) / FRESHNESS_MANIFEST,
        "duplicate": Path(args.duplicate_protection_plan_dir) / DUPLICATE_MANIFEST,
        "manual_plan": Path(args.manual_approval_kill_switch_plan_dir) / MANUAL_PLAN_MANIFEST,
        "future_request": Path(args.future_request_readiness_plan_dir) / FUTURE_REQUEST_MANIFEST,
        "registry": Path(args.canonical_registry),
        "policy": Path(args.demo_execution_policy),
        "future_state": Path(args.future_state_json),
    }


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
        "blocking_warning": "true" if blocking_warning else "false",
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


def add_boundary_warnings(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> None:
    for code, message in (
        ("order_send_not_called", "This readiness plan did not call order-send paths."),
        ("order_check_not_called_by_this_module", "This readiness plan did not call order-check paths."),
        ("readiness_plan_does_not_authorize_order_send", "This readiness plan does not authorize order-send now."),
        ("readiness_plan_does_not_authorize_execution", "This readiness plan does not authorize order execution."),
        ("final_rechecks_required_before_future_order_send", "All pre-send rechecks must be rerun by a separate future send module."),
    ):
        add_warning(
            warnings,
            args=args,
            warning_code=code,
            message=message,
            source="fixed_candidate_demo_order_send_pilot_readiness_plan",
            blocking_warning=False,
            severity="info",
        )


def load_inputs(args: argparse.Namespace) -> dict[str, Any]:
    paths = source_paths(args)
    inputs: dict[str, Any] = {"paths": paths}
    for key in (
        "order_check_manifest",
        "order_check_result",
        "readiness_manifest",
        "request_manifest",
        "approval_record",
        "schema_manifest",
        "reconciliation",
        "margin",
        "margin_snapshot",
        "freshness",
        "duplicate",
        "manual_plan",
        "future_request",
        "registry",
        "policy",
    ):
        data, error = read_json(paths[key])
        inputs[key] = data
        inputs[f"{key}_error"] = error
    for key in ("order_check_status", "order_check_gates", "order_check_bound_intent", "order_check_preview"):
        rows, error = read_csv_rows(paths[key])
        inputs[key] = rows
        inputs[f"{key}_error"] = error
    inputs["future_state_exists"] = paths["future_state"].exists()
    if paths["future_state"].exists():
        future_state, error = read_json(paths["future_state"])
        inputs["future_state"] = future_state
        inputs["future_state_error"] = error
    else:
        inputs["future_state"] = {}
        inputs["future_state_error"] = "missing"
    return inputs


def validate_canonical_registry(registry: dict[str, Any]) -> bool:
    return (
        registry.get("candidate_id") == CANDIDATE_ID
        and registry.get("symbol") == SYMBOL
        and registry.get("timeframe") == TIMEFRAME
        and registry.get("direction") == DIRECTION
        and safe_float(registry.get("max_spread_points")) == MAX_SPREAD_POINTS
        and safe_int(registry.get("max_open_positions")) in (None, MAX_OPEN_POSITIONS)
        and safe_int(registry.get("horizon_bars")) in (None, HORIZON_BARS)
    )


def validate_demo_policy(policy: dict[str, Any]) -> bool:
    boundaries = policy.get("safety_boundaries", {})
    if not isinstance(boundaries, dict):
        boundaries = {}
    return (
        policy.get("candidate_id") in (None, CANDIDATE_ID)
        and policy.get("symbol") in (None, SYMBOL)
        and policy.get("timeframe") in (None, TIMEFRAME)
        and policy.get("direction") in (None, DIRECTION)
        and policy.get("spread_unit") == "broker_points"
        and safe_float(policy.get("max_spread_points")) == MAX_SPREAD_POINTS
        and safe_int(policy.get("max_open_positions")) == MAX_OPEN_POSITIONS
        and boundaries.get("real_money_allowed") is False
        and boundaries.get("order_execution_allowed") is False
        and boundaries.get("order_request_construction_allowed") is False
        and boundaries.get("order_check_allowed") is False
        and boundaries.get("order_calc_allowed") is False
        and boundaries.get("manual_approval_required_before_any_future_demo_order") is True
    )


def validate_order_check_passed(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("order_check_status") == "order_check_available_passed_no_send"
        and manifest.get("order_check_called") is True
        and safe_int(manifest.get("order_check_call_count")) == 1
        and manifest.get("order_check_passed") is True
        and safe_int(manifest.get("order_check_retcode")) == 0
        and manifest.get("order_send_called") is False
        and safe_int(manifest.get("order_send_call_count")) in (None, 0)
        and manifest.get("order_execution_performed") is False
        and manifest.get("broker_payload_written") is False
        and manifest.get("executable_order_object_written") is False
        and manifest.get("future_state_json_written") is False
    )


def request_demo_module_validation_manifest(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("request_construction_status") == REQUEST_CONSTRUCTION_STALE_OVERRIDE_STATUS
        and manifest.get("module_validation_demo_execution") is True
        and manifest.get("stale_override_used") is True
        and manifest.get("strategy_valid") is False
        and manifest.get("production_valid") is False
        and manifest.get("order_check_allowed_for_demo_module_validation_only") is True
        and manifest.get("order_send_allowed_for_demo_module_validation_only") is False
    )


def stale_override_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return (
        args.module_validation_demo_execution is True
        and args.allow_stale_upstream_artifacts_for_demo_module_validation is True
        and args.module_validation_acknowledgment == MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT
        and request_demo_module_validation_manifest(inputs["request_manifest"])
    )


def expired_signal_override_requested(args: argparse.Namespace) -> bool:
    return bool(args.allow_expired_signal_for_demo_module_validation or args.expired_signal_override_acknowledgment)


def expired_signal_override_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return (
        stale_override_allowed(args, inputs)
        and args.allow_expired_signal_for_demo_module_validation is True
        and args.expired_signal_override_acknowledgment == EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT
    )


def demo_module_validation_send_readiness_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return stale_override_allowed(args, inputs)


def validate_request_construction(manifest: dict[str, Any], args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return (
        (
            manifest.get("request_construction_status") == REQUEST_CONSTRUCTION_AVAILABLE_STATUS
            and manifest.get("request_intent_created") is True
        )
        or demo_module_validation_send_readiness_allowed(args, inputs)
    ) and (
        manifest.get("broker_payload_constructed") is False
        and manifest.get("executable_order_object_constructed") is False
        and manifest.get("order_send_called") is False
        and manifest.get("order_execution_performed") is False
    )


def validate_readiness(manifest: dict[str, Any], args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    normal = (
        manifest.get("order_check_readiness_status") == "order_check_readiness_plan_available_no_order_check"
        and manifest.get("future_order_check_ready") is True
    )
    if normal:
        return True
    return (
        demo_module_validation_send_readiness_allowed(args, inputs)
        and validate_order_check_passed(inputs["order_check_manifest"])
        and manifest.get("order_check_readiness_status") == "order_check_readiness_plan_fixture_only_no_request_intent"
    )


def validate_schema(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("schema_status") == "manual_approval_record_schema_available_no_order"
        and manifest.get("schema_patch_status") == "schema_audit_gaps_closed_no_order"
    )


def validate_approval(record: dict[str, Any], args: argparse.Namespace, inputs: dict[str, Any]) -> tuple[bool, str]:
    if not record:
        return False, "order_send_pilot_readiness_plan_blocked_expired_approval"
    if record.get("approval_status") != "approved_for_future_request_construction_only":
        return False, "order_send_pilot_readiness_plan_blocked_expired_approval"
    checks = (
        record.get("approval_scope") == "future_request_construction_only",
        record.get("approval_does_not_execute_order") is True,
        record.get("approval_does_not_construct_request") is True,
        record.get("approval_requires_final_pre_request_recheck") is True,
        record.get("approval_revoked") is False,
        bool(record.get("record_hash_or_digest")),
        bool(record.get("signal_id")),
        bool(record.get("idempotency_key")),
    )
    if not all(checks):
        return False, "order_send_pilot_readiness_plan_blocked_expired_approval"
    expiry = parse_time(record.get("approval_expiry_time_utc"))
    if expiry is None or expiry <= utc_now():
        if not expired_signal_override_allowed(args, inputs):
            return False, "order_send_pilot_readiness_plan_blocked_expired_approval"
    return True, ""


def validate_freshness(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("freshness_status")
        in {"live_signal_freshness_fresh_current_or_latest_signal", "live_signal_freshness_fresh_within_horizon"}
        and manifest.get("is_fresh") is True
        and manifest.get("is_stale") is False
        and (safe_int(manifest.get("bars_elapsed")) is not None and safe_int(manifest.get("bars_elapsed")) <= HORIZON_BARS)
    )


def validate_reconciliation(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("reconciliation_status") == "broker_local_reconciliation_clean_no_local_no_broker"
        and safe_int(manifest.get("broker_position_count_symbol")) == 0
        and safe_int(manifest.get("broker_pending_order_count_symbol")) == 0
    )


def validate_margin(manifest: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    manifest_status = manifest.get("validation_status")
    snapshot_status = snapshot.get("validation_status")
    ratio = safe_float(manifest.get("broker_margin_usage_ratio"))
    if ratio is None:
        ratio = safe_float(snapshot.get("broker_margin_usage_ratio"))
    manifest_volume = safe_float(manifest.get("stepped_volume_lots"))
    snapshot_volume = safe_float(snapshot.get("margin_calc_volume_lots"))
    volume_coherent = True
    if manifest_volume is not None and manifest_volume <= 0:
        volume_coherent = False
    if snapshot_volume is not None and snapshot_volume <= 0:
        volume_coherent = False
    if manifest_volume is not None and snapshot_volume is not None:
        volume_coherent = volume_coherent and abs(manifest_volume - snapshot_volume) <= VOLUME_TOLERANCE
    return (
        manifest_status in ACCEPTABLE_MARGIN_VALIDATION_STATUSES
        and (snapshot_status in ("", None) or snapshot_status in ACCEPTABLE_MARGIN_VALIDATION_STATUSES)
        and manifest.get("source_nature") == "live_data_shadow_signal"
        and manifest.get("account_mode_label") == "demo"
        and manifest.get("account_currency") == ACCOUNT_CURRENCY
        and manifest.get("account_equity_policy_status") == "within_10pct"
        and ratio is not None
        and ratio <= HARD_MARGIN_CAP_RATIO
        and manifest.get("spread_within_policy") is True
        and volume_coherent
    )


def validate_duplicate(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("plan_status") == "duplicate_protection_plan_available_no_order"
        and safe_int(manifest.get("max_open_positions")) == MAX_OPEN_POSITIONS
        and manifest.get("plan_actionable") is False
    )


def validate_manual_plan(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("plan_status") == "manual_approval_kill_switch_plan_available_no_order"
        and manifest.get("kill_switch_executed") is False
        and manifest.get("plan_actionable") is False
    )


def validate_future_request(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("plan_status") == "future_request_construction_readiness_plan_available_no_order"
        and manifest.get("request_construction_allowed_now") is False
        and manifest.get("broker_request_constructed") is False
        and manifest.get("broker_payload_constructed") is False
        and manifest.get("order_object_constructed") is False
    )


def first_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[0] if rows else {}


def client_reject_flat_contract(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    intent = first_row(inputs.get("order_check_bound_intent", []))
    return state_contracts.evaluate_explicit_second_demo_send_after_client_reject_flat(
        state=inputs.get("future_state") or {},
        signal_id=intent.get("signal_id", ""),
        idempotency_key=intent.get("idempotency_key", ""),
        module_validation_demo_execution=bool(args.module_validation_demo_execution),
        demo_account_only=True,
        allow_flag=bool(args.allow_new_demo_send_after_client_reject_flat),
        acknowledgment=args.client_reject_resend_acknowledgment,
        broker_local_reconciliation=inputs.get("reconciliation") or {},
        require_broker_local_reconciliation=True,
    )


def future_state_incompatible(args: argparse.Namespace, inputs: dict[str, Any]) -> tuple[bool, bool, dict[str, Any]]:
    state = inputs.get("future_state") or {}
    if not state:
        return False, False, {}
    contract = client_reject_flat_contract(args, inputs)
    if contract["accepted"]:
        return False, False, contract
    intent = first_row(inputs.get("order_check_bound_intent", []))
    incompatible, same_key = state_contracts.future_state_is_incompatible_without_explicit_client_reject_contract(
        state,
        signal_id=intent.get("signal_id", ""),
        idempotency_key=intent.get("idempotency_key", ""),
    )
    return incompatible, same_key, contract


def future_state_warning_code(inputs: dict[str, Any], same_key: bool, contract: dict[str, Any]) -> str:
    if bool(contract.get("candidate")) and same_key:
        return "order_send_pilot_readiness_plan_blocked_client_reject_resend_acknowledgment"
    if same_key:
        return "order_send_pilot_readiness_plan_blocked_existing_active_idempotency_key"
    return "order_send_pilot_readiness_plan_blocked_future_state_incompatible"


def order_check_status(inputs: dict[str, Any]) -> str:
    return str(inputs["order_check_manifest"].get("order_check_status", ""))


def gate_row(
    args: argparse.Namespace,
    name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    path: Path | str,
    warning_code: str,
    blocking: bool = True,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "gate_name": name,
        "gate_status": "passed" if passed else "failed",
        "observed_value": observed,
        "expected_value": expected,
        "source_path": str(path),
        "blocking_if_failed": blocking,
        "warning_code": warning_code,
    }


def evaluate(args: argparse.Namespace, inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    paths = inputs["paths"]
    status = order_check_status(inputs)
    fixture = status in {"order_check_blocked_fixture_only_no_request_intent", "order_check_blocked_fixture_only_no_order_check_readiness"}
    dry_run_no_broker = status == "order_check_dry_run_no_broker_call"
    failed_check = status == "order_check_available_failed_no_send"
    passed_check = status == "order_check_available_passed_no_send"
    approval_ok, approval_status = validate_approval(inputs["approval_record"], args, inputs)
    future_state_bad, future_state_same_key, client_reject_contract = future_state_incompatible(args, inputs)
    gates = [
        gate_row(args, "canonical_candidate", validate_canonical_registry(inputs["registry"]), inputs["registry"].get("candidate_id"), CANDIDATE_ID, paths["registry"], "order_send_pilot_readiness_plan_blocked_noncanonical_candidate"),
        gate_row(args, "demo_execution_policy", validate_demo_policy(inputs["policy"]), inputs["policy"].get("policy_id", ""), "safe base policy with send/check/construct/calc disabled", paths["policy"], "order_send_pilot_readiness_plan_blocked_noncanonical_demo_execution_policy"),
        gate_row(args, "order_check_artifact_present", bool(inputs["order_check_manifest"]), status or inputs["order_check_manifest_error"], "order-check manifest present", paths["order_check_manifest"], "order_send_pilot_readiness_plan_blocked_no_real_order_check_pass"),
    ]
    if passed_check:
        gates.extend(
            [
                gate_row(args, "order_check_passed_no_send", validate_order_check_passed(inputs["order_check_manifest"]), status, "passed no-send order-check", paths["order_check_manifest"], "order_send_pilot_readiness_plan_blocked_order_check_failed"),
                gate_row(args, "request_construction_non_executable", validate_request_construction(inputs["request_manifest"], args, inputs), inputs["request_manifest"].get("request_construction_status"), "non-executable request construction or explicit demo module validation request", paths["request_manifest"], "order_send_pilot_readiness_plan_blocked_no_real_order_check_pass"),
                gate_row(args, "order_check_readiness_available", validate_readiness(inputs["readiness_manifest"], args, inputs), inputs["readiness_manifest"].get("order_check_readiness_status"), "order-check readiness available or passed order_check demo module validation", paths["readiness_manifest"], "order_send_pilot_readiness_plan_blocked_no_real_order_check_pass"),
                gate_row(args, "manual_approval_schema", validate_schema(inputs["schema_manifest"]), inputs["schema_manifest"].get("schema_status"), "manual approval schema available", paths["schema_manifest"], "order_send_pilot_readiness_plan_blocked_expired_approval"),
                gate_row(args, "manual_approval_record", approval_ok, inputs["approval_record"].get("approval_status", inputs["approval_record_error"]), "approved non-revoked non-expired approval", paths["approval_record"], approval_status or "order_send_pilot_readiness_plan_blocked_expired_approval"),
                gate_row(args, "live_signal_freshness", validate_freshness(inputs["freshness"]), inputs["freshness"].get("freshness_status"), "fresh signal within h10", paths["freshness"], "order_send_pilot_readiness_plan_blocked_stale_signal"),
                gate_row(args, "broker_local_reconciliation", validate_reconciliation(inputs["reconciliation"]), inputs["reconciliation"].get("reconciliation_status"), "clean no local/no broker", paths["reconciliation"], "order_send_pilot_readiness_plan_blocked_broker_local_reconciliation"),
                gate_row(args, "broker_safe_margin", validate_margin(inputs["margin"], inputs["margin_snapshot"]), inputs["margin"].get("broker_margin_usage_ratio"), "demo margin <= 0.70 and spread within policy", paths["margin"], "order_send_pilot_readiness_plan_blocked_margin_policy"),
                gate_row(args, "duplicate_protection", validate_duplicate(inputs["duplicate"]), inputs["duplicate"].get("plan_status"), "duplicate protection available", paths["duplicate"], "order_send_pilot_readiness_plan_blocked_duplicate_protection"),
                gate_row(args, "manual_approval_kill_switch", validate_manual_plan(inputs["manual_plan"]), inputs["manual_plan"].get("plan_status"), "kill-switch inactive", paths["manual_plan"], "order_send_pilot_readiness_plan_blocked_kill_switch"),
                gate_row(args, "future_request_readiness", validate_future_request(inputs["future_request"]), inputs["future_request"].get("plan_status"), "future request readiness no-order", paths["future_request"], "order_send_pilot_readiness_plan_blocked_no_real_order_check_pass"),
                gate_row(
                    args,
                    "future_state_compatible",
                    not future_state_bad,
                    state_contracts.state_status(inputs["future_state"])
                    or ("exists" if inputs["future_state_exists"] else "missing"),
                    "missing, terminal-safe state, or explicit demo client-reject-flat resend",
                    paths["future_state"],
                    future_state_warning_code(inputs, future_state_same_key, client_reject_contract),
                ),
            ]
        )
        if request_demo_module_validation_manifest(inputs["request_manifest"]):
            gates.append(
                gate_row(
                    args,
                    "demo_module_validation_stale_override_acknowledgment",
                    stale_override_allowed(args, inputs),
                    f"module_validation_demo_execution={args.module_validation_demo_execution};allow_stale={args.allow_stale_upstream_artifacts_for_demo_module_validation};ack={args.module_validation_acknowledgment or ''}",
                    f"ack={MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT}",
                    paths["request_manifest"],
                    "order_send_pilot_readiness_plan_blocked_demo_module_validation_acknowledgment",
                )
            )
        if expired_signal_override_requested(args):
            gates.append(
                gate_row(
                    args,
                    "demo_module_validation_expired_signal_override_acknowledgment",
                    expired_signal_override_allowed(args, inputs),
                    f"allow_expired={args.allow_expired_signal_for_demo_module_validation};ack={args.expired_signal_override_acknowledgment or ''}",
                    f"ack={EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT}",
                    paths["approval_record"],
                    "order_send_pilot_readiness_plan_blocked_expired_signal_override_acknowledgment",
                )
            )
    for row in gates:
        if row["gate_status"] == "failed" and row["blocking_if_failed"] is True:
            add_warning(
                warnings,
                args=args,
                warning_code=str(row["warning_code"]),
                message=f"Gate failed: {row['gate_name']}",
                source=str(row["source_path"]),
                blocking_warning=True,
            )
    inputs["client_reject_flat_contract"] = client_reject_contract
    failures = [row for row in gates if row["gate_status"] == "failed" and row["blocking_if_failed"] is True]
    if failures:
        return str(failures[0]["warning_code"]), gates
    if fixture:
        return "order_send_pilot_readiness_plan_fixture_only_no_order_check_pass", gates
    if dry_run_no_broker:
        return "order_send_pilot_readiness_plan_blocked_no_real_order_check_pass", gates
    if failed_check:
        return "order_send_pilot_readiness_plan_blocked_order_check_failed", gates
    if passed_check:
        return "order_send_pilot_readiness_plan_available_no_send", gates
    return "order_send_pilot_readiness_plan_blocked_no_real_order_check_pass", gates


def first_order_check_status_row(inputs: dict[str, Any]) -> dict[str, str]:
    return inputs["order_check_status"][0] if inputs["order_check_status"] else {}


def first_bound_intent(inputs: dict[str, Any]) -> dict[str, str]:
    return inputs["order_check_bound_intent"][0] if inputs["order_check_bound_intent"] else {}


def send_input_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    bound = first_bound_intent(inputs)
    status_row = first_order_check_status_row(inputs)
    values = {
        "action_intent": "future_deal",
        "symbol": SYMBOL,
        "volume": "",
        "type_intent": SIDE_INTENT,
        "price_reference": "",
        "sl": "",
        "tp": "",
        "deviation_policy": "future_send_policy_required",
        "magic_policy": "future_send_policy_required",
        "comment_policy": "future_send_policy_required",
        "type_time_policy": "future_send_policy_required",
        "type_filling_policy": "future_send_policy_required",
        "signal_id": bound.get("signal_id", ""),
        "idempotency_key": bound.get("idempotency_key", ""),
        "approval_record_id": bound.get("approval_record_id", ""),
        "order_check_run_id": status_row.get("run_id", inputs["order_check_manifest"].get("run_id", "")),
    }
    return [
        {
            "run_id": args.run_id,
            "field_name": name,
            "intended_value": value,
            "source": "bound_order_check_or_future_recheck",
            "required_for_future_order_send": True,
            "must_be_rechecked_before_order_send": True,
            "broker_payload_field_now": False,
            "executable_now": False,
            "safety_note": "descriptor_only_not_a_broker_payload_and_not_callable_now",
        }
        for name, value in values.items()
    ]


def broker_send_field_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = [
        ("action", "future mapping to trade action deal", "future send module policy"),
        ("symbol", "GBPUSD", "fixed candidate plus future symbol recheck"),
        ("volume", "stepped volume from approved intent and order-check result", "future send recheck"),
        ("type", "future mapping to sell order type", "fixed candidate direction"),
        ("price", "future broker tick/send policy read at send time", "future broker read in separate module"),
        ("sl", "stop-loss from bound intent", "bound intent plus stop-level recheck"),
        ("tp", "take-profit from bound intent", "bound intent plus stop-level recheck"),
        ("deviation", "future deviation policy", "future send module policy"),
        ("magic", "future magic policy", "future send module policy"),
        ("comment", "future audit-safe comment policy", "future send module policy"),
        ("type_time", "future time-in-force policy", "future send module policy"),
        ("type_filling", "future filling policy after symbol constraints recheck", "future send module policy"),
    ]
    return [
        {
            "run_id": args.run_id,
            "future_mt5_field": name,
            "mapping_description": description,
            "source_or_future_source": source,
            "available_now": name in {"symbol", "type", "sl", "tp"},
            "requires_broker_read_at_send_time": name in {"price", "type_filling"},
            "executable_now": False,
            "safety_note": "future_mapping_only_no_executable_object_now",
        }
        for name, description, source in specs
    ]


def pre_send_recheck_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = [
        ("recheck_signal_freshness", "freshness_status fresh and bars_elapsed <= 10"),
        ("recheck_approval_record_not_expired", "approval expiry time has not passed"),
        ("recheck_approval_record_not_revoked", "approval_revoked is false"),
        ("recheck_broker_local_reconciliation_clean", "broker/local reconciliation clean"),
        ("recheck_broker_positions_zero", "broker_position_count_symbol == 0"),
        ("recheck_broker_pending_orders_zero", "broker_pending_order_count_symbol == 0"),
        ("recheck_margin_usage_below_hard_cap", "broker_margin_usage_ratio <= 0.70"),
        ("recheck_spread_within_policy", "spread <= 15.0 broker_points"),
        ("recheck_duplicate_protection_clean", "idempotency and duplicate gates clean"),
        ("recheck_kill_switch_inactive", "kill-switch inactive"),
        ("recheck_future_state_compatible", "future state absent or compatible"),
        ("recheck_order_check_passed_and_recent", "order-check passed and is recent enough"),
        ("recheck_order_check_request_matches_send_intent", "send intent matches checked intent"),
        ("recheck_no_existing_active_request_for_idempotency_key", "no active intent for idempotency key"),
        ("recheck_no_scheduler_loop_background", "single-shot only, no scheduler/loop/background task"),
    ]
    return [
        {
            "run_id": args.run_id,
            "recheck_name": name,
            "timing": "immediately_before_future_order_send",
            "required": True,
            "blocking_if_failed": True,
            "expected_value": expected,
            "safety_note": "future_send_module_must_rerun_this_check_before_any_send_attempt",
        }
        for name, expected in specs
    ]


def state_transition_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = [
        ("no_local_state", "No local active state exists", "future_send_module", "approval_record_created", False),
        ("approval_record_created", "Manual approval record exists", "future_approval_module", "request_intent_ready", True),
        ("request_intent_ready", "Non-executable request intent is ready", "future_request_module", "order_check_passed", True),
        ("order_check_passed", "Real order-check passed no-send", "future_order_check_module", "pre_send_recheck_passed", True),
        ("pre_send_recheck_passed", "Immediate pre-send rechecks passed", "future_send_module", "pre_send_pending", True),
        ("pre_send_pending", "Durable idempotency claim exists before the single future send attempt", "future_send_module", "send_in_progress;reconciliation_hold", True),
        ("send_in_progress", "Future send call started", "future_send_module", "send_result_received;reconciliation_hold", True),
        ("send_result_received", "Future send result captured", "future_send_module", "broker_position_detected;broker_pending_order_detected;execution_rejected", True),
        ("broker_position_detected", "Broker position detected after future send", "future_reconciliation_module", "closed_future_only", True),
        ("broker_pending_order_detected", "Broker pending order detected after future send", "future_reconciliation_module", "reconciliation_hold", True),
        ("execution_rejected", "Future send rejected", "future_send_module", "no_local_state;reconciliation_hold", False),
        ("reconciliation_hold", "Manual reconciliation required", "future_reconciliation_module", "closed_future_only", True),
        ("duplicate_blocked", "Duplicate/idempotency block", "future_duplicate_module", "reconciliation_hold", True),
        ("closed_future_only", "Future lifecycle closed", "future_tracker_module", "no_local_state", False),
    ]
    return [
        {
            "run_id": args.run_id,
            "state_name": name,
            "meaning": meaning,
            "entered_by_future_module": entered_by,
            "allowed_next_states": next_states,
            "blocking_for_new_order": blocking,
            "safety_note": "future_state_plan_only_no_state_written",
        }
        for name, meaning, entered_by, next_states, blocking in specs
    ]


def retcode_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = [
        ("success_deal", "TRADE_RETCODE_DONE", "record result then reconcile broker position", "broker_position_detected", False, False),
        ("success_placed", "TRADE_RETCODE_PLACED", "record result then reconcile pending/position state", "broker_pending_order_detected", False, False),
        ("partial_fill", "TRADE_RETCODE_DONE_PARTIAL", "record partial result and route to reconciliation hold", "reconciliation_hold", False, True),
        ("reject", "TRADE_RETCODE_REJECT", "record rejection and stop", "execution_rejected", False, True),
        ("requote", "TRADE_RETCODE_REQUOTE", "stop and require manual review", "execution_rejected", False, True),
        ("price_changed", "TRADE_RETCODE_PRICE_CHANGED", "stop and require fresh signal/recheck", "execution_rejected", False, True),
        ("price_off", "TRADE_RETCODE_PRICE_OFF", "stop and require market/freshness review", "execution_rejected", False, True),
        ("invalid_stops", "TRADE_RETCODE_INVALID_STOPS", "stop and inspect stops policy", "execution_rejected", False, True),
        ("invalid_volume", "TRADE_RETCODE_INVALID_VOLUME", "stop and inspect volume policy", "execution_rejected", False, True),
        ("invalid_filling", "TRADE_RETCODE_INVALID_FILL", "stop and inspect filling policy", "execution_rejected", False, True),
        ("market_closed", "TRADE_RETCODE_MARKET_CLOSED", "stop and wait for eligible session", "execution_rejected", False, True),
        ("no_money", "TRADE_RETCODE_NO_MONEY", "stop and inspect margin policy", "execution_rejected", False, True),
        ("trade_disabled", "TRADE_RETCODE_TRADE_DISABLED", "stop and inspect demo environment", "execution_rejected", False, True),
        ("too_many_requests", "TRADE_RETCODE_TOO_MANY_REQUESTS", "stop with no retry and require manual review", "reconciliation_hold", False, True),
        ("connection_lost", "future_symbolic_lookup_required", "treat transport uncertainty as reconciliation hold", "reconciliation_hold", False, True),
        ("result_none", "future_symbolic_lookup_required", "treat missing result as reconciliation hold", "reconciliation_hold", False, True),
        ("exception", "future_symbolic_lookup_required", "capture redacted exception and route to reconciliation hold", "reconciliation_hold", False, True),
        ("timeout", "future_symbolic_lookup_required", "treat timeout as unknown outcome and route to reconciliation hold", "reconciliation_hold", False, True),
        ("unknown_retcode", "future_symbolic_lookup_required", "route unknown result to manual reconciliation hold", "reconciliation_hold", False, True),
    ]
    return [
        {
            "run_id": args.run_id,
            "retcode_category": category,
            "symbolic_retcode": symbolic_retcode,
            "numeric_retcode_policy": "use_stable_documented_numeric_value_or_future_symbolic_lookup",
            "future_expected_action": action,
            "state_transition": transition,
            "retry_allowed": retry,
            "retry_allowed_default": False,
            "manual_review_required": manual,
            "broker_local_reconciliation_required": True,
            "duplicate_rerun_behavior": "block_second_send_until_reconciliation_is_resolved",
            "safety_note": "future_handling_plan_only_no_send_performed_and_no_automatic_retry",
        }
        for category, symbolic_retcode, action, transition, retry, manual in specs
    ]


def post_send_reconciliation_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = [
        ("read_broker_positions_once", "read GBPUSD positions once after the send result", "positions_get symbol=GBPUSD", 1),
        ("read_broker_orders_once", "read GBPUSD pending orders once after the send result", "orders_get symbol=GBPUSD", 1),
        ("confirm_ticket_order_deal_linkage", "confirm ticket/order/deal linkage if returned", "none", 0),
        ("confirm_volume_side_symbol_match", "confirm broker volume/side/symbol match intent", "none", 0),
        ("confirm_sl_tp_match", "confirm SL/TP match or route to reconciliation_hold", "none", 0),
        ("confirm_max_open_positions_one", "confirm symbol-level GBPUSD max_open_positions remains 1", "none", 0),
        ("pending_result_handling", "pending result remains blocking and prevents a second send", "none", 0),
        ("claimed_success_but_no_position", "route to reconciliation_hold", "none", 0),
        ("broker_position_without_local_state", "route to reconciliation_hold", "none", 0),
        ("history_reads_forbidden", "history reads remain forbidden in the pilot send module", "none", 0),
        ("no_second_send_while_unresolved", "block any second send while pending or reconciliation_hold", "none", 0),
    ]
    return [
        {
            "run_id": args.run_id,
            "requirement_name": name,
            "expected_future_behavior": behavior,
            "allowed_read": allowed_read,
            "max_call_count": max_call_count,
            "history_reads_allowed": False,
            "polling_allowed": False,
            "scheduler_allowed": False,
            "scope": "GBPUSD_symbol_level_pilot",
            "blocking_if_failed": True,
            "safety_note": "post_send_plan_only_no_broker_read_performed",
        }
        for name, behavior, allowed_read, max_call_count in specs
    ]


def crash_recovery_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = [
        ("crash_before_state_pre_write", "restart with no local state and rerun all gates", "no_local_state", False),
        ("crash_after_state_pre_write_before_order_send", "route to reconciliation_hold before retry", "reconciliation_hold", True),
        ("crash_during_order_send_before_response_captured", "route to reconciliation_hold and inspect broker state", "reconciliation_hold", True),
        ("crash_after_order_send_success_before_local_state_update", "route to reconciliation_hold and bind broker position", "reconciliation_hold", True),
        ("crash_after_order_send_reject_before_local_state_update", "route to reconciliation_hold or execution_rejected after evidence", "reconciliation_hold", True),
        ("duplicate_rerun_after_crash", "block by idempotency until reconciliation", "duplicate_blocked", True),
        ("stale_approval_after_crash", "block and require new approval", "execution_rejected", True),
        ("local_broker_mismatch_after_restart", "route to reconciliation_hold", "reconciliation_hold", True),
    ]
    return [
        {
            "run_id": args.run_id,
            "crash_case": case,
            "future_recovery_action": action,
            "state_transition": transition,
            "manual_review_required": manual,
            "safety_note": "crash_recovery_plan_only_no_background_task_added",
        }
        for case, action, transition, manual in specs
    ]


def future_send_cli_contract_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    future_script = "scripts/send_fixed_candidate_demo_order_pilot.py"
    specs = [
        ("--run-id", True, "", "unique single-shot pilot run id", "missing run id blocks"),
        ("--order-send-pilot-readiness-plan-dir", True, "", "bind this audited readiness plan", "missing or non-available plan blocks"),
        ("--order-check-dir", True, "", "bind the passed order-check artifact", "missing, failed, fixture-only, or stale order-check blocks"),
        ("--request-construction-dry-run-dir", True, "", "bind the non-executable request intent", "missing or mismatched intent blocks"),
        ("--manual-approval-record-json", True, "", "bind one valid operator approval record", "missing, revoked, expired, or mismatched approval blocks"),
        ("--broker-local-reconciliation-dir", True, "", "bind clean broker/local reconciliation", "dirty reconciliation blocks"),
        ("--broker-safe-margin-validation-dir", True, "", "bind current margin safety evidence", "margin policy failure blocks"),
        ("--live-signal-freshness-dir", True, "", "bind fresh signal evidence", "stale signal blocks"),
        ("--duplicate-protection-plan-dir", True, "", "bind duplicate and idempotency policy", "duplicate or incompatible state blocks"),
        ("--manual-approval-kill-switch-plan-dir", True, "", "bind kill-switch policy", "active kill-switch blocks"),
        ("--canonical-registry", True, "", "bind canonical candidate", "candidate mismatch blocks"),
        ("--demo-execution-policy", True, "", "bind demo execution policy", "unsafe or noncanonical policy blocks"),
        ("--future-state-json", True, "", "durable pilot state path", "missing durable pre-send state claim blocks real send"),
        ("--output-dir", True, "", "write audit artifacts for the single-shot run", "output collision without overwrite blocks"),
        ("--dry-run", False, "true", "default no-send mode", "dry-run path never reaches real send"),
        ("--allow-real-order-send", False, "false", "explicit real demo send gate", "false blocks any real send"),
        ("--operator-final-send-confirmation", False, "", "one-shot final confirmation token", "missing or invalid confirmation blocks first real pilot"),
        ("--mt5-package", False, "dependency_injected_mock_for_tests", "dependency injection for mocked tests only", "fixture or test path never reaches real send"),
        ("--overwrite", False, "false", "explicit artifact replacement", "existing output blocks unless explicitly enabled"),
    ]
    return [
        {
            "run_id": args.run_id,
            "future_script": future_script,
            "cli_flag": flag,
            "required": required,
            "default_value": default_value,
            "purpose": purpose,
            "blocking_rule": blocking_rule,
            "safety_note": "future_contract_only_no_send_module_implemented_here",
        }
        for flag, required, default_value, purpose, blocking_rule in specs
    ]


def final_operator_confirmation_contract_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    binding_fields = [
        "signal_id",
        "idempotency_key",
        "approval_record_id",
        "approval_record_digest",
        "request_intent_digest",
        "order_check_run_id",
        "order_check_digest",
        "operator_identity_ref",
        "operator_timestamp_utc",
        "confirmation_expiry_time_utc",
    ]
    rows = [
        {
            "run_id": args.run_id,
            "contract_item": field,
            "item_type": "required_binding_field",
            "required": True,
            "allowed_value": "must_match_current_bound_artifacts_or_current_operator_context",
            "allowed": True,
            "binding_scope": "single_signal_single_idempotency_key_single_order_check",
            "blocking_if_failed": True,
            "safety_note": "one_shot_final_confirmation_required_before_first_real_pilot",
        }
        for field in binding_fields
    ]
    rows.append(
        {
            "run_id": args.run_id,
            "contract_item": "confirmation_label",
            "item_type": "allowed_confirmation_label",
            "required": True,
            "allowed_value": "confirm_single_demo_send_only",
            "allowed": True,
            "binding_scope": "single_signal_single_idempotency_key_single_order_check",
            "blocking_if_failed": True,
            "safety_note": "does_not_authorize_any_additional_send",
        }
    )
    for meaning in (
        "approve_live_trading",
        "approve_multiple_sends",
        "bypass_checks",
        "ignore_stale_signal",
        "ignore_reconciliation",
        "ignore_margin_policy",
        "ignore_duplicate_protection",
        "ignore_kill_switch",
    ):
        rows.append(
            {
                "run_id": args.run_id,
                "contract_item": meaning,
                "item_type": "forbidden_confirmation_meaning",
                "required": True,
                "allowed_value": "",
                "allowed": False,
                "binding_scope": "all_future_pilot_invocations",
                "blocking_if_failed": True,
                "safety_note": "forbidden_meaning_must_never_expand_confirmation_scope",
            }
        )
    return rows


def request_order_check_send_binding_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    digest_specs = [
        ("request_intent_digest", "request_construction_dry_run_request_intent", "request_intent_digest"),
        ("request_fields_digest", "request_construction_dry_run_request_fields", "request_fields_digest"),
        ("order_check_manifest_digest", "order_check_manifest", "order_check_manifest_digest"),
        ("order_check_result_snapshot_digest", "order_check_result_snapshot", "order_check_result_snapshot_digest"),
        ("approval_record_digest", "manual_approval_record", "approval_record_digest"),
        ("upstream_reconciliation_digest", "broker_local_reconciliation", "upstream_reconciliation_digest"),
        ("freshness_digest", "live_signal_freshness", "freshness_digest"),
        ("margin_validation_digest", "broker_safe_margin_validation", "margin_validation_digest"),
    ]
    rows = [
        {
            "run_id": args.run_id,
            "binding_name": name,
            "source_artifact": source,
            "digest_field": digest,
            "recompute_immediately_before_send": True,
            "required_match": True,
            "blocking_if_mismatch": True,
            "safety_note": "digest_mismatch_or_replaced_artifact_blocks_send",
        }
        for name, source, digest in digest_specs
    ]
    for field in ("volume", "sl", "tp", "symbol", "side", "signal_id", "idempotency_key"):
        rows.append(
            {
                "run_id": args.run_id,
                "binding_name": f"intent_order_check_send_field_match_{field}",
                "source_artifact": "request_intent_and_order_check_result",
                "digest_field": field,
                "recompute_immediately_before_send": True,
                "required_match": True,
                "blocking_if_mismatch": True,
                "safety_note": "blank_critical_field_or_field_mismatch_blocks_send",
            }
        )
    return rows


def atomic_state_contract_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    state_fields = (
        "state_version;candidate_id;symbol;timeframe;direction;signal_id;idempotency_key;"
        "approval_record_id;request_intent_digest;order_check_run_id;order_check_digest;"
        "send_attempt_id;state_status;pre_send_claimed_at_utc;send_started_at_utc;"
        "send_completed_at_utc;broker_order_ticket;broker_deal_ticket;broker_position_ticket;"
        "last_retcode;reconciliation_status;crash_recovery_required"
    )
    specs = [
        ("state_schema", state_fields, "before any future real send", "all required fields validated before durable write", "reconciliation_hold"),
        ("atomic_idempotency_claim", "signal_id;idempotency_key;send_attempt_id", "before any future real send", "compare-and-swap or exclusive lock required", "reconciliation_hold"),
        ("durable_pre_send_pending", state_fields, "must complete before the single send attempt", "atomic durable write with state_status=pre_send_pending", "reconciliation_hold"),
        ("atomic_write_strategy", "state_version;state_status;send_attempt_id", "every future state transition", "temporary file plus atomic replace or equivalent durable transaction", "reconciliation_hold"),
        ("crash_recovery_ownership", "send_attempt_id;crash_recovery_required;reconciliation_status", "before and after the single send attempt", "future pilot owns recovery until reconciliation resolves", "reconciliation_hold"),
        ("claim_or_write_failure_block", "idempotency_key;state_status", "before any future real send", "no send when claim or durable write fails", "reconciliation_hold"),
        ("second_send_block", "state_status;idempotency_key", "on every invocation", "pending open or reconciliation_hold state blocks second send", "reconciliation_hold"),
    ]
    return [
        {
            "run_id": args.run_id,
            "requirement_name": name,
            "required_fields": fields,
            "timing": timing,
            "atomicity_requirement": atomicity,
            "blocking_if_failed": True,
            "state_on_failure": failure_state,
            "safety_note": "contract_only_no_future_state_written_by_this_planner",
        }
        for name, fields, timing, atomicity, failure_state in specs
    ]


def post_send_state_update_contract_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = [
        (1, "persist_send_result_snapshot", "persist raw and redacted send result snapshot before interpreting outcome", "reconciliation_hold"),
        (2, "persist_returned_tickets", "persist broker ticket order deal and position identifiers when available", "reconciliation_hold"),
        (3, "atomic_state_update_by_retcode", "update local state atomically according to the retcode matrix", "reconciliation_hold"),
        (4, "bounded_broker_local_reconciliation", "perform the bounded symbol-level reconciliation contract", "reconciliation_hold"),
        (5, "state_write_failure_handling", "state write failure routes to reconciliation_hold", "reconciliation_hold"),
        (6, "unknown_response_handling", "unknown missing exception or timeout response routes to reconciliation_hold", "reconciliation_hold"),
        (7, "block_second_send_until_resolved", "never allow a second send while reconciliation remains unresolved", "reconciliation_hold"),
    ]
    return [
        {
            "run_id": args.run_id,
            "sequence_index": index,
            "requirement_name": name,
            "expected_future_behavior": behavior,
            "state_on_failure": state,
            "blocking_if_failed": True,
            "safety_note": "future_post_send_contract_only_no_state_written",
        }
        for index, name, behavior, state in specs
    ]


def future_send_test_contract_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = [
        ("dry_run_never_imports_mt5", "dry-run invocation", "no send and no broker dependency import", True, False, True),
        ("real_send_blocked_without_flag", "real path without explicit flag", "blocked before send", True, False, True),
        ("real_send_blocked_without_final_confirmation", "real path without final confirmation", "blocked before send", True, False, True),
        ("fixture_source_blocked", "fixture-only order-check source", "blocked before send", True, False, True),
        ("missing_passed_order_check_blocked", "missing or failed order-check", "blocked before send", True, False, True),
        ("stale_approval_or_signal_blocked", "expired approval or stale signal", "blocked before send", True, False, True),
        ("dirty_reconciliation_blocked", "dirty broker/local reconciliation", "blocked before send", True, False, True),
        ("duplicate_or_incompatible_state_blocked", "duplicate idempotency or incompatible state", "blocked before send", True, False, True),
        ("mocked_success_exactly_once", "mocked success response", "exactly one gated send then bounded reconciliation", True, True, False),
        ("mocked_reject_exactly_once", "mocked reject response", "exactly one gated send then rejected or reconciliation state", True, True, False),
        ("mocked_exception_routes_hold", "mocked exception", "reconciliation_hold and no retry", True, True, False),
        ("mocked_timeout_routes_hold", "mocked timeout", "reconciliation_hold and no retry", True, True, False),
        ("rerun_never_sends_twice", "rerun after pending open or hold state", "blocked second send", True, False, True),
        ("no_scheduler_loop_background", "source safety inspection", "no scheduler loop or background behavior", False, False, True),
        ("no_history_reads", "source safety inspection", "no broker history reads", False, False, True),
    ]
    return [
        {
            "run_id": args.run_id,
            "test_name": name,
            "scenario": scenario,
            "expected_result": expected,
            "mocked_mt5_required": mocked,
            "exactly_once_send_expected": exactly_once,
            "no_send_expected": no_send,
            "safety_note": "future_test_contract_only_no_mt5_or_send_used_here",
        }
        for name, scenario, expected, mocked, exactly_once, no_send in specs
    ]


def future_send_safety_grep_contract_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = [
        ("exactly_one_gated_send_signature", "exactly one gated order_send call signature is allowed", "1"),
        ("no_send_in_dry_run", "no order_send call signature is reachable from dry-run", "0"),
        ("no_send_without_state_and_confirmation", "no send without pre_send_pending claim final confirmation and passed order-check", "0"),
        ("no_second_or_retry_send", "no second send or automatic retry path", "0"),
        ("no_scheduler_loop_background", "no scheduler loop or background behavior", "0"),
        ("no_history_reads", "no broker history read call signatures", "0"),
        ("no_executable_payload_written", "no executable broker payload is written to artifacts", "0"),
        ("no_fixture_send", "no send from fixture-only inputs", "0"),
    ]
    return [
        {
            "run_id": args.run_id,
            "rule_name": name,
            "expectation": expectation,
            "allowed_occurrence_count": count,
            "applies_to": "future_send_fixed_candidate_demo_order_pilot_source_and_tests",
            "blocking_if_failed": True,
            "safety_note": "future_static_safety_contract_only",
        }
        for name, expectation, count in specs
    ]


def block_rows(args: argparse.Namespace, gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "block_condition": row["gate_name"],
            "condition_status": row["gate_status"],
            "observed_value": row["observed_value"],
            "expected_value": row["expected_value"],
            "blocking_if_failed": row["blocking_if_failed"],
            "caveat": "blocks future order-send readiness when failed",
        }
        for row in gates
    ]


def bound_order_check_row(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    path = inputs["paths"]["order_check_manifest"]
    return {
        "run_id": args.run_id,
        "order_check_dir": str(inputs["paths"]["order_check_dir"]),
        "order_check_manifest_path": str(path),
        "order_check_status": order_check_status(inputs),
        "order_check_passed": inputs["order_check_manifest"].get("order_check_passed"),
        "order_check_run_id": inputs["order_check_manifest"].get("run_id", ""),
        "binding_status": "read_only_bound" if path.exists() else "missing",
        "sha256_digest": sha256_file(path),
    }


def bound_upstream_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    specs = [
        ("order_check_manifest", "order_check_manifest", "order_check_status"),
        ("order_check_readiness", "readiness_manifest", "order_check_readiness_status"),
        ("request_construction", "request_manifest", "request_construction_status"),
        ("manual_approval_schema", "schema_manifest", "schema_status"),
        ("broker_local_reconciliation", "reconciliation", "reconciliation_status"),
        ("broker_safe_margin_validation", "margin", "validation_status"),
        ("broker_safe_margin_validation_margin_snapshot", "margin_snapshot", "validation_status"),
        ("live_signal_freshness", "freshness", "freshness_status"),
        ("duplicate_protection", "duplicate", "plan_status"),
        ("manual_approval_kill_switch", "manual_plan", "plan_status"),
        ("future_request_readiness", "future_request", "plan_status"),
        ("canonical_registry", "registry", "candidate_id"),
        ("demo_execution_policy", "policy", "policy_id"),
    ]
    rows = []
    for name, key, status_field in specs:
        path = inputs["paths"][key]
        source = inputs.get(key, {})
        rows.append(
            {
                "run_id": args.run_id,
                "upstream_name": name,
                "upstream_path": str(path),
                "upstream_status_field": status_field,
                "upstream_status_value": source.get(status_field, "") if isinstance(source, dict) else "",
                "sha256_digest": sha256_file(path),
                "binding_status": "read_only_bound" if path.exists() else "missing",
            }
        )
    return rows


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
        "no_broker_payload_constructed": True,
        "no_executable_order_object_constructed": True,
        "no_future_state_json_written": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
        "evidence_label": "order_send_pilot_readiness_plan_no_order_boundary",
        "caveat": "planning_only_no_order_send_no_order_check_no_broker_payload",
    }


def recommended_next_step(status: str) -> str:
    if status == "order_send_pilot_readiness_plan_available_no_send":
        return "implement_send_fixed_candidate_demo_order_pilot_gated_no_send_default"
    if status == "order_send_pilot_readiness_plan_fixture_only_no_order_check_pass":
        return "wait_for_fresh_signal_valid_approval_request_intent_and_passed_order_check"
    if status == "order_send_pilot_readiness_plan_blocked_no_real_order_check_pass":
        return "run_real_order_check_only_after_non_fixture_readiness"
    return "resolve_blocking_condition_before_future_order_send"


def write_report(
    path: Path,
    status: str,
    warnings: list[dict[str, Any]],
    args: argparse.Namespace | None = None,
    inputs: dict[str, Any] | None = None,
) -> None:
    module_lines: list[str] = []
    if args is not None and inputs is not None:
        approval_expiry = parse_time(inputs["approval_record"].get("approval_expiry_time_utc"))
        approval_is_expired = approval_expiry is None or approval_expiry <= utc_now()
        stale_override = bool(stale_override_allowed(args, inputs))
        expired_override = bool(expired_signal_override_allowed(args, inputs) and approval_is_expired)
        module_validation = bool(
            args.module_validation_demo_execution
            or inputs["request_manifest"].get("module_validation_demo_execution") is True
            or inputs["order_check_manifest"].get("module_validation_demo_execution") is True
        )
        strategy_valid = not bool(module_validation or stale_override or expired_override)
        send_readiness_demo_only = bool(
            status == "order_send_pilot_readiness_plan_available_no_send"
            and demo_module_validation_send_readiness_allowed(args, inputs)
        )
        client_reject_contract = inputs.get("client_reject_flat_contract") or {}
        explicit_client_reject_resend = bool(client_reject_contract.get("accepted"))
        module_lines = [
            "## Module Validation Contract",
            "",
            f"- module_validation_demo_execution: `{module_validation}`",
            f"- stale_override_used: `{stale_override}`",
            f"- expired_signal_override_used: `{expired_override}`",
            f"- explicit_second_demo_send_after_client_reject_flat: `{explicit_client_reject_resend}`",
            f"- previous_state_status: `{client_reject_contract.get('previous_state_status', '')}`",
            f"- previous_send_retcode: `{client_reject_contract.get('previous_send_retcode', '')}`",
            f"- new_operator_authorized_attempt: `{explicit_client_reject_resend}`",
            f"- strategy_valid: `{strategy_valid}`",
            f"- production_valid: `{strategy_valid}`",
            f"- send_readiness_for_demo_module_validation_only: `{send_readiness_demo_only}`",
            "",
        ]
    lines = [
        "# Fixed-Candidate Demo Order-Send Pilot Readiness Plan",
        "",
        "Artifact-only readiness plan for a future first demo order-send pilot.",
        "",
        "No MT5 import or connection was performed. No broker/API query, positions/orders/history read, order-send call, order-check call, order-calc call, order execution, broker payload, executable order object, future state write, database mutation, child script, scheduler, loop, background task, demo broker approval, or trading decision was performed.",
        "",
        "This plan does not authorize order-send now and does not authorize execution. A separate future send module must rerun all pre-send checks immediately before any send attempt.",
        "",
        "The audited future contract requires a default no-send CLI, an explicit real-send flag, a one-shot final operator confirmation, digest binding, a durable atomic pre-send claim, bounded post-send reconciliation, no automatic retry, mocked dependency tests, and a future static safety-grep gate.",
        "",
        "## Result",
        "",
        f"- order_send_pilot_readiness_status: `{status}`",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{sum(1 for warning in warnings if warning.get('blocking_warning') == 'true')}`",
        "",
        *module_lines,
        "## Recommended Next Step",
        "",
        f"`{recommended_next_step(status)}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    args: argparse.Namespace,
    output_dir: Path,
    status: str,
    inputs: dict[str, Any],
    warnings: list[dict[str, Any]],
    paths: dict[str, Path],
) -> None:
    available = status == "order_send_pilot_readiness_plan_available_no_send"
    approval_expiry = parse_time(inputs["approval_record"].get("approval_expiry_time_utc"))
    approval_is_expired = approval_expiry is None or approval_expiry <= utc_now()
    stale_override_used = bool(stale_override_allowed(args, inputs))
    expired_signal_override_used = bool(expired_signal_override_allowed(args, inputs) and approval_is_expired)
    module_validation_demo_execution = bool(
        args.module_validation_demo_execution
        or inputs["request_manifest"].get("module_validation_demo_execution") is True
        or inputs["order_check_manifest"].get("module_validation_demo_execution") is True
    )
    strategy_valid = not bool(module_validation_demo_execution or stale_override_used or expired_signal_override_used)
    production_valid = strategy_valid
    send_readiness_for_demo_module_validation_only = bool(
        available and demo_module_validation_send_readiness_allowed(args, inputs)
    )
    client_reject_contract = inputs.get("client_reject_flat_contract") or {}
    explicit_client_reject_resend = bool(client_reject_contract.get("accepted"))
    content = {
        "run_id": args.run_id,
        "order_send_pilot_readiness_status": status,
        "candidate_id": CANDIDATE_ID,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "direction": DIRECTION,
        "source_nature": "passed_order_check" if available else "fixture_or_blocked",
        "order_check_status": order_check_status(inputs),
        "order_check_passed": inputs["order_check_manifest"].get("order_check_passed"),
        "order_check_called": inputs["order_check_manifest"].get("order_check_called"),
        "order_check_retcode": inputs["order_check_manifest"].get("order_check_retcode"),
        "order_check_run_id": inputs["order_check_manifest"].get("run_id", ""),
        "request_construction_status": inputs["request_manifest"].get("request_construction_status", ""),
        "module_validation_demo_execution": module_validation_demo_execution,
        "stale_override_used": stale_override_used,
        "expired_signal_override_used": expired_signal_override_used,
        "explicit_second_demo_send_after_client_reject_flat": explicit_client_reject_resend,
        "client_reject_resend_acknowledgment_valid": bool(
            client_reject_contract.get("client_reject_resend_acknowledgment_valid")
        ),
        "previous_state_status": client_reject_contract.get("previous_state_status", ""),
        "previous_send_retcode": client_reject_contract.get("previous_send_retcode", ""),
        "new_operator_authorized_attempt": explicit_client_reject_resend,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "strategy_valid": strategy_valid,
        "production_valid": production_valid,
        "send_readiness_for_demo_module_validation_only": send_readiness_for_demo_module_validation_only,
        "future_order_send_ready": available,
        "order_send_allowed_now": False,
        "order_send_callable_future_only": True,
        "order_execution_allowed": False,
        "broker_payload_constructed": False,
        "executable_order_object_constructed": False,
        "order_send_called": False,
        "order_send_call_count": 0,
        "order_execution_performed": False,
        "future_state_json_written": False,
        "approval_record_exists": bool(inputs["approval_record"]),
        "future_state_json_exists": inputs["future_state_exists"],
        "readiness_patch_status": "order_send_pilot_readiness_audit_gaps_closed_no_send",
        "cli_contract_complete": True,
        "final_operator_confirmation_contract_complete": True,
        "binding_digest_contract_complete": True,
        "atomic_state_contract_complete": True,
        "post_send_state_update_contract_complete": True,
        "retcode_failure_matrix_complete": True,
        "bounded_reconciliation_contract_complete": True,
        "future_mocked_mt5_test_contract_complete": True,
        "future_send_safety_grep_contract_complete": True,
        "output_files": {key: str(value) for key, value in paths.items()},
        "created_at_utc": utc_now_text(),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "recommended_next_step": recommended_next_step(status),
        "no_mt5_import_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_api_query_performed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_execution_performed": True,
        "no_broker_payload_constructed": True,
        "no_executable_order_object_constructed": True,
        "no_future_state_json_written": True,
        "no_child_scripts_executed": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    write_json(path, content)


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for(args)
    paths = output_paths(output_dir)
    ensure_outputs_writable(paths, bool(args.overwrite))
    warnings: list[dict[str, Any]] = []
    add_boundary_warnings(args, warnings)
    inputs = load_inputs(args)
    status, gates = evaluate(args, inputs, warnings)
    write_csv(paths["gate_checks"], gates, GATE_FIELDNAMES)
    write_csv(paths["send_inputs"], send_input_rows(args, inputs), SEND_INPUT_FIELDNAMES)
    write_csv(paths["broker_send_fields"], broker_send_field_rows(args), BROKER_SEND_FIELDNAMES)
    write_csv(paths["pre_send_rechecks"], pre_send_recheck_rows(args), PRE_SEND_FIELDNAMES)
    write_csv(paths["state_transitions"], state_transition_rows(args), STATE_FIELDNAMES)
    write_csv(paths["retcodes"], retcode_rows(args), RETCODE_FIELDNAMES)
    write_csv(paths["post_send_reconciliation"], post_send_reconciliation_rows(args), POST_SEND_FIELDNAMES)
    write_csv(paths["crash_recovery"], crash_recovery_rows(args), CRASH_FIELDNAMES)
    write_csv(paths["blocks"], block_rows(args, gates), BLOCK_FIELDNAMES)
    write_csv(paths["bound_order_check"], [bound_order_check_row(args, inputs)], BOUND_ORDER_CHECK_FIELDNAMES)
    write_csv(paths["bound_upstream"], bound_upstream_rows(args, inputs), BOUND_UPSTREAM_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["no_order"], [no_order_evidence_row(args)], NO_ORDER_FIELDNAMES)
    write_csv(paths["future_send_cli_contract"], future_send_cli_contract_rows(args), CLI_CONTRACT_FIELDNAMES)
    write_csv(
        paths["final_operator_confirmation_contract"],
        final_operator_confirmation_contract_rows(args),
        FINAL_CONFIRMATION_FIELDNAMES,
    )
    write_csv(
        paths["request_order_check_send_binding"],
        request_order_check_send_binding_rows(args),
        BINDING_FIELDNAMES,
    )
    write_csv(paths["atomic_state_contract"], atomic_state_contract_rows(args), ATOMIC_STATE_FIELDNAMES)
    write_csv(
        paths["post_send_state_update_contract"],
        post_send_state_update_contract_rows(args),
        POST_SEND_STATE_FIELDNAMES,
    )
    write_csv(paths["future_send_test_contract"], future_send_test_contract_rows(args), FUTURE_SEND_TEST_FIELDNAMES)
    write_csv(
        paths["future_send_safety_grep_contract"],
        future_send_safety_grep_contract_rows(args),
        FUTURE_SEND_SAFETY_FIELDNAMES,
    )
    write_report(paths["report"], status, warnings, args, inputs)
    write_manifest(paths["manifest"], args, output_dir, status, inputs, warnings, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a fixed-candidate demo order-send pilot readiness plan without calling broker/order paths.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--order-check-dir", type=Path, default=DEFAULT_ORDER_CHECK_DIR)
    parser.add_argument("--order-check-readiness-plan-dir", type=Path, default=DEFAULT_ORDER_CHECK_READINESS_DIR)
    parser.add_argument("--request-construction-dry-run-dir", type=Path, default=DEFAULT_REQUEST_CONSTRUCTION_DIR)
    parser.add_argument("--manual-approval-record-json", type=Path, default=DEFAULT_APPROVAL_RECORD_JSON)
    parser.add_argument("--manual-approval-record-schema-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    parser.add_argument("--broker-local-reconciliation-dir", type=Path, default=DEFAULT_BROKER_LOCAL_RECONCILIATION_DIR)
    parser.add_argument("--broker-safe-margin-validation-dir", type=Path, default=DEFAULT_BROKER_SAFE_MARGIN_VALIDATION_DIR)
    parser.add_argument("--live-signal-freshness-dir", type=Path, default=DEFAULT_LIVE_SIGNAL_FRESHNESS_DIR)
    parser.add_argument("--duplicate-protection-plan-dir", type=Path, default=DEFAULT_DUPLICATE_PROTECTION_DIR)
    parser.add_argument("--manual-approval-kill-switch-plan-dir", type=Path, default=DEFAULT_MANUAL_APPROVAL_KILL_SWITCH_DIR)
    parser.add_argument("--future-request-readiness-plan-dir", type=Path, default=DEFAULT_FUTURE_REQUEST_READINESS_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_DEMO_EXECUTION_POLICY)
    parser.add_argument("--future-state-json", type=Path, default=DEFAULT_FUTURE_STATE_JSON)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--module-validation-demo-execution", action="store_true")
    parser.add_argument("--allow-stale-upstream-artifacts-for-demo-module-validation", action="store_true")
    parser.add_argument("--module-validation-acknowledgment", default="")
    parser.add_argument("--allow-expired-signal-for-demo-module-validation", action="store_true")
    parser.add_argument("--expired-signal-override-acknowledgment", default="")
    parser.add_argument("--allow-new-demo-send-after-client-reject-flat", action="store_true")
    parser.add_argument("--client-reject-resend-acknowledgment", default="")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = build_outputs(args)
    print("Fixed-candidate demo order-send pilot readiness plan complete.")
    for key, path in paths.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
