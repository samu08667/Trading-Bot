import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_order_send_pilot_readiness_plan as plan


FUTURE_EXPIRY = "2099-01-01T00:00:00+00:00"
EXPIRED_EXPIRY = "2020-01-01T00:00:00+00:00"
DEMO_MODULE_VALIDATION_ARGS = [
    "--module-validation-demo-execution",
    "--allow-stale-upstream-artifacts-for-demo-module-validation",
    "--module-validation-acknowledgment",
    plan.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
    "--allow-expired-signal-for-demo-module-validation",
    "--expired-signal-override-acknowledgment",
    plan.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
]


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, content: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def canonical_registry(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
        "horizon_bars": 10,
    }
    content.update(overrides)
    return content


def demo_policy(**boundary_overrides: object) -> dict[str, object]:
    boundaries: dict[str, object] = {
        "real_money_allowed": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "order_check_allowed": False,
        "order_calc_allowed": False,
        "manual_approval_required_before_any_future_demo_order": True,
    }
    boundaries.update(boundary_overrides)
    return {
        "policy_id": "fixture_policy",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
        "safety_boundaries": boundaries,
    }


def order_check_manifest(status: str = "order_check_available_passed_no_send", **overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "run_id": "order_check_fixture",
        "order_check_status": status,
        "order_check_called": status in {"order_check_available_passed_no_send", "order_check_available_failed_no_send"},
        "order_check_call_count": 1 if status in {"order_check_available_passed_no_send", "order_check_available_failed_no_send"} else 0,
        "order_check_passed": status == "order_check_available_passed_no_send",
        "order_check_retcode": 0 if status == "order_check_available_passed_no_send" else 10013,
        "order_send_called": False,
        "order_send_call_count": 0,
        "order_execution_performed": False,
        "broker_payload_written": False,
        "executable_order_object_written": False,
        "future_state_json_written": False,
    }
    content.update(overrides)
    return content


def request_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "request_construction_status": "request_construction_dry_run_available_non_executable",
        "request_intent_created": True,
        "broker_payload_constructed": False,
        "executable_order_object_constructed": False,
        "order_send_called": False,
        "order_execution_performed": False,
    }
    content.update(overrides)
    return content


def module_validation_request_manifest(**overrides: object) -> dict[str, object]:
    content = request_manifest(
        request_construction_status="request_construction_dry_run_available_with_stale_override_for_demo_module_validation",
        module_validation_demo_execution=True,
        stale_override_used=True,
        strategy_valid=False,
        production_valid=False,
        order_check_allowed_for_demo_module_validation_only=True,
        order_send_allowed_for_demo_module_validation_only=False,
    )
    content.update(overrides)
    return content


def readiness_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "order_check_readiness_status": "order_check_readiness_plan_available_no_order_check",
        "future_order_check_ready": True,
    }
    content.update(overrides)
    return content


def approval_record(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "approval_status": "approved_for_future_request_construction_only",
        "approval_scope": "future_request_construction_only",
        "approval_does_not_execute_order": True,
        "approval_does_not_construct_request": True,
        "approval_requires_final_pre_request_recheck": True,
        "approval_revoked": False,
        "record_hash_or_digest": "a" * 64,
        "approval_expiry_time_utc": FUTURE_EXPIRY,
        "signal_id": "signal_fixture",
        "idempotency_key": "idem_fixture",
    }
    content.update(overrides)
    return content


def schema_manifest() -> dict[str, object]:
    return {
        "schema_status": "manual_approval_record_schema_available_no_order",
        "schema_patch_status": "schema_audit_gaps_closed_no_order",
    }


def reconciliation_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "reconciliation_status": "broker_local_reconciliation_clean_no_local_no_broker",
        "broker_position_count_symbol": 0,
        "broker_pending_order_count_symbol": 0,
    }
    content.update(overrides)
    return content


def margin_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "validation_status": "broker_safe_margin_validation_available",
        "source_nature": "live_data_shadow_signal",
        "account_mode_label": "demo",
        "account_currency": "EUR",
        "account_equity_policy_status": "within_10pct",
        "broker_margin_usage_ratio": 0.27,
        "spread_within_policy": True,
        "stepped_volume_lots": 0.07,
        "margin_calc_volume_lots": 0.07,
    }
    content.update(overrides)
    return content


