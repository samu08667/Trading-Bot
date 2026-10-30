"""Build train-only frozen numeric-tercile thresholds for the fixed candidate.

This artifact builder reads a local SQLite feature table through a read-only
URI connection, requires an explicit training end time, and computes the fixed
candidate's numeric-tercile cutoffs only from rows inside the training window.
It does not run replay, backtest, holdout, cost sensitivity, MT5, broker, order,
or scheduler paths, and it does not mutate the database or canonical config.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_train_only_numeric_tercile_thresholds"
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_FEATURE_TABLE = "price_features"
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_SESSION_COLUMN = "hour_session"
DEFAULT_REQUIRED_SESSION = "Off_hours"
DEFAULT_FEATURES = ("close_to_ma_fast_atr_20", "tick_volume_percentile_100")
DEFAULT_MIN_TRAIN_ROWS = 500
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_train_only_numeric_tercile_thresholds"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_DIRECTION = "short"
EXPECTED_MAX_SPREAD_POINTS = 15.0
EXPECTED_REQUIRED_CONDITIONS = {
    "close_to_ma_fast_atr_20": "high_tercile",
    "tick_volume_percentile_100": "mid_tercile",
}

MANIFEST_FILE = "fixed_candidate_train_only_numeric_tercile_thresholds_manifest.json"
THRESHOLDS_FILE = "fixed_candidate_train_only_numeric_tercile_thresholds.json"
FEATURE_SUMMARY_FILE = "fixed_candidate_train_only_numeric_tercile_thresholds_feature_summary.csv"
SOURCE_WINDOW_FILE = "fixed_candidate_train_only_numeric_tercile_thresholds_source_window.csv"
VALIDATION_FILE = "fixed_candidate_train_only_numeric_tercile_thresholds_validation.csv"
REPORT_FILE = "fixed_candidate_train_only_numeric_tercile_thresholds_report.md"
WARNINGS_FILE = "fixed_candidate_train_only_numeric_tercile_thresholds_warnings.csv"
NO_ORDER_EVIDENCE_FILE = "fixed_candidate_train_only_numeric_tercile_thresholds_no_order_evidence.csv"

STATUS_AVAILABLE = "train_only_numeric_tercile_thresholds_available"
STATUS_MISSING_TRAIN_END = "train_only_numeric_tercile_thresholds_blocked_missing_train_end_time"
STATUS_MISSING_DB = "train_only_numeric_tercile_thresholds_blocked_missing_db"
STATUS_MISSING_TABLE = "train_only_numeric_tercile_thresholds_blocked_missing_table"
STATUS_MISSING_COLUMNS = "train_only_numeric_tercile_thresholds_blocked_missing_columns"
STATUS_EMPTY_TRAIN = "train_only_numeric_tercile_thresholds_blocked_empty_train_window"
STATUS_INSUFFICIENT_ROWS = "train_only_numeric_tercile_thresholds_blocked_insufficient_rows"
STATUS_NONCANONICAL = "train_only_numeric_tercile_thresholds_blocked_noncanonical_candidate"
STATUS_OUTPUT_EXISTS = "train_only_numeric_tercile_thresholds_blocked_output_exists_without_overwrite"

OUTPUT_KEYS = {
    "manifest": MANIFEST_FILE,
    "thresholds": THRESHOLDS_FILE,
    "feature_summary": FEATURE_SUMMARY_FILE,
    "source_window": SOURCE_WINDOW_FILE,
    "validation": VALIDATION_FILE,
    "report": REPORT_FILE,
    "warnings": WARNINGS_FILE,
    "no_order_evidence": NO_ORDER_EVIDENCE_FILE,
}

WARNING_FIELDNAMES = [
    "run_id",
    "warning_code",
    "severity",
    "message",
    "source",
    "blocking_warning",
]

VALIDATION_FIELDNAMES = [
    "check_name",
    "status",
    "observed",
    "expected",
    "blocking",
    "warning_code",
]

FEATURE_SUMMARY_FIELDNAMES = [
    "feature_name",
    "non_null_count",
    "low_mid_cutoff",
    "mid_high_cutoff",
    "required_bucket",
    "status",
]

SOURCE_WINDOW_FIELDNAMES = [
    "source_min_time_server",
    "source_max_time_server",
    "train_start_time_requested",
    "train_start_time_effective",
    "train_end_time",
    "train_min_time_server",
    "train_max_time_server",
    "source_row_count",
    "train_row_count",
]

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


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_mtime_utc(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


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


def validation_row(
    *,
    check_name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    blocking: bool,
    warning_code: str = "",
) -> dict[str, Any]:
    return {
        "check_name": check_name,
        "status": "passed" if passed else "failed",
        "observed": observed,
        "expected": expected,
        "blocking": blocking,
        "warning_code": warning_code,
    }


def output_dir_for_args(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    return DEFAULT_OUTPUT_ROOT / str(args.run_id)


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {key: output_dir / name for key, name in OUTPUT_KEYS.items()}


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


def linear_quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("Cannot compute quantile for an empty sample.")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    weight = position - lower_index
    return lower_value + (upper_value - lower_value) * weight


def base_scope_filters(args: argparse.Namespace, columns: set[str]) -> tuple[list[str], list[Any], dict[str, bool]]:
    filters: list[str] = []
    params: list[Any] = []
    applied = {
        "symbol_filter_applied": False,
        "timeframe_filter_applied": False,
        "session_filter_applied": False,
    }
    if "symbol" in columns:
        filters.append(f"{quote_identifier('symbol')} = ?")
        params.append(str(args.symbol))
        applied["symbol_filter_applied"] = True
    if "timeframe" in columns:
        filters.append(f"{quote_identifier('timeframe')} = ?")
        params.append(str(args.timeframe))
        applied["timeframe_filter_applied"] = True
    if str(args.required_session or ""):
        filters.append(f"{quote_identifier(str(args.session_column))} = ?")
        params.append(str(args.required_session))
        applied["session_filter_applied"] = True
    return filters, params, applied


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


def fetch_train_values(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    feature: str,
    filters: list[str],
    params: list[Any],
) -> list[float]:
    feature_filters = [*filters, f"{quote_identifier(feature)} IS NOT NULL"]
    query = (
        f"SELECT {quote_identifier(feature)} AS value "
        f"FROM {quote_identifier(table_name)}"
        f"{where_clause(feature_filters)}"
    )
    values: list[float] = []
    for row in connection.execute(query, params):
        value = safe_float(row["value"])
        if value is not None:
            values.append(value)
    return values


def load_canonical_registry(args: argparse.Namespace) -> tuple[dict[str, Any], str, str]:
    path = Path(args.canonical_registry)
    payload, error = read_json_object(path)
    digest = sha256_file(path) if path.exists() and not error else ""
    return payload, error, digest


def canonical_mismatches(args: argparse.Namespace, canonical: dict[str, Any], error: str) -> list[str]:
    if error:
        return [f"canonical_registry_{error}"]
    checks = {
        "candidate_id": EXPECTED_CANDIDATE_ID,
        "symbol": str(args.symbol),
        "timeframe": str(args.timeframe),
        "direction": EXPECTED_DIRECTION,
        "max_spread_points": EXPECTED_MAX_SPREAD_POINTS,
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


def required_columns(args: argparse.Namespace, features: list[str]) -> set[str]:
    columns = {"time_server", *features}
    if str(args.required_session or ""):
        columns.add(str(args.session_column))
    return columns


def threshold_payload_for_feature(feature: str, values: list[float]) -> dict[str, Any]:
    low_mid = linear_quantile(values, 1 / 3)
    mid_high = linear_quantile(values, 2 / 3)
    return {
        "feature_name": feature,
        "non_null_count": len(values),
        "low_mid_cutoff": low_mid,
        "mid_high_cutoff": mid_high,
        "bucket_rules": {
            "low_tercile": "value <= low_mid_cutoff",
            "mid_tercile": "low_mid_cutoff < value <= mid_high_cutoff",
            "high_tercile": "value > mid_high_cutoff",
        },
    }


def derive_status(
    *,
    train_end_time: str,
    db_exists: bool,
    table_exists: bool,
    missing_columns: list[str],
    canonical_mismatch_items: list[str],
    train_row_count: int,
    min_train_rows: int,
    insufficient_features: list[str],
) -> str:
    if not train_end_time:
        return STATUS_MISSING_TRAIN_END
    if canonical_mismatch_items:
        return STATUS_NONCANONICAL
    if not db_exists:
        return STATUS_MISSING_DB
    if not table_exists:
        return STATUS_MISSING_TABLE
    if missing_columns:
        return STATUS_MISSING_COLUMNS
    if train_row_count == 0:
        return STATUS_EMPTY_TRAIN
    if train_row_count < min_train_rows or insufficient_features:
        return STATUS_INSUFFICIENT_ROWS
    return STATUS_AVAILABLE


def build_artifact_model(args: argparse.Namespace) -> dict[str, Any]:
    run_id = str(args.run_id)
    db_path = Path(args.db_path)
    feature_table = str(args.feature_table)
    features = list(args.feature or DEFAULT_FEATURES)
    train_end_time = str(args.train_end_time or "").strip()
    train_start_requested = str(args.train_start_time or "").strip()
    canonical, canonical_error, canonical_digest = load_canonical_registry(args)
    canonical_mismatch_items = canonical_mismatches(args, canonical, canonical_error)
    table_exists = False
    columns: set[str] = set()
    schema_error = ""
    missing_columns: list[str] = []
    source_window = {
        "source_min_time_server": "",
        "source_max_time_server": "",
        "train_start_time_requested": train_start_requested,
        "train_start_time_effective": "",
        "train_end_time": train_end_time,
        "train_min_time_server": "",
        "train_max_time_server": "",
        "source_row_count": 0,
        "train_row_count": 0,
    }
    filter_flags = {
        "symbol_filter_applied": False,
        "timeframe_filter_applied": False,
        "session_filter_applied": False,
    }
    feature_values: dict[str, list[float]] = {}
    feature_payloads: dict[str, dict[str, Any]] = {}
    feature_summary: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []

    db_exists = db_path.exists()
    validation.append(
        validation_row(
            check_name="train_end_time_provided",
            passed=bool(train_end_time),
            observed=train_end_time,
            expected="non-empty --train-end-time",
            blocking=True,
            warning_code="" if train_end_time else "missing_train_end_time",
        )
    )
    if not train_end_time:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="missing_train_end_time",
                message="--train-end-time is required for train-only threshold lineage.",
                source="--train-end-time",
                blocking_warning=True,
            )
        )

    validation.append(
        validation_row(
            check_name="canonical_candidate",
            passed=not canonical_mismatch_items,
            observed=";".join(canonical_mismatch_items),
            expected=EXPECTED_CANDIDATE_ID,
            blocking=True,
            warning_code="" if not canonical_mismatch_items else "noncanonical_candidate",
        )
    )
    if canonical_mismatch_items:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="noncanonical_candidate",
                message="Canonical registry does not match the fixed candidate: "
                + "; ".join(canonical_mismatch_items),
                source=args.canonical_registry,
                blocking_warning=True,
            )
        )

    validation.append(
        validation_row(
            check_name="db_exists",
            passed=db_exists,
            observed=db_path,
            expected="existing SQLite DB",
            blocking=True,
            warning_code="" if db_exists else "missing_db",
        )
    )
    if not db_exists:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="missing_db",
                message="Configured SQLite DB does not exist.",
                source=db_path,
                blocking_warning=True,
            )
        )
    else:
        table_exists, columns, schema_error = inspect_table(db_path, feature_table)

    validation.append(
        validation_row(
            check_name="feature_table_exists",
            passed=table_exists,
            observed=feature_table if table_exists else schema_error,
            expected=feature_table,
            blocking=True,
            warning_code="" if table_exists else "missing_table",
        )
    )
    if db_exists and not table_exists:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="missing_table",
                message="Configured feature table is missing or unreadable.",
                source=feature_table,
                blocking_warning=True,
            )
        )

    if table_exists:
        missing_columns = sorted(required_columns(args, features) - columns)
    validation.append(
        validation_row(
            check_name="required_columns_present",
            passed=not missing_columns,
            observed=";".join(missing_columns),
            expected="time_server, requested features, and required session column",
            blocking=True,
            warning_code="" if not missing_columns else "missing_columns",
        )
    )
    if missing_columns:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="missing_columns",
                message="Feature table is missing required columns: " + ", ".join(missing_columns),
                source=feature_table,
                blocking_warning=True,
            )
        )

    can_query = db_exists and table_exists and not missing_columns
    if can_query:
        with connect_read_only(db_path) as connection:
            base_filters, base_params, filter_flags = base_scope_filters(args, columns)
            source_info = one_row_window_query(
                connection=connection,
                table_name=feature_table,
                filters=base_filters,
                params=base_params,
            )
            train_start_effective = train_start_requested or str(source_info["min_time_server"] or "")
            train_filters = list(base_filters)
            train_params = list(base_params)
            if train_start_requested:
                train_filters.append(f"{quote_identifier('time_server')} >= ?")
                train_params.append(train_start_requested)
            if train_end_time:
                train_filters.append(f"{quote_identifier('time_server')} <= ?")
                train_params.append(train_end_time)
            train_info = one_row_window_query(
                connection=connection,
                table_name=feature_table,
                filters=train_filters,
                params=train_params,
            )
            source_window = {
                "source_min_time_server": source_info["min_time_server"],
                "source_max_time_server": source_info["max_time_server"],
                "train_start_time_requested": train_start_requested,
                "train_start_time_effective": train_start_effective,
                "train_end_time": train_end_time,
                "train_min_time_server": train_info["min_time_server"],
                "train_max_time_server": train_info["max_time_server"],
                "source_row_count": source_info["row_count"],
                "train_row_count": train_info["row_count"],
            }
            for feature in features:
                values = fetch_train_values(
                    connection=connection,
                    table_name=feature_table,
                    feature=feature,
                    filters=train_filters,
                    params=train_params,
                )
                feature_values[feature] = values

    train_row_count = int(source_window["train_row_count"] or 0)
    insufficient_features = [
        feature for feature, values in feature_values.items() if len(values) < int(args.min_train_rows)
    ]
    for feature in features:
        values = feature_values.get(feature, [])
        if values and len(values) >= int(args.min_train_rows):
            payload = threshold_payload_for_feature(feature, values)
            feature_payloads[feature] = payload
            feature_summary.append(
                {
                    "feature_name": feature,
                    "non_null_count": payload["non_null_count"],
                    "low_mid_cutoff": payload["low_mid_cutoff"],
                    "mid_high_cutoff": payload["mid_high_cutoff"],
                    "required_bucket": EXPECTED_REQUIRED_CONDITIONS.get(feature, ""),
                    "status": "available",
                }
            )
        else:
            feature_summary.append(
                {
                    "feature_name": feature,
                    "non_null_count": len(values),
                    "low_mid_cutoff": "",
                    "mid_high_cutoff": "",
                    "required_bucket": EXPECTED_REQUIRED_CONDITIONS.get(feature, ""),
                    "status": "insufficient_rows",
                }
            )

    validation.append(
        validation_row(
            check_name="train_window_not_empty",
            passed=train_row_count > 0,
            observed=train_row_count,
            expected="> 0",
            blocking=True,
            warning_code="" if train_row_count > 0 else "empty_train_window",
        )
    )
    validation.append(
        validation_row(
            check_name="train_row_count_minimum",
            passed=train_row_count >= int(args.min_train_rows),
            observed=train_row_count,
            expected=int(args.min_train_rows),
            blocking=True,
            warning_code="" if train_row_count >= int(args.min_train_rows) else "insufficient_train_rows",
        )
    )
    for feature in features:
        count = len(feature_values.get(feature, []))
        validation.append(
            validation_row(
                check_name=f"{feature}_non_null_minimum",
                passed=count >= int(args.min_train_rows),
                observed=count,
                expected=int(args.min_train_rows),
                blocking=True,
                warning_code="" if count >= int(args.min_train_rows) else "insufficient_feature_rows",
            )
        )

    if train_row_count == 0 and can_query:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="empty_train_window",
                message="No rows matched the requested train window.",
                source=feature_table,
                blocking_warning=True,
            )
        )
    elif can_query and train_row_count < int(args.min_train_rows):
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="insufficient_train_rows",
                message=f"Train window has {train_row_count} rows, below minimum {args.min_train_rows}.",
                source=feature_table,
                blocking_warning=True,
            )
        )
    if can_query:
        for feature in insufficient_features:
            warnings.append(
                warning_row(
                    run_id=run_id,
                    warning_code="insufficient_feature_rows",
                    message=(
                        f"{feature} has {len(feature_values.get(feature, []))} non-null train rows, "
                        f"below minimum {args.min_train_rows}."
                    ),
                    source=feature_table,
                    blocking_warning=True,
                )
            )

    status = derive_status(
        train_end_time=train_end_time,
        db_exists=db_exists,
        table_exists=table_exists,
        missing_columns=missing_columns,
        canonical_mismatch_items=canonical_mismatch_items,
        train_row_count=train_row_count,
        min_train_rows=int(args.min_train_rows),
        insufficient_features=insufficient_features,
    )
    created_at = utc_now_text()
    threshold_json = {
        "candidate_id": EXPECTED_CANDIDATE_ID,
        "symbol": str(args.symbol),
        "timeframe": str(args.timeframe),
        "threshold_lineage": "train_only",
        "calibration_scope": "train_window_only",
        "train_start_time_effective": source_window["train_start_time_effective"],
        "train_end_time": train_end_time,
        "required_session": str(args.required_session or ""),
        "features": feature_payloads,
        "required_conditions": dict(EXPECTED_REQUIRED_CONDITIONS),
        "full_sample_thresholds_used": False,
        "train_end_time_required": True,
        "oos_rows_used_for_thresholds": False,
        "threshold_status": status,
        "created_at_utc": created_at,
    }
    threshold_digest = sha256_text(canonical_json(threshold_json))
    db_size = db_path.stat().st_size if db_path.exists() else 0
    manifest = {
        "run_id": run_id,
        "threshold_status": status,
        "candidate_id": EXPECTED_CANDIDATE_ID,
        "symbol": str(args.symbol),
        "timeframe": str(args.timeframe),
        "required_session": str(args.required_session or ""),
        "feature_table": feature_table,
        "db_path": str(db_path),
        "db_size_bytes": db_size,
        "db_mtime_utc": file_mtime_utc(db_path),
        "train_start_time_requested": train_start_requested,
        "train_start_time_effective": source_window["train_start_time_effective"],
        "train_end_time": train_end_time,
        "source_min_time_server": source_window["source_min_time_server"],
        "source_max_time_server": source_window["source_max_time_server"],
        "train_min_time_server": source_window["train_min_time_server"],
        "train_max_time_server": source_window["train_max_time_server"],
        "source_row_count": source_window["source_row_count"],
        "train_row_count": source_window["train_row_count"],
        "feature_count": len(features),
        "min_train_rows": int(args.min_train_rows),
        "threshold_lineage": "train_only",
        "calibration_scope": "train_window_only",
        "full_sample_thresholds_used": False,
        "train_end_time_required": True,
        "oos_rows_used_for_thresholds": False,
        "canonical_registry_sha256": canonical_digest,
        "threshold_payload_sha256": threshold_digest,
        "output_files": {},
        "created_at_utc": created_at,
        "canonical_registry": str(args.canonical_registry),
        "canonical_mismatch_count": len(canonical_mismatch_items),
        "canonical_mismatches": canonical_mismatch_items,
        "missing_required_columns": missing_columns,
        "symbol_filter_applied": filter_flags["symbol_filter_applied"],
        "timeframe_filter_applied": filter_flags["timeframe_filter_applied"],
        "session_filter_applied": filter_flags["session_filter_applied"],
        "warning_count": len(warnings),
        "blocking_warning_count": sum(bool(warning["blocking_warning"]) for warning in warnings),
        **NO_ORDER_EVIDENCE,
    }
    return {
        "manifest": manifest,
        "threshold_json": threshold_json,
        "feature_summary": feature_summary,
        "source_window": [source_window],
        "validation": validation,
        "warnings": warnings,
        "no_order_evidence": [
            {"evidence_name": key, "value": value, "note": "artifact_builder_static_no_order_boundary"}
            for key, value in NO_ORDER_EVIDENCE.items()
        ],
    }


def report_text(model: dict[str, Any]) -> str:
    manifest = model["manifest"]
    lines = [
        "# Fixed Candidate Train-Only Numeric Tercile Thresholds",
        "",
        "Artifact-only builder for frozen train-window numeric tercile thresholds.",
        "",
        "## Status",
        "",
        f"- threshold_status: `{manifest['threshold_status']}`",
        f"- threshold_lineage: `{manifest['threshold_lineage']}`",
        f"- calibration_scope: `{manifest['calibration_scope']}`",
        f"- full_sample_thresholds_used: `{str(manifest['full_sample_thresholds_used']).lower()}`",
        f"- oos_rows_used_for_thresholds: `{str(manifest['oos_rows_used_for_thresholds']).lower()}`",
        "",
        "## Train Window",
        "",
        f"- train_start_time_requested: `{manifest['train_start_time_requested']}`",
        f"- train_start_time_effective: `{manifest['train_start_time_effective']}`",
        f"- train_end_time: `{manifest['train_end_time']}`",
        f"- source_min_time_server: `{manifest['source_min_time_server']}`",
        f"- source_max_time_server: `{manifest['source_max_time_server']}`",
        f"- train_min_time_server: `{manifest['train_min_time_server']}`",
        f"- train_max_time_server: `{manifest['train_max_time_server']}`",
        f"- source_row_count: `{manifest['source_row_count']}`",
        f"- train_row_count: `{manifest['train_row_count']}`",
        "",
        "## Feature Summary",
        "",
        "| Feature | Non-Null Train Rows | Low/Mid Cutoff | Mid/High Cutoff | Required Bucket | Status |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in model["feature_summary"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["feature_name"]),
                    str(row["non_null_count"]),
                    str(row["low_mid_cutoff"]),
                    str(row["mid_high_cutoff"]),
                    str(row["required_bucket"]),
                    str(row["status"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Safety Evidence",
            "",
            "- No MT5 import, connection, broker query, order check, order send, order calculation, history read, child script, scheduler, loop, background task, DB mutation, future-state write, executable payload, or trading decision was performed.",
            "- The canonical registry pointer was not updated.",
            "- Replay, backtest, holdout, cost sensitivity, no-order cycle, shadow, and paper workflows were not run.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for_args(args)
    paths = ensure_output_writable(output_dir, bool(args.overwrite))
    model = build_artifact_model(args)
    output_file_map = {key: str(path) for key, path in paths.items()}
    model["manifest"]["output_files"] = output_file_map
    write_json(paths["thresholds"], model["threshold_json"])
    write_csv(paths["feature_summary"], model["feature_summary"], FEATURE_SUMMARY_FIELDNAMES)
    write_csv(paths["source_window"], model["source_window"], SOURCE_WINDOW_FIELDNAMES)
    write_csv(paths["validation"], model["validation"], VALIDATION_FIELDNAMES)
    write_csv(paths["warnings"], model["warnings"], WARNING_FIELDNAMES)
    write_csv(
        paths["no_order_evidence"],
        model["no_order_evidence"],
        ["evidence_name", "value", "note"],
    )
    paths["report"].write_text(report_text(model), encoding="utf-8")
    write_json(paths["manifest"], model["manifest"])
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build train-only frozen numeric-tercile threshold artifacts for the fixed candidate. "
            "--train-end-time is required for a non-blocked artifact."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--feature-table", default=DEFAULT_FEATURE_TABLE)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--train-start-time")
    parser.add_argument("--train-end-time")
    parser.add_argument("--session-column", default=DEFAULT_SESSION_COLUMN)
    parser.add_argument("--required-session", default=DEFAULT_REQUIRED_SESSION)
    parser.add_argument("--feature", action="append")
    parser.add_argument("--min-train-rows", type=int, default=DEFAULT_MIN_TRAIN_ROWS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except BlockedStatusError as exc:
        print(f"Fixed-candidate train-only numeric-tercile threshold build blocked: {exc}")
        return 1
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate train-only numeric-tercile threshold build failed: {exc}")
        return 1
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    print("Fixed-candidate train-only numeric-tercile threshold artifacts written.")
    print(f"threshold_status: {manifest['threshold_status']}")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0 if manifest["threshold_status"] == STATUS_AVAILABLE else 1


if __name__ == "__main__":
    raise SystemExit(main())
