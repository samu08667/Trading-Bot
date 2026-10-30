from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts import export_fixed_candidate_mt5_raw_source_parity_dataset as export


SPEC_PATH = Path("config/strategy_specs/gbpusd_short_h10_1_5_off_hours_strategy_spec.json")


def raw_row(
    time_server: datetime,
    *,
    open_price: float = 1.2,
    high: float = 1.2005,
    low: float = 1.1995,
    close: float = 1.2,
    tick_volume: int = 100,
    spread: int = 6,
) -> dict[str, object]:
    return {
        "time_server": time_server.strftime("%Y-%m-%d %H:%M:%S"),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "tick_volume": tick_volume,
        "spread": spread,
    }


def write_raw_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=export.RAW_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_spec() -> dict[str, object]:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def continuous_raw_rows(count: int, *, start: datetime) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(count):
        rows.append(
            raw_row(
                start + index * timedelta(minutes=15),
                close=1.2 + index * 0.000001,
                high=1.2005 + index * 0.000001,
                low=1.1995 + index * 0.000001,
                tick_volume=(index % 100) + 1,
            )
        )
    return rows


def test_strategy_spec_contains_no_weekend_hold_policy() -> None:
    spec = read_spec()
    lifecycle = spec["trade_lifecycle"]  # type: ignore[index]
    assert lifecycle["max_holding_bars"] == 10
    assert lifecycle["no_weekend_hold"] is True
    assert lifecycle["forced_friday_exit_enabled"] is True
    assert lifecycle["friday_last_entry_time_server"] == "23:15"
    assert lifecycle["friday_forced_flat_time_server"] == "23:45"
    assert lifecycle["time_basis"] == "mt5_server_time"
    assert lifecycle["weekend_crossing_allowed"] is False


def test_export_from_mt5_raw_csv_includes_required_columns_and_no_runtime_calls(tmp_path: Path) -> None:
    raw_csv = tmp_path / "raw.csv"
    output_csv = tmp_path / "raw_source_parity.csv"
    write_raw_csv(raw_csv, continuous_raw_rows(130, start=datetime(2026, 6, 26, 0, 0)))

    summary = export.export_raw_source_parity_dataset(
        strategy_spec_path=SPEC_PATH,
        mt5_raw_csv=raw_csv,
        output_csv=output_csv,
        overwrite=True,
    )

    rows = read_csv(output_csv)
    diagnostics = json.loads(Path(summary["diagnostics_json"]).read_text(encoding="utf-8"))
    assert set(export.EXPORT_FIELDNAMES).issubset(rows[0].keys())
    assert summary["raw_rows_read"] == 130
    assert summary["rows_exported"] == 31
    assert diagnostics["database_read_performed"] is False
    assert diagnostics["mt5_connection_performed"] is False
    assert diagnostics["order_check_performed"] is False
    assert diagnostics["order_send_performed"] is False
    assert diagnostics["trade_operation_performed"] is False


def test_recomputes_atr_ma_and_inclusive_percentile_from_past_bars(tmp_path: Path) -> None:
    raw_csv = tmp_path / "raw.csv"
    output_csv = tmp_path / "raw_source_parity.csv"
    start = datetime(2026, 6, 22, 0, 0)
    rows = [
        raw_row(
            start + index * timedelta(minutes=15),
            high=1.2010,
            low=1.2,
            close=1.2005,
            tick_volume=index + 1,
        )
        for index in range(100)
    ]
    rows.append(
        raw_row(
            start + 100 * timedelta(minutes=15),
            high=1.2010,
            low=1.2,
            close=1.2005,
            tick_volume=50,
        )
    )
    write_raw_csv(raw_csv, rows)

    export.export_raw_source_parity_dataset(
        strategy_spec_path=SPEC_PATH,
        mt5_raw_csv=raw_csv,
        output_csv=output_csv,
        overwrite=True,
    )

    exported = read_csv(output_csv)
    first_exported = exported[0]
    second_exported = exported[1]
    assert first_exported["time_server"] == "2026-06-23 00:45:00"
    assert float(first_exported["atr_20"]) == pytest.approx(0.001)
    assert float(first_exported["ma_fast"]) == pytest.approx(1.2005)
    assert float(first_exported["tick_volume_percentile_100"]) == pytest.approx(1.0)
    assert float(second_exported["tick_volume_percentile_100"]) == pytest.approx(0.5)


def test_signal_bool_uses_strategy_spec_rules(tmp_path: Path) -> None:
    raw_csv = tmp_path / "raw.csv"
    output_csv = tmp_path / "raw_source_parity.csv"
    start = datetime(2026, 6, 25, 21, 45)
    rows = [
        raw_row(
            start + index * timedelta(minutes=15),
            open_price=1.2,
            high=1.2005,
            low=1.1995,
            close=1.2,
            tick_volume=index + 1,
        )
        for index in range(99)
    ]
    rows.append(
        raw_row(
            datetime(2026, 6, 26, 22, 30),
            open_price=1.2,
            high=1.2012,
            low=1.2008,
            close=1.201,
            tick_volume=20,
            spread=6,
        )
    )
    for index in range(10):
        rows.append(raw_row(datetime(2026, 6, 26, 22, 45) + index * timedelta(minutes=15)))
    write_raw_csv(raw_csv, rows)

    export.export_raw_source_parity_dataset(
        strategy_spec_path=SPEC_PATH,
        mt5_raw_csv=raw_csv,
        output_csv=output_csv,
        overwrite=True,
    )

    signal_row = read_csv(output_csv)[0]
    assert signal_row["hour_session"] == "Off_hours"
    assert signal_row["close_to_ma_fast_atr_20_bucket"] == "high_tercile"
    assert signal_row["tick_volume_percentile_100_bucket"] == "mid_tercile"
    assert signal_row["signal_bool"] == "true"
    assert float(signal_row["entry_reference_price"]) == pytest.approx(1.201)
    assert signal_row["max_holding_bars"] == "10"
    assert signal_row["max_exit_time_server"] == "2026-06-26 23:45:00"


