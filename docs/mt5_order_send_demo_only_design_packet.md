# MT5 OrderSend Demo-Only Design Packet

This packet began as the conservative entry `OrderSend` demo-only design for
`gbpusd_short_h10_1_5_off_hours`. The current validated EA now contains exactly
two callable `OrderSend(` call sites: one entry send and one integrated
lifecycle close. Both are demo-only, explicitly gated, no-retry paths. This
document keeps historical entry-phase notes where useful and marks current
state where the implementation has advanced.

> Historical design boundary as of the entry OrderSend design phase
> (`e9601e0`). At that boundary this packet was design only and did not change
> any `.mq5` execution surface. The current EA surface now contains exactly two
> callable `OrderSend(` call sites: one entry and one lifecycle close.

The starting point is the validated `GBPUSD_FixedCandidate_OrderCheckDemoOnly`
phase:

- signal parity against the raw MT5 source passed for signals, buckets,
  sessions, features, entry, SL, and TP;
- the `ordercheck_enabled_003` run used a demo account and called `OrderCheck`
  six times;
- every observed `OrderCheck` retcode was `0`;
- `order_send_called=false` and `execution_performed=false` for every row;
- broker state remained flat: `position_count=0`, `pending_order_count=0`;
- `trade_transactions_log.csv` had no external/manual trade events;
- one signal was correctly blocked by `current_spread_exceeded`.

## 1. Scope

The current OrderSend demo-only EA stays narrowly scoped:

- demo account only;
- `GBPUSD` only;
- `M15` only;
- strategy `gbpusd_short_h10_1_5_off_hours` only;
- short direction only;
- closed M15 bars only, never the forming bar;
- reuse the signal logic already validated in raw-source parity;
- use the OrderCheck demo-only EA as the implementation base;
- one broker preflight and at most one entry send attempt per signal/attempt;
- one integrated lifecycle close attempt per lifecycle close attempt id;
- full structured logging and reconciliation before and after the attempt.

The future phase must not support:

- live accounts;
- multi-symbol operation;
- multi-strategy operation;
- automatic retry;
- external loops, daemons, schedulers, or background polling;
- martingale, grid, averaging, recovery, or re-entry systems;
- production validity.

## 2. Explicit Send Enable

Future send-capable inputs must default to safe values:

```text
InpEnableOrderCheck = false
InpEnableOrderSend = false
InpRequireDemoAccount = true
InpAllowLiveAccount = false
InpMaxOrderSendAttempts = 1
InpFinalSendAcknowledgment = ""
```

`OrderSend` may be called only when all of these are true:

```text
InpEnableOrderSend = true
InpFinalSendAcknowledgment = "confirm_single_demo_send_only"
InpMaxOrderSendAttempts = 1
```

`InpEnableOrderCheck=true` remains necessary but not sufficient. A successful
`OrderCheck` does not grant send authority by itself.

Any missing or mismatched send enable input must produce a blocked decision row
and no broker mutation.

## 3. Gate Sequence

The flow must be strict for each signal attempt. This is not a max-one-send-per-run design:

```text
new closed M15 bar
signal evaluation
decision gates
fresh broker reconciliation
OrderCheck
OrderCheck retcode/pass validation
pre-send fresh broker reconciliation
final send gates
single OrderSend attempt for the attempt_id/signal_id
OnTradeTransaction capture
post-send bounded reconciliation
state/log finalization
```

The send stage must not run if any earlier stage is missing, stale, failed,
blocked, or not bound to the same request digest.

## 4. Pre-Send Gates

All gates below are mandatory before a future send attempt:

- demo account is verified true;
- live account is forbidden and `InpAllowLiveAccount=false`;
- chart symbol, input symbol, and request symbol are locked to `GBPUSD`;
- chart timeframe and input timeframe are locked to `PERIOD_M15`;
- terminal trading is allowed;
- expert trading is allowed;
- symbol trade mode permits a short market deal;
- spread is within policy immediately before send;
- signal remains bound to the same closed M15 bar;
- no existing position for `GBPUSD` with the configured magic/candidate;
- no pending order for `GBPUSD` with the configured magic/candidate;
- Friday entry cutoff is respected;
- no-weekend-hold policy is respected;
- volume is normalized to symbol min/max/step and remains valid;
- sell SL/TP are normalized to symbol digits and remain valid;
- `OrderCheck` was called on the same request;
- `OrderCheck` passed according to an explicit pass rule;
- request hash/digest is unchanged between `OrderCheck` and `OrderSend`;
- `InpEnableOrderSend=true`;
- `InpFinalSendAcknowledgment` exactly equals
  `confirm_single_demo_send_only`;
