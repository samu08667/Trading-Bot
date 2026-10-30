from __future__ import annotations

import re
from pathlib import Path


DOC_PATH = Path("docs/mt5_lifecycle_demo_only_design_packet.md")
EA_PATH = Path("mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5")


def read_doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_lifecycle_design_packet_exists() -> None:
    assert DOC_PATH.exists()


def test_lifecycle_scope_and_strategy_spec_contract_are_documented() -> None:
    text = read_doc()
    for token in [
        "demo account only",
        "`GBPUSD` only",
        "`M15` only",
        "short strategy only",
        "candidate id `gbpusd_short_h10_1_5_off_hours`",
        "max_holding_bars = 10",
        "close_at_market_after_10_closed_bars_if_sl_or_tp_not_hit",
        "no_weekend_hold = true",
        "forced_friday_exit_enabled = true",
        "friday_last_entry_time_server = 23:15",
        "friday_forced_flat_time_server = 23:45",
    ]:
        assert token in text


def test_bar_counting_and_position_identity_are_defined() -> None:
    text = read_doc()
    for token in [
        "MT5 server time",
        "MqlRates.time",
        "entry_bar_time",
        "latest_closed_bar_time",
        "bars_elapsed",
        "bar_open_time > entry_bar_time",
        "position ticket",
        "original order ticket",
        "original deal ticket",
        "local `attempt_id`",
        "Broker comment",
    ]:
        assert token in text


def test_lifecycle_states_and_close_gates_are_documented() -> None:
    text = read_doc()
    for token in [
        "position_observed_open",
        "position_closed_by_tp",
        "position_closed_by_sl",
        "position_close_required_time_exit",
        "position_close_required_friday_forced_flat",
        "position_close_attempted",
        "position_close_confirmed",
        "position_close_rejected_no_retry",
        "position_close_uncertain_reconciliation_hold",
        "manual_intervention_detected",
        "broker_closed_position_detected",
        "max close attempts",
        "`1`",
        "fresh reconciliation immediately before close",
    ]:
        assert token in text


def test_close_request_retcode_and_logs_are_specified_without_implementation() -> None:
    text = read_doc()
    for token in [
        "close at market",
        "for closing a short, use the current ask price",
        "no partial close",
        "close_request_digest",
        "close_accepted_position_flat",
        "close_rejected_position_still_open",
        "close_rejected_position_already_closed",
        "market_closed",
        "trade_disabled",
        "invalid_volume",
        "price_changed_or_requote",
        "timeout_or_uncertain",
        "unknown_retcode",
        "lifecycle_watch_log.csv",
        "lifecycle_exit_decision_log.csv",
        "position_close_log.csv",
        "lifecycle_reconciliation_log.csv",
        "lifecycle_state_transition_log.csv",
        "automatic_retry_allowed",
    ]:
        assert token in text


def test_future_static_guards_and_non_goals_are_documented() -> None:
    text = read_doc()
    for token in [
        "Historical design boundary as of the standalone lifecycle design phase",
        "`17e11fe`",
        "PositionClose",
        "current integrated EA contains exactly two callable `OrderSend(` matches",
        "one entry and one lifecycle close",
        "no retry loop",
        "live account is forbidden",
        "demo account is required",
        "Friday forced flat `23:45`",
        "max holding bars `10`",
        "Lifecycle dry/watch-only",
        "Lifecycle close-preflight only",
        "Lifecycle single demo close",
        "This packet does not implement",
        "any `.mq5` code change",
    ]:
        assert token in text


def test_current_integrated_ea_has_two_reviewed_sends_and_no_forbidden_primitives() -> None:
    source = EA_PATH.read_text(encoding="utf-8")
    for pattern in [
        r"\bOrderSendAsync\s*\(",
        r"\bPositionClose\s*\(",
        r"\bCTrade\b",
        r"\btrade\.Buy\s*\(",
        r"\btrade\.Sell\s*\(",
        r"\bSleep\s*\(",
        r"\bOnTimer\s*\(",
    ]:
        assert re.search(pattern, source) is None

    assert len(re.findall(r"\bOrderSend\s*\(", source)) == 2
    assert "OrderSend(preflight_request, send_result)" in source
    assert "OrderSend(close_request_before_send, close_result)" in source
