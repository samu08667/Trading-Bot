from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess

import pytest

from scripts import run_hypothesis_discovery_pipeline as pipeline


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


def make_input_backtest_root(tmp_path: Path, direction: str = "long") -> Path:
    root = tmp_path / "backtests"
    (root / direction).mkdir(parents=True)
    return root


def make_valid_args(tmp_path: Path, *extra: str) -> object:
    cost_config = tmp_path / "costs.json"
    write_cost_config(cost_config)
    input_root = make_input_backtest_root(tmp_path)
    return pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--direction",
            "long",
            "--symbols",
            "EURUSD",
            "GBPUSD",
            "--timeframe",
            "M15",
            "--target-horizon",
            "10",
            "--input-backtest-root",
            str(input_root),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--combined-output-root",
            str(tmp_path / "combined_runs"),
            "--db-path",
            str(tmp_path / "trading_bot.db"),
            "--cost-config",
            str(cost_config),
            *extra,
        ]
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open("r", encoding="utf-8")))


class FakeRunner:
    def __init__(self, *, fail_stage: str = "", insufficient_stages: set[str] | None = None) -> None:
        self.fail_stage = fail_stage
        self.insufficient_stages = insufficient_stages or set()
        self.calls: list[pipeline.PipelineCommand] = []

    def __call__(self, command: pipeline.PipelineCommand) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if command.stage == self.fail_stage:
            return subprocess.CompletedProcess(command.args, 9, stdout="stage failed\n", stderr="synthetic failure\n")
        if command.stage in self.insufficient_stages:
            return subprocess.CompletedProcess(
                command.args,
                2,
                stdout=(
                    "Combined hypotheses backtest failed: "
                    "Need at least two usable select/watchlist hypotheses to combine.\n"
                ),
                stderr="",
            )
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


def test_help_describes_input_backtest_root_contract() -> None:
    help_text = pipeline.build_parser().format_help()

    assert "Root directory containing direction subfolders" in help_text
    assert "long/short." in help_text
    assert "--input-backtest-dir" in help_text


def test_input_backtest_root_resolves_parent_plus_direction(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    input_root = tmp_path / "backtests"
    direction_dir = input_root / "long"
    first_command = read_csv(outputs["command_plan"])[0]["command"]

    assert manifest["input_sources"]["input_backtest_root"] == str(input_root)
    assert manifest["input_sources"]["direction_input_dir"] == str(direction_dir)
    assert str(direction_dir) in first_command
    assert str(direction_dir / "long") not in first_command


def test_input_backtest_dir_resolves_direction_specific_folder_directly(tmp_path: Path) -> None:
    cost_config = tmp_path / "costs.json"
    write_cost_config(cost_config)
    input_root = make_input_backtest_root(tmp_path)
    direction_dir = input_root / "long"
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--direction",
            "long",
            "--symbols",
            "EURUSD",
            "--input-backtest-dir",
            str(direction_dir),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--combined-output-root",
            str(tmp_path / "combined_runs"),
            "--cost-config",
            str(cost_config),
            "--dry-run",
        ]
    )

    outputs = pipeline.run_pipeline(args)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    first_command = read_csv(outputs["command_plan"])[0]["command"]

    assert manifest["input_sources"]["input_backtest_root"] == str(input_root)
    assert manifest["input_sources"]["input_backtest_dir"] == str(direction_dir)
    assert manifest["input_sources"]["direction_input_dir"] == str(direction_dir)
    assert str(direction_dir) in first_command
    assert str(direction_dir / "long") not in first_command


