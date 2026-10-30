from __future__ import annotations

import re
from pathlib import Path


DOC_PATH = Path("docs/mt5_integrated_lifecycle_order_send_design_packet.md")
ENTRY_EA_PATH = Path("mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5")
LIFECYCLE_WATCH_EA_PATH = Path(
    "mt5_ea_prototypes/GBPUSD_FixedCandidate_LifecycleWatchDemoOnly.mq5"
)


def read_doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_integrated_lifecycle_design_packet_exists() -> None:
    assert DOC_PATH.exists()
    text = read_doc()
    assert "Historical design boundary as of the integrated lifecycle roadmap" in text
    assert "`500ea4b`" in text
    assert "before Patches A, B, and C were implemented" in text


def test_architectural_motivation_is_documented() -> None:
    text = read_doc()
    for token in [
        "separate lifecycle watch EA",
        "no_position_observed",
        "same run",
        "same magic number",
        "same `signal_id` and `attempt_id`",
        "same `OnTradeTransaction` stream",
        "post-send broker state",
        "lower risk of tester/runtime mismatch",
        "entry request, order ticket, deal ticket, position ticket",
    ]:
        assert token in text


def test_scope_and_strategy_contract_are_documented() -> None:
    text = read_doc()
    for token in [
        "demo account only",
        "no live account support",
        "`GBPUSD` only",
        "`M15` only",
        "short strategy only",
        "candidate id `gbpusd_short_h10_1_5_off_hours`",
        "max_holding_bars = 10",
        "close_at_market_after_10_closed_bars_if_sl_or_tp_not_hit",
        "no_weekend_hold = true",
        "friday_last_entry_time_server = 23:15",
        "friday_forced_flat_time_server = 23:45",
    ]:
        assert token in text


def test_exit_rules_trigger_and_bar_counting_are_documented() -> None:
    text = read_doc()
    for token in [
        "Broker-side SL/TP have priority",
        "Friday at or after `23:45`",
        "No new entry may be opened Friday after `23:15`",
        "one-position-only gate remains mandatory",
        "prefer normal `OnTick` evaluation",
        "first observed tick at or after Friday",
        "do not use `Sleep`",
        "do not add an external scheduler",
        "`OnTimer` is excluded",
        "entry_bar_time = M15 bar open time containing entry_time",
        "latest_closed_bar_time = iTime(symbol, PERIOD_M15, 1)",
        "bars_elapsed = count of closed M15 bars",
        "MqlRates.time",
        "entry_bar_time_unresolved",
    ]:
        assert token in text


def test_position_identity_and_state_model_are_documented() -> None:
    text = read_doc()
    for token in [
        "symbol `GBPUSD`",
        "configured magic number",
        "`signal_id`",
        "`attempt_id`",
        "original order ticket",
        "original deal ticket",
        "position ticket",
        "Broker comment must not be the primary key",
        "position_observed_open",
        "position_closed_by_tp",
        "position_closed_by_sl",
        "position_close_required_time_exit",
        "position_close_required_friday_forced_flat",
        "position_close_preflight_blocked",
        "position_close_preflight_passed_no_close",
        "position_close_attempted",
        "position_close_confirmed",
        "position_close_rejected_no_retry",
        "position_close_uncertain_reconciliation_hold",
        "manual_intervention_detected",
        "broker_closed_position_detected",
    ]:
        assert token in text


def test_patch_roadmap_inputs_and_close_gates_are_documented() -> None:
    text = read_doc()
    for token in [
        "Patch A - Integrated Lifecycle Watch-Only",
        "Patch B - Integrated Lifecycle Close-Preflight-Only",
        "Patch C - Single Close Demo-Only",
        "InpEnableIntegratedLifecycleWatch = false",
        "InpEnableIntegratedLifecycleClosePreflight = false",
        "InpEnableIntegratedLifecycleClose = false",
        'InpFinalLifecycleAcknowledgment = ""',
        "InpMaxLifecycleCloseAttempts = 1",
        "InpMaxHoldingBars = 10",
        "InpFridayForcedFlatTime = 23:45",
        "`InpMaxLifecycleCloseAttempts == 1`",
        "no duplicate close attempt for the same position ticket and exit reason",
        "fresh reconciliation immediately before close",
    ]:
        assert token in text


def test_integrated_logging_and_entry_interaction_are_documented() -> None:
    text = read_doc()
    for token in [
        "TradingBot/gbpusd_short_h10_1_5_off_hours/<run_id>/",
        "integrated_lifecycle_watch_log.csv",
        "integrated_lifecycle_exit_decision_log.csv",
        "integrated_position_close_log.csv",
        "integrated_lifecycle_reconciliation_log.csv",
        "integrated_lifecycle_state_transition_log.csv",
        "lifecycle_close_attempt_id",
        "close_request_digest",
        "close_called",
        "close_attempt_count",
        "retry_performed",
        "automatic_retry_allowed",
        "entry must not open a new trade if a matching position is open",
        "post-send reconciliation should feed the initial lifecycle state",
        "broker-side SL/TP close",
    ]:
        assert token in text


def test_static_guard_design_and_non_goals_are_documented() -> None:
    text = read_doc()
    for token in [
        "no `PositionClose` or close-order primitive in Patch A",
        "no `PositionClose` or close-order primitive in Patch B",
        "Patch C allows exactly one lifecycle close `OrderSend(` call site",
        "the EA contains exactly two callable `OrderSend(` matches after Patch C",
        "entry `OrderSend` remains the original validated call",
        "no duplicate entry `OrderSend`",
        "no `OrderSendAsync`",
        "no `CTrade`",
        "no `trade.Buy(` and no `trade.Sell(`",
        "no retry loop",
        "no scheduler",
        "live account forbidden and demo required",
        "This packet does not implement",
        "live real-money close execution",
        "StrategySpec changes",
    ]:
        assert token in text


def test_current_mq5_execution_surface_has_two_reviewed_send_calls() -> None:
    entry_source = ENTRY_EA_PATH.read_text(encoding="utf-8")
    lifecycle_source = LIFECYCLE_WATCH_EA_PATH.read_text(encoding="utf-8")

    assert len(re.findall(r"\bOrderSend\s*\(", entry_source)) == 2
    assert "OrderSend(preflight_request, send_result)" in entry_source
    assert "OrderSend(close_request_before_send, close_result)" in entry_source
    assert re.search(r"\bOrderSend\s*\(", lifecycle_source) is None

    for path in Path("mt5_ea_prototypes").glob("*.mq5"):
        source = path.read_text(encoding="utf-8")
        for pattern in [
            r"\bOrderSendAsync\s*\(",
            r"\bPositionClose\s*\(",
            r"\bCTrade\b",
            r"\btrade\.Buy\s*\(",
            r"\btrade\.Sell\s*\(",
            r"\bSleep\s*\(",
            r"\bOnTimer\s*\(",
        ]:
            assert re.search(pattern, source) is None, path
