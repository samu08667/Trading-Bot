"""Read-only/no-order demo environment checker for the fixed candidate.

The checker can optionally inspect MT5 environment facts with a demo terminal:
terminal info, account info, symbol info, and symbol tick info. It never creates
trade requests, never sends or validates orders, never queries positions/orders,
never mutates the database, and never makes candidate-quality or trading
decisions.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_environment_check"
DEFAULT_DEMO_ENVIRONMENT_CHECK_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_environment_check_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_environment_check_plan_spread15_v1"
)
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR / "config" / "paper_demo" / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_environment_check"

PLAN_MANIFEST = "fixed_candidate_demo_environment_check_plan_manifest.json"
PLAN_REPORT = "fixed_candidate_demo_environment_check_plan_report.md"
PLAN_REQUIREMENTS = "fixed_candidate_demo_environment_check_plan_requirements.csv"
PLAN_FUTURE_ARTIFACTS = "fixed_candidate_demo_environment_check_plan_future_artifacts.csv"
PLAN_WARNINGS = "fixed_candidate_demo_environment_check_plan_warnings.csv"

OUTPUT_MANIFEST = "fixed_candidate_demo_environment_check_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_environment_check_report.md"
OUTPUT_CHECKLIST = "fixed_candidate_demo_environment_check_checklist.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_environment_check_warnings.csv"
OUTPUT_REQUIREMENTS = "fixed_candidate_demo_environment_check_requirements.csv"
OUTPUT_ACCOUNT_SNAPSHOT = "fixed_candidate_demo_environment_account_snapshot_redacted.json"
OUTPUT_SYMBOL_SNAPSHOT = "fixed_candidate_demo_environment_symbol_contract_snapshot.json"
OUTPUT_NO_ORDER = "fixed_candidate_demo_environment_dry_run_no_order_check.csv"

ACCEPTABLE_PLAN_STATUS = {"demo_environment_check_plan_available_with_caveats"}
REQUIRED_KILL_SWITCH_CONDITIONS = {
    "required_data_missing",
    "required_features_missing",
    "spread_abnormal_or_not_configured",
    "atr_calculation_failed",
    "timeframe_mismatch",
    "session_mismatch",
    "existing_paper_demo_trade_open",
}
CHECK_AREAS = [
    "account_mode_check",
    "terminal_connection_check",
    "symbol_visibility_check",
    "symbol_contract_check",
    "spread_unit_check",
    "risk_sizing_check",
    "one_open_trade_state_check",
    "duplicate_protection_check",
    "sl_tp_attachment_check",
    "timeout_h10_handling_check",
    "broker_state_reconciliation_check",
    "crash_restart_recovery_check",
    "kill_switch_check",
    "audit_logging_check",
    "dry_run_no_order_check",
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

REQUIREMENT_FIELDNAMES = [
    "run_id",
    "requirement_area",
    "requirement_name",
    "required_fields",
    "expected_condition",
    "check_status",
    "observed_value",
    "blocking_if_failed",
    "caveat",
]

NO_ORDER_FIELDNAMES = [
    "run_id",
    "no_order_execution_performed",
    "no_order_request_constructed",
    "mt5_order_send_used",
    "mt5_order_check_used",
    "mt5_order_calc_margin_used",
    "mt5_order_calc_profit_used",
    "disallowed_mt5_functions_detected",
    "dry_run_mode",
    "evidence_label",
    "caveat",
]

WARNING_FIELDNAMES = [
    "run_id",
    "warning_code",
    "severity",
    "message",
    "source",
    "blocking_warning",
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
        return {}, ""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(value, dict):
        return {}, "JSON root must be an object"
    return value, ""


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], ""
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), ""
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        return [], str(exc)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "checklist": output_dir / OUTPUT_CHECKLIST,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "requirements": output_dir / OUTPUT_REQUIREMENTS,
        "account_snapshot": output_dir / OUTPUT_ACCOUNT_SNAPSHOT,
        "symbol_snapshot": output_dir / OUTPUT_SYMBOL_SNAPSHOT,
        "no_order": output_dir / OUTPUT_NO_ORDER,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
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
    return [warning for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"]


def effective_dry_run(args: argparse.Namespace) -> bool:
    return bool(args.dry_run) or not bool(args.allow_broker_read)


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def extract_first_number(text: Any) -> float | None:
    if not isinstance(text, str):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


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


def value_from(data: dict[str, Any], key: str) -> Any:
    return data.get(key)


def load_config(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    path = Path(args.demo_strategy_config)
    config, error = read_json(path)
    if not path.exists():
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_config_missing",
            message="Demo strategy config is missing.",
            source=path,
            blocking_warning=True,
        )
    elif error:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_config_unreadable",
            message=f"Demo strategy config is unreadable: {error}",
            source=path,
            blocking_warning=True,
        )
    return config


def config_boundaries(config: dict[str, Any]) -> dict[str, Any]:
    max_open_positions_note = nested_get(config, "demo_risk_controls", "max_open_positions_note")
    risk_note = nested_get(config, "demo_risk_controls", "risk_per_trade_note")
    kill_conditions = nested_get(config, "kill_switch", "conditions")
    if not isinstance(kill_conditions, list):
        kill_conditions = []
    max_open_positions = extract_first_number(max_open_positions_note)
    risk_percent = extract_first_number(risk_note)
    max_spread_points = safe_float(nested_get(config, "spread_and_session_controls", "max_spread_points"))
    spread_unit = nested_get(config, "spread_and_session_controls", "spread_unit")
    max_spread_points_positive = max_spread_points is not None and max_spread_points > 0
    spread_unit_is_broker_points = spread_unit == "broker_points"
    max_spread_points_is_15 = max_spread_points == 15.0
    return {
        "paper_only": config.get("paper_only") is True,
        "broker_connection_allowed_false": config.get("broker_connection_allowed") is False,
        "order_execution_allowed_false": config.get("order_execution_allowed") is False,
        "real_money_allowed_false": config.get("real_money_allowed") is False,
        "max_open_positions_is_one": max_open_positions == 1,
        "max_risk_per_trade_is_one_percent": risk_percent == 1,
        "spread_unit_is_broker_points": spread_unit_is_broker_points,
        "max_spread_points_is_15": max_spread_points_is_15,
        "max_spread_points_positive": max_spread_points_positive,
        "spread_policy_matches_canonical": spread_unit_is_broker_points and max_spread_points_is_15 and max_spread_points_positive,
        "kill_switch_conditions_present": REQUIRED_KILL_SWITCH_CONDITIONS.issubset(set(str(item) for item in kill_conditions)),
        "max_open_positions": max_open_positions,
        "max_risk_percent": risk_percent,
        "max_spread_points": max_spread_points,
        "spread_unit": spread_unit,
        "kill_switch_conditions": kill_conditions,
    }


def config_boundary_safe(boundaries: dict[str, Any]) -> bool:
    return all(
        bool(boundaries[key])
        for key in (
            "paper_only",
            "broker_connection_allowed_false",
            "order_execution_allowed_false",
            "real_money_allowed_false",
            "max_open_positions_is_one",
            "max_risk_per_trade_is_one_percent",
            "spread_policy_matches_canonical",
            "kill_switch_conditions_present",
        )
    )


def load_plan_source(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    root = Path(args.demo_environment_check_plan_dir)
    paths = {
        "dir": root,
        "manifest": root / PLAN_MANIFEST,
        "report": root / PLAN_REPORT,
        "requirements": root / PLAN_REQUIREMENTS,
        "future_artifacts": root / PLAN_FUTURE_ARTIFACTS,
        "warnings": root / PLAN_WARNINGS,
    }
    required = {"manifest", "requirements", "future_artifacts"}
    missing = [name for name in ("manifest", "report", "requirements", "future_artifacts", "warnings") if not paths[name].exists()]
    for name in missing:
        add_warning(
            warnings,
            args=args,
            warning_code=f"environment_plan_{name}_missing",
            message=f"Demo environment plan source artifact is missing: {paths[name].name}",
            source=paths[name],
            blocking_warning=name in required,
        )
    manifest, manifest_error = read_json(paths["manifest"])
    requirements, requirements_error = read_csv_rows(paths["requirements"])
    future_artifacts, future_error = read_csv_rows(paths["future_artifacts"])
    source_warnings, warnings_error = read_csv_rows(paths["warnings"])
    report = read_text(paths["report"])
    for name, error in [
        ("manifest", manifest_error),
        ("requirements", requirements_error),
        ("future_artifacts", future_error),
        ("warnings", warnings_error),
    ]:
        if error:
            add_warning(
                warnings,
                args=args,
                warning_code=f"environment_plan_{name}_unreadable",
                message=f"Demo environment plan source artifact is unreadable: {error}",
                source=paths[name],
                blocking_warning=name in required,
            )
    for row in source_warnings:
        add_warning(
            warnings,
            args=args,
            warning_code=row.get("warning_code", "environment_plan_source_warning"),
            message=row.get("message", "Demo environment plan source warning preserved."),
            source=row.get("source", paths["warnings"]),
            blocking_warning=str(row.get("blocking_warning", "")).lower() == "true",
            severity=row.get("severity") or "warning",
        )
    return {
        "paths": paths,
        "manifest": manifest,
        "requirements": requirements,
        "future_artifacts": future_artifacts,
        "report": report,
        "missing_required_count": sum(1 for name in missing if name in required),
        "unreadable_required_count": sum(
            1
            for name, error in [
                ("manifest", manifest_error),
                ("requirements", requirements_error),
                ("future_artifacts", future_error),
            ]
            if error
        ),
    }


def classify_account_mode(mt5_module: Any, raw_mode: Any) -> tuple[str, bool | None]:
    if raw_mode is None:
        return "unknown", None
    demo_const = getattr(mt5_module, "ACCOUNT_TRADE_MODE_DEMO", None)
    contest_const = getattr(mt5_module, "ACCOUNT_TRADE_MODE_CONTEST", None)
    real_const = getattr(mt5_module, "ACCOUNT_TRADE_MODE_REAL", None)
    if demo_const is not None and raw_mode == demo_const:
        return "demo", True
    if contest_const is not None and raw_mode == contest_const:
        return "contest", False
    if real_const is not None and raw_mode == real_const:
        return "real", False
    return "unknown", None


def redacted_account_snapshot(account_info: dict[str, Any], mode_label: str, is_demo: bool | None) -> dict[str, Any]:
    return {
        "account_trade_mode_raw": account_info.get("trade_mode"),
        "account_trade_mode_label": mode_label,
        "leverage": account_info.get("leverage"),
        "currency": account_info.get("currency"),
        "balance_present": account_info.get("balance") is not None,
        "equity_present": account_info.get("equity") is not None,
        "margin_mode": account_info.get("margin_mode"),
        "trade_allowed": account_info.get("trade_allowed"),
        "trade_expert": account_info.get("trade_expert"),
        "is_demo_account": is_demo,
        "redaction_applied": True,
    }


def symbol_contract_snapshot(
    symbol: str,
    symbol_info: dict[str, Any],
    tick_info: dict[str, Any],
    max_spread_points: float | None,
    spread_unit: str | None,
) -> dict[str, Any]:
    spread = value_from(symbol_info, "spread")
    spread_float = value_from(symbol_info, "spread_float")
    spread_value = safe_float(spread)
    return {
        "symbol": value_from(symbol_info, "name") or symbol,
        "visible": value_from(symbol_info, "visible"),
        "select": value_from(symbol_info, "select"),
        "trade_mode": value_from(symbol_info, "trade_mode"),
        "trade_contract_size": value_from(symbol_info, "trade_contract_size"),
        "volume_min": value_from(symbol_info, "volume_min"),
        "volume_max": value_from(symbol_info, "volume_max"),
        "volume_step": value_from(symbol_info, "volume_step"),
        "point": value_from(symbol_info, "point"),
        "digits": value_from(symbol_info, "digits"),
        "trade_tick_size": value_from(symbol_info, "trade_tick_size"),
        "trade_tick_value": value_from(symbol_info, "trade_tick_value"),
        "trade_stops_level": value_from(symbol_info, "trade_stops_level"),
        "trade_freeze_level": value_from(symbol_info, "trade_freeze_level"),
        "spread": spread,
        "spread_float": spread_float,
        "spread_current_points": spread_value,
        "max_spread_points": max_spread_points,
        "spread_unit": spread_unit,
        "spread_within_config_gate": None if spread_value is None or max_spread_points is None else spread_value <= max_spread_points,
        "bid": value_from(tick_info, "bid") if tick_info else value_from(symbol_info, "bid"),
        "ask": value_from(tick_info, "ask") if tick_info else value_from(symbol_info, "ask"),
        "time": value_from(tick_info, "time") if tick_info else value_from(symbol_info, "time"),
        "currency_base": value_from(symbol_info, "currency_base"),
        "currency_profit": value_from(symbol_info, "currency_profit"),
        "currency_margin": value_from(symbol_info, "currency_margin"),
    }


def planned_account_snapshot() -> dict[str, Any]:
    return {
        "account_trade_mode_raw": "not_queried",
        "account_trade_mode_label": "not_queried",
        "leverage": "not_queried",
        "currency": "not_queried",
        "balance_present": False,
        "equity_present": False,
        "margin_mode": "not_queried",
        "trade_allowed": "not_queried",
        "trade_expert": "not_queried",
        "is_demo_account": None,
        "redaction_applied": True,
    }


def planned_symbol_snapshot(symbol: str, max_spread_points: float | None, spread_unit: str | None) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "visible": "not_queried",
        "select": "not_queried",
        "trade_mode": "not_queried",
        "trade_contract_size": "not_queried",
        "volume_min": "not_queried",
        "volume_max": "not_queried",
        "volume_step": "not_queried",
        "point": "not_queried",
        "digits": "not_queried",
        "trade_tick_size": "not_queried",
        "trade_tick_value": "not_queried",
        "trade_stops_level": "not_queried",
        "trade_freeze_level": "not_queried",
        "spread": "not_queried",
        "spread_float": "not_queried",
        "spread_current_points": None,
        "max_spread_points": max_spread_points,
        "spread_unit": spread_unit,
        "spread_within_config_gate": None,
        "bid": "not_queried",
        "ask": "not_queried",
        "time": "not_queried",
        "currency_base": "not_queried",
        "currency_profit": "not_queried",
        "currency_margin": "not_queried",
    }


def inspect_mt5(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    state = {
        "mt5_import_attempted": False,
        "mt5_initialize_attempted": False,
        "mt5_initialize_success": False,
        "terminal_info": {},
        "account_info": {},
        "symbol_info": {},
        "tick_info": {},
        "mt5_module": None,
        "import_error": "",
        "initialize_error": "",
    }
    if args.dry_run:
        return state
    state["mt5_import_attempted"] = True
    try:
        mt5_module = importlib.import_module(str(args.mt5_package))
    except Exception as exc:
        state["import_error"] = str(exc)
        add_warning(
            warnings,
            args=args,
            warning_code="mt5_package_unavailable",
            message=f"Configured MT5 package could not be imported: {exc}",
            source=args.mt5_package,
            blocking_warning=True,
        )
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
        add_warning(
            warnings,
            args=args,
            warning_code="mt5_initialize_failed",
            message="MT5 initialization failed in read-only environment-check mode.",
            source=args.mt5_package,
            blocking_warning=True,
        )
        return state
    try:
        state["terminal_info"] = object_to_dict(mt5_module.terminal_info())
        state["account_info"] = object_to_dict(mt5_module.account_info())
        state["symbol_info"] = object_to_dict(mt5_module.symbol_info(args.symbol))
        state["tick_info"] = object_to_dict(mt5_module.symbol_info_tick(args.symbol))
    finally:
        shutdown = getattr(mt5_module, "shutdown", None)
        if callable(shutdown):
            shutdown()
    return state


def checked_statuses(
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    boundaries: dict[str, Any],
    mt5_state: dict[str, Any],
    account_snapshot: dict[str, Any],
    symbol_snapshot: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if args.dry_run:
        return {
            area: {
                "status": "planned_not_verified" if area != "dry_run_no_order_check" else "passed",
                "observed": "not_queried" if area != "dry_run_no_order_check" else "no_order_functions_used",
                "expected": "future read-only environment check",
                "warning_code": "",
            }
            for area in CHECK_AREAS
        }
    terminal = mt5_state["terminal_info"]
    symbol_info_available = bool(mt5_state["symbol_info"])
    visible = symbol_snapshot.get("visible")
    selected = symbol_snapshot.get("select")
    contract_fields = [
        "volume_min",
        "volume_max",
        "volume_step",
        "point",
        "digits",
        "trade_tick_size",
        "trade_tick_value",
        "trade_stops_level",
        "trade_freeze_level",
    ]
    contract_available = symbol_info_available and all(symbol_snapshot.get(field) is not None for field in contract_fields)
    spread_within_gate = symbol_snapshot.get("spread_within_config_gate")
    return {
        "account_mode_check": {
            "status": "passed" if account_snapshot.get("is_demo_account") is True else "failed",
            "observed": account_snapshot.get("account_trade_mode_label"),
            "expected": "demo",
            "warning_code": "" if account_snapshot.get("is_demo_account") is True else "account_mode_not_demo",
        },
        "terminal_connection_check": {
            "status": "passed" if terminal.get("connected") is True else "failed",
            "observed": terminal.get("connected"),
            "expected": "connected=true",
            "warning_code": "" if terminal.get("connected") is True else "terminal_not_connected",
        },
        "symbol_visibility_check": {
            "status": "passed" if visible is True and selected is True else "failed",
            "observed": {"visible": visible, "select": selected},
            "expected": "visible=true and select=true",
            "warning_code": "" if visible is True and selected is True else "symbol_not_visible_or_selectable",
        },
        "symbol_contract_check": {
            "status": "passed" if contract_available else "failed",
            "observed": {field: symbol_snapshot.get(field) for field in contract_fields},
            "expected": "all symbol contract fields available",
            "warning_code": "" if contract_available else "symbol_contract_incomplete",
        },
        "spread_unit_check": {
            "status": "passed" if spread_within_gate is True else "failed" if spread_within_gate is False else "unknown",
            "observed": symbol_snapshot.get("spread_current_points"),
            "expected": f"spread_current_points <= {boundaries['max_spread_points']} broker_points",
            "warning_code": "" if spread_within_gate is True else "spread_above_config_threshold" if spread_within_gate is False else "spread_unavailable",
        },
        "risk_sizing_check": {
            "status": "planned_not_verified",
            "observed": {"balance_present": account_snapshot.get("balance_present"), "risk_percent": boundaries["max_risk_percent"]},
            "expected": "future no-order risk preview uses demo balance only",
            "warning_code": "",
        },
        "one_open_trade_state_check": {
            "status": "planned_not_verified",
            "observed": "not_queried",
            "expected": "future local/environment state reconciliation",
            "warning_code": "",
        },
        "duplicate_protection_check": {
            "status": "planned_not_verified",
            "observed": "not_queried",
            "expected": "future duplicate protection evidence",
            "warning_code": "",
        },
        "sl_tp_attachment_check": {
            "status": "planned_not_verified",
            "observed": "not_constructed",
            "expected": "future no-order dry-run preview only",
            "warning_code": "",
        },
        "timeout_h10_handling_check": {
            "status": "planned_not_verified",
            "observed": nested_get(config, "candidate", "target_horizon"),
            "expected": "horizon_bars=10",
            "warning_code": "",
        },
        "broker_state_reconciliation_check": {
            "status": "planned_not_verified",
            "observed": "not_queried",
            "expected": "future state reconciliation",
            "warning_code": "",
        },
        "crash_restart_recovery_check": {
            "status": "planned_not_verified",
            "observed": "not_checked",
            "expected": "future crash/restart recovery check",
            "warning_code": "",
        },
        "kill_switch_check": {
            "status": "passed" if boundaries["kill_switch_conditions_present"] else "failed",
            "observed": boundaries["kill_switch_conditions"],
            "expected": "all configured kill-switch conditions present",
            "warning_code": "" if boundaries["kill_switch_conditions_present"] else "kill_switch_conditions_missing",
        },
        "audit_logging_check": {
            "status": "passed" if bool(nested_get(config, "logging", "required_fields")) else "failed",
            "observed": nested_get(config, "logging", "required_fields") or [],
            "expected": "logging required fields present",
            "warning_code": "" if bool(nested_get(config, "logging", "required_fields")) else "logging_fields_missing",
        },
        "dry_run_no_order_check": {
            "status": "passed",
            "observed": "no_order_functions_used",
            "expected": "no order functions used and no request constructed",
            "warning_code": "",
        },
    }


def build_checklist_rows(args: argparse.Namespace, statuses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    names = {
        "account_mode_check": "account mode is demo",
        "terminal_connection_check": "terminal connection facts captured",
        "symbol_visibility_check": "symbol visible/selectable without state change",
        "symbol_contract_check": "symbol contract fields captured",
        "spread_unit_check": "spread points within configured gate",
        "risk_sizing_check": "risk sizing remains future no-order preview",
        "one_open_trade_state_check": "one-open-trade state remains future reconciliation",
        "duplicate_protection_check": "duplicate protection remains future check",
        "sl_tp_attachment_check": "SL/TP attachment remains future no-order preview",
        "timeout_h10_handling_check": "timeout h10 fields represented",
        "broker_state_reconciliation_check": "state reconciliation remains future check",
        "crash_restart_recovery_check": "crash/restart recovery remains future check",
        "kill_switch_check": "kill-switch config represented",
        "audit_logging_check": "audit logging fields represented",
        "dry_run_no_order_check": "no-order boundary confirmed",
    }
    rows: list[dict[str, Any]] = []
    for area in CHECK_AREAS:
        status = statuses[area]
        rows.append(
            {
                "run_id": args.run_id,
                "check_area": area,
                "check_name": names[area],
                "check_status": status["status"],
                "observed_value": status["observed"],
                "expected_value": status["expected"],
                "blocking_if_failed": True,
                "evidence_source": "mt5_read_only_query" if status["status"] in {"passed", "failed", "unknown"} and not args.dry_run else "planned_no_mt5_query",
                "caveat": "read_only_no_order_environment_evidence",
                "warning_code": status["warning_code"],
            }
        )
    return rows


def build_requirement_rows(
    args: argparse.Namespace,
    plan_requirements: list[dict[str, str]],
    statuses: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in plan_requirements:
        area = source.get("requirement_area", "")
        status = statuses.get(area, {"status": "planned_not_verified", "observed": "not_checked"})
        rows.append(
            {
                "run_id": args.run_id,
                "requirement_area": area,
                "requirement_name": source.get("requirement_name", ""),
                "required_fields": source.get("required_fields", ""),
                "expected_condition": source.get("expected_condition", ""),
                "check_status": status.get("status", "planned_not_verified"),
                "observed_value": status.get("observed", ""),
                "blocking_if_failed": source.get("blocking_if_failed", "true"),
                "caveat": source.get("caveat", ""),
            }
        )
    return rows


def add_check_warnings(args: argparse.Namespace, checklist_rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    for row in checklist_rows:
        if row["check_status"] not in {"failed", "unknown"}:
            continue
        add_warning(
            warnings,
            args=args,
            warning_code=row["warning_code"] or f"{row['check_area']}_not_confirmed",
            message=f"Environment check requirement did not pass: {row['check_area']}",
            source=row["evidence_source"],
            blocking_warning=str(row.get("blocking_if_failed", "")).lower() == "true",
        )


def build_no_order_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "no_order_execution_performed": True,
            "no_order_request_constructed": True,
            "mt5_order_send_used": False,
            "mt5_order_check_used": False,
            "mt5_order_calc_margin_used": False,
            "mt5_order_calc_profit_used": False,
            "disallowed_mt5_functions_detected": False,
            "dry_run_mode": bool(args.dry_run),
            "evidence_label": "no_order_boundary_confirmed",
            "caveat": "checker only records environment facts and does not prepare trades",
        }
    ]


def determine_status(
    *,
    args: argparse.Namespace,
    plan_source: dict[str, Any],
    config: dict[str, Any],
    boundaries: dict[str, Any],
    mt5_state: dict[str, Any],
    account_snapshot: dict[str, Any],
    symbol_snapshot: dict[str, Any],
    checklist_rows: list[dict[str, Any]],
) -> str:
    if plan_source["missing_required_count"] or not plan_source["manifest"]:
        return "blocked_by_plan_status"
    plan_status_value = str(plan_source["manifest"].get("plan_status") or "")
    if plan_status_value not in ACCEPTABLE_PLAN_STATUS:
        return "blocked_by_plan_status"
    if not config or not config_boundary_safe(boundaries):
        return "blocked_by_config_boundary"
    if args.dry_run:
        return "demo_environment_check_dry_run_no_broker_read"
    if mt5_state["import_error"]:
        return "blocked_mt5_unavailable"
    if not mt5_state["mt5_initialize_success"]:
        return "blocked_mt5_initialize_failed"
    if account_snapshot.get("is_demo_account") is not True:
        return "blocked_account_mode_not_demo"
    if not mt5_state["symbol_info"]:
        return "blocked_missing_symbol_info"
    failed_blocking = [
        row
        for row in checklist_rows
        if row["check_status"] in {"failed", "unknown"} and str(row.get("blocking_if_failed", "")).lower() == "true"
    ]
    if failed_blocking:
        return "environment_check_failed_blocking_requirements"
    return "environment_check_available_with_caveats"


def recommended_next_step(status: str) -> str:
    if status in {"dry_run_no_mt5_query_performed", "demo_environment_check_dry_run_no_broker_read"}:
        return "run_environment_check_read_only_when_demo_terminal_ready"
    if status == "environment_check_available_with_caveats":
        return "build_fixed_candidate_demo_no_order_dry_run_plan"
    return "fix_demo_environment_blocker"


def count_status(rows: list[dict[str, Any]], status: str) -> int:
    return sum(1 for row in rows if row.get("check_status") == status)


def failed_blocking_count(rows: list[dict[str, Any]]) -> int:
    return sum(
        1
        for row in rows
        if row.get("check_status") in {"failed", "unknown"} and str(row.get("blocking_if_failed", "")).lower() == "true"
    )


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    plan_source = load_plan_source(args, warnings)
    config = load_config(args, warnings)
    boundaries = config_boundaries(config)
    if config and not config_boundary_safe(boundaries):
        add_warning(
            warnings,
            args=args,
            warning_code="demo_config_boundary_unsafe",
            message="Demo strategy config does not satisfy read-only demo environment check boundaries.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    mt5_state = inspect_mt5(args, warnings) if plan_source["manifest"].get("plan_status") in ACCEPTABLE_PLAN_STATUS and config_boundary_safe(boundaries) else {
        "mt5_import_attempted": False,
        "mt5_initialize_attempted": False,
        "mt5_initialize_success": False,
        "terminal_info": {},
        "account_info": {},
        "symbol_info": {},
        "tick_info": {},
        "mt5_module": None,
        "import_error": "",
        "initialize_error": "",
    }
    if args.dry_run or not mt5_state["account_info"]:
        account_snapshot = planned_account_snapshot()
    else:
        mode_label, is_demo = classify_account_mode(mt5_state["mt5_module"], mt5_state["account_info"].get("trade_mode"))
        account_snapshot = redacted_account_snapshot(mt5_state["account_info"], mode_label, is_demo)
    if args.dry_run or not mt5_state["symbol_info"]:
        symbol_snapshot = planned_symbol_snapshot(args.symbol, boundaries["max_spread_points"], boundaries["spread_unit"])
    else:
        symbol_snapshot = symbol_contract_snapshot(
            args.symbol,
            mt5_state["symbol_info"],
            mt5_state["tick_info"],
            boundaries["max_spread_points"],
            boundaries["spread_unit"],
        )
    statuses = checked_statuses(
        args=args,
        config=config,
        boundaries=boundaries,
        mt5_state=mt5_state,
        account_snapshot=account_snapshot,
        symbol_snapshot=symbol_snapshot,
    )
    checklist_rows = build_checklist_rows(args, statuses)
    add_check_warnings(args, checklist_rows, warnings)
    requirement_rows = build_requirement_rows(args, plan_source["requirements"], statuses)
    no_order_rows = build_no_order_rows(args)
    status = determine_status(
        args=args,
        plan_source=plan_source,
        config=config,
        boundaries=boundaries,
        mt5_state=mt5_state,
        account_snapshot=account_snapshot,
        symbol_snapshot=symbol_snapshot,
        checklist_rows=checklist_rows,
    )
    write_csv(output_paths["checklist"], checklist_rows, CHECKLIST_FIELDNAMES)
    write_csv(output_paths["requirements"], requirement_rows, REQUIREMENT_FIELDNAMES)
    write_csv(output_paths["no_order"], no_order_rows, NO_ORDER_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    output_paths["account_snapshot"].write_text(json.dumps(account_snapshot, indent=2, sort_keys=True), encoding="utf-8")
    output_paths["symbol_snapshot"].write_text(json.dumps(symbol_snapshot, indent=2, sort_keys=True), encoding="utf-8")
    write_report(
        output_paths["report"],
        args=args,
        status=status,
        plan_source=plan_source,
        boundaries=boundaries,
        mt5_state=mt5_state,
        account_snapshot=account_snapshot,
        symbol_snapshot=symbol_snapshot,
        checklist_rows=checklist_rows,
        warnings=warnings,
    )
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        status=status,
        plan_source=plan_source,
        boundaries=boundaries,
        mt5_state=mt5_state,
        account_snapshot=account_snapshot,
        symbol_snapshot=symbol_snapshot,
        checklist_rows=checklist_rows,
        requirement_rows=requirement_rows,
        warnings=warnings,
        output_paths=output_paths,
    )
    return {
        "environment_check_status": status,
        "checklist_rows": checklist_rows,
        "requirement_rows": requirement_rows,
        "warnings": warnings,
        "account_snapshot": account_snapshot,
        "symbol_snapshot": symbol_snapshot,
    }


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    status: str,
    plan_source: dict[str, Any],
    boundaries: dict[str, Any],
    mt5_state: dict[str, Any],
    account_snapshot: dict[str, Any],
    symbol_snapshot: dict[str, Any],
    checklist_rows: list[dict[str, Any]],
    requirement_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    output_paths: dict[str, Path],
) -> None:
    output = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_environment_check_plan_dir": str(args.demo_environment_check_plan_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "allow_broker_read": bool(args.allow_broker_read),
        "dry_run": bool(args.dry_run),
        "environment_check_status": status,
        "broker_read_performed": bool(mt5_state["terminal_info"] or mt5_state["account_info"] or mt5_state["symbol_info"] or mt5_state["tick_info"]),
        "mt5_import_performed": bool(mt5_state["mt5_import_attempted"]),
        "mt5_connection_performed": bool(mt5_state["mt5_initialize_success"]),
        "mt5_import_attempted": mt5_state["mt5_import_attempted"],
        "mt5_initialize_attempted": mt5_state["mt5_initialize_attempted"],
        "mt5_initialize_success": mt5_state["mt5_initialize_success"],
        "terminal_info_available": bool(mt5_state["terminal_info"]),
        "account_info_available": bool(mt5_state["account_info"]),
        "symbol_info_available": bool(mt5_state["symbol_info"]),
        "symbol_tick_available": bool(mt5_state["tick_info"]),
        "account_mode_label": account_snapshot.get("account_trade_mode_label"),
        "is_demo_account": account_snapshot.get("is_demo_account"),
        "account_snapshot_redacted_path": str(output_paths["account_snapshot"]),
        "symbol_contract_snapshot_path": str(output_paths["symbol_snapshot"]),
        "checklist_row_count": len(checklist_rows),
        "requirement_row_count": len(requirement_rows),
        "checked_requirement_count": sum(1 for row in checklist_rows if row.get("check_status") in {"passed", "failed", "unknown"}),
        "planned_not_verified_count": count_status(checklist_rows, "planned_not_verified"),
        "failed_blocking_requirement_count": failed_blocking_count(checklist_rows),
        "warning_count": len(warnings),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "spread_current_points": symbol_snapshot.get("spread_current_points"),
        "max_spread_points": boundaries["max_spread_points"],
        "spread_unit": boundaries["spread_unit"],
        "spread_policy_matches_canonical": boundaries["spread_policy_matches_canonical"],
        "spread_within_config_gate": symbol_snapshot.get("spread_within_config_gate"),
        "volume_min": symbol_snapshot.get("volume_min"),
        "volume_max": symbol_snapshot.get("volume_max"),
        "volume_step": symbol_snapshot.get("volume_step"),
        "point": symbol_snapshot.get("point"),
        "digits": symbol_snapshot.get("digits"),
        "trade_tick_size": symbol_snapshot.get("trade_tick_size"),
        "trade_tick_value": symbol_snapshot.get("trade_tick_value"),
        "trade_stops_level": symbol_snapshot.get("trade_stops_level"),
        "trade_freeze_level": symbol_snapshot.get("trade_freeze_level"),
        "source_plan_status": plan_source["manifest"].get("plan_status", ""),
        "recommended_next_step": recommended_next_step(status),
        "no_child_scripts_executed": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_replay_rerun": True,
        "no_cost_sensitivity_rerun": True,
        "no_recent_holdout_rerun": True,
        "no_optimization_performed": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    status: str,
    plan_source: dict[str, Any],
    boundaries: dict[str, Any],
    mt5_state: dict[str, Any],
    account_snapshot: dict[str, Any],
    symbol_snapshot: dict[str, Any],
    checklist_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    planned_count = count_status(checklist_rows, "planned_not_verified")
    failed_count = failed_blocking_count(checklist_rows)
    lines = [
        "# Fixed Candidate Demo Environment Check",
        "",
        "Read-only/no-order demo environment check artifact.",
        "Dry-run mode writes planned checks only and performs no MT5 import or query.",
        "No order execution was performed.",
        "No order request was constructed.",
        "No database mutation was performed.",
        "No data generation or feature refresh was performed.",
        "No replay, cost sensitivity, or recent holdout rerun was performed.",
        "No optimization or parameter search was performed.",
        "This check is not future-performance proof.",
        "This check is not demo broker approval.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- demo_environment_check_plan_dir: `{args.demo_environment_check_plan_dir}`",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- symbol: `{args.symbol}`",
        f"- timeframe: `{args.timeframe}`",
        f"- allow_broker_read: `{bool_text(bool(args.allow_broker_read))}`",
        f"- dry_run: `{bool_text(bool(args.dry_run))}`",
        "",
        "## Terminal/Account/Symbol Summary",
        "",
        f"- mt5_import_attempted: `{bool_text(bool(mt5_state['mt5_import_attempted']))}`",
        f"- mt5_initialize_attempted: `{bool_text(bool(mt5_state['mt5_initialize_attempted']))}`",
        f"- terminal_info_available: `{bool_text(bool(mt5_state['terminal_info']))}`",
        f"- account_info_available: `{bool_text(bool(mt5_state['account_info']))}`",
        f"- account_mode_label: `{account_snapshot.get('account_trade_mode_label')}`",
        f"- is_demo_account: `{account_snapshot.get('is_demo_account')}`",
        f"- symbol_info_available: `{bool_text(bool(mt5_state['symbol_info']))}`",
        f"- symbol_tick_available: `{bool_text(bool(mt5_state['tick_info']))}`",
        "",
        "## Account Mode Check Result",
        "",
        f"- account_mode_label: `{account_snapshot.get('account_trade_mode_label')}`",
        f"- is_demo_account: `{account_snapshot.get('is_demo_account')}`",
        f"- redaction_applied: `{account_snapshot.get('redaction_applied')}`",
        "",
        "## Symbol Contract Check Result",
        "",
        f"- visible: `{symbol_snapshot.get('visible')}`",
        f"- select: `{symbol_snapshot.get('select')}`",
        f"- volume_min: `{symbol_snapshot.get('volume_min')}`",
        f"- volume_max: `{symbol_snapshot.get('volume_max')}`",
        f"- volume_step: `{symbol_snapshot.get('volume_step')}`",
        f"- point: `{symbol_snapshot.get('point')}`",
        f"- digits: `{symbol_snapshot.get('digits')}`",
        f"- trade_stops_level: `{symbol_snapshot.get('trade_stops_level')}`",
        f"- trade_freeze_level: `{symbol_snapshot.get('trade_freeze_level')}`",
        "",
        "## Spread Unit Check Result",
        "",
        f"- spread_current_points: `{symbol_snapshot.get('spread_current_points')}`",
        f"- spread_unit: `{boundaries['spread_unit']}`",
        f"- max_spread_points: `{boundaries['max_spread_points']}`",
        f"- spread_within_config_gate: `{symbol_snapshot.get('spread_within_config_gate')}`",
        "",
        "## Planned-Not-Verified Requirements",
        "",
        f"- planned_not_verified_count: `{planned_count}`",
        "",
        "## Blocking Failures",
        "",
        f"- failed_blocking_requirement_count: `{failed_count}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        "",
        "## Environment Check Status",
        "",
        f"`{status}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{recommended_next_step(status)}`",
        "",
        "## Source Plan",
        "",
        f"- source_plan_status: `{plan_source['manifest'].get('plan_status', '')}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    runtime_args = argparse.Namespace(**vars(args))
    runtime_args.dry_run = effective_dry_run(args)
    build_artifacts(runtime_args, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check fixed-candidate demo environment facts in read-only/no-order mode.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-environment-check-plan-dir", type=Path, default=DEFAULT_DEMO_ENVIRONMENT_CHECK_PLAN_DIR)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--mt5-package", default="MetaTrader5")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-broker-read", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate demo environment check failed: {exc}")
        return 1
    print("Fixed-candidate demo environment check complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
