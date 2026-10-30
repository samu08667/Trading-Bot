import csv
import random
import sqlite3
from pathlib import Path

import pytest

from scripts.run_candidate_baseline_diagnostics import main as diagnostics_main
from scripts.run_candidate_baseline_diagnostics import random_sample_rows


CANDIDATE_FIELDS = [
    "combination_key",
    "symbol",
    "direction",
    "cost_mode",
    "return_mode",
    "final_classification",
    "pair_specific_classification",
]


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def candidate_row(combination_key: str, **overrides: object) -> dict[str, object]:
    row = {
        "combination_key": combination_key,
        "symbol": "",
        "direction": "long",
        "cost_mode": "none",
        "return_mode": "gross",
        "final_classification": "select",
        "pair_specific_classification": "",
    }
    row.update(overrides)
    return row


def create_db(db_path: Path, *, mostly_single_filter: bool = False) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE ml_dataset (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                future_return_10 REAL,
                day_of_week INTEGER,
                hour INTEGER,
                volume_spike_20 INTEGER,
                volume_dry_up_20 INTEGER,
                ma_diff REAL,
                open REAL,
                high REAL,
                low REAL,
                close REAL
            )
            """
        )
        rows = []
        dates = [
            "2024-01-01 00:00:00",
            "2024-02-05 00:00:00",
            "2024-03-04 00:00:00",
            "2024-04-01 00:00:00",
        ]
        candidate_return = 0.02 if mostly_single_filter else 0.03
        monday_extra_return = 0.04 if mostly_single_filter else -0.01
        for index, timestamp in enumerate(dates):
            rows.append(("EURUSD", "M15", timestamp, candidate_return, 0, index, 1, 0, 1.0, 1.0, 1.1, 0.9, 1.0))
            rows.append(("EURUSD", "M15", timestamp.replace("00:00:00", "10:00:00"), monday_extra_return, 0, 10, 0, 1, -1.0, 1.0, 1.1, 0.9, 1.0))
            rows.append(("EURUSD", "M15", timestamp.replace("00:00:00", "00:15:00"), -0.01, 1, index, 0, 1, -1.0, 1.0, 1.1, 0.9, 1.0))
            rows.append(("EURUSD", "M15", timestamp.replace("00:00:00", "14:00:00"), -0.01, 2, 14, 0, 1, -1.0, 1.0, 1.1, 0.9, 1.0))
            rows.append(("GBPUSD", "M15", timestamp, 0.01, 0, index, 1, 0, 1.0, 1.0, 1.1, 0.9, 1.0))
            rows.append(("GBPUSD", "M15", timestamp.replace("00:00:00", "14:00:00"), -0.01, 2, 14, 0, 1, -1.0, 1.0, 1.1, 0.9, 1.0))
        connection.executemany(
            """
            INSERT INTO ml_dataset (
                symbol, timeframe, time_server, future_return_10, day_of_week, hour,
                volume_spike_20, volume_dry_up_20, ma_diff, open, high, low, close
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def validation_base(tmp_path: Path, direction: str = "long") -> Path:
    return tmp_path / "validation" / "by_year" / "run1" / direction


def run_diagnostics(
    tmp_path: Path,
    *,
    direction: str = "long",
    symbols: list[str] | None = None,
    include_pair_specific: bool = False,
    min_trades: int = 2,
    overwrite: bool = False,
) -> int:
    args = [
        "--run-id",
        "run1",
        "--direction",
        direction,
        "--symbols",
        *(symbols or ["EURUSD", "GBPUSD"]),
        "--db-path",
        str(tmp_path / "research.db"),
        "--validation-dir",
        str(tmp_path / "validation" / "by_year"),
        "--random-baseline-dir",
        str(tmp_path / "random_baseline"),
        "--output-dir",
        str(tmp_path / "baseline_diagnostics"),
        "--cost-mode",
        "none",
        "--return-mode",
        "gross",
        "--random-runs",
        "30",
        "--seed",
        "7",
        "--min-trades",
        str(min_trades),
    ]
    if include_pair_specific:
        args.append("--include-pair-specific")
    if overwrite:
        args.append("--overwrite")
    return diagnostics_main(args)


def output_base(tmp_path: Path, direction: str = "long") -> Path:
    return tmp_path / "baseline_diagnostics" / "run1" / direction


def test_candidate_a_and_b_compared_with_single_filters(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(
        validation_base(tmp_path) / "final_research_candidates.csv",
        [candidate_row("day_of_week:Monday AND hour_session:Asia")],
        CANDIDATE_FIELDS,
    )
    write_csv(validation_base(tmp_path) / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path)
    detail = read_csv(output_base(tmp_path) / "baseline_diagnostics_detail.csv")
    single_keys = {row["baseline_key"] for row in detail if row["baseline_type"] == "single_filter"}

    assert "day_of_week:Monday" in single_keys
    assert "hour_session:Asia" in single_keys


def test_candidate_a_b_c_generates_leave_one_out_baselines(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(
        validation_base(tmp_path) / "final_research_candidates.csv",
        [candidate_row("day_of_week:Monday AND hour_session:Asia AND volume_spike_20:1")],
        CANDIDATE_FIELDS,
    )
    write_csv(validation_base(tmp_path) / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path)
    detail = read_csv(output_base(tmp_path) / "baseline_diagnostics_detail.csv")
    leave_one_out = [row for row in detail if row["baseline_type"] == "leave_one_out"]

    assert len(leave_one_out) == 3
    assert any("day_of_week:Monday AND hour_session:Asia" == row["baseline_key"] for row in leave_one_out)


def test_random_sample_maintains_same_trade_count() -> None:
    rows = [{"id": index} for index in range(10)]
    sample = random_sample_rows(rows, 4, random.Random(11))

    assert len(sample) == 4
    assert len({row["id"] for row in sample}) == 4


def test_conditional_random_samples_inside_single_filter(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(
        validation_base(tmp_path) / "final_research_candidates.csv",
        [candidate_row("day_of_week:Monday AND hour_session:Asia")],
        CANDIDATE_FIELDS,
    )
    write_csv(validation_base(tmp_path) / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path)
    detail = read_csv(output_base(tmp_path) / "baseline_diagnostics_detail.csv")
    conditional = [row for row in detail if row["baseline_type"] == "conditional_random_median"]

    assert {row["baseline_key"] for row in conditional} == {"day_of_week:Monday", "hour_session:Asia"}
    assert all(row["candidate_trades_count"] == row["baseline_trades_count"] for row in conditional)


def test_pair_specific_uses_only_candidate_symbol(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(validation_base(tmp_path) / "final_research_candidates.csv", [], CANDIDATE_FIELDS)
    write_csv(
        validation_base(tmp_path) / "pair_specific_candidates.csv",
        [candidate_row("day_of_week:Monday AND hour_session:Asia", symbol="EURUSD", pair_specific_classification="select_pair_specific")],
        CANDIDATE_FIELDS,
    )

    run_diagnostics(tmp_path, include_pair_specific=True)
    detail = read_csv(output_base(tmp_path) / "baseline_diagnostics_detail.csv")
    all_row = next(row for row in detail if row["baseline_type"] == "all_candles")

    assert all_row["candidate_scope"] == "pair_specific"
    assert all_row["baseline_trades_count"] == "16"


def test_cross_pair_uses_all_requested_symbols(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(
        validation_base(tmp_path) / "final_research_candidates.csv",
        [candidate_row("day_of_week:Monday AND hour_session:Asia")],
        CANDIDATE_FIELDS,
    )
    write_csv(validation_base(tmp_path) / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path)
    detail = read_csv(output_base(tmp_path) / "baseline_diagnostics_detail.csv")
    all_row = next(row for row in detail if row["baseline_type"] == "all_candles")

    assert all_row["candidate_scope"] == "cross_pair"
    assert all_row["baseline_trades_count"] == "24"


def test_long_and_short_outputs_are_separate(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(validation_base(tmp_path, "long") / "final_research_candidates.csv", [candidate_row("volume_spike_20:1")], CANDIDATE_FIELDS)
    write_csv(validation_base(tmp_path, "long") / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)
    write_csv(
        validation_base(tmp_path, "short") / "final_research_candidates.csv",
        [candidate_row("volume_dry_up_20:1", direction="short")],
        CANDIDATE_FIELDS,
    )
    write_csv(validation_base(tmp_path, "short") / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path, direction="short")
    summary = read_csv(output_base(tmp_path, "short") / "baseline_diagnostics_summary.csv")

    assert summary
    assert all(row["direction"] == "short" for row in summary)
    assert not output_base(tmp_path, "long").exists()


def test_net_with_cost_none_fails(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        diagnostics_main(
            [
                "--run-id",
                "run1",
                "--symbols",
                "EURUSD",
                "--db-path",
                str(tmp_path / "research.db"),
                "--cost-mode",
                "none",
                "--return-mode",
                "net",
            ]
        )


def test_raw_price_and_numeric_tercile_are_skipped(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(
        validation_base(tmp_path) / "final_research_candidates.csv",
        [
            candidate_row("close:1"),
            candidate_row("numeric_tercile:ma_diff:high"),
        ],
        CANDIDATE_FIELDS,
    )
    write_csv(validation_base(tmp_path) / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path)
    skipped = read_csv(output_base(tmp_path) / "skipped_baseline_diagnostics_candidates.csv")

    assert {row["skip_reason"] for row in skipped} == {
        "raw_price_level_excluded",
        "numeric_tercile_skipped_to_avoid_temporal_leakage",
    }


def test_empty_candidate_file_does_not_crash(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(validation_base(tmp_path) / "final_research_candidates.csv", [], CANDIDATE_FIELDS)
    write_csv(validation_base(tmp_path) / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path)
    summary = read_csv(output_base(tmp_path) / "baseline_diagnostics_summary.csv")
    report = (output_base(tmp_path) / "baseline_diagnostics_report.md").read_text(encoding="utf-8")

    assert summary == []
    assert "Optional random baseline reference not found" in report


def test_output_already_existing_requires_overwrite(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(validation_base(tmp_path) / "final_research_candidates.csv", [candidate_row("volume_spike_20:1")], CANDIDATE_FIELDS)
    write_csv(validation_base(tmp_path) / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path)
    with pytest.raises(FileExistsError, match="--overwrite"):
        run_diagnostics(tmp_path)
    run_diagnostics(tmp_path, overwrite=True)


def test_candidate_beating_all_but_not_single_filter_is_mostly_single_effect(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db", mostly_single_filter=True)
    write_csv(
        validation_base(tmp_path) / "final_research_candidates.csv",
        [candidate_row("day_of_week:Monday AND hour_session:Asia")],
        CANDIDATE_FIELDS,
    )
    write_csv(validation_base(tmp_path) / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path)
    summary = read_csv(output_base(tmp_path) / "baseline_diagnostics_summary.csv")

    assert summary[0]["all_candles_result"] == "beat"
    assert summary[0]["final_baseline_diagnostic_classification"] == "mostly_single_filter_effect"


def test_candidate_beating_context_adds_incremental_value(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(
        validation_base(tmp_path) / "final_research_candidates.csv",
        [candidate_row("day_of_week:Monday AND hour_session:Asia")],
        CANDIDATE_FIELDS,
    )
    write_csv(validation_base(tmp_path) / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path)
    summary = read_csv(output_base(tmp_path) / "baseline_diagnostics_summary.csv")

    assert summary[0]["final_baseline_diagnostic_classification"] == "adds_incremental_value"


def test_candidate_with_few_trades_is_low_sample(tmp_path: Path) -> None:
    create_db(tmp_path / "research.db")
    write_csv(validation_base(tmp_path) / "final_research_candidates.csv", [candidate_row("volume_spike_20:1")], CANDIDATE_FIELDS)
    write_csv(validation_base(tmp_path) / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)

    run_diagnostics(tmp_path, min_trades=20)
    summary = read_csv(output_base(tmp_path) / "baseline_diagnostics_summary.csv")

    assert summary[0]["final_baseline_diagnostic_classification"] == "low_sample"