def freshness_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "freshness_status": "live_signal_freshness_fresh_current_or_latest_signal",
        "is_fresh": True,
        "is_stale": False,
        "bars_elapsed": 1,
    }
    content.update(overrides)
    return content


def duplicate_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "plan_status": "duplicate_protection_plan_available_no_order",
        "max_open_positions": 1,
        "plan_actionable": False,
    }
    content.update(overrides)
    return content


def manual_plan_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "plan_status": "manual_approval_kill_switch_plan_available_no_order",
        "kill_switch_executed": False,
        "plan_actionable": False,
    }
    content.update(overrides)
    return content


def future_request_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "plan_status": "future_request_construction_readiness_plan_available_no_order",
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
    }
    content.update(overrides)
    return content


def write_sources(
    tmp_path: Path,
    *,
    write_order_check: bool = True,
    order_check_payload: dict[str, object] | None = None,
    request_payload: dict[str, object] | None = None,
    readiness_payload: dict[str, object] | None = None,
    approval_payload: dict[str, object] | None = None,
    recon_payload: dict[str, object] | None = None,
    margin_payload: dict[str, object] | None = None,
    freshness_payload: dict[str, object] | None = None,
    duplicate_payload: dict[str, object] | None = None,
    manual_payload: dict[str, object] | None = None,
    future_request_payload: dict[str, object] | None = None,
    registry_payload: dict[str, object] | None = None,
    policy_payload: dict[str, object] | None = None,
    future_state_payload: dict[str, object] | None = None,
) -> dict[str, Path]:
    order_dir = tmp_path / "order_check"
    readiness_dir = tmp_path / "readiness"
    request_dir = tmp_path / "request"
    schema_dir = tmp_path / "schema"
    recon_dir = tmp_path / "recon"
    margin_dir = tmp_path / "margin"
    freshness_dir = tmp_path / "freshness"
    duplicate_dir = tmp_path / "duplicate"
    manual_dir = tmp_path / "manual"
    future_request_dir = tmp_path / "future_request"
    if write_order_check:
        order_data = order_check_payload or order_check_manifest()
        write_json(order_dir / plan.ORDER_CHECK_MANIFEST, order_data)
        write_csv(
            order_dir / plan.ORDER_CHECK_STATUS,
            [
                {
                    "run_id": "order_check_fixture",
                    "order_check_status": order_data["order_check_status"],
                    "order_check_passed": order_data["order_check_passed"],
                    "order_send_called": "false",
                    "order_execution_performed": "false",
                }
            ],
            ["run_id", "order_check_status", "order_check_passed", "order_send_called", "order_execution_performed"],
        )
        write_csv(
            order_dir / plan.ORDER_CHECK_BOUND_INTENT,
            [
                {
                    "run_id": "order_check_fixture",
                    "signal_id": "signal_fixture",
                    "idempotency_key": "idem_fixture",
                    "approval_record_id": "approval_fixture",
                }
            ],
            ["run_id", "signal_id", "idempotency_key", "approval_record_id"],
        )
        write_csv(order_dir / plan.ORDER_CHECK_GATES, [], ["run_id"])
        write_csv(order_dir / plan.ORDER_CHECK_PREVIEW, [], ["run_id"])
        write_json(order_dir / plan.ORDER_CHECK_RESULT, {"result_available": True})
    write_json(readiness_dir / plan.READINESS_MANIFEST, readiness_payload or readiness_manifest())
    write_json(request_dir / plan.REQUEST_MANIFEST, request_payload or request_manifest())
    write_json(schema_dir / plan.SCHEMA_MANIFEST, schema_manifest())
    write_json(tmp_path / "state" / "approval.json", approval_payload or approval_record())
    write_json(recon_dir / plan.BROKER_RECON_MANIFEST, recon_payload or reconciliation_manifest())
    write_json(margin_dir / plan.MARGIN_MANIFEST, margin_payload or margin_manifest())
    write_json(margin_dir / plan.MARGIN_SNAPSHOT, margin_payload or margin_manifest())
    write_json(freshness_dir / plan.FRESHNESS_MANIFEST, freshness_payload or freshness_manifest())
    write_json(duplicate_dir / plan.DUPLICATE_MANIFEST, duplicate_payload or duplicate_manifest())
    write_json(manual_dir / plan.MANUAL_PLAN_MANIFEST, manual_payload or manual_plan_manifest())
    write_json(future_request_dir / plan.FUTURE_REQUEST_MANIFEST, future_request_payload or future_request_manifest())
    write_json(tmp_path / "config" / "canonical.json", registry_payload or canonical_registry())
    write_json(tmp_path / "config" / "policy.json", policy_payload or demo_policy())
    future_state = tmp_path / "state" / "future_state.json"
    if future_state_payload is not None:
        write_json(future_state, future_state_payload)
    return {
        "order_check": order_dir,
        "readiness": readiness_dir,
        "request": request_dir,
        "schema": schema_dir,
        "approval": tmp_path / "state" / "approval.json",
        "recon": recon_dir,
        "margin": margin_dir,
        "freshness": freshness_dir,
        "duplicate": duplicate_dir,
        "manual": manual_dir,
        "future_request": future_request_dir,
        "registry": tmp_path / "config" / "canonical.json",
        "policy": tmp_path / "config" / "policy.json",
        "future_state": future_state,
    }


