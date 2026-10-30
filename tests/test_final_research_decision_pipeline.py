from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import run_final_research_decision_pipeline as pipeline


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open("r", encoding="utf-8")))


def write_csv(path: Path, header: str, row: str = "value\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + row, encoding="utf-8")


def make_combined_validation_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "combined_validation"
    directory.mkdir()
    (directory / "combined_validation_manifest.json").write_text("{}\n", encoding="utf-8")
    write_csv(
        directory / "combined_validation_summary.csv",
        "final_classification,decision_scope",
        "COMBINED_VALIDATION_PIPELINE_COMPLETED,combined_validation_pipeline\n",
    )
    (directory / "combined_validation_report.md").write_text("# Combined Validation\n", encoding="utf-8")
    write_csv(
        directory / "combined_validation_warnings.csv",
        "warning_code,severity,blocking,message",
        "none,info,false,ok\n",
    )
    return directory


def make_scorecard_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "scorecard"
    directory.mkdir()
    write_csv(directory / "final_feature_scorecard.csv", "feature,score", "hour_session,1\n")
    (directory / "final_feature_scorecard_report.md").write_text("# Scorecard\n", encoding="utf-8")
    return directory


def make_stress_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "stress"
    directory.mkdir()
    write_csv(directory / "candidate_stress_summary.csv", "candidate_id,final_classification", "c1,ready\n")
    (directory / "candidate_stress_report.md").write_text("# Stress\n", encoding="utf-8")
    return directory


def make_stress_wrapper_dir(tmp_path: Path, stress_output_dir: Path) -> Path:
    directory = tmp_path / "stress_wrapper"
    directory.mkdir()
    (directory / "fixed_candidate_stress_validation_manifest.json").write_text(
        json.dumps({"stress_output_dir": str(stress_output_dir)}),
        encoding="utf-8",
    )
    return directory


def make_candidate_audit_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "candidate_audit"
    directory.mkdir()
    (directory / "candidate_audit_manifest.json").write_text("{}\n", encoding="utf-8")
    write_csv(
        directory / "candidate_audit_pipeline_summary.csv",
        "final_classification,decision_scope",
        "CANDIDATE_AUDIT_PIPELINE_COMPLETED,candidate_audit_pipeline\n",
    )
    (directory / "candidate_audit_pipeline_report.md").write_text("# Candidate Audit\n", encoding="utf-8")
    write_csv(
        directory / "candidate_audit_pipeline_warnings.csv",
        "warning_code,severity,blocking,message",
        "none,info,false,ok\n",
    )
    return directory


def make_valid_args(tmp_path: Path, *extra: str) -> object:
    combined_dir = make_combined_validation_dir(tmp_path)
    return pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--combined-validation-dir",
            str(combined_dir),
            "--candidate-id",
            "candidate_1",
            "--symbol",
            "EURUSD",
            "--direction",
            "long",
            "--timeframe",
            "M15",
            "--target-horizon",
            "10",
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            *extra,
        ]
    )


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


def test_no_input_directories_fails_clearly(tmp_path: Path) -> None:
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--dry-run",
        ]
    )

    with pytest.raises(ValueError, match="At least one upstream input directory"):
        pipeline.run_pipeline(args)


def test_missing_provided_input_directory_fails_early(tmp_path: Path) -> None:
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--combined-validation-dir",
            str(tmp_path / "missing_combined_validation"),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--dry-run",
        ]
    )

    with pytest.raises(FileNotFoundError, match="--combined-validation-dir does not exist"):
        pipeline.run_pipeline(args)


def test_dry_run_writes_required_wrapper_artifacts(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)

    for key in ("manifest", "command_plan", "stage_results", "summary", "report", "warnings"):
        assert outputs[key].exists()
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "FINAL_RESEARCH_DECISION_PIPELINE_DRY_RUN_PLANNED"
    assert summary["pipeline_scope"] == "artifact_consolidation_only"
    assert summary["executed_stage_count"] == "0"


