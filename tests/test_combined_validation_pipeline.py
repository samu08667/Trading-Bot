from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess

import pytest

from scripts import run_combined_validation_pipeline as pipeline
from scripts import run_research_validation_pipeline
from scripts.research_costs import validate_orchestrator_cost_preflight


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
    },
    "GBPUSD": {
      "point_size": 0.00001,
      "fallback_spread_points": 1.0
    }
  }
}
""".strip(),
        encoding="utf-8",
    )


def make_combined_input(tmp_path: Path) -> Path:
    combined_input_dir = tmp_path / "combined_input"
    combined_input_dir.mkdir()
    (combined_input_dir / "combined_hypotheses_summary.csv").write_text(
        "combination_key,trades\nhour_session:London,100\n",
        encoding="utf-8",
    )
    return combined_input_dir


def make_valid_args(tmp_path: Path, *extra: str) -> object:
    cost_config = tmp_path / "costs.json"
    write_cost_config(cost_config)
    combined_input_dir = make_combined_input(tmp_path)
    return pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--combined-input-dir",
            str(combined_input_dir),
            "--combined-evaluations-dir",
            str(tmp_path / "combined_evaluations"),
            "--validation-output-dir",
            str(tmp_path / "validation"),
            "--scorecard-output-dir",
            str(tmp_path / "scorecard"),
            "--db-path",
            str(tmp_path / "trading_bot.db"),
            "--symbols",
            "EURUSD",
            "GBPUSD",
            "--cost-config",
            str(cost_config),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            *extra,
        ]
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open("r", encoding="utf-8")))


class FakeRunner:
    def __init__(self, *, fail_stage: str = "") -> None:
        self.fail_stage = fail_stage
        self.calls: list[pipeline.PipelineCommand] = []

    def __call__(self, command: pipeline.PipelineCommand) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if command.stage == self.fail_stage:
            return subprocess.CompletedProcess(command.args, 7, stdout="stage failed\n", stderr="synthetic failure\n")
        for expected_output in command.expected_outputs:
            path = Path(expected_output)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == ".csv":
                path.write_text("status\nok\n", encoding="utf-8")
            else:
                path.write_text(f"# {command.stage}\n", encoding="utf-8")
        return subprocess.CompletedProcess(command.args, 0, stdout=f"ok {command.stage}\n", stderr="")


def command_flag_value(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


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


def test_dry_run_creates_artifacts_without_executing_child_scripts(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")
    fake_runner = FakeRunner()

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert fake_runner.calls == []
    for key in ("manifest", "command_plan", "stage_results", "summary", "report", "warnings"):
        assert outputs[key].exists()
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "COMBINED_VALIDATION_PIPELINE_DRY_RUN_PLANNED"
    assert summary["pipeline_scope"] == "combined_validation_research_orchestration"
    assert summary["planned_stage_count"] == "3"
    assert summary["executed_stage_count"] == "0"
    assert int(summary["warnings_count"]) == (
        int(summary["blocking_warnings_count"]) + int(summary["non_blocking_warnings_count"])
    )


def test_command_plan_contains_expected_scripts_in_order(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)
    rows = read_csv(outputs["command_plan"])

    assert [row["stage"] for row in rows] == [
        "combined_evaluation",
        "yearly_validation",
        "final_feature_scorecard",
    ]
    assert [row["command_order"] for row in rows] == ["1", "2", "3"]
    assert [row["stage_name"] for row in rows] == [row["stage"] for row in rows]
    assert "evaluate_combined_hypotheses.py" in rows[0]["command"]
    assert "validate_hypotheses_by_year.py" in rows[1]["command"]
    assert "build_final_feature_scorecard.py" in rows[2]["command"]
    assert [row["stage_order"] for row in rows] == ["1", "2", "3"]


def test_execute_uses_fake_runner_and_completes(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")
    fake_runner = FakeRunner()

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert [command.stage for command in fake_runner.calls] == [
        "combined_evaluation",
        "yearly_validation",
        "final_feature_scorecard",
    ]
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "COMBINED_VALIDATION_PIPELINE_COMPLETED"
    assert summary["executed_stage_count"] == "3"
    stage_results = read_csv(outputs["stage_results"])
    assert all(row["status"] == "executed" for row in stage_results)
    assert [row["command_order"] for row in stage_results] == ["1", "2", "3"]
    assert [row["stage_name"] for row in stage_results] == [row["stage"] for row in stage_results]
    assert "error_message" in stage_results[0]
    assert Path(stage_results[0]["stdout_log"]).read_text(encoding="utf-8").startswith("ok combined_evaluation")


def test_failed_fake_stage_marks_failed_and_stops_by_default(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")
    fake_runner = FakeRunner(fail_stage="yearly_validation")

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert [command.stage for command in fake_runner.calls] == ["combined_evaluation", "yearly_validation"]
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "COMBINED_VALIDATION_PIPELINE_FAILED"
    assert summary["failed_stage_count"] == "1"
    assert summary["skipped_stage_count"] == "1"
    stage_results = read_csv(outputs["stage_results"])
    assert stage_results[1]["status"] == "failed"
    assert stage_results[2]["status"] == "skipped"


def test_logs_are_written_for_fake_execution(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")

    outputs = pipeline.run_pipeline(args, runner=FakeRunner())
    logs = sorted((outputs["output_dir"] / "logs").glob("*.log"))

    assert logs
    assert any(path.name == "combined_evaluation.stdout.log" for path in logs)
    assert any(path.name == "final_feature_scorecard.stderr.log" for path in logs)


def test_cost_preflight_rejects_net_none(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run", "--cost-mode", "none", "--return-mode", "net")

    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        pipeline.run_pipeline(args)


def test_cost_preflight_accepts_gross_none_without_cost_config(tmp_path: Path) -> None:
    combined_input_dir = make_combined_input(tmp_path)
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--combined-input-dir",
            str(combined_input_dir),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--cost-mode",
            "none",
            "--return-mode",
            "gross",
            "--dry-run",
        ]
    )

    outputs = pipeline.run_pipeline(args)

    assert outputs["summary"].exists()


def test_estimated_net_requires_valid_cost_config(tmp_path: Path) -> None:
    combined_input_dir = make_combined_input(tmp_path)
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--combined-input-dir",
            str(combined_input_dir),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--dry-run",
        ]
    )

    with pytest.raises(ValueError, match="Missing --cost-config"):
        pipeline.run_pipeline(args)


def test_invalid_cost_config_json_fails_clearly(tmp_path: Path) -> None:
    bad_config = tmp_path / "bad_costs.json"
    bad_config.write_text("{not json", encoding="utf-8")
    combined_input_dir = make_combined_input(tmp_path)
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--combined-input-dir",
            str(combined_input_dir),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--cost-config",
            str(bad_config),
            "--dry-run",
        ]
    )

    with pytest.raises(ValueError, match="Invalid cost config JSON"):
        pipeline.run_pipeline(args)


def test_existing_output_dir_requires_overwrite(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")
    output_dir = Path(args.output_root) / "run1"
    output_dir.mkdir(parents=True)

    with pytest.raises(FileExistsError, match="Output directory already exists"):
        pipeline.run_pipeline(args)


def test_overwrite_reuses_existing_output_dir(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run", "--overwrite")
    output_dir = Path(args.output_root) / "run1"
    output_dir.mkdir(parents=True)

    outputs = pipeline.run_pipeline(args)

    assert outputs["manifest"].exists()


def test_old_validation_pipeline_child_command_compatibility(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cost_config = tmp_path / "costs.json"
    write_cost_config(cost_config)
    combined_input_dir = make_combined_input(tmp_path)
    combined_evaluations_dir = tmp_path / "combined_evaluations"
    validation_output_dir = tmp_path / "validation"
    scorecard_output_dir = tmp_path / "scorecard"
    common_args = [
        "--run-id",
        "run1",
        "--combined-input-dir",
        str(combined_input_dir),
        "--combined-evaluations-dir",
        str(combined_evaluations_dir),
        "--validation-output-dir",
        str(validation_output_dir),
        "--scorecard-output-dir",
        str(scorecard_output_dir),
        "--db-path",
        str(tmp_path / "trading_bot.db"),
        "--symbols",
        "EURUSD",
        "GBPUSD",
        "--cost-config",
        str(cost_config),
        "--start-year",
        "2022",
        "--end-year",
        "2024",
        "--overwrite-validation",
    ]
    old_args = run_research_validation_pipeline.build_parser().parse_args(common_args)
    old_commands: list[list[str]] = []

    def fake_run_step(step_name: str, command: list[str]) -> None:
        old_commands.append([str(item) for item in command])
        if step_name.startswith("1."):
            selected = combined_evaluations_dir / "run1" / "long" / "selected_combined_hypotheses.csv"
            selected.parent.mkdir(parents=True, exist_ok=True)
            selected.write_text("combination_key\nhour_session:London\n", encoding="utf-8")

    monkeypatch.setattr(run_research_validation_pipeline, "run_step", fake_run_step)
    run_research_validation_pipeline.run_pipeline(old_args)

    new_args = pipeline.build_parser().parse_args(
        [
            *common_args,
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--dry-run",
        ]
    )
    cost_mode, return_mode = validate_orchestrator_cost_preflight(
        cost_mode=new_args.cost_mode,
        return_mode=new_args.return_mode,
        cost_config_path=new_args.cost_config,
    )
    new_commands, _stage_dirs = pipeline.build_stage_commands(
        args=new_args,
        run_id="run1",
        combined_input_dir=combined_input_dir,
        symbols=pipeline.normalize_symbols(new_args.symbols),
        timeframe=str(new_args.timeframe).upper(),
        cost_mode=cost_mode,
        return_mode=return_mode,
    )
    new_command_args = [list(command.args) for command in new_commands]

    assert [Path(command[1]).name for command in new_command_args] == [
        "evaluate_combined_hypotheses.py",
        "validate_hypotheses_by_year.py",
        "build_final_feature_scorecard.py",
    ]
    assert [Path(command[1]).name for command in old_commands] == [Path(command[1]).name for command in new_command_args]
    assert command_flag_value(old_commands[0], "--input-dir") == command_flag_value(new_command_args[0], "--input-dir")
    assert command_flag_value(old_commands[0], "--direction") == command_flag_value(new_command_args[0], "--direction")
    assert command_flag_value(old_commands[1], "--start-year") == command_flag_value(new_command_args[1], "--start-year")
    assert command_flag_value(old_commands[1], "--end-year") == command_flag_value(new_command_args[1], "--end-year")
    assert "--overwrite" in old_commands[1]
    assert "--overwrite" in new_command_args[1]
    assert "--overwrite" in old_commands[2]
    assert "--overwrite" in new_command_args[2]


def test_forbidden_actions_are_present_in_report(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)
    report = outputs["report"].read_text(encoding="utf-8")

    for action in pipeline.FORBIDDEN_ACTIONS:
        assert action in report


def test_no_broker_order_api_terms_in_wrapper_source() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    forbidden_terms = [
        "order_" + "send",
        "place_" + "order",
        "open_" + "position",
        "close_" + "position",
        "Meta" + "Trader5 " + "order " + "APIs",
    ]

    for term in forbidden_terms:
        assert term not in source
