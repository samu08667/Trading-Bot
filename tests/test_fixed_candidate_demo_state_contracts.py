from scripts import fixed_candidate_demo_state_contracts as contracts


SIGNAL_ID = "signal-1"
IDEMPOTENCY_KEY = "signal-1"


def flat_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "state_status": "send_rejected_no_position_no_order",
        "last_retcode": 10027,
        "order_execution_performed": False,
        "crash_recovery_required": False,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "broker_order_ticket": "",
        "broker_deal_ticket": "",
        "broker_position_ticket": "",
        "signal_id": SIGNAL_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
    }
    state.update(overrides)
    return state


def market_closed_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "state_status": "execution_rejected",
        "last_retcode": 10018,
        "reconciliation_status": "broker_local_reconciliation_clean_after_reject_no_broker_state",
        "order_execution_performed": False,
        "crash_recovery_required": True,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "broker_order_ticket": 0,
        "broker_deal_ticket": 0,
        "broker_position_ticket": "",
        "broker_position_detected_after_send": False,
        "broker_pending_order_detected_after_send": False,
        "broker_position_count_after_send": 0,
        "broker_pending_order_count_after_send": 0,
        "signal_id": "previous-signal",
        "idempotency_key": "previous-idem",
    }
    state.update(overrides)
    return state


def clean_reconciliation(**overrides: object) -> dict[str, object]:
    reconciliation: dict[str, object] = {
        "reconciliation_status": "broker_local_reconciliation_clean_no_local_no_broker",
        "broker_position_count_symbol": 0,
        "broker_pending_order_count_symbol": 0,
    }
    reconciliation.update(overrides)
    return reconciliation


def evaluate(**overrides: object) -> dict[str, object]:
    kwargs = {
        "state": flat_state(),
        "signal_id": SIGNAL_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "module_validation_demo_execution": True,
        "demo_account_only": True,
        "allow_flag": True,
        "acknowledgment": contracts.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        "broker_local_reconciliation": clean_reconciliation(),
        "require_broker_local_reconciliation": True,
    }
    kwargs.update(overrides)
    return contracts.evaluate_explicit_second_demo_send_after_client_reject_flat(**kwargs)


def test_contract_accepts_client_reject_flat_with_ack() -> None:
    result = evaluate()
    assert result["accepted"] is True
    assert result["explicit_second_demo_send_after_client_reject_flat"] is True
    assert result["previous_state_status"] == "send_rejected_no_position_no_order"
    assert result["previous_send_retcode"] == 10027
    assert result["new_operator_authorized_attempt"] is True
    assert result["automatic_retry_allowed"] is False
    assert result["retry_performed"] is False


def test_contract_blocks_without_ack() -> None:
    result = evaluate(acknowledgment="")
    assert result["accepted"] is False
    assert "client_reject_resend_acknowledgment_required" in result["blocking_reasons"]


def test_contract_blocks_wrong_ack() -> None:
    result = evaluate(acknowledgment="wrong")
    assert result["accepted"] is False
    assert "client_reject_resend_acknowledgment_required" in result["blocking_reasons"]


def test_contract_blocks_reconciliation_hold() -> None:
    result = evaluate(state=flat_state(state_status="reconciliation_hold"))
    assert result["accepted"] is False
    assert "state_status_not_send_rejected_no_position_no_order" in result["blocking_reasons"]


def test_contract_blocks_execution_true() -> None:
    result = evaluate(state=flat_state(order_execution_performed=True))
    assert result["accepted"] is False
    assert "previous_order_execution_must_be_false" in result["blocking_reasons"]


def test_contract_blocks_crash_recovery_true() -> None:
    result = evaluate(state=flat_state(crash_recovery_required=True))
    assert result["accepted"] is False
    assert "crash_recovery_required_must_be_false" in result["blocking_reasons"]


def test_contract_blocks_automatic_retry_true() -> None:
    result = evaluate(state=flat_state(automatic_retry_allowed=True))
    assert result["accepted"] is False
    assert "automatic_retry_allowed_must_be_false" in result["blocking_reasons"]


def test_contract_blocks_retry_performed_true() -> None:
    result = evaluate(state=flat_state(retry_performed=True))
    assert result["accepted"] is False
    assert "retry_performed_must_be_false" in result["blocking_reasons"]


def test_contract_blocks_broker_tickets_present() -> None:
    for field in ("broker_order_ticket", "broker_deal_ticket", "broker_position_ticket"):
        result = evaluate(state=flat_state(**{field: 12345}))
        assert result["accepted"] is False
        assert f"{field}_must_be_empty" in result["blocking_reasons"]


def test_contract_blocks_idempotency_mismatch() -> None:
    result = evaluate(state=flat_state(idempotency_key="other"))
    assert result["accepted"] is False
    assert "idempotency_key_mismatch" in result["blocking_reasons"]


def test_contract_blocks_signal_mismatch() -> None:
    result = evaluate(state=flat_state(signal_id="other"))
    assert result["accepted"] is False
    assert "signal_id_mismatch" in result["blocking_reasons"]


def test_contract_blocks_dirty_broker_local_reconciliation() -> None:
    result = evaluate(broker_local_reconciliation=clean_reconciliation(broker_position_count_symbol=1))
    assert result["accepted"] is False
    assert "broker_local_reconciliation_not_clean_no_local_no_broker" in result["blocking_reasons"]


def test_market_closed_flat_contract_accepts_new_signal_when_broker_flat() -> None:
    result = contracts.evaluate_market_closed_reject_flat_new_signal(
        state=market_closed_state(),
        signal_id="new-signal",
        idempotency_key="new-idem",
        broker_local_reconciliation=clean_reconciliation(),
        require_broker_local_reconciliation=True,
    )

    assert result["accepted"] is True
    assert result["explicit_new_signal_after_market_closed_flat"] is True
    assert result["previous_state_status"] == "execution_rejected"
    assert result["previous_send_retcode"] == 10018
    assert result["automatic_retry_allowed"] is False
    assert result["retry_performed"] is False
    assert result["new_operator_authorized_attempt"] is False


def test_market_closed_flat_contract_blocks_same_signal_and_idempotency() -> None:
    result = contracts.evaluate_market_closed_reject_flat_new_signal(
        state=market_closed_state(signal_id=SIGNAL_ID, idempotency_key=IDEMPOTENCY_KEY),
        signal_id=SIGNAL_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        broker_local_reconciliation=clean_reconciliation(),
        require_broker_local_reconciliation=True,
    )

    assert result["accepted"] is False
    assert "new_signal_id_required" in result["blocking_reasons"]
    assert "new_idempotency_key_required" in result["blocking_reasons"]


def test_market_closed_flat_contract_blocks_dirty_reconciliation() -> None:
    result = contracts.evaluate_market_closed_reject_flat_new_signal(
        state=market_closed_state(),
        signal_id="new-signal",
        idempotency_key="new-idem",
        broker_local_reconciliation=clean_reconciliation(broker_pending_order_count_symbol=1),
        require_broker_local_reconciliation=True,
    )

    assert result["accepted"] is False
    assert "broker_local_reconciliation_not_clean_no_local_no_broker" in result["blocking_reasons"]
