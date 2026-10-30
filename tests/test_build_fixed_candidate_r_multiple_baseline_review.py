from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_r_multiple_baseline_review as review


COMPARISON_FIELDS = [
    "run_id",
    "row_type",
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
    "feature_condition",
    "baseline_filter",
    "cost_config_path",
    "source_artifact_type",
    "source_output_dir",
    "source_csv",
    "source_report",
    "trades",
    "mean_return",
    "profit_factor",
    "cumulative_return",
    "max_drawdown",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "yearly_positive_ratio",
    "timeout_rate",
    "tp_hit_rate",
    "sl_hit_rate",
    "exact_mean_R",
    "exact_profit_factor_R",
    "exact_cumulative_R",
    "exact_max_drawdown_R",
    "baseline_mean_R",
    "baseline_profit_factor_R",
    "baseline_cumulative_R",
    "baseline_max_drawdown_R",
    "baseline_mean_return",
    "baseline_profit_factor",
    "baseline_cumulative_return",
    "baseline_max_drawdown",
    "warning_code",
    "blocking_warning",
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


def exact_row(cost_profile: str) -> dict[str, object]:
    is_p75 = cost_profile == "p75"
    return {
        "run_id": "comparison_v3",
        "row_type": "exact_rule",
        "baseline_type": "exact_rule",
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
        "feature_condition": "filter_a AND filter_b",
        "baseline_filter": "filter_a AND filter_b",
        "cost_config_path": f"config/{cost_profile}.json",
        "source_artifact_type": "candidate_stress_summary",
        "source_output_dir": "exact",
        "source_csv": "exact/candidate_stress_summary.csv",
        "source_report": "exact/candidate_stress_report.md",
        "trades": "10",
        "mean_return": "",
        "profit_factor": "",
        "cumulative_return": "",
        "max_drawdown": "",
        "monthly_positive_ratio": "1.0",
        "quarterly_positive_ratio": "1.0",
        "yearly_positive_ratio": "1.0",
        "timeout_rate": "0.1",
        "tp_hit_rate": "0.5",
        "sl_hit_rate": "0.2",
        "exact_mean_R": "0.50" if is_p75 else "0.40",
        "exact_profit_factor_R": "2.00" if is_p75 else "1.80",
        "exact_cumulative_R": "5.0" if is_p75 else "4.0",
        "exact_max_drawdown_R": "1.0" if is_p75 else "1.2",
        "baseline_mean_R": "",
        "baseline_profit_factor_R": "",
        "baseline_cumulative_R": "",
        "baseline_max_drawdown_R": "",
        "baseline_mean_return": "",
        "baseline_profit_factor": "",
        "baseline_cumulative_return": "",
        "baseline_max_drawdown": "",
        "warning_code": "",
        "blocking_warning": "false",
    }


def baseline_row(baseline_type: str, cost_profile: str, *, namespace: str = "R_multiple") -> dict[str, object]:
    is_p75 = cost_profile == "p75"
    base_values = {
        "broad_regime_baseline": ("20", "0.30", "1.50", "6.0", "2.0", "0.5"),
        "single_filter_a": ("12", "0.60", "2.20", "7.2", "1.6", "1.0"),
        "single_filter_b": ("18", "0.20", "1.20", "3.6", "2.5", "0.5"),
    }
    stress_values = {
        "broad_regime_baseline": ("20", "0.20", "1.30", "4.0", "2.2", "0.5"),
        "single_filter_a": ("12", "0.55", "2.00", "6.6", "1.8", "1.0"),
        "single_filter_b": ("18", "0.10", "1.10", "1.8", "2.7", "0.5"),
    }
    trades, mean_r, pf_r, cumulative_r, dd_r, yearly = (base_values if is_p75 else stress_values)[baseline_type]
    return {
        "run_id": "comparison_v3",
        "row_type": "baseline",
        "baseline_type": baseline_type,
        "cost_profile": cost_profile,
        "artifact_status": "available",
        "metric_namespace": namespace,
        "metric_unit": "R" if namespace == "R_multiple" else "return_fraction",
        "symbol": "GBPUSD",
        "direction": "short",
        "timeframe": "M15",
        "target_horizon": "10",
        "target_family": "preferred_1_5atr_1atr_hit_first",
        "regime_column": "hour_session",
        "regime_value": "Off_hours",
        "feature_condition": "filter_a AND filter_b",
        "baseline_filter": "" if baseline_type == "broad_regime_baseline" else f"{baseline_type}_filter",
        "cost_config_path": f"config/{cost_profile}.json",
        "source_artifact_type": "fixed_candidate_baseline_r_multiple_outputs_consolidated",
        "source_output_dir": f"baseline/{baseline_type}",
        "source_csv": f"baseline/{baseline_type}/candidate_stress_summary.csv",
        "source_report": f"baseline/{baseline_type}/candidate_stress_report.md",
        "trades": trades,
        "mean_return": "",
        "profit_factor": "",
        "cumulative_return": "",
        "max_drawdown": "",
        "monthly_positive_ratio": "",
        "quarterly_positive_ratio": "",
        "yearly_positive_ratio": yearly,
        "timeout_rate": "",
        "tp_hit_rate": "",
        "sl_hit_rate": "",
        "exact_mean_R": "",
        "exact_profit_factor_R": "",
        "exact_cumulative_R": "",
        "exact_max_drawdown_R": "",
        "baseline_mean_R": mean_r if namespace == "R_multiple" else "",
        "baseline_profit_factor_R": pf_r if namespace == "R_multiple" else "",
        "baseline_cumulative_R": cumulative_r if namespace == "R_multiple" else "",
        "baseline_max_drawdown_R": dd_r if namespace == "R_multiple" else "",
        "baseline_mean_return": "0.01" if namespace != "R_multiple" else "",
        "baseline_profit_factor": "1.1" if namespace != "R_multiple" else "",
        "baseline_cumulative_return": "1.2" if namespace != "R_multiple" else "",
        "baseline_max_drawdown": "0.3" if namespace != "R_multiple" else "",
        "warning_code": "",
        "blocking_warning": "false",
    }


def write_comparison_table(path: Path, *, omit_exact: str = "", omit_baseline: tuple[str, str] | None = None, namespace: str = "R_multiple") -> None:
    rows: list[dict[str, object]] = []
    for cost_profile in ("p75", "p90"):
        if cost_profile != omit_exact:
            rows.append(exact_row(cost_profile))
    for baseline_type in review.BASELINE_TYPES:
        for cost_profile in ("p75", "p90"):
            if omit_baseline == (baseline_type, cost_profile):
                continue
            rows.append(baseline_row(baseline_type, cost_profile, namespace=namespace))
    write_csv(path, COMPARISON_FIELDS, rows)


def write_manifest(path: Path, namespaces: list[str] | None = None) -> None:
    path.write_text(
        json.dumps({"metric_namespaces": namespaces or ["R_multiple"], "mixed_metric_namespaces": False}),
        encoding="utf-8",
    )


def make_args(tmp_path: Path, **kwargs: object) -> object:
    comparison_csv = tmp_path / "comparison.csv"
    manifest_json = tmp_path / "manifest.json"
    write_comparison_table(comparison_csv, **kwargs)
    write_manifest(manifest_json, ["net_return"] if kwargs.get("namespace") == "net_return" else ["R_multiple"])
    return review.build_parser().parse_args(
        [
            "--run-id",
            "unit_review",
            "--comparison-table-csv",
            str(comparison_csv),
            "--comparison-manifest-json",
            str(manifest_json),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        review.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = review.build_outputs(make_args(tmp_path))

    assert outputs["review"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_valid_r_multiple_table_creates_six_exact_vs_baseline_rows(tmp_path: Path) -> None:
    outputs = review.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["review"])
    exact_vs_rows = [row for row in rows if row["review_scope"].startswith("exact_vs_")]

    assert len(exact_vs_rows) == 6
    assert {row["review_status"] for row in exact_vs_rows} == {"descriptive_review_available"}
    assert len(rows) == 10


def test_exact_vs_broad_p75_and_p90_rows_are_present(tmp_path: Path) -> None:
    outputs = review.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["review"])
    broad_rows = [row for row in rows if row["review_scope"] == "exact_vs_broad_regime_baseline"]

    assert {row["cost_profile"] for row in broad_rows} == {"p75", "p90"}


def test_exact_vs_single_filter_rows_are_present(tmp_path: Path) -> None:
    outputs = review.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["review"])

    single_a = [row for row in rows if row["review_scope"] == "exact_vs_single_filter_a"]
    single_b = [row for row in rows if row["review_scope"] == "exact_vs_single_filter_b"]
    assert {row["cost_profile"] for row in single_a} == {"p75", "p90"}
    assert {row["cost_profile"] for row in single_b} == {"p75", "p90"}


def test_trade_count_ratio_and_deltas_are_computed(tmp_path: Path) -> None:
    outputs = review.build_outputs(make_args(tmp_path))
    row = next(
        row
        for row in read_csv(outputs["review"])
        if row["review_scope"] == "exact_vs_broad_regime_baseline" and row["cost_profile"] == "p75"
    )

    assert float(row["trade_count_ratio_exact_to_baseline"]) == pytest.approx(0.5)
    assert float(row["delta_mean_R"]) == pytest.approx(0.2)
    assert float(row["delta_profit_factor_R"]) == pytest.approx(0.5)
    assert float(row["delta_cumulative_R"]) == pytest.approx(-1.0)
    assert float(row["delta_max_drawdown_R"]) == pytest.approx(-1.0)
    assert float(row["delta_yearly_positive_ratio"]) == pytest.approx(0.5)
    assert "same_namespace_descriptive_only" in row["descriptive_tradeoff_note"]


def test_namespace_mismatch_creates_blocked_warning(tmp_path: Path) -> None:
    outputs = review.build_outputs(make_args(tmp_path, namespace="net_return"))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])

    blocked = [row for row in rows if row["review_status"] == "blocked_metric_namespace_mismatch"]
    assert blocked
    assert {row["warning_code"] for row in warnings} == {"metric_namespace_mismatch"}


