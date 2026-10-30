"""Build an artifact-only recent-period holdout review for fixed-rule replay.

This module reads completed fixed-rule replay, replay review, and cost
sensitivity review artifacts, then isolates recent replay trades for a
descriptive holdout review. It does not rerun replay, rerun cost sensitivity
review, query or mutate the database, run child scripts, refresh data, connect
to MT5, connect to broker/API services, execute orders, optimize parameters, or
make candidate-quality or trading decisions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_recent_period_holdout_review"
DEFAULT_REPLAY_BACKTEST_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_fixed_rule_replay_backtest"
    / "gbpusd_short_h10_1_5_off_hours_fixed_rule_replay_full_v1"
)
DEFAULT_REPLAY_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_fixed_rule_replay_backtest_review"
    / "gbpusd_short_h10_1_5_off_hours_fixed_rule_replay_backtest_review_v1"
)
DEFAULT_COST_SENSITIVITY_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_replay_cost_sensitivity_review"
    / "gbpusd_short_h10_1_5_off_hours_replay_cost_sensitivity_review_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_recent_period_holdout_review"

REPLAY_MANIFEST = "fixed_candidate_fixed_rule_replay_backtest_manifest.json"
REPLAY_TRADES = "fixed_candidate_fixed_rule_replay_backtest_trades.csv"
REPLAY_EQUITY = "fixed_candidate_fixed_rule_replay_backtest_equity.csv"
REPLAY_WARNINGS = "fixed_candidate_fixed_rule_replay_backtest_warnings.csv"

REPLAY_REVIEW_MANIFEST = "fixed_candidate_fixed_rule_replay_backtest_review_manifest.json"
REPLAY_REVIEW_YEARLY = "fixed_candidate_fixed_rule_replay_backtest_review_yearly.csv"
REPLAY_REVIEW_MONTHLY = "fixed_candidate_fixed_rule_replay_backtest_review_monthly.csv"
REPLAY_REVIEW_OUTCOMES = "fixed_candidate_fixed_rule_replay_backtest_review_outcomes.csv"
REPLAY_REVIEW_WARNINGS = "fixed_candidate_fixed_rule_replay_backtest_review_warnings.csv"

COST_REVIEW_MANIFEST = "fixed_candidate_replay_cost_sensitivity_review_manifest.json"
COST_REVIEW_REPORT = "fixed_candidate_replay_cost_sensitivity_review_report.md"

OUTPUT_REVIEW = "fixed_candidate_recent_period_holdout_review.csv"
OUTPUT_TRADES = "fixed_candidate_recent_period_holdout_review_trades.csv"
OUTPUT_MONTHLY = "fixed_candidate_recent_period_holdout_review_monthly.csv"
OUTPUT_OUTCOMES = "fixed_candidate_recent_period_holdout_review_outcomes.csv"
OUTPUT_REPORT = "fixed_candidate_recent_period_holdout_review_report.md"
OUTPUT_WARNINGS = "fixed_candidate_recent_period_holdout_review_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_recent_period_holdout_review_manifest.json"

EXPECTED_SOURCES = (
    ("replay", REPLAY_MANIFEST, True),
    ("replay", REPLAY_TRADES, True),
    ("replay", REPLAY_EQUITY, False),
    ("replay", REPLAY_WARNINGS, False),
    ("replay_review", REPLAY_REVIEW_MANIFEST, True),
    ("replay_review", REPLAY_REVIEW_YEARLY, False),
    ("replay_review", REPLAY_REVIEW_MONTHLY, False),
    ("replay_review", REPLAY_REVIEW_OUTCOMES, False),
    ("replay_review", REPLAY_REVIEW_WARNINGS, False),
    ("cost_sensitivity_review", COST_REVIEW_MANIFEST, True),
    ("cost_sensitivity_review", COST_REVIEW_REPORT, False),
)
REQUIRED_TRADE_COLUMNS = (
    "open_signal_id",
    "entry_time_server",
    "exit_time_server",
    "entry_price",
    "exit_price",
    "tp_price",
    "sl_price",
    "exit_reason",
    "R_multiple",
    "bars_elapsed",
    "horizon_bars",
)
BOUNDARY_FLAGS = (
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

RECENT_TRADE_FIELDNAMES = [
    "run_id",
    "open_signal_id",
    "entry_time_server",
    "exit_time_server",
    "entry_price",
    "exit_price",
    "tp_price",
    "sl_price",
    "exit_reason",
    "R_multiple",
    "bars_elapsed",
    "horizon_bars",
    "period_label",
]

MONTHLY_FIELDNAMES = [
    "run_id",
    "period",
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
    "share_of_recent_trades",
    "total_R",
    "average_R",
    "median_R",
    "min_R",
    "max_R",
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


def parse_time(value: Any) -> datetime | None:
    if value in ("", None):
        return None
    text = str(value).strip()
    for candidate in (text, text.replace(" ", "T"), text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            continue
    return None


def period_label(value: Any) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return "unknown"
    return f"{parsed.year:04d}-{parsed.month:02d}"


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
        "trades": output_dir / OUTPUT_TRADES,
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


def source_path(args: argparse.Namespace, source_role: str, name: str) -> Path:
    if source_role == "replay":
        return Path(args.replay_backtest_dir) / name
    if source_role == "replay_review":
        return Path(args.replay_review_dir) / name
    return Path(args.cost_sensitivity_review_dir) / name


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    missing_count = 0
    missing_required_count = 0
    for source_role, name, required in EXPECTED_SOURCES:
        path = source_path(args, source_role, name)
        if path.exists():
            continue
        missing_count += 1
        missing_required_count += 1 if required else 0
        add_warning(
            warnings,
            args=args,
            warning_code=f"source_{name}_missing",
            message=f"Source artifact is missing: {name}",
            source=path,
            blocking_warning=required,
        )
    replay_manifest, replay_manifest_error = read_json(Path(args.replay_backtest_dir) / REPLAY_MANIFEST)
    replay_review_manifest, replay_review_manifest_error = read_json(Path(args.replay_review_dir) / REPLAY_REVIEW_MANIFEST)
    cost_manifest, cost_manifest_error = read_json(Path(args.cost_sensitivity_review_dir) / COST_REVIEW_MANIFEST)
    trades, trades_error = read_csv_rows(Path(args.replay_backtest_dir) / REPLAY_TRADES)
    equity, equity_error = read_csv_rows(Path(args.replay_backtest_dir) / REPLAY_EQUITY)
    replay_warnings, replay_warnings_error = read_csv_rows(Path(args.replay_backtest_dir) / REPLAY_WARNINGS)
    yearly_rows, yearly_error = read_csv_rows(Path(args.replay_review_dir) / REPLAY_REVIEW_YEARLY)
    monthly_rows, monthly_error = read_csv_rows(Path(args.replay_review_dir) / REPLAY_REVIEW_MONTHLY)
    review_outcomes, review_outcomes_error = read_csv_rows(Path(args.replay_review_dir) / REPLAY_REVIEW_OUTCOMES)
    review_warnings, review_warnings_error = read_csv_rows(Path(args.replay_review_dir) / REPLAY_REVIEW_WARNINGS)
    unreadable_count = 0
    for name, path, error, required in [
        (REPLAY_MANIFEST, Path(args.replay_backtest_dir) / REPLAY_MANIFEST, replay_manifest_error, True),
        (REPLAY_REVIEW_MANIFEST, Path(args.replay_review_dir) / REPLAY_REVIEW_MANIFEST, replay_review_manifest_error, True),
        (COST_REVIEW_MANIFEST, Path(args.cost_sensitivity_review_dir) / COST_REVIEW_MANIFEST, cost_manifest_error, True),
        (REPLAY_TRADES, Path(args.replay_backtest_dir) / REPLAY_TRADES, trades_error, True),
        (REPLAY_EQUITY, Path(args.replay_backtest_dir) / REPLAY_EQUITY, equity_error, False),
        (REPLAY_WARNINGS, Path(args.replay_backtest_dir) / REPLAY_WARNINGS, replay_warnings_error, False),
        (REPLAY_REVIEW_YEARLY, Path(args.replay_review_dir) / REPLAY_REVIEW_YEARLY, yearly_error, False),
        (REPLAY_REVIEW_MONTHLY, Path(args.replay_review_dir) / REPLAY_REVIEW_MONTHLY, monthly_error, False),
        (REPLAY_REVIEW_OUTCOMES, Path(args.replay_review_dir) / REPLAY_REVIEW_OUTCOMES, review_outcomes_error, False),
        (REPLAY_REVIEW_WARNINGS, Path(args.replay_review_dir) / REPLAY_REVIEW_WARNINGS, review_warnings_error, False),
    ]:
        if error:
            unreadable_count += 1
            add_warning(
                warnings,
                args=args,
                warning_code=f"source_{name}_unreadable",
                message=f"Source artifact is unreadable: {error}",
                source=path,
                blocking_warning=required,
            )
    if trades and not set(REQUIRED_TRADE_COLUMNS).issubset(trades[0].keys()):
        unreadable_count += 1
        add_warning(
            warnings,
            args=args,
            warning_code="source_trades_csv_unreadable",
            message="Replay trades CSV is missing required holdout review columns.",
            source=Path(args.replay_backtest_dir) / REPLAY_TRADES,
            blocking_warning=True,
        )
    for source_warning_path, rows in [
        (Path(args.replay_backtest_dir) / REPLAY_WARNINGS, replay_warnings),
        (Path(args.replay_review_dir) / REPLAY_REVIEW_WARNINGS, review_warnings),
    ]:
        for row in rows:
            add_warning(
                warnings,
                args=args,
                warning_code=row.get("warning_code", "source_warning"),
                message=row.get("message", "Source warning preserved."),
                source=row.get("source", source_warning_path),
                blocking_warning=str(row.get("blocking_warning", "")).lower() == "true",
                severity=row.get("severity") or "warning",
            )
    return {
        "replay_manifest": replay_manifest,
        "replay_review_manifest": replay_review_manifest,
        "cost_manifest": cost_manifest,
        "trades": trades,
        "equity": equity,
        "yearly_rows": yearly_rows,
        "monthly_rows": monthly_rows,
        "review_outcomes": review_outcomes,
        "cost_report": read_text(Path(args.cost_sensitivity_review_dir) / COST_REVIEW_REPORT),
        "missing_source_artifact_count": missing_count,
        "missing_required_artifact_count": missing_required_count,
        "unreadable_source_artifact_count": unreadable_count,
    }


def source_boundaries_confirmed(replay_manifest: dict[str, Any], cost_manifest: dict[str, Any]) -> bool:
    if replay_manifest.get("fixed_rule_replay_backtest_run") is not True:
        return False
    for manifest in [replay_manifest, cost_manifest]:
        for flag in BOUNDARY_FLAGS:
            if flag in manifest and manifest.get(flag) is not True:
                return False
    return True


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


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = r_values(rows)
    timeout_values = [safe_float(row.get("R_multiple")) for row in rows if row.get("exit_reason") == "paper_timeout"]
    timeout_values = [value for value in timeout_values if value is not None]
    wins = sum(1 for value in values if value > 0)
    return {
        "trades_closed": len(rows),
        "trades_tp": sum(1 for row in rows if row.get("exit_reason") == "paper_tp_hit"),
        "trades_sl": sum(1 for row in rows if row.get("exit_reason") == "paper_sl_hit"),
        "trades_timeout": sum(1 for row in rows if row.get("exit_reason") == "paper_timeout"),
        "total_R": sum(values),
        "average_R": statistics.mean(values) if values else None,
        "median_R": statistics.median(values) if values else None,
        "min_R": min(values) if values else None,
        "max_R": max(values) if values else None,
        "win_rate_R_positive": wins / len(values) if values else None,
        "max_drawdown_R": max_drawdown_from_r(values),
        "longest_loss_streak": longest_streak(values, positive=False),
        "longest_win_streak": longest_streak(values, positive=True),
        "timeout_trade_count": len(timeout_values),
        "timeout_total_R": sum(timeout_values),
        "timeout_average_R": statistics.mean(timeout_values) if timeout_values else None,
    }


def selected_period_definition(args: argparse.Namespace, trades: list[dict[str, Any]]) -> dict[str, Any]:
    if args.recent_from_time:
        threshold = parse_time(args.recent_from_time)
        return {
            "definition": "recent_from_time",
            "threshold": threshold,
            "label": f"entry_time_server >= {args.recent_from_time}",
        }
    recent_year = safe_int(args.recent_year)
    if recent_year is not None:
        return {
            "definition": "recent_year",
            "year": recent_year,
            "label": str(recent_year),
        }
    parsed_times = [parse_time(row.get("entry_time_server")) for row in trades]
    parsed_times = [value for value in parsed_times if value is not None]
    if not parsed_times:
        return {"definition": "latest_months", "min_month_key": None, "label": "latest_months_unavailable"}
    latest = max(parsed_times)
    months = max(1, int(args.recent_months))
    latest_key = latest.year * 12 + latest.month
    return {
        "definition": "latest_months",
        "min_month_key": latest_key - months + 1,
        "label": f"latest_{months}_calendar_months_through_{latest.year:04d}-{latest.month:02d}",
    }


def trade_selected(row: dict[str, Any], definition: dict[str, Any]) -> bool:
    parsed = parse_time(row.get("entry_time_server"))
    if parsed is None:
        return False
    if definition["definition"] == "recent_from_time":
        threshold = definition.get("threshold")
        return threshold is not None and parsed >= threshold
    if definition["definition"] == "recent_year":
        return parsed.year == definition["year"]
    min_month_key = definition.get("min_month_key")
    if min_month_key is None:
        return False
    return parsed.year * 12 + parsed.month >= min_month_key


def select_recent_trades(args: argparse.Namespace, trades: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    definition = selected_period_definition(args, trades)
    selected = [row for row in trades if trade_selected(row, definition)]
    return selected, definition


def build_recent_trade_rows(args: argparse.Namespace, recent_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in recent_trades:
        rows.append(
            {
                "run_id": args.run_id,
                "open_signal_id": row.get("open_signal_id"),
                "entry_time_server": row.get("entry_time_server"),
                "exit_time_server": row.get("exit_time_server"),
                "entry_price": row.get("entry_price"),
                "exit_price": row.get("exit_price"),
                "tp_price": row.get("tp_price"),
                "sl_price": row.get("sl_price"),
                "exit_reason": row.get("exit_reason"),
                "R_multiple": row.get("R_multiple"),
                "bars_elapsed": row.get("bars_elapsed"),
                "horizon_bars": row.get("horizon_bars"),
                "period_label": period_label(row.get("entry_time_server")),
            }
        )
    return rows


def build_monthly_rows(args: argparse.Namespace, recent_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in recent_trades:
        grouped[period_label(row.get("entry_time_server"))].append(row)
    rows: list[dict[str, Any]] = []
    for period in sorted(grouped):
        stats = metrics(grouped[period])
        rows.append(
            {
                "run_id": args.run_id,
                "period": period,
                "trades_closed": stats["trades_closed"],
                "trades_tp": stats["trades_tp"],
                "trades_sl": stats["trades_sl"],
                "trades_timeout": stats["trades_timeout"],
                "total_R": stats["total_R"],
                "average_R": stats["average_R"],
                "median_R": stats["median_R"],
                "min_R": stats["min_R"],
                "max_R": stats["max_R"],
                "win_rate_R_positive": stats["win_rate_R_positive"],
                "max_drawdown_R": stats["max_drawdown_R"],
                "longest_loss_streak": stats["longest_loss_streak"],
                "longest_win_streak": stats["longest_win_streak"],
                "caveat": "recent_monthly_breakdown_descriptive_only",
            }
        )
    return rows


def build_outcome_rows(args: argparse.Namespace, recent_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in recent_trades:
        grouped[str(row.get("exit_reason") or "unknown")].append(row)
    total = len(recent_trades)
    rows: list[dict[str, Any]] = []
    for reason in sorted(grouped):
        values = r_values(grouped[reason])
        rows.append(
            {
                "run_id": args.run_id,
                "exit_reason": reason,
                "trade_count": len(grouped[reason]),
                "share_of_recent_trades": len(grouped[reason]) / total if total else None,
                "total_R": sum(values),
                "average_R": statistics.mean(values) if values else None,
                "median_R": statistics.median(values) if values else None,
                "min_R": min(values) if values else None,
                "max_R": max(values) if values else None,
                "caveat": "recent_outcome_breakdown_descriptive_only",
            }
        )
    return rows


def full_timeout_average(trades: list[dict[str, Any]]) -> float | None:
    timeout_values = [
        safe_float(row.get("R_multiple"))
        for row in trades
        if row.get("exit_reason") == "paper_timeout" and safe_float(row.get("R_multiple")) is not None
    ]
    return statistics.mean(timeout_values) if timeout_values else None


def status_for_review(inputs: dict[str, Any], warnings: list[dict[str, Any]], recent_stats: dict[str, Any]) -> str:
    if inputs["missing_required_artifact_count"]:
        return "blocked_missing_required_artifact"
    cost_status = str(inputs["cost_manifest"].get("review_status") or "")
    if cost_status.startswith("blocked"):
        return "blocked_by_source_review_status"
    if inputs["unreadable_source_artifact_count"] or blocking_warnings(warnings):
        return "blocked_unreadable_input"
    count = int(recent_stats["trades_closed"])
    total = safe_float(recent_stats["total_R"])
    average = safe_float(recent_stats["average_R"])
    win_rate = safe_float(recent_stats["win_rate_R_positive"])
    drawdown = safe_float(recent_stats["max_drawdown_R"])
    if total is None or average is None or count == 0:
        return "hold_for_recent_period_weakness"
    if total <= 0 or average <= 0:
        return "hold_for_recent_period_weakness"
    if count < 30:
        return "continue_demo_readiness_planning_with_holdout_caveat"
    if average > 0.25 and win_rate is not None and win_rate > 0.55 and drawdown is not None and math.isfinite(drawdown):
        return "continue_paper_validation_recent_period_ok"
    return "hold_for_recent_period_weakness"


def recommended_next_step(status: str) -> str:
    if status in {"continue_demo_readiness_planning_with_holdout_caveat", "continue_paper_validation_recent_period_ok"}:
        return "build_fixed_candidate_demo_readiness_plan"
    if status == "hold_for_recent_period_weakness":
        return "inspect_recent_period_weakness_before_demo_readiness"
    return "fix_missing_or_unreadable_holdout_artifacts"


def review_row(
    *,
    args: argparse.Namespace,
    area: str,
    status: str,
    artifact_status: str,
    source: Path,
    observed: Any,
    expected: Any,
    label: str,
    caveat: str,
    warning_code: str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "review_area": area,
        "review_status": status,
        "artifact_status": artifact_status,
        "source_path": source,
        "observed_value": observed,
        "expected_value": expected,
        "evidence_label": label,
        "caveat": caveat,
        "warning_code": warning_code,
        "blocking_warning": blocking_warning,
    }


def build_review_rows(
    args: argparse.Namespace,
    inputs: dict[str, Any],
    status: str,
    recent_stats: dict[str, Any],
    full_stats: dict[str, Any],
    definition: dict[str, Any],
    small_sample: bool,
) -> list[dict[str, Any]]:
    artifact_status = (
        "available_with_caveat"
        if status == "continue_demo_readiness_planning_with_holdout_caveat"
        else "available"
        if status in {"continue_paper_validation_recent_period_ok", "hold_for_recent_period_weakness"}
        else "missing"
        if status == "blocked_missing_required_artifact"
        else "unreadable"
    )
    average_delta = (
        safe_float(recent_stats["average_R"]) - safe_float(full_stats["average_R"])
        if safe_float(recent_stats["average_R"]) is not None and safe_float(full_stats["average_R"]) is not None
        else None
    )
    return [
        review_row(
            args=args,
            area="source_boundary_context",
            status=status,
            artifact_status=artifact_status,
            source=Path(args.replay_backtest_dir) / REPLAY_MANIFEST,
            observed=source_boundaries_confirmed(inputs["replay_manifest"], inputs["cost_manifest"]),
            expected="source safety boundary flags confirmed",
            label="source_boundaries_confirmed",
            caveat="no_replay_rerun",
        ),
        review_row(
            args=args,
            area="cost_sensitivity_context",
            status=status,
            artifact_status="available_with_caveat",
            source=Path(args.cost_sensitivity_review_dir) / COST_REVIEW_MANIFEST,
            observed=inputs["cost_manifest"].get("review_status"),
            expected="continue_paper_validation_with_cost_caveat",
            label="cost_caveat_preserved",
            caveat="cost_caveat_preserved",
        ),
        review_row(
            args=args,
            area="recent_period_selection",
            status=status,
            artifact_status=artifact_status,
            source=Path(args.replay_backtest_dir) / REPLAY_TRADES,
            observed=definition["label"],
            expected="recent period selected from replay trades",
            label="recent_period_holdout_available",
            caveat="recent_period_selection_descriptive_only",
        ),
        review_row(
            args=args,
            area="recent_aggregate_metrics",
            status=status,
            artifact_status=artifact_status,
            source=Path(args.replay_backtest_dir) / REPLAY_TRADES,
            observed=f"trades={recent_stats['trades_closed']};total_R={recent_stats['total_R']};average_R={recent_stats['average_R']}",
            expected="recent total_R and average_R positive",
            label="recent_period_positive_R_observed"
            if (safe_float(recent_stats["total_R"]) or 0) > 0
            else "recent_period_weakness_observed",
            caveat="recent_period_small_sample_caveat" if small_sample else "recent_period_review_descriptive_only",
        ),
        review_row(
            args=args,
            area="recent_vs_full_comparison",
            status=status,
            artifact_status=artifact_status,
            source=Path(args.replay_review_dir) / REPLAY_REVIEW_MANIFEST,
            observed=f"average_R_delta={average_delta}",
            expected="recent metrics compared against full replay baseline",
            label="recent_period_holdout_available",
            caveat="full_replay_baseline_is_descriptive",
        ),
        review_row(
            args=args,
            area="recent_monthly_breakdown",
            status=status,
            artifact_status=artifact_status,
            source=Path(args.replay_backtest_dir) / REPLAY_TRADES,
            observed="created",
            expected="monthly recent breakdown",
            label="recent_monthly_breakdown_created",
            caveat="monthly_breakdown_descriptive_only",
        ),
        review_row(
            args=args,
            area="recent_outcome_breakdown",
            status=status,
            artifact_status=artifact_status,
            source=Path(args.replay_backtest_dir) / REPLAY_TRADES,
            observed="created",
            expected="recent outcome breakdown",
            label="recent_outcome_breakdown_created",
            caveat="outcome_breakdown_descriptive_only",
        ),
        review_row(
            args=args,
            area="timeout_review",
            status=status,
            artifact_status=artifact_status,
            source=Path(args.replay_backtest_dir) / REPLAY_TRADES,
            observed=f"recent_timeout_average_R={recent_stats['timeout_average_R']};full_timeout_average_R={full_stats['timeout_average_R']}",
            expected="timeout reviewed in recent and full context",
            label="cost_caveat_preserved",
            caveat="timeout_and_cost_caveats_preserved",
        ),
        review_row(
            args=args,
            area="sample_size_review",
            status=status,
            artifact_status="available_with_caveat" if small_sample else artifact_status,
            source=Path(args.replay_backtest_dir) / REPLAY_TRADES,
            observed=recent_stats["trades_closed"],
            expected="30 or more trades avoids small sample caveat",
            label="recent_period_small_sample_caveat" if small_sample else "recent_period_holdout_available",
            caveat="small_sample_caveat" if small_sample else "sample_size_context_only",
        ),
        review_row(
            args=args,
            area="next_research_step",
            status=status,
            artifact_status="available",
            source=Path(args.replay_backtest_dir),
            observed=recommended_next_step(status),
            expected="manual next artifact only",
            label="demo_readiness_planning_recommended"
            if status in {"continue_demo_readiness_planning_with_holdout_caveat", "continue_paper_validation_recent_period_ok"}
            else "hold_before_demo_readiness",
            caveat="no_trading_decision_made",
        ),
    ]


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    inputs = load_inputs(args, warnings)
    if inputs["replay_manifest"] and inputs["cost_manifest"] and not source_boundaries_confirmed(
        inputs["replay_manifest"], inputs["cost_manifest"]
    ):
        add_warning(
            warnings,
            args=args,
            warning_code="source_boundary_not_confirmed",
            message="Source manifests do not confirm all required boundary flags.",
            source=Path(args.replay_backtest_dir) / REPLAY_MANIFEST,
            blocking_warning=True,
        )
    recent_trades, definition = select_recent_trades(args, inputs["trades"])
    recent_stats = metrics(recent_trades)
    full_stats = metrics(inputs["trades"])
    full_stats["average_R"] = safe_float(inputs["replay_manifest"].get("average_R")) or full_stats["average_R"]
    full_stats["win_rate_R_positive"] = safe_float(inputs["replay_manifest"].get("win_rate_R_positive")) or full_stats[
        "win_rate_R_positive"
    ]
    full_stats["max_drawdown_R"] = safe_float(inputs["replay_manifest"].get("max_drawdown_R")) or full_stats["max_drawdown_R"]
    full_stats["timeout_average_R"] = full_timeout_average(inputs["trades"])
    status = status_for_review(inputs, warnings, recent_stats)
    small_sample = status == "continue_demo_readiness_planning_with_holdout_caveat"
    recent_trade_rows = build_recent_trade_rows(args, recent_trades) if not status.startswith("blocked") else []
    monthly_rows = build_monthly_rows(args, recent_trades) if not status.startswith("blocked") else []
    outcome_rows = build_outcome_rows(args, recent_trades) if not status.startswith("blocked") else []
    review_rows = build_review_rows(args, inputs, status, recent_stats, full_stats, definition, small_sample)
    write_csv(output_paths["review"], review_rows, REVIEW_FIELDNAMES)
    write_csv(output_paths["trades"], recent_trade_rows, RECENT_TRADE_FIELDNAMES)
    write_csv(output_paths["monthly"], monthly_rows, MONTHLY_FIELDNAMES)
    write_csv(output_paths["outcomes"], outcome_rows, OUTCOME_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(
        output_paths["report"],
        args=args,
        inputs=inputs,
        review_status_value=status,
        recent_stats=recent_stats,
        full_stats=full_stats,
        definition=definition,
        monthly_rows=monthly_rows,
        outcome_rows=outcome_rows,
        warnings=warnings,
        small_sample=small_sample,
    )
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        inputs=inputs,
        review_status_value=status,
        recent_stats=recent_stats,
        full_stats=full_stats,
        definition=definition,
        monthly_rows=monthly_rows,
        outcome_rows=outcome_rows,
        warnings=warnings,
        small_sample=small_sample,
    )
    return {
        "review_status": status,
        "recent_trades": recent_trades,
        "recent_stats": recent_stats,
        "full_stats": full_stats,
        "monthly_rows": monthly_rows,
        "outcome_rows": outcome_rows,
        "warnings": warnings,
        "inputs": inputs,
    }


def metric_delta(left: Any, right: Any) -> float | None:
    left_value = safe_float(left)
    right_value = safe_float(right)
    if left_value is None or right_value is None:
        return None
    return left_value - right_value


def drawdown_ratio(recent_drawdown: Any, full_drawdown: Any) -> float | None:
    recent_value = safe_float(recent_drawdown)
    full_value = safe_float(full_drawdown)
    if recent_value is None or full_value in (None, 0):
        return None
    return recent_value / full_value


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    inputs: dict[str, Any],
    review_status_value: str,
    recent_stats: dict[str, Any],
    full_stats: dict[str, Any],
    definition: dict[str, Any],
    monthly_rows: list[dict[str, Any]],
    outcome_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    small_sample: bool,
) -> None:
    output = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "replay_backtest_dir": str(args.replay_backtest_dir),
        "replay_review_dir": str(args.replay_review_dir),
        "cost_sensitivity_review_dir": str(args.cost_sensitivity_review_dir),
        "source_replay_manifest_path": str(Path(args.replay_backtest_dir) / REPLAY_MANIFEST),
        "source_trades_path": str(Path(args.replay_backtest_dir) / REPLAY_TRADES),
        "source_equity_path": str(Path(args.replay_backtest_dir) / REPLAY_EQUITY),
        "source_replay_review_manifest_path": str(Path(args.replay_review_dir) / REPLAY_REVIEW_MANIFEST),
        "source_cost_sensitivity_review_manifest_path": str(Path(args.cost_sensitivity_review_dir) / COST_REVIEW_MANIFEST),
        "review_status": review_status_value,
        "recent_period_definition": definition["label"],
        "recent_from_time": args.recent_from_time,
        "recent_year": safe_int(args.recent_year),
        "recent_months": int(args.recent_months),
        "recent_trade_count": recent_stats["trades_closed"],
        "recent_trades_tp": recent_stats["trades_tp"],
        "recent_trades_sl": recent_stats["trades_sl"],
        "recent_trades_timeout": recent_stats["trades_timeout"],
        "recent_total_R": recent_stats["total_R"],
        "recent_average_R": recent_stats["average_R"],
        "recent_median_R": recent_stats["median_R"],
        "recent_win_rate_R_positive": recent_stats["win_rate_R_positive"],
        "recent_max_drawdown_R": recent_stats["max_drawdown_R"],
        "recent_longest_loss_streak": recent_stats["longest_loss_streak"],
        "recent_longest_win_streak": recent_stats["longest_win_streak"],
        "recent_timeout_trade_count": recent_stats["timeout_trade_count"],
        "recent_timeout_total_R": recent_stats["timeout_total_R"],
        "recent_timeout_average_R": recent_stats["timeout_average_R"],
        "full_trades_closed": safe_int(inputs["replay_manifest"].get("trades_closed")) or full_stats["trades_closed"],
        "full_total_R": safe_float(inputs["replay_manifest"].get("total_R")) or full_stats["total_R"],
        "full_average_R": full_stats["average_R"],
        "full_win_rate_R_positive": full_stats["win_rate_R_positive"],
        "full_max_drawdown_R": full_stats["max_drawdown_R"],
        "average_R_delta_recent_vs_full": metric_delta(recent_stats["average_R"], full_stats["average_R"]),
        "win_rate_delta_recent_vs_full": metric_delta(recent_stats["win_rate_R_positive"], full_stats["win_rate_R_positive"]),
        "drawdown_ratio_recent_vs_full": drawdown_ratio(recent_stats["max_drawdown_R"], full_stats["max_drawdown_R"]),
        "monthly_row_count": len(monthly_rows),
        "outcome_row_count": len(outcome_rows),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "missing_source_artifact_count": inputs["missing_source_artifact_count"],
        "unreadable_source_artifact_count": inputs["unreadable_source_artifact_count"],
        "small_sample_caveat": small_sample,
        "cost_caveat_preserved": True,
        "recommended_next_step": recommended_next_step(review_status_value),
        "no_child_scripts_executed": True,
        "no_replay_rerun": True,
        "no_cost_sensitivity_review_rerun": True,
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
    recent_stats: dict[str, Any],
    full_stats: dict[str, Any],
    definition: dict[str, Any],
    monthly_rows: list[dict[str, Any]],
    outcome_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    small_sample: bool,
) -> None:
    lines = [
        "# Fixed Candidate Recent-Period Holdout Review",
        "",
        "Artifact-only recent-period holdout review.",
        "This module did not rerun the replay.",
        "This module did not rerun the cost sensitivity review.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation or feature refresh was performed.",
        "No optimization or parameter search was performed.",
        "This review is not future-performance proof.",
        "This review is not demo broker readiness approval.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- replay_backtest_dir: `{args.replay_backtest_dir}`",
        f"- replay_review_dir: `{args.replay_review_dir}`",
        f"- cost_sensitivity_review_dir: `{args.cost_sensitivity_review_dir}`",
        f"- cost sensitivity review status: `{inputs['cost_manifest'].get('review_status')}`",
        "",
        "## Recent Period Definition",
        "",
        f"`{definition['label']}`",
        "",
        "## Recent Aggregate Metrics",
        "",
        f"- recent_trades_closed: `{recent_stats['trades_closed']}`",
        f"- recent_trades_tp: `{recent_stats['trades_tp']}`",
        f"- recent_trades_sl: `{recent_stats['trades_sl']}`",
        f"- recent_trades_timeout: `{recent_stats['trades_timeout']}`",
        f"- recent_total_R: `{recent_stats['total_R']}`",
        f"- recent_average_R: `{recent_stats['average_R']}`",
        f"- recent_median_R: `{recent_stats['median_R']}`",
        f"- recent_win_rate_R_positive: `{recent_stats['win_rate_R_positive']}`",
        f"- recent_max_drawdown_R: `{recent_stats['max_drawdown_R']}`",
        "",
        "## Comparison Against Full Replay Baseline",
        "",
        f"- full_average_R: `{full_stats['average_R']}`",
        f"- full_win_rate_R_positive: `{full_stats['win_rate_R_positive']}`",
        f"- full_max_drawdown_R: `{full_stats['max_drawdown_R']}`",
        f"- average_R_delta_recent_vs_full: `{metric_delta(recent_stats['average_R'], full_stats['average_R'])}`",
        f"- win_rate_delta_recent_vs_full: `{metric_delta(recent_stats['win_rate_R_positive'], full_stats['win_rate_R_positive'])}`",
        f"- drawdown_ratio_recent_vs_full: `{drawdown_ratio(recent_stats['max_drawdown_R'], full_stats['max_drawdown_R'])}`",
        "",
        "## Monthly Recent Summary",
        "",
    ]
    for row in monthly_rows:
        lines.append(
            f"- {row['period']}: trades={row['trades_closed']}, total_R={row['total_R']}, average_R={row['average_R']}"
        )
    lines.extend(["", "## Recent Outcome Breakdown", ""])
    for row in outcome_rows:
        lines.append(
            f"- {row['exit_reason']}: count={row['trade_count']}, share={row['share_of_recent_trades']}, average_R={row['average_R']}"
        )
    lines.extend(
        [
            "",
            "## Timeout Review",
            "",
            f"- recent_timeout_trade_count: `{recent_stats['timeout_trade_count']}`",
            f"- recent_timeout_average_R: `{recent_stats['timeout_average_R']}`",
            f"- full_timeout_average_R: `{full_stats['timeout_average_R']}`",
            "",
            "## Caveats",
            "",
            f"- small_sample_caveat: `{bool_text(small_sample)}`",
            "- Cost caveat from sensitivity review is preserved.",
            "- Recent-period review is descriptive and separate from any readiness decision.",
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
    parser = argparse.ArgumentParser(description="Build artifact-only recent-period holdout review for fixed-rule replay.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--replay-backtest-dir", type=Path, default=DEFAULT_REPLAY_BACKTEST_DIR)
    parser.add_argument("--replay-review-dir", type=Path, default=DEFAULT_REPLAY_REVIEW_DIR)
    parser.add_argument("--cost-sensitivity-review-dir", type=Path, default=DEFAULT_COST_SENSITIVITY_REVIEW_DIR)
    parser.add_argument("--recent-from-time", default="")
    parser.add_argument("--recent-year", default="2026")
    parser.add_argument("--recent-months", type=int, default=12)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate recent-period holdout review failed: {exc}")
        return 1
    print("Fixed-candidate recent-period holdout review complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
