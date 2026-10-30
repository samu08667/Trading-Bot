# MT5 OrderSend Demo-Only EA

## Purpose

`GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5` is the demo-only
single-attempt-per-signal entry EA for
`gbpusd_short_h10_1_5_off_hours`.

This phase preserves the validated signal and preflight logic and adds a gated
real `OrderSend` path. A run may contain more than one broker transmission only
when each transmission belongs to a distinct `signal_id`/`attempt_id` and all
broker-state gates pass again.

This EA is not production-valid and must not be used on a live account.

For supervised demo-live smoke operation, use the compact checklist in
`docs/demo_live_smoke_runbook.md` before enabling any gated send or lifecycle
close input.

## Scope

- Demo account only.
- `GBPUSD` only.
- `M15` only.
- Short-only.
- Candidate only: `gbpusd_short_h10_1_5_off_hours`.
- One broker transmission attempt per `attempt_id`.
- No live-account support.
- Integrated lifecycle Patch C can perform one gated demo-only lifecycle close attempt per lifecycle close attempt id; no retry, no scheduler.
- No `OrderSendAsync`, `PositionClose`, `CTrade`, `trade.Buy`, or `trade.Sell`. The lifecycle close path uses one additional raw `OrderSend` call.

## Inputs

Safe defaults:

```text
InpEnableOrderCheck = false
InpEnableSendPreflight = false
InpEnableOrderSend = false
InpFinalSendAcknowledgment = ""
InpEnableIntegratedLifecycleWatch = false
InpEnableIntegratedLifecycleClosePreflight = false
InpEnableIntegratedLifecycleClose = false
InpFinalLifecycleAcknowledgment = ""
InpMaxOrderSendAttempts = 1
InpMaxLifecycleCloseAttempts = 1
InpMaxHoldingBars = 10
InpRequireDemoAccount = true
InpAllowLiveAccount = false
InpRunId = ""
InpOverwriteLogsOnInit = true
InpLogCommonFiles = true
InpVolumeLots = 0.01
InpUseRiskBasedSizing = false
InpRiskPercentPerTrade = 0.5
InpMaxRiskPercentPerTrade = 0.5
InpMagicNumber = 1510152345
InpMaxSpreadPoints = 15
InpFridayLastEntryTime = 23:15
InpFridayForcedFlatTime = 23:45
```

`InpEnableOrderCheck` allows the broker preflight check after signal and safety
gates pass.

`InpEnableSendPreflight` allows the final send-preflight gate evaluation.

`InpEnableOrderSend` must be `true` before a broker transmission for a specific
`attempt_id` can be attempted. It is not sufficient by itself.

`InpFinalSendAcknowledgment` must exactly equal
`confirm_single_demo_send_only` for the demo send path.

`InpMaxOrderSendAttempts` must equal `1` for each `attempt_id`/`signal_id`. Any
other value blocks initialization or preflight. This is not a max-one-send-per-run
or max-one-trade-per-run setting.

`InpRequireDemoAccount=true` and `InpAllowLiveAccount=false` are mandatory
safety boundaries.

`InpEnableIntegratedLifecycleWatch` enables Patch A lifecycle observation inside
the same run as entry/send. It only logs matching position state, bar count, and
`exit_reason_preview`.

`InpEnableIntegratedLifecycleClosePreflight` is logged in Patch A but does not
run close preflight yet. If a lifecycle exit would be required, Patch A logs
`integrated_lifecycle_close_preflight_not_implemented_in_patch_a` when this
input is true.

`InpEnableIntegratedLifecycleClose` is logged and defaults to `false`. In Patch
A it never closes a position.

`InpMaxLifecycleCloseAttempts` must equal `1`; invalid values block lifecycle
watch/preflight logging with a precise reason but do not add any retry path.

`InpMaxHoldingBars=10` preserves the StrategySpec lifecycle horizon.

