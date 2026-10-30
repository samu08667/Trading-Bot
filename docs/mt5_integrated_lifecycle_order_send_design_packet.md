# MT5 Integrated Lifecycle OrderSend Demo-Only Design Packet

This packet defines the lifecycle-management integration inside
`mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`.

It started as a design and audit gate. Current status:

- Patch A integrated lifecycle watch-only: implemented and statically guarded.
- Patch B integrated lifecycle close-preflight-only: implemented and statically guarded.
- Patch C integrated lifecycle single close demo-only: implemented and
  statically guarded. Tester/demo runtime evidence remains a separate
  validation boundary.

> Historical design boundary as of the integrated lifecycle roadmap
> (`500ea4b`), before Patches A, B, and C were implemented. The current EA
> surface now contains exactly two callable `OrderSend(` call sites: one entry
> and one lifecycle close.

The integrated code still does not implement `PositionClose`, does not use
`CTrade`, and does not change the validated entry `OrderSend` path. Patch C
adds exactly one reviewed raw lifecycle close `OrderSend(` call site.

## Architectural Motivation

The separate lifecycle watch EA proved useful as a scaffold, but independent
tester/runtime runs can leave it unable to observe positions created by the
entry/send EA. The observed result is repeated `no_position_observed` even when
the entry EA can create and reconcile positions in its own run.

Integrating lifecycle into `GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5` is the
preferred next architecture because it keeps lifecycle evaluation in the same
run as entry execution:

- same run and log folder;
- same magic number;
- same `signal_id` and `attempt_id`;
- same `OnTradeTransaction` stream;
- direct access to the post-send broker state already reconciled by the entry
  EA;
- lower risk of tester/runtime mismatch between entry and lifecycle modules;
- simpler correlation between entry request, order ticket, deal ticket,
  position ticket, and lifecycle exit decision.

The integrated design must preserve a direct audit chain across entry request, order ticket, deal ticket, position ticket, and lifecycle exit state.

The separate lifecycle scaffold remains a useful reference for bar counting,
watch/preflight logging, and no-close static guards. It should not be the final
runtime owner of lifecycle close behavior for this candidate.

## Current Scope

The integrated lifecycle module is implemented inside the existing demo entry EA
and remains limited to:

- demo account only;
- no live account support;
- `GBPUSD` only;
- `M15` only;
- short strategy only;
- candidate id `gbpusd_short_h10_1_5_off_hours`;
- the same configured magic number already used by the entry EA;
- one matching lifecycle-managed position at a time;
- no retry;
- no external scheduler;
- no martingale/grid;
- no multi-symbol execution.

The StrategySpec remains unchanged. This packet does not authorize production
or live trading.

## Lifecycle Rules To Integrate

The frozen lifecycle contract is:

```text
max_holding_bars = 10
timeframe = M15
exit_policy = close_at_market_after_10_closed_bars_if_sl_or_tp_not_hit
no_weekend_hold = true
forced_friday_exit_enabled = true
friday_last_entry_time_server = 23:15
friday_forced_flat_time_server = 23:45
```

Rules:

1. Broker-side SL/TP have priority. If SL or TP closes the position first, the
   integrated lifecycle code must only observe and classify the broker close.
2. If a matching position is still open after `10` closed M15 bars after entry,
   Patch C may close it at market on demo after all gates pass.
3. If server time is Friday at or after `23:45` and the position is still open,
   Patch C may force flat at market on demo after all gates pass.
4. No position may be intentionally held over the weekend.
5. No new entry may be opened Friday after `23:15` server time.
6. The existing one-position-only gate remains mandatory. Entry must remain
   blocked while a matching position exists or lifecycle state is uncertain.

If both time-exit and Friday forced-flat are true, Friday forced-flat has
operational priority because it protects the no-weekend-hold requirement. The
logged exit reason must still retain enough detail to audit that the position
was also beyond the max holding threshold when applicable.

## Evaluation Trigger

The next integrated implementation should prefer normal `OnTick` evaluation:

- evaluate lifecycle watch state at most once per newly closed M15 bar;
- evaluate Friday forced-flat on the first observed tick at or after Friday
  `23:45` server time;
