import argparse
import csv
from datetime import datetime
from pathlib import Path

import pytest

from scripts.build_rule_based_regime_candidate_review import (
    READY_LABEL,
    REJECTED_LABEL,
    RETAINED_LABEL,
    parse_args,
    run_rule_based_review,
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


def default_values(count: int = 120) -> list[float]:
    return [-0.2 if index % 10 == 0 else 0.45 for index in range(count)]


def trade_rows(
    values: list[float] | None = None,
    *,
    start_year: int = 2024,
    force_timeout_negative: bool = False,
) -> list[dict[str, object]]:
    selected = values or default_values()
    rows: list[dict[str, object]] = []
    for index, value in enumerate(selected):
        year = start_year + index // 120
        month = index % 12 + 1
        day = index % 10 + 1
        hour = [0, 1, 2, 21, 22, 23][index % 6]
        entry = datetime(year, month, day, hour, 0)
        exit_time = entry.replace(minute=15)
        if force_timeout_negative and index % 9 == 0:
            exit_reason = "TIMEOUT"
            value = -0.4
        elif index % 10 == 0:
            exit_reason = "SL"
        elif index % 9 == 0:
            exit_reason = "TIMEOUT"
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
                "exit_time": exit_time.strftime("%Y-%m-%d %H:%M:%S"),
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


def summary_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "run_id": "unit_rule_review",
        "final_rule_replay_classification": "RULE_REPLAY_MATCHED_STRESS_VALIDATION",
        "generated_logs_match_stress_validation": "True",
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
        "atr_column": "atr_20",
        "same_bar_policy": "stop_first",
        "bar_level_no_overlap": "True",
        "stress_spread_policy": "max_row_or_fallback",
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


def comparison_rows(match: bool = True) -> list[dict[str, object]]:
    return [
        {"comparison_scope": "base", "trade_logs_match_within_tolerance": str(match)},
        {"comparison_scope": "stress", "trade_logs_match_within_tolerance": str(match)},
    ]


def write_replay_package(
    tmp_path: Path,
    *,
    stress_values: list[float] | None = None,
    base_values: list[float] | None = None,
    summary_overrides: dict[str, object] | None = None,
    comparison_match: bool = True,
    warning_rows: list[dict[str, object]] | None = None,
    force_timeout_negative: bool = False,
) -> Path:
    replay_dir = tmp_path / "rule_replay" / "unit_rule_review"
    stress_trades = trade_rows(stress_values, force_timeout_negative=force_timeout_negative)
    base_trades = trade_rows(base_values or [float(row["R"]) + 0.03 for row in stress_trades])
    write_csv(replay_dir / "rule_based_backtest_summary.csv", [summary_row(**(summary_overrides or {}))])
    write_csv(replay_dir / "rule_based_comparison_to_stress_validation.csv", comparison_rows(comparison_match))
    write_csv(replay_dir / "rule_based_trade_log_base.csv", base_trades, TRADE_FIELDNAMES)
    write_csv(replay_dir / "rule_based_trade_log_stress.csv", stress_trades, TRADE_FIELDNAMES)
    write_csv(replay_dir / "rule_based_equity_curve_base.csv", equity_rows(base_trades))
    write_csv(replay_dir / "rule_based_equity_curve_stress.csv", equity_rows(stress_trades))
    write_csv(
        replay_dir / "rule_based_warnings.csv",
        warning_rows or [],
        ["severity", "check", "blocks_match", "message"],
    )
    return replay_dir


def build_args(tmp_path: Path, replay_dir: Path, *, overwrite: bool = True) -> argparse.Namespace:
    argv = [
        "--rule-replay-dir",
        str(replay_dir),
        "--output-root",
        str(tmp_path / "review_outputs"),
        "--run-id",
        "unit_rule_review",
    ]
    if overwrite:
        argv.append("--overwrite")
    return parse_args(argv)


def run_review(
    tmp_path: Path,
    replay_dir: Path,
    *,
    overwrite: bool = True,
) -> tuple[dict[str, Path], dict[str, str], list[dict[str, str]]]:
    outputs = run_rule_based_review(build_args(tmp_path, replay_dir, overwrite=overwrite))
    summary = read_csv(outputs["summary"])[0]
    warnings = read_csv(outputs["warnings"])
    return outputs, summary, warnings


def test_happy_path_ready_for_controlled_expansion(tmp_path: Path) -> None:
    replay_dir = write_replay_package(tmp_path)

    outputs, summary, warnings = run_review(tmp_path, replay_dir)
    report = outputs["report"].read_text(encoding="utf-8")

    assert summary["final_research_only_classification"] == READY_LABEL
    assert summary["ready_for_controlled_rule_research_backtest_expansion"] == "True"
    assert warnings == []
    assert read_csv(outputs["monthly"])
    assert read_csv(outputs["yearly"])
    assert read_csv(outputs["rolling"])
    assert read_csv(outputs["exit_profile"])
    assert read_csv(outputs["entry_hour"])
    assert "Candidate can continue to controlled offline rule research expansion." in report


def test_different_candidate_metadata_flows_to_summary_and_report(tmp_path: Path) -> None:
    replay_dir = write_replay_package(tmp_path, summary_overrides=candidate_b_fields())

    outputs, summary, warnings = run_review(tmp_path, replay_dir)
    report = outputs["report"].read_text(encoding="utf-8")

    assert summary["final_research_only_classification"] == READY_LABEL
    assert summary["symbol"] == "EURUSD"
    assert summary["direction"] == "long"
    assert summary["horizon"] == "5"
    assert summary["target_family"] == "preferred_2atr_1atr_hit_first"
    assert summary["regime_value"] == "London"
    assert "momentum_score" in summary["feature_condition"]
    assert "EURUSD" in report
    assert "London" in report
    assert "momentum_score" in report
    assert warnings == []


def test_missing_candidate_metadata_writes_clear_warning(tmp_path: Path) -> None:
    replay_dir = write_replay_package(tmp_path, summary_overrides={"symbol": ""})

    _outputs, summary, warnings = run_review(tmp_path, replay_dir)

    assert summary["ready_for_controlled_rule_research_backtest_expansion"] == "False"
    assert any(row["check"] == "candidate_metadata_missing" and "symbol" in row["message"] for row in warnings)


def test_replay_mismatch_is_rejected(tmp_path: Path) -> None:
    replay_dir = write_replay_package(
        tmp_path,
        summary_overrides={"final_rule_replay_classification": "RULE_REPLAY_MISMATCH_REJECTED"},
        comparison_match=False,
    )

    _outputs, summary, warnings = run_review(tmp_path, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "rule_replay_classification" for row in warnings)


def test_stress_mean_not_positive_is_rejected(tmp_path: Path) -> None:
    replay_dir = write_replay_package(tmp_path, stress_values=[-0.05] * 120)

    _outputs, summary, warnings = run_review(tmp_path, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "stress_mean_R" for row in warnings)


def test_stress_profit_factor_not_above_one_is_rejected(tmp_path: Path) -> None:
    replay_dir = write_replay_package(tmp_path, stress_values=[0.2 if index % 2 == 0 else -0.2 for index in range(120)])

    _outputs, summary, warnings = run_review(tmp_path, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "stress_profit_factor_R" for row in warnings)


def test_negative_year_is_not_ready(tmp_path: Path) -> None:
    values = default_values(240)
    for index in range(120, 240):
        values[index] = -0.05
    replay_dir = write_replay_package(tmp_path, stress_values=values)

    _outputs, summary, warnings = run_review(tmp_path, replay_dir)

    assert summary["final_research_only_classification"] != READY_LABEL
    assert any(row["check"] == "negative_year" for row in warnings)


def test_rolling_50_non_positive_window_is_not_ready(tmp_path: Path) -> None:
    values = default_values()
    for index in range(50):
        values[index] = -0.01
    for index in range(50, 120):
        values[index] = 0.6
    replay_dir = write_replay_package(tmp_path, stress_values=values)

    _outputs, summary, warnings = run_review(tmp_path, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "rolling_50_cumulative_R" for row in warnings)


def test_severe_concentration_is_not_ready(tmp_path: Path) -> None:
    values = [0.05] * 120
    values[0] = 10.0
    replay_dir = write_replay_package(tmp_path, stress_values=values)

    _outputs, summary, warnings = run_review(tmp_path, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "severe_top_5_percent_contribution" for row in warnings)


def test_strongly_negative_timeout_bucket_is_not_ready(tmp_path: Path) -> None:
    replay_dir = write_replay_package(tmp_path, force_timeout_negative=True)

    _outputs, summary, warnings = run_review(tmp_path, replay_dir)

    assert summary["final_research_only_classification"] == REJECTED_LABEL
    assert any(row["check"] == "timeout_fragility" for row in warnings)


def test_missing_input_file_errors(tmp_path: Path) -> None:
    replay_dir = write_replay_package(tmp_path)
    (replay_dir / "rule_based_backtest_summary.csv").unlink()

    with pytest.raises(FileNotFoundError, match="rule_based_backtest_summary"):
        run_review(tmp_path, replay_dir)


def test_overwrite_protection(tmp_path: Path) -> None:
    replay_dir = write_replay_package(tmp_path)
    run_review(tmp_path, replay_dir, overwrite=True)

    with pytest.raises(FileExistsError, match="--overwrite"):
        run_review(tmp_path, replay_dir, overwrite=False)
