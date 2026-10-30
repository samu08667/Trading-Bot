import argparse
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.run_rule_based_regime_candidate_backtest import (
    MATCHED_LABEL,
    MINOR_LABEL,
    REJECTED_LABEL,
    build_spec,
    parse_args,
    run_rule_replay,
)
from scripts.validate_regime_candidate_stress import (
    CandidateScope,
    CandidateSpec,
    EQUITY_FIELDNAMES,
    STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK,
    TRADE_LOG_FIELDNAMES,
    apply_bar_level_no_overlap,
    collect_replay_events,
    condition_text_from_filter_sets,
    equity_curve_rows,
    load_cost_config,
    path_config_for_spec,
    prepare_scope_predicate,
    replay_metrics,
    trade_log_rows,
)


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


def write_cost_config(path: Path, fallback_spread_points: float) -> None:
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
                        "fallback_spread_points": fallback_spread_points,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def synthetic_rows(outcomes: list[str]) -> list[dict[str, object]]:
    start = datetime(2024, 1, 1)
    expanded = []
    eligible: set[int] = set()
    for index, outcome in enumerate(outcomes):
        entry_index = index * 2
        while len(expanded) <= entry_index:
            expanded.append("timeout")
        expanded[entry_index] = outcome
        eligible.add(entry_index)

    rows: list[dict[str, object]] = []
    for index in range(len(expanded) + 2):
        timestamp = start + timedelta(minutes=15 * index)
        rows.append(
            {
                "symbol": "GBPUSD",
                "timeframe": "M15",
                "time_server": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "open": 100.0,
                "high": 100.4,
                "low": 99.6,
                "close": 100.0,
                "atr_20": 1.0,
                "session": "Off_hours" if index in eligible else "London",
                "feature_flag": 1 if index in eligible else 0,
                "spread": 2.0,
            }
        )
    for index, outcome in enumerate(expanded):
        exit_row = rows[index + 1]
        if outcome == "tp":
            exit_row["low"] = 98.4
        elif outcome == "sl":
            exit_row["high"] = 101.1
        elif outcome == "timeout":
            exit_row["close"] = 99.8
    return rows


def candidate_spec() -> CandidateSpec:
    return CandidateSpec(
        symbol="GBPUSD",
        direction="short",
        timeframe="M15",
        horizon=1,
        target_family="preferred_1_5atr_1atr_hit_first",
        regime_column="session",
        regime_value="Off_hours",
        tp_atr=1.5,
        sl_atr=1.0,
        atr_column="atr_20",
        same_bar_policy="stop_first",
    )