- use MT5 server time only;
- do not use local wall-clock time;
- do not use `Sleep`;
- do not add an external scheduler;
- do not add artificial retry or polling loops.

`OnTimer` is excluded from the next implementation boundary to keep the first
integrated lifecycle patch aligned with the existing entry EA style. A later
review may consider `OnTimer` only as a watch trigger, not as a retry or close
loop, and only with new static guards.

## Position Identity

A lifecycle decision must correlate the open position to the entry path with
multiple identifiers:

- symbol `GBPUSD`;
- configured magic number;
- candidate id `gbpusd_short_h10_1_5_off_hours`;
- `signal_id`;
- `attempt_id`;
- original order ticket;
- original deal ticket;
- position ticket;
- broker comment, as supporting evidence only.

Broker comment must not be the primary key. It can be truncated or normalized by
the broker. The primary runtime identity is symbol, magic, candidate ownership
from local logs/state, and broker tickets observed through send result,
position reads, reconciliation, and `OnTradeTransaction`.

Patch A stores a minimal in-memory confirmed-entry mapping only after
`OrderSend` is accepted and post-send reconciliation observes an open position:

```text
confirmed_position_ticket
confirmed_entry_signal_id
confirmed_entry_attempt_id
confirmed_entry_time
confirmed_entry_bar_time
confirmed_order_ticket
confirmed_deal_ticket
```

Lifecycle watch must not use the current or last signal context as a fallback for
an already-open position. If `observed_position_ticket == confirmed_position_ticket`,
it logs `position_identity_status=matched_confirmed_entry` and uses the confirmed
entry `signal_id` and `attempt_id`. Otherwise it logs unresolved ids and
`position_identity_status=unresolved_after_restart_or_external_position`.
The current conservative hardening policy keeps unresolved positions observable
but not close-eligible: lifecycle close must block with
`position_identity_unresolved_manual_review_required`,
`not_called_position_identity_unresolved`, `manual_intervention_required=true`,
and `unresolved_policy_action=block_lifecycle_close` before building any close
request.
`OnTradeTransaction` must follow the same rule for passive transaction logs: match
`trans.position` to `confirmed_position_ticket`, then match `trans.order` and
`trans.deal` to `confirmed_order_ticket` and `confirmed_deal_ticket`. Matched
transactions use the confirmed entry `signal_id` and `attempt_id` with
`transaction_identity_status=matched_confirmed_entry`. Unmatched events with an
order/deal/position reference use unresolved ids and
`transaction_identity_status=unresolved_after_restart_or_external_event`; events
without those references use `transaction_identity_status=no_position_reference`.
It must not use the current or last signal context as a fallback.

Manual or external position changes must be classified as
`manual_intervention_detected` or `broker_closed_position_detected` when they
cannot be tied to the local lifecycle path.

## Entry Time And Bar Counting

The integrated lifecycle module must compute:

```text
entry_time
entry_bar_time
bars_elapsed
```

Preferred source order:

1. Use already-known entry/send correlation when available: accepted send audit,
   order ticket, deal ticket, position ticket, and `OnTradeTransaction` data.
2. Use current position info, including `POSITION_TIME`, as the fallback
   `entry_time`.
3. Use broker history only as a read-only improvement in a later patch if
   required for robust ticket mapping.

Bar counting rules:

```text
entry_bar_time = M15 bar open time containing entry_time
latest_closed_bar_time = iTime(symbol, PERIOD_M15, 1)
bars_elapsed = count of closed M15 bars where
  bar_open_time > entry_bar_time
  and bar_open_time <= latest_closed_bar_time
```

The entry bar itself is not counted. Only M15 bars closed after
`entry_bar_time` count. A time exit becomes eligible when
`bars_elapsed >= InpMaxHoldingBars`, with default `InpMaxHoldingBars = 10`.

All time calculations use MT5 server time and `MqlRates.time`/`iTime` bar-open
timestamps. Local wall-clock time, sleep intervals, and timer cadence must not
be used as the source of truth.

If `entry_time` or `entry_bar_time` cannot be resolved, the integrated lifecycle
preflight must block and log an exact reason such as
`entry_bar_time_unresolved` or `bar_count_unavailable`.

## Integrated State Model

Future integrated lifecycle states:

