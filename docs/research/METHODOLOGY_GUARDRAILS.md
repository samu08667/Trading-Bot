# Methodology Guardrails

When modifying the pipeline, update this document if the change affects scripts, outputs, methodology, or next actions.

These rules define how research outputs should be generated and interpreted. They are intended to prevent leakage, premature conclusions, and accidental drift toward live trading.

## Core Rules

- ML generates hypotheses, not live trading signals.
- Features may use only information available at the current row or in the past.
- Targets may look into the future because they are labels for supervised research.
- Economic calendar `actual`, `forecast`, `previous`, revised values, and surprise-derived values must not be used as pre-news features unless a future implementation proves they are time-safe.
- Raw price levels such as `open`, `high`, `low`, and `close` are excluded from ML feature selection and robust final promotion because they are not tradable rules by themselves.
- Raw `tick_volume` and raw spread points are excluded from ML feature selection when contextual volume and normalized spread features are available.
- `numeric_tercile` is excluded from final validation and walk-forward promotion until thresholds are computed in a train-only, time-safe way.
- Long and short research must remain separate.
- Gross and net research must remain separate.
- Cross-pair and pair-specific candidates must remain separate.
- A cost model is required before trusting results for anything beyond gross exploratory analysis.
- Overlapping labels must be controlled with purge, embargo, or non-overlap evaluation where applicable.
- Random baseline robustness may test final candidates against same-trade-count random samples, but it must not search for new strategy rules.
- Candidate baseline diagnostics may compare final candidates with their own single-filter, leave-one-out, and conditional random contexts, but they must not create new strategy candidates.
- Horizon consistency may compare already-produced h5/h10/h20 scorecards, but it must not rerun backtests or promote a feature into a strategy by itself.
- Volume and `tick_volume` features are context and liquidity filters, not autonomous signals.
- The final feature scorecard lists ingredients for future backtests, not a tradable strategy.
- The research decision report is triage for future research only; `CANDIDATA_A_TEST_SUCCESSIVI` is not a live-ready strategy.
- No output equals a recommendation to buy, sell, hold, open, close, or size a trade.

## Time Safety

Feature generation must avoid future information. A row can use:

- Current and previous OHLCV bars.
- Rolling or expanding calculations that do not include future rows.
- Known timestamp, session, symbol, timeframe, and past/current calendar timing.
- News timing and importance when available before the row.
- True range, ATR, ATR-normalized candle shape, ATR-normalized moving-average distance, and volatility ratios when they are calculated from current/past rows only.
- Spread price/return and spread-to-ATR features when raw MT5 spread points are converted with symbol-level `point_size` before comparing with price-unit ATR.
- XAUUSD and other non-FX point sizes from explicit arguments or ignored local symbol metadata; current spread snapshots are diagnostics only, not model defaults.

A row must not use:

- Future returns except in target columns.
- Future max/min return, future range, MFE, MAE, or `target_*_good_*` columns except as supervised labels.
- Future event outcomes.
- Full-sample thresholds that would reveal future distributions.
- Test-period distribution information while selecting train-period hypotheses.

Future-path labels can be useful because close-to-close return alone misses intrahorizon path quality. MFE/MAE and h5/h10/h20 triple-barrier labels describe future path outcomes, but they remain labels for offline supervised learning and validation only. Triple-barrier labels use current-bar `atr_20`; future OHLC is used only to decide the label outcome. Same-bar TP/SL touches are labeled with conservative `stop_first`. They are not trade entries, exits, or buy/sell instructions.

## ML Interpretation

ML reports rank features and suggest hypotheses. They are exploratory evidence only.

Useful ML outputs can justify a controlled research backtest, but they cannot justify live execution, autonomous strategy execution, or a trader-facing recommendation by themselves.

Accuracy is often misleading for imbalanced targets because a model can look accurate while barely finding positive cases. Precision, recall, F1, ROC AUC, average precision, base-rate lift, and return diagnostics should be read together.