def test_missing_exact_row_creates_unavailable_status(tmp_path: Path) -> None:
    outputs = review.build_outputs(make_args(tmp_path, omit_exact="p75"))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])

    missing = [
        row
        for row in rows
        if row["cost_profile"] == "p75" and row["review_status"] == "unavailable_missing_exact_row"
    ]
    assert missing
    assert "missing_exact_row" in {row["warning_code"] for row in warnings}


def test_missing_baseline_row_creates_unavailable_status(tmp_path: Path) -> None:
    outputs = review.build_outputs(make_args(tmp_path, omit_baseline=("single_filter_a", "p90")))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])

    row = next(
        row
        for row in rows
        if row["review_scope"] == "exact_vs_single_filter_a" and row["cost_profile"] == "p90"
    )
    assert row["review_status"] == "unavailable_missing_baseline_row"
    assert "missing_baseline_row" in {warning["warning_code"] for warning in warnings}


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = review.build_outputs(make_args(tmp_path, omit_baseline=("single_filter_b", "p90")))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["review_row_count"] == len(rows)
    assert manifest["descriptive_review_available_count"] == sum(
        row["review_status"] == "descriptive_review_available" for row in rows
    )
    assert manifest["unavailable_missing_baseline_row_count"] == sum(
        row["review_status"] == "unavailable_missing_baseline_row" for row in rows
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
    outputs = review.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-only descriptive review" in report
    assert "No candidate-quality evaluation" in report
    assert "trading decision" in report
    assert "not approval or rejection" in report
    assert "walk-forward review" in report
    assert "timeout policy review" in report


def test_no_child_or_heavy_commands_are_executed() -> None:
    source = Path(review.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "validate_regime_candidate_stress.py --" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
