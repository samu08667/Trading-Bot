from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_replay_cost_sensitivity_review as review


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
    payload: dict[str, object] = {
        "run_id": "fixture_cost_plan",
        "plan_status": "cost_sensitivity_plan_available",
        "scenario_count": 5,
        "scenario_labels": ["base", "mild", "medium", "severe", "stress"],
        "source_trades_closed": 437,
        "source_total_R": 258.80477002324454,
        "source_average_R": 0.5922305950188662,
        "timeout_trade_count": 147,
        "timeout_gross_average_R": 0.1449304083213955,
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
        "no_stress_validation_executed": True,
        "no_walk_forward_validation_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
    }
    payload.update(overrides)
    return payload


def scenario_row(
    label: str,
    cost: float,
    total: float,
    average: float,
    drawdown: float,
    status: str,
) -> dict[str, object]:
    return {
        "run_id": "fixture_cost_plan",
        "scenario_label": label,
        "extra_cost_R_per_trade": cost,
        "trades_closed": 437,
        "gross_total_R": 258.80477002324454,
        "total_extra_cost_R": 437 * cost,
        "adjusted_total_R": total,
        "adjusted_average_R": average,
        "adjusted_median_R": average,
        "adjusted_min_R": -1.0 - cost,
        "adjusted_max_R": 1.5 - cost,
        "adjusted_win_rate_R_positive": 0.69,
        "adjusted_trades_positive_count": 300,
        "adjusted_trades_negative_count": 137,
        "adjusted_trades_zero_count": 0,
        "adjusted_max_drawdown_R": drawdown,
        "adjusted_longest_loss_streak": 5,
        "adjusted_longest_win_streak": 13,
        "scenario_status": status,
        "caveat": "fixed_extra_cost_estimate_only",
    }


def scenario_rows(*, medium_total: float = 215.1047700232445, stress_total: float = 127.70477002324452) -> list[dict[str, object]]:
    medium_average = medium_total / 437
    stress_average = stress_total / 437
    return [
        scenario_row("base", 0.00, 258.80477002324454, 0.5922305950188662, 4.34301958307006, "robust_under_scenario"),
        scenario_row("mild", 0.05, 236.95477002324452, 0.5422305950188662, 4.643019583070128, "robust_under_scenario"),
        scenario_row(
            "medium",
            0.10,
            medium_total,
            medium_average,
            5.36811706034452,
            "robust_under_scenario" if medium_total > 0 and medium_average > 0.25 else "positive_but_degraded",
        ),
        scenario_row("severe", 0.20, 171.40477002324454, 0.39223059501886626, 8.932362818960721, "fragile_under_scenario"),
        scenario_row(
            "stress",
            0.30,
            stress_total,
            stress_average,
            13.832362818960723,
            "fragile_under_scenario" if stress_total > 0 else "negative_under_scenario",
        ),
    ]


def outcome_rows(*, stress_timeout_average: float = -0.15506959167860448) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    timeout_averages = {
        "base": 0.1449304083213955,
        "mild": 0.09493040832139549,
        "medium": 0.044930408321395505,
        "severe": -0.0550695916786045,
        "stress": stress_timeout_average,
    }
    costs = {"base": 0.0, "mild": 0.05, "medium": 0.10, "severe": 0.20, "stress": 0.30}
    for label, cost in costs.items():
        rows.extend(
            [
                {
                    "run_id": "fixture_cost_plan",
                    "scenario_label": label,
                    "extra_cost_R_per_trade": cost,
                    "exit_reason": "paper_tp_hit",
                    "trade_count": 211,
                    "gross_total_R": 316.5,
                    "gross_average_R": 1.5,
                    "adjusted_total_R": 211 * (1.5 - cost),
                    "adjusted_average_R": 1.5 - cost,
                    "adjusted_win_rate_R_positive": 1.0,
                    "caveat": "outcome_sensitivity_estimate_only",
                },
                {
                    "run_id": "fixture_cost_plan",
                    "scenario_label": label,
                    "extra_cost_R_per_trade": cost,
                    "exit_reason": "paper_sl_hit",
                    "trade_count": 79,
                    "gross_total_R": -79.0,
                    "gross_average_R": -1.0,
                    "adjusted_total_R": 79 * (-1.0 - cost),
                    "adjusted_average_R": -1.0 - cost,
                    "adjusted_win_rate_R_positive": 0.0,
                    "caveat": "outcome_sensitivity_estimate_only",
                },
                {
                    "run_id": "fixture_cost_plan",
                    "scenario_label": label,
                    "extra_cost_R_per_trade": cost,
                    "exit_reason": "paper_timeout",
                    "trade_count": 147,
                    "gross_total_R": 21.30477002324514,
                    "gross_average_R": 0.1449304083213955,
                    "adjusted_total_R": 147 * timeout_averages[label],
                    "adjusted_average_R": timeout_averages[label],
                    "adjusted_win_rate_R_positive": 0.51,
                    "caveat": "timeout_bucket_negative_under_extra_cost"
                    if timeout_averages[label] < 0
                    else "outcome_sensitivity_estimate_only",
                },
            ]
        )
    return rows


