import argparse
import csv
from pathlib import Path

import pytest

from scripts.build_research_decision_report import (
    DECISION_CANDIDATE,
    DECISION_REJECT,
    DECISION_REVIEW,
    build_research_decision_report,
)


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


CANDIDATE_FIELDS = [
    "combination_key",
    "symbol",
    "direction",
    "cost_mode",
    "return_mode",
    "final_classification",
    "pair_specific_classification",
    "avg_trades_per_year",
    "min_trades_in_any_year",
    "positive_year_ratio",
    "positive_symbol_ratio",
    "avg_profit_factor_improvement_pct",
    "avg_max_drawdown_improvement_pct",
    "worst_year_profit_factor_improvement_pct",
    "worst_year_drawdown_improvement_pct",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "best_month_contribution_pct",
    "top_5_percent_trades_contribution_pct",
]

RANDOM_FIELDS = [
    "candidate_type",
    "combination_key",
    "symbol",
    "direction",
    "cost_mode",
    "return_mode",
    "random_baseline_classification",
    "trades_count",
    "cumulative_return_percentile",
    "profit_factor_percentile",
    "mean_return_percentile",
    "win_rate_percentile",
    "max_drawdown_percentile",
    "cumulative_return_empirical_p_value",
    "mean_return_empirical_p_value",
]


def good_cross_candidate(**overrides: object) -> dict[str, object]:
    row = {
        "combination_key": "volume_spike_20:1",
        "symbol": "",
        "direction": "long",
        "cost_mode": "estimated",
        "return_mode": "net",
        "final_classification": "select",
        "pair_specific_classification": "",
        "avg_trades_per_year": 200,
        "min_trades_in_any_year": 150,
        "positive_year_ratio": 0.80,
        "positive_symbol_ratio": 0.75,
        "avg_profit_factor_improvement_pct": 12,
        "avg_max_drawdown_improvement_pct": 8,
        "worst_year_profit_factor_improvement_pct": -5,
        "worst_year_drawdown_improvement_pct": -10,
        "monthly_positive_ratio": 0.60,
        "quarterly_positive_ratio": 0.70,
        "best_month_contribution_pct": 35,
        "top_5_percent_trades_contribution_pct": 45,
    }
    row.update(overrides)
    return row


def pair_candidate(**overrides: object) -> dict[str, object]:
    row = good_cross_candidate(
        combination_key="volume_dry_up_20:0",
        symbol="EURUSD",
        final_classification="",
        pair_specific_classification="select_pair_specific",
    )
    row.update(overrides)
    return row


def random_row(**overrides: object) -> dict[str, object]:
    row = {
        "candidate_type": "cross_pair",
        "combination_key": "volume_spike_20:1",
        "symbol": "",
        "direction": "long",
        "cost_mode": "estimated",
        "return_mode": "net",
        "random_baseline_classification": "robust_vs_random",
        "trades_count": 240,
        "cumulative_return_percentile": 95,
        "profit_factor_percentile": 94,
        "mean_return_percentile": 93,
        "win_rate_percentile": 91,
        "max_drawdown_percentile": 90,
        "cumulative_return_empirical_p_value": 0.03,
        "mean_return_empirical_p_value": 0.04,
    }
    row.update(overrides)
    return row


def base_args(tmp_path: Path, direction: str = "long") -> argparse.Namespace:
    return argparse.Namespace(
        run_id="run1",
        direction=direction,
        validation_dir=tmp_path / "validation" / "by_year",
        random_baseline_dir=tmp_path / "random_baseline",
        scorecard_dir=tmp_path / "scorecard",
        walk_forward_dir=tmp_path / "walk_forward",
        output_dir=tmp_path / "research_decision",
        cost_mode="estimated",
        return_mode="net",
        include_cross_pair=True,
        include_pair_specific=True,
        overwrite=False,
    )


def write_standard_inputs(
    tmp_path: Path,
    *,
    cross_rows: list[dict[str, object]] | None = None,
    pair_rows: list[dict[str, object]] | None = None,
    random_rows: list[dict[str, object]] | None = None,
    direction: str = "long",
) -> None:
    validation_base = tmp_path / "validation" / "by_year" / "run1" / direction
    random_base = tmp_path / "random_baseline" / "run1" / direction
    write_csv(validation_base / "final_research_candidates.csv", cross_rows or [], CANDIDATE_FIELDS)
    write_csv(validation_base / "pair_specific_candidates.csv", pair_rows or [], CANDIDATE_FIELDS)
    write_csv(validation_base / "skipped_hypotheses.csv", [], ["combination_key", "skip_reason", "source_file"])
    write_csv(random_base / "random_baseline_detail.csv", random_rows or [], RANDOM_FIELDS)
    write_csv(random_base / "random_baseline_summary.csv", [], ["candidate_type", "candidates_tested"])
    write_csv(
        random_base / "skipped_random_baseline_candidates.csv",
        [],
        ["candidate_type", "combination_key", "symbol", "skip_reason", "source_file"],
    )


