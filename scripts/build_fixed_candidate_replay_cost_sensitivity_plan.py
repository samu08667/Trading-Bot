"""Build an artifact-only cost/slippage sensitivity plan for fixed-rule replay results.

This module reads completed fixed-rule replay review and replay artifacts, then
estimates fixed extra-cost impacts in R per trade. It does not rerun the replay,
query or mutate the database, run child scripts, refresh data, connect to MT5,
connect to broker/API services, execute orders, optimize parameters, or make
candidate-quality or trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_replay_cost_sensitivity_plan"
DEFAULT_REPLAY_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_fixed_rule_replay_backtest_review"
    / "gbpusd_short_h10_1_5_off_hours_fixed_rule_replay_backtest_review_v1"
)
DEFAULT_REPLAY_BACKTEST_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_fixed_rule_replay_backtest"
    / "gbpusd_short_h10_1_5_off_hours_fixed_rule_replay_full_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_replay_cost_sensitivity_plan"
DEFAULT_EXTRA_COST_SCENARIOS = [0.00, 0.05, 0.10, 0.20, 0.30]

REVIEW_MANIFEST = "fixed_candidate_fixed_rule_replay_backtest_review_manifest.json"
REVIEW_REPORT = "fixed_candidate_fixed_rule_replay_backtest_review_report.md"
REVIEW_CSV = "fixed_candidate_fixed_rule_replay_backtest_review.csv"
REVIEW_YEARLY = "fixed_candidate_fixed_rule_replay_backtest_review_yearly.csv"
REVIEW_MONTHLY = "fixed_candidate_fixed_rule_replay_backtest_review_monthly.csv"
REVIEW_OUTCOMES = "fixed_candidate_fixed_rule_replay_backtest_review_outcomes.csv"
REVIEW_WARNINGS = "fixed_candidate_fixed_rule_replay_backtest_review_warnings.csv"

REPLAY_MANIFEST = "fixed_candidate_fixed_rule_replay_backtest_manifest.json"
REPLAY_TRADES = "fixed_candidate_fixed_rule_replay_backtest_trades.csv"
REPLAY_EQUITY = "fixed_candidate_fixed_rule_replay_backtest_equity.csv"
REPLAY_WARNINGS = "fixed_candidate_fixed_rule_replay_backtest_warnings.csv"

OUTPUT_PLAN = "fixed_candidate_replay_cost_sensitivity_plan.csv"
OUTPUT_SCENARIOS = "fixed_candidate_replay_cost_sensitivity_plan_scenarios.csv"
OUTPUT_OUTCOMES = "fixed_candidate_replay_cost_sensitivity_plan_outcomes.csv"
OUTPUT_REPORT = "fixed_candidate_replay_cost_sensitivity_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_replay_cost_sensitivity_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_replay_cost_sensitivity_plan_manifest.json"

REVIEW_EXPECTED_FILES = (
    REVIEW_MANIFEST,
    REVIEW_REPORT,
    REVIEW_CSV,
    REVIEW_YEARLY,
    REVIEW_MONTHLY,
    REVIEW_OUTCOMES,
    REVIEW_WARNINGS,
)
REVIEW_REQUIRED_FILES = (REVIEW_MANIFEST,)
REPLAY_EXPECTED_FILES = (REPLAY_MANIFEST, REPLAY_TRADES, REPLAY_EQUITY, REPLAY_WARNINGS)
REPLAY_REQUIRED_FILES = (REPLAY_MANIFEST, REPLAY_TRADES)
REQUIRED_TRADE_COLUMNS = ("exit_reason", "R_multiple")

BOUNDARY_FLAGS = (
    "no_broker_connection_performed",
    "no_order_execution_performed",
    "no_db_mutation_performed",
    "no_data_generation_performed",
    "no_feature_refresh_performed",
    "no_optimization_performed",
    "no_trading_decision_performed",
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

SCENARIO_FIELDNAMES = [
    "run_id",
    "scenario_label",
    "extra_cost_R_per_trade",
    "trades_closed",
    "gross_total_R",
    "total_extra_cost_R",
    "adjusted_total_R",
    "adjusted_average_R",
    "adjusted_median_R",
    "adjusted_min_R",
    "adjusted_max_R",
    "adjusted_win_rate_R_positive",
    "adjusted_trades_positive_count",
    "adjusted_trades_negative_count",
    "adjusted_trades_zero_count",
    "adjusted_max_drawdown_R",
    "adjusted_longest_loss_streak",
    "adjusted_longest_win_streak",
    "scenario_status",
    "caveat",
]

OUTCOME_FIELDNAMES = [
    "run_id",
    "scenario_label",
    "extra_cost_R_per_trade",
    "exit_reason",
    "trade_count",
    "gross_total_R",
    "gross_average_R",
    "adjusted_total_R",
    "adjusted_average_R",
    "adjusted_win_rate_R_positive",
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
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        return [], str(exc)
    return rows, ""


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


def scenario_label(extra_cost: float, used: set[str] | None = None) -> str:
    labels = {
        0.00: "base",
        0.05: "mild",
        0.10: "medium",
        0.20: "severe",
        0.30: "stress",
    }
    rounded = round(float(extra_cost), 10)
    label = labels.get(rounded, f"cost_{str(rounded).replace('.', '_')}R")
    if used is not None and label in used:
        suffix = 2
        while f"{label}_{suffix}" in used:
            suffix += 1
        label = f"{label}_{suffix}"
    if used is not None:
        used.add(label)
    return label


def longest_streak(values: list[float], *, positive: bool) -> int:
    longest = 0
    current = 0
    for value in values:
        hit = value > 0 if positive else value < 0
        if hit:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def max_drawdown_from_r(values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
    return max_drawdown


def classify_scenario(adjusted_values: list[float], timeout_adjusted_average: float | None) -> str:
    if not adjusted_values:
        return "context_only"
    adjusted_total = sum(adjusted_values)
    adjusted_average = statistics.mean(adjusted_values)
    adjusted_drawdown = max_drawdown_from_r(adjusted_values)
    if adjusted_total <= 0:
        return "negative_under_scenario"
    if timeout_adjusted_average is not None and timeout_adjusted_average < 0:
        return "fragile_under_scenario"
    if adjusted_average > 0.25 and math.isfinite(adjusted_drawdown):
        return "robust_under_scenario"
    if adjusted_average > 0:
        return "positive_but_degraded"
    return "context_only"


def outcome_values(trades: list[dict[str, Any]], exit_reason: str) -> list[float]:
    values: list[float] = []
    for row in trades:
        if row.get("exit_reason") == exit_reason:
            value = safe_float(row.get("R_multiple"))
            if value is not None:
                values.append(value)
    return values


def required_file_status(
    *,
    args: argparse.Namespace,
    root: Path,
    expected: tuple[str, ...],
    required: tuple[str, ...],
    warnings: list[dict[str, Any]],
    source_role: str,
) -> tuple[int, int]:
    missing_count = 0
    missing_required_count = 0
    for name in expected:
        path = root / name
        if path.exists():
            continue
        missing_count += 1
        is_required = name in required
        missing_required_count += 1 if is_required else 0
        add_warning(
            warnings,
            args=args,
            warning_code=f"{source_role}_{name}_missing",
            message=f"Source artifact is missing: {name}",
            source=path,
            blocking_warning=is_required,
        )
    return missing_count, missing_required_count


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    review_dir = Path(args.replay_review_dir)
    replay_dir = Path(args.replay_backtest_dir)
    review_missing, review_required_missing = required_file_status(
        args=args,
        root=review_dir,
        expected=REVIEW_EXPECTED_FILES,
        required=REVIEW_REQUIRED_FILES,
        warnings=warnings,
        source_role="review",
    )
    replay_missing, replay_required_missing = required_file_status(
        args=args,
        root=replay_dir,
        expected=REPLAY_EXPECTED_FILES,
        required=REPLAY_REQUIRED_FILES,
        warnings=warnings,
        source_role="replay",
    )
    review_manifest, review_manifest_error = read_json(review_dir / REVIEW_MANIFEST)
    replay_manifest, replay_manifest_error = read_json(replay_dir / REPLAY_MANIFEST)
    review_rows, review_rows_error = read_csv_rows(review_dir / REVIEW_CSV)
    review_yearly, review_yearly_error = read_csv_rows(review_dir / REVIEW_YEARLY)
    review_monthly, review_monthly_error = read_csv_rows(review_dir / REVIEW_MONTHLY)
    review_outcomes, review_outcomes_error = read_csv_rows(review_dir / REVIEW_OUTCOMES)
    review_warning_rows, review_warnings_error = read_csv_rows(review_dir / REVIEW_WARNINGS)
    trades, trades_error = read_csv_rows(replay_dir / REPLAY_TRADES)
    equity, equity_error = read_csv_rows(replay_dir / REPLAY_EQUITY)
    replay_warning_rows, replay_warnings_error = read_csv_rows(replay_dir / REPLAY_WARNINGS)
    unreadable_count = 0
    for name, error, required, source_role, root in [
        (REVIEW_MANIFEST, review_manifest_error, True, "review", review_dir),
        (REPLAY_MANIFEST, replay_manifest_error, True, "replay", replay_dir),
        (REVIEW_CSV, review_rows_error, False, "review", review_dir),
        (REVIEW_YEARLY, review_yearly_error, False, "review", review_dir),
        (REVIEW_MONTHLY, review_monthly_error, False, "review", review_dir),
        (REVIEW_OUTCOMES, review_outcomes_error, False, "review", review_dir),
        (REVIEW_WARNINGS, review_warnings_error, False, "review", review_dir),
        (REPLAY_TRADES, trades_error, True, "replay", replay_dir),
        (REPLAY_EQUITY, equity_error, False, "replay", replay_dir),
        (REPLAY_WARNINGS, replay_warnings_error, False, "replay", replay_dir),
    ]:
        if error:
            unreadable_count += 1
            add_warning(
                warnings,
                args=args,
                warning_code=f"{source_role}_{name}_unreadable",
                message=f"Source artifact is unreadable: {error}",
                source=root / name,
                blocking_warning=required,
            )
    if trades and not set(REQUIRED_TRADE_COLUMNS).issubset(trades[0].keys()):
        unreadable_count += 1
        add_warning(
            warnings,
            args=args,
            warning_code="replay_trades_csv_unreadable",
            message="Trades CSV is missing required sensitivity columns.",
            source=replay_dir / REPLAY_TRADES,
            blocking_warning=True,
        )
    for source_path, rows in [
        (review_dir / REVIEW_WARNINGS, review_warning_rows),
        (replay_dir / REPLAY_WARNINGS, replay_warning_rows),
    ]:
        for row in rows:
            add_warning(
                warnings,
                args=args,
                warning_code=row.get("warning_code", "source_warning"),
                message=row.get("message", "Source warning preserved."),
                source=row.get("source", source_path),
                blocking_warning=str(row.get("blocking_warning", "")).lower() == "true",
                severity=row.get("severity") or "warning",
            )
    return {
        "review_manifest": review_manifest,
        "replay_manifest": replay_manifest,
        "review_rows": review_rows,
        "review_yearly": review_yearly,
        "review_monthly": review_monthly,
        "review_outcomes": review_outcomes,
        "trades": trades,
        "equity": equity,
        "review_report": read_text(review_dir / REVIEW_REPORT),
        "missing_source_artifact_count": review_missing + replay_missing,
        "missing_required_artifact_count": review_required_missing + replay_required_missing,
        "unreadable_source_artifact_count": unreadable_count,
    }


def source_boundaries_confirmed(review_manifest: dict[str, Any], replay_manifest: dict[str, Any]) -> bool:
    for manifest in [review_manifest, replay_manifest]:
        for flag in BOUNDARY_FLAGS:
            if flag in manifest and manifest.get(flag) is not True:
                return False
    return True


def source_review_plan_status(inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> str:
    if inputs["missing_required_artifact_count"]:
        return "blocked_missing_required_artifact"
    review_status = str(inputs["review_manifest"].get("review_status") or "")
    if review_status.startswith("blocked"):
        return "blocked_by_source_review_status"
    if inputs["unreadable_source_artifact_count"] or blocking_warnings(warnings):
        return "blocked_unreadable_input"
    if review_status == "hold_for_more_validation":
        return "cost_sensitivity_plan_available_with_caveat"
    return "cost_sensitivity_plan_available"


def r_values(trades: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for row in trades:
        value = safe_float(row.get("R_multiple"))
        if value is not None:
            values.append(value)
    return values


def build_scenario_rows(args: argparse.Namespace, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = r_values(trades)
    gross_total = sum(values)
    rows: list[dict[str, Any]] = []
    used_labels: set[str] = set()
    timeout_values = outcome_values(trades, "paper_timeout")
    for extra_cost in args.extra_cost_r_scenarios:
        cost = float(extra_cost)
        label = scenario_label(cost, used_labels)
        adjusted_values = [value - cost for value in values]
        timeout_adjusted_values = [value - cost for value in timeout_values]
        timeout_adjusted_average = statistics.mean(timeout_adjusted_values) if timeout_adjusted_values else None
        total_extra_cost = len(values) * cost
        adjusted_total = sum(adjusted_values)
        scenario_status = classify_scenario(adjusted_values, timeout_adjusted_average)
        rows.append(
            {
                "run_id": args.run_id,
                "scenario_label": label,
                "extra_cost_R_per_trade": cost,
                "trades_closed": len(values),
                "gross_total_R": gross_total,
                "total_extra_cost_R": total_extra_cost,
                "adjusted_total_R": adjusted_total,
                "adjusted_average_R": statistics.mean(adjusted_values) if adjusted_values else None,
                "adjusted_median_R": statistics.median(adjusted_values) if adjusted_values else None,
                "adjusted_min_R": min(adjusted_values) if adjusted_values else None,
                "adjusted_max_R": max(adjusted_values) if adjusted_values else None,
                "adjusted_win_rate_R_positive": (
                    sum(1 for value in adjusted_values if value > 0) / len(adjusted_values) if adjusted_values else None
                ),
                "adjusted_trades_positive_count": sum(1 for value in adjusted_values if value > 0),
                "adjusted_trades_negative_count": sum(1 for value in adjusted_values if value < 0),
                "adjusted_trades_zero_count": sum(1 for value in adjusted_values if value == 0),
                "adjusted_max_drawdown_R": max_drawdown_from_r(adjusted_values),
                "adjusted_longest_loss_streak": longest_streak(adjusted_values, positive=False),
                "adjusted_longest_win_streak": longest_streak(adjusted_values, positive=True),
                "scenario_status": scenario_status,
                "caveat": (
                    "timeout_adjusted_average_below_zero"
                    if timeout_adjusted_average is not None and timeout_adjusted_average < 0
                    else "fixed_extra_cost_estimate_only"
                ),
            }
        )
    return rows


def build_outcome_rows(args: argparse.Namespace, trades: list[dict[str, Any]], scenario_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in trades:
        value = safe_float(row.get("R_multiple"))
        if value is not None:
            grouped[str(row.get("exit_reason") or "unknown")].append(value)
    rows: list[dict[str, Any]] = []
    for scenario in scenario_rows:
        cost = float(scenario["extra_cost_R_per_trade"])
        for reason in sorted(grouped):
            values = grouped[reason]
            adjusted_values = [value - cost for value in values]
            adjusted_average = statistics.mean(adjusted_values) if adjusted_values else None
            rows.append(
                {
                    "run_id": args.run_id,
                    "scenario_label": scenario["scenario_label"],
                    "extra_cost_R_per_trade": cost,
                    "exit_reason": reason,
                    "trade_count": len(values),
                    "gross_total_R": sum(values),
                    "gross_average_R": statistics.mean(values) if values else None,
                    "adjusted_total_R": sum(adjusted_values),
                    "adjusted_average_R": adjusted_average,
                    "adjusted_win_rate_R_positive": (
                        sum(1 for value in adjusted_values if value > 0) / len(adjusted_values)
                        if adjusted_values
                        else None
                    ),
                    "caveat": (
                        "timeout_bucket_negative_under_extra_cost"
                        if reason == "paper_timeout" and adjusted_average is not None and adjusted_average < 0
                        else "outcome_sensitivity_estimate_only"
                    ),
                }
            )
    return rows


def adjusted_value_for_label(scenario_rows: list[dict[str, Any]], label: str, field: str) -> float | None:
    for row in scenario_rows:
        if row["scenario_label"] == label:
            return safe_float(row.get(field))
    return None


def recommended_next_step(scenario_rows: list[dict[str, Any]], plan_status: str) -> str:
    if plan_status.startswith("blocked"):
        return "fix_missing_or_unreadable_artifacts"
    medium_total = adjusted_value_for_label(scenario_rows, "medium", "adjusted_total_R")
    severe_total = adjusted_value_for_label(scenario_rows, "severe", "adjusted_total_R")
    if medium_total is not None and severe_total is not None and medium_total > 0 and severe_total > 0:
        return "build_fixed_candidate_replay_cost_sensitivity_review"
    return "hold_for_cost_model_review"


def plan_row(
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
        "plan_area": area,
        "plan_status": status,
        "artifact_status": artifact_status,
        "source_path": source_path,
        "observed_value": observed_value,
        "expected_value": expected_value,
        "evidence_label": evidence_label,
        "caveat": caveat,
        "warning_code": warning_code,
        "blocking_warning": blocking_warning,
    }


def build_plan_rows(
    args: argparse.Namespace,
    inputs: dict[str, Any],
    scenario_rows: list[dict[str, Any]],
    outcome_rows: list[dict[str, Any]],
    status: str,
) -> list[dict[str, Any]]:
    review_dir = Path(args.replay_review_dir)
    replay_dir = Path(args.replay_backtest_dir)
    artifact_status = (
        "available_with_caveat"
        if status == "cost_sensitivity_plan_available_with_caveat"
        else "available"
        if status == "cost_sensitivity_plan_available"
        else "missing"
        if status == "blocked_missing_required_artifact"
        else "unreadable"
    )
    timeout_negative_labels = sorted(
        {
            row["scenario_label"]
            for row in outcome_rows
            if row["exit_reason"] == "paper_timeout" and (safe_float(row.get("adjusted_average_R")) or 0) < 0
        }
    )
    rows = [
        plan_row(
            args=args,
            area="replay_review_gate",
            status=status,
            artifact_status=artifact_status,
            source_path=review_dir / REVIEW_MANIFEST,
            observed_value=inputs["review_manifest"].get("review_status"),
            expected_value="continue_paper_validation or hold_for_more_validation",
            evidence_label="replay_review_available",
            caveat=(
                "source_review_hold_status_preserved"
                if inputs["review_manifest"].get("review_status") == "hold_for_more_validation"
                else "source_review_status_preserved"
            ),
            warning_code="source_review_hold_for_more_validation"
            if inputs["review_manifest"].get("review_status") == "hold_for_more_validation"
            else "",
            blocking_warning=False,
        ),
        plan_row(
            args=args,
            area="replay_trades_gate",
            status=status,
            artifact_status=artifact_status,
            source_path=replay_dir / REPLAY_TRADES,
            observed_value=len(inputs["trades"]),
            expected_value="closed trades CSV available",
            evidence_label="replay_trades_available",
            caveat="existing_trade_list_used_no_replay_rerun",
        ),
        plan_row(
            args=args,
            area="source_boundaries_confirmed",
            status=status,
            artifact_status=artifact_status,
            source_path=replay_dir / REPLAY_MANIFEST,
            observed_value=source_boundaries_confirmed(inputs["review_manifest"], inputs["replay_manifest"]),
            expected_value="artifact boundary flags true where present",
            evidence_label="source_boundaries_confirmed",
            caveat="no_replay_rerun",
        ),
        plan_row(
            args=args,
            area="cost_scenarios_defined",
            status=status,
            artifact_status="available",
            source_path=Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id,
            observed_value=";".join(row["scenario_label"] for row in scenario_rows),
            expected_value="base;mild;medium;severe;stress by default",
            evidence_label="cost_scenarios_defined",
            caveat="fixed_extra_cost_R_per_trade_only",
        ),
        plan_row(
            args=args,
            area="scenario_impact_estimated",
            status=status,
            artifact_status=artifact_status,
            source_path=replay_dir / REPLAY_TRADES,
            observed_value=f"scenario_count={len(scenario_rows)}",
            expected_value="adjusted R metrics written for each scenario",
            evidence_label="scenario_impact_estimated",
            caveat="aggregate_estimate_without_replay_rerun",
        ),
        plan_row(
            args=args,
            area="timeout_fragility_reviewed",
            status=status,
            artifact_status="available_with_caveat" if timeout_negative_labels else "available",
            source_path=replay_dir / REPLAY_TRADES,
            observed_value=";".join(timeout_negative_labels),
            expected_value="timeout bucket reviewed under extra cost scenarios",
            evidence_label="timeout_fragility_reviewed",
            caveat="timeout_fragility_under_extra_cost" if timeout_negative_labels else "timeout_bucket_remained_non_negative",
        ),
        plan_row(
            args=args,
            area="next_research_step",
            status=status,
            artifact_status="available",
            source_path=Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id,
            observed_value=recommended_next_step(scenario_rows, status),
            expected_value="manual follow-up artifact only",
            evidence_label="no_trading_decision_made",
            caveat="no_candidate_or_trading_decision",
        ),
    ]
    return rows


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    inputs = load_inputs(args, warnings)
    if inputs["review_manifest"] and inputs["review_manifest"].get("review_status") == "hold_for_more_validation":
        add_warning(
            warnings,
            args=args,
            warning_code="source_review_hold_for_more_validation",
            message="Source replay review status is hold_for_more_validation; sensitivity plan remains descriptive with caveat.",
            source=Path(args.replay_review_dir) / REVIEW_MANIFEST,
            blocking_warning=False,
        )
    if inputs["review_manifest"] and inputs["review_manifest"].get("review_status", "").startswith("blocked"):
        add_warning(
            warnings,
            args=args,
            warning_code="source_review_status_blocked",
            message="Source replay review status is blocked, so cost sensitivity planning is blocked.",
            source=Path(args.replay_review_dir) / REVIEW_MANIFEST,
            blocking_warning=True,
        )
    if inputs["review_manifest"] and inputs["replay_manifest"] and not source_boundaries_confirmed(
        inputs["review_manifest"], inputs["replay_manifest"]
    ):
        add_warning(
            warnings,
            args=args,
            warning_code="source_boundary_not_confirmed",
            message="Source manifests do not confirm all required boundary flags where present.",
            source=Path(args.replay_backtest_dir) / REPLAY_MANIFEST,
            blocking_warning=True,
        )
    status = source_review_plan_status(inputs, warnings)
    scenario_rows = [] if status.startswith("blocked") else build_scenario_rows(args, inputs["trades"])
    outcome_rows = [] if status.startswith("blocked") else build_outcome_rows(args, inputs["trades"], scenario_rows)
    plan_rows = build_plan_rows(args, inputs, scenario_rows, outcome_rows, status)
    write_csv(output_paths["plan"], plan_rows, PLAN_FIELDNAMES)
    write_csv(output_paths["scenarios"], scenario_rows, SCENARIO_FIELDNAMES)
    write_csv(output_paths["outcomes"], outcome_rows, OUTCOME_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(
        output_paths["report"],
        args=args,
        inputs=inputs,
        plan_status=status,
        scenario_rows=scenario_rows,
        outcome_rows=outcome_rows,
        warnings=warnings,
    )
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        inputs=inputs,
        plan_status=status,
        scenario_rows=scenario_rows,
        outcome_rows=outcome_rows,
        warnings=warnings,
    )
    return {
        "plan_status": status,
        "plan_rows": plan_rows,
        "scenario_rows": scenario_rows,
        "outcome_rows": outcome_rows,
        "warnings": warnings,
        "inputs": inputs,
    }


def scenario_lookup(scenario_rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    for row in scenario_rows:
        if row["scenario_label"] == label:
            return row
    return {}


def manifest_metric(manifest: dict[str, Any], key: str, fallback: Any = None) -> Any:
    value = manifest.get(key)
    return fallback if value in ("", None) else value


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    inputs: dict[str, Any],
    plan_status: str,
    scenario_rows: list[dict[str, Any]],
    outcome_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    values = r_values(inputs["trades"])
    timeout_values = outcome_values(inputs["trades"], "paper_timeout")
    scenario_labels = [row["scenario_label"] for row in scenario_rows]
    output: dict[str, Any] = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "replay_review_dir": str(args.replay_review_dir),
        "replay_backtest_dir": str(args.replay_backtest_dir),
        "source_review_manifest_path": str(Path(args.replay_review_dir) / REVIEW_MANIFEST),
        "source_replay_manifest_path": str(Path(args.replay_backtest_dir) / REPLAY_MANIFEST),
        "source_trades_path": str(Path(args.replay_backtest_dir) / REPLAY_TRADES),
        "plan_status": plan_status,
        "scenario_count": len(scenario_rows),
        "scenario_labels": scenario_labels,
        "extra_cost_R_scenarios": [float(value) for value in args.extra_cost_r_scenarios],
        "source_trades_closed": safe_int(manifest_metric(inputs["replay_manifest"], "trades_closed", len(values))) or len(values),
        "source_total_R": safe_float(manifest_metric(inputs["replay_manifest"], "total_R", sum(values))),
        "source_average_R": safe_float(manifest_metric(inputs["replay_manifest"], "average_R")),
        "source_median_R": safe_float(manifest_metric(inputs["replay_manifest"], "median_R")),
        "source_win_rate_R_positive": safe_float(manifest_metric(inputs["replay_manifest"], "win_rate_R_positive")),
        "source_max_drawdown_R": safe_float(manifest_metric(inputs["replay_manifest"], "max_drawdown_R")),
        "timeout_trade_count": len(timeout_values),
        "timeout_gross_total_R": sum(timeout_values),
        "timeout_gross_average_R": statistics.mean(timeout_values) if timeout_values else None,
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "missing_source_artifact_count": inputs["missing_source_artifact_count"],
        "unreadable_source_artifact_count": inputs["unreadable_source_artifact_count"],
        "recommended_next_step": recommended_next_step(scenario_rows, plan_status),
        "no_child_scripts_executed": True,
        "no_replay_rerun": True,
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
    for label in ("base", "mild", "medium", "severe", "stress"):
        scenario = scenario_lookup(scenario_rows, label)
        output[f"{label}_adjusted_total_R"] = safe_float(scenario.get("adjusted_total_R")) if scenario else None
        output[f"{label}_adjusted_average_R"] = safe_float(scenario.get("adjusted_average_R")) if scenario else None
        output[f"{label}_adjusted_max_drawdown_R"] = safe_float(scenario.get("adjusted_max_drawdown_R")) if scenario else None
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    inputs: dict[str, Any],
    plan_status: str,
    scenario_rows: list[dict[str, Any]],
    outcome_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    replay_manifest = inputs["replay_manifest"]
    timeout_rows = [row for row in outcome_rows if row["exit_reason"] == "paper_timeout"]
    timeout_negative = [row for row in timeout_rows if (safe_float(row.get("adjusted_average_R")) or 0) < 0]
    lines = [
        "# Fixed Candidate Replay Cost Sensitivity Plan",
        "",
        "Artifact-only cost sensitivity plan. This module did not rerun the replay.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation or feature refresh was performed.",
        "No optimization or parameter search was performed.",
        "This sensitivity plan is not future-performance proof.",
        "This sensitivity plan is not candidate approval.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- replay_review_dir: `{args.replay_review_dir}`",
        f"- replay_backtest_dir: `{args.replay_backtest_dir}`",
        f"- source_trades: `{Path(args.replay_backtest_dir) / REPLAY_TRADES}`",
        f"- source review status: `{inputs['review_manifest'].get('review_status')}`",
        "",
        "## Source Replay Summary",
        "",
        f"- trades_closed: `{replay_manifest.get('trades_closed')}`",
        f"- total_R: `{replay_manifest.get('total_R')}`",
        f"- average_R: `{replay_manifest.get('average_R')}`",
        f"- median_R: `{replay_manifest.get('median_R')}`",
        f"- win_rate_R_positive: `{replay_manifest.get('win_rate_R_positive')}`",
        f"- max_drawdown_R: `{replay_manifest.get('max_drawdown_R')}`",
        "",
        "## Scenario Table",
        "",
    ]
    for row in scenario_rows:
        lines.append(
            "- "
            f"{row['scenario_label']}: extra_cost_R={row['extra_cost_R_per_trade']}, "
            f"adjusted_total_R={row['adjusted_total_R']}, "
            f"adjusted_average_R={row['adjusted_average_R']}, "
            f"adjusted_max_drawdown_R={row['adjusted_max_drawdown_R']}, "
            f"scenario_status={row['scenario_status']}"
        )
    lines.extend(["", "## Outcome Sensitivity Table", ""])
    for row in outcome_rows:
        lines.append(
            "- "
            f"{row['scenario_label']} / {row['exit_reason']}: "
            f"count={row['trade_count']}, gross_average_R={row['gross_average_R']}, "
            f"adjusted_average_R={row['adjusted_average_R']}"
        )
    lines.extend(
        [
            "",
            "## Timeout Fragility Note",
            "",
            f"- timeout scenarios with negative adjusted average: `{';'.join(row['scenario_label'] for row in timeout_negative)}`",
            "- Timeout sensitivity is descriptive and does not change the validated h10 rule.",
            "",
            "## Caveats",
            "",
            "- Fixed extra-cost R estimates only; original replay results were not modified.",
            "- Thresholds, TP/SL, horizon, and same-bar policy were not changed.",
            "- Cost and slippage assumptions require separate manual review.",
            "- No candidate-quality decision was made.",
            "",
            "## Plan Status",
            "",
            f"`{plan_status}`",
            "",
            "## Recommended Next Step",
            "",
            f"`{recommended_next_step(scenario_rows, plan_status)}`",
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
    parser = argparse.ArgumentParser(description="Build artifact-only cost sensitivity plan for fixed-rule replay results.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--replay-review-dir", type=Path, default=DEFAULT_REPLAY_REVIEW_DIR)
    parser.add_argument("--replay-backtest-dir", type=Path, default=DEFAULT_REPLAY_BACKTEST_DIR)
    parser.add_argument("--extra-cost-r-scenarios", type=float, nargs="+", default=DEFAULT_EXTRA_COST_SCENARIOS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate replay cost sensitivity plan failed: {exc}")
        return 1
    print("Fixed-candidate replay cost sensitivity plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
