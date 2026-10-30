from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_candidate_audit_readiness as readiness


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
    (directory / spec.report_name).write_text("# Fixture report\n", encoding="utf-8")


def write_all_artifacts(tmp_path: Path, *, omit: str | None = None) -> dict[str, Path]:
    dirs = {
        "research_packet": tmp_path / "research_packet",
        "split_review": tmp_path / "split_review",
        "timeout_review": tmp_path / "timeout_review",
        "equity_review": tmp_path / "equity_review",
        "comparison": tmp_path / "comparison",
        "r_review": tmp_path / "r_review",
        "old_audit": tmp_path / "old_audit",
    }
    if omit != "research_packet":
        write_artifact(
            dirs["research_packet"],
            spec=readiness.SPECS["research_packet"],
            rows=[
                {
                    "review_block": "exact_vs_single_filter_a_review",
                    "key_metric_2_value": "-0.01",
                    "key_metric_3_value": "-12.4",
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
                "walk_forward_split_comparison_count": 5,
                "exact_lower_drawdown_split_count": 5,
                "exact_mean_R_higher_split_count": 2,
                "exact_profit_factor_higher_split_count": 1,
                "warnings_count": 0,
                "blocking_warnings_count": 0,
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
                    "longest_negative_streak_delta": "-10.0",
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
            rows=[
                {
                    "final_classification": "CANDIDATE_AUDIT_PIPELINE_COMPLETED",
                    "decision_scope": "candidate_audit_pipeline",
                }
            ],
            manifest={"final_classification": "CANDIDATE_AUDIT_PIPELINE_COMPLETED"},
        )
    return dirs


def make_args(tmp_path: Path, *, omit: str | None = None) -> object:
    dirs = write_all_artifacts(tmp_path, omit=omit)
    return readiness.build_parser().parse_args(
        [
            "--run-id",
            "unit_candidate_audit_readiness",
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
    blocks = {row["readiness_block"] for row in rows}

    assert "artifact_chain_integrity" in blocks
    assert "exact_vs_single_filter_a_ablation_readiness" in blocks
    assert "deeper_walkforward_split_readiness" in blocks
    assert "timeout_artifact_readiness" in blocks
    assert "equity_drawdown_sequence_readiness" in blocks
    assert "candidate_audit_planning_readiness" in blocks
    assert all(row["artifact_status"] != "missing" for row in rows)


def test_missing_required_artifact_creates_blocked_missing_required_artifact(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, omit="timeout_review"))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    timeout = next(row for row in rows if row["readiness_block"] == "timeout_artifact_readiness")
    planning = next(row for row in rows if row["readiness_block"] == "candidate_audit_planning_readiness")

    assert timeout["artifact_status"] == "missing"
    assert timeout["readiness_status"] == "blocked_missing_required_artifact"
    assert timeout["blocking_warning"] == "true"
    assert planning["readiness_status"] == "blocked_missing_required_artifact"
    assert any(row["warning_code"] == "timeout_artifact_readiness_missing" for row in warnings)


def test_optional_old_candidate_audit_missing_is_context_not_blocker(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, omit="old_audit"))
    rows = read_csv(outputs["readiness"])
    old = next(row for row in rows if row["readiness_block"] == "old_candidate_audit_context")
    planning = next(row for row in rows if row["readiness_block"] == "candidate_audit_planning_readiness")

    assert old["artifact_status"] == "optional_missing"
    assert old["evidence_status"] == "context_only"
    assert old["readiness_status"] == "context_only"
    assert old["blocking_warning"] == "false"
    assert planning["readiness_status"] == "ready_with_caveat_for_candidate_audit_planning"


def test_readiness_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, omit="old_audit"))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["readiness_row_count"] == len(rows)
    assert manifest["available_count"] == sum(row["artifact_status"] == "available" for row in rows)
    assert manifest["available_with_caveat_count"] == sum(
        row["artifact_status"] == "available_with_caveat" for row in rows
    )
    assert manifest["optional_missing_count"] == sum(row["artifact_status"] == "optional_missing" for row in rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_candidate_audit_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_walk_forward_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_timeout_policy_review_executed"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_old_audit_context_only_caveat(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "old candidate audit is context-only" in report
    assert "does not consume the newer fixed-candidate evidence chain" in report


def test_report_includes_no_decision_caveats(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")
    lowered = report.lower()

    assert "Artifact-only candidate-audit readiness review" in report
    assert "No candidate-quality conclusion or trading decision was made." in report
    assert "formal candidate audit is still separate" in report
    assert "build_fixed_candidate_candidate_audit_command_plan.py" in report
    for forbidden in ("approved", "rejected", "profitable", "strategy_ready", "deploy", "buy", "sell"):
        assert forbidden not in lowered


def test_csv_preserves_source_paths(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    split = next(row for row in rows if row["readiness_block"] == "deeper_walkforward_split_readiness")

    assert split["source_dir"].endswith("split_review")
    assert split["source_manifest"].endswith(readiness.SPECS["split_review"].manifest_name)
    assert split["source_report"].endswith(readiness.SPECS["split_review"].report_name)
    assert split["source_csv"].endswith(readiness.SPECS["split_review"].csv_name)


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    readiness.build_outputs(make_args(tmp_path))