```text
position_observed_open
position_closed_by_tp
position_closed_by_sl
position_close_required_time_exit
position_close_required_friday_forced_flat
position_close_preflight_blocked
position_close_preflight_passed_no_close
position_close_attempted
position_close_confirmed
position_close_rejected_no_retry
position_close_uncertain_reconciliation_hold
manual_intervention_detected
broker_closed_position_detected
```

State meaning:

- `position_observed_open`: exactly one matching open position is present and no
  close condition is currently due.
- `position_closed_by_tp` / `position_closed_by_sl`: broker-side SL/TP closed
  the position before lifecycle time exit.
- `position_close_required_time_exit`: `bars_elapsed >= 10` and the position is
  still open.
- `position_close_required_friday_forced_flat`: server time is Friday at or
  after `23:45` and the position is still open.
- `position_close_preflight_blocked`: close preflight is disabled or a close
  gate failed.
- `position_close_preflight_passed_no_close`: Patch B gate pass with no close
  primitive.
- `position_close_attempted`: Patch C only, after one real demo close attempt.
- `position_close_confirmed`: bounded reconciliation confirms the matching
  position is flat.
- `position_close_rejected_no_retry`: close was rejected and no retry is
  allowed.
- `position_close_uncertain_reconciliation_hold`: retcode or broker state is
  inconclusive; entry must remain blocked until manual review.
- `manual_intervention_detected`: broker state changed outside the EA path.
- `broker_closed_position_detected`: position is no longer open and broker data
  indicates it closed outside the lifecycle close path.

## Patch Roadmap

### Patch A - Integrated Lifecycle Watch-Only

Status: implemented as watch-only observability in
`GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`.

- Adds lifecycle observation inside `GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`.
- Does not add `PositionClose` or any close-order primitive.
- Reuses the existing run id, log folder, magic number, `signal_id`,
  `attempt_id`, and broker reconciliation context when available.
- Logs matching position count, position ticket, entry time, `entry_bar_time`,
  `bars_elapsed`, `exit_reason_preview`, and lifecycle state.
- Stores confirmed entry identity in memory after an accepted send and post-send
  reconciliation observes an open position.
- Uses confirmed entry `signal_id` and `attempt_id` only when the observed
  `position_ticket` equals the confirmed position ticket.
- Uses `signal_id_unresolved`, `attempt_id_unresolved`, and
  `position_identity_status=unresolved_after_restart_or_external_position` after
  restart/attach or for any external/unmatched position.
- Leaves entry/send behavior unchanged; the existing one-position and
  pending-order gates remain the entry safety boundary.

### Patch B - Integrated Lifecycle Close-Preflight-Only

Status: implemented as close-preflight-only audit inside the entry/send EA.

- Adds close-preflight gates without close execution.
- Adds deterministic `lifecycle_close_attempt_id` and close request digest.
- Log `position_close_preflight_passed_no_close` only when all close gates pass.
- Keep `close_called=false`, `close_attempt_count=0`,
  `retry_performed=false`, and `automatic_retry_allowed=false`.
- Blocks if `InpEnableIntegratedLifecycleClose=true` with
  `InpEnableIntegratedLifecycleClose=true` during Patch B only; Patch C makes it actionable after all gates pass.
- Does not add `PositionClose` or any close-order primitive.

### Patch C - Single Close Demo-Only

Status: implemented as one raw lifecycle close request path inside the entry/send EA.

- Uses one additional reviewed `OrderSend(close_request, close_result)` call in the lifecycle section.
- Keeps `InpMaxLifecycleCloseAttempts = 1`.
- Allows at most one close send per `lifecycle_close_attempt_id`.
- Closes only actionable lifecycle exits: `time_exit_10_m15_bars` and `friday_forced_flat`.
- Uses `TRADE_ACTION_DEAL`, `ORDER_TYPE_BUY`, full open position volume, Ask price, position ticket, configured magic, and compatible filling mode for short-position close.
- No retry, no retry loop, no scheduler.
- Adds post-close bounded reconciliation and lifecycle close result classification.
- Stops on `position_close_uncertain_reconciliation_hold`.
## Future Inputs

Integrated lifecycle inputs default safe:

```text
InpEnableIntegratedLifecycleWatch = false
InpEnableIntegratedLifecycleClosePreflight = false
InpEnableIntegratedLifecycleClose = false
InpFinalLifecycleAcknowledgment = ""
InpMaxLifecycleCloseAttempts = 1
InpMaxHoldingBars = 10
InpFridayForcedFlatTime = 23:45
```

`InpEnableIntegratedLifecycleClose` did not authorize a close in Patch A or
Patch B. In current Patch C it becomes actionable only after watch, preflight,
acknowledgment, duplicate, identity, digest, broker-state, and reconciliation
gates pass.

`InpMaxLifecycleCloseAttempts` means one attempt per lifecycle attempt, not one
close per whole run.

## Patch C Close Gates

Before any real Patch C close, all gates must pass:

- demo account true;
- live account forbidden;
- position exists;
- position belongs to symbol, magic, and candidate;
- exactly one matching position;
- exit reason is valid: `time_exit_10_m15_bars` or `friday_forced_flat`;
- integrated close preflight enabled;
- final lifecycle acknowledgment valid;
- `InpMaxLifecycleCloseAttempts == 1`;
- no duplicate close attempt for the same position ticket and exit reason;
- no duplicate close send for the same `lifecycle_close_attempt_id`;
- terminal trade allowed;
- expert trade allowed;
- symbol trade mode permits the required close;
- fresh reconciliation immediately before close;
- no retry.

Any failed close gate must log `close_called=false`, `close_attempt_count=0`,
`retry_performed=false`, `automatic_retry_allowed=false`, and a precise
`block_reason`.

## Integrated Logging And Reconciliation Design

Logs should use the existing run isolation:

```text
TradingBot/gbpusd_short_h10_1_5_off_hours/<run_id>/
```

Future integrated lifecycle logs:

```text
integrated_lifecycle_watch_log.csv
integrated_lifecycle_exit_decision_log.csv
integrated_lifecycle_reconciliation_log.csv
integrated_lifecycle_state_transition_log.csv
```

`integrated_position_close_log.csv` is intentionally not part of Patch A. Patch B adds it as a no-close preflight artifact. Patch C extends it with close result and reconciliation fields.

Minimum `integrated_lifecycle_watch_log.csv` fields:

```text
run_id
timestamp_server
candidate_id
symbol
timeframe
magic_number
signal_id
attempt_id
position_identity_status
position_observed_open
matching_position_count
position_ticket
entry_time
entry_bar_time
current_closed_bar_time
bars_elapsed
max_holding_bars
friday_forced_flat_time
exit_reason_preview
lifecycle_status
```

Minimum `integrated_lifecycle_exit_decision_log.csv` fields:

```text
run_id
lifecycle_close_attempt_id
entry_signal_id
entry_attempt_id
candidate_id
symbol
position_ticket
position_identity_status
entry_time
entry_bar_time
current_time_server
bars_elapsed
exit_reason_preview
watch_enabled
close_preflight_enabled
integrated_close_enabled
final_lifecycle_ack_valid
decision
block_reason
```

Minimum `integrated_position_close_log.csv` fields:

```text
run_id
lifecycle_close_attempt_id
entry_signal_id
entry_attempt_id
candidate_id
symbol
position_ticket
position_identity_status
entry_time
current_time_server
bars_elapsed
exit_reason
volume
close_price_preview
close_request_digest
close_called
close_attempt_count
close_retcode
close_comment
close_deal_ticket
close_order_ticket
close_confirmed
final_position_count
retry_performed
automatic_retry_allowed
close_preflight_status
block_reason
```

Patch A and Patch B must always log `close_called=false` and
`close_attempt_count=0`.
Patch B close-preflight states are:

```text
position_close_preflight_not_required
position_close_preflight_blocked
position_close_preflight_duplicate_blocked
position_close_preflight_passed_no_close
```

Patch B computes only a close price preview. For a short position, a future market
close would buy at Ask, so the preview source is `SYMBOL_ASK`. Missing Ask blocks
with `close_price_preview_unavailable`. Patch B retcode fields are empty and
`close_comment=no_close_preflight_only`.
Patch C extends `integrated_position_close_log.csv` with:

```text
close_request_price
close_result_bid
close_result_ask
close_result_volume
post_close_reconciliation_status
close_result_category
close_identity_status
close_request_digest_preflight
close_request_digest_before_send
close_request_unchanged_after_preflight
lifecycle_close_sent
lifecycle_close_result_status
```

