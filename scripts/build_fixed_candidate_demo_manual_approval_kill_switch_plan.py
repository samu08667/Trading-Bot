"""Build an artifact-only demo manual approval and kill-switch plan.

The plan defines future operator approval gates, hard stop conditions, warning
escalation, pre-execution blocks, audit requirements, and future state
transitions for the fixed candidate. It reads only existing local artifacts and
config files. It does not import/connect MT5, query broker/API or databases,
read/write future state, run child scripts, construct broker requests, execute
orders, approve demo use, or make trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_kill_switch_plan"
DEFAULT_DUPLICATE_PROTECTION_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_duplicate_protection_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_duplicate_protection_plan_fixture_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_manual_approval_kill_switch_plan"

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

SOURCE_MANIFEST = "fixed_candidate_demo_duplicate_protection_plan_manifest.json"
SOURCE_REPORT = "fixed_candidate_demo_duplicate_protection_plan_report.md"
SOURCE_MAIN = "fixed_candidate_demo_duplicate_protection_plan.csv"
SOURCE_SIGNAL_IDENTITY = "fixed_candidate_demo_duplicate_protection_plan_signal_identity.csv"
SOURCE_STATE_GATES = "fixed_candidate_demo_duplicate_protection_plan_state_gates.csv"
SOURCE_IDEMPOTENCY = "fixed_candidate_demo_duplicate_protection_plan_idempotency_checks.csv"
SOURCE_MAX_OPEN_POSITIONS = "fixed_candidate_demo_duplicate_protection_plan_max_open_positions.csv"
SOURCE_STALE_SIGNAL_POLICY = "fixed_candidate_demo_duplicate_protection_plan_stale_signal_policy.csv"
SOURCE_FUTURE_PRE_EXECUTION_CHECKS = "fixed_candidate_demo_duplicate_protection_plan_future_pre_execution_checks.csv"
SOURCE_WARNINGS = "fixed_candidate_demo_duplicate_protection_plan_warnings.csv"

OUTPUT_MAIN = "fixed_candidate_demo_manual_approval_kill_switch_plan.csv"
OUTPUT_MANUAL_APPROVAL_GATE = "fixed_candidate_demo_manual_approval_kill_switch_plan_manual_approval_gate.csv"
OUTPUT_OPERATOR_REVIEW_CHECKLIST = "fixed_candidate_demo_manual_approval_kill_switch_plan_operator_review_checklist.csv"
OUTPUT_KILL_SWITCH_RULES = "fixed_candidate_demo_manual_approval_kill_switch_plan_kill_switch_rules.csv"
OUTPUT_WARNING_ESCALATION = "fixed_candidate_demo_manual_approval_kill_switch_plan_warning_escalation.csv"
OUTPUT_PRE_EXECUTION_BLOCKS = "fixed_candidate_demo_manual_approval_kill_switch_plan_pre_execution_blocks.csv"
OUTPUT_AUDIT_REQUIREMENTS = "fixed_candidate_demo_manual_approval_kill_switch_plan_audit_requirements.csv"
OUTPUT_FUTURE_STATE_TRANSITIONS = "fixed_candidate_demo_manual_approval_kill_switch_plan_future_state_transitions.csv"
OUTPUT_REPORT = "fixed_candidate_demo_manual_approval_kill_switch_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_demo_manual_approval_kill_switch_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json"

ACCEPTABLE_DUPLICATE_PROTECTION_STATUSES = {
    "duplicate_protection_plan_fixture_only",
    "duplicate_protection_plan_available_no_order",
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

MANUAL_APPROVAL_STATUSES = (
    "not_requested",
    "pending_review",
    "approved_for_future_request_construction_only",
    "rejected",
    "expired",
    "revoked",
    "blocked_by_kill_switch",
    "blocked_by_stale_signal",
    "blocked_by_duplicate_protection",
    "blocked_by_state_reconciliation",
    "blocked_by_margin_policy",
    "blocked_by_spread_policy",
)

OPERATOR_REVIEW_ITEMS = (
    ("confirm_demo_account_only", "confirm demo account only"),
    ("confirm_no_real_money_mode", "confirm no real-money mode"),
    ("confirm_symbol_gbpusd", "confirm symbol = GBPUSD"),
    ("confirm_timeframe_m15", "confirm timeframe = M15"),
    ("confirm_direction_short", "confirm direction = short"),
    ("confirm_session_off_hours", "confirm session/regime = Off_hours"),
    ("confirm_spread_within_15_broker_points", "confirm spread <= 15 broker points"),
    ("confirm_live_data_no_order_signal", "confirm latest signal is live-data no-order, not fixture"),
    ("confirm_signal_not_stale", "confirm signal is not stale"),
    ("confirm_duplicate_protection_passed", "confirm duplicate protection passed in future module"),
    ("confirm_state_reconciliation_passed", "confirm state reconciliation passed in future module"),
    ("confirm_max_open_positions_one", "confirm max_open_positions = 1 is respected"),
    ("confirm_margin_below_hard_cap", "confirm broker-safe margin validation is available and below hard cap"),
    ("confirm_warning_threshold_reviewed", "confirm warning threshold breaches are reviewed"),
    ("confirm_short_tp_sl_geometry", "confirm TP/SL geometry is valid for short direction"),
    ("confirm_volume_within_risk_policy", "confirm intended volume remains within risk policy"),
    ("confirm_no_scheduler_loop_background", "confirm no scheduler/loop/background execution"),
    ("confirm_no_automated_approval", "confirm no automated approval"),
)

KILL_SWITCH_RULES = (
    "real_money_detected",
    "non_demo_account_detected",
    "order_execution_policy_false_or_missing",
    "manual_approval_missing",
    "manual_approval_expired",
    "manual_approval_revoked",
    "source_nature_is_synthetic_fixture",
    "stale_signal_detected",
    "duplicate_signal_detected",
    "idempotency_key_already_seen",
    "local_state_pending_or_open",
    "local_broker_state_mismatch",
    "max_open_positions_violation",
    "spread_above_policy",
    "margin_above_policy_cap",
    "risk_amount_above_policy_cap",
    "symbol_unavailable",
    "stop_or_tp_geometry_invalid",
    "broker_reconciliation_unavailable",
    "audit_logging_unavailable",
)

WARNING_ESCALATION_RULES = (
    ("margin_warning_threshold", "margin above warning threshold but below hard cap", "explicit manual warning acknowledgment in future module"),
    ("spread_near_max_threshold", "spread near max threshold", "explicit operator spread review"),
    ("stale_time_proximity", "signal approaching stale age", "explicit stale-time review"),
    ("fixture_only_source", "source nature is synthetic fixture", "keep non-actionable and block any future execution phase"),
    ("missing_noncritical_advisory_artifact", "missing advisory artifact", "warn without authorizing execution"),
)

PRE_EXECUTION_BLOCKS = (
    "missing_live_data_would_signal",
    "fixture_source",
    "missing_manual_approval",
    "stale_signal",
    "duplicate_protection_failure",
    "state_reconciliation_failure",
    "broker_reconciliation_unavailable",
    "margin_hard_cap_breach",
    "spread_policy_breach",
    "max_open_positions_breach",
    "missing_audit_log_path",
    "unsafe_policy_flag",
)

AUDIT_REQUIREMENTS = (
    ("approval_audit_before", "immutable audit rows before manual approval"),
    ("approval_audit_after", "immutable audit rows after manual approval"),
    ("operator_approval_timestamp", "operator approval timestamp"),
    ("operator_decision_label", "operator decision label"),
    ("signal_id", "signal_id"),
    ("idempotency_key", "idempotency_key"),
    ("source_nature", "source_nature"),
    ("kill_switch_checks", "all kill-switch checks"),
    ("warning_acknowledgments", "all warning acknowledgments"),
    ("approval_no_order_evidence", "approval did not execute an order"),
)

FUTURE_STATE_TRANSITIONS = (
    ("signal_seen", "pending_manual_review", "future signal becomes reviewable"),
    ("pending_manual_review", "manually_rejected", "operator rejects"),
    ("pending_manual_review", "approved_for_future_request_construction_only", "operator explicitly approves future request-construction phase only"),
    ("pending_manual_review", "expired", "signal becomes stale"),
    ("pending_manual_review", "blocked_by_kill_switch", "hard stop condition matched"),
    ("approved_for_future_request_construction_only", "revoked", "operator revokes"),
    ("approved_for_future_request_construction_only", "expired", "approval becomes stale"),
    ("approved_for_future_request_construction_only", "blocked_by_kill_switch", "hard stop condition matched after approval"),
)

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
MANUAL_GATE_FIELDNAMES = [
    "run_id",
    "gate_area",
    "gate_name",
    "future_manual_approval_status",
    "expected_condition",
    "blocking_if_failed",
    "approval_executes_order",
    "approval_constructs_request",
    "caveat",
]
OPERATOR_CHECKLIST_FIELDNAMES = [
    "run_id",
    "checklist_item",
    "expected_confirmation",
    "blocking_if_failed",
    "source_or_future_artifact",
    "caveat",
]
KILL_SWITCH_FIELDNAMES = [
    "run_id",
    "kill_switch_code",
    "trigger_condition",
    "future_action",
    "blocking",
    "manual_approval_can_override",
    "caveat",
]
WARNING_ESCALATION_FIELDNAMES = [
    "run_id",
    "warning_code",
    "escalation_condition",
    "required_future_acknowledgment",
    "blocking_if_unacknowledged",
    "caveat",
]
PRE_EXECUTION_BLOCK_FIELDNAMES = [
    "run_id",
    "block_code",
    "block_condition",
    "future_block_action",
    "blocking",
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
TRANSITION_FIELDNAMES = [
    "run_id",
    "from_state",
    "to_state",
    "future_trigger",
    "order_execution_performed",
    "request_construction_performed_by_transition",
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
        "manual_approval_gate": output_dir / OUTPUT_MANUAL_APPROVAL_GATE,
        "operator_review_checklist": output_dir / OUTPUT_OPERATOR_REVIEW_CHECKLIST,
        "kill_switch_rules": output_dir / OUTPUT_KILL_SWITCH_RULES,
        "warning_escalation": output_dir / OUTPUT_WARNING_ESCALATION,
        "pre_execution_blocks": output_dir / OUTPUT_PRE_EXECUTION_BLOCKS,
        "audit_requirements": output_dir / OUTPUT_AUDIT_REQUIREMENTS,
        "future_state_transitions": output_dir / OUTPUT_FUTURE_STATE_TRANSITIONS,
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
    return status in ACCEPTABLE_DUPLICATE_PROTECTION_STATUSES


def status_from_source(manifest: dict[str, Any]) -> str:
    if manifest.get("source_nature") == "synthetic_fixture":
        return "manual_approval_kill_switch_plan_fixture_only"
    return "manual_approval_kill_switch_plan_available_no_order"


def recommended_next_step(plan_status: str) -> str:
    if plan_status == "manual_approval_kill_switch_plan_fixture_only":
        return "continue_no_order_monitoring_or_build_future_broker_state_reconciliation_check_plan"
    if plan_status == "manual_approval_kill_switch_plan_available_no_order":
        return "build_fixed_candidate_demo_future_broker_state_reconciliation_check_plan"
    return "fix_manual_approval_kill_switch_plan_inputs"


def determine_plan_status(
    *,
    args: argparse.Namespace,
    registry_error: str,
    policy_error: str,
    source_manifest: dict[str, Any],
    source_manifest_error: str,
    signal_identity_error: str,
    state_gates_error: str,
    idempotency_error: str,
    max_open_error: str,
    stale_policy_error: str,
    future_checks_error: str,
    canonical_ok: bool,
    policy_ok_without_manual: bool,
    manual_required: bool,
    boundary_ok: bool,
    boundary_failures: list[str],
    warnings: list[dict[str, Any]],
) -> str:
    source_dir = Path(args.duplicate_protection_plan_dir)
    if source_manifest_error == "missing":
        add_warning(warnings, args=args, warning_code="duplicate_protection_manifest_missing", message="Duplicate protection plan manifest is missing.", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_missing_duplicate_protection_manifest"
    if signal_identity_error == "missing":
        add_warning(warnings, args=args, warning_code="signal_identity_missing", message="Duplicate protection signal identity artifact is missing.", source=source_dir / SOURCE_SIGNAL_IDENTITY, blocking_warning=True)
        return "blocked_missing_signal_identity"
    if state_gates_error == "missing":
        add_warning(warnings, args=args, warning_code="state_gates_missing", message="Duplicate protection state gates artifact is missing.", source=source_dir / SOURCE_STATE_GATES, blocking_warning=True)
        return "blocked_missing_state_gates"
    if idempotency_error == "missing":
        add_warning(warnings, args=args, warning_code="idempotency_checks_missing", message="Duplicate protection idempotency checks artifact is missing.", source=source_dir / SOURCE_IDEMPOTENCY, blocking_warning=True)
        return "blocked_missing_idempotency_checks"
    if max_open_error == "missing":
        add_warning(warnings, args=args, warning_code="max_open_positions_missing", message="Duplicate protection max-open-positions artifact is missing.", source=source_dir / SOURCE_MAX_OPEN_POSITIONS, blocking_warning=True)
        return "blocked_missing_max_open_positions"
    if stale_policy_error == "missing":
        add_warning(warnings, args=args, warning_code="stale_signal_policy_missing", message="Duplicate protection stale signal policy artifact is missing.", source=source_dir / SOURCE_STALE_SIGNAL_POLICY, blocking_warning=True)
        return "blocked_missing_stale_signal_policy"
    if future_checks_error == "missing":
        add_warning(warnings, args=args, warning_code="future_pre_execution_checks_missing", message="Duplicate protection future pre-execution checks artifact is missing.", source=source_dir / SOURCE_FUTURE_PRE_EXECUTION_CHECKS, blocking_warning=True)
        return "blocked_missing_future_pre_execution_checks"
    unreadable = [
        ("canonical_registry_unreadable", registry_error, args.canonical_registry),
        ("demo_execution_policy_unreadable", policy_error, args.demo_execution_policy),
        ("duplicate_protection_manifest_unreadable", source_manifest_error, source_dir / SOURCE_MANIFEST),
        ("signal_identity_unreadable", signal_identity_error, source_dir / SOURCE_SIGNAL_IDENTITY),
        ("state_gates_unreadable", state_gates_error, source_dir / SOURCE_STATE_GATES),
        ("idempotency_checks_unreadable", idempotency_error, source_dir / SOURCE_IDEMPOTENCY),
        ("max_open_positions_unreadable", max_open_error, source_dir / SOURCE_MAX_OPEN_POSITIONS),
        ("stale_signal_policy_unreadable", stale_policy_error, source_dir / SOURCE_STALE_SIGNAL_POLICY),
        ("future_pre_execution_checks_unreadable", future_checks_error, source_dir / SOURCE_FUTURE_PRE_EXECUTION_CHECKS),
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
        add_warning(warnings, args=args, warning_code="noncanonical_demo_execution_policy", message="Demo execution policy does not match risk/margin/no-order boundaries.", source=args.demo_execution_policy, blocking_warning=True)
        return "blocked_noncanonical_demo_execution_policy"
    if not manual_required:
        add_warning(warnings, args=args, warning_code="manual_approval_not_required_by_policy", message="Demo execution policy does not require manual approval before any future demo order.", source=args.demo_execution_policy, blocking_warning=True)
        return "blocked_manual_approval_not_required_by_policy"
    source_status = str(source_manifest.get("plan_status") or "")
    if not source_status_acceptable(source_status):
        add_warning(warnings, args=args, warning_code="unacceptable_duplicate_protection_status", message=f"Duplicate protection plan status is not acceptable: {source_status}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_unacceptable_duplicate_protection_status"
    if not boundary_ok:
        add_warning(warnings, args=args, warning_code="unsafe_duplicate_protection_boundary", message=f"Duplicate protection boundary failed fields: {boundary_failures}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_unsafe_duplicate_protection_boundary"
    return status_from_source(source_manifest)


def main_rows(args: argparse.Namespace, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    source = Path(args.duplicate_protection_plan_dir) / SOURCE_MANIFEST
    items = [
        ("source_artifact_chain", ctx["duplicate_protection_plan_status"], "acceptable duplicate protection plan status", "duplicate_protection_source_accepted", "plan remains artifact-only"),
        ("source_nature", ctx["source_nature"], "synthetic_fixture or live_data_shadow_signal", "source_nature_identified", "fixture source remains non-actionable"),
        ("manual_approval_gate", "required", "explicit approval required before future request-construction phase", "manual_approval_required", "approval does not execute orders"),
        ("manual_approval_statuses", ";".join(MANUAL_APPROVAL_STATUSES), "future statuses defined", "manual_approval_statuses_defined", "planning-only"),
        ("operator_review_checklist", len(OPERATOR_REVIEW_ITEMS), "operator checks defined", "operator_review_required", "future operator evidence required"),
        ("kill_switch_rules", len(KILL_SWITCH_RULES), "hard stop rules defined", "kill_switch_rules_defined", "manual approval cannot override"),
        ("warning_escalation", len(WARNING_ESCALATION_RULES), "warning escalation rules defined", "warning_escalation_defined", "future acknowledgments required"),
        ("pre_execution_blocks", len(PRE_EXECUTION_BLOCKS), "pre-execution blocks defined", "pre_execution_blocks_defined", "blocks occur before any future request construction"),
        ("audit_requirements", len(AUDIT_REQUIREMENTS), "audit requirements defined", "audit_requirements_defined", "approval audit must show no order execution"),
        ("future_state_transitions", len(FUTURE_STATE_TRANSITIONS), "future state transition plan defined", "future_state_transitions_defined", "no transition executes an order"),
        ("no_order_boundary", True, True, "no_order_boundary_confirmed", "no order path in this module"),
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


def manual_approval_gate_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = [
        {
            "run_id": args.run_id,
            "gate_area": "manual_approval_rule",
            "gate_name": "explicit_manual_approval_required",
            "future_manual_approval_status": "",
            "expected_condition": "manual approval is required before any future demo order attempt",
            "blocking_if_failed": True,
            "approval_executes_order": False,
            "approval_constructs_request": False,
            "caveat": "planning-only; no approval workflow implemented here",
        },
        {
            "run_id": args.run_id,
            "gate_area": "manual_approval_rule",
            "gate_name": "approval_tied_to_signal_identity",
            "future_manual_approval_status": "",
            "expected_condition": "approval must be tied to one signal_id and one idempotency_key",
            "blocking_if_failed": True,
            "approval_executes_order": False,
            "approval_constructs_request": False,
            "caveat": "approval cannot cover multiple signals",
        },
        {
            "run_id": args.run_id,
            "gate_area": "manual_approval_rule",
            "gate_name": "approval_expires_if_signal_stale",
            "future_manual_approval_status": "",
            "expected_condition": "approval must expire if signal becomes stale",
            "blocking_if_failed": True,
            "approval_executes_order": False,
            "approval_constructs_request": False,
            "caveat": "horizon_bars=10 and M15 signal identity apply",
        },
        {
            "run_id": args.run_id,
            "gate_area": "manual_approval_rule",
            "gate_name": "approval_cannot_override_blocks",
            "future_manual_approval_status": "",
            "expected_condition": "approval must not override kill-switch, spread, margin, risk, duplicate, or state failures",
            "blocking_if_failed": True,
            "approval_executes_order": False,
            "approval_constructs_request": False,
            "caveat": "manual approval is weaker than all safety blocks",
        },
    ]
    for status in MANUAL_APPROVAL_STATUSES:
        rows.append(
            {
                "run_id": args.run_id,
                "gate_area": "manual_approval_status",
                "gate_name": status,
                "future_manual_approval_status": status,
                "expected_condition": "future manual approval workflow may use this status",
                "blocking_if_failed": status.startswith("blocked_") or status in {"expired", "revoked"},
                "approval_executes_order": False,
                "approval_constructs_request": status == "approved_for_future_request_construction_only",
                "caveat": "status is planning-only and does not authorize or perform execution",
            }
        )
    return rows


def operator_review_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "checklist_item": item,
            "expected_confirmation": confirmation,
            "blocking_if_failed": True,
            "source_or_future_artifact": "future manual approval audit artifact",
            "caveat": "operator review is future-only and no approval is performed here",
        }
        for item, confirmation in OPERATOR_REVIEW_ITEMS
    ]


def kill_switch_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "kill_switch_code": code,
            "trigger_condition": code,
            "future_action": "block_future_request_construction_and_execution_phase",
            "blocking": True,
            "manual_approval_can_override": False,
            "caveat": "hard block rule; planning-only in this module",
        }
        for code in KILL_SWITCH_RULES
    ]


def warning_escalation_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "warning_code": code,
            "escalation_condition": condition,
            "required_future_acknowledgment": acknowledgment,
            "blocking_if_unacknowledged": True,
            "caveat": "future module must record warning acknowledgment before any later phase",
        }
        for code, condition, acknowledgment in WARNING_ESCALATION_RULES
    ]


def pre_execution_block_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "block_code": code,
            "block_condition": code,
            "future_block_action": "block_before_any_future_request_construction",
            "blocking": True,
            "caveat": "pre-execution block is planned before any future request construction",
        }
        for code in PRE_EXECUTION_BLOCKS
    ]


def audit_requirement_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for area, record in AUDIT_REQUIREMENTS:
        rows.append(
            {
                "run_id": args.run_id,
                "audit_area": area,
                "required_audit_record": record,
                "required_timing": "before_and_after_manual_approval" if "approval" in area else "at_manual_review",
                "immutable": True,
                "caveat": "future audit record only; no approval or order path here",
            }
        )
    return rows


def future_state_transition_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "from_state": from_state,
            "to_state": to_state,
            "future_trigger": trigger,
            "order_execution_performed": False,
            "request_construction_performed_by_transition": False,
            "caveat": "state transition planning only; future state JSON is not read or written here",
        }
        for from_state, to_state, trigger in FUTURE_STATE_TRANSITIONS
    ]


def manifest_data(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    ctx: dict[str, Any],
    outputs: dict[str, Path],
    manual_gate: list[dict[str, Any]],
    operator_review: list[dict[str, Any]],
    kill_switch: list[dict[str, Any]],
    warning_escalation: list[dict[str, Any]],
    pre_execution_blocks: list[dict[str, Any]],
    audit_requirements: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
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
        "duplicate_protection_plan_dir": str(args.duplicate_protection_plan_dir),
        "duplicate_protection_plan_status": ctx["duplicate_protection_plan_status"],
        "future_state_json": str(args.future_state_json),
        "future_state_json_read_or_written": False,
        "manual_approval_required_before_any_future_demo_order": True,
        "manual_approval_gate_row_count": len(manual_gate),
        "operator_review_checklist_row_count": len(operator_review),
        "kill_switch_rule_row_count": len(kill_switch),
        "warning_escalation_row_count": len(warning_escalation),
        "pre_execution_block_row_count": len(pre_execution_blocks),
        "audit_requirement_row_count": len(audit_requirements),
        "future_state_transition_row_count": len(transitions),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "recommended_next_step": ctx["recommended_next_step"],
        "no_mt5_import_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_api_query_performed": True,
        "no_db_query_performed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_order_request_constructed": True,
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
        "manual_approval_performed": False,
        "kill_switch_executed": False,
    }


def write_report(path: Path, *, ctx: dict[str, Any], args: argparse.Namespace, warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Manual Approval And Kill-Switch Plan",
        "",
        "Artifact-only manual approval and kill-switch planning.",
        "No MT5 import or connection was performed.",
        "No broker/API/account/symbol query was performed.",
        "No database query or mutation was performed.",
        "No future state JSON was read or written.",
        "No child script was executed.",
        "No broker request dictionary or order object was constructed.",
        "No order execution, order check, or order calculation was performed.",
        "No positions, orders, or history reads were performed.",
        "No scheduler, loop, daemon, or background task was added.",
        "No manual approval was performed.",
        "No demo approval, trading decision, or candidate-quality final decision was made.",
        "",
        "## Source Summary",
        "",
        f"- duplicate_protection_plan_dir: `{args.duplicate_protection_plan_dir}`",
        f"- duplicate_protection_plan_status: `{ctx['duplicate_protection_plan_status']}`",
        f"- source_nature: `{ctx['source_nature']}`",
        f"- plan_status: `{ctx['plan_status']}`",
        f"- future_state_json: `{args.future_state_json}`",
        "",
        "## Manual Approval Gate",
        "",
        "Future manual approval must be explicit, tied to one signal_id and one idempotency_key, expire if stale, and must not override kill-switch, spread, margin, risk, duplicate, or state failures.",
        "Manual approval by itself must not construct a broker request or execute an order.",
        "",
        "## Operator Review Checklist",
        "",
        "Future operator review must confirm demo-only mode, GBPUSD/M15/short/Off_hours identity, spread <= 15 broker points, live-data no-order signal source, freshness, duplicate and state checks, max_open_positions=1, margin policy, TP/SL geometry, risk policy, no scheduling loop, and no automated approval.",
        "",
        "## Kill-Switch Rules",
        "",
        "Any hard kill-switch condition blocks future request construction and any future execution phase. Manual approval cannot override a kill-switch.",
        "",
        "## Warning Escalation",
        "",
        "Margin warning threshold, near-threshold spread, stale-time proximity, fixture-only source, and missing advisory artifacts require future warning handling without authorizing execution.",
        "",
        "## Pre-Execution Blocks",
        "",
        "Future modules must block before request construction for missing live-data would_signal, fixture source, missing approval, stale signal, duplicate/state/reconciliation failures, hard cap breaches, spread/max-open/policy failures, and missing audit path.",
        "",
        "## Audit Requirements",
        "",
        "Future modules must write immutable audit rows before and after approval, including operator timestamp, decision label, signal_id, idempotency_key, source_nature, kill-switch checks, warning acknowledgments, and proof approval did not execute an order.",
        "",
        "## Future State Transitions",
        "",
        "Future state transitions are planning-only. No transition executes an order or constructs a request by itself.",
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
    source_dir = Path(args.duplicate_protection_plan_dir)
    source_manifest, source_manifest_error = read_json(source_dir / SOURCE_MANIFEST)
    _report, report_error = read_text(source_dir / SOURCE_REPORT)
    _main_rows, main_error = read_csv_rows(source_dir / SOURCE_MAIN)
    _signal_identity_rows, signal_identity_error = read_csv_rows(source_dir / SOURCE_SIGNAL_IDENTITY)
    _state_gates_rows, state_gates_error = read_csv_rows(source_dir / SOURCE_STATE_GATES)
    _idempotency_rows, idempotency_error = read_csv_rows(source_dir / SOURCE_IDEMPOTENCY)
    _max_open_rows, max_open_error = read_csv_rows(source_dir / SOURCE_MAX_OPEN_POSITIONS)
    _stale_policy_rows, stale_policy_error = read_csv_rows(source_dir / SOURCE_STALE_SIGNAL_POLICY)
    _future_checks_rows, future_checks_error = read_csv_rows(source_dir / SOURCE_FUTURE_PRE_EXECUTION_CHECKS)
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
        signal_identity_error=signal_identity_error,
        state_gates_error=state_gates_error,
        idempotency_error=idempotency_error,
        max_open_error=max_open_error,
        stale_policy_error=stale_policy_error,
        future_checks_error=future_checks_error,
        canonical_ok=canonical_ok,
        policy_ok_without_manual=policy_ok_without_manual,
        manual_required=manual_required,
        boundary_ok=boundary_ok,
        boundary_failures=boundary_failures,
        warnings=warnings,
    )
    if source_manifest.get("source_nature") == "synthetic_fixture":
        add_warning(warnings, args=args, warning_code="fixture_only_source", message="Duplicate protection source is fixture-only and non-actionable.", source=source_dir / SOURCE_MANIFEST, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="manual_approval_planning_only", message="Manual approval is planning-only; no approval workflow was executed.", source="manual_approval_plan", blocking_warning=False)
    add_warning(warnings, args=args, warning_code="kill_switch_planning_only", message="Kill-switch rules are planning-only and not executed by this module.", source="kill_switch_plan", blocking_warning=False)
    add_warning(warnings, args=args, warning_code="future_state_json_not_read_or_written", message="Future state JSON path is a target only and was not read or written.", source=args.future_state_json, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="future_broker_reads_not_performed", message="Future broker reads are not performed by this module.", source=source_dir / SOURCE_FUTURE_PRE_EXECUTION_CHECKS, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="execution_remains_forbidden", message="Order execution and order request construction remain forbidden.", source=args.demo_execution_policy, blocking_warning=False)

    ctx = {
        "plan_status": plan_status,
        "source_nature": source_manifest.get("source_nature", "unknown"),
        "duplicate_protection_plan_status": source_manifest.get("plan_status", ""),
        "recommended_next_step": recommended_next_step(plan_status),
    }
    manual_gate = manual_approval_gate_rows(args)
    operator_review = operator_review_rows(args)
    kill_switch = kill_switch_rows(args)
    warning_escalation = warning_escalation_rows(args)
    pre_execution_blocks = pre_execution_block_rows(args)
    audit_requirements = audit_requirement_rows(args)
    transitions = future_state_transition_rows(args)
    write_csv(outputs["main"], main_rows(args, ctx), MAIN_FIELDNAMES)
    write_csv(outputs["manual_approval_gate"], manual_gate, MANUAL_GATE_FIELDNAMES)
    write_csv(outputs["operator_review_checklist"], operator_review, OPERATOR_CHECKLIST_FIELDNAMES)
    write_csv(outputs["kill_switch_rules"], kill_switch, KILL_SWITCH_FIELDNAMES)
    write_csv(outputs["warning_escalation"], warning_escalation, WARNING_ESCALATION_FIELDNAMES)
    write_csv(outputs["pre_execution_blocks"], pre_execution_blocks, PRE_EXECUTION_BLOCK_FIELDNAMES)
    write_csv(outputs["audit_requirements"], audit_requirements, AUDIT_FIELDNAMES)
    write_csv(outputs["future_state_transitions"], transitions, TRANSITION_FIELDNAMES)
    write_csv(outputs["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(outputs["report"], ctx=ctx, args=args, warnings=warnings)
    write_json(
        outputs["manifest"],
        manifest_data(
            args=args,
            output_dir=output_dir,
            ctx=ctx,
            outputs=outputs,
            manual_gate=manual_gate,
            operator_review=operator_review,
            kill_switch=kill_switch,
            warning_escalation=warning_escalation,
            pre_execution_blocks=pre_execution_blocks,
            audit_requirements=audit_requirements,
            transitions=transitions,
            warnings=warnings,
        ),
    )
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only fixed-candidate demo manual approval and kill-switch plan.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--duplicate-protection-plan-dir", type=Path, default=DEFAULT_DUPLICATE_PROTECTION_PLAN_DIR)
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
        print(f"Fixed-candidate demo manual approval and kill-switch plan failed: {exc}")
        return 1
    print("Fixed-candidate demo manual approval and kill-switch plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
