from __future__ import annotations

import re
from pathlib import Path


EA_PATH = Path("mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5")
DOC_PATH = Path("docs/mt5_risk_based_position_sizing_design_packet.md")

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


def test_risk_based_sizing_inputs_default_safe() -> None:
    source = read_ea()
    for token in [
        "input bool InpUseRiskBasedSizing = false;",
        "input double InpRiskPercentPerTrade = 0.5;",
        "input double InpMaxRiskPercentPerTrade = 0.5;",
        "input double InpVolumeLots = 0.01;",
        "InpRiskPercentPerTrade <= 0.0",
        "InpRiskPercentPerTrade > InpMaxRiskPercentPerTrade",
        "MathAbs(InpMaxRiskPercentPerTrade - 0.5)",
        "sizing_risk_percent_invalid",
    ]:
        assert token in source


def test_risk_based_sizing_uses_equity_and_order_calc_profit() -> None:
    source = read_ea()
    for token in [
        "ACCOUNT_EQUITY",
        "risk_account_basis",
        "OrderCalcProfit(ORDER_TYPE_SELL",
        "loss_per_1_lot_at_sl",
        "SYMBOL_TRADE_TICK_SIZE",
        "SYMBOL_TRADE_TICK_VALUE_LOSS",
        "SYMBOL_TRADE_TICK_VALUE",
        "risk_amount_account_currency",
        "expected_tp_amount",
        "risk_reward_ratio",
    ]:
        assert token in source
    assert "1 pip = 10" not in source


def test_volume_normalization_and_policy_blocks_are_present() -> None:
    source = read_ea()
    for token in [
        "NormalizeVolumeFloorToStep",
        "MathFloor",
        "SYMBOL_VOLUME_MIN",
        "SYMBOL_VOLUME_MAX",
        "SYMBOL_VOLUME_STEP",
        "sizing_volume_below_min_lot",
        "sizing_volume_above_max_lot",
        "sizing_effective_risk_exceeds_policy",
        "sizing_tick_value_unavailable",
        "sizing_sl_distance_invalid",
        "sizing_margin_check_failed",
        "sizing_fixed_volume_used",
        "sizing_risk_based_passed",
    ]:
        assert token in source


def test_sizing_happens_before_order_check_and_send_preflight() -> None:
    source = read_ea()
    process_start = source.index("void ProcessClosedBar")
    order_check_index = source.index("OrderCheck(request, check_result)", process_start)
    sizing_index = source.index("ComputePositionSizing(snapshot, attempt_id, signal_id, \"order_check\"", process_start)
    assert sizing_index < order_check_index

    preflight_start = source.index("void EvaluateSendPreflight")
    send_index = source.index("OrderSend(preflight_request, send_result)", preflight_start)
    preflight_sizing_index = source.index("ComputePositionSizing(snapshot, attempt_id, signal_id, \"send_preflight\"", preflight_start)
    assert preflight_sizing_index < send_index

    sizing_block_index = source.index("!sizing_ok", preflight_start)
    request_block_index = source.index("!request_ok", preflight_start)
    assert sizing_block_index < request_block_index


def test_request_digest_and_logs_include_sizing_fields() -> None:
    source = read_ea()
    for token in [
        "position_sizing_log.csv",
        "WritePositionSizingHeader",
        "WritePositionSizingLog",
        "sizing_digest",
        "|sizing_mode=",
        "|risk_percent_per_trade=",
        "|risk_account_basis=",
        "|account_equity=",
        "|risk_amount=",
        "|sl_distance=",
        "|loss_per_1_lot_at_sl=",
        "|raw_risk_volume_lots=",
        "|normalized_risk_volume_lots=",
        "|effective_risk_amount=",
        "|effective_risk_percent=",
        "decision_log.csv",
        "order_check_log.csv",
        "send_preflight_log.csv",
        "order_send_log.csv",
    ]:
        assert token in source


