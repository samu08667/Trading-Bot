from __future__ import annotations

import re
from pathlib import Path


EA_PATH = Path("mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5")


FORBIDDEN_PATTERNS = [
    r"\bOrderSendAsync\s*\(",
    r"\bPositionClose\b",
    r"\bCTrade\b",
    r"\btrade\.Buy\s*\(",
    r"\btrade\.Sell\s*\(",
    r"\bSleep\s*\(",
    r"\bOnTimer\s*\(",
]


def read_ea() -> str:
    return EA_PATH.read_text(encoding="utf-8")


def test_exactly_two_order_send_calls_entry_and_lifecycle_close() -> None:
    source = read_ea()
    matches = list(re.finditer(r"\bOrderSend\s*\(", source))
    assert len(matches) == 2
    assert "OrderSend(preflight_request, send_result)" in source
    assert "OrderSend(close_request_before_send, close_result)" in source


def test_lifecycle_close_raw_request_is_buy_to_close() -> None:
    source = read_ea()
    for token in [
        "BuildLifecycleCloseRequest",
        "TRADE_ACTION_DEAL",
        "ORDER_TYPE_BUY",
        "close_request.position = snapshot.position_ticket",
        "close_request.volume = close_volume",
        "close_request.price = NormalizeSymbolPrice(ask_price)",
        "close_request.magic = (ulong)InpMagicNumber",
        "close_request.comment = LIFECYCLE_CLOSE_COMMENT",
        "close_request.type_time = ORDER_TIME_GTC",
        "ResolveLifecycleCloseFillingMode",
    ]:
        assert token in source


def test_lifecycle_close_gates_and_ack_are_present() -> None:
    source = read_ea()
    for token in [
        "InpEnableIntegratedLifecycleWatch",
        "InpEnableIntegratedLifecycleClosePreflight",
        "InpEnableIntegratedLifecycleClose",
        "IntegratedFinalLifecycleAckValid",
        "confirm_single_demo_lifecycle_close_only",
        "InpMaxLifecycleCloseAttempts != 1",
        "exactly_one_matching_position_required",
        "position_type_not_short",
        "position_identity_not_allowed_for_close_preflight",
        "position_identity_unresolved_manual_review_required",
        "not_called_position_identity_unresolved",
        "block_lifecycle_close",
        "manual_intervention_required",
        "unresolved_policy_action",
        "fresh_reconciliation_not_clean",
        "position_close_preflight_passed",
        "position_close_blocked",
        "existing_lifecycle_uncertainty_hold",
    ]:
        assert token in source


def test_lifecycle_close_digest_duplicate_and_no_retry_controls() -> None:
    source = read_ea()
    for token in [
        "LifecycleCloseSendDuplicateExists",
        "RememberLifecycleCloseSentAttempt",
        "position_close_duplicate_send_blocked",
        "close_request_digest_preflight",
        "close_request_digest_before_send",
        "close_request_unchanged_after_preflight",
        "close_request_digest_changed_before_send",
        "audit.close_attempt_count = 1",
        "audit.retry_performed = false",
        "audit.automatic_retry_allowed = false",
        "retry_performed=false",
        "automatic_retry_allowed=false",
    ]:
        assert token in source
    assert "retry_performed = true" not in source
    assert "automatic_retry_allowed = true" not in source


def test_lifecycle_close_retcode_and_reconciliation_states() -> None:
    source = read_ea()
    for token in [
        "CloseRetcodeResultCategory",
        "close_success_accepted",
        "close_rejected_no_retry",
        "close_rejected_position_already_closed",
        "close_market_closed",
        "close_trade_disabled",
        "close_invalid_volume",
        "close_price_changed_or_requote",
        "close_no_money_or_margin",
        "close_timeout_or_uncertain",
        "close_unknown_retcode",
        "PostCloseReconciliationStatus",
        "FinalLifecycleCloseResultStatus",
        "position_close_attempted",
        "position_close_confirmed",
        "position_close_rejected_no_retry",
        "position_close_uncertain_reconciliation_hold",
        "position_close_skipped_already_closed_by_broker",
        "position_identity_unresolved_manual_review_required",
    ]:
        assert token in source


