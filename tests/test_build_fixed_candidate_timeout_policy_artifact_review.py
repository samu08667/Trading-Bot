from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_timeout_policy_artifact_review as timeout_review


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


def trade_rows(timeout_count: int, total: int, *, timeout_net: float, other_net: float, bars: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(total):
        is_timeout = index < timeout_count
        net_r = timeout_net if is_timeout else other_net
        rows.append(
            {
                "symbol": "GBPUSD",
                "target_family": "preferred_1_5atr_1atr_hit_first",
                "horizon": "10",
                "exit_reason": "TIMEOUT" if is_timeout else "TP",
                "bars_held": bars if is_timeout else 5,
                "R": net_r,
                "cost_R": "0.1",
                "net_R": net_r,
            }
        )
    return rows


def write_stress_dir(
    path: Path,
    *,
    base_rows: list[dict[str, object]] | None = None,
    stress_rows: list[dict[str, object]] | None = None,
    include_base: bool = True,
    include_stress: bool = True,
    include_exit_reason: bool = True,
) -> None:
    fields = ["symbol", "target_family", "horizon", "exit_reason", "bars_held", "R", "cost_R", "net_R"]
    if not include_exit_reason:
        fields = ["symbol", "target_family", "horizon", "bars_held", "R", "cost_R", "net_R"]
    write_csv(
        path / timeout_review.SUMMARY_FILE,
        ["target_family", "horizon"],
        [{"target_family": "preferred_1_5atr_1atr_hit_first", "horizon": "10"}],
    )
    if include_base:
        rows = base_rows or trade_rows(2, 3, timeout_net=0.25, other_net=1.0, bars=10)
        if not include_exit_reason:
            rows = [{key: value for key, value in row.items() if key != "exit_reason"} for row in rows]
        write_csv(path / timeout_review.TRADE_BASE_FILE, fields, rows)
    if include_stress:
        rows = stress_rows or trade_rows(1, 3, timeout_net=0.10, other_net=0.8, bars=10)
        if not include_exit_reason:
            rows = [{key: value for key, value in row.items() if key != "exit_reason"} for row in rows]
        write_csv(path / timeout_review.TRADE_STRESS_FILE, fields, rows)
    (path / timeout_review.REPORT_FILE).write_text("# Stress report\n", encoding="utf-8")


def write_readiness_dir(path: Path) -> None:
    write_csv(
        path / timeout_review.READINESS_FILE,
        ["review_scope", "readiness_status"],
        [{"review_scope": "exact_vs_single_filter_a_timeout_review_readiness", "readiness_status": "ready"}],
    )
    (path / timeout_review.READINESS_MANIFEST_FILE).write_text("{}", encoding="utf-8")


def make_args(
    tmp_path: Path,
    *,
    exact_base: bool = True,
    single_base: bool = True,
    exact_stress: bool = True,
    single_stress: bool = True,
    include_exit_reason: bool = True,
) -> object:
    exact_dir = tmp_path / "exact"
    single_dir = tmp_path / "single_filter_a"
    readiness_dir = tmp_path / "timeout_readiness"
    review_dir = tmp_path / "walkforward_drawdown_review"
    write_stress_dir(
        exact_dir,
        base_rows=trade_rows(2, 3, timeout_net=0.25, other_net=1.0, bars=10),
        stress_rows=trade_rows(1, 3, timeout_net=0.05, other_net=0.9, bars=10),
        include_base=exact_base,
        include_stress=exact_stress,
        include_exit_reason=include_exit_reason,
    )
    write_stress_dir(
        single_dir,
        base_rows=trade_rows(1, 4, timeout_net=-0.25, other_net=0.7, bars=9),
        stress_rows=trade_rows(2, 4, timeout_net=-0.35, other_net=0.6, bars=9),
        include_base=single_base,
        include_stress=single_stress,
        include_exit_reason=include_exit_reason,
    )
    write_readiness_dir(readiness_dir)
    write_csv(review_dir / "fixed_candidate_walkforward_drawdown_artifact_review.csv", ["review_scope"], [{"review_scope": "x"}])
    return timeout_review.build_parser().parse_args(
        [
            "--run-id",
            "unit_timeout_artifact_review",
            "--exact-stress-dir",
            str(exact_dir),
            "--single-filter-a-stress-dir",
            str(single_dir),
            "--timeout-readiness-dir",
            str(readiness_dir),
            "--walkforward-drawdown-review-dir",
            str(review_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        timeout_review.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = timeout_review.build_outputs(make_args(tmp_path))

    assert outputs["review"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_exit_reason_distribution_is_generated_from_trade_logs(tmp_path: Path) -> None:
    outputs = timeout_review.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["review"])
    timeout_row = next(
        row
        for row in rows
        if row["review_scope"] == "exact_rule_base_exit_reason_distribution"
        and row["exit_reason"] == "TIMEOUT"
    )

    assert timeout_row["trade_count"] == "3"
    assert timeout_row["exit_reason_count"] == "2"
    assert timeout_row["exit_reason_rate"] == str(2 / 3)
    assert timeout_row["mean_net_R"] == "0.25"
    assert timeout_row["sum_net_R"] == "0.5"
    assert timeout_row["mean_bars_held"] == "10.0"
    assert timeout_row["readiness_status"] == "descriptive_timeout_review_available"


def test_base_and_stress_trade_logs_are_both_handled(tmp_path: Path) -> None:
    outputs = timeout_review.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["review"])
    scopes = {row["review_scope"] for row in rows}

    assert "exact_rule_base_exit_reason_distribution" in scopes
    assert "exact_rule_stress_exit_reason_distribution" in scopes
    assert "single_filter_a_base_exit_reason_distribution" in scopes
    assert "single_filter_a_stress_exit_reason_distribution" in scopes
    assert any(row["cost_profile"] == "p75" for row in rows)
    assert any(row["cost_profile"] == "p90" for row in rows)


def test_timeout_comparison_rows_are_generated(tmp_path: Path) -> None:
    outputs = timeout_review.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["review"])
    base = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_base_timeout_comparison")
    stress = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_stress_timeout_comparison")

    assert base["row_type"] == "timeout_comparison"
    assert base["exact_timeout_rate"] == str(2 / 3)
    assert base["single_filter_a_timeout_rate"] == str(1 / 4)
    assert base["timeout_rate_delta"] == str((2 / 3) - (1 / 4))
    assert base["timeout_mean_net_R_delta"] == str(0.25 - (-0.25))
    assert base["timeout_mean_bars_held_delta"] == str(10.0 - 9.0)
    assert "exact_timeout_rate_higher_observed" in base["descriptive_observation"]
    assert stress["cost_profile"] == "p90"


def test_missing_exit_reason_blocks_timeout_artifact_review(tmp_path: Path) -> None:
    outputs = timeout_review.build_outputs(make_args(tmp_path, include_exit_reason=False))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    base = next(row for row in rows if row["review_scope"] == "exact_vs_single_filter_a_base_timeout_comparison")

    assert base["readiness_status"] == "blocked_requires_timeout_artifact"
    assert base["required_next_artifact"] == "trade_logs_with_exit_reason_for_both_sources"
    assert any(row["warning_code"].endswith("exit_reason_missing") for row in warnings)


def test_missing_optional_stress_log_creates_non_blocking_warning_and_caveat(tmp_path: Path) -> None:
    outputs = timeout_review.build_outputs(make_args(tmp_path, exact_stress=False))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    stress = next(row for row in rows if row["review_scope"] == "exact_rule_stress_exit_reason_distribution")

    assert stress["readiness_status"] == "descriptive_timeout_review_available_with_caveat"
    assert stress["blocking_warning"] == "false"
    assert {row["blocking_warning"] for row in warnings} == {"false"}
    assert "exact_rule_stress_exit_reason_distribution_trade_log_missing" in {
        row["warning_code"] for row in warnings
    }


def test_required_missing_trade_log_creates_unavailable_status(tmp_path: Path) -> None:
    outputs = timeout_review.build_outputs(make_args(tmp_path, exact_base=False))
    rows = read_csv(outputs["review"])
    exact = next(row for row in rows if row["review_scope"] == "exact_rule_base_exit_reason_distribution")

    assert exact["readiness_status"] == "unavailable_missing_artifact"
    assert exact["artifact_status"] == "missing"
    assert exact["required_next_artifact"] == "trade_log_with_exit_reason_and_timeout_rows"


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = timeout_review.build_outputs(make_args(tmp_path, single_stress=False))
    rows = read_csv(outputs["review"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["review_row_count"] == len(rows)
    assert manifest["descriptive_timeout_review_available_count"] == sum(
        row["readiness_status"] == "descriptive_timeout_review_available" for row in rows
    )
    assert manifest["descriptive_timeout_review_available_with_caveat_count"] == sum(
        row["readiness_status"] == "descriptive_timeout_review_available_with_caveat" for row in rows
    )
    assert manifest["blocked_requires_timeout_artifact_count"] == sum(
        row["readiness_status"] == "blocked_requires_timeout_artifact" for row in rows
    )
    assert manifest["unavailable_missing_artifact_count"] == sum(
        row["readiness_status"] == "unavailable_missing_artifact" for row in rows
    )
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["detected_outcome_columns"] == ["exit_reason"]
    assert "exit_reason" in manifest["detected_timeout_columns"]
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_timeout_policy_review_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_audit_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_artifact_only_and_no_decision_caveats(tmp_path: Path) -> None:
    outputs = timeout_review.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Artifact-only descriptive review" in report
    assert "No candidate-quality conclusion" in report
    assert "trading decision" in report
    assert "No path outcomes were recomputed" in report
    assert "does not replace a separate timeout policy review" in report


def test_no_path_recomputation_or_child_commands_are_present() -> None:
    source = Path(timeout_review.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "validate_regime_candidate_stress.py --" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
    assert "run_tp_sl_path_backtests.py" not in source
