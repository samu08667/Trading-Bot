import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.build_controlled_rule_research_expansion import (
    READY_LABEL,
    REJECTED_LABEL,
    TIMEOUT_REVIEW_LABEL,
    parse_args,
    run_controlled_expansion,
)


TRADE_FIELDNAMES = [
    "symbol",
    "direction",
    "target_family",
    "horizon",
    "regime_column",
    "regime_value",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "exit_reason",
    "bars_held",
    "tp_atr",
    "sl_atr",
    "R",
    "cost_R",
    "net_R",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def review_summary(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "run_id": "unit_expansion",
        "final_research_only_classification": "READY_FOR_CONTROLLED_RULE_RESEARCH_BACKTEST_EXPANSION",
        "symbol": "GBPUSD",
        "direction": "short",
        "timeframe": "M15",
        "horizon": "10",
        "target_family": "preferred_1_5atr_1atr_hit_first",
        "regime_column": "session",
        "regime_value": "Off_hours",
        "feature_condition": (
            "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
            "numeric_tercile:tick_volume_percentile_100:mid_tercile"
        ),
        "tp_atr": "1.5",
        "sl_atr": "1.0",
        "same_bar_policy": "stop_first",
        "stress_spread_policy": "max_row_or_fallback",
        "input_rule_replay_classification": "RULE_REPLAY_MATCHED_STRESS_VALIDATION",
        "generated_logs_match_stress_validation": "True",
        "stress_trades_count": "120",
        "stress_mean_R": "0.4",
        "stress_median_R": "0.42",
        "stress_profit_factor_R": "2.4",
        "stress_cumulative_R": "48.0",
        "stress_max_drawdown_R": "2.0",
        "stress_yearly_positive_ratio": "1.0",
        "stress_monthly_positive_ratio": "0.9",
        "stress_rolling_50_min_cumulative_R": "8.0",
        "stress_rolling_100_min_cumulative_R": "18.0",
        "top_month_contribution_pct": "8.0",
        "top_5_percent_contribution_pct": "16.0",
        "stress_largest_drawdown_sequence_R": "2.0",
        "stress_longest_losing_streak": "2",
        "stress_longest_non_positive_streak": "3",
    }
    row.update(overrides)
    return row


def candidate_b_fields() -> dict[str, object]:
    return {
        "symbol": "EURUSD",
        "direction": "long",
        "timeframe": "M15",
        "horizon": "5",
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


def monthly_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for month in range(1, 13):
        rows.append(
            {
                "scope": "stress",
                "period": f"2024-{month:02d}",
                "trades_count": "10",
                "mean_R": "0.4",
                "median_R": "0.4",
                "profit_factor_R": "2.4",
                "cumulative_R": "4.0",
                "max_drawdown_R": "0.5",
                "positive": "True",
                "tp_hit_rate": "0.7",
                "sl_hit_rate": "0.2",
                "timeout_rate": "0.1",
            }
        )
    return rows


def yearly_rows(cumulative: str = "48.0") -> list[dict[str, object]]:
    return [
        {
            "scope": "stress",
            "period": "2024",
            "trades_count": "120",
            "mean_R": "0.4",
            "median_R": "0.4",
            "profit_factor_R": "2.4",
            "cumulative_R": cumulative,
            "max_drawdown_R": "2.0",
            "positive": str(float(cumulative) > 0),
            "tp_hit_rate": "0.7",
            "sl_hit_rate": "0.2",
            "timeout_rate": "0.1",
        }
    ]


def rolling_rows(rolling_50: str = "8.0", rolling_100: str = "18.0") -> list[dict[str, object]]:
    return [
        {
            "scope": "stress",
            "window_size": "50",
            "start_trade_index": "1",
            "end_trade_index": "50",
            "start_time": "2024-01-01 22:00:00",
            "end_time": "2024-02-01 22:00:00",
            "trades_count": "50",
            "mean_R": "0.16",
            "cumulative_R": rolling_50,
            "min_cumulative_R": "0.0",
            "max_drawdown_R": "1.0",
            "positive": str(float(rolling_50) > 0),
        },
        {
            "scope": "stress",
            "window_size": "100",
            "start_trade_index": "1",
            "end_trade_index": "100",
            "start_time": "2024-01-01 22:00:00",
            "end_time": "2024-04-01 22:00:00",
            "trades_count": "100",
            "mean_R": "0.18",
            "cumulative_R": rolling_100,
            "min_cumulative_R": "0.0",
            "max_drawdown_R": "1.2",
            "positive": str(float(rolling_100) > 0),
        },
    ]


def exit_rows(timeout_cumulative: str = "2.0", timeout_mean: str = "0.1") -> list[dict[str, object]]:
    return [
        {
            "scope": "stress",
            "exit_reason": "TP",
            "trades_count": "80",
            "hit_rate": "0.666",
            "mean_R": "0.6",
            "cumulative_R": "48.0",
            "mean_cost_R": "0.05",
            "mean_net_R": "0.6",
        },
        {
            "scope": "stress",
            "exit_reason": "TIMEOUT",
            "trades_count": "20",
            "hit_rate": "0.166",
            "mean_R": timeout_mean,
            "cumulative_R": timeout_cumulative,
            "mean_cost_R": "0.05",
            "mean_net_R": timeout_mean,
        },
    ]


def entry_hour_rows(
    *,
    hour22_count: str = "40",
    hour22_mean: str = "0.4",
    hour22_cumulative: str = "16.0",
    hour23_count: str = "38",
    hour23_mean: str = "0.35",
    hour23_cumulative: str = "13.3",
) -> list[dict[str, object]]:
    return [
        {
            "scope": "stress",
            "entry_hour": "22",
            "trades_count": hour22_count,
            "trade_pct": "0.33",
            "mean_R": hour22_mean,
            "cumulative_R": hour22_cumulative,
        },
        {
            "scope": "stress",
            "entry_hour": "23",
            "trades_count": hour23_count,
            "trade_pct": "0.31",
            "mean_R": hour23_mean,
            "cumulative_R": hour23_cumulative,
        },
    ]


def drawdown_rows(drawdown: str = "2.0") -> list[dict[str, object]]:
    return [
        {
            "scope": "stress",
            "sequence_id": "1",
            "start_trade_index": "10",
            "trough_trade_index": "12",
            "end_trade_index": "15",
            "max_drawdown_R": drawdown,
            "duration_trades": "6",
            "recovered": "True",
        }
    ]


def trade_rows(*, timeout_r: float | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = datetime(2024, 1, 1, 22, 0)
    for index in range(120):
        entry = start + timedelta(days=index)
        value = -0.2 if index % 10 == 0 else 0.45
        if timeout_r is not None and index % 8 == 0:
            exit_reason = "TIMEOUT"
            value = timeout_r
        elif timeout_r is None and index % 9 == 0:
            exit_reason = "TIMEOUT"
            value = 0.1
        elif index % 10 == 0:
            exit_reason = "SL"
        else:
            exit_reason = "TP"
        rows.append(
            {
                "symbol": "GBPUSD",
                "direction": "short",
                "target_family": "preferred_1_5atr_1atr_hit_first",
                "horizon": "10",
                "regime_column": "session",
                "regime_value": "Off_hours",
                "entry_time": entry.strftime("%Y-%m-%d %H:%M:%S"),
                "exit_time": (entry + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S"),
                "entry_price": "100.0",
                "exit_price": "99.0",
                "exit_reason": exit_reason,
                "bars_held": "10",
                "tp_atr": "1.5",
                "sl_atr": "1.0",
                "R": value,
                "cost_R": "0.05",
                "net_R": value,
            }
        )
    return rows


def equity_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    cumulative = 0.0
    peak = 0.0
    output: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        cumulative += float(row["R"])
        peak = max(peak, cumulative)
        output.append(
            {
                "trade_index": index,
                "exit_time": row["exit_time"],
                "cumulative_R": cumulative,
                "drawdown_R": peak - cumulative,
            }
        )
    return output


def write_review_package(
    tmp_path: Path,
    *,
    summary_overrides: dict[str, object] | None = None,
    warning_rows: list[dict[str, object]] | None = None,
    entry_rows: list[dict[str, object]] | None = None,
    timeout_cumulative: str = "2.0",
    timeout_mean: str = "0.1",
    rolling_50: str = "8.0",
    rolling_100: str = "18.0",
    yearly_cumulative: str = "48.0",
) -> Path:
    review_dir = tmp_path / "rule_review" / "unit_expansion"
    write_csv(review_dir / "rule_based_review_summary.csv", [review_summary(**(summary_overrides or {}))])
    (review_dir / "rule_based_review_report.md").write_text("review\n", encoding="utf-8")
    write_csv(review_dir / "rule_based_review_warnings.csv", warning_rows or [], ["severity", "check", "blocks_ready", "message"])
    write_csv(review_dir / "rule_based_review_monthly.csv", monthly_rows())
    write_csv(review_dir / "rule_based_review_yearly.csv", yearly_rows(yearly_cumulative))
    write_csv(review_dir / "rule_based_review_rolling_windows.csv", rolling_rows(rolling_50, rolling_100))
    write_csv(review_dir / "rule_based_review_exit_profile.csv", exit_rows(timeout_cumulative, timeout_mean))
    write_csv(review_dir / "rule_based_review_entry_hour.csv", entry_rows or entry_hour_rows())
    write_csv(review_dir / "rule_based_review_drawdown_sequences.csv", drawdown_rows())
    return review_dir


def write_replay_package(tmp_path: Path, *, timeout_r: float | None = None) -> Path:
    replay_dir = tmp_path / "rule_replay" / "unit_expansion"
    stress_trades = trade_rows(timeout_r=timeout_r)
    base_trades = [
        {
            **row,
            "R": float(row["R"]) + 0.03,
            "net_R": float(row["R"]) + 0.03,
        }
        for row in stress_trades
    ]
    write_csv(
        replay_dir / "rule_based_backtest_summary.csv",
        [
            {
                "final_rule_replay_classification": "RULE_REPLAY_MATCHED_STRESS_VALIDATION",
                "generated_logs_match_stress_validation": "True",
            }
        ],
    )
    write_csv(replay_dir / "rule_based_trade_log_base.csv", base_trades, TRADE_FIELDNAMES)
    write_csv(replay_dir / "rule_based_trade_log_stress.csv", stress_trades, TRADE_FIELDNAMES)
    write_csv(replay_dir / "rule_based_equity_curve_base.csv", equity_rows(base_trades))
    write_csv(replay_dir / "rule_based_equity_curve_stress.csv", equity_rows(stress_trades))
    write_csv(
        replay_dir / "rule_based_comparison_to_stress_validation.csv",
        [
            {"comparison_scope": "base", "trade_logs_match_within_tolerance": "True"},
            {"comparison_scope": "stress", "trade_logs_match_within_tolerance": "True"},
        ],
    )
    write_csv(replay_dir / "rule_based_warnings.csv", [], ["severity", "check", "blocks_match", "message"])
    return replay_dir


def build_args(
    tmp_path: Path,
    review_dir: Path,
    replay_dir: Path | None,
    *,
    overwrite: bool = True,
) -> argparse.Namespace:
    argv = [
        "--rule-review-dir",
        str(review_dir),
        "--output-root",
        str(tmp_path / "expansion_outputs"),
        "--run-id",
        "unit_expansion",
    ]
    if replay_dir is not None:
        argv.extend(["--rule-replay-dir", str(replay_dir)])
    if overwrite:
        argv.append("--overwrite")
    return parse_args(argv)


def run_package(
    tmp_path: Path,
    review_dir: Path,
    replay_dir: Path | None,
    *,
    overwrite: bool = True,
) -> tuple[dict[str, Path], dict[str, str], list[dict[str, str]]]:
    outputs = run_controlled_expansion(build_args(tmp_path, review_dir, replay_dir, overwrite=overwrite))
    summary = read_csv(outputs["summary"])[0]
    warnings = read_csv(outputs["warnings"])
    return outputs, summary, warnings


def test_happy_path_ready_for_baseline_and_cost_review(tmp_path: Path) -> None:
    review_dir = write_review_package(tmp_path)
    replay_dir = write_replay_package(tmp_path)

    outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)
    report = outputs["report"].read_text(encoding="utf-8")

    assert summary["final_research_only_classification"] == READY_LABEL
    assert summary["ready_for_baseline_and_cost_sensitivity_review"] == "True"
    assert warnings == []
    assert read_csv(outputs["entry_hour"])
    assert read_csv(outputs["subperiods"])
    assert read_csv(outputs["timeout_fragility"])
    assert read_csv(outputs["cost_sensitivity_plan"])
    assert read_csv(outputs["baseline_plan"])
    assert "Candidate can continue to baseline and cost-sensitivity review." in report


def test_different_candidate_metadata_flows_to_summary_report_and_baseline_plan(tmp_path: Path) -> None:
    review_dir = write_review_package(tmp_path, summary_overrides=candidate_b_fields())
    replay_dir = write_replay_package(tmp_path)

    outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)
    report = outputs["report"].read_text(encoding="utf-8")
    baseline_plan = read_csv(outputs["baseline_plan"])

    assert summary["final_research_only_classification"] == READY_LABEL
    assert summary["symbol"] == "EURUSD"
    assert summary["direction"] == "long"
    assert summary["horizon"] == "5"
    assert summary["target_family"] == "preferred_2atr_1atr_hit_first"
    assert summary["regime_value"] == "London"
    assert "momentum_score" in summary["feature_condition"]
    assert "EURUSD" in report
    assert "London" in report
    assert any("session=London" in row["comparison"] for row in baseline_plan)
    assert any("momentum_score" in row["comparison"] for row in baseline_plan)
    assert warnings == []


def test_input_review_not_ready_is_rejected(tmp_path: Path) -> None:
    review_dir = write_review_package(
        tmp_path,
        summary_overrides={"final_research_only_classification": "RULE_BASED_REVIEW_RETAINED"},
    )
    replay_dir = write_replay_package(tmp_path)

    _outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "input_review_classification" for row in warnings)


def test_severe_entry_hour_fragility_is_not_ready(tmp_path: Path) -> None:
    review_dir = write_review_package(
        tmp_path,
        entry_rows=entry_hour_rows(
            hour22_count="100",
            hour22_mean="0.5",
            hour22_cumulative="50.0",
            hour23_count="20",
            hour23_mean="-0.1",
            hour23_cumulative="-2.0",
        ),
    )
    replay_dir = write_replay_package(tmp_path)

    _outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)

    assert summary["final_research_only_classification"] != READY_LABEL
    assert any(row["check"] == "severe_entry_hour_fragility" for row in warnings)