def write_plan_dir(
    path: Path,
    *,
    manifest: dict[str, object] | None = None,
    scenarios: list[dict[str, object]] | None = None,
    outcomes: list[dict[str, object]] | None = None,
    missing_manifest: bool = False,
    missing_scenarios: bool = False,
    missing_outcomes: bool = False,
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not missing_manifest:
        write_json(path / review.SOURCE_MANIFEST, manifest if manifest is not None else source_manifest())
    (path / review.SOURCE_REPORT).write_text("# Cost sensitivity plan\n", encoding="utf-8")
    write_csv(path / review.SOURCE_PLAN, review.REVIEW_FIELDNAMES, [])
    if not missing_scenarios:
        rows = scenarios if scenarios is not None else scenario_rows()
        write_csv(path / review.SOURCE_SCENARIOS, list(rows[0].keys()), rows)
    if not missing_outcomes:
        rows = outcomes if outcomes is not None else outcome_rows()
        write_csv(path / review.SOURCE_OUTCOMES, list(rows[0].keys()), rows)
    write_csv(path / review.SOURCE_WARNINGS, review.WARNING_FIELDNAMES, [])


def make_args(tmp_path: Path, plan_dir: Path) -> object:
    return review.build_parser().parse_args(
        [
            "--run-id",
            "unit_cost_sensitivity_review",
            "--cost-sensitivity-plan-dir",
            str(plan_dir),
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
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir)
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))

    assert outputs["review"].exists()
    assert outputs["scenarios"].exists()
    assert outputs["outcomes"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_valid_cost_plan_continues_with_cost_caveat(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir)
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "continue_paper_validation_with_cost_caveat"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_recent_period_holdout_review"


def test_medium_weak_scenario_holds_for_cost_model_review(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir, scenarios=scenario_rows(medium_total=90.0))
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "hold_for_cost_model_review"


def test_stress_negative_scenario_holds_for_cost_model_review(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir, scenarios=scenario_rows(stress_total=-1.0))
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "hold_for_cost_model_review"
    assert manifest["negative_under_scenario_count"] == 1


def test_missing_manifest_blocks(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir, missing_manifest=True)
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_missing_required_artifact"
    assert manifest["missing_source_artifact_count"] >= 1


def test_missing_scenario_csv_blocks(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir, missing_scenarios=True)
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["review_status"] == "blocked_missing_required_artifact"
    assert any(warning["warning_code"] == f"source_{review.SOURCE_SCENARIOS}_missing" for warning in warnings)


def test_missing_outcome_csv_blocks(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir, missing_outcomes=True)
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["review_status"] == "blocked_missing_required_artifact"
    assert any(warning["warning_code"] == f"source_{review.SOURCE_OUTCOMES}_missing" for warning in warnings)


def test_source_plan_blocked_status_blocks_review(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir, manifest=source_manifest(plan_status="blocked_missing_required_artifact"))
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_by_source_plan_status"


def test_timeout_severe_stress_negative_is_detected(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir)
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    manifest = read_json(outputs["manifest"])
    outcomes = read_csv(outputs["outcomes"])

    assert manifest["timeout_negative_under_severe"] is True
    assert manifest["timeout_negative_under_stress"] is True
    assert any(row["outcome_review_label"] == "timeout_bucket_fragile_under_severe_stress" for row in outcomes)


def test_drawdown_expansion_ratio_is_computed(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir)
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["stress_drawdown_expansion_ratio"] == pytest.approx(13.832362818960723 / 4.34301958307006)


def test_manifest_counts_match_csvs_and_warnings(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir)
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["scenario_row_count"] == len(read_csv(outputs["scenarios"]))
    assert manifest["outcome_row_count"] == len(read_csv(outputs["outcomes"]))
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(
        1 for warning in warnings if warning["blocking_warning"].lower() == "true"
    )


def test_report_includes_no_rerun_execution_db_mutation_optimization_future_proof_approval_caveats(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir)
    outputs = review.build_outputs(make_args(tmp_path, plan_dir))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "did not rerun the replay" in report
    assert "did not rerun the cost sensitivity plan" in report
    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No order execution was performed." in report
    assert "No database mutation was performed." in report
    assert "No optimization or parameter search was performed." in report
    assert "not future-performance proof" in report
    assert "not candidate approval or demo broker readiness" in report


def test_no_db_queries_are_performed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("DB query should not be performed")

    monkeypatch.setattr(sqlite3, "connect", fail_if_called)
    review.build_outputs(make_args(tmp_path, plan_dir))


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan_dir = tmp_path / "plan"
    write_plan_dir(plan_dir)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    review.build_outputs(make_args(tmp_path, plan_dir))
