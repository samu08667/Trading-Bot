import math
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.condition_utils import precheck_combination_skip_reason
from scripts.feature_safety import FUTURE_TARGET_SKIP_REASON, is_future_or_target_column
from scripts.generate_ml_dataset import INPUT_COLUMNS, generate_rows
from scripts.generate_price_features import generate_features, resolve_point_size
from scripts.init_database import init_database
from scripts.ml_research import prepare_numeric_features
from scripts.target_families import (
    barrier_bars_column,
    barrier_hit_first_column,
    triple_barrier_column,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


NEW_PRICE_COLUMNS = {
    "true_range",
    "atr_14",
    "atr_20",
    "atr_50",
    "range_to_atr_20",
    "body_to_atr_20",
    "upper_wick_to_atr_20",
    "lower_wick_to_atr_20",
    "close_to_ma_fast_atr_20",
    "close_to_ma_slow_atr_20",
    "ma_diff_atr_20",
    "volatility_100",
    "volatility_ratio_20_100",
    "spread_price",
    "spread_return",
    "spread_to_atr_20",
}
NEW_REGIME_COLUMNS = {
    "session",
    "spread_liquidity_regime",
    "volatility_regime",
    "range_regime",
    "volume_liquidity_regime",
}

NEW_LABEL_COLUMNS = {
    f"{prefix}_{horizon}"
    for horizon in (5, 10, 20)
    for prefix in (
        "future_max_return",
        "future_min_return",
        "future_range",
        "long_mfe",
        "long_mae",
        "short_mfe",
        "short_mae",
        "target_long_good",
        "target_short_good",
    )
}
TRIPLE_BARRIER_COLUMNS = {
    column
    for horizon in (5, 10, 20)
    for direction in ("long", "short")
    for tp_atr, sl_atr in ((1, 1), (1.5, 1), (2, 1))
    for column in (
        barrier_hit_first_column(direction, tp_atr, sl_atr, horizon),
        triple_barrier_column(direction, tp_atr, sl_atr, horizon),
        barrier_bars_column(direction, tp_atr, sl_atr, horizon),
    )
}


def table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})")}


def test_sqlite_schema_contains_new_price_and_label_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "trading_bot.db"

    init_database(db_path)

    with sqlite3.connect(db_path) as connection:
        assert NEW_PRICE_COLUMNS.issubset(table_columns(connection, "price_features"))
        assert NEW_PRICE_COLUMNS.issubset(table_columns(connection, "market_features"))
        assert NEW_REGIME_COLUMNS.issubset(table_columns(connection, "price_features"))
        assert NEW_REGIME_COLUMNS.issubset(table_columns(connection, "market_features"))
        ml_columns = table_columns(connection, "ml_dataset")
        assert NEW_PRICE_COLUMNS.issubset(ml_columns)
        assert NEW_REGIME_COLUMNS.issubset(ml_columns)
        assert NEW_LABEL_COLUMNS.issubset(ml_columns)
        assert TRIPLE_BARRIER_COLUMNS.issubset(ml_columns)


def price_row(index: int, close: float, spread: int = 12) -> dict[str, object]:
    timestamp = datetime(2024, 1, 1) + timedelta(minutes=15 * index)
    return {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "time_server": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "open": close - 0.0002,
        "high": close + 0.0010,
        "low": close - 0.0020,
        "close": close,
        "tick_volume": 100 + index,
        "spread": spread,
    }


def xauusd_price_row(index: int, close: float = 2000.0, spread: int = 24) -> dict[str, object]:
    timestamp = datetime(2024, 1, 1) + timedelta(minutes=15 * index)
    return {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "time_server": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "open": close,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "tick_volume": 100 + index,
        "spread": spread,
    }


