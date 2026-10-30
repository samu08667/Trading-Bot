from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_deeper_walkforward_split_review as split_review


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


INPUT_FIELDS = [
    "review_target",
    "row_type",
    "cost_profile",
    "split_id",
    "year",
    "artifact_status",
    "source_output_dir",
    "source_walk_forward_csv",
    "source_yearly_csv",
    "trades",
    "mean_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
]


def split_row(
    *,
    review_target: str,
    split_id: str,
    trades: object,
    mean_R: object,
    profit_factor_R: object,
    max_drawdown_R: object,
) -> dict[str, object]:
    return {
        "review_target": review_target,
        "row_type": "walk_forward_split",
        "cost_profile": "p75",
        "split_id": split_id,
        "year": "",
        "artifact_status": "available",
        "source_output_dir": f"manual_outputs/{review_target}",
        "source_walk_forward_csv": f"manual_outputs/{review_target}/walk_forward_validation.csv",
        "source_yearly_csv": f"manual_outputs/{review_target}/yearly_validation.csv",
        "trades": trades,
        "mean_R": mean_R,
        "profit_factor_R": profit_factor_R,
        "cumulative_R": "",
        "max_drawdown_R": max_drawdown_R,
    }


def yearly_row(
    *,
    review_target: str,
    year: str,
    trades: object,
    mean_R: object,
    profit_factor_R: object,
    cumulative_R: object,
    max_drawdown_R: object,
) -> dict[str, object]:
    return {
        "review_target": review_target,
        "row_type": "yearly_validation",
        "cost_profile": "p75",
        "split_id": "",
        "year": year,
        "artifact_status": "available",
        "source_output_dir": f"manual_outputs/{review_target}",
        "source_walk_forward_csv": f"manual_outputs/{review_target}/walk_forward_validation.csv",
        "source_yearly_csv": f"manual_outputs/{review_target}/yearly_validation.csv",
        "trades": trades,
        "mean_R": mean_R,
        "profit_factor_R": profit_factor_R,
        "cumulative_R": cumulative_R,
        "max_drawdown_R": max_drawdown_R,
    }


def write_consolidated_input(tmp_path: Path, *, omit_single_split_2: bool = False) -> Path:
    consolidated_dir = tmp_path / "consolidated"
    rows: list[dict[str, object]] = [
        split_row(
            review_target="exact_rule",
            split_id="1",
            trades=10,
            mean_R=0.5,
            profit_factor_R=2.0,
            max_drawdown_R=1.0,
        ),
        split_row(
            review_target="single_filter_a",
            split_id="1",
            trades=30,
            mean_R=0.6,
            profit_factor_R=2.5,
            max_drawdown_R=3.0,
        ),
        split_row(
            review_target="exact_rule",
            split_id="2",
            trades=8,
            mean_R=0.7,
            profit_factor_R=2.2,
            max_drawdown_R=2.0,
        ),
        yearly_row(
            review_target="exact_rule",
            year="2023",
            trades=50,
            mean_R=0.4,
            profit_factor_R=1.8,
            cumulative_R=20.0,
            max_drawdown_R=5.0,
        ),
        yearly_row(
            review_target="single_filter_a",
            year="2023",
            trades=100,
            mean_R=0.3,
            profit_factor_R=1.6,
            cumulative_R=30.0,
            max_drawdown_R=9.0,
        ),
    ]
    if not omit_single_split_2:
        rows.insert(
            3,
            split_row(
                review_target="single_filter_a",
                split_id="2",
                trades=25,
                mean_R=0.5,
                profit_factor_R=2.0,
                max_drawdown_R=4.0,
            ),
        )
    write_csv(consolidated_dir / split_review.INPUT_CSV, INPUT_FIELDS, rows)
    return consolidated_dir


