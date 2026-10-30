from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import run_ml_research_pipeline as pipeline


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows or []:
            writer.writerow(row)


def write_text(path: Path, text: str = "ok\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_standard_report_set(path: Path, *, missing: set[str] | None = None) -> None:
    missing = missing or set()
    csv_headers = {
        "correlations.csv": ["feature", "abs_spearman"],
        "mutual_information.csv": ["feature", "mutual_information"],
        "random_forest_importance.csv": ["feature", "importance"],
        "permutation_importance.csv": ["feature", "importance_mean"],
        "model_metrics.csv": ["metric", "value"],
        "threshold_analysis.csv": ["threshold", "predicted_positive_count"],
        "feature_summary.csv": ["feature"],
    }
    for file_name, headers in csv_headers.items():
        if file_name not in missing:
            write_csv(path / file_name, headers, [{headers[0]: "value"}])


def write_target_comparison(path: Path) -> None:
    write_csv(path / "target_comparison.csv", ["symbol", "target"], [{"symbol": "EURUSD", "target": "target_up_10"}])
    write_text(path / "target_comparison_report.md", "# Target Comparison\n")


def write_preferred_artifacts(root: Path) -> None:
    stability = root / "preferred_target_feature_stability" / "long" / "M15_h10"
    write_csv(stability / "feature_stability.csv", ["feature", "score"], [{"feature": "return_5", "score": 1}])
    write_text(stability / "feature_stability_report.md", "# Stability\n")

    shortlist = root / "preferred_feature_hypotheses" / "long" / "M15_h10"
    write_csv(shortlist / "preferred_feature_hypotheses.csv", ["feature"], [{"feature": "return_5"}])
    write_text(shortlist / "preferred_feature_hypotheses_report.md", "# Shortlist\n")

    build = root / "preferred_horizon_shortlist_builds" / "unit_build"
    write_csv(build / "preferred_horizon_shortlist_manifest.csv", ["run_id", "row_type"], [{"run_id": "unit", "row_type": "target"}])
    write_text(build / "preferred_horizon_shortlist_report.md", "# Build\n")


def make_reports_root(tmp_path: Path, *, complete_optional: bool = False, missing_standard: set[str] | None = None) -> Path:
    root = tmp_path / "ml_research"
    write_standard_report_set(root / "long" / "EURUSD_M15_h10", missing=missing_standard)
    if complete_optional:
        write_standard_report_set(
            root / "target_runs" / "long" / "EURUSD_M15_h10" / "target_up_10"
        )
        write_target_comparison(root / "target_comparison" / "long" / "EURUSD_M15_h10")
        write_preferred_artifacts(root)
    return root


def make_args(tmp_path: Path, reports_root: Path, *extra: str) -> object:
    return pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--reports-root",
            str(reports_root),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--direction",
            "long",
            "--timeframe",
            "M15",
            "--symbols",
            "EURUSD",
            "--horizons",
            "10",
            *extra,
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        pipeline.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_no_mode_selected_fails_clearly(tmp_path: Path) -> None:
    args = make_args(tmp_path, make_reports_root(tmp_path))

    with pytest.raises(ValueError, match="Choose either --dry-run or --execute"):
        pipeline.run_pipeline(args)


def test_both_modes_selected_fails_clearly(tmp_path: Path) -> None:
    args = make_args(tmp_path, make_reports_root(tmp_path), "--dry-run", "--execute")

    with pytest.raises(ValueError, match="Choose only one"):
        pipeline.run_pipeline(args)


def test_missing_reports_root_fails_clearly(tmp_path: Path) -> None:
    args = make_args(tmp_path, tmp_path / "missing_ml_research", "--dry-run")

    with pytest.raises(FileNotFoundError, match="--reports-root does not exist"):
        pipeline.run_pipeline(args)


def test_dry_run_writes_required_wrapper_artifacts_without_child_scripts(tmp_path: Path) -> None:
    args = make_args(tmp_path, make_reports_root(tmp_path), "--dry-run")

    outputs = pipeline.run_pipeline(args)

    for key in ("manifest", "command_plan", "stage_results", "summary", "report", "warnings"):
        assert outputs[key].exists()
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "ML_RESEARCH_PIPELINE_DRY_RUN_PLANNED"
    assert summary["executed_stage_count"] == "0"
    assert not outputs["artifact_inventory"].exists()
    assert all(row["command"].startswith("internal ") for row in read_csv(outputs["command_plan"]))


def test_execute_writes_required_and_consolidation_artifacts(tmp_path: Path) -> None:
    args = make_args(
        tmp_path,
        make_reports_root(tmp_path, complete_optional=True),
        "--include-target-runs",
        "--include-preferred-artifacts",
        "--execute",
    )

    outputs = pipeline.run_pipeline(args)

    for key in (
        "manifest",
        "command_plan",
        "stage_results",
        "summary",
        "report",
        "warnings",
        "inputs",
        "artifact_inventory",
        "missing_artifacts",
        "schema_checks",
    ):
        assert outputs[key].exists()
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "ML_RESEARCH_PIPELINE_COMPLETED"
    assert summary["artifact_readiness_label"] == "ML_ARTIFACTS_READY_FOR_REVIEW"
    assert int(summary["inventoried_artifact_count"]) >= 22


def test_execute_writes_inputs_inventory_missing_and_schema_rows(tmp_path: Path) -> None:
    args = make_args(
        tmp_path,
        make_reports_root(tmp_path, missing_standard={"threshold_analysis.csv"}),
        "--execute",
    )

    outputs = pipeline.run_pipeline(args)

    inputs = read_csv(outputs["inputs"])
    inventory = read_csv(outputs["artifact_inventory"])
    missing = read_csv(outputs["missing_artifacts"])
    schema = read_csv(outputs["schema_checks"])

    assert any(row["input_type"] == "reports_root" and row["enabled"] == "true" for row in inputs)
    assert any(row["relative_path"] == "correlations.csv" for row in inventory)
    assert any(row["missing_file"] == "threshold_analysis.csv" for row in missing)
    assert any(row["csv_path"].endswith("threshold_analysis.csv") and row["status"] == "missing" for row in schema)


def test_optional_missing_target_and_preferred_roots_are_non_blocking(tmp_path: Path) -> None:
    args = make_args(
        tmp_path,
        make_reports_root(tmp_path),
        "--include-target-runs",
        "--include-preferred-artifacts",
        "--execute",
    )

    outputs = pipeline.run_pipeline(args)
    warnings = read_csv(outputs["warnings"])
    summary = read_csv(outputs["summary"])[0]

    assert any(row["warning_code"] == "optional_artifact_root_missing" for row in warnings)
    assert all(row["blocking"] == "false" for row in warnings)
    assert summary["final_classification"] == "ML_RESEARCH_PIPELINE_COMPLETED_WITH_WARNINGS"
    assert summary["artifact_readiness_label"] == "ML_ARTIFACTS_REVIEW_REQUIRED"


def test_report_aggregates_repeated_missing_artifact_warnings(tmp_path: Path) -> None:
    root = tmp_path / "ml_research"
    write_standard_report_set(root / "long" / "EURUSD_M15_h10", missing={"threshold_analysis.csv"})
    write_standard_report_set(root / "long" / "GBPUSD_M15_h10", missing={"threshold_analysis.csv"})
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--reports-root",
            str(root),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--direction",
            "long",
            "--timeframe",
            "M15",
            "--horizons",
            "10",
            "--execute",
        ]
    )

    outputs = pipeline.run_pipeline(args)
    report = outputs["report"].read_text(encoding="utf-8")
    warnings = read_csv(outputs["warnings"])

    assert sum(row["warning_code"] == "missing_expected_ml_artifact" for row in warnings) == 2
    assert "`missing_expected_ml_artifact`: `2` total" in report
    assert "missing_file `threshold_analysis.csv`: `2` total" in report
    assert "Missing expected ML artifacts indicate incomplete existing artifact sets" in report
    assert "Expected ML artifact is missing: threshold_analysis.csv" not in report
    assert "Detailed row-level warnings are preserved in `ml_research_warnings.csv`." in report


