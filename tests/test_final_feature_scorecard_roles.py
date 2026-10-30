from scripts.build_final_feature_scorecard import rule_role_for, tradability_note_for


def test_rule_role_mapping_for_common_research_features() -> None:
    cases = {
        ("ma_diff", "ma_diff_gt_0", ""): "trend_filter",
        ("return_20", "high_tercile", ""): "momentum_filter",
        ("volatility_20", "low_tercile", ""): "volatility_regime_filter",
        ("atr_20", "low_tercile", ""): "volatility_regime_filter",
        ("close_to_ma_fast_atr_20", "high_tercile", ""): "volatility_regime_filter",
        ("spread_avg_20", "low_tercile", ""): "execution_quality_filter",
        ("spread_return", "low_tercile", ""): "execution_quality_filter",
        ("spread_to_atr_20", "low_tercile", ""): "execution_quality_filter",
        ("tick_volume_avg_20", "high_tercile", ""): "volume_liquidity_filter",
        ("volume_spike_20", "1", ""): "volume_liquidity_filter",
        ("hour_session", "London", ""): "session_filter",
        ("day_of_week", "Monday", ""): "calendar_filter",
        ("has_high_impact_news_next_30m", "1", ""): "news_risk_filter",
        ("open", "1", "raw_price_level_excluded"): "not_tradable_alone",
        ("volatility_20", "low_tercile", "numeric_tercile_not_time_safe"): "not_tradable_alone",
    }

    for (feature, condition, exclusion_reason), expected_role in cases.items():
        assert rule_role_for(feature, condition, exclusion_reason) == expected_role


def test_not_tradable_note_is_explicit() -> None:
    note = tradability_note_for(
        "not_tradable_alone",
        "volatility_20",
        "numeric_tercile_not_time_safe",
    )

    assert "Not tradable alone" in note
    assert "train-only" in note


def test_volume_liquidity_note_is_not_directional() -> None:
    note = tradability_note_for("volume_liquidity_filter", "volume_spike_20")

    assert "Volume/liquidity context filter" in note
    assert "not define direction alone" in note
