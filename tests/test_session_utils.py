import pytest

from scripts.session_utils import (
    SESSION_RANGES,
    hour_in_session,
    normalize_session_name,
    session_name,
)


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, "Asia"),
        (7, "Asia"),
        (8, "London"),
        (13, "London"),
        (14, "New_York"),
        (21, "New_York"),
        (22, "Off_hours"),
        (23, "Off_hours"),
    ],
)
def test_session_name_boundaries(hour: int, expected: str) -> None:
    assert session_name(hour) == expected


def test_session_ranges_match_boundary_mapping() -> None:
    assert SESSION_RANGES["Asia"] == tuple(range(0, 8))
    assert SESSION_RANGES["London"] == tuple(range(8, 14))
    assert SESSION_RANGES["New_York"] == tuple(range(14, 22))
    assert SESSION_RANGES["Off_hours"] == tuple(range(22, 24))


def test_hour_in_session_normalizes_names() -> None:
    assert hour_in_session(14, "New York")
    assert hour_in_session(23, "off-hours")
    assert not hour_in_session(13, "New_York")


def test_normalize_session_name_rejects_unknown_bucket() -> None:
    with pytest.raises(ValueError, match="Unsupported hour_session bucket"):
        normalize_session_name("Overlap")
