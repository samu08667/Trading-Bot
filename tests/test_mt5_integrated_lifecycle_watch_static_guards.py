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
]


def read_ea() -> str:
    return EA_PATH.read_text(encoding="utf-8")


def test_integrated_lifecycle_watch_inputs_and_logs_are_present() -> None:
    source = read_ea()
    for token in [
        "InpEnableIntegratedLifecycleWatch",
        "InpEnableIntegratedLifecycleClosePreflight",
        "InpEnableIntegratedLifecycleClose",
        "InpFinalLifecycleAcknowledgment",
        "InpMaxLifecycleCloseAttempts",
        "InpMaxHoldingBars",
        "integrated_lifecycle_watch_log.csv",
        "integrated_lifecycle_exit_decision_log.csv",
        "integrated_lifecycle_reconciliation_log.csv",
        "integrated_lifecycle_state_transition_log.csv",
        "integrated_position_close_log.csv",
        "position_identity_status",
        "transaction_identity_status",
        "manual_intervention_required",
        "unresolved_policy_action",
    ]:
        assert token in source


def test_integrated_lifecycle_watch_only_states_are_present() -> None:
    source = read_ea()
    for token in [
        "integrated_lifecycle_watch_disabled",
        "no_position_observed",
        "position_observed_open",
        "position_close_required_time_exit_watch_only",
        "position_close_required_friday_forced_flat_watch_only",
        "multiple_matching_positions_blocked",
        "entry_bar_time_unresolved",
        "bar_count_unavailable",
        "time_exit_10_m15_bars",
        "friday_forced_flat",
        "position_close_preflight_not_required",
        "position_close_preflight_blocked",
        "position_close_preflight_passed_no_close",
        "position_close_preflight_duplicate_blocked",
        "position_close_preflight_passed",
        "position_close_blocked",
        "position_close_attempted",
        "position_close_confirmed",
        "position_close_rejected_no_retry",
        "position_close_uncertain_reconciliation_hold",
        "position_close_duplicate_send_blocked",
        "position_identity_unresolved_manual_review_required",
        "matched_confirmed_entry",
        "unresolved_after_restart_or_external_position",
    ]:
        assert token in source



def test_integrated_lifecycle_uses_confirmed_position_identity_mapping() -> None:
    source = read_ea()
    for token in [
        "g_confirmed_position_ticket",
        "g_confirmed_entry_signal_id",
        "g_confirmed_entry_attempt_id",
        "g_confirmed_entry_time",
        "g_confirmed_entry_bar_time",
        "g_confirmed_order_ticket",
        "g_confirmed_deal_ticket",
        "StoreConfirmedPositionIdentity(send_audit)",
        "snapshot.position_ticket == g_confirmed_position_ticket",
        "snapshot.signal_id = g_confirmed_entry_signal_id",
        "snapshot.attempt_id = g_confirmed_entry_attempt_id",
        "position_identity_status",
        "transaction_identity_status",
        "matched_confirmed_entry",
        "unresolved_after_restart_or_external_position",
    ]:
        assert token in source

    assert "IntegratedLifecycleSignalId" not in source
    assert "IntegratedLifecycleAttemptId" not in source
    assert "return g_last_signal_id" not in source
    assert "return g_last_attempt_id" not in source


def test_trade_transaction_logging_does_not_fallback_to_current_signal_context() -> None:
    source = read_ea()
    for token in [
        "transaction_identity_status",
        "ResolveTradeTransactionIdentity",
        "TicketMatchesConfirmedIdentity(trans.position,g_confirmed_position_ticket)",
        "TicketMatchesConfirmedIdentity(trans.order,g_confirmed_order_ticket)",
        "TicketMatchesConfirmedIdentity(trans.deal,g_confirmed_deal_ticket)",
        "matched_confirmed_entry",
        "unresolved_after_restart_or_external_event",
        "no_position_reference",
    ]:
        assert token in source

    start = source.index("void WriteTradeTransactionLog")
    end = source.index("void WriteReconciliationHeader", start)
    trade_transaction_log = source[start:end]
    assert "g_last_signal_id" not in trade_transaction_log
    assert "g_last_attempt_id" not in trade_transaction_log

def test_integrated_lifecycle_close_defaults_safe_and_never_retries() -> None:
    source = read_ea()
    assert "close_called=false" in source
    assert "close_attempt_count=0" in source
    assert "retry_performed=false" in source
    assert "automatic_retry_allowed=false" in source
    assert "retry_performed = true" not in source
    assert "automatic_retry_allowed = true" not in source
    assert "InpEnableIntegratedLifecycleClose = false" in source


def test_integrated_lifecycle_preserves_entry_execution_surface() -> None:
    source = read_ea()
    assert len(re.findall(r"\bOrderSend\s*\(", source)) == 2
    for pattern in FORBIDDEN_PATTERNS:
        assert re.search(pattern, source) is None


def test_integrated_lifecycle_no_obvious_loop_or_timer_source() -> None:
    source = read_ea().lower()
    for forbidden in [
        "ontimer",
        "eventsettimer",
        "eventkilltimer",
        "sleep(",
        "while(",
        "while (",
        "scheduler",
        "daemon",
        "martingale",
        "grid",
    ]:
        assert forbidden not in source