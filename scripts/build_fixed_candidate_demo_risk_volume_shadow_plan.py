"""Build an artifact-only demo risk/volume shadow plan for the fixed candidate.

The plan reads local artifacts, defines offline formulas, and optionally
computes an indicative lot preview from static artifact fields plus an explicit
demo equity value. It does not query external systems or databases, run child
scripts, build broker-submit-ready structures, validate margin/profit, or
perform order operations.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_risk_volume_shadow_plan"
DEFAULT_DESIGN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_order_request_shadow_design"
    / "gbpusd_short_h10_1_5_off_hours_demo_order_request_shadow_design_fixture_v1"
)
DEFAULT_ENV_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_environment_check"
    / "gbpusd_short_h10_1_5_off_hours_demo_environment_check_spread15_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_risk_volume_shadow_plan"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_SYMBOL = "GBPUSD"
EXPECTED_TIMEFRAME = "M15"
EXPECTED_DIRECTION = "short"
EXPECTED_SPREAD_UNIT = "broker_points"
EXPECTED_MAX_SPREAD_POINTS = 15.0
EXPECTED_ACCOUNT_CURRENCY = "EUR"
EXPECTED_DEMO_EQUITY = 1000.0
EXPECTED_RISK_PERCENT_MAX = 0.5
EXPECTED_RISK_AMOUNT_MAX = 5.0
EXPECTED_MAX_MARGIN_USAGE_RATIO = 0.7
EXPECTED_MAX_MARGIN_USAGE_AMOUNT = 700.0
EXPECTED_MAX_MARGIN_USAGE_WARNING_RATIO = 0.5
EXPECTED_MAX_MARGIN_USAGE_WARNING_AMOUNT = 500.0

SOURCE_DESIGN_MANIFEST = "fixed_candidate_demo_order_request_shadow_design_manifest.json"
SOURCE_DESIGN_REPORT = "fixed_candidate_demo_order_request_shadow_design_report.md"
SOURCE_DESIGN_MAIN_CSV = "fixed_candidate_demo_order_request_shadow_design.csv"
SOURCE_DESIGN_STAGES_CSV = "fixed_candidate_demo_order_request_shadow_design_validation_stages.csv"
SOURCE_DESIGN_FIELDS_CSV = "fixed_candidate_demo_order_request_shadow_design_future_intent_fields.csv"
SOURCE_DESIGN_WARNINGS_CSV = "fixed_candidate_demo_order_request_shadow_design_warnings.csv"

ENV_MANIFEST = "fixed_candidate_demo_environment_check_manifest.json"
SYMBOL_SNAPSHOT = "fixed_candidate_demo_environment_symbol_contract_snapshot.json"
ACCOUNT_SNAPSHOT = "fixed_candidate_demo_environment_account_snapshot_redacted.json"
ENV_NO_ORDER_CSV = "fixed_candidate_demo_environment_dry_run_no_order_check.csv"
ENV_WARNINGS_CSV = "fixed_candidate_demo_environment_check_warnings.csv"

OUTPUT_MANIFEST = "fixed_candidate_demo_risk_volume_shadow_plan_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_risk_volume_shadow_plan_report.md"
OUTPUT_MAIN_CSV = "fixed_candidate_demo_risk_volume_shadow_plan.csv"
OUTPUT_FORMULA_CSV = "fixed_candidate_demo_risk_volume_shadow_plan_formula.csv"
OUTPUT_REQUIREMENTS_CSV = "fixed_candidate_demo_risk_volume_shadow_plan_requirements.csv"
OUTPUT_WARNINGS_CSV = "fixed_candidate_demo_risk_volume_shadow_plan_warnings.csv"

TRUE_DESIGN_BOUNDARY_FIELDS = (
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
    "broker_payload_forbidden",
    "executable_request_object_forbidden",
)
FALSE_DESIGN_BOUNDARY_FIELDS = (
    "design_actionable",
    "future_request_construction_allowed",
    "order_execution_allowed",
    "order_request_construction_allowed",
    "demo_broker_approval_performed",
)

MAIN_FIELDNAMES = [
    "run_id",
    "plan_status",
    "source_nature",
    "source_design_status",
    "candidate_id",
    "symbol",
    "timeframe",
    "direction",
    "time_server",
    "entry_reference_price",
    "tp_price_preview",
    "sl_price_preview",
    "risk_distance_price",
    "risk_percent",
    "demo_equity",
    "risk_amount",
    "demo_execution_policy_path",
    "account_currency",
    "policy_intended_demo_equity",
    "policy_risk_percent_max",
    "policy_risk_amount_max",
    "policy_max_margin_usage_ratio",
    "policy_max_margin_usage_amount",
    "policy_max_margin_usage_warning_ratio",
    "policy_max_margin_usage_warning_amount",
    "trade_tick_size",
    "trade_tick_value",
    "value_per_price_unit_per_lot",
    "raw_volume_lots",
    "stepped_volume_lots",
    "volume_preview_status",
    "volume_min",
    "volume_max",
    "volume_step",
    "stop_level_check_status",
    "plan_area",
    "observed_value",
    "expected_value",
    "plan_result",
    "blocking_if_failed",
    "caveat",
    "recommended_next_step",
]
FORMULA_FIELDNAMES = [
    "run_id",
    "formula_name",
    "formula_expression",
    "input_fields",
    "output_field",
    "computed_value",
    "formula_status",
    "caveat",
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
        "formula": output_dir / OUTPUT_FORMULA_CSV,
        "requirements": output_dir / OUTPUT_REQUIREMENTS_CSV,
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


def execution_policy_valid(policy: dict[str, Any]) -> bool:
    safety = policy.get("safety_boundaries")
    if not isinstance(safety, dict):
        safety = {}
    volume_policy = policy.get("volume_policy")
    if not isinstance(volume_policy, dict):
        volume_policy = {}
    return (
        policy.get("policy_id") == "gbpusd_short_h10_1_5_off_hours_demo_execution_policy_v1"
        and policy.get("candidate_id") == EXPECTED_CANDIDATE_ID
        and policy.get("symbol") == EXPECTED_SYMBOL
        and policy.get("timeframe") == EXPECTED_TIMEFRAME
        and policy.get("direction") == EXPECTED_DIRECTION
        and policy.get("account_currency") == EXPECTED_ACCOUNT_CURRENCY
        and close_float(policy.get("intended_demo_equity"), EXPECTED_DEMO_EQUITY)
        and close_float(policy.get("risk_percent_max"), EXPECTED_RISK_PERCENT_MAX)
        and close_float(policy.get("risk_amount_max"), EXPECTED_RISK_AMOUNT_MAX)
        and close_float(policy.get("max_margin_usage_ratio"), EXPECTED_MAX_MARGIN_USAGE_RATIO)
        and close_float(policy.get("max_margin_usage_amount"), EXPECTED_MAX_MARGIN_USAGE_AMOUNT)
        and close_float(policy.get("max_margin_usage_warning_ratio"), EXPECTED_MAX_MARGIN_USAGE_WARNING_RATIO)
        and close_float(policy.get("max_margin_usage_warning_amount"), EXPECTED_MAX_MARGIN_USAGE_WARNING_AMOUNT)
        and policy.get("spread_unit") == EXPECTED_SPREAD_UNIT
        and close_float(policy.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS)
        and safe_float(policy.get("max_open_positions")) == 1
        and volume_policy.get("rounding") == "floor_to_volume_step"
        and volume_policy.get("below_min_volume") == "block"
        and volume_policy.get("above_max_volume") == "block"
        and volume_policy.get("risk_margin_conflict") == "cap_by_margin_or_block_before_request"
        and as_bool(volume_policy.get("do_not_force_full_risk_if_margin_infeasible")) is True
        and as_bool(safety.get("paper_only_until_explicit_future_change")) is True
        and as_bool(safety.get("real_money_allowed")) is False
        and as_bool(safety.get("broker_connection_allowed_for_this_policy_file")) is False
        and as_bool(safety.get("order_execution_allowed")) is False
        and as_bool(safety.get("order_request_construction_allowed")) is False
        and as_bool(safety.get("order_check_allowed")) is False
        and as_bool(safety.get("order_calc_allowed")) is False
    )


def effective_policy_values(args: argparse.Namespace, policy: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    policy_demo_equity = safe_float(policy.get("intended_demo_equity"))
    policy_risk_percent = safe_float(policy.get("risk_percent_max"))
    policy_risk_amount = safe_float(policy.get("risk_amount_max"))
    demo_equity = safe_float(args.demo_equity) if args.demo_equity is not None else policy_demo_equity
    risk_percent = safe_float(args.risk_percent) if args.risk_percent is not None else policy_risk_percent

    if args.demo_equity is not None and policy_demo_equity is not None and not close_float(args.demo_equity, policy_demo_equity):
        add_warning(
            warnings,
            args=args,
            warning_code="demo_equity_policy_override",
            message=f"CLI demo equity {args.demo_equity} differs from policy intended_demo_equity {policy_demo_equity}.",
            source="cli",
            blocking_warning=False,
            severity="warning",
        )
    if args.risk_percent is not None and policy_risk_percent is not None and not close_float(args.risk_percent, policy_risk_percent):
        add_warning(
            warnings,
            args=args,
            warning_code="risk_percent_policy_override",
            message=f"CLI risk percent {args.risk_percent} differs from policy risk_percent_max {policy_risk_percent}.",
            source="cli",
            blocking_warning=False,
            severity="warning",
        )

    return {
        "demo_execution_policy_path": str(args.demo_execution_policy),
        "account_currency": policy.get("account_currency", EXPECTED_ACCOUNT_CURRENCY),
        "policy_intended_demo_equity": policy_demo_equity,
        "policy_risk_percent_max": policy_risk_percent,
        "policy_risk_amount_max": policy_risk_amount,
        "policy_max_margin_usage_ratio": safe_float(policy.get("max_margin_usage_ratio")),
        "policy_max_margin_usage_amount": safe_float(policy.get("max_margin_usage_amount")),
        "policy_max_margin_usage_warning_ratio": safe_float(policy.get("max_margin_usage_warning_ratio")),
        "policy_max_margin_usage_warning_amount": safe_float(policy.get("max_margin_usage_warning_amount")),
        "demo_equity": demo_equity,
        "risk_percent": risk_percent,
    }


def design_boundary_ok(design: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for field in TRUE_DESIGN_BOUNDARY_FIELDS:
        if as_bool(design.get(field)) is not True:
            failures.append(field)
    for field in FALSE_DESIGN_BOUNDARY_FIELDS:
        if as_bool(design.get(field)) is not False:
            failures.append(field)
    return not failures, failures


def environment_ok(env: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if env.get("environment_check_status") != "environment_check_available_with_caveats":
        failures.append("environment_check_status")
    if as_bool(env.get("is_demo_account")) is not True:
        failures.append("is_demo_account")
    if as_bool(env.get("spread_policy_matches_canonical")) is not True:
        failures.append("spread_policy_matches_canonical")
    if as_bool(env.get("spread_within_config_gate")) is not True:
        failures.append("spread_within_config_gate")
    return not failures, failures


def symbol_contract_ok(symbol_contract: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if symbol_contract.get("symbol") != EXPECTED_SYMBOL:
        failures.append("symbol")
    if as_bool(symbol_contract.get("visible")) is not True:
        failures.append("visible")
    if as_bool(symbol_contract.get("select")) is not True:
        failures.append("select")
    if safe_float(symbol_contract.get("digits")) != 5:
        failures.append("digits")
    for field in ("point", "volume_min", "volume_max", "volume_step"):
        value = safe_float(symbol_contract.get(field))
        if value is None or value <= 0:
            failures.append(field)
    for field in ("trade_tick_size", "trade_tick_value"):
        if symbol_contract.get(field) not in ("", None):
            value = safe_float(symbol_contract.get(field))
            if value is None or value <= 0:
                failures.append(field)
    for field in ("trade_stops_level", "trade_freeze_level"):
        if field not in symbol_contract:
            failures.append(field)
    return not failures, failures


def account_snapshot_ok(account: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    mode = account.get("account_trade_mode_label") or account.get("account_mode_label")
    if mode != "demo":
        failures.append("account_trade_mode_label")
    if as_bool(account.get("is_demo_account")) is not True:
        failures.append("is_demo_account")
    if as_bool(account.get("redaction_applied")) is not True:
        failures.append("redaction_applied")
    return not failures, failures


def signal_prices_ok(design: dict[str, Any]) -> tuple[bool, list[str], float | None]:
    failures: list[str] = []
    entry = safe_float(design.get("entry_reference_price"))
    tp_preview = safe_float(design.get("tp_price_preview"))
    sl_preview = safe_float(design.get("sl_price_preview"))
    for field, value in (
        ("entry_reference_price", entry),
        ("tp_price_preview", tp_preview),
        ("sl_price_preview", sl_preview),
    ):
        if value is None or value <= 0:
            failures.append(field)
    risk_distance = None
    if entry is not None and tp_preview is not None and sl_preview is not None:
        if not tp_preview < entry:
            failures.append("short_tp_below_entry")
        if not sl_preview > entry:
            failures.append("short_sl_above_entry")
        risk_distance = sl_preview - entry
        if risk_distance <= 0:
            failures.append("risk_distance_price")
    return not failures, failures, risk_distance


def risk_policy_ok(risk_percent: Any) -> bool:
    risk = safe_float(risk_percent)
    return risk is not None and 0 < risk <= 1.0


def floor_to_step(raw_value: float, step: float) -> float:
    stepped = math.floor(raw_value / step) * step
    decimals = max(0, min(8, len(f"{step:.8f}".rstrip("0").split(".")[-1]) if "." in f"{step:.8f}".rstrip("0") else 0))
    return round(stepped, decimals)


def compute_volume_context(
    *,
    design: dict[str, Any],
    symbol_contract: dict[str, Any],
    risk_distance_price: float | None,
    demo_equity: float | None,
    risk_percent: float | None,
) -> dict[str, Any]:
    volume_min = safe_float(symbol_contract.get("volume_min"))
    volume_max = safe_float(symbol_contract.get("volume_max"))
    volume_step = safe_float(symbol_contract.get("volume_step"))
    tick_size = safe_float(symbol_contract.get("trade_tick_size"))
    tick_value = safe_float(symbol_contract.get("trade_tick_value"))
    point = safe_float(symbol_contract.get("point"))
    stops_level = safe_float(symbol_contract.get("trade_stops_level"))
    entry = safe_float(design.get("entry_reference_price"))
    tp_preview = safe_float(design.get("tp_price_preview"))
    sl_preview = safe_float(design.get("sl_price_preview"))

    risk_amount = None
    value_per_price_unit = None
    raw_volume = None
    stepped_volume = None
    volume_status = "blocked_missing_demo_equity"
    formula_status = "formula_defined_missing_demo_equity"
    if demo_equity is not None and demo_equity > 0 and risk_percent is not None and risk_distance_price is not None:
        risk_amount = demo_equity * risk_percent / 100.0
        if tick_size is not None and tick_size > 0 and tick_value is not None and tick_value > 0:
            value_per_price_unit = tick_value / tick_size
            risk_per_lot = risk_distance_price * value_per_price_unit
            if risk_per_lot > 0 and volume_step is not None and volume_step > 0:
                raw_volume = risk_amount / risk_per_lot
                stepped_volume = floor_to_step(raw_volume, volume_step)
                if volume_min is not None and stepped_volume < volume_min:
                    volume_status = "blocked_below_min_volume"
                elif volume_max is not None and stepped_volume > volume_max:
                    volume_status = "blocked_above_max_volume"
                else:
                    volume_status = "shadow_volume_preview_available_not_broker_validated"
                formula_status = "computed_from_static_artifacts"
            else:
                volume_status = "blocked_by_volume_formula"
                formula_status = "blocked_by_volume_formula"
        else:
            volume_status = "blocked_by_volume_formula"
            formula_status = "blocked_by_missing_tick_value_or_size"

    stop_level_status = "requires_future_broker_recheck"
    min_stop_distance = None
    if point is not None and stops_level is not None:
        min_stop_distance = stops_level * point
        if entry is not None and tp_preview is not None and sl_preview is not None:
            tp_distance = entry - tp_preview
            sl_distance = sl_preview - entry
            stop_level_status = "static_artifact_stop_distance_passed" if tp_distance >= min_stop_distance and sl_distance >= min_stop_distance else "static_artifact_stop_distance_failed"

    return {
        "risk_percent": risk_percent,
        "demo_equity": demo_equity,
        "risk_amount": risk_amount,
        "trade_tick_size": tick_size,
        "trade_tick_value": tick_value,
        "value_per_price_unit_per_lot": value_per_price_unit,
        "raw_volume_lots": raw_volume,
        "stepped_volume_lots": stepped_volume,
        "volume_preview_status": volume_status,
        "volume_min": volume_min,
        "volume_max": volume_max,
        "volume_step": volume_step,
        "stop_level_check_status": stop_level_status,
        "min_stop_distance_price": min_stop_distance,
        "formula_status": formula_status,
    }


def recommended_next_step(plan_status: str) -> str:
    if plan_status == "risk_volume_shadow_plan_fixture_only":
        return "wait_for_live_shadow_signal_or_continue_no_order_monitoring"
    if plan_status == "risk_volume_shadow_plan_available_no_order":
        return "build_fixed_candidate_demo_state_reconciliation_plan"
    if plan_status == "hold_no_order_request_shadow_design_available":
        return "continue_no_order_monitoring"
    return "fix_risk_volume_shadow_plan_blocker"


def determine_plan_status(
    *,
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_error: str,
    policy: dict[str, Any],
    policy_error: str,
    design: dict[str, Any],
    design_error: str,
    env: dict[str, Any],
    env_error: str,
    symbol_contract: dict[str, Any],
    symbol_error: str,
    account: dict[str, Any],
    account_error: str,
    boundary_safe: bool,
    env_safe: bool,
    symbol_safe: bool,
    account_safe: bool,
    signal_safe: bool,
    policy_safe: bool,
    risk_percent: float | None,
    volume_context: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> str:
    missing = [
        ("canonical_registry_missing", registry_error, args.canonical_registry),
        ("demo_execution_policy_missing", policy_error, args.demo_execution_policy),
        ("order_request_shadow_design_manifest_missing", design_error, Path(args.order_request_shadow_design_dir) / SOURCE_DESIGN_MANIFEST),
        ("environment_manifest_missing", env_error, Path(args.demo_environment_check_dir) / ENV_MANIFEST),
        ("symbol_contract_snapshot_missing", symbol_error, Path(args.demo_environment_check_dir) / SYMBOL_SNAPSHOT),
        ("account_snapshot_missing", account_error, Path(args.demo_environment_check_dir) / ACCOUNT_SNAPSHOT),
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
    if not canonical_registry_valid(registry):
        add_warning(warnings, args=args, warning_code="canonical_registry_boundary_mismatch", message="Canonical registry does not match fixed-candidate spread15 boundaries.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_by_config_boundary"
    if not policy_safe:
        add_warning(warnings, args=args, warning_code="demo_execution_policy_boundary_mismatch", message="Demo execution policy does not match intended equity1000/risk0.5/margin70 no-order boundaries.", source=args.demo_execution_policy, blocking_warning=True)
        return "blocked_by_config_boundary"
    source_status = str(design.get("design_status") or "")
    if source_status == "hold_no_order_shadow_plan_available":
        return "hold_no_order_request_shadow_design_available"
    if source_status.startswith("blocked_"):
        add_warning(warnings, args=args, warning_code="order_request_shadow_design_status_blocked", message=f"Design status is blocked: {source_status}", source=Path(args.order_request_shadow_design_dir) / SOURCE_DESIGN_MANIFEST, blocking_warning=True)
        return "blocked_by_order_request_shadow_design_status"
    if source_status not in {"order_request_shadow_design_fixture_only", "order_request_shadow_design_available_no_order"}:
        add_warning(warnings, args=args, warning_code="order_request_shadow_design_status_not_acceptable", message=f"Design status is not acceptable: {source_status}", source=Path(args.order_request_shadow_design_dir) / SOURCE_DESIGN_MANIFEST, blocking_warning=True)
        return "blocked_by_order_request_shadow_design_status"
    if not boundary_safe:
        add_warning(warnings, args=args, warning_code="no_request_boundary_violation", message="Design no-order/no-request boundary is missing or unsafe.", source=Path(args.order_request_shadow_design_dir) / SOURCE_DESIGN_MANIFEST, blocking_warning=True)
        return "blocked_by_no_order_boundary"
    if not env_safe:
        add_warning(warnings, args=args, warning_code="environment_artifact_invalid", message="Environment check artifact is not acceptable.", source=Path(args.demo_environment_check_dir) / ENV_MANIFEST, blocking_warning=True)
        return "blocked_by_environment_artifact"
    if not symbol_safe:
        add_warning(warnings, args=args, warning_code="symbol_contract_invalid", message="Symbol contract snapshot is missing required static fields.", source=Path(args.demo_environment_check_dir) / SYMBOL_SNAPSHOT, blocking_warning=True)
        return "blocked_by_symbol_contract"
    if not account_safe:
        add_warning(warnings, args=args, warning_code="account_snapshot_invalid", message="Redacted account snapshot is not a confirmed demo account artifact.", source=Path(args.demo_environment_check_dir) / ACCOUNT_SNAPSHOT, blocking_warning=True)
        return "blocked_by_account_snapshot"
    if not signal_safe:
        add_warning(warnings, args=args, warning_code="signal_price_preview_invalid", message="Signal price preview is missing or geometrically invalid.", source=Path(args.order_request_shadow_design_dir) / SOURCE_DESIGN_MANIFEST, blocking_warning=True)
        return "blocked_by_signal_price_preview"
    if not risk_policy_ok(risk_percent):
        add_warning(warnings, args=args, warning_code="risk_policy_invalid", message="risk_percent must be numeric, positive, and <= 1.0.", source="cli", blocking_warning=True)
        return "blocked_by_risk_policy"
    if volume_context.get("volume_preview_status") == "blocked_by_volume_formula":
        add_warning(warnings, args=args, warning_code="volume_formula_blocked", message="Static artifact fields are insufficient for the volume formula.", source=Path(args.demo_environment_check_dir) / SYMBOL_SNAPSHOT, blocking_warning=True)
        return "blocked_by_volume_formula"
    if source_status == "order_request_shadow_design_fixture_only":
        return "risk_volume_shadow_plan_fixture_only"
    return "risk_volume_shadow_plan_available_no_order"


def source_nature_for(design: dict[str, Any], plan_status: str) -> str:
    if plan_status == "risk_volume_shadow_plan_fixture_only":
        return "synthetic_fixture"
    if plan_status == "risk_volume_shadow_plan_available_no_order":
        return "live_data_shadow_signal"
    return str(design.get("source_nature") or "unclear")


def context(args: argparse.Namespace, design: dict[str, Any], registry: dict[str, Any], plan_status: str, source_nature: str, risk_distance: float | None, policy_context: dict[str, Any], volume_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "plan_status": plan_status,
        "source_nature": source_nature,
        "source_design_status": design.get("design_status", ""),
        "candidate_id": registry.get("candidate_id", EXPECTED_CANDIDATE_ID),
        "symbol": registry.get("symbol", EXPECTED_SYMBOL),
        "timeframe": registry.get("timeframe", EXPECTED_TIMEFRAME),
        "direction": registry.get("direction", EXPECTED_DIRECTION),
        "time_server": design.get("time_server", ""),
        "entry_reference_price": design.get("entry_reference_price", ""),
        "tp_price_preview": design.get("tp_price_preview", ""),
        "sl_price_preview": design.get("sl_price_preview", ""),
        "risk_distance_price": risk_distance,
        **policy_context,
        **volume_context,
        "recommended_next_step": recommended_next_step(plan_status),
    }


def main_rows(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    items = [
        ("source_design_status", ctx["source_design_status"], "acceptable order request shadow design", "checked", True, "source artifact controls scope"),
        ("source_nature", ctx["source_nature"], "synthetic_fixture or live_data_shadow_signal", "checked", True, "fixture remains non-actionable"),
        ("account_demo_artifact_confirmed", "demo account artifact", "demo and redacted", "checked", True, "artifact-only confirmation"),
        ("symbol_contract_artifact_confirmed", "symbol contract artifact", "static contract fields present", "checked", True, "no live symbol query"),
        ("signal_price_preview_confirmed", "entry/tp/sl preview", "short geometry valid", "checked", True, "not an order"),
        ("short_risk_distance_confirmed", ctx["risk_distance_price"], "> 0", "checked", True, "short risk uses SL-entry"),
        ("demo_execution_policy_loaded", ctx["demo_execution_policy_path"], "config/fixed_candidate_demo_execution_policy.json", "checked", True, "policy is artifact-only and no-order"),
        ("risk_percent_policy_confirmed", ctx["risk_percent"], "default policy risk_percent_max=0.5 unless CLI override", "checked", True, "0.5% cap keeps max risk near 5 EUR for 1000 EUR"),
        ("demo_equity_status", ctx["demo_equity"], "default policy intended_demo_equity=1000.0 EUR unless CLI override", "checked" if ctx["demo_equity"] else "formula_only", False, "omitted equity now falls back to policy"),
        ("risk_amount_policy_confirmed", ctx["risk_amount"], "policy risk_amount_max=5.0 EUR", "checked", True, "risk cap is a maximum and is not forced if margin is infeasible"),
        ("static_contract_fields_available", "tick/volume/point fields", "present where needed", "checked", True, "static artifact fields only"),
        ("volume_formula_defined", "offline formulas", "defined without broker calculation", "checked", True, "shadow preview only"),
        ("volume_preview_status", ctx["volume_preview_status"], "preview available or blocked with caveat", "checked", False, "not broker-validated"),
        ("volume_min_step_max_check", f"{ctx['volume_min']};{ctx['volume_step']};{ctx['volume_max']}", "min/step/max checked", "checked", True, "artifact contract only"),
        ("stop_level_distance_check", ctx["stop_level_check_status"], "static check or future recheck", "checked", True, "future broker-safe recheck needed"),
        ("broker_margin_check_forbidden_here", True, True, "confirmed", True, "margin validation forbidden here"),
        ("broker_profit_check_forbidden_here", True, True, "confirmed", True, "profit validation forbidden here"),
        ("order_request_construction_forbidden", True, True, "confirmed", True, "no broker payload"),
        ("order_execution_forbidden", True, True, "confirmed", True, "no execution"),
        ("future_state_reconciliation_required", "not checked", "future state plan", "required", True, "future module"),
        ("future_duplicate_protection_required", "not checked", "future duplicate guard", "required", True, "future module"),
        ("future_kill_switch_required", "not checked", "future kill-switch check", "required", True, "future module"),
        ("future_manual_approval_required", "not checked", "future manual gate", "required", True, "future module"),
    ]
    return [
        {
            **ctx,
            "plan_area": area,
            "observed_value": observed,
            "expected_value": expected,
            "plan_result": result,
            "blocking_if_failed": blocking,
            "caveat": caveat,
        }
        for area, observed, expected, result, blocking, caveat in items
    ]


def formula_rows(args: argparse.Namespace, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    formulas = [
        ("risk_amount", "demo_equity * risk_percent / 100", "demo_equity;risk_percent", "risk_amount", ctx["risk_amount"]),
        ("risk_distance_price", "sl_price_preview - entry_reference_price for short", "sl_price_preview;entry_reference_price", "risk_distance_price", ctx["risk_distance_price"]),
        ("value_per_price_unit_per_lot", "trade_tick_value / trade_tick_size", "trade_tick_value;trade_tick_size", "value_per_price_unit_per_lot", ctx["value_per_price_unit_per_lot"]),
        ("risk_per_lot", "risk_distance_price * value_per_price_unit_per_lot", "risk_distance_price;value_per_price_unit_per_lot", "risk_per_lot", (ctx["risk_distance_price"] * ctx["value_per_price_unit_per_lot"]) if ctx["risk_distance_price"] and ctx["value_per_price_unit_per_lot"] else None),
        ("raw_volume_lots", "risk_amount / risk_per_lot", "risk_amount;risk_per_lot", "raw_volume_lots", ctx["raw_volume_lots"]),
        ("stepped_volume_lots", "floor(raw_volume_lots / volume_step) * volume_step", "raw_volume_lots;volume_step", "stepped_volume_lots", ctx["stepped_volume_lots"]),
        ("stop_distance_min_price", "trade_stops_level * point", "trade_stops_level;point", "min_stop_distance_price", ctx["min_stop_distance_price"]),
    ]
    return [
        {
            "run_id": args.run_id,
            "formula_name": name,
            "formula_expression": expression,
            "input_fields": inputs,
            "output_field": output,
            "computed_value": value,
            "formula_status": ctx["formula_status"] if value not in (None, "") else "not_computed_or_not_applicable",
            "caveat": "shadow_preview_only_not_broker_validated_not_executable",
        }
        for name, expression, inputs, output, value in formulas
    ]


def requirement_rows(run_id: str) -> list[dict[str, Any]]:
    rows = [
        ("source", "live_data_signal_only", "future validation", "input is live-data shadow signal, not fixture", True, "demo_state_reconciliation_plan", "fixture cannot advance"),
        ("account", "account_demo_reconfirmed", "future validation", "demo account re-confirmed", True, "demo_state_reconciliation_plan", "read-only evidence"),
        ("symbol", "symbol_contract_reconfirmed", "future validation", "symbol contract re-confirmed", True, "demo_state_reconciliation_plan", "read-only evidence"),
        ("spread", "spread_rechecked", "future validation", "spread <= 15 broker_points", True, "demo_state_reconciliation_plan", "current spread required"),
        ("stops", "stop_levels_rechecked", "future validation", "broker stop levels compatible", True, "demo_state_reconciliation_plan", "future read-only check"),
        ("volume", "volume_min_max_step_rechecked", "future validation", "volume min/max/step compatible", True, "demo_state_reconciliation_plan", "future read-only check"),
        ("capital", "margin_adequacy_future_check", "future validation", "margin adequacy checked in explicitly allowed future module", True, "demo_state_reconciliation_plan", "not done here"),
        ("risk", "risk_percent_capped", "future validation", "risk_percent_max <= 0.5 and risk_amount_max <= 5 EUR unless explicitly reviewed", True, "demo_state_reconciliation_plan", "demo-only policy"),
        ("margin", "risk_margin_conflict_policy", "future validation", "cap by margin or block before any future executable path", True, "demo_state_reconciliation_plan", "risk cap is not forced when margin infeasible"),
        ("state", "duplicate_protection", "future validation", "no duplicate signal or position", True, "demo_state_reconciliation_plan", "future module"),
        ("state", "state_reconciliation", "future validation", "local and broker state reconciled", True, "demo_state_reconciliation_plan", "future module"),
        ("state", "idempotency_key", "future validation", "idempotency key defined", True, "demo_state_reconciliation_plan", "future module"),
        ("safety", "kill_switch_state", "future validation", "kill-switch state clear", True, "demo_state_reconciliation_plan", "future module"),
        ("manual", "manual_approval_gate", "future validation", "manual approval checkpoint present", True, "demo_state_reconciliation_plan", "no automatic advance"),
        ("audit", "audit_logging", "future validation", "audit log destination defined", True, "demo_state_reconciliation_plan", "future module"),
        ("boundary", "no_real_money_boundary", "future validation", "real-money use forbidden", True, "demo_state_reconciliation_plan", "demo-only boundary"),
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


def manifest_data(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    ctx: dict[str, Any],
    formulas: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "canonical_registry_path": str(args.canonical_registry),
        "demo_execution_policy_path": ctx["demo_execution_policy_path"],
        "order_request_shadow_design_dir": str(args.order_request_shadow_design_dir),
        "demo_environment_check_dir": str(args.demo_environment_check_dir),
        "plan_status": ctx["plan_status"],
        "source_nature": ctx["source_nature"],
        "source_design_status": ctx["source_design_status"],
        "candidate_id": ctx["candidate_id"],
        "symbol": ctx["symbol"],
        "timeframe": ctx["timeframe"],
        "direction": ctx["direction"],
        "time_server": ctx["time_server"],
        "entry_reference_price": ctx["entry_reference_price"],
        "tp_price_preview": ctx["tp_price_preview"],
        "sl_price_preview": ctx["sl_price_preview"],
        "risk_distance_price": ctx["risk_distance_price"],
        "risk_percent": ctx["risk_percent"],
        "demo_equity": ctx["demo_equity"],
        "risk_amount": ctx["risk_amount"],
        "account_currency": ctx["account_currency"],
        "policy_intended_demo_equity": ctx["policy_intended_demo_equity"],
        "policy_risk_percent_max": ctx["policy_risk_percent_max"],
        "policy_risk_amount_max": ctx["policy_risk_amount_max"],
        "policy_max_margin_usage_ratio": ctx["policy_max_margin_usage_ratio"],
        "policy_max_margin_usage_amount": ctx["policy_max_margin_usage_amount"],
        "policy_max_margin_usage_warning_ratio": ctx["policy_max_margin_usage_warning_ratio"],
        "policy_max_margin_usage_warning_amount": ctx["policy_max_margin_usage_warning_amount"],
        "trade_tick_size": ctx["trade_tick_size"],
        "trade_tick_value": ctx["trade_tick_value"],
        "value_per_price_unit_per_lot": ctx["value_per_price_unit_per_lot"],
        "raw_volume_lots": ctx["raw_volume_lots"],
        "stepped_volume_lots": ctx["stepped_volume_lots"],
        "volume_preview_status": ctx["volume_preview_status"],
        "volume_min": ctx["volume_min"],
        "volume_max": ctx["volume_max"],
        "volume_step": ctx["volume_step"],
        "stop_level_check_status": ctx["stop_level_check_status"],
        "plan_actionable": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "future_request_construction_allowed": False,
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
        "margin_validation_forbidden_here": True,
        "profit_validation_forbidden_here": True,
        "formula_row_count": len(formulas),
        "requirement_row_count": len(requirements),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "recommended_next_step": ctx["recommended_next_step"],
    }


def write_report(path: Path, *, ctx: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Risk/Volume Shadow Plan",
        "",
        "Artifact-only risk/volume shadow plan. It reads local artifacts and defines offline formulas only.",
        f"Source nature: `{ctx['source_nature']}`.",
    ]
    if ctx["source_nature"] == "synthetic_fixture":
        lines.append("The source is a synthetic fixture and is non-actionable.")
    if ctx["source_nature"] == "live_data_shadow_signal":
        lines.append("The source is live-data shadow evidence, but no order approval is given.")
    lines.extend(
        [
            "No MT5, broker, API, account, or symbol live query was performed.",
            "No database query or mutation was performed.",
            "No broker request dictionary or executable request object was constructed.",
            "No order execution was performed.",
            "No order_check or order_calc call was performed.",
            "No margin or profit validation was performed.",
            "Any volume preview is not broker-validated, not margin-validated, not executable, and not approved.",
            "The demo execution policy models 1000 EUR intended demo equity, 0.5% max risk, and 5 EUR max risk amount.",
            "The risk cap is a maximum and is not forced if margin feasibility later fails.",
            "No scheduler, loop, or background task was added.",
            "This is not demo broker approval and not a trading decision.",
            "",
            "## Formula Summary",
            "",
            f"- demo_execution_policy_path: `{ctx['demo_execution_policy_path']}`",
            f"- account_currency: `{ctx['account_currency']}`",
            f"- policy_intended_demo_equity: `{ctx['policy_intended_demo_equity']}`",
            f"- policy_risk_percent_max: `{ctx['policy_risk_percent_max']}`",
            f"- policy_risk_amount_max: `{ctx['policy_risk_amount_max']}`",
            f"- policy_max_margin_usage_ratio: `{ctx['policy_max_margin_usage_ratio']}`",
            f"- policy_max_margin_usage_warning_ratio: `{ctx['policy_max_margin_usage_warning_ratio']}`",
            f"- risk_percent: `{ctx['risk_percent']}`",
            f"- demo_equity: `{ctx['demo_equity']}`",
            f"- risk_amount: `{ctx['risk_amount']}`",
            f"- risk_distance_price: `{ctx['risk_distance_price']}`",
            f"- raw_volume_lots: `{ctx['raw_volume_lots']}`",
            f"- stepped_volume_lots: `{ctx['stepped_volume_lots']}`",
            f"- volume_preview_status: `{ctx['volume_preview_status']}`",
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
    policy, policy_error = read_json(Path(args.demo_execution_policy))
    design_dir = Path(args.order_request_shadow_design_dir)
    env_dir = Path(args.demo_environment_check_dir)
    design, design_error = read_json(design_dir / SOURCE_DESIGN_MANIFEST)
    env, env_error = read_json(env_dir / ENV_MANIFEST)
    symbol_contract, symbol_error = read_json(env_dir / SYMBOL_SNAPSHOT)
    account, account_error = read_json(env_dir / ACCOUNT_SNAPSHOT)
    source_warning_rows, _ = read_csv_rows(design_dir / SOURCE_DESIGN_WARNINGS_CSV)
    env_warning_rows, _ = read_csv_rows(env_dir / ENV_WARNINGS_CSV)
    read_csv_rows(env_dir / ENV_NO_ORDER_CSV)
    warnings = preserve_source_warnings(args, source_warning_rows, design_dir / SOURCE_DESIGN_WARNINGS_CSV)
    warnings.extend(preserve_source_warnings(args, env_warning_rows, env_dir / ENV_WARNINGS_CSV))
    policy_context = effective_policy_values(args, policy, warnings)

    boundary_safe, boundary_failures = design_boundary_ok(design)
    env_safe, env_failures = environment_ok(env)
    symbol_safe, symbol_failures = symbol_contract_ok(symbol_contract)
    account_safe, account_failures = account_snapshot_ok(account)
    signal_safe, signal_failures, risk_distance = signal_prices_ok(design)
    policy_safe = execution_policy_valid(policy)
    preliminary_volume = compute_volume_context(
        design=design,
        symbol_contract=symbol_contract,
        risk_distance_price=risk_distance,
        demo_equity=safe_float(policy_context.get("demo_equity")),
        risk_percent=safe_float(policy_context.get("risk_percent")),
    )
    plan_status = determine_plan_status(
        args=args,
        registry=registry,
        registry_error=registry_error,
        policy=policy,
        policy_error=policy_error,
        design=design,
        design_error=design_error,
        env=env,
        env_error=env_error,
        symbol_contract=symbol_contract,
        symbol_error=symbol_error,
        account=account,
        account_error=account_error,
        boundary_safe=boundary_safe,
        env_safe=env_safe,
        symbol_safe=symbol_safe,
        account_safe=account_safe,
        signal_safe=signal_safe,
        policy_safe=policy_safe,
        risk_percent=safe_float(policy_context.get("risk_percent")),
        volume_context=preliminary_volume,
        warnings=warnings,
    )
    failure_map = (
        ("blocked_by_no_order_boundary", "no_request_boundary_failed_fields", boundary_failures, design_dir / SOURCE_DESIGN_MANIFEST),
        ("blocked_by_environment_artifact", "environment_failed_fields", env_failures, env_dir / ENV_MANIFEST),
        ("blocked_by_symbol_contract", "symbol_contract_failed_fields", symbol_failures, env_dir / SYMBOL_SNAPSHOT),
        ("blocked_by_account_snapshot", "account_snapshot_failed_fields", account_failures, env_dir / ACCOUNT_SNAPSHOT),
        ("blocked_by_signal_price_preview", "signal_price_failed_fields", signal_failures, design_dir / SOURCE_DESIGN_MANIFEST),
    )
    for status, code, failures, source in failure_map:
        if plan_status == status and failures:
            add_warning(warnings, args=args, warning_code=code, message=f"Failed fields: {failures}", source=source, blocking_warning=True)
    source_nature = source_nature_for(design, plan_status)
    ctx = context(args, design, registry, plan_status, source_nature, risk_distance, policy_context, preliminary_volume)
    formulas = formula_rows(args, ctx)
    requirements = requirement_rows(args.run_id)

    write_csv(paths["main"], main_rows(ctx), MAIN_FIELDNAMES)
    write_csv(paths["formula"], formulas, FORMULA_FIELDNAMES)
    write_csv(paths["requirements"], requirements, REQUIREMENT_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_json(paths["manifest"], manifest_data(args=args, output_dir=output_dir, ctx=ctx, formulas=formulas, requirements=requirements, warnings=warnings))
    write_report(paths["report"], ctx=ctx, warnings=warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only fixed-candidate demo risk/volume shadow plan.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--order-request-shadow-design-dir", type=Path, default=DEFAULT_DESIGN_DIR)
    parser.add_argument("--demo-environment-check-dir", type=Path, default=DEFAULT_ENV_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_EXECUTION_POLICY)
    parser.add_argument("--risk-percent", type=float)
    parser.add_argument("--demo-equity", type=float)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        build_outputs(args)
    except Exception as exc:
        print(f"Fixed-candidate demo risk/volume shadow plan failed: {exc}")
        return 1
    print("Fixed-candidate demo risk/volume shadow plan complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
