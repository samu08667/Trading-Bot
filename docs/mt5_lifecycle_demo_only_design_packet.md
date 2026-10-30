# MT5 Lifecycle Demo-Only Design Packet

This historical design packet defined the future lifecycle-management phase for
`gbpusd_short_h10_1_5_off_hours` after the demo-only entry EA has already opened
a position. It is a design gate only. It does not implement `PositionClose`, does
not modify any `.mq5` file, and does not authorize live trading.

Current status: the separate design was superseded operationally by integrated
lifecycle work inside `GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`. Patch A
watch-only, Patch B close-preflight-only, and Patch C single close demo-only are
now implemented and statically guarded in the integrated EA. Tester/demo runtime
evidence remains a separate validation boundary. This document remains useful
as historical design context, not as the current runtime boundary.

> Historical design boundary as of the standalone lifecycle design phase
> (`17e11fe`). At that boundary this packet specified future watch, preflight,
> and close behavior without changing an `.mq5` file. The current EA surface now
> contains exactly two callable `OrderSend(` call sites: one entry and one
> lifecycle close.

## 1. Scope

Lifecycle management is separate from entry signal generation and entry
execution. The future lifecycle component watches and, in a later approved
patch, may close an already-open position created by the demo-only entry EA.

Scope is intentionally narrow:

- demo account only;
- `GBPUSD` only;
- `M15` only;
- short strategy only;
- candidate id `gbpusd_short_h10_1_5_off_hours`;
- configured magic number only;
- one matching position lifecycle at a time;
- no live-account support;
- no entry signal changes;
- no StrategySpec changes.

Historical note: the original boundary kept
`GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5` as entry-only until lifecycle
review passed. That review has passed, and lifecycle close is now integrated in
Patch C with one raw demo-only lifecycle `OrderSend` call.

## 2. Exit Rules

The lifecycle rules come from the frozen StrategySpec:

```text
max_holding_bars = 10
timeframe = M15
exit_policy = close_at_market_after_10_closed_bars_if_sl_or_tp_not_hit
no_weekend_hold = true
forced_friday_exit_enabled = true
friday_last_entry_time_server = 23:15
friday_forced_flat_time_server = 23:45
```

Exit priority:

1. Broker-side SL/TP have priority. If SL or TP closes the position first, the
   lifecycle module must only observe and classify the close.
2. If the position is still open after `10` closed M15 bars after entry, the
   future lifecycle module must close at market.
3. If it is Friday `23:45` server time and the position is still open, the
   future lifecycle module must close at market.
4. No position may be intentionally held over the weekend.
5. New entries remain forbidden after Friday `23:15` server time; this is an
   entry gate, not a lifecycle close trigger.

If both time-exit and Friday forced-flat are true, Friday forced-flat has
operational priority because it protects the no-weekend-hold requirement. The
state/logs should still preserve that max-holding was also satisfied if both
conditions are observed.

## 3. Bar Counting And Server Time

All lifecycle timing uses MT5 server time. Do not use local wall-clock time,
workstation time, `Sleep`, timers, or tick intervals as the primary source of
truth for bar age.

MQL5 `MqlRates.time` is the M15 bar-open timestamp. The lifecycle module must
derive `entry_bar_time` as the M15 bar-open time containing the position entry
time or, if available and more reliable, from the entry signal bar recorded by
the entry EA.

Recommended rule:

```text
entry_bar_time = M15 bar open time containing position entry_time
latest_closed_bar_time = iTime(symbol, PERIOD_M15, 1)
bars_elapsed = count of closed M15 bars with
  bar_open_time > entry_bar_time
  and bar_open_time <= latest_closed_bar_time
```

The entry bar itself is not counted. The first counted bar is the next M15 bar
that has closed after the entry bar. A time-exit is eligible when
`bars_elapsed >= 10` and the position is still open.

If the EA starts after a position already exists, it must reconstruct
`entry_bar_time` from broker position/deal history when available. If identity
or entry timing cannot be reconstructed safely, it must log an uncertain hold
and must not close automatically.

## 4. Position Identity

A future close decision must correlate the observed position using multiple
keys:

- symbol `GBPUSD`;
- magic number for `gbpusd_short_h10_1_5_off_hours`;
- candidate id in local logs/state;
- position ticket;
- original order ticket when available;
- original deal ticket when available;
- local `attempt_id` from the entry EA when available;
- broker comment when available.

Broker comment is useful audit metadata, but it is not sufficient by itself.
The lifecycle module must not close a position if symbol/magic/candidate
identity is ambiguous.

## 5. Lifecycle State Model

Required states:

```text
position_observed_open
position_closed_by_tp
position_closed_by_sl
position_close_required_time_exit
position_close_required_friday_forced_flat
position_close_attempted
position_close_confirmed
position_close_rejected_no_retry
position_close_uncertain_reconciliation_hold
manual_intervention_detected
broker_closed_position_detected
```

State interpretation:

- `position_observed_open`: a matching open position is present and no close
  trigger is currently active.
- `position_closed_by_tp` / `position_closed_by_sl`: broker history or
  transaction data indicates SL/TP closed the position.
- `position_close_required_time_exit`: `bars_elapsed >= 10` and the position is
  still open.
- `position_close_required_friday_forced_flat`: Friday server time is at or
  after `23:45` and the position is still open.
- `position_close_attempted`: one close request has been sent in a future
  implementation.
- `position_close_confirmed`: bounded reconciliation confirms no matching
  position remains.
- `position_close_rejected_no_retry`: broker rejected and the position remains
  open; no retry is allowed.
- `position_close_uncertain_reconciliation_hold`: retcode or broker state is
  inconclusive; human review required.
- `manual_intervention_detected`: position state changed in a way not
  attributable to the EA.
- `broker_closed_position_detected`: the position is no longer open and broker
  history indicates it closed outside the lifecycle close path.

## 6. Future Close Gates

Before any future close request, all gates must pass:

- demo account is true;
- live account is forbidden and `InpAllowLiveAccount=false`;
- a matching position exists;
- position belongs to `GBPUSD`, configured magic, and candidate id;
- position side is consistent with the short strategy;
- no duplicate close attempt exists for the same position ticket and
  `exit_reason`;
- `exit_reason` is one of `time_exit` or `friday_forced_flat`;
- `InpMaxPositionCloseAttempts` or equivalent max close attempts input equals
  `1`;
- no retry is allowed;
- terminal trading is allowed;
- expert trading is allowed;
- symbol trade mode permits a market close;
- spread/slippage sanity checks are acceptable for a market close;
- final lifecycle acknowledgment is valid, if explicit acknowledgment is kept;
- fresh reconciliation immediately before close confirms the same position is
  still open.

Any failed gate must log `close_called=false`, `close_attempt_count=0`,
`retry_performed=false`, `automatic_retry_allowed=false`, and an exact
`block_reason`.

## 7. Close Request Design

This section specifies the future payload only; it does not implement it.

Close behavior:

- close at market;
- close the full open volume;
- no partial close unless a later design explicitly approves partial closes;
- use an opposite-side market deal for the open short position;
- for closing a short, use the current ask price;
- normalize volume to symbol step and verify it equals the open position volume;
- use conservative deviation;
- use configured magic number;
- use broker-safe comment text;
- choose a symbol-compatible `type_filling`;
- do not open, reverse, hedge, or scale the position.

The future implementation may use a raw `MqlTradeRequest` close-by-opposite-deal
pattern or a direct platform close primitive only in the lifecycle-specific
file approved by static guards. The entry EA must not gain close primitives.

The close request digest must be deterministic from canonical fields:

```text
candidate_id
symbol
position_ticket
entry_time
exit_reason
volume
close_price
deviation
magic
comment
type_filling
```

A non-cryptographic digest is acceptable for local equality/audit checks if it
is clearly named as non-cryptographic.

## 8. Retcode And Reconciliation

Every close result must be classified without retry:

| category | close_confirmed | retry_allowed | reconciliation behavior | final state |
| --- | --- | --- | --- | --- |
| `close_accepted_position_flat` | true | false | verify no matching position remains and log close order/deal tickets | `position_close_confirmed` |
| `close_rejected_position_still_open` | false | false | verify matching position remains open | `position_close_rejected_no_retry` |
| `close_rejected_position_already_closed` | true | false | verify position was already flat and classify broker/manual close if possible | `broker_closed_position_detected` |
| `market_closed` | false | false | verify matching position remains open, stop | `position_close_rejected_no_retry` |
| `trade_disabled` | false | false | verify matching position remains open, stop | `position_close_rejected_no_retry` |
| `invalid_volume` | false | false | verify matching position remains open, stop | `position_close_rejected_no_retry` |
| `price_changed_or_requote` | false | false | verify matching position remains open, stop | `position_close_rejected_no_retry` |
| `timeout_or_uncertain` | unknown | false | bounded reconciliation by position ticket, order, deal, symbol, magic | `position_close_uncertain_reconciliation_hold` |
| `unknown_retcode` | unknown | false | bounded reconciliation; hold if not conclusive | `position_close_uncertain_reconciliation_hold` |

`retry_allowed=false` for every category. A true return from a close call is not
close confirmation by itself. Confirmation requires retcode classification plus
bounded reconciliation.

Bounded reconciliation:

- read positions by symbol and magic;
- match position ticket when available;
- read relevant order/deal history if available;
- use a fixed small number of observations or a single snapshot if that matches
  the implementation style;
