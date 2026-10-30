import argparse
import csv
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.validate_regime_candidate_stress import (
    apply_bar_level_no_overlap,
    collect_replay_events,
    parse_args,
    path_config_for_spec,
    replay_metrics,
    resolve_candidate_spec,
    run_candidate_stress,
    summarize_random_baseline,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def write_cost_config(
    path: Path,
    *,
    slippage_bps: float,
    fallback_spread_points: float = 0.0,
    commission_bps: float = 0.0,
) -> None:
    path.write_text(
        json.dumps(
            {
                "default": {
                    "slippage_bps_round_trip": slippage_bps,
                    "commission_bps_round_trip": commission_bps,
                },
                "symbols": {
                    "GBPUSD": {
                        "point_size": 0.00001,
                        "fallback_spread_points": fallback_spread_points,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def base_argv(tmp_path: Path) -> list[str]:
    return [
        "--symbol",
        "GBPUSD",
        "--direction",
        "short",
        "--timeframe",
        "M15",
        "--horizon",
        "h10",
        "--target-family",
        "preferred_1_5atr_1atr_hit_first",
        "--regime-column",
        "session",
        "--regime-value",
        "Off_hours",
        "--tp-atr",
        "1.5",
        "--sl-atr",
        "1.0",
        "--atr-column",
        "atr_20",
        "--same-bar-policy",
        "stop_first",
        "--db-path",
        str(tmp_path / "unused.db"),
        "--run-id",
        "unit_run",
        "--output-root",
        str(tmp_path / "reports"),
        "--overwrite",
    ]


def synthetic_rows(
    outcomes: list[str],
    *,
    direction: str = "short",
    symbol: str = "GBPUSD",
    eligible_indexes: set[int] | None = None,
    feature_flag_indexes: set[int] | None = None,
    start: datetime | None = None,
) -> list[dict[str, object]]:
    start_time = start or datetime(2024, 1, 1)
    row_count = len(outcomes) + 2
    eligible = eligible_indexes if eligible_indexes is not None else set(range(len(outcomes)))
    feature_flags = feature_flag_indexes if feature_flag_indexes is not None else set(range(len(outcomes)))
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        timestamp = start_time + timedelta(minutes=15 * index)
        rows.append(
            {
                "symbol": symbol,
                "timeframe": "M15",
                "time_server": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "open": 100.0,
                "high": 100.4,
                "low": 99.6,
                "close": 100.0,
                "atr_20": 1.0,
                "session": "Off_hours" if index in eligible else "London",
                "feature_flag": 1 if index in feature_flags else 0,
                "spread": 0,
            }
        )
    for index, outcome in enumerate(outcomes):
        exit_row = rows[index + 1]
        if direction == "short":
            if outcome == "tp":
                exit_row["low"] = 98.4
            elif outcome == "sl":
                exit_row["high"] = 101.1
        else:
            if outcome == "tp":
                exit_row["high"] = 101.6
            elif outcome == "sl":
                exit_row["low"] = 98.9
    return rows


def sparse_rows(outcomes: list[str], *, direction: str = "short") -> list[dict[str, object]]:
    expanded = []
    eligible: set[int] = set()
    for index, outcome in enumerate(outcomes):
        entry_index = index * 2
        while len(expanded) <= entry_index:
            expanded.append("timeout")
        expanded[entry_index] = outcome
        eligible.add(entry_index)
    return synthetic_rows(expanded, direction=direction, eligible_indexes=eligible)


def test_explicit_candidate_cli_parsing(tmp_path: Path) -> None:
    args = parse_args(base_argv(tmp_path) + ["--bar-level-no-overlap", "--random-baseline-iterations", "5"])

    assert args.symbol == "GBPUSD"
    assert args.direction == "short"
    assert args.bar_level_no_overlap is True
    assert args.random_baseline_iterations == 5


def test_broad_regime_mode_remains_available(tmp_path: Path) -> None:
    args = parse_args(base_argv(tmp_path) + ["--horizon", "1"])

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sparse_rows(["tp", "sl"], direction="short")

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]

    assert summary["candidate_scope"] == "broad_regime_only"
    assert summary["rows_matching_symbol_direction_regime"] == "2"


def test_target_family_mapping_uses_target_families(tmp_path: Path) -> None:
    spec = resolve_candidate_spec(parse_args(base_argv(tmp_path)))

    assert spec.target_family == "preferred_1_5atr_1atr_hit_first"
    assert spec.tp_atr == 1.5
    assert spec.sl_atr == 1.0

    mismatched = base_argv(tmp_path)
    mismatched[mismatched.index("1.5")] = "2.0"
    with pytest.raises(ValueError, match="must match"):
        resolve_candidate_spec(parse_args(mismatched))


def test_exact_feature_combination_filters_fewer_or_equal_rows(tmp_path: Path) -> None:
    broad_args = parse_args(base_argv(tmp_path) + ["--horizon", "1", "--run-id", "broad"])
    exact_args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--condition",
            "binary_feature:feature_flag:1",
            "--run-id",
            "exact",
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return synthetic_rows(
            ["tp", "tp", "tp", "tp"],
            direction="short",
            feature_flag_indexes={0, 2},
        )

    broad_outputs = run_candidate_stress(broad_args, row_loader=row_loader)
    exact_outputs = run_candidate_stress(exact_args, row_loader=row_loader)
    broad_summary = read_csv(broad_outputs["candidate_stress_summary"])[0]
    exact_summary = read_csv(exact_outputs["candidate_stress_summary"])[0]
    report = exact_outputs["candidate_stress_report"].read_text(encoding="utf-8")

    assert exact_summary["candidate_scope"] == "exact_feature_combination"
    assert int(exact_summary["rows_matching_feature_condition"]) == 2
    assert int(exact_summary["candidate_entries_before_no_overlap"]) <= int(
        broad_summary["candidate_entries_before_no_overlap"]
    )
    assert "Candidate scope" in report
    assert "Source Row Reconstruction" in report


def test_exact_candidate_unavailable_reports_reason_without_broad_fallback(tmp_path: Path) -> None:
    summary_csv = tmp_path / "candidate_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "candidate_id",
                "target_family",
                "horizon",
                "direction",
                "symbol",
                "regime_column",
                "regime_value",
                "source_files",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "candidate_id": "missing_filters",
                "target_family": "preferred_1_5atr_1atr_hit_first",
                "horizon": "h1",
                "direction": "short",
                "symbol": "GBPUSD",
                "regime_column": "session",
                "regime_value": "Off_hours",
                "source_files": "",
            }
        )
    args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--candidate-summary-csv",
            str(summary_csv),
            "--candidate-id",
            "missing_filters",
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sparse_rows(["tp", "tp"], direction="short")

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]

    assert summary["candidate_scope"] == "exact_feature_combination"
    assert summary["accept_broad_regime_scope"] == "0"
    assert "could not be reconstructed" in summary["exact_candidate_not_available_reason"]
    assert summary["final_research_label"] == "EXACT_CANDIDATE_NOT_AVAILABLE"
    assert summary["rows_matching_symbol_direction_regime"] == "2"
    assert summary["candidate_entries_before_no_overlap"] == "0"
    assert summary["sequential_trades_count"] == "0"
    assert read_csv(outputs["trade_log_base"]) == []


def test_bar_level_no_overlap_skips_same_symbol_overlapping_trades(tmp_path: Path) -> None:
    args = parse_args(base_argv(tmp_path) + ["--bar-level-no-overlap", "--horizon", "1"])
    spec = resolve_candidate_spec(args)
    config = path_config_for_spec(spec, cost_mode="none", return_mode="gross")
    rows = synthetic_rows(["tp", "tp", "tp", "tp"], direction="short")

    events = collect_replay_events(rows, spec, config=config, cost_config={})
    replay = apply_bar_level_no_overlap(events, True)

    assert len(replay.events) == 2
    assert replay.skipped_due_to_overlap == 2


def test_opposite_direction_same_symbol_entries_skip_while_trade_is_open(tmp_path: Path) -> None:
    long_args = parse_args([arg if arg != "short" else "long" for arg in base_argv(tmp_path)] + ["--horizon", "1"])
    short_args = parse_args(base_argv(tmp_path) + ["--horizon", "1"])
    long_spec = resolve_candidate_spec(long_args)
    short_spec = resolve_candidate_spec(short_args)
    long_config = path_config_for_spec(long_spec, cost_mode="none", return_mode="gross")
    short_config = path_config_for_spec(short_spec, cost_mode="none", return_mode="gross")
    rows = synthetic_rows(["tp", "tp"], direction="short")

    events = [
        *collect_replay_events(rows, long_spec, config=long_config, cost_config={}),
        *collect_replay_events(rows, short_spec, config=short_config, cost_config={}),
    ]
    replay = apply_bar_level_no_overlap(events, True)

    assert len(replay.events) < len(events)
    assert replay.skipped_due_to_overlap > 0


def test_trade_log_equity_curve_yearly_and_walk_forward_outputs(tmp_path: Path) -> None:
    args = parse_args(base_argv(tmp_path) + ["--bar-level-no-overlap", "--horizon", "1", "--walk-forward-splits", "2"])

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        rows = sparse_rows(["sl", "sl", "tp", "tp", "tp"], direction="short")
        for index, row in enumerate(rows):
            year = 2023 if index < 5 else 2024
            row["time_server"] = (datetime(year, 1, 1) + timedelta(minutes=15 * index)).strftime("%Y-%m-%d %H:%M:%S")
        return rows

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]
    equity = read_csv(outputs["equity_curve_base"])
    trade_log = read_csv(outputs["trade_log_base"])
    yearly = read_csv(outputs["yearly_validation"])
    walk_forward = read_csv(outputs["walk_forward_validation"])

    assert outputs["trade_log_base"].exists()
    assert outputs["equity_curve_base"].exists()
    assert len(trade_log) == 5
    assert len(equity) == 5
    assert summary["max_drawdown_R"] == "2.0"
    assert summary["max_consecutive_losses"] == "2"
    assert summary["max_consecutive_non_positive_trades"] == "2"
    assert {row["year"] for row in yearly} == {"2023", "2024"}
    assert walk_forward


def test_stress_config_missing_and_broad_random_baseline_write_clear_reasons(tmp_path: Path) -> None:
    args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--stress-cost-config",
            str(tmp_path / "missing_stress.json"),
            "--random-baseline-iterations",
            "20",
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sparse_rows(["tp", "sl"], direction="short")

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]
    random_rows = read_csv(outputs["random_baseline_summary"])

    assert summary["stress_cost_config_requested"] == "True"
    assert "not found" in summary["stress_cost_not_available_reason"]
    assert random_rows[0]["iterations"] == "20"
    assert random_rows[0]["random_baseline_available"] == "False"
    assert "exact feature-combination scope" in random_rows[0]["random_baseline_not_available_reason"]
    assert summary["final_research_label"] != "NEEDS_WALK_FORWARD_REVIEW"


