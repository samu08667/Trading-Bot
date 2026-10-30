from __future__ import annotations

import re
from pathlib import Path


EA_PATH = Path("mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5")
DOC_PATH = Path("docs/mt5_order_send_demo_only_ea_scaffold.md")

ORDER_SEND_CALL_PATTERN = r"\bOrderSend\s*\("

FORBIDDEN_CALLABLE_PATTERNS = [
    r"\bOrderSendAsync\s*\(",
    r"\bPositionClose\s*\(",
    r"\bCTrade\b",
    r"\btrade\.Buy\s*\(",
    r"\btrade\.Sell\s*\(",
    r"\bSleep\s*\(",
]

ALLOWED_ORDER_SEND_CONFIG_TOKENS = [
    "InpEnableOrderSend",
    "InpMaxOrderSendAttempts",
    "order_send_called",
    "order_send_attempt_count",
]


def read_ea() -> str:
    return EA_PATH.read_text(encoding="utf-8")


def test_send_demo_only_scaffold_files_exist() -> None:
    assert EA_PATH.exists()
    assert DOC_PATH.exists()


def test_required_safe_inputs_are_present() -> None:
    source = read_ea()
    for token in [
        "InpEnableOrderCheck",
        "InpEnableSendPreflight",
        "InpEnableOrderSend",
        "InpFinalSendAcknowledgment",
        "InpEnableIntegratedLifecycleWatch",
        "InpEnableIntegratedLifecycleClosePreflight",
        "InpEnableIntegratedLifecycleClose",
        "InpFinalLifecycleAcknowledgment",
        "InpMaxOrderSendAttempts",
        "InpMaxLifecycleCloseAttempts",
        "InpMaxHoldingBars",
        "InpRequireDemoAccount",
        "InpAllowLiveAccount",
        'InpRunId = ""',
        "InpOverwriteLogsOnInit",
        "InpLogCommonFiles",
        "InpVolumeLots = 0.01",
        "InpUseRiskBasedSizing = false",
        "InpRiskPercentPerTrade = 0.5",
        "InpMaxRiskPercentPerTrade = 0.5",
        "InpMagicNumber = 1510152345",
        "InpMaxSpreadPoints = 15",
        'InpFridayLastEntryTime = "23:15"',
        'InpFridayForcedFlatTime = "23:45"',
    ]:
        assert token in source


def test_signal_contract_matches_validated_candidate_shape() -> None:
    source = read_ea()
    for token in [
        'CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"',
        'REQUIRED_SYMBOL = "GBPUSD"',
        "REQUIRED_TIMEFRAME = PERIOD_M15",
        "SIDE_SELL",
        "ATR_PERIOD = 20",
        "MA_FAST_PERIOD = 20",
        "TICK_VOLUME_PERCENTILE_WINDOW = 100",
        "CLOSE_TO_MA_LOW_MID = -0.4303672057741361",
        "CLOSE_TO_MA_MID_HIGH = 0.5954421525644814",
        "TICK_VOLUME_LOW_MID = 0.14",
        "TICK_VOLUME_MID_HIGH = 0.37",
        "SL_ATR_MULTIPLIER = 1.0",
        "TP_ATR_MULTIPLIER = 1.5",
        "FridayEntryCutoffOk",
        "FridayForcedFlatTimeIfApplicable",
    ]:
        assert token in source


