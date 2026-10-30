"""Smoke test for year-by-year hypothesis validation.

This test creates a temporary SQLite database and temporary reports. It does
not require MetaTrader5, does not use real data, and does not write tracked
runtime artifacts.
"""

from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


BASE_DIR = Path(__file__).resolve().parents[1]


def create_smoke_database(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE ml_dataset (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                future_return_10 REAL,
                day_of_week INTEGER,
                ma_diff REAL,
                hour INTEGER,
                always_on INTEGER,
                xau_only INTEGER,
                blackout_window_30m INTEGER,
                volatility_20 REAL,
                open REAL,
                close REAL
            )
            """
        )
        rows = [
            ("EURUSD", "M15", "2022-01-03T00:00:00", 0.005, 0, 0.10, 1, 1, 1, 1, 0.10, 1.10, 1.11),
            ("EURUSD", "M15", "2022-06-15T12:00:00", -0.030, 2, -0.10, 12, 1, 1, 1, 0.20, 1.12, 1.10),
            ("EURUSD", "M15", "2022-12-28T14:00:00", 0.020, 2, -0.10, 14, 1, 0, 0, 0.20, 1.12, 1.10),
            ("EURUSD", "M15", "2023-01-02T02:00:00", 0.004, 0, 0.20, 2, 1, 1, 1, 0.12, 1.09, 1.11),
            ("EURUSD", "M15", "2023-06-15T12:00:00", -0.028, 3, -0.20, 12, 1, 1, 1, 0.20, 1.12, 1.10),
            ("EURUSD", "M15", "2023-12-27T15:00:00", 0.018, 2, -0.20, 15, 1, 0, 0, 0.22, 1.11, 1.10),
            ("EURUSD", "M15", "2026-01-05T03:00:00", 0.010, 0, 0.30, 3, 1, 1, 1, 0.15, 1.13, 1.14),
            ("XAUUSD", "M15", "2022-01-03T01:00:00", 0.030, 0, 0.20, 1, 1, 1, 1, 0.10, 1800.0, 1805.0),
            ("XAUUSD", "M15", "2022-06-15T12:00:00", -0.005, 2, -0.10, 12, 1, 1, 1, 0.20, 1805.0, 1804.0),
            ("XAUUSD", "M15", "2022-12-28T14:00:00", -0.020, 2, -0.10, 14, 1, 0, 0, 0.20, 1804.0, 1800.0),
            ("XAUUSD", "M15", "2023-01-02T02:00:00", 0.025, 0, 0.20, 2, 1, 1, 1, 0.12, 1810.0, 1816.0),
            ("XAUUSD", "M15", "2023-06-15T12:00:00", -0.004, 3, -0.10, 12, 1, 1, 1, 0.20, 1816.0, 1814.0),
            ("XAUUSD", "M15", "2023-12-27T15:00:00", -0.018, 2, -0.20, 15, 1, 0, 0, 0.22, 1814.0, 1810.0),
        ]
        connection.executemany(
            """
            INSERT INTO ml_dataset (
                symbol, timeframe, time_server, future_return_10, day_of_week,
                ma_diff, hour, always_on, xau_only, blackout_window_30m, volatility_20, open, close
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    finally:
        connection.close()


def create_hypotheses_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"combination_key": "always_on:1", "classification": "watchlist"},
        {"combination_key": "xau_only:1", "classification": "watchlist"},
        {"combination_key": "day_of_week:Monday AND ma_diff:ma_diff_gt_0", "classification": "interesting"},
        {"combination_key": "hour_session:Asia", "classification": "watchlist"},
        {"combination_key": "blackout_window_30m:1", "classification": "watchlist"},
        {"combination_key": "numeric_tercile:volatility_20:low_tercile", "classification": "interesting"},
        {"combination_key": "binary_feature:close:1", "classification": "interesting"},
        {"combination_key": "unsupported:thing:value", "classification": "interesting"},
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["combination_key", "classification"])
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def run_smoke_test() -> None:
    with TemporaryDirectory() as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        db_path = temp_dir / "smoke.db"
        hypotheses_file = temp_dir / "evaluations" / "smoke_run" / "selected_combined_hypotheses.csv"
        output_base = temp_dir / "validation" / "by_year"
        create_smoke_database(db_path)
        create_hypotheses_file(hypotheses_file)

        command = [
            sys.executable,
            str(BASE_DIR / "scripts" / "validate_hypotheses_by_year.py"),
            "--hypotheses-file",
            str(hypotheses_file),
            "--run-id",
            "smoke_run",
            "--symbols",
            "EURUSD",
            "XAUUSD",
            "--timeframe",
            "M15",
            "--target-horizon",
            "10",
            "--direction",
            "long",
            "--years",
            "2022",
            "2023",
            "2026",
            "--min-trades-per-year",
            "1",
            "--min-positive-year-ratio",
            "0.5",
            "--min-positive-symbol-ratio",
            "0.75",
            "--db-path",
            str(db_path),
            "--output-dir",
            str(output_base),
        ]
        completed = subprocess.run(command, cwd=BASE_DIR, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stdout + completed.stderr)

        run_output = output_base / "smoke_run" / "long"
        detail_path = run_output / "by_year_validation_detail.csv"
        summary_path = run_output / "by_year_validation_summary.csv"
        candidates_path = run_output / "final_research_candidates.csv"
        report_path = run_output / "final_research_candidates_report.md"
        pair_specific_path = run_output / "pair_specific_candidates.csv"
        pair_specific_report_path = run_output / "pair_specific_candidates_report.md"
        skipped_path = run_output / "skipped_hypotheses.csv"
        for path in (
            detail_path,
            summary_path,
            candidates_path,
            report_path,
            pair_specific_path,
            pair_specific_report_path,
            skipped_path,
        ):
            if not path.exists():
                raise AssertionError(f"Missing expected output: {path}")

        detail_rows = read_csv(detail_path)
        if not any(row["combination_key"] == "hour_session:Asia" for row in detail_rows):
            raise AssertionError("hour_session:Asia was not validated.")
        if not any(row["year"] == "2026" and row["partial_year"] == "true" for row in detail_rows):
            raise AssertionError("2026 was not marked partial_year=true.")

        summary_rows = read_csv(summary_path)
        always_on_summary = next(
            (row for row in summary_rows if row["combination_key"] == "always_on:1"),
            None,
        )
        if always_on_summary is None:
            raise AssertionError("always_on:1 summary row was not written.")
        if always_on_summary["median_profit_factor_improvement_pct"] == "":
            raise AssertionError("median_profit_factor_improvement_pct was not calculated.")
        valid_pf_improvement_rows = [
            row
            for row in detail_rows
            if row["combination_key"] == "always_on:1"
            and row["partial_year"] == "false"
            and row["profit_factor_improvement_pct"] != ""
        ]
        if len(valid_pf_improvement_rows) < 2:
            raise AssertionError("Smoke test did not cover median calculation with at least 2 valid values.")

        xau_only_summary = next(
            (row for row in summary_rows if row["combination_key"] == "xau_only:1"),
            None,
        )
        if xau_only_summary is None:
            raise AssertionError("xau_only:1 summary row was not written.")
        if xau_only_summary["final_classification"] == "select":
            raise AssertionError("xau_only:1 should not be selected as a cross-pair candidate.")

        pair_rows = read_csv(pair_specific_path)
        xau_pair_row = next(
            (
                row for row in pair_rows
                if row["combination_key"] == "xau_only:1"
                and row["symbol"] == "XAUUSD"
                and row["direction"] == "long"
            ),
            None,
        )
        if xau_pair_row is None:
            raise AssertionError("XAUUSD-only combination did not appear in pair_specific_candidates.csv.")
        if xau_pair_row["pair_specific_classification"] != "select_pair_specific":
            raise AssertionError("XAUUSD-only combination was not selected as pair-specific.")

        skipped_rows = read_csv(skipped_path)
        reasons = {row["skip_reason"] for row in skipped_rows}
        expected_reasons = {
            "numeric_tercile_skipped_to_avoid_temporal_leakage",
            "raw_price_level_excluded",
        }
        missing = expected_reasons - reasons
        if missing:
            raise AssertionError(f"Missing skipped reasons: {sorted(missing)}")
        if not any(reason.startswith("unsupported_condition:") for reason in reasons):
            raise AssertionError("Unsupported condition was not skipped.")

        short_command = command.copy()
        short_command[short_command.index("long")] = "short"
        completed = subprocess.run(short_command, cwd=BASE_DIR, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stdout + completed.stderr)
        short_output = output_base / "smoke_run" / "short"
        short_pair_path = short_output / "pair_specific_candidates.csv"
        if not short_pair_path.exists():
            raise AssertionError("Short pair-specific output was not created separately.")
        short_rows = read_csv(short_pair_path)
        if not short_rows or any(row["direction"] != "short" for row in short_rows):
            raise AssertionError("Short pair-specific rows were not kept direction-specific.")

    print("Smoke test passed: validate_hypotheses_by_year.py")


def main() -> int:
    try:
        run_smoke_test()
    except (AssertionError, RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"Smoke test failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
