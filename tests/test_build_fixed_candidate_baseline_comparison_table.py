from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_baseline_comparison_table as comparison


MATRIX_FIELDS = [
    "baseline_type",
    "cost_profile",
    "symbol",
    "direction",
    "timeframe",
    "target_horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "feature_condition",
    "baseline_filter",
    "cost_config_path",
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


def matrix_row(baseline_type: str, cost_profile: str, baseline_filter: str = "") -> dict[str, str]:
    feature_condition = "filter_a AND filter_b"
    return {
        "baseline_type": baseline_type,
        "cost_profile": cost_profile,
        "symbol": "GBPUSD",
        "direction": "short",
        "timeframe": "M15",
        "target_horizon": "10",
        "target_family": "preferred_1_5atr_1atr_hit_first",
        "regime_column": "hour_session",
        "regime_value": "Off_hours",
        "feature_condition": feature_condition,
        "baseline_filter": baseline_filter or (feature_condition if baseline_type == "exact_rule" else ""),
        "cost_config_path": f"config/brokers/{cost_profile}.json",
    }


def write_matrix(path: Path) -> None:
    rows = [
        matrix_row("exact_rule", "p75", "filter_a AND filter_b"),
        matrix_row("exact_rule", "p90", "filter_a AND filter_b"),
        matrix_row("broad_regime_baseline", "p75"),
        matrix_row("broad_regime_baseline", "p90"),
        matrix_row("single_filter_a", "p75", "filter_a"),
        matrix_row("single_filter_a", "p90", "filter_a"),
        matrix_row("single_filter_b", "p75", "filter_b"),
        matrix_row("single_filter_b", "p90", "filter_b"),
    ]
    write_csv(path, MATRIX_FIELDS, rows)


def write_exact_stress_output(root: Path) -> None:
    write_csv(
        root / "candidate_stress_summary.csv",
        [
            "symbol",
            "direction",
            "timeframe",
            "target_family",
            "horizon",
            "regime_column",
            "regime_value",
            "feature_condition",
            "base_cost_config_path",
            "stress_cost_config_path",
            "sequential_trades_count",
            "stress_sequential_trades_count",
            "mean_R",
            "stress_mean_R",
            "profit_factor_R",
            "stress_profit_factor_R",
            "cumulative_R",
            "stress_cumulative_R",
            "max_drawdown_R",
            "stress_max_drawdown_R",
            "monthly_positive_ratio",
            "quarterly_positive_ratio",
            "yearly_positive_ratio",
            "timeout_rate",
            "tp_hit_rate",
            "sl_hit_rate",
        ],
        [
            {
                "symbol": "GBPUSD",
                "direction": "short",
                "timeframe": "M15",
                "target_family": "preferred_1_5atr_1atr_hit_first",
                "horizon": "10",
                "regime_column": "hour_session",
                "regime_value": "Off_hours",
                "feature_condition": "filter_a AND filter_b",
                "base_cost_config_path": "config/brokers/p75.json",
                "stress_cost_config_path": "config/brokers/p90.json",
                "sequential_trades_count": "708",
                "stress_sequential_trades_count": "708",
                "mean_R": "0.49",
                "stress_mean_R": "0.46",
                "profit_factor_R": "2.9",
                "stress_profit_factor_R": "2.7",
                "cumulative_R": "348",
                "stress_cumulative_R": "327",
                "max_drawdown_R": "8.2",
                "stress_max_drawdown_R": "8.4",
                "monthly_positive_ratio": "0.87",
                "quarterly_positive_ratio": "1.0",
                "yearly_positive_ratio": "1.0",
                "timeout_rate": "0.31",
                "tp_hit_rate": "0.51",
                "sl_hit_rate": "0.16",
            }
        ],
    )
    (root / "candidate_stress_report.md").write_text("# Stress report\n", encoding="utf-8")


def write_baseline_consolidated_output(root: Path) -> None:
    rows: list[dict[str, object]] = []
    for baseline_type in ["broad_regime_baseline", "single_filter_a", "single_filter_b"]:
        for cost_profile in ["p75", "p90"]:
            rows.append(
                {
                    "baseline_type": baseline_type,
                    "cost_profile": cost_profile,
                    "cost_config_path": f"config/brokers/{cost_profile}.json",
                    "artifact_status": "available",
                    "source_output_dir": str(root / "raw" / f"{baseline_type}_{cost_profile}"),
                    "source_csv": str(root / "raw" / f"{baseline_type}_{cost_profile}" / "baseline_diagnostics_detail.csv"),
                    "source_report": str(root / "raw" / f"{baseline_type}_{cost_profile}" / "baseline_diagnostics_report.md"),
                    "symbol": "GBPUSD",
                    "direction": "short",
                    "baseline_key": "" if baseline_type == "broad_regime_baseline" else f"{baseline_type}_filter",
                    "combination_key": "filter_a AND filter_b",
                    "baseline_trades_count": "100",
                    "baseline_mean_return": "0.01",
                    "baseline_profit_factor": "1.1",
                    "baseline_cumulative_return": "1.2",
                    "baseline_max_drawdown": "0.3",
                    "baseline_monthly_positive_ratio": "0.5",
                    "warning_code": "",
                    "blocking_warning": "false",
                }
            )
    write_csv(
        root / "fixed_candidate_baseline_outputs_consolidated.csv",
        [
            "baseline_type",
            "cost_profile",
            "cost_config_path",
            "artifact_status",
            "source_output_dir",
            "source_csv",
            "source_report",
            "symbol",
            "direction",
            "baseline_key",
            "combination_key",
            "baseline_trades_count",
            "baseline_mean_return",
            "baseline_profit_factor",
            "baseline_cumulative_return",
            "baseline_max_drawdown",
            "baseline_monthly_positive_ratio",
            "warning_code",
            "blocking_warning",
        ],
        rows,
    )
    (root / "fixed_candidate_baseline_outputs_report.md").write_text("# Baseline report\n", encoding="utf-8")


def write_r_multiple_baseline_consolidated_output(root: Path) -> None:
    rows: list[dict[str, object]] = []
    for baseline_type in ["broad_regime_baseline", "single_filter_a", "single_filter_b"]:
        for cost_profile in ["p75", "p90"]:
            rows.append(
                {
                    "baseline_type": baseline_type,
                    "cost_profile": cost_profile,
                    "artifact_status": "available",
                    "metric_namespace": "R_multiple",
                    "metric_unit": "R",
                    "symbol": "GBPUSD",
                    "direction": "short",
                    "timeframe": "M15",
                    "target_horizon": "10",
                    "target_family": "preferred_1_5atr_1atr_hit_first",
                    "regime_column": "hour_session",
                    "regime_value": "Off_hours",
                    "condition_to_apply": "" if baseline_type == "broad_regime_baseline" else f"{baseline_type}_filter",
                    "exact_feature_condition_metadata": "filter_a AND filter_b",
                    "cost_config_path": f"config/brokers/{cost_profile}.json",
                    "source_output_dir": str(root / "raw" / baseline_type),
                    "source_summary_csv": str(root / "raw" / baseline_type / "candidate_stress_summary.csv"),
                    "source_report_md": str(root / "raw" / baseline_type / "candidate_stress_report.md"),
                    "source_trade_csv": str(root / "raw" / baseline_type / f"trade_log_{cost_profile}.csv"),
                    "trades": "100",
                    "mean_R": "0.22" if cost_profile == "p75" else "0.18",
                    "profit_factor_R": "1.7" if cost_profile == "p75" else "1.5",
                    "cumulative_R": "22.0" if cost_profile == "p75" else "18.0",
                    "max_drawdown_R": "4.0" if cost_profile == "p75" else "4.5",
                    "yearly_positive_ratio": "1.0",
                    "warning_code": "",
                    "blocking_warning": "false",
                }
            )
    write_csv(
        root / "fixed_candidate_baseline_r_multiple_outputs_consolidated.csv",
        [
            "baseline_type",
            "cost_profile",
            "artifact_status",
            "metric_namespace",
            "metric_unit",
            "symbol",
            "direction",
            "timeframe",
            "target_horizon",
            "target_family",
            "regime_column",
            "regime_value",
            "condition_to_apply",
            "exact_feature_condition_metadata",
            "cost_config_path",
            "source_output_dir",
            "source_summary_csv",
            "source_report_md",
            "source_trade_csv",
            "trades",
            "mean_R",
            "profit_factor_R",
            "cumulative_R",
            "max_drawdown_R",
            "yearly_positive_ratio",
            "warning_code",
            "blocking_warning",
        ],
        rows,
    )
    (root / "fixed_candidate_baseline_r_multiple_outputs_report.md").write_text("# R baseline report\n", encoding="utf-8")


def make_args(
    tmp_path: Path,
    *,
    exact: bool = True,
    baseline: bool = True,
    baseline_kind: str = "net_return",
) -> object:
    exact_dir = tmp_path / "exact"
    baseline_dir = tmp_path / "baseline"
    matrix_csv = tmp_path / "matrix.csv"
    write_matrix(matrix_csv)
    if exact:
        write_exact_stress_output(exact_dir)
    if baseline:
        if baseline_kind == "r_multiple":
            write_r_multiple_baseline_consolidated_output(baseline_dir)
        else:
            write_baseline_consolidated_output(baseline_dir)
    return comparison.build_parser().parse_args(
        [
            "--run-id",
            "unit",
            "--exact-stress-dir",
            str(exact_dir),
            "--baseline-consolidated-dir",
            str(baseline_dir),
            "--matrix-csv",
            str(matrix_csv),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        comparison.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))

    assert outputs["comparison"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_exact_stress_fixture_creates_exact_rule_p75_and_p90_rows(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["comparison"])
    exact_rows = [row for row in rows if row["row_type"] == "exact_rule"]

    assert {row["cost_profile"] for row in exact_rows} == {"p75", "p90"}
    assert {row["artifact_status"] for row in exact_rows} == {"available"}
    assert {row["metric_namespace"] for row in exact_rows} == {"R_multiple"}
    assert {row["metric_unit"] for row in exact_rows} == {"R"}
    p75 = next(row for row in exact_rows if row["cost_profile"] == "p75")
    p90 = next(row for row in exact_rows if row["cost_profile"] == "p90")
    assert p75["exact_mean_R"] == "0.49"
    assert p90["exact_mean_R"] == "0.46"
    assert p75["mean_return"] == ""


def test_baseline_consolidated_fixture_creates_six_baseline_rows(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["comparison"])
    baseline_rows = [row for row in rows if row["row_type"] == "baseline"]

    assert len(baseline_rows) == 6
    assert {row["artifact_status"] for row in baseline_rows} == {"available"}
    assert {row["metric_namespace"] for row in baseline_rows} == {"net_return"}
    assert {row["metric_unit"] for row in baseline_rows} == {"return_fraction"}
    assert {row["baseline_mean_return"] for row in baseline_rows} == {"0.01"}
    assert {row["mean_return"] for row in baseline_rows} == {"0.01"}
    assert {row["baseline_type"] for row in baseline_rows} == {
        "broad_regime_baseline",
        "single_filter_a",
        "single_filter_b",
    }


def test_r_multiple_baseline_input_creates_eight_rows_all_in_r_multiple(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path, baseline_kind="r_multiple"))
    rows = read_csv(outputs["comparison"])
    baseline_rows = [row for row in rows if row["row_type"] == "baseline"]

    assert len(rows) == 8
    assert len(baseline_rows) == 6
    assert {row["metric_namespace"] for row in rows} == {"R_multiple"}
    assert {row["metric_unit"] for row in rows} == {"R"}
    assert {row["baseline_mean_R"] for row in baseline_rows} == {"0.22", "0.18"}
    assert {row["baseline_profit_factor_R"] for row in baseline_rows} == {"1.7", "1.5"}
    assert {row["baseline_mean_return"] for row in baseline_rows} == {""}
    assert {row["mean_return"] for row in baseline_rows} == {""}


def test_r_multiple_baseline_input_does_not_emit_mixed_namespace_warning(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path, baseline_kind="r_multiple"))
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "mixed_metric_namespace_caveat" not in {row["warning_code"] for row in warnings}
    assert manifest["mixed_metric_namespaces"] is False
    assert manifest["metric_namespaces"] == ["R_multiple"]
    assert "Exact-rule and baseline rows in this table use the same metric namespace" in report