Close result categories are:

```text
close_success_accepted
close_rejected_no_retry
close_rejected_position_already_closed
close_market_closed
close_trade_disabled
close_invalid_volume
close_price_changed_or_requote
close_no_money_or_margin
close_timeout_or_uncertain
close_unknown_retcode
```

Minimum `integrated_lifecycle_reconciliation_log.csv` fields:

```text
run_id
timestamp_server
candidate_id
symbol
magic_number
signal_id
attempt_id
matching_position_count
pending_order_count
position_ticket
position_identity_status
position_volume
position_price_open
position_sl
position_tp
broker_state
reconciliation_status
```

Minimum `integrated_lifecycle_state_transition_log.csv` fields:

```text
run_id
timestamp_server
lifecycle_close_attempt_id
entry_signal_id
entry_attempt_id
candidate_id
symbol
position_ticket
position_identity_status
previous_state
next_state
exit_reason
source_gate
close_called
close_confirmed
manual_intervention_required
unresolved_policy_action
```

Reconciliation must be bounded and read-only in Patch A and Patch B. Patch C adds one close attempt, followed by bounded post-close reconciliation. No loop may attempt repeated broker mutations.

Patch C confirms close only when the close retcode category is `close_success_accepted` and post-close reconciliation finds no matching position and no pending-order conflict. A successful retcode with a still-open position becomes `position_close_uncertain_reconciliation_hold`. A rejected close with the position already flat becomes `position_close_skipped_already_closed_by_broker`.

## Interaction With Entry/Send

The integrated lifecycle logic must coexist with the validated entry/send path:

- entry must not open a new trade if a matching position is open;
- entry must not open a new trade if lifecycle state is
  `position_close_uncertain_reconciliation_hold`;
- lifecycle observation must not change signal calculation, feature formulas,
  bucket cutoffs, SL/TP construction, or spread policy;
- lifecycle-required close state blocks entry while the position exists;
- post-send reconciliation should feed the initial lifecycle state and
  position identity;
- `OnTradeTransaction` should passively enrich correlation for entry and
  lifecycle from confirmed entry/position/order/deal mappings, never from
  current signal context, and never trigger retry or close loops;
- a broker-side SL/TP close should release the one-position gate only after
  reconciliation confirms the matching position is flat.

If lifecycle state is uncertain, the EA should prefer blocked/no-new-entry
behavior and log the hold reason instead of trying to recover automatically.

## Static Guard Design

Future static guards must enforce:

- no `PositionClose` or close-order primitive in Patch A;
- no `PositionClose` or close-order primitive in Patch B;
- Patch C allows exactly one lifecycle close `OrderSend(` call site;
- the EA contains exactly two callable `OrderSend(` matches after Patch C: one entry and one lifecycle close;
- entry `OrderSend` remains the original validated call in `GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`;
- no duplicate entry `OrderSend`;
- no `OrderSendAsync`;
- no `CTrade` unless a later reviewed close design explicitly changes this;
- no `trade.Buy(` and no `trade.Sell(`;
- max close attempts equals `1`;
- no retry loop;
- no scheduler, `Sleep`, or timer-driven close loop;
- live account forbidden and demo required;
- safe lifecycle defaults are present;
- `close_called=false` and `close_attempt_count=0` remain invariant in Patch A
  and Patch B.

## Non-Goals

This packet does not implement:

- live trading;
- retry;
- external scheduler;
- martingale/grid;
- multi-symbol execution;
- manual state editing;
- bypassing broker reconciliation;
- live real-money close execution;
- `PositionClose` in this design packet;
- any third `OrderSend`;
- StrategySpec changes;
- signal logic changes;
- SL/TP changes;
- spread policy changes.

## Recommended Implementation Boundary

The current implementation boundary is Patch C single close demo-only inside
`GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`.

Patch C keeps entry/send unchanged, keeps demo-only gates, uses one lifecycle close send attempt per lifecycle close attempt id, and relies on bounded post-close reconciliation before confirming a close. The next review should focus on tester/demo run evidence for `time_exit_10_m15_bars` and `friday_forced_flat` close attempts.
