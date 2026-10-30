# Regime Classification Diagnostics

These columns are lightweight descriptive labels for offline research
diagnostics. They are derived only from current-row or past-known fields in the
feature pipeline. They do not use future targets, TP/SL outcomes, news actuals,
forecasts, surprises, or broker execution data.

## Columns

- `session`: derived from `hour` or `time_server` using server-hour buckets.
  - `Asia`: 00:00-07:59
  - `London`: 08:00-12:59
  - `London_NewYork_Overlap`: 13:00-16:59
  - `New_York`: 17:00-21:59
  - `Off_hours`: 22:00-23:59

- `spread_liquidity_regime`: first available source from
  `spread_to_atr_20`, `cost_to_atr`, `estimated_cost_R`, `spread_return`, or
  `spread_to_volume_ratio`.
  - Ratio buckets: `<=0.05 low_spread`, `<=0.15 normal_spread`,
    `<=0.30 high_spread`, otherwise `extreme_spread`.
  - `spread_return` fallback buckets: `<=0.00005 low_spread`,
    `<=0.00015 normal_spread`, `<=0.00030 high_spread`, otherwise
    `extreme_spread`.

- `volatility_regime`: first available source from `volatility_ratio_20_100`
  or `volatility_100`.
  - Ratio buckets: `<=0.75 low_volatility`, `<=1.25 normal_volatility`,
    `<=1.75 high_volatility`, otherwise `extreme_volatility`.
  - `volatility_100` fallback buckets: `<=0.0005 low_volatility`,
    `<=0.0015 normal_volatility`, `<=0.0030 high_volatility`, otherwise
    `extreme_volatility`.

- `range_regime`: derived from `range_to_atr_20`.
  - `<=0.60 compressed_range`, `<=1.40 normal_range`,
    `<=2.20 expanded_range`, otherwise `extreme_range`.

- `volume_liquidity_regime`: first uses `volume_spike_20` and
  `volume_dry_up_20`, then falls back to `tick_volume_zscore_100`,
  `tick_volume_percentile_100`, or `volume_vs_session_avg`.
  - Spike flag or very high fallback values: `volume_spike`.
  - High fallback values: `high_volume`.
  - Dry-up flag or low fallback values: `dry_volume`.
  - Otherwise: `normal_volume`.

## Interpretation

These labels are descriptive research diagnostics only. Static thresholds are
chosen for interpretability and reproducibility. They should be reviewed before
any deployment-oriented use, especially when a fallback threshold is applied
across symbols with different pricing or liquidity behavior.

## Legacy table fallback

Older `price_features`, `market_features`, or `ml_dataset` tables may have the
source columns above without the research label columns. Current generation and
diagnostic loading code fills blank or absent regime labels from the current row
in memory. If a source group is absent, the label remains blank/NULL and
`scripts/check_ml_dataset.py --regime-schema-only` reports the missing source
availability explicitly.
