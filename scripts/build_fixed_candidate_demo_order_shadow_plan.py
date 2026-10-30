"""Build an artifact-only demo order shadow plan for the fixed candidate.

This module reads a would-signal review artifact and writes a plan for future
design work. It does not query external systems, databases, or child scripts.
It does not create broker-submit-ready payloads and does not perform any order
operation.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_order_shadow_plan"
DEFAULT_WOULD_SIGNAL_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_would_signal_review"
    / "gbpusd_short_h10_1_5_off_hours_demo_would_signal_review_fixture_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_order_shadow_plan"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_SYMBOL = "GBPUSD"
EXPECTED_TIMEFRAME = "M15"
EXPECTED_DIRECTION = "short"
EXPECTED_SESSION = "Off_hours"
EXPECTED_SPREAD_UNIT = "broker_points"
EXPECTED_MAX_SPREAD_POINTS = 15.0
EXPECTED_CLOSE_BUCKET = "high_tercile"
EXPECTED_VOLUME_BUCKET = "mid_tercile"

SOURCE_MANIFEST = "fixed_candidate_demo_would_signal_review_manifest.json"
SOURCE_REPORT = "fixed_candidate_demo_would_signal_review_report.md"
SOURCE_MAIN_CSV = "fixed_candidate_demo_would_signal_review.csv"
SOURCE_CHECKLIST_CSV = "fixed_candidate_demo_would_signal_review_checklist.csv"
SOURCE_WARNINGS_CSV = "fixed_candidate_demo_would_signal_review_warnings.csv"

OUTPUT_MANIFEST = "fixed_candidate_demo_order_shadow_plan_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_order_shadow_plan_report.md"
OUTPUT_MAIN_CSV = "fixed_candidate_demo_order_shadow_plan.csv"
OUTPUT_REQUIREMENTS_CSV = "fixed_candidate_demo_order_shadow_plan_requirements.csv"
OUTPUT_FUTURE_FIELDS_CSV = "fixed_candidate_demo_order_shadow_plan_future_fields.csv"
OUTPUT_WARNINGS_CSV = "fixed_candidate_demo_order_shadow_plan_warnings.csv"

NO_ORDER_TRUE_FIELDS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_demo_broker_approval_performed",
    "no_trading_decision_performed",
)
NO_ORDER_FALSE_FIELDS = (
    "order_execution_allowed",
    "order_request_construction_allowed",
    "demo_broker_approval_performed",
    "actionable_signal",
)

MAIN_FIELDNAMES = [
    "run_id",
    "plan_status",
    "source_nature",
    "review_status",
    "candidate_id",
    "symbol",
    "timeframe",
    "direction",
    "time_server",
    "session_observed",
    "spread",
    "spread_unit",
    "max_spread_points",
    "entry_reference_price",
    "tp_price_preview",
    "sl_price_preview",
    "plan_area",
    "observed_value",
    "expected_value",
    "plan_result",
    "blocking_if_failed",
    "caveat",
    "recommended_next_step",
]
REQUIREMENT_FIELDNAMES = [
    "run_id",
    "requirement_area",
    "requirement_name",
    "required_before",
    "expected_condition",
    "blocking_if_failed",
    "future_module",
    "caveat",
]
FUTURE_FIELD_FIELDNAMES = [
    "run_id",
    "future_field_name",
    "field_role",
    "expected_source",
    "required_before",
    "future_field_only",
    "not_constructed",
    "broker_request_field",
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
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(payload, dict):
        return {}, "JSON root must be an object"
    return payload, ""


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], "missing"
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), ""
    except OSError as exc:
        return [], str(exc)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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


def preserve_source_warnings(args: argparse.Namespace, source_rows: list[dict[str, str]], source_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in source_rows:
        rows.append(
            {
                "run_id": args.run_id,
                "warning_code": f"source_{row.get('warning_code', 'warning')}",
                "severity": row.get("severity", "warning"),
                "message": row.get("message", ""),
                "source": row.get("source") or str(source_path),
                "blocking_warning": as_bool(row.get("blocking_warning")) is True,
            }
        )
    return rows


def default_output_dir(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / str(args.run_id)


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "main": output_dir / OUTPUT_MAIN_CSV,
        "requirements": output_dir / OUTPUT_REQUIREMENTS_CSV,
        "future_fields": output_dir / OUTPUT_FUTURE_FIELDS_CSV,
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


def no_order_boundary_ok(manifest: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for field in NO_ORDER_TRUE_FIELDS:
        if as_bool(manifest.get(field)) is not True:
            failures.append(field)
    for field in NO_ORDER_FALSE_FIELDS:
        if as_bool(manifest.get(field)) is not False:
            failures.append(field)
    return not failures, failures


def signal_preview_ok(manifest: dict[str, Any], source_nature: str) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if manifest.get("symbol") != EXPECTED_SYMBOL:
        failures.append("symbol")
    if manifest.get("timeframe") != EXPECTED_TIMEFRAME:
        failures.append("timeframe")
    if manifest.get("direction") != EXPECTED_DIRECTION:
        failures.append("direction")
    if source_nature != "synthetic_fixture" and manifest.get("session_observed") != EXPECTED_SESSION:
        failures.append("session_observed")
    if manifest.get("spread_unit") != EXPECTED_SPREAD_UNIT:
        failures.append("spread_unit")
    if not close_float(manifest.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS):
        failures.append("max_spread_points")
    spread = safe_float(manifest.get("spread"))
    if spread is None or spread > EXPECTED_MAX_SPREAD_POINTS:
        failures.append("spread")
    if manifest.get("close_to_ma_fast_atr_20_bucket") != EXPECTED_CLOSE_BUCKET:
        failures.append("close_to_ma_fast_atr_20_bucket")
    if manifest.get("tick_volume_percentile_100_bucket") != EXPECTED_VOLUME_BUCKET:
        failures.append("tick_volume_percentile_100_bucket")
    entry = safe_float(manifest.get("entry_reference_price"))
    tp_price = safe_float(manifest.get("tp_price_preview"))
    sl_price = safe_float(manifest.get("sl_price_preview"))
    close = safe_float(manifest.get("close"))
    atr_20 = safe_float(manifest.get("atr_20"))
    for name, value in (
        ("close", close),
        ("atr_20", atr_20),
        ("entry_reference_price", entry),
        ("tp_price_preview", tp_price),
        ("sl_price_preview", sl_price),
    ):
        if value is None or value <= 0:
            failures.append(name)
    if entry is not None and tp_price is not None and not tp_price < entry:
        failures.append("short_tp_below_entry")
    if entry is not None and sl_price is not None and not sl_price > entry:
        failures.append("short_sl_above_entry")
    return not failures, failures


def recommended_next_step(plan_status: str) -> str:
    if plan_status == "order_shadow_plan_fixture_only":
        return "wait_for_live_shadow_signal_or_continue_no_order_monitoring"
    if plan_status == "order_shadow_plan_available_no_order":
        return "build_fixed_candidate_demo_order_request_shadow_design"
    if plan_status == "hold_no_would_signal_for_order_shadow_plan":
        return "continue_no_order_monitoring"
    return "fix_order_shadow_plan_blocker"


def determine_plan_status(
    *,
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_error: str,
    source_manifest: dict[str, Any],
    source_error: str,
    no_order_ok: bool,
    signal_ok: bool,
    warnings: list[dict[str, Any]],
) -> str:
    if registry_error == "missing" or source_error == "missing":
        if registry_error == "missing":
            add_warning(warnings, args=args, warning_code="canonical_registry_missing", message="Canonical registry is missing.", source=args.canonical_registry, blocking_warning=True)
        if source_error == "missing":
            add_warning(warnings, args=args, warning_code="would_signal_review_manifest_missing", message="Would-signal review manifest is missing.", source=Path(args.would_signal_review_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_missing_required_artifact"
    if registry_error or source_error:
        add_warning(warnings, args=args, warning_code="required_input_unreadable", message="A required JSON input is unreadable.", source=args.would_signal_review_dir, blocking_warning=True)
        return "blocked_unreadable_input"
    if not canonical_registry_valid(registry):
        add_warning(warnings, args=args, warning_code="canonical_registry_boundary_mismatch", message="Canonical registry does not match fixed-candidate spread15 boundaries.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_by_config_boundary"
    review_status = str(source_manifest.get("review_status") or "")
    if review_status == "hold_no_would_signal_to_review":
        return "hold_no_would_signal_for_order_shadow_plan"
    if review_status.startswith("blocked_"):
        add_warning(warnings, args=args, warning_code="would_signal_review_status_blocked", message=f"Would-signal review status is blocked: {review_status}", source=Path(args.would_signal_review_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_by_would_signal_review_status"
    if review_status not in {"would_signal_review_fixture_only", "would_signal_review_available_no_order"}:
        add_warning(warnings, args=args, warning_code="would_signal_review_status_not_acceptable", message=f"Would-signal review status is not acceptable: {review_status}", source=Path(args.would_signal_review_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_by_would_signal_review_status"
    if not no_order_ok:
        add_warning(warnings, args=args, warning_code="no_order_boundary_violation", message="Would-signal review no-order boundary is missing or unsafe.", source=Path(args.would_signal_review_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_by_no_order_boundary"
    if not signal_ok:
        add_warning(warnings, args=args, warning_code="signal_preview_invalid", message="Would-signal preview is missing or inconsistent.", source=Path(args.would_signal_review_dir) / SOURCE_MANIFEST, blocking_warning=True)
        return "blocked_by_signal_preview"
    if review_status == "would_signal_review_fixture_only":
        if as_bool(source_manifest.get("fixture_not_actionable")) is not True:
            add_warning(warnings, args=args, warning_code="fixture_actionability_boundary_missing", message="Fixture review did not preserve non-actionable fixture boundary.", source=Path(args.would_signal_review_dir) / SOURCE_MANIFEST, blocking_warning=True)
            return "blocked_by_fixture_actionability_boundary"
        return "order_shadow_plan_fixture_only"
    return "order_shadow_plan_available_no_order"


def source_nature_for(source_manifest: dict[str, Any], plan_status: str) -> str:
    if plan_status == "order_shadow_plan_fixture_only":
        return "synthetic_fixture"
    if plan_status == "order_shadow_plan_available_no_order":
        return "live_data_shadow_signal"
    value = str(source_manifest.get("source_nature") or "")
    return value or "unclear"


def main_context(args: argparse.Namespace, manifest: dict[str, Any], registry: dict[str, Any], plan_status: str, source_nature: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "plan_status": plan_status,
        "source_nature": source_nature,
        "review_status": manifest.get("review_status", ""),
        "candidate_id": registry.get("candidate_id", EXPECTED_CANDIDATE_ID),
        "symbol": registry.get("symbol", EXPECTED_SYMBOL),
        "timeframe": registry.get("timeframe", EXPECTED_TIMEFRAME),
        "direction": registry.get("direction", EXPECTED_DIRECTION),
        "time_server": manifest.get("time_server", ""),
        "session_observed": manifest.get("session_observed", ""),
        "spread": manifest.get("spread", ""),
        "spread_unit": manifest.get("spread_unit", ""),
        "max_spread_points": manifest.get("max_spread_points", ""),
        "entry_reference_price": manifest.get("entry_reference_price", ""),
        "tp_price_preview": manifest.get("tp_price_preview", ""),
        "sl_price_preview": manifest.get("sl_price_preview", ""),
        "recommended_next_step": recommended_next_step(plan_status),
    }


def plan_rows(context: dict[str, Any], manifest: dict[str, Any], plan_status: str) -> list[dict[str, Any]]:
    definitions = [
        ("source_review_status", manifest.get("review_status", ""), "acceptable would-signal review status", "checked", True, "input review governs plan scope"),
        ("source_nature", context["source_nature"], "synthetic_fixture or live_data_shadow_signal", "checked", True, "fixture stays non-actionable"),
        ("signal_preview_available", "entry/tp/sl preview fields", "preview fields available and geometrically valid", "checked", True, "preview only"),
        ("no_order_boundary_confirmed", "no-order flags safe", "execution and request construction remain forbidden", "checked", True, "no broker payload exists"),
        ("fixture_non_actionable_boundary", manifest.get("fixture_not_actionable", ""), "true for fixture input", "checked", False, "only applies to fixture"),
        ("manual_approval_required", manifest.get("manual_review_required", ""), "true before future design stage", "planned", True, "human gate required later"),
        ("demo_account_confirmation_required", "not checked here", "future read-only demo confirmation", "required", True, "artifact-only module"),
        ("symbol_contract_confirmation_required", "not checked here", "future current symbol contract check", "required", True, "spread15 contract compatibility"),
        ("spread_recheck_required", manifest.get("spread", ""), "<= 15 broker_points at future check time", "required", True, "current artifact can age"),
        ("max_open_positions_required", "1", "max_open_positions=1", "required", True, "one-open-position rule"),
        ("duplicate_protection_required", "not checked here", "idempotency and duplicate signal guard", "required", True, "future module"),
        ("state_reconciliation_required", "not checked here", "local and broker state reconciled", "required", True, "future module"),
        ("SL_TP_mandatory", "preview present", "SL and TP mandatory before any future path", "required", True, "not an order payload"),
        ("risk_volume_calculation_required", "not computed here", "risk and volume calculation plan required", "required", True, "no order_calc in this module"),
        ("order_request_construction_still_forbidden", False, False, "confirmed", True, "future fields only"),
        ("order_check_still_forbidden", False, False, "confirmed", True, "no validation call in this module"),
        ("order_calc_still_forbidden", False, False, "confirmed", True, "no calculation call in this module"),
        ("order_execution_still_forbidden", False, False, "confirmed", True, "no execution approval"),
        ("audit_logging_required", "not checked here", "future audit destination defined", "required", True, "future module"),
        ("kill_switch_required", "not checked here", "kill-switch state checked", "required", True, "future module"),
        ("crash_recovery_required", "not checked here", "recovery state path defined", "required", True, "future module"),
        ("next_module_required", recommended_next_step(plan_status), "next artifact module only", "planned", False, "no execution implied"),
    ]
    rows: list[dict[str, Any]] = []
    for area, observed, expected, result, blocking, caveat in definitions:
        rows.append(
            {
                **context,
                "plan_area": area,
                "observed_value": observed,
                "expected_value": expected,
                "plan_result": result,
                "blocking_if_failed": blocking,
                "caveat": caveat,
            }
        )
    return rows


def requirement_rows(run_id: str) -> list[dict[str, Any]]:
    rows = [
        ("source", "live_data_signal_only", "future design", "input is live-data shadow signal, not fixture", True, "demo_order_request_shadow_design", "fixture input cannot advance"),
        ("account", "demo_account_reconfirmed", "future design", "read-only environment artifact confirms demo account", True, "demo_order_request_shadow_design", "no real-money boundary"),
        ("symbol", "symbol_contract_current", "future design", "symbol contract is current and compatible", True, "demo_order_request_shadow_design", "min/max/step/point/tick fields required"),
        ("spread", "spread_current_rechecked", "future design", "spread <= 15 broker_points", True, "demo_order_request_shadow_design", "artifact spread can age"),
        ("state", "one_open_trade_state_checked", "future design", "max one open position", True, "demo_order_request_shadow_design", "local and broker state must agree"),
        ("state", "duplicate_protection_checked", "future design", "no duplicate open or pending signal", True, "demo_order_request_shadow_design", "idempotency required"),
        ("prices", "SL_TP_mandatory", "future design", "SL and TP preview available and correctly placed", True, "demo_order_request_shadow_design", "short geometry required"),
        ("broker_limits", "stop_distance_checked", "future design", "SL/TP distance compatible with broker minimum stop level", True, "demo_order_request_shadow_design", "future read-only contract check"),
        ("volume", "volume_step_min_max_checked", "future design", "volume respects min/max/step", True, "demo_order_request_shadow_design", "no volume computed here"),
        ("risk", "risk_percentage_capped", "future design", "risk percentage configured and capped", True, "demo_order_request_shadow_design", "no real-money sizing"),
        ("capital", "margin_capital_plan_defined", "future design", "capital sufficiency plan defined without this module calling order_calc", True, "demo_order_request_shadow_design", "future policy required"),
        ("manual_gate", "manual_approval_gate_present", "future design", "manual approval token or checkpoint required", True, "demo_order_request_shadow_design", "no automatic advance"),
        ("safety", "kill_switch_state_checked", "future design", "kill-switch state clear", True, "demo_order_request_shadow_design", "future module"),
        ("recovery", "crash_recovery_state_path_defined", "future design", "recovery state path and reconciliation defined", True, "demo_order_request_shadow_design", "future module"),
        ("audit", "audit_log_destination_defined", "future design", "durable audit log destination defined", True, "demo_order_request_shadow_design", "future module"),
        ("boundary", "explicit_no_real_money_boundary", "future design", "real-money use remains forbidden", True, "demo_order_request_shadow_design", "demo-only future planning"),
    ]
    return [
        {
            "run_id": run_id,
            "requirement_area": area,
            "requirement_name": name,
            "required_before": required_before,
            "expected_condition": expected,
            "blocking_if_failed": blocking,
            "future_module": future_module,
            "caveat": caveat,
        }
        for area, name, required_before, expected, blocking, future_module, caveat in rows
    ]


def future_field_rows(run_id: str) -> list[dict[str, Any]]:
    fields = [
        ("future_symbol", "instrument", "canonical registry and future environment artifact"),
        ("future_direction", "side descriptor", "canonical registry"),
        ("future_order_type", "future type descriptor", "future design policy"),
        ("future_entry_reference_price", "price reference", "would-signal review artifact"),
        ("future_sl_price", "protective stop preview", "would-signal review artifact"),
        ("future_tp_price", "target preview", "would-signal review artifact"),
        ("future_volume_lots", "volume preview", "future risk module"),
        ("future_risk_percent", "risk cap", "canonical config"),
        ("future_magic_comment_audit_id", "audit identifier", "future audit module"),
        ("future_time_in_force_policy", "duration policy", "future design policy"),
        ("future_deviation_policy", "price tolerance policy", "future design policy"),
        ("future_manual_approval_token", "manual approval gate", "future operator checkpoint"),
        ("future_state_signal_id", "state identifier", "future state module"),
        ("future_idempotency_key", "duplicate guard", "future state module"),
    ]
    return [
        {
            "run_id": run_id,
            "future_field_name": name,
            "field_role": role,
            "expected_source": source,
            "required_before": "any future broker payload design",
            "future_field_only": True,
            "not_constructed": True,
            "broker_request_field": False,
            "caveat": "field descriptor only; not a broker payload",
        }
        for name, role, source in fields
    ]


def manifest_payload(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    context: dict[str, Any],
    source_manifest: dict[str, Any],
    plan_status: str,
    source_nature: str,
    requirements: list[dict[str, Any]],
    future_fields: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "canonical_registry_path": str(args.canonical_registry),
        "would_signal_review_dir": str(args.would_signal_review_dir),
        "plan_status": plan_status,
        "source_nature": source_nature,
        "review_status": source_manifest.get("review_status", ""),
        "candidate_id": context["candidate_id"],
        "symbol": context["symbol"],
        "timeframe": context["timeframe"],
        "direction": context["direction"],
        "time_server": context["time_server"],
        "session_observed": context["session_observed"],
        "spread": context["spread"],
        "spread_unit": context["spread_unit"],
        "max_spread_points": context["max_spread_points"],
        "entry_reference_price": context["entry_reference_price"],
        "tp_price_preview": context["tp_price_preview"],
        "sl_price_preview": context["sl_price_preview"],
        "manual_review_required": as_bool(source_manifest.get("manual_review_required")) is True,
        "actionable_signal": False,
        "future_order_path_allowed": False,
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
        "future_fields_count": len(future_fields),
        "requirement_row_count": len(requirements),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "recommended_next_step": recommended_next_step(plan_status),
    }


def write_report(path: Path, *, context: dict[str, Any], source_manifest: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    plan_status = str(context["plan_status"])
    source_nature = str(context["source_nature"])
    lines = [
        "# Fixed Candidate Demo Order Shadow Plan",
        "",
        "Artifact-only order shadow planning. This module reads local review artifacts and writes future requirements.",
        "No MT5, broker, API, account, or symbol query was performed.",
        "No database query or mutation was performed.",
        "No broker order request was constructed.",
        "No order execution was performed.",
        "No order_check or order_calc call was performed.",
        "No scheduler, loop, or background task was added.",
        "This is not demo broker approval and not a trading decision.",
    ]
    if source_nature == "synthetic_fixture":
        lines.append("The source is a synthetic fixture and is non-actionable.")
    if source_nature == "live_data_shadow_signal":
        lines.append("The source is live-data shadow evidence, but no order approval is given.")
    lines.extend(
        [
            "",
            "## Source Summary",
            "",
            f"- review_status: `{source_manifest.get('review_status', '')}`",
            f"- source_nature: `{source_nature}`",
            f"- plan_status: `{plan_status}`",
            f"- time_server: `{context.get('time_server', '')}`",
            f"- spread: `{context.get('spread', '')}` `{context.get('spread_unit', '')}`",
            "",
            "## Future Requirements",
            "",
            "- manual approval gate",
            "- demo account confirmation",
            "- symbol contract confirmation",
            "- spread recheck",
            "- duplicate protection",
            "- state reconciliation",
            "- mandatory SL/TP",
            "- risk and volume calculation plan",
            "- kill-switch check",
            "- audit logging",
            "",
            "## Future Fields",
            "",
            "Future fields are descriptors only. They are marked future_field_only and not_constructed.",
            "",
            "## Recommended Next Step",
            "",
            f"`{context.get('recommended_next_step', '')}`",
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
    source_dir = Path(args.would_signal_review_dir)
    source_manifest, source_error = read_json(source_dir / SOURCE_MANIFEST)
    source_warnings, _ = read_csv_rows(source_dir / SOURCE_WARNINGS_CSV)
    warnings = preserve_source_warnings(args, source_warnings, source_dir / SOURCE_WARNINGS_CSV)
    no_order_ok, no_order_failures = no_order_boundary_ok(source_manifest)
    source_nature_hint = str(source_manifest.get("source_nature") or "")
    signal_ok, signal_failures = signal_preview_ok(source_manifest, source_nature_hint)
    plan_status = determine_plan_status(
        args=args,
        registry=registry,
        registry_error=registry_error,
        source_manifest=source_manifest,
        source_error=source_error,
        no_order_ok=no_order_ok,
        signal_ok=signal_ok,
        warnings=warnings,
    )
    if no_order_failures and plan_status == "blocked_by_no_order_boundary":
        add_warning(warnings, args=args, warning_code="no_order_boundary_failed_fields", message=f"Unsafe no-order fields: {no_order_failures}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
    if signal_failures and plan_status == "blocked_by_signal_preview":
        add_warning(warnings, args=args, warning_code="signal_preview_failed_fields", message=f"Invalid signal preview fields: {signal_failures}", source=source_dir / SOURCE_MANIFEST, blocking_warning=True)
    source_nature = source_nature_for(source_manifest, plan_status)
    context = main_context(args, source_manifest, registry, plan_status, source_nature)
    requirements = requirement_rows(args.run_id)
    future_fields = future_field_rows(args.run_id)
    rows = plan_rows(context, source_manifest, plan_status)

    write_csv(paths["main"], rows, MAIN_FIELDNAMES)
    write_csv(paths["requirements"], requirements, REQUIREMENT_FIELDNAMES)
    write_csv(paths["future_fields"], future_fields, FUTURE_FIELD_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_json(paths["manifest"], manifest_payload(args=args, output_dir=output_dir, context=context, source_manifest=source_manifest, plan_status=plan_status, source_nature=source_nature, requirements=requirements, future_fields=future_fields, warnings=warnings))
    write_report(paths["report"], context=context, source_manifest=source_manifest, warnings=warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only fixed-candidate demo order shadow plan.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--would-signal-review-dir", type=Path, default=DEFAULT_WOULD_SIGNAL_REVIEW_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        build_outputs(args)
    except Exception as exc:
        print(f"Fixed-candidate demo order shadow plan failed: {exc}")
        return 1
    print("Fixed-candidate demo order shadow plan complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
