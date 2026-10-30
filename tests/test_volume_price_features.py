import math

from scripts.generate_price_features import generate_features


def price_row(index: int, tick_volume: int, spread: int = 10) -> dict[str, object]:
    return {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "time_server": f"2024-01-01 10:{index:02d}:00",
        "open": 1.1000,
        "high": 1.1010,
        "low": 1.0990,
        "close": 1.1005,
        "tick_volume": tick_volume,
        "spread": spread,
    }


def last_feature_for_volumes(volumes: list[int], spread: int = 10) -> dict[str, object]:
    features, skipped = generate_features(
        [price_row(index, tick_volume, spread=spread) for index, tick_volume in enumerate(volumes)]
    )
    assert skipped == 0
    return features[-1]


def test_tick_volume_ratio_20_and_spike_flag() -> None:
    feature = last_feature_for_volumes([95] * 18 + [90, 200])

    assert math.isclose(float(feature["tick_volume_avg_20"]), 100.0)
    assert math.isclose(float(feature["tick_volume_ratio_20"]), 2.0)
    assert feature["volume_spike_20"] == 1
    assert feature["volume_dry_up_20"] == 0


def test_volume_dry_up_20_flag() -> None:
    feature = last_feature_for_volumes([100] * 18 + [130, 70])

    assert math.isclose(float(feature["tick_volume_ratio_20"]), 0.7)
    assert feature["volume_dry_up_20"] == 1
    assert feature["volume_spike_20"] == 0


def test_spread_to_volume_ratio_handles_zero_volume_without_crashing() -> None:
    feature = last_feature_for_volumes([0] * 20)

    assert feature["tick_volume_avg_20"] == 0
    assert feature["spread_to_volume_ratio"] is None


def test_volume_vs_hour_avg_uses_shifted_expanding_mean() -> None:
    features, skipped = generate_features([price_row(0, 100), price_row(1, 200), price_row(2, 9999)])

    assert skipped == 0
    assert features[0]["volume_vs_hour_avg"] is None
    assert math.isclose(float(features[1]["volume_vs_hour_avg"]), 2.0)
    assert math.isclose(float(features[2]["volume_vs_hour_avg"]), 9999 / 150)
    assert math.isclose(float(features[1]["volume_vs_session_avg"]), 2.0)
