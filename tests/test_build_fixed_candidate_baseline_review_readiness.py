from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_baseline_review_readiness as readiness


COMPARISON_FIELDS = [
    "row_type",
    "baseline_type",
    "cost_profile",
    "artifact_status",
    "metric_namespace",
    "metric_unit",
    "source_csv",
    "trades",
    "mean_return",
    "profit_factor",
    "cumulative_return",
    "max_drawdown",
    "exact_mean_R",
    "exact_profit_factor_R",
    "exact_cumulative_R",
    "exact_max_drawdown_R",
    "baseline_mean_return",
    "baseline_profit_factor",
    "baseline_cumulative_return",
    "baseline_max_drawdown",
]


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


def exact_row(cost_profile: str) -> dict[str, str]:
    return {
        "row_type": "exact_rule",
        "baseline_type": "exact_rule",
        "cost_profile": cost_profile,
        "artifact_status": "available",
        "metric_namespace": "R_multiple",
        "metric_unit": "R",
        "source_csv": "candidate_stress_summary.csv",
        "trades": "708",
        "mean_return": "",
        "profit_factor": "",
        "cumulative_return": "",
        "max_drawdown": "",
        "exact_mean_R": "0.49" if cost_profile == "p75" else "0.46",
        "exact_profit_factor_R": "2.9",
        "exact_cumulative_R": "348",
        "exact_max_drawdown_R": "8.2",
        "baseline_mean_return": "",
        "baseline_profit_factor": "",
        "baseline_cumulative_return": "",
        "baseline_max_drawdown": "",
    }


def baseline_row(baseline_type: str, cost_profile: str) -> dict[str, str]:
    return {
        "row_type": "baseline",
        "baseline_type": baseline_type,
        "cost_profile": cost_profile,
        "artifact_status": "available",
        "metric_namespace": "net_return",
        "metric_unit": "return_fraction",
        "source_csv": "baseline_diagnostics_detail.csv",
        "trades": "100",
        "mean_return": "0.01",
        "profit_factor": "1.1",
        "cumulative_return": "1.2",
        "max_drawdown": "0.3",
        "exact_mean_R": "",
        "exact_profit_factor_R": "",
        "exact_cumulative_R": "",
        "exact_max_drawdown_R": "",
        "baseline_mean_return": "0.01",
        "baseline_profit_factor": "1.1",
        "baseline_cumulative_return": "1.2",
        "baseline_max_drawdown": "0.3",
    }


def write_comparison_table(path: Path) -> None:
    rows = [exact_row("p75"), exact_row("p90")]
    for baseline_type in ["broad_regime_baseline", "single_filter_a", "single_filter_b"]:
        rows.append(baseline_row(baseline_type, "p75"))
        rows.append(baseline_row(baseline_type, "p90"))
    write_csv(path, COMPARISON_FIELDS, rows)


def make_args(tmp_path: Path, *, write_table: bool = True) -> object:
    comparison_csv = tmp_path / "comparison.csv"
    manifest_json = tmp_path / "comparison_manifest.json"
    if write_table:
        write_comparison_table(comparison_csv)
    manifest_json.write_text(
        json.dumps(
            {
                "comparison_row_count": 8,
                "metric_namespaces": ["R_multiple", "net_return"],
                "warnings_count": 1,
                "blocking_warnings_count": 0,
            }
        ),
        encoding="utf-8",
    )
    return readiness.build_parser().parse_args(
        [
            "--run-id",
            "unit",
            "--comparison-table-csv",
            str(comparison_csv),
            "--comparison-manifest-json",
            str(manifest_json),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )


def row_by_scope(rows: list[dict[str, str]], scope: str) -> dict[str, str]:
    return next(row for row in rows if row["review_scope"] == scope)


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


def test_mixed_metric_namespaces_are_detected(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert "R_multiple" in manifest["metric_namespaces"]
    assert "net_return" in manifest["metric_namespaces"]
    assert any(row["warning_code"] == "mixed_metric_namespace_caveat" for row in warnings)


def test_exact_vs_baseline_is_blocked_requires_normalization(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])

    for scope in ["exact_vs_broad_review", "exact_vs_single_filter_a_review", "exact_vs_single_filter_b_review"]:
        row = row_by_scope(rows, scope)
        assert row["readiness_status"] == "blocked_requires_normalization"
        assert row["allowed_without_normalization"] == "false"
        assert row["required_next_artifact"] == "normalized_exact_vs_baseline_metric_table"
        assert "blocked until normalization" in row["caveat"]


def test_exact_p75_p90_is_ready_same_metric_namespace(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    row = row_by_scope(read_csv(outputs["readiness"]), "exact_rule_cost_sensitivity_review")

    assert row["readiness_status"] == "ready_same_metric_namespace"
    assert row["allowed_without_normalization"] == "true"
    assert row["metric_namespaces_involved"] == "R_multiple"


def test_baseline_reviews_are_ready_with_or_without_caveat(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    cost_row = row_by_scope(rows, "baseline_cost_sensitivity_review")
    context_row = row_by_scope(rows, "baseline_context_review")

    assert cost_row["readiness_status"] == "ready_with_caveat"
    assert cost_row["allowed_without_normalization"] == "true"
    assert "row-level spread" in cost_row["caveat"]
    assert context_row["readiness_status"] == "ready_same_metric_namespace"
    assert context_row["metric_namespaces_involved"] == "net_return"


def test_manifest_counts_match_readiness_and_warnings(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["readiness_row_count"] == len(rows)
    assert manifest["ready_same_metric_namespace_count"] == sum(
        row["readiness_status"] == "ready_same_metric_namespace" for row in rows
    )
    assert manifest["ready_with_caveat_count"] == sum(row["readiness_status"] == "ready_with_caveat" for row in rows)
    assert manifest["blocked_requires_normalization_count"] == sum(
        row["readiness_status"] == "blocked_requires_normalization" for row in rows
    )
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_audit_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_missing_comparison_table_marks_rows_unavailable(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, write_table=False))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])

    assert {row["readiness_status"] for row in rows} == {"unavailable_missing_artifacts"}
    assert any(row["warning_code"] == "comparison_table_missing" for row in warnings)


def test_report_includes_no_decision_caveats(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-only review-readiness report" in report
    assert "No candidate-quality evaluation" in report
    assert "No trading decision was made" in report
    assert "blocked until a normalization artifact exists" in report
    assert "Baseline-vs-baseline review is possible" in report
    assert "Exact p75/p90 review is possible" in report


def test_no_child_scripts_are_executed() -> None:
    source = Path(readiness.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
    assert "validate_regime_candidate_stress.py --" not in source
