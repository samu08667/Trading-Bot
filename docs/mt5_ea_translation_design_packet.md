# MT5 EA Translation Design Packet

This packet prepares the signal-only MQL5 translation work for
`gbpusd_short_h10_1_5_off_hours`. It intentionally stops before any EA
`OrderCheck` or `OrderSend` implementation.

## StrategySpec summary

Frozen StrategySpec:
`config/strategy_specs/gbpusd_short_h10_1_5_off_hours_strategy_spec.json`

Candidate:

- candidate_id: `gbpusd_short_h10_1_5_off_hours`
- symbol: `GBPUSD`
- timeframe: `M15`
- direction: `short`
- session: `hour_session=Off_hours`, broker/server hours `22` and `23`
- spread policy: `spread <= 15.0 broker_points`
- target family: `preferred_1_5atr_1atr_hit_first`
- horizon: `10` M15 bars
- max holding period: `10` closed M15 bars after entry
- no-weekend-hold: `true`
- last Friday entry time: `23:15` server time
- forced Friday flat time: `23:45` server time
- lifecycle exit policy:
  `close_at_market_after_10_closed_bars_if_sl_or_tp_not_hit`
- same-bar research policy: `stop_first`
- strategy_valid: `false`
- production_valid: `false`
- execution_enabled: `false`

The StrategySpec is an EA translation artifact, not an operational trading
policy change. Existing demo execution policy remains the source for risk caps
and broker-safety gates.

## Feature formulas

The signal-only EA prototype must reproduce these Python formulas from
`scripts/generate_price_features.py`:

- `true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))`
- `atr_20 = simple mean(true_range, 20)`
- `ma_fast = simple mean(close, 20)`
- `close_to_ma_fast_atr_20 = (close - ma_fast) / atr_20`
- `tick_volume_percentile_100 = count(window_tick_volume <= current_tick_volume) / 100`
- `hour_session` is mapped from broker/server hour:
  - Asia: `0..7`
  - London: `8..13`
  - New_York: `14..21`
  - Off_hours: `22..23`

Train-only bucket cutoffs:

| Feature | Required bucket | Low/mid cutoff | Mid/high cutoff |
| --- | --- | ---: | ---: |
| `close_to_ma_fast_atr_20` | `high_tercile` | `-0.4303672057741361` | `0.5954421525644814` |
| `tick_volume_percentile_100` | `mid_tercile` | `0.14` | `0.37` |

Bucket rules:

- low: `value <= low_mid_cutoff`
- mid: `low_mid_cutoff < value <= mid_high_cutoff`
- high: `value > mid_high_cutoff`

Signal rule:

```text
signal_bool =
  hour_session == Off_hours
  AND close_to_ma_fast_atr_20_bucket == high_tercile
  AND tick_volume_percentile_100_bucket == mid_tercile
  AND spread <= 15.0 broker_points
  AND close > 0
  AND atr_20 > 0
```

For a signal row:

- `entry_reference_price = closed_bar_close`
- `sl_price_preview = close + 1.0 * atr_20`
- `tp_price_preview = close - 1.5 * atr_20`

## Trade lifecycle time-exit requirement

The max holding period is not an entry signal rule. It is a future trade
lifecycle rule for an execution-capable EA after a position has already been
opened.

Frozen lifecycle contract:

- `max_holding_bars = 10`
- `timeframe = M15`
- `exit_policy = close_at_market_after_10_closed_bars_if_sl_or_tp_not_hit`
- `bar_count_basis = closed_bars_after_entry`
- `time_basis = mt5_server_time`
- `no_weekend_hold = true`
- `forced_friday_exit_enabled = true`
- `friday_last_entry_time_server = 23:15`
- `friday_forced_flat_time_server = 23:45`
- `max_exit_time_server = min(10th_future_m15_closed_bar_inside_export_window, friday_forced_flat_time_server)`
- priority: SL/TP first; time-exit only if the position is still open

The signal-only EA prototype must not close positions. It should only log this
requirement as a future execution constraint.

In MQL5, `MqlRates.time` is normally the opening timestamp of the candle. The
Friday `23:15` cutoff is an operational entry execution cutoff, not merely a
signal bar timestamp label. A future execution-capable EA must avoid opening a
new trade after `23:15` server time on Friday and must not carry a position
through the weekend.

The current parity dataset includes consecutive Python signals. A future
execution-capable EA must still enforce one-position-only: after opening a
position, it must ignore any subsequent signal while that position remains open.
Consecutive signal rows are parity evidence, not permission to stack positions.

A future execution-capable EA must:

- save the entry time and entry bar reference;
- count closed M15 bars after entry using MT5 server time;
- close the position at market when `bars_elapsed >= 10` if SL/TP has not
  already closed it;