def args_for(tmp_path: Path, paths: dict[str, Path], *extra: str) -> object:
    return plan.build_parser().parse_args(
        [
            "--run-id",
            "send_plan_fixture",
            "--order-check-dir",
            str(paths["order_check"]),
            "--order-check-readiness-plan-dir",
            str(paths["readiness"]),
            "--request-construction-dry-run-dir",
            str(paths["request"]),
            "--manual-approval-record-json",
            str(paths["approval"]),
            "--manual-approval-record-schema-dir",
            str(paths["schema"]),
            "--broker-local-reconciliation-dir",
            str(paths["recon"]),
            "--broker-safe-margin-validation-dir",
            str(paths["margin"]),
            "--live-signal-freshness-dir",
            str(paths["freshness"]),
            "--duplicate-protection-plan-dir",
            str(paths["duplicate"]),
            "--manual-approval-kill-switch-plan-dir",
            str(paths["manual"]),
            "--future-request-readiness-plan-dir",
            str(paths["future_request"]),
            "--canonical-registry",
            str(paths["registry"]),
            "--demo-execution-policy",
            str(paths["policy"]),
            "--future-state-json",
            str(paths["future_state"]),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
        + list(extra)
    )


def build(tmp_path: Path, *extra: str, **kwargs: object) -> tuple[dict[str, Path], dict[str, object]]:
    paths = write_sources(tmp_path, **kwargs)
    outputs = plan.build_outputs(args_for(tmp_path, paths, *extra))
    return outputs, read_json(outputs["manifest"])


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        plan.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_missing_order_check_artifact_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, write_order_check=False)
    assert manifest["order_send_pilot_readiness_status"].startswith("order_send_pilot_readiness_plan_blocked")


def test_fixture_only_order_check_produces_fixture_status(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, order_check_payload=order_check_manifest("order_check_blocked_fixture_only_no_request_intent"))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_fixture_only_no_order_check_pass"


def test_dry_run_no_broker_order_check_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, order_check_payload=order_check_manifest("order_check_dry_run_no_broker_call"))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_no_real_order_check_pass"


def test_failed_order_check_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, order_check_payload=order_check_manifest("order_check_available_failed_no_send"))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_order_check_failed"