def build_previous_package(
    tmp_path: Path,
    *,
    summary_overrides: dict[str, object] | None = None,
    review_classification: str = "READY_FOR_RULE_BASED_RESEARCH_BACKTEST_REVIEW",
    trim_previous_logs: bool = False,
) -> tuple[Path, Path, Path, Path, Path, list[dict[str, object]]]:
    rows = synthetic_rows(["tp", "tp", "sl"])
    base_cost = tmp_path / "p75_cost.json"
    stress_cost = tmp_path / "p90_cost.json"
    write_cost_config(base_cost, 1.0)
    write_cost_config(stress_cost, 5.0)
    spec = candidate_spec()
    filter_set = ("binary_feature:feature_flag:1",)
    scope = CandidateScope(
        name="exact_feature_combination",
        filter_sets=(filter_set,),
        condition_text=condition_text_from_filter_sets((filter_set,)),
    )
    prepared_scope, predicate = prepare_scope_predicate(rows, scope)
    assert not prepared_scope.exact_candidate_not_available_reason
    base_events = collect_replay_events(
        rows,
        spec,
        config=path_config_for_spec(spec, cost_mode="estimated", return_mode="net"),
        cost_config=load_cost_config(base_cost),
        scope=prepared_scope,
        scope_predicate=predicate,
    )
    stress_events = collect_replay_events(
        rows,
        spec,
        config=path_config_for_spec(spec, cost_mode="estimated", return_mode="net"),
        cost_config=load_cost_config(stress_cost),
        scope=prepared_scope,
        scope_predicate=predicate,
        stress_spread_policy=STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK,
    )
    base_result = apply_bar_level_no_overlap(base_events, True)
    stress_result = apply_bar_level_no_overlap(stress_events, True)
    base_metrics = replay_metrics(base_result.events, base_result.skipped_due_to_overlap)
    stress_metrics = replay_metrics(stress_result.events, stress_result.skipped_due_to_overlap)
    base_log = trade_log_rows(base_result.events)
    stress_log = trade_log_rows(stress_result.events)
    written_base_log = base_log[:-1] if trim_previous_logs else base_log
    written_stress_log = stress_log[:-1] if trim_previous_logs else stress_log
    stress_dir = tmp_path / "stress_outputs" / "unit_rule_candidate"
    review_dir = tmp_path / "review_outputs" / "unit_rule_candidate"
    summary: dict[str, object] = {
        "symbol": spec.symbol,
        "direction": spec.direction,
        "timeframe": spec.timeframe,
        "horizon": spec.horizon,
        "target_family": spec.target_family,
        "regime_column": spec.regime_column,
        "regime_value": spec.regime_value,
        "feature_condition": prepared_scope.condition_text,
        "tp_atr": spec.tp_atr,
        "sl_atr": spec.sl_atr,
        "atr_column": spec.atr_column,
        "same_bar_policy": spec.same_bar_policy,
        "bar_level_no_overlap": 1,
        "candidate_scope": "exact_feature_combination",
        "exact_candidate_not_available_reason": "",
        "stress_spread_policy": "max_row_or_fallback",
        "stress_applied": "True",
        "stress_changed_cost_R": "True",
        "stress_cost_no_effect_warning": "False",
        "sequential_trades_count": base_metrics["sequential_trades_count"],
        "stress_sequential_trades_count": stress_metrics["sequential_trades_count"],
        "mean_R": base_metrics["mean_R"],
        "profit_factor_R": base_metrics["profit_factor_R"],
        "cumulative_R": base_metrics["cumulative_R"],
        "max_drawdown_R": base_metrics["max_drawdown_R"],
        "stress_mean_R": stress_metrics["mean_R"],
        "stress_profit_factor_R": stress_metrics["profit_factor_R"],
        "stress_cumulative_R": stress_metrics["cumulative_R"],
        "stress_max_drawdown_R": stress_metrics["max_drawdown_R"],
        "random_baseline_available": "True",
        "candidate_mean_R_vs_random_p95": "0.1",
        "candidate_profit_factor_R_vs_random_p95": "0.2",
        "yearly_positive_ratio": "1.0",
        "final_research_label": "NEEDS_WALK_FORWARD_REVIEW",
    }
    if trim_previous_logs:
        summary["sequential_trades_count"] = int(summary["sequential_trades_count"]) - 1
        summary["stress_sequential_trades_count"] = int(summary["stress_sequential_trades_count"]) - 1
    if summary_overrides:
        summary.update(summary_overrides)
    write_csv(stress_dir / "candidate_stress_summary.csv", [summary])
    write_csv(stress_dir / "trade_log_base.csv", written_base_log, TRADE_LOG_FIELDNAMES)
    write_csv(stress_dir / "trade_log_stress.csv", written_stress_log, TRADE_LOG_FIELDNAMES)
    write_csv(stress_dir / "equity_curve_base.csv", equity_curve_rows(base_result.events), EQUITY_FIELDNAMES)
    write_csv(stress_dir / "equity_curve_stress.csv", equity_curve_rows(stress_result.events), EQUITY_FIELDNAMES)
    write_csv(
        review_dir / "candidate_review_summary.csv",
        [
            {
                "final_research_only_classification": review_classification,
                "stress_output_dir": str(stress_dir),
                "symbol": spec.symbol,
                "direction": spec.direction,
                "feature_condition": prepared_scope.condition_text,
            }
        ],
    )
    write_csv(review_dir / "candidate_review_warnings.csv", [], ["severity", "check", "blocks_ready", "message"])
    (review_dir / "candidate_review_report.md").write_text("review\n", encoding="utf-8")
    return stress_dir, review_dir, base_cost, stress_cost, tmp_path / "unused.db", rows


def build_args(
    tmp_path: Path,
    *,
    stress_dir: Path,
    review_dir: Path | None,
    base_cost: Path,
    stress_cost: Path,
    db_path: Path,
    overwrite: bool = True,
) -> argparse.Namespace:
    argv = [
        "--stress-output-dir",
        str(stress_dir),
        "--db-path",
        str(db_path),
        "--cost-config",
        str(base_cost),
        "--stress-cost-config",
        str(stress_cost),
        "--stress-spread-policy",
        "max_row_or_fallback",
        "--bar-level-no-overlap",
        "--run-id",
        "unit_rule_candidate",
        "--output-root",
        str(tmp_path / "rule_outputs"),
    ]
    if review_dir is not None:
        argv.extend(["--review-package-dir", str(review_dir)])
    if overwrite:
        argv.append("--overwrite")
    return parse_args(argv)


