"""Build an artifact-only future broker/local reconciliation check plan.

The plan defines how a future separate read-only reconciliation module should
compare local candidate state against broker state before any future request
construction phase. It reads only existing local artifacts and config files.
It does not import/connect MT5, query broker/API or databases, read/write
future state, run child scripts, construct broker requests, execute orders,
approve demo use, or make trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_future_broker_state_reconciliation_check_plan"
DEFAULT_MANUAL_APPROVAL_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_manual_approval_kill_switch_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_kill_switch_plan_fixture_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_future_broker_state_reconciliation_check_plan"

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

SOURCE_MANIFEST = "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json"
SOURCE_REPORT = "fixed_candidate_demo_manual_approval_kill_switch_plan_report.md"
SOURCE_MAIN = "fixed_candidate_demo_manual_approval_kill_switch_plan.csv"
SOURCE_MANUAL_APPROVAL_GATE = "fixed_candidate_demo_manual_approval_kill_switch_plan_manual_approval_gate.csv"
SOURCE_OPERATOR_REVIEW = "fixed_candidate_demo_manual_approval_kill_switch_plan_operator_review_checklist.csv"
SOURCE_KILL_SWITCH_RULES = "fixed_candidate_demo_manual_approval_kill_switch_plan_kill_switch_rules.csv"
SOURCE_WARNING_ESCALATION = "fixed_candidate_demo_manual_approval_kill_switch_plan_warning_escalation.csv"
SOURCE_PRE_EXECUTION_BLOCKS = "fixed_candidate_demo_manual_approval_kill_switch_plan_pre_execution_blocks.csv"
SOURCE_AUDIT_REQUIREMENTS = "fixed_candidate_demo_manual_approval_kill_switch_plan_audit_requirements.csv"
SOURCE_FUTURE_STATE_TRANSITIONS = "fixed_candidate_demo_manual_approval_kill_switch_plan_future_state_transitions.csv"
SOURCE_WARNINGS = "fixed_candidate_demo_manual_approval_kill_switch_plan_warnings.csv"

OUTPUT_MAIN = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan.csv"
OUTPUT_LOCAL_STATE_REQUIREMENTS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_local_state_requirements.csv"
OUTPUT_FUTURE_BROKER_READS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_future_broker_reads.csv"
OUTPUT_MATCHING_FIELDS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_matching_fields.csv"
OUTPUT_RECONCILIATION_STATUSES = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_reconciliation_statuses.csv"
OUTPUT_MISMATCH_HANDLING = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_mismatch_handling.csv"
OUTPUT_MAX_OPEN_POSITIONS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_max_open_positions.csv"
OUTPUT_PRE_REQUEST_BLOCKS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_pre_request_blocks.csv"
OUTPUT_AUDIT_REQUIREMENTS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_audit_requirements.csv"
OUTPUT_REPORT = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_demo_future_broker_state_reconciliation_check_plan_manifest.json"

ACCEPTABLE_MANUAL_APPROVAL_STATUSES = {
    "manual_approval_kill_switch_plan_fixture_only",
    "manual_approval_kill_switch_plan_available_no_order",
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

LOCAL_STATE_FIELDS = (
    "candidate_id",
    "symbol",
    "timeframe",
    "direction",
    "signal_time_server",
    "signal_id",
    "idempotency_key",
    "state_status",
    "intended_entry_reference_price",
    "intended_sl_price",
    "intended_tp_price",
    "intended_volume_lots",
    "broker_margin_estimate",
    "margin_validation_run_id",
    "manual_approval_status",
    "created_at",
    "updated_at",
)

FUTURE_BROKER_READS = (
    ("positions_get", "future broker/local state reconciliation check module only", "candidate/symbol/direction open-position count and fields", True, False),
    ("orders_get", "future broker/local state reconciliation check module only if pending-order detection is needed", "candidate/symbol/direction pending-order count if separately planned", True, False),
    ("history_orders_get", "forbidden unless separately planned", "historical order context remains unavailable in this plan", False, True),
    ("history_deals_get", "forbidden unless separately planned", "historical deal context remains unavailable in this plan", False, True),
    ("order_send", "forbidden", "no send path in reconciliation", False, True),
    ("order_check", "forbidden", "no validation path in reconciliation", False, True),
    ("order_calc_profit", "forbidden", "no calculation path in reconciliation", False, True),
)

MATCHING_FIELDS = (
    "symbol",
    "direction_or_side",
    "volume_lots",
    "entry_reference_price_or_broker_open_price_tolerance",
    "sl_price",
    "tp_price",
    "signal_time_server",
    "signal_id",
    "idempotency_key",
    "local_state_status",
    "manual_approval_status",
)

RECONCILIATION_STATUSES = (
    "reconciliation_not_run",
    "reconciliation_clean_no_local_no_broker",
    "reconciliation_clean_local_pending_no_broker",
    "reconciliation_clean_local_open_broker_open",
    "reconciliation_hold_local_open_broker_none",
    "reconciliation_hold_local_missing_broker_open",
    "reconciliation_hold_local_pending_broker_open",
    "reconciliation_hold_broker_pending_order_detected",
    "reconciliation_hold_duplicate_broker_positions",
    "reconciliation_hold_symbol_or_side_mismatch",
    "reconciliation_hold_volume_mismatch",
    "reconciliation_hold_sl_tp_mismatch",
    "reconciliation_hold_stale_local_state",
    "reconciliation_blocked_non_demo_account",
    "reconciliation_blocked_broker_read_unavailable",
)

MISMATCH_HANDLING = (
    ("local_open_broker_none", "local open but broker none", "reconciliation_hold"),
    ("broker_open_local_missing", "broker open but local missing", "reconciliation_hold"),
    ("local_pending_broker_open", "local pending but broker open", "reconciliation_hold"),
    ("broker_pending_order_detected", "broker pending order detected", "reconciliation_hold"),
    ("duplicate_broker_positions_detected", "duplicate broker positions detected", "reconciliation_hold"),
    ("symbol_or_side_mismatch", "symbol/side mismatch", "reconciliation_hold"),
    ("volume_mismatch", "volume mismatch", "reconciliation_hold"),
    ("sl_tp_mismatch", "SL/TP mismatch", "reconciliation_hold"),
    ("stale_local_state", "stale local state", "reconciliation_hold_or_stale_state_blocked"),
)

MAX_OPEN_POLICIES = (
    ("future_local_open_count", 0, "future local state", "must be 0 before any future request construction"),
    ("future_broker_open_position_count", 0, "future broker reconciliation module", "must be 0 for candidate/symbol/direction before any future request construction"),
    ("future_broker_pending_order_count", 0, "future broker reconciliation module if separately planned", "must be 0 for candidate/symbol/direction before any future request construction"),
    ("unknown_count", "known", "future local state and future broker reconciliation", "if any count is unknown, block"),
    ("local_broker_count_match", "match", "future local state and future broker reconciliation", "if counts disagree, reconciliation_hold"),
    ("hedging_workaround", "not_allowed", "future policy", "no hedging workaround"),
    ("netting_workaround", "not_allowed", "future policy", "no netting workaround"),
    ("second_trade_pending_open_unknown", "not_allowed", "future local and broker state", "no second trade while pending/open/unknown"),
)

PRE_REQUEST_BLOCKS = (
    "reconciliation_not_run",
    "reconciliation_hold_status",
    "broker_read_unavailable",
    "non_demo_account",
    "local_state_malformed",
    "local_broker_mismatch",
    "local_pending_or_open_state",
    "broker_open_position_exists",
    "broker_pending_order_exists",
    "max_open_positions_breach",
    "missing_manual_approval",
    "expired_manual_approval",
    "stale_signal",
    "duplicate_signal_or_idempotency_failure",
    "kill_switch_active",
)

AUDIT_REQUIREMENTS = (
    ("timestamp", "future reconciliation timestamp"),
    ("account_mode_label", "account mode label"),
    ("symbol", "symbol"),
    ("local_state_digest", "local state hash or stable digest"),
    ("broker_position_count", "broker position count"),
    ("broker_order_count", "broker order count if orders_get is used"),
    ("matching_fields_reviewed", "matching fields reviewed"),
    ("reconciliation_status", "reconciliation status"),
    ("mismatch_reason", "mismatch reason"),
    ("max_open_positions_result", "max_open_positions result"),
    ("no_order_request_constructed", "no order request constructed during reconciliation"),
    ("no_order_execution_performed", "no order execution performed during reconciliation"),
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
LOCAL_STATE_FIELDNAMES = [
    "run_id",
    "state_field",
    "required",
    "future_read_mode",
    "malformed_action",
    "missing_before_approval_action",
    "missing_after_broker_evidence_action",
    "caveat",
]
FUTURE_BROKER_READ_FIELDNAMES = [
    "run_id",
    "future_call_name",
    "allowed_scope",
    "planned_purpose",
    "future_only",
    "current_module_called",
    "forbidden_unless_separately_planned",
    "caveat",
]
MATCHING_FIELDNAMES = [
    "run_id",
    "matching_field",
    "local_source",
    "broker_source",
    "match_rule",
    "mismatch_action",
    "caveat",
]
RECONCILIATION_STATUS_FIELDNAMES = [
    "run_id",
    "reconciliation_status",
    "status_class",
    "allows_future_request_construction",
    "requires_reconciliation_hold",
    "caveat",
]
MISMATCH_FIELDNAMES = [
    "run_id",
    "mismatch_code",
    "mismatch_condition",
    "future_action",
    "allow_new_signal",
    "allow_future_request_construction",
    "caveat",
]
MAX_OPEN_FIELDNAMES = [
    "run_id",
    "max_open_area",
    "required_value",
    "future_count_source",
    "expected_condition",
    "future_action_if_failed",
    "blocking_if_failed",
    "caveat",
]
PRE_REQUEST_BLOCK_FIELDNAMES = [
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
        "local_state_requirements": output_dir / OUTPUT_LOCAL_STATE_REQUIREMENTS,
        "future_broker_reads": output_dir / OUTPUT_FUTURE_BROKER_READS,
        "matching_fields": output_dir / OUTPUT_MATCHING_FIELDS,
        "reconciliation_statuses": output_dir / OUTPUT_RECONCILIATION_STATUSES,
        "mismatch_handling": output_dir / OUTPUT_MISMATCH_HANDLING,
        "max_open_positions": output_dir / OUTPUT_MAX_OPEN_POSITIONS,
        "pre_request_blocks": output_dir / OUTPUT_PRE_REQUEST_BLOCKS,
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
    return status in ACCEPTABLE_MANUAL_APPROVAL_STATUSES


def status_from_source(manifest: dict[str, Any]) -> str:
    if manifest.get("source_nature") == "synthetic_fixture":
        return "future_broker_state_reconciliation_check_plan_fixture_only"
    return "future_broker_state_reconciliation_check_plan_available_no_order"


def recommended_next_step(plan_status: str) -> str:
    if plan_status == "future_broker_state_reconciliation_check_plan_fixture_only":
        return "continue_no_order_monitoring_or_build_future_request_construction_readiness_plan"
    if plan_status == "future_broker_state_reconciliation_check_plan_available_no_order":
        return "build_fixed_candidate_demo_future_request_construction_readiness_plan"
    return "fix_future_broker_state_reconciliation_check_plan_inputs"


def determine_plan_status(
    *,
    args: argparse.Namespace,
    registry_error: str,
    policy_error: str,
    source_manifest: dict[str, Any],
    source_manifest_error: str,
    manual_gate_error: str,
    kill_switch_error: str,
    pre_execution_error: str,
    audit_error: str,
    transitions_error: str,
    canonical_ok: bool,
    policy_ok_without_manual: bool,
    manual_required: bool,
    boundary_ok: bool,
    boundary_failures: list[str],
    warnings: list[dict[str, Any]],
) -> str:
    source_dir = Path(args.manual_approval_kill_switch_plan_dir)
    if source_manifest_error == "missing":
        add_warning(warnings, args=args, warning_code="manual_approval_kill_switch_manifest_missing", message="Manual approval / kill-switch plan manifest is missing.", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_missing_manual_approval_kill_switch_manifest"
    if manual_gate_error == "missing":
        add_warning(warnings, args=args, warning_code="manual_approval_gate_missing", message="Manual approval gate artifact is missing.", source=source_dir / SOURCE_MANUAL_APPROVAL_GATE, blocking_warning=True)
        return "blocked_missing_manual_approval_gate"
    if kill_switch_error == "missing":
        add_warning(warnings, args=args, warning_code="kill_switch_rules_missing", message="Kill-switch rules artifact is missing.", source=source_dir / SOURCE_KILL_SWITCH_RULES, blocking_warning=True)
        return "blocked_missing_kill_switch_rules"
    if pre_execution_error == "missing":
        add_warning(warnings, args=args, warning_code="pre_execution_blocks_missing", message="Pre-execution blocks artifact is missing.", source=source_dir / SOURCE_PRE_EXECUTION_BLOCKS, blocking_warning=True)
        return "blocked_missing_pre_execution_blocks"
    if audit_error == "missing":
        add_warning(warnings, args=args, warning_code="audit_requirements_missing", message="Audit requirements artifact is missing.", source=source_dir / SOURCE_AUDIT_REQUIREMENTS, blocking_warning=True)
        return "blocked_missing_audit_requirements"
    if transitions_error == "missing":
        add_warning(warnings, args=args, warning_code="future_state_transitions_missing", message="Future state transitions artifact is missing.", source=source_dir / SOURCE_FUTURE_STATE_TRANSITIONS, blocking_warning=True)
        return "blocked_missing_future_state_transitions"
    unreadable = [
        ("canonical_registry_unreadable", registry_error, args.canonical_registry),
        ("demo_execution_policy_unreadable", policy_error, args.demo_execution_policy),
        ("manual_approval_kill_switch_manifest_unreadable", source_manifest_error, source_dir / SOURCE_MANIFEST),
        ("manual_approval_gate_unreadable", manual_gate_error, source_dir / SOURCE_MANUAL_APPROVAL_GATE),
        ("kill_switch_rules_unreadable", kill_switch_error, source_dir / SOURCE_KILL_SWITCH_RULES),
        ("pre_execution_blocks_unreadable", pre_execution_error, source_dir / SOURCE_PRE_EXECUTION_BLOCKS),
        ("audit_requirements_unreadable", audit_error, source_dir / SOURCE_AUDIT_REQUIREMENTS),
        ("future_state_transitions_unreadable", transitions_error, source_dir / SOURCE_FUTURE_STATE_TRANSITIONS),
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
        add_warning(warnings, args=args, warning_code="unacceptable_manual_approval_kill_switch_status", message=f"Manual approval / kill-switch plan status is not acceptable: {source_status}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_unacceptable_manual_approval_kill_switch_status"
    if not boundary_ok:
        add_warning(warnings, args=args, warning_code="unsafe_manual_approval_kill_switch_boundary", message=f"Manual approval / kill-switch boundary failed fields: {boundary_failures}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_unsafe_manual_approval_kill_switch_boundary"
    return status_from_source(source_manifest)


def main_rows(args: argparse.Namespace, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    source = Path(args.manual_approval_kill_switch_plan_dir) / SOURCE_MANIFEST
    items = [
        ("source_artifact_chain", ctx["manual_approval_kill_switch_plan_status"], "acceptable manual approval / kill-switch plan status", "manual_approval_kill_switch_source_accepted", "plan remains artifact-only"),
        ("source_nature", ctx["source_nature"], "synthetic_fixture or live_data_shadow_signal", "source_nature_identified", "fixture source remains non-actionable"),
        ("future_local_state_requirements", len(LOCAL_STATE_FIELDS), "future local state fields defined", "future_local_state_requirements_defined", "future module only"),
        ("future_broker_read_policy", "positions_get/orders_get future-only", "broker reads planned only for separate future module", "future_broker_reads_planned", "not performed here"),
        ("history_read_policy", "forbidden unless separately planned", "history reads remain forbidden", "history_reads_forbidden", "not performed here"),
        ("matching_fields", len(MATCHING_FIELDS), "local-vs-broker matching fields defined", "matching_fields_defined", "future module only"),
        ("reconciliation_statuses", len(RECONCILIATION_STATUSES), "status taxonomy defined", "reconciliation_statuses_defined", "planning-only"),
        ("mismatch_handling", len(MISMATCH_HANDLING), "mismatch handling defined", "mismatch_handling_defined", "reconciliation_hold blocks future request path"),
        ("max_open_positions", EXPECTED_MAX_OPEN_POSITIONS, 1, "max_open_positions_one_required", "future local and broker counts must be zero"),
        ("pre_request_blocks", len(PRE_REQUEST_BLOCKS), "pre-request blocks defined", "pre_request_blocks_defined", "blocks before future request construction"),
        ("audit_requirements", len(AUDIT_REQUIREMENTS), "future reconciliation audit requirements defined", "audit_requirements_defined", "must record no request/no execution evidence"),
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


def local_state_requirement_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "state_field": field,
            "required": True,
            "future_read_mode": "read_only_before_explicit_state_transition",
            "malformed_action": "reconciliation_hold",
            "missing_before_approval_action": "treat_as_empty_only_before_approval_or_execution_attempt",
            "missing_after_broker_evidence_action": "block_with_reconciliation_hold",
            "caveat": "future_state_json is not read or written by this planning module",
        }
        for field in LOCAL_STATE_FIELDS
    ]


def future_broker_read_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for call_name, scope, purpose, future_only, forbidden in FUTURE_BROKER_READS:
        rows.append(
            {
                "run_id": args.run_id,
                "future_call_name": call_name,
                "allowed_scope": scope,
                "planned_purpose": purpose,
                "future_only": future_only,
                "current_module_called": False,
                "forbidden_unless_separately_planned": forbidden,
                "caveat": "planning-only; this module calls no broker/API functions",
            }
        )
    rows.extend(
        [
            {
                "run_id": args.run_id,
                "future_call_name": "broker_read_filter_account_mode",
                "allowed_scope": "future reconciliation module",
                "planned_purpose": "account must be demo",
                "future_only": True,
                "current_module_called": False,
                "forbidden_unless_separately_planned": False,
                "caveat": "non-demo account blocks reconciliation",
            },
            {
                "run_id": args.run_id,
                "future_call_name": "broker_read_filter_symbol_side",
                "allowed_scope": "future reconciliation module",
                "planned_purpose": "symbol must be GBPUSD and side must be short-compatible",
                "future_only": True,
                "current_module_called": False,
                "forbidden_unless_separately_planned": False,
                "caveat": "unrelated symbols cannot approve this candidate",
            },
            {
                "run_id": args.run_id,
                "future_call_name": "candidate_metadata_conservative_match",
                "allowed_scope": "future reconciliation module",
                "planned_purpose": "candidate_id matched through local metadata/audit/idempotency where available",
                "future_only": True,
                "current_module_called": False,
                "forbidden_unless_separately_planned": False,
                "caveat": "positions or orders without candidate metadata are treated conservatively",
            },
        ]
    )
    return rows


def matching_field_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for field in MATCHING_FIELDS:
        rows.append(
            {
                "run_id": args.run_id,
                "matching_field": field,
                "local_source": "future local state",
                "broker_source": "future broker read or local metadata when broker has no candidate metadata",
                "match_rule": "must match or be within explicitly planned tolerance",
                "mismatch_action": "reconciliation_hold",
                "caveat": "future module only; no broker or state read here",
            }
        )
    return rows


def reconciliation_status_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for status in RECONCILIATION_STATUSES:
        clean = status.startswith("reconciliation_clean")
        hold = "hold" in status
        blocked = "blocked" in status
        rows.append(
            {
                "run_id": args.run_id,
                "reconciliation_status": status,
                "status_class": "clean" if clean else "hold" if hold else "blocked" if blocked else "not_run",
                "allows_future_request_construction": clean and status != "reconciliation_clean_local_open_broker_open",
                "requires_reconciliation_hold": hold,
                "caveat": "clean local open/broker open is evidence for tracking, not permission for a second trade",
            }
        )
    return rows


def mismatch_handling_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "mismatch_code": code,
            "mismatch_condition": condition,
            "future_action": action,
            "allow_new_signal": False,
            "allow_future_request_construction": False,
            "caveat": "mismatch blocks new signal and future request path until resolved",
        }
        for code, condition, action in MISMATCH_HANDLING
    ]


def max_open_position_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "max_open_area": area,
            "required_value": required,
            "future_count_source": source,
            "expected_condition": condition,
            "future_action_if_failed": "block_or_reconciliation_hold",
            "blocking_if_failed": True,
            "caveat": "max_open_positions=1; no second trade while pending/open/unknown",
        }
        for area, required, source, condition in MAX_OPEN_POLICIES
    ]


def pre_request_block_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "block_code": code,
            "block_condition": code,
            "future_block_action": "block_before_any_future_request_construction",
            "blocking": True,
            "caveat": "pre-request block occurs before any future request construction path",
        }
        for code in PRE_REQUEST_BLOCKS
    ]


def audit_requirement_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "audit_area": area,
            "required_audit_record": record,
            "required_timing": "during_future_reconciliation_check",
            "immutable": True,
            "caveat": "future audit record only; no reconciliation is run here",
        }
        for area, record in AUDIT_REQUIREMENTS
    ]


def manifest_data(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    ctx: dict[str, Any],
    outputs: dict[str, Path],
    local_state: list[dict[str, Any]],
    broker_reads: list[dict[str, Any]],
    matching: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
    mismatches: list[dict[str, Any]],
    max_open: list[dict[str, Any]],
    pre_blocks: list[dict[str, Any]],
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
        "manual_approval_kill_switch_plan_dir": str(args.manual_approval_kill_switch_plan_dir),
        "manual_approval_kill_switch_plan_status": ctx["manual_approval_kill_switch_plan_status"],
        "future_state_json": str(args.future_state_json),
        "future_state_json_read_or_written": False,
        "future_positions_get_planned_only": True,
        "future_orders_get_planned_only": True,
        "history_reads_forbidden_unless_separately_planned": True,
        "local_state_requirement_row_count": len(local_state),
        "future_broker_read_row_count": len(broker_reads),
        "matching_field_row_count": len(matching),
        "reconciliation_status_row_count": len(statuses),
        "mismatch_handling_row_count": len(mismatches),
        "max_open_positions_row_count": len(max_open),
        "pre_request_block_row_count": len(pre_blocks),
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
        "# Fixed Candidate Demo Future Broker/Local State Reconciliation Check Plan",
        "",
        "Artifact-only future broker/local state reconciliation check planning.",
        "No MT5 import or connection was performed.",
        "No broker/API/account/symbol query was performed.",
        "No database query or mutation was performed.",
        "No future state JSON was read or written.",
        "No child script was executed.",
        "No broker request dictionary or order object was constructed.",
        "No order execution, order check, or order calculation was performed.",
        "No positions, orders, or history reads were performed.",
        "No scheduler, loop, daemon, or background task was added.",
        "No demo approval, trading decision, or candidate-quality final decision was made.",
        "",
        "## Source Summary",
        "",
        f"- manual_approval_kill_switch_plan_dir: `{args.manual_approval_kill_switch_plan_dir}`",
        f"- manual_approval_kill_switch_plan_status: `{ctx['manual_approval_kill_switch_plan_status']}`",
        f"- source_nature: `{ctx['source_nature']}`",
        f"- plan_status: `{ctx['plan_status']}`",
        f"- future_state_json: `{args.future_state_json}`",
        "",
        "## Future Local State Requirements",
        "",
        "A future separately implemented reconciliation check may read future_state_json read-only before explicit state transition.",
        "Malformed local state must block with reconciliation_hold. Missing local state is empty only before approval/execution attempt; after broker evidence exists, missing state blocks.",
        "",
        "## Future Broker Read Policy",
        "",
        "positions_get may be allowed only in a future broker/local state reconciliation check module.",
        "orders_get may be allowed only in a future broker/local state reconciliation check module if pending-order detection is separately planned.",
        "history_orders_get and history_deals_get remain forbidden unless separately planned.",
        "order_send, order_check, and order_calc_profit remain forbidden.",
        "This planning module calls none of these.",
        "",
        "## Matching Fields",
        "",
        "Future matching must compare symbol, direction/side, volume, entry/open price tolerance, SL, TP, signal_time_server, signal_id, idempotency_key, local state_status, and manual_approval_status.",
        "Positions or orders without candidate metadata must be treated conservatively.",
        "",
        "## Reconciliation Statuses And Mismatches",
        "",
        "Clean statuses document consistency; hold and blocked statuses stop new signals and any future request construction until resolved.",
        "Local/broker mismatches enter reconciliation_hold or stale_state_blocked.",
        "",
        "## Max Open Positions",
        "",
        "max_open_positions remains 1. Future local open count, broker open count, and broker pending order count must be zero before any future request construction. Unknown counts block.",
        "No hedging workaround, no netting workaround, and no second trade while pending/open/unknown.",
        "",
        "## Pre-Request Blocks",
        "",
        "Future request construction is blocked if reconciliation has not run, any hold status exists, broker reads are unavailable, account is non-demo, state is malformed, local/broker mismatch exists, pending/open state exists, manual approval is missing/expired, signal is stale, duplicate/idempotency failed, or kill-switch is active.",
        "",
        "## Audit Requirements",
        "",
        "Future reconciliation must record timestamp, account mode, symbol, local state digest, broker counts, matching fields, reconciliation status, mismatch reason, max-open-position result, and no-request/no-execution evidence.",
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
    source_dir = Path(args.manual_approval_kill_switch_plan_dir)
    source_manifest, source_manifest_error = read_json(source_dir / SOURCE_MANIFEST)
    _report, report_error = read_text(source_dir / SOURCE_REPORT)
    _main_rows, main_error = read_csv_rows(source_dir / SOURCE_MAIN)
    _manual_gate_rows, manual_gate_error = read_csv_rows(source_dir / SOURCE_MANUAL_APPROVAL_GATE)
    _operator_rows, operator_error = read_csv_rows(source_dir / SOURCE_OPERATOR_REVIEW)
    _kill_switch_rows, kill_switch_error = read_csv_rows(source_dir / SOURCE_KILL_SWITCH_RULES)
    _warning_escalation_rows, warning_escalation_error = read_csv_rows(source_dir / SOURCE_WARNING_ESCALATION)
    _pre_execution_rows, pre_execution_error = read_csv_rows(source_dir / SOURCE_PRE_EXECUTION_BLOCKS)
    _audit_rows, audit_error = read_csv_rows(source_dir / SOURCE_AUDIT_REQUIREMENTS)
    _transition_rows, transitions_error = read_csv_rows(source_dir / SOURCE_FUTURE_STATE_TRANSITIONS)
    source_warnings, source_warnings_error = read_csv_rows(source_dir / SOURCE_WARNINGS)
    if not source_warnings_error:
        warnings.extend(preserve_source_warnings(args, source_warnings, source_dir / SOURCE_WARNINGS))
    if report_error == "missing":
        add_warning(warnings, args=args, warning_code="source_report_missing", message="Source report is missing.", source=source_dir / SOURCE_REPORT, blocking_warning=False)
    if main_error == "missing":
        add_warning(warnings, args=args, warning_code="source_main_missing", message="Source main plan CSV is missing.", source=source_dir / SOURCE_MAIN, blocking_warning=False)
    if operator_error == "missing":
        add_warning(warnings, args=args, warning_code="source_operator_review_missing", message="Source operator review checklist is missing.", source=source_dir / SOURCE_OPERATOR_REVIEW, blocking_warning=False)
    if warning_escalation_error == "missing":
        add_warning(warnings, args=args, warning_code="source_warning_escalation_missing", message="Source warning escalation artifact is missing.", source=source_dir / SOURCE_WARNING_ESCALATION, blocking_warning=False)

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
        manual_gate_error=manual_gate_error,
        kill_switch_error=kill_switch_error,
        pre_execution_error=pre_execution_error,
        audit_error=audit_error,
        transitions_error=transitions_error,
        canonical_ok=canonical_ok,
        policy_ok_without_manual=policy_ok_without_manual,
        manual_required=manual_required,
        boundary_ok=boundary_ok,
        boundary_failures=boundary_failures,
        warnings=warnings,
    )
    if source_manifest.get("source_nature") == "synthetic_fixture":
        add_warning(warnings, args=args, warning_code="fixture_only_source", message="Manual approval / kill-switch source is fixture-only and non-actionable.", source=source_dir / SOURCE_MANIFEST, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="broker_local_reconciliation_planning_only", message="Broker/local state reconciliation is planning-only; no reconciliation was performed.", source="future_broker_state_reconciliation_check_plan", blocking_warning=False)
    add_warning(warnings, args=args, warning_code="future_state_json_not_read_or_written", message="Future state JSON path is a target only and was not read or written.", source=args.future_state_json, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="future_positions_orders_reads_not_called", message="positions_get/orders_get are future-only and not called here.", source="future_broker_reads", blocking_warning=False)
    add_warning(warnings, args=args, warning_code="history_reads_remain_forbidden", message="history_orders_get/history_deals_get remain forbidden unless separately planned.", source="future_broker_reads", blocking_warning=False)
    add_warning(warnings, args=args, warning_code="execution_remains_forbidden", message="Order execution and order request construction remain forbidden.", source=args.demo_execution_policy, blocking_warning=False)

    ctx = {
        "plan_status": plan_status,
        "source_nature": source_manifest.get("source_nature", "unknown"),
        "manual_approval_kill_switch_plan_status": source_manifest.get("plan_status", ""),
        "recommended_next_step": recommended_next_step(plan_status),
    }
    local_state = local_state_requirement_rows(args)
    broker_reads = future_broker_read_rows(args)
    matching = matching_field_rows(args)
    statuses = reconciliation_status_rows(args)
    mismatches = mismatch_handling_rows(args)
    max_open = max_open_position_rows(args)
    pre_blocks = pre_request_block_rows(args)
    audit = audit_requirement_rows(args)
    write_csv(outputs["main"], main_rows(args, ctx), MAIN_FIELDNAMES)
    write_csv(outputs["local_state_requirements"], local_state, LOCAL_STATE_FIELDNAMES)
    write_csv(outputs["future_broker_reads"], broker_reads, FUTURE_BROKER_READ_FIELDNAMES)
    write_csv(outputs["matching_fields"], matching, MATCHING_FIELDNAMES)
    write_csv(outputs["reconciliation_statuses"], statuses, RECONCILIATION_STATUS_FIELDNAMES)
    write_csv(outputs["mismatch_handling"], mismatches, MISMATCH_FIELDNAMES)
    write_csv(outputs["max_open_positions"], max_open, MAX_OPEN_FIELDNAMES)
    write_csv(outputs["pre_request_blocks"], pre_blocks, PRE_REQUEST_BLOCK_FIELDNAMES)
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
            local_state=local_state,
            broker_reads=broker_reads,
            matching=matching,
            statuses=statuses,
            mismatches=mismatches,
            max_open=max_open,
            pre_blocks=pre_blocks,
            audit=audit,
            warnings=warnings,
        ),
    )
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only fixed-candidate future broker/local state reconciliation check plan.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--manual-approval-kill-switch-plan-dir", type=Path, default=DEFAULT_MANUAL_APPROVAL_PLAN_DIR)
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
        print(f"Fixed-candidate future broker/local state reconciliation check plan failed: {exc}")
        return 1
    print("Fixed-candidate future broker/local state reconciliation check plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
