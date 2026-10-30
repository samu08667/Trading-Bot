import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.build_timeout_fragility_audit import (
    FAILED_LABEL,
    PASSED_LABEL,
    RETAINED_LABEL,
    build_timeout_fragility_audit,
    parse_args,
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


def candidate_fields(**overrides: object) -> dict[str, object]:
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
        "same_bar_policy": "stop_first",
        "candidate_scope": "exact_feature_combination",
        "stress_spread_policy": "max_row_or_fallback",
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


def trade_row(entry: datetime, exit_reason: str, value: float) -> dict[str, object]:
    return {
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
        "net_R": value - 0.05,
    }


def build_stress_rows(
    timeout_by_year: dict[int, list[float]],
    *,
    stress_total_R: float = 100.0,
    non_timeout_count: int = 20,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    timeout_total = sum(sum(values) for values in timeout_by_year.values())
    non_timeout_value = (stress_total_R - timeout_total) / non_timeout_count
    start = datetime(2021, 1, 1, 22, 0)
    for index in range(non_timeout_count):
        rows.append(trade_row(start + timedelta(days=index), "TP", non_timeout_value))
    for year, values in sorted(timeout_by_year.items()):
        for index, value in enumerate(values):
            rows.append(trade_row(datetime(year, 1 + index, 2, 23, 0), "TIMEOUT", value))
    return sorted(rows, key=lambda row: str(row["entry_time"]))


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


def write_controlled_package(
    tmp_path: Path,
    *,
    classification: str = "CONTROLLED_EXPANSION_RETAINED_FOR_TIMEOUT_REVIEW",
    warning_rows: list[dict[str, object]] | None = None,
    candidate_overrides: dict[str, object] | None = None,
) -> Path:
    controlled_dir = tmp_path / "controlled" / "unit_timeout_audit"
    summary = {
        "run_id": "unit_timeout_audit",
        "final_research_only_classification": classification,
        "timeout_severity": "timeout_review",
        "blocking_warnings_count": "0",
        "stress_cumulative_R": "100.0",
        "stress_mean_R": "1.0",
        "stress_profit_factor_R": "inf",
        "timeout_count": "4",
        "timeout_trade_share": "0.1",
        "timeout_cumulative_R": "-1.0",
        **candidate_fields(**(candidate_overrides or {})),
    }
    write_csv(controlled_dir / "controlled_rule_expansion_summary.csv", [summary])
    (controlled_dir / "controlled_rule_expansion_report.md").write_text("controlled\n", encoding="utf-8")
    write_csv(
        controlled_dir / "controlled_rule_expansion_timeout_fragility.csv",
        [
            {
                "scope": "stress",
                "period_type": "overall",
                "period": "all",
                "timeout_count": "4",
                "timeout_trade_pct": "0.1",
                "timeout_mean_R": "-0.25",
                "timeout_cumulative_R": "-1.0",
            }
        ],
    )
    write_csv(
        controlled_dir / "controlled_rule_expansion_warnings.csv",
        warning_rows or [],
        ["warning_code", "severity", "blocking", "message", "related_metric", "metric_value", "threshold"],
    )
    write_csv(
        controlled_dir / "controlled_rule_expansion_subperiods.csv",
        [{"scope": "stress", "subperiod": "early", "cumulative_R": "10.0"}],
    )
    write_csv(
        controlled_dir / "controlled_rule_expansion_entry_hour.csv",
        [{"scope": "stress", "entry_hour": "23", "cumulative_R": "10.0"}],
    )
    return controlled_dir


def write_replay_package(
    tmp_path: Path,
    stress_rows: list[dict[str, object]],
    *,
    candidate_overrides: dict[str, object] | None = None,
) -> Path:
    replay_dir = tmp_path / "replay" / "unit_timeout_audit"
    base_rows = [{**row, "R": float(row["R"]) + 0.1, "net_R": float(row["net_R"]) + 0.1} for row in stress_rows]
    write_csv(
        replay_dir / "rule_based_backtest_summary.csv",
        [
            {
                "final_rule_replay_classification": "RULE_REPLAY_MATCHED_STRESS_VALIDATION",
                "generated_logs_match_stress_validation": "True",
                **candidate_fields(**(candidate_overrides or {})),
            }
        ],
    )
    write_csv(replay_dir / "rule_based_trade_log_stress.csv", stress_rows, TRADE_FIELDNAMES)
    write_csv(replay_dir / "rule_based_trade_log_base.csv", base_rows, TRADE_FIELDNAMES)
    write_csv(replay_dir / "rule_based_equity_curve_stress.csv", equity_rows(stress_rows))
    write_csv(replay_dir / "rule_based_warnings.csv", [], ["severity", "check", "blocks_match", "message"])
    return replay_dir


def build_args(
    tmp_path: Path,
    controlled_dir: Path,
    replay_dir: Path,
    *,
    overwrite: bool = True,
) -> argparse.Namespace:
    argv = [
        "--controlled-expansion-dir",
        str(controlled_dir),
        "--rule-replay-dir",
        str(replay_dir),
        "--output-root",
        str(tmp_path / "audit_outputs"),
        "--run-id",
        "unit_timeout_audit",
    ]
    if overwrite:
        argv.append("--overwrite")
    return parse_args(argv)


def run_audit(
    tmp_path: Path,
    timeout_by_year: dict[int, list[float]],
    *,
    stress_total_R: float = 100.0,
    classification: str = "CONTROLLED_EXPANSION_RETAINED_FOR_TIMEOUT_REVIEW",
    candidate_overrides: dict[str, object] | None = None,
    overwrite: bool = True,
) -> tuple[dict[str, Path], dict[str, str], list[dict[str, str]]]:
    controlled_dir = write_controlled_package(tmp_path, classification=classification, candidate_overrides=candidate_overrides)
    replay_dir = write_replay_package(
        tmp_path,
        build_stress_rows(timeout_by_year, stress_total_R=stress_total_R),
        candidate_overrides=candidate_overrides,
    )
    outputs = build_timeout_fragility_audit(build_args(tmp_path, controlled_dir, replay_dir, overwrite=overwrite))
    return outputs, read_csv(outputs["summary"])[0], read_csv(outputs["warnings"])


def test_mild_negative_timeout_can_pass(tmp_path: Path) -> None:
    outputs, summary, warnings = run_audit(tmp_path, {2024: [-1.0]})

    assert summary["final_timeout_audit_classification"] == PASSED_LABEL
    assert summary["can_return_to_baseline_and_cost_sensitivity_review"] == "True"
    assert any(row["warning_code"] == "timeout_negative_but_small" for row in warnings)


def test_different_candidate_metadata_flows_to_summary_and_report(tmp_path: Path) -> None:
    outputs, summary, _warnings = run_audit(
        tmp_path,
        {2023: [-0.05, 0.02], 2024: [0.03, -0.01]},
        candidate_overrides=candidate_b_fields(),
    )
    report = outputs["report"].read_text(encoding="utf-8")

    assert summary["symbol"] == "EURUSD"
    assert summary["direction"] == "long"
    assert summary["horizon"] == "h5"
    assert summary["target_family"] == "preferred_2atr_1atr_hit_first"
    assert summary["regime_value"] == "London"
    assert "momentum_score" in summary["feature_condition"]
    assert "EURUSD" in report
    assert "London" in report
    assert "momentum_score" in report
    assert read_csv(outputs["yearly"])
    assert read_csv(outputs["monthly"])
    assert read_csv(outputs["entry_hour"])
    assert read_csv(outputs["subperiods"])
    assert read_csv(outputs["sequences"])
    assert read_csv(outputs["non_timeout_comparison"])


def test_current_like_timeout_review_is_not_failed(tmp_path: Path) -> None:
    _outputs, summary, _warnings = run_audit(
        tmp_path,
        {
            2022: [-1.0],
            2023: [2.0],
            2024: [-4.0],
            2025: [2.0],
        },
    )

    assert summary["final_timeout_audit_classification"] != FAILED_LABEL
    assert int(summary["timeout_negative_year_count"]) == 2
    assert float(summary["timeout_worst_year_loss_ratio"]) == pytest.approx(0.04)


def test_severe_timeout_loss_is_retained_for_review(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_audit(tmp_path, {2024: [-6.0]})

    assert summary["final_timeout_audit_classification"] == RETAINED_LABEL
    assert any(row["warning_code"] == "timeout_loss_review" for row in warnings)


def test_catastrophic_timeout_loss_fails(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_audit(tmp_path, {2024: [-12.0]})

    assert summary["final_timeout_audit_classification"] == FAILED_LABEL
    assert any(row["warning_code"] == "timeout_total_loss_blocking" for row in warnings)


def test_four_negative_timeout_years_fail(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_audit(
        tmp_path,
        {
            2022: [-0.5],
            2023: [-0.5],
            2024: [-0.5],
            2025: [-0.5],
        },
    )

    assert summary["final_timeout_audit_classification"] == FAILED_LABEL
    assert any(row["warning_code"] == "timeout_negative_years_blocking" for row in warnings)


def test_inherited_rejected_controlled_expansion_fails(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_audit(
        tmp_path,
        {2024: [1.0]},
        classification="CONTROLLED_EXPANSION_REJECTED",
    )

    assert summary["final_timeout_audit_classification"] == FAILED_LABEL
    assert any(row["warning_code"] == "input_controlled_expansion_classification" for row in warnings)


def test_missing_stress_trade_log_errors(tmp_path: Path) -> None:
    controlled_dir = write_controlled_package(tmp_path)
    replay_dir = write_replay_package(tmp_path, build_stress_rows({2024: [-1.0]}))
    (replay_dir / "rule_based_trade_log_stress.csv").unlink()

    with pytest.raises(FileNotFoundError, match="rule_based_trade_log_stress"):
        build_timeout_fragility_audit(build_args(tmp_path, controlled_dir, replay_dir))


def test_missing_controlled_summary_errors(tmp_path: Path) -> None:
    controlled_dir = write_controlled_package(tmp_path)
    replay_dir = write_replay_package(tmp_path, build_stress_rows({2024: [-1.0]}))
    (controlled_dir / "controlled_rule_expansion_summary.csv").unlink()

    with pytest.raises(FileNotFoundError, match="controlled_rule_expansion_summary"):
        build_timeout_fragility_audit(build_args(tmp_path, controlled_dir, replay_dir))


def test_overwrite_protection(tmp_path: Path) -> None:
    controlled_dir = write_controlled_package(tmp_path)
    replay_dir = write_replay_package(tmp_path, build_stress_rows({2024: [-1.0]}))
    build_timeout_fragility_audit(build_args(tmp_path, controlled_dir, replay_dir, overwrite=True))

    with pytest.raises(FileExistsError, match="--overwrite"):
        build_timeout_fragility_audit(build_args(tmp_path, controlled_dir, replay_dir, overwrite=False))
