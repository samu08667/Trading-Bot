from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_fixed_rule_replay_backtest_review as review


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


def source_manifest(**overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "run_id": "fixture_replay",
        "fixed_rule_replay_backtest_run": True,
        "bars_processed": 101186,
        "signals_opened": 437,
        "signals_skipped": 97831,
        "trades_closed": 120,
        "trades_tp": 60,
        "trades_sl": 20,
        "trades_timeout": 40,
        "total_R": 72.0,
        "average_R": 0.6,
        "median_R": 0.5,
        "win_rate_R_positive": 0.7,
        "max_drawdown_R": 4.0,
        "longest_loss_streak": 3,
        "longest_win_streak": 8,
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "spread_policy_matches_canonical": True,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_stress_validation_executed": True,
        "no_walk_forward_validation_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
    }
    manifest.update(overrides)
    return manifest


def trade(
    entry: str,
    exit_time: str,
    reason: str,
    r_multiple: float,
    signal_id: str,
) -> dict[str, object]:
    return {
        "run_id": "fixture_replay",
        "open_signal_id": signal_id,
        "entry_time_server": entry,
        "exit_time_server": exit_time,
        "entry_price": 1.25,
        "exit_price": 1.248 if r_multiple > 0 else 1.252,
        "tp_price": 1.247,
        "sl_price": 1.252,
        "direction": "short",
        "exit_reason": reason,
        "R_multiple": r_multiple,
        "bars_elapsed": 3,
        "horizon_bars": 10,
        "same_bar_policy": "stop_first",
    }


def fixture_trades() -> list[dict[str, object]]:
    return [
        trade("2025-01-01 00:00:00", "2025-01-01 01:00:00", "paper_tp_hit", 1.5, "s1"),
        trade("2025-01-02 00:00:00", "2025-01-02 01:00:00", "paper_sl_hit", -1.0, "s2"),
        trade("2025-02-01 00:00:00", "2025-02-01 01:00:00", "paper_timeout", 0.25, "s3"),
        trade("2026-01-01 00:00:00", "2026-01-01 01:00:00", "paper_tp_hit", 1.5, "s4"),
    ]


