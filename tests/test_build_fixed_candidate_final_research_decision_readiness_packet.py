from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_final_research_decision_readiness_packet as readiness


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
    spec: readiness.ArtifactSpec,
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
    audit_blocker: bool = False,
    risk_framing: bool = True,
) -> dict[str, Path]:
    dirs = {
        "artifact_audit": tmp_path / "artifact_audit",
        "formal_packet": tmp_path / "formal_packet",
        "readiness": tmp_path / "readiness",
        "research_packet": tmp_path / "research_packet",
        "split_review": tmp_path / "split_review",
        "timeout_review": tmp_path / "timeout_review",
        "equity_review": tmp_path / "equity_review",
        "comparison": tmp_path / "comparison",
        "r_review": tmp_path / "r_review",
        "old_audit": tmp_path / "old_audit",
    }
    if omit != "artifact_audit":
        audit_label = "risk_filtered_candidate_framing_preserved" if risk_framing else "manual_review_required_before_final_decision"
        write_artifact(
            dirs["artifact_audit"],
            spec=readiness.SPECS["artifact_audit"],
            rows=[
                {
                    "audit_area": "risk_filtered_framing_check",
                    "key_evidence_label": audit_label,
                    "audit_status": (
                        "blocked_missing_required_artifact"
                        if audit_blocker
                        else "candidate_audit_artifact_ready_with_caveats"
                    ),
                    "blocking_warning": "true" if audit_blocker else "false",
                }
            ],
            manifest={
                "audit_row_count": 13,
                "blocked_missing_required_artifact_count": 1 if audit_blocker else 0,
                "blocked_unreadable_input_count": 0,
                "blocking_warnings_count": 1 if audit_blocker else 0,
                "warnings_count": 1 if audit_blocker else 0,
                "risk_filtered_framing_present": risk_framing,
                readiness.DECISION_ABSENT_KEY: not audit_blocker,
                "old_candidate_audit_context_only": True,
                "candidate_audit_artifact_ready_for_manual_review_count": 9,
                "candidate_audit_artifact_ready_with_caveats_count": 3,
            },
            report_text="# Artifact-aware audit\nrisk-filtered candidate\n" if risk_framing else "# Artifact-aware audit\n",
        )
    if omit != "formal_packet":
        formal_label = "risk_filtered_candidate_framing_required" if risk_framing else "manual_review_required_before_final_decision"
        write_artifact(
            dirs["formal_packet"],
            spec=readiness.SPECS["formal_packet"],
            rows=[{"audit_area": "risk_filtered_candidate_framing", "key_evidence_label": formal_label}],
            manifest={
                "audit_packet_row_count": 13,
                "blocked_missing_required_artifact_count": 0,
                "blocked_unreadable_input_count": 0,
                "blocking_warnings_count": 0,
            },
            report_text="# Formal packet\nrisk-filtered candidate\n" if risk_framing else "# Formal packet\n",
        )
    if omit != "readiness":
        write_artifact(
            dirs["readiness"],
            spec=readiness.SPECS["readiness"],
            rows=[{"readiness_block": "candidate_audit_planning_readiness"}],
            manifest={"readiness_row_count": 10, "warnings_count": 0, "blocking_warnings_count": 0},
        )
    if omit != "research_packet":
        write_artifact(
            dirs["research_packet"],
            spec=readiness.SPECS["research_packet"],
            rows=[
                {
                    "review_block": "key_tradeoff_summary",
                    "descriptive_summary": "exact_lower_drawdown_observed;average_edge_not_clearly_higher_for_exact",
                }
            ],
            manifest={"review_packet_row_count": 13},
        )
    if omit != "split_review":
        write_artifact(
            dirs["split_review"],
            spec=readiness.SPECS["split_review"],
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
            spec=readiness.SPECS["timeout_review"],
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
            spec=readiness.SPECS["equity_review"],
            rows=[
                {
                    "review_scope": "exact_vs_single_filter_a_base_drawdown_sequence_comparison",
                    "drawdown_delta": "-12.4",
                    "drawdown_duration_delta": "-17.0",
                }
            ],
            manifest={"review_row_count": 8},
        )
    if omit != "comparison":
        write_artifact(
            dirs["comparison"],
            spec=readiness.SPECS["comparison"],
            rows=[{"row_type": "exact_rule", "metric_namespace": "R_multiple"}],
            manifest={"metric_namespaces": ["R_multiple"], "comparison_row_count": 8},
        )
    if omit != "r_review":
        write_artifact(
            dirs["r_review"],
            spec=readiness.SPECS["r_review"],
            rows=[{"review_scope": "exact_vs_single_filter_a"}],
            manifest={"review_row_count": 10},
        )
    if omit != "old_audit":
        write_artifact(
            dirs["old_audit"],
            spec=readiness.SPECS["old_audit"],
            rows=[{"final_classification": "CANDIDATE_AUDIT_PIPELINE_COMPLETED"}],
            manifest={"final_classification": "CANDIDATE_AUDIT_PIPELINE_COMPLETED"},
        )
    return dirs