def run_package(
    tmp_path: Path,
    *,
    summary_overrides: dict[str, object] | None = None,
    review_classification: str = "READY_FOR_RULE_BASED_RESEARCH_BACKTEST_REVIEW",
    trim_previous_logs: bool = False,
    overwrite: bool = True,
) -> tuple[dict[str, Path], dict[str, str]]:
    stress_dir, review_dir, base_cost, stress_cost, db_path, rows = build_previous_package(
        tmp_path,
        summary_overrides=summary_overrides,
        review_classification=review_classification,
        trim_previous_logs=trim_previous_logs,
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return rows

    outputs = run_rule_replay(
        build_args(
            tmp_path,
            stress_dir=stress_dir,
            review_dir=review_dir,
            base_cost=base_cost,
            stress_cost=stress_cost,
            db_path=db_path,
            overwrite=overwrite,
        ),
        row_loader=row_loader,
    )
    return outputs, read_csv(outputs["summary"])[0]


def test_happy_path_replay_matches_previous_stress_validation(tmp_path: Path) -> None:
    outputs, summary = run_package(tmp_path)

    assert summary["final_rule_replay_classification"] == MATCHED_LABEL
    assert summary["generated_logs_match_stress_validation"] == "True"
    assert read_csv(outputs["warnings"]) == []
    assert "Candidate can continue to offline rule-based research review." in outputs["report"].read_text(encoding="utf-8")


def test_review_package_not_ready_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not ready"):
        run_package(tmp_path, review_classification="REVIEW_PACKAGE_RETAINED")


def test_broad_regime_scope_is_not_allowed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="candidate_scope"):
        run_package(tmp_path, summary_overrides={"candidate_scope": "broad_regime_only"})


def test_missing_exact_feature_condition_errors(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="feature_condition|Exact feature condition"):
        run_package(tmp_path, summary_overrides={"feature_condition": ""})


def test_build_spec_reads_different_candidate_metadata() -> None:
    spec = build_spec(
        {
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
            "atr_column": "atr_14",
            "same_bar_policy": "target_first",
        }
    )

    assert spec.symbol == "EURUSD"
    assert spec.direction == "long"
    assert spec.horizon == 5
    assert spec.target_family == "preferred_2atr_1atr_hit_first"
    assert spec.regime_value == "London"
    assert spec.tp_atr == 2.0
    assert spec.sl_atr == 1.0


def test_build_spec_missing_metadata_errors_clearly() -> None:
    with pytest.raises(ValueError, match="Candidate metadata is missing.*symbol"):
        build_spec(
            {
                "symbol": "",
                "direction": "long",
                "timeframe": "M15",
                "horizon": "h5",
                "target_family": "preferred_2atr_1atr_hit_first",
                "regime_column": "session",
                "regime_value": "London",
                "feature_condition": "numeric_tercile:momentum_score:high_tercile",
                "tp_atr": "2.0",
                "sl_atr": "1.0",
            }
        )


def test_stress_no_effect_warning_is_not_allowed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="stress_changed_cost_R|stress_cost_no_effect_warning"):
        run_package(
            tmp_path,
            summary_overrides={"stress_changed_cost_R": "False", "stress_cost_no_effect_warning": "True"},
        )


def test_trade_count_mismatch_is_minor_review(tmp_path: Path) -> None:
    _outputs, summary = run_package(tmp_path, trim_previous_logs=True)

    assert summary["final_rule_replay_classification"] == MINOR_LABEL
    assert summary["generated_logs_match_stress_validation"] == "False"
    assert summary["extra_trades_count"] == "2"


def test_mean_r_mismatch_above_tolerance_is_rejected(tmp_path: Path) -> None:
    _outputs, summary = run_package(tmp_path, summary_overrides={"stress_mean_R": "99.0"})

    assert summary["final_rule_replay_classification"] == REJECTED_LABEL
    assert float(summary["stress_mean_R_difference"]) != 0.0


def test_missing_input_file_errors(tmp_path: Path) -> None:
    stress_dir, review_dir, base_cost, stress_cost, db_path, rows = build_previous_package(tmp_path)
    (stress_dir / "candidate_stress_summary.csv").unlink()

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return rows

    with pytest.raises(FileNotFoundError, match="candidate_stress_summary"):
        run_rule_replay(
            build_args(
                tmp_path,
                stress_dir=stress_dir,
                review_dir=review_dir,
                base_cost=base_cost,
                stress_cost=stress_cost,
                db_path=db_path,
            ),
            row_loader=row_loader,
        )


def test_overwrite_protection(tmp_path: Path) -> None:
    stress_dir, review_dir, base_cost, stress_cost, db_path, rows = build_previous_package(tmp_path)

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return rows

    run_rule_replay(
        build_args(
            tmp_path,
            stress_dir=stress_dir,
            review_dir=review_dir,
            base_cost=base_cost,
            stress_cost=stress_cost,
            db_path=db_path,
        ),
        row_loader=row_loader,
    )
    with pytest.raises(FileExistsError, match="--overwrite"):
        run_rule_replay(
            build_args(
                tmp_path,
                stress_dir=stress_dir,
                review_dir=review_dir,
                base_cost=base_cost,
                stress_cost=stress_cost,
                db_path=db_path,
                overwrite=False,
            ),
            row_loader=row_loader,
        )