def test_current_like_timeout_fragility_is_retained_for_timeout_review(tmp_path: Path) -> None:
    review_dir = write_review_package(tmp_path)
    replay_dir = write_replay_package(tmp_path, timeout_r=-0.11)

    outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)
    report = outputs["report"].read_text(encoding="utf-8")

    assert summary["final_research_only_classification"] == TIMEOUT_REVIEW_LABEL
    assert summary["timeout_severity"] == "timeout_review"
    assert any(row["check"] == "timeout_review_required" for row in warnings)
    assert "focused timeout fragility audit" in report
    assert "Candidate can continue to baseline and cost-sensitivity review." not in report


def test_severe_but_not_catastrophic_timeout_fragility_is_retained(tmp_path: Path) -> None:
    review_dir = write_review_package(tmp_path)
    replay_dir = write_replay_package(tmp_path, timeout_r=-0.22)

    _outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)

    assert summary["final_research_only_classification"] == TIMEOUT_REVIEW_LABEL
    assert summary["timeout_severity"] == "timeout_severe"
    assert any(row["check"] == "severe_timeout_fragility" for row in warnings)


def test_catastrophic_timeout_fragility_is_rejected(tmp_path: Path) -> None:
    review_dir = write_review_package(tmp_path)
    replay_dir = write_replay_package(tmp_path, timeout_r=-0.4)

    _outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert summary["timeout_severity"] == "timeout_blocking"
    assert any(row["check"] == "timeout_blocking_fragility" and row["blocking"] == "True" for row in warnings)


