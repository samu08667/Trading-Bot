"""Build an artifact-only review for fixed-candidate replay cost sensitivity.

This module reads completed cost/slippage sensitivity plan artifacts and
produces a conservative review artifact. It does not rerun replay, rerun the
sensitivity plan, query or mutate the database, run child scripts, refresh data,
connect to MT5, connect to broker/API services, execute orders, optimize
parameters, or make candidate-quality or trading decisions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_replay_cost_sensitivity_review"
DEFAULT_COST_SENSITIVITY_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_replay_cost_sensitivity_plan"
    / "gbpusd_short_h10_1_5_off_hours_replay_cost_sensitivity_plan_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_replay_cost_sensitivity_review"

SOURCE_MANIFEST = "fixed_candidate_replay_cost_sensitivity_plan_manifest.json"
SOURCE_REPORT = "fixed_candidate_replay_cost_sensitivity_plan_report.md"
SOURCE_PLAN = "fixed_candidate_replay_cost_sensitivity_plan.csv"
SOURCE_SCENARIOS = "fixed_candidate_replay_cost_sensitivity_plan_scenarios.csv"
SOURCE_OUTCOMES = "fixed_candidate_replay_cost_sensitivity_plan_outcomes.csv"
SOURCE_WARNINGS = "fixed_candidate_replay_cost_sensitivity_plan_warnings.csv"

OUTPUT_REVIEW = "fixed_candidate_replay_cost_sensitivity_review.csv"
OUTPUT_SCENARIOS = "fixed_candidate_replay_cost_sensitivity_review_scenarios.csv"
OUTPUT_OUTCOMES = "fixed_candidate_replay_cost_sensitivity_review_outcomes.csv"
OUTPUT_REPORT = "fixed_candidate_replay_cost_sensitivity_review_report.md"
OUTPUT_WARNINGS = "fixed_candidate_replay_cost_sensitivity_review_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_replay_cost_sensitivity_review_manifest.json"

EXPECTED_SOURCE_FILES = (
    SOURCE_MANIFEST,
    SOURCE_REPORT,
    SOURCE_PLAN,
    SOURCE_SCENARIOS,
    SOURCE_OUTCOMES,
    SOURCE_WARNINGS,
)
REQUIRED_SOURCE_FILES = (SOURCE_MANIFEST, SOURCE_PLAN, SOURCE_SCENARIOS, SOURCE_OUTCOMES)
REQUIRED_SCENARIO_COLUMNS = (
    "scenario_label",
    "extra_cost_R_per_trade",
    "adjusted_total_R",
    "adjusted_average_R",
    "adjusted_median_R",
    "adjusted_win_rate_R_positive",
    "adjusted_max_drawdown_R",
    "adjusted_longest_loss_streak",
    "adjusted_longest_win_streak",
    "scenario_status",
)
REQUIRED_OUTCOME_COLUMNS = (
    "scenario_label",
    "extra_cost_R_per_trade",
    "exit_reason",
    "trade_count",
    "gross_average_R",
    "adjusted_average_R",
    "adjusted_total_R",
    "adjusted_win_rate_R_positive",
)
SOURCE_BOUNDARY_FLAGS = (
    "no_replay_rerun",
    "no_broker_connection_performed",
    "no_order_execution_performed",
    "no_db_mutation_performed",
    "no_data_generation_performed",
    "no_feature_refresh_performed",
    "no_optimization_performed",
    "no_trading_decision_performed",
)

REVIEW_FIELDNAMES = [
    "run_id",
    "review_area",
    "review_status",
    "artifact_status",
    "source_path",
    "observed_value",
    "expected_value",
    "evidence_label",
    "caveat",
    "warning_code",
    "blocking_warning",
]

SCENARIO_REVIEW_FIELDNAMES = [
    "run_id",
    "scenario_label",
    "extra_cost_R_per_trade",
    "adjusted_total_R",
    "adjusted_average_R",
    "adjusted_median_R",
    "adjusted_win_rate_R_positive",
    "adjusted_max_drawdown_R",
    "adjusted_longest_loss_streak",
    "adjusted_longest_win_streak",
    "source_scenario_status",
    "review_label",
    "caveat",
]

OUTCOME_REVIEW_FIELDNAMES = [
    "run_id",
    "scenario_label",
    "extra_cost_R_per_trade",
    "exit_reason",
    "trade_count",
    "gross_average_R",
    "adjusted_average_R",
    "adjusted_total_R",
    "adjusted_win_rate_R_positive",
    "outcome_review_label",
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


def safe_int(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(float(value))
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
        "review": output_dir / OUTPUT_REVIEW,
        "scenarios": output_dir / OUTPUT_SCENARIOS,
        "outcomes": output_dir / OUTPUT_OUTCOMES,
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


def source_boundaries_confirmed(manifest: dict[str, Any]) -> bool:
    return all(manifest.get(flag) is True for flag in SOURCE_BOUNDARY_FLAGS if flag in manifest)


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    root = Path(args.cost_sensitivity_plan_dir)
    missing_count = 0
    missing_required_count = 0
    for name in EXPECTED_SOURCE_FILES:
        path = root / name
        if path.exists():
            continue
        missing_count += 1
        is_required = name in REQUIRED_SOURCE_FILES
        missing_required_count += 1 if is_required else 0
        add_warning(
            warnings,
            args=args,
            warning_code=f"source_{name}_missing",
            message=f"Source artifact is missing: {name}",
            source=path,
            blocking_warning=is_required,
        )
    manifest, manifest_error = read_json(root / SOURCE_MANIFEST)
    plan_rows, plan_error = read_csv_rows(root / SOURCE_PLAN)
    scenario_rows, scenario_error = read_csv_rows(root / SOURCE_SCENARIOS)
    outcome_rows, outcome_error = read_csv_rows(root / SOURCE_OUTCOMES)
    source_warnings, source_warnings_error = read_csv_rows(root / SOURCE_WARNINGS)
    unreadable_count = 0
    for name, error, required in [
        (SOURCE_MANIFEST, manifest_error, True),
        (SOURCE_PLAN, plan_error, True),
        (SOURCE_SCENARIOS, scenario_error, True),
        (SOURCE_OUTCOMES, outcome_error, True),
        (SOURCE_WARNINGS, source_warnings_error, False),
    ]:
        if error:
            unreadable_count += 1
            add_warning(
                warnings,
                args=args,
                warning_code=f"source_{name}_unreadable",
                message=f"Source artifact is unreadable: {error}",
                source=root / name,
                blocking_warning=required,
            )
    if scenario_rows and not set(REQUIRED_SCENARIO_COLUMNS).issubset(scenario_rows[0].keys()):
        unreadable_count += 1
        add_warning(
            warnings,
            args=args,
            warning_code="source_scenarios_csv_unreadable",
            message="Scenario CSV is missing required review columns.",
            source=root / SOURCE_SCENARIOS,
            blocking_warning=True,
        )
    if outcome_rows and not set(REQUIRED_OUTCOME_COLUMNS).issubset(outcome_rows[0].keys()):
        unreadable_count += 1
        add_warning(
            warnings,
            args=args,
            warning_code="source_outcomes_csv_unreadable",
            message="Outcome CSV is missing required review columns.",
            source=root / SOURCE_OUTCOMES,
            blocking_warning=True,
        )
    for row in source_warnings:
        add_warning(
            warnings,
            args=args,
            warning_code=row.get("warning_code", "source_cost_sensitivity_warning"),
            message=row.get("message", "Source cost sensitivity warning preserved."),
            source=row.get("source", root / SOURCE_WARNINGS),
            blocking_warning=str(row.get("blocking_warning", "")).lower() == "true",
            severity=row.get("severity") or "warning",
        )
    return {
        "manifest": manifest,
        "plan_rows": plan_rows,
        "scenario_rows": scenario_rows,
        "outcome_rows": outcome_rows,
        "source_warnings": source_warnings,
        "report": read_text(root / SOURCE_REPORT),
        "missing_source_artifact_count": missing_count,
        "missing_required_artifact_count": missing_required_count,
        "unreadable_source_artifact_count": unreadable_count,
    }


def scenario_by_label(scenario_rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    for row in scenario_rows:
        if row.get("scenario_label") == label:
            return row
    return {}


def outcome_by_label_and_reason(outcome_rows: list[dict[str, Any]], label: str, reason: str) -> dict[str, Any]:
    for row in outcome_rows:
        if row.get("scenario_label") == label and row.get("exit_reason") == reason:
            return row
    return {}


def count_scenario_status(scenario_rows: list[dict[str, Any]], status: str) -> int:
    return sum(1 for row in scenario_rows if row.get("scenario_status") == status)


def review_status(inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> str:
    if inputs["missing_required_artifact_count"]:
        return "blocked_missing_required_artifact"
    source_plan_status = str(inputs["manifest"].get("plan_status") or "")
    if source_plan_status.startswith("blocked"):
        return "blocked_by_source_plan_status"
    if inputs["unreadable_source_artifact_count"] or blocking_warnings(warnings):
        return "blocked_unreadable_input"
    medium = scenario_by_label(inputs["scenario_rows"], "medium")
    stress = scenario_by_label(inputs["scenario_rows"], "stress")
    medium_total = safe_float(medium.get("adjusted_total_R"))
    medium_average = safe_float(medium.get("adjusted_average_R"))
    stress_total = safe_float(stress.get("adjusted_total_R"))
    if medium_total is not None and medium_average is not None and stress_total is not None:
        if medium_total > 0 and medium_average > 0.25 and stress_total > 0:
            return "continue_paper_validation_with_cost_caveat"
    return "hold_for_cost_model_review"


def recommended_next_step(status: str) -> str:
    if status == "continue_paper_validation_with_cost_caveat":
        return "build_fixed_candidate_recent_period_holdout_review"
    if status == "hold_for_cost_model_review":
        return "inspect_cost_model_and_timeout_policy_before_demo_readiness"
    return "fix_missing_or_unreadable_artifacts"


def scenario_review_label(row: dict[str, Any]) -> str:
    label = str(row.get("scenario_label") or "")
    total = safe_float(row.get("adjusted_total_R"))
    average = safe_float(row.get("adjusted_average_R"))
    status = str(row.get("scenario_status") or "")
    if total is not None and total <= 0:
        return "scenario_negative_under_extra_cost"
    if label == "medium" and total is not None and average is not None and total > 0 and average > 0.25:
        return "medium_scenario_positive"
    if label == "stress" and total is not None and total > 0:
        return "stress_scenario_positive"
    if label in {"severe", "stress"} and status == "fragile_under_scenario":
        return "severe_stress_fragility_observed"
    return status or "scenario_reviewed"


def build_scenario_review_rows(args: argparse.Namespace, scenario_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in scenario_rows:
        source_status = str(row.get("scenario_status") or "")
        rows.append(
            {
                "run_id": args.run_id,
                "scenario_label": row.get("scenario_label"),
                "extra_cost_R_per_trade": row.get("extra_cost_R_per_trade"),
                "adjusted_total_R": row.get("adjusted_total_R"),
                "adjusted_average_R": row.get("adjusted_average_R"),
                "adjusted_median_R": row.get("adjusted_median_R"),
                "adjusted_win_rate_R_positive": row.get("adjusted_win_rate_R_positive"),
                "adjusted_max_drawdown_R": row.get("adjusted_max_drawdown_R"),
                "adjusted_longest_loss_streak": row.get("adjusted_longest_loss_streak"),
                "adjusted_longest_win_streak": row.get("adjusted_longest_win_streak"),
                "source_scenario_status": source_status,
                "review_label": scenario_review_label(row),
                "caveat": "timeout_cost_caveat_preserved"
                if source_status == "fragile_under_scenario"
                else "scenario_review_descriptive_only",
            }
        )
    return rows


def outcome_review_label(row: dict[str, Any]) -> str:
    reason = str(row.get("exit_reason") or "")
    scenario = str(row.get("scenario_label") or "")
    adjusted_average = safe_float(row.get("adjusted_average_R"))
    if reason == "paper_tp_hit" and adjusted_average is not None and adjusted_average > 0:
        return "tp_bucket_positive_under_scenario"
    if reason == "paper_sl_hit" and adjusted_average is not None and adjusted_average < 0:
        return "sl_bucket_negative_as_expected"
    if reason == "paper_timeout" and scenario in {"severe", "stress"} and adjusted_average is not None and adjusted_average < 0:
        return "timeout_bucket_fragile_under_severe_stress"
    if reason == "paper_timeout":
        return "timeout_bucket_reviewed"
    return "outcome_bucket_reviewed"


def build_outcome_review_rows(args: argparse.Namespace, outcome_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in outcome_rows:
        rows.append(
            {
                "run_id": args.run_id,
                "scenario_label": row.get("scenario_label"),
                "extra_cost_R_per_trade": row.get("extra_cost_R_per_trade"),
                "exit_reason": row.get("exit_reason"),
                "trade_count": row.get("trade_count"),
                "gross_average_R": row.get("gross_average_R"),
                "adjusted_average_R": row.get("adjusted_average_R"),
                "adjusted_total_R": row.get("adjusted_total_R"),
                "adjusted_win_rate_R_positive": row.get("adjusted_win_rate_R_positive"),
                "outcome_review_label": outcome_review_label(row),
                "caveat": "timeout_bucket_cost_fragility"
                if outcome_review_label(row) == "timeout_bucket_fragile_under_severe_stress"
                else "outcome_review_descriptive_only",
            }
        )
    return rows


def drawdown_expansion_ratio(scenario_rows: list[dict[str, Any]]) -> float | None:
    base = safe_float(scenario_by_label(scenario_rows, "base").get("adjusted_max_drawdown_R"))
    stress = safe_float(scenario_by_label(scenario_rows, "stress").get("adjusted_max_drawdown_R"))
    if base in (None, 0) or stress is None:
        return None
    return stress / base


def timeout_adjusted_average(outcome_rows: list[dict[str, Any]], label: str) -> float | None:
    return safe_float(outcome_by_label_and_reason(outcome_rows, label, "paper_timeout").get("adjusted_average_R"))


def review_row(
    *,
    args: argparse.Namespace,
    area: str,
    status: str,
    artifact_status: str,
    source_path: Path,
    observed_value: Any,
    expected_value: Any,
    evidence_label: str,
    caveat: str,
    warning_code: str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "review_area": area,
        "review_status": status,
        "artifact_status": artifact_status,
        "source_path": source_path,
        "observed_value": observed_value,
        "expected_value": expected_value,
        "evidence_label": evidence_label,
        "caveat": caveat,
        "warning_code": warning_code,
        "blocking_warning": blocking_warning,
    }


def build_review_rows(
    args: argparse.Namespace,
    inputs: dict[str, Any],
    status: str,
    scenario_review_rows: list[dict[str, Any]],
    outcome_review_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    root = Path(args.cost_sensitivity_plan_dir)
    scenarios = inputs["scenario_rows"]
    outcomes = inputs["outcome_rows"]
    medium = scenario_by_label(scenarios, "medium")
    severe = scenario_by_label(scenarios, "severe")
    stress = scenario_by_label(scenarios, "stress")
    artifact_status = (
        "available"
        if status in {"continue_paper_validation_with_cost_caveat", "hold_for_cost_model_review"}
        else "missing"
        if status == "blocked_missing_required_artifact"
        else "unreadable"
    )
    timeout_negative = [
        row["scenario_label"]
        for row in outcome_review_rows
        if row["outcome_review_label"] == "timeout_bucket_fragile_under_severe_stress"
    ]
    return [
        review_row(
            args=args,
            area="plan_context",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_MANIFEST,
            observed_value=inputs["manifest"].get("plan_status"),
            expected_value="cost_sensitivity_plan_available",
            evidence_label="cost_sensitivity_plan_available",
            caveat="source_plan_status_preserved",
        ),
        review_row(
            args=args,
            area="source_replay_context",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_MANIFEST,
            observed_value=f"trades={inputs['manifest'].get('source_trades_closed')};total_R={inputs['manifest'].get('source_total_R')}",
            expected_value="source replay metrics preserved",
            evidence_label="source_boundaries_confirmed" if source_boundaries_confirmed(inputs["manifest"]) else "",
            caveat="no_replay_rerun",
        ),
        review_row(
            args=args,
            area="scenario_robustness_review",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_SCENARIOS,
            observed_value=(
                f"robust={count_scenario_status(scenarios, 'robust_under_scenario')};"
                f"fragile={count_scenario_status(scenarios, 'fragile_under_scenario')};"
                f"negative={count_scenario_status(scenarios, 'negative_under_scenario')}"
            ),
            expected_value="medium and stress positive for continue status",
            evidence_label="severe_stress_fragility_observed"
            if count_scenario_status(scenarios, "fragile_under_scenario")
            else "medium_scenario_positive",
            caveat="scenario_statuses_are_cost_sensitivity_evidence_only",
        ),
        review_row(
            args=args,
            area="medium_cost_review",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_SCENARIOS,
            observed_value=f"total={medium.get('adjusted_total_R')};average={medium.get('adjusted_average_R')}",
            expected_value="medium adjusted_total_R > 0 and adjusted_average_R > 0.25",
            evidence_label="medium_scenario_positive",
            caveat="medium_extra_cost_review_only",
        ),
        review_row(
            args=args,
            area="severe_cost_review",
            status=status,
            artifact_status="available_with_caveat"
            if severe.get("scenario_status") == "fragile_under_scenario"
            else artifact_status,
            source_path=root / SOURCE_SCENARIOS,
            observed_value=f"total={severe.get('adjusted_total_R')};average={severe.get('adjusted_average_R')};status={severe.get('scenario_status')}",
            expected_value="severe reviewed with timeout caveat",
            evidence_label="severe_stress_fragility_observed"
            if severe.get("scenario_status") == "fragile_under_scenario"
            else "scenario_reviewed",
            caveat="timeout_cost_caveat_preserved"
            if severe.get("scenario_status") == "fragile_under_scenario"
            else "severe_extra_cost_review_only",
        ),
        review_row(
            args=args,
            area="stress_cost_review",
            status=status,
            artifact_status="available_with_caveat"
            if stress.get("scenario_status") == "fragile_under_scenario"
            else artifact_status,
            source_path=root / SOURCE_SCENARIOS,
            observed_value=f"total={stress.get('adjusted_total_R')};average={stress.get('adjusted_average_R')};status={stress.get('scenario_status')}",
            expected_value="stress adjusted_total_R > 0 for continue status",
            evidence_label="stress_scenario_positive"
            if (safe_float(stress.get("adjusted_total_R")) or 0) > 0
            else "hold_for_cost_model_review",
            caveat="stress_timeout_fragility_caveat"
            if stress.get("scenario_status") == "fragile_under_scenario"
            else "stress_extra_cost_review_only",
        ),
        review_row(
            args=args,
            area="timeout_fragility_review",
            status=status,
            artifact_status="available_with_caveat" if timeout_negative else artifact_status,
            source_path=root / SOURCE_OUTCOMES,
            observed_value=";".join(timeout_negative),
            expected_value="timeout severe/stress fragility identified if present",
            evidence_label="timeout_bucket_fragile_under_severe_stress" if timeout_negative else "timeout_bucket_reviewed",
            caveat="timeout_bucket_cost_fragility" if timeout_negative else "timeout_bucket_non_negative_under_default_scenarios",
        ),
        review_row(
            args=args,
            area="drawdown_expansion_review",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_SCENARIOS,
            observed_value=drawdown_expansion_ratio(scenarios),
            expected_value="stress drawdown expansion ratio computed when possible",
            evidence_label="drawdown_expands_under_stress",
            caveat="drawdown_expansion_is_descriptive",
        ),
        review_row(
            args=args,
            area="caveat_cost_model_review",
            status=status,
            artifact_status="available_with_caveat",
            source_path=root / SOURCE_REPORT,
            observed_value="cost model caveat preserved",
            expected_value="cost model review before demo broker readiness",
            evidence_label="cost_model_review_required_before_demo",
            caveat="cost_model_review_required_before_demo",
        ),
        review_row(
            args=args,
            area="caveat_not_future_proof",
            status=status,
            artifact_status="available_with_caveat",
            source_path=root / SOURCE_REPORT,
            observed_value="one replay cost sensitivity review",
            expected_value="not future-performance proof",
            evidence_label="cost_model_review_required_before_demo",
            caveat="no_candidate_approval_no_trading_decision",
        ),
        review_row(
            args=args,
            area="next_research_step",
            status=status,
            artifact_status="available",
            source_path=root,
            observed_value=recommended_next_step(status),
            expected_value="manual follow-up artifact only",
            evidence_label="recent_period_holdout_review_recommended"
            if status == "continue_paper_validation_with_cost_caveat"
            else "cost_model_review_required_before_demo",
            caveat="no_trading_decision_made",
        ),
    ]


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    inputs = load_inputs(args, warnings)
    if inputs["manifest"] and not source_boundaries_confirmed(inputs["manifest"]):
        add_warning(
            warnings,
            args=args,
            warning_code="source_boundary_not_confirmed",
            message="Cost sensitivity plan manifest does not confirm all expected boundary flags.",
            source=Path(args.cost_sensitivity_plan_dir) / SOURCE_MANIFEST,
            blocking_warning=True,
        )
    status = review_status(inputs, warnings)
    scenario_review_rows = [] if status.startswith("blocked") else build_scenario_review_rows(args, inputs["scenario_rows"])
    outcome_review_rows = [] if status.startswith("blocked") else build_outcome_review_rows(args, inputs["outcome_rows"])
    review_rows = build_review_rows(args, inputs, status, scenario_review_rows, outcome_review_rows)
    write_csv(output_paths["review"], review_rows, REVIEW_FIELDNAMES)
    write_csv(output_paths["scenarios"], scenario_review_rows, SCENARIO_REVIEW_FIELDNAMES)
    write_csv(output_paths["outcomes"], outcome_review_rows, OUTCOME_REVIEW_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(
        output_paths["report"],
        args=args,
        inputs=inputs,
        review_status_value=status,
        scenario_review_rows=scenario_review_rows,
        outcome_review_rows=outcome_review_rows,
        warnings=warnings,
    )
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        inputs=inputs,
        review_status_value=status,
        scenario_review_rows=scenario_review_rows,
        outcome_review_rows=outcome_review_rows,
        warnings=warnings,
    )
    return {
        "review_status": status,
        "review_rows": review_rows,
        "scenario_review_rows": scenario_review_rows,
        "outcome_review_rows": outcome_review_rows,
        "warnings": warnings,
        "inputs": inputs,
    }


def scenario_metric(scenario_rows: list[dict[str, Any]], label: str, field: str) -> float | None:
    return safe_float(scenario_by_label(scenario_rows, label).get(field))


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    inputs: dict[str, Any],
    review_status_value: str,
    scenario_review_rows: list[dict[str, Any]],
    outcome_review_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    scenarios = inputs["scenario_rows"]
    outcomes = inputs["outcome_rows"]
    timeout_severe = timeout_adjusted_average(outcomes, "severe")
    timeout_stress = timeout_adjusted_average(outcomes, "stress")
    output = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "cost_sensitivity_plan_dir": str(args.cost_sensitivity_plan_dir),
        "source_plan_manifest_path": str(Path(args.cost_sensitivity_plan_dir) / SOURCE_MANIFEST),
        "source_scenarios_path": str(Path(args.cost_sensitivity_plan_dir) / SOURCE_SCENARIOS),
        "source_outcomes_path": str(Path(args.cost_sensitivity_plan_dir) / SOURCE_OUTCOMES),
        "source_warnings_path": str(Path(args.cost_sensitivity_plan_dir) / SOURCE_WARNINGS),
        "review_status": review_status_value,
        "scenario_row_count": len(scenario_review_rows),
        "outcome_row_count": len(outcome_review_rows),
        "robust_under_scenario_count": count_scenario_status(scenarios, "robust_under_scenario"),
        "positive_but_degraded_count": count_scenario_status(scenarios, "positive_but_degraded"),
        "fragile_under_scenario_count": count_scenario_status(scenarios, "fragile_under_scenario"),
        "negative_under_scenario_count": count_scenario_status(scenarios, "negative_under_scenario"),
        "source_trades_closed": safe_int(inputs["manifest"].get("source_trades_closed")),
        "source_total_R": safe_float(inputs["manifest"].get("source_total_R")),
        "source_average_R": safe_float(inputs["manifest"].get("source_average_R")),
        "base_adjusted_total_R": scenario_metric(scenarios, "base", "adjusted_total_R"),
        "mild_adjusted_total_R": scenario_metric(scenarios, "mild", "adjusted_total_R"),
        "medium_adjusted_total_R": scenario_metric(scenarios, "medium", "adjusted_total_R"),
        "severe_adjusted_total_R": scenario_metric(scenarios, "severe", "adjusted_total_R"),
        "stress_adjusted_total_R": scenario_metric(scenarios, "stress", "adjusted_total_R"),
        "base_adjusted_average_R": scenario_metric(scenarios, "base", "adjusted_average_R"),
        "mild_adjusted_average_R": scenario_metric(scenarios, "mild", "adjusted_average_R"),
        "medium_adjusted_average_R": scenario_metric(scenarios, "medium", "adjusted_average_R"),
        "severe_adjusted_average_R": scenario_metric(scenarios, "severe", "adjusted_average_R"),
        "stress_adjusted_average_R": scenario_metric(scenarios, "stress", "adjusted_average_R"),
        "base_adjusted_max_drawdown_R": scenario_metric(scenarios, "base", "adjusted_max_drawdown_R"),
        "medium_adjusted_max_drawdown_R": scenario_metric(scenarios, "medium", "adjusted_max_drawdown_R"),
        "severe_adjusted_max_drawdown_R": scenario_metric(scenarios, "severe", "adjusted_max_drawdown_R"),
        "stress_adjusted_max_drawdown_R": scenario_metric(scenarios, "stress", "adjusted_max_drawdown_R"),
        "stress_drawdown_expansion_ratio": drawdown_expansion_ratio(scenarios),
        "timeout_trade_count": safe_int(inputs["manifest"].get("timeout_trade_count")),
        "timeout_gross_average_R": safe_float(inputs["manifest"].get("timeout_gross_average_R")),
        "timeout_medium_adjusted_average_R": timeout_adjusted_average(outcomes, "medium"),
        "timeout_severe_adjusted_average_R": timeout_severe,
        "timeout_stress_adjusted_average_R": timeout_stress,
        "timeout_negative_under_severe": timeout_severe is not None and timeout_severe < 0,
        "timeout_negative_under_stress": timeout_stress is not None and timeout_stress < 0,
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "missing_source_artifact_count": inputs["missing_source_artifact_count"],
        "unreadable_source_artifact_count": inputs["unreadable_source_artifact_count"],
        "recommended_next_step": recommended_next_step(review_status_value),
        "no_child_scripts_executed": True,
        "no_replay_rerun": True,
        "no_sensitivity_plan_rerun": True,
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
    inputs: dict[str, Any],
    review_status_value: str,
    scenario_review_rows: list[dict[str, Any]],
    outcome_review_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    scenarios = inputs["scenario_rows"]
    timeout_negative = [
        row
        for row in outcome_review_rows
        if row["outcome_review_label"] == "timeout_bucket_fragile_under_severe_stress"
    ]
    lines = [
        "# Fixed Candidate Replay Cost Sensitivity Review",
        "",
        "Artifact-only cost sensitivity review. This module did not rerun the replay.",
        "This module did not rerun the cost sensitivity plan.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation or feature refresh was performed.",
        "No optimization or parameter search was performed.",
        "This review is not future-performance proof.",
        "This review is not candidate approval or demo broker readiness.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- cost_sensitivity_plan_dir: `{args.cost_sensitivity_plan_dir}`",
        f"- source_manifest: `{Path(args.cost_sensitivity_plan_dir) / SOURCE_MANIFEST}`",
        f"- source_scenarios: `{Path(args.cost_sensitivity_plan_dir) / SOURCE_SCENARIOS}`",
        f"- source_outcomes: `{Path(args.cost_sensitivity_plan_dir) / SOURCE_OUTCOMES}`",
        "",
        "## Scenario Robustness Summary",
        "",
        f"- robust_under_scenario_count: `{count_scenario_status(scenarios, 'robust_under_scenario')}`",
        f"- fragile_under_scenario_count: `{count_scenario_status(scenarios, 'fragile_under_scenario')}`",
        f"- negative_under_scenario_count: `{count_scenario_status(scenarios, 'negative_under_scenario')}`",
        "",
        "## Scenario Table",
        "",
    ]
    for row in scenario_review_rows:
        lines.append(
            "- "
            f"{row['scenario_label']}: adjusted_total_R={row['adjusted_total_R']}, "
            f"adjusted_average_R={row['adjusted_average_R']}, "
            f"adjusted_max_drawdown_R={row['adjusted_max_drawdown_R']}, "
            f"source_status={row['source_scenario_status']}, review_label={row['review_label']}"
        )
    lines.extend(["", "## Outcome Sensitivity Summary", ""])
    for row in outcome_review_rows:
        lines.append(
            "- "
            f"{row['scenario_label']} / {row['exit_reason']}: "
            f"adjusted_average_R={row['adjusted_average_R']}, "
            f"adjusted_total_R={row['adjusted_total_R']}, "
            f"label={row['outcome_review_label']}"
        )
    lines.extend(
        [
            "",
            "## Timeout Fragility Review",
            "",
            f"- timeout severe/stress negative rows: `{';'.join(row['scenario_label'] for row in timeout_negative)}`",
            "",
            "## Drawdown Expansion Review",
            "",
            f"- stress_drawdown_expansion_ratio: `{drawdown_expansion_ratio(scenarios)}`",
            "",
            "## Caveats",
            "",
            "- Cost sensitivity is a fixed extra-R transform of existing replay results.",
            "- Timeout outcomes are fragile under severe/stress cost assumptions when their adjusted average is negative.",
            "- Recent-period holdout review remains separate.",
            "- No candidate-quality decision was made.",
            "",
            "## Review Status",
            "",
            f"`{review_status_value}`",
            "",
            "## Recommended Next Step",
            "",
            f"`{recommended_next_step(review_status_value)}`",
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
    parser = argparse.ArgumentParser(description="Build artifact-only review for fixed-candidate replay cost sensitivity plan.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--cost-sensitivity-plan-dir", type=Path, default=DEFAULT_COST_SENSITIVITY_PLAN_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate replay cost sensitivity review failed: {exc}")
        return 1
    print("Fixed-candidate replay cost sensitivity review complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
