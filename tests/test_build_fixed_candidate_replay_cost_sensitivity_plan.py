from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_replay_cost_sensitivity_plan as plan


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


def review_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_review",
        "review_status": "continue_paper_validation",
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "no_child_scripts_executed": True,
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


def replay_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_replay",
        "fixed_rule_replay_backtest_run": True,
        "trades_closed": 4,
        "trades_tp": 2,
        "trades_sl": 1,
        "trades_timeout": 1,
        "total_R": 2.15,
        "average_R": 0.5375,
        "median_R": 0.825,
        "win_rate_R_positive": 0.75,
        "max_drawdown_R": 1.0,
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
    payload.update(overrides)
    return payload


def trades() -> list[dict[str, object]]:
    return [
        {
            "run_id": "fixture_replay",
            "open_signal_id": "s1",
            "entry_time_server": "2026-01-01 00:00:00",
            "exit_time_server": "2026-01-01 00:15:00",
            "exit_reason": "paper_tp_hit",
            "R_multiple": 1.5,
        },
        {
            "run_id": "fixture_replay",
            "open_signal_id": "s2",
            "entry_time_server": "2026-01-02 00:00:00",
            "exit_time_server": "2026-01-02 00:15:00",
            "exit_reason": "paper_sl_hit",
            "R_multiple": -1.0,
        },
        {
            "run_id": "fixture_replay",
            "open_signal_id": "s3",
            "entry_time_server": "2026-01-03 00:00:00",
            "exit_time_server": "2026-01-03 00:15:00",
            "exit_reason": "paper_timeout",
            "R_multiple": 0.15,
        },
        {
            "run_id": "fixture_replay",
            "open_signal_id": "s4",
            "entry_time_server": "2026-01-04 00:00:00",
            "exit_time_server": "2026-01-04 00:15:00",
            "exit_reason": "paper_tp_hit",
            "R_multiple": 1.5,
        },
    ]


def equity_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    cumulative = 0.0
    peak = 0.0
    for index, row in enumerate(trades(), start=1):
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


def write_review_dir(path: Path, *, manifest: dict[str, object] | None = None, missing_manifest: bool = False) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not missing_manifest:
        write_json(path / plan.REVIEW_MANIFEST, manifest if manifest is not None else review_manifest())
    (path / plan.REVIEW_REPORT).write_text("# Review\n", encoding="utf-8")
    write_csv(path / plan.REVIEW_CSV, plan.PLAN_FIELDNAMES, [])
    write_csv(path / plan.REVIEW_YEARLY, ["period"], [{"period": "2026"}])
    write_csv(path / plan.REVIEW_MONTHLY, ["period"], [{"period": "2026-01"}])
    write_csv(path / plan.REVIEW_OUTCOMES, ["exit_reason"], [{"exit_reason": "paper_tp_hit"}])
    write_csv(path / plan.REVIEW_WARNINGS, plan.WARNING_FIELDNAMES, [])


