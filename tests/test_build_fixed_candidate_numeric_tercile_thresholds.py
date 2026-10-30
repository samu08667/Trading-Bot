from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_numeric_tercile_thresholds as thresholds


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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
    }
    config.update(overrides)
    return config


def write_readiness_dir(path: Path, *, non_threshold_blocker: bool = False) -> None:
    write_csv(
        path / thresholds.READINESS_CSV,
        ["readiness_area", "readiness_status", "warning_code", "blocking_warning"],
        [
            {
                "readiness_area": "numeric_tercile_threshold_artifact_gate",
                "readiness_status": "blocked_missing_threshold_artifact",
                "warning_code": "numeric_tercile_threshold_artifact_missing",
                "blocking_warning": "true",
            }
        ],
    )
    write_json(
        path / thresholds.READINESS_MANIFEST,
        {
            "run_id": "fixture_readiness",
            "readiness_row_count": 17,
            "blocked_missing_threshold_artifact_count": 4,
            "blocked_missing_required_artifact_count": 1 if non_threshold_blocker else 0,
            "blocked_missing_required_column_count": 0,
            "blocked_unreadable_input_count": 0,
            "blocked_by_leakage_risk_count": 0,
            "blocked_by_config_count": 0,
            "blocking_warnings_count": 1,
        },
    )
    (path / thresholds.READINESS_REPORT).write_text("# Readiness\nthreshold missing\n", encoding="utf-8")
    write_csv(
        path / thresholds.READINESS_WARNINGS,
        ["warning_code", "blocking_warning"],
        [
            {
                "warning_code": "numeric_tercile_threshold_artifact_missing",
                "blocking_warning": "true",
            }
        ],
    )


def feature_rows() -> list[dict[str, object]]:
    values = [
        ("GBPUSD", "M15", "Off_hours", 0.0, 10.0),
        ("GBPUSD", "M15", "Off_hours", 3.0, 20.0),
        ("GBPUSD", "M15", "Off_hours", 6.0, 30.0),
        ("GBPUSD", "M15", "Off_hours", 9.0, 40.0),
        ("EURUSD", "M15", "Off_hours", 300.0, 300.0),
        ("GBPUSD", "H1", "Off_hours", 400.0, 400.0),
        ("GBPUSD", "M15", "London", 500.0, 500.0),
    ]
    rows: list[dict[str, object]] = []
    for index, (symbol, timeframe, session, close_ma, volume_pct) in enumerate(values):
        rows.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "time_server": f"2024-01-01 00:{index:02d}:00",
                "open": "1.0",
                "high": "1.1",
                "low": "0.9",
                "close": "1.05",
                "hour_session": session,
                "close_to_ma_fast_atr_20": close_ma,
                "tick_volume_percentile_100": volume_pct,
            }
        )
    return rows


def write_feature_db(
    path: Path,
    *,
    table: str = "price_features",
    missing_column: str | None = None,
    include_symbol: bool = True,
    include_timeframe: bool = True,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "symbol",
        "timeframe",
        "time_server",
        "open",
        "high",
        "low",
        "close",
        "hour_session",
        "close_to_ma_fast_atr_20",
        "tick_volume_percentile_100",
        "atr_20",
        "spread",
        "spread_avg_20",
    ]
    if not include_symbol:
        columns.remove("symbol")
    if not include_timeframe:
        columns.remove("timeframe")
    if missing_column:
        columns.remove(missing_column)
    with sqlite3.connect(path) as connection:
        connection.execute(f'CREATE TABLE "{table}" ({", ".join(f"{thresholds.quote_identifier(column)} REAL" for column in columns)})')
        for row in feature_rows():
            values = {
                **row,
                "atr_20": 0.002,
                "spread": 12,
                "spread_avg_20": 11,
            }
            selected_values = [values.get(column) for column in columns]
            placeholders = ",".join("?" for _ in columns)
            connection.execute(
                f'INSERT INTO "{table}" ({", ".join(thresholds.quote_identifier(column) for column in columns)}) VALUES ({placeholders})',
                selected_values,
            )
    return path


