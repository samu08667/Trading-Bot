"""Run one local fixed-candidate paper signal logger evaluation.

This script is intentionally single-shot and local-only. It reads completed
paper/demo artifacts, frozen numeric-tercile thresholds, and one latest row from
an allowlisted local feature table. It writes paper log artifacts only. It does
not loop, schedule itself, connect to MT5, connect to broker/API services,
execute orders, simulate broker execution, mutate the project database,
generate market data, run backtests, run validation, or make candidate-quality
or trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_paper_signal_logger"
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR
    / "config"
    / "paper_demo"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)
DEFAULT_DEMO_STRATEGY_SPEC_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_strategy_spec"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v4"
)
DEFAULT_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger_readiness"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_readiness_v3"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_FEATURE_SOURCE_DB = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_FEATURE_SOURCE_TABLE = "price_features"
DEFAULT_STATE_JSON = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_v1"
    / "fixed_candidate_paper_signal_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_paper_signal_logger"

SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_REPORT = "fixed_candidate_demo_strategy_spec_report.md"
SPEC_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"
SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"

READINESS_CSV = "fixed_candidate_paper_signal_logger_readiness.csv"
READINESS_REPORT = "fixed_candidate_paper_signal_logger_readiness_report.md"
READINESS_WARNINGS = "fixed_candidate_paper_signal_logger_readiness_warnings.csv"
READINESS_MANIFEST = "fixed_candidate_paper_signal_logger_readiness_manifest.json"

OUTPUT_SIGNAL_LOG = "fixed_candidate_paper_signal_log.csv"
OUTPUT_EVENTS = "fixed_candidate_paper_signal_events.jsonl"
OUTPUT_STATE = "fixed_candidate_paper_signal_state.json"
OUTPUT_STATE_HISTORY = "fixed_candidate_paper_signal_state_history.csv"
OUTPUT_REPORT = "fixed_candidate_paper_signal_logger_report.md"
OUTPUT_WARNINGS = "fixed_candidate_paper_signal_logger_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_paper_signal_logger_manifest.json"

ALLOWLISTED_FEATURE_TABLES = {"price_features", "market_features"}
BLOCKED_FEATURE_TABLES = {"ml_dataset"}
CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"

REQUIRED_ROW_COLUMNS = (
    "time_server",
    "open",
    "high",
    "low",
    "close",
    "atr_20",
    "hour_session",
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
    "spread",
    "spread_avg_20",
)
OPTIONAL_ROW_COLUMNS = ("symbol", "timeframe", "tick_volume", "volume")
REQUIRED_THRESHOLD_FEATURES = {
    "close_to_ma_fast_atr_20": "high_tercile",
    "tick_volume_percentile_100": "mid_tercile",
}

SIGNAL_FIELDNAMES = [
    "run_id",
    "signal_id",
    "evaluated_at",
    "time_server",
    "symbol",
    "timeframe",
    "direction",
    "signal_state",
    "skip_reasons",
    "regime_column",
    "regime_value_observed",
    "spread",
    "max_spread_points",
    "close_to_ma_fast_atr_20",
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100",
    "tick_volume_percentile_100_bucket",
    "atr_20",
    "entry_reference_price",
    "tp_price",
    "sl_price",
    "horizon_bars",
    "same_bar_policy",
    "state_before",
    "state_after",
    "source_db",
    "source_table",
    "threshold_artifact",
    "no_order_execution",
]

STATE_HISTORY_FIELDNAMES = [
    "run_id",
    "signal_id",
    "evaluated_at",
    "event",
    "state_before",
    "state_after",
    "source_state_json",
    "output_state_json",
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


def labels(*values: str) -> str:
    return ";".join(value for value in values if value)


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
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


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str], *, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    mode = "a" if append else "w"
    with path.open(mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if not append or not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "signal_log": output_dir / OUTPUT_SIGNAL_LOG,
        "events": output_dir / OUTPUT_EVENTS,
        "state": output_dir / OUTPUT_STATE,
        "state_history": output_dir / OUTPUT_STATE_HISTORY,
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


def event(events: list[dict[str, Any]], name: str, **details: Any) -> None:
    events.append({"event_name": name, "event_at": utc_now_text(), **details})


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


def load_bundle(root: Path, csv_name: str, manifest_name: str, report_name: str, warnings_name: str) -> dict[str, Any]:
    csv_path = root / csv_name
    manifest_path = root / manifest_name
    report_path = root / report_name
    warnings_path = root / warnings_name
    rows, csv_error = read_csv_rows(csv_path)
    manifest, manifest_error = read_json(manifest_path)
    warning_rows, warnings_error = read_csv_rows(warnings_path)
    report = read_text(report_path)
    files_present = csv_path.exists() and manifest_path.exists() and report_path.exists()
    return {
        "dir": root,
        "csv_path": csv_path,
        "manifest_path": manifest_path,
        "report_path": report_path,
        "warnings_path": warnings_path,
        "rows": rows,
        "manifest": manifest,
        "warnings": warning_rows,
        "report": report,
        "files_present": files_present,
        "error": labels(csv_error, manifest_error, warnings_error),
        "loaded": files_present and not (csv_error or manifest_error or warnings_error),
    }


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def load_inputs(args: argparse.Namespace) -> dict[str, Any]:
    canonical_registry, canonical_registry_error = read_json(Path(args.canonical_registry))
    config, config_error = read_json(Path(args.demo_strategy_config))
    spec = load_bundle(
        Path(args.demo_strategy_spec_dir),
        SPEC_CSV,
        SPEC_MANIFEST,
        SPEC_REPORT,
        SPEC_WARNINGS,
    )
    readiness = load_bundle(
        Path(args.paper_signal_logger_readiness_dir),
        READINESS_CSV,
        READINESS_MANIFEST,
        READINESS_REPORT,
        READINESS_WARNINGS,
    )
    thresholds, thresholds_error = read_json(Path(args.tercile_thresholds_json))
    state, state_error = read_json(Path(args.state_json))
    return {
        "canonical_registry": canonical_registry,
        "canonical_registry_error": canonical_registry_error,
        "canonical_registry_exists": Path(args.canonical_registry).exists(),
        "config": config,
        "config_error": config_error,
        "config_exists": Path(args.demo_strategy_config).exists(),
        "spec": spec,
        "readiness": readiness,
        "thresholds": thresholds,
        "thresholds_error": thresholds_error,
        "thresholds_exists": Path(args.tercile_thresholds_json).exists(),
        "state": state,
        "state_error": state_error,
        "state_exists": Path(args.state_json).exists(),
    }


def validate_inputs(args: argparse.Namespace, inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    config = inputs["config"]
    spec_manifest = inputs["spec"]["manifest"]
    readiness_manifest = inputs["readiness"]["manifest"]
    thresholds = inputs["thresholds"]
    config_boundary = bool(
        inputs["config_exists"]
        and not inputs["config_error"]
        and config.get("paper_only") is True
        and config.get("broker_connection_allowed") is False
        and config.get("order_execution_allowed") is False
        and config.get("real_money_allowed") is False
    )
    spec_boundary = bool(inputs["spec"]["loaded"] and spec_manifest.get("paper_only_specification") is True)
    readiness_boundary = bool(inputs["readiness"]["loaded"] and readiness_manifest.get("paper_only_boundary_confirmed") is True)
    readiness_clear = bool(
        inputs["readiness"]["loaded"]
        and int(readiness_manifest.get("blocked_missing_threshold_artifact_count") or 0) == 0
        and int(readiness_manifest.get("blocked_missing_required_column_count") or 0) == 0
        and int(readiness_manifest.get("blocked_by_config_count") or 0) == 0
        and int(readiness_manifest.get("blocked_by_leakage_risk_count") or 0) == 0
        and int(readiness_manifest.get("blocking_warnings_count") or 0) == 0
    )
    threshold_valid = validate_threshold_artifact(thresholds, allow_legacy=bool(args.allow_legacy_full_sample_thresholds))
    table_name = str(args.feature_source_table)
    table_allowlisted = table_name in ALLOWLISTED_FEATURE_TABLES
    table_blocked = table_name in BLOCKED_FEATURE_TABLES
    max_spread_points = safe_float(
        nested_get(config, "spread_and_session_controls", "max_spread_points")
    )
    validation = {
        "config_boundary": config_boundary,
        "spec_boundary": spec_boundary,
        "readiness_boundary": readiness_boundary,
        "readiness_clear": readiness_clear,
        "threshold_valid": threshold_valid,
        "table_allowlisted": table_allowlisted,
        "table_blocked": table_blocked,
        "max_spread_points": max_spread_points,
        "paper_only_boundary_confirmed": config_boundary and spec_boundary and readiness_boundary,
    }
    if not inputs["config_exists"]:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_config_missing",
            message="Demo strategy config is missing.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    elif inputs["config_error"]:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_config_unreadable",
            message=f"Demo strategy config is unreadable: {inputs['config_error']}",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    elif not config_boundary:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_only_boundary_not_confirmed",
            message="Demo strategy config does not preserve the required paper-only boundary.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    if not inputs["spec"]["loaded"]:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_spec_unreadable_or_missing",
            message="Demo strategy spec artifacts are missing or unreadable.",
            source=args.demo_strategy_spec_dir,
            blocking_warning=True,
        )
    elif not spec_boundary:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_spec_boundary_not_confirmed",
            message="Demo strategy spec does not confirm paper_only_specification.",
            source=args.demo_strategy_spec_dir,
            blocking_warning=True,
        )
    if not inputs["readiness"]["loaded"]:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_signal_logger_readiness_unreadable_or_missing",
            message="Paper signal logger readiness artifacts are missing or unreadable.",
            source=args.paper_signal_logger_readiness_dir,
            blocking_warning=True,
        )
    elif not (readiness_boundary and readiness_clear):
        add_warning(
            warnings,
            args=args,
            warning_code="paper_signal_logger_readiness_blocker_present",
            message="Paper signal logger readiness has blockers or does not confirm paper-only boundary.",
            source=args.paper_signal_logger_readiness_dir,
            blocking_warning=True,
        )
    if not inputs["thresholds_exists"]:
        add_warning(
            warnings,
            args=args,
            warning_code="threshold_artifact_missing",
            message="Frozen numeric-tercile threshold artifact is missing.",
            source=args.tercile_thresholds_json,
            blocking_warning=True,
        )
    elif inputs["thresholds_error"]:
        add_warning(
            warnings,
            args=args,
            warning_code="threshold_artifact_unreadable",
            message=f"Frozen numeric-tercile threshold artifact is unreadable: {inputs['thresholds_error']}",
            source=args.tercile_thresholds_json,
            blocking_warning=True,
        )
    elif not threshold_valid:
        add_warning(
            warnings,
            args=args,
            warning_code="threshold_artifact_unreadable",
            message="Current paper logger paths require train-only numeric-tercile thresholds; legacy full-sample thresholds require --allow-legacy-full-sample-thresholds.",
            source=args.tercile_thresholds_json,
            blocking_warning=True,
        )
    if table_blocked:
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_table_leakage_risk",
            message="ml_dataset is blocked as a paper signal input.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    elif not table_allowlisted:
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_table_not_allowlisted",
            message="Feature source table is not allowlisted.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    if max_spread_points is None:
        add_warning(
            warnings,
            args=args,
            warning_code="spread_missing_or_unreadable",
            message="max_spread_points is missing or unreadable in the demo strategy config.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    if inputs["state_exists"] and inputs["state_error"]:
        add_warning(
            warnings,
            args=args,
            warning_code="state_json_unreadable",
            message=f"State JSON is unreadable: {inputs['state_error']}",
            source=args.state_json,
            blocking_warning=True,
        )
    return validation


def threshold_schema_label(thresholds: dict[str, Any]) -> str:
    features = thresholds.get("features")
    if not isinstance(features, dict):
        return "unknown"
    train_only = True
    legacy = True
    for feature in REQUIRED_THRESHOLD_FEATURES:
        payload = features.get(feature)
        if not isinstance(payload, dict):
            return "unknown"
        train_only = train_only and safe_float(payload.get("low_mid_cutoff")) is not None and safe_float(payload.get("mid_high_cutoff")) is not None
        legacy = legacy and safe_float(payload.get("lower_tercile_boundary")) is not None and safe_float(payload.get("upper_tercile_boundary")) is not None
    if train_only:
        return "train_only_low_mid_mid_high"
    if legacy:
        return "legacy_full_sample_lower_upper"
    return "unknown"


def validate_threshold_artifact(thresholds: dict[str, Any], *, allow_legacy: bool = False) -> bool:
    if not thresholds or thresholds.get("schema_version") is None or thresholds.get("candidate_id") != CANDIDATE_ID:
        return False
    schema_label = threshold_schema_label(thresholds)
    if schema_label == "train_only_low_mid_mid_high":
        return (
            thresholds.get("threshold_lineage") == "train_only"
            and thresholds.get("calibration_scope") == "train_window_only"
            and thresholds.get("full_sample_thresholds_used") is False
            and thresholds.get("oos_rows_used_for_thresholds") is False
        )
    if schema_label == "legacy_full_sample_lower_upper":
        return allow_legacy
    return False


def threshold_metadata(thresholds: dict[str, Any], *, allow_legacy: bool) -> dict[str, Any]:
    schema_label = threshold_schema_label(thresholds)
    return {
        "threshold_lineage": thresholds.get("threshold_lineage", "legacy_full_sample" if schema_label == "legacy_full_sample_lower_upper" else ""),
        "calibration_scope": thresholds.get("calibration_scope", ""),
        "full_sample_thresholds_used": thresholds.get("full_sample_thresholds_used", True if schema_label == "legacy_full_sample_lower_upper" else None),
        "oos_rows_used_for_thresholds": thresholds.get("oos_rows_used_for_thresholds", None),
        "threshold_schema_label": schema_label,
        "legacy_full_sample_thresholds_allowed": bool(allow_legacy),
    }


def threshold_cutoffs(thresholds: dict[str, Any], feature: str) -> tuple[float, float]:
    payload = thresholds.get("features", {}).get(feature, {})
    if threshold_schema_label(thresholds) == "train_only_low_mid_mid_high":
        return float(payload.get("low_mid_cutoff")), float(payload.get("mid_high_cutoff"))
    return float(payload.get("lower_tercile_boundary")), float(payload.get("upper_tercile_boundary"))


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


def fetch_latest_row(args: argparse.Namespace, columns: set[str]) -> dict[str, Any] | None:
    selected_columns = [column for column in [*REQUIRED_ROW_COLUMNS, *OPTIONAL_ROW_COLUMNS] if column in columns]
    filters: list[str] = []
    params: list[Any] = []
    if "symbol" in columns:
        filters.append(f"{quote_identifier('symbol')} = ?")
        params.append(nested_get(load_config_only(Path(args.demo_strategy_config)), "candidate", "symbol") or "GBPUSD")
    if "timeframe" in columns:
        filters.append(f"{quote_identifier('timeframe')} = ?")
        params.append(nested_get(load_config_only(Path(args.demo_strategy_config)), "candidate", "timeframe") or "M15")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = (
        f"SELECT {', '.join(quote_identifier(column) for column in selected_columns)} "
        f"FROM {quote_identifier(str(args.feature_source_table))} {where} "
        f"ORDER BY {quote_identifier('time_server')} DESC LIMIT 1"
    )
    uri = f"file:{Path(args.feature_source_db).resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    if row is None:
        return None
    return {column: row[column] for column in selected_columns}


def load_config_only(path: Path) -> dict[str, Any]:
    config, _error = read_json(path)
    return config


def empty_state() -> dict[str, Any]:
    return {
        "has_open_paper_trade": False,
        "open_signal_id": "",
        "entry_time_server": "",
        "entry_price": None,
        "tp_price": None,
        "sl_price": None,
        "bars_elapsed": 0,
        "horizon_bars": 10,
        "last_seen_time_server": "",
        "state_updated_at": "",
    }


def current_state(inputs: dict[str, Any]) -> dict[str, Any]:
    if inputs["state_exists"] and inputs["state"] and not inputs["state_error"]:
        state = empty_state()
        state.update(inputs["state"])
        return state
    return empty_state()


def bucket_for_value(value: float | None, lower: float, upper: float) -> str:
    if value is None:
        return "unreadable"
    if value <= lower:
        return "low_tercile"
    if value <= upper:
        return "mid_tercile"
    return "high_tercile"


def evaluate_row(
    *,
    args: argparse.Namespace,
    inputs: dict[str, Any],
    validation: dict[str, Any],
    latest_row: dict[str, Any] | None,
    state_before: dict[str, Any],
    warnings: list[dict[str, Any]],
    signal_id: str,
    evaluated_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = inputs["config"]
    thresholds = inputs["thresholds"]
    skip_reasons: list[str] = []
    signal_state = "paper_signal_skipped"
    if latest_row is None:
        skip_reasons.append("required_data_missing")
    else:
        add_warning(
            warnings,
            args=args,
            warning_code="latest_closed_bar_assumed_from_persisted_feature_table",
            message="Closed-bar status is assumed from the persisted local feature table.",
            source=args.feature_source_table,
            blocking_warning=False,
        )
    if state_before.get("has_open_paper_trade") is True:
        skip_reasons.append("existing_paper_demo_trade_open")
        add_warning(
            warnings,
            args=args,
            warning_code="existing_paper_demo_trade_open",
            message="Existing paper state has an open paper trade; no new paper signal is opened.",
            source=args.state_json,
            blocking_warning=False,
        )

    regime_column = str(nested_get(config, "entry_rule", "regime_column") or "hour_session")
    regime_value = str(nested_get(config, "entry_rule", "regime_value") or "Off_hours")
    direction = str(nested_get(config, "candidate", "direction") or "short")
    symbol = str(nested_get(config, "candidate", "symbol") or latest_row.get("symbol", "GBPUSD") if latest_row else "GBPUSD")
    timeframe = str(nested_get(config, "candidate", "timeframe") or latest_row.get("timeframe", "M15") if latest_row else "M15")
    horizon_bars = int(nested_get(config, "candidate", "target_horizon") or 10)
    tp_atr = safe_float(nested_get(config, "risk_reward", "tp_atr")) or 1.5
    sl_atr = safe_float(nested_get(config, "risk_reward", "sl_atr")) or 1.0
    same_bar_policy = str(nested_get(config, "risk_reward", "same_bar_policy") or "stop_first")
    max_spread_points = validation["max_spread_points"]
    close_value = safe_float(latest_row.get("close")) if latest_row else None
    atr_value = safe_float(latest_row.get("atr_20")) if latest_row else None
    spread_value = safe_float(latest_row.get("spread")) if latest_row else None
    feature_a = safe_float(latest_row.get("close_to_ma_fast_atr_20")) if latest_row else None
    feature_b = safe_float(latest_row.get("tick_volume_percentile_100")) if latest_row else None
    observed_regime = str(latest_row.get(regime_column) or "") if latest_row else ""
    observed_timeframe = str(latest_row.get("timeframe") or timeframe) if latest_row else timeframe

    if latest_row:
        if observed_timeframe != timeframe:
            skip_reasons.append("timeframe_mismatch")
            add_warning(
                warnings,
                args=args,
                warning_code="timeframe_mismatch",
                message="Latest row timeframe does not match config timeframe.",
                source=args.feature_source_table,
                blocking_warning=False,
            )
        if observed_regime != regime_value:
            skip_reasons.append("session_mismatch")
            add_warning(
                warnings,
                args=args,
                warning_code="session_mismatch",
                message="Latest row regime/session does not match configured regime.",
                source=args.feature_source_table,
                blocking_warning=False,
            )
        if atr_value is None:
            skip_reasons.append("atr_calculation_failed")
        if feature_a is None or feature_b is None:
            skip_reasons.append("required_features_missing")
            add_warning(
                warnings,
                args=args,
                warning_code="required_feature_missing",
                message="One or more required feature values are missing or unreadable.",
                source=args.feature_source_table,
                blocking_warning=False,
            )
        if spread_value is None:
            skip_reasons.append("spread_missing_or_unreadable")
            add_warning(
                warnings,
                args=args,
                warning_code="spread_missing_or_unreadable",
                message="Spread is missing or unreadable; new paper signal is skipped.",
                source=args.feature_source_table,
                blocking_warning=False,
            )
        elif max_spread_points is not None and spread_value > max_spread_points:
            skip_reasons.append("spread_above_threshold")
            add_warning(
                warnings,
                args=args,
                warning_code="spread_above_threshold",
                message="Spread is above max_spread_points; new paper signal is skipped.",
                source=args.feature_source_table,
                blocking_warning=False,
            )

    threshold_a_lower, threshold_a_upper = threshold_cutoffs(thresholds, "close_to_ma_fast_atr_20")
    threshold_b_lower, threshold_b_upper = threshold_cutoffs(thresholds, "tick_volume_percentile_100")
    bucket_a = bucket_for_value(
        feature_a,
        threshold_a_lower,
        threshold_a_upper,
    )
    bucket_b = bucket_for_value(
        feature_b,
        threshold_b_lower,
        threshold_b_upper,
    )
    if latest_row and bucket_a != "high_tercile":
        skip_reasons.append("close_to_ma_fast_atr_20_bucket_mismatch")
    if latest_row and bucket_b != "mid_tercile":
        skip_reasons.append("tick_volume_percentile_100_bucket_mismatch")

    state_after = dict(state_before)
    entry_reference_price = ""
    tp_price = ""
    sl_price = ""
    if not skip_reasons and close_value is not None and atr_value is not None and max_spread_points is not None:
        signal_state = "paper_signal_opened"
        entry_reference_price = close_value
        if direction == "short":
            tp_price = close_value - tp_atr * atr_value
            sl_price = close_value + sl_atr * atr_value
        else:
            tp_price = close_value + tp_atr * atr_value
            sl_price = close_value - sl_atr * atr_value
        state_after = {
            "has_open_paper_trade": True,
            "open_signal_id": signal_id,
            "entry_time_server": latest_row.get("time_server", ""),
            "entry_price": entry_reference_price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "bars_elapsed": 0,
            "horizon_bars": horizon_bars,
            "last_seen_time_server": latest_row.get("time_server", ""),
            "state_updated_at": evaluated_at,
        }
    elif state_before.get("has_open_paper_trade") is True:
        state_after["last_seen_time_server"] = latest_row.get("time_server", state_before.get("last_seen_time_server", "")) if latest_row else state_before.get("last_seen_time_server", "")
        state_after["state_updated_at"] = evaluated_at
    else:
        state_after = empty_state()
        state_after["last_seen_time_server"] = latest_row.get("time_server", "") if latest_row else ""
        state_after["state_updated_at"] = evaluated_at

    signal_row = {
        "run_id": args.run_id,
        "signal_id": signal_id,
        "evaluated_at": evaluated_at,
        "time_server": latest_row.get("time_server", "") if latest_row else "",
        "symbol": latest_row.get("symbol", symbol) if latest_row else symbol,
        "timeframe": observed_timeframe,
        "direction": direction,
        "signal_state": signal_state,
        "skip_reasons": ";".join(dict.fromkeys(skip_reasons)),
        "regime_column": regime_column,
        "regime_value_observed": observed_regime,
        "spread": spread_value,
        "max_spread_points": max_spread_points,
        "close_to_ma_fast_atr_20": feature_a,
        "close_to_ma_fast_atr_20_bucket": bucket_a,
        "tick_volume_percentile_100": feature_b,
        "tick_volume_percentile_100_bucket": bucket_b,
        "atr_20": atr_value,
        "entry_reference_price": entry_reference_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "horizon_bars": horizon_bars,
        "same_bar_policy": same_bar_policy,
        "state_before": state_before,
        "state_after": state_after,
        "source_db": args.feature_source_db,
        "source_table": args.feature_source_table,
        "threshold_artifact": args.tercile_thresholds_json,
        "no_order_execution": True,
        "paper_only_boundary_confirmed": validation["paper_only_boundary_confirmed"],
    }
    return signal_row, state_after


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [warning for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"]


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    evaluated_at = utc_now_text()
    signal_id = f"{args.run_id}_{evaluated_at.replace(':', '').replace('-', '').replace('.', '')}"
    event(events, "run_started", run_id=args.run_id)
    inputs = load_inputs(args)
    validation = validate_inputs(args, inputs, warnings)
    event(events, "input_validated", blocking_warnings=len(blocking_warnings(warnings)))

    schema = inspect_schema(Path(args.feature_source_db), str(args.feature_source_table))
    latest_row: dict[str, Any] | None = None
    if schema["error"]:
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_db_unreadable",
            message=f"Feature source DB schema could not be inspected: {schema['error']}",
            source=args.feature_source_db,
            blocking_warning=True,
        )
    elif not schema["db_exists"]:
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_db_missing",
            message="Feature source DB is missing.",
            source=args.feature_source_db,
            blocking_warning=True,
        )
    elif not schema["table_exists"]:
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_table_missing",
            message="Feature source table is missing.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    else:
        missing = [column for column in REQUIRED_ROW_COLUMNS if column not in schema["columns"]]
        if missing:
            add_warning(
                warnings,
                args=args,
                warning_code="required_feature_missing",
                message=f"Feature source table is missing required columns: {', '.join(missing)}",
                source=args.feature_source_table,
                blocking_warning=True,
            )
        elif not blocking_warnings(warnings):
            latest_row = fetch_latest_row(args, set(schema["columns"]))
            if latest_row is None:
                add_warning(
                    warnings,
                    args=args,
                    warning_code="required_feature_missing",
                    message="No latest row was available for the configured local paper scope.",
                    source=args.feature_source_table,
                    blocking_warning=True,
                )
    event(events, "latest_row_loaded", available=latest_row is not None)

    state_before = current_state(inputs)
    if blocking_warnings(warnings):
        state_after = dict(state_before)
        signal_row = {
            "run_id": args.run_id,
            "signal_id": signal_id,
            "evaluated_at": evaluated_at,
            "time_server": latest_row.get("time_server", "") if latest_row else "",
            "symbol": nested_get(inputs["config"], "candidate", "symbol") or "GBPUSD",
            "timeframe": nested_get(inputs["config"], "candidate", "timeframe") or "M15",
            "direction": nested_get(inputs["config"], "candidate", "direction") or "short",
            "signal_state": "paper_signal_blocked",
            "skip_reasons": ";".join(warning["warning_code"] for warning in blocking_warnings(warnings)),
            "regime_column": nested_get(inputs["config"], "entry_rule", "regime_column") or "hour_session",
            "regime_value_observed": latest_row.get("hour_session", "") if latest_row else "",
            "spread": latest_row.get("spread", "") if latest_row else "",
            "max_spread_points": validation.get("max_spread_points"),
            "close_to_ma_fast_atr_20": latest_row.get("close_to_ma_fast_atr_20", "") if latest_row else "",
            "close_to_ma_fast_atr_20_bucket": "",
            "tick_volume_percentile_100": latest_row.get("tick_volume_percentile_100", "") if latest_row else "",
            "tick_volume_percentile_100_bucket": "",
            "atr_20": latest_row.get("atr_20", "") if latest_row else "",
            "entry_reference_price": "",
            "tp_price": "",
            "sl_price": "",
            "horizon_bars": nested_get(inputs["config"], "candidate", "target_horizon") or 10,
            "same_bar_policy": nested_get(inputs["config"], "risk_reward", "same_bar_policy") or "stop_first",
            "state_before": state_before,
            "state_after": state_after,
            "source_db": args.feature_source_db,
            "source_table": args.feature_source_table,
            "threshold_artifact": args.tercile_thresholds_json,
            "no_order_execution": True,
            "paper_only_boundary_confirmed": validation["paper_only_boundary_confirmed"],
        }
    else:
        signal_row, state_after = evaluate_row(
            args=args,
            inputs=inputs,
            validation=validation,
            latest_row=latest_row,
            state_before=state_before,
            warnings=warnings,
            signal_id=signal_id,
            evaluated_at=evaluated_at,
        )
    event(events, "gates_evaluated", signal_state=signal_row["signal_state"], skip_reasons=signal_row["skip_reasons"])
    event_name = "signal_logged" if signal_row["signal_state"] == "paper_signal_opened" else "signal_skipped"
    event(events, event_name, signal_state=signal_row["signal_state"])
    output_paths["state"].write_text(json.dumps(state_after, indent=2, sort_keys=True), encoding="utf-8")
    event(events, "state_written", state_json=str(output_paths["state"]))
    event(events, "run_completed", signal_state=signal_row["signal_state"])

    state_history = [
        {
            "run_id": args.run_id,
            "signal_id": signal_id,
            "evaluated_at": evaluated_at,
            "event": "state_written",
            "state_before": state_before,
            "state_after": state_after,
            "source_state_json": args.state_json,
            "output_state_json": output_paths["state"],
        }
    ]
    write_csv(output_paths["signal_log"], [signal_row], SIGNAL_FIELDNAMES)
    write_csv(output_paths["state_history"], state_history, STATE_HISTORY_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_jsonl(output_paths["events"], events)
    write_report(
        output_paths["report"],
        args=args,
        signal_row=signal_row,
        warnings=warnings,
        state_before=state_before,
        state_after=state_after,
        latest_row=latest_row,
        thresholds=inputs["thresholds"],
    )
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        signal_row=signal_row,
        warnings=warnings,
        state_after=state_after,
        thresholds=inputs["thresholds"],
    )
    return {"signal_row": signal_row, "warnings": warnings, "events": events, "state_after": state_after}


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    signal_row: dict[str, Any],
    warnings: list[dict[str, Any]],
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    latest_row: dict[str, Any] | None,
    thresholds: dict[str, Any],
) -> None:
    metadata = threshold_metadata(thresholds, allow_legacy=bool(args.allow_legacy_full_sample_thresholds))
    lines = [
        "# Fixed Candidate Paper Signal Logger",
        "",
        "Single-shot local paper logger artifact. This run does not loop, schedule itself, or stay resident.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation was performed.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- demo_strategy_spec_dir: `{args.demo_strategy_spec_dir}`",
        f"- paper_signal_logger_readiness_dir: `{args.paper_signal_logger_readiness_dir}`",
        f"- tercile_thresholds_json: `{args.tercile_thresholds_json}`",
        f"- threshold_lineage: `{metadata['threshold_lineage']}`",
        f"- calibration_scope: `{metadata['calibration_scope']}`",
        f"- threshold_schema_label: `{metadata['threshold_schema_label']}`",
        f"- legacy_full_sample_thresholds_allowed: `{bool_text(bool(metadata['legacy_full_sample_thresholds_allowed']))}`",
        f"- feature_source_db: `{args.feature_source_db}`",
        f"- feature_source_table: `{args.feature_source_table}`",
        "",
        "## Latest Row Overview",
        "",
        f"- time_server: `{signal_row.get('time_server', '')}`",
        f"- spread: `{signal_row.get('spread', '')}`",
        f"- atr_20: `{signal_row.get('atr_20', '')}`",
        "",
        "## Gate Evaluation Summary",
        "",
        f"- regime_value_observed: `{signal_row.get('regime_value_observed', '')}`",
        f"- close_to_ma_fast_atr_20_bucket: `{signal_row.get('close_to_ma_fast_atr_20_bucket', '')}`",
        f"- tick_volume_percentile_100_bucket: `{signal_row.get('tick_volume_percentile_100_bucket', '')}`",
        f"- max_spread_points: `{signal_row.get('max_spread_points', '')}`",
        "",
        "## Signal Result",
        "",
        f"- signal_state: `{signal_row['signal_state']}`",
        f"- skip_reasons: `{signal_row.get('skip_reasons', '')}`",
        f"- tp_price: `{signal_row.get('tp_price', '')}`",
        f"- sl_price: `{signal_row.get('sl_price', '')}`",
        "",
        "## State Summary",
        "",
        f"- state_before_has_open_paper_trade: `{bool_text(bool(state_before.get('has_open_paper_trade')))}`",
        f"- state_after_has_open_paper_trade: `{bool_text(bool(state_after.get('has_open_paper_trade')))}`",
        f"- open_signal_id: `{state_after.get('open_signal_id', '')}`",
        "",
        "## Warnings Summary",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        "",
        "## Next Step",
        "",
        "Rerun the logger manually on future updated local data, or create a separate command plan for repeated manual paper logging later.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    signal_row: dict[str, Any],
    warnings: list[dict[str, Any]],
    state_after: dict[str, Any],
    thresholds: dict[str, Any],
) -> None:
    metadata = threshold_metadata(thresholds, allow_legacy=bool(args.allow_legacy_full_sample_thresholds))
    signal_opened = signal_row["signal_state"] == "paper_signal_opened"
    signal_skipped = signal_row["signal_state"] in {"paper_signal_skipped", "paper_signal_blocked"}
    manifest = {
        "run_id": args.run_id,
        "generated_at": signal_row["evaluated_at"],
        "output_dir": str(output_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "paper_signal_logger_readiness_dir": str(args.paper_signal_logger_readiness_dir),
        "tercile_thresholds_json": str(args.tercile_thresholds_json),
        "numeric_tercile_thresholds_json": str(args.tercile_thresholds_json),
        "canonical_registry": str(args.canonical_registry),
        **metadata,
        "feature_source_db": str(args.feature_source_db),
        "feature_source_table": str(args.feature_source_table),
        "state_json": str(args.state_json),
        "evaluated_row_time_server": signal_row.get("time_server", ""),
        "signal_state": signal_row["signal_state"],
        "signal_opened_count": 1 if signal_opened else 0,
        "signal_skipped_count": 1 if signal_skipped else 0,
        "warning_count": len(warnings),
        "warnings_count": len(warnings),
        "blocking_warning_count": len(blocking_warnings(warnings)),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "paper_only_boundary_confirmed": bool(signal_row.get("paper_only_boundary_confirmed")),
        "has_open_paper_trade_after": bool(state_after.get("has_open_paper_trade")),
        "no_child_scripts_executed": True,
        "no_paper_runner_loop_executed": True,
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
    normalize_threshold_args(args)
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    build_artifacts(args, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one local fixed-candidate paper signal logger evaluation."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--paper-signal-logger-readiness-dir", type=Path, default=DEFAULT_READINESS_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--tercile-thresholds-json", type=Path)
    parser.add_argument("--allow-legacy-full-sample-thresholds", action="store_true")
    parser.add_argument("--feature-source-db", type=Path, default=DEFAULT_FEATURE_SOURCE_DB)
    parser.add_argument("--feature-source-table", default=DEFAULT_FEATURE_SOURCE_TABLE)
    parser.add_argument("--state-json", type=Path, default=DEFAULT_STATE_JSON)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, sqlite3.Error, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate paper signal logger failed: {exc}")
        return 1
    print("Fixed-candidate paper signal logger single-shot run complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
