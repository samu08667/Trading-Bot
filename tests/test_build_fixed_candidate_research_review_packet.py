from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_research_review_packet as packet


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
    spec: packet.ArtifactSpec,
    rows: list[dict[str, object]],
    manifest: dict[str, object] | None = None,
) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()}) or ["review_scope"]
    write_csv(directory / spec.csv_name, fieldnames, rows)
    write_csv(directory / spec.warnings_name, ["warning_code", "blocking_warning"], [])
    default_manifest = {
        "run_id": "fixture",
        "review_row_count": len(rows),
        "comparison_row_count": len(rows),
        "warnings_count": 0,
        "blocking_warnings_count": 0,
    }
    if manifest:
        default_manifest.update(manifest)
    (directory / spec.manifest_name).write_text(json.dumps(default_manifest), encoding="utf-8")
    (directory / spec.report_name).write_text("# Fixture report\n", encoding="utf-8")


def write_all_artifacts(tmp_path: Path, *, omit: str | None = None, include_optional: bool = True) -> dict[str, Path]:
    dirs = {
        "comparison": tmp_path / "comparison",
        "r_review": tmp_path / "r_review",
        "wf_readiness": tmp_path / "wf_readiness",
        "wf_review": tmp_path / "wf_review",
        "timeout_readiness": tmp_path / "timeout_readiness",
        "timeout_review": tmp_path / "timeout_review",
        "equity_review": tmp_path / "equity_review",
        "baseline_r_outputs": tmp_path / "baseline_r_outputs",
        "exact_stress": tmp_path / "exact_stress",
    }
    if omit != "comparison":
        write_artifact(
            dirs["comparison"],
            spec=packet.SPECS["comparison"],
            rows=[{"row_type": "exact_rule", "metric_namespace": "R_multiple"}],
            manifest={
                "comparison_row_count": 8,
                "metric_namespaces": ["R_multiple"],
                "mixed_metric_namespaces": False,
                "warnings_count": 0,
                "blocking_warnings_count": 0,
            },
        )
    if omit != "r_review":
        write_artifact(
            dirs["r_review"],
            spec=packet.SPECS["r_review"],
            rows=[
                {
                    "review_scope": "exact_vs_broad_regime_baseline",
                    "baseline_type": "broad_regime_baseline",
                    "cost_profile": "p75",
                    "trade_count_ratio_exact_to_baseline": "0.08",
                    "delta_mean_R": "0.20",
                    "delta_max_drawdown_R": "-40.0",
                },
                {
                    "review_scope": "exact_vs_single_filter_a",
                    "baseline_type": "single_filter_a",
                    "cost_profile": "p75",
                    "trade_count_ratio_exact_to_baseline": "0.27",
                    "delta_mean_R": "-0.01",
                    "delta_max_drawdown_R": "-12.0",
                },
                {
                    "review_scope": "exact_vs_single_filter_b",
                    "baseline_type": "single_filter_b",
                    "cost_profile": "p75",
                    "trade_count_ratio_exact_to_baseline": "0.29",
                    "delta_mean_R": "0.29",
                    "delta_max_drawdown_R": "-7.0",
                },
            ],
        )
    if omit != "wf_readiness":
        write_artifact(
            dirs["wf_readiness"],
            spec=packet.SPECS["wf_readiness"],
            rows=[{"review_scope": "next_review_area_readiness", "readiness_status": "ready_with_caveat"}],
            manifest={"review_row_count": 7, "warnings_count": 0, "blocking_warnings_count": 0},
        )
    if omit != "wf_review":
        write_artifact(
            dirs["wf_review"],
            spec=packet.SPECS["wf_review"],
            rows=[
                {
                    "review_scope": "exact_vs_single_filter_a_drawdown_review",
                    "exact_trades": "708",
                    "baseline_trades": "2595",
                    "baseline_max_drawdown_R": "20.6",
                }
            ],
            manifest={"review_row_count": 8, "warnings_count": 0, "blocking_warnings_count": 0},
        )
    if omit != "timeout_readiness":
        write_artifact(
            dirs["timeout_readiness"],
            spec=packet.SPECS["timeout_readiness"],
            rows=[{"review_scope": "exact_vs_single_filter_a_timeout_review_readiness", "readiness_status": "ready"}],
            manifest={"review_row_count": 6, "warnings_count": 0, "blocking_warnings_count": 0},
        )
    if omit != "timeout_review":
        write_artifact(
            dirs["timeout_review"],
            spec=packet.SPECS["timeout_review"],
            rows=[
                {
                    "review_scope": "exact_vs_single_filter_a_base_timeout_comparison",
                    "timeout_rate_delta": "0.025",
                    "timeout_mean_net_R_delta": "0.029",
                    "timeout_sum_net_R_delta": "24.8",
                }
            ],
            manifest={"review_row_count": 15, "warnings_count": 0, "blocking_warnings_count": 0},
        )
    if omit != "equity_review":
        write_artifact(
            dirs["equity_review"],
            spec=packet.SPECS["equity_review"],
            rows=[
                {
                    "review_scope": "exact_vs_single_filter_a_base_drawdown_sequence_comparison",
                    "drawdown_delta": "-12.4",
                    "drawdown_duration_delta": "-17.0",
                    "longest_negative_streak_delta": "-10.0",
                }
            ],
            manifest={"review_row_count": 8, "warnings_count": 0, "blocking_warnings_count": 0},
        )
    if include_optional and omit != "baseline_r_outputs":
        write_artifact(
            dirs["baseline_r_outputs"],
            spec=packet.SPECS["baseline_r_outputs"],
            rows=[{"baseline_type": "single_filter_a", "cost_profile": "p75"}],
            manifest={"consolidated_row_count": 6, "warnings_count": 0, "blocking_warnings_count": 0},
        )
    if include_optional and omit != "exact_stress":
        write_csv(
            dirs["exact_stress"] / "candidate_stress_summary.csv",
            ["symbol", "sequential_trades_count"],
            [{"symbol": "GBPUSD", "sequential_trades_count": "708"}],
        )
        (dirs["exact_stress"] / "candidate_stress_report.md").write_text("# Exact stress\n", encoding="utf-8")
    return dirs


