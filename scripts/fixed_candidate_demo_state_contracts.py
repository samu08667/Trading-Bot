"""Shared state contracts for fixed-candidate demo signal-to-order modules.

The helpers in this module do not read files, call MT5, mutate state, or make
broker/API requests. They only evaluate already-loaded artifacts.
"""

from __future__ import annotations

from typing import Any, Mapping


CLIENT_AUTOTRADING_DISABLED_RETCODE = 10027
MARKET_CLOSED_RETCODE = 10018
CLIENT_REJECT_FLAT_STATE_STATUS = "send_rejected_no_position_no_order"
MARKET_CLOSED_REJECT_STATE_STATUS = "execution_rejected"
CLIENT_REJECT_RESEND_ACKNOWLEDGMENT = (
    "acknowledge_new_demo_send_after_client_reject_flat_no_position_no_order"
)
CLEAN_NO_LOCAL_NO_BROKER_RECONCILIATION_STATUS = "broker_local_reconciliation_clean_no_local_no_broker"
CLEAN_AFTER_REJECT_NO_BROKER_STATE_RECONCILIATION_STATUS = (
    "broker_local_reconciliation_clean_after_reject_no_broker_state"
)

ACTIVE_OR_UNRESOLVED_STATE_STATUSES = {
    "pending",
    "open",
    "active",
    "pre_send_pending",
    "send_in_progress",
    "reconciliation_hold",
    "open_reconciliation_required",
    "pending_reconciliation_required",
    "position_open",
    "request_pending",
}


def safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def bool_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value is True
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def bool_false(value: Any) -> bool:
    if isinstance(value, bool):
        return value is False
    if isinstance(value, str):
        return value.strip().lower() == "false"
    return False


def empty_ticket(value: Any) -> bool:
    return value in (None, "", 0, "0")


def state_status(state: Mapping[str, Any] | None) -> str:
    state = state or {}
    return str(state.get("state_status") or state.get("state") or state.get("status") or "").strip().lower()


def _string_equal(left: Any, right: Any) -> bool:
    return bool(left not in (None, "") and right not in (None, "") and str(left) == str(right))


def broker_local_reconciliation_clean(reconciliation: Mapping[str, Any] | None) -> bool:
    reconciliation = reconciliation or {}
    return (
        reconciliation.get("reconciliation_status") == CLEAN_NO_LOCAL_NO_BROKER_RECONCILIATION_STATUS
        and safe_int(reconciliation.get("broker_position_count_symbol")) == 0
        and safe_int(reconciliation.get("broker_pending_order_count_symbol")) == 0
    )


def _state_flat_no_broker_tickets(state: Mapping[str, Any]) -> bool:
    return (
        empty_ticket(state.get("broker_order_ticket"))
        and empty_ticket(state.get("broker_deal_ticket"))
        and empty_ticket(state.get("broker_position_ticket"))
    )


def _state_detected_flat(state: Mapping[str, Any]) -> bool:
    position_detected = state.get("broker_position_detected_after_send")
    pending_detected = state.get("broker_pending_order_detected_after_send")
    return (
        not bool_true(position_detected)
        and not bool_true(pending_detected)
        and safe_int(state.get("broker_position_count_after_send")) in (None, 0)
        and safe_int(state.get("broker_pending_order_count_after_send")) in (None, 0)
    )