Raw `future_return_{H}` is not direction-aware. In short research, negative raw future returns are favorable and positive raw future returns are unfavorable, so ML reports must use directional-return columns equal to `-future_return_{H}` for short return interpretation.

`threshold_analysis.csv` is a diagnostic sweep over test-set probabilities. It helps show how precision, recall, lift, and selected-row raw and directional returns change under hypothetical cutoffs, but it does not set a global threshold, create a signal, or change the selection methodology.

ML target-comparison reports may compute `average_precision_lift_vs_base` and a `recommended_research_threshold` field for comparing target diagnostics. Average precision should be compared with the target base positive ratio. The recommended research threshold is a conservative diagnostic summary only; it is not an execution cutoff, live signal, or strategy rule.

For FX M15 h10 ML research, current target-comparison diagnostics favor `long_tp_2atr_sl_1atr_hit_first_10` for long and `short_tp_2atr_sl_1atr_hit_first_10` for short. Directional `target_up_10` / `target_down_10` and good-path `target_long_good_10` / `target_short_good_10` targets remain benchmark references, not the preferred target for current FX ML ranking work. XAUUSD remains separate review because its best tested 2ATR/1ATR target did not pass conservative recommended-threshold criteria.

Preferred-target feature-stability reports summarize whether feature rankings recur across EURUSD, GBPUSD, and USDJPY. They should be read as a transparent count-and-rank diagnostic only. Recurrence across feature-ranking files does not prove robustness, profitability, or strategy validity, and permutation importance should be treated as noisy.

Preferred feature hypothesis shortlists classify stable ML features into research roles and caution levels. Raw or scale-dependent features such as moving-average levels, raw ranges, raw ATR, raw tick-volume averages, and raw spread averages may remain in the shortlist for review, but normalized variants should be preferred for controlled tests when available.

## Backtest Interpretation

Exploratory backtests and combined hypothesis backtests are research filters. They can identify weak or promising ingredients, but they are not complete trading strategies.

Preferred feature backtest reports are another exploratory layer. They reuse the existing single-feature bucket backtest workflow for prioritized normalized/contextual shortlist features, keep long and short separate, and exclude XAUUSD by default. Read each row against its same-symbol baseline and treat zero-trade conditions as untestable, not as normal evidence. `scenario_source` must be checked before treating a row as preferred-shortlist evidence, because standard/default backtest context can also appear unless `--strict-shortlist-only` was used. Their feature filters are not trading signals, and aggregate rows do not prove cross-symbol robustness.

Gross/none preferred-feature reports are diagnostic only. Estimated/net results are required for serious evaluation, and a gross edge erased by estimated costs is not a survivor.

Preferred feature combination backtests are a controlled follow-up only after the gross/net preferred-feature comparison. They should test small two-filter pairs, not exhaustive grids, and should pair momentum/returns or trend/MA ingredients with liquidity, volatility, range, or spread context filters. Long and short, symbols, and gross/net modes must remain separate. Zero-trade combinations are untestable and must be skipped. A net survivor must have positive net mean return, net profit factor above 1, conservative trade count, and no severe concentration issue; even then it remains a research lead only.

TP/SL path-exit diagnostics are fixed-assumption follow-ups for already-discovered filters. Batch mode may evaluate existing preferred-feature combination detail rows, but it must not create new pairs, weaken classification thresholds, or change TP/SL/horizon values based on row performance. Source close-to-close results are context only; the path-exit classification must come from the fixed path diagnostic metrics and baseline comparison.

Research branch outcome reports are closure records for already-tested branches. They may summarize that a branch is closed under current feature and cost assumptions, but they must read existing outputs only and must not restart candidate discovery, rerun diagnostics, adjust TP/SL, add features, or imply operational readiness.

Preferred horizon/cost diagnostics are sensitivity orchestration over existing scripts. They may compare h5, h10, and h20 behavior and p50, p75, and p90 local cost assumptions, but XAUUSD must stay separate from the FX group, TP/SL values must remain fixed for a branch, and child scripts must retain their own guardrails.