def make_args(
    tmp_path: Path,
    *,
    table: str = "price_features",
    missing_column: str | None = None,
    include_symbol: bool = True,
    include_timeframe: bool = True,
    min_count: int = 1,
    non_threshold_blocker: bool = False,
    config: dict[str, object] | None = None,
) -> object:
    config_path = write_json(tmp_path / "config" / "demo_strategy_config.json", config or demo_config())
    readiness_dir = tmp_path / "readiness"
    write_readiness_dir(readiness_dir, non_threshold_blocker=non_threshold_blocker)
    db_path = write_feature_db(
        tmp_path / "db" / "trading_bot.db",
        table=table,
        missing_column=missing_column,
        include_symbol=include_symbol,
        include_timeframe=include_timeframe,
    )
    return thresholds.build_parser().parse_args(
        [
            "--run-id",
            "unit_numeric_tercile_thresholds",
            "--demo-strategy-config",
            str(config_path),
            "--paper-signal-logger-readiness-dir",
            str(readiness_dir),
            "--feature-source-db",
            str(db_path),
            "--feature-source-table",
            table,
            "--candidate-id",
            "gbpusd_short_h10_1_5_off_hours",
            "--symbol",
            "GBPUSD",
            "--timeframe",
            "M15",
            "--regime-column",
            "hour_session",
            "--regime-value",
            "Off_hours",
            "--features",
            "close_to_ma_fast_atr_20",
            "tick_volume_percentile_100",
            "--min-non-null-count",
            str(min_count),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        thresholds.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path))

    assert outputs["threshold_json"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_json_threshold_artifact_contains_schema_candidate_and_features(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path))
    payload = json.loads(outputs["threshold_json"].read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["candidate_id"] == "gbpusd_short_h10_1_5_off_hours"
    assert set(payload["features"]) == {"close_to_ma_fast_atr_20", "tick_volume_percentile_100"}


def test_price_features_is_allowlisted(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path, table="price_features"))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["feature_source_table_allowlisted"] is True
    assert manifest["blocked_by_leakage_risk_count"] == 0


def test_market_features_is_allowlisted(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path, table="market_features"))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["feature_source_table_allowlisted"] is True
    assert manifest["blocked_by_leakage_risk_count"] == 0


def test_ml_dataset_is_blocked_by_leakage_risk(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path, table="ml_dataset"))
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert any(row["warning_code"] == "feature_source_table_leakage_risk" for row in warnings)
    assert manifest["blocked_by_leakage_risk_count"] == 1
    assert manifest["threshold_json_valid"] is False


def test_missing_required_column_creates_blocking_warning(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path, missing_column="close_to_ma_fast_atr_20"))
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert any(row["warning_code"] == "missing_required_column" for row in warnings)
    assert manifest["blocked_missing_required_column_count"] == 1


def test_insufficient_rows_creates_blocking_warning(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path, min_count=100))
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert any(row["warning_code"] == "insufficient_non_null_rows" for row in warnings)
    assert manifest["blocked_insufficient_rows_count"] == 2
    assert manifest["threshold_json_valid"] is False


def test_symbol_timeframe_and_regime_filters_are_applied_when_columns_exist(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    payload = json.loads(outputs["threshold_json"].read_text(encoding="utf-8"))

    assert manifest["symbol_filter_applied"] is True
    assert manifest["timeframe_filter_applied"] is True
    assert manifest["regime_filter_applied"] is True
    assert payload["features"]["close_to_ma_fast_atr_20"]["non_null_count"] == 4


def test_missing_symbol_timeframe_columns_create_non_blocking_caveats(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path, include_symbol=False, include_timeframe=False))
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert any(row["warning_code"] == "symbol_filter_unavailable" for row in warnings)
    assert any(row["warning_code"] == "timeframe_filter_unavailable" for row in warnings)
    assert manifest["blocking_warnings_count"] == 0
    assert manifest["symbol_filter_applied"] is False
    assert manifest["timeframe_filter_applied"] is False


def test_required_bucket_labels_are_present(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path))
    payload = json.loads(outputs["threshold_json"].read_text(encoding="utf-8"))
    close_feature = payload["features"]["close_to_ma_fast_atr_20"]
    volume_feature = payload["features"]["tick_volume_percentile_100"]

    assert close_feature["required_bucket_for_candidate"] == "high_tercile"
    assert "high_tercile" in close_feature
    assert volume_feature["required_bucket_for_candidate"] == "mid_tercile"
    assert "mid_tercile" in volume_feature


def test_linear_quantile_boundaries_are_deterministic_on_fixture_data(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path))
    payload = json.loads(outputs["threshold_json"].read_text(encoding="utf-8"))
    close_feature = payload["features"]["close_to_ma_fast_atr_20"]
    volume_feature = payload["features"]["tick_volume_percentile_100"]

    assert close_feature["lower_tercile_boundary"] == pytest.approx(3.0)
    assert close_feature["upper_tercile_boundary"] == pytest.approx(6.0)
    assert volume_feature["lower_tercile_boundary"] == pytest.approx(20.0)
    assert volume_feature["upper_tercile_boundary"] == pytest.approx(30.0)


def test_manifest_counts_match_warnings(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path, min_count=100))
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["threshold_json_written"] is True
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_paper_runner_executed"] is True
    assert manifest["no_db_mutation_performed"] is True
    assert manifest["no_data_generation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_db_read_only_no_execution_and_no_decision_caveats(tmp_path: Path) -> None:
    outputs = thresholds.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-only threshold builder" in report
    assert "DB read-only mode" in report
    assert "No data generation was performed." in report
    assert "No order execution was performed." in report
    assert "No trading decision was made." in report


def test_no_db_mutation_occurs_in_tests(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    db_path = Path(args.feature_source_db)
    thresholds.build_outputs(args)

    with sqlite3.connect(db_path) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]

    assert tables == ["price_features"]


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    thresholds.build_outputs(make_args(tmp_path))
