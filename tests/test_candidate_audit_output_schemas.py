import importlib
from pathlib import Path

from tests.test_regime_candidate_review_package import (
    candidate_b_fields as review_candidate_b_fields,
    run_package as run_candidate_review_package,
    write_stress_package,
)
from tests.test_rule_candidate_gate_decision_report import run_gate
from tests.test_rule_candidate_gate_decision_report import read_csv as read_gate_csv
from tests.test_timeout_policy_sensitivity_review import read_csv as read_timeout_policy_csv
from tests.test_timeout_policy_sensitivity_review import run_review as run_timeout_policy_review


COMMON_WARNING_FIELDS = {
    "warning_code",
    "severity",
    "blocking",
    "message",
    "related_stage",
    "related_metric",
    "metric_value",
    "threshold",
}
COMMON_SUMMARY_FIELDS = {
    "final_classification",
    "decision_scope",
    "warnings_count",
    "blocking_warnings_count",
}
COMMON_NEXT_ACTION_FIELDS = {"action_type", "status", "message", "forbidden_actions"}
ALLOWED_SEVERITIES = {"info", "review", "severe", "blocking"}


WARNING_CONTRACTS = [
    ("scripts.build_regime_candidate_review_package", "WARNING_FIELDNAMES"),
    ("scripts.run_rule_based_regime_candidate_backtest", "WARNING_FIELDNAMES"),
    ("scripts.build_rule_based_regime_candidate_review", "WARNING_FIELDNAMES"),
    ("scripts.build_controlled_rule_research_expansion", "WARNING_FIELDNAMES"),
    ("scripts.build_timeout_fragility_audit", "WARNING_FIELDNAMES"),
    ("scripts.build_timeout_root_cause_review", "WARNING_FIELDNAMES"),
    ("scripts.build_timeout_sequence_drilldown_review", "WARNING_FIELDNAMES"),
    ("scripts.build_timeout_policy_sensitivity_review", "WARNING_FIELDNAMES"),
    ("scripts.build_rule_candidate_gate_decision_report", "WARNING_FIELDNAMES"),
]

SUMMARY_CONTRACTS = [
    ("scripts.build_regime_candidate_review_package", "SUMMARY_FIELDNAMES", "final_research_only_classification"),
    ("scripts.run_rule_based_regime_candidate_backtest", "SUMMARY_FIELDNAMES", "final_rule_replay_classification"),
    ("scripts.build_rule_based_regime_candidate_review", "SUMMARY_FIELDNAMES", "final_research_only_classification"),
    ("scripts.build_controlled_rule_research_expansion", "SUMMARY_FIELDNAMES", "final_research_only_classification"),
    ("scripts.build_timeout_fragility_audit", "SUMMARY_FIELDNAMES", "final_timeout_audit_classification"),
    ("scripts.build_timeout_root_cause_review", "SUMMARY_FIELDNAMES", "final_timeout_root_cause_classification"),
    ("scripts.build_timeout_sequence_drilldown_review", "SUMMARY_FIELDNAMES", "final_timeout_sequence_classification"),
    (
        "scripts.build_timeout_policy_sensitivity_review",
        "SUMMARY_FIELDNAMES",
        "final_timeout_policy_sensitivity_classification",
    ),
    ("scripts.build_rule_candidate_gate_decision_report", "SUMMARY_FIELDNAMES", "final_gate_decision"),
]

NEXT_ACTION_CONTRACTS = [
    ("scripts.build_timeout_root_cause_review", "PLAN_FIELDNAMES"),
    ("scripts.build_timeout_sequence_drilldown_review", "NEXT_ACTION_FIELDNAMES"),
    ("scripts.build_timeout_policy_sensitivity_review", "NEXT_ACTION_FIELDNAMES"),
    ("scripts.build_rule_candidate_gate_decision_report", "NEXT_ACTION_FIELDNAMES"),
]


def fieldnames(module_name: str, attr: str) -> set[str]:
    return set(getattr(importlib.import_module(module_name), attr))


