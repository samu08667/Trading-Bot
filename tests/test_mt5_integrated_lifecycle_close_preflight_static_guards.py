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


def test_integrated_position_close_log_schema_is_present() -> None:
    source = read_ea()
    for token in [
        "integrated_position_close_log.csv",
        "WriteIntegratedLifecycleCloseHeader",
        "WriteIntegratedLifecycleCloseLog",
        "lifecycle_close_attempt_id",
        "entry_signal_id",
        "entry_attempt_id",
        "position_identity_status",
        "close_price_preview",
        "close_request_digest",
        "close_preflight_enabled",
        "close_enabled",
        "final_lifecycle_ack_valid",
        "close_preflight_status",
        "block_reason",
        "final_position_count",
        "manual_intervention_required",
        "unresolved_policy_action",
    ]:
        assert token in source


def test_close_preflight_patch_b_states_and_gates_are_present() -> None:
    source = read_ea()
    for token in [
        "position_close_preflight_not_required",
        "position_close_preflight_blocked",
        "position_close_preflight_passed_no_close",
        "position_close_preflight_duplicate_blocked",
        "position_close_preflight_passed",
        "position_close_blocked",
        "integrated_lifecycle_close_preflight_disabled",
        "confirm_single_demo_lifecycle_close_only",
        "final_lifecycle_ack_missing_or_invalid",
        "exactly_one_matching_position_required",
        "position_type_not_short",
        "position_identity_not_allowed_for_close_preflight",
        "position_identity_unresolved_manual_review_required",
        "not_called_position_identity_unresolved",
        "block_lifecycle_close",
        "fresh_reconciliation_not_clean",
        "close_price_unavailable",
        "demo_account_required",
        "live_account_forbidden",
        "terminal_trade_not_allowed",
        "expert_trade_not_allowed",
    ]:
        assert token in source


def test_close_preflight_attempt_identity_digest_and_duplicate_protection() -> None:
    source = read_ea()
    for token in [
        "LifecycleCloseAttemptCanonical",
        "LifecycleCloseAttemptId",
        "candidate_id=",
        "position_ticket=",
        "exit_reason=",
        "entry_attempt_id=",
        "run_id=",
        "phase=integrated_lifecycle_single_close",
        "lifecycle_close_attempt_digest_non_crypto_",
        "g_lifecycle_close_preflight_keys",
        "LifecycleClosePreflightDuplicateExists",
        "RememberLifecycleClosePreflightKey",
        "LifecycleClosePreflightKey",
    ]:
        assert token in source


def test_close_preflight_and_single_close_logging_markers_are_present() -> None:
    source = read_ea()
    for token in [
        "close_called=false",
        "close_attempt_count=0",
        "no_close_preflight_only",
        "audit.close_called = true",
        "audit.close_attempt_count = 1",
        "retry_performed=false",
        "automatic_retry_allowed=false",
        "position_close_attempted",
        "position_close_confirmed",
        "position_close_rejected_no_retry",
        "position_close_uncertain_reconciliation_hold",
        "position_close_duplicate_send_blocked",
        "close_request_digest_before_send",
        "close_request_unchanged_after_preflight",
        "close_result_category",
        "post_close_reconciliation_status",
        "lifecycle_close_sent",
        "lifecycle_close_result_status",
    ]:
        assert token in source

    assert "retry_performed = true" not in source
    assert "automatic_retry_allowed = true" not in source


def test_close_price_preview_uses_ask_for_short_without_broker_mutation() -> None:
    source = read_ea()
    assert "SymbolInfoDouble(InpSymbol, SYMBOL_ASK)" in source
    assert "POSITION_TYPE_SELL" in source
    assert "close_request.type = ORDER_TYPE_BUY" in source


def test_safe_defaults_and_order_send_surface_are_preserved() -> None:
    source = read_ea()
    for token in [
        "input bool InpEnableIntegratedLifecycleWatch = false;",
        "input bool InpEnableIntegratedLifecycleClosePreflight = false;",
        "input bool InpEnableIntegratedLifecycleClose = false;",
        "input string InpFinalLifecycleAcknowledgment = \"\";",
        "input int InpMaxLifecycleCloseAttempts = 1;",
        "input int InpMaxHoldingBars = 10;",
        "InpMaxLifecycleCloseAttempts != 1",
        "InpMaxHoldingBars == MAX_HOLDING_BARS",
    ]:
        assert token in source

    assert len(re.findall(r"\bOrderSend\s*\(", source)) == 2
    for pattern in FORBIDDEN_PATTERNS:
        assert re.search(pattern, source) is None


def test_no_retry_loop_scheduler_or_timer_source() -> None:
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