from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import export_fixed_candidate_mt5_ea_parity_dataset as export


SPEC_PATH = Path("config/strategy_specs/gbpusd_short_h10_1_5_off_hours_strategy_spec.json")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def create_feature_db(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    db_path = tmp_path / "features.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE price_features (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                tick_volume REAL,
                spread REAL,
                atr_20 REAL,
                ma_fast REAL,
                close_to_ma_fast_atr_20 REAL,
                tick_volume_percentile_100 REAL,
                hour_session TEXT
            )
            """
        )
        for row in rows:
            payload = {
                "symbol": "GBPUSD",
                "timeframe": "M15",
                "time_server": "2026-06-26 22:30:00",
                "open": 1.2498,
                "high": 1.2504,
                "low": 1.2495,
                "close": 1.25,
                "tick_volume": 123,
                "spread": 6.0,
                "atr_20": 0.0006,
                "ma_fast": 1.2496,
                "close_to_ma_fast_atr_20": 0.7,
                "tick_volume_percentile_100": 0.2,
                "hour_session": "Off_hours",
            }
            payload.update(row)
            connection.execute(
                """
                INSERT INTO price_features (
                    symbol,
                    timeframe,
                    time_server,
                    open,
                    high,
                    low,
                    close,
                    tick_volume,
                    spread,
                    atr_20,
                    ma_fast,
                    close_to_ma_fast_atr_20,
                    tick_volume_percentile_100,
                    hour_session
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["symbol"],
                    payload["timeframe"],
                    payload["time_server"],
                    payload["open"],
                    payload["high"],
                    payload["low"],
                    payload["close"],
                    payload["tick_volume"],
                    payload["spread"],
                    payload["atr_20"],
                    payload["ma_fast"],
                    payload["close_to_ma_fast_atr_20"],
                    payload["tick_volume_percentile_100"],
                    payload["hour_session"],
                ),
            )
    return db_path


def test_strategy_spec_contains_audited_values() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert spec["candidate_id"] == "gbpusd_short_h10_1_5_off_hours"
    assert spec["symbol"] == "GBPUSD"
    assert spec["timeframe"] == "M15"
    assert spec["direction"] == "short"
    assert spec["session"]["required_value"] == "Off_hours"
    assert spec["session"]["server_hours"] == [22, 23]
    assert spec["features"]["close_to_ma_fast_atr_20"]["mid_high_cutoff"] == pytest.approx(
        0.5954421525644814
    )
    assert spec["features"]["tick_volume_percentile_100"]["low_mid_cutoff"] == pytest.approx(0.14)
    assert spec["spread_policy"]["max_spread_points"] == pytest.approx(15.0)
    assert spec["sl_tp"]["tp_atr"] == pytest.approx(1.5)
    assert spec["sl_tp"]["sl_atr"] == pytest.approx(1.0)
    assert spec["trade_lifecycle"]["max_holding_bars"] == 10
    assert spec["trade_lifecycle"]["timeframe"] == "M15"
    assert (
        spec["trade_lifecycle"]["exit_policy"]
        == "close_at_market_after_10_closed_bars_if_sl_or_tp_not_hit"
    )
    assert spec["trade_lifecycle"]["bar_count_basis"] == "closed_bars_after_entry"
    assert spec["trade_lifecycle"]["time_basis"] == "mt5_server_time"
    assert spec["mql5_translation_boundaries"]["order_check_implemented"] is False
    assert spec["mql5_translation_boundaries"]["order_send_implemented"] is False


def test_export_dataset_includes_required_columns_and_signal_row(tmp_path: Path) -> None:
    db_path = create_feature_db(tmp_path, [{"time_server": "2026-06-26 22:30:00"}])
    output_csv = tmp_path / "parity.csv"

    summary = export.export_parity_dataset(
        strategy_spec_path=SPEC_PATH,
        db_path=db_path,
        feature_table="price_features",
        output_csv=output_csv,
        limit=50,
        overwrite=True,
    )

    rows = read_csv(output_csv)
    assert summary["read_only_db"] is True
    assert summary["broker_connection_performed"] is False
    assert summary["trade_operation_performed"] is False
    assert summary["rows_exported"] == 1
    assert set(export.EXPORT_FIELDNAMES).issubset(rows[0].keys())
    assert rows[0]["close_to_ma_fast_atr_20_bucket"] == "high_tercile"
    assert rows[0]["tick_volume_percentile_100_bucket"] == "mid_tercile"
    assert rows[0]["signal_bool"] == "true"
    assert float(rows[0]["entry_reference_price"]) == pytest.approx(1.25)
    assert float(rows[0]["sl_price_preview"]) == pytest.approx(1.2506)
    assert float(rows[0]["tp_price_preview"]) == pytest.approx(1.2491)
    assert rows[0]["max_holding_bars"] == "10"
    assert rows[0]["max_exit_time_server"] == ""


