from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts import compare_fixed_candidate_mt5_ea_parity as compare


def base_row(**overrides: str) -> dict[str, str]:
    row = {
        "time_server": "2026-06-26 22:30:00",
        "hour_session": "Off_hours",
        "atr_20": "0.0006",
        "ma_fast": "1.2496",
        "close_to_ma_fast_atr_20": "0.7",
        "tick_volume_percentile_100": "0.2",
        "close_to_ma_fast_atr_20_bucket": "high_tercile",
        "tick_volume_percentile_100_bucket": "mid_tercile",
        "signal_bool": "true",
        "entry_reference_price": "1.25",
        "sl_price_preview": "1.2506",
        "tp_price_preview": "1.2491",
        "max_holding_bars": "10",
        "max_exit_time_server": "2026-06-27 01:00:00",
    }
    row.update(overrides)
    return row


def write_parity_csv(
    path: Path,
    rows: list[dict[str, str]],
    *,
    fieldnames: list[str] | None = None,
) -> None:
    fields = fieldnames or compare.REQUIRED_COLUMNS
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run_compare(
    tmp_path: Path,
    *,
    python_rows: list[dict[str, str]],
    mql5_rows: list[dict[str, str]],
    numeric_tolerance: float = 1e-9,
    near_threshold_epsilon: float = 0.02,
    allow_extra_mql5_times: bool = False,
) -> tuple[dict[str, object], Path]:
    python_csv = tmp_path / "python.csv"
    mql5_csv = tmp_path / "mql5.csv"
    output_dir = tmp_path / "comparison"
    write_parity_csv(python_csv, python_rows)
    write_parity_csv(mql5_csv, mql5_rows)
    manifest = compare.compare_parity_csvs(
        python_csv=python_csv,
        mql5_csv=mql5_csv,
        output_dir=output_dir,
        numeric_tolerance=numeric_tolerance,
        near_threshold_epsilon=near_threshold_epsilon,
        allow_extra_mql5_times=allow_extra_mql5_times,
    )
    return manifest, output_dir


def test_perfect_match_join_by_time_writes_acceptance_artifacts(tmp_path: Path) -> None:
    first = base_row(time_server="2026-06-26 22:30:00")
    second = base_row(time_server="2026-06-26 22:45:00", signal_bool="false", max_exit_time_server="")
    manifest, output_dir = run_compare(
        tmp_path,
        python_rows=[first, second],
        mql5_rows=[second, first],
    )

    assert manifest["acceptance_passed"] is True
    assert manifest["python_row_count"] == 2
    assert manifest["mql5_row_count"] == 2
    assert manifest["aligned_row_count"] == 2
    assert manifest["time_server_match_rate"] == 1.0
    assert manifest["signal_bool_match_rate"] == 1.0
    assert manifest["bucket_match_rate"] == 1.0
    assert manifest["hour_session_match_rate"] == 1.0
    assert manifest["max_holding_bars_match_rate"] == 1.0
    assert manifest["max_exit_time_server_match_rate"] == 1.0
    assert manifest["numeric_within_tolerance_rate"] == 1.0
    assert (output_dir / compare.MANIFEST_NAME).exists()
    assert (output_dir / compare.SUMMARY_NAME).exists()
    assert (output_dir / compare.MISMATCHES_NAME).exists()
    assert (output_dir / compare.MISSING_TIMES_NAME).exists()
    assert (output_dir / compare.EXTRA_TIMES_NAME).exists()
    assert (output_dir / compare.NEAR_MISSES_NAME).exists()
    assert (output_dir / compare.REPORT_NAME).exists()
    assert read_csv(output_dir / compare.MISMATCHES_NAME) == []


