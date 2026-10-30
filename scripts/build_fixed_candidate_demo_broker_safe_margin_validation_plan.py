"""Build an artifact-only broker-safe margin validation plan.

This module reads existing local artifacts and writes a plan for a separate,
explicitly authorized future broker-safe margin validation check. It does not
import or connect to MT5, query account/symbol state, query databases, run child
scripts, construct broker-ready structures, validate margin/profit through a
broker API, or perform order operations.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_broker_safe_margin_validation_plan"
DEFAULT_MARGIN_FEASIBILITY_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_margin_feasibility_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_margin_feasibility_plan_fixture_equity1000_risk05_margin70_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_FUTURE_SCRIPT = BASE_DIR / "scripts" / "check_fixed_candidate_demo_broker_safe_margin_validation.py"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_broker_safe_margin_validation_plan"

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
EXPECTED_MAX_MARGIN_USAGE_WARNING_RATIO = 0.5
EXPECTED_MAX_MARGIN_USAGE_RATIO = 0.7
EXPECTED_MAX_MARGIN_USAGE_AMOUNT = 700.0

SOURCE_MANIFEST = "fixed_candidate_demo_margin_feasibility_plan_manifest.json"
SOURCE_REPORT = "fixed_candidate_demo_margin_feasibility_plan_report.md"
SOURCE_MAIN_CSV = "fixed_candidate_demo_margin_feasibility_plan.csv"
SOURCE_FORMULA_CSV = "fixed_candidate_demo_margin_feasibility_plan_formula.csv"
SOURCE_REQUIREMENTS_CSV = "fixed_candidate_demo_margin_feasibility_plan_requirements.csv"
SOURCE_WARNINGS_CSV = "fixed_candidate_demo_margin_feasibility_plan_warnings.csv"

OUTPUT_MANIFEST = "fixed_candidate_demo_broker_safe_margin_validation_plan_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_broker_safe_margin_validation_plan_report.md"
OUTPUT_MAIN_CSV = "fixed_candidate_demo_broker_safe_margin_validation_plan.csv"
OUTPUT_ALLOWED_CALLS_CSV = "fixed_candidate_demo_broker_safe_margin_validation_plan_allowed_future_calls.csv"
OUTPUT_REQUIREMENTS_CSV = "fixed_candidate_demo_broker_safe_margin_validation_plan_requirements.csv"
OUTPUT_FUTURE_ARTIFACTS_CSV = "fixed_candidate_demo_broker_safe_margin_validation_plan_future_artifacts.csv"
OUTPUT_WARNINGS_CSV = "fixed_candidate_demo_broker_safe_margin_validation_plan_warnings.csv"

ACCEPTABLE_SOURCE_STATUSES = {
    "margin_feasibility_plan_fixture_only",
    "margin_feasibility_plan_available_no_order",
    "margin_feasibility_hold_requires_broker_margin_validation",
}
MISSING_VOLUME_STATUS = "margin_feasibility_formula_only_missing_volume"

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
    "order_calc_margin_forbidden_here",
    "broker_margin_validation_required_future",
    "margin_estimate_static_artifact_only",
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
    "plan_area",
    "plan_status",
    "artifact_status",
    "source_path",
    "observed_value",
    "expected_value",
    "evidence_label",
    "caveat",
    "warning_code",
    "blocking_warning",
]
ALLOWED_CALL_FIELDNAMES = [
    "run_id",
    "future_call_label",
    "call_name",
    "allowed_future",
    "current_module_called",
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
FUTURE_ARTIFACT_FIELDNAMES = [
    "run_id",
    "future_artifact_name",
    "future_artifact_role",
    "produced_by_future_script",
    "required_before",
    "blocking_if_missing",
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


def read_text(path: Path) -> tuple[str, str]:
    if not path.exists():
        return "", "missing"
    try:
        return path.read_text(encoding="utf-8"), ""
    except OSError as exc:
        return "", str(exc)


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
        "allowed_calls": output_dir / OUTPUT_ALLOWED_CALLS_CSV,
        "requirements": output_dir / OUTPUT_REQUIREMENTS_CSV,
        "future_artifacts": output_dir / OUTPUT_FUTURE_ARTIFACTS_CSV,
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
        and close_float(policy.get("max_margin_usage_warning_ratio"), EXPECTED_MAX_MARGIN_USAGE_WARNING_RATIO)
        and close_float(policy.get("max_margin_usage_ratio"), EXPECTED_MAX_MARGIN_USAGE_RATIO)
        and close_float(policy.get("max_margin_usage_amount"), EXPECTED_MAX_MARGIN_USAGE_AMOUNT)
        and policy.get("spread_unit") == EXPECTED_SPREAD_UNIT
        and close_float(policy.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS)
        and as_bool(safety.get("real_money_allowed")) is False
        and as_bool(safety.get("order_execution_allowed")) is False
        and as_bool(safety.get("order_request_construction_allowed")) is False
        and as_bool(safety.get("order_check_allowed")) is False
        and as_bool(safety.get("order_calc_allowed")) is False
        and as_bool(safety.get("manual_approval_required_before_any_future_demo_order")) is True
    )


def source_boundary_ok(source: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for field in TRUE_SOURCE_BOUNDARY_FIELDS:
        if as_bool(source.get(field)) is not True:
            failures.append(field)
    for field in FALSE_SOURCE_BOUNDARY_FIELDS:
        if as_bool(source.get(field)) is not False:
            failures.append(field)
    return not failures, failures


def source_margin_fields_ok(source: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not close_float(source.get("intended_demo_equity"), EXPECTED_DEMO_EQUITY):
        failures.append("intended_demo_equity")
    if not close_float(source.get("risk_percent"), EXPECTED_RISK_PERCENT):
        failures.append("risk_percent")
    if not close_float(source.get("risk_amount"), EXPECTED_RISK_AMOUNT, tolerance=0.02):
        failures.append("risk_amount")
    if source.get("max_margin_usage_ratio") not in ("", None) and not close_float(
        source.get("max_margin_usage_ratio"), EXPECTED_MAX_MARGIN_USAGE_RATIO
    ):
        failures.append("max_margin_usage_ratio")
    if as_bool(source.get("margin_estimate_static_artifact_only")) is not True:
        failures.append("margin_estimate_static_artifact_only")
    if as_bool(source.get("broker_margin_validation_required_future")) is not True:
        failures.append("broker_margin_validation_required_future")
    margin_status = str(source.get("margin_usage_ratio_status") or "")
    account_margin_status = str(source.get("estimated_margin_account_currency_status") or "")
    if "broker_validated" in margin_status and "not_broker_validated" not in margin_status:
        failures.append("margin_usage_ratio_status")
    if "broker_validated" in account_margin_status and "not_broker_validated" not in account_margin_status:
        failures.append("estimated_margin_account_currency_status")
    approximate_ratio = safe_float(source.get("approximate_margin_usage_ratio"))
    if approximate_ratio is not None and approximate_ratio > EXPECTED_MAX_MARGIN_USAGE_RATIO + 1e-6:
        failures.append("approximate_margin_usage_ratio_above_policy_cap")
    return not failures, failures


def margin_warning_active(source: dict[str, Any], source_warnings: list[dict[str, str]]) -> bool:
    if any("margin_usage_above_warning_threshold" in str(row.get("warning_code", "")) for row in source_warnings):
        return True
    approximate_ratio = safe_float(source.get("approximate_margin_usage_ratio"))
    if approximate_ratio is None:
        return False
    return EXPECTED_MAX_MARGIN_USAGE_WARNING_RATIO < approximate_ratio <= EXPECTED_MAX_MARGIN_USAGE_RATIO


def recommended_next_step(plan_status: str) -> str:
    if plan_status == "broker_safe_margin_validation_plan_fixture_only":
        return "wait_for_live_shadow_signal_or_continue_no_order_monitoring"
    if plan_status in {
        "broker_safe_margin_validation_plan_available",
        "broker_safe_margin_validation_plan_required_due_to_margin_warning",
    }:
        return "implement_check_fixed_candidate_demo_broker_safe_margin_validation_when_explicitly_authorized"
    if plan_status == "hold_missing_volume_for_margin_validation_plan":
        return "rerun_risk_volume_shadow_plan_with_policy_equity"
    return "fix_broker_safe_margin_validation_plan_inputs"


def determine_plan_status(
    *,
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_error: str,
    policy: dict[str, Any],
    policy_error: str,
    source: dict[str, Any],
    source_error: str,
    source_report_error: str,
    source_main_error: str,
    source_formula_error: str,
    source_requirements_error: str,
    source_warnings_error: str,
    boundary_safe: bool,
    field_safe: bool,
    policy_safe: bool,
    source_warnings: list[dict[str, str]],
    warnings: list[dict[str, Any]],
) -> str:
    source_dir = Path(args.margin_feasibility_plan_dir)
    missing = [
        ("canonical_registry_missing", registry_error, args.canonical_registry),
        ("demo_execution_policy_missing", policy_error, args.demo_execution_policy),
        ("margin_feasibility_manifest_missing", source_error, source_dir / SOURCE_MANIFEST),
        ("margin_feasibility_report_missing", source_report_error, source_dir / SOURCE_REPORT),
        ("margin_feasibility_main_csv_missing", source_main_error, source_dir / SOURCE_MAIN_CSV),
        ("margin_feasibility_formula_csv_missing", source_formula_error, source_dir / SOURCE_FORMULA_CSV),
        ("margin_feasibility_requirements_csv_missing", source_requirements_error, source_dir / SOURCE_REQUIREMENTS_CSV),
        ("margin_feasibility_warnings_csv_missing", source_warnings_error, source_dir / SOURCE_WARNINGS_CSV),
    ]
    missing_errors = [item for item in missing if item[1] == "missing"]
    if missing_errors:
        for code, _error, path in missing_errors:
            add_warning(warnings, args=args, warning_code=code, message="Required input artifact is missing.", source=path, blocking_warning=True)
        return "blocked_missing_required_artifact"
    unreadable_errors = [item for item in missing if item[1]]
    if unreadable_errors:
        for code, error, path in unreadable_errors:
            add_warning(
                warnings,
                args=args,
                warning_code=code.replace("missing", "unreadable"),
                message=f"Required input artifact is unreadable: {error}",
                source=path,
                blocking_warning=True,
            )
        return "blocked_unreadable_input"
    if not canonical_registry_valid(registry):
        add_warning(
            warnings,
            args=args,
            warning_code="canonical_registry_boundary_mismatch",
            message="Canonical registry does not match fixed-candidate spread15 boundaries.",
            source=args.canonical_registry,
            blocking_warning=True,
        )
        return "blocked_by_config_boundary"
    if not policy_safe:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_execution_policy_boundary_mismatch",
            message="Demo execution policy does not match equity1000/risk0.5/margin70 no-order boundaries.",
            source=args.demo_execution_policy,
            blocking_warning=True,
        )
        return "blocked_by_demo_execution_policy"
    source_status = str(source.get("plan_status") or "")
    if source_status.startswith("blocked_"):
        add_warning(
            warnings,
            args=args,
            warning_code="margin_feasibility_status_blocked",
            message=f"Margin feasibility plan status is blocked: {source_status}",
            source=source_dir / SOURCE_MANIFEST,
            blocking_warning=True,
        )
        return "blocked_by_margin_feasibility_status"
    if source_status == MISSING_VOLUME_STATUS:
        return "hold_missing_volume_for_margin_validation_plan"
    if source_status not in ACCEPTABLE_SOURCE_STATUSES:
        add_warning(
            warnings,
            args=args,
            warning_code="margin_feasibility_status_not_acceptable",
            message=f"Margin feasibility plan status is not acceptable: {source_status}",
            source=source_dir / SOURCE_MANIFEST,
            blocking_warning=True,
        )
        return "blocked_by_margin_feasibility_status"
    if not boundary_safe:
        add_warning(
            warnings,
            args=args,
            warning_code="no_order_boundary_violation",
            message="Margin feasibility no-order/no-request boundary is missing or unsafe.",
            source=source_dir / SOURCE_MANIFEST,
            blocking_warning=True,
        )
        return "blocked_by_no_order_boundary"
    if not field_safe:
        add_warning(
            warnings,
            args=args,
            warning_code="source_margin_fields_invalid",
            message="Margin feasibility source fields are inconsistent with policy or static-artifact-only requirements.",
            source=source_dir / SOURCE_MANIFEST,
            blocking_warning=True,
        )
        return "blocked_by_source_margin_fields"
    if margin_warning_active(source, source_warnings):
        add_warning(
            warnings,
            args=args,
            warning_code="margin_usage_above_warning_threshold_requires_future_broker_safe_validation",
            message="Static margin approximation is above the 50% warning threshold and below the 70% cap; future broker-safe margin validation remains required.",
            source=source_dir / SOURCE_MANIFEST,
            blocking_warning=False,
            severity="warning",
        )
    if source_status == "margin_feasibility_hold_requires_broker_margin_validation":
        return "broker_safe_margin_validation_plan_required_due_to_margin_warning"
    if source_status == "margin_feasibility_plan_fixture_only":
        return "broker_safe_margin_validation_plan_fixture_only"
    return "broker_safe_margin_validation_plan_available"


def source_nature_for(source: dict[str, Any], plan_status: str) -> str:
    if plan_status == "broker_safe_margin_validation_plan_fixture_only":
        return "synthetic_fixture"
    if plan_status in {
        "broker_safe_margin_validation_plan_available",
        "broker_safe_margin_validation_plan_required_due_to_margin_warning",
    }:
        return str(source.get("source_nature") or "live_data_shadow_signal")
    return str(source.get("source_nature") or "unclear")


def context(args: argparse.Namespace, source: dict[str, Any], registry: dict[str, Any], policy: dict[str, Any], plan_status: str, source_nature: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "plan_status": plan_status,
        "source_nature": source_nature,
        "source_margin_feasibility_status": source.get("plan_status", ""),
        "candidate_id": registry.get("candidate_id", EXPECTED_CANDIDATE_ID),
        "symbol": registry.get("symbol", EXPECTED_SYMBOL),
        "timeframe": registry.get("timeframe", EXPECTED_TIMEFRAME),
        "direction": registry.get("direction", EXPECTED_DIRECTION),
        "intended_demo_equity": safe_float(policy.get("intended_demo_equity")),
        "account_currency": policy.get("account_currency", EXPECTED_ACCOUNT_CURRENCY),
        "risk_percent_max": safe_float(policy.get("risk_percent_max")),
        "risk_amount_max": safe_float(policy.get("risk_amount_max")),
        "max_margin_usage_warning_ratio": safe_float(policy.get("max_margin_usage_warning_ratio")),
        "max_margin_usage_ratio": safe_float(policy.get("max_margin_usage_ratio")),
        "max_margin_usage_amount": safe_float(policy.get("max_margin_usage_amount")),
        "approximate_margin_usage_ratio": safe_float(source.get("approximate_margin_usage_ratio")),
        "estimated_margin_quote": safe_float(source.get("estimated_margin_quote")),
        "future_broker_safe_margin_validation_script": str(args.future_broker_safe_margin_validation_script),
        "plan_actionable": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "demo_broker_approval_performed": False,
        "recommended_next_step": recommended_next_step(plan_status),
    }


def main_rows(ctx: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    source_manifest = Path(args.margin_feasibility_plan_dir) / SOURCE_MANIFEST
    items = [
        ("source_margin_feasibility_status", ctx["source_margin_feasibility_status"], "acceptable margin feasibility status", "source_margin_feasibility_available", "source artifact controls scope"),
        ("source_margin_warning", ctx["approximate_margin_usage_ratio"], "warning at >0.50 and cap at <=0.70", "margin_warning_reviewed", "future broker-safe validation remains required"),
        ("execution_policy_loaded", args.demo_execution_policy, "config/fixed_candidate_demo_execution_policy.json", "execution_policy_available", "policy is no-order"),
        ("margin70_policy_confirmed", ctx["max_margin_usage_ratio"], "0.70", "margin70_policy_confirmed", "policy cap is not demo approval"),
        ("warning50_policy_confirmed", ctx["max_margin_usage_warning_ratio"], "0.50", "warning50_policy_confirmed", "warning threshold is non-blocking context"),
        ("broker_safe_validation_required_future", True, True, "broker_safe_validation_required_future", "future module only"),
        ("order_calc_margin_future_allowed_only_in_separate_module", True, "separate explicitly authorized future module only", "future_order_calc_margin_scoped", "not allowed here"),
        ("order_check_forbidden", False, False, "order_check_forbidden", "forbidden for broker-safe margin validation path"),
        ("order_send_forbidden", False, False, "order_send_forbidden", "forbidden for broker-safe margin validation path"),
        ("order_calc_profit_forbidden", False, False, "order_calc_profit_forbidden", "forbidden for broker-safe margin validation path"),
        ("positions_orders_history_forbidden", False, False, "positions_orders_history_forbidden", "forbidden for broker-safe margin validation path"),
        ("demo_account_reconfirmation_required", "future", "demo account must be re-confirmed", "demo_reconfirmation_required", "future read-only check"),
        ("equity_free_margin_recheck_required", "future", "equity/free margin captured read-only", "equity_free_margin_recheck_required", "future read-only check"),
        ("symbol_contract_recheck_required", "future", "GBPUSD contract fields re-read", "symbol_contract_recheck_required", "future read-only check"),
        ("spread_recheck_required", "future", "spread <= 15 broker_points", "spread_recheck_required", "future read-only check"),
        ("live_data_signal_required", ctx["source_nature"], "live_data_shadow_signal", "live_data_signal_required", "fixture cannot advance"),
        ("fixture_not_actionable", ctx["source_nature"], "synthetic_fixture is non-actionable", "fixture_non_actionable", "wait for live-data signal"),
        ("manual_approval_required_future", True, True, "manual_approval_required_future", "manual gate remains required"),
        ("no_order_boundary_confirmed", True, True, "no_order_boundary_confirmed", "no current order path"),
    ]
    return [
        {
            "run_id": ctx["run_id"],
            "plan_area": area,
            "plan_status": ctx["plan_status"],
            "artifact_status": "planned",
            "source_path": source_manifest if area.startswith("source") else args.demo_execution_policy,
            "observed_value": observed,
            "expected_value": expected,
            "evidence_label": evidence,
            "caveat": caveat,
            "warning_code": "",
            "blocking_warning": False,
        }
        for area, observed, expected, evidence, caveat in items
    ]


def allowed_future_call_rows(run_id: str) -> list[dict[str, Any]]:
    rows = [
        ("future_initialize_mt5_read_only_context", "mt5_initialize_read_only_context", True, "future explicitly authorized module only"),
        ("future_terminal_info_read", "terminal_info", True, "read-only future evidence only"),
        ("future_account_info_read", "account_info", True, "read-only future evidence only"),
        ("future_symbol_info_read", "symbol_info", True, "read-only future evidence only"),
        ("future_symbol_tick_read", "symbol_info_tick", True, "read-only future evidence only"),
        ("future_order_calc_margin_for_margin_estimate_only", "order_calc_margin", True, "only in a separate future broker-safe margin validation module, never in artifact-only modules"),
        ("order_send", "order_send", False, "forbidden for broker-safe margin validation path"),
        ("order_check", "order_check", False, "forbidden for broker-safe margin validation path"),
        ("order_calc_profit", "order_calc_profit", False, "forbidden for broker-safe margin validation path"),
        ("positions_get", "positions_get", False, "forbidden for broker-safe margin validation path"),
        ("orders_get", "orders_get", False, "forbidden for broker-safe margin validation path"),
        ("history_orders_get", "history_orders_get", False, "forbidden for broker-safe margin validation path"),
        ("history_deals_get", "history_deals_get", False, "forbidden for broker-safe margin validation path"),
    ]
    return [
        {
            "run_id": run_id,
            "future_call_label": label,
            "call_name": name,
            "allowed_future": allowed,
            "current_module_called": False,
            "caveat": caveat,
        }
        for label, name, allowed, caveat in rows
    ]


def requirement_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    future_module = str(args.future_broker_safe_margin_validation_script)
    rows = [
        ("authorization", "explicit_user_authorization_required", "future broker-safe margin validation", "user explicitly authorizes read-only margin validation module", True, "manual gate"),
        ("terminal", "mt5_open_on_demo_account", "future broker-safe margin validation", "MT5 terminal is open on demo account", True, "future read-only check"),
        ("account", "account_mode_reconfirmed_demo", "future broker-safe margin validation", "account mode is demo", True, "redacted future artifact"),
        ("symbol", "symbol_reconfirmed_gbpusd", "future broker-safe margin validation", "symbol is GBPUSD", True, "future read-only check"),
        ("account", "account_currency_confirmed_eur", "future broker-safe margin validation", "account currency is EUR", True, "redacted future artifact"),
        ("account", "equity_free_margin_read_only_captured", "future broker-safe margin validation", "current equity and free margin captured read-only", True, "redacted future artifact"),
        ("spread", "current_spread_within_15_broker_points", "future broker-safe margin validation", "current spread <= 15 broker_points", True, "future read-only check"),
        ("symbol", "contract_fields_re_read", "future broker-safe margin validation", "contract size, point, tick, stop, freeze, and volume fields captured", True, "future read-only check"),
        ("source", "live_data_signal_not_fixture", "future broker-safe margin validation", "source signal is live-data shadow evidence, not fixture", True, "source artifact check"),
        ("volume", "volume_from_policy_risk_volume_artifact", "future broker-safe margin validation", "volume comes from policy risk/volume artifact", True, "source artifact check"),
        ("boundary", "no_broker_structure_constructed", "future broker-safe margin validation", "no broker-ready structure is constructed", True, "no-order evidence"),
        ("margin", "order_calc_margin_estimator_only", "future broker-safe margin validation", "order_calc_margin may be used only as a margin estimator", True, "future explicit authorization"),
        ("boundary", "order_check_forbidden", "future broker-safe margin validation", "order_check remains forbidden", True, "no-order evidence"),
        ("boundary", "order_send_forbidden", "future broker-safe margin validation", "order_send remains forbidden", True, "no-order evidence"),
        ("boundary", "order_calc_profit_forbidden", "future broker-safe margin validation", "order_calc_profit remains forbidden", True, "no-order evidence"),
        ("boundary", "no_positions_orders_history_queries", "future broker-safe margin validation", "positions, orders, and history queries remain forbidden", True, "no-order evidence"),
        ("manual", "manual_approval_required_before_later_phase", "future broker-safe margin validation", "manual approval remains required before any later phase", True, "manual gate"),
        ("security", "account_sensitive_fields_redacted", "future broker-safe margin validation", "account-sensitive fields are redacted", True, "redacted future artifact"),
        ("audit", "no_order_evidence_written", "future broker-safe margin validation", "all no-order evidence is written", True, "future artifact"),
    ]
    return [
        {
            "run_id": args.run_id,
            "requirement_area": area,
            "requirement_name": name,
            "required_before": required_before,
            "expected_condition": expected,
            "blocking_if_failed": blocking,
            "future_module": future_module,
            "caveat": caveat,
        }
        for area, name, required_before, expected, blocking, caveat in rows
    ]


def future_artifact_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    future_module = str(args.future_broker_safe_margin_validation_script)
    rows = [
        ("fixed_candidate_demo_broker_safe_margin_validation_manifest.json", "future manifest", "before any later phase", True, "status and boundary flags"),
        ("fixed_candidate_demo_broker_safe_margin_validation_report.md", "future report", "before any later phase", True, "human-readable caveats"),
        ("fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json", "future margin snapshot", "before any later phase", True, "redacted margin evidence"),
        ("fixed_candidate_demo_broker_safe_margin_validation_checklist.csv", "future checklist", "before any later phase", True, "requirement results"),
        ("fixed_candidate_demo_broker_safe_margin_validation_warnings.csv", "future warnings", "before any later phase", True, "blocking and non-blocking warnings"),
        ("fixed_candidate_demo_broker_safe_margin_validation_no_order_evidence.csv", "future no-order evidence", "before any later phase", True, "no-order boundary evidence"),
    ]
    return [
        {
            "run_id": args.run_id,
            "future_artifact_name": name,
            "future_artifact_role": role,
            "produced_by_future_script": future_module,
            "required_before": required_before,
            "blocking_if_missing": blocking,
            "caveat": caveat,
        }
        for name, role, required_before, blocking, caveat in rows
    ]


def manifest_data(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    ctx: dict[str, Any],
    allowed_calls: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    future_artifacts: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "canonical_registry_path": str(args.canonical_registry),
        "demo_execution_policy_path": str(args.demo_execution_policy),
        "margin_feasibility_plan_dir": str(args.margin_feasibility_plan_dir),
        "future_broker_safe_margin_validation_script": ctx["future_broker_safe_margin_validation_script"],
        "plan_status": ctx["plan_status"],
        "source_nature": ctx["source_nature"],
        "source_margin_feasibility_status": ctx["source_margin_feasibility_status"],
        "candidate_id": ctx["candidate_id"],
        "symbol": ctx["symbol"],
        "timeframe": ctx["timeframe"],
        "direction": ctx["direction"],
        "intended_demo_equity": ctx["intended_demo_equity"],
        "account_currency": ctx["account_currency"],
        "risk_percent_max": ctx["risk_percent_max"],
        "risk_amount_max": ctx["risk_amount_max"],
        "max_margin_usage_warning_ratio": ctx["max_margin_usage_warning_ratio"],
        "max_margin_usage_ratio": ctx["max_margin_usage_ratio"],
        "max_margin_usage_amount": ctx["max_margin_usage_amount"],
        "approximate_margin_usage_ratio": ctx["approximate_margin_usage_ratio"],
        "estimated_margin_quote": ctx["estimated_margin_quote"],
        "future_order_calc_margin_allowed_only_in_separate_module": True,
        "future_order_send_allowed": False,
        "future_order_check_allowed": False,
        "future_order_calc_profit_allowed": False,
        "future_positions_orders_history_allowed": False,
        "plan_actionable": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "demo_broker_approval_performed": False,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_db_query_performed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_trading_decision_performed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "allowed_future_call_row_count": len(allowed_calls),
        "requirement_row_count": len(requirements),
        "future_artifact_row_count": len(future_artifacts),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "recommended_next_step": ctx["recommended_next_step"],
    }


def write_report(path: Path, *, ctx: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Broker-Safe Margin Validation Plan",
        "",
        "Artifact-only broker-safe margin validation planning.",
        "The current module does not import or connect to MT5.",
        "The current module does not query broker, API, account, or symbol state.",
        "The current module does not call order_calc_margin.",
        "The current module does not call order_check, order_send, or order_calc_profit.",
        "The current module does not construct a broker-ready structure or broker payload.",
        "The current module does not query or mutate a database.",
        "The current module adds no scheduler, loop, daemon, or background behavior.",
        "Future order_calc_margin may be allowed only in a separate explicitly authorized module for margin estimation.",
        "Even future broker-safe margin validation must not send, check, or profit-calculate orders.",
        "Fixture input is non-actionable.",
        "This is not demo broker approval and not a trading decision.",
        "",
        "## Source Summary",
        "",
        f"- plan_status: `{ctx['plan_status']}`",
        f"- source_nature: `{ctx['source_nature']}`",
        f"- source_margin_feasibility_status: `{ctx['source_margin_feasibility_status']}`",
        f"- intended_demo_equity: `{ctx['intended_demo_equity']}`",
        f"- risk_percent_max: `{ctx['risk_percent_max']}`",
        f"- risk_amount_max: `{ctx['risk_amount_max']}`",
        f"- max_margin_usage_warning_ratio: `{ctx['max_margin_usage_warning_ratio']}`",
        f"- max_margin_usage_ratio: `{ctx['max_margin_usage_ratio']}`",
        f"- estimated_margin_quote: `{ctx['estimated_margin_quote']}`",
        f"- approximate_margin_usage_ratio: `{ctx['approximate_margin_usage_ratio']}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{ctx['recommended_next_step']}`",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        lines.extend(f"- {row['warning_code']}: {row['message']}" for row in warnings)
    else:
        lines.append("- none")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = default_output_dir(args)
    paths = output_paths(output_dir)
    ensure_outputs_writable(paths, bool(args.overwrite))

    source_dir = Path(args.margin_feasibility_plan_dir)
    registry, registry_error = read_json(Path(args.canonical_registry))
    policy, policy_error = read_json(Path(args.demo_execution_policy))
    source, source_error = read_json(source_dir / SOURCE_MANIFEST)
    _source_report_text, source_report_error = read_text(source_dir / SOURCE_REPORT)
    _source_main_rows, source_main_error = read_csv_rows(source_dir / SOURCE_MAIN_CSV)
    _source_formula_rows, source_formula_error = read_csv_rows(source_dir / SOURCE_FORMULA_CSV)
    _source_requirement_rows, source_requirements_error = read_csv_rows(source_dir / SOURCE_REQUIREMENTS_CSV)
    source_warning_rows, source_warnings_error = read_csv_rows(source_dir / SOURCE_WARNINGS_CSV)
    warnings = preserve_source_warnings(args, source_warning_rows, source_dir / SOURCE_WARNINGS_CSV) if not source_warnings_error else []

    boundary_safe, boundary_failures = source_boundary_ok(source)
    field_safe, field_failures = source_margin_fields_ok(source)
    policy_safe = execution_policy_valid(policy)
    plan_status = determine_plan_status(
        args=args,
        registry=registry,
        registry_error=registry_error,
        policy=policy,
        policy_error=policy_error,
        source=source,
        source_error=source_error,
        source_report_error=source_report_error,
        source_main_error=source_main_error,
        source_formula_error=source_formula_error,
        source_requirements_error=source_requirements_error,
        source_warnings_error=source_warnings_error,
        boundary_safe=boundary_safe,
        field_safe=field_safe,
        policy_safe=policy_safe,
        source_warnings=source_warning_rows,
        warnings=warnings,
    )
    if plan_status == "blocked_by_no_order_boundary" and boundary_failures:
        add_warning(
            warnings,
            args=args,
            warning_code="no_order_boundary_failed_fields",
            message=f"Failed fields: {boundary_failures}",
            source=source_dir / SOURCE_MANIFEST,
            blocking_warning=True,
        )
    if plan_status == "blocked_by_source_margin_fields" and field_failures:
        add_warning(
            warnings,
            args=args,
            warning_code="source_margin_failed_fields",
            message=f"Failed fields: {field_failures}",
            source=source_dir / SOURCE_MANIFEST,
            blocking_warning=True,
        )
    source_nature = source_nature_for(source, plan_status)
    ctx = context(args, source, registry, policy, plan_status, source_nature)
    rows_main = main_rows(ctx, args)
    rows_calls = allowed_future_call_rows(args.run_id)
    rows_requirements = requirement_rows(args)
    rows_future_artifacts = future_artifact_rows(args)

    write_csv(paths["main"], rows_main, MAIN_FIELDNAMES)
    write_csv(paths["allowed_calls"], rows_calls, ALLOWED_CALL_FIELDNAMES)
    write_csv(paths["requirements"], rows_requirements, REQUIREMENT_FIELDNAMES)
    write_csv(paths["future_artifacts"], rows_future_artifacts, FUTURE_ARTIFACT_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_json(
        paths["manifest"],
        manifest_data(
            args=args,
            output_dir=output_dir,
            ctx=ctx,
            allowed_calls=rows_calls,
            requirements=rows_requirements,
            future_artifacts=rows_future_artifacts,
            warnings=warnings,
        ),
    )
    write_report(paths["report"], ctx=ctx, warnings=warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only fixed-candidate broker-safe margin validation plan.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--margin-feasibility-plan-dir", type=Path, default=DEFAULT_MARGIN_FEASIBILITY_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_EXECUTION_POLICY)
    parser.add_argument("--future-broker-safe-margin-validation-script", type=Path, default=DEFAULT_FUTURE_SCRIPT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        build_outputs(args)
    except Exception as exc:
        print(f"Fixed-candidate broker-safe margin validation plan failed: {exc}")
        return 1
    print("Fixed-candidate broker-safe margin validation plan complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
