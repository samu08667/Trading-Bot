"""Build an artifact-only demo duplicate protection plan for the fixed candidate.

The plan defines future signal identity, idempotency, state gates, stale-signal
handling, and max-open-position protections. It reads only existing local
artifacts and config files. It does not import/connect MT5, query broker/API
or databases, read/write future state, run child scripts, construct broker
requests, execute orders, approve demo use, or make trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_duplicate_protection_plan"
DEFAULT_STATE_RECONCILIATION_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_state_reconciliation_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_state_reconciliation_plan_fixture_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_duplicate_protection_plan"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_SYMBOL = "GBPUSD"
EXPECTED_TIMEFRAME = "M15"
EXPECTED_DIRECTION = "short"
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

SOURCE_MANIFEST = "fixed_candidate_demo_state_reconciliation_plan_manifest.json"
SOURCE_REPORT = "fixed_candidate_demo_state_reconciliation_plan_report.md"
SOURCE_MAIN = "fixed_candidate_demo_state_reconciliation_plan.csv"
SOURCE_STATE_SCHEMA = "fixed_candidate_demo_state_reconciliation_plan_state_schema.csv"
SOURCE_IDEMPOTENCY = "fixed_candidate_demo_state_reconciliation_plan_idempotency.csv"
SOURCE_FAILURE_MODES = "fixed_candidate_demo_state_reconciliation_plan_failure_modes.csv"
SOURCE_FUTURE_BROKER_READS = "fixed_candidate_demo_state_reconciliation_plan_future_broker_reads.csv"
SOURCE_WARNINGS = "fixed_candidate_demo_state_reconciliation_plan_warnings.csv"

OUTPUT_MAIN = "fixed_candidate_demo_duplicate_protection_plan.csv"
OUTPUT_SIGNAL_IDENTITY = "fixed_candidate_demo_duplicate_protection_plan_signal_identity.csv"
OUTPUT_STATE_GATES = "fixed_candidate_demo_duplicate_protection_plan_state_gates.csv"
OUTPUT_IDEMPOTENCY_CHECKS = "fixed_candidate_demo_duplicate_protection_plan_idempotency_checks.csv"
OUTPUT_MAX_OPEN_POSITIONS = "fixed_candidate_demo_duplicate_protection_plan_max_open_positions.csv"
OUTPUT_STALE_SIGNAL_POLICY = "fixed_candidate_demo_duplicate_protection_plan_stale_signal_policy.csv"
OUTPUT_FUTURE_PRE_EXECUTION_CHECKS = "fixed_candidate_demo_duplicate_protection_plan_future_pre_execution_checks.csv"
OUTPUT_REPORT = "fixed_candidate_demo_duplicate_protection_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_demo_duplicate_protection_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_demo_duplicate_protection_plan_manifest.json"

ACCEPTABLE_STATE_RECONCILIATION_STATUSES = {
    "state_reconciliation_plan_fixture_only",
    "state_reconciliation_plan_available_no_order",
}

OPTIONAL_SOURCE_TRUE_FIELDS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_positions_get_called",
    "no_orders_get_called",
    "no_history_orders_get_called",
    "no_history_deals_get_called",
    "no_trading_decision_performed",
    "no_demo_broker_approval_performed",
)

SIGNAL_IDENTITY_FIELDS = (
    "candidate_id",
    "symbol",
    "timeframe",
    "direction",
    "signal_time_server",
    "signal_id",
    "idempotency_key",
    "entry_reference_price",
    "sl_price",
    "tp_price",
)

IDEMPOTENCY_COMPONENTS = (
    "candidate_id",
    "symbol",
    "timeframe",
    "direction",
    "signal_time_server",
    "entry_reference_price",
    "sl_price",
    "tp_price",
)

BLOCKING_STATE_GATES = (
    ("duplicate_signal_time_server", "block duplicate signal_time_server"),
    ("duplicate_signal_id", "block duplicate signal_id"),
    ("duplicate_idempotency_key", "block duplicate idempotency_key"),
    ("same_candle_rerun_not_terminal", "block same candle rerun unless previous state is explicitly terminal and safe"),
    ("pending_manual_review", "block if local state has pending_manual_review"),
    ("manually_approved_pending_execution", "block if local state has manually_approved_pending_execution"),
    ("execution_submitted_future_only", "block if local state has execution_submitted_future_only"),
    ("open_future_only", "block if local state has open_future_only"),
    ("reconciliation_hold", "block if local state has reconciliation_hold"),
    ("error_hold", "block if local state has error_hold"),
    ("max_open_positions_exceeded", "block if max_open_positions would exceed 1"),
)

TERMINAL_ALLOW_STATES = (
    "empty",
    "manually_rejected",
    "closed_future_only",
    "stale_signal_blocked",
    "duplicate_blocked",
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
SIGNAL_IDENTITY_FIELDNAMES = [
    "run_id",
    "signal_identity_field",
    "field_role",
    "required",
    "future_source",
    "duplicate_protection_role",
    "not_broker_request_field",
    "caveat",
]
STATE_GATE_FIELDNAMES = [
    "run_id",
    "state_gate",
    "state_status_or_condition",
    "future_gate_action",
    "blocking_if_matched",
    "terminal_state_allows_new_signal",
    "requires_manual_resolution",
    "caveat",
]
IDEMPOTENCY_FIELDNAMES = [
    "run_id",
    "idempotency_area",
    "composition_order",
    "component_name",
    "expected_source",
    "future_check_action",
    "blocking_if_duplicate",
    "not_broker_request_field",
    "caveat",
]
MAX_OPEN_FIELDNAMES = [
    "run_id",
    "max_open_area",
    "required_count",
    "future_count_source",
    "expected_condition",
    "future_action_if_failed",
    "blocking_if_failed",
    "caveat",
]
STALE_POLICY_FIELDNAMES = [
    "run_id",
    "stale_policy_area",
    "timeframe",
    "horizon_bars",
    "expected_condition",
    "future_action_if_failed",
    "blocking_if_failed",
    "caveat",
]
FUTURE_CHECK_FIELDNAMES = [
    "run_id",
    "future_check_area",
    "future_check_name",
    "future_check_source",
    "expected_condition",
    "future_only",
    "current_module_performed",
    "blocking_if_failed",
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
        "signal_identity": output_dir / OUTPUT_SIGNAL_IDENTITY,
        "state_gates": output_dir / OUTPUT_STATE_GATES,
        "idempotency_checks": output_dir / OUTPUT_IDEMPOTENCY_CHECKS,
        "max_open_positions": output_dir / OUTPUT_MAX_OPEN_POSITIONS,
        "stale_signal_policy": output_dir / OUTPUT_STALE_SIGNAL_POLICY,
        "future_pre_execution_checks": output_dir / OUTPUT_FUTURE_PRE_EXECUTION_CHECKS,
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


def execution_policy_valid(policy: dict[str, Any]) -> bool:
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
        and as_bool(safety.get("manual_approval_required_before_any_future_demo_order")) is True
    )


def source_boundary_valid(manifest: dict[str, Any], future_reads: list[dict[str, str]]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if as_bool(manifest.get("plan_actionable")) is not False:
        failures.append("plan_actionable_not_false")
    for field in OPTIONAL_SOURCE_TRUE_FIELDS:
        if field in manifest and as_bool(manifest.get(field)) is not True:
            failures.append(field)
    for row in future_reads:
        if as_bool(row.get("current_module_called")) is True:
            failures.append(f"source_future_broker_read_called:{row.get('future_call_name')}")
    return not failures, failures


def source_status_acceptable(status: str) -> bool:
    return status in ACCEPTABLE_STATE_RECONCILIATION_STATUSES


def status_from_source(manifest: dict[str, Any]) -> str:
    if manifest.get("source_nature") == "synthetic_fixture":
        return "duplicate_protection_plan_fixture_only"
    return "duplicate_protection_plan_available_no_order"


def recommended_next_step(plan_status: str) -> str:
    if plan_status == "duplicate_protection_plan_fixture_only":
        return "continue_no_order_monitoring_or_build_manual_approval_kill_switch_plan"
    if plan_status == "duplicate_protection_plan_available_no_order":
        return "build_fixed_candidate_demo_manual_approval_kill_switch_plan"
    return "fix_duplicate_protection_plan_inputs"


def determine_plan_status(
    *,
    args: argparse.Namespace,
    registry_error: str,
    policy_error: str,
    source_manifest: dict[str, Any],
    source_manifest_error: str,
    idempotency_error: str,
    state_schema_error: str,
    future_reads_error: str,
    canonical_ok: bool,
    policy_ok: bool,
    boundary_ok: bool,
    boundary_failures: list[str],
    warnings: list[dict[str, Any]],
) -> str:
    source_dir = Path(args.state_reconciliation_plan_dir)
    if source_manifest_error == "missing":
        add_warning(warnings, args=args, warning_code="state_reconciliation_manifest_missing", message="State reconciliation plan manifest is missing.", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_missing_state_reconciliation_manifest"
    if idempotency_error == "missing":
        add_warning(warnings, args=args, warning_code="state_reconciliation_idempotency_missing", message="State reconciliation idempotency artifact is missing.", source=source_dir / SOURCE_IDEMPOTENCY, blocking_warning=True)
        return "blocked_missing_state_reconciliation_idempotency"
    if state_schema_error == "missing":
        add_warning(warnings, args=args, warning_code="state_reconciliation_state_schema_missing", message="State reconciliation state schema artifact is missing.", source=source_dir / SOURCE_STATE_SCHEMA, blocking_warning=True)
        return "blocked_missing_state_reconciliation_state_schema"
    if future_reads_error == "missing":
        add_warning(warnings, args=args, warning_code="state_reconciliation_future_broker_reads_missing", message="State reconciliation future broker reads artifact is missing.", source=source_dir / SOURCE_FUTURE_BROKER_READS, blocking_warning=True)
        return "blocked_missing_state_reconciliation_future_broker_reads"
    unreadable = [
        ("canonical_registry_unreadable", registry_error, args.canonical_registry),
        ("demo_execution_policy_unreadable", policy_error, args.demo_execution_policy),
        ("state_reconciliation_manifest_unreadable", source_manifest_error, source_dir / SOURCE_MANIFEST),
        ("state_reconciliation_idempotency_unreadable", idempotency_error, source_dir / SOURCE_IDEMPOTENCY),
        ("state_reconciliation_state_schema_unreadable", state_schema_error, source_dir / SOURCE_STATE_SCHEMA),
        ("state_reconciliation_future_broker_reads_unreadable", future_reads_error, source_dir / SOURCE_FUTURE_BROKER_READS),
    ]
    unreadable_errors = [item for item in unreadable if item[1] and item[1] != "missing"]
    if unreadable_errors:
        for code, error, source in unreadable_errors:
            add_warning(warnings, args=args, warning_code=code, message=f"Input artifact is unreadable: {error}", source=source, blocking_warning=True)
        return "blocked_unreadable_input"
    if not canonical_ok:
        add_warning(warnings, args=args, warning_code="noncanonical_candidate", message="Canonical registry/policy does not match fixed candidate spread15 max-open-one boundaries.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_noncanonical_candidate"
    if not policy_ok:
        add_warning(warnings, args=args, warning_code="noncanonical_demo_execution_policy", message="Demo execution policy does not match risk/margin/no-order boundaries.", source=args.demo_execution_policy, blocking_warning=True)
        return "blocked_noncanonical_demo_execution_policy"
    source_status = str(source_manifest.get("plan_status") or "")
    if not source_status_acceptable(source_status):
        add_warning(warnings, args=args, warning_code="unacceptable_state_reconciliation_status", message=f"State reconciliation plan status is not acceptable: {source_status}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_unacceptable_state_reconciliation_status"
    if not boundary_ok:
        add_warning(warnings, args=args, warning_code="unsafe_state_reconciliation_boundary", message=f"State reconciliation boundary failed fields: {boundary_failures}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_unsafe_state_reconciliation_boundary"
    return status_from_source(source_manifest)


def main_rows(args: argparse.Namespace, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    source = Path(args.state_reconciliation_plan_dir) / SOURCE_MANIFEST
    items = [
        ("source_artifact_chain", ctx["state_reconciliation_plan_status"], "acceptable state reconciliation plan status", "state_reconciliation_source_accepted", "plan remains artifact-only"),
        ("source_nature", ctx["source_nature"], "synthetic_fixture or live_data_shadow_signal", "source_nature_identified", "fixture source remains non-actionable"),
        ("canonical_candidate", EXPECTED_CANDIDATE_ID, EXPECTED_CANDIDATE_ID, "canonical_candidate_confirmed", "fixed candidate only"),
        ("spread_policy", f"{EXPECTED_SPREAD_UNIT}:{EXPECTED_MAX_SPREAD_POINTS}", "broker_points:15.0", "spread15_policy_confirmed", "no pip conversion introduced"),
        ("future_state_json", ctx["future_state_json"], "future target only", "future_state_target_defined", "not read or written here"),
        ("signal_identity", ";".join(SIGNAL_IDENTITY_FIELDS), "identity fields defined", "signal_identity_defined", "future local artifact fields only"),
        ("idempotency_key", "+".join(IDEMPOTENCY_COMPONENTS), "fixed composition", "idempotency_composition_defined", "not a broker request field"),
        ("state_gates", "blocking and terminal gates defined", "duplicate/new-signal gating defined", "state_gates_defined", "future local state only"),
        ("max_open_positions", EXPECTED_MAX_OPEN_POSITIONS, 1, "max_open_positions_one_required", "future local and future broker count checks required"),
        ("stale_signal_policy", f"horizon_bars={EXPECTED_HORIZON_BARS}", "block stale signal older than horizon", "stale_signal_policy_defined", "future module must compare server time"),
        ("future_pre_execution_checks", "defined", "all future duplicate checks before manual approval", "future_pre_execution_checks_defined", "planning-only"),
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


def signal_identity_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    roles = {
        "candidate_id": "fixed_candidate_identity",
        "symbol": "fixed_candidate_identity",
        "timeframe": "fixed_candidate_identity",
        "direction": "fixed_candidate_identity",
        "signal_time_server": "single_m15_candle_identity",
        "signal_id": "future_signal_record_identity",
        "idempotency_key": "future_deduplication_identity",
        "entry_reference_price": "price_component_for_idempotency",
        "sl_price": "risk_price_component_for_idempotency",
        "tp_price": "reward_price_component_for_idempotency",
    }
    return [
        {
            "run_id": args.run_id,
            "signal_identity_field": field,
            "field_role": roles[field],
            "required": True,
            "future_source": "future local no-order or manual-review signal artifact",
            "duplicate_protection_role": "identity_or_idempotency_component",
            "not_broker_request_field": True,
            "caveat": "planning-only; no state file is read or written here",
        }
        for field in SIGNAL_IDENTITY_FIELDS
    ]


def state_gate_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for state_gate, description in BLOCKING_STATE_GATES:
        rows.append(
            {
                "run_id": args.run_id,
                "state_gate": state_gate,
                "state_status_or_condition": state_gate,
                "future_gate_action": description,
                "blocking_if_matched": True,
                "terminal_state_allows_new_signal": False,
                "requires_manual_resolution": state_gate in {"reconciliation_hold", "error_hold"},
                "caveat": "future local state gate only; no current state read here",
            }
        )
    for state in TERMINAL_ALLOW_STATES:
        rows.append(
            {
                "run_id": args.run_id,
                "state_gate": "terminal_state_may_allow_new_signal",
                "state_status_or_condition": state,
                "future_gate_action": "may allow new signal only after duplicate/idempotency checks pass",
                "blocking_if_matched": False,
                "terminal_state_allows_new_signal": True,
                "requires_manual_resolution": False,
                "caveat": "terminal state does not bypass max-open-position or stale-signal checks",
            }
        )
    return rows


def idempotency_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, component in enumerate(IDEMPOTENCY_COMPONENTS, start=1):
        rows.append(
            {
                "run_id": args.run_id,
                "idempotency_area": "composition",
                "composition_order": index,
                "component_name": component,
                "expected_source": "future local signal/state artifact",
                "future_check_action": "compose_idempotency_key",
                "blocking_if_duplicate": False,
                "not_broker_request_field": True,
                "caveat": "+".join(IDEMPOTENCY_COMPONENTS),
            }
        )
    rows.extend(
        [
            {
                "run_id": args.run_id,
                "idempotency_area": "duplicate_check",
                "composition_order": "",
                "component_name": "idempotency_key",
                "expected_source": "future local state",
                "future_check_action": "block_if_idempotency_key_already_present",
                "blocking_if_duplicate": True,
                "not_broker_request_field": True,
                "caveat": "prevents repeated future order attempts for same signal identity",
            },
            {
                "run_id": args.run_id,
                "idempotency_area": "duplicate_check",
                "composition_order": "",
                "component_name": "signal_id",
                "expected_source": "future local state",
                "future_check_action": "block_if_signal_id_already_present",
                "blocking_if_duplicate": True,
                "not_broker_request_field": True,
                "caveat": "prevents duplicate state writes for same signal",
            },
            {
                "run_id": args.run_id,
                "idempotency_area": "duplicate_check",
                "composition_order": "",
                "component_name": "signal_time_server",
                "expected_source": "future local state",
                "future_check_action": "block_if_signal_time_server_already_processed_unless_terminal_safe",
                "blocking_if_duplicate": True,
                "not_broker_request_field": True,
                "caveat": "same M15 candle reruns must be idempotent",
            },
        ]
    )
    return rows


def max_open_position_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    items = [
        ("future_local_open_count", 0, "future local state", "local open or pending count must be 0", "block_or_reconciliation_hold", True, "no second trade while pending/open"),
        ("future_broker_open_count", 0, "future broker reconciliation module", "future broker open count for candidate/symbol/direction must be 0", "reconciliation_hold", True, "future-only broker read, not performed here"),
        ("local_broker_count_match", "match", "future local state and future broker reconciliation", "local and future broker counts must agree", "reconciliation_hold", True, "ambiguous state blocks future execution phase"),
        ("netting_hedging_workaround", "not_allowed", "future execution policy", "no netting or hedging workaround allowed", "block", True, "max_open_positions remains 1"),
        ("second_trade_while_pending_or_open", "not_allowed", "future local state", "no second trade while pending/open", "block", True, "manual approval does not bypass duplicate protection"),
    ]
    return [
        {
            "run_id": args.run_id,
            "max_open_area": area,
            "required_count": required,
            "future_count_source": source,
            "expected_condition": condition,
            "future_action_if_failed": action,
            "blocking_if_failed": blocking,
            "caveat": caveat,
        }
        for area, required, source, condition, action, blocking, caveat in items
    ]


def stale_signal_policy_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    items = [
        ("m15_candle_identity", "signal_time_server must map to one M15 candle", "duplicate_blocked", True, "same candle processing must be idempotent"),
        ("same_candle_rerun", "repeated processing of same M15 candle must reuse idempotency result", "duplicate_blocked_or_noop", True, "rerun is allowed only if previous state is terminal and safe"),
        ("horizon_age_gate", "stale signal older than horizon_bars=10 must be blocked or marked stale", "stale_signal_blocked", True, "future module compares server time to signal_time_server"),
        ("manual_approval_age_gate", "current server time must be checked before manual approval/future execution phase", "hold_or_stale_signal_blocked", True, "approval gate cannot revive stale signals"),
    ]
    return [
        {
            "run_id": args.run_id,
            "stale_policy_area": area,
            "timeframe": EXPECTED_TIMEFRAME,
            "horizon_bars": EXPECTED_HORIZON_BARS,
            "expected_condition": condition,
            "future_action_if_failed": action,
            "blocking_if_failed": blocking,
            "caveat": caveat,
        }
        for area, condition, action, blocking, caveat in items
    ]


def future_pre_execution_check_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    items = [
        ("state_initialization", "future_state_file_exists_or_initialized_empty_safely", "future local state", "state exists or empty state initialized safely", True, True, "state JSON is not read or written by this plan"),
        ("idempotency", "idempotency_key_not_already_present", "future local state", "idempotency_key absent", True, True, "blocks duplicate future order attempts"),
        ("signal_time_server", "signal_time_server_not_already_processed", "future local state", "signal_time_server absent unless terminal safe", True, True, "same candle rerun is idempotent"),
        ("pending_open_state", "no_pending_or_open_state", "future local state", "no pending/open/hold state", True, True, "manual review and open states block"),
        ("max_open_positions", "max_open_positions_equals_one_and_not_exceeded", "policy plus future local state", "max_open_positions=1 and current count=0", True, True, "no second trade"),
        ("future_broker_reads", "positions_get_future_only", "separate future reconciliation module", "future broker position count is 0 before future execution phase", True, False, "not called by this module"),
        ("future_broker_reads", "orders_get_future_only_if_separately_planned", "separate future reconciliation module", "future pending order count reconciled if separately planned", True, False, "not called by this module"),
        ("future_broker_reads", "history_orders_get_forbidden_unless_separately_planned", "separate future reconciliation module", "remain forbidden unless separately planned", True, False, "not called by this module"),
        ("future_broker_reads", "history_deals_get_forbidden_unless_separately_planned", "separate future reconciliation module", "remain forbidden unless separately planned", True, False, "not called by this module"),
        ("manual_approval", "manual_approval_gate_after_duplicate_checks", "future operator gate", "manual approval happens after duplicate checks", True, True, "planning only; no approval performed here"),
    ]
    return [
        {
            "run_id": args.run_id,
            "future_check_area": area,
            "future_check_name": name,
            "future_check_source": source,
            "expected_condition": condition,
            "future_only": future_only,
            "current_module_performed": False,
            "blocking_if_failed": blocking,
            "caveat": caveat,
        }
        for area, name, source, condition, future_only, blocking, caveat in items
    ]


def manifest_data(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    ctx: dict[str, Any],
    outputs: dict[str, Path],
    signal_identity: list[dict[str, Any]],
    state_gates: list[dict[str, Any]],
    idempotency: list[dict[str, Any]],
    max_open: list[dict[str, Any]],
    stale_policy: list[dict[str, Any]],
    future_checks: list[dict[str, Any]],
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
        "spread_unit": EXPECTED_SPREAD_UNIT,
        "max_spread_points": EXPECTED_MAX_SPREAD_POINTS,
        "state_reconciliation_plan_dir": str(args.state_reconciliation_plan_dir),
        "state_reconciliation_plan_status": ctx["state_reconciliation_plan_status"],
        "future_state_json": str(args.future_state_json),
        "future_state_json_read_or_written": False,
        "max_open_positions": EXPECTED_MAX_OPEN_POSITIONS,
        "horizon_bars": EXPECTED_HORIZON_BARS,
        "signal_identity_row_count": len(signal_identity),
        "state_gate_row_count": len(state_gates),
        "idempotency_check_row_count": len(idempotency),
        "max_open_positions_row_count": len(max_open),
        "stale_signal_policy_row_count": len(stale_policy),
        "future_pre_execution_check_row_count": len(future_checks),
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
    }


def write_report(path: Path, *, ctx: dict[str, Any], args: argparse.Namespace, warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Duplicate Protection Plan",
        "",
        "Artifact-only duplicate protection planning.",
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
        f"- state_reconciliation_plan_dir: `{args.state_reconciliation_plan_dir}`",
        f"- state_reconciliation_plan_status: `{ctx['state_reconciliation_plan_status']}`",
        f"- source_nature: `{ctx['source_nature']}`",
        f"- plan_status: `{ctx['plan_status']}`",
        f"- future_state_json: `{args.future_state_json}`",
        "",
        "## Signal Identity And Idempotency",
        "",
        "Signal identity fields: candidate_id, symbol, timeframe, direction, signal_time_server, signal_id, idempotency_key, entry_reference_price, sl_price, tp_price.",
        "Idempotency composition: candidate_id + symbol + timeframe + direction + signal_time_server + entry_reference_price + sl_price + tp_price.",
        "The idempotency key is future local-state-only and not a broker request field.",
        "",
        "## State Gates",
        "",
        "Future modules must block duplicate signal_time_server, duplicate signal_id, duplicate idempotency_key, same-candle reruns without a safe terminal state, pending/open states, reconciliation holds, error holds, and max-open-position violations.",
        "Terminal states that may allow a future new signal are empty, manually_rejected, closed_future_only, stale_signal_blocked, and duplicate_blocked.",
        "",
        "## Max Open Positions",
        "",
        "max_open_positions remains 1. Future local open count and future broker open count for the candidate/symbol/direction must both be 0 before any future execution phase.",
        "Local-vs-future-broker count mismatch must enter reconciliation_hold. No netting or hedging workaround is allowed.",
        "",
        "## Stale Signal Policy",
        "",
        "signal_time_server must map to one M15 candle. Same-candle repeated processing must be idempotent.",
        "Signals older than horizon_bars=10 must be blocked or marked stale before manual approval or any future execution phase.",
        "",
        "## Future Pre-Execution Checks",
        "",
        "Future modules must check local state, idempotency key, signal_time_server, pending/open state, max_open_positions=1, future broker reconciliation in a separate module, and manual approval after duplicate checks.",
        "positions_get and orders_get are future-only names for a separately planned reconciliation/check module. History reads remain forbidden unless separately planned.",
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
    source_dir = Path(args.state_reconciliation_plan_dir)
    source_manifest, source_manifest_error = read_json(source_dir / SOURCE_MANIFEST)
    _report, report_error = read_text(source_dir / SOURCE_REPORT)
    _main_rows, main_error = read_csv_rows(source_dir / SOURCE_MAIN)
    _idempotency_rows, idempotency_error = read_csv_rows(source_dir / SOURCE_IDEMPOTENCY)
    _state_schema_rows, state_schema_error = read_csv_rows(source_dir / SOURCE_STATE_SCHEMA)
    _failure_mode_rows, failure_modes_error = read_csv_rows(source_dir / SOURCE_FAILURE_MODES)
    future_reads_rows, future_reads_error = read_csv_rows(source_dir / SOURCE_FUTURE_BROKER_READS)
    source_warnings, source_warnings_error = read_csv_rows(source_dir / SOURCE_WARNINGS)
    if not source_warnings_error:
        warnings.extend(preserve_source_warnings(args, source_warnings, source_dir / SOURCE_WARNINGS))
    if report_error == "missing":
        add_warning(warnings, args=args, warning_code="source_report_missing", message="Source report is missing.", source=source_dir / SOURCE_REPORT, blocking_warning=False)
    if main_error == "missing":
        add_warning(warnings, args=args, warning_code="source_main_missing", message="Source main plan CSV is missing.", source=source_dir / SOURCE_MAIN, blocking_warning=False)
    if failure_modes_error == "missing":
        add_warning(warnings, args=args, warning_code="source_failure_modes_missing", message="Source failure modes CSV is missing.", source=source_dir / SOURCE_FAILURE_MODES, blocking_warning=False)

    canonical_ok = not registry_error and not policy_error and canonical_registry_valid(registry, policy)
    policy_ok = not policy_error and execution_policy_valid(policy)
    boundary_ok, boundary_failures = source_boundary_valid(source_manifest, future_reads_rows)
    plan_status = determine_plan_status(
        args=args,
        registry_error=registry_error,
        policy_error=policy_error,
        source_manifest=source_manifest,
        source_manifest_error=source_manifest_error,
        idempotency_error=idempotency_error,
        state_schema_error=state_schema_error,
        future_reads_error=future_reads_error,
        canonical_ok=canonical_ok,
        policy_ok=policy_ok,
        boundary_ok=boundary_ok,
        boundary_failures=boundary_failures,
        warnings=warnings,
    )
    if source_manifest.get("source_nature") == "synthetic_fixture":
        add_warning(warnings, args=args, warning_code="fixture_only_source", message="State reconciliation source is fixture-only and non-actionable.", source=source_dir / SOURCE_MANIFEST, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="duplicate_protection_planning_only", message="Duplicate protection is planning-only; no live duplicate checking was performed.", source="duplicate_protection_plan", blocking_warning=False)
    add_warning(warnings, args=args, warning_code="future_state_json_not_read_or_written", message="Future state JSON path is a target only and was not read or written.", source=args.future_state_json, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="future_broker_reads_planning_only", message="Future broker reads are planning-only and not performed by this module.", source=source_dir / SOURCE_FUTURE_BROKER_READS, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="execution_remains_forbidden", message="Order execution and order request construction remain forbidden.", source=args.demo_execution_policy, blocking_warning=False)

    ctx = {
        "plan_status": plan_status,
        "source_nature": source_manifest.get("source_nature", "unknown"),
        "state_reconciliation_plan_status": source_manifest.get("plan_status", ""),
        "future_state_json": str(args.future_state_json),
        "recommended_next_step": recommended_next_step(plan_status),
    }
    signal_identity = signal_identity_rows(args)
    state_gates = state_gate_rows(args)
    idempotency = idempotency_rows(args)
    max_open = max_open_position_rows(args)
    stale_policy = stale_signal_policy_rows(args)
    future_checks = future_pre_execution_check_rows(args)
    write_csv(outputs["main"], main_rows(args, ctx), MAIN_FIELDNAMES)
    write_csv(outputs["signal_identity"], signal_identity, SIGNAL_IDENTITY_FIELDNAMES)
    write_csv(outputs["state_gates"], state_gates, STATE_GATE_FIELDNAMES)
    write_csv(outputs["idempotency_checks"], idempotency, IDEMPOTENCY_FIELDNAMES)
    write_csv(outputs["max_open_positions"], max_open, MAX_OPEN_FIELDNAMES)
    write_csv(outputs["stale_signal_policy"], stale_policy, STALE_POLICY_FIELDNAMES)
    write_csv(outputs["future_pre_execution_checks"], future_checks, FUTURE_CHECK_FIELDNAMES)
    write_csv(outputs["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(outputs["report"], ctx=ctx, args=args, warnings=warnings)
    write_json(
        outputs["manifest"],
        manifest_data(
            args=args,
            output_dir=output_dir,
            ctx=ctx,
            outputs=outputs,
            signal_identity=signal_identity,
            state_gates=state_gates,
            idempotency=idempotency,
            max_open=max_open,
            stale_policy=stale_policy,
            future_checks=future_checks,
            warnings=warnings,
        ),
    )
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only fixed-candidate demo duplicate protection plan.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--state-reconciliation-plan-dir", type=Path, default=DEFAULT_STATE_RECONCILIATION_PLAN_DIR)
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
        print(f"Fixed-candidate demo duplicate protection plan failed: {exc}")
        return 1
    print("Fixed-candidate demo duplicate protection plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
