import csv
import json
import sqlite3
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.analyze_historical_spreads import (
    build_cost_config,
    detect_spread_source,
    infer_point_size,
    is_versionable_broker_example_config,
    load_spread_samples,
    run_analysis,
    spread_stats,
)


def create_price_bars_db(path: Path, rows: list[tuple[str, str, str, float]]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE price_bars (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                spread REAL
            )
            """
        )
        connection.executemany(
            "INSERT INTO price_bars (symbol, timeframe, time_server, spread) VALUES (?, ?, ?, ?)",
            rows,
        )


def default_args(tmp_path: Path, db_path: Path, symbols: list[str]) -> Namespace:
    return Namespace(
        db_path=db_path,
        symbols=symbols,
        timeframe="M15",
        start_date=None,
        end_date=None,
        output_dir=tmp_path / "reports",
        broker_name="Pepperstone",
        account_type="Razor",
        generate_config=False,
        config_percentiles=[75, 90, 95],
        output_config_dir=tmp_path / "config" / "brokers",
        config_prefix="pepperstone_historical",
        slippage_bps_round_trip=0.2,
        xauusd_slippage_bps_round_trip=0.5,
        commission_bps_round_trip=0.7,
        xauusd_commission_bps_round_trip=0.0,
        overwrite=False,
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return [dict(row) for row in csv.DictReader(csv_file)]


def test_spread_statistics_are_calculated_correctly() -> None:
    stats = spread_stats([1, 2, 3, 4])

    assert stats["spread_count"] == 4
    assert stats["spread_mean_points"] == 2.5
    assert stats["spread_median_points"] == 2.5
    assert stats["spread_min_points"] == 1
    assert stats["spread_max_points"] == 4


def test_percentiles_are_present() -> None:
    stats = spread_stats([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

    assert stats["spread_p75_points"] == 7
    assert stats["spread_p90_points"] == 9
    assert stats["spread_p95_points"] == 9


def test_outputs_by_hour_and_session_are_created(tmp_path: Path) -> None:
    db_path = tmp_path / "spreads.db"
    create_price_bars_db(
        db_path,
        [
            ("EURUSD", "M15", "2024-01-01 00:00:00", 1),
            ("EURUSD", "M15", "2024-01-01 08:00:00", 2),
            ("EURUSD", "M15", "2024-01-01 14:00:00", 3),
        ],
    )

    paths = run_analysis(default_args(tmp_path, db_path, ["EURUSD"]), run_id="run1", created_at="2026-05-15T00:00:00+00:00")

    assert paths["spread_by_hour"].exists()
    assert paths["spread_by_session"].exists()
    assert {row["hour"] for row in read_csv_rows(paths["spread_by_hour"])} == {"0", "8", "14"}
    assert {row["hour_session"] for row in read_csv_rows(paths["spread_by_session"])} == {"Asia", "London", "New_York"}


def test_generated_config_uses_selected_percentile(tmp_path: Path) -> None:
    db_path = tmp_path / "spreads.db"
    create_price_bars_db(
        db_path,
        [
            ("EURUSD", "M15", f"2024-01-01 0{index}:00:00", spread)
            for index, spread in enumerate([1, 2, 3, 4])
        ],
    )
    args = default_args(tmp_path, db_path, ["EURUSD"])
    args.generate_config = True
    args.config_percentiles = [75]

    paths = run_analysis(args, run_id="run1", created_at="2026-05-15T00:00:00+00:00")
    payload = json.loads(paths["config_p75"].read_text(encoding="utf-8"))

    assert payload["symbols"]["EURUSD"]["fallback_spread_points"] == 3
    assert payload["metadata"]["percentile_used"] == 75


def test_point_size_inference() -> None:
    assert infer_point_size("EURUSD") == 0.00001
    assert infer_point_size("USDJPY") == 0.001
    assert infer_point_size("XAUUSD") is None


def test_xauusd_is_skipped_without_configured_point_size(tmp_path: Path) -> None:
    config = build_cost_config(
        symbol_rows=[
            {
                "symbol": "XAUUSD",
                "spread_p75_points": 25,
                "spread_p90_points": 30,
                "spread_p95_points": 35,
            }
        ],
        percentile_value=75,
        broker_name="Pepperstone",
        account_type="Razor",
        db_path=tmp_path / "spreads.db",
        timeframe="M15",
        start_date=None,
        end_date=None,
        spread_source=detect_source_stub(),
        slippage_bps_round_trip=0.2,
        xauusd_slippage_bps_round_trip=0.5,
        commission_bps_round_trip=0.7,
        xauusd_commission_bps_round_trip=0.0,
        created_at="2026-05-15T00:00:00+00:00",
    )

    assert "XAUUSD" not in config["symbols"]


def detect_source_stub():
    from scripts.analyze_historical_spreads import SpreadSource

    return SpreadSource("price_bars", "spread")


def test_missing_spread_column_fails_with_clear_error(tmp_path: Path) -> None:
    db_path = tmp_path / "missing_spread.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE price_bars (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT
            )
            """
        )

    with sqlite3.connect(db_path) as connection:
        with pytest.raises(ValueError, match="No supported historical spread column"):
            detect_spread_source(connection)


def test_output_already_exists_requires_overwrite(tmp_path: Path) -> None:
    db_path = tmp_path / "spreads.db"
    create_price_bars_db(db_path, [("EURUSD", "M15", "2024-01-01 00:00:00", 1)])
    args = default_args(tmp_path, db_path, ["EURUSD"])
    run_analysis(args, run_id="run1", created_at="2026-05-15T00:00:00+00:00")

    with pytest.raises(FileExistsError, match="Pass --overwrite"):
        run_analysis(args, run_id="run1", created_at="2026-05-15T00:00:00+00:00")


def test_local_config_is_not_versionable_example(tmp_path: Path) -> None:
    local_path = tmp_path / "pepperstone_historical_p75.local.json"
    example_path = tmp_path / "pepperstone_historical_p75.example.json"

    assert not is_versionable_broker_example_config(local_path)
    assert is_versionable_broker_example_config(example_path)


def test_price_bars_spread_is_preferred_over_price_features(tmp_path: Path) -> None:
    db_path = tmp_path / "source.db"
    create_price_bars_db(db_path, [("EURUSD", "M15", "2024-01-01 00:00:00", 2)])
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE price_features (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                spread_avg_20 REAL
            )
            """
        )

    source, samples = load_spread_samples(
        db_path,
        symbols=["EURUSD"],
        timeframe="M15",
        start_date=None,
        end_date=None,
    )

    assert source.label == "price_bars.spread"
    assert samples[0].spread_points == 2
