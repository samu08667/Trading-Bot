from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_manual_approval_kill_switch_plan as approval_plan


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def canonical_registry(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
    }
    data.update(overrides)
    return data


def execution_policy(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "policy_id": "policy",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "account_currency": "EUR",
        "intended_demo_equity": 1000.0,
        "risk_percent_max": 0.5,
        "risk_amount_max": 5.0,
        "max_margin_usage_warning_ratio": 0.5,
        "max_margin_usage_warning_amount": 500.0,
        "max_margin_usage_ratio": 0.7,
        "max_margin_usage_amount": 700.0,
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
        "safety_boundaries": {
            "real_money_allowed": False,
            "broker_connection_allowed_for_this_policy_file": False,
            "order_execution_allowed": False,
            "order_request_construction_allowed": False,
            "order_check_allowed": False,
            "order_calc_allowed": False,
            "manual_approval_required_before_any_future_demo_order": True,
        },
    }
    data.update(overrides)
    return data


def duplicate_protection_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "run_id": "source_duplicate_protection",
        "plan_status": "duplicate_protection_plan_fixture_only",
        "plan_actionable": False,
        "source_nature": "synthetic_fixture",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "max_open_positions": 1,
        "no_mt5_connection_performed": True,
        "no_broker_api_query_performed": True,
        "no_db_query_performed": True,
        "no_db_mutation_performed": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    data.update(overrides)
    return data


def source_csv_row(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {"run_id": "source_duplicate_protection", "name": "row", "caveat": "source"}
    data.update(overrides)
    return data


def write_source_artifacts(
    root: Path,
    *,
    manifest_data: dict[str, object] | None = None,
    missing_manifest: bool = False,
    missing_signal_identity: bool = False,
    missing_state_gates: bool = False,
    missing_idempotency: bool = False,
    missing_max_open: bool = False,
    missing_stale_policy: bool = False,
    missing_future_checks: bool = False,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if not missing_manifest:
        write_json(root / approval_plan.SOURCE_MANIFEST, manifest_data or duplicate_protection_manifest())
    if not missing_signal_identity:
        write_csv(root / approval_plan.SOURCE_SIGNAL_IDENTITY, [source_csv_row(signal_identity_field="candidate_id")], ["run_id", "name", "caveat", "signal_identity_field"])
    if not missing_state_gates:
        write_csv(root / approval_plan.SOURCE_STATE_GATES, [source_csv_row(state_gate="duplicate_signal_id")], ["run_id", "name", "caveat", "state_gate"])
    if not missing_idempotency:
        write_csv(root / approval_plan.SOURCE_IDEMPOTENCY, [source_csv_row(component_name="idempotency_key")], ["run_id", "name", "caveat", "component_name"])
    if not missing_max_open:
        write_csv(root / approval_plan.SOURCE_MAX_OPEN_POSITIONS, [source_csv_row(max_open_area="future_local_open_count")], ["run_id", "name", "caveat", "max_open_area"])
    if not missing_stale_policy:
        write_csv(root / approval_plan.SOURCE_STALE_SIGNAL_POLICY, [source_csv_row(stale_policy_area="horizon_age_gate")], ["run_id", "name", "caveat", "stale_policy_area"])
    if not missing_future_checks:
        write_csv(root / approval_plan.SOURCE_FUTURE_PRE_EXECUTION_CHECKS, [source_csv_row(future_check_name="manual_approval_gate_after_duplicate_checks")], ["run_id", "name", "caveat", "future_check_name"])
    (root / approval_plan.SOURCE_REPORT).write_text("source report\n", encoding="utf-8")
    write_csv(root / approval_plan.SOURCE_MAIN, [], approval_plan.MAIN_FIELDNAMES)
    write_csv(root / approval_plan.SOURCE_WARNINGS, [], approval_plan.WARNING_FIELDNAMES)
    return root


def make_args(
    tmp_path: Path,
    *,
    registry_data: dict[str, object] | None = None,
    policy_data: dict[str, object] | None = None,
    source_dir: Path | None = None,
) -> object:
    registry_path = write_json(tmp_path / "registry.json", registry_data or canonical_registry())
    policy_path = write_json(tmp_path / "policy.json", policy_data or execution_policy())
    if source_dir is None:
        source_dir = write_source_artifacts(tmp_path / "source")
    argv = [
        "--run-id",
        "unit_manual_approval_kill_switch_plan",
        "--duplicate-protection-plan-dir",
        str(source_dir),
        "--canonical-registry",
        str(registry_path),
        "--demo-execution-policy",
        str(policy_path),
        "--future-state-json",
        str(tmp_path / "state" / "future_state.json"),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    return approval_plan.build_parser().parse_args(argv)


def build_valid_fixture_plan(tmp_path: Path) -> dict[str, Path]:
    return approval_plan.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        approval_plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written_on_happy_path(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_source_produces_fixture_only(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "manual_approval_kill_switch_plan_fixture_only"
    assert manifest["plan_actionable"] is False
    assert manifest["recommended_next_step"] == "continue_no_order_monitoring_or_build_future_broker_state_reconciliation_check_plan"


def test_live_data_source_produces_available_no_order(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=duplicate_protection_manifest(
            plan_status="duplicate_protection_plan_available_no_order",
            source_nature="live_data_shadow_signal",
        ),
    )
    outputs = approval_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "manual_approval_kill_switch_plan_available_no_order"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_demo_future_broker_state_reconciliation_check_plan"


def test_missing_duplicate_protection_manifest_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_manifest=True)
    outputs = approval_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_duplicate_protection_manifest"


def test_missing_signal_identity_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_signal_identity=True)
    outputs = approval_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_signal_identity"


def test_missing_state_gates_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_state_gates=True)
    outputs = approval_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_state_gates"


def test_missing_idempotency_checks_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_idempotency=True)
    outputs = approval_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_idempotency_checks"


def test_missing_max_open_positions_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_max_open=True)
    outputs = approval_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_max_open_positions"