- no infinite loops;
- no automatic retry;
- if state is inconclusive, move to `position_close_uncertain_reconciliation_hold`.

## 9. Logging

Future lifecycle logs must be separate from entry logs:

```text
lifecycle_watch_log.csv
lifecycle_exit_decision_log.csv
position_close_log.csv
lifecycle_reconciliation_log.csv
lifecycle_state_transition_log.csv
```

Minimum `lifecycle_watch_log.csv` fields:

```text
run_id
timestamp_server
candidate_id
symbol
position_detected
position_ticket
entry_time
entry_bar_time
current_time_server
latest_closed_bar_time
bars_elapsed
max_holding_bars
friday_forced_flat_time_server
position_volume
position_price_open
position_sl
position_tp
watch_status
```

Minimum `lifecycle_exit_decision_log.csv` fields:

```text
run_id
lifecycle_attempt_id
original_attempt_id
candidate_id
symbol
position_ticket
entry_time
current_time_server
bars_elapsed
exit_reason
demo_account_ok
live_account_forbidden_ok
position_identity_ok
duplicate_close_attempt_exists
max_close_attempts_ok
trade_allowed_ok
fresh_reconciliation_ok
decision
block_reason
```

Minimum `position_close_log.csv` fields:

```text
run_id
lifecycle_attempt_id
original_attempt_id
candidate_id
symbol
position_ticket
entry_time
current_time_server
bars_elapsed
exit_reason
volume
close_price
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
```

Minimum `lifecycle_reconciliation_log.csv` fields:

```text
run_id
lifecycle_attempt_id
timestamp_server
candidate_id
symbol
position_ticket
position_count
pending_order_count
final_broker_state
observed_close_deal_ticket
observed_close_order_ticket
manual_intervention_detected
reconciliation_status
```

Minimum `lifecycle_state_transition_log.csv` fields:

```text
run_id
timestamp_server
lifecycle_attempt_id
original_attempt_id
candidate_id
symbol
position_ticket
previous_state
next_state
exit_reason
source_gate
close_called
close_confirmed
```

## 10. Static Guard Design

Historical static-guard plan:

- `PositionClose` remains forbidden;
- the current integrated EA contains exactly two callable `OrderSend(` matches:
  one entry and one lifecycle close;
- no extra `OrderSend(` appears outside the reviewed entry/lifecycle call sites;
- no `OrderSendAsync`;
- no `CTrade`, unless a later reviewed lifecycle design explicitly allows it;
- no `trade.Buy(` or `trade.Sell(`;
- no retry loop, scheduler, watcher daemon, `Sleep`, `OnTimer`, or timer-driven
  close source;
- max close attempts equals `1`;
- live account is forbidden;
- demo account is required;
- Friday forced flat `23:45` is present;
- max holding bars `10` is present;
- lifecycle logs are present;
- `retry_performed=false` and `automatic_retry_allowed=false` remain invariant.

Static scans must distinguish safe documentation/config/log tokens from callable
broker mutation primitives. Design documents may mention `PositionClose`; `.mq5`
files must not contain it until the lifecycle implementation patch is approved.

## 11. Future Runbook

Required future sequence:

1. Lifecycle dry/watch-only: observe positions and compute lifecycle state, but
   do not build or send a close request.
2. Lifecycle close-preflight only: evaluate every close gate and log the
   hypothetical request digest, but do not close.
3. Lifecycle single demo close: allow at most one close attempt for the matching
   `position_ticket` and `exit_reason`.
4. Analyze `lifecycle_*` logs, broker history, and final broker state.
5. Stop on `position_close_uncertain_reconciliation_hold`, rejected close, or
   manual intervention.

No runbook step may bypass broker reconciliation, demo-account gating, duplicate
attempt protection, or max close attempts `1`.

## 12. Non-Goals

This packet does not implement or authorize:

- live trading;
- production validity;
- retry;
- external scheduler;
- martingale/grid;
- multi-symbol lifecycle;
- multi-strategy lifecycle;
- manual state editing;
- bypass broker reconciliation;
- partial close;
- position reversal;
- DB mutation;
- runtime CSV edits;
- StrategySpec changes;
- `PositionClose` in this design packet;
- any `.mq5` code change.

## 13. Historical Implementation Boundary

At the historical `17e11fe` boundary, the recommended next implementation was a
separate lifecycle watch/preflight EA or module, not an in-place mutation of the
then-validated entry-send behavior. The first proposed patch was watch-only and
stopped before any close primitive; a later isolated patch could add one
demo-only close call after lifecycle-gate review. That roadmap is preserved as
historical context. The current runtime boundary is the integrated Patch C EA
with exactly two reviewed `OrderSend(` call sites.