def make_args(tmp_path: Path, *, omit_single_split_2: bool = False) -> object:
    consolidated_dir = write_consolidated_input(tmp_path, omit_single_split_2=omit_single_split_2)
    return split_review.build_parser().parse_args(
        [
            "--run-id",
            "unit_split_review",
            "--deeper-walkforward-consolidated-dir",
            str(consolidated_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        split_review.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = split_review.build_outputs(make_args(tmp_path))

    assert outputs["review"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_split_rows_are_matched_by_split_id(tmp_path: Path) -> None:
    outputs = split_review.build_outputs(make_args(tmp_path))
    split_rows = [
        row for row in read_csv(outputs["review"]) if row["review_scope"] == "walk_forward_split_comparison"
    ]

    assert [row["split_id"] for row in split_rows] == ["1", "2"]
    assert {row["review_status"] for row in split_rows} == {"descriptive_split_review_available"}
    assert split_rows[0]["exact_source_walk_forward_csv"].endswith("exact_rule/walk_forward_validation.csv")
    assert split_rows[0]["baseline_source_walk_forward_csv"].endswith("single_filter_a/walk_forward_validation.csv")


def test_yearly_rows_are_matched_by_year(tmp_path: Path) -> None:
    outputs = split_review.build_outputs(make_args(tmp_path))
    yearly = next(row for row in read_csv(outputs["review"]) if row["review_scope"] == "yearly_validation_comparison")

    assert yearly["year"] == "2023"
    assert yearly["exact_source_yearly_csv"].endswith("exact_rule/yearly_validation.csv")
    assert yearly["baseline_source_yearly_csv"].endswith("single_filter_a/yearly_validation.csv")


def test_deltas_are_computed_correctly(tmp_path: Path) -> None:
    outputs = split_review.build_outputs(make_args(tmp_path))
    split_1 = next(
        row
        for row in read_csv(outputs["review"])
        if row["review_scope"] == "walk_forward_split_comparison" and row["split_id"] == "1"
    )
    yearly = next(row for row in read_csv(outputs["review"]) if row["review_scope"] == "yearly_validation_comparison")

    assert split_1["delta_trades"] == "-20.0"
    assert split_1["trade_count_ratio_exact_to_baseline"] == str(10 / 30)
    assert split_1["delta_mean_R"] == str(0.5 - 0.6)
    assert split_1["delta_profit_factor_R"] == str(2.0 - 2.5)
    assert split_1["delta_max_drawdown_R"] == str(1.0 - 3.0)
    assert split_1["exact_lower_drawdown_flag"] == "true"
    assert split_1["exact_mean_R_higher_flag"] == "false"
    assert yearly["delta_cumulative_R"] == str(20.0 - 30.0)


def test_summary_counts_are_computed_correctly(tmp_path: Path) -> None:
    outputs = split_review.build_outputs(make_args(tmp_path))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    rows = read_csv(outputs["review"])
    split_summary = next(row for row in rows if row["review_scope"] == "walk_forward_split_summary")

    assert manifest["exact_lower_drawdown_split_count"] == 2
    assert manifest["exact_mean_R_higher_split_count"] == 1
    assert manifest["exact_profit_factor_higher_split_count"] == 1
    assert split_summary["exact_max_drawdown_R"] == "2"
    assert split_summary["baseline_max_drawdown_R"] == "2"
    assert "exact_lower_drawdown_all_splits_observed" in split_summary["descriptive_observation"]
    assert "exact_mean_R_not_consistently_higher" in split_summary["descriptive_observation"]


def test_missing_matching_split_row_creates_warning(tmp_path: Path) -> None:
    outputs = split_review.build_outputs(make_args(tmp_path, omit_single_split_2=True))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    missing = next(
        row
        for row in rows
        if row["review_scope"] == "walk_forward_split_comparison" and row["split_id"] == "2"
    )

    assert missing["review_status"] == "unavailable_missing_matching_row"
    assert missing["warning_code"] == "matching_row_missing"
    assert any(warning["warning_code"] == "matching_row_missing" for warning in warnings)
    assert all(warning["blocking_warning"] == "false" for warning in warnings)


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = split_review.build_outputs(make_args(tmp_path, omit_single_split_2=True))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["review_row_count"] == len(rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["walk_forward_split_comparison_count"] == 2
    assert manifest["yearly_validation_comparison_count"] == 1
    assert manifest["unavailable_missing_matching_row_count"] == 1
    assert manifest["blocking_warnings_count"] == 0


def test_report_includes_artifact_only_and_no_decision_caveats(tmp_path: Path) -> None:
    outputs = split_review.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-only descriptive review" in report
    assert "No candidate-quality conclusion, ranking, or trading decision was made." in report
    assert "does not replace final candidate audit" in report


def test_module_does_not_execute_child_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    split_review.build_outputs(make_args(tmp_path))
