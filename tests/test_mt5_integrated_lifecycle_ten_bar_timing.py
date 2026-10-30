from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path


EA_PATH = Path("mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5")
M15 = timedelta(minutes=15)


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


def mql_bar_count_adjustment(source: str) -> int:
    body = function_body(source, "IntegratedClosedBarsAfterEntry")
    formula = re.search(
        r"const\s+int\s+(?P<name>\w+)\s*=\s*entry_shift\s*-\s*current_shift"
        r"(?:\s*(?P<sign>[+-])\s*(?P<amount>\d+))?\s*;",
        body,
    )
    assert formula is not None, "Integrated lifecycle bar-count formula changed unexpectedly"
    variable = formula.group("name")
    assert re.search(
        rf"return\s+{re.escape(variable)}\s*<\s*0\s*\?\s*0\s*:\s*{re.escape(variable)}\s*;",
        body,
    )
    if formula.group("amount") is None:
        return 0
    amount = int(formula.group("amount"))
    return amount if formula.group("sign") == "+" else -amount


def m15_opens(first_open: datetime, current_open: datetime) -> list[datetime]:
    opens: list[datetime] = []
    value = first_open
    while value <= current_open:
        opens.append(value)
        value += M15
    return opens


def i_bar_shift_exact_false(available_opens: list[datetime], timestamp: datetime) -> int:
    matching_indices = [index for index, bar_open in enumerate(available_opens) if bar_open <= timestamp]
    if not matching_indices:
        return -1
    ascending_index = matching_indices[-1]
    return len(available_opens) - 1 - ascending_index


def bars_elapsed_from_ea_formula(
    source: str,
    *,
    available_opens: list[datetime],
    entry_execution_time: datetime,
    current_closed_bar_open: datetime,
) -> int:
    entry_shift = i_bar_shift_exact_false(available_opens, entry_execution_time)
    current_shift = i_bar_shift_exact_false(available_opens, current_closed_bar_open)
    if entry_shift < 0 or current_shift < 0:
        return -1
    elapsed = entry_shift - current_shift + mql_bar_count_adjustment(source)
    return max(0, elapsed)


def time_exit_due(bars_elapsed: int, max_holding_bars: int) -> bool:
    return bars_elapsed >= max_holding_bars


def test_ten_bar_timeline_closes_at_0145_and_does_not_wait_for_bar_eleven() -> None:
    source = read_ea()
    entry_bar_open = datetime(2026, 7, 8, 23, 15)
    entry_execution = entry_bar_open + timedelta(seconds=5)

    opens_at_0130 = m15_opens(datetime(2026, 7, 8, 23, 0), datetime(2026, 7, 9, 1, 30))
    after_nine = bars_elapsed_from_ea_formula(
        source,
        available_opens=opens_at_0130,
        entry_execution_time=entry_execution,
        current_closed_bar_open=datetime(2026, 7, 9, 1, 15),
    )
    assert after_nine == 9
    assert not time_exit_due(after_nine, 10)

    opens_at_0145 = m15_opens(datetime(2026, 7, 8, 23, 0), datetime(2026, 7, 9, 1, 45))
    after_ten = bars_elapsed_from_ea_formula(
        source,
        available_opens=opens_at_0145,
        entry_execution_time=entry_execution,
        current_closed_bar_open=datetime(2026, 7, 9, 1, 30),
    )
    assert after_ten == 10
    assert time_exit_due(after_ten, 10)

    opens_at_0200 = m15_opens(datetime(2026, 7, 8, 23, 0), datetime(2026, 7, 9, 2, 0))
    after_eleven = bars_elapsed_from_ea_formula(
        source,
        available_opens=opens_at_0200,
        entry_execution_time=entry_execution,
        current_closed_bar_open=datetime(2026, 7, 9, 1, 45),
    )
    assert after_eleven == 11
    assert time_exit_due(after_eleven, 10)


def test_one_bar_policy_is_due_when_the_entry_bar_first_completes() -> None:
    source = read_ea()
    entry_open = datetime(2026, 7, 8, 23, 15)
    entry_execution = entry_open + timedelta(seconds=37)

    at_entry = bars_elapsed_from_ea_formula(
        source,
        available_opens=m15_opens(datetime(2026, 7, 8, 23, 0), entry_open),
        entry_execution_time=entry_execution,
        current_closed_bar_open=datetime(2026, 7, 8, 23, 0),
    )
    assert at_entry == 0
    assert not time_exit_due(at_entry, 1)

    first_completion = bars_elapsed_from_ea_formula(
        source,
        available_opens=m15_opens(datetime(2026, 7, 8, 23, 0), datetime(2026, 7, 8, 23, 30)),
        entry_execution_time=entry_execution,
        current_closed_bar_open=entry_open,
    )
    assert first_completion == 1
    assert time_exit_due(first_completion, 1)


