from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import run_fixed_candidate_fixed_rule_replay_backtest as replay


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
            "max_spread_points": 15.0,
            "spread_unit": "broker_points",
        },
    }
    config.update(overrides)
    return config


def write_spec_dir(path: Path) -> None:
    write_csv(path / replay.SPEC_CSV, ["spec_section", "spec_key"], [{"spec_section": "paper", "spec_key": "ok"}])
    write_json(
        path / replay.SPEC_MANIFEST,
        {
            "paper_only_specification": True,
            "warnings_count": 0,
            "blocking_warnings_count": 0,
        },
    )
    (path / replay.SPEC_REPORT).write_text("# Spec\n", encoding="utf-8")
    write_csv(path / replay.SPEC_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_readiness_dir(path: Path) -> None:
    write_csv(
        path / replay.READINESS_CSV,
        ["readiness_area", "readiness_status"],
        [{"readiness_area": "paper_boundary", "readiness_status": "ready"}],
    )
    write_json(
        path / replay.READINESS_MANIFEST,
        {
            "paper_only_boundary_confirmed": True,
            "blocked_missing_threshold_artifact_count": 0,
            "blocked_missing_required_column_count": 0,
            "blocked_by_config_count": 0,
            "blocked_by_leakage_risk_count": 0,
            "blocking_warnings_count": 0,
            "warnings_count": 0,
        },
    )
    (path / replay.READINESS_REPORT).write_text("# Readiness\n", encoding="utf-8")
    write_csv(path / replay.READINESS_WARNINGS, ["warning_code", "blocking_warning"], [])


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
                "low_mid_cutoff": -0.45,
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
                "lower_tercile_boundary": -0.45,
                "upper_tercile_boundary": 0.5951568132962021,
            },
            "tick_volume_percentile_100": {
                "lower_tercile_boundary": 0.15,
                "upper_tercile_boundary": 0.37,
            },
        },
    }


def bar(time_server: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "time_server": time_server,
        "open": 1.2500,
        "high": 1.2510,
        "low": 1.2480,
        "close": 1.2500,
        "spread": 2.0,
        "spread_avg_20": 1.8,
        "atr_20": 0.0020,
        "hour_session": "Off_hours",
        "close_to_ma_fast_atr_20": 0.75,
        "tick_volume_percentile_100": 0.20,
        "future_target_R": 999,
    }
    row.update(overrides)
    return row


def no_hit_bars(start_hour: int = 1, count: int = 10) -> list[dict[str, object]]:
    return [
        bar(
            f"2026-05-28 {start_hour + (i // 4):02d}:{(i % 4) * 15:02d}:00",
            high=1.2510,
            low=1.2480,
            close=1.2495,
        )
        for i in range(count)
    ]


def write_feature_db(
    path: Path,
    rows: list[dict[str, object]],
    *,
    table: str = "price_features",
    missing_column: str | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [*replay.REQUIRED_SOURCE_COLUMNS, "future_target_R"]
    if missing_column:
        columns = [column for column in columns if column != missing_column]
    with sqlite3.connect(path) as connection:
        connection.execute(
            f'CREATE TABLE "{table}" ({", ".join(f"{replay.quote_identifier(column)} TEXT" for column in columns)})'
        )
        placeholders = ",".join("?" for _ in columns)
        column_sql = ", ".join(replay.quote_identifier(column) for column in columns)
        for row in rows:
            connection.execute(
                f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})',
                [row.get(column) for column in columns],
            )
    return path


