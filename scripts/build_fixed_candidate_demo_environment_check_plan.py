"""Build an artifact-only demo environment check plan for the fixed candidate.

This module converts the completed demo readiness checklist into a concrete
future environment-check plan. It does not connect to MT5, connect to broker/API
services, query account or symbol state, execute orders, query or mutate the
database, refresh features, rerun replay or reviews, optimize parameters, or
make candidate-quality or trading decisions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_environment_check_plan"
DEFAULT_DEMO_READINESS_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_readiness_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_readiness_plan_spread15_v1"
)
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR / "config" / "paper_demo" / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)
DEFAULT_DEMO_STRATEGY_SPEC_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_strategy_spec"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v5_spread15"
)
DEFAULT_FUTURE_ENVIRONMENT_CHECK_SCRIPT = BASE_DIR / "scripts" / "check_fixed_candidate_demo_environment.py"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_environment_check_plan"

READINESS_PLAN_CSV = "fixed_candidate_demo_readiness_plan.csv"
READINESS_PLAN_CHECKLIST = "fixed_candidate_demo_readiness_plan_checklist.csv"
READINESS_PLAN_MANIFEST = "fixed_candidate_demo_readiness_plan_manifest.json"
READINESS_PLAN_REPORT = "fixed_candidate_demo_readiness_plan_report.md"
READINESS_PLAN_WARNINGS = "fixed_candidate_demo_readiness_plan_warnings.csv"

SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"
SPEC_REPORT = "fixed_candidate_demo_strategy_spec_report.md"

OUTPUT_PLAN = "fixed_candidate_demo_environment_check_plan.csv"
OUTPUT_REQUIREMENTS = "fixed_candidate_demo_environment_check_plan_requirements.csv"
OUTPUT_FUTURE_ARTIFACTS = "fixed_candidate_demo_environment_check_plan_future_artifacts.csv"
OUTPUT_REPORT = "fixed_candidate_demo_environment_check_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_demo_environment_check_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_demo_environment_check_plan_manifest.json"

ACCEPTABLE_DEMO_READINESS_STATUSES = {
    "demo_readiness_plan_available",
    "demo_readiness_plan_available_with_caveats",
}
BOUNDARY_FLAGS = (
    "no_broker_connection_performed",
    "no_order_execution_performed",
    "no_db_mutation_performed",
    "no_data_generation_performed",
    "no_feature_refresh_performed",
    "no_trading_decision_performed",
)
REQUIRED_KILL_SWITCH_CONDITIONS = {
    "required_data_missing",
    "required_features_missing",
    "spread_abnormal_or_not_configured",
    "atr_calculation_failed",
    "timeframe_mismatch",
    "session_mismatch",
    "existing_paper_demo_trade_open",
}

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
    "future_checker_script",
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


def load_demo_readiness_source(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    root = Path(args.demo_readiness_plan_dir)
    paths = {
        "dir": root,
        "manifest": root / READINESS_PLAN_MANIFEST,
        "report": root / READINESS_PLAN_REPORT,
        "plan": root / READINESS_PLAN_CSV,
        "checklist": root / READINESS_PLAN_CHECKLIST,
        "warnings": root / READINESS_PLAN_WARNINGS,
    }
    required = {"manifest", "plan", "checklist"}
    missing = [name for name in ("manifest", "report", "plan", "checklist", "warnings") if not paths[name].exists()]
    for name in missing:
        add_warning(
            warnings,
            args=args,
            warning_code=f"demo_readiness_{name}_missing",
            message=f"Demo readiness source artifact is missing: {paths[name].name}",
            source=paths[name],
            blocking_warning=name in required,
        )
    manifest, manifest_error = read_json(paths["manifest"])
    plan_rows, plan_error = read_csv_rows(paths["plan"])
    checklist_rows, checklist_error = read_csv_rows(paths["checklist"])
    source_warnings, warnings_error = read_csv_rows(paths["warnings"])
    report = read_text(paths["report"])
    for name, error in [
        ("manifest", manifest_error),
        ("plan", plan_error),
        ("checklist", checklist_error),
        ("warnings", warnings_error),
    ]:
        if error:
            add_warning(
                warnings,
                args=args,
                warning_code=f"demo_readiness_{name}_unreadable",
                message=f"Demo readiness source artifact is unreadable: {error}",
                source=paths[name],
                blocking_warning=name in required,
            )
    for row in source_warnings:
        add_warning(
            warnings,
            args=args,
            warning_code=row.get("warning_code", "demo_readiness_source_warning"),
            message=row.get("message", "Demo readiness source warning preserved."),
            source=row.get("source", paths["warnings"]),
            blocking_warning=str(row.get("blocking_warning", "")).lower() == "true",
            severity=row.get("severity") or "warning",
        )
    return {
        "paths": paths,
        "manifest": manifest,
        "plan_rows": plan_rows,
        "checklist_rows": checklist_rows,
        "report": report,
        "missing_required_count": sum(1 for name in missing if name in required),
        "missing_count": len(missing),
        "unreadable_required_count": sum(
            1
            for name, error in [
                ("manifest", manifest_error),
                ("plan", plan_error),
                ("checklist", checklist_error),
            ]
            if error
        ),
        "unreadable_count": sum(1 for error in (manifest_error, plan_error, checklist_error, warnings_error) if error),
    }


def load_demo_strategy_spec(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.demo_strategy_spec_dir)
    manifest, manifest_error = read_json(root / SPEC_MANIFEST)
    rows, rows_error = read_csv_rows(root / SPEC_CSV)
    return {
        "paths": {
            "dir": root,
            "manifest": root / SPEC_MANIFEST,
            "csv": root / SPEC_CSV,
            "report": root / SPEC_REPORT,
        },
        "manifest": manifest,
        "rows": rows,
        "report": read_text(root / SPEC_REPORT),
        "missing_count": sum(1 for name in (SPEC_MANIFEST, SPEC_CSV, SPEC_REPORT) if not (root / name).exists()),
        "unreadable_count": sum(1 for error in (manifest_error, rows_error) if error),
    }


def readiness_boundaries_confirmed(manifest: dict[str, Any]) -> bool:
    for flag in BOUNDARY_FLAGS:
        if manifest.get(flag) is not True:
            return False
    return True


def plan_status(
    *,
    config: dict[str, Any],
    boundaries: dict[str, Any],
    readiness_source: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> str:
    if not config or readiness_source["missing_required_count"]:
        return "blocked_missing_required_artifact"
    if readiness_source["unreadable_required_count"]:
        return "blocked_unreadable_input"
    if not config_boundary_safe(boundaries):
        return "blocked_by_config_boundary"
    readiness_status = str(readiness_source["manifest"].get("readiness_status") or "")
    if readiness_status.startswith("hold"):
        return "hold_before_environment_check"
    if readiness_status not in ACCEPTABLE_DEMO_READINESS_STATUSES:
        return "blocked_by_demo_readiness_status"
    if not readiness_boundaries_confirmed(readiness_source["manifest"]):
        return "blocked_by_demo_readiness_status"
    if blocking_warnings(warnings):
        return "blocked_unreadable_input"
    return "demo_environment_check_plan_available_with_caveats"


def recommended_next_step(status: str) -> str:
    if status in {"demo_environment_check_plan_available", "demo_environment_check_plan_available_with_caveats"}:
        return "implement_check_fixed_candidate_demo_environment"
    return "fix_environment_plan_inputs"


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


def build_plan_rows(
    args: argparse.Namespace,
    *,
    status: str,
    readiness_source: dict[str, Any],
    spec_source: dict[str, Any],
    config: dict[str, Any],
    boundaries: dict[str, Any],
) -> list[dict[str, Any]]:
    artifact_status = artifact_status_for(status)
    readiness_status = readiness_source["manifest"].get("readiness_status", "")
    return [
        plan_row(
            args=args,
            area="demo_readiness_source",
            status=status,
            artifact_status=artifact_status,
            source_path=readiness_source["paths"]["manifest"],
            observed=readiness_status,
            expected="demo_readiness_plan_available_with_caveats",
            label="demo_readiness_plan_available",
            caveat="source_demo_readiness_plan_is_planning_context_only",
        ),
        plan_row(
            args=args,
            area="strategy_config_boundary",
            status=status,
            artifact_status=artifact_status,
            source_path=args.demo_strategy_config,
            observed={
                "paper_only": boundaries["paper_only"],
                "max_open_positions": boundaries["max_open_positions"],
                "max_risk_percent": boundaries["max_risk_percent"],
                "max_spread_points": boundaries["max_spread_points"],
            },
            expected="paper/demo config boundaries remain disabled for external actions",
            label="config_boundaries_safe",
            caveat="future environment check must stay no-order/read-only first",
        ),
        plan_row(
            args=args,
            area="demo_strategy_spec_context",
            status=status,
            artifact_status="available_with_caveat" if spec_source["manifest"] else "missing",
            source_path=spec_source["paths"]["manifest"],
            observed=spec_source["manifest"].get("paper_only_specification", ""),
            expected="paper_only_specification=true when available",
            label="environment_check_required",
            caveat="spec_read_for_context_only",
        ),
        plan_row(
            args=args,
            area="environment_check_scope",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.future_environment_check_script,
            observed="future read-only/no-order checker planned",
            expected="no account/symbol query in this plan module",
            label="environment_check_required",
            caveat="environment_unchecked",
        ),
        plan_row(
            args=args,
            area="account_mode_check",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.future_environment_check_script,
            observed="not_checked",
            expected="future checker confirms demo account and blocks other account modes",
            label="account_mode_check_required",
            caveat="account_mode_unchecked",
        ),
        plan_row(
            args=args,
            area="symbol_contract_check",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.future_environment_check_script,
            observed="not_checked",
            expected="future checker captures symbol contract fields",
            label="symbol_contract_check_required",
            caveat="broker_contract_unchecked",
        ),
        plan_row(
            args=args,
            area="spread_unit_check",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.demo_strategy_config,
            observed={"spread_unit": boundaries["spread_unit"], "max_spread_points": boundaries["max_spread_points"]},
            expected="spread_unit=broker_points and max_spread_points=15.0",
            label="spread_unit_check_required",
            caveat="spread_unit_unchecked",
        ),
        plan_row(
            args=args,
            area="risk_sizing_check",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.demo_strategy_config,
            observed=boundaries["max_risk_percent"],
            expected="future checker uses demo balance only and sends no order",
            label="risk_sizing_check_required",
            caveat="demo_balance_not_queried",
        ),
        plan_row(
            args=args,
            area="one_open_trade_state_check",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.future_environment_check_script,
            observed="not_checked",
            expected="one open trade enforcement checked later",
            label="state_reconciliation_check_required",
            caveat="state_reconciliation_unchecked",
        ),
        plan_row(
            args=args,
            area="execution_dry_run_required",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.future_environment_check_script,
            observed="not_performed",
            expected="dry-run/no-order check before any later environment action",
            label="dry_run_no_order_check_required",
            caveat="execution_dry_run_not_performed",
        ),
        plan_row(
            args=args,
            area="kill_switch_check",
            status=status,
            artifact_status=artifact_status,
            source_path=args.demo_strategy_config,
            observed=boundaries["kill_switch_conditions_present"],
            expected="all configured kill-switch conditions present",
            label="kill_switch_check_required",
            caveat="future_checker_must_verify_behavior_without_orders",
        ),
        plan_row(
            args=args,
            area="audit_logging_check",
            status=status,
            artifact_status=artifact_status,
            source_path=args.demo_strategy_config,
            observed=nested_get(config, "logging", "required_fields") or [],
            expected="future checker emits full audit artifacts",
            label="audit_logging_check_required",
            caveat="future_artifacts_required",
        ),
        plan_row(
            args=args,
            area="next_artifact_required",
            status=status,
            artifact_status="available",
            source_path=args.output_dir or "",
            observed=recommended_next_step(status),
            expected="future environment checker implementation only",
            label="environment_check_required",
            caveat="no_trading_decision_made",
        ),
    ]


def requirement_row(
    args: argparse.Namespace,
    area: str,
    name: str,
    required_fields: list[str],
    expected_condition: str,
    future_artifact: str,
    caveat: str,
    blocking_if_failed: bool = True,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "requirement_area": area,
        "requirement_name": name,
        "required_fields": required_fields,
        "expected_condition": expected_condition,
        "blocking_if_failed": blocking_if_failed,
        "future_artifact": future_artifact,
        "future_checker_script": str(args.future_environment_check_script),
        "check_mode": "future_read_only_no_order_check",
        "caveat": caveat,
    }


def build_requirement_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    manifest = "fixed_candidate_demo_environment_check_manifest.json"
    symbol_snapshot = "fixed_candidate_demo_environment_symbol_contract_snapshot.json"
    account_snapshot = "fixed_candidate_demo_environment_account_snapshot_redacted.json"
    dry_run = "fixed_candidate_demo_environment_dry_run_no_order_check.csv"
    report = "fixed_candidate_demo_environment_check_report.md"
    return [
        requirement_row(
            args,
            "account_mode_check",
            "confirm account mode permits only demo-environment review",
            ["account_login_redacted", "account_server", "account_trade_mode", "is_demo_account", "non_demo_account_blocked"],
            "is_demo_account=true and non_demo_account_blocked=true before any later environment action",
            account_snapshot,
            "future checker may inspect account mode only when explicitly run",
        ),
        requirement_row(
            args,
            "terminal_connection_check",
            "confirm terminal connection status in a separate future check",
            ["terminal_name", "terminal_build", "connected", "environment_check_timestamp"],
            "connection status captured for context without sending orders",
            manifest,
            "this planning module performs no terminal connection",
        ),
        requirement_row(
            args,
            "symbol_visibility_check",
            "confirm GBPUSD symbol visible and selectable in demo environment",
            ["symbol", "symbol_visible", "symbol_selected", "trade_availability"],
            "symbol_visible=true and trade availability captured",
            symbol_snapshot,
            "symbol state is unchecked in this artifact",
        ),
        requirement_row(
            args,
            "symbol_contract_check",
            "capture GBPUSD symbol contract fields",
            [
                "symbol",
                "trade_mode",
                "min_volume",
                "max_volume",
                "volume_step",
                "point_size",
                "tick_size",
                "tick_value",
                "stop_level",
                "freeze_level",
            ],
            "all symbol contract fields present and internally consistent",
            symbol_snapshot,
            "symbol contract remains unchecked until future artifact",
        ),
        requirement_row(
            args,
            "symbol_contract_check",
            "confirm min volume, max volume, and volume step",
            ["symbol", "min_volume", "max_volume", "volume_step", "volume_contract_status"],
            "volume_contract_status=pass and values are present",
            symbol_snapshot,
            "lot/volume contract details remain unchecked until future artifact",
        ),
        requirement_row(
            args,
            "symbol_contract_check",
            "confirm point size, tick size, and tick value",
            ["symbol", "point_size", "tick_size", "tick_value", "price_increment_status"],
            "price_increment_status=pass and values are present",
            symbol_snapshot,
            "price increment details remain unchecked until future artifact",
        ),
        requirement_row(
            args,
            "symbol_contract_check",
            "confirm stop level and freeze level",
            ["symbol", "stop_level", "freeze_level", "stop_freeze_status"],
            "stop_freeze_status=pass and values are present",
            symbol_snapshot,
            "stop/freeze constraints remain unchecked until future artifact",
        ),
        requirement_row(
            args,
            "spread_unit_check",
            "confirm spread source and units align with max_spread_points",
            ["current_spread", "spread_units", "max_spread_points_config", "spread_unit_alignment_result"],
            "spread_unit_alignment_result=aligned, spread_units=broker_points, and max_spread_points_config=15.0",
            symbol_snapshot,
            "spread units are project-defined until checked against future environment data",
        ),
        requirement_row(
            args,
            "risk_sizing_check",
            "verify risk sizing can be computed from demo balance only",
            ["demo_balance", "risk_percent", "computed_volume_preview", "volume_step_adjusted_preview", "order_sent"],
            "computed using demo balance only and order_sent=false",
            account_snapshot,
            "this plan does not query demo balance or compute volume",
        ),
        requirement_row(
            args,
            "one_open_trade_state_check",
            "verify one-open-trade state gate",
            ["local_state_open_trade_count", "environment_position_count", "one_open_trade_gate_result"],
            "one_open_trade_gate_result=pass before any later module",
            "fixed_candidate_demo_environment_state_reconciliation.csv",
            "state reconciliation is a future check",
        ),
        requirement_row(
            args,
            "duplicate_protection_check",
            "verify duplicate protection plan",
            ["candidate_id", "symbol", "magic_or_strategy_tag", "duplicate_detection_result"],
            "duplicate_detection_result=pass",
            "fixed_candidate_demo_environment_duplicate_protection.csv",
            "future checker must remain no-order",
        ),
        requirement_row(
            args,
            "sl_tp_attachment_check",
            "verify SL/TP attachment fields can be derived",
            ["entry_reference_price", "tp_price_preview", "sl_price_preview", "sl_tp_attachable", "order_sent"],
            "sl_tp_attachable=true and order_sent=false",
            dry_run,
            "preview only; no order is sent",
        ),
        requirement_row(
            args,
            "timeout_h10_handling_check",
            "verify timeout h10 handling is represented in future state model",
            ["horizon_bars", "timeframe", "timeout_state_field", "timeout_action_preview"],
            "horizon_bars=10 and timeout fields available",
            "fixed_candidate_demo_environment_timeout_plan.csv",
            "timeout behavior is not executed by this plan",
        ),
        requirement_row(
            args,
            "broker_state_reconciliation_check",
            "verify local state and future environment state reconciliation",
            ["local_state_snapshot", "environment_state_snapshot", "reconciliation_status"],
            "reconciliation_status=pass before any later action",
            "fixed_candidate_demo_environment_state_reconciliation.csv",
            "future checker must redact sensitive account fields",
        ),
        requirement_row(
            args,
            "crash_restart_recovery_check",
            "verify crash/restart recovery fields",
            ["state_file_path", "state_loaded", "last_seen_time_server", "recovery_status"],
            "recovery_status=pass",
            "fixed_candidate_demo_environment_recovery_check.csv",
            "future checker only plans recovery evidence",
        ),
        requirement_row(
            args,
            "kill_switch_check",
            "verify configured kill-switch conditions",
            ["required_data_missing", "required_features_missing", "spread_gate", "atr_gate", "timeframe_gate", "session_gate", "open_trade_gate"],
            "each configured kill-switch condition is represented and testable",
            "fixed_candidate_demo_environment_kill_switch_check.csv",
            "future checker must not send orders when checking gates",
        ),
        requirement_row(
            args,
            "audit_logging_check",
            "verify audit logging fields",
            ["timestamp", "symbol", "timeframe", "signal_state", "errors", "skipped_reasons", "kill_switch_state"],
            "required audit fields present in future environment checker output",
            report,
            "future artifacts must be sufficient for manual review",
        ),
        requirement_row(
            args,
            "dry_run_no_order_check",
            "verify dry-run/no-order mode before any later environment test",
            ["dry_run", "order_send_called", "order_check_called", "order_sent", "orders_created"],
            "dry_run=true, order_send_called=false, order_sent=false, orders_created=0",
            dry_run,
            "this is mandatory before any later demo order test planning",
        ),
    ]


def future_artifact_row(
    args: argparse.Namespace,
    name: str,
    role: str,
    required_before: str,
    caveat: str,
    blocking_if_missing: bool = True,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "future_artifact_name": name,
        "future_artifact_role": role,
        "produced_by_future_script": str(args.future_environment_check_script),
        "required_before": required_before,
        "blocking_if_missing": blocking_if_missing,
        "caveat": caveat,
    }


def build_future_artifact_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        future_artifact_row(args, "fixed_candidate_demo_environment_check_manifest.json", "future environment check manifest", "any later environment action", "must preserve no-order boundary flags"),
        future_artifact_row(args, "fixed_candidate_demo_environment_check_report.md", "future environment check report", "manual environment review", "must include no-approval caveats"),
        future_artifact_row(args, "fixed_candidate_demo_environment_check_checklist.csv", "future environment checklist result", "manual environment review", "must record pass/fail for each requirement"),
        future_artifact_row(args, "fixed_candidate_demo_environment_check_warnings.csv", "future warnings artifact", "manual environment review", "must preserve blocking warnings"),
        future_artifact_row(args, "fixed_candidate_demo_environment_check_requirements.csv", "future requirements evidence", "manual environment review", "must map checks to this plan"),
        future_artifact_row(args, "fixed_candidate_demo_environment_account_snapshot_redacted.json", "redacted account mode snapshot", "account mode review", "must not include sensitive secrets"),
        future_artifact_row(args, "fixed_candidate_demo_environment_symbol_contract_snapshot.json", "symbol contract snapshot", "symbol contract review", "must include spread unit evidence"),
        future_artifact_row(args, "fixed_candidate_demo_environment_dry_run_no_order_check.csv", "dry-run/no-order evidence", "before any later demo order test planning", "must show no order was sent"),
    ]


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    readiness_source = load_demo_readiness_source(args, warnings)
    config = load_config(args, warnings)
    spec_source = load_demo_strategy_spec(args)
    boundaries = config_boundaries(config)
    if config and not config_boundary_safe(boundaries):
        add_warning(
            warnings,
            args=args,
            warning_code="demo_config_boundary_unsafe",
            message="Demo strategy config does not satisfy required paper/demo environment planning boundaries.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    if readiness_source["manifest"] and not readiness_boundaries_confirmed(readiness_source["manifest"]):
        add_warning(
            warnings,
            args=args,
            warning_code="demo_readiness_boundary_not_confirmed",
            message="Demo readiness manifest does not confirm required no-execution boundary flags.",
            source=readiness_source["paths"]["manifest"],
            blocking_warning=True,
        )
    status = plan_status(config=config, boundaries=boundaries, readiness_source=readiness_source, warnings=warnings)
    plan_rows = build_plan_rows(
        args,
        status=status,
        readiness_source=readiness_source,
        spec_source=spec_source,
        config=config,
        boundaries=boundaries,
    )
    requirement_rows = build_requirement_rows(args)
    future_artifact_rows = build_future_artifact_rows(args)
    write_csv(output_paths["plan"], plan_rows, PLAN_FIELDNAMES)
    write_csv(output_paths["requirements"], requirement_rows, REQUIREMENT_FIELDNAMES)
    write_csv(output_paths["future_artifacts"], future_artifact_rows, FUTURE_ARTIFACT_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(
        output_paths["report"],
        args=args,
        status=status,
        readiness_source=readiness_source,
        config=config,
        boundaries=boundaries,
        requirement_rows=requirement_rows,
        future_artifact_rows=future_artifact_rows,
        warnings=warnings,
    )
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        status=status,
        readiness_source=readiness_source,
        config=config,
        boundaries=boundaries,
        requirement_rows=requirement_rows,
        future_artifact_rows=future_artifact_rows,
        warnings=warnings,
    )
    return {
        "plan_status": status,
        "plan_rows": plan_rows,
        "requirement_rows": requirement_rows,
        "future_artifact_rows": future_artifact_rows,
        "warnings": warnings,
    }


def blocking_requirement_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if bool(row.get("blocking_if_failed")))


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    status: str,
    readiness_source: dict[str, Any],
    config: dict[str, Any],
    boundaries: dict[str, Any],
    requirement_rows: list[dict[str, Any]],
    future_artifact_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    output = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_readiness_plan_dir": str(args.demo_readiness_plan_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "future_environment_check_script": str(args.future_environment_check_script),
        "plan_status": status,
        "demo_readiness_status": readiness_source["manifest"].get("readiness_status", ""),
        "config_paper_only": boundaries["paper_only"],
        "config_max_risk_percent": boundaries["max_risk_percent"],
        "config_max_open_positions": boundaries["max_open_positions"],
        "config_max_spread_points": boundaries["max_spread_points"],
        "config_spread_unit": boundaries["spread_unit"],
        "config_spread_policy_matches_canonical": boundaries["spread_policy_matches_canonical"],
        "spread_unit": boundaries["spread_unit"],
        "max_spread_points": boundaries["max_spread_points"],
        "spread_policy_matches_canonical": boundaries["spread_policy_matches_canonical"],
        "kill_switch_conditions_present": boundaries["kill_switch_conditions_present"],
        "requirement_row_count": len(requirement_rows),
        "future_artifact_row_count": len(future_artifact_rows),
        "blocking_requirement_count": blocking_requirement_count(requirement_rows),
        "missing_source_artifact_count": readiness_source["missing_count"] + (0 if config else 1),
        "unreadable_source_artifact_count": readiness_source["unreadable_count"],
        "environment_unchecked": True,
        "account_mode_unchecked": True,
        "broker_contract_unchecked": True,
        "spread_unit_unchecked": True,
        "execution_dry_run_not_performed": True,
        "recommended_next_step": recommended_next_step(status),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "no_child_scripts_executed": True,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_replay_rerun": True,
        "no_cost_sensitivity_rerun": True,
        "no_recent_holdout_rerun": True,
        "no_optimization_performed": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    status: str,
    readiness_source: dict[str, Any],
    config: dict[str, Any],
    boundaries: dict[str, Any],
    requirement_rows: list[dict[str, Any]],
    future_artifact_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    lines = [
        "# Fixed Candidate Demo Environment Check Plan",
        "",
        "Artifact-only demo environment check planning artifact.",
        "No MT5, broker/API, or external connection was performed.",
        "No account query was performed.",
        "No symbol query was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No feature refresh was performed.",
        "No replay, cost sensitivity, or recent holdout rerun was performed.",
        "No optimization or parameter search was performed.",
        "This plan is not future-performance proof.",
        "This plan is not demo broker approval.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- demo_readiness_plan_dir: `{args.demo_readiness_plan_dir}`",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- demo_strategy_spec_dir: `{args.demo_strategy_spec_dir}`",
        f"- future_environment_check_script: `{args.future_environment_check_script}`",
        "",
        "## Demo Readiness Source Summary",
        "",
        f"- demo_readiness_status: `{readiness_source['manifest'].get('readiness_status', '')}`",
        f"- source_checklist_rows: `{len(readiness_source['checklist_rows'])}`",
        f"- source_blocking_checklist_items: `{readiness_source['manifest'].get('blocking_checklist_item_count', '')}`",
        "",
        "## Config Boundary Summary",
        "",
        f"- candidate_id: `{config.get('candidate_id')}`",
        f"- symbol: `{nested_get(config, 'candidate', 'symbol')}`",
        f"- timeframe: `{nested_get(config, 'candidate', 'timeframe')}`",
        f"- paper_only: `{bool_text(bool(boundaries['paper_only']))}`",
        f"- max_risk_percent_from_note: `{boundaries['max_risk_percent']}`",
        f"- max_open_positions_from_note: `{boundaries['max_open_positions']}`",
        f"- spread_unit: `{boundaries['spread_unit']}`",
        f"- max_spread_points: `{boundaries['max_spread_points']}`",
        f"- kill_switch_conditions_present: `{bool_text(bool(boundaries['kill_switch_conditions_present']))}`",
        "",
        "## Required Environment Checks",
        "",
    ]
    for row in requirement_rows:
        lines.append(f"- `{row['requirement_area']}`: {row['requirement_name']}")
    lines.extend(
        [
            "",
            "## Required Future Artifacts",
            "",
        ]
    )
    for row in future_artifact_rows:
        lines.append(f"- `{row['future_artifact_name']}`: {row['future_artifact_role']}")
    lines.extend(
        [
            "",
            "## Remaining Caveats",
            "",
            "- Environment has not been checked.",
            "- Account mode has not been checked.",
            "- Symbol contract has not been checked.",
            "- Spread units have not been checked against future environment data.",
            "- Dry-run/no-order evidence has not been produced.",
            "- Upstream cost timeout fragility remains preserved as a caveat.",
            "- This plan does not approve any demo broker action.",
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
    parser = argparse.ArgumentParser(description="Build artifact-only demo environment check plan for the fixed candidate.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-readiness-plan-dir", type=Path, default=DEFAULT_DEMO_READINESS_PLAN_DIR)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--future-environment-check-script", type=Path, default=DEFAULT_FUTURE_ENVIRONMENT_CHECK_SCRIPT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate demo environment check plan failed: {exc}")
        return 1
    print("Fixed-candidate demo environment check plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
