from __future__ import annotations

import csv
from pathlib import Path
import sys

import pytest

from scripts import run_full_research_pipeline as pipeline

DEFAULT_TEST_COST_CONFIG = Path(__file__).resolve().parents[1] / "config" / "cost_model.example.json"


class FakeRunner:
    def __init__(self, tmp_path: Path, *, run_id: str = "run1", continue_on_error: bool = False) -> None:
        self.run_id = run_id
        self.log_path = tmp_path / "full_pipeline.log"
        self.continue_on_error = continue_on_error
        self.completed_steps: list[str] = []
        self.failed_steps: list[str] = []
        self.skipped_steps: list[str] = []
        self.messages: list[str] = []
        self.commands: list[tuple[str, list[str]]] = []
        self.final_review = pipeline.FinalReviewState()

    def emit(self, text: str = "") -> None:
        self.messages.append(text)

    def skip(self, step_name: str, reason: str) -> None:
        self.skipped_steps.append(step_name)
        self.emit(f"SKIP: {step_name}")
        self.emit(f"Reason: {reason}")

    def run_step(self, step_name: str, command: list[str]) -> None:
        self.commands.append((step_name, [str(item) for item in command]))
        self.completed_steps.append(step_name)


def configure_tmp_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pipeline, "COMBINED_RUNS_DIR", tmp_path / "combined_runs")
    monkeypatch.setattr(pipeline, "COMBINED_EVALUATIONS_DIR", tmp_path / "combined_evaluations")
    monkeypatch.setattr(pipeline, "VALIDATION_OUTPUT_DIR", tmp_path / "validation" / "by_year")
    monkeypatch.setattr(pipeline, "FINAL_SCORECARD_OUTPUT_DIR", tmp_path / "final_feature_scorecard")
    monkeypatch.setattr(pipeline, "WALK_FORWARD_OUTPUT_DIR", tmp_path / "walk_forward")
    monkeypatch.setattr(pipeline, "RANDOM_BASELINE_OUTPUT_DIR", tmp_path / "random_baseline")
    monkeypatch.setattr(pipeline, "BASELINE_DIAGNOSTICS_OUTPUT_DIR", tmp_path / "baseline_diagnostics")
    monkeypatch.setattr(pipeline, "RESEARCH_DECISION_OUTPUT_DIR", tmp_path / "research_decision")
    monkeypatch.setattr(pipeline, "LOGS_DIR", tmp_path / "logs")


def parse_args(*extra: str) -> object:
    return pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--symbols",
            "EURUSD",
            "--skip-calendar-import",
            "--skip-price-import",
            "--skip-checks",
            "--cost-config",
            str(DEFAULT_TEST_COST_CONFIG),
            *extra,
        ]
    )


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["combination_key", "direction", "cost_mode", "return_mode", "symbol"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def prepare_selected_hypotheses() -> None:
    path = pipeline.COMBINED_EVALUATIONS_DIR / "run1" / "long" / pipeline.SELECTED_COMBINED_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("combination_key\nhour_session:London\n", encoding="utf-8")


def prepare_candidates(*, cross_pair: bool = True, pair_specific: bool = False) -> None:
    cross_path, pair_path = pipeline.final_candidate_paths("run1", "long")
    candidate = {
        "combination_key": "hour_session:London",
        "direction": "long",
        "cost_mode": "estimated",
        "return_mode": "net",
        "symbol": "EURUSD",
    }
    write_rows(cross_path, [candidate] if cross_pair else [])
    write_rows(pair_path, [candidate] if pair_specific else [])


def run_with_fake_runner(tmp_path: Path, args: object) -> FakeRunner:
    prepare_selected_hypotheses()
    runner = FakeRunner(tmp_path)
    pipeline.run_pipeline(args, runner)
    return runner


def command_for(runner: FakeRunner, script_name: str) -> list[str] | None:
    for _step, command in runner.commands:
        if len(command) > 1 and Path(command[1]).name == script_name:
            return command
    return None


def test_run_final_review_enables_all_review_steps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)
    prepare_candidates(cross_pair=True)

    runner = run_with_fake_runner(tmp_path, parse_args("--run-final-review"))

    assert command_for(runner, "run_random_baseline_tests.py") is not None
    assert command_for(runner, "run_candidate_baseline_diagnostics.py") is not None
    assert command_for(runner, "build_research_decision_report.py") is not None
    assert runner.final_review.completed_steps == [
        pipeline.FINAL_REVIEW_RANDOM_BASELINE,
        pipeline.FINAL_REVIEW_BASELINE_DIAGNOSTICS,
        pipeline.FINAL_REVIEW_RESEARCH_DECISION,
    ]


def test_run_random_baseline_only_runs_random_baseline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)
    prepare_candidates(cross_pair=True)

    runner = run_with_fake_runner(tmp_path, parse_args("--run-random-baseline"))

    assert command_for(runner, "run_random_baseline_tests.py") is not None
    assert command_for(runner, "run_candidate_baseline_diagnostics.py") is None
    assert command_for(runner, "build_research_decision_report.py") is None


def test_run_baseline_diagnostics_only_runs_diagnostics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)
    prepare_candidates(cross_pair=True)

    runner = run_with_fake_runner(tmp_path, parse_args("--run-baseline-diagnostics"))

    assert command_for(runner, "run_random_baseline_tests.py") is None
    assert command_for(runner, "run_candidate_baseline_diagnostics.py") is not None
    assert command_for(runner, "build_research_decision_report.py") is None


