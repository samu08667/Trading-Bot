"""Shared research-only metric helpers.

The helpers in this module do not create trading signals and do not call any
broker or MetaTrader5 APIs. They only summarize already prepared return series.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import math
from statistics import mean, median
from typing import Iterable


DIRECTIONS = ("long", "short")


def normalize_direction(value: object) -> str:
    direction = str(value or "long").strip().lower()
    if direction not in DIRECTIONS:
        raise ValueError("direction must be one of: long, short")
    return direction


def directional_return(value: object, direction: str) -> float | None:
    parsed = safe_float(value)
    if parsed is None or not math.isfinite(parsed):
        return None
    normalized = normalize_direction(direction)
    return parsed if normalized == "long" else -parsed


def target_column_for_direction(direction: str, horizon: int) -> str:
    normalized = normalize_direction(direction)
    prefix = "target_up" if normalized == "long" else "target_down"
    return f"{prefix}_{horizon}"


def safe_float(value: object) -> float | None:
    """Parse a numeric value and return None when it is missing or invalid."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def is_finite_number(value: object) -> bool:
    parsed = safe_float(value)
    return parsed is not None and math.isfinite(parsed)


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    """Divide two finite values without producing inf/NaN."""
    if numerator is None or denominator is None:
        return None
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator == 0:
        return None
    return numerator / denominator


def finite_returns(values: Iterable[object]) -> list[float]:
    returns: list[float] = []
    for value in values:
        parsed = safe_float(value)
        if parsed is not None and math.isfinite(parsed):
            returns.append(parsed)
    return returns


def calculate_cumulative_return(returns: Iterable[object]) -> float | None:
    """Compounded return: product(1 + return) - 1."""
    values = finite_returns(returns)
    if not values:
        return None
    total = 1.0
    for item in values:
        total *= 1 + item
    return total - 1


def calculate_max_drawdown(returns: Iterable[object]) -> float | None:
    """Return the worst drawdown on a compounded equity curve."""
    values = finite_returns(returns)
    if not values:
        return None
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for item in values:
        equity *= 1 + item
        peak = max(peak, equity)
        drawdown = equity / peak - 1 if peak else 0.0
        worst = min(worst, drawdown)
    return worst


def calculate_profit_factor(returns: Iterable[object]) -> float | None:
    """Gross gains divided by absolute gross losses."""
    values = finite_returns(returns)
    gains = sum(item for item in values if item > 0)
    losses = abs(sum(item for item in values if item < 0))
    if losses == 0:
        return None if gains == 0 else float("inf")
    return gains / losses


def calculate_win_rate(returns: Iterable[object]) -> float | None:
    values = finite_returns(returns)
    if not values:
        return None
    return sum(1 for item in values if item > 0) / len(values)


def calculate_payoff_ratio(avg_positive_return: object, avg_negative_return: object) -> float | None:
    positive = safe_float(avg_positive_return)
    negative = safe_float(avg_negative_return)
    if positive is None or negative is None:
        return None
    if not math.isfinite(positive) or not math.isfinite(negative):
        return None
    if positive <= 0 or negative == 0:
        return None
    payoff = positive / abs(negative)
    if not math.isfinite(payoff) or payoff <= 0:
        return None
    return payoff


def calculate_breakeven_winrate(payoff_ratio: object) -> float | None:
    payoff = safe_float(payoff_ratio)
    if payoff is None or not math.isfinite(payoff) or payoff <= 0:
        return None
    return 1 / (1 + payoff)


def calculate_breakeven_winrate_margin(win_rate: object, breakeven_winrate: object) -> float | None:
    parsed_win_rate = safe_float(win_rate)
    parsed_breakeven = safe_float(breakeven_winrate)
    if parsed_win_rate is None or parsed_breakeven is None:
        return None
    if not math.isfinite(parsed_win_rate) or not math.isfinite(parsed_breakeven):
        return None
    return parsed_win_rate - parsed_breakeven


def calculate_return_metrics(returns: Iterable[object]) -> dict[str, object]:
    """Calculate generic metrics for any finite return series, gross or net."""
    values = finite_returns(returns)
    positive_returns = [value for value in values if value > 0]
    negative_returns = [value for value in values if value < 0]
    avg_positive_return = mean(positive_returns) if positive_returns else None
    avg_negative_return = mean(negative_returns) if negative_returns else None
    win_rate = calculate_win_rate(values)
    payoff_ratio = calculate_payoff_ratio(avg_positive_return, avg_negative_return)
    breakeven_winrate = calculate_breakeven_winrate(payoff_ratio)
    return {
        "trades_count": len(values),
        "mean_return": mean(values) if values else None,
        "median_return": median(values) if values else None,
        "win_rate": win_rate,
        "cumulative_return": calculate_cumulative_return(values),
        "max_drawdown": calculate_max_drawdown(values),
        "profit_factor": calculate_profit_factor(values),
        "avg_positive_return": avg_positive_return,
        "avg_negative_return": avg_negative_return,
        "payoff_ratio": payoff_ratio,
        "breakeven_winrate": breakeven_winrate,
        "breakeven_winrate_margin": calculate_breakeven_winrate_margin(win_rate, breakeven_winrate),
    }


