# Cost Model

When modifying cost assumptions or cost-related outputs, update this document if the change affects interpretation, configuration, or research workflow.

This project uses costs only as offline research accounting. The cost model estimates how spread, slippage, and commissions would reduce a direction-aware research return. It does not simulate real order execution and does not create trading signals.

## Return Components

`gross_strategy_return` is the direction-aware return before estimated execution costs:

- Long research uses `future_return_H`.
- Short research uses `-future_return_H`.

`estimated_cost_return` is the total offline cost estimate for a research sample:

```text
estimated_cost_return = spread_cost_return + slippage_cost_return + commission_cost_return
```

`net_strategy_return` subtracts the estimated cost from the gross return:

```text
net_strategy_return = gross_strategy_return - estimated_cost_return
```

Gross and net outputs must stay separate. Gross results show the raw statistical relationship. Net results show that same relationship after an estimated cost haircut.

## Default Research Mode

Cost-aware research, validation, and post-validation scripts default to:

```text
--cost-mode estimated --return-mode net
```

Gross comparison remains available explicitly:

```text
--cost-mode none --return-mode gross
```

`--return-mode net` with `--cost-mode none` must fail because net without costs is misleading. `--overwrite` and `--overwrite-validation` are not defaults and must remain explicit when regenerating existing outputs.

The existing orchestration scripts perform a lightweight preflight before starting child stages. `scripts/run_full_research_pipeline.py` and `scripts/run_research_validation_pipeline.py` fail early when cost/return modes are incompatible, when estimated mode is requested without an explicit `--cost-config`, or when a provided cost config path is missing or invalid JSON. This preflight is offline configuration validation only; it does not imply live readiness.

In the full pipeline, the same `--cost-config` is also passed to price-feature generation as point-size metadata. This contract is intentional because `generate_price_features.py` can read `symbols.<SYMBOL>.point_size` from the cost config. Local broker configs still need to be verified before relying on estimated-net outputs.

## Spread Cost

MetaTrader 5 spread values are commonly stored in points, not directly as a return. The research cost model converts spread points into a price distance and then into a return:

```text
spread_price = spread_points * point_size
spread_cost_return = spread_price / close
```

The price-feature layer uses the same unit conversion:

```text
spread_price = spread_points * point_size
spread_return = spread_price / close
spread_to_atr_20 = spread_price / atr_20
```

Raw `spread` and `spread_avg_20` remain MT5 points. ATR is in price units, so `spread / atr_20` is not unit-consistent and should be considered stale methodology in older generated outputs.

The spread source is chosen per symbol from the available research row and cost config:

1. Current-row `spread`, when present and finite.
2. `spread_avg_20`, when current-row `spread` is not available.
3. Configured `fallback_spread_points`, when the dataset does not provide a usable spread column.

`fallback_spread_points` is a research fallback, not a broker quote. It should be verified before trusting estimated-net results.

## Pip-To-Point Conversion

Broker spread tables often quote FX spreads in pips, while this cost model expects `fallback_spread_points` in MT5 points.

For the major FX examples used here:

- 5-digit non-JPY FX pairs use `point_size = 0.00001` and `1 pip = 10 points`.
- 3-digit JPY FX pairs use `point_size = 0.001` and `1 pip = 10 points`.

Therefore, a table value of `0.1` pip becomes `1` fallback spread point, and a table value of `1.3` pips becomes `13` fallback spread points.

Pepperstone example configs follow this rule because the user-provided table values are assumed to be pips, while the scripts consume MT5 points.

## Pepperstone Example Configs

Versioned research-only examples are provided for the user-supplied Pepperstone major FX table:

```text
config/brokers/pepperstone_razor.example.json
config/brokers/pepperstone_standard.example.json
```

These examples use average spread values as `fallback_spread_points`, not minimum spread values. Average spread is a better fallback than minimum spread because minimum spread is often an ideal or brief market condition and can understate normal research costs.

For conservative research, average spread is still only a starting point. A p75, p90, or p95 spread calibration from MetaTrader 5 exports or the local SQLite database is preferred because it captures local symbol naming, session mix, broker/account conditions, volatility, and tail spread behavior.

The Pepperstone examples include only the FX symbols present in the user-provided table: `AUDUSD`, `EURUSD`, `GBPUSD`, `USDCAD`, `USDCHF`, and `USDJPY`. `XAUUSD` is intentionally omitted because no Pepperstone XAUUSD spread value was provided.

## Historical Spread Calibration

`scripts/analyze_historical_spreads.py` reads local SQLite spread history only. It prefers `price_bars.spread`, falls back to `price_features.spread_avg_20` when needed, and never invents spreads when neither column exists.

The script writes p75, p90, and p95 spread summaries under `reports/cost_model/historical_spreads/{RUN_ID}/`. With `--generate-config`, it can create ignored local configs such as `config/brokers/pepperstone_historical_p90.local.json`. These configs are offline estimates from local data, not broker-official settings.

`scripts/compare_mt5_recent_spreads.py` can compare recent read-only MT5 tick spreads from the currently logged-in terminal against those local DB spread statistics. It writes diagnostics under `reports/cost_model/mt5_spread_comparison/{RUN_ID}/`, does not create cost configs, and must not be used as an execution signal.

## Slippage And Commissions

Slippage is configured as basis points with `slippage_bps_round_trip`. It estimates the round-trip cost of execution uncertainty.

Commissions are configured as basis points with `commission_bps_round_trip`. They estimate round-trip commission cost.

Both are offline assumptions. Real slippage and commissions can change by broker, account type, symbol, session, volatility, order size, and execution method.

## Point Size

