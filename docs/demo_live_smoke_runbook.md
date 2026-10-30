# Demo-Live Smoke Runbook

This runbook is for a supervised demo-live smoke of
`gbpusd_short_h10_1_5_off_hours` only. It is not a live-account runbook and not
an unattended demo-forward operating procedure.

## Readiness Classification

- Blocked: do not start a new supervised demo-live smoke with automatic
  entry/lifecycle before the `AUD-001` time-exit and `AUD-002` first-tick
  freshness fixes have deterministic Strategy Tester validation.
- Not OK: unattended demo-forward continuous operation.
- Not OK: real or live account trading.

`AUD-001` now has a localized code-and-test remediation in the active EA. It
counts the entry-containing bar when that bar completes after execution, but no
MT5, Strategy Tester, or new demo-live validation has been run for this patch.
`AUD-002` now has a localized code-and-test remediation: initialization records
the most recent closed-bar identity as an in-memory baseline and entry waits for
a later closed-bar identity. This does not add persistence or restart recovery.
Neither patch has new MT5, Strategy Tester, or demo-live evidence. This runbook
update is not smoke authorization; the checklist is retained for a future
supervised smoke after the remaining validation gates are closed.

Current operating policy for the smoke remains:

- `current_10_bars`
- `max_holding_bars = 10`
- Friday forced flat enabled.
- No weekend hold requirement preserved through Friday cutoff/forced flat.
- Opt-in risk sizing capped at 0.5% of `ACCOUNT_EQUITY`.

## Ten-Bar Timing Contract

`max_holding_bars = 10` means close at the first available tick after the tenth
M15 bar completion observed after entry execution. For an entry executed in the
23:15 bar, the completion timestamps are:

```text
23:30 = 1
23:45 = 2
00:00 = 3
00:15 = 4
00:30 = 5
00:45 = 6
01:00 = 7
01:15 = 8
01:30 = 9
01:45 = 10
```

At the first tick opening the 01:45 bar, the just-closed bar has open time
01:30 and the lifecycle time exit is eligible. There is no timer or scheduler;
if the first tick arrives late, evaluation occurs on that first available tick.

## Entry Freshness Contract

On each successful EA initialization, `iTime(GBPUSD, M15, 1)` establishes the
in-memory entry baseline. The stored value is the MQL5 open-time identity of the
most recent closed bar, not the wall-clock time when initialization occurred.

- A first tick carrying the baseline bar is logged as
  `first_tick_historical_bar_skipped`; it cannot reach signal evaluation,
  `OrderCheck`, or entry `OrderSend`.
- The first `closed_bar_time` strictly greater than both the baseline and the
  last observed identity can enter the normal signal and execution gates.
- If closed-bar history is unavailable, entry fails closed. The first later
  valid bar becomes the baseline and is also skipped.
- Algo Trading OFF does not create a new instance. New-bar identity continues
  to advance while terminal trade permission prevents `OrderCheck` and send, so
  re-enabling does not replay the same bar.
- Removing and reattaching the EA, terminal restart, and VPS restart create a
  fresh in-memory baseline. No durable state is recovered.

Entry freshness does not suppress lifecycle observation for an existing
position. If closed-bar history is unavailable, the lifecycle receives one
fail-closed observation with bar count unavailable; this cannot make a close
eligible. A position found after restart remains
`unresolved_after_restart_or_external_position` and cannot be closed
automatically by the lifecycle.

## MT5 Pre-Checks

Before attaching or enabling the EA:

- Confirm the account is a demo account.
- Confirm symbol `GBPUSD`.
- Confirm timeframe `M15`.
- Keep AutoTrading OFF while setting inputs and checking the environment.
- Confirm there is no open `GBPUSD` position for the candidate.
- Confirm there is no pending `GBPUSD` order for the candidate.
- Use one unique magic number for this candidate.
- Confirm no other EA instance uses the same symbol and magic number.
- Use a new `InpRunId`. This is mandatory after any CSV schema change: with
  `InpOverwriteLogsOnInit=false`, never append current-schema rows to artifacts
  created by an earlier EA version.
- Confirm current spread is reasonable for the strategy and below the policy
  limit when an actionable signal appears.

## Recommended Inputs

Use the safe defaults unless this smoke explicitly requires a gated action:

