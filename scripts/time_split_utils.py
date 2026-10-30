from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any, Iterable


SUPPORTED_TIMEFRAMES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


def parse_timeframe_to_minutes(timeframe: str) -> int:
    normalized = str(timeframe or "").strip().upper()
    if normalized in SUPPORTED_TIMEFRAMES:
        return SUPPORTED_TIMEFRAMES[normalized]

    match = re.fullmatch(r"([MHD])(\d+)", normalized)
    if not match:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")
    unit, value_text = match.groups()
    value = int(value_text)
    if value <= 0:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")
    if unit == "M":
        return value
    if unit == "H":
        return value * 60
    if unit == "D":
        return value * 1440
    raise ValueError(f"Unsupported timeframe: {timeframe!r}")


def horizon_to_timedelta(timeframe: str, target_horizon: int) -> timedelta:
    horizon = int(target_horizon)
    if horizon <= 0:
        raise ValueError("target_horizon must be greater than zero.")
    return timedelta(minutes=parse_timeframe_to_minutes(timeframe) * horizon)


def parse_time_server(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for date_format in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%Y.%m.%d %H:%M:%S",
                "%Y.%m.%d %H:%M",
            ):
                try:
                    parsed = datetime.strptime(text, date_format)
                    break
                except ValueError:
                    continue
            else:
                return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _row_time(row: Any) -> datetime | None:
    getter = getattr(row, "get", None)
    if callable(getter):
        return parse_time_server(getter("time_server"))
    return None


def _coerce_datetime(value: Any, name: str) -> datetime:
    parsed = parse_time_server(value)
    if parsed is None:
        raise ValueError(f"{name} must be a valid datetime.")
    return parsed


def apply_purge_train_test_split(
    rows: Iterable[Any],
    train_start: Any,
    train_end: Any,
    test_start: Any,
    test_end: Any,
    timeframe: str,
    target_horizon: int,
    purge_bars: int | None = None,
    embargo_bars: int = 0,
) -> tuple[list[Any], list[Any]]:
    train_start_dt = _coerce_datetime(train_start, "train_start")
    train_end_dt = _coerce_datetime(train_end, "train_end")
    test_start_dt = _coerce_datetime(test_start, "test_start")
    test_end_dt = _coerce_datetime(test_end, "test_end")
    if train_start_dt > train_end_dt:
        raise ValueError("train_start cannot be after train_end.")
    if test_start_dt > test_end_dt:
        raise ValueError("test_start cannot be after test_end.")

    explicit_purge_bars = target_horizon if purge_bars is None else int(purge_bars)
    if explicit_purge_bars < 0:
        raise ValueError("purge_bars cannot be negative.")
    if int(embargo_bars) < 0:
        raise ValueError("embargo_bars cannot be negative.")

    bar_delta = timedelta(minutes=parse_timeframe_to_minutes(timeframe))
    purge_delta = bar_delta * explicit_purge_bars
    effective_test_start = test_start_dt + bar_delta * int(embargo_bars)

    train_rows: list[Any] = []
    test_rows: list[Any] = []
    for row in rows:
        timestamp = _row_time(row)
        if timestamp is None:
            continue
        if train_start_dt <= timestamp <= train_end_dt:
            label_end_time = timestamp + purge_delta
            if label_end_time < test_start_dt:
                train_rows.append(row)
        elif effective_test_start <= timestamp <= test_end_dt:
            test_rows.append(row)

    return train_rows, test_rows


def downsample_non_overlapping_rows(
    rows: Iterable[Any],
    timeframe: str,
    target_horizon: int,
    anchor: str = "first",
) -> list[Any]:
    horizon = int(target_horizon)
    if horizon <= 0:
        raise ValueError("target_horizon must be greater than zero.")
    parse_timeframe_to_minutes(timeframe)

    timed_rows = [(timestamp, index, row) for index, row in enumerate(rows) if (timestamp := _row_time(row)) is not None]
    timed_rows.sort(key=lambda item: (item[0], item[1]))
    sorted_rows = [item[2] for item in timed_rows]
    if anchor == "first":
        return sorted_rows[::horizon]
    if anchor == "last":
        offset = max(horizon - 1, 0)
        return sorted_rows[offset::horizon]
    raise ValueError("anchor must be 'first' or 'last'.")
