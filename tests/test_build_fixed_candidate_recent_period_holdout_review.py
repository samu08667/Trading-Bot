from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_recent_period_holdout_review as holdout


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def replay_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_replay",
        "fixed_rule_replay_backtest_run": True,
        "trades_closed": 45,
        "trades_tp": 28,
        "trades_sl": 9,
        "trades_timeout": 8,
        "total_R": 36.0,
        "average_R": 0.5,
        "median_R": 0.5,
        "win_rate_R_positive": 0.6,
        "max_drawdown_R": 2.0,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_optimization_performed": True,
        "no_trading_decision_performed": True,
    }
    payload.update(overrides)
    return payload


def replay_review_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_replay_review",
        "review_status": "continue_paper_validation",
        "yearly_row_count": 2,
        "monthly_row_count": 4,
        "outcome_row_count": 3,
        "no_replay_rerun": True,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_optimization_performed": True,
        "no_trading_decision_performed": True,
    }
    payload.update(overrides)
    return payload


def cost_review_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_cost_review",
        "review_status": "continue_paper_validation_with_cost_caveat",
        "recommended_next_step": "build_fixed_candidate_recent_period_holdout_review",
        "blocking_warnings_count": 0,
        "timeout_negative_under_severe": True,
        "timeout_negative_under_stress": True,
        "no_replay_rerun": True,
        "no_sensitivity_plan_rerun": True,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_optimization_performed": True,
        "no_trading_decision_performed": True,
    }
    payload.update(overrides)
    return payload


def trade(index: int, entry_time: str, reason: str, r_multiple: float) -> dict[str, object]:
    return {
        "run_id": "fixture_replay",
        "open_signal_id": f"s{index:03d}",
        "entry_time_server": entry_time,
        "exit_time_server": entry_time,
        "entry_price": 1.25,
        "exit_price": 1.24 if r_multiple > 0 else 1.26,
        "tp_price": 1.24,
        "sl_price": 1.26,
        "direction": "short",
        "exit_reason": reason,
        "R_multiple": r_multiple,
        "bars_elapsed": 5,
        "horizon_bars": 10,
        "same_bar_policy": "stop_first",
    }


def base_trades() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(1, 26):
        month = 1 if idx <= 12 else 2
        rows.append(trade(idx, f"2026-{month:02d}-{(idx - 1) % 12 + 1:02d} 00:00:00", "paper_tp_hit", 1.5))
    for idx in range(26, 31):
        rows.append(trade(idx, f"2026-03-{idx - 25:02d} 00:00:00", "paper_sl_hit", -1.0))
    for idx in range(31, 36):
        rows.append(trade(idx, f"2026-04-{idx - 30:02d} 00:00:00", "paper_timeout", 0.2))
    for idx in range(36, 41):
        rows.append(trade(idx, f"2025-12-{idx - 35:02d} 00:00:00", "paper_tp_hit", 1.5))
    return rows


def small_sample_trades() -> list[dict[str, object]]:
    return [
        *[trade(idx, f"2026-01-{idx:02d} 00:00:00", "paper_tp_hit", 1.5) for idx in range(1, 8)],
        *[trade(idx, f"2026-02-{idx - 7:02d} 00:00:00", "paper_sl_hit", -1.0) for idx in range(8, 10)],
        trade(10, "2025-12-01 00:00:00", "paper_tp_hit", 1.5),
    ]


def negative_recent_trades() -> list[dict[str, object]]:
    return [trade(idx, f"2026-01-{idx:02d} 00:00:00", "paper_sl_hit", -1.0) for idx in range(1, 10)]


def equity_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    cumulative = 0.0
    peak = 0.0
    for index, row in enumerate(rows, start=1):
        cumulative += float(row["R_multiple"])
        peak = max(peak, cumulative)
        output.append(
            {
                "run_id": "fixture_replay",
                "trade_index": index,
                "open_signal_id": row["open_signal_id"],
                "exit_time_server": row["exit_time_server"],
                "exit_reason": row["exit_reason"],
                "R_multiple": row["R_multiple"],
                "cumulative_R": cumulative,
                "peak_cumulative_R": peak,
                "drawdown_R": peak - cumulative,
            }
        )
    return output


def write_fixture_dirs(
    root: Path,
    *,
    trades: list[dict[str, object]] | None = None,
    missing_replay_manifest: bool = False,
    missing_trades: bool = False,
    bad_trades_csv: bool = False,
) -> tuple[Path, Path, Path]:
    replay_dir = root / "replay"
    review_dir = root / "replay_review"
    cost_dir = root / "cost_review"
    trade_rows = trades if trades is not None else base_trades()
    replay_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    cost_dir.mkdir(parents=True, exist_ok=True)
    if not missing_replay_manifest:
        write_json(replay_dir / holdout.REPLAY_MANIFEST, replay_manifest())
    if not missing_trades:
        if bad_trades_csv:
            write_csv(replay_dir / holdout.REPLAY_TRADES, ["not_required"], [{"not_required": "bad"}])
        else:
            write_csv(replay_dir / holdout.REPLAY_TRADES, list(trade_rows[0].keys()), trade_rows)
    write_csv(replay_dir / holdout.REPLAY_EQUITY, list(equity_rows(trade_rows)[0].keys()), equity_rows(trade_rows))
    write_csv(replay_dir / holdout.REPLAY_WARNINGS, holdout.WARNING_FIELDNAMES, [])
    write_json(review_dir / holdout.REPLAY_REVIEW_MANIFEST, replay_review_manifest())
    write_csv(review_dir / holdout.REPLAY_REVIEW_YEARLY, ["period", "trades_closed"], [{"period": "2026", "trades_closed": 35}])
    write_csv(review_dir / holdout.REPLAY_REVIEW_MONTHLY, ["period", "trades_closed"], [{"period": "2026-01", "trades_closed": 12}])
    write_csv(review_dir / holdout.REPLAY_REVIEW_OUTCOMES, ["exit_reason", "trade_count"], [{"exit_reason": "paper_tp_hit", "trade_count": 25}])
    write_csv(review_dir / holdout.REPLAY_REVIEW_WARNINGS, holdout.WARNING_FIELDNAMES, [])
    write_json(cost_dir / holdout.COST_REVIEW_MANIFEST, cost_review_manifest())
    (cost_dir / holdout.COST_REVIEW_REPORT).write_text("# Cost Review\n", encoding="utf-8")
    return replay_dir, review_dir, cost_dir


