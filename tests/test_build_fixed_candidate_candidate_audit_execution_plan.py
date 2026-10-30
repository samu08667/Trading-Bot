from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_candidate_audit_execution_plan as execution_plan


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_formal_packet_dir(
    path: Path,
    *,
    blockers: bool = False,
    risk_framing: bool = True,
    decision_marker: bool = False,
) -> None:
    label = "risk_filtered_candidate_framing_required" if risk_framing else "manual_review_required"
    if decision_marker:
        label = f"{label};final_decision"
    write_csv(
        path / execution_plan.PACKET_CSV,
        ["audit_area", "key_evidence_label", "audit_packet_status", "blocking_warning"],
        [
            {
                "audit_area": "risk_filtered_candidate_framing",
                "key_evidence_label": label,
                "audit_packet_status": (
                    "blocked_missing_required_artifact" if blockers else "audit_packet_ready_with_caveats"
                ),
                "blocking_warning": "true" if blockers else "false",
            }
        ],
    )
    (path / execution_plan.PACKET_MANIFEST).write_text(
        json.dumps(
            {
                "audit_packet_row_count": 13,
                "blocked_missing_required_artifact_count": 1 if blockers else 0,
                "blocked_unreadable_input_count": 0,
                "blocking_warnings_count": 1 if blockers else 0,
                "warnings_count": 1 if blockers else 0,
            }
        ),
        encoding="utf-8",
    )
    report = "# Formal packet\n"
    if risk_framing:
        report += "risk-filtered candidate\n"
    if decision_marker:
        report += "final_decision\n"
    (path / execution_plan.PACKET_REPORT).write_text(report, encoding="utf-8")
    write_csv(
        path / execution_plan.PACKET_WARNINGS,
        ["warning_code", "blocking_warning"],
        [{"warning_code": "blocked", "blocking_warning": "true"}] if blockers else [],
    )


def write_script(path: Path, flags: tuple[str, ...]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(flags), encoding="utf-8")
    return path


