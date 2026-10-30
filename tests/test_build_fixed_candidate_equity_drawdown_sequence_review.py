from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_equity_drawdown_sequence_review as sequence_review


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


def trade_rows(values: list[float]) -> list[dict[str, object]]:
    return [
        {
            "entry_time": f"2023-01-{index + 1:02d} 00:00:00",
            "exit_time": f"2023-01-{index + 1:02d} 00:15:00",
            "exit_reason": "SL" if value < 0 else "TP",
            "bars_held": "10",
            "R": value,
            "net_R": value,
        }
        for index, value in enumerate(values)
    ]


def equity_rows(drawdowns: list[float]) -> list[dict[str, object]]:
    cumulative = 0.0
    rows: list[dict[str, object]] = []
    for index, drawdown in enumerate(drawdowns, start=1):
        cumulative += 1.0 - drawdown / 100.0
        rows.append(
            {
                "trade_index": index,
                "exit_time": f"2023-01-{index:02d} 00:15:00",
                "cumulative_R": cumulative,
                "drawdown_R": drawdown,
            }
        )
    return rows


def write_stress_dir(
    path: Path,
    *,
    base_values: list[float],
    stress_values: list[float],
    base_drawdowns: list[float],
    stress_drawdowns: list[float],
    include_base_trade: bool = True,
    include_base_equity: bool = True,
    include_stress_equity: bool = True,
    unrecognized_equity_columns: bool = False,
) -> None:
    write_csv(
        path / sequence_review.SUMMARY_FILE,
        ["target_family", "horizon"],
        [{"target_family": "preferred_1_5atr_1atr_hit_first", "horizon": "10"}],
    )
    if include_base_trade:
        write_csv(
            path / sequence_review.TRADE_BASE_FILE,
            ["entry_time", "exit_time", "exit_reason", "bars_held", "R", "net_R"],
            trade_rows(base_values),
        )
    write_csv(
        path / sequence_review.TRADE_STRESS_FILE,
        ["entry_time", "exit_time", "exit_reason", "bars_held", "R", "net_R"],
        trade_rows(stress_values),
    )
    if include_base_equity:
        if unrecognized_equity_columns:
            write_csv(path / sequence_review.EQUITY_BASE_FILE, ["trade_no", "value"], [{"trade_no": 1, "value": 1.0}])
        else:
            write_csv(
                path / sequence_review.EQUITY_BASE_FILE,
                ["trade_index", "exit_time", "cumulative_R", "drawdown_R"],
                equity_rows(base_drawdowns),
            )
    if include_stress_equity:
        write_csv(
            path / sequence_review.EQUITY_STRESS_FILE,
            ["trade_index", "exit_time", "cumulative_R", "drawdown_R"],
            equity_rows(stress_drawdowns),
        )
    (path / sequence_review.REPORT_FILE).write_text("# Stress report\n", encoding="utf-8")


def make_args(
    tmp_path: Path,
    *,
    exact_base_trade: bool = True,
    exact_base_equity: bool = True,
    exact_stress_equity: bool = True,
    exact_bad_equity_columns: bool = False,
) -> object:
    exact_dir = tmp_path / "exact"
    single_dir = tmp_path / "single_filter_a"
    timeout_dir = tmp_path / "timeout_artifact_review"
    walk_dir = tmp_path / "walkforward_drawdown_review"
    exact_base_values = [-1.0] * 10 + [1.0] * 10
    exact_stress_values = [-1.0] * 10 + [2.0] * 10
    single_base_values = [-2.0] * 10 + [1.0] * 10
    single_stress_values = [-2.0] * 10 + [2.0] * 10
    write_stress_dir(
        exact_dir,
        base_values=exact_base_values,
        stress_values=exact_stress_values,
        base_drawdowns=[0.0, 1.0, 5.0, 0.0] + [0.0] * 16,
        stress_drawdowns=[0.0, 1.0, 6.0, 0.0] + [0.0] * 16,
        include_base_trade=exact_base_trade,
        include_base_equity=exact_base_equity,
        include_stress_equity=exact_stress_equity,
        unrecognized_equity_columns=exact_bad_equity_columns,
    )
    write_stress_dir(
        single_dir,
        base_values=single_base_values,
        stress_values=single_stress_values,
        base_drawdowns=[0.0, 2.0, 12.0, 0.0] + [0.0] * 16,
        stress_drawdowns=[0.0, 2.0, 13.0, 0.0] + [0.0] * 16,
    )
    write_csv(timeout_dir / "fixed_candidate_timeout_policy_artifact_review.csv", ["review_scope"], [{"review_scope": "x"}])
    write_csv(walk_dir / "fixed_candidate_walkforward_drawdown_artifact_review.csv", ["review_scope"], [{"review_scope": "x"}])
    return sequence_review.build_parser().parse_args(
        [
            "--run-id",
            "unit_sequence_review",
            "--exact-stress-dir",
            str(exact_dir),
            "--single-filter-a-stress-dir",
            str(single_dir),
            "--timeout-artifact-review-dir",
            str(timeout_dir),
            "--walkforward-drawdown-review-dir",
            str(walk_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        sequence_review.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path))

    assert outputs["review"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_equity_curve_and_trade_log_columns_are_detected(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert "cumulative_R" in manifest["detected_equity_columns"]
    assert "drawdown_R" in manifest["detected_equity_columns"]
    assert "net_R" in manifest["detected_trade_columns"]
    assert "exit_reason" in manifest["detected_trade_columns"]


def test_base_and_stress_equity_trade_logs_are_both_handled(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["review"])
    scopes = {row["review_scope"] for row in rows}

    assert "exact_rule_base_equity_sequence_review" in scopes
    assert "exact_rule_stress_equity_sequence_review" in scopes
    assert "single_filter_a_base_equity_sequence_review" in scopes
    assert "single_filter_a_stress_equity_sequence_review" in scopes
    assert any(row["cost_profile"] == "p75" for row in rows)
    assert any(row["cost_profile"] == "p90" for row in rows)


def test_max_drawdown_is_read_from_fixture_equity_curves(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path))
    row = next(row for row in read_csv(outputs["review"]) if row["review_scope"] == "exact_rule_base_equity_sequence_review")

    assert row["max_drawdown_R"] == "5.0"
    assert row["max_drawdown_start_index"] == "2"
    assert row["max_drawdown_end_index"] == "3"
    assert row["max_drawdown_duration_trades"] == "2"


def test_drawdown_duration_caveat_is_emitted_when_not_derivable(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path, exact_bad_equity_columns=True))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    row = next(row for row in rows if row["review_scope"] == "exact_rule_base_equity_sequence_review")

    assert row["readiness_status"] == "descriptive_sequence_review_available_with_caveat"
    assert "drawdown_duration_not_derivable" in row["caveat"]
    assert "exact_rule_base_equity_sequence_review_drawdown_duration_not_derivable" in {
        warning["warning_code"] for warning in warnings
    }


def test_worst_rolling_trade_sums_are_computed_correctly(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path))
    exact = next(row for row in read_csv(outputs["review"]) if row["review_scope"] == "exact_rule_base_equity_sequence_review")
    single = next(row for row in read_csv(outputs["review"]) if row["review_scope"] == "single_filter_a_base_equity_sequence_review")

    assert exact["worst_10_trade_sum_net_R"] == "-10.0"
    assert exact["worst_20_trade_sum_net_R"] == "0.0"
    assert single["worst_10_trade_sum_net_R"] == "-20.0"
    assert single["worst_20_trade_sum_net_R"] == "-10.0"


