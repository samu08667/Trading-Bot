"""Shared market-session helpers for offline research scripts.

This module contains static time-bucket mapping only. It does not connect to
MetaTrader5, create signals, or perform any live trading action.
"""

from __future__ import annotations

SESSION_RANGES = {
    "Asia": tuple(range(0, 8)),
    "London": tuple(range(8, 14)),
    "New_York": tuple(range(14, 22)),
    "Off_hours": tuple(range(22, 24)),
}

SESSION_NAMES = tuple(SESSION_RANGES)


def normalize_session_name(value: object) -> str:
    normalized = str(value or "").strip().replace(" ", "_").replace("-", "_").lower()
    for session in SESSION_NAMES:
        if normalized == session.lower():
            return session
    raise ValueError(f"Unsupported hour_session bucket: {value!r}")


def session_name(hour: int | None) -> str | None:
    if hour is None:
        return None
    if 0 <= hour <= 7:
        return "Asia"
    if 8 <= hour <= 13:
        return "London"
    if 14 <= hour <= 21:
        return "New_York"
    return "Off_hours"


def hour_in_session(hour: int | None, session: object) -> bool:
    if hour is None:
        return False
    return session_name(hour) == normalize_session_name(session)