- `InpMaxOrderSendAttempts=1` for the current `attempt_id`/`signal_id`;
- no previous send attempt exists for the same `attempt_id`;
- local state/audit marker can be atomically claimed for this attempt.

Any gate failure must produce `order_send_called=false`,
`execution_confirmed=false`, `retry_performed=false`, and a concrete
`block_reason`.

Multiple sends in one run are permitted only for distinct signals after broker
state returns to an eligible state. The design does not impose a run-level send
cap.

## 4A. Opt-In 0.5% Risk-Based Entry Sizing

The entry EA supports an opt-in sizing mode without changing signal logic,
SL/TP price logic, OrderCheck, entry send gates, or lifecycle close. Safe
defaults keep the validated fixed-lot behavior:

```text
InpUseRiskBasedSizing = false
InpVolumeLots = 0.01
InpRiskPercentPerTrade = 0.5
InpMaxRiskPercentPerTrade = 0.5
```

When enabled, entry risk is capped at 0.5% of `ACCOUNT_EQUITY`:

```text
risk_amount = ACCOUNT_EQUITY * InpRiskPercentPerTrade / 100.0
```

The existing strategy SL remains `1 ATR` and TP remains `1.5 ATR`. The EA must
compute loss at SL with `OrderCalcProfit(ORDER_TYPE_SELL, symbol, 1.0,
entry_price, sl_price, profit)` where possible, never with hardcoded pip value
or USD assumptions. Tick-size/tick-value symbol properties are only a fallback.
The final volume is floored to `SYMBOL_VOLUME_STEP` and must respect
`SYMBOL_VOLUME_MIN` and `SYMBOL_VOLUME_MAX`; below-min and above-max cases block
before `OrderCheck`, with no retry and no `OrderSend`.

The request digest includes sizing mode, risk percent, equity basis, risk
amount, SL distance, one-lot SL loss, raw volume, normalized volume, effective
risk, and sizing digest. Any digest mismatch between `OrderCheck` and send
preflight still blocks send.

Sizing logs are written to `position_sizing_log.csv` and summarized into
`decision_log.csv`, `order_check_log.csv`, `send_preflight_log.csv`, and
`order_send_log.csv`. The sizing log can keep `sizing_phase`, but the canonical
`sizing_digest` used by the request digest must exclude phase, timestamp, run,
`attempt_id`, and `signal_id` context. Lifecycle close is not risk-sized; it
closes the actual open position volume only.
## 5. Idempotency And Attempt Identity

Future identity fields:

- `signal_id`: deterministic from candidate id, symbol, timeframe, direction,
  and closed-bar server time;
- `attempt_id`: deterministic from `signal_id`, magic number, side, volume, SL,
  TP, and request digest;
- broker-safe comment: alphanumeric only, short enough for broker limits;
- deterministic magic number: stable per candidate and phase.

Rules:

- one send attempt per `signal_id`/`attempt_id`;
- no retry;
- no second send on the same bar;
- no second send while a matching position or pending order exists;
- write a local state/audit marker before send using compare-and-swap semantics
  if a state file is used;
- abort if the marker already exists or cannot be claimed unambiguously;
- do not let manual approval or operator acknowledgment bypass duplicate
  protection.

## 6. OrderSend Request

The entry broker request uses:

```text
TRADE_ACTION_DEAL
symbol GBPUSD
type sell
price bid immediately before send
volume normalized
sl normalized
tp normalized
deviation conservative
magic deterministic
comment broker-safe
type_filling selected safely for symbol
type_time safe default
```

The send-enabled EA implements this payload only after the final demo-only entry
gates pass. The separate `GBPUSD_FixedCandidate_OrderCheckDemoOnly` EA remains
OrderCheck-only.

Current Patch C also implements a separate integrated lifecycle close request in
the same demo EA. That close request uses the opposite-side raw `OrderSend`
pattern for a short position: `TRADE_ACTION_DEAL`, `ORDER_TYPE_BUY`, full open
position volume, Ask price, position ticket, configured magic, compatible
filling mode, lifecycle acknowledgment, close request digest, and bounded
post-close reconciliation.

## 7. Retcode Classification

Every send result must be classified without retry:

