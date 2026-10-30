from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


EA_PATH = Path("mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5")


def read_ea() -> str:
    return EA_PATH.read_text(encoding="utf-8")


def function_body(source: str, function_name: str) -> str:
    signature = re.search(rf"\b{re.escape(function_name)}\s*\([^)]*\)\s*\{{", source)
    assert signature is not None, f"MQL5 function not found: {function_name}"
    open_brace = source.index("{", signature.start())
    depth = 0
    for index in range(open_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace + 1 : index]
    raise AssertionError(f"Unterminated MQL5 function: {function_name}")


@dataclass
class FreshnessModel:
    baseline: datetime | None
    last_observed: datetime | None = None
    entry_evaluations: int = 0
    order_checks: int = 0
    order_sends: int = 0
    lifecycle_observations: int = 0

    def __post_init__(self) -> None:
        if self.baseline is not None:
            self.last_observed = self.baseline

    def on_tick(
        self,
        closed_bar_time: datetime | None,
        *,
        algo_trading_enabled: bool = True,
        matching_position_exists: bool = False,
    ) -> str:
        if closed_bar_time is None:
            self.lifecycle_observations += 1
            return "entry_signal_freshness_blocked_history_unavailable"
        self.lifecycle_observations += 1
        if self.baseline is None:
            self.baseline = closed_bar_time
            self.last_observed = closed_bar_time
            return "first_tick_historical_bar_skipped"
        if closed_bar_time <= self.baseline:
            return "first_tick_historical_bar_skipped"
        if self.last_observed is not None and closed_bar_time <= self.last_observed:
            return "entry_signal_freshness_blocked_already_observed"

        self.last_observed = closed_bar_time
        self.entry_evaluations += 1
        if not algo_trading_enabled:
            return "entry_evaluated_terminal_trade_disabled"
        if matching_position_exists:
            return "entry_evaluated_one_position_only_block"
        self.order_checks += 1
        self.order_sends += 1
        return "entry_signal_freshness_passed"


def test_attach_during_bar_skips_pre_init_close_then_allows_first_new_close() -> None:
    baseline = datetime(2026, 7, 9, 22, 0)  # 22:00-22:15 was already closed at 22:22 init.
    model = FreshnessModel(baseline)

    assert model.on_tick(baseline) == "first_tick_historical_bar_skipped"
    assert model.entry_evaluations == 0
    assert model.order_checks == 0
    assert model.order_sends == 0

    first_post_init_close = datetime(2026, 7, 9, 22, 15)  # 22:15-22:30 closes.
    assert model.on_tick(first_post_init_close) == "entry_signal_freshness_passed"
    assert model.entry_evaluations == 1


def test_attach_seconds_after_close_blocks_that_pre_init_bar() -> None:
    baseline = datetime(2026, 7, 9, 22, 0)  # Init 22:15:05, bar closed at 22:15.
    model = FreshnessModel(baseline)

    assert model.on_tick(baseline) == "first_tick_historical_bar_skipped"
    assert (model.entry_evaluations, model.order_checks, model.order_sends) == (0, 0, 0)


def test_repeated_first_tick_identity_never_reprocesses_or_sends_twice() -> None:
    baseline = datetime(2026, 7, 9, 22, 0)
    new_close = datetime(2026, 7, 9, 22, 15)
    model = FreshnessModel(baseline)

    assert model.on_tick(new_close) == "entry_signal_freshness_passed"
    assert model.on_tick(new_close) == "entry_signal_freshness_blocked_already_observed"
    assert (model.entry_evaluations, model.order_checks, model.order_sends) == (1, 1, 1)


def test_algo_trading_off_advances_identity_without_deferred_send() -> None:
    baseline = datetime(2026, 7, 9, 22, 0)
    new_close = datetime(2026, 7, 9, 22, 15)
    model = FreshnessModel(baseline)

    assert model.on_tick(new_close, algo_trading_enabled=False) == "entry_evaluated_terminal_trade_disabled"
    assert (model.entry_evaluations, model.order_checks, model.order_sends) == (1, 0, 0)
    assert model.on_tick(new_close, algo_trading_enabled=True) == "entry_signal_freshness_blocked_already_observed"
    assert (model.entry_evaluations, model.order_checks, model.order_sends) == (1, 0, 0)


def test_reattach_creates_a_new_baseline_and_skips_current_history() -> None:
    old_instance = FreshnessModel(datetime(2026, 7, 9, 22, 0))
    assert old_instance.on_tick(datetime(2026, 7, 9, 22, 15)) == "entry_signal_freshness_passed"

    new_instance = FreshnessModel(datetime(2026, 7, 9, 22, 15))
    assert new_instance.on_tick(datetime(2026, 7, 9, 22, 15)) == "first_tick_historical_bar_skipped"
    assert new_instance.on_tick(datetime(2026, 7, 9, 22, 30)) == "entry_signal_freshness_passed"


def test_restart_with_position_observes_lifecycle_but_never_enters() -> None:
    baseline = datetime(2026, 7, 9, 22, 0)
    model = FreshnessModel(baseline)

    assert model.on_tick(baseline, matching_position_exists=True) == "first_tick_historical_bar_skipped"
    assert model.lifecycle_observations == 1
    assert model.on_tick(
        datetime(2026, 7, 9, 22, 15), matching_position_exists=True
    ) == "entry_evaluated_one_position_only_block"
    assert model.lifecycle_observations == 2
    assert (model.order_checks, model.order_sends) == (0, 0)


