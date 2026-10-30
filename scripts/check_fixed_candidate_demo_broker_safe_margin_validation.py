"""Broker-safe read-only demo margin validation for the fixed candidate.

This checker may connect to an explicitly configured demo MT5 environment and
use the broker margin estimator for scalar margin validation only. It does not
send, check, profit-calculate, inspect positions/orders/history, construct a
broker-ready structure, query databases, run child scripts, or approve any demo
execution.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_broker_safe_margin_validation"
DEFAULT_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_broker_safe_margin_validation_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_broker_safe_margin_validation_plan_fixture_v1"
)
DEFAULT_RISK_VOLUME_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_risk_volume_shadow_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_risk_volume_shadow_plan_fixture_equity1000_risk05_margin70_v1"
)
DEFAULT_MARGIN_FEASIBILITY_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_margin_feasibility_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_margin_feasibility_plan_fixture_equity1000_risk05_margin70_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_broker_safe_margin_validation"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_SYMBOL = "GBPUSD"
EXPECTED_TIMEFRAME = "M15"
EXPECTED_DIRECTION = "short"
EXPECTED_SPREAD_UNIT = "broker_points"
EXPECTED_MAX_SPREAD_POINTS = 15.0
EXPECTED_ACCOUNT_CURRENCY = "EUR"
EXPECTED_DEMO_EQUITY = 1000.0
EXPECTED_EQUITY_TOLERANCE_RATIO = 0.10
EXPECTED_RISK_PERCENT = 0.5
EXPECTED_RISK_AMOUNT = 5.0
EXPECTED_WARNING_RATIO = 0.5
EXPECTED_CAP_RATIO = 0.7

PLAN_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_plan_manifest.json"
RISK_VOLUME_MANIFEST = "fixed_candidate_demo_risk_volume_shadow_plan_manifest.json"
MARGIN_FEASIBILITY_MANIFEST = "fixed_candidate_demo_margin_feasibility_plan_manifest.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_broker_safe_margin_validation_report.md"
OUTPUT_CHECKLIST = "fixed_candidate_demo_broker_safe_margin_validation_checklist.csv"
OUTPUT_MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"
OUTPUT_WARNINGS = "fixed_candidate_demo_broker_safe_margin_validation_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_broker_safe_margin_validation_no_order_evidence.csv"

ACCEPTABLE_PLAN_STATUSES = {
    "broker_safe_margin_validation_plan_fixture_only",
    "broker_safe_margin_validation_plan_available",
    "broker_safe_margin_validation_plan_required_due_to_margin_warning",
}
ACCEPTABLE_RISK_VOLUME_STATUSES = {
    "risk_volume_shadow_plan_fixture_only",
    "risk_volume_shadow_plan_available_no_order",
}
ACCEPTABLE_MARGIN_FEASIBILITY_STATUSES = {
    "margin_feasibility_plan_fixture_only",
    "margin_feasibility_plan_available_no_order",
    "margin_feasibility_hold_requires_broker_margin_validation",
}

SOURCE_NATURES = {"synthetic_fixture", "live_data_shadow_signal"}

TRUE_SOURCE_BOUNDARY_FIELDS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_profit_called",
    "no_demo_broker_approval_performed",
    "no_trading_decision_performed",
    "no_db_mutation_performed",
    "no_child_scripts_executed",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
)
OPTIONAL_TRUE_SOURCE_BOUNDARY_FIELDS = (
    "no_mt5_connection_performed",
    "no_broker_connection_performed",
    "no_account_query_performed",
    "no_symbol_query_performed",
    "no_db_query_performed",
    "no_order_calc_margin_called",
)
FALSE_SOURCE_BOUNDARY_FIELDS = (
    "plan_actionable",
    "order_execution_allowed",
    "order_request_construction_allowed",
    "demo_broker_approval_performed",
)

CHECKLIST_AREAS = [
    "canonical_registry_loaded",
    "execution_policy_loaded",
    "margin_validation_plan_loaded",
    "risk_volume_artifact_loaded",
    "margin_feasibility_artifact_loaded",
    "source_nature_identified",
    "mt5_import_status",
    "mt5_initialize_status",
    "terminal_info_read",
    "account_info_read",
    "demo_account_confirmed",
    "account_currency_confirmed",
    "account_equity_policy_checked",
    "symbol_info_read",
    "symbol_visibility_checked",
    "symbol_select_if_needed",
    "symbol_tick_read",
    "spread_policy_checked",
    "scalar_margin_inputs_prepared",
    "order_calc_margin_called_once",
    "broker_margin_result_available",
    "margin_usage_policy_checked",
    "no_order_send_confirmed",
    "no_order_check_confirmed",
    "no_order_calc_profit_confirmed",
    "no_positions_orders_history_confirmed",
    "no_request_payload_constructed",
    "no_execution_approval_confirmed",
]

CHECKLIST_FIELDNAMES = [
    "run_id",
    "check_area",
    "check_name",
    "check_status",
    "observed_value",
    "expected_value",
    "blocking_if_failed",
    "evidence_source",
    "caveat",
    "warning_code",
]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
NO_ORDER_FIELDNAMES = [
    "run_id",
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_profit_called",
    "no_positions_get_called",
    "no_orders_get_called",
    "no_history_orders_get_called",
    "no_history_deals_get_called",
    "order_calc_margin_called",
    "order_calc_margin_call_count",
    "no_db_query_performed",
    "no_db_mutation_performed",
    "no_child_scripts_executed",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "no_trading_decision_performed",
    "no_demo_broker_approval_performed",
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


def close_float(left: Any, right: float, tolerance: float = 1e-6) -> bool:
    left_float = safe_float(left)
    return left_float is not None and abs(left_float - right) <= tolerance


def object_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    output: dict[str, Any] = {}
    for name in dir(value):
        if name.startswith("_"):
            continue
        try:
            item = getattr(value, name)
        except Exception:
            continue
        if callable(item):
            continue
        output[name] = item
    return output


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


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


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
        "blocking_warning": blocking_warning,
    }


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
    warning_code: str,
    message: str,
    source: Path | str,
    blocking_warning: bool = False,
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


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in warnings if as_bool(row.get("blocking_warning")) is True]


def effective_dry_run(args: argparse.Namespace) -> bool:
    return bool(args.dry_run) or not bool(args.allow_broker_read)


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "checklist": output_dir / OUTPUT_CHECKLIST,
        "margin_snapshot": output_dir / OUTPUT_MARGIN_SNAPSHOT,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def canonical_registry_valid(registry: dict[str, Any], symbol: str, direction: str) -> bool:
    return (
        registry.get("candidate_id") == EXPECTED_CANDIDATE_ID
        and registry.get("symbol") == symbol == EXPECTED_SYMBOL
        and registry.get("timeframe") == EXPECTED_TIMEFRAME
        and registry.get("direction") == direction == EXPECTED_DIRECTION
        and registry.get("spread_unit") == EXPECTED_SPREAD_UNIT
        and close_float(registry.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS)
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
        and close_float(policy.get("max_margin_usage_ratio"), EXPECTED_CAP_RATIO)
        and as_bool(safety.get("real_money_allowed")) is False
        and as_bool(safety.get("order_execution_allowed")) is False
        and as_bool(safety.get("order_request_construction_allowed")) is False
        and as_bool(safety.get("order_check_allowed")) is False
        and as_bool(safety.get("order_calc_allowed")) is False
        and as_bool(safety.get("manual_approval_required_before_any_future_demo_order")) is True
    )


def plan_artifact_valid(plan: dict[str, Any]) -> bool:
    return (
        plan.get("plan_status") in ACCEPTABLE_PLAN_STATUSES
        and as_bool(plan.get("future_order_calc_margin_allowed_only_in_separate_module")) is True
        and as_bool(plan.get("future_order_send_allowed")) is False
        and as_bool(plan.get("future_order_check_allowed")) is False
        and as_bool(plan.get("future_order_calc_profit_allowed")) is False
        and as_bool(plan.get("future_positions_orders_history_allowed")) is False
    )


def source_boundary_ok(source: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for field in TRUE_SOURCE_BOUNDARY_FIELDS:
        if as_bool(source.get(field)) is not True:
            failures.append(field)
    for field in OPTIONAL_TRUE_SOURCE_BOUNDARY_FIELDS:
        if field in source and as_bool(source.get(field)) is not True:
            failures.append(field)
    for field in FALSE_SOURCE_BOUNDARY_FIELDS:
        if field in source and as_bool(source.get(field)) is not False:
            failures.append(field)
    return not failures, failures


def risk_volume_valid(source: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if source.get("plan_status") not in ACCEPTABLE_RISK_VOLUME_STATUSES:
        failures.append("plan_status")
    if source.get("source_nature") not in SOURCE_NATURES:
        failures.append("source_nature")
    if not close_float(source.get("risk_percent"), EXPECTED_RISK_PERCENT):
        failures.append("risk_percent")
    if not close_float(source.get("demo_equity"), EXPECTED_DEMO_EQUITY):
        failures.append("demo_equity")
    if not close_float(source.get("risk_amount"), EXPECTED_RISK_AMOUNT, tolerance=0.02):
        failures.append("risk_amount")
    if safe_float(source.get("stepped_volume_lots")) is None or safe_float(source.get("stepped_volume_lots")) <= 0:
        failures.append("stepped_volume_lots")
    if safe_float(source.get("entry_reference_price")) is None or safe_float(source.get("entry_reference_price")) <= 0:
        failures.append("entry_reference_price")
    if source.get("direction") != EXPECTED_DIRECTION:
        failures.append("direction")
    if source.get("volume_preview_status") != "shadow_volume_preview_available_not_broker_validated":
        failures.append("volume_preview_status")
    return not failures, failures


def margin_feasibility_valid(source: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if source.get("plan_status") not in ACCEPTABLE_MARGIN_FEASIBILITY_STATUSES:
        failures.append("plan_status")
    if source.get("approximate_margin_usage_ratio") not in ("", None) and safe_float(source.get("approximate_margin_usage_ratio")) is None:
        failures.append("approximate_margin_usage_ratio")
    if not close_float(source.get("max_margin_usage_ratio"), EXPECTED_CAP_RATIO):
        failures.append("max_margin_usage_ratio")
    if as_bool(source.get("margin_estimate_static_artifact_only")) is not True:
        failures.append("margin_estimate_static_artifact_only")
    return not failures, failures


def classify_account_mode(mt5_module: Any, account_info: dict[str, Any]) -> tuple[str, bool | None]:
    raw_mode = account_info.get("trade_mode")
    demo_const = getattr(mt5_module, "ACCOUNT_TRADE_MODE_DEMO", None)
    contest_const = getattr(mt5_module, "ACCOUNT_TRADE_MODE_CONTEST", None)
    real_const = getattr(mt5_module, "ACCOUNT_TRADE_MODE_REAL", None)
    if demo_const is not None and raw_mode == demo_const:
        return "demo", True
    if contest_const is not None and raw_mode == contest_const:
        return "contest", False
    if real_const is not None and raw_mode == real_const:
        return "real", False
    text = " ".join(str(account_info.get(field, "")) for field in ("server", "name", "company")).lower()
    if "demo" in text:
        return "demo", True
    if "real" in text or "live" in text:
        return "real", False
    return "unknown", None


def validate_account(account: dict[str, Any], mode_label: str, is_demo: bool | None) -> tuple[bool, list[str], str]:
    failures: list[str] = []
    if is_demo is not True or mode_label != "demo":
        failures.append("account_mode")
    if account.get("currency") != EXPECTED_ACCOUNT_CURRENCY:
        failures.append("currency")
    if account.get("trade_allowed") is not None and as_bool(account.get("trade_allowed")) is not True:
        failures.append("trade_allowed")
    if account.get("trade_expert") is not None and as_bool(account.get("trade_expert")) is not True:
        failures.append("trade_expert")
    leverage = safe_float(account.get("leverage"))
    if leverage is None or leverage <= 0:
        failures.append("leverage")
    equity = safe_float(account.get("equity"))
    if equity is None or equity <= 0:
        failures.append("equity")
        equity_status = "invalid"
    else:
        delta_ratio = abs(equity - EXPECTED_DEMO_EQUITY) / EXPECTED_DEMO_EQUITY
        equity_status = "within_10pct" if delta_ratio <= EXPECTED_EQUITY_TOLERANCE_RATIO else "outside_10pct"
    if account.get("margin_free") not in ("", None) and safe_float(account.get("margin_free")) is None:
        failures.append("margin_free")
    return not failures, failures, equity_status


def validate_symbol(symbol_info: dict[str, Any], tick_info: dict[str, Any], symbol: str) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if (symbol_info.get("name") or symbol) != symbol:
        failures.append("symbol")
    for field in ("point", "volume_min", "volume_max", "volume_step"):
        value = safe_float(symbol_info.get(field))
        if value is None or value <= 0:
            failures.append(field)
    if safe_float(symbol_info.get("digits")) != 5:
        failures.append("digits")
    for field in ("trade_tick_size", "trade_tick_value"):
        if symbol_info.get(field) not in ("", None) and safe_float(symbol_info.get(field)) is None:
            failures.append(field)
    spread = safe_float(symbol_info.get("spread"))
    if spread is None:
        failures.append("spread")
    elif spread > EXPECTED_MAX_SPREAD_POINTS:
        failures.append("spread_above_policy")
    bid = safe_float(tick_info.get("bid"))
    ask = safe_float(tick_info.get("ask"))
    if bid is None or bid <= 0:
        failures.append("bid")
    if ask is None or ask <= 0:
        failures.append("ask")
    return not failures, failures


def planned_margin_snapshot(args: argparse.Namespace, source_nature: str, risk_volume: dict[str, Any], margin_feasibility: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "validation_status": "broker_safe_margin_validation_plan_only",
        "source_nature": source_nature,
        "account_mode_label": "not_queried",
        "account_currency": "not_queried",
        "account_equity": None,
        "account_leverage": None,
        "account_margin_free": None,
        "account_redaction_applied": True,
        "symbol": args.symbol,
        "digits": None,
        "point": None,
        "volume_min": None,
        "volume_max": None,
        "volume_step": None,
        "spread_current_points": None,
        "bid": None,
        "ask": None,
        "margin_calc_side": "SELL",
        "margin_calc_symbol": args.symbol,
        "margin_calc_volume_lots": safe_float(risk_volume.get("stepped_volume_lots")),
        "margin_calc_price": None,
        "broker_margin_estimate": None,
        "broker_margin_usage_ratio": None,
        "static_estimated_margin_quote": safe_float(margin_feasibility.get("estimated_margin_quote")),
        "static_approximate_margin_usage_ratio": safe_float(margin_feasibility.get("approximate_margin_usage_ratio")),
        "warning_ratio": EXPECTED_WARNING_RATIO,
        "hard_cap_ratio": EXPECTED_CAP_RATIO,
        "order_calc_margin_called": False,
        "order_calc_margin_call_count": 0,
        "broker_read_performed": False,
        "no_order_request_constructed": True,
        "no_order_execution_performed": True,
        "not_execution_approval": True,
    }


def inspect_mt5_and_margin(
    args: argparse.Namespace,
    warnings: list[dict[str, Any]],
    risk_volume: dict[str, Any],
    margin_feasibility: dict[str, Any],
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "mt5_import_attempted": False,
        "mt5_initialize_attempted": False,
        "mt5_initialize_success": False,
        "terminal_info": {},
        "account_info": {},
        "symbol_info": {},
        "tick_info": {},
        "symbol_select_performed": False,
        "symbol_select_success": False,
        "account_mode_label": "not_queried",
        "is_demo_account": None,
        "account_equity_policy_status": "not_checked",
        "account_failures": [],
        "symbol_failures": [],
        "margin_calc_side": "SELL",
        "margin_calc_price": None,
        "broker_margin_estimate": None,
        "broker_margin_usage_ratio": None,
        "order_calc_margin_called": False,
        "order_calc_margin_call_count": 0,
        "broker_read_performed": False,
        "margin_calc_error": "",
        "import_error": "",
        "initialize_error": "",
        "mt5_module": None,
    }
    state["mt5_import_attempted"] = True
    try:
        mt5_module = importlib.import_module(str(args.mt5_package))
    except Exception as exc:
        state["import_error"] = str(exc)
        add_warning(warnings, args=args, warning_code="mt5_import_failed", message=f"Configured MT5 package could not be imported: {exc}", source=args.mt5_package, blocking_warning=True)
        return state
    state["mt5_module"] = mt5_module
    state["mt5_initialize_attempted"] = True
    try:
        initialized = bool(mt5_module.initialize())
    except Exception as exc:
        initialized = False
        state["initialize_error"] = str(exc)
    state["mt5_initialize_success"] = initialized
    if not initialized:
        add_warning(warnings, args=args, warning_code="mt5_initialize_failed", message="MT5 initialization failed.", source=args.mt5_package, blocking_warning=True)
        return state
    try:
        state["terminal_info"] = object_to_dict(mt5_module.terminal_info())
        account_info = object_to_dict(mt5_module.account_info())
        state["account_info"] = account_info
        state["broker_read_performed"] = bool(state["terminal_info"] or state["account_info"])
        mode_label, is_demo = classify_account_mode(mt5_module, account_info)
        state["account_mode_label"] = mode_label
        state["is_demo_account"] = is_demo
        account_ok, account_failures, equity_status = validate_account(account_info, mode_label, is_demo)
        state["account_failures"] = account_failures
        state["account_equity_policy_status"] = equity_status
        if equity_status == "outside_10pct":
            add_warning(
                warnings,
                args=args,
                warning_code="account_equity_differs_from_policy",
                message="Current account equity differs from intended 1000 EUR policy by more than 10%.",
                source=args.mt5_package,
                blocking_warning=False,
            )
        if not account_ok:
            add_warning(warnings, args=args, warning_code="account_snapshot_invalid", message=f"Account validation failed: {account_failures}", source=args.mt5_package, blocking_warning=True)
            return state
        symbol_info = object_to_dict(mt5_module.symbol_info(args.symbol))
        if symbol_info and as_bool(symbol_info.get("visible")) is not True:
            select_fn = getattr(mt5_module, "symbol_select", None)
            if callable(select_fn):
                state["symbol_select_performed"] = True
                state["symbol_select_success"] = bool(select_fn(args.symbol, True))
                if state["symbol_select_success"]:
                    symbol_info = object_to_dict(mt5_module.symbol_info(args.symbol))
        state["symbol_info"] = symbol_info
        state["broker_read_performed"] = bool(state["broker_read_performed"] or state["symbol_info"])
        if not symbol_info or as_bool(symbol_info.get("visible")) is not True:
            add_warning(warnings, args=args, warning_code="symbol_unavailable", message="Symbol info is missing or not visible after optional selection.", source=args.symbol, blocking_warning=True)
            return state
        tick_info = object_to_dict(mt5_module.symbol_info_tick(args.symbol))
        state["tick_info"] = tick_info
        state["broker_read_performed"] = bool(state["broker_read_performed"] or state["tick_info"])
        symbol_ok, symbol_failures = validate_symbol(symbol_info, tick_info, args.symbol)
        state["symbol_failures"] = symbol_failures
        if not symbol_ok:
            spread_fail_only = symbol_failures == ["spread_above_policy"]
            add_warning(
                warnings,
                args=args,
                warning_code="spread_above_policy" if spread_fail_only else "symbol_contract_invalid",
                message=f"Symbol validation failed: {symbol_failures}",
                source=args.symbol,
                blocking_warning=True,
            )
            return state
        price = safe_float(tick_info.get("bid")) if args.direction == "short" else safe_float(tick_info.get("ask"))
        if price is None or price <= 0:
            price = safe_float(risk_volume.get("entry_reference_price"))
            add_warning(warnings, args=args, warning_code="margin_calc_price_fallback", message="Tick price unavailable; entry reference price used as margin-estimation scalar.", source=args.symbol, blocking_warning=False)
        state["margin_calc_price"] = price
        volume_lots = safe_float(risk_volume.get("stepped_volume_lots"))
        side_value = getattr(mt5_module, "ORDER_TYPE_SELL", 1)
        if not args.allow_order_calc_margin:
            state["margin_calc_error"] = "missing --allow-order-calc-margin"
            add_warning(
                warnings,
                args=args,
                warning_code="missing_allow_order_calc_margin",
                message="Broker margin estimator requires explicit --allow-order-calc-margin.",
                source=args.mt5_package,
                blocking_warning=True,
            )
            return state
        calc_margin = getattr(mt5_module, "order_calc_margin", None)
        if not callable(calc_margin):
            state["margin_calc_error"] = "order_calc_margin unavailable"
            add_warning(warnings, args=args, warning_code="margin_calc_unavailable", message="Broker margin estimator is unavailable.", source=args.mt5_package, blocking_warning=True)
            return state
        try:
            state["order_calc_margin_called"] = True
            state["order_calc_margin_call_count"] = 1
            margin_result = calc_margin(side_value, args.symbol, volume_lots, price)
        except Exception as exc:
            state["margin_calc_error"] = str(exc)
            add_warning(warnings, args=args, warning_code="margin_calc_failed", message=f"Broker margin estimator failed: {exc}", source=args.mt5_package, blocking_warning=True)
            return state
        state["broker_margin_estimate"] = safe_float(margin_result)
        equity = safe_float(account_info.get("equity"))
        if state["broker_margin_estimate"] is not None and equity is not None and equity > 0:
            state["broker_margin_usage_ratio"] = state["broker_margin_estimate"] / equity
        if state["broker_margin_estimate"] is None:
            add_warning(warnings, args=args, warning_code="margin_calc_result_missing", message="Broker margin estimator returned no numeric result.", source=args.mt5_package, blocking_warning=True)
    finally:
        shutdown = getattr(mt5_module, "shutdown", None)
        if callable(shutdown):
            shutdown()
    return state


def preflight_status(
    *,
    args: argparse.Namespace,
    registry_error: str,
    policy_error: str,
    plan_error: str,
    risk_error: str,
    margin_error: str,
    registry: dict[str, Any],
    policy: dict[str, Any],
    plan: dict[str, Any],
    risk_volume: dict[str, Any],
    margin_feasibility: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> str | None:
    missing = [
        ("canonical_registry_missing", registry_error, args.canonical_registry),
        ("demo_execution_policy_missing", policy_error, args.demo_execution_policy),
        ("margin_validation_plan_missing", plan_error, Path(args.broker_safe_margin_validation_plan_dir) / PLAN_MANIFEST),
        ("risk_volume_manifest_missing", risk_error, Path(args.risk_volume_shadow_plan_dir) / RISK_VOLUME_MANIFEST),
        ("margin_feasibility_manifest_missing", margin_error, Path(args.margin_feasibility_plan_dir) / MARGIN_FEASIBILITY_MANIFEST),
    ]
    missing_errors = [item for item in missing if item[1] == "missing"]
    if missing_errors:
        for code, _error, source in missing_errors:
            add_warning(warnings, args=args, warning_code=code, message="Required input artifact is missing.", source=source, blocking_warning=True)
        return "blocked_missing_required_artifact"
    unreadable_errors = [item for item in missing if item[1]]
    if unreadable_errors:
        for code, error, source in unreadable_errors:
            add_warning(warnings, args=args, warning_code=code.replace("missing", "unreadable"), message=f"Required input artifact is unreadable: {error}", source=source, blocking_warning=True)
        return "blocked_unreadable_input"
    if not canonical_registry_valid(registry, args.symbol, args.direction):
        add_warning(warnings, args=args, warning_code="canonical_registry_boundary_mismatch", message="Canonical registry does not match fixed-candidate spread15 boundaries.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_by_config_boundary"
    if not execution_policy_valid(policy):
        add_warning(warnings, args=args, warning_code="demo_execution_policy_boundary_mismatch", message="Demo execution policy does not match equity1000/risk0.5/margin70 no-order boundaries.", source=args.demo_execution_policy, blocking_warning=True)
        return "blocked_by_policy_boundary"
    plan_status = str(plan.get("plan_status") or "")
    if plan_status.startswith("blocked_") or plan_status == "hold_missing_volume_for_margin_validation_plan" or not plan_artifact_valid(plan):
        add_warning(warnings, args=args, warning_code="margin_validation_plan_status_invalid", message=f"Margin validation plan is not acceptable: {plan_status}", source=Path(args.broker_safe_margin_validation_plan_dir) / PLAN_MANIFEST, blocking_warning=True)
        return "blocked_by_margin_validation_plan_status"
    risk_boundary_ok, risk_boundary_failures = source_boundary_ok(risk_volume)
    margin_boundary_ok, margin_boundary_failures = source_boundary_ok(margin_feasibility)
    if not risk_boundary_ok or not margin_boundary_ok:
        failures = risk_boundary_failures + margin_boundary_failures
        add_warning(warnings, args=args, warning_code="source_no_order_boundary_violation", message=f"Source no-order boundary failed: {failures}", source="source_artifacts", blocking_warning=True)
        return "blocked_no_order_boundary_violation"
    risk_ok, risk_failures = risk_volume_valid(risk_volume)
    if not risk_ok:
        add_warning(warnings, args=args, warning_code="risk_volume_artifact_invalid", message=f"Risk/volume artifact failed: {risk_failures}", source=Path(args.risk_volume_shadow_plan_dir) / RISK_VOLUME_MANIFEST, blocking_warning=True)
        return "blocked_by_risk_volume_artifact"
    margin_ok, margin_failures = margin_feasibility_valid(margin_feasibility)
    if not margin_ok:
        add_warning(warnings, args=args, warning_code="margin_feasibility_artifact_invalid", message=f"Margin feasibility artifact failed: {margin_failures}", source=Path(args.margin_feasibility_plan_dir) / MARGIN_FEASIBILITY_MANIFEST, blocking_warning=True)
        return "blocked_by_margin_feasibility_artifact"
    return None


def source_nature_for(plan: dict[str, Any], risk_volume: dict[str, Any], margin_feasibility: dict[str, Any]) -> str:
    for source in (risk_volume, margin_feasibility, plan):
        value = source.get("source_nature")
        if value in SOURCE_NATURES:
            return str(value)
    if plan.get("plan_status") == "broker_safe_margin_validation_plan_fixture_only":
        return "synthetic_fixture"
    return "live_data_shadow_signal"


def final_status(args: argparse.Namespace, source_nature: str, preflight: str | None, state: dict[str, Any]) -> str:
    if preflight:
        return preflight
    if args.dry_run:
        return "broker_read_dry_run_no_broker_read"
    if state["import_error"]:
        return "blocked_mt5_import_failed"
    if not state["mt5_initialize_success"]:
        return "blocked_mt5_initialize_failed"
    if state["account_failures"]:
        if "account_mode" in state["account_failures"]:
            return "blocked_non_demo_account"
        return "blocked_account_snapshot_invalid"
    if not state["symbol_info"]:
        return "blocked_symbol_unavailable"
    if "spread_above_policy" in state["symbol_failures"]:
        return "blocked_spread_above_policy"
    if state["symbol_failures"]:
        return "blocked_symbol_contract_invalid"
    if args.allow_broker_read and not args.allow_order_calc_margin:
        return "broker_safe_margin_validation_blocked_missing_allow_order_calc_margin"
    if state["broker_margin_estimate"] is None:
        return "broker_safe_margin_validation_blocked_by_margin_calc_failure"
    usage_ratio = safe_float(state["broker_margin_usage_ratio"])
    if usage_ratio is not None and usage_ratio > EXPECTED_CAP_RATIO:
        return "broker_safe_margin_validation_hold_margin_above_policy_cap"
    if source_nature == "synthetic_fixture":
        if usage_ratio is not None and usage_ratio > EXPECTED_WARNING_RATIO:
            return "broker_safe_margin_validation_fixture_only_available_with_margin_warning"
        return "broker_safe_margin_validation_fixture_only"
    if usage_ratio is not None and usage_ratio > EXPECTED_WARNING_RATIO:
        return "broker_safe_margin_validation_available_with_margin_warning"
    return "broker_safe_margin_validation_available"


def recommended_next_step(status: str, source_nature: str) -> str:
    if status in {"broker_safe_margin_validation_plan_only", "broker_read_dry_run_no_broker_read"}:
        return "run_broker_safe_margin_validation_when_demo_terminal_ready"
    if status == "broker_safe_margin_validation_blocked_missing_allow_order_calc_margin":
        return "rerun_with_allow_order_calc_margin_only_after_operator_review"
    if source_nature == "synthetic_fixture" and status.startswith("broker_safe_margin_validation_fixture_only"):
        return "wait_for_live_shadow_signal_or_continue_no_order_monitoring"
    if status in {"broker_safe_margin_validation_available", "broker_safe_margin_validation_available_with_margin_warning"}:
        return "build_fixed_candidate_demo_state_reconciliation_plan"
    if status == "broker_safe_margin_validation_hold_margin_above_policy_cap":
        return "review_margin_policy_or_reduce_shadow_volume_before_any_later_phase"
    return "fix_broker_safe_margin_validation_blocker"


def build_margin_snapshot(
    *,
    args: argparse.Namespace,
    status: str,
    source_nature: str,
    state: dict[str, Any],
    risk_volume: dict[str, Any],
    margin_feasibility: dict[str, Any],
) -> dict[str, Any]:
    account = state.get("account_info", {})
    symbol = state.get("symbol_info", {})
    tick = state.get("tick_info", {})
    if args.dry_run or not account:
        return planned_margin_snapshot(args, source_nature, risk_volume, margin_feasibility)
    return {
        "run_id": args.run_id,
        "validation_status": status,
        "source_nature": source_nature,
        "account_mode_label": state["account_mode_label"],
        "account_currency": account.get("currency"),
        "account_equity": safe_float(account.get("equity")),
        "account_leverage": safe_float(account.get("leverage")),
        "account_margin_free": safe_float(account.get("margin_free")),
        "account_redaction_applied": True,
        "symbol": symbol.get("name") or args.symbol,
        "digits": safe_float(symbol.get("digits")),
        "point": safe_float(symbol.get("point")),
        "volume_min": safe_float(symbol.get("volume_min")),
        "volume_max": safe_float(symbol.get("volume_max")),
        "volume_step": safe_float(symbol.get("volume_step")),
        "spread_current_points": safe_float(symbol.get("spread")),
        "bid": safe_float(tick.get("bid")),
        "ask": safe_float(tick.get("ask")),
        "margin_calc_side": state["margin_calc_side"],
        "margin_calc_symbol": args.symbol,
        "margin_calc_volume_lots": safe_float(risk_volume.get("stepped_volume_lots")),
        "margin_calc_price": state["margin_calc_price"],
        "broker_margin_estimate": state["broker_margin_estimate"],
        "broker_margin_usage_ratio": state["broker_margin_usage_ratio"],
        "static_estimated_margin_quote": safe_float(margin_feasibility.get("estimated_margin_quote")),
        "static_approximate_margin_usage_ratio": safe_float(margin_feasibility.get("approximate_margin_usage_ratio")),
        "warning_ratio": EXPECTED_WARNING_RATIO,
        "hard_cap_ratio": EXPECTED_CAP_RATIO,
        "order_calc_margin_called": state["order_calc_margin_called"],
        "order_calc_margin_call_count": state["order_calc_margin_call_count"],
        "no_order_request_constructed": True,
        "no_order_execution_performed": True,
        "not_execution_approval": True,
    }


def checklist_rows(args: argparse.Namespace, status: str, preflight: str | None, source_nature: str, state: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    statuses: dict[str, tuple[str, Any, Any, str]] = {
        "canonical_registry_loaded": ("passed" if not preflight or preflight != "blocked_by_config_boundary" else "failed", "loaded", "fixed candidate spread15", "canonical_registry_boundary_mismatch"),
        "execution_policy_loaded": ("passed" if not preflight or preflight != "blocked_by_policy_boundary" else "failed", "loaded", "equity1000/risk0.5/margin70", "demo_execution_policy_boundary_mismatch"),
        "margin_validation_plan_loaded": ("passed" if not preflight or preflight != "blocked_by_margin_validation_plan_status" else "failed", status, "acceptable plan status", "margin_validation_plan_status_invalid"),
        "risk_volume_artifact_loaded": ("passed" if not preflight or preflight != "blocked_by_risk_volume_artifact" else "failed", "loaded", "valid risk/volume artifact", "risk_volume_artifact_invalid"),
        "margin_feasibility_artifact_loaded": ("passed" if not preflight or preflight != "blocked_by_margin_feasibility_artifact" else "failed", "loaded", "valid margin artifact", "margin_feasibility_artifact_invalid"),
        "source_nature_identified": ("passed", source_nature, "synthetic_fixture or live_data_shadow_signal", ""),
        "mt5_import_status": ("planned_not_verified" if args.dry_run else ("passed" if state["mt5_import_attempted"] and not state["import_error"] else "failed"), state["mt5_import_attempted"], "MT5 imported only in non-dry-run", "mt5_import_failed"),
        "mt5_initialize_status": ("planned_not_verified" if args.dry_run else ("passed" if state["mt5_initialize_success"] else "failed"), state["mt5_initialize_success"], "MT5 initialized", "mt5_initialize_failed"),
        "terminal_info_read": ("planned_not_verified" if args.dry_run else ("passed" if state["terminal_info"] else "failed"), bool(state["terminal_info"]), "terminal_info available", "terminal_info_missing"),
        "account_info_read": ("planned_not_verified" if args.dry_run else ("passed" if state["account_info"] else "failed"), bool(state["account_info"]), "account_info available", "account_info_missing"),
        "demo_account_confirmed": ("planned_not_verified" if args.dry_run else ("passed" if state["is_demo_account"] is True else "failed"), state["account_mode_label"], "demo", "account_not_demo"),
        "account_currency_confirmed": ("planned_not_verified" if args.dry_run else ("passed" if snapshot.get("account_currency") == EXPECTED_ACCOUNT_CURRENCY else "failed"), snapshot.get("account_currency"), "EUR", "account_currency_not_eur"),
        "account_equity_policy_checked": ("planned_not_verified" if args.dry_run else ("passed" if state["account_equity_policy_status"] in {"within_10pct", "outside_10pct"} else "failed"), state["account_equity_policy_status"], "positive equity; warning if outside 10pct", "account_equity_invalid"),
        "symbol_info_read": ("planned_not_verified" if args.dry_run else ("passed" if state["symbol_info"] else "failed"), bool(state["symbol_info"]), "symbol_info available", "symbol_unavailable"),
        "symbol_visibility_checked": ("planned_not_verified" if args.dry_run else ("passed" if snapshot.get("symbol") == args.symbol else "failed"), snapshot.get("symbol"), args.symbol, "symbol_unavailable"),
        "symbol_select_if_needed": ("planned_not_verified" if args.dry_run else "passed", state["symbol_select_performed"], "only if symbol was not visible", ""),
        "symbol_tick_read": ("planned_not_verified" if args.dry_run else ("passed" if state["tick_info"] else "failed"), bool(state["tick_info"]), "tick available", "symbol_tick_missing"),
        "spread_policy_checked": ("planned_not_verified" if args.dry_run else ("passed" if safe_float(snapshot.get("spread_current_points")) is not None and safe_float(snapshot.get("spread_current_points")) <= EXPECTED_MAX_SPREAD_POINTS else "failed"), snapshot.get("spread_current_points"), "<=15 broker_points", "spread_above_policy"),
        "scalar_margin_inputs_prepared": ("planned_not_verified" if args.dry_run else ("passed" if state["margin_calc_price"] else "failed"), state["margin_calc_price"], "scalar side/symbol/volume/price", "scalar_margin_inputs_missing"),
        "order_calc_margin_called_once": ("planned_not_verified" if args.dry_run else ("passed" if state["order_calc_margin_call_count"] == 1 else "failed"), state["order_calc_margin_call_count"], 1, "margin_calc_call_count_invalid"),
        "broker_margin_result_available": ("planned_not_verified" if args.dry_run else ("passed" if state["broker_margin_estimate"] is not None else "failed"), state["broker_margin_estimate"], "numeric margin result", "margin_calc_result_missing"),
        "margin_usage_policy_checked": ("planned_not_verified" if args.dry_run else ("passed" if state["broker_margin_usage_ratio"] is not None else "failed"), state["broker_margin_usage_ratio"], "compared to 0.50 warning and 0.70 cap", "margin_usage_not_computed"),
        "no_order_send_confirmed": ("passed", True, True, ""),
        "no_order_check_confirmed": ("passed", True, True, ""),
        "no_order_calc_profit_confirmed": ("passed", True, True, ""),
        "no_positions_orders_history_confirmed": ("passed", True, True, ""),
        "no_request_payload_constructed": ("passed", True, True, ""),
        "no_execution_approval_confirmed": ("passed", True, True, ""),
    }
    rows: list[dict[str, Any]] = []
    for area in CHECKLIST_AREAS:
        check_status, observed, expected, warning_code = statuses[area]
        rows.append(
            {
                "run_id": args.run_id,
                "check_area": area,
                "check_name": area.replace("_", " "),
                "check_status": check_status,
                "observed_value": observed,
                "expected_value": expected,
                "blocking_if_failed": area not in {"account_equity_policy_checked"},
                "evidence_source": "artifact_or_mt5_read_only",
                "caveat": "broker_safe_margin_validation_no_order_no_approval",
                "warning_code": warning_code,
            }
        )
    return rows


def add_status_warnings(args: argparse.Namespace, rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    for row in rows:
        if row.get("check_status") != "failed":
            continue
        add_warning(
            warnings,
            args=args,
            warning_code=row.get("warning_code") or f"{row['check_area']}_failed",
            message=f"Broker-safe margin validation check failed: {row['check_area']}",
            source=row["evidence_source"],
            blocking_warning=as_bool(row.get("blocking_if_failed")) is True,
        )


def no_order_rows(args: argparse.Namespace, state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "no_order_execution_performed": True,
            "no_order_request_constructed": True,
            "no_order_send_called": True,
            "no_order_check_called": True,
            "no_order_calc_profit_called": True,
            "no_positions_get_called": True,
            "no_orders_get_called": True,
            "no_history_orders_get_called": True,
            "no_history_deals_get_called": True,
            "order_calc_margin_called": state.get("order_calc_margin_called", False),
            "order_calc_margin_call_count": state.get("order_calc_margin_call_count", 0),
            "no_db_query_performed": True,
            "no_db_mutation_performed": True,
            "no_child_scripts_executed": True,
            "no_scheduler_added": True,
            "no_loop_added": True,
            "no_background_task_added": True,
            "no_trading_decision_performed": True,
            "no_demo_broker_approval_performed": True,
        }
    ]


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    status: str,
    source_nature: str,
    policy: dict[str, Any],
    state: dict[str, Any],
    snapshot: dict[str, Any],
    checklist: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    data = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "dry_run": bool(args.dry_run),
        "allow_broker_read": bool(args.allow_broker_read),
        "allow_order_calc_margin": bool(args.allow_order_calc_margin),
        "broker_read_performed": bool(state.get("broker_read_performed")),
        "mt5_import_performed": bool(state.get("mt5_import_attempted")),
        "mt5_connection_performed": bool(state.get("mt5_initialize_success")),
        "broker_safe_margin_validation_plan_dir": str(args.broker_safe_margin_validation_plan_dir),
        "risk_volume_shadow_plan_dir": str(args.risk_volume_shadow_plan_dir),
        "margin_feasibility_plan_dir": str(args.margin_feasibility_plan_dir),
        "canonical_registry_path": str(args.canonical_registry),
        "demo_execution_policy_path": str(args.demo_execution_policy),
        "validation_status": status,
        "source_nature": source_nature,
        "candidate_id": EXPECTED_CANDIDATE_ID,
        "symbol": args.symbol,
        "direction": args.direction,
        "intended_demo_equity": safe_float(policy.get("intended_demo_equity")),
        "risk_percent_max": safe_float(policy.get("risk_percent_max")),
        "risk_amount_max": safe_float(policy.get("risk_amount_max")),
        "max_margin_usage_warning_ratio": safe_float(policy.get("max_margin_usage_warning_ratio")),
        "max_margin_usage_ratio": safe_float(policy.get("max_margin_usage_ratio")),
        "account_mode_label": snapshot.get("account_mode_label"),
        "account_currency": snapshot.get("account_currency"),
        "account_equity": snapshot.get("account_equity"),
        "account_leverage": snapshot.get("account_leverage"),
        "account_equity_policy_status": state.get("account_equity_policy_status"),
        "symbol_visible": state.get("symbol_info", {}).get("visible"),
        "symbol_select_performed": state.get("symbol_select_performed", False),
        "spread_current_points": snapshot.get("spread_current_points"),
        "spread_within_policy": None if snapshot.get("spread_current_points") is None else snapshot.get("spread_current_points") <= EXPECTED_MAX_SPREAD_POINTS,
        "stepped_volume_lots": snapshot.get("margin_calc_volume_lots"),
        "margin_calc_side": snapshot.get("margin_calc_side"),
        "margin_calc_price": snapshot.get("margin_calc_price"),
        "broker_margin_estimate": snapshot.get("broker_margin_estimate"),
        "broker_margin_usage_ratio": snapshot.get("broker_margin_usage_ratio"),
        "static_estimated_margin_quote": snapshot.get("static_estimated_margin_quote"),
        "static_approximate_margin_usage_ratio": snapshot.get("static_approximate_margin_usage_ratio"),
        "order_calc_margin_called": state.get("order_calc_margin_called", False),
        "order_calc_margin_call_count": state.get("order_calc_margin_call_count", 0),
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_profit_called": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_db_query_performed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "checklist_row_count": len(checklist),
        "recommended_next_step": recommended_next_step(status, source_nature),
    }
    write_json(path, data)


def write_report(path: Path, *, args: argparse.Namespace, status: str, source_nature: str, snapshot: dict[str, Any], state: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Broker-Safe Margin Validation",
        "",
        "Broker-safe margin validation artifact.",
        "order_calc_margin is used only for margin estimation in this module.",
        "No order_send was called.",
        "No order_check was called.",
        "No order_calc_profit was called.",
        "No positions, orders, or history queries were called.",
        "No broker request payload was constructed.",
        "No order execution was performed.",
        "No demo approval was performed.",
        "No trading decision was made.",
        "Account fields are redacted or omitted from output.",
        "Fixture input remains non-actionable if source_nature is synthetic_fixture.",
        "The margin estimate may be broker-provided, but it is still not execution approval.",
        "No database query or mutation was performed.",
        "No scheduler, loop, daemon, or background behavior was added.",
        "",
        "## Input Overview",
        "",
        f"- broker_safe_margin_validation_plan_dir: `{args.broker_safe_margin_validation_plan_dir}`",
        f"- risk_volume_shadow_plan_dir: `{args.risk_volume_shadow_plan_dir}`",
        f"- margin_feasibility_plan_dir: `{args.margin_feasibility_plan_dir}`",
        f"- allow_broker_read: `{bool_text(bool(args.allow_broker_read))}`",
        f"- allow_order_calc_margin: `{bool_text(bool(args.allow_order_calc_margin))}`",
        f"- dry_run: `{bool_text(bool(args.dry_run))}`",
        f"- source_nature: `{source_nature}`",
        "",
        "## Margin Summary",
        "",
        f"- validation_status: `{status}`",
        f"- account_mode_label: `{snapshot.get('account_mode_label')}`",
        f"- account_currency: `{snapshot.get('account_currency')}`",
        f"- account_equity_policy_status: `{state.get('account_equity_policy_status')}`",
        f"- spread_current_points: `{snapshot.get('spread_current_points')}`",
        f"- margin_calc_side: `{snapshot.get('margin_calc_side')}`",
        f"- margin_calc_volume_lots: `{snapshot.get('margin_calc_volume_lots')}`",
        f"- margin_calc_price: `{snapshot.get('margin_calc_price')}`",
        f"- broker_margin_estimate: `{snapshot.get('broker_margin_estimate')}`",
        f"- broker_margin_usage_ratio: `{snapshot.get('broker_margin_usage_ratio')}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{recommended_next_step(status, source_nature)}`",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        lines.extend(f"- {row['warning_code']}: {row['message']}" for row in warnings)
    else:
        lines.append("- none")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_artifacts(args: argparse.Namespace, paths: dict[str, Path]) -> None:
    warnings: list[dict[str, Any]] = []
    registry, registry_error = read_json(Path(args.canonical_registry))
    policy, policy_error = read_json(Path(args.demo_execution_policy))
    plan, plan_error = read_json(Path(args.broker_safe_margin_validation_plan_dir) / PLAN_MANIFEST)
    risk_volume, risk_error = read_json(Path(args.risk_volume_shadow_plan_dir) / RISK_VOLUME_MANIFEST)
    margin_feasibility, margin_error = read_json(Path(args.margin_feasibility_plan_dir) / MARGIN_FEASIBILITY_MANIFEST)
    preflight = preflight_status(
        args=args,
        registry_error=registry_error,
        policy_error=policy_error,
        plan_error=plan_error,
        risk_error=risk_error,
        margin_error=margin_error,
        registry=registry,
        policy=policy,
        plan=plan,
        risk_volume=risk_volume,
        margin_feasibility=margin_feasibility,
        warnings=warnings,
    )
    source_nature = source_nature_for(plan, risk_volume, margin_feasibility)
    state = {
        "mt5_import_attempted": False,
        "mt5_initialize_attempted": False,
        "mt5_initialize_success": False,
        "terminal_info": {},
        "account_info": {},
        "symbol_info": {},
        "tick_info": {},
        "symbol_select_performed": False,
        "symbol_select_success": False,
        "account_mode_label": "not_queried",
        "is_demo_account": None,
        "account_equity_policy_status": "not_checked",
        "account_failures": [],
        "symbol_failures": [],
        "margin_calc_side": "SELL",
        "margin_calc_price": None,
        "broker_margin_estimate": None,
        "broker_margin_usage_ratio": None,
        "order_calc_margin_called": False,
        "order_calc_margin_call_count": 0,
        "broker_read_performed": False,
        "margin_calc_error": "",
        "import_error": "",
        "initialize_error": "",
        "mt5_module": None,
    }
    if not args.dry_run and preflight is None:
        state = inspect_mt5_and_margin(args, warnings, risk_volume, margin_feasibility)
    status = final_status(args, source_nature, preflight, state)
    snapshot = build_margin_snapshot(args=args, status=status, source_nature=source_nature, state=state, risk_volume=risk_volume, margin_feasibility=margin_feasibility)
    if status in {"broker_safe_margin_validation_available_with_margin_warning", "broker_safe_margin_validation_fixture_only_available_with_margin_warning"}:
        add_warning(warnings, args=args, warning_code="broker_margin_above_warning_threshold", message="Broker margin usage is above 50% warning threshold and within 70% cap.", source=args.mt5_package, blocking_warning=False)
    if status == "broker_safe_margin_validation_hold_margin_above_policy_cap":
        add_warning(warnings, args=args, warning_code="broker_margin_above_policy_cap", message="Broker margin usage is above 70% policy cap.", source=args.mt5_package, blocking_warning=False)
    checklist = checklist_rows(args, status, preflight, source_nature, state, snapshot)
    add_status_warnings(args, checklist, warnings)
    write_csv(paths["checklist"], checklist, CHECKLIST_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["no_order"], no_order_rows(args, state), NO_ORDER_FIELDNAMES)
    write_json(paths["margin_snapshot"], snapshot)
    write_manifest(paths["manifest"], args=args, output_dir=paths["manifest"].parent, status=status, source_nature=source_nature, policy=policy, state=state, snapshot=snapshot, checklist=checklist, warnings=warnings)
    write_report(paths["report"], args=args, status=status, source_nature=source_nature, snapshot=snapshot, state=state, warnings=warnings)


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / str(args.run_id)
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    runtime_args = argparse.Namespace(**vars(args))
    runtime_args.dry_run = effective_dry_run(args)
    build_artifacts(runtime_args, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run broker-safe read-only demo margin validation for the fixed candidate.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--broker-safe-margin-validation-plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--risk-volume-shadow-plan-dir", type=Path, default=DEFAULT_RISK_VOLUME_DIR)
    parser.add_argument("--margin-feasibility-plan-dir", type=Path, default=DEFAULT_MARGIN_FEASIBILITY_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_EXECUTION_POLICY)
    parser.add_argument("--symbol", default=EXPECTED_SYMBOL)
    parser.add_argument("--direction", default=EXPECTED_DIRECTION)
    parser.add_argument("--mt5-package", default="MetaTrader5")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-broker-read", action="store_true")
    parser.add_argument("--allow-order-calc-margin", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate broker-safe margin validation failed: {exc}")
        return 1
    print("Fixed-candidate broker-safe margin validation complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