def test_missing_stale_signal_policy_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_stale_policy=True)
    outputs = approval_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_stale_signal_policy"


def test_missing_future_pre_execution_checks_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_future_checks=True)
    outputs = approval_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_future_pre_execution_checks"


def test_unacceptable_duplicate_protection_status_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=duplicate_protection_manifest(plan_status="blocked_unreadable_input"),
    )
    outputs = approval_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_unacceptable_duplicate_protection_status"


def test_unsafe_duplicate_protection_boundary_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=duplicate_protection_manifest(no_order_request_constructed=False),
    )
    outputs = approval_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_unsafe_duplicate_protection_boundary"


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    outputs = approval_plan.build_outputs(make_args(tmp_path, registry_data=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_noncanonical_candidate"


def test_noncanonical_demo_execution_policy_blocks(tmp_path: Path) -> None:
    unsafe = execution_policy(max_margin_usage_ratio=0.5)
    outputs = approval_plan.build_outputs(make_args(tmp_path, policy_data=unsafe))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_noncanonical_demo_execution_policy"


def test_policy_without_manual_approval_required_blocks(tmp_path: Path) -> None:
    policy = execution_policy()
    safety = dict(policy["safety_boundaries"])  # type: ignore[index]
    safety["manual_approval_required_before_any_future_demo_order"] = False
    policy["safety_boundaries"] = safety
    outputs = approval_plan.build_outputs(make_args(tmp_path, policy_data=policy))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_manual_approval_not_required_by_policy"


def test_manual_approval_statuses_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["manual_approval_gate"])
    statuses = {row["future_manual_approval_status"] for row in rows}

    assert set(approval_plan.MANUAL_APPROVAL_STATUSES) <= statuses
    assert all(row["approval_executes_order"] == "false" for row in rows)


def test_operator_review_checklist_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["operator_review_checklist"])
    items = {row["checklist_item"] for row in rows}

    assert {
        "confirm_demo_account_only",
        "confirm_no_real_money_mode",
        "confirm_spread_within_15_broker_points",
        "confirm_live_data_no_order_signal",
        "confirm_duplicate_protection_passed",
        "confirm_state_reconciliation_passed",
        "confirm_no_automated_approval",
    } <= items


def test_kill_switch_hard_block_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["kill_switch_rules"])
    codes = {row["kill_switch_code"] for row in rows}

    assert {
        "real_money_detected",
        "manual_approval_missing",
        "source_nature_is_synthetic_fixture",
        "stale_signal_detected",
        "duplicate_signal_detected",
        "margin_above_policy_cap",
        "audit_logging_unavailable",
    } <= codes
    assert all(row["manual_approval_can_override"] == "false" for row in rows)


def test_warning_escalation_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["warning_escalation"])
    codes = {row["warning_code"] for row in rows}

    assert {
        "margin_warning_threshold",
        "spread_near_max_threshold",
        "stale_time_proximity",
        "fixture_only_source",
        "missing_noncritical_advisory_artifact",
    } <= codes


def test_pre_execution_block_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["pre_execution_blocks"])
    codes = {row["block_code"] for row in rows}

    assert {
        "missing_live_data_would_signal",
        "fixture_source",
        "missing_manual_approval",
        "stale_signal",
        "duplicate_protection_failure",
        "state_reconciliation_failure",
        "unsafe_policy_flag",
    } <= codes


def test_audit_requirement_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["audit_requirements"])
    areas = {row["audit_area"] for row in rows}

    assert {
        "approval_audit_before",
        "approval_audit_after",
        "operator_approval_timestamp",
        "operator_decision_label",
        "signal_id",
        "idempotency_key",
        "kill_switch_checks",
        "approval_no_order_evidence",
    } <= areas


def test_future_state_transition_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_state_transitions"])
    transitions = {(row["from_state"], row["to_state"]) for row in rows}

    assert {
        ("signal_seen", "pending_manual_review"),
        ("pending_manual_review", "manually_rejected"),
        ("pending_manual_review", "approved_for_future_request_construction_only"),
        ("pending_manual_review", "blocked_by_kill_switch"),
        ("approved_for_future_request_construction_only", "revoked"),
        ("approved_for_future_request_construction_only", "blocked_by_kill_switch"),
    } <= transitions
    assert all(row["order_execution_performed"] == "false" for row in rows)


def test_static_safety_grep_confirms_forbidden_call_signatures_absent() -> None:
    source = Path(approval_plan.__file__).read_text(encoding="utf-8")
    forbidden = [
        "MetaTrader5",
        "mt5.initialize",
        "positions_get(",
        "orders_get(",
        "history_orders_get(",
        "history_deals_get(",
        "order_send(",
        "order_check(",
        "order_calc_margin(",
        "order_calc_profit(",
    ]

    for token in forbidden:
        assert token not in source


def test_no_scheduler_loop_background_markers() -> None:
    source = Path(approval_plan.__file__).read_text(encoding="utf-8")
    forbidden = ["Task Scheduler", "schtasks", "while True", "APScheduler", "threading.Timer"]

    for token in forbidden:
        assert token not in source