def test_formula_counts_available_closed_bars_instead_of_wall_clock_intervals() -> None:
    source = read_ea()
    entry_open = datetime(2026, 7, 8, 20, 0)
    offsets = [-1, 0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11]
    available_opens = [entry_open + offset * M15 for offset in offsets]

    elapsed = bars_elapsed_from_ea_formula(
        source,
        available_opens=available_opens,
        entry_execution_time=entry_open + timedelta(seconds=4),
        current_closed_bar_open=entry_open + 10 * M15,
    )

    assert elapsed == 10
    assert time_exit_due(elapsed, 10)
    assert (available_opens[-1] - entry_open) // M15 == 11


def test_missing_entry_history_keeps_bar_count_unavailable() -> None:
    source = read_ea()
    available_opens = m15_opens(datetime(2026, 7, 9, 0, 0), datetime(2026, 7, 9, 1, 0))

    assert (
        bars_elapsed_from_ea_formula(
            source,
            available_opens=available_opens,
            entry_execution_time=datetime(2026, 7, 8, 23, 15),
            current_closed_bar_open=datetime(2026, 7, 9, 0, 45),
        )
        == -1
    )


def test_mql_formula_is_inclusive_of_the_entry_bar_once_it_is_closed() -> None:
    source = read_ea()
    body = function_body(source, "IntegratedClosedBarsAfterEntry")

    assert mql_bar_count_adjustment(source) == 1
    assert "entry_shift - current_shift + 1" in body
    assert "iTime(InpSymbol, InpTimeframe, 0)" not in body


def test_lifecycle_evaluates_shift_one_on_the_first_tick_of_the_new_bar() -> None:
    source = read_ea()
    on_tick = function_body(source, 'OnTick')
    evaluation_due = function_body(source, 'IntegratedLifecycleEvaluationDue')

    assert 'const datetime closed_bar_time = iTime(InpSymbol, InpTimeframe, 1);' in on_tick
    assert 'EvaluateIntegratedLifecycleWatch(closed_bar_time);' in on_tick
    assert 'current_closed_bar_time != g_last_integrated_lifecycle_evaluated_bar_time' in evaluation_due


def test_friday_forced_flat_keeps_priority_over_time_exit() -> None:
    source = read_ea()
    body = function_body(source, "ReadIntegratedLifecycleSnapshot")

    friday_check = body.index("if(IntegratedFridayForcedFlatRequired(snapshot.timestamp_server))")
    time_exit_check = body.index("if(snapshot.bars_elapsed >= InpMaxHoldingBars)")
    assert friday_check < time_exit_check
    friday_block = body[friday_check:time_exit_check]
    assert 'snapshot.exit_reason_preview = "friday_forced_flat";' in friday_block
    assert "return;" in friday_block


def test_no_position_returns_before_bar_count_or_close_eligibility() -> None:
    source = read_ea()
    snapshot_body = function_body(source, "ReadIntegratedLifecycleSnapshot")
    no_position = snapshot_body.index("if(snapshot.matching_position_count == 0)")
    bar_count = snapshot_body.index("snapshot.bars_elapsed = IntegratedClosedBarsAfterEntry")
    no_position_block = snapshot_body[no_position:bar_count]

    assert no_position < bar_count
    assert 'snapshot.exit_reason_preview = "time_exit_10_m15_bars";' not in no_position_block
    assert "return;" in no_position_block


def test_unresolved_already_closed_and_duplicate_guards_precede_close_send() -> None:
    source = read_ea()
    body = function_body(source, "EvaluateIntegratedLifecycleClosePreflight")
    unresolved = body.index(
        'if(snapshot.position_identity_status == "unresolved_after_restart_or_external_position")'
    )
    request_build = body.index("BuildLifecycleCloseRequest(snapshot, close_request_preflight")
    already_closed = body.index("else if(fresh_snapshot.matching_position_count == 0)")
    preflight_duplicate = body.index("else if(LifecycleClosePreflightDuplicateExists(preflight_key))")
    send_duplicate = body.index("if(LifecycleCloseSendDuplicateExists(audit.lifecycle_close_attempt_id))")
    close_send = body.index("OrderSend(close_request_before_send, close_result)")

    assert unresolved < request_build
    assert already_closed < preflight_duplicate < send_duplicate < close_send
    assert "position_close_skipped_already_closed_by_broker" in body[already_closed:preflight_duplicate]
    assert "position_close_preflight_duplicate_blocked" in body[preflight_duplicate:send_duplicate]
    assert "position_close_duplicate_send_blocked" in body[send_duplicate:close_send]
