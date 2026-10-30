"""Build an artifact-only demo readiness plan for the fixed candidate.

This module reads the canonical paper/demo config plus completed replay,
cost-sensitivity, and recent-period holdout review artifacts, then writes a
future demo-readiness checklist. It does not connect to MT5, connect to
broker/API services, execute orders, query or mutate the database, refresh
features, rerun replay or reviews, optimize parameters, or make candidate-quality
or trading decisions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_readiness_plan"
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR / "config" / "paper_demo" / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)
DEFAULT_DEMO_STRATEGY_SPEC_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_strategy_spec"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v5_spread15"
)
DEFAULT_REPLAY_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_fixed_rule_replay_backtest_review"
    / "gbpusd_short_h10_1_5_off_hours_fixed_rule_replay_spread15_review_v1"
)
DEFAULT_COST_SENSITIVITY_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_replay_cost_sensitivity_review"
    / "gbpusd_short_h10_1_5_off_hours_replay_cost_sensitivity_review_spread15_v1"
)
DEFAULT_RECENT_HOLDOUT_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_recent_period_holdout_review"
    / "gbpusd_short_h10_1_5_off_hours_recent_period_holdout_review_spread15_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_readiness_plan"

SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"
SPEC_REPORT = "fixed_candidate_demo_strategy_spec_report.md"
SPEC_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"

REPLAY_REVIEW_CSV = "fixed_candidate_fixed_rule_replay_backtest_review.csv"
REPLAY_REVIEW_MANIFEST = "fixed_candidate_fixed_rule_replay_backtest_review_manifest.json"
REPLAY_REVIEW_REPORT = "fixed_candidate_fixed_rule_replay_backtest_review_report.md"
REPLAY_REVIEW_WARNINGS = "fixed_candidate_fixed_rule_replay_backtest_review_warnings.csv"

COST_REVIEW_CSV = "fixed_candidate_replay_cost_sensitivity_review.csv"
COST_REVIEW_MANIFEST = "fixed_candidate_replay_cost_sensitivity_review_manifest.json"
COST_REVIEW_REPORT = "fixed_candidate_replay_cost_sensitivity_review_report.md"
COST_REVIEW_WARNINGS = "fixed_candidate_replay_cost_sensitivity_review_warnings.csv"

HOLDOUT_REVIEW_CSV = "fixed_candidate_recent_period_holdout_review.csv"
HOLDOUT_REVIEW_MANIFEST = "fixed_candidate_recent_period_holdout_review_manifest.json"
HOLDOUT_REVIEW_REPORT = "fixed_candidate_recent_period_holdout_review_report.md"
HOLDOUT_REVIEW_WARNINGS = "fixed_candidate_recent_period_holdout_review_warnings.csv"

OUTPUT_PLAN = "fixed_candidate_demo_readiness_plan.csv"
OUTPUT_CHECKLIST = "fixed_candidate_demo_readiness_plan_checklist.csv"
OUTPUT_REPORT = "fixed_candidate_demo_readiness_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_demo_readiness_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_demo_readiness_plan_manifest.json"

SOURCE_SPECS = {
    "demo_strategy_spec": {
        "dir_arg": "demo_strategy_spec_dir",
        "csv": SPEC_CSV,
        "manifest": SPEC_MANIFEST,
        "report": SPEC_REPORT,
        "warnings": SPEC_WARNINGS,
        "required": True,
    },
    "replay_review": {
        "dir_arg": "replay_review_dir",
        "csv": REPLAY_REVIEW_CSV,
        "manifest": REPLAY_REVIEW_MANIFEST,
        "report": REPLAY_REVIEW_REPORT,
        "warnings": REPLAY_REVIEW_WARNINGS,
        "required": True,
    },
    "cost_sensitivity_review": {
        "dir_arg": "cost_sensitivity_review_dir",
        "csv": COST_REVIEW_CSV,
        "manifest": COST_REVIEW_MANIFEST,
        "report": COST_REVIEW_REPORT,
        "warnings": COST_REVIEW_WARNINGS,
        "required": True,
    },
    "recent_holdout_review": {
        "dir_arg": "recent_period_holdout_review_dir",
        "csv": HOLDOUT_REVIEW_CSV,
        "manifest": HOLDOUT_REVIEW_MANIFEST,
        "report": HOLDOUT_REVIEW_REPORT,
        "warnings": HOLDOUT_REVIEW_WARNINGS,
        "required": True,
    },
}

ACCEPTABLE_REPLAY_STATUS = {"continue_paper_validation"}
ACCEPTABLE_COST_STATUS = {"continue_paper_validation_with_cost_caveat"}
ACCEPTABLE_HOLDOUT_STATUS = {
    "continue_paper_validation_recent_period_ok",
    "continue_demo_readiness_planning_with_holdout_caveat",
}
BOUNDARY_FLAGS = (
    "no_broker_connection_performed",
    "no_order_execution_performed",
    "no_db_mutation_performed",
    "no_data_generation_performed",
    "no_feature_refresh_performed",
    "no_optimization_performed",
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
    "readiness_area",
    "readiness_status",
    "artifact_status",
    "source_path",
    "observed_value",
    "expected_value",
    "evidence_label",
    "caveat",
    "warning_code",
    "blocking_warning",
]

CHECKLIST_FIELDNAMES = [
    "run_id",
    "checklist_area",
    "checklist_item",
    "required_before",
    "check_status",
    "source_or_future_artifact",
    "blocking_if_failed",
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
        "checklist": output_dir / OUTPUT_CHECKLIST,
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


def source_dir(args: argparse.Namespace, key: str) -> Path:
    return Path(getattr(args, SOURCE_SPECS[key]["dir_arg"]))


def load_source_bundle(args: argparse.Namespace, key: str, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    spec = SOURCE_SPECS[key]
    root = source_dir(args, key)
    paths = {
        "dir": root,
        "csv": root / str(spec["csv"]),
        "manifest": root / str(spec["manifest"]),
        "report": root / str(spec["report"]),
        "warnings": root / str(spec["warnings"]),
    }
    missing = [name for name in ("csv", "manifest", "report", "warnings") if not paths[name].exists()]
    for name in missing:
        add_warning(
            warnings,
            args=args,
            warning_code=f"{key}_{name}_missing",
            message=f"Required source artifact is missing: {paths[name].name}",
            source=paths[name],
            blocking_warning=bool(spec["required"]) and name in {"csv", "manifest"},
        )
    rows, csv_error = read_csv_rows(paths["csv"])
    manifest, manifest_error = read_json(paths["manifest"])
    source_warning_rows, warnings_error = read_csv_rows(paths["warnings"])
    report = read_text(paths["report"])
    for name, error in [("csv", csv_error), ("manifest", manifest_error), ("warnings", warnings_error)]:
        if error:
            add_warning(
                warnings,
                args=args,
                warning_code=f"{key}_{name}_unreadable",
                message=f"Source artifact is unreadable: {error}",
                source=paths[name],
                blocking_warning=bool(spec["required"]) and name in {"csv", "manifest"},
            )
    for row in source_warning_rows:
        add_warning(
            warnings,
            args=args,
            warning_code=row.get("warning_code", f"{key}_source_warning"),
            message=row.get("message", "Source warning preserved."),
            source=row.get("source", paths["warnings"]),
            blocking_warning=str(row.get("blocking_warning", "")).lower() == "true",
            severity=row.get("severity") or "warning",
        )
    return {
        "key": key,
        "paths": paths,
        "rows": rows,
        "manifest": manifest,
        "report": report,
        "missing_count": len(missing),
        "unreadable_count": sum(1 for error in (csv_error, manifest_error, warnings_error) if error),
    }


def load_sources(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {key: load_source_bundle(args, key, warnings) for key in SOURCE_SPECS}


def boundary_flags_confirmed(manifests: list[dict[str, Any]]) -> bool:
    for manifest in manifests:
        for flag in BOUNDARY_FLAGS:
            if flag in manifest and manifest.get(flag) is not True:
                return False
    return True


def extract_first_number(text: Any) -> float | None:
    if not isinstance(text, str):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


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


def status_from_sources(sources: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        "replay_review_status": str(sources["replay_review"]["manifest"].get("review_status") or ""),
        "cost_sensitivity_review_status": str(sources["cost_sensitivity_review"]["manifest"].get("review_status") or ""),
        "recent_period_holdout_review_status": str(sources["recent_holdout_review"]["manifest"].get("review_status") or ""),
    }


def source_statuses_acceptable(statuses: dict[str, str]) -> bool:
    return (
        statuses["replay_review_status"] in ACCEPTABLE_REPLAY_STATUS
        and statuses["cost_sensitivity_review_status"] in ACCEPTABLE_COST_STATUS
        and statuses["recent_period_holdout_review_status"] in ACCEPTABLE_HOLDOUT_STATUS
    )


def readiness_status(
    *,
    config: dict[str, Any],
    boundaries: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    if not config:
        return "blocked_missing_required_artifact"
    if any(source["missing_count"] for source in sources.values()):
        return "blocked_missing_required_artifact"
    if not config_boundary_safe(boundaries):
        return "blocked_by_config_boundary"
    if any(source["unreadable_count"] for source in sources.values()) or blocking_warnings(warnings):
        return "blocked_unreadable_input"
    statuses = status_from_sources(sources)
    if statuses["replay_review_status"].startswith("hold") or statuses["recent_period_holdout_review_status"].startswith("hold"):
        return "hold_before_demo_readiness"
    if not source_statuses_acceptable(statuses):
        return "blocked_by_source_review_status"
    if not boundary_flags_confirmed([source["manifest"] for source in sources.values()]):
        return "blocked_by_source_review_status"
    return "demo_readiness_plan_available_with_caveats"


def recommended_next_step(status: str) -> str:
    if status == "demo_readiness_plan_available_with_caveats":
        return "build_fixed_candidate_demo_environment_check_plan"
    return "fix_blocking_demo_readiness_inputs"


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
        "readiness_area": area,
        "readiness_status": status,
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
    config: dict[str, Any],
    boundaries: dict[str, Any],
    sources: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    statuses = status_from_sources(sources)
    base_artifact_status = (
        "available_with_caveat"
        if status == "demo_readiness_plan_available_with_caveats"
        else "available"
        if status == "hold_before_demo_readiness"
        else "missing"
        if status == "blocked_missing_required_artifact"
        else "unreadable"
        if status == "blocked_unreadable_input"
        else "available_with_caveat"
    )
    exact_condition = nested_get(config, "entry_rule", "exact_condition") or ""
    candidate = nested_get(config, "candidate") or {}
    risk_note = nested_get(config, "demo_risk_controls", "risk_per_trade_note") or ""
    return [
        plan_row(
            args=args,
            area="source_artifact_chain",
            status=status,
            artifact_status=base_artifact_status,
            source_path=args.recent_period_holdout_review_dir,
            observed=statuses,
            expected="acceptable replay, cost, and recent holdout statuses",
            label="artifact_chain_available",
            caveat="source_reviews_are_inputs_not_demo_execution",
        ),
        plan_row(
            args=args,
            area="strategy_identity",
            status=status,
            artifact_status=base_artifact_status,
            source_path=args.demo_strategy_config,
            observed=f"{candidate.get('symbol')} {candidate.get('direction')} {candidate.get('timeframe')}",
            expected="GBPUSD short M15 fixed candidate",
            label="fixed_rule_evidence_available",
            caveat="strategy_identity_from_config",
        ),
        plan_row(
            args=args,
            area="fixed_rule_definition",
            status=status,
            artifact_status=base_artifact_status,
            source_path=args.demo_strategy_config,
            observed=exact_condition,
            expected="fixed exact rule preserved",
            label="fixed_rule_evidence_available",
            caveat="no_threshold_or_rule_change",
        ),
        plan_row(
            args=args,
            area="risk_controls",
            status=status,
            artifact_status=base_artifact_status,
            source_path=args.demo_strategy_config,
            observed=f"risk={risk_note};max_open_positions={boundaries['max_open_positions']}",
            expected="1 percent note and one open position",
            label="one_open_trade_rule_required",
            caveat="risk_controls_require_future_environment_check",
        ),
        plan_row(
            args=args,
            area="spread_policy",
            status=status,
            artifact_status=base_artifact_status,
            source_path=args.demo_strategy_config,
            observed={"spread_unit": boundaries["spread_unit"], "max_spread_points": boundaries["max_spread_points"]},
            expected="spread_unit=broker_points and max_spread_points=15.0",
            label="fixed_rule_evidence_available",
            caveat="spread_unit_alignment_requires_future_symbol_contract_check",
        ),
        plan_row(
            args=args,
            area="timeout_policy",
            status=status,
            artifact_status=base_artifact_status,
            source_path=args.demo_strategy_config,
            observed=nested_get(config, "risk_reward", "timeout_note"),
            expected="h10 timeout policy preserved",
            label="fixed_rule_evidence_available",
            caveat="timeout_fragility_caveat_preserved",
        ),
        plan_row(
            args=args,
            area="one_open_trade_rule",
            status=status,
            artifact_status=base_artifact_status,
            source_path=args.demo_strategy_config,
            observed=boundaries["max_open_positions"],
            expected="1",
            label="one_open_trade_rule_required",
            caveat="future implementation must reconcile state",
        ),
        plan_row(
            args=args,
            area="replay_evidence",
            status=status,
            artifact_status=base_artifact_status,
            source_path=sources["replay_review"]["paths"]["manifest"],
            observed=statuses["replay_review_status"],
            expected="continue_paper_validation",
            label="replay_review_positive",
            caveat="replay_evidence_not_future_performance_proof",
        ),
        plan_row(
            args=args,
            area="cost_sensitivity_caveat",
            status=status,
            artifact_status="available_with_caveat",
            source_path=sources["cost_sensitivity_review"]["paths"]["manifest"],
            observed=statuses["cost_sensitivity_review_status"],
            expected="continue_paper_validation_with_cost_caveat",
            label="cost_caveat_preserved",
            caveat="timeout_fragility_under_severe_and_stress_cost_assumptions",
        ),
        plan_row(
            args=args,
            area="recent_period_holdout",
            status=status,
            artifact_status=base_artifact_status,
            source_path=sources["recent_holdout_review"]["paths"]["manifest"],
            observed=statuses["recent_period_holdout_review_status"],
            expected="recent holdout acceptable or acceptable with caveat",
            label="recent_period_holdout_ok",
            caveat="recent_holdout_context_only",
        ),
        plan_row(
            args=args,
            area="broker_environment_checks_required",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.output_dir or "",
            observed="not_checked",
            expected="future separate environment check plan",
            label="demo_environment_check_required",
            caveat="no_broker_connection_performed",
        ),
        plan_row(
            args=args,
            area="account_safety_checks_required",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.output_dir or "",
            observed="not_checked",
            expected="future account safety check",
            label="demo_environment_check_required",
            caveat="must_confirm_demo_account_in_separate_future_artifact",
        ),
        plan_row(
            args=args,
            area="symbol_contract_checks_required",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.output_dir or "",
            observed="not_checked",
            expected="future symbol contract check",
            label="broker_symbol_contract_check_required",
            caveat="spread_point_lot_and_stop_level_units_unchecked",
        ),
        plan_row(
            args=args,
            area="execution_safety_checks_required",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.output_dir or "",
            observed="not_checked",
            expected="future dry-run/no-order execution check",
            label="execution_dry_run_required",
            caveat="no_order_execution_performed",
        ),
        plan_row(
            args=args,
            area="logging_and_audit_requirements",
            status=status,
            artifact_status=base_artifact_status,
            source_path=args.demo_strategy_config,
            observed="logging_fields_configured",
            expected="full audit log requirements preserved",
            label="audit_logging_required",
            caveat="future logger must preserve audit fields",
        ),
        plan_row(
            args=args,
            area="manual_operator_checklist",
            status=status,
            artifact_status="available_with_caveat",
            source_path=args.output_dir or "",
            observed="checklist_written",
            expected="manual checklist required before future environment work",
            label="kill_switch_required",
            caveat="manual_operator_review_required",
        ),
        plan_row(
            args=args,
            area="next_artifact_required",
            status=status,
            artifact_status="available",
            source_path=args.output_dir or "",
            observed=recommended_next_step(status),
            expected="future environment check plan only",
            label="demo_environment_check_required",
            caveat="no_trading_decision_made",
        ),
    ]


def checklist_row(
    args: argparse.Namespace,
    area: str,
    item: str,
    required_before: str,
    source_or_future_artifact: str,
    blocking_if_failed: bool = True,
    caveat: str = "future_manual_check_required",
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "checklist_area": area,
        "checklist_item": item,
        "required_before": required_before,
        "check_status": "not_checked_future_artifact_required",
        "source_or_future_artifact": source_or_future_artifact,
        "blocking_if_failed": blocking_if_failed,
        "caveat": caveat,
    }


def build_checklist_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    future_plan = "build_fixed_candidate_demo_environment_check_plan"
    return [
        checklist_row(args, "broker_environment", "confirm account is demo, not real", "any future demo broker connection", future_plan),
        checklist_row(args, "broker_environment", "confirm terminal/broker connection only in separate future check", "future environment check", future_plan),
        checklist_row(args, "symbol_contract", "confirm GBPUSD symbol visible/tradable in demo account", "future symbol contract check", future_plan),
        checklist_row(args, "symbol_contract", "confirm min lot, max lot, lot step", "future symbol contract check", future_plan),
        checklist_row(args, "symbol_contract", "confirm point/tick size", "future symbol contract check", future_plan),
        checklist_row(args, "symbol_contract", "confirm stop level and freeze level", "future symbol contract check", future_plan),
        checklist_row(args, "spread_policy", "confirm spread source and spread sanity", "future symbol contract check", future_plan),
        checklist_row(args, "spread_policy", "confirm max spread gate uses same units as broker symbol", "future symbol contract check", future_plan),
        checklist_row(args, "account_safety", "confirm volume/risk calculation uses demo balance only", "future account safety check", future_plan),
        checklist_row(args, "state_safety", "confirm one-open-trade enforcement", "future execution dry-run check", future_plan),
        checklist_row(args, "execution_safety", "confirm no duplicate order protection", "future execution dry-run check", future_plan),
        checklist_row(args, "execution_safety", "confirm SL/TP attached at placement", "future execution dry-run check", future_plan),
        checklist_row(args, "timeout_policy", "confirm timeout h10 closure logic", "future execution dry-run check", future_plan),
        checklist_row(args, "state_reconciliation", "confirm reconciliation between local state and broker state", "future state reconciliation check", future_plan),
        checklist_row(args, "state_reconciliation", "confirm crash/restart recovery", "future state reconciliation check", future_plan),
        checklist_row(args, "kill_switch", "confirm kill-switch behavior", "future kill-switch check", future_plan),
        checklist_row(args, "audit_logging", "confirm full audit log", "future logging check", future_plan),
        checklist_row(args, "execution_safety", "confirm dry-run/no-order execution test before any demo order", "future execution dry-run check", future_plan),
    ]


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    config = load_config(args, warnings)
    sources = load_sources(args, warnings)
    boundaries = config_boundaries(config)
    if config and not config_boundary_safe(boundaries):
        add_warning(
            warnings,
            args=args,
            warning_code="demo_config_boundary_unsafe",
            message="Demo strategy config does not satisfy required paper/demo safety boundaries.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    if sources and not boundary_flags_confirmed([source["manifest"] for source in sources.values()]):
        add_warning(
            warnings,
            args=args,
            warning_code="source_boundary_not_confirmed",
            message="One or more source manifests do not confirm the required no-execution boundary flags.",
            source=args.output_dir or "",
            blocking_warning=True,
        )
    status = readiness_status(config=config, boundaries=boundaries, sources=sources, warnings=warnings)
    plan_rows = build_plan_rows(args, status=status, config=config, boundaries=boundaries, sources=sources)
    checklist_rows = build_checklist_rows(args)
    write_csv(output_paths["plan"], plan_rows, PLAN_FIELDNAMES)
    write_csv(output_paths["checklist"], checklist_rows, CHECKLIST_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(
        output_paths["report"],
        args=args,
        config=config,
        boundaries=boundaries,
        sources=sources,
        status=status,
        checklist_rows=checklist_rows,
        warnings=warnings,
    )
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        config=config,
        boundaries=boundaries,
        sources=sources,
        status=status,
        checklist_rows=checklist_rows,
        warnings=warnings,
    )
    return {
        "readiness_status": status,
        "plan_rows": plan_rows,
        "checklist_rows": checklist_rows,
        "warnings": warnings,
        "config": config,
        "sources": sources,
    }


def checklist_blocking_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if bool(row.get("blocking_if_failed")))


def source_artifact_count(sources: dict[str, dict[str, Any]]) -> int:
    return sum(1 for source in sources.values() if source["paths"]["manifest"].exists())


def missing_source_artifact_count(sources: dict[str, dict[str, Any]]) -> int:
    return sum(source["missing_count"] for source in sources.values())


def unreadable_source_artifact_count(sources: dict[str, dict[str, Any]]) -> int:
    return sum(source["unreadable_count"] for source in sources.values())


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    config: dict[str, Any],
    boundaries: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    status: str,
    checklist_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    statuses = status_from_sources(sources)
    output = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "replay_review_dir": str(args.replay_review_dir),
        "cost_sensitivity_review_dir": str(args.cost_sensitivity_review_dir),
        "recent_period_holdout_review_dir": str(args.recent_period_holdout_review_dir),
        "readiness_status": status,
        "source_artifact_count": source_artifact_count(sources),
        "missing_source_artifact_count": missing_source_artifact_count(sources) + (0 if config else 1),
        "unreadable_source_artifact_count": unreadable_source_artifact_count(sources),
        "checklist_row_count": len(checklist_rows),
        "blocking_checklist_item_count": checklist_blocking_count(checklist_rows),
        "replay_review_status": statuses["replay_review_status"],
        "cost_sensitivity_review_status": statuses["cost_sensitivity_review_status"],
        "recent_period_holdout_review_status": statuses["recent_period_holdout_review_status"],
        "cost_caveat_preserved": True,
        "timeout_fragility_caveat_preserved": bool(sources["cost_sensitivity_review"]["manifest"].get("timeout_negative_under_severe"))
        or bool(sources["cost_sensitivity_review"]["manifest"].get("timeout_negative_under_stress")),
        "recent_holdout_ok": statuses["recent_period_holdout_review_status"] in ACCEPTABLE_HOLDOUT_STATUS,
        "demo_environment_unchecked": True,
        "broker_contract_unchecked": True,
        "execution_dry_run_not_performed": True,
        "recommended_next_step": recommended_next_step(status),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "config_paper_only": boundaries["paper_only"],
        "config_max_open_positions": boundaries["max_open_positions"],
        "config_max_risk_percent": boundaries["max_risk_percent"],
        "config_max_spread_points": boundaries["max_spread_points"],
        "config_spread_unit": boundaries["spread_unit"],
        "config_spread_policy_matches_canonical": boundaries["spread_policy_matches_canonical"],
        "spread_unit": boundaries["spread_unit"],
        "max_spread_points": boundaries["max_spread_points"],
        "spread_policy_matches_canonical": boundaries["spread_policy_matches_canonical"],
        "no_child_scripts_executed": True,
        "no_replay_rerun": True,
        "no_cost_sensitivity_rerun": True,
        "no_recent_holdout_rerun": True,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_optimization_performed": True,
        "no_stress_validation_executed": True,
        "no_walk_forward_validation_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    boundaries: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    status: str,
    checklist_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    statuses = status_from_sources(sources)
    lines = [
        "# Fixed Candidate Demo Readiness Plan",
        "",
        "Artifact-only demo readiness planning artifact.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation or feature refresh was performed.",
        "No replay, cost sensitivity, or recent holdout rerun was performed.",
        "No optimization or parameter search was performed.",
        "This plan is not future-performance proof.",
        "This plan is not demo broker approval.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- demo_strategy_spec_dir: `{args.demo_strategy_spec_dir}`",
        f"- replay_review_dir: `{args.replay_review_dir}`",
        f"- cost_sensitivity_review_dir: `{args.cost_sensitivity_review_dir}`",
        f"- recent_period_holdout_review_dir: `{args.recent_period_holdout_review_dir}`",
        "",
        "## Evidence Chain Summary",
        "",
        f"- replay_review_status: `{statuses['replay_review_status']}`",
        f"- cost_sensitivity_review_status: `{statuses['cost_sensitivity_review_status']}`",
        f"- recent_period_holdout_review_status: `{statuses['recent_period_holdout_review_status']}`",
        f"- timeout_fragility_caveat_preserved: `{bool_text(bool(sources['cost_sensitivity_review']['manifest'].get('timeout_negative_under_severe') or sources['cost_sensitivity_review']['manifest'].get('timeout_negative_under_stress')))}`",
        "",
        "## Risk/Config Summary",
        "",
        f"- candidate_id: `{config.get('candidate_id')}`",
        f"- symbol: `{nested_get(config, 'candidate', 'symbol')}`",
        f"- direction: `{nested_get(config, 'candidate', 'direction')}`",
        f"- timeframe: `{nested_get(config, 'candidate', 'timeframe')}`",
        f"- max_risk_percent_from_note: `{boundaries['max_risk_percent']}`",
        f"- max_open_positions_from_note: `{boundaries['max_open_positions']}`",
        f"- spread_unit: `{boundaries['spread_unit']}`",
        f"- max_spread_points: `{boundaries['max_spread_points']}`",
        f"- kill_switch_conditions_present: `{bool_text(bool(boundaries['kill_switch_conditions_present']))}`",
        "",
        "## Remaining Caveats",
        "",
        "- Demo environment has not been checked.",
        "- Broker symbol contract has not been checked.",
        "- Execution dry-run has not been performed.",
        "- Cost sensitivity timeout fragility remains preserved as a caveat.",
        "- This plan does not approve any demo broker action.",
        "",
        "## Checklist Summary",
        "",
        f"- checklist_rows: `{len(checklist_rows)}`",
        f"- blocking_if_failed: `{checklist_blocking_count(checklist_rows)}`",
        "",
        "## Readiness Status",
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
    path.write_text("\n".join(lines), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    build_artifacts(args, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build artifact-only demo readiness plan for the fixed candidate.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--replay-review-dir", type=Path, default=DEFAULT_REPLAY_REVIEW_DIR)
    parser.add_argument("--cost-sensitivity-review-dir", type=Path, default=DEFAULT_COST_SENSITIVITY_REVIEW_DIR)
    parser.add_argument("--recent-period-holdout-review-dir", type=Path, default=DEFAULT_RECENT_HOLDOUT_REVIEW_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate demo readiness plan failed: {exc}")
        return 1
    print("Fixed-candidate demo readiness plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