`InpUseRiskBasedSizing=false` preserves the validated fixed-lot behavior with
`InpVolumeLots=0.01`. When `InpUseRiskBasedSizing=true`, entry volume is
computed before request digest, `OrderCheck`, send preflight, and entry
`OrderSend`. The policy is capped at `InpRiskPercentPerTrade=0.5` and
`InpMaxRiskPercentPerTrade=0.5`, using `ACCOUNT_EQUITY` as the account basis.
The entry sizing path uses `OrderCalcProfit` for the estimated loss of one lot
at the existing strategy SL, floors the computed volume to the broker volume
step, blocks risk-based entries if min/max lot or effective-risk policy would be
violated, and logs all values to `position_sizing_log.csv`. In fixed mode, the
0.5% cap is audit-only and does not block the validated `InpVolumeLots=0.01`
path. Lifecycle close remains unchanged and uses the actual open position
volume, not entry sizing.

## Dry Run

Use the default safety inputs:

```text
Expert: GBPUSD_FixedCandidate_OrderSendDemoOnly
Symbol: GBPUSD
Timeframe: M15
Account: demo only
InpEnableOrderCheck = false
InpEnableSendPreflight = false
InpEnableOrderSend = false
InpFinalSendAcknowledgment = ""
InpMaxOrderSendAttempts = 1
```

Expected behavior:

- Signal rows are logged on new closed M15 bars.
- Broker state snapshots are read-only.
- No broker mutation occurs.
- A signal that reaches the send boundary blocks with
  `order_check_required_before_send`.

## OrderCheck / Preflight No-Send Run

For a controlled no-send preflight after the real-send patch:

```text
InpEnableOrderCheck = true
InpEnableSendPreflight = true
InpEnableOrderSend = false
InpFinalSendAcknowledgment = ""
InpEnableIntegratedLifecycleWatch = false
InpEnableIntegratedLifecycleClosePreflight = false
InpEnableIntegratedLifecycleClose = false
InpFinalLifecycleAcknowledgment = ""
InpMaxOrderSendAttempts = 1
InpMaxLifecycleCloseAttempts = 1
InpMaxHoldingBars = 10
InpRequireDemoAccount = true
InpAllowLiveAccount = false
```

Expected behavior when all pre-send gates up to the final send enable pass:

```text
signal_detected
order_check_passed
send_preflight_blocked
block_reason=order_send_input_disabled
```

No broker transmission is attempted in this mode.

## Demo Send Run

For a demo send run with one broker transmission attempt allowed per signal:

```text
InpEnableOrderCheck = true
InpEnableSendPreflight = true
InpEnableOrderSend = true
InpFinalSendAcknowledgment = confirm_single_demo_send_only
InpMaxOrderSendAttempts = 1
InpRequireDemoAccount = true
InpAllowLiveAccount = false
```

Expected state path when every gate passes for a signal:

```text
signal_detected
order_check_passed
send_attempted
send_accepted_position_open
```

If the broker rejects and reconciliation confirms flat state, expected final
state is:

```text
send_rejected_no_position_no_order
```

If the retcode or broker state is inconclusive, expected final state is:

```text
send_uncertain_reconciliation_hold
```

A hold state requires manual review. Do not rerun automatically and do not try a
second send for the same signal.

`InpMaxOrderSendAttempts=1` means one broker transmission attempt for the
current `attempt_id`/`signal_id`. It does not cap the whole run at one send. More
than one trade in the same run is acceptable only when later signals have
distinct identities and the one-position-only plus pending-order gates confirm
eligible broker state again.

A manual single-shot test is an operator runbook choice: stop the run after the
first accepted send if that is the test objective. It is not a final bot
constraint.

## Logs

Logs are written under:

```text
TradingBot/gbpusd_short_h10_1_5_off_hours/<run_id>/
```

Files:

- `run_config_log.csv`: initial effective inputs and account-state snapshot only;
  it is not a final run summary.
