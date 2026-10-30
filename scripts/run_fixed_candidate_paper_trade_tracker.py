"""Run one local fixed-candidate paper trade tracker evaluation.

This script is intentionally single-shot and local-only. It reads an existing
paper signal state, copies that state into the tracker output as an immutable
input snapshot, inspects an allowlisted local feature table in read-only mode,
and tracks only locally observed bars after the paper entry timestamp. It does
not call the paper signal logger, loop, schedule itself, connect to MT5,
connect to broker/API services, execute orders, simulate broker execution,
mutate the project database, generate market data, run backtests, run
validation, or make candidate-quality or trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_paper_trade_tracker"
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
DEFAULT_PAPER_SIGNAL_LOGGER_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_v2"
)
DEFAULT_PAPER_SIGNAL_STATE_JSON = DEFAULT_PAPER_SIGNAL_LOGGER_DIR / "fixed_candidate_paper_signal_state.json"
DEFAULT_FEATURE_SOURCE_DB = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_FEATURE_SOURCE_TABLE = "price_features"
DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_paper_trade_tracker"

SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_REPORT = "fixed_candidate_demo_strategy_spec_report.md"
SPEC_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"
SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"

PAPER_LOGGER_CSV = "fixed_candidate_paper_signal_log.csv"
PAPER_LOGGER_REPORT = "fixed_candidate_paper_signal_logger_report.md"
PAPER_LOGGER_WARNINGS = "fixed_candidate_paper_signal_logger_warnings.csv"
PAPER_LOGGER_MANIFEST = "fixed_candidate_paper_signal_logger_manifest.json"

OUTPUT_TRACKER_CSV = "fixed_candidate_paper_trade_tracker.csv"
OUTPUT_EVENTS = "fixed_candidate_paper_trade_tracker_events.jsonl"
OUTPUT_INPUT_STATE_SNAPSHOT = "fixed_candidate_paper_trade_tracker_input_state_snapshot.json"
OUTPUT_STATE = "fixed_candidate_paper_trade_tracker_state.json"
OUTPUT_STATE_HISTORY = "fixed_candidate_paper_trade_tracker_state_history.csv"
OUTPUT_REPORT = "fixed_candidate_paper_trade_tracker_report.md"
OUTPUT_WARNINGS = "fixed_candidate_paper_trade_tracker_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_paper_trade_tracker_manifest.json"

ALLOWLISTED_FEATURE_TABLES = {"price_features", "market_features"}
BLOCKED_FEATURE_TABLES = {"ml_dataset"}
REQUIRED_STATE_FIELDS = (
    "has_open_paper_trade",
    "open_signal_id",
    "entry_time_server",
    "entry_price",
    "tp_price",
    "sl_price",
    "horizon_bars",
)
REQUIRED_BAR_COLUMNS = ("time_server", "open", "high", "low", "close")
OPTIONAL_FILTER_COLUMNS = ("symbol", "timeframe")

TRACKER_FIELDNAMES = [
    "run_id",
    "open_signal_id",
    "row_type",
    "time_server",
    "bar_index_after_entry",
    "open",
    "high",
    "low",
    "close",
    "entry_price",
    "tp_price",
    "sl_price",
    "direction",
    "same_bar_policy",
    "tp_hit",
    "sl_hit",
    "exit_reason",
    "exit_price",
    "R_multiple",
    "trade_status",
    "has_open_paper_trade_before",
    "has_open_paper_trade_after",
    "source_db",
    "source_table",
    "no_order_execution",
]

STATE_HISTORY_FIELDNAMES = [
    "run_id",
    "open_signal_id",
    "event",
    "event_at",
    "state_before",
    "state_after",
    "source_state_json",
    "input_state_snapshot_json",
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


def write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "tracker": output_dir / OUTPUT_TRACKER_CSV,
        "events": output_dir / OUTPUT_EVENTS,
        "input_state_snapshot": output_dir / OUTPUT_INPUT_STATE_SNAPSHOT,
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


def fetch_observed_bars(
    *,
    db_path: Path,
    table_name: str,
    columns: set[str],
    symbol: str,
    timeframe: str,
    entry_time_server: str,
    horizon_bars: int,
) -> list[dict[str, Any]]:
    selected_columns = [column for column in [*REQUIRED_BAR_COLUMNS, *OPTIONAL_FILTER_COLUMNS] if column in columns]
    filters = [f"{quote_identifier('time_server')} > ?"]
    params: list[Any] = [entry_time_server]
    if "symbol" in columns:
        filters.append(f"{quote_identifier('symbol')} = ?")
        params.append(symbol)
    if "timeframe" in columns:
        filters.append(f"{quote_identifier('timeframe')} = ?")
        params.append(timeframe)
    query = (
        f"SELECT {', '.join(quote_identifier(column) for column in selected_columns)} "
        f"FROM {quote_identifier(table_name)} "
        f"WHERE {' AND '.join(filters)} "
        f"ORDER BY {quote_identifier('time_server')} ASC LIMIT ?"
    )
    params.append(max(horizon_bars + 5, 1))
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()
    return [{column: row[column] for column in selected_columns} for row in rows]


def copy_input_state_snapshot(args: argparse.Namespace, snapshot_path: Path, warnings: list[dict[str, Any]]) -> bool:
    source = Path(args.paper_signal_state_json)
    if not source.exists():
        add_warning(
            warnings,
            args=args,
            warning_code="state_json_unreadable",
            message="Paper signal state JSON is missing.",
            source=source,
            blocking_warning=True,
        )
        return False
    try:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, snapshot_path)
    except OSError as exc:
        add_warning(
            warnings,
            args=args,
            warning_code="input_state_snapshot_failed",
            message=f"Input state snapshot could not be written: {exc}",
            source=source,
            blocking_warning=True,
        )
        return False
    return True


def load_inputs(args: argparse.Namespace) -> dict[str, Any]:
    config, config_error = read_json(Path(args.demo_strategy_config))
    spec = load_bundle(Path(args.demo_strategy_spec_dir), SPEC_CSV, SPEC_MANIFEST, SPEC_REPORT, SPEC_WARNINGS)
    logger_bundle = load_bundle(
        Path(args.paper_signal_logger_dir),
        PAPER_LOGGER_CSV,
        PAPER_LOGGER_MANIFEST,
        PAPER_LOGGER_REPORT,
        PAPER_LOGGER_WARNINGS,
    )
    state, state_error = read_json(Path(args.paper_signal_state_json))
    return {
        "config": config,
        "config_error": config_error,
        "config_exists": Path(args.demo_strategy_config).exists(),
        "spec": spec,
        "logger": logger_bundle,
        "state": state,
        "state_error": state_error,
        "state_exists": Path(args.paper_signal_state_json).exists(),
    }


def validate_boundaries(args: argparse.Namespace, inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, bool]:
    config = inputs["config"]
    spec_manifest = inputs["spec"]["manifest"]
    logger_manifest = inputs["logger"]["manifest"]
    config_boundary = bool(
        inputs["config_exists"]
        and not inputs["config_error"]
        and config.get("paper_only") is True
        and config.get("broker_connection_allowed") is False
        and config.get("order_execution_allowed") is False
        and config.get("real_money_allowed") is False
    )
    spec_boundary = bool(inputs["spec"]["loaded"] and spec_manifest.get("paper_only_specification") is True)
    logger_boundary = bool(
        inputs["logger"]["loaded"]
        and logger_manifest.get("no_order_execution_performed") is True
        and logger_manifest.get("no_broker_connection_performed") is True
    )
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
    if not inputs["logger"]["loaded"]:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_signal_logger_artifact_unreadable_or_missing",
            message="Paper signal logger artifacts are missing or unreadable.",
            source=args.paper_signal_logger_dir,
            blocking_warning=True,
        )
    elif not logger_boundary:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_signal_logger_boundary_not_confirmed",
            message="Paper signal logger manifest does not confirm no-order and no-broker boundaries.",
            source=args.paper_signal_logger_dir,
            blocking_warning=True,
        )
    return {
        "config_boundary": config_boundary,
        "spec_boundary": spec_boundary,
        "logger_boundary": logger_boundary,
        "paper_only_boundary_confirmed": config_boundary and spec_boundary and logger_boundary,
    }


def validate_state(args: argparse.Namespace, state: dict[str, Any], state_error: str, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    if state_error:
        add_warning(
            warnings,
            args=args,
            warning_code="state_json_unreadable",
            message=f"Paper signal state JSON is unreadable: {state_error}",
            source=args.paper_signal_state_json,
            blocking_warning=True,
        )
        return {"valid": False, "no_open_trade": False}
    if not state:
        add_warning(
            warnings,
            args=args,
            warning_code="state_json_unreadable",
            message="Paper signal state JSON is missing or empty.",
            source=args.paper_signal_state_json,
            blocking_warning=True,
        )
        return {"valid": False, "no_open_trade": False}
    if state.get("has_open_paper_trade") is not True:
        add_warning(
            warnings,
            args=args,
            warning_code="no_open_paper_trade_to_track",
            message="Input state has no open paper trade to track.",
            source=args.paper_signal_state_json,
            blocking_warning=False,
        )
        return {"valid": True, "no_open_trade": True}
    missing = [field for field in REQUIRED_STATE_FIELDS if state.get(field) in ("", None)]
    entry_price = safe_float(state.get("entry_price"))
    tp_price = safe_float(state.get("tp_price"))
    sl_price = safe_float(state.get("sl_price"))
    horizon_bars = safe_int(state.get("horizon_bars"))
    if missing or entry_price is None or tp_price is None or sl_price is None or horizon_bars is None or horizon_bars <= 0:
        add_warning(
            warnings,
            args=args,
            warning_code="input_state_missing_required_field",
            message="Input state is missing required open paper trade fields or numeric values.",
            source=args.paper_signal_state_json,
            blocking_warning=True,
        )
        return {"valid": False, "no_open_trade": False}
    return {
        "valid": True,
        "no_open_trade": False,
        "entry_price": entry_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "horizon_bars": horizon_bars,
        "bars_elapsed_before": safe_int(state.get("bars_elapsed")) or 0,
    }


def validate_feature_source(
    args: argparse.Namespace,
    state_validation: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    table_name = str(args.feature_source_table)
    if table_name in BLOCKED_FEATURE_TABLES:
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_table_blocked",
            message="ml_dataset is blocked as a paper trade tracking source due leakage risk.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
        return {"db_exists": False, "table_exists": False, "columns": set(), "error": ""}, []
    if table_name not in ALLOWLISTED_FEATURE_TABLES:
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_table_blocked",
            message="Feature source table is not allowlisted.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
        return {"db_exists": False, "table_exists": False, "columns": set(), "error": ""}, []
    schema = inspect_schema(Path(args.feature_source_db), table_name)
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
        missing = [column for column in REQUIRED_BAR_COLUMNS if column not in schema["columns"]]
        if missing:
            add_warning(
                warnings,
                args=args,
                warning_code="observed_bars_missing",
                message=f"Feature source table is missing required observed bar columns: {', '.join(missing)}",
                source=args.feature_source_table,
                blocking_warning=True,
            )
    observed_bars: list[dict[str, Any]] = []
    if schema["db_exists"] and schema["table_exists"] and not blocking_warnings(warnings) and not state_validation.get("no_open_trade"):
        observed_bars = fetch_observed_bars(
            db_path=Path(args.feature_source_db),
            table_name=table_name,
            columns=set(schema["columns"]),
            symbol=str(args.symbol),
            timeframe=str(args.timeframe),
            entry_time_server=str(state_validation["state"].get("entry_time_server", "")),
            horizon_bars=int(state_validation["horizon_bars"]),
        )
        if not observed_bars:
            add_warning(
                warnings,
                args=args,
                warning_code="observed_bars_missing",
                message="No locally observed bars after entry_time_server were available.",
                source=args.feature_source_table,
                blocking_warning=False,
            )
    return schema, observed_bars


def compute_short_r(entry_price: float, exit_price: float, sl_price: float) -> float | None:
    risk = sl_price - entry_price
    if risk <= 0:
        return None
    return (entry_price - exit_price) / risk


def evaluate_trade(
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    input_state: dict[str, Any],
    state_validation: dict[str, Any],
    observed_bars: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    direction = str(nested_get(config, "candidate", "direction") or "short")
    same_bar_policy = str(nested_get(config, "risk_reward", "same_bar_policy") or "stop_first")
    entry_price = float(state_validation["entry_price"])
    tp_price = float(state_validation["tp_price"])
    sl_price = float(state_validation["sl_price"])
    horizon_bars = int(state_validation["horizon_bars"])
    bars_elapsed_before = int(state_validation["bars_elapsed_before"])
    open_signal_id = str(input_state.get("open_signal_id", ""))
    state_after = dict(input_state)
    state_after.setdefault("has_open_paper_trade", True)
    status = "paper_trade_still_open"
    exit_reason = ""
    exit_price: float | None = None
    exit_time_server = ""
    r_multiple: float | None = None
    bars_elapsed_after = bars_elapsed_before
    has_open_before = bool(input_state.get("has_open_paper_trade"))

    for index, bar in enumerate(observed_bars, start=1):
        bars_elapsed_after = bars_elapsed_before + index
        high = safe_float(bar.get("high"))
        low = safe_float(bar.get("low"))
        close = safe_float(bar.get("close"))
        time_server = str(bar.get("time_server") or "")
        tp_hit = low is not None and low <= tp_price if direction == "short" else high is not None and high >= tp_price
        sl_hit = high is not None and high >= sl_price if direction == "short" else low is not None and low <= sl_price
        row_exit_reason = ""
        row_exit_price: float | None = None
        row_status = "paper_trade_still_open"
        if tp_hit and sl_hit:
            if same_bar_policy == "stop_first":
                row_exit_reason = "paper_sl_hit"
                row_exit_price = sl_price
                add_warning(
                    warnings,
                    args=args,
                    warning_code="same_bar_stop_first_applied",
                    message="TP and SL were both touched on the same observed bar; stop_first policy applied.",
                    source=args.feature_source_table,
                    blocking_warning=False,
                )
            else:
                row_exit_reason = "paper_tp_hit"
                row_exit_price = tp_price
        elif tp_hit:
            row_exit_reason = "paper_tp_hit"
            row_exit_price = tp_price
        elif sl_hit:
            row_exit_reason = "paper_sl_hit"
            row_exit_price = sl_price
        elif bars_elapsed_after >= horizon_bars and close is not None:
            row_exit_reason = "paper_timeout"
            row_exit_price = close
        if row_exit_reason:
            exit_reason = row_exit_reason
            exit_price = row_exit_price
            exit_time_server = time_server
            status = {
                "paper_tp_hit": "paper_trade_closed_tp",
                "paper_sl_hit": "paper_trade_closed_sl",
                "paper_timeout": "paper_trade_closed_timeout",
            }[row_exit_reason]
            row_status = status
            if exit_price is not None and direction == "short":
                r_multiple = compute_short_r(entry_price, exit_price, sl_price)
            state_after.update(
                {
                    "has_open_paper_trade": False,
                    "close_time_server": exit_time_server,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "bars_elapsed": bars_elapsed_after,
                    "last_seen_time_server": time_server,
                    "state_updated_at": utc_now_text(),
                    "R_multiple": r_multiple,
                }
            )
        rows.append(
            {
                "run_id": args.run_id,
                "open_signal_id": open_signal_id,
                "row_type": "observed_bar",
                "time_server": time_server,
                "bar_index_after_entry": index,
                "open": bar.get("open", ""),
                "high": bar.get("high", ""),
                "low": bar.get("low", ""),
                "close": bar.get("close", ""),
                "entry_price": entry_price,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "direction": direction,
                "same_bar_policy": same_bar_policy,
                "tp_hit": tp_hit,
                "sl_hit": sl_hit,
                "exit_reason": row_exit_reason,
                "exit_price": row_exit_price,
                "R_multiple": r_multiple if row_exit_reason else "",
                "trade_status": row_status,
                "has_open_paper_trade_before": has_open_before,
                "has_open_paper_trade_after": row_status == "paper_trade_still_open",
                "source_db": args.feature_source_db,
                "source_table": args.feature_source_table,
                "no_order_execution": True,
            }
        )
        if row_exit_reason:
            break

    if not observed_bars:
        state_after.update(
            {
                "has_open_paper_trade": True,
                "bars_elapsed": bars_elapsed_before,
                "last_seen_time_server": input_state.get("last_seen_time_server", ""),
                "state_updated_at": utc_now_text(),
            }
        )
    elif status == "paper_trade_still_open":
        if bars_elapsed_after < horizon_bars:
            add_warning(
                warnings,
                args=args,
                warning_code="insufficient_bars_for_timeout",
                message="Fewer observed bars than horizon_bars are available; paper trade remains open.",
                source=args.feature_source_table,
                blocking_warning=False,
            )
        last_bar = observed_bars[min(len(observed_bars), horizon_bars) - 1]
        state_after.update(
            {
                "has_open_paper_trade": True,
                "bars_elapsed": bars_elapsed_after,
                "last_seen_time_server": last_bar.get("time_server", input_state.get("last_seen_time_server", "")),
                "state_updated_at": utc_now_text(),
            }
        )
    summary = {
        "run_id": args.run_id,
        "open_signal_id": open_signal_id,
        "row_type": "summary",
        "time_server": exit_time_server or state_after.get("last_seen_time_server", ""),
        "bar_index_after_entry": bars_elapsed_after,
        "open": "",
        "high": "",
        "low": "",
        "close": "",
        "entry_price": entry_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "direction": direction,
        "same_bar_policy": same_bar_policy,
        "tp_hit": exit_reason == "paper_tp_hit",
        "sl_hit": exit_reason == "paper_sl_hit",
        "exit_reason": exit_reason,
        "exit_price": exit_price,
        "R_multiple": r_multiple,
        "trade_status": status,
        "has_open_paper_trade_before": has_open_before,
        "has_open_paper_trade_after": bool(state_after.get("has_open_paper_trade")),
        "source_db": args.feature_source_db,
        "source_table": args.feature_source_table,
        "no_order_execution": True,
    }
    rows.append(summary)
    state_after["trade_status"] = status
    return rows, state_after


def no_open_trade_rows(args: argparse.Namespace, input_state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    state_after = dict(input_state)
    state_after["has_open_paper_trade"] = False
    state_after["trade_status"] = "no_open_paper_trade_to_track"
    row = {
        "run_id": args.run_id,
        "open_signal_id": input_state.get("open_signal_id", ""),
        "row_type": "summary",
        "time_server": input_state.get("last_seen_time_server", ""),
        "bar_index_after_entry": input_state.get("bars_elapsed", 0),
        "open": "",
        "high": "",
        "low": "",
        "close": "",
        "entry_price": input_state.get("entry_price", ""),
        "tp_price": input_state.get("tp_price", ""),
        "sl_price": input_state.get("sl_price", ""),
        "direction": "",
        "same_bar_policy": "",
        "tp_hit": False,
        "sl_hit": False,
        "exit_reason": "",
        "exit_price": "",
        "R_multiple": "",
        "trade_status": "no_open_paper_trade_to_track",
        "has_open_paper_trade_before": False,
        "has_open_paper_trade_after": False,
        "source_db": args.feature_source_db,
        "source_table": args.feature_source_table,
        "no_order_execution": True,
    }
    return [row], state_after


def blocked_rows(args: argparse.Namespace, input_state: dict[str, Any], warnings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    state_after = dict(input_state)
    state_after["trade_status"] = "paper_trade_tracking_blocked"
    row = {
        "run_id": args.run_id,
        "open_signal_id": input_state.get("open_signal_id", ""),
        "row_type": "summary",
        "time_server": input_state.get("last_seen_time_server", ""),
        "bar_index_after_entry": input_state.get("bars_elapsed", ""),
        "open": "",
        "high": "",
        "low": "",
        "close": "",
        "entry_price": input_state.get("entry_price", ""),
        "tp_price": input_state.get("tp_price", ""),
        "sl_price": input_state.get("sl_price", ""),
        "direction": "",
        "same_bar_policy": "",
        "tp_hit": False,
        "sl_hit": False,
        "exit_reason": ";".join(warning["warning_code"] for warning in blocking_warnings(warnings)),
        "exit_price": "",
        "R_multiple": "",
        "trade_status": "paper_trade_tracking_blocked",
        "has_open_paper_trade_before": bool(input_state.get("has_open_paper_trade")),
        "has_open_paper_trade_after": bool(input_state.get("has_open_paper_trade")),
        "source_db": args.feature_source_db,
        "source_table": args.feature_source_table,
        "no_order_execution": True,
    }
    return [row], state_after


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    event(events, "run_started", run_id=args.run_id)
    snapshot_written = copy_input_state_snapshot(args, output_paths["input_state_snapshot"], warnings)
    event(events, "input_state_snapshot_written", written=snapshot_written)
    inputs = load_inputs(args)
    boundary = validate_boundaries(args, inputs, warnings)
    state_validation = validate_state(args, inputs["state"], inputs["state_error"], warnings)
    state_validation["state"] = inputs["state"]
    event(events, "input_validated", blocking_warnings=len(blocking_warnings(warnings)))

    observed_bars: list[dict[str, Any]] = []
    schema: dict[str, Any] = {"columns": set(), "db_exists": False, "table_exists": False, "error": ""}
    if state_validation.get("valid") and not state_validation.get("no_open_trade") and not blocking_warnings(warnings):
        schema, observed_bars = validate_feature_source(args, state_validation, warnings)
    elif state_validation.get("no_open_trade"):
        schema = inspect_schema(Path(args.feature_source_db), str(args.feature_source_table))
    event(events, "observed_bars_loaded", observed_bar_count=len(observed_bars))

    input_state = inputs["state"] if isinstance(inputs["state"], dict) else {}
    if blocking_warnings(warnings):
        tracker_rows, state_after = blocked_rows(args, input_state, warnings)
    elif state_validation.get("no_open_trade"):
        tracker_rows, state_after = no_open_trade_rows(args, input_state)
    else:
        event(events, "trade_tracking_started", open_signal_id=input_state.get("open_signal_id", ""))
        tracker_rows, state_after = evaluate_trade(
            args=args,
            config=inputs["config"],
            input_state=input_state,
            state_validation=state_validation,
            observed_bars=observed_bars,
            warnings=warnings,
        )
        for row in tracker_rows:
            if row["row_type"] == "observed_bar":
                event(
                    events,
                    "bar_evaluated",
                    time_server=row.get("time_server"),
                    trade_status=row.get("trade_status"),
                    exit_reason=row.get("exit_reason"),
                )
    final_row = tracker_rows[-1]
    if final_row["trade_status"].startswith("paper_trade_closed"):
        event(events, "trade_closed", exit_reason=final_row.get("exit_reason"))
    elif final_row["trade_status"] == "paper_trade_still_open":
        event(events, "trade_still_open", bars_elapsed=final_row.get("bar_index_after_entry"))
    else:
        event(events, final_row["trade_status"])

    output_paths["state"].write_text(json.dumps(state_after, indent=2, sort_keys=True), encoding="utf-8")
    event(events, "state_written", state_json=str(output_paths["state"]))
    event(events, "run_completed", trade_status=final_row["trade_status"])

    state_history = [
        {
            "run_id": args.run_id,
            "open_signal_id": input_state.get("open_signal_id", ""),
            "event": "state_written",
            "event_at": utc_now_text(),
            "state_before": input_state,
            "state_after": state_after,
            "source_state_json": args.paper_signal_state_json,
            "input_state_snapshot_json": output_paths["input_state_snapshot"],
            "output_state_json": output_paths["state"],
        }
    ]
    write_csv(output_paths["tracker"], tracker_rows, TRACKER_FIELDNAMES)
    write_csv(output_paths["state_history"], state_history, STATE_HISTORY_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_jsonl(output_paths["events"], events)
    write_report(
        output_paths["report"],
        args=args,
        tracker_rows=tracker_rows,
        warnings=warnings,
        state_before=input_state,
        state_after=state_after,
        observed_bar_count=len(observed_bars),
    )
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        tracker_rows=tracker_rows,
        warnings=warnings,
        state_before=input_state,
        state_after=state_after,
        observed_bar_count=len(observed_bars),
        boundary=boundary,
        input_state_snapshot_path=output_paths["input_state_snapshot"],
    )
    return {
        "tracker_rows": tracker_rows,
        "warnings": warnings,
        "events": events,
        "state_after": state_after,
        "schema": schema,
    }


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    tracker_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    observed_bar_count: int,
) -> None:
    final_row = tracker_rows[-1]
    lines = [
        "# Fixed Candidate Paper Trade Tracker",
        "",
        "Single-shot local paper trade tracker artifact. This run does not loop, schedule itself, or stay resident.",
        "The paper signal logger was not executed.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation or feature refresh was performed.",
        "No trading decision was made.",
        "",
        "## Input State Summary",
        "",
        f"- source_state_json: `{args.paper_signal_state_json}`",
        f"- open_signal_id: `{state_before.get('open_signal_id', '')}`",
        f"- entry_time_server: `{state_before.get('entry_time_server', '')}`",
        f"- entry_price: `{state_before.get('entry_price', '')}`",
        f"- tp_price: `{state_before.get('tp_price', '')}`",
        f"- sl_price: `{state_before.get('sl_price', '')}`",
        f"- horizon_bars: `{state_before.get('horizon_bars', '')}`",
        "",
        "## Observed Bars Summary",
        "",
        f"- feature_source_db: `{args.feature_source_db}`",
        f"- feature_source_table: `{args.feature_source_table}`",
        f"- observed_bar_count: `{observed_bar_count}`",
        "",
        "## TP/SL/Timeout Evaluation",
        "",
        f"- same_bar_policy: `{final_row.get('same_bar_policy', '')}`",
        f"- trade_status: `{final_row.get('trade_status', '')}`",
        f"- exit_reason: `{final_row.get('exit_reason', '')}`",
        f"- exit_price: `{final_row.get('exit_price', '')}`",
        f"- R_multiple: `{final_row.get('R_multiple', '')}`",
        "",
        "## Updated State Summary",
        "",
        f"- has_open_paper_trade_before: `{bool_text(bool(state_before.get('has_open_paper_trade')))}`",
        f"- has_open_paper_trade_after: `{bool_text(bool(state_after.get('has_open_paper_trade')))}`",
        f"- bars_elapsed_after: `{state_after.get('bars_elapsed', '')}`",
        f"- last_seen_time_server: `{state_after.get('last_seen_time_server', '')}`",
        "",
        "## Warnings Summary",
        "",
        f"- warning_count: `{len(warnings)}`",
        f"- blocking_warning_count: `{len(blocking_warnings(warnings))}`",
        "",
        "## Next Step",
        "",
    ]
    if final_row.get("trade_status") == "paper_trade_still_open":
        lines.append("If still open, rerun this tracker manually after refreshing local data.")
    elif str(final_row.get("trade_status", "")).startswith("paper_trade_closed"):
        lines.append("If closed, rerun the paper signal logger manually only if desired and if local data is fresh.")
    else:
        lines.append("Review the tracker artifact before any further manual paper step.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    tracker_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    observed_bar_count: int,
    boundary: dict[str, bool],
    input_state_snapshot_path: Path,
) -> None:
    final_row = tracker_rows[-1]
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "paper_signal_logger_dir": str(args.paper_signal_logger_dir),
        "paper_signal_state_json": str(args.paper_signal_state_json),
        "input_state_snapshot_path": str(input_state_snapshot_path),
        "feature_source_db": str(args.feature_source_db),
        "feature_source_table": str(args.feature_source_table),
        "open_signal_id": state_before.get("open_signal_id", ""),
        "entry_time_server": state_before.get("entry_time_server", ""),
        "entry_price": safe_float(state_before.get("entry_price")),
        "tp_price": safe_float(state_before.get("tp_price")),
        "sl_price": safe_float(state_before.get("sl_price")),
        "horizon_bars": safe_int(state_before.get("horizon_bars")),
        "observed_bar_count": observed_bar_count,
        "bars_elapsed_before": safe_int(state_before.get("bars_elapsed")) or 0,
        "bars_elapsed_after": safe_int(state_after.get("bars_elapsed")) or 0,
        "trade_status": final_row.get("trade_status", ""),
        "exit_reason": final_row.get("exit_reason", ""),
        "exit_time_server": final_row.get("time_server", "") if final_row.get("exit_reason") else "",
        "exit_price": safe_float(final_row.get("exit_price")),
        "R_multiple": safe_float(final_row.get("R_multiple")),
        "has_open_paper_trade_before": bool(state_before.get("has_open_paper_trade")),
        "has_open_paper_trade_after": bool(state_after.get("has_open_paper_trade")),
        "warning_count": len(warnings),
        "warnings_count": len(warnings),
        "blocking_warning_count": len(blocking_warnings(warnings)),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "paper_only_boundary_confirmed": bool(boundary.get("paper_only_boundary_confirmed")),
        "no_child_scripts_executed": True,
        "no_paper_signal_logger_executed": True,
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
    build_artifacts(args, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one local fixed-candidate paper trade tracker evaluation.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--paper-signal-logger-dir", type=Path, default=DEFAULT_PAPER_SIGNAL_LOGGER_DIR)
    parser.add_argument("--paper-signal-state-json", type=Path, default=DEFAULT_PAPER_SIGNAL_STATE_JSON)
    parser.add_argument("--feature-source-db", type=Path, default=DEFAULT_FEATURE_SOURCE_DB)
    parser.add_argument("--feature-source-table", default=DEFAULT_FEATURE_SOURCE_TABLE)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, sqlite3.Error, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate paper trade tracker failed: {exc}")
        return 1
    print("Fixed-candidate paper trade tracker single-shot run complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
