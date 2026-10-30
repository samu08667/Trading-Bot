"""Build a non-executable request-construction dry-run packet.

This module reads an approved fixed-candidate manual approval record and the
required upstream safety artifacts, then writes a dry-run request intent and
field descriptor packet. It does not import/connect to MT5, query broker/API
state, construct an executable broker payload or order object, call order check
or send paths, execute orders, mutate databases, write future trading state, or
run child scripts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
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

    from scripts.fixed_candidate_demo_state_contracts import (
        CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        evaluate_explicit_second_demo_send_after_client_reject_flat,
        evaluate_market_closed_reject_flat_new_signal,
        future_state_is_incompatible_without_explicit_client_reject_contract,
        state_status,
    )
except ModuleNotFoundError:
    from _fixed_candidate_artifact_freshness import (
        ARTIFACT_FRESHNESS_FIELDNAMES,
        DEFAULT_MAX_ARTIFACT_AGE_MINUTES,
        artifact_freshness_summary,
        evaluate_artifact_freshness,
        status_is_stale,
    )

    from fixed_candidate_demo_state_contracts import (
        CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        evaluate_explicit_second_demo_send_after_client_reject_flat,
        evaluate_market_closed_reject_flat_new_signal,
        future_state_is_incompatible_without_explicit_client_reject_contract,
        state_status,
    )


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
REQUEST_CONSTRUCTION_AVAILABLE_STATUSES = {
    REQUEST_CONSTRUCTION_AVAILABLE_STATUS,
    REQUEST_CONSTRUCTION_STALE_OVERRIDE_STATUS,
}
MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT = (
    "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only"
)
EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT = "acknowledge_expired_signal_for_demo_module_validation_only"
ATOMIC_ARTIFACT_WRITES_ENABLED = True
ATOMIC_WRITE_STRATEGY = "temp_file_same_directory_os_replace"

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_request_construction_dry_run"
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
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR / "state" / "fixed_candidate_demo_state" / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_request_construction_dry_run"

BOUND_UPSTREAM_PATH_KEYS = {
    "future_request_readiness_plan_manifest": "future_request",
    "broker_local_reconciliation_manifest": "reconciliation",
    "broker_safe_margin_validation_manifest": "margin",
    "broker_safe_margin_validation_margin_snapshot": "margin_snapshot",
    "live_signal_freshness_manifest": "freshness",
    "duplicate_protection_plan_manifest": "duplicate",
    "manual_approval_kill_switch_plan_manifest": "manual_plan",
}

SCHEMA_MANIFEST = "fixed_candidate_demo_manual_approval_record_schema_manifest.json"
SCHEMA_ALLOWED_STATUSES = "fixed_candidate_demo_manual_approval_record_schema_allowed_statuses.csv"
SCHEMA_OPERATOR_DECISIONS = "fixed_candidate_demo_manual_approval_record_schema_operator_decision_labels.csv"
SCHEMA_POST_APPROVAL_RECHECKS = "fixed_candidate_demo_manual_approval_record_schema_post_approval_pre_request_rechecks.csv"
SCHEMA_DIGEST_RULES = "fixed_candidate_demo_manual_approval_record_schema_digest_rules.csv"
FUTURE_REQUEST_MANIFEST = "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json"
BROKER_RECON_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
MARGIN_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"
FRESHNESS_MANIFEST = "fixed_candidate_demo_live_signal_freshness_manifest.json"
DUPLICATE_MANIFEST = "fixed_candidate_demo_duplicate_protection_plan_manifest.json"
MANUAL_PLAN_MANIFEST = "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_request_construction_dry_run_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_request_construction_dry_run_report.md"
OUTPUT_INTENT = "fixed_candidate_demo_request_construction_dry_run_request_intent.csv"
OUTPUT_FIELDS = "fixed_candidate_demo_request_construction_dry_run_request_fields.csv"
OUTPUT_GATE_CHECKS = "fixed_candidate_demo_request_construction_dry_run_gate_checks.csv"
OUTPUT_BOUND_APPROVAL = "fixed_candidate_demo_request_construction_dry_run_bound_approval_record.csv"
OUTPUT_BOUND_UPSTREAM = "fixed_candidate_demo_request_construction_dry_run_bound_upstream_artifacts.csv"
OUTPUT_IDEMPOTENCY = "fixed_candidate_demo_request_construction_dry_run_idempotency.csv"
OUTPUT_BLOCKS = "fixed_candidate_demo_request_construction_dry_run_block_conditions.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_request_construction_dry_run_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_request_construction_dry_run_no_order_evidence.csv"
OUTPUT_ARTIFACT_FRESHNESS = "fixed_candidate_demo_request_construction_dry_run_artifact_freshness_checks.csv"

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
INTENT_FIELDNAMES = [
    "run_id",
    "candidate_id",
    "symbol",
    "timeframe",
    "direction",
    "side",
    "order_type_intent",
    "volume_lots",
    "entry_reference_price",
    "sl_price",
    "tp_price",
    "risk_amount",
    "risk_percent",
    "broker_margin_estimate",
    "broker_margin_usage_ratio",
    "spread_current_points",
    "signal_time_server",
    "signal_id",
    "idempotency_key",
    "approval_record_id",
    "approval_record_digest",
    "approval_scope",
    "request_construction_mode",
    "broker_payload_constructed",
    "executable_order_object_constructed",
    "order_check_allowed_now",
    "order_send_allowed_now",
    "order_execution_allowed",
]
FIELD_DESCRIPTOR_FIELDNAMES = [
    "run_id",
    "field_name",
    "intended_value",
    "source",
    "required_for_future_order_check",
    "broker_payload_field_now",
    "executable_now",
    "safety_note",
]
BOUND_APPROVAL_FIELDNAMES = [
    "run_id",
    "approval_record_path",
    "approval_record_id",
    "approval_record_digest",
    "approval_status",
    "approval_scope",
    "approval_expiry_time_utc",
    "binding_status",
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
IDEMPOTENCY_FIELDNAMES = [
    "run_id",
    "signal_id",
    "idempotency_key",
    "approval_record_id",
    "idempotency_status",
    "caveat",
]
BLOCK_FIELDNAMES = ["run_id", "block_condition", "condition_status", "observed_value", "expected_value", "blocking_if_failed", "caveat"]
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


def bool_text(value: bool) -> str:
    return "true" if value else "false"


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
    candidates = [text, text.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip()
    return len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text)


def digest_algorithm_ok(value: Any) -> bool:
    return str(value or "").replace("-", "").lower() == DIGEST_ALGORITHM


def signal_identity_source_text(record: dict[str, Any]) -> str:
    required = (
        "candidate_id",
        "symbol",
        "timeframe",
        "direction",
        "signal_time_server",
        "entry_reference_price",
        "sl_price",
        "tp_price",
    )
    values = [record.get(key) for key in required]
    if any(value in (None, "") for value in values):
        return ""
    return "".join(str(value) for value in values)


def deterministic_signal_id(record: dict[str, Any]) -> str:
    text = signal_identity_source_text(record)
    return sha256_text(text) if text else ""


def validate_signal_idempotency(record: dict[str, Any]) -> bool:
    signal_id = str(record.get("signal_id") or "")
    idempotency_key = str(record.get("idempotency_key") or "")
    if not signal_id or not idempotency_key or signal_id != idempotency_key:
        return False
    expected_signal_id = deterministic_signal_id(record)
    return not expected_signal_id or signal_id == expected_signal_id


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


def atomic_write_text(path: Path, content: str, *, newline: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline=newline,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = ""
    finally:
        if temporary_path:
            try:
                Path(temporary_path).unlink()
            except OSError:
                pass


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = ""
    finally:
        if temporary_path:
            try:
                Path(temporary_path).unlink()
            except OSError:
                pass


def snapshot_path(path: Path) -> tuple[bool, bytes]:
    if not path.exists():
        return False, b""
    return True, path.read_bytes()


def restore_path(path: Path, snapshot: tuple[bool, bytes]) -> None:
    existed, content = snapshot
    try:
        if existed:
            atomic_write_bytes(path, content)
        elif path.exists():
            path.unlink()
    except OSError:
        pass


def write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            newline="",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = handle.name
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = ""
    finally:
        if temporary_path:
            try:
                Path(temporary_path).unlink()
            except OSError:
                pass


def output_dir_for(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "intent": output_dir / OUTPUT_INTENT,
        "fields": output_dir / OUTPUT_FIELDS,
        "gate_checks": output_dir / OUTPUT_GATE_CHECKS,
        "bound_approval": output_dir / OUTPUT_BOUND_APPROVAL,
        "bound_upstream": output_dir / OUTPUT_BOUND_UPSTREAM,
        "idempotency": output_dir / OUTPUT_IDEMPOTENCY,
        "blocks": output_dir / OUTPUT_BLOCKS,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
        "artifact_freshness": output_dir / OUTPUT_ARTIFACT_FRESHNESS,
    }


def ensure_outputs_writable(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)


def schema_paths(args: argparse.Namespace) -> dict[str, Path]:
    base = Path(args.manual_approval_record_schema_dir)
    return {
        "schema_manifest": base / SCHEMA_MANIFEST,
        "allowed_statuses": base / SCHEMA_ALLOWED_STATUSES,
        "operator_decisions": base / SCHEMA_OPERATOR_DECISIONS,
        "post_approval_rechecks": base / SCHEMA_POST_APPROVAL_RECHECKS,
        "digest_rules": base / SCHEMA_DIGEST_RULES,
    }


def source_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths = schema_paths(args)
    paths.update(
        {
            "approval_record": Path(args.manual_approval_record_json),
            "registry": Path(args.canonical_registry),
            "policy": Path(args.demo_execution_policy),
            "future_request": Path(args.future_request_readiness_plan_dir) / FUTURE_REQUEST_MANIFEST,
            "reconciliation": Path(args.broker_local_reconciliation_dir) / BROKER_RECON_MANIFEST,
            "margin": Path(args.broker_safe_margin_validation_dir) / MARGIN_MANIFEST,
            "margin_snapshot": Path(args.broker_safe_margin_validation_dir) / MARGIN_SNAPSHOT,
            "freshness": Path(args.live_signal_freshness_dir) / FRESHNESS_MANIFEST,
            "duplicate": Path(args.duplicate_protection_plan_dir) / DUPLICATE_MANIFEST,
            "manual_plan": Path(args.manual_approval_kill_switch_plan_dir) / MANUAL_PLAN_MANIFEST,
            "future_state": Path(args.future_state_json),
        }
    )
    return paths


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


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    paths = source_paths(args)
    inputs: dict[str, Any] = {"paths": paths}
    json_keys = (
        "registry",
        "policy",
        "schema_manifest",
        "future_request",
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
        if error:
            add_warning(
                warnings,
                args=args,
                warning_code=f"{key}_missing_or_unreadable",
                message=error,
                source=paths[key],
                blocking_warning=True,
            )
    approval_record, approval_error = read_json(paths["approval_record"])
    inputs["approval_record"] = approval_record
    inputs["approval_error"] = approval_error
    if approval_error and not (approval_error == "missing" and args.allow_missing_approval_record_for_fixture_only):
        add_warning(
            warnings,
            args=args,
            warning_code="approval_record_missing_or_unreadable",
            message=approval_error,
            source=paths["approval_record"],
            blocking_warning=True,
        )
    for key in ("allowed_statuses", "operator_decisions", "post_approval_rechecks", "digest_rules"):
        rows, error = read_csv_rows(paths[key])
        inputs[key] = rows
        if error:
            add_warning(
                warnings,
                args=args,
                warning_code=f"{key}_missing_or_unreadable",
                message=error,
                source=paths[key],
                blocking_warning=True,
            )
    future_state, future_state_error = read_json(paths["future_state"])
    inputs["future_state"] = future_state
    inputs["future_state_exists"] = paths["future_state"].exists()
    inputs["future_state_error"] = "" if future_state_error == "missing" else future_state_error
    return inputs


def validate_canonical_registry(registry: dict[str, Any]) -> bool:
    registry_max_open = safe_int(registry.get("max_open_positions"))
    return (
        registry.get("candidate_id") == CANDIDATE_ID
        and registry.get("symbol") == SYMBOL
        and registry.get("timeframe") == TIMEFRAME
        and registry.get("direction") == DIRECTION
        and registry.get("spread_unit") == "broker_points"
        and safe_float(registry.get("max_spread_points")) == MAX_SPREAD_POINTS
        and registry_max_open in (None, MAX_OPEN_POSITIONS)
        and registry.get("horizon_bars") in (None, HORIZON_BARS)
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
        and policy.get("spread_unit") in (None, "broker_points")
        and safe_float(policy.get("max_spread_points")) in (None, MAX_SPREAD_POINTS)
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


def validate_digest_rules(rows: list[dict[str, str]]) -> bool:
    values = {row.get("rule_name"): row.get("rule_value") for row in rows}
    return values.get("approval_record_digest_algorithm") in (None, "SHA-256") or values.get("upstream_artifact_digest_algorithm") == "SHA-256"


def approval_record_expired(record: dict[str, Any]) -> bool:
    expiry = parse_time(record.get("approval_expiry_time_utc"))
    return expiry is None or expiry <= utc_now()


def expired_signal_override_requested(args: argparse.Namespace) -> bool:
    return bool(args.allow_expired_signal_for_demo_module_validation or args.expired_signal_override_acknowledgment)


def expired_signal_override_allowed(args: argparse.Namespace) -> bool:
    return (
        args.module_validation_demo_execution is True
        and args.allow_expired_signal_for_demo_module_validation is True
        and args.expired_signal_override_acknowledgment == EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT
    )


def validate_approval_record(record: dict[str, Any], args: argparse.Namespace) -> tuple[bool, str]:
    if record.get("approval_status") != "approved_for_future_request_construction_only":
        return False, "request_construction_dry_run_blocked_unapproved_record"
    if record.get("approval_scope") != "future_request_construction_only":
        return False, "request_construction_dry_run_blocked_unapproved_record"
    checks = (
        record.get("approval_does_not_execute_order") is True,
        record.get("approval_does_not_construct_request") is True,
        record.get("approval_requires_final_pre_request_recheck") is True,
        record.get("approval_revoked") is False,
        bool(record.get("record_hash_or_digest")),
        record.get("candidate_id") == CANDIDATE_ID,
        record.get("symbol") == SYMBOL,
        record.get("timeframe") == TIMEFRAME,
        record.get("direction") == DIRECTION,
        bool(record.get("signal_id")),
        bool(record.get("idempotency_key")),
        validate_signal_idempotency(record),
        record.get("operator_decision_label") == "approve_for_future_request_construction_only",
    )
    if not all(checks):
        return False, "request_construction_dry_run_blocked_unapproved_record"
    if approval_record_expired(record) and not expired_signal_override_allowed(args):
        return False, "request_construction_dry_run_blocked_expired_approval"
    return True, ""


def bound_artifact_current_path(name: str, item: dict[str, Any], paths: dict[str, Path]) -> Path | None:
    path_key = BOUND_UPSTREAM_PATH_KEYS.get(name)
    if path_key:
        return paths.get(path_key)
    item_path = item.get("path")
    return Path(str(item_path)) if item_path else None


def approval_digest_binding_summary(record: dict[str, Any], *, required: bool, paths: dict[str, Path]) -> dict[str, Any]:
    missing_count = 0
    mismatch_count = 0
    if required:
        if record.get("digest_binding_verified") is not True:
            mismatch_count += 1
        if safe_int(record.get("missing_digest_count")) != 0:
            missing_count += 1
        if safe_int(record.get("digest_mismatch_count")) != 0:
            mismatch_count += 1
        if not is_sha256_hex(record.get("record_hash_or_digest")):
            missing_count += 1
        if not digest_algorithm_ok(record.get("digest_algorithm")):
            missing_count += 1
        canonical_rule = record.get("canonical_serialization_rule") or record.get("digest_canonicalization")
        if not canonical_rule:
            missing_count += 1
        bound = record.get("bound_upstream_artifact_digests")
        if not isinstance(bound, dict) or not bound:
            missing_count += 1
        else:
            for name, item in bound.items():
                if not isinstance(item, dict):
                    missing_count += 1
                    continue
                expected_digest = item.get("sha256_digest")
                if not is_sha256_hex(expected_digest):
                    missing_count += 1
                    continue
                current_path = bound_artifact_current_path(str(name), item, paths)
                if current_path is None or not current_path.exists():
                    missing_count += 1
                    continue
                actual_digest = sha256_file(current_path)
                if actual_digest.lower() != str(expected_digest).lower():
                    mismatch_count += 1
    verified = required and missing_count == 0 and mismatch_count == 0
    if not required:
        status = "digest_binding_not_required_fixture_only"
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


def validate_freshness(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("freshness_status")
        in {"live_signal_freshness_fresh_current_or_latest_signal", "live_signal_freshness_fresh_within_horizon"}
        and manifest.get("is_fresh") is True
        and manifest.get("is_stale") is False
        and (safe_int(manifest.get("bars_elapsed")) is None or safe_int(manifest.get("bars_elapsed")) <= HORIZON_BARS)
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
    snapshot_ratio = safe_float(snapshot.get("broker_margin_usage_ratio"))
    manifest_volume = safe_float(manifest.get("stepped_volume_lots"))
    snapshot_volume = safe_float(snapshot.get("margin_calc_volume_lots"))
    volume_matches = (
        manifest_volume is not None
        and manifest_volume > 0
        and snapshot_volume is not None
        and snapshot_volume > 0
        and abs(manifest_volume - snapshot_volume) <= VOLUME_TOLERANCE
    )
    return (
        manifest_status in ACCEPTABLE_MARGIN_VALIDATION_STATUSES
        and manifest.get("source_nature") == "live_data_shadow_signal"
        and manifest.get("account_mode_label") == "demo"
        and manifest.get("account_currency") == "EUR"
        and manifest.get("account_equity_policy_status") == "within_10pct"
        and ratio is not None
        and ratio <= HARD_MARGIN_CAP_RATIO
        and manifest.get("spread_within_policy") is True
        and volume_matches
        and (snapshot_status in ("", None) or snapshot_status in ACCEPTABLE_MARGIN_VALIDATION_STATUSES)
        and (snapshot_ratio is None or snapshot_ratio <= HARD_MARGIN_CAP_RATIO)
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
        and manifest.get("manual_approval_performed") in (False, None)
        and manifest.get("kill_switch_executed") is False
        and manifest.get("plan_actionable") is False
    )


def validate_future_request(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("plan_status") == "future_request_construction_readiness_plan_available_no_order"
        and manifest.get("request_construction_allowed_now") is False
        and manifest.get("broker_request_constructed", False) is False
        and manifest.get("broker_payload_constructed", False) is False
        and manifest.get("order_object_constructed", False) is False
    )


def client_reject_flat_contract(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    record = inputs["approval_record"]
    return evaluate_explicit_second_demo_send_after_client_reject_flat(
        state=inputs.get("future_state") or {},
        signal_id=record.get("signal_id", ""),
        idempotency_key=record.get("idempotency_key", ""),
        module_validation_demo_execution=bool(args.module_validation_demo_execution),
        demo_account_only=True,
        allow_flag=bool(args.allow_new_demo_send_after_client_reject_flat),
        acknowledgment=args.client_reject_resend_acknowledgment,
        broker_local_reconciliation=inputs.get("reconciliation") or {},
        require_broker_local_reconciliation=True,
    )


def market_closed_flat_contract(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    record = inputs["approval_record"]
    return evaluate_market_closed_reject_flat_new_signal(
        state=inputs.get("future_state") or {},
        signal_id=record.get("signal_id", ""),
        idempotency_key=record.get("idempotency_key", ""),
        broker_local_reconciliation=inputs.get("reconciliation") or {},
        require_broker_local_reconciliation=True,
    )


def future_state_incompatible(args: argparse.Namespace, inputs: dict[str, Any]) -> tuple[bool, str, dict[str, Any], dict[str, Any]]:
    path = inputs["paths"]["future_state"]
    if not path.exists():
        return False, "missing_allowed_when_reconciliation_clean", {}, {}
    state = inputs.get("future_state") or {}
    error = inputs.get("future_state_error", "")
    if error:
        return True, error, {}, {}
    contract = client_reject_flat_contract(args, inputs)
    if contract["accepted"]:
        return False, "explicit_second_demo_send_after_client_reject_flat", contract, {}
    market_contract = market_closed_flat_contract(args, inputs)
    if market_contract["accepted"]:
        return False, "explicit_new_signal_after_market_closed_flat", contract, market_contract
    incompatible, same_key = future_state_is_incompatible_without_explicit_client_reject_contract(
        state,
        signal_id=inputs["approval_record"].get("signal_id", ""),
        idempotency_key=inputs["approval_record"].get("idempotency_key", ""),
    )
    if incompatible:
        reason = "same_idempotency_key" if same_key else state_status(state) or "future_state_incompatible"
        if contract.get("candidate"):
            reason = "client_reject_flat_requires_demo_module_validation_acknowledgment"
        elif market_contract.get("candidate"):
            reason = "market_closed_reject_flat_requires_new_signal_and_clean_reconciliation"
        return True, reason, contract, market_contract
    return False, state_status(state) or "compatible", contract, market_contract


def gate_row(args: argparse.Namespace, name: str, ok: bool, observed: Any, expected: Any, source: Path, code: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "gate_name": name,
        "gate_status": "passed" if ok else "failed",
        "observed_value": observed,
        "expected_value": expected,
        "source_path": str(source),
        "blocking_if_failed": bool_text(True),
        "warning_code": "" if ok else code,
    }


def status_from_gates(gates: list[dict[str, Any]], inputs: dict[str, Any], args: argparse.Namespace) -> str:
    if inputs["approval_error"] == "missing" and args.allow_missing_approval_record_for_fixture_only:
        return "request_construction_dry_run_fixture_only_no_approval_record"
    for row in gates:
        if row["gate_status"] == "failed":
            return str(row["warning_code"])
    return REQUEST_CONSTRUCTION_AVAILABLE_STATUS


def add_boundary_warnings(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> None:
    for code, message in (
        ("request_intent_is_non_executable", "Request intent is non-executable and not a broker payload."),
        ("approval_does_not_authorize_execution", "Approval record does not authorize order execution."),
        ("order_check_not_called", "Order check was not called."),
        ("order_send_not_called", "Order send was not called."),
        ("final_pre_request_rechecks_required_future", "Final pre-request rechecks remain required in a later module."),
    ):
        add_warning(warnings, args=args, warning_code=code, message=message, source="request_construction_dry_run", blocking_warning=False)


def non_fixture_request_progression(args: argparse.Namespace, inputs: dict[str, Any]) -> bool:
    return not (args.allow_missing_approval_record_for_fixture_only and inputs["approval_error"] == "missing")


def module_validation_override_requested(args: argparse.Namespace) -> bool:
    return bool(
        args.allow_stale_upstream_artifacts_for_demo_module_validation
        or args.module_validation_acknowledgment
    )


def module_validation_stale_override_allowed(args: argparse.Namespace) -> bool:
    return (
        args.module_validation_demo_execution is True
        and args.allow_stale_upstream_artifacts_for_demo_module_validation is True
        and args.module_validation_acknowledgment == MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT
    )


def module_validation_override_observed(args: argparse.Namespace) -> str:
    return (
        f"demo_execution={args.module_validation_demo_execution};"
        f"allow_stale={args.allow_stale_upstream_artifacts_for_demo_module_validation};"
        f"stale_ack={args.module_validation_acknowledgment or ''};"
        f"allow_expired={args.allow_expired_signal_for_demo_module_validation};"
        f"expired_ack={args.expired_signal_override_acknowledgment or ''}"
    )


def status_allows_request_intent(status: str) -> bool:
    return status in REQUEST_CONSTRUCTION_AVAILABLE_STATUSES


def artifact_freshness_checks(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    paths = inputs["paths"]
    blocking = non_fixture_request_progression(args, inputs) and not module_validation_stale_override_allowed(args)
    max_age = float(args.max_artifact_age_minutes)
    specs = [
        {
            "artifact_name": "manual_approval_record",
            "path": paths["approval_record"],
            "payload": inputs["approval_record"],
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
            warning_code=(
                "request_construction_dry_run_blocked_stale_upstream_artifact"
                if blocking
                else "stale_upstream_artifact_warning"
            ),
            message=f"Artifact freshness check failed for {row['artifact_name']}: {row['status']}.",
            source=row["path"],
            blocking_warning=blocking,
        )


def evaluate(args: argparse.Namespace, inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    paths = inputs["paths"]
    record = inputs["approval_record"]
    freshness_rows = artifact_freshness_checks(args, inputs)
    freshness_summary = artifact_freshness_summary(
        freshness_rows,
        float(args.max_artifact_age_minutes),
    )
    approval_present = not inputs["approval_error"]
    approval_ok, approval_status = (False, "request_construction_dry_run_blocked_missing_approval_record")
    if approval_present:
        approval_ok, approval_status = validate_approval_record(record, args)
    elif args.allow_missing_approval_record_for_fixture_only and inputs["approval_error"] == "missing":
        approval_ok, approval_status = False, "fixture_only"
    digest_required = approval_present and not (
        args.allow_missing_approval_record_for_fixture_only and inputs["approval_error"] == "missing"
    )
    digest_summary = approval_digest_binding_summary(record, required=digest_required, paths=paths)

    future_state_bad, future_state_note, client_reject_contract, market_closed_contract = future_state_incompatible(args, inputs)
    gates = [
        gate_row(args, "canonical_registry", validate_canonical_registry(inputs["registry"]), inputs["registry"].get("candidate_id"), CANDIDATE_ID, paths["registry"], "request_construction_dry_run_blocked_noncanonical_candidate"),
        gate_row(args, "demo_execution_policy", validate_demo_policy(inputs["policy"]), "policy_boundaries", "no request/no execution/no real money", paths["policy"], "request_construction_dry_run_blocked_noncanonical_demo_execution_policy"),
        gate_row(args, "approval_record_schema", validate_schema(inputs["schema_manifest"]), inputs["schema_manifest"].get("schema_status"), "manual_approval_record_schema_available_no_order", paths["schema_manifest"], "request_construction_dry_run_blocked_unsafe_policy"),
        gate_row(args, "allowed_statuses", bool(inputs["allowed_statuses"]), len(inputs["allowed_statuses"]), "present", paths["allowed_statuses"], "request_construction_dry_run_blocked_unsafe_policy"),
        gate_row(args, "operator_decision_labels", bool(inputs["operator_decisions"]), len(inputs["operator_decisions"]), "present", paths["operator_decisions"], "request_construction_dry_run_blocked_unsafe_policy"),
        gate_row(args, "post_approval_rechecks", validate_post_approval_rows(inputs["post_approval_rechecks"]), len(inputs["post_approval_rechecks"]), "all required/blocking", paths["post_approval_rechecks"], "request_construction_dry_run_blocked_unsafe_policy"),
        gate_row(args, "digest_rules", validate_digest_rules(inputs["digest_rules"]), len(inputs["digest_rules"]), "SHA-256 digest rules", paths["digest_rules"], "request_construction_dry_run_blocked_unsafe_policy"),
        gate_row(args, "approval_record", approval_ok or bool(args.allow_missing_approval_record_for_fixture_only and inputs["approval_error"] == "missing"), record.get("approval_status", inputs["approval_error"]), "approved non-revoked non-expired record", paths["approval_record"], approval_status),
        gate_row(
            args,
            "digest_binding",
            (not digest_summary["digest_binding_required"]) or bool(digest_summary["digest_binding_verified"]),
            f"missing={digest_summary['missing_digest_count']};mismatch={digest_summary['digest_mismatch_count']}",
            "approval record hash and bound upstream SHA-256 digests match current artifacts",
            paths["approval_record"],
            "request_construction_blocked_missing_digest_binding"
            if digest_summary["missing_digest_count"]
            else "request_construction_blocked_digest_mismatch",
        ),
        gate_row(args, "freshness", validate_freshness(inputs["freshness"]), inputs["freshness"].get("freshness_status"), "fresh within h10", paths["freshness"], "request_construction_dry_run_blocked_stale_signal"),
        gate_row(args, "broker_local_reconciliation", validate_reconciliation(inputs["reconciliation"]), inputs["reconciliation"].get("reconciliation_status"), "clean no local/no broker", paths["reconciliation"], "request_construction_dry_run_blocked_broker_local_reconciliation"),
        gate_row(args, "broker_safe_margin", validate_margin(inputs["margin"], inputs["margin_snapshot"]), inputs["margin"].get("validation_status"), "demo margin <= hard cap and coherent margin volume", paths["margin"], "request_construction_dry_run_blocked_margin_policy"),
        gate_row(args, "duplicate_protection", validate_duplicate(inputs["duplicate"]), inputs["duplicate"].get("plan_status"), "duplicate protection available", paths["duplicate"], "request_construction_dry_run_blocked_duplicate_protection"),
        gate_row(args, "manual_approval_kill_switch_plan", validate_manual_plan(inputs["manual_plan"]), inputs["manual_plan"].get("plan_status"), "kill switch plan available", paths["manual_plan"], "request_construction_dry_run_blocked_kill_switch"),
        gate_row(args, "future_request_readiness", validate_future_request(inputs["future_request"]), inputs["future_request"].get("plan_status"), "future request readiness no-order", paths["future_request"], "request_construction_dry_run_blocked_unsafe_policy"),
        gate_row(args, "future_state_compatible", not future_state_bad, future_state_note, "missing or compatible", paths["future_state"], "request_construction_dry_run_blocked_future_state_incompatible"),
    ]
    if module_validation_override_requested(args):
        gates.append(
            gate_row(
                args,
                "module_validation_stale_override_acknowledgment",
                module_validation_stale_override_allowed(args),
                module_validation_override_observed(args),
                f"demo execution stale override with ack={MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT}",
                paths["approval_record"],
                "request_construction_dry_run_blocked_module_validation_acknowledgment",
            )
        )
    if expired_signal_override_requested(args):
        gates.append(
            gate_row(
                args,
                "module_validation_expired_signal_override_acknowledgment",
                expired_signal_override_allowed(args),
                module_validation_override_observed(args),
                f"demo execution expired signal override with ack={EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT}",
                paths["approval_record"],
                "request_construction_dry_run_blocked_expired_signal_override_acknowledgment",
            )
        )
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
    add_artifact_freshness_warnings(args, warnings, freshness_rows)
    expired_signal_override_used = bool(
        approval_present
        and approval_record_expired(record)
        and expired_signal_override_allowed(args)
    )
    if expired_signal_override_used:
        add_warning(
            warnings,
            args=args,
            warning_code="request_construction_dry_run_blocked_expired_approval",
            message="Approval expiry gate overridden for demo module validation only.",
            source=paths["approval_record"],
            blocking_warning=False,
        )
    status = status_from_gates(gates, inputs, args)
    stale_override_used = False
    if status == REQUEST_CONSTRUCTION_AVAILABLE_STATUS and freshness_summary["blocking_stale_artifact_count"]:
        status = "request_construction_dry_run_blocked_stale_upstream_artifact"
    elif (
        status == REQUEST_CONSTRUCTION_AVAILABLE_STATUS
        and freshness_summary["stale_artifact_count"]
        and module_validation_stale_override_allowed(args)
    ):
        status = REQUEST_CONSTRUCTION_STALE_OVERRIDE_STATUS
        stale_override_used = True
    return {
        "status": status,
        "gates": gates,
        "future_state_note": future_state_note,
        "client_reject_flat_contract": client_reject_contract,
        "market_closed_flat_contract": market_closed_contract,
        "digest_summary": digest_summary,
        "artifact_freshness_checks": freshness_rows,
        "artifact_freshness_summary": freshness_summary,
        "stale_override_used": stale_override_used,
        "expired_signal_override_used": expired_signal_override_used,
    }


def approval_digest(record: dict[str, Any], path: Path) -> str:
    return str(record.get("record_hash_or_digest") or (sha256_file(path) if path.exists() else ""))


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def request_intent_row(args: argparse.Namespace, inputs: dict[str, Any], status: str) -> dict[str, Any]:
    record = inputs["approval_record"]
    if not status_allows_request_intent(status):
        return {"run_id": args.run_id, "candidate_id": CANDIDATE_ID, "symbol": SYMBOL, "timeframe": TIMEFRAME, "direction": DIRECTION, "request_construction_mode": "fixture_or_blocked_no_intent"}
    margin = inputs["margin"]
    margin_snapshot = inputs["margin_snapshot"]
    return {
        "run_id": args.run_id,
        "candidate_id": CANDIDATE_ID,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "direction": DIRECTION,
        "side": SIDE_INTENT,
        "order_type_intent": ORDER_TYPE_INTENT,
        "volume_lots": first_present(record.get("volume_lots"), margin.get("stepped_volume_lots"), margin_snapshot.get("margin_calc_volume_lots")),
        "entry_reference_price": record.get("entry_reference_price"),
        "sl_price": record.get("sl_price"),
        "tp_price": record.get("tp_price"),
        "risk_amount": first_present(record.get("risk_amount"), margin.get("risk_amount_max"), inputs["policy"].get("risk_amount_max")),
        "risk_percent": first_present(record.get("risk_percent"), margin.get("risk_percent_max"), inputs["policy"].get("risk_percent_max")),
        "broker_margin_estimate": first_present(record.get("broker_margin_estimate"), margin.get("broker_margin_estimate"), margin_snapshot.get("broker_margin_estimate")),
        "broker_margin_usage_ratio": first_present(record.get("broker_margin_usage_ratio"), margin.get("broker_margin_usage_ratio"), margin_snapshot.get("broker_margin_usage_ratio")),
        "spread_current_points": first_present(record.get("spread_current_points"), margin.get("spread_current_points"), margin_snapshot.get("spread_current_points")),
        "signal_time_server": record.get("signal_time_server"),
        "signal_id": record.get("signal_id"),
        "idempotency_key": record.get("idempotency_key"),
        "approval_record_id": record.get("approval_record_id"),
        "approval_record_digest": approval_digest(record, inputs["paths"]["approval_record"]),
        "approval_scope": "future_request_construction_only",
        "request_construction_mode": "dry_run_non_executable",
        "broker_payload_constructed": False,
        "executable_order_object_constructed": False,
        "order_check_allowed_now": False,
        "order_send_allowed_now": False,
        "order_execution_allowed": False,
    }


def request_field_rows(args: argparse.Namespace, intent_row: dict[str, Any]) -> list[dict[str, Any]]:
    descriptors = [
        ("action_intent", "future_deal", "fixed dry-run descriptor"),
        ("symbol", intent_row.get("symbol", SYMBOL), "approval/canonical"),
        ("volume", intent_row.get("volume_lots", ""), "approval_or_margin_validation"),
        ("type_intent", SIDE_INTENT, "fixed candidate direction"),
        ("price_reference", intent_row.get("entry_reference_price", ""), "approval record"),
        ("sl", intent_row.get("sl_price", ""), "approval record"),
        ("tp", intent_row.get("tp_price", ""), "approval record"),
        ("deviation_policy", "future_policy_recheck_required", "future order-check module"),
        ("magic_policy", "future_policy_recheck_required", "future order-check module"),
        ("comment_policy", "future_policy_recheck_required", "future order-check module"),
        ("type_time_policy", "future_policy_recheck_required", "future order-check module"),
        ("type_filling_policy", "future_policy_recheck_required", "future order-check module"),
    ]
    return [
        {
            "run_id": args.run_id,
            "field_name": name,
            "intended_value": value,
            "source": source,
            "required_for_future_order_check": True,
            "broker_payload_field_now": False,
            "executable_now": False,
            "safety_note": "descriptor_only_not_a_broker_payload",
        }
        for name, value, source in descriptors
    ]


def bound_approval_row(args: argparse.Namespace, inputs: dict[str, Any], status: str) -> dict[str, Any]:
    record = inputs["approval_record"]
    return {
        "run_id": args.run_id,
        "approval_record_path": str(inputs["paths"]["approval_record"]),
        "approval_record_id": record.get("approval_record_id", ""),
        "approval_record_digest": approval_digest(record, inputs["paths"]["approval_record"]) if record else "",
        "approval_status": record.get("approval_status", inputs.get("approval_error", "")),
        "approval_scope": record.get("approval_scope", ""),
        "approval_expiry_time_utc": record.get("approval_expiry_time_utc", ""),
        "binding_status": "bound" if status_allows_request_intent(status) else "not_bound",
    }


def bound_upstream_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    specs = [
        ("schema_manifest", "schema_manifest", "schema_status"),
        ("future_request_readiness", "future_request", "plan_status"),
        ("broker_local_reconciliation", "reconciliation", "reconciliation_status"),
        ("broker_safe_margin_validation", "margin", "validation_status"),
        ("broker_safe_margin_validation_margin_snapshot", "margin_snapshot", "validation_status"),
        ("live_signal_freshness", "freshness", "freshness_status"),
        ("duplicate_protection", "duplicate", "plan_status"),
        ("manual_approval_kill_switch", "manual_plan", "plan_status"),
    ]
    rows = []
    for name, key, status_field in specs:
        path = inputs["paths"][key]
        rows.append(
            {
                "run_id": args.run_id,
                "upstream_name": name,
                "upstream_path": str(path),
                "upstream_status_field": status_field,
                "upstream_status_value": inputs[key].get(status_field, ""),
                "sha256_digest": sha256_file(path) if path.exists() else "",
                "binding_status": "read_only_bound" if path.exists() else "missing",
            }
        )
    return rows


def idempotency_row(args: argparse.Namespace, inputs: dict[str, Any], status: str) -> dict[str, Any]:
    record = inputs["approval_record"]
    ok = bool(record.get("signal_id")) and bool(record.get("idempotency_key"))
    return {
        "run_id": args.run_id,
        "signal_id": record.get("signal_id", ""),
        "idempotency_key": record.get("idempotency_key", ""),
        "approval_record_id": record.get("approval_record_id", ""),
        "idempotency_status": "available" if ok and status_allows_request_intent(status) else "not_actionable",
        "caveat": "no state mutation and no broker request construction",
    }


def block_rows(args: argparse.Namespace, gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "block_condition": row["gate_name"],
            "condition_status": row["gate_status"],
            "observed_value": row["observed_value"],
            "expected_value": row["expected_value"],
            "blocking_if_failed": row["blocking_if_failed"],
            "caveat": "blocks dry-run request intent when failed",
        }
        for row in gates
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
        "evidence_label": "request_construction_dry_run_no_order_boundary",
        "caveat": "non_executable_intent_only_no_order_check_no_order_send",
    }


def recommended_next_step(status: str) -> str:
    if status == REQUEST_CONSTRUCTION_AVAILABLE_STATUS:
        return "build_fixed_candidate_demo_order_check_plan_or_check_module"
    if status == REQUEST_CONSTRUCTION_STALE_OVERRIDE_STATUS:
        return "run_order_check_only_for_demo_module_validation_after_operator_review"
    if status == "request_construction_dry_run_fixture_only_no_approval_record":
        return "wait_for_fresh_signal_and_valid_approval_record"
    if status == "request_construction_dry_run_blocked_missing_approval_record":
        return "wait_for_fresh_signal_and_valid_approval_record"
    return "resolve_blocking_condition_before_request_construction"


def write_report(path: Path, args: argparse.Namespace, status: str, warnings: list[dict[str, Any]], inputs: dict[str, Any]) -> None:
    stale_override_used = status == REQUEST_CONSTRUCTION_STALE_OVERRIDE_STATUS
    expired_signal_override_used = bool(inputs.get("expired_signal_override_used"))
    client_reject_contract = inputs.get("client_reject_flat_contract") or {}
    explicit_client_reject_resend = bool(client_reject_contract.get("accepted"))
    market_closed_contract = inputs.get("market_closed_flat_contract") or {}
    explicit_market_closed_new_signal = bool(market_closed_contract.get("accepted"))
    lines = [
        "# Fixed-Candidate Demo Request Construction Dry-Run",
        "",
        "Artifact-only non-executable request-construction dry-run.",
        "",
        "No MT5 import or connection was performed. No broker/API query, positions/orders/history read, order check, order send, order-calc call, order execution, broker payload, executable order object, future state write, database mutation, child script, scheduler, loop, background task, or trading decision was performed.",
        "",
        "The request intent and field descriptors are not broker payloads and cannot be passed directly to an order-send API. Order-check remains unavailable except for an explicit demo-module validation override.",
        "",
        "## Result",
        "",
        f"- request_construction_status: `{status}`",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{sum(1 for warning in warnings if warning.get('blocking_warning') == 'true')}`",
        "",
    ]
    if stale_override_used or expired_signal_override_used or explicit_client_reject_resend:
        lines.extend(
            [
                "## Demo Module Validation Override",
                "",
                "- module_validation_demo_execution: `true`",
                f"- stale_override_used: `{bool_text(stale_override_used)}`",
                f"- expired_signal_override_used: `{bool_text(expired_signal_override_used)}`",
                f"- explicit_second_demo_send_after_client_reject_flat: `{bool_text(explicit_client_reject_resend)}`",
                f"- previous_state_status: `{client_reject_contract.get('previous_state_status', '')}`",
                f"- previous_send_retcode: `{client_reject_contract.get('previous_send_retcode', '')}`",
                f"- new_operator_authorized_attempt: `{bool_text(explicit_client_reject_resend)}`",
                "- strategy_valid: `false`",
                "- production_valid: `false`",
                "- order_check_allowed_for_demo_module_validation_only: `true`",
                "- order_send_allowed_for_demo_module_validation_only: `false`",
                "- broker_payload_constructed: `false`",
                "- executable_order_object_constructed: `false`",
                "- order_check_called: `false`",
                "- order_send_called: `false`",
                "- order_execution_performed: `false`",
                "",
            ]
        )
    if explicit_market_closed_new_signal:
        lines.extend(
            [
                "## Prior Market Closed Reject",
                "",
                "- explicit_new_signal_after_market_closed_flat: `true`",
                f"- previous_state_status: `{market_closed_contract.get('previous_state_status', '')}`",
                f"- previous_send_retcode: `{market_closed_contract.get('previous_send_retcode', '')}`",
                f"- previous_reconciliation_status: `{market_closed_contract.get('previous_reconciliation_status', '')}`",
                f"- same_signal_id: `{bool_text(bool(market_closed_contract.get('same_signal_id')))}`",
                f"- same_idempotency_key: `{bool_text(bool(market_closed_contract.get('same_idempotency_key')))}`",
                "- automatic_retry_allowed: `false`",
                "- retry_performed: `false`",
                "",
            ]
        )
    lines.extend(
        [
            "## Recommended Next Step",
            "",
            f"`{recommended_next_step(status)}`",
            "",
        ]
    )
    atomic_write_text(path, "\n".join(lines))


def write_manifest(path: Path, args: argparse.Namespace, output_dir: Path, status: str, intent_row: dict[str, Any], inputs: dict[str, Any], warnings: list[dict[str, Any]], paths: dict[str, Path]) -> None:
    record = inputs["approval_record"]
    stale_override_used = bool(inputs.get("stale_override_used"))
    expired_signal_override_used = bool(inputs.get("expired_signal_override_used"))
    client_reject_contract = inputs.get("client_reject_flat_contract") or {}
    explicit_client_reject_resend = bool(client_reject_contract.get("accepted"))
    market_closed_contract = inputs.get("market_closed_flat_contract") or {}
    explicit_market_closed_new_signal = bool(market_closed_contract.get("accepted"))
    module_validation_invalid = bool(
        args.module_validation_demo_execution
        or stale_override_used
        or expired_signal_override_used
        or explicit_client_reject_resend
    )
    manifest = {
        "run_id": args.run_id,
        "request_construction_status": status,
        "candidate_id": CANDIDATE_ID,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "direction": DIRECTION,
        "side": intent_row.get("side", ""),
        "signal_time_server": record.get("signal_time_server", ""),
        "signal_id": record.get("signal_id", ""),
        "idempotency_key": record.get("idempotency_key", ""),
        "approval_record_id": record.get("approval_record_id", ""),
        "approval_status": record.get("approval_status", ""),
        "approval_scope": record.get("approval_scope", ""),
        "approval_expiry_time_utc": record.get("approval_expiry_time_utc", ""),
        "approval_record_digest": approval_digest(record, inputs["paths"]["approval_record"]) if record else "",
        "digest_binding_required": inputs["digest_summary"]["digest_binding_required"],
        "digest_binding_verified": inputs["digest_summary"]["digest_binding_verified"],
        "digest_algorithm": inputs["digest_summary"]["digest_algorithm"],
        "digest_canonicalization": inputs["digest_summary"]["digest_canonicalization"],
        "missing_digest_count": inputs["digest_summary"]["missing_digest_count"],
        "digest_mismatch_count": inputs["digest_summary"]["digest_mismatch_count"],
        "digest_verification_status": inputs["digest_summary"]["digest_verification_status"],
        "request_intent_digest": sha256_file(paths["intent"]) if paths["intent"].exists() else "",
        "request_fields_digest": sha256_file(paths["fields"]) if paths["fields"].exists() else "",
        "request_intent_created": status_allows_request_intent(status),
        "module_validation_demo_execution": bool(args.module_validation_demo_execution),
        "stale_override_used": stale_override_used,
        "expired_signal_override_used": expired_signal_override_used,
        "explicit_second_demo_send_after_client_reject_flat": explicit_client_reject_resend,
        "explicit_new_signal_after_market_closed_flat": explicit_market_closed_new_signal,
        "client_reject_resend_acknowledgment_valid": bool(
            client_reject_contract.get("client_reject_resend_acknowledgment_valid")
        ),
        "previous_state_status": first_present(
            client_reject_contract.get("previous_state_status", ""),
            market_closed_contract.get("previous_state_status", ""),
        ),
        "previous_send_retcode": first_present(
            client_reject_contract.get("previous_send_retcode", ""),
            market_closed_contract.get("previous_send_retcode", ""),
        ),
        "previous_reconciliation_status": market_closed_contract.get("previous_reconciliation_status", ""),
        "new_signal_id_differs_from_previous_state": (
            not bool(market_closed_contract.get("same_signal_id")) if explicit_market_closed_new_signal else False
        ),
        "new_idempotency_key_differs_from_previous_state": (
            not bool(market_closed_contract.get("same_idempotency_key")) if explicit_market_closed_new_signal else False
        ),
        "new_operator_authorized_attempt": explicit_client_reject_resend,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "strategy_valid": status == REQUEST_CONSTRUCTION_AVAILABLE_STATUS and not module_validation_invalid,
        "production_valid": status == REQUEST_CONSTRUCTION_AVAILABLE_STATUS and not module_validation_invalid,
        "order_check_allowed_for_demo_module_validation_only": (
            stale_override_used or expired_signal_override_used or explicit_client_reject_resend
        ),
        "order_send_allowed_for_demo_module_validation_only": False,
        "atomic_artifact_writes_enabled": ATOMIC_ARTIFACT_WRITES_ENABLED,
        "atomic_write_strategy": ATOMIC_WRITE_STRATEGY,
        "broker_payload_constructed": False,
        "executable_order_object_constructed": False,
        "order_check_called": False,
        "order_send_called": False,
        "order_execution_performed": False,
        "future_state_json_written": False,
        "order_check_allowed_now": False,
        "order_send_allowed_now": False,
        "request_construction_mode": intent_row.get("request_construction_mode", "fixture_or_blocked_no_intent"),
        "output_files": {key: str(value) for key, value in paths.items()},
        "created_at_utc": utc_now_text(),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "recommended_next_step": recommended_next_step(status),
        "no_mt5_import_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_api_query_performed": True,
        "no_order_check_called": True,
        "no_order_send_called": True,
        "no_order_execution_performed": True,
        "no_broker_payload_constructed": True,
        "no_executable_order_object_constructed": True,
        "no_future_state_json_written": True,
        "no_child_scripts_executed": True,
    }
    manifest.update(inputs["artifact_freshness_summary"])
    write_json(path, manifest)


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for(args)
    paths = output_paths(output_dir)
    ensure_outputs_writable(paths, bool(args.overwrite))
    warnings: list[dict[str, Any]] = []
    add_boundary_warnings(args, warnings)
    inputs = load_inputs(args, warnings)
    result = evaluate(args, inputs, warnings)
    status = result["status"]
    intent_row = request_intent_row(args, inputs, status)
    field_rows = request_field_rows(args, intent_row)
    protected_snapshots = {
        paths["intent"]: snapshot_path(paths["intent"]),
        paths["fields"]: snapshot_path(paths["fields"]),
    }
    try:
        write_csv(paths["intent"], [intent_row], INTENT_FIELDNAMES)
        write_csv(paths["fields"], field_rows, FIELD_DESCRIPTOR_FIELDNAMES)
        write_csv(paths["gate_checks"], result["gates"], GATE_FIELDNAMES)
        write_csv(paths["bound_approval"], [bound_approval_row(args, inputs, status)], BOUND_APPROVAL_FIELDNAMES)
        write_csv(paths["bound_upstream"], bound_upstream_rows(args, inputs), BOUND_UPSTREAM_FIELDNAMES)
        write_csv(paths["idempotency"], [idempotency_row(args, inputs, status)], IDEMPOTENCY_FIELDNAMES)
        write_csv(paths["blocks"], block_rows(args, result["gates"]), BLOCK_FIELDNAMES)
        write_csv(paths["artifact_freshness"], result["artifact_freshness_checks"], ARTIFACT_FRESHNESS_FIELDNAMES)
        inputs["artifact_freshness_summary"] = result["artifact_freshness_summary"]
        inputs["digest_summary"] = result["digest_summary"]
        inputs["stale_override_used"] = result["stale_override_used"]
        inputs["expired_signal_override_used"] = result["expired_signal_override_used"]
        inputs["client_reject_flat_contract"] = result["client_reject_flat_contract"]
        inputs["market_closed_flat_contract"] = result["market_closed_flat_contract"]
        write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
        write_csv(paths["no_order"], [no_order_evidence_row(args)], NO_ORDER_FIELDNAMES)
        write_report(paths["report"], args, status, warnings, inputs)
        write_manifest(paths["manifest"], args, output_dir, status, intent_row, inputs, warnings, paths)
    except Exception:
        for protected_path, snapshot in protected_snapshots.items():
            restore_path(protected_path, snapshot)
        raise
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a non-executable fixed-candidate demo request-construction dry-run packet.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--manual-approval-record-json", type=Path, default=DEFAULT_APPROVAL_RECORD_JSON)
    parser.add_argument("--manual-approval-record-schema-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    parser.add_argument("--future-request-readiness-plan-dir", type=Path, default=DEFAULT_FUTURE_REQUEST_READINESS_DIR)
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
    parser.add_argument("--allow-missing-approval-record-for-fixture-only", action="store_true")
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
    print("Fixed-candidate demo request construction dry-run complete.")
    for key, path in paths.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
