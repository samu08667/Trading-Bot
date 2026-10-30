"""Run a single-shot, gated fixed-candidate demo order-send pilot.

The default path is dry-run/no-send and does not import MT5, query broker
state, write future trading state, or construct an executable broker payload.
The real-send path is reachable only through explicit flags and validated,
non-fixture safety artifacts. It permits one send attempt, never retries, and
requires durable idempotency state before that attempt.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts._fixed_candidate_artifact_freshness import (
        ARTIFACT_FRESHNESS_FIELDNAMES,
        DEFAULT_MAX_ARTIFACT_AGE_MINUTES,
        DEFAULT_MAX_ORDER_CHECK_ARTIFACT_AGE_MINUTES,
        artifact_freshness_summary,
        evaluate_artifact_freshness,
        status_is_stale,
    )
    from scripts import fixed_candidate_demo_state_contracts as state_contracts
except ModuleNotFoundError:
    from _fixed_candidate_artifact_freshness import (
        ARTIFACT_FRESHNESS_FIELDNAMES,
        DEFAULT_MAX_ARTIFACT_AGE_MINUTES,
        DEFAULT_MAX_ORDER_CHECK_ARTIFACT_AGE_MINUTES,
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
SIDE = "sell"
MAX_SPREAD_POINTS = 15.0
MAX_OPEN_POSITIONS = 1
HORIZON_BARS = 10
HARD_MARGIN_CAP_RATIO = 0.70
ACCOUNT_CURRENCY = "EUR"
BROKER_COMMENT_MAX_LENGTH = 20
BROKER_COMMENT_IDEMPOTENCY_SUFFIX_LENGTH = 6
CLIENT_AUTOTRADING_DISABLED_RETCODE = state_contracts.CLIENT_AUTOTRADING_DISABLED_RETCODE
CLIENT_AUTOTRADING_DISABLED_COMMENT = "autotrading disabled by client"
FINAL_CONFIRMATION = "confirm_single_demo_send_only"
PRICE_TOLERANCE = 0.00001
VOLUME_TOLERANCE = 0.0000001
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

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_order_send_pilot"
DEFAULT_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_order_send_pilot_readiness_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_order_send_pilot_readiness_plan_fixture_v1"
)
DEFAULT_ORDER_CHECK_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_order_check"
    / "gbpusd_short_h10_1_5_off_hours_demo_order_check_dry_run_fixture_v1"
)
DEFAULT_REQUEST_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_request_construction_dry_run"
    / "gbpusd_short_h10_1_5_off_hours_demo_request_construction_dry_run_fixture_v1"
)
DEFAULT_APPROVAL_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record.json"
)
DEFAULT_RECONCILIATION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_broker_local_state_reconciliation"
    / "gbpusd_short_h10_1_5_off_hours_demo_broker_local_state_reconciliation_real_v1"
)
DEFAULT_MARGIN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_broker_safe_margin_validation"
    / "gbpusd_short_h10_1_5_off_hours_demo_broker_safe_margin_validation_live_v1"
)
DEFAULT_FRESHNESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_live_signal_freshness"
    / "gbpusd_short_h10_1_5_off_hours_demo_live_signal_freshness_v1"
)
DEFAULT_DUPLICATE_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_duplicate_protection_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_duplicate_protection_plan_live_v1"
)
DEFAULT_MANUAL_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_manual_approval_kill_switch_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_kill_switch_plan_live_v1"
)
DEFAULT_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE = (
    BASE_DIR / "state" / "fixed_candidate_demo_state" / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_order_send_pilot"

READINESS_MANIFEST = "fixed_candidate_demo_order_send_pilot_readiness_plan_manifest.json"
READINESS_CONTRACT_FILES = (
    "fixed_candidate_demo_order_send_pilot_readiness_plan_future_send_cli_contract.csv",
    "fixed_candidate_demo_order_send_pilot_readiness_plan_final_operator_confirmation_contract.csv",
    "fixed_candidate_demo_order_send_pilot_readiness_plan_request_order_check_send_binding.csv",
    "fixed_candidate_demo_order_send_pilot_readiness_plan_atomic_state_contract.csv",
    "fixed_candidate_demo_order_send_pilot_readiness_plan_post_send_state_update_contract.csv",
    "fixed_candidate_demo_order_send_pilot_readiness_plan_retcode_handling.csv",
    "fixed_candidate_demo_order_send_pilot_readiness_plan_post_send_reconciliation.csv",
    "fixed_candidate_demo_order_send_pilot_readiness_plan_future_send_test_contract.csv",
    "fixed_candidate_demo_order_send_pilot_readiness_plan_future_send_safety_grep_contract.csv",
)
ORDER_CHECK_MANIFEST = "fixed_candidate_demo_order_check_manifest.json"
ORDER_CHECK_RESULT = "fixed_candidate_demo_order_check_result_snapshot.json"
ORDER_CHECK_BOUND_INTENT = "fixed_candidate_demo_order_check_bound_request_intent.csv"
REQUEST_MANIFEST = "fixed_candidate_demo_request_construction_dry_run_manifest.json"
REQUEST_INTENT = "fixed_candidate_demo_request_construction_dry_run_request_intent.csv"
REQUEST_FIELDS = "fixed_candidate_demo_request_construction_dry_run_request_fields.csv"
RECONCILIATION_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
MARGIN_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"
FRESHNESS_MANIFEST = "fixed_candidate_demo_live_signal_freshness_manifest.json"
DUPLICATE_MANIFEST = "fixed_candidate_demo_duplicate_protection_plan_manifest.json"
MANUAL_PLAN_MANIFEST = "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_order_send_pilot_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_order_send_pilot_report.md"
OUTPUT_GATES = "fixed_candidate_demo_order_send_pilot_gate_checks.csv"
OUTPUT_BOUND_ORDER_CHECK = "fixed_candidate_demo_order_send_pilot_bound_order_check.csv"
OUTPUT_BOUND_INTENT = "fixed_candidate_demo_order_send_pilot_bound_request_intent.csv"
OUTPUT_CONFIRMATION = "fixed_candidate_demo_order_send_pilot_operator_confirmation.csv"
OUTPUT_STATE_PREVIEW = "fixed_candidate_demo_order_send_pilot_state_claim_preview.json"
OUTPUT_PAYLOAD_PREVIEW = "fixed_candidate_demo_order_send_pilot_send_payload_preview.csv"
OUTPUT_BROKER_SNAPSHOT = "fixed_candidate_demo_order_send_pilot_broker_snapshot.json"
OUTPUT_SEND_RESULT = "fixed_candidate_demo_order_send_pilot_send_result_snapshot.json"
OUTPUT_RECONCILIATION = "fixed_candidate_demo_order_send_pilot_reconciliation_snapshot.json"
OUTPUT_STATUS = "fixed_candidate_demo_order_send_pilot_status.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_order_send_pilot_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_order_send_pilot_no_order_evidence.csv"
OUTPUT_ARTIFACT_FRESHNESS = "fixed_candidate_demo_order_send_pilot_artifact_freshness_checks.csv"
DIGEST_ALGORITHM = "sha256"
DIGEST_CANONICALIZATION = "canonical_json_or_documented_csv_rule"

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
BOUND_ORDER_CHECK_FIELDNAMES = [
    "run_id",
    "order_check_run_id",
    "order_check_status",
    "order_check_passed",
    "order_check_call_count",
    "order_check_manifest_digest",
    "order_check_result_digest",
    "binding_status",
]
BOUND_INTENT_FIELDNAMES = [
    "run_id",
    "request_construction_run_id",
    "request_construction_status",
    "signal_id",
    "idempotency_key",
    "approval_record_id",
    "symbol",
    "side",
    "volume_lots",
    "sl_price",
    "tp_price",
    "request_intent_digest",
    "binding_status",
]
CONFIRMATION_FIELDNAMES = [
    "run_id",
    "confirmation_present",
    "confirmation_label",
    "expected_confirmation_label",
    "confirmation_valid",
    "signal_id",
    "idempotency_key",
    "approval_record_id",
    "request_intent_digest",
    "order_check_run_id",
    "order_check_digest",
    "single_send_scope_only",
    "caveat",
]
PAYLOAD_PREVIEW_FIELDNAMES = [
    "run_id",
    "field_name",
    "preview_value",
    "source",
    "in_memory_only_if_real_send",
    "persisted_executable_field",
    "safety_note",
]
STATUS_FIELDNAMES = [
    "run_id",
    "order_send_pilot_status",
    "dry_run",
    "allow_real_order_send",
    "order_send_called",
    "order_send_call_count",
    "order_send_retcode",
    "order_send_result_category",
    "reconciliation_status",
    "state_status",
    "recommended_next_step",
]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
NO_ORDER_FIELDNAMES = [
    "run_id",
    "dry_run",
    "mt5_import_performed",
    "mt5_connection_performed",
    "broker_api_query_performed",
    "positions_get_call_count",
    "orders_get_call_count",
    "order_send_called",
    "order_send_call_count",
    "order_execution_performed",
    "future_state_json_written",
    "no_order_execution_retry_performed",
    "no_second_order_send_called",
    "no_history_orders_get_called",
    "no_history_deals_get_called",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "no_db_mutation_performed",
    "no_child_scripts_executed",
    "no_trading_decision_performed",
    "no_live_account_allowed",
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
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def object_value(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    return (value, "") if isinstance(value, dict) else ({}, "JSON root must be an object")


def read_csv(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], "missing"
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), ""
    except (OSError, csv.Error) as exc:
        return [], str(exc)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def acquire_state_claim_lock(state_path: Path, run_id: str) -> tuple[int, Path]:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_name(f"{state_path.name}.pilot.lock")
    handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(handle, run_id.encode("utf-8"))
    except Exception:
        os.close(handle)
        lock_path.unlink(missing_ok=True)
        raise
    return handle, lock_path


def release_state_claim_lock(handle: int | None, lock_path: Path | None) -> None:
    if handle is not None:
        os.close(handle)
    if lock_path is not None and lock_path.exists():
        lock_path.unlink()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(content: dict[str, Any]) -> bytes:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_payload(content: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


def sha256_payload_excluding(content: dict[str, Any], excluded_keys: set[str]) -> str:
    return sha256_payload({key: value for key, value in content.items() if key not in excluded_keys})


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
        "bound_order_check": output_dir / OUTPUT_BOUND_ORDER_CHECK,
        "bound_request_intent": output_dir / OUTPUT_BOUND_INTENT,
        "operator_confirmation": output_dir / OUTPUT_CONFIRMATION,
        "state_claim_preview": output_dir / OUTPUT_STATE_PREVIEW,
        "send_payload_preview": output_dir / OUTPUT_PAYLOAD_PREVIEW,
        "broker_snapshot": output_dir / OUTPUT_BROKER_SNAPSHOT,
        "send_result_snapshot": output_dir / OUTPUT_SEND_RESULT,
        "reconciliation_snapshot": output_dir / OUTPUT_RECONCILIATION,
        "status": output_dir / OUTPUT_STATUS,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order_evidence": output_dir / OUTPUT_NO_ORDER,
        "artifact_freshness": output_dir / OUTPUT_ARTIFACT_FRESHNESS,
    }


def ensure_outputs_writable(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError("Output files already exist. Use --overwrite to replace them.")
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)


def input_paths(args: argparse.Namespace) -> dict[str, Path]:
    readiness_dir = Path(args.order_send_pilot_readiness_plan_dir)
    order_check_dir = Path(args.order_check_dir)
    request_dir = Path(args.request_construction_dry_run_dir)
    paths = {
        "readiness_manifest": readiness_dir / READINESS_MANIFEST,
        "order_check_manifest": order_check_dir / ORDER_CHECK_MANIFEST,
        "order_check_result": order_check_dir / ORDER_CHECK_RESULT,
        "order_check_bound_intent": order_check_dir / ORDER_CHECK_BOUND_INTENT,
        "request_manifest": request_dir / REQUEST_MANIFEST,
        "request_intent": request_dir / REQUEST_INTENT,
        "request_fields": request_dir / REQUEST_FIELDS,
        "approval": Path(args.manual_approval_record_json),
        "reconciliation": Path(args.broker_local_reconciliation_dir) / RECONCILIATION_MANIFEST,
        "margin": Path(args.broker_safe_margin_validation_dir) / MARGIN_MANIFEST,
        "margin_snapshot": Path(args.broker_safe_margin_validation_dir) / MARGIN_SNAPSHOT,
        "freshness": Path(args.live_signal_freshness_dir) / FRESHNESS_MANIFEST,
        "duplicate": Path(args.duplicate_protection_plan_dir) / DUPLICATE_MANIFEST,
        "manual_plan": Path(args.manual_approval_kill_switch_plan_dir) / MANUAL_PLAN_MANIFEST,
        "registry": Path(args.canonical_registry),
        "policy": Path(args.demo_execution_policy),
        "future_state": Path(args.future_state_json),
    }
    for index, file_name in enumerate(READINESS_CONTRACT_FILES):
        paths[f"readiness_contract_{index}"] = readiness_dir / file_name
    return paths


def load_inputs(args: argparse.Namespace) -> dict[str, Any]:
    paths = input_paths(args)
    json_keys = (
        "readiness_manifest",
        "order_check_manifest",
        "order_check_result",
        "request_manifest",
        "approval",
        "reconciliation",
        "margin",
        "margin_snapshot",
        "freshness",
        "duplicate",
        "manual_plan",
        "registry",
        "policy",
    )
    inputs: dict[str, Any] = {"paths": paths, "errors": {}}
    for key in json_keys:
        inputs[key], inputs["errors"][key] = read_json(paths[key])
    for key in ("order_check_bound_intent", "request_intent"):
        rows, error = read_csv(paths[key])
        inputs[key] = rows
        inputs["errors"][key] = error
    state, state_error = read_json(paths["future_state"])
    inputs["future_state"] = state
    inputs["future_state_exists"] = paths["future_state"].exists()
    inputs["errors"]["future_state"] = "" if not inputs["future_state_exists"] else state_error
    inputs["readiness_contracts_available"] = all(paths[f"readiness_contract_{index}"].exists() for index in range(len(READINESS_CONTRACT_FILES)))
    return inputs


def artifact_freshness_checks(args: argparse.Namespace, inputs: dict[str, Any], blocking: bool) -> list[dict[str, Any]]:
    paths = inputs["paths"]
    upstream_max_age = float(args.max_artifact_age_minutes)
    order_check_max_age = float(args.max_order_check_artifact_age_minutes)
    specs = [
        {
            "artifact_name": "order_check",
            "path": paths["order_check_manifest"],
            "payload": inputs["order_check_manifest"],
            "max_age_minutes": order_check_max_age,
            "blocking_if_stale": blocking,
        },
        {
            "artifact_name": "order_send_readiness",
            "path": paths["readiness_manifest"],
            "payload": inputs["readiness_manifest"],
            "max_age_minutes": upstream_max_age,
            "blocking_if_stale": blocking,
        },
        {
            "artifact_name": "live_signal_freshness",
            "path": paths["freshness"],
            "payload": inputs["freshness"],
            "max_age_minutes": upstream_max_age,
            "blocking_if_stale": blocking,
        },
        {
            "artifact_name": "broker_local_reconciliation",
            "path": paths["reconciliation"],
            "payload": inputs["reconciliation"],
            "max_age_minutes": upstream_max_age,
            "blocking_if_stale": blocking,
        },
        {
            "artifact_name": "broker_safe_margin_validation",
            "path": paths["margin"],
            "payload": inputs["margin"],
            "max_age_minutes": upstream_max_age,
            "blocking_if_stale": blocking,
        },
    ]
    return evaluate_artifact_freshness(specs)


def first_row(rows: list[dict[str, str]]) -> dict[str, str]:
    return rows[0] if rows else {}


def policy_boundaries(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("safety_boundaries")
    return value if isinstance(value, dict) else {}


def canonical_valid(registry: dict[str, Any]) -> bool:
    return (
        registry.get("candidate_id") == CANDIDATE_ID
        and registry.get("symbol") == SYMBOL
        and registry.get("timeframe") == TIMEFRAME
        and registry.get("direction") == DIRECTION
        and registry.get("spread_unit") == "broker_points"
        and safe_float(registry.get("max_spread_points")) == MAX_SPREAD_POINTS
        and safe_int(registry.get("max_open_positions")) in (None, MAX_OPEN_POSITIONS)
    )


def policy_valid(policy: dict[str, Any]) -> bool:
    boundaries = policy_boundaries(policy)
    return (
        policy.get("candidate_id") == CANDIDATE_ID
        and policy.get("symbol") == SYMBOL
        and policy.get("timeframe") == TIMEFRAME
        and policy.get("direction") == DIRECTION
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


def readiness_status(inputs: dict[str, Any]) -> str:
    return str(inputs["readiness_manifest"].get("order_send_pilot_readiness_status") or "")


def fixture_source(inputs: dict[str, Any]) -> bool:
    values = (
        readiness_status(inputs),
        inputs["readiness_manifest"].get("source_nature"),
        inputs["order_check_manifest"].get("source_nature"),
        inputs["request_manifest"].get("source_nature"),
        inputs["order_check_manifest"].get("run_id"),
        inputs["request_manifest"].get("run_id"),
    )
    for value in values:
        text = str(value or "").lower()
        if text == "fixture_or_blocked" or "fixture_only" in text or "_fixture_" in text:
            return True
    return False


def readiness_valid(inputs: dict[str, Any]) -> bool:
    manifest = inputs["readiness_manifest"]
    patch = manifest.get("readiness_patch_status")
    demo_only = manifest.get("send_readiness_for_demo_module_validation_only") is True
    if demo_only and not (
        manifest.get("module_validation_demo_execution") is True
        and manifest.get("strategy_valid") is False
        and manifest.get("production_valid") is False
        and manifest.get("stale_override_used") is True
    ):
        return False
    return (
        readiness_status(inputs) == "order_send_pilot_readiness_plan_available_no_send"
        and manifest.get("future_order_send_ready") is True
        and (patch in (None, "order_send_pilot_readiness_audit_gaps_closed_no_send"))
        and inputs["readiness_contracts_available"] is True
    )


def order_check_valid(inputs: dict[str, Any]) -> bool:
    manifest = inputs["order_check_manifest"]
    return (
        manifest.get("order_check_status") == "order_check_available_passed_no_send"
        and manifest.get("order_check_called") is True
        and safe_int(manifest.get("order_check_call_count")) == 1
        and manifest.get("order_check_passed") is True
        and safe_int(manifest.get("order_check_retcode")) == 0
        and manifest.get("order_send_called") is False
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
        and inputs["readiness_manifest"].get("send_readiness_for_demo_module_validation_only") is True
    )


def expired_signal_override_requested(args: argparse.Namespace) -> bool:
    return bool(args.allow_expired_signal_for_demo_module_validation or args.expired_signal_override_acknowledgment)


def expired_signal_override_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return (
        stale_override_allowed(args, inputs)
        and args.allow_expired_signal_for_demo_module_validation is True
        and args.expired_signal_override_acknowledgment == EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT
        and inputs["readiness_manifest"].get("expired_signal_override_used") is True
    )


def module_validation_send_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return stale_override_allowed(args, inputs)


def request_valid(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    manifest = inputs["request_manifest"]
    intent = first_row(inputs["request_intent"])
    critical_numbers = (safe_float(intent.get("volume_lots")), safe_float(intent.get("sl_price")), safe_float(intent.get("tp_price")))
    return (
        (
            (
                manifest.get("request_construction_status") == REQUEST_CONSTRUCTION_AVAILABLE_STATUS
                and manifest.get("request_intent_created") is True
            )
            or module_validation_send_allowed(args, inputs)
        )
        and manifest.get("broker_payload_constructed") is False
        and manifest.get("executable_order_object_constructed") is False
        and intent.get("candidate_id") == CANDIDATE_ID
        and intent.get("symbol") == SYMBOL
        and intent.get("direction") == DIRECTION
        and intent.get("side") == SIDE
        and all(value is not None and value > 0 for value in critical_numbers)
        and bool(intent.get("signal_id"))
        and bool(intent.get("idempotency_key"))
    )


def approval_status(args: argparse.Namespace, inputs: dict[str, Any]) -> str:
    record = inputs["approval"]
    if not record:
        return "missing"
    if record.get("approval_revoked") is True:
        return "revoked"
    if record.get("approval_status") != "approved_for_future_request_construction_only":
        return "unapproved"
    if record.get("approval_scope") != "future_request_construction_only":
        return "unapproved"
    if (
        record.get("candidate_id") != CANDIDATE_ID
        or record.get("symbol") != SYMBOL
        or record.get("timeframe") != TIMEFRAME
        or record.get("direction") != DIRECTION
    ):
        return "unapproved"
    expiry = parse_time(record.get("approval_expiry_time_utc"))
    if expiry is None or expiry <= utc_now():
        return "valid" if expired_signal_override_allowed(args, inputs) else "expired"
    if not record.get("signal_id") or not record.get("idempotency_key"):
        return "unapproved"
    return "valid"


def freshness_valid(manifest: dict[str, Any]) -> bool:
    bars_elapsed = safe_int(manifest.get("bars_elapsed"))
    return (
        manifest.get("freshness_status")
        in {"live_signal_freshness_fresh_current_or_latest_signal", "live_signal_freshness_fresh_within_horizon"}
        and manifest.get("is_fresh") is True
        and manifest.get("is_stale") is False
        and (bars_elapsed is None or bars_elapsed <= HORIZON_BARS)
    )


def reconciliation_valid(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("reconciliation_status") == "broker_local_reconciliation_clean_no_local_no_broker"
        and safe_int(manifest.get("broker_position_count_symbol")) == 0
        and safe_int(manifest.get("broker_pending_order_count_symbol")) == 0
    )


def margin_valid(manifest: dict[str, Any], snapshot: dict[str, Any]) -> bool:
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


def duplicate_valid(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("plan_status") == "duplicate_protection_plan_available_no_order"
        and safe_int(manifest.get("max_open_positions")) == MAX_OPEN_POSITIONS
        and manifest.get("plan_actionable") is False
    )


def kill_switch_valid(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("plan_status") == "manual_approval_kill_switch_plan_available_no_order"
        and manifest.get("kill_switch_executed") is False
        and manifest.get("plan_actionable") is False
    )


def state_status(state: dict[str, Any]) -> str:
    return state_contracts.state_status(state)


def empty_ticket(value: Any) -> bool:
    return state_contracts.empty_ticket(value)


def client_reject_flat_contract(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    intent = first_row(inputs.get("request_intent", []))
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


def client_reject_flat_resend_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    if not (
        args.allow_real_order_send is True
        and args.operator_final_send_confirmation == FINAL_CONFIRMATION
        and safe_int(args.max_order_send_attempts) == 1
    ):
        return False
    return bool(client_reject_flat_contract(args, inputs)["accepted"])


def client_reject_flat_resend_candidate(inputs: dict[str, Any]) -> bool:
    if not inputs.get("future_state_exists"):
        return False
    state = inputs.get("future_state", {})
    intent = first_row(inputs.get("request_intent", []))
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


def market_closed_flat_contract(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    intent = first_row(inputs.get("request_intent", []))
    return state_contracts.evaluate_market_closed_reject_flat_new_signal(
        state=inputs.get("future_state") or {},
        signal_id=intent.get("signal_id", ""),
        idempotency_key=intent.get("idempotency_key", ""),
        broker_local_reconciliation=inputs.get("reconciliation") or {},
        require_broker_local_reconciliation=True,
    )


def market_closed_flat_new_signal_allowed(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return bool(market_closed_flat_contract(args, inputs)["accepted"])


def future_state_compatible(args: argparse.Namespace, inputs: dict[str, Any]) -> tuple[bool, bool]:
    if not inputs["future_state_exists"]:
        return True, False
    state = inputs["future_state"]
    intent = first_row(inputs["request_intent"])
    incompatible, same_active_key = state_contracts.future_state_is_incompatible_without_explicit_client_reject_contract(
        state,
        signal_id=intent.get("signal_id", ""),
        idempotency_key=intent.get("idempotency_key", ""),
    )
    if client_reject_flat_resend_allowed(args, inputs):
        return True, False
    if market_closed_flat_new_signal_allowed(args, inputs):
        return True, False
    return not incompatible, same_active_key


def binding_valid(inputs: dict[str, Any]) -> bool:
    intent = first_row(inputs["request_intent"])
    checked = first_row(inputs["order_check_bound_intent"])
    approval = inputs["approval"]
    for field in ("signal_id", "idempotency_key", "approval_record_id", "symbol", "side", "volume_lots", "sl_price", "tp_price"):
        values = [str(source.get(field)) for source in (intent, checked, approval) if source.get(field) not in (None, "")]
        if values and len(set(values)) > 1:
            return False
    return True


def digest_binding_summary(inputs: dict[str, Any], *, required: bool) -> dict[str, Any]:
    missing_count = 0
    mismatch_count = 0
    if required:
        paths = inputs["paths"]
        intent = first_row(inputs["request_intent"])
        approval = inputs["approval"]
        request_manifest = inputs["request_manifest"]
        order_check_manifest = inputs["order_check_manifest"]
        checks = [
            (intent.get("approval_record_digest"), approval.get("record_hash_or_digest")),
            (request_manifest.get("request_intent_digest"), sha256_file(paths["request_intent"])),
            (request_manifest.get("request_fields_digest"), sha256_file(paths["request_fields"])),
            (order_check_manifest.get("request_intent_digest"), request_manifest.get("request_intent_digest")),
            (order_check_manifest.get("request_fields_digest"), request_manifest.get("request_fields_digest")),
            (order_check_manifest.get("approval_record_digest"), approval.get("record_hash_or_digest")),
            (
                order_check_manifest.get("order_check_manifest_digest"),
                sha256_payload_excluding(order_check_manifest, {"order_check_manifest_digest"}),
            ),
            (order_check_manifest.get("order_check_result_digest"), sha256_file(paths["order_check_result"])),
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
        "approval, request, order-check manifest, and order-check result SHA-256 digests present and matching",
        inputs["paths"]["order_check_manifest"],
        (
            "order_send_pilot_blocked_missing_digest_binding"
            if summary["missing_digest_count"]
            else "order_send_pilot_blocked_digest_mismatch"
        ),
    )


def gate_row(args: argparse.Namespace, name: str, ok: bool, observed: Any, expected: Any, source: Path | str, code: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "gate_name": name,
        "gate_status": "passed" if ok else "failed",
        "observed_value": observed,
        "expected_value": expected,
        "source_path": str(source),
        "blocking_if_failed": True,
        "warning_code": "" if ok else code,
    }


def structural_gates(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    paths = inputs["paths"]
    state_ok, same_active_key = future_state_compatible(args, inputs)
    client_reject_candidate = client_reject_flat_resend_candidate(inputs)
    approval_state = approval_status(args, inputs)
    gates = [
        gate_row(args, "canonical_registry", canonical_valid(inputs["registry"]), inputs["registry"].get("candidate_id"), CANDIDATE_ID, paths["registry"], "order_send_pilot_blocked_unsafe_policy"),
        gate_row(args, "demo_execution_policy", policy_valid(inputs["policy"]), inputs["policy"].get("policy_id"), "canonical no-execution base policy plus explicit pilot flags", paths["policy"], "order_send_pilot_blocked_unsafe_policy"),
        gate_row(args, "max_order_send_attempts", safe_int(args.max_order_send_attempts) == 1, args.max_order_send_attempts, 1, "cli:max_order_send_attempts", "order_send_pilot_blocked_max_attempts_not_one"),
        gate_row(args, "readiness_not_fixture", not fixture_source(inputs), readiness_status(inputs), "non-fixture upstream artifacts", paths["readiness_manifest"], "order_send_pilot_blocked_fixture_only_readiness"),
        gate_row(args, "readiness_available", readiness_valid(inputs), readiness_status(inputs), "order_send_pilot_readiness_plan_available_no_send", paths["readiness_manifest"], "order_send_pilot_blocked_fixture_only_readiness"),
        gate_row(args, "passed_order_check", order_check_valid(inputs), inputs["order_check_manifest"].get("order_check_status"), "order_check_available_passed_no_send called once", paths["order_check_manifest"], "order_send_pilot_blocked_no_passed_order_check"),
        gate_row(args, "request_intent", request_valid(args, inputs), inputs["request_manifest"].get("request_construction_status"), "valid non-executable request intent or explicit demo module validation request", paths["request_manifest"], "order_send_pilot_blocked_no_passed_order_check"),
        gate_row(args, "approval_record", approval_state == "valid", approval_state, "valid unexpired non-revoked approval", paths["approval"], "order_send_pilot_blocked_expired_approval" if approval_state == "expired" else "order_send_pilot_blocked_no_passed_order_check"),
        gate_row(args, "fresh_signal", freshness_valid(inputs["freshness"]), inputs["freshness"].get("freshness_status"), "fresh signal within horizon", paths["freshness"], "order_send_pilot_blocked_stale_signal"),
        gate_row(args, "broker_local_reconciliation", reconciliation_valid(inputs["reconciliation"]), inputs["reconciliation"].get("reconciliation_status"), "clean no local/no broker", paths["reconciliation"], "order_send_pilot_blocked_broker_local_reconciliation"),
        gate_row(args, "margin_policy", margin_valid(inputs["margin"], inputs["margin_snapshot"]), inputs["margin"].get("broker_margin_usage_ratio"), "<= 0.70 and spread within policy", paths["margin"], "order_send_pilot_blocked_margin_policy"),
        gate_row(args, "duplicate_protection", duplicate_valid(inputs["duplicate"]), inputs["duplicate"].get("plan_status"), "duplicate protection available and max_open_positions=1", paths["duplicate"], "order_send_pilot_blocked_duplicate_protection"),
        gate_row(args, "kill_switch", kill_switch_valid(inputs["manual_plan"]), inputs["manual_plan"].get("kill_switch_executed"), False, paths["manual_plan"], "order_send_pilot_blocked_kill_switch"),
        gate_row(
            args,
            "future_state_compatible",
            state_ok,
            state_status(inputs["future_state"]) or "missing",
            "missing, terminal-safe state, or explicit demo client-reject-flat resend",
            paths["future_state"],
            (
                "order_send_pilot_blocked_client_reject_resend_acknowledgment"
                if same_active_key and client_reject_candidate
                else "order_send_pilot_blocked_existing_active_idempotency_key"
                if same_active_key
                else "order_send_pilot_blocked_future_state_incompatible"
            ),
        ),
        gate_row(args, "request_order_check_send_binding", binding_valid(inputs), "evaluated", "matching intent/check/approval and available digests", paths["order_check_bound_intent"], "order_send_pilot_blocked_no_passed_order_check"),
    ]
    if request_demo_module_validation_manifest(inputs["request_manifest"]):
        gates.append(
            gate_row(
                args,
                "demo_module_validation_stale_override_acknowledgment",
                stale_override_allowed(args, inputs),
                f"module_validation_demo_execution={args.module_validation_demo_execution};allow_stale={args.allow_stale_upstream_artifacts_for_demo_module_validation};ack={args.module_validation_acknowledgment or ''}",
                f"ack={MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT}",
                paths["request_manifest"],
                "order_send_pilot_blocked_demo_module_validation_acknowledgment",
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
                paths["approval"],
                "order_send_pilot_blocked_expired_signal_override_acknowledgment",
            )
        )
    return gates


def first_failed_status(gates: list[dict[str, Any]]) -> str:
    for row in gates:
        if row["gate_status"] == "failed":
            return str(row["warning_code"])
    return ""


def effective_dry_run(args: argparse.Namespace) -> bool:
    if args.dry_run is True:
        return True
    if args.allow_real_order_send:
        return False
    return True if args.dry_run is None else bool(args.dry_run)


def warning_row(args: argparse.Namespace, code: str, message: str, source: Path | str, blocking: bool) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "warning_code": code,
        "severity": "error" if blocking else "warning",
        "message": message,
        "source": str(source),
        "blocking_warning": blocking,
    }


def add_artifact_freshness_warnings(
    args: argparse.Namespace,
    warnings: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        if not status_is_stale(row["status"]):
            continue
        blocking = row.get("blocking_if_stale") is True
        warnings.append(
            warning_row(
                args,
                "order_send_pilot_blocked_stale_upstream_artifact" if blocking else "stale_upstream_artifact_warning",
                f"Artifact freshness check failed for {row['artifact_name']}: {row['status']}.",
                row["path"],
                blocking,
            )
        )


def state_claim_preview(args: argparse.Namespace, inputs: dict[str, Any], would_write: bool) -> dict[str, Any]:
    intent = first_row(inputs["request_intent"])
    approval = inputs["approval"]
    previous_state = inputs.get("future_state", {})
    preview = {
        "state_version": 1,
        "candidate_id": CANDIDATE_ID,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "direction": DIRECTION,
        "signal_id": intent.get("signal_id") or approval.get("signal_id"),
        "idempotency_key": intent.get("idempotency_key") or approval.get("idempotency_key"),
        "approval_record_id": intent.get("approval_record_id") or approval.get("approval_record_id"),
        "request_intent_digest": sha256_file(inputs["paths"]["request_intent"]),
        "order_check_run_id": inputs["order_check_manifest"].get("run_id"),
        "order_check_digest": sha256_file(inputs["paths"]["order_check_manifest"]),
        "send_attempt_id": args.run_id,
        "state_status": "pre_send_pending",
        "pre_send_claimed_at_utc": utc_now_text() if would_write else "",
        "send_started_at_utc": "",
        "send_completed_at_utc": "",
        "broker_order_ticket": "",
        "broker_deal_ticket": "",
        "broker_position_ticket": "",
        "last_retcode": "",
        "reconciliation_status": "pre_send_recheck_required",
        "crash_recovery_required": True,
        "state_write_planned": would_write,
        "state_write_performed": False,
        "exclusive_claim_lock_required": True,
        "compare_and_swap_equivalent": "exclusive_lock_plus_fresh_state_reread",
    }
    if client_reject_flat_resend_allowed(args, inputs):
        preview.update(
            {
                "explicit_second_demo_send_after_client_reject_flat": True,
                "previous_send_retcode": previous_state.get("last_retcode"),
                "previous_state_status": previous_state.get("state_status", ""),
                "previous_reconciliation_status": previous_state.get("reconciliation_status", ""),
                "previous_send_attempt_id": previous_state.get("send_attempt_id", ""),
                "previous_send_started_at_utc": previous_state.get("send_started_at_utc", ""),
                "previous_send_completed_at_utc": previous_state.get("send_completed_at_utc", ""),
                "previous_order_execution_performed": previous_state.get("order_execution_performed"),
                "previous_broker_order_ticket": previous_state.get("broker_order_ticket", ""),
                "previous_broker_deal_ticket": previous_state.get("broker_deal_ticket", ""),
                "previous_broker_position_ticket": previous_state.get("broker_position_ticket", ""),
                "automatic_retry_allowed": False,
                "retry_performed": False,
                "new_operator_authorized_attempt": True,
                "client_reject_resend_acknowledgment_valid": True,
            }
        )
    market_contract = market_closed_flat_contract(args, inputs)
    if market_contract.get("accepted"):
        preview.update(
            {
                "explicit_new_signal_after_market_closed_flat": True,
                "previous_send_retcode": previous_state.get("last_retcode"),
                "previous_state_status": previous_state.get("state_status", ""),
                "previous_reconciliation_status": previous_state.get("reconciliation_status", ""),
                "previous_send_attempt_id": previous_state.get("send_attempt_id", ""),
                "previous_send_started_at_utc": previous_state.get("send_started_at_utc", ""),
                "previous_send_completed_at_utc": previous_state.get("send_completed_at_utc", ""),
                "previous_order_execution_performed": previous_state.get("order_execution_performed"),
                "previous_broker_order_ticket": previous_state.get("broker_order_ticket", ""),
                "previous_broker_deal_ticket": previous_state.get("broker_deal_ticket", ""),
                "previous_broker_position_ticket": previous_state.get("broker_position_ticket", ""),
                "new_signal_id_differs_from_previous_state": not bool(market_contract.get("same_signal_id")),
                "new_idempotency_key_differs_from_previous_state": not bool(
                    market_contract.get("same_idempotency_key")
                ),
                "automatic_retry_allowed": False,
                "retry_performed": False,
                "new_operator_authorized_attempt": False,
            }
        )
    return preview


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


def comment_diagnostics(comment: Any) -> dict[str, Any]:
    return {
        "comment_length": len(comment) if isinstance(comment, str) else 0,
        "comment_redacted_preview": redacted_comment_preview(comment),
        "comment_broker_safe": broker_comment_is_safe(comment),
    }


def payload_preview_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    intent = first_row(inputs["request_intent"])
    broker_safe_comment = build_broker_safe_comment(CANDIDATE_ID, intent.get("idempotency_key", ""))
    specs = [
        ("action", "TRADE_ACTION_DEAL", "fixed future mapping"),
        ("symbol", SYMBOL, "canonical registry"),
        ("volume", intent.get("volume_lots", ""), "bound request intent"),
        ("type", "ORDER_TYPE_SELL", "fixed candidate direction"),
        ("price", "current_bid_at_single_send_attempt", "future bounded tick read"),
        ("sl", intent.get("sl_price", ""), "bound request intent"),
        ("tp", intent.get("tp_price", ""), "bound request intent"),
        ("deviation", 10, "conservative pilot default"),
        ("magic", 151015, "deterministic candidate magic"),
        ("comment", redacted_comment_preview(broker_safe_comment), "broker-safe short audit reference"),
        ("type_time", "ORDER_TIME_GTC", "single-shot pilot policy"),
        ("type_filling", "ORDER_FILLING_IOC", "pilot default subject to symbol gate"),
    ]
    return [
        {
            "run_id": args.run_id,
            "field_name": name,
            "preview_value": value,
            "source": source,
            "in_memory_only_if_real_send": True,
            "persisted_executable_field": False,
            "safety_note": "non_executable_preview_only",
        }
        for name, value, source in specs
    ]


def account_is_demo(mt5: Any, account: Any) -> bool:
    demo_mode = object_value(mt5, "ACCOUNT_TRADE_MODE_DEMO")
    trade_mode = object_value(account, "trade_mode")
    return str(trade_mode).lower() == "demo" if demo_mode is None else trade_mode == demo_mode


def bool_is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def auto_trading_flags_enabled(terminal: Any, account: Any) -> bool:
    return bool_is_true(object_value(terminal, "trade_allowed")) and bool_is_true(
        object_value(account, "trade_allowed")
    )


def redacted_broker_snapshot(
    *,
    imported: bool,
    connected: bool,
    terminal: Any = None,
    account: Any = None,
    symbol: Any = None,
    tick: Any = None,
    positions_count: int = 0,
    orders_count: int = 0,
    positions_calls: int = 0,
    orders_calls: int = 0,
) -> dict[str, Any]:
    return {
        "mt5_import_performed": imported,
        "mt5_connection_performed": connected,
        "terminal_info_available": terminal is not None,
        "terminal_connected": object_value(terminal, "connected"),
        "terminal_trade_allowed": object_value(terminal, "trade_allowed"),
        "account_info_available": account is not None,
        "account_trade_mode_raw": object_value(account, "trade_mode"),
        "account_trade_allowed": object_value(account, "trade_allowed"),
        "account_currency": object_value(account, "currency"),
        "is_demo_account": None if account is None else str(object_value(account, "trade_mode")).lower() == "demo",
        "symbol_info_available": symbol is not None,
        "symbol": object_value(symbol, "name", SYMBOL),
        "symbol_visible": object_value(symbol, "visible"),
        "symbol_spread": object_value(symbol, "spread"),
        "tick_available": tick is not None,
        "bid_present": object_value(tick, "bid") is not None,
        "ask_present": object_value(tick, "ask") is not None,
        "broker_position_count_symbol_before_send": positions_count,
        "broker_pending_order_count_symbol_before_send": orders_count,
        "positions_get_call_count": positions_calls,
        "orders_get_call_count": orders_calls,
        "redaction_applied": True,
    }


def result_category(mt5: Any, result: Any) -> str:
    if result is None:
        return "result_none"
    retcode = object_value(result, "retcode")
    if client_autotrading_disabled_result(result):
        return "client_autotrading_disabled"
    mappings = (
        ("success_deal", "TRADE_RETCODE_DONE"),
        ("success_placed", "TRADE_RETCODE_PLACED"),
        ("partial_fill", "TRADE_RETCODE_DONE_PARTIAL"),
        ("reject", "TRADE_RETCODE_REJECT"),
        ("requote", "TRADE_RETCODE_REQUOTE"),
        ("price_changed", "TRADE_RETCODE_PRICE_CHANGED"),
        ("price_off", "TRADE_RETCODE_PRICE_OFF"),
        ("invalid_stops", "TRADE_RETCODE_INVALID_STOPS"),
        ("invalid_volume", "TRADE_RETCODE_INVALID_VOLUME"),
        ("invalid_filling", "TRADE_RETCODE_INVALID_FILL"),
        ("market_closed", "TRADE_RETCODE_MARKET_CLOSED"),
        ("no_money", "TRADE_RETCODE_NO_MONEY"),
        ("trade_disabled", "TRADE_RETCODE_TRADE_DISABLED"),
        ("too_many_requests", "TRADE_RETCODE_TOO_MANY_REQUESTS"),
        ("connection_lost", "TRADE_RETCODE_CONNECTION"),
    )
    for category, constant in mappings:
        expected = object_value(mt5, constant)
        if expected is not None and retcode == expected:
            return category
    return "unknown_retcode"


def result_has_no_broker_ticket(result: Any) -> bool:
    return all(
        empty_ticket(object_value(result, field))
        for field in ("order", "deal", "position")
    )


def client_autotrading_disabled_result(result: Any) -> bool:
    comment = str(object_value(result, "comment") or "").lower()
    return (
        safe_int(object_value(result, "retcode")) == CLIENT_AUTOTRADING_DISABLED_RETCODE
        and CLIENT_AUTOTRADING_DISABLED_COMMENT in comment
        and result_has_no_broker_ticket(result)
    )


def retcode_name(category: str, result: Any) -> str:
    if category == "client_autotrading_disabled":
        return "TRADE_RETCODE_CLIENT_DISABLES_AT"
    retcode = safe_int(object_value(result, "retcode"))
    if retcode is None:
        return ""
    return ""


def recommended_recovery_action(category: str, reconciliation_status: str = "") -> str:
    if category == "client_autotrading_disabled":
        if reconciliation_status == "broker_local_reconciliation_clean_after_client_reject_no_broker_state":
            return "finalize_state_as_send_rejected_no_position_no_order_after_operator_review"
        return "perform_bounded_broker_local_reconciliation_then_finalize_or_hold"
    return ""


def state_after_result(pre_state: dict[str, Any], category: str, result: Any) -> dict[str, Any]:
    state = dict(pre_state)
    state["send_completed_at_utc"] = utc_now_text()
    state["last_retcode"] = object_value(result, "retcode")
    state["broker_order_ticket"] = object_value(result, "order", "")
    state["broker_deal_ticket"] = object_value(result, "deal", "")
    state["broker_position_ticket"] = object_value(result, "position", "")
    state["reconciliation_status"] = "reconciliation_required_after_send"
    state["crash_recovery_required"] = True
    if category == "success_deal":
        state["state_status"] = "open_reconciliation_required"
    elif category == "success_placed":
        state["state_status"] = "pending_reconciliation_required"
    elif category == "client_autotrading_disabled":
        state["state_status"] = "send_rejected_no_position_no_order"
    elif category in {"reject", "requote", "price_changed", "price_off", "invalid_stops", "invalid_volume", "invalid_filling", "market_closed", "no_money", "trade_disabled", "too_many_requests"}:
        state["state_status"] = "execution_rejected"
    else:
        state["state_status"] = "reconciliation_hold"
    return state


def redacted_send_result(
    result: Any,
    category: str,
    error: str = "",
    *,
    send_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostics = comment_diagnostics((send_parameters or {}).get("comment"))
    return {
        "result_available": result is not None,
        "order_send_result_category": category,
        "retcode": object_value(result, "retcode"),
        "retcode_name": retcode_name(category, result),
        "comment": object_value(result, "comment"),
        "order_ticket": object_value(result, "order"),
        "deal_ticket": object_value(result, "deal"),
        "position_ticket": object_value(result, "position"),
        "volume_present": object_value(result, "volume") is not None,
        "price_present": object_value(result, "price") is not None,
        "no_broker_ticket_returned": result is not None and result_has_no_broker_ticket(result),
        "recommended_recovery_action": recommended_recovery_action(category),
        "error": error,
        "raw_executable_payload_written": False,
        "redaction_applied": True,
        **diagnostics,
    }


def status_for_category(category: str) -> str:
    if category == "success_deal":
        return "order_send_pilot_sent_success_deal_reconciliation_required"
    if category == "success_placed":
        return "order_send_pilot_sent_success_placed_reconciliation_required"
    if category == "client_autotrading_disabled":
        return "order_send_pilot_blocked_client_autotrading_disabled_no_send_confirmed"
    if category in {"reject", "requote", "price_changed", "price_off", "invalid_stops", "invalid_volume", "invalid_filling", "market_closed", "no_money", "trade_disabled", "too_many_requests"}:
        return "order_send_pilot_sent_rejected_no_retry"
    return "order_send_pilot_sent_uncertain_reconciliation_hold"


def safe_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        return list(value)
    except TypeError:
        return []


def redacted_identifier(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value)
    return f"redacted:{text[-4:]}"


def broker_state_read(mt5: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "positions": [],
        "orders": [],
        "positions_get_called": False,
        "positions_get_call_count": 0,
        "orders_get_called": False,
        "orders_get_call_count": 0,
        "error": "",
    }
    try:
        positions = mt5.positions_get(symbol=SYMBOL)
        result["positions_get_called"] = True
        result["positions_get_call_count"] = 1
    except Exception as exc:  # noqa: BLE001
        result["positions_get_called"] = True
        result["positions_get_call_count"] = 1
        result["error"] = f"positions_get_failed:{exc}"
        return result
    try:
        orders = mt5.orders_get(symbol=SYMBOL)
        result["orders_get_called"] = True
        result["orders_get_call_count"] = 1
    except Exception as exc:  # noqa: BLE001
        result["orders_get_called"] = True
        result["orders_get_call_count"] = 1
        result["positions"] = safe_sequence(positions)
        result["error"] = f"orders_get_failed:{exc}"
        return result
    result["positions"] = safe_sequence(positions)
    result["orders"] = safe_sequence(orders)
    if positions is None or orders is None:
        result["error"] = "broker_state_read_returned_none"
    return result


def type_matches_sell(mt5: Any, value: Any, *, item_kind: str) -> bool | None:
    if value in (None, ""):
        return None
    text = str(value).lower()
    if "sell" in text or "short" in text:
        return True
    if "buy" in text or "long" in text:
        return False
    constant_names = ["ORDER_TYPE_SELL"]
    if item_kind == "position":
        constant_names.insert(0, "POSITION_TYPE_SELL")
    expected = [object_value(mt5, name) for name in constant_names]
    expected = [item for item in expected if item is not None]
    if expected:
        return value in expected or str(value) in {str(item) for item in expected}
    return None


def float_matches(observed: Any, expected: Any, tolerance: float) -> bool | None:
    observed_float = safe_float(observed)
    expected_float = safe_float(expected)
    if observed_float is None or expected_float is None:
        return None
    return abs(observed_float - expected_float) <= tolerance


def broker_item_snapshot(item: Any, *, mt5: Any, item_kind: str, intent: dict[str, str]) -> dict[str, Any]:
    observed_symbol = object_value(item, "symbol")
    observed_type = object_value(item, "type")
    observed_volume = object_value(item, "volume", object_value(item, "volume_current"))
    observed_sl = object_value(item, "sl")
    observed_tp = object_value(item, "tp")
    symbol_match = observed_symbol == SYMBOL
    side_match = type_matches_sell(mt5, observed_type, item_kind=item_kind)
    volume_match = float_matches(observed_volume, intent.get("volume_lots"), VOLUME_TOLERANCE)
    sl_match = float_matches(observed_sl, intent.get("sl_price"), PRICE_TOLERANCE)
    tp_match = float_matches(observed_tp, intent.get("tp_price"), PRICE_TOLERANCE)
    mismatch_reasons: list[str] = []
    if not symbol_match:
        mismatch_reasons.append("symbol_mismatch")
    if side_match is False:
        mismatch_reasons.append("side_mismatch")
    if volume_match is False:
        mismatch_reasons.append("volume_mismatch")
    if sl_match is False:
        mismatch_reasons.append("sl_mismatch")
    if tp_match is False:
        mismatch_reasons.append("tp_mismatch")
    matched = symbol_match and side_match is not False and volume_match is not False and sl_match is not False and tp_match is not False
    return {
        "kind": item_kind,
        "symbol": observed_symbol,
        "type": "" if observed_type is None else str(observed_type),
        "volume": observed_volume,
        "sl": observed_sl,
        "tp": observed_tp,
        "ticket_redacted": redacted_identifier(object_value(item, "ticket")),
        "order_redacted": redacted_identifier(object_value(item, "order")),
        "deal_redacted": redacted_identifier(object_value(item, "deal")),
        "position_redacted": redacted_identifier(object_value(item, "position", object_value(item, "identifier"))),
        "matched_expected_symbol": symbol_match,
        "matched_expected_side": side_match,
        "matched_expected_volume": volume_match,
        "matched_expected_sl": sl_match,
        "matched_expected_tp": tp_match,
        "matched_expected_state": matched,
        "mismatch_reasons": mismatch_reasons,
    }


def reconcile_post_send(mt5: Any, inputs: dict[str, Any], category: str) -> dict[str, Any]:
    intent = first_row(inputs["request_intent"])
    read = broker_state_read(mt5)
    positions = read["positions"]
    orders = read["orders"]
    position_rows = [broker_item_snapshot(item, mt5=mt5, item_kind="position", intent=intent) for item in positions]
    order_rows = [broker_item_snapshot(item, mt5=mt5, item_kind="order", intent=intent) for item in orders]
    position_count = len(position_rows)
    order_count = len(order_rows)
    total_state_count = position_count + order_count
    matched_positions = [row for row in position_rows if row["matched_expected_state"] is True]
    matched_orders = [row for row in order_rows if row["matched_expected_state"] is True]
    mismatch_reasons = sorted(
        {
            reason
            for row in [*position_rows, *order_rows]
            for reason in row.get("mismatch_reasons", [])
        }
    )
    success_categories = {"success_deal", "success_placed", "partial_fill"}
    reject_categories = {
        "reject",
        "requote",
        "price_changed",
        "price_off",
        "invalid_stops",
        "invalid_volume",
        "invalid_filling",
        "market_closed",
        "no_money",
        "trade_disabled",
        "too_many_requests",
    }
    client_reject_categories = {"client_autotrading_disabled"}
    if read["error"]:
        reconciliation_status = "broker_local_reconciliation_unavailable_after_send"
        state_status_value = "reconciliation_hold"
    elif total_state_count > MAX_OPEN_POSITIONS:
        reconciliation_status = "broker_local_reconciliation_multiple_states_after_send"
        state_status_value = "reconciliation_hold"
    elif category in success_categories:
        if total_state_count == 0:
            reconciliation_status = "broker_local_reconciliation_missing_after_claimed_success"
            state_status_value = "reconciliation_hold"
        elif len(matched_positions) + len(matched_orders) == 1 and not mismatch_reasons:
            reconciliation_status = "broker_local_reconciliation_matched_after_send"
            state_status_value = "broker_position_detected" if matched_positions else "broker_pending_order_detected"
        else:
            reconciliation_status = "broker_local_reconciliation_mismatch_after_send"
            state_status_value = "reconciliation_hold"
    elif category in reject_categories and total_state_count == 0:
        reconciliation_status = "broker_local_reconciliation_clean_after_reject_no_broker_state"
        state_status_value = "execution_rejected"
    elif category in client_reject_categories and total_state_count == 0:
        reconciliation_status = "broker_local_reconciliation_clean_after_client_reject_no_broker_state"
        state_status_value = "send_rejected_no_position_no_order"
    elif category in client_reject_categories:
        reconciliation_status = "broker_local_reconciliation_unexpected_broker_state_after_client_reject"
        state_status_value = "reconciliation_hold"
    elif category in reject_categories or total_state_count > 0:
        reconciliation_status = "broker_local_reconciliation_unexpected_broker_state_after_non_success"
        state_status_value = "reconciliation_hold"
    else:
        reconciliation_status = "broker_local_reconciliation_missing_after_uncertain_result"
        state_status_value = "reconciliation_hold"
    recovery_action = recommended_recovery_action(category, reconciliation_status)
    return {
        "post_send_reconciliation_performed": True,
        "post_send_positions_get_called": read["positions_get_called"],
        "post_send_positions_get_call_count": read["positions_get_call_count"],
        "post_send_orders_get_called": read["orders_get_called"],
        "post_send_orders_get_call_count": read["orders_get_call_count"],
        "broker_position_detected_after_send": position_count > 0,
        "broker_pending_order_detected_after_send": order_count > 0,
        "broker_position_count_after_send": position_count,
        "broker_pending_order_count_after_send": order_count,
        "reconciliation_status": reconciliation_status,
        "state_status": state_status_value,
        "recommended_recovery_action": recovery_action,
        "reconciliation_snapshot": {
            "reconciliation_status": reconciliation_status,
            "post_send_reconciliation_performed": True,
            "bounded_reads_only": True,
            "polling_performed": False,
            "retry_performed": False,
            "second_send_allowed": False,
            "history_reads_performed": False,
            "symbol": SYMBOL,
            "expected_side": SIDE,
            "expected_volume_lots": safe_float(intent.get("volume_lots")),
            "expected_sl": safe_float(intent.get("sl_price")),
            "expected_tp": safe_float(intent.get("tp_price")),
            "positions_get_called": read["positions_get_called"],
            "positions_get_call_count": read["positions_get_call_count"],
            "orders_get_called": read["orders_get_called"],
            "orders_get_call_count": read["orders_get_call_count"],
            "broker_position_count_after_send": position_count,
            "broker_pending_order_count_after_send": order_count,
            "broker_position_detected_after_send": position_count > 0,
            "broker_pending_order_detected_after_send": order_count > 0,
            "matching_position_count": len(matched_positions),
            "matching_pending_order_count": len(matched_orders),
            "mismatch_reasons": mismatch_reasons,
            "query_error": read["error"],
            "result_category": category,
            "recommended_recovery_action": recovery_action,
            "positions": position_rows,
            "orders": order_rows,
            "redaction_applied": True,
            "raw_executable_payload_written": False,
        },
    }


def run_real_send(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    runtime: dict[str, Any] = {
        "status": "",
        "mt5_import_performed": False,
        "mt5_connection_performed": False,
        "broker_api_query_performed": False,
        "positions_get_call_count": 0,
        "orders_get_call_count": 0,
        "order_send_call_count": 0,
        "order_send_retcode": None,
        "order_send_result_category": "",
        "order_execution_performed": False,
        "future_state_json_written": False,
        "state_status": "",
        "broker_position_detected_after_send": False,
        "broker_pending_order_detected_after_send": False,
        "broker_position_count_after_send": 0,
        "broker_pending_order_count_after_send": 0,
        "post_send_reconciliation_performed": False,
        "post_send_positions_get_called": False,
        "post_send_positions_get_call_count": 0,
        "post_send_orders_get_called": False,
        "post_send_orders_get_call_count": 0,
        "reconciliation_status": "not_started",
        "broker_snapshot": redacted_broker_snapshot(imported=False, connected=False),
        "send_result_snapshot": redacted_send_result(None, "not_called"),
        "reconciliation_snapshot": {"reconciliation_status": "not_started", "bounded_reads_only": True},
    }
    claim_lock_handle: int | None = None
    claim_lock_path: Path | None = None
    try:
        mt5 = importlib.import_module(args.mt5_package)
        runtime["mt5_import_performed"] = True
    except Exception as exc:  # noqa: BLE001
        runtime["status"] = "order_send_pilot_blocked_mt5_import_failure"
        runtime["send_result_snapshot"] = redacted_send_result(None, "not_called", str(exc))
        return runtime
    try:
        try:
            initialized = bool(mt5.initialize())
        except Exception as exc:  # noqa: BLE001
            runtime["status"] = "order_send_pilot_blocked_mt5_initialize_failure"
            runtime["send_result_snapshot"] = redacted_send_result(None, "not_called", str(exc))
            return runtime
        if not initialized:
            runtime["status"] = "order_send_pilot_blocked_mt5_initialize_failure"
            return runtime
        runtime["mt5_connection_performed"] = True
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        symbol = mt5.symbol_info(SYMBOL)
        tick = mt5.symbol_info_tick(SYMBOL)
        runtime["broker_api_query_performed"] = True
        if account is None or not account_is_demo(mt5, account):
            runtime["status"] = "order_send_pilot_blocked_non_demo_account"
            runtime["broker_snapshot"] = redacted_broker_snapshot(imported=True, connected=True, terminal=terminal, account=account, symbol=symbol, tick=tick)
            return runtime
        if client_reject_flat_resend_allowed(args, inputs) and not auto_trading_flags_enabled(terminal, account):
            runtime["status"] = "order_send_pilot_blocked_client_reject_resend_autotrading_disabled"
            runtime["broker_snapshot"] = redacted_broker_snapshot(imported=True, connected=True, terminal=terminal, account=account, symbol=symbol, tick=tick)
            return runtime
        if object_value(account, "currency") != "EUR":
            runtime["status"] = "order_send_pilot_blocked_account_currency_mismatch"
            runtime["broker_snapshot"] = redacted_broker_snapshot(imported=True, connected=True, terminal=terminal, account=account, symbol=symbol, tick=tick)
            return runtime
        if symbol is None or object_value(symbol, "visible") is not True:
            runtime["status"] = "order_send_pilot_blocked_symbol_unavailable"
            runtime["broker_snapshot"] = redacted_broker_snapshot(imported=True, connected=True, terminal=terminal, account=account, symbol=symbol, tick=tick)
            return runtime
        if tick is None or safe_float(object_value(tick, "bid")) is None:
            runtime["status"] = "order_send_pilot_blocked_tick_unavailable"
            runtime["broker_snapshot"] = redacted_broker_snapshot(imported=True, connected=True, terminal=terminal, account=account, symbol=symbol, tick=tick)
            return runtime
        spread = safe_float(object_value(symbol, "spread"))
        if spread is None or spread > MAX_SPREAD_POINTS:
            runtime["status"] = "order_send_pilot_blocked_margin_policy"
            runtime["broker_snapshot"] = redacted_broker_snapshot(imported=True, connected=True, terminal=terminal, account=account, symbol=symbol, tick=tick)
            return runtime
        pre_send_state = broker_state_read(mt5)
        runtime["positions_get_call_count"] = pre_send_state["positions_get_call_count"]
        runtime["orders_get_call_count"] = pre_send_state["orders_get_call_count"]
        if pre_send_state["error"]:
            runtime["status"] = "order_send_pilot_blocked_broker_local_reconciliation"
            runtime["send_result_snapshot"] = redacted_send_result(None, "not_called", str(pre_send_state["error"]))
            return runtime
        positions = pre_send_state["positions"]
        orders = pre_send_state["orders"]
        if positions is None or orders is None or len(positions) > 0 or len(orders) > 0:
            runtime["status"] = "order_send_pilot_blocked_broker_local_reconciliation"
            runtime["broker_snapshot"] = redacted_broker_snapshot(
                imported=True,
                connected=True,
                terminal=terminal,
                account=account,
                symbol=symbol,
                tick=tick,
                positions_count=len(positions),
                orders_count=len(orders),
                positions_calls=pre_send_state["positions_get_call_count"],
                orders_calls=pre_send_state["orders_get_call_count"],
            )
            return runtime
        runtime["broker_snapshot"] = redacted_broker_snapshot(
            imported=True,
            connected=True,
            terminal=terminal,
            account=account,
            symbol=symbol,
            tick=tick,
            positions_calls=pre_send_state["positions_get_call_count"],
            orders_calls=pre_send_state["orders_get_call_count"],
        )
        if approval_status(args, inputs) != "valid":
            runtime["status"] = "order_send_pilot_blocked_expired_approval"
            return runtime
        if not freshness_valid(inputs["freshness"]):
            runtime["status"] = "order_send_pilot_blocked_stale_signal"
            return runtime
        if not all(
            (
                reconciliation_valid(inputs["reconciliation"]),
                margin_valid(inputs["margin"], inputs["margin_snapshot"]),
                duplicate_valid(inputs["duplicate"]),
                kill_switch_valid(inputs["manual_plan"]),
                binding_valid(inputs),
            )
        ):
            runtime["status"] = "order_send_pilot_blocked_broker_local_reconciliation"
            return runtime
        intent = first_row(inputs["request_intent"])
        send_parameters = {
            "action": object_value(mt5, "TRADE_ACTION_DEAL"),
            "symbol": SYMBOL,
            "volume": safe_float(intent.get("volume_lots")),
            "type": object_value(mt5, "ORDER_TYPE_SELL"),
            "price": safe_float(object_value(tick, "bid")),
            "sl": safe_float(intent.get("sl_price")),
            "tp": safe_float(intent.get("tp_price")),
            "deviation": 10,
            "magic": 151015,
            "comment": build_broker_safe_comment(CANDIDATE_ID, intent.get("idempotency_key", "")),
            "type_time": object_value(mt5, "ORDER_TIME_GTC"),
            "type_filling": object_value(mt5, "ORDER_FILLING_IOC"),
        }
        if not broker_comment_is_safe(send_parameters["comment"]):
            runtime["status"] = "order_send_pilot_blocked_invalid_order_send_payload"
            runtime["send_result_snapshot"] = redacted_send_result(
                None,
                "not_called",
                "invalid_broker_comment",
                send_parameters=send_parameters,
            )
            runtime["state_status"] = "reconciliation_hold"
            return runtime
        try:
            claim_lock_handle, claim_lock_path = acquire_state_claim_lock(Path(args.future_state_json), args.run_id)
        except OSError as exc:
            runtime["status"] = "order_send_pilot_blocked_state_claim_failed"
            runtime["send_result_snapshot"] = redacted_send_result(None, "not_called", str(exc))
            runtime["state_status"] = "reconciliation_hold"
            return runtime
        fresh_state, fresh_state_error = read_json(Path(args.future_state_json))
        inputs["future_state_exists"] = Path(args.future_state_json).exists()
        inputs["future_state"] = fresh_state
        if fresh_state_error not in ("", "missing") or not future_state_compatible(args, inputs)[0]:
            runtime["status"] = "order_send_pilot_blocked_existing_active_idempotency_key"
            runtime["state_status"] = state_status(fresh_state) or "reconciliation_hold"
            return runtime
        pre_state = state_claim_preview(args, inputs, True)
        pre_state["state_write_performed"] = True
        try:
            atomic_write_json(Path(args.future_state_json), pre_state)
        except Exception as exc:  # noqa: BLE001
            runtime["status"] = "order_send_pilot_blocked_state_claim_failed"
            runtime["send_result_snapshot"] = redacted_send_result(None, "not_called", str(exc))
            runtime["state_status"] = "reconciliation_hold"
            return runtime
        runtime["future_state_json_written"] = True
        runtime["state_status"] = "pre_send_pending"
        pre_state["send_started_at_utc"] = utc_now_text()
        pre_state["state_status"] = "send_in_progress"
        try:
            atomic_write_json(Path(args.future_state_json), pre_state)
        except Exception as exc:  # noqa: BLE001
            runtime["status"] = "order_send_pilot_blocked_state_claim_failed"
            runtime["send_result_snapshot"] = redacted_send_result(None, "not_called", str(exc))
            runtime["state_status"] = "reconciliation_hold"
            return runtime
        runtime["order_send_call_count"] = 1
        try:
            result = mt5.order_send(send_parameters)
            category = result_category(mt5, result)
            error = ""
        except TimeoutError as exc:
            result = None
            category = "timeout"
            error = str(exc)
        except Exception as exc:  # noqa: BLE001
            result = None
            category = "exception"
            error = str(exc)
        runtime["order_execution_performed"] = category in {"success_deal", "success_placed", "partial_fill"}
        runtime["order_send_retcode"] = object_value(result, "retcode")
        runtime["order_send_result_category"] = category
        runtime["send_result_snapshot"] = redacted_send_result(result, category, error, send_parameters=send_parameters)
        post_state = state_after_result(pre_state, category, result)
        reconciliation = reconcile_post_send(mt5, inputs, category)
        runtime["positions_get_call_count"] += reconciliation["post_send_positions_get_call_count"]
        runtime["orders_get_call_count"] += reconciliation["post_send_orders_get_call_count"]
        runtime["post_send_reconciliation_performed"] = reconciliation["post_send_reconciliation_performed"]
        runtime["post_send_positions_get_called"] = reconciliation["post_send_positions_get_called"]
        runtime["post_send_positions_get_call_count"] = reconciliation["post_send_positions_get_call_count"]
        runtime["post_send_orders_get_called"] = reconciliation["post_send_orders_get_called"]
        runtime["post_send_orders_get_call_count"] = reconciliation["post_send_orders_get_call_count"]
        runtime["broker_position_detected_after_send"] = reconciliation["broker_position_detected_after_send"]
        runtime["broker_pending_order_detected_after_send"] = reconciliation["broker_pending_order_detected_after_send"]
        runtime["broker_position_count_after_send"] = reconciliation["broker_position_count_after_send"]
        runtime["broker_pending_order_count_after_send"] = reconciliation["broker_pending_order_count_after_send"]
        runtime["reconciliation_status"] = reconciliation["reconciliation_status"]
        runtime["reconciliation_snapshot"] = reconciliation["reconciliation_snapshot"]
        recovery_action = reconciliation.get("recommended_recovery_action", "")
        runtime["send_result_snapshot"]["recommended_recovery_action"] = recovery_action
        post_state["state_status"] = reconciliation["state_status"]
        post_state["reconciliation_status"] = reconciliation["reconciliation_status"]
        post_state["recommended_recovery_action"] = recovery_action
        post_state["post_send_reconciliation_performed"] = reconciliation["post_send_reconciliation_performed"]
        post_state["broker_position_detected_after_send"] = reconciliation["broker_position_detected_after_send"]
        post_state["broker_pending_order_detected_after_send"] = reconciliation["broker_pending_order_detected_after_send"]
        post_state["broker_position_count_after_send"] = reconciliation["broker_position_count_after_send"]
        post_state["broker_pending_order_count_after_send"] = reconciliation["broker_pending_order_count_after_send"]
        post_state["order_execution_performed"] = runtime["order_execution_performed"]
        post_state["retry_performed"] = False
        post_state["automatic_retry_allowed"] = False
        post_state["crash_recovery_required"] = reconciliation["reconciliation_status"] not in {
            "broker_local_reconciliation_matched_after_send",
            "broker_local_reconciliation_clean_after_client_reject_no_broker_state",
        }
        try:
            atomic_write_json(Path(args.future_state_json), post_state)
            runtime["future_state_json_written"] = True
            runtime["state_status"] = post_state["state_status"]
        except Exception as exc:  # noqa: BLE001
            runtime["state_status"] = "reconciliation_hold"
            runtime["send_result_snapshot"]["state_update_error"] = str(exc)
            category = "state_write_failure"
            runtime["order_send_result_category"] = category
        runtime["status"] = (
            "order_send_pilot_blocked_order_send_exception_reconciliation_hold"
            if category == "exception"
            else status_for_category(category)
        )
        return runtime
    finally:
        release_state_claim_lock(claim_lock_handle, claim_lock_path)
        shutdown = getattr(mt5, "shutdown", None)
        if runtime["mt5_connection_performed"] and callable(shutdown):
            shutdown()


def recommended_next_step(status: str) -> str:
    if status == "order_send_pilot_dry_run_no_send":
        return "review_dry_run_artifacts_before_any_explicit_pilot_override"
    if status in {
        "order_send_pilot_sent_success_deal_reconciliation_required",
        "order_send_pilot_sent_success_placed_reconciliation_required",
        "order_send_pilot_sent_rejected_no_retry",
        "order_send_pilot_sent_uncertain_reconciliation_hold",
        "order_send_pilot_blocked_order_send_exception_reconciliation_hold",
    }:
        return "perform_manual_bounded_broker_local_reconciliation_before_any_next_send"
    if status == "order_send_pilot_blocked_client_autotrading_disabled_no_send_confirmed":
        return "verify_broker_local_flat_read_only_then_finalize_state_as_send_rejected_no_position_no_order"
    return "resolve_blocking_condition_before_any_demo_send"


def bound_order_check_row(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    manifest = inputs["order_check_manifest"]
    return {
        "run_id": args.run_id,
        "order_check_run_id": manifest.get("run_id", ""),
        "order_check_status": manifest.get("order_check_status", ""),
        "order_check_passed": manifest.get("order_check_passed"),
        "order_check_call_count": manifest.get("order_check_call_count"),
        "order_check_manifest_digest": sha256_file(inputs["paths"]["order_check_manifest"]),
        "order_check_result_digest": sha256_file(inputs["paths"]["order_check_result"]),
        "binding_status": "bound" if order_check_valid(inputs) and binding_valid(inputs) and digest_binding_summary(inputs, required=True)["digest_binding_verified"] else "not_bound",
    }


def bound_intent_row(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    manifest = inputs["request_manifest"]
    intent = first_row(inputs["request_intent"])
    return {
        "run_id": args.run_id,
        "request_construction_run_id": manifest.get("run_id", ""),
        "request_construction_status": manifest.get("request_construction_status", ""),
        "signal_id": intent.get("signal_id", ""),
        "idempotency_key": intent.get("idempotency_key", ""),
        "approval_record_id": intent.get("approval_record_id", ""),
        "symbol": intent.get("symbol", ""),
        "side": intent.get("side", ""),
        "volume_lots": intent.get("volume_lots", ""),
        "sl_price": intent.get("sl_price", ""),
        "tp_price": intent.get("tp_price", ""),
        "request_intent_digest": sha256_file(inputs["paths"]["request_intent"]),
        "binding_status": "bound" if request_valid(args, inputs) and binding_valid(inputs) and digest_binding_summary(inputs, required=True)["digest_binding_verified"] else "not_bound",
    }


def confirmation_row(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    value = args.operator_final_send_confirmation or ""
    intent = first_row(inputs["request_intent"])
    return {
        "run_id": args.run_id,
        "confirmation_present": bool(value),
        "confirmation_label": value,
        "expected_confirmation_label": FINAL_CONFIRMATION,
        "confirmation_valid": value == FINAL_CONFIRMATION,
        "signal_id": intent.get("signal_id", ""),
        "idempotency_key": intent.get("idempotency_key", ""),
        "approval_record_id": intent.get("approval_record_id", ""),
        "request_intent_digest": sha256_file(inputs["paths"]["request_intent"]),
        "order_check_run_id": inputs["order_check_manifest"].get("run_id", ""),
        "order_check_digest": sha256_file(inputs["paths"]["order_check_manifest"]),
        "single_send_scope_only": True,
        "caveat": "confirmation_does_not_authorize_live_trading_or_multiple_sends",
    }


def no_order_evidence_row(args: argparse.Namespace, runtime: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "dry_run": dry_run,
        "mt5_import_performed": runtime["mt5_import_performed"],
        "mt5_connection_performed": runtime["mt5_connection_performed"],
        "broker_api_query_performed": runtime["broker_api_query_performed"],
        "positions_get_call_count": runtime["positions_get_call_count"],
        "orders_get_call_count": runtime["orders_get_call_count"],
        "order_send_called": runtime["order_send_call_count"] == 1,
        "order_send_call_count": runtime["order_send_call_count"],
        "order_execution_performed": runtime["order_execution_performed"],
        "future_state_json_written": runtime["future_state_json_written"],
        "no_order_execution_retry_performed": True,
        "no_second_order_send_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_trading_decision_performed": True,
        "no_live_account_allowed": True,
        "caveat": "single_shot_demo_pilot_default_no_send_and_never_live_account",
    }


def write_report(path: Path, args: argparse.Namespace, status: str, dry_run: bool, runtime: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    module_validation = bool(args.module_validation_demo_execution)
    lines = [
        "# Fixed-Candidate Demo Order-Send Pilot",
        "",
        "Single-shot gated demo pilot. Default behavior is dry-run/no-send.",
        "",
        "No live account is allowed. No automatic retry, second send, scheduler, polling loop, background task, database mutation, child script, trading decision, or executable broker payload artifact is permitted.",
        "",
        "A real demo send path requires explicit allow-real-order-send and the exact one-shot operator confirmation, plus non-fixture passed order-check and all safety gates.",
        "",
        "## Result",
        "",
        f"- order_send_pilot_status: `{status}`",
        f"- dry_run: `{dry_run}`",
        f"- order_send_call_count: `{runtime['order_send_call_count']}`",
        f"- result_category: `{runtime['order_send_result_category']}`",
        f"- module_validation_demo_execution: `{module_validation}`",
        f"- strategy_valid: `{not module_validation}`",
        f"- production_valid: `{not module_validation}`",
        f"- reconciliation_status: `{runtime['reconciliation_status']}`",
        f"- future_state_json_written: `{runtime['future_state_json_written']}`",
        f"- warnings_count: `{len(warnings)}`",
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
    status: str,
    dry_run: bool,
    inputs: dict[str, Any],
    runtime: dict[str, Any],
    output_files: dict[str, Path],
    warnings: list[dict[str, Any]],
    artifact_summary: dict[str, Any],
    digest_summary: dict[str, Any],
) -> None:
    intent = first_row(inputs["request_intent"])
    approval = inputs["approval"]
    module_validation_demo_execution = bool(
        args.module_validation_demo_execution
        or inputs["readiness_manifest"].get("module_validation_demo_execution") is True
        or inputs["request_manifest"].get("module_validation_demo_execution") is True
        or inputs["order_check_manifest"].get("module_validation_demo_execution") is True
    )
    stale_override_used = bool(
        inputs["readiness_manifest"].get("stale_override_used") is True
        or inputs["request_manifest"].get("stale_override_used") is True
    )
    expired_signal_override_used = bool(
        inputs["readiness_manifest"].get("expired_signal_override_used") is True
        or inputs["request_manifest"].get("expired_signal_override_used") is True
        or inputs["order_check_manifest"].get("expired_signal_override_used") is True
    )
    strategy_valid = not bool(module_validation_demo_execution or stale_override_used or expired_signal_override_used)
    send_allowed_for_demo_module_validation_only = bool(
        readiness_valid(inputs) and module_validation_send_allowed(args, inputs)
    )
    client_reject_resend_allowed = client_reject_flat_resend_allowed(args, inputs)
    market_contract = market_closed_flat_contract(args, inputs)
    explicit_market_closed_new_signal = bool(market_contract.get("accepted"))
    previous_state = inputs.get("future_state", {})
    content = {
        "run_id": args.run_id,
        "order_send_pilot_status": status,
        "dry_run": dry_run,
        "allow_real_order_send": bool(args.allow_real_order_send),
        "operator_final_send_confirmation_present": bool(args.operator_final_send_confirmation),
        "operator_final_send_confirmation_valid": args.operator_final_send_confirmation == FINAL_CONFIRMATION,
        "base_policy_order_execution_allowed": policy_boundaries(inputs["policy"]).get("order_execution_allowed"),
        "explicit_pilot_override_flags_present": bool(args.allow_real_order_send) and args.operator_final_send_confirmation == FINAL_CONFIRMATION,
        "candidate_id": CANDIDATE_ID,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "direction": DIRECTION,
        "signal_id": intent.get("signal_id") or approval.get("signal_id"),
        "idempotency_key": intent.get("idempotency_key") or approval.get("idempotency_key"),
        "approval_record_id": intent.get("approval_record_id") or approval.get("approval_record_id"),
        "approval_record_digest": approval.get("record_hash_or_digest", ""),
        "request_intent_digest": inputs["request_manifest"].get("request_intent_digest", ""),
        "request_fields_digest": inputs["request_manifest"].get("request_fields_digest", ""),
        "order_check_manifest_digest": inputs["order_check_manifest"].get("order_check_manifest_digest", ""),
        "order_check_result_digest": inputs["order_check_manifest"].get("order_check_result_digest", ""),
        "readiness_status": readiness_status(inputs),
        "request_construction_status": inputs["request_manifest"].get("request_construction_status", ""),
        "order_check_status": inputs["order_check_manifest"].get("order_check_status", ""),
        "order_check_called": inputs["order_check_manifest"].get("order_check_called"),
        "order_check_passed": inputs["order_check_manifest"].get("order_check_passed"),
        "order_check_retcode": inputs["order_check_manifest"].get("order_check_retcode"),
        "module_validation_demo_execution": module_validation_demo_execution,
        "stale_override_used": stale_override_used,
        "expired_signal_override_used": expired_signal_override_used,
        "strategy_valid": strategy_valid,
        "production_valid": strategy_valid,
        "send_allowed_for_demo_module_validation_only": send_allowed_for_demo_module_validation_only,
        "explicit_second_demo_send_after_client_reject_flat": client_reject_resend_allowed,
        "explicit_new_signal_after_market_closed_flat": explicit_market_closed_new_signal,
        "client_reject_resend_acknowledgment_valid": args.client_reject_resend_acknowledgment == CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        "previous_send_retcode": previous_state.get("last_retcode", ""),
        "previous_state_status": previous_state.get("state_status", ""),
        "previous_reconciliation_status": previous_state.get("reconciliation_status", ""),
        "new_signal_id_differs_from_previous_state": (
            not bool(market_contract.get("same_signal_id")) if explicit_market_closed_new_signal else False
        ),
        "new_idempotency_key_differs_from_previous_state": (
            not bool(market_contract.get("same_idempotency_key")) if explicit_market_closed_new_signal else False
        ),
        "previous_order_execution_performed": previous_state.get("order_execution_performed", ""),
        "previous_broker_order_ticket": previous_state.get("broker_order_ticket", ""),
        "previous_broker_deal_ticket": previous_state.get("broker_deal_ticket", ""),
        "previous_broker_position_ticket": previous_state.get("broker_position_ticket", ""),
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "new_operator_authorized_attempt": client_reject_resend_allowed,
        "digest_binding_required": digest_summary["digest_binding_required"],
        "digest_binding_verified": digest_summary["digest_binding_verified"],
        "digest_algorithm": digest_summary["digest_algorithm"],
        "digest_canonicalization": digest_summary["digest_canonicalization"],
        "missing_digest_count": digest_summary["missing_digest_count"],
        "digest_mismatch_count": digest_summary["digest_mismatch_count"],
        "digest_verification_status": digest_summary["digest_verification_status"],
        "order_check_run_id": inputs["order_check_manifest"].get("run_id"),
        "request_construction_run_id": inputs["request_manifest"].get("run_id"),
        "order_send_called": runtime["order_send_call_count"] == 1,
        "order_send_call_count": runtime["order_send_call_count"],
        "order_send_attempt_count": runtime["order_send_call_count"],
        "order_send_retcode": runtime["order_send_retcode"],
        "order_send_retcode_name": runtime["send_result_snapshot"].get("retcode_name", ""),
        "order_send_result_category": runtime["order_send_result_category"],
        "comment_length": runtime["send_result_snapshot"].get("comment_length", 0),
        "comment_redacted_preview": runtime["send_result_snapshot"].get("comment_redacted_preview", ""),
        "comment_broker_safe": runtime["send_result_snapshot"].get("comment_broker_safe", False),
        "order_execution_performed": runtime["order_execution_performed"],
        "post_send_reconciliation_performed": runtime["post_send_reconciliation_performed"],
        "post_send_positions_get_called": runtime["post_send_positions_get_called"],
        "post_send_positions_get_call_count": runtime["post_send_positions_get_call_count"],
        "post_send_orders_get_called": runtime["post_send_orders_get_called"],
        "post_send_orders_get_call_count": runtime["post_send_orders_get_call_count"],
        "broker_position_detected_after_send": runtime["broker_position_detected_after_send"],
        "broker_pending_order_detected_after_send": runtime["broker_pending_order_detected_after_send"],
        "broker_position_count_after_send": runtime["broker_position_count_after_send"],
        "broker_pending_order_count_after_send": runtime["broker_pending_order_count_after_send"],
        "reconciliation_status": runtime["reconciliation_status"],
        "future_state_json_written": runtime["future_state_json_written"],
        "state_status": runtime["state_status"],
        "broker_payload_written": False,
        "executable_order_object_written": False,
        "no_order_execution_retry_performed": True,
        "no_retry_performed": True,
        "no_second_order_send_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_trading_decision_performed": True,
        "no_live_account_allowed": True,
        "recommended_recovery_action": runtime["send_result_snapshot"].get("recommended_recovery_action", ""),
        "recommended_next_step": recommended_next_step(status),
        "output_files": {key: str(value) for key, value in output_files.items()},
        "created_at_utc": utc_now_text(),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for item in warnings if item["blocking_warning"] is True),
    }
    content.update(artifact_summary)
    write_json(path, content)


def initial_runtime() -> dict[str, Any]:
    return {
        "status": "",
        "mt5_import_performed": False,
        "mt5_connection_performed": False,
        "broker_api_query_performed": False,
        "positions_get_call_count": 0,
        "orders_get_call_count": 0,
        "order_send_call_count": 0,
        "order_send_retcode": None,
        "order_send_result_category": "not_called",
        "order_execution_performed": False,
        "future_state_json_written": False,
        "state_status": "",
        "broker_position_detected_after_send": False,
        "broker_pending_order_detected_after_send": False,
        "broker_position_count_after_send": 0,
        "broker_pending_order_count_after_send": 0,
        "post_send_reconciliation_performed": False,
        "post_send_positions_get_called": False,
        "post_send_positions_get_call_count": 0,
        "post_send_orders_get_called": False,
        "post_send_orders_get_call_count": 0,
        "reconciliation_status": "not_started",
        "broker_snapshot": redacted_broker_snapshot(imported=False, connected=False),
        "send_result_snapshot": redacted_send_result(None, "not_called"),
        "reconciliation_snapshot": {"reconciliation_status": "not_started", "bounded_reads_only": True},
    }


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for(args)
    outputs = output_paths(output_dir)
    ensure_outputs_writable(outputs, bool(args.overwrite))
    inputs = load_inputs(args)
    gates = structural_gates(args, inputs)
    dry_run = effective_dry_run(args)
    freshness_blocking = (not dry_run) and bool(args.allow_real_order_send)
    freshness_rows = artifact_freshness_checks(args, inputs, freshness_blocking)
    freshness_summary = artifact_freshness_summary(
        freshness_rows,
        {
            "default_upstream_artifact_minutes": float(args.max_artifact_age_minutes),
            "order_check_artifact_minutes": float(args.max_order_check_artifact_age_minutes),
        },
    )
    runtime = initial_runtime()
    status = first_failed_status(gates)
    if not status and not dry_run and not args.allow_real_order_send:
        status = "order_send_pilot_blocked_real_send_not_allowed"
    if not status and not dry_run and args.operator_final_send_confirmation != FINAL_CONFIRMATION:
        status = "order_send_pilot_blocked_missing_final_confirmation"
    if not status and freshness_summary["blocking_stale_artifact_count"]:
        status = "order_send_pilot_blocked_stale_upstream_artifact"
    digest_required = (not status) and (not dry_run) and bool(args.allow_real_order_send)
    digest_summary = digest_binding_summary(inputs, required=digest_required)
    if digest_required:
        digest_gate = digest_gate_row(args, inputs, digest_summary)
        gates.append(digest_gate)
        if digest_gate["gate_status"] == "failed":
            status = str(digest_gate["warning_code"])
    if not status and dry_run:
        status = "order_send_pilot_dry_run_no_send"
    if not status:
        runtime = run_real_send(args, inputs)
        status = runtime["status"]
    warnings = [
        warning_row(args, "single_shot_no_retry", "This pilot never retries or sends a second order.", "send_fixed_candidate_demo_order_pilot", False),
        warning_row(args, "live_account_forbidden", "Live/real-money accounts are forbidden.", "send_fixed_candidate_demo_order_pilot", False),
    ]
    for gate in gates:
        if gate["gate_status"] == "failed":
            warnings.append(warning_row(args, str(gate["warning_code"]), f"Gate failed: {gate['gate_name']}", gate["source_path"], True))
    add_artifact_freshness_warnings(args, warnings, freshness_rows)
    if status.startswith("order_send_pilot_blocked") and status not in {item["warning_code"] for item in warnings}:
        warnings.append(warning_row(args, status, f"Pilot blocked: {status}", "send_fixed_candidate_demo_order_pilot", True))
    runtime["status"] = status
    state_preview = state_claim_preview(args, inputs, not dry_run and not status.startswith("order_send_pilot_blocked"))
    write_csv(outputs["gate_checks"], gates, GATE_FIELDNAMES)
    write_csv(outputs["bound_order_check"], [bound_order_check_row(args, inputs)], BOUND_ORDER_CHECK_FIELDNAMES)
    write_csv(outputs["bound_request_intent"], [bound_intent_row(args, inputs)], BOUND_INTENT_FIELDNAMES)
    write_csv(outputs["operator_confirmation"], [confirmation_row(args, inputs)], CONFIRMATION_FIELDNAMES)
    write_json(outputs["state_claim_preview"], state_preview)
    write_csv(outputs["send_payload_preview"], payload_preview_rows(args, inputs), PAYLOAD_PREVIEW_FIELDNAMES)
    write_csv(outputs["artifact_freshness"], freshness_rows, ARTIFACT_FRESHNESS_FIELDNAMES)
    write_json(outputs["broker_snapshot"], runtime["broker_snapshot"])
    write_json(outputs["send_result_snapshot"], runtime["send_result_snapshot"])
    write_json(outputs["reconciliation_snapshot"], runtime["reconciliation_snapshot"])
    write_csv(
        outputs["status"],
        [
            {
                "run_id": args.run_id,
                "order_send_pilot_status": status,
                "dry_run": dry_run,
                "allow_real_order_send": bool(args.allow_real_order_send),
                "order_send_called": runtime["order_send_call_count"] == 1,
                "order_send_call_count": runtime["order_send_call_count"],
                "order_send_retcode": runtime["order_send_retcode"],
                "order_send_result_category": runtime["order_send_result_category"],
                "reconciliation_status": runtime["reconciliation_status"],
                "state_status": runtime["state_status"],
                "recommended_next_step": recommended_next_step(status),
            }
        ],
        STATUS_FIELDNAMES,
    )
    write_csv(outputs["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(outputs["no_order_evidence"], [no_order_evidence_row(args, runtime, dry_run)], NO_ORDER_FIELDNAMES)
    write_report(outputs["report"], args, status, dry_run, runtime, warnings)
    write_manifest(outputs["manifest"], args, status, dry_run, inputs, runtime, outputs, warnings, freshness_summary, digest_summary)
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a gated single-shot fixed-candidate demo order-send pilot with dry-run/no-send default.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--order-send-pilot-readiness-plan-dir", type=Path, default=DEFAULT_READINESS_DIR)
    parser.add_argument("--order-check-dir", type=Path, default=DEFAULT_ORDER_CHECK_DIR)
    parser.add_argument("--request-construction-dry-run-dir", type=Path, default=DEFAULT_REQUEST_DIR)
    parser.add_argument("--manual-approval-record-json", type=Path, default=DEFAULT_APPROVAL_JSON)
    parser.add_argument("--broker-local-reconciliation-dir", type=Path, default=DEFAULT_RECONCILIATION_DIR)
    parser.add_argument("--broker-safe-margin-validation-dir", type=Path, default=DEFAULT_MARGIN_DIR)
    parser.add_argument("--live-signal-freshness-dir", type=Path, default=DEFAULT_FRESHNESS_DIR)
    parser.add_argument("--duplicate-protection-plan-dir", type=Path, default=DEFAULT_DUPLICATE_DIR)
    parser.add_argument("--manual-approval-kill-switch-plan-dir", type=Path, default=DEFAULT_MANUAL_PLAN_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--future-state-json", type=Path, default=DEFAULT_FUTURE_STATE)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-artifact-age-minutes", type=float, default=DEFAULT_MAX_ARTIFACT_AGE_MINUTES)
    parser.add_argument(
        "--max-order-check-artifact-age-minutes",
        type=float,
        default=DEFAULT_MAX_ORDER_CHECK_ARTIFACT_AGE_MINUTES,
    )
    parser.add_argument("--dry-run", action="store_true", default=None)
    parser.add_argument("--allow-real-order-send", action="store_true")
    parser.add_argument("--operator-final-send-confirmation")
    parser.add_argument("--max-order-send-attempts", type=int, default=1)
    parser.add_argument("--module-validation-demo-execution", action="store_true")
    parser.add_argument("--allow-stale-upstream-artifacts-for-demo-module-validation", action="store_true")
    parser.add_argument("--module-validation-acknowledgment", default="")
    parser.add_argument("--allow-expired-signal-for-demo-module-validation", action="store_true")
    parser.add_argument("--expired-signal-override-acknowledgment", default="")
    parser.add_argument("--allow-new-demo-send-after-client-reject-flat", action="store_true")
    parser.add_argument("--client-reject-resend-acknowledgment", default="")
    parser.add_argument("--mt5-package", default="MetaTrader5")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError, csv.Error) as exc:
        print(f"Fixed-candidate demo order-send pilot failed: {exc}")
        return 1
    print("Fixed-candidate demo order-send pilot complete.")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
