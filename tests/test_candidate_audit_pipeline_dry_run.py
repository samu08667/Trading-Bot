from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import run_candidate_audit_pipeline as pipeline


REQUIRED_STAGES = {
    "candidate_review",
    "rule_replay",
    "rule_review",
    "controlled_expansion",
    "gate_decision",
}
CONDITIONAL_STAGES = {
    "timeout_audit",
    "timeout_root_cause",
    "timeout_sequence_drilldown",
    "timeout_policy_sensitivity",
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
    cost_config = write_cost_config(tmp_path / "cost_config.json")
    stress_cost_config = write_cost_config(tmp_path / "stress_cost_config.json")
    return {
        "stress_output_dir": stress_output_dir,
        "db_path": db_path,
        "cost_config": cost_config,
        "stress_cost_config": stress_cost_config,
        "output_root": tmp_path / "reports",
    }


def parse_valid_args(tmp_path: Path, *extra: str, dry_run: bool = True) -> tuple[object, dict[str, Path]]:
    paths = make_inputs(tmp_path)
    argv = [
        "--stress-output-dir",
        str(paths["stress_output_dir"]),
        "--db-path",
        str(paths["db_path"]),
        "--cost-config",
        str(paths["cost_config"]),
        "--stress-cost-config",
        str(paths["stress_cost_config"]),
        "--stress-spread-policy",
        "max_row_or_fallback",
        "--run-id",
        "unit_audit_run",
        "--output-root",
        str(paths["output_root"]),
    ]
    if dry_run:
        argv.append("--dry-run")
    argv.extend(extra)
    return pipeline.build_parser().parse_args(argv), paths


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        pipeline.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_dry_run_creates_manifest_plan_summary_report_and_warnings(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path)

    outputs = pipeline.run_pipeline(args)

    assert outputs["manifest"].is_file()
    assert outputs["command_plan"].is_file()
    assert outputs["summary"].is_file()
    assert outputs["report"].is_file()
    assert outputs["warnings"].is_file()


def test_dry_run_does_not_create_child_stage_outputs(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path)

    outputs = pipeline.run_pipeline(args)

    for spec in pipeline.STAGE_SPECS:
        assert not (outputs["output_dir"] / spec.output_dir_name).exists()


def test_fails_clearly_without_dry_run(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path, dry_run=False)

    with pytest.raises(ValueError, match="Choose either --dry-run or --execute."):
        pipeline.run_pipeline(args)


def test_missing_stress_output_dir_fails_clearly(tmp_path: Path) -> None:
    paths = make_inputs(tmp_path)
    args = pipeline.build_parser().parse_args(
        [
            "--dry-run",
            "--db-path",
            str(paths["db_path"]),
            "--cost-config",
            str(paths["cost_config"]),
            "--stress-cost-config",
            str(paths["stress_cost_config"]),
            "--output-root",
            str(paths["output_root"]),
        ]
    )

    with pytest.raises(ValueError, match="Missing --stress-output-dir"):
        pipeline.run_pipeline(args)


def test_missing_cost_config_fails_clearly(tmp_path: Path) -> None:
    paths = make_inputs(tmp_path)
    args = pipeline.build_parser().parse_args(
        [
            "--dry-run",
            "--stress-output-dir",
            str(paths["stress_output_dir"]),
            "--db-path",
            str(paths["db_path"]),
            "--stress-cost-config",
            str(paths["stress_cost_config"]),
            "--output-root",
            str(paths["output_root"]),
        ]
    )

    with pytest.raises(ValueError, match="Missing --cost-config"):
        pipeline.run_pipeline(args)


def test_invalid_cost_config_json_fails_clearly(tmp_path: Path) -> None:
    args, paths = parse_valid_args(tmp_path)
    paths["cost_config"].write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid --cost-config JSON"):
        pipeline.run_pipeline(args)


def test_existing_output_dir_without_overwrite_fails(tmp_path: Path) -> None:
    args, paths = parse_valid_args(tmp_path)
    (paths["output_root"] / "unit_audit_run").mkdir(parents=True)

    with pytest.raises(FileExistsError, match="Output directory already exists"):
        pipeline.run_pipeline(args)


def test_existing_output_dir_with_overwrite_succeeds(tmp_path: Path) -> None:
    args, paths = parse_valid_args(tmp_path, "--overwrite")
    output_dir = paths["output_root"] / "unit_audit_run"
    output_dir.mkdir(parents=True)
    marker = output_dir / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")

    outputs = pipeline.run_pipeline(args)

    assert outputs["manifest"].is_file()
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_manifest_includes_all_default_planned_stages(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path)

    outputs = pipeline.run_pipeline(args)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["planned_stages"] == [spec.stage for spec in pipeline.STAGE_SPECS]
    assert manifest["status"] == "dry_run"
    assert manifest["pipeline_scope"] == "candidate_audit_research_orchestration"
    assert manifest["aggregated_stage_status"] in {"dry_run", "partial"}


def test_manifest_includes_execution_ready_stage_metadata(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path)

    outputs = pipeline.run_pipeline(args)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    metadata = {row["stage"]: row for row in manifest["stage_metadata"]}

    assert set(metadata) == {spec.stage for spec in pipeline.STAGE_SPECS}
    for stage in REQUIRED_STAGES:
        assert metadata[stage]["required"] is True
        assert metadata[stage]["conditional"] is False
    for stage in CONDITIONAL_STAGES:
        assert metadata[stage]["required"] is False
        assert metadata[stage]["conditional"] is True
        assert metadata[stage]["condition_source_stage"]
        assert metadata[stage]["condition_label_column"]
        assert metadata[stage]["condition_expected_values"]
        assert metadata[stage]["skip_if_condition_not_met"] is True


def test_command_plan_includes_expected_child_scripts(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path)

    outputs = pipeline.run_pipeline(args)
    rows = list(csv.DictReader(outputs["command_plan"].open("r", encoding="utf-8")))
    command_text = "\n".join(row["command"] for row in rows)

    assert rows
    assert list(rows[0]) == pipeline.COMMAND_PLAN_FIELDNAMES
    assert rows[0]["command_order"] == "1"
    assert rows[0]["stage_name"] == rows[0]["stage"]
    for spec in pipeline.STAGE_SPECS:
        assert spec.script_name in command_text


def test_command_plan_marks_required_and_conditional_stages(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path)

    outputs = pipeline.run_pipeline(args)
    rows = list(csv.DictReader(outputs["command_plan"].open("r", encoding="utf-8")))
    by_stage = {row["stage"]: row for row in rows}

    assert list(rows[0]) == pipeline.COMMAND_PLAN_FIELDNAMES
    for stage in REQUIRED_STAGES:
        assert by_stage[stage]["required"] == "true"
        assert by_stage[stage]["conditional"] == "false"
        assert by_stage[stage]["condition_source_stage"] == ""
        assert by_stage[stage]["skip_if_condition_not_met"] == "false"
    for stage in CONDITIONAL_STAGES:
        assert by_stage[stage]["required"] == "false"
        assert by_stage[stage]["conditional"] == "true"
        assert by_stage[stage]["condition_source_stage"]
        assert by_stage[stage]["condition_label_column"]
        assert by_stage[stage]["condition_expected_values"]
        assert by_stage[stage]["skip_if_condition_not_met"] == "true"


def test_summary_has_dry_run_final_classification(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path)

    outputs = pipeline.run_pipeline(args)
    rows = list(csv.DictReader(outputs["summary"].open("r", encoding="utf-8")))

    assert rows[0]["final_classification"] == pipeline.FINAL_CLASSIFICATION
    assert rows[0]["decision_scope"] == pipeline.DECISION_SCOPE
    assert rows[0]["pipeline_scope"] == "candidate_audit_research_orchestration"
    assert rows[0]["dry_run"] == "true"
    assert rows[0]["next_action"] == pipeline.NEXT_ACTION
    assert "--execute" in rows[0]["next_action"]
    assert "user-run only" in rows[0]["next_action"]
    assert rows[0]["required_stage_count"] == str(len(REQUIRED_STAGES))
    assert rows[0]["conditional_stage_count"] == str(len(CONDITIONAL_STAGES))
    assert int(rows[0]["warnings_count"]) == (
        int(rows[0]["blocking_warnings_count"]) + int(rows[0]["non_blocking_warnings_count"])
    )


def test_skip_timeout_policy_sensitivity_marks_stage_skipped_and_omits_gate_input(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path, "--skip-timeout-policy-sensitivity")

    outputs = pipeline.run_pipeline(args)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    rows = list(csv.DictReader(outputs["command_plan"].open("r", encoding="utf-8")))
    by_stage = {row["stage"]: row for row in rows}

    assert "timeout_policy_sensitivity" not in manifest["planned_stages"]
    assert manifest["skipped_stages"] == [
        {
            "stage": "timeout_policy_sensitivity",
            "reason": "Skipped by explicit dry-run planning flag.",
        }
    ]
    skipped_metadata = [
        row for row in manifest["stage_metadata"]
        if row["stage"] == "timeout_policy_sensitivity"
    ][0]
    assert skipped_metadata["planned"] is False
    assert skipped_metadata["conditional"] is True
    assert "--timeout-policy-sensitivity-dir" not in by_stage["gate_decision"]["command"]


def test_timeout_policy_never_still_plans_potential_stage_without_skip_flag(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path, "--timeout-policy", "never")

    outputs = pipeline.run_pipeline(args)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert "timeout_policy_sensitivity" in manifest["planned_stages"]
    assert manifest["skipped_stages"] == []


def test_forbidden_actions_are_present_in_report(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path)

    outputs = pipeline.run_pipeline(args)
    report = outputs["report"].read_text(encoding="utf-8")

    for action in pipeline.FORBIDDEN_ACTIONS:
        assert action in report


def test_dry_run_report_and_warning_describe_execute_mode_without_running_it(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path)

    outputs = pipeline.run_pipeline(args)
    report = outputs["report"].read_text(encoding="utf-8")
    warnings = list(csv.DictReader(outputs["warnings"].open("r", encoding="utf-8")))
    dry_run_warning = [
        row for row in warnings
        if row["warning_code"] == "DRY_RUN_ONLY_EXECUTION_NOT_RUN"
    ][0]

    assert "Execution mode exists" in report
    assert "requires explicit --execute" in report
    assert "user-run only for heavy stages" in report
    assert "Execution requires explicit --execute" in dry_run_warning["message"]
    assert dry_run_warning["blocking"] == "False"


def test_wrapper_uses_research_pipeline_utils_and_no_ad_hoc_subprocess_logic() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")

    assert "PipelineCommand" in source
    assert "write_manifest" in source
    assert "write_command_plan_csv" in source
    assert "ensure_output_dir" in source
    assert "run_command(" in source
    assert "subprocess.run" not in source


def test_warnings_use_common_schema(tmp_path: Path) -> None:
    args, _paths = parse_valid_args(tmp_path)

    outputs = pipeline.run_pipeline(args)
    rows = list(csv.DictReader(outputs["warnings"].open("r", encoding="utf-8")))

    assert rows
    assert list(rows[0]) == pipeline.COMMON_WARNING_FIELDNAMES
