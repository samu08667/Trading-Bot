# MT5 OrderCheck Demo-Only EA

## Purpose

`GBPUSD_FixedCandidate_OrderCheckDemoOnly.mq5` is the controlled MT5 EA
prototype for `gbpusd_short_h10_1_5_off_hours`. It keeps the validated
signal-only feature logic and adds demo-only broker preflight up to `OrderCheck`.
It does not open, modify, or close trades.

## What It Does

- Runs only on `GBPUSD` `M15`.
- Evaluates one newly closed M15 bar at a time and ignores the forming bar.
- Recomputes ATR 20, MA fast 20, close-to-MA ATR ratio, inclusive 100-bar tick
  volume percentile, hour session, buckets, `signal_bool`, entry preview, SL,
  TP, max holding bars, and max-exit metadata.
- Creates a unique run folder for each run unless `InpRunId` is supplied.
- Writes `run_config_log.csv` at initialization so the effective inputs are
  auditable before interpreting signal or preflight rows.
- Applies demo-only safety gates before any broker preflight.
- Builds a short-only `TRADE_ACTION_DEAL` request for `OrderCheck` when all
  gates pass and `InpEnableOrderCheck = true`.
- Logs signal, decision, preflight, position observation, passive trade
  transaction, and reconciliation CSV rows.

## What It Does Not Do

- Does not send orders.
- Does not close positions.
- Does not modify existing positions or pending orders.
- Does not retry.
- Does not run an external scheduler or artificial loop.
- Does not support live accounts.
- Does not change StrategySpec values, thresholds, SL/TP multipliers, spread
  limits, volume policy, risk policy, DB state, or reports runtime.

## Inputs

Use these defaults unless explicitly reviewing a controlled demo preflight:

```text
InpEnableOrderCheck = false
InpRequireDemoAccount = true
InpAllowLiveAccount = false
InpSymbol = GBPUSD
InpTimeframe = PERIOD_M15
InpMaxSpreadPoints = 15
InpVolumeLots = 0.01
InpMagicNumber = 1510152345
InpLogCommonFiles = true
InpLogPrefix = gbpusd_short_h10_1_5_off_hours
InpRunId = ""
InpOverwriteLogsOnInit = true
InpFridayLastEntryTime = 23:15
InpFridayForcedFlatTime = 23:45
```

If `InpRunId` is blank, the EA generates a value like
`ordercheck_demo_YYYYMMDD_HHMMSS` from local terminal time. Supplying an explicit
`InpRunId` is useful when rerunning a named test. The resolved run id is used
both for the run folder and as the first CSV column, and the EA does not use a
numeric `0` fallback. With `InpOverwriteLogsOnInit = true`, existing CSV files
in that exact run folder are removed at startup before headers and the new
`run_config_log.csv` row are written.

`InpEnableOrderCheck = false` is the dry/log-only mode. With that setting the EA
logs signals and decisions, then records `order_check_called=false` with
`block_reason=order_check_disabled` when a signal reaches the preflight boundary.

`InpEnableOrderCheck = true` allows one `OrderCheck` per eligible closed bar only
when every safety gate passes on a demo account. If another gate blocks,
`order_check_log.csv` records that gate in `block_reason`.

## Logs Produced

The EA writes CSV files under this logical folder:

```text
TradingBot/gbpusd_short_h10_1_5_off_hours/<run_id>/
```

Files:

- `run_config_log.csv`: one initialization row with effective inputs and account
  trade state.
- `signal_log.csv`: one row per evaluated new closed bar.
- `decision_log.csv`: gate status, decision, and block reason.
- `order_check_log.csv`: rows for called preflight or final preflight blocks.
- `position_lifecycle_log.csv`: read-only position observation; action is always
  `none_observation_only`.
- `trade_transactions_log.csv`: passive `OnTradeTransaction` observations from
  external/manual activity.
- `reconciliation_log.csv`: read-only GBPUSD/magic position and pending-order
  snapshot.

Every CSV, including `run_config_log.csv`, has `run_id` as the first column. The
config log records `timestamp_server` immediately after `run_id`, then the
effective inputs and account state. All preflight rows keep
`order_send_called=false` and `execution_performed=false`.

## Where To Find Logs In MT5

With `InpLogCommonFiles = true`, MT5 writes files below the common terminal
files area, typically:

```text
<Terminal Common Data Folder>/Files/TradingBot/gbpusd_short_h10_1_5_off_hours/<run_id>/
```

With `InpLogCommonFiles = false`, logs are written under the current terminal or
Strategy Tester `Files` directory with the same `TradingBot/.../<run_id>/`
subfolder.

## Copying Logs Into The Repo

After a run, copy the run folder into a future analysis folder under the repo,
for example:

```text
data/exports/mt5_order_check_demo_only/gbpusd_short_h10_1_5_off_hours/<run_id>/
```

Do not overwrite parity reports or runtime state directories. Treat these logs
as analysis inputs for a separate review step.

## Future Analysis

A future analyzer should first read `run_config_log.csv`, then join
`signal_log.csv`, `decision_log.csv`, and `order_check_log.csv` by `run_id`,
`bar_time`, and `candidate_id`. Check:

- the intended `InpEnableOrderCheck` value is visible in `run_config_log.csv`;
- no duplicate evaluated bars inside a run;
- no duplicate preflight attempt per bar;
- all blocked rows have a concrete `block_reason`;
- `order_send_called` is always false;
- `execution_performed` is always false;
- demo/account/symbol/timeframe/spread/position/pending/Friday/volume/SL/TP gates
  are visible before every preflight attempt.

## Safety Boundaries

The EA must remain demo-only. `InpAllowLiveAccount` must stay false. The account
must be demo when `InpRequireDemoAccount = true`. Any existing GBPUSD position or
pending order with the configured magic blocks preflight. Friday entries after
`23:15` server time are blocked, and Friday max-exit metadata is capped at
`23:45` server time.

The EA is not an execution approval. It is a broker preflight/logging prototype.

## Difference From A Future Demo Send Phase

This phase stops at `OrderCheck`. A future demo send phase would require a
separate review, explicit safety gates, separate static guards, and fresh
approval before adding any order transmission behavior. The current EA must not
be broadened into that phase in-place.

## MT5 Instructions

```text
Expert: GBPUSD_FixedCandidate_OrderCheckDemoOnly
Symbol: GBPUSD
Timeframe: M15
Account: demo only
InpEnableOrderCheck = false for dry/log-only
InpEnableOrderCheck = true only when demo OrderCheck preflight is intentionally allowed
InpRunId = "" for auto-generated run id, or a unique explicit id
InpOverwriteLogsOnInit = true for a clean run folder
```

Do not run this EA on a live account.