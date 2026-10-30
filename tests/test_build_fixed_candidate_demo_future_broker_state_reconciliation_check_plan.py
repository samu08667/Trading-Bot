from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_future_broker_state_reconciliation_check_plan as recon_plan


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


def manual_approval_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "run_id": "source_manual_approval",
        "plan_status": "manual_approval_kill_switch_plan_fixture_only",
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
    data: dict[str, object] = {"run_id": "source_manual_approval", "name": "row", "caveat": "source"}
    data.update(overrides)
    return data


def write_source_artifacts(
    root: Path,
    *,
    manifest_data: dict[str, object] | None = None,
    missing_manifest: bool = False,
    missing_manual_gate: bool = False,
    missing_kill_switch: bool = False,
    missing_pre_execution: bool = False,
    missing_audit: bool = False,
    missing_transitions: bool = False,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if not missing_manifest:
        write_json(root / recon_plan.SOURCE_MANIFEST, manifest_data or manual_approval_manifest())
    if not missing_manual_gate:
        write_csv(root / recon_plan.SOURCE_MANUAL_APPROVAL_GATE, [source_csv_row(gate_name="explicit_manual_approval_required")], ["run_id", "name", "caveat", "gate_name"])
    if not missing_kill_switch:
        write_csv(root / recon_plan.SOURCE_KILL_SWITCH_RULES, [source_csv_row(kill_switch_code="real_money_detected")], ["run_id", "name", "caveat", "kill_switch_code"])
    if not missing_pre_execution:
        write_csv(root / recon_plan.SOURCE_PRE_EXECUTION_BLOCKS, [source_csv_row(block_code="missing_manual_approval")], ["run_id", "name", "caveat", "block_code"])
    if not missing_audit:
        write_csv(root / recon_plan.SOURCE_AUDIT_REQUIREMENTS, [source_csv_row(audit_area="approval_audit_before")], ["run_id", "name", "caveat", "audit_area"])
    if not missing_transitions:
        write_csv(root / recon_plan.SOURCE_FUTURE_STATE_TRANSITIONS, [source_csv_row(from_state="signal_seen", to_state="pending_manual_review")], ["run_id", "name", "caveat", "from_state", "to_state"])
    (root / recon_plan.SOURCE_REPORT).write_text("source report\n", encoding="utf-8")
    write_csv(root / recon_plan.SOURCE_MAIN, [], recon_plan.MAIN_FIELDNAMES)
    write_csv(root / recon_plan.SOURCE_OPERATOR_REVIEW, [], ["run_id", "checklist_item"])
    write_csv(root / recon_plan.SOURCE_WARNING_ESCALATION, [], ["run_id", "warning_code"])
    write_csv(root / recon_plan.SOURCE_WARNINGS, [], recon_plan.WARNING_FIELDNAMES)
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
        "unit_future_broker_state_reconciliation_check_plan",
        "--manual-approval-kill-switch-plan-dir",
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
    return recon_plan.build_parser().parse_args(argv)


def build_valid_fixture_plan(tmp_path: Path) -> dict[str, Path]:
    return recon_plan.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        recon_plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written_on_happy_path(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_source_produces_fixture_only(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "future_broker_state_reconciliation_check_plan_fixture_only"
    assert manifest["plan_actionable"] is False
    assert manifest["recommended_next_step"] == "continue_no_order_monitoring_or_build_future_request_construction_readiness_plan"


def test_live_data_source_produces_available_no_order(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=manual_approval_manifest(
            plan_status="manual_approval_kill_switch_plan_available_no_order",
            source_nature="live_data_shadow_signal",
        ),
    )
    outputs = recon_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "future_broker_state_reconciliation_check_plan_available_no_order"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_demo_future_request_construction_readiness_plan"


def test_missing_manual_approval_kill_switch_manifest_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_manifest=True)
    outputs = recon_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_manual_approval_kill_switch_manifest"


def test_missing_manual_approval_gate_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_manual_gate=True)
    outputs = recon_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_manual_approval_gate"


def test_missing_kill_switch_rules_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_kill_switch=True)
    outputs = recon_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_kill_switch_rules"


def test_missing_pre_execution_blocks_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_pre_execution=True)
    outputs = recon_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_pre_execution_blocks"


def test_missing_audit_requirements_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_audit=True)
    outputs = recon_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_audit_requirements"


def test_missing_future_state_transitions_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_transitions=True)
    outputs = recon_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_future_state_transitions"


def test_unacceptable_manual_approval_kill_switch_status_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=manual_approval_manifest(plan_status="blocked_unreadable_input"),
    )
    outputs = recon_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_unacceptable_manual_approval_kill_switch_status"


