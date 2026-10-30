from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess

import pytest

from scripts import run_candidate_audit_pipeline as pipeline


READY_LABELS = {
    "candidate_review": "CANDIDATE_REVIEW_READY_FOR_RULE_REPLAY",
    "rule_replay": "RULE_REPLAY_MATCHED_STRESS_VALIDATION",
    "rule_review": "RULE_REVIEW_READY_FOR_CONTROLLED_EXPANSION",
    "controlled_expansion": "CONTROLLED_EXPANSION_READY_FOR_GATE_DECISION",
    "gate_decision": "GATE_DECISION_COMPLETED",
}

TIMEOUT_RETAINED_LABELS = {
    **READY_LABELS,
    "controlled_expansion": "CONTROLLED_EXPANSION_RETAINED_FOR_TIMEOUT_REVIEW",
    "timeout_audit": "TIMEOUT_AUDIT_RETAINED_FOR_REVIEW",
    "timeout_root_cause": "TIMEOUT_ROOT_CAUSE_RETAINED_FOR_REVIEW",
    "timeout_sequence_drilldown": "TIMEOUT_SEQUENCE_RETAINED_FOR_REVIEW",
    "timeout_policy_sensitivity": "TIMEOUT_POLICY_SENSITIVITY_REJECTED",
}