def equity_rows(trades: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    cumulative = 0.0
    peak = 0.0
    for index, row in enumerate(trades, start=1):
        cumulative += float(row["R_multiple"])
        peak = max(peak, cumulative)
        rows.append(
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
    return rows


def write_replay_dir(
    path: Path,
    *,
    manifest: dict[str, object] | None = None,
    trades: list[dict[str, object]] | None = None,
    missing_manifest: bool = False,
    missing_trades: bool = False,
    bad_trades_csv: bool = False,
    same_bar_warnings: int = 0,
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    trade_rows = trades if trades is not None else fixture_trades()
    if not missing_manifest:
        write_json(path / review.SOURCE_MANIFEST, manifest if manifest is not None else source_manifest())
    (path / review.SOURCE_REPORT).write_text("# Replay\n", encoding="utf-8")
    write_csv(path / review.SOURCE_BARS, ["run_id", "time_server"], [{"run_id": "fixture_replay", "time_server": "2025-01-01 00:00:00"}])
    write_csv(path / review.SOURCE_SIGNALS, ["run_id", "signal_state"], [{"run_id": "fixture_replay", "signal_state": "paper_signal_opened"}])
    if not missing_trades:
        if bad_trades_csv:
            write_csv(path / review.SOURCE_TRADES, ["not_the_right_column"], [{"not_the_right_column": "bad"}])
        else:
            write_csv(path / review.SOURCE_TRADES, list(trade_rows[0].keys()), trade_rows)
    write_csv(path / review.SOURCE_EQUITY, list(equity_rows(trade_rows)[0].keys()), equity_rows(trade_rows))
    warnings = [
        {
            "run_id": "fixture_replay",
            "warning_code": "same_bar_stop_first_applied",
            "severity": "warning",
            "message": "same bar caveat",
            "source": "fixture",
            "blocking_warning": "false",
        }
        for _ in range(same_bar_warnings)
    ]
    write_csv(path / review.SOURCE_WARNINGS, review.WARNING_FIELDNAMES, warnings)


def make_args(tmp_path: Path, replay_dir: Path) -> object:
    return review.build_parser().parse_args(
        [
            "--run-id",
            "unit_replay_review",
            "--replay-backtest-dir",
            str(replay_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        review.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))

    assert outputs["review"].exists()
    assert outputs["yearly"].exists()
    assert outputs["monthly"].exists()
    assert outputs["outcomes"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_valid_replay_produces_continue_paper_validation(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "continue_paper_validation"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_replay_cost_sensitivity_plan"
    assert manifest["spread_unit"] == "broker_points"
    assert manifest["max_spread_points"] == 15.0
    assert manifest["spread_policy_matches_canonical"] is True


def test_negative_weak_replay_holds_for_more_validation(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir, manifest=source_manifest(trades_closed=80, total_R=-1.0, average_R=-0.01))
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "hold_for_more_validation"


def test_missing_manifest_blocks(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir, missing_manifest=True)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_missing_required_artifact"
    assert manifest["missing_source_artifact_count"] >= 1


def test_missing_trades_csv_blocks(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir, missing_trades=True)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    warnings = read_csv(outputs["warnings"])
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_missing_required_artifact"
    assert any(warning["warning_code"] == f"source_{review.SOURCE_TRADES}_missing" for warning in warnings)


def test_unreadable_trades_csv_blocks_safely(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir, bad_trades_csv=True)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    warnings = read_csv(outputs["warnings"])
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_unreadable_replay_artifacts"
    assert any(warning["warning_code"] == "source_trades_csv_unreadable" for warning in warnings)


def test_yearly_breakdown_is_computed_correctly(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    yearly = {row["period"]: row for row in read_csv(outputs["yearly"])}

    assert yearly["2025"]["trades_closed"] == "3"
    assert float(yearly["2025"]["total_R"]) == pytest.approx(0.75)
    assert yearly["2026"]["trades_closed"] == "1"


def test_monthly_breakdown_is_computed_correctly(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    monthly = {row["period"]: row for row in read_csv(outputs["monthly"])}

    assert monthly["2025-01"]["trades_closed"] == "2"
    assert float(monthly["2025-01"]["total_R"]) == pytest.approx(0.5)
    assert monthly["2025-02"]["trades_timeout"] == "1"


def test_outcome_breakdown_is_computed_correctly(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    outcomes = {row["exit_reason"]: row for row in read_csv(outputs["outcomes"])}

    assert outcomes["paper_tp_hit"]["trade_count"] == "2"
    assert float(outcomes["paper_tp_hit"]["share_of_trades"]) == pytest.approx(0.5)
    assert outcomes["paper_sl_hit"]["trade_count"] == "1"


def test_timeout_contribution_is_summarized(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    rows = {row["review_area"]: row for row in read_csv(outputs["review"])}

    assert rows["timeout_review"]["evidence_label"] == "timeout_contribution_reviewed"
    assert rows["timeout_review"]["observed_value"] == "40"


def test_same_bar_warning_count_is_preserved(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir, same_bar_warnings=2)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    manifest = read_json(outputs["manifest"])
    rows = {row["review_area"]: row for row in read_csv(outputs["review"])}

    assert manifest["same_bar_stop_first_warning_count"] == 2
    assert rows["same_bar_warning_review"]["observed_value"] == "2"


def test_manifest_counts_match_csvs_and_warnings(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir, same_bar_warnings=1)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    warnings = read_csv(outputs["warnings"])
    manifest = read_json(outputs["manifest"])

    assert manifest["yearly_row_count"] == len(read_csv(outputs["yearly"]))
    assert manifest["monthly_row_count"] == len(read_csv(outputs["monthly"]))
    assert manifest["outcome_row_count"] == len(read_csv(outputs["outcomes"]))
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(
        1 for warning in warnings if warning["blocking_warning"].lower() == "true"
    )


def test_report_includes_no_execution_db_mutation_optimization_future_proof_approval_caveats(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir)
    outputs = review.build_outputs(make_args(tmp_path, replay_dir))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No order execution was performed." in report
    assert "No database mutation was performed." in report
    assert "No optimization or parameter search was performed." in report
    assert "not future-performance proof" in report
    assert "not candidate approval" in report
    assert "spread_policy_matches_canonical: `True`" in report


def test_no_db_queries_are_performed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("DB query should not be performed")

    monkeypatch.setattr(sqlite3, "connect", fail_if_called)
    review.build_outputs(make_args(tmp_path, replay_dir))


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replay_dir = tmp_path / "replay"
    write_replay_dir(replay_dir)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    review.build_outputs(make_args(tmp_path, replay_dir))
