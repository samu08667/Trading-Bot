"""Run a fixed-rule local replay backtest for the GBPUSD paper/demo logic.

This script replays the already-finalized fixed paper/demo rule over local
historical feature rows. It is not optimization, parameter search, candidate
search, broker/demo/live execution, or a final trading decision. It reads only
required columns from an allowlisted local SQLite feature table in read-only
mode and writes local replay artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_fixed_rule_replay_backtest"
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
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v5_spread15"
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
DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_MAX_BARS = 50000
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_fixed_rule_replay_backtest"
CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
REQUIRED_THRESHOLD_FEATURES = (
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
)

SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_REPORT = "fixed_candidate_demo_strategy_spec_report.md"
SPEC_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"
SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"

READINESS_CSV = "fixed_candidate_paper_signal_logger_readiness.csv"
READINESS_REPORT = "fixed_candidate_paper_signal_logger_readiness_report.md"
READINESS_WARNINGS = "fixed_candidate_paper_signal_logger_readiness_warnings.csv"
READINESS_MANIFEST = "fixed_candidate_paper_signal_logger_readiness_manifest.json"

OUTPUT_BARS = "fixed_candidate_fixed_rule_replay_backtest_bars.csv"
OUTPUT_SIGNALS = "fixed_candidate_fixed_rule_replay_backtest_signals.csv"
OUTPUT_TRADES = "fixed_candidate_fixed_rule_replay_backtest_trades.csv"
OUTPUT_EQUITY = "fixed_candidate_fixed_rule_replay_backtest_equity.csv"
OUTPUT_REPORT = "fixed_candidate_fixed_rule_replay_backtest_report.md"
OUTPUT_WARNINGS = "fixed_candidate_fixed_rule_replay_backtest_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_fixed_rule_replay_backtest_manifest.json"

ALLOWLISTED_FEATURE_TABLES = {"price_features", "market_features"}
BLOCKED_FEATURE_TABLES = {"ml_dataset"}
REQUIRED_SOURCE_COLUMNS = (
    "symbol",
    "timeframe",
    "time_server",
    "open",
    "high",
    "low",
    "close",
    "spread",
    "spread_avg_20",
    "atr_20",
    "hour_session",
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
)

BARS_FIELDNAMES = [
    "run_id",
    "time_server",
    "symbol",
    "timeframe",
    "state_before",
    "state_after",
    "signal_state",
    "trade_status",
    "skip_reasons",
    "open",
    "high",
    "low",
    "close",
    "spread",
    "max_spread_points",
    "hour_session",
    "close_to_ma_fast_atr_20",
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100",
    "tick_volume_percentile_100_bucket",
    "atr_20",
    "open_signal_id",
    "bars_elapsed",
    "event_label",
]

SIGNALS_FIELDNAMES = [
    "run_id",
    "signal_id",
    "time_server",
    "symbol",
    "timeframe",
    "direction",
    "signal_state",
    "skip_reasons",
    "entry_reference_price",
    "tp_price",
    "sl_price",
    "atr_20",
    "spread",
    "max_spread_points",
    "hour_session",
    "close_to_ma_fast_atr_20",
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100",
    "tick_volume_percentile_100_bucket",
]

TRADES_FIELDNAMES = [
    "run_id",
    "open_signal_id",
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
]

EQUITY_FIELDNAMES = [
    "run_id",
    "trade_index",
    "open_signal_id",
    "exit_time_server",
    "exit_reason",
    "R_multiple",
    "cumulative_R",
    "peak_cumulative_R",
    "drawdown_R",
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


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "bars": output_dir / OUTPUT_BARS,
        "signals": output_dir / OUTPUT_SIGNALS,
        "trades": output_dir / OUTPUT_TRADES,
        "equity": output_dir / OUTPUT_EQUITY,
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
    spec = load_bundle(Path(args.demo_strategy_spec_dir), SPEC_CSV, SPEC_MANIFEST, SPEC_REPORT, SPEC_WARNINGS)
    readiness = load_bundle(
        Path(args.paper_signal_logger_readiness_dir),
        READINESS_CSV,
        READINESS_MANIFEST,
        READINESS_REPORT,
        READINESS_WARNINGS,
    )
    thresholds, thresholds_error = read_json(Path(args.tercile_thresholds_json))
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
    }


def validate_inputs(args: argparse.Namespace, inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    config = inputs["config"]
    readiness_manifest = inputs["readiness"]["manifest"]
    config_ok = bool(
        inputs["config_exists"]
        and not inputs["config_error"]
        and config.get("paper_only") is True
        and config.get("broker_connection_allowed") is False
        and config.get("order_execution_allowed") is False
        and config.get("real_money_allowed") is False
    )
    spec_ok = bool(inputs["spec"]["loaded"] and inputs["spec"]["manifest"].get("paper_only_specification") is True)
    readiness_clear = bool(
        inputs["readiness"]["loaded"]
        and int(readiness_manifest.get("blocked_missing_threshold_artifact_count") or 0) == 0
        and int(readiness_manifest.get("blocked_missing_required_column_count") or 0) == 0
        and int(readiness_manifest.get("blocked_by_config_count") or 0) == 0
        and int(readiness_manifest.get("blocked_by_leakage_risk_count") or 0) == 0
        and int(readiness_manifest.get("blocking_warnings_count") or 0) == 0
    )
    thresholds_valid = validate_thresholds(inputs["thresholds"], allow_legacy=bool(args.allow_legacy_full_sample_thresholds))
    table = str(args.feature_source_table)
    table_allowed = table in ALLOWLISTED_FEATURE_TABLES
    table_blocked = table in BLOCKED_FEATURE_TABLES
    if not config_ok:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_only_boundary_not_confirmed",
            message="Demo strategy config does not preserve required paper-only flags.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    if not spec_ok:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_spec_unreadable_or_missing",
            message="Demo strategy spec is missing, unreadable, or does not confirm paper_only_specification.",
            source=args.demo_strategy_spec_dir,
            blocking_warning=True,
        )
    if not readiness_clear:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_signal_logger_readiness_blocker_present",
            message="Paper signal logger readiness is missing, unreadable, or has blockers.",
            source=args.paper_signal_logger_readiness_dir,
            blocking_warning=True,
        )
    if not inputs["thresholds_exists"] or inputs["thresholds_error"] or not thresholds_valid:
        add_warning(
            warnings,
            args=args,
            warning_code="threshold_artifact_unreadable",
            message="Current replays require train-only numeric-tercile thresholds; legacy full-sample thresholds require --allow-legacy-full-sample-thresholds.",
            source=args.tercile_thresholds_json,
            blocking_warning=True,
        )
    if table_blocked:
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_table_blocked",
            message="ml_dataset is blocked as a fixed-rule replay source due leakage risk.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    elif not table_allowed:
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_table_not_allowlisted",
            message="Feature source table is not allowlisted.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    return {
        "config_ok": config_ok,
        "spec_ok": spec_ok,
        "readiness_clear": readiness_clear,
        "thresholds_valid": thresholds_valid,
        "table_allowed": table_allowed,
        "table_blocked": table_blocked,
        "paper_only_boundary_confirmed": config_ok and spec_ok and readiness_clear,
    }


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


def validate_thresholds(thresholds: dict[str, Any], *, allow_legacy: bool = False) -> bool:
    if thresholds.get("candidate_id") != CANDIDATE_ID:
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


def fetch_feature_rows(args: argparse.Namespace, columns: set[str]) -> list[dict[str, Any]]:
    selected_columns = [column for column in REQUIRED_SOURCE_COLUMNS if column in columns]
    filters = [f"{quote_identifier('symbol')} = ?", f"{quote_identifier('timeframe')} = ?"]
    params: list[Any] = [args.symbol, args.timeframe]
    if args.from_time:
        filters.append(f"{quote_identifier('time_server')} >= ?")
        params.append(args.from_time)
    if args.to_time:
        filters.append(f"{quote_identifier('time_server')} <= ?")
        params.append(args.to_time)
    query = (
        f"SELECT {', '.join(quote_identifier(column) for column in selected_columns)} "
        f"FROM {quote_identifier(str(args.feature_source_table))} "
        f"WHERE {' AND '.join(filters)} "
        f"ORDER BY {quote_identifier('time_server')} ASC LIMIT ?"
    )
    params.append(int(args.max_bars))
    uri = f"file:{Path(args.feature_source_db).resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()
    return [{column: row[column] for column in selected_columns} for row in rows]


def bucket_for_value(value: float | None, lower: float, upper: float) -> str:
    if value is None:
        return "unreadable"
    if value <= lower:
        return "low_tercile"
    if value <= upper:
        return "mid_tercile"
    return "high_tercile"


def config_value(config: dict[str, Any]) -> dict[str, Any]:
    spread_unit = str(nested_get(config, "spread_and_session_controls", "spread_unit") or "broker_points")
    max_spread_points = safe_float(nested_get(config, "spread_and_session_controls", "max_spread_points")) or 15.0
    return {
        "direction": str(nested_get(config, "candidate", "direction") or "short"),
        "regime_column": str(nested_get(config, "entry_rule", "regime_column") or "hour_session"),
        "regime_value": str(nested_get(config, "entry_rule", "regime_value") or "Off_hours"),
        "tp_atr": safe_float(nested_get(config, "risk_reward", "tp_atr")) or 1.5,
        "sl_atr": safe_float(nested_get(config, "risk_reward", "sl_atr")) or 1.0,
        "atr_column": str(nested_get(config, "risk_reward", "atr_column") or "atr_20"),
        "horizon_bars": safe_int(nested_get(config, "candidate", "target_horizon")) or 10,
        "same_bar_policy": str(nested_get(config, "risk_reward", "same_bar_policy") or "stop_first"),
        "spread_unit": spread_unit,
        "max_spread_points": max_spread_points,
        "spread_policy_matches_canonical": spread_unit == "broker_points" and max_spread_points == 15.0,
    }


def threshold_values(thresholds: dict[str, Any]) -> dict[str, float]:
    features = thresholds["features"]
    if threshold_schema_label(thresholds) == "train_only_low_mid_mid_high":
        return {
            "close_to_ma_fast_atr_20_lower": float(features["close_to_ma_fast_atr_20"]["low_mid_cutoff"]),
            "close_to_ma_fast_atr_20_upper": float(features["close_to_ma_fast_atr_20"]["mid_high_cutoff"]),
            "tick_volume_percentile_100_lower": float(features["tick_volume_percentile_100"]["low_mid_cutoff"]),
            "tick_volume_percentile_100_upper": float(features["tick_volume_percentile_100"]["mid_high_cutoff"]),
        }
    return {
        "close_to_ma_fast_atr_20_lower": float(features["close_to_ma_fast_atr_20"].get("lower_tercile_boundary", float("-inf"))),
        "close_to_ma_fast_atr_20_upper": float(features["close_to_ma_fast_atr_20"]["upper_tercile_boundary"]),
        "tick_volume_percentile_100_lower": float(features["tick_volume_percentile_100"]["lower_tercile_boundary"]),
        "tick_volume_percentile_100_upper": float(features["tick_volume_percentile_100"]["upper_tercile_boundary"]),
    }


def compute_r(entry_price: float, exit_price: float, sl_price: float, direction: str) -> float | None:
    if direction != "short":
        return None
    risk = sl_price - entry_price
    if risk <= 0:
        return None
    return (entry_price - exit_price) / risk


def evaluate_signal_gates(
    *,
    row: dict[str, Any],
    cfg: dict[str, Any],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    skip_reasons: list[str] = []
    close_value = safe_float(row.get("close"))
    atr_value = safe_float(row.get(cfg["atr_column"]))
    spread_value = safe_float(row.get("spread"))
    feature_a = safe_float(row.get("close_to_ma_fast_atr_20"))
    feature_b = safe_float(row.get("tick_volume_percentile_100"))
    observed_regime = str(row.get(cfg["regime_column"]) or "")
    bucket_a = "high_tercile" if feature_a is not None and feature_a > thresholds["close_to_ma_fast_atr_20_upper"] else bucket_for_value(
        feature_a,
        thresholds["close_to_ma_fast_atr_20_lower"],
        thresholds["close_to_ma_fast_atr_20_upper"],
    )
    bucket_b = bucket_for_value(
        feature_b,
        thresholds["tick_volume_percentile_100_lower"],
        thresholds["tick_volume_percentile_100_upper"],
    )
    if close_value is None or atr_value is None or spread_value is None or feature_a is None or feature_b is None:
        skip_reasons.append("required_value_missing")
    if observed_regime != cfg["regime_value"]:
        skip_reasons.append("session_mismatch")
    if spread_value is not None and spread_value > cfg["max_spread_points"]:
        skip_reasons.append("spread_above_threshold")
    if spread_value is None:
        skip_reasons.append("spread_missing")
    if bucket_a != "high_tercile":
        skip_reasons.append("close_to_ma_fast_atr_20_bucket_mismatch")
    if bucket_b != "mid_tercile":
        skip_reasons.append("tick_volume_percentile_100_bucket_mismatch")
    return {
        "skip_reasons": skip_reasons,
        "bucket_a": bucket_a,
        "bucket_b": bucket_b,
        "close": close_value,
        "atr": atr_value,
        "spread": spread_value,
        "feature_a": feature_a,
        "feature_b": feature_b,
        "observed_regime": observed_regime,
    }


def replay_rows(
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    cfg: dict[str, Any],
    thresholds: dict[str, float],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    bars: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    equity: list[dict[str, Any]] = []
    state: dict[str, Any] | None = None
    cumulative_r = 0.0
    peak_r = 0.0
    signal_index = 0

    for row in rows:
        state_before = "open" if state else "flat"
        row_open_signal_id = state["open_signal_id"] if state else ""
        signal_state = ""
        trade_status = ""
        event_label = ""
        skip_reasons: list[str] = []
        bucket_a = ""
        bucket_b = ""
        bars_elapsed = state.get("bars_elapsed", "") if state else ""
        if state:
            if str(row.get("time_server")) > str(state["entry_time_server"]):
                state["bars_elapsed"] += 1
                bars_elapsed = state["bars_elapsed"]
                low = safe_float(row.get("low"))
                high = safe_float(row.get("high"))
                close = safe_float(row.get("close"))
                tp_hit = low is not None and low <= state["tp_price"]
                sl_hit = high is not None and high >= state["sl_price"]
                exit_reason = ""
                exit_price: float | None = None
                if tp_hit and sl_hit:
                    exit_reason = "paper_sl_hit"
                    exit_price = state["sl_price"]
                    add_warning(
                        warnings,
                        args=args,
                        warning_code="same_bar_stop_first_applied",
                        message="TP and SL were both touched after entry; stop_first policy applied.",
                        source=args.feature_source_table,
                        blocking_warning=False,
                    )
                elif tp_hit:
                    exit_reason = "paper_tp_hit"
                    exit_price = state["tp_price"]
                elif sl_hit:
                    exit_reason = "paper_sl_hit"
                    exit_price = state["sl_price"]
                elif state["bars_elapsed"] >= state["horizon_bars"] and close is not None:
                    exit_reason = "paper_timeout"
                    exit_price = close
                if exit_reason:
                    r_multiple = compute_r(state["entry_price"], float(exit_price), state["sl_price"], cfg["direction"])
                    trades.append(
                        {
                            "run_id": args.run_id,
                            "open_signal_id": state["open_signal_id"],
                            "entry_time_server": state["entry_time_server"],
                            "exit_time_server": row.get("time_server", ""),
                            "entry_price": state["entry_price"],
                            "exit_price": exit_price,
                            "tp_price": state["tp_price"],
                            "sl_price": state["sl_price"],
                            "direction": cfg["direction"],
                            "exit_reason": exit_reason,
                            "R_multiple": r_multiple,
                            "bars_elapsed": state["bars_elapsed"],
                            "horizon_bars": state["horizon_bars"],
                            "same_bar_policy": cfg["same_bar_policy"],
                        }
                    )
                    if r_multiple is not None:
                        cumulative_r += r_multiple
                        peak_r = max(peak_r, cumulative_r)
                        equity.append(
                            {
                                "run_id": args.run_id,
                                "trade_index": len(trades),
                                "open_signal_id": state["open_signal_id"],
                                "exit_time_server": row.get("time_server", ""),
                                "exit_reason": exit_reason,
                                "R_multiple": r_multiple,
                                "cumulative_R": cumulative_r,
                                "peak_cumulative_R": peak_r,
                                "drawdown_R": peak_r - cumulative_r,
                            }
                        )
                    trade_status = {
                        "paper_tp_hit": "paper_trade_closed_tp",
                        "paper_sl_hit": "paper_trade_closed_sl",
                        "paper_timeout": "paper_trade_closed_timeout",
                    }[exit_reason]
                    event_label = "trade_closed"
                    state = None
                else:
                    trade_status = "paper_trade_still_open"
                    event_label = "trade_tracked"
            else:
                trade_status = "paper_trade_entry_bar_not_evaluated"
                event_label = "entry_bar_not_evaluated"
        else:
            gate = evaluate_signal_gates(row=row, cfg=cfg, thresholds=thresholds)
            skip_reasons = gate["skip_reasons"]
            bucket_a = gate["bucket_a"]
            bucket_b = gate["bucket_b"]
            if not skip_reasons and gate["close"] is not None and gate["atr"] is not None:
                signal_index += 1
                signal_id = f"{args.run_id}_{signal_index:06d}"
                entry_price = float(gate["close"])
                tp_price = entry_price - cfg["tp_atr"] * float(gate["atr"])
                sl_price = entry_price + cfg["sl_atr"] * float(gate["atr"])
                state = {
                    "open_signal_id": signal_id,
                    "entry_time_server": row.get("time_server", ""),
                    "entry_price": entry_price,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "bars_elapsed": 0,
                    "horizon_bars": cfg["horizon_bars"],
                }
                row_open_signal_id = signal_id
                signal_state = "paper_signal_opened"
                trade_status = "paper_trade_opened"
                event_label = "signal_opened"
                signals.append(
                    signal_row(
                        args=args,
                        row=row,
                        signal_id=signal_id,
                        cfg=cfg,
                        signal_state=signal_state,
                        skip_reasons=[],
                        entry_reference_price=entry_price,
                        tp_price=tp_price,
                        sl_price=sl_price,
                        gate=gate,
                    )
                )
            else:
                signal_state = "paper_signal_skipped"
                trade_status = "flat"
                event_label = "signal_skipped"
                signals.append(
                    signal_row(
                        args=args,
                        row=row,
                        signal_id="",
                        cfg=cfg,
                        signal_state=signal_state,
                        skip_reasons=skip_reasons,
                        entry_reference_price="",
                        tp_price="",
                        sl_price="",
                        gate=gate,
                    )
                )
        state_after = "open" if state else "flat"
        bars.append(
            {
                "run_id": args.run_id,
                "time_server": row.get("time_server", ""),
                "symbol": row.get("symbol", ""),
                "timeframe": row.get("timeframe", ""),
                "state_before": state_before,
                "state_after": state_after,
                "signal_state": signal_state,
                "trade_status": trade_status,
                "skip_reasons": ";".join(dict.fromkeys(skip_reasons)),
                "open": row.get("open", ""),
                "high": row.get("high", ""),
                "low": row.get("low", ""),
                "close": row.get("close", ""),
                "spread": row.get("spread", ""),
                "max_spread_points": cfg["max_spread_points"],
                "hour_session": row.get("hour_session", ""),
                "close_to_ma_fast_atr_20": row.get("close_to_ma_fast_atr_20", ""),
                "close_to_ma_fast_atr_20_bucket": bucket_a,
                "tick_volume_percentile_100": row.get("tick_volume_percentile_100", ""),
                "tick_volume_percentile_100_bucket": bucket_b,
                "atr_20": row.get("atr_20", ""),
                "open_signal_id": row_open_signal_id,
                "bars_elapsed": bars_elapsed if bars_elapsed != "" else (state["bars_elapsed"] if state else ""),
                "event_label": event_label,
            }
        )
    return {"bars": bars, "signals": signals, "trades": trades, "equity": equity, "open_state": state}


def signal_row(
    *,
    args: argparse.Namespace,
    row: dict[str, Any],
    signal_id: str,
    cfg: dict[str, Any],
    signal_state: str,
    skip_reasons: list[str],
    entry_reference_price: Any,
    tp_price: Any,
    sl_price: Any,
    gate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "signal_id": signal_id,
        "time_server": row.get("time_server", ""),
        "symbol": row.get("symbol", ""),
        "timeframe": row.get("timeframe", ""),
        "direction": cfg["direction"],
        "signal_state": signal_state,
        "skip_reasons": ";".join(dict.fromkeys(skip_reasons)),
        "entry_reference_price": entry_reference_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "atr_20": gate["atr"],
        "spread": gate["spread"],
        "max_spread_points": cfg["max_spread_points"],
        "hour_session": gate["observed_regime"],
        "close_to_ma_fast_atr_20": gate["feature_a"],
        "close_to_ma_fast_atr_20_bucket": gate["bucket_a"],
        "tick_volume_percentile_100": gate["feature_b"],
        "tick_volume_percentile_100_bucket": gate["bucket_b"],
    }


def longest_streak(values: list[float], positive: bool) -> int:
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


def metrics(replay: dict[str, Any], rows_loaded: int, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    trades = replay["trades"]
    r_values = [float(trade["R_multiple"]) for trade in trades if trade.get("R_multiple") not in ("", None)]
    return {
        "bars_loaded": rows_loaded,
        "bars_processed": len(replay["bars"]),
        "signals_opened": sum(1 for signal in replay["signals"] if signal["signal_state"] == "paper_signal_opened"),
        "signals_skipped": sum(1 for signal in replay["signals"] if signal["signal_state"] == "paper_signal_skipped"),
        "trades_closed": len(trades),
        "trades_tp": sum(1 for trade in trades if trade["exit_reason"] == "paper_tp_hit"),
        "trades_sl": sum(1 for trade in trades if trade["exit_reason"] == "paper_sl_hit"),
        "trades_timeout": sum(1 for trade in trades if trade["exit_reason"] == "paper_timeout"),
        "open_trade_remaining": replay["open_state"] is not None,
        "total_R": sum(r_values) if r_values else 0.0,
        "average_R": statistics.mean(r_values) if r_values else None,
        "median_R": statistics.median(r_values) if r_values else None,
        "min_R": min(r_values) if r_values else None,
        "max_R": max(r_values) if r_values else None,
        "win_rate_R_positive": (sum(1 for value in r_values if value > 0) / len(r_values)) if r_values else None,
        "max_drawdown_R": max((float(row["drawdown_R"]) for row in replay["equity"]), default=0.0),
        "longest_loss_streak": longest_streak(r_values, positive=False),
        "longest_win_streak": longest_streak(r_values, positive=True),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
    }


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    inputs = load_inputs(args)
    validation = validate_inputs(args, inputs, warnings)
    feature_rows: list[dict[str, Any]] = []
    schema = {"db_exists": False, "table_exists": False, "columns": set(), "error": ""}
    if not blocking_warnings(warnings):
        schema = inspect_schema(Path(args.feature_source_db), str(args.feature_source_table))
        if schema["error"]:
            add_warning(
                warnings,
                args=args,
                warning_code="feature_source_db_unreadable",
                message=f"Feature source DB could not be inspected: {schema['error']}",
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
            missing = [column for column in REQUIRED_SOURCE_COLUMNS if column not in schema["columns"]]
            if missing:
                add_warning(
                    warnings,
                    args=args,
                    warning_code="missing_required_columns",
                    message=f"Feature source table is missing required columns: {', '.join(missing)}",
                    source=args.feature_source_table,
                    blocking_warning=True,
                )
            else:
                feature_rows = fetch_feature_rows(args, set(schema["columns"]))
    cfg = config_value(inputs["config"])
    threshold_payload = threshold_values(inputs["thresholds"]) if validation["thresholds_valid"] else {}
    replay = {"bars": [], "signals": [], "trades": [], "equity": [], "open_state": None}
    if not blocking_warnings(warnings):
        replay = replay_rows(args=args, rows=feature_rows, cfg=cfg, thresholds=threshold_payload, warnings=warnings)
    stats = metrics(replay, len(feature_rows), warnings)
    write_csv(output_paths["bars"], replay["bars"], BARS_FIELDNAMES)
    write_csv(output_paths["signals"], replay["signals"], SIGNALS_FIELDNAMES)
    write_csv(output_paths["trades"], replay["trades"], TRADES_FIELDNAMES)
    write_csv(output_paths["equity"], replay["equity"], EQUITY_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(output_paths["report"], args=args, stats=stats, warnings=warnings, validation=validation, cfg=cfg, thresholds=inputs["thresholds"])
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        stats=stats,
        warnings=warnings,
        validation=validation,
        cfg=cfg,
        thresholds=inputs["thresholds"],
    )
    return {"replay": replay, "warnings": warnings, "stats": stats, "schema": schema}


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    stats: dict[str, Any],
    warnings: list[dict[str, Any]],
    validation: dict[str, Any],
    cfg: dict[str, Any],
    thresholds: dict[str, Any],
) -> None:
    metadata = threshold_metadata(thresholds, allow_legacy=bool(args.allow_legacy_full_sample_thresholds))
    lines = [
        "# Fixed Candidate Fixed-Rule Replay Backtest",
        "",
        "Fixed-rule local replay/backtest artifact. This uses already-imported local data.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation or feature refresh was performed.",
        "No optimization, parameter search, or candidate search was performed.",
        "This replay does not prove future performance.",
        "This replay is not candidate approval.",
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
        "## Replay Window Summary",
        "",
        f"- symbol: `{args.symbol}`",
        f"- timeframe: `{args.timeframe}`",
        f"- from_time: `{args.from_time}`",
        f"- to_time: `{args.to_time}`",
        f"- max_bars: `{args.max_bars}`",
        f"- bars_loaded: `{stats['bars_loaded']}`",
        f"- bars_processed: `{stats['bars_processed']}`",
        "",
        "## Signal Summary",
        "",
        f"- signals_opened: `{stats['signals_opened']}`",
        f"- signals_skipped: `{stats['signals_skipped']}`",
        "",
        "## Trade Outcome Summary",
        "",
        f"- trades_closed: `{stats['trades_closed']}`",
        f"- trades_tp: `{stats['trades_tp']}`",
        f"- trades_sl: `{stats['trades_sl']}`",
        f"- trades_timeout: `{stats['trades_timeout']}`",
        f"- open_trade_remaining: `{stats['open_trade_remaining']}`",
        "",
        "## Spread Policy",
        "",
        f"- spread_unit: `{cfg['spread_unit']}`",
        f"- max_spread_points: `{cfg['max_spread_points']}`",
        f"- spread_policy_matches_canonical: `{bool_text(bool(cfg['spread_policy_matches_canonical']))}`",
        "",
        "## R/Equity Summary",
        "",
        f"- total_R: `{stats['total_R']}`",
        f"- average_R: `{stats['average_R']}`",
        f"- median_R: `{stats['median_R']}`",
        f"- min_R: `{stats['min_R']}`",
        f"- max_R: `{stats['max_R']}`",
        f"- win_rate_R_positive: `{stats['win_rate_R_positive']}`",
        "",
        "## Drawdown/Streak Summary",
        "",
        f"- max_drawdown_R: `{stats['max_drawdown_R']}`",
        f"- longest_loss_streak: `{stats['longest_loss_streak']}`",
        f"- longest_win_streak: `{stats['longest_win_streak']}`",
        "",
        "## Caveats",
        "",
        "- Fixed rule only; thresholds, TP/SL, horizon, and spread gate were not changed.",
        "- Local replay only; not broker/demo/live execution.",
        "- Descriptive replay metrics only; no candidate-quality decision.",
        "",
        "## Next Manual Step",
        "",
        "Review replay artifacts before deciding any separate research follow-up.",
        "",
        "## Warnings",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        f"- paper_only_boundary_confirmed: `{bool_text(bool(validation['paper_only_boundary_confirmed']))}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    stats: dict[str, Any],
    warnings: list[dict[str, Any]],
    validation: dict[str, Any],
    cfg: dict[str, Any],
    thresholds: dict[str, Any],
) -> None:
    metadata = threshold_metadata(thresholds, allow_legacy=bool(args.allow_legacy_full_sample_thresholds))
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
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
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "from_time": args.from_time,
        "to_time": args.to_time,
        "max_bars": int(args.max_bars),
        "spread_unit": cfg["spread_unit"],
        "max_spread_points": cfg["max_spread_points"],
        "spread_policy_matches_canonical": cfg["spread_policy_matches_canonical"],
        **stats,
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "paper_only_boundary_confirmed": bool(validation["paper_only_boundary_confirmed"]),
        "no_child_scripts_executed": True,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_backtests_run": False,
        "fixed_rule_replay_backtest_run": True,
        "no_stress_validation_executed": True,
        "no_walk_forward_validation_executed": True,
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
    parser = argparse.ArgumentParser(description="Run fixed-rule local replay backtest for the fixed candidate.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--paper-signal-logger-readiness-dir", type=Path, default=DEFAULT_READINESS_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--tercile-thresholds-json", type=Path)
    parser.add_argument("--allow-legacy-full-sample-thresholds", action="store_true")
    parser.add_argument("--feature-source-db", type=Path, default=DEFAULT_FEATURE_SOURCE_DB)
    parser.add_argument("--feature-source-table", default=DEFAULT_FEATURE_SOURCE_TABLE)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--from-time", default="")
    parser.add_argument("--to-time", default="")
    parser.add_argument("--max-bars", type=int, default=DEFAULT_MAX_BARS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, sqlite3.Error, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate fixed-rule replay backtest failed: {exc}")
        return 1
    print("Fixed-candidate fixed-rule replay backtest complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
