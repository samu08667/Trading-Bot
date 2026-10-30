"""Design the future manual approval record schema for the fixed candidate.

This artifact-only module defines the approval record schema required before
any future real manual approval could be recorded. It does not perform manual
approval, request operator input, create approval records, write future state,
construct broker requests or payloads, execute orders, query broker/API state,
mutate databases, run child scripts, schedule work, or make trading decisions.
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
CANDIDATE_SYMBOL = "GBPUSD"
CANDIDATE_TIMEFRAME = "M15"
CANDIDATE_DIRECTION = "short"
MAX_SPREAD_POINTS = 15.0
MAX_OPEN_POSITIONS = 1
HORIZON_BARS = 10
HARD_MARGIN_CAP_RATIO = 0.70

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record_schema"
DEFAULT_GATE_DRY_RUN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_manual_approval_gate_dry_run"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_gate_dry_run_v1"
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
DEFAULT_FUTURE_APPROVAL_RECORD_JSON = BASE_DIR / "state" / "fixed_candidate_demo_state" / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record.json"
DEFAULT_FUTURE_STATE_JSON = BASE_DIR / "state" / "fixed_candidate_demo_state" / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_manual_approval_record_schema"

GATE_MANIFEST = "fixed_candidate_demo_manual_approval_gate_dry_run_manifest.json"
FRESHNESS_MANIFEST = "fixed_candidate_demo_live_signal_freshness_manifest.json"
BROKER_RECON_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
MARGIN_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"
DUPLICATE_MANIFEST = "fixed_candidate_demo_duplicate_protection_plan_manifest.json"
MANUAL_PLAN_MANIFEST = "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json"
FUTURE_REQUEST_MANIFEST = "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_manual_approval_record_schema_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_manual_approval_record_schema_report.md"
OUTPUT_FIELDS = "fixed_candidate_demo_manual_approval_record_schema_fields.csv"
OUTPUT_BINDINGS = "fixed_candidate_demo_manual_approval_record_schema_required_bindings.csv"
OUTPUT_EXPIRY = "fixed_candidate_demo_manual_approval_record_schema_expiry_revocation.csv"
OUTPUT_SCOPE = "fixed_candidate_demo_manual_approval_record_schema_authorization_scope.csv"
OUTPUT_RECHECKS = "fixed_candidate_demo_manual_approval_record_schema_pre_approval_rechecks.csv"
OUTPUT_BLOCKS = "fixed_candidate_demo_manual_approval_record_schema_block_conditions.csv"
OUTPUT_AUDIT = "fixed_candidate_demo_manual_approval_record_schema_audit_requirements.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_manual_approval_record_schema_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_manual_approval_record_schema_no_order_evidence.csv"
OUTPUT_ALLOWED_STATUSES = "fixed_candidate_demo_manual_approval_record_schema_allowed_statuses.csv"
OUTPUT_OPERATOR_DECISIONS = "fixed_candidate_demo_manual_approval_record_schema_operator_decision_labels.csv"
OUTPUT_POST_APPROVAL_RECHECKS = "fixed_candidate_demo_manual_approval_record_schema_post_approval_pre_request_rechecks.csv"
OUTPUT_DIGEST_RULES = "fixed_candidate_demo_manual_approval_record_schema_digest_rules.csv"
OUTPUT_UPSTREAM_DIGESTS = "fixed_candidate_demo_manual_approval_record_schema_upstream_artifact_digests.csv"
OUTPUT_SIGNAL_ID_RULE = "fixed_candidate_demo_manual_approval_record_schema_signal_id_rule.csv"

FIELD_FIELDNAMES = ["run_id", "field_name", "field_type", "required", "value_source", "validation_rule", "safety_note"]
BINDING_FIELDNAMES = ["run_id", "binding_name", "required", "source_artifact", "validation_rule", "safety_note"]
EXPIRY_FIELDNAMES = ["run_id", "rule_name", "rule_type", "trigger_condition", "effect", "reuse_allowed", "safety_note"]
SCOPE_FIELDNAMES = ["run_id", "scope_name", "scope_status", "scope_effect", "allowed", "safety_note"]
RECHECK_FIELDNAMES = ["run_id", "recheck_name", "required_before", "validation_rule", "blocking_if_failed", "source_hint"]
BLOCK_FIELDNAMES = ["run_id", "block_condition", "blocking_if_present", "validation_rule", "source_hint", "safety_note"]
AUDIT_FIELDNAMES = ["run_id", "audit_requirement", "required", "validation_rule", "storage_note", "safety_note"]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
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
    "no_manual_approval_performed",
    "no_demo_broker_approval_performed",
    "no_future_approval_record_created",
    "no_future_state_json_written",
    "no_db_mutation_performed",
    "no_child_scripts_executed",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "no_trading_decision_performed",
    "evidence_label",
    "caveat",
]
ALLOWED_STATUS_FIELDNAMES = ["status", "status_type", "terminal", "reusable", "permits_request_construction", "permits_order_execution", "safety_note"]
OPERATOR_DECISION_FIELDNAMES = ["label", "label_type", "allowed", "maps_to_approval_status", "permits_request_construction", "permits_order_execution", "safety_note"]
POST_APPROVAL_RECHECK_FIELDNAMES = ["recheck_name", "timing", "required", "blocking_if_failed", "expected_value", "safety_note"]
DIGEST_RULE_FIELDNAMES = ["rule_name", "rule_value", "applies_to", "blocking_if_missing", "safety_note"]
UPSTREAM_DIGEST_FIELDNAMES = ["upstream_name", "upstream_path", "upstream_run_id", "upstream_status_field", "upstream_status_value", "digest_algorithm", "sha256_digest", "required_for_future_approval_record", "safety_note"]
SIGNAL_ID_RULE_FIELDNAMES = ["rule_name", "rule_value", "required", "blocking_if_failed", "safety_note"]

SCHEMA_FIELDS = [
    ("approval_record_version", "string", "schema constant", "must match current schema version", "versioned record for compatibility"),
    ("approval_record_id", "string", "future approval module", "globally unique for one approval attempt", "idempotent approval identity"),
    ("approval_status", "enum", "future approval module", "must be one allowed approval_status value", "positive status does not execute"),
    ("approval_scope", "enum", "future approval module", "only future_request_construction_only may be positive", "narrow scope only"),
    ("candidate_id", "string", "canonical registry", f"must equal {CANDIDATE_ID}", "binds approval to fixed candidate"),
    ("symbol", "string", "canonical registry", f"must equal {CANDIDATE_SYMBOL}", "symbol immutable"),
    ("timeframe", "string", "canonical registry", f"must equal {CANDIDATE_TIMEFRAME}", "timeframe immutable"),
    ("direction", "string", "canonical registry", f"must equal {CANDIDATE_DIRECTION}", "direction immutable"),
    ("source_nature", "string", "upstream artifacts", "must be live_data_shadow_signal", "fixture signals cannot be approved"),
    ("signal_time_server", "timestamp", "would-signal/freshness artifact", "must bind to fresh signal timestamp", "stale signal blocks"),
    ("signal_id", "string", "future signal identity", "required non-empty", "prevents ambiguous approval"),
    ("signal_id_derivation_rule", "string", "signal id rule artifact", "explicit signal_id preferred; deterministic fallback only if inputs complete", "missing derivation inputs block"),
    ("idempotency_key", "string", "duplicate protection artifact", "required non-empty and unique", "prevents duplicate request path"),
    ("entry_reference_price", "number", "would-signal review", "must match bound signal", "audit-only price binding"),
    ("sl_price", "number", "would-signal review", "must match bound signal", "risk boundary binding"),
    ("tp_price", "number", "would-signal review", "must match bound signal", "target boundary binding"),
    ("volume_lots", "number", "risk/volume or margin validation", "must match validated stepped volume", "no recalculation here"),
    ("risk_amount", "number", "demo execution policy/risk artifact", "must be within configured cap", "demo-only risk cap"),
    ("risk_percent", "number", "demo execution policy/risk artifact", "must be within configured cap", "demo-only risk cap"),
    ("broker_margin_estimate", "number", "margin validation artifact", "must match bound margin run", "margin evidence binding"),
    ("broker_margin_usage_ratio", "number", "margin validation artifact", f"must be <= {HARD_MARGIN_CAP_RATIO}", "hard cap binding"),
    ("spread_current_points", "number", "margin validation artifact", f"must be <= {MAX_SPREAD_POINTS}", "broker-points policy"),
    ("would_signal_review_run_id", "string", "would-signal review", "required", "upstream audit binding"),
    ("freshness_run_id", "string", "freshness artifact", "required", "upstream audit binding"),
    ("broker_local_reconciliation_run_id", "string", "reconciliation artifact", "required", "upstream audit binding"),
    ("broker_safe_margin_validation_run_id", "string", "margin artifact", "required", "upstream audit binding"),
    ("duplicate_protection_run_id", "string", "duplicate artifact", "required", "upstream audit binding"),
    ("manual_approval_gate_dry_run_id", "string", "gate dry-run artifact", "required", "upstream audit binding"),
    ("future_request_readiness_run_id", "string", "future request readiness artifact", "required", "upstream audit binding"),
    ("kill_switch_plan_run_id", "string", "manual approval/kill-switch plan", "required", "upstream audit binding"),
    ("bound_upstream_artifact_digests", "object", "upstream artifact digest artifact", "must include SHA-256 digest for every bound upstream artifact", "detects replaced artifacts"),
    ("digest_algorithm", "string", "digest rules artifact", "must equal SHA-256", "digest algorithm fixed"),
    ("canonical_serialization_rule", "string", "digest rules artifact", "must equal canonical_json_sorted_keys_utf8_no_extra_whitespace", "canonical digest input"),
    ("operator_decision_label", "enum", "operator decision labels artifact", "must be one allowed operator decision label", "unknown or forbidden labels block"),
    ("operator_decision_label_enum", "array", "operator decision labels artifact", "must match allowed labels artifact", "machine-readable label set"),
    ("operator_identity_ref", "string", "operator", "required before any future approval", "not collected here"),
    ("operator_timestamp_utc", "timestamp", "future approval module", "must be UTC", "audit timestamp"),
    ("approval_expiry_time_utc", "timestamp", "future approval module", "must be bounded by h10 freshness", "expiry required"),
    ("approval_expiry_formula", "string", "expiry artifact", "approval_expiry_time_utc = signal_time_server + horizon_bars * timeframe_minutes", "explicit h10 expiry"),
    ("approval_revoked", "boolean", "future approval module", "false at creation unless revocation record", "revocation explicit"),
    ("approval_revocation_time_utc", "timestamp/null", "future revocation module", "required only if revoked", "revocation audit"),
    ("approval_revocation_reason", "string/null", "future revocation module", "required only if revoked", "revocation audit"),
    ("manual_warning_acknowledgments", "array", "operator", "must acknowledge non-execution and risk caveats", "not approval here"),
    ("approval_does_not_execute_order", "boolean", "schema constant", "must be true", "approval is not execution"),
    ("approval_does_not_construct_request", "boolean", "schema constant", "must be true at approval record creation", "separate request module"),
    ("approval_requires_final_pre_request_recheck", "boolean", "schema constant", "must be true", "final gate required"),
    ("post_approval_pre_request_recheck_required", "boolean", "post-approval recheck artifact", "must be true before any later request construction", "approval alone insufficient"),
    ("created_at_utc", "timestamp", "future approval module", "must be UTC", "audit timestamp"),
    ("record_hash_or_digest", "string", "future approval module", "digest over bound fields", "immutability evidence"),
]

ALLOWED_APPROVAL_STATUSES = [
    "not_created",
    "pending_operator_review",
    "approved_for_future_request_construction_only",
    "rejected",
    "expired",
    "revoked",
    "blocked_stale_signal",
    "blocked_kill_switch",
    "blocked_broker_local_reconciliation",
    "blocked_margin_policy",
    "blocked_duplicate_protection",
    "blocked_unsafe_policy",
]
FORBIDDEN_SCOPES = [
    "execute_order",
    "send_order",
    "bypass_order_check",
    "bypass_kill_switch",
    "bypass_stale_signal",
    "bypass_margin_policy",
    "bypass_duplicate_protection",
    "bypass_broker_local_reconciliation",
]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
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


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "fields": output_dir / OUTPUT_FIELDS,
        "bindings": output_dir / OUTPUT_BINDINGS,
        "expiry": output_dir / OUTPUT_EXPIRY,
        "scope": output_dir / OUTPUT_SCOPE,
        "rechecks": output_dir / OUTPUT_RECHECKS,
        "blocks": output_dir / OUTPUT_BLOCKS,
        "audit": output_dir / OUTPUT_AUDIT,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
        "allowed_statuses": output_dir / OUTPUT_ALLOWED_STATUSES,
        "operator_decisions": output_dir / OUTPUT_OPERATOR_DECISIONS,
        "post_approval_rechecks": output_dir / OUTPUT_POST_APPROVAL_RECHECKS,
        "digest_rules": output_dir / OUTPUT_DIGEST_RULES,
        "upstream_digests": output_dir / OUTPUT_UPSTREAM_DIGESTS,
        "signal_id_rule": output_dir / OUTPUT_SIGNAL_ID_RULE,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def validate_canonical_registry(registry: dict[str, Any]) -> bool:
    horizon = registry.get("horizon_bars")
    return (
        registry.get("candidate_id") == CANDIDATE_ID
        and registry.get("symbol") == CANDIDATE_SYMBOL
        and registry.get("timeframe") == CANDIDATE_TIMEFRAME
        and registry.get("direction") == CANDIDATE_DIRECTION
        and registry.get("spread_unit") == "broker_points"
        and safe_float(registry.get("max_spread_points")) == MAX_SPREAD_POINTS
        and safe_float(registry.get("max_open_positions")) in (None, float(MAX_OPEN_POSITIONS))
        and (horizon in ("", None) or safe_float(horizon) == float(HORIZON_BARS))
    )


def validate_demo_policy(policy: dict[str, Any]) -> bool:
    boundaries = policy.get("safety_boundaries")
    if not isinstance(boundaries, dict):
        return False
    return (
        policy.get("candidate_id") == CANDIDATE_ID
        and policy.get("symbol") == CANDIDATE_SYMBOL
        and policy.get("timeframe") == CANDIDATE_TIMEFRAME
        and policy.get("direction") == CANDIDATE_DIRECTION
        and policy.get("spread_unit") == "broker_points"
        and safe_float(policy.get("max_spread_points")) == MAX_SPREAD_POINTS
        and safe_float(policy.get("max_open_positions")) == float(MAX_OPEN_POSITIONS)
        and safe_float(policy.get("max_margin_usage_ratio")) == HARD_MARGIN_CAP_RATIO
        and boundaries.get("real_money_allowed") is False
        and boundaries.get("order_execution_allowed") is False
        and boundaries.get("order_request_construction_allowed") is False
        and boundaries.get("order_check_allowed") is False
        and boundaries.get("order_calc_allowed") is False
        and boundaries.get("manual_approval_required_before_any_future_demo_order") is True
    )


def validate_gate(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("gate_status") == "manual_approval_gate_dry_run_passed_non_actionable"
        and manifest.get("source_nature") == "live_data_shadow_signal"
        and manifest.get("manual_approval_allowed_now") is False
        and manifest.get("manual_approval_performed") is False
        and manifest.get("request_construction_allowed_now") is False
        and manifest.get("broker_request_constructed") is False
        and manifest.get("broker_payload_constructed") is False
        and manifest.get("order_object_constructed") is False
        and manifest.get("order_execution_allowed") is False
        and manifest.get("future_state_json_written") is False
    )


def validate_freshness(manifest: dict[str, Any]) -> bool:
    allowed = {
        "live_signal_freshness_fresh_current_or_latest_signal",
        "live_signal_freshness_fresh_within_horizon",
    }
    return (
        manifest.get("freshness_status") in allowed
        and manifest.get("is_fresh") is True
        and manifest.get("is_stale") is False
        and safe_float(manifest.get("bars_elapsed")) is not None
        and safe_float(manifest.get("bars_elapsed")) <= HORIZON_BARS
        and manifest.get("future_manual_approval_allowed_now") is False
        and manifest.get("request_construction_allowed_now") is False
    )


def validate_reconciliation(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("reconciliation_status") == "broker_local_reconciliation_clean_no_local_no_broker"
        and manifest.get("source_nature") == "live_data_shadow_signal"
        and int(manifest.get("broker_position_count_symbol", -1)) == 0
        and int(manifest.get("broker_pending_order_count_symbol", -1)) == 0
        and manifest.get("request_construction_allowed_now") is False
    )


def validate_margin(manifest: dict[str, Any]) -> bool:
    usage = safe_float(manifest.get("broker_margin_usage_ratio"))
    return (
        manifest.get("validation_status") == "broker_safe_margin_validation_available"
        and manifest.get("source_nature") == "live_data_shadow_signal"
        and manifest.get("account_mode_label") == "demo"
        and usage is not None
        and usage <= HARD_MARGIN_CAP_RATIO
        and manifest.get("spread_within_policy") is True
    )


def validate_duplicate(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("plan_status") == "duplicate_protection_plan_available_no_order"
        and manifest.get("source_nature") == "live_data_shadow_signal"
        and safe_float(manifest.get("max_open_positions")) == float(MAX_OPEN_POSITIONS)
        and manifest.get("plan_actionable") is False
    )


def validate_manual_plan(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("plan_status") == "manual_approval_kill_switch_plan_available_no_order"
        and manifest.get("source_nature") == "live_data_shadow_signal"
        and manifest.get("manual_approval_performed") is False
        and manifest.get("kill_switch_executed") is False
        and manifest.get("plan_actionable") is False
    )


def validate_future_request(manifest: dict[str, Any]) -> bool:
    false_flags = (
        "request_construction_allowed_now",
        "broker_request_constructed",
        "broker_payload_constructed",
        "order_object_constructed",
    )
    return (
        manifest.get("plan_status") == "future_request_construction_readiness_plan_available_no_order"
        and manifest.get("source_nature") == "live_data_shadow_signal"
        and all(manifest.get(flag) in (False, None) for flag in false_flags)
    )


def source_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "registry": Path(args.canonical_registry),
        "policy": Path(args.demo_execution_policy),
        "gate": Path(args.manual_approval_gate_dry_run_dir) / GATE_MANIFEST,
        "freshness": Path(args.live_signal_freshness_dir) / FRESHNESS_MANIFEST,
        "reconciliation": Path(args.broker_local_reconciliation_dir) / BROKER_RECON_MANIFEST,
        "margin": Path(args.broker_safe_margin_validation_dir) / MARGIN_MANIFEST,
        "margin_snapshot": Path(args.broker_safe_margin_validation_dir) / MARGIN_SNAPSHOT,
        "duplicate": Path(args.duplicate_protection_plan_dir) / DUPLICATE_MANIFEST,
        "manual_plan": Path(args.manual_approval_kill_switch_plan_dir) / MANUAL_PLAN_MANIFEST,
        "future_request": Path(args.future_request_readiness_plan_dir) / FUTURE_REQUEST_MANIFEST,
    }


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    paths = source_paths(args)
    inputs: dict[str, Any] = {"paths": paths, "errors": {}}
    for key, path in paths.items():
        data, error = read_json(path)
        inputs[key] = data
        inputs["errors"][key] = error
        if error:
            warnings.append(
                warning_row(
                    run_id=args.run_id,
                    warning_code=f"{key}_unreadable",
                    message=error,
                    source=path,
                    blocking_warning=True,
                )
            )
    return inputs


def determine_status(inputs: dict[str, Any]) -> str:
    errors = inputs["errors"]
    if errors["gate"] == "missing":
        return "blocked_missing_manual_approval_gate_dry_run"
    if any(error == "missing" for error in errors.values()):
        return "blocked_missing_manual_approval_gate_dry_run"
    if errors["registry"] or not validate_canonical_registry(inputs["registry"]):
        return "blocked_noncanonical_candidate"
    if errors["policy"] or not validate_demo_policy(inputs["policy"]):
        return "blocked_noncanonical_demo_execution_policy"
    if not validate_gate(inputs["gate"]):
        return "blocked_unacceptable_manual_approval_gate_status"
    if not validate_freshness(inputs["freshness"]):
        if inputs["freshness"].get("freshness_status") == "live_signal_freshness_stale_beyond_horizon":
            return "blocked_stale_signal"
        return "blocked_unacceptable_manual_approval_gate_status"
    if not validate_reconciliation(inputs["reconciliation"]):
        return "blocked_broker_local_reconciliation"
    if not validate_margin(inputs["margin"]):
        return "blocked_margin_policy"
    if not validate_duplicate(inputs["duplicate"]):
        return "blocked_duplicate_protection"
    if not validate_manual_plan(inputs["manual_plan"]) or not validate_future_request(inputs["future_request"]):
        return "blocked_unsafe_policy"
    return "manual_approval_record_schema_available_no_order"


def schema_field_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "field_name": name,
            "field_type": field_type,
            "required": True,
            "value_source": source,
            "validation_rule": rule,
            "safety_note": note,
        }
        for name, field_type, source, rule, note in SCHEMA_FIELDS
    ]


def binding_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    bindings = [
        ("one signal_time_server", "would-signal/freshness artifact", "must match bound live signal timestamp"),
        ("one signal_id", "future signal identity", "must be non-empty and unique for the signal"),
        ("one idempotency_key", "duplicate protection artifact", "must be non-empty and unique"),
        ("one would_signal_review_run_id", "would-signal review", "must bind exact upstream run"),
        ("one freshness_run_id", "freshness check", "must bind exact upstream run"),
        ("one broker_local_reconciliation_run_id", "broker/local reconciliation", "must bind exact upstream run"),
        ("one broker_safe_margin_validation_run_id", "margin validation", "must bind exact upstream run"),
        ("one duplicate_protection_run_id", "duplicate protection", "must bind exact upstream run"),
        ("one manual_approval_gate_dry_run_id", "manual approval gate dry-run", "must bind exact upstream run"),
        ("one future_request_readiness_run_id", "future request readiness", "must bind exact upstream run"),
        ("one kill_switch_plan_run_id", "manual approval/kill-switch plan", "must bind exact upstream run"),
        ("one candidate_id/symbol/timeframe/direction tuple", "canonical registry", "must match fixed candidate tuple"),
    ]
    return [
        {
            "run_id": args.run_id,
            "binding_name": name,
            "required": True,
            "source_artifact": source,
            "validation_rule": rule,
            "safety_note": "approval record must be rejected if binding is missing or changed",
        }
        for name, source, rule in bindings
    ]


def expiry_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rules = [
        ("explicit_approval_expiry_formula", "expiry", "approval_expiry_time_utc = signal_time_server + horizon_bars * timeframe_minutes; horizon_bars = 10, timeframe_minutes = 15, max_age_minutes = 150", "approval expires at or before signal_time_server + 150 minutes", False),
        ("expires_after_horizon_bars", "expiry", f"bars_elapsed exceeds {HORIZON_BARS}", "approval becomes expired", False),
        ("expires_when_newer_feature_makes_signal_stale", "expiry", "new GBPUSD M15 row makes signal stale", "approval becomes expired", False),
        ("expires_when_reconciliation_not_clean", "expiry", "broker/local reconciliation not clean", "approval becomes expired", False),
        ("expires_when_margin_validation_stale_or_unavailable", "expiry", "margin validation stale/unavailable", "approval becomes expired", False),
        ("expires_when_spread_exceeds_policy", "expiry", f"spread exceeds {MAX_SPREAD_POINTS} broker_points", "approval becomes expired", False),
        ("expires_when_duplicate_state_changes", "expiry", "idempotency or duplicate state changes", "approval becomes expired", False),
        ("expires_when_kill_switch_active", "expiry", "kill-switch becomes active", "approval becomes expired", False),
        ("manual_revocation_allowed", "revocation", "operator or safety module revokes approval", "approval becomes revoked", False),
        ("revoked_approval_cannot_be_reused", "revocation", "approval_revoked is true", "must create new record", False),
        ("expired_approval_cannot_be_reused", "expiry", "approval_status is expired", "must create new record", False),
        ("recreate_not_refresh_after_expiry_or_revocation", "expiry_revocation", "expired or revoked record exists", "new record required", False),
    ]
    return [
        {
            "run_id": args.run_id,
            "rule_name": name,
            "rule_type": rule_type,
            "trigger_condition": trigger,
            "effect": effect,
            "reuse_allowed": reuse,
            "safety_note": "approval must not be refreshed in-place",
        }
        for name, rule_type, trigger, effect, reuse in rules
    ]


def scope_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = [
        {
            "run_id": args.run_id,
            "scope_name": "future_request_construction_only",
            "scope_status": "only_allowed_positive_scope",
            "scope_effect": "may allow a future module to construct a request only after final pre-request rechecks",
            "allowed": True,
            "safety_note": "does not construct request in this schema module",
        }
    ]
    for scope in FORBIDDEN_SCOPES:
        rows.append(
            {
                "run_id": args.run_id,
                "scope_name": scope,
                "scope_status": "forbidden_scope",
                "scope_effect": "must never be authorized by this approval record",
                "allowed": False,
                "safety_note": "approval cannot override safety gates",
            }
        )
    negative_effects = [
        "approval does not construct a request",
        "approval does not authorize request construction unless post-approval/pre-request rechecks pass",
        "approval does not create a broker payload",
        "approval does not call order_check",
        "approval does not call order_send",
        "approval does not execute an order",
        "approval does not override kill-switch",
        "approval does not override stale signal",
        "approval does not override broker/local reconciliation",
        "approval does not override margin/risk/spread policy",
        "approval does not override duplicate protection",
    ]
    rows.extend(
        {
            "run_id": args.run_id,
            "scope_name": effect.replace(" ", "_"),
            "scope_status": "explicit_non_authorization",
            "scope_effect": effect,
            "allowed": False,
            "safety_note": "negative scope statement",
        }
        for effect in negative_effects
    )
    return rows


def recheck_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    rechecks = [
        ("signal still fresh", "freshness_status is fresh and bars_elapsed <= 10"),
        ("broker/local reconciliation still clean", "reconciliation_status is clean"),
        ("broker positions still zero for GBPUSD", "broker_position_count_symbol == 0"),
        ("broker pending orders still zero for GBPUSD", "broker_pending_order_count_symbol == 0"),
        ("margin validation still available and below hard cap", "broker_margin_usage_ratio <= 0.70"),
        ("spread still within policy", "spread_current_points <= 15 broker_points"),
        ("duplicate protection still clean", "idempotency and max-open gates pass"),
        ("kill-switch inactive", "kill_switch_executed is false and no kill condition active"),
        ("future state JSON status compatible", "state missing/flat and no pending/open state"),
        ("request construction still disabled until after approval record creation", "request_construction_allowed_now is false"),
    ]
    return [
        {
            "run_id": args.run_id,
            "recheck_name": name,
            "required_before": "future real approval record creation",
            "validation_rule": rule,
            "blocking_if_failed": True,
            "source_hint": "rerun/read current upstream evidence immediately before approval record creation",
        }
        for name, rule in rechecks
    ]


def block_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    blocks = [
        ("stale signal", "freshness_status stale or bars_elapsed > 10", "freshness artifact"),
        ("missing signal_id or idempotency_key", "signal_id/idempotency_key absent", "future signal identity/duplicate protection"),
        ("missing_signal_id", "signal_id absent and deterministic derivation unavailable", "signal id rule artifact"),
        ("missing_idempotency_key", "idempotency_key absent", "duplicate protection"),
        ("missing or non-live source", "source_nature != live_data_shadow_signal", "all upstream artifacts"),
        ("broker/local reconciliation not clean", "reconciliation_status not clean", "broker/local reconciliation"),
        ("broker positions or pending orders present", "positions/orders count > 0", "broker/local reconciliation"),
        ("margin above hard cap", "broker_margin_usage_ratio > 0.70", "margin validation"),
        ("spread above policy", "spread_current_points > 15 broker_points", "margin validation"),
        ("duplicate protection unavailable", "duplicate plan status not available", "duplicate protection"),
        ("kill-switch active", "kill-switch condition active", "kill-switch plan/current recheck"),
        ("unsafe demo policy", "request/execution/check/calc enabled", "demo execution policy"),
        ("future request readiness boundary unsafe", "request construction already allowed or payload exists", "future request readiness"),
        ("future state JSON exists in incompatible status", "state open/pending/malformed", "future state JSON"),
        ("missing audit path", "approval record output path unavailable", "future approval module"),
        ("missing operator identity reference", "operator_identity_ref absent", "future approval module"),
        ("missing_operator_identity_ref", "operator_identity_ref absent", "future approval module"),
        ("missing operator decision label", "operator_decision_label absent", "future approval module"),
        ("unknown_operator_decision_label", "operator decision label not listed in allowed labels artifact", "operator decision label artifact"),
        ("forbidden_operator_decision_label", "operator decision label maps to forbidden meaning", "operator decision label artifact"),
        ("missing_warning_acknowledgment_when_required", "non-execution or risk caveats require acknowledgment and acknowledgment is absent", "future approval module"),
        ("upstream_artifact_digest_mismatch", "bound upstream artifact digest differs from approval record digest binding", "upstream digest artifact"),
        ("upstream_artifact_replaced_after_schema", "required upstream artifact file changed after schema/design digest capture", "upstream digest artifact"),
        ("digest_algorithm_missing", "digest_algorithm absent or not SHA-256", "digest rule artifact"),
        ("canonical_serialization_missing", "canonical serialization rule absent or not canonical_json_sorted_keys_utf8_no_extra_whitespace", "digest rule artifact"),
        ("post_approval_pre_request_recheck_missing", "required post-approval/pre-request recheck result absent", "post-approval recheck artifact"),
        ("approval would imply execution", "approval_scope includes execution", "future approval module"),
        ("approval would imply request construction without final recheck", "request construction before final recheck", "future approval module"),
    ]
    return [
        {
            "run_id": args.run_id,
            "block_condition": name,
            "blocking_if_present": True,
            "validation_rule": rule,
            "source_hint": source,
            "safety_note": "approval record creation must be blocked if condition is present",
        }
        for name, rule, source in blocks
    ]


def audit_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    audits = [
        ("record must be immutable after creation except explicit revocation record", "immutable fields after creation"),
        ("record must include digest/hash over all bound upstream run IDs and critical fields", "digest required"),
        ("record must be stored separately from broker payload/request artifacts", "separate artifact path"),
        ("record must be human-readable", "JSON with clear field names"),
        ("record must be machine-parseable", "valid JSON schema-compatible object"),
        ("record must preserve no-order evidence", "no-order flags embedded"),
        ("record must preserve explicit not-execution language", "negative authorization fields true"),
        ("record must be rejected if any bound upstream artifact is stale or replaced", "bound run IDs/digest checked"),
    ]
    return [
        {
            "run_id": args.run_id,
            "audit_requirement": name,
            "required": True,
            "validation_rule": rule,
            "storage_note": "future approval record JSON",
            "safety_note": "auditability and idempotency requirement",
        }
        for name, rule in audits
    ]


def allowed_status_rows() -> list[dict[str, Any]]:
    terminal_statuses = {
        "rejected",
        "expired",
        "revoked",
        "blocked_stale_signal",
        "blocked_kill_switch",
        "blocked_broker_local_reconciliation",
        "blocked_margin_policy",
        "blocked_duplicate_protection",
        "blocked_unsafe_policy",
    }
    status_types = {
        "not_created": "initial",
        "pending_operator_review": "pending",
        "approved_for_future_request_construction_only": "conditional_positive",
        "rejected": "operator_terminal",
        "expired": "safety_terminal",
        "revoked": "operator_terminal",
        "blocked_stale_signal": "blocked_terminal",
        "blocked_kill_switch": "blocked_terminal",
        "blocked_broker_local_reconciliation": "blocked_terminal",
        "blocked_margin_policy": "blocked_terminal",
        "blocked_duplicate_protection": "blocked_terminal",
        "blocked_unsafe_policy": "blocked_terminal",
    }
    rows: list[dict[str, Any]] = []
    for status in ALLOWED_APPROVAL_STATUSES:
        rows.append(
            {
                "status": status,
                "status_type": status_types[status],
                "terminal": status in terminal_statuses,
                "reusable": False if status in terminal_statuses else status == "pending_operator_review",
                "permits_request_construction": "conditional_after_final_pre_request_rechecks" if status == "approved_for_future_request_construction_only" else "false",
                "permits_order_execution": False,
                "safety_note": "approval status never permits order execution",
            }
        )
    return rows


def operator_decision_rows() -> list[dict[str, Any]]:
    allowed = {
        "approve_for_future_request_construction_only": ("allowed_positive", "approved_for_future_request_construction_only", "conditional_after_final_pre_request_rechecks"),
        "reject_signal": ("allowed_terminal", "rejected", "false"),
        "revoke_prior_approval": ("allowed_terminal", "revoked", "false"),
        "acknowledge_warning_only": ("allowed_nonapproval", "", "false"),
        "no_decision": ("allowed_nonapproval", "", "false"),
    }
    forbidden = (
        "approve_trade",
        "approve_execution",
        "send_order",
        "execute_order",
        "bypass_checks",
        "ignore_stale_signal",
        "ignore_kill_switch",
        "ignore_margin_policy",
        "ignore_duplicate_protection",
        "ignore_broker_local_reconciliation",
    )
    rows = [
        {
            "label": label,
            "label_type": label_type,
            "allowed": True,
            "maps_to_approval_status": mapped,
            "permits_request_construction": permits_request,
            "permits_order_execution": False,
            "safety_note": "future creator must reject missing or unknown operator_decision_label",
        }
        for label, (label_type, mapped, permits_request) in allowed.items()
    ]
    rows.extend(
        {
            "label": label,
            "label_type": "forbidden_meaning",
            "allowed": False,
            "maps_to_approval_status": "",
            "permits_request_construction": "false",
            "permits_order_execution": False,
            "safety_note": "forbidden label meaning must block approval record creation",
        }
        for label in forbidden
    )
    return rows


def post_approval_recheck_rows() -> list[dict[str, Any]]:
    rechecks = [
        ("recheck_signal_freshness_still_fresh", "freshness_status fresh and bars_elapsed <= 10"),
        ("recheck_broker_local_reconciliation_clean", "broker/local reconciliation clean"),
        ("recheck_broker_positions_zero", "broker_position_count_symbol == 0"),
        ("recheck_broker_pending_orders_zero", "broker_pending_order_count_symbol == 0"),
        ("recheck_margin_validation_still_below_hard_cap", "broker_margin_usage_ratio <= 0.70"),
        ("recheck_spread_still_within_policy", "spread <= 15 broker_points"),
        ("recheck_duplicate_protection_still_clean", "idempotency and duplicate gates clean"),
        ("recheck_kill_switch_inactive", "kill-switch inactive"),
        ("recheck_approval_not_expired", "approval_status not expired and expiry time not passed"),
        ("recheck_approval_not_revoked", "approval_revoked is false"),
        ("recheck_approval_scope_future_request_construction_only", "approval_scope == future_request_construction_only"),
        ("recheck_idempotency_key_matches_approval_record", "idempotency_key matches approval record"),
        ("recheck_signal_id_matches_approval_record", "signal_id matches approval record"),
        ("recheck_no_future_state_incompatible_status", "future state absent/flat and compatible"),
        ("recheck_request_construction_policy_still_disabled_until_request_module", "policy still disables request construction until request module"),
        ("recheck_no_scheduler_loop_background", "no scheduler/loop/background path"),
        ("recheck_audit_path_available", "audit path available and separate from request payload"),
    ]
    return [
        {
            "recheck_name": name,
            "timing": "post_approval_pre_request",
            "required": True,
            "blocking_if_failed": True,
            "expected_value": expected,
            "safety_note": "approval alone is insufficient for request construction",
        }
        for name, expected in rechecks
    ]


def digest_rule_rows() -> list[dict[str, Any]]:
    rules = [
        ("approval_record_digest_algorithm", "SHA-256", "future approval record", True, "fixed digest algorithm"),
        ("approval_record_canonical_serialization", "canonical_json_sorted_keys_utf8_no_extra_whitespace", "future approval record", True, "canonical JSON with sorted keys, UTF-8, no extra whitespace"),
        ("upstream_artifact_digest_algorithm", "SHA-256", "upstream artifact files", True, "raw file bytes"),
        ("upstream_artifact_digest_scope", "raw_file_bytes_for_each_bound_upstream_artifact", "upstream artifact files", True, "future approval must bind or recompute equivalent digests"),
        ("digest_recompute_requirement", "record_hash_or_digest_excludes_record_hash_or_digest_field_itself", "future approval record", True, "prevents self-referential digest ambiguity"),
        ("digest_mismatch_block_rule", "digest mismatch blocks future request construction and requires manual investigation; replaced upstream artifact invalidates prior approval reuse", "approval/request path", True, "digest mismatch is a hard blocker"),
    ]
    return [
        {
            "rule_name": name,
            "rule_value": value,
            "applies_to": applies_to,
            "blocking_if_missing": blocking,
            "safety_note": note,
        }
        for name, value, applies_to, blocking, note in rules
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upstream_digest_rows(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    specs = [
        ("manual_approval_gate_dry_run_manifest", "gate", "gate_status"),
        ("live_signal_freshness_manifest", "freshness", "freshness_status"),
        ("broker_local_reconciliation_manifest", "reconciliation", "reconciliation_status"),
        ("broker_safe_margin_validation_manifest", "margin", "validation_status"),
        ("broker_safe_margin_validation_margin_snapshot", "margin_snapshot", "validation_status"),
        ("duplicate_protection_plan_manifest", "duplicate", "plan_status"),
        ("manual_approval_kill_switch_plan_manifest", "manual_plan", "plan_status"),
        ("future_request_readiness_plan_manifest", "future_request", "plan_status"),
    ]
    rows = []
    for upstream_name, key, status_field in specs:
        path = inputs["paths"][key]
        rows.append(
            {
                "upstream_name": upstream_name,
                "upstream_path": path,
                "upstream_run_id": inputs[key].get("run_id", ""),
                "upstream_status_field": status_field,
                "upstream_status_value": inputs[key].get(status_field, ""),
                "digest_algorithm": "SHA-256",
                "sha256_digest": sha256_file(path) if path.exists() else "",
                "required_for_future_approval_record": True,
                "safety_note": "future approval record must bind to this digest or recompute an equivalent digest",
            }
        )
    return rows


def signal_id_rule_rows() -> list[dict[str, Any]]:
    rules = [
        ("signal_id_required", "future real approval creator must require a non-empty signal_id", True, True, "missing signal_id blocks"),
        ("signal_id_primary_source", "would-signal/review artifact signal_id if present", True, True, "explicit source preferred"),
        ("signal_id_derivation_fallback", "deterministic SHA-256 over candidate_id + symbol + timeframe + direction + signal_time_server + entry_reference_price + sl_price + tp_price", True, True, "fallback is deterministic and machine-readable"),
        ("signal_id_missing_block_rule", "missing explicit signal_id and missing derivation inputs must block approval record creation", True, True, "no ambiguous signal approval"),
        ("signal_id_must_bind_to_idempotency_key", "signal_id must be included in idempotency/audit binding", True, True, "prevents duplicate or mismatched approval reuse"),
    ]
    return [
        {
            "rule_name": name,
            "rule_value": value,
            "required": required,
            "blocking_if_failed": blocking,
            "safety_note": note,
        }
        for name, value, required, blocking, note in rules
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
        "no_order_request_constructed": True,
        "no_broker_payload_constructed": True,
        "no_executable_order_object_constructed": True,
        "no_manual_approval_performed": True,
        "no_demo_broker_approval_performed": True,
        "no_future_approval_record_created": True,
        "no_future_state_json_written": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "evidence_label": "manual_approval_record_schema_design_only_no_order_boundary",
        "caveat": "schema_only_no_approval_no_request_no_execution",
    }


def recommended_next_step(status: str) -> str:
    if status == "manual_approval_record_schema_available_no_order":
        return "audit_manual_approval_record_schema_before_real_approval_or_stop"
    return "resolve_blocking_condition_before_manual_approval_record_design"


def add_status_warning(args: argparse.Namespace, warnings: list[dict[str, Any]], status: str) -> None:
    if status == "manual_approval_record_schema_available_no_order":
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="schema_available_design_only_no_approval_created",
                message="Manual approval record schema is available, but no approval record was created.",
                source=args.output_dir or DEFAULT_OUTPUT_ROOT,
                blocking_warning=False,
            )
        )
    else:
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code=status,
                message="Manual approval record schema design is blocked by source evidence or policy.",
                source=args.output_dir or DEFAULT_OUTPUT_ROOT,
                blocking_warning=True,
            )
        )


def write_report(path: Path, args: argparse.Namespace, status: str, inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Manual Approval Record Schema",
        "",
        "Artifact-only schema design for a future manual approval record.",
        "No manual approval was performed.",
        "No operator input was requested.",
        "No approval record was created.",
        "No future state JSON was written or created.",
        "No MT5 import or connection was performed.",
        "No broker/API query or broker state read was performed.",
        "No broker request, broker payload, or executable order object was constructed.",
        "No order send, check, calc, or history function was called.",
        "No order execution was performed.",
        "No database mutation, child script, scheduler, loop, or background task was performed.",
        "No strategy optimization or threshold tuning was performed.",
        "This schema is not demo approval and not a trading decision.",
        "",
        "## Inputs",
        "",
        f"- manual_approval_gate_dry_run_dir: `{args.manual_approval_gate_dry_run_dir}`",
        f"- live_signal_freshness_dir: `{args.live_signal_freshness_dir}`",
        f"- broker_local_reconciliation_dir: `{args.broker_local_reconciliation_dir}`",
        f"- broker_safe_margin_validation_dir: `{args.broker_safe_margin_validation_dir}`",
        f"- future_approval_record_json: `{args.future_approval_record_json}`",
        f"- future_state_json: `{args.future_state_json}`",
        "",
        "## Schema Result",
        "",
        f"- schema_status: `{status}`",
        f"- signal_time_server: `{inputs['gate'].get('signal_time_server', '')}`",
        f"- freshness_status: `{inputs['freshness'].get('freshness_status', '')}`",
        f"- broker_local_reconciliation_status: `{inputs['reconciliation'].get('reconciliation_status', '')}`",
        f"- broker_margin_validation_status: `{inputs['margin'].get('validation_status', '')}`",
        f"- broker_margin_usage_ratio: `{inputs['margin'].get('broker_margin_usage_ratio', '')}`",
        "",
        "## Schema Audit Patch",
        "",
        "- allowed approval statuses artifact: `written`",
        "- operator decision labels artifact: `written`",
        "- post-approval/pre-request rechecks artifact: `written`",
        "- digest rules artifact: `written`",
        "- upstream artifact digests artifact: `written`",
        "- signal_id rule artifact: `written`",
        "- digest_algorithm: `SHA-256`",
        "- canonical_serialization: `canonical_json_sorted_keys_utf8_no_extra_whitespace`",
        "- schema_patch_status: `schema_audit_gaps_closed_no_order`",
        "- approval_expiry_formula: `approval_expiry_time_utc = signal_time_server + horizon_bars * timeframe_minutes`",
        "",
        "## Boundary",
        "",
        "- future_approval_record_created: `false`",
        "- manual_approval_performed: `false`",
        "- request_construction_allowed_now: `false`",
        "- order_execution_allowed: `false`",
        "",
        "## Warnings",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{recommended_next_step(status)}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(path: Path, args: argparse.Namespace, output_dir: Path, status: str, inputs: dict[str, Any], paths: dict[str, Path], warnings: list[dict[str, Any]]) -> None:
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "created_at_utc": utc_now_text(),
        "output_dir": str(output_dir),
        "schema_status": status,
        "schema_patch_status": "schema_audit_gaps_closed_no_order",
        "candidate_id": inputs["registry"].get("candidate_id", CANDIDATE_ID),
        "symbol": inputs["registry"].get("symbol", CANDIDATE_SYMBOL),
        "timeframe": inputs["registry"].get("timeframe", CANDIDATE_TIMEFRAME),
        "direction": inputs["registry"].get("direction", CANDIDATE_DIRECTION),
        "source_nature": inputs["gate"].get("source_nature", ""),
        "signal_time_server": inputs["gate"].get("signal_time_server", ""),
        "freshness_status": inputs["freshness"].get("freshness_status", ""),
        "broker_local_reconciliation_status": inputs["reconciliation"].get("reconciliation_status", ""),
        "broker_margin_validation_status": inputs["margin"].get("validation_status", ""),
        "broker_margin_usage_ratio": safe_float(inputs["margin"].get("broker_margin_usage_ratio")),
        "manual_approval_gate_dry_run_status": inputs["gate"].get("gate_status", ""),
        "future_approval_record_json": str(args.future_approval_record_json),
        "future_approval_record_created": False,
        "future_state_json": str(args.future_state_json),
        "future_state_json_written": False,
        "approval_record_schema_actionable": False,
        "manual_approval_performed": False,
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
        "order_execution_allowed": False,
        "demo_approval_performed": False,
        "allowed_statuses_artifact_written": True,
        "operator_decision_labels_artifact_written": True,
        "post_approval_pre_request_rechecks_artifact_written": True,
        "digest_rules_artifact_written": True,
        "upstream_artifact_digests_artifact_written": True,
        "signal_id_rule_artifact_written": True,
        "digest_algorithm": "SHA-256",
        "canonical_serialization": "canonical_json_sorted_keys_utf8_no_extra_whitespace",
        "recommended_next_step": recommended_next_step(status),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "output_files": {key: str(value) for key, value in paths.items()},
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
        "no_manual_approval_performed": True,
        "no_demo_broker_approval_performed": True,
        "no_future_approval_record_created": True,
        "no_future_state_json_written": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_artifacts(args: argparse.Namespace, paths: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    inputs = load_inputs(args, warnings)
    status = determine_status(inputs)
    add_status_warning(args, warnings, status)
    write_csv(paths["fields"], schema_field_rows(args), FIELD_FIELDNAMES)
    write_csv(paths["bindings"], binding_rows(args), BINDING_FIELDNAMES)
    write_csv(paths["expiry"], expiry_rows(args), EXPIRY_FIELDNAMES)
    write_csv(paths["scope"], scope_rows(args), SCOPE_FIELDNAMES)
    write_csv(paths["rechecks"], recheck_rows(args), RECHECK_FIELDNAMES)
    write_csv(paths["blocks"], block_rows(args), BLOCK_FIELDNAMES)
    write_csv(paths["audit"], audit_rows(args), AUDIT_FIELDNAMES)
    write_csv(paths["allowed_statuses"], allowed_status_rows(), ALLOWED_STATUS_FIELDNAMES)
    write_csv(paths["operator_decisions"], operator_decision_rows(), OPERATOR_DECISION_FIELDNAMES)
    write_csv(paths["post_approval_rechecks"], post_approval_recheck_rows(), POST_APPROVAL_RECHECK_FIELDNAMES)
    write_csv(paths["digest_rules"], digest_rule_rows(), DIGEST_RULE_FIELDNAMES)
    write_csv(paths["upstream_digests"], upstream_digest_rows(inputs), UPSTREAM_DIGEST_FIELDNAMES)
    write_csv(paths["signal_id_rule"], signal_id_rule_rows(), SIGNAL_ID_RULE_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["no_order"], [no_order_evidence_row(args)], NO_ORDER_FIELDNAMES)
    write_report(paths["report"], args, status, inputs, warnings)
    write_manifest(paths["manifest"], args, output_dir, status, inputs, paths, warnings)
    return {"status": status, "warnings": warnings}


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    build_artifacts(args, paths, output_dir)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only manual approval record schema for the fixed candidate.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--manual-approval-gate-dry-run-dir", type=Path, default=DEFAULT_GATE_DRY_RUN_DIR)
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
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, csv.Error) as exc:
        print(f"Fixed-candidate manual approval record schema build failed: {exc}")
        return 1
    print("Fixed-candidate manual approval record schema build complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
