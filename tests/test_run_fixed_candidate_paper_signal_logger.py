from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import run_fixed_candidate_paper_signal_logger as logger


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
        "entry_rule": {
            "regime_column": "hour_session",
            "regime_value": "Off_hours",
        },
        "risk_reward": {
            "tp_atr": 1.5,
            "sl_atr": 1.0,
            "atr_column": "atr_20",
            "same_bar_policy": "stop_first",
        },
        "spread_and_session_controls": {
            "spread_threshold_note": "Skip new paper/demo signals if spread exceeds max_spread_points",
            "max_spread_points": 15.0,
            "spread_unit": "broker_points",
            "spread_policy_status": "configured_numeric_threshold",
            "spread_policy_action_when_exceeded": "skip_new_signal",
            "spread_policy_action_when_missing": "skip_new_signal",
        },
    }
    config.update(overrides)
    return config


def thresholds_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "threshold_lineage": "train_only",
        "calibration_scope": "train_window_only",
        "full_sample_thresholds_used": False,
        "oos_rows_used_for_thresholds": False,
        "features": {
            "close_to_ma_fast_atr_20": {
                "low_mid_cutoff": -0.45968425469893365,
                "mid_high_cutoff": 0.5951568132962021,
            },
            "tick_volume_percentile_100": {
                "low_mid_cutoff": 0.15,
                "mid_high_cutoff": 0.37,
            },
        },
    }


def legacy_thresholds_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "features": {
            "close_to_ma_fast_atr_20": {
                "lower_tercile_boundary": -0.45968425469893365,
                "upper_tercile_boundary": 0.5951568132962021,
            },
            "tick_volume_percentile_100": {
                "lower_tercile_boundary": 0.15,
                "upper_tercile_boundary": 0.37,
            },
        },
    }


