from __future__ import annotations

from pathlib import Path


EA_PATH = Path("mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderCheckDemoOnly.mq5")
DOC_PATH = Path("docs/mt5_order_check_demo_only_ea.md")


def read_ea() -> str:
    return EA_PATH.read_text(encoding="utf-8")


def test_order_check_demo_only_ea_exists() -> None:
    assert EA_PATH.exists()
    assert DOC_PATH.exists()


def test_order_check_boundary_present_without_execution_primitives() -> None:
    source = read_ea()
    assert "OrderCheck" in source
    forbidden = [
        "OrderSend",
        "OrderSendAsync",
        "PositionClose",
        "CTrade",
        "trade.Buy",
        "trade.Sell",
        "trade.PositionClose",
    ]
    for token in forbidden:
        assert token not in source


def test_required_log_files_are_declared() -> None:
    source = read_ea()
    for log_name in [
        "run_config_log.csv",
        "signal_log.csv",
        "decision_log.csv",
        "order_check_log.csv",
        "position_lifecycle_log.csv",
        "trade_transactions_log.csv",
        "reconciliation_log.csv",
    ]:
        assert log_name in source
    assert "order_send_called" in source
    assert "execution_performed" in source


def test_demo_only_inputs_and_account_gate_are_present() -> None:
    source = read_ea()
    for token in [
        "InpEnableOrderCheck",
        "InpRequireDemoAccount",
        "InpAllowLiveAccount",
        "ACCOUNT_TRADE_MODE_DEMO",
        "demo_account_required",
        "live_account_input_enabled",
    ]:
        assert token in source


def test_symbol_timeframe_and_signal_contract_are_present() -> None:
    source = read_ea()
    for token in [
        "REQUIRED_SYMBOL = \"GBPUSD\"",
        "REQUIRED_TIMEFRAME = PERIOD_M15",
        "ATR_PERIOD = 20",
        "MA_FAST_PERIOD = 20",
        "TICK_VOLUME_PERCENTILE_WINDOW = 100",
        "CLOSE_TO_MA_LOW_MID = -0.4303672057741361",
        "CLOSE_TO_MA_MID_HIGH = 0.5954421525644814",
        "TICK_VOLUME_LOW_MID = 0.14",
        "TICK_VOLUME_MID_HIGH = 0.37",
        "SL_ATR_MULTIPLIER = 1.0",
        "TP_ATR_MULTIPLIER = 1.5",
        "ORDER_TYPE_SELL",
        "TRADE_ACTION_DEAL",
    ]:
        assert token in source


def test_duplicate_protection_and_broker_state_gates_are_present() -> None:
    source = read_ea()
    for token in [
        "g_last_evaluated_bar_time",
        "g_last_order_check_bar_time",
        "duplicate_bar_skipped",
        "duplicate_order_check_block",
        "CountPositionsForCandidate",
        "CountPendingOrdersForCandidate",
        "one_position_only_block",
        "pending_order_block",
    ]:
        assert token in source


def test_friday_cutoff_metadata_and_gate_are_present() -> None:
    source = read_ea()
    for token in [
        "InpFridayLastEntryTime",
        "InpFridayForcedFlatTime",
        "FridayEntryCutoffOk",
        "FridayForcedFlatTimeIfApplicable",
        "friday_entry_cutoff_block",
        "23:15",
        "23:45",
    ]:
        assert token in source

def test_run_isolation_inputs_and_run_id_logging_are_present() -> None:
    source = read_ea()
    for token in [
        'input string InpRunId = "";',
        "InpOverwriteLogsOnInit",
        'string g_run_id = "";',
        "ResolveRunId",
        "BuildGeneratedRunId",
        "DeleteCurrentRunLogs",
        "run_config_log.csv",
        "WriteRunConfigLog",
        "ordercheck_demo_",
        r'LogFolder() { return "TradingBot\\" + InpLogPrefix + "\\" + g_run_id; }',
    ]:
        assert token in source

    assert "configured = StringTrimLeft" not in source
    assert "configured = StringTrimRight" not in source
    assert "StringTrimLeft(configured);" in source
    assert "StringTrimRight(configured);" in source
    assert "StringLen(configured) > 0" in source

    assert 'g_run_id = "0"' not in source
    assert 'return "0"' not in source
    assert "InpRunId = 0" not in source

    assert 'FileWrite(handle,"run_id","timestamp_server","candidate_id"' in source
    assert "FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),CANDIDATE_ID" in source
    assert source.count("FileWrite(handle,g_run_id,") >= 7
    assert source.count('"run_id"') >= 7


def test_order_check_log_records_block_reason() -> None:
    source = read_ea()
    assert '"block_reason"' in source
    assert "order_check_disabled" in source
    assert "WriteOrderCheckLog" in source
