import math

from scripts.research_metrics import (
    calculate_best_period_contribution_pct,
    calculate_payoff_ratio,
    calculate_period_positive_ratio,
    calculate_performance_concentration_metrics,
    calculate_return_metrics,
    calculate_top_trade_contribution_pct,
)


def test_monthly_positive_ratio_uses_compounded_month_returns() -> None:
    returns = [0.10, -0.05, -0.02, 0.03]
    timestamps = [
        "2024-01-02 10:00:00",
        "2024-01-15 10:00:00",
        "2024-02-02 10:00:00",
        "2024-03-02 10:00:00",
    ]

    assert math.isclose(calculate_period_positive_ratio(returns, timestamps, "month"), 2 / 3)


def test_quarterly_positive_ratio() -> None:
    returns = [0.02, -0.01, 0.03, -0.04]
    timestamps = [
        "2024-01-02 10:00:00",
        "2024-04-02 10:00:00",
        "2024-07-02 10:00:00",
        "2024-10-02 10:00:00",
    ]

    assert math.isclose(calculate_period_positive_ratio(returns, timestamps, "quarter"), 0.5)


def test_best_month_contribution_pct_uses_positive_month_profit_only() -> None:
    returns = [0.10, 0.05, -0.02]
    timestamps = [
        "2024-01-02 10:00:00",
        "2024-02-02 10:00:00",
        "2024-03-02 10:00:00",
    ]

    assert math.isclose(
        calculate_best_period_contribution_pct(returns, timestamps, "month"),
        0.10 / 0.15 * 100,
    )


def test_top_5_percent_trades_contribution_pct() -> None:
    returns = [0.50, 0.30, 0.20] + [0.0] * 17

    assert math.isclose(calculate_top_trade_contribution_pct(returns), 50.0)


def test_performance_concentration_metrics_wrapper() -> None:
    returns = [0.10, -0.05, -0.02, 0.03]
    timestamps = [
        "2024-01-02T10:00:00",
        "2024-01-15T10:00:00",
        "2024-02-02T10:00:00",
        "2024-03-02T10:00:00",
    ]
    metrics = calculate_performance_concentration_metrics(returns, timestamps)

    assert math.isclose(float(metrics["monthly_positive_ratio"]), 2 / 3)
    assert metrics["max_flat_period_bars"] == 3


def test_payoff_and_breakeven_metrics_are_calculated_from_returns() -> None:
    metrics = calculate_return_metrics([0.02, -0.01, 0.01, -0.01])

    assert metrics["trades_count"] == 4
    assert math.isclose(float(metrics["avg_positive_return"]), 0.015)
    assert math.isclose(float(metrics["avg_negative_return"]), -0.01)
    assert math.isclose(float(metrics["payoff_ratio"]), 1.5)
    assert math.isclose(float(metrics["breakeven_winrate"]), 0.4)
    assert math.isclose(float(metrics["win_rate"]), 0.5)
    assert math.isclose(float(metrics["breakeven_winrate_margin"]), 0.1)
    assert math.isclose(float(metrics["profit_factor"]), 1.5)


def test_payoff_metrics_handle_missing_positive_or_negative_returns() -> None:
    no_positive = calculate_return_metrics([-0.01, -0.02])
    no_negative = calculate_return_metrics([0.01, 0.02])

    assert no_positive["avg_positive_return"] is None
    assert no_positive["payoff_ratio"] is None
    assert no_positive["breakeven_winrate"] is None
    assert no_positive["breakeven_winrate_margin"] is None

    assert no_negative["avg_negative_return"] is None
    assert no_negative["payoff_ratio"] is None
    assert no_negative["breakeven_winrate"] is None
    assert no_negative["breakeven_winrate_margin"] is None


def test_payoff_ratio_handles_zero_negative_average() -> None:
    assert calculate_payoff_ratio(0.01, 0.0) is None