def test_passed_order_check_with_valid_upstream_artifacts_produces_available(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_available_no_send"


def test_demo_module_validation_request_and_passed_order_check_produces_available(tmp_path: Path) -> None:
    outputs, manifest = build(
        tmp_path,
        *DEMO_MODULE_VALIDATION_ARGS,
        request_payload=module_validation_request_manifest(),
        readiness_payload=readiness_manifest(
            order_check_readiness_status="order_check_readiness_plan_fixture_only_no_request_intent",
            future_order_check_ready=False,
        ),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )
    report = outputs["report"].read_text(encoding="utf-8")

    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_available_no_send"
    assert manifest["module_validation_demo_execution"] is True
    assert manifest["stale_override_used"] is True
    assert manifest["expired_signal_override_used"] is True
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False
    assert manifest["send_readiness_for_demo_module_validation_only"] is True
    assert "send_readiness_for_demo_module_validation_only: `True`" in report


def test_demo_module_validation_blocks_without_stale_ack(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        "wrong_ack",
        request_payload=module_validation_request_manifest(),
        readiness_payload=readiness_manifest(
            order_check_readiness_status="order_check_readiness_plan_fixture_only_no_request_intent",
            future_order_check_ready=False,
        ),
    )

    assert manifest["order_send_pilot_readiness_status"].startswith("order_send_pilot_readiness_plan_blocked")
    assert manifest["send_readiness_for_demo_module_validation_only"] is False


def test_demo_module_validation_expired_approval_requires_expired_override_ack(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        plan.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
        request_payload=module_validation_request_manifest(),
        readiness_payload=readiness_manifest(
            order_check_readiness_status="order_check_readiness_plan_fixture_only_no_request_intent",
            future_order_check_ready=False,
        ),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )

    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_expired_approval"
    assert manifest["expired_signal_override_used"] is False


def test_demo_module_validation_still_blocks_when_order_check_not_passed(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        *DEMO_MODULE_VALIDATION_ARGS,
        order_check_payload=order_check_manifest("order_check_available_failed_no_send"),
        request_payload=module_validation_request_manifest(),
        readiness_payload=readiness_manifest(
            order_check_readiness_status="order_check_readiness_plan_fixture_only_no_request_intent",
            future_order_check_ready=False,
        ),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )

    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_order_check_failed"


def test_stale_signal_blocks_for_non_fixture_path(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        freshness_payload=freshness_manifest(
            freshness_status="live_signal_freshness_stale_beyond_horizon",
            is_fresh=False,
            is_stale=True,
            bars_elapsed=11,
        ),
    )
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_stale_signal"


def test_expired_approval_blocks_for_non_fixture_path(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_expired_approval"


def test_broker_local_reconciliation_hold_blocks_for_non_fixture_path(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, recon_payload=reconciliation_manifest(reconciliation_status="hold", broker_position_count_symbol=1))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_broker_local_reconciliation"


def test_margin_above_hard_cap_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, margin_payload=margin_manifest(broker_margin_usage_ratio=0.71))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_margin_policy"


def test_margin_warning_status_under_hard_cap_passes(tmp_path: Path) -> None:
    warning_status = "broker_safe_margin_validation_available_with_margin_warning"
    _outputs, manifest = build(
        tmp_path,
        margin_payload=margin_manifest(validation_status=warning_status, broker_margin_usage_ratio=0.6),
    )
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_available_no_send"


def test_margin_volume_mismatch_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        margin_payload=margin_manifest(stepped_volume_lots=0.05, margin_calc_volume_lots=0.07),
    )
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_margin_policy"


def test_margin_artifact_non_demo_account_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, margin_payload=margin_manifest(account_mode_label="real"))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_margin_policy"


def test_margin_spread_outside_policy_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, margin_payload=margin_manifest(spread_within_policy=False))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_margin_policy"


def test_duplicate_protection_unavailable_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, duplicate_payload=duplicate_manifest(plan_status="hold"))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_duplicate_protection"


def test_kill_switch_active_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, manual_payload=manual_plan_manifest(kill_switch_executed=True))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_kill_switch"


def test_future_state_incompatible_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, future_state_payload={"state": "open"})
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_blocked_future_state_incompatible"


def client_reject_flat_state(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "state_status": "send_rejected_no_position_no_order",
        "last_retcode": 10027,
        "order_execution_performed": False,
        "crash_recovery_required": False,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "broker_order_ticket": "",
        "broker_deal_ticket": "",
        "broker_position_ticket": "",
        "signal_id": "signal_fixture",
        "idempotency_key": "idem_fixture",
    }
    payload.update(overrides)
    return payload


def test_client_reject_flat_state_blocks_without_specific_ack(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        *DEMO_MODULE_VALIDATION_ARGS,
        request_payload=module_validation_request_manifest(),
        order_check_payload=order_check_manifest(module_validation_demo_execution=True, strategy_valid=False, production_valid=False),
        future_state_payload=client_reject_flat_state(),
    )

    assert (
        manifest["order_send_pilot_readiness_status"]
        == "order_send_pilot_readiness_plan_blocked_client_reject_resend_acknowledgment"
    )
    assert manifest["explicit_second_demo_send_after_client_reject_flat"] is False