def test_required_log_files_and_send_fields_are_present() -> None:
    source = read_ea()
    for log_name in [
        "run_config_log.csv",
        "entry_signal_freshness_log.csv",
        "signal_log.csv",
        "decision_log.csv",
        "order_check_log.csv",
        "send_preflight_log.csv",
        "order_send_log.csv",
        "position_sizing_log.csv",
        "state_transition_log.csv",
        "post_send_reconciliation_log.csv",
        "run_final_summary_log.csv",
        "trade_transactions_log.csv",
        "reconciliation_log.csv",
        "position_lifecycle_log.csv",
        "integrated_lifecycle_watch_log.csv",
        "integrated_lifecycle_exit_decision_log.csv",
        "integrated_lifecycle_reconciliation_log.csv",
        "integrated_lifecycle_state_transition_log.csv",
        "integrated_position_close_log.csv",
    ]:
        assert log_name in source

    for token in [
        "order_send_called",
        "order_send_attempt_count",
        "execution_confirmed",
        "retry_performed",
        "automatic_retry_allowed",
        "broker_ticket_expected",
        "total_order_send_attempt_count",
        "execution_confirmed_count",
        "rejected_count",
        "uncertain_count",
        "max_order_send_attempts_per_attempt",
        "lifecycle_close_called_count",
        "lifecycle_close_confirmed_count",
        "lifecycle_close_rejected_count",
        "lifecycle_close_uncertain_count",
        "lifecycle_close_skipped_already_closed_count",
        "lifecycle_close_duplicate_blocked_count",
        "lifecycle_close_time_exit_count",
        "lifecycle_close_friday_forced_flat_count",
        "lifecycle_close_unresolved_identity_blocked_count",
        "manual_intervention_required_count",
        "max_lifecycle_close_attempts_per_attempt",
        "sizing_mode_fixed_count",
        "sizing_mode_risk_based_count",
        "sizing_risk_based_passed_count",
        "sizing_fixed_volume_used_count",
        "sizing_blocked_count",
        "sizing_min_effective_risk_percent",
        "sizing_max_effective_risk_percent",
        "sizing_min_volume_lots",
        "sizing_max_volume_lots",
        "close_called",
        "close_attempt_count",
        "position_identity_status",
        "transaction_identity_status",
    ]:
        assert token in source

def test_run_config_is_initial_snapshot_and_summary_is_final_state() -> None:
    source = read_ea()
    assert "initial_run_config_snapshot" in source
    assert "WriteRunFinalSummaryLog" in source
    assert "OnDeinit" in source
    assert '"snapshot_type"' in source

    header_start = source.index("void WriteRunConfigHeader")
    header_end = source.index("void WriteRunConfigLog")
    run_config_header = source[header_start:header_end]
    assert "order_send_called" not in run_config_header
    assert "order_send_attempt_count" not in run_config_header
    assert "execution_performed" not in run_config_header


def test_state_transition_post_send_flags_are_explicit() -> None:
    source = read_ea()
    assert '"send_attempted","all_final_gates_passed","order_send",true,false' in source
    assert '"post_send_reconciliation",true,send_audit.execution_confirmed' in source


def test_summary_counts_attempts_without_run_level_send_cap() -> None:
    source = read_ea()
    assert "UpdateRunFinalSummaryCounters" in source
    assert "g_total_order_send_attempt_count += audit.order_send_attempt_count" in source
    assert "UpdateLifecycleCloseFinalSummaryCounters" in source
    assert "UpdateSizingFinalSummaryCounters" in source
    assert "max_order_send_attempts_per_attempt" in source
    assert "max_lifecycle_close_attempts_per_attempt" in source
    assert "max_order_send_attempts_per_run" not in source.lower()
    assert "single-send prototype" not in source


def test_run_final_summary_includes_lifecycle_and_sizing_counters() -> None:
    source = read_ea()
    summary_start = source.index("void WriteRunFinalSummaryHeader")
    summary_end = source.index("void WriteRunFinalSummaryLog", summary_start)
    summary_header = source[summary_start:summary_end]
    for token in [
        "lifecycle_close_called_count",
        "lifecycle_close_confirmed_count",
        "lifecycle_close_rejected_count",
        "lifecycle_close_uncertain_count",
        "lifecycle_close_skipped_already_closed_count",
        "lifecycle_close_duplicate_blocked_count",
        "lifecycle_close_time_exit_count",
        "lifecycle_close_friday_forced_flat_count",
        "lifecycle_close_unresolved_identity_blocked_count",
        "manual_intervention_required_count",
        "max_lifecycle_close_attempts_per_attempt",
        "sizing_mode_fixed_count",
        "sizing_mode_risk_based_count",
        "sizing_risk_based_passed_count",
        "sizing_fixed_volume_used_count",
        "sizing_blocked_count",
        "sizing_risk_percent_invalid_count",
        "sizing_volume_below_min_lot_count",
        "sizing_volume_above_max_lot_count",
        "sizing_effective_risk_exceeds_policy_count",
        "sizing_tick_value_unavailable_count",
        "sizing_min_effective_risk_percent",
        "sizing_max_effective_risk_percent",
        "sizing_min_volume_lots",
        "sizing_max_volume_lots",
    ]:
        assert token in summary_header

    assert "UpdateLifecycleCloseFinalSummaryCounters(snapshot,audit)" in source
    assert "UpdateSizingFinalSummaryCounters(audit)" in source



