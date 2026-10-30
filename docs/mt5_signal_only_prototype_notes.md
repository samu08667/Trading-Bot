# MT5 Signal-Only Prototype Notes

Prototype:
`mt5_ea_prototypes/GBPUSD_FixedCandidate_SignalOnly.mq5`

This file is a signal parity prototype for
`gbpusd_short_h10_1_5_off_hours`. It is not an execution EA.

## Scope

- Runs only on `GBPUSD` `M15`.
- Evaluates closed bars only.
- Exports a CSV with the Python parity dataset schema.
- Copies rates into an explicit oldest-to-newest buffer before calculating
  rolling features.
- Filters output with `InpOutputStartTime`, `InpOutputEndTime`, and
  `InpMaxOutputRows` so the CSV can match the Python 500-row parity export.
- Deletes any existing output CSV before writing a fresh file for the run.
- Exports at most one row per `time_server`; duplicate bar times are skipped
  and counted in the diagnostic log.
- If the filtered buffer has more than `InpMaxOutputRows`, exports the first
  rows in chronological order.
- Computes ATR 20, MA fast 20, close-to-MA ATR ratio, inclusive 100-bar
  tick-volume percentile, buckets, signal flag, entry preview, SL preview,
  TP preview, and max holding metadata.
- Computes lifecycle metadata with no-weekend-hold:
  `friday_last_entry_time_server = 23:15`,
  `friday_forced_flat_time_server = 23:45`, and
  `max_exit_time_server` from the selected export window, capped at the Friday
  forced-flat time when applicable.
- Does not create, modify, or close positions.

## Strategy Tester Range

For the current Python parity CSV, run the signal-only prototype in Strategy
Tester with:

- Expert: `GBPUSD_FixedCandidate_SignalOnly`
- Symbol: `GBPUSD`
- Timeframe: `M15`
- Range: `2026.06.17 00:00` to `2026.06.30 00:00`

Keep the prototype inputs aligned with the Python CSV:

- `InpOutputStartTime = 2026.06.17 01:15:00`
- `InpOutputEndTime = 2026.06.29 22:45:00`
- `InpMaxOutputRows = 500`

After any `.mq5` lifecycle metadata change, regenerate the MQL5 signal-only CSV
before running the comparator; stale CSV files can preserve older
`max_exit_time_server` values.

The Strategy Tester end must be later than the final Python signal at
`2026-06-29 22:30:00`, and later than the final Python row at
`2026-06-29 22:45:00`, otherwise the MQL5 export cannot produce the same
closed-bar comparison range.

## One-Position-Only Future Requirement

The Python parity dataset can contain consecutive signal rows. A future
execution-capable EA must open at most one position for this strategy and must
ignore later signals while that position remains open.

This one-position-only rule belongs in a future execution phase, together with
the existing duplicate/idempotency design. It is intentionally not implemented
in the signal-only prototype.

## Future Lifecycle Requirement

If a future EA opens a position, it must save the entry time and entry bar, then
count closed M15 bars using MT5 server time. If SL/TP has not closed the
position after `max_holding_bars = 10`, the future execution EA must close the
position at market.

The future execution EA must also enforce no-weekend-hold:

- no new Friday entry after `23:15` server time;
- any still-open Friday position flat by `23:45` server time;
- no position carried over the weekend;
- SL/TP still have priority if hit first.

`MqlRates.time` is normally the opening timestamp of the M15 candle. The
`23:15` Friday cutoff is an operational entry execution cutoff, not only a
signal bar timestamp check. The signal-only CSV keeps the entry signal fields
unchanged and logs lifecycle metadata separately.

The signal-only prototype only logs `max_holding_bars` and
`max_exit_time_server` for parity work. The Friday `23:15` cutoff remains a
future execution gate and does not change `signal_bool` in this signal-only
phase.

## Explicit Non-Goals

- No `OrderCheck`.
- No `OrderSend`.
- No `PositionClose`.
- No broker payload construction.
- No retry.
- No scheduler.
- No grid, martingale, or position stacking.
- No production/live-account support.
