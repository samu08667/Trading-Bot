import argparse
import csv
from pathlib import Path

import pytest

from scripts.build_regime_candidate_review_package import (
    READY_LABEL,
    REJECTED_LABEL,
    RETAINED_LABEL,
    parse_args,
    run_review_package,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def stress_summary_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "GBPUSD",
        "direction": "short",
        "timeframe": "M15",
        "horizon": "h10",
        "target_family": "preferred_1_5atr_1atr_hit_first",
        "regime_column": "session",
        "regime_value": "Off_hours",
        "feature_condition": (
            "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
            "numeric_tercile:tick_volume_percentile_100:mid_tercile"
        ),
        "tp_atr": "1.5",
        "sl_atr": "1.0",
        "candidate_scope": "exact_feature_combination",
        "exact_candidate_not_available_reason": "",
        "stress_spread_policy": "max_row_or_fallback",
        "stress_applied": "True",
        "stress_changed_cost_R": "True",
        "stress_cost_no_effect_warning": "False",
        "sequential_trades_count": "60",
        "stress_sequential_trades_count": "60",
        "mean_R": "0.45",
        "profit_factor_R": "2.8",
        "stress_mean_R": "0.42",
        "stress_profit_factor_R": "2.6",
        "stress_mean_R_delta": "-0.03",
        "stress_profit_factor_R_delta": "-0.2",
        "mean_cost_R_base": "0.02",
        "mean_cost_R_stress": "0.05",
        "cost_R_delta_mean": "0.03",
        "net_R_delta_mean": "-0.03",
        "yearly_positive_ratio": "1.0",
        "max_drawdown_R": "2.0",
        "stress_max_drawdown_R": "2.2",
        "top_month_contribution_pct": "20.0",
        "top_5_percent_contribution_pct": "25.0",
        "random_baseline_available": "True",
        "candidate_mean_R_vs_random_p95": "0.12",
        "candidate_profit_factor_R_vs_random_p95": "0.7",
    }
    row.update(overrides)
    return row


def candidate_b_fields() -> dict[str, object]:
    return {
        "symbol": "EURUSD",
        "direction": "long",
        "timeframe": "M15",
        "horizon": "h5",
        "target_family": "preferred_2atr_1atr_hit_first",
        "regime_column": "session",
        "regime_value": "London",
        "feature_condition": (
            "numeric_tercile:momentum_score:high_tercile AND "
            "numeric_tercile:liquidity_rank:low_tercile"
        ),
        "tp_atr": "2.0",
        "sl_atr": "1.0",
    }


def trade_rows() -> list[dict[str, object]]:
    return [
        {"exit_reason": "tp", "R": "1.5", "cost_R": "0.02", "net_R": "1.48"},
        {"exit_reason": "sl", "R": "-1.0", "cost_R": "0.02", "net_R": "-1.02"},
        {"exit_reason": "timeout", "R": "0.3", "cost_R": "0.02", "net_R": "0.28"},
    ]


def equity_rows() -> list[dict[str, object]]:
    return [
        {"trade_index": "1", "exit_time": "2022-01-01 00:15:00", "cumulative_R": "1.48", "drawdown_R": "0.0"},
        {"trade_index": "2", "exit_time": "2022-01-01 00:30:00", "cumulative_R": "0.46", "drawdown_R": "1.02"},
        {"trade_index": "3", "exit_time": "2022-01-01 00:45:00", "cumulative_R": "0.74", "drawdown_R": "0.74"},
    ]


def random_rows(**overrides: object) -> list[dict[str, object]]:
    row: dict[str, object] = {
        "iterations": "20",
        "random_mean_R_mean": "0.1",
        "random_mean_R_median": "0.08",
        "random_mean_R_p95": "0.3",
        "random_profit_factor_R_mean": "1.3",
        "random_profit_factor_R_p95": "1.9",
        "random_max_drawdown_R_median": "4.0",
        "candidate_mean_R_vs_random_p95": "0.12",
        "candidate_profit_factor_R_vs_random_p95": "0.7",
        "candidate_percentile_vs_random_mean_R": "1.0",
        "random_baseline_available": "True",
        "random_baseline_not_available_reason": "",
    }
    row.update(overrides)
    return [row]


def yearly_rows() -> list[dict[str, object]]:
    return [
        {
            "year": "2022",
            "trades_count": "30",
            "mean_R": "0.4",
            "profit_factor_R": "2.4",
            "cumulative_R": "12.0",
            "max_drawdown_R": "2.0",
        },
        {
            "year": "2023",
            "trades_count": "30",
            "mean_R": "0.44",
            "profit_factor_R": "2.7",
            "cumulative_R": "13.2",
            "max_drawdown_R": "1.8",
        },
    ]


def walk_forward_rows(test_classification: str = "review") -> list[dict[str, object]]:
    return [
        {
            "split_id": "1",
            "train_trades": "30",
            "test_trades": "30",
            "test_mean_R": "0.33",
            "test_profit_factor_R": "2.1",
            "test_classification": test_classification,
        }
    ]


def write_stress_package(tmp_path: Path, **summary_overrides: object) -> Path:
    stress_dir = tmp_path / "stress_outputs" / "unit_candidate"
    write_csv(stress_dir / "candidate_stress_summary.csv", [stress_summary_row(**summary_overrides)])
    write_csv(stress_dir / "trade_log_base.csv", trade_rows())
    write_csv(stress_dir / "trade_log_stress.csv", trade_rows())
    write_csv(stress_dir / "equity_curve_base.csv", equity_rows())
    write_csv(stress_dir / "equity_curve_stress.csv", equity_rows())
    write_csv(stress_dir / "yearly_validation.csv", yearly_rows())
    write_csv(stress_dir / "walk_forward_validation.csv", walk_forward_rows())
    write_csv(stress_dir / "random_baseline_summary.csv", random_rows())
    return stress_dir