def test_extra_mql5_times_fail_by_default(tmp_path: Path) -> None:
    extra = base_row(time_server="2026-06-26 23:00:00")
    manifest, output_dir = run_compare(
        tmp_path,
        python_rows=[base_row()],
        mql5_rows=[base_row(), extra],
    )

    mismatches = read_csv(output_dir / compare.MISMATCHES_NAME)
    extra_times = read_csv(output_dir / compare.EXTRA_TIMES_NAME)
    assert manifest["acceptance_passed"] is False
    assert manifest["extra_mql5_time_count"] == 1
    assert manifest["extra_mql5_time_blocking_count"] == 1
    assert mismatches[0]["mismatch_type"] == "extra_mql5_time"
    assert extra_times[0]["time_server"] == "2026-06-26 23:00:00"


def test_extra_mql5_times_can_be_allowed(tmp_path: Path) -> None:
    extra = base_row(time_server="2026-06-26 23:00:00")
    manifest, output_dir = run_compare(
        tmp_path,
        python_rows=[base_row()],
        mql5_rows=[base_row(), extra],
        allow_extra_mql5_times=True,
    )

    assert manifest["acceptance_passed"] is True
    assert manifest["extra_mql5_time_count"] == 1
    assert manifest["extra_mql5_time_blocking_count"] == 0
    assert read_csv(output_dir / compare.MISMATCHES_NAME) == []
    assert read_csv(output_dir / compare.EXTRA_TIMES_NAME)[0]["allowed"] == "True"


def test_missing_mql5_time_fails_acceptance(tmp_path: Path) -> None:
    missing_python_row = base_row(time_server="2026-06-26 22:45:00")
    manifest, output_dir = run_compare(
        tmp_path,
        python_rows=[base_row(), missing_python_row],
        mql5_rows=[base_row()],
    )

    mismatches = read_csv(output_dir / compare.MISMATCHES_NAME)
    missing_times = read_csv(output_dir / compare.MISSING_TIMES_NAME)
    assert manifest["acceptance_passed"] is False
    assert manifest["missing_mql5_time_count"] == 1
    assert manifest["time_server_match_rate"] == 0.5
    assert mismatches[0]["mismatch_type"] == "missing_mql5_time"
    assert missing_times[0]["time_server"] == "2026-06-26 22:45:00"


def test_signal_bool_mismatch_same_time_server_fails_acceptance(tmp_path: Path) -> None:
    manifest, output_dir = run_compare(
        tmp_path,
        python_rows=[base_row(signal_bool="true")],
        mql5_rows=[base_row(signal_bool="false")],
    )

    mismatches = read_csv(output_dir / compare.MISMATCHES_NAME)
    assert manifest["acceptance_passed"] is False
    assert manifest["signal_bool_match_rate"] == 0.0
    assert mismatches[0]["field"] == "signal_bool"


def test_bucket_mismatch_same_time_server_fails_acceptance(tmp_path: Path) -> None:
    manifest, output_dir = run_compare(
        tmp_path,
        python_rows=[base_row(close_to_ma_fast_atr_20_bucket="high_tercile")],
        mql5_rows=[base_row(close_to_ma_fast_atr_20_bucket="mid_tercile")],
    )

    mismatches = read_csv(output_dir / compare.MISMATCHES_NAME)
    assert manifest["acceptance_passed"] is False
    assert manifest["bucket_match_rate"] == 0.5
    assert mismatches[0]["field"] == "close_to_ma_fast_atr_20_bucket"


def test_numeric_mismatch_outside_tolerance_fails_acceptance(tmp_path: Path) -> None:
    manifest, output_dir = run_compare(
        tmp_path,
        python_rows=[base_row(atr_20="0.0006")],
        mql5_rows=[base_row(atr_20="0.0008")],
        numeric_tolerance=1e-9,
    )

    mismatches = read_csv(output_dir / compare.MISMATCHES_NAME)
    assert manifest["acceptance_passed"] is False
    assert manifest["numeric_within_tolerance_rate"] < 1.0
    assert mismatches[0]["field"] == "atr_20"
    assert mismatches[0]["mismatch_type"] == "numeric"


