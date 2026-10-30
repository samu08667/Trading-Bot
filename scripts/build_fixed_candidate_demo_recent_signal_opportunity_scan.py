"""Build a no-order recent signal opportunity scan for the fixed candidate.

This diagnostic reads recent local feature rows through a read-only SQLite
connection and applies the fixed GBPUSD rule as-is. It does not connect to MT5
or broker/API services, run child scripts, mutate the database, construct
requests, execute orders, change thresholds, or make trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_recent_signal_opportunity_scan"
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_DEMO_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_recent_signal_opportunity_scan"
FEATURE_SOURCE_TABLE = "price_features"

OUTPUT_SUMMARY = "fixed_candidate_demo_recent_signal_opportunity_scan_summary.csv"
OUTPUT_CONDITION_COUNTS = "fixed_candidate_demo_recent_signal_opportunity_scan_condition_counts.csv"
OUTPUT_RECENT_ROWS = "fixed_candidate_demo_recent_signal_opportunity_scan_recent_rows.csv"
OUTPUT_FULL_MATCHES = "fixed_candidate_demo_recent_signal_opportunity_scan_full_matches.csv"
OUTPUT_NEAR_MISSES = "fixed_candidate_demo_recent_signal_opportunity_scan_near_misses.csv"
OUTPUT_MISSING_BREAKDOWN = "fixed_candidate_demo_recent_signal_opportunity_scan_missing_condition_breakdown.csv"
OUTPUT_REPORT = "fixed_candidate_demo_recent_signal_opportunity_scan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_demo_recent_signal_opportunity_scan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_demo_recent_signal_opportunity_scan_manifest.json"

REQUIRED_COLUMNS = (
    "time_server",
    "close",
    "atr_20",
    "spread",
    "hour_session",
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
)
OPTIONAL_COLUMNS = ("symbol", "timeframe", "open", "high", "low", "tick_volume", "volume")
SELECTABLE_COLUMNS = (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS)
NO_ORDER_FLAGS = {
    "no_mt5_connection_performed": True,
    "no_broker_connection_performed": True,
    "no_account_query_performed": True,
    "no_symbol_query_performed": True,
    "no_order_execution_performed": True,
    "no_order_request_constructed": True,
    "no_broker_payload_constructed": True,
    "no_executable_order_object_constructed": True,
    "no_order_send_called": True,
    "no_order_check_called": True,
    "no_order_calc_margin_called": True,
    "no_order_calc_profit_called": True,
    "no_positions_orders_history_checked": True,
    "no_db_mutation_performed": True,
    "no_child_scripts_executed": True,
    "no_data_generation_performed": True,
    "no_feature_refresh_performed": True,
    "no_trading_decision_performed": True,
    "no_demo_broker_approval_performed": True,
    "no_scheduled_task_added": True,
    "no_background_task_added": True,
    "no_candidate_rule_change_performed": True,
}

SUMMARY_FIELDNAMES = [
    "run_id",
    "scan_status",
    "candidate_id",
    "symbol",
    "timeframe",
    "scanned_rows",
    "full_match_rows",
    "near_miss_rows",
    "off_hours_rows",
    "close_to_ma_high_rows",
    "volume_mid_rows",
    "spread_within_policy_rows",
    "bucket_pair_match_rows",
    "session_and_close_match_rows",
    "session_and_volume_match_rows",
    "most_common_missing_condition",
    "latest_row_time_server",
    "latest_full_match_time_server",
    "latest_near_miss_time_server",
    "latest_bucket_pair_match_time_server",
    "latest_off_hours_time_server",
    "recommended_next_step",
    "historical_or_recent_observation_only",
    "manual_review_required",
]
CONDITION_COUNT_FIELDNAMES = ["run_id", "condition_name", "condition_count", "scanned_rows", "share_of_scanned_rows"]
ROW_FIELDNAMES = [
    "run_id",
    "time_server",
    "symbol",
    "timeframe",
    "session_observed",
    "spread",
    "spread_unit",
    "max_spread_points",
    "close",
    "atr_20",
    "close_to_ma_fast_atr_20",
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100",
    "tick_volume_percentile_100_bucket",
    "condition_session_off_hours",
    "condition_close_to_ma_high_tercile",
    "condition_volume_mid_tercile",
    "condition_spread_within_policy",
    "condition_symbol_timeframe_ok",
    "required_values_present",
    "all_conditions_match",
    "near_miss",
    "missing_conditions",
    "historical_or_recent_observation_only",
    "manual_review_required",
]
BREAKDOWN_FIELDNAMES = ["run_id", "missing_condition", "missing_count", "share_of_scanned_rows", "most_common_missing_condition"]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_text() -> str:
    return utc_now().isoformat()


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
        return {}, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(value, dict):
        return {}, "JSON root must be an object"
    return value, ""


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


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


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [warning for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"]


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "summary": output_dir / OUTPUT_SUMMARY,
        "condition_counts": output_dir / OUTPUT_CONDITION_COUNTS,
        "recent_rows": output_dir / OUTPUT_RECENT_ROWS,
        "full_matches": output_dir / OUTPUT_FULL_MATCHES,
        "near_misses": output_dir / OUTPUT_NEAR_MISSES,
        "missing_breakdown": output_dir / OUTPUT_MISSING_BREAKDOWN,
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


def output_dir_for_args(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id


def validate_canonical_registry(registry: dict[str, Any], args: argparse.Namespace) -> bool:
    return (
        registry.get("candidate_id") == "gbpusd_short_h10_1_5_off_hours"
        and registry.get("symbol") == args.symbol == "GBPUSD"
        and registry.get("timeframe") == args.timeframe == "M15"
        and registry.get("direction") == "short"
        and registry.get("spread_unit") == "broker_points"
        and safe_float(registry.get("max_spread_points")) == 15.0
    )


def validate_demo_policy(policy: dict[str, Any]) -> bool:
    boundaries = policy.get("safety_boundaries")
    if not isinstance(boundaries, dict):
        return False
    return (
        policy.get("candidate_id") == "gbpusd_short_h10_1_5_off_hours"
        and policy.get("symbol") == "GBPUSD"
        and policy.get("timeframe") == "M15"
        and policy.get("direction") == "short"
        and policy.get("spread_unit") == "broker_points"
        and safe_float(policy.get("max_spread_points")) == 15.0
        and boundaries.get("real_money_allowed") is False
        and boundaries.get("order_execution_allowed") is False
        and boundaries.get("order_request_construction_allowed") is False
        and boundaries.get("order_check_allowed") is False
        and boundaries.get("order_calc_allowed") is False
    )


def inspect_feature_table(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"status": "blocked_missing_db", "columns": []}
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (FEATURE_SOURCE_TABLE,),
            ).fetchone()
            if not table_exists:
                return {"status": "blocked_missing_required_table", "columns": []}
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({quote_identifier(FEATURE_SOURCE_TABLE)})")]
    except sqlite3.Error as exc:
        return {"status": "blocked_db_read_failure", "columns": [], "error": str(exc)}
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        return {"status": "blocked_missing_required_columns", "columns": columns, "missing_columns": missing}
    return {"status": "ok", "columns": columns}


def fetch_recent_rows(args: argparse.Namespace, columns: list[str]) -> tuple[list[dict[str, Any]], str]:
    selected = [column for column in SELECTABLE_COLUMNS if column in columns]
    filters: list[str] = []
    values: list[Any] = []
    if "symbol" in columns:
        filters.append("symbol = ?")
        values.append(args.symbol)
    if "timeframe" in columns:
        filters.append("timeframe = ?")
        values.append(args.timeframe)
    where_sql = f" WHERE {' AND '.join(filters)}" if filters else ""
    selected_sql = ", ".join(quote_identifier(column) for column in selected)
    query = (
        f"SELECT {selected_sql} FROM {quote_identifier(FEATURE_SOURCE_TABLE)}"
        f"{where_sql} ORDER BY time_server DESC LIMIT ?"
    )
    values.append(int(args.limit))
    try:
        uri = f"file:{Path(args.db_path).resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            rows = [dict(row) for row in connection.execute(query, values).fetchall()]
    except sqlite3.Error as exc:
        return [], str(exc)
    rows.reverse()
    return rows, ""


def bucket_for_value(value: float | None, lower: float, upper: float) -> str:
    if value is None:
        return "missing"
    if value <= lower:
        return "low_tercile"
    if value <= upper:
        return "mid_tercile"
    return "high_tercile"


def threshold_bounds() -> dict[str, float]:
    # Frozen from the fixed-candidate numeric threshold artifact. The scanner
    # intentionally does not recompute or tune thresholds.
    return {
        "close_to_ma_fast_atr_20_lower": -0.45968425469893365,
        "close_to_ma_fast_atr_20_upper": 0.5951568132962021,
        "tick_volume_percentile_100_lower": 0.15,
        "tick_volume_percentile_100_upper": 0.37,
    }


def missing_conditions_for(evaluated: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not evaluated["condition_session_off_hours"]:
        missing.append("missing_session")
    if not evaluated["condition_close_to_ma_high_tercile"]:
        missing.append("missing_close_to_ma_bucket")
    if not evaluated["condition_volume_mid_tercile"]:
        missing.append("missing_volume_bucket")
    if not evaluated["condition_spread_within_policy"]:
        missing.append("missing_spread_gate")
    if not evaluated["condition_symbol_timeframe_ok"]:
        missing.append("missing_symbol_timeframe")
    if not evaluated["required_values_present"]:
        missing.append("missing_required_input_data")
    return missing


def evaluate_row(args: argparse.Namespace, row: dict[str, Any], max_spread_points: float) -> dict[str, Any]:
    bounds = threshold_bounds()
    feature_a = safe_float(row.get("close_to_ma_fast_atr_20"))
    feature_b = safe_float(row.get("tick_volume_percentile_100"))
    spread = safe_float(row.get("spread"))
    close = safe_float(row.get("close"))
    atr_20 = safe_float(row.get("atr_20"))
    bucket_a = bucket_for_value(feature_a, bounds["close_to_ma_fast_atr_20_lower"], bounds["close_to_ma_fast_atr_20_upper"])
    bucket_b = bucket_for_value(feature_b, bounds["tick_volume_percentile_100_lower"], bounds["tick_volume_percentile_100_upper"])
    symbol = row.get("symbol") if "symbol" in row else args.symbol
    timeframe = row.get("timeframe") if "timeframe" in row else args.timeframe
    evaluated = {
        "run_id": args.run_id,
        "time_server": row.get("time_server", ""),
        "symbol": symbol,
        "timeframe": timeframe,
        "session_observed": row.get("hour_session", ""),
        "spread": spread,
        "spread_unit": "broker_points",
        "max_spread_points": max_spread_points,
        "close": close,
        "atr_20": atr_20,
        "close_to_ma_fast_atr_20": feature_a,
        "close_to_ma_fast_atr_20_bucket": bucket_a,
        "tick_volume_percentile_100": feature_b,
        "tick_volume_percentile_100_bucket": bucket_b,
        "condition_session_off_hours": row.get("hour_session") == "Off_hours",
        "condition_close_to_ma_high_tercile": bucket_a == "high_tercile",
        "condition_volume_mid_tercile": bucket_b == "mid_tercile",
        "condition_spread_within_policy": spread is not None and spread <= max_spread_points,
        "condition_symbol_timeframe_ok": symbol == args.symbol and timeframe == args.timeframe,
        "required_values_present": all(value is not None for value in (close, atr_20, spread, feature_a, feature_b)) and bool(row.get("time_server")),
    }
    evaluated["all_conditions_match"] = all(
        bool(evaluated[key])
        for key in (
            "condition_session_off_hours",
            "condition_close_to_ma_high_tercile",
            "condition_volume_mid_tercile",
            "condition_spread_within_policy",
            "condition_symbol_timeframe_ok",
            "required_values_present",
        )
    )
    bucket_pair = evaluated["condition_close_to_ma_high_tercile"] and evaluated["condition_volume_mid_tercile"]
    session_one_bucket = evaluated["condition_session_off_hours"] and (
        evaluated["condition_close_to_ma_high_tercile"] != evaluated["condition_volume_mid_tercile"]
    )
    missing = missing_conditions_for(evaluated)
    evaluated["near_miss"] = (not evaluated["all_conditions_match"]) and (
        len(missing) == 1 or (bucket_pair and not evaluated["condition_session_off_hours"]) or session_one_bucket
    )
    evaluated["missing_conditions"] = ";".join(missing)
    evaluated["historical_or_recent_observation_only"] = bool(evaluated["all_conditions_match"])
    evaluated["manual_review_required"] = False
    return evaluated


def latest_time(rows: list[dict[str, Any]], predicate: str) -> str:
    selected = [str(row.get("time_server", "")) for row in rows if row.get(predicate)]
    return selected[-1] if selected else ""


def build_counts(args: argparse.Namespace, evaluated_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    scanned = len(evaluated_rows)
    count_specs = [
        ("scanned_rows", scanned),
        ("full_match_rows", sum(1 for row in evaluated_rows if row["all_conditions_match"])),
        ("near_miss_rows", sum(1 for row in evaluated_rows if row["near_miss"])),
        ("off_hours_rows", sum(1 for row in evaluated_rows if row["condition_session_off_hours"])),
        ("close_to_ma_high_rows", sum(1 for row in evaluated_rows if row["condition_close_to_ma_high_tercile"])),
        ("volume_mid_rows", sum(1 for row in evaluated_rows if row["condition_volume_mid_tercile"])),
        ("spread_within_policy_rows", sum(1 for row in evaluated_rows if row["condition_spread_within_policy"])),
        ("bucket_pair_match_rows", sum(1 for row in evaluated_rows if row["condition_close_to_ma_high_tercile"] and row["condition_volume_mid_tercile"])),
        ("session_and_close_match_rows", sum(1 for row in evaluated_rows if row["condition_session_off_hours"] and row["condition_close_to_ma_high_tercile"])),
        ("session_and_volume_match_rows", sum(1 for row in evaluated_rows if row["condition_session_off_hours"] and row["condition_volume_mid_tercile"])),
    ]
    condition_counts = [
        {
            "run_id": args.run_id,
            "condition_name": name,
            "condition_count": value,
            "scanned_rows": scanned,
            "share_of_scanned_rows": (value / scanned) if scanned else 0,
        }
        for name, value in count_specs
    ]

    missing_counter: Counter[str] = Counter()
    for row in evaluated_rows:
        for item in str(row.get("missing_conditions", "")).split(";"):
            if item:
                missing_counter[item] += 1
    missing_order = [
        "missing_session",
        "missing_close_to_ma_bucket",
        "missing_volume_bucket",
        "missing_spread_gate",
        "missing_symbol_timeframe",
        "missing_required_input_data",
    ]
    most_common = ""
    if missing_counter:
        most_common = sorted(missing_counter.items(), key=lambda item: (-item[1], missing_order.index(item[0]) if item[0] in missing_order else 99))[0][0]
    breakdown = [
        {
            "run_id": args.run_id,
            "missing_condition": name,
            "missing_count": missing_counter.get(name, 0),
            "share_of_scanned_rows": (missing_counter.get(name, 0) / scanned) if scanned else 0,
            "most_common_missing_condition": name == most_common,
        }
        for name in missing_order
    ]
    summary_counts = {name: value for name, value in count_specs}
    summary_counts["most_common_missing_condition"] = most_common
    return summary_counts, condition_counts, breakdown


def scan_status_for(full_matches: int, near_misses: int) -> str:
    if full_matches > 0:
        return "recent_signal_opportunity_scan_available_with_matches"
    if near_misses > 0:
        return "recent_signal_opportunity_scan_available_near_misses_only"
    return "recent_signal_opportunity_scan_available_no_recent_matches"


def recommended_next_step(status: str) -> str:
    if status == "recent_signal_opportunity_scan_available_with_matches":
        return "review_recent_match_timestamps_and_run_shadow_signal_on_current_live_row_if_relevant"
    if status == "recent_signal_opportunity_scan_available_near_misses_only":
        return "continue_no_order_monitoring_focus_on_missing_conditions"
    if status == "recent_signal_opportunity_scan_available_no_recent_matches":
        return "continue_no_order_monitoring_or_expand_recent_scan_window_without_changing_strategy"
    return "fix_recent_signal_opportunity_scan_blocker"


def blocked_outputs(args: argparse.Namespace, status: str, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary_row": {
            "run_id": args.run_id,
            "scan_status": status,
            "candidate_id": "gbpusd_short_h10_1_5_off_hours",
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "scanned_rows": 0,
            "full_match_rows": 0,
            "near_miss_rows": 0,
            "most_common_missing_condition": "",
            "latest_row_time_server": "",
            "latest_full_match_time_server": "",
            "latest_near_miss_time_server": "",
            "recommended_next_step": recommended_next_step(status),
            "historical_or_recent_observation_only": True,
            "manual_review_required": False,
        },
        "condition_counts": [],
        "recent_rows": [],
        "full_matches": [],
        "near_misses": [],
        "breakdown": [],
        "warnings": warnings,
    }


def build_scan(args: argparse.Namespace) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    registry, registry_error = read_json(Path(args.canonical_registry))
    policy, policy_error = read_json(Path(args.demo_execution_policy))
    if registry_error:
        warnings.append(warning_row(run_id=args.run_id, warning_code="canonical_registry_unreadable", message=f"Canonical registry missing or unreadable: {registry_error}", source=args.canonical_registry, blocking_warning=True))
        return blocked_outputs(args, "blocked_noncanonical_candidate", warnings)
    if policy_error:
        warnings.append(warning_row(run_id=args.run_id, warning_code="demo_execution_policy_unreadable", message=f"Demo execution policy missing or unreadable: {policy_error}", source=args.demo_execution_policy, blocking_warning=True))
        return blocked_outputs(args, "blocked_noncanonical_demo_execution_policy", warnings)
    if not validate_canonical_registry(registry, args):
        warnings.append(warning_row(run_id=args.run_id, warning_code="noncanonical_candidate", message="Canonical registry does not match the fixed GBPUSD spread15 candidate.", source=args.canonical_registry, blocking_warning=True))
        return blocked_outputs(args, "blocked_noncanonical_candidate", warnings)
    if not validate_demo_policy(policy):
        warnings.append(warning_row(run_id=args.run_id, warning_code="noncanonical_demo_execution_policy", message="Demo execution policy does not preserve the no-order boundaries.", source=args.demo_execution_policy, blocking_warning=True))
        return blocked_outputs(args, "blocked_noncanonical_demo_execution_policy", warnings)

    table = inspect_feature_table(Path(args.db_path))
    if table["status"] != "ok":
        warnings.append(warning_row(run_id=args.run_id, warning_code=table["status"], message=f"Feature table scan blocked: {table.get('error') or table.get('missing_columns') or table['status']}", source=args.db_path, blocking_warning=True))
        return blocked_outputs(args, str(table["status"]), warnings)

    rows, read_error = fetch_recent_rows(args, list(table["columns"]))
    if read_error:
        warnings.append(warning_row(run_id=args.run_id, warning_code="blocked_db_read_failure", message=f"Recent feature row read failed: {read_error}", source=args.db_path, blocking_warning=True))
        return blocked_outputs(args, "blocked_db_read_failure", warnings)
    if not rows:
        warnings.append(warning_row(run_id=args.run_id, warning_code="blocked_no_recent_rows", message="No recent feature rows were found for the configured scope.", source=args.db_path, blocking_warning=True))
        return blocked_outputs(args, "blocked_no_recent_rows", warnings)

    max_spread_points = float(registry["max_spread_points"])
    evaluated_rows = [evaluate_row(args, row, max_spread_points) for row in rows]
    summary_counts, condition_counts, breakdown = build_counts(args, evaluated_rows)
    full_matches = [row for row in evaluated_rows if row["all_conditions_match"]]
    near_misses = [row for row in evaluated_rows if row["near_miss"]]
    status = scan_status_for(summary_counts["full_match_rows"], summary_counts["near_miss_rows"])
    summary_row = {
        "run_id": args.run_id,
        "scan_status": status,
        "candidate_id": registry["candidate_id"],
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        **summary_counts,
        "latest_row_time_server": str(evaluated_rows[-1].get("time_server", "")),
        "latest_full_match_time_server": latest_time(evaluated_rows, "all_conditions_match"),
        "latest_near_miss_time_server": latest_time(evaluated_rows, "near_miss"),
        "latest_bucket_pair_match_time_server": next((str(row.get("time_server", "")) for row in reversed(evaluated_rows) if row["condition_close_to_ma_high_tercile"] and row["condition_volume_mid_tercile"]), ""),
        "latest_off_hours_time_server": latest_time(evaluated_rows, "condition_session_off_hours"),
        "recommended_next_step": recommended_next_step(status),
        "historical_or_recent_observation_only": True,
        "manual_review_required": False,
    }
    return {
        "summary_row": summary_row,
        "condition_counts": condition_counts,
        "recent_rows": evaluated_rows,
        "full_matches": full_matches,
        "near_misses": near_misses,
        "breakdown": breakdown,
        "warnings": warnings,
    }


def write_report(path: Path, args: argparse.Namespace, summary: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Recent Signal Opportunity Scan",
        "",
        "Read-only no-order diagnostic scan over already-available local feature rows.",
        "No MT5 connection was performed.",
        "No broker/API query was performed.",
        "No database mutation was performed.",
        "No child scripts were executed.",
        "No import, feature refresh, replay, cost, holdout, paper workflow, or shadow wrapper was run.",
        "No broker request, broker payload, or executable order object was constructed.",
        "No order_send, order_check, order_calc_margin, or order_calc_profit call was performed.",
        "No positions/orders/history read was performed.",
        "No scheduled task or background task was added.",
        "No candidate rule change was performed.",
        "This scan is not demo approval and not a trading decision.",
        "",
        "## Input Overview",
        "",
        f"- canonical_registry: `{args.canonical_registry}`",
        f"- demo_execution_policy: `{args.demo_execution_policy}`",
        f"- db_path: `{args.db_path}`",
        f"- feature_source_table: `{FEATURE_SOURCE_TABLE}`",
        f"- symbol: `{args.symbol}`",
        f"- timeframe: `{args.timeframe}`",
        f"- limit: `{args.limit}`",
        "",
        "## Scan Summary",
        "",
        f"- scan_status: `{summary.get('scan_status', '')}`",
        f"- scanned_rows: `{summary.get('scanned_rows', 0)}`",
        f"- full_match_rows: `{summary.get('full_match_rows', 0)}`",
        f"- near_miss_rows: `{summary.get('near_miss_rows', 0)}`",
        f"- most_common_missing_condition: `{summary.get('most_common_missing_condition', '')}`",
        f"- latest_row_time_server: `{summary.get('latest_row_time_server', '')}`",
        f"- latest_full_match_time_server: `{summary.get('latest_full_match_time_server', '')}`",
        f"- latest_near_miss_time_server: `{summary.get('latest_near_miss_time_server', '')}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{summary.get('recommended_next_step', '')}`",
        "",
        "## Warnings",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(path: Path, args: argparse.Namespace, output_dir: Path, scan: dict[str, Any], paths: dict[str, Path]) -> None:
    summary = scan["summary_row"]
    manifest = {
        "run_id": args.run_id,
        "created_at_utc": utc_now_text(),
        "output_dir": str(output_dir),
        "scan_status": summary.get("scan_status"),
        "candidate_id": summary.get("candidate_id"),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "db_path": str(args.db_path),
        "feature_source_table": FEATURE_SOURCE_TABLE,
        "read_only_db": True,
        "limit": int(args.limit),
        "scanned_rows": summary.get("scanned_rows", 0),
        "full_match_rows": summary.get("full_match_rows", 0),
        "near_miss_rows": summary.get("near_miss_rows", 0),
        "most_common_missing_condition": summary.get("most_common_missing_condition", ""),
        "latest_row_time_server": summary.get("latest_row_time_server", ""),
        "latest_full_match_time_server": summary.get("latest_full_match_time_server", ""),
        "latest_near_miss_time_server": summary.get("latest_near_miss_time_server", ""),
        "recommended_next_step": summary.get("recommended_next_step", ""),
        "warnings_count": len(scan["warnings"]),
        "blocking_warnings_count": len(blocking_warnings(scan["warnings"])),
        "output_files": {key: str(value) for key, value in paths.items()},
        **NO_ORDER_FLAGS,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    if int(args.limit) <= 0:
        raise ValueError("--limit must be positive")
    output_dir = output_dir_for_args(args)
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    scan = build_scan(args)
    write_csv(paths["summary"], [scan["summary_row"]], SUMMARY_FIELDNAMES)
    write_csv(paths["condition_counts"], scan["condition_counts"], CONDITION_COUNT_FIELDNAMES)
    write_csv(paths["recent_rows"], scan["recent_rows"], ROW_FIELDNAMES)
    write_csv(paths["full_matches"], scan["full_matches"], ROW_FIELDNAMES)
    write_csv(paths["near_misses"], scan["near_misses"], ROW_FIELDNAMES)
    write_csv(paths["missing_breakdown"], scan["breakdown"], BREAKDOWN_FIELDNAMES)
    write_csv(paths["warnings"], scan["warnings"], WARNING_FIELDNAMES)
    write_report(paths["report"], args, scan["summary_row"], scan["warnings"])
    write_manifest(paths["manifest"], args, output_dir, scan, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a no-order recent signal opportunity scan for the fixed GBPUSD candidate.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_DEMO_EXECUTION_POLICY)
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, sqlite3.Error, csv.Error) as exc:
        print(f"Fixed-candidate recent signal opportunity scan failed: {exc}")
        return 1
    print("Fixed-candidate recent signal opportunity scan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
