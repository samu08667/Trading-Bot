import argparse
import csv
import math
import random
import sqlite3
from pathlib import Path

import pytest

from scripts.research_costs import validate_cost_args
from scripts.run_random_baseline_tests import (
    candidate_file_path,
    empirical_p_value_lower_abs_is_better,
    load_candidate_file,
    percentile_higher_is_better,
    percentile_lower_abs_is_better,
    precheck_combination_skip_reason,
    random_sample_rows,
    run_random_baseline_tests,
)


def write_candidate_file(path: Path, rows: list[dict[str, object]], pair_specific: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "combination_key",
        "direction",
        "cost_mode",
        "return_mode",
        "final_classification",
        "symbol",
        "pair_specific_classification",
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            if pair_specific and "pair_specific_classification" not in row:
                row = {**row, "pair_specific_classification": "select_pair_specific"}
            writer.writerow(row)


def create_ml_dataset(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
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
                volume_spike_20 INTEGER,
                volume_dry_up_20 INTEGER,
                blackout_window_30m INTEGER,
                has_high_impact_news_next_30m INTEGER,
                open REAL,
                close REAL
            )
            """
        )
        rows = [
            ("EURUSD", "M15", "2024-01-01 00:00:00", 0.010, 0, 1.0, 0, 1, 0, 0, 0, 1.0, 1.10),
            ("EURUSD", "M15", "2024-01-01 00:15:00", -0.002, 0, 1.0, 1, 1, 0, 0, 0, 1.0, 1.10),
            ("EURUSD", "M15", "2024-01-01 00:30:00", 0.001, 0, -1.0, 2, 0, 1, 1, 0, 1.0, 1.10),
            ("EURUSD", "M15", "2024-01-01 00:45:00", -0.003, 0, -1.0, 3, 0, 1, 1, 1, 1.0, 1.10),
        ]
        connection.executemany(
            """
            INSERT INTO ml_dataset (
                symbol, timeframe, time_server, future_return_10, day_of_week,
                ma_diff, hour, volume_spike_20, volume_dry_up_20,
                blackout_window_30m, has_high_impact_news_next_30m, open, close
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def test_random_sample_uses_same_number_of_trades_without_replacement() -> None:
    rows = [{"id": index} for index in range(10)]
    sample = random_sample_rows(rows, 4, random.Random(7))

    assert len(sample) == 4
    assert len({row["id"] for row in sample}) == 4
    assert all(row in rows for row in sample)


def test_percentile_higher_is_better() -> None:
    assert math.isclose(percentile_higher_is_better(2, [1, 2, 3]), 2 / 3 * 100)


def test_drawdown_percentile_uses_absolute_drawdown() -> None:
    random_drawdowns = [-0.20, -0.05, -0.30]

    assert math.isclose(percentile_lower_abs_is_better(-0.10, random_drawdowns), 2 / 3 * 100)
    assert math.isclose(empirical_p_value_lower_abs_is_better(-0.10, random_drawdowns), 0.5)


def test_empty_candidate_file_returns_no_candidates(tmp_path: Path) -> None:
    candidate_path = tmp_path / "final_research_candidates.csv"
    write_candidate_file(candidate_path, [])

    rows = load_candidate_file(candidate_path, "cross_pair", "long", "none", "gross")

    assert rows == []


def test_skip_numeric_tercile_and_raw_price_levels() -> None:
    assert precheck_combination_skip_reason("numeric_tercile:volatility_20:low_tercile")
    assert precheck_combination_skip_reason("binary_feature:close:1")


def test_random_baseline_keeps_long_and_short_outputs_separate(tmp_path: Path) -> None:
    db_path = tmp_path / "research.db"
    validation_dir = tmp_path / "validation" / "by_year"
    output_dir = tmp_path / "random_baseline"
    create_ml_dataset(db_path)
    write_candidate_file(
        candidate_file_path(validation_dir, "run1", "long", "cross_pair"),
        [
            {
                "combination_key": "volume_spike_20:1",
                "direction": "long",
                "cost_mode": "none",
                "return_mode": "gross",
                "final_classification": "select",
            }
        ],
    )
    write_candidate_file(
        candidate_file_path(validation_dir, "run1", "short", "cross_pair"),
        [
            {
                "combination_key": "volume_dry_up_20:1",
                "direction": "short",
                "cost_mode": "none",
                "return_mode": "gross",
                "final_classification": "select",
            }
        ],
    )

    run_random_baseline_tests(
        argparse.Namespace(
            run_id="run1",
            direction="short",
            symbols=["EURUSD"],
            timeframe="M15",
            target_horizon=10,
            db_path=db_path,
            validation_dir=validation_dir,
            output_dir=output_dir,
            cost_mode="none",
            return_mode="gross",
            cost_config=None,
            strict_cost_config=False,
            random_runs=5,
            seed=3,
            max_candidates=50,
            include_cross_pair=True,
            include_pair_specific=False,
            min_trades=1,
            overwrite=False,
        )
    )

    assert not (output_dir / "run1" / "long").exists()
    detail_path = output_dir / "run1" / "short" / "random_baseline_detail.csv"
    with detail_path.open("r", newline="", encoding="utf-8") as csv_file:
        detail_rows = list(csv.DictReader(csv_file))

    assert detail_rows
    assert all(row["direction"] == "short" for row in detail_rows)
    assert all(row["return_mode"] == "gross" for row in detail_rows)


def test_return_mode_net_with_cost_mode_none_fails() -> None:
    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        validate_cost_args("none", "net")
