"""Smoke test for research-only walk-forward validation."""

from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


BASE_DIR = Path(__file__).resolve().parents[1]


def create_database(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE ml_dataset (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                future_return_10 REAL,
                target_up_10 INTEGER,
                target_down_10 INTEGER,
                day_of_week INTEGER,
                ma_diff REAL,
                hour INTEGER,
                long_flag INTEGER,
                short_flag INTEGER,
                open REAL,
                close REAL
            )
            """
        )
        rows = []
        for symbol in ("EURUSD", "XAUUSD"):
            price = 1.10 if symbol == "EURUSD" else 1800.0
            for year in (2020, 2021, 2022, 2023):
                rows.extend(
                    [
                        (symbol, "M15", f"{year}-01-03T01:00:00", 0.030, 1, 0, 0, 0.20, 1, 1, 0, price, price + 1),
                        (symbol, "M15", f"{year}-06-15T12:00:00", -0.005, 0, 1, 2, -0.10, 12, 1, 0, price, price - 1),
                        (symbol, "M15", f"{year}-03-10T09:00:00", -0.030, 0, 1, 3, -0.20, 9, 0, 1, price, price - 2),
                        (symbol, "M15", f"{year}-09-10T14:00:00", 0.005, 1, 0, 4, 0.10, 14, 0, 1, price, price + 2),
                        (symbol, "M15", f"{year}-12-28T15:00:00", -0.020, 0, 1, 2, -0.20, 15, 0, 0, price, price - 1),
                    ]
                )
        connection.executemany(
            """
            INSERT INTO ml_dataset (
                symbol, timeframe, time_server, future_return_10, target_up_10,
                target_down_10, day_of_week, ma_diff, hour, long_flag,
                short_flag, open, close
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    finally:
        connection.close()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def run_direction(db_path: Path, output_dir: Path, direction: str) -> None:
    command = [
        sys.executable,
        str(BASE_DIR / "scripts" / "run_walk_forward_research.py"),
        "--symbols",
        "EURUSD",
        "XAUUSD",
        "--timeframe",
        "M15",
        "--target-horizon",
        "10",
        "--direction",
        direction,
        "--train-start-year",
        "2020",
        "--first-test-year",
        "2022",
        "--last-test-year",
        "2023",
        "--min-trades-per-year",
        "1",
        "--db-path",
        str(db_path),
        "--output-dir",
        str(output_dir),
        "--run-id",
        "smoke_walk",
        "--max-combination-size",
        "5",
        "--max-seed-conditions",
        "8",
        "--max-candidates-per-level",
        "20",
        "--max-cross-pair-candidates-per-fold",
        "20",
        "--max-pair-specific-candidates-per-symbol",
        "20",
        "--overwrite",
    ]
    completed = subprocess.run(command, cwd=BASE_DIR, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout + completed.stderr)

    run_output = output_dir / "smoke_walk" / direction
    expected = [
        run_output / "walk_forward_detail.csv",
        run_output / "walk_forward_summary.csv",
        run_output / "walk_forward_candidates.csv",
        run_output / "walk_forward_report.md",
        run_output / "pair_specific_walk_forward_candidates.csv",
        run_output / "pair_specific_walk_forward_report.md",
    ]
    for path in expected:
        if not path.exists():
            raise AssertionError(f"Missing expected output: {path}")

    detail_rows = read_csv(run_output / "walk_forward_detail.csv")
    if not detail_rows:
        raise AssertionError("Walk-forward detail rows were not written.")
    required_columns = {"combination_size", "train_selection_level", "train_selection_score"}
    missing_columns = required_columns - set(detail_rows[0])
    if missing_columns:
        raise AssertionError(f"Missing walk-forward detail columns: {sorted(missing_columns)}")
    if any(int(row["combination_size"]) > 5 for row in detail_rows):
        raise AssertionError("Walk-forward generated a combination above --max-combination-size.")
    if any(row["direction"] != direction for row in detail_rows):
        raise AssertionError("Walk-forward detail rows mixed directions.")

    summary_rows = read_csv(run_output / "walk_forward_summary.csv")
    if not summary_rows:
        raise AssertionError("Walk-forward summary rows were not written.")
    missing_columns = required_columns - set(summary_rows[0])
    if missing_columns:
        raise AssertionError(f"Missing walk-forward summary columns: {sorted(missing_columns)}")

    pair_rows = read_csv(run_output / "pair_specific_walk_forward_candidates.csv")
    if not pair_rows:
        raise AssertionError("Pair-specific walk-forward rows were not written.")
    missing_columns = required_columns - set(pair_rows[0])
    if missing_columns:
        raise AssertionError(f"Missing pair-specific walk-forward columns: {sorted(missing_columns)}")
    if any(row["direction"] != direction for row in pair_rows):
        raise AssertionError("Pair-specific walk-forward rows mixed directions.")


def run_smoke_test() -> None:
    with TemporaryDirectory() as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        db_path = temp_dir / "walk_forward_smoke.db"
        output_dir = temp_dir / "walk_forward"
        create_database(db_path)
        run_direction(db_path, output_dir, "long")
        run_direction(db_path, output_dir, "short")

    print("Smoke test passed: run_walk_forward_research.py")


def main() -> int:
    try:
        run_smoke_test()
    except (AssertionError, RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"Smoke test failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
