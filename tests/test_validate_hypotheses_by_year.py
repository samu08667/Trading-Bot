import argparse
import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

from scripts.validate_hypotheses_by_year import infer_run_id


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_infer_run_id_from_direction_specific_selected_combined_file() -> None:
    args = argparse.Namespace(run_id=None)

    long_path = Path(
        "reports/backtests/combined/evaluations/20260511_200059/long/selected_combined_hypotheses.csv"
    )
    short_path = Path(
        "reports/backtests/combined/evaluations/20260511_200059/short/selected_combined_hypotheses.csv"
    )

    assert infer_run_id(args, long_path) == "20260511_200059"
    assert infer_run_id(args, short_path) == "20260511_200059"


def test_infer_run_id_from_legacy_selected_combined_file() -> None:
    args = argparse.Namespace(run_id=None)
    path = Path("reports/backtests/combined/evaluations/20260511_200059/selected_combined_hypotheses.csv")

    assert infer_run_id(args, path) == "20260511_200059"


def test_infer_run_id_prefers_explicit_run_id() -> None:
    args = argparse.Namespace(run_id="manual_run")
    path = Path(
        "reports/backtests/combined/evaluations/20260511_200059/long/selected_combined_hypotheses.csv"
    )

    assert infer_run_id(args, path) == "manual_run"


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


def test_validate_hypotheses_by_year_smoke(tmp_path: Path) -> None:
    db_path = tmp_path / "smoke.db"
    hypotheses_file = tmp_path / "evaluations" / "smoke_run" / "selected_combined_hypotheses.csv"
    output_base = tmp_path / "validation" / "by_year"
    create_smoke_database(db_path)
    create_hypotheses_file(hypotheses_file)

    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "validate_hypotheses_by_year.py"),
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
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    run_output = output_base / "smoke_run" / "long"
    detail_path = run_output / "by_year_validation_detail.csv"
    summary_path = run_output / "by_year_validation_summary.csv"
    candidates_path = run_output / "final_research_candidates.csv"
    report_path = run_output / "final_research_candidates_report.md"
    pair_specific_path = run_output / "pair_specific_candidates.csv"
    pair_specific_report_path = run_output / "pair_specific_candidates_report.md"
    skipped_path = run_output / "skipped_hypotheses.csv"

    assert detail_path.exists()
    assert summary_path.exists()
    assert candidates_path.exists()
    assert report_path.exists()
    assert pair_specific_path.exists()
    assert pair_specific_report_path.exists()
    assert skipped_path.exists()

    with detail_path.open("r", newline="", encoding="utf-8") as csv_file:
        detail_rows = list(csv.DictReader(csv_file))
    assert any(row["combination_key"] == "hour_session:Asia" for row in detail_rows)
    assert any(row["year"] == "2026" and row["partial_year"] == "true" for row in detail_rows)
    assert any(row["direction"] == "long" for row in detail_rows)

    with summary_path.open("r", newline="", encoding="utf-8") as csv_file:
        summary_rows = list(csv.DictReader(csv_file))
    always_on_summary = next(row for row in summary_rows if row["combination_key"] == "always_on:1")
    assert always_on_summary["median_profit_factor_improvement_pct"] != ""
    valid_pf_rows = [
        row
        for row in detail_rows
        if row["combination_key"] == "always_on:1"
        and row["partial_year"] == "false"
        and row["profit_factor_improvement_pct"] != ""
    ]
    assert len(valid_pf_rows) >= 2

    xau_only_summary = next(row for row in summary_rows if row["combination_key"] == "xau_only:1")
    assert xau_only_summary["final_classification"] != "select"

    with pair_specific_path.open("r", newline="", encoding="utf-8") as csv_file:
        pair_rows = list(csv.DictReader(csv_file))
    xau_pair_row = next(
        row
        for row in pair_rows
        if row["combination_key"] == "xau_only:1"
        and row["symbol"] == "XAUUSD"
        and row["direction"] == "long"
    )
    assert xau_pair_row["pair_specific_classification"] == "select_pair_specific"

    with skipped_path.open("r", newline="", encoding="utf-8") as csv_file:
        skipped_rows = list(csv.DictReader(csv_file))
    reasons = {row["skip_reason"] for row in skipped_rows}
    assert "numeric_tercile_skipped_to_avoid_temporal_leakage" in reasons
    assert "raw_price_level_excluded" in reasons
    assert any(reason.startswith("unsupported_condition:") for reason in reasons)

    short_command = command.copy()
    short_command[short_command.index("long")] = "short"
    short_completed = subprocess.run(short_command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)

    assert short_completed.returncode == 0, short_completed.stdout + short_completed.stderr
    short_pair_path = output_base / "smoke_run" / "short" / "pair_specific_candidates.csv"
    assert short_pair_path.exists()
    with short_pair_path.open("r", newline="", encoding="utf-8") as csv_file:
        short_pair_rows = list(csv.DictReader(csv_file))
    assert short_pair_rows
    assert all(row["direction"] == "short" for row in short_pair_rows)