def test_lifecycle_close_log_fields_are_present() -> None:
    source = read_ea()
    for token in [
        "close_request_price",
        "close_result_bid",
        "close_result_ask",
        "close_result_volume",
        "post_close_reconciliation_status",
        "close_result_category",
        "close_identity_status",
        "close_request_digest_preflight",
        "close_request_digest_before_send",
        "close_request_unchanged_after_preflight",
        "lifecycle_close_sent",
        "lifecycle_close_result_status",
        "manual_intervention_required",
        "unresolved_policy_action",
    ]:
        assert token in source


def test_lifecycle_close_final_summary_counters_are_present() -> None:
    source = read_ea()
    for token in [
        "g_lifecycle_close_called_count",
        "g_lifecycle_close_confirmed_count",
        "g_lifecycle_close_rejected_count",
        "g_lifecycle_close_uncertain_count",
        "g_lifecycle_close_skipped_already_closed_count",
        "g_lifecycle_close_duplicate_blocked_count",
        "g_lifecycle_close_time_exit_count",
        "g_lifecycle_close_friday_forced_flat_count",
        "g_lifecycle_close_unresolved_identity_blocked_count",
        "g_manual_intervention_required_count",
        "UpdateLifecycleCloseFinalSummaryCounters",
        "max_lifecycle_close_attempts_per_attempt",
    ]:
        assert token in source



def test_unresolved_position_identity_is_not_close_eligible() -> None:
    source = read_ea()
    allowed_start = source.index("bool IntegratedLifecyclePositionIdentityAllowed")
    allowed_end = source.index("string LifecycleCloseAttemptCanonical", allowed_start)
    allowed_block = source[allowed_start:allowed_end]
    assert 'return position_identity_status == "matched_confirmed_entry";' in allowed_block
    assert "unresolved_after_restart_or_external_position" not in allowed_block

    preflight_start = source.index("IntegratedLifecycleCloseAudit EvaluateIntegratedLifecycleClosePreflight")
    unresolved_index = source.index('snapshot.position_identity_status == "unresolved_after_restart_or_external_position"', preflight_start)
    close_request_index = source.index("BuildLifecycleCloseRequest(snapshot, close_request_preflight", preflight_start)
    assert unresolved_index < close_request_index
    unresolved_block = source[unresolved_index:close_request_index]
    for token in [
        "position_identity_unresolved_manual_review_required",
        "not_called_position_identity_unresolved",
        "manual_review_required_unresolved_identity",
        "audit.manual_intervention_required = true",
        'audit.unresolved_policy_action = "block_lifecycle_close"',
        "WriteIntegratedLifecycleCloseLog(snapshot,audit)",
        "return audit",
    ]:
        assert token in unresolved_block

def test_no_forbidden_lifecycle_close_primitives_or_timers() -> None:
    source = read_ea()
    for pattern in FORBIDDEN_PATTERNS:
        assert re.search(pattern, source) is None
    lowered = source.lower()
    for forbidden in [
        "sleep(",
        "ontimer",
        "eventsettimer",
        "eventkilltimer",
        "while(",
        "while (",
        "scheduler",
        "daemon",
        "martingale",
        "grid",
    ]:
        assert forbidden not in lowered


def test_safe_defaults_remain() -> None:
    source = read_ea()
    for token in [
        "input bool InpEnableIntegratedLifecycleWatch = false;",
        "input bool InpEnableIntegratedLifecycleClosePreflight = false;",
        "input bool InpEnableIntegratedLifecycleClose = false;",
        "input string InpFinalLifecycleAcknowledgment = \"\";",
        "input int InpMaxLifecycleCloseAttempts = 1;",
        "input bool InpRequireDemoAccount = true;",
        "input bool InpAllowLiveAccount = false;",
    ]:
        assert token in source