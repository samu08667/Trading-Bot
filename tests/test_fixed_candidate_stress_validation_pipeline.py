from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess

import pytest

from scripts import run_fixed_candidate_stress_validation_pipeline as pipeline


def write_cost_config(path: Path) -> None:
    path.write_text(
        """
{
  "default": {
    "slippage_bps_round_trip": 0.1,
    "commission_bps_round_trip": 0.2,
    "fallback_spread_points": 1.0
  },
  "symbols": {
    "EURUSD": {
      "point_size": 0.00001,
      "fallback_spread_points": 1.0
    }
  }
}
""".strip(),
        encoding="utf-8",
    )


def make_valid_args(tmp_path: Path, *extra: str) -> object:
    db_path = tmp_path / "trading_bot.db"
    db_path.write_text("", encoding="utf-8")
    cost_config = tmp_path / "costs.json"
    stress_cost_config = tmp_path / "stress_costs.json"
    write_cost_config(cost_config)
    write_cost_config(stress_cost_config)
    return pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--symbol",
            "EURUSD",
            "--direction",
            "long",
            "--timeframe",
            "M15",
            "--target-horizon",
            "10",
            "--target-family",
            "long_tp_2atr_sl_1atr_hit_first",
            "--regime-column",
            "hour_session",
            "--regime-value",
            "London",
            "--tp-atr",
            "2",
            "--sl-atr",
            "1",
            "--feature-condition",
            "tick_volume_percentile_100 >= 0.8",
            "--db-path",
            str(db_path),
            "--cost-config",
            str(cost_config),
            "--stress-cost-config",
            str(stress_cost_config),
            "--stress-spread-policy",
            "max_row_or_fallback",
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--stress-output-root",
            str(tmp_path / "stress_outputs"),
            *extra,
        ]
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open("r", encoding="utf-8")))


class FakeRunner:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[pipeline.PipelineCommand] = []

    def __call__(self, command: pipeline.PipelineCommand) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if self.fail:
            return subprocess.CompletedProcess(command.args, 5, stdout="stage failed\n", stderr="synthetic failure\n")
        for expected_output in command.expected_outputs:
            path = Path(expected_output)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == ".csv":
                path.write_text("status\nok\n", encoding="utf-8")
            else:
                path.write_text(f"# {command.stage}\n", encoding="utf-8")
        return subprocess.CompletedProcess(command.args, 0, stdout=f"ok {command.stage}\n", stderr="")


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        pipeline.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_no_mode_selected_fails_clearly(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path)

    with pytest.raises(ValueError, match="Choose either --dry-run or --execute"):
        pipeline.run_pipeline(args)


def test_both_modes_selected_fails_clearly(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run", "--execute")

    with pytest.raises(ValueError, match="Choose only one"):
        pipeline.run_pipeline(args)


def test_dry_run_writes_artifacts_without_executing_child_scripts(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")
    fake_runner = FakeRunner()

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert fake_runner.calls == []
    for key in ("manifest", "command_plan", "stage_results", "summary", "report", "warnings"):
        assert outputs[key].exists()
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "FIXED_CANDIDATE_STRESS_VALIDATION_PIPELINE_DRY_RUN_PLANNED"
    assert summary["pipeline_scope"] == "fixed_candidate_stress_validation_research_orchestration"
    assert summary["planned_stage_count"] == "1"
    assert summary["executed_stage_count"] == "0"
    assert int(summary["warnings_count"]) == (
        int(summary["blocking_warnings_count"]) + int(summary["non_blocking_warnings_count"])
    )


def test_command_plan_includes_stress_validation_child_and_ordering(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)
    rows = read_csv(outputs["command_plan"])

    assert len(rows) == 1
    assert rows[0]["command_order"] == "1"
    assert rows[0]["stage_order"] == "1"
    assert rows[0]["stage_name"] == "stress_validation"
    assert "validate_regime_candidate_stress.py" in rows[0]["command"]
    assert "--condition" in rows[0]["command"]
    assert str(outputs["stress_output_dir"]) == rows[0]["planned_output_dir"]


def test_manifest_records_planned_command_and_stress_output_dir(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["planned_stages"] == ["stress_validation"]
    assert manifest["stress_output_dir"] == str(tmp_path / "stress_outputs" / "run1")
    assert manifest["pipeline_scope"] == "fixed_candidate_stress_validation_research_orchestration"
    assert manifest["planned_commands"][0]["command_order"] == 1
    assert manifest["planned_commands"][0]["stage_order"] == 1


def test_fake_runner_execution_success_writes_completed_summary_and_logs(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")
    fake_runner = FakeRunner()

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert [command.stage for command in fake_runner.calls] == ["stress_validation"]
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "FIXED_CANDIDATE_STRESS_VALIDATION_PIPELINE_COMPLETED"
    assert summary["executed_stage_count"] == "1"
    stage_results = read_csv(outputs["stage_results"])
    assert stage_results[0]["stage_name"] == "stress_validation"
    assert stage_results[0]["command_order"] == "1"
    assert stage_results[0]["stage_order"] == "1"
    assert stage_results[0]["status"] == "executed"
    assert Path(stage_results[0]["stdout_log"]).read_text(encoding="utf-8").startswith("ok stress_validation")


def test_fake_runner_failure_writes_failed_summary(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")
    fake_runner = FakeRunner(fail=True)

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "FIXED_CANDIDATE_STRESS_VALIDATION_PIPELINE_FAILED"
    assert summary["failed_stage_count"] == "1"
    assert summary["blocking_warnings_count"] == "1"
    stage_results = read_csv(outputs["stage_results"])
    assert stage_results[0]["status"] == "failed"
    assert "exit code 5" in stage_results[0]["error_message"]


def test_no_stop_on_failure_is_accepted_for_single_stage_failure(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute", "--no-stop-on-failure")
    fake_runner = FakeRunner(fail=True)

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert len(fake_runner.calls) == 1
    assert read_csv(outputs["summary"])[0]["final_classification"] == (
        "FIXED_CANDIDATE_STRESS_VALIDATION_PIPELINE_FAILED"
    )


def test_missing_db_path_fails_early(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")
    args.db_path = tmp_path / "missing.db"

    with pytest.raises(FileNotFoundError, match="--db-path does not exist"):
        pipeline.run_pipeline(args)


def test_invalid_cost_config_fails_early(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")
    bad_config = tmp_path / "bad_costs.json"
    bad_config.write_text("{not json", encoding="utf-8")
    args.cost_config = bad_config

    with pytest.raises(ValueError, match="Invalid --cost-config"):
        pipeline.run_pipeline(args)


def test_missing_stress_cost_config_fails_early_when_provided(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")
    args.stress_cost_config = tmp_path / "missing_stress_costs.json"

    with pytest.raises(FileNotFoundError, match="--stress-cost-config does not exist"):
        pipeline.run_pipeline(args)


def test_existing_output_dir_requires_overwrite(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")
    (tmp_path / "pipeline_outputs" / "run1").mkdir(parents=True)

    with pytest.raises(FileExistsError, match="Output directory already exists"):
        pipeline.run_pipeline(args)


def test_report_includes_research_only_caveat_and_forbidden_actions(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "offline fixed-candidate stress validation only" in report
    for action in pipeline.FORBIDDEN_ACTIONS:
        assert action in report


def test_no_broker_order_api_terms_in_wrapper_source() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    forbidden_terms = [
        "order_" + "send",
        "place_" + "order",
        "open_" + "position",
        "close_" + "position",
    ]

    for term in forbidden_terms:
        assert term not in source