def population_std(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5


def test_generate_price_features_calculates_atr_and_atr_ratios() -> None:
    closes = [1.0 + index * 0.001 for index in range(101)]
    features, skipped = generate_features(
        [price_row(index, close) for index, close in enumerate(closes)]
    )

    assert skipped == 0
    first_atr_20 = features[18]["atr_20"]
    feature = features[100]

    assert first_atr_20 is None
    assert math.isclose(float(feature["true_range"]), 0.003, rel_tol=1e-9)
    assert math.isclose(float(feature["atr_14"]), 0.003, rel_tol=1e-9)
    assert math.isclose(float(feature["atr_20"]), 0.003, rel_tol=1e-9)
    assert math.isclose(float(feature["atr_50"]), 0.003, rel_tol=1e-9)
    assert math.isclose(float(feature["range_to_atr_20"]), 1.0, rel_tol=1e-9)
    assert math.isclose(float(feature["body_to_atr_20"]), 0.0002 / 0.003, rel_tol=1e-9)
    assert math.isclose(float(feature["upper_wick_to_atr_20"]), 0.001 / 0.003, rel_tol=1e-9)
    assert math.isclose(float(feature["lower_wick_to_atr_20"]), 0.0018 / 0.003, rel_tol=1e-9)
    assert feature["spread"] == 12
    assert math.isclose(float(feature["spread_price"]), 12 * 0.00001, rel_tol=1e-9)
    assert math.isclose(float(feature["spread_return"]), (12 * 0.00001) / closes[-1], rel_tol=1e-9)
    assert math.isclose(float(feature["spread_to_atr_20"]), (12 * 0.00001) / 0.003, rel_tol=1e-9)
    assert feature["spread_liquidity_regime"] == "low_spread"
    assert feature["range_regime"] == "normal_range"
    assert feature["volume_liquidity_regime"] in {"normal_volume", "high_volume", "volume_spike"}

    returns = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))]
    expected_volatility_20 = population_std(returns[-20:])
    expected_volatility_100 = population_std(returns)
    assert math.isclose(float(feature["volatility_100"]), expected_volatility_100, rel_tol=1e-9)
    assert math.isclose(
        float(feature["volatility_ratio_20_100"]),
        expected_volatility_20 / expected_volatility_100,
        rel_tol=1e-9,
    )


def test_spread_point_size_conversion_for_eurusd_and_usdjpy() -> None:
    eurusd_features, eurusd_skipped = generate_features(
        [price_row(index, 1.1000 + index * 0.001, spread=10) for index in range(20)]
    )
    usdjpy_rows = [
        {**price_row(index, 150.0 + index * 0.01, spread=10), "symbol": "USDJPY"}
        for index in range(20)
    ]
    usdjpy_features, usdjpy_skipped = generate_features(usdjpy_rows, point_size=0.001)

    assert eurusd_skipped == 0
    assert usdjpy_skipped == 0
    assert eurusd_features[-1]["spread"] == 10
    assert math.isclose(float(eurusd_features[-1]["spread_price"]), 0.00010, rel_tol=1e-9)
    assert math.isclose(float(usdjpy_features[-1]["spread_price"]), 0.010, rel_tol=1e-9)


def test_xauusd_configured_point_size_converts_spread_points_to_price_units() -> None:
    features, skipped = generate_features(
        [xauusd_price_row(index, close=2000.0 + index) for index in range(20)],
        point_size=0.01,
    )

    feature = features[-1]

    assert skipped == 0
    assert feature["spread"] == 24
    assert math.isclose(float(feature["spread_price"]), 0.24, rel_tol=1e-9)
    assert math.isclose(float(feature["spread_return"]), 0.24 / float(feature["close"]), rel_tol=1e-9)
    assert math.isclose(float(feature["atr_20"]), 2.0, rel_tol=1e-9)
    assert math.isclose(float(feature["spread_to_atr_20"]), 0.24 / 2.0, rel_tol=1e-9)


def test_xauusd_missing_point_size_preserves_raw_spread_and_leaves_unit_features_null() -> None:
    features, skipped = generate_features([xauusd_price_row(index) for index in range(20)])

    feature = features[-1]

    assert skipped == 0
    assert feature["spread"] == 24
    assert feature["spread_price"] is None
    assert feature["spread_return"] is None
    assert feature["spread_to_atr_20"] is None


