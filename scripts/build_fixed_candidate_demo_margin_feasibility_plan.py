"""Build an artifact-only demo margin feasibility plan for the fixed candidate.

The plan reads local risk/volume and environment artifacts, then estimates
static margin feasibility for the intended demo execution policy. It does not
query external systems or databases, run child scripts, build broker-ready
structures, validate margin/profit through broker APIs, or perform order
operations.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_margin_feasibility_plan"
DEFAULT_RISK_VOLUME_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_risk_volume_shadow_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_risk_volume_shadow_plan_fixture_equity1000_risk05_margin70_v1"
)
DEFAULT_ENV_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_environment_check"
    / "gbpusd_short_h10_1_5_off_hours_demo_environment_check_spread15_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_margin_feasibility_plan"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_SYMBOL = "GBPUSD"
EXPECTED_TIMEFRAME = "M15"
EXPECTED_DIRECTION = "short"
EXPECTED_SPREAD_UNIT = "broker_points"
EXPECTED_MAX_SPREAD_POINTS = 15.0
EXPECTED_ACCOUNT_CURRENCY = "EUR"
EXPECTED_DEMO_EQUITY = 1000.0
EXPECTED_RISK_PERCENT = 0.5
EXPECTED_RISK_AMOUNT = 5.0
EXPECTED_MAX_MARGIN_USAGE_RATIO = 0.7
EXPECTED_MAX_MARGIN_USAGE_AMOUNT = 700.0
EXPECTED_MAX_MARGIN_USAGE_WARNING_RATIO = 0.5
EXPECTED_MAX_MARGIN_USAGE_WARNING_AMOUNT = 500.0

SOURCE_RISK_VOLUME_MANIFEST = "fixed_candidate_demo_risk_volume_shadow_plan_manifest.json"
SOURCE_RISK_VOLUME_REPORT = "fixed_candidate_demo_risk_volume_shadow_plan_report.md"
SOURCE_RISK_VOLUME_MAIN_CSV = "fixed_candidate_demo_risk_volume_shadow_plan.csv"
SOURCE_RISK_VOLUME_FORMULA_CSV = "fixed_candidate_demo_risk_volume_shadow_plan_formula.csv"
SOURCE_RISK_VOLUME_REQUIREMENTS_CSV = "fixed_candidate_demo_risk_volume_shadow_plan_requirements.csv"
SOURCE_RISK_VOLUME_WARNINGS_CSV = "fixed_candidate_demo_risk_volume_shadow_plan_warnings.csv"

ENV_MANIFEST = "fixed_candidate_demo_environment_check_manifest.json"
SYMBOL_SNAPSHOT = "fixed_candidate_demo_environment_symbol_contract_snapshot.json"
ACCOUNT_SNAPSHOT = "fixed_candidate_demo_environment_account_snapshot_redacted.json"
ENV_NO_ORDER_CSV = "fixed_candidate_demo_environment_dry_run_no_order_check.csv"
ENV_WARNINGS_CSV = "fixed_candidate_demo_environment_check_warnings.csv"

OUTPUT_MANIFEST = "fixed_candidate_demo_margin_feasibility_plan_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_margin_feasibility_plan_report.md"
OUTPUT_MAIN_CSV = "fixed_candidate_demo_margin_feasibility_plan.csv"
OUTPUT_FORMULA_CSV = "fixed_candidate_demo_margin_feasibility_plan_formula.csv"
OUTPUT_REQUIREMENTS_CSV = "fixed_candidate_demo_margin_feasibility_plan_requirements.csv"
OUTPUT_WARNINGS_CSV = "fixed_candidate_demo_margin_feasibility_plan_warnings.csv"

TRUE_SOURCE_BOUNDARY_FIELDS = (
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
    "margin_validation_forbidden_here",
    "profit_validation_forbidden_here",
)
FALSE_SOURCE_BOUNDARY_FIELDS = (
    "plan_actionable",
    "order_execution_allowed",
    "order_request_construction_allowed",
    "future_request_construction_allowed",
    "demo_broker_approval_performed",
)

MAIN_FIELDNAMES = [
    "run_id",
    "plan_status",
    "source_nature",
    "source_risk_volume_status",
    "candidate_id",
    "symbol",
    "timeframe",
    "direction",
    "intended_demo_equity",
    "risk_percent",
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
    "entry_reference_price",
    "tp_price_preview",
    "sl_price_preview",
    "risk_distance_price",
    "raw_volume_lots",
    "stepped_volume_lots",
    "volume_preview_status",
    "leverage",
    "contract_size",
    "estimated_notional_base",
    "estimated_notional_quote",
    "estimated_margin_quote",
    "estimated_margin_account_currency",
    "estimated_margin_account_currency_status",
    "approximate_margin_usage_ratio",
    "margin_usage_ratio_status",
    "max_margin_usage_ratio",
    "max_margin_usage_amount",
    "max_margin_usage_warning_ratio",
    "max_margin_usage_warning_amount",
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
        and close_float(policy.get("risk_percent_max"), EXPECTED_RISK_PERCENT)
        and close_float(policy.get("risk_amount_max"), EXPECTED_RISK_AMOUNT)
        and close_float(policy.get("max_margin_usage_ratio"), EXPECTED_MAX_MARGIN_USAGE_RATIO)
        and close_float(policy.get("max_margin_usage_amount"), EXPECTED_MAX_MARGIN_USAGE_AMOUNT)
        and close_float(policy.get("max_margin_usage_warning_ratio"), EXPECTED_MAX_MARGIN_USAGE_WARNING_RATIO)
        and close_float(policy.get("max_margin_usage_warning_amount"), EXPECTED_MAX_MARGIN_USAGE_WARNING_AMOUNT)
        and policy.get("spread_unit") == EXPECTED_SPREAD_UNIT
        and close_float(policy.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS)
        and safe_float(policy.get("max_open_positions")) == 1
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
    policy_margin_ratio = safe_float(policy.get("max_margin_usage_ratio"))
    policy_margin_amount = safe_float(policy.get("max_margin_usage_amount"))
    policy_margin_warning_ratio = safe_float(policy.get("max_margin_usage_warning_ratio"))
    policy_margin_warning_amount = safe_float(policy.get("max_margin_usage_warning_amount"))
    intended_demo_equity = safe_float(args.intended_demo_equity) if args.intended_demo_equity is not None else policy_demo_equity
    max_margin_usage_ratio = safe_float(args.max_margin_usage_ratio) if args.max_margin_usage_ratio is not None else policy_margin_ratio
    max_margin_usage_amount = None
    if intended_demo_equity is not None and max_margin_usage_ratio is not None:
        max_margin_usage_amount = intended_demo_equity * max_margin_usage_ratio
    max_margin_usage_warning_amount = None
    if intended_demo_equity is not None and policy_margin_warning_ratio is not None:
        max_margin_usage_warning_amount = intended_demo_equity * policy_margin_warning_ratio

    if args.intended_demo_equity is not None and policy_demo_equity is not None and not close_float(args.intended_demo_equity, policy_demo_equity):
        add_warning(
            warnings,
            args=args,
            warning_code="intended_demo_equity_policy_override",
            message=f"CLI intended demo equity {args.intended_demo_equity} differs from policy intended_demo_equity {policy_demo_equity}.",
            source="cli",
            blocking_warning=False,
            severity="warning",
        )
    if args.max_margin_usage_ratio is not None and policy_margin_ratio is not None and not close_float(args.max_margin_usage_ratio, policy_margin_ratio):
        add_warning(
            warnings,
            args=args,
            warning_code="max_margin_usage_ratio_policy_override",
            message=f"CLI max margin usage ratio {args.max_margin_usage_ratio} differs from policy max_margin_usage_ratio {policy_margin_ratio}.",
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
        "policy_max_margin_usage_ratio": policy_margin_ratio,
        "policy_max_margin_usage_amount": policy_margin_amount,
        "policy_max_margin_usage_warning_ratio": policy_margin_warning_ratio,
        "policy_max_margin_usage_warning_amount": policy_margin_warning_amount,
        "intended_demo_equity": intended_demo_equity,
        "max_margin_usage_ratio": max_margin_usage_ratio,
        "max_margin_usage_amount": max_margin_usage_amount,
        "max_margin_usage_warning_ratio": policy_margin_warning_ratio,
        "max_margin_usage_warning_amount": max_margin_usage_warning_amount,
    }


def source_boundary_ok(source: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for field in TRUE_SOURCE_BOUNDARY_FIELDS:
        if as_bool(source.get(field)) is not True:
            failures.append(field)
    for field in FALSE_SOURCE_BOUNDARY_FIELDS:
        if as_bool(source.get(field)) is not False:
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


def account_ok(account: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    mode = account.get("account_trade_mode_label") or account.get("account_mode_label")
    if mode != "demo":
        failures.append("account_trade_mode_label")
    if as_bool(account.get("is_demo_account")) is not True:
        failures.append("is_demo_account")
    if as_bool(account.get("redaction_applied")) is not True:
        failures.append("redaction_applied")
    leverage = safe_float(account.get("leverage"))
    if account.get("leverage") not in ("", None) and (leverage is None or leverage <= 0):
        failures.append("leverage")
    currency = account.get("currency")
    if currency not in ("", None) and currency != "EUR":
        failures.append("currency")
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
    for field in ("trade_tick_size", "trade_tick_value", "trade_contract_size"):
        value = safe_float(symbol_contract.get(field))
        if value is None or value <= 0:
            failures.append(field)
    for field in ("trade_stops_level", "trade_freeze_level"):
        if field not in symbol_contract:
            failures.append(field)
    return not failures, failures


def risk_volume_preview_ok(source: dict[str, Any], intended_demo_equity: float, risk_percent_max: float | None) -> tuple[bool, list[str]]:
    failures: list[str] = []
    risk_percent = safe_float(source.get("risk_percent"))
    if risk_percent is None or risk_percent <= 0 or risk_percent > 1.0:
        failures.append("risk_percent")
    if risk_percent is not None and risk_percent_max is not None and risk_percent > risk_percent_max + 1e-6:
        failures.append("risk_percent_above_policy_max")
    risk_amount = safe_float(source.get("risk_amount"))
    if risk_amount is not None and risk_percent is not None:
        expected_risk_amount = intended_demo_equity * risk_percent / 100.0
        if abs(risk_amount - expected_risk_amount) > 0.02:
            failures.append("risk_amount")
    status = source.get("volume_preview_status")
    if status not in {
        "shadow_volume_preview_available_not_broker_validated",
        "blocked_missing_demo_equity",
        "blocked_below_min_volume",
        "blocked_above_max_volume",
    }:
        failures.append("volume_preview_status")
    return not failures, failures


def compute_margin_context(
    *,
    source: dict[str, Any],
    account: dict[str, Any],
    symbol_contract: dict[str, Any],
    intended_demo_equity: float,
    max_margin_usage_ratio: float,
    max_margin_usage_amount: float | None,
    max_margin_usage_warning_ratio: float | None,
    max_margin_usage_warning_amount: float | None,
) -> dict[str, Any]:
    risk_percent = safe_float(source.get("risk_percent"))
    risk_amount = intended_demo_equity * risk_percent / 100.0 if risk_percent is not None else None
    entry_reference_price = safe_float(source.get("entry_reference_price"))
    stepped_volume = safe_float(source.get("stepped_volume_lots"))
    raw_volume = safe_float(source.get("raw_volume_lots"))
    contract_size = safe_float(symbol_contract.get("trade_contract_size"))
    leverage = safe_float(account.get("leverage"))
    estimated_notional_base = None
    estimated_notional_quote = None
    estimated_margin_quote = None
    estimated_margin_account_currency = None
    approximate_margin_usage_ratio = None
    estimated_margin_account_currency_status = "requires_currency_conversion_or_broker_validation"
    margin_usage_ratio_status = "requires_future_broker_validation"

    if stepped_volume is not None and entry_reference_price is not None and contract_size is not None:
        estimated_notional_base = stepped_volume * contract_size
        estimated_notional_quote = estimated_notional_base * entry_reference_price
        if leverage is not None and leverage > 0:
            estimated_margin_quote = estimated_notional_quote / leverage
            account_currency = account.get("currency")
            if account_currency == "USD":
                estimated_margin_account_currency = estimated_margin_quote
                estimated_margin_account_currency_status = "static_artifact_estimate_only_account_currency_matches_quote"
                approximate_margin_usage_ratio = estimated_margin_account_currency / intended_demo_equity
                margin_usage_ratio_status = "static_artifact_account_currency_estimate"
            else:
                approximate_margin_usage_ratio = estimated_margin_quote / intended_demo_equity
                margin_usage_ratio_status = "quote_currency_approximation_not_broker_validated"

    margin_estimate_status = "formula_available" if estimated_margin_quote is not None else "formula_only_missing_volume_or_leverage"
    over_margin_policy = approximate_margin_usage_ratio is not None and approximate_margin_usage_ratio > max_margin_usage_ratio
    if estimated_margin_quote is not None and max_margin_usage_amount is not None and estimated_margin_quote > max_margin_usage_amount:
        over_margin_policy = True
    over_margin_warning = approximate_margin_usage_ratio is not None and max_margin_usage_warning_ratio is not None and approximate_margin_usage_ratio > max_margin_usage_warning_ratio
    if estimated_margin_quote is not None and max_margin_usage_warning_amount is not None and estimated_margin_quote > max_margin_usage_warning_amount:
        over_margin_warning = True
    return {
        "risk_percent": risk_percent,
        "risk_amount": risk_amount,
        "entry_reference_price": entry_reference_price,
        "tp_price_preview": safe_float(source.get("tp_price_preview")),
        "sl_price_preview": safe_float(source.get("sl_price_preview")),
        "risk_distance_price": safe_float(source.get("risk_distance_price")),
        "raw_volume_lots": raw_volume,
        "stepped_volume_lots": stepped_volume,
        "volume_preview_status": source.get("volume_preview_status", ""),
        "volume_min": safe_float(source.get("volume_min")),
        "volume_max": safe_float(source.get("volume_max")),
        "volume_step": safe_float(source.get("volume_step")),
        "leverage": leverage,
        "contract_size": contract_size,
        "estimated_notional_base": estimated_notional_base,
        "estimated_notional_quote": estimated_notional_quote,
        "estimated_margin_quote": estimated_margin_quote,
        "estimated_margin_account_currency": estimated_margin_account_currency,
        "estimated_margin_account_currency_status": estimated_margin_account_currency_status,
        "approximate_margin_usage_ratio": approximate_margin_usage_ratio,
        "margin_usage_ratio_status": margin_usage_ratio_status,
        "margin_estimate_status": margin_estimate_status,
        "over_margin_policy": over_margin_policy,
        "over_margin_warning": over_margin_warning,
        "max_margin_usage_amount": max_margin_usage_amount,
        "max_margin_usage_warning_ratio": max_margin_usage_warning_ratio,
        "max_margin_usage_warning_amount": max_margin_usage_warning_amount,
    }


def recommended_next_step(plan_status: str) -> str:
    if plan_status == "margin_feasibility_plan_fixture_only":
        return "wait_for_live_shadow_signal_or_continue_no_order_monitoring"
    if plan_status == "margin_feasibility_plan_available_no_order":
        return "build_fixed_candidate_demo_state_reconciliation_plan"
    if plan_status == "margin_feasibility_formula_only_missing_volume":
        return "rerun_risk_volume_shadow_plan_with_execution_policy_equity1000_risk05"
    if plan_status == "margin_feasibility_hold_requires_broker_margin_validation":
        return "reduce_risk_or_verify_margin_with_future_allowed_module"
    if plan_status.startswith("hold_"):
        return "continue_no_order_monitoring"
    return "fix_margin_feasibility_plan_blocker"


def determine_plan_status(
    *,
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_error: str,
    policy: dict[str, Any],
    policy_error: str,
    source: dict[str, Any],
    source_error: str,
    env: dict[str, Any],
    env_error: str,
    account: dict[str, Any],
    account_error: str,
    symbol_contract: dict[str, Any],
    symbol_error: str,
    boundary_safe: bool,
    env_safe: bool,
    account_safe: bool,
    symbol_safe: bool,
    risk_preview_safe: bool,
    policy_safe: bool,
    margin_context: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> str:
    missing = [
        ("canonical_registry_missing", registry_error, args.canonical_registry),
        ("demo_execution_policy_missing", policy_error, args.demo_execution_policy),
        ("risk_volume_manifest_missing", source_error, Path(args.risk_volume_shadow_plan_dir) / SOURCE_RISK_VOLUME_MANIFEST),
        ("environment_manifest_missing", env_error, Path(args.demo_environment_check_dir) / ENV_MANIFEST),
        ("account_snapshot_missing", account_error, Path(args.demo_environment_check_dir) / ACCOUNT_SNAPSHOT),
        ("symbol_contract_snapshot_missing", symbol_error, Path(args.demo_environment_check_dir) / SYMBOL_SNAPSHOT),
    ]
    missing_errors = [item for item in missing if item[1] == "missing"]
    if missing_errors:
        for code, _error, path in missing_errors:
            add_warning(warnings, args=args, warning_code=code, message="Required input artifact is missing.", source=path, blocking_warning=True)
        return "blocked_missing_required_artifact"
    unreadable_errors = [item for item in missing if item[1]]
    if unreadable_errors:
        for code, error, path in unreadable_errors:
            add_warning(warnings, args=args, warning_code=code.replace("missing", "unreadable"), message=f"Required input artifact is unreadable: {error}", source=path, blocking_warning=True)
        return "blocked_unreadable_input"
    if not canonical_registry_valid(registry):
        add_warning(warnings, args=args, warning_code="canonical_registry_boundary_mismatch", message="Canonical registry does not match fixed-candidate spread15 boundaries.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_by_config_boundary"
    if not policy_safe:
        add_warning(warnings, args=args, warning_code="demo_execution_policy_boundary_mismatch", message="Demo execution policy does not match intended equity1000/risk0.5/margin70 no-order boundaries.", source=args.demo_execution_policy, blocking_warning=True)
        return "blocked_by_config_boundary"
    status = str(source.get("plan_status") or "")
    if status == "hold_no_order_request_shadow_design_available":
        return "hold_no_order_request_shadow_design_available"
    if status.startswith("blocked_"):
        add_warning(warnings, args=args, warning_code="risk_volume_status_blocked", message=f"Risk/volume plan status is blocked: {status}", source=Path(args.risk_volume_shadow_plan_dir) / SOURCE_RISK_VOLUME_MANIFEST, blocking_warning=True)
        return "blocked_by_risk_volume_status"
    if status not in {"risk_volume_shadow_plan_fixture_only", "risk_volume_shadow_plan_available_no_order"}:
        add_warning(warnings, args=args, warning_code="risk_volume_status_not_acceptable", message=f"Risk/volume plan status is not acceptable: {status}", source=Path(args.risk_volume_shadow_plan_dir) / SOURCE_RISK_VOLUME_MANIFEST, blocking_warning=True)
        return "blocked_by_risk_volume_status"
    if not boundary_safe:
        add_warning(warnings, args=args, warning_code="no_request_boundary_violation", message="Risk/volume no-order/no-request boundary is missing or unsafe.", source=Path(args.risk_volume_shadow_plan_dir) / SOURCE_RISK_VOLUME_MANIFEST, blocking_warning=True)
        return "blocked_by_no_order_boundary"
    if not env_safe:
        add_warning(warnings, args=args, warning_code="environment_artifact_invalid", message="Environment artifact is not acceptable.", source=Path(args.demo_environment_check_dir) / ENV_MANIFEST, blocking_warning=True)
        return "blocked_by_environment_artifact"
    if not account_safe:
        add_warning(warnings, args=args, warning_code="account_snapshot_invalid", message="Account snapshot is not an acceptable redacted EUR demo artifact.", source=Path(args.demo_environment_check_dir) / ACCOUNT_SNAPSHOT, blocking_warning=True)
        return "blocked_by_account_snapshot"
    if not symbol_safe:
        add_warning(warnings, args=args, warning_code="symbol_contract_invalid", message="Symbol contract snapshot is missing required static fields.", source=Path(args.demo_environment_check_dir) / SYMBOL_SNAPSHOT, blocking_warning=True)
        return "blocked_by_symbol_contract"
    if not risk_preview_safe:
        add_warning(warnings, args=args, warning_code="risk_volume_preview_invalid", message="Risk/volume preview is inconsistent with intended 1000 EUR / 0.5% / 5 EUR policy.", source=Path(args.risk_volume_shadow_plan_dir) / SOURCE_RISK_VOLUME_MANIFEST, blocking_warning=True)
        return "blocked_by_volume_preview"
    if safe_float(source.get("risk_percent")) is not None and safe_float(source.get("risk_percent")) > EXPECTED_RISK_PERCENT:
        add_warning(warnings, args=args, warning_code="risk_percent_above_policy", message="Risk percent exceeds policy risk_percent_max 0.5.", source=Path(args.risk_volume_shadow_plan_dir) / SOURCE_RISK_VOLUME_MANIFEST, blocking_warning=True)
        return "blocked_by_volume_preview"
    if source.get("volume_preview_status") == "blocked_missing_demo_equity" or margin_context["margin_estimate_status"] != "formula_available":
        return "margin_feasibility_formula_only_missing_volume"
    if margin_context["over_margin_policy"]:
        add_warning(
            warnings,
            args=args,
            warning_code="static_margin_usage_above_policy",
            message="Static quote-currency margin approximation exceeds max margin usage ratio.",
            source=Path(args.risk_volume_shadow_plan_dir) / SOURCE_RISK_VOLUME_MANIFEST,
            blocking_warning=False,
            severity="warning",
        )
        return "margin_feasibility_hold_requires_broker_margin_validation"
    if margin_context["over_margin_warning"]:
        add_warning(
            warnings,
            args=args,
            warning_code="margin_usage_above_warning_threshold",
            message="Static margin approximation exceeds the 50% warning threshold but remains within the 70% policy cap.",
            source=Path(args.risk_volume_shadow_plan_dir) / SOURCE_RISK_VOLUME_MANIFEST,
            blocking_warning=False,
            severity="warning",
        )
    if status == "risk_volume_shadow_plan_fixture_only":
        return "margin_feasibility_plan_fixture_only"
    return "margin_feasibility_plan_available_no_order"


def source_nature_for(source: dict[str, Any], plan_status: str) -> str:
    if plan_status == "margin_feasibility_plan_fixture_only":
        return "synthetic_fixture"
    if plan_status == "margin_feasibility_plan_available_no_order":
        return "live_data_shadow_signal"
    return str(source.get("source_nature") or "unclear")


def context(args: argparse.Namespace, source: dict[str, Any], registry: dict[str, Any], plan_status: str, source_nature: str, policy_context: dict[str, Any], margin_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "plan_status": plan_status,
        "source_nature": source_nature,
        "source_risk_volume_status": source.get("plan_status", ""),
        "candidate_id": registry.get("candidate_id", EXPECTED_CANDIDATE_ID),
        "symbol": registry.get("symbol", EXPECTED_SYMBOL),
        "timeframe": registry.get("timeframe", EXPECTED_TIMEFRAME),
        "direction": registry.get("direction", EXPECTED_DIRECTION),
        **policy_context,
        **margin_context,
        "recommended_next_step": recommended_next_step(plan_status),
    }


def main_rows(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    items = [
        ("source_risk_volume_status", ctx["source_risk_volume_status"], "acceptable risk/volume status", "checked", True, "source artifact controls scope"),
        ("source_nature", ctx["source_nature"], "synthetic_fixture or live_data_shadow_signal", "checked", True, "fixture remains non-actionable"),
        ("demo_execution_policy_loaded", ctx["demo_execution_policy_path"], "config/fixed_candidate_demo_execution_policy.json", "checked", True, "policy is artifact-only and no-order"),
        ("intended_demo_equity_confirmed", ctx["intended_demo_equity"], "1000.0 EUR", "checked", True, "future demo account should mirror intended account size"),
        ("risk_percent_policy_confirmed", ctx["risk_percent"], "risk_percent_max=0.5", "checked", True, "risk cap is not forced if margin is infeasible"),
        ("risk_amount_confirmed", ctx["risk_amount"], "max 5 EUR from 0.5% of 1000 EUR", "checked", True, "risk cap remains near 5 EUR"),
        ("volume_preview_status", ctx["volume_preview_status"], "static volume preview or formula-only caveat", "checked", False, "not broker-validated"),
        ("symbol_contract_static_fields", ctx["contract_size"], "contract size and volume fields available", "checked", True, "static artifact only"),
        ("leverage_static_field", ctx["leverage"], "numeric leverage from redacted artifact", "checked", True, "static artifact only"),
        ("static_margin_formula_available", ctx["margin_estimate_status"], "formula_available", "checked", False, "no broker margin validation"),
        ("estimated_notional_base", ctx["estimated_notional_base"], "stepped_volume_lots * contract_size", "estimated", False, "static_artifact_estimate_only"),
        ("estimated_notional_quote", ctx["estimated_notional_quote"], "estimated_notional_base * entry_reference_price", "estimated", False, "quote currency estimate"),
        ("estimated_margin_quote", ctx["estimated_margin_quote"], "estimated_notional_quote / leverage", "estimated", False, "not_order_calc_margin"),
        ("currency_conversion_status", ctx["estimated_margin_account_currency_status"], "requires conversion or broker validation for EUR", "checked", False, "no live FX lookup"),
        ("margin_usage_ratio_status", ctx["margin_usage_ratio_status"], "static approximation or future validation required", "checked", False, "not broker-validated"),
        ("max_margin_usage_policy", ctx["max_margin_usage_ratio"], "<= 0.70 configured policy", "checked", False, "hold if static estimate exceeds policy"),
        ("max_margin_usage_amount_policy", ctx["max_margin_usage_amount"], "<= 700.0 EUR static reference", "checked", False, "hold if static estimate exceeds policy"),
        ("margin_usage_warning_policy", ctx["max_margin_usage_warning_ratio"], "warning above 0.50 or 500.0 EUR", "checked", False, "non-blocking elevated margin warning"),
        ("order_calc_margin_forbidden_here", True, True, "confirmed", True, "no margin API call"),
        ("broker_margin_validation_required_future", True, True, "required", True, "future explicitly allowed module"),
        ("plan_actionable_false", False, False, "confirmed", True, "no approval"),
        ("future_state_reconciliation_required", "not checked", "future state plan", "required", True, "future module"),
        ("future_duplicate_protection_required", "not checked", "future duplicate guard", "required", True, "future module"),
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
        ("risk_amount", "intended_demo_equity * risk_percent / 100", "intended_demo_equity;risk_percent", "risk_amount", ctx["risk_amount"]),
        ("estimated_notional_base", "stepped_volume_lots * contract_size", "stepped_volume_lots;contract_size", "estimated_notional_base", ctx["estimated_notional_base"]),
        ("estimated_notional_quote", "estimated_notional_base * entry_reference_price", "estimated_notional_base;entry_reference_price", "estimated_notional_quote", ctx["estimated_notional_quote"]),
        ("estimated_margin_quote", "estimated_notional_quote / leverage", "estimated_notional_quote;leverage", "estimated_margin_quote", ctx["estimated_margin_quote"]),
        ("approximate_margin_usage_ratio", "estimated_margin_quote / intended_demo_equity", "estimated_margin_quote;intended_demo_equity", "approximate_margin_usage_ratio", ctx["approximate_margin_usage_ratio"]),
    ]
    return [
        {
            "run_id": args.run_id,
            "formula_name": name,
            "formula_expression": expression,
            "input_fields": inputs,
            "output_field": output,
            "computed_value": value,
            "formula_status": "computed_static_artifact_estimate" if value not in (None, "") else "not_computed",
            "caveat": "static_artifact_estimate_only;not_order_calc_margin;not_broker_validated;not_executable",
        }
        for name, expression, inputs, output, value in formulas
    ]


def requirement_rows(run_id: str) -> list[dict[str, Any]]:
    rows = [
        ("source", "live_data_signal_only", "future validation", "input is live-data shadow signal, not fixture", True, "demo_state_reconciliation_plan", "fixture cannot advance"),
        ("account", "account_demo_reconfirmed", "future validation", "demo account re-confirmed", True, "demo_state_reconciliation_plan", "read-only evidence"),
        ("account", "equity_free_margin_current_read_only_check", "future validation", "account equity and free margin current and read-only checked", True, "demo_state_reconciliation_plan", "future broker-safe check"),
        ("symbol", "symbol_contract_current_compatible", "future validation", "symbol contract current and compatible", True, "demo_state_reconciliation_plan", "future read-only check"),
        ("spread", "current_spread_rechecked", "future validation", "spread <= 15 broker_points", True, "demo_state_reconciliation_plan", "future read-only check"),
        ("stops", "stop_levels_rechecked", "future validation", "stop levels compatible", True, "demo_state_reconciliation_plan", "future read-only check"),
        ("volume", "volume_min_max_step_rechecked", "future validation", "volume min/max/step compatible", True, "demo_state_reconciliation_plan", "future read-only check"),
        ("margin", "broker_margin_future_validation", "future validation", "margin checked in explicitly allowed future module", True, "demo_state_reconciliation_plan", "not done here"),
        ("risk", "risk_percent_capped", "future validation", "risk_percent_max <= 0.5 and risk_amount_max <= 5 EUR", True, "demo_state_reconciliation_plan", "1000 EUR account policy"),
        ("margin", "max_margin_usage_capped", "future validation", "margin usage ratio <= 0.70 and amount <= 700 EUR before any future executable path", True, "demo_state_reconciliation_plan", "future broker validation still required"),
        ("margin", "margin_usage_warning_threshold", "future validation", "margin usage above 0.50 or 500 EUR is elevated and must be reviewed", False, "demo_state_reconciliation_plan", "non-blocking warning threshold"),
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
        "risk_volume_shadow_plan_dir": str(args.risk_volume_shadow_plan_dir),
        "demo_environment_check_dir": str(args.demo_environment_check_dir),
        "plan_status": ctx["plan_status"],
        "source_nature": ctx["source_nature"],
        "source_risk_volume_status": ctx["source_risk_volume_status"],
        "candidate_id": ctx["candidate_id"],
        "symbol": ctx["symbol"],
        "timeframe": ctx["timeframe"],
        "direction": ctx["direction"],
        "intended_demo_equity": ctx["intended_demo_equity"],
        "risk_percent": ctx["risk_percent"],
        "risk_amount": ctx["risk_amount"],
        "account_currency": ctx["account_currency"],
        "policy_intended_demo_equity": ctx["policy_intended_demo_equity"],
        "policy_risk_percent_max": ctx["policy_risk_percent_max"],
        "policy_risk_amount_max": ctx["policy_risk_amount_max"],
        "policy_max_margin_usage_ratio": ctx["policy_max_margin_usage_ratio"],
        "policy_max_margin_usage_amount": ctx["policy_max_margin_usage_amount"],
        "policy_max_margin_usage_warning_ratio": ctx["policy_max_margin_usage_warning_ratio"],
        "policy_max_margin_usage_warning_amount": ctx["policy_max_margin_usage_warning_amount"],
        "entry_reference_price": ctx["entry_reference_price"],
        "tp_price_preview": ctx["tp_price_preview"],
        "sl_price_preview": ctx["sl_price_preview"],
        "risk_distance_price": ctx["risk_distance_price"],
        "raw_volume_lots": ctx["raw_volume_lots"],
        "stepped_volume_lots": ctx["stepped_volume_lots"],
        "volume_preview_status": ctx["volume_preview_status"],
        "volume_min": ctx["volume_min"],
        "volume_max": ctx["volume_max"],
        "volume_step": ctx["volume_step"],
        "leverage": ctx["leverage"],
        "contract_size": ctx["contract_size"],
        "estimated_notional_base": ctx["estimated_notional_base"],
        "estimated_notional_quote": ctx["estimated_notional_quote"],
        "estimated_margin_quote": ctx["estimated_margin_quote"],
        "estimated_margin_account_currency": ctx["estimated_margin_account_currency"],
        "estimated_margin_account_currency_status": ctx["estimated_margin_account_currency_status"],
        "approximate_margin_usage_ratio": ctx["approximate_margin_usage_ratio"],
        "margin_usage_ratio_status": ctx["margin_usage_ratio_status"],
        "max_margin_usage_ratio": ctx["max_margin_usage_ratio"],
        "max_margin_usage_amount": ctx["max_margin_usage_amount"],
        "max_margin_usage_warning_ratio": ctx["max_margin_usage_warning_ratio"],
        "max_margin_usage_warning_amount": ctx["max_margin_usage_warning_amount"],
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
        "order_calc_margin_forbidden_here": True,
        "broker_margin_validation_required_future": True,
        "margin_estimate_static_artifact_only": True,
        "formula_row_count": len(formulas),
        "requirement_row_count": len(requirements),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "recommended_next_step": ctx["recommended_next_step"],
    }


def write_report(path: Path, *, ctx: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Margin Feasibility Plan",
        "",
        "Artifact-only margin feasibility plan.",
        "Intended demo equity: 1000 EUR.",
        "Risk percent max: 0.5%.",
        "Risk amount max: 5 EUR.",
        "Max margin usage policy: 70% or about 700 EUR static reference.",
        "Margin usage above 50% or about 500 EUR is an elevated non-blocking warning threshold.",
        f"Source nature: `{ctx['source_nature']}`.",
    ]
    if ctx["source_nature"] == "synthetic_fixture":
        lines.append("The source is synthetic/non-actionable.")
    if ctx["source_nature"] == "live_data_shadow_signal":
        lines.append("The source is live-data shadow evidence, but no order approval is given.")
    lines.extend(
        [
            "No MT5, broker, API, account, or symbol live query was performed.",
            "No database query or mutation was performed.",
            "No broker request dictionary or executable request object was constructed.",
            "No order execution was performed.",
            "No order_check, order_calc_margin, or order_calc_profit call was performed.",
            "No broker margin validation was performed.",
            "Margin estimates are static artifact-only and not executable.",
            "The risk cap is a maximum and is not forced if static margin feasibility is weak.",
            "Static margin usage above 50% is elevated, but usage below the 70% policy cap is acceptable for artifact-only planning.",
            "Future broker margin validation is still required before any later executable path.",
            "No scheduler, loop, or background task was added.",
            "This is not demo broker approval and not a trading decision.",
            "",
            "## Margin Estimate Summary",
            "",
            f"- demo_execution_policy_path: `{ctx['demo_execution_policy_path']}`",
            f"- account_currency: `{ctx['account_currency']}`",
            f"- policy_intended_demo_equity: `{ctx['policy_intended_demo_equity']}`",
            f"- policy_risk_percent_max: `{ctx['policy_risk_percent_max']}`",
            f"- policy_risk_amount_max: `{ctx['policy_risk_amount_max']}`",
            f"- policy_max_margin_usage_ratio: `{ctx['policy_max_margin_usage_ratio']}`",
            f"- policy_max_margin_usage_warning_ratio: `{ctx['policy_max_margin_usage_warning_ratio']}`",
            f"- plan_status: `{ctx['plan_status']}`",
            f"- risk_percent: `{ctx['risk_percent']}`",
            f"- risk_amount: `{ctx['risk_amount']}`",
            f"- volume_preview_status: `{ctx['volume_preview_status']}`",
            f"- estimated_margin_quote: `{ctx['estimated_margin_quote']}`",
            f"- approximate_margin_usage_ratio: `{ctx['approximate_margin_usage_ratio']}`",
            f"- margin_usage_ratio_status: `{ctx['margin_usage_ratio_status']}`",
            f"- max_margin_usage_ratio: `{ctx['max_margin_usage_ratio']}`",
            f"- max_margin_usage_amount: `{ctx['max_margin_usage_amount']}`",
            f"- max_margin_usage_warning_ratio: `{ctx['max_margin_usage_warning_ratio']}`",
            f"- max_margin_usage_warning_amount: `{ctx['max_margin_usage_warning_amount']}`",
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
    risk_dir = Path(args.risk_volume_shadow_plan_dir)
    env_dir = Path(args.demo_environment_check_dir)
    source, source_error = read_json(risk_dir / SOURCE_RISK_VOLUME_MANIFEST)
    env, env_error = read_json(env_dir / ENV_MANIFEST)
    account, account_error = read_json(env_dir / ACCOUNT_SNAPSHOT)
    symbol_contract, symbol_error = read_json(env_dir / SYMBOL_SNAPSHOT)
    source_warning_rows, _ = read_csv_rows(risk_dir / SOURCE_RISK_VOLUME_WARNINGS_CSV)
    env_warning_rows, _ = read_csv_rows(env_dir / ENV_WARNINGS_CSV)
    read_csv_rows(risk_dir / SOURCE_RISK_VOLUME_FORMULA_CSV)
    read_csv_rows(risk_dir / SOURCE_RISK_VOLUME_REQUIREMENTS_CSV)
    read_csv_rows(env_dir / ENV_NO_ORDER_CSV)
    warnings = preserve_source_warnings(args, source_warning_rows, risk_dir / SOURCE_RISK_VOLUME_WARNINGS_CSV)
    warnings.extend(preserve_source_warnings(args, env_warning_rows, env_dir / ENV_WARNINGS_CSV))
    policy_context = effective_policy_values(args, policy, warnings)

    intended_demo_equity = safe_float(policy_context.get("intended_demo_equity")) or EXPECTED_DEMO_EQUITY
    max_margin_usage_ratio = safe_float(policy_context.get("max_margin_usage_ratio")) or EXPECTED_MAX_MARGIN_USAGE_RATIO
    max_margin_usage_amount = safe_float(policy_context.get("max_margin_usage_amount"))
    max_margin_usage_warning_ratio = safe_float(policy_context.get("max_margin_usage_warning_ratio"))
    max_margin_usage_warning_amount = safe_float(policy_context.get("max_margin_usage_warning_amount"))
    boundary_safe, boundary_failures = source_boundary_ok(source)
    env_safe, env_failures = environment_ok(env)
    account_safe, account_failures = account_ok(account)
    symbol_safe, symbol_failures = symbol_contract_ok(symbol_contract)
    policy_safe = execution_policy_valid(policy)
    risk_preview_safe, risk_preview_failures = risk_volume_preview_ok(source, intended_demo_equity, safe_float(policy_context.get("policy_risk_percent_max")))
    margin_context = compute_margin_context(
        source=source,
        account=account,
        symbol_contract=symbol_contract,
        intended_demo_equity=intended_demo_equity,
        max_margin_usage_ratio=max_margin_usage_ratio,
        max_margin_usage_amount=max_margin_usage_amount,
        max_margin_usage_warning_ratio=max_margin_usage_warning_ratio,
        max_margin_usage_warning_amount=max_margin_usage_warning_amount,
    )
    plan_status = determine_plan_status(
        args=args,
        registry=registry,
        registry_error=registry_error,
        policy=policy,
        policy_error=policy_error,
        source=source,
        source_error=source_error,
        env=env,
        env_error=env_error,
        account=account,
        account_error=account_error,
        symbol_contract=symbol_contract,
        symbol_error=symbol_error,
        boundary_safe=boundary_safe,
        env_safe=env_safe,
        account_safe=account_safe,
        symbol_safe=symbol_safe,
        risk_preview_safe=risk_preview_safe,
        policy_safe=policy_safe,
        margin_context=margin_context,
        warnings=warnings,
    )
    failure_map = (
        ("blocked_by_no_order_boundary", "no_request_boundary_failed_fields", boundary_failures, risk_dir / SOURCE_RISK_VOLUME_MANIFEST),
        ("blocked_by_environment_artifact", "environment_failed_fields", env_failures, env_dir / ENV_MANIFEST),
        ("blocked_by_account_snapshot", "account_failed_fields", account_failures, env_dir / ACCOUNT_SNAPSHOT),
        ("blocked_by_symbol_contract", "symbol_contract_failed_fields", symbol_failures, env_dir / SYMBOL_SNAPSHOT),
        ("blocked_by_volume_preview", "risk_volume_failed_fields", risk_preview_failures, risk_dir / SOURCE_RISK_VOLUME_MANIFEST),
    )
    for status, code, failures, source_path in failure_map:
        if plan_status == status and failures:
            add_warning(warnings, args=args, warning_code=code, message=f"Failed fields: {failures}", source=source_path, blocking_warning=True)
    source_nature = source_nature_for(source, plan_status)
    ctx = context(args, source, registry, plan_status, source_nature, policy_context, margin_context)
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
    parser = argparse.ArgumentParser(description="Build an artifact-only fixed-candidate demo margin feasibility plan.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--risk-volume-shadow-plan-dir", type=Path, default=DEFAULT_RISK_VOLUME_DIR)
    parser.add_argument("--demo-environment-check-dir", type=Path, default=DEFAULT_ENV_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_EXECUTION_POLICY)
    parser.add_argument("--intended-demo-equity", type=float)
    parser.add_argument("--max-margin-usage-ratio", type=float)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        build_outputs(args)
    except Exception as exc:
        print(f"Fixed-candidate demo margin feasibility plan failed: {exc}")
        return 1
    print("Fixed-candidate demo margin feasibility plan complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
