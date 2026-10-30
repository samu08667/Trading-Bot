from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import run_fixed_candidate_paper_trade_tracker as tracker


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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
        "risk_reward": {
            "same_bar_policy": "stop_first",
        },
    }
    config.update(overrides)
    return config


def open_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "has_open_paper_trade": True,
        "open_signal_id": "fixture_open_signal",
        "entry_time_server": "2026-05-27 22:45:00",
        "entry_price": 1.34308,
        "tp_price": 1.34217475,
        "sl_price": 1.3436835,
        "bars_elapsed": 0,
        "horizon_bars": 10,
        "last_seen_time_server": "2026-05-27 22:45:00",
        "state_updated_at": "2026-05-27T19:57:49+00:00",
    }
    state.update(overrides)
    return state


def bar(time_server: str, *, high: float = 1.3434, low: float = 1.3426, close: float = 1.3430) -> dict[str, object]:
    return {
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "time_server": time_server,
        "open": 1.3431,
        "high": high,
        "low": low,
        "close": close,
    }


def no_hit_bars(count: int) -> list[dict[str, object]]:
    return [
        bar(f"2026-05-27 {23 + ((i + 1) // 4):02d}:{((i + 1) % 4) * 15:02d}:00")
        for i in range(count)
    ]


def write_spec_dir(path: Path, *, blocked: bool = False) -> None:
    write_csv(path / tracker.SPEC_CSV, ["spec_section", "spec_key"], [{"spec_section": "paper", "spec_key": "ok"}])
    write_json(
        path / tracker.SPEC_MANIFEST,
        {
            "run_id": "fixture_spec",
            "paper_only_specification": not blocked,
            "no_broker_connection_performed": True,
            "no_order_execution_performed": True,
            "no_trading_decision_performed": True,
            "warnings_count": 0,
            "blocking_warnings_count": 0,
        },
    )
    (path / tracker.SPEC_REPORT).write_text("# Spec\npaper only\n", encoding="utf-8")
    write_csv(path / tracker.SPEC_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_logger_dir(path: Path, *, blocked: bool = False) -> None:
    write_csv(
        path / tracker.PAPER_LOGGER_CSV,
        ["run_id", "time_server", "signal_state"],
        [
            {
                "run_id": "fixture_logger",
                "time_server": "2026-05-27 22:45:00",
                "signal_state": "paper_signal_opened",
            }
        ],
    )
    write_json(
        path / tracker.PAPER_LOGGER_MANIFEST,
        {
            "run_id": "fixture_logger",
            "evaluated_row_time_server": "2026-05-27 22:45:00",
            "signal_state": "paper_signal_opened",
            "signal_opened_count": 1,
            "signal_skipped_count": 0,
            "no_broker_connection_performed": not blocked,
            "no_order_execution_performed": not blocked,
            "no_db_mutation_performed": True,
        },
    )
    (path / tracker.PAPER_LOGGER_REPORT).write_text("# Paper signal logger\n", encoding="utf-8")
    write_csv(path / tracker.PAPER_LOGGER_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_feature_db(
    path: Path,
    rows: list[dict[str, object]],
    *,
    table: str = "price_features",
    missing_column: str | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["symbol", "timeframe", *tracker.REQUIRED_BAR_COLUMNS]
    if missing_column:
        columns = [column for column in columns if column != missing_column]
    with sqlite3.connect(path) as connection:
        connection.execute(
            f'CREATE TABLE "{table}" ({", ".join(f"{tracker.quote_identifier(column)} TEXT" for column in columns)})'
        )
        placeholders = ",".join("?" for _ in columns)
        column_sql = ", ".join(tracker.quote_identifier(column) for column in columns)
        for row in rows:
            connection.execute(
                f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})',
                [row.get(column) for column in columns],
            )
    return path


def make_args(
    tmp_path: Path,
    *,
    config: dict[str, object] | None = None,
    state: dict[str, object] | None = None,
    rows: list[dict[str, object]] | None = None,
    table: str = "price_features",
    missing_column: str | None = None,
    logger_blocked: bool = False,
) -> object:
    config_path = write_json(tmp_path / "config" / "demo_strategy_config.json", config or demo_config())
    spec_dir = tmp_path / "spec"
    logger_dir = tmp_path / "signal_logger"
    write_spec_dir(spec_dir)
    write_logger_dir(logger_dir, blocked=logger_blocked)
    state_path = write_json(logger_dir / "fixed_candidate_paper_signal_state.json", state or open_state())
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", rows or [], table=table, missing_column=missing_column)
    return tracker.build_parser().parse_args(
        [
            "--run-id",
            "unit_paper_trade_tracker",
            "--demo-strategy-config",
            str(config_path),
            "--demo-strategy-spec-dir",
            str(spec_dir),
            "--paper-signal-logger-dir",
            str(logger_dir),
            "--paper-signal-state-json",
            str(state_path),
            "--feature-source-db",
            str(db_path),
            "--feature-source-table",
            table,
            "--symbol",
            "GBPUSD",
            "--timeframe",
            "M15",
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        tracker.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(make_args(tmp_path, rows=[bar("2026-05-27 23:00:00")]))

    assert outputs["tracker"].exists()
    assert outputs["events"].exists()
    assert outputs["input_state_snapshot"].exists()
    assert outputs["state"].exists()
    assert outputs["state_history"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_input_state_is_copied_and_source_state_not_modified(tmp_path: Path) -> None:
    args = make_args(tmp_path, rows=[bar("2026-05-27 23:00:00")])
    source_state_text = Path(args.paper_signal_state_json).read_text(encoding="utf-8")
    outputs = tracker.build_outputs(args)

    assert outputs["input_state_snapshot"].read_text(encoding="utf-8") == source_state_text
    assert Path(args.paper_signal_state_json).read_text(encoding="utf-8") == source_state_text


def test_no_open_paper_trade_exits_cleanly(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(
        make_args(tmp_path, state=open_state(has_open_paper_trade=False), rows=[bar("2026-05-27 23:00:00")])
    )
    rows = read_csv(outputs["tracker"])
    warnings = read_csv(outputs["warnings"])
    manifest = read_json(outputs["manifest"])

    assert rows[-1]["trade_status"] == "no_open_paper_trade_to_track"
    assert any(warning["warning_code"] == "no_open_paper_trade_to_track" for warning in warnings)
    assert manifest["has_open_paper_trade_after"] is False


def test_short_tp_hit_closes_trade_with_positive_r(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(
        make_args(tmp_path, rows=[bar("2026-05-27 23:00:00", high=1.3432, low=1.3420)])
    )
    rows = read_csv(outputs["tracker"])
    state = read_json(outputs["state"])

    assert rows[-1]["trade_status"] == "paper_trade_closed_tp"
    assert rows[-1]["exit_reason"] == "paper_tp_hit"
    assert float(rows[-1]["R_multiple"]) == pytest.approx(1.5)
    assert state["has_open_paper_trade"] is False


def test_short_sl_hit_closes_trade_with_negative_r(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(
        make_args(tmp_path, rows=[bar("2026-05-27 23:00:00", high=1.3438, low=1.3425)])
    )
    rows = read_csv(outputs["tracker"])

    assert rows[-1]["trade_status"] == "paper_trade_closed_sl"
    assert rows[-1]["exit_reason"] == "paper_sl_hit"
    assert float(rows[-1]["R_multiple"]) == pytest.approx(-1.0)


def test_same_bar_tp_and_sl_applies_stop_first(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(
        make_args(tmp_path, rows=[bar("2026-05-27 23:00:00", high=1.3438, low=1.3420)])
    )
    rows = read_csv(outputs["tracker"])
    warnings = read_csv(outputs["warnings"])

    assert rows[-1]["trade_status"] == "paper_trade_closed_sl"
    assert rows[-1]["exit_reason"] == "paper_sl_hit"
    assert any(warning["warning_code"] == "same_bar_stop_first_applied" for warning in warnings)


def test_timeout_closes_at_h10_close_when_no_tp_sl_hit(tmp_path: Path) -> None:
    rows_after_entry = no_hit_bars(10)
    rows_after_entry[-1]["close"] = 1.3430
    outputs = tracker.build_outputs(make_args(tmp_path, rows=rows_after_entry))
    rows = read_csv(outputs["tracker"])
    state = read_json(outputs["state"])

    assert rows[-1]["trade_status"] == "paper_trade_closed_timeout"
    assert rows[-1]["exit_reason"] == "paper_timeout"
    assert float(rows[-1]["exit_price"]) == pytest.approx(1.3430)
    assert state["has_open_paper_trade"] is False
    assert state["bars_elapsed"] == 10


def test_fewer_than_h10_bars_keeps_trade_open(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(make_args(tmp_path, rows=no_hit_bars(3)))
    rows = read_csv(outputs["tracker"])
    state = read_json(outputs["state"])
    warnings = read_csv(outputs["warnings"])

    assert rows[-1]["trade_status"] == "paper_trade_still_open"
    assert state["has_open_paper_trade"] is True
    assert state["bars_elapsed"] == 3
    assert any(warning["warning_code"] == "insufficient_bars_for_timeout" for warning in warnings)


def test_existing_bars_before_or_equal_entry_are_ignored(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(
        make_args(
            tmp_path,
            rows=[
                bar("2026-05-27 22:30:00", high=1.3440, low=1.3420),
                bar("2026-05-27 22:45:00", high=1.3440, low=1.3420),
                bar("2026-05-27 23:00:00"),
            ],
        )
    )
    rows = read_csv(outputs["tracker"])
    manifest = read_json(outputs["manifest"])

    observed_rows = [row for row in rows if row["row_type"] == "observed_bar"]
    assert len(observed_rows) == 1
    assert observed_rows[0]["time_server"] == "2026-05-27 23:00:00"
    assert manifest["observed_bar_count"] == 1


def test_ml_dataset_source_is_blocked(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(make_args(tmp_path, table="ml_dataset", rows=[bar("2026-05-27 23:00:00")]))
    rows = read_csv(outputs["tracker"])
    warnings = read_csv(outputs["warnings"])

    assert rows[-1]["trade_status"] == "paper_trade_tracking_blocked"
    assert any(warning["warning_code"] == "feature_source_table_blocked" for warning in warnings)


def test_missing_required_state_fields_blocks_safely(tmp_path: Path) -> None:
    bad_state = open_state()
    bad_state.pop("tp_price")
    outputs = tracker.build_outputs(make_args(tmp_path, state=bad_state, rows=[bar("2026-05-27 23:00:00")]))
    rows = read_csv(outputs["tracker"])
    warnings = read_csv(outputs["warnings"])

    assert rows[-1]["trade_status"] == "paper_trade_tracking_blocked"
    assert any(warning["warning_code"] == "input_state_missing_required_field" for warning in warnings)


def test_missing_observed_bars_warns_and_keeps_open(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(make_args(tmp_path, rows=[]))
    rows = read_csv(outputs["tracker"])
    warnings = read_csv(outputs["warnings"])
    state = read_json(outputs["state"])

    assert rows[-1]["trade_status"] == "paper_trade_still_open"
    assert state["has_open_paper_trade"] is True
    assert any(warning["warning_code"] == "observed_bars_missing" for warning in warnings)


def test_manifest_counts_match_csv_warnings_and_state(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(make_args(tmp_path, rows=no_hit_bars(3)))
    rows = read_csv(outputs["tracker"])
    warnings = read_csv(outputs["warnings"])
    state = read_json(outputs["state"])
    manifest = read_json(outputs["manifest"])

    assert manifest["warning_count"] == len(warnings)
    assert manifest["blocking_warning_count"] == sum(
        1 for warning in warnings if warning["blocking_warning"].lower() == "true"
    )
    assert manifest["bars_elapsed_after"] == state["bars_elapsed"]
    assert manifest["trade_status"] == rows[-1]["trade_status"]
    assert manifest["has_open_paper_trade_after"] == state["has_open_paper_trade"]


def test_report_includes_no_connection_order_db_mutation_caveats(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(make_args(tmp_path, rows=[bar("2026-05-27 23:00:00")]))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "The paper signal logger was not executed." in report
    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No order execution was performed." in report
    assert "No database mutation was performed." in report
    assert "No trading decision was made." in report


def test_no_db_mutation_occurs(tmp_path: Path) -> None:
    args = make_args(tmp_path, rows=[bar("2026-05-27 23:00:00")])
    db_path = Path(args.feature_source_db)
    tracker.build_outputs(args)
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

    monkeypatch.setattr("subprocess.run", fail_if_called)
    tracker.build_outputs(make_args(tmp_path, rows=[bar("2026-05-27 23:00:00")]))


def test_events_jsonl_includes_expected_event_names(tmp_path: Path) -> None:
    outputs = tracker.build_outputs(make_args(tmp_path, rows=[bar("2026-05-27 23:00:00")]))
    event_names = {event["event_name"] for event in read_jsonl(outputs["events"])}

    assert "run_started" in event_names
    assert "input_state_snapshot_written" in event_names
    assert "input_validated" in event_names
    assert "observed_bars_loaded" in event_names
    assert "state_written" in event_names
    assert "run_completed" in event_names