def test_strict_point_size_fails_when_symbol_has_no_safe_default() -> None:
    with pytest.raises(ValueError, match="point_size"):
        resolve_point_size("XAUUSD", strict=True)


def test_xauusd_point_size_can_use_symbol_metadata_config_shape(tmp_path: Path) -> None:
    config_path = tmp_path / "symbol_metadata.local.json"
    config_path.write_text(
        """
        {
          "XAUUSD": {
            "point_size": 0.01,
            "digits": 2,
            "trade_tick_size": 0.01,
            "trade_contract_size": 100.0,
            "source": "mt5_symbol_info_point"
          }
        }
        """,
        encoding="utf-8",
    )

    point_size, source = resolve_point_size("XAUUSD", point_size_config=config_path, strict=True)

    assert point_size == 0.01
    assert source == "symbol_metadata_config_symbol"


def test_xauusd_point_size_can_be_config_driven(tmp_path: Path) -> None:
    config_path = tmp_path / "cost_config.json"
    config_path.write_text(
        '{"symbols": {"XAUUSD": {"point_size": 0.01}}}',
        encoding="utf-8",
    )

    point_size, source = resolve_point_size("XAUUSD", point_size_config=config_path, strict=True)

    assert point_size == 0.01
    assert source == "point_size_config_symbol"


def market_row(index: int, close: float, high: float | None = None, low: float | None = None) -> dict[str, object]:
    row = {column: None for column in INPUT_COLUMNS}
    timestamp = datetime(2024, 1, 1) + timedelta(minutes=15 * index)
    row.update(
        {
            "symbol": "EURUSD",
            "timeframe": "M15",
            "time_server": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "open": close,
            "high": close + 0.5 if high is None else high,
            "low": close - 0.5 if low is None else low,
            "close": close,
            "tick_volume": 100,
            "spread": 12,
            "hour": timestamp.hour,
            "day_of_week": timestamp.weekday(),
            "relevant_currencies": "EUR,USD",
        }
    )
    return row


def barrier_rows(length: int = 12) -> list[dict[str, object]]:
    rows = [market_row(index, 100.0, high=100.5, low=99.5) for index in range(length)]
    rows[0]["atr_20"] = 1.0
    return rows


def test_generate_ml_dataset_calculates_future_mfe_mae_targets_and_tail_nulls() -> None:
    rows = [market_row(index, 100.0) for index in range(30)]
    rows[3].update({"high": 106.0, "low": 97.0})
    rows[5]["close"] = 101.0

    rows[7].update({"close": 100.0, "high": 100.5, "low": 99.5})
    for index in range(8, 13):
        rows[index].update({"close": 100.0, "high": 101.0, "low": 99.0})
    rows[10]["low"] = 95.0
    rows[12]["close"] = 99.0

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    long_row = generated[0]
    assert math.isclose(float(long_row["future_return_5"]), 0.01)
    assert math.isclose(float(long_row["future_max_return_5"]), 0.06)
    assert math.isclose(float(long_row["future_min_return_5"]), -0.03)
    assert math.isclose(float(long_row["future_range_5"]), 0.09)
    assert math.isclose(float(long_row["long_mfe_5"]), 0.06)
    assert math.isclose(float(long_row["long_mae_5"]), -0.03)
    assert math.isclose(float(long_row["short_mfe_5"]), 0.03)
    assert math.isclose(float(long_row["short_mae_5"]), -0.06)
    assert long_row["target_long_good_5"] == 1
    assert long_row["target_short_good_5"] == 0

    short_row = generated[7]
    assert math.isclose(float(short_row["future_return_5"]), -0.01)
    assert math.isclose(float(short_row["future_max_return_5"]), 0.01)
    assert math.isclose(float(short_row["future_min_return_5"]), -0.05)
    assert math.isclose(float(short_row["short_mfe_5"]), 0.05)
    assert math.isclose(float(short_row["short_mae_5"]), -0.01)
    assert short_row["target_long_good_5"] == 0
    assert short_row["target_short_good_5"] == 1

    assert generated[-6]["future_return_5"] is not None
    assert generated[-5]["future_return_5"] is None
    assert generated[-5]["future_max_return_5"] is None
    assert generated[-5]["target_long_good_5"] is None
    assert generated[-21]["future_return_20"] is not None
    assert generated[-20]["future_return_20"] is None
    assert generated[-20]["future_min_return_20"] is None