def test_stress_cost_configs_with_different_values_change_cost_and_net_R(tmp_path: Path) -> None:
    base_cost = tmp_path / "base_cost.json"
    stress_cost = tmp_path / "stress_cost.json"
    write_cost_config(base_cost, slippage_bps=0.0)
    write_cost_config(stress_cost, slippage_bps=10.0)
    args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--condition",
            "binary_feature:feature_flag:1",
            "--cost-config",
            str(base_cost),
            "--stress-cost-config",
            str(stress_cost),
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sparse_rows(["tp", "tp", "sl"], direction="short")

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]
    base_log = read_csv(outputs["trade_log_base"])
    stress_log = read_csv(outputs["trade_log_stress"])

    assert summary["stress_applied"] == "True"
    assert summary["stress_cost_no_effect_warning"] == "False"
    assert float(summary["mean_cost_R_stress"]) > float(summary["mean_cost_R_base"])
    assert float(summary["net_R_delta_mean"]) < 0
    assert base_log[0]["net_R"] != stress_log[0]["net_R"]


def test_fallback_spread_configs_have_no_effect_when_row_spread_is_used(tmp_path: Path) -> None:
    base_cost = tmp_path / "base_fallback_cost.json"
    stress_cost = tmp_path / "stress_fallback_cost.json"
    write_cost_config(base_cost, slippage_bps=0.2, fallback_spread_points=1.0, commission_bps=0.7)
    write_cost_config(stress_cost, slippage_bps=0.2, fallback_spread_points=3.0, commission_bps=0.7)
    args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--condition",
            "binary_feature:feature_flag:1",
            "--cost-config",
            str(base_cost),
            "--stress-cost-config",
            str(stress_cost),
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        rows = sparse_rows(["tp", "tp", "sl"], direction="short")
        for row in rows:
            row["spread"] = 2
        return rows

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]
    report = outputs["candidate_stress_report"].read_text(encoding="utf-8")

    assert summary["stress_cost_no_effect_warning"] == "True"
    assert summary["stress_changed_cost_R"] == "False"
    assert summary["stress_cost_R_changed"] == "False"
    assert summary["stress_spread_policy"] == "standard"
    assert summary["base_spread_source_used"] == "spread"
    assert summary["stress_spread_source_used"] == "spread"
    assert summary["base_row_level_spread_count"] == "3"
    assert summary["stress_row_level_spread_count"] == "3"
    assert summary["base_fallback_spread_count"] == "0"
    assert summary["stress_fallback_spread_count"] == "0"
    assert summary["base_max_row_or_fallback_count"] == "0"
    assert summary["stress_max_row_or_fallback_count"] == "0"
    assert summary["base_fallback_spread_points"] == "1.0"
    assert summary["stress_fallback_spread_points"] == "3.0"
    assert summary["base_fallback_spread_used"] == "False"
    assert summary["stress_fallback_spread_used"] == "False"
    assert "row-level spread field" in summary["cost_stress_no_effect_explanation"]
    assert "fallback_spread_points" in report


