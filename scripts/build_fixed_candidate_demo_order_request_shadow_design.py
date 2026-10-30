"""Build an artifact-only future intent design for the fixed candidate.

The design reads an order shadow plan artifact and writes conceptual future
validation stages plus intent field descriptors. It does not query external
systems or databases, run child scripts, build broker-submit-ready structures,
or perform order operations.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_order_request_shadow_design"
DEFAULT_ORDER_SHADOW_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_order_shadow_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_order_shadow_plan_fixture_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_order_request_shadow_design"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_SYMBOL = "GBPUSD"
EXPECTED_TIMEFRAME = "M15"
EXPECTED_DIRECTION = "short"
EXPECTED_SPREAD_UNIT = "broker_points"
EXPECTED_MAX_SPREAD_POINTS = 15.0

SOURCE_MANIFEST = "fixed_candidate_demo_order_shadow_plan_manifest.json"
SOURCE_REPORT = "fixed_candidate_demo_order_shadow_plan_report.md"
SOURCE_MAIN_CSV = "fixed_candidate_demo_order_shadow_plan.csv"
SOURCE_REQUIREMENTS_CSV = "fixed_candidate_demo_order_shadow_plan_requirements.csv"
SOURCE_FUTURE_FIELDS_CSV = "fixed_candidate_demo_order_shadow_plan_future_fields.csv"
SOURCE_WARNINGS_CSV = "fixed_candidate_demo_order_shadow_plan_warnings.csv"

OUTPUT_MANIFEST = "fixed_candidate_demo_order_request_shadow_design_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_order_request_shadow_design_report.md"
OUTPUT_MAIN_CSV = "fixed_candidate_demo_order_request_shadow_design.csv"
OUTPUT_STAGES_CSV = "fixed_candidate_demo_order_request_shadow_design_validation_stages.csv"
OUTPUT_INTENT_FIELDS_CSV = "fixed_candidate_demo_order_request_shadow_design_future_intent_fields.csv"
OUTPUT_WARNINGS_CSV = "fixed_candidate_demo_order_request_shadow_design_warnings.csv"

TRUE_BOUNDARY_FIELDS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_demo_broker_approval_performed",
    "no_trading_decision_performed",
    "no_mt5_connection_performed",
    "no_broker_connection_performed",
    "no_account_query_performed",
    "no_symbol_query_performed",
    "no_db_query_performed",
    "no_db_mutation_performed",
    "no_child_scripts_executed",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
)
FALSE_BOUNDARY_FIELDS = (
    "future_order_path_allowed",
    "order_execution_allowed",
    "order_request_construction_allowed",
    "demo_broker_approval_performed",
    "actionable_signal",
)

MAIN_FIELDNAMES = [
    "run_id",
    "design_status",
    "source_nature",
    "source_plan_status",
    "candidate_id",
    "symbol",
    "timeframe",
    "direction",
    "time_server",
    "spread_unit",
    "max_spread_points",
    "entry_reference_price",
    "tp_price_preview",
    "sl_price_preview",
    "design_area",
    "observed_value",
    "expected_value",
    "design_result",
    "blocking_if_failed",
    "caveat",
    "recommended_next_step",
]
STAGE_FIELDNAMES = [
    "run_id",
    "stage_index",
    "stage_name",
    "required_before",
    "expected_inputs",
    "blocked_until",
    "can_run_now",
    "caveat",
]
INTENT_FIELDNAMES = [
    "run_id",
    "intent_field_name",
    "field_role",
    "expected_source",
    "required_before",
    "intent_field_only",
    "not_broker_payload",
    "not_constructed",
    "future_request_construction_allowed",
    "caveat",
]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]


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


def close_float(left: Any, right: float, tolerance: float = 1e-6) -> bool:
    left_float = safe_float(left)
    return left_float is not None and abs(left_float - right) <= tolerance


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
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
    except OSError as exc:
        return [], str(exc)


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


def default_output_dir(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / str(args.run_id)


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "main": output_dir / OUTPUT_MAIN_CSV,
        "stages": output_dir / OUTPUT_STAGES_CSV,
        "intent_fields": output_dir / OUTPUT_INTENT_FIELDS_CSV,
        "warnings": output_dir / OUTPUT_WARNINGS_CSV,
    }


def ensure_outputs_writable(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)


def canonical_registry_valid(registry: dict[str, Any]) -> bool:
    return (
        registry.get("candidate_id") == EXPECTED_CANDIDATE_ID
        and registry.get("symbol") == EXPECTED_SYMBOL
        and registry.get("timeframe") == EXPECTED_TIMEFRAME
        and registry.get("direction") == EXPECTED_DIRECTION
        and registry.get("spread_unit") == EXPECTED_SPREAD_UNIT
        and close_float(registry.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS)
    )


def boundary_ok(source: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for field in TRUE_BOUNDARY_FIELDS:
        if as_bool(source.get(field)) is not True:
            failures.append(field)
    for field in FALSE_BOUNDARY_FIELDS:
        if as_bool(source.get(field)) is not False:
            failures.append(field)
    return not failures, failures


def signal_preview_ok(source: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if source.get("symbol") != EXPECTED_SYMBOL:
        failures.append("symbol")
    if source.get("timeframe") != EXPECTED_TIMEFRAME:
        failures.append("timeframe")
    if source.get("direction") != EXPECTED_DIRECTION:
        failures.append("direction")
    if source.get("spread_unit") != EXPECTED_SPREAD_UNIT:
        failures.append("spread_unit")
    if not close_float(source.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS):
        failures.append("max_spread_points")
    entry = safe_float(source.get("entry_reference_price"))
    tp_preview = safe_float(source.get("tp_price_preview"))
    sl_preview = safe_float(source.get("sl_price_preview"))
    for name, value in (
        ("entry_reference_price", entry),
        ("tp_price_preview", tp_preview),
        ("sl_price_preview", sl_preview),
    ):
        if value is None or value <= 0:
            failures.append(name)
    if entry is not None and tp_preview is not None and not tp_preview < entry:
        failures.append("short_tp_below_entry")
    if entry is not None and sl_preview is not None and not sl_preview > entry:
        failures.append("short_sl_above_entry")
    return not failures, failures


def recommended_next_step(design_status: str) -> str:
    if design_status == "order_request_shadow_design_fixture_only":
        return "wait_for_live_shadow_signal_or_continue_no_order_monitoring"
    if design_status == "order_request_shadow_design_available_no_order":
        return "build_fixed_candidate_demo_risk_volume_shadow_plan"
    if design_status == "hold_no_order_shadow_plan_available":
        return "continue_no_order_monitoring"
    return "fix_order_request_shadow_design_blocker"


def determine_design_status(
    *,
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_error: str,
    source: dict[str, Any],
    source_error: str,
    boundary_safe: bool,
    preview_safe: bool,
    warnings: list[dict[str, Any]],
) -> str:
    if registry_error == "missing" or source_error == "missing":
        if registry_error == "missing":
            add_warning(warnings, args=args, warning_code="canonical_registry_missing", message="Canonical registry is missing.", source=args.canonical_registry, blocking_warning=True)
        if source_error == "missing":
            add_warning(warnings, args=args, warning_code="order_shadow_plan_manifest_missing", message="Order shadow plan manifest is missing.", source=Path(args.order_shadow_plan_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_missing_required_artifact"
    if registry_error or source_error:
        add_warning(warnings, args=args, warning_code="required_input_unreadable", message="A required JSON input is unreadable.", source=args.order_shadow_plan_dir, blocking_warning=True)
        return "blocked_unreadable_input"
    if not canonical_registry_valid(registry):
        add_warning(warnings, args=args, warning_code="canonical_registry_boundary_mismatch", message="Canonical registry does not match fixed-candidate spread15 boundaries.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_by_config_boundary"
    source_status = str(source.get("plan_status") or "")
    source_nature = str(source.get("source_nature") or "")
    if source_status == "hold_no_would_signal_for_order_shadow_plan":
        return "hold_no_order_shadow_plan_available"
    if source_status.startswith("blocked_"):
        add_warning(warnings, args=args, warning_code="order_shadow_plan_status_blocked", message=f"Order shadow plan status is blocked: {source_status}", source=Path(args.order_shadow_plan_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_by_order_shadow_plan_status"
    if source_status not in {"order_shadow_plan_fixture_only", "order_shadow_plan_available_no_order"}:
        add_warning(warnings, args=args, warning_code="order_shadow_plan_status_not_acceptable", message=f"Order shadow plan status is not acceptable: {source_status}", source=Path(args.order_shadow_plan_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_by_order_shadow_plan_status"
    if source_nature not in {"synthetic_fixture", "live_data_shadow_signal"}:
        add_warning(warnings, args=args, warning_code="source_nature_unclear", message="Order shadow plan source nature is unclear.", source=Path(args.order_shadow_plan_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "hold_source_nature_unclear"
    if not boundary_safe:
        add_warning(warnings, args=args, warning_code="no_request_boundary_violation", message="No-order/no-request boundary fields are missing or unsafe.", source=Path(args.order_shadow_plan_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_by_no_order_boundary"
    if not preview_safe:
        add_warning(warnings, args=args, warning_code="signal_preview_invalid", message="Order shadow plan preview fields are missing or inconsistent.", source=Path(args.order_shadow_plan_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_by_signal_preview"
    if as_bool(source.get("order_request_construction_allowed")) is not False or as_bool(source.get("future_order_path_allowed")) is not False:
        add_warning(warnings, args=args, warning_code="request_construction_boundary_violation", message="Source did not preserve request-construction boundary.", source=Path(args.order_shadow_plan_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_by_request_construction_boundary"
    if source_status == "order_shadow_plan_fixture_only":
        return "order_request_shadow_design_fixture_only"
    return "order_request_shadow_design_available_no_order"


def source_nature_for(source: dict[str, Any], design_status: str) -> str:
    if design_status == "order_request_shadow_design_fixture_only":
        return "synthetic_fixture"
    if design_status == "order_request_shadow_design_available_no_order":
        return "live_data_shadow_signal"
    return str(source.get("source_nature") or "unclear")


def context(args: argparse.Namespace, source: dict[str, Any], registry: dict[str, Any], design_status: str, source_nature: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "design_status": design_status,
        "source_nature": source_nature,
        "source_plan_status": source.get("plan_status", ""),
        "candidate_id": registry.get("candidate_id", EXPECTED_CANDIDATE_ID),
        "symbol": registry.get("symbol", EXPECTED_SYMBOL),
        "timeframe": registry.get("timeframe", EXPECTED_TIMEFRAME),
        "direction": registry.get("direction", EXPECTED_DIRECTION),
        "time_server": source.get("time_server", ""),
        "spread_unit": source.get("spread_unit", ""),
        "max_spread_points": source.get("max_spread_points", ""),
        "entry_reference_price": source.get("entry_reference_price", ""),
        "tp_price_preview": source.get("tp_price_preview", ""),
        "sl_price_preview": source.get("sl_price_preview", ""),
        "recommended_next_step": recommended_next_step(design_status),
    }


def design_rows(ctx: dict[str, Any], source: dict[str, Any]) -> list[dict[str, Any]]:
    items = [
        ("source_plan_status", source.get("plan_status", ""), "acceptable order shadow plan status", "checked", True, "source artifact controls scope"),
        ("source_nature", ctx["source_nature"], "synthetic_fixture or live_data_shadow_signal", "checked", True, "fixture remains non-actionable"),
        ("signal_preview_reference", "entry/tp/sl preview fields", "present and geometrically valid", "checked", True, "preview only"),
        ("conceptual_order_intent", "future intent descriptors", "not broker payload", "planned", True, "no executable object"),
        ("direction_short_only", ctx["direction"], "short", "checked", True, "fixed candidate only"),
        ("entry_reference_from_signal_close", source.get("entry_reference_price", ""), "from would-signal review", "checked", True, "not an execution price"),
        ("tp_from_signal_preview", source.get("tp_price_preview", ""), "from would-signal review", "checked", True, "future validation required"),
        ("sl_from_signal_preview", source.get("sl_price_preview", ""), "from would-signal review", "checked", True, "future validation required"),
        ("volume_blocked_until_risk_module", "not computed", "risk-volume shadow module required", "blocked", True, "no calculation call here"),
        ("account_reconfirmation_required", "not checked", "future demo account read-only confirmation", "required", True, "no account query here"),
        ("symbol_contract_reconfirmation_required", "not checked", "future symbol contract read-only confirmation", "required", True, "no symbol query here"),
        ("spread_recheck_required", source.get("spread", ""), "<= 15 broker_points at future stage", "required", True, "signal can age"),
        ("stop_level_distance_check_required", "not checked", "future stop distance compatibility", "required", True, "future contract evidence"),
        ("duplicate_protection_required", "not checked", "future duplicate guard", "required", True, "idempotency needed"),
        ("idempotency_required", "not checked", "future idempotency key", "required", True, "state dependency"),
        ("local_state_write_plan_required", "not defined", "future state write design", "required", True, "no state write here"),
        ("broker_state_reconciliation_required", "not checked", "future reconciliation evidence", "required", True, "future read-only evidence"),
        ("kill_switch_required", "not checked", "future kill-switch clear state", "required", True, "future safety module"),
        ("manual_approval_required", source.get("manual_review_required", ""), "manual approval gate required", "required", True, "no automatic advance"),
        ("audit_log_required", "not defined", "future audit log destination", "required", True, "future module"),
        ("broker_payload_forbidden", True, True, "confirmed", True, "no broker payload built"),
        ("order_check_forbidden", True, True, "confirmed", True, "no validation call"),
        ("order_calc_forbidden", True, True, "confirmed", True, "no calculation call"),
        ("order_send_forbidden", True, True, "confirmed", True, "no execution call"),
        ("no_real_money_boundary", True, True, "confirmed", True, "real-money use remains forbidden"),
    ]
    return [
        {
            **ctx,
            "design_area": area,
            "observed_value": observed,
            "expected_value": expected,
            "design_result": result,
            "blocking_if_failed": blocking,
            "caveat": caveat,
        }
        for area, observed, expected, result, blocking, caveat in items
    ]


def validation_stage_rows(run_id: str) -> list[dict[str, Any]]:
    rows = [
        (1, "stage_01_live_signal_source_validation", "future design", "live shadow signal and would-signal review", "live-data shadow artifact", True, "fixture may satisfy format only"),
        (2, "stage_02_demo_environment_reconfirmation", "future design", "read-only demo environment evidence", "demo account and terminal check", False, "requires future read-only check"),
        (3, "stage_03_symbol_contract_reconfirmation", "future design", "current symbol contract evidence", "symbol contract check", False, "requires future read-only check"),
        (4, "stage_04_spread_and_stops_recheck", "future design", "current spread and stop-level evidence", "spread/stops check", False, "requires future read-only check"),
        (5, "stage_05_risk_volume_shadow_calculation", "future design", "risk cap and volume constraints", "risk-volume shadow plan", False, "no calculation call here"),
        (6, "stage_06_duplicate_and_state_reconciliation", "future design", "local and broker state evidence", "state reconciliation plan", False, "requires future state module"),
        (7, "stage_07_kill_switch_and_manual_approval", "future design", "kill-switch state and manual approval", "operator gate", False, "human gate required"),
        (8, "stage_08_future_request_construction_gate", "future request design", "all previous stages complete", "explicit later approval", False, "not allowed here"),
        (9, "stage_09_future_order_check_gate", "future validation", "constructed future design and explicit later approval", "future module", False, "not allowed here"),
        (10, "stage_10_future_execution_gate", "future execution", "all checks plus explicit manual approval", "future module", False, "not allowed here"),
    ]
    return [
        {
            "run_id": run_id,
            "stage_index": index,
            "stage_name": name,
            "required_before": required_before,
            "expected_inputs": expected_inputs,
            "blocked_until": blocked_until,
            "can_run_now": can_run_now,
            "caveat": caveat,
        }
        for index, name, required_before, expected_inputs, blocked_until, can_run_now, caveat in rows
    ]


def intent_field_rows(run_id: str) -> list[dict[str, Any]]:
    fields = [
        ("intent_symbol", "instrument descriptor", "canonical registry"),
        ("intent_direction", "direction descriptor", "canonical registry"),
        ("intent_order_side", "side descriptor", "future policy mapping"),
        ("intent_entry_reference_price", "entry reference descriptor", "would-signal review"),
        ("intent_tp_price", "target descriptor", "would-signal review"),
        ("intent_sl_price", "protective stop descriptor", "would-signal review"),
        ("intent_risk_percent", "risk cap descriptor", "canonical config"),
        ("intent_volume_lots", "future volume descriptor", "future risk-volume module"),
        ("intent_timeframe", "timeframe descriptor", "canonical registry"),
        ("intent_signal_time_server", "signal time descriptor", "would-signal review"),
        ("intent_signal_id", "future state descriptor", "future state module"),
        ("intent_idempotency_key", "duplicate guard descriptor", "future state module"),
        ("intent_manual_approval_token", "manual gate descriptor", "operator checkpoint"),
        ("intent_audit_id", "audit descriptor", "future audit module"),
        ("intent_expiry_policy", "expiry descriptor", "future policy module"),
        ("intent_max_spread_points", "spread cap descriptor", "canonical registry"),
        ("intent_kill_switch_state", "safety state descriptor", "future safety module"),
        ("intent_duplicate_check_state", "duplicate-check descriptor", "future state module"),
        ("intent_reconciliation_state", "reconciliation descriptor", "future reconciliation module"),
    ]
    return [
        {
            "run_id": run_id,
            "intent_field_name": name,
            "field_role": role,
            "expected_source": source,
            "required_before": "any future request-design implementation",
            "intent_field_only": True,
            "not_broker_payload": True,
            "not_constructed": True,
            "future_request_construction_allowed": False,
            "caveat": "conceptual descriptor only",
        }
        for name, role, source in fields
    ]


def manifest_data(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    ctx: dict[str, Any],
    stages: list[dict[str, Any]],
    intent_fields: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "canonical_registry_path": str(args.canonical_registry),
        "order_shadow_plan_dir": str(args.order_shadow_plan_dir),
        "design_status": ctx["design_status"],
        "source_nature": ctx["source_nature"],
        "source_plan_status": ctx["source_plan_status"],
        "candidate_id": ctx["candidate_id"],
        "symbol": ctx["symbol"],
        "timeframe": ctx["timeframe"],
        "direction": ctx["direction"],
        "time_server": ctx["time_server"],
        "spread_unit": ctx["spread_unit"],
        "max_spread_points": ctx["max_spread_points"],
        "entry_reference_price": ctx["entry_reference_price"],
        "tp_price_preview": ctx["tp_price_preview"],
        "sl_price_preview": ctx["sl_price_preview"],
        "design_actionable": False,
        "future_request_construction_allowed": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "demo_broker_approval_performed": False,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_trading_decision_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_db_query_performed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "broker_payload_forbidden": True,
        "executable_request_object_forbidden": True,
        "validation_stage_count": len(stages),
        "future_intent_field_count": len(intent_fields),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "recommended_next_step": ctx["recommended_next_step"],
    }


def write_report(path: Path, *, ctx: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Order Request Shadow Design",
        "",
        "Artifact-only order request shadow design. This is a conceptual future-intent design, not a broker request dictionary.",
        "No executable request object was created.",
        "No MT5, broker, API, account, or symbol query was performed.",
        "No database query or mutation was performed.",
        "No order execution was performed.",
        "No order_check or order_calc call was performed.",
        "No scheduler, loop, or background task was added.",
        "This is not demo broker approval and not a trading decision.",
    ]
    if ctx["source_nature"] == "synthetic_fixture":
        lines.append("The source is a synthetic fixture and is non-actionable.")
    if ctx["source_nature"] == "live_data_shadow_signal":
        lines.append("The source is live-data shadow evidence, but no order approval is given.")
    lines.extend(
        [
            "",
            "## Design Summary",
            "",
            f"- design_status: `{ctx['design_status']}`",
            f"- source_plan_status: `{ctx['source_plan_status']}`",
            f"- source_nature: `{ctx['source_nature']}`",
            f"- entry_reference_price: `{ctx['entry_reference_price']}`",
            f"- tp_price_preview: `{ctx['tp_price_preview']}`",
            f"- sl_price_preview: `{ctx['sl_price_preview']}`",
            "",
            "## Validation Stages",
            "",
            "Future broker/account/symbol checks, risk-volume work, request construction, order_check, and execution gates are blocked in this module.",
            "",
            "## Future Intent Fields",
            "",
            "Future intent fields are descriptors only. They are not broker payload fields and are not constructed into any executable object.",
            "",
            "## Recommended Next Step",
            "",
            f"`{ctx['recommended_next_step']}`",
            "",
            "## Warnings",
            "",
        ]
    )
    if warnings:
        lines.extend(f"- {row['warning_code']}: {row['message']}" for row in warnings)
    else:
        lines.append("- none")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = default_output_dir(args)
    paths = output_paths(output_dir)
    ensure_outputs_writable(paths, bool(args.overwrite))

    registry, registry_error = read_json(Path(args.canonical_registry))
    source_dir = Path(args.order_shadow_plan_dir)
    source, source_error = read_json(source_dir / SOURCE_MANIFEST)
    source_warnings, _ = read_csv_rows(source_dir / SOURCE_WARNINGS_CSV)
    read_csv_rows(source_dir / SOURCE_REQUIREMENTS_CSV)
    read_csv_rows(source_dir / SOURCE_FUTURE_FIELDS_CSV)
    warnings = preserve_source_warnings(args, source_warnings, source_dir / SOURCE_WARNINGS_CSV)
    boundary_safe, boundary_failures = boundary_ok(source)
    preview_safe, preview_failures = signal_preview_ok(source)
    design_status = determine_design_status(
        args=args,
        registry=registry,
        registry_error=registry_error,
        source=source,
        source_error=source_error,
        boundary_safe=boundary_safe,
        preview_safe=preview_safe,
        warnings=warnings,
    )
    if boundary_failures and design_status == "blocked_by_no_order_boundary":
        add_warning(warnings, args=args, warning_code="no_request_boundary_failed_fields", message=f"Unsafe no-request fields: {boundary_failures}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
    if preview_failures and design_status == "blocked_by_signal_preview":
        add_warning(warnings, args=args, warning_code="signal_preview_failed_fields", message=f"Invalid preview fields: {preview_failures}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
    source_nature = source_nature_for(source, design_status)
    ctx = context(args, source, registry, design_status, source_nature)
    rows = design_rows(ctx, source)
    stages = validation_stage_rows(args.run_id)
    intent_fields = intent_field_rows(args.run_id)

    write_csv(paths["main"], rows, MAIN_FIELDNAMES)
    write_csv(paths["stages"], stages, STAGE_FIELDNAMES)
    write_csv(paths["intent_fields"], intent_fields, INTENT_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_json(paths["manifest"], manifest_data(args=args, output_dir=output_dir, ctx=ctx, stages=stages, intent_fields=intent_fields, warnings=warnings))
    write_report(paths["report"], ctx=ctx, warnings=warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only fixed-candidate demo order request shadow design.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--order-shadow-plan-dir", type=Path, default=DEFAULT_ORDER_SHADOW_PLAN_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        build_outputs(args)
    except Exception as exc:
        print(f"Fixed-candidate demo order request shadow design failed: {exc}")
        return 1
    print("Fixed-candidate demo order request shadow design complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