def test_generate_ml_dataset_derives_blank_research_regime_labels() -> None:
    rows = [market_row(index, 100.0) for index in range(30)]
    for row in rows:
        row.update(
            {
                "session": None,
                "spread_liquidity_regime": None,
                "volatility_regime": None,
                "range_regime": None,
                "volume_liquidity_regime": None,
                "spread_to_atr_20": 0.20,
                "volatility_ratio_20_100": 1.50,
                "range_to_atr_20": 1.00,
                "volume_spike_20": 0,
                "volume_dry_up_20": 1,
            }
        )

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    assert generated[0]["session"] == "Asia"
    assert generated[0]["spread_liquidity_regime"] == "high_spread"
    assert generated[0]["volatility_regime"] == "high_volatility"
    assert generated[0]["range_regime"] == "normal_range"
    assert generated[0]["volume_liquidity_regime"] == "dry_volume"


def test_triple_barrier_long_tp_first() -> None:
    rows = barrier_rows()
    rows[3].update({"high": 101.1, "low": 99.5})

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    assert generated[0]["long_tp_1atr_sl_1atr_hit_first_10"] == 1
    assert generated[0]["long_triple_barrier_1_1_10"] == 1
    assert generated[0]["long_tp_1atr_sl_1atr_bars_to_first_barrier_10"] == 3


def test_triple_barrier_columns_are_generated_for_h5_h10_h20() -> None:
    rows = barrier_rows(length=25)
    rows[3].update({"high": 102.1, "low": 99.5})

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    for horizon in (5, 10, 20):
        assert f"long_tp_1_5atr_sl_1atr_hit_first_{horizon}" in generated[0]
        assert f"short_tp_1_5atr_sl_1atr_hit_first_{horizon}" in generated[0]
        assert f"long_tp_2atr_sl_1atr_hit_first_{horizon}" in generated[0]
        assert f"short_tp_2atr_sl_1atr_hit_first_{horizon}" in generated[0]
    assert generated[0]["long_tp_1_5atr_sl_1atr_hit_first_5"] == 1
    assert generated[0]["long_tp_1_5atr_sl_1atr_hit_first_10"] == 1
    assert generated[0]["long_tp_1_5atr_sl_1atr_hit_first_20"] == 1
    assert generated[0]["long_tp_2atr_sl_1atr_hit_first_5"] == 1
    assert generated[0]["long_tp_2atr_sl_1atr_hit_first_10"] == 1
    assert generated[0]["long_tp_2atr_sl_1atr_hit_first_20"] == 1
    assert generated[0]["long_triple_barrier_2_1_10"] == 1
    assert generated[0]["long_tp_2atr_sl_1atr_bars_to_first_barrier_10"] == 3


def test_one_and_half_atr_long_and_short_target_labels_are_directional() -> None:
    rows = barrier_rows(length=25)
    rows[2].update({"high": 100.5, "low": 98.4})

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    assert generated[0]["long_tp_1_5atr_sl_1atr_hit_first_5"] == 0
    assert generated[0]["long_triple_barrier_1_5_1_5"] == -1
    assert generated[0]["short_tp_1_5atr_sl_1atr_hit_first_5"] == 1
    assert generated[0]["short_triple_barrier_1_5_1_5"] == 1