def test_client_reject_flat_state_with_specific_ack_allows_readiness(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        *DEMO_MODULE_VALIDATION_ARGS,
        "--allow-new-demo-send-after-client-reject-flat",
        "--client-reject-resend-acknowledgment",
        plan.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        request_payload=module_validation_request_manifest(),
        order_check_payload=order_check_manifest(module_validation_demo_execution=True, strategy_valid=False, production_valid=False),
        future_state_payload=client_reject_flat_state(),
    )

    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_available_no_send"
    assert manifest["explicit_second_demo_send_after_client_reject_flat"] is True
    assert manifest["previous_state_status"] == "send_rejected_no_position_no_order"
    assert manifest["previous_send_retcode"] == 10027
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False
    assert manifest["automatic_retry_allowed"] is False
    assert manifest["retry_performed"] is False


def test_client_reject_flat_state_idempotency_mismatch_blocks_readiness(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        *DEMO_MODULE_VALIDATION_ARGS,
        "--allow-new-demo-send-after-client-reject-flat",
        "--client-reject-resend-acknowledgment",
        plan.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        request_payload=module_validation_request_manifest(),
        order_check_payload=order_check_manifest(module_validation_demo_execution=True, strategy_valid=False, production_valid=False),
        future_state_payload=client_reject_flat_state(idempotency_key="other"),
    )

    assert (
        manifest["order_send_pilot_readiness_status"]
        == "order_send_pilot_readiness_plan_blocked_future_state_incompatible"
    )
    assert manifest["explicit_second_demo_send_after_client_reject_flat"] is False


def test_future_order_send_input_descriptors_are_written(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["send_inputs"])
    assert {"action_intent", "symbol", "volume", "order_check_run_id"} <= {row["field_name"] for row in rows}


def test_future_broker_send_field_mappings_are_written(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["broker_send_fields"])
    assert {"action", "symbol", "volume", "type", "price", "sl", "tp"} <= {row["future_mt5_field"] for row in rows}


def test_every_future_broker_send_field_is_not_executable_now(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["broker_send_fields"])
    assert rows
    assert all(row["executable_now"] == "false" for row in rows)


def test_every_order_send_input_descriptor_is_not_payload_now(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["send_inputs"])
    assert rows
    assert all(row["broker_payload_field_now"] == "false" for row in rows)


def test_pre_send_rechecks_are_all_required_and_blocking(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["pre_send_rechecks"])
    assert rows
    assert all(row["required"] == "true" and row["blocking_if_failed"] == "true" for row in rows)


