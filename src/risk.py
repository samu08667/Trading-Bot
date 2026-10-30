"""Safe, read-only risk validation helpers.

This module only validates numeric parameters. It does not calculate orders, size
positions, send instructions to brokers, or manage live trading state.
"""


def require_positive_number(value: int | float, name: str = "value") -> int | float:
    """Return ``value`` when it is numeric and strictly positive."""

    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{name} deve essere un numero.")
    if value <= 0:
        raise ValueError(f"{name} deve essere maggiore di zero.")
    return value


def validate_percentage_limit(value: int | float, name: str = "percentage", max_value: float = 100) -> int | float:
    """Validate that a percentage-like value is within ``0 < value <= max_value``."""

    require_positive_number(max_value, "max_value")
    require_positive_number(value, name)
    if value > max_value:
        raise ValueError(f"{name} deve essere minore o uguale a {max_value}.")
    return value


def is_within_drawdown_limit(current_drawdown_pct: int | float, max_drawdown_pct: int | float) -> bool:
    """Check whether a read-only drawdown metric is inside the configured limit."""

    validate_percentage_limit(current_drawdown_pct, "current_drawdown_pct")
    validate_percentage_limit(max_drawdown_pct, "max_drawdown_pct")
    return current_drawdown_pct <= max_drawdown_pct