def evaluate_explicit_second_demo_send_after_client_reject_flat(
    *,
    state: Mapping[str, Any] | None,
    signal_id: Any = "",
    idempotency_key: Any = "",
    module_validation_demo_execution: bool = False,
    demo_account_only: bool = True,
    allow_flag: bool = False,
    acknowledgment: str = "",
    broker_local_reconciliation: Mapping[str, Any] | None = None,
    require_broker_local_reconciliation: bool = False,
) -> dict[str, Any]:
    """Evaluate the explicit second demo-send contract after a flat client reject."""

    state = state or {}
    reconciliation = broker_local_reconciliation or {}
    blocking_reasons: list[str] = []

    previous_state_status = state_status(state)
    previous_send_retcode = safe_int(state.get("last_retcode"))
    state_shape_candidate = bool(
        previous_state_status == CLIENT_REJECT_FLAT_STATE_STATUS
        and previous_send_retcode == CLIENT_AUTOTRADING_DISABLED_RETCODE
    )

    if not module_validation_demo_execution:
        blocking_reasons.append("module_validation_demo_execution_required")
    if not demo_account_only:
        blocking_reasons.append("demo_account_only_required")
    if not allow_flag:
        blocking_reasons.append("allow_new_demo_send_after_client_reject_flat_required")
    if acknowledgment != CLIENT_REJECT_RESEND_ACKNOWLEDGMENT:
        blocking_reasons.append("client_reject_resend_acknowledgment_required")
    if previous_state_status != CLIENT_REJECT_FLAT_STATE_STATUS:
        blocking_reasons.append("state_status_not_send_rejected_no_position_no_order")
    if previous_send_retcode != CLIENT_AUTOTRADING_DISABLED_RETCODE:
        blocking_reasons.append("last_retcode_not_10027")
    if not bool_false(state.get("order_execution_performed")):
        blocking_reasons.append("previous_order_execution_must_be_false")
    if not bool_false(state.get("crash_recovery_required")):
        blocking_reasons.append("crash_recovery_required_must_be_false")
    if not bool_false(state.get("automatic_retry_allowed")):
        blocking_reasons.append("automatic_retry_allowed_must_be_false")
    if not bool_false(state.get("retry_performed")):
        blocking_reasons.append("retry_performed_must_be_false")
    if not empty_ticket(state.get("broker_order_ticket")):
        blocking_reasons.append("broker_order_ticket_must_be_empty")
    if not empty_ticket(state.get("broker_deal_ticket")):
        blocking_reasons.append("broker_deal_ticket_must_be_empty")
    if not empty_ticket(state.get("broker_position_ticket")):
        blocking_reasons.append("broker_position_ticket_must_be_empty")
    if not _string_equal(state.get("signal_id"), signal_id):
        blocking_reasons.append("signal_id_mismatch")
    if not _string_equal(state.get("idempotency_key"), idempotency_key):
        blocking_reasons.append("idempotency_key_mismatch")
    if require_broker_local_reconciliation and not broker_local_reconciliation_clean(reconciliation):
        blocking_reasons.append("broker_local_reconciliation_not_clean_no_local_no_broker")

    accepted = not blocking_reasons
    return {
        "accepted": accepted,
        "candidate": state_shape_candidate,
        "status": (
            "explicit_second_demo_send_after_client_reject_flat_accepted"
            if accepted
            else "explicit_second_demo_send_after_client_reject_flat_blocked"
        ),
        "blocking_reasons": blocking_reasons,
        "explicit_second_demo_send_after_client_reject_flat": accepted,
        "module_validation_demo_execution": bool(module_validation_demo_execution),
        "strategy_valid": False if accepted else None,
        "production_valid": False if accepted else None,
        "previous_state_status": previous_state_status,
        "previous_send_retcode": previous_send_retcode if previous_send_retcode is not None else "",
        "previous_order_execution_performed": state.get("order_execution_performed", ""),
        "previous_crash_recovery_required": state.get("crash_recovery_required", ""),
        "previous_automatic_retry_allowed": state.get("automatic_retry_allowed", ""),
        "previous_retry_performed": state.get("retry_performed", ""),
        "previous_broker_order_ticket": state.get("broker_order_ticket", ""),
        "previous_broker_deal_ticket": state.get("broker_deal_ticket", ""),
        "previous_broker_position_ticket": state.get("broker_position_ticket", ""),
        "new_operator_authorized_attempt": accepted,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "client_reject_resend_acknowledgment_valid": acknowledgment == CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        "broker_local_reconciliation_clean": broker_local_reconciliation_clean(reconciliation),
    }