@pytest.mark.parametrize("policy", ["max_row_or_fallback", "fallback_override"])
def test_stress_spread_policy_changes_cost_when_stress_fallback_exceeds_row_spread(
    tmp_path: Path,
    policy: str,
) -> None:
    base_cost = tmp_path / f"base_{policy}_cost.json"
    stress_cost = tmp_path / f"stress_{policy}_cost.json"
    write_cost_config(base_cost, slippage_bps=0.0, fallback_spread_points=1.0)
    write_cost_config(stress_cost, slippage_bps=0.0, fallback_spread_points=5.0)
    args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--condition",
            "binary_feature:feature_flag:1",
            "--cost-config",
            str(base_cost),
            "--stress-cost-config",
            str(stress_cost),
            "--stress-spread-policy",
            policy,
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        rows = sparse_rows(["tp", "tp", "sl"], direction="short")
        for row in rows:
            row["spread"] = 2.0
        return rows

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]
    base_log = read_csv(outputs["trade_log_base"])
    stress_log = read_csv(outputs["trade_log_stress"])

    assert summary["stress_spread_policy"] == policy
    assert summary["stress_cost_no_effect_warning"] == "False"
    assert summary["stress_changed_cost_R"] == "True"
    assert summary["stress_cost_R_changed"] == "True"
    assert summary["base_spread_source_used"] == "spread"
    assert summary["stress_spread_source_used"] == "cost_config_symbol_fallback_spread_points"
    assert summary["stress_row_level_spread_count"] == "3"
    assert summary["stress_fallback_spread_count"] == "3"
    assert summary["stress_max_row_or_fallback_count"] == ("3" if policy == "max_row_or_fallback" else "0")
    assert summary["stress_fallback_spread_used"] == "True"
    assert float(summary["mean_cost_R_stress"]) > float(summary["mean_cost_R_base"])
    assert float(summary["cost_R_delta_mean"]) > 0
    assert float(summary["net_R_delta_mean"]) < 0
    assert float(stress_log[0]["cost_R"]) > float(base_log[0]["cost_R"])
    assert float(stress_log[0]["net_R"]) < float(base_log[0]["net_R"])


