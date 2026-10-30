from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import run_fixed_candidate_artifact_aware_candidate_audit as audit


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


def write_artifact(
    directory: Path,
    *,
    spec: audit.ArtifactSpec,
    rows: list[dict[str, object]],
    manifest: dict[str, object] | None = None,
    report_text: str = "# Fixture report\n",
) -> None:
    fieldnames = sorted({key for row in rows for key in row}) or ["status"]
    write_csv(directory / spec.csv_name, fieldnames, rows)
    write_csv(directory / spec.warnings_name, ["warning_code", "blocking_warning"], [])
    base_manifest = {
        "run_id": "fixture",
        "warnings_count": 0,
        "blocking_warnings_count": 0,
    }
    if manifest:
        base_manifest.update(manifest)
    (directory / spec.manifest_name).write_text(json.dumps(base_manifest), encoding="utf-8")
    (directory / spec.report_name).write_text(report_text, encoding="utf-8")


def write_all_artifacts(
    tmp_path: Path,
    *,
    omit: str | None = None,
    execution_blocker: bool = False,
    risk_framing: bool = True,
) -> dict[str, Path]:
    dirs = {
        "formal_packet": tmp_path / "formal_packet",
        "execution_plan": tmp_path / "execution_plan",
        "readiness": tmp_path / "readiness",
        "research_packet": tmp_path / "research_packet",
        "split_review": tmp_path / "split_review",
        "timeout_review": tmp_path / "timeout_review",
        "equity_review": tmp_path / "equity_review",
        "comparison": tmp_path / "comparison",
        "r_review": tmp_path / "r_review",
        "old_audit": tmp_path / "old_audit",
    }
    if omit != "formal_packet":
        formal_label = "risk_filtered_candidate_framing_required" if risk_framing else "manual_review_required"
        write_artifact(
            dirs["formal_packet"],
            spec=audit.SPECS["formal_packet"],
            rows=[
                {
                    "audit_area": "risk_filtered_candidate_framing",
                    "key_evidence_label": formal_label,
                    "audit_packet_status": "audit_packet_ready_with_caveats",
                }
            ],
            manifest={
                "audit_packet_row_count": 13,
                "blocked_missing_required_artifact_count": 0,
                "blocked_unreadable_input_count": 0,
                "blocking_warnings_count": 0,
            },
            report_text="# Formal packet\nrisk-filtered candidate\n" if risk_framing else "# Formal packet\n",
        )
    if omit != "execution_plan":
        write_artifact(
            dirs["execution_plan"],
            spec=audit.SPECS["execution_plan"],
            rows=[{"plan_step": "formal_packet_gate_check", "command_status": "no_command_needed"}],
            manifest={
                "plan_row_count": 9,
                "packet_blockers_present": execution_blocker,
                "risk_filtered_framing_present": risk_framing,
                audit.DECISION_ABSENT_KEY: not execution_blocker,
                "blocking_warnings_count": 1 if execution_blocker else 0,
                "warnings_count": 1 if execution_blocker else 0,
            },
        )
    if omit != "readiness":
        write_artifact(
            dirs["readiness"],
            spec=audit.SPECS["readiness"],
            rows=[{"readiness_block": "candidate_audit_planning_readiness"}],
            manifest={"readiness_row_count": 10, "warnings_count": 0, "blocking_warnings_count": 0},
        )
    if omit != "research_packet":
        write_artifact(
            dirs["research_packet"],
            spec=audit.SPECS["research_packet"],
            rows=[
                {
                    "review_block": "key_tradeoff_summary",
                    "descriptive_summary": "exact_lower_drawdown_observed;average_edge_not_clearly_higher_for_exact",
                    "key_metric_2_name": "delta_mean_R",
                    "key_metric_2_value": "-0.01",
                    "key_metric_3_name": "delta_max_drawdown_R",
                    "key_metric_3_value": "-12.4",
                }
            ],
            manifest={"review_packet_row_count": 13},
        )
    if omit != "split_review":
        write_artifact(
            dirs["split_review"],
            spec=audit.SPECS["split_review"],
            rows=[{"review_scope": "walk_forward_split_summary"}],
            manifest={
                "matched_split_count": 5,
                "exact_lower_drawdown_split_count": 5,
                "exact_mean_R_higher_split_count": 2,
                "exact_profit_factor_higher_split_count": 1,
            },
        )
    if omit != "timeout_review":
        write_artifact(
            dirs["timeout_review"],
            spec=audit.SPECS["timeout_review"],
            rows=[
                {
                    "review_scope": "exact_vs_single_filter_a_base_timeout_comparison",
                    "timeout_rate_delta": "0.025",
                    "timeout_mean_net_R_delta": "0.029",
                }
            ],
            manifest={"review_row_count": 15},
        )
    if omit != "equity_review":
        write_artifact(
            dirs["equity_review"],
            spec=audit.SPECS["equity_review"],
            rows=[
                {
                    "review_scope": "exact_vs_single_filter_a_base_drawdown_sequence_comparison",
                    "drawdown_delta": "-12.4",
                    "drawdown_duration_delta": "-17.0",
                    "longest_negative_streak_delta": "-10.0",
                }
            ],
            manifest={"review_row_count": 8},
        )
    if omit != "comparison":
        write_artifact(
            dirs["comparison"],
            spec=audit.SPECS["comparison"],
            rows=[{"row_type": "exact_rule", "metric_namespace": "R_multiple"}],
            manifest={"metric_namespaces": ["R_multiple"], "comparison_row_count": 8},
        )
    if omit != "r_review":
        write_artifact(
            dirs["r_review"],
            spec=audit.SPECS["r_review"],
            rows=[{"review_scope": "exact_vs_single_filter_a"}],
            manifest={"review_row_count": 10},
        )
    if omit != "old_audit":
        write_artifact(
            dirs["old_audit"],
            spec=audit.SPECS["old_audit"],
            rows=[{"final_classification": "CANDIDATE_AUDIT_PIPELINE_COMPLETED"}],
            manifest={"final_classification": "CANDIDATE_AUDIT_PIPELINE_COMPLETED"},
        )
    return dirs