def test_dry_run_does_not_plan_child_scripts(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--dry-run")

    outputs = pipeline.run_pipeline(args)
    rows = read_csv(outputs["command_plan"])

    assert all(row["command"].startswith("internal ") for row in rows)
    assert all(".py" not in row["command"] for row in rows)


def test_execute_writes_consolidation_artifacts(tmp_path: Path) -> None:
    args = make_valid_args(
        tmp_path,
        "--final-feature-scorecard-dir",
        str(make_scorecard_dir(tmp_path)),
        "--stress-validation-dir",
        str(make_stress_dir(tmp_path)),
        "--candidate-audit-dir",
        str(make_candidate_audit_dir(tmp_path)),
        "--execute",
    )

    outputs = pipeline.run_pipeline(args)

    for key in ("inputs", "artifact_index", "schema_checks"):
        assert outputs[key].exists()
    summary = read_csv(outputs["summary"])[0]
    assert summary["final_classification"] == "FINAL_RESEARCH_DECISION_PIPELINE_COMPLETED"
    assert summary["artifact_readiness_label"] == "ARTIFACTS_READY_FOR_REVIEW"
    assert summary["executed_stage_count"] == "4"
    assert int(summary["indexed_artifact_count"]) >= 10


def test_stress_validation_wrapper_dir_resolves_child_output_dir(tmp_path: Path) -> None:
    stress_dir = make_stress_dir(tmp_path)
    stress_wrapper_dir = make_stress_wrapper_dir(tmp_path, stress_dir)
    args = make_valid_args(
        tmp_path,
        "--final-feature-scorecard-dir",
        str(make_scorecard_dir(tmp_path)),
        "--stress-validation-dir",
        str(stress_wrapper_dir),
        "--candidate-audit-dir",
        str(make_candidate_audit_dir(tmp_path)),
        "--execute",
    )

    outputs = pipeline.run_pipeline(args)
    input_rows = read_csv(outputs["inputs"])
    artifact_rows = read_csv(outputs["artifact_index"])
    warnings = read_csv(outputs["warnings"])

    stress_input = next(row for row in input_rows if row["input_type"] == "stress_validation")
    assert stress_input["path"] == str(stress_dir.resolve())
    assert any(
        row["input_type"] == "stress_validation"
        and row["relative_path"] == "candidate_stress_summary.csv"
        for row in artifact_rows
    )
    assert any(row["warning_code"] == "stress_validation_wrapper_dir_resolved" for row in warnings)


def test_stress_validation_wrapper_dir_without_stress_output_dir_fails_clearly(tmp_path: Path) -> None:
    stress_wrapper_dir = tmp_path / "stress_wrapper"
    stress_wrapper_dir.mkdir()
    (stress_wrapper_dir / "fixed_candidate_stress_validation_manifest.json").write_text(
        "{}",
        encoding="utf-8",
    )
    args = make_valid_args(
        tmp_path,
        "--stress-validation-dir",
        str(stress_wrapper_dir),
        "--dry-run",
    )

    with pytest.raises(ValueError, match=r"Use the child stress output directory reports/regime_candidate_stress"):
        pipeline.run_pipeline(args)


def test_optional_missing_inputs_are_non_blocking_warnings(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")

    outputs = pipeline.run_pipeline(args)
    warnings = read_csv(outputs["warnings"])
    summary = read_csv(outputs["summary"])[0]

    assert any(row["warning_code"] == "optional_input_not_provided" for row in warnings)
    assert all(row["blocking"] == "false" for row in warnings)
    assert summary["final_classification"] == "FINAL_RESEARCH_DECISION_PIPELINE_COMPLETED_WITH_WARNINGS"
    assert summary["artifact_readiness_label"] == "ARTIFACTS_REVIEW_REQUIRED"
    assert int(summary["warnings_count"]) == (
        int(summary["blocking_warnings_count"]) + int(summary["non_blocking_warnings_count"])
    )


def test_missing_expected_key_file_gets_non_blocking_warning(tmp_path: Path) -> None:
    combined_dir = make_combined_validation_dir(tmp_path)
    (combined_dir / "combined_validation_report.md").unlink()
    args = pipeline.build_parser().parse_args(
        [
            "--run-id",
            "run1",
            "--combined-validation-dir",
            str(combined_dir),
            "--output-root",
            str(tmp_path / "pipeline_outputs"),
            "--execute",
        ]
    )

    outputs = pipeline.run_pipeline(args)
    warnings = read_csv(outputs["warnings"])

    assert any(row["warning_code"] == "missing_expected_artifact" for row in warnings)
    assert all(row["blocking"] == "false" for row in warnings)


def test_command_plan_and_stage_results_include_ordering(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")

    outputs = pipeline.run_pipeline(args)
    command_plan = read_csv(outputs["command_plan"])
    stage_results = read_csv(outputs["stage_results"])

    assert [row["command_order"] for row in command_plan] == ["1", "2", "3", "4"]
    assert [row["stage_order"] for row in command_plan] == ["1", "2", "3", "4"]
    assert [row["command_order"] for row in stage_results] == ["1", "2", "3", "4"]
    assert [row["stage_order"] for row in stage_results] == ["1", "2", "3", "4"]
    assert all(row["status"] == "executed" for row in stage_results)


def test_artifact_index_and_schema_checks_capture_known_artifacts(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")

    outputs = pipeline.run_pipeline(args)
    artifact_rows = read_csv(outputs["artifact_index"])
    schema_rows = read_csv(outputs["schema_checks"])

    assert any(row["relative_path"] == "combined_validation_summary.csv" for row in artifact_rows)
    summary_check = next(row for row in schema_rows if row["file_name"] == "combined_validation_summary.csv")
    assert summary_check["status"] == "ok"
    assert "final_classification" in summary_check["header_columns"]


def test_report_states_no_candidate_quality_or_trading_decision(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")

    outputs = pipeline.run_pipeline(args)
    report = outputs["report"].read_text(encoding="utf-8")
    summary = read_csv(outputs["summary"])[0]

    assert "made no candidate quality" in report
    assert "No candidate was ranked, promoted, rejected, approved for trading" in report
    for action in pipeline.FORBIDDEN_ACTIONS:
        assert action in report
    assert "live " + "readiness" in summary["forbidden_actions"]


def test_manifest_records_artifact_scope_and_no_quality_evaluation(tmp_path: Path) -> None:
    args = make_valid_args(tmp_path, "--execute")

    outputs = pipeline.run_pipeline(args)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["pipeline_scope"] == "artifact_consolidation_only"
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["warnings_count"] == (
        manifest["blocking_warnings_count"] + manifest["non_blocking_warnings_count"]
    )


def test_no_broker_order_api_terms_in_wrapper_source() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    forbidden_terms = [
        "order_" + "send",
        "place_" + "order",
        "open_" + "position",
        "close_" + "position",
        "buy " + "signal",
        "sell " + "signal",
    ]

    for term in forbidden_terms:
        assert term not in source