def test_max_row_or_fallback_keeps_row_spread_when_row_spread_exceeds_fallback(tmp_path: Path) -> None:
    base_cost = tmp_path / "base_max_row_keeps_row_cost.json"
    stress_cost = tmp_path / "stress_max_row_keeps_row_cost.json"
    write_cost_config(base_cost, slippage_bps=0.0, fallback_spread_points=1.0)
    write_cost_config(stress_cost, slippage_bps=0.0, fallback_spread_points=2.0)
    args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--condition",
            "binary_feature:feature_flag:1",
            "--cost-config",
            str(base_cost),
            "--stress-cost-config",
            str(stress_cost),
            "--stress-spread-policy",
            "max_row_or_fallback",
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        rows = sparse_rows(["tp", "tp", "sl"], direction="short")
        for row in rows:
            row["spread"] = 5.0
        return rows

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]
    base_log = read_csv(outputs["trade_log_base"])
    stress_log = read_csv(outputs["trade_log_stress"])

    assert summary["stress_spread_policy"] == "max_row_or_fallback"
    assert summary["stress_cost_no_effect_warning"] == "True"
    assert summary["stress_changed_cost_R"] == "False"
    assert summary["base_spread_source_used"] == "spread"
    assert summary["stress_spread_source_used"] == "spread"
    assert summary["stress_row_level_spread_count"] == "3"
    assert summary["stress_fallback_spread_count"] == "0"
    assert summary["stress_max_row_or_fallback_count"] == "0"
    assert "not larger than the available row-level spread" in summary["cost_stress_no_effect_explanation"]
    assert float(summary["mean_cost_R_stress"]) == pytest.approx(float(summary["mean_cost_R_base"]))
    assert float(summary["cost_R_delta_mean"]) == pytest.approx(0.0)
    assert float(summary["net_R_delta_mean"]) == pytest.approx(0.0)
    assert float(stress_log[0]["cost_R"]) == pytest.approx(float(base_log[0]["cost_R"]))
    assert float(stress_log[0]["net_R"]) == pytest.approx(float(base_log[0]["net_R"]))