def parse_metric_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    if len(text) >= 10:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return None


def _period_key(timestamp: datetime, period: str) -> tuple[int, int]:
    if period == "month":
        return timestamp.year, timestamp.month
    if period == "quarter":
        return timestamp.year, (timestamp.month - 1) // 3 + 1
    raise ValueError(f"Unsupported concentration period: {period}")


def _period_cumulative_returns(
    returns: Iterable[object],
    timestamps: Iterable[object],
    period: str,
) -> list[float]:
    grouped: dict[tuple[int, int], list[float]] = defaultdict(list)
    for value, timestamp_value in zip(returns, timestamps):
        parsed_return = safe_float(value)
        timestamp = parse_metric_timestamp(timestamp_value)
        if parsed_return is None or not math.isfinite(parsed_return) or timestamp is None:
            continue
        grouped[_period_key(timestamp, period)].append(parsed_return)

    period_returns: list[float] = []
    for key in sorted(grouped):
        cumulative = calculate_cumulative_return(grouped[key])
        if cumulative is not None and math.isfinite(cumulative):
            period_returns.append(cumulative)
    return period_returns


def calculate_period_positive_ratio(
    returns: Iterable[object],
    timestamps: Iterable[object],
    period: str,
) -> float | None:
    period_returns = _period_cumulative_returns(returns, timestamps, period)
    if not period_returns:
        return None
    return sum(1 for value in period_returns if value > 0) / len(period_returns)


def calculate_best_period_contribution_pct(
    returns: Iterable[object],
    timestamps: Iterable[object],
    period: str,
) -> float | None:
    period_returns = _period_cumulative_returns(returns, timestamps, period)
    positive_period_returns = [value for value in period_returns if value > 0]
    total_positive = sum(positive_period_returns)
    if total_positive <= 0:
        return None
    return max(positive_period_returns) / total_positive * 100


def calculate_top_trade_contribution_pct(returns: Iterable[object], top_fraction: float = 0.05) -> float | None:
    values = finite_returns(returns)
    positive_total = sum(value for value in values if value > 0)
    if positive_total <= 0:
        return None
    top_count = max(1, math.ceil(len(values) * top_fraction))
    top_positive = sum(value for value in sorted(values, reverse=True)[:top_count] if value > 0)
    return top_positive / positive_total * 100


def calculate_max_flat_period_bars(returns: Iterable[object]) -> int | None:
    values = finite_returns(returns)
    if not values:
        return None
    equity = 1.0
    peak = 1.0
    current_flat = 0
    max_flat = 0
    for value in values:
        equity *= 1 + value
        if equity > peak:
            peak = equity
            current_flat = 0
        else:
            current_flat += 1
            max_flat = max(max_flat, current_flat)
    return max_flat


def calculate_performance_concentration_metrics(
    returns: Iterable[object],
    timestamps: Iterable[object],
) -> dict[str, object]:
    return_values = list(returns)
    timestamp_values = list(timestamps)
    return {
        "monthly_positive_ratio": calculate_period_positive_ratio(return_values, timestamp_values, "month"),
        "quarterly_positive_ratio": calculate_period_positive_ratio(return_values, timestamp_values, "quarter"),
        "best_month_contribution_pct": calculate_best_period_contribution_pct(return_values, timestamp_values, "month"),
        "top_5_percent_trades_contribution_pct": calculate_top_trade_contribution_pct(return_values, 0.05),
        "max_flat_period_bars": calculate_max_flat_period_bars(return_values),
    }


def calculate_profit_factor_improvement_pct(value: object, baseline: object) -> float | None:
    """Real percentage change in profit factor, where 5 means 5%."""
    scenario = safe_float(value)
    base = safe_float(baseline)
    if scenario is None or base is None or base == 0:
        return None
    if not math.isfinite(scenario) or not math.isfinite(base):
        return None
    return ((scenario - base) / abs(base)) * 100


def calculate_max_drawdown_improvement_pct(value: object, baseline: object) -> float | None:
    """Drawdown improvement percentage. Positive means drawdown improved."""
    scenario = safe_float(value)
    base = safe_float(baseline)
    if scenario is None or base is None:
        return None
    if not math.isfinite(scenario) or not math.isfinite(base):
        return None
    baseline_abs = abs(base)
    if baseline_abs == 0:
        return None
    scenario_abs = abs(scenario)
    return ((baseline_abs - scenario_abs) / baseline_abs) * 100


def csv_safe_value(value: object) -> object:
    """Return a CSV-safe scalar without raw inf/NaN values."""
    parsed = safe_float(value)
    if parsed is not None and not math.isfinite(parsed):
        return ""
    return "" if value is None else value