def evaluate_market_closed_reject_flat_new_signal(
    *,
    state: Mapping[str, Any] | None,
    signal_id: Any = "",
    idempotency_key: Any = "",
    broker_local_reconciliation: Mapping[str, Any] | None = None,
    require_broker_local_reconciliation: bool = False,
) -> dict[str, Any]:
    """Allow a new signal after a broker-side market-closed reject confirmed flat.

    This is not a retry contract. It only accepts a different signal/idempotency
    key after the previous send had no execution evidence, no broker tickets, and
    a clean no-position/no-order reconciliation.
    """

    state = state or {}
    reconciliation = broker_local_reconciliation or {}
    blocking_reasons: list[str] = []

    previous_state_status = state_status(state)
    previous_send_retcode = safe_int(state.get("last_retcode"))
    same_signal = _string_equal(state.get("signal_id"), signal_id)
    same_key = _string_equal(state.get("idempotency_key"), idempotency_key)
    state_reconciliation_status = str(state.get("reconciliation_status") or "")
    state_shape_candidate = bool(
        previous_state_status == MARKET_CLOSED_REJECT_STATE_STATUS
        and previous_send_retcode == MARKET_CLOSED_RETCODE
    )

    if previous_state_status != MARKET_CLOSED_REJECT_STATE_STATUS:
        blocking_reasons.append("state_status_not_execution_rejected")
    if previous_send_retcode != MARKET_CLOSED_RETCODE:
        blocking_reasons.append("last_retcode_not_10018")
    if not bool_false(state.get("order_execution_performed")):
        blocking_reasons.append("previous_order_execution_must_be_false")
    if not _state_flat_no_broker_tickets(state):
        blocking_reasons.append("broker_tickets_must_be_empty")
    if not _state_detected_flat(state):
        blocking_reasons.append("previous_broker_state_must_be_flat")
    if not bool_false(state.get("automatic_retry_allowed")):
        blocking_reasons.append("automatic_retry_allowed_must_be_false")
    if not bool_false(state.get("retry_performed")):
        blocking_reasons.append("retry_performed_must_be_false")
    if same_signal:
        blocking_reasons.append("new_signal_id_required")
    if same_key:
        blocking_reasons.append("new_idempotency_key_required")
    if state_reconciliation_status != CLEAN_AFTER_REJECT_NO_BROKER_STATE_RECONCILIATION_STATUS:
        blocking_reasons.append("previous_reconciliation_status_not_clean_after_reject_no_broker_state")
    if require_broker_local_reconciliation and not broker_local_reconciliation_clean(reconciliation):
        blocking_reasons.append("broker_local_reconciliation_not_clean_no_local_no_broker")

    accepted = not blocking_reasons
    return {
        "accepted": accepted,
        "candidate": state_shape_candidate,
        "status": (
            "market_closed_reject_flat_new_signal_accepted"
            if accepted
            else "market_closed_reject_flat_new_signal_blocked"
        ),
        "blocking_reasons": blocking_reasons,
        "explicit_new_signal_after_market_closed_flat": accepted,
        "previous_state_status": previous_state_status,
        "previous_send_retcode": previous_send_retcode if previous_send_retcode is not None else "",
        "previous_reconciliation_status": state_reconciliation_status,
        "previous_order_execution_performed": state.get("order_execution_performed", ""),
        "previous_crash_recovery_required": state.get("crash_recovery_required", ""),
        "previous_automatic_retry_allowed": state.get("automatic_retry_allowed", ""),
        "previous_retry_performed": state.get("retry_performed", ""),
        "previous_broker_order_ticket": state.get("broker_order_ticket", ""),
        "previous_broker_deal_ticket": state.get("broker_deal_ticket", ""),
        "previous_broker_position_ticket": state.get("broker_position_ticket", ""),
        "same_signal_id": same_signal,
        "same_idempotency_key": same_key,
        "new_operator_authorized_attempt": False,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "broker_local_reconciliation_clean": broker_local_reconciliation_clean(reconciliation),
    }


def future_state_is_incompatible_without_explicit_client_reject_contract(
    state: Mapping[str, Any] | None,
    *,
    signal_id: Any = "",
    idempotency_key: Any = "",
) -> tuple[bool, bool]:
    """Return ``(incompatible, same_idempotency_key)`` for ordinary state gates."""

    state = state or {}
    if not state:
        return False, False
    status = state_status(state)
    same_key = _string_equal(state.get("idempotency_key"), idempotency_key)
    if status in ACTIVE_OR_UNRESOLVED_STATE_STATUSES:
        return True, same_key
    if status == CLIENT_REJECT_FLAT_STATE_STATUS:
        return True, same_key
    if same_key:
        return True, True
    if bool_true(state.get("order_execution_performed")):
        return True, same_key
    if bool_true(state.get("crash_recovery_required")):
        return True, same_key
    if bool_true(state.get("automatic_retry_allowed")) or bool_true(state.get("retry_performed")):
        return True, same_key
    if not (
        empty_ticket(state.get("broker_order_ticket"))
        and empty_ticket(state.get("broker_deal_ticket"))
        and empty_ticket(state.get("broker_position_ticket"))
    ):
        return True, same_key
    return False, same_key