def test_fallback_spread_configs_change_cost_when_spread_fields_are_missing(tmp_path: Path) -> None:
    base_cost = tmp_path / "base_effective_fallback_cost.json"
    stress_cost = tmp_path / "stress_effective_fallback_cost.json"
    write_cost_config(base_cost, slippage_bps=0.0, fallback_spread_points=1.0)
    write_cost_config(stress_cost, slippage_bps=0.0, fallback_spread_points=3.0)
    args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--condition",
            "binary_feature:feature_flag:1",
            "--cost-config",
            str(base_cost),
            "--stress-cost-config",
            str(stress_cost),
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        rows = sparse_rows(["tp", "tp", "sl"], direction="short")
        for row in rows:
            row.pop("spread", None)
            row.pop("spread_avg_20", None)
        return rows

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]
    base_log = read_csv(outputs["trade_log_base"])
    stress_log = read_csv(outputs["trade_log_stress"])

    assert summary["stress_cost_no_effect_warning"] == "False"
    assert summary["base_spread_source_used"] == "cost_config_symbol_fallback_spread_points"
    assert summary["stress_spread_source_used"] == "cost_config_symbol_fallback_spread_points"
    assert summary["base_fallback_spread_used"] == "True"
    assert summary["stress_fallback_spread_used"] == "True"
    assert float(summary["mean_cost_R_stress"]) > float(summary["mean_cost_R_base"])
    assert float(summary["net_R_delta_mean"]) < 0
    assert float(stress_log[0]["cost_R"]) > float(base_log[0]["cost_R"])
    assert float(stress_log[0]["net_R"]) < float(base_log[0]["net_R"])


