"""Replay fixed-candidate OOS signal diagnostics with train-only thresholds.

This module reads a local SQLite feature table through a read-only URI, applies
the fixed candidate rule only after the train-only threshold artifact's
train_end_time, and writes artifact-only OOS diagnostics. It does not update
canonical config, mutate the DB, run broker/order paths, run child workflows, or
create live/paper execution instructions.
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

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_train_only_threshold_oos_replay_v1"
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
DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_SESSION_COLUMN = "hour_session"
DEFAULT_REQUIRED_SESSION = "Off_hours"
DEFAULT_MAX_SPREAD_POINTS = 15.0
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_train_only_threshold_oos_replay"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_DIRECTION = "short"
EXPECTED_REQUIRED_CONDITIONS = {
    "close_to_ma_fast_atr_20": "high_tercile",
    "tick_volume_percentile_100": "mid_tercile",
}
FEATURE_A = "close_to_ma_fast_atr_20"
FEATURE_B = "tick_volume_percentile_100"
SAME_BAR_POLICY = "stop_first"
HORIZON_BARS = 10

STATUS_AVAILABLE_WITH_OUTCOMES = "train_only_threshold_oos_replay_available_with_outcomes"
STATUS_AVAILABLE_SIGNAL_ONLY = "train_only_threshold_oos_replay_available_signal_only"
STATUS_MISSING_THRESHOLD = "train_only_threshold_oos_replay_blocked_missing_threshold_artifact"
STATUS_NON_TRAIN_ONLY = "train_only_threshold_oos_replay_blocked_non_train_only_thresholds"
STATUS_MISSING_DB = "train_only_threshold_oos_replay_blocked_missing_db"
STATUS_MISSING_TABLE = "train_only_threshold_oos_replay_blocked_missing_table"
STATUS_MISSING_COLUMNS = "train_only_threshold_oos_replay_blocked_missing_columns"
STATUS_EMPTY_OOS = "train_only_threshold_oos_replay_blocked_empty_oos_window"
STATUS_NONCANONICAL = "train_only_threshold_oos_replay_blocked_noncanonical_candidate"
STATUS_OUTPUT_EXISTS = "train_only_threshold_oos_replay_blocked_output_exists_without_overwrite"

MANIFEST_FILE = "fixed_candidate_train_only_threshold_oos_replay_manifest.json"
REPORT_FILE = "fixed_candidate_train_only_threshold_oos_replay_report.md"
SUMMARY_FILE = "fixed_candidate_train_only_threshold_oos_replay_summary.csv"
MATCHES_FILE = "fixed_candidate_train_only_threshold_oos_replay_matches.csv"
BUCKET_COUNTS_FILE = "fixed_candidate_train_only_threshold_oos_replay_bucket_counts.csv"
CONDITION_COUNTS_FILE = "fixed_candidate_train_only_threshold_oos_replay_condition_counts.csv"
WINDOW_FILE = "fixed_candidate_train_only_threshold_oos_replay_window.csv"
WARNINGS_FILE = "fixed_candidate_train_only_threshold_oos_replay_warnings.csv"
NO_ORDER_EVIDENCE_FILE = "fixed_candidate_train_only_threshold_oos_replay_no_order_evidence.csv"

OUTPUT_FILES = {
    "manifest": MANIFEST_FILE,
    "report": REPORT_FILE,
    "summary": SUMMARY_FILE,
    "matches": MATCHES_FILE,
    "bucket_counts": BUCKET_COUNTS_FILE,
    "condition_counts": CONDITION_COUNTS_FILE,
    "window": WINDOW_FILE,
    "warnings": WARNINGS_FILE,
    "no_order_evidence": NO_ORDER_EVIDENCE_FILE,
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
    "source_row_count",
    "oos_row_count",
    "off_hours_oos_row_count",
    "rule_match_count",
    "spread_pass_count",
    "outcome_columns_available",
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
MATCH_FIELDS = [
    "time_server",
    "symbol",
    "timeframe",
    "hour_session",
    "spread",
    FEATURE_A,
    f"{FEATURE_A}_bucket",
    FEATURE_B,
    f"{FEATURE_B}_bucket",
    "spread_pass",
    "rule_match",
    "R_multiple",
    "exit_reason",
]
BUCKET_COUNT_FIELDS = ["feature_name", "bucket", "count"]
CONDITION_COUNT_FIELDS = ["condition_name", "pass_count", "fail_count", "total_count"]
WINDOW_FIELDS = [
    "source_min_time_server",
    "source_max_time_server",
    "train_end_time",
    "oos_start_time",
    "oos_end_time",
    "source_row_count",
    "oos_row_count",
    "off_hours_oos_row_count",
]

R_COLUMN_CANDIDATES = ("R_multiple", "r_multiple", "selected_R", "net_R", "gross_R", "R")
EXIT_REASON_CANDIDATES = ("exit_reason", "outcome", "target_outcome", "hit_outcome")

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
        raise BlockedStatusError(
            STATUS_OUTPUT_EXISTS,
            "Output files already exist; use --overwrite to replace this artifact set.",
        )
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
    if not filters:
        return ""
    return " WHERE " + " AND ".join(filters)


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


def bucket_for_value(value: float | None, low_mid: float, mid_high: float) -> str:
    if value is None:
        return "missing"
    if value <= low_mid:
        return "low_tercile"
    if value <= mid_high:
        return "mid_tercile"
    return "high_tercile"


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


def load_threshold_artifact(path: Path) -> tuple[dict[str, Any], str]:
    return read_json_object(path)


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
    if str(payload.get("candidate_id") or "") != EXPECTED_CANDIDATE_ID:
        noncanonical.append("candidate_id")
    if str(payload.get("symbol") or "") != str(args.symbol):
        noncanonical.append("symbol")
    if str(payload.get("timeframe") or "") != str(args.timeframe):
        noncanonical.append("timeframe")
    required_conditions = payload.get("required_conditions")
    if required_conditions != EXPECTED_REQUIRED_CONDITIONS:
        noncanonical.append("required_conditions")
    if set(threshold_cutoffs(payload)) != {FEATURE_A, FEATURE_B}:
        non_train_only.append("feature_cutoffs")
    if not str(payload.get("train_end_time") or "").strip():
        non_train_only.append("train_end_time")
    return non_train_only, noncanonical


def canonical_mismatches(args: argparse.Namespace, canonical: dict[str, Any], error: str) -> list[str]:
    if error:
        return [f"canonical_registry_{error}"]
    mismatches: list[str] = []
    checks = {
        "candidate_id": EXPECTED_CANDIDATE_ID,
        "symbol": str(args.symbol),
        "timeframe": str(args.timeframe),
        "direction": EXPECTED_DIRECTION,
        "max_spread_points": float(args.max_spread_points),
    }
    for key, expected in checks.items():
        observed = canonical.get(key)
        if isinstance(expected, float):
            if safe_float(observed) != expected:
                mismatches.append(f"{key}={observed!r}")
        elif str(observed) != str(expected):
            mismatches.append(f"{key}={observed!r}")
    return mismatches


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


def oos_filters(
    args: argparse.Namespace,
    columns: set[str],
    *,
    train_end_time: str,
    oos_start_time: str,
    oos_end_time: str,
    include_session: bool,
) -> tuple[list[str], list[Any]]:
    filters, params = source_filters(args, columns)
    filters.append(f"{quote_identifier('time_server')} > ?")
    params.append(train_end_time)
    if oos_start_time:
        filters.append(f"{quote_identifier('time_server')} >= ?")
        params.append(oos_start_time)
    if oos_end_time:
        filters.append(f"{quote_identifier('time_server')} <= ?")
        params.append(oos_end_time)
    if include_session:
        filters.append(f"{quote_identifier(str(args.session_column))} = ?")
        params.append(str(args.required_session))
    return filters, params


def fetch_rows(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    columns: set[str],
    filters: list[str],
    params: list[Any],
) -> list[dict[str, Any]]:
    optional_columns = [
        column for column in [*R_COLUMN_CANDIDATES, *EXIT_REASON_CANDIDATES] if column in columns
    ]
    select_columns = [
        "time_server",
        "symbol" if "symbol" in columns else "",
        "timeframe" if "timeframe" in columns else "",
        "spread",
        str(FEATURE_A),
        str(FEATURE_B),
        *optional_columns,
    ]
    session_column = "hour_session"
    if session_column not in select_columns and session_column in columns:
        select_columns.append(session_column)
    select_columns = [column for column in select_columns if column]
    query = (
        "SELECT "
        + ", ".join(quote_identifier(column) for column in select_columns)
        + f" FROM {quote_identifier(table_name)}"
        + where_clause(filters)
        + f" ORDER BY {quote_identifier('time_server')} ASC"
    )
    return [dict(row) for row in connection.execute(query, params).fetchall()]


def r_column(columns: set[str]) -> str:
    return next((column for column in R_COLUMN_CANDIDATES if column in columns), "")


def exit_reason_column(columns: set[str]) -> str:
    return next((column for column in EXIT_REASON_CANDIDATES if column in columns), "")


def profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if not values or losses == 0:
        return None
    return gains / losses


def max_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return drawdown


def outcome_reason_counts(matches: list[dict[str, Any]], reason_column: str) -> dict[str, int]:
    counts = {"tp_hit_count": 0, "sl_hit_count": 0, "timeout_count": 0}
    if not reason_column:
        return counts
    for row in matches:
        reason = str(row.get(reason_column) or "").lower()
        if "tp" in reason:
            counts["tp_hit_count"] += 1
        if "sl" in reason:
            counts["sl_hit_count"] += 1
        if "timeout" in reason or "end_of_data" in reason:
            counts["timeout_count"] += 1
    return counts


def metrics_for_matches(matches: list[dict[str, Any]], r_col: str, reason_col: str) -> dict[str, Any]:
    if not r_col:
        return {
            "trade_count": None,
            "mean_R": None,
            "median_R": None,
            "sum_R": None,
            "profit_factor_R": None,
            "win_rate_R_positive": None,
            "max_drawdown_R": None,
            "tp_hit_count": None,
            "sl_hit_count": None,
            "timeout_count": None,
            "timeout_rate": None,
        }
    values = [value for row in matches if (value := safe_float(row.get(r_col))) is not None]
    count = len(values)
    reason_counts = outcome_reason_counts(matches, reason_col)
    timeout_count = reason_counts["timeout_count"]
    return {
        "trade_count": count,
        "mean_R": (sum(values) / count) if count else None,
        "median_R": statistics.median(values) if values else None,
        "sum_R": sum(values) if values else None,
        "profit_factor_R": profit_factor(values),
        "win_rate_R_positive": (sum(1 for value in values if value > 0) / count) if count else None,
        "max_drawdown_R": max_drawdown(values),
        "tp_hit_count": reason_counts["tp_hit_count"],
        "sl_hit_count": reason_counts["sl_hit_count"],
        "timeout_count": timeout_count,
        "timeout_rate": (timeout_count / count) if count else None,
    }


def evaluate_oos_rows(
    rows: list[dict[str, Any]],
    *,
    cutoffs: dict[str, dict[str, float]],
    max_spread_points: float,
    r_col: str,
    reason_col: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    bucket_counts = {
        FEATURE_A: {"low_tercile": 0, "mid_tercile": 0, "high_tercile": 0, "missing": 0},
        FEATURE_B: {"low_tercile": 0, "mid_tercile": 0, "high_tercile": 0, "missing": 0},
    }
    spread_pass_count = 0
    feature_a_pass = 0
    feature_b_pass = 0
    matches: list[dict[str, Any]] = []
    evaluated_rows: list[dict[str, Any]] = []
    for row in rows:
        feature_a = safe_float(row.get(FEATURE_A))
        feature_b = safe_float(row.get(FEATURE_B))
        spread = safe_float(row.get("spread"))
        bucket_a = bucket_for_value(
            feature_a,
            cutoffs[FEATURE_A]["low_mid_cutoff"],
            cutoffs[FEATURE_A]["mid_high_cutoff"],
        )
        bucket_b = bucket_for_value(
            feature_b,
            cutoffs[FEATURE_B]["low_mid_cutoff"],
            cutoffs[FEATURE_B]["mid_high_cutoff"],
        )
        bucket_counts[FEATURE_A][bucket_a] += 1
        bucket_counts[FEATURE_B][bucket_b] += 1
        spread_pass = spread is not None and spread <= max_spread_points
        if spread_pass:
            spread_pass_count += 1
        if bucket_a == "high_tercile":
            feature_a_pass += 1
        if bucket_b == "mid_tercile":
            feature_b_pass += 1
        rule_match = bucket_a == "high_tercile" and bucket_b == "mid_tercile" and spread_pass
        evaluated = {
            "time_server": row.get("time_server", ""),
            "symbol": row.get("symbol", ""),
            "timeframe": row.get("timeframe", ""),
            "hour_session": row.get("hour_session", ""),
            "spread": spread,
            FEATURE_A: feature_a,
            f"{FEATURE_A}_bucket": bucket_a,
            FEATURE_B: feature_b,
            f"{FEATURE_B}_bucket": bucket_b,
            "spread_pass": spread_pass,
            "rule_match": rule_match,
            "R_multiple": row.get(r_col, "") if r_col else "",
            "exit_reason": row.get(reason_col, "") if reason_col else "",
        }
        evaluated_rows.append(evaluated)
        if rule_match:
            matches.append(evaluated)
    bucket_rows = [
        {"feature_name": feature, "bucket": bucket, "count": count}
        for feature, counts in bucket_counts.items()
        for bucket, count in counts.items()
    ]
    total = len(rows)
    condition_rows = [
        {
            "condition_name": "session_filter",
            "pass_count": total,
            "fail_count": 0,
            "total_count": total,
        },
        {
            "condition_name": "spread_gate",
            "pass_count": spread_pass_count,
            "fail_count": total - spread_pass_count,
            "total_count": total,
        },
        {
            "condition_name": f"{FEATURE_A}_high_tercile",
            "pass_count": feature_a_pass,
            "fail_count": total - feature_a_pass,
            "total_count": total,
        },
        {
            "condition_name": f"{FEATURE_B}_mid_tercile",
            "pass_count": feature_b_pass,
            "fail_count": total - feature_b_pass,
            "total_count": total,
        },
        {
            "condition_name": "rule_match",
            "pass_count": len(matches),
            "fail_count": total - len(matches),
            "total_count": total,
        },
    ]
    return evaluated_rows, matches, bucket_rows, {
        "condition_rows": condition_rows,
        "spread_pass_count": spread_pass_count,
    }


def required_columns(args: argparse.Namespace) -> set[str]:
    return {
        "time_server",
        str(args.session_column),
        "spread",
        FEATURE_A,
        FEATURE_B,
    }


def derive_status(
    *,
    threshold_missing: bool,
    threshold_non_train_only: bool,
    noncanonical: bool,
    db_exists: bool,
    table_exists: bool,
    missing_columns: list[str],
    off_hours_oos_row_count: int,
    outcome_columns_available: bool,
) -> str:
    if threshold_missing:
        return STATUS_MISSING_THRESHOLD
    if noncanonical:
        return STATUS_NONCANONICAL
    if threshold_non_train_only:
        return STATUS_NON_TRAIN_ONLY
    if not db_exists:
        return STATUS_MISSING_DB
    if not table_exists:
        return STATUS_MISSING_TABLE
    if missing_columns:
        return STATUS_MISSING_COLUMNS
    if off_hours_oos_row_count == 0:
        return STATUS_EMPTY_OOS
    return STATUS_AVAILABLE_WITH_OUTCOMES if outcome_columns_available else STATUS_AVAILABLE_SIGNAL_ONLY


def build_model(args: argparse.Namespace) -> dict[str, Any]:
    run_id = str(args.run_id)
    threshold_path = Path(args.train_only_thresholds)
    db_path = Path(args.db_path)
    canonical_path = Path(args.canonical_registry)
    threshold_payload, threshold_error = load_threshold_artifact(threshold_path)
    canonical_payload, canonical_error = read_json_object(canonical_path)
    warnings: list[dict[str, Any]] = []

    threshold_missing = bool(threshold_error)
    if threshold_missing:
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
    source_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    oos_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    offhours_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    rows: list[dict[str, Any]] = []
    evaluated_rows: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    bucket_rows: list[dict[str, Any]] = []
    condition_rows: list[dict[str, Any]] = []
    spread_pass_count = 0
    r_col = r_column(columns)
    reason_col = exit_reason_column(columns)
    outcome_columns_available = bool(r_col)
    cutoffs = threshold_cutoffs(threshold_payload) if threshold_payload else {}

    can_query = db_exists and table_exists and not missing_columns and not threshold_missing and not noncanonical_items and not non_train_errors
    if can_query:
        with connect_read_only(db_path) as connection:
            src_filters, src_params = source_filters(args, columns)
            source_info = one_row_window_query(
                connection=connection,
                table_name=str(args.feature_table),
                filters=src_filters,
                params=src_params,
            )
            if not oos_end_time:
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
            oos_all_filters, oos_all_params = oos_filters(
                args,
                columns,
                train_end_time=train_end_time,
                oos_start_time=oos_start_time,
                oos_end_time=oos_end_time,
                include_session=False,
            )
            oos_info = one_row_window_query(
                connection=connection,
                table_name=str(args.feature_table),
                filters=oos_all_filters,
                params=oos_all_params,
            )
            off_filters, off_params = oos_filters(
                args,
                columns,
                train_end_time=train_end_time,
                oos_start_time=oos_start_time,
                oos_end_time=oos_end_time,
                include_session=True,
            )
            offhours_info = one_row_window_query(
                connection=connection,
                table_name=str(args.feature_table),
                filters=off_filters,
                params=off_params,
            )
            rows = fetch_rows(
                connection=connection,
                table_name=str(args.feature_table),
                columns=columns,
                filters=off_filters,
                params=off_params,
            )
    if rows and cutoffs:
        evaluated_rows, matches, bucket_rows, eval_info = evaluate_oos_rows(
            rows,
            cutoffs=cutoffs,
            max_spread_points=float(args.max_spread_points),
            r_col=r_col,
            reason_col=reason_col,
        )
        condition_rows = eval_info["condition_rows"]
        spread_pass_count = int(eval_info["spread_pass_count"])

    if can_query and int(offhours_info["row_count"] or 0) == 0:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="empty_oos_window",
                message="No required-session OOS rows were available after train_end_time.",
                source=args.feature_table,
                blocking_warning=True,
            )
        )

    metrics = metrics_for_matches(matches, r_col, reason_col)
    replay_status = derive_status(
        threshold_missing=threshold_missing,
        threshold_non_train_only=bool(non_train_errors),
        noncanonical=bool(noncanonical_items),
        db_exists=db_exists,
        table_exists=table_exists,
        missing_columns=missing_columns,
        off_hours_oos_row_count=int(offhours_info["row_count"] or 0),
        outcome_columns_available=outcome_columns_available,
    )
    created_at = utc_now_text()
    manifest = {
        "run_id": run_id,
        "replay_status": replay_status,
        "candidate_id": EXPECTED_CANDIDATE_ID,
        "symbol": str(args.symbol),
        "timeframe": str(args.timeframe),
        "direction": EXPECTED_DIRECTION,
        "same_bar_policy": SAME_BAR_POLICY,
        "horizon_bars": HORIZON_BARS,
        "required_session": str(args.required_session),
        "max_spread_points": float(args.max_spread_points),
        "train_only_threshold_artifact": str(threshold_path),
        "threshold_lineage": threshold_payload.get("threshold_lineage", ""),
        "calibration_scope": threshold_payload.get("calibration_scope", ""),
        "train_end_time": train_end_time,
        "oos_start_time": oos_start_time,
        "oos_end_time": oos_end_time,
        "source_row_count": source_info["row_count"],
        "oos_row_count": oos_info["row_count"],
        "off_hours_oos_row_count": offhours_info["row_count"],
        "rule_match_count": len(matches),
        "spread_pass_count": spread_pass_count,
        "outcome_columns_available": outcome_columns_available,
        "r_column": r_col,
        "exit_reason_column": reason_col,
        "canonical_registry_sha256": sha256_file(canonical_path) if canonical_path.exists() and not canonical_error else "",
        "threshold_artifact_sha256": sha256_file(threshold_path) if threshold_path.exists() and not threshold_error else "",
        "feature_table": str(args.feature_table),
        "db_path": str(db_path),
        "missing_required_columns": missing_columns,
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(bool(warning["blocking_warning"]) for warning in warnings),
        "created_at_utc": created_at,
        "output_files": {},
        **metrics,
        **NO_ORDER_EVIDENCE,
    }
    summary = [{field: manifest.get(field) for field in SUMMARY_FIELDS}]
    window = [
        {
            "source_min_time_server": source_info["min_time_server"],
            "source_max_time_server": source_info["max_time_server"],
            "train_end_time": train_end_time,
            "oos_start_time": oos_start_time,
            "oos_end_time": oos_end_time,
            "source_row_count": source_info["row_count"],
            "oos_row_count": oos_info["row_count"],
            "off_hours_oos_row_count": offhours_info["row_count"],
        }
    ]
    no_order_evidence = [
        {"evidence_name": key, "value": value, "note": "artifact_only_train_threshold_oos_replay"}
        for key, value in NO_ORDER_EVIDENCE.items()
    ]
    return {
        "manifest": manifest,
        "summary": summary,
        "matches": matches,
        "bucket_counts": bucket_rows,
        "condition_counts": condition_rows,
        "window": window,
        "warnings": warnings,
        "no_order_evidence": no_order_evidence,
    }


def report_text(model: dict[str, Any]) -> str:
    manifest = model["manifest"]
    lines = [
        "# Fixed Candidate Train-Only Threshold OOS Replay",
        "",
        "Artifact-only OOS replay diagnostics using frozen train-only numeric tercile thresholds.",
        "",
        "## Status",
        "",
        f"- replay_status: `{manifest['replay_status']}`",
        f"- threshold_lineage: `{manifest['threshold_lineage']}`",
        f"- train_end_time: `{manifest['train_end_time']}`",
        f"- oos_start_time: `{manifest['oos_start_time']}`",
        f"- oos_end_time: `{manifest['oos_end_time']}`",
        "",
        "## Counts",
        "",
        f"- source_row_count: `{manifest['source_row_count']}`",
        f"- oos_row_count: `{manifest['oos_row_count']}`",
        f"- off_hours_oos_row_count: `{manifest['off_hours_oos_row_count']}`",
        f"- rule_match_count: `{manifest['rule_match_count']}`",
        f"- spread_pass_count: `{manifest['spread_pass_count']}`",
        "",
        "## Metrics",
        "",
        f"- outcome_columns_available: `{str(manifest['outcome_columns_available']).lower()}`",
        f"- trade_count: `{manifest.get('trade_count')}`",
        f"- mean_R: `{manifest.get('mean_R')}`",
        f"- median_R: `{manifest.get('median_R')}`",
        f"- sum_R: `{manifest.get('sum_R')}`",
        f"- profit_factor_R: `{manifest.get('profit_factor_R')}`",
        f"- win_rate_R_positive: `{manifest.get('win_rate_R_positive')}`",
        f"- max_drawdown_R: `{manifest.get('max_drawdown_R')}`",
        "",
        "## Safety Boundary",
        "",
        "- No canonical config update, DB mutation, future-state write, broker/API call, order check, order send, child workflow, scheduler, loop, background task, or trading decision was performed.",
    ]
    return "\n".join(lines) + "\n"


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for_args(args)
    paths = ensure_output_writable(output_dir, bool(args.overwrite))
    model = build_model(args)
    model["manifest"]["output_files"] = {label: str(path) for label, path in paths.items()}
    write_csv(paths["summary"], model["summary"], SUMMARY_FIELDS)
    write_csv(paths["matches"], model["matches"], MATCH_FIELDS)
    write_csv(paths["bucket_counts"], model["bucket_counts"], BUCKET_COUNT_FIELDS)
    write_csv(paths["condition_counts"], model["condition_counts"], CONDITION_COUNT_FIELDS)
    write_csv(paths["window"], model["window"], WINDOW_FIELDS)
    write_csv(paths["warnings"], model["warnings"], WARNING_FIELDS)
    write_csv(paths["no_order_evidence"], model["no_order_evidence"], ["evidence_name", "value", "note"])
    paths["report"].write_text(report_text(model), encoding="utf-8")
    write_json(paths["manifest"], model["manifest"])
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run artifact-only OOS replay diagnostics using train-only fixed-candidate thresholds."
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
        print(f"Fixed-candidate train-only threshold OOS replay blocked: {exc}")
        return 1
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate train-only threshold OOS replay failed: {exc}")
        return 1
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    print("Fixed-candidate train-only threshold OOS replay complete.")
    print(f"replay_status: {manifest['replay_status']}")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0 if str(manifest["replay_status"]).startswith("train_only_threshold_oos_replay_available") else 1


if __name__ == "__main__":
    raise SystemExit(main())