def make_args(
    tmp_path: Path,
    rows: list[dict[str, object]],
    *,
    table: str = "price_features",
    missing_column: str | None = None,
    max_bars: int = 50000,
    threshold_payload: dict[str, object] | None = None,
    explicit_threshold: bool = True,
    allow_legacy: bool = False,
) -> object:
    config_path = write_json(tmp_path / "config" / "demo_config.json", demo_config())
    spec_dir = tmp_path / "spec"
    readiness_dir = tmp_path / "readiness"
    thresholds_path = write_json(
        tmp_path / "thresholds" / "fixed_candidate_numeric_tercile_thresholds.json",
        threshold_payload if threshold_payload is not None else thresholds_payload(),
    )
    canonical_path = write_json(
        tmp_path / "config" / "fixed_candidate_current_canonical.json",
        {
            "candidate_id": "gbpusd_short_h10_1_5_off_hours",
            "numeric_tercile_thresholds_json": str(thresholds_path),
        },
    )
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", rows, table=table, missing_column=missing_column)
    write_spec_dir(spec_dir)
    write_readiness_dir(readiness_dir)
    argv = [
            "--run-id",
            "unit_fixed_rule_replay",
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
            "--symbol",
            "GBPUSD",
            "--timeframe",
            "M15",
            "--max-bars",
            str(max_bars),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    if explicit_threshold:
        argv.extend(["--tercile-thresholds-json", str(thresholds_path)])
    if allow_legacy:
        argv.append("--allow-legacy-full-sample-thresholds")
    return replay.build_parser().parse_args(argv)


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        replay.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_default_demo_strategy_spec_path_references_spread15() -> None:
    args = replay.build_parser().parse_args([])

    assert "demo_strategy_spec_v5_spread15" in str(args.demo_strategy_spec_dir)
    assert args.tercile_thresholds_json is None


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = replay.build_outputs(make_args(tmp_path, [bar("2026-05-28 00:00:00")]))

    assert outputs["bars"].exists()
    assert outputs["signals"].exists()
    assert outputs["trades"].exists()
    assert outputs["equity"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_eligible_bar_opens_trade(tmp_path: Path) -> None:
    outputs = replay.build_outputs(make_args(tmp_path, [bar("2026-05-28 00:00:00")]))
    signals = read_csv(outputs["signals"])
    manifest = read_json(outputs["manifest"])

    assert signals[0]["signal_state"] == "paper_signal_opened"
    assert manifest["signals_opened"] == 1
    assert manifest["open_trade_remaining"] is True
    assert manifest["spread_unit"] == "broker_points"
    assert manifest["max_spread_points"] == 15.0
    assert manifest["spread_policy_matches_canonical"] is True
    assert manifest["threshold_lineage"] == "train_only"
    assert manifest["calibration_scope"] == "train_window_only"
    assert manifest["full_sample_thresholds_used"] is False
    assert manifest["oos_rows_used_for_thresholds"] is False
    assert manifest["threshold_schema_label"] == "train_only_low_mid_mid_high"


def test_default_threshold_path_resolves_from_canonical_registry(tmp_path: Path) -> None:
    outputs = replay.build_outputs(make_args(tmp_path, [bar("2026-05-28 00:00:00")], explicit_threshold=False))
    manifest = read_json(outputs["manifest"])

    assert manifest["threshold_lineage"] == "train_only"
    assert manifest["numeric_tercile_thresholds_json"].endswith("fixed_candidate_numeric_tercile_thresholds.json")


def test_legacy_full_sample_thresholds_rejected_by_default(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(tmp_path, [bar("2026-05-28 00:00:00")], threshold_payload=legacy_thresholds_payload())
    )
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["bars_processed"] == 0
    assert manifest["threshold_schema_label"] == "legacy_full_sample_lower_upper"
    assert manifest["legacy_full_sample_thresholds_allowed"] is False
    assert any(row["warning_code"] == "threshold_artifact_unreadable" for row in warnings)


def test_legacy_full_sample_thresholds_allowed_only_with_explicit_flag(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(
            tmp_path,
            [bar("2026-05-28 00:00:00")],
            threshold_payload=legacy_thresholds_payload(),
            allow_legacy=True,
        )
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["signals_opened"] == 1
    assert manifest["threshold_schema_label"] == "legacy_full_sample_lower_upper"
    assert manifest["legacy_full_sample_thresholds_allowed"] is True


def test_subsequent_bar_hits_short_tp_and_closes_positive_r(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(
            tmp_path,
            [
                bar("2026-05-28 00:00:00"),
                bar("2026-05-28 00:15:00", high=1.2510, low=1.2468),
            ],
        )
    )
    trades = read_csv(outputs["trades"])

    assert trades[0]["exit_reason"] == "paper_tp_hit"
    assert float(trades[0]["R_multiple"]) == pytest.approx(1.5)


def test_subsequent_bar_hits_short_sl_and_closes_negative_r(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(
            tmp_path,
            [
                bar("2026-05-28 00:00:00"),
                bar("2026-05-28 00:15:00", high=1.2525, low=1.2485),
            ],
        )
    )
    trades = read_csv(outputs["trades"])

    assert trades[0]["exit_reason"] == "paper_sl_hit"
    assert float(trades[0]["R_multiple"]) == pytest.approx(-1.0)


def test_same_bar_tp_sl_after_entry_applies_stop_first(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(
            tmp_path,
            [
                bar("2026-05-28 00:00:00"),
                bar("2026-05-28 00:15:00", high=1.2525, low=1.2468),
            ],
        )
    )
    trades = read_csv(outputs["trades"])
    warnings = read_csv(outputs["warnings"])

    assert trades[0]["exit_reason"] == "paper_sl_hit"
    assert any(warning["warning_code"] == "same_bar_stop_first_applied" for warning in warnings)


def test_timeout_closes_at_h10_close(tmp_path: Path) -> None:
    rows = [bar("2026-05-28 00:00:00"), *no_hit_bars(count=10)]
    outputs = replay.build_outputs(make_args(tmp_path, rows))
    trades = read_csv(outputs["trades"])

    assert trades[0]["exit_reason"] == "paper_timeout"
    assert trades[0]["bars_elapsed"] == "10"
    assert float(trades[0]["exit_price"]) == pytest.approx(1.2495)


def test_ineligible_session_skips_signal(tmp_path: Path) -> None:
    outputs = replay.build_outputs(make_args(tmp_path, [bar("2026-05-28 00:00:00", hour_session="London")]))
    signals = read_csv(outputs["signals"])

    assert signals[0]["signal_state"] == "paper_signal_skipped"
    assert "session_mismatch" in signals[0]["skip_reasons"]


def test_spread_above_threshold_skips_signal(tmp_path: Path) -> None:
    outputs = replay.build_outputs(make_args(tmp_path, [bar("2026-05-28 00:00:00", spread=20.0)]))
    signals = read_csv(outputs["signals"])

    assert signals[0]["signal_state"] == "paper_signal_skipped"
    assert "spread_above_threshold" in signals[0]["skip_reasons"]


def test_bucket_mismatch_skips_signal(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(tmp_path, [bar("2026-05-28 00:00:00", close_to_ma_fast_atr_20=0.1)])
    )
    signals = read_csv(outputs["signals"])

    assert signals[0]["signal_state"] == "paper_signal_skipped"
    assert "close_to_ma_fast_atr_20_bucket_mismatch" in signals[0]["skip_reasons"]


def test_existing_open_trade_prevents_new_signal_until_closed(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(
            tmp_path,
            [
                bar("2026-05-28 00:00:00"),
                bar("2026-05-28 00:15:00", high=1.2510, low=1.2485),
                bar("2026-05-28 00:30:00", high=1.2510, low=1.2468),
                bar("2026-05-28 00:45:00"),
            ],
        )
    )
    signals = read_csv(outputs["signals"])
    manifest = read_json(outputs["manifest"])

    assert [signal["time_server"] for signal in signals if signal["signal_state"] == "paper_signal_opened"] == [
        "2026-05-28 00:00:00",
        "2026-05-28 00:45:00",
    ]
    assert manifest["signals_opened"] == 2


def test_no_same_bar_entry_exit_on_entry_bar(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(tmp_path, [bar("2026-05-28 00:00:00", high=1.2525, low=1.2468)])
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["signals_opened"] == 1
    assert manifest["trades_closed"] == 0
    assert manifest["open_trade_remaining"] is True


def test_no_new_trade_opens_on_same_bar_where_trade_closes(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(
            tmp_path,
            [
                bar("2026-05-28 00:00:00"),
                bar("2026-05-28 00:15:00", high=1.2510, low=1.2468),
                bar("2026-05-28 00:30:00"),
            ],
        )
    )
    signals = read_csv(outputs["signals"])

    assert [signal["time_server"] for signal in signals if signal["signal_state"] == "paper_signal_opened"] == [
        "2026-05-28 00:00:00",
        "2026-05-28 00:30:00",
    ]


def test_ml_dataset_is_blocked(tmp_path: Path) -> None:
    outputs = replay.build_outputs(make_args(tmp_path, [bar("2026-05-28 00:00:00")], table="ml_dataset"))
    warnings = read_csv(outputs["warnings"])
    manifest = read_json(outputs["manifest"])

    assert any(warning["warning_code"] == "feature_source_table_blocked" for warning in warnings)
    assert manifest["blocking_warnings_count"] >= 1
    assert manifest["bars_processed"] == 0


def test_missing_required_columns_create_blocker(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(tmp_path, [bar("2026-05-28 00:00:00")], missing_column="atr_20")
    )
    warnings = read_csv(outputs["warnings"])

    assert any(warning["warning_code"] == "missing_required_columns" for warning in warnings)


def test_no_target_future_columns_are_emitted_or_required(tmp_path: Path) -> None:
    outputs = replay.build_outputs(make_args(tmp_path, [bar("2026-05-28 00:00:00")]))
    text = outputs["bars"].read_text(encoding="utf-8") + outputs["signals"].read_text(encoding="utf-8")

    assert "future_target_R" not in text
    assert "future" not in ",".join(replay.REQUIRED_SOURCE_COLUMNS)
    assert "target" not in ",".join(replay.REQUIRED_SOURCE_COLUMNS)


def test_equity_curve_cumulative_and_drawdown_are_computed(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(
            tmp_path,
            [
                bar("2026-05-28 00:00:00"),
                bar("2026-05-28 00:15:00", high=1.2510, low=1.2468),
                bar("2026-05-28 00:30:00"),
                bar("2026-05-28 00:45:00", high=1.2525, low=1.2485),
            ],
        )
    )
    equity = read_csv(outputs["equity"])
    manifest = read_json(outputs["manifest"])

    assert float(equity[0]["cumulative_R"]) == pytest.approx(1.5)
    assert float(equity[1]["cumulative_R"]) == pytest.approx(0.5)
    assert float(equity[1]["drawdown_R"]) == pytest.approx(1.0)
    assert manifest["max_drawdown_R"] == pytest.approx(1.0)


def test_manifest_counts_match_csvs(tmp_path: Path) -> None:
    outputs = replay.build_outputs(
        make_args(
            tmp_path,
            [
                bar("2026-05-28 00:00:00"),
                bar("2026-05-28 00:15:00", high=1.2510, low=1.2468),
            ],
        )
    )
    bars = read_csv(outputs["bars"])
    signals = read_csv(outputs["signals"])
    trades = read_csv(outputs["trades"])
    warnings = read_csv(outputs["warnings"])
    manifest = read_json(outputs["manifest"])

    assert manifest["bars_processed"] == len(bars)
    assert manifest["signals_opened"] == sum(1 for signal in signals if signal["signal_state"] == "paper_signal_opened")
    assert manifest["signals_skipped"] == sum(1 for signal in signals if signal["signal_state"] == "paper_signal_skipped")
    assert manifest["trades_closed"] == len(trades)
    assert manifest["warnings_count"] == len(warnings)


def test_report_includes_no_execution_db_mutation_optimization_future_proof_caveats(tmp_path: Path) -> None:
    outputs = replay.build_outputs(make_args(tmp_path, [bar("2026-05-28 00:00:00")]))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No order execution was performed." in report
    assert "No database mutation was performed." in report
    assert "No optimization, parameter search, or candidate search was performed." in report
    assert "does not prove future performance" in report
    assert "spread_policy_matches_canonical: `true`" in report


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    replay.build_outputs(make_args(tmp_path, [bar("2026-05-28 00:00:00")]))
