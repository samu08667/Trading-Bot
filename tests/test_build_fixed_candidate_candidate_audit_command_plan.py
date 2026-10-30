from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_candidate_audit_command_plan as command_plan


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


def write_readiness_dir(path: Path, *, blockers: bool = False) -> None:
    write_csv(
        path / command_plan.READINESS_CSV,
        ["readiness_block", "readiness_status", "blocking_warning"],
        [
            {
                "readiness_block": "candidate_audit_planning_readiness",
                "readiness_status": (
                    "blocked_missing_required_artifact"
                    if blockers
                    else "ready_with_caveat_for_candidate_audit_planning"
                ),
                "blocking_warning": "true" if blockers else "false",
            }
        ],
    )
    (path / command_plan.READINESS_MANIFEST).write_text(
        json.dumps(
            {
                "blocked_missing_required_artifact_count": 1 if blockers else 0,
                "blocked_unreadable_input_count": 0,
                "blocking_warnings_count": 1 if blockers else 0,
                "warnings_count": 1 if blockers else 0,
            }
        ),
        encoding="utf-8",
    )
    (path / command_plan.READINESS_REPORT).write_text("# Readiness\n", encoding="utf-8")
    write_csv(
        path / command_plan.READINESS_WARNINGS,
        ["warning_code", "blocking_warning"],
        [{"warning_code": "blocked", "blocking_warning": "true"}] if blockers else [],
    )


def write_context_dirs(tmp_path: Path) -> dict[str, Path]:
    dirs = {
        "readiness": tmp_path / "readiness",
        "research_packet": tmp_path / "research_packet",
        "split_review": tmp_path / "split_review",
        "timeout_review": tmp_path / "timeout_review",
        "equity_review": tmp_path / "equity_review",
        "old_audit": tmp_path / "old_audit",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    write_readiness_dir(dirs["readiness"])
    return dirs


def write_formal_script(path: Path, *, compatible: bool = True) -> Path:
    flags = command_plan.FORMAL_AUDIT_REQUIRED_FLAGS if compatible else ("--run-id", "--output-dir")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(flags), encoding="utf-8")
    return path


