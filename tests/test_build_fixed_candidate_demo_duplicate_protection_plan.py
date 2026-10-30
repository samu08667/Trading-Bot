from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_duplicate_protection_plan as duplicate_plan


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


def state_reconciliation_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "run_id": "source_state_reconciliation",
        "plan_status": "state_reconciliation_plan_fixture_only",
        "plan_actionable": False,
        "source_nature": "synthetic_fixture",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    data.update(overrides)
    return data


def idempotency_row(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "run_id": "source_state_reconciliation",
        "idempotency_area": "composition",
        "composition_order": 1,
        "component_name": "candidate_id",
        "expected_source": "future local signal/state artifact",
        "future_local_state_only": True,
        "not_broker_request_field": True,
        "caveat": "source",
    }
    data.update(overrides)
    return data


def state_schema_row(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "run_id": "source_state_reconciliation",
        "state_field": "candidate_id",
        "field_role": "future_local_demo_state",
        "required": True,
        "future_state_statuses": "empty",
        "source_or_future_input": "source",
        "caveat": "source",
    }
    data.update(overrides)
    return data


def future_broker_read_row(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "run_id": "source_state_reconciliation",
        "future_read_label": "positions_reconciliation",
        "future_call_name": "positions_get",
        "allowed_only_in_future_reconciliation_module": True,
        "current_module_called": False,
        "required_before_future_execution": True,
        "caveat": "source",
    }
    data.update(overrides)
    return data


def write_source_artifacts(
    root: Path,
    *,
    manifest_data: dict[str, object] | None = None,
    missing_manifest: bool = False,
    missing_idempotency: bool = False,
    missing_schema: bool = False,
    missing_future_reads: bool = False,
    future_reads_data: list[dict[str, object]] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if not missing_manifest:
        write_json(root / duplicate_plan.SOURCE_MANIFEST, manifest_data or state_reconciliation_manifest())
    if not missing_idempotency:
        write_csv(root / duplicate_plan.SOURCE_IDEMPOTENCY, [idempotency_row()], list(idempotency_row().keys()))
    if not missing_schema:
        write_csv(root / duplicate_plan.SOURCE_STATE_SCHEMA, [state_schema_row()], list(state_schema_row().keys()))
    if not missing_future_reads:
        rows = future_reads_data or [
            future_broker_read_row(future_call_name="positions_get"),
            future_broker_read_row(future_call_name="orders_get"),
            future_broker_read_row(future_call_name="history_orders_get", required_before_future_execution=False),
            future_broker_read_row(future_call_name="history_deals_get", required_before_future_execution=False),
        ]
        write_csv(root / duplicate_plan.SOURCE_FUTURE_BROKER_READS, rows, list(future_broker_read_row().keys()))
    (root / duplicate_plan.SOURCE_REPORT).write_text("source report\n", encoding="utf-8")
    write_csv(root / duplicate_plan.SOURCE_MAIN, [], duplicate_plan.MAIN_FIELDNAMES)
    write_csv(root / duplicate_plan.SOURCE_FAILURE_MODES, [], ["run_id", "failure_mode"])
    write_csv(root / duplicate_plan.SOURCE_WARNINGS, [], duplicate_plan.WARNING_FIELDNAMES)
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
        "unit_duplicate_protection_plan",
        "--state-reconciliation-plan-dir",
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
    return duplicate_plan.build_parser().parse_args(argv)


def build_valid_fixture_plan(tmp_path: Path) -> dict[str, Path]:
    return duplicate_plan.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        duplicate_plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written_on_happy_path(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_source_produces_fixture_only(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "duplicate_protection_plan_fixture_only"
    assert manifest["plan_actionable"] is False
    assert manifest["recommended_next_step"] == "continue_no_order_monitoring_or_build_manual_approval_kill_switch_plan"


def test_live_data_source_produces_available_no_order(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=state_reconciliation_manifest(
            plan_status="state_reconciliation_plan_available_no_order",
            source_nature="live_data_shadow_signal",
        ),
    )
    outputs = duplicate_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "duplicate_protection_plan_available_no_order"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_demo_manual_approval_kill_switch_plan"


def test_missing_state_reconciliation_manifest_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_manifest=True)
    outputs = duplicate_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_state_reconciliation_manifest"


def test_missing_idempotency_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_idempotency=True)
    outputs = duplicate_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_state_reconciliation_idempotency"


def test_missing_state_schema_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_schema=True)
    outputs = duplicate_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_state_reconciliation_state_schema"