def test_stress_cost_no_effect_warning_blocks_walk_forward_label(tmp_path: Path) -> None:
    base_cost = tmp_path / "same_base_cost.json"
    stress_cost = tmp_path / "same_stress_cost.json"
    write_cost_config(base_cost, slippage_bps=0.0)
    write_cost_config(stress_cost, slippage_bps=0.0)
    args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--condition",
            "binary_feature:feature_flag:1",
            "--cost-config",
            str(base_cost),
            "--stress-cost-config",
            str(stress_cost),
            "--walk-forward-splits",
            "0",
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sparse_rows(["tp"] * 60, direction="short")

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]

    assert summary["stress_applied"] == "True"
    assert summary["stress_cost_no_effect_warning"] == "True"
    assert summary["final_research_label"] == "STRESS_REVIEW_RETAINED"


def test_requested_random_baseline_unavailable_blocks_walk_forward_label(tmp_path: Path) -> None:
    args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--accept-broad-regime-scope",
            "--random-baseline-iterations",
            "5",
            "--walk-forward-splits",
            "0",
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sparse_rows(["tp"] * 60, direction="short")

    outputs = run_candidate_stress(args, row_loader=row_loader)
    summary = read_csv(outputs["candidate_stress_summary"])[0]

    assert summary["random_baseline_available"] == "False"
    assert summary["final_research_label"] == "STRESS_REVIEW_RETAINED"


def test_exact_scope_random_baseline_runs_on_synthetic_rows(tmp_path: Path) -> None:
    args = parse_args(
        base_argv(tmp_path)
        + [
            "--horizon",
            "1",
            "--condition",
            "binary_feature:feature_flag:1",
            "--random-baseline-iterations",
            "4",
            "--random-seed",
            "7",
        ]
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return synthetic_rows(
            ["tp", "sl", "tp", "sl", "tp", "sl"],
            direction="short",
            feature_flag_indexes={0, 2},
        )

    outputs = run_candidate_stress(args, row_loader=row_loader)
    random_rows = read_csv(outputs["random_baseline_summary"])
    summary = read_csv(outputs["candidate_stress_summary"])[0]

    assert random_rows[0]["random_baseline_available"] == "True"
    assert random_rows[0]["random_baseline_not_available_reason"] == ""
    assert summary["random_baseline_available"] == "True"


def test_random_baseline_synthetic_percentile_calculation() -> None:
    summary = summarize_random_baseline(
        {"mean_R": 0.4, "profit_factor_R": 2.0},
        [
            {"mean_R": 0.1, "profit_factor_R": 1.0, "max_drawdown_R": 3.0},
            {"mean_R": 0.2, "profit_factor_R": 1.5, "max_drawdown_R": 2.0},
            {"mean_R": 0.3, "profit_factor_R": 1.8, "max_drawdown_R": 1.0},
        ],
        3,
    )

    assert summary["random_mean_R_mean"] == pytest.approx(0.2)
    assert summary["random_mean_R_p95"] == pytest.approx(0.29)
    assert summary["candidate_percentile_vs_random_mean_R"] == 1.0


def test_report_contains_research_warning_and_no_blocked_language(tmp_path: Path) -> None:
    args = parse_args(base_argv(tmp_path) + ["--horizon", "1"])

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sparse_rows(["tp", "sl"], direction="short")

    outputs = run_candidate_stress(args, row_loader=row_loader)
    report = outputs["candidate_stress_report"].read_text(encoding="utf-8").lower()

    assert "research-only warning" in report
    for blocked in ("strategy", "signal", "live", "deploy"):
        assert blocked not in report


def test_script_does_not_import_metatrader_or_execution_terms() -> None:
    text = (Path(__file__).resolve().parents[1] / "scripts" / "validate_regime_candidate_stress.py").read_text(
        encoding="utf-8"
    )
    blocked = re.compile(
        "|".join(
            [
                "order_" + "send",
                "place_" + "order",
                "execute_" + "trade",
                "open_" + "position",
                "close_" + "position",
                "trade_" + "send",
                "position_" + "open",
                "position_" + "close",
                "import " + "Meta" + "Trader5",
                "from " + "Meta" + "Trader5",
                "mt5" + r"\.",
            ]
        )
    )

    assert blocked.findall(text) == []