def test_negative_stress_mean_is_rejected(tmp_path: Path) -> None:
    review_dir = write_review_package(tmp_path, summary_overrides={"stress_mean_R": "-0.1"})
    replay_dir = write_replay_package(tmp_path)

    _outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "stress_mean_R" for row in warnings)


def test_negative_rolling_window_is_not_ready(tmp_path: Path) -> None:
    review_dir = write_review_package(
        tmp_path,
        summary_overrides={"stress_rolling_50_min_cumulative_R": "-0.5"},
        rolling_50="-0.5",
    )
    replay_dir = write_replay_package(tmp_path)

    _outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "rolling_50_min_cumulative_R" for row in warnings)


def test_negative_yearly_period_is_not_ready(tmp_path: Path) -> None:
    review_dir = write_review_package(
        tmp_path,
        summary_overrides={"stress_yearly_positive_ratio": "0.0"},
        yearly_cumulative="-1.0",
    )
    replay_dir = write_replay_package(tmp_path)

    _outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "yearly_positive_ratio" for row in warnings)
    assert any(row["check"] == "negative_year" for row in warnings)


def test_severe_concentration_is_not_ready(tmp_path: Path) -> None:
    review_dir = write_review_package(
        tmp_path,
        summary_overrides={"top_month_contribution_pct": "30.0", "top_5_percent_contribution_pct": "40.0"},
    )
    replay_dir = write_replay_package(tmp_path)

    _outputs, summary, warnings = run_package(tmp_path, review_dir, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "severe_top_month_contribution" for row in warnings)
    assert any(row["check"] == "severe_top_5_percent_contribution" for row in warnings)