def test_input_backtest_root_ending_with_direction_fails_clearly(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")
    args.input_backtest_root = Path(args.input_backtest_root) / "long"

    with pytest.raises(ValueError, match="Use --input-backtest-dir for a direction-specific folder"):
        pipeline.run_pipeline(args)


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
    assert summary["final_classification"] == "HYPOTHESIS_DISCOVERY_PIPELINE_DRY_RUN_PLANNED"
    assert summary["pipeline_scope"] == "hypothesis_discovery_research_orchestration"
    assert summary["planned_stage_count"] == "3"
    assert summary["planned_command_count"] == "4"
    assert summary["executed_command_count"] == "0"
    assert int(summary["warnings_count"]) == (
        int(summary["blocking_warnings_count"]) + int(summary["non_blocking_warnings_count"])
    )


def test_command_plan_contains_expected_child_scripts_and_per_symbol_combined_backtests(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)
    rows = read_csv(outputs["command_plan"])

    assert "command_order" in rows[0]
    assert "stage_order" in rows[0]
    assert "stage_name" in rows[0]
    assert [row["command_order"] for row in rows] == ["1", "2", "3", "4"]
    assert [row["stage_order"] for row in rows] == ["1", "2", "3", "3"]
    assert [row["stage_name"] for row in rows] == [row["stage"] for row in rows]
    assert "evaluate_backtest_results.py" in rows[0]["command"]
    assert "select_research_hypotheses.py" in rows[1]["command"]
    combined_rows = rows[2:]
    assert len(combined_rows) == 2
    assert all("backtest_combined_hypotheses.py" in row["command"] for row in combined_rows)
    assert all(row["stage_order"] == "3" for row in combined_rows)
    assert [row["symbol"] for row in combined_rows] == ["EURUSD", "GBPUSD"]


def test_combined_output_dirs_are_run_scoped(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)
    rows = read_csv(outputs["command_plan"])
    combined_output_dir = tmp_path / "combined_runs" / "run1" / "long"

    assert read_csv(outputs["summary"])[0]["combined_output_dir"] == str(combined_output_dir)
    assert str(combined_output_dir / "EURUSD_M15_h10") == rows[2]["planned_output_dir"]
    assert str(combined_output_dir / "GBPUSD_M15_h10") == rows[3]["planned_output_dir"]


def test_manifest_includes_planned_commands_and_combined_output_dir(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["combined_output_dir"] == str(tmp_path / "combined_runs" / "run1" / "long")
    assert manifest["planned_stages"] == ["backtest_evaluation", "hypothesis_selection", "combined_backtest"]
    assert len(manifest["planned_commands"]) == 4
    assert [row["command_order"] for row in manifest["planned_commands"]] == [1, 2, 3, 4]
    assert [row["stage_order"] for row in manifest["planned_commands"]] == [1, 2, 3, 3]


def test_fake_runner_execution_can_complete(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")
    fake_runner = FakeRunner()

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert [command.stage for command in fake_runner.calls] == [
        "backtest_evaluation",
        "hypothesis_selection",
        "combined_backtest_EURUSD",
        "combined_backtest_GBPUSD",
    ]
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "HYPOTHESIS_DISCOVERY_PIPELINE_COMPLETED"
    assert summary["executed_command_count"] == "4"
    stage_results = read_csv(outputs["stage_results"])
    assert all(row["status"] == "executed" for row in stage_results)
    assert [row["command_order"] for row in stage_results] == ["1", "2", "3", "4"]
    assert [row["stage_order"] for row in stage_results] == ["1", "2", "3", "3"]
    assert [row["stage_name"] for row in stage_results] == [row["stage"] for row in stage_results]
    assert "error_message" in stage_results[0]
    assert Path(stage_results[0]["stdout_log"]).read_text(encoding="utf-8").startswith("ok backtest_evaluation")


def test_fake_runner_failure_stops_by_default(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")
    fake_runner = FakeRunner(fail_stage="hypothesis_selection")

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert [command.stage for command in fake_runner.calls] == ["backtest_evaluation", "hypothesis_selection"]
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "HYPOTHESIS_DISCOVERY_PIPELINE_FAILED"
    assert summary["failed_command_count"] == "1"
    assert summary["skipped_command_count"] == "2"
    stage_results = read_csv(outputs["stage_results"])
    assert stage_results[1]["status"] == "failed"
    assert stage_results[2]["status"] == "skipped"
    assert stage_results[3]["status"] == "skipped"
    assert [row["command_order"] for row in stage_results] == ["1", "2", "3", "4"]
    assert [row["stage_order"] for row in stage_results] == ["1", "2", "3", "3"]


def test_single_symbol_insufficient_hypotheses_gets_clear_research_outcome(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--symbols", "XAUUSD", "--execute")
    fake_runner = FakeRunner(insufficient_stages={"combined_backtest_XAUUSD"})

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert [command.stage for command in fake_runner.calls] == [
        "backtest_evaluation",
        "hypothesis_selection",
        "combined_backtest_XAUUSD",
    ]
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "HYPOTHESIS_DISCOVERY_PIPELINE_STOPPED_NO_COMBINABLE_HYPOTHESES"
    assert summary["failed_command_count"] == "1"
    assert summary["blocking_warnings_count"] == "1"
    stage_results = read_csv(outputs["stage_results"])
    assert [row["command_order"] for row in stage_results] == ["1", "2", "3"]
    assert [row["stage_order"] for row in stage_results] == ["1", "2", "3"]
    assert stage_results[2]["status"] == "failed"
    assert stage_results[2]["failure_reason"] == "Insufficient selected/watchlist hypotheses for combined backtest."
    stdout_log = Path(stage_results[2]["stdout_log"]).read_text(encoding="utf-8")
    assert "Need at least two usable select/watchlist hypotheses to combine." in stdout_log
    warnings = read_csv(outputs["warnings"])
    assert any(
        row["warning_code"] == "insufficient_selected_hypotheses_for_combined_backtest"
        and row["blocking"] == "true"
        for row in warnings
    )


def test_multi_symbol_insufficient_hypotheses_completes_with_warning(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--symbols", "EURUSD", "XAUUSD", "--execute")
    fake_runner = FakeRunner(insufficient_stages={"combined_backtest_XAUUSD"})

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert [command.stage for command in fake_runner.calls] == [
        "backtest_evaluation",
        "hypothesis_selection",
        "combined_backtest_EURUSD",
        "combined_backtest_XAUUSD",
    ]
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "HYPOTHESIS_DISCOVERY_PIPELINE_COMPLETED_WITH_UNCOMBINABLE_SYMBOLS"
    assert summary["executed_command_count"] == "3"
    assert summary["failed_command_count"] == "1"
    assert summary["skipped_command_count"] == "0"
    assert summary["blocking_warnings_count"] == "0"
    stage_results = read_csv(outputs["stage_results"])
    assert [row["command_order"] for row in stage_results] == ["1", "2", "3", "4"]
    assert [row["stage_order"] for row in stage_results] == ["1", "2", "3", "3"]
    assert stage_results[2]["status"] == "executed"
    assert stage_results[3]["status"] == "failed"
    assert stage_results[3]["failure_reason"] == "Insufficient selected/watchlist hypotheses for combined backtest."
    warnings = read_csv(outputs["warnings"])
    assert any(
        row["warning_code"] == "insufficient_selected_hypotheses_for_combined_backtest"
        and row["blocking"] == "false"
        for row in warnings
    )


def test_cost_preflight_rejects_net_none(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run", "--cost-mode", "none", "--return-mode", "net")

    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        pipeline.run_pipeline(args)


def test_cost_preflight_accepts_gross_none_without_cost_config(tmp_path: Path) -> None:
    input_root = make_input_backtest_root(tmp_path)
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--input-backtest-root",
            str(input_root),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--combined-output-root",
            str(tmp_path / "combined_runs"),
            "--symbols",
            "EURUSD",
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
    input_root = make_input_backtest_root(tmp_path)
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--input-backtest-root",
            str(input_root),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--combined-output-root",
            str(tmp_path / "combined_runs"),
            "--dry-run",
        ]
    )

    with pytest.raises(ValueError, match="Missing --cost-config"):
        pipeline.run_pipeline(args)


def test_invalid_cost_config_json_fails_clearly(tmp_path: Path) -> None:
    bad_config = tmp_path / "bad_costs.json"
    bad_config.write_text("{not json", encoding="utf-8")
    input_root = make_input_backtest_root(tmp_path)
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--input-backtest-root",
            str(input_root),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--combined-output-root",
            str(tmp_path / "combined_runs"),
            "--cost-config",
            str(bad_config),
            "--dry-run",
        ]
    )

    with pytest.raises(ValueError, match="Invalid cost config JSON"):
        pipeline.run_pipeline(args)


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