def make_args(
    tmp_path: Path,
    *,
    omit: str | None = None,
    audit_blocker: bool = False,
    risk_framing: bool = True,
) -> object:
    dirs = write_all_artifacts(tmp_path, omit=omit, audit_blocker=audit_blocker, risk_framing=risk_framing)
    return readiness.build_parser().parse_args(
        [
            "--run-id",
            "unit_final_research_decision_readiness_packet",
            "--artifact-aware-candidate-audit-dir",
            str(dirs["artifact_audit"]),
            "--formal-candidate-audit-packet-dir",
            str(dirs["formal_packet"]),
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
        readiness.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))

    assert outputs["readiness"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_required_artifacts_are_read_from_fixture_dirs(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    areas = {row["readiness_area"] for row in rows}

    assert "artifact_aware_candidate_audit_status" in areas
    assert "formal_candidate_audit_packet_status" in areas
    assert "candidate_audit_readiness_status" in areas
    assert "deeper_walkforward_drawdown_status" in areas
    assert "timeout_caveat_status" in areas


def test_missing_required_artifact_creates_blocked_missing_required_artifact(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, omit="artifact_audit"))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    audit_row = next(row for row in rows if row["readiness_area"] == "artifact_aware_candidate_audit_status")
    boundary = next(row for row in rows if row["readiness_area"] == "final_research_decision_boundary")

    assert audit_row["artifact_status"] == "missing"
    assert audit_row["readiness_status"] == "blocked_missing_required_artifact"
    assert boundary["readiness_status"] == "blocked_missing_required_artifact"
    assert any(row["warning_code"] == "artifact_aware_candidate_audit_status_missing" for row in warnings)


def test_artifact_aware_audit_blockers_create_blocked_status(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, audit_blocker=True))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    audit_row = next(row for row in rows if row["readiness_area"] == "artifact_aware_candidate_audit_status")

    assert audit_row["readiness_status"] == "blocked_missing_required_artifact"
    assert any(row["warning_code"] == "artifact_aware_candidate_audit_blocked" for row in warnings)
    assert any(row["blocking_warning"] == "true" for row in warnings)


def test_risk_filtered_framing_is_preserved(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, risk_framing=True))
    rows = read_csv(outputs["readiness"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    framing = next(row for row in rows if row["readiness_area"] == "risk_filtered_framing_status")

    assert framing["key_evidence_label"] == "risk_filtered_candidate_framing_preserved"
    assert framing["key_evidence_value"] == "true"
    assert manifest["risk_filtered_framing_present"] is True


def test_decision_absence_is_verified(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest[readiness.DECISION_ABSENT_KEY] is True


def test_old_candidate_audit_is_context_only(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    old = next(row for row in rows if row["readiness_area"] == "old_candidate_audit_context_status")

    assert old["artifact_status"] == "available_with_caveat"
    assert old["evidence_status"] == "context_only"
    assert old["readiness_status"] == "context_only"
    assert old["key_evidence_label"] == "old_candidate_audit_context_only"


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["readiness_row_count"] == len(rows)
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
    assert manifest[readiness.NO_CANDIDATE_QUALITY_DECISION_KEY] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_readiness_only_caveat(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Final-research-decision-readiness only" in report
    assert "This is not a final research decision." in report


def test_report_includes_no_decision_and_no_trading_caveats(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No final research decision was made." in report
    assert "No trading decision was made." in report


def test_report_includes_risk_filtered_candidate_framing(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "risk-filtered candidate" in report
    assert "not clearly superior average-edge candidate" in report
    assert "exact lower drawdown in `5/5` deeper walk-forward splits" in report


def test_csv_preserves_source_paths(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    audit_row = next(row for row in rows if row["readiness_area"] == "artifact_aware_candidate_audit_status")
    split = next(row for row in rows if row["readiness_area"] == "deeper_walkforward_drawdown_status")

    assert audit_row["source_dir"].endswith("artifact_audit")
    assert audit_row["source_csv"].endswith(readiness.SPECS["artifact_audit"].csv_name)
    assert split["source_dir"].endswith("split_review")


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    readiness.build_outputs(make_args(tmp_path))
