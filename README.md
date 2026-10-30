# Trading-Bot: GBPUSD M15 demo-only candidate

This publication is an independent source snapshot of candidate commit
`10eb0bf7535a4483b3941b829794b028e00e8aa6`. The original development history
and operational evidence are preserved privately; historical commit references
in the documentation describe that private development history and may not
resolve in this repository.

The active artifact is `mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`:
GBPUSD, M15, short-only, with explicit demo-account checks, entry and lifecycle
close gates, duplicate protection, and opt-in risk-based sizing. This repository
also contains Python research tools and gated demo execution modules. It is not
an unattended trading service or evidence of production readiness. The existing
source, tests, strategy configuration, and safety policies are preserved unchanged.

Only source, configuration examples, documentation, tests, and empty directory
placeholders are included. Historical reports, databases, runtime state, actual
approval records, local broker configuration, credentials, compiled EAs, and
private terminal exports are excluded. References to generated reports describe
locally produced evidence; those reports are not distributed here. Research and
demo observations do not establish future profitability.

## Offline validation

Use a fresh environment containing the offline dependencies only:

```powershell
python -m venv .venv-offline
.\.venv-offline\Scripts\python.exe -m pip install numpy pandas scikit-learn pytest python-dotenv
.\.venv-offline\Scripts\python.exe -m pytest -q
```

The automated tests use synthetic data and mocked broker interfaces. Do not
install MetaTrader5 in this validation environment. `requirements.txt` also
lists the terminal connector for separately supervised workflows; installing
that full list is unnecessary for offline validation. `main.py` and data-import
commands can connect to a terminal and are not offline test commands. MQL5 safety
tests inspect source; they do not compile or run an EA or Strategy Tester.

The detailed project documentation below records the candidate's capabilities,
limitations, and supervised workflows. Publication does not authorize any broker
action, terminal launch, or change to an existing demo deployment.

---

# Trading Bot Repository

This repository is a local trading bot project that combines offline research,
MetaTrader 5 parity work, and a narrowly scoped demo-only MT5 execution
prototype for the fixed candidate `gbpusd_short_h10_1_5_off_hours`.

The repository still does not include credentials, API keys, broker login
automation, live-account trading, production ML models, or a service that keeps
the bot running. GitHub is used only for code and versioning. The current MT5
execution capability is demo-only, manually configured, and guarded by explicit
inputs, static checks, broker reconciliation, and no-retry policy.

## Research documentation

Stable internal research references live under `docs/research/`:

- [Project State](docs/research/PROJECT_STATE.md)
- [Pipeline Steps](docs/research/PIPELINE_STEPS.md)
- [Outputs And Reports](docs/research/OUTPUTS_AND_REPORTS.md)
- [Methodology Guardrails](docs/research/METHODOLOGY_GUARDRAILS.md)
- [Cost Model](docs/research/COST_MODEL.md)
- [Next Actions](docs/research/NEXT_ACTIONS.md)

Update these files when pipeline scripts, generated outputs, methodology, or research priorities change. They are versioned references for future Codex and ChatGPT prompts, not generated run outputs.

Recent fixed-candidate audit tools package existing stress, replay, timeout, and gate-decision CSVs for offline review only. Their reports are not live signals, not broker-execution instructions, and not evidence of live readiness.

## Current Fixed-Candidate Stage

Current stage: fixed-candidate MT5 demo execution prototype plus offline
research/parity evidence.

The active execution artifact is:

```text
mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5
```

It is demo-only and limited to `GBPUSD`, `M15`, short-only,
`gbpusd_short_h10_1_5_off_hours`. It implements:

- raw-source signal parity logic for the fixed candidate;
- entry `OrderCheck` before entry `OrderSend`;
- send preflight and request digest checks;
- one entry `OrderSend` call site;
- integrated lifecycle watch;
- integrated lifecycle close preflight;
- one lifecycle close `OrderSend` call site for `time_exit_10_m15_bars` and
  `friday_forced_flat`;
- opt-in 0.5% `ACCOUNT_EQUITY` risk-based entry sizing;
- fixed-lot backward compatibility with `InpUseRiskBasedSizing=false` and
  `InpVolumeLots=0.01`;
- no retry, no scheduler, no live-account support, no `OrderSendAsync`, no
  `PositionClose`, no `CTrade`, no `trade.Buy`, and no `trade.Sell`.

A repo-wide read-only audit confirmed the two-call-site execution surface and
kept the current static safety invariants intact. `AUD-001` now has a localized
code-and-test remediation in the active EA: the lifecycle count includes the
bar containing the entry when that bar completes after execution, so the first
post-entry completion is bar 1 and the tenth is eligible on the first tick after
it closes. Deterministic timeline tests cover the 9/10/11 boundary, a one-bar
policy, day rollover, missing bars, Friday priority, and close guards.
`AUD-002` now also has a localized code-and-test remediation. On successful
initialization, the EA records `iTime(..., 1)` as its in-memory closed-bar
baseline. A bar at or before that baseline is observation-only for entry, while
the first later closed-bar identity can enter the normal signal flow. If history
is unavailable during initialization, the first valid closed bar becomes the
baseline and is skipped. Lifecycle observation for an existing position remains
separate from entry freshness. Neither remediation has been validated in MT5 or
Strategy Tester, and this does not authorize automatic smoke or unattended
demo-forward operation.

A localized transaction-observability Patch A is now implemented in the active
EA. Every `TRADE_TRANSACTION_DEAL_ADD` callback performs exactly one synchronous
`HistoryDealSelect(trans.deal)` lookup. A successful select is followed by
boolean-overload getters: valid zero values are logged as zero, while failed
getters leave their columns empty and are listed in `missing_history_fields`
with `history_getter_status=...partial_getter_failure`. Classification uses
validated `DEAL_TYPE`, `DEAL_ENTRY`, and `DEAL_REASON`; incomplete core getters
produce `history_data_incomplete`, `DEAL_ENTRY_INOUT` produces
`reversal_deal`, and an unknown deal type produces `unknown_deal_type`. The
transaction position ticket from `trans.position` and the stable
`DEAL_POSITION_ID` are exported separately. `request` and `result` fields are
read only for `TRADE_TRANSACTION_REQUEST`.

When the deal is not yet selectable, the callback is logged once with
`history_lookup_status=unavailable_at_callback`; there is no retry, timer, loop,
or later automatic query. `session_instance_id` is generated once in `OnInit`,
is practically unique per EA attach/restart, and is appended to
`run_config_log.csv`, `trade_transactions_log.csv`, and
`run_final_summary_log.csv`. It is observability only: it does not alter
execution state, request construction, reconciliation, idempotency, or trading
behavior. After a CSV schema change, use a new `InpRunId`; do not append the new
schema to artifacts created by an earlier EA version when
`InpOverwriteLogsOnInit=false`.
Synchronized deal-time Bid/Ask capture and the replay-versus-broker Bid/Ask
mismatch remain out of scope.

This is still not production or live-like continuous operation. Before any
broader demo-forward or live-like use, the project still needs persistence and
recovery hardening, an explicit policy for restart/unresolved position identity,
validation of the new transaction observability in a supervised smoke, and a
clearer state/report/data export policy. Lifecycle, sizing, and localized deal
observation counters are implemented in `run_final_summary_log.csv`.

Canonical spread policy is `spread_unit=broker_points` and
`max_spread_points=15.0`.

Canonical demo execution policy is recorded in
`config/fixed_candidate_demo_execution_policy.json`. It models
`intended_demo_equity=1000.0 EUR`, `risk_percent_max=0.5`,
`risk_amount_max=5.0 EUR`, `max_margin_usage_ratio=0.70`, and
`max_margin_usage_amount=700.0 EUR`, with a warning threshold at
`max_margin_usage_warning_ratio=0.50` or
`max_margin_usage_warning_amount=500.0 EUR`. The risk cap is a maximum, not a
forced target: if the risk-derived volume is not feasible, executable paths must
block before broker mutation.

Risk source of truth: `config/fixed_candidate_demo_execution_policy.json` is the
current demo risk policy. The demo cap is 0.5% / 5 EUR on intended 1000 EUR demo
equity, account currency EUR, max open positions 1, 50% margin warning, and 70%
hard margin cap. Older `1%` references in `config/paper_demo/`, archived
configs, paper-runner docs, or test fixtures are legacy/paper-only unless
explicitly re-reviewed; they are not current demo execution sizing and do not
authorize real-money or live-account trading.

Numeric tercile threshold source of truth: `config/fixed_candidate_current_canonical.json` now points to the frozen train-only threshold artifact at `reports/fixed_candidate_train_only_numeric_tercile_thresholds/gbpusd_short_h10_1_5_off_hours_train_only_numeric_tercile_thresholds_train_to_2024_12_31_v1/fixed_candidate_train_only_numeric_tercile_thresholds.json`. That artifact uses `threshold_lineage=train_only`, `calibration_scope=train_window_only`, and `train_end_time=2024-12-31 23:59:59`. The old full-sample numeric-tercile artifact is historical only and is not the current canonical fixed-candidate threshold source.

The current fixed-candidate evidence is now based on train-only threshold validation. OOS validation from 2025-01-02 00:00:00 through 2026-06-05 22:00:00 passed in position-aware mode with `max_open_positions=1`: 405 raw rule matches, 169 accepted trades, 236 overlap skips, `sum_R=106.92071036159173`, `profit_factor_R=3.9267711320413383`, and `position_aware_verdict=position_aware_degrades_but_positive`. This strengthens the methodology lineage, but it is still offline evidence and does not authorize order execution.

The planning chain has advanced through would-signal review, order shadow
planning, conceptual order request shadow design, risk/volume shadow planning,
margin feasibility planning, broker-safe margin validation planning and
read-only margin validation, state reconciliation planning, duplicate protection
planning, manual approval/kill-switch planning, future broker/local
reconciliation planning, request construction readiness planning, MT5
OrderCheck, MT5 demo entry send, integrated lifecycle close, and opt-in
risk-based sizing.