def test_export_dataset_includes_lifecycle_exit_time_when_available(tmp_path: Path) -> None:
    times = [
        "2026-06-26 22:00:00",
        "2026-06-26 22:15:00",
        "2026-06-26 22:30:00",
        "2026-06-26 22:45:00",
        "2026-06-26 23:00:00",
        "2026-06-26 23:15:00",
        "2026-06-26 23:30:00",
        "2026-06-26 23:45:00",
        "2026-06-27 00:00:00",
        "2026-06-27 00:15:00",
        "2026-06-27 00:30:00",
    ]
    db_path = create_feature_db(tmp_path, [{"time_server": time_server} for time_server in times])
    output_csv = tmp_path / "parity.csv"

    export.export_parity_dataset(
        strategy_spec_path=SPEC_PATH,
        db_path=db_path,
        feature_table="price_features",
        output_csv=output_csv,
        limit=50,
        overwrite=True,
    )

    rows = read_csv(output_csv)
    assert rows[0]["max_holding_bars"] == "10"
    assert rows[0]["max_exit_time_server"] == "2026-06-27 00:30:00"
    assert rows[1]["max_exit_time_server"] == ""


@pytest.mark.parametrize(
    ("override", "expected_close_bucket", "expected_volume_bucket"),
    [
        ({"hour_session": "London"}, "high_tercile", "mid_tercile"),
        ({"spread": 16.0}, "high_tercile", "mid_tercile"),
        ({"close_to_ma_fast_atr_20": 0.1}, "mid_tercile", "mid_tercile"),
        ({"tick_volume_percentile_100": 0.9}, "high_tercile", "high_tercile"),
    ],
)
def test_signal_bool_uses_python_rule_contract(
    tmp_path: Path,
    override: dict[str, object],
    expected_close_bucket: str,
    expected_volume_bucket: str,
) -> None:
    db_path = create_feature_db(tmp_path, [override])
    output_csv = tmp_path / "parity.csv"

    export.export_parity_dataset(
        strategy_spec_path=SPEC_PATH,
        db_path=db_path,
        feature_table="price_features",
        output_csv=output_csv,
        limit=50,
        overwrite=True,
    )

    row = read_csv(output_csv)[0]
    assert row["close_to_ma_fast_atr_20_bucket"] == expected_close_bucket
    assert row["tick_volume_percentile_100_bucket"] == expected_volume_bucket
    assert row["signal_bool"] == "false"
    assert row["entry_reference_price"] == ""
    assert row["sl_price_preview"] == ""
    assert row["tp_price_preview"] == ""


def test_exporter_blocks_non_allowlisted_table(tmp_path: Path) -> None:
    db_path = create_feature_db(tmp_path, [{}])
    with pytest.raises(ValueError, match="not allowlisted"):
        export.fetch_feature_rows(
            db_path=db_path,
            table_name="ml_dataset",
            symbol="GBPUSD",
            timeframe="M15",
            limit=10,
        )


def test_static_safety_no_broker_trade_calls() -> None:
    source = Path("scripts/export_fixed_candidate_mt5_ea_parity_dataset.py").read_text(encoding="utf-8")
    assert "MetaTrader5" not in source
    assert ".order_check(" not in source
    assert ".order_send(" not in source


def test_design_packet_documents_time_exit_rule() -> None:
    packet = Path("docs/mt5_ea_translation_design_packet.md").read_text(encoding="utf-8")
    assert "max holding period: `10` closed M15 bars after entry" in packet
    assert "close_at_market_after_10_closed_bars_if_sl_or_tp_not_hit" in packet
    assert "not an entry signal rule" in packet
    assert "The signal-only EA prototype must not close positions" in packet
    assert "Do not implement `PositionClose`" in packet
