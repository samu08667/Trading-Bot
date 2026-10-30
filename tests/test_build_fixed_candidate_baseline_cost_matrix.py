from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_baseline_cost_matrix as matrix_module


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


def write_stress_summary(path: Path) -> None:
    fieldnames = [
        "symbol",
        "direction",
        "timeframe",
        "target_family",
        "horizon",
        "regime_column",
        "regime_value",
        "tp_atr",
        "sl_atr",
        "same_bar_policy",
        "candidate_scope",
        "feature_condition",
        "sequential_trades_count",
        "mean_R",
        "profit_factor_R",
        "cumulative_R",
        "max_drawdown_R",
        "monthly_positive_ratio",
        "quarterly_positive_ratio",
        "yearly_positive_ratio",
        "timeout_rate",
        "tp_hit_rate",
        "sl_hit_rate",
        "base_cost_config_path",
        "stress_cost_config_path",
        "stress_sequential_trades_count",
        "stress_mean_R",
        "stress_profit_factor_R",
        "stress_cumulative_R",
        "stress_max_drawdown_R",
    ]
    write_csv(
        path / "candidate_stress_summary.csv",
        fieldnames,
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
                "same_bar_policy": "stop_first",
                "candidate_scope": "exact_feature_combination",
                "feature_condition": matrix_module.DEFAULT_FEATURE_CONDITION,
                "sequential_trades_count": "708",
                "mean_R": "0.49",
                "profit_factor_R": "2.93",
                "cumulative_R": "348.7",
                "max_drawdown_R": "8.21",
                "monthly_positive_ratio": "0.87",
                "quarterly_positive_ratio": "1.0",
                "yearly_positive_ratio": "1.0",
                "timeout_rate": "0.31",
                "tp_hit_rate": "0.51",
                "sl_hit_rate": "0.16",
                "base_cost_config_path": "config/brokers/p75.json",
                "stress_cost_config_path": "config/brokers/p90.json",
                "stress_sequential_trades_count": "708",
                "stress_mean_R": "0.46",
                "stress_profit_factor_R": "2.74",
                "stress_cumulative_R": "327.0",
                "stress_max_drawdown_R": "8.40",
            }
        ],
    )


def write_controlled_expansion(path: Path) -> None:
    write_csv(
        path / "controlled_rule_expansion_baseline_plan.csv",
        ["plan_item", "comparison", "status", "existing_file_used", "notes"],
        [
            {
                "plan_item": "broad_regime_baseline",
                "comparison": "exact rule vs broad regime baseline",
                "status": "planned_not_run",
                "existing_file_used": "",
                "notes": "future review",
            },
            {
                "plan_item": "single_filter_baseline_a",
                "comparison": "exact rule vs single filter A",
                "status": "planned_not_run",
                "existing_file_used": "",
                "notes": "future review",
            },
            {
                "plan_item": "single_filter_baseline_b",
                "comparison": "exact rule vs single filter B",
                "status": "planned_not_run",
                "existing_file_used": "",
                "notes": "future review",
            },
            {
                "plan_item": "regime_no_feature_baseline",
                "comparison": "exact rule vs no-feature baseline",
                "status": "planned_not_run",
                "existing_file_used": "",
                "notes": "future review",
            },
        ],
    )
    write_csv(
        path / "controlled_rule_expansion_cost_sensitivity_plan.csv",
        ["plan_item", "comparison", "status", "existing_file_used", "notes"],
        [
            {
                "plan_item": "current_conservative_stress",
                "comparison": "current p90 stress",
                "status": "documented_existing_review",
                "existing_file_used": "",
                "notes": "already reviewed",
            }
        ],
    )