def test_final_table_has_eight_expected_rows(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["comparison"])

    assert len(rows) == 8
    assert rows[0]["row_type"] == "exact_rule"
    assert rows[-1]["baseline_type"] == "single_filter_b"


def test_missing_exact_stress_artifact_produces_warning_and_missing_exact_rows(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path, exact=False))
    rows = read_csv(outputs["comparison"])
    warnings = read_csv(outputs["warnings"])
    exact_rows = [row for row in rows if row["row_type"] == "exact_rule"]

    assert {row["artifact_status"] for row in exact_rows} == {"missing"}
    assert sum(row["warning_code"] == "exact_stress_summary_missing" for row in warnings) == 2


def test_missing_baseline_consolidated_artifact_produces_warning_and_missing_baseline_rows(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path, baseline=False))
    rows = read_csv(outputs["comparison"])
    warnings = read_csv(outputs["warnings"])
    baseline_rows = [row for row in rows if row["row_type"] == "baseline"]

    assert len(baseline_rows) == 6
    assert {row["artifact_status"] for row in baseline_rows} == {"missing"}
    assert sum(row["warning_code"] == "baseline_consolidated_missing" for row in warnings) == 6


def test_cost_config_path_is_preserved(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["comparison"])

    assert next(row for row in rows if row["row_type"] == "exact_rule" and row["cost_profile"] == "p75")[
        "cost_config_path"
    ] == "config/brokers/p75.json"
    assert next(row for row in rows if row["baseline_type"] == "single_filter_b" and row["cost_profile"] == "p90")[
        "cost_config_path"
    ] == "config/brokers/p90.json"


