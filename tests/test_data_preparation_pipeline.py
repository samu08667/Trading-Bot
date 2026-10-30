from __future__ import annotations

import csv
import json
import sqlite3
import argparse
from pathlib import Path

import pytest

from scripts import run_data_preparation_pipeline as pipeline


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows or []:
            writer.writerow(row)


def make_calendar(path: Path) -> Path:
    write_csv(
        path,
        list(pipeline.CALENDAR_REQUIRED_COLUMNS),
        [
            {
                "value_id": 1,
                "event_id": 10,
                "time_server": "2024-01-01 00:00:00",
                "currency": "USD",
                "event_name": "Example",
                "event_code": "EX",
                "importance": "high",
                "impact_type": "",
                "actual": "",
                "forecast": "",
                "previous": "",
                "revised_previous": "",
                "period": "",
                "revision": "",
            }
        ],
    )
    return path


def make_database(path: Path, *, include_optional_table: bool = False, missing_core_table: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        if missing_core_table != "economic_events":
            connection.execute(
                """
                CREATE TABLE economic_events (
                    value_id INTEGER,
                    time_server TEXT,
                    currency TEXT,
                    event_name TEXT,
                    importance TEXT
                )
                """
            )
            connection.execute(
                "INSERT INTO economic_events VALUES (1, '2024-01-01 00:00:00', 'USD', 'Example', 'high')"
            )
        if missing_core_table != "price_bars":
            connection.execute(
                """
                CREATE TABLE price_bars (
                    symbol TEXT,
                    timeframe TEXT,
                    time_server TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    spread REAL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO price_bars
                VALUES ('EURUSD', 'M15', '2024-01-01 00:00:00', 1.0, 1.1, 0.9, 1.05, 10.0)
                """
            )
        if missing_core_table != "price_features":
            connection.execute(
                """
                CREATE TABLE price_features (
                    symbol TEXT,
                    timeframe TEXT,
                    time_server TEXT,
                    return_1 REAL
                )
                """
            )
            connection.execute(
                "INSERT INTO price_features VALUES ('EURUSD', 'M15', '2024-01-01 00:00:00', 0.01)"
            )
        if missing_core_table != "market_features":
            connection.execute(
                """
                CREATE TABLE market_features (
                    symbol TEXT,
                    timeframe TEXT,
                    time_server TEXT,
                    minutes_to_next_news REAL
                )
                """
            )
            connection.execute(
                "INSERT INTO market_features VALUES ('EURUSD', 'M15', '2024-01-01 00:00:00', 60.0)"
            )
        if include_optional_table:
            connection.execute(
                """
                CREATE TABLE ml_dataset (
                    symbol TEXT,
                    timeframe TEXT,
                    time_server TEXT,
                    target_long_10 INTEGER
                )
                """
            )
            connection.execute(
                "INSERT INTO ml_dataset VALUES ('EURUSD', 'M15', '2024-01-01 00:00:00', 1)"
            )
    return path


def make_data_root(
    tmp_path: Path,
    *,
    include_calendar: bool = True,
    include_database: bool = True,
    include_optional_table: bool = False,
    missing_core_table: str = "",
) -> tuple[Path, Path, Path]:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    db_path = data_root / "trading_bot.db"
    calendar_csv = data_root / "economic_calendar.csv"
    if include_database:
        make_database(db_path, include_optional_table=include_optional_table, missing_core_table=missing_core_table)
    if include_calendar:
        make_calendar(calendar_csv)
    return data_root, db_path, calendar_csv


def make_args(tmp_path: Path, data_root: Path, db_path: Path, calendar_csv: Path, *extra: str) -> argparse.Namespace:
    return pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--data-root",
            str(data_root),
            "--db-path",
            str(db_path),
            "--calendar-csv",
            str(calendar_csv),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--symbols",
            "EURUSD",
            "--timeframe",
            "M15",
            *extra,
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        pipeline.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_no_mode_selected_fails_clearly(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path)
    args = make_args(tmp_path, data_root, db_path, calendar_csv)

    with pytest.raises(ValueError, match="Choose either --dry-run or --execute"):
        pipeline.run_pipeline(args)


def test_both_modes_selected_fails_clearly(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path)
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--dry-run", "--execute")

    with pytest.raises(ValueError, match="Choose only one"):
        pipeline.run_pipeline(args)


def test_missing_data_root_creates_blocking_warning(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing_data"
    args = make_args(
        tmp_path,
        missing_root,
        missing_root / "trading_bot.db",
        missing_root / "economic_calendar.csv",
        "--execute",
    )

    outputs = pipeline.run_pipeline(args)
    summary = read_csv(outputs["summary"])[0]
    warnings = read_csv(outputs["warnings"])

    assert summary["final_classification"] == "DATA_PREPARATION_PIPELINE_FAILED"
    assert summary["artifact_readiness_label"] == "DATA_ARTIFACTS_BLOCKED_MISSING_REQUIRED_INPUTS"
    assert any(row["warning_code"] == "missing_required_input_root" and row["blocking"] == "true" for row in warnings)


def test_missing_db_path_creates_blocking_warning(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path, include_database=False)
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--execute")

    outputs = pipeline.run_pipeline(args)
    summary = read_csv(outputs["summary"])[0]
    warnings = read_csv(outputs["warnings"])

    assert summary["final_classification"] == "DATA_PREPARATION_PIPELINE_FAILED"
    assert any(row["warning_code"] == "missing_required_database" and row["blocking"] == "true" for row in warnings)


def test_missing_calendar_csv_is_non_blocking(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path, include_calendar=False)
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--execute")

    outputs = pipeline.run_pipeline(args)
    summary = read_csv(outputs["summary"])[0]
    warnings = read_csv(outputs["warnings"])

    assert summary["final_classification"] == "DATA_PREPARATION_PIPELINE_COMPLETED_WITH_WARNINGS"
    assert summary["artifact_readiness_label"] == "DATA_ARTIFACTS_REVIEW_REQUIRED"
    assert any(row["warning_code"] == "missing_optional_data_artifact" and row["blocking"] == "false" for row in warnings)


def test_dry_run_writes_required_wrapper_artifacts_without_child_scripts(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path)
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--dry-run")

    outputs = pipeline.run_pipeline(args)

    for key in ("manifest", "command_plan", "stage_results", "summary", "report", "warnings"):
        assert outputs[key].exists()
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "DATA_PREPARATION_PIPELINE_DRY_RUN_PLANNED"
    assert summary["executed_stage_count"] == "0"
    assert summary["full_inventory_performed"] == "false"
    assert not outputs["artifact_inventory"].exists()
    command_plan = read_csv(outputs["command_plan"])
    assert all(row["command"].startswith("internal ") for row in command_plan)
    assert all(".py" not in row["command"] for row in command_plan)


def test_execute_writes_required_and_consolidation_artifacts(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path)
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--execute")

    outputs = pipeline.run_pipeline(args)

    for key in (
        "manifest",
        "command_plan",
        "stage_results",
        "summary",
        "report",
        "warnings",
        "inputs",
        "artifact_inventory",
        "missing_artifacts",
        "schema_checks",
    ):
        assert outputs[key].exists()
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "DATA_PREPARATION_PIPELINE_COMPLETED"
    assert summary["artifact_readiness_label"] == "DATA_ARTIFACTS_READY_FOR_REVIEW"


def test_execute_writes_inputs_inventory_missing_and_schema_rows(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path, missing_core_table="market_features")
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--execute")

    outputs = pipeline.run_pipeline(args)

    inputs = read_csv(outputs["inputs"])
    inventory = read_csv(outputs["artifact_inventory"])
    missing = read_csv(outputs["missing_artifacts"])
    schema = read_csv(outputs["schema_checks"])

    assert any(row["input_type"] == "data_root" and row["enabled"] == "true" for row in inputs)
    assert any(row["relative_path"] == "trading_bot.db" for row in inventory)
    assert any(row["artifact_type"] == "database_table" and row["name"] == "market_features" for row in missing)
    assert any(row["check_type"] == "sqlite_table_schema" and row["table_name"] == "market_features" for row in schema)


def test_sqlite_schema_checks_are_read_only(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path)
    with sqlite3.connect(db_path) as connection:
        before_tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
        before_count = connection.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0]
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--execute")

    pipeline.run_pipeline(args)

    with sqlite3.connect(db_path) as connection:
        after_tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
        after_count = connection.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0]
    assert after_tables == before_tables
    assert after_count == before_count