def test_warning_csv_contracts_include_common_fields() -> None:
    for module_name, attr in WARNING_CONTRACTS:
        assert COMMON_WARNING_FIELDS.issubset(fieldnames(module_name, attr)), module_name


def test_summary_csv_contracts_include_common_fields_and_stage_labels() -> None:
    for module_name, attr, stage_label in SUMMARY_CONTRACTS:
        names = fieldnames(module_name, attr)
        assert COMMON_SUMMARY_FIELDS.issubset(names), module_name
        assert stage_label in names, module_name


def test_next_action_csv_contracts_include_common_fields() -> None:
    for module_name, attr in NEXT_ACTION_CONTRACTS:
        assert COMMON_NEXT_ACTION_FIELDS.issubset(fieldnames(module_name, attr)), module_name


def test_candidate_review_outputs_common_schema_and_candidate_b_metadata(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path, **review_candidate_b_fields())

    _outputs, summary, warnings = run_candidate_review_package(tmp_path, stress_dir)

    assert summary["symbol"] == "EURUSD"
    assert summary["direction"] == "long"
    assert summary["regime_value"] == "London"
    assert summary["decision_scope"] == "candidate_review"
    assert summary["final_classification"] == summary["final_research_only_classification"]
    assert "EURUSD" in summary["candidate_id"]
    assert "momentum_score" in summary["candidate_id"]
    assert summary["next_action"]
    assert warnings == []


def test_legacy_warning_outputs_are_extended_without_losing_legacy_columns(tmp_path: Path) -> None:
    stress_dir = write_stress_package(tmp_path, symbol="")

    _outputs, summary, warnings = run_candidate_review_package(tmp_path, stress_dir)

    assert summary["decision_scope"] == "candidate_review"
    assert summary["final_classification"] == summary["final_research_only_classification"]
    assert warnings
    warning = warnings[0]
    assert COMMON_WARNING_FIELDS.issubset(warning)
    assert {"check", "blocks_ready"}.issubset(warning)
    assert warning["severity"] in ALLOWED_SEVERITIES
    assert warning["warning_code"] == warning["check"]
    assert warning["blocking"] in {"True", "False"}


def test_timeout_policy_next_action_and_summary_are_consistent(tmp_path: Path) -> None:
    outputs, summary, warnings = run_timeout_policy_review(tmp_path, ["sl", "sl", "sl", "sl"])
    next_actions = read_timeout_policy_csv(outputs["next_actions"])

    assert summary["final_timeout_policy_sensitivity_classification"] == "TIMEOUT_POLICY_SENSITIVITY_REJECTED"
    assert summary["final_classification"] == summary["final_timeout_policy_sensitivity_classification"]
    assert summary["decision_scope"] == "timeout_policy_sensitivity"
    assert next_actions[0]["status"] == summary["final_classification"]
    assert "Alternative timeout policies are rejected" in next_actions[0]["message"]
    assert next_actions[0]["forbidden_actions"]
    assert all(row["severity"] in ALLOWED_SEVERITIES for row in warnings)


def test_gate_keeps_timeout_policy_rejection_scoped_to_alternative_policies(tmp_path: Path) -> None:
    outputs, summary, warnings = run_gate(tmp_path, include_timeout_policy=True)
    next_actions = read_gate_csv(outputs["next_actions"])

    assert summary["final_gate_decision"] == "GATE_ALLOW_LIMITED_BASELINE_COST_REVIEW_WITH_TIMEOUT_CAVEAT"
    assert summary["final_classification"] == summary["final_gate_decision"]
    assert summary["decision_scope"] == "gate_decision"
    assert summary["alternative_timeout_policies_rejected"] == "True"
    assert summary["limited_baseline_cost_review_allowed"] == "True"
    assert summary["h10_timeout_policy_required"] == "True"
    assert next_actions[0]["status"] == summary["final_classification"]
    assert "under the original validated h10 timeout rule" in next_actions[0]["message"]
    assert next_actions[0]["forbidden_actions"]
    assert all(row["blocking"] == "False" for row in warnings)