def test_history_unavailable_fails_closed_then_first_available_bar_becomes_baseline() -> None:
    model = FreshnessModel(None)

    assert model.on_tick(None) == "entry_signal_freshness_blocked_history_unavailable"
    assert model.lifecycle_observations == 1
    assert model.on_tick(datetime(2026, 7, 9, 22, 0)) == "first_tick_historical_bar_skipped"
    assert (model.entry_evaluations, model.order_checks, model.order_sends) == (0, 0, 0)


def test_day_and_weekend_boundaries_use_bar_identity_not_elapsed_minutes() -> None:
    overnight = FreshnessModel(datetime(2026, 7, 9, 23, 45))
    assert overnight.on_tick(datetime(2026, 7, 10, 0, 0)) == "entry_signal_freshness_passed"

    monday_restart = FreshnessModel(datetime(2026, 7, 10, 23, 45))
    assert monday_restart.on_tick(datetime(2026, 7, 10, 23, 45)) == "first_tick_historical_bar_skipped"
    assert monday_restart.on_tick(datetime(2026, 7, 13, 0, 0)) == "entry_signal_freshness_passed"


def test_source_establishes_baseline_before_first_tick_entry_processing() -> None:
    source = read_ea()
    on_init = function_body(source, "OnInit")
    on_tick = function_body(source, "OnTick")
    initialize = function_body(source, "InitializeEntrySignalFreshnessBaseline")
    freshness = function_body(source, "EntrySignalFreshnessPassed")

    assert "InitializeEntrySignalFreshnessBaseline();" in on_init
    assert on_init.index("ValidateChartAndInputs()") < on_init.index("InitializeEntrySignalFreshnessBaseline();")
    assert "ResetEntrySignalFreshnessState();" in initialize
    assert "iTime(InpSymbol, InpTimeframe, 1)" in initialize
    assert "closed_bar_time <= g_entry_signal_baseline_closed_bar_time" in freshness
    assert "closed_bar_time <= g_last_evaluated_bar_time" in freshness
    assert on_tick.index("EntrySignalFreshnessPassed(closed_bar_time)") < on_tick.index(
        "ProcessClosedBar(closed_bar_time)"
    )

    history_unavailable = on_tick[on_tick.index("if(closed_bar_time <= 0)") : on_tick.index(
        "if(!g_entry_signal_baseline_established)"
    )]
    assert "entry_signal_freshness_blocked" in history_unavailable
    assert "EvaluateIntegratedLifecycleWatch(0);" in history_unavailable
    assert "return;" in history_unavailable
    assert "ProcessClosedBar" not in history_unavailable
    assert "OrderCheck" not in history_unavailable
    assert "OrderSend" not in history_unavailable


def test_source_keeps_lifecycle_observation_outside_entry_freshness_gate() -> None:
    source = read_ea()
    on_tick = function_body(source, "OnTick")
    blocked = on_tick.index("if(!EntrySignalFreshnessPassed(closed_bar_time))")
    process = on_tick.index("ProcessClosedBar(closed_bar_time)")

    assert "EvaluateIntegratedLifecycleWatch(closed_bar_time)" in on_tick[blocked:process]
    assert "ProcessClosedBar(closed_bar_time)" not in on_tick[blocked:process]


def test_source_logging_and_existing_execution_guards_remain_ordered() -> None:
    source = read_ea()
    process = function_body(source, "ProcessClosedBar")
    preflight = function_body(source, "EvaluateIntegratedLifecycleClosePreflight")

    for token in [
        "entry_signal_freshness_log.csv",
        "DeleteRunLogFile(ENTRY_SIGNAL_FRESHNESS_LOG)",
        "OpenLogForAppend(ENTRY_SIGNAL_FRESHNESS_LOG, write_header)",
        "initial_baseline_established",
        "first_tick_historical_bar_skipped",
        "new_closed_bar_observed",
        "entry_signal_freshness_passed",
        "entry_signal_freshness_blocked",
    ]:
        assert token in source
    assert process.index("terminal_trade_disabled") < process.index("OrderCheck(request, check_result)")
    assert process.index("one_position_only_block") < process.index("OrderCheck(request, check_result)")
    assert preflight.index("unresolved_after_restart_or_external_position") < preflight.index(
        "BuildLifecycleCloseRequest(snapshot, close_request_preflight"
    )


def test_aud_001_and_friday_priority_are_unchanged() -> None:
    source = read_ea()
    bar_count = function_body(source, "IntegratedClosedBarsAfterEntry")
    lifecycle_snapshot = function_body(source, "ReadIntegratedLifecycleSnapshot")
    process = function_body(source, "ProcessClosedBar")

    assert "entry_shift - current_shift + 1" in bar_count
    assert lifecycle_snapshot.index("IntegratedFridayForcedFlatRequired") < lifecycle_snapshot.index(
        "snapshot.bars_elapsed >= InpMaxHoldingBars"
    )
    assert "FridayEntryCutoffOk(snapshot.bar_time)" in process