def test_triple_barrier_long_and_short_target_labels_are_directional() -> None:
    rows = barrier_rows(length=25)
    rows[2].update({"high": 100.5, "low": 97.8})

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    assert generated[0]["long_tp_2atr_sl_1atr_hit_first_5"] == 0
    assert generated[0]["long_triple_barrier_2_1_5"] == -1
    assert generated[0]["short_tp_2atr_sl_1atr_hit_first_5"] == 1
    assert generated[0]["short_triple_barrier_2_1_5"] == 1


def test_triple_barrier_long_sl_first() -> None:
    rows = barrier_rows()
    rows[2].update({"high": 100.5, "low": 98.9})

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    assert generated[0]["long_tp_1atr_sl_1atr_hit_first_10"] == 0
    assert generated[0]["long_triple_barrier_1_1_10"] == -1
    assert generated[0]["long_tp_1atr_sl_1atr_bars_to_first_barrier_10"] == 2


def test_triple_barrier_short_tp_first() -> None:
    rows = barrier_rows()
    rows[4].update({"high": 100.5, "low": 98.8})

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    assert generated[0]["short_tp_1atr_sl_1atr_hit_first_10"] == 1
    assert generated[0]["short_triple_barrier_1_1_10"] == 1
    assert generated[0]["short_tp_1atr_sl_1atr_bars_to_first_barrier_10"] == 4


def test_triple_barrier_short_sl_first() -> None:
    rows = barrier_rows()
    rows[5].update({"high": 101.1, "low": 99.5})

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    assert generated[0]["short_tp_1atr_sl_1atr_hit_first_10"] == 0
    assert generated[0]["short_triple_barrier_1_1_10"] == -1
    assert generated[0]["short_tp_1atr_sl_1atr_bars_to_first_barrier_10"] == 5


def test_triple_barrier_same_bar_tp_sl_uses_stop_first() -> None:
    rows = barrier_rows()
    rows[1].update({"high": 101.5, "low": 98.5})

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    assert generated[0]["long_tp_1atr_sl_1atr_hit_first_10"] == 0
    assert generated[0]["long_tp_1_5atr_sl_1atr_hit_first_10"] == 0
    assert generated[0]["long_triple_barrier_1_5_1_10"] == -1
    assert generated[0]["long_tp_1_5atr_sl_1atr_bars_to_first_barrier_10"] == 1
    assert generated[0]["long_triple_barrier_1_1_10"] == -1
    assert generated[0]["long_tp_1atr_sl_1atr_bars_to_first_barrier_10"] == 1
    assert generated[0]["long_tp_1atr_sl_1atr_hit_first_5"] == 0
    assert generated[0]["long_triple_barrier_1_1_5"] == -1
    assert generated[0]["long_tp_1atr_sl_1atr_bars_to_first_barrier_5"] == 1
    assert generated[0]["short_tp_1atr_sl_1atr_hit_first_10"] == 0
    assert generated[0]["short_tp_1_5atr_sl_1atr_hit_first_10"] == 0
    assert generated[0]["short_triple_barrier_1_5_1_10"] == -1
    assert generated[0]["short_tp_1_5atr_sl_1atr_bars_to_first_barrier_10"] == 1
    assert generated[0]["short_triple_barrier_1_1_10"] == -1
    assert generated[0]["short_tp_1atr_sl_1atr_bars_to_first_barrier_10"] == 1
    assert generated[0]["short_tp_1atr_sl_1atr_hit_first_5"] == 0
    assert generated[0]["short_triple_barrier_1_1_5"] == -1
    assert generated[0]["short_tp_1atr_sl_1atr_bars_to_first_barrier_5"] == 1