def make_args(
    tmp_path: Path,
    *,
    omit: str | None = None,
    execution_blocker: bool = False,
    risk_framing: bool = True,
) -> object:
    dirs = write_all_artifacts(
        tmp_path,
        omit=omit,
        execution_blocker=execution_blocker,
        risk_framing=risk_framing,
    )
    return audit.build_parser().parse_args(
        [
            "--run-id",
            "unit_artifact_aware_candidate_audit",
            "--formal-candidate-audit-packet-dir",
            str(dirs["formal_packet"]),
            "--candidate-audit-execution-plan-dir",
            str(dirs["execution_plan"]),
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
            "--comparison-table-dir",
            str(dirs["comparison"]),
            "--r-multiple-review-dir",
            str(dirs["r_review"]),
            "--old-candidate-audit-dir",
            str(dirs["old_audit"]),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        audit.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path))

    assert outputs["audit"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_required_artifacts_are_read_from_fixture_dirs(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["audit"])
    areas = {row["audit_area"] for row in rows}

    assert "formal_packet_gate_check" in areas
    assert "execution_plan_gate_check" in areas
    assert "risk_filtered_framing_check" in areas
    assert "deeper_walkforward_split_audit" in areas
    assert "timeout_artifact_audit" in areas
    assert "equity_drawdown_sequence_audit" in areas


def test_missing_required_formal_packet_creates_blocked_missing_required_artifact(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path, omit="formal_packet"))
    rows = read_csv(outputs["audit"])
    warnings = read_csv(outputs["warnings"])
    formal = next(row for row in rows if row["audit_area"] == "formal_packet_gate_check")
    summary = next(row for row in rows if row["audit_area"] == "candidate_audit_status_summary")

    assert formal["artifact_status"] == "missing"
    assert formal["audit_status"] == "blocked_missing_required_artifact"
    assert summary["audit_status"] == "blocked_missing_required_artifact"
    assert any(row["warning_code"] == "formal_packet_gate_check_missing" for row in warnings)


def test_execution_plan_blockers_create_blocked_status(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path, execution_blocker=True))
    rows = read_csv(outputs["audit"])
    warnings = read_csv(outputs["warnings"])
    execution = next(row for row in rows if row["audit_area"] == "execution_plan_gate_check")

    assert execution["audit_status"] == "blocked_missing_required_artifact"
    assert any(row["warning_code"] == "execution_plan_gate_blocked" for row in warnings)
    assert any(row["blocking_warning"] == "true" for row in warnings)


def test_risk_filtered_framing_is_preserved(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path, risk_framing=True))
    rows = read_csv(outputs["audit"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    framing = next(row for row in rows if row["audit_area"] == "risk_filtered_framing_check")

    assert framing["key_evidence_label"] == "risk_filtered_candidate_framing_preserved"
    assert framing["key_evidence_value"] == "true"
    assert manifest["risk_filtered_framing_present"] is True


def test_decision_absence_is_verified(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest[audit.DECISION_ABSENT_KEY] is True


def test_old_candidate_audit_is_context_only(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["audit"])
    old = next(row for row in rows if row["audit_area"] == "old_candidate_audit_context")

    assert old["artifact_status"] == "available_with_caveat"
    assert old["evidence_status"] == "context_only"
    assert old["audit_status"] == "context_only"
    assert old["key_evidence_label"] == "old_candidate_audit_context_only"


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["audit"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["audit_row_count"] == len(rows)
    assert manifest["available_count"] == sum(row["artifact_status"] == "available" for row in rows)
    assert manifest["available_with_caveat_count"] == sum(
        row["artifact_status"] == "available_with_caveat" for row in rows
    )
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["old_candidate_audit_context_only"] is True
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_candidate_audit_pipeline_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_walk_forward_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_timeout_policy_review_executed"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest[audit.NO_CANDIDATE_QUALITY_DECISION_KEY] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_artifact_aware_and_no_final_research_decision_caveats(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-aware candidate audit only" in report
    assert "No final research decision was made." in report
    assert "No trading decision was made." in report
    assert "final research decision remains separate" in report


def test_report_includes_risk_filtered_candidate_framing(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "risk-filtered candidate" in report
    assert "not clearly superior average-edge candidate" in report
    assert "exact lower drawdown in `5/5` deeper walk-forward splits" in report


def test_csv_preserves_source_paths(tmp_path: Path) -> None:
    outputs = audit.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["audit"])
    formal = next(row for row in rows if row["audit_area"] == "formal_packet_gate_check")
    split = next(row for row in rows if row["audit_area"] == "deeper_walkforward_split_audit")

    assert formal["source_dir"].endswith("formal_packet")
    assert formal["source_csv"].endswith(audit.SPECS["formal_packet"].csv_name)
    assert split["source_dir"].endswith("split_review")


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    audit.build_outputs(make_args(tmp_path))
