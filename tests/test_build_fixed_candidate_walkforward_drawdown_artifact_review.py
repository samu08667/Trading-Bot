from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_walkforward_drawdown_artifact_review as artifact_review


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


def write_stress_dir(
    path: Path,
    *,
    trades: str = "100",
    mean_r: str = "0.40",
    profit_factor: str = "2.0",
    cumulative: str = "40.0",
    drawdown: str = "3.0",
    yearly_ratio: str = "1.0",
    top_month: str = "8.0",
    top_5: str = "11.0",
    max_month_rows: str = "12",
    include_summary: bool = True,
    include_yearly: bool = True,
    include_walk_forward: bool = True,
) -> None:
    if include_summary:
        write_csv(
            path / artifact_review.SUMMARY_FILE,
            [
                "sequential_trades_count",
                "mean_R",
                "profit_factor_R",
                "cumulative_R",
                "max_drawdown_R",
                "yearly_positive_ratio",
                "top_month_contribution_pct",
                "top_5_percent_contribution_pct",
                "max_trades_in_one_month",
            ],
            [
                {
                    "sequential_trades_count": trades,
                    "mean_R": mean_r,
                    "profit_factor_R": profit_factor,
                    "cumulative_R": cumulative,
                    "max_drawdown_R": drawdown,
                    "yearly_positive_ratio": yearly_ratio,
                    "top_month_contribution_pct": top_month,
                    "top_5_percent_contribution_pct": top_5,
                    "max_trades_in_one_month": max_month_rows,
                }
            ],
        )
    if include_yearly:
        write_csv(path / "yearly_validation.csv", ["year", "mean_R"], [{"year": "2023", "mean_R": mean_r}])
    if include_walk_forward:
        write_csv(
            path / "walk_forward_validation.csv",
            ["split", "test_mean_R"],
            [{"split": "1", "test_mean_R": mean_r}, {"split": "2", "test_mean_R": mean_r}],
        )
    write_csv(path / artifact_review.EQUITY_BASE_FILE, ["cumulative_R"], [{"cumulative_R": "1"}])
    write_csv(path / artifact_review.EQUITY_STRESS_FILE, ["cumulative_R"], [{"cumulative_R": "1"}])
    write_csv(path / artifact_review.TRADE_BASE_FILE, ["R"], [{"R": "1"}])
    write_csv(path / artifact_review.TRADE_STRESS_FILE, ["R"], [{"R": "1"}])
    (path / artifact_review.REPORT_FILE).write_text("# Stress report\n", encoding="utf-8")


def write_readiness_dir(path: Path) -> None:
    write_csv(
        path / artifact_review.READINESS_FILE,
        ["review_scope", "readiness_status"],
        [{"review_scope": "exact_vs_single_filter_a_next_review_readiness", "readiness_status": "ready_with_caveat"}],
    )


