from datetime import datetime, timedelta
from pathlib import Path
import re

from scripts.time_split_utils import (
    apply_purge_train_test_split,
    downsample_non_overlapping_rows,
    horizon_to_timedelta,
    parse_time_server,
    parse_timeframe_to_minutes,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def row(timestamp: str) -> dict[str, object]:
    return {"time_server": timestamp}


def test_m15_horizon_10_is_150_minutes() -> None:
    assert parse_timeframe_to_minutes("M15") == 15
    assert horizon_to_timedelta("M15", 10) == timedelta(minutes=150)


def test_parse_time_server_accepts_iso_and_db_formats() -> None:
    assert parse_time_server("2024-01-02T03:04:05") == datetime(2024, 1, 2, 3, 4, 5)
    assert parse_time_server("2024-01-02 03:04:05") == datetime(2024, 1, 2, 3, 4, 5)
    assert parse_time_server("2024.01.02 03:04") == datetime(2024, 1, 2, 3, 4)


def test_purge_removes_train_rows_whose_label_reaches_test_start() -> None:
    rows = [
        row("2024-01-01T09:00:00"),
        row("2024-01-01T09:30:00"),
        row("2024-01-01T09:45:00"),
        row("2024-01-01T10:00:00"),
        row("2024-01-01T10:15:00"),
    ]
    train_rows, test_rows = apply_purge_train_test_split(
        rows,
        train_start="2024-01-01T09:00:00",
        train_end="2024-01-01T09:45:00",
        test_start="2024-01-01T10:00:00",
        test_end="2024-01-01T10:30:00",
        timeframe="M15",
        target_horizon=2,
    )
    assert [item["time_server"] for item in train_rows] == ["2024-01-01T09:00:00"]
    assert [item["time_server"] for item in test_rows] == [
        "2024-01-01T10:00:00",
        "2024-01-01T10:15:00",
    ]


def test_embargo_removes_first_test_bars() -> None:
    rows = [
        row("2024-01-01T09:00:00"),
        row("2024-01-01T10:00:00"),
        row("2024-01-01T10:15:00"),
        row("2024-01-01T10:30:00"),
    ]
    _train_rows, test_rows = apply_purge_train_test_split(
        rows,
        train_start="2024-01-01T09:00:00",
        train_end="2024-01-01T09:45:00",
        test_start="2024-01-01T10:00:00",
        test_end="2024-01-01T10:45:00",
        timeframe="M15",
        target_horizon=2,
        embargo_bars=2,
    )
    assert [item["time_server"] for item in test_rows] == ["2024-01-01T10:30:00"]


def test_downsample_keeps_one_row_every_target_horizon_bars() -> None:
    rows = [
        row("2024-01-01T10:00:00"),
        row("2024-01-01T10:15:00"),
        row("2024-01-01T10:30:00"),
        row("2024-01-01T10:45:00"),
        row("2024-01-01T11:00:00"),
    ]
    sampled = downsample_non_overlapping_rows(rows, "M15", 2)
    assert [item["time_server"] for item in sampled] == [
        "2024-01-01T10:00:00",
        "2024-01-01T10:30:00",
        "2024-01-01T11:00:00",
    ]


def test_overlapping_label_research_files_do_not_use_execution_or_terminal_api() -> None:
    blocked_terms = [
        "order_" + "send",
        "place_" + "order",
        "execute_" + "trade",
        "open_" + "position",
        "close_" + "position",
        "trade_" + "send",
        "position_" + "open",
        "position_" + "close",
        "import " + "Meta" + "Trader5",
        "from " + "Meta" + "Trader5",
        "mt5" + r"\.",
    ]
    blocked = re.compile("|".join(blocked_terms))
    files = [
        REPO_ROOT / "scripts" / "time_split_utils.py",
        REPO_ROOT / "scripts" / "ml_research.py",
        REPO_ROOT / "scripts" / "run_walk_forward_research.py",
        REPO_ROOT / "scripts" / "validate_hypotheses_by_year.py",
    ]
    matches = {
        str(path.relative_to(REPO_ROOT)): blocked.findall(path.read_text(encoding="utf-8"))
        for path in files
    }
    assert matches == {str(path.relative_to(REPO_ROOT)): [] for path in files}