def test_longest_negative_trade_streak_is_computed_correctly(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path))
    row = next(row for row in read_csv(outputs["review"]) if row["review_scope"] == "exact_rule_base_equity_sequence_review")

    assert row["longest_negative_trade_streak"] == "10"
    assert row["average_negative_trade_streak_length"] == "10.0"
    assert row["loss_cluster_count"] == "1"


def test_exact_vs_single_filter_a_comparison_rows_are_generated(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["review"])
    base = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_base_drawdown_sequence_comparison")

    assert base["row_type"] == "sequence_comparison"
    assert base["exact_max_drawdown_R"] == "5.0"
    assert base["single_filter_a_max_drawdown_R"] == "12.0"
    assert base["drawdown_delta"] == "-7.0"
    assert base["exact_worst_20_trade_sum_net_R"] == "0.0"
    assert base["single_filter_a_worst_20_trade_sum_net_R"] == "-10.0"
    assert base["worst_20_trade_sum_delta"] == "10.0"


def test_missing_optional_equity_curve_creates_non_blocking_caveat(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path, exact_stress_equity=False))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    row = next(row for row in rows if row["review_scope"] == "exact_rule_stress_equity_sequence_review")

    assert row["readiness_status"] == "descriptive_sequence_review_available_with_caveat"
    assert row["blocking_warning"] == "false"
    assert {warning["blocking_warning"] for warning in warnings} == {"false"}
    assert "exact_rule_stress_equity_sequence_review_equity_curve_missing" in {
        warning["warning_code"] for warning in warnings
    }


def test_missing_required_trade_log_creates_unavailable_status(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path, exact_base_trade=False))
    rows = read_csv(outputs["review"])
    row = next(row for row in rows if row["review_scope"] == "exact_rule_base_equity_sequence_review")

    assert row["readiness_status"] == "unavailable_missing_artifact"
    assert row["artifact_status"] == "missing"
    assert row["required_next_artifact"] == "trade_log_base_or_trade_log_stress"


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path, exact_stress_equity=False))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["review_row_count"] == len(rows)
    assert manifest["descriptive_sequence_review_available_count"] == sum(
        row["readiness_status"] == "descriptive_sequence_review_available" for row in rows
    )
    assert manifest["descriptive_sequence_review_available_with_caveat_count"] == sum(
        row["readiness_status"] == "descriptive_sequence_review_available_with_caveat" for row in rows
    )
    assert manifest["unavailable_missing_artifact_count"] == sum(
        row["readiness_status"] == "unavailable_missing_artifact" for row in rows
    )
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


def test_report_includes_artifact_only_and_no_decision_caveats(tmp_path: Path) -> None:
    outputs = sequence_review.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-only descriptive review" in report
    assert "No candidate-quality conclusion" in report
    assert "trading decision" in report
    assert "No TP/SL path outcomes were recalculated" in report
    assert "does not replace true walk-forward validation or timeout policy review" in report


def test_no_path_recalculation_or_child_commands_are_present() -> None:
    source = Path(sequence_review.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "run_tp_sl_path_backtests.py" not in source
    assert "validate_regime_candidate_stress.py --" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