Branches with zero tested TP/SL path rows must be labeled separately as `NO_TESTED_COMBINATIONS`. They are not review candidates and are not closed survivors or failures; they indicate the branch lacked evaluated path rows and requires input/skipped-output inspection.

Zero-tested diagnostics may read existing matrix and child CSV outputs to count where rows disappeared across preferred-feature summaries, cost comparisons, controlled combination inputs, and TP/SL path batches. These diagnostics are audit records only; they must not rerun child scripts, introduce new combinations, add features, or change TP/SL settings.

Preferred horizon prerequisite diagnostics may check existing `ml_dataset` target columns and preferred shortlist files before a horizon run. They are availability and balance audits only; they must not generate labels, build new shortlists, run preferred-feature backtests, or alter target/feature selection.

Preferred horizon shortlist builds may fill missing h5/h20 preferred ranking and shortlist inputs only by reusing the existing target-specific ML research, preferred-target feature stability, and preferred feature hypothesis shortlist methodology. They must not add features, search combinations, run preferred-feature backtests, optimize TP/SL, or weaken feature-safety exclusions.

Before a candidate can be considered for later strategy design, it needs:

- Direction-specific validation.
- Gross and estimated-net review.
- Cost-model audit.
- Yearly stability.
- Walk-forward evidence.
- Concentration checks.
- Random baseline robustness review.
- Baseline diagnostics review to confirm a combination adds value beyond single filters and contextual random samples.
- Horizon consistency review across nearby target horizons.
- A separate rule-based research backtest with explicit entry, exit, risk, and execution assumptions.

## Random Baseline Discipline

Random baseline tests compare already-final candidates against random samples with the same number of trades from the same universe. They are permutation-style robustness checks, not feature search and not strategy discovery.

Random baseline outputs can downgrade confidence in a candidate that does not beat chance-like sampling. They cannot promote a candidate to live trading and cannot be read as an operational signal.

## Baseline Diagnostics Discipline

Candidate baseline diagnostics test only already-final candidates. They may decompose a candidate into its existing single filters and leave-one-out contexts to check whether the full combination adds incremental value, but they must not search for new feature combinations.

Diagnostics such as `adds_incremental_value` or `mostly_single_filter_effect` are research labels only. They do not create signals, do not replace walk-forward validation, and do not replace a future rule-based research backtest.

When candidate baseline diagnostics are launched by the full pipeline final-review shortcut, the orchestration default is 100 random runs to keep the full run practical. Use the standalone diagnostics script with 250 or more random runs for a heavier final review.

## Horizon Consistency Discipline

Horizon consistency compares feature and condition evidence across h5, h10, and h20 final scorecards. It is a stability lens, not a new backtest and not a candidate discovery step.

Labels such as `consistent_across_horizons`, `consistent_medium_slow`, or `short_horizon_only` describe research behavior across target horizons. They are not buy/sell instructions, not strategy definitions, and not substitutes for random baseline checks, baseline diagnostics, walk-forward validation, or rule-based backtests.

## Decision Report Discipline

The research decision report may summarize final outputs into `SCARTARE`, `DA_APPROFONDIRE`, and `CANDIDATA_A_TEST_SUCCESSIVI`. These labels are research workflow labels only.

`CANDIDATA_A_TEST_SUCCESSIVI` means a candidate can be considered for a future rule-based research backtest. It does not mean buy, sell, live-ready, or complete strategy.

## Fixed-Candidate Audit Discipline

Candidate-audit scripts read existing stress, replay, timeout, and gate-decision output folders for one fixed candidate. They must not search new features, add filters, optimize TP/SL, rerun candidate discovery, add multi-timeframe logic, or create operational instructions.

Exact-candidate scope must remain separate from broad-regime diagnostics. A broad-regime result can explain context, but it must not be promoted as evidence for the exact candidate unless the exact feature condition, direction, timeframe, horizon, regime, and cost mode are preserved.