def test_report_with_cross_pair_candidate(tmp_path: Path) -> None:
    write_standard_inputs(tmp_path, cross_rows=[good_cross_candidate()], random_rows=[random_row()])

    paths = build_research_decision_report(base_args(tmp_path))
    rows = read_csv(paths["summary"])

    assert rows[0]["candidate_scope"] == "cross_pair"
    assert rows[0]["decision"] == DECISION_CANDIDATE
    assert rows[0]["random_baseline_classification"] == "robust_vs_random"


def test_report_with_pair_specific_candidate(tmp_path: Path) -> None:
    write_standard_inputs(
        tmp_path,
        pair_rows=[pair_candidate()],
        random_rows=[
            random_row(
                candidate_type="pair_specific",
                combination_key="volume_dry_up_20:0",
                symbol="EURUSD",
                random_baseline_classification="interesting_vs_random",
            )
        ],
    )

    paths = build_research_decision_report(base_args(tmp_path))
    rows = read_csv(paths["summary"])

    assert rows[0]["candidate_scope"] == "pair_specific"
    assert rows[0]["decision"] == DECISION_REVIEW
    assert rows[0]["primary_reason"] == "pair_specific_not_generalizable"


def test_random_baseline_missing_warns_without_crashing(tmp_path: Path) -> None:
    validation_base = tmp_path / "validation" / "by_year" / "run1" / "long"
    write_csv(validation_base / "final_research_candidates.csv", [good_cross_candidate()], CANDIDATE_FIELDS)
    write_csv(validation_base / "pair_specific_candidates.csv", [], CANDIDATE_FIELDS)
    write_csv(validation_base / "skipped_hypotheses.csv", [], ["combination_key", "skip_reason", "source_file"])

    paths = build_research_decision_report(base_args(tmp_path))
    warnings = read_csv(paths["warnings"])
    rows = read_csv(paths["summary"])

    assert any(row["warning_type"] == "missing_random_baseline_detail" for row in warnings)
    assert rows[0]["decision"] == DECISION_REVIEW


def test_candidate_file_empty_and_zero_candidates(tmp_path: Path) -> None:
    write_standard_inputs(tmp_path)

    paths = build_research_decision_report(base_args(tmp_path))
    rows = read_csv(paths["summary"])
    warnings = read_csv(paths["warnings"])

    assert rows == []
    assert any(row["warning_type"] == "empty_candidate_file" for row in warnings)


def test_net_with_cost_none_fails(tmp_path: Path) -> None:
    args = base_args(tmp_path)
    args.cost_mode = "none"

    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        build_research_decision_report(args)


def test_long_and_short_outputs_are_separate(tmp_path: Path) -> None:
    write_standard_inputs(tmp_path, cross_rows=[good_cross_candidate()], random_rows=[random_row()], direction="long")
    write_standard_inputs(
        tmp_path,
        cross_rows=[good_cross_candidate(direction="short", combination_key="volume_dry_up_20:1")],
        random_rows=[
            random_row(
                direction="short",
                combination_key="volume_dry_up_20:1",
                random_baseline_classification="interesting_vs_random",
            )
        ],
        direction="short",
    )

    paths = build_research_decision_report(base_args(tmp_path, direction="short"))
    rows = read_csv(paths["summary"])

    assert all(row["direction"] == "short" for row in rows)
    assert rows[0]["combination_key"] == "volume_dry_up_20:1"
    assert not (tmp_path / "research_decision" / "run1" / "long").exists()


def test_overwrite_required(tmp_path: Path) -> None:
    write_standard_inputs(tmp_path, cross_rows=[good_cross_candidate()], random_rows=[random_row()])
    args = base_args(tmp_path)

    build_research_decision_report(args)
    with pytest.raises(FileExistsError, match="--overwrite"):
        build_research_decision_report(args)


def test_not_better_than_random_is_rejected(tmp_path: Path) -> None:
    write_standard_inputs(
        tmp_path,
        cross_rows=[good_cross_candidate()],
        random_rows=[random_row(random_baseline_classification="not_better_than_random")],
    )

    paths = build_research_decision_report(base_args(tmp_path))
    rows = read_csv(paths["summary"])

    assert rows[0]["decision"] == DECISION_REJECT
    assert rows[0]["primary_reason"] == "not_better_than_random"


def test_select_robust_needs_no_severe_penalties(tmp_path: Path) -> None:
    write_standard_inputs(
        tmp_path,
        cross_rows=[good_cross_candidate(worst_year_drawdown_improvement_pct=-80)],
        random_rows=[random_row(random_baseline_classification="robust_vs_random")],
    )

    paths = build_research_decision_report(base_args(tmp_path))
    rows = read_csv(paths["summary"])

    assert rows[0]["decision"] == DECISION_REJECT
    assert rows[0]["primary_reason"] == "worst_year_drawdown_very_negative"


def test_weak_or_missing_evidence_needs_review(tmp_path: Path) -> None:
    write_standard_inputs(
        tmp_path,
        cross_rows=[good_cross_candidate()],
        random_rows=[random_row(random_baseline_classification="weak_vs_random")],
    )

    paths = build_research_decision_report(base_args(tmp_path))
    rows = read_csv(paths["summary"])

    assert rows[0]["decision"] == DECISION_REVIEW
    assert rows[0]["primary_reason"] == "random_baseline_weak_or_missing"
