from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_train_only_numeric_tercile_thresholds as thresholds


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def canonical_registry(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
    }
    payload.update(overrides)
    return payload


def fixture_rows() -> list[dict[str, object]]:
    train_values = [
        ("2024-01-01 00:00:00", "GBPUSD", "M15", "Off_hours", 0.0, 10.0),
        ("2024-01-01 00:01:00", "GBPUSD", "M15", "Off_hours", 3.0, 20.0),
        ("2024-01-01 00:02:00", "GBPUSD", "M15", "Off_hours", 6.0, 30.0),
        ("2024-01-01 00:03:00", "GBPUSD", "M15", "Off_hours", 9.0, 40.0),
        ("2024-01-01 00:04:00", "GBPUSD", "M15", "Off_hours", 12.0, 50.0),
        ("2024-01-01 00:05:00", "GBPUSD", "M15", "Off_hours", 15.0, 60.0),
        ("2024-01-01 00:06:00", "GBPUSD", "M15", "Off_hours", 900.0, 900.0),
        ("2024-01-01 00:07:00", "GBPUSD", "M15", "Off_hours", 1200.0, 1200.0),
        ("2024-01-01 00:02:00", "GBPUSD", "M15", "London", 600.0, 600.0),
        ("2024-01-01 00:02:00", "EURUSD", "M15", "Off_hours", 700.0, 700.0),
        ("2024-01-01 00:02:00", "GBPUSD", "H1", "Off_hours", 800.0, 800.0),
    ]
    return [
        {
            "time_server": time_server,
            "symbol": symbol,
            "timeframe": timeframe,
            "hour_session": session,
            "close_to_ma_fast_atr_20": close_ma,
            "tick_volume_percentile_100": volume,
        }
        for time_server, symbol, timeframe, session, close_ma, volume in train_values
    ]


def write_feature_db(
    path: Path,
    *,
    table: str = "price_features",
    missing_columns: set[str] | None = None,
    include_table: bool = True,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "time_server",
        "symbol",
        "timeframe",
        "hour_session",
        "close_to_ma_fast_atr_20",
        "tick_volume_percentile_100",
    ]
    for column in missing_columns or set():
        columns.remove(column)
    with sqlite3.connect(path) as connection:
        if include_table:
            column_defs = []
            for column in columns:
                column_type = "REAL" if column in thresholds.DEFAULT_FEATURES else "TEXT"
                column_defs.append(f"{thresholds.quote_identifier(column)} {column_type}")
            connection.execute(f"CREATE TABLE {thresholds.quote_identifier(table)} ({', '.join(column_defs)})")
            for row in fixture_rows():
                selected = [row[column] for column in columns]
                placeholders = ",".join("?" for _ in selected)
                connection.execute(
                    f"INSERT INTO {thresholds.quote_identifier(table)} "
                    f"({', '.join(thresholds.quote_identifier(column) for column in columns)}) "
                    f"VALUES ({placeholders})",
                    selected,
                )
    return path


def make_args(
    tmp_path: Path,
    *,
    train_start_time: str | None = None,
    train_end_time: str | None = "2024-01-01 00:05:00",
    min_train_rows: int = 6,
    db_path: Path | None = None,
    canonical: dict[str, object] | None = None,
    feature_table: str = "price_features",
    output_dir: Path | None = None,
    overwrite: bool = True,
) -> object:
    registry_path = write_json(tmp_path / "config" / "fixed_candidate_current_canonical.json", canonical or canonical_registry())
    if db_path is None:
        db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", table=feature_table)
    args = [
        "--run-id",
        "unit_train_only_thresholds",
        "--db-path",
        str(db_path),
        "--feature-table",
        feature_table,
        "--canonical-registry",
        str(registry_path),
        "--symbol",
        "GBPUSD",
        "--timeframe",
        "M15",
        "--session-column",
        "hour_session",
        "--required-session",
        "Off_hours",
        "--min-train-rows",
        str(min_train_rows),
        "--output-dir",
        str(output_dir or tmp_path / "out"),
    ]
    for feature in thresholds.DEFAULT_FEATURES:
        args.extend(["--feature", feature])
    if train_start_time is not None:
        args.extend(["--train-start-time", train_start_time])
    if train_end_time is not None:
        args.extend(["--train-end-time", train_end_time])
    if overwrite:
        args.append("--overwrite")
    return thresholds.build_parser().parse_args(args)