def test_schema_check_csv_includes_core_table_rows(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path)
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--execute")

    outputs = pipeline.run_pipeline(args)
    schema = read_csv(outputs["schema_checks"])
    schema_tables = {
        row["table_name"]
        for row in schema
        if row["check_type"] == "sqlite_table_schema" and row["exists"] == "true"
    }

    assert set(pipeline.CORE_TABLE_COLUMNS) <= schema_tables


def test_optional_dataset_table_checks_are_covered(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path, include_optional_table=True)
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--include-ml-dataset", "--execute")

    outputs = pipeline.run_pipeline(args)
    schema = read_csv(outputs["schema_checks"])

    assert any(
        row["check_type"] == "sqlite_table_schema" and row["table_name"] == "ml_dataset" and row["status"] == "ok"
        for row in schema
    )


def test_command_plan_and_stage_results_include_command_and_stage_order(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path)
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--execute")

    outputs = pipeline.run_pipeline(args)
    command_plan = read_csv(outputs["command_plan"])
    stage_results = read_csv(outputs["stage_results"])

    assert [row["command_order"] for row in command_plan] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [row["stage_order"] for row in command_plan] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [row["command_order"] for row in stage_results] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [row["stage_order"] for row in stage_results] == ["1", "2", "3", "4", "5", "6", "7"]