def write_context_dirs(tmp_path: Path, *, blockers: bool = False, risk_framing: bool = True) -> dict[str, Path]:
    dirs = {
        "packet": tmp_path / "packet",
        "command_plan": tmp_path / "command_plan",
        "readiness": tmp_path / "readiness",
        "research_packet": tmp_path / "research_packet",
        "split_review": tmp_path / "split_review",
        "timeout_review": tmp_path / "timeout_review",
        "equity_review": tmp_path / "equity_review",
        "old_audit": tmp_path / "old_audit",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    write_formal_packet_dir(dirs["packet"], blockers=blockers, risk_framing=risk_framing)
    return dirs


def make_args(
    tmp_path: Path,
    *,
    artifact_script_exists: bool = False,
    artifact_script_compatible: bool = True,
    blockers: bool = False,
    risk_framing: bool = True,
    old_compatible: bool = False,
) -> object:
    dirs = write_context_dirs(tmp_path, blockers=blockers, risk_framing=risk_framing)
    artifact_script = tmp_path / "scripts" / "run_fixed_candidate_artifact_aware_candidate_audit.py"
    if artifact_script_exists:
        flags = (
            execution_plan.ARTIFACT_AWARE_REQUIRED_FLAGS
            if artifact_script_compatible
            else ("--run-id", "--output-dir")
        )
        write_script(artifact_script, flags)
    old_script = tmp_path / "scripts" / "run_candidate_audit_pipeline.py"
    old_flags = execution_plan.FORMAL_PACKET_CONTRACT_FLAGS if old_compatible else ("--db-path", "--run-id")
    write_script(old_script, old_flags)
    return execution_plan.build_parser().parse_args(
        [
            "--run-id",
            "unit_candidate_audit_execution_plan",
            "--formal-candidate-audit-packet-dir",
            str(dirs["packet"]),
            "--candidate-audit-command-plan-dir",
            str(dirs["command_plan"]),
            "--candidate-audit-readiness-dir",
            str(dirs["readiness"]),
            "--research-review-packet-dir",
            str(dirs["research_packet"]),
            "--deeper-walkforward-split-review-dir",
            str(dirs["split_review"]),
            "--timeout-artifact-review-dir",
            str(dirs["timeout_review"]),
            "--equity-drawdown-sequence-review-dir",
            str(dirs["equity_review"]),
            "--old-candidate-audit-dir",
            str(dirs["old_audit"]),
            "--artifact-aware-audit-script",
            str(artifact_script),
            "--old-candidate-audit-script",
            str(old_script),
            "--python-executable",
            "python",
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        execution_plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(make_args(tmp_path))

    assert outputs["execution_plan"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_formal_packet_with_no_blockers_creates_gate_row(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["execution_plan"])
    gate = next(row for row in rows if row["plan_step"] == "formal_packet_gate_check")

    assert gate["plan_role"] == "packet_gate"
    assert gate["command_status"] == "no_command_needed"
    assert gate["packet_status"] == "formal_packet_no_blockers"
    assert "formal_packet_no_blockers" in gate["caveat"]


def test_risk_filtered_framing_is_detected_and_preserved(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(make_args(tmp_path, risk_framing=True))
    rows = read_csv(outputs["execution_plan"])
    framing = next(row for row in rows if row["plan_step"] == "risk_filtered_framing_check")
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert framing["command_status"] == "no_command_needed"
    assert "risk_filtered_candidate_framing_preserved" in framing["caveat"]
    assert manifest["risk_filtered_framing_present"] is True


def test_final_decision_absence_is_checked(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["execution_plan"])
    absence = next(row for row in rows if row["plan_step"] == "final_decision_absence_check")
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert absence["command_status"] == "no_command_needed"
    assert "no_final_decision_in_packet" in absence["caveat"]
    assert manifest["final_decision_absent"] is True


def test_missing_artifact_aware_audit_script_creates_implementation_required_row(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(make_args(tmp_path, artifact_script_exists=False))
    rows = read_csv(outputs["execution_plan"])
    script_status = next(row for row in rows if row["plan_step"] == "artifact_aware_audit_script_status")

    assert script_status["artifact_status"] == "missing"
    assert script_status["command_status"] == "implementation_required"
    assert script_status["warning_code"] == "artifact_aware_audit_script_missing"


def test_existing_compatible_artifact_aware_audit_script_creates_planned_manual_command(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(
        make_args(tmp_path, artifact_script_exists=True, artifact_script_compatible=True)
    )
    rows = read_csv(outputs["execution_plan"])
    command = next(row for row in rows if row["plan_step"] == "artifact_aware_audit_command")

    assert command["command_status"] == "planned_manual_command"
    assert command["compatibility_status"] == "compatible_with_formal_packet"
    assert "--formal-candidate-audit-packet-dir" in command["manual_command"]
    assert "--candidate-audit-readiness-dir" in command["manual_command"]
    assert "--research-review-packet-dir" in command["manual_command"]
    assert "--output-dir" in command["manual_command"]
    assert "--run-id" in command["manual_command"]


def test_old_candidate_audit_script_is_context_only_by_default(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["execution_plan"])
    legacy = next(row for row in rows if row["plan_step"] == "legacy_candidate_audit_context")

    assert legacy["plan_role"] == "legacy_context"
    assert legacy["command_status"] == "context_only_no_command"
    assert legacy["compatibility_status"] == "context_only"
    assert legacy["manual_command"] == ""


def test_packet_blockers_create_blocked_rows_and_no_planned_command(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(
        make_args(tmp_path, artifact_script_exists=True, blockers=True)
    )
    rows = read_csv(outputs["execution_plan"])
    warnings = read_csv(outputs["warnings"])

    assert any(row["command_status"] == "blocked_by_packet" for row in rows)
    assert not any(row["command_status"] == "planned_manual_command" for row in rows)
    assert any(row["warning_code"] == "formal_packet_blockers_present" for row in warnings)
    assert any(row["blocking_warning"] == "true" for row in warnings)


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(
        make_args(tmp_path, artifact_script_exists=True, artifact_script_compatible=True)
    )
    rows = read_csv(outputs["execution_plan"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["plan_row_count"] == len(rows)
    assert manifest["planned_manual_command_count"] == sum(
        row["command_status"] == "planned_manual_command" for row in rows
    )
    assert manifest["implementation_required_count"] == sum(
        row["command_status"] == "implementation_required" for row in rows
    )
    assert manifest["context_only_count"] == sum(row["command_status"] == "context_only_no_command" for row in rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["old_candidate_audit_context_only"] is True
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_candidate_audit_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_walk_forward_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_timeout_policy_review_executed"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_command_plan_only_and_no_decision_caveats(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Command-plan-only artifact" in report
    assert "No candidate-quality conclusion or trading decision was made." in report
    assert "old candidate audit remains context-only" in report
    assert "run_fixed_candidate_artifact_aware_candidate_audit.py" in report


def test_csv_preserves_source_paths(tmp_path: Path) -> None:
    outputs = execution_plan.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["execution_plan"])
    gate = next(row for row in rows if row["plan_step"] == "formal_packet_gate_check")
    script_status = next(row for row in rows if row["plan_step"] == "artifact_aware_audit_script_status")

    assert gate["source_dir"].endswith("packet")
    assert script_status["source_script"].endswith("run_fixed_candidate_artifact_aware_candidate_audit.py")
    assert script_status["expected_output_dir"].endswith("manual_artifact_aware_audit")


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    execution_plan.build_outputs(make_args(tmp_path, artifact_script_exists=True))