```text
InpUseRiskBasedSizing = true
InpRiskPercentPerTrade = 0.5
InpMaxRiskPercentPerTrade = 0.5
InpMaxOrderSendAttempts = 1
InpMaxLifecycleCloseAttempts = 1
InpRequireDemoAccount = true
InpAllowLiveAccount = false
InpOverwriteLogsOnInit = false
```

For an entry send, the send inputs still require the existing explicit gates:

```text
InpEnableOrderCheck = true
InpEnableSendPreflight = true
InpEnableOrderSend = true
InpFinalSendAcknowledgment = confirm_single_demo_send_only
```

For lifecycle close, the lifecycle inputs still require the existing explicit
gates:

```text
InpEnableIntegratedLifecycleWatch = true
InpEnableIntegratedLifecycleClosePreflight = true
InpEnableIntegratedLifecycleClose = true
InpFinalLifecycleAcknowledgment = confirm_single_demo_lifecycle_close_only
```

## Stop Conditions

Stop the smoke and review manually if any of these appear in logs, terminal
state, broker state, or operator observation:

- `manual_intervention_required=true`
- `unresolved_after_restart_or_external_position`
- `send_uncertain_reconciliation_hold`
- `position_close_uncertain_reconciliation_hold`
- any close status that is operationally uncertain
- `retry_performed=true`
- `automatic_retry_allowed=true`
- more than one matching position
- unexpected pending order
- effective risk above 0.5%
- account is not demo
- live account detected
- unexpected symbol, timeframe, magic, ticket, deal, or position identity
- broker/local reconciliation unavailable, mismatched, or inconclusive

Do not restart automatically from a stop condition.

## Logs To Collect

Collect the full run folder from MT5 Files/Common Files after the smoke. At
minimum, review these CSV files when present:

- `run_config_log.csv`
- `entry_signal_freshness_log.csv`
- `run_final_summary_log.csv`
- `position_sizing_log.csv`
- `order_check_log.csv`
- `send_preflight_log.csv`
- `order_send_log.csv`
- `integrated_position_close_log.csv`
- `integrated_lifecycle_watch_log.csv`
- `integrated_lifecycle_state_transition_log.csv`
- `trade_transactions_log.csv`
- `post_send_reconciliation_log.csv`
- `reconciliation_log.csv`

Treat these files as runtime artifacts. Do not commit them.

## Daily Review Checklist

For each supervised smoke day:

- Confirm `run_config_log.csv` shows demo account, expected symbol/timeframe,
  `InpRequireDemoAccount=true`, `InpAllowLiveAccount=false`, and a non-empty
  `session_instance_id`.
- Confirm final summary has `retry_performed=false` and
  `automatic_retry_allowed=false`.
- Confirm final summary position and pending-order counts match broker reality.
- Confirm freshness logs show `initial_baseline_established`, no entry processing
  for `first_tick_historical_bar_skipped`, and a strictly later identity for
  `entry_signal_freshness_passed`.
- Review sizing rows for `sizing_risk_based_passed` or an expected fixed-mode
  audit, and verify effective risk never exceeds 0.5%.
- Review order-check and send-preflight rows before trusting any send result.
- Review post-send reconciliation after every send attempt.
- Review lifecycle watch/close logs until the position is confirmed flat or a
  manual review state is reached.
- Review every `DEAL_ADD` row for `transaction_position_ticket` versus
  `deal_position_id`, `deal_time_msc`, raw/name deal type/entry/reason,
  profit and costs, `history_lookup_status`, `history_getter_status`,
  `missing_history_fields`, and `deal_event_classification`. A row marked
  `unavailable_at_callback` is retained evidence and must not be retried
  automatically; a partial getter failure leaves only the failed fields empty.
- For broker-side exits, require `DEAL_REASON_SL` or `DEAL_REASON_TP` before
  calling the exit SL/TP; matching the recorded deal price to SL/TP alone is not
  sufficient.
- Confirm final summary deal-add count equals lookup-success plus
  lookup-unavailable count for the observed callback stream.
- Record any stop condition before the next run.

## Restart Or Reattach Handling

The current EA does not provide complete persistent restart recovery. If MT5,
the terminal, or the EA restarts while a position may be open:

- Keep AutoTrading OFF initially.
- Expect the reinitialized instance to establish a new entry baseline and skip
  the first historical closed-bar identity.
- Do not enable send or lifecycle close immediately after reattach.
- First reconcile broker state manually.
- Read `integrated_lifecycle_watch_log.csv`,
  `integrated_lifecycle_state_transition_log.csv`, and
  `integrated_position_close_log.csv`.
- If identity is `unresolved_after_restart_or_external_position`, treat the
  position as manual-review only.
- Do not let the EA close an unresolved position.
- Do not open a new trade until the prior state is flat and reviewed.

The freshness baseline prevents stale entry replay only. It does not restore
the confirmed ticket/signal/attempt mapping of the prior process and therefore
does not make restart recovery complete.

This restart behavior is acceptable for supervised smoke only. It blocks
unattended demo-forward operation until persistent state and durable idempotency
exist.

## Deal Transaction Observability Contract

Each EA initialization creates one in-memory `session_instance_id`. It remains
unchanged until deinitialization and is written to `run_config_log.csv`,
`trade_transactions_log.csv`, and `run_final_summary_log.csv`. It is
practically unique per attach/restart, including when an operator reuses
`InpRunId`; this is not a mathematical uniqueness guarantee. It is
observability metadata only and is not persisted as execution state, included
in request digests, used for authorization, or used to suppress callbacks.

For `TRADE_TRANSACTION_DEAL_ADD`, the callback makes one synchronous
`HistoryDealSelect(trans.deal)` attempt:

- A successful select sets `history_lookup_status=history_select_success`,
  then uses the boolean getter overloads. Valid zero values are logged as zero;
  a failed getter leaves only its column empty and records
  `partial_getter_failure`, an error, and its property name in
  `missing_history_fields`.
- `transaction_position_ticket` comes only from `trans.position`;
  `deal_position_id` comes only from a successful `DEAL_POSITION_ID` getter.
  Neither is used as fallback for the other.
- Failure logs `history_lookup_status=unavailable_at_callback`, error
  code/text, and the fields already present in `MqlTradeTransaction`.
- There is no retry, loop, timer, sleep, or automatic lookup from a later
  transaction event.
- `MqlTradeRequest` and `MqlTradeResult` fields are read only when
  `trans.type == TRADE_TRANSACTION_REQUEST`; other callbacks use
  `request_context_status=not_applicable` and no magic-number fallback.
- `transaction_data_source` lists only sources actually consumed. It starts as
  `MqlTradeTransaction`, adds `MqlTradeRequest+MqlTradeResult` for a request
  callback, and adds `DealHistory` only after a successful deal-history select.
  A `DEAL_ADD` lookup that is unavailable therefore retains
  `MqlTradeTransaction`; `history_lookup_status=unavailable_at_callback` is the
  primary indication of that failed one-shot enrichment.

`deal_event_classification` is derived only after type, entry, and reason
getters all succeed. Incomplete core getters produce
`history_data_incomplete`; `DEAL_ENTRY_INOUT` produces `reversal_deal`;
an unknown `DEAL_TYPE` produces `unknown_deal_type`.
Expected values include `broker_stop_loss_exit`,
`broker_take_profit_exit`, `ea_or_manual_exit`, `entry_deal`,
`external_or_unknown_exit`, `non_position_deal`,
`history_lookup_unavailable`. Raw enum values remain the source evidence;
unrecognized enum values use `unknown_<numeric_value>`. Price equality with an
SL or TP is not used to classify an exit.

This patch does not capture Bid/Ask synchronized to the deal timestamp and does
not correct the known replay-versus-broker Bid/Ask mismatch.

## What Not To Do

- Do not use a real/live account.
- Do not run multiple EA instances for the same symbol and magic number.
- Do not change the magic number while a run or position is open.
- Do not change the 0.5% risk cap during a run.
- Do not bypass demo-only acknowledgments.
- Do not ignore manual intervention or unresolved identity states.
- Do not retry after a rejected or uncertain send/close.
- Do not edit runtime CSVs to make a run appear clean.
- Do not commit runtime state, logs, reports, MT5 exports, or Graphify output.

## Out Of Scope

This runbook does not implement persistent state, restart recovery, durable
idempotency, new EA features, strategy changes, exit-policy changes, EA refactor,
or Graphify refresh.
