from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import consolidate_fixed_candidate_deeper_walkforward_outputs as consolidator


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


def write_run_dir(
    path: Path,
    *,
    review_target: str,
    include_summary: bool = True,
    include_optional: bool = True,
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    condition = (
        "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
        "numeric_tercile:tick_volume_percentile_100:mid_tercile"
        if review_target == "exact_rule"
        else "numeric_tercile:close_to_ma_fast_atr_20:high_tercile"
    )
    trades = "708" if review_target == "exact_rule" else "2595"
    if include_summary:
        write_csv(
            path / consolidator.SUMMARY_FILE,
            [
                "symbol",
                "direction",
                "timeframe",
                "horizon",
                "target_family",
                "regime_column",
                "regime_value",
                "feature_condition",
                "sequential_trades_count",
                "mean_R",
                "profit_factor_R",
                "cumulative_R",
                "max_drawdown_R",
                "stress_sequential_trades_count",
                "stress_mean_R",
                "stress_profit_factor_R",
                "stress_cumulative_R",
                "stress_max_drawdown_R",
                "yearly_positive_ratio",
                "max_trades_in_one_month",
                "top_month_contribution_pct",
                "top_5_percent_contribution_pct",
                "final_research_label",
            ],
            [
                {
                    "symbol": "GBPUSD",
                    "direction": "short",
                    "timeframe": "M15",
                    "horizon": "10",
                    "target_family": "preferred_1_5atr_1atr_hit_first",
                    "regime_column": "hour_session",
                    "regime_value": "Off_hours",
                    "feature_condition": condition,
                    "sequential_trades_count": trades,
                    "mean_R": "0.49",
                    "profit_factor_R": "2.9",
                    "cumulative_R": "348.7",
                    "max_drawdown_R": "8.2",
                    "stress_sequential_trades_count": trades,
                    "stress_mean_R": "0.46",
                    "stress_profit_factor_R": "2.7",
                    "stress_cumulative_R": "327.0",
                    "stress_max_drawdown_R": "8.4",
                    "yearly_positive_ratio": "1.0",
                    "max_trades_in_one_month": "33",
                    "top_month_contribution_pct": "7.9",
                    "top_5_percent_contribution_pct": "9.6",
                    "final_research_label": "NEEDS_WALK_FORWARD_REVIEW",
                }
            ],
        )
    if include_optional:
        (path / consolidator.REPORT_FILE).write_text("# Stress report\n", encoding="utf-8")
        write_csv(
            path / consolidator.WALK_FORWARD_FILE,
            [
                "split_id",
                "train_trades",
                "train_mean_R",
                "test_trades",
                "test_mean_R",
                "test_profit_factor_R",
                "test_max_drawdown_R",
            ],
            [
                {
                    "split_id": "1",
                    "train_trades": "10",
                    "train_mean_R": "0.1",
                    "test_trades": "5",
                    "test_mean_R": "0.2",
                    "test_profit_factor_R": "1.5",
                    "test_max_drawdown_R": "2.0",
                },
                {
                    "split_id": "2",
                    "train_trades": "15",
                    "train_mean_R": "0.2",
                    "test_trades": "6",
                    "test_mean_R": "0.3",
                    "test_profit_factor_R": "1.6",
                    "test_max_drawdown_R": "2.5",
                },
            ],
        )
        write_csv(
            path / consolidator.YEARLY_FILE,
            ["year", "trades_count", "mean_R", "profit_factor_R", "cumulative_R", "max_drawdown_R"],
            [
                {
                    "year": "2023",
                    "trades_count": "11",
                    "mean_R": "0.2",
                    "profit_factor_R": "1.7",
                    "cumulative_R": "2.2",
                    "max_drawdown_R": "1.1",
                }
            ],
        )
        for name in (
            consolidator.EQUITY_BASE_FILE,
            consolidator.EQUITY_STRESS_FILE,
            consolidator.TRADE_BASE_FILE,
            consolidator.TRADE_STRESS_FILE,
            consolidator.RANDOM_BASELINE_FILE,
        ):
            write_csv(path / name, ["value"], [{"value": "1"}])


def make_args(
    tmp_path: Path,
    *,
    exact_summary: bool = True,
    single_summary: bool = True,
    include_optional: bool = True,
) -> object:
    root = tmp_path / "manual_outputs"
    exact_dir = root / "exact_rule"
    single_dir = root / "single_filter_a"
    write_run_dir(exact_dir, review_target="exact_rule", include_summary=exact_summary, include_optional=include_optional)
    write_run_dir(single_dir, review_target="single_filter_a", include_summary=single_summary, include_optional=include_optional)
    run_specs_dir = tmp_path / "run_specs"
    review_packet_dir = tmp_path / "research_packet"
    run_specs_dir.mkdir(parents=True, exist_ok=True)
    review_packet_dir.mkdir(parents=True, exist_ok=True)
    return consolidator.build_parser().parse_args(
        [
            "--run-id",
            "unit_deeper_wf_outputs",
            "--deeper-walkforward-output-root",
            str(root),
            "--run-specs-dir",
            str(run_specs_dir),
            "--research-review-packet-dir",
            str(review_packet_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        consolidator.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path))

    assert outputs["consolidated"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_exact_rule_and_single_filter_summaries_are_consolidated(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["consolidated"])
    exact = next(row for row in rows if row["review_target"] == "exact_rule" and row["row_type"] == "summary_base")
    single = next(row for row in rows if row["review_target"] == "single_filter_a" and row["row_type"] == "summary_base")
    stress = next(row for row in rows if row["review_target"] == "exact_rule" and row["row_type"] == "summary_stress")

    assert exact["trades"] == "708"
    assert exact["mean_R"] == "0.49"
    assert exact["profit_factor_R"] == "2.9"
    assert exact["walk_forward_splits"] == "2"
    assert single["trades"] == "2595"
    assert stress["cost_profile"] == "p90"
    assert stress["mean_R"] == "0.46"
    assert stress["profit_factor_R"] == "2.7"


def test_walk_forward_validation_rows_are_preserved(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path))
    rows = [
        row
        for row in read_csv(outputs["consolidated"])
        if row["review_target"] == "exact_rule" and row["row_type"] == "walk_forward_split"
    ]

    assert len(rows) == 2
    assert rows[0]["split_id"] == "1"
    assert rows[0]["trades"] == "5"
    assert rows[0]["mean_R"] == "0.2"
    assert rows[0]["profit_factor_R"] == "1.5"
    assert rows[1]["split_id"] == "2"


def test_yearly_validation_rows_are_preserved(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path))
    row = next(
        row
        for row in read_csv(outputs["consolidated"])
        if row["review_target"] == "single_filter_a" and row["row_type"] == "yearly_validation"
    )

    assert row["year"] == "2023"
    assert row["trades"] == "11"
    assert row["cumulative_R"] == "2.2"
    assert row["max_drawdown_R"] == "1.1"


def test_artifact_availability_rows_are_written(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path))
    rows = [row for row in read_csv(outputs["consolidated"]) if row["row_type"] == "artifact_availability"]

    assert len(rows) == 2
    assert {row["review_target"] for row in rows} == {"exact_rule", "single_filter_a"}
    assert {row["artifact_status"] for row in rows} == {"available"}