Timeout-excluded diagnostics are biased because they remove existing TIMEOUT rows from an already selected replay. They may explain fragility, but they are not validated performance. Extended h20/h40/h80 timeout diagnostics inspect sensitivity for existing h10 timeout entries only. They are not replacement timeout rules and must not be read as horizon optimization.

`TIMEOUT_POLICY_SENSITIVITY_REJECTED` means the alternative timeout policies were rejected. If the original h10 stress metrics remain strong, this label does not automatically reject the original h10 candidate. A gate decision can allow limited offline baseline/cost-sensitivity review only under the original h10 timeout rule, with the timeout caveat preserved.

## Cost Discipline

Gross results are useful for understanding raw statistical relationships. Net results are required before trusting a candidate as a practical research lead.

Cost-aware research, validation, and post-validation scripts default to `--cost-mode estimated --return-mode net`. Gross/none remains available only when passed explicitly with `--cost-mode none --return-mode gross`; `--return-mode net` with `--cost-mode none` must fail.

Long-running orchestration scripts must fail before child stages start if their cost/return configuration is invalid or ambiguous. Estimated orchestration requires an explicit readable JSON `--cost-config`; gross/none remains the explicit comparison mode. This preflight is an offline guardrail and must not be presented as operational readiness.

Estimated net results must be treated carefully because spread, slippage, commission, broker point size, account type, symbol suffixes, and session conditions can change the conclusion.

MT5 spread is stored as points while ATR is in price units. Any spread-to-ATR feature must use `spread_price = spread_points * point_size` before dividing by `atr_20`; old generated outputs using `spread / atr_20` should be treated as stale unless regenerated.

Explicit stress spread policies are research-only sensitivity controls. The default must preserve normal row-level spread priority, while max/override fallback spread policies may only change offline cost accounting for a fixed candidate replay; they must not change feature filters, target families, TP/SL, horizon, regime logic, candidate selection, path exits, position sizing, or execution behavior.

Use `docs/research/COST_MODEL.md` as the interpretation reference for gross strategy return, estimated cost return, strict cost config, point size, spread source policy, and local broker-specific config rules.

Pepperstone example configs under `config/brokers/*.example.json` are versioned research templates only. Local broker configs such as `config/brokers/pepperstone_razor.local.json` must stay uncommitted and should be passed explicitly with `--cost-config`.

Payoff ratio, breakeven win rate, and breakeven win-rate margin are descriptive return-quality metrics. They can help diagnose whether a result depends on win rate, payoff size, or both, but they are not strategy rules or live signals.

Cost-aware labels are intentionally not generated directly in `ml_dataset` yet. Net labels would require broker-verified point sizes, spread-source policy, slippage, commission, symbol suffix handling, and a clear decision about whether labels should be gross, estimated-net, or both. Calculating net labels inside dataset generation too early could bake mutable cost assumptions into reusable labels and blur the separation between gross and net research.

## Output Discipline

Generated CSVs, SQLite databases, reports, and logs are local artifacts. They are not source documentation and should not be committed.

Overwrite behavior must remain explicit and opt-in. Do not make `--overwrite` or `--overwrite-validation` a default behavior.

Full-pipeline final-review outputs must also require explicit `--overwrite-final-review`. `--overwrite-validation` must not imply final-review overwrite.

Local broker-specific cost configs such as `config/cost_model.local.json` and `config/brokers/*.json` are also local artifacts and should not be committed; only `.example.json` broker templates are versionable.

Versioned documentation should describe how to interpret outputs, not embed run-specific results.

## Trading Boundary

The research pipeline must not include:

- Live trading.
- `order_send`.
- Operational signal generation.
- Autonomous execution.
- Position opening or closing logic.
- Broker credential handling.

The pipeline can import historical data, generate features, run offline research, and produce versioned methodology documentation.