def write_replay_dir(
    path: Path,
    *,
    manifest: dict[str, object] | None = None,
    missing_trades: bool = False,
    bad_trades_csv: bool = False,
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    write_json(path / plan.REPLAY_MANIFEST, manifest if manifest is not None else replay_manifest())
    if not missing_trades:
        if bad_trades_csv:
            write_csv(path / plan.REPLAY_TRADES, ["not_r"], [{"not_r": "bad"}])
        else:
            write_csv(path / plan.REPLAY_TRADES, list(trades()[0].keys()), trades())
    write_csv(path / plan.REPLAY_EQUITY, list(equity_rows()[0].keys()), equity_rows())
    write_csv(path / plan.REPLAY_WARNINGS, plan.WARNING_FIELDNAMES, [])


def make_args(tmp_path: Path, review_dir: Path, replay_dir: Path) -> object:
    return plan.build_parser().parse_args(
        [
            "--run-id",
            "unit_cost_sensitivity_plan",
            "--replay-review-dir",
            str(review_dir),
            "--replay-backtest-dir",
            str(replay_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def build_fixture(tmp_path: Path, *, review_payload: dict[str, object] | None = None) -> tuple[Path, Path]:
    review_dir = tmp_path / "review"
    replay_dir = tmp_path / "replay"
    write_review_dir(review_dir, manifest=review_payload)
    write_replay_dir(replay_dir)
    return review_dir, replay_dir


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    review_dir, replay_dir = build_fixture(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))

    assert outputs["plan"].exists()
    assert outputs["scenarios"].exists()
    assert outputs["outcomes"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_valid_replay_produces_five_default_scenario_rows(tmp_path: Path) -> None:
    review_dir, replay_dir = build_fixture(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    scenarios = read_csv(outputs["scenarios"])

    assert [row["scenario_label"] for row in scenarios] == ["base", "mild", "medium", "severe", "stress"]
    assert len(scenarios) == 5


def test_scenario_adjusted_totals_subtract_cost_per_trade(tmp_path: Path) -> None:
    review_dir, replay_dir = build_fixture(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    scenarios = {row["scenario_label"]: row for row in read_csv(outputs["scenarios"])}

    assert float(scenarios["base"]["adjusted_total_R"]) == pytest.approx(2.15)
    assert float(scenarios["mild"]["adjusted_total_R"]) == pytest.approx(2.15 - 4 * 0.05)
    assert float(scenarios["medium"]["adjusted_average_R"]) == pytest.approx((2.15 - 4 * 0.10) / 4)


def test_outcome_sensitivity_is_computed_correctly(tmp_path: Path) -> None:
    review_dir, replay_dir = build_fixture(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    outcomes = {
        (row["scenario_label"], row["exit_reason"]): row
        for row in read_csv(outputs["outcomes"])
    }

    assert outcomes[("medium", "paper_tp_hit")]["trade_count"] == "2"
    assert float(outcomes[("medium", "paper_tp_hit")]["adjusted_average_R"]) == pytest.approx(1.4)
    assert float(outcomes[("medium", "paper_timeout")]["adjusted_average_R"]) == pytest.approx(0.05)


def test_timeout_fragility_caveat_appears_when_timeout_adjusted_average_negative(tmp_path: Path) -> None:
    review_dir, replay_dir = build_fixture(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    outcomes = read_csv(outputs["outcomes"])
    scenarios = {row["scenario_label"]: row for row in read_csv(outputs["scenarios"])}
    report = outputs["report"].read_text(encoding="utf-8")

    assert any(
        row["scenario_label"] == "severe"
        and row["exit_reason"] == "paper_timeout"
        and row["caveat"] == "timeout_bucket_negative_under_extra_cost"
        for row in outcomes
    )
    assert scenarios["severe"]["scenario_status"] == "fragile_under_scenario"
    assert "timeout scenarios with negative adjusted average" in report


def test_missing_review_manifest_blocks(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    replay_dir = tmp_path / "replay"
    write_review_dir(review_dir, missing_manifest=True)
    write_replay_dir(replay_dir)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_required_artifact"
    assert manifest["missing_source_artifact_count"] >= 1


def test_missing_trades_csv_blocks(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    replay_dir = tmp_path / "replay"
    write_review_dir(review_dir)
    write_replay_dir(replay_dir, missing_trades=True)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["plan_status"] == "blocked_missing_required_artifact"
    assert any(warning["warning_code"] == f"replay_{plan.REPLAY_TRADES}_missing" for warning in warnings)


def test_unreadable_trades_csv_blocks_safely(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    replay_dir = tmp_path / "replay"
    write_review_dir(review_dir)
    write_replay_dir(replay_dir, bad_trades_csv=True)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["plan_status"] == "blocked_unreadable_input"
    assert any(warning["warning_code"] == "replay_trades_csv_unreadable" for warning in warnings)


def test_source_review_hold_status_creates_available_with_caveat(tmp_path: Path) -> None:
    review_dir, replay_dir = build_fixture(tmp_path, review_payload=review_manifest(review_status="hold_for_more_validation"))
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    manifest = read_json(outputs["manifest"])
    rows = {row["plan_area"]: row for row in read_csv(outputs["plan"])}

    assert manifest["plan_status"] == "cost_sensitivity_plan_available_with_caveat"
    assert rows["replay_review_gate"]["artifact_status"] == "available_with_caveat"


def test_source_review_blocked_status_blocks_plan(tmp_path: Path) -> None:
    review_dir, replay_dir = build_fixture(
        tmp_path,
        review_payload=review_manifest(review_status="blocked_missing_required_artifact"),
    )
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["plan_status"] == "blocked_by_source_review_status"
    assert any(warning["warning_code"] == "source_review_status_blocked" for warning in warnings)


def test_manifest_counts_match_csvs_and_warnings(tmp_path: Path) -> None:
    review_dir, replay_dir = build_fixture(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["scenario_count"] == len(read_csv(outputs["scenarios"]))
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(
        1 for warning in warnings if warning["blocking_warning"].lower() == "true"
    )


def test_report_includes_no_replay_rerun_execution_db_mutation_optimization_approval_caveats(tmp_path: Path) -> None:
    review_dir, replay_dir = build_fixture(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "did not rerun the replay" in report
    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No order execution was performed." in report
    assert "No database mutation was performed." in report
    assert "No optimization or parameter search was performed." in report
    assert "not candidate approval" in report


def test_no_db_queries_are_performed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    review_dir, replay_dir = build_fixture(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("DB query should not be performed")

    monkeypatch.setattr(sqlite3, "connect", fail_if_called)
    plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    review_dir, replay_dir = build_fixture(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    plan.build_outputs(make_args(tmp_path, review_dir, replay_dir))