def test_sizing_digest_is_phase_invariant_and_log_can_keep_phase() -> None:
    source = read_ea()
    start = source.index("string PositionSizingCanonical")
    end = source.index("void FinalizePositionSizingDigest", start)
    canonical_block = source[start:end]
    for forbidden in [
        "sizing_phase",
        "timestamp_server",
        "run_id",
        "attempt_id",
        "signal_id",
        "bar_time",
        "order_check",
        "send_preflight",
    ]:
        assert forbidden not in canonical_block

    for required in [
        "sizing_mode=",
        "fixed_volume_lots=",
        "risk_percent_per_trade=",
        "max_risk_percent_per_trade=",
        "risk_account_basis=",
        "account_equity=",
        "risk_amount_account_currency=",
        "entry_price=",
        "sl_price=",
        "tp_price=",
        "sl_distance_price=",
        "loss_per_1_lot_at_sl=",
        "raw_risk_volume_lots=",
        "normalized_risk_volume_lots=",
        "effective_risk_amount=",
        "effective_risk_percent=",
        "expected_tp_amount=",
        "risk_reward_ratio=",
        "sizing_status=",
        "sizing_block_reason=",
    ]:
        assert required in canonical_block

    log_start = source.index("void WritePositionSizingHeader")
    log_end = source.index("void WriteStateTransitionHeader", log_start)
    position_sizing_log_block = source[log_start:log_end]
    assert "sizing_phase" in position_sizing_log_block
    assert "|sizing_digest=" in source

def test_final_summary_sizing_counters_are_present() -> None:
    source = read_ea()
    for token in [
        "g_sizing_mode_fixed_count",
        "g_sizing_mode_risk_based_count",
        "g_sizing_risk_based_passed_count",
        "g_sizing_fixed_volume_used_count",
        "g_sizing_blocked_count",
        "g_sizing_risk_percent_invalid_count",
        "g_sizing_volume_below_min_lot_count",
        "g_sizing_volume_above_max_lot_count",
        "g_sizing_effective_risk_exceeds_policy_count",
        "g_sizing_tick_value_unavailable_count",
        "g_sizing_min_effective_risk_percent",
        "g_sizing_max_effective_risk_percent",
        "g_sizing_min_volume_lots",
        "g_sizing_max_volume_lots",
        "UpdateSizingFinalSummaryCounters",
        "run_final_summary_log.csv",
    ]:
        assert token in source


def test_lifecycle_close_surface_and_order_send_count_unchanged() -> None:
    source = read_ea()
    assert len(re.findall(r"\bOrderSend\s*\(", source)) == 2
    assert "OrderSend(preflight_request, send_result)" in source
    assert "OrderSend(close_request_before_send, close_result)" in source
    assert "close_request.volume = close_volume" in source
    assert "ComputePositionSizing" in source
    close_start = source.index("bool BuildLifecycleCloseRequest")
    close_end = source.index("void WriteIntegratedLifecycleCloseHeader", close_start)
    close_request_block = source[close_start:close_end]
    assert "ComputePositionSizing" not in close_request_block


def test_no_forbidden_primitives_retry_or_scheduler() -> None:
    source = read_ea()
    for pattern in FORBIDDEN_PATTERNS:
        assert re.search(pattern, source) is None
    lowered = source.lower()
    for forbidden in [
        "retry_performed = true",
        "automatic_retry_allowed = true",
        "while(",
        "while (",
        "scheduler",
        "daemon",
        "martingale",
        "grid",
    ]:
        assert forbidden not in lowered


def test_design_doc_exists_and_documents_half_percent_policy() -> None:
    assert DOC_PATH.exists()
    doc = DOC_PATH.read_text(encoding="utf-8")
    for token in [
        "0.5%",
        "ACCOUNT_EQUITY",
        "InpUseRiskBasedSizing = false",
        "InpRiskPercentPerTrade = 0.5",
        "InpMaxRiskPercentPerTrade = 0.5",
        "position_sizing_log.csv",
        "OrderCalcProfit",
        "sizing_effective_risk_exceeds_policy",
    ]:
        assert token in doc