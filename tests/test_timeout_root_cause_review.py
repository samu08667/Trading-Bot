import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from scripts.build_timeout_root_cause_review import (
    CLEARED_LABEL,
    FAILED_LABEL,
    RETAINED_LABEL,
    build_timeout_root_cause_review,
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


def trade_row(entry: datetime, exit_reason: str, value: float, cost: float = 0.05) -> dict[str, object]:
    return {
        "symbol": "GBPUSD",
        "direction": "short",
        "target_family": "preferred_1_5atr_1atr_hit_first",
        "horizon": "10",
        "regime_column": "session",
        "regime_value": "Off_hours",
        "entry_time": entry.strftime("%Y-%m-%d %H:%M:%S"),
        "exit_time": (entry + timedelta(minutes=150)).strftime("%Y-%m-%d %H:%M:%S"),
        "entry_price": "100.0",
        "exit_price": "99.0",
        "exit_reason": exit_reason,
        "bars_held": "10",
        "tp_atr": "1.5",
        "sl_atr": "1.0",
        "R": value,
        "cost_R": cost,
        "net_R": value,
    }


def build_rows(timeout_values: list[float], *, costs: list[float] | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = datetime(2024, 1, 1, 22, 0)
    for index in range(20):
        rows.append(trade_row(start + timedelta(days=index), "TP", 5.0, 0.05))
    for index, value in enumerate(timeout_values):
        entry = datetime(2024, 2 + (index // 10), (index % 10) + 1, 23 if index % 2 else 22, 0)
        cost = costs[index] if costs is not None else 0.05
        rows.append(trade_row(entry, "TIMEOUT", value, cost))
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


def write_timeout_audit_package(
    tmp_path: Path,
    *,
    classification: str = "TIMEOUT_AUDIT_RETAINED_FOR_REVIEW",
    stress_cumulative: float = 100.0,
    middle_cumulative: float = 0.0,
    sequence_start: int = 1,
    sequence_end: int = 2,
    sequence_drawdown: float = 0.1,
    candidate_overrides: dict[str, object] | None = None,
) -> Path:
    audit_dir = tmp_path / "audit" / "unit_root_cause"
    summary = {
        "run_id": "unit_root_cause",
        "final_timeout_audit_classification": classification,
        "warnings_count": "0",
        "blocking_warnings_count": "0",
        "stress_total_trades": "40",
        "stress_cumulative_R": stress_cumulative,
        "timeout_trades": "20",
        "timeout_cumulative_R": "-0.1",
        "largest_timeout_drawdown_sequence_R": sequence_drawdown,
        **candidate_fields(**(candidate_overrides or {})),
    }
    write_csv(audit_dir / "timeout_fragility_audit_summary.csv", [summary])
    (audit_dir / "timeout_fragility_audit_report.md").write_text("audit\n", encoding="utf-8")
    write_csv(
        audit_dir / "timeout_fragility_audit_warnings.csv",
        [],
        ["warning_code", "severity", "blocking", "message", "related_metric", "metric_value", "threshold"],
    )
    write_csv(
        audit_dir / "timeout_fragility_audit_yearly.csv",
        [{"period_type": "year", "period": "2024", "timeout_count": "20", "timeout_cumulative_R": "-0.1"}],
    )
    write_csv(
        audit_dir / "timeout_fragility_audit_monthly.csv",
        [{"period_type": "month", "period": "2024-02", "timeout_count": "10", "timeout_cumulative_R": "-0.1"}],
    )
    write_csv(
        audit_dir / "timeout_fragility_audit_entry_hour.csv",
        [
            {"entry_hour": "22", "timeout_count": "10", "timeout_cumulative_R": "-0.1"},
            {"entry_hour": "23", "timeout_count": "10", "timeout_cumulative_R": "0.0"},
        ],
    )
    write_csv(
        audit_dir / "timeout_fragility_audit_subperiods.csv",
        [
            {"subperiod": "early", "timeout_count": "6", "timeout_cumulative_R": "0.0"},
            {"subperiod": "middle", "timeout_count": "8", "timeout_cumulative_R": middle_cumulative},
            {"subperiod": "recent", "timeout_count": "6", "timeout_cumulative_R": "0.0"},
        ],
    )
    write_csv(
        audit_dir / "timeout_fragility_audit_sequences.csv",
        [
            {
                "diagnostic_type": "largest_timeout_drawdown_sequence",
                "sequence_id": "1",
                "start_trade_index": str(sequence_start),
                "end_trade_index": str(sequence_end),
                "timeout_count": str(max(0, sequence_end - sequence_start + 1)),
                "cumulative_R": "-0.1",
                "max_drawdown_R": sequence_drawdown,
            }
        ],
    )
    write_csv(
        audit_dir / "timeout_fragility_audit_non_timeout_comparison.csv",
        [{"scope": "overall", "period_type": "overall", "period": "all", "timeout_count": "20"}],
    )
    return audit_dir


def write_replay_package(
    tmp_path: Path,
    stress_rows: list[dict[str, object]],
    *,
    candidate_overrides: dict[str, object] | None = None,
) -> Path:
    replay_dir = tmp_path / "replay" / "unit_root_cause"
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
    audit_dir: Path,
    replay_dir: Path,
    *,
    db_path: Path | None = None,
    overwrite: bool = True,
) -> argparse.Namespace:
    argv = [
        "--timeout-audit-dir",
        str(audit_dir),
        "--rule-replay-dir",
        str(replay_dir),
        "--output-root",
        str(tmp_path / "root_cause_outputs"),
        "--run-id",
        "unit_root_cause",
    ]
    if db_path is not None:
        argv.extend(["--db-path", str(db_path)])
    if overwrite:
        argv.append("--overwrite")
    return parse_args(argv)


def run_review(
    tmp_path: Path,
    timeout_values: list[float],
    *,
    costs: list[float] | None = None,
    classification: str = "TIMEOUT_AUDIT_RETAINED_FOR_REVIEW",
    sequence_start: int = 1,
    sequence_end: int = 2,
    sequence_drawdown: float = 0.1,
    middle_cumulative: float = 0.0,
    db_path: Path | None = None,
    candidate_overrides: dict[str, object] | None = None,
    overwrite: bool = True,
) -> tuple[dict[str, Path], dict[str, str], list[dict[str, str]]]:
    audit_dir = write_timeout_audit_package(
        tmp_path,
        classification=classification,
        sequence_start=sequence_start,
        sequence_end=sequence_end,
        sequence_drawdown=sequence_drawdown,
        middle_cumulative=middle_cumulative,
        candidate_overrides=candidate_overrides,
    )
    replay_dir = write_replay_package(tmp_path, build_rows(timeout_values, costs=costs), candidate_overrides=candidate_overrides)
    outputs = build_timeout_root_cause_review(build_args(tmp_path, audit_dir, replay_dir, db_path=db_path, overwrite=overwrite))
    return outputs, read_csv(outputs["summary"])[0], read_csv(outputs["warnings"])


def diffuse_small_timeout_values() -> list[float]:
    return [-0.05] * 20 + [0.045] * 20


def test_cleared_case_small_bounded_no_cost_difference(tmp_path: Path) -> None:
    outputs, summary, warnings = run_review(tmp_path, diffuse_small_timeout_values())

    assert summary["final_timeout_root_cause_classification"] == CLEARED_LABEL
    assert summary["can_return_to_baseline_and_cost_sensitivity_review"] == "True"
    assert not any(row["blocking"] == "True" for row in warnings)
    assert read_csv(outputs["largest_sequence_trades"])
    assert read_csv(outputs["negative_timeout_trades"])
    assert read_csv(outputs["positive_vs_negative"])
    assert read_csv(outputs["year_month_breakdown"])
    assert read_csv(outputs["entry_hour_breakdown"])
    assert read_csv(outputs["cost_profile"])
    assert read_csv(outputs["next_review_plan"])


def test_retained_case_large_sequence_drawdown(tmp_path: Path) -> None:
    values = [-0.6] * 10 + [0.5] * 10
    _outputs, summary, warnings = run_review(
        tmp_path,
        values,
        sequence_start=1,
        sequence_end=10,
        sequence_drawdown=6.0,
    )

    assert summary["final_timeout_root_cause_classification"] == RETAINED_LABEL
    assert any(row["warning_code"] == "largest_sequence_review" for row in warnings)


def test_failed_case_severe_sequence_loss(tmp_path: Path) -> None:
    values = [-1.2] * 10 + [1.1] * 10
    _outputs, summary, warnings = run_review(
        tmp_path,
        values,
        sequence_start=1,
        sequence_end=10,
        sequence_drawdown=12.0,
    )

    assert summary["final_timeout_root_cause_classification"] == FAILED_LABEL
    assert any(row["warning_code"] == "largest_sequence_blocking" for row in warnings)


def test_negative_timeout_costs_materially_higher_are_retained(tmp_path: Path) -> None:
    values = diffuse_small_timeout_values()
    costs = [0.20 if value < 0 else 0.01 for value in values]
    _outputs, summary, warnings = run_review(tmp_path, values, costs=costs)

    assert summary["final_timeout_root_cause_classification"] == RETAINED_LABEL
    assert summary["negative_timeout_cost_materially_higher"] == "True"
    assert any(row["warning_code"] == "negative_timeout_cost_review" for row in warnings)


def test_input_timeout_audit_failed_blocks(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_review(
        tmp_path,
        diffuse_small_timeout_values(),
        classification="TIMEOUT_AUDIT_FAILED",
    )

    assert summary["final_timeout_root_cause_classification"] == FAILED_LABEL
    assert any(row["warning_code"] == "input_timeout_audit_failed" for row in warnings)


def test_missing_input_file_errors(tmp_path: Path) -> None:
    audit_dir = write_timeout_audit_package(tmp_path)
    replay_dir = write_replay_package(tmp_path, build_rows(diffuse_small_timeout_values()))
    (audit_dir / "timeout_fragility_audit_summary.csv").unlink()

    with pytest.raises(FileNotFoundError, match="timeout_fragility_audit_summary"):
        build_timeout_root_cause_review(build_args(tmp_path, audit_dir, replay_dir))


def test_db_enrichment_unavailable_is_non_blocking_and_writes_report(tmp_path: Path) -> None:
    db_path = tmp_path / "bad.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE ml_dataset (symbol TEXT)")

    outputs, summary, warnings = run_review(tmp_path, diffuse_small_timeout_values(), db_path=db_path)

    assert outputs["report"].exists()
    assert summary["db_enrichment_available"] == "False"
    assert any(row["warning_code"] == "db_enrichment_unavailable" and row["blocking"] == "False" for row in warnings)


def test_db_enrichment_uses_candidate_feature_names_from_input_metadata(tmp_path: Path) -> None:
    candidate_b = candidate_b_fields()
    timeout_values = diffuse_small_timeout_values()
    stress_rows = build_rows(timeout_values)
    entry_times = [str(row["entry_time"]) for row in stress_rows if str(row["exit_reason"]).upper() == "TIMEOUT"]
    db_path = tmp_path / "features.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE ml_dataset (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                spread REAL,
                atr_20 REAL,
                session TEXT,
                momentum_score REAL,
                liquidity_rank REAL
            )
            """
        )
        for index, entry_time in enumerate(entry_times):
            connection.execute(
                "INSERT INTO ml_dataset VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    candidate_b["symbol"],
                    candidate_b["timeframe"],
                    entry_time,
                    1.2,
                    0.8,
                    candidate_b["regime_value"],
                    0.5 + index,
                    10.0 - index,
                ),
            )

    audit_dir = write_timeout_audit_package(tmp_path, candidate_overrides=candidate_b)
    replay_dir = write_replay_package(tmp_path, stress_rows, candidate_overrides=candidate_b)
    outputs = build_timeout_root_cause_review(build_args(tmp_path, audit_dir, replay_dir, db_path=db_path))
    summary = read_csv(outputs["summary"])[0]
    context = read_csv(outputs["feature_context"])
    report = outputs["report"].read_text(encoding="utf-8")

    assert summary["symbol"] == "EURUSD"
    assert summary["direction"] == "long"
    assert summary["horizon"] == "h5"
    assert summary["regime_value"] == "London"
    assert summary["db_enrichment_available"] == "True"
    assert {row["context_field"] for row in context} >= {"momentum_score", "liquidity_rank"}
    assert "EURUSD" in report
    assert "momentum_score" in report


def test_overwrite_protection(tmp_path: Path) -> None:
    audit_dir = write_timeout_audit_package(tmp_path)
    replay_dir = write_replay_package(tmp_path, build_rows(diffuse_small_timeout_values()))
    build_timeout_root_cause_review(build_args(tmp_path, audit_dir, replay_dir, overwrite=True))

    with pytest.raises(FileExistsError, match="--overwrite"):
        build_timeout_root_cause_review(build_args(tmp_path, audit_dir, replay_dir, overwrite=False))
