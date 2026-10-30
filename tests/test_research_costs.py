import math

import pytest

from scripts.research_costs import (
    cost_adjusted_return_metrics,
    cost_report_warnings,
    default_point_size,
    estimate_spread_cost_return,
    estimate_total_cost_return,
    load_cost_config,
    validate_estimated_cost_config,
    validate_cost_args,
    net_strategy_return,
    strategy_return_components,
)


def test_eurusd_spread_cost_return() -> None:
    cost = estimate_spread_cost_return(
        {"spread": 10, "close": 1.10000},
        "EURUSD",
        default_point_size("EURUSD"),
        {},
    )
    assert cost is not None
    assert math.isclose(cost, 0.0000909, rel_tol=1e-3)


def test_usdjpy_spread_cost_return() -> None:
    cost = estimate_spread_cost_return(
        {"spread": 10, "close": 150},
        "USDJPY",
        default_point_size("USDJPY"),
        {},
    )
    assert cost is not None
    assert math.isclose(cost, 0.0000667, rel_tol=1e-3)


def test_xauusd_spread_cost_return() -> None:
    cost = estimate_spread_cost_return(
        {"spread": 25, "close": 2300},
        "XAUUSD",
        0.01,
        {},
    )
    assert cost is not None
    assert math.isclose(cost, 0.0001087, rel_tol=1e-3)


def test_xauusd_has_no_internal_point_size_without_config() -> None:
    assert default_point_size("XAUUSD") is None


def test_net_return_subtracts_estimated_cost() -> None:
    assert math.isclose(net_strategy_return(0.0020, 0.0003), 0.0017)


def test_return_mode_net_requires_estimated_cost_mode() -> None:
    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        validate_cost_args("none", "net")


def test_avg_positive_and_negative_returns_follow_return_mode() -> None:
    rows = [
        {"future_return_10": 0.0020, "time_server": "2024-01-01 00:00:00"},
        {"future_return_10": 0.0005, "time_server": "2024-01-01 00:15:00"},
        {"future_return_10": -0.0005, "time_server": "2024-01-01 00:30:00"},
    ]
    cost_config = {
        "default": {"slippage_bps_round_trip": 5.0},
        "symbols": {"EURUSD": {"point_size": 0.00001}},
    }

    gross_metrics = cost_adjusted_return_metrics(
        rows,
        symbol="EURUSD",
        return_column="future_return_10",
        direction="long",
        cost_config=cost_config,
        cost_mode="estimated",
        return_mode="gross",
    )
    net_metrics = cost_adjusted_return_metrics(
        rows,
        symbol="EURUSD",
        return_column="future_return_10",
        direction="long",
        cost_config=cost_config,
        cost_mode="estimated",
        return_mode="net",
    )

    assert math.isclose(float(gross_metrics["avg_positive_return"]), 0.00125)
    assert math.isclose(float(gross_metrics["avg_negative_return"]), -0.0005)
    assert math.isclose(float(gross_metrics["payoff_ratio"]), 2.5)
    assert math.isclose(float(gross_metrics["breakeven_winrate"]), 1 / 3.5)
    assert math.isclose(float(gross_metrics["breakeven_winrate_margin"]), (2 / 3) - (1 / 3.5))
    assert math.isclose(float(net_metrics["avg_positive_return"]), 0.0015)
    assert math.isclose(float(net_metrics["avg_negative_return"]), -0.0010)
    assert math.isclose(float(net_metrics["payoff_ratio"]), 1.5)
    assert math.isclose(float(net_metrics["breakeven_winrate"]), 0.4)
    assert math.isclose(float(net_metrics["breakeven_winrate_margin"]), (1 / 3) - 0.4)


def test_short_gross_return_is_negated_and_cost_is_subtracted() -> None:
    gross, cost, net = strategy_return_components(
        {"future_return_10": -0.0020, "spread": 10, "close": 1.10000},
        symbol="EURUSD",
        return_column="future_return_10",
        direction="short",
        cost_config={"default": {}, "symbols": {}},
        cost_mode="estimated",
    )
    assert gross == 0.0020
    assert cost is not None and cost > 0
    assert net is not None
    assert math.isclose(net, gross - cost)


def test_total_cost_supports_slippage_and_commission_bps() -> None:
    cost = estimate_total_cost_return(
        {"spread": 10, "close": 1.10000},
        "EURUSD",
        {
            "default": {
                "slippage_bps_round_trip": 1.0,
                "commission_bps_round_trip": 2.0,
            },
            "symbols": {},
        },
    )
    assert cost > 0.0000909


def test_strict_cost_config_passes_with_explicit_point_size_and_fallback() -> None:
    report = validate_estimated_cost_config(
        symbols=["EURUSD"],
        rows_by_symbol={"EURUSD": [{"close": 1.10000}]},
        config={
            "default": {},
            "symbols": {
                "EURUSD": {
                    "point_size": 0.00001,
                    "fallback_spread_points": 12,
                }
            },
        },
        strict=True,
    )

    assert report["EURUSD"]["point_size_source"] == "cost_config_symbol"
    assert report["EURUSD"]["spread_source_used"] == "cost_config_symbol_fallback_spread_points"


def test_strict_cost_config_fails_without_explicit_point_size() -> None:
    with pytest.raises(ValueError, match="EURUSD.*point_size"):
        validate_estimated_cost_config(
            symbols=["EURUSD"],
            rows_by_symbol={"EURUSD": [{"close": 1.10000, "spread": 10}]},
            config={
                "default": {},
                "symbols": {"EURUSD": {"fallback_spread_points": 12}},
            },
            strict=True,
        )


def test_non_strict_cost_config_warns_for_internal_defaults_without_crashing() -> None:
    report = validate_estimated_cost_config(
        symbols=["EURUSD"],
        rows_by_symbol={"EURUSD": [{"close": 1.10000}]},
        config=load_cost_config(),
        strict=False,
    )
    warnings = "\n".join(cost_report_warnings(report))

    assert report["EURUSD"]["point_size_source"] == "internal_default"
    assert report["EURUSD"]["spread_source_used"] == "internal_default_fallback_spread_points"
    assert "using internal default point_size" in warnings
    assert "using internal fallback_spread_points" in warnings