def make_args(tmp_path: Path, *, with_plan: bool = True) -> object:
    exact_dir = tmp_path / "stress"
    audit_dir = tmp_path / "audit"
    write_stress_summary(exact_dir)
    if with_plan:
        write_controlled_expansion(audit_dir / "controlled_expansion")
    return matrix_module.build_parser().parse_args(
        [
            "--run-id",
            "unit",
            "--exact-stress-dir",
            str(exact_dir),
            "--candidate-audit-dir",
            str(audit_dir),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        matrix_module.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = matrix_module.build_outputs(make_args(tmp_path))

    assert outputs["matrix"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_stress_summary_creates_exact_rule_p75_and_p90_available_rows(tmp_path: Path) -> None:
    outputs = matrix_module.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["matrix"])
    exact_rows = {
        row["cost_profile"]: row
        for row in rows
        if row["baseline_type"] == "exact_rule"
    }

    assert exact_rows["p75"]["artifact_status"] == "available"
    assert exact_rows["p75"]["mean_R"] == "0.49"
    assert exact_rows["p75"]["cost_config_path"] == "config/brokers/p75.json"
    assert exact_rows["p90"]["artifact_status"] == "available"
    assert exact_rows["p90"]["mean_R"] == "0.46"
    assert exact_rows["p90"]["cost_config_path"] == "config/brokers/p90.json"


def test_controlled_expansion_plan_creates_planned_not_run_rows(tmp_path: Path) -> None:
    outputs = matrix_module.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["matrix"])

    planned = [
        row
        for row in rows
        if row["baseline_type"] in {"broad_regime_baseline", "single_filter_a", "single_filter_b"}
    ]
    assert len(planned) == 6
    assert {row["artifact_status"] for row in planned} == {"planned_not_run"}
    assert all(row["planned_source"].endswith("controlled_rule_expansion_baseline_plan.csv") for row in planned)


def test_missing_plans_create_missing_rows(tmp_path: Path) -> None:
    outputs = matrix_module.build_outputs(make_args(tmp_path, with_plan=False))
    rows = read_csv(outputs["matrix"])

    missing = [
        row
        for row in rows
        if row["baseline_type"] in {"broad_regime_baseline", "single_filter_a", "single_filter_b"}
    ]
    assert {row["artifact_status"] for row in missing} == {"missing"}
    assert {row["warning_code"] for row in missing} == {"baseline_row_missing"}


def test_no_feature_off_hours_duplicate_behavior_is_explicit(tmp_path: Path) -> None:
    outputs = matrix_module.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["matrix"])
    no_feature = [row for row in rows if row["baseline_type"] == "no_feature_off_hours"]

    assert len(no_feature) == 2
    assert {row["artifact_status"] for row in no_feature} == {"not_applicable"}
    assert {row["warning_code"] for row in no_feature} == {"duplicate_baseline_definition"}


def test_matrix_has_required_columns(tmp_path: Path) -> None:
    outputs = matrix_module.build_outputs(make_args(tmp_path))

    with outputs["matrix"].open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == matrix_module.FIELDNAMES


def test_manifest_count_fields_match_matrix_and_warnings(tmp_path: Path) -> None:
    outputs = matrix_module.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["matrix"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["matrix_row_count"] == len(rows)
    assert manifest["available_row_count"] == sum(row["artifact_status"] == "available" for row in rows)
    assert manifest["planned_not_run_row_count"] == sum(row["artifact_status"] == "planned_not_run" for row in rows)
    assert manifest["missing_row_count"] == sum(row["artifact_status"] == "missing" for row in rows)
    assert manifest["not_applicable_row_count"] == sum(row["artifact_status"] == "not_applicable" for row in rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True
    assert manifest["no_backtests_run"] is True


def test_report_states_no_child_scripts_or_decisions(tmp_path: Path) -> None:
    outputs = matrix_module.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No child scripts were executed" in report
    assert "No baseline diagnostics were executed" in report
    assert "No backtests were run" in report
    assert "No candidate-quality evaluation" in report
    assert "trading decision was made" in report


def test_safety_terms_are_not_introduced_as_executable_behavior() -> None:
    source = Path(matrix_module.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "order_send" not in source
    assert "place_order" not in source
    assert "open_position" not in source
    assert "close_position" not in source
    assert "MetaTrader5" not in source
    assert "mt5.initialize" not in source
    assert "copy_rates" not in source
    assert "import_price_bars" not in source
    assert "generate_price_features" not in source
    assert "generate_market_features" not in source
    assert "generate_ml_dataset" not in source
    assert "init_database" not in source


def test_no_child_scripts_are_executed_in_tests(tmp_path: Path) -> None:
    outputs = matrix_module.build_outputs(make_args(tmp_path))

    assert len(read_csv(outputs["matrix"])) == 10
    assert not (tmp_path / "baseline_diagnostics").exists()
