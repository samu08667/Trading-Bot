import argparse
import csv
from pathlib import Path

import pytest

from scripts.build_rule_candidate_gate_decision_report import (
    GATE_ALLOW_LIMITED_LABEL,
    GATE_REJECT_LABEL,
    GATE_RETAIN_LABEL,
    build_rule_candidate_gate_decision_report,
    parse_args,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def candidate_fields() -> dict[str, object]:
    return {
        "symbol": "GBPUSD",
        "direction": "short",
        "timeframe": "M15",
        "horizon": "h10",
        "target_family": "preferred_1_5atr_1atr_hit_first",
        "regime_column": "session",
        "regime_value": "Off_hours",
        "feature_condition": (
            "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
            "numeric_tercile:tick_volume_percentile_100:mid_tercile"
        ),
        "tp_atr": "1.5",
        "sl_atr": "1.0",
        "same_bar_policy": "stop_first",
        "candidate_scope": "exact_feature_combination",
        "stress_spread_policy": "max_row_or_fallback",
    }


def stage_dirs(tmp_path: Path) -> dict[str, Path]:
    return {
        "candidate_review": tmp_path / "candidate_review" / "unit_gate",
        "rule_replay": tmp_path / "rule_replay" / "unit_gate",
        "rule_review": tmp_path / "rule_review" / "unit_gate",
        "controlled": tmp_path / "controlled" / "unit_gate",
        "timeout_audit": tmp_path / "timeout_audit" / "unit_gate",
        "timeout_root": tmp_path / "timeout_root" / "unit_gate",
        "timeout_sequence": tmp_path / "timeout_sequence" / "unit_gate",
        "timeout_policy": tmp_path / "timeout_policy" / "unit_gate",
    }


def base_summaries() -> dict[str, dict[str, object]]:
    fields = candidate_fields()
    stress = {
        "stress_mean_R": "0.42",
        "stress_profit_factor_R": "2.6",
        "stress_cumulative_R": "100.0",
        "stress_max_drawdown_R": "8.0",
    }
    return {
        "candidate_review": {
            "final_research_only_classification": "READY_FOR_RULE_BASED_RESEARCH_BACKTEST_REVIEW",
            "ready_for_rule_based_research_backtest_review": "True",
            "warnings_count": "0",
            "blocking_warnings_count": "0",
            **fields,
            **stress,
        },
        "rule_replay": {
            "final_rule_replay_classification": "RULE_REPLAY_MATCHED_STRESS_VALIDATION",
            "generated_logs_match_stress_validation": "True",
            "warnings_count": "0",
            "blocking_warnings_count": "0",
            **fields,
            **stress,
        },
        "rule_review": {
            "final_research_only_classification": "READY_FOR_CONTROLLED_RULE_RESEARCH_BACKTEST_EXPANSION",
            "ready_for_controlled_rule_research_backtest_expansion": "True",
            "warnings_count": "0",
            "blocking_warnings_count": "0",
            **fields,
            **stress,
        },
        "controlled": {
            "final_research_only_classification": "CONTROLLED_EXPANSION_RETAINED_FOR_TIMEOUT_REVIEW",
            "ready_for_baseline_and_cost_sensitivity_review": "False",
            "warnings_count": "0",
            "blocking_warnings_count": "0",
            "timeout_cumulative_R": "-1.0",
            "timeout_cumulative_R_pct_of_stress_cumulative_R": "-1.0",
            **fields,
            **stress,
        },
        "timeout_audit": {
            "final_timeout_audit_classification": "TIMEOUT_AUDIT_RETAINED_FOR_REVIEW",
            "warnings_count": "0",
            "blocking_warnings_count": "0",
            "timeout_cumulative_R": "-1.0",
            "timeout_cumulative_R_pct_of_stress_cumulative_R": "-1.0",
            "timeout_loss_ratio_of_stress_cumulative_R": "0.01",
            **fields,
            **stress,
        },
        "timeout_root": {
            "final_timeout_root_cause_classification": "TIMEOUT_ROOT_CAUSE_RETAINED_FOR_REVIEW",
            "warnings_count": "0",
            "blocking_warnings_count": "0",
            **fields,
            **stress,
        },
        "timeout_sequence": {
            "final_timeout_sequence_classification": "TIMEOUT_SEQUENCE_RETAINED_FOR_REVIEW",
            "warnings_count": "0",
            "blocking_warnings_count": "0",
            "sequence_cumulative_R": "-4.0",
            "sequence_max_drawdown_R": "5.0",
            "sequence_share_of_total_timeout_loss": "80.0",
            "sequence_share_of_total_stress_cumulative_R": "0.04",
            **fields,
            **stress,
        },
    }


def timeout_policy_summary() -> dict[str, object]:
    return {
        **candidate_fields(),
        "final_timeout_policy_sensitivity_classification": "TIMEOUT_POLICY_SENSITIVITY_REJECTED",
        "warnings_count": "1",
        "blocking_warnings_count": "1",
        "stress_cumulative_R": "100.0",
        "stress_mean_R": "0.42",
        "stress_profit_factor_R": "2.6",
        "current_h10_timeout_cumulative_R": "100.0",
        "current_h10_timeout_mean_R": "0.42",
        "current_h10_timeout_profit_factor_R": "2.6",
        "h20_timeout_subset_cumulative_R": "-12.0",
        "h40_timeout_subset_cumulative_R": "-14.0",
        "h80_timeout_subset_cumulative_R": "-13.0",
        "h20_delta_vs_original_h10_timeout_R": "-11.0",
        "h40_delta_vs_original_h10_timeout_R": "-13.0",
        "h80_delta_vs_original_h10_timeout_R": "-12.0",
    }


def write_gate_inputs(
    tmp_path: Path,
    *,
    summary_overrides: dict[str, dict[str, object]] | None = None,
    warning_rows: dict[str, list[dict[str, object]]] | None = None,
    comparison_match: bool = True,
    include_timeout_audit: bool = True,
    include_timeout_root: bool = True,
    include_timeout_sequence: bool = True,
    include_timeout_policy: bool = False,
) -> dict[str, Path]:
    dirs = stage_dirs(tmp_path)
    summaries = base_summaries()
    summaries["timeout_policy"] = timeout_policy_summary()
    for stage, overrides in (summary_overrides or {}).items():
        summaries[stage].update(overrides)
    warnings = warning_rows or {}

    write_csv(dirs["candidate_review"] / "candidate_review_summary.csv", [summaries["candidate_review"]])
    write_csv(
        dirs["candidate_review"] / "candidate_review_warnings.csv",
        warnings.get("candidate_review", []),
        ["severity", "check", "blocks_ready", "message"],
    )
    (dirs["candidate_review"] / "candidate_review_report.md").write_text("candidate review\n", encoding="utf-8")

    write_csv(dirs["rule_replay"] / "rule_based_backtest_summary.csv", [summaries["rule_replay"]])
    write_csv(
        dirs["rule_replay"] / "rule_based_comparison_to_stress_validation.csv",
        [
            {"comparison_scope": "base", "trade_logs_match_within_tolerance": str(comparison_match)},
            {"comparison_scope": "stress", "trade_logs_match_within_tolerance": str(comparison_match)},
        ],
    )
    write_csv(
        dirs["rule_replay"] / "rule_based_warnings.csv",
        warnings.get("rule_replay", []),
        ["severity", "check", "blocks_match", "message"],
    )
    (dirs["rule_replay"] / "rule_based_backtest_report.md").write_text("rule replay\n", encoding="utf-8")

    write_csv(dirs["rule_review"] / "rule_based_review_summary.csv", [summaries["rule_review"]])
    write_csv(
        dirs["rule_review"] / "rule_based_review_warnings.csv",
        warnings.get("rule_review", []),
        ["severity", "check", "blocks_ready", "message"],
    )
    (dirs["rule_review"] / "rule_based_review_report.md").write_text("rule review\n", encoding="utf-8")

    write_csv(dirs["controlled"] / "controlled_rule_expansion_summary.csv", [summaries["controlled"]])
    write_csv(
        dirs["controlled"] / "controlled_rule_expansion_warnings.csv",
        warnings.get("controlled", []),
        ["warning_code", "severity", "blocking", "message", "related_metric", "metric_value", "threshold"],
    )
    (dirs["controlled"] / "controlled_rule_expansion_report.md").write_text("controlled\n", encoding="utf-8")

    if include_timeout_audit:
        write_csv(dirs["timeout_audit"] / "timeout_fragility_audit_summary.csv", [summaries["timeout_audit"]])
        write_csv(
            dirs["timeout_audit"] / "timeout_fragility_audit_warnings.csv",
            warnings.get("timeout_audit", []),
            ["warning_code", "severity", "blocking", "message", "related_metric", "metric_value", "threshold"],
        )
        (dirs["timeout_audit"] / "timeout_fragility_audit_report.md").write_text(
            "timeout audit\n",
            encoding="utf-8",
        )

    if include_timeout_root:
        write_csv(dirs["timeout_root"] / "timeout_root_cause_summary.csv", [summaries["timeout_root"]])
        write_csv(
            dirs["timeout_root"] / "timeout_root_cause_warnings.csv",
            warnings.get("timeout_root", []),
            ["warning_code", "severity", "blocking", "message", "related_metric", "metric_value", "threshold"],
        )
        (dirs["timeout_root"] / "timeout_root_cause_report.md").write_text("timeout root\n", encoding="utf-8")

    if include_timeout_sequence:
        write_csv(dirs["timeout_sequence"] / "timeout_sequence_drilldown_summary.csv", [summaries["timeout_sequence"]])
        write_csv(
            dirs["timeout_sequence"] / "timeout_sequence_drilldown_warnings.csv",
            warnings.get("timeout_sequence", []),
            ["warning_code", "severity", "blocking", "message", "related_metric", "metric_value", "threshold"],
        )
        (dirs["timeout_sequence"] / "timeout_sequence_drilldown_report.md").write_text(
            "timeout sequence\n",
            encoding="utf-8",
        )
    if include_timeout_policy:
        write_csv(dirs["timeout_policy"] / "timeout_policy_sensitivity_summary.csv", [summaries["timeout_policy"]])
        write_csv(
            dirs["timeout_policy"] / "timeout_policy_sensitivity_warnings.csv",
            warnings.get(
                "timeout_policy",
                [
                    {
                        "warning_code": "timeout_policy_blocking_failure",
                        "severity": "blocking",
                        "blocking": "True",
                        "message": "alternative timeout policies rejected",
                        "related_metric": "extended_horizon_timeout_policy_rejected",
                        "metric_value": "True",
                        "threshold": "False",
                    }
                ],
            ),
            ["warning_code", "severity", "blocking", "message", "related_metric", "metric_value", "threshold"],
        )
        (dirs["timeout_policy"] / "timeout_policy_sensitivity_report.md").write_text(
            "timeout policy\n",
            encoding="utf-8",
        )
    return dirs


def build_args(
    tmp_path: Path,
    dirs: dict[str, Path],
    *,
    overwrite: bool = True,
    include_timeout_audit: bool = True,
    include_timeout_root: bool = True,
    include_timeout_sequence: bool = True,
    include_timeout_policy: bool = False,
) -> argparse.Namespace:
    argv = [
        "--candidate-review-dir",
        str(dirs["candidate_review"]),
        "--rule-replay-dir",
        str(dirs["rule_replay"]),
        "--rule-review-dir",
        str(dirs["rule_review"]),
        "--controlled-expansion-dir",
        str(dirs["controlled"]),
        "--output-root",
        str(tmp_path / "gate_outputs"),
        "--run-id",
        "unit_gate",
    ]
    if include_timeout_audit:
        argv.extend(["--timeout-audit-dir", str(dirs["timeout_audit"])])
    if include_timeout_root:
        argv.extend(["--timeout-root-cause-dir", str(dirs["timeout_root"])])
    if include_timeout_sequence:
        argv.extend(["--timeout-sequence-dir", str(dirs["timeout_sequence"])])
    if include_timeout_policy:
        argv.extend(["--timeout-policy-sensitivity-dir", str(dirs["timeout_policy"])])
    if overwrite:
        argv.append("--overwrite")
    return parse_args(argv)


def run_gate(
    tmp_path: Path,
    *,
    summary_overrides: dict[str, dict[str, object]] | None = None,
    warning_rows: dict[str, list[dict[str, object]]] | None = None,
    comparison_match: bool = True,
    overwrite: bool = True,
    include_timeout_audit: bool = True,
    include_timeout_root: bool = True,
    include_timeout_sequence: bool = True,
    include_timeout_policy: bool = False,
) -> tuple[dict[str, Path], dict[str, str], list[dict[str, str]]]:
    dirs = write_gate_inputs(
        tmp_path,
        summary_overrides=summary_overrides,
        warning_rows=warning_rows,
        comparison_match=comparison_match,
        include_timeout_audit=include_timeout_audit,
        include_timeout_root=include_timeout_root,
        include_timeout_sequence=include_timeout_sequence,
        include_timeout_policy=include_timeout_policy,
    )
    outputs = build_rule_candidate_gate_decision_report(
        build_args(
            tmp_path,
            dirs,
            overwrite=overwrite,
            include_timeout_audit=include_timeout_audit,
            include_timeout_root=include_timeout_root,
            include_timeout_sequence=include_timeout_sequence,
            include_timeout_policy=include_timeout_policy,
        )
    )
    return outputs, read_csv(outputs["summary"])[0], read_csv(outputs["warnings"])


def test_happy_limited_review_case(tmp_path: Path) -> None:
    outputs, summary, warnings = run_gate(tmp_path)
    chain_by_stage = {row["stage"]: row for row in read_csv(outputs["chain"])}

    assert summary["final_gate_decision"] == GATE_ALLOW_LIMITED_LABEL
    assert summary["limited_baseline_cost_review_allowed"] == "True"
    assert summary["timeout_issue_unresolved"] == "True"
    assert summary["timeout_audit_status"] == "ready"
    assert summary["timeout_root_cause_status"] == "ready"
    assert summary["timeout_sequence_status"] == "ready"
    assert summary["timeout_policy_sensitivity_status"] == "not_run"
    assert summary["symbol"] == "GBPUSD"
    assert any(row["warning_code"] == "baseline_cost_review_allowed_with_caveat" for row in warnings)
    assert any(row["warning_code"] == "timeout_policy_sensitivity_not_run" for row in warnings)
    assert chain_by_stage["timeout_policy_sensitivity"]["stage_status"] == "not_run"
    assert read_csv(outputs["chain"])
    assert read_csv(outputs["next_actions"])


def test_timeout_policy_rejected_alternatives_keeps_limited_review_allowed(tmp_path: Path) -> None:
    outputs, summary, warnings = run_gate(tmp_path, include_timeout_policy=True)
    chain_by_stage = {row["stage"]: row for row in read_csv(outputs["chain"])}
    report = outputs["report"].read_text(encoding="utf-8")

    assert summary["final_gate_decision"] == GATE_ALLOW_LIMITED_LABEL
    assert summary["limited_baseline_cost_review_allowed"] == "True"
    assert summary["h10_timeout_policy_required"] == "True"
    assert summary["alternative_timeout_policies_rejected"] == "True"
    assert summary["extended_horizon_timeout_policy_rejected"] == "True"
    assert summary["timeout_policy_sensitivity_status"] == "alternative_policy_rejected"
    assert chain_by_stage["timeout_policy_sensitivity"]["stage_status"] == "alternative_policy_rejected"
    assert summary["timeout_policy_blocking_warnings_count"] == "1"
    assert summary["prior_blocking_warnings_count"] == "0"
    assert summary["current_h10_policy_cumulative_R"] == summary["current_h10_timeout_cumulative_R"]
    assert summary["current_h10_policy_mean_R"] == summary["current_h10_timeout_mean_R"]
    assert summary["current_h10_policy_profit_factor_R"] == summary["current_h10_timeout_profit_factor_R"]
    assert summary["current_h10_policy_cumulative_R"] == "100.0"
    assert summary["current_h10_policy_mean_R"] == "0.42"
    assert summary["current_h10_policy_profit_factor_R"] == "2.6"
    assert summary["timeout_cumulative_R"] == "-1.0"
    assert summary["timeout_cumulative_R_pct_of_stress_cumulative_R"] == "-1.0"
    assert summary["timeout_loss_ratio_of_stress_cumulative_R"] == "0.01"
    assert "current_h10_policy_*" in report
    assert "full validated h10 policy" in report
    assert "timeout_cumulative_R" in report
    assert "refers only to the timeout bucket" in report
    assert all(row["blocking"] == "False" for row in warnings)
    assert any(row["warning_code"] == "alternative_timeout_policies_rejected" for row in warnings)
    chain = read_csv(outputs["chain"])
    assert any(row["stage"] == "timeout_policy_sensitivity" for row in chain)


def test_summary_preserves_old_h10_timeout_fields_and_adds_policy_aliases(tmp_path: Path) -> None:
    outputs, summary, _warnings = run_gate(tmp_path, include_timeout_policy=True)
    fieldnames = list(csv.DictReader(outputs["summary"].open("r", encoding="utf-8")).fieldnames or [])

    old_fields = [
        "current_h10_timeout_cumulative_R",
        "current_h10_timeout_mean_R",
        "current_h10_timeout_profit_factor_R",
    ]
    alias_fields = [
        "current_h10_policy_cumulative_R",
        "current_h10_policy_mean_R",
        "current_h10_policy_profit_factor_R",
    ]

    for field in old_fields + alias_fields:
        assert field in fieldnames
    for old_field, alias_field in zip(old_fields, alias_fields):
        assert summary[alias_field] == summary[old_field]


def test_timeout_policy_rejected_with_broken_h10_metrics_does_not_allow_review(tmp_path: Path) -> None:
    outputs, summary, warnings = run_gate(
        tmp_path,
        include_timeout_policy=True,
        summary_overrides={
            "timeout_policy": {
                "stress_cumulative_R": "-2.0",
                "stress_mean_R": "-0.05",
                "stress_profit_factor_R": "0.8",
                "current_h10_timeout_cumulative_R": "-2.0",
                "current_h10_timeout_mean_R": "-0.05",
                "current_h10_timeout_profit_factor_R": "0.8",
            }
        },
    )

    assert summary["final_gate_decision"] == GATE_REJECT_LABEL
    assert summary["limited_baseline_cost_review_allowed"] == "False"
    assert summary["alternative_timeout_policies_rejected"] == "False"
    assert summary["timeout_policy_sensitivity_status"] == "failed"
    assert {row["stage"]: row for row in read_csv(outputs["chain"])}["timeout_policy_sensitivity"][
        "stage_status"
    ] == "failed"
    assert any(row["warning_code"] == "gate_rejected" for row in warnings)


def test_timeout_policy_blocking_warning_is_scoped_to_alternative_policies(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_gate(tmp_path, include_timeout_policy=True)

    assert summary["final_gate_decision"] == GATE_ALLOW_LIMITED_LABEL
    assert summary["timeout_policy_alternative_blocking_warnings_count"] == "1"
    assert summary["blocking_warnings_count"] == "0"
    assert any(row["warning_code"] == "alternative_timeout_policy_blocking_warning" for row in warnings)
    assert all(row["blocking"] == "False" for row in warnings)


def test_gate_allows_skipped_timeout_chain_when_controlled_expansion_does_not_require_it(tmp_path: Path) -> None:
    outputs, summary, warnings = run_gate(
        tmp_path,
        summary_overrides={
            "controlled": {
                "final_research_only_classification": "READY_FOR_BASELINE_AND_COST_SENSITIVITY_REVIEW",
                "ready_for_baseline_and_cost_sensitivity_review": "True",
            }
        },
        include_timeout_audit=False,
        include_timeout_root=False,
        include_timeout_sequence=False,
    )
    chain_by_stage = {row["stage"]: row for row in read_csv(outputs["chain"])}

    assert summary["final_gate_decision"] == GATE_ALLOW_LIMITED_LABEL
    assert summary["limited_baseline_cost_review_allowed"] == "True"
    assert summary["missing_required_timeout_stage_count"] == "0"
    assert summary["blocking_warnings_count"] == "0"
    assert summary["timeout_audit_status"] == "skipped_not_required"
    assert summary["timeout_root_cause_status"] == "skipped_not_required"
    assert summary["timeout_sequence_status"] == "skipped_not_required"
    assert summary["timeout_policy_sensitivity_status"] == "skipped_not_required"
    assert chain_by_stage["timeout_audit"]["stage_status"] == "skipped_not_required"
    assert chain_by_stage["timeout_root_cause"]["stage_status"] == "skipped_not_required"
    assert chain_by_stage["timeout_sequence"]["stage_status"] == "skipped_not_required"
    assert chain_by_stage["timeout_policy_sensitivity"]["stage_status"] == "skipped_not_required"
    assert any(row["warning_code"] == "optional_timeout_stage_skipped" for row in warnings)
    assert any(row["warning_code"] == "timeout_policy_sensitivity_optional" for row in warnings)
    assert all(row["blocking"] == "False" for row in warnings)


def test_gate_blocks_when_required_timeout_audit_is_missing(tmp_path: Path) -> None:
    outputs, summary, warnings = run_gate(
        tmp_path,
        include_timeout_audit=False,
        include_timeout_root=False,
        include_timeout_sequence=False,
    )
    chain_by_stage = {row["stage"]: row for row in read_csv(outputs["chain"])}

    assert summary["final_gate_decision"] == GATE_REJECT_LABEL
    assert summary["limited_baseline_cost_review_allowed"] == "False"
    assert summary["missing_required_timeout_stage_count"] == "1"
    assert summary["timeout_audit_status"] == "missing_required"
    assert chain_by_stage["timeout_audit"]["stage_status"] == "missing_required"
    assert any(row["warning_code"] == "missing_required_timeout_stage" for row in warnings)
    assert any(row["blocking"] == "True" for row in warnings)


def test_report_next_action_requires_original_h10_timeout_policy(tmp_path: Path) -> None:
    outputs, summary, _warnings = run_gate(tmp_path, include_timeout_policy=True)
    report = outputs["report"].read_text(encoding="utf-8")
    next_actions = read_csv(outputs["next_actions"])

    assert summary["final_gate_decision"] == GATE_ALLOW_LIMITED_LABEL
    assert "original validated h10 timeout rule" in report
    assert "under the original validated h10 timeout rule" in next_actions[0]["message"]


def test_prior_blocking_warning_rejects(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_gate(
        tmp_path,
        summary_overrides={"candidate_review": {"blocking_warnings_count": "1"}},
        warning_rows={
            "candidate_review": [
                {"severity": "error", "check": "unit_blocker", "blocks_ready": "True", "message": "blocked"}
            ]
        },
    )

    assert summary["final_gate_decision"] == GATE_REJECT_LABEL
    assert any(row["warning_code"] == "prior_blocking_warning" for row in warnings)


def test_rule_replay_mismatch_rejects(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_gate(
        tmp_path,
        summary_overrides={
            "rule_replay": {
                "final_rule_replay_classification": "RULE_REPLAY_MISMATCH_REJECTED",
                "generated_logs_match_stress_validation": "False",
            }
        },
        comparison_match=False,
    )

    assert summary["final_gate_decision"] == GATE_REJECT_LABEL
    assert any(row["warning_code"] == "gate_rejected" for row in warnings)


def test_timeout_sequence_failed_rejects(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_gate(
        tmp_path,
        summary_overrides={
            "timeout_sequence": {"final_timeout_sequence_classification": "TIMEOUT_SEQUENCE_FAILED"}
        },
    )

    assert summary["final_gate_decision"] == GATE_REJECT_LABEL
    assert any(row["warning_code"] == "gate_rejected" for row in warnings)


def test_timeout_sequence_too_severe_is_retained_before_reject_threshold(tmp_path: Path) -> None:
    _outputs, summary, warnings = run_gate(
        tmp_path,
        summary_overrides={
            "timeout_sequence": {"sequence_share_of_total_stress_cumulative_R": "0.07"}
        },
    )

    assert summary["final_gate_decision"] == GATE_RETAIN_LABEL
    assert any(row["warning_code"] == "sequence_review_required" for row in warnings)


def test_missing_input_file_errors(tmp_path: Path) -> None:
    dirs = write_gate_inputs(tmp_path)
    (dirs["timeout_sequence"] / "timeout_sequence_drilldown_summary.csv").unlink()

    with pytest.raises(FileNotFoundError, match="timeout_sequence_drilldown_summary"):
        build_rule_candidate_gate_decision_report(build_args(tmp_path, dirs))


def test_missing_timeout_policy_input_file_errors_when_dir_provided(tmp_path: Path) -> None:
    dirs = write_gate_inputs(tmp_path, include_timeout_policy=True)
    (dirs["timeout_policy"] / "timeout_policy_sensitivity_summary.csv").unlink()

    with pytest.raises(FileNotFoundError, match="timeout_policy_sensitivity_summary"):
        build_rule_candidate_gate_decision_report(
            build_args(tmp_path, dirs, include_timeout_policy=True)
        )


def test_overwrite_protection(tmp_path: Path) -> None:
    dirs = write_gate_inputs(tmp_path, include_timeout_policy=True)
    build_rule_candidate_gate_decision_report(
        build_args(tmp_path, dirs, overwrite=True, include_timeout_policy=True)
    )

    with pytest.raises(FileExistsError, match="--overwrite"):
        build_rule_candidate_gate_decision_report(
            build_args(tmp_path, dirs, overwrite=False, include_timeout_policy=True)
        )


def test_report_forbidden_next_actions_are_always_present(tmp_path: Path) -> None:
    outputs, _summary, _warnings = run_gate(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    for phrase in [
        "live trading",
        "trading signal",
        "broker execution",
        "position sizing",
        "TP/SL optimization",
        "new feature search",
        "new filters",
        "live readiness",
    ]:
        assert phrase in report
