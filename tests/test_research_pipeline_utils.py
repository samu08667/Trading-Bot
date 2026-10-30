from __future__ import annotations

import csv
import inspect
import json
from pathlib import Path
import subprocess

import pytest

from scripts import research_pipeline_utils as utils


def command() -> utils.PipelineCommand:
    return utils.PipelineCommand(
        stage="unit test stage",
        args=["python", "script.py", "--flag", "value with spaces"],
        cwd=Path("."),
        expected_outputs=[Path("reports/out.csv")],
        description="planned unit test command",
    )


def result(status: str) -> utils.PipelineCommandResult:
    return utils.PipelineCommandResult(stage=status, args=["python"], status=status)


def test_pipeline_command_renders_without_execution() -> None:
    rendered = utils.render_command(command())

    assert "python" in rendered
    assert "script.py" in rendered
    assert "--flag" in rendered
    assert "value with spaces" in rendered


def test_run_command_dry_run_does_not_call_runner() -> None:
    calls: list[utils.PipelineCommand] = []

    def fake_runner(pipeline_command: utils.PipelineCommand) -> subprocess.CompletedProcess[str]:
        calls.append(pipeline_command)
        return subprocess.CompletedProcess(pipeline_command.args, 0, stdout="unexpected", stderr="")

    run_result = utils.run_command(command(), runner=fake_runner, dry_run=True)

    assert calls == []
    assert run_result.status == "dry_run"
    assert run_result.returncode is None


def test_run_command_uses_injected_runner() -> None:
    calls: list[utils.PipelineCommand] = []

    def fake_runner(pipeline_command: utils.PipelineCommand) -> subprocess.CompletedProcess[str]:
        calls.append(pipeline_command)
        return subprocess.CompletedProcess(pipeline_command.args, 0, stdout="ok", stderr="")

    run_result = utils.run_command(command(), runner=fake_runner)

    assert calls == [command()]
    assert run_result.status == "success"
    assert run_result.returncode == 0


def test_successful_command_result_gets_success_status() -> None:
    run_result = utils.run_command(
        command(),
        runner=lambda pipeline_command: subprocess.CompletedProcess(pipeline_command.args, 0, stdout="", stderr=""),
    )

    assert run_result.status == "success"
    assert run_result.error_message == ""


def test_nonzero_command_result_gets_failed_status() -> None:
    run_result = utils.run_command(
        command(),
        runner=lambda pipeline_command: subprocess.CompletedProcess(
            pipeline_command.args,
            2,
            stdout="",
            stderr="bad",
        ),
    )

    assert run_result.status == "failed"
    assert run_result.returncode == 2
    assert "exit code 2" in run_result.error_message


def test_stdout_and_stderr_logs_are_written(tmp_path: Path) -> None:
    run_result = utils.run_command(
        command(),
        runner=lambda pipeline_command: subprocess.CompletedProcess(
            pipeline_command.args,
            0,
            stdout="hello\n",
            stderr="warn\n",
        ),
        log_dir=tmp_path / "logs",
    )

    assert run_result.stdout_log is not None
    assert run_result.stderr_log is not None
    assert Path(run_result.stdout_log).read_text(encoding="utf-8") == "hello\n"
    assert Path(run_result.stderr_log).read_text(encoding="utf-8") == "warn\n"


def test_ensure_output_dir_creates_missing_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "new_output"

    returned = utils.ensure_output_dir(output_dir)

    assert returned == output_dir
    assert output_dir.is_dir()


def test_ensure_output_dir_refuses_existing_directory_without_overwrite(tmp_path: Path) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()

    with pytest.raises(FileExistsError, match="overwrite=True"):
        utils.ensure_output_dir(output_dir)


def test_ensure_output_dir_allows_existing_directory_with_overwrite(tmp_path: Path) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    marker = output_dir / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    returned = utils.ensure_output_dir(output_dir, overwrite=True)

    assert returned == output_dir
    assert marker.read_text(encoding="utf-8") == "keep"


def test_write_manifest_adds_schema_version_and_generated_at(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"

    returned = utils.write_manifest(manifest_path, {"run_id": "run1"})
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert returned == manifest_path
    assert payload["run_id"] == "run1"
    assert payload["schema_version"] == utils.PIPELINE_MANIFEST_SCHEMA_VERSION
    assert payload["generated_at"]


def test_write_manifest_respects_overwrite_false(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    utils.write_manifest(manifest_path, {"run_id": "run1"})

    with pytest.raises(FileExistsError, match="overwrite=True"):
        utils.write_manifest(manifest_path, {"run_id": "run2"})


def test_aggregate_status_handles_terminal_states() -> None:
    assert utils.aggregate_status([result("success")]) == "success"
    assert utils.aggregate_status([result("failed")]) == "failed"
    assert utils.aggregate_status([result("dry_run")]) == "dry_run"
    assert utils.aggregate_status([result("skipped")]) == "skipped"
    assert utils.aggregate_status([result("success"), result("failed")]) == "partial"
    assert utils.aggregate_status([result("success"), result("skipped")]) == "partial"
    assert utils.aggregate_status([result("partial")]) == "partial"
    assert utils.aggregate_status([]) == "skipped"


def test_write_command_plan_csv_writes_expected_columns(tmp_path: Path) -> None:
    plan_path = tmp_path / "command_plan.csv"

    returned = utils.write_command_plan_csv(plan_path, [command()])
    rows = list(csv.DictReader(plan_path.open("r", encoding="utf-8")))

    assert returned == plan_path
    assert rows
    assert rows[0]["stage"] == "unit test stage"
    assert rows[0]["heavy"] == "false"
    assert rows[0]["required"] == "true"
    assert rows[0]["description"] == "planned unit test command"
    assert rows[0]["expected_outputs"] == "reports\\out.csv" or rows[0]["expected_outputs"] == "reports/out.csv"
    assert list(rows[0]) == utils.COMMAND_PLAN_FIELDNAMES


def test_helpers_do_not_require_domain_specific_metadata() -> None:
    forbidden_parameters = {
        "symbol",
        "symbols",
        "timeframe",
        "direction",
        "target_family",
        "regime",
        "candidate_id",
        "candidate_scope",
    }
    public_callables = [
        utils.PipelineCommand,
        utils.PipelineCommandResult,
        utils.render_command,
        utils.run_command,
        utils.ensure_output_dir,
        utils.write_manifest,
        utils.aggregate_status,
        utils.write_command_plan_csv,
        utils.build_run_paths,
        utils.require_existing_path,
    ]

    for item in public_callables:
        parameters = set(inspect.signature(item).parameters)
        assert not (parameters & forbidden_parameters), item


def test_module_does_not_import_or_call_broker_execution_apis() -> None:
    source = Path(utils.__file__).read_text(encoding="utf-8")
    forbidden_terms = [
        "MetaTrader5",
        "order_send",
        "place_order",
        "open_position",
        "close_position",
    ]

    for term in forbidden_terms:
        assert term not in source
