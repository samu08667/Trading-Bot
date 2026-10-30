"""Build an artifact-only readiness plan for a future demo order-check module.

This planner reads the fixed-candidate request-construction dry-run packet and
upstream safety artifacts, then writes a non-executable contract for a later
module that may perform an explicitly controlled order-check step. It does not
import/connect to MT5, query broker/API state, construct a broker payload or
executable order object, call order-check or order-send paths, execute orders,
mutate databases, write future trading state, or run child scripts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_order_check_readiness_plan"
DEFAULT_REQUEST_CONSTRUCTION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_request_construction_dry_run"
    / "gbpusd_short_h10_1_5_off_hours_demo_request_construction_dry_run_fixture_v1"
)
DEFAULT_SCHEMA_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_manual_approval_record_schema"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record_schema_v1"
)
DEFAULT_FUTURE_REQUEST_READINESS_DIR = (
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
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_DEMO_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_APPROVAL_RECORD_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record.json"
)
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR / "state" / "fixed_candidate_demo_state" / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_order_check_readiness_plan"

REQUEST_MANIFEST = "fixed_candidate_demo_request_construction_dry_run_manifest.json"
REQUEST_INTENT = "fixed_candidate_demo_request_construction_dry_run_request_intent.csv"
REQUEST_FIELDS = "fixed_candidate_demo_request_construction_dry_run_request_fields.csv"
SCHEMA_MANIFEST = "fixed_candidate_demo_manual_approval_record_schema_manifest.json"
SCHEMA_POST_APPROVAL_RECHECKS = "fixed_candidate_demo_manual_approval_record_schema_post_approval_pre_request_rechecks.csv"
FUTURE_REQUEST_MANIFEST = "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json"
BROKER_RECON_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
MARGIN_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"
FRESHNESS_MANIFEST = "fixed_candidate_demo_live_signal_freshness_manifest.json"
DUPLICATE_MANIFEST = "fixed_candidate_demo_duplicate_protection_plan_manifest.json"
MANUAL_PLAN_MANIFEST = "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_order_check_readiness_plan_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_order_check_readiness_plan_report.md"
OUTPUT_GATE_CHECKS = "fixed_candidate_demo_order_check_readiness_plan_gate_checks.csv"
OUTPUT_FUTURE_INPUTS = "fixed_candidate_demo_order_check_readiness_plan_future_order_check_inputs.csv"
OUTPUT_FUTURE_BROKER_FIELDS = "fixed_candidate_demo_order_check_readiness_plan_future_broker_request_fields.csv"
OUTPUT_PRE_RECHECKS = "fixed_candidate_demo_order_check_readiness_plan_pre_order_check_rechecks.csv"
OUTPUT_BLOCKS = "fixed_candidate_demo_order_check_readiness_plan_block_conditions.csv"
OUTPUT_BOUND_INTENT = "fixed_candidate_demo_order_check_readiness_plan_bound_request_intent.csv"
OUTPUT_BOUND_UPSTREAM = "fixed_candidate_demo_order_check_readiness_plan_bound_upstream_artifacts.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_order_check_readiness_plan_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_order_check_readiness_plan_no_order_evidence.csv"

ACCEPTED_REQUEST_STATUSES = {
    "request_construction_dry_run_available_non_executable",
    "request_construction_dry_run_fixture_only_no_approval_record",
}

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
FUTURE_INPUT_FIELDNAMES = [
    "run_id",
    "field_name",
    "intended_value",
    "source",
    "required_for_future_order_check",
    "must_be_rechecked_before_order_check",
    "broker_payload_field_now",
    "executable_now",
    "safety_note",
]
FUTURE_BROKER_FIELDNAMES = [
    "run_id",
    "future_mt5_field",
    "mapping_description",
    "source_or_future_source",
    "available_now",
    "requires_broker_read_at_order_check_time",
    "executable_now",
    "safety_note",
]
PRE_RECHECK_FIELDNAMES = [
    "run_id",
    "recheck_name",
    "timing",
    "required",
    "blocking_if_failed",
    "expected_value",
    "safety_note",
]
BLOCK_FIELDNAMES = ["run_id", "block_condition", "condition_status", "observed_value", "expected_value", "blocking_if_failed", "caveat"]
BOUND_INTENT_FIELDNAMES = [
    "run_id",
    "request_construction_dry_run_dir",
    "request_intent_path",
    "request_construction_status",
    "request_intent_created",
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


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return bool_text(value)
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
        "gate_checks": output_dir / OUTPUT_GATE_CHECKS,
        "future_inputs": output_dir / OUTPUT_FUTURE_INPUTS,
        "future_broker_fields": output_dir / OUTPUT_FUTURE_BROKER_FIELDS,
        "pre_rechecks": output_dir / OUTPUT_PRE_RECHECKS,
        "blocks": output_dir / OUTPUT_BLOCKS,
        "bound_intent": output_dir / OUTPUT_BOUND_INTENT,
        "bound_upstream": output_dir / OUTPUT_BOUND_UPSTREAM,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
    }


def ensure_outputs_writable(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)


def source_paths(args: argparse.Namespace) -> dict[str, Path]:
    request_dir = Path(args.request_construction_dry_run_dir)
    schema_dir = Path(args.manual_approval_record_schema_dir)
    return {
        "request_dir": request_dir,
        "request_manifest": request_dir / REQUEST_MANIFEST,
        "request_intent": request_dir / REQUEST_INTENT,
        "request_fields": request_dir / REQUEST_FIELDS,
        "schema_manifest": schema_dir / SCHEMA_MANIFEST,
        "post_approval_rechecks": schema_dir / SCHEMA_POST_APPROVAL_RECHECKS,
        "future_request": Path(args.future_request_readiness_plan_dir) / FUTURE_REQUEST_MANIFEST,
        "reconciliation": Path(args.broker_local_reconciliation_dir) / BROKER_RECON_MANIFEST,
        "margin": Path(args.broker_safe_margin_validation_dir) / MARGIN_MANIFEST,
        "margin_snapshot": Path(args.broker_safe_margin_validation_dir) / MARGIN_SNAPSHOT,
        "freshness": Path(args.live_signal_freshness_dir) / FRESHNESS_MANIFEST,
        "duplicate": Path(args.duplicate_protection_plan_dir) / DUPLICATE_MANIFEST,
        "manual_plan": Path(args.manual_approval_kill_switch_plan_dir) / MANUAL_PLAN_MANIFEST,
        "registry": Path(args.canonical_registry),
        "policy": Path(args.demo_execution_policy),
        "future_approval": Path(args.future_approval_record_json),
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


def add_boundary_warnings(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> None:
    for code, message in (
        ("order_check_not_called", "This planner did not call order-check paths."),
        ("order_send_not_called", "This planner did not call order-send paths."),
        ("readiness_plan_does_not_authorize_order_check", "This readiness plan does not authorize order-check now."),
        ("readiness_plan_does_not_authorize_order_send", "This readiness plan does not authorize order-send now."),
        ("final_rechecks_required_before_future_order_check", "All pre-order-check rechecks must be rerun by a separate future module."),
    ):
        add_warning(
            warnings,
            args=args,
            warning_code=code,
            message=message,
            source="fixed_candidate_demo_order_check_readiness_plan",
            blocking_warning=False,
            severity="info",
        )


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    paths = source_paths(args)
    inputs: dict[str, Any] = {"paths": paths}
    always_required = {"request_manifest", "schema_manifest", "post_approval_rechecks", "registry", "policy"}
    json_keys = (
        "request_manifest",
        "schema_manifest",
        "future_request",
        "reconciliation",
        "margin",
        "margin_snapshot",
        "freshness",
        "duplicate",
        "manual_plan",
        "registry",
        "policy",
    )
    for key in json_keys:
        data, error = read_json(paths[key])
        inputs[key] = data
        if error and key in always_required:
            add_warning(
                warnings,
                args=args,
                warning_code=f"{key}_missing_or_unreadable",
                message=error,
                source=paths[key],
                blocking_warning=True,
            )
    request_fields, fields_error = read_csv_rows(paths["request_fields"])
    request_intent, intent_error = read_csv_rows(paths["request_intent"])
    post_rechecks, rechecks_error = read_csv_rows(paths["post_approval_rechecks"])
    inputs["request_fields"] = request_fields
    inputs["request_fields_error"] = fields_error
    inputs["request_intent"] = request_intent
    inputs["request_intent_error"] = intent_error
    inputs["post_approval_rechecks"] = post_rechecks
    inputs["post_approval_rechecks_error"] = rechecks_error
    if rechecks_error:
        add_warning(
            warnings,
            args=args,
            warning_code="post_approval_rechecks_missing_or_unreadable",
            message=rechecks_error,
            source=paths["post_approval_rechecks"],
            blocking_warning=True,
        )
    inputs["future_approval_record_exists"] = paths["future_approval"].exists()
    inputs["future_state_json_exists"] = paths["future_state"].exists()
    inputs["future_state"] = {}
    if paths["future_state"].exists():
        future_state, future_state_error = read_json(paths["future_state"])
        inputs["future_state"] = future_state
        inputs["future_state_error"] = future_state_error
    else:
        inputs["future_state_error"] = "missing"
    return inputs


def validate_canonical_registry(registry: dict[str, Any]) -> bool:
    return (
        registry.get("candidate_id") == CANDIDATE_ID
        and registry.get("symbol") == SYMBOL
        and registry.get("timeframe") == TIMEFRAME
        and registry.get("direction") == DIRECTION
        and registry.get("spread_unit") == "broker_points"
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


def validate_schema(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("schema_status") == "manual_approval_record_schema_available_no_order"
        and manifest.get("schema_patch_status") == "schema_audit_gaps_closed_no_order"
    )


def validate_post_approval_rows(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and all(row.get("required") == "true" and row.get("blocking_if_failed") == "true" for row in rows)


def request_status(inputs: dict[str, Any]) -> str:
    return str(inputs["request_manifest"].get("request_construction_status", ""))


def is_fixture_only(inputs: dict[str, Any]) -> bool:
    return request_status(inputs) == "request_construction_dry_run_fixture_only_no_approval_record"


def validate_request_manifest_flags(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("request_intent_created") is True
        and manifest.get("request_construction_mode") == "dry_run_non_executable"
        and manifest.get("broker_payload_constructed") is False
        and manifest.get("executable_order_object_constructed") is False
        and manifest.get("order_check_called") is False
        and manifest.get("order_send_called") is False
        and manifest.get("order_execution_performed") is False
        and manifest.get("future_state_json_written") is False
    )


def first_request_intent(inputs: dict[str, Any]) -> dict[str, str]:
    return inputs["request_intent"][0] if inputs["request_intent"] else {}


def false_csv(value: Any) -> bool:
    return str(value).lower() == "false"


def validate_intent_fields(intent: dict[str, str]) -> bool:
    return (
        intent.get("side") == SIDE_INTENT
        and intent.get("order_type_intent") == ORDER_TYPE_INTENT
        and intent.get("symbol") == SYMBOL
        and intent.get("timeframe") == TIMEFRAME
        and intent.get("direction") == DIRECTION
        and safe_float(intent.get("volume_lots")) is not None
        and safe_float(intent.get("volume_lots")) > 0
        and bool(intent.get("entry_reference_price"))
        and bool(intent.get("sl_price"))
        and bool(intent.get("tp_price"))
        and bool(intent.get("signal_id"))
        and bool(intent.get("idempotency_key"))
        and intent.get("approval_scope") == "future_request_construction_only"
        and false_csv(intent.get("broker_payload_constructed"))
        and false_csv(intent.get("executable_order_object_constructed"))
        and false_csv(intent.get("order_check_allowed_now"))
        and false_csv(intent.get("order_send_allowed_now"))
        and false_csv(intent.get("order_execution_allowed"))
    )


def validate_request_fields(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and all(
        row.get("broker_payload_field_now") == "false"
        and row.get("executable_now") == "false"
        and row.get("intended_value") not in ("order_check_allowed_now", "order_send_allowed_now")
        for row in rows
    )


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
    ratio = safe_float(manifest.get("broker_margin_usage_ratio"))
    if ratio is None:
        ratio = safe_float(snapshot.get("broker_margin_usage_ratio"))
    return (
        manifest.get("validation_status") == "broker_safe_margin_validation_available"
        and manifest.get("account_mode_label") == "demo"
        and ratio is not None
        and ratio <= HARD_MARGIN_CAP_RATIO
        and manifest.get("spread_within_policy") is True
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


def future_state_incompatible(inputs: dict[str, Any]) -> bool:
    state = inputs.get("future_state") or {}
    if not state:
        return False
    text = json.dumps(state, sort_keys=True).lower()
    markers = ("open", "pending", "active", "incompatible")
    return any(marker in text for marker in markers)


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
    req_status = request_status(inputs)
    fixture_only = is_fixture_only(inputs)
    intent = first_request_intent(inputs)
    nonfixture = req_status == "request_construction_dry_run_available_non_executable"
    gates = [
        gate_row(args, "canonical_candidate", validate_canonical_registry(inputs["registry"]), inputs["registry"].get("candidate_id"), CANDIDATE_ID, paths["registry"], "order_check_readiness_plan_blocked_noncanonical_candidate"),
        gate_row(args, "demo_execution_policy", validate_demo_policy(inputs["policy"]), inputs["policy"].get("policy_id", ""), "no order-check/order-send/order-calc policy", paths["policy"], "order_check_readiness_plan_blocked_noncanonical_demo_execution_policy"),
        gate_row(args, "schema_manifest", validate_schema(inputs["schema_manifest"]), inputs["schema_manifest"].get("schema_status"), "manual_approval_record_schema_available_no_order", paths["schema_manifest"], "order_check_readiness_plan_blocked_noncanonical_demo_execution_policy"),
        gate_row(args, "schema_post_approval_rechecks", validate_post_approval_rows(inputs["post_approval_rechecks"]), len(inputs["post_approval_rechecks"]), "all rows required/blocking", paths["post_approval_rechecks"], "order_check_readiness_plan_blocked_noncanonical_demo_execution_policy"),
        gate_row(args, "request_construction_manifest", bool(inputs["request_manifest"]), req_status or "missing", "request construction dry-run manifest", paths["request_manifest"], "order_check_readiness_plan_blocked_missing_request_construction"),
        gate_row(args, "request_construction_status", req_status in ACCEPTED_REQUEST_STATUSES, req_status, "accepted fixture-only or non-executable dry-run status", paths["request_manifest"], "order_check_readiness_plan_blocked_unacceptable_request_construction_status"),
    ]
    if nonfixture:
        gates.extend(
            [
                gate_row(args, "request_construction_flags", validate_request_manifest_flags(inputs["request_manifest"]), inputs["request_manifest"].get("request_construction_mode"), "dry_run_non_executable and no broker payload/object/check/send", paths["request_manifest"], "order_check_readiness_plan_blocked_request_intent_executable"),
                gate_row(args, "request_intent_available", bool(inputs["request_intent"]), inputs["request_intent_error"] or len(inputs["request_intent"]), "request intent CSV present", paths["request_intent"], "order_check_readiness_plan_blocked_request_intent_missing"),
                gate_row(args, "request_intent_non_executable", validate_intent_fields(intent), intent.get("side", ""), "sell market intent with all safety flags false", paths["request_intent"], "order_check_readiness_plan_blocked_request_intent_executable"),
                gate_row(args, "request_fields_non_executable", validate_request_fields(inputs["request_fields"]), inputs["request_fields_error"] or len(inputs["request_fields"]), "all field descriptors non-payload and non-executable", paths["request_fields"], "order_check_readiness_plan_blocked_request_intent_executable"),
                gate_row(args, "live_signal_freshness", validate_freshness(inputs["freshness"]), inputs["freshness"].get("freshness_status"), "fresh signal within h10", paths["freshness"], "order_check_readiness_plan_blocked_stale_signal"),
                gate_row(args, "broker_local_reconciliation", validate_reconciliation(inputs["reconciliation"]), inputs["reconciliation"].get("reconciliation_status"), "clean no local/no broker", paths["reconciliation"], "order_check_readiness_plan_blocked_broker_local_reconciliation"),
                gate_row(args, "broker_safe_margin", validate_margin(inputs["margin"], inputs["margin_snapshot"]), inputs["margin"].get("broker_margin_usage_ratio"), "demo margin usage <= 0.70 and spread within policy", paths["margin"], "order_check_readiness_plan_blocked_margin_policy"),
                gate_row(args, "duplicate_protection", validate_duplicate(inputs["duplicate"]), inputs["duplicate"].get("plan_status"), "duplicate protection available", paths["duplicate"], "order_check_readiness_plan_blocked_duplicate_protection"),
                gate_row(args, "manual_approval_kill_switch", validate_manual_plan(inputs["manual_plan"]), inputs["manual_plan"].get("plan_status"), "kill-switch plan available and inactive", paths["manual_plan"], "order_check_readiness_plan_blocked_kill_switch"),
                gate_row(args, "future_request_readiness", validate_future_request(inputs["future_request"]), inputs["future_request"].get("plan_status"), "future request readiness no-order", paths["future_request"], "order_check_readiness_plan_blocked_noncanonical_demo_execution_policy"),
                gate_row(args, "future_state_compatible", not future_state_incompatible(inputs), "exists" if inputs["future_state_json_exists"] else "missing", "missing or compatible with no pending/open state", paths["future_state"], "order_check_readiness_plan_blocked_future_state_incompatible"),
            ]
        )
    elif fixture_only:
        gates.extend(
            [
                gate_row(args, "fixture_only_request_intent", True, "not_created", "future request intent required before order-check module", paths["request_intent"], "order_check_readiness_plan_fixture_only_no_request_intent", blocking=False),
                gate_row(args, "future_order_check_gates_recorded", True, "fixture_only", "fresh signal, approval, reconciliation, margin, duplicate, kill-switch must pass later", paths["request_manifest"], "future_rechecks_required", blocking=False),
            ]
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
    status = status_from_gates(gates, req_status, fixture_only)
    return status, gates


def status_from_gates(gates: list[dict[str, Any]], req_status: str, fixture_only: bool) -> str:
    failures = [row for row in gates if row["gate_status"] == "failed" and row["blocking_if_failed"] is True]
    if failures:
        code = str(failures[0]["warning_code"])
        if code.startswith("order_check_readiness_plan_"):
            return code
        return "order_check_readiness_plan_blocked_unacceptable_request_construction_status"
    if fixture_only:
        return "order_check_readiness_plan_fixture_only_no_request_intent"
    if req_status == "request_construction_dry_run_available_non_executable":
        return "order_check_readiness_plan_available_no_order_check"
    return "order_check_readiness_plan_blocked_unacceptable_request_construction_status"


def future_order_check_input_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    intent = first_request_intent(inputs)
    values = {
        "action_intent": "future_deal",
        "symbol": intent.get("symbol", SYMBOL) or SYMBOL,
        "volume": intent.get("volume_lots", ""),
        "type_intent": SIDE_INTENT,
        "price_reference": intent.get("entry_reference_price", ""),
        "sl": intent.get("sl_price", ""),
        "tp": intent.get("tp_price", ""),
        "deviation_policy": "future_policy_recheck_required",
        "magic_policy": "future_policy_recheck_required",
        "comment_policy": "future_policy_recheck_required",
        "type_time_policy": "future_policy_recheck_required",
        "type_filling_policy": "future_policy_recheck_required",
        "signal_id": intent.get("signal_id", ""),
        "idempotency_key": intent.get("idempotency_key", ""),
        "approval_record_id": intent.get("approval_record_id", ""),
    }
    return [
        {
            "run_id": args.run_id,
            "field_name": name,
            "intended_value": value,
            "source": "request_construction_dry_run_or_future_recheck",
            "required_for_future_order_check": True,
            "must_be_rechecked_before_order_check": True,
            "broker_payload_field_now": False,
            "executable_now": False,
            "safety_note": "descriptor_only_not_a_broker_payload_and_not_callable_now",
        }
        for name, value in values.items()
    ]


def future_broker_request_field_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = [
        ("action", "future mapping to trade action deal", "future controlled order-check module policy"),
        ("symbol", "GBPUSD", "fixed candidate and future symbol recheck"),
        ("volume", "stepped volume from approved non-executable intent", "request intent plus future volume recheck"),
        ("type", "future mapping to sell order type", "fixed candidate direction"),
        ("price", "future current price policy/read at order-check time", "future broker read in separate module"),
        ("sl", "stop-loss bound from approved intent", "request intent plus stop-level recheck"),
        ("tp", "take-profit bound from approved intent", "request intent plus stop-level recheck"),
        ("deviation", "future deviation policy", "future controlled order-check module policy"),
        ("magic", "future magic policy", "future controlled order-check module policy"),
        ("comment", "future audit-safe comment policy", "future controlled order-check module policy"),
        ("type_time", "future time-in-force policy", "future controlled order-check module policy"),
        ("type_filling", "future filling policy after broker contract recheck", "future controlled order-check module policy"),
    ]
    return [
        {
            "run_id": args.run_id,
            "future_mt5_field": name,
            "mapping_description": description,
            "source_or_future_source": source,
            "available_now": name in {"symbol", "volume", "type", "sl", "tp"},
            "requires_broker_read_at_order_check_time": name in {"price", "type_filling"},
            "executable_now": False,
            "safety_note": "future_mapping_only_no_executable_object_now",
        }
        for name, description, source in specs
    ]


def pre_order_check_recheck_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
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
        ("recheck_order_check_policy_explicitly_enabled_for_check_module", "separate future check module has explicit permission"),
        ("recheck_no_existing_active_request_for_idempotency_key", "no active intent for idempotency key"),
        ("recheck_no_scheduler_loop_background", "single-shot only, no scheduler/loop/background task"),
    ]
    return [
        {
            "run_id": args.run_id,
            "recheck_name": name,
            "timing": "immediately_before_future_order_check",
            "required": True,
            "blocking_if_failed": True,
            "expected_value": expected,
            "safety_note": "future_module_must_rerun_this_check_before_any_order_check_call",
        }
        for name, expected in specs
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
            "caveat": "blocks future order-check readiness when failed",
        }
        for row in gates
    ]


def bound_request_intent_row(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    path = inputs["paths"]["request_intent"]
    return {
        "run_id": args.run_id,
        "request_construction_dry_run_dir": str(inputs["paths"]["request_dir"]),
        "request_intent_path": str(path),
        "request_construction_status": request_status(inputs),
        "request_intent_created": inputs["request_manifest"].get("request_intent_created", False),
        "binding_status": "bound_read_only" if path.exists() and inputs["request_intent"] else "not_bound_fixture_or_missing",
        "sha256_digest": sha256_file(path),
    }


def bound_upstream_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    specs = [
        ("request_construction_manifest", "request_manifest", "request_construction_status"),
        ("schema_manifest", "schema_manifest", "schema_status"),
        ("future_request_readiness", "future_request", "plan_status"),
        ("broker_local_reconciliation", "reconciliation", "reconciliation_status"),
        ("broker_safe_margin_validation", "margin", "validation_status"),
        ("broker_safe_margin_validation_margin_snapshot", "margin_snapshot", "validation_status"),
        ("live_signal_freshness", "freshness", "freshness_status"),
        ("duplicate_protection", "duplicate", "plan_status"),
        ("manual_approval_kill_switch", "manual_plan", "plan_status"),
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
        "evidence_label": "order_check_readiness_plan_no_order_boundary",
        "caveat": "planning_only_no_order_check_no_order_send_no_broker_payload",
    }


def recommended_next_step(status: str) -> str:
    if status == "order_check_readiness_plan_available_no_order_check":
        return "implement_check_fixed_candidate_demo_order_check_module_no_send"
    if status == "order_check_readiness_plan_fixture_only_no_request_intent":
        return "wait_for_fresh_signal_valid_approval_and_non_executable_request_intent"
    return "resolve_blocking_condition_before_future_order_check"


def write_report(path: Path, status: str, warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed-Candidate Demo Order-Check Readiness Plan",
        "",
        "Artifact-only readiness plan for a future order-check module.",
        "",
        "No MT5 import or connection was performed. No broker/API query, positions/orders/history read, order-check call, order-send call, order-calc call, order execution, broker payload, executable order object, future state write, database mutation, child script, scheduler, loop, background task, demo broker approval, or trading decision was performed.",
        "",
        "This plan does not authorize order-check now and does not authorize order-send or any order execution. A separate future module must rerun all pre-order-check rechecks immediately before any order-check attempt.",
        "",
        "## Result",
        "",
        f"- order_check_readiness_status: `{status}`",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{sum(1 for warning in warnings if warning.get('blocking_warning') == 'true')}`",
        "",
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
    intent = first_request_intent(inputs)
    fixture_only = status == "order_check_readiness_plan_fixture_only_no_request_intent"
    available = status == "order_check_readiness_plan_available_no_order_check"
    content = {
        "run_id": args.run_id,
        "order_check_readiness_status": status,
        "candidate_id": CANDIDATE_ID,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "direction": DIRECTION,
        "source_nature": "fixture_only_no_request_intent" if fixture_only else "non_executable_request_intent" if available else "blocked",
        "request_construction_status": request_status(inputs),
        "request_intent_created": inputs["request_manifest"].get("request_intent_created", False),
        "future_order_check_ready": available,
        "order_check_allowed_now": False,
        "order_check_callable_future_only": True,
        "order_send_allowed_now": False,
        "order_execution_allowed": False,
        "broker_payload_constructed": False,
        "executable_order_object_constructed": False,
        "order_check_called": False,
        "order_send_called": False,
        "order_execution_performed": False,
        "future_state_json_written": False,
        "approval_record_exists": inputs["future_approval_record_exists"],
        "future_state_json_exists": inputs["future_state_json_exists"],
        "signal_id": intent.get("signal_id", ""),
        "idempotency_key": intent.get("idempotency_key", ""),
        "approval_record_id": intent.get("approval_record_id", ""),
        "output_files": {key: str(value) for key, value in paths.items()},
        "created_at_utc": utc_now_text(),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "recommended_next_step": recommended_next_step(status),
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
    }
    write_json(path, content)


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for(args)
    paths = output_paths(output_dir)
    ensure_outputs_writable(paths, bool(args.overwrite))
    warnings: list[dict[str, Any]] = []
    add_boundary_warnings(args, warnings)
    inputs = load_inputs(args, warnings)
    status, gates = evaluate(args, inputs, warnings)
    write_csv(paths["gate_checks"], gates, GATE_FIELDNAMES)
    write_csv(paths["future_inputs"], future_order_check_input_rows(args, inputs), FUTURE_INPUT_FIELDNAMES)
    write_csv(paths["future_broker_fields"], future_broker_request_field_rows(args), FUTURE_BROKER_FIELDNAMES)
    write_csv(paths["pre_rechecks"], pre_order_check_recheck_rows(args), PRE_RECHECK_FIELDNAMES)
    write_csv(paths["blocks"], block_rows(args, gates), BLOCK_FIELDNAMES)
    write_csv(paths["bound_intent"], [bound_request_intent_row(args, inputs)], BOUND_INTENT_FIELDNAMES)
    write_csv(paths["bound_upstream"], bound_upstream_rows(args, inputs), BOUND_UPSTREAM_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["no_order"], [no_order_evidence_row(args)], NO_ORDER_FIELDNAMES)
    write_report(paths["report"], status, warnings)
    write_manifest(paths["manifest"], args, output_dir, status, inputs, warnings, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a fixed-candidate demo order-check readiness plan without calling broker/order paths.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--request-construction-dry-run-dir", type=Path, default=DEFAULT_REQUEST_CONSTRUCTION_DIR)
    parser.add_argument("--manual-approval-record-schema-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    parser.add_argument("--future-request-readiness-plan-dir", type=Path, default=DEFAULT_FUTURE_REQUEST_READINESS_DIR)
    parser.add_argument("--broker-local-reconciliation-dir", type=Path, default=DEFAULT_BROKER_LOCAL_RECONCILIATION_DIR)
    parser.add_argument("--broker-safe-margin-validation-dir", type=Path, default=DEFAULT_BROKER_SAFE_MARGIN_VALIDATION_DIR)
    parser.add_argument("--live-signal-freshness-dir", type=Path, default=DEFAULT_LIVE_SIGNAL_FRESHNESS_DIR)
    parser.add_argument("--duplicate-protection-plan-dir", type=Path, default=DEFAULT_DUPLICATE_PROTECTION_DIR)
    parser.add_argument("--manual-approval-kill-switch-plan-dir", type=Path, default=DEFAULT_MANUAL_APPROVAL_KILL_SWITCH_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_DEMO_EXECUTION_POLICY)
    parser.add_argument("--future-approval-record-json", type=Path, default=DEFAULT_FUTURE_APPROVAL_RECORD_JSON)
    parser.add_argument("--future-state-json", type=Path, default=DEFAULT_FUTURE_STATE_JSON)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = build_outputs(args)
    print("Fixed-candidate demo order-check readiness plan complete.")
    for key, path in paths.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
