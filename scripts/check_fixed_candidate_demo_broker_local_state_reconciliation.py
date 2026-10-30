"""Check demo broker/local state reconciliation for the fixed candidate.

This module performs a controlled read-only MT5 demo state check. In real mode
it reads terminal/account/symbol facts and exactly one positions_get plus one
orders_get call for GBPUSD. It does not construct broker requests, execute
orders, call order check/calc/history functions, mutate local state, mutate a
database, run child scripts, schedule work, approve demo execution, or make a
trading decision.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_broker_local_state_reconciliation"
CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
CANDIDATE_SYMBOL = "GBPUSD"
CANDIDATE_TIMEFRAME = "M15"
CANDIDATE_DIRECTION = "short"
DEFAULT_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_future_request_construction_readiness_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_future_request_construction_readiness_plan_live_v1"
)
DEFAULT_MARGIN_VALIDATION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_broker_safe_margin_validation"
    / "gbpusd_short_h10_1_5_off_hours_demo_broker_safe_margin_validation_live_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_DEMO_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_STATE_JSON = BASE_DIR / "state" / "fixed_candidate_demo_state" / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_broker_local_state_reconciliation"

READINESS_MANIFEST = "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json"
MARGIN_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_manifest.json"
MARGIN_SNAPSHOT = "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_broker_local_state_reconciliation_report.md"
OUTPUT_CHECKLIST = "fixed_candidate_demo_broker_local_state_reconciliation_checklist.csv"
OUTPUT_BROKER_SNAPSHOT = "fixed_candidate_demo_broker_local_state_reconciliation_broker_snapshot.json"
OUTPUT_LOCAL_STATE_SNAPSHOT = "fixed_candidate_demo_broker_local_state_reconciliation_local_state_snapshot.json"
OUTPUT_MATCHING_FIELDS = "fixed_candidate_demo_broker_local_state_reconciliation_matching_fields.csv"
OUTPUT_STATUS = "fixed_candidate_demo_broker_local_state_reconciliation_status.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_broker_local_state_reconciliation_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_broker_local_state_reconciliation_no_order_evidence.csv"

ACCEPTABLE_MARGIN_VALIDATION_STATUSES = {
    "broker_safe_margin_validation_available",
    "broker_safe_margin_validation_available_with_margin_warning",
}
VOLUME_TOLERANCE = 1e-9

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
MATCHING_FIELDNAMES = [
    "run_id",
    "field_name",
    "local_value",
    "broker_value",
    "expected_value",
    "match_status",
    "caveat",
]
STATUS_FIELDNAMES = [
    "run_id",
    "reconciliation_status",
    "status_area",
    "observed_value",
    "expected_value",
    "blocking_if_failed",
    "caveat",
]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
NO_ORDER_FIELDNAMES = [
    "run_id",
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_history_orders_get_called",
    "no_history_deals_get_called",
    "positions_get_called",
    "orders_get_called",
    "positions_get_call_count",
    "orders_get_call_count",
    "future_state_json_written",
    "no_db_mutation_performed",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "no_trading_decision_performed",
    "no_demo_broker_approval_performed",
    "evidence_label",
    "caveat",
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


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def object_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "_asdict"):
        try:
            return dict(value._asdict())
        except (TypeError, ValueError):
            return {}
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return {}


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


def effective_dry_run(args: argparse.Namespace) -> bool:
    return bool(args.dry_run) or not bool(args.allow_broker_read)


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "checklist": output_dir / OUTPUT_CHECKLIST,
        "broker_snapshot": output_dir / OUTPUT_BROKER_SNAPSHOT,
        "local_state_snapshot": output_dir / OUTPUT_LOCAL_STATE_SNAPSHOT,
        "matching_fields": output_dir / OUTPUT_MATCHING_FIELDS,
        "status": output_dir / OUTPUT_STATUS,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def validate_canonical_registry(registry: dict[str, Any]) -> bool:
    return (
        registry.get("candidate_id") == "gbpusd_short_h10_1_5_off_hours"
        and registry.get("symbol") == "GBPUSD"
        and registry.get("timeframe") == "M15"
        and registry.get("direction") == "short"
        and registry.get("spread_unit") == "broker_points"
        and safe_float(registry.get("max_spread_points")) == 15.0
        and (registry.get("max_open_positions") in ("", None) or safe_float(registry.get("max_open_positions")) == 1.0)
    )


def validate_demo_policy(policy: dict[str, Any]) -> bool:
    boundaries = policy.get("safety_boundaries")
    if not isinstance(boundaries, dict):
        return False
    return (
        policy.get("candidate_id") == "gbpusd_short_h10_1_5_off_hours"
        and policy.get("symbol") == "GBPUSD"
        and policy.get("timeframe") == "M15"
        and policy.get("direction") == "short"
        and policy.get("spread_unit") == "broker_points"
        and safe_float(policy.get("max_spread_points")) == 15.0
        and safe_float(policy.get("max_open_positions")) == 1.0
        and boundaries.get("real_money_allowed") is False
        and boundaries.get("order_execution_allowed") is False
        and boundaries.get("order_request_construction_allowed") is False
        and boundaries.get("order_check_allowed") is False
        and boundaries.get("order_calc_allowed") is False
        and boundaries.get("manual_approval_required_before_any_future_demo_order") is True
    )


def validate_readiness(manifest: dict[str, Any]) -> tuple[bool, str]:
    if manifest.get("plan_status") != "future_request_construction_readiness_plan_available_no_order":
        return False, "blocked_unacceptable_readiness_status"
    if manifest.get("source_nature") != "live_data_shadow_signal":
        return False, "blocked_unacceptable_readiness_status"
    false_flags = (
        "request_construction_allowed_now",
        "broker_request_constructed",
        "broker_payload_constructed",
        "order_object_constructed",
        "order_execution_allowed",
    )
    for flag in false_flags:
        if flag in manifest and manifest.get(flag) is not False:
            return False, "blocked_unsafe_readiness_boundary"
    return True, ""


def validate_margin(manifest: dict[str, Any], snapshot: dict[str, Any]) -> tuple[bool, str]:
    manifest_status = manifest.get("validation_status")
    snapshot_status = snapshot.get("validation_status")
    manifest_volume = safe_float(manifest.get("stepped_volume_lots"))
    snapshot_volume = safe_float(snapshot.get("margin_calc_volume_lots"))
    volume_matches = (
        manifest_volume is not None
        and manifest_volume > 0
        and snapshot_volume is not None
        and snapshot_volume > 0
        and abs(manifest_volume - snapshot_volume) <= VOLUME_TOLERANCE
    )
    if manifest_status not in ACCEPTABLE_MARGIN_VALIDATION_STATUSES:
        return False, "blocked_unacceptable_margin_validation_status"
    if manifest.get("source_nature") != "live_data_shadow_signal":
        return False, "blocked_unacceptable_margin_validation_status"
    checks = (
        manifest.get("account_mode_label") == "demo",
        manifest.get("account_currency") == "EUR",
        manifest.get("account_equity_policy_status") == "within_10pct",
        safe_float(manifest.get("broker_margin_usage_ratio")) is not None
        and safe_float(manifest.get("broker_margin_usage_ratio")) <= 0.7,
        manifest.get("spread_within_policy") is True,
        volume_matches,
        snapshot_status in ("", None) or snapshot_status in ACCEPTABLE_MARGIN_VALIDATION_STATUSES,
    )
    return (all(checks), "" if all(checks) else "blocked_unacceptable_margin_validation_status")


def classify_account_mode(mt5_module: Any, account_info: dict[str, Any]) -> tuple[str, bool | None]:
    raw = account_info.get("trade_mode")
    demo_value = getattr(mt5_module, "ACCOUNT_TRADE_MODE_DEMO", None)
    real_value = getattr(mt5_module, "ACCOUNT_TRADE_MODE_REAL", None)
    contest_value = getattr(mt5_module, "ACCOUNT_TRADE_MODE_CONTEST", None)
    if demo_value is not None and raw == demo_value:
        return "demo", True
    if real_value is not None and raw == real_value:
        return "real", False
    if contest_value is not None and raw == contest_value:
        return "contest", False
    text = " ".join(str(account_info.get(field, "")) for field in ("server", "name", "company")).lower()
    if "demo" in text:
        return "demo", True
    if raw in ("demo", "DEMO"):
        return "demo", True
    return "unknown", None


def equity_policy_status(equity: float | None, intended: float) -> str:
    if equity is None:
        return "unknown"
    lower = intended * 0.9
    upper = intended * 1.1
    return "within_10pct" if lower <= equity <= upper else "outside_10pct"


def redact_account(account: dict[str, Any], mode_label: str, is_demo: bool | None) -> dict[str, Any]:
    return {
        "account_trade_mode_raw": account.get("trade_mode"),
        "account_mode_label": mode_label,
        "is_demo_account": is_demo,
        "currency": account.get("currency"),
        "equity_present": account.get("equity") not in ("", None),
        "balance_present": account.get("balance") not in ("", None),
        "leverage": account.get("leverage"),
        "trade_allowed": account.get("trade_allowed"),
        "trade_expert": account.get("trade_expert"),
        "redaction_applied": True,
    }


def sanitize_position(position: dict[str, Any], mt5_module: Any) -> dict[str, Any]:
    position_type = position.get("type")
    sell_value = getattr(mt5_module, "POSITION_TYPE_SELL", 1)
    buy_value = getattr(mt5_module, "POSITION_TYPE_BUY", 0)
    if position_type == sell_value:
        side = "SELL"
    elif position_type == buy_value:
        side = "BUY"
    else:
        side = str(position_type)
    return {
        "symbol": position.get("symbol"),
        "type": position_type,
        "side_label": side,
        "volume": position.get("volume"),
        "price_open": position.get("price_open"),
        "sl": position.get("sl"),
        "tp": position.get("tp"),
        "magic_present": position.get("magic") not in ("", None),
        "comment_present": bool(position.get("comment")),
    }


def sanitize_order(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": order.get("symbol"),
        "type": order.get("type"),
        "volume_current": order.get("volume_current", order.get("volume")),
        "price_open": order.get("price_open"),
        "sl": order.get("sl"),
        "tp": order.get("tp"),
        "magic_present": order.get("magic") not in ("", None),
        "comment_present": bool(order.get("comment")),
    }


def load_local_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "local_state_exists": False,
            "local_state_status": "local_state_missing",
            "local_state": {},
            "local_state_error": "",
        }
    data, error = read_json(path)
    if error:
        return {
            "local_state_exists": True,
            "local_state_status": "local_state_malformed",
            "local_state": {},
            "local_state_error": error,
        }
    state_text = " ".join(str(data.get(key, "")) for key in ("state", "status", "local_state_status", "trade_status")).lower()
    has_open = any(data.get(key) is True for key in ("has_open_trade", "has_open_demo_trade", "has_open_paper_trade", "open_trade_exists"))
    has_pending = any(data.get(key) is True for key in ("has_pending_trade", "pending_request_exists", "local_pending"))
    if "open" in state_text:
        has_open = True
    if "pending" in state_text:
        has_pending = True
    if has_open:
        status = "local_state_open"
    elif has_pending:
        status = "local_state_pending"
    else:
        status = "local_state_flat"
    return {
        "local_state_exists": True,
        "local_state_status": status,
        "local_state": data,
        "local_state_error": "",
    }


def run_broker_reads(args: argparse.Namespace, warnings: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "mt5_import_attempted": False,
        "mt5_initialize_attempted": False,
        "mt5_initialize_success": False,
        "terminal_info": {},
        "account_info_raw": {},
        "account_snapshot_redacted": {},
        "symbol_info": {},
        "positions": [],
        "orders": [],
        "positions_get_called": False,
        "orders_get_called": False,
        "positions_get_call_count": 0,
        "orders_get_call_count": 0,
        "broker_read_status": "",
        "account_mode_label": "",
        "is_demo_account": None,
        "account_currency": "",
        "account_equity": None,
        "account_equity_policy_status": "",
        "broker_read_performed": False,
    }
    if args.dry_run:
        state["broker_read_status"] = "broker_read_dry_run_no_broker_read"
        return state
    state["mt5_import_attempted"] = True
    try:
        mt5_module = importlib.import_module("MetaTrader5")
    except ImportError as exc:
        state["broker_read_status"] = "blocked_mt5_import_failure"
        warnings.append(warning_row(run_id=args.run_id, warning_code="mt5_import_failure", message=str(exc), source="MetaTrader5", blocking_warning=True))
        return state
    state["mt5_initialize_attempted"] = True
    try:
        initialized = bool(mt5_module.initialize())
    except Exception as exc:  # pragma: no cover - defensive against external package exceptions.
        initialized = False
        warnings.append(warning_row(run_id=args.run_id, warning_code="mt5_initialize_exception", message=str(exc), source="MetaTrader5", blocking_warning=True))
    state["mt5_initialize_success"] = initialized
    if not initialized:
        state["broker_read_status"] = "blocked_mt5_initialize_failure"
        warnings.append(warning_row(run_id=args.run_id, warning_code="mt5_initialize_failure", message="MT5 initialization failed.", source="MetaTrader5", blocking_warning=True))
        return state
    try:
        terminal = object_to_dict(mt5_module.terminal_info())
        account = object_to_dict(mt5_module.account_info())
        symbol = object_to_dict(mt5_module.symbol_info(CANDIDATE_SYMBOL))
        state["broker_read_performed"] = bool(terminal or account or symbol)
        if not terminal:
            state["broker_read_status"] = "blocked_terminal_info_unavailable"
            warnings.append(warning_row(run_id=args.run_id, warning_code="terminal_info_unavailable", message="terminal_info unavailable.", source="MetaTrader5", blocking_warning=True))
            return state
        if not account:
            state["broker_read_status"] = "blocked_account_info_unavailable"
            warnings.append(warning_row(run_id=args.run_id, warning_code="account_info_unavailable", message="account_info unavailable.", source="MetaTrader5", blocking_warning=True))
            return state
        mode_label, is_demo = classify_account_mode(mt5_module, account)
        equity = safe_float(account.get("equity"))
        intended = safe_float(policy.get("intended_demo_equity")) or 1000.0
        equity_status = equity_policy_status(equity, intended)
        state.update(
            {
                "terminal_info": {
                    "connected": terminal.get("connected"),
                    "trade_allowed": terminal.get("trade_allowed"),
                    "community_account_present": terminal.get("community_account") not in ("", None),
                },
                "account_info_raw": account,
                "account_snapshot_redacted": redact_account(account, mode_label, is_demo),
                "account_mode_label": mode_label,
                "is_demo_account": is_demo,
                "account_currency": account.get("currency"),
                "account_equity": equity,
                "account_equity_policy_status": equity_status,
                "symbol_info": {
                    "symbol": symbol.get("name", CANDIDATE_SYMBOL),
                    "visible": symbol.get("visible"),
                    "select": symbol.get("select"),
                    "trade_mode": symbol.get("trade_mode"),
                    "digits": symbol.get("digits"),
                    "point": symbol.get("point"),
                    "spread": symbol.get("spread"),
                    "volume_min": symbol.get("volume_min"),
                    "volume_max": symbol.get("volume_max"),
                    "volume_step": symbol.get("volume_step"),
                    "trade_stops_level": symbol.get("trade_stops_level"),
                    "trade_freeze_level": symbol.get("trade_freeze_level"),
                },
            }
        )
        if is_demo is not True:
            state["broker_read_status"] = "blocked_non_demo_account"
            warnings.append(warning_row(run_id=args.run_id, warning_code="non_demo_account", message="Account is not confirmed demo.", source="MetaTrader5.account_info", blocking_warning=True))
            return state
        if account.get("currency") != "EUR":
            state["broker_read_status"] = "blocked_account_currency_mismatch"
            warnings.append(warning_row(run_id=args.run_id, warning_code="account_currency_mismatch", message="Account currency is not EUR.", source="MetaTrader5.account_info", blocking_warning=True))
            return state
        if equity_status != "within_10pct":
            state["broker_read_status"] = "blocked_account_equity_outside_policy"
            warnings.append(warning_row(run_id=args.run_id, warning_code="account_equity_outside_policy", message="Account equity is outside intended policy band.", source="MetaTrader5.account_info", blocking_warning=True))
            return state
        if not symbol or as_bool(symbol.get("visible")) is not True:
            state["broker_read_status"] = "blocked_symbol_unavailable"
            warnings.append(warning_row(run_id=args.run_id, warning_code="symbol_unavailable", message="Symbol info is missing or not visible.", source="MetaTrader5.symbol_info", blocking_warning=True))
            return state
        try:
            raw_positions = mt5_module.positions_get(symbol=CANDIDATE_SYMBOL)
        except Exception as exc:  # pragma: no cover - defensive.
            raw_positions = None
            warnings.append(warning_row(run_id=args.run_id, warning_code="positions_get_failure", message=str(exc), source="MetaTrader5.positions_get", blocking_warning=True))
        state["positions_get_called"] = True
        state["positions_get_call_count"] = 1
        if raw_positions is None:
            state["broker_read_status"] = "blocked_positions_get_failure"
            return state
        try:
            raw_orders = mt5_module.orders_get(symbol=CANDIDATE_SYMBOL)
        except Exception as exc:  # pragma: no cover - defensive.
            raw_orders = None
            warnings.append(warning_row(run_id=args.run_id, warning_code="orders_get_failure", message=str(exc), source="MetaTrader5.orders_get", blocking_warning=True))
        state["orders_get_called"] = True
        state["orders_get_call_count"] = 1
        if raw_orders is None:
            state["broker_read_status"] = "blocked_orders_get_failure"
            return state
        state["positions"] = [sanitize_position(object_to_dict(item), mt5_module) for item in list(raw_positions)]
        state["orders"] = [sanitize_order(object_to_dict(item)) for item in list(raw_orders)]
        state["broker_read_status"] = "broker_reads_available"
        state["broker_read_performed"] = True
        return state
    finally:
        shutdown = getattr(mt5_module, "shutdown", None)
        if callable(shutdown):
            shutdown()


def decide_reconciliation(local: dict[str, Any], broker: dict[str, Any], expected_volume: float) -> str:
    if broker["broker_read_status"].startswith("blocked_"):
        return broker["broker_read_status"]
    if broker["broker_read_status"] in {"dry_run_no_broker_reads", "broker_read_dry_run_no_broker_read"}:
        return "broker_local_reconciliation_dry_run_no_broker_read"
    if local["local_state_status"] == "local_state_malformed":
        return "broker_local_reconciliation_hold_local_state_malformed"
    positions = broker.get("positions", [])
    orders = broker.get("orders", [])
    position_count = len(positions)
    order_count = len(orders)
    local_status = local["local_state_status"]
    if order_count > 0:
        return "broker_local_reconciliation_hold_broker_pending_order_detected"
    if position_count > 1:
        return "broker_local_reconciliation_hold_duplicate_broker_positions"
    if position_count == 0:
        if local_status == "local_state_missing":
            return "broker_local_reconciliation_clean_no_local_no_broker"
        if local_status == "local_state_pending":
            return "broker_local_reconciliation_clean_local_pending_no_broker"
        if local_status == "local_state_open":
            return "broker_local_reconciliation_hold_local_open_broker_none"
        return "broker_local_reconciliation_clean_no_local_no_broker"
    position = positions[0]
    if local_status == "local_state_missing":
        return "broker_local_reconciliation_hold_local_missing_broker_open"
    if local_status == "local_state_pending":
        return "broker_local_reconciliation_hold_local_pending_broker_open"
    if position.get("symbol") != "GBPUSD" or position.get("side_label") != "SELL":
        return "broker_local_reconciliation_hold_symbol_or_side_mismatch"
    local_state = local.get("local_state", {})
    local_volume = safe_float(local_state.get("stepped_volume_lots") or local_state.get("volume_lots") or local_state.get("volume"))
    broker_volume = safe_float(position.get("volume"))
    if local_volume is not None and broker_volume is not None and abs(local_volume - broker_volume) > 1e-9:
        return "broker_local_reconciliation_hold_volume_mismatch"
    if broker_volume is not None and abs(broker_volume - expected_volume) > 1e-9:
        return "broker_local_reconciliation_hold_volume_mismatch"
    local_sl = safe_float(local_state.get("sl_price_preview") or local_state.get("sl"))
    local_tp = safe_float(local_state.get("tp_price_preview") or local_state.get("tp"))
    broker_sl = safe_float(position.get("sl"))
    broker_tp = safe_float(position.get("tp"))
    if local_sl is not None and broker_sl is not None and abs(local_sl - broker_sl) > 1e-9:
        return "broker_local_reconciliation_hold_sl_tp_mismatch"
    if local_tp is not None and broker_tp is not None and abs(local_tp - broker_tp) > 1e-9:
        return "broker_local_reconciliation_hold_sl_tp_mismatch"
    return "broker_local_reconciliation_hold_local_pending_broker_open"


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    readiness_path = Path(args.future_request_construction_readiness_plan_dir) / READINESS_MANIFEST
    margin_manifest_path = Path(args.broker_safe_margin_validation_dir) / MARGIN_MANIFEST
    margin_snapshot_path = Path(args.broker_safe_margin_validation_dir) / MARGIN_SNAPSHOT
    registry, registry_error = read_json(Path(args.canonical_registry))
    policy, policy_error = read_json(Path(args.demo_execution_policy))
    readiness, readiness_error = read_json(readiness_path)
    margin, margin_error = read_json(margin_manifest_path)
    margin_snapshot, margin_snapshot_error = read_json(margin_snapshot_path)
    inputs = {
        "registry": registry,
        "policy": policy,
        "readiness": readiness,
        "margin": margin,
        "margin_snapshot": margin_snapshot,
        "paths": {
            "readiness": readiness_path,
            "margin_manifest": margin_manifest_path,
            "margin_snapshot": margin_snapshot_path,
            "registry": Path(args.canonical_registry),
            "policy": Path(args.demo_execution_policy),
        },
        "errors": {
            "registry": registry_error,
            "policy": policy_error,
            "readiness": readiness_error,
            "margin": margin_error,
            "margin_snapshot": margin_snapshot_error,
        },
    }
    if registry_error:
        warnings.append(warning_row(run_id=args.run_id, warning_code="canonical_registry_unreadable", message=registry_error, source=args.canonical_registry, blocking_warning=True))
    if policy_error:
        warnings.append(warning_row(run_id=args.run_id, warning_code="demo_execution_policy_unreadable", message=policy_error, source=args.demo_execution_policy, blocking_warning=True))
    if readiness_error:
        warnings.append(warning_row(run_id=args.run_id, warning_code="readiness_manifest_unreadable", message=readiness_error, source=readiness_path, blocking_warning=True))
    if margin_error:
        warnings.append(warning_row(run_id=args.run_id, warning_code="margin_validation_manifest_unreadable", message=margin_error, source=margin_manifest_path, blocking_warning=True))
    if margin_snapshot_error:
        warnings.append(warning_row(run_id=args.run_id, warning_code="margin_snapshot_unreadable", message=margin_snapshot_error, source=margin_snapshot_path, blocking_warning=True))
    return inputs


def initial_block_status(inputs: dict[str, Any]) -> str | None:
    errors = inputs["errors"]
    if errors["readiness"] == "missing":
        return "blocked_missing_readiness_manifest"
    if errors["margin"] == "missing":
        return "blocked_missing_margin_validation_manifest"
    if errors["margin_snapshot"] == "missing":
        return "blocked_missing_margin_snapshot"
    if errors["registry"] or not validate_canonical_registry(inputs["registry"]):
        return "blocked_noncanonical_candidate"
    if errors["policy"] or not validate_demo_policy(inputs["policy"]):
        return "blocked_noncanonical_demo_execution_policy"
    readiness_ok, readiness_status = validate_readiness(inputs["readiness"])
    if not readiness_ok:
        return readiness_status
    margin_ok, margin_status = validate_margin(inputs["margin"], inputs["margin_snapshot"])
    if not margin_ok:
        return margin_status
    return None


def checklist_row(args: argparse.Namespace, area: str, name: str, status: str, observed: Any, expected: Any, source: Any, warning_code: str = "") -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "check_area": area,
        "check_name": name,
        "check_status": status,
        "observed_value": observed,
        "expected_value": expected,
        "blocking_if_failed": status in {"failed", "blocked"},
        "evidence_source": source,
        "caveat": "read_only_no_request_no_execution",
        "warning_code": warning_code,
    }


def build_rows(args: argparse.Namespace, inputs: dict[str, Any], local: dict[str, Any], broker: dict[str, Any], status: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    checklist = [
        checklist_row(args, "source", "canonical registry", "passed" if validate_canonical_registry(inputs["registry"]) else "failed", inputs["registry"].get("candidate_id"), "gbpusd_short_h10_1_5_off_hours", inputs["paths"]["registry"], "noncanonical_candidate"),
        checklist_row(args, "source", "demo execution policy", "passed" if validate_demo_policy(inputs["policy"]) else "failed", inputs["policy"].get("policy_id"), "no-order policy", inputs["paths"]["policy"], "noncanonical_demo_execution_policy"),
        checklist_row(args, "source", "future request readiness", "passed" if validate_readiness(inputs["readiness"])[0] else "failed", inputs["readiness"].get("plan_status"), "future_request_construction_readiness_plan_available_no_order", inputs["paths"]["readiness"], "readiness_status"),
        checklist_row(args, "source", "broker-safe margin validation", "passed" if validate_margin(inputs["margin"], inputs["margin_snapshot"])[0] else "failed", inputs["margin"].get("validation_status"), "available status, margin <= 0.70, spread ok, coherent margin volume", inputs["paths"]["margin_manifest"], "margin_status"),
        checklist_row(args, "broker", "terminal info read", "planned_not_verified" if args.dry_run else ("passed" if broker.get("terminal_info") else "failed"), bool(broker.get("terminal_info")), True, "MetaTrader5.terminal_info", "terminal_info_unavailable"),
        checklist_row(args, "broker", "account info read", "planned_not_verified" if args.dry_run else ("passed" if broker.get("account_snapshot_redacted") else "failed"), bool(broker.get("account_snapshot_redacted")), True, "MetaTrader5.account_info", "account_info_unavailable"),
        checklist_row(args, "broker", "symbol info read", "planned_not_verified" if args.dry_run else ("passed" if broker.get("symbol_info") else "failed"), bool(broker.get("symbol_info")), True, "MetaTrader5.symbol_info", "symbol_unavailable"),
        checklist_row(args, "broker", "positions_get once", "planned_not_verified" if args.dry_run else ("passed" if broker.get("positions_get_call_count") == 1 else "failed"), broker.get("positions_get_call_count", 0), 1, "MetaTrader5.positions_get", "positions_get_failure"),
        checklist_row(args, "broker", "orders_get once", "planned_not_verified" if args.dry_run else ("passed" if broker.get("orders_get_call_count") == 1 else "failed"), broker.get("orders_get_call_count", 0), 1, "MetaTrader5.orders_get", "orders_get_failure"),
        checklist_row(args, "local", "future state read only", "passed", local.get("local_state_status"), "read-only or missing", args.future_state_json, "future_state_not_mutated"),
    ]
    matching = [
        {"run_id": args.run_id, "field_name": "symbol", "local_value": "GBPUSD", "broker_value": broker.get("symbol_info", {}).get("symbol", ""), "expected_value": "GBPUSD", "match_status": "planned_not_verified" if args.dry_run else ("matched" if broker.get("symbol_info", {}).get("symbol") == "GBPUSD" else "unmatched"), "caveat": "read_only"},
        {"run_id": args.run_id, "field_name": "account_currency", "local_value": "EUR", "broker_value": broker.get("account_currency", ""), "expected_value": "EUR", "match_status": "planned_not_verified" if args.dry_run else ("matched" if broker.get("account_currency") == "EUR" else "unmatched"), "caveat": "redacted_account_snapshot"},
        {"run_id": args.run_id, "field_name": "broker_position_count_symbol", "local_value": local.get("local_state_status"), "broker_value": len(broker.get("positions", [])), "expected_value": "0 before future request construction", "match_status": "planned_not_verified" if args.dry_run else ("matched" if len(broker.get("positions", [])) == 0 else "hold"), "caveat": "max_open_positions_1"},
        {"run_id": args.run_id, "field_name": "broker_pending_order_count_symbol", "local_value": local.get("local_state_status"), "broker_value": len(broker.get("orders", [])), "expected_value": "0 before future request construction", "match_status": "planned_not_verified" if args.dry_run else ("matched" if len(broker.get("orders", [])) == 0 else "hold"), "caveat": "pending_orders_block"},
    ]
    status_rows = [
        {"run_id": args.run_id, "reconciliation_status": status, "status_area": "local_state", "observed_value": local.get("local_state_status"), "expected_value": "missing/flat/pending only if broker clear", "blocking_if_failed": status.startswith("blocked_") or "_hold_" in status, "caveat": "future_state_json_not_written"},
        {"run_id": args.run_id, "reconciliation_status": status, "status_area": "broker_positions", "observed_value": len(broker.get("positions", [])), "expected_value": "0", "blocking_if_failed": len(broker.get("positions", [])) > 0, "caveat": "max_open_positions_1"},
        {"run_id": args.run_id, "reconciliation_status": status, "status_area": "broker_pending_orders", "observed_value": len(broker.get("orders", [])), "expected_value": "0", "blocking_if_failed": len(broker.get("orders", [])) > 0, "caveat": "pending_orders_block_future_request"},
    ]
    return checklist, matching, status_rows


def no_order_evidence(args: argparse.Namespace, broker: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "no_order_execution_performed": True,
            "no_order_request_constructed": True,
            "no_order_send_called": True,
            "no_order_check_called": True,
            "no_order_calc_margin_called": True,
            "no_order_calc_profit_called": True,
            "no_history_orders_get_called": True,
            "no_history_deals_get_called": True,
            "positions_get_called": bool(broker.get("positions_get_called")),
            "orders_get_called": bool(broker.get("orders_get_called")),
            "positions_get_call_count": int(broker.get("positions_get_call_count", 0)),
            "orders_get_call_count": int(broker.get("orders_get_call_count", 0)),
            "future_state_json_written": False,
            "no_db_mutation_performed": True,
            "no_scheduler_added": True,
            "no_loop_added": True,
            "no_background_task_added": True,
            "no_trading_decision_performed": True,
            "no_demo_broker_approval_performed": True,
            "evidence_label": "read_only_reconciliation_no_order_boundary",
            "caveat": "positions_orders_read_only_when_not_dry_run",
        }
    ]


def write_report(path: Path, args: argparse.Namespace, status: str, broker: dict[str, Any], local: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Broker/Local State Reconciliation",
        "",
        "Read-only demo broker/local state reconciliation check.",
        "No broker request dictionary was constructed.",
        "No executable order object was constructed.",
        "No order execution was performed.",
        "No send/check/calc/history broker functions were called.",
        "The only broker state reads in real mode are terminal/account/symbol facts, one positions_get call, and one orders_get call.",
        "No future state JSON was written or created.",
        "No database mutation, child script, scheduler, loop, background task, demo approval, or trading decision was performed.",
        "",
        "## Inputs",
        "",
        f"- readiness_plan_dir: `{args.future_request_construction_readiness_plan_dir}`",
        f"- broker_safe_margin_validation_dir: `{args.broker_safe_margin_validation_dir}`",
        f"- future_state_json: `{args.future_state_json}`",
        f"- allow_broker_read: `{bool_text(bool(args.allow_broker_read))}`",
        f"- dry_run: `{bool_text(bool(args.dry_run))}`",
        "",
        "## Result",
        "",
        f"- reconciliation_status: `{status}`",
        f"- account_mode_label: `{broker.get('account_mode_label', '')}`",
        f"- account_currency: `{broker.get('account_currency', '')}`",
        f"- account_equity_policy_status: `{broker.get('account_equity_policy_status', '')}`",
        f"- broker_position_count_symbol: `{len(broker.get('positions', []))}`",
        f"- broker_pending_order_count_symbol: `{len(broker.get('orders', []))}`",
        f"- local_state_status: `{local.get('local_state_status', '')}`",
        "",
        "## Warnings",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(path: Path, args: argparse.Namespace, output_dir: Path, inputs: dict[str, Any], status: str, broker: dict[str, Any], local: dict[str, Any], warnings: list[dict[str, Any]], paths: dict[str, Path]) -> None:
    manifest = {
        "run_id": args.run_id,
        "created_at_utc": utc_now_text(),
        "output_dir": str(output_dir),
        "reconciliation_status": status,
        "source_nature": inputs["readiness"].get("source_nature") or inputs["margin"].get("source_nature"),
        "candidate_id": inputs["registry"].get("candidate_id", "gbpusd_short_h10_1_5_off_hours"),
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "allow_broker_read": bool(args.allow_broker_read),
        "dry_run": bool(args.dry_run),
        "broker_read_performed": bool(broker.get("broker_read_performed")),
        "mt5_import_performed": bool(broker.get("mt5_import_attempted")),
        "mt5_connection_performed": bool(broker.get("mt5_initialize_success")),
        "account_mode_label": broker.get("account_mode_label"),
        "account_currency": broker.get("account_currency"),
        "account_equity_policy_status": broker.get("account_equity_policy_status"),
        "broker_position_count_symbol": len(broker.get("positions", [])),
        "broker_pending_order_count_symbol": len(broker.get("orders", [])),
        "local_state_status": local.get("local_state_status"),
        "local_state_exists": local.get("local_state_exists"),
        "max_open_positions": 1,
        "request_construction_allowed_now": False,
        "order_execution_allowed": False,
        "demo_approval_performed": False,
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "output_files": {key: str(value) for key, value in paths.items()},
        "positions_get_called": bool(broker.get("positions_get_called")),
        "orders_get_called": bool(broker.get("orders_get_called")),
        "positions_get_call_count": int(broker.get("positions_get_call_count", 0)),
        "orders_get_call_count": int(broker.get("orders_get_call_count", 0)),
        "future_state_json_written": False,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def broker_snapshot(broker: dict[str, Any]) -> dict[str, Any]:
    return {
        "terminal_info": broker.get("terminal_info", {}),
        "account_snapshot_redacted": broker.get("account_snapshot_redacted", {}),
        "symbol_info": broker.get("symbol_info", {}),
        "positions": broker.get("positions", []),
        "orders": broker.get("orders", []),
        "positions_get_called": broker.get("positions_get_called", False),
        "orders_get_called": broker.get("orders_get_called", False),
        "positions_get_call_count": broker.get("positions_get_call_count", 0),
        "orders_get_call_count": broker.get("orders_get_call_count", 0),
        "broker_read_performed": broker.get("broker_read_performed", False),
    }


def local_state_snapshot(local: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "future_state_json": str(args.future_state_json),
        "local_state_exists": local.get("local_state_exists"),
        "local_state_status": local.get("local_state_status"),
        "local_state_error": local.get("local_state_error"),
        "local_state_read_only": True,
        "future_state_json_written": False,
        "local_state": local.get("local_state", {}),
    }


def build_artifacts(args: argparse.Namespace, paths: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    inputs = load_inputs(args, warnings)
    local = load_local_state(Path(args.future_state_json))
    initial_status = initial_block_status(inputs)
    if initial_status:
        status = initial_status
        broker = run_broker_reads(argparse.Namespace(**{**vars(args), "dry_run": True}), warnings, inputs.get("policy", {}))
    else:
        broker = run_broker_reads(args, warnings, inputs["policy"])
        expected_volume = safe_float(inputs["margin"].get("stepped_volume_lots")) or safe_float(inputs["margin_snapshot"].get("margin_calc_volume_lots")) or 0.0
        status = decide_reconciliation(local, broker, expected_volume)
    checklist, matching, status_rows = build_rows(args, inputs, local, broker, status)
    write_csv(paths["checklist"], checklist, CHECKLIST_FIELDNAMES)
    write_csv(paths["matching_fields"], matching, MATCHING_FIELDNAMES)
    write_csv(paths["status"], status_rows, STATUS_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["no_order"], no_order_evidence(args, broker), NO_ORDER_FIELDNAMES)
    paths["broker_snapshot"].write_text(json.dumps(broker_snapshot(broker), indent=2, sort_keys=True), encoding="utf-8")
    paths["local_state_snapshot"].write_text(json.dumps(local_state_snapshot(local, args), indent=2, sort_keys=True), encoding="utf-8")
    write_report(paths["report"], args, status, broker, local, warnings)
    write_manifest(paths["manifest"], args, output_dir, inputs, status, broker, local, warnings, paths)
    return {"status": status, "warnings": warnings}


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    runtime_args = argparse.Namespace(**vars(args))
    runtime_args.dry_run = effective_dry_run(args)
    build_artifacts(runtime_args, paths, output_dir)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check fixed-candidate demo broker/local state reconciliation in read-only mode.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--future-request-construction-readiness-plan-dir", type=Path, default=DEFAULT_READINESS_DIR)
    parser.add_argument("--broker-safe-margin-validation-dir", type=Path, default=DEFAULT_MARGIN_VALIDATION_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_DEMO_EXECUTION_POLICY)
    parser.add_argument("--future-state-json", type=Path, default=DEFAULT_FUTURE_STATE_JSON)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-broker-read", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, csv.Error) as exc:
        print(f"Fixed-candidate broker/local state reconciliation failed: {exc}")
        return 1
    print("Fixed-candidate broker/local state reconciliation complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
