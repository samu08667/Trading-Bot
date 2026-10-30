import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from scripts.build_timeout_sequence_drilldown_review import (
    CLEARED_LABEL,
    FAILED_LABEL,
    RETAINED_LABEL,
    build_timeout_sequence_drilldown_review,
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


def build_rows(
    timeout_values: list[float],
    *,
    costs: list[float] | None = None,
    years: list[int] | None = None,
    hours: list[int] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = datetime(2021, 1, 1, 22, 0)
    for index in range(20):
        rows.append(trade_row(start + timedelta(days=index), "TP", 5.0, 0.05))
    for index, value in enumerate(timeout_values):
        year = years[index] if years is not None else 2024
        hour = hours[index] if hours is not None else (22 if index % 2 == 0 else 23)
        month = 1 + (index % 12)
        day = 1 + (index % 20)
        cost = costs[index] if costs is not None else 0.05
        rows.append(trade_row(datetime(year, month, day, hour, 0), "TIMEOUT", value, cost))
    return sorted(rows, key=lambda row: str(row["entry_time"]))


def write_replay_package(
    tmp_path: Path,
    stress_rows: list[dict[str, object]],
    *,
    candidate_overrides: dict[str, object] | None = None,
) -> Path:
    replay_dir = tmp_path / "replay" / "unit_sequence"
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
    return replay_dir


def timeout_trade_outputs(stress_rows: list[dict[str, object]], start: int, end: int) -> list[dict[str, object]]:
    timeout_index = 0
    output: list[dict[str, object]] = []
    for stress_index, row in enumerate(sorted(stress_rows, key=lambda item: str(item["entry_time"])), start=1):
        if str(row["exit_reason"]).upper() != "TIMEOUT":
            continue
        timeout_index += 1
        if start <= timeout_index <= end:
            entry = datetime.strptime(str(row["entry_time"]), "%Y-%m-%d %H:%M:%S")
            output.append(
                {
                    "stress_trade_index": stress_index,
                    "timeout_trade_index": timeout_index,
                    "entry_time": row["entry_time"],
                    "exit_time": row["exit_time"],
                    "symbol": row["symbol"],
                    "direction": row["direction"],
                    "exit_reason": row["exit_reason"],
                    "bars_held": row["bars_held"],
                    "R": row["R"],
                    "cost_R": row["cost_R"],
                    "net_R": row["net_R"],
                    "gross_R_proxy": float(row["R"]) + float(row["cost_R"]),
                    "entry_hour": entry.hour,
                    "year": entry.year,
                    "month": f"{entry.year:04d}-{entry.month:02d}",
                }
            )
    return output


def write_root_cause_package(
    tmp_path: Path,
    stress_rows: list[dict[str, object]],
    *,
    sequence_start: int,
    sequence_end: int,
    classification: str = "TIMEOUT_ROOT_CAUSE_RETAINED_FOR_REVIEW",
    candidate_overrides: dict[str, object] | None = None,
) -> Path:
    root_dir = tmp_path / "root_cause" / "unit_sequence"
    sequence_rows = timeout_trade_outputs(stress_rows, sequence_start, sequence_end)
    timeout_values = [float(row["R"]) for row in stress_rows if str(row["exit_reason"]).upper() == "TIMEOUT"]
    sequence_values = [float(row["R"]) for row in sequence_rows]
    summary = {
        "run_id": "unit_sequence",
        "final_timeout_root_cause_classification": classification,
        "warnings_count": "0",
        "blocking_warnings_count": "0",
        "stress_cumulative_R": "100.0",
        "timeout_count": len(timeout_values),
        "timeout_cumulative_R": sum(timeout_values),
        "sequence_timeout_count": len(sequence_values),
        "sequence_cumulative_R": sum(sequence_values),
        **candidate_fields(**(candidate_overrides or {})),
    }
    write_csv(root_dir / "timeout_root_cause_summary.csv", [summary])
    write_csv(root_dir / "timeout_root_cause_largest_sequence_trades.csv", sequence_rows)
    write_csv(
        root_dir / "timeout_root_cause_negative_timeout_trades.csv",
        [row for row in sequence_rows if float(row["R"]) < 0],
    )
    write_csv(
        root_dir / "timeout_root_cause_positive_vs_negative_timeout.csv",
        [{"bucket": "all_timeout", "count": len(timeout_values), "cumulative_R": sum(timeout_values)}],
    )
    write_csv(
        root_dir / "timeout_root_cause_warnings.csv",
        [],
        ["warning_code", "severity", "blocking", "message", "related_metric", "metric_value", "threshold"],
    )
    return root_dir


def write_audit_package(
    tmp_path: Path,
    sequence_start: int,
    sequence_end: int,
    *,
    candidate_overrides: dict[str, object] | None = None,
) -> Path:
    audit_dir = tmp_path / "audit" / "unit_sequence"
    write_csv(
        audit_dir / "timeout_fragility_audit_sequences.csv",
        [
            {
                "diagnostic_type": "largest_timeout_drawdown_sequence",
                "start_trade_index": sequence_start,
                "end_trade_index": sequence_end,
                "max_drawdown_R": "1.0",
            }
        ],
    )
    write_csv(audit_dir / "timeout_fragility_audit_monthly.csv", [{"period": "2024-01", "timeout_cumulative_R": "-1.0"}])
    write_csv(audit_dir / "timeout_fragility_audit_yearly.csv", [{"period": "2024", "timeout_cumulative_R": "-1.0"}])
    write_csv(audit_dir / "timeout_fragility_audit_entry_hour.csv", [{"entry_hour": "22", "timeout_cumulative_R": "-1.0"}])
    return audit_dir


def build_args(
    tmp_path: Path,
    root_dir: Path,
    audit_dir: Path,
    replay_dir: Path,
    *,
    db_path: Path | None = None,
    overwrite: bool = True,
) -> argparse.Namespace:
    argv = [
        "--timeout-root-cause-dir",
        str(root_dir),
        "--timeout-audit-dir",
        str(audit_dir),
        "--rule-replay-dir",
        str(replay_dir),
        "--output-root",
        str(tmp_path / "sequence_outputs"),
        "--run-id",
        "unit_sequence",
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
    sequence_start: int = 1,
    sequence_end: int = 4,
    costs: list[float] | None = None,
    years: list[int] | None = None,
    hours: list[int] | None = None,
    db_path: Path | None = None,
    root_classification: str = "TIMEOUT_ROOT_CAUSE_RETAINED_FOR_REVIEW",
    candidate_overrides: dict[str, object] | None = None,
    overwrite: bool = True,
) -> tuple[dict[str, Path], dict[str, str], list[dict[str, str]]]:
    stress_rows = build_rows(timeout_values, costs=costs, years=years, hours=hours)
    replay_dir = write_replay_package(tmp_path, stress_rows, candidate_overrides=candidate_overrides)
    root_dir = write_root_cause_package(
        tmp_path,
        stress_rows,
        sequence_start=sequence_start,
        sequence_end=sequence_end,
        classification=root_classification,
        candidate_overrides=candidate_overrides,
    )
    audit_dir = write_audit_package(tmp_path, sequence_start, sequence_end, candidate_overrides=candidate_overrides)
    outputs = build_timeout_sequence_drilldown_review(
        build_args(tmp_path, root_dir, audit_dir, replay_dir, db_path=db_path, overwrite=overwrite)
    )
    return outputs, read_csv(outputs["summary"])[0], read_csv(outputs["warnings"])


def test_cleared_bounded_sequence(tmp_path: Path) -> None:
    values = [-0.05, 0.04, -0.05, 0.04] + [-0.05, 0.05] * 8
    outputs, summary, warnings = run_review(
        tmp_path,
        values,
        sequence_start=1,
        sequence_end=4,
        costs=[0.001] * len(values),
    )

    assert summary["final_timeout_sequence_classification"] == CLEARED_LABEL
    assert summary["can_return_to_baseline_and_cost_sensitivity_review"] == "True"
    assert not any(row["blocking"] == "True" for row in warnings)
    assert read_csv(outputs["trades"])
    assert read_csv(outputs["calendar"])
    assert read_csv(outputs["entry_hour"])
    assert read_csv(outputs["cost_profile"])
    assert read_csv(outputs["next_action"])


def test_retained_broad_sequence(tmp_path: Path) -> None:
    values = [-0.4] * 16 + [0.1] * 4
    years = [2023, 2024, 2025, 2026] * 5
    _outputs, summary, warnings = run_review(
        tmp_path,
        values,
        sequence_start=1,
        sequence_end=16,
        years=years,
    )

    assert summary["final_timeout_sequence_classification"] == RETAINED_LABEL
    assert any(row["warning_code"] == "sequence_calendar_broadness_review" for row in warnings)


def test_failed_severe_sequence(tmp_path: Path) -> None:
    values = [-1.0] * 16 + [0.1] * 4
    _outputs, summary, warnings = run_review(tmp_path, values, sequence_start=1, sequence_end=16)

    assert summary["final_timeout_sequence_classification"] == FAILED_LABEL
    assert any(row["warning_code"] == "sequence_blocking_failure" for row in warnings)


def test_cost_driven_sequence_warning(tmp_path: Path) -> None:
    values = [-0.1, -0.1, 0.05, 0.05] + [-0.1, 0.1] * 8
    costs = [0.3, 0.3, 0.3, 0.3] + [0.05] * 16
    _outputs, summary, warnings = run_review(
        tmp_path,
        values,
        sequence_start=1,
        sequence_end=4,
        costs=costs,
    )

    assert summary["final_timeout_sequence_classification"] == RETAINED_LABEL
    assert summary["sequence_cost_primary_driver"] == "True"
    assert any(row["warning_code"] == "sequence_cost_driver_review" for row in warnings)


def test_entry_hour_concentrated_sequence_warning(tmp_path: Path) -> None:
    values = [-0.2, -0.1, 0.05, 0.05] + [-0.1, 0.1] * 8
    hours = [23] * 4 + [22, 23] * 8
    _outputs, summary, warnings = run_review(
        tmp_path,
        values,
        sequence_start=1,
        sequence_end=4,
        hours=hours,
    )

    assert summary["final_timeout_sequence_classification"] == RETAINED_LABEL
    assert any(row["warning_code"] == "sequence_entry_hour_review" for row in warnings)


def test_db_enrichment_unavailable_is_non_blocking(tmp_path: Path) -> None:
    db_path = tmp_path / "bad.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE ml_dataset (symbol TEXT)")

    _outputs, summary, warnings = run_review(
        tmp_path,
        [-0.05, 0.04, -0.05, 0.04] + [-0.08, 0.08] * 8,
        db_path=db_path,
    )

    assert summary["db_enrichment_available"] == "False"
    assert any(row["warning_code"] == "db_enrichment_unavailable" and row["blocking"] == "False" for row in warnings)


def test_db_enrichment_uses_candidate_feature_names_from_input_metadata(tmp_path: Path) -> None:
    candidate_b = candidate_b_fields()
    values = [-0.05, 0.04, -0.05, 0.04] + [-0.05, 0.05] * 8
    stress_rows = build_rows(values)
    sequence_entries = [
        str(row["entry_time"])
        for row in timeout_trade_outputs(stress_rows, 1, 4)
    ]
    db_path = tmp_path / "sequence_features.db"
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
        for index, entry_time in enumerate(sequence_entries):
            connection.execute(
                "INSERT INTO ml_dataset VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    candidate_b["symbol"],
                    candidate_b["timeframe"],
                    entry_time,
                    1.1,
                    0.7,
                    candidate_b["regime_value"],
                    0.2 + index,
                    5.0 - index,
                ),
            )

    outputs, summary, _warnings = run_review(
        tmp_path,
        values,
        db_path=db_path,
        candidate_overrides=candidate_b,
    )
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