def build_args(tmp_path: Path, stress_dir: Path, *, overwrite: bool = True) -> argparse.Namespace:
    argv = [
        "--stress-output-dir",
        str(stress_dir),
        "--output-root",
        str(tmp_path / "review_outputs"),
        "--run-id",
        "unit_candidate",
    ]
    if overwrite:
        argv.append("--overwrite")
    return parse_args(argv)


def run_package(tmp_path: Path, stress_dir: Path, *, overwrite: bool = True) -> tuple[dict[str, Path], dict[str, str], list[dict[str, str]]]:
    outputs = run_review_package(build_args(tmp_path, stress_dir, overwrite=overwrite))
    summary = read_csv(outputs["candidate_review_summary"])[0]
    warnings = read_csv(outputs["candidate_review_warnings"])
    return outputs, summary, warnings


def test_happy_path_ready_for_rule_based_review(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path)

    outputs, summary, warnings = run_package(tmp_path, stress_dir)
    report = outputs["candidate_review_report"].read_text(encoding="utf-8")

    assert summary["final_research_only_classification"] == READY_LABEL
    assert summary["ready_for_rule_based_research_backtest_review"] == "True"
    assert summary["weak_walk_forward_count"] == "0"
    assert warnings == []
    assert "Candidate may be considered for a future offline rule-based research backtester." in report


def test_candidate_metadata_is_read_from_input_files_for_different_candidate(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path, **candidate_b_fields())

    outputs, summary, warnings = run_package(tmp_path, stress_dir)
    report = outputs["candidate_review_report"].read_text(encoding="utf-8")

    assert summary["final_research_only_classification"] == READY_LABEL
    assert summary["symbol"] == "EURUSD"
    assert summary["direction"] == "long"
    assert summary["horizon"] == "h5"
    assert summary["target_family"] == "preferred_2atr_1atr_hit_first"
    assert summary["regime_value"] == "London"
    assert "momentum_score" in summary["feature_condition"]
    assert "EURUSD" in report
    assert "London" in report
    assert "momentum_score" in report
    assert warnings == []


def test_missing_candidate_metadata_writes_clear_warning(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path, symbol="")

    _outputs, summary, warnings = run_package(tmp_path, stress_dir)

    assert summary["ready_for_rule_based_research_backtest_review"] == "False"
    assert any(row["check"] == "candidate_metadata_missing" and "symbol" in row["message"] for row in warnings)


def test_broad_regime_scope_is_not_ready(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path, candidate_scope="broad_regime_only")

    _outputs, summary, warnings = run_package(tmp_path, stress_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert summary["ready_for_rule_based_research_backtest_review"] == "False"
    assert any(row["check"] == "candidate_scope" for row in warnings)


def test_stress_no_effect_warning_is_not_ready(tmp_path: Path) -> None:
    stress_dir = write_stress_package(
        tmp_path,
        stress_changed_cost_R="False",
        stress_cost_no_effect_warning="True",
    )

    _outputs, summary, warnings = run_package(tmp_path, stress_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "stress_cost_no_effect_warning" for row in warnings)


def test_random_baseline_unavailable_is_not_ready(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path)
    write_csv(
        stress_dir / "random_baseline_summary.csv",
        random_rows(random_baseline_available="False", random_baseline_not_available_reason="not enough rows"),
    )

    _outputs, summary, warnings = run_package(tmp_path, stress_dir)

    assert summary["final_research_only_classification"] == RETAINED_LABEL
    assert summary["ready_for_rule_based_research_backtest_review"] == "False"
    assert any(row["check"] == "random_baseline_available" for row in warnings)


def test_random_mean_margin_not_beaten_is_not_ready(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path)
    write_csv(stress_dir / "random_baseline_summary.csv", random_rows(candidate_mean_R_vs_random_p95="0"))

    _outputs, summary, warnings = run_package(tmp_path, stress_dir)

    assert summary["final_research_only_classification"] == RETAINED_LABEL
    assert summary["ready_for_rule_based_research_backtest_review"] == "False"
    assert any(row["check"] == "candidate_mean_R_vs_random_p95" for row in warnings)


def test_weak_walk_forward_split_is_not_ready(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path)
    write_csv(stress_dir / "walk_forward_validation.csv", walk_forward_rows("weak"))

    _outputs, summary, warnings = run_package(tmp_path, stress_dir)

    assert summary["final_research_only_classification"] == RETAINED_LABEL
    assert summary["weak_walk_forward_count"] == "1"
    assert any(row["check"] == "walk_forward_weak_split" for row in warnings)


def test_missing_auxiliary_input_file_writes_warning(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path)
    (stress_dir / "random_baseline_summary.csv").unlink()

    _outputs, summary, warnings = run_package(tmp_path, stress_dir)

    assert summary["final_research_only_classification"] == RETAINED_LABEL
    assert any(row["check"] == "missing_random_baseline_summary_csv" for row in warnings)
    assert any(row["check"] == "random_baseline_available" for row in warnings)


def test_overwrite_protection(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path)
    run_package(tmp_path, stress_dir, overwrite=True)

    with pytest.raises(FileExistsError, match="--overwrite"):
        run_package(tmp_path, stress_dir, overwrite=False)
