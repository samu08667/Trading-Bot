from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_future_request_construction_readiness_plan as request_plan


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


def reconciliation_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "run_id": "source_reconciliation",
        "plan_status": "future_broker_state_reconciliation_check_plan_fixture_only",
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
        "no_future_state_json_read_performed": True,
        "no_future_state_json_write_performed": True,
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
    data: dict[str, object] = {"run_id": "source_reconciliation", "name": "row", "caveat": "source"}
    data.update(overrides)
    return data


def write_source_artifacts(
    root: Path,
    *,
    manifest_data: dict[str, object] | None = None,
    missing_manifest: bool = False,
    missing_local_state: bool = False,
    missing_broker_reads: bool = False,
    missing_matching: bool = False,
    missing_statuses: bool = False,
    missing_mismatch: bool = False,
    missing_max_open: bool = False,
    missing_pre_blocks: bool = False,
    missing_audit: bool = False,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if not missing_manifest:
        write_json(root / request_plan.SOURCE_MANIFEST, manifest_data or reconciliation_manifest())
    if not missing_local_state:
        write_csv(root / request_plan.SOURCE_LOCAL_STATE_REQUIREMENTS, [source_csv_row(state_field="candidate_id")], ["run_id", "name", "caveat", "state_field"])
    if not missing_broker_reads:
        write_csv(root / request_plan.SOURCE_FUTURE_BROKER_READS, [source_csv_row(future_call_name="positions_get")], ["run_id", "name", "caveat", "future_call_name"])
    if not missing_matching:
        write_csv(root / request_plan.SOURCE_MATCHING_FIELDS, [source_csv_row(matching_field="symbol")], ["run_id", "name", "caveat", "matching_field"])
    if not missing_statuses:
        write_csv(root / request_plan.SOURCE_RECONCILIATION_STATUSES, [source_csv_row(reconciliation_status="reconciliation_not_run")], ["run_id", "name", "caveat", "reconciliation_status"])
    if not missing_mismatch:
        write_csv(root / request_plan.SOURCE_MISMATCH_HANDLING, [source_csv_row(mismatch_code="local_open_broker_none")], ["run_id", "name", "caveat", "mismatch_code"])
    if not missing_max_open:
        write_csv(root / request_plan.SOURCE_MAX_OPEN_POSITIONS, [source_csv_row(max_open_area="future_local_open_count")], ["run_id", "name", "caveat", "max_open_area"])
    if not missing_pre_blocks:
        write_csv(root / request_plan.SOURCE_PRE_REQUEST_BLOCKS, [source_csv_row(block_code="reconciliation_not_run")], ["run_id", "name", "caveat", "block_code"])
    if not missing_audit:
        write_csv(root / request_plan.SOURCE_AUDIT_REQUIREMENTS, [source_csv_row(audit_area="timestamp")], ["run_id", "name", "caveat", "audit_area"])
    (root / request_plan.SOURCE_REPORT).write_text("source report\n", encoding="utf-8")
    write_csv(root / request_plan.SOURCE_MAIN, [], request_plan.MAIN_FIELDNAMES)
    write_csv(root / request_plan.SOURCE_WARNINGS, [], request_plan.WARNING_FIELDNAMES)
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
        "unit_future_request_construction_readiness_plan",
        "--future-broker-state-reconciliation-check-plan-dir",
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
    return request_plan.build_parser().parse_args(argv)


def build_valid_fixture_plan(tmp_path: Path) -> dict[str, Path]:
    return request_plan.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        request_plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written_on_happy_path(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_source_produces_fixture_only(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "future_request_construction_readiness_plan_fixture_only"
    assert manifest["plan_actionable"] is False
    assert manifest["request_construction_allowed_now"] is False
    assert manifest["recommended_next_step"] == "continue_no_order_monitoring_until_live_data_would_signal"


def test_live_data_source_produces_available_no_order(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=reconciliation_manifest(
            plan_status="future_broker_state_reconciliation_check_plan_available_no_order",
            source_nature="live_data_shadow_signal",
        ),
    )
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "future_request_construction_readiness_plan_available_no_order"
    assert manifest["recommended_next_step"] == "review_live_data_would_signal_and_refresh_planning_artifacts"


def test_missing_future_broker_state_reconciliation_manifest_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_manifest=True)
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_missing_future_broker_state_reconciliation_manifest"


def test_missing_local_state_requirements_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_local_state=True)
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_missing_local_state_requirements"


def test_missing_future_broker_reads_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_broker_reads=True)
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_missing_future_broker_reads"


def test_missing_matching_fields_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_matching=True)
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_missing_matching_fields"


def test_missing_reconciliation_statuses_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_statuses=True)
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_missing_reconciliation_statuses"


def test_missing_mismatch_handling_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_mismatch=True)
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_missing_mismatch_handling"


def test_missing_max_open_positions_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_max_open=True)
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_missing_max_open_positions"


def test_missing_pre_request_blocks_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_pre_blocks=True)
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_missing_pre_request_blocks"


def test_missing_audit_requirements_artifact_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_audit=True)
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_missing_audit_requirements"