No extra `build_fixed_candidate_demo_future_request_construction_shadow_plan.py` module is needed now. The request-adjacent boundary remains non-actionable: `build_fixed_candidate_demo_order_request_shadow_design.py` records conceptual future intent fields only, and `build_fixed_candidate_demo_future_request_construction_readiness_plan.py` is a gatekeeper that keeps request construction unavailable now.

### Controlled Demo-Pilot CLI Overrides

The project intentionally accepts `--allow-real-order-check` and `--allow-real-order-send` as explicit operational demo-pilot overrides. Either flag may be supplied manually by an operator or automatically by a future controlled one-shot orchestrator. The flags are necessary execution-stage gates, not standalone authorization or safety bypasses: a flag alone is never enough, and it has no authority unless every required non-fixture gate for that stage passes.

Before a real demo-account `order_check`, the required chain includes:

- a fresh `shadow_signal_detected` / `would_signal` chain;
- a valid approval record and non-fixture request-construction dry-run;
- available order-check readiness;
- clean broker/local reconciliation;
- safe margin and spread;
- passing duplicate protection and an inactive kill switch;
- a confirmed demo EUR account and an available symbol contract.

Before a real demo-account `order_send` pilot, all order-check gates must pass, plus:

- `order_check_available_passed_no_send`;
- `order_send_pilot_readiness_plan_available_no_send`;
- the exact final confirmation `confirm_single_demo_send_only`;
- an atomic `pre_send_pending` state claim;
- no active idempotency conflict and `max_open_positions = 1`;
- no retry, bounded post-send reconciliation, and a stop after one send attempt.

### Artifact Freshness Max-Age Guard

A shared cross-module artifact freshness guard now exists at `scripts/_fixed_candidate_artifact_freshness.py`. It is used by:

- `scripts/create_fixed_candidate_demo_manual_approval_record.py`
- `scripts/build_fixed_candidate_demo_request_construction_dry_run.py`
- `scripts/check_fixed_candidate_demo_order_check.py`
- `scripts/send_fixed_candidate_demo_order_pilot.py`

Each patched stage writes `artifact_freshness_checks.csv` with upstream artifact timestamp, age, configured max age, freshness status, and whether staleness would block that path. Each patched manifest includes `artifact_freshness_policy_applied`, `stale_artifact_count`, `blocking_stale_artifact_count`, and `max_artifact_age_minutes`.

Dry-run and fixture paths record stale artifact warnings as nonblocking evidence. Real or non-fixture manual approval, request construction, `order_check`, and `order_send` paths block stale, missing-timestamp, or malformed-timestamp artifacts before MT5 import or broker/order calls. The default upstream artifact max age is 15 minutes. The `order_check` artifact max age before `order_send` is 5 minutes. Manual approval record expiry remains governed by `approval_expiry_time_utc`.

New stale-artifact block statuses are:

- `manual_approval_record_creation_blocked_stale_upstream_artifact`
- `request_construction_dry_run_blocked_stale_upstream_artifact`
- `order_check_blocked_stale_upstream_artifact`
- `order_send_pilot_blocked_stale_upstream_artifact`

Controlled automation is accepted because the final target is an automatic demo bot, but it must remain one-shot and gated. No ungated scheduler, loop, daemon, background task, or retry loop may use these flags. The accepted modes are manual pilot mode and a future controlled auto-demo mode; full scheduler/live-loop mode is not implemented or authorized.

Current Python-side pilot scripts may be used in fixture and dry-run modes unless
their explicit real-demo gates are satisfied. The MT5 EA path is separate and
demo-only: it requires explicit EA inputs, final acknowledgments, demo account
verification, broker-state gates, digest checks, and reconciliation before any
entry or lifecycle close mutation. This decision does not authorize real-money
trading, live-account trading, strategy optimization, or threshold changes.

## Repository Navigation Freshness

`graphify-out/GRAPH_REPORT.md` was built from commit `2357575c` and is stale
relative to the current MT5 demo execution commits. Treat it as historical
navigation only until a separate tooling pass refreshes Graphify output.

## Demo-Live Smoke Runbook

The compact supervised demo-live smoke checklist is in
`docs/demo_live_smoke_runbook.md`.

This runbook keeps the current policy unchanged: `current_10_bars`,
`max_holding_bars=10`, Friday forced flat, no weekend hold protection, and
0.5% opt-in risk sizing. Ten bars means ten M15 bar completions observed after
entry execution, including the entry-containing bar when it subsequently
closes. The `AUD-001` and `AUD-002` code/test remediations still require
deterministic MT5 Strategy Tester and supervised demo evidence. The runbook does
not authorize unattended demo-forward or real/live operation. The next
supervised smoke should verify `session_instance_id`, `deal_time_msc`, raw/name
deal enums, deal costs, `history_lookup_status`, and broker-side SL/TP reason
classification in `trade_transactions_log.csv`.

## Runtime Artifact Policy

Runtime artifacts are local evidence, not source artifacts. Do not commit:

- generated `reports/` contents, except tracked `.gitkeep` placeholders;
- `state/` runtime state and manual approval records;
- runtime CSV files;
- MT5 Files or Common Files exports copied into the repository;
- generated Graphify output under `graphify-out/`.

As of commit `ff37d1a`, runtime state JSON files under `state/` are no longer
tracked. Existing local copies remain ignored runtime evidence, not fixtures;
do not add, edit, or commit them. `git ls-files state` is expected to return no
tracked runtime state paths.

## Repository Structure

```text
mql5/
  ExportEconomicCalendar.mq5   MetaTrader 5 script for exporting the economic calendar
scripts/
  run_pipeline.py              Orchestrates local database initialization and CSV import
  init_database.py             Creates the local SQLite database and schema
  import_calendar_csv.py       Imports exported calendar CSV rows into SQLite
  import_price_bars.py         Imports read-only historical OHLCV bars from MetaTrader 5
  generate_price_features.py   Generates basic features from imported price bars
  generate_market_features.py  Combines price features with economic calendar timing
  generate_ml_dataset.py       Adds supervised future-return and future-path labels to market features
  ml_research.py               Creates offline ML research reports from ml_dataset
  compare_ml_target_reports.py Compares ML diagnostics across target-specific report folders
  build_preferred_target_feature_stability.py Summarizes recurring features for preferred FX ML targets
  build_preferred_feature_hypothesis_shortlist.py Classifies preferred stable ML features for follow-up research
  run_preferred_feature_backtests.py Runs controlled backtest summaries for shortlisted preferred features
  compare_preferred_feature_backtest_cost_modes.py Compares gross and estimated-net preferred-feature runs
  run_preferred_feature_combination_backtests.py Tests small controlled preferred-feature two-filter combinations
  run_tp_sl_path_backtests.py Tests fixed TP/SL path-exit diagnostics for already-discovered filters
  build_research_branch_outcome_report.py Records research-only closure outcomes for rejected branches
  run_preferred_horizon_cost_diagnostics.py Orchestrates dry-run, controlled horizon/cost sensitivity, and zero-tested summary diagnostics
  validate_regime_candidate_stress.py Replays one fixed regime candidate with sequential, cost-stress, random-baseline, and effective-cost diagnostics
  build_regime_candidate_review_package.py Packages existing stress outputs into a research-only candidate review
  run_rule_based_regime_candidate_backtest.py Replays one fixed reviewed candidate as an offline rule-replay audit
  build_rule_based_regime_candidate_review.py Summarizes existing rule-replay outputs for extended research review
  build_controlled_rule_research_expansion.py Builds a controlled expansion package from existing review/replay outputs
  build_timeout_fragility_audit.py Audits existing TIMEOUT trades without rerunning replay
  build_timeout_root_cause_review.py Reviews timeout root-cause evidence from existing outputs
  build_timeout_sequence_drilldown_review.py Drills into the largest timeout sequence from existing outputs
  build_timeout_policy_sensitivity_review.py Compares timeout-policy diagnostics for existing timeout entries
  build_rule_candidate_gate_decision_report.py Builds a fixed-candidate research-only gate decision
  run_candidate_audit_pipeline.py Plans or executes the fixed-candidate audit chain with stage gating
  diagnose_preferred_horizon_prerequisites.py Checks target/shortlist prerequisites for preferred horizon runs
  build_preferred_horizon_shortlists.py Builds preferred target rankings and shortlist inputs for configured horizons
  check_database.py            Prints diagnostics for economic_events
  check_price_bars.py          Prints diagnostics for price_bars
  check_price_features.py      Prints diagnostics for price_features
  check_market_features.py     Prints diagnostics for market_features
  check_ml_dataset.py          Prints diagnostics for ml_dataset
  check_ml_research_outputs.py Checks generated ML research report CSV files
  run_full_research_pipeline.py Runs the full offline research pipeline
  run_hypothesis_discovery_pipeline.py Plans or executes the minimal hypothesis discovery sub-pipeline
  run_combined_validation_pipeline.py Plans or executes the combined validation sub-pipeline
  evaluate_backtest_results.py Evaluates exploratory backtest buckets against baselines
  select_research_hypotheses.py Selects research hypotheses from evaluated reports
  backtest_combined_hypotheses.py Tests controlled combinations of selected hypotheses
  evaluate_combined_hypotheses.py Evaluates combined hypothesis reports
  validate_hypotheses_by_year.py Validates selected hypotheses year by year
  run_random_baseline_tests.py Tests final candidates against random same-size baselines
  run_candidate_baseline_diagnostics.py Tests incremental candidate value versus contextual baselines
  build_research_decision_report.py Builds the final research-only decision report
  build_final_feature_scorecard.py Aggregates final research features and conditions
  build_horizon_consistency_report.py Compares scorecard behavior across h5/h10/h20
  analyze_historical_spreads.py Analyzes local SQLite spread history for cost-model calibration
  compare_mt5_recent_spreads.py Compares recent read-only MT5 spreads with local DB spreads
  run_research_validation_pipeline.py Runs post-backtest combined evaluation and yearly validation (compatibility runner)
  condition_utils.py          Shared condition parser for validated research combinations
  research_costs.py            Shared estimated spread/slippage/commission return costs
  research_pipeline_utils.py   Shared orchestration-only helpers for future pipeline wrappers
data/
  .gitkeep                     Placeholder for local data artifacts
reports/
  .gitkeep                     Placeholder for local report artifacts
  ml_research/.gitkeep         Placeholder for ignored ML research CSV outputs
models/
  .gitkeep                     Placeholder for future model artifacts
logs/
  .gitkeep                     Placeholder for local log files
```