def test_missing_optional_artifacts_create_non_blocking_warnings(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path, include_optional=False))
    rows = read_csv(outputs["consolidated"])
    warnings = read_csv(outputs["warnings"])
    availability = [
        row
        for row in rows
        if row["row_type"] == "artifact_availability"
    ]

    assert {row["artifact_status"] for row in availability} == {"available_with_caveat"}
    assert {row["blocking_warning"] for row in warnings} == {"false"}
    assert {row["warning_code"] for row in warnings} == {"optional_artifacts_missing"}


def test_missing_required_summary_creates_missing_row_and_warning(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path, exact_summary=False))
    rows = read_csv(outputs["consolidated"])
    warnings = read_csv(outputs["warnings"])
    exact_rows = [row for row in rows if row["review_target"] == "exact_rule"]

    assert any(row["row_type"] == "summary_base" and row["artifact_status"] == "missing" for row in exact_rows)
    assert any(row["row_type"] == "summary_stress" and row["artifact_status"] == "missing" for row in exact_rows)
    assert "required_summary_missing" in {row["warning_code"] for row in warnings}
    assert "true" in {row["blocking_warning"] for row in warnings}


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path, include_optional=False))
    rows = read_csv(outputs["consolidated"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["consolidated_row_count"] == len(rows)
    assert manifest["exact_rule_row_count"] == sum(row["review_target"] == "exact_rule" for row in rows)
    assert manifest["single_filter_a_row_count"] == sum(row["review_target"] == "single_filter_a" for row in rows)
    assert manifest["summary_row_count"] == sum(row["row_type"] in {"summary_base", "summary_stress"} for row in rows)
    assert manifest["walk_forward_row_count"] == sum(row["row_type"] == "walk_forward_split" for row in rows)
    assert manifest["yearly_row_count"] == sum(row["row_type"] == "yearly_validation" for row in rows)
    assert manifest["artifact_availability_row_count"] == sum(row["row_type"] == "artifact_availability" for row in rows)
    assert manifest["available_count"] == sum(row["artifact_status"] == "available" for row in rows)
    assert manifest["available_with_caveat_count"] == sum(row["artifact_status"] == "available_with_caveat" for row in rows)
    assert manifest["missing_count"] == sum(row["artifact_status"] == "missing" for row in rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_walk_forward_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_timeout_policy_review_executed"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_audit_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_artifact_only_and_no_decision_caveats(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-only consolidation" in report
    assert "No candidate-quality conclusion" in report
    assert "trading decision" in report
    assert "does not replace deeper walk-forward review" in report
    assert "split-by-split exact vs single_filter_a review" in report


def test_no_child_or_heavy_commands_are_executed() -> None:
    source = Path(consolidator.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "validate_regime_candidate_stress.py --" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
    assert "run_tp_sl_path_backtests.py" not in source