- close the position at market by Friday `23:45` server time if SL/TP has not
  already closed it;
- avoid opening a new trade while the previous position is still open.

The bar count must use closed M15 bars from MT5 server time, not a local wall
clock timer, sleep interval, tick count, or workstation time.

## Parity dataset schema

Exporter:
`scripts/export_fixed_candidate_mt5_ea_parity_dataset.py`

The exporter opens the SQLite DB in read-only mode and exports rows from the
existing feature table. It writes only the requested CSV.

Required output columns:

- `time_server`
- `open`
- `high`
- `low`
- `close`
- `tick_volume`
- `spread`
- `atr_20`
- `ma_fast`
- `close_to_ma_fast_atr_20`
- `tick_volume_percentile_100`
- `hour_session`
- `close_to_ma_fast_atr_20_bucket`
- `tick_volume_percentile_100_bucket`
- `signal_bool`
- `entry_reference_price`
- `sl_price_preview`
- `tp_price_preview`
- `max_holding_bars`
- `max_exit_time_server`

`max_exit_time_server` is derived only when enough future rows are present in
the exported comparison dataset, except that an applicable Friday forced-flat
time may cap or supply the value. It is a parity-design aid, not a live close
instruction.

Suggested operator command for a local parity CSV:

```powershell
python scripts\export_fixed_candidate_mt5_ea_parity_dataset.py `
  --output-csv data\exports\gbpusd_short_h10_1_5_off_hours_ea_parity_dataset.csv `
  --limit 500
```

Do not use that CSV as a trade trigger. It is a feature/signal equivalence
fixture for MQL5 development.

## MQL5 signal-only prototype requirements

The first MQL5 artifact should be a signal-only EA or script:

- Load or hardcode the frozen StrategySpec constants.
- Run only on `GBPUSD` `M15`.
- Evaluate only newly closed bars, never the forming bar.
- Copy bars into an explicit oldest-to-newest buffer before rolling feature
  calculation.
- Compute ATR 20 as simple moving average of true range.
- Compute MA fast as simple moving average of close.
- Compute the inclusive 100-bar tick-volume percentile.
- Apply the exact bucket cutoffs.
- Apply the exact `hour_session` map using server time.
- Apply spread in broker points.
- Log all feature values, buckets, `signal_bool`, entry, SL, and TP.
- Filter the output range to match the Python parity CSV before comparing.
- Write a fresh CSV per run, skip duplicate `time_server` values, and keep the
  first 500 rows in chronological order for the current parity dataset.
- Log the lifecycle max holding rule for future execution work, without
  closing positions.
- Log the no-weekend-hold lifecycle metadata and compute
  `max_exit_time_server` as the earlier of the tenth future M15 bar inside the
  exported/raw-source comparison window and Friday `23:45` server time when
  applicable.
- Do not implement broker execution.
- Do not implement `PositionClose`.
- Do not implement retries, loops, schedulers, grids, martingale behavior, or
  production/live-account support.

## Validation criteria

Before any EA `OrderCheck` work:

- `time_server`/bar time must align to Python exported rows.
- `hour_session` must match 100%.
- `atr_20` must match within a strict floating tolerance.
- `ma_fast` must match within a strict floating tolerance.
- `close_to_ma_fast_atr_20` must match within a strict floating tolerance.
- `tick_volume_percentile_100` must match exactly or within `1e-12`.
- Both bucket columns must match 100%.
- `signal_bool` must match 100%.
- `entry_reference_price`, `sl_price_preview`, and `tp_price_preview` must match
  after symbol digit normalization.
- Spread gate must match in broker points.
- The exported `max_holding_bars` must be `10`. Any available
  `max_exit_time_server` value must correspond to the tenth closed M15 bar
  after the signal row inside the raw-source/export comparison window, except
  when the Friday `23:45` forced-flat no-weekend-hold cap applies. If neither
  value exists in that comparison window, `max_exit_time_server` must be blank.

Rows close to a threshold should be listed separately in the comparison report
so small floating differences are visible rather than hidden.

## What not to implement yet

Do not implement these in the first EA translation phase:

- `OrderCheck`
- `OrderSend`
- `PositionClose`
- time-exit execution
- broker payload construction
- position mutation
- request construction
- Python manual approval/digest workflow inside MQL5
- threshold recalibration
- DB writes
- full pilot send
- live-account support
- automatic retry
- loops, schedulers, or background polling
- changes to margin, spread, risk, SL, TP, or volume policy

## Recommended next step

Generate a parity CSV from the current Python feature table, then build a
signal-only MQL5 prototype that emits a comparable CSV. The next architectural
gate should be a Python-vs-MQL5 comparison report, not an execution module.