def test_manifest_summary_warnings_and_report_counts_are_consistent(tmp_path: Path) -> None:
    args = make_args(
        tmp_path,
        make_reports_root(tmp_path, missing_standard={"threshold_analysis.csv"}),
        "--execute",
    )

    outputs = pipeline.run_pipeline(args)
    warnings = read_csv(outputs["warnings"])
    summary = read_csv(outputs["summary"])[0]
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    report = outputs["report"].read_text(encoding="utf-8")
    blocking_count = sum(row["blocking"] == "true" for row in warnings)

    assert int(summary["warnings_count"]) == len(warnings)
    assert int(summary["blocking_warnings_count"]) == blocking_count
    assert int(summary["non_blocking_warnings_count"]) == len(warnings) - blocking_count
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == blocking_count
    assert manifest["non_blocking_warnings_count"] == len(warnings) - blocking_count
    assert f"total_warnings: `{len(warnings)}`" in report
    assert f"blocking_warnings: `{blocking_count}`" in report
    assert summary["full_inventory_performed"] == "true"
    assert manifest["full_inventory_performed"] is True


def test_dry_run_manifest_and_report_state_planning_only(tmp_path: Path) -> None:
    args = make_args(tmp_path, make_reports_root(tmp_path), "--dry-run")

    outputs = pipeline.run_pipeline(args)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    summary = read_csv(outputs["summary"])[0]
    report = outputs["report"].read_text(encoding="utf-8")

    assert manifest["dry_run_planning_only"] is True
    assert manifest["full_inventory_performed"] is False
    assert summary["full_inventory_performed"] == "false"
    assert "Dry-run mode wrote wrapper planning artifacts only." in report
    assert "full_inventory_performed: `false`" in report
    assert "dry_run_planning_only: `true`" in report