def test_triple_barrier_tail_rows_without_full_horizon_are_null() -> None:
    rows = barrier_rows(length=10)

    generated, skipped = generate_rows(rows, min_return_threshold=0.0)

    assert skipped == 0
    assert generated[0]["long_tp_1atr_sl_1atr_hit_first_10"] is None
    assert generated[0]["long_triple_barrier_1_1_10"] is None
    assert generated[0]["long_tp_1atr_sl_1atr_bars_to_first_barrier_10"] is None
    assert generated[0]["short_tp_1atr_sl_1atr_hit_first_10"] is None
    assert generated[0]["short_triple_barrier_1_1_10"] is None
    assert generated[0]["short_tp_1atr_sl_1atr_bars_to_first_barrier_10"] is None
    assert generated[0]["long_tp_1atr_sl_1atr_hit_first_20"] is None
    assert generated[0]["short_tp_1atr_sl_1atr_hit_first_20"] is None


def test_ml_research_excludes_unsafe_columns_and_keeps_normalized_context_features() -> None:
    pd = pytest.importorskip("pandas")
    data = pd.DataFrame(
        {
            "symbol": ["EURUSD"] * 4,
            "timeframe": ["M15"] * 4,
            "time_server": [f"2024-01-01 00:{index:02d}:00" for index in range(4)],
            "open": [1.1000, 1.1005, 1.1010, 1.1015],
            "high": [1.1010, 1.1015, 1.1020, 1.1025],
            "low": [1.0990, 1.0995, 1.1000, 1.1005],
            "close": [1.1002, 1.1007, 1.1012, 1.1017],
            "tick_volume": [100, 110, 120, 130],
            "spread": [10, 11, 12, 13],
            "feature_alpha": [1.0, 2.0, 3.0, 4.0],
            "feature_beta": [4.0, 3.0, 2.0, 1.0],
            "spread_price": [0.00010, 0.00011, 0.00012, 0.00013],
            "spread_return": [0.00009, 0.00010, 0.00011, 0.00012],
            "spread_to_atr_20": [0.05, 0.06, 0.07, 0.08],
            "tick_volume_ratio_20": [0.8, 0.9, 1.1, 1.2],
            "tick_volume_zscore_100": [-1.0, -0.5, 0.5, 1.0],
            "tick_volume_percentile_100": [0.25, 0.50, 0.75, 1.0],
            "volume_vs_hour_avg": [0.7, 0.9, 1.1, 1.3],
            "volume_vs_session_avg": [0.8, 1.0, 1.2, 1.4],
            "atr_20": [0.0020, 0.0021, 0.0022, 0.0023],
            "range_to_atr_20": [0.7, 0.8, 0.9, 1.0],
            "hour": [0, 1, 2, 3],
            "day_of_week": [0, 1, 2, 3],
            "future_return_10": [0.01, -0.01, 0.02, -0.02],
            "future_max_return_10": [0.02, 0.01, 0.03, 0.01],
            "future_min_return_10": [-0.01, -0.02, -0.01, -0.03],
            "future_range_10": [0.03, 0.03, 0.04, 0.04],
            "long_mfe_10": [0.02, 0.01, 0.03, 0.01],
            "long_mae_10": [-0.01, -0.02, -0.01, -0.03],
            "short_mfe_10": [0.01, 0.02, 0.01, 0.03],
            "short_mae_10": [-0.02, -0.01, -0.03, -0.01],
            "target_up_10": [1, 0, 1, 0],
            "target_down_10": [0, 1, 0, 1],
            "target_long_good_10": [1, 0, 1, 0],
            "target_short_good_10": [0, 1, 0, 1],
            "long_tp_1atr_sl_1atr_hit_first_10": [1, 0, 1, 0],
            "long_triple_barrier_1_1_10": [1, -1, 1, 0],
            "long_tp_1atr_sl_1atr_bars_to_first_barrier_10": [2, 3, 4, None],
            "short_tp_2atr_sl_1atr_hit_first_10": [0, 1, 0, 1],
            "short_triple_barrier_2_1_10": [-1, 1, 0, 1],
            "short_tp_2atr_sl_1atr_bars_to_first_barrier_10": [1, 2, None, 4],
            "custom_triple_barrier_label_10": [1, -1, 0, 1],
            "custom_hit_first_label_10": [1, 0, 1, 0],
            "custom_bars_to_first_barrier_10": [1, 2, 3, 4],
        }
    )

    _filtered, numeric_features, _y, _returns = prepare_numeric_features(
        pd,
        data,
        "target_up_10",
        "future_return_10",
    )

    assert set(numeric_features.columns) == {
        "feature_alpha",
        "feature_beta",
        "spread_price",
        "spread_return",
        "spread_to_atr_20",
        "tick_volume_ratio_20",
        "tick_volume_zscore_100",
        "tick_volume_percentile_100",
        "volume_vs_hour_avg",
        "volume_vs_session_avg",
        "atr_20",
        "range_to_atr_20",
        "hour",
        "day_of_week",
    }