def write_cost_config(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "default": {
                    "slippage_bps_round_trip": 0.0,
                    "commission_bps_round_trip": 0.0,
                    "fallback_spread_points": 12,
                },
                "symbols": {
                    "EURUSD": {
                        "point_size": 0.00001,
                        "fallback_spread_points": 12,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def make_inputs(tmp_path: Path) -> dict[str, Path]:
    stress_output_dir = tmp_path / "stress_outputs"
    stress_output_dir.mkdir()
    db_path = tmp_path / "research.sqlite"
    db_path.write_text("", encoding="utf-8")
    return {
        "stress_output_dir": stress_output_dir,
        "db_path": db_path,
        "cost_config": write_cost_config(tmp_path / "cost_config.json"),
        "stress_cost_config": write_cost_config(tmp_path / "stress_cost_config.json"),
        "output_root": tmp_path / "reports",
    }


def parse_execute_args(tmp_path: Path, *extra: str) -> tuple[object, dict[str, Path]]:
    paths = make_inputs(tmp_path)
    argv = [
        "--execute",
        "--stress-output-dir",
        str(paths["stress_output_dir"]),
        "--db-path",
        str(paths["db_path"]),
        "--cost-config",
        str(paths["cost_config"]),
        "--stress-cost-config",
        str(paths["stress_cost_config"]),
        "--run-id",
        "unit_execution_run",
        "--output-root",
        str(paths["output_root"]),
    ]
    argv.extend(extra)
    return pipeline.build_parser().parse_args(argv), paths


def summary_path_for(command: pipeline.PipelineCommand) -> Path:
    for expected_output in command.expected_outputs:
        path = Path(expected_output)
        if path.name.endswith("_summary.csv"):
            return path
    raise AssertionError(f"Missing summary path for {command.stage}")


class FakeRunner:
    def __init__(
        self,
        *,
        labels: dict[str, str] | None = None,
        returncodes: dict[str, int] | None = None,
        missing_summaries: set[str] | None = None,
        blocking_warnings: set[str] | None = None,
    ) -> None:
        self.labels = labels or READY_LABELS
        self.returncodes = returncodes or {}
        self.missing_summaries = missing_summaries or set()
        self.blocking_warnings = blocking_warnings or set()
        self.calls: list[pipeline.PipelineCommand] = []

    def __call__(self, command: pipeline.PipelineCommand) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        returncode = self.returncodes.get(command.stage, 0)
        if returncode == 0 and command.stage not in self.missing_summaries:
            summary_path = summary_path_for(command)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            blocking_count = 1 if command.stage in self.blocking_warnings else 0
            with summary_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "final_classification",
                        "decision_scope",
                        "warnings_count",
                        "blocking_warnings_count",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "final_classification": self.labels.get(command.stage, f"{command.stage.upper()}_COMPLETED"),
                        "decision_scope": command.stage,
                        "warnings_count": blocking_count,
                        "blocking_warnings_count": blocking_count,
                    }
                )
        return subprocess.CompletedProcess(
            args=list(command.args),
            returncode=returncode,
            stdout=f"{command.stage} stdout\n",
            stderr=f"{command.stage} stderr\n" if returncode else "",
        )


def read_summary(outputs: dict[str, Path]) -> dict[str, str]:
    rows = list(csv.DictReader(outputs["summary"].open("r", encoding="utf-8")))
    return rows[0]


def read_stage_results(outputs: dict[str, Path]) -> list[dict[str, str]]:
    return list(csv.DictReader(outputs["stage_results"].open("r", encoding="utf-8")))


def test_both_modes_fail_clearly(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path, "--dry-run")

    with pytest.raises(ValueError, match="Choose only one of --dry-run or --execute."):
        pipeline.run_pipeline(args, runner=FakeRunner())


def test_execute_mode_uses_injected_fake_runner(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)
    fake_runner = FakeRunner()

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert [command.stage for command in fake_runner.calls] == [
        "candidate_review",
        "rule_replay",
        "rule_review",
        "controlled_expansion",
        "gate_decision",
    ]
    summary = read_summary(outputs)
    assert summary["final_classification"] == pipeline.FINAL_CLASSIFICATION_COMPLETED_WITH_SKIPS
    assert summary["pipeline_scope"] == "candidate_audit_research_orchestration"
    assert int(summary["warnings_count"]) == (
        int(summary["blocking_warnings_count"]) + int(summary["non_blocking_warnings_count"])
    )


def test_execute_mode_never_uses_ad_hoc_subprocess_directly() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")

    assert "run_command(" in source
    assert "subprocess.run" not in source


def test_required_command_failure_fails_and_stops(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)
    fake_runner = FakeRunner(returncodes={"rule_replay": 2})

    outputs = pipeline.run_pipeline(args, runner=fake_runner)
    stage_results = read_stage_results(outputs)

    assert read_summary(outputs)["final_classification"] == pipeline.FINAL_CLASSIFICATION_FAILED
    assert [command.stage for command in fake_runner.calls] == ["candidate_review", "rule_replay"]
    assert {row["stage"]: row["status"] for row in stage_results}["rule_replay"] == "failed"
    assert {row["stage"]: row["status"] for row in stage_results}["rule_review"] == "skipped"


def test_missing_required_summary_after_success_fails(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)
    fake_runner = FakeRunner(missing_summaries={"rule_review"})

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert read_summary(outputs)["final_classification"] == pipeline.FINAL_CLASSIFICATION_FAILED
    assert {row["stage"]: row["status"] for row in read_stage_results(outputs)}["rule_review"] == "failed"


def test_required_stage_with_blocking_warnings_stops(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)
    fake_runner = FakeRunner(blocking_warnings={"rule_review"})

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert read_summary(outputs)["final_classification"] == pipeline.FINAL_CLASSIFICATION_STOPPED
    rule_review = {row["stage"]: row for row in read_stage_results(outputs)}["rule_review"]
    assert rule_review["status"] == "stopped"
    assert "blocking warning" in rule_review["failure_reason"]


def test_required_rejection_label_stops_without_continue_after_reject(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)
    labels = {**READY_LABELS, "candidate_review": "CANDIDATE_REVIEW_REJECTED"}
    fake_runner = FakeRunner(labels=labels)

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert read_summary(outputs)["final_classification"] == pipeline.FINAL_CLASSIFICATION_STOPPED
    assert [command.stage for command in fake_runner.calls] == ["candidate_review"]


def test_continue_after_reject_keeps_running_for_forensic_outputs(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path, "--continue-after-reject")
    labels = {**READY_LABELS, "candidate_review": "CANDIDATE_REVIEW_REJECTED"}
    fake_runner = FakeRunner(labels=labels)

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert read_summary(outputs)["final_classification"] == pipeline.FINAL_CLASSIFICATION_COMPLETED_WITH_SKIPS
    assert "rule_replay" in [command.stage for command in fake_runner.calls]


def test_conditional_timeout_stages_skip_when_condition_not_met(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)
    fake_runner = FakeRunner(labels=READY_LABELS)

    outputs = pipeline.run_pipeline(args, runner=fake_runner)
    results_by_stage = {row["stage"]: row for row in read_stage_results(outputs)}
    gate_command = fake_runner.calls[-1]

    assert read_summary(outputs)["final_classification"] == pipeline.FINAL_CLASSIFICATION_COMPLETED_WITH_SKIPS
    assert results_by_stage["timeout_audit"]["status"] == "skipped"
    assert "condition not met" in results_by_stage["timeout_audit"]["skip_reason"]
    assert gate_command.stage == "gate_decision"
    assert "--timeout-audit-dir" not in gate_command.args
    assert "--timeout-root-cause-dir" not in gate_command.args
    assert "--timeout-sequence-dir" not in gate_command.args
    assert "--timeout-policy-sensitivity-dir" not in gate_command.args


def test_conditional_timeout_stages_execute_when_conditions_match(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)
    fake_runner = FakeRunner(labels=TIMEOUT_RETAINED_LABELS)

    outputs = pipeline.run_pipeline(args, runner=fake_runner)

    assert [command.stage for command in fake_runner.calls] == [spec.stage for spec in pipeline.STAGE_SPECS]
    assert read_summary(outputs)["final_classification"] == pipeline.FINAL_CLASSIFICATION_COMPLETED


def test_skip_timeout_policy_sensitivity_omits_gate_input_in_execute_mode(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path, "--skip-timeout-policy-sensitivity")
    fake_runner = FakeRunner(labels=TIMEOUT_RETAINED_LABELS)

    outputs = pipeline.run_pipeline(args, runner=fake_runner)
    gate_command = fake_runner.calls[-1]

    assert gate_command.stage == "gate_decision"
    assert "--timeout-policy-sensitivity-dir" not in gate_command.args
    assert read_summary(outputs)["final_classification"] == pipeline.FINAL_CLASSIFICATION_COMPLETED_WITH_SKIPS


def test_stage_results_csv_contains_required_columns(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)

    outputs = pipeline.run_pipeline(args, runner=FakeRunner())
    rows = read_stage_results(outputs)

    assert rows
    assert list(rows[0]) == pipeline.STAGE_RESULT_FIELDNAMES
    assert rows[0]["command_order"] == "1"
    assert rows[0]["stage_name"] == rows[0]["stage"]
    assert "error_message" in rows[0]


def test_manifest_contains_stage_results_and_final_status(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)

    outputs = pipeline.run_pipeline(args, runner=FakeRunner())
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["execute"] is True
    assert manifest["pipeline_scope"] == "candidate_audit_research_orchestration"
    assert manifest["aggregated_stage_status"] == "partial"
    assert manifest["stage_results"]
    assert manifest["final_classification"] == pipeline.FINAL_CLASSIFICATION_COMPLETED_WITH_SKIPS
    assert manifest["status"] == "completed_with_skips"


def test_logs_are_written_for_executed_fake_runner_commands(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)

    outputs = pipeline.run_pipeline(args, runner=FakeRunner())
    logs_dir = outputs["output_dir"] / "logs"

    assert (logs_dir / "candidate_review.stdout.log").is_file()
    assert (logs_dir / "candidate_review.stderr.log").is_file()
    assert "candidate_review stdout" in (logs_dir / "candidate_review.stdout.log").read_text(encoding="utf-8")


def test_forbidden_actions_remain_in_execution_report(tmp_path: Path) -> None:
    args, _paths = parse_execute_args(tmp_path)

    outputs = pipeline.run_pipeline(args, runner=FakeRunner())
    report = outputs["report"].read_text(encoding="utf-8")

    for action in pipeline.FORBIDDEN_ACTIONS:
        assert action in report