- `signal_log.csv`: validated feature and signal fields.
- `decision_log.csv`: safety gates and block reason.
- `order_check_log.csv`: `OrderCheck` request and result when enabled.
- `send_preflight_log.csv`: final pre-send gates and send attempt count.
- `order_send_log.csv`: per-attempt send result, retcode category, tickets,
  retry flags, reconciliation status, final state, and sizing audit fields.
- `position_sizing_log.csv`: per-attempt fixed/risk sizing audit, including
  account equity, 0.5% cap, SL loss estimate, raw/floored volume, effective
  risk, expected gross TP amount, and sizing block reason.
- `state_transition_log.csv`: `signal_detected`, `order_check_passed`,
  `send_preflight_blocked`, `send_attempted`, and final send state with
  post-send `order_send_called`/`execution_performed` flags.
- `post_send_reconciliation_log.csv`: bounded read-only broker snapshot.
- `run_final_summary_log.csv`: final run-level audit summary, including total
  send attempts, confirmed executions, rejected sends, uncertain sends, final
  broker state, `max_order_send_attempts_per_attempt`, lifecycle close counters,
  and position sizing counters.
- `trade_transactions_log.csv`: passive transaction observations only, including `transaction_identity_status`.
- `reconciliation_log.csv`: read-only position and pending-order counts.
- `position_lifecycle_log.csv`: read-only legacy lifecycle metadata snapshot.
- `integrated_lifecycle_watch_log.csv`: Patch A integrated lifecycle observation
  in the same run as entry/send, including `position_identity_status`.
- `integrated_lifecycle_exit_decision_log.csv`: watch-only lifecycle decision,
  including close-required preview and no-close flags.
- `integrated_lifecycle_reconciliation_log.csv`: read-only matching position and
  pending-order counts for lifecycle context.
- `integrated_lifecycle_state_transition_log.csv`: integrated lifecycle watch/preflight states.
- `integrated_position_close_log.csv`: Patch B close-preflight-only audit. It
  always keeps `close_called=false`, `close_attempt_count=0`,
  `close_confirmed=false`, `retry_performed=false`, and
  `automatic_retry_allowed=false`.

Send constraints in logs:

```text
order_send_attempt_count <= 1 per attempt_id/signal_id
total_order_send_attempt_count may be greater than 1 for distinct signals
retry_performed=false
automatic_retry_allowed=false
```

`execution_confirmed` is set only after retcode classification and read-only
post-send reconciliation. The EA does not treat the boolean return from
`OrderSend` alone as execution confirmation.

`run_final_summary_log.csv` appends lifecycle and sizing summary fields after
its original entry/send columns. Lifecycle fields include close called,
confirmed, rejected, uncertain, skipped-already-closed, duplicate-blocked,
time-exit, Friday forced-flat, unresolved-identity blocked, manual-intervention
required, and `max_lifecycle_close_attempts_per_attempt`. Sizing fields count fixed and risk-based sizing evaluations, passed/blocked
sizing statuses, main sizing block reasons, and min/max observed effective risk
percent plus min/max final volume lots. These counters are accumulated in memory
from the EA audit events; the EA does not parse runtime CSV files to build the
summary.

## Attempt Identity And Digest

`signal_id` is deterministic from:

```text
candidate_id + symbol + timeframe + bar_time + side
```

`attempt_id` is deterministic from:

```text
signal_id + run_id + send_preflight
```

The request digest is a deterministic non-cryptographic hash of a canonical
request string. It is logged as `request_digest_non_crypto_*` and is only an
audit/local equality check, not a security hash.

The EA compares the digest from the `OrderCheck` request to a fresh immediate
pre-send request digest. A mismatch blocks with:

```text
request_digest_changed_after_order_check
```

## Integrated Lifecycle Watch-Only Patch A

Patch A adds lifecycle observability inside the validated entry/send EA. It does
not close positions and does not change signal, `OrderCheck`, send preflight,
`OrderSend`, retcode classification, SL/TP, or spread behavior.