def test_mixed_metric_namespaces_trigger_non_blocking_warning(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    warning = next(row for row in warnings if row["warning_code"] == "mixed_metric_namespace_caveat")

    assert warning["severity"] == "info"
    assert warning["blocking_warning"] == "false"
    assert "R-multiple" in warning["message"]
    assert "net-return" in warning["message"]
    assert manifest["mixed_metric_namespaces"] is True
    assert set(manifest["metric_namespaces"]) == {"R_multiple", "net_return"}


def test_source_paths_are_preserved(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["comparison"])
    exact = next(row for row in rows if row["row_type"] == "exact_rule" and row["cost_profile"] == "p75")
    baseline = next(row for row in rows if row["baseline_type"] == "single_filter_a" and row["cost_profile"] == "p75")

    assert exact["source_csv"].endswith("candidate_stress_summary.csv")
    assert exact["source_report"].endswith("candidate_stress_report.md")
    assert baseline["source_csv"].endswith("baseline_diagnostics_detail.csv")
    assert baseline["source_report"].endswith("baseline_diagnostics_report.md")


def test_r_multiple_source_paths_and_cost_profiles_are_preserved(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path, baseline_kind="r_multiple"))
    rows = read_csv(outputs["comparison"])
    baseline = next(row for row in rows if row["baseline_type"] == "single_filter_a" and row["cost_profile"] == "p90")

    assert baseline["source_artifact_type"] == "fixed_candidate_baseline_r_multiple_outputs_consolidated"
    assert baseline["source_csv"].endswith("candidate_stress_summary.csv")
    assert baseline["source_report"].endswith("candidate_stress_report.md")
    assert baseline["cost_config_path"] == "config/brokers/p90.json"
    assert baseline["feature_condition"] == "filter_a AND filter_b"
    assert baseline["baseline_filter"] == "filter_a"


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path, baseline=False))
    rows = read_csv(outputs["comparison"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["comparison_row_count"] == len(rows)
    assert manifest["exact_rule_row_count"] == sum(row["row_type"] == "exact_rule" for row in rows)
    assert manifest["baseline_row_count"] == sum(row["row_type"] == "baseline" for row in rows)
    assert manifest["available_row_count"] == sum(row["artifact_status"] == "available" for row in rows)
    assert manifest["missing_row_count"] == sum(row["artifact_status"] == "missing" for row in rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_states_no_candidate_or_trading_decision(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Research-only artifact fusion" in report
    assert "does not rank baselines" in report
    assert "does not compare profitability" in report
    assert "not directly numerically comparable unless normalized" in report
    assert "Metric Namespaces" in report
    assert "No candidate-quality evaluation was performed" in report
    assert "No trading decision was made" in report
    assert "row-level spread fields" in report


def test_no_child_scripts_are_executed() -> None:
    source = Path(comparison.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
    assert "validate_regime_candidate_stress.py --" not in source