def test_state_transition_plan_rows_are_present(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    assert read_csv(outputs["state_transitions"])


def test_retcode_handling_rows_are_present(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    assert read_csv(outputs["retcodes"])


def test_post_send_reconciliation_rows_are_present(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    assert read_csv(outputs["post_send_reconciliation"])


def test_crash_recovery_rows_are_present(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    assert read_csv(outputs["crash_recovery"])


def test_manifest_confirms_order_send_called_false(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)
    assert manifest["order_send_called"] is False


def test_manifest_confirms_order_execution_performed_false(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)
    assert manifest["order_execution_performed"] is False


def test_manifest_confirms_future_state_json_written_false(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)
    assert manifest["future_state_json_written"] is False


def test_no_order_evidence_rows_are_present(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    evidence = read_csv(outputs["no_order"])[0]
    assert evidence["no_order_send_called"] == "true"
    assert evidence["no_order_check_called"] == "true"
    assert evidence["no_future_state_json_written"] == "true"


def test_static_safety_grep_confirms_no_forbidden_broker_order_history_calls() -> None:
    source = Path(plan.__file__).read_text(encoding="utf-8")
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


def test_static_safety_grep_confirms_no_scheduler_loop_background_behavior() -> None:
    source = Path(plan.__file__).read_text(encoding="utf-8")
    forbidden = ["while " + "True", "Background" + "Scheduler", "schedule" + ".every", "threading" + ".", "asyncio" + "."]
    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_executable_request_object_construction() -> None:
    source = Path(plan.__file__).read_text(encoding="utf-8")
    forbidden = ["request = {", "order_request = {", "broker_payload = {", "payload = {", "executable_order_object = {"]
    for token in forbidden:
        assert token not in source


def test_future_send_cli_contract_is_complete(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["future_send_cli_contract"])
    flags = {row["cli_flag"]: row for row in rows}
    assert {
        "--run-id",
        "--order-send-pilot-readiness-plan-dir",
        "--order-check-dir",
        "--request-construction-dry-run-dir",
        "--manual-approval-record-json",
        "--broker-local-reconciliation-dir",
        "--broker-safe-margin-validation-dir",
        "--live-signal-freshness-dir",
        "--duplicate-protection-plan-dir",
        "--manual-approval-kill-switch-plan-dir",
        "--canonical-registry",
        "--demo-execution-policy",
        "--future-state-json",
        "--output-dir",
        "--dry-run",
        "--allow-real-order-send",
        "--operator-final-send-confirmation",
        "--mt5-package",
        "--overwrite",
    } <= set(flags)
    assert flags["--dry-run"]["default_value"] == "true"
    assert flags["--allow-real-order-send"]["default_value"] == "false"
    assert "first real pilot" in flags["--operator-final-send-confirmation"]["blocking_rule"]


def test_final_operator_confirmation_contract_binds_current_evidence(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["final_operator_confirmation_contract"])
    required = {row["contract_item"] for row in rows if row["item_type"] == "required_binding_field"}
    assert {
        "signal_id",
        "idempotency_key",
        "approval_record_id",
        "approval_record_digest",
        "request_intent_digest",
        "order_check_run_id",
        "order_check_digest",
    } <= required
    label = next(row for row in rows if row["contract_item"] == "confirmation_label")
    assert label["allowed_value"] == "confirm_single_demo_send_only"


def test_final_operator_confirmation_forbidden_meanings_are_disallowed(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["final_operator_confirmation_contract"])
    forbidden = {row["contract_item"]: row for row in rows if row["item_type"] == "forbidden_confirmation_meaning"}
    assert {
        "approve_live_trading",
        "approve_multiple_sends",
        "bypass_checks",
        "ignore_stale_signal",
        "ignore_reconciliation",
        "ignore_margin_policy",
        "ignore_duplicate_protection",
        "ignore_kill_switch",
    } <= set(forbidden)
    assert all(row["allowed"] == "false" for row in forbidden.values())


def test_request_order_check_send_binding_requires_digest_recheck_and_match(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["request_order_check_send_binding"])
    names = {row["binding_name"] for row in rows}
    assert {
        "request_intent_digest",
        "request_fields_digest",
        "order_check_manifest_digest",
        "order_check_result_snapshot_digest",
        "approval_record_digest",
        "upstream_reconciliation_digest",
        "freshness_digest",
        "margin_validation_digest",
    } <= names
    assert all(row["recompute_immediately_before_send"] == "true" for row in rows)
    assert all(row["required_match"] == "true" and row["blocking_if_mismatch"] == "true" for row in rows)


def test_request_order_check_send_binding_checks_critical_fields(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["request_order_check_send_binding"])
    names = {row["binding_name"] for row in rows}
    assert {
        "intent_order_check_send_field_match_volume",
        "intent_order_check_send_field_match_sl",
        "intent_order_check_send_field_match_tp",
        "intent_order_check_send_field_match_symbol",
        "intent_order_check_send_field_match_side",
        "intent_order_check_send_field_match_signal_id",
        "intent_order_check_send_field_match_idempotency_key",
    } <= names


def test_atomic_state_contract_requires_durable_pre_send_pending(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["atomic_state_contract"])
    by_name = {row["requirement_name"]: row for row in rows}
    assert "atomic_idempotency_claim" in by_name
    assert "durable_pre_send_pending" in by_name
    assert "state_status=pre_send_pending" in by_name["durable_pre_send_pending"]["atomicity_requirement"]
    assert "before the single send attempt" in by_name["durable_pre_send_pending"]["timing"]
    assert "pending open or reconciliation_hold" in by_name["second_send_block"]["atomicity_requirement"]


def test_atomic_state_contract_contains_required_state_schema(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["atomic_state_contract"])
    schema = next(row for row in rows if row["requirement_name"] == "state_schema")
    assert {
        "state_version",
        "signal_id",
        "idempotency_key",
        "send_attempt_id",
        "state_status",
        "last_retcode",
        "reconciliation_status",
        "crash_recovery_required",
    } <= set(schema["required_fields"].split(";"))


def test_post_send_state_update_contract_has_exact_safe_sequence(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["post_send_state_update_contract"])
    assert [row["sequence_index"] for row in rows] == [str(index) for index in range(1, 8)]
    assert rows[0]["requirement_name"] == "persist_send_result_snapshot"
    assert rows[-1]["requirement_name"] == "block_second_send_until_resolved"
    assert all(row["state_on_failure"] == "reconciliation_hold" for row in rows)


def test_retcode_matrix_covers_failure_and_uncertain_outcomes(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["retcodes"])
    categories = {row["retcode_category"] for row in rows}
    assert {
        "partial_fill",
        "result_none",
        "exception",
        "timeout",
        "invalid_filling",
        "price_off",
        "too_many_requests",
        "connection_lost",
        "unknown_retcode",
    } <= categories
    assert all(row["retry_allowed_default"] == "false" for row in rows)
    assert all(row["duplicate_rerun_behavior"] == "block_second_send_until_reconciliation_is_resolved" for row in rows)


def test_post_send_reconciliation_is_bounded_and_forbids_history(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["post_send_reconciliation"])
    by_name = {row["requirement_name"]: row for row in rows}
    assert by_name["read_broker_positions_once"]["allowed_read"] == "positions_get symbol=GBPUSD"
    assert by_name["read_broker_positions_once"]["max_call_count"] == "1"
    assert by_name["read_broker_orders_once"]["allowed_read"] == "orders_get symbol=GBPUSD"
    assert by_name["read_broker_orders_once"]["max_call_count"] == "1"
    assert all(row["history_reads_allowed"] == "false" for row in rows)
    assert all(row["polling_allowed"] == "false" and row["scheduler_allowed"] == "false" for row in rows)
    assert all(row["scope"] == "GBPUSD_symbol_level_pilot" for row in rows)


def test_future_send_test_contract_includes_exactly_once_mocked_send(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["future_send_test_contract"])
    by_name = {row["test_name"]: row for row in rows}
    assert by_name["mocked_success_exactly_once"]["mocked_mt5_required"] == "true"
    assert by_name["mocked_success_exactly_once"]["exactly_once_send_expected"] == "true"
    assert by_name["mocked_reject_exactly_once"]["exactly_once_send_expected"] == "true"
    assert by_name["dry_run_never_imports_mt5"]["no_send_expected"] == "true"
    assert "rerun_never_sends_twice" in by_name


def test_future_send_safety_grep_contract_requires_one_gated_send_signature(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["future_send_safety_grep_contract"])
    by_name = {row["rule_name"]: row for row in rows}
    assert by_name["exactly_one_gated_send_signature"]["allowed_occurrence_count"] == "1"
    assert by_name["no_send_in_dry_run"]["allowed_occurrence_count"] == "0"
    assert by_name["no_history_reads"]["allowed_occurrence_count"] == "0"
    assert by_name["no_fixture_send"]["allowed_occurrence_count"] == "0"


def test_manifest_marks_readiness_audit_gaps_closed(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)
    assert manifest["readiness_patch_status"] == "order_send_pilot_readiness_audit_gaps_closed_no_send"
    for field in (
        "cli_contract_complete",
        "final_operator_confirmation_contract_complete",
        "binding_digest_contract_complete",
        "atomic_state_contract_complete",
        "post_send_state_update_contract_complete",
        "retcode_failure_matrix_complete",
        "bounded_reconciliation_contract_complete",
        "future_mocked_mt5_test_contract_complete",
        "future_send_safety_grep_contract_complete",
    ):
        assert manifest[field] is True


def test_manifest_includes_new_contract_output_files(tmp_path: Path) -> None:
    outputs, manifest = build(tmp_path)
    for key in (
        "future_send_cli_contract",
        "final_operator_confirmation_contract",
        "request_order_check_send_binding",
        "atomic_state_contract",
        "post_send_state_update_contract",
        "future_send_test_contract",
        "future_send_safety_grep_contract",
    ):
        assert Path(manifest["output_files"][key]) == outputs[key]


def test_fixture_only_status_remains_unchanged_after_readiness_patch(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, order_check_payload=order_check_manifest("order_check_blocked_fixture_only_no_request_intent"))
    assert manifest["order_send_pilot_readiness_status"] == "order_send_pilot_readiness_plan_fixture_only_no_order_check_pass"
    assert manifest["future_order_send_ready"] is False
    assert manifest["order_send_called"] is False
    assert manifest["future_state_json_written"] is False
