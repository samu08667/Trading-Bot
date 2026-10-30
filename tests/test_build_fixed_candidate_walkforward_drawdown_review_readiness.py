from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_walkforward_drawdown_review_readiness as readiness


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
    mean_r: str = "0.4",
    profit_factor: str = "2.0",
    drawdown: str = "3.0",
    yearly_ratio: str = "1.0",
    top_month: str = "8.0",
    top_5: str = "11.0",
    include_yearly: bool = True,
    include_walk_forward: bool = True,
) -> None:
    write_csv(
        path / readiness.SUMMARY_FILE,
        [
            "sequential_trades_count",
            "mean_R",
            "profit_factor_R",
            "max_drawdown_R",
            "yearly_positive_ratio",
            "top_month_contribution_pct",
            "top_5_percent_contribution_pct",
        ],
        [
            {
                "sequential_trades_count": trades,
                "mean_R": mean_r,
                "profit_factor_R": profit_factor,
                "max_drawdown_R": drawdown,
                "yearly_positive_ratio": yearly_ratio,
                "top_month_contribution_pct": top_month,
                "top_5_percent_contribution_pct": top_5,
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
    write_csv(path / readiness.EQUITY_BASE_FILE, ["cumulative_R"], [{"cumulative_R": "1"}])
    write_csv(path / readiness.EQUITY_STRESS_FILE, ["cumulative_R"], [{"cumulative_R": "1"}])
    write_csv(path / readiness.TRADE_BASE_FILE, ["R"], [{"R": "1"}])
    write_csv(path / readiness.TRADE_STRESS_FILE, ["R"], [{"R": "1"}])
    (path / readiness.REPORT_FILE).write_text("# Stress report\n", encoding="utf-8")


def write_r_review_dir(path: Path) -> None:
    write_csv(
        path / readiness.R_MULTIPLE_REVIEW_FILE,
        ["review_scope", "review_status"],
        [{"review_scope": "exact_vs_single_filter_a", "review_status": "descriptive_review_available"}],
    )


def make_args(
    tmp_path: Path,
    *,
    exact: bool = True,
    single: bool = True,
    exact_yearly: bool = True,
    single_yearly: bool = True,
    exact_walk_forward: bool = True,
    single_walk_forward: bool = True,
) -> object:
    exact_dir = tmp_path / "exact"
    single_dir = tmp_path / "single_filter_a"
    review_dir = tmp_path / "r_review"
    if exact:
        write_stress_dir(
            exact_dir,
            trades="10",
            mean_r="0.50",
            profit_factor="2.0",
            drawdown="1.0",
            include_yearly=exact_yearly,
            include_walk_forward=exact_walk_forward,
        )
    if single:
        write_stress_dir(
            single_dir,
            trades="30",
            mean_r="0.55",
            profit_factor="2.2",
            drawdown="2.5",
            top_month="9.5",
            top_5="13.0",
            include_yearly=single_yearly,
            include_walk_forward=single_walk_forward,
        )
    write_r_review_dir(review_dir)
    return readiness.build_parser().parse_args(
        [
            "--run-id",
            "unit_readiness",
            "--exact-stress-dir",
            str(exact_dir),
            "--single-filter-a-stress-dir",
            str(single_dir),
            "--r-multiple-review-dir",
            str(review_dir),
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


def test_exact_and_single_filter_summaries_are_read(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    drawdown = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_drawdown_artifact_review")

    assert drawdown["exact_trades"] == "10"
    assert drawdown["baseline_trades"] == "30"
    assert drawdown["exact_mean_R"] == "0.50"
    assert drawdown["baseline_mean_R"] == "0.55"
    assert drawdown["exact_max_drawdown_R"] == "1.0"
    assert drawdown["baseline_max_drawdown_R"] == "2.5"


def test_yearly_summary_availability_is_detected(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    row = next(
        row
        for row in read_csv(outputs["readiness"])
        if row["review_scope"] == "exact_vs_single_filter_a_yearly_coverage"
    )

    assert row["readiness_status"] == "ready_for_artifact_review"
    assert "yearly_artifacts_present" in row["caveat"]


def test_walk_forward_summary_availability_is_detected(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    row = next(
        row
        for row in read_csv(outputs["readiness"])
        if row["review_scope"] == "exact_vs_single_filter_a_walk_forward_coverage"
    )

    assert row["readiness_status"] == "ready_for_artifact_review"
    assert row["exact_walk_forward_splits"] == "2"
    assert row["baseline_walk_forward_splits"] == "2"
    assert "walk_forward_artifacts_present" in row["caveat"]


def test_missing_exact_dir_creates_unavailable_row_and_warning(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, exact=False))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    row = next(row for row in rows if row["review_scope"] == "exact_rule_artifact_availability")

    assert row["readiness_status"] == "unavailable_missing_artifact"
    assert row["artifact_status"] == "missing"
    assert "exact_rule_artifact_missing" in {warning["warning_code"] for warning in warnings}


def test_missing_single_filter_a_dir_creates_unavailable_row_and_warning(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, single=False))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    row = next(row for row in rows if row["review_scope"] == "single_filter_a_artifact_availability")

    assert row["readiness_status"] == "unavailable_missing_artifact"
    assert row["artifact_status"] == "missing"
    assert "single_filter_a_artifact_missing" in {warning["warning_code"] for warning in warnings}


def test_readiness_rows_are_neutral(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    text = outputs["readiness"].read_text(encoding="utf-8").lower()

    forbidden_labels = ("approv" + "ed", "reject" + "ed", "profit" + "able", "strategy" + "_ready")
    for forbidden in forbidden_labels:
        assert forbidden not in text
    assert "exact_more_selective" in text
    assert "exact_lower_drawdown_observed" in text
    assert "descriptive_only_no_decision" in text


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, single_walk_forward=False))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["review_row_count"] == len(rows)
    assert manifest["ready_for_artifact_review_count"] == sum(
        row["readiness_status"] == "ready_for_artifact_review" for row in rows
    )
    assert manifest["ready_with_caveat_count"] == sum(row["readiness_status"] == "ready_with_caveat" for row in rows)
    assert manifest["unavailable_missing_artifact_count"] == sum(
        row["readiness_status"] == "unavailable_missing_artifact" for row in rows
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
    outputs = readiness.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-only review-readiness report" in report
    assert "No candidate-quality conclusion" in report
    assert "trading decision" in report
    assert "walk-forward review" in report
    assert "timeout policy review" in report
    assert "drawdown/clustering review" in report


def test_no_child_or_heavy_commands_are_executed() -> None:
    source = Path(readiness.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "validate_regime_candidate_stress.py --" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
