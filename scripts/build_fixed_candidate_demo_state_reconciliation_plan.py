"""Build an artifact-only demo state reconciliation plan for the fixed candidate.

The plan defines future local state, idempotency, duplicate protection, crash
recovery, and future local-vs-broker reconciliation requirements. It reads only
existing local artifacts and config files. It does not import/connect MT5,
query broker/API/account/symbol state, query or mutate databases, run child
scripts, construct broker-ready structures, execute orders, approve demo use,
or make trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_state_reconciliation_plan"
DEFAULT_BROKER_SAFE_MARGIN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_broker_safe_margin_validation"
    / "gbpusd_short_h10_1_5_off_hours_demo_broker_safe_margin_validation_equity1000_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_state_reconciliation_plan"

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

SOURCE_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
SOURCE_REPORT = "fixed_candidate_demo_broker_safe_margin_validation_report.md"
SOURCE_MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"
SOURCE_CHECKLIST = "fixed_candidate_demo_broker_safe_margin_validation_checklist.csv"
SOURCE_NO_ORDER = "fixed_candidate_demo_broker_safe_margin_validation_no_order_evidence.csv"
SOURCE_WARNINGS = "fixed_candidate_demo_broker_safe_margin_validation_warnings.csv"

OUTPUT_MANIFEST = "fixed_candidate_demo_state_reconciliation_plan_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_state_reconciliation_plan_report.md"
OUTPUT_MAIN = "fixed_candidate_demo_state_reconciliation_plan.csv"
OUTPUT_STATE_SCHEMA = "fixed_candidate_demo_state_reconciliation_plan_state_schema.csv"
OUTPUT_IDEMPOTENCY = "fixed_candidate_demo_state_reconciliation_plan_idempotency.csv"
OUTPUT_FAILURE_MODES = "fixed_candidate_demo_state_reconciliation_plan_failure_modes.csv"
OUTPUT_FUTURE_BROKER_READS = "fixed_candidate_demo_state_reconciliation_plan_future_broker_reads.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_state_reconciliation_plan_warnings.csv"

ACCEPTABLE_MARGIN_STATUSES = {
    "broker_safe_margin_validation_fixture_only_available_with_margin_warning",
    "broker_safe_margin_validation_fixture_only",
    "broker_safe_margin_validation_available",
    "broker_safe_margin_validation_available_with_margin_warning",
}

NO_ORDER_TRUE_FIELDS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_profit_called",
    "no_positions_get_called",
    "no_orders_get_called",
    "no_history_orders_get_called",
    "no_history_deals_get_called",
    "no_trading_decision_performed",
    "no_demo_broker_approval_performed",
)

STATE_FIELDS = (
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
STATE_STATUSES = (
    "empty",
    "signal_seen",
    "pending_manual_review",
    "manually_rejected",
    "manually_approved_pending_execution",
    "execution_submitted_future_only",
    "open_future_only",
    "closed_future_only",
    "reconciliation_hold",
    "duplicate_blocked",
    "stale_signal_blocked",
    "error_hold",
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
STATE_SCHEMA_FIELDNAMES = [
    "run_id",
    "state_field",
    "field_role",
    "required",
    "future_state_statuses",
    "source_or_future_input",
    "caveat",
]
IDEMPOTENCY_FIELDNAMES = [
    "run_id",
    "idempotency_area",
    "composition_order",
    "component_name",
    "expected_source",
    "future_local_state_only",
    "not_broker_request_field",
    "caveat",
]
FAILURE_MODE_FIELDNAMES = [
    "run_id",
    "failure_mode",
    "planned_detection",
    "planned_response",
    "blocking_until_resolved",
    "caveat",
]
FUTURE_BROKER_READ_FIELDNAMES = [
    "run_id",
    "future_read_label",
    "future_call_name",
    "allowed_only_in_future_reconciliation_module",
    "current_module_called",
    "required_before_future_execution",
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
        "state_schema": output_dir / OUTPUT_STATE_SCHEMA,
        "idempotency": output_dir / OUTPUT_IDEMPOTENCY,
        "failure_modes": output_dir / OUTPUT_FAILURE_MODES,
        "future_broker_reads": output_dir / OUTPUT_FUTURE_BROKER_READS,
        "report": output_dir / OUTPUT_REPORT,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "manifest": output_dir / OUTPUT_MANIFEST,
    }


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = output_paths(output_dir)
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
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
        close_float(policy.get("intended_demo_equity"), EXPECTED_DEMO_EQUITY)
        and policy.get("account_currency") == EXPECTED_ACCOUNT_CURRENCY
        and close_float(policy.get("risk_percent_max"), EXPECTED_RISK_PERCENT)
        and close_float(policy.get("risk_amount_max"), EXPECTED_RISK_AMOUNT)
        and close_float(policy.get("max_margin_usage_warning_ratio"), EXPECTED_WARNING_RATIO)
        and close_float(policy.get("max_margin_usage_warning_amount"), EXPECTED_WARNING_AMOUNT)
        and close_float(policy.get("max_margin_usage_ratio"), EXPECTED_CAP_RATIO)
        and close_float(policy.get("max_margin_usage_amount"), EXPECTED_CAP_AMOUNT)
        and as_bool(safety.get("real_money_allowed")) is False
        and as_bool(safety.get("order_execution_allowed")) is False
        and as_bool(safety.get("order_request_construction_allowed")) is False
        and as_bool(safety.get("order_check_allowed")) is False
        and as_bool(safety.get("manual_approval_required_before_any_future_demo_order")) is True
    )


def no_order_evidence_valid(rows: list[dict[str, str]]) -> tuple[bool, list[str]]:
    if not rows:
        return False, ["no_rows"]
    row = rows[0]
    failures = [field for field in NO_ORDER_TRUE_FIELDS if as_bool(row.get(field)) is not True]
    return not failures, failures


def source_status_acceptable(status: str) -> bool:
    return status in ACCEPTABLE_MARGIN_STATUSES


def plan_status_for(manifest: dict[str, Any]) -> str:
    source_nature = manifest.get("source_nature")
    if source_nature == "synthetic_fixture":
        return "state_reconciliation_plan_fixture_only"
    return "state_reconciliation_plan_available_no_order"


def recommended_next_step(plan_status: str) -> str:
    if plan_status == "state_reconciliation_plan_fixture_only":
        return "wait_for_live_shadow_signal_or_continue_no_order_monitoring"
    if plan_status == "state_reconciliation_plan_available_no_order":
        return "build_fixed_candidate_demo_duplicate_protection_plan"
    return "fix_state_reconciliation_plan_inputs"


def determine_plan_status(
    *,
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_error: str,
    policy: dict[str, Any],
    policy_error: str,
    source_manifest: dict[str, Any],
    source_manifest_error: str,
    margin_snapshot: dict[str, Any],
    margin_snapshot_error: str,
    no_order_rows: list[dict[str, str]],
    no_order_error: str,
    canonical_ok: bool,
    policy_ok: bool,
    no_order_ok: bool,
    no_order_failures: list[str],
    warnings: list[dict[str, Any]],
) -> str:
    source_dir = Path(args.broker_safe_margin_validation_dir)
    if source_manifest_error == "missing":
        add_warning(warnings, args=args, warning_code="broker_safe_margin_validation_manifest_missing", message="Broker-safe margin validation manifest is missing.", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_missing_broker_safe_margin_validation_manifest"
    if margin_snapshot_error == "missing":
        add_warning(warnings, args=args, warning_code="margin_snapshot_missing", message="Broker-safe margin validation margin snapshot is missing.", source=source_dir / SOURCE_MARGIN_SNAPSHOT, blocking_warning=True)
        return "blocked_missing_margin_snapshot"
    if no_order_error == "missing":
        add_warning(warnings, args=args, warning_code="no_order_evidence_missing", message="Broker-safe margin validation no-order evidence is missing.", source=source_dir / SOURCE_NO_ORDER, blocking_warning=True)
        return "blocked_missing_no_order_evidence"
    unreadable = [
        ("canonical_registry_unreadable", registry_error, args.canonical_registry),
        ("demo_execution_policy_unreadable", policy_error, args.demo_execution_policy),
        ("broker_safe_manifest_unreadable", source_manifest_error, source_dir / SOURCE_MANIFEST),
        ("margin_snapshot_unreadable", margin_snapshot_error, source_dir / SOURCE_MARGIN_SNAPSHOT),
        ("no_order_evidence_unreadable", no_order_error, source_dir / SOURCE_NO_ORDER),
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
        add_warning(warnings, args=args, warning_code="noncanonical_demo_execution_policy", message="Demo execution policy does not match equity/risk/margin/no-order boundaries.", source=args.demo_execution_policy, blocking_warning=True)
        return "blocked_noncanonical_demo_execution_policy"
    source_status = str(source_manifest.get("validation_status") or "")
    if not source_status_acceptable(source_status):
        add_warning(warnings, args=args, warning_code="unacceptable_margin_validation_status", message=f"Margin validation status is not acceptable: {source_status}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_unacceptable_margin_validation_status"
    if not no_order_ok:
        add_warning(warnings, args=args, warning_code="unsafe_no_order_evidence", message=f"No-order evidence failed fields: {no_order_failures}", source=source_dir / SOURCE_NO_ORDER, blocking_warning=True)
        return "blocked_unsafe_no_order_evidence"
    return plan_status_for(source_manifest)


def main_rows(args: argparse.Namespace, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    source = Path(args.broker_safe_margin_validation_dir) / SOURCE_MANIFEST
    items = [
        ("source_margin_validation_status", ctx["broker_safe_margin_validation_status"], "acceptable broker-safe margin validation status", "margin_validation_source_accepted", "no execution approval implied"),
        ("source_nature", ctx["source_nature"], "synthetic_fixture or live_data_shadow_signal", "source_nature_identified", "fixture remains non-actionable"),
        ("future_state_json", ctx["future_state_json"], "future target only", "future_state_target_defined", "not created or mutated here"),
        ("max_open_positions_enforcement", EXPECTED_MAX_OPEN_POSITIONS, 1, "max_open_positions_one_required", "future state and broker reconciliation required"),
        ("manual_approval_gate", "required", "manual approval before any future execution phase", "manual_approval_required", "planning-only"),
        ("duplicate_protection", "required", "signal time and idempotency key unique", "duplicate_protection_required", "future local state check"),
        ("crash_recovery", "required", "reconciliation_hold on ambiguous state", "crash_recovery_required", "future module required"),
        ("future_broker_reads", "planned", "future-only separate reconciliation module", "future_broker_reads_planned_only", "not called here"),
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


def state_schema_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    statuses = ";".join(STATE_STATUSES)
    return [
        {
            "run_id": args.run_id,
            "state_field": field,
            "field_role": "future_local_demo_state",
            "required": True,
            "future_state_statuses": statuses,
            "source_or_future_input": "source_artifact_or_future_manual_gate",
            "caveat": "schema planning only; state file is not created or mutated here",
        }
        for field in STATE_FIELDS
    ]


def idempotency_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    components = [
        "candidate_id",
        "symbol",
        "timeframe",
        "direction",
        "signal_time_server",
        "entry_reference_price",
        "sl_price",
        "tp_price",
    ]
    rows: list[dict[str, Any]] = []
    for index, component in enumerate(components, start=1):
        rows.append(
            {
                "run_id": args.run_id,
                "idempotency_area": "composition",
                "composition_order": index,
                "component_name": component,
                "expected_source": "future local signal/state artifact",
                "future_local_state_only": True,
                "not_broker_request_field": True,
                "caveat": "candidate_id+symbol+timeframe+direction+signal_time_server+entry_reference_price+sl_price+tp_price",
            }
        )
    rows.extend(
        [
            {
                "run_id": args.run_id,
                "idempotency_area": "duplicate_protection",
                "composition_order": "",
                "component_name": "no_duplicate_signal_time_server",
                "expected_source": "future local state",
                "future_local_state_only": True,
                "not_broker_request_field": True,
                "caveat": "block duplicate signal_time_server",
            },
            {
                "run_id": args.run_id,
                "idempotency_area": "duplicate_protection",
                "composition_order": "",
                "component_name": "no_duplicate_idempotency_key",
                "expected_source": "future local state",
                "future_local_state_only": True,
                "not_broker_request_field": True,
                "caveat": "block duplicate idempotency_key",
            },
            {
                "run_id": args.run_id,
                "idempotency_area": "duplicate_protection",
                "composition_order": "",
                "component_name": "block_when_local_state_open_or_pending",
                "expected_source": "future local state",
                "future_local_state_only": True,
                "not_broker_request_field": True,
                "caveat": "block new signal while open, pending manual review, or approved pending future execution",
            },
        ]
    )
    return rows


def failure_mode_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = [
        ("crash_before_state_write", "missing state for source signal", "rerun can rebuild signal_seen or require manual review"),
        ("crash_after_signal_seen_state_write", "state_status=signal_seen without manual review", "resume pending_manual_review"),
        ("crash_before_manual_approval", "pending_manual_review", "keep waiting for manual decision"),
        ("crash_after_manual_approval_before_future_execution", "manually_approved_pending_execution", "future reconciliation required before any later module"),
        ("future_execution_submitted_but_state_write_failed", "broker/local mismatch future-only", "reconciliation_hold"),
        ("local_state_says_open_broker_says_no_matching_position", "future broker read mismatch", "reconciliation_hold"),
        ("broker_says_open_local_state_missing", "future broker read mismatch", "reconciliation_hold"),
        ("duplicate_run_on_same_signal", "duplicate idempotency_key", "duplicate_blocked"),
        ("stale_state_older_than_horizon", "state age exceeds horizon", "stale_signal_blocked"),
    ]
    return [
        {
            "run_id": args.run_id,
            "failure_mode": mode,
            "planned_detection": detection,
            "planned_response": response,
            "blocking_until_resolved": True,
            "caveat": "future local state and future broker reconciliation only; not executed here",
        }
        for mode, detection, response in rows
    ]


def future_broker_read_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = [
        ("positions_reconciliation", "positions_get", True, True, "allowed only in separately planned future reconciliation module"),
        ("orders_reconciliation_if_needed", "orders_get", True, True, "allowed only in separately planned future reconciliation module if needed"),
        ("history_orders_forbidden_until_separately_planned", "history_orders_get", True, False, "remains forbidden unless separately planned"),
        ("history_deals_forbidden_until_separately_planned", "history_deals_get", True, False, "remains forbidden unless separately planned"),
    ]
    return [
        {
            "run_id": args.run_id,
            "future_read_label": label,
            "future_call_name": name,
            "allowed_only_in_future_reconciliation_module": future_only,
            "current_module_called": False,
            "required_before_future_execution": required,
            "caveat": caveat,
        }
        for label, name, future_only, required, caveat in rows
    ]


def manifest_data(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    ctx: dict[str, Any],
    outputs: dict[str, Path],
    state_schema: list[dict[str, Any]],
    idempotency: list[dict[str, Any]],
    failure_modes: list[dict[str, Any]],
    future_reads: list[dict[str, Any]],
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
        "broker_safe_margin_validation_dir": str(args.broker_safe_margin_validation_dir),
        "broker_safe_margin_validation_status": ctx["broker_safe_margin_validation_status"],
        "future_state_json": str(args.future_state_json),
        "max_open_positions": EXPECTED_MAX_OPEN_POSITIONS,
        "state_schema_row_count": len(state_schema),
        "idempotency_row_count": len(idempotency),
        "failure_mode_row_count": len(failure_modes),
        "future_broker_read_row_count": len(future_reads),
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
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
        "future_state_json_created_or_mutated": False,
    }


def write_report(path: Path, *, ctx: dict[str, Any], args: argparse.Namespace, warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo State Reconciliation Plan",
        "",
        "Artifact-only state reconciliation planning.",
        "No MT5 import or connection was performed.",
        "No broker/API/account/symbol query was performed.",
        "No database query or mutation was performed.",
        "No child script was executed.",
        "No broker request dictionary or order object was constructed.",
        "No order execution or demo approval was performed.",
        "No trading decision or candidate-quality final decision was made.",
        "No scheduler, loop, daemon, or background task was added.",
        "Future state JSON path is a target only and was not created or mutated.",
        "",
        "## Source Summary",
        "",
        f"- broker_safe_margin_validation_dir: `{args.broker_safe_margin_validation_dir}`",
        f"- broker_safe_margin_validation_status: `{ctx['broker_safe_margin_validation_status']}`",
        f"- source_nature: `{ctx['source_nature']}`",
        f"- plan_status: `{ctx['plan_status']}`",
        f"- future_state_json: `{args.future_state_json}`",
        "",
        "## Idempotency And Duplicate Protection",
        "",
        "Idempotency composition: candidate_id + symbol + timeframe + direction + signal_time_server + entry_reference_price + sl_price + tp_price.",
        "The idempotency key is future local-state-only and not a broker request field.",
        "Duplicate protection requires max_open_positions = 1, no duplicate signal_time_server, no duplicate idempotency_key, and no new signal while local state is open or pending.",
        "",
        "## Crash Recovery",
        "",
        "Ambiguous local-vs-future-broker state must enter reconciliation_hold until manually resolved.",
        "",
        "## Future Broker Reads",
        "",
        "positions_get and orders_get are planning-only future reads in a separately planned reconciliation module.",
        "history_orders_get and history_deals_get remain forbidden unless separately planned.",
        "This module itself does not call broker read functions.",
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
    source_dir = Path(args.broker_safe_margin_validation_dir)
    source_manifest, source_manifest_error = read_json(source_dir / SOURCE_MANIFEST)
    margin_snapshot, margin_snapshot_error = read_json(source_dir / SOURCE_MARGIN_SNAPSHOT)
    no_order_rows_source, no_order_error = read_csv_rows(source_dir / SOURCE_NO_ORDER)
    _report, report_error = read_text(source_dir / SOURCE_REPORT)
    _checklist_rows, checklist_error = read_csv_rows(source_dir / SOURCE_CHECKLIST)
    source_warnings, source_warnings_error = read_csv_rows(source_dir / SOURCE_WARNINGS)
    if not source_warnings_error:
        warnings.extend(preserve_source_warnings(args, source_warnings, source_dir / SOURCE_WARNINGS))
    if report_error == "missing":
        add_warning(warnings, args=args, warning_code="source_report_missing", message="Source report is missing.", source=source_dir / SOURCE_REPORT, blocking_warning=False)
    if checklist_error == "missing":
        add_warning(warnings, args=args, warning_code="source_checklist_missing", message="Source checklist is missing.", source=source_dir / SOURCE_CHECKLIST, blocking_warning=False)

    canonical_ok = not registry_error and not policy_error and canonical_registry_valid(registry, policy)
    policy_ok = not policy_error and execution_policy_valid(policy)
    no_order_ok, no_order_failures = no_order_evidence_valid(no_order_rows_source)
    plan_status = determine_plan_status(
        args=args,
        registry=registry,
        registry_error=registry_error,
        policy=policy,
        policy_error=policy_error,
        source_manifest=source_manifest,
        source_manifest_error=source_manifest_error,
        margin_snapshot=margin_snapshot,
        margin_snapshot_error=margin_snapshot_error,
        no_order_rows=no_order_rows_source,
        no_order_error=no_order_error,
        canonical_ok=canonical_ok,
        policy_ok=policy_ok,
        no_order_ok=no_order_ok,
        no_order_failures=no_order_failures,
        warnings=warnings,
    )
    if source_manifest.get("source_nature") == "synthetic_fixture":
        add_warning(warnings, args=args, warning_code="fixture_only_source", message="Broker-safe margin validation source is fixture-only and non-actionable.", source=source_dir / SOURCE_MANIFEST, blocking_warning=False)
    if safe_float(source_manifest.get("broker_margin_usage_ratio")) is not None and safe_float(source_manifest.get("broker_margin_usage_ratio")) > EXPECTED_WARNING_RATIO:
        add_warning(warnings, args=args, warning_code="inherited_margin_warning", message="Broker-safe margin validation inherited a margin warning above 50% and below cap.", source=source_dir / SOURCE_MANIFEST, blocking_warning=False)
    add_warning(warnings, args=args, warning_code="future_broker_reads_planning_only", message="Future broker reads are planning-only and not executed by this module.", source="future_broker_reads", blocking_warning=False)
    add_warning(warnings, args=args, warning_code="future_state_json_not_created", message="Future state JSON path is a target only and was not created or mutated.", source=args.future_state_json, blocking_warning=False)

    ctx = {
        "plan_status": plan_status,
        "source_nature": source_manifest.get("source_nature", "unknown"),
        "broker_safe_margin_validation_status": source_manifest.get("validation_status", ""),
        "future_state_json": str(args.future_state_json),
        "recommended_next_step": recommended_next_step(plan_status),
    }
    state_schema = state_schema_rows(args)
    idempotency = idempotency_rows(args)
    failure_modes = failure_mode_rows(args)
    future_reads = future_broker_read_rows(args)
    write_csv(outputs["main"], main_rows(args, ctx), MAIN_FIELDNAMES)
    write_csv(outputs["state_schema"], state_schema, STATE_SCHEMA_FIELDNAMES)
    write_csv(outputs["idempotency"], idempotency, IDEMPOTENCY_FIELDNAMES)
    write_csv(outputs["failure_modes"], failure_modes, FAILURE_MODE_FIELDNAMES)
    write_csv(outputs["future_broker_reads"], future_reads, FUTURE_BROKER_READ_FIELDNAMES)
    write_csv(outputs["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(outputs["report"], ctx=ctx, args=args, warnings=warnings)
    write_json(
        outputs["manifest"],
        manifest_data(
            args=args,
            output_dir=output_dir,
            ctx=ctx,
            outputs=outputs,
            state_schema=state_schema,
            idempotency=idempotency,
            failure_modes=failure_modes,
            future_reads=future_reads,
            warnings=warnings,
        ),
    )
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only fixed-candidate demo state reconciliation plan.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--broker-safe-margin-validation-dir", type=Path, default=DEFAULT_BROKER_SAFE_MARGIN_DIR)
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
        print(f"Fixed-candidate demo state reconciliation plan failed: {exc}")
        return 1
    print("Fixed-candidate demo state reconciliation plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
