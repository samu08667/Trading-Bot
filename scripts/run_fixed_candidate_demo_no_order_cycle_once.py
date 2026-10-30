"""Run one controlled live-data no-order cycle for the fixed candidate.

This orchestrator is single-shot. It may run only the local bar import,
feature generation, and demo no-order dry-run scripts. It does not construct
order requests, execute orders, inspect positions/orders/history, run replay or
paper workflows, optimize parameters, approve broker use, or make trading
decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_no_order_cycle_once"
DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_TIMEFRAME = "M15"
EXPECTED_MAX_SPREAD_POINTS = 15.0
PRICE_BARS_TABLE = "price_bars"
PRICE_FEATURES_TABLE = "price_features"
IMPORT_FROM_OVERLAP_HOURS = 2.0
IMPORT_TO_INCLUSION_MINUTES = 1.0
DEFAULT_FEATURE_SOURCE_DB = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_DEMO_NO_ORDER_DRY_RUN_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_no_order_dry_run_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_no_order_dry_run_plan_spread15_v1"
)
DEFAULT_DEMO_ENVIRONMENT_CHECK_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_environment_check"
    / "gbpusd_short_h10_1_5_off_hours_demo_environment_check_spread15_v1"
)
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR / "config" / "paper_demo" / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_DEMO_STRATEGY_SPEC_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_strategy_spec"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v5_spread15"
)
DEFAULT_STATE_JSON = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_v1"
    / "fixed_candidate_paper_signal_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_no_order_cycle_once"

CHILD_SCRIPT_PATHS = {
    "import_price_bars": BASE_DIR / "scripts" / "import_price_bars.py",
    "generate_price_features": BASE_DIR / "scripts" / "generate_price_features.py",
    "demo_no_order_dry_run": BASE_DIR / "scripts" / "run_fixed_candidate_demo_no_order_dry_run.py",
}
ALLOWED_CHILD_SCRIPT_PATHS = frozenset(path.resolve() for path in CHILD_SCRIPT_PATHS.values())
DISALLOWED_CHILD_NAME_PARTS = (
    "paper_signal_logger",
    "paper_trade_tracker",
    "local_paper_cycle",
    "replay",
    "backtest",
    "cost_sensitivity",
    "holdout",
    "stress",
    "walkforward",
    "walk-forward",
    "baseline",
    "execution",
)

PLAN_MANIFEST = "fixed_candidate_demo_no_order_dry_run_plan_manifest.json"
ENV_MANIFEST = "fixed_candidate_demo_environment_check_manifest.json"
NO_ORDER_CHILD_MANIFEST = "fixed_candidate_demo_no_order_dry_run_manifest.json"

OUTPUT_CSV = "fixed_candidate_demo_no_order_cycle_once.csv"
OUTPUT_CHILD_COMMANDS = "fixed_candidate_demo_no_order_cycle_once_child_commands.csv"
OUTPUT_CHILD_RESULTS = "fixed_candidate_demo_no_order_cycle_once_child_results.csv"
OUTPUT_REPORT = "fixed_candidate_demo_no_order_cycle_once_report.md"
OUTPUT_WARNINGS = "fixed_candidate_demo_no_order_cycle_once_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_demo_no_order_cycle_once_manifest.json"

MAIN_FIELDNAMES = [
    "run_id",
    "cycle_area",
    "cycle_status",
    "artifact_status",
    "source_path",
    "observed_value",
    "expected_value",
    "evidence_label",
    "caveat",
    "warning_code",
    "blocking_warning",
]
COMMAND_FIELDNAMES = [
    "run_id",
    "child_step",
    "command_index",
    "command_executable",
    "command_args_json",
    "planned_only",
    "allowed_child_script",
    "check_mode",
    "caveat",
]
RESULT_FIELDNAMES = [
    "run_id",
    "child_step",
    "command_index",
    "return_code",
    "started_at",
    "completed_at",
    "duration_seconds",
    "stdout_tail",
    "stderr_tail",
    "child_status",
    "blocking_warning",
]
WARNING_FIELDNAMES = [
    "run_id",
    "warning_code",
    "severity",
    "message",
    "source",
    "blocking_warning",
]
NO_ORDER_FLAGS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_demo_broker_approval_performed",
    "no_candidate_quality_final_decision_performed",
    "no_trading_decision_performed",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_text() -> str:
    return utc_now().isoformat()


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def format_time_server(timestamp: int | float | None) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def object_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    try:
        return value[key]
    except (TypeError, KeyError, IndexError, ValueError):
        return getattr(value, key, None)


def mt5_time_basis_unavailable(reason: str, *, dry_run: bool = False) -> dict[str, Any]:
    live_spread_status = "live_spread_not_checked_no_broker_context" if dry_run else "blocked_current_spread_unavailable"
    return {
        "mt5_time_basis_status": "live_data_mt5_time_basis_unavailable",
        "mt5_time_basis_unavailable_reason": reason,
        "mt5_alignment_checked": False,
        "time_server_source": "raw_broker_server_time_or_existing_db_time_server",
        "import_time_basis": "mt5_time_basis_unavailable",
        "pc_utc_now": utc_now_text(),
        "mt5_tick_time_server": "",
        "latest_mt5_closed_bar_time_server": "",
        "mt5_server_time_offset_seconds_vs_pc_utc": None,
        "mt5_time_basis_caveat": "not_checked_dry_run" if dry_run else "mt5_probe_unavailable",
        "current_broker_spread_points": "",
        "current_broker_spread_source": "not_checked_no_broker_context" if dry_run else "unavailable",
        "current_broker_spread_within_policy": None if dry_run else False,
        "current_broker_spread_policy_max_points": EXPECTED_MAX_SPREAD_POINTS,
        "live_spread_gate_status": live_spread_status,
    }


def current_broker_spread_evidence(symbol_info: Any, tick: Any) -> dict[str, Any]:
    symbol_spread = safe_float(object_value(symbol_info, "spread"))
    if symbol_spread is not None and symbol_spread >= 0:
        spread = symbol_spread
        source = "symbol_info.spread"
    else:
        bid = safe_float(object_value(tick, "bid"))
        ask = safe_float(object_value(tick, "ask"))
        point = safe_float(object_value(symbol_info, "point"))
        if bid is None or ask is None or point is None or point <= 0 or ask < bid:
            return {
                "current_broker_spread_points": "",
                "current_broker_spread_source": "unavailable",
                "current_broker_spread_within_policy": False,
                "current_broker_spread_policy_max_points": EXPECTED_MAX_SPREAD_POINTS,
                "live_spread_gate_status": "blocked_current_spread_unavailable",
            }
        spread = round((ask - bid) / point, 6)
        source = "tick_ask_bid_div_point"
    within_policy = spread <= EXPECTED_MAX_SPREAD_POINTS
    return {
        "current_broker_spread_points": spread,
        "current_broker_spread_source": source,
        "current_broker_spread_within_policy": within_policy,
        "current_broker_spread_policy_max_points": EXPECTED_MAX_SPREAD_POINTS,
        "live_spread_gate_status": "live_spread_within_policy" if within_policy else "blocked_current_spread_above_policy",
    }


def collect_mt5_time_basis(args: argparse.Namespace, mt5_module: Any | None = None) -> dict[str, Any]:
    pc_now = utc_now()
    try:
        mt5 = mt5_module
        if mt5 is None:
            import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError as exc:
        return mt5_time_basis_unavailable(str(exc))

    initialized = False
    try:
        if mt5_module is None:
            initialized = bool(mt5.initialize())
            if not initialized:
                return mt5_time_basis_unavailable(f"initialize_failed:{mt5.last_error()}")
        timeframe_value = getattr(mt5, f"TIMEFRAME_{str(args.timeframe).upper()}")
        symbol_info = mt5.symbol_info(args.symbol) if hasattr(mt5, "symbol_info") else None
        tick = mt5.symbol_info_tick(args.symbol)
        rates = mt5.copy_rates_from_pos(args.symbol, timeframe_value, 1, 1)
        if rates is None or len(rates) == 0:
            return mt5_time_basis_unavailable(f"latest_closed_bar_unavailable:{getattr(mt5, 'last_error', lambda: '')()}")
        rate = rates[0]
        tick_raw = object_value(tick, "time") if tick is not None else None
        rate_raw = object_value(rate, "time")
        latest_bar = format_time_server(rate_raw)
        if not latest_bar:
            return mt5_time_basis_unavailable("latest_closed_bar_time_missing")
        offset: int | None = None
        try:
            offset = int(tick_raw) - int(pc_now.timestamp()) if tick_raw is not None else None
        except (TypeError, ValueError, OverflowError):
            offset = None
        return {
            "mt5_time_basis_status": "mt5_alignment_checked",
            "mt5_time_basis_unavailable_reason": "",
            "mt5_alignment_checked": True,
            "time_server_source": "raw_broker_server_time_or_existing_db_time_server",
            "import_time_basis": "mt5_broker_server_time_when_available",
            "pc_utc_now": pc_now.isoformat(),
            "mt5_tick_time_server": format_time_server(tick_raw),
            "latest_mt5_closed_bar_time_server": latest_bar,
            "mt5_server_time_offset_seconds_vs_pc_utc": offset,
            "mt5_time_basis_caveat": "diagnostic_only_no_offset_hardcoded",
            **current_broker_spread_evidence(symbol_info, tick),
        }
    except Exception as exc:
        return mt5_time_basis_unavailable(str(exc))
    finally:
        if initialized:
            mt5.shutdown()


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


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def command_arg_value(value: Any, default: Any = "") -> str:
    return str(default if value in ("", None) else value)


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


def repo_relative_path(path: Path | str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else BASE_DIR / candidate


def resolve_thresholds_path(args: argparse.Namespace) -> Path:
    explicit = getattr(args, "tercile_thresholds_json", None)
    if explicit:
        return Path(explicit)
    registry, _error = read_json(Path(args.canonical_registry))
    configured = registry.get("numeric_tercile_thresholds_json")
    if not configured:
        return BASE_DIR / "__missing_canonical_numeric_tercile_thresholds_json__"
    return repo_relative_path(str(configured))


def normalize_threshold_args(args: argparse.Namespace) -> argparse.Namespace:
    args.tercile_thresholds_json = resolve_thresholds_path(args)
    return args


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "main": output_dir / OUTPUT_CSV,
        "child_commands": output_dir / OUTPUT_CHILD_COMMANDS,
        "child_results": output_dir / OUTPUT_CHILD_RESULTS,
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
    blocking_warning: bool,
) -> None:
    warnings.append(
        warning_row(
            run_id=args.run_id,
            warning_code=warning_code,
            message=message,
            source=source,
            blocking_warning=blocking_warning,
        )
    )


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [warning for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"]


def is_allowed_child_script(path: Path) -> bool:
    resolved = Path(path).resolve()
    name = path.name.lower()
    return resolved in ALLOWED_CHILD_SCRIPT_PATHS and not any(part in name for part in DISALLOWED_CHILD_NAME_PARTS)


def command_to_row(args: argparse.Namespace, command: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "child_step": command["child_step"],
        "command_index": command["command_index"],
        "command_executable": command["command"][0],
        "command_args_json": command["command"][1:],
        "planned_only": bool(args.dry_run),
        "allowed_child_script": command["allowed_child_script"],
        "check_mode": "single_shot_live_data_no_order_cycle",
        "caveat": command["caveat"],
    }


def child_output_dir(output_dir: Path, run_id: str) -> Path:
    return output_dir / "children" / f"demo_no_order_dry_run_{run_id}"


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def parse_time_server(value: Any) -> datetime | None:
    if value in ("", None):
        return None
    text = str(value).strip()
    candidates = [text, text.replace("Z", "+00:00")]
    if " " in text and "T" not in text:
        candidates.append(text.replace(" ", "T"))
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def inspect_latest_db_time_server(db_path: Path, table_name: str, symbol: str, timeframe: str) -> str:
    if not db_path.exists():
        return ""
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            if table_exists is None:
                return ""
            columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})")}
            if "time_server" not in columns:
                return ""
            filters: list[str] = []
            params: list[Any] = []
            if "symbol" in columns:
                filters.append(f"{quote_identifier('symbol')} = ?")
                params.append(symbol)
            if "timeframe" in columns:
                filters.append(f"{quote_identifier('timeframe')} = ?")
                params.append(timeframe)
            where = f" WHERE {' AND '.join(filters)}" if filters else ""
            query = f"SELECT MAX({quote_identifier('time_server')}) FROM {quote_identifier(table_name)}{where}"
            row = connection.execute(query, params).fetchone()
    except sqlite3.Error:
        return ""
    return str(row[0] or "") if row else ""


def inspect_db_refresh_times(args: argparse.Namespace) -> dict[str, str]:
    return {
        "latest_db_price_bar_time_server": inspect_latest_db_time_server(
            Path(args.feature_source_db),
            PRICE_BARS_TABLE,
            str(args.symbol),
            str(args.timeframe),
        ),
        "latest_db_feature_time_server": inspect_latest_db_time_server(
            Path(args.feature_source_db),
            PRICE_FEATURES_TABLE,
            str(args.symbol),
            str(args.timeframe),
        ),
    }


def resolve_dates(args: argparse.Namespace) -> tuple[str, str]:
    if args.from_date and args.to_date:
        return args.from_date, args.to_date
    to_dt = utc_now()
    from_dt = to_dt - timedelta(hours=float(args.lookback_hours))
    return format_utc(from_dt), format_utc(to_dt)


def resolve_effective_import_dates(
    args: argparse.Namespace,
    mt5_time_basis: dict[str, Any],
    before_times: dict[str, str],
) -> dict[str, Any]:
    fallback_from, fallback_to = resolve_dates(args)
    latest_mt5 = str(mt5_time_basis.get("latest_mt5_closed_bar_time_server") or "").strip()
    latest_mt5_dt = parse_time_server(latest_mt5)
    if latest_mt5_dt is None:
        return {
            "effective_import_from_date": fallback_from,
            "effective_import_from_date_source": "explicit_cli_from_date" if args.from_date else "pc_utc_lookback_fallback",
            "effective_import_to_date": fallback_to,
            "effective_import_to_date_source": "explicit_cli_to_date" if args.to_date else "pc_utc_now_fallback",
            "effective_import_date_caveat": "mt5_latest_closed_bar_unavailable",
        }

    latest_bar = str(before_times.get("latest_db_price_bar_time_server") or "").strip()
    latest_bar_dt = parse_time_server(latest_bar)
    if latest_bar_dt is not None:
        from_dt = latest_bar_dt - timedelta(hours=IMPORT_FROM_OVERLAP_HOURS)
        from_source = "latest_db_price_bar_time_server_minus_overlap"
    elif args.from_date:
        parsed_from = parse_time_server(args.from_date)
        from_dt = parsed_from or (latest_mt5_dt - timedelta(hours=float(args.lookback_hours)))
        from_source = "explicit_cli_from_date"
    else:
        from_dt = latest_mt5_dt - timedelta(hours=float(args.lookback_hours))
        from_source = "latest_mt5_closed_bar_time_server_minus_lookback"

    to_dt = latest_mt5_dt + timedelta(minutes=IMPORT_TO_INCLUSION_MINUTES)
    return {
        "effective_import_from_date": format_utc(from_dt),
        "effective_import_from_date_source": from_source,
        "effective_import_to_date": format_utc(to_dt),
        "effective_import_to_date_source": "latest_mt5_closed_bar_time_server",
        "effective_import_date_caveat": "mt5_bounded_import_window",
    }


def alignment_status_from_db_times(
    args: argparse.Namespace,
    mt5_time_basis: dict[str, Any],
    db_times: dict[str, str],
) -> dict[str, Any]:
    latest_mt5 = str(mt5_time_basis.get("latest_mt5_closed_bar_time_server") or "").strip()
    evidence: dict[str, Any] = {
        "latest_db_price_bar_time_server": str(db_times.get("latest_db_price_bar_time_server") or ""),
        "latest_db_feature_time_server": str(db_times.get("latest_db_feature_time_server") or ""),
        "db_lag_bars_vs_mt5_latest_closed_bar": None,
        "db_lag_minutes_vs_mt5_latest_closed_bar": None,
        "live_alignment_status": "live_data_mt5_time_basis_unavailable",
    }
    latest_mt5_dt = parse_time_server(latest_mt5)
    if latest_mt5_dt is None:
        return evidence

    bar_dt = parse_time_server(evidence["latest_db_price_bar_time_server"])
    feature_dt = parse_time_server(evidence["latest_db_feature_time_server"])
    if bar_dt is None or feature_dt is None:
        evidence["live_alignment_status"] = "live_data_mt5_alignment_unparseable"
        return evidence

    latest_db_dt = min(bar_dt, feature_dt)
    lag_minutes = (latest_mt5_dt - latest_db_dt).total_seconds() / 60.0
    lag_bars = lag_minutes / float(args.timeframe_minutes)
    evidence["db_lag_minutes_vs_mt5_latest_closed_bar"] = round(lag_minutes, 6)
    evidence["db_lag_bars_vs_mt5_latest_closed_bar"] = round(lag_bars, 6)
    tolerance_minutes = float(args.db_lag_tolerance_bars) * float(args.timeframe_minutes)
    if lag_minutes > tolerance_minutes:
        evidence["live_alignment_status"] = "live_data_blocked_db_lagging_mt5_latest_bar"
    elif lag_minutes < -float(args.timeframe_minutes):
        evidence["live_alignment_status"] = "live_data_blocked_db_ahead_of_mt5_latest_bar"
    else:
        evidence["live_alignment_status"] = "live_data_aligned_with_mt5_latest_bar"
    return evidence


def stdout_metric(child_results: list[dict[str, Any]], child_step: str, label: str) -> int | None:
    pattern = re.compile(rf"^{re.escape(label)}:\s*([0-9]+)\s*$", re.IGNORECASE)
    for result in child_results:
        if result.get("child_step") != child_step:
            continue
        for line in str(result.get("stdout_tail") or "").splitlines():
            match = pattern.match(line.strip())
            if match:
                return int(match.group(1))
    return None


def build_child_commands(
    args: argparse.Namespace,
    output_dir: Path,
    from_date: str,
    to_date: str,
    mt5_time_basis: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if mt5_time_basis is None:
        mt5_time_basis = mt5_time_basis_unavailable("not_checked_direct_command_build", dry_run=True)
    no_order_output_dir = child_output_dir(output_dir, args.run_id)
    commands = [
        {
            "child_step": "import_price_bars",
            "command_index": 1,
            "script": Path(CHILD_SCRIPT_PATHS["import_price_bars"]),
            "timeout_seconds": 120,
            "caveat": "reads MT5 bars and writes local price_bars only",
            "command": [
                str(args.python_executable),
                str(CHILD_SCRIPT_PATHS["import_price_bars"]),
                "--symbol",
                args.symbol,
                "--timeframe",
                args.timeframe,
                "--from-date",
                from_date,
                "--to-date",
                to_date,
                "--db-path",
                str(args.feature_source_db),
            ],
        },
        {
            "child_step": "generate_price_features",
            "command_index": 2,
            "script": Path(CHILD_SCRIPT_PATHS["generate_price_features"]),
            "timeout_seconds": 180,
            "caveat": "updates local price_features from local price_bars",
            "command": [
                str(args.python_executable),
                str(CHILD_SCRIPT_PATHS["generate_price_features"]),
                "--symbol",
                args.symbol,
                "--timeframe",
                args.timeframe,
                "--db-path",
                str(args.feature_source_db),
                "--strict-point-size",
            ],
        },
        {
            "child_step": "demo_no_order_dry_run",
            "command_index": 3,
            "script": Path(CHILD_SCRIPT_PATHS["demo_no_order_dry_run"]),
            "timeout_seconds": 120,
            "caveat": "emits would_skip/would_signal/would_block without broker request",
            "output_dir": no_order_output_dir,
            "command": [
                str(args.python_executable),
                str(CHILD_SCRIPT_PATHS["demo_no_order_dry_run"]),
                "--run-id",
                f"{args.run_id}_child_no_order_dry_run",
                "--demo-no-order-dry-run-plan-dir",
                str(args.demo_no_order_dry_run_plan_dir),
                "--demo-environment-check-dir",
                str(args.demo_environment_check_dir),
                "--demo-strategy-config",
                str(args.demo_strategy_config),
                "--demo-strategy-spec-dir",
                str(args.demo_strategy_spec_dir),
                "--tercile-thresholds-json",
                str(args.tercile_thresholds_json),
                "--feature-source-db",
                str(args.feature_source_db),
                "--feature-source-table",
                "price_features",
                "--symbol",
                args.symbol,
                "--timeframe",
                args.timeframe,
                "--max-staleness-hours",
                str(args.max_staleness_hours),
                "--timeframe-minutes",
                str(args.timeframe_minutes),
                "--db-lag-tolerance-bars",
                str(args.db_lag_tolerance_bars),
                "--require-mt5-alignment",
                "--mt5-time-basis-status",
                str(mt5_time_basis.get("mt5_time_basis_status") or ""),
                "--pc-utc-now",
                str(mt5_time_basis.get("pc_utc_now") or ""),
                "--mt5-tick-time-server",
                str(mt5_time_basis.get("mt5_tick_time_server") or ""),
                "--latest-mt5-closed-bar-time-server",
                str(mt5_time_basis.get("latest_mt5_closed_bar_time_server") or ""),
                "--mt5-server-time-offset-seconds-vs-pc-utc",
                str(mt5_time_basis.get("mt5_server_time_offset_seconds_vs_pc_utc") or ""),
                "--current-broker-spread-points",
                command_arg_value(mt5_time_basis.get("current_broker_spread_points")),
                "--current-broker-spread-source",
                command_arg_value(mt5_time_basis.get("current_broker_spread_source")),
                "--current-broker-spread-policy-max-points",
                command_arg_value(mt5_time_basis.get("current_broker_spread_policy_max_points"), EXPECTED_MAX_SPREAD_POINTS),
                "--output-dir",
                str(no_order_output_dir),
                "--overwrite",
            ],
        },
    ]
    for command in commands:
        command["allowed_child_script"] = is_allowed_child_script(Path(command["script"]))
    return commands


def load_inputs(args: argparse.Namespace) -> dict[str, Any]:
    config, config_error = read_json(Path(args.demo_strategy_config))
    plan_manifest, plan_error = read_json(Path(args.demo_no_order_dry_run_plan_dir) / PLAN_MANIFEST)
    env_manifest, env_error = read_json(Path(args.demo_environment_check_dir) / ENV_MANIFEST)
    return {
        "config": config,
        "config_error": config_error,
        "config_exists": Path(args.demo_strategy_config).exists(),
        "plan_manifest": plan_manifest,
        "plan_error": plan_error,
        "plan_exists": (Path(args.demo_no_order_dry_run_plan_dir) / PLAN_MANIFEST).exists(),
        "env_manifest": env_manifest,
        "env_error": env_error,
        "env_exists": (Path(args.demo_environment_check_dir) / ENV_MANIFEST).exists(),
    }


def config_boundary_safe(config: dict[str, Any]) -> bool:
    spread_unit = nested_get(config, "spread_and_session_controls", "spread_unit")
    max_spread_points = safe_float(nested_get(config, "spread_and_session_controls", "max_spread_points"))
    return (
        config.get("paper_only") is True
        and config.get("broker_connection_allowed") is False
        and config.get("order_execution_allowed") is False
        and config.get("real_money_allowed") is False
        and spread_unit == "broker_points"
        and max_spread_points == 15.0
    )


def environment_safe(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("environment_check_status") == "environment_check_available_with_caveats"
        and manifest.get("is_demo_account") is True
        and manifest.get("spread_policy_matches_canonical") is True
        and manifest.get("spread_within_config_gate") is True
    )


def plan_safe(manifest: dict[str, Any]) -> bool:
    return manifest.get("plan_status") == "demo_no_order_dry_run_plan_available_with_caveats"


def no_order_boundary_details(source: str, manifest: dict[str, Any]) -> dict[str, Any]:
    missing = [f"{source}:{flag}" for flag in NO_ORDER_FLAGS if flag not in manifest]
    unsafe = [
        {
            "source": source,
            "flag": flag,
            "observed_value": manifest.get(flag),
        }
        for flag in NO_ORDER_FLAGS
        if flag in manifest and manifest.get(flag) is not True
    ]
    return {
        "missing_no_order_flags": missing,
        "unsafe_no_order_flags": unsafe,
        "missing_no_order_flag_count": len(missing),
        "unsafe_no_order_flag_count": len(unsafe),
        "no_order_boundary_confirmed": not missing and not unsafe,
    }


def summarize_no_order_boundaries(manifests: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    missing: list[str] = []
    unsafe: list[dict[str, Any]] = []
    for source, manifest in manifests:
        details = no_order_boundary_details(source, manifest)
        missing.extend(details["missing_no_order_flags"])
        unsafe.extend(details["unsafe_no_order_flags"])
    return {
        "missing_no_order_flags": missing,
        "unsafe_no_order_flags": unsafe,
        "missing_no_order_flag_count": len(missing),
        "unsafe_no_order_flag_count": len(unsafe),
        "no_order_boundary_confirmed": not missing and not unsafe,
    }


def no_order_boundary_safe(manifest: dict[str, Any]) -> bool:
    return bool(no_order_boundary_details("manifest", manifest)["no_order_boundary_confirmed"])


def no_order_warning_message(summary: dict[str, Any]) -> str:
    if summary["missing_no_order_flag_count"]:
        return "Required no-order boundary flags are missing: " + "; ".join(summary["missing_no_order_flags"])
    unsafe_labels = [
        f"{item['source']}:{item['flag']}={item['observed_value']!r}"
        for item in summary["unsafe_no_order_flags"]
    ]
    return "Required no-order boundary flags are not exactly true: " + "; ".join(unsafe_labels)


def validate_inputs(args: argparse.Namespace, inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> str | None:
    if not inputs["config_exists"] or inputs["config_error"] or not config_boundary_safe(inputs["config"]):
        add_warning(warnings, args=args, warning_code="config_boundary_unsafe", message="Canonical config does not preserve spread15/no-order boundaries.", source=args.demo_strategy_config, blocking_warning=True)
        return "blocked_by_config_boundary"
    if not inputs["plan_exists"] or inputs["plan_error"] or not plan_safe(inputs["plan_manifest"]):
        add_warning(warnings, args=args, warning_code="plan_status_blocked", message="No-order dry-run plan is missing, unreadable, or not available.", source=args.demo_no_order_dry_run_plan_dir, blocking_warning=True)
        return "blocked_by_plan_status"
    if not inputs["env_exists"] or inputs["env_error"] or not environment_safe(inputs["env_manifest"]):
        add_warning(warnings, args=args, warning_code="environment_check_blocked", message="Environment check is missing, unreadable, or not acceptable.", source=args.demo_environment_check_dir, blocking_warning=True)
        return "blocked_by_environment_check_status"
    source_summary = summarize_no_order_boundaries(
        [
            ("plan_manifest", inputs["plan_manifest"]),
            ("environment_manifest", inputs["env_manifest"]),
        ]
    )
    if source_summary["missing_no_order_flag_count"]:
        add_warning(warnings, args=args, warning_code="missing_no_order_boundary_flag", message=no_order_warning_message(source_summary), source=args.demo_no_order_dry_run_plan_dir, blocking_warning=True)
        return "blocked_no_order_boundary_violation"
    if source_summary["unsafe_no_order_flag_count"]:
        add_warning(warnings, args=args, warning_code="unsafe_no_order_boundary_flag", message=no_order_warning_message(source_summary), source=args.demo_no_order_dry_run_plan_dir, blocking_warning=True)
        return "blocked_no_order_boundary_violation"
    return None


def tail_text(value: str, limit: int = 1000) -> str:
    value = value or ""
    return value[-limit:]


def run_child(command: dict[str, Any]) -> dict[str, Any]:
    started_dt = utc_now()
    started_at = started_dt.isoformat()
    try:
        result = subprocess.run(
            command["command"],
            shell=False,
            capture_output=True,
            text=True,
            check=False,
            timeout=int(command["timeout_seconds"]),
        )
        return_code = int(result.returncode)
        stdout_tail = tail_text(result.stdout or "")
        stderr_tail = tail_text(result.stderr or "")
        child_status = "success" if return_code == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        return_code = 124
        stdout_tail = tail_text(exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or ""))
        stderr_tail = tail_text(exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "timeout"))
        child_status = "failed"
    completed_dt = utc_now()
    return {
        "child_step": command["child_step"],
        "command_index": command["command_index"],
        "return_code": return_code,
        "started_at": started_at,
        "completed_at": completed_dt.isoformat(),
        "duration_seconds": (completed_dt - started_dt).total_seconds(),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "child_status": child_status,
        "blocking_warning": child_status != "success",
    }


def not_executed_result(command: dict[str, Any], status: str = "not_executed") -> dict[str, Any]:
    return {
        "child_step": command["child_step"],
        "command_index": command["command_index"],
        "return_code": "",
        "started_at": "",
        "completed_at": "",
        "duration_seconds": "",
        "stdout_tail": "",
        "stderr_tail": "",
        "child_status": status,
        "blocking_warning": False,
    }


def status_from_child_decision(decision_label: str) -> str:
    return {
        "would_skip": "demo_no_order_cycle_completed_would_skip",
        "would_signal": "demo_no_order_cycle_completed_would_signal",
        "would_block": "demo_no_order_cycle_completed_would_block",
    }.get(decision_label, "blocked_child_manifest_missing")


def recommended_next_step(status: str, child_manifest: dict[str, Any] | None = None) -> str:
    live_spread_status = str((child_manifest or {}).get("live_spread_gate_status") or "")
    if live_spread_status in {"blocked_current_spread_above_policy", "blocked_current_spread_unavailable"}:
        return "wait_for_current_spread_within_policy_and_rerun_live_shadow"
    return {
        "demo_no_order_cycle_plan_only": "run_demo_no_order_cycle_once_when_ready",
        "demo_no_order_cycle_completed_would_signal": "build_fixed_candidate_demo_would_signal_review",
        "demo_no_order_cycle_completed_would_skip": "monitor_next_feature_row_or_schedule_cycle",
        "demo_no_order_cycle_completed_would_block": "fix_demo_no_order_cycle_blocker",
    }.get(status, "fix_demo_no_order_cycle_blocker")


def main_row(args: argparse.Namespace, area: str, status: str, observed: Any, expected: Any, label: str, caveat: str, source: Path | str = "", warning_code: str = "", blocking: bool = False) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "cycle_area": area,
        "cycle_status": status,
        "artifact_status": "available" if not blocking else "blocked",
        "source_path": str(source),
        "observed_value": observed,
        "expected_value": expected,
        "evidence_label": label,
        "caveat": caveat,
        "warning_code": warning_code,
        "blocking_warning": blocking,
    }


def build_cycle(
    args: argparse.Namespace,
    output_dir: Path,
    commands: list[dict[str, Any]],
    inputs: dict[str, Any],
    warnings: list[dict[str, Any]],
    initial_status: str | None,
    mt5_time_basis: dict[str, Any],
    refresh_evidence: dict[str, Any],
) -> dict[str, Any]:
    child_results: list[dict[str, Any]] = []
    child_manifest: dict[str, Any] = {}
    latest_child_manifest_path = child_output_dir(output_dir, args.run_id) / NO_ORDER_CHILD_MANIFEST

    if initial_status:
        child_results = [not_executed_result(command, "not_executed_blocked") for command in commands]
        return {"cycle_status": initial_status, "child_results": child_results, "child_manifest": child_manifest, "latest_child_manifest_path": latest_child_manifest_path}

    if not all(command["allowed_child_script"] for command in commands):
        add_warning(warnings, args=args, warning_code="child_script_not_allowlisted", message="At least one child script is outside the allowlist.", source="child_commands", blocking_warning=True)
        child_results = [not_executed_result(command, "not_executed_blocked") for command in commands]
        return {"cycle_status": "blocked_child_command_failed", "child_results": child_results, "child_manifest": child_manifest, "latest_child_manifest_path": latest_child_manifest_path}

    if args.dry_run:
        child_results = [not_executed_result(command, "not_executed_dry_run") for command in commands]
        return {"cycle_status": "demo_no_order_cycle_plan_only", "child_results": child_results, "child_manifest": child_manifest, "latest_child_manifest_path": latest_child_manifest_path}

    for command in commands:
        if command["child_step"] == "generate_price_features":
            before_generation = inspect_db_refresh_times(args)
            refresh_evidence["latest_db_feature_time_server_before_generation"] = before_generation[
                "latest_db_feature_time_server"
            ]
        result = run_child(command)
        child_results.append(result)
        if result["child_status"] != "success":
            add_warning(warnings, args=args, warning_code="child_command_failed", message=f"Child command failed: {command['child_step']}.", source=command["script"], blocking_warning=True)
            remaining = [later for later in commands if int(later["command_index"]) > int(command["command_index"])]
            child_results.extend(not_executed_result(later, "not_executed_after_failure") for later in remaining)
            return {"cycle_status": "blocked_child_command_failed", "child_results": child_results, "child_manifest": child_manifest, "latest_child_manifest_path": latest_child_manifest_path}
        if command["child_step"] == "import_price_bars":
            after_import = inspect_db_refresh_times(args)
            refresh_evidence["latest_db_price_bar_time_server_after_import"] = after_import[
                "latest_db_price_bar_time_server"
            ]
        elif command["child_step"] == "generate_price_features":
            after_generation = inspect_db_refresh_times(args)
            refresh_evidence["latest_db_feature_time_server_after_generation"] = after_generation[
                "latest_db_feature_time_server"
            ]
            refresh_evidence.update(alignment_status_from_db_times(args, mt5_time_basis, after_generation))

    child_manifest, manifest_error = read_json(latest_child_manifest_path)
    refresh_evidence["imported_rows_count"] = stdout_metric(child_results, "import_price_bars", "Rows inserted")
    refresh_evidence["generated_features_count"] = stdout_metric(child_results, "generate_price_features", "Rows generated")
    if manifest_error or not latest_child_manifest_path.exists():
        add_warning(warnings, args=args, warning_code="child_manifest_missing", message="No-order dry-run child manifest is missing or unreadable.", source=latest_child_manifest_path, blocking_warning=True)
        return {"cycle_status": "blocked_child_manifest_missing", "child_results": child_results, "child_manifest": child_manifest, "latest_child_manifest_path": latest_child_manifest_path}
    child_summary = summarize_no_order_boundaries([("child_manifest", child_manifest)])
    if child_summary["missing_no_order_flag_count"]:
        add_warning(warnings, args=args, warning_code="missing_no_order_boundary_flag", message=no_order_warning_message(child_summary), source=latest_child_manifest_path, blocking_warning=True)
        return {"cycle_status": "blocked_no_order_boundary_violation", "child_results": child_results, "child_manifest": child_manifest, "latest_child_manifest_path": latest_child_manifest_path}
    if child_summary["unsafe_no_order_flag_count"]:
        add_warning(warnings, args=args, warning_code="unsafe_no_order_boundary_flag", message=no_order_warning_message(child_summary), source=latest_child_manifest_path, blocking_warning=True)
        return {"cycle_status": "blocked_no_order_boundary_violation", "child_results": child_results, "child_manifest": child_manifest, "latest_child_manifest_path": latest_child_manifest_path}
    refresh_status = str(refresh_evidence.get("live_alignment_status") or "")
    if refresh_status in {
        "live_data_blocked_db_lagging_mt5_latest_bar",
        "live_data_blocked_db_ahead_of_mt5_latest_bar",
        "live_data_mt5_alignment_unparseable",
    }:
        add_warning(
            warnings,
            args=args,
            warning_code=refresh_status,
            message="DB price bars/features remain out of alignment with the latest MT5 closed bar after refresh.",
            source=args.feature_source_db,
            blocking_warning=True,
        )
        return {
            "cycle_status": "demo_no_order_cycle_completed_would_block",
            "child_results": child_results,
            "child_manifest": child_manifest,
            "latest_child_manifest_path": latest_child_manifest_path,
        }
    return {
        "cycle_status": status_from_child_decision(str(child_manifest.get("decision_label") or "")),
        "child_results": child_results,
        "child_manifest": child_manifest,
        "latest_child_manifest_path": latest_child_manifest_path,
    }


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    commands: list[dict[str, Any]],
    child_results: list[dict[str, Any]],
    cycle_status: str,
    child_manifest: dict[str, Any],
    no_order_summary: dict[str, Any],
    from_date: str,
    to_date: str,
    mt5_time_basis: dict[str, Any],
    refresh_evidence: dict[str, Any],
) -> None:
    unsafe_labels = [
        f"{item['source']}:{item['flag']}={item['observed_value']!r}"
        for item in no_order_summary["unsafe_no_order_flags"]
    ]
    lines = [
        "# Fixed Candidate Demo No-Order Cycle Once",
        "",
        "Single-shot live-data no-order cycle. It does not loop or schedule itself.",
        "MT5 bar import may read bars, but no orders are sent.",
        "No broker order execution was performed.",
        "No order request was constructed.",
        "No order_check or order_calc call was performed.",
        "No replay, cost sensitivity, recent holdout, or paper workflow was run.",
        "No optimization or parameter search was performed.",
        "This cycle is not future-performance proof.",
        "This cycle is not demo broker approval.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- symbol: `{args.symbol}`",
        f"- timeframe: `{args.timeframe}`",
        f"- feature_source_db: `{args.feature_source_db}`",
        f"- canonical_registry: `{args.canonical_registry}`",
        f"- numeric_tercile_thresholds_json: `{args.tercile_thresholds_json}`",
        f"- child_threshold_lineage: `{child_manifest.get('threshold_lineage', '')}`",
        f"- child_threshold_schema_label: `{child_manifest.get('threshold_schema_label', '')}`",
        f"- from_date: `{from_date}`",
        f"- to_date: `{to_date}`",
        f"- db_refresh_before_shadow_enabled: `{refresh_evidence.get('db_refresh_before_shadow_enabled', '')}`",
        f"- mt5_time_basis_checked: `{refresh_evidence.get('mt5_time_basis_checked', '')}`",
        f"- mt5_time_basis_status: `{mt5_time_basis.get('mt5_time_basis_status', '')}`",
        f"- mt5_tick_time_server: `{mt5_time_basis.get('mt5_tick_time_server', '')}`",
        f"- latest_mt5_closed_bar_time_server: `{mt5_time_basis.get('latest_mt5_closed_bar_time_server', '')}`",
        f"- mt5_server_time_offset_seconds_vs_pc_utc: `{mt5_time_basis.get('mt5_server_time_offset_seconds_vs_pc_utc', '')}`",
        f"- current_broker_spread_points: `{mt5_time_basis.get('current_broker_spread_points', '')}`",
        f"- current_broker_spread_source: `{mt5_time_basis.get('current_broker_spread_source', '')}`",
        f"- current_broker_spread_within_policy: `{mt5_time_basis.get('current_broker_spread_within_policy', '')}`",
        f"- live_spread_gate_status: `{mt5_time_basis.get('live_spread_gate_status', '')}`",
        "",
        "## Refresh Before Shadow",
        "",
        f"- latest_db_price_bar_time_server_before_import: `{refresh_evidence.get('latest_db_price_bar_time_server_before_import', '')}`",
        f"- latest_db_feature_time_server_before_generation: `{refresh_evidence.get('latest_db_feature_time_server_before_generation', '')}`",
        f"- effective_import_from_date: `{refresh_evidence.get('effective_import_from_date', '')}`",
        f"- effective_import_from_date_source: `{refresh_evidence.get('effective_import_from_date_source', '')}`",
        f"- effective_import_to_date: `{refresh_evidence.get('effective_import_to_date', '')}`",
        f"- effective_import_to_date_source: `{refresh_evidence.get('effective_import_to_date_source', '')}`",
        f"- latest_db_price_bar_time_server_after_import: `{refresh_evidence.get('latest_db_price_bar_time_server_after_import', '')}`",
        f"- latest_db_feature_time_server_after_generation: `{refresh_evidence.get('latest_db_feature_time_server_after_generation', '')}`",
        f"- imported_rows_count: `{refresh_evidence.get('imported_rows_count', '')}`",
        f"- generated_features_count: `{refresh_evidence.get('generated_features_count', '')}`",
        f"- db_lag_bars_vs_mt5_latest_closed_bar: `{refresh_evidence.get('db_lag_bars_vs_mt5_latest_closed_bar', '')}`",
        f"- db_lag_minutes_vs_mt5_latest_closed_bar: `{refresh_evidence.get('db_lag_minutes_vs_mt5_latest_closed_bar', '')}`",
        f"- live_alignment_status: `{refresh_evidence.get('live_alignment_status', '')}`",
        "",
        "## Child Command Plan",
        "",
    ]
    for command in commands:
        lines.append(f"- {command['child_step']}: `{subprocess.list2cmdline([str(item) for item in command['command']])}`")
    lines.extend(["", "## Child Execution Summary", ""])
    for result in child_results:
        lines.append(f"- {result['child_step']}: `{result['child_status']}` return_code=`{result['return_code']}`")
    lines.extend(
        [
            "",
            "## Final No-Order Dry-Run Decision Summary",
            "",
            f"- child_decision_label: `{child_manifest.get('decision_label', '')}`",
            f"- child_dry_run_status: `{child_manifest.get('dry_run_status', '')}`",
            f"- child_feature_row_fresh: `{child_manifest.get('feature_row_fresh', '')}`",
            f"- child_evaluated_feature_time_server: `{child_manifest.get('evaluated_feature_time_server', child_manifest.get('time_server', ''))}`",
            f"- child_latest_db_price_bar_time_server: `{child_manifest.get('latest_db_price_bar_time_server', '')}`",
            f"- child_latest_db_feature_time_server: `{child_manifest.get('latest_db_feature_time_server', '')}`",
            f"- child_latest_mt5_closed_bar_time_server: `{child_manifest.get('latest_mt5_closed_bar_time_server', '')}`",
            f"- child_db_lag_bars_vs_mt5_latest_closed_bar: `{child_manifest.get('db_lag_bars_vs_mt5_latest_closed_bar', '')}`",
            f"- child_live_alignment_status: `{child_manifest.get('live_alignment_status', '')}`",
            f"- child_feature_row_spread_broker_points: `{child_manifest.get('feature_row_spread_broker_points', child_manifest.get('spread', ''))}`",
            f"- child_feature_row_spread_source: `{child_manifest.get('feature_row_spread_source', child_manifest.get('spread_source', ''))}`",
            f"- child_current_broker_spread_points: `{child_manifest.get('current_broker_spread_points', '')}`",
            f"- child_current_broker_spread_source: `{child_manifest.get('current_broker_spread_source', '')}`",
            f"- child_current_broker_spread_within_policy: `{child_manifest.get('current_broker_spread_within_policy', '')}`",
            f"- child_live_spread_gate_status: `{child_manifest.get('live_spread_gate_status', '')}`",
            "",
            "## No-Order Boundary Summary",
            "",
            f"- no_order_boundary_confirmed: `{bool_text(bool(no_order_summary['no_order_boundary_confirmed']))}`",
            f"- missing_no_order_flag_count: `{no_order_summary['missing_no_order_flag_count']}`",
            f"- unsafe_no_order_flag_count: `{no_order_summary['unsafe_no_order_flag_count']}`",
            f"- missing_no_order_flags: `{';'.join(no_order_summary['missing_no_order_flags'])}`",
            f"- unsafe_no_order_flags: `{';'.join(unsafe_labels)}`",
            "",
            "## Cycle Status",
            "",
            f"`{cycle_status}`",
            "",
            "## Recommended Next Step",
            "",
            f"`{recommended_next_step(cycle_status, child_manifest)}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    from_date: str,
    to_date: str,
    cycle_status: str,
    commands: list[dict[str, Any]],
    child_results: list[dict[str, Any]],
    child_manifest: dict[str, Any],
    inputs: dict[str, Any],
    no_order_summary: dict[str, Any],
    warnings: list[dict[str, Any]],
    latest_child_manifest_path: Path,
    mt5_time_basis: dict[str, Any],
    refresh_evidence: dict[str, Any],
) -> None:
    executed_steps = {result["child_step"] for result in child_results if result["child_status"] == "success"}
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "feature_source_db": str(args.feature_source_db),
        "canonical_registry": str(args.canonical_registry),
        "numeric_tercile_thresholds_json": str(args.tercile_thresholds_json),
        "threshold_lineage": child_manifest.get("threshold_lineage", ""),
        "calibration_scope": child_manifest.get("calibration_scope", ""),
        "full_sample_thresholds_used": child_manifest.get("full_sample_thresholds_used"),
        "oos_rows_used_for_thresholds": child_manifest.get("oos_rows_used_for_thresholds"),
        "threshold_schema_label": child_manifest.get("threshold_schema_label", ""),
        "legacy_full_sample_thresholds_allowed": child_manifest.get("legacy_full_sample_thresholds_allowed", False),
        "from_date": from_date,
        "to_date": to_date,
        "db_refresh_before_shadow_enabled": refresh_evidence.get("db_refresh_before_shadow_enabled"),
        "mt5_time_basis_checked": refresh_evidence.get("mt5_time_basis_checked"),
        "latest_db_price_bar_time_server_before_import": refresh_evidence.get("latest_db_price_bar_time_server_before_import"),
        "latest_db_feature_time_server_before_generation": refresh_evidence.get("latest_db_feature_time_server_before_generation"),
        "latest_db_feature_time_server_before_import": refresh_evidence.get("latest_db_feature_time_server_before_import"),
        "effective_import_from_date": refresh_evidence.get("effective_import_from_date"),
        "effective_import_from_date_source": refresh_evidence.get("effective_import_from_date_source"),
        "effective_import_to_date": refresh_evidence.get("effective_import_to_date"),
        "effective_import_to_date_source": refresh_evidence.get("effective_import_to_date_source"),
        "effective_import_date_caveat": refresh_evidence.get("effective_import_date_caveat"),
        "latest_db_price_bar_time_server_after_import": refresh_evidence.get("latest_db_price_bar_time_server_after_import"),
        "latest_db_feature_time_server_after_generation": refresh_evidence.get("latest_db_feature_time_server_after_generation"),
        "latest_db_price_bar_time_server": refresh_evidence.get("latest_db_price_bar_time_server_after_import"),
        "latest_db_feature_time_server": refresh_evidence.get("latest_db_feature_time_server_after_generation"),
        "imported_rows_count": refresh_evidence.get("imported_rows_count"),
        "generated_features_count": refresh_evidence.get("generated_features_count"),
        "db_lag_bars_vs_mt5_latest_closed_bar": refresh_evidence.get("db_lag_bars_vs_mt5_latest_closed_bar"),
        "db_lag_minutes_vs_mt5_latest_closed_bar": refresh_evidence.get("db_lag_minutes_vs_mt5_latest_closed_bar"),
        "live_alignment_status": refresh_evidence.get("live_alignment_status"),
        "time_server_source": mt5_time_basis.get("time_server_source", "raw_broker_server_time_or_existing_db_time_server"),
        "import_time_basis": mt5_time_basis.get("import_time_basis", "mt5_time_basis_unavailable"),
        "pc_utc_now": mt5_time_basis.get("pc_utc_now", ""),
        "mt5_time_basis_status": mt5_time_basis.get("mt5_time_basis_status", ""),
        "mt5_alignment_checked": mt5_time_basis.get("mt5_alignment_checked", False),
        "mt5_time_basis_unavailable_reason": mt5_time_basis.get("mt5_time_basis_unavailable_reason", ""),
        "mt5_tick_time_server": mt5_time_basis.get("mt5_tick_time_server", ""),
        "latest_mt5_closed_bar_time_server": mt5_time_basis.get("latest_mt5_closed_bar_time_server", ""),
        "mt5_server_time_offset_seconds_vs_pc_utc": mt5_time_basis.get("mt5_server_time_offset_seconds_vs_pc_utc"),
        "mt5_time_basis_caveat": mt5_time_basis.get("mt5_time_basis_caveat", ""),
        "current_broker_spread_points": mt5_time_basis.get("current_broker_spread_points"),
        "current_broker_spread_source": mt5_time_basis.get("current_broker_spread_source"),
        "current_broker_spread_within_policy": mt5_time_basis.get("current_broker_spread_within_policy"),
        "current_broker_spread_policy_max_points": mt5_time_basis.get("current_broker_spread_policy_max_points"),
        "live_spread_gate_status": mt5_time_basis.get("live_spread_gate_status"),
        "lookback_hours": float(args.lookback_hours),
        "max_staleness_hours": float(args.max_staleness_hours),
        "timeframe_minutes": float(args.timeframe_minutes),
        "db_lag_tolerance_bars": float(args.db_lag_tolerance_bars),
        "dry_run": bool(args.dry_run),
        "cycle_status": cycle_status,
        "spread_unit": nested_get(inputs["config"], "spread_and_session_controls", "spread_unit"),
        "max_spread_points": safe_float(nested_get(inputs["config"], "spread_and_session_controls", "max_spread_points")),
        "spread_policy_matches_canonical": config_boundary_safe(inputs["config"]),
        "child_command_count": len(commands),
        "child_success_count": sum(1 for result in child_results if result["child_status"] == "success"),
        "child_failure_count": sum(1 for result in child_results if result["child_status"] == "failed"),
        "no_order_dry_run_child_output_dir": str(child_output_dir(output_dir, args.run_id)),
        "child_decision_label": child_manifest.get("decision_label"),
        "child_dry_run_status": child_manifest.get("dry_run_status"),
        "child_feature_row_fresh": child_manifest.get("feature_row_fresh"),
        "child_time_server": child_manifest.get("time_server"),
        "child_evaluated_feature_time_server": child_manifest.get("evaluated_feature_time_server", child_manifest.get("time_server")),
        "child_latest_db_price_bar_time_server": child_manifest.get("latest_db_price_bar_time_server"),
        "child_latest_db_feature_time_server": child_manifest.get("latest_db_feature_time_server"),
        "child_latest_mt5_closed_bar_time_server": child_manifest.get("latest_mt5_closed_bar_time_server"),
        "child_db_lag_bars_vs_mt5_latest_closed_bar": child_manifest.get("db_lag_bars_vs_mt5_latest_closed_bar"),
        "child_db_lag_minutes_vs_mt5_latest_closed_bar": child_manifest.get("db_lag_minutes_vs_mt5_latest_closed_bar"),
        "child_live_alignment_status": child_manifest.get("live_alignment_status"),
        "child_session_observed": child_manifest.get("session_observed"),
        "child_spread": child_manifest.get("spread"),
        "child_feature_row_spread_broker_points": child_manifest.get("feature_row_spread_broker_points", child_manifest.get("spread")),
        "child_feature_row_spread_source": child_manifest.get("feature_row_spread_source", child_manifest.get("spread_source")),
        "child_current_broker_spread_points": child_manifest.get("current_broker_spread_points"),
        "child_current_broker_spread_source": child_manifest.get("current_broker_spread_source"),
        "child_current_broker_spread_within_policy": child_manifest.get("current_broker_spread_within_policy"),
        "child_current_broker_spread_policy_max_points": child_manifest.get("current_broker_spread_policy_max_points"),
        "child_live_spread_gate_status": child_manifest.get("live_spread_gate_status"),
        "child_spread_source": child_manifest.get("spread_source"),
        "child_spread_within_gate": child_manifest.get("spread_within_gate"),
        "child_close_to_ma_fast_atr_20_bucket": child_manifest.get("close_to_ma_fast_atr_20_bucket"),
        "child_tick_volume_percentile_100_bucket": child_manifest.get("tick_volume_percentile_100_bucket"),
        "child_skip_reason_count": child_manifest.get("skip_reason_count"),
        "child_block_reason_count": child_manifest.get("block_reason_count"),
        "recommended_next_step": recommended_next_step(cycle_status, child_manifest),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "missing_no_order_flag_count": no_order_summary["missing_no_order_flag_count"],
        "unsafe_no_order_flag_count": no_order_summary["unsafe_no_order_flag_count"],
        "no_order_boundary_confirmed": no_order_summary["no_order_boundary_confirmed"],
        "missing_no_order_flags": no_order_summary["missing_no_order_flags"],
        "unsafe_no_order_flags": no_order_summary["unsafe_no_order_flags"],
        "latest_child_manifest_path": str(latest_child_manifest_path),
        "mt5_bar_import_child_executed": "import_price_bars" in executed_steps,
        "price_feature_generation_child_executed": "generate_price_features" in executed_steps,
        "no_order_dry_run_child_executed": "demo_no_order_dry_run" in executed_steps,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
        "no_replay_rerun": True,
        "no_cost_sensitivity_rerun": True,
        "no_recent_holdout_rerun": True,
        "no_paper_signal_logger_run": True,
        "no_paper_trade_tracker_run": True,
        "no_paper_orchestrator_run": True,
        "no_optimization_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    normalize_threshold_args(args)
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    mt5_time_basis = mt5_time_basis_unavailable("not_checked_dry_run", dry_run=True) if args.dry_run else collect_mt5_time_basis(args)
    before_refresh_times = inspect_db_refresh_times(args)
    import_window = resolve_effective_import_dates(args, mt5_time_basis, before_refresh_times)
    from_date = str(import_window["effective_import_from_date"])
    to_date = str(import_window["effective_import_to_date"])
    refresh_evidence: dict[str, Any] = {
        "db_refresh_before_shadow_enabled": True,
        "mt5_time_basis_checked": bool(mt5_time_basis.get("mt5_alignment_checked")),
        "latest_db_price_bar_time_server_before_import": before_refresh_times["latest_db_price_bar_time_server"],
        "latest_db_feature_time_server_before_generation": before_refresh_times["latest_db_feature_time_server"],
        "latest_db_feature_time_server_before_import": before_refresh_times["latest_db_feature_time_server"],
        "latest_db_price_bar_time_server_after_import": "",
        "latest_db_feature_time_server_after_generation": "",
        "imported_rows_count": None,
        "generated_features_count": None,
        **import_window,
        **alignment_status_from_db_times(args, mt5_time_basis, before_refresh_times),
    }
    inputs = load_inputs(args)
    warnings: list[dict[str, Any]] = []
    initial_status = validate_inputs(args, inputs, warnings)
    commands = build_child_commands(args, output_dir, from_date, to_date, mt5_time_basis)
    cycle = build_cycle(args, output_dir, commands, inputs, warnings, initial_status, mt5_time_basis, refresh_evidence)
    cycle_status = str(cycle["cycle_status"])
    child_results = list(cycle["child_results"])
    child_manifest = dict(cycle["child_manifest"])
    latest_child_manifest_path = Path(cycle["latest_child_manifest_path"])
    no_order_manifests = [
        ("plan_manifest", inputs["plan_manifest"]),
        ("environment_manifest", inputs["env_manifest"]),
    ]
    if child_manifest:
        no_order_manifests.append(("child_manifest", child_manifest))
    no_order_summary = summarize_no_order_boundaries(no_order_manifests)
    main_rows = [
        main_row(args, "config_gate", cycle_status, config_boundary_safe(inputs["config"]), "true", "config_spread_policy_confirmed", "spread15 broker_points"),
        main_row(args, "plan_gate", cycle_status, inputs["plan_manifest"].get("plan_status", ""), "demo_no_order_dry_run_plan_available_with_caveats", "plan_status_confirmed", "artifact input"),
        main_row(args, "environment_gate", cycle_status, inputs["env_manifest"].get("environment_check_status", ""), "environment_check_available_with_caveats", "environment_check_confirmed", "artifact input"),
        main_row(args, "db_refresh_before_shadow", cycle_status, refresh_evidence.get("db_refresh_before_shadow_enabled"), "true", "db_refresh_before_shadow_enabled", "single_shot_refresh"),
        main_row(args, "mt5_time_basis", cycle_status, refresh_evidence.get("mt5_time_basis_checked"), "true", "mt5_time_basis_checked", "required_for_mt5_bounded_import"),
        main_row(args, "effective_import_window", cycle_status, {"from": from_date, "to": to_date, "to_source": refresh_evidence.get("effective_import_to_date_source")}, "latest_mt5_closed_bar_time_server", "effective_import_dates", "preserves_raw_time_server_labels"),
        main_row(args, "db_refresh_alignment", cycle_status, {"latest_bar": refresh_evidence.get("latest_db_price_bar_time_server_after_import"), "latest_feature": refresh_evidence.get("latest_db_feature_time_server_after_generation"), "lag_bars": refresh_evidence.get("db_lag_bars_vs_mt5_latest_closed_bar")}, "aligned_with_latest_mt5_closed_bar", "live_alignment_status", str(refresh_evidence.get("live_alignment_status") or "")),
        main_row(args, "child_command_plan", cycle_status, len(commands), "3", "allowed_child_scripts_planned", "single_shot_only"),
        main_row(args, "cycle_outcome", cycle_status, cycle_status, "allowed cycle status", "no_order_cycle_status_emitted", "no_demo_broker_approval_performed", warning_code=cycle_status if cycle_status.startswith("blocked") else "", blocking=cycle_status.startswith("blocked")),
    ]
    command_rows = [command_to_row(args, command) for command in commands]
    write_csv(paths["main"], main_rows, MAIN_FIELDNAMES)
    write_csv(paths["child_commands"], command_rows, COMMAND_FIELDNAMES)
    write_csv(paths["child_results"], child_results, RESULT_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(
        paths["report"],
        args=args,
        commands=commands,
        child_results=child_results,
        cycle_status=cycle_status,
        child_manifest=child_manifest,
        no_order_summary=no_order_summary,
        from_date=from_date,
        to_date=to_date,
        mt5_time_basis=mt5_time_basis,
        refresh_evidence=refresh_evidence,
    )
    write_manifest(
        paths["manifest"],
        args=args,
        output_dir=output_dir,
        from_date=from_date,
        to_date=to_date,
        cycle_status=cycle_status,
        commands=commands,
        child_results=child_results,
        child_manifest=child_manifest,
        inputs=inputs,
        no_order_summary=no_order_summary,
        warnings=warnings,
        latest_child_manifest_path=latest_child_manifest_path,
        mt5_time_basis=mt5_time_basis,
        refresh_evidence=refresh_evidence,
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one controlled live-data no-order cycle for the fixed candidate.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--feature-source-db", type=Path, default=DEFAULT_FEATURE_SOURCE_DB)
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--lookback-hours", type=float, default=72.0)
    parser.add_argument("--max-staleness-hours", type=float, default=24.0)
    parser.add_argument("--timeframe-minutes", type=float, default=15.0)
    parser.add_argument("--db-lag-tolerance-bars", type=float, default=1.0)
    parser.add_argument("--demo-no-order-dry-run-plan-dir", type=Path, default=DEFAULT_DEMO_NO_ORDER_DRY_RUN_PLAN_DIR)
    parser.add_argument("--demo-environment-check-dir", type=Path, default=DEFAULT_DEMO_ENVIRONMENT_CHECK_DIR)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--tercile-thresholds-json", type=Path)
    parser.add_argument("--state-json", type=Path, default=DEFAULT_STATE_JSON)
    parser.add_argument("--python-executable", default="python")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate demo no-order cycle once failed: {exc}")
        return 1
    print("Fixed-candidate demo no-order cycle once complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