def test_future_target_conditions_are_prechecked_as_leakage() -> None:
    assert precheck_combination_skip_reason("target_long_good_10:1") == FUTURE_TARGET_SKIP_REASON
    assert (
        precheck_combination_skip_reason("binary_feature:future_max_return_10:1")
        == FUTURE_TARGET_SKIP_REASON
    )
    assert (
        precheck_combination_skip_reason("long_triple_barrier_1_1_10:1")
        == FUTURE_TARGET_SKIP_REASON
    )


def test_feature_safety_excludes_generated_tp_sl_target_columns() -> None:
    unsafe_columns = [
        "long_tp_2atr_sl_1atr_hit_first_5",
        "long_tp_1_5atr_sl_1atr_hit_first_10",
        "short_tp_2atr_sl_1atr_hit_first_20",
        "short_tp_1_5atr_sl_1atr_hit_first_20",
        "long_triple_barrier_2_1_5",
        "short_triple_barrier_1_1_20",
        "bars_to_first_barrier_20",
    ]

    assert all(is_future_or_target_column(column) for column in unsafe_columns)


def test_research_validation_and_report_scripts_do_not_import_mt5_or_execution_api() -> None:
    blocked = re.compile(
        "|".join(
            [
                "order_" + "send",
                "place_" + "order",
                "execute_" + "trade",
                "open_" + "position",
                "close_" + "position",
                "trade_" + "send",
                "position_" + "open",
                "position_" + "close",
                "import " + "Meta" + "Trader5",
                "from " + "Meta" + "Trader5",
                "mt5" + r"\.",
            ]
        )
    )
    files = [
        REPO_ROOT / "scripts" / "generate_price_features.py",
        REPO_ROOT / "scripts" / "backtest_research.py",
        REPO_ROOT / "scripts" / "backtest_combined_hypotheses.py",
        REPO_ROOT / "scripts" / "validate_hypotheses_by_year.py",
        REPO_ROOT / "scripts" / "run_walk_forward_research.py",
        REPO_ROOT / "scripts" / "run_random_baseline_tests.py",
        REPO_ROOT / "scripts" / "run_candidate_baseline_diagnostics.py",
        REPO_ROOT / "scripts" / "build_research_decision_report.py",
        REPO_ROOT / "scripts" / "build_horizon_consistency_report.py",
        REPO_ROOT / "scripts" / "build_final_feature_scorecard.py",
        REPO_ROOT / "scripts" / "build_preferred_target_feature_stability.py",
        REPO_ROOT / "scripts" / "build_preferred_feature_hypothesis_shortlist.py",
        REPO_ROOT / "scripts" / "run_preferred_feature_backtests.py",
        REPO_ROOT / "scripts" / "compare_preferred_feature_backtest_cost_modes.py",
        REPO_ROOT / "scripts" / "run_preferred_feature_combination_backtests.py",
        REPO_ROOT / "scripts" / "run_tp_sl_path_backtests.py",
    ]

    matches = {
        str(path.relative_to(REPO_ROOT)): blocked.findall(path.read_text(encoding="utf-8"))
        for path in files
    }

    assert matches == {str(path.relative_to(REPO_ROOT)): [] for path in files}

