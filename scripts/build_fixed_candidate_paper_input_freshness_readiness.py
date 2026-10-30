"""Build paper input freshness readiness for the fixed-candidate logger.

This artifact-only module checks whether the local feature source appears fresh
enough for manual single-shot paper logging. It reads paper/demo artifacts,
inspects a local SQLite feature table in read-only mode, and runs only a scoped
MIN/MAX/COUNT freshness query. It does not refresh data, generate data, mutate
the database, run the paper logger, connect to MT5, connect to broker/API
services, execute orders, run validation/backtests, or make candidate-quality
or trading decisions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_paper_input_freshness_readiness"
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
DEFAULT_PAPER_SIGNAL_LOGGER_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger_readiness"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_readiness_v3"
)
DEFAULT_PAPER_SIGNAL_LOGGER_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_v1"
)
DEFAULT_FEATURE_SOURCE_DB = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_FEATURE_SOURCE_TABLE = "price_features"
DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_MAX_STALENESS_HOURS = 24.0
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_paper_input_freshness_readiness"

SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_REPORT = "fixed_candidate_demo_strategy_spec_report.md"
SPEC_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"
SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"

READINESS_CSV = "fixed_candidate_paper_signal_logger_readiness.csv"
READINESS_REPORT = "fixed_candidate_paper_signal_logger_readiness_report.md"
READINESS_WARNINGS = "fixed_candidate_paper_signal_logger_readiness_warnings.csv"
READINESS_MANIFEST = "fixed_candidate_paper_signal_logger_readiness_manifest.json"

PAPER_LOGGER_CSV = "fixed_candidate_paper_signal_log.csv"
PAPER_LOGGER_REPORT = "fixed_candidate_paper_signal_logger_report.md"
PAPER_LOGGER_WARNINGS = "fixed_candidate_paper_signal_logger_warnings.csv"
PAPER_LOGGER_MANIFEST = "fixed_candidate_paper_signal_logger_manifest.json"

OUTPUT_CSV = "fixed_candidate_paper_input_freshness_readiness.csv"
OUTPUT_REPORT = "fixed_candidate_paper_input_freshness_readiness_report.md"
OUTPUT_WARNINGS = "fixed_candidate_paper_input_freshness_readiness_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_paper_input_freshness_readiness_manifest.json"

ALLOWLISTED_FEATURE_TABLES = {"price_features", "market_features"}
BLOCKED_FEATURE_TABLES = {"ml_dataset"}

FIELDNAMES = [
    "run_id",
    "readiness_area",
    "artifact_status",
    "readiness_status",
    "source_path",
    "source_table",
    "observed_value",
    "expected_value",
    "latest_time_server",
    "current_timestamp_utc",
    "staleness_hours",
    "max_staleness_hours",
    "evidence_label",
    "caveat",
    "required_next_artifact",
    "warning_code",
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_text() -> str:
    return utc_now().isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def labels(*values: str) -> str:
    return ";".join(value for value in values if value)


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
        "readiness": output_dir / OUTPUT_CSV,
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


def base_row(args: argparse.Namespace, readiness_area: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "readiness_area": readiness_area,
        "artifact_status": "available",
        "readiness_status": "fresh_enough_for_manual_single_shot_paper_logging",
        "source_path": "",
        "source_table": "",
        "observed_value": "",
        "expected_value": "",
        "latest_time_server": "",
        "current_timestamp_utc": "",
        "staleness_hours": "",
        "max_staleness_hours": args.max_staleness_hours,
        "evidence_label": "",
        "caveat": "no_trading_decision_made",
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


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


def parse_time_server(value: Any) -> tuple[datetime | None, str]:
    if value in ("", None):
        return None, "missing timestamp"
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        return None, str(exc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed, ""


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


def fetch_freshness(
    *,
    db_path: Path,
    table_name: str,
    columns: set[str],
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    filters: list[str] = []
    params: list[Any] = []
    symbol_filter_applied = False
    timeframe_filter_applied = False
    if "symbol" in columns:
        filters.append(f"{quote_identifier('symbol')} = ?")
        params.append(symbol)
        symbol_filter_applied = True
    if "timeframe" in columns:
        filters.append(f"{quote_identifier('timeframe')} = ?")
        params.append(timeframe)
        timeframe_filter_applied = True
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = (
        f"SELECT MIN({quote_identifier('time_server')}), MAX({quote_identifier('time_server')}), COUNT(*) "
        f"FROM {quote_identifier(table_name)} {where}"
    )
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        row = connection.execute(query, params).fetchone()
    return {
        "earliest_time_server": row[0] if row else None,
        "latest_time_server": row[1] if row else None,
        "row_count_for_scope": int(row[2] or 0) if row else 0,
        "symbol_filter_applied": symbol_filter_applied,
        "timeframe_filter_applied": timeframe_filter_applied,
    }


def validate_config_and_artifacts(
    args: argparse.Namespace,
    config: dict[str, Any],
    config_error: str,
    spec: dict[str, Any],
    readiness: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, bool]:
    config_ok = bool(
        config
        and not config_error
        and config.get("paper_only") is True
        and config.get("broker_connection_allowed") is False
        and config.get("order_execution_allowed") is False
        and config.get("real_money_allowed") is False
    )
    spec_ok = bool(spec["loaded"] and spec["manifest"].get("paper_only_specification") is True)
    readiness_ok = bool(readiness["loaded"] and readiness["manifest"].get("paper_only_boundary_confirmed") is True)
    if not config:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_config_missing",
            message="Demo strategy config is missing or empty.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    elif config_error:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_config_unreadable",
            message=f"Demo strategy config is unreadable: {config_error}",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    elif not config_ok:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_only_boundary_not_confirmed",
            message="Demo strategy config does not preserve paper-only boundary flags.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    if not spec["loaded"]:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_spec_missing_or_unreadable",
            message="Demo strategy spec artifacts are missing or unreadable.",
            source=args.demo_strategy_spec_dir,
            blocking_warning=True,
        )
    elif not spec_ok:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_spec_boundary_not_confirmed",
            message="Demo strategy spec does not confirm paper_only_specification.",
            source=args.demo_strategy_spec_dir,
            blocking_warning=True,
        )
    if not readiness["loaded"]:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_signal_logger_readiness_missing_or_unreadable",
            message="Paper signal logger readiness artifacts are missing or unreadable.",
            source=args.paper_signal_logger_readiness_dir,
            blocking_warning=True,
        )
    elif not readiness_ok:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_signal_logger_readiness_boundary_not_confirmed",
            message="Paper signal logger readiness does not confirm paper-only boundary.",
            source=args.paper_signal_logger_readiness_dir,
            blocking_warning=True,
        )
    return {
        "config_ok": config_ok,
        "spec_ok": spec_ok,
        "readiness_ok": readiness_ok,
        "paper_only_boundary_confirmed": config_ok and spec_ok and readiness_ok,
    }


def latest_from_paper_logger(logger_bundle: dict[str, Any]) -> str:
    manifest = logger_bundle["manifest"]
    value = manifest.get("evaluated_row_time_server")
    if value:
        return str(value)
    for row in logger_bundle["rows"]:
        if row.get("time_server"):
            return str(row["time_server"])
    return ""


def build_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    current_dt = utc_now()
    current_timestamp_utc = current_dt.isoformat()
    config, config_error = read_json(Path(args.demo_strategy_config))
    spec = load_bundle(Path(args.demo_strategy_spec_dir), SPEC_CSV, SPEC_MANIFEST, SPEC_REPORT, SPEC_WARNINGS)
    readiness = load_bundle(
        Path(args.paper_signal_logger_readiness_dir),
        READINESS_CSV,
        READINESS_MANIFEST,
        READINESS_REPORT,
        READINESS_WARNINGS,
    )
    logger_bundle = load_bundle(
        Path(args.paper_signal_logger_dir),
        PAPER_LOGGER_CSV,
        PAPER_LOGGER_MANIFEST,
        PAPER_LOGGER_REPORT,
        PAPER_LOGGER_WARNINGS,
    )
    boundary = validate_config_and_artifacts(args, config, config_error, spec, readiness, warnings)

    config_row = base_row(args, "demo_strategy_config_gate")
    config_row.update(
        {
            "source_path": args.demo_strategy_config,
            "observed_value": bool_text(boundary["config_ok"]),
            "expected_value": "paper_only=true;broker_connection_allowed=false;order_execution_allowed=false;real_money_allowed=false",
            "evidence_label": "paper_only_boundary_confirmed" if boundary["config_ok"] else "",
        }
    )
    if not boundary["config_ok"]:
        config_row.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_config",
                "warning_code": "demo_strategy_config_gate_blocked",
                "blocking_warning": True,
            }
        )
    rows.append(config_row)

    spec_row = base_row(args, "demo_strategy_spec_gate")
    spec_row.update(
        {
            "source_path": args.demo_strategy_spec_dir,
            "observed_value": bool_text(boundary["spec_ok"]),
            "expected_value": "paper_only_specification=true",
            "evidence_label": "paper_only_boundary_confirmed" if boundary["spec_ok"] else "",
        }
    )
    if not boundary["spec_ok"]:
        spec_row.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_missing_required_artifact"
                if not spec["files_present"]
                else "blocked_by_config",
                "warning_code": "demo_strategy_spec_gate_blocked",
                "blocking_warning": True,
            }
        )
    rows.append(spec_row)

    readiness_row = base_row(args, "paper_signal_logger_readiness_gate")
    readiness_row.update(
        {
            "source_path": args.paper_signal_logger_readiness_dir,
            "observed_value": bool_text(boundary["readiness_ok"]),
            "expected_value": "paper_only_boundary_confirmed=true",
            "evidence_label": "paper_only_boundary_confirmed" if boundary["readiness_ok"] else "",
        }
    )
    if not boundary["readiness_ok"]:
        readiness_row.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_missing_required_artifact"
                if not readiness["files_present"]
                else "blocked_by_config",
                "warning_code": "paper_signal_logger_readiness_gate_blocked",
                "blocking_warning": True,
            }
        )
    rows.append(readiness_row)

    previous_time = latest_from_paper_logger(logger_bundle)
    previous_context = base_row(args, "paper_signal_logger_previous_run_context")
    previous_context.update(
        {
            "artifact_status": "available" if logger_bundle["loaded"] else "missing",
            "readiness_status": "context_only",
            "source_path": args.paper_signal_logger_dir,
            "observed_value": previous_time,
            "evidence_label": "paper_signal_logger_previous_run_context" if previous_time else "",
        }
    )
    rows.append(previous_context)

    schema = inspect_schema(Path(args.feature_source_db), str(args.feature_source_table))
    table_name = str(args.feature_source_table)
    table_allowlisted = table_name in ALLOWLISTED_FEATURE_TABLES
    table_blocked = table_name in BLOCKED_FEATURE_TABLES
    feature_source_db_gate = base_row(args, "feature_source_db_gate")
    feature_source_db_gate.update(
        {
            "source_path": args.feature_source_db,
            "source_table": table_name,
            "observed_value": bool_text(bool(schema["db_exists"])),
            "evidence_label": "feature_source_db_available" if schema["db_exists"] else "",
            "caveat": "no_db_mutation_performed",
        }
    )
    if schema["error"]:
        feature_source_db_gate.update(
            {
                "artifact_status": "unreadable",
                "readiness_status": "blocked_unreadable_input",
                "warning_code": "feature_source_db_unreadable",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_db_unreadable",
            message=f"Feature source DB schema could not be inspected: {schema['error']}",
            source=args.feature_source_db,
            blocking_warning=True,
        )
    elif not schema["db_exists"]:
        feature_source_db_gate.update(
            {
                "artifact_status": "missing",
                "readiness_status": "blocked_missing_required_artifact",
                "warning_code": "feature_source_db_missing",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_db_missing",
            message="Feature source DB is missing.",
            source=args.feature_source_db,
            blocking_warning=True,
        )
    rows.append(feature_source_db_gate)

    feature_source_table_gate = base_row(args, "feature_source_table_gate")
    feature_source_table_gate.update(
        {
            "source_path": args.feature_source_db,
            "source_table": table_name,
            "observed_value": table_name,
            "expected_value": ",".join(sorted(ALLOWLISTED_FEATURE_TABLES)),
            "evidence_label": "feature_source_table_allowlisted" if table_allowlisted else "",
        }
    )
    if table_blocked:
        feature_source_table_gate.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_leakage_risk",
                "evidence_label": "feature_source_table_blocked_for_leakage_risk",
                "warning_code": "feature_source_table_leakage_risk",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_table_leakage_risk",
            message="ml_dataset is blocked as a paper input freshness source due leakage risk.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    elif not table_allowlisted:
        feature_source_table_gate.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_config",
                "warning_code": "feature_source_table_not_allowlisted",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_table_not_allowlisted",
            message="Feature source table is not allowlisted.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    elif schema["db_exists"] and not schema["table_exists"]:
        feature_source_table_gate.update(
            {
                "artifact_status": "missing",
                "readiness_status": "blocked_missing_required_artifact",
                "warning_code": "feature_source_table_missing",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            args=args,
            warning_code="feature_source_table_missing",
            message="Feature source table is missing.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    rows.append(feature_source_table_gate)

    columns = set(schema["columns"])
    freshness_schema_gate = base_row(args, "freshness_schema_gate")
    freshness_schema_gate.update(
        {
            "source_path": args.feature_source_db,
            "source_table": table_name,
            "expected_value": "time_server",
            "observed_value": "time_server_present=" + bool_text("time_server" in columns),
            "evidence_label": "latest_time_server_available" if "time_server" in columns else "",
            "caveat": "no_db_mutation_performed",
        }
    )
    if schema["table_exists"] and "time_server" not in columns:
        freshness_schema_gate.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_config",
                "warning_code": "time_server_column_missing",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            args=args,
            warning_code="time_server_column_missing",
            message="time_server column is required for freshness readiness.",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    rows.append(freshness_schema_gate)

    freshness: dict[str, Any] = {
        "earliest_time_server": "",
        "latest_time_server": "",
        "row_count_for_scope": 0,
        "symbol_filter_applied": False,
        "timeframe_filter_applied": False,
    }
    if "symbol" not in columns and schema["table_exists"] and table_allowlisted and not table_blocked:
        add_warning(
            warnings,
            args=args,
            warning_code="symbol_filter_unavailable",
            message="symbol column is unavailable; symbol filter was not applied.",
            source=args.feature_source_table,
            blocking_warning=False,
        )
    if "timeframe" not in columns and schema["table_exists"] and table_allowlisted and not table_blocked:
        add_warning(
            warnings,
            args=args,
            warning_code="timeframe_filter_unavailable",
            message="timeframe column is unavailable; timeframe filter was not applied.",
            source=args.feature_source_table,
            blocking_warning=False,
        )
    if (
        schema["db_exists"]
        and schema["table_exists"]
        and "time_server" in columns
        and table_allowlisted
        and not table_blocked
    ):
        freshness = fetch_freshness(
            db_path=Path(args.feature_source_db),
            table_name=table_name,
            columns=columns,
            symbol=str(args.symbol),
            timeframe=str(args.timeframe),
        )

    latest_dt, latest_error = parse_time_server(freshness["latest_time_server"])
    earliest_dt, _earliest_error = parse_time_server(freshness["earliest_time_server"])
    staleness_hours: float | None = None
    stale = False
    if latest_dt is not None:
        staleness_hours = (current_dt - latest_dt).total_seconds() / 3600
        stale = staleness_hours > float(args.max_staleness_hours)

    latest_check = base_row(args, "latest_time_server_check")
    latest_check.update(
        {
            "source_path": args.feature_source_db,
            "source_table": table_name,
            "observed_value": freshness["latest_time_server"],
            "latest_time_server": freshness["latest_time_server"] or "",
            "current_timestamp_utc": current_timestamp_utc,
            "evidence_label": "latest_time_server_available" if latest_dt is not None else "",
        }
    )
    if schema["table_exists"] and "time_server" in columns and latest_dt is None:
        latest_check.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_unreadable_timestamp",
                "warning_code": "latest_time_server_unreadable",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            args=args,
            warning_code="latest_time_server_unreadable",
            message=f"latest time_server could not be parsed: {latest_error}",
            source=args.feature_source_table,
            blocking_warning=True,
        )
    rows.append(latest_check)

    staleness_check = base_row(args, "staleness_check")
    staleness_check.update(
        {
            "source_path": args.feature_source_db,
            "source_table": table_name,
            "latest_time_server": freshness["latest_time_server"] or "",
            "current_timestamp_utc": current_timestamp_utc,
            "staleness_hours": staleness_hours,
            "max_staleness_hours": args.max_staleness_hours,
            "observed_value": staleness_hours,
            "expected_value": f"<= {args.max_staleness_hours}",
            "evidence_label": "staleness_exceeds_threshold" if stale else "staleness_within_threshold",
        }
    )
    if latest_dt is None:
        staleness_check.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_unreadable_timestamp",
                "warning_code": "staleness_unavailable",
                "blocking_warning": True,
            }
        )
    elif stale:
        staleness_check.update(
            {
                "artifact_status": "available_with_caveat",
                "readiness_status": "stale_input_source",
                "warning_code": "stale_input_source",
                "caveat": "manual_feature_source_refresh_required",
            }
        )
        add_warning(
            warnings,
            args=args,
            warning_code="stale_input_source",
            message="Feature source latest time_server exceeds max staleness threshold.",
            source=args.feature_source_table,
            blocking_warning=False,
        )
    rows.append(staleness_check)

    previous_dt, _previous_error = parse_time_server(previous_time)
    consistency = base_row(args, "logger_latest_row_consistency_check")
    used_latest: bool | None = None
    consistency_label = ""
    consistency_status = "context_only"
    if previous_dt is not None and latest_dt is not None:
        used_latest = previous_dt == latest_dt
        if used_latest:
            consistency_label = "logger_used_latest_available_row"
        elif previous_dt < latest_dt:
            consistency_label = "logger_used_older_row_warning"
            consistency_status = "ready_with_caveat_for_manual_single_shot_paper_logging"
            add_warning(
                warnings,
                args=args,
                warning_code="logger_used_older_row_warning",
                message="Previous paper logger evaluated row is older than the current source MAX(time_server).",
                source=args.paper_signal_logger_dir,
                blocking_warning=False,
            )
        else:
            consistency_label = "logger_previous_row_after_latest_source_row"
            consistency_status = "ready_with_caveat_for_manual_single_shot_paper_logging"
    consistency.update(
        {
            "artifact_status": "available" if previous_time else "missing",
            "readiness_status": consistency_status,
            "source_path": args.paper_signal_logger_dir,
            "observed_value": previous_time,
            "expected_value": freshness["latest_time_server"] or "",
            "latest_time_server": freshness["latest_time_server"] or "",
            "current_timestamp_utc": current_timestamp_utc,
            "evidence_label": consistency_label,
            "caveat": "paper_signal_logger_previous_run_context",
        }
    )
    rows.append(consistency)

    source_refresh = base_row(args, "source_refresh_next_step")
    source_refresh.update(
        {
            "source_path": args.feature_source_db,
            "source_table": table_name,
            "latest_time_server": freshness["latest_time_server"] or "",
            "current_timestamp_utc": current_timestamp_utc,
            "staleness_hours": staleness_hours,
            "max_staleness_hours": args.max_staleness_hours,
            "readiness_status": "stale_input_source" if stale else "context_only",
            "artifact_status": "available_with_caveat" if stale else "available",
            "evidence_label": "manual_feature_source_refresh_required" if stale else "",
            "required_next_artifact": "manual_feature_source_refresh_planning_or_read_only_audit" if stale else "",
            "caveat": "do_not_run_refresh_from_this_module",
        }
    )
    rows.append(source_refresh)

    manual_logging = base_row(args, "manual_paper_logging_next_step")
    manual_logging.update(
        {
            "source_path": args.paper_signal_logger_dir,
            "latest_time_server": freshness["latest_time_server"] or "",
            "current_timestamp_utc": current_timestamp_utc,
            "staleness_hours": staleness_hours,
            "max_staleness_hours": args.max_staleness_hours,
            "readiness_status": "fresh_enough_for_manual_single_shot_paper_logging"
            if latest_dt is not None and not stale
            else "stale_input_source",
            "artifact_status": "available" if latest_dt is not None and not stale else "available_with_caveat",
            "evidence_label": "manual_single_shot_paper_logger_rerun_allowed"
            if latest_dt is not None and not stale
            else "manual_feature_source_refresh_required",
            "required_next_artifact": "manual_single_shot_paper_logger_rerun"
            if latest_dt is not None and not stale
            else "manual_feature_source_refresh_required",
            "caveat": "no_paper_runner_executed",
        }
    )
    rows.append(manual_logging)

    metadata = {
        "current_timestamp_utc": current_timestamp_utc,
        "schema": schema,
        "feature_source_table_allowlisted": table_allowlisted,
        "freshness": freshness,
        "earliest_time_server": freshness["earliest_time_server"] or "",
        "latest_time_server": freshness["latest_time_server"] or "",
        "earliest_dt": earliest_dt,
        "latest_dt": latest_dt,
        "staleness_hours": staleness_hours,
        "stale": stale,
        "paper_logger_previous_evaluated_row_time_server": previous_time,
        "paper_logger_used_latest_available_row": used_latest,
        "paper_only_boundary_confirmed": boundary["paper_only_boundary_confirmed"],
    }
    return rows, warnings, metadata


def count_rows(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    return Counter(str(row.get(field) or "") for row in rows)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    stale = bool(metadata["stale"])
    decision_text = (
        "stale input source"
        if stale
        else "fresh enough for manual single-shot paper logging"
    )
    next_step = (
        "manual feature source refresh planning/audit"
        if stale
        else "rerun paper signal logger manually when desired"
    )
    lines = [
        "# Fixed Candidate Paper Input Freshness Readiness",
        "",
        "Freshness-readiness-only artifact. This module only assesses local input freshness.",
        "Paper/local-only review. No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation or feature refresh was performed.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- demo_strategy_spec_dir: `{args.demo_strategy_spec_dir}`",
        f"- paper_signal_logger_readiness_dir: `{args.paper_signal_logger_readiness_dir}`",
        f"- paper_signal_logger_dir: `{args.paper_signal_logger_dir}`",
        f"- feature_source_db: `{args.feature_source_db}`",
        f"- feature_source_table: `{args.feature_source_table}`",
        "",
        "## Feature Source Table",
        "",
        f"- feature_source_table_allowlisted: `{bool_text(bool(metadata['feature_source_table_allowlisted']))}`",
        f"- row_count_for_scope: `{metadata['freshness']['row_count_for_scope']}`",
        f"- symbol_filter_applied: `{bool_text(bool(metadata['freshness']['symbol_filter_applied']))}`",
        f"- timeframe_filter_applied: `{bool_text(bool(metadata['freshness']['timeframe_filter_applied']))}`",
        "",
        "## Freshness",
        "",
        f"- earliest_time_server: `{metadata['earliest_time_server']}`",
        f"- latest_time_server: `{metadata['latest_time_server']}`",
        f"- current_timestamp_utc: `{metadata['current_timestamp_utc']}`",
        f"- staleness_hours: `{metadata['staleness_hours']}`",
        f"- max_staleness_hours: `{args.max_staleness_hours}`",
        "",
        "## Previous Paper Logger Row",
        "",
        f"- paper_logger_previous_evaluated_row_time_server: `{metadata['paper_logger_previous_evaluated_row_time_server']}`",
        f"- paper_logger_used_latest_available_row: `{metadata['paper_logger_used_latest_available_row']}`",
        "",
        "## Freshness Decision",
        "",
        f"`{decision_text}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{next_step}`",
        "",
        "Existing feature/data refresh scripts, if any, should only be considered through a separate read-only audit or manual command plan.",
        "",
        "## Warnings",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{sum(str(warning.get('blocking_warning')).lower() == 'true' for warning in warnings)}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    statuses = count_rows(rows, "readiness_status")
    stale = bool(metadata["stale"])
    recommended_next_step = (
        "manual_feature_source_refresh_required"
        if stale
        else "manual_single_shot_paper_logger_rerun_allowed"
    )
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "paper_signal_logger_readiness_dir": str(args.paper_signal_logger_readiness_dir),
        "paper_signal_logger_dir": str(args.paper_signal_logger_dir),
        "feature_source_db": str(args.feature_source_db),
        "feature_source_table": str(args.feature_source_table),
        "feature_source_table_allowlisted": bool(metadata["feature_source_table_allowlisted"]),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "max_staleness_hours": float(args.max_staleness_hours),
        "current_timestamp_utc": metadata["current_timestamp_utc"],
        "earliest_time_server": metadata["earliest_time_server"],
        "latest_time_server": metadata["latest_time_server"],
        "row_count_for_scope": int(metadata["freshness"]["row_count_for_scope"] or 0),
        "staleness_hours": metadata["staleness_hours"],
        "stale_input_source": stale,
        "freshness_ready_for_manual_single_shot_paper_logging": bool(metadata["latest_dt"] is not None and not stale),
        "paper_logger_previous_evaluated_row_time_server": metadata["paper_logger_previous_evaluated_row_time_server"],
        "paper_logger_used_latest_available_row": metadata["paper_logger_used_latest_available_row"],
        "readiness_row_count": len(rows),
        "fresh_enough_for_manual_single_shot_paper_logging_count": statuses.get(
            "fresh_enough_for_manual_single_shot_paper_logging", 0
        ),
        "stale_input_source_count": statuses.get("stale_input_source", 0),
        "blocked_missing_required_artifact_count": statuses.get("blocked_missing_required_artifact", 0),
        "blocked_unreadable_input_count": statuses.get("blocked_unreadable_input", 0),
        "blocked_unreadable_timestamp_count": statuses.get("blocked_unreadable_timestamp", 0),
        "blocked_by_leakage_risk_count": statuses.get("blocked_by_leakage_risk", 0),
        "blocked_by_config_count": statuses.get("blocked_by_config", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "recommended_next_step": recommended_next_step,
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
    rows, warnings, metadata = build_rows(args)
    write_csv(paths["readiness"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build artifact-only freshness readiness for fixed-candidate paper signal inputs."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--paper-signal-logger-readiness-dir", type=Path, default=DEFAULT_PAPER_SIGNAL_LOGGER_READINESS_DIR)
    parser.add_argument("--paper-signal-logger-dir", type=Path, default=DEFAULT_PAPER_SIGNAL_LOGGER_DIR)
    parser.add_argument("--feature-source-db", type=Path, default=DEFAULT_FEATURE_SOURCE_DB)
    parser.add_argument("--feature-source-table", default=DEFAULT_FEATURE_SOURCE_TABLE)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--max-staleness-hours", type=float, default=DEFAULT_MAX_STALENESS_HOURS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, sqlite3.Error, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate paper input freshness readiness failed: {exc}")
        return 1
    print("Fixed-candidate paper input freshness readiness complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
