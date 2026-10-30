from __future__ import annotations

import re
from pathlib import Path


EA_PATH = Path("mt5_ea_prototypes/GBPUSD_FixedCandidate_LifecycleWatchDemoOnly.mq5")
DOC_PATH = Path("docs/mt5_lifecycle_watch_demo_only_ea.md")


FORBIDDEN_TOKENS = [
    "PositionClose",
    "OrderSend",
    "OrderSendAsync",
    "CTrade",
    "trade.Buy",
    "trade.Sell",
]


def read_ea() -> str:
    return EA_PATH.read_text(encoding="utf-8")


def test_lifecycle_watch_files_exist() -> None:
    assert EA_PATH.exists()
    assert DOC_PATH.exists()


def test_safe_inputs_are_present() -> None:
    source = read_ea()
    for token in [
        "InpEnableLifecycleWatch",
        "InpEnableLifecycleClosePreflight",
        "InpEnableLifecycleClose",
        "InpFinalLifecycleAcknowledgment",
        "InpMaxLifecycleCloseAttempts",
        "InpMaxHoldingBars",
        "InpRequireDemoAccount",
        "InpAllowLiveAccount",
        'InpRunId = ""',
        "InpOverwriteLogsOnInit",
        "InpLogCommonFiles",
        "InpMagicNumber = 1510152345",
        "InpFridayForcedFlatTime = \"23:45\"",
        "InpFridayLastEntryTime = \"23:15\"",
    ]:
        assert token in source


def test_required_logs_and_fields_are_present() -> None:
    source = read_ea()
    for token in [
        "run_config_log.csv",
        "lifecycle_watch_log.csv",
        "lifecycle_exit_decision_log.csv",
        "position_close_log.csv",
        "lifecycle_reconciliation_log.csv",
        "lifecycle_state_transition_log.csv",
        "position_close_preflight_passed_no_close",
        "close_called",
        "close_attempt_count",
        "retry_performed",
        "automatic_retry_allowed",
        "lifecycle_attempt_digest_non_crypto",
        "position_close_status",
    ]:
        assert token in source


def test_lifecycle_logic_markers_are_present() -> None:
    source = read_ea()
    for token in [
        "no_position_observed",
        "multiple_matching_positions_blocked",
        "entry_bar_time_unresolved",
        "bar_count_unavailable",
        "time_exit_10_m15_bars",
        "friday_forced_flat",
        "position_close_required_time_exit",
        "position_close_required_friday_forced_flat",
        "position_close_preflight_blocked",
        "POSITION_TIME",
        "iBarShift",
        "iTime",
        "POSITION_TYPE_SELL",
        "confirm_single_demo_lifecycle_close_only",
    ]:
        assert token in source


def test_no_forbidden_broker_primitives_or_entry_send_are_present() -> None:
    source = read_ea()
    for token in FORBIDDEN_TOKENS:
        assert token not in source
    assert re.search(r"\bOrderSend\s*\(", source) is None


def test_no_retry_scheduler_or_sleep_patterns_are_present() -> None:
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
    assert "retry_performed = true" not in source
    assert "automatic_retry_allowed = true" not in source


def test_safe_defaults_and_close_attempt_limit_are_enforced() -> None:
    source = read_ea()
    for token in [
        "input bool InpEnableLifecycleWatch = false;",
        "input bool InpEnableLifecycleClosePreflight = false;",
        "input bool InpEnableLifecycleClose = false;",
        "input string InpFinalLifecycleAcknowledgment = \"\";",
        "input int InpMaxLifecycleCloseAttempts = 1;",
        "input bool InpAllowLiveAccount = false;",
        "input int InpMaxHoldingBars = 10;",
        "if(InpMaxLifecycleCloseAttempts != 1)",
        "InpMaxLifecycleCloseAttempts == 1",
        "if(InpAllowLiveAccount)",
        "if(InpMaxHoldingBars != REQUIRED_MAX_HOLDING_BARS)",
    ]:
        assert token in source


def test_close_log_is_no_close_only() -> None:
    source = read_ea()
    assert '"false","0"' in source
    assert '"false","false",position_close_status' in source
    assert "position_close_attempted" not in source