def test_unsafe_manual_approval_kill_switch_boundary_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=manual_approval_manifest(no_order_request_constructed=False),
    )
    outputs = recon_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_unsafe_manual_approval_kill_switch_boundary"


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    outputs = recon_plan.build_outputs(make_args(tmp_path, registry_data=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_noncanonical_candidate"


def test_noncanonical_demo_execution_policy_blocks(tmp_path: Path) -> None:
    unsafe = execution_policy(max_margin_usage_ratio=0.5)
    outputs = recon_plan.build_outputs(make_args(tmp_path, policy_data=unsafe))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_noncanonical_demo_execution_policy"


def test_policy_without_manual_approval_required_blocks(tmp_path: Path) -> None:
    policy = execution_policy()
    safety = dict(policy["safety_boundaries"])  # type: ignore[index]
    safety["manual_approval_required_before_any_future_demo_order"] = False
    policy["safety_boundaries"] = safety
    outputs = recon_plan.build_outputs(make_args(tmp_path, policy_data=policy))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_manual_approval_not_required_by_policy"


def test_local_state_requirements_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["local_state_requirements"])
    fields = {row["state_field"] for row in rows}

    assert set(recon_plan.LOCAL_STATE_FIELDS) <= fields
    assert all(row["future_read_mode"] == "read_only_before_explicit_state_transition" for row in rows)


def test_future_broker_read_planning_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_broker_reads"])
    calls = {row["future_call_name"] for row in rows}

    assert {"positions_get", "orders_get", "history_orders_get", "history_deals_get", "order_send", "order_check", "order_calc_profit"} <= calls


def test_matching_fields_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["matching_fields"])
    fields = {row["matching_field"] for row in rows}

    assert set(recon_plan.MATCHING_FIELDS) <= fields


def test_reconciliation_statuses_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["reconciliation_statuses"])
    statuses = {row["reconciliation_status"] for row in rows}

    assert {
        "reconciliation_not_run",
        "reconciliation_clean_no_local_no_broker",
        "reconciliation_hold_local_open_broker_none",
        "reconciliation_hold_local_missing_broker_open",
        "reconciliation_hold_duplicate_broker_positions",
        "reconciliation_blocked_non_demo_account",
    } <= statuses


def test_mismatch_handling_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["mismatch_handling"])
    codes = {row["mismatch_code"] for row in rows}

    assert {
        "local_open_broker_none",
        "broker_open_local_missing",
        "broker_pending_order_detected",
        "duplicate_broker_positions_detected",
        "sl_tp_mismatch",
        "stale_local_state",
    } <= codes
    assert all(row["allow_future_request_construction"] == "false" for row in rows)


def test_max_open_position_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["max_open_positions"])
    areas = {row["max_open_area"] for row in rows}

    assert {
        "future_local_open_count",
        "future_broker_open_position_count",
        "future_broker_pending_order_count",
        "unknown_count",
        "local_broker_count_match",
        "hedging_workaround",
        "netting_workaround",
        "second_trade_pending_open_unknown",
    } <= areas


def test_pre_request_block_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["pre_request_blocks"])
    codes = {row["block_code"] for row in rows}

    assert {
        "reconciliation_not_run",
        "reconciliation_hold_status",
        "broker_read_unavailable",
        "non_demo_account",
        "local_broker_mismatch",
        "max_open_positions_breach",
        "missing_manual_approval",
        "kill_switch_active",
    } <= codes


def test_audit_requirement_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["audit_requirements"])
    areas = {row["audit_area"] for row in rows}

    assert {
        "timestamp",
        "account_mode_label",
        "local_state_digest",
        "broker_position_count",
        "broker_order_count",
        "reconciliation_status",
        "no_order_request_constructed",
        "no_order_execution_performed",
    } <= areas


def test_positions_and_orders_reads_are_future_only_and_not_executed(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_broker_reads"])
    calls = {row["future_call_name"]: row for row in rows}

    assert calls["positions_get"]["future_only"] == "true"
    assert calls["orders_get"]["future_only"] == "true"
    assert calls["positions_get"]["current_module_called"] == "false"
    assert calls["orders_get"]["current_module_called"] == "false"


def test_history_reads_remain_forbidden_unless_separately_planned(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_broker_reads"])
    calls = {row["future_call_name"]: row for row in rows}

    assert calls["history_orders_get"]["forbidden_unless_separately_planned"] == "true"
    assert calls["history_deals_get"]["forbidden_unless_separately_planned"] == "true"
    assert calls["history_orders_get"]["current_module_called"] == "false"
    assert calls["history_deals_get"]["current_module_called"] == "false"


def test_static_safety_grep_confirms_forbidden_call_signatures_absent() -> None:
    source = Path(recon_plan.__file__).read_text(encoding="utf-8")
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
    source = Path(recon_plan.__file__).read_text(encoding="utf-8")
    forbidden = ["Task Scheduler", "schtasks", "while True", "APScheduler", "threading.Timer"]

    for token in forbidden:
        assert token not in source
