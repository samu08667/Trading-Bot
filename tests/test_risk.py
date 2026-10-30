import pytest

from src.risk import (
    is_within_drawdown_limit,
    require_positive_number,
    validate_percentage_limit,
)


def test_require_positive_number_accepts_positive_values():
    assert require_positive_number(10, "amount") == 10
    assert require_positive_number(0.5, "amount") == 0.5


@pytest.mark.parametrize("value", [0, -1, "1", True])
def test_require_positive_number_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        require_positive_number(value, "amount")


def test_validate_percentage_limit_accepts_value_inside_limit():
    assert validate_percentage_limit(2.5, "risk_pct", max_value=5) == 2.5


def test_validate_percentage_limit_rejects_value_above_limit():
    with pytest.raises(ValueError, match="risk_pct deve essere minore o uguale"):
        validate_percentage_limit(6, "risk_pct", max_value=5)


def test_is_within_drawdown_limit_returns_read_only_boolean():
    assert is_within_drawdown_limit(4, 10) is True
    assert is_within_drawdown_limit(12, 10) is False
