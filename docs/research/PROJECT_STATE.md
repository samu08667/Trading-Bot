# Project State

When modifying the pipeline, update this document if the change affects scripts, outputs, methodology, or next actions.

## Objective

Trading-Bot combines offline market-data research with a narrowly scoped GBPUSD M15 demo-only execution prototype. Research prepares datasets and evaluates feature hypotheses; the fixed-candidate execution stage is documented below.

Research and execution currently share this repository and codebase, including feature and candidate definitions. Future research development is moving to a separate repository; that separation is in progress, and the research tools here remain part of the published snapshot. This project does not support live-account trading or unattended operation.

[Back to README](../../README.md) | [Research usage](PIPELINE_STEPS.md#detailed-usage-reference)

## Stack

- MetaTrader 5 for manual economic calendar export and read-only historical OHLCV bar access.
- Python for orchestration, feature generation, research analysis, validation, and reports.
- SQLite for local research tables under `data/trading_bot.db`.
- ML research tooling for offline feature ranking and hypothesis generation.

## Current Implemented State

- Database schema initialization for economic events, price bars, price features, market features, and ML datasets.
- Manual MT5 economic calendar export through `mql5/ExportEconomicCalendar.mq5`.
- Read-only MT5 price-bar import through `copy_rates_range()`.
- Price feature generation from historical OHLCV bars, including time-safe ATR/range, volatility, spread, session, and liquidity context features.
- Market feature generation from price features plus economic-calendar timing.
- ML dataset generation with future-return targets plus supervised future-path labels such as MFE, MAE, and long/short good-path targets.
- Offline ML feature research reports.
- ML target-comparison diagnostics across target-specific ML report folders.
- Preferred-target feature-stability diagnostics for recurring FX ML features across EURUSD, GBPUSD, and USDJPY.
- Preferred feature hypothesis shortlist reports that classify stable ML features for later controlled research tests.
- Preferred feature backtest launcher/reporting for prioritized normalized/contextual FX shortlist features.
- Fixed TP/SL path-exit diagnostics for already-discovered filter combinations, with R-multiple accounting and baseline comparison. The diagnostic can run one explicit fixed-filter candidate or batch-evaluate already-generated preferred-feature combination detail rows without creating new combinations or changing TP/SL settings.
- Exploratory feature-bucket backtests.
- Combined hypothesis backtests.
- Combined hypothesis evaluation.
- Yearly validation by symbol and direction.
- Walk-forward research validation with train-period selection and future out-of-sample testing.
- Random baseline robustness testing for final candidates with same-trade-count random samples.
- Candidate baseline diagnostics for checking incremental value against single-filter, leave-one-out, and contextual random baselines.
- Final feature scorecard generation.
- Horizon consistency reporting across h5, h10, and h20 scorecards.
- Research-only decision report generation for final candidate triage.
- Research-only branch outcome reporting for closing rejected research branches from existing diagnostic outputs.
- Preferred horizon/cost diagnostic orchestration for controlled h5/h10/h20 and p50/p75/p90 sensitivity planning across FX and separate XAUUSD groups, including read-only zero-tested branch diagnostics for existing matrix runs.
- Preferred horizon prerequisite diagnostics for checking whether target columns and preferred shortlist inputs exist before preferred-feature horizon runs.
- Preferred horizon shortlist generation that reuses target-specific ML research, preferred-target feature stability, and preferred feature hypothesis shortlist scripts for configured h5/h10/h20 inputs without adding features or running backtests.
- Regime candidate stress validation for one fixed historical candidate, with exact-feature-scope replay, sequential/no-overlap diagnostics, optional cost stress, random baseline summaries, effective-cost-field diagnostics that explain no-effect cost stresses, and explicit research-only stress spread policies for row-level spread versus configured fallback sensitivity.
- Fixed-candidate audit packaging from existing stress outputs, rule-replay outputs, controlled expansion outputs, timeout fragility/root-cause/sequence reviews, timeout-policy sensitivity diagnostics, and gate-decision reports.
- Candidate-audit summary, warning, and next-action CSVs now expose common research-audit fields such as `final_classification`, `decision_scope`, `warning_code`, `blocking`, `related_stage`, and `forbidden_actions` while preserving stage-specific final labels.

## Direction Support

Long and short research are supported separately.

- Long research uses `target_up_{H}` and `future_return_{H}`.
- Short research uses `target_down_{H}` and direction-aware returns equivalent to `-future_return_{H}`.
- ML threshold and correlation diagnostics keep raw `future_return_{H}` and direction-aware returns separate; short raw returns should not be read directly as favorable or unfavorable without the direction-aware sign flip.
- Long and short outputs must not be mixed when reading, validating, or summarizing results.

## ML Target Preference

Recent M15 h10 target-comparison diagnostics across EURUSD, GBPUSD, USDJPY, and XAUUSD support using the 2ATR/1ATR triple-barrier hit-first labels as the preferred FX ML research targets:

- Long FX: `long_tp_2atr_sl_1atr_hit_first_10`.
- Short FX: `short_tp_2atr_sl_1atr_hit_first_10`.

`target_up_10`, `target_down_10`, `target_long_good_10`, and `target_short_good_10` remain useful benchmark/reference targets for comparison. XAUUSD should stay in separate review: the 2ATR/1ATR target was best among tested XAUUSD targets, but it did not pass the conservative recommended-threshold diagnostics. This preference is only ML research guidance; it does not change model training logic, backtest selection, live readiness, or strategy validity.

`scripts/build_preferred_target_feature_stability.py` can summarize which features recur across the preferred FX target-specific ML reports. It is a diagnostic ranking for hypothesis discovery only; recurrence across symbols does not prove strategy validity.

`scripts/build_preferred_feature_hypothesis_shortlist.py` can turn those stability rows into a preferred feature hypothesis shortlist with family, role, normalized/raw status, usage, and caution fields. It is a research triage report only and does not promote features into strategies.

`scripts/build_preferred_horizon_shortlists.py` can build the same preferred target ranking and shortlist inputs for configured horizons. It reuses the existing h10 methodology, keeps the stability symbol set explicit, and excludes future/target label columns through shared feature-safety rules.

`scripts/run_preferred_feature_backtests.py` can feed the preferred shortlist into the existing single-feature bucket backtest workflow and summarize per-symbol plus aggregate exploratory rows. It reports scenario conditions, source tags, buckets, baseline deltas, and skipped or zero-trade conditions. It excludes XAUUSD by default and does not change full-pipeline defaults or backtest selection methodology.

`scripts/compare_preferred_feature_backtest_cost_modes.py` can compare existing gross/none and estimated/net preferred-feature runs, preserve scenario-source and shortlist metadata, report source-tag diagnostics, and flag rows where estimated costs erased a gross edge. This comparison is diagnostic and does not change the cost model or backtest methodology.

`scripts/run_preferred_feature_combination_backtests.py` can read those cost-mode comparison rows and test a small controlled set of two-filter preferred-feature combinations. It keeps symbols and directions separate, excludes XAUUSD by default, pairs momentum/trend ingredients only with liquidity, volatility, range, or spread context filters, routes zero-trade combinations to skipped output, and reports candidate diagnostics for each filter stage. It is exploratory research only and does not add execution, position sizing, stops, targets, multi-timeframe logic, or live readiness.

## Gross And Net Support

The research pipeline supports both gross and estimated-net return modes.

- Gross mode keeps the raw direction-aware future return.
- Net mode subtracts an estimated cost return from the gross strategy return.
- Gross and net outputs must be read separately.
- Net results depend on the configured cost assumptions and broker-specific point sizes.

## Cost Model

The cost model is implemented as offline research accounting, not live execution logic.

- The example configuration lives at `config/cost_model.example.json`.
- Estimated costs can include spread, slippage, and commission assumptions.
- Strict cost configuration should be used before trusting net results.
- Point sizes must be verified against the exact broker symbol exported from MT5.

## Validation Support

### Yearly Validation

Yearly validation checks whether selected combined hypotheses remain stable across years and symbols. It produces final research candidates and pair-specific candidates, but it does not create operational trading signals.

### Walk-Forward Validation

Walk-forward validation is stricter than yearly validation. Each fold selects candidates using only past train years and tests them on a future out-of-sample year. It keeps cross-pair and pair-specific results separate.

## Candidate Types

### Cross-Pair Candidates

Cross-pair candidates are hypotheses that show evidence across multiple symbols. They are useful for identifying general feature ingredients.

### Pair-Specific Candidates

Pair-specific candidates are hypotheses that look useful for one symbol only. They are research leads for dedicated follow-up backtests and must not be generalized to other instruments without evidence.

## Final Feature Scorecard

The final feature scorecard aggregates yearly validation, selected combined hypotheses, ML feature ranking, backtest summaries, and pair-specific candidates into direction-specific research rankings.

The scorecard lists ingredients for future research backtests. It is not a tradable strategy, not a signal engine, and not a trader-facing final report.

## Fixed-Candidate Audit Chain

The fixed-candidate audit chain is research-only tooling for one already discovered candidate at a time. It reads existing output folders, keeps exact-candidate scope explicit, and records whether the candidate should be rejected, retained for timeout review, or allowed only into limited offline baseline/cost-sensitivity review with caveats.

Timeout-excluded diagnostics are biased because they remove a losing exit bucket from an already selected replay; they are not validated performance. Extended h20/h40/h80 timeout diagnostics are sensitivity checks for existing h10 timeout entries only; they are not replacement rules and must not be treated as horizon optimization.

`TIMEOUT_POLICY_SENSITIVITY_REJECTED` rejects alternative timeout policies. It does not automatically reject the original h10 candidate when the original h10 stress metrics remain strong. A gate decision may allow limited offline baseline/cost-sensitivity review only under the original h10 timeout rule, with the timeout caveat still unresolved.

## Current Fixed-Candidate Demo Execution Stage

The current stage is fixed-candidate MT5 demo execution prototype plus offline
research/parity evidence.

The active MT5 EA is
`mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`. It is
strictly demo-only, `GBPUSD`/`M15`/short-only, and scoped to
`gbpusd_short_h10_1_5_off_hours`. It implements entry `OrderCheck`, entry
`OrderSend`, send preflight/digest checks, integrated lifecycle watch,
integrated lifecycle close preflight, one integrated lifecycle close
`OrderSend`, opt-in 0.5% `ACCOUNT_EQUITY` risk-based entry sizing, and fixed-lot
backward compatibility with `InpUseRiskBasedSizing=false` and
`InpVolumeLots=0.01`.

A repo-wide read-only audit confirmed that the current EA has exactly two
callable `OrderSend(` sites: one entry and one lifecycle close. `AUD-001`
(time-exit bar alignment) now has a minimal code-and-test remediation: the MQL5
index-distance count includes the entry-containing bar once it completes after
entry execution. This makes bar 1 the first post-entry completion and makes the
time exit eligible on the first tick after completion 10. `AUD-002` (first-tick
signal freshness) now has a separate minimal code-and-test remediation: each
successful initialization establishes an in-memory `iTime(..., 1)` closed-bar
baseline, and entry processing remains blocked until a later closed-bar identity
is observed. Missing initialization history fails closed by making the first
valid closed bar the skipped baseline. Existing-position lifecycle observation
still runs independently, while restart positions remain unresolved under the
existing manual-review policy. Both execution-sensitive fixes still need
deterministic Strategy Tester and supervised demo evidence; they do not
authorize automatic or unattended demo operation.

The active EA now also contains the localized transaction-observability Patch A.
For each `TRADE_TRANSACTION_DEAL_ADD`, it makes one synchronous
`HistoryDealSelect(trans.deal)` attempt. After a successful select, boolean
getter overloads record independently whether core, economic, and text fields
were read. Valid zero values remain zero; unavailable values remain empty and
are named in `missing_history_fields`. The transaction position ticket from
`trans.position` is separate from the stable `DEAL_POSITION_ID`.
`MqlTradeRequest` and `MqlTradeResult` fields are consumed only for
`TRADE_TRANSACTION_REQUEST`.

Classification is observational and requires validated `DEAL_TYPE`,
`DEAL_ENTRY`, and `DEAL_REASON`: incomplete core data maps to
`history_data_incomplete`, `DEAL_ENTRY_INOUT` to `reversal_deal`, and an
unknown deal type to `unknown_deal_type`; price equality with SL is never used.
A failed select is logged as `unavailable_at_callback` with the original
`MqlTradeTransaction` fields and no retry or scheduled follow-up. The
per-`OnInit` `session_instance_id` is practically unique per attach/restart
and remains non-persisted, non-operational metadata. After a CSV schema change,
operators must use a new `InpRunId` instead of appending to an older schema
with `InpOverwriteLogsOnInit=false`. Deal-observation counters remain appended
to the final summary. Deal-time synchronized Bid/Ask and the known
replay-versus-broker Bid/Ask mismatch are not changed by this patch.

The EA remains non-production and not live-like continuous operation. It has no
live-account support, no retry, no scheduler, no `OrderSendAsync`, no
`PositionClose`, no `CTrade`, no `trade.Buy`, and no `trade.Sell`. Before any
broader demo-forward or live-like use, the project still needs persistence and
recovery hardening, an explicit policy for restart/unresolved position identity,
supervised validation of the new session/deal observability, and a clearer
state/report/data export policy. Lifecycle, sizing, and localized deal
observation counters are present in the final run summary.

Canonical spread policy is `spread_unit=broker_points` and
`max_spread_points=15.0`.

Canonical demo execution policy is
`config/fixed_candidate_demo_execution_policy.json`: intended demo equity is
1000 EUR, max risk is 0.5% or 5 EUR per trade, and max static margin usage is
70% or about 700 EUR. Static margin usage above 50% or about 500 EUR is an
elevated warning threshold. The risk cap is enforced only in the opt-in
risk-based sizing path; fixed-lot mode remains backward compatible and logs risk
for audit.

Risk source of truth is explicit: `config/fixed_candidate_demo_execution_policy.json`
is the current demo risk policy. The accepted cap is 0.5% / 5 EUR on intended
1000 EUR demo equity, account currency EUR, max open positions 1, 50% margin
warning, and 70% hard margin cap. The cap is a maximum, not a target to force.
Older `1%` references in `config/paper_demo`, archived configs, paper-only
command planning, or test fixtures are legacy/paper-only unless explicitly
re-reviewed; they must not be used for current demo execution sizing.

Numeric tercile threshold lineage is now explicit for the fixed candidate. `config/fixed_candidate_current_canonical.json` points to `reports/fixed_candidate_train_only_numeric_tercile_thresholds/gbpusd_short_h10_1_5_off_hours_train_only_numeric_tercile_thresholds_train_to_2024_12_31_v1/fixed_candidate_train_only_numeric_tercile_thresholds.json`, not the older full-sample artifact. The frozen artifact uses `threshold_lineage=train_only`, `calibration_scope=train_window_only`, `train_end_time=2024-12-31 23:59:59`, `full_sample_thresholds_used=false`, and `oos_rows_used_for_thresholds=false`. The old full-sample numeric-tercile threshold artifact remains historical only.

The current fixed-candidate evidence is now based on train-only threshold validation. The position-aware OOS replay for 2025-01-02 00:00:00 through 2026-06-05 22:00:00 passed with `max_open_positions=1`: 405 raw rule matches, 169 accepted trades, 236 overlap skips, `sum_R=106.92071036159173`, `profit_factor_R=3.9267711320413383`, and `position_aware_verdict=position_aware_degrades_but_positive`. This resolves the previous fixed-candidate full-sample threshold pointer problem, but it remains offline evidence and does not authorize execution.

The current fixed-candidate planning chain now includes the no-order live-data
dry run, shadow signal wrapper, synthetic would-signal fixture, would-signal
review, order shadow plan, order request shadow design, risk/volume shadow plan,
static margin feasibility plan, broker-safe margin validation, state
reconciliation planning, duplicate protection, manual approval/kill-switch
planning, future broker/local reconciliation planning, request construction
readiness planning, MT5 raw-source signal parity, MT5 demo OrderCheck, MT5 demo
entry send, integrated lifecycle close, fixed-lot regression, and opt-in 0.5%
risk-based sizing.

The request-adjacent ladder is intentionally split:

- `scripts/build_fixed_candidate_demo_order_shadow_plan.py` records future requirements after would-signal evidence.
- `scripts/build_fixed_candidate_demo_order_request_shadow_design.py` records conceptual future intent fields only. It does not construct a broker payload, broker request object, or executable order object.
- `scripts/build_fixed_candidate_demo_future_request_construction_readiness_plan.py` is a gatekeeper. It records prerequisites, block conditions, non-actionable future field descriptors, and the no-request boundary. It keeps `request_construction_allowed_now=false`, `broker_request_constructed=false`, `broker_payload_constructed=false`, and `order_object_constructed=false`.

No new `build_fixed_candidate_demo_future_request_construction_shadow_plan.py` module is needed at the current stage. That no-order planning branch is historical context; the current safer next actions are deterministic Strategy Tester and supervised demo validation of the `AUD-001` and `AUD-002` fixes, verification of deal reason/cost/session fields in the next supervised smoke, demo-state persistence/recovery hardening, unresolved-position identity policy, and continued offline research separation before any broader demo-forward operation.

### Accepted Controlled CLI Override Model

The project intentionally accepts `--allow-real-order-check` and `--allow-real-order-send` as explicit operational demo-pilot overrides. An operator may supply them manually, and a future controlled one-shot orchestrator may supply them automatically. They are necessary execution-stage gates rather than bypasses: neither flag is sufficient by itself, and neither may advance unless every required non-fixture safety gate for its stage passes.

The required gates for real demo-account `order_check` are:

- a fresh `shadow_signal_detected` / `would_signal` chain;
- a valid approval record;
- a non-fixture request-construction dry-run;
- available order-check readiness;
- clean broker/local reconciliation;
- safe margin and spread;
- passing duplicate protection;
- an inactive kill switch;
- a confirmed demo EUR account;
- an available symbol contract.

The required gates for the real demo-account `order_send` pilot are all order-check gates plus:

- `order_check_available_passed_no_send`;
- `order_send_pilot_readiness_plan_available_no_send`;
- final confirmation `confirm_single_demo_send_only`;
- an atomic `pre_send_pending` state claim;
- no active idempotency conflict;
- `max_open_positions = 1`;
- no retry;
- bounded post-send reconciliation;
- stop after one send attempt.

### Artifact Freshness Guard

The fixed-candidate demo chain now has a shared artifact freshness and max-age guard in `scripts/_fixed_candidate_artifact_freshness.py`.

The guard is applied in these stages:

- `scripts/create_fixed_candidate_demo_manual_approval_record.py`
- `scripts/build_fixed_candidate_demo_request_construction_dry_run.py`
- `scripts/check_fixed_candidate_demo_order_check.py`
- `scripts/send_fixed_candidate_demo_order_pilot.py`

Each patched stage writes `artifact_freshness_checks.csv`. Each patched manifest includes:

- `artifact_freshness_policy_applied`
- `stale_artifact_count`
- `blocking_stale_artifact_count`
- `max_artifact_age_minutes`

Dry-run and fixture paths record stale artifact warnings as nonblocking. Real or non-fixture approval, request construction, `order_check`, and `order_send` paths block stale, missing-timestamp, or malformed-timestamp upstream artifacts before MT5 import or any broker/order call. The default upstream artifact max age is 15 minutes. The `order_check` artifact max age before `order_send` is 5 minutes. Manual approval record expiry remains governed by `approval_expiry_time_utc`.

The stale-artifact block statuses are:

- `manual_approval_record_creation_blocked_stale_upstream_artifact`
- `request_construction_dry_run_blocked_stale_upstream_artifact`
- `order_check_blocked_stale_upstream_artifact`
- `order_send_pilot_blocked_stale_upstream_artifact`

The accepted future operating modes are:

- **Manual pilot mode:** an operator supplies the explicit flag after reviewing a complete non-fixture chain.
- **Controlled auto demo mode:** a future one-shot orchestrator may supply the flag only after programmatically proving the same gates.
- **Full scheduler/live-loop mode:** not implemented and not authorized.

Controlled automation is accepted because the final target is an automatic demo bot, but no ungated scheduler, loop, daemon, background task, or retry loop may use these flags. No extra pilot-authorization artifact will be added for now.

Current code may be used in fixture and dry-run modes. Real `order_check` and `order_send` remain blocked until a fresh, complete non-fixture chain exists. No new execution path was added by the artifact freshness guard or the threshold-pointer update, and no MT5, `order_check`, `order_send`, pipeline, database, or future-state mutation was run as part of those patches. The next real progression is to wait for a fresh non-fixture signal and run the gated chain. This policy does not authorize real-money trading, live-account trading, strategy optimization, threshold changes, or a trading decision.

## Demo-Live Smoke Runbook And Runtime Artifacts

The compact supervised smoke checklist is now
`docs/demo_live_smoke_runbook.md`. It documents the current boundary:

- a new supervised demo-live smoke with automatic entry/lifecycle remains
  blocked until the `AUD-001` and `AUD-002` fixes have deterministic Strategy
  Tester validation;
- the next supervised smoke must verify `session_instance_id`, deal raw/name
  enums, `deal_time_msc`, costs, and `history_lookup_status`, including the
  allowed `unavailable_at_callback` one-shot outcome;
- unattended demo-forward operation is not ready;
- real/live account use is not allowed.

Runtime artifacts remain local evidence and should not be committed:

- generated `reports/` outputs;
- `state/` runtime state and approval records;
- runtime CSV files;
- MT5 Files/Common Files exports copied into the repository;
- generated Graphify output under `graphify-out/`.

As of commit `ff37d1a`, runtime state JSON files under
`state/fixed_candidate_demo_state/` are no longer tracked. Local copies remain
ignored runtime evidence, not fixtures, and must not be added or edited to make
a run appear clean. `git ls-files state` is expected to return no tracked
runtime state paths.

Graphify output is intentionally not refreshed here. `graphify-out/GRAPH_REPORT.md`
is stale relative to current `HEAD` and should be refreshed in a separate
tooling pass.

## Volume Features

Volume-derived features are present in the price feature layer when the source bars include `tick_volume`.

Current volume and liquidity context features include:

- `tick_volume_avg_20`
- `tick_volume_ratio_20`
- `tick_volume_zscore_100`
- `tick_volume_percentile_100`
- `volume_spike_20`
- `volume_dry_up_20`
- `spread_to_volume_ratio`
- `volume_vs_hour_avg`
- `volume_vs_session_avg`

For Forex and CFD exports, these are tick-volume and liquidity context features. They are filters and research context, not standalone buy or sell signals.

## ATR And Future-Path Labels

Price features include time-safe true range, ATR, ATR-normalized candle shape, ATR-normalized moving-average distance, longer volatility, and spread-to-ATR context. These use only current and previous bars plus rolling past/current windows. Raw MT5 spread remains in points; `spread_price`, `spread_return`, and `spread_to_atr_20` convert through symbol-level `point_size` so spread and ATR are compared in price units.

The ML dataset also includes future max/min return, range, MFE, MAE, `target_long_good_*` / `target_short_good_*`, and controlled h5/h10/h20 triple-barrier TP/SL research labels that use current-bar `atr_20` and future OHLC path only as supervised outcomes. Same-bar TP/SL touches use conservative `stop_first`. These are supervised labels only. They must not be used as model features, validation conditions, live signals, or execution rules.

## Not Live-Ready

The project is not live-ready because it does not yet have:

- A trader-facing decision report.
- A production risk model.
- Broker-verified execution assumptions.
- Live order routing.
- Operational monitoring.
- Real-time data validation.
- A validated rule-based strategy with explicit entry, exit, stop, take-profit, sizing, slippage, and drawdown controls.
- Robust net walk-forward evidence strong enough to justify live-system design.

No research report, candidate-audit output, gate decision, or next-action CSV should be interpreted as live readiness.

## Prohibitions

- No live trading.
- No real/live-account `order_send`; demo-only `OrderSend` remains restricted
  to the explicitly gated prototypes and the current post-audit readiness
  boundary.
- No operational trading signals.
- No autonomous order execution.
- No direct recommendation to buy, sell, open, close, or hold a position.
- No generated output should be interpreted as trading advice.
