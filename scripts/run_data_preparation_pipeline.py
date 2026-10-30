"""Read-only data-preparation readiness checks for offline research artifacts."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from research_pipeline_utils import (
        PipelineCommand,
        aggregate_status,
        default_run_id,
        ensure_output_dir,
        render_command,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.research_pipeline_utils import (
        PipelineCommand,
        aggregate_status,
        default_run_id,
        ensure_output_dir,
        render_command,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = BASE_DIR / "data"
DEFAULT_DB_PATH = DEFAULT_DATA_ROOT / "trading_bot.db"
DEFAULT_CALENDAR_CSV = DEFAULT_DATA_ROOT / "economic_calendar.csv"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "data_preparation_pipeline"

MANIFEST_FILE = "data_preparation_manifest.json"
COMMAND_PLAN_FILE = "data_preparation_command_plan.csv"
STAGE_RESULTS_FILE = "data_preparation_stage_results.csv"
SUMMARY_FILE = "data_preparation_summary.csv"
REPORT_FILE = "data_preparation_report.md"
WARNINGS_FILE = "data_preparation_warnings.csv"
INPUTS_FILE = "data_preparation_inputs.csv"
ARTIFACT_INVENTORY_FILE = "data_preparation_artifact_inventory.csv"
MISSING_ARTIFACTS_FILE = "data_preparation_missing_artifacts.csv"
SCHEMA_CHECKS_FILE = "data_preparation_schema_checks.csv"

DECISION_SCOPE = "data_preparation_pipeline"
PIPELINE_SCOPE = "data_preparation_read_only_checks"

FINAL_CLASSIFICATION_DRY_RUN = "DATA_PREPARATION_PIPELINE_DRY_RUN_PLANNED"
FINAL_CLASSIFICATION_COMPLETED = "DATA_PREPARATION_PIPELINE_COMPLETED"
FINAL_CLASSIFICATION_COMPLETED_WITH_WARNINGS = "DATA_PREPARATION_PIPELINE_COMPLETED_WITH_WARNINGS"
FINAL_CLASSIFICATION_FAILED = "DATA_PREPARATION_PIPELINE_FAILED"
FINAL_CLASSIFICATION_STOPPED = "DATA_PREPARATION_PIPELINE_STOPPED"

ARTIFACTS_READY = "DATA_ARTIFACTS_READY_FOR_REVIEW"
ARTIFACTS_REVIEW_REQUIRED = "DATA_ARTIFACTS_REVIEW_REQUIRED"
ARTIFACTS_BLOCKED = "DATA_ARTIFACTS_BLOCKED_MISSING_REQUIRED_INPUTS"
ARTIFACTS_NOT_READY = "DATA_ARTIFACTS_NOT_READY"

STAGE_SPECS = (
    ("inventory_data_inputs", "Inventory configured data-preparation inputs and files."),
    ("validate_filesystem_artifacts", "Check existing filesystem artifact presence and headers."),
    ("validate_database_presence", "Check configured SQLite database presence and readability."),
    ("validate_database_schema", "Inspect expected SQLite table schemas in read-only mode."),
    ("validate_table_coverage", "Collect lightweight table counts and time ranges in read-only mode."),
    ("validate_data_preparation_readiness", "Assign research-only data artifact readiness labels."),
    ("write_consolidated_status", "Write consolidated read-only status artifacts."),
)

ARTIFACT_SUFFIXES = {".csv", ".json", ".db", ".sqlite", ".sqlite3", ".txt", ".parquet"}

CALENDAR_REQUIRED_COLUMNS = (
    "value_id",
    "event_id",
    "time_server",
    "currency",
    "event_name",
    "event_code",
    "importance",
    "impact_type",
    "actual",
    "forecast",
    "previous",
    "revised_previous",
    "period",
    "revision",
)

CORE_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "economic_events": ("value_id", "time_server", "currency", "event_name", "importance"),
    "price_bars": ("symbol", "timeframe", "time_server", "open", "high", "low", "close"),
    "price_features": ("symbol", "timeframe", "time_server"),
    "market_features": ("symbol", "timeframe", "time_server"),
}

OPTIONAL_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "ml_dataset": ("symbol", "timeframe", "time_server"),
}

FORBIDDEN_ACTIONS = [
    "live " + "trading",
    "broker " + "execution",
    "order_" + "send",
    "place_" + "order",
    "open_" + "position",
    "close_" + "position",
    "live " + "signals",
    "position " + "sizing",
    "TP/SL " + "optimization",
    "Meta" + "Trader5",
    "mt5." + "initialize",
    "copy_" + "rates",
    "import_" + "price_bars",
    "generate_" + "price_features",
    "generate_" + "market_features",
    "generate_" + "ml_dataset",
    "init_" + "database",
]

COMMAND_PLAN_FIELDNAMES = [
    "command_order",
    "stage_order",
    "stage_name",
    "command",
    "heavy",
    "required",
    "description",
    "cwd",
    "expected_outputs",
    "planned_output_dir",
]

STAGE_RESULTS_FIELDNAMES = [
    "command_order",
    "stage_order",
    "stage_name",
    "status",
    "planned",
    "executed",
    "skipped",
    "failed",
    "required",
    "returncode",
    "started_at",
    "finished_at",
    "duration_seconds",
    "error_message",
    "stdout_log",
    "stderr_log",
]

SUMMARY_FIELDNAMES = [
    "run_id",
    "final_classification",
    "decision_scope",
    "pipeline_scope",
    "artifact_readiness_label",
    "dry_run",
    "execute",
    "planned_stage_count",
    "executed_stage_count",
    "skipped_stage_count",
    "failed_stage_count",
    "input_root_count",
    "inventoried_artifact_count",
    "missing_artifact_count",
    "schema_check_count",
    "warnings_count",
    "blocking_warnings_count",
    "non_blocking_warnings_count",
    "full_inventory_performed",
    "dry_run_planning_only",
    "no_data_generation_performed",
    "no_database_mutation_performed",
    "no_mt5_import_performed",
    "no_feature_generation_performed",
    "no_model_training_performed",
    "no_candidate_quality_evaluation_performed",
    "no_trading_decision_performed",
    "forbidden_actions",
    "next_action",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "blocking",
    "message",
    "related_stage",
    "related_artifact",
    "metric_value",
]

INPUT_FIELDNAMES = [
    "input_type",
    "enabled",
    "required",
    "path",
    "exists",
    "status",
    "artifact_count",
    "notes",
]

ARTIFACT_INVENTORY_FIELDNAMES = [
    "input_type",
    "path",
    "relative_path",
    "suffix",
    "size_bytes",
]

MISSING_ARTIFACT_FIELDNAMES = [
    "artifact_type",
    "name",
    "path",
    "required",
    "blocking",
    "notes",
]

SCHEMA_CHECK_FIELDNAMES = [
    "check_type",
    "object_name",
    "path",
    "table_name",
    "required",
    "blocking",
    "exists",
    "status",
    "columns",
    "missing_columns",
    "row_count",
    "min_time_server",
    "max_time_server",
    "notes",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate existing data-preparation inputs with read-only checks. "
            "Execution mode performs no data import, database mutation, or artifact generation."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--calendar-csv", type=Path, default=DEFAULT_CALENDAR_CSV)
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--timeframe", default="")
    parser.add_argument("--include-ml-dataset", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--python-executable")
    parser.add_argument("--stop-on-failure", action=argparse.BooleanOptionalAction, default=True)
    return parser


def _bool_text(value: object) -> str:
    return str(bool(value)).lower()


def _write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
    *,
    overwrite: bool,
) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"CSV already exists; pass --overwrite to replace it: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return path


def _warning_row(
    *,
    warning_code: str,
    severity: str,
    blocking: bool,
    message: str,
    related_stage: str = "",
    related_artifact: str = "",
    metric_value: object = "",
) -> dict[str, object]:
    if severity not in {"info", "review", "blocking"}:
        raise ValueError(f"Unsupported warning severity: {severity}")
    return {
        "warning_code": warning_code,
        "severity": severity,
        "blocking": _bool_text(blocking),
        "message": message,
        "related_stage": related_stage,
        "related_artifact": related_artifact,
        "metric_value": metric_value,
    }


def _is_blocking(row: Mapping[str, object]) -> bool:
    return str(row.get("blocking") or "").strip().lower() in {"true", "1", "yes"}


def _validate_mode(args: argparse.Namespace) -> None:
    if bool(args.dry_run) == bool(args.execute):
        if args.dry_run:
            raise ValueError("Choose only one of --dry-run or --execute.")
        raise ValueError("Choose either --dry-run or --execute.")


def _resolve_run_id(value: str | None) -> str:
    run_id = str(value or "").strip() or default_run_id()
    if "/" in run_id or "\\" in run_id:
        raise ValueError("--run-id must be a single path segment, not a nested path.")
    return run_id


def _normalize_symbols(values: Sequence[object] | None) -> set[str]:
    symbols: set[str] = set()
    for value in values or []:
        for token in str(value).split(","):
            symbol = token.strip().upper()
            if symbol:
                symbols.add(symbol)
    return symbols


def build_pipeline_paths(args: argparse.Namespace, run_id: str) -> dict[str, Path]:
    output_dir = Path(args.output_root) / run_id
    return {
        "output_dir": output_dir,
        "manifest": output_dir / MANIFEST_FILE,
        "command_plan": output_dir / COMMAND_PLAN_FILE,
        "stage_results": output_dir / STAGE_RESULTS_FILE,
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "inputs": output_dir / INPUTS_FILE,
        "artifact_inventory": output_dir / ARTIFACT_INVENTORY_FILE,
        "missing_artifacts": output_dir / MISSING_ARTIFACTS_FILE,
        "schema_checks": output_dir / SCHEMA_CHECKS_FILE,
    }


def _stage_order(stage_name: str) -> int:
    for index, (stage, _description) in enumerate(STAGE_SPECS, start=1):
        if stage_name == stage:
            return index
    raise ValueError(f"Unknown data-preparation pipeline stage: {stage_name}")


def build_stage_commands(paths: Mapping[str, Path]) -> list[PipelineCommand]:
    stage_outputs = {
        "inventory_data_inputs": (paths["inputs"], paths["artifact_inventory"]),
        "validate_filesystem_artifacts": (paths["missing_artifacts"], paths["schema_checks"]),
        "validate_database_presence": (paths["missing_artifacts"], paths["schema_checks"]),
        "validate_database_schema": (paths["schema_checks"],),
        "validate_table_coverage": (paths["schema_checks"],),
        "validate_data_preparation_readiness": (paths["warnings"], paths["summary"]),
        "write_consolidated_status": (paths["summary"], paths["report"], paths["warnings"]),
    }
    return [
        PipelineCommand(
            stage=stage_name,
            args=["internal", stage_name],
            cwd=BASE_DIR,
            expected_outputs=stage_outputs[stage_name],
            heavy=False,
            required=True,
            description=description,
        )
        for stage_name, description in STAGE_SPECS
    ]


def _command_plan_row_builder() -> Any:
    def row_builder(index: int, command: PipelineCommand) -> dict[str, object]:
        return {
            "command_order": index,
            "stage_order": _stage_order(command.stage),
            "stage_name": command.stage,
            "planned_output_dir": str(command.expected_outputs[0].parent if command.expected_outputs else ""),
        }

    return row_builder


def _planned_command_rows(commands: Sequence[PipelineCommand]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, command in enumerate(commands, start=1):
        rows.append(
            {
                "command_order": index,
                "stage_order": _stage_order(command.stage),
                "stage_name": command.stage,
                "command": render_command(command),
                "heavy": bool(command.heavy),
                "required": bool(command.required),
                "description": command.description,
                "cwd": str(command.cwd or ""),
                "expected_outputs": [str(path) for path in command.expected_outputs],
                "planned_output_dir": str(command.expected_outputs[0].parent if command.expected_outputs else ""),
            }
        )
    return rows


def _stage_result_row(
    *,
    index: int,
    command: PipelineCommand,
    status: str,
    started_at: str = "",
    finished_at: str = "",
    duration_seconds: float | str = "",
    returncode: int | str = "",
    error_message: str = "",
) -> dict[str, object]:
    return {
        "command_order": index,
        "stage_order": _stage_order(command.stage),
        "stage_name": command.stage,
        "status": status,
        "planned": "true",
        "executed": _bool_text(status == "executed"),
        "skipped": _bool_text(status == "skipped"),
        "failed": _bool_text(status == "failed"),
        "required": _bool_text(command.required),
        "returncode": returncode,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "error_message": error_message,
        "stdout_log": "",
        "stderr_log": "",
    }


def _planned_stage_results(commands: Sequence[PipelineCommand]) -> list[dict[str, object]]:
    return [
        _stage_result_row(index=index, command=command, status="planned")
        for index, command in enumerate(commands, start=1)
    ]


def _executed_stage_results(commands: Sequence[PipelineCommand]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, command in enumerate(commands, start=1):
        started_at = utc_now_iso()
        started = time.perf_counter()
        finished_at = utc_now_iso()
        rows.append(
            _stage_result_row(
                index=index,
                command=command,
                status="executed",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=round(time.perf_counter() - started, 6),
                returncode=0,
            )
        )
    return rows


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _path_status(path: Path, *, expected_kind: str) -> str:
    if not _path_exists(path):
        return "missing"
    if expected_kind == "dir" and not path.is_dir():
        return "not_a_directory"
    if expected_kind == "file" and not path.is_file():
        return "not_a_file"
    return "present"


def _input_rows(args: argparse.Namespace, artifact_rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    data_root = Path(args.data_root)
    db_path = Path(args.db_path)
    calendar_csv = Path(args.calendar_csv)
    artifact_count = sum(1 for row in artifact_rows if row.get("input_type") == "data_root")
    return [
        {
            "input_type": "data_root",
            "enabled": "true",
            "required": "true",
            "path": str(data_root),
            "exists": _bool_text(_path_exists(data_root) and data_root.is_dir()),
            "status": _path_status(data_root, expected_kind="dir"),
            "artifact_count": artifact_count,
            "notes": "Existing data-preparation artifact root.",
        },
        {
            "input_type": "db_path",
            "enabled": "true",
            "required": "true",
            "path": str(db_path),
            "exists": _bool_text(_path_exists(db_path) and db_path.is_file()),
            "status": _path_status(db_path, expected_kind="file"),
            "artifact_count": 1 if _path_exists(db_path) and db_path.is_file() else 0,
            "notes": "SQLite database inspected in read-only mode when present.",
        },
        {
            "input_type": "calendar_csv",
            "enabled": "true",
            "required": "false",
            "path": str(calendar_csv),
            "exists": _bool_text(_path_exists(calendar_csv) and calendar_csv.is_file()),
            "status": _path_status(calendar_csv, expected_kind="file"),
            "artifact_count": 1 if _path_exists(calendar_csv) and calendar_csv.is_file() else 0,
            "notes": "Calendar CSV header inspected only when present.",
        },
        {
            "input_type": "ml_dataset_table",
            "enabled": _bool_text(args.include_ml_dataset),
            "required": "false",
            "path": str(db_path),
            "exists": _bool_text(_path_exists(db_path) and db_path.is_file()),
            "status": "enabled" if args.include_ml_dataset else "disabled",
            "artifact_count": "",
            "notes": "Optional table schema check controlled by --include-ml-dataset.",
        },
    ]


def _artifact_inventory_rows(args: argparse.Namespace) -> list[dict[str, object]]:
    data_root = Path(args.data_root)
    rows: list[dict[str, object]] = []
    if not data_root.exists() or not data_root.is_dir():
        return rows
    for path in sorted(data_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ARTIFACT_SUFFIXES:
            continue
        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = ""
        try:
            relative_path = str(path.relative_to(data_root))
        except ValueError:
            relative_path = path.name
        rows.append(
            {
                "input_type": "data_root",
                "path": str(path),
                "relative_path": relative_path,
                "suffix": path.suffix.lower(),
                "size_bytes": size_bytes,
            }
        )
    return rows


def _missing_artifact_rows(args: argparse.Namespace, schema_rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    data_root = Path(args.data_root)
    db_path = Path(args.db_path)
    calendar_csv = Path(args.calendar_csv)
    rows: list[dict[str, object]] = []
    if not data_root.exists() or not data_root.is_dir():
        rows.append(
            {
                "artifact_type": "input_root",
                "name": "data_root",
                "path": str(data_root),
                "required": "true",
                "blocking": "true",
                "notes": "Required data root is missing or is not a directory.",
            }
        )
    if not db_path.exists() or not db_path.is_file():
        rows.append(
            {
                "artifact_type": "sqlite_database",
                "name": "db_path",
                "path": str(db_path),
                "required": "true",
                "blocking": "true",
                "notes": "Required SQLite database is missing or is not a file.",
            }
        )
    if not calendar_csv.exists() or not calendar_csv.is_file():
        rows.append(
            {
                "artifact_type": "calendar_csv",
                "name": "calendar_csv",
                "path": str(calendar_csv),
                "required": "false",
                "blocking": "false",
                "notes": "Optional calendar CSV is missing; no import or generation was attempted.",
            }
        )
    for row in schema_rows:
        if str(row.get("check_type") or "") != "sqlite_table_schema":
            continue
        if str(row.get("exists") or "").lower() == "true":
            continue
        rows.append(
            {
                "artifact_type": "database_table",
                "name": row.get("table_name") or row.get("object_name") or "",
                "path": str(db_path),
                "required": row.get("required", ""),
                "blocking": row.get("blocking", ""),
                "notes": row.get("notes", ""),
            }
        )
    return rows


def _read_csv_header(path: Path) -> tuple[list[str], str]:
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    for encoding in encodings:
        try:
            with path.open("r", newline="", encoding=encoding) as handle:
                sample = handle.read(4096)
                handle.seek(0)
                delimiter = ","
                if sample.strip():
                    try:
                        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
                        if dialect.delimiter in {",", ";"}:
                            delimiter = dialect.delimiter
                    except csv.Error:
                        delimiter = ","
                reader = csv.reader(handle, delimiter=delimiter)
                return next(reader, []), encoding
        except UnicodeDecodeError:
            continue
        except (OSError, csv.Error):
            return [], "unreadable"
    return [], "undecodable"


def _csv_schema_check(path: Path, *, required_columns: Sequence[str]) -> dict[str, object]:
    if not path.exists() or not path.is_file():
        return {
            "check_type": "csv_header",
            "object_name": "calendar_csv",
            "path": str(path),
            "table_name": "",
            "required": "false",
            "blocking": "false",
            "exists": "false",
            "status": "missing",
            "columns": "",
            "missing_columns": ",".join(required_columns),
            "row_count": "",
            "min_time_server": "",
            "max_time_server": "",
            "notes": "Calendar CSV was not present; header was not inspected.",
        }
    columns, encoding = _read_csv_header(path)
    missing_columns = [column for column in required_columns if column not in columns]
    if not columns:
        status = "empty_header"
    elif missing_columns:
        status = "missing_columns"
    else:
        status = "ok"
    return {
        "check_type": "csv_header",
        "object_name": "calendar_csv",
        "path": str(path),
        "table_name": "",
        "required": "false",
        "blocking": "false",
        "exists": "true",
        "status": status,
        "columns": ",".join(columns),
        "missing_columns": ",".join(missing_columns),
        "row_count": "",
        "min_time_server": "",
        "max_time_server": "",
        "notes": f"Header read with {encoding}; values were not interpreted.",
    }


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _open_read_only(db_path: Path) -> sqlite3.Connection:
    uri = db_path.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    cursor = connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")
    return [str(row[1]) for row in cursor.fetchall()]


def _table_coverage(connection: sqlite3.Connection, table_name: str, columns: Sequence[str]) -> tuple[object, object, object]:
    quoted = _quote_identifier(table_name)
    count = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
    min_time = ""
    max_time = ""
    if "time_server" in columns:
        min_time, max_time = connection.execute(f"SELECT MIN(time_server), MAX(time_server) FROM {quoted}").fetchone()
    return count, min_time or "", max_time or ""


def _database_schema_rows(args: argparse.Namespace) -> tuple[list[dict[str, object]], str]:
    db_path = Path(args.db_path)
    rows: list[dict[str, object]] = []
    if not db_path.exists() or not db_path.is_file():
        rows.append(
            {
                "check_type": "sqlite_database",
                "object_name": "db_path",
                "path": str(db_path),
                "table_name": "",
                "required": "true",
                "blocking": "true",
                "exists": "false",
                "status": "missing",
                "columns": "",
                "missing_columns": "",
                "row_count": "",
                "min_time_server": "",
                "max_time_server": "",
                "notes": "SQLite database was not present; no read-only open was attempted.",
            }
        )
        return rows, "missing"

    try:
        with _open_read_only(db_path) as connection:
            table_names = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
                ).fetchall()
            }
            rows.append(
                {
                    "check_type": "sqlite_database",
                    "object_name": "db_path",
                    "path": str(db_path),
                    "table_name": "",
                    "required": "true",
                    "blocking": "true",
                    "exists": "true",
                    "status": "readable",
                    "columns": ",".join(sorted(table_names)),
                    "missing_columns": "",
                    "row_count": "",
                    "min_time_server": "",
                    "max_time_server": "",
                    "notes": "SQLite database opened with read-only URI.",
                }
            )
            expected_tables: dict[str, tuple[tuple[str, ...], bool]] = {
                table_name: (columns, True)
                for table_name, columns in CORE_TABLE_COLUMNS.items()
            }
            if args.include_ml_dataset:
                expected_tables.update(
                    {
                        table_name: (columns, False)
                        for table_name, columns in OPTIONAL_TABLE_COLUMNS.items()
                    }
                )
            for table_name, (required_columns, required) in expected_tables.items():
                exists = table_name in table_names
                columns = _table_columns(connection, table_name) if exists else []
                missing_columns = [column for column in required_columns if column not in columns]
                blocking = bool(required) and (not exists or bool(missing_columns))
                status = "missing" if not exists else ("missing_columns" if missing_columns else "ok")
                rows.append(
                    {
                        "check_type": "sqlite_table_schema",
                        "object_name": table_name,
                        "path": str(db_path),
                        "table_name": table_name,
                        "required": _bool_text(required),
                        "blocking": _bool_text(blocking),
                        "exists": _bool_text(exists),
                        "status": status,
                        "columns": ",".join(columns),
                        "missing_columns": ",".join(missing_columns),
                        "row_count": "",
                        "min_time_server": "",
                        "max_time_server": "",
                        "notes": "Table schema inspected only; values were not interpreted.",
                    }
                )
                if exists:
                    try:
                        row_count, min_time, max_time = _table_coverage(connection, table_name, columns)
                        coverage_status = "ok"
                        coverage_notes = "Lightweight row count and time range only."
                    except sqlite3.Error as exc:
                        row_count, min_time, max_time = "", "", ""
                        coverage_status = "coverage_unavailable"
                        coverage_notes = f"Coverage query failed: {exc}"
                    rows.append(
                        {
                            "check_type": "sqlite_table_coverage",
                            "object_name": table_name,
                            "path": str(db_path),
                            "table_name": table_name,
                            "required": _bool_text(required),
                            "blocking": "false",
                            "exists": "true",
                            "status": coverage_status,
                            "columns": ",".join(columns),
                            "missing_columns": "",
                            "row_count": row_count,
                            "min_time_server": min_time,
                            "max_time_server": max_time,
                            "notes": coverage_notes,
                        }
                    )
        return rows, "readable"
    except sqlite3.Error as exc:
        rows.append(
            {
                "check_type": "sqlite_database",
                "object_name": "db_path",
                "path": str(db_path),
                "table_name": "",
                "required": "true",
                "blocking": "true",
                "exists": "true",
                "status": "read_only_open_failed",
                "columns": "",
                "missing_columns": "",
                "row_count": "",
                "min_time_server": "",
                "max_time_server": "",
                "notes": f"Read-only SQLite open failed: {exc}",
            }
        )
        return rows, "read_only_open_failed"


def _schema_check_rows(args: argparse.Namespace) -> tuple[list[dict[str, object]], str]:
    rows = [_csv_schema_check(Path(args.calendar_csv), required_columns=CALENDAR_REQUIRED_COLUMNS)]
    database_rows, database_status = _database_schema_rows(args)
    rows.extend(database_rows)
    return rows, database_status


def _warning_rows(
    *,
    input_rows: Sequence[Mapping[str, object]],
    missing_rows: Sequence[Mapping[str, object]],
    schema_rows: Sequence[Mapping[str, object]],
    artifact_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    for row in input_rows:
        input_type = str(row.get("input_type") or "")
        status = str(row.get("status") or "")
        if input_type == "data_root" and status != "present":
            warnings.append(
                _warning_row(
                    warning_code="missing_required_input_root",
                    severity="blocking",
                    blocking=True,
                    message="Required data root is missing or not a directory.",
                    related_stage="inventory_data_inputs",
                    related_artifact=str(row.get("path") or ""),
                    metric_value=input_type,
                )
            )
        if input_type == "db_path" and status != "present":
            warnings.append(
                _warning_row(
                    warning_code="missing_required_database",
                    severity="blocking",
                    blocking=True,
                    message="Required SQLite database is missing or not a file.",
                    related_stage="validate_database_presence",
                    related_artifact=str(row.get("path") or ""),
                    metric_value=input_type,
                )
            )
        if input_type == "calendar_csv" and status != "present":
            warnings.append(
                _warning_row(
                    warning_code="missing_optional_data_artifact",
                    severity="review",
                    blocking=False,
                    message="Calendar CSV is missing; no import or generation was attempted.",
                    related_stage="validate_filesystem_artifacts",
                    related_artifact=str(row.get("path") or ""),
                    metric_value="calendar_csv",
                )
            )
    if not artifact_rows and all(str(row.get("input_type") or "") != "data_root" or row.get("status") == "present" for row in input_rows):
        warnings.append(
            _warning_row(
                warning_code="no_data_artifacts_discovered",
                severity="review",
                blocking=False,
                message="No CSV, JSON, SQLite, text, or parquet artifacts were discovered under the data root.",
                related_stage="inventory_data_inputs",
                metric_value="data_root",
            )
        )
    for row in missing_rows:
        if str(row.get("artifact_type") or "") != "database_table":
            continue
        blocking = str(row.get("blocking") or "").lower() == "true"
        warnings.append(
            _warning_row(
                warning_code="missing_required_database_table" if blocking else "missing_optional_database_table",
                severity="blocking" if blocking else "review",
                blocking=blocking,
                message="Expected SQLite table is missing from the existing database.",
                related_stage="validate_database_schema",
                related_artifact=str(row.get("name") or ""),
                metric_value=row.get("name") or "",
            )
        )
    for row in schema_rows:
        check_type = str(row.get("check_type") or "")
        status = str(row.get("status") or "")
        if check_type == "sqlite_database" and status == "read_only_open_failed":
            warnings.append(
                _warning_row(
                    warning_code="database_read_only_open_failed",
                    severity="blocking",
                    blocking=True,
                    message="SQLite database could not be opened in read-only mode.",
                    related_stage="validate_database_presence",
                    related_artifact=str(row.get("path") or ""),
                    metric_value=status,
                )
            )
        if check_type in {"csv_header", "sqlite_table_schema"} and status in {"empty_header", "missing_columns"}:
            blocking = str(row.get("blocking") or "").lower() == "true"
            warnings.append(
                _warning_row(
                    warning_code="schema_presence_check_warning",
                    severity="blocking" if blocking else "review",
                    blocking=blocking,
                    message="A low-risk schema/header presence check needs review.",
                    related_stage="validate_database_schema" if check_type.startswith("sqlite") else "validate_filesystem_artifacts",
                    related_artifact=str(row.get("object_name") or row.get("path") or ""),
                    metric_value=status,
                )
            )
    return warnings


def _dry_run_warnings() -> list[dict[str, object]]:
    return [
        _warning_row(
            warning_code="dry_run_only_execution_not_run",
            severity="info",
            blocking=False,
            message="Dry-run mode planned internal read-only validation stages only.",
            related_stage=DECISION_SCOPE,
        ),
        _warning_row(
            warning_code="research_only_non_decision",
            severity="info",
            blocking=False,
            message="No data generation, database mutation, model training, candidate-quality evaluation, or trading decision was made.",
            related_stage=DECISION_SCOPE,
        ),
    ]


def _final_classification(*, dry_run: bool, warnings: Sequence[Mapping[str, object]]) -> str:
    if dry_run:
        return FINAL_CLASSIFICATION_DRY_RUN
    if any(_is_blocking(row) for row in warnings):
        return FINAL_CLASSIFICATION_FAILED
    if warnings:
        return FINAL_CLASSIFICATION_COMPLETED_WITH_WARNINGS
    return FINAL_CLASSIFICATION_COMPLETED


def _artifact_readiness(*, dry_run: bool, warnings: Sequence[Mapping[str, object]]) -> str:
    if dry_run:
        return ARTIFACTS_NOT_READY
    if any(_is_blocking(row) for row in warnings):
        return ARTIFACTS_BLOCKED
    non_info_warnings = [row for row in warnings if str(row.get("severity") or "") != "info"]
    if non_info_warnings:
        return ARTIFACTS_REVIEW_REQUIRED
    return ARTIFACTS_READY


def _next_action(final_classification: str) -> str:
    if final_classification == FINAL_CLASSIFICATION_DRY_RUN:
        return "Review the command plan. Re-run with --execute to write read-only inventory and check artifacts."
    if final_classification == FINAL_CLASSIFICATION_COMPLETED:
        return "Review the generated input inventory and schema checks manually."
    if final_classification == FINAL_CLASSIFICATION_COMPLETED_WITH_WARNINGS:
        return "Review missing-artifact and schema/header warnings before using the data artifact set downstream."
    if final_classification == FINAL_CLASSIFICATION_FAILED:
        return "Resolve blocking input or schema issues and rerun the read-only wrapper."
    return "Review stopped stages before rerunning."


def _warning_count(warnings: Sequence[Mapping[str, object]], *, blocking: bool | None = None) -> int:
    if blocking is None:
        return len(warnings)
    return sum(1 for row in warnings if _is_blocking(row) is blocking)


def _grouped_warning_lines(warnings: Sequence[Mapping[str, object]]) -> list[str]:
    if not warnings:
        return ["- None."]

    lines = [
        f"- total_warnings: `{_warning_count(warnings)}`",
        f"- blocking_warnings: `{_warning_count(warnings, blocking=True)}`",
        f"- non_blocking_warnings: `{_warning_count(warnings, blocking=False)}`",
    ]
    codes = sorted({str(row.get("warning_code") or "") for row in warnings})
    for code in codes:
        rows = [row for row in warnings if str(row.get("warning_code") or "") == code]
        affected = {str(row.get("related_artifact") or "") for row in rows if str(row.get("related_artifact") or "")}
        blocking_count = _warning_count(rows, blocking=True)
        lines.append(
            f"- `{code}`: `{len(rows)}` total, `{len(affected)}` artifacts/groups affected, "
            f"`{blocking_count}` blocking"
        )
        if code.startswith("missing_"):
            values = sorted({str(row.get("metric_value") or "unknown") for row in rows})
            for value in values:
                value_rows = [row for row in rows if str(row.get("metric_value") or "unknown") == value]
                lines.append(f"  - missing `{value}`: `{len(value_rows)}` total")
        elif code == "schema_presence_check_warning":
            statuses = sorted({str(row.get("metric_value") or "unknown") for row in rows})
            for status in statuses:
                status_rows = [row for row in rows if str(row.get("metric_value") or "unknown") == status]
                lines.append(f"  - status `{status}`: `{len(status_rows)}` total")
    return lines


def _write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    run_id: str,
    input_rows: Sequence[Mapping[str, object]],
    artifact_rows: Sequence[Mapping[str, object]],
    missing_rows: Sequence[Mapping[str, object]],
    schema_rows: Sequence[Mapping[str, object]],
    warnings: Sequence[Mapping[str, object]],
    final_classification: str,
    artifact_readiness: str,
    next_action: str,
    overwrite: bool,
) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Report already exists; pass --overwrite to replace it: {path}")
    mode_text = (
        "Dry-run mode wrote wrapper planning artifacts only."
        if args.dry_run
        else "Execution mode wrote internal read-only inventory and schema-check artifacts only."
    )
    lines = [
        "# Data Preparation Pipeline Report",
        "",
        "## Research-Only Caveat",
        (
            "This wrapper validates existing data-preparation inputs only. "
            "It did not generate data, mutate a database, import terminal data, generate features, "
            "train models, run backtests, or make candidate-quality, profitability, or trading decisions."
        ),
        "",
        "## Pipeline Scope",
        f"`{PIPELINE_SCOPE}`",
        "",
        "## Mode",
        mode_text,
        f"- full_inventory_performed: `{_bool_text(not args.dry_run)}`",
        f"- dry_run_planning_only: `{_bool_text(args.dry_run)}`",
        "",
        "## Inputs",
        f"- run_id: `{run_id}`",
        f"- data_root: `{args.data_root}`",
        f"- db_path: `{args.db_path}`",
        f"- calendar_csv: `{args.calendar_csv}`",
        f"- symbols: `{', '.join(sorted(_normalize_symbols(args.symbols)))}`",
        f"- timeframe: `{args.timeframe or ''}`",
        f"- include_ml_dataset: `{_bool_text(args.include_ml_dataset)}`",
        "",
        "## Artifact Checks",
        f"- input_root_count: `{len(input_rows)}`",
        f"- inventoried_artifact_count: `{len(artifact_rows)}`",
        f"- missing_artifact_count: `{len(missing_rows)}`",
        f"- schema_check_count: `{len(schema_rows)}`",
        "",
        "## Input Roots",
        "| Input Type | Enabled | Required | Exists | Status | Artifacts |",
        "|---|---|---|---|---|---:|",
    ]
    for row in input_rows:
        lines.append(
            f"| `{row.get('input_type')}` | {row.get('enabled')} | {row.get('required')} | "
            f"{row.get('exists')} | `{row.get('status')}` | {row.get('artifact_count')} |"
        )
    lines.extend(
        [
            "",
            "## Schema Checks",
            "Only file headers, SQLite table presence, table columns, row counts, and time ranges were checked; values were not interpreted.",
            "",
            "## Warnings",
            (
                "Missing or incomplete data-preparation artifacts indicate incomplete existing artifact sets, "
                "not permission for this wrapper to import, generate, repair, or mutate data."
            ),
        ]
    )
    lines.extend(_grouped_warning_lines(warnings))
    lines.extend(["", "Detailed row-level warnings are preserved in `data_preparation_warnings.csv`."])
    lines.extend(
        [
            "",
            "## Explicit Non-Decisions",
            "No data generation, database mutation, terminal import, feature generation, model training, candidate-quality evaluation, profitability evaluation, or trading decision was made.",
            "- no_data_generation_performed: `true`",
            "- no_database_mutation_performed: `true`",
            "- no_mt5_import_performed: `true`",
            "- no_feature_generation_performed: `true`",
            "- no_model_training_performed: `true`",
            "- no_candidate_quality_evaluation_performed: `true`",
            "- no_trading_decision_performed: `true`",
            "- no_profitability_evaluation_performed: `true`",
            "",
            "## Final Classification",
            f"`{final_classification}`",
            "",
            "## Artifact Readiness",
            f"`{artifact_readiness}`",
            "",
            "## Forbidden Actions",
        ]
    )
    for action in FORBIDDEN_ACTIONS:
        lines.append(f"- {action}")
    lines.extend(["", "## Next Action", next_action, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _empty_execute_rows() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    return [], [], [], []


def _aggregate_stage_status(stage_results: Sequence[Mapping[str, object]]) -> str:
    status_map = {
        "planned": "dry_run",
        "executed": "success",
        "skipped": "skipped",
        "failed": "failed",
    }
    results = []
    for row in stage_results:
        status = status_map.get(str(row.get("status") or ""), "skipped")
        results.append(type("StageResult", (), {"status": status})())
    return aggregate_status(results)


def run_pipeline(args: argparse.Namespace) -> dict[str, Path]:
    _validate_mode(args)
    run_id = _resolve_run_id(args.run_id)
    paths = build_pipeline_paths(args, run_id)
    ensure_output_dir(paths["output_dir"], overwrite=args.overwrite)
    commands = build_stage_commands(paths)

    if args.dry_run:
        input_rows, artifact_rows, missing_rows, schema_rows = _empty_execute_rows()
        warnings = _dry_run_warnings()
        database_status = "not_checked"
        stage_results = _planned_stage_results(commands)
    else:
        artifact_rows = _artifact_inventory_rows(args)
        input_rows = _input_rows(args, artifact_rows)
        schema_rows, database_status = _schema_check_rows(args)
        missing_rows = _missing_artifact_rows(args, schema_rows)
        warnings = _warning_rows(
            input_rows=input_rows,
            missing_rows=missing_rows,
            schema_rows=schema_rows,
            artifact_rows=artifact_rows,
        )
        stage_results = _executed_stage_results(commands)
        _write_csv(paths["inputs"], INPUT_FIELDNAMES, input_rows, overwrite=args.overwrite)
        _write_csv(paths["artifact_inventory"], ARTIFACT_INVENTORY_FIELDNAMES, artifact_rows, overwrite=args.overwrite)
        _write_csv(paths["missing_artifacts"], MISSING_ARTIFACT_FIELDNAMES, missing_rows, overwrite=args.overwrite)
        _write_csv(paths["schema_checks"], SCHEMA_CHECK_FIELDNAMES, schema_rows, overwrite=args.overwrite)

    final_classification = _final_classification(dry_run=bool(args.dry_run), warnings=warnings)
    artifact_readiness = _artifact_readiness(dry_run=bool(args.dry_run), warnings=warnings)
    next_action = _next_action(final_classification)
    aggregated_stage_status = _aggregate_stage_status(stage_results)
    output_artifacts = {
        "manifest": str(paths["manifest"]),
        "command_plan": str(paths["command_plan"]),
        "stage_results": str(paths["stage_results"]),
        "summary": str(paths["summary"]),
        "report": str(paths["report"]),
        "warnings": str(paths["warnings"]),
        "inputs": str(paths["inputs"]),
        "artifact_inventory": str(paths["artifact_inventory"]),
        "missing_artifacts": str(paths["missing_artifacts"]),
        "schema_checks": str(paths["schema_checks"]),
    }

    _write_csv(paths["warnings"], WARNING_FIELDNAMES, warnings, overwrite=args.overwrite)
    _write_csv(paths["stage_results"], STAGE_RESULTS_FIELDNAMES, stage_results, overwrite=args.overwrite)
    write_command_plan_csv(
        paths["command_plan"],
        commands,
        overwrite=args.overwrite,
        fieldnames=COMMAND_PLAN_FIELDNAMES,
        row_builder=_command_plan_row_builder(),
    )

    executed_stage_count = sum(1 for row in stage_results if row.get("executed") == "true")
    skipped_stage_count = sum(1 for row in stage_results if row.get("skipped") == "true")
    failed_stage_count = sum(1 for row in stage_results if row.get("failed") == "true")
    blocking_warnings_count = sum(1 for row in warnings if _is_blocking(row))
    _write_csv(
        paths["summary"],
        SUMMARY_FIELDNAMES,
        [
            {
                "run_id": run_id,
                "final_classification": final_classification,
                "decision_scope": DECISION_SCOPE,
                "pipeline_scope": PIPELINE_SCOPE,
                "artifact_readiness_label": artifact_readiness,
                "dry_run": _bool_text(args.dry_run),
                "execute": _bool_text(args.execute),
                "planned_stage_count": len(commands),
                "executed_stage_count": executed_stage_count,
                "skipped_stage_count": skipped_stage_count,
                "failed_stage_count": failed_stage_count,
                "input_root_count": len(input_rows),
                "inventoried_artifact_count": len(artifact_rows),
                "missing_artifact_count": len(missing_rows),
                "schema_check_count": len(schema_rows),
                "warnings_count": len(warnings),
                "blocking_warnings_count": blocking_warnings_count,
                "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
                "full_inventory_performed": _bool_text(not args.dry_run),
                "dry_run_planning_only": _bool_text(args.dry_run),
                "no_data_generation_performed": "true",
                "no_database_mutation_performed": "true",
                "no_mt5_import_performed": "true",
                "no_feature_generation_performed": "true",
                "no_model_training_performed": "true",
                "no_candidate_quality_evaluation_performed": "true",
                "no_trading_decision_performed": "true",
                "forbidden_actions": ";".join(FORBIDDEN_ACTIONS),
                "next_action": next_action,
            }
        ],
        overwrite=args.overwrite,
    )
    _write_report(
        paths["report"],
        args=args,
        run_id=run_id,
        input_rows=input_rows,
        artifact_rows=artifact_rows,
        missing_rows=missing_rows,
        schema_rows=schema_rows,
        warnings=warnings,
        final_classification=final_classification,
        artifact_readiness=artifact_readiness,
        next_action=next_action,
        overwrite=args.overwrite,
    )
    status = (
        "dry_run"
        if final_classification == FINAL_CLASSIFICATION_DRY_RUN
        else final_classification.removeprefix("DATA_PREPARATION_PIPELINE_").lower()
    )
    write_manifest(
        paths["manifest"],
        {
            "generated_at": utc_now_iso(),
            "completed_at": utc_now_iso(),
            "run_id": run_id,
            "output_dir": str(paths["output_dir"]),
            "data_root": str(Path(args.data_root)),
            "db_path": str(Path(args.db_path)),
            "calendar_csv": str(Path(args.calendar_csv)),
            "symbols": sorted(_normalize_symbols(args.symbols)),
            "timeframe": str(args.timeframe or ""),
            "include_ml_dataset": bool(args.include_ml_dataset),
            "python_executable": str(args.python_executable or ""),
            "stop_on_failure": bool(args.stop_on_failure),
            "dry_run": bool(args.dry_run),
            "execute": bool(args.execute),
            "planned_stages": [stage for stage, _description in STAGE_SPECS],
            "planned_commands": _planned_command_rows(commands),
            "stage_results": stage_results,
            "aggregated_stage_status": aggregated_stage_status,
            "status": status,
            "pipeline_scope": PIPELINE_SCOPE,
            "dry_run_planning_only": bool(args.dry_run),
            "full_inventory_performed": not bool(args.dry_run),
            "database_status": database_status,
            "artifact_readiness_label": artifact_readiness,
            "final_classification": final_classification,
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_warnings_count,
            "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
            "input_root_count": len(input_rows),
            "inventoried_artifact_count": len(artifact_rows),
            "missing_artifact_count": len(missing_rows),
            "schema_check_count": len(schema_rows),
            "output_artifacts": output_artifacts,
            "forbidden_actions": FORBIDDEN_ACTIONS,
            "no_data_generation_performed": True,
            "no_database_mutation_performed": True,
            "no_mt5_import_performed": True,
            "no_feature_generation_performed": True,
            "no_model_training_performed": True,
            "no_candidate_quality_evaluation_performed": True,
            "no_trading_decision_performed": True,
        },
        overwrite=args.overwrite,
    )
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        outputs = run_pipeline(args)
    except (FileExistsError, OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Data preparation pipeline artifacts written to {outputs['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