def test_manifest_summary_warnings_and_report_counts_are_consistent(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path, missing_core_table="market_features")
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--execute")

    outputs = pipeline.run_pipeline(args)
    warnings = read_csv(outputs["warnings"])
    summary = read_csv(outputs["summary"])[0]
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    report = outputs["report"].read_text(encoding="utf-8")
    blocking_count = sum(row["blocking"] == "true" for row in warnings)

    assert int(summary["warnings_count"]) == len(warnings)
    assert int(summary["blocking_warnings_count"]) == blocking_count
    assert int(summary["non_blocking_warnings_count"]) == len(warnings) - blocking_count
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == blocking_count
    assert manifest["non_blocking_warnings_count"] == len(warnings) - blocking_count
    assert f"total_warnings: `{len(warnings)}`" in report
    assert f"blocking_warnings: `{blocking_count}`" in report


def test_report_and_summary_state_research_only_non_decisions(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path)
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--execute")

    outputs = pipeline.run_pipeline(args)
    report = outputs["report"].read_text(encoding="utf-8")
    summary = read_csv(outputs["summary"])[0]
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert "Research-Only Caveat" in report
    assert "did not generate data" in report
    assert "No data generation, database mutation, terminal import, feature generation, model training" in report
    assert summary["no_data_generation_performed"] == "true"
    assert summary["no_database_mutation_performed"] == "true"
    assert summary["no_feature_generation_performed"] == "true"
    assert summary["no_model_training_performed"] == "true"
    assert summary["no_candidate_quality_evaluation_performed"] == "true"
    assert summary["no_trading_decision_performed"] == "true"
    for action in pipeline.FORBIDDEN_ACTIONS:
        assert action in report
    assert manifest["pipeline_scope"] == "data_preparation_read_only_checks"
    assert manifest["no_database_mutation_performed"] is True


def test_no_child_scripts_are_planned_or_executed(tmp_path: Path) -> None:
    data_root, db_path, calendar_csv = make_data_root(tmp_path)
    args = make_args(tmp_path, data_root, db_path, calendar_csv, "--execute")

    outputs = pipeline.run_pipeline(args)

    command_plan = read_csv(outputs["command_plan"])
    assert all(row["command"].startswith("internal ") for row in command_plan)
    assert all(".py" not in row["command"] for row in command_plan)


def test_no_forbidden_runtime_logic_is_introduced() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    forbidden_terms = [
        "order_" + "send",
        "place_" + "order",
        "open_" + "position",
        "close_" + "position",
        "broker " + "execution",
        "live " + "signal",
        "position " + "sizing",
        "TP/SL " + "optimization",
        "live " + "readiness",
        "buy " + "signal",
        "sell " + "signal",
        "Meta" + "Trader5",
        "mt5." + "initialize",
        "copy_" + "rates",
        "import_" + "price_bars",
        "generate_" + "price_features",
        "generate_" + "market_features",
        "generate_" + "ml_dataset",
        "init_" + "database",
    ]

    for term in forbidden_terms:
        assert term not in source