def build_and_read(tmp_path: Path, **kwargs: object) -> tuple[dict[str, Path], dict[str, object], dict[str, object]]:
    outputs = thresholds.build_outputs(make_args(tmp_path, **kwargs))
    return outputs, read_json(outputs["manifest"]), read_json(outputs["thresholds"])


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        thresholds.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_missing_train_end_time_blocks(tmp_path: Path) -> None:
    outputs, manifest, _payload = build_and_read(tmp_path, train_end_time=None)

    assert manifest["threshold_status"] == thresholds.STATUS_MISSING_TRAIN_END
    assert any(row["warning_code"] == "missing_train_end_time" for row in read_csv(outputs["warnings"]))


def test_missing_db_blocks(tmp_path: Path) -> None:
    missing_db = tmp_path / "db" / "missing.db"
    _outputs, manifest, _payload = build_and_read(tmp_path, db_path=missing_db)

    assert manifest["threshold_status"] == thresholds.STATUS_MISSING_DB


def test_missing_table_blocks(tmp_path: Path) -> None:
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", include_table=False)
    _outputs, manifest, _payload = build_and_read(tmp_path, db_path=db_path)

    assert manifest["threshold_status"] == thresholds.STATUS_MISSING_TABLE


def test_missing_columns_block(tmp_path: Path) -> None:
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", missing_columns={"time_server"})
    _outputs, manifest, _payload = build_and_read(tmp_path, db_path=db_path)

    assert manifest["threshold_status"] == thresholds.STATUS_MISSING_COLUMNS
    assert "time_server" in manifest["missing_required_columns"]


def test_empty_train_window_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _payload = build_and_read(tmp_path, train_start_time="2025-01-01 00:00:00")

    assert manifest["threshold_status"] == thresholds.STATUS_EMPTY_TRAIN


def test_insufficient_train_rows_block(tmp_path: Path) -> None:
    _outputs, manifest, _payload = build_and_read(tmp_path, min_train_rows=7)

    assert manifest["threshold_status"] == thresholds.STATUS_INSUFFICIENT_ROWS


def test_valid_train_window_computes_thresholds_only_from_rows_at_or_before_train_end_time(tmp_path: Path) -> None:
    _outputs, manifest, payload = build_and_read(tmp_path)
    feature = payload["features"]["close_to_ma_fast_atr_20"]

    assert manifest["threshold_status"] == thresholds.STATUS_AVAILABLE
    assert feature["low_mid_cutoff"] == pytest.approx(5.0)
    assert feature["mid_high_cutoff"] == pytest.approx(10.0)


def test_rows_after_train_end_time_do_not_affect_cutoffs(tmp_path: Path) -> None:
    _outputs, _manifest, payload = build_and_read(tmp_path)
    volume = payload["features"]["tick_volume_percentile_100"]

    assert volume["low_mid_cutoff"] == pytest.approx(26.6666666667)
    assert volume["mid_high_cutoff"] == pytest.approx(43.3333333333)
    assert volume["mid_high_cutoff"] < 900.0


def test_optional_train_start_time_is_respected(tmp_path: Path) -> None:
    _outputs, manifest, payload = build_and_read(
        tmp_path,
        train_start_time="2024-01-01 00:02:00",
        min_train_rows=4,
    )
    feature = payload["features"]["close_to_ma_fast_atr_20"]

    assert manifest["train_row_count"] == 4
    assert feature["low_mid_cutoff"] == pytest.approx(9.0)
    assert feature["mid_high_cutoff"] == pytest.approx(12.0)


def test_effective_train_start_time_is_first_available_row_when_omitted(tmp_path: Path) -> None:
    _outputs, manifest, _payload = build_and_read(tmp_path)

    assert manifest["train_start_time_requested"] == ""
    assert manifest["train_start_time_effective"] == "2024-01-01 00:00:00"