def test_run_research_decision_only_runs_decision_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)
    prepare_candidates(cross_pair=True)

    runner = run_with_fake_runner(tmp_path, parse_args("--run-research-decision-report"))

    assert command_for(runner, "run_random_baseline_tests.py") is None
    assert command_for(runner, "run_candidate_baseline_diagnostics.py") is None
    assert command_for(runner, "build_research_decision_report.py") is not None


def test_candidate_preflight_skips_random_and_diagnostics_when_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)
    prepare_candidates(cross_pair=False, pair_specific=False)

    runner = run_with_fake_runner(tmp_path, parse_args("--run-final-review"))

    assert command_for(runner, "run_random_baseline_tests.py") is None
    assert command_for(runner, "run_candidate_baseline_diagnostics.py") is None
    assert command_for(runner, "build_research_decision_report.py") is not None
    assert "No final candidates found" in "\n".join(runner.messages)


def test_pair_specific_candidates_ignored_without_final_review_include(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)
    prepare_candidates(cross_pair=False, pair_specific=True)

    runner = run_with_fake_runner(tmp_path, parse_args("--run-random-baseline"))

    assert command_for(runner, "run_random_baseline_tests.py") is None
    assert runner.final_review.candidate_counts == {"cross_pair": 0, "pair_specific": 1}


def test_pair_specific_candidates_counted_with_final_review_include(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)
    prepare_candidates(cross_pair=False, pair_specific=True)

    runner = run_with_fake_runner(
        tmp_path,
        parse_args("--run-random-baseline", "--include-pair-specific-final-review"),
    )

    command = command_for(runner, "run_random_baseline_tests.py")
    assert command is not None
    assert "--include-pair-specific" in command


def test_final_review_commands_receive_expected_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)
    prepare_candidates(cross_pair=True)
    cost_config = tmp_path / "costs.json"
    cost_config.write_text("{}", encoding="utf-8")

    runner = run_with_fake_runner(
        tmp_path,
        parse_args(
            "--run-final-review",
            "--include-pair-specific-final-review",
            "--random-baseline-runs",
            "260",
            "--diagnostics-random-runs",
            "77",
            "--diagnostics-max-candidates",
            "12",
            "--cost-config",
            str(cost_config),
            "--strict-cost-config",
            "--overwrite-final-review",
        ),
    )

    random_command = command_for(runner, "run_random_baseline_tests.py")
    diagnostics_command = command_for(runner, "run_candidate_baseline_diagnostics.py")
    decision_command = command_for(runner, "build_research_decision_report.py")
    assert random_command is not None
    assert diagnostics_command is not None
    assert decision_command is not None

    for command in (random_command, diagnostics_command):
        assert command[command.index("--run-id") + 1] == "run1"
        assert command[command.index("--direction") + 1] == "long"
        assert command[command.index("--symbols") + 1] == "EURUSD"
        assert command[command.index("--timeframe") + 1] == "M15"
        assert command[command.index("--target-horizon") + 1] == "10"
        assert command[command.index("--cost-mode") + 1] == "estimated"
        assert command[command.index("--return-mode") + 1] == "net"
        assert command[command.index("--cost-config") + 1] == str(cost_config)
        assert "--strict-cost-config" in command
        assert "--include-pair-specific" in command
        assert "--overwrite" in command

    assert random_command[random_command.index("--random-runs") + 1] == "260"
    assert diagnostics_command[diagnostics_command.index("--random-runs") + 1] == "77"
    assert diagnostics_command[diagnostics_command.index("--max-candidates") + 1] == "12"
    assert decision_command[decision_command.index("--cost-mode") + 1] == "estimated"
    assert decision_command[decision_command.index("--return-mode") + 1] == "net"


def test_overwrite_final_review_required_for_existing_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)
    prepare_candidates(cross_pair=True)
    existing = pipeline.RANDOM_BASELINE_OUTPUT_DIR / "run1" / "long" / "random_baseline_report.md"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("old report\n", encoding="utf-8")

    with pytest.raises(pipeline.PipelineAbort):
        run_with_fake_runner(tmp_path, parse_args("--run-random-baseline"))

    runner = run_with_fake_runner(tmp_path, parse_args("--run-random-baseline", "--overwrite-final-review"))
    command = command_for(runner, "run_random_baseline_tests.py")
    assert command is not None
    assert "--overwrite" in command


def test_keyboard_interrupt_does_not_report_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)

    def interrupt(_args: object, _runner: object) -> Path:
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "run_pipeline", interrupt)
    monkeypatch.setattr(sys, "argv", ["run_full_research_pipeline.py", "--run-id", "run1"])

    result = pipeline.main()

    output = capsys.readouterr().out
    assert result == 130
    assert "final status: interrupted" in output
    assert "final status: success" not in output


def test_failed_step_reports_partial_success_not_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_tmp_dirs(monkeypatch, tmp_path)

    def fail_one_step(_args: object, runner: object) -> Path:
        runner.failed_steps.append("failed child")
        return pipeline.COMBINED_EVALUATIONS_DIR / runner.run_id / "long"

    monkeypatch.setattr(pipeline, "run_pipeline", fail_one_step)
    monkeypatch.setattr(sys, "argv", ["run_full_research_pipeline.py", "--run-id", "run1"])

    result = pipeline.main()

    output = capsys.readouterr().out
    assert result == 1
    assert "final status: partial_success" in output
    assert "final status: success" not in output