def test_max_exit_time_mismatch_is_lifecycle_metadata(tmp_path: Path) -> None:
    manifest, output_dir = run_compare(
        tmp_path,
        python_rows=[base_row(max_exit_time_server="2026-06-27 01:00:00")],
        mql5_rows=[base_row(max_exit_time_server="")],
    )

    mismatches = read_csv(output_dir / compare.MISMATCHES_NAME)
    assert manifest["acceptance_passed"] is True
    assert manifest["lifecycle_metadata_acceptance_passed"] is False
    assert manifest["max_exit_time_server_match_rate"] == 0.0
    assert mismatches[0]["field"] == "max_exit_time_server"
    assert mismatches[0]["mismatch_type"] == "lifecycle_metadata"


def test_near_threshold_rows_are_reported(tmp_path: Path) -> None:
    manifest, output_dir = run_compare(
        tmp_path,
        python_rows=[base_row(close_to_ma_fast_atr_20="0.59544")],
        mql5_rows=[base_row(close_to_ma_fast_atr_20="0.59544")],
        near_threshold_epsilon=0.001,
    )

    near_misses = read_csv(output_dir / compare.NEAR_MISSES_NAME)
    assert manifest["acceptance_passed"] is True
    assert manifest["threshold_near_miss_count"] == 1
    assert near_misses[0]["field"] == "close_to_ma_fast_atr_20"
    assert near_misses[0]["cutoff_name"] == "close_to_ma_fast_atr_20_mid_high"


def test_missing_required_columns_block(tmp_path: Path) -> None:
    python_csv = tmp_path / "python.csv"
    mql5_csv = tmp_path / "mql5.csv"
    write_parity_csv(python_csv, [base_row()])
    missing_fields = [field for field in compare.REQUIRED_COLUMNS if field != "max_exit_time_server"]
    write_parity_csv(mql5_csv, [base_row()], fieldnames=missing_fields)

    with pytest.raises(ValueError, match="missing required columns"):
        compare.compare_parity_csvs(
            python_csv=python_csv,
            mql5_csv=mql5_csv,
            output_dir=tmp_path / "comparison",
        )


def test_duplicate_time_server_in_python_blocks(tmp_path: Path) -> None:
    python_csv = tmp_path / "python.csv"
    mql5_csv = tmp_path / "mql5.csv"
    write_parity_csv(python_csv, [base_row(), base_row()])
    write_parity_csv(mql5_csv, [base_row()])

    with pytest.raises(ValueError, match="python_csv contains duplicate time_server"):
        compare.compare_parity_csvs(
            python_csv=python_csv,
            mql5_csv=mql5_csv,
            output_dir=tmp_path / "comparison",
        )


def test_duplicate_time_server_in_mql5_blocks(tmp_path: Path) -> None:
    python_csv = tmp_path / "python.csv"
    mql5_csv = tmp_path / "mql5.csv"
    write_parity_csv(python_csv, [base_row()])
    write_parity_csv(mql5_csv, [base_row(), base_row()])

    with pytest.raises(ValueError, match="mql5_csv contains duplicate time_server"):
        compare.compare_parity_csvs(
            python_csv=python_csv,
            mql5_csv=mql5_csv,
            output_dir=tmp_path / "comparison",
        )


def test_report_written_on_failure(tmp_path: Path) -> None:
    manifest, output_dir = run_compare(
        tmp_path,
        python_rows=[base_row(signal_bool="true")],
        mql5_rows=[base_row(signal_bool="false")],
    )

    report = output_dir / compare.REPORT_NAME
    assert manifest["acceptance_passed"] is False
    assert report.exists()
    assert "acceptance: `FAIL`" in report.read_text(encoding="utf-8")


def test_static_safety_no_broker_trade_calls() -> None:
    source = Path("scripts/compare_fixed_candidate_mt5_ea_parity.py").read_text(encoding="utf-8")
    assert "MetaTrader5" not in source
    assert ".order_check(" not in source
    assert ".order_send(" not in source