@pytest.mark.parametrize(
    ("value", "low_mid", "mid_high", "expected"),
    [
        (-0.4303672057741361, -0.4303672057741361, 0.5954421525644814, "low_tercile"),
        (-0.1, -0.4303672057741361, 0.5954421525644814, "mid_tercile"),
        (0.5954421525644814, -0.4303672057741361, 0.5954421525644814, "mid_tercile"),
        (0.7, -0.4303672057741361, 0.5954421525644814, "high_tercile"),
    ],
)
def test_bucket_rules_are_inclusive_at_low_and_mid_high_cutoffs(
    value: float,
    low_mid: float,
    mid_high: float,
    expected: str,
) -> None:
    assert export.bucket_for_value(value, low_mid, mid_high) == expected


def test_max_exit_time_uses_tenth_real_m15_bar_and_blanks_on_gap(tmp_path: Path) -> None:
    raw_csv = tmp_path / "raw.csv"
    output_csv = tmp_path / "raw_source_parity.csv"
    start = datetime(2026, 6, 22, 0, 0)
    rows = continuous_raw_rows(111, start=start)
    rows.pop(109)
    write_raw_csv(raw_csv, rows)

    summary = export.export_raw_source_parity_dataset(
        strategy_spec_path=SPEC_PATH,
        mt5_raw_csv=raw_csv,
        output_csv=output_csv,
        overwrite=True,
    )

    exported = read_csv(output_csv)
    diagnostics = json.loads(Path(summary["diagnostics_json"]).read_text(encoding="utf-8"))
    first_exported = exported[0]
    assert first_exported["time_server"] == "2026-06-23 00:45:00"
    assert first_exported["max_exit_time_server"] == ""
    assert diagnostics["gap_count"] == 1
    assert diagnostics["non_weekend_gap_count"] == 1


def test_weekday_normal_max_exit_uses_tenth_future_m15_bar(tmp_path: Path) -> None:
    raw_csv = tmp_path / "raw.csv"
    output_csv = tmp_path / "raw_source_parity.csv"
    start = datetime(2026, 6, 22, 0, 0)
    write_raw_csv(raw_csv, continuous_raw_rows(111, start=start))

    export.export_raw_source_parity_dataset(
        strategy_spec_path=SPEC_PATH,
        mt5_raw_csv=raw_csv,
        output_csv=output_csv,
        overwrite=True,
    )

    first_exported = read_csv(output_csv)[0]
    assert first_exported["time_server"] == "2026-06-23 00:45:00"
    assert first_exported["max_exit_time_server"] == "2026-06-23 03:15:00"


def test_friday_after_last_entry_cutoff_is_not_future_entry_allowed_but_signal_unchanged(
    tmp_path: Path,
) -> None:
    raw_csv = tmp_path / "raw.csv"
    output_csv = tmp_path / "raw_source_parity.csv"
    spec = read_spec()
    start = datetime(2026, 6, 25, 22, 45)
    rows = [
        raw_row(
            start + index * timedelta(minutes=15),
            open_price=1.2,
            high=1.2005,
            low=1.1995,
            close=1.2,
            tick_volume=index + 1,
        )
        for index in range(99)
    ]
    rows.append(
        raw_row(
            datetime(2026, 6, 26, 23, 30),
            open_price=1.2,
            high=1.2012,
            low=1.2008,
            close=1.201,
            tick_volume=20,
            spread=6,
        )
    )
    rows.append(raw_row(datetime(2026, 6, 26, 23, 45)))
    write_raw_csv(raw_csv, rows)

    export.export_raw_source_parity_dataset(
        strategy_spec_path=SPEC_PATH,
        mt5_raw_csv=raw_csv,
        output_csv=output_csv,
        overwrite=True,
    )

    signal_row = read_csv(output_csv)[0]
    assert export.entry_allowed_by_lifecycle(datetime(2026, 6, 26, 23, 30), spec) is False
    assert signal_row["signal_bool"] == "true"
    assert signal_row["close_to_ma_fast_atr_20_bucket"] == "high_tercile"
    assert signal_row["tick_volume_percentile_100_bucket"] == "mid_tercile"
    assert signal_row["entry_reference_price"] != ""
    assert signal_row["sl_price_preview"] != ""
    assert signal_row["tp_price_preview"] != ""
    assert signal_row["max_exit_time_server"] == "2026-06-26 23:45:00"


def test_duplicate_raw_time_blocks(tmp_path: Path) -> None:
    raw_csv = tmp_path / "raw.csv"
    rows = [
        raw_row(datetime(2026, 6, 26, 0, 0)),
        raw_row(datetime(2026, 6, 26, 0, 0)),
    ]
    write_raw_csv(raw_csv, rows)

    with pytest.raises(ValueError, match="Duplicate raw time_server"):
        export.read_raw_bar_rows(raw_csv)


def test_static_safety_no_db_mt5_or_trade_calls() -> None:
    source = Path("scripts/export_fixed_candidate_mt5_raw_source_parity_dataset.py").read_text(
        encoding="utf-8"
    )
    assert "sqlite3" not in source
    assert "MetaTrader5" not in source
    assert ".order_check(" not in source
    assert ".order_send(" not in source
