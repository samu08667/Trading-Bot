import json
from pathlib import Path

from scripts import finalize_fixed_candidate_demo_send_rejected_state as finalizer


IDEMPOTENCY_KEY = "fb5f5b7c41aba4ad30948096ee1e2ca9db21ee54f8f2cb43a649b8afe4694439"


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def state_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "approval_record_id": "approval-123",
        "broker_deal_ticket": 0,
        "broker_order_ticket": 0,
        "broker_pending_order_count_after_send": 0,
        "broker_position_count_after_send": 0,
        "broker_position_ticket": "",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "compare_and_swap_equivalent": "exclusive_lock_plus_fresh_state_reread",
        "crash_recovery_required": True,
        "direction": "short",
        "idempotency_key": IDEMPOTENCY_KEY,
        "last_retcode": 10027,
        "order_check_digest": "order-check-digest",
        "order_check_run_id": "order-check-run",
        "pre_send_claimed_at_utc": "2026-06-27T13:10:52+00:00",
        "reconciliation_status": "broker_local_reconciliation_missing_after_uncertain_result",
        "request_intent_digest": "request-intent-digest",
        "send_attempt_id": "send-attempt-001",
        "send_completed_at_utc": "2026-06-27T13:10:53+00:00",
        "send_started_at_utc": "2026-06-27T13:10:52+00:00",
        "signal_id": IDEMPOTENCY_KEY,
        "state_status": "reconciliation_hold",
        "state_version": 1,
        "state_write_performed": True,
        "symbol": "GBPUSD",
        "timeframe": "M15",
    }
    payload.update(overrides)
    return payload


def reconciliation_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "recon-run",
        "reconciliation_status": "broker_local_reconciliation_clean_no_local_no_broker",
        "broker_position_count_symbol": 0,
        "broker_pending_order_count_symbol": 0,
        "local_state_exists": True,
        "positions_get_called": True,
        "orders_get_called": True,
        "positions_get_call_count": 1,
        "orders_get_call_count": 1,
        "future_state_json_written": False,
        "no_order_send_called": True,
        "no_order_check_called": True,
    }
    payload.update(overrides)
    return payload


def write_reconciliation_dir(tmp_path: Path, manifest: dict[str, object], local_state: dict[str, object]) -> Path:
    recon_dir = tmp_path / "reconciliation"
    write_json(recon_dir / finalizer.BROKER_LOCAL_RECONCILIATION_MANIFEST, manifest)
    write_json(
        recon_dir / finalizer.BROKER_LOCAL_RECONCILIATION_LOCAL_STATE,
        {
            "future_state_json": str(tmp_path / "state.json"),
            "local_state_exists": True,
            "local_state_status": "local_state_flat",
            "local_state_read_only": True,
            "future_state_json_written": False,
            "local_state": local_state,
        },
    )
    return recon_dir


def run_finalizer(
    tmp_path: Path,
    *,
    state: dict[str, object] | None = None,
    reconciliation: dict[str, object] | None = None,
    snapshot_state: dict[str, object] | None = None,
    expected_idempotency_key: str = IDEMPOTENCY_KEY,
    expected_retcode: int = 10027,
    acknowledgment: str = finalizer.FINALIZATION_ACKNOWLEDGMENT,
) -> tuple[int, Path, Path]:
    state_path = tmp_path / "state.json"
    current_state = state or state_payload()
    write_json(state_path, current_state)
    recon_dir = write_reconciliation_dir(
        tmp_path,
        reconciliation or reconciliation_payload(),
        snapshot_state or dict(current_state),
    )
    output_dir = tmp_path / "out"
    exit_code = finalizer.main(
        [
            "--run-id",
            "finalize-run",
            "--future-state-json",
            str(state_path),
            "--broker-local-reconciliation-dir",
            str(recon_dir),
            "--expected-idempotency-key",
            expected_idempotency_key,
            "--expected-retcode",
            str(expected_retcode),
            "--operator-acknowledgment",
            acknowledgment,
            "--output-dir",
            str(output_dir),
        ]
    )
    return exit_code, state_path, output_dir


def manifest(output_dir: Path) -> dict[str, object]:
    return read_json(output_dir / finalizer.OUTPUT_MANIFEST)