The watch evaluates at most once per newly closed M15 bar. For Friday forced
flat, it also evaluates on the first observed tick at or after Friday `23:45`
server time, even if the current closed bar was already processed.

Patch A position discovery is limited to `GBPUSD` and `InpMagicNumber`. If no
matching position exists, it logs:

```text
integrated_lifecycle_status=no_position_observed
exit_reason_preview=none
```

If exactly one matching position exists, it logs position ticket, position type,
volume, open price, SL, TP, `POSITION_TIME`, `entry_bar_time`, and
`bars_elapsed`.

After an entry send is confirmed and post-send reconciliation observes an open
position, the EA stores an in-memory mapping from `position_ticket` to the entry
`signal_id`, entry `attempt_id`, entry time, entry bar time, order ticket, and
deal ticket. Lifecycle watch uses that mapping only when the observed
`position_ticket` equals the confirmed position ticket. It never uses the
current or last signal context as a fallback for an already-open position.

`position_identity_status` values are:

```text
matched_confirmed_entry
unresolved_after_restart_or_external_position
no_position_observed
multiple_matching_positions_blocked
```

If the ticket does not match the confirmed mapping, or if the EA was restarted or
attached without in-memory mapping, it logs `signal_id_unresolved`,
`attempt_id_unresolved`, and
`position_identity_status=unresolved_after_restart_or_external_position` without
blocking watch.

Current conservative hardening blocks lifecycle close for
`position_identity_status=unresolved_after_restart_or_external_position`. The
position is still observed and reconciled, but any actionable lifecycle exit logs
`position_identity_unresolved_manual_review_required`,
`not_called_position_identity_unresolved`, `manual_intervention_required=true`,
and `unresolved_policy_action=block_lifecycle_close`; no close request is built
or sent.

`OnTradeTransaction` uses the same confirmed-entry mapping for passive
transaction logs. If the transaction `position` equals the confirmed position or
its `order`/`deal` equals the confirmed entry order/deal ticket, it logs the
confirmed entry `signal_id` and `attempt_id` with
`transaction_identity_status=matched_confirmed_entry`. If the event has an
order/deal/position reference that cannot be matched, it logs unresolved ids and
`transaction_identity_status=unresolved_after_restart_or_external_event`. Events
without a position, order, or deal reference log
`transaction_identity_status=no_position_reference`. The transaction logger does
not fall back to the current or last signal context.

`exit_reason_preview` is observation only:

```text
none
time_exit_10_m15_bars
friday_forced_flat
```

Patch B evaluates close-preflight when `exit_reason_preview` is actionable and
`InpEnableIntegratedLifecycleClosePreflight=true`. It still never closes. If
`exit_reason_preview=none`, it logs `position_close_preflight_not_required`.

```text
close_called=false
close_attempt_count=0
retry_performed=false
automatic_retry_allowed=false
```

Patch B historical no-close outcomes were:

```text
position_close_preflight_not_required
position_close_preflight_blocked
position_close_preflight_duplicate_blocked
position_close_preflight_passed_no_close
```

Patch C adds one single demo-only lifecycle close path using a raw `OrderSend(close_request, close_result)` request in the lifecycle section. It is allowed only for `time_exit_10_m15_bars` and `friday_forced_flat`. It does not manually close TP/SL events. If the position is already absent, broker-side closure is logged and no close is sent. A pass requires demo account, live forbidden, exactly one matching GBPUSD magic position, short position type, `position_identity_status=matched_confirmed_entry`, valid exit reason, `InpMaxLifecycleCloseAttempts=1`, no duplicate close send for the lifecycle attempt id, terminal and expert trading allowed, fresh reconciliation, Ask close price available, final lifecycle acknowledgment `confirm_single_demo_lifecycle_close_only`, unchanged close request digest, and `InpEnableIntegratedLifecycleClose=true`. Unresolved restart/external positions are not close-eligible and require manual review.

### Lifecycle Watch-Only Run