def test_missing_future_broker_reads_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_future_reads=True)
    outputs = duplicate_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_state_reconciliation_future_broker_reads"


def test_unacceptable_state_reconciliation_status_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=state_reconciliation_manifest(plan_status="blocked_unreadable_input"),
    )
    outputs = duplicate_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_unacceptable_state_reconciliation_status"


def test_unsafe_state_reconciliation_boundary_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=state_reconciliation_manifest(no_order_request_constructed=False),
    )
    outputs = duplicate_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_unsafe_state_reconciliation_boundary"


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    outputs = duplicate_plan.build_outputs(make_args(tmp_path, registry_data=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_noncanonical_candidate"


def test_noncanonical_demo_execution_policy_blocks(tmp_path: Path) -> None:
    unsafe = execution_policy()
    safety = dict(unsafe["safety_boundaries"])  # type: ignore[index]
    safety["order_calc_allowed"] = True
    unsafe["safety_boundaries"] = safety
    outputs = duplicate_plan.build_outputs(make_args(tmp_path, policy_data=unsafe))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_noncanonical_demo_execution_policy"


def test_signal_identity_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["signal_identity"])
    fields = {row["signal_identity_field"] for row in rows}

    assert set(duplicate_plan.SIGNAL_IDENTITY_FIELDS) <= fields
    assert all(row["not_broker_request_field"] == "true" for row in rows)


def test_idempotency_composition_row_is_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["idempotency_checks"])
    components = [row["component_name"] for row in rows if row["idempotency_area"] == "composition"]

    assert components == list(duplicate_plan.IDEMPOTENCY_COMPONENTS)
    assert "+".join(duplicate_plan.IDEMPOTENCY_COMPONENTS) in rows[0]["caveat"]


def test_duplicate_state_gate_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["state_gates"])
    gates = {row["state_gate"] for row in rows}
    statuses = {row["state_status_or_condition"] for row in rows}

    assert {
        "duplicate_signal_time_server",
        "duplicate_signal_id",
        "duplicate_idempotency_key",
        "same_candle_rerun_not_terminal",
        "max_open_positions_exceeded",
    } <= gates
    assert {"empty", "manually_rejected", "closed_future_only", "stale_signal_blocked", "duplicate_blocked"} <= statuses


def test_max_open_positions_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["max_open_positions"])
    areas = {row["max_open_area"] for row in rows}

    assert {
        "future_local_open_count",
        "future_broker_open_count",
        "local_broker_count_match",
        "netting_hedging_workaround",
        "second_trade_while_pending_or_open",
    } <= areas


def test_stale_signal_policy_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["stale_signal_policy"])
    areas = {row["stale_policy_area"] for row in rows}

    assert {"m15_candle_identity", "same_candle_rerun", "horizon_age_gate", "manual_approval_age_gate"} <= areas
    assert all(row["horizon_bars"] == "10" for row in rows)


def test_future_pre_execution_duplicate_checks_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_pre_execution_checks"])
    names = {row["future_check_name"] for row in rows}

    assert {
        "future_state_file_exists_or_initialized_empty_safely",
        "idempotency_key_not_already_present",
        "signal_time_server_not_already_processed",
        "no_pending_or_open_state",
        "max_open_positions_equals_one_and_not_exceeded",
        "manual_approval_gate_after_duplicate_checks",
    } <= names


def test_future_broker_reads_are_future_only_and_not_executed(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_pre_execution_checks"])
    broker_rows = [row for row in rows if row["future_check_area"] == "future_broker_reads"]
    names = {row["future_check_name"] for row in broker_rows}

    assert {
        "positions_get_future_only",
        "orders_get_future_only_if_separately_planned",
        "history_orders_get_forbidden_unless_separately_planned",
        "history_deals_get_forbidden_unless_separately_planned",
    } <= names
    assert all(row["future_only"] == "true" for row in broker_rows)
    assert all(row["current_module_performed"] == "false" for row in broker_rows)


def test_static_safety_grep_confirms_forbidden_call_signatures_absent() -> None:
    source = Path(duplicate_plan.__file__).read_text(encoding="utf-8")
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
    source = Path(duplicate_plan.__file__).read_text(encoding="utf-8")
    forbidden = ["Task Scheduler", "schtasks", "while True", "APScheduler", "threading.Timer"]

    for token in forbidden:
        assert token not in source
