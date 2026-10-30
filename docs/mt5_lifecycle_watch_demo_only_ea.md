# MT5 Lifecycle Watch Demo-Only EA

## Purpose

`GBPUSD_FixedCandidate_LifecycleWatchDemoOnly.mq5` is a demo-only lifecycle
watch and close-preflight scaffold for `gbpusd_short_h10_1_5_off_hours`.

It observes a matching open position, derives lifecycle timing from MT5 server
time, decides whether a lifecycle close would be required, and writes structured
CSV logs. It does not close positions and does not call any broker close
primitive.

Current status: this separate lifecycle scaffold is historical/reference
material. The active runtime lifecycle owner is now the integrated lifecycle
inside `GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`, where Patch C can perform
one gated demo-only lifecycle close attempt for validated lifecycle exit
reasons. This scaffold still remains no-close.

## Scope

- Demo account only.
- `GBPUSD` only.
- `M15` only.
- Short strategy only.
- Candidate only: `gbpusd_short_h10_1_5_off_hours`.
- Magic number aligned with the entry EA: `1510152345`.
- Watch/preflight only.
- No live-account support.
- No close execution.
- No retry and no scheduler.

The entry EA remains separate. This lifecycle scaffold must not modify
`GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`.

## Inputs

Safe defaults:

```text
InpEnableLifecycleWatch = false
InpEnableLifecycleClosePreflight = false
InpEnableLifecycleClose = false
InpFinalLifecycleAcknowledgment = ""
InpMaxLifecycleCloseAttempts = 1
InpRequireDemoAccount = true
InpAllowLiveAccount = false
InpRunId = ""
InpOverwriteLogsOnInit = true
InpLogCommonFiles = true
InpMagicNumber = 1510152345
InpMaxHoldingBars = 10
InpFridayForcedFlatTime = 23:45
InpFridayLastEntryTime = 23:15
```

The implementation uses `InpEnableLifecycleClose` and
`InpMaxLifecycleCloseAttempts` so the raw `.mq5` static guard can keep the
platform close primitive token out of source files. The log schema still uses
`position_close_*` field names.

`InpEnableLifecycleWatch` enables position observation and lifecycle decision
logging.

`InpEnableLifecycleClosePreflight` enables final gate evaluation for a
hypothetical lifecycle close. Passing this gate logs
`position_close_preflight_passed_no_close`.

`InpEnableLifecycleClose` is logged and defaults to `false`. In this scaffold it
does not authorize a close. If it is set to `true`, the final lifecycle
acknowledgment must exactly equal
`confirm_single_demo_lifecycle_close_only`; even then, this scaffold still does
not close anything.

`InpMaxLifecycleCloseAttempts` must equal `1`. Any other value blocks
initialization.

## Evaluation Trigger

The EA uses normal `OnTick` and evaluates at most once per newly closed M15 bar.
It does not use timer events, sleep calls, an external scheduler, or a polling
loop.

Friday forced flat is evaluated as:

```text
close required on first observed tick at or after Friday 23:45 server time
```

Without a timer, the EA can only observe server time when a tick arrives. This
is acceptable for the watch/preflight scaffold and must be reviewed again before
any real close patch.

## Position Discovery

The scaffold reads current positions matching:

- symbol `GBPUSD`;
- configured magic number;
- short position side.

If no matching position exists:

```text
position_observed_open=false
lifecycle_status=no_position_observed
```

If more than one matching position exists:

```text
lifecycle_status=multiple_matching_positions_blocked
```

The scaffold does not attempt to repair or mutate broker state.

## Bar Counting

The scaffold uses `POSITION_TIME` as `entry_time` and derives `entry_bar_time`
from the M15 bar-open time containing that entry timestamp.

`bars_elapsed` is the number of closed M15 bars after `entry_bar_time`:

```text
entry bar is not counted
bar_open_time > entry_bar_time
bar_open_time <= current_closed_bar_time
```

All time is MT5 server time. If the entry bar cannot be derived, the scaffold
blocks preflight with `entry_bar_time_unresolved`. If closed-bar history is
insufficient, it logs `bar_count_unavailable`.

Deal-history reconstruction is intentionally deferred to a later patch.

## Exit Decision

`exit_reason_preview` can be:

```text
none
time_exit_10_m15_bars
friday_forced_flat
```

Priority:

1. No matching position: `none`.
2. Friday at or after `23:45` server time with an open position:
   `friday_forced_flat`.
3. `bars_elapsed >= 10`: `time_exit_10_m15_bars`.
4. Otherwise: `none`.

Broker-side SL/TP are not actions in this scaffold. If the position is already
gone, the scaffold logs `no_position_observed`.

## Close Preflight Only

If `exit_reason_preview != none` and `InpEnableLifecycleClosePreflight=true`,
the scaffold checks:

- demo account true;
- live account forbidden;
- matching position exists;
- exactly one matching position;
- short side;
- max close attempts equals `1`;
- no duplicate lifecycle attempt for the same position and exit reason;
- terminal and expert trading allowed;
- symbol trade mode allows market close;
- lifecycle acknowledgment valid when lifecycle close input is enabled;
- close price preview available.

If all gates pass, it logs:

```text
position_close_preflight_passed_no_close
```

No broker mutation follows. `close_called=false`, `close_attempt_count=0`,
`retry_performed=false`, and `automatic_retry_allowed=false` remain invariant.

## Logs

Logs are written under:

```text
TradingBot/gbpusd_short_h10_1_5_off_hours/<run_id>/
```

Files:

- `run_config_log.csv`: initial lifecycle inputs and account snapshot.
- `lifecycle_watch_log.csv`: observed position, entry time, bar count, and
  exit preview.
- `lifecycle_exit_decision_log.csv`: watch/preflight decision and block reason.
- `position_close_log.csv`: hypothetical close audit with no close performed.
- `lifecycle_reconciliation_log.csv`: matching position and pending order
  snapshot.
- `lifecycle_state_transition_log.csv`: lifecycle state movement for the
  current observation.

## Expected Runs

Watch disabled dry run:

```text
InpEnableLifecycleWatch = false
InpEnableLifecycleClosePreflight = false
InpEnableLifecycleClose = false
```

Expected status:

```text
lifecycle_watch_disabled
close_called=false
```

Watch-only run:

```text
InpEnableLifecycleWatch = true
InpEnableLifecycleClosePreflight = false
InpEnableLifecycleClose = false
```

Expected statuses include `no_position_observed`, `position_observed_open`,
`position_close_required_time_exit`, or
`position_close_required_friday_forced_flat`.

Close-preflight-only run:

```text
InpEnableLifecycleWatch = true
InpEnableLifecycleClosePreflight = true
InpEnableLifecycleClose = false
InpMaxLifecycleCloseAttempts = 1
InpRequireDemoAccount = true
InpAllowLiveAccount = false
```

If a matching position has a lifecycle exit reason and all gates pass:

```text
position_close_preflight_passed_no_close
```

## Safety Boundaries

This scaffold does not implement real close execution. A future patch must be
separate, must update static guards intentionally, and must be validated in a
demo-only run before any lifecycle close call is allowed.

Do not use this EA on a live account.
