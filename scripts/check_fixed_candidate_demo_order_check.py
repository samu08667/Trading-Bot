"""Run a gated fixed-candidate demo order-check stage.

Default behavior is dry-run/no-broker: the script reads existing artifacts,
validates gates, writes status evidence, and does not import/connect to MT5.
Real order-check mode is available only with ``--allow-real-order-check`` and
only after non-fixture upstream artifacts and all safety gates pass. This module
never sends orders, executes orders, writes future trading state, mutates a DB,
runs child scripts, or creates scheduler/loop/background behavior.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts._fixed_candidate_artifact_freshness import (
        ARTIFACT_FRESHNESS_FIELDNAMES,
        DEFAULT_MAX_ARTIFACT_AGE_MINUTES,
        artifact_freshness_summary,
        evaluate_artifact_freshness,
        status_is_stale,
    )
    from scripts import fixed_candidate_demo_state_contracts as state_contracts
except ModuleNotFoundError:
    from _fixed_candidate_artifact_freshness import (
        ARTIFACT_FRESHNESS_FIELDNAMES,
        DEFAULT_MAX_ARTIFACT_AGE_MINUTES,
        artifact_freshness_summary,
        evaluate_artifact_freshness,
        status_is_stale,
    )
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
DIGEST_ALGORITHM = "sha256"
DIGEST_CANONICALIZATION = "canonical_json_or_documented_csv_rule"
ACCEPTABLE_MARGIN_VALIDATION_STATUSES = {
    "broker_safe_margin_validation_available",
    "broker_safe_margin_validation_available_with_margin_warning",
}
VOLUME_TOLERANCE = 1e-9
REQUEST_CONSTRUCTION_AVAILABLE_STATUS = "request_construction_dry_run_available_non_executable"
REQUEST_CONSTRUCTION_STALE_OVERRIDE_STATUS = (
    "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
)
REQUEST_CONSTRUCTION_ACCEPTABLE_STATUSES = {
    REQUEST_CONSTRUCTION_AVAILABLE_STATUS,
    REQUEST_CONSTRUCTION_STALE_OVERRIDE_STATUS,
}
MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT = (
    "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only"
)
EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT = "acknowledge_expired_signal_for_demo_module_validation_only"
CLIENT_AUTOTRADING_DISABLED_RETCODE = state_contracts.CLIENT_AUTOTRADING_DISABLED_RETCODE
CLIENT_REJECT_RESEND_ACKNOWLEDGMENT = state_contracts.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT
ORDER_CHECK_REQUIRED_PAYLOAD_FIELDS = [
    "action",
    "symbol",
    "volume",
    "type",
    "price",
    "sl",
    "tp",
    "deviation",
    "magic",
    "comment",
    "type_time",
    "type_filling",
]
ORDER_CHECK_NUMERIC_PAYLOAD_FIELDS = {"volume", "price", "sl", "tp"}
ORDER_CHECK_INT_PAYLOAD_FIELDS = {"action", "type", "deviation", "magic", "type_time", "type_filling"}
PLACEHOLDER_PAYLOAD_TOKENS = (
    "placeholder",
    "preview",
    "policy",
    "descriptor",
    "future_",
    "intent",
    "redacted_non_executable",
)
BROKER_COMMENT_MAX_LENGTH = 20
BROKER_COMMENT_IDEMPOTENCY_SUFFIX_LENGTH = 6

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_order_check"
DEFAULT_REQUEST_CONSTRUCTION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_request_construction_dry_run"
    / "gbpusd_short_h10_1_5_off_hours_demo_request_construction_dry_run_fixture_v1"
)
DEFAULT_ORDER_CHECK_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_order_check_readiness_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_order_check_readiness_plan_fixture_v1"
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
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_DEMO_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR / "state" / "fixed_candidate_demo_state" / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_order_check"

REQUEST_MANIFEST = "fixed_candidate_demo_request_construction_dry_run_manifest.json"
REQUEST_INTENT = "fixed_candidate_demo_request_construction_dry_run_request_intent.csv"
REQUEST_FIELDS = "fixed_candidate_demo_request_construction_dry_run_request_fields.csv"
READINESS_MANIFEST = "fixed_candidate_demo_order_check_readiness_plan_manifest.json"
READINESS_INPUTS = "fixed_candidate_demo_order_check_readiness_plan_future_order_check_inputs.csv"
READINESS_BROKER_FIELDS = "fixed_candidate_demo_order_check_readiness_plan_future_broker_request_fields.csv"
READINESS_PRE_RECHECKS = "fixed_candidate_demo_order_check_readiness_plan_pre_order_check_rechecks.csv"
SCHEMA_MANIFEST = "fixed_candidate_demo_manual_approval_record_schema_manifest.json"
BROKER_RECON_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
MARGIN_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"
FRESHNESS_MANIFEST = "fixed_candidate_demo_live_signal_freshness_manifest.json"
DUPLICATE_MANIFEST = "fixed_candidate_demo_duplicate_protection_plan_manifest.json"
MANUAL_PLAN_MANIFEST = "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_order_check_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_order_check_report.md"
OUTPUT_GATES = "fixed_candidate_demo_order_check_gate_checks.csv"
OUTPUT_BOUND_INTENT = "fixed_candidate_demo_order_check_bound_request_intent.csv"
OUTPUT_PREVIEW = "fixed_candidate_demo_order_check_order_check_payload_preview.csv"
OUTPUT_BROKER_SNAPSHOT = "fixed_candidate_demo_order_check_broker_snapshot.json"
OUTPUT_RESULT_SNAPSHOT = "fixed_candidate_demo_order_check_result_snapshot.json"
OUTPUT_STATUS = "fixed_candidate_demo_order_check_status.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_order_check_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_order_check_no_order_evidence.csv"
OUTPUT_ARTIFACT_FRESHNESS = "fixed_candidate_demo_order_check_artifact_freshness_checks.csv"

WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
GATE_FIELDNAMES = [
    "run_id",
    "check_name",
    "gate_name",
    "gate_status",
    "observed_value",
    "expected_value",
    "source_path",
    "blocking_if_failed",
    "warning_code",
]
BOUND_INTENT_FIELDNAMES = [
    "run_id",
    "request_construction_dry_run_dir",
    "request_intent_path",
    "request_construction_status",
    "request_intent_created",
    "signal_id",
    "idempotency_key",
    "approval_record_id",
    "binding_status",
]
PREVIEW_FIELDNAMES = [
    "run_id",
    "field_name",
    "preview_value",
    "source",
    "redacted",
    "broker_payload_field_now",
    "executable_now",
    "caveat",
]
STATUS_FIELDNAMES = [
    "run_id",
    "order_check_status",
    "dry_run",
    "allow_real_order_check",
    "order_check_called",
    "order_check_call_count",
    "order_check_retcode",
    "order_check_passed",
    "order_send_called",
    "order_execution_performed",
    "recommended_next_step",
]
NO_ORDER_FIELDNAMES = [
    "run_id",
    "no_order_send_called",
    "no_order_execution_performed",
    "no_future_state_json_written",
    "no_db_mutation_performed",
    "no_child_scripts_executed",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "no_trading_decision_performed",
    "no_demo_broker_approval_performed",
    "no_mt5_import_performed",
    "no_mt5_connection_performed",
    "no_broker_api_query_performed",
    "no_order_check_called",
    "mt5_import_performed",
    "mt5_connection_performed",
    "broker_api_query_performed",
    "order_check_called",
    "order_check_call_count",
    "evidence_label",
    "caveat",
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


def object_value(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def object_dict(obj: Any, fields: list[str]) -> dict[str, Any]:
    return {field: object_value(obj, field) for field in fields}


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


def canonical_json_bytes(content: dict[str, Any]) -> bytes:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_payload(content: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip()
    return len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text)


def output_dir_for(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "gate_checks": output_dir / OUTPUT_GATES,
        "bound_intent": output_dir / OUTPUT_BOUND_INTENT,
        "payload_preview": output_dir / OUTPUT_PREVIEW,
        "broker_snapshot": output_dir / OUTPUT_BROKER_SNAPSHOT,
        "result_snapshot": output_dir / OUTPUT_RESULT_SNAPSHOT,
        "status": output_dir / OUTPUT_STATUS,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
        "artifact_freshness": output_dir / OUTPUT_ARTIFACT_FRESHNESS,
    }


def ensure_outputs_writable(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError("Output files already exist. Use --overwrite to replace them.")
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)


def source_paths(args: argparse.Namespace) -> dict[str, Path]:
    request_dir = Path(args.request_construction_dry_run_dir)
    readiness_dir = Path(args.order_check_readiness_plan_dir)
    schema_dir = Path(args.manual_approval_record_schema_dir)
    return {
        "registry": Path(args.canonical_registry),
        "policy": Path(args.demo_execution_policy),
        "request_manifest": request_dir / REQUEST_MANIFEST,
        "request_intent": request_dir / REQUEST_INTENT,
        "request_fields": request_dir / REQUEST_FIELDS,
        "readiness_manifest": readiness_dir / READINESS_MANIFEST,
        "readiness_inputs": readiness_dir / READINESS_INPUTS,
        "readiness_broker_fields": readiness_dir / READINESS_BROKER_FIELDS,
        "readiness_pre_rechecks": readiness_dir / READINESS_PRE_RECHECKS,
        "approval_record": Path(args.manual_approval_record_json),
        "schema_manifest": schema_dir / SCHEMA_MANIFEST,
        "reconciliation": Path(args.broker_local_reconciliation_dir) / BROKER_RECON_MANIFEST,
        "margin": Path(args.broker_safe_margin_validation_dir) / MARGIN_MANIFEST,
        "margin_snapshot": Path(args.broker_safe_margin_validation_dir) / MARGIN_SNAPSHOT,
        "freshness": Path(args.live_signal_freshness_dir) / FRESHNESS_MANIFEST,
        "duplicate": Path(args.duplicate_protection_plan_dir) / DUPLICATE_MANIFEST,
        "manual_plan": Path(args.manual_approval_kill_switch_plan_dir) / MANUAL_PLAN_MANIFEST,
        "future_state": Path(args.future_state_json),
        "request_dir": request_dir,
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
        ("order_send_not_called", "This module does not call order-send paths."),
        ("order_execution_not_performed", "This module does not execute orders."),
        ("future_state_not_written", "This module does not write future trading state JSON."),
        ("order_check_gated", "Real order-check mode requires --allow-real-order-check and passing non-fixture gates."),
    ):
        add_warning(
            warnings,
            args=args,
            warning_code=code,
            message=message,
            source="fixed_candidate_demo_order_check",
            blocking_warning=False,
            severity="info",
        )


def artifact_freshness_checks(args: argparse.Namespace, inputs: dict[str, Any], blocking: bool) -> list[dict[str, Any]]:
    paths = inputs["paths"]
    max_age = float(args.max_artifact_age_minutes)
    specs = [
        {
            "artifact_name": "request_construction",
            "path": paths["request_manifest"],
            "payload": inputs["request_manifest"],
            "max_age_minutes": max_age,
            "blocking_if_stale": blocking,
        },
        {
            "artifact_name": "live_signal_freshness",
            "path": paths["freshness"],
            "payload": inputs["freshness"],
            "max_age_minutes": max_age,
            "blocking_if_stale": blocking,
        },
        {
            "artifact_name": "broker_local_reconciliation",
            "path": paths["reconciliation"],
            "payload": inputs["reconciliation"],
            "max_age_minutes": max_age,
            "blocking_if_stale": blocking,
        },
        {
            "artifact_name": "broker_safe_margin_validation",
            "path": paths["margin"],
            "payload": inputs["margin"],
            "max_age_minutes": max_age,
            "blocking_if_stale": blocking,
        },
    ]
    return evaluate_artifact_freshness(specs)


def add_artifact_freshness_warnings(
    args: argparse.Namespace,
    warnings: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        if not status_is_stale(row["status"]):
            continue
        blocking = row.get("blocking_if_stale") is True
        add_warning(
            warnings,
            args=args,
            warning_code="order_check_blocked_stale_upstream_artifact" if blocking else "stale_upstream_artifact_warning",
            message=f"Artifact freshness check failed for {row['artifact_name']}: {row['status']}.",
            source=row["path"],
            blocking_warning=blocking,
        )


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    paths = source_paths(args)
    inputs: dict[str, Any] = {"paths": paths}
    json_keys = (
        "registry",
        "policy",
        "request_manifest",
        "readiness_manifest",
        "approval_record",
        "schema_manifest",
        "reconciliation",
        "margin",
        "margin_snapshot",
        "freshness",
        "duplicate",
        "manual_plan",
    )
    for key in json_keys:
        data, error = read_json(paths[key])
        inputs[key] = data
        inputs[f"{key}_error"] = error
    for key in ("request_intent", "request_fields", "readiness_inputs", "readiness_broker_fields", "readiness_pre_rechecks"):
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


def effective_dry_run(args: argparse.Namespace) -> bool:
    if args.dry_run is True:
        return True
    if args.dry_run is False and not args.allow_real_order_check:
        return False
    if args.allow_real_order_check:
        return False
    return True


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


def validate_request_manifest(manifest: dict[str, Any]) -> bool:
    status = manifest.get("request_construction_status")
    stale_override_status = status == REQUEST_CONSTRUCTION_STALE_OVERRIDE_STATUS
    if stale_override_status and not (
        manifest.get("module_validation_demo_execution") is True
        and manifest.get("stale_override_used") is True
        and manifest.get("strategy_valid") is False
        and manifest.get("production_valid") is False
        and manifest.get("order_check_allowed_for_demo_module_validation_only") is True
        and manifest.get("order_send_allowed_for_demo_module_validation_only") is False
    ):
        return False
    return (
        status in REQUEST_CONSTRUCTION_ACCEPTABLE_STATUSES
        and manifest.get("request_intent_created") is True
        and manifest.get("broker_payload_constructed") is False
        and manifest.get("executable_order_object_constructed") is False
        and manifest.get("order_check_called") is False
        and manifest.get("order_send_called") is False
        and manifest.get("order_execution_performed") is False
        and manifest.get("order_check_allowed_now") is False
        and manifest.get("order_send_allowed_now") is False
        and manifest.get("request_construction_mode") == "dry_run_non_executable"
    )


def request_demo_module_validation_manifest(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("request_construction_status") == REQUEST_CONSTRUCTION_STALE_OVERRIDE_STATUS
        and manifest.get("module_validation_demo_execution") is True
        and manifest.get("strategy_valid") is False
        and manifest.get("production_valid") is False
        and manifest.get("order_check_allowed_for_demo_module_validation_only") is True
        and manifest.get("order_send_allowed_for_demo_module_validation_only") is False
    )


def module_validation_order_check_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return (
        args.allow_real_order_check is True
        and args.module_validation_demo_execution is True
        and args.module_validation_acknowledgment == MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT
        and request_demo_module_validation_manifest(inputs["request_manifest"])
    )


def expired_signal_override_requested(args: argparse.Namespace) -> bool:
    return bool(args.allow_expired_signal_for_demo_module_validation or args.expired_signal_override_acknowledgment)


def expired_signal_override_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return (
        module_validation_order_check_allowed(args, inputs)
        and args.allow_expired_signal_for_demo_module_validation is True
        and args.expired_signal_override_acknowledgment == EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT
    )


def approval_record_expired(record: dict[str, Any]) -> bool:
    expiry = parse_time(record.get("approval_expiry_time_utc"))
    return expiry is None or expiry <= utc_now()


def validate_readiness_manifest(manifest: dict[str, Any], args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    if (
        manifest.get("order_check_readiness_status") == "order_check_readiness_plan_fixture_only_no_request_intent"
        and module_validation_order_check_allowed(args, inputs)
    ):
        return True
    return (
        manifest.get("order_check_readiness_status") == "order_check_readiness_plan_available_no_order_check"
        and manifest.get("future_order_check_ready") is True
        and manifest.get("order_check_allowed_now") is False
        and manifest.get("order_check_callable_future_only") is True
        and manifest.get("order_send_allowed_now") is False
        and manifest.get("order_execution_allowed") is False
        and manifest.get("broker_payload_constructed") is False
        and manifest.get("executable_order_object_constructed") is False
        and manifest.get("order_check_called") is False
        and manifest.get("order_send_called") is False
    )


def first_intent(inputs: dict[str, Any]) -> dict[str, str]:
    return inputs["request_intent"][0] if inputs["request_intent"] else {}


def false_csv(value: Any) -> bool:
    return str(value).lower() == "false"


def validate_intent(intent: dict[str, str]) -> bool:
    return (
        intent.get("side") == SIDE_INTENT
        and intent.get("order_type_intent") == ORDER_TYPE_INTENT
        and intent.get("symbol") == SYMBOL
        and intent.get("timeframe") == TIMEFRAME
        and intent.get("direction") == DIRECTION
        and (safe_float(intent.get("volume_lots")) or 0) > 0
        and bool(intent.get("entry_reference_price"))
        and bool(intent.get("sl_price"))
        and bool(intent.get("tp_price"))
        and bool(intent.get("signal_id"))
        and bool(intent.get("idempotency_key"))
        and false_csv(intent.get("broker_payload_constructed"))
        and false_csv(intent.get("executable_order_object_constructed"))
        and false_csv(intent.get("order_check_allowed_now"))
        and false_csv(intent.get("order_send_allowed_now"))
        and false_csv(intent.get("order_execution_allowed"))
    )


def validate_request_fields(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and all(row.get("broker_payload_field_now") == "false" and row.get("executable_now") == "false" for row in rows)


def validate_readiness_descriptors(inputs: dict[str, Any]) -> bool:
    future_inputs = inputs["readiness_inputs"]
    future_fields = inputs["readiness_broker_fields"]
    rechecks = inputs["readiness_pre_rechecks"]
    return (
        bool(future_inputs)
        and bool(future_fields)
        and bool(rechecks)
        and all(row.get("broker_payload_field_now") == "false" and row.get("executable_now") == "false" for row in future_inputs)
        and all(row.get("executable_now") == "false" for row in future_fields)
        and all(row.get("required") == "true" and row.get("blocking_if_failed") == "true" for row in rechecks)
    )


def validate_schema(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("schema_status") == "manual_approval_record_schema_available_no_order"
        and manifest.get("schema_patch_status") == "schema_audit_gaps_closed_no_order"
    )


def validate_approval_record(args: argparse.Namespace, inputs: dict[str, Any]) -> tuple[bool, str]:
    record = inputs["approval_record"]
    if not record:
        return False, "order_check_blocked_missing_approval_record"
    if record.get("approval_status") != "approved_for_future_request_construction_only":
        return False, "order_check_blocked_unapproved_record"
    if record.get("approval_scope") != "future_request_construction_only":
        return False, "order_check_blocked_unapproved_record"
    checks = (
        record.get("approval_does_not_execute_order") is True,
        record.get("approval_does_not_construct_request") is True,
        record.get("approval_requires_final_pre_request_recheck") is True,
        record.get("approval_revoked") is False,
        bool(record.get("record_hash_or_digest")),
        bool(record.get("signal_id")),
        bool(record.get("idempotency_key")),
    )
    if not all(checks):
        return False, "order_check_blocked_unapproved_record"
    if approval_record_expired(record) and not expired_signal_override_allowed(args, inputs):
        return False, "order_check_blocked_expired_approval"
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


def bool_false(value: Any) -> bool:
    if isinstance(value, bool):
        return value is False
    if isinstance(value, str):
        return value.strip().lower() == "false"
    return False


def bool_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value is True
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def empty_ticket(value: Any) -> bool:
    return value in (None, "", 0, "0")


def state_status(state: dict[str, Any]) -> str:
    return state_contracts.state_status(state)


def client_reject_flat_contract(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    intent = first_intent(inputs)
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


def client_reject_flat_resend_candidate(inputs: dict[str, Any]) -> bool:
    if not inputs.get("future_state_exists"):
        return False
    state = inputs.get("future_state") or {}
    if not state:
        return False
    intent = first_intent(inputs)
    contract = state_contracts.evaluate_explicit_second_demo_send_after_client_reject_flat(
        state=state,
        signal_id=intent.get("signal_id", ""),
        idempotency_key=intent.get("idempotency_key", ""),
        module_validation_demo_execution=True,
        demo_account_only=True,
        allow_flag=True,
        acknowledgment=CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        broker_local_reconciliation=inputs.get("reconciliation") or {},
        require_broker_local_reconciliation=True,
    )
    return bool(contract["candidate"] and not contract["blocking_reasons"])


def client_reject_flat_resend_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return (
        args.allow_real_order_check is True
        and module_validation_order_check_allowed(args, inputs)
        and bool(client_reject_flat_contract(args, inputs)["accepted"])
    )


def market_closed_flat_contract(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    intent = first_intent(inputs)
    return state_contracts.evaluate_market_closed_reject_flat_new_signal(
        state=inputs.get("future_state") or {},
        signal_id=intent.get("signal_id", ""),
        idempotency_key=intent.get("idempotency_key", ""),
        broker_local_reconciliation=inputs.get("reconciliation") or {},
        require_broker_local_reconciliation=True,
    )


def market_closed_flat_new_signal_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return args.allow_real_order_check is True and bool(market_closed_flat_contract(args, inputs)["accepted"])


def future_state_incompatible(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    state = inputs.get("future_state") or {}
    if not state:
        return False
    if client_reject_flat_resend_allowed(args, inputs):
        return False
    if market_closed_flat_new_signal_allowed(args, inputs):
        return False
    incompatible, _same_key = state_contracts.future_state_is_incompatible_without_explicit_client_reject_contract(
        state,
        signal_id=first_intent(inputs).get("signal_id", ""),
        idempotency_key=first_intent(inputs).get("idempotency_key", ""),
    )
    return incompatible


def future_state_warning_code(args: argparse.Namespace, inputs: dict[str, Any]) -> str:
    if client_reject_flat_resend_candidate(inputs) and not client_reject_flat_resend_allowed(args, inputs):
        return "order_check_blocked_client_reject_resend_acknowledgment"
    return "order_check_blocked_future_state_incompatible"


def digest_binding_summary(inputs: dict[str, Any], *, required: bool) -> dict[str, Any]:
    missing_count = 0
    mismatch_count = 0
    if required:
        paths = inputs["paths"]
        request_manifest = inputs["request_manifest"]
        intent = first_intent(inputs)
        approval = inputs["approval_record"]
        checks = [
            (
                request_manifest.get("request_intent_digest"),
                sha256_file(paths["request_intent"]),
            ),
            (
                request_manifest.get("request_fields_digest"),
                sha256_file(paths["request_fields"]),
            ),
            (
                intent.get("approval_record_digest"),
                approval.get("record_hash_or_digest"),
            ),
        ]
        for expected, actual in checks:
            if not is_sha256_hex(expected) or not is_sha256_hex(actual):
                missing_count += 1
            elif str(expected).lower() != str(actual).lower():
                mismatch_count += 1
    verified = required and missing_count == 0 and mismatch_count == 0
    if not required:
        status = "digest_binding_not_required_dry_run_or_blocked"
    elif missing_count:
        status = "digest_binding_missing"
    elif mismatch_count:
        status = "digest_binding_mismatch"
    else:
        status = "digest_binding_verified"
    return {
        "digest_binding_required": required,
        "digest_binding_verified": verified,
        "digest_algorithm": DIGEST_ALGORITHM,
        "digest_canonicalization": DIGEST_CANONICALIZATION,
        "missing_digest_count": missing_count,
        "digest_mismatch_count": mismatch_count,
        "digest_verification_status": status,
    }


def digest_gate_row(args: argparse.Namespace, inputs: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return gate_row(
        args,
        "digest_binding",
        bool(summary["digest_binding_verified"]),
        f"missing={summary['missing_digest_count']};mismatch={summary['digest_mismatch_count']}",
        "approval, request intent, and request fields SHA-256 digests present and matching",
        inputs["paths"]["request_manifest"],
        (
            "order_check_blocked_missing_digest_binding"
            if summary["missing_digest_count"]
            else "order_check_blocked_digest_mismatch"
        ),
    )


def gate_row(
    args: argparse.Namespace,
    name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    path: Path | str,
    warning_code: str,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "check_name": name,
        "gate_name": name,
        "gate_status": "passed" if passed else "failed",
        "observed_value": observed,
        "expected_value": expected,
        "source_path": str(path),
        "blocking_if_failed": True,
        "warning_code": warning_code,
    }


def structural_gates(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    paths = inputs["paths"]
    approval_ok, approval_status = validate_approval_record(args, inputs)
    gates = [
        gate_row(args, "canonical_candidate", validate_canonical_registry(inputs["registry"]), inputs["registry"].get("candidate_id"), CANDIDATE_ID, paths["registry"], "order_check_blocked_noncanonical_candidate"),
        gate_row(args, "demo_execution_policy", validate_demo_policy(inputs["policy"]), inputs["policy"].get("policy_id", ""), "safe base policy with order execution/check/calc disabled", paths["policy"], "order_check_blocked_noncanonical_demo_execution_policy"),
        gate_row(args, "request_construction_manifest", validate_request_manifest(inputs["request_manifest"]), inputs["request_manifest"].get("request_construction_status"), "non-executable request construction dry-run", paths["request_manifest"], "order_check_blocked_fixture_only_no_request_intent"),
        gate_row(args, "request_intent", validate_intent(first_intent(inputs)), len(inputs["request_intent"]), "non-executable intent with volume/prices/ids", paths["request_intent"], "order_check_blocked_fixture_only_no_request_intent"),
        gate_row(args, "request_fields", validate_request_fields(inputs["request_fields"]), len(inputs["request_fields"]), "all descriptors non-executable", paths["request_fields"], "order_check_blocked_fixture_only_no_request_intent"),
        gate_row(args, "order_check_readiness_manifest", validate_readiness_manifest(inputs["readiness_manifest"], args, inputs), inputs["readiness_manifest"].get("order_check_readiness_status"), "readiness available no order-check or explicit demo module validation order-check", paths["readiness_manifest"], "order_check_blocked_fixture_only_no_order_check_readiness"),
        gate_row(args, "order_check_readiness_descriptors", validate_readiness_descriptors(inputs), "descriptor rows", "all descriptor/recheck rows non-executable and blocking", paths["readiness_manifest"], "order_check_blocked_fixture_only_no_order_check_readiness"),
        gate_row(args, "manual_approval_schema", validate_schema(inputs["schema_manifest"]), inputs["schema_manifest"].get("schema_status"), "manual approval schema available no-order", paths["schema_manifest"], "order_check_blocked_unapproved_record"),
        gate_row(args, "manual_approval_record", approval_ok, inputs["approval_record"].get("approval_status", inputs["approval_record_error"]), "approved non-revoked non-expired approval", paths["approval_record"], approval_status or "order_check_blocked_unapproved_record"),
        gate_row(args, "live_signal_freshness", validate_freshness(inputs["freshness"]), inputs["freshness"].get("freshness_status"), "fresh signal within h10", paths["freshness"], "order_check_blocked_stale_signal"),
        gate_row(args, "broker_local_reconciliation", validate_reconciliation(inputs["reconciliation"]), inputs["reconciliation"].get("reconciliation_status"), "clean no local/no broker", paths["reconciliation"], "order_check_blocked_broker_local_reconciliation"),
        gate_row(args, "broker_safe_margin", validate_margin(inputs["margin"], inputs["margin_snapshot"]), inputs["margin"].get("broker_margin_usage_ratio"), "demo margin <= 0.70 and spread within policy", paths["margin"], "order_check_blocked_margin_policy"),
        gate_row(args, "duplicate_protection", validate_duplicate(inputs["duplicate"]), inputs["duplicate"].get("plan_status"), "duplicate protection available", paths["duplicate"], "order_check_blocked_duplicate_protection"),
        gate_row(args, "manual_approval_kill_switch", validate_manual_plan(inputs["manual_plan"]), inputs["manual_plan"].get("plan_status"), "kill-switch inactive", paths["manual_plan"], "order_check_blocked_kill_switch"),
        gate_row(
            args,
            "future_state_compatible",
            not future_state_incompatible(args, inputs),
            state_status(inputs.get("future_state") or {}) if inputs["future_state_exists"] else "missing",
            "missing, compatible terminal state, or explicit demo client-reject-flat resend",
            paths["future_state"],
            future_state_warning_code(args, inputs),
        ),
    ]
    if request_demo_module_validation_manifest(inputs["request_manifest"]):
        gates.append(
            gate_row(
                args,
                "module_validation_order_check_acknowledgment",
                module_validation_order_check_allowed(args, inputs),
                (
                    f"allow_real_order_check={args.allow_real_order_check};"
                    f"module_validation_demo_execution={args.module_validation_demo_execution};"
                    f"ack={args.module_validation_acknowledgment or ''}"
                ),
                f"real demo order_check with ack={MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT}",
                paths["request_manifest"],
                "order_check_blocked_module_validation_acknowledgment",
            )
        )
    if expired_signal_override_requested(args):
        gates.append(
            gate_row(
                args,
                "expired_signal_override_acknowledgment",
                expired_signal_override_allowed(args, inputs),
                (
                    f"allow_expired={args.allow_expired_signal_for_demo_module_validation};"
                    f"ack={args.expired_signal_override_acknowledgment or ''}"
                ),
                f"demo module validation expired signal override with ack={EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT}",
                paths["approval_record"],
                "order_check_blocked_expired_signal_override_acknowledgment",
            )
        )
    return gates


def status_from_gates(inputs: dict[str, Any], gates: list[dict[str, Any]], dry_run: bool) -> str:
    req_status = inputs["request_manifest"].get("request_construction_status")
    readiness_status = inputs["readiness_manifest"].get("order_check_readiness_status")
    if req_status == "request_construction_dry_run_fixture_only_no_approval_record":
        return "order_check_blocked_fixture_only_no_request_intent"
    if (
        readiness_status == "order_check_readiness_plan_fixture_only_no_request_intent"
        and not request_demo_module_validation_manifest(inputs["request_manifest"])
    ):
        return "order_check_blocked_fixture_only_no_order_check_readiness"
    failures = [row for row in gates if row["gate_status"] == "failed"]
    if request_demo_module_validation_manifest(inputs["request_manifest"]):
        for row in failures:
            if row["gate_name"] in {
                "module_validation_order_check_acknowledgment",
                "expired_signal_override_acknowledgment",
            }:
                return str(row["warning_code"])
    if failures:
        code = str(failures[0]["warning_code"])
        if code.startswith("order_check_"):
            return code
    if dry_run:
        return "order_check_dry_run_no_broker_call"
    return ""


def record_gate_warnings(args: argparse.Namespace, gates: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    for row in gates:
        if row["gate_status"] == "failed":
            add_warning(
                warnings,
                args=args,
                warning_code=str(row["warning_code"]),
                message=f"Gate failed: {row['gate_name']}",
                source=str(row["source_path"]),
                blocking_warning=True,
            )


def account_is_demo(mt5: Any, account: Any) -> bool:
    trade_mode = object_value(account, "trade_mode")
    demo_mode = object_value(mt5, "ACCOUNT_TRADE_MODE_DEMO")
    if demo_mode is None:
        return str(trade_mode).lower() == "demo"
    return trade_mode == demo_mode


def import_mt5_module() -> Any:
    return importlib.import_module("MetaTrader5")


def ascii_alnum_slug(value: Any) -> str:
    return "".join(char.lower() for char in str(value or "") if char.isascii() and char.isalnum())


def broker_comment_is_safe(comment: Any) -> bool:
    if not isinstance(comment, str):
        return False
    if not comment or len(comment) > BROKER_COMMENT_MAX_LENGTH:
        return False
    return all(char.isascii() and char.isalnum() for char in comment)


def build_broker_safe_comment(candidate_id: Any, idempotency_key: Any) -> str:
    candidate_slug = ascii_alnum_slug(candidate_id)
    idempotency_slug = ascii_alnum_slug(idempotency_key)
    if not candidate_slug or not idempotency_slug:
        return ""
    suffix_length = min(BROKER_COMMENT_IDEMPOTENCY_SUFFIX_LENGTH, len(idempotency_slug))
    idempotency_suffix = idempotency_slug[-suffix_length:]
    candidate_budget = max(1, BROKER_COMMENT_MAX_LENGTH - len(idempotency_suffix))
    return f"{candidate_slug[:candidate_budget]}{idempotency_suffix}"


def redacted_comment_preview(comment: Any) -> str:
    text = str(comment or "")
    if not text:
        return ""
    if len(text) <= 6:
        return f"{text[:2]}***"
    return f"{text[:4]}***{text[-2:]}"


def build_check_args(mt5: Any, intent: dict[str, str], tick: Any) -> dict[str, Any]:
    price = object_value(tick, "bid")
    return dict(
        action=object_value(mt5, "TRADE_ACTION_DEAL"),
        symbol=SYMBOL,
        volume=safe_float(intent.get("volume_lots")),
        type=object_value(mt5, "ORDER_TYPE_SELL"),
        price=price,
        sl=safe_float(intent.get("sl_price")),
        tp=safe_float(intent.get("tp_price")),
        deviation=10,
        magic=151015,
        comment=build_broker_safe_comment(CANDIDATE_ID, intent.get("idempotency_key", "")),
        type_time=object_value(mt5, "ORDER_TIME_GTC"),
        type_filling=object_value(mt5, "ORDER_FILLING_IOC"),
    )


def mt5_last_error_snapshot(mt5: Any) -> Any:
    last_error = getattr(mt5, "last_error", None)
    if not callable(last_error):
        return ""
    try:
        value = last_error()
    except Exception as exc:  # noqa: BLE001
        return {"last_error_exception": str(exc)}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, dict):
        return value
    return str(value)


def value_has_placeholder_token(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    return any(token in text for token in PLACEHOLDER_PAYLOAD_TOKENS)


def payload_diagnostics(check_args: dict[str, Any]) -> dict[str, Any]:
    missing_fields: list[str] = []
    invalid_fields: list[str] = []
    placeholder_fields: list[str] = []
    for field in ORDER_CHECK_REQUIRED_PAYLOAD_FIELDS:
        value = check_args.get(field)
        if value in (None, ""):
            missing_fields.append(field)
            continue
        if value_has_placeholder_token(value):
            placeholder_fields.append(field)
        if field in ORDER_CHECK_NUMERIC_PAYLOAD_FIELDS:
            numeric = safe_float(value)
            if numeric is None or not math.isfinite(numeric) or numeric <= 0:
                invalid_fields.append(field)
        if field in ORDER_CHECK_INT_PAYLOAD_FIELDS:
            integer = safe_int(value)
            if integer is None:
                invalid_fields.append(field)
    if check_args.get("symbol") != SYMBOL:
        invalid_fields.append("symbol")
    comment = check_args.get("comment")
    comment_broker_safe = broker_comment_is_safe(comment)
    if not comment_broker_safe and "comment" not in missing_fields:
        invalid_fields.append("comment")
    return {
        "payload_required_fields_present": not missing_fields and not invalid_fields and not placeholder_fields,
        "payload_missing_fields": sorted(set(missing_fields)),
        "payload_invalid_fields": sorted(set(invalid_fields)),
        "payload_placeholder_fields": sorted(set(placeholder_fields)),
        "payload_redacted_keys": list(ORDER_CHECK_REQUIRED_PAYLOAD_FIELDS),
        "comment_length": len(comment) if isinstance(comment, str) else 0,
        "comment_redacted_preview": redacted_comment_preview(comment),
        "comment_broker_safe": comment_broker_safe,
    }


def redacted_request_echo(check_args: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": check_args.get("symbol"),
        "volume_lots": check_args.get("volume"),
        "side": SIDE_INTENT,
        "action_present": check_args.get("action") is not None,
        "type_present": check_args.get("type") is not None,
        "price_present": check_args.get("price") is not None,
        "sl_present": check_args.get("sl") is not None,
        "tp_present": check_args.get("tp") is not None,
        "deviation_present": check_args.get("deviation") is not None,
        "magic_present": check_args.get("magic") is not None,
        "comment_present": bool(check_args.get("comment")),
        "type_time_present": check_args.get("type_time") is not None,
        "type_filling_present": check_args.get("type_filling") is not None,
        "not_executable_artifact": True,
    }


def payload_block_result_snapshot(
    check_args: dict[str, Any],
    diagnostics: dict[str, Any],
    current_spread: float | None,
) -> dict[str, Any]:
    return {
        "result_available": False,
        "blocked_before_order_check": True,
        "block_reason": "order_check_blocked_invalid_order_check_payload",
        "order_check_result_type": "",
        "mt5_last_error": "",
        "order_check_exception": False,
        "current_broker_spread_points": "" if current_spread is None else current_spread,
        "max_spread_points": MAX_SPREAD_POINTS,
        "current_spread_within_policy": current_spread is not None and current_spread <= MAX_SPREAD_POINTS,
        "spread_rechecked_immediately_before_order_check": True,
        "request_echo_redacted": redacted_request_echo(check_args),
        "raw_request_payload_written": False,
        **diagnostics,
    }


def current_spread_points(symbol: Any) -> float | None:
    spread = safe_float(object_value(symbol, "spread"))
    if spread is None or not math.isfinite(spread):
        return None
    return spread


def retcode_passed(mt5: Any, retcode: Any) -> bool:
    accepted = {0, object_value(mt5, "TRADE_RETCODE_DONE"), object_value(mt5, "TRADE_RETCODE_PLACED")}
    accepted.discard(None)
    return retcode in accepted


def blocked_spread_result_snapshot(status: str, current_spread: float | None, within_policy: bool | None) -> dict[str, Any]:
    return {
        "result_available": False,
        "blocked_before_order_check": True,
        "block_reason": status,
        "current_broker_spread_points": "" if current_spread is None else current_spread,
        "max_spread_points": MAX_SPREAD_POINTS,
        "current_spread_within_policy": within_policy,
        "spread_rechecked_immediately_before_order_check": True,
        "raw_request_payload_written": False,
    }


def run_real_order_check(inputs: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any], int, Any]:
    mt5_imported = False
    connected = False
    call_count = 0
    check_args: dict[str, Any] | None = None
    broker_snapshot: dict[str, Any] = {"mode": "real_order_check"}
    result_snapshot: dict[str, Any] = {"result_available": False}
    try:
        mt5 = import_mt5_module()
        mt5_imported = True
    except Exception as exc:  # noqa: BLE001
        return "order_check_blocked_mt5_import_failure", {"mt5_imported": mt5_imported, "error": str(exc)}, result_snapshot, call_count, None
    try:
        if not mt5.initialize():
            return "order_check_blocked_mt5_initialize_failure", {"mt5_imported": mt5_imported, "mt5_initialize_success": False}, result_snapshot, call_count, None
        connected = True
        terminal = mt5.terminal_info()
        if terminal is None:
            return "order_check_blocked_terminal_info_unavailable", {"mt5_imported": mt5_imported, "mt5_connection_performed": connected}, result_snapshot, call_count, None
        account = mt5.account_info()
        if account is None:
            return "order_check_blocked_account_info_unavailable", {"mt5_imported": mt5_imported, "mt5_connection_performed": connected}, result_snapshot, call_count, None
        if not account_is_demo(mt5, account):
            return "order_check_blocked_non_demo_account", redacted_broker_snapshot(terminal, account, None, None, mt5_imported, connected), result_snapshot, call_count, None
        if object_value(account, "currency") != ACCOUNT_CURRENCY:
            return "order_check_blocked_account_currency_mismatch", redacted_broker_snapshot(terminal, account, None, None, mt5_imported, connected), result_snapshot, call_count, None
        symbol = mt5.symbol_info(SYMBOL)
        if symbol is None:
            return "order_check_blocked_symbol_unavailable", redacted_broker_snapshot(terminal, account, None, None, mt5_imported, connected), result_snapshot, call_count, None
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None:
            return "order_check_blocked_tick_unavailable", redacted_broker_snapshot(terminal, account, symbol, None, mt5_imported, connected), result_snapshot, call_count, None
        symbol = mt5.symbol_info(SYMBOL)
        if symbol is None:
            status = "order_check_blocked_current_spread_unavailable"
            broker_snapshot = redacted_broker_snapshot(
                terminal,
                account,
                None,
                tick,
                mt5_imported,
                connected,
                spread_rechecked=True,
                current_spread_within_policy=False,
                current_spread_block_status=status,
            )
            result_snapshot = blocked_spread_result_snapshot(status, None, False)
            return status, broker_snapshot, result_snapshot, call_count, None
        current_spread = current_spread_points(symbol)
        if current_spread is None:
            status = "order_check_blocked_current_spread_unavailable"
            broker_snapshot = redacted_broker_snapshot(
                terminal,
                account,
                symbol,
                tick,
                mt5_imported,
                connected,
                spread_rechecked=True,
                current_spread_points=None,
                current_spread_within_policy=False,
                current_spread_block_status=status,
            )
            result_snapshot = blocked_spread_result_snapshot(status, None, False)
            return status, broker_snapshot, result_snapshot, call_count, None
        current_spread_within_policy = current_spread <= MAX_SPREAD_POINTS
        if not current_spread_within_policy:
            status = "order_check_blocked_current_spread_policy"
            broker_snapshot = redacted_broker_snapshot(
                terminal,
                account,
                symbol,
                tick,
                mt5_imported,
                connected,
                spread_rechecked=True,
                current_spread_points=current_spread,
                current_spread_within_policy=False,
                current_spread_block_status=status,
            )
            result_snapshot = blocked_spread_result_snapshot(status, current_spread, False)
            return status, broker_snapshot, result_snapshot, call_count, None
        check_args = build_check_args(mt5, first_intent(inputs), tick)
        diagnostics = payload_diagnostics(check_args)
        if diagnostics["payload_required_fields_present"] is not True:
            status = "order_check_blocked_invalid_order_check_payload"
            broker_snapshot = redacted_broker_snapshot(
                terminal,
                account,
                symbol,
                tick,
                mt5_imported,
                connected,
                spread_rechecked=True,
                current_spread_points=current_spread,
                current_spread_within_policy=True,
                current_spread_block_status=status,
            )
            result_snapshot = payload_block_result_snapshot(check_args, diagnostics, current_spread)
            return status, broker_snapshot, result_snapshot, call_count, None
        call_count += 1
        result = mt5.order_check(check_args)
        retcode = object_value(result, "retcode")
        broker_snapshot = redacted_broker_snapshot(
            terminal,
            account,
            symbol,
            tick,
            mt5_imported,
            connected,
            spread_rechecked=True,
            current_spread_points=current_spread,
            current_spread_within_policy=True,
        )
        result_snapshot = redacted_result_snapshot(
            result,
            check_args,
            mt5,
            retcode,
            mt5_last_error=mt5_last_error_snapshot(mt5) if result is None or retcode is None else "",
            current_spread_points=current_spread,
            current_spread_within_policy=True,
            spread_rechecked=True,
        )
        if retcode_passed(mt5, retcode):
            return "order_check_available_passed_no_send", broker_snapshot, result_snapshot, call_count, retcode
        return "order_check_available_failed_no_send", broker_snapshot, result_snapshot, call_count, retcode
    except Exception as exc:  # noqa: BLE001
        diagnostics = payload_diagnostics(check_args or {}) if check_args is not None else {}
        result_snapshot = {
            "result_available": False,
            "error": str(exc),
            "mt5_last_error": mt5_last_error_snapshot(mt5) if mt5_imported else "",
            "order_check_exception": True,
            "order_check_result_type": "",
            "raw_request_payload_written": False,
            **diagnostics,
        }
        return "order_check_blocked_order_check_exception", {"mt5_imported": mt5_imported, "mt5_connection_performed": connected}, result_snapshot, call_count, None
    finally:
        if connected:
            shutdown = getattr(mt5, "shutdown", None)
            if callable(shutdown):
                shutdown()


def redacted_broker_snapshot(
    terminal: Any,
    account: Any,
    symbol: Any,
    tick: Any,
    mt5_imported: bool,
    connected: bool,
    *,
    spread_rechecked: bool = False,
    current_spread_points: float | None = None,
    current_spread_within_policy: bool | None = None,
    current_spread_block_status: str = "",
) -> dict[str, Any]:
    return {
        "mt5_import_performed": mt5_imported,
        "mt5_connection_performed": connected,
        "terminal_info_available": terminal is not None,
        "terminal_connected": object_value(terminal, "connected"),
        "account_info_available": account is not None,
        "account_trade_mode_raw": object_value(account, "trade_mode"),
        "account_currency": object_value(account, "currency"),
        "account_equity_present": object_value(account, "equity") is not None,
        "account_balance_present": object_value(account, "balance") is not None,
        "symbol_info_available": symbol is not None,
        "symbol": object_value(symbol, "name", SYMBOL) if symbol is not None else "",
        "visible": object_value(symbol, "visible"),
        "volume_min": object_value(symbol, "volume_min"),
        "volume_max": object_value(symbol, "volume_max"),
        "volume_step": object_value(symbol, "volume_step"),
        "point": object_value(symbol, "point"),
        "digits": object_value(symbol, "digits"),
        "spread": object_value(symbol, "spread"),
        "current_broker_spread_points": "" if current_spread_points is None else current_spread_points,
        "max_spread_points": MAX_SPREAD_POINTS,
        "current_spread_within_policy": current_spread_within_policy,
        "spread_rechecked_immediately_before_order_check": spread_rechecked,
        "current_spread_block_status": current_spread_block_status,
        "tick_available": tick is not None,
        "bid_present": object_value(tick, "bid") is not None,
        "ask_present": object_value(tick, "ask") is not None,
        "redaction_applied": True,
    }


def redacted_result_snapshot(
    result: Any,
    check_args: dict[str, Any],
    mt5: Any,
    retcode: Any,
    *,
    mt5_last_error: Any,
    current_spread_points: float | None,
    current_spread_within_policy: bool | None,
    spread_rechecked: bool,
) -> dict[str, Any]:
    diagnostics = payload_diagnostics(check_args)
    return {
        "result_available": result is not None,
        "retcode": retcode,
        "comment": object_value(result, "comment"),
        "mt5_last_error": mt5_last_error,
        "order_check_exception": False,
        "order_check_result_type": type(result).__name__ if result is not None else "NoneType",
        "balance_present": object_value(result, "balance") is not None,
        "equity_present": object_value(result, "equity") is not None,
        "margin_present": object_value(result, "margin") is not None,
        "order_check_passed": retcode_passed(mt5, retcode),
        "current_broker_spread_points": "" if current_spread_points is None else current_spread_points,
        "max_spread_points": MAX_SPREAD_POINTS,
        "current_spread_within_policy": current_spread_within_policy,
        "spread_rechecked_immediately_before_order_check": spread_rechecked,
        "request_echo_redacted": redacted_request_echo(check_args),
        "raw_request_payload_written": False,
        **diagnostics,
    }


def current_spread_gate_row(args: argparse.Namespace, broker_snapshot: dict[str, Any]) -> dict[str, Any] | None:
    if broker_snapshot.get("spread_rechecked_immediately_before_order_check") is not True:
        return None
    observed = broker_snapshot.get("current_broker_spread_points")
    within_policy = broker_snapshot.get("current_spread_within_policy") is True
    warning_code = str(broker_snapshot.get("current_spread_block_status") or "order_check_blocked_current_spread_policy")
    if observed in (None, ""):
        warning_code = "order_check_blocked_current_spread_unavailable"
    return gate_row(
        args,
        "current_broker_spread_immediate_recheck",
        within_policy,
        observed if observed not in (None, "") else "unavailable_or_non_numeric",
        f"<= {MAX_SPREAD_POINTS}",
        "MetaTrader5.symbol_info(GBPUSD).spread",
        warning_code,
    )


def payload_preview_rows(args: argparse.Namespace, inputs: dict[str, Any], dry_run: bool) -> list[dict[str, Any]]:
    intent = first_intent(inputs)
    fields = [
        ("action_intent", "future_deal", "readiness descriptor"),
        ("symbol", intent.get("symbol", SYMBOL) or SYMBOL, "request intent"),
        ("volume", intent.get("volume_lots", ""), "request intent"),
        ("type_intent", SIDE_INTENT, "fixed candidate"),
        ("price_reference", intent.get("entry_reference_price", ""), "request intent"),
        ("sl", intent.get("sl_price", ""), "request intent"),
        ("tp", intent.get("tp_price", ""), "request intent"),
        ("deviation_policy", "safe_default_or_future_policy", "future module policy"),
        ("magic_policy", "deterministic_candidate_magic", "future module policy"),
        ("comment_policy", "short_candidate_idempotency_comment", "future module policy"),
        ("type_time_policy", "good_till_cancelled_policy", "future module policy"),
        ("type_filling_policy", "future_symbol_contract_policy", "future module policy"),
    ]
    return [
        {
            "run_id": args.run_id,
            "field_name": name,
            "preview_value": "redacted_non_executable" if dry_run and name in {"volume", "price_reference", "sl", "tp"} else value,
            "source": source,
            "redacted": dry_run and name in {"volume", "price_reference", "sl", "tp"},
            "broker_payload_field_now": False,
            "executable_now": False,
            "caveat": "preview_only_not_a_broker_payload",
        }
        for name, value, source in fields
    ]


def bound_intent_row(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    intent = first_intent(inputs)
    return {
        "run_id": args.run_id,
        "request_construction_dry_run_dir": str(inputs["paths"]["request_dir"]),
        "request_intent_path": str(inputs["paths"]["request_intent"]),
        "request_construction_status": inputs["request_manifest"].get("request_construction_status", ""),
        "request_intent_created": inputs["request_manifest"].get("request_intent_created", False),
        "signal_id": intent.get("signal_id", ""),
        "idempotency_key": intent.get("idempotency_key", ""),
        "approval_record_id": intent.get("approval_record_id", ""),
        "binding_status": "read_only_bound" if intent else "not_bound_fixture_or_missing",
    }


def recommended_next_step(status: str, dry_run: bool) -> str:
    if status in {"order_check_blocked_fixture_only_no_request_intent", "order_check_blocked_fixture_only_no_order_check_readiness"}:
        return "wait_for_fresh_signal_valid_approval_non_executable_request_intent_and_readiness"
    if status == "order_check_dry_run_no_broker_call":
        return "run_real_order_check_only_after_reviewing_non_fixture_readiness"
    if status == "order_check_available_passed_no_send":
        return "stop_or_build_order_send_pilot_plan_no_execution_default"
    if status == "order_check_available_failed_no_send":
        return "inspect_order_check_failure_no_send"
    return "resolve_order_check_blocker_before_any_future_attempt"


def no_order_evidence_row(
    args: argparse.Namespace,
    dry_run: bool,
    order_check_called: bool,
    call_count: int,
    mt5_import_performed: bool,
    mt5_connection_performed: bool,
    broker_api_query_performed: bool,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "no_order_send_called": True,
        "no_order_execution_performed": True,
        "no_future_state_json_written": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
        "no_mt5_import_performed": not mt5_import_performed,
        "no_mt5_connection_performed": not mt5_connection_performed,
        "no_broker_api_query_performed": not broker_api_query_performed,
        "no_order_check_called": not order_check_called,
        "mt5_import_performed": mt5_import_performed,
        "mt5_connection_performed": mt5_connection_performed,
        "broker_api_query_performed": broker_api_query_performed,
        "order_check_called": order_check_called,
        "order_check_call_count": call_count,
        "evidence_label": "demo_order_check_gated_no_send_boundary",
        "caveat": "order-check only when explicitly allowed; order-send and execution remain forbidden",
    }


def status_row(args: argparse.Namespace, status: str, dry_run: bool, call_count: int, retcode: Any) -> dict[str, Any]:
    passed: bool | None
    if status == "order_check_available_passed_no_send":
        passed = True
    elif status == "order_check_available_failed_no_send":
        passed = False
    else:
        passed = None
    return {
        "run_id": args.run_id,
        "order_check_status": status,
        "dry_run": dry_run,
        "allow_real_order_check": args.allow_real_order_check,
        "order_check_called": call_count == 1,
        "order_check_call_count": call_count,
        "order_check_retcode": retcode,
        "order_check_passed": passed,
        "order_send_called": False,
        "order_execution_performed": False,
        "recommended_next_step": recommended_next_step(status, dry_run),
    }


def write_report(
    path: Path,
    status: str,
    dry_run: bool,
    warnings: list[dict[str, Any]],
    args: argparse.Namespace,
    inputs: dict[str, Any],
) -> None:
    previous_state = inputs.get("future_state") or {}
    explicit_client_reject_resend = client_reject_flat_resend_allowed(args, inputs)
    market_contract = market_closed_flat_contract(args, inputs)
    explicit_market_closed_new_signal = bool(market_contract.get("accepted"))
    lines = [
        "# Fixed-Candidate Demo Order Check",
        "",
        "Gated fixed-candidate demo order-check module.",
        "",
        "Dry-run mode performs no MT5 import, no MT5 connection, no broker/API query, and no order-check call. Real order-check mode is available only with explicit permission and passing non-fixture gates.",
        "",
        "No order-send path was called. No order execution, future trading state write, DB mutation, child script, scheduler, loop, background task, demo broker approval, or trading decision was performed.",
        "",
        "No executable broker payload or executable order object was written to disk. Any payload preview artifact is redacted/non-executable evidence only.",
        "",
        "## Result",
        "",
        f"- order_check_status: `{status}`",
        f"- dry_run: `{dry_run}`",
        f"- explicit_second_demo_send_after_client_reject_flat: `{explicit_client_reject_resend}`",
        f"- explicit_new_signal_after_market_closed_flat: `{explicit_market_closed_new_signal}`",
        f"- previous_state_status: `{previous_state.get('state_status', '')}`",
        f"- previous_send_retcode: `{previous_state.get('last_retcode', '')}`",
        f"- new_operator_authorized_attempt: `{explicit_client_reject_resend}`",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{sum(1 for warning in warnings if warning.get('blocking_warning') == 'true')}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{recommended_next_step(status, dry_run)}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    args: argparse.Namespace,
    status: str,
    dry_run: bool,
    inputs: dict[str, Any],
    paths: dict[str, Path],
    warnings: list[dict[str, Any]],
    call_count: int,
    retcode: Any,
    artifact_summary: dict[str, Any],
    broker_snapshot: dict[str, Any],
    digest_summary: dict[str, Any],
) -> None:
    intent = first_intent(inputs)
    approval = inputs["approval_record"]
    passed = status == "order_check_available_passed_no_send" if call_count else None
    module_validation_demo_execution = bool(
        args.module_validation_demo_execution
        or inputs["request_manifest"].get("module_validation_demo_execution") is True
    )
    stale_override_used = bool(inputs["request_manifest"].get("stale_override_used") is True)
    expired_signal_override_used = bool(
        expired_signal_override_allowed(args, inputs) and approval_record_expired(approval)
    )
    strategy_valid = bool(
        inputs["request_manifest"].get("strategy_valid") is True
        and not module_validation_demo_execution
        and not stale_override_used
        and not expired_signal_override_used
    )
    production_valid = bool(
        inputs["request_manifest"].get("production_valid") is True
        and not module_validation_demo_execution
        and not stale_override_used
        and not expired_signal_override_used
    )
    previous_state = inputs.get("future_state") or {}
    explicit_client_reject_resend = client_reject_flat_resend_allowed(args, inputs)
    market_contract = market_closed_flat_contract(args, inputs)
    explicit_market_closed_new_signal = bool(market_contract.get("accepted"))
    content = {
        "run_id": args.run_id,
        "order_check_status": status,
        "dry_run": dry_run,
        "allow_real_order_check": args.allow_real_order_check,
        "candidate_id": CANDIDATE_ID,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "direction": DIRECTION,
        "side": SIDE_INTENT,
        "signal_time_server": intent.get("signal_time_server", approval.get("signal_time_server", "")),
        "signal_id": intent.get("signal_id", approval.get("signal_id", "")),
        "idempotency_key": intent.get("idempotency_key", approval.get("idempotency_key", "")),
        "approval_record_id": intent.get("approval_record_id", approval.get("approval_record_id", "")),
        "approval_status": approval.get("approval_status", ""),
        "approval_scope": approval.get("approval_scope", ""),
        "approval_record_digest": approval.get("record_hash_or_digest", ""),
        "request_construction_status": inputs["request_manifest"].get("request_construction_status", ""),
        "module_validation_demo_execution": module_validation_demo_execution,
        "stale_override_used": stale_override_used,
        "expired_signal_override_used": expired_signal_override_used,
        "strategy_valid": strategy_valid,
        "production_valid": production_valid,
        "order_check_allowed_for_demo_module_validation_only": module_validation_order_check_allowed(args, inputs),
        "order_send_allowed_for_demo_module_validation_only": False,
        "explicit_second_demo_send_after_client_reject_flat": explicit_client_reject_resend,
        "explicit_new_signal_after_market_closed_flat": explicit_market_closed_new_signal,
        "client_reject_resend_acknowledgment_valid": args.client_reject_resend_acknowledgment == CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        "previous_state_status": previous_state.get("state_status", ""),
        "previous_send_retcode": previous_state.get("last_retcode", ""),
        "previous_reconciliation_status": previous_state.get("reconciliation_status", ""),
        "new_signal_id_differs_from_previous_state": (
            not bool(market_contract.get("same_signal_id")) if explicit_market_closed_new_signal else False
        ),
        "new_idempotency_key_differs_from_previous_state": (
            not bool(market_contract.get("same_idempotency_key")) if explicit_market_closed_new_signal else False
        ),
        "previous_order_execution_performed": previous_state.get("order_execution_performed", ""),
        "previous_crash_recovery_required": previous_state.get("crash_recovery_required", ""),
        "previous_automatic_retry_allowed": previous_state.get("automatic_retry_allowed", ""),
        "previous_retry_performed": previous_state.get("retry_performed", ""),
        "previous_broker_order_ticket": previous_state.get("broker_order_ticket", ""),
        "previous_broker_deal_ticket": previous_state.get("broker_deal_ticket", ""),
        "previous_broker_position_ticket": previous_state.get("broker_position_ticket", ""),
        "new_operator_authorized_attempt": explicit_client_reject_resend,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "request_intent_digest": inputs["request_manifest"].get("request_intent_digest", ""),
        "request_fields_digest": inputs["request_manifest"].get("request_fields_digest", ""),
        "digest_binding_required": digest_summary["digest_binding_required"],
        "digest_binding_verified": digest_summary["digest_binding_verified"],
        "digest_algorithm": digest_summary["digest_algorithm"],
        "digest_canonicalization": digest_summary["digest_canonicalization"],
        "missing_digest_count": digest_summary["missing_digest_count"],
        "digest_mismatch_count": digest_summary["digest_mismatch_count"],
        "digest_verification_status": digest_summary["digest_verification_status"],
        "order_check_readiness_status": inputs["readiness_manifest"].get("order_check_readiness_status", ""),
        "order_check_called": call_count == 1,
        "order_check_call_count": call_count,
        "order_check_retcode": retcode,
        "order_check_passed": passed,
        "order_check_result_digest": sha256_file(paths["result_snapshot"]),
        "current_broker_spread_points": broker_snapshot.get("current_broker_spread_points", ""),
        "max_spread_points": MAX_SPREAD_POINTS,
        "current_spread_within_policy": broker_snapshot.get("current_spread_within_policy"),
        "spread_rechecked_immediately_before_order_check": bool(
            broker_snapshot.get("spread_rechecked_immediately_before_order_check")
        ),
        "order_send_called": False,
        "order_send_call_count": 0,
        "order_execution_performed": False,
        "broker_payload_written": False,
        "executable_order_object_written": False,
        "future_state_json_written": False,
        "output_files": {key: str(value) for key, value in paths.items()},
        "created_at_utc": utc_now_text(),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "recommended_next_step": recommended_next_step(status, dry_run),
        "no_order_send_called": True,
        "no_order_execution_performed": True,
        "no_future_state_json_written": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    content.update(artifact_summary)
    content["order_check_manifest_digest"] = sha256_payload(
        {key: value for key, value in content.items() if key != "order_check_manifest_digest"}
    )
    write_json(path, content)


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for(args)
    paths = output_paths(output_dir)
    ensure_outputs_writable(paths, bool(args.overwrite))
    dry_run = effective_dry_run(args)
    warnings: list[dict[str, Any]] = []
    add_boundary_warnings(args, warnings)
    inputs = load_inputs(args, warnings)
    gates = structural_gates(args, inputs)
    freshness_blocking = (not dry_run) and bool(args.allow_real_order_check)
    freshness_rows = artifact_freshness_checks(args, inputs, freshness_blocking)
    freshness_summary = artifact_freshness_summary(
        freshness_rows,
        float(args.max_artifact_age_minutes),
    )
    status = status_from_gates(inputs, gates, dry_run)
    digest_required = (not status) and (not dry_run) and bool(args.allow_real_order_check)
    digest_summary = digest_binding_summary(inputs, required=digest_required)
    if digest_required:
        digest_gate = digest_gate_row(args, inputs, digest_summary)
        gates.append(digest_gate)
        if digest_gate["gate_status"] == "failed":
            status = str(digest_gate["warning_code"])
    order_check_call_count = 0
    order_check_retcode = None
    broker_snapshot = {"mode": "dry_run_no_broker_call" if dry_run else "not_queried", "redaction_applied": True}
    result_snapshot = {"result_available": False, "dry_run": dry_run, "raw_request_payload_written": False}
    if not status:
        if freshness_summary["blocking_stale_artifact_count"]:
            status = "order_check_blocked_stale_upstream_artifact"
            broker_snapshot = {"mode": "blocked_before_mt5_import_stale_upstream_artifact", "redaction_applied": True}
            result_snapshot = {"result_available": False, "blocked_before_mt5_import": True, "raw_request_payload_written": False}
        elif dry_run:
            status = "order_check_dry_run_no_broker_call"
        elif not args.allow_real_order_check:
            status = "order_check_blocked_real_mode_not_allowed"
        else:
            status, broker_snapshot, result_snapshot, order_check_call_count, order_check_retcode = run_real_order_check(inputs)
    spread_gate = current_spread_gate_row(args, broker_snapshot)
    if spread_gate is not None:
        gates.append(spread_gate)
    record_gate_warnings(args, gates, warnings)
    add_artifact_freshness_warnings(args, warnings, freshness_rows)
    if status.startswith("order_check_blocked") and status not in {row["warning_code"] for row in warnings}:
        add_warning(
            warnings,
            args=args,
            warning_code=status,
            message=f"Order-check status blocked: {status}",
            source="fixed_candidate_demo_order_check",
            blocking_warning=True,
        )
    if expired_signal_override_allowed(args, inputs) and approval_record_expired(inputs["approval_record"]):
        add_warning(
            warnings,
            args=args,
            warning_code="order_check_blocked_expired_approval",
            message="Approval expiry gate overridden for demo module validation order_check only.",
            source=inputs["paths"]["approval_record"],
            blocking_warning=False,
        )
    mt5_import_performed = bool(broker_snapshot.get("mt5_import_performed") or broker_snapshot.get("mt5_imported"))
    mt5_connection_performed = bool(broker_snapshot.get("mt5_connection_performed"))
    broker_api_query_performed = bool(mt5_connection_performed)
    write_csv(paths["gate_checks"], gates, GATE_FIELDNAMES)
    write_csv(paths["bound_intent"], [bound_intent_row(args, inputs)], BOUND_INTENT_FIELDNAMES)
    write_csv(paths["payload_preview"], payload_preview_rows(args, inputs, dry_run), PREVIEW_FIELDNAMES)
    write_csv(paths["artifact_freshness"], freshness_rows, ARTIFACT_FRESHNESS_FIELDNAMES)
    write_json(paths["broker_snapshot"], broker_snapshot)
    write_json(paths["result_snapshot"], result_snapshot)
    write_csv(paths["status"], [status_row(args, status, dry_run, order_check_call_count, order_check_retcode)], STATUS_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(
        paths["no_order"],
        [
            no_order_evidence_row(
                args,
                dry_run,
                order_check_call_count == 1,
                order_check_call_count,
                mt5_import_performed,
                mt5_connection_performed,
                broker_api_query_performed,
            )
        ],
        NO_ORDER_FIELDNAMES,
    )
    write_report(paths["report"], status, dry_run, warnings, args, inputs)
    write_manifest(
        paths["manifest"],
        args,
        status,
        dry_run,
        inputs,
        paths,
        warnings,
        order_check_call_count,
        order_check_retcode,
        freshness_summary,
        broker_snapshot,
        digest_summary,
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a gated fixed-candidate demo order-check stage with dry-run default and no order-send path.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--request-construction-dry-run-dir", type=Path, default=DEFAULT_REQUEST_CONSTRUCTION_DIR)
    parser.add_argument("--order-check-readiness-plan-dir", type=Path, default=DEFAULT_ORDER_CHECK_READINESS_DIR)
    parser.add_argument("--manual-approval-record-json", type=Path, default=DEFAULT_APPROVAL_RECORD_JSON)
    parser.add_argument("--manual-approval-record-schema-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    parser.add_argument("--broker-local-reconciliation-dir", type=Path, default=DEFAULT_BROKER_LOCAL_RECONCILIATION_DIR)
    parser.add_argument("--broker-safe-margin-validation-dir", type=Path, default=DEFAULT_BROKER_SAFE_MARGIN_VALIDATION_DIR)
    parser.add_argument("--live-signal-freshness-dir", type=Path, default=DEFAULT_LIVE_SIGNAL_FRESHNESS_DIR)
    parser.add_argument("--duplicate-protection-plan-dir", type=Path, default=DEFAULT_DUPLICATE_PROTECTION_DIR)
    parser.add_argument("--manual-approval-kill-switch-plan-dir", type=Path, default=DEFAULT_MANUAL_APPROVAL_KILL_SWITCH_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_DEMO_EXECUTION_POLICY)
    parser.add_argument("--future-state-json", type=Path, default=DEFAULT_FUTURE_STATE_JSON)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-artifact-age-minutes", type=float, default=DEFAULT_MAX_ARTIFACT_AGE_MINUTES)
    parser.add_argument("--dry-run", action="store_true", default=None)
    parser.add_argument("--allow-real-order-check", action="store_true")
    parser.add_argument("--module-validation-demo-execution", action="store_true")
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
    print("Fixed-candidate demo order-check stage complete.")
    for key, path in paths.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