Use the normal demo/tester EA setup and enable only watch:

```text
InpEnableIntegratedLifecycleWatch = true
InpEnableIntegratedLifecycleClosePreflight = false
InpEnableIntegratedLifecycleClose = false
InpFinalLifecycleAcknowledgment = ""
InpMaxLifecycleCloseAttempts = 1
InpMaxHoldingBars = 10
InpRequireDemoAccount = true
InpAllowLiveAccount = false
```

Read:

```text
integrated_lifecycle_watch_log.csv
integrated_lifecycle_exit_decision_log.csv
integrated_lifecycle_reconciliation_log.csv
integrated_lifecycle_state_transition_log.csv
```
### Lifecycle Close-Preflight-Only Run

Use the normal demo/tester EA setup and enable watch plus close preflight only:

```text
InpEnableIntegratedLifecycleWatch = true
InpEnableIntegratedLifecycleClosePreflight = true
InpEnableIntegratedLifecycleClose = false
InpFinalLifecycleAcknowledgment = confirm_single_demo_lifecycle_close_only
InpMaxLifecycleCloseAttempts = 1
InpMaxHoldingBars = 10
InpRequireDemoAccount = true
InpAllowLiveAccount = false
```

Read:

```text
integrated_position_close_log.csv
integrated_lifecycle_exit_decision_log.csv
integrated_lifecycle_state_transition_log.csv
integrated_lifecycle_reconciliation_log.csv
```

Expected Patch B pass state, when a lifecycle exit is required and all gates pass:

```text
position_close_preflight_passed_no_close
```

Expected invariant in every row:

```text
close_called=false
close_attempt_count=0
close_confirmed=false
retry_performed=false
automatic_retry_allowed=false
```

### Lifecycle Single Demo Close Run

Use only on demo/tester after the preflight run has been reviewed:

```text
InpEnableIntegratedLifecycleWatch = true
InpEnableIntegratedLifecycleClosePreflight = true
InpEnableIntegratedLifecycleClose = true
InpFinalLifecycleAcknowledgment = confirm_single_demo_lifecycle_close_only
InpMaxLifecycleCloseAttempts = 1
InpMaxHoldingBars = 10
InpRequireDemoAccount = true
InpAllowLiveAccount = false
```

When all close gates pass, Patch C logs `position_close_attempted`, then bounded reconciliation classifies the outcome as one of:

```text
position_close_confirmed
position_close_rejected_no_retry
position_close_uncertain_reconciliation_hold
position_close_skipped_already_closed_by_broker
position_close_duplicate_send_blocked
position_identity_unresolved_manual_review_required
```

Read `integrated_position_close_log.csv`, `integrated_lifecycle_state_transition_log.csv`, and `integrated_lifecycle_reconciliation_log.csv`. Stop and review manually on `position_close_uncertain_reconciliation_hold` or `position_identity_unresolved_manual_review_required`; there is no retry.

## Static Guard Scan

Safe configuration and log tokens such as `InpEnableOrderSend`,
`InpMaxOrderSendAttempts`, `order_send_called`, `order_send_attempt_count`, and
`total_order_send_attempt_count` are allowed.

This entry-plus-lifecycle-close EA must contain exactly two callable `OrderSend` matches: one for entry and one for lifecycle close.

```powershell
Select-String -Path mt5_ea_prototypes\GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5 -Pattern "OrderSend\s*\("
```

This broader forbidden-primitive scan must return no matches:

```powershell
Select-String -Path mt5_ea_prototypes\*.mq5 -Pattern "OrderSendAsync\s*\(|PositionClose|CTrade|trade\.Buy\s*\(|trade\.Sell\s*\(|Sleep\s*\("
```

## Remaining Out Of Scope

Manual recovery, retry, scheduler operation, multi-symbol execution, and live trading remain out of scope. TP/SL remain broker-side. Patch C only adds the single demo-only lifecycle close attempt for time exit or Friday forced-flat.