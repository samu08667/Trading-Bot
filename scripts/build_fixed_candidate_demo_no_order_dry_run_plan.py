"""Build an artifact-only demo no-order dry-run plan for the fixed candidate.

The plan consumes existing demo environment evidence and describes a future
no-order dry-run script. It does not connect to MT5 or broker/API services,
query account or symbol state, construct order requests, execute orders, query
or mutate the database, refresh features, rerun replay/reviews/paper workflow,
optimize parameters, or make candidate-quality or trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_no_order_dry_run_plan"
DEFAULT_DEMO_ENVIRONMENT_CHECK_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_environment_check"
    / "gbpusd_short_h10_1_5_off_hours_demo_environment_check_spread15_v1"
)
DEFAULT_DEMO_ENVIRONMENT_CHECK_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_environment_check_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_environment_check_plan_spread15_v1"
)
DEFAULT_DEMO_READINESS_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_readiness_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_readiness_plan_spread15_v1"
)
DEFAULT_DEMO_STRATEGY_SPEC_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_strategy_spec"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v5_spread15"
)
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR / "config" / "paper_demo" / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)
DEFAULT_TERCILE_THRESHOLDS_JSON = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_numeric_tercile_thresholds"
    / "gbpusd_short_h10_1_5_off_hours_numeric_tercile_thresholds_v1"
    / "fixed_candidate_numeric_tercile_thresholds.json"
)
DEFAULT_FUTURE_NO_ORDER_DRY_RUN_SCRIPT = BASE_DIR / "scripts" / "run_fixed_candidate_demo_no_order_dry_run.py"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_no_order_dry_run_plan"

ENV_MANIFEST = "fixed_candidate_demo_environment_check_manifest.json"
ENV_REPORT = "fixed_candidate_demo_environment_check_report.md"
ENV_CHECKLIST = "fixed_candidate_demo_environment_check_checklist.csv"
ENV_REQUIREMENTS = "fixed_candidate_demo_environment_check_requirements.csv"
ENV_WARNINGS = "fixed_candidate_demo_environment_check_warnings.csv"
ENV_ACCOUNT_SNAPSHOT = "fixed_candidate_demo_environment_account_snapshot_redacted.json"
ENV_SYMBOL_SNAPSHOT = "fixed_candidate_demo_environment_symbol_contract_snapshot.json"
ENV_NO_ORDER = "fixed_candidate_demo_environment_dry_run_no_order_check.csv"

ENV_PLAN_MANIFEST = "fixed_candidate_demo_environment_check_plan_manifest.json"
ENV_PLAN_REQUIREMENTS = "fixed_candidate_demo_environment_check_plan_requirements.csv"
ENV_PLAN_FUTURE_ARTIFACTS = "fixed_candidate_demo_environment_check_plan_future_artifacts.csv"
ENV_PLAN_WARNINGS = "fixed_candidate_demo_environment_check_plan_warnings.csv"

READINESS_MANIFEST = "fixed_candidate_demo_readiness_plan_manifest.json"
READINESS_CHECKLIST = "fixed_candidate_demo_readiness_plan_checklist.csv"
READINESS_WARNINGS = "fixed_candidate_demo_readiness_plan_warnings.csv"

SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"
SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"

OUTPUT_PLAN = "fixed_candidate_demo_no_order_dry_run_plan.csv"
OUTPUT_REQUIREMENTS = "fixed_candidate_demo_no_order_dry_run_plan_requirements.csv"
OUTPUT_FUTURE_ARTIFACTS = "fixed_candidate_demo_no_order_dry_run_plan_future_artifacts.csv"
OUTPUT_REPORT = "fixed_candidate_demo_no_order_dry_run_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_demo_no_order_dry_run_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_demo_no_order_dry_run_plan_manifest.json"

REQUIRED_KILL_SWITCH_CONDITIONS = {
    "required_data_missing",
    "required_features_missing",
    "spread_abnormal_or_not_configured",
    "atr_calculation_failed",
    "timeframe_mismatch",
    "session_mismatch",
    "existing_paper_demo_trade_open",
}
NO_ORDER_FLAGS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_db_mutation_performed",
    "no_trading_decision_performed",
    "no_demo_broker_approval_performed",
)

PLAN_FIELDNAMES = [
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

REQUIREMENT_FIELDNAMES = [
    "run_id",
    "requirement_area",
    "requirement_name",
    "required_fields",
    "expected_condition",
    "blocking_if_failed",
    "future_artifact",
    "future_script",
    "check_mode",
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


def extract_first_number(text: Any) -> float | None:
    if not isinstance(text, str):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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
        "plan": output_dir / OUTPUT_PLAN,
        "requirements": output_dir / OUTPUT_REQUIREMENTS,
        "future_artifacts": output_dir / OUTPUT_FUTURE_ARTIFACTS,
        "report": output_dir / OUTPUT_REPORT,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "manifest": output_dir / OUTPUT_MANIFEST,
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


def load_required_json(args: argparse.Namespace, warnings: list[dict[str, Any]], path: Path, code: str) -> dict[str, Any]:
    data, error = read_json(path)
    if not path.exists():
        add_warning(warnings, args=args, warning_code=f"{code}_missing", message="Required JSON artifact is missing.", source=path, blocking_warning=True)
    elif error:
        add_warning(warnings, args=args, warning_code=f"{code}_unreadable", message=f"Required JSON artifact is unreadable: {error}", source=path, blocking_warning=True)
    return data


def load_required_csv(args: argparse.Namespace, warnings: list[dict[str, Any]], path: Path, code: str) -> list[dict[str, str]]:
    rows, error = read_csv_rows(path)
    if not path.exists():
        add_warning(warnings, args=args, warning_code=f"{code}_missing", message="Required CSV artifact is missing.", source=path, blocking_warning=True)
    elif error:
        add_warning(warnings, args=args, warning_code=f"{code}_unreadable", message=f"Required CSV artifact is unreadable: {error}", source=path, blocking_warning=True)
    return rows


def preserve_source_warnings(args: argparse.Namespace, warnings: list[dict[str, Any]], rows: list[dict[str, str]], source_name: str) -> None:
    for row in rows:
        add_warning(
            warnings,
            args=args,
            warning_code=row.get("warning_code", f"{source_name}_source_warning"),
            message=row.get("message", "Source warning preserved."),
            source=row.get("source", source_name),
            blocking_warning=str(row.get("blocking_warning", "")).lower() == "true",
            severity=row.get("severity") or "warning",
        )


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
    return {
        "paper_only": config.get("paper_only") is True,
        "broker_connection_allowed_false": config.get("broker_connection_allowed") is False,
        "order_execution_allowed_false": config.get("order_execution_allowed") is False,
        "real_money_allowed_false": config.get("real_money_allowed") is False,
        "max_open_positions": max_open_positions,
        "max_open_positions_is_one": max_open_positions == 1,
        "max_risk_percent": risk_percent,
        "max_risk_per_trade_is_one_percent": risk_percent == 1,
        "spread_unit": spread_unit,
        "max_spread_points": max_spread_points,
        "spread_policy_matches_canonical": spread_unit == "broker_points" and max_spread_points == 15.0,
        "kill_switch_conditions_present": REQUIRED_KILL_SWITCH_CONDITIONS.issubset(set(str(item) for item in kill_conditions)),
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


def no_order_boundary_confirmed(env_manifest: dict[str, Any]) -> bool:
    return all(env_manifest.get(flag) is True for flag in NO_ORDER_FLAGS)


def account_snapshot_valid(account: dict[str, Any]) -> bool:
    return (
        account.get("is_demo_account") is True
        and account.get("account_trade_mode_label") == "demo"
        and account.get("redaction_applied") is True
    )


def symbol_snapshot_valid(symbol_snapshot: dict[str, Any], expected_symbol: str = "GBPUSD") -> bool:
    numeric_positive = all(
        (safe_float(symbol_snapshot.get(field)) is not None and safe_float(symbol_snapshot.get(field)) > 0)
        for field in ("point", "volume_min", "volume_step")
    )
    return (
        symbol_snapshot.get("symbol") == expected_symbol
        and symbol_snapshot.get("visible") is True
        and symbol_snapshot.get("select") is True
        and symbol_snapshot.get("digits") == 5
        and numeric_positive
        and "trade_stops_level" in symbol_snapshot
        and "trade_freeze_level" in symbol_snapshot
    )


def spread_policy_valid(env_manifest: dict[str, Any], symbol_snapshot: dict[str, Any], boundaries: dict[str, Any]) -> bool:
    spread = safe_float(env_manifest.get("spread_current_points"))
    if spread is None:
        spread = safe_float(symbol_snapshot.get("spread_current_points"))
    max_spread = safe_float(env_manifest.get("max_spread_points"))
    if max_spread is None:
        max_spread = safe_float(symbol_snapshot.get("max_spread_points"))
    spread_unit = env_manifest.get("spread_unit") or symbol_snapshot.get("spread_unit")
    within_gate = env_manifest.get("spread_within_config_gate")
    canonical = env_manifest.get("spread_policy_matches_canonical")
    return (
        spread_unit == "broker_points"
        and max_spread == 15.0
        and spread is not None
        and spread <= max_spread
        and within_gate is True
        and canonical is True
        and boundaries["spread_policy_matches_canonical"]
    )


def threshold_json_valid(thresholds: dict[str, Any]) -> bool:
    features = thresholds.get("features")
    return (
        bool(thresholds.get("schema_version"))
        and thresholds.get("candidate_id") == "gbpusd_short_h10_1_5_off_hours"
        and isinstance(features, dict)
        and "close_to_ma_fast_atr_20" in features
        and "tick_volume_percentile_100" in features
    )


def source_artifact_paths(args: argparse.Namespace) -> dict[str, Path]:
    env = Path(args.demo_environment_check_dir)
    env_plan = Path(args.demo_environment_check_plan_dir)
    readiness = Path(args.demo_readiness_plan_dir)
    spec = Path(args.demo_strategy_spec_dir)
    return {
        "env_manifest": env / ENV_MANIFEST,
        "env_report": env / ENV_REPORT,
        "env_checklist": env / ENV_CHECKLIST,
        "env_requirements": env / ENV_REQUIREMENTS,
        "env_warnings": env / ENV_WARNINGS,
        "account_snapshot": env / ENV_ACCOUNT_SNAPSHOT,
        "symbol_snapshot": env / ENV_SYMBOL_SNAPSHOT,
        "env_no_order": env / ENV_NO_ORDER,
        "env_plan_manifest": env_plan / ENV_PLAN_MANIFEST,
        "env_plan_requirements": env_plan / ENV_PLAN_REQUIREMENTS,
        "env_plan_future_artifacts": env_plan / ENV_PLAN_FUTURE_ARTIFACTS,
        "env_plan_warnings": env_plan / ENV_PLAN_WARNINGS,
        "readiness_manifest": readiness / READINESS_MANIFEST,
        "readiness_checklist": readiness / READINESS_CHECKLIST,
        "readiness_warnings": readiness / READINESS_WARNINGS,
        "spec_manifest": spec / SPEC_MANIFEST,
        "spec_csv": spec / SPEC_CSV,
        "spec_warnings": spec / SPEC_WARNINGS,
        "config": Path(args.demo_strategy_config),
        "thresholds": Path(args.tercile_thresholds_json),
    }


def load_sources(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    paths = source_artifact_paths(args)
    sources = {
        "paths": paths,
        "env_manifest": load_required_json(args, warnings, paths["env_manifest"], "environment_check_manifest"),
        "account_snapshot": load_required_json(args, warnings, paths["account_snapshot"], "account_snapshot"),
        "symbol_snapshot": load_required_json(args, warnings, paths["symbol_snapshot"], "symbol_contract_snapshot"),
        "env_plan_manifest": load_required_json(args, warnings, paths["env_plan_manifest"], "environment_check_plan_manifest"),
        "readiness_manifest": load_required_json(args, warnings, paths["readiness_manifest"], "demo_readiness_manifest"),
        "spec_manifest": load_required_json(args, warnings, paths["spec_manifest"], "demo_strategy_spec_manifest"),
        "config": load_required_json(args, warnings, paths["config"], "demo_strategy_config"),
        "thresholds": load_required_json(args, warnings, paths["thresholds"], "tercile_thresholds_json"),
        "env_checklist": load_required_csv(args, warnings, paths["env_checklist"], "environment_check_checklist"),
        "env_requirements": load_required_csv(args, warnings, paths["env_requirements"], "environment_check_requirements"),
        "env_warnings": load_required_csv(args, warnings, paths["env_warnings"], "environment_check_warnings"),
        "env_no_order": load_required_csv(args, warnings, paths["env_no_order"], "environment_check_no_order_evidence"),
        "env_plan_requirements": load_required_csv(args, warnings, paths["env_plan_requirements"], "environment_check_plan_requirements"),
        "env_plan_future_artifacts": load_required_csv(args, warnings, paths["env_plan_future_artifacts"], "environment_check_plan_future_artifacts"),
        "env_plan_warnings": load_required_csv(args, warnings, paths["env_plan_warnings"], "environment_check_plan_warnings"),
        "readiness_checklist": load_required_csv(args, warnings, paths["readiness_checklist"], "demo_readiness_checklist"),
        "readiness_warnings": load_required_csv(args, warnings, paths["readiness_warnings"], "demo_readiness_warnings"),
        "spec_csv": load_required_csv(args, warnings, paths["spec_csv"], "demo_strategy_spec_csv"),
        "spec_warnings": load_required_csv(args, warnings, paths["spec_warnings"], "demo_strategy_spec_warnings"),
        "env_report": read_text(paths["env_report"]),
    }
    for key in ("env_warnings", "env_plan_warnings", "readiness_warnings", "spec_warnings"):
        preserve_source_warnings(args, warnings, sources[key], key)
    return sources


def missing_source_artifact_count(paths: dict[str, Path]) -> int:
    return sum(1 for path in paths.values() if not path.exists())


def unreadable_source_artifact_count(warnings: list[dict[str, Any]]) -> int:
    return sum(1 for warning in warnings if str(warning.get("warning_code", "")).endswith("_unreadable"))


def plan_status(*, sources: dict[str, Any], boundaries: dict[str, Any], warnings: list[dict[str, Any]]) -> str:
    if missing_source_artifact_count(sources["paths"]):
        return "blocked_missing_required_artifact"
    if unreadable_source_artifact_count(warnings):
        return "blocked_unreadable_input"
    if not config_boundary_safe(boundaries):
        return "blocked_by_config_boundary"
    env_status = sources["env_manifest"].get("environment_check_status")
    if env_status == "dry_run_no_mt5_query_performed":
        return "hold_before_no_order_dry_run"
    if env_status != "environment_check_available_with_caveats":
        return "blocked_by_environment_check_status"
    if not no_order_boundary_confirmed(sources["env_manifest"]):
        return "blocked_by_no_order_boundary"
    if not account_snapshot_valid(sources["account_snapshot"]):
        return "blocked_by_environment_check_status"
    if not symbol_snapshot_valid(sources["symbol_snapshot"]):
        return "blocked_by_environment_check_status"
    if not spread_policy_valid(sources["env_manifest"], sources["symbol_snapshot"], boundaries):
        return "blocked_by_config_boundary"
    if not threshold_json_valid(sources["thresholds"]):
        return "blocked_unreadable_input"
    if blocking_warnings(warnings):
        return "blocked_unreadable_input"
    return "demo_no_order_dry_run_plan_available_with_caveats"


def recommended_next_step(status: str) -> str:
    if status in {"demo_no_order_dry_run_plan_available", "demo_no_order_dry_run_plan_available_with_caveats"}:
        return "implement_run_fixed_candidate_demo_no_order_dry_run"
    return "fix_no_order_dry_run_plan_inputs"


def artifact_status_for(status: str) -> str:
    if status == "blocked_missing_required_artifact":
        return "missing"
    if status == "blocked_unreadable_input":
        return "unreadable"
    if status.startswith("blocked"):
        return "blocked"
    return "available_with_caveat"


def plan_row(
    *,
    args: argparse.Namespace,
    area: str,
    status: str,
    artifact_status: str,
    source_path: Path | str,
    observed: Any,
    expected: Any,
    label: str,
    caveat: str,
    warning_code: str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "plan_area": area,
        "plan_status": status,
        "artifact_status": artifact_status,
        "source_path": str(source_path),
        "observed_value": observed,
        "expected_value": expected,
        "evidence_label": label,
        "caveat": caveat,
        "warning_code": warning_code,
        "blocking_warning": blocking_warning,
    }


def build_plan_rows(args: argparse.Namespace, sources: dict[str, Any], boundaries: dict[str, Any], status: str) -> list[dict[str, Any]]:
    artifact_status = artifact_status_for(status)
    env_manifest = sources["env_manifest"]
    account = sources["account_snapshot"]
    symbol = sources["symbol_snapshot"]
    return [
        plan_row(args=args, area="source_artifact_chain", status=status, artifact_status=artifact_status, source_path=args.demo_environment_check_dir, observed="source artifacts read", expected="all required inputs readable", label="environment_check_available", caveat="artifact_only_plan"),
        plan_row(args=args, area="environment_check_status", status=status, artifact_status=artifact_status, source_path=sources["paths"]["env_manifest"], observed=env_manifest.get("environment_check_status"), expected="environment_check_available_with_caveats", label="environment_check_available", caveat="source_environment_check_only"),
        plan_row(args=args, area="account_demo_check", status=status, artifact_status=artifact_status, source_path=sources["paths"]["account_snapshot"], observed={"account_mode_label": account.get("account_trade_mode_label"), "is_demo_account": account.get("is_demo_account")}, expected="demo account redacted snapshot", label="demo_account_confirmed", caveat="redacted_account_snapshot_only"),
        plan_row(args=args, area="symbol_contract_check", status=status, artifact_status=artifact_status, source_path=sources["paths"]["symbol_snapshot"], observed={"symbol": symbol.get("symbol"), "digits": symbol.get("digits"), "point": symbol.get("point")}, expected="GBPUSD symbol contract available", label="symbol_contract_available", caveat="source_snapshot_only"),
        plan_row(args=args, area="spread_policy_check", status=status, artifact_status=artifact_status, source_path=sources["paths"]["symbol_snapshot"], observed={"spread_unit": symbol.get("spread_unit"), "spread_current_points": symbol.get("spread_current_points"), "max_spread_points": symbol.get("max_spread_points")}, expected="broker_points spread <= 15.0", label="spread_policy_canonical", caveat="no_pip_conversion_in_gate"),
        plan_row(args=args, area="no_order_boundary_check", status=status, artifact_status=artifact_status, source_path=sources["paths"]["env_manifest"], observed={flag: env_manifest.get(flag) for flag in NO_ORDER_FLAGS}, expected="all no-order boundary flags true", label="no_order_boundary_confirmed", caveat="order_request_construction_forbidden"),
        plan_row(args=args, area="fixed_rule_inputs_required", status=status, artifact_status="available_with_caveat", source_path=args.demo_strategy_spec_dir, observed="config/spec/feature rows required later", expected="fixed rule inputs available to future script", label="fixed_rule_inputs_required", caveat="feature_row_freshness_unchecked"),
        plan_row(args=args, area="tercile_thresholds_required", status=status, artifact_status=artifact_status, source_path=args.tercile_thresholds_json, observed=sources["thresholds"].get("candidate_id"), expected="frozen thresholds readable", label="frozen_thresholds_required", caveat="future script must not recompute thresholds"),
        plan_row(args=args, area="latest_feature_row_required", status=status, artifact_status="available_with_caveat", source_path=args.future_no_order_dry_run_script, observed="not_checked_here", expected="future script verifies local latest feature row", label="fixed_rule_inputs_required", caveat="feature_row_freshness_unchecked"),
        plan_row(args=args, area="no_order_decision_path", status=status, artifact_status="available_with_caveat", source_path=args.future_no_order_dry_run_script, observed="planned", expected="would_skip/would_signal/would_block only", label="no_order_decision_path_required", caveat="no_trading_decision_made"),
        plan_row(args=args, area="would_skip_path", status=status, artifact_status="available_with_caveat", source_path=args.future_no_order_dry_run_script, observed="planned", expected="future script can emit would_skip", label="would_skip_path_required", caveat="no_order_request_constructed"),
        plan_row(args=args, area="would_signal_path", status=status, artifact_status="available_with_caveat", source_path=args.future_no_order_dry_run_script, observed="planned", expected="future script can emit would_signal", label="would_signal_path_required", caveat="signal_label_only_no_order"),
        plan_row(args=args, area="would_block_path", status=status, artifact_status="available_with_caveat", source_path=args.future_no_order_dry_run_script, observed="planned", expected="future script can emit would_block", label="would_block_path_required", caveat="kill_switch_required"),
        plan_row(args=args, area="risk_preview_without_order_request", status=status, artifact_status="available_with_caveat", source_path=args.future_no_order_dry_run_script, observed=boundaries["max_risk_percent"], expected="preview only without order request or order_calc", label="no_order_boundary_confirmed", caveat="volume_preview_if_possible_without_order_calc"),
        plan_row(args=args, area="state_reconciliation_required", status=status, artifact_status="available_with_caveat", source_path=args.future_no_order_dry_run_script, observed="planned", expected="state reconciliation required", label="state_reconciliation_required", caveat="state_reconciliation_unchecked"),
        plan_row(args=args, area="duplicate_protection_required", status=status, artifact_status="available_with_caveat", source_path=args.future_no_order_dry_run_script, observed="planned", expected="duplicate protection required", label="duplicate_protection_required", caveat="future_check_required"),
        plan_row(args=args, area="kill_switch_required", status=status, artifact_status=artifact_status, source_path=args.demo_strategy_config, observed=boundaries["kill_switch_conditions_present"], expected="kill-switch conditions present", label="kill_switch_required", caveat="future script must exercise block labels only"),
        plan_row(args=args, area="audit_logging_required", status=status, artifact_status=artifact_status, source_path=args.demo_strategy_config, observed=nested_get(sources["config"], "logging", "required_fields") or [], expected="audit logging required", label="audit_logging_required", caveat="future artifacts_required"),
        plan_row(args=args, area="next_future_script", status=status, artifact_status="available", source_path=args.future_no_order_dry_run_script, observed=recommended_next_step(status), expected="future script implementation only", label="no_order_decision_path_required", caveat="no_demo_broker_approval_performed"),
    ]


def requirement_row(
    args: argparse.Namespace,
    area: str,
    name: str,
    fields: list[str],
    expected: str,
    future_artifact: str,
    caveat: str,
    blocking: bool = True,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "requirement_area": area,
        "requirement_name": name,
        "required_fields": fields,
        "expected_condition": expected,
        "blocking_if_failed": blocking,
        "future_artifact": future_artifact,
        "future_script": str(args.future_no_order_dry_run_script),
        "check_mode": "future_demo_no_order_dry_run_only",
        "caveat": caveat,
    }


def build_requirement_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    decision = "fixed_candidate_demo_no_order_dry_run_decision.csv"
    no_order = "fixed_candidate_demo_no_order_dry_run_no_order_evidence.csv"
    state = "fixed_candidate_demo_no_order_dry_run_state_preview.json"
    manifest = "fixed_candidate_demo_no_order_dry_run_manifest.json"
    return [
        requirement_row(args, "read_canonical_config", "read canonical demo strategy config", ["demo_strategy_config_path", "candidate_id", "spread_unit", "max_spread_points"], "config loaded without changing thresholds or risk settings", manifest, "config_read_only"),
        requirement_row(args, "read_demo_strategy_spec", "read demo strategy spec", ["demo_strategy_spec_dir", "paper_only_specification"], "spec loaded as context only", manifest, "spec_read_only"),
        requirement_row(args, "read_environment_check_artifact", "read environment check artifact", ["environment_check_status", "is_demo_account", "spread_within_config_gate"], "source environment evidence remains acceptable", manifest, "no_environment_query_in_future_dry_run_unless_explicitly_allowed"),
        requirement_row(args, "read_frozen_tercile_thresholds", "read frozen tercile thresholds", ["schema_version", "candidate_id", "features"], "thresholds read and never recomputed", manifest, "frozen_thresholds_required"),
        requirement_row(args, "latest_feature_row_required", "read latest local feature row if explicitly allowed", ["time_server", "hour_session", "spread", "atr_20", "required_features"], "feature row is available and fresh enough", decision, "feature_row_freshness_unchecked_here"),
        requirement_row(args, "session_gate", "evaluate session gate", ["hour_session", "required_session"], "would_block or continue based on Off_hours", decision, "decision_label_only"),
        requirement_row(args, "spread_gate", "evaluate spread gate in broker_points", ["spread_current_points", "spread_unit", "max_spread_points"], "spread_current_points <= 15.0 broker_points", decision, "no_pip_conversion"),
        requirement_row(args, "feature_values", "evaluate required feature values", ["close_to_ma_fast_atr_20", "tick_volume_percentile_100", "atr_20"], "required values readable", decision, "no_ml_or_recompute"),
        requirement_row(args, "frozen_tercile_buckets", "evaluate frozen tercile buckets", ["close_to_ma_fast_atr_20_bucket", "tick_volume_percentile_100_bucket"], "buckets evaluated from frozen thresholds only", decision, "thresholds_not_recomputed"),
        requirement_row(args, "one_open_trade_state", "evaluate one-open-trade local state", ["state_path", "has_open_trade"], "would_block if state already has open trade", state, "state_reconciliation_required"),
        requirement_row(args, "would_skip_path", "produce would_skip path", ["decision_label", "skip_reasons"], "would_skip emitted without order request", decision, "would_skip_path_required"),
        requirement_row(args, "would_signal_path", "produce would_signal path", ["decision_label", "entry_reference", "tp_preview", "sl_preview"], "would_signal emitted as label only without order request", decision, "would_signal_path_required"),
        requirement_row(args, "would_block_path", "produce would_block path", ["decision_label", "blocking_reasons"], "would_block emitted for kill-switch/state/config blockers", decision, "would_block_path_required"),
        requirement_row(args, "preview_prices", "compute hypothetical price preview fields only", ["entry_reference", "tp_price_preview", "sl_price_preview", "horizon_bars"], "preview fields only and no request dictionary", decision, "no_order_request_constructed"),
        requirement_row(args, "risk_preview_without_order_request", "compute demo risk preview only if no order_calc is needed", ["risk_percent", "volume_preview", "order_calc_used"], "order_calc_used=false and no request dictionary exists", decision, "preview_may_be_omitted_if_not_safe"),
        requirement_row(args, "duplicate_protection_required", "evaluate duplicate protection evidence", ["candidate_id", "state_signal_id", "duplicate_status"], "would_block if duplicate detected", state, "duplicate_protection_required"),
        requirement_row(args, "kill_switch_required", "emit kill-switch state", ["kill_switch_state", "kill_switch_reasons"], "kill-switch states logged without external action", decision, "kill_switch_required"),
        requirement_row(args, "audit_logging_required", "write full audit artifacts", ["manifest", "report", "decision", "warnings", "no_order_evidence"], "all future artifacts written", manifest, "audit_logging_required"),
        requirement_row(args, "no_order_evidence", "write no-order evidence", ["no_order_request_constructed", "no_order_send_called", "no_order_check_called", "no_order_calc_margin_called", "no_order_calc_profit_called"], "all no-order flags true", no_order, "no_order_boundary_confirmed"),
    ]


def future_artifact_row(args: argparse.Namespace, name: str, role: str, required_before: str, caveat: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "future_artifact_name": name,
        "future_artifact_role": role,
        "produced_by_future_script": str(args.future_no_order_dry_run_script),
        "required_before": required_before,
        "blocking_if_missing": True,
        "caveat": caveat,
    }


def build_future_artifact_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        future_artifact_row(args, "fixed_candidate_demo_no_order_dry_run_manifest.json", "future no-order dry-run manifest", "manual review", "must preserve no-order flags"),
        future_artifact_row(args, "fixed_candidate_demo_no_order_dry_run_report.md", "future no-order dry-run report", "manual review", "must include no-approval caveats"),
        future_artifact_row(args, "fixed_candidate_demo_no_order_dry_run_decision.csv", "future decision-label artifact", "manual review", "would_skip/would_signal/would_block labels only"),
        future_artifact_row(args, "fixed_candidate_demo_no_order_dry_run_checklist.csv", "future checklist result", "manual review", "must show every requirement status"),
        future_artifact_row(args, "fixed_candidate_demo_no_order_dry_run_warnings.csv", "future warnings artifact", "manual review", "must preserve blockers"),
        future_artifact_row(args, "fixed_candidate_demo_no_order_dry_run_no_order_evidence.csv", "future no-order evidence", "manual review", "must show no request/order/order_check/order_calc"),
        future_artifact_row(args, "fixed_candidate_demo_no_order_dry_run_state_preview.json", "future local state preview", "manual review", "must not mutate external state"),
    ]


def blocking_requirement_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if bool(row.get("blocking_if_failed")))


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    sources = load_sources(args, warnings)
    boundaries = config_boundaries(sources["config"])
    if sources["config"] and not config_boundary_safe(boundaries):
        add_warning(warnings, args=args, warning_code="config_boundary_unsafe", message="Canonical config does not match spread15/paper-only boundaries.", source=args.demo_strategy_config, blocking_warning=True)
    if sources["env_manifest"] and not no_order_boundary_confirmed(sources["env_manifest"]):
        add_warning(warnings, args=args, warning_code="no_order_boundary_not_confirmed", message="Environment check source does not preserve all no-order boundary flags.", source=sources["paths"]["env_manifest"], blocking_warning=True)
    if sources["account_snapshot"] and not account_snapshot_valid(sources["account_snapshot"]):
        add_warning(warnings, args=args, warning_code="account_snapshot_not_demo", message="Account snapshot does not confirm redacted demo account evidence.", source=sources["paths"]["account_snapshot"], blocking_warning=True)
    if sources["symbol_snapshot"] and not symbol_snapshot_valid(sources["symbol_snapshot"]):
        add_warning(warnings, args=args, warning_code="symbol_contract_snapshot_incomplete", message="Symbol contract snapshot does not satisfy required GBPUSD contract fields.", source=sources["paths"]["symbol_snapshot"], blocking_warning=True)
    if sources["env_manifest"] and sources["symbol_snapshot"] and not spread_policy_valid(sources["env_manifest"], sources["symbol_snapshot"], boundaries):
        add_warning(warnings, args=args, warning_code="spread_policy_not_canonical_or_outside_gate", message="Spread policy is not canonical broker_points/15.0 or source spread is outside the gate.", source=sources["paths"]["symbol_snapshot"], blocking_warning=True)
    if sources["thresholds"] and not threshold_json_valid(sources["thresholds"]):
        add_warning(warnings, args=args, warning_code="tercile_thresholds_invalid", message="Frozen threshold artifact is unreadable or missing required feature thresholds.", source=args.tercile_thresholds_json, blocking_warning=True)
    status = plan_status(sources=sources, boundaries=boundaries, warnings=warnings)
    plan_rows = build_plan_rows(args, sources, boundaries, status)
    requirement_rows = build_requirement_rows(args)
    future_artifact_rows = build_future_artifact_rows(args)
    write_csv(output_paths["plan"], plan_rows, PLAN_FIELDNAMES)
    write_csv(output_paths["requirements"], requirement_rows, REQUIREMENT_FIELDNAMES)
    write_csv(output_paths["future_artifacts"], future_artifact_rows, FUTURE_ARTIFACT_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(output_paths["report"], args=args, status=status, sources=sources, boundaries=boundaries, requirement_rows=requirement_rows, future_artifact_rows=future_artifact_rows, warnings=warnings)
    write_manifest(output_paths["manifest"], args=args, output_dir=output_paths["manifest"].parent, status=status, sources=sources, boundaries=boundaries, requirement_rows=requirement_rows, future_artifact_rows=future_artifact_rows, warnings=warnings)
    return {"plan_status": status, "plan_rows": plan_rows, "requirement_rows": requirement_rows, "future_artifact_rows": future_artifact_rows, "warnings": warnings}


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    status: str,
    sources: dict[str, Any],
    boundaries: dict[str, Any],
    requirement_rows: list[dict[str, Any]],
    future_artifact_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    env = sources["env_manifest"]
    symbol = sources["symbol_snapshot"]
    account = sources["account_snapshot"]
    output = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_environment_check_dir": str(args.demo_environment_check_dir),
        "demo_environment_check_plan_dir": str(args.demo_environment_check_plan_dir),
        "demo_readiness_plan_dir": str(args.demo_readiness_plan_dir),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "tercile_thresholds_json": str(args.tercile_thresholds_json),
        "future_no_order_dry_run_script": str(args.future_no_order_dry_run_script),
        "plan_status": status,
        "environment_check_status": env.get("environment_check_status"),
        "account_mode_label": account.get("account_trade_mode_label"),
        "is_demo_account": account.get("is_demo_account"),
        "symbol": env.get("symbol") or symbol.get("symbol"),
        "timeframe": env.get("timeframe"),
        "spread_unit": env.get("spread_unit") or symbol.get("spread_unit"),
        "max_spread_points": env.get("max_spread_points") or symbol.get("max_spread_points"),
        "spread_current_points": env.get("spread_current_points") or symbol.get("spread_current_points"),
        "spread_within_config_gate": env.get("spread_within_config_gate"),
        "spread_policy_matches_canonical": env.get("spread_policy_matches_canonical"),
        "volume_min": symbol.get("volume_min"),
        "volume_max": symbol.get("volume_max"),
        "volume_step": symbol.get("volume_step"),
        "point": symbol.get("point"),
        "digits": symbol.get("digits"),
        "trade_tick_size": symbol.get("trade_tick_size"),
        "trade_tick_value": symbol.get("trade_tick_value"),
        "trade_stops_level": symbol.get("trade_stops_level"),
        "trade_freeze_level": symbol.get("trade_freeze_level"),
        "requirement_row_count": len(requirement_rows),
        "future_artifact_row_count": len(future_artifact_rows),
        "blocking_requirement_count": blocking_requirement_count(requirement_rows),
        "missing_source_artifact_count": missing_source_artifact_count(sources["paths"]),
        "unreadable_source_artifact_count": unreadable_source_artifact_count(warnings),
        "future_no_order_dry_run_not_implemented": True,
        "feature_row_freshness_unchecked": True,
        "state_reconciliation_unchecked": True,
        "order_request_construction_forbidden": True,
        "recommended_next_step": recommended_next_step(status),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "no_child_scripts_executed": True,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
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
    sources: dict[str, Any],
    boundaries: dict[str, Any],
    requirement_rows: list[dict[str, Any]],
    future_artifact_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    env = sources["env_manifest"]
    account = sources["account_snapshot"]
    symbol = sources["symbol_snapshot"]
    lines = [
        "# Fixed Candidate Demo No-Order Dry-Run Plan",
        "",
        "Artifact-only demo no-order dry-run planning artifact.",
        "No MT5, broker/API, or external connection was performed.",
        "No account query was performed.",
        "No symbol query was performed.",
        "No order execution was performed.",
        "No order request was constructed.",
        "No order_check or order_calc call was performed.",
        "No database mutation was performed.",
        "No feature refresh was performed.",
        "No replay, cost sensitivity, recent holdout, or paper workflow was rerun.",
        "No optimization or parameter search was performed.",
        "This plan is not future-performance proof.",
        "This plan is not demo broker approval.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- demo_environment_check_dir: `{args.demo_environment_check_dir}`",
        f"- demo_environment_check_plan_dir: `{args.demo_environment_check_plan_dir}`",
        f"- demo_readiness_plan_dir: `{args.demo_readiness_plan_dir}`",
        f"- demo_strategy_spec_dir: `{args.demo_strategy_spec_dir}`",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- tercile_thresholds_json: `{args.tercile_thresholds_json}`",
        f"- future_no_order_dry_run_script: `{args.future_no_order_dry_run_script}`",
        "",
        "## Environment Check Source Summary",
        "",
        f"- environment_check_status: `{env.get('environment_check_status')}`",
        f"- recommended_next_step: `{env.get('recommended_next_step')}`",
        f"- no_order_boundary_confirmed: `{bool_text(no_order_boundary_confirmed(env))}`",
        "",
        "## Account/Symbol/Spread Source Evidence",
        "",
        f"- account_mode_label: `{account.get('account_trade_mode_label')}`",
        f"- is_demo_account: `{account.get('is_demo_account')}`",
        f"- redaction_applied: `{account.get('redaction_applied')}`",
        f"- symbol: `{symbol.get('symbol')}`",
        f"- digits: `{symbol.get('digits')}`",
        f"- point: `{symbol.get('point')}`",
        f"- volume_min: `{symbol.get('volume_min')}`",
        f"- volume_step: `{symbol.get('volume_step')}`",
        f"- spread_unit: `{env.get('spread_unit') or symbol.get('spread_unit')}`",
        f"- max_spread_points: `{env.get('max_spread_points') or symbol.get('max_spread_points')}`",
        f"- spread_current_points: `{env.get('spread_current_points') or symbol.get('spread_current_points')}`",
        f"- spread_policy_matches_canonical: `{env.get('spread_policy_matches_canonical')}`",
        "",
        "## No-Order Boundary Summary",
        "",
    ]
    for flag in NO_ORDER_FLAGS:
        lines.append(f"- {flag}: `{env.get(flag)}`")
    lines.extend(["", "## Required Future No-Order Dry-Run Checks", ""])
    for row in requirement_rows:
        lines.append(f"- `{row['requirement_area']}`: {row['requirement_name']}")
    lines.extend(["", "## Required Future Artifacts", ""])
    for row in future_artifact_rows:
        lines.append(f"- `{row['future_artifact_name']}`: {row['future_artifact_role']}")
    lines.extend(
        [
            "",
            "## Remaining Caveats",
            "",
            "- Future no-order dry-run is not implemented.",
            "- Feature row freshness is not checked here.",
            "- State reconciliation is not checked here.",
            "- No future decision path has been executed.",
            "- No demo broker action is approved.",
            "",
            "## Plan Status",
            "",
            f"`{status}`",
            "",
            "## Recommended Next Step",
            "",
            f"`{recommended_next_step(status)}`",
            "",
            "## Warnings",
            "",
            f"- warnings_count: `{len(warnings)}`",
            f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
            f"- config_spread_policy_matches_canonical: `{bool_text(bool(boundaries['spread_policy_matches_canonical']))}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    build_artifacts(args, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build artifact-only demo no-order dry-run plan for the fixed candidate.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-environment-check-dir", type=Path, default=DEFAULT_DEMO_ENVIRONMENT_CHECK_DIR)
    parser.add_argument("--demo-environment-check-plan-dir", type=Path, default=DEFAULT_DEMO_ENVIRONMENT_CHECK_PLAN_DIR)
    parser.add_argument("--demo-readiness-plan-dir", type=Path, default=DEFAULT_DEMO_READINESS_PLAN_DIR)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--tercile-thresholds-json", type=Path, default=DEFAULT_TERCILE_THRESHOLDS_JSON)
    parser.add_argument("--future-no-order-dry-run-script", type=Path, default=DEFAULT_FUTURE_NO_ORDER_DRY_RUN_SCRIPT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate demo no-order dry-run plan failed: {exc}")
        return 1
    print("Fixed-candidate demo no-order dry-run plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