`point_size` is the price value of one broker-reported point for a symbol. It is required to convert spread points into price distance.

Point size depends on the exact broker and symbol definition. For example, broker suffixes, metals, JPY pairs, CFDs, account types, and quote precision can all change how a point maps to price. Always verify `point_size` against MetaTrader 5 Symbol Info for the exact exported symbol before relying on net results.

Internal no-config point-size defaults are limited to common FX symbols: `EURUSD`, `GBPUSD`, `AUDUSD`, `USDCAD`, `USDCHF`, and `USDJPY`. XAUUSD and other CFDs require a config-driven or explicit `point_size`; a versioned example may include placeholders, but it is a template, not proof of correctness for a specific broker.

For price-feature generation, local symbol metadata can be supplied with:

```text
--point-size-config config/symbol_metadata.local.json
```

The local file may use top-level symbol entries such as `XAUUSD.point_size`. For the observed read-only MT5 XAUUSD metadata, `point=0.01` maps to `point_size=0.01`. A current spread snapshot, for example 24 points, is only a temporary observation and must not be used as a fixed historical spread. Historical spread remains `price_bars.spread`.

## Strict Cost Config

Use `--strict-cost-config` with `--cost-mode estimated` when estimated-net results should be treated as more than a rough exploratory view.

Strict mode requires every requested symbol to have an explicit:

```text
symbols.<SYMBOL>.point_size
```

It also requires a usable spread source: either finite `spread` or `spread_avg_20` values in the dataset, or configured `fallback_spread_points`.

Without strict mode, scripts can fall back to backward-compatible internal defaults and print warnings when defaults are used. Those warnings mean the net report is only a rough estimate.

## Effective Cost Diagnostics

Cost-aware reports should make it clear which configured fields were actually reached by the cost source priority.

Single-candidate stress reports include base/stress diagnostics for the replayed symbol: cost config source, point-size source/value, spread-source counts across replayed trades, row-level and fallback spread counts, max-row-or-fallback fallback-selection counts, fallback spread source/value, whether fallback spreads were actually used, selected stress spread policy, effective slippage/commission bps, `stress_changed_cost_R`, and mean cost/net deltas. When base and stress configs have no effect on `cost_R` or `net_R`, the report writes a no-effect explanation.

For example, p75/p90 configs that differ only in `fallback_spread_points` will not change costs when every replayed row has a finite current-row `spread`, because row-level spread is used before configured fallback values.

`scripts/validate_regime_candidate_stress.py` keeps that normal source priority by default with `--stress-spread-policy standard`. For explicit research-only sensitivity checks, `--stress-spread-policy max_row_or_fallback` uses `max(row spread or spread_avg_20, configured fallback)` for stress costs, and `--stress-spread-policy fallback_override` uses the configured fallback spread for stress costs when it is available. These modes only change offline stress cost accounting; they do not alter candidate selection, features, TP/SL, horizon, path exits, or any live execution behavior.

## Offline Estimate Boundary

Estimated net return is an offline estimate, not a real execution simulation. It does not model queue position, fill quality, rejected orders, partial fills, latency, order type, stop-loss/take-profit placement, market impact, changing intra-bar spread, or broker-specific execution rules.

Therefore, net reports are useful for research triage, but they are not live-ready performance claims and not a recommendation to buy, sell, open, close, or size a position.

## Config Files

The versioned template is:

```text
config/cost_model.example.json
```

Broker-specific and local configs should not be committed because they may contain private account assumptions, broker conventions, symbol suffixes, and cost policies that are local to one environment.

Future local usage should prefer ignored files such as:

```text
--point-size-config config/symbol_metadata.local.json
--cost-config config/cost_model.local.json
--cost-config config/brokers/NOME.json
--cost-config config/brokers/pepperstone_razor.local.json
```

Versioned broker examples may use the `.example.json` suffix, for example:

```text
config/brokers/example_broker.example.json
config/brokers/pepperstone_razor.example.json
config/brokers/pepperstone_standard.example.json
```

## Command Examples

[Back to README](../../README.md) | [Pipeline usage](PIPELINE_STEPS.md#detailed-usage-reference)

Run from the repository root with local inputs. Example configs are templates;
verify symbol point sizes and account-specific assumptions before interpreting
net results. The final comparison command connects to MT5 and is separate from
offline validation.

Full pipeline examples with estimated net returns:

```powershell
python scripts/run_full_research_pipeline.py --skip-calendar-import --skip-price-import --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --cost-mode estimated --return-mode net --cost-config config/cost_model.example.json --strict-cost-config --start-year 2022 --end-year 2024 --overwrite-validation
python scripts/run_full_research_pipeline.py --skip-calendar-import --skip-price-import --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction short --cost-mode estimated --return-mode net --cost-config config/cost_model.example.json --strict-cost-config --start-year 2022 --end-year 2024 --overwrite-validation
```

Walk-forward can use the same estimated net mode:

```powershell
python scripts/run_walk_forward_research.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --train-start-year 2020 --first-test-year 2022 --last-test-year 2025 --cost-mode estimated --return-mode net --cost-config config/cost_model.example.json --strict-cost-config --purge-overlap --embargo-bars 0
```

Historical spread calibration can be run offline from the local SQLite database without MetaTrader5:

```powershell
python scripts/analyze_historical_spreads.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --generate-config --overwrite
```

Recent MT5 spreads from the currently logged-in terminal can be compared with local DB spread history in read-only diagnostic mode:

```powershell
python scripts/compare_mt5_recent_spreads.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --mt5-lookback-hours 24 --broker-name Pepperstone --account-type Razor --overwrite
```