def test_command_plan_and_stage_results_include_command_and_stage_order(tmp_path: Path) -> None:
    args = make_args(tmp_path, make_reports_root(tmp_path), "--execute")

    outputs = pipeline.run_pipeline(args)
    command_plan = read_csv(outputs["command_plan"])
    stage_results = read_csv(outputs["stage_results"])

    assert [row["command_order"] for row in command_plan] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [row["stage_order"] for row in command_plan] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [row["command_order"] for row in stage_results] == ["1", "2", "3", "4", "5", "6", "7"]
    assert [row["stage_order"] for row in stage_results] == ["1", "2", "3", "4", "5", "6", "7"]


def test_report_and_summary_state_research_only_non_decisions(tmp_path: Path) -> None:
    args = make_args(tmp_path, make_reports_root(tmp_path), "--execute")

    outputs = pipeline.run_pipeline(args)
    report = outputs["report"].read_text(encoding="utf-8")
    summary = read_csv(outputs["summary"])[0]
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert "Research-Only Caveat" in report
    assert "did not run model training" in report
    assert "No model-quality, candidate-quality, profitability, or trading decision was made" in report
    assert summary["no_model_quality_evaluation_performed"] == "true"
    assert summary["no_candidate_quality_evaluation_performed"] == "true"
    assert summary["no_trading_decision_performed"] == "true"
    for action in pipeline.FORBIDDEN_ACTIONS:
        assert action in report
    assert manifest["pipeline_scope"] == "ml_artifact_consolidation_only"
    assert manifest["no_model_quality_evaluation_performed"] is True


def test_no_child_scripts_are_planned_or_executed(tmp_path: Path) -> None:
    args = make_args(tmp_path, make_reports_root(tmp_path), "--execute")

    outputs = pipeline.run_pipeline(args)

    command_plan = read_csv(outputs["command_plan"])
    assert all(row["command"].startswith("internal ") for row in command_plan)
    assert all(".py" not in row["command"] for row in command_plan)
    assert ("ml_" + "research.py") not in Path(pipeline.__file__).read_text(encoding="utf-8")


def test_no_live_broker_or_deployment_logic_is_introduced() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    forbidden_terms = [
        "order_" + "send",
        "place_" + "order",
        "open_" + "position",
        "close_" + "position",
        "broker " + "execution",
        "live " + "signal",
        "position " + "sizing",
        "TP/SL " + "optimization",
        "live " + "readiness",
        "buy " + "signal",
        "sell " + "signal",
        "model " + "deployment",
        "live " + "prediction",
        "run-" + "ml-research",
    ]

    for term in forbidden_terms:
        assert term not in source
