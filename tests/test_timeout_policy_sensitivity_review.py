import argparse
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from scripts.build_timeout_policy_sensitivity_review import (
    CLEARED_LABEL,
    REJECTED_LABEL,
    RETAINED_LABEL,
    build_timeout_policy_sensitivity_review,
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


def candidate_fields() -> dict[str, object]:
    return {
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
        "atr_column": "atr_20",
        "same_bar_policy": "stop_first",
        "candidate_scope": "exact_feature_combination",
        "stress_spread_policy": "max_row_or_fallback",
    }


def write_cost_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "default": {
                    "slippage_bps_round_trip": 0.0,
                    "commission_bps_round_trip": 0.0,
                },
                "symbols": {
                    "GBPUSD": {
                        "point_size": 0.00001,
                        "fallback_spread_points": 2.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def trade_row(index: int, entry_time: datetime, exit_reason: str, value: float, bars_held: int) -> dict[str, object]:
    return {
        "symbol": "GBPUSD",
        "direction": "short",
        "target_family": "preferred_1_5atr_1atr_hit_first",
        "horizon": "10",
        "regime_column": "session",
        "regime_value": "Off_hours",
        "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
        "exit_time": (entry_time + timedelta(minutes=15 * bars_held)).strftime("%Y-%m-%d %H:%M:%S"),
        "entry_price": "100.0",
        "exit_price": "100.0",
        "exit_reason": exit_reason,
        "bars_held": str(bars_held),
        "tp_atr": "1.5",
        "sl_atr": "1.0",
        "R": value,
        "cost_R": "0.0002",
        "net_R": value,
    }


def build_replay_trades(timeout_outcomes: list[str]) -> tuple[list[dict[str, object]], list[int]]:
    start = datetime(2024, 1, 1)
    trade_plan = [("TP", 1.5, 3), ("TP", 1.5, 3), ("TP", 1.5, 3), ("TP", 1.5, 3), ("SL", -1.0, 4), ("SL", -1.0, 4)]
    trade_plan.extend(("TIMEOUT", -0.03, 10) for _ in timeout_outcomes)
    rows: list[dict[str, object]] = []
    timeout_entry_indexes: list[int] = []
    for index, (reason, value, bars_held) in enumerate(trade_plan):
        entry_index = index * 100
        entry_time = start + timedelta(minutes=15 * entry_index)
        if reason == "TIMEOUT":
            timeout_entry_indexes.append(entry_index)
        rows.append(trade_row(index, entry_time, reason, value, bars_held))
    return rows, timeout_entry_indexes


def write_db(path: Path, timeout_entry_indexes: list[int], timeout_outcomes: list[str], *, truncate: bool = False) -> None:
    start = datetime(2024, 1, 1)
    last_index = max(timeout_entry_indexes) + (15 if truncate else 90)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE ml_dataset (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                atr_20 REAL,
                spread REAL,
                session TEXT
            )
            """
        )
        rows = []
        for index in range(last_index + 1):
            timestamp = start + timedelta(minutes=15 * index)
            rows.append(
                [
                    "GBPUSD",
                    "M15",
                    timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    100.0,
                    100.2,
                    99.8,
                    100.0,
                    1.0,
                    2.0,
                    "Off_hours",
                ]
            )
        for entry_index, outcome in zip(timeout_entry_indexes, timeout_outcomes):
            if truncate:
                continue
            hit_index = entry_index + 12
            if outcome == "tp":
                rows[hit_index][5] = 98.4
            elif outcome == "sl":
                rows[hit_index][4] = 101.2
            elif outcome == "late_tp":
                rows[entry_index + 30][5] = 98.4
        connection.executemany("INSERT INTO ml_dataset VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def write_inputs(
    tmp_path: Path,
    timeout_outcomes: list[str],
    *,
    truncate_db: bool = False,
) -> tuple[dict[str, Path], Path, Path, Path]:
    dirs = {
        "rule_replay": tmp_path / "rule_replay" / "unit_policy",
        "timeout_audit": tmp_path / "timeout_audit" / "unit_policy",
        "timeout_root": tmp_path / "timeout_root" / "unit_policy",
        "timeout_sequence": tmp_path / "timeout_sequence" / "unit_policy",
    }
    stress_rows, timeout_entry_indexes = build_replay_trades(timeout_outcomes)
    base_rows = [{**row, "R": float(row["R"]) + 0.02, "net_R": float(row["net_R"]) + 0.02} for row in stress_rows]
    stress_values = [float(row["R"]) for row in stress_rows]
    summary = {
        **candidate_fields(),
        "final_rule_replay_classification": "RULE_REPLAY_MATCHED_STRESS_VALIDATION",
        "generated_logs_match_stress_validation": "True",
        "stress_mean_R": sum(stress_values) / len(stress_values),
        "stress_profit_factor_R": "6.0",
        "stress_cumulative_R": sum(stress_values),
        "stress_max_drawdown_R": "2.0",
    }
    write_csv(dirs["rule_replay"] / "rule_based_backtest_summary.csv", [summary])
    write_csv(dirs["rule_replay"] / "rule_based_trade_log_stress.csv", stress_rows, TRADE_FIELDNAMES)
    write_csv(dirs["rule_replay"] / "rule_based_trade_log_base.csv", base_rows, TRADE_FIELDNAMES)
    write_csv(dirs["rule_replay"] / "rule_based_warnings.csv", [], ["severity", "check", "blocks_match", "message"])

    audit_summary = {
        **candidate_fields(),
        "final_timeout_audit_classification": "TIMEOUT_AUDIT_RETAINED_FOR_REVIEW",
        "stress_cumulative_R": sum(stress_values),
        "timeout_cumulative_R": "-0.12",
        "timeout_loss_ratio_of_stress_cumulative_R": "0.02",
    }
    write_csv(dirs["timeout_audit"] / "timeout_fragility_audit_summary.csv", [audit_summary])
    write_csv(
        dirs["timeout_root"] / "timeout_root_cause_summary.csv",
        [{**candidate_fields(), "final_timeout_root_cause_classification": "TIMEOUT_ROOT_CAUSE_RETAINED_FOR_REVIEW"}],
    )
    write_csv(
        dirs["timeout_sequence"] / "timeout_sequence_drilldown_summary.csv",
        [{**candidate_fields(), "final_timeout_sequence_classification": "TIMEOUT_SEQUENCE_RETAINED_FOR_REVIEW"}],
    )
    db_path = tmp_path / "policy.db"
    write_db(db_path, timeout_entry_indexes, timeout_outcomes, truncate=truncate_db)
    cost_path = tmp_path / "base_cost.json"
    stress_cost_path = tmp_path / "stress_cost.json"
    write_cost_config(cost_path)
    write_cost_config(stress_cost_path)
    return dirs, db_path, cost_path, stress_cost_path


def build_args(
    tmp_path: Path,
    dirs: dict[str, Path],
    db_path: Path,
    cost_path: Path,
    stress_cost_path: Path,
    *,
    overwrite: bool = True,
) -> argparse.Namespace:
    argv = [
        "--rule-replay-dir",
        str(dirs["rule_replay"]),
        "--timeout-audit-dir",
        str(dirs["timeout_audit"]),
        "--timeout-root-cause-dir",
        str(dirs["timeout_root"]),
        "--timeout-sequence-dir",
        str(dirs["timeout_sequence"]),
        "--db-path",
        str(db_path),
        "--cost-config",
        str(cost_path),
        "--stress-cost-config",
        str(stress_cost_path),
        "--stress-spread-policy",
        "max_row_or_fallback",
        "--output-root",
        str(tmp_path / "policy_outputs"),
        "--run-id",
        "unit_policy",
    ]
    if overwrite:
        argv.append("--overwrite")
    return parse_args(argv)


def run_review(
    tmp_path: Path,
    timeout_outcomes: list[str],
    *,
    truncate_db: bool = False,
    overwrite: bool = True,
) -> tuple[dict[str, Path], dict[str, str], list[dict[str, str]]]:
    dirs, db_path, cost_path, stress_cost_path = write_inputs(tmp_path, timeout_outcomes, truncate_db=truncate_db)
    outputs = build_timeout_policy_sensitivity_review(
        build_args(tmp_path, dirs, db_path, cost_path, stress_cost_path, overwrite=overwrite)
    )
    return outputs, read_csv(outputs["summary"])[0], read_csv(outputs["warnings"])


def test_current_strong_extended_mixed_not_dangerous(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_review(tmp_path, ["tp", "sl", "late_tp", "none"])

    assert summary["final_timeout_policy_sensitivity_classification"] in {CLEARED_LABEL, RETAINED_LABEL}
    assert summary["stress_cumulative_R"]
    assert any(row["warning_code"] == "h10_timeout_caveat_unresolved" for row in warnings)


def test_timeout_excluded_bias_warning_exists(tmp_path: Path) -> None:
    _outputs, _summary, warnings = run_review(tmp_path, ["tp", "tp", "late_tp", "none"])

    assert any(row["warning_code"] == "timeout_excluded_bias_warning" for row in warnings)


def test_extended_horizon_mostly_sl_rejects(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_review(tmp_path, ["sl", "sl", "sl", "sl"])

    assert summary["final_timeout_policy_sensitivity_classification"] == REJECTED_LABEL
    assert any(row["warning_code"] == "extended_horizon_sl_dominance_warning" for row in warnings)


def test_extended_horizon_mostly_tp_can_clear_with_diagnostic_warning(tmp_path: Path) -> None:
    outputs, summary, warnings = run_review(tmp_path, ["tp", "tp", "tp", "late_tp"])
    report = outputs["report"].read_text(encoding="utf-8")

    assert summary["final_timeout_policy_sensitivity_classification"] == CLEARED_LABEL
    assert not any(row["blocking"] == "True" for row in warnings)
    assert "diagnostic_replacement_only_not_validated_rule" in report


def test_missing_db_future_bars_retains_with_non_blocking_warning(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_review(tmp_path, ["tp", "tp", "tp", "tp"], truncate_db=True)

    assert summary["final_timeout_policy_sensitivity_classification"] == RETAINED_LABEL
    assert any(
        row["warning_code"] == "db_future_path_unavailable" and row["blocking"] == "False"
        for row in warnings
    )


def test_missing_required_input_file_errors(tmp_path: Path) -> None:
    dirs, db_path, cost_path, stress_cost_path = write_inputs(tmp_path, ["tp", "tp", "tp", "tp"])
    (dirs["rule_replay"] / "rule_based_trade_log_stress.csv").unlink()

    with pytest.raises(FileNotFoundError, match="rule_based_trade_log_stress"):
        build_timeout_policy_sensitivity_review(build_args(tmp_path, dirs, db_path, cost_path, stress_cost_path))


def test_overwrite_protection(tmp_path: Path) -> None:
    dirs, db_path, cost_path, stress_cost_path = write_inputs(tmp_path, ["tp", "tp", "tp", "tp"])
    build_timeout_policy_sensitivity_review(build_args(tmp_path, dirs, db_path, cost_path, stress_cost_path))

    with pytest.raises(FileExistsError, match="--overwrite"):
        build_timeout_policy_sensitivity_review(
            build_args(tmp_path, dirs, db_path, cost_path, stress_cost_path, overwrite=False)
        )


def test_report_always_includes_forbidden_actions(tmp_path: Path) -> None:
    outputs, _summary, _warnings = run_review(tmp_path, ["tp", "tp", "tp", "tp"])
    report = outputs["report"].read_text(encoding="utf-8")

    for phrase in [
        "live trading",
        "trading signals",
        "broker execution",
        "position sizing",
        "TP/SL optimization",
        "new filters",
        "new feature search",
        "live readiness",
    ]:
        assert phrase in report
