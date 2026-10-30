"""Build an artifact-only future request construction readiness plan.

The plan defines prerequisite evidence, readiness gates, non-actionable future
field descriptors, block conditions, no-request boundaries, and audit
requirements that must be satisfied before any separate future module may even
construct a broker request. It reads only existing local artifacts and config
files. It does not import/connect MT5, query broker/API or databases, read/write
future state, run child scripts, construct broker requests or broker-ready
payloads, execute orders, approve demo use, or make trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_future_request_construction_readiness_plan"
DEFAULT_RECONCILIATION_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_future_broker_state_reconciliation_check_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_future_broker_state_reconciliation_check_plan_fixture_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_future_request_construction_readiness_plan"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_SYMBOL = "GBPUSD"
EXPECTED_TIMEFRAME = "M15"
EXPECTED_DIRECTION = "short"
EXPECTED_SESSION = "Off_hours"
EXPECTED_SPREAD_UNIT = "broker_points"
EXPECTED_MAX_SPREAD_POINTS = 15.0
EXPECTED_MAX_OPEN_POSITIONS = 1
EXPECTED_ACCOUNT_CURRENCY = "EUR"
EXPECTED_DEMO_EQUITY = 1000.0
EXPECTED_RISK_PERCENT = 0.5
EXPECTED_RISK_AMOUNT = 5.0
EXPECTED_WARNING_RATIO = 0.5
EXPECTED_WARNING_AMOUNT = 500.0
EXPECTED_CAP_RATIO = 0.7
EXPECTED_CAP_AMOUNT = 700.0
EXPECTED_HORIZON_BARS = 10
EXPECTED_SAME_BAR_POLICY = "stop_first"

SOURCE_MANIFEST = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_manifest.json"
SOURCE_REPORT = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_report.md"
SOURCE_MAIN = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan.csv"
SOURCE_LOCAL_STATE_REQUIREMENTS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_local_state_requirements.csv"
SOURCE_FUTURE_BROKER_READS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_future_broker_reads.csv"
SOURCE_MATCHING_FIELDS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_matching_fields.csv"
SOURCE_RECONCILIATION_STATUSES = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_reconciliation_statuses.csv"
SOURCE_MISMATCH_HANDLING = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_mismatch_handling.csv"
SOURCE_MAX_OPEN_POSITIONS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_max_open_positions.csv"
SOURCE_PRE_REQUEST_BLOCKS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_pre_request_blocks.csv"
SOURCE_AUDIT_REQUIREMENTS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_audit_requirements.csv"
SOURCE_WARNINGS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_warnings.csv"

OUTPUT_MAIN = "fixed_candidate_demo_future_request_construction_readiness_plan.csv"
OUTPUT_UPSTREAM_EVIDENCE = "fixed_candidate_demo_future_request_construction_readiness_plan_upstream_evidence.csv"
OUTPUT_PREREQUISITES = "fixed_candidate_demo_future_request_construction_readiness_plan_prerequisites.csv"
OUTPUT_READINESS_GATES = "fixed_candidate_demo_future_request_construction_readiness_plan_readiness_gates.csv"
OUTPUT_FUTURE_FIELD_DESCRIPTORS = "fixed_candidate_demo_future_request_construction_readiness_plan_future_field_descriptors.csv"
OUTPUT_BLOCK_CONDITIONS = "fixed_candidate_demo_future_request_construction_readiness_plan_block_conditions.csv"
OUTPUT_NO_REQUEST_BOUNDARY = "fixed_candidate_demo_future_request_construction_readiness_plan_no_request_boundary.csv"
OUTPUT_AUDIT_REQUIREMENTS = "fixed_candidate_demo_future_request_construction_readiness_plan_audit_requirements.csv"
OUTPUT_REPORT = "fixed_candidate_demo_future_request_construction_readiness_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_demo_future_request_construction_readiness_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json"

ACCEPTABLE_RECONCILIATION_PLAN_STATUSES = {
    "future_broker_state_reconciliation_check_plan_fixture_only",
    "future_broker_state_reconciliation_check_plan_available_no_order",
}

OPTIONAL_SOURCE_TRUE_FIELDS = (
    "no_mt5_connection_performed",
    "no_broker_connection_performed",
    "no_broker_api_query_performed",
    "no_db_query_performed",
    "no_db_mutation_performed",
    "no_future_state_json_read_performed",
    "no_future_state_json_write_performed",
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_positions_get_called",
    "no_orders_get_called",
    "no_history_orders_get_called",
    "no_history_deals_get_called",
    "no_trading_decision_performed",
    "no_demo_broker_approval_performed",
)

UPSTREAM_EVIDENCE = (
    ("live_data_would_signal_review", "live-data would_signal review must be available and not fixture"),
    ("broker_safe_margin_validation", "broker-safe margin validation must be available and below hard cap"),
    ("duplicate_protection", "duplicate protection must pass"),
    ("manual_approval", "manual approval must be explicit and not expired or revoked"),
    ("kill_switch", "kill-switch must be inactive"),
    ("broker_local_reconciliation", "broker/local state reconciliation must be clean"),
    ("audit_logging", "audit logging must be available"),
    ("spread_policy", "spread must be within policy"),
    ("account_mode", "account must be demo"),
    ("source_nature", "source_nature must not be synthetic_fixture"),
)

PREREQUISITES = (
    "candidate_identity_confirmed",
    "policy_identity_confirmed",
    "live_no_order_signal_confirmed",
    "would_signal_review_confirmed",
    "risk_volume_shadow_plan_confirmed",
    "broker_safe_margin_validation_confirmed",
    "state_reconciliation_confirmed",
    "duplicate_protection_confirmed",
    "manual_approval_confirmed",
    "kill_switch_inactive",
    "future_broker_local_reconciliation_clean",
    "max_open_positions_one_respected",
    "no_stale_signal",
    "audit_path_available",
)

READINESS_GATES = (
    "gate_live_signal",
    "gate_fixture_block",
    "gate_spread_policy",
    "gate_risk_policy",
    "gate_margin_policy",
    "gate_duplicate_protection",
    "gate_manual_approval",
    "gate_kill_switch",
    "gate_broker_local_reconciliation",
    "gate_max_open_positions",
    "gate_audit_logging",
    "gate_no_scheduler",
    "gate_no_background_execution",
)

FUTURE_FIELD_DESCRIPTORS = (
    "future_descriptor_candidate_id",
    "future_descriptor_symbol",
    "future_descriptor_direction_side",
    "future_descriptor_order_intent",
    "future_descriptor_entry_reference_price",
    "future_descriptor_stop_loss_price",
    "future_descriptor_take_profit_price",
    "future_descriptor_volume_lots",
    "future_descriptor_signal_time_server",
    "future_descriptor_signal_id",
    "future_descriptor_idempotency_key",
    "future_descriptor_margin_validation_run_id",
    "future_descriptor_manual_approval_id",
    "future_descriptor_reconciliation_run_id",
    "future_descriptor_audit_run_id",
)

BLOCK_CONDITIONS = (
    "fixture_source",
    "missing_live_data_would_signal",
    "missing_or_stale_manual_approval",
    "kill_switch_active",
    "duplicate_protection_not_passed",
    "broker_local_reconciliation_not_clean",
    "margin_validation_missing",
    "margin_above_hard_cap",
    "spread_above_policy",
    "risk_amount_above_cap",
    "max_open_positions_breach",
    "broker_open_position_exists",
    "broker_pending_order_exists",
    "local_state_pending_open_hold",
    "idempotency_key_already_seen",
    "stale_signal",
    "audit_unavailable",
    "unsafe_policy_flag",
)

NO_REQUEST_BOUNDARIES = (
    ("request_construction_allowed_now", False),
    ("broker_request_constructed", False),
    ("broker_payload_constructed", False),
    ("order_object_constructed", False),
    ("order_send_allowed", False),
    ("order_check_allowed", False),
    ("order_execution_allowed", False),
    ("demo_approval_performed", False),
)

AUDIT_REQUIREMENTS = (
    ("upstream_artifact_run_ids", "all upstream artifact run IDs"),
    ("readiness_gate_results", "every readiness gate result"),
    ("block_condition_results", "every block condition result"),
    ("source_nature", "source_nature"),
    ("manual_approval_status", "manual approval status"),
    ("reconciliation_status", "reconciliation status"),
    ("idempotency_key", "idempotency_key"),
    ("no_broker_request_constructed", "no broker request was constructed"),
    ("no_order_executed", "no order was executed"),
)

RESERVED_BROKER_PAYLOAD_KEYS = {"action", "type", "price", "sl", "tp", "volume"}

WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
MAIN_FIELDNAMES = [
    "run_id",
    "plan_area",
    "plan_status",
    "artifact_status",
    "source_path",
    "observed_value",
    "expected_value",
    "evidence_label",
    "caveat",
    "warning_code",
    "blocking_warning",
]
UPSTREAM_FIELDNAMES = [
    "run_id",
    "evidence_area",
    "required_evidence",
    "required_before_future_request_construction",
    "fixture_source_blocks",
    "caveat",
]
PREREQUISITE_FIELDNAMES = [
    "run_id",
    "prerequisite_name",
    "expected_condition",
    "blocking_if_missing",
    "source_or_future_artifact",
    "caveat",
]
READINESS_GATE_FIELDNAMES = [
    "run_id",
    "gate_name",
    "expected_condition",
    "blocking_if_failed",
    "evaluated_now",
    "caveat",
]
FIELD_DESCRIPTOR_FIELDNAMES = [
    "run_id",
    "descriptor_name",
    "semantic_role",
    "future_field_only",
    "not_constructed",
    "broker_request_field",
    "broker_payload_ready",
    "value_source_required",
    "executable_now",
    "caveat",
]
BLOCK_CONDITION_FIELDNAMES = [
    "run_id",
    "block_condition",
    "future_block_response",
    "blocking",
    "before_future_request_construction",
    "caveat",
]
NO_REQUEST_FIELDNAMES = [
    "run_id",
    "boundary_name",
    "observed_value",
    "expected_value",
    "boundary_confirmed",
    "caveat",
]
AUDIT_FIELDNAMES = [
    "run_id",
    "audit_area",
    "required_audit_record",
    "required_timing",
    "immutable",
    "caveat",
]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return bool_text(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def close_float(value: Any, expected: float, tolerance: float = 1e-6) -> bool:
    value_float = safe_float(value)
    return value_float is not None and abs(value_float - expected) <= tolerance


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(data, dict):
        return {}, "JSON root must be an object"
    return data, ""


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], "missing"
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), ""
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        return [], str(exc)


def read_text(path: Path) -> tuple[str, str]:
    if not path.exists():
        return "", "missing"
    try:
        return path.read_text(encoding="utf-8"), ""
    except OSError as exc:
        return "", str(exc)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


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
    severity: str,
    message: str,
    source: Path | str,
    blocking_warning: bool,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "source": str(source),
        "blocking_warning": blocking_warning,
    }


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
    warning_code: str,
    message: str,
    source: Path | str,
    blocking_warning: bool,
    severity: str | None = None,
) -> None:
    warnings.append(
        warning_row(
            run_id=args.run_id,
            warning_code=warning_code,
            severity=severity or ("error" if blocking_warning else "warning"),
            message=message,
            source=source,
            blocking_warning=blocking_warning,
        )
    )


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in warnings if as_bool(row.get("blocking_warning")) is True]


def preserve_source_warnings(args: argparse.Namespace, rows: list[dict[str, str]], source_path: Path) -> list[dict[str, Any]]:
    preserved: list[dict[str, Any]] = []
    for row in rows:
        preserved.append(
            {
                "run_id": args.run_id,
                "warning_code": f"source_{row.get('warning_code', 'warning')}",
                "severity": row.get("severity", "warning"),
                "message": row.get("message", ""),
                "source": row.get("source") or str(source_path),
                "blocking_warning": as_bool(row.get("blocking_warning")) is True,
            }
        )
    return preserved


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "main": output_dir / OUTPUT_MAIN,
        "upstream_evidence": output_dir / OUTPUT_UPSTREAM_EVIDENCE,
        "prerequisites": output_dir / OUTPUT_PREREQUISITES,
        "readiness_gates": output_dir / OUTPUT_READINESS_GATES,
        "future_field_descriptors": output_dir / OUTPUT_FUTURE_FIELD_DESCRIPTORS,
        "block_conditions": output_dir / OUTPUT_BLOCK_CONDITIONS,
        "no_request_boundary": output_dir / OUTPUT_NO_REQUEST_BOUNDARY,
        "audit_requirements": output_dir / OUTPUT_AUDIT_REQUIREMENTS,
        "report": output_dir / OUTPUT_REPORT,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "manifest": output_dir / OUTPUT_MANIFEST,
    }


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = output_paths(output_dir)
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"blocked_output_exists_without_overwrite: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def canonical_registry_valid(registry: dict[str, Any], policy: dict[str, Any]) -> bool:
    return (
        registry.get("candidate_id") == EXPECTED_CANDIDATE_ID
        and registry.get("symbol") == EXPECTED_SYMBOL
        and registry.get("timeframe") == EXPECTED_TIMEFRAME
        and registry.get("direction") == EXPECTED_DIRECTION
        and registry.get("spread_unit") == EXPECTED_SPREAD_UNIT
        and close_float(registry.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS)
        and close_float(policy.get("max_open_positions"), EXPECTED_MAX_OPEN_POSITIONS)
    )


def manual_approval_required(policy: dict[str, Any]) -> bool:
    safety = policy.get("safety_boundaries")
    if not isinstance(safety, dict):
        return False
    return as_bool(safety.get("manual_approval_required_before_any_future_demo_order")) is True


def execution_policy_valid_without_manual_gate(policy: dict[str, Any]) -> bool:
    safety = policy.get("safety_boundaries")
    if not isinstance(safety, dict):
        safety = {}
    return (
        policy.get("candidate_id") in {None, EXPECTED_CANDIDATE_ID}
        and policy.get("symbol") in {None, EXPECTED_SYMBOL}
        and policy.get("timeframe") in {None, EXPECTED_TIMEFRAME}
        and policy.get("direction") in {None, EXPECTED_DIRECTION}
        and policy.get("account_currency") == EXPECTED_ACCOUNT_CURRENCY
        and close_float(policy.get("intended_demo_equity"), EXPECTED_DEMO_EQUITY)
        and close_float(policy.get("risk_percent_max"), EXPECTED_RISK_PERCENT)
        and close_float(policy.get("risk_amount_max"), EXPECTED_RISK_AMOUNT)
        and close_float(policy.get("max_margin_usage_warning_ratio"), EXPECTED_WARNING_RATIO)
        and close_float(policy.get("max_margin_usage_warning_amount"), EXPECTED_WARNING_AMOUNT)
        and close_float(policy.get("max_margin_usage_ratio"), EXPECTED_CAP_RATIO)
        and close_float(policy.get("max_margin_usage_amount"), EXPECTED_CAP_AMOUNT)
        and close_float(policy.get("max_open_positions"), EXPECTED_MAX_OPEN_POSITIONS)
        and policy.get("spread_unit") == EXPECTED_SPREAD_UNIT
        and close_float(policy.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS)
        and as_bool(safety.get("real_money_allowed")) is False
        and as_bool(safety.get("broker_connection_allowed_for_this_policy_file")) is False
        and as_bool(safety.get("order_execution_allowed")) is False
        and as_bool(safety.get("order_request_construction_allowed")) is False
        and as_bool(safety.get("order_check_allowed")) is False
        and as_bool(safety.get("order_calc_allowed")) is False
    )


def source_boundary_valid(manifest: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if as_bool(manifest.get("plan_actionable")) is not False:
        failures.append("plan_actionable_not_false")
    for field in OPTIONAL_SOURCE_TRUE_FIELDS:
        if field in manifest and as_bool(manifest.get(field)) is not True:
            failures.append(field)
    return not failures, failures


def source_status_acceptable(status: str) -> bool:
    return status in ACCEPTABLE_RECONCILIATION_PLAN_STATUSES


def status_from_source(manifest: dict[str, Any]) -> str:
    if manifest.get("source_nature") == "synthetic_fixture":
        return "future_request_construction_readiness_plan_fixture_only"
    return "future_request_construction_readiness_plan_available_no_order"


def recommended_next_step(plan_status: str) -> str:
    if plan_status == "future_request_construction_readiness_plan_fixture_only":
        return "continue_no_order_monitoring_until_live_data_would_signal"
    if plan_status == "future_request_construction_readiness_plan_available_no_order":
        return "review_live_data_would_signal_and_refresh_planning_artifacts"
    return "fix_future_request_construction_readiness_plan_inputs"


def determine_plan_status(
    *,
    args: argparse.Namespace,
    registry_error: str,
    policy_error: str,
    source_manifest: dict[str, Any],
    source_manifest_error: str,
    local_state_error: str,
    broker_reads_error: str,
    matching_error: str,
    statuses_error: str,
    mismatch_error: str,
    max_open_error: str,
    pre_blocks_error: str,
    audit_error: str,
    canonical_ok: bool,
    policy_ok_without_manual: bool,
    manual_required: bool,
    boundary_ok: bool,
    boundary_failures: list[str],
    warnings: list[dict[str, Any]],
) -> str:
    source_dir = Path(args.future_broker_state_reconciliation_check_plan_dir)
    missing_checks = [
        (source_manifest_error, "blocked_missing_future_broker_state_reconciliation_manifest", "future_broker_state_reconciliation_manifest_missing", SOURCE_MANIFEST, "Future broker/local reconciliation manifest is missing."),
        (local_state_error, "blocked_missing_local_state_requirements", "local_state_requirements_missing", SOURCE_LOCAL_STATE_REQUIREMENTS, "Local state requirements artifact is missing."),
        (broker_reads_error, "blocked_missing_future_broker_reads", "future_broker_reads_missing", SOURCE_FUTURE_BROKER_READS, "Future broker reads artifact is missing."),
        (matching_error, "blocked_missing_matching_fields", "matching_fields_missing", SOURCE_MATCHING_FIELDS, "Matching fields artifact is missing."),
        (statuses_error, "blocked_missing_reconciliation_statuses", "reconciliation_statuses_missing", SOURCE_RECONCILIATION_STATUSES, "Reconciliation statuses artifact is missing."),
        (mismatch_error, "blocked_missing_mismatch_handling", "mismatch_handling_missing", SOURCE_MISMATCH_HANDLING, "Mismatch handling artifact is missing."),
        (max_open_error, "blocked_missing_max_open_positions", "max_open_positions_missing", SOURCE_MAX_OPEN_POSITIONS, "Max open positions artifact is missing."),
        (pre_blocks_error, "blocked_missing_pre_request_blocks", "pre_request_blocks_missing", SOURCE_PRE_REQUEST_BLOCKS, "Pre-request blocks artifact is missing."),
        (audit_error, "blocked_missing_audit_requirements", "audit_requirements_missing", SOURCE_AUDIT_REQUIREMENTS, "Audit requirements artifact is missing."),
    ]
    for error, status, code, filename, message in missing_checks:
        if error == "missing":
            add_warning(warnings, args=args, warning_code=code, message=message, source=source_dir / filename, blocking_warning=True)
            return status
    unreadable = [
        ("canonical_registry_unreadable", registry_error, args.canonical_registry),
        ("demo_execution_policy_unreadable", policy_error, args.demo_execution_policy),
        ("future_broker_state_reconciliation_manifest_unreadable", source_manifest_error, source_dir / SOURCE_MANIFEST),
        ("local_state_requirements_unreadable", local_state_error, source_dir / SOURCE_LOCAL_STATE_REQUIREMENTS),
        ("future_broker_reads_unreadable", broker_reads_error, source_dir / SOURCE_FUTURE_BROKER_READS),
        ("matching_fields_unreadable", matching_error, source_dir / SOURCE_MATCHING_FIELDS),
        ("reconciliation_statuses_unreadable", statuses_error, source_dir / SOURCE_RECONCILIATION_STATUSES),
        ("mismatch_handling_unreadable", mismatch_error, source_dir / SOURCE_MISMATCH_HANDLING),
        ("max_open_positions_unreadable", max_open_error, source_dir / SOURCE_MAX_OPEN_POSITIONS),
        ("pre_request_blocks_unreadable", pre_blocks_error, source_dir / SOURCE_PRE_REQUEST_BLOCKS),
        ("audit_requirements_unreadable", audit_error, source_dir / SOURCE_AUDIT_REQUIREMENTS),
    ]
    unreadable_errors = [item for item in unreadable if item[1] and item[1] != "missing"]
    if unreadable_errors:
        for code, error, source in unreadable_errors:
            add_warning(warnings, args=args, warning_code=code, message=f"Input artifact is unreadable: {error}", source=source, blocking_warning=True)
        return "blocked_unreadable_input"
    if not canonical_ok:
        add_warning(warnings, args=args, warning_code="noncanonical_candidate", message="Canonical registry/policy does not match fixed candidate spread15 max-open-one boundaries.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_noncanonical_candidate"
    if not policy_ok_without_manual:
        add_warning(warnings, args=args, warning_code="noncanonical_demo_execution_policy", message="Demo execution policy does not match risk/margin/no-request boundaries.", source=args.demo_execution_policy, blocking_warning=True)
        return "blocked_noncanonical_demo_execution_policy"
    if not manual_required:
        add_warning(warnings, args=args, warning_code="manual_approval_not_required_by_policy", message="Demo execution policy does not require manual approval before any future demo order.", source=args.demo_execution_policy, blocking_warning=True)
        return "blocked_manual_approval_not_required_by_policy"
    source_status = str(source_manifest.get("plan_status") or "")
    if not source_status_acceptable(source_status):
        add_warning(warnings, args=args, warning_code="unacceptable_future_broker_state_reconciliation_status", message=f"Future broker/local reconciliation plan status is not acceptable: {source_status}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_unacceptable_future_broker_state_reconciliation_status"
    if not boundary_ok:
        add_warning(warnings, args=args, warning_code="unsafe_future_broker_state_reconciliation_boundary", message=f"Future broker/local reconciliation boundary failed fields: {boundary_failures}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_unsafe_future_broker_state_reconciliation_boundary"
    return status_from_source(source_manifest)


def main_rows(args: argparse.Namespace, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    source = Path(args.future_broker_state_reconciliation_check_plan_dir) / SOURCE_MANIFEST
    items = [
        ("source_artifact_chain", ctx["source_plan_status"], "acceptable future broker/local reconciliation plan status", "future_broker_reconciliation_source_accepted", "plan remains artifact-only"),
        ("source_nature", ctx["source_nature"], "synthetic_fixture or live_data_shadow_signal", "source_nature_identified", "fixture source blocks future request construction"),
        ("request_construction_allowed_now", False, False, "request_construction_not_allowed_now", "planning-only"),
        ("upstream_evidence_requirements", len(UPSTREAM_EVIDENCE), "upstream evidence requirements defined", "upstream_evidence_defined", "all future-only"),
        ("readiness_prerequisites", len(PREREQUISITES), "readiness prerequisites defined", "prerequisites_defined", "all future-only"),
        ("readiness_gates", len(READINESS_GATES), "readiness gates defined", "readiness_gates_defined", "not evaluated now"),
        ("future_field_descriptors", len(FUTURE_FIELD_DESCRIPTORS), "non-actionable descriptors defined", "future_field_descriptors_defined", "not broker payload fields"),
        ("block_conditions", len(BLOCK_CONDITIONS), "block conditions defined", "block_conditions_defined", "blocks before any future request construction"),
        ("no_request_boundary", len(NO_REQUEST_BOUNDARIES), "no-request boundaries confirmed", "no_request_boundary_confirmed", "no payload/request/object constructed"),
        ("audit_requirements", len(AUDIT_REQUIREMENTS), "future audit requirements defined", "audit_requirements_defined", "must record no request/no execution"),
    ]
    return [
        {
            "run_id": args.run_id,
            "plan_area": area,
            "plan_status": ctx["plan_status"],
            "artifact_status": "planned",
            "source_path": source,
            "observed_value": observed,
            "expected_value": expected,
            "evidence_label": evidence,
            "caveat": caveat,
            "warning_code": "",
            "blocking_warning": False,
        }
        for area, observed, expected, evidence, caveat in items
    ]


def upstream_evidence_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "evidence_area": area,
            "required_evidence": required,
            "required_before_future_request_construction": True,
            "fixture_source_blocks": area == "source_nature" or "fixture" in required,
            "caveat": "future evidence only; not evaluated by this planner",
        }
        for area, required in UPSTREAM_EVIDENCE
    ]


def prerequisite_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "prerequisite_name": name,
            "expected_condition": "must be satisfied before any future request construction module",
            "blocking_if_missing": True,
            "source_or_future_artifact": "future readiness evidence artifact",
            "caveat": "planning-only",
        }
        for name in PREREQUISITES
    ]


def readiness_gate_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "gate_name": name,
            "expected_condition": "pass before future request construction",
            "blocking_if_failed": True,
            "evaluated_now": False,
            "caveat": "gate definition only; no execution readiness decision is made",
        }
        for name in READINESS_GATES
    ]


def future_field_descriptor_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for descriptor in FUTURE_FIELD_DESCRIPTORS:
        rows.append(
            {
                "run_id": args.run_id,
                "descriptor_name": descriptor,
                "semantic_role": "non_actionable_future_request_construction_input_descriptor",
                "future_field_only": True,
                "not_constructed": True,
                "broker_request_field": False,
                "broker_payload_ready": False,
                "value_source_required": True,
                "executable_now": False,
                "caveat": "descriptor only; not a broker payload key and not executable",
            }
        )
    return rows


def block_condition_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "block_condition": condition,
            "future_block_response": "block_before_future_request_construction",
            "blocking": True,
            "before_future_request_construction": True,
            "caveat": "future request construction remains unavailable when condition is present",
        }
        for condition in BLOCK_CONDITIONS
    ]


def no_request_boundary_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "boundary_name": name,
            "observed_value": value,
            "expected_value": value,
            "boundary_confirmed": True,
            "caveat": "planning-only no-request boundary",
        }
        for name, value in NO_REQUEST_BOUNDARIES
    ]


def audit_requirement_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "audit_area": area,
            "required_audit_record": record,
            "required_timing": "future_request_construction_readiness_check",
            "immutable": True,
            "caveat": "future audit record only; no request construction is performed here",
        }
        for area, record in AUDIT_REQUIREMENTS
    ]


def manifest_data(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    ctx: dict[str, Any],
    outputs: dict[str, Path],
    upstream: list[dict[str, Any]],
    prerequisites: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    descriptors: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    no_request: list[dict[str, Any]],
    audit: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "created_at_utc": utc_now_text(),
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "output_files": {key: str(value) for key, value in outputs.items()},
        "plan_status": ctx["plan_status"],
        "plan_actionable": False,
        "source_nature": ctx["source_nature"],
        "candidate_id": EXPECTED_CANDIDATE_ID,
        "symbol": EXPECTED_SYMBOL,
        "timeframe": EXPECTED_TIMEFRAME,
        "direction": EXPECTED_DIRECTION,
        "session_regime": EXPECTED_SESSION,
        "spread_unit": EXPECTED_SPREAD_UNIT,
        "max_spread_points": EXPECTED_MAX_SPREAD_POINTS,
        "max_open_positions": EXPECTED_MAX_OPEN_POSITIONS,
        "horizon_bars": EXPECTED_HORIZON_BARS,
        "same_bar_policy": EXPECTED_SAME_BAR_POLICY,
        "future_broker_state_reconciliation_check_plan_dir": str(args.future_broker_state_reconciliation_check_plan_dir),
        "future_broker_state_reconciliation_check_plan_status": ctx["source_plan_status"],
        "future_state_json": str(args.future_state_json),
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
        "upstream_evidence_row_count": len(upstream),
        "prerequisite_row_count": len(prerequisites),
        "readiness_gate_row_count": len(gates),
        "future_field_descriptor_row_count": len(descriptors),
        "block_condition_row_count": len(blocks),
        "no_request_boundary_row_count": len(no_request),
        "audit_requirement_row_count": len(audit),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "recommended_next_step": ctx["recommended_next_step"],
        "no_mt5_import_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_api_query_performed": True,
        "no_db_query_performed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_future_state_json_read_performed": True,
        "no_future_state_json_write_performed": True,
        "no_order_request_constructed": True,
        "no_broker_payload_constructed": True,
        "no_order_object_constructed": True,
        "no_order_execution_performed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }


def write_report(path: Path, *, ctx: dict[str, Any], args: argparse.Namespace, warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Future Request Construction Readiness Plan",
        "",
        "Artifact-only future request construction readiness planning.",
        "No MT5 import or connection was performed.",
        "No broker/API/account/symbol query was performed.",
        "No database query or mutation was performed.",
        "No future state JSON was read or written.",
        "No child script was executed.",
        "No broker request dictionary, broker payload, or executable order object was constructed.",
        "No order execution, order check, or order calculation was performed.",
        "No positions, orders, or history reads were performed.",
        "No scheduler, loop, daemon, or background task was added.",
        "No demo approval, trading decision, or candidate-quality final decision was made.",
        "",
        "## Source Summary",
        "",
        f"- future_broker_state_reconciliation_check_plan_dir: `{args.future_broker_state_reconciliation_check_plan_dir}`",
        f"- future_broker_state_reconciliation_check_plan_status: `{ctx['source_plan_status']}`",
        f"- source_nature: `{ctx['source_nature']}`",
        f"- plan_status: `{ctx['plan_status']}`",
        f"- future_state_json: `{args.future_state_json}`",
        "",
        "## Upstream Evidence Requirements",
        "",
        "Future request construction readiness requires non-fixture live-data would_signal evidence, broker-safe margin validation below hard cap, duplicate protection, explicit non-stale manual approval, inactive kill-switch, clean broker/local reconciliation, audit logging, spread within policy, demo account evidence, and source_nature not synthetic_fixture.",
        "",
        "## Readiness Prerequisites And Gates",
        "",
        "Future prerequisites and gates are defined for identity, policy, live signal, would-signal review, risk/volume, margin, state reconciliation, duplicate protection, manual approval, kill-switch, max-open-position, stale-signal, audit, no scheduler, and no background execution.",
        "",
        "## Future Field Descriptors",
        "",
        "Future field descriptors are non-actionable planning rows. Every descriptor is marked future_field_only, not_constructed, broker_request_field=false, broker_payload_ready=false, value_source_required=true, and executable_now=false.",
        "The descriptors do not create a broker-ready dictionary and do not use executable broker payload keys.",
        "",
        "## Block Conditions",
        "",
        "Fixture source, missing live-data would_signal, stale/missing approval, active kill-switch, duplicate failure, unclean reconciliation, missing or excessive margin, spread/risk/max-open breaches, broker/local open or pending state, repeated idempotency key, stale signal, audit gaps, and unsafe policy flags block before any future request construction.",
        "",
        "## No-Request Boundary",
        "",
        "request_construction_allowed_now=false, broker_request_constructed=false, broker_payload_constructed=false, order_object_constructed=false, order_send_allowed=false, order_check_allowed=false, order_execution_allowed=false, and demo_approval_performed=false.",
        "",
        "## Audit Requirements",
        "",
        "Future readiness checks must record upstream run IDs, gate results, block condition results, source_nature, manual approval status, reconciliation status, idempotency_key, and no-request/no-order evidence.",
        "",
        "## Recommended Next Step",
        "",
        f"`{ctx['recommended_next_step']}`",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        lines.extend(f"- {row['warning_code']}: {row['message']}" for row in warnings)
    else:
        lines.append("- none")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / str(args.run_id)
    outputs = ensure_outputs_writable(output_dir, bool(args.overwrite))
    warnings: list[dict[str, Any]] = []

    registry, registry_error = read_json(Path(args.canonical_registry))
    policy, policy_error = read_json(Path(args.demo_execution_policy))
    source_dir = Path(args.future_broker_state_reconciliation_check_plan_dir)
    source_manifest, source_manifest_error = read_json(source_dir / SOURCE_MANIFEST)
    _report, report_error = read_text(source_dir / SOURCE_REPORT)
    _main_rows, main_error = read_csv_rows(source_dir / SOURCE_MAIN)
    _local_rows, local_state_error = read_csv_rows(source_dir / SOURCE_LOCAL_STATE_REQUIREMENTS)
    _broker_rows, broker_reads_error = read_csv_rows(source_dir / SOURCE_FUTURE_BROKER_READS)
    _matching_rows, matching_error = read_csv_rows(source_dir / SOURCE_MATCHING_FIELDS)
    _status_rows, statuses_error = read_csv_rows(source_dir / SOURCE_RECONCILIATION_STATUSES)
    _mismatch_rows, mismatch_error = read_csv_rows(source_dir / SOURCE_MISMATCH_HANDLING)
    _max_open_rows, max_open_error = read_csv_rows(source_dir / SOURCE_MAX_OPEN_POSITIONS)
    _pre_request_rows, pre_blocks_error = read_csv_rows(source_dir / SOURCE_PRE_REQUEST_BLOCKS)
    _audit_rows, audit_error = read_csv_rows(source_dir / SOURCE_AUDIT_REQUIREMENTS)
    source_warnings, source_warnings_error = read_csv_rows(source_dir / SOURCE_WARNINGS)
    if not source_warnings_error:
        warnings.extend(preserve_source_warnings(args, source_warnings, source_dir / SOURCE_WARNINGS))
    if report_error == "missing":
        add_warning(warnings, args=args, warning_code="source_report_missing", message="Source report is missing.", source=source_dir / SOURCE_REPORT, blocking_warning=False)
    if main_error == "missing":
        add_warning(warnings, args=args, warning_code="source_main_missing", message="Source main plan CSV is missing.", source=source_dir / SOURCE_MAIN, blocking_warning=False)

    canonical_ok = not registry_error and not policy_error and canonical_registry_valid(registry, policy)
    policy_ok_without_manual = not policy_error and execution_policy_valid_without_manual_gate(policy)
    manual_required = not policy_error and manual_approval_required(policy)
    boundary_ok, boundary_failures = source_boundary_valid(source_manifest)
    plan_status = determine_plan_status(
        args=args,
        registry_error=registry_error,
        policy_error=policy_error,
        source_manifest=source_manifest,
        source_manifest_error=source_manifest_error,
        local_state_error=local_state_error,
        broker_reads_error=broker_reads_error,
        matching_error=matching_error,
        statuses_error=statuses_error,
        mismatch_error=mismatch_error,
        max_open_error=max_open_error,
        pre_blocks_error=pre_blocks_error,
        audit_error=audit_error,
        canonical_ok=canonical_ok,
        policy_ok_without_manual=policy_ok_without_manual,
        manual_required=manual_required,
        boundary_ok=boundary_ok,
        boundary_failures=boundary_failures,
        warnings=warnings,
    )
    if source_manifest.get("source_nature") == "synthetic_fixture":
        add_warning(warnings, args=args, warning_code="fixture_only_source", message="Future broker/local reconciliation source is fixture-only and non-actionable.", source=source_dir / SOURCE_MANIFEST, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="request_construction_readiness_planning_only", message="Request construction readiness is planning-only; no request was constructed.", source="future_request_construction_readiness_plan", blocking_warning=False)
    add_warning(warnings, args=args, warning_code="future_field_descriptors_not_payload", message="Future field descriptors are not broker payload fields.", source="future_field_descriptors", blocking_warning=False)
    add_warning(warnings, args=args, warning_code="future_state_json_not_read_or_written", message="Future state JSON path is a target only and was not read or written.", source=args.future_state_json, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="positions_orders_reads_not_called", message="positions_get/orders_get are not called here.", source="source_future_broker_reads", blocking_warning=False)
    add_warning(warnings, args=args, warning_code="execution_remains_forbidden", message="Order execution and request construction remain forbidden.", source=args.demo_execution_policy, blocking_warning=False)

    ctx = {
        "plan_status": plan_status,
        "source_nature": source_manifest.get("source_nature", "unknown"),
        "source_plan_status": source_manifest.get("plan_status", ""),
        "recommended_next_step": recommended_next_step(plan_status),
    }
    upstream = upstream_evidence_rows(args)
    prerequisites = prerequisite_rows(args)
    gates = readiness_gate_rows(args)
    descriptors = future_field_descriptor_rows(args)
    blocks = block_condition_rows(args)
    no_request = no_request_boundary_rows(args)
    audit = audit_requirement_rows(args)
    write_csv(outputs["main"], main_rows(args, ctx), MAIN_FIELDNAMES)
    write_csv(outputs["upstream_evidence"], upstream, UPSTREAM_FIELDNAMES)
    write_csv(outputs["prerequisites"], prerequisites, PREREQUISITE_FIELDNAMES)
    write_csv(outputs["readiness_gates"], gates, READINESS_GATE_FIELDNAMES)
    write_csv(outputs["future_field_descriptors"], descriptors, FIELD_DESCRIPTOR_FIELDNAMES)
    write_csv(outputs["block_conditions"], blocks, BLOCK_CONDITION_FIELDNAMES)
    write_csv(outputs["no_request_boundary"], no_request, NO_REQUEST_FIELDNAMES)
    write_csv(outputs["audit_requirements"], audit, AUDIT_FIELDNAMES)
    write_csv(outputs["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(outputs["report"], ctx=ctx, args=args, warnings=warnings)
    write_json(
        outputs["manifest"],
        manifest_data(
            args=args,
            output_dir=output_dir,
            ctx=ctx,
            outputs=outputs,
            upstream=upstream,
            prerequisites=prerequisites,
            gates=gates,
            descriptors=descriptors,
            blocks=blocks,
            no_request=no_request,
            audit=audit,
            warnings=warnings,
        ),
    )
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only fixed-candidate future request construction readiness plan.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--future-broker-state-reconciliation-check-plan-dir", type=Path, default=DEFAULT_RECONCILIATION_PLAN_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_EXECUTION_POLICY)
    parser.add_argument("--future-state-json", type=Path, default=DEFAULT_FUTURE_STATE_JSON)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate future request construction readiness plan failed: {exc}")
        return 1
    print("Fixed-candidate future request construction readiness plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
