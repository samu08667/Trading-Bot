# MT5 Raw-Source Signal Parity Workflow

This workflow replaces the sparse DB-feature parity fixture for the MQL5
signal-only comparison. The old CSV is still useful for audit history, but it
can contain data-source gaps or feature rows generated from a different bar
history than the MT5 Strategy Tester sees. For EA parity, the raw MT5 bar
history must become the shared source.

## Purpose

Goal:

1. Export raw closed `GBPUSD` `M15` bars from MT5.
2. Recompute the Python feature and signal contract from that raw CSV.
3. Compare the recomputed Python parity CSV to the MQL5 signal-only CSV with
   `time_server` as the join key.

This keeps the comparison about implementation parity, not DB-vs-MT5 history
differences.

## Raw MT5 Bar Export

Prototype:
`mt5_ea_prototypes/GBPUSD_M15_RawBarsExporter.mq5`

The exporter writes only:

- `time_server`
- `open`
- `high`
- `low`
- `close`
- `tick_volume`
- `spread`

It writes a fresh CSV per run, filters by `InpOutputStartTime` and
`InpOutputEndTime`, supports `InpMaxOutputRows = 0` for no row cap, exports
oldest-to-newest, and skips duplicate `time_server` values.

Suggested Strategy Tester inputs:

- Expert: `GBPUSD_M15_RawBarsExporter`
- Symbol: `GBPUSD`
- Timeframe: `M15`
- Range: `2026.06.17 00:00` to `2026.06.30 00:00`
- `InpOutputStartTime = 2026.06.17 01:15:00`
- `InpOutputEndTime = 2026.06.29 22:45:00`
- `InpMaxOutputRows = 0`
- `InpOutputCsv = gbpusd_m15_mt5_raw_bars.csv`

Copy the generated file from the MT5 tester files location into:

```text
data/exports/gbpusd_m15_mt5_raw_bars.csv
```

## Python Raw-Source Recompute

Exporter:
`scripts/export_fixed_candidate_mt5_raw_source_parity_dataset.py`

The script reads only the raw MT5 CSV and the frozen StrategySpec. It does not
open the DB, connect to MT5, or perform broker operations.

It recomputes:

- true range
- ATR 20 simple mean
- MA fast 20 simple mean
- close-to-MA ATR ratio
- inclusive 100-bar tick-volume percentile
- hour session from server time
- bucket labels
- signal flag
- entry, SL, and TP previews for signal rows
- `max_holding_bars`
- `max_exit_time_server`

Lifecycle metadata includes the no-weekend-hold policy:

- `no_weekend_hold = true`
- `forced_friday_exit_enabled = true`
- `friday_last_entry_time_server = 23:15`
- `friday_forced_flat_time_server = 23:45`
- time basis: MT5 server time

`max_exit_time_server` is the minimum of the tenth future real M15 timestamp
inside the raw-source/export comparison window and the same-day Friday
forced-flat timestamp when applicable. If a weekday row has no tenth future M15
timestamp available in that comparison window, the value is blank. If a Friday
row has fewer than ten future M15 bars but the forced-flat timestamp is still
available, the forced-flat timestamp is used. The MQL5 signal-only exporter must
look for the tenth future timestamp in the selected export rows, not in the full
`CopyRates` buffer.

This is lifecycle metadata, not an entry signal rule. The exported
`signal_bool` remains the pure signal-parity value. A future execution-capable
EA must use the Friday entry cutoff as an operational entry permission check.
`MqlRates.time` is normally the M15 bar-open timestamp, so
`friday_last_entry_time_server = 23:15` is an entry execution cutoff, not a
blanket permission for every signal bar whose open time is `23:15` or earlier.
Any still-open position must be flat by `23:45` server time on Friday, with
SL/TP taking priority if hit first.

Suggested command:

```powershell
python scripts\export_fixed_candidate_mt5_raw_source_parity_dataset.py `
  --mt5-raw-csv data\exports\gbpusd_m15_mt5_raw_bars.csv `
  --output-csv data\exports\gbpusd_short_h10_1_5_off_hours_mt5_raw_source_parity_dataset.csv `
  --overwrite
```

The exporter also writes a diagnostics JSON next to the output CSV. It includes
raw row count, exported row count, signal row count, gap count, and non-weekend
gap count.

## Comparator

After regenerating the MQL5 signal-only CSV from the current
`GBPUSD_FixedCandidate_SignalOnly.mq5`, compare against the raw-source Python
CSV. Regenerate this CSV after lifecycle metadata changes; stale MQL5 exports
can retain old `max_exit_time_server` values.

```powershell
python scripts\compare_fixed_candidate_mt5_ea_parity.py `
  --python-csv data\exports\gbpusd_short_h10_1_5_off_hours_mt5_raw_source_parity_dataset.csv `
  --mql5-csv data\exports\gbpusd_short_h10_1_5_off_hours_mql5_signal_only.csv `
  --output-dir reports\mt5_ea_parity_comparison\gbpusd_short_h10_1_5_off_hours_raw_source_signal_only_001 `
  --allow-extra-mql5-times
```

Use `--allow-extra-mql5-times` only when the MQL5 signal-only export contains
additional warm-up or context rows outside the Python raw-source export. Python
rows must still all match by `time_server`.

## Non-Goals

This workflow does not implement or authorize broker execution. It does not
change the StrategySpec, thresholds, SL/TP multipliers, spread policy, risk
policy, state, reports runtime, or the database.

The MQL5 prototypes in this phase must remain signal/export only. Execution,
broker preflight, position lifecycle management, retry, scheduling, and live
trading remain out of scope.