def make_args(
    tmp_path: Path,
    *,
    exact_summary: bool = True,
    single_summary: bool = True,
    exact_yearly: bool = True,
    single_yearly: bool = True,
    exact_walk_forward: bool = True,
    single_walk_forward: bool = True,
) -> object:
    exact_dir = tmp_path / "exact"
    single_dir = tmp_path / "single_filter_a"
    readiness_dir = tmp_path / "readiness"
    write_stress_dir(
        exact_dir,
        trades="10",
        mean_r="0.50",
        profit_factor="2.0",
        cumulative="5.0",
        drawdown="1.0",
        top_month="7.5",
        top_5="9.5",
        max_month_rows="4",
        include_summary=exact_summary,
        include_yearly=exact_yearly,
        include_walk_forward=exact_walk_forward,
    )
    write_stress_dir(
        single_dir,
        trades="30",
        mean_r="0.55",
        profit_factor="2.2",
        cumulative="16.5",
        drawdown="2.5",
        top_month="9.5",
        top_5="13.0",
        max_month_rows="9",
        include_summary=single_summary,
        include_yearly=single_yearly,
        include_walk_forward=single_walk_forward,
    )
    write_readiness_dir(readiness_dir)
    return artifact_review.build_parser().parse_args(
        [
            "--run-id",
            "unit_artifact_review",
            "--exact-stress-dir",
            str(exact_dir),
            "--single-filter-a-stress-dir",
            str(single_dir),
            "--readiness-dir",
            str(readiness_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        artifact_review.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = artifact_review.build_outputs(make_args(tmp_path))

    assert outputs["review"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_exact_and_single_filter_summaries_are_read(tmp_path: Path) -> None:
    outputs = artifact_review.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["review"])
    drawdown = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_drawdown_review")

    assert drawdown["exact_trades"] == "10"
    assert drawdown["baseline_trades"] == "30"
    assert drawdown["exact_mean_R"] == "0.50"
    assert drawdown["baseline_mean_R"] == "0.55"
    assert drawdown["exact_cumulative_R"] == "5.0"
    assert drawdown["baseline_cumulative_R"] == "16.5"


def test_yearly_artifact_availability_is_detected(tmp_path: Path) -> None:
    outputs = artifact_review.build_outputs(make_args(tmp_path))
    row = next(row for row in read_csv(outputs["review"]) if row["review_scope"] == "exact_vs_single_filter_a_yearly_review")

    assert row["review_status"] == "descriptive_review_available"
    assert row["descriptive_observation"] == "yearly_coverage_artifacts_available"


def test_walk_forward_artifact_availability_is_detected(tmp_path: Path) -> None:
    outputs = artifact_review.build_outputs(make_args(tmp_path))
    row = next(
        row
        for row in read_csv(outputs["review"])
        if row["review_scope"] == "exact_vs_single_filter_a_walk_forward_review"
    )

    assert row["review_status"] == "descriptive_review_available"
    assert row["exact_walk_forward_splits"] == "2"
    assert row["baseline_walk_forward_splits"] == "2"
    assert row["descriptive_observation"] == "walk_forward_artifacts_available"


def test_clustering_fields_are_preserved(tmp_path: Path) -> None:
    outputs = artifact_review.build_outputs(make_args(tmp_path))
    row = next(row for row in read_csv(outputs["review"]) if row["review_scope"] == "exact_vs_single_filter_a_clustering_review")

    assert row["exact_top_month_contribution_pct"] == "7.5"
    assert row["baseline_top_month_contribution_pct"] == "9.5"
    assert row["exact_top_5_percent_contribution_pct"] == "9.5"
    assert row["baseline_top_5_percent_contribution_pct"] == "13.0"
    assert row["exact_max_rows_in_one_month"] == "4"
    assert row["baseline_max_rows_in_one_month"] == "9"
    assert "clustering_review_needed" in row["caveat"]


def test_missing_optional_yearly_and_walk_forward_create_non_blocking_warnings(tmp_path: Path) -> None:
    outputs = artifact_review.build_outputs(
        make_args(tmp_path, single_yearly=False, single_walk_forward=False)
    )
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    yearly = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_yearly_review")
    walk = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_walk_forward_review")

    assert yearly["review_status"] == "descriptive_review_available_with_caveat"
    assert walk["review_status"] == "descriptive_review_available_with_caveat"
    assert {row["blocking_warning"] for row in warnings} == {"false"}
    assert {"yearly_artifact_missing", "walk_forward_artifact_missing"}.issubset(
        {row["warning_code"] for row in warnings}
    )


def test_missing_required_summary_creates_unavailable_row_and_warning(tmp_path: Path) -> None:
    outputs = artifact_review.build_outputs(make_args(tmp_path, exact_summary=False))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    exact = next(row for row in rows if row["review_scope"] == "exact_rule_summary_artifact_review")

    assert exact["review_status"] == "unavailable_missing_artifact"
    assert exact["artifact_status"] == "missing"
    assert "exact_summary_missing" in {row["warning_code"] for row in warnings}


def test_review_rows_use_neutral_descriptive_labels(tmp_path: Path) -> None:
    outputs = artifact_review.build_outputs(make_args(tmp_path))
    text = outputs["review"].read_text(encoding="utf-8").lower()
    forbidden = ("b" + "est", "profit" + "able", "de" + "ploy", "b" + "uy", "s" + "ell", "strategy" + "_ready")

    for word in forbidden:
        assert word not in text
    assert "exact_more_selective_observed" in text
    assert "exact_lower_drawdown_observed" in text
    assert "descriptive_only_no_decision" in text


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = artifact_review.build_outputs(make_args(tmp_path, single_walk_forward=False))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["review_row_count"] == len(rows)
    assert manifest["descriptive_review_available_count"] == sum(
        row["review_status"] == "descriptive_review_available" for row in rows
    )
    assert manifest["descriptive_review_available_with_caveat_count"] == sum(
        row["review_status"] == "descriptive_review_available_with_caveat" for row in rows
    )
    assert manifest["unavailable_missing_artifact_count"] == sum(
        row["review_status"] == "unavailable_missing_artifact" for row in rows
    )
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_audit_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_artifact_only_and_no_decision_caveats(tmp_path: Path) -> None:
    outputs = artifact_review.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-only descriptive review" in report
    assert "No candidate-quality conclusion" in report
    assert "trading decision" in report
    assert "walk-forward" in report
    assert "timeout policy review" in report
    assert "drawdown/clustering review" in report


def test_no_child_or_heavy_commands_are_executed() -> None:
    source = Path(artifact_review.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "validate_regime_candidate_stress.py --" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