def test_integrated_lifecycle_watch_patch_a_markers_are_present() -> None:
    source = read_ea()
    for token in [
        "input bool InpEnableIntegratedLifecycleWatch = false;",
        "input bool InpEnableIntegratedLifecycleClosePreflight = false;",
        "input bool InpEnableIntegratedLifecycleClose = false;",
        "input string InpFinalLifecycleAcknowledgment = \"\";",
        "input int InpMaxLifecycleCloseAttempts = 1;",
        "input int InpMaxHoldingBars = 10;",
        "IntegratedLifecycleEvaluationDue",
        "EvaluateIntegratedLifecycleWatch",
        "integrated_lifecycle_watch_log.csv",
        "integrated_lifecycle_exit_decision_log.csv",
        "integrated_lifecycle_reconciliation_log.csv",
        "integrated_lifecycle_state_transition_log.csv",
        "integrated_position_close_log.csv",
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
        "signal_id_unresolved",
        "position_identity_status",
        "transaction_identity_status",
        "matched_confirmed_entry",
        "unresolved_after_restart_or_external_position",
        "StoreConfirmedPositionIdentity(send_audit)",
        "attempt_id_unresolved",
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
        "not_called_position_identity_unresolved",
        "block_lifecycle_close",
        "manual_intervention_required",
        "unresolved_policy_action",
        "confirm_single_demo_lifecycle_close_only",
        "lifecycle_close_attempt_digest_non_crypto_",
        "LifecycleCloseAttemptId",
        "LifecycleClosePreflightDuplicateExists",
        "RememberLifecycleClosePreflightKey",
        "no_close_preflight_only",
        "close_request_digest_before_send",
        "close_request_unchanged_after_preflight",
        "close_result_category",
        "post_close_reconciliation_status",
        "lifecycle_close_sent",
        "lifecycle_close_result_status",
        "TRADE_ACTION_DEAL",
        "ORDER_TYPE_BUY",
        "SymbolInfoDouble(InpSymbol, SYMBOL_ASK)",
        "max_lifecycle_close_attempts_must_equal_one",
        "InpMaxHoldingBars == MAX_HOLDING_BARS",
        "close_called=false",
        "close_attempt_count=0",
        "retry_performed=false",
        "automatic_retry_allowed=false",
    ]:
        assert token in source

    assert "IntegratedLifecycleSignalId" not in source
    assert "IntegratedLifecycleAttemptId" not in source
    assert "return g_last_signal_id" not in source
    assert "return g_last_attempt_id" not in source


def test_unresolved_lifecycle_position_requires_manual_review_before_close_request() -> None:
    source = read_ea()
    allowed_start = source.index("bool IntegratedLifecyclePositionIdentityAllowed")
    allowed_end = source.index("string LifecycleCloseAttemptCanonical", allowed_start)
    allowed_block = source[allowed_start:allowed_end]
    assert 'return position_identity_status == "matched_confirmed_entry";' in allowed_block
    assert 'unresolved_after_restart_or_external_position' not in allowed_block

    preflight_start = source.index("IntegratedLifecycleCloseAudit EvaluateIntegratedLifecycleClosePreflight")
    unresolved_index = source.index('snapshot.position_identity_status == "unresolved_after_restart_or_external_position"', preflight_start)
    request_index = source.index("BuildLifecycleCloseRequest(snapshot, close_request_preflight", preflight_start)
    unresolved_block = source[unresolved_index:request_index]
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