def test_symbol_timeframe_filters_are_applied_when_columns_exist(tmp_path: Path) -> None:
    _outputs, manifest, _payload = build_and_read(tmp_path)

    assert manifest["symbol_filter_applied"] is True
    assert manifest["timeframe_filter_applied"] is True
    assert manifest["source_row_count"] == 8
    assert manifest["train_row_count"] == 6


def test_session_filter_is_applied_when_session_column_exists(tmp_path: Path) -> None:
    _outputs, manifest, payload = build_and_read(tmp_path)

    assert manifest["session_filter_applied"] is True
    assert payload["features"]["close_to_ma_fast_atr_20"]["mid_high_cutoff"] == pytest.approx(10.0)


def test_threshold_json_includes_train_only_lineage(tmp_path: Path) -> None:
    _outputs, _manifest, payload = build_and_read(tmp_path)

    assert payload["threshold_lineage"] == "train_only"
    assert payload["calibration_scope"] == "train_window_only"


def test_manifest_includes_full_sample_thresholds_used_false(tmp_path: Path) -> None:
    _outputs, manifest, _payload = build_and_read(tmp_path)

    assert manifest["full_sample_thresholds_used"] is False


def test_manifest_includes_oos_rows_used_for_thresholds_false(tmp_path: Path) -> None:
    _outputs, manifest, _payload = build_and_read(tmp_path)

    assert manifest["oos_rows_used_for_thresholds"] is False


def test_manifest_includes_source_and_train_min_max_timestamps(tmp_path: Path) -> None:
    _outputs, manifest, _payload = build_and_read(tmp_path)

    assert manifest["source_min_time_server"] == "2024-01-01 00:00:00"
    assert manifest["source_max_time_server"] == "2024-01-01 00:07:00"
    assert manifest["train_min_time_server"] == "2024-01-01 00:00:00"
    assert manifest["train_max_time_server"] == "2024-01-01 00:05:00"


def test_feature_summary_csv_includes_counts_and_cutoffs(tmp_path: Path) -> None:
    outputs, _manifest, _payload = build_and_read(tmp_path)
    rows = read_csv(outputs["feature_summary"])

    assert rows[0]["feature_name"] == "close_to_ma_fast_atr_20"
    assert rows[0]["non_null_count"] == "6"
    assert float(rows[0]["low_mid_cutoff"]) == pytest.approx(5.0)
    assert float(rows[0]["mid_high_cutoff"]) == pytest.approx(10.0)


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _payload = build_and_read(
        tmp_path,
        canonical=canonical_registry(candidate_id="other_candidate"),
    )

    assert manifest["threshold_status"] == thresholds.STATUS_NONCANONICAL


def test_output_exists_without_overwrite_blocks(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    args = make_args(tmp_path, output_dir=output_dir)
    thresholds.build_outputs(args)
    args.overwrite = False

    with pytest.raises(thresholds.BlockedStatusError) as exc:
        thresholds.build_outputs(args)

    assert exc.value.status == thresholds.STATUS_OUTPUT_EXISTS


def test_no_order_evidence_is_written(tmp_path: Path) -> None:
    outputs, manifest, _payload = build_and_read(tmp_path)
    rows = read_csv(outputs["no_order_evidence"])
    evidence = {row["evidence_name"]: row["value"] for row in rows}

    assert manifest["no_order_send_called"] is True
    assert evidence["no_mt5_import_performed"] == "true"
    assert evidence["no_db_mutation_performed"] == "true"


def test_static_safety_grep_confirms_no_mt5_order_broker_history_scheduler_calls() -> None:
    source = Path(thresholds.__file__).read_text(encoding="utf-8")

    assert "MetaTrader5" not in source
    assert "mt5." not in source
    assert not re.search(
        r"\.(order_check|order_send|order_calc_margin|order_calc_profit|positions_get|orders_get|"
        r"history_orders_get|history_deals_get)\s*\(",
        source,
    )
    assert "subprocess" not in source
    assert not re.search(r"\b(threading|schedule|apscheduler)\b", source)


def test_static_safety_grep_confirms_no_db_mutation_statements() -> None:
    source = Path(thresholds.__file__).read_text(encoding="utf-8")

    assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|REPLACE|CREATE)\b", source)