def test_unacceptable_future_broker_local_reconciliation_status_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=reconciliation_manifest(plan_status="blocked_unreadable_input"),
    )
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_unacceptable_future_broker_state_reconciliation_status"


def test_unsafe_future_broker_local_reconciliation_boundary_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=reconciliation_manifest(no_order_request_constructed=False),
    )
    outputs = request_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_unsafe_future_broker_state_reconciliation_boundary"


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    outputs = request_plan.build_outputs(make_args(tmp_path, registry_data=canonical_registry(max_spread_points=2.5)))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_noncanonical_candidate"


def test_noncanonical_demo_execution_policy_blocks(tmp_path: Path) -> None:
    outputs = request_plan.build_outputs(make_args(tmp_path, policy_data=execution_policy(max_margin_usage_ratio=0.5)))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_noncanonical_demo_execution_policy"


def test_policy_without_manual_approval_required_blocks(tmp_path: Path) -> None:
    policy = execution_policy()
    safety = dict(policy["safety_boundaries"])  # type: ignore[index]
    safety["manual_approval_required_before_any_future_demo_order"] = False
    policy["safety_boundaries"] = safety
    outputs = request_plan.build_outputs(make_args(tmp_path, policy_data=policy))
    assert read_json(outputs["manifest"])["plan_status"] == "blocked_manual_approval_not_required_by_policy"


def test_upstream_evidence_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["upstream_evidence"])
    areas = {row["evidence_area"] for row in rows}

    assert {
        "live_data_would_signal_review",
        "broker_safe_margin_validation",
        "duplicate_protection",
        "manual_approval",
        "broker_local_reconciliation",
        "source_nature",
    } <= areas


def test_readiness_prerequisite_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["prerequisites"])
    names = {row["prerequisite_name"] for row in rows}

    assert {
        "candidate_identity_confirmed",
        "live_no_order_signal_confirmed",
        "risk_volume_shadow_plan_confirmed",
        "manual_approval_confirmed",
        "future_broker_local_reconciliation_clean",
        "audit_path_available",
    } <= names


def test_readiness_gate_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["readiness_gates"])
    names = {row["gate_name"] for row in rows}

    assert {
        "gate_live_signal",
        "gate_fixture_block",
        "gate_spread_policy",
        "gate_manual_approval",
        "gate_broker_local_reconciliation",
        "gate_no_scheduler",
        "gate_no_background_execution",
    } <= names
    assert all(row["evaluated_now"] == "false" for row in rows)


def test_future_field_descriptor_rows_are_present_and_non_actionable(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_field_descriptors"])
    names = {row["descriptor_name"] for row in rows}

    assert set(request_plan.FUTURE_FIELD_DESCRIPTORS) <= names
    assert all(row["future_field_only"] == "true" for row in rows)
    assert all(row["not_constructed"] == "true" for row in rows)
    assert all(row["broker_request_field"] == "false" for row in rows)
    assert all(row["broker_payload_ready"] == "false" for row in rows)
    assert all(row["executable_now"] == "false" for row in rows)


def test_future_field_descriptors_do_not_create_broker_payload_keys(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_field_descriptors"])
    names = {row["descriptor_name"] for row in rows}

    assert not (names & request_plan.RESERVED_BROKER_PAYLOAD_KEYS)


def test_block_condition_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["block_conditions"])
    names = {row["block_condition"] for row in rows}

    assert {
        "fixture_source",
        "missing_live_data_would_signal",
        "missing_or_stale_manual_approval",
        "kill_switch_active",
        "broker_local_reconciliation_not_clean",
        "broker_open_position_exists",
        "unsafe_policy_flag",
    } <= names


def test_no_request_boundary_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["no_request_boundary"])
    names = {row["boundary_name"] for row in rows}

    assert {
        "request_construction_allowed_now",
        "broker_request_constructed",
        "broker_payload_constructed",
        "order_object_constructed",
        "order_send_allowed",
        "order_check_allowed",
        "order_execution_allowed",
        "demo_approval_performed",
    } <= names
    assert all(row["observed_value"] == "false" for row in rows)
    assert all(row["boundary_confirmed"] == "true" for row in rows)


def test_audit_requirement_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["audit_requirements"])
    areas = {row["audit_area"] for row in rows}

    assert {
        "upstream_artifact_run_ids",
        "readiness_gate_results",
        "block_condition_results",
        "manual_approval_status",
        "reconciliation_status",
        "idempotency_key",
        "no_broker_request_constructed",
        "no_order_executed",
    } <= areas


def test_manifest_confirms_request_construction_not_allowed_now(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["request_construction_allowed_now"] is False
    assert manifest["broker_request_constructed"] is False
    assert manifest["broker_payload_constructed"] is False
    assert manifest["order_object_constructed"] is False


def test_static_safety_grep_confirms_forbidden_call_signatures_absent() -> None:
    source = Path(request_plan.__file__).read_text(encoding="utf-8")
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
    source = Path(request_plan.__file__).read_text(encoding="utf-8")
    forbidden = ["Task Scheduler", "schtasks", "while True", "APScheduler", "threading.Timer"]

    for token in forbidden:
        assert token not in source