def test_trade_transaction_identity_uses_confirmed_entry_mapping() -> None:
    source = read_ea()
    for token in [
        "transaction_identity_status",
        "ResolveTradeTransactionIdentity",
        "TicketMatchesConfirmedIdentity(trans.position,g_confirmed_position_ticket)",
        "TicketMatchesConfirmedIdentity(trans.order,g_confirmed_order_ticket)",
        "TicketMatchesConfirmedIdentity(trans.deal,g_confirmed_deal_ticket)",
        "tx_signal_id",
        "tx_attempt_id",
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

def test_send_preflight_schema_and_terminal_states_are_present() -> None:
    source = read_ea()
    for token in [
        "send_preflight_passed",
        "send_preflight_blocked",
        "send_attempted",
        "send_accepted_position_open",
        "send_rejected_no_position_no_order",
        "send_uncertain_reconciliation_hold",
        "signal_detected",
        "order_check_passed",
        "order_check_required_before_send",
        "request_digest_changed_after_order_check",
        "no_send_no_broker_mutation",
        "previous_send_attempt_exists",
        "final_ack_missing_or_invalid",
        "max_order_send_attempts_must_equal_one",
    ]:
        assert token in source


def test_attempt_identity_and_non_crypto_digest_are_present() -> None:
    source = read_ea()
    for token in [
        "SignalId",
        "AttemptId",
        "signal_id=",
        "run_id=",
        "phase=send_preflight",
        "CanonicalRequestString",
        "NonCryptoDigest",
        "request_digest_non_crypto_",
        "digest_unchanged",
    ]:
        assert token in source


def test_exactly_two_order_send_calls_are_present_in_entry_and_lifecycle_close() -> None:
    source = read_ea()
    assert len(re.findall(ORDER_SEND_CALL_PATTERN, source)) == 2


def test_no_other_mq5_file_contains_order_send_call() -> None:
    for path in Path("mt5_ea_prototypes").glob("*.mq5"):
        if path == EA_PATH:
            continue
        source = path.read_text(encoding="utf-8")
        assert re.search(ORDER_SEND_CALL_PATTERN, source) is None, path


def test_no_forbidden_broker_primitives_are_present() -> None:
    source = read_ea()
    for pattern in FORBIDDEN_CALLABLE_PATTERNS:
        assert re.search(pattern, source) is None


def test_required_order_send_config_and_log_tokens_are_allowed() -> None:
    source = read_ea()
    for token in ALLOWED_ORDER_SEND_CONFIG_TOKENS:
        assert token in source


def test_no_retry_scheduler_or_timer_patterns_are_present() -> None:
    source = read_ea()
    lowered = source.lower()
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
        assert forbidden not in lowered

    order_send_index = source.index("OrderSend(")
    pre_call_window = source[max(0, order_send_index - 240):order_send_index]
    assert "for(" not in pre_call_window
    assert "for (" not in pre_call_window
    assert "while" not in pre_call_window.lower()
    assert "retry_performed = false" in source
    assert "automatic_retry_allowed = false" in source
    assert "retry_performed = true" not in source
    assert "automatic_retry_allowed = true" not in source


def test_live_account_is_forbidden_and_demo_gate_is_logged() -> None:
    source = read_ea()
    for token in [
        "ACCOUNT_TRADE_MODE_DEMO",
        "ACCOUNT_TRADE_MODE_REAL",
        "demo_account_required",
        "live_account_forbidden",
        "InpAllowLiveAccount",
        "InpRequireDemoAccount",
    ]:
        assert token in source


def test_order_check_boundary_is_optional_but_required_before_send_preflight_pass() -> None:
    source = read_ea()
    assert "OrderCheck(request, check_result)" in source
    assert "check_passed = check_called && check_result.retcode == 0" in source
    assert "order_check_required_before_send" in source

def test_single_attempt_send_enable_defaults_and_ack_are_safe() -> None:
    source = read_ea()
    for token in [
        "input bool InpEnableOrderSend = false;",
        "input string InpFinalSendAcknowledgment = \"\";",
        "input int InpMaxOrderSendAttempts = 1;",
        "input bool InpAllowLiveAccount = false;",
        "if(InpMaxOrderSendAttempts != 1)",
        "InpMaxOrderSendAttempts == 1",
        "InpFinalSendAcknowledgment",
        "confirm_single_demo_send_only",
    ]:
        assert token in source


def test_retcode_classification_and_send_result_logging_are_present() -> None:
    source = read_ea()
    for token in [
        "success_accepted",
        "client_autotrading_disabled",
        "market_closed",
        "trade_disabled",
        "invalid_volume",
        "invalid_stops",
        "price_changed_or_requote",
        "no_money_or_margin",
        "timeout_or_uncertain",
        "unknown_retcode",
        "order_send_retcode",
        "order_send_request_id",
        "post_send_reconciliation_status",
    ]:
        assert token in source
