"""Build an artifact-only review for the fixed-rule replay backtest.

This module reads completed fixed-rule replay artifacts and produces aggregate,
yearly, monthly, and outcome-level review artifacts. It does not rerun the
replay, query or mutate the database, run child scripts, refresh data, connect
to MT5, connect to broker/API services, execute orders, optimize parameters,
or make candidate-quality or trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_fixed_rule_replay_backtest_review"
DEFAULT_REPLAY_BACKTEST_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_fixed_rule_replay_backtest"
    / "gbpusd_short_h10_1_5_off_hours_fixed_rule_replay_full_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_fixed_rule_replay_backtest_review"

SOURCE_MANIFEST = "fixed_candidate_fixed_rule_replay_backtest_manifest.json"
SOURCE_REPORT = "fixed_candidate_fixed_rule_replay_backtest_report.md"
SOURCE_BARS = "fixed_candidate_fixed_rule_replay_backtest_bars.csv"
SOURCE_SIGNALS = "fixed_candidate_fixed_rule_replay_backtest_signals.csv"
SOURCE_TRADES = "fixed_candidate_fixed_rule_replay_backtest_trades.csv"
SOURCE_EQUITY = "fixed_candidate_fixed_rule_replay_backtest_equity.csv"
SOURCE_WARNINGS = "fixed_candidate_fixed_rule_replay_backtest_warnings.csv"

OUTPUT_REVIEW = "fixed_candidate_fixed_rule_replay_backtest_review.csv"
OUTPUT_YEARLY = "fixed_candidate_fixed_rule_replay_backtest_review_yearly.csv"
OUTPUT_MONTHLY = "fixed_candidate_fixed_rule_replay_backtest_review_monthly.csv"
OUTPUT_OUTCOMES = "fixed_candidate_fixed_rule_replay_backtest_review_outcomes.csv"
OUTPUT_REPORT = "fixed_candidate_fixed_rule_replay_backtest_review_report.md"
OUTPUT_WARNINGS = "fixed_candidate_fixed_rule_replay_backtest_review_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_fixed_rule_replay_backtest_review_manifest.json"

REQUIRED_SOURCE_FILES = (SOURCE_MANIFEST, SOURCE_TRADES, SOURCE_EQUITY)
EXPECTED_SOURCE_FILES = (
    SOURCE_MANIFEST,
    SOURCE_REPORT,
    SOURCE_BARS,
    SOURCE_SIGNALS,
    SOURCE_TRADES,
    SOURCE_EQUITY,
    SOURCE_WARNINGS,
)
REQUIRED_TRADE_COLUMNS = ("entry_time_server", "exit_time_server", "exit_reason", "R_multiple")
REQUIRED_EQUITY_COLUMNS = ("trade_index", "open_signal_id", "exit_time_server", "R_multiple", "cumulative_R", "drawdown_R")
BOUNDARY_FLAGS = {
    "fixed_rule_replay_backtest_run": True,
    "no_broker_connection_performed": True,
    "no_order_execution_performed": True,
    "no_db_mutation_performed": True,
    "no_data_generation_performed": True,
    "no_feature_refresh_performed": True,
    "no_stress_validation_executed": True,
    "no_walk_forward_validation_executed": True,
    "no_baseline_diagnostics_executed": True,
    "no_candidate_quality_final_decision_performed": True,
    "no_trading_decision_performed": True,
}

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

PERIOD_FIELDNAMES = [
    "run_id",
    "period",
    "period_type",
    "trades_closed",
    "trades_tp",
    "trades_sl",
    "trades_timeout",
    "total_R",
    "average_R",
    "median_R",
    "min_R",
    "max_R",
    "win_rate_R_positive",
    "max_drawdown_R",
    "longest_loss_streak",
    "longest_win_streak",
    "caveat",
]

OUTCOME_FIELDNAMES = [
    "run_id",
    "exit_reason",
    "trade_count",
    "share_of_trades",
    "total_R",
    "average_R",
    "median_R",
    "min_R",
    "max_R",
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
    return str(value)


def bool_text(value: bool) -> str:
    return "true" if value else "false"


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
        "yearly": output_dir / OUTPUT_YEARLY,
        "monthly": output_dir / OUTPUT_MONTHLY,
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


def parse_period(value: str, period_type: str) -> str:
    if not value:
        return "unknown"
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return f"{parsed.year:04d}" if period_type == "year" else f"{parsed.year:04d}-{parsed.month:02d}"
    except ValueError:
        return text[:4] if period_type == "year" else text[:7]


def r_values(rows: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = safe_float(row.get("R_multiple"))
        if value is not None:
            values.append(value)
    return values


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


def period_metrics(run_id: str, period: str, period_type: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = r_values(rows)
    total = sum(values)
    count = len(rows)
    wins = sum(1 for value in values if value > 0)
    return {
        "run_id": run_id,
        "period": period,
        "period_type": period_type,
        "trades_closed": count,
        "trades_tp": sum(1 for row in rows if row.get("exit_reason") == "paper_tp_hit"),
        "trades_sl": sum(1 for row in rows if row.get("exit_reason") == "paper_sl_hit"),
        "trades_timeout": sum(1 for row in rows if row.get("exit_reason") == "paper_timeout"),
        "total_R": total,
        "average_R": statistics.mean(values) if values else None,
        "median_R": statistics.median(values) if values else None,
        "min_R": min(values) if values else None,
        "max_R": max(values) if values else None,
        "win_rate_R_positive": wins / len(values) if values else None,
        "max_drawdown_R": max_drawdown_from_r(values),
        "longest_loss_streak": longest_streak(values, positive=False),
        "longest_win_streak": longest_streak(values, positive=True),
        "caveat": "descriptive_period_breakdown_only",
    }


def build_period_rows(run_id: str, trades: list[dict[str, Any]], period_type: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in trades:
        timestamp = row.get("exit_time_server") or row.get("entry_time_server") or ""
        grouped[parse_period(str(timestamp), period_type)].append(row)
    return [period_metrics(run_id, period, period_type, grouped[period]) for period in sorted(grouped)]


def build_outcome_rows(run_id: str, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total_trades = len(trades)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in trades:
        grouped[str(row.get("exit_reason") or "unknown")].append(row)
    rows: list[dict[str, Any]] = []
    for reason in sorted(grouped):
        values = r_values(grouped[reason])
        rows.append(
            {
                "run_id": run_id,
                "exit_reason": reason,
                "trade_count": len(grouped[reason]),
                "share_of_trades": len(grouped[reason]) / total_trades if total_trades else None,
                "total_R": sum(values),
                "average_R": statistics.mean(values) if values else None,
                "median_R": statistics.median(values) if values else None,
                "min_R": min(values) if values else None,
                "max_R": max(values) if values else None,
            }
        )
    return rows


def validate_source_artifacts(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    root = Path(args.replay_backtest_dir)
    missing = [name for name in EXPECTED_SOURCE_FILES if not (root / name).exists()]
    required_missing = [name for name in REQUIRED_SOURCE_FILES if not (root / name).exists()]
    for name in missing:
        add_warning(
            warnings,
            args=args,
            warning_code=f"source_{name}_missing",
            message=f"Source artifact is missing: {name}",
            source=root / name,
            blocking_warning=name in REQUIRED_SOURCE_FILES,
        )
    manifest, manifest_error = read_json(root / SOURCE_MANIFEST)
    trades, trades_error = read_csv_rows(root / SOURCE_TRADES)
    equity, equity_error = read_csv_rows(root / SOURCE_EQUITY)
    signals, signals_error = read_csv_rows(root / SOURCE_SIGNALS)
    source_warnings, source_warnings_error = read_csv_rows(root / SOURCE_WARNINGS)
    report = read_text(root / SOURCE_REPORT)
    unreadable_count = 0
    for name, error, required in [
        (SOURCE_MANIFEST, manifest_error, True),
        (SOURCE_TRADES, trades_error, True),
        (SOURCE_EQUITY, equity_error, True),
        (SOURCE_SIGNALS, signals_error, False),
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
    if trades and not set(REQUIRED_TRADE_COLUMNS).issubset(trades[0].keys()):
        unreadable_count += 1
        add_warning(
            warnings,
            args=args,
            warning_code="source_trades_csv_unreadable",
            message="Trades CSV is missing required review columns.",
            source=root / SOURCE_TRADES,
            blocking_warning=True,
        )
    if equity and not set(REQUIRED_EQUITY_COLUMNS).issubset(equity[0].keys()):
        unreadable_count += 1
        add_warning(
            warnings,
            args=args,
            warning_code="source_equity_csv_unreadable",
            message="Equity CSV is missing required review columns.",
            source=root / SOURCE_EQUITY,
            blocking_warning=True,
        )
    for row in source_warnings:
        add_warning(
            warnings,
            args=args,
            warning_code=row.get("warning_code", "source_replay_warning"),
            message=row.get("message", "Source replay warning preserved."),
            source=row.get("source", root / SOURCE_WARNINGS),
            blocking_warning=str(row.get("blocking_warning", "")).lower() == "true",
            severity=row.get("severity") or "warning",
        )
    return {
        "manifest": manifest,
        "trades": trades,
        "equity": equity,
        "signals": signals,
        "source_warnings": source_warnings,
        "report": report,
        "missing_source_artifact_count": len(missing),
        "missing_required_artifact_count": len(required_missing),
        "unreadable_source_artifact_count": unreadable_count,
    }


def boundary_confirmed(manifest: dict[str, Any]) -> bool:
    return all(manifest.get(field) is expected for field, expected in BOUNDARY_FLAGS.items())


def review_status(source: dict[str, Any], warnings: list[dict[str, Any]]) -> str:
    if source["missing_required_artifact_count"]:
        return "blocked_missing_required_artifact"
    if source["unreadable_source_artifact_count"] or blocking_warnings(warnings):
        return "blocked_unreadable_replay_artifacts"
    manifest = source["manifest"]
    trades_closed = safe_int(manifest.get("trades_closed")) or 0
    total_r = safe_float(manifest.get("total_R"))
    average_r = safe_float(manifest.get("average_R"))
    max_drawdown = safe_float(manifest.get("max_drawdown_R"))
    if (
        trades_closed >= 100
        and total_r is not None
        and total_r > 0
        and average_r is not None
        and average_r > 0
        and max_drawdown is not None
        and math.isfinite(max_drawdown)
    ):
        return "continue_paper_validation"
    return "hold_for_more_validation"


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


def build_review_rows(args: argparse.Namespace, source: dict[str, Any], status: str, same_bar_count: int) -> list[dict[str, Any]]:
    manifest = source["manifest"]
    root = Path(args.replay_backtest_dir)
    artifact_status = "available" if status in {"continue_paper_validation", "hold_for_more_validation"} else "missing" if status == "blocked_missing_required_artifact" else "unreadable"
    next_step = (
        "build_fixed_candidate_replay_cost_sensitivity_plan"
        if status == "continue_paper_validation"
        else "inspect_missing_or_weak_periods_before_more_automation"
        if status == "hold_for_more_validation"
        else "fix_missing_or_unreadable_artifacts"
    )
    return [
        review_row(
            args=args,
            area="replay_context",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_MANIFEST,
            observed_value=boundary_confirmed(manifest),
            expected_value="fixed_rule_replay_backtest_run=true and safety flags confirmed",
            evidence_label="replay_boundary_confirmed" if boundary_confirmed(manifest) else "",
            caveat="fixed_rule_replay_review_only",
            warning_code="" if boundary_confirmed(manifest) else "replay_boundary_not_confirmed",
            blocking_warning=not boundary_confirmed(manifest),
        ),
        review_row(
            args=args,
            area="aggregate_signal_count",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_MANIFEST,
            observed_value=f"opened={manifest.get('signals_opened')};skipped={manifest.get('signals_skipped')}",
            expected_value="descriptive_counts_available",
            evidence_label="fixed_rule_replay_available",
            caveat="descriptive_only_no_trading_decision",
        ),
        review_row(
            args=args,
            area="aggregate_trade_count",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_MANIFEST,
            observed_value=f"closed={manifest.get('trades_closed')};tp={manifest.get('trades_tp')};sl={manifest.get('trades_sl')};timeout={manifest.get('trades_timeout')}",
            expected_value="trades_closed >= 100 for continue_paper_validation",
            evidence_label="fixed_rule_replay_available",
            caveat="count_threshold_is_review_gate_not_strategy_decision",
        ),
        review_row(
            args=args,
            area="aggregate_R_summary",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_MANIFEST,
            observed_value=f"total_R={manifest.get('total_R')};average_R={manifest.get('average_R')};median_R={manifest.get('median_R')}",
            expected_value="total_R > 0 and average_R > 0 for continue_paper_validation",
            evidence_label="aggregate_positive_R_observed" if (safe_float(manifest.get("total_R")) or 0) > 0 else "",
            caveat="one_replay_not_future_proof",
        ),
        review_row(
            args=args,
            area="aggregate_drawdown_summary",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_MANIFEST,
            observed_value=manifest.get("max_drawdown_R"),
            expected_value="finite max_drawdown_R",
            evidence_label="fixed_rule_replay_available",
            caveat="drawdown_from_local_fixed_replay_only",
        ),
        review_row(
            args=args,
            area="aggregate_streak_summary",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_MANIFEST,
            observed_value=f"loss={manifest.get('longest_loss_streak')};win={manifest.get('longest_win_streak')}",
            expected_value="descriptive_streaks_available",
            evidence_label="fixed_rule_replay_available",
            caveat="streak_review_descriptive_only",
        ),
        review_row(
            args=args,
            area="timeout_review",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_MANIFEST,
            observed_value=manifest.get("trades_timeout"),
            expected_value="timeout_contribution_reviewed",
            evidence_label="timeout_contribution_reviewed",
            caveat="timeout_outcomes_need_cost_slippage_sensitivity_context",
        ),
        review_row(
            args=args,
            area="same_bar_warning_review",
            status=status,
            artifact_status=artifact_status,
            source_path=root / SOURCE_WARNINGS,
            observed_value=same_bar_count,
            expected_value="same_bar_stop_first_applied warnings summarized",
            evidence_label="same_bar_stop_first_reviewed",
            caveat="non_blocking_if_source_warning_non_blocking",
        ),
        review_row(
            args=args,
            area="caveat_cost_slippage_review",
            status=status,
            artifact_status="available_with_caveat",
            source_path=root / SOURCE_MANIFEST,
            observed_value="fixed_rule_replay_without_new_cost_sensitivity",
            expected_value="cost_slippage_sensitivity_required",
            evidence_label="cost_slippage_sensitivity_required",
            caveat="cost_slippage_sensitivity_required",
        ),
        review_row(
            args=args,
            area="caveat_replay_not_future_proof",
            status=status,
            artifact_status="available_with_caveat",
            source_path=root / SOURCE_REPORT,
            observed_value="one_fixed_rule_replay",
            expected_value="not_future_performance_proof",
            evidence_label="one_replay_not_future_proof",
            caveat="no_candidate_approval_no_trading_decision",
        ),
        review_row(
            args=args,
            area="next_research_step",
            status=status,
            artifact_status="available",
            source_path=root,
            observed_value=next_step,
            expected_value="manual_follow_up_only",
            evidence_label=status,
            caveat="no_trading_decision_made",
        ),
    ]


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    source = validate_source_artifacts(args, warnings)
    same_bar_count = sum(1 for warning in warnings if warning.get("warning_code") == "same_bar_stop_first_applied")
    if source["manifest"] and not boundary_confirmed(source["manifest"]):
        add_warning(
            warnings,
            args=args,
            warning_code="replay_boundary_not_confirmed",
            message="Replay manifest does not confirm all fixed-rule replay safety boundary flags.",
            source=Path(args.replay_backtest_dir) / SOURCE_MANIFEST,
            blocking_warning=True,
        )
    status = review_status(source, warnings)
    yearly_rows = build_period_rows(args.run_id, source["trades"], "year") if not status.startswith("blocked") else []
    monthly_rows = build_period_rows(args.run_id, source["trades"], "month") if not status.startswith("blocked") else []
    outcome_rows = build_outcome_rows(args.run_id, source["trades"]) if not status.startswith("blocked") else []
    review_rows = build_review_rows(args, source, status, same_bar_count)
    write_csv(output_paths["review"], review_rows, REVIEW_FIELDNAMES)
    write_csv(output_paths["yearly"], yearly_rows, PERIOD_FIELDNAMES)
    write_csv(output_paths["monthly"], monthly_rows, PERIOD_FIELDNAMES)
    write_csv(output_paths["outcomes"], outcome_rows, OUTCOME_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(
        output_paths["report"],
        args=args,
        review_status=status,
        source=source,
        yearly_rows=yearly_rows,
        monthly_rows=monthly_rows,
        outcome_rows=outcome_rows,
        same_bar_count=same_bar_count,
        warnings=warnings,
    )
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        review_status=status,
        source=source,
        yearly_rows=yearly_rows,
        monthly_rows=monthly_rows,
        outcome_rows=outcome_rows,
        same_bar_count=same_bar_count,
        warnings=warnings,
    )
    return {
        "review_status": status,
        "review_rows": review_rows,
        "yearly_rows": yearly_rows,
        "monthly_rows": monthly_rows,
        "outcome_rows": outcome_rows,
        "warnings": warnings,
        "source": source,
    }


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    review_status: str,
    source: dict[str, Any],
    yearly_rows: list[dict[str, Any]],
    monthly_rows: list[dict[str, Any]],
    outcome_rows: list[dict[str, Any]],
    same_bar_count: int,
    warnings: list[dict[str, Any]],
) -> None:
    manifest = source["manifest"]
    lines = [
        "# Fixed Candidate Fixed-Rule Replay Backtest Review",
        "",
        "Fixed-rule replay review artifact only. This module did not rerun the replay.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation or feature refresh was performed.",
        "No optimization or parameter search was performed.",
        "This review is not future-performance proof.",
        "This review is not candidate approval.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- replay_backtest_dir: `{args.replay_backtest_dir}`",
        f"- source_manifest: `{Path(args.replay_backtest_dir) / SOURCE_MANIFEST}`",
        f"- source_trades: `{Path(args.replay_backtest_dir) / SOURCE_TRADES}`",
        f"- source_equity: `{Path(args.replay_backtest_dir) / SOURCE_EQUITY}`",
        "",
        "## Aggregate Replay Metrics",
        "",
        f"- bars_processed: `{manifest.get('bars_processed')}`",
        f"- signals_opened: `{manifest.get('signals_opened')}`",
        f"- signals_skipped: `{manifest.get('signals_skipped')}`",
        f"- trades_closed: `{manifest.get('trades_closed')}`",
        f"- trades_tp: `{manifest.get('trades_tp')}`",
        f"- trades_sl: `{manifest.get('trades_sl')}`",
        f"- trades_timeout: `{manifest.get('trades_timeout')}`",
        f"- total_R: `{manifest.get('total_R')}`",
        f"- average_R: `{manifest.get('average_R')}`",
        f"- median_R: `{manifest.get('median_R')}`",
        f"- win_rate_R_positive: `{manifest.get('win_rate_R_positive')}`",
        f"- max_drawdown_R: `{manifest.get('max_drawdown_R')}`",
        f"- longest_loss_streak: `{manifest.get('longest_loss_streak')}`",
        f"- longest_win_streak: `{manifest.get('longest_win_streak')}`",
        f"- spread_unit: `{manifest.get('spread_unit')}`",
        f"- max_spread_points: `{manifest.get('max_spread_points')}`",
        f"- spread_policy_matches_canonical: `{manifest.get('spread_policy_matches_canonical')}`",
        "",
        "## Yearly Summary",
        "",
    ]
    for row in yearly_rows[:12]:
        lines.append(
            f"- {row['period']}: trades={row['trades_closed']}, total_R={row['total_R']}, average_R={row['average_R']}, max_drawdown_R={row['max_drawdown_R']}"
        )
    lines.extend(["", "## Monthly Summary", ""])
    for row in monthly_rows[:24]:
        lines.append(
            f"- {row['period']}: trades={row['trades_closed']}, total_R={row['total_R']}, average_R={row['average_R']}"
        )
    if len(monthly_rows) > 24:
        lines.append(f"- Additional monthly rows written to CSV: `{len(monthly_rows) - 24}`")
    lines.extend(["", "## Outcome Breakdown", ""])
    for row in outcome_rows:
        lines.append(
            f"- {row['exit_reason']}: count={row['trade_count']}, share={row['share_of_trades']}, total_R={row['total_R']}, average_R={row['average_R']}"
        )
    lines.extend(
        [
            "",
            "## Timeout Review",
            "",
            f"- trades_timeout: `{manifest.get('trades_timeout')}`",
            "",
            "## Drawdown/Streak Review",
            "",
            f"- max_drawdown_R: `{manifest.get('max_drawdown_R')}`",
            f"- longest_loss_streak: `{manifest.get('longest_loss_streak')}`",
            f"- longest_win_streak: `{manifest.get('longest_win_streak')}`",
            "",
            "## Warnings Review",
            "",
            f"- same_bar_stop_first_warning_count: `{same_bar_count}`",
            f"- warnings_count: `{len(warnings)}`",
            f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
            "",
            "## Review Status",
            "",
            f"`{review_status}`",
            "",
            "## Recommended Next Step",
            "",
            f"`{recommended_next_step(review_status)}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def recommended_next_step(status: str) -> str:
    if status == "continue_paper_validation":
        return "build_fixed_candidate_replay_cost_sensitivity_plan"
    if status == "hold_for_more_validation":
        return "inspect_missing_or_weak_periods_before_more_automation"
    return "fix_missing_or_unreadable_artifacts"


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    review_status: str,
    source: dict[str, Any],
    yearly_rows: list[dict[str, Any]],
    monthly_rows: list[dict[str, Any]],
    outcome_rows: list[dict[str, Any]],
    same_bar_count: int,
    warnings: list[dict[str, Any]],
) -> None:
    manifest = source["manifest"]
    output = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "replay_backtest_dir": str(args.replay_backtest_dir),
        "source_manifest_path": str(Path(args.replay_backtest_dir) / SOURCE_MANIFEST),
        "source_trades_path": str(Path(args.replay_backtest_dir) / SOURCE_TRADES),
        "source_equity_path": str(Path(args.replay_backtest_dir) / SOURCE_EQUITY),
        "source_signals_path": str(Path(args.replay_backtest_dir) / SOURCE_SIGNALS),
        "source_warnings_path": str(Path(args.replay_backtest_dir) / SOURCE_WARNINGS),
        "source_report_path": str(Path(args.replay_backtest_dir) / SOURCE_REPORT),
        "review_status": review_status,
        "spread_unit": manifest.get("spread_unit"),
        "max_spread_points": manifest.get("max_spread_points"),
        "spread_policy_matches_canonical": manifest.get("spread_policy_matches_canonical"),
        "replay_bars_processed": safe_int(manifest.get("bars_processed")),
        "replay_signals_opened": safe_int(manifest.get("signals_opened")),
        "replay_signals_skipped": safe_int(manifest.get("signals_skipped")),
        "replay_trades_closed": safe_int(manifest.get("trades_closed")),
        "replay_trades_tp": safe_int(manifest.get("trades_tp")),
        "replay_trades_sl": safe_int(manifest.get("trades_sl")),
        "replay_trades_timeout": safe_int(manifest.get("trades_timeout")),
        "replay_total_R": safe_float(manifest.get("total_R")),
        "replay_average_R": safe_float(manifest.get("average_R")),
        "replay_median_R": safe_float(manifest.get("median_R")),
        "replay_win_rate_R_positive": safe_float(manifest.get("win_rate_R_positive")),
        "replay_max_drawdown_R": safe_float(manifest.get("max_drawdown_R")),
        "replay_longest_loss_streak": safe_int(manifest.get("longest_loss_streak")),
        "replay_longest_win_streak": safe_int(manifest.get("longest_win_streak")),
        "yearly_row_count": len(yearly_rows),
        "monthly_row_count": len(monthly_rows),
        "outcome_row_count": len(outcome_rows),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "missing_source_artifact_count": source["missing_source_artifact_count"],
        "unreadable_source_artifact_count": source["unreadable_source_artifact_count"],
        "same_bar_stop_first_warning_count": same_bar_count,
        "recommended_next_step": recommended_next_step(review_status),
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
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    build_artifacts(args, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build artifact-only review for fixed-rule replay backtest outputs.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--replay-backtest-dir", type=Path, default=DEFAULT_REPLAY_BACKTEST_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate fixed-rule replay backtest review failed: {exc}")
        return 1
    print("Fixed-candidate fixed-rule replay backtest review complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