def test_missing_required_input_file_errors(tmp_path: Path) -> None:
    values = [-0.05, 0.04, -0.05, 0.04] + [-0.08, 0.08] * 8
    stress_rows = build_rows(values)
    replay_dir = write_replay_package(tmp_path, stress_rows)
    root_dir = write_root_cause_package(tmp_path, stress_rows, sequence_start=1, sequence_end=4)
    audit_dir = write_audit_package(tmp_path, 1, 4)
    (root_dir / "timeout_root_cause_summary.csv").unlink()

    with pytest.raises(FileNotFoundError, match="timeout_root_cause_summary"):
        build_timeout_sequence_drilldown_review(build_args(tmp_path, root_dir, audit_dir, replay_dir))


def test_overwrite_protection(tmp_path: Path) -> None:
    values = [-0.05, 0.04, -0.05, 0.04] + [-0.08, 0.08] * 8
    stress_rows = build_rows(values)
    replay_dir = write_replay_package(tmp_path, stress_rows)
    root_dir = write_root_cause_package(tmp_path, stress_rows, sequence_start=1, sequence_end=4)
    audit_dir = write_audit_package(tmp_path, 1, 4)
    build_timeout_sequence_drilldown_review(build_args(tmp_path, root_dir, audit_dir, replay_dir, overwrite=True))

    with pytest.raises(FileExistsError, match="--overwrite"):
        build_timeout_sequence_drilldown_review(build_args(tmp_path, root_dir, audit_dir, replay_dir, overwrite=False))
