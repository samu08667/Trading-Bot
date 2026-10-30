"""Create a manual approval record for the fixed candidate.

This module may write exactly one manual approval record JSON when explicitly
invoked with valid operator fields and clean upstream artifacts. It does not
query MT5 or broker/API state, construct broker requests or payloads, construct
executable order objects, write future trading state, mutate databases, run
child scripts, schedule work, or make trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
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
except ModuleNotFoundError:
    from _fixed_candidate_artifact_freshness import (
        ARTIFACT_FRESHNESS_FIELDNAMES,
        DEFAULT_MAX_ARTIFACT_AGE_MINUTES,
        artifact_freshness_summary,
        evaluate_artifact_freshness,
        status_is_stale,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
CANDIDATE_SYMBOL = "GBPUSD"
CANDIDATE_TIMEFRAME = "M15"
CANDIDATE_DIRECTION = "short"
MAX_SPREAD_POINTS = 15.0
MAX_OPEN_POSITIONS = 1
HORIZON_BARS = 10
TIMEFRAME_MINUTES = 15
HARD_MARGIN_CAP_RATIO = 0.70
EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT = "acknowledge_expired_signal_for_demo_module_validation_only"
CANONICAL_SERIALIZATION = "canonical_json_sorted_keys_utf8_no_extra_whitespace"
DIGEST_ALGORITHM = "SHA-256"
ATOMIC_ARTIFACT_WRITES_ENABLED = True
ATOMIC_WRITE_STRATEGY = "temp_file_same_directory_os_replace"

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record_creation"
DEFAULT_SCHEMA_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_manual_approval_record_schema"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record_schema_v1"
)
DEFAULT_GATE_DRY_RUN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_manual_approval_gate_dry_run"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_gate_dry_run_v1"
)
DEFAULT_WOULD_SIGNAL_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_would_signal_review"
    / "gbpusd_short_h10_1_5_off_hours_demo_would_signal_review_live_v1"
)
DEFAULT_LIVE_SIGNAL_FRESHNESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_live_signal_freshness"
    / "gbpusd_short_h10_1_5_off_hours_demo_live_signal_freshness_v1"
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
DEFAULT_DUPLICATE_PROTECTION_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_duplicate_protection_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_duplicate_protection_plan_live_v1"
)
DEFAULT_MANUAL_APPROVAL_KILL_SWITCH_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_manual_approval_kill_switch_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_kill_switch_plan_live_v1"
)
DEFAULT_FUTURE_REQUEST_READINESS_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_future_request_construction_readiness_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_future_request_construction_readiness_plan_live_v1"
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
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_manual_approval_record_creation"

SCHEMA_MANIFEST = "fixed_candidate_demo_manual_approval_record_schema_manifest.json"
SCHEMA_FIELDS = "fixed_candidate_demo_manual_approval_record_schema_fields.csv"
SCHEMA_BINDINGS = "fixed_candidate_demo_manual_approval_record_schema_required_bindings.csv"
SCHEMA_EXPIRY = "fixed_candidate_demo_manual_approval_record_schema_expiry_revocation.csv"
SCHEMA_SCOPE = "fixed_candidate_demo_manual_approval_record_schema_authorization_scope.csv"
SCHEMA_PRE_APPROVAL_RECHECKS = "fixed_candidate_demo_manual_approval_record_schema_pre_approval_rechecks.csv"
SCHEMA_BLOCKS = "fixed_candidate_demo_manual_approval_record_schema_block_conditions.csv"
SCHEMA_AUDIT = "fixed_candidate_demo_manual_approval_record_schema_audit_requirements.csv"
SCHEMA_WARNINGS = "fixed_candidate_demo_manual_approval_record_schema_warnings.csv"
SCHEMA_ALLOWED_STATUSES = "fixed_candidate_demo_manual_approval_record_schema_allowed_statuses.csv"
SCHEMA_OPERATOR_DECISIONS = "fixed_candidate_demo_manual_approval_record_schema_operator_decision_labels.csv"
SCHEMA_POST_APPROVAL_RECHECKS = "fixed_candidate_demo_manual_approval_record_schema_post_approval_pre_request_rechecks.csv"
SCHEMA_DIGEST_RULES = "fixed_candidate_demo_manual_approval_record_schema_digest_rules.csv"
SCHEMA_UPSTREAM_DIGESTS = "fixed_candidate_demo_manual_approval_record_schema_upstream_artifact_digests.csv"
SCHEMA_SIGNAL_ID_RULE = "fixed_candidate_demo_manual_approval_record_schema_signal_id_rule.csv"

GATE_MANIFEST = "fixed_candidate_demo_manual_approval_gate_dry_run_manifest.json"
WOULD_SIGNAL_REVIEW_MANIFEST = "fixed_candidate_demo_would_signal_review_manifest.json"
FRESHNESS_MANIFEST = "fixed_candidate_demo_live_signal_freshness_manifest.json"
BROKER_RECON_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
MARGIN_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"
DUPLICATE_MANIFEST = "fixed_candidate_demo_duplicate_protection_plan_manifest.json"
MANUAL_PLAN_MANIFEST = "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json"
FUTURE_REQUEST_MANIFEST = "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json"

RUNTIME_UPSTREAM_BINDINGS = [
    ("manual_approval_gate_dry_run_manifest", "gate", "gate_status"),
    ("live_signal_freshness_manifest", "freshness", "freshness_status"),
    ("broker_local_reconciliation_manifest", "reconciliation", "reconciliation_status"),
    ("broker_safe_margin_validation_manifest", "margin", "validation_status"),
    ("broker_safe_margin_validation_margin_snapshot", "margin_snapshot", "validation_status"),
    ("duplicate_protection_plan_manifest", "duplicate", "plan_status"),
    ("manual_approval_kill_switch_plan_manifest", "manual_plan", "plan_status"),
    ("future_request_readiness_plan_manifest", "future_request", "plan_status"),
]

OUTPUT_MANIFEST = "fixed_candidate_demo_manual_approval_record_creation_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_manual_approval_record_creation_report.md"
OUTPUT_GATE_CHECKS = "fixed_candidate_demo_manual_approval_record_creation_gate_checks.csv"
OUTPUT_OPERATOR_DECISION = "fixed_candidate_demo_manual_approval_record_creation_operator_decision.csv"
OUTPUT_BOUND_UPSTREAM = "fixed_candidate_demo_manual_approval_record_creation_bound_upstream_artifacts.csv"
OUTPUT_DIGEST_VERIFICATION = "fixed_candidate_demo_manual_approval_record_creation_digest_verification.csv"
OUTPUT_PREVIEW = "fixed_candidate_demo_manual_approval_record_creation_record_preview.json"
OUTPUT_STATUS = "fixed_candidate_demo_manual_approval_record_creation_status.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_manual_approval_record_creation_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_manual_approval_record_creation_no_order_evidence.csv"
OUTPUT_ARTIFACT_FRESHNESS = "fixed_candidate_demo_manual_approval_record_creation_artifact_freshness_checks.csv"

WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
GATE_FIELDNAMES = ["run_id", "gate_name", "gate_status", "observed_value", "expected_value", "source_path", "blocking_if_failed", "warning_code"]
OPERATOR_FIELDNAMES = ["run_id", "operator_decision_label", "operator_identity_ref_present", "operator_warning_acknowledgment_present", "decision_allowed", "decision_positive", "approval_status", "blocking_warning", "warning_code"]
BOUND_FIELDNAMES = ["run_id", "upstream_name", "upstream_path", "upstream_run_id", "upstream_status_field", "upstream_status_value", "sha256_digest", "required_for_future_approval_record"]
DIGEST_FIELDNAMES = ["run_id", "upstream_name", "expected_sha256_digest", "actual_sha256_digest", "digest_match", "source_path", "blocking_warning"]
STATUS_FIELDNAMES = ["run_id", "creation_status", "approval_record_created", "approval_status", "approval_scope", "recommended_next_step", "blocking_warnings_count"]
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
    "no_order_request_constructed",
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


def read_csv(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], "missing"
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), ""
    except (OSError, csv.Error) as exc:
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


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_sha256_hex(value: Any) -> bool:
    text = str(value or "").strip()
    return len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text)


def digest_binding_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing_count = 0
    mismatch_count = 0
    required_count = len(rows)
    for row in rows:
        expected = row.get("expected_sha256_digest", "")
        actual = row.get("actual_sha256_digest", "")
        if not is_sha256_hex(expected) or not is_sha256_hex(actual):
            missing_count += 1
        elif str(expected).lower() != str(actual).lower():
            mismatch_count += 1
    verified = required_count > 0 and missing_count == 0 and mismatch_count == 0
    if missing_count:
        status = "digest_binding_missing"
    elif mismatch_count:
        status = "digest_binding_mismatch"
    elif verified:
        status = "digest_binding_verified"
    else:
        status = "digest_binding_missing"
    return {
        "digest_binding_required": True,
        "digest_binding_verified": verified,
        "digest_algorithm": "sha256",
        "digest_canonicalization": "canonical_json_or_documented_csv_rule",
        "missing_digest_count": missing_count if required_count else 1,
        "digest_mismatch_count": mismatch_count,
        "digest_verification_status": status,
    }


def parse_time(value: Any) -> datetime | None:
    if value in ("", None):
        return None
    text = str(value).strip()
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    if " " in text and "T" not in text:
        candidates.append(text.replace(" ", "T"))
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


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


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [warning for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"]


def expired_signal_override_requested(args: argparse.Namespace) -> bool:
    return bool(args.allow_expired_signal_for_demo_module_validation or args.expired_signal_override_acknowledgment)


def expired_signal_override_allowed(args: argparse.Namespace) -> bool:
    return (
        args.module_validation_demo_execution is True
        and args.allow_expired_signal_for_demo_module_validation is True
        and args.expired_signal_override_acknowledgment == EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT
    )


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "gate_checks": output_dir / OUTPUT_GATE_CHECKS,
        "operator_decision": output_dir / OUTPUT_OPERATOR_DECISION,
        "bound_upstream": output_dir / OUTPUT_BOUND_UPSTREAM,
        "digest_verification": output_dir / OUTPUT_DIGEST_VERIFICATION,
        "record_preview": output_dir / OUTPUT_PREVIEW,
        "status": output_dir / OUTPUT_STATUS,
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
        "schema_fields": base / SCHEMA_FIELDS,
        "schema_bindings": base / SCHEMA_BINDINGS,
        "schema_expiry": base / SCHEMA_EXPIRY,
        "schema_scope": base / SCHEMA_SCOPE,
        "schema_pre_approval_rechecks": base / SCHEMA_PRE_APPROVAL_RECHECKS,
        "schema_blocks": base / SCHEMA_BLOCKS,
        "schema_audit": base / SCHEMA_AUDIT,
        "schema_warnings": base / SCHEMA_WARNINGS,
        "allowed_statuses": base / SCHEMA_ALLOWED_STATUSES,
        "operator_decisions": base / SCHEMA_OPERATOR_DECISIONS,
        "post_approval_rechecks": base / SCHEMA_POST_APPROVAL_RECHECKS,
        "digest_rules": base / SCHEMA_DIGEST_RULES,
        "upstream_digests": base / SCHEMA_UPSTREAM_DIGESTS,
        "signal_id_rule": base / SCHEMA_SIGNAL_ID_RULE,
    }


def source_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths = schema_paths(args)
    paths.update(
        {
            "registry": Path(args.canonical_registry),
            "policy": Path(args.demo_execution_policy),
            "gate": Path(args.manual_approval_gate_dry_run_dir) / GATE_MANIFEST,
            "would_signal": Path(args.would_signal_review_dir) / WOULD_SIGNAL_REVIEW_MANIFEST,
            "freshness": Path(args.live_signal_freshness_dir) / FRESHNESS_MANIFEST,
            "reconciliation": Path(args.broker_local_reconciliation_dir) / BROKER_RECON_MANIFEST,
            "margin": Path(args.broker_safe_margin_validation_dir) / MARGIN_MANIFEST,
            "margin_snapshot": Path(args.broker_safe_margin_validation_dir) / MARGIN_SNAPSHOT,
            "duplicate": Path(args.duplicate_protection_plan_dir) / DUPLICATE_MANIFEST,
            "manual_plan": Path(args.manual_approval_kill_switch_plan_dir) / MANUAL_PLAN_MANIFEST,
            "future_request": Path(args.future_request_readiness_plan_dir) / FUTURE_REQUEST_MANIFEST,
            "future_approval_record": Path(args.future_approval_record_json),
            "future_state": Path(args.future_state_json),
        }
    )
    return paths


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    paths = source_paths(args)
    inputs: dict[str, Any] = {"paths": paths, "json_errors": {}, "csv_errors": {}}
    json_keys = {
        "schema_manifest",
        "registry",
        "policy",
        "gate",
        "would_signal",
        "freshness",
        "reconciliation",
        "margin",
        "margin_snapshot",
        "duplicate",
        "manual_plan",
        "future_request",
    }
    csv_keys = {
        "schema_fields",
        "schema_bindings",
        "schema_expiry",
        "schema_scope",
        "schema_pre_approval_rechecks",
        "schema_blocks",
        "schema_audit",
        "schema_warnings",
        "allowed_statuses",
        "operator_decisions",
        "post_approval_rechecks",
        "digest_rules",
        "upstream_digests",
        "signal_id_rule",
    }
    for key in json_keys:
        data, error = read_json(paths[key])
        inputs[key] = data
        inputs["json_errors"][key] = error
        if error:
            code = "blocked_missing_schema_manifest" if key == "schema_manifest" and error == "missing" else f"{key}_unreadable"
            warnings.append(
                warning_row(
                    run_id=args.run_id,
                    warning_code=code,
                    message=error,
                    source=paths[key],
                    blocking_warning=True,
                )
            )
    for key in csv_keys:
        rows, error = read_csv(paths[key])
        inputs[key] = rows
        inputs["csv_errors"][key] = error
        if error:
            missing_codes = {
                "allowed_statuses": "blocked_missing_allowed_statuses_artifact",
                "operator_decisions": "blocked_missing_operator_decision_labels_artifact",
                "post_approval_rechecks": "blocked_missing_post_approval_pre_request_rechecks_artifact",
                "digest_rules": "blocked_missing_digest_rules_artifact",
                "upstream_digests": "blocked_missing_upstream_artifact_digests_artifact",
                "signal_id_rule": "blocked_missing_signal_id_rule_artifact",
            }
            code = missing_codes.get(key, f"{key}_unreadable") if error == "missing" else f"{key}_unreadable"
            warnings.append(
                warning_row(
                    run_id=args.run_id,
                    warning_code=code,
                    message=error,
                    source=paths[key],
                    blocking_warning=True,
                )
            )
    return inputs


def validate_canonical_registry(registry: dict[str, Any]) -> bool:
    registry_max_open_positions = safe_int(registry.get("max_open_positions"))
    return (
        registry.get("candidate_id") == CANDIDATE_ID
        and registry.get("symbol") == CANDIDATE_SYMBOL
        and registry.get("timeframe") == CANDIDATE_TIMEFRAME
        and registry.get("direction") == CANDIDATE_DIRECTION
        and registry.get("spread_unit") == "broker_points"
        and safe_float(registry.get("max_spread_points")) == MAX_SPREAD_POINTS
        and registry_max_open_positions in (None, MAX_OPEN_POSITIONS)
        and (registry.get("horizon_bars") in (None, HORIZON_BARS))
    )


def validate_demo_policy(policy: dict[str, Any]) -> bool:
    boundaries = policy.get("safety_boundaries", {})
    if not isinstance(boundaries, dict):
        boundaries = {}
    return (
        policy.get("candidate_id") in (None, CANDIDATE_ID)
        and policy.get("symbol") in (None, CANDIDATE_SYMBOL)
        and policy.get("timeframe") in (None, CANDIDATE_TIMEFRAME)
        and policy.get("direction") in (None, CANDIDATE_DIRECTION)
        and policy.get("spread_unit") in (None, "broker_points")
        and (safe_float(policy.get("max_spread_points")) in (None, MAX_SPREAD_POINTS))
        and safe_int(policy.get("max_open_positions")) == MAX_OPEN_POSITIONS
        and boundaries.get("real_money_allowed") is False
        and boundaries.get("order_execution_allowed") is False
        and boundaries.get("order_request_construction_allowed") is False
        and boundaries.get("order_check_allowed") is False
        and boundaries.get("order_calc_allowed") is False
        and boundaries.get("manual_approval_required_before_any_future_demo_order") is True
    )


def validate_schema(inputs: dict[str, Any]) -> tuple[bool, str]:
    manifest = inputs["schema_manifest"]
    if manifest.get("schema_status") != "manual_approval_record_schema_available_no_order":
        return False, "blocked_unacceptable_schema_status"
    if manifest.get("schema_patch_status") != "schema_audit_gaps_closed_no_order":
        return False, "blocked_schema_patch_missing"
    checks = [
        manifest.get("future_approval_record_created") is False,
        manifest.get("future_state_json_written") is False,
        manifest.get("manual_approval_performed") is False,
        manifest.get("request_construction_allowed_now") is False,
    ]
    return (all(checks), "blocked_unacceptable_schema_status" if not all(checks) else "")


def truthy_text(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def validate_allowed_statuses(rows: list[dict[str, str]]) -> bool:
    if not rows:
        return False
    statuses = {row.get("status", ""): row for row in rows}
    approved = statuses.get("approved_for_future_request_construction_only")
    if not approved:
        return False
    if approved.get("permits_request_construction") != "conditional_after_final_pre_request_rechecks":
        return False
    return all(row.get("permits_order_execution") == "false" for row in rows)


def operator_label_row(rows: list[dict[str, str]], label: str | None) -> dict[str, str] | None:
    if not label:
        return None
    for row in rows:
        if row.get("label") == label:
            return row
    return None


def validate_post_approval_rechecks(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and all(row.get("required") == "true" and row.get("blocking_if_failed") == "true" for row in rows)


def validate_digest_rules(rows: list[dict[str, str]]) -> bool:
    values = {row.get("rule_name"): row.get("rule_value") for row in rows}
    return (
        values.get("approval_record_digest_algorithm") == DIGEST_ALGORITHM
        and values.get("approval_record_canonical_serialization") == CANONICAL_SERIALIZATION
        and values.get("upstream_artifact_digest_algorithm") == DIGEST_ALGORITHM
        and "excludes_record_hash_or_digest_field_itself" in values.get("digest_recompute_requirement", "")
    )


def validate_gate(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("gate_status") == "manual_approval_gate_dry_run_passed_non_actionable"
        and manifest.get("source_nature") == "live_data_shadow_signal"
        and manifest.get("manual_approval_performed") is False
        and manifest.get("request_construction_allowed_now") is False
    )


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


def validate_margin(manifest: dict[str, Any]) -> bool:
    ratio = safe_float(manifest.get("broker_margin_usage_ratio"))
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
        and manifest.get("manual_approval_performed") is False
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


def upstream_warning_count(inputs: dict[str, Any]) -> int:
    count = safe_int(inputs["schema_manifest"].get("warnings_count")) or 0
    for key in ("gate", "would_signal", "freshness", "reconciliation", "margin", "duplicate", "manual_plan", "future_request"):
        count += safe_int(inputs[key].get("warnings_count")) or 0
    return count


def digest_verification_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in runtime_upstream_digest_rows(args, inputs):
        path = Path(row.get("upstream_path", ""))
        actual = sha256_file(path) if path.exists() else ""
        expected = row.get("sha256_digest", "")
        rows.append(
            {
                "run_id": args.run_id,
                "upstream_name": row.get("upstream_name", ""),
                "expected_sha256_digest": expected,
                "actual_sha256_digest": actual,
                "digest_match": bool_text(bool(expected) and actual == expected),
                "source_path": path,
                "blocking_warning": bool_text(not expected or actual != expected),
            }
        )
    return rows


def runtime_upstream_digest_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    paths = inputs["paths"]
    for upstream_name, key, status_field in RUNTIME_UPSTREAM_BINDINGS:
        path = paths[key]
        payload = inputs.get(key) or {}
        rows.append(
            {
                "run_id": args.run_id,
                "upstream_name": upstream_name,
                "upstream_path": str(path),
                "upstream_run_id": payload.get("run_id", ""),
                "upstream_status_field": status_field,
                "upstream_status_value": payload.get(status_field, ""),
                "sha256_digest": sha256_file(path) if path.exists() else "",
                "required_for_future_approval_record": "true",
            }
        )
    return rows


def bound_upstream_rows(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    return runtime_upstream_digest_rows(args, inputs)


def first_present(inputs: dict[str, Any], key: str) -> Any:
    for source in ("gate", "would_signal", "freshness", "margin", "margin_snapshot", "future_request"):
        value = inputs[source].get(key)
        if value not in (None, ""):
            return value
    return None


def first_present_alias(inputs: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = first_present(inputs, key)
        if value not in (None, ""):
            return value
    return None


def signal_components(inputs: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": CANDIDATE_ID,
        "symbol": CANDIDATE_SYMBOL,
        "timeframe": CANDIDATE_TIMEFRAME,
        "direction": CANDIDATE_DIRECTION,
        "signal_time_server": first_present_alias(inputs, "signal_time_server", "time_server"),
        "entry_reference_price": first_present_alias(inputs, "entry_reference_price", "entry_price_preview", "margin_calc_price"),
        "sl_price": first_present_alias(inputs, "sl_price", "sl_price_preview"),
        "tp_price": first_present_alias(inputs, "tp_price", "tp_price_preview"),
    }


def identity_source_text(components: dict[str, Any]) -> str | None:
    required = [
        "candidate_id",
        "symbol",
        "timeframe",
        "direction",
        "signal_time_server",
        "entry_reference_price",
        "sl_price",
        "tp_price",
    ]
    values = [components.get(key) for key in required]
    if any(value in (None, "") for value in values):
        return None
    return "".join(str(value) for value in values)


def signal_id(inputs: dict[str, Any]) -> tuple[str, str]:
    explicit = first_present(inputs, "signal_id")
    if explicit:
        return str(explicit), "explicit_upstream_signal_id"
    text = identity_source_text(signal_components(inputs))
    if not text:
        return "", "missing_derivation_inputs"
    return sha256_text(text), "deterministic_sha256_fallback"


def idempotency_key(inputs: dict[str, Any]) -> str:
    text = identity_source_text(signal_components(inputs))
    return sha256_text(text) if text else ""


def future_state_incompatible(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing_allowed"
    data, error = read_json(path)
    if error:
        return True, error
    state = str(data.get("state") or data.get("status") or data.get("approval_status") or "").lower()
    if state in {"pending", "open", "approved", "active", "request_pending", "position_open"}:
        return True, state
    return False, state or "compatible"


def existing_approval(path: Path) -> tuple[dict[str, Any], str, bool]:
    data, error = read_json(path)
    if error == "missing":
        return {}, "", False
    if error:
        return {}, error, False
    expiry = parse_time(data.get("approval_expiry_time_utc"))
    active = (
        data.get("approval_status") == "approved_for_future_request_construction_only"
        and data.get("approval_revoked") is not True
        and (expiry is None or expiry > utc_now())
    )
    return data, "", active


def approval_status_for_label(label: str | None, existing_record_exists: bool) -> str:
    if label == "approve_for_future_request_construction_only":
        return "approved_for_future_request_construction_only"
    if label == "reject_signal":
        return "rejected"
    if label == "revoke_prior_approval" and existing_record_exists:
        return "revoked"
    return "not_created"


def build_approval_record(args: argparse.Namespace, inputs: dict[str, Any], approval_status: str, sig_id: str, idem_key: str, now: datetime) -> dict[str, Any]:
    components = signal_components(inputs)
    signal_time = parse_time(components["signal_time_server"])
    expiry = signal_time + timedelta(minutes=HORIZON_BARS * TIMEFRAME_MINUTES) if signal_time else None
    operator_labels = [row.get("label", "") for row in inputs["operator_decisions"] if row.get("allowed") == "true"]
    bound_rows = inputs.get("runtime_upstream_digests") or inputs["upstream_digests"]
    bound_digests = {
        row.get("upstream_name", ""): {
            "path": row.get("upstream_path", ""),
            "sha256_digest": row.get("sha256_digest", ""),
            "status_field": row.get("upstream_status_field", ""),
            "status_value": row.get("upstream_status_value", ""),
        }
        for row in bound_rows
    }
    approval_scope = "future_request_construction_only" if approval_status == "approved_for_future_request_construction_only" else "no_request_no_execution"
    record = {
        "approval_record_version": "v1",
        "approval_record_id": sha256_text(f"{args.run_id}{sig_id}{args.operator_identity_ref or ''}")[:32],
        "approval_status": approval_status,
        "approval_scope": approval_scope,
        "candidate_id": CANDIDATE_ID,
        "symbol": CANDIDATE_SYMBOL,
        "timeframe": CANDIDATE_TIMEFRAME,
        "direction": CANDIDATE_DIRECTION,
        "source_nature": inputs["gate"].get("source_nature", ""),
        "signal_time_server": components["signal_time_server"],
        "signal_id": sig_id,
        "idempotency_key": idem_key,
        "entry_reference_price": safe_float(components["entry_reference_price"]),
        "sl_price": safe_float(components["sl_price"]),
        "tp_price": safe_float(components["tp_price"]),
        "volume_lots": safe_float(
            first_present_alias(inputs, "volume_lots", "stepped_volume_lots", "margin_calc_volume_lots")
        ),
        "risk_amount": safe_float(inputs["margin"].get("risk_amount_max") or inputs["policy"].get("risk_amount_max")),
        "risk_percent": safe_float(inputs["margin"].get("risk_percent_max") or inputs["policy"].get("risk_percent_max")),
        "broker_margin_estimate": safe_float(inputs["margin"].get("broker_margin_estimate") or inputs["margin_snapshot"].get("broker_margin_estimate")),
        "broker_margin_usage_ratio": safe_float(inputs["margin"].get("broker_margin_usage_ratio") or inputs["margin_snapshot"].get("broker_margin_usage_ratio")),
        "spread_current_points": safe_float(inputs["margin"].get("spread_current_points") or inputs["margin_snapshot"].get("spread_current_points")),
        "would_signal_review_run_id": inputs["gate"].get("would_signal_review_run_id") or inputs["would_signal"].get("run_id", ""),
        "freshness_run_id": inputs["freshness"].get("run_id", ""),
        "broker_local_reconciliation_run_id": inputs["reconciliation"].get("run_id", ""),
        "broker_safe_margin_validation_run_id": inputs["margin"].get("run_id", ""),
        "duplicate_protection_run_id": inputs["duplicate"].get("run_id", ""),
        "manual_approval_gate_dry_run_id": inputs["gate"].get("run_id", ""),
        "future_request_readiness_run_id": inputs["future_request"].get("run_id", ""),
        "kill_switch_plan_run_id": inputs["manual_plan"].get("run_id", ""),
        "operator_decision_label": args.operator_decision_label or "",
        "operator_identity_ref": args.operator_identity_ref or "",
        "operator_timestamp_utc": now.isoformat(),
        "approval_expiry_time_utc": expiry.isoformat() if expiry else "",
        "approval_revoked": approval_status == "revoked",
        "approval_revocation_time_utc": now.isoformat() if approval_status == "revoked" else None,
        "approval_revocation_reason": "operator_requested_revocation" if approval_status == "revoked" else None,
        "manual_warning_acknowledgments": [args.operator_warning_acknowledgment] if args.operator_warning_acknowledgment else [],
        "approval_note": args.approval_note or "",
        "approval_does_not_execute_order": True,
        "approval_does_not_construct_request": True,
        "approval_requires_final_pre_request_recheck": True,
        "bound_upstream_artifact_digests": bound_digests,
        "digest_algorithm": DIGEST_ALGORITHM,
        "canonical_serialization_rule": CANONICAL_SERIALIZATION,
        "post_approval_pre_request_recheck_required": True,
        "operator_decision_label_enum": operator_labels,
        "signal_id_derivation_rule": "deterministic SHA-256 over candidate_id + symbol + timeframe + direction + signal_time_server + entry_reference_price + sl_price + tp_price",
        "approval_expiry_formula": "approval_expiry_time_utc = signal_time_server + horizon_bars * timeframe_minutes",
        "created_at_utc": now.isoformat(),
        "record_hash_or_digest": "",
    }
    digest_input = dict(record)
    digest_input.pop("record_hash_or_digest", None)
    record["record_hash_or_digest"] = sha256_payload(digest_input)
    return record


def add_boundary_warnings(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> None:
    for code, message in [
        ("approval_record_does_not_authorize_execution", "Approval record does not authorize order execution."),
        ("approval_record_does_not_construct_request", "Approval record does not construct a broker request."),
        ("approval_requires_final_pre_request_rechecks", "Final post-approval/pre-request rechecks remain required."),
        ("request_construction_remains_disabled", "Request construction remains disabled in this module."),
        ("order_execution_remains_disabled", "Order execution remains disabled in this module."),
    ]:
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code=code,
                message=message,
                source=args.output_dir or DEFAULT_OUTPUT_ROOT,
                blocking_warning=False,
            )
        )


def artifact_freshness_checks(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    paths = inputs["paths"]
    blocking = not args.dry_run
    max_age = float(args.max_artifact_age_minutes)
    specs = [
        {
            "artifact_name": "would_signal_review",
            "path": paths["would_signal"],
            "payload": inputs["would_signal"],
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
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code=(
                    "manual_approval_record_creation_blocked_stale_upstream_artifact"
                    if blocking
                    else "stale_upstream_artifact_warning"
                ),
                message=f"Artifact freshness check failed for {row['artifact_name']}: {row['status']}.",
                source=row["path"],
                blocking_warning=blocking,
            )
        )


def gate_row(args: argparse.Namespace, name: str, ok: bool, observed: Any, expected: Any, source: Path, warning_code: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "gate_name": name,
        "gate_status": "passed" if ok else "failed",
        "observed_value": observed,
        "expected_value": expected,
        "source_path": source,
        "blocking_if_failed": True,
        "warning_code": "" if ok else warning_code,
    }


def evaluate(args: argparse.Namespace, inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    paths = inputs["paths"]
    freshness_rows = artifact_freshness_checks(args, inputs)
    freshness_summary = artifact_freshness_summary(
        freshness_rows,
        float(args.max_artifact_age_minutes),
    )
    inputs["runtime_upstream_digests"] = runtime_upstream_digest_rows(args, inputs)
    digest_rows = digest_verification_rows(args, inputs)
    digest_summary = digest_binding_summary(digest_rows)
    sig_id, sig_source = signal_id(inputs)
    idem_key = idempotency_key(inputs)
    label = args.operator_decision_label
    label_row = operator_label_row(inputs["operator_decisions"], label)
    existing_record, existing_error, existing_active = existing_approval(paths["future_approval_record"])
    future_state_bad, future_state_note = future_state_incompatible(paths["future_state"])
    now = utc_now()
    components = signal_components(inputs)
    signal_time = parse_time(components["signal_time_server"])
    expiry = signal_time + timedelta(minutes=HORIZON_BARS * TIMEFRAME_MINUTES) if signal_time else None
    schema_ok, schema_block = validate_schema(inputs)
    existing_record_exists = paths["future_approval_record"].exists()
    approval_status = approval_status_for_label(label, existing_record_exists)
    decision_positive = label == "approve_for_future_request_construction_only"
    warning_ack_required = upstream_warning_count(inputs) > 0
    expired_signal_override_used = False

    gate_checks = [
        gate_row(args, "canonical_registry", validate_canonical_registry(inputs["registry"]), inputs["registry"].get("candidate_id"), CANDIDATE_ID, paths["registry"], "blocked_noncanonical_candidate"),
        gate_row(args, "demo_execution_policy", validate_demo_policy(inputs["policy"]), "policy_boundaries", "no request/no execution/no real money", paths["policy"], "blocked_noncanonical_demo_execution_policy"),
        gate_row(args, "schema_status", schema_ok, inputs["schema_manifest"].get("schema_status"), "manual_approval_record_schema_available_no_order", paths["schema_manifest"], schema_block or "blocked_unacceptable_schema_status"),
        gate_row(args, "allowed_statuses", validate_allowed_statuses(inputs["allowed_statuses"]), len(inputs["allowed_statuses"]), "machine-readable statuses with no execution permission", paths["allowed_statuses"], "blocked_missing_allowed_statuses_artifact"),
        gate_row(args, "operator_decision_labels", bool(inputs["operator_decisions"]), len(inputs["operator_decisions"]), "machine-readable operator labels", paths["operator_decisions"], "blocked_missing_operator_decision_labels_artifact"),
        gate_row(args, "post_approval_pre_request_rechecks", validate_post_approval_rechecks(inputs["post_approval_rechecks"]), len(inputs["post_approval_rechecks"]), "all required/blocking", paths["post_approval_rechecks"], "blocked_missing_post_approval_pre_request_rechecks_artifact"),
        gate_row(args, "digest_rules", validate_digest_rules(inputs["digest_rules"]), len(inputs["digest_rules"]), "SHA-256 and canonical serialization rules", paths["digest_rules"], "blocked_missing_digest_rules_artifact"),
        gate_row(args, "signal_id_rule", bool(inputs["signal_id_rule"]), len(inputs["signal_id_rule"]), "signal id required and fallback rule present", paths["signal_id_rule"], "blocked_missing_signal_id_rule_artifact"),
        gate_row(args, "upstream_artifact_digests", bool(inputs["upstream_digests"]), len(inputs["upstream_digests"]), "required upstream digest rows", paths["upstream_digests"], "blocked_missing_upstream_artifact_digests_artifact"),
        gate_row(
            args,
            "digest_binding",
            bool(digest_summary["digest_binding_verified"]),
            f"missing={digest_summary['missing_digest_count']};mismatch={digest_summary['digest_mismatch_count']}",
            "all required SHA-256 digests present and matching",
            paths["upstream_digests"],
            (
                "approval_record_creation_blocked_missing_digest_binding"
                if digest_summary["missing_digest_count"]
                else "blocked_upstream_artifact_digest_mismatch"
            ),
        ),
        gate_row(args, "upstream_digest_match", all(row["digest_match"] == "true" for row in digest_rows), "digest verification", "all match", paths["schema_manifest"], "blocked_upstream_artifact_digest_mismatch"),
        gate_row(args, "manual_approval_gate", validate_gate(inputs["gate"]), inputs["gate"].get("gate_status"), "manual_approval_gate_dry_run_passed_non_actionable", paths["gate"], "blocked_unsafe_policy"),
        gate_row(args, "signal_freshness", validate_freshness(inputs["freshness"]), inputs["freshness"].get("freshness_status"), "fresh/current", paths["freshness"], "blocked_stale_signal"),
        gate_row(args, "broker_local_reconciliation", validate_reconciliation(inputs["reconciliation"]), inputs["reconciliation"].get("reconciliation_status"), "broker_local_reconciliation_clean_no_local_no_broker", paths["reconciliation"], "blocked_broker_local_reconciliation"),
        gate_row(args, "broker_safe_margin", validate_margin(inputs["margin"]), inputs["margin"].get("validation_status"), "broker_safe_margin_validation_available", paths["margin"], "blocked_margin_policy"),
        gate_row(args, "duplicate_protection", validate_duplicate(inputs["duplicate"]), inputs["duplicate"].get("plan_status"), "duplicate_protection_plan_available_no_order", paths["duplicate"], "blocked_duplicate_protection"),
        gate_row(args, "manual_approval_kill_switch_plan", validate_manual_plan(inputs["manual_plan"]), inputs["manual_plan"].get("plan_status"), "manual_approval_kill_switch_plan_available_no_order", paths["manual_plan"], "blocked_unsafe_policy"),
        gate_row(args, "future_request_readiness", validate_future_request(inputs["future_request"]), inputs["future_request"].get("plan_status"), "future_request_construction_readiness_plan_available_no_order", paths["future_request"], "blocked_unsafe_policy"),
        gate_row(args, "signal_id", bool(sig_id), sig_source, "non-empty signal_id", paths["gate"], "blocked_stale_signal"),
        gate_row(args, "idempotency_key", bool(idem_key), bool_text(bool(idem_key)), "deterministic digest present", paths["gate"], "blocked_duplicate_protection"),
        gate_row(args, "future_state_compatible", not future_state_bad, future_state_note, "missing or compatible", paths["future_state"], "blocked_future_state_incompatible"),
    ]
    if label is not None:
        gate_checks.append(
            gate_row(args, "operator_decision_label", label_row is not None and label_row.get("allowed") == "true", label, "allowed operator decision label", paths["operator_decisions"], "blocked_unknown_operator_decision_label" if label_row is None else "blocked_forbidden_operator_decision_label")
        )
    if not args.dry_run:
        gate_checks.append(gate_row(args, "operator_decision_label_present", bool(label), bool_text(bool(label)), "present", paths["operator_decisions"], "blocked_unknown_operator_decision_label"))
        gate_checks.append(gate_row(args, "operator_identity_ref", bool(args.operator_identity_ref), bool_text(bool(args.operator_identity_ref)), "present", paths["schema_manifest"], "blocked_missing_operator_identity_ref"))
        gate_checks.append(
            gate_row(
                args,
                "operator_warning_acknowledgment",
                (not warning_ack_required) or bool(args.operator_warning_acknowledgment),
                bool_text(bool(args.operator_warning_acknowledgment)),
                "present when upstream warnings exist",
                paths["schema_manifest"],
                "blocked_missing_warning_acknowledgment",
            )
        )
    if existing_error:
        gate_checks.append(gate_row(args, "existing_approval_record_readable", False, existing_error, "missing or readable", paths["future_approval_record"], "blocked_output_exists_without_overwrite"))
    if existing_active and decision_positive:
        gate_checks.append(gate_row(args, "existing_active_approval_record", False, "active approved record exists", "no active approved record", paths["future_approval_record"], "blocked_existing_active_approval_record"))
    if existing_record_exists and not args.overwrite and not args.dry_run:
        gate_checks.append(gate_row(args, "approval_record_output_overwrite", False, "existing output", "use --overwrite only when safe", paths["future_approval_record"], "blocked_output_exists_without_overwrite"))
    if expired_signal_override_requested(args) and not expired_signal_override_allowed(args):
        gate_checks.append(
            gate_row(
                args,
                "expired_signal_override_authorization",
                False,
                (
                    f"module_validation_demo_execution={args.module_validation_demo_execution};"
                    f"allow_expired={args.allow_expired_signal_for_demo_module_validation};"
                    f"ack={args.expired_signal_override_acknowledgment or ''}"
                ),
                f"demo module validation with ack={EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT}",
                paths["freshness"],
                "blocked_invalid_expired_signal_override",
            )
        )
    if decision_positive and expiry is not None and expiry <= now:
        if expired_signal_override_allowed(args):
            expired_signal_override_used = True
            gate_checks.append(
                {
                    "run_id": args.run_id,
                    "gate_name": "approval_expiry_time",
                    "gate_status": "overridden_for_demo_module_validation",
                    "observed_value": expiry.isoformat(),
                    "expected_value": "future relative to current UTC unless explicit demo module validation override",
                    "source_path": paths["freshness"],
                    "blocking_if_failed": False,
                    "warning_code": "blocked_expired_signal",
                }
            )
            warnings.append(
                warning_row(
                    run_id=args.run_id,
                    warning_code="blocked_expired_signal",
                    message="Gate overridden for demo module validation only: approval_expiry_time.",
                    source=paths["freshness"],
                    blocking_warning=False,
                )
            )
        else:
            gate_checks.append(gate_row(args, "approval_expiry_time", False, expiry.isoformat(), "future relative to current UTC", paths["freshness"], "blocked_expired_signal"))
    if label == "revoke_prior_approval" and not existing_record:
        gate_checks.append(gate_row(args, "revocation_existing_record", False, "missing", "existing record required for revocation", paths["future_approval_record"], "blocked_output_exists_without_overwrite"))

    for row in gate_checks:
        if row["gate_status"] == "failed":
            warnings.append(
                warning_row(
                    run_id=args.run_id,
                    warning_code=str(row["warning_code"]),
                    message=f"Gate failed: {row['gate_name']}",
                    source=str(row["source_path"]),
                    blocking_warning=True,
                )
            )
    add_artifact_freshness_warnings(args, warnings, freshness_rows)

    if args.dry_run:
        creation_status = "manual_approval_record_creation_dry_run_no_record_created"
    elif freshness_summary["blocking_stale_artifact_count"]:
        creation_status = "manual_approval_record_creation_blocked_stale_upstream_artifact"
    elif blocking_warnings(warnings):
        creation_status = blocking_warnings(warnings)[0]["warning_code"]
    elif label in {"no_decision", "acknowledge_warning_only"}:
        creation_status = "manual_approval_record_not_created_no_positive_decision"
    elif label == "approve_for_future_request_construction_only":
        creation_status = "manual_approval_record_created_for_future_request_construction_only"
    elif label == "reject_signal":
        creation_status = "manual_approval_record_created_rejected_no_request"
    elif label == "revoke_prior_approval":
        creation_status = "manual_approval_record_created_revoked_no_request"
    else:
        creation_status = "blocked_unknown_operator_decision_label"

    record_status = approval_status
    record = build_approval_record(args, inputs, record_status, sig_id, idem_key, now)
    record.update(digest_summary)
    record["module_validation_demo_execution"] = bool(args.module_validation_demo_execution)
    record["expired_signal_override_used"] = expired_signal_override_used
    record["strategy_valid"] = not (args.module_validation_demo_execution or expired_signal_override_used)
    record["production_valid"] = not (args.module_validation_demo_execution or expired_signal_override_used)
    digest_input = dict(record)
    digest_input.pop("record_hash_or_digest", None)
    record["record_hash_or_digest"] = sha256_payload(digest_input)
    if "blocked" in creation_status:
        record["approval_status"] = creation_status
        record["approval_scope"] = "no_request_no_execution"
        digest_input = dict(record)
        digest_input.pop("record_hash_or_digest", None)
        record["record_hash_or_digest"] = sha256_payload(digest_input)

    return {
        "creation_status": creation_status,
        "approval_status": record_status,
        "approval_scope": record.get("approval_scope", ""),
        "approval_record_created": creation_status.startswith("manual_approval_record_created"),
        "record": record,
        "gate_checks": gate_checks,
        "digest_rows": digest_rows,
        "digest_summary": digest_summary,
        "bound_rows": bound_upstream_rows(args, inputs),
        "signal_id": sig_id,
        "signal_id_source": sig_source,
        "idempotency_key": idem_key,
        "approval_expiry_time_utc": record.get("approval_expiry_time_utc", ""),
        "operator_label_row": label_row or {},
        "existing_approval_active": existing_active,
        "artifact_freshness_checks": freshness_rows,
        "artifact_freshness_summary": freshness_summary,
        "expired_signal_override_used": expired_signal_override_used,
        "module_validation_demo_execution": bool(args.module_validation_demo_execution),
        "strategy_valid": not (args.module_validation_demo_execution or expired_signal_override_used),
        "production_valid": not (args.module_validation_demo_execution or expired_signal_override_used),
    }


def recommended_next_step(status: str) -> str:
    if status.startswith("manual_approval_record_created"):
        return "stop_or_build_post_approval_pre_request_recheck_module"
    if status == "manual_approval_record_creation_dry_run_no_record_created":
        return "run_real_manual_approval_record_creation_only_if_operator_intends_to_approve"
    if status == "manual_approval_record_not_created_no_positive_decision":
        return "stop_or_rerun_with_positive_operator_decision_if_intended"
    return "resolve_blocking_condition_before_manual_approval_record_creation"


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
        "no_order_request_constructed": True,
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
        "evidence_label": "manual_approval_record_creation_no_order_boundary",
        "caveat": "approval_record_only_no_request_no_payload_no_execution",
    }


def operator_decision_row(args: argparse.Namespace, result: dict[str, Any]) -> dict[str, Any]:
    label_row = result["operator_label_row"]
    return {
        "run_id": args.run_id,
        "operator_decision_label": args.operator_decision_label or "",
        "operator_identity_ref_present": bool(args.operator_identity_ref),
        "operator_warning_acknowledgment_present": bool(args.operator_warning_acknowledgment),
        "decision_allowed": label_row.get("allowed", "false") == "true",
        "decision_positive": args.operator_decision_label == "approve_for_future_request_construction_only",
        "approval_status": result["approval_status"],
        "blocking_warning": result["creation_status"].startswith("blocked_"),
        "warning_code": result["creation_status"] if result["creation_status"].startswith("blocked_") else "",
    }


def status_row(args: argparse.Namespace, result: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "creation_status": result["creation_status"],
        "approval_record_created": result["approval_record_created"],
        "approval_status": result["approval_status"],
        "approval_scope": result["approval_scope"],
        "recommended_next_step": recommended_next_step(result["creation_status"]),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
    }


def write_report(path: Path, args: argparse.Namespace, result: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Manual Approval Record Creation",
        "",
        "Creates at most one manual approval record JSON for the fixed GBPUSD candidate.",
        "No MT5 import or connection was performed.",
        "No broker/API query or broker state read was performed.",
        "No broker request, broker payload, or executable order object was constructed.",
        "No order send, check, calc, positions, orders, or history function was called.",
        "No order execution was performed.",
        "No future trading state JSON was written.",
        "No database mutation, child script, scheduler, loop, or background task was performed.",
        "This approval record does not authorize request construction by itself.",
        "This approval record does not authorize execution and is not a trading decision.",
        "",
        "## Result",
        "",
        f"- creation_status: `{result['creation_status']}`",
        f"- approval_record_created: `{bool_text(result['approval_record_created'])}`",
        f"- approval_status: `{result['approval_status']}`",
        f"- approval_scope: `{result['approval_scope']}`",
        f"- signal_id: `{result['signal_id']}`",
        f"- idempotency_key: `{result['idempotency_key']}`",
        f"- approval_expiry_time_utc: `{result['approval_expiry_time_utc']}`",
        f"- module_validation_demo_execution: `{bool_text(result['module_validation_demo_execution'])}`",
        f"- expired_signal_override_used: `{bool_text(result['expired_signal_override_used'])}`",
        f"- strategy_valid: `{bool_text(result['strategy_valid'])}`",
        f"- production_valid: `{bool_text(result['production_valid'])}`",
        "",
        "## Boundary",
        "",
        "- future_state_json_written: `false`",
        "- request_construction_allowed_now: `false`",
        "- broker_request_constructed: `false`",
        "- broker_payload_constructed: `false`",
        "- order_object_constructed: `false`",
        "- order_execution_allowed: `false`",
        "",
        "## Warnings",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{recommended_next_step(result['creation_status'])}`",
        "",
    ]
    atomic_write_text(path, "\n".join(lines))


def write_manifest(path: Path, args: argparse.Namespace, output_dir: Path, result: dict[str, Any], warnings: list[dict[str, Any]], paths: dict[str, Path]) -> None:
    record = result["record"]
    manifest = {
        "run_id": args.run_id,
        "created_at_utc": utc_now_text(),
        "output_dir": str(output_dir),
        "creation_status": result["creation_status"],
        "approval_record_created": result["approval_record_created"],
        "approval_status": result["approval_status"],
        "approval_scope": result["approval_scope"],
        "candidate_id": CANDIDATE_ID,
        "symbol": CANDIDATE_SYMBOL,
        "timeframe": CANDIDATE_TIMEFRAME,
        "direction": CANDIDATE_DIRECTION,
        "source_nature": record.get("source_nature", ""),
        "signal_time_server": record.get("signal_time_server", ""),
        "signal_id": result["signal_id"],
        "idempotency_key": result["idempotency_key"],
        "approval_expiry_time_utc": result["approval_expiry_time_utc"],
        "module_validation_demo_execution": result["module_validation_demo_execution"],
        "expired_signal_override_used": result["expired_signal_override_used"],
        "strategy_valid": result["strategy_valid"],
        "production_valid": result["production_valid"],
        "digest_binding_required": result["digest_summary"]["digest_binding_required"],
        "digest_binding_verified": result["digest_summary"]["digest_binding_verified"],
        "digest_algorithm": result["digest_summary"]["digest_algorithm"],
        "digest_canonicalization": result["digest_summary"]["digest_canonicalization"],
        "missing_digest_count": result["digest_summary"]["missing_digest_count"],
        "digest_mismatch_count": result["digest_summary"]["digest_mismatch_count"],
        "digest_verification_status": result["digest_summary"]["digest_verification_status"],
        "operator_decision_label": args.operator_decision_label or "",
        "operator_identity_ref_present": bool(args.operator_identity_ref),
        "future_approval_record_json": str(args.future_approval_record_json),
        "future_approval_record_written": bool(result["approval_record_created"] and not args.dry_run),
        "atomic_artifact_writes_enabled": ATOMIC_ARTIFACT_WRITES_ENABLED,
        "atomic_write_strategy": ATOMIC_WRITE_STRATEGY,
        "future_state_json_written": False,
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
        "order_execution_allowed": False,
        "demo_approval_performed": False,
        "output_files": {key: str(value) for key, value in paths.items()},
        "recommended_next_step": recommended_next_step(result["creation_status"]),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
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
        "no_order_request_constructed": True,
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
    manifest.update(result["artifact_freshness_summary"])
    write_json(path, manifest)


def maybe_write_approval_record(args: argparse.Namespace, result: dict[str, Any]) -> None:
    if args.dry_run or not result["approval_record_created"]:
        return
    path = Path(args.future_approval_record_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, result["record"])


def build_artifacts(args: argparse.Namespace, paths: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    inputs = load_inputs(args, warnings)
    add_boundary_warnings(args, warnings)
    result = evaluate(args, inputs, warnings)
    approval_record_snapshot = snapshot_path(Path(args.future_approval_record_json))
    try:
        write_csv(paths["gate_checks"], result["gate_checks"], GATE_FIELDNAMES)
        write_csv(paths["operator_decision"], [operator_decision_row(args, result)], OPERATOR_FIELDNAMES)
        write_csv(paths["bound_upstream"], result["bound_rows"], BOUND_FIELDNAMES)
        write_csv(paths["digest_verification"], result["digest_rows"], DIGEST_FIELDNAMES)
        write_csv(paths["artifact_freshness"], result["artifact_freshness_checks"], ARTIFACT_FRESHNESS_FIELDNAMES)
        write_json(paths["record_preview"], result["record"])
        write_csv(paths["status"], [status_row(args, result, warnings)], STATUS_FIELDNAMES)
        write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
        write_csv(paths["no_order"], [no_order_evidence_row(args)], NO_ORDER_FIELDNAMES)
        maybe_write_approval_record(args, result)
        write_report(paths["report"], args, result, warnings)
        write_manifest(paths["manifest"], args, output_dir, result, warnings, paths)
    except Exception:
        restore_path(Path(args.future_approval_record_json), approval_record_snapshot)
        raise
    return {"result": result, "warnings": warnings}


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = output_paths(output_dir)
    ensure_outputs_writable(paths, bool(args.overwrite))
    build_artifacts(args, paths, output_dir)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a fixed-candidate manual approval record without request construction or execution.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--manual-approval-record-schema-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    parser.add_argument("--manual-approval-gate-dry-run-dir", type=Path, default=DEFAULT_GATE_DRY_RUN_DIR)
    parser.add_argument("--would-signal-review-dir", type=Path, default=DEFAULT_WOULD_SIGNAL_REVIEW_DIR)
    parser.add_argument("--live-signal-freshness-dir", type=Path, default=DEFAULT_LIVE_SIGNAL_FRESHNESS_DIR)
    parser.add_argument("--broker-local-reconciliation-dir", type=Path, default=DEFAULT_BROKER_LOCAL_RECONCILIATION_DIR)
    parser.add_argument("--broker-safe-margin-validation-dir", type=Path, default=DEFAULT_BROKER_SAFE_MARGIN_VALIDATION_DIR)
    parser.add_argument("--duplicate-protection-plan-dir", type=Path, default=DEFAULT_DUPLICATE_PROTECTION_PLAN_DIR)
    parser.add_argument("--manual-approval-kill-switch-plan-dir", type=Path, default=DEFAULT_MANUAL_APPROVAL_KILL_SWITCH_PLAN_DIR)
    parser.add_argument("--future-request-readiness-plan-dir", type=Path, default=DEFAULT_FUTURE_REQUEST_READINESS_PLAN_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_DEMO_EXECUTION_POLICY)
    parser.add_argument("--future-approval-record-json", type=Path, default=DEFAULT_FUTURE_APPROVAL_RECORD_JSON)
    parser.add_argument("--future-state-json", type=Path, default=DEFAULT_FUTURE_STATE_JSON)
    parser.add_argument("--operator-decision-label")
    parser.add_argument("--operator-identity-ref")
    parser.add_argument("--operator-warning-acknowledgment")
    parser.add_argument("--approval-note", default="")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-artifact-age-minutes", type=float, default=DEFAULT_MAX_ARTIFACT_AGE_MINUTES)
    parser.add_argument("--module-validation-demo-execution", action="store_true")
    parser.add_argument("--allow-expired-signal-for-demo-module-validation", action="store_true")
    parser.add_argument("--expired-signal-override-acknowledgment", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, csv.Error) as exc:
        print(f"Fixed-candidate manual approval record creation failed: {exc}")
        return 1
    print("Fixed-candidate manual approval record creation complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