def make_args(
    tmp_path: Path,
    replay_dir: Path,
    review_dir: Path,
    cost_dir: Path,
    *extra: str,
) -> object:
    return holdout.build_parser().parse_args(
        [
            "--run-id",
            "unit_holdout_review",
            "--replay-backtest-dir",
            str(replay_dir),
            "--replay-review-dir",
            str(review_dir),
            "--cost-sensitivity-review-dir",
            str(cost_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
            *extra,
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        holdout.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))

    assert outputs["review"].exists()
    assert outputs["trades"].exists()
    assert outputs["monthly"].exists()
    assert outputs["outcomes"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_recent_year_selection_filters_correct_trades(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["recent_period_definition"] == "2026"
    assert manifest["recent_trade_count"] == 35


def test_recent_from_time_selection_overrides_recent_year(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)
    outputs = holdout.build_outputs(
        make_args(tmp_path, replay_dir, review_dir, cost_dir, "--recent-from-time", "2025-12-01 00:00:00")
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["recent_period_definition"] == "entry_time_server >= 2025-12-01 00:00:00"
    assert manifest["recent_trade_count"] == 40


def test_latest_n_months_selection_works_without_recent_year_or_from_time(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)
    outputs = holdout.build_outputs(
        make_args(tmp_path, replay_dir, review_dir, cost_dir, "--recent-year", "", "--recent-months", "2")
    )
    manifest = read_json(outputs["manifest"])
    trades = read_csv(outputs["trades"])

    assert "latest_2_calendar_months" in str(manifest["recent_period_definition"])
    assert {row["period_label"] for row in trades} == {"2026-03", "2026-04"}


def test_positive_recent_period_with_at_least_30_trades_is_ok(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "continue_paper_validation_recent_period_ok"


def test_positive_recent_period_under_30_trades_has_holdout_caveat(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path, trades=small_sample_trades())
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "continue_demo_readiness_planning_with_holdout_caveat"
    assert manifest["small_sample_caveat"] is True


def test_negative_recent_period_holds_for_weakness(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path, trades=negative_recent_trades())
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "hold_for_recent_period_weakness"


def test_missing_replay_manifest_blocks(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path, missing_replay_manifest=True)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_missing_required_artifact"


def test_missing_trades_csv_blocks(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path, missing_trades=True)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_missing_required_artifact"


def test_unreadable_trades_csv_blocks_safely(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path, bad_trades_csv=True)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["review_status"] == "blocked_unreadable_input"
    assert any(warning["warning_code"] == "source_trades_csv_unreadable" for warning in warnings)


def test_monthly_breakdown_is_computed_correctly(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    monthly = {row["period"]: row for row in read_csv(outputs["monthly"])}

    assert monthly["2026-01"]["trades_closed"] == "12"
    assert monthly["2026-03"]["trades_sl"] == "5"
    assert monthly["2026-04"]["trades_timeout"] == "5"


def test_outcome_breakdown_is_computed_correctly(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    outcomes = {row["exit_reason"]: row for row in read_csv(outputs["outcomes"])}

    assert outcomes["paper_tp_hit"]["trade_count"] == "25"
    assert outcomes["paper_sl_hit"]["trade_count"] == "5"
    assert outcomes["paper_timeout"]["trade_count"] == "5"


def test_recent_vs_full_deltas_are_computed_correctly(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["average_R_delta_recent_vs_full"] == pytest.approx(manifest["recent_average_R"] - 0.5)
    assert manifest["win_rate_delta_recent_vs_full"] == pytest.approx(manifest["recent_win_rate_R_positive"] - 0.6)
    assert manifest["drawdown_ratio_recent_vs_full"] == pytest.approx(manifest["recent_max_drawdown_R"] / 2.0)


def test_manifest_counts_match_csvs_and_warnings(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["recent_trade_count"] == len(read_csv(outputs["trades"]))
    assert manifest["monthly_row_count"] == len(read_csv(outputs["monthly"]))
    assert manifest["outcome_row_count"] == len(read_csv(outputs["outcomes"]))
    assert manifest["warnings_count"] == len(warnings)


def test_report_includes_no_rerun_execution_db_mutation_optimization_future_proof_demo_readiness_caveats(tmp_path: Path) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)
    outputs = holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "did not rerun the replay" in report
    assert "did not rerun the cost sensitivity review" in report
    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No order execution was performed." in report
    assert "No database mutation was performed." in report
    assert "No optimization or parameter search was performed." in report
    assert "not future-performance proof" in report
    assert "not demo broker readiness approval" in report


def test_no_db_queries_are_performed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("DB query should not be performed")

    monkeypatch.setattr(sqlite3, "connect", fail_if_called)
    holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replay_dir, review_dir, cost_dir = write_fixture_dirs(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    holdout.build_outputs(make_args(tmp_path, replay_dir, review_dir, cost_dir))
