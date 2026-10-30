"""Freeze numeric-tercile thresholds for the fixed-candidate paper logger.

This artifact-only builder reads an allowlisted local SQLite feature table in
read-only mode, calculates deterministic numeric-tercile boundaries for the
fixed candidate's required features, and writes versioned threshold artifacts.
It does not implement or run a paper signal logger, connect to MT5, connect to
broker/API services, execute orders, run backtests, run validation, generate
market data, mutate a database, or make candidate-quality or trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_numeric_tercile_thresholds"
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR
    / "config"
    / "paper_demo"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)
DEFAULT_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger_readiness"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_readiness_v1"
)
DEFAULT_FEATURE_SOURCE_DB = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_FEATURE_SOURCE_TABLE = "price_features"
DEFAULT_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_REGIME_COLUMN = "hour_session"
DEFAULT_REGIME_VALUE = "Off_hours"
DEFAULT_FEATURES = ("close_to_ma_fast_atr_20", "tick_volume_percentile_100")
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_numeric_tercile_thresholds"
DEFAULT_MIN_NON_NULL_COUNT = 100
DEFAULT_QUANTILE_METHOD = "linear"

READINESS_CSV = "fixed_candidate_paper_signal_logger_readiness.csv"
READINESS_REPORT = "fixed_candidate_paper_signal_logger_readiness_report.md"
READINESS_WARNINGS = "fixed_candidate_paper_signal_logger_readiness_warnings.csv"
READINESS_MANIFEST = "fixed_candidate_paper_signal_logger_readiness_manifest.json"

OUTPUT_JSON = "fixed_candidate_numeric_tercile_thresholds.json"
OUTPUT_REPORT = "fixed_candidate_numeric_tercile_thresholds_report.md"
OUTPUT_WARNINGS = "fixed_candidate_numeric_tercile_thresholds_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_numeric_tercile_thresholds_manifest.json"

WARNING_FIELDNAMES = [
    "run_id",
    "warning_code",
    "severity",
    "message",
    "source",
    "blocking_warning",
]

ALLOWLISTED_FEATURE_TABLES = {"price_features", "market_features"}
FORBIDDEN_FEATURE_TABLES = {"ml_dataset"}
REQUIRED_BUCKET_FOR_FEATURE = {
    "close_to_ma_fast_atr_20": "high_tercile",
    "tick_volume_percentile_100": "mid_tercile",
}
THRESHOLD_RELATED_WARNING_TOKENS = ("threshold", "tercile")


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
    except (OSError, csv.Error) as exc:
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
        "threshold_json": output_dir / OUTPUT_JSON,
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


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    run_id: str,
    warning_code: str,
    message: str,
    source: Path | str,
    blocking_warning: bool = False,
    severity: str = "warning",
) -> None:
    warnings.append(
        warning_row(
            run_id=run_id,
            warning_code=warning_code,
            message=message,
            source=source,
            blocking_warning=blocking_warning,
            severity=severity,
        )
    )


def load_config(path: Path) -> dict[str, Any]:
    data, error = read_json(path)
    paper_boundary_ok = bool(
        data
        and data.get("paper_only") is True
        and data.get("broker_connection_allowed") is False
        and data.get("order_execution_allowed") is False
        and data.get("real_money_allowed") is False
    )
    return {
        "path": path,
        "data": data,
        "exists": path.exists(),
        "error": error,
        "loaded": path.exists() and not error and bool(data),
        "paper_boundary_ok": paper_boundary_ok,
    }


def readiness_paths(root: Path) -> dict[str, Path]:
    return {
        "dir": root,
        "csv": root / READINESS_CSV,
        "manifest": root / READINESS_MANIFEST,
        "report": root / READINESS_REPORT,
        "warnings": root / READINESS_WARNINGS,
    }


def load_readiness(root: Path) -> dict[str, Any]:
    paths = readiness_paths(root)
    rows, csv_error = read_csv_rows(paths["csv"])
    manifest, manifest_error = read_json(paths["manifest"])
    warnings, warnings_error = read_csv_rows(paths["warnings"])
    report = read_text(paths["report"])
    files_present = paths["csv"].exists() and paths["manifest"].exists() and paths["report"].exists()
    return {
        "paths": paths,
        "rows": rows,
        "manifest": manifest,
        "warnings": warnings,
        "report": report,
        "files_present": files_present,
        "error": ";".join(error for error in (csv_error, manifest_error, warnings_error) if error),
        "loaded": files_present and not (csv_error or manifest_error or warnings_error),
    }


def readiness_has_only_threshold_blockers(readiness: dict[str, Any]) -> bool:
    if not readiness["loaded"]:
        return False
    manifest = readiness["manifest"]
    non_threshold_blocker_fields = (
        "blocked_missing_required_artifact_count",
        "blocked_missing_required_column_count",
        "blocked_unreadable_input_count",
        "blocked_by_leakage_risk_count",
        "blocked_by_config_count",
    )
    if any(int(manifest.get(field) or 0) for field in non_threshold_blocker_fields):
        return False
    blocking_warnings = [
        row for row in readiness["warnings"] if str(row.get("blocking_warning") or "").lower() == "true"
    ]
    if not blocking_warnings:
        return True
    return all(
        any(token in str(row.get("warning_code") or "").lower() for token in THRESHOLD_RELATED_WARNING_TOKENS)
        for row in blocking_warnings
    )


def inspect_schema(db_path: Path, table_name: str) -> dict[str, Any]:
    if not db_path.exists():
        return {"db_exists": False, "table_exists": False, "columns": set(), "error": ""}
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            table_exists = (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone()
                is not None
            )
            columns: set[str] = set()
            if table_exists:
                columns = {
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
                }
            return {"db_exists": True, "table_exists": table_exists, "columns": columns, "error": ""}
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return {"db_exists": True, "table_exists": False, "columns": set(), "error": str(exc)}


def safe_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def linear_quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("Cannot calculate quantile from an empty list.")
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


def connect_read_only(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def fetch_feature_values(
    *,
    db_path: Path,
    table_name: str,
    feature: str,
    symbol: str,
    timeframe: str,
    regime_column: str,
    regime_value: str,
    columns: set[str],
) -> tuple[list[float], dict[str, bool]]:
    filters: list[str] = [f"{quote_identifier(feature)} IS NOT NULL"]
    params: list[Any] = []
    filter_flags = {
        "symbol_filter_applied": False,
        "timeframe_filter_applied": False,
        "regime_filter_applied": False,
    }
    if "symbol" in columns:
        filters.append(f"{quote_identifier('symbol')} = ?")
        params.append(symbol)
        filter_flags["symbol_filter_applied"] = True
    if "timeframe" in columns:
        filters.append(f"{quote_identifier('timeframe')} = ?")
        params.append(timeframe)
        filter_flags["timeframe_filter_applied"] = True
    if regime_column in columns:
        filters.append(f"{quote_identifier(regime_column)} = ?")
        params.append(regime_value)
        filter_flags["regime_filter_applied"] = True
    query = (
        f"SELECT {quote_identifier(feature)} FROM {quote_identifier(table_name)} "
        f"WHERE {' AND '.join(filters)}"
    )
    with connect_read_only(db_path) as connection:
        rows = connection.execute(query, params).fetchall()
    values = [number for row in rows if (number := safe_float(row[0])) is not None]
    return values, filter_flags


def feature_threshold_payload(feature: str, values: list[float], required_bucket: str) -> dict[str, Any]:
    lower = linear_quantile(values, 1 / 3)
    upper = linear_quantile(values, 2 / 3)
    return {
        "non_null_count": len(values),
        "lower_tercile_boundary": lower,
        "upper_tercile_boundary": upper,
        "bucket_definitions": {
            "low_tercile": "value <= lower_tercile_boundary",
            "mid_tercile": "lower_tercile_boundary < value <= upper_tercile_boundary",
            "high_tercile": "value > upper_tercile_boundary",
        },
        "low_tercile": {
            "upper_bound": lower,
            "condition": "value <= lower_tercile_boundary",
        },
        "mid_tercile": {
            "lower_bound_exclusive": lower,
            "upper_bound": upper,
            "condition": "lower_tercile_boundary < value <= upper_tercile_boundary",
        },
        "high_tercile": {
            "lower_bound_exclusive": upper,
            "condition": "value > upper_tercile_boundary",
        },
        "required_bucket_for_candidate": required_bucket,
    }


def build_thresholds(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    config = load_config(Path(args.demo_strategy_config))
    readiness = load_readiness(Path(args.paper_signal_logger_readiness_dir))
    schema = inspect_schema(Path(args.feature_source_db), str(args.feature_source_table))
    table_name = str(args.feature_source_table)
    features = [str(feature) for feature in args.features]
    table_allowlisted = table_name in ALLOWLISTED_FEATURE_TABLES
    blocked_by_leakage = table_name in FORBIDDEN_FEATURE_TABLES
    missing_required_columns: list[str] = []
    insufficient_features: list[str] = []
    computed_features: dict[str, Any] = {}
    filter_flags = {
        "symbol_filter_applied": False,
        "timeframe_filter_applied": False,
        "regime_filter_applied": False,
    }

    if not config["exists"]:
        add_warning(
            warnings,
            run_id=args.run_id,
            warning_code="demo_strategy_config_missing",
            message="Canonical demo strategy config is missing.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    elif not config["loaded"]:
        add_warning(
            warnings,
            run_id=args.run_id,
            warning_code="demo_strategy_config_unreadable",
            message=f"Canonical demo strategy config is unreadable: {config['error']}",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    elif not config["paper_boundary_ok"]:
        add_warning(
            warnings,
            run_id=args.run_id,
            warning_code="paper_only_boundary_not_confirmed",
            message="Canonical demo strategy config does not preserve the paper-only boundary.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )

    if not readiness["loaded"]:
        add_warning(
            warnings,
            run_id=args.run_id,
            warning_code="paper_signal_logger_readiness_missing_or_unreadable",
            message="Paper signal logger readiness artifact is missing or unreadable.",
            source=args.paper_signal_logger_readiness_dir,
            blocking_warning=True,
        )
    elif not readiness_has_only_threshold_blockers(readiness):
        add_warning(
            warnings,
            run_id=args.run_id,
            warning_code="paper_signal_logger_readiness_has_non_threshold_blockers",
            message="Readiness artifact has blockers other than the missing numeric-tercile threshold artifact.",
            source=args.paper_signal_logger_readiness_dir,
            blocking_warning=True,
        )

    if blocked_by_leakage:
        add_warning(
            warnings,
            run_id=args.run_id,
            warning_code="feature_source_table_leakage_risk",
            message="ml_dataset is blocked as a threshold source for the paper signal logger.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    elif not table_allowlisted:
        add_warning(
            warnings,
            run_id=args.run_id,
            warning_code="feature_source_table_not_allowlisted",
            message="Feature source table is not allowlisted.",
            source=args.feature_source_table,
            blocking_warning=True,
        )

    if schema["error"]:
        add_warning(
            warnings,
            run_id=args.run_id,
            warning_code="feature_source_db_unreadable",
            message=f"Feature source DB schema could not be inspected: {schema['error']}",
            source=args.feature_source_db,
            blocking_warning=True,
        )
    elif not schema["db_exists"]:
        add_warning(
            warnings,
            run_id=args.run_id,
            warning_code="feature_source_db_missing",
            message="Feature source DB is missing.",
            source=args.feature_source_db,
            blocking_warning=True,
        )
    elif not schema["table_exists"]:
        add_warning(
            warnings,
            run_id=args.run_id,
            warning_code="feature_source_table_missing",
            message="Feature source table is missing.",
            source=args.feature_source_table,
            blocking_warning=True,
        )

    columns = set(schema["columns"])
    if schema["table_exists"] and not blocked_by_leakage and table_allowlisted:
        for required_column in [*features, args.regime_column]:
            if required_column not in columns:
                missing_required_columns.append(required_column)
        if missing_required_columns:
            add_warning(
                warnings,
                run_id=args.run_id,
                warning_code="missing_required_column",
                message=f"Feature source table is missing required columns: {', '.join(missing_required_columns)}",
                source=args.feature_source_table,
                blocking_warning=True,
            )
        if "symbol" not in columns:
            add_warning(
                warnings,
                run_id=args.run_id,
                warning_code="symbol_filter_unavailable",
                message="symbol column is unavailable; symbol filtering was not applied.",
                source=args.feature_source_table,
                blocking_warning=False,
            )
        if "timeframe" not in columns:
            add_warning(
                warnings,
                run_id=args.run_id,
                warning_code="timeframe_filter_unavailable",
                message="timeframe column is unavailable; timeframe filtering was not applied.",
                source=args.feature_source_table,
                blocking_warning=False,
            )

    can_query = bool(
        schema["db_exists"]
        and schema["table_exists"]
        and table_allowlisted
        and not blocked_by_leakage
        and not missing_required_columns
    )
    if can_query:
        for feature in features:
            values, current_filter_flags = fetch_feature_values(
                db_path=Path(args.feature_source_db),
                table_name=table_name,
                feature=feature,
                symbol=str(args.symbol),
                timeframe=str(args.timeframe),
                regime_column=str(args.regime_column),
                regime_value=str(args.regime_value),
                columns=columns,
            )
            for key, value in current_filter_flags.items():
                filter_flags[key] = filter_flags[key] or value
            if len(values) < int(args.min_non_null_count):
                insufficient_features.append(feature)
                add_warning(
                    warnings,
                    run_id=args.run_id,
                    warning_code="insufficient_non_null_rows",
                    message=(
                        f"{feature} has {len(values)} non-null calibration rows, below "
                        f"minimum {args.min_non_null_count}."
                    ),
                    source=args.feature_source_table,
                    blocking_warning=True,
                )
                continue
            required_bucket = REQUIRED_BUCKET_FOR_FEATURE.get(feature, "")
            computed_features[feature] = feature_threshold_payload(feature, values, required_bucket)

    blocking_warnings = [warning for warning in warnings if str(warning["blocking_warning"]).lower() == "true"]
    threshold_json_valid = not blocking_warnings and len(computed_features) == len(features)
    generated_at = utc_now_text()
    threshold_json = {
        "schema_version": 1,
        "artifact_role": "fixed_candidate_numeric_tercile_thresholds",
        "run_id": args.run_id,
        "candidate_id": args.candidate_id,
        "generated_at": generated_at,
        "feature_source_db": str(args.feature_source_db),
        "feature_source_table": table_name,
        "quantile_method": args.quantile_method,
        "calibration_scope": {
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "regime_column": args.regime_column,
            "regime_value": args.regime_value,
            "paper_logger_use": True,
            "db_read_only": True,
        },
        "features": computed_features,
        "threshold_json_valid": threshold_json_valid,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_trading_decision_performed": True,
    }
    metadata = {
        "generated_at": generated_at,
        "config": config,
        "readiness": readiness,
        "schema": schema,
        "table_allowlisted": table_allowlisted,
        "blocked_by_leakage": blocked_by_leakage,
        "missing_required_columns": missing_required_columns,
        "insufficient_features": insufficient_features,
        "filter_flags": filter_flags,
        "threshold_feature_count": len(computed_features),
        "threshold_json_valid": threshold_json_valid,
        "features": features,
    }
    return threshold_json, warnings, metadata


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    threshold_json: dict[str, Any],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    feature_lines = [
        "| Feature | Non-Null Count | Lower Boundary | Upper Boundary | Required Candidate Bucket |",
        "|---|---:|---:|---:|---|",
    ]
    for feature, payload in threshold_json["features"].items():
        feature_lines.append(
            "| "
            + " | ".join(
                [
                    str(feature),
                    str(payload.get("non_null_count", "")),
                    str(payload.get("lower_tercile_boundary", "")),
                    str(payload.get("upper_tercile_boundary", "")),
                    str(payload.get("required_bucket_for_candidate", "")),
                ]
            )
            + " |"
        )
    if len(feature_lines) == 2:
        feature_lines.append("| none | 0 |  |  |  |")

    lines = [
        "# Fixed Candidate Numeric Tercile Thresholds",
        "",
        "Artifact-only threshold builder. These thresholds are frozen for future paper logger evaluation.",
        "DB read-only mode was used for schema inspection and controlled feature-column reads.",
        "No data generation was performed.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- paper_signal_logger_readiness_dir: `{args.paper_signal_logger_readiness_dir}`",
        f"- feature_source_db: `{args.feature_source_db}`",
        f"- feature_source_table: `{args.feature_source_table}`",
        "",
        "## Calibration Scope",
        "",
        f"- candidate_id: `{args.candidate_id}`",
        f"- symbol: `{args.symbol}`",
        f"- timeframe: `{args.timeframe}`",
        f"- regime filter: `{args.regime_column}={args.regime_value}`",
        f"- features: `{';'.join(metadata['features'])}`",
        "",
        "## Filters Applied",
        "",
        f"- symbol_filter_applied: `{bool_text(bool(metadata['filter_flags']['symbol_filter_applied']))}`",
        f"- timeframe_filter_applied: `{bool_text(bool(metadata['filter_flags']['timeframe_filter_applied']))}`",
        f"- regime_filter_applied: `{bool_text(bool(metadata['filter_flags']['regime_filter_applied']))}`",
        "",
        "## Quantile Method",
        "",
        f"`{args.quantile_method}` with lower boundary at 1/3 and upper boundary at 2/3.",
        "",
        "## Threshold Table",
        "",
        *feature_lines,
        "",
        "## Caveats",
        "",
        "- Thresholds are frozen for future paper logger evaluation.",
        "- The future one-row logger must not recompute these thresholds.",
        "- The future paper logger must skip if this threshold artifact is missing or unreadable.",
        "- Spread numeric threshold configuration remains separate.",
        "",
        "## Next Step",
        "",
        "Rerun paper signal logger readiness using this threshold artifact.",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{sum(str(warning['blocking_warning']).lower() == 'true' for warning in warnings)}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    threshold_json_path: Path,
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    blocking = [warning for warning in warnings if str(warning["blocking_warning"]).lower() == "true"]
    warning_codes = [str(warning["warning_code"]) for warning in warnings]
    manifest = {
        "run_id": args.run_id,
        "generated_at": metadata["generated_at"],
        "output_dir": str(output_dir),
        "threshold_json_path": str(threshold_json_path),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "paper_signal_logger_readiness_dir": str(args.paper_signal_logger_readiness_dir),
        "feature_source_db": str(args.feature_source_db),
        "feature_source_table": str(args.feature_source_table),
        "feature_source_table_allowlisted": bool(metadata["table_allowlisted"]),
        "candidate_id": args.candidate_id,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "regime_column": args.regime_column,
        "regime_value": args.regime_value,
        "features": list(metadata["features"]),
        "quantile_method": args.quantile_method,
        "min_non_null_count": int(args.min_non_null_count),
        "calibration_filter_applied": bool(metadata["filter_flags"]["regime_filter_applied"]),
        "symbol_filter_applied": bool(metadata["filter_flags"]["symbol_filter_applied"]),
        "timeframe_filter_applied": bool(metadata["filter_flags"]["timeframe_filter_applied"]),
        "regime_filter_applied": bool(metadata["filter_flags"]["regime_filter_applied"]),
        "threshold_feature_count": int(metadata["threshold_feature_count"]),
        "threshold_json_written": True,
        "threshold_json_valid": bool(metadata["threshold_json_valid"]),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking),
        "blocked_by_leakage_risk_count": sum(code == "feature_source_table_leakage_risk" for code in warning_codes),
        "blocked_missing_required_column_count": sum(code == "missing_required_column" for code in warning_codes),
        "blocked_insufficient_rows_count": sum(code == "insufficient_non_null_rows" for code in warning_codes),
        "no_child_scripts_executed": True,
        "no_paper_runner_executed": True,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_backtests_run": True,
        "no_stress_validation_executed": True,
        "no_walk_forward_validation_executed": True,
        "no_timeout_policy_review_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    threshold_json, warnings, metadata = build_thresholds(args)
    paths["threshold_json"].write_text(json.dumps(threshold_json, indent=2, sort_keys=True), encoding="utf-8")
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, threshold_json=threshold_json, warnings=warnings, metadata=metadata)
    write_manifest(
        paths["manifest"],
        args=args,
        output_dir=output_dir,
        threshold_json_path=paths["threshold_json"],
        warnings=warnings,
        metadata=metadata,
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build artifact-only frozen numeric-tercile thresholds for the fixed-candidate paper signal logger."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--paper-signal-logger-readiness-dir", type=Path, default=DEFAULT_READINESS_DIR)
    parser.add_argument("--feature-source-db", type=Path, default=DEFAULT_FEATURE_SOURCE_DB)
    parser.add_argument("--feature-source-table", default=DEFAULT_FEATURE_SOURCE_TABLE)
    parser.add_argument("--candidate-id", default=DEFAULT_CANDIDATE_ID)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--regime-column", default=DEFAULT_REGIME_COLUMN)
    parser.add_argument("--regime-value", default=DEFAULT_REGIME_VALUE)
    parser.add_argument("--features", nargs="+", default=list(DEFAULT_FEATURES))
    parser.add_argument("--min-non-null-count", type=int, default=DEFAULT_MIN_NON_NULL_COUNT)
    parser.add_argument("--quantile-method", choices=("linear",), default=DEFAULT_QUANTILE_METHOD)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, sqlite3.Error, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate numeric-tercile threshold build failed: {exc}")
        return 1
    print("Fixed-candidate numeric-tercile thresholds complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