def test_flat_broker_and_retcode_10027_finalizes(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(tmp_path)
    after = read_json(state_path)
    result = manifest(output_dir)
    before_snapshot = read_json(output_dir / finalizer.OUTPUT_BEFORE_STATE)
    after_preview = read_json(output_dir / finalizer.OUTPUT_AFTER_STATE)

    assert exit_code == 0
    assert result["finalization_status"] == finalizer.COMPLETED_STATUS
    assert result["future_state_json_written"] is True
    assert after["state_status"] == "send_rejected_no_position_no_order"
    assert after["reconciliation_status"] == "broker_local_reconciliation_clean_after_client_reject_no_broker_state"
    assert after["crash_recovery_required"] is False
    assert after["automatic_retry_allowed"] is False
    assert after["retry_performed"] is False
    assert after["order_execution_performed"] is False
    assert after["finalization_reason"] == "client_autotrading_disabled_no_broker_state"
    assert after["finalized_at_utc"]
    assert after["send_attempt_id"] == "send-attempt-001"
    assert after["signal_id"] == IDEMPOTENCY_KEY
    assert after["idempotency_key"] == IDEMPOTENCY_KEY
    assert after["last_retcode"] == 10027
    assert after["send_started_at_utc"] == "2026-06-27T13:10:52+00:00"
    assert before_snapshot["state_status"] == "reconciliation_hold"
    assert after_preview["state_status"] == after["state_status"]


def test_broker_position_blocks(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(
        tmp_path,
        reconciliation=reconciliation_payload(broker_position_count_symbol=1),
    )
    after = read_json(state_path)
    result = manifest(output_dir)

    assert exit_code == 1
    assert result["finalization_status"] == "send_rejected_state_finalization_blocked_broker_position_count_not_zero"
    assert result["future_state_json_written"] is False
    assert after["state_status"] == "reconciliation_hold"


def test_pending_order_blocks(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(
        tmp_path,
        reconciliation=reconciliation_payload(broker_pending_order_count_symbol=1),
    )
    after = read_json(state_path)
    result = manifest(output_dir)

    assert exit_code == 1
    assert result["finalization_status"] == "send_rejected_state_finalization_blocked_broker_pending_order_count_not_zero"
    assert after["state_status"] == "reconciliation_hold"


def test_idempotency_mismatch_blocks(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(tmp_path, expected_idempotency_key="wrong-key")
    after = read_json(state_path)
    result = manifest(output_dir)

    assert exit_code == 1
    assert result["finalization_status"] == "send_rejected_state_finalization_blocked_idempotency_key_mismatch"
    assert result["idempotency_key_match"] is False
    assert after["state_status"] == "reconciliation_hold"


def test_retcode_mismatch_blocks(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(tmp_path, state=state_payload(last_retcode=10006))
    after = read_json(state_path)
    result = manifest(output_dir)

    assert exit_code == 1
    assert result["finalization_status"] == "send_rejected_state_finalization_blocked_last_retcode_mismatch"
    assert after["state_status"] == "reconciliation_hold"


def test_missing_ack_blocks(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(tmp_path, acknowledgment="")
    after = read_json(state_path)
    result = manifest(output_dir)

    assert exit_code == 1
    assert result["finalization_status"] == "send_rejected_state_finalization_blocked_operator_acknowledgment_invalid"
    assert result["operator_acknowledgment_valid"] is False
    assert after["state_status"] == "reconciliation_hold"


def test_wrong_current_state_blocks(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(
        tmp_path,
        state=state_payload(state_status="execution_rejected"),
    )
    after = read_json(state_path)
    result = manifest(output_dir)

    assert exit_code == 1
    assert result["finalization_status"] == "send_rejected_state_finalization_blocked_state_status_not_reconciliation_hold"
    assert after["state_status"] == "execution_rejected"


def test_non_empty_broker_tickets_block(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(
        tmp_path,
        state=state_payload(broker_order_ticket=12345),
    )
    after = read_json(state_path)
    result = manifest(output_dir)

    assert exit_code == 1
    assert result["finalization_status"] == "send_rejected_state_finalization_blocked_broker_order_ticket_present"
    assert after["state_status"] == "reconciliation_hold"


def test_reconciliation_status_must_be_clean_flat(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(
        tmp_path,
        reconciliation=reconciliation_payload(reconciliation_status="broker_local_reconciliation_hold_broker_pending_order_detected"),
    )
    after = read_json(state_path)
    result = manifest(output_dir)

    assert exit_code == 1
    assert result["finalization_status"] == "send_rejected_state_finalization_blocked_reconciliation_status_not_clean_flat"
    assert after["state_status"] == "reconciliation_hold"


def test_reconciliation_snapshot_mismatch_blocks(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(
        tmp_path,
        snapshot_state=state_payload(idempotency_key="other-key"),
    )
    after = read_json(state_path)
    result = manifest(output_dir)

    assert exit_code == 1
    assert result["finalization_status"] == "send_rejected_state_finalization_blocked_reconciliation_local_state_idempotency_key_mismatch"
    assert after["state_status"] == "reconciliation_hold"


def test_success_never_enables_retry_or_deletes_audit_fields(tmp_path: Path) -> None:
    exit_code, state_path, output_dir = run_finalizer(tmp_path)
    after = read_json(state_path)
    result = manifest(output_dir)
    no_order = (output_dir / finalizer.OUTPUT_NO_ORDER).read_text(encoding="utf-8")

    assert exit_code == 0
    assert after["automatic_retry_allowed"] is False
    assert after["retry_performed"] is False
    assert after["approval_record_id"] == "approval-123"
    assert after["order_check_digest"] == "order-check-digest"
    assert after["request_intent_digest"] == "request-intent-digest"
    assert after["send_completed_at_utc"] == "2026-06-27T13:10:53+00:00"
    assert result["state_deleted"] is False
    assert result["audit_trail_preserved"] is True
    assert "no_order_send_called" in no_order
    assert "true" in no_order