| category | execution_confirmed | broker_ticket_expected | retry_allowed | reconciliation behavior | log/state status |
| --- | --- | --- | --- | --- | --- |
| success / accepted with broker ticket | true | yes | false | read matching position/order/deal by ticket, symbol, and magic | `send_accepted_position_open` or accepted pending/order state |
| rejected no broker state | false | no | false | verify no matching position and no pending order | `send_rejected_no_position_no_order` |
| market closed | false | no | false | verify flat state and stop | `send_rejected_no_position_no_order` with market-closed reason |
| client autotrading disabled | false | no | false | verify flat state and stop | `send_rejected_no_position_no_order` with client-disabled reason |
| trade disabled | false | no | false | verify flat state and stop | `send_rejected_no_position_no_order` with trade-disabled reason |
| invalid volume | false | no | false | verify flat state and stop | `send_rejected_no_position_no_order` with invalid-volume reason |
| invalid stops | false | no | false | verify flat state and stop | `send_rejected_no_position_no_order` with invalid-stops reason |
| price changed / requote | false | no | false | verify flat state and stop | `send_rejected_no_position_no_order` with price-change reason |
| no money / margin | false | no | false | verify flat state and stop | `send_rejected_no_position_no_order` with margin reason |
| timeout / uncertain | unknown | unknown | false | bounded reconciliation; hold if not conclusive | `send_uncertain_reconciliation_hold` |
| unknown retcode | unknown | unknown | false | bounded reconciliation; hold if not conclusive | `send_uncertain_reconciliation_hold` |

`retry_allowed` is always false. A retcode category can only decide state after
post-send reconciliation confirms whether broker state changed.

## 8. Logging Schema

Future send phase logs must extend, not replace, the current OrderCheck logs.

Required additional files:

```text
send_preflight_log.csv
order_send_log.csv
trade_transactions_log.csv
post_send_reconciliation_log.csv
state_transition_log.csv
run_final_summary_log.csv
```

Minimum `send_preflight_log.csv` fields:

```text
run_id
attempt_id
signal_id
candidate_id
bar_time
timestamp_server
demo_account_ok
live_account_forbidden_ok
symbol_ok
timeframe_ok
terminal_trade_allowed_ok
expert_trade_allowed_ok
spread_ok
signal_binding_ok
one_position_only_ok
pending_order_ok
friday_entry_cutoff_ok
no_weekend_hold_ok
volume_ok
sl_tp_ok
order_check_passed
request_digest_unchanged
send_enabled
final_ack_ok
max_attempts_ok
duplicate_attempt_ok
decision
block_reason
```

Minimum `order_send_log.csv` fields:

```text
run_id
attempt_id
signal_id
candidate_id
bar_time
timestamp_server
symbol
side
volume
price
sl
tp
magic_number
comment
request_digest
order_check_digest
order_send_called
order_send_attempt_count
order_send_retcode
order_send_retcode_name
order_send_comment
order_ticket
deal_ticket
position_ticket
execution_confirmed
order_send_result_category
retry_performed
automatic_retry_allowed
```

`order_send_attempt_count` must never exceed `1` for one `attempt_id`/`signal_id`.
`total_order_send_attempt_count` in the final run summary may be greater than
`1` when distinct signals pass all gates.

`trade_transactions_log.csv` must remain passive and include the local
`attempt_id` when a transaction can be correlated.

`post_send_reconciliation_log.csv` must record position count, pending order
count, observed ticket/deal/position ids, and the final reconciliation status.

`state_transition_log.csv` must record every state transition with previous
state, next state, reason, source gate, timestamp, `order_send_called`, and
`execution_performed`. Post-send states must not retain pre-send false defaults.

`run_config_log.csv` is an `initial_run_config_snapshot`; it must not be read as
a final execution summary. `run_final_summary_log.csv` provides the final run
summary with `total_order_send_attempt_count`, `execution_confirmed_count`,
`rejected_count`, `uncertain_count`, final broker state, retry flags,
`max_order_send_attempts_per_attempt`, lifecycle close counters, and position
sizing counters. The lifecycle close counters cover close-called, confirmed,
rejected, uncertain, skipped-already-closed, duplicate-blocked, time-exit,
Friday forced-flat, unresolved-identity blocked, and manual-intervention
required outcomes. The sizing counters cover fixed/risk-based modes,
passed/blocked sizing statuses, primary sizing block reasons, and min/max
observed effective risk and final volume.

## 9. OnTradeTransaction Correlation

Future `OnTradeTransaction` handling is passive observation only. It must not
open, modify, close, retry, or schedule anything.

Correlation keys:

- magic number;
- symbol;
- order ticket;
- deal ticket;
- position ticket;
- broker comment when available;
- local `attempt_id`;
- `signal_id`;
- closed bar time and candidate id.

Unmatched transaction events must be logged as external/manual observations and
must not trigger a send or retry.

## 10. Post-Send Reconciliation

Post-send reconciliation must be read-only and bounded:

- read positions by symbol and magic;
- read pending orders by symbol and magic;
- match order/deal/position tickets if available;
- compare broker state to the send result category;
- perform a fixed, small number of reads or a fixed short observation window;
- no infinite loop;
- no retry;
- no second send;
- if broker state is not conclusive, move to `reconciliation_hold`.

`reconciliation_hold` requires human review and must not auto-recover by
sending another order.

## 11. State Model

Future states:

```text
no_signal
signal_detected
order_check_passed
send_preflight_passed
send_attempted
send_accepted_position_open
send_rejected_no_position_no_order
send_uncertain_reconciliation_hold
position_closed_tp
position_closed_sl
position_closed_time_exit
position_closed_friday_forced_flat
manual_intervention_detected
```

The send-enabled EA implements the entry-send states through the bounded
post-send reconciliation result. Integrated lifecycle Patch C now also
implements the close states in
`docs/mt5_integrated_lifecycle_order_send_design_packet.md`.

## 12. Friday Forced-Flat

Friday forced-flat is an execution/lifecycle design separate from entry send:

- do not open a new position after `23:15` server time on Friday;
- if a matching position is still open at Friday `23:45` server time, the
  current integrated lifecycle Patch C may close it at market on demo after all
  lifecycle gates pass and `position_identity_status=matched_confirmed_entry`;
- if `position_identity_status=unresolved_after_restart_or_external_position`,
  time-exit and Friday forced-flat close are blocked with
  `position_identity_unresolved_manual_review_required`,
  `not_called_position_identity_unresolved`, `manual_intervention_required=true`,
  and `unresolved_policy_action=block_lifecycle_close`;
- do not implement `PositionClose`; the current close path uses one reviewed raw
  lifecycle `OrderSend` call instead;
- never hold a position over the weekend.

The entry path enforces the Friday entry cutoff. The integrated lifecycle path
handles the forced-flat close.

## 13. Static Guard Requirements

Current tests must enforce:

- exactly two callable `OrderSend(` matches appear in the send-enabled EA: one
  entry send and one integrated lifecycle close;
- no additional `OrderSend(` appears in the OrderCheck EA or any other `.mq5`
  file;
- `OrderSendAsync` is absent;
- `PositionClose` is absent;
- `InpMaxOrderSendAttempts` exists and is hard/validated as `1`;
- no retry loops;
- no scheduler, watcher, daemon, timer loop, or background polling;
- live account is forbidden;
- final acknowledgment is required;
- `OrderCheck` is required before send;
- request digest is unchanged between check and send;
- `order_send_attempt_count <= 1` per `attempt_id`/`signal_id`;
- `run_final_summary_log.csv` and summary counters are present;
- all per-signal logs include `run_id`, `attempt_id`, and `signal_id`.

Static scans should distinguish safe input/config/log fields from callable
broker mutation primitives. Safe fields include `InpEnableOrderSend`,
`InpMaxOrderSendAttempts`, `order_send_called`, `order_send_attempt_count`, and
`total_order_send_attempt_count`.

The send-enabled EA must contain exactly two callable `OrderSend(` matches:

```powershell
Select-String -Path mt5_ea_prototypes\GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5 -Pattern "OrderSend\s*\("
```

Forbidden primitive scans must return no matches:

```powershell
Select-String -Path mt5_ea_prototypes\*.mq5 -Pattern "OrderSendAsync\s*\(|PositionClose\s*\(|CTrade|trade\.Buy\s*\(|trade\.Sell\s*\("
```

## 14. Operator Runbook

Future operator sequence:

1. Dry/log-only run with send disabled.
2. OrderCheck-only run with `InpEnableOrderCheck=true` and send disabled.
3. Send preflight-only run that validates every final gate but does not call
   `OrderSend`.
4. Demo `OrderSend` run with final acknowledgment and
   `InpMaxOrderSendAttempts=1` per attempt/signal.
5. Post-send reconciliation and final summary review.
6. Analyze logs and broker state.
7. Stop; do not rerun automatically.

Any blocked, rejected, uncertain, or manually intervened state stops the
operator runbook until reviewed. A manual single-shot test may stop after the
first accepted send, but that is an operational test choice, not a bot-level
constraint.

## 15. Non-Goals

This design explicitly excludes:

- live trading;
- production validity;
- multi-strategy support;
- multi-symbol support;
- retry;
- scheduler;
- auto recovery send;
- auto recovery close;
- manual state editing;
- gate bypass;
- martingale/grid;
- background execution;
- automatic Friday close inside the entry send phase; current Friday forced-flat
  is handled only by the integrated lifecycle close path;
- DB mutation from MQL5;
- StrategySpec value changes.
