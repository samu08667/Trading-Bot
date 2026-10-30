import argparse
import csv
from pathlib import Path

import pytest

from scripts.build_horizon_consistency_report import build_horizon_consistency_report


SCORECARD_FIELDS = [
    "feature",
    "condition",
    "feature_condition_key",
    "direction",
    "cost_mode",
    "return_mode",
    "total_score",
    "final_feature_classification",
    "avg_positive_year_ratio",
    "avg_positive_symbol_ratio",
    "avg_profit_factor_improvement_pct",
    "avg_max_drawdown_improvement_pct",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "best_month_contribution_pct",
    "top_5_percent_trades_contribution_pct",
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


def scorecard_row(
    key: str,
    *,
    classification: str = "strong",
    score: float = 8,
    pf: float = 10,
    dd: float = 5,
    direction: str = "long",
    cost_mode: str = "none",
    return_mode: str = "gross",
) -> dict[str, object]:
    feature, condition = key.split(":", 1)
    return {
        "feature": feature,
        "condition": condition,
        "feature_condition_key": key,
        "direction": direction,
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "total_score": score,
        "final_feature_classification": classification,
        "avg_positive_year_ratio": 0.75 if classification in {"strong", "interesting"} else 0.40,
        "avg_positive_symbol_ratio": 0.75 if classification in {"strong", "interesting"} else 0.40,
        "avg_profit_factor_improvement_pct": pf,
        "avg_max_drawdown_improvement_pct": dd,
        "monthly_positive_ratio": 0.60,
        "quarterly_positive_ratio": 0.60,
        "best_month_contribution_pct": 35,
        "top_5_percent_trades_contribution_pct": 45,
    }


def write_scorecard(tmp_path: Path, run_id: str, direction: str, rows: list[dict[str, object]]) -> None:
    write_csv(
        tmp_path / "scorecards" / run_id / direction / "final_feature_scorecard.csv",
        rows,
        SCORECARD_FIELDS,
    )


def base_args(tmp_path: Path, direction: str = "long") -> argparse.Namespace:
    return argparse.Namespace(
        group_id="group1",
        direction=direction,
        h5_run_id="run_h5",
        h10_run_id="run_h10",
        h20_run_id="run_h20",
        scorecard_dir=tmp_path / "scorecards",
        validation_dir=tmp_path / "validation",
        output_dir=tmp_path / "horizon_consistency",
        cost_mode="none",
        return_mode="gross",
        include_pair_specific=False,
        overwrite=False,
    )


def write_three_horizons(
    tmp_path: Path,
    key: str,
    h5: dict[str, object],
    h10: dict[str, object],
    h20: dict[str, object],
    *,
    direction: str = "long",
) -> None:
    write_scorecard(tmp_path, "run_h5", direction, [scorecard_row(key, direction=direction, **h5)])
    write_scorecard(tmp_path, "run_h10", direction, [scorecard_row(key, direction=direction, **h10)])
    write_scorecard(tmp_path, "run_h20", direction, [scorecard_row(key, direction=direction, **h20)])


def test_feature_present_on_h5_h10_h20_is_aggregated(tmp_path: Path) -> None:
    write_three_horizons(
        tmp_path,
        "ma_diff:ma_diff_gt_0",
        {"classification": "strong", "score": 8, "pf": 10, "dd": 5},
        {"classification": "interesting", "score": 5, "pf": 6, "dd": 3},
        {"classification": "weak", "score": 1, "pf": 0, "dd": 0},
    )

    paths = build_horizon_consistency_report(base_args(tmp_path))
    rows = read_csv(paths["summary"])

    assert len(rows) == 1
    assert rows[0]["feature_condition_key"] == "ma_diff:ma_diff_gt_0"
    assert rows[0]["h5_classification"] == "strong"
    assert rows[0]["h10_score"] == "5.0"
    assert rows[0]["horizon_consistency_classification"] == "consistent_across_horizons"


def test_h10_h20_good_h5_weak_is_consistent_medium_slow(tmp_path: Path) -> None:
    write_three_horizons(
        tmp_path,
        "hour_session:Asia",
        {"classification": "weak", "score": 1, "pf": 0, "dd": 0},
        {"classification": "strong", "score": 8, "pf": 9, "dd": 5},
        {"classification": "interesting", "score": 5, "pf": 6, "dd": 4},
    )

    rows = read_csv(build_horizon_consistency_report(base_args(tmp_path))["summary"])

    assert rows[0]["horizon_consistency_classification"] == "consistent_medium_slow"


def test_good_only_on_h5_is_short_horizon_only(tmp_path: Path) -> None:
    write_three_horizons(
        tmp_path,
        "volume_spike_20:1",
        {"classification": "strong", "score": 8, "pf": 9, "dd": 4},
        {"classification": "weak", "score": 1, "pf": 0, "dd": 0},
        {"classification": "weak", "score": 1, "pf": 0, "dd": 0},
    )

    rows = read_csv(build_horizon_consistency_report(base_args(tmp_path))["summary"])

    assert rows[0]["horizon_consistency_classification"] == "short_horizon_only"


def test_good_only_on_h20_is_long_horizon_only(tmp_path: Path) -> None:
    write_three_horizons(
        tmp_path,
        "day_of_week:Monday",
        {"classification": "weak", "score": 1, "pf": 0, "dd": 0},
        {"classification": "weak", "score": 1, "pf": 0, "dd": 0},
        {"classification": "strong", "score": 8, "pf": 9, "dd": 4},
    )

    rows = read_csv(build_horizon_consistency_report(base_args(tmp_path))["summary"])

    assert rows[0]["horizon_consistency_classification"] == "long_horizon_only"


def test_contradictory_feature_is_unstable(tmp_path: Path) -> None:
    write_three_horizons(
        tmp_path,
        "volume_dry_up_20:0",
        {"classification": "strong", "score": 8, "pf": 12, "dd": 8},
        {"classification": "weak", "score": -5, "pf": -15, "dd": -30},
        {"classification": "weak", "score": 1, "pf": 0, "dd": 0},
    )

    rows = read_csv(build_horizon_consistency_report(base_args(tmp_path))["summary"])

    assert rows[0]["horizon_consistency_classification"] == "unstable_across_horizons"


def test_missing_file_writes_warning_without_crashing(tmp_path: Path) -> None:
    write_scorecard(tmp_path, "run_h5", "long", [scorecard_row("ma_diff:ma_diff_gt_0")])
    write_scorecard(tmp_path, "run_h10", "long", [scorecard_row("ma_diff:ma_diff_gt_0")])

    paths = build_horizon_consistency_report(base_args(tmp_path))
    warnings = read_csv(paths["warnings"])

    assert any(row["warning_type"] == "missing_input_file" and row["horizon"] == "h20" for row in warnings)


def test_empty_file_does_not_crash(tmp_path: Path) -> None:
    write_scorecard(tmp_path, "run_h5", "long", [])
    write_scorecard(tmp_path, "run_h10", "long", [scorecard_row("ma_diff:ma_diff_gt_0")])
    write_scorecard(tmp_path, "run_h20", "long", [scorecard_row("ma_diff:ma_diff_gt_0")])

    paths = build_horizon_consistency_report(base_args(tmp_path))
    warnings = read_csv(paths["warnings"])

    assert any(row["warning_type"] == "empty_input_file" and row["horizon"] == "h5" for row in warnings)


def test_net_with_cost_none_fails(tmp_path: Path) -> None:
    args = base_args(tmp_path)
    args.return_mode = "net"

    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        build_horizon_consistency_report(args)


def test_long_short_outputs_are_separate(tmp_path: Path) -> None:
    write_three_horizons(
        tmp_path,
        "ma_diff:ma_diff_gt_0",
        {"classification": "strong", "score": 8, "pf": 10, "dd": 5},
        {"classification": "strong", "score": 8, "pf": 10, "dd": 5},
        {"classification": "strong", "score": 8, "pf": 10, "dd": 5},
        direction="short",
    )
    write_scorecard(tmp_path, "run_h5", "long", [scorecard_row("volume_spike_20:1")])
    write_scorecard(tmp_path, "run_h10", "long", [scorecard_row("volume_spike_20:1")])
    write_scorecard(tmp_path, "run_h20", "long", [scorecard_row("volume_spike_20:1")])

    paths = build_horizon_consistency_report(base_args(tmp_path, direction="short"))
    rows = read_csv(paths["summary"])

    assert rows[0]["direction"] == "short"
    assert rows[0]["feature_condition_key"] == "ma_diff:ma_diff_gt_0"
    assert not (tmp_path / "horizon_consistency" / "group1" / "long").exists()


def test_overwrite_required_if_outputs_exist(tmp_path: Path) -> None:
    write_three_horizons(
        tmp_path,
        "ma_diff:ma_diff_gt_0",
        {"classification": "strong", "score": 8, "pf": 10, "dd": 5},
        {"classification": "strong", "score": 8, "pf": 10, "dd": 5},
        {"classification": "strong", "score": 8, "pf": 10, "dd": 5},
    )
    args = base_args(tmp_path)

    build_horizon_consistency_report(args)
    with pytest.raises(FileExistsError, match="--overwrite"):
        build_horizon_consistency_report(args)
    args.overwrite = True
    build_horizon_consistency_report(args)