def test_report_next_action_matches_rejected_classification(tmp_path: Path) -> None:
    review_dir = write_review_package(
        tmp_path,
        summary_overrides={"final_research_only_classification": "RULE_BASED_REVIEW_RETAINED"},
    )
    replay_dir = write_replay_package(tmp_path)

    outputs, summary, _warnings = run_package(tmp_path, review_dir, replay_dir)
    report = outputs["report"].read_text(encoding="utf-8")

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert "Candidate should not continue to baseline and cost-sensitivity review under current evidence." in report
    assert "Candidate can continue to baseline and cost-sensitivity review." not in report


def test_warning_csv_contains_structured_severity_fields(tmp_path: Path) -> None:
    review_dir = write_review_package(tmp_path)
    replay_dir = write_replay_package(tmp_path, timeout_r=-0.11)

    _outputs, _summary, warnings = run_package(tmp_path, review_dir, replay_dir)

    assert warnings
    assert {"severity", "blocking", "metric_value", "threshold"}.issubset(warnings[0])
    assert warnings[0]["severity"] == "review"
    assert warnings[0]["blocking"] == "False"
    assert warnings[0]["metric_value"] != ""
    assert warnings[0]["threshold"] != ""


def test_missing_input_file_errors(tmp_path: Path) -> None:
    review_dir = write_review_package(tmp_path)
    replay_dir = write_replay_package(tmp_path)
    (review_dir / "rule_based_review_summary.csv").unlink()

    with pytest.raises(FileNotFoundError, match="rule_based_review_summary"):
        run_package(tmp_path, review_dir, replay_dir)


def test_overwrite_protection(tmp_path: Path) -> None:
    review_dir = write_review_package(tmp_path)
    replay_dir = write_replay_package(tmp_path)
    run_package(tmp_path, review_dir, replay_dir, overwrite=True)

    with pytest.raises(FileExistsError, match="--overwrite"):
        run_package(tmp_path, review_dir, replay_dir, overwrite=False)
