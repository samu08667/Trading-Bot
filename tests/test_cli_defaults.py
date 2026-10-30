import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scripts import backtest_combined_hypotheses
from scripts import backtest_research
from scripts import build_final_feature_scorecard
from scripts import build_horizon_consistency_report
from scripts import build_research_decision_report
from scripts import evaluate_backtest_results
from scripts import evaluate_combined_hypotheses
from scripts import run_candidate_baseline_diagnostics
from scripts import run_full_research_pipeline
from scripts import run_random_baseline_tests
from scripts import run_research_validation_pipeline
from scripts import run_walk_forward_research
from scripts import select_research_hypotheses
from scripts import validate_hypotheses_by_year
from scripts.research_costs import validate_cost_args


def assert_estimated_net(args) -> None:
    assert args.cost_mode == "estimated"
    assert args.return_mode == "net"


def assert_none_gross(args) -> None:
    assert args.cost_mode == "none"
    assert args.return_mode == "gross"


def test_validate_hypotheses_by_year_defaults_to_estimated_net(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["validate_hypotheses_by_year.py"])

    assert_estimated_net(validate_hypotheses_by_year.parse_args())


def test_backtest_research_defaults_to_estimated_net(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["backtest_research.py", "--symbol", "EURUSD", "--timeframe", "M15"])

    assert_estimated_net(backtest_research.parse_args())


def test_backtest_combined_hypotheses_defaults_to_estimated_net(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["backtest_combined_hypotheses.py", "--symbol", "EURUSD", "--timeframe", "M15"],
    )

    assert_estimated_net(backtest_combined_hypotheses.parse_args())


def test_backtest_evaluators_default_to_estimated_net(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["evaluate_backtest_results.py"])
    assert_estimated_net(evaluate_backtest_results.parse_args())

    monkeypatch.setattr(sys, "argv", ["evaluate_combined_hypotheses.py"])
    assert_estimated_net(evaluate_combined_hypotheses.parse_args())


