from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_paper_input_freshness_readiness as freshness


FIXED_NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def demo_config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "schema_version": 1,
        "config_role": "paper_demo_strategy_config",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "paper_only": True,
        "broker_connection_allowed": False,
        "order_execution_allowed": False,
        "real_money_allowed": False,
        "candidate": {
            "symbol": "GBPUSD",
            "direction": "short",
            "timeframe": "M15",
            "target_horizon": 10,
            "target_family": "preferred_1_5atr_1atr_hit_first",
        },
        "entry_rule": {
            "regime_column": "hour_session",
            "regime_value": "Off_hours",
        },
    }
    config.update(overrides)
    return config


def write_demo_spec_dir(path: Path, *, paper_only: bool = True) -> None:
    write_csv(
        path / freshness.SPEC_CSV,
        ["spec_section", "spec_key", "spec_value"],
        [{"spec_section": "paper_execution_boundary", "spec_key": "boundary", "spec_value": "paper_only"}],
    )
    write_json(
        path / freshness.SPEC_MANIFEST,
        {
            "run_id": "fixture_demo_spec",
            "paper_only_specification": paper_only,
            "no_broker_connection_performed": True,
            "no_order_execution_performed": True,
            "no_trading_decision_performed": True,
            "warnings_count": 0,
            "blocking_warnings_count": 0,
        },
    )
    (path / freshness.SPEC_REPORT).write_text("# Demo spec\npaper/local only\n", encoding="utf-8")
    write_csv(path / freshness.SPEC_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_paper_signal_logger_readiness_dir(path: Path, *, paper_boundary: bool = True) -> None:
    write_csv(
        path / freshness.READINESS_CSV,
        ["readiness_area", "readiness_status"],
        [{"readiness_area": "future_logger", "readiness_status": "ready"}],
    )
    write_json(
        path / freshness.READINESS_MANIFEST,
        {
            "run_id": "fixture_logger_readiness",
            "paper_only_boundary_confirmed": paper_boundary,
            "blocked_missing_threshold_artifact_count": 0,
            "blocked_missing_required_column_count": 0,
            "blocked_by_config_count": 0,
            "blocked_by_leakage_risk_count": 0,
            "warnings_count": 0,
            "blocking_warnings_count": 0,
        },
    )
    (path / freshness.READINESS_REPORT).write_text("# Readiness\n", encoding="utf-8")
    write_csv(path / freshness.READINESS_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_paper_logger_dir(path: Path, evaluated_time: str) -> None:
    write_csv(
        path / freshness.PAPER_LOGGER_CSV,
        ["run_id", "time_server", "signal_state"],
        [{"run_id": "previous_logger", "time_server": evaluated_time, "signal_state": "paper_signal_skipped"}],
    )
    write_json(
        path / freshness.PAPER_LOGGER_MANIFEST,
        {
            "run_id": "previous_logger",
            "evaluated_row_time_server": evaluated_time,
            "signal_state": "paper_signal_skipped",
            "no_db_mutation_performed": True,
            "no_order_execution_performed": True,
        },
    )
    (path / freshness.PAPER_LOGGER_REPORT).write_text("# Paper logger\n", encoding="utf-8")
    write_csv(path / freshness.PAPER_LOGGER_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_feature_db(
    path: Path,
    *,
    table: str = "price_features",
    rows: list[dict[str, object]] | None = None,
    include_symbol: bool = True,
    include_timeframe: bool = True,
    include_time_server: bool = True,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    if include_time_server:
        columns.append("time_server")
    if include_symbol:
        columns.append("symbol")
    if include_timeframe:
        columns.append("timeframe")
    data = rows or [
        {
            "time_server": "2026-05-27 10:00:00",
            "symbol": "GBPUSD",
            "timeframe": "M15",
        }
    ]
    with sqlite3.connect(path) as connection:
        column_sql = ", ".join(f'"{column}" TEXT' for column in columns)
        connection.execute(f'CREATE TABLE "{table}" ({column_sql})')
        if columns:
            placeholders = ",".join("?" for _ in columns)
            column_names = ", ".join(f'"{column}"' for column in columns)
            for row in data:
                connection.execute(
                    f'INSERT INTO "{table}" ({column_names}) VALUES ({placeholders})',
                    [row.get(column) for column in columns],
                )
    return path


def make_args(
    tmp_path: Path,
    *,
    config: dict[str, object] | None = None,
    table: str = "price_features",
    db_missing: bool = False,
    rows: list[dict[str, object]] | None = None,
    include_symbol: bool = True,
    include_timeframe: bool = True,
    include_time_server: bool = True,
    paper_logger_time: str | None = None,
    max_staleness_hours: float = 24.0,
) -> object:
    spec_dir = tmp_path / "demo_spec"
    readiness_dir = tmp_path / "logger_readiness"
    paper_logger_dir = tmp_path / "paper_logger"
    write_demo_spec_dir(spec_dir)
    write_paper_signal_logger_readiness_dir(readiness_dir)
    if paper_logger_time is not None:
        write_paper_logger_dir(paper_logger_dir, paper_logger_time)
    config_path = write_json(tmp_path / "config" / "demo_strategy_config.json", config or demo_config())
    db_path = tmp_path / "db" / "trading_bot.db"
    if not db_missing:
        write_feature_db(
            db_path,
            table=table,
            rows=rows,
            include_symbol=include_symbol,
            include_timeframe=include_timeframe,
            include_time_server=include_time_server,
        )
    return freshness.build_parser().parse_args(
        [
            "--run-id",
            "unit_paper_input_freshness",
            "--demo-strategy-config",
            str(config_path),
            "--demo-strategy-spec-dir",
            str(spec_dir),
            "--paper-signal-logger-readiness-dir",
            str(readiness_dir),
            "--paper-signal-logger-dir",
            str(paper_logger_dir),
            "--feature-source-db",
            str(db_path),
            "--feature-source-table",
            table,
            "--symbol",
            "GBPUSD",
            "--timeframe",
            "M15",
            "--max-staleness-hours",
            str(max_staleness_hours),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def run_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> tuple[dict[str, Path], list[dict[str, str]], list[dict[str, str]], dict[str, object]]:
    monkeypatch.setattr(freshness, "utc_now", lambda: FIXED_NOW)
    args = make_args(tmp_path, **kwargs)
    paths = freshness.build_outputs(args)
    rows = read_csv(paths["readiness"])
    warnings = read_csv(paths["warnings"])
    manifest = read_json(paths["manifest"])
    return paths, rows, warnings, manifest


def row_by_area(rows: list[dict[str, str]], area: str) -> dict[str, str]:
    return next(row for row in rows if row["readiness_area"] == area)


def test_help_works() -> None:
    parser = freshness.build_parser()
    help_text = parser.format_help()
    assert "--feature-source-db" in help_text
    assert "--max-staleness-hours" in help_text


def test_output_artifacts_are_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths, _rows, _warnings, _manifest = run_build(tmp_path, monkeypatch)
    assert paths["readiness"].exists()
    assert paths["report"].exists()
    assert paths["warnings"].exists()
    assert paths["manifest"].exists()


def test_fresh_source_under_threshold_is_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, rows, _warnings, manifest = run_build(tmp_path, monkeypatch)
    staleness = row_by_area(rows, "staleness_check")
    assert staleness["readiness_status"] == "fresh_enough_for_manual_single_shot_paper_logging"
    assert staleness["evidence_label"] == "staleness_within_threshold"
    assert manifest["freshness_ready_for_manual_single_shot_paper_logging"] is True


def test_stale_source_over_threshold_is_marked_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, rows, warnings, manifest = run_build(
        tmp_path,
        monkeypatch,
        rows=[{"time_server": "2026-05-25 00:00:00", "symbol": "GBPUSD", "timeframe": "M15"}],
    )
    staleness = row_by_area(rows, "staleness_check")
    assert staleness["readiness_status"] == "stale_input_source"
    assert staleness["evidence_label"] == "staleness_exceeds_threshold"
    assert manifest["stale_input_source"] is True
    assert any(warning["warning_code"] == "stale_input_source" for warning in warnings)


def test_missing_db_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, rows, warnings, manifest = run_build(tmp_path, monkeypatch, db_missing=True)
    db_gate = row_by_area(rows, "feature_source_db_gate")
    assert db_gate["readiness_status"] == "blocked_missing_required_artifact"
    assert any(warning["warning_code"] == "feature_source_db_missing" for warning in warnings)
    assert manifest["blocked_missing_required_artifact_count"] >= 1


def test_ml_dataset_source_is_blocked_by_leakage_risk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, rows, warnings, manifest = run_build(tmp_path, monkeypatch, table="ml_dataset")
    table_gate = row_by_area(rows, "feature_source_table_gate")
    assert table_gate["readiness_status"] == "blocked_by_leakage_risk"
    assert any(warning["warning_code"] == "feature_source_table_leakage_risk" for warning in warnings)
    assert manifest["blocked_by_leakage_risk_count"] == 1


def test_missing_time_server_column_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, rows, warnings, manifest = run_build(tmp_path, monkeypatch, include_time_server=False)
    schema_gate = row_by_area(rows, "freshness_schema_gate")
    assert schema_gate["readiness_status"] == "blocked_by_config"
    assert any(warning["warning_code"] == "time_server_column_missing" for warning in warnings)
    assert manifest["blocked_by_config_count"] >= 1


def test_unparseable_time_server_blocks_timestamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, rows, warnings, manifest = run_build(
        tmp_path,
        monkeypatch,
        rows=[{"time_server": "not-a-date", "symbol": "GBPUSD", "timeframe": "M15"}],
    )
    latest = row_by_area(rows, "latest_time_server_check")
    assert latest["readiness_status"] == "blocked_unreadable_timestamp"
    assert any(warning["warning_code"] == "latest_time_server_unreadable" for warning in warnings)
    assert manifest["blocked_unreadable_timestamp_count"] >= 1


def test_symbol_timeframe_filters_are_applied_when_columns_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, _rows, _warnings, manifest = run_build(
        tmp_path,
        monkeypatch,
        rows=[
            {"time_server": "2026-05-27 08:00:00", "symbol": "GBPUSD", "timeframe": "M15"},
            {"time_server": "2026-05-27 11:45:00", "symbol": "EURUSD", "timeframe": "M15"},
            {"time_server": "2026-05-27 11:30:00", "symbol": "GBPUSD", "timeframe": "H1"},
        ],
    )
    assert manifest["latest_time_server"] == "2026-05-27 08:00:00"
    assert manifest["row_count_for_scope"] == 1


def test_missing_symbol_timeframe_columns_warn_without_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, _rows, warnings, manifest = run_build(
        tmp_path,
        monkeypatch,
        rows=[{"time_server": "2026-05-27 10:00:00"}],
        include_symbol=False,
        include_timeframe=False,
    )
    codes = {warning["warning_code"] for warning in warnings}
    assert "symbol_filter_unavailable" in codes
    assert "timeframe_filter_unavailable" in codes
    assert manifest["blocking_warnings_count"] == 0


def test_previous_logger_latest_row_match_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, rows, _warnings, manifest = run_build(
        tmp_path,
        monkeypatch,
        paper_logger_time="2026-05-27 10:00:00",
    )
    consistency = row_by_area(rows, "logger_latest_row_consistency_check")
    assert consistency["evidence_label"] == "logger_used_latest_available_row"
    assert manifest["paper_logger_used_latest_available_row"] is True


def test_previous_logger_older_row_warning_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, rows, warnings, manifest = run_build(
        tmp_path,
        monkeypatch,
        paper_logger_time="2026-05-27 09:45:00",
    )
    consistency = row_by_area(rows, "logger_latest_row_consistency_check")
    assert consistency["evidence_label"] == "logger_used_older_row_warning"
    assert any(warning["warning_code"] == "logger_used_older_row_warning" for warning in warnings)
    assert manifest["paper_logger_used_latest_available_row"] is False


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paths, rows, warnings, manifest = run_build(tmp_path, monkeypatch, paper_logger_time="2026-05-27 09:45:00")
    statuses = [row["readiness_status"] for row in rows]
    assert manifest["readiness_row_count"] == len(rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(
        1 for warning in warnings if warning["blocking_warning"].lower() == "true"
    )
    assert manifest["stale_input_source_count"] == statuses.count("stale_input_source")
    assert manifest["blocked_unreadable_timestamp_count"] == statuses.count("blocked_unreadable_timestamp")


def test_report_includes_no_mutation_no_execution_no_generation_caveats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, _rows, _warnings, _manifest = run_build(tmp_path, monkeypatch)
    report = paths["report"].read_text(encoding="utf-8")
    assert "No database mutation was performed." in report
    assert "No order execution was performed." in report
    assert "No data generation or feature refresh was performed." in report
    assert "No trading decision was made." in report


def test_no_db_mutation_occurs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "db" / "trading_bot.db"
    args = make_args(tmp_path, rows=[{"time_server": "2026-05-27 10:00:00", "symbol": "GBPUSD", "timeframe": "M15"}])
    monkeypatch.setattr(freshness, "utc_now", lambda: FIXED_NOW)
    freshness.build_outputs(args)
    with sqlite3.connect(db_path) as connection:
        tables = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        ]
        row_count = connection.execute('SELECT COUNT(*) FROM "price_features"').fetchone()[0]
    assert tables == ["price_features"]
    assert row_count == 1


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr(freshness, "utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr("subprocess.run", fail_if_called)
    args = make_args(tmp_path)
    freshness.build_outputs(args)
