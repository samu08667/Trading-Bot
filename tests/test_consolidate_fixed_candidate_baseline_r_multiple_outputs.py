from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import consolidate_fixed_candidate_baseline_r_multiple_outputs as consolidator


ROW_SPEC_FIELDS = [
    "run_id",
    "baseline_type",
    "expected_cost_profiles",
    "symbol",
    "direction",
    "timeframe",
    "target_horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "tp_atr",
    "sl_atr",
    "atr_column",
    "condition_to_apply",
    "exact_feature_condition_metadata",
    "db_path",
    "p75_cost_config",
    "p90_cost_config",
    "stress_spread_policy",
    "expected_output_dir",
    "spec_status",
    "warning_code",
    "blocking_warning",
]

SUMMARY_FIELDS = [
    "symbol",
    "direction",
    "timeframe",
    "target_family",
    "horizon",
    "regime_column",
    "regime_value",
    "tp_atr",
    "sl_atr",
    "atr_column",
    "same_bar_policy",
    "feature_condition",
    "sequential_trades_count",
    "mean_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
    "yearly_positive_ratio",
    "base_cost_config_path",
    "stress_cost_config_path",
    "stress_spread_policy",
    "mean_cost_R_base",
    "mean_cost_R_stress",
    "net_R_delta_mean",
    "stress_changed_cost_R",
    "stress_sequential_trades_count",
    "stress_mean_R",
    "stress_profit_factor_R",
    "stress_cumulative_R",
    "stress_max_drawdown_R",
    "final_research_label",
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


def condition_for(baseline_type: str) -> str:
    if baseline_type == "single_filter_a":
        return "numeric_tercile:close_to_ma_fast_atr_20:high_tercile"
    if baseline_type == "single_filter_b":
        return "numeric_tercile:tick_volume_percentile_100:mid_tercile"
    return ""


def write_row_specs(row_specs_dir: Path, output_root: Path) -> None:
    rows = []
    for baseline_type in consolidator.BASELINE_TYPES:
        rows.append(
            {
                "run_id": "specs_v1",
                "baseline_type": baseline_type,
                "expected_cost_profiles": "p75;p90",
                "symbol": "GBPUSD",
                "direction": "short",
                "timeframe": "M15",
                "target_horizon": "10",
                "target_family": "preferred_1_5atr_1atr_hit_first",
                "regime_column": "hour_session",
                "regime_value": "Off_hours",
                "tp_atr": "1.5",
                "sl_atr": "1.0",
                "atr_column": "atr_20",
                "condition_to_apply": condition_for(baseline_type),
                "exact_feature_condition_metadata": "filter_a AND filter_b",
                "db_path": "data/unit.db",
                "p75_cost_config": "config/p75.json",
                "p90_cost_config": "config/p90.json",
                "stress_spread_policy": "max_row_or_fallback",
                "expected_output_dir": str(output_root / f"specs_v1_{baseline_type}"),
                "spec_status": "spec_ready",
                "warning_code": "",
                "blocking_warning": "false",
            }
        )
    write_csv(row_specs_dir / consolidator.ROW_SPECS_FILE, ROW_SPEC_FIELDS, rows)


def write_stress_output(output_root: Path, baseline_type: str, *, base_mean: str = "0.10", stress_mean: str = "0.07") -> Path:
    output_dir = output_root / f"specs_v1_{baseline_type}"
    write_csv(
        output_dir / consolidator.SUMMARY_FILE,
        SUMMARY_FIELDS,
        [
            {
                "symbol": "GBPUSD",
                "direction": "short",
                "timeframe": "M15",
                "target_family": "preferred_1_5atr_1atr_hit_first",
                "horizon": "10",
                "regime_column": "hour_session",
                "regime_value": "Off_hours",
                "tp_atr": "1.5",
                "sl_atr": "1.0",
                "atr_column": "atr_20",
                "same_bar_policy": "stop_first",
                "feature_condition": condition_for(baseline_type),
                "sequential_trades_count": "100",
                "mean_R": base_mean,
                "profit_factor_R": "1.50",
                "cumulative_R": "10.0",
                "max_drawdown_R": "2.0",
                "yearly_positive_ratio": "1.0",
                "base_cost_config_path": "config/p75.json",
                "stress_cost_config_path": "config/p90.json",
                "stress_spread_policy": "max_row_or_fallback",
                "mean_cost_R_base": "0.11",
                "mean_cost_R_stress": "0.22",
                "net_R_delta_mean": "-0.03",
                "stress_changed_cost_R": "True",
                "stress_sequential_trades_count": "100",
                "stress_mean_R": stress_mean,
                "stress_profit_factor_R": "1.30",
                "stress_cumulative_R": "7.0",
                "stress_max_drawdown_R": "3.0",
                "final_research_label": "STRESS_REVIEW_RETAINED",
            }
        ],
    )
    write_csv(output_dir / consolidator.BASE_TRADE_LOG_FILE, ["R"], [{"R": "0.1"}])
    write_csv(output_dir / consolidator.STRESS_TRADE_LOG_FILE, ["R"], [{"R": "0.07"}])
    write_csv(output_dir / consolidator.WALK_FORWARD_FILE, ["split"], [{"split": "1"}, {"split": "2"}])
    (output_dir / consolidator.REPORT_FILE).write_text("# Stress Report\n", encoding="utf-8")
    return output_dir


def make_args(tmp_path: Path, *, write_specs: bool = True) -> object:
    row_specs_dir = tmp_path / "row_specs"
    output_root = row_specs_dir / "manual_r_multiple_outputs"
    if write_specs:
        write_row_specs(row_specs_dir, output_root)
    return consolidator.build_parser().parse_args(
        [
            "--run-id",
            "unit_consolidated",
            "--r-multiple-output-root",
            str(output_root),
            "--row-specs-dir",
            str(row_specs_dir),
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
    args = make_args(tmp_path)
    output_root = Path(args.r_multiple_output_root)
    write_stress_output(output_root, "broad_regime_baseline")

    outputs = consolidator.build_outputs(args)

    assert outputs["consolidated"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_three_baseline_folders_produce_six_rows(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    output_root = Path(args.r_multiple_output_root)
    for baseline_type in consolidator.BASELINE_TYPES:
        write_stress_output(output_root, baseline_type)

    outputs = consolidator.build_outputs(args)
    rows = read_csv(outputs["consolidated"])

    assert len(rows) == 6
    assert {row["baseline_type"] for row in rows} == set(consolidator.BASELINE_TYPES)
    assert {row["cost_profile"] for row in rows} == {"p75", "p90"}
    assert {row["artifact_status"] for row in rows} == {"available"}


def test_p75_rows_use_base_fields(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    output_root = Path(args.r_multiple_output_root)
    write_stress_output(output_root, "broad_regime_baseline", base_mean="0.26", stress_mean="0.23")

    outputs = consolidator.build_outputs(args)
    row = next(
        row
        for row in read_csv(outputs["consolidated"])
        if row["baseline_type"] == "broad_regime_baseline" and row["cost_profile"] == "p75"
    )

    assert row["trades"] == "100"
    assert row["mean_R"] == "0.26"
    assert row["profit_factor_R"] == "1.50"
    assert row["cumulative_R"] == "10.0"
    assert row["max_drawdown_R"] == "2.0"
    assert row["mean_cost_R"] == "0.11"
    assert row["cost_config_path"] == "config/p75.json"
    assert row["source_trade_csv"].endswith("trade_log_base.csv")


def test_p90_rows_use_stress_fields(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    output_root = Path(args.r_multiple_output_root)
    write_stress_output(output_root, "single_filter_a", base_mean="0.50", stress_mean="0.47")

    outputs = consolidator.build_outputs(args)
    row = next(
        row
        for row in read_csv(outputs["consolidated"])
        if row["baseline_type"] == "single_filter_a" and row["cost_profile"] == "p90"
    )

    assert row["trades"] == "100"
    assert row["mean_R"] == "0.47"
    assert row["profit_factor_R"] == "1.30"
    assert row["cumulative_R"] == "7.0"
    assert row["max_drawdown_R"] == "3.0"
    assert row["mean_cost_R"] == "0.22"
    assert row["cost_config_path"] == "config/p90.json"
    assert row["source_trade_csv"].endswith("trade_log_stress.csv")


def test_source_paths_are_preserved(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    output_root = Path(args.r_multiple_output_root)
    source_dir = write_stress_output(output_root, "single_filter_b")

    outputs = consolidator.build_outputs(args)
    row = next(
        row
        for row in read_csv(outputs["consolidated"])
        if row["baseline_type"] == "single_filter_b" and row["cost_profile"] == "p75"
    )

    assert row["source_output_dir"] == str(source_dir)
    assert row["source_summary_csv"] == str(source_dir / consolidator.SUMMARY_FILE)
    assert row["source_report_md"] == str(source_dir / consolidator.REPORT_FILE)
    assert row["condition_to_apply"] == "numeric_tercile:tick_volume_percentile_100:mid_tercile"
    assert row["exact_feature_condition_metadata"] == "filter_a AND filter_b"


def test_missing_folder_creates_missing_rows_and_warnings(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    output_root = Path(args.r_multiple_output_root)
    write_stress_output(output_root, "broad_regime_baseline")

    outputs = consolidator.build_outputs(args)
    rows = read_csv(outputs["consolidated"])
    warnings = read_csv(outputs["warnings"])
    missing_rows = [row for row in rows if row["artifact_status"] == "missing"]

    assert len(rows) == 6
    assert len(missing_rows) == 4
    assert len(warnings) == 4
    assert {row["warning_code"] for row in warnings} == {"r_multiple_output_missing"}


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    output_root = Path(args.r_multiple_output_root)
    write_stress_output(output_root, "broad_regime_baseline")
    write_stress_output(output_root, "single_filter_a")

    outputs = consolidator.build_outputs(args)
    rows = read_csv(outputs["consolidated"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["consolidated_row_count"] == len(rows)
    assert manifest["available_row_count"] == sum(row["artifact_status"] == "available" for row in rows)
    assert manifest["missing_row_count"] == sum(row["artifact_status"] == "missing" for row in rows)
    assert manifest["skipped_row_count"] == sum(row["artifact_status"] == "skipped" for row in rows)
    assert manifest["unreadable_row_count"] == sum(row["artifact_status"] == "unreadable" for row in rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["baseline_type_count"] == 3
    assert manifest["cost_profile_count"] == 2
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_all_rows_are_r_multiple_namespace(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    output_root = Path(args.r_multiple_output_root)
    for baseline_type in consolidator.BASELINE_TYPES:
        write_stress_output(output_root, baseline_type)

    outputs = consolidator.build_outputs(args)
    rows = read_csv(outputs["consolidated"])

    assert {row["metric_namespace"] for row in rows} == {"R_multiple"}
    assert {row["metric_unit"] for row in rows} == {"R"}


def test_report_states_no_candidate_or_trading_decision(tmp_path: Path) -> None:
    args = make_args(tmp_path)

    outputs = consolidator.build_outputs(args)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "artifact consolidation only" in report
    assert "does not execute stress validation" in report
    assert "does not interpret candidate quality" in report
    assert "make trading decisions" in report
    assert "does not decide whether the exact rule is better" in report