def write_old_script(path: Path, *, compatible: bool = False) -> Path:
    flags = command_plan.NEW_EVIDENCE_CHAIN_FLAGS if compatible else ("--stress-output-dir", "--db-path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(flags), encoding="utf-8")
    return path


def make_args(
    tmp_path: Path,
    *,
    formal_exists: bool = False,
    formal_compatible: bool = True,
    blockers: bool = False,
    old_compatible: bool = False,
) -> object:
    dirs = write_context_dirs(tmp_path)
    if blockers:
        write_readiness_dir(dirs["readiness"], blockers=True)
    formal_script = tmp_path / "scripts" / "build_fixed_candidate_formal_candidate_audit_packet.py"
    if formal_exists:
        write_formal_script(formal_script, compatible=formal_compatible)
    old_script = write_old_script(tmp_path / "scripts" / "run_candidate_audit_pipeline.py", compatible=old_compatible)
    return command_plan.build_parser().parse_args(
        [
            "--run-id",
            "unit_candidate_audit_command_plan",
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
            "--formal-audit-packet-script",
            str(formal_script),
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
        command_plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = command_plan.build_outputs(make_args(tmp_path))

    assert outputs["command_plan"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_readiness_with_no_blockers_produces_readiness_gate_check_row(tmp_path: Path) -> None:
    outputs = command_plan.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["command_plan"])
    gate = next(row for row in rows if row["plan_step"] == "readiness_gate_check")

    assert gate["plan_role"] == "readiness_gate"
    assert gate["command_status"] == "no_command_needed"
    assert gate["readiness_status"] == "readiness_no_blockers"
    assert "readiness_no_blockers" in gate["caveat"]


def test_missing_formal_audit_packet_script_creates_implementation_required_row(tmp_path: Path) -> None:
    outputs = command_plan.build_outputs(make_args(tmp_path, formal_exists=False))
    rows = read_csv(outputs["command_plan"])
    status = next(row for row in rows if row["plan_step"] == "formal_audit_packet_script_status")

    assert status["artifact_status"] == "missing"
    assert status["command_status"] == "implementation_required"
    assert status["warning_code"] == "formal_audit_packet_script_missing"


def test_existing_compatible_formal_audit_packet_script_creates_planned_manual_command(tmp_path: Path) -> None:
    outputs = command_plan.build_outputs(make_args(tmp_path, formal_exists=True, formal_compatible=True))
    rows = read_csv(outputs["command_plan"])
    command = next(row for row in rows if row["plan_step"] == "formal_audit_packet_command")

    assert command["command_status"] == "planned_manual_command"
    assert command["compatibility_status"] == "compatible_with_new_evidence_chain"
    assert "--candidate-audit-readiness-dir" in command["manual_command"]
    assert "--research-review-packet-dir" in command["manual_command"]
    assert "--deeper-walkforward-split-review-dir" in command["manual_command"]
    assert "--timeout-artifact-review-dir" in command["manual_command"]
    assert "--equity-drawdown-sequence-review-dir" in command["manual_command"]


def test_old_candidate_audit_script_is_context_only_by_default(tmp_path: Path) -> None:
    outputs = command_plan.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["command_plan"])
    legacy = next(row for row in rows if row["plan_step"] == "legacy_candidate_audit_context")

    assert legacy["plan_role"] == "legacy_context"
    assert legacy["command_status"] == "context_only_no_command"
    assert legacy["compatibility_status"] == "context_only"
    assert legacy["manual_command"] == ""


def test_old_candidate_audit_command_is_not_emitted_when_cli_lacks_new_inputs(tmp_path: Path) -> None:
    outputs = command_plan.build_outputs(make_args(tmp_path, old_compatible=False))
    rows = read_csv(outputs["command_plan"])
    compat = next(row for row in rows if row["plan_step"] == "old_candidate_audit_compatibility_check")

    assert compat["compatibility_status"] == "not_compatible_with_new_evidence_chain"
    assert compat["command_status"] == "context_only_no_command"
    assert all("run_candidate_audit_pipeline.py" not in row["manual_command"] for row in rows)


def test_readiness_blockers_create_blocked_rows_and_no_planned_command(tmp_path: Path) -> None:
    outputs = command_plan.build_outputs(make_args(tmp_path, formal_exists=True, blockers=True))
    rows = read_csv(outputs["command_plan"])
    warnings = read_csv(outputs["warnings"])

    assert any(row["command_status"] == "blocked_by_readiness" for row in rows)
    assert not any(row["command_status"] == "planned_manual_command" for row in rows)
    assert any(row["warning_code"] == "readiness_blockers_present" for row in warnings)
    assert any(row["blocking_warning"] == "true" for row in warnings)


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = command_plan.build_outputs(make_args(tmp_path, formal_exists=True, formal_compatible=True))
    rows = read_csv(outputs["command_plan"])
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
    outputs = command_plan.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Command-plan-only artifact" in report
    assert "No candidate-quality conclusion or trading decision was made." in report
    assert "old candidate audit is context-only" in report
    assert "build_fixed_candidate_formal_candidate_audit_packet.py" in report


def test_csv_preserves_source_paths(tmp_path: Path) -> None:
    outputs = command_plan.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["command_plan"])
    gate = next(row for row in rows if row["plan_step"] == "readiness_gate_check")
    formal = next(row for row in rows if row["plan_step"] == "preferred_formal_audit_packet_path")

    assert gate["source_dir"].endswith("readiness")
    assert formal["source_script"].endswith("build_fixed_candidate_formal_candidate_audit_packet.py")
    assert formal["expected_output_dir"].endswith("manual_formal_audit_packet")


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    command_plan.build_outputs(make_args(tmp_path, formal_exists=True))