def make_args(tmp_path: Path, *, omit: str | None = None, include_optional: bool = True) -> object:
    dirs = write_all_artifacts(tmp_path, omit=omit, include_optional=include_optional)
    return packet.build_parser().parse_args(
        [
            "--run-id",
            "unit_packet",
            "--comparison-table-dir",
            str(dirs["comparison"]),
            "--r-multiple-review-dir",
            str(dirs["r_review"]),
            "--walkforward-drawdown-readiness-dir",
            str(dirs["wf_readiness"]),
            "--walkforward-drawdown-review-dir",
            str(dirs["wf_review"]),
            "--timeout-readiness-dir",
            str(dirs["timeout_readiness"]),
            "--timeout-artifact-review-dir",
            str(dirs["timeout_review"]),
            "--equity-drawdown-sequence-review-dir",
            str(dirs["equity_review"]),
            "--exact-stress-dir",
            str(dirs["exact_stress"]),
            "--baseline-r-multiple-consolidated-dir",
            str(dirs["baseline_r_outputs"]),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        packet.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = packet.build_outputs(make_args(tmp_path))

    assert outputs["packet"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_all_expected_input_review_artifacts_are_read(tmp_path: Path) -> None:
    outputs = packet.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["packet"])
    blocks = {row["review_block"] for row in rows}

    assert "artifact_chain_integrity" in blocks
    assert "r_multiple_comparison_table_status" in blocks
    assert "exact_vs_single_filter_a_review" in blocks
    assert "walkforward_drawdown_artifact_review_status" in blocks
    assert "timeout_artifact_review_status" in blocks
    assert "equity_drawdown_sequence_review_status" in blocks
    assert "recommended_next_research_artifact" in blocks
    assert all(row["artifact_status"] != "missing" for row in rows)


def test_missing_optional_source_artifact_creates_available_with_caveat(tmp_path: Path) -> None:
    outputs = packet.build_outputs(make_args(tmp_path, include_optional=False))
    rows = read_csv(outputs["packet"])
    warnings = read_csv(outputs["warnings"])
    chain = next(row for row in rows if row["review_block"] == "artifact_chain_integrity")

    assert chain["artifact_status"] == "available_with_caveat"
    assert chain["evidence_status"] == "descriptive_evidence_available_with_caveat"
    assert chain["blocking_warning"] == "false"
    assert "artifact_chain_optional_source_missing" in {row["warning_code"] for row in warnings}


def test_missing_required_review_artifact_creates_missing_row_and_warning(tmp_path: Path) -> None:
    outputs = packet.build_outputs(make_args(tmp_path, omit="timeout_review"))
    rows = read_csv(outputs["packet"])
    warnings = read_csv(outputs["warnings"])
    timeout_row = next(row for row in rows if row["review_block"] == "timeout_artifact_review_status")

    assert timeout_row["artifact_status"] == "missing"
    assert timeout_row["evidence_status"] == "missing_required_artifact"
    assert timeout_row["blocking_warning"] == "true"
    assert "timeout_artifact_review_status_missing" in {row["warning_code"] for row in warnings}


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = packet.build_outputs(make_args(tmp_path, include_optional=False))
    rows = read_csv(outputs["packet"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["review_packet_row_count"] == len(rows)
    assert manifest["available_count"] == sum(row["artifact_status"] == "available" for row in rows)
    assert manifest["available_with_caveat_count"] == sum(
        row["artifact_status"] == "available_with_caveat" for row in rows
    )
    assert manifest["missing_count"] == sum(row["artifact_status"] == "missing" for row in rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_timeout_policy_review_executed"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_audit_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_artifact_only_no_decision_and_tradeoff_summary(tmp_path: Path) -> None:
    outputs = packet.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")
    lowered = report.lower()

    assert "Artifact-only review packet" in report
    assert "No candidate-quality conclusion" in report
    assert "trading decision" in report
    assert "appears to add selectivity, drawdown, and loss-cluster improvement" in report
    assert "does not clearly improve mean_R or profit_factor_R" in report
    assert "This packet does not replace true walk-forward validation" in report
    for forbidden in ("approved", "rejected", "profitable", "strategy_ready", "deploy", "buy", "sell"):
        assert forbidden not in lowered


def test_csv_preserves_source_paths(tmp_path: Path) -> None:
    outputs = packet.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["packet"])
    r_row = next(row for row in rows if row["review_block"] == "exact_vs_single_filter_a_review")

    assert r_row["source_dir"].endswith("r_review")
    assert r_row["source_manifest"].endswith(packet.SPECS["r_review"].manifest_name)
    assert r_row["source_report"].endswith(packet.SPECS["r_review"].report_name)
    assert r_row["source_csv"].endswith(packet.SPECS["r_review"].csv_name)


def test_no_child_or_heavy_commands_are_executed() -> None:
    source = Path(packet.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "validate_regime_candidate_stress.py --" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
    assert "run_tp_sl_path_backtests.py" not in source