Runtime files such as `data/trading_bot.db`, `data/economic_calendar.csv`, model artifacts, and log files are intentionally kept out of Git.

## Manual MetaTrader 5 Export Step

MetaTrader 5 export remains the only manual step.

1. Open MetaEditor from MetaTrader 5.
2. Create or open:

   ```text
   MQL5\Scripts\ExportEconomicCalendar.mq5
   ```

3. Copy the repository file `mql5/ExportEconomicCalendar.mq5` into that MetaEditor script location.
4. Compile the script in MetaEditor.
5. In MetaTrader 5, run `ExportEconomicCalendar` manually from the Scripts section.

The script creates:

```text
economic_calendar.csv
```

MetaTrader 5 usually writes files to:

```text
MQL5\Files
```

To find that folder, use:

```text
MetaTrader 5 > File > Open Data Folder > MQL5 > Files
```

The expected CSV header is:

```text
value_id,event_id,time_server,currency,event_name,event_code,importance,impact_type,actual,forecast,previous,revised_previous,period,revision
```

## Automated Repository Workflow

After the CSV has been exported, run the repository-side workflow from the repository root:

```powershell
python scripts/run_pipeline.py
```

By default this uses:

```text
Database: data\trading_bot.db
CSV:      data\economic_calendar.csv
Table:    economic_events
```

The pipeline creates `data/`, `models/`, and `logs/` if missing, initializes the SQLite database, and imports the CSV. Duplicate rows are ignored using the unique `value_id`.

Database initialization also creates the `price_bars` table for historical OHLCV bars, the `price_features` table for derived price features, the `market_features` table for price features combined with economic calendar timing, and the `ml_dataset` table for supervised future-return and future-path labels. These tables are unique by `symbol`, `timeframe`, and `time_server`.

To copy directly from the MT5 `MQL5\Files` export location before importing:

```powershell
python scripts/run_pipeline.py --csv-source "C:\path\to\MQL5\Files\economic_calendar.csv"
```

To use custom local paths:

```powershell
python scripts/run_pipeline.py --db-path data/trading_bot.db --csv-path data/economic_calendar.csv
```

To initialize folders and the database only, without requiring a CSV:

```powershell
python scripts/run_pipeline.py --init-only
```

To import only, assuming the database and `economic_events` table already exist:

```powershell
python scripts/run_pipeline.py --import-only
```

The final report shows folders checked or created, database path, CSV path, whether `--csv-source` was copied, rows read, rows inserted, rows skipped, and final status.

## Standalone Commands

Initialize the SQLite database directly:

```powershell
python scripts/init_database.py
```

Import the default CSV directly:

```powershell
python scripts/import_calendar_csv.py
```

The standalone importer defaults to:

```text
CSV: data\economic_calendar.csv
DB:  data\trading_bot.db
```

Check economic calendar data:

```powershell
python scripts/check_database.py
```

## Historical Price Bars From MetaTrader 5

Historical OHLCV import is read-only and uses the official MetaTrader 5 Python package. It calls `mt5.initialize()` and `copy_rates_range()` only. It does not send orders and does not use order execution APIs.

On Windows, install the MetaTrader 5 Python package in your active environment if it is not already available:

```powershell
python -m pip install MetaTrader5
```

Make sure the MetaTrader 5 desktop terminal is installed, opened, and connected to the account/server that provides the requested symbol.

Initialize the database schema:

```powershell
python scripts/init_database.py
```

Import historical bars:

```powershell
python scripts/import_price_bars.py --symbol EURUSD --timeframe M15 --from-date 2024-01-01 --to-date 2024-12-31
```

Supported timeframes:

```text
M1, M5, M15, M30, H1, H4, D1
```

Dates are interpreted as UTC when no timezone is included. ISO datetime values are also accepted:

```powershell
python scripts/import_price_bars.py --symbol EURUSD --timeframe H1 --from-date 2024-01-01T00:00:00Z --to-date 2024-02-01T00:00:00Z
```

Use a custom database path if needed:

```powershell
python scripts/import_price_bars.py --symbol GBPUSD --timeframe H4 --from-date 2024-01-01 --to-date 2024-06-30 --db-path data\trading_bot.db
```

The import report prints symbol, timeframe, date range, rows downloaded, rows inserted, and rows skipped. Existing bars are ignored with `INSERT OR IGNORE`.

Check imported price bars:

```powershell
python scripts/check_price_bars.py
```

The checker prints total bars, counts and date ranges by symbol/timeframe, duplicate key count, missing OHLC count, and spread average/min/max by symbol/timeframe.

## Price Feature Generation

Feature generation reads from `price_bars` and writes to `price_features`. It is a data-preparation step only: it does not train models, run backtests, create strategies, send orders, or use order execution APIs.

Initialize the schema first:

```powershell
python scripts/init_database.py
```

Generate features for one symbol and timeframe:

```powershell
python scripts/generate_price_features.py --symbol EURUSD --timeframe M15
```

Use a custom database path if needed:

```powershell
python scripts/generate_price_features.py --symbol EURUSD --timeframe H1 --db-path data\trading_bot.db
```

The generator computes:

```text
return_1, return_5, return_20
candle_range, body_size, upper_wick, lower_wick
true_range, atr_14, atr_20, atr_50
range_to_atr_20, body_to_atr_20
upper_wick_to_atr_20, lower_wick_to_atr_20
volatility_20, volatility_100, volatility_ratio_20_100
ma_fast, ma_slow, ma_diff
close_to_ma_fast_atr_20, close_to_ma_slow_atr_20, ma_diff_atr_20
spread_avg_20, spread_price, spread_return, spread_to_atr_20, tick_volume_avg_20
tick_volume_ratio_20, tick_volume_zscore_100, tick_volume_percentile_100
volume_spike_20, volume_dry_up_20
spread_to_volume_ratio
volume_vs_hour_avg, volume_vs_session_avg
hour_session, hour, day_of_week
```

ATR features are calculated from current high/low and previous close only. Rolling ATR and volatility windows use past/current rows, so their initial rows remain `NULL` until enough history exists.

Raw `spread` and `spread_avg_20` are preserved as MT5 points. `spread_price = spread * point_size`, `spread_return = spread_price / close`, and `spread_to_atr_20 = spread_price / atr_20`. Feature generation has generic internal point-size defaults only for common FX symbols; use `--point-size` or `--point-size-config config/symbol_metadata.local.json` for broker-specific symbols such as metals, and `--strict-point-size` when missing point size should fail instead of producing `NULL` spread price features. The versioned `config/symbol_metadata.example.json` is only a placeholder template; keep filled broker metadata in ignored local files.

Forex/CFD exports usually provide `tick_volume`, not centralized exchange volume. In this research pipeline, volume-derived features are liquidity and context filters only. They should help answer when another setup works better or worse; they are not standalone buy/sell signals.

The normalized volume features are:

- `tick_volume_ratio_20`: current `tick_volume` divided by the rolling 20-bar tick-volume average.
- `tick_volume_zscore_100`: current `tick_volume` versus the rolling 100-bar mean and standard deviation.
- `tick_volume_percentile_100`: current `tick_volume` rank inside the rolling 100-bar past/current window.
- `volume_spike_20`: binary flag for `tick_volume_ratio_20 >= 1.5`.
- `volume_dry_up_20`: binary flag for `tick_volume_ratio_20 <= 0.7`.
- `spread_to_volume_ratio`: rolling spread divided by rolling tick volume, with zero-volume protection.
- `volume_vs_hour_avg`: current `tick_volume` divided by the previous expanding mean for the same hour.
- `volume_vs_session_avg`: current `tick_volume` divided by the previous expanding mean for the same session.

`volume_vs_hour_avg` and `volume_vs_session_avg` use shifted expanding means, so the current row is compared only with earlier rows from the same hour or session. `hour_session` uses a single label per bar: `Asia` for hours 0-7, `London` for 8-13, `New_York` for 14-21, and `Off_hours` otherwise. This assigns the London/New York overlap hours 14-15 to `New_York` in the generated categorical feature.

Volume features must be validated with long and short kept separate, walk-forward selection, cost-adjusted net returns, and pair-specific and cross-pair results reviewed separately. Do not interpret a result such as `volume_spike_20 strong` as a direct buy/sell rule; it is only evidence that volume context may be useful as a filter in a future rule-based backtest.

Rows are written with an upsert on `symbol`, `timeframe`, and `time_server`, so rerunning the command refreshes existing feature rows.

Check generated features:

```powershell
python scripts/check_price_features.py
```

The checker prints total feature rows, counts and date ranges by symbol/timeframe, NULL counts in core features, basic stats for return, volatility, spread, ATR/range, and volume/liquidity features when those columns exist.

## Market Feature Generation

Market feature generation reads from `price_features` and `economic_events`, then writes to `market_features`. It uses only event timing, currency, and importance. It intentionally does not use `actual`, `forecast`, `previous`, or `revised_previous` from the economic calendar, to avoid leaking post-event data into candle features.

Initialize the schema first:

```powershell
python scripts/init_database.py
```

Generate market features for one symbol and timeframe:

```powershell
python scripts/generate_market_features.py --symbol EURUSD --timeframe M15
```

Use a custom database path if needed:

```powershell
python scripts/generate_market_features.py --symbol EURUSD --timeframe H1 --db-path data\trading_bot.db
```

Override relevant news currencies manually:

```powershell
python scripts/generate_market_features.py --symbol EURUSDm --timeframe M15 --news-currencies "EUR,USD"
```

Built-in symbol to news-currency mapping:

```text
EURUSD -> EUR,USD
GBPUSD -> GBP,USD
USDJPY -> USD,JPY
XAUUSD -> USD
XAGUSD -> USD
```

Broker suffixes such as `EURUSDm`, `XAUUSDm`, and `EURUSD.` are normalized to the base symbol when possible.

The generator computes next/previous news distances, high-impact windows, blackout/post-news flags, event counts, max importance, and next/last event currency and importance. High impact means `importance >= 2`.

Check generated market features:

```powershell
python scripts/check_market_features.py
```

The checker prints total rows, counts and date ranges by symbol/timeframe, blackout and high-impact counts, minutes-to/from-news statistics, and rows with missing required news features.

## ML Dataset Generation

ML dataset generation reads from `market_features` and writes to `ml_dataset`. It only prepares supervised learning rows by adding future-return targets and future MFE/MAE labels. It does not train models, run backtests, create strategies, send orders, or use order execution APIs.

Initialize the schema first:

```powershell
python scripts/init_database.py
```

Generate the dataset for one symbol and timeframe:

```powershell
python scripts/generate_ml_dataset.py --symbol EURUSD --timeframe M15
```

Use a minimum return threshold for directional targets:

```powershell
python scripts/generate_ml_dataset.py --symbol EURUSD --timeframe M15 --min-return-threshold 0.0002
```

Use a custom database path if needed:

```powershell
python scripts/generate_ml_dataset.py --symbol EURUSD --timeframe H1 --db-path data\trading_bot.db
```

The generator computes:

```text
future_return_5, future_return_10, future_return_20
future_max_return_5/10/20, future_min_return_5/10/20, future_range_5/10/20
long_mfe_5/10/20, long_mae_5/10/20
short_mfe_5/10/20, short_mae_5/10/20
target_long_good_5/10/20, target_short_good_5/10/20
long_tp_1atr_sl_1atr_hit_first_10, long_tp_2atr_sl_1atr_hit_first_10
short_tp_1atr_sl_1atr_hit_first_10, short_tp_2atr_sl_1atr_hit_first_10
long_triple_barrier_1_1_10, long_triple_barrier_2_1_10
short_triple_barrier_1_1_10, short_triple_barrier_2_1_10
*_bars_to_first_barrier_10
target_up_5, target_up_10, target_up_20
target_down_5, target_down_10, target_down_20
```

Future returns are calculated from future closes. Future max/min return, MFE, MAE, `target_*_good_*`, and h5/h10/h20 triple-barrier columns are supervised labels derived from future bars; they are not features, not signals, and not execution rules. Triple-barrier labels use current-bar `atr_20` and the matching future OHLC path horizon. If TP and SL are touched in the same future candle, the conservative `stop_first` policy labels the stop as first. The final rows that do not have enough future bars are kept with `NULL` target values.

Check the generated dataset:

```powershell
python scripts/check_ml_dataset.py
```

The checker prints total rows, counts and date ranges by symbol/timeframe, target NULL counts, distributions for directional and MFE/MAE-based h10 targets, and basic stats for future-return and future-path label columns.

## ML Research Reports

ML research reads from `ml_dataset` and writes report CSV files to a symbol/timeframe/horizon-specific folder under `reports\ml_research`. It is an offline analysis step only. It does not create trading signals, run backtests, send orders, use order execution APIs, or deploy a production model.

Install the project dependencies in your active Python environment:

```powershell
python -m pip install -r requirements.txt
```

Run the default research analysis:

```powershell
python scripts/ml_research.py --symbol EURUSD --timeframe M15
```

By default this writes to:

```text
reports\ml_research\long\EURUSD_M15_h10\
```

Choose a different classification target or return target if needed:

```powershell
python scripts/ml_research.py --symbol EURUSD --timeframe M15 --target target_down_10 --return-target future_return_10
```

Use a custom output folder:

```powershell
python scripts/ml_research.py --symbol EURUSD --timeframe M15 --output-dir reports\ml_research
```

Analyze ML research reports:

```powershell
python scripts/analyze_research_reports.py
```

When no `--input-dir` is passed, the analyzer scans all report folders like:

```text
reports\ml_research\{DIRECTION}\{SYMBOL}_{TIMEFRAME}_h{H}\
```

It writes `summary_feature_ranking.csv` inside each analyzed folder and, when multiple folders are found, writes `aggregate_feature_ranking.csv` to `reports\ml_research`.

Analyze one folder only:

```powershell
python scripts/analyze_research_reports.py --input-dir reports\ml_research\EURUSD_M15_h10
```

Build the preferred FX target feature-stability report after target-specific ML reports exist:

```powershell
python scripts/build_preferred_target_feature_stability.py
```