def write_spec_dir(path: Path, *, blocked: bool = False) -> None:
    write_csv(path / logger.SPEC_CSV, ["spec_section", "spec_key"], [{"spec_section": "paper", "spec_key": "ok"}])
    write_json(
        path / logger.SPEC_MANIFEST,
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
    (path / logger.SPEC_REPORT).write_text("# Spec\npaper only\n", encoding="utf-8")
    write_csv(path / logger.SPEC_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_readiness_dir(path: Path, *, blocked: bool = False) -> None:
    write_csv(
        path / logger.READINESS_CSV,
        ["readiness_area", "readiness_status"],
        [{"readiness_area": "future_logger", "readiness_status": "ready"}],
    )
    write_json(
        path / logger.READINESS_MANIFEST,
        {
            "run_id": "fixture_readiness",
            "paper_only_boundary_confirmed": True,
            "blocked_missing_threshold_artifact_count": 0,
            "blocked_missing_required_column_count": 1 if blocked else 0,
            "blocked_by_config_count": 0,
            "blocked_by_leakage_risk_count": 0,
            "blocking_warnings_count": 1 if blocked else 0,
        },
    )
    (path / logger.READINESS_REPORT).write_text("# Readiness\n", encoding="utf-8")
    write_csv(path / logger.READINESS_WARNINGS, ["warning_code", "blocking_warning"], [])


def latest_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "time_server": "2026-05-27 10:00:00",
        "open": 1.2500,
        "high": 1.2510,
        "low": 1.2490,
        "close": 1.2500,
        "atr_20": 0.0020,
        "hour_session": "Off_hours",
        "close_to_ma_fast_atr_20": 0.75,
        "tick_volume_percentile_100": 0.20,
        "spread": 2.0,
        "spread_avg_20": 1.8,
        "tick_volume": 100,
    }
    row.update(overrides)
    return row


def write_feature_db(
    path: Path,
    *,
    table: str = "price_features",
    row: dict[str, object] | None = None,
    missing_column: str | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = row or latest_row()
    columns = list(logger.REQUIRED_ROW_COLUMNS) + ["symbol", "timeframe", "tick_volume"]
    if missing_column:
        columns = [column for column in columns if column != missing_column]
    with sqlite3.connect(path) as connection:
        connection.execute(
            f'CREATE TABLE "{table}" ({", ".join(f"{logger.quote_identifier(column)} TEXT" for column in columns)})'
        )
        placeholders = ",".join("?" for _ in columns)
        connection.execute(
            f'INSERT INTO "{table}" ({", ".join(logger.quote_identifier(column) for column in columns)}) VALUES ({placeholders})',
            [data.get(column) for column in columns],
        )
    return path


def make_args(
    tmp_path: Path,
    *,
    config: dict[str, object] | None = None,
    row: dict[str, object] | None = None,
    state: dict[str, object] | None = None,
    table: str = "price_features",
    threshold_missing: bool = False,
    threshold_text: str | None = None,
    threshold_payload: dict[str, object] | None = None,
    explicit_threshold: bool = True,
    allow_legacy: bool = False,
    readiness_blocked: bool = False,
    missing_column: str | None = None,
) -> object:
    config_path = write_json(tmp_path / "config" / "demo_strategy_config.json", config or demo_config())
    spec_dir = tmp_path / "spec"
    readiness_dir = tmp_path / "readiness"
    write_spec_dir(spec_dir)
    write_readiness_dir(readiness_dir, blocked=readiness_blocked)
    threshold_path = tmp_path / "thresholds" / "fixed_candidate_numeric_tercile_thresholds.json"
    if not threshold_missing:
        if threshold_text is not None:
            threshold_path.parent.mkdir(parents=True, exist_ok=True)
            threshold_path.write_text(threshold_text, encoding="utf-8")
        else:
            write_json(threshold_path, threshold_payload if threshold_payload is not None else thresholds_payload())
    canonical_path = write_json(
        tmp_path / "config" / "fixed_candidate_current_canonical.json",
        {
            "candidate_id": "gbpusd_short_h10_1_5_off_hours",
            "numeric_tercile_thresholds_json": str(threshold_path),
        },
    )
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", table=table, row=row, missing_column=missing_column)
    state_path = tmp_path / "state" / "paper_signal_state.json"
    if state is not None:
        write_json(state_path, state)
    argv = [
            "--run-id",
            "unit_paper_signal_logger",
            "--demo-strategy-config",
            str(config_path),
            "--demo-strategy-spec-dir",
            str(spec_dir),
            "--paper-signal-logger-readiness-dir",
            str(readiness_dir),
            "--canonical-registry",
            str(canonical_path),
            "--feature-source-db",
            str(db_path),
            "--feature-source-table",
            table,
            "--state-json",
            str(state_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    if explicit_threshold:
        argv.extend(["--tercile-thresholds-json", str(threshold_path)])
    if allow_legacy:
        argv.append("--allow-legacy-full-sample-thresholds")
    return logger.build_parser().parse_args(argv)


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        logger.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path))

    assert outputs["signal_log"].exists()
    assert outputs["events"].exists()
    assert outputs["state"].exists()
    assert outputs["state_history"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_eligible_row_opens_paper_signal(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["signal_log"])
    state = json.loads(outputs["state"].read_text(encoding="utf-8"))
    manifest = read_json(outputs["manifest"])

    assert rows[0]["signal_state"] == "paper_signal_opened"
    assert rows[0]["close_to_ma_fast_atr_20_bucket"] == "high_tercile"
    assert rows[0]["tick_volume_percentile_100_bucket"] == "mid_tercile"
    assert float(rows[0]["tp_price"]) == pytest.approx(1.247)
    assert float(rows[0]["sl_price"]) == pytest.approx(1.252)
    assert state["has_open_paper_trade"] is True
    assert manifest["threshold_lineage"] == "train_only"
    assert manifest["calibration_scope"] == "train_window_only"
    assert manifest["full_sample_thresholds_used"] is False
    assert manifest["oos_rows_used_for_thresholds"] is False
    assert manifest["threshold_schema_label"] == "train_only_low_mid_mid_high"


def test_default_threshold_path_resolves_from_canonical_registry(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, explicit_threshold=False))
    manifest = read_json(outputs["manifest"])

    assert manifest["threshold_lineage"] == "train_only"
    assert manifest["numeric_tercile_thresholds_json"].endswith("fixed_candidate_numeric_tercile_thresholds.json")


def test_legacy_full_sample_thresholds_rejected_by_default(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, threshold_payload=legacy_thresholds_payload()))
    rows = read_csv(outputs["signal_log"])
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert rows[0]["signal_state"] == "paper_signal_blocked"
    assert manifest["threshold_schema_label"] == "legacy_full_sample_lower_upper"
    assert manifest["legacy_full_sample_thresholds_allowed"] is False
    assert any(row["warning_code"] == "threshold_artifact_unreadable" for row in warnings)


def test_legacy_full_sample_thresholds_allowed_only_with_explicit_flag(tmp_path: Path) -> None:
    outputs = logger.build_outputs(
        make_args(tmp_path, threshold_payload=legacy_thresholds_payload(), allow_legacy=True)
    )
    rows = read_csv(outputs["signal_log"])
    manifest = read_json(outputs["manifest"])

    assert rows[0]["signal_state"] == "paper_signal_opened"
    assert manifest["threshold_schema_label"] == "legacy_full_sample_lower_upper"
    assert manifest["legacy_full_sample_thresholds_allowed"] is True


def test_ineligible_close_to_ma_bucket_skips_signal(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, row=latest_row(close_to_ma_fast_atr_20=0.10)))
    row = read_csv(outputs["signal_log"])[0]

    assert row["signal_state"] == "paper_signal_skipped"
    assert "close_to_ma_fast_atr_20_bucket_mismatch" in row["skip_reasons"]


