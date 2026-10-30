from __future__ import annotations

from pathlib import Path

import pytest

from scripts import run_full_research_pipeline
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
    }
  }
}
""".strip(),
        encoding="utf-8",
    )


class FakeRunner:
    def __init__(self, tmp_path: Path) -> None:
        self.run_id = "run1"
        self.log_path = tmp_path / "full_pipeline.log"
        self.continue_on_error = False
        self.completed_steps: list[str] = []
        self.failed_steps: list[str] = []
        self.skipped_steps: list[str] = []
        self.commands: list[tuple[str, list[str]]] = []
        self.final_review = run_full_research_pipeline.FinalReviewState()

    def emit(self, _text: str = "") -> None:
        return None

    def skip(self, step_name: str, _reason: str) -> None:
        self.skipped_steps.append(step_name)

    def run_step(self, step_name: str, command: list[str]) -> None:
        self.commands.append((step_name, [str(item) for item in command]))
        self.completed_steps.append(step_name)


def test_net_return_with_no_cost_mode_fails_preflight() -> None:
    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        validate_orchestrator_cost_preflight(
            cost_mode="none",
            return_mode="net",
            cost_config_path=None,
        )


def test_gross_none_is_allowed_without_cost_config() -> None:
    assert validate_orchestrator_cost_preflight(
        cost_mode="none",
        return_mode="gross",
        cost_config_path=None,
    ) == ("none", "gross")


def test_estimated_mode_requires_explicit_cost_config() -> None:
    with pytest.raises(ValueError, match="Missing --cost-config"):
        validate_orchestrator_cost_preflight(
            cost_mode="estimated",
            return_mode="net",
            cost_config_path=None,
        )


def test_estimated_net_with_valid_cost_config_is_allowed(tmp_path: Path) -> None:
    cost_config = tmp_path / "costs.json"
    write_cost_config(cost_config)

    assert validate_orchestrator_cost_preflight(
        cost_mode="estimated",
        return_mode="net",
        cost_config_path=cost_config,
    ) == ("estimated", "net")


def test_invalid_cost_config_path_is_actionable(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    with pytest.raises(ValueError, match="Cost config path does not exist"):
        validate_orchestrator_cost_preflight(
            cost_mode="estimated",
            return_mode="net",
            cost_config_path=missing,
        )


def test_invalid_cost_config_json_is_actionable(tmp_path: Path) -> None:
    bad_config = tmp_path / "bad_costs.json"
    bad_config.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid cost config JSON"):
        validate_orchestrator_cost_preflight(
            cost_mode="estimated",
            return_mode="net",
            cost_config_path=bad_config,
        )


def test_orchestrator_parser_defaults_remain_estimated_net() -> None:
    full_args = run_full_research_pipeline.build_parser().parse_args([])
    validation_args = run_research_validation_pipeline.build_parser().parse_args([])

    assert full_args.cost_mode == "estimated"
    assert full_args.return_mode == "net"
    assert validation_args.cost_mode == "estimated"
    assert validation_args.return_mode == "net"


def test_full_pipeline_preflight_runs_before_child_steps(tmp_path: Path) -> None:
    args = run_full_research_pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--symbols",
            "EURUSD",
            "--skip-calendar-import",
            "--skip-price-import",
            "--skip-checks",
            "--cost-mode",
            "none",
            "--return-mode",
            "net",
        ]
    )
    runner = FakeRunner(tmp_path)

    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        run_full_research_pipeline.run_pipeline(args, runner)

    assert runner.commands == []


def test_validation_pipeline_preflight_runs_before_child_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    args = run_research_validation_pipeline.build_parser().parse_args(
        ["--run-id", "run1", "--cost-mode", "none", "--return-mode", "net"]
    )
    commands: list[tuple[str, list[str]]] = []

    def fail_if_combined_input_is_resolved(_args: object) -> tuple[str, Path]:
        raise AssertionError("combined input should not be resolved before cost preflight")

    monkeypatch.setattr(run_research_validation_pipeline, "resolve_combined_input", fail_if_combined_input_is_resolved)
    monkeypatch.setattr(
        run_research_validation_pipeline,
        "run_step",
        lambda step_name, command: commands.append((step_name, command)),
    )

    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        run_research_validation_pipeline.run_pipeline(args)

    assert commands == []


def test_validation_pipeline_valid_preflight_can_reach_child_planning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cost_config = tmp_path / "costs.json"
    write_cost_config(cost_config)
    combined_input_dir = tmp_path / "combined"
    combined_input_dir.mkdir()
    (combined_input_dir / "combined_hypotheses_summary.csv").write_text("combination_key\nx\n", encoding="utf-8")
    combined_evaluations_dir = tmp_path / "evaluations"
    validation_output_dir = tmp_path / "validation"
    scorecard_output_dir = tmp_path / "scorecard"

    args = run_research_validation_pipeline.build_parser().parse_args(
        [
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
            "--symbols",
            "EURUSD",
            "--cost-config",
            str(cost_config),
        ]
    )
    commands: list[tuple[str, list[str]]] = []

    def fake_run_step(step_name: str, command: list[str]) -> None:
        commands.append((step_name, [str(item) for item in command]))
        if step_name.startswith("1."):
            selected = combined_evaluations_dir / "run1" / "long" / "selected_combined_hypotheses.csv"
            selected.parent.mkdir(parents=True, exist_ok=True)
            selected.write_text("combination_key\nhour_session:London\n", encoding="utf-8")

    monkeypatch.setattr(run_research_validation_pipeline, "run_step", fake_run_step)

    run_research_validation_pipeline.run_pipeline(args)

    assert [step for step, _command in commands] == [
        "1. evaluate combined hypotheses",
        "2. validate combined hypotheses by year",
        "3. build final feature scorecard",
    ]


def test_orchestrator_help_still_exits_successfully() -> None:
    with pytest.raises(SystemExit) as full_help:
        run_full_research_pipeline.build_parser().parse_args(["--help"])
    with pytest.raises(SystemExit) as validation_help:
        run_research_validation_pipeline.build_parser().parse_args(["--help"])

    assert full_help.value.code == 0
    assert validation_help.value.code == 0