By default this reads EURUSD, GBPUSD, and USDJPY target-run folders for the preferred M15 h10 2ATR/1ATR targets and writes diagnostic outputs under `reports\ml_research\preferred_target_feature_stability\`. XAUUSD is intentionally excluded from the default preferred FX stability report until stronger target-threshold diagnostics appear.

Build a preferred feature hypothesis shortlist from the stability report:

```powershell
python scripts/build_preferred_feature_hypothesis_shortlist.py
```

This reads `feature_stability.csv`, filters for recurring features, classifies feature family, role, normalized/raw status, usage, and caution level, then writes under `reports\ml_research\preferred_feature_hypotheses\`. The shortlist is research triage for controlled backtest and validation design only.

Run controlled preferred-feature backtests from the shortlist:

```powershell
python scripts/run_preferred_feature_backtests.py
```

This reuses `backtest_research.py` bucket logic for shortlisted normalized/contextual features and writes run-scoped summaries under `reports\preferred_feature_backtests\{RUN_ID}\{DIRECTION}\`. EURUSD, GBPUSD, and USDJPY are the default FX symbols; XAUUSD is included only when explicitly passed with `--symbols`. The summary/detail CSVs include condition, source, bucket, same-symbol baseline metrics, deltas versus baseline, and skip reasons. Zero-trade conditions are written to `skipped_features.csv`. By default, standard context scenarios from `backtest_research.py` are retained and tagged with `scenario_source`; pass `--strict-shortlist-only` to keep only scenarios whose feature is in the preferred shortlist. These reports are exploratory and do not establish strategy validity or deployment readiness.

Compare an existing gross/none preferred-feature run with an estimated/net run:

```powershell
python scripts/compare_preferred_feature_backtest_cost_modes.py --gross-run-id GROSS_RUN_ID --net-run-id NET_RUN_ID
```

This writes under `reports\preferred_feature_backtests\cost_mode_comparison\` and flags rows where estimated costs erased a weak gross edge. Gross/none evidence is diagnostic context only; estimated/net review is required for serious evaluation.

Run small controlled preferred-feature combination backtests from the cost-mode comparison:

```powershell
python scripts/run_preferred_feature_combination_backtests.py --gross-run-id GROSS_RUN_ID --net-run-id NET_RUN_ID
```

This reads preferred-shortlist rows from `cost_mode_comparison.csv`, keeps EURUSD, GBPUSD, and USDJPY as the default symbols, and tests rank-aligned two-filter pairings between momentum/trend features and liquidity, volatility, or spread context features. It writes under `reports\preferred_feature_combination_backtests\{RUN_ID}\{DIRECTION}\`. The outputs separate normal rows from zero-trade or unsupported combinations in `skipped_combinations.csv` and include `candidate_diagnostics.csv` plus markdown candidate counters so empty runs show which filter stage removed the rows. The run is exploratory research only and does not add execution, position sizing, stops, targets, or multi-timeframe logic.

The script uses a temporal split, not a random split:

```text
70% train
30% test
```

It excludes identifiers, metadata, raw OHLC levels, raw `tick_volume`, raw spread points, all future-return/future-path label columns, and all target columns from the feature matrix. Only numeric feature columns are used. Missing numeric values are reported in `feature_summary.csv` and imputed with train-set medians for model-based analysis.

ML return diagnostics keep raw and direction-aware interpretations separate. For long research, directional return equals `future_return_{H}`. For short research, directional return equals `-future_return_{H}`, so a negative raw future return is favorable in directional-return columns. `threshold_analysis.csv` is diagnostic only; it does not set thresholds globally, create live signals, or produce trading advice.

Generated reports:

```text
correlations.csv
mutual_information.csv
random_forest_importance.csv
permutation_importance.csv
model_metrics.csv
threshold_analysis.csv
feature_summary.csv
```

Check generated reports:

```powershell
python scripts/check_ml_research_outputs.py
```

Compare multiple ML targets without overwriting the standard ML report folder:

```powershell
python scripts/compare_ml_target_reports.py --symbol EURUSD --timeframe M15 --direction long --horizon 10 --run-ml-research --overwrite
python scripts/compare_ml_target_reports.py --symbol EURUSD --timeframe M15 --direction short --horizon 10 --run-ml-research --overwrite
```

Target-specific runs are written under:

```text
reports\ml_research\target_runs\{DIRECTION}\{SYMBOL}_{TIMEFRAME}_h{H}\{TARGET}\
```

The comparison summary is written under:

```text
reports\ml_research\target_comparison\{DIRECTION}\{SYMBOL}_{TIMEFRAME}_h{H}\
```

`recommended_research_threshold` in the comparison output is a conservative diagnostic field only. It is not an operational threshold, does not create signals, and does not alter the normal ML pipeline output convention.

## Backtest Research Reports

Backtest research reads from `ml_dataset` and evaluates exploratory feature buckets against the baseline for the same symbol/timeframe/horizon. It is research only: it does not create operational signals, does not connect to MetaTrader 5, and does not call order execution APIs.

Run one exploratory backtest:

```powershell
python scripts/backtest_research.py --symbol EURUSD --timeframe M15 --target-horizon 10
```

By default this writes:

```text
reports\backtests\EURUSD_M15_h10\
```

Evaluate all symbol/timeframe/horizon backtest folders:

```powershell
python scripts/evaluate_backtest_results.py
```

Select robust research hypotheses:

```powershell
python scripts/select_research_hypotheses.py
```

By default the selector writes the top 5 hypotheses per report scope. This does not change the maximum combination size used later by combined-hypothesis testing.

The clear profit factor metric is:

```text
profit_factor_improvement_pct
avg_profit_factor_improvement_pct
```

These are real percentages, not ratios. Positive values mean profit factor improved versus the matching baseline. For example, baseline `1.20` and scenario `1.26` produces `+5`; a 5% threshold is written as `5`, not `0.05`.

If a scenario has gains but no losses, raw profit factor is mathematically infinite. Final research CSV writers avoid emitting raw non-finite values and treat non-finite profit factor improvements as unavailable rather than as automatic evidence.

The clear drawdown metric is:

```text
max_drawdown_improvement_pct
```

Positive values mean drawdown improved. Negative values mean drawdown worsened. For example, baseline `-0.10` and scenario `-0.08` produces `+20`; baseline `-0.10` and scenario `-0.12` produces `-20`.

`cumulative_return` is compounded:

```text
cumulative_return = product(1 + returns) - 1
```

It is not a simple sum of returns.

The return quality columns include:

- `payoff_ratio`: average positive return divided by the absolute average negative return.
- `breakeven_winrate`: win rate needed to break even at the observed payoff ratio.
- `breakeven_winrate_margin`: observed win rate minus breakeven win rate.

### Performance Concentration Metrics

Research reports also track whether a result is distributed through time or concentrated in a few lucky periods/trades. These metrics are calculated from the same strategy-return series used for the main report: gross returns when `--return-mode gross` is active, and estimated net returns when `--return-mode net` is active.

The main concentration columns are:

- `monthly_positive_ratio`: fraction of active months with compounded monthly return greater than zero.
- `quarterly_positive_ratio`: fraction of active quarters with compounded quarterly return greater than zero.
- `best_month_contribution_pct`: share of total positive monthly profit explained by the single best month.
- `top_5_percent_trades_contribution_pct`: share of total positive trade profit explained by the best 5% of trades.
- `max_flat_period_bars`: longest number of consecutive evaluated rows without a new equity high.

If total positive profit is not greater than zero, contribution metrics are left empty instead of forcing a misleading value. A combination can look positive year by year and still be fragile if most of the profit comes from one month or a tiny number of trades. These metrics are used as light penalties for concentration risk, not as standalone promotion criteria.

Current penalty checks are:

```text
monthly_positive_ratio < 0.45
quarterly_positive_ratio < 0.50
best_month_contribution_pct > 60
top_5_percent_trades_contribution_pct > 70
```

Long and short remain separate, gross and net remain separate, and cross-pair and pair-specific reports keep their concentration diagnostics separate.

## Combined Hypothesis Research

Combined hypothesis backtests read selected/watchlist hypotheses and test combinations of at most three filters.

The minimal hypothesis discovery wrapper can plan the upstream chain that produces run-scoped combined outputs for validation:

```powershell
python scripts/run_hypothesis_discovery_pipeline.py --run-id 20260509_190544 --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-config config/cost_model.example.json --dry-run
```

It writes wrapper artifacts under `reports\hypothesis_discovery_pipeline\{RUN_ID}\` and plans combined backtest outputs under `reports\backtests\combined\runs\{RUN_ID}\{DIRECTION}\{SYMBOL}_{TIMEFRAME}_h{H}\`. Controlled execution requires explicit `--execute` and should be user-run only for heavy research outputs. The outputs are exploratory discovery inputs for combined validation, not validated strategy evidence.

Run one combined backtest:

```powershell
python scripts/backtest_combined_hypotheses.py --symbol EURUSD --timeframe M15 --target-horizon 10
```

By default this writes:

```text
reports\backtests\combined\EURUSD_M15_h10\
```

Evaluate combined hypotheses across all combined result folders:

```powershell
python scripts/evaluate_combined_hypotheses.py
```

The final evaluation output is timestamped:

```text
reports\backtests\combined\evaluations\{RUN_ID}\{DIRECTION}\
```

Use a fixed run ID when needed:

```powershell
python scripts/evaluate_combined_hypotheses.py --run-id 20260509_183012
```

Automatic combined-hypothesis generation explicitly excludes raw price levels:

```text
open, high, low, close
```

Those columns remain available in `price_features`, `market_features`, and `ml_dataset`, but they are not used to generate cross-symbol combinations because EURUSD, USDJPY, and XAUUSD use different absolute price scales. Cross-symbol combinations should prefer normalized or relative features such as:

```text
return_*
ma_diff
volatility_20, volatility_100, volatility_ratio_20_100
atr_20 and ATR-normalized candle/MA distance features
spread_avg_20, spread_return, spread_to_atr_20
tick_volume_avg_20
tick_volume_ratio_20
volume_spike_20
volume_dry_up_20
volume_vs_hour_avg
volume_vs_session_avg
spread_to_volume_ratio
hour
day_of_week
news features
```

Raw `tick_volume` is intentionally excluded from automatic final combinations because broker feeds, symbols, and sessions can have different tick-count scales. Use normalized or binary volume/liquidity features instead.

## Year-by-Year Combined Hypothesis Validation

Year-by-year validation is the research step after `evaluate_combined_hypotheses.py`. It reads selected/watchlist combinations from:

```text
reports\backtests\combined\evaluations\{RUN_ID}\{DIRECTION}\selected_combined_hypotheses.csv
```

It then validates every combination across the requested symbols and years against the baseline from the same symbol and year. It is research only: it reads SQLite, does not use MetaTrader5, does not call order execution APIs, and does not create live signals.

Final validation is intentionally stricter than exploratory backtests. It skips:

```text
numeric_tercile
open, high, low, close
future_* and target_* label columns
```

`numeric_tercile` is useful during exploration, but generic final validation must not use full-period tercile thresholds because they can leak future distribution information into earlier years. The GBPUSD fixed candidate is now a specific exception backed by a frozen train-only artifact with `train_end_time=2024-12-31 23:59:59`; older full-sample threshold outputs remain historical only. A future general walk-forward version should compute fold-specific tercile thresholds only from previous/training rows. Raw price levels are skipped because absolute prices are not robust across EURUSD, USDJPY, XAUUSD, and other symbols with different scales. Future-path and target columns are skipped because they are supervised labels, not feature conditions. Numeric volume terciles outside the validated fixed-candidate artifact remain exploratory until their thresholds are computed train-only. Skipped combinations are written to `skipped_hypotheses.csv`.

Run validation for a known combined-evaluation run:

```powershell
python scripts/validate_hypotheses_by_year.py --run-id 20260509_190544 --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10
```

Or pass the selected combinations file directly:

```powershell
python scripts/validate_hypotheses_by_year.py --hypotheses-file reports\backtests\combined\evaluations\20260509_190544\long\selected_combined_hypotheses.csv --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long
```

By default this writes to a run-specific directory:

```text
reports\validation\by_year\{RUN_ID}\{DIRECTION}\by_year_validation_detail.csv
reports\validation\by_year\{RUN_ID}\{DIRECTION}\by_year_validation_summary.csv
reports\validation\by_year\{RUN_ID}\{DIRECTION}\final_research_candidates.csv
reports\validation\by_year\{RUN_ID}\{DIRECTION}\final_research_candidates_report.md
reports\validation\by_year\{RUN_ID}\{DIRECTION}\skipped_hypotheses.csv
```

The validator refuses to overwrite an existing run-specific output unless `--overwrite` is passed.

Useful controls:

```powershell
python scripts/validate_hypotheses_by_year.py --run-id 20260509_190544 --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --start-year 2020 --end-year 2026 --min-trades-per-year 100 --min-positive-year-ratio 0.75 --min-positive-symbol-ratio 0.75
python scripts/validate_hypotheses_by_year.py --run-id 20260509_190544 --symbols EURUSD GBPUSD USDJPY XAUUSD --years 2022 2023 2024 2025
python scripts/validate_hypotheses_by_year.py --run-id 20260509_190544 --include-incomplete-years
```

If `--start-year`, `--end-year`, and `--years` are omitted, the script detects available years in `ml_dataset`. Incomplete years are written to the detail CSV with `partial_year = true`; they do not affect the final classification unless `--include-incomplete-years` is passed. Final classifications are `select`, `watchlist`, or `reject`, ordered by year stability, cross-symbol stability, trade count, drawdown behavior, and profit factor improvement.

Classification meaning:

- `select`: stable enough across eligible symbol-years and symbols for the next research step.
- `watchlist`: interesting but not stable enough, or sample size is low.
- `reject`: weak stability, drawdown/PF deterioration, or performance concentrated in too few years.

The correct next step after a good `final_research_candidates_report.md` is still research-only: a separate rule-based backtest with explicit spread/cost assumptions and risk-model checks. Do not move a candidate directly to live trading.

### Random Baseline Robustness Tests

Random baseline testing is a separate post-validation robustness step. It reads final cross-pair and pair-specific candidates, applies each `combination_key` to `ml_dataset`, then compares the candidate against random samples with the same number of trades from the same universe.

It does not search for new strategies, does not create live signals, does not connect to MetaTrader 5, and does not call order execution APIs. Long and short, gross and net, and cross-pair and pair-specific candidates remain separate.

Run cross-pair final candidates for a known run:

```powershell
python scripts/run_random_baseline_tests.py --run-id 20260509_190544 --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-mode estimated --return-mode net --cost-config config/cost_model.example.json --strict-cost-config --overwrite
```

Include pair-specific candidates too:

```powershell
python scripts/run_random_baseline_tests.py --run-id 20260509_190544 --direction short --symbols EURUSD GBPUSD USDJPY XAUUSD --include-pair-specific --cost-mode estimated --return-mode net --cost-config config/cost_model.example.json --strict-cost-config --overwrite
```

Outputs are written to:

```text
reports\random_baseline\{RUN_ID}\{DIRECTION}\random_baseline_detail.csv
reports\random_baseline\{RUN_ID}\{DIRECTION}\random_baseline_summary.csv
reports\random_baseline\{RUN_ID}\{DIRECTION}\random_baseline_report.md
reports\random_baseline\{RUN_ID}\{DIRECTION}\skipped_random_baseline_candidates.csv
```

The random baseline report classifies candidates as `robust_vs_random`, `interesting_vs_random`, `weak_vs_random`, `not_better_than_random`, or `low_sample`. These labels are research diagnostics only; they are not trading instructions.

### Candidate Baseline Diagnostics

Candidate baseline diagnostics are a separate research-only step after yearly validation and random baseline robustness. The diagnostic reads only final cross-pair and pair-specific candidates, applies each `combination_key` to `ml_dataset`, and checks whether the full combination adds value beyond all candles, each single filter, leave-one-out filters, random same-trade-count baselines, and conditional random same-trade-count baselines inside each single-filter universe.

It does not search for new strategies, generate combinations outside the candidate's own filters, create live signals, connect to MetaTrader 5, or call order execution APIs. Long and short, gross and net, and cross-pair and pair-specific diagnostics remain separate.

Run long diagnostics:

```powershell
python scripts/run_candidate_baseline_diagnostics.py --run-id 20260509_190544 --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-mode estimated --return-mode net --strict-cost-config --cost-config config/cost_model.example.json --random-runs 250 --overwrite
```

Run short diagnostics:

```powershell
python scripts/run_candidate_baseline_diagnostics.py --run-id 20260509_190544 --direction short --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-mode estimated --return-mode net --strict-cost-config --cost-config config/cost_model.example.json --random-runs 250 --overwrite
```

Outputs are written to:

```text
reports\baseline_diagnostics\{RUN_ID}\{DIRECTION}\baseline_diagnostics_detail.csv
reports\baseline_diagnostics\{RUN_ID}\{DIRECTION}\baseline_diagnostics_summary.csv
reports\baseline_diagnostics\{RUN_ID}\{DIRECTION}\baseline_diagnostics_report.md
reports\baseline_diagnostics\{RUN_ID}\{DIRECTION}\skipped_baseline_diagnostics_candidates.csv
```

The diagnostic classifies candidates as `adds_incremental_value`, `mostly_single_filter_effect`, `not_better_than_context`, or `low_sample`. These labels only decide what deserves further research-only review; they are not buy/sell recommendations and do not make a candidate strategy-ready.

### Research Decision Report

The research decision report is a final research-only summary layer. It combines yearly validation candidates, random baseline robustness, skipped-candidate files, and optional scorecard or walk-forward outputs into one direction-specific report.

It classifies candidates as:

- `SCARTARE`
- `DA_APPROFONDIRE`
- `CANDIDATA_A_TEST_SUCCESSIVI`

`CANDIDATA_A_TEST_SUCCESSIVI` only means the candidate may deserve a future rule-based research backtest. It does not mean live-ready, buy/sell, or complete strategy.

Build the report after validation and random baseline outputs exist:

```powershell
python scripts/build_research_decision_report.py --run-id 20260509_190544 --direction long --cost-mode estimated --return-mode net --overwrite
python scripts/build_research_decision_report.py --run-id 20260509_190544 --direction short --cost-mode estimated --return-mode net --overwrite
```

Outputs are written to:

```text
reports\research_decision\{RUN_ID}\{DIRECTION}\research_decision_report.md
reports\research_decision\{RUN_ID}\{DIRECTION}\research_decision_summary.csv
reports\research_decision\{RUN_ID}\{DIRECTION}\research_decision_warnings.csv
```

The decision report does not generate new candidates, does not create signals, does not connect to MetaTrader 5, and does not call order execution APIs. Long and short, gross and net, and cross-pair and pair-specific rows remain separate.

Run the clearer combined validation pipeline wrapper in dry-run mode before any manual execution:

```powershell
python scripts/run_combined_validation_pipeline.py --run-id 20260509_190544 --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-config config/cost_model.example.json --dry-run
```

`scripts/run_combined_validation_pipeline.py` writes a manifest, command plan, stage results, summary, warnings, and markdown report under `reports\combined_validation_pipeline\{RUN_ID}\`. Controlled execution requires explicit `--execute` and should be user-run only for heavy research outputs. The older `scripts/run_research_validation_pipeline.py` remains available as a compatibility runner:

```powershell
python scripts/run_research_validation_pipeline.py --run-id 20260509_190544 --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-config config/cost_model.example.json
```

The orchestrator never evaluates mixed/global combined outputs automatically. With `--run-id`, it uses only `reports\backtests\combined\runs\{RUN_ID}\{DIRECTION}\`. With `--combined-input-dir`, it uses only that explicit directory. If neither is provided, it uses the latest valid directory under `reports\backtests\combined\runs\` for the selected direction.

Use `--overwrite-validation` only when you intentionally want to replace an existing `reports\validation\by_year\{RUN_ID}\{DIRECTION}\` validation output.

This orchestrator runs only:

```text
evaluate_combined_hypotheses.py
validate_hypotheses_by_year.py
build_final_feature_scorecard.py
```

It does not import data from MT5, does not send orders, and does not generate live signals.

## Full Research Pipeline

The full research pipeline script is a thin orchestrator around the existing scripts. It uses Python `subprocess`, writes a run log, and does not duplicate the feature, research, backtest, or evaluation logic from the individual scripts.

Recommended single command from the repository root:

```powershell
python scripts/run_full_research_pipeline.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --from-date 2022-01-01 --to-date 2025-12-31 --target-horizon 10 --direction long --cost-config config/cost_model.example.json --start-year 2020 --end-year 2026
```

To run with estimated/net defaults, pass an explicit cost config so the orchestrator can validate costs before child stages start:

```powershell
python scripts/run_full_research_pipeline.py --cost-config config/cost_model.example.json
```

Regenerate without reimporting prices:

```powershell
python scripts/run_full_research_pipeline.py --skip-calendar-import --skip-price-import --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --cost-config config/cost_model.example.json --start-year 2022 --end-year 2024 --overwrite-validation
python scripts/run_full_research_pipeline.py --skip-calendar-import --skip-price-import --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction short --cost-config config/cost_model.example.json --start-year 2022 --end-year 2024 --overwrite-validation
```

The full pipeline can optionally run the final post-validation review after yearly validation and the final feature scorecard:

```powershell
python scripts/run_full_research_pipeline.py --skip-calendar-import --skip-price-import --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --cost-mode estimated --return-mode net --strict-cost-config --cost-config config/brokers/pepperstone_historical_p75.local.json --start-year 2022 --end-year 2024 --run-final-review --include-pair-specific-final-review --random-baseline-runs 250 --diagnostics-random-runs 100 --overwrite-validation --overwrite-final-review
```

`--run-final-review` runs, in order, random baseline robustness, candidate baseline diagnostics, and the research decision report. The three steps can also be requested individually with `--run-random-baseline`, `--run-baseline-diagnostics`, and `--run-research-decision-report`.

`--overwrite-final-review` is separate from `--overwrite-validation` and is required to regenerate random baseline, diagnostics, or decision-report outputs. Candidate baseline diagnostics can be slow; the full-pipeline orchestration default is `--diagnostics-random-runs 100`. For a heavier final standalone review, run `scripts/run_candidate_baseline_diagnostics.py` directly with 250 or more random runs.

The single-run full pipeline does not run horizon consistency, historical spread analysis, MT5 spread comparison, rule-based backtests, live trading, or signal generation.

For explicit gross comparison runs, use `--cost-mode none --return-mode gross`. `--return-mode net` with `--cost-mode none`, missing estimated cost configs, and unreadable or invalid cost config files fail before orchestration starts child scripts.

Direction-specific research:

- `--direction long`: ML target is `target_up_{H}` and research returns use `future_return_{H}`.
- `--direction short`: ML target is `target_down_{H}` and research backtests/validation use `-future_return_{H}` in memory.
- Long and short reports are written separately and are not aggregated together.

Useful skip flags:

```powershell
python scripts/run_full_research_pipeline.py --cost-config config/cost_model.example.json --skip-checks
python scripts/run_full_research_pipeline.py --cost-config config/cost_model.example.json --continue-on-error
```

Prerequisites:

- MetaTrader 5 must be open and connected when `import_price_bars.py` runs, unless `--skip-price-import` is used.
- The economic calendar CSV must already be exported from MT5, either copied to `data\economic_calendar.csv` or passed with `--calendar-csv-source`.
- The local SQLite database `data\trading_bot.db` is generated locally and ignored by Git.
- Research dependencies such as `pandas` and `scikit-learn` must be installed for `ml_research.py`.

Each run uses a `RUN_ID` in `YYYYMMDD_HHMMSS` format unless `--run-id` is passed manually. The log is written to:

```text
logs\full_pipeline_{RUN_ID}.log
```

The final combined-hypothesis evaluation is written to:

```text
reports\backtests\combined\evaluations\{RUN_ID}\{DIRECTION}\
```

The final yearly validation is written to:

```text
reports\validation\by_year\{RUN_ID}\{DIRECTION}\final_research_candidates_report.md
reports\validation\by_year\{RUN_ID}\{DIRECTION}\final_research_candidates.csv
reports\validation\by_year\{RUN_ID}\{DIRECTION}\pair_specific_candidates_report.md
reports\validation\by_year\{RUN_ID}\{DIRECTION}\pair_specific_candidates.csv
reports\validation\by_year\{RUN_ID}\{DIRECTION}\skipped_hypotheses.csv
```

The optional random baseline robustness output is written to:

```text
reports\random_baseline\{RUN_ID}\{DIRECTION}\random_baseline_report.md
reports\random_baseline\{RUN_ID}\{DIRECTION}\random_baseline_detail.csv
reports\random_baseline\{RUN_ID}\{DIRECTION}\random_baseline_summary.csv
reports\random_baseline\{RUN_ID}\{DIRECTION}\skipped_random_baseline_candidates.csv
```

The optional candidate baseline diagnostics output is written to:

```text
reports\baseline_diagnostics\{RUN_ID}\{DIRECTION}\baseline_diagnostics_report.md
reports\baseline_diagnostics\{RUN_ID}\{DIRECTION}\baseline_diagnostics_detail.csv
reports\baseline_diagnostics\{RUN_ID}\{DIRECTION}\baseline_diagnostics_summary.csv
reports\baseline_diagnostics\{RUN_ID}\{DIRECTION}\skipped_baseline_diagnostics_candidates.csv
```

The final research-only decision report is written to:

```text
reports\research_decision\{RUN_ID}\{DIRECTION}\research_decision_report.md
reports\research_decision\{RUN_ID}\{DIRECTION}\research_decision_summary.csv
reports\research_decision\{RUN_ID}\{DIRECTION}\research_decision_warnings.csv
```

The final feature scorecard is written to:

```text
reports\final_feature_scorecard\{RUN_ID}\{DIRECTION}\final_feature_scorecard_report.md
reports\final_feature_scorecard\{RUN_ID}\{DIRECTION}\final_feature_scorecard.csv
reports\final_feature_scorecard\{RUN_ID}\{DIRECTION}\pair_specific_feature_scorecard.csv
```

The validation keeps two research levels separate:

- Cross-pair candidates are combinations that remain robust across multiple symbols. They use positive symbol ratio, positive year ratio, trade count, drawdown improvement, and profit-factor improvement.
- Pair-specific candidates are combinations that look useful for one symbol, even if they do not generalize to the others. They emphasize symbol, direction, positive year ratio, years tested, trades per year, profit-factor improvement, and drawdown behavior.

Cross-pair candidates are useful when looking for general features. Pair-specific candidates are useful when deciding what to test in a dedicated rule-based backtest for EURUSD, XAUUSD, USDJPY, or another single symbol. Pair-specific does not mean live-ready: any follow-up still needs a separate backtest with costs, spread, SL/TP, slippage, and risk assumptions.

The scorecard aggregates final yearly validation, selected combined hypotheses, ML feature ranking, backtest summaries, and pair-specific candidates into research-only rankings for one direction at a time. It does not produce operational instructions or strategies; it is only a decision aid for choosing what to test later in a separate rule-based backtest with explicit costs and risk assumptions.

Feature scorecard entries are ingredients for future rule-based backtests, not standalone trading strategies. The CSV files include:

```text
rule_role
tradability_note
```

`rule_role` separates potential entry or directional-bias ingredients from supporting filters:

- `ma_diff`: trend filter and possible entry-bias ingredient.
- `return_*`: momentum filter.
- `volatility_20`, `volatility_100`, and `volatility_ratio_20_100`: volatility regime filters.
- `true_range`, `atr_*`, and ATR-normalized candle/MA distance features: volatility-normalized price-action filters.
- `spread_avg_20`, `spread_price`, `spread_return`, and `spread_to_atr_20`: execution-quality filters.
- `tick_volume_avg_20`, `tick_volume_ratio_20`, `tick_volume_zscore_100`, `tick_volume_percentile_100`, `volume_spike_20`, `volume_dry_up_20`, `volume_vs_hour_avg`, and `volume_vs_session_avg`: volume/liquidity filters.
- `spread_to_volume_ratio`: execution-quality and liquidity-context filter.
- `hour` and `hour_session`: session filter.
- `day_of_week`: calendar filter.
- `blackout_window_*`, `post_news_window_*`, `has_news_*`, and `has_high_impact_news_*`: news/risk filter.
- `open`, `high`, `low`, `close`: not tradable alone and excluded from final promotion.
- `numeric_tercile`: not tradable alone unless thresholds are computed in a time-safe, train-only way. The current GBPUSD fixed candidate uses a frozen train-only threshold artifact; generic numeric-tercile research outputs without train-only lineage remain exploratory.

The scorecard report groups rows into potential entry/bias features, context filters, risk/news filters, execution-quality filters, and not-tradable-alone/excluded rows. A high-scoring feature can help design a future rule, but it is not a complete entry, exit, risk, and execution model.

You can also rebuild only the scorecard for an existing run:

```powershell
python scripts/build_final_feature_scorecard.py --run-id 20260509_190544 --direction long --overwrite
```

### Horizon Consistency Report

The horizon consistency report compares already-produced final feature scorecards across nearby target horizons: h5, h10, and h20. It is research-only and does not rerun backtests, search for new strategies, create live signals, or provide buy/sell recommendations.

The report keeps long and short separate, keeps gross and net separate, and can optionally include pair-specific scorecards without mixing them with cross-pair rows.

Example:

```powershell
python scripts/build_horizon_consistency_report.py --group-id 20260511_h5_h10_h20 --direction long --h5-run-id RUN_ID_H5 --h10-run-id RUN_ID_H10 --h20-run-id RUN_ID_H20 --cost-mode estimated --return-mode net --overwrite
```

Outputs are written to:

```text
reports\horizon_consistency\{GROUP_ID}\{DIRECTION}\horizon_consistency_report.md
reports\horizon_consistency\{GROUP_ID}\{DIRECTION}\horizon_consistency_summary.csv
reports\horizon_consistency\{GROUP_ID}\{DIRECTION}\horizon_consistency_warnings.csv
```

Classifications include `consistent_across_horizons`, `consistent_medium_slow`, `short_horizon_only`, `long_horizon_only`, `unstable_across_horizons`, and `insufficient_evidence`. These labels are research triage only; promising rows still need random baseline robustness, candidate baseline diagnostics, and a separate rule-based research backtest.

### Walk-Forward Research Validation

Yearly validation and walk-forward validation answer different research questions:

- Yearly validation checks whether hypotheses already found by the pipeline are stable by year and by symbol.
- Walk-forward validation is stricter: each fold selects hypotheses using only past train years and tests them on a future out-of-sample year.

Example folds:

```text
train 2020-2021 -> test 2022
train 2020-2022 -> test 2023
train 2020-2023 -> test 2024
train 2020-2024 -> test 2025
```

Run it directly:

```powershell
python scripts/run_walk_forward_research.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --train-start-year 2020 --first-test-year 2022 --last-test-year 2025 --overwrite
python scripts/run_walk_forward_research.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction short --train-start-year 2020 --first-test-year 2022 --last-test-year 2025 --overwrite
```

By default, walk-forward searches combinations up to 2 conditions. Larger combinations are controlled by beam search instead of exhaustive brute force:

```powershell
python scripts/run_walk_forward_research.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --max-combination-size 5 --max-seed-conditions 12 --max-candidates-per-level 50 --overwrite
```

`--max-combination-size 5` is optional. Longer combinations increase overfitting risk because each added condition can reduce trade count and fit train-year noise. Keep the default of 2 for normal research runs; use 5 only for controlled experiments, then validate any candidate with separate out-of-sample and rule-based backtests.

The main beam controls are:

- `--max-seed-conditions`: best train-period single conditions kept as seeds.
- `--max-candidates-per-level`: best train candidates retained after each beam level.
- `--max-cross-pair-candidates-per-fold`: cross-pair train-selected candidates tested on each future fold.
- `--max-pair-specific-candidates-per-symbol`: symbol-specific train-selected candidates tested per symbol.

Walk-forward output is direction-specific:

```text
reports\walk_forward\{RUN_ID}\{DIRECTION}\walk_forward_detail.csv
reports\walk_forward\{RUN_ID}\{DIRECTION}\walk_forward_summary.csv
reports\walk_forward\{RUN_ID}\{DIRECTION}\walk_forward_candidates.csv
reports\walk_forward\{RUN_ID}\{DIRECTION}\walk_forward_report.md
reports\walk_forward\{RUN_ID}\{DIRECTION}\pair_specific_walk_forward_candidates.csv
reports\walk_forward\{RUN_ID}\{DIRECTION}\pair_specific_walk_forward_report.md
```

Walk-forward keeps cross-pair and pair-specific candidates separate. Cross-pair rows must hold across symbols. Pair-specific rows are symbol-only research leads and should not be generalized to other instruments.

`numeric_tercile` remains skipped in generic walk-forward until fold-specific train-only thresholds are implemented. The fixed GBPUSD candidate has a separate frozen train-only threshold artifact and OOS validation path; that does not make generic walk-forward numeric terciles safe by default. This avoids using future test-year distribution information to create train-period hypotheses. Walk-forward can select binary volume/liquidity conditions such as `volume_spike_20:1`, `volume_spike_20:0`, `volume_dry_up_20:1`, and `volume_dry_up_20:0`; numeric volume thresholds should be added only when their cutoffs are computed from train rows.

The full pipeline can optionally run walk-forward after the final scorecard:

```powershell
python scripts/run_full_research_pipeline.py --skip-calendar-import --skip-price-import --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --cost-config config/cost_model.example.json --start-year 2022 --end-year 2024 --overwrite-validation --run-walk-forward
python scripts/run_full_research_pipeline.py --skip-calendar-import --skip-price-import --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction short --cost-config config/cost_model.example.json --start-year 2022 --end-year 2024 --overwrite-validation --run-walk-forward
```

Walk-forward validation is still research-only. It does not produce live signals, does not send orders, and does not call MetaTrader5.

### Overlapping Label Controls

With `target_horizon > 1`, nearby rows can share much of the same future movement. On M15 with `target_horizon 10`, a 10:00 row looks forward to about 12:30, while the 10:15 row looks forward to about 12:45. This is not necessarily direct leakage, but it can inflate apparent stability and significance.

Purged split removes train rows whose future label window reaches into the test period. Embargo adds a buffer by removing the first N bars from the test period. Non-overlap evaluation keeps roughly one row every `target_horizon` bars; it is stricter and reduces sample size.

Walk-forward uses purged train/test folds by default. Standard run with purge:

```powershell
python scripts/run_walk_forward_research.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --train-start-year 2020 --first-test-year 2022 --last-test-year 2025 --purge-overlap --embargo-bars 0
```

More severe walk-forward robustness run:

```powershell
python scripts/run_walk_forward_research.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --train-start-year 2020 --first-test-year 2022 --last-test-year 2025 --purge-overlap --embargo-bars 10 --non-overlap-test
```

Yearly validation can run a non-overlap robustness check:

```powershell
python scripts/validate_hypotheses_by_year.py --run-id RUN_ID --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --non-overlap-eval
```

The full pipeline exposes the same controls with `--purge-overlap`, `--no-purge-overlap`, `--embargo-bars`, `--non-overlap-walk-forward`, and `--non-overlap-validation`.

Use `--skip-yearly-validation` only when you want to stop after combined-hypothesis evaluation. Use `--overwrite-validation` to regenerate an existing validation output for the same `RUN_ID`.

The full pipeline remains offline research only. It does not create live trading signals, does not send orders, and does not call order execution APIs.

### Cost-Adjusted Returns

Cost-aware research, validation, and post-validation scripts default to `--cost-mode estimated --return-mode net`. Research reports remain backward compatible with existing gross-return outputs through explicit `--cost-mode none --return-mode gross`, while gross mode remains available for comparison runs.

`--overwrite` and `--overwrite-validation` are intentionally not defaults. Regenerating existing report folders must remain explicit and opt-in.

Estimated net returns can be enabled with:

```text
net_strategy_return = gross_strategy_return - estimated_cost_return
```

For each research sample, gross strategy return is direction-aware:

- long: `future_return_H`
- short: `-future_return_H`

Estimated costs are offline assumptions only:

- spread cost from current-row `spread`, then `spread_avg_20`, then configured fallback spread points;
- slippage cost in basis points;
- commission cost in basis points.

MetaTrader 5 spread values are often stored in points. The research cost model converts them with:

```text
spread_price = spread_points * point_size
spread_cost_return = spread_price / close
```

The feature layer uses the same point-to-price conversion for `spread_price`, `spread_return`, and `spread_to_atr_20`; historical reports generated before this correction should not be rewritten unless intentionally regenerated.

The example config is tracked at:

```text
config/cost_model.example.json
```

See [Cost Model](docs/research/COST_MODEL.md) for the full interpretation of gross returns, estimated costs, strict config, point sizes, and local broker-specific config policy.

Versioned Pepperstone research examples are available at `config/brokers/pepperstone_razor.example.json` and `config/brokers/pepperstone_standard.example.json`. Copy one to an ignored local file such as `config/brokers/pepperstone_razor.local.json`, verify account-specific commission/slippage and spread assumptions, then pass it explicitly with `--cost-config config/brokers/pepperstone_razor.local.json`.

`scripts/run_full_research_pipeline.py` and `scripts/run_research_validation_pipeline.py` validate cost/return settings before launching child scripts. Estimated orchestration requires an explicit readable JSON `--cost-config`; gross/none remains available for comparison runs with `--cost-mode none --return-mode gross`. This preflight is research-run hygiene only and does not imply live readiness.

Point size depends on the broker symbol definition. Internal no-config defaults are limited to common FX examples such as `EURUSD=0.00001`, `GBPUSD=0.00001`, `AUDUSD=0.00001`, `USDCAD=0.00001`, `USDCHF=0.00001`, and `USDJPY=0.001`. For XAUUSD and other CFDs, provide a config-driven `point_size` verified against the broker symbol definition before relying on spread or net-cost features. An observed read-only XAUUSD MT5 snapshot with `point=0.01` can be stored locally as `config/symbol_metadata.local.json`; a current spread snapshot such as 24 points is not a fixed historical spread and should not replace `price_bars.spread`.

For more reliable net results, pass `--strict-cost-config` together with `--cost-mode estimated`. Strict mode requires every requested symbol to have an explicit `symbols.<SYMBOL>.point_size` in the cost config. It also requires either `fallback_spread_points` in the cost config or usable `spread`/`spread_avg_20` values in `ml_dataset`.

Without strict mode, research scripts keep the backward-compatible internal defaults, but they print warnings when a symbol uses an internal default `point_size` or internal fallback spread. Treat those warnings as a sign that net results are only rough estimates.

Before trusting estimated net reports, verify every `point_size` against the broker's MetaTrader 5 Symbol Info for the exact exported symbol. Broker suffixes, metals, JPY pairs, CFDs, and account types can use different point conventions.

Cost-adjusted reports include these audit fields:

```text
cost_config_source
point_size_source
spread_source_used
symbols_using_default_costs
```

Single-candidate stress reports also include base/stress effective-cost diagnostics: point-size source/value, spread-source counts across replayed trades, row-level and fallback spread counts, max-row-or-fallback fallback-selection counts, fallback spread source/value, whether fallback spreads were actually used, selected stress spread policy, effective slippage/commission bps, `stress_changed_cost_R`, and a no-effect explanation when paired cost configs produce identical `cost_R` and `net_R`. The default stress spread policy keeps the normal row-level spread priority. Explicit research-only stress policies can compare costs with `max(row spread or spread_avg_20, configured fallback)` or with configured fallback overriding row-level spread when available.

Net results are more realistic than gross results, but they are still offline estimates, not real execution simulation. Slippage and commissions can vary by broker, account type, session, volatility, and order size. No net report is a live-trading guarantee. On M15, small theoretical edges can disappear after spread, slippage, and commission assumptions.

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

It writes audit CSV/MD files under `reports/cost_model/historical_spreads/{RUN_ID}/` and, with `--generate-config`, ignored local configs such as `config/brokers/pepperstone_historical_p90.local.json`.

Recent MT5 spreads from the currently logged-in terminal can be compared with local DB spread history in read-only diagnostic mode:

```powershell
python scripts/compare_mt5_recent_spreads.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --mt5-lookback-hours 24 --broker-name Pepperstone --account-type Razor --overwrite
```

It writes comparison CSV/MD files under `reports/cost_model/mt5_spread_comparison/{RUN_ID}/` and does not generate cost configs.

## Common Errors

`CSV missing`: run the MQL5 script manually in MetaTrader 5 and copy `economic_calendar.csv` into `data\economic_calendar.csv`, or pass `--csv-source` with the path to the MT5 `MQL5\Files` CSV.

`Database missing`: run `python scripts/init_database.py`, or run `python scripts/run_pipeline.py` without `--import-only`.

`Empty CSV`: the importer exits gracefully with zero rows read, inserted, and skipped. Re-run the MT5 export if records were expected.

`Wrong delimiter`: the importer detects comma or semicolon automatically and falls back to comma. If the header still cannot be read, it prints the detected delimiter and columns.

`Missing required columns`: the importer prints the required columns, detected columns, detected delimiter, and a hint that the CSV header or delimiter may be wrong.

`Duplicate value_id rows`: duplicate rows are skipped non-destructively. Existing database rows are not deleted or overwritten.

`MetaTrader5 package missing`: install it with `python -m pip install MetaTrader5` in the same environment used to run the scripts.

`ML research dependencies missing`: install them with `python -m pip install -r requirements.txt` in the same environment used to run the scripts.

`Symbol unavailable`: open MetaTrader 5, verify that the symbol exists in Market Watch, and retry. The importer attempts `mt5.symbol_select(symbol, True)` before failing.

## Git-Ignored Files

The repository intentionally ignores generated and local-only files, including:

- `*.db`
- `*.sqlite`
- `*.csv`
- `__pycache__/`
- `venv/`
- `.env`
- `state/*`
- `graphify-out/`
- MT5 Files/Common Files exports copied into the repository
- `config/cost_model.local.json`
- `config/brokers/*.json`
- `logs/*.log`
- `reports/ml_research/*`
- `reports/backtests/*`
- `reports/cost_model/*`
- `reports/validation/*`
- `reports/random_baseline/*`
- `reports/baseline_diagnostics/*`
- `reports/horizon_consistency/*`
- `reports/research_decision/*`
- `reports/research_branch_outcomes/*`
- `reports/hypothesis_discovery_pipeline/*`
- `reports/combined_validation_pipeline/*`
- `reports/preferred_horizon_cost_diagnostics/*`
- `reports/regime_candidate_review/*`
- `reports/rule_based_regime_candidate_backtests/*`
- `reports/rule_based_regime_candidate_review/*`
- `reports/controlled_rule_research_expansion/*`
- `reports/timeout_fragility_audit/*`
- `reports/timeout_root_cause_review/*`
- `reports/timeout_sequence_drilldown_review/*`
- `reports/timeout_policy_sensitivity_review/*`
- `reports/rule_candidate_gate_decisions/*`
- `reports/candidate_audit_pipeline/*`
- `reports/tp_sl_path_backtests/*`

Do not commit `.env`, broker exports, local broker-specific cost configs, SQLite databases, CSV data, generated reports, runtime state, Graphify output, MT5 Files/Common Files exports, or logs. Versionable broker examples must use `config/brokers/*.example.json`. The placeholder files `data/.gitkeep`, `models/.gitkeep`, `logs/.gitkeep`, `reports/.gitkeep`, `reports/ml_research/.gitkeep`, and `reports/validation/.gitkeep` remain trackable so the empty folders are preserved in Git.