def test_ineligible_tick_volume_bucket_skips_signal(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, row=latest_row(tick_volume_percentile_100=0.80)))
    row = read_csv(outputs["signal_log"])[0]

    assert row["signal_state"] == "paper_signal_skipped"
    assert "tick_volume_percentile_100_bucket_mismatch" in row["skip_reasons"]


def test_session_mismatch_skips_signal(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, row=latest_row(hour_session="London")))
    row = read_csv(outputs["signal_log"])[0]

    assert row["signal_state"] == "paper_signal_skipped"
    assert "session_mismatch" in row["skip_reasons"]


def test_spread_above_threshold_skips_signal(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, row=latest_row(spread=20.0)))
    row = read_csv(outputs["signal_log"])[0]

    assert row["signal_state"] == "paper_signal_skipped"
    assert "spread_above_threshold" in row["skip_reasons"]


def test_missing_spread_skips_signal(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, row=latest_row(spread=None)))
    row = read_csv(outputs["signal_log"])[0]

    assert row["signal_state"] == "paper_signal_skipped"
    assert "spread_missing_or_unreadable" in row["skip_reasons"]


def test_existing_open_state_skips_new_signal(tmp_path: Path) -> None:
    outputs = logger.build_outputs(
        make_args(
            tmp_path,
            state={
                "has_open_paper_trade": True,
                "open_signal_id": "existing",
                "entry_time_server": "2026-05-27 09:45:00",
                "last_seen_time_server": "2026-05-27 09:45:00",
                "bars_elapsed": 0,
                "horizon_bars": 10,
            },
        )
    )
    row = read_csv(outputs["signal_log"])[0]

    assert row["signal_state"] == "paper_signal_skipped"
    assert "existing_paper_demo_trade_open" in row["skip_reasons"]


def test_ml_dataset_source_is_blocked(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, table="ml_dataset"))
    row = read_csv(outputs["signal_log"])[0]
    warnings = read_csv(outputs["warnings"])

    assert row["signal_state"] == "paper_signal_blocked"
    assert any(warning["warning_code"] == "feature_source_table_leakage_risk" for warning in warnings)


def test_threshold_json_missing_blocks_safely(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, threshold_missing=True))
    row = read_csv(outputs["signal_log"])[0]
    warnings = read_csv(outputs["warnings"])

    assert row["signal_state"] == "paper_signal_blocked"
    assert any(warning["warning_code"] == "threshold_artifact_missing" for warning in warnings)


def test_threshold_json_unreadable_blocks_safely(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, threshold_text="{not-json"))
    row = read_csv(outputs["signal_log"])[0]
    warnings = read_csv(outputs["warnings"])

    assert row["signal_state"] == "paper_signal_blocked"
    assert any(warning["warning_code"] == "threshold_artifact_unreadable" for warning in warnings)


def test_readiness_blocker_blocks_safely(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, readiness_blocked=True))
    row = read_csv(outputs["signal_log"])[0]
    warnings = read_csv(outputs["warnings"])

    assert row["signal_state"] == "paper_signal_blocked"
    assert any(warning["warning_code"] == "paper_signal_logger_readiness_blocker_present" for warning in warnings)


def test_missing_required_row_column_blocks_safely(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path, missing_column="atr_20"))
    row = read_csv(outputs["signal_log"])[0]
    warnings = read_csv(outputs["warnings"])

    assert row["signal_state"] == "paper_signal_blocked"
    assert any(warning["warning_code"] == "required_feature_missing" for warning in warnings)


def test_state_json_written_and_no_db_mutation_occurs(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    db_path = Path(args.feature_source_db)
    outputs = logger.build_outputs(args)

    assert outputs["state"].exists()
    with sqlite3.connect(db_path) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
    assert tables == ["price_features"]


def test_events_jsonl_includes_expected_event_names(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path))
    events = read_jsonl(outputs["events"])
    names = [str(event["event_name"]) for event in events]

    assert "run_started" in names
    assert "input_validated" in names
    assert "latest_row_loaded" in names
    assert "gates_evaluated" in names
    assert "signal_logged" in names
    assert "state_written" in names
    assert "run_completed" in names


def test_manifest_counts_match_logs_and_warnings(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["signal_log"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert len(rows) == 1
    assert manifest["signal_opened_count"] == sum(row["signal_state"] == "paper_signal_opened" for row in rows)
    assert manifest["signal_skipped_count"] == sum(
        row["signal_state"] in {"paper_signal_skipped", "paper_signal_blocked"} for row in rows
    )
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_paper_runner_loop_executed"] is True
    assert manifest["no_db_mutation_performed"] is True
    assert manifest["no_data_generation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_no_external_no_order_and_no_db_mutation_caveats(tmp_path: Path) -> None:
    outputs = logger.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Single-shot local paper logger artifact" in report
    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No order execution was performed." in report
    assert "No database mutation was performed." in report
    assert "No trading decision was made." in report


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    logger.build_outputs(make_args(tmp_path))
