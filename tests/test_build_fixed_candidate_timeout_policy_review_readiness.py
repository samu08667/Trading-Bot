from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_timeout_policy_review_readiness as timeout_readiness


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
    include_trade_logs: bool = True,
    include_timeout_columns: bool = True,
    include_summary: bool = True,
    timeout_rows: int = 1,
) -> None:
    if include_summary:
        write_csv(
            path / timeout_readiness.SUMMARY_FILE,
            ["target_family", "horizon", "timeout_rate"],
            [
                {
                    "target_family": "preferred_1_5atr_1atr_hit_first",
                    "horizon": "10",
                    "timeout_rate": "0.3333333333333333",
                }
            ],
        )
    if include_trade_logs:
        if include_timeout_columns:
            rows = [
                {
                    "symbol": "GBPUSD",
                    "target_family": "preferred_1_5atr_1atr_hit_first",
                    "horizon": "10",
                    "exit_reason": "timeout" if index < timeout_rows else "tp",
                    "bars_held": "10",
                    "net_R": "0.1",
                }
                for index in range(3)
            ]
            fields = ["symbol", "target_family", "horizon", "exit_reason", "bars_held", "net_R"]
        else:
            rows = [
                {"symbol": "GBPUSD", "target_family": "preferred_1_5atr_1atr_hit_first", "horizon": "10", "R": "0.1"}
                for _ in range(3)
            ]
            fields = ["symbol", "target_family", "horizon", "R"]
        write_csv(path / timeout_readiness.TRADE_BASE_FILE, fields, rows)
        write_csv(path / timeout_readiness.TRADE_STRESS_FILE, fields, rows)
    (path / timeout_readiness.REPORT_FILE).write_text("# Stress report\n", encoding="utf-8")


def make_args(
    tmp_path: Path,
    *,
    exact_exists: bool = True,
    single_exists: bool = True,
    exact_trade_logs: bool = True,
    single_trade_logs: bool = True,
    exact_timeout_columns: bool = True,
    single_timeout_columns: bool = True,
) -> object:
    exact_dir = tmp_path / "exact"
    single_dir = tmp_path / "single_filter_a"
    review_dir = tmp_path / "walkforward_drawdown_review"
    if exact_exists:
        write_stress_dir(
            exact_dir,
            include_trade_logs=exact_trade_logs,
            include_timeout_columns=exact_timeout_columns,
            timeout_rows=2,
        )
    if single_exists:
        write_stress_dir(
            single_dir,
            include_trade_logs=single_trade_logs,
            include_timeout_columns=single_timeout_columns,
            timeout_rows=1,
        )
    write_csv(review_dir / "fixed_candidate_walkforward_drawdown_artifact_review.csv", ["review_scope"], [{"review_scope": "x"}])
    return timeout_readiness.build_parser().parse_args(
        [
            "--run-id",
            "unit_timeout_readiness",
            "--exact-stress-dir",
            str(exact_dir),
            "--single-filter-a-stress-dir",
            str(single_dir),
            "--walkforward-drawdown-review-dir",
            str(review_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        timeout_readiness.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = timeout_readiness.build_outputs(make_args(tmp_path))

    assert outputs["readiness"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_trade_log_column_detection_works(tmp_path: Path) -> None:
    outputs = timeout_readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    coverage = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_timeout_column_coverage")

    assert "exit_reason" in coverage["exact_available_columns"]
    assert "bars_held" in coverage["exact_available_columns"]
    assert coverage["exact_timeout_columns_detected"] == "exit_reason"
    assert coverage["baseline_timeout_columns_detected"] == "exit_reason"
    assert coverage["exact_outcome_columns_detected"] == "exit_reason"
    assert coverage["baseline_outcome_columns_detected"] == "exit_reason"


def test_timeout_columns_present_creates_ready_status(tmp_path: Path) -> None:
    outputs = timeout_readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    counts = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_timeout_descriptive_counts")

    assert counts["readiness_status"] == "ready_for_timeout_artifact_review"
    assert counts["exact_trade_count"] == "3"
    assert counts["baseline_trade_count"] == "3"
    assert counts["exact_timeout_count"] == "2"
    assert counts["baseline_timeout_count"] == "1"
    assert counts["exact_timeout_rate"] == str(2 / 3)
    assert counts["baseline_timeout_rate"] == str(1 / 3)


def test_timeout_columns_missing_blocks_timeout_artifact_review(tmp_path: Path) -> None:
    outputs = timeout_readiness.build_outputs(
        make_args(tmp_path, exact_timeout_columns=False, single_timeout_columns=False)
    )
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    readiness = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_timeout_review_readiness")

    assert readiness["readiness_status"] == "blocked_requires_timeout_artifact"
    assert readiness["required_next_artifact"] == "trade_logs_with_timeout_flag_or_timeout_outcome_values"
    assert "timeout_columns_missing" in readiness["caveat"]
    assert any(row["warning_code"].endswith("timeout_columns_missing") for row in warnings)


def test_missing_exact_trade_log_creates_unavailable_status_and_warning(tmp_path: Path) -> None:
    outputs = timeout_readiness.build_outputs(make_args(tmp_path, exact_trade_logs=False))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    exact = next(row for row in rows if row["review_scope"] == "exact_rule_timeout_artifact_availability")

    assert exact["readiness_status"] == "unavailable_missing_artifact"
    assert exact["artifact_status"] == "missing"
    assert exact["warning_code"] == "exact_rule_timeout_artifact_availability_trade_logs_missing"
    assert exact["blocking_warning"] == "false"
    assert "exact_rule_timeout_artifact_availability_trade_logs_missing" in {
        row["warning_code"] for row in warnings
    }


def test_missing_required_stress_dir_creates_unavailable_status(tmp_path: Path) -> None:
    outputs = timeout_readiness.build_outputs(make_args(tmp_path, exact_exists=False))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    exact = next(row for row in rows if row["review_scope"] == "exact_rule_timeout_artifact_availability")

    assert exact["readiness_status"] == "unavailable_missing_artifact"
    assert exact["blocking_warning"] == "true"
    assert "exact_rule_timeout_artifact_availability_source_dir_missing" in {
        row["warning_code"] for row in warnings
    }


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = timeout_readiness.build_outputs(make_args(tmp_path, single_timeout_columns=False))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["review_row_count"] == len(rows)
    assert manifest["ready_for_timeout_artifact_review_count"] == sum(
        row["readiness_status"] == "ready_for_timeout_artifact_review" for row in rows
    )
    assert manifest["ready_with_caveat_count"] == sum(row["readiness_status"] == "ready_with_caveat" for row in rows)
    assert manifest["blocked_requires_timeout_artifact_count"] == sum(
        row["readiness_status"] == "blocked_requires_timeout_artifact" for row in rows
    )
    assert manifest["unavailable_missing_artifact_count"] == sum(
        row["readiness_status"] == "unavailable_missing_artifact" for row in rows
    )
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_timeout_policy_review_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_audit_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_artifact_only_and_no_decision_caveats(tmp_path: Path) -> None:
    outputs = timeout_readiness.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-only readiness review" in report
    assert "No candidate-quality conclusion" in report
    assert "trading decision" in report
    assert "No path outcomes were recomputed" in report
    assert "does not replace a true timeout policy review" in report


def test_no_child_or_heavy_commands_are_executed() -> None:
    source = Path(timeout_readiness.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "validate_regime_candidate_stress.py --" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