def test_random_baseline_defaults_to_estimated_net(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_random_baseline_tests.py", "--run-id", "run1", "--symbols", "EURUSD"])

    assert_estimated_net(run_random_baseline_tests.parse_args())


def test_candidate_baseline_diagnostics_defaults_to_estimated_net() -> None:
    assert_estimated_net(run_candidate_baseline_diagnostics.parse_args(["--run-id", "run1"]))


def test_research_decision_report_defaults_to_estimated_net(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["build_research_decision_report.py", "--run-id", "run1"])

    assert_estimated_net(build_research_decision_report.parse_args())


def test_horizon_consistency_defaults_to_estimated_net() -> None:
    args = build_horizon_consistency_report.parse_args(
        [
            "--group-id",
            "group1",
            "--h5-run-id",
            "run_h5",
            "--h10-run-id",
            "run_h10",
            "--h20-run-id",
            "run_h20",
        ]
    )

    assert_estimated_net(args)


def test_walk_forward_defaults_to_estimated_net(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_walk_forward_research.py", "--symbols", "EURUSD"])

    assert_estimated_net(run_walk_forward_research.parse_args())


def test_post_validation_orchestrators_default_to_estimated_net(monkeypatch: pytest.MonkeyPatch) -> None:
    assert_estimated_net(run_full_research_pipeline.build_parser().parse_args([]))
    assert_estimated_net(run_research_validation_pipeline.build_parser().parse_args([]))
    monkeypatch.setattr(sys, "argv", ["build_final_feature_scorecard.py"])
    assert_estimated_net(build_final_feature_scorecard.parse_args())


def test_select_research_hypotheses_default_top_n_is_5(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["select_research_hypotheses.py"])

    assert select_research_hypotheses.parse_args().top_n == 5


def test_net_return_mode_with_no_cost_mode_still_fails() -> None:
    with pytest.raises(ValueError, match="--return-mode net requires --cost-mode estimated"):
        validate_cost_args("none", "net")


def test_overwrite_defaults_remain_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["validate_hypotheses_by_year.py"])
    assert validate_hypotheses_by_year.parse_args().overwrite is False

    monkeypatch.setattr(sys, "argv", ["run_random_baseline_tests.py", "--run-id", "run1", "--symbols", "EURUSD"])
    assert run_random_baseline_tests.parse_args().overwrite is False

    assert run_candidate_baseline_diagnostics.parse_args(["--run-id", "run1"]).overwrite is False

    monkeypatch.setattr(sys, "argv", ["build_research_decision_report.py", "--run-id", "run1"])
    assert build_research_decision_report.parse_args().overwrite is False

    args = build_horizon_consistency_report.parse_args(
        [
            "--group-id",
            "group1",
            "--h5-run-id",
            "run_h5",
            "--h10-run-id",
            "run_h10",
            "--h20-run-id",
            "run_h20",
        ]
    )
    assert args.overwrite is False

    monkeypatch.setattr(sys, "argv", ["run_walk_forward_research.py", "--symbols", "EURUSD"])
    assert run_walk_forward_research.parse_args().overwrite is False

    full_pipeline_args = run_full_research_pipeline.build_parser().parse_args([])
    assert full_pipeline_args.overwrite_validation is False
    assert full_pipeline_args.overwrite_final_review is False
    assert full_pipeline_args.skip_final_review_if_no_candidates is True
    assert full_pipeline_args.diagnostics_random_runs == 100


def test_explicit_none_gross_still_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_hypotheses_by_year.py", "--cost-mode", "none", "--return-mode", "gross"],
    )
    assert_none_gross(validate_hypotheses_by_year.parse_args())

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backtest_research.py",
            "--symbol",
            "EURUSD",
            "--timeframe",
            "M15",
            "--cost-mode",
            "none",
            "--return-mode",
            "gross",
        ],
    )
    assert_none_gross(backtest_research.parse_args())

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backtest_combined_hypotheses.py",
            "--symbol",
            "EURUSD",
            "--timeframe",
            "M15",
            "--cost-mode",
            "none",
            "--return-mode",
            "gross",
        ],
    )
    assert_none_gross(backtest_combined_hypotheses.parse_args())

    monkeypatch.setattr(sys, "argv", ["evaluate_backtest_results.py", "--cost-mode", "none", "--return-mode", "gross"])
    assert_none_gross(evaluate_backtest_results.parse_args())

    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_combined_hypotheses.py", "--cost-mode", "none", "--return-mode", "gross"],
    )
    assert_none_gross(evaluate_combined_hypotheses.parse_args())

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_random_baseline_tests.py",
            "--run-id",
            "run1",
            "--symbols",
            "EURUSD",
            "--cost-mode",
            "none",
            "--return-mode",
            "gross",
        ],
    )
    assert_none_gross(run_random_baseline_tests.parse_args())

    assert_none_gross(
        run_candidate_baseline_diagnostics.parse_args(
            ["--run-id", "run1", "--cost-mode", "none", "--return-mode", "gross"]
        )
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["build_research_decision_report.py", "--run-id", "run1", "--cost-mode", "none", "--return-mode", "gross"],
    )
    assert_none_gross(build_research_decision_report.parse_args())

    assert_none_gross(
        build_horizon_consistency_report.parse_args(
            [
                "--group-id",
                "group1",
                "--h5-run-id",
                "run_h5",
                "--h10-run-id",
                "run_h10",
                "--h20-run-id",
                "run_h20",
                "--cost-mode",
                "none",
                "--return-mode",
                "gross",
            ]
        )
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_walk_forward_research.py", "--symbols", "EURUSD", "--cost-mode", "none", "--return-mode", "gross"],
    )
    assert_none_gross(run_walk_forward_research.parse_args())

    assert_none_gross(
        run_full_research_pipeline.build_parser().parse_args(["--cost-mode", "none", "--return-mode", "gross"])
    )
