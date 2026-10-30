"""Compute OOS outcomes for fixed-candidate train-only threshold matches.

This focused diagnostic reads SQLite through a read-only URI, reads a frozen
train-only numeric-tercile threshold artifact, identifies OOS rule matches, and
simulates fixed short TP/SL/horizon outcomes from local price path columns. It
does not mutate config or DB state, call MT5/broker/order APIs, run child
pipelines, or create execution instructions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_train_only_threshold_oos_outcome_replay_v1"
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_FEATURE_TABLE = "price_features"
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_TRAIN_ONLY_THRESHOLDS = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_train_only_numeric_tercile_thresholds"
    / "gbpusd_short_h10_1_5_off_hours_train_only_numeric_tercile_thresholds_train_to_2024_12_31_v1"
    / "fixed_candidate_train_only_numeric_tercile_thresholds.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_train_only_threshold_oos_outcome_replay"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_DIRECTION = "short"
DEFAULT_SESSION_COLUMN = "hour_session"
DEFAULT_REQUIRED_SESSION = "Off_hours"
DEFAULT_MAX_SPREAD_POINTS = 15.0
FEATURE_A = "close_to_ma_fast_atr_20"
FEATURE_B = "tick_volume_percentile_100"
ATR_COLUMN = "atr_20"
TP_ATR = 1.5
SL_ATR = 1.0
HORIZON_BARS = 10
SAME_BAR_POLICY = "stop_first"
EXPECTED_REQUIRED_CONDITIONS = {
    FEATURE_A: "high_tercile",
    FEATURE_B: "mid_tercile",
}

STATUS_AVAILABLE = "train_only_threshold_oos_outcome_replay_available"
STATUS_MISSING_THRESHOLD = "train_only_threshold_oos_outcome_replay_blocked_missing_threshold_artifact"
STATUS_NON_TRAIN_ONLY = "train_only_threshold_oos_outcome_replay_blocked_non_train_only_thresholds"
STATUS_MISSING_DB = "train_only_threshold_oos_outcome_replay_blocked_missing_db"
STATUS_MISSING_TABLE = "train_only_threshold_oos_outcome_replay_blocked_missing_table"
STATUS_MISSING_COLUMNS = "train_only_threshold_oos_outcome_replay_blocked_missing_columns"
STATUS_EMPTY_OOS = "train_only_threshold_oos_outcome_replay_blocked_empty_oos_window"
STATUS_NONCANONICAL = "train_only_threshold_oos_outcome_replay_blocked_noncanonical_candidate"
STATUS_OUTPUT_EXISTS = "train_only_threshold_oos_outcome_replay_blocked_output_exists_without_overwrite"

OUTPUT_FILES = {
    "manifest": "manifest.json",
    "report": "report.md",
    "summary": "summary.csv",
    "trades": "trades.csv",
    "equity_curve": "equity_curve.csv",
    "condition_counts": "condition_counts.csv",
    "bucket_counts": "bucket_counts.csv",
    "warnings": "warnings.csv",
    "no_order_evidence": "no_order_evidence.csv",
}

WARNING_FIELDS = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
SUMMARY_FIELDS = [
    "run_id",
    "replay_status",
    "candidate_id",
    "symbol",
    "timeframe",
    "train_end_time",
    "oos_start_time",
    "oos_end_time",
    "oos_row_count",
    "off_hours_oos_row_count",
    "rule_match_count",
    "trade_count",
    "mean_R",
    "median_R",
    "sum_R",
    "profit_factor_R",
    "win_rate_R_positive",
    "max_drawdown_R",
    "tp_hit_count",
    "sl_hit_count",
    "timeout_count",
    "timeout_rate",
]
TRADE_FIELDS = [
    "run_id",
    "trade_index",
    "signal_id",
    "entry_time_server",
    "exit_time_server",
    "entry_price",
    "exit_price",
    "tp_price",
    "sl_price",
    "direction",
    "exit_reason",
    "R_multiple",
    "bars_elapsed",
    "horizon_bars",
    "same_bar_policy",
    "spread",
    FEATURE_A,
    f"{FEATURE_A}_bucket",
    FEATURE_B,
    f"{FEATURE_B}_bucket",
]
EQUITY_FIELDS = [
    "run_id",
    "trade_index",
    "signal_id",
    "exit_time_server",
    "exit_reason",
    "R_multiple",
    "cumulative_R",
    "peak_cumulative_R",
    "drawdown_R",
]
COUNT_FIELDS = ["name", "bucket_or_condition", "count"]

NO_ORDER_EVIDENCE = {
    "no_mt5_import_performed": True,
    "no_mt5_connection_performed": True,
    "no_broker_api_query_performed": True,
    "no_order_check_called": True,
    "no_order_send_called": True,
    "no_order_calc_margin_called": True,
    "no_order_calc_profit_called": True,
    "no_positions_get_called": True,
    "no_orders_get_called": True,
    "no_history_orders_get_called": True,
    "no_history_deals_get_called": True,
    "no_order_execution_performed": True,
    "no_broker_payload_constructed": True,
    "no_executable_order_object_constructed": True,
    "no_db_mutation_performed": True,
    "no_future_state_json_written": True,
    "no_child_scripts_executed": True,
    "no_scheduler_added": True,
    "no_loop_added": True,
    "no_background_task_added": True,
    "no_trading_decision_performed": True,
}


@dataclass(frozen=True)
class BlockedStatusError(Exception):
    status: str
    message: str

    def __str__(self) -> str:
        return f"{self.status}: {self.message}"


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def read_json_object(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(payload, dict):
        return {}, "JSON root is not an object"
    return payload, ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


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
        "blocking_warning": blocking_warning,
    }


def output_dir_for_args(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    return DEFAULT_OUTPUT_ROOT / str(args.run_id)


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {label: output_dir / file_name for label, file_name in OUTPUT_FILES.items()}


def ensure_output_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = output_paths(output_dir)
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise BlockedStatusError(STATUS_OUTPUT_EXISTS, "Output files already exist; use --overwrite.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def connect_read_only(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def inspect_table(db_path: Path, table_name: str) -> tuple[bool, set[str], str]:
    if not db_path.exists():
        return False, set(), "missing_db"
    try:
        with connect_read_only(db_path) as connection:
            exists = (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone()
                is not None
            )
            if not exists:
                return False, set(), ""
            columns = {
                str(row[1])
                for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
            }
            return True, columns, ""
    except sqlite3.Error as exc:
        return False, set(), str(exc)


def where_clause(filters: list[str]) -> str:
    return "" if not filters else " WHERE " + " AND ".join(filters)


def parse_time_text(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def plus_one_second_text(value: str) -> str:
    parsed = parse_time_text(value)
    if parsed is None:
        return value
    return (parsed + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")


def one_row_window_query(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    filters: list[str],
    params: list[Any],
) -> dict[str, Any]:
    query = (
        "SELECT "
        "COUNT(*) AS row_count, "
        f"MIN({quote_identifier('time_server')}) AS min_time_server, "
        f"MAX({quote_identifier('time_server')}) AS max_time_server "
        f"FROM {quote_identifier(table_name)}"
        f"{where_clause(filters)}"
    )
    row = connection.execute(query, params).fetchone()
    return {
        "row_count": int(row["row_count"] or 0) if row else 0,
        "min_time_server": str(row["min_time_server"] or "") if row else "",
        "max_time_server": str(row["max_time_server"] or "") if row else "",
    }


def source_filters(args: argparse.Namespace, columns: set[str]) -> tuple[list[str], list[Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if "symbol" in columns:
        filters.append(f"{quote_identifier('symbol')} = ?")
        params.append(str(args.symbol))
    if "timeframe" in columns:
        filters.append(f"{quote_identifier('timeframe')} = ?")
        params.append(str(args.timeframe))
    return filters, params


def required_columns(args: argparse.Namespace) -> set[str]:
    return {
        "time_server",
        str(args.session_column),
        "spread",
        "open",
        "high",
        "low",
        "close",
        ATR_COLUMN,
        FEATURE_A,
        FEATURE_B,
    }


def threshold_cutoffs(payload: dict[str, Any]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    for feature in (FEATURE_A, FEATURE_B):
        feature_payload = features.get(feature) if isinstance(features.get(feature), dict) else {}
        low_mid = safe_float(feature_payload.get("low_mid_cutoff"))
        mid_high = safe_float(feature_payload.get("mid_high_cutoff"))
        if low_mid is not None and mid_high is not None:
            result[feature] = {"low_mid_cutoff": low_mid, "mid_high_cutoff": mid_high}
    return result


def threshold_validation_errors(payload: dict[str, Any], args: argparse.Namespace) -> tuple[list[str], list[str]]:
    non_train_only: list[str] = []
    noncanonical: list[str] = []
    if payload.get("threshold_lineage") != "train_only":
        non_train_only.append("threshold_lineage")
    if payload.get("calibration_scope") != "train_window_only":
        non_train_only.append("calibration_scope")
    if payload.get("full_sample_thresholds_used") is not False:
        non_train_only.append("full_sample_thresholds_used")
    if payload.get("oos_rows_used_for_thresholds") is not False:
        non_train_only.append("oos_rows_used_for_thresholds")
    if set(threshold_cutoffs(payload)) != {FEATURE_A, FEATURE_B}:
        non_train_only.append("feature_cutoffs")
    if not str(payload.get("train_end_time") or "").strip():
        non_train_only.append("train_end_time")
    if str(payload.get("candidate_id") or "") != EXPECTED_CANDIDATE_ID:
        noncanonical.append("candidate_id")
    if str(payload.get("symbol") or "") != str(args.symbol):
        noncanonical.append("symbol")
    if str(payload.get("timeframe") or "") != str(args.timeframe):
        noncanonical.append("timeframe")
    if payload.get("required_conditions") != EXPECTED_REQUIRED_CONDITIONS:
        noncanonical.append("required_conditions")
    return non_train_only, noncanonical


def canonical_mismatches(args: argparse.Namespace, canonical: dict[str, Any], error: str) -> list[str]:
    if error:
        return [f"canonical_registry_{error}"]
    checks = {
        "candidate_id": EXPECTED_CANDIDATE_ID,
        "symbol": str(args.symbol),
        "timeframe": str(args.timeframe),
        "direction": DEFAULT_DIRECTION,
        "max_spread_points": float(args.max_spread_points),
    }
    mismatches: list[str] = []
    for key, expected in checks.items():
        observed = canonical.get(key)
        if isinstance(expected, float):
            if safe_float(observed) != expected:
                mismatches.append(f"{key}={observed!r}")
        elif str(observed) != str(expected):
            mismatches.append(f"{key}={observed!r}")
    return mismatches


def bucket_for_value(value: float | None, low_mid: float, mid_high: float) -> str:
    if value is None:
        return "missing"
    if value <= low_mid:
        return "low_tercile"
    if value <= mid_high:
        return "mid_tercile"
    return "high_tercile"


def fetch_price_rows(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    columns: set[str],
    filters: list[str],
    params: list[Any],
    session_column: str,
) -> list[dict[str, Any]]:
    select_columns = [
        "time_server",
        "symbol" if "symbol" in columns else "",
        "timeframe" if "timeframe" in columns else "",
        "open",
        "high",
        "low",
        "close",
        "spread",
        ATR_COLUMN,
        str(session_column),
        FEATURE_A,
        FEATURE_B,
    ]
    select_columns = [column for column in select_columns if column]
    query = (
        "SELECT "
        + ", ".join(quote_identifier(column) for column in select_columns)
        + f" FROM {quote_identifier(table_name)}"
        + where_clause(filters)
        + f" ORDER BY {quote_identifier('time_server')} ASC"
    )
    return [dict(row) for row in connection.execute(query, params).fetchall()]


def entry_gate(row: dict[str, Any], cutoffs: dict[str, dict[str, float]], args: argparse.Namespace) -> dict[str, Any]:
    feature_a = safe_float(row.get(FEATURE_A))
    feature_b = safe_float(row.get(FEATURE_B))
    spread = safe_float(row.get("spread"))
    bucket_a = bucket_for_value(feature_a, cutoffs[FEATURE_A]["low_mid_cutoff"], cutoffs[FEATURE_A]["mid_high_cutoff"])
    bucket_b = bucket_for_value(feature_b, cutoffs[FEATURE_B]["low_mid_cutoff"], cutoffs[FEATURE_B]["mid_high_cutoff"])
    spread_pass = spread is not None and spread <= float(args.max_spread_points)
    session_pass = str(row.get(str(args.session_column)) or "") == str(args.required_session)
    match = session_pass and spread_pass and bucket_a == "high_tercile" and bucket_b == "mid_tercile"
    return {
        "feature_a": feature_a,
        "feature_b": feature_b,
        "bucket_a": bucket_a,
        "bucket_b": bucket_b,
        "spread": spread,
        "spread_pass": spread_pass,
        "session_pass": session_pass,
        "rule_match": match,
    }


def compute_r(entry_price: float, exit_price: float, sl_price: float) -> float | None:
    risk = sl_price - entry_price
    if risk <= 0:
        return None
    return (entry_price - exit_price) / risk


def simulate_trade(
    *,
    rows: list[dict[str, Any]],
    entry_index: int,
    gate: dict[str, Any],
    run_id: str,
    signal_id: str,
    trade_index: int,
    warnings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    entry = rows[entry_index]
    entry_price = safe_float(entry.get("close"))
    atr = safe_float(entry.get(ATR_COLUMN))
    if entry_price is None or atr is None or atr <= 0:
        return None
    tp_price = entry_price - TP_ATR * atr
    sl_price = entry_price + SL_ATR * atr
    last_seen: dict[str, Any] | None = None
    for offset, path_row in enumerate(rows[entry_index + 1 : entry_index + HORIZON_BARS + 1], start=1):
        last_seen = path_row
        low = safe_float(path_row.get("low"))
        high = safe_float(path_row.get("high"))
        close = safe_float(path_row.get("close"))
        tp_hit = low is not None and low <= tp_price
        sl_hit = high is not None and high >= sl_price
        exit_reason = ""
        exit_price: float | None = None
        if tp_hit and sl_hit:
            exit_reason = "paper_sl_hit"
            exit_price = sl_price
            warnings.append(
                warning_row(
                    run_id=run_id,
                    warning_code="same_bar_stop_first_applied",
                    message="TP and SL were both touched after entry; stop_first policy applied.",
                    source="price_path",
                    blocking_warning=False,
                )
            )
        elif tp_hit:
            exit_reason = "paper_tp_hit"
            exit_price = tp_price
        elif sl_hit:
            exit_reason = "paper_sl_hit"
            exit_price = sl_price
        elif offset >= HORIZON_BARS and close is not None:
            exit_reason = "paper_timeout"
            exit_price = close
        if exit_reason and exit_price is not None:
            r_multiple = compute_r(entry_price, exit_price, sl_price)
            return {
                "run_id": run_id,
                "trade_index": trade_index,
                "signal_id": signal_id,
                "entry_time_server": entry.get("time_server", ""),
                "exit_time_server": path_row.get("time_server", ""),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "direction": DEFAULT_DIRECTION,
                "exit_reason": exit_reason,
                "R_multiple": r_multiple,
                "bars_elapsed": offset,
                "horizon_bars": HORIZON_BARS,
                "same_bar_policy": SAME_BAR_POLICY,
                "spread": gate["spread"],
                FEATURE_A: gate["feature_a"],
                f"{FEATURE_A}_bucket": gate["bucket_a"],
                FEATURE_B: gate["feature_b"],
                f"{FEATURE_B}_bucket": gate["bucket_b"],
            }
    if last_seen is not None and safe_float(last_seen.get("close")) is not None:
        exit_price = float(safe_float(last_seen.get("close")))
        r_multiple = compute_r(entry_price, exit_price, sl_price)
        return {
            "run_id": run_id,
            "trade_index": trade_index,
            "signal_id": signal_id,
            "entry_time_server": entry.get("time_server", ""),
            "exit_time_server": last_seen.get("time_server", ""),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "direction": DEFAULT_DIRECTION,
            "exit_reason": "paper_end_of_data",
            "R_multiple": r_multiple,
            "bars_elapsed": "",
            "horizon_bars": HORIZON_BARS,
            "same_bar_policy": SAME_BAR_POLICY,
            "spread": gate["spread"],
            FEATURE_A: gate["feature_a"],
            f"{FEATURE_A}_bucket": gate["bucket_a"],
            FEATURE_B: gate["feature_b"],
            f"{FEATURE_B}_bucket": gate["bucket_b"],
        }
    return None


def profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if not values or losses == 0:
        return None
    return gains / losses


def max_drawdown(values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return drawdown


def metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(value) for trade in trades if (value := safe_float(trade.get("R_multiple"))) is not None]
    count = len(values)
    tp_count = sum(1 for trade in trades if trade["exit_reason"] == "paper_tp_hit")
    sl_count = sum(1 for trade in trades if trade["exit_reason"] == "paper_sl_hit")
    timeout_count = sum(1 for trade in trades if trade["exit_reason"] == "paper_timeout")
    return {
        "trade_count": count,
        "mean_R": (sum(values) / count) if count else None,
        "median_R": statistics.median(values) if values else None,
        "sum_R": sum(values) if values else None,
        "profit_factor_R": profit_factor(values),
        "win_rate_R_positive": (sum(1 for value in values if value > 0) / count) if count else None,
        "max_drawdown_R": max_drawdown(values),
        "tp_hit_count": tp_count,
        "sl_hit_count": sl_count,
        "timeout_count": timeout_count,
        "timeout_rate": (timeout_count / count) if count else None,
    }


def equity_curve(run_id: str, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cumulative = 0.0
    peak = 0.0
    rows: list[dict[str, Any]] = []
    for trade in trades:
        r_multiple = safe_float(trade.get("R_multiple"))
        if r_multiple is None:
            continue
        cumulative += r_multiple
        peak = max(peak, cumulative)
        rows.append(
            {
                "run_id": run_id,
                "trade_index": trade["trade_index"],
                "signal_id": trade["signal_id"],
                "exit_time_server": trade["exit_time_server"],
                "exit_reason": trade["exit_reason"],
                "R_multiple": r_multiple,
                "cumulative_R": cumulative,
                "peak_cumulative_R": peak,
                "drawdown_R": peak - cumulative,
            }
        )
    return rows


def count_rows(name: str, counts: dict[str, int]) -> list[dict[str, Any]]:
    return [{"name": name, "bucket_or_condition": key, "count": value} for key, value in counts.items()]


def replay_rows(
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    train_end_time: str,
    cutoffs: dict[str, dict[str, float]],
    warnings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    trades: list[dict[str, Any]] = []
    bucket_a_counts = {"low_tercile": 0, "mid_tercile": 0, "high_tercile": 0, "missing": 0}
    bucket_b_counts = {"low_tercile": 0, "mid_tercile": 0, "high_tercile": 0, "missing": 0}
    condition_counts = {
        "session_pass": 0,
        "spread_pass": 0,
        f"{FEATURE_A}_high_tercile": 0,
        f"{FEATURE_B}_mid_tercile": 0,
        "rule_match": 0,
    }
    rule_match_count = 0
    for index, row in enumerate(rows):
        if str(row.get("time_server") or "") <= train_end_time:
            continue
        gate = entry_gate(row, cutoffs, args)
        bucket_a_counts[gate["bucket_a"]] += 1
        bucket_b_counts[gate["bucket_b"]] += 1
        if gate["session_pass"]:
            condition_counts["session_pass"] += 1
        if gate["spread_pass"]:
            condition_counts["spread_pass"] += 1
        if gate["bucket_a"] == "high_tercile":
            condition_counts[f"{FEATURE_A}_high_tercile"] += 1
        if gate["bucket_b"] == "mid_tercile":
            condition_counts[f"{FEATURE_B}_mid_tercile"] += 1
        if gate["rule_match"]:
            rule_match_count += 1
            condition_counts["rule_match"] += 1
            trade = simulate_trade(
                rows=rows,
                entry_index=index,
                gate=gate,
                run_id=str(args.run_id),
                signal_id=f"{args.run_id}_{rule_match_count:06d}",
                trade_index=len(trades) + 1,
                warnings=warnings,
            )
            if trade is not None:
                trades.append(trade)
    bucket_rows = [
        *count_rows(FEATURE_A, bucket_a_counts),
        *count_rows(FEATURE_B, bucket_b_counts),
    ]
    condition_rows = count_rows("condition", condition_counts)
    return trades, bucket_rows, condition_rows, rule_match_count


def derive_status(
    *,
    threshold_missing: bool,
    non_train_only: bool,
    noncanonical: bool,
    db_exists: bool,
    table_exists: bool,
    missing_columns: list[str],
    oos_row_count: int,
) -> str:
    if threshold_missing:
        return STATUS_MISSING_THRESHOLD
    if noncanonical:
        return STATUS_NONCANONICAL
    if non_train_only:
        return STATUS_NON_TRAIN_ONLY
    if not db_exists:
        return STATUS_MISSING_DB
    if not table_exists:
        return STATUS_MISSING_TABLE
    if missing_columns:
        return STATUS_MISSING_COLUMNS
    if oos_row_count == 0:
        return STATUS_EMPTY_OOS
    return STATUS_AVAILABLE


def build_model(args: argparse.Namespace) -> dict[str, Any]:
    run_id = str(args.run_id)
    threshold_path = Path(args.train_only_thresholds)
    canonical_path = Path(args.canonical_registry)
    db_path = Path(args.db_path)
    threshold_payload, threshold_error = read_json_object(threshold_path)
    canonical_payload, canonical_error = read_json_object(canonical_path)
    warnings: list[dict[str, Any]] = []
    if threshold_error:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="missing_threshold_artifact",
                message=f"Train-only threshold artifact missing or unreadable: {threshold_error}",
                source=threshold_path,
                blocking_warning=True,
            )
        )
    non_train_errors, threshold_noncanonical = (
        threshold_validation_errors(threshold_payload, args) if threshold_payload else ([], [])
    )
    if non_train_errors:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="non_train_only_thresholds",
                message="Threshold artifact failed train-only checks: " + ", ".join(non_train_errors),
                source=threshold_path,
                blocking_warning=True,
            )
        )
    canonical_errors = canonical_mismatches(args, canonical_payload, canonical_error)
    noncanonical_items = [*threshold_noncanonical, *canonical_errors]
    if noncanonical_items:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="noncanonical_candidate",
                message="Candidate identity/config checks failed: " + ", ".join(noncanonical_items),
                source=f"{threshold_path};{canonical_path}",
                blocking_warning=True,
            )
        )

    table_exists = False
    columns: set[str] = set()
    schema_error = ""
    db_exists = db_path.exists()
    if db_exists:
        table_exists, columns, schema_error = inspect_table(db_path, str(args.feature_table))
    else:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="missing_db",
                message="Configured SQLite DB does not exist.",
                source=db_path,
                blocking_warning=True,
            )
        )
    if db_exists and not table_exists:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="missing_table",
                message=f"Feature table missing or unreadable: {schema_error}",
                source=args.feature_table,
                blocking_warning=True,
            )
        )
    missing_columns = sorted(required_columns(args) - columns) if table_exists else []
    if missing_columns:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="missing_columns",
                message="Feature table is missing required columns: " + ", ".join(missing_columns),
                source=args.feature_table,
                blocking_warning=True,
            )
        )

    train_end_time = str(threshold_payload.get("train_end_time") or "")
    oos_start_time = str(args.oos_start_time or "")
    oos_end_time = str(args.oos_end_time or "")
    oos_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    offhours_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    rows: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    bucket_counts: list[dict[str, Any]] = []
    condition_counts: list[dict[str, Any]] = []
    rule_match_count = 0
    cutoffs = threshold_cutoffs(threshold_payload) if threshold_payload else {}
    can_query = (
        db_exists
        and table_exists
        and not missing_columns
        and not threshold_error
        and not non_train_errors
        and not noncanonical_items
    )
    if can_query:
        with connect_read_only(db_path) as connection:
            src_filters, src_params = source_filters(args, columns)
            if not oos_end_time:
                source_info = one_row_window_query(
                    connection=connection,
                    table_name=str(args.feature_table),
                    filters=src_filters,
                    params=src_params,
                )
                oos_end_time = source_info["max_time_server"]
            if not oos_start_time:
                first_filters = [*src_filters, f"{quote_identifier('time_server')} > ?"]
                first_params = [*src_params, train_end_time]
                first_info = one_row_window_query(
                    connection=connection,
                    table_name=str(args.feature_table),
                    filters=first_filters,
                    params=first_params,
                )
                oos_start_time = first_info["min_time_server"] or plus_one_second_text(train_end_time)
            oos_filters = [
                *src_filters,
                f"{quote_identifier('time_server')} > ?",
                f"{quote_identifier('time_server')} >= ?",
            ]
            oos_params = [*src_params, train_end_time, oos_start_time]
            if oos_end_time:
                oos_filters.append(f"{quote_identifier('time_server')} <= ?")
                oos_params.append(oos_end_time)
            oos_info = one_row_window_query(
                connection=connection,
                table_name=str(args.feature_table),
                filters=oos_filters,
                params=oos_params,
            )
            off_filters = [*oos_filters, f"{quote_identifier(str(args.session_column))} = ?"]
            off_params = [*oos_params, str(args.required_session)]
            offhours_info = one_row_window_query(
                connection=connection,
                table_name=str(args.feature_table),
                filters=off_filters,
                params=off_params,
            )
            rows = fetch_price_rows(
                connection=connection,
                table_name=str(args.feature_table),
                columns=columns,
                filters=oos_filters,
                params=oos_params,
                session_column=str(args.session_column),
            )
        if rows:
            trades, bucket_counts, condition_counts, rule_match_count = replay_rows(
                args=args,
                rows=rows,
                train_end_time=train_end_time,
                cutoffs=cutoffs,
                warnings=warnings,
            )
    if can_query and int(oos_info["row_count"] or 0) == 0:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="empty_oos_window",
                message="No OOS rows were available after train_end_time.",
                source=args.feature_table,
                blocking_warning=True,
            )
        )

    stats = metrics(trades)
    equity = equity_curve(run_id, trades)
    replay_status = derive_status(
        threshold_missing=bool(threshold_error),
        non_train_only=bool(non_train_errors),
        noncanonical=bool(noncanonical_items),
        db_exists=db_exists,
        table_exists=table_exists,
        missing_columns=missing_columns,
        oos_row_count=int(oos_info["row_count"] or 0),
    )
    manifest = {
        "run_id": run_id,
        "replay_status": replay_status,
        "candidate_id": EXPECTED_CANDIDATE_ID,
        "symbol": str(args.symbol),
        "timeframe": str(args.timeframe),
        "direction": DEFAULT_DIRECTION,
        "train_only_threshold_artifact": str(threshold_path),
        "threshold_lineage": threshold_payload.get("threshold_lineage", ""),
        "calibration_scope": threshold_payload.get("calibration_scope", ""),
        "train_end_time": train_end_time,
        "oos_start_time": oos_start_time,
        "oos_end_time": oos_end_time,
        "oos_row_count": oos_info["row_count"],
        "off_hours_oos_row_count": offhours_info["row_count"],
        "rule_match_count": rule_match_count,
        "tp_atr": TP_ATR,
        "sl_atr": SL_ATR,
        "horizon_bars": HORIZON_BARS,
        "same_bar_policy": SAME_BAR_POLICY,
        "max_spread_points": float(args.max_spread_points),
        "feature_table": str(args.feature_table),
        "db_path": str(db_path),
        "missing_required_columns": missing_columns,
        "canonical_registry_sha256": sha256_file(canonical_path) if canonical_path.exists() and not canonical_error else "",
        "threshold_artifact_sha256": sha256_file(threshold_path) if threshold_path.exists() and not threshold_error else "",
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(bool(warning["blocking_warning"]) for warning in warnings),
        "created_at_utc": utc_now_text(),
        "output_files": {},
        **stats,
        **NO_ORDER_EVIDENCE,
    }
    summary = [{field: manifest.get(field) for field in SUMMARY_FIELDS}]
    no_order_evidence = [
        {"evidence_name": key, "value": value, "note": "artifact_only_oos_outcome_replay"}
        for key, value in NO_ORDER_EVIDENCE.items()
    ]
    return {
        "manifest": manifest,
        "summary": summary,
        "trades": trades,
        "equity_curve": equity,
        "condition_counts": condition_counts,
        "bucket_counts": bucket_counts,
        "warnings": warnings,
        "no_order_evidence": no_order_evidence,
    }


def report_text(model: dict[str, Any]) -> str:
    manifest = model["manifest"]
    lines = [
        "# Fixed Candidate Train-Only Threshold OOS Outcome Replay",
        "",
        "Artifact-only OOS outcome replay using frozen train-only thresholds and fixed TP/SL/horizon assumptions.",
        "",
        "## Status",
        "",
        f"- replay_status: `{manifest['replay_status']}`",
        f"- train_end_time: `{manifest['train_end_time']}`",
        f"- oos_start_time: `{manifest['oos_start_time']}`",
        f"- oos_end_time: `{manifest['oos_end_time']}`",
        f"- rule_match_count: `{manifest['rule_match_count']}`",
        "",
        "## Metrics",
        "",
        f"- trade_count: `{manifest['trade_count']}`",
        f"- mean_R: `{manifest['mean_R']}`",
        f"- median_R: `{manifest['median_R']}`",
        f"- sum_R: `{manifest['sum_R']}`",
        f"- profit_factor_R: `{manifest['profit_factor_R']}`",
        f"- win_rate_R_positive: `{manifest['win_rate_R_positive']}`",
        f"- max_drawdown_R: `{manifest['max_drawdown_R']}`",
        f"- tp_hit_count: `{manifest['tp_hit_count']}`",
        f"- sl_hit_count: `{manifest['sl_hit_count']}`",
        f"- timeout_count: `{manifest['timeout_count']}`",
        "",
        "## Safety Boundary",
        "",
        "- No canonical config update, DB mutation, future-state write, MT5/broker/API call, order_check, order_send, child workflow, scheduler, loop, background task, or trading decision was performed.",
    ]
    return "\n".join(lines) + "\n"


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for_args(args)
    paths = ensure_output_writable(output_dir, bool(args.overwrite))
    model = build_model(args)
    model["manifest"]["output_files"] = {label: str(path) for label, path in paths.items()}
    write_json(paths["manifest"], model["manifest"])
    paths["report"].write_text(report_text(model), encoding="utf-8")
    write_csv(paths["summary"], model["summary"], SUMMARY_FIELDS)
    write_csv(paths["trades"], model["trades"], TRADE_FIELDS)
    write_csv(paths["equity_curve"], model["equity_curve"], EQUITY_FIELDS)
    write_csv(paths["condition_counts"], model["condition_counts"], COUNT_FIELDS)
    write_csv(paths["bucket_counts"], model["bucket_counts"], COUNT_FIELDS)
    write_csv(paths["warnings"], model["warnings"], WARNING_FIELDS)
    write_csv(paths["no_order_evidence"], model["no_order_evidence"], ["evidence_name", "value", "note"])
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute artifact-only OOS trade outcomes using train-only fixed-candidate thresholds."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--feature-table", default=DEFAULT_FEATURE_TABLE)
    parser.add_argument("--train-only-thresholds", type=Path, default=DEFAULT_TRAIN_ONLY_THRESHOLDS)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--oos-start-time")
    parser.add_argument("--oos-end-time")
    parser.add_argument("--session-column", default=DEFAULT_SESSION_COLUMN)
    parser.add_argument("--required-session", default=DEFAULT_REQUIRED_SESSION)
    parser.add_argument("--max-spread-points", type=float, default=DEFAULT_MAX_SPREAD_POINTS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except BlockedStatusError as exc:
        print(f"Fixed-candidate train-only threshold OOS outcome replay blocked: {exc}")
        return 1
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate train-only threshold OOS outcome replay failed: {exc}")
        return 1
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    print("Fixed-candidate train-only threshold OOS outcome replay complete.")
    print(f"replay_status: {manifest['replay_status']}")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0 if manifest["replay_status"] == STATUS_AVAILABLE else 1


if __name__ == "__main__":
    raise SystemExit(main())
