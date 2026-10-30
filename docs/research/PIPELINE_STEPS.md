# Pipeline Steps

When modifying the pipeline, update this document if the change affects scripts, outputs, methodology, or next actions.

This table is a reference map for the current offline research pipeline. The files listed here are scripts and versioned code paths, not generated data artifacts.

| Step | Script | Input | Output | What It Does | What It Does Not Do | Type |
|---:|---|---|---|---|---|---|
| 1 | `scripts/init_database.py` | Local paths and schema definitions | SQLite schema in `data/trading_bot.db` | Creates local research tables for events, price bars, features, market features, and ML dataset rows. | Does not import broker data, run models, backtest, or trade. | Utility |
| 2 | `scripts/run_pipeline.py` | `data/economic_calendar.csv` or `--csv-source`; local DB path | Initialized DB and imported `economic_events` rows | Orchestrates local folder setup, DB initialization, and calendar CSV import. | Does not import prices, generate features, run ML, backtest, or trade. | Utility |
| 3 | `scripts/import_price_bars.py` | MT5 terminal, symbol, timeframe, date range, local DB | `price_bars` rows in SQLite | Imports read-only historical OHLCV bars from MT5 using `copy_rates_range()`. | Does not send orders or use execution APIs. | Utility |
| 4 | `scripts/generate_price_features.py` | `price_bars` plus optional point-size config | `price_features` rows | Generates price, true-range/ATR, volatility, unit-consistent spread, session, and tick-volume/liquidity features. Raw spread remains in points; `spread_price`, `spread_return`, and `spread_to_atr_20` use `point_size`. | Does not use future returns, train models, backtest, or trade. | Utility |
| 5 | `scripts/generate_market_features.py` | `price_features`, `economic_events` | `market_features` rows | Adds time-safe news timing, importance, blackout, post-news, and event-count context. | Does not use `actual`, `forecast`, `previous`, or `surprise` values as pre-news features. | Utility |
| 6 | `scripts/generate_ml_dataset.py` | `market_features` | `ml_dataset` rows | Adds future-return, future-path, MFE/MAE, h5/h10/h20 triple-barrier, and directional target columns for supervised research. | Does not train models, create signals, backtest, or trade. | Utility |
| 7 | `scripts/ml_research.py` | `ml_dataset`, symbol, timeframe, target horizon, direction | ML research CSVs under `reports/ml_research/...` | Produces offline feature rankings and model diagnostics with temporal train/test split, raw and direction-aware return diagnostics, and future/target label exclusions from features. | Does not deploy a model, produce live predictions, or create operational signals. | Exploratory |
| 8 | `scripts/analyze_research_reports.py` | ML research report folders | `summary_feature_ranking.csv`, aggregate rankings, markdown summary when applicable | Summarizes feature rankings across one or more ML research output folders. | Does not validate profitability or create a trading strategy. | Exploratory |
| 9 | `scripts/backtest_research.py` | `ml_dataset`, feature buckets, direction, gross/net settings | Exploratory backtest CSV/MD reports under `reports/backtests/...` | Tests single-feature research buckets against matching baselines. | Does not represent a deployable strategy or signal engine. | Exploratory |
| 10 | `scripts/evaluate_backtest_results.py` | Exploratory backtest folders | Evaluated backtest summaries | Compares exploratory buckets against baselines with improvement and risk metrics. | Does not prove robustness or live readiness. | Validation |
| 11 | `scripts/select_research_hypotheses.py` | Evaluated exploratory backtest reports | Selected research hypothesis CSV/MD files | Selects research hypotheses for controlled combined testing. | Does not select live trades or create executable strategy rules. | Validation |
| 12 | `scripts/backtest_combined_hypotheses.py` | Selected hypotheses, `ml_dataset`, direction, gross/net settings | Combined hypothesis reports under `reports/backtests/combined/...` | Tests controlled combinations of selected feature conditions. | Does not execute orders or guarantee out-of-sample stability. | Validation |
| 13 | `scripts/evaluate_combined_hypotheses.py` | Combined hypothesis folders, optional run ID and direction | Timestamped evaluation outputs under `reports/backtests/combined/evaluations/...` | Evaluates combined hypotheses and separates direction-specific results. | Does not perform yearly validation or produce final trader decisions. | Validation |
| 14 | `scripts/validate_hypotheses_by_year.py` | Selected combined hypotheses, `ml_dataset`, symbols, years, direction | `final_research_candidates*`, `pair_specific_candidates*`, validation details | Validates selected hypotheses by year and symbol, keeping cross-pair and pair-specific candidates separate. | Does not make candidates live-ready or turn them into signals. | Validation |
| 15 | `scripts/run_random_baseline_tests.py` | Final cross-pair and/or pair-specific candidate CSVs, `ml_dataset`, symbols, direction, gross/net settings | Random baseline reports under `reports/random_baseline/{RUN_ID}/{DIRECTION}/` | Compares final candidates against random same-trade-count samples from the same universe. | Does not search for new strategies, create live signals, import MT5 data, or execute orders. | Validation |
| 16 | `scripts/run_candidate_baseline_diagnostics.py` | Final cross-pair and/or pair-specific candidate CSVs, `ml_dataset`, symbols, direction, gross/net settings | Baseline diagnostics reports under `reports/baseline_diagnostics/{RUN_ID}/{DIRECTION}/` | Checks whether a final candidate adds incremental value over all candles, its single filters, leave-one-out filters, random same-trade-count baselines, and conditional random baselines. | Does not search for new strategies, generate new combinations outside candidate filters, create signals, import MT5 data, or execute orders. | Validation |
| 17 | `scripts/build_final_feature_scorecard.py` | Yearly validation outputs, ML rankings, backtest summaries, selected hypotheses | `final_feature_scorecard*` and pair-specific scorecard outputs | Aggregates research evidence into feature and condition rankings for future backtests. | Does not create a complete strategy or trader-facing report. | Final scoring |
| 18 | `scripts/build_horizon_consistency_report.py` | h5/h10/h20 final feature scorecards, optional pair-specific scorecards and validation candidates | Horizon consistency outputs under `reports/horizon_consistency/{GROUP_ID}/{DIRECTION}/` | Compares feature/condition behavior across nearby target horizons without rerunning backtests. | Does not search for strategies, create signals, make buy/sell recommendations, or mix long/short or gross/net rows. | Final scoring |
| 19 | `scripts/run_walk_forward_research.py` | `ml_dataset`, symbols, train/test years, direction, gross/net settings | Walk-forward reports under `reports/walk_forward/{RUN_ID}/{DIRECTION}/` | Selects candidates on past train years and tests them on future out-of-sample folds. | Does not mix train and test periods intentionally, and does not create live signals. | Validation |
| 20 | `scripts/build_research_decision_report.py` | Final validation candidates, random baseline detail/summary, skipped files, optional scorecard and walk-forward outputs | `research_decision_report.md`, `research_decision_summary.csv`, `research_decision_warnings.csv` under `reports/research_decision/{RUN_ID}/{DIRECTION}/` | Produces a final research-only triage into `SCARTARE`, `DA_APPROFONDIRE`, and `CANDIDATA_A_TEST_SUCCESSIVI`. | Does not create signals, make buy/sell recommendations, turn candidates into strategies, or mix long/short, gross/net, or candidate scopes. | Final scoring |
| 21 | `scripts/run_full_research_pipeline.py` | Calendar CSV, MT5 price availability unless skipped, symbols, timeframe, direction, costs, optional final-review flags | Full offline run outputs, logs, combined evaluation, validation, scorecard, optional walk-forward, optional final review | Orchestrates the complete offline research workflow using existing scripts and can optionally run random baseline, baseline diagnostics, and the research decision report. | Does not add trading execution, duplicate numerical logic from child scripts, run horizon consistency, run spread calibration/comparison, or add rule-based strategy backtests. | Utility |
| 22 | `scripts/run_research_validation_pipeline.py` | Existing combined run ID or explicit combined input dir, symbols, direction | Combined evaluation, yearly validation, and final scorecard outputs | Runs the post-backtest validation stage for an existing combined research run. | Does not import data, regenerate features, send orders, or generate live signals. | Utility |
| 23 | `scripts/condition_utils.py` | Validated `combination_key` strings and prepared research rows | Parsed predicates or controlled skip reasons | Provides shared parsing for final validation, random-baseline, and baseline-diagnostics condition evaluation. | Does not generate candidates, run backtests, or connect to MT5. | Utility |
| 24 | `scripts/analyze_historical_spreads.py` | Local SQLite `price_bars.spread` or `price_features.spread_avg_20` | Historical spread audit reports and optional ignored `.local.json` cost configs | Calculates p75/p90/p95 spread statistics for offline cost-model calibration. | Does not connect to MT5, fetch broker data, generate signals, or change pipeline defaults. | Utility |
| 25 | `scripts/compare_mt5_recent_spreads.py` | Current read-only MT5 tick spreads and local SQLite historical spread samples | MT5-vs-DB spread comparison reports | Compares recent MT5 p50/p75/p90/p95 spreads with historical DB spread percentiles. | Does not generate configs, send orders, open or close positions, create signals, or change pipeline defaults. | Utility |
| 26 | `scripts/compare_ml_target_reports.py` | Target-specific `ml_research.py` outputs, or `ml_dataset` when `--run-ml-research` is passed | Target comparison CSV/MD reports under `reports/ml_research/target_comparison/...` | Compares model metrics, average precision lift, threshold diagnostics, and direction-aware return summaries across supervised ML targets. | Does not change normal ML output paths, train live models, create signals, or alter selection methodology. | Exploratory |
| 27 | `scripts/build_preferred_target_feature_stability.py` | Preferred FX target-specific ML report folders under `reports/ml_research/target_runs/...` | Feature stability CSV/MD reports under `reports/ml_research/preferred_target_feature_stability/...` | Summarizes top-N feature recurrence, ranks, and feature families across EURUSD, GBPUSD, and USDJPY for the preferred 2ATR/1ATR h10 targets. | Does not train models, change thresholds, alter target selection, include XAUUSD by default, or create signals. | Exploratory |
| 28 | `scripts/build_preferred_feature_hypothesis_shortlist.py` | Preferred target feature stability CSVs | Preferred feature hypothesis CSV/MD reports under `reports/ml_research/preferred_feature_hypotheses/...` | Filters stable features and classifies family, research role, normalized/raw status, recommended usage, and caution level for follow-up research design. | Does not create a strategy, change model training, change backtest selection, include XAUUSD by default, or create signals. | Exploratory |
| 29 | `scripts/run_preferred_feature_backtests.py` | Preferred feature hypothesis shortlists, `ml_dataset`, direction, gross/net settings | Run-scoped preferred feature backtest CSV/MD reports under `reports/preferred_feature_backtests/{RUN_ID}/{DIRECTION}/` | Reuses `backtest_research.py` single-feature bucket logic for shortlisted normalized/contextual features and summarizes per-symbol plus aggregate exploratory rows with scenario source tags, same-symbol baseline deltas, and skipped-feature reasons. | Does not change pipeline defaults, create strategy rules, include XAUUSD by default, or create signals. | Exploratory |
| 30 | `scripts/compare_preferred_feature_backtest_cost_modes.py` | Existing gross/none and estimated/net preferred-feature backtest runs | Cost-mode comparison CSV/MD reports under `reports/preferred_feature_backtests/cost_mode_comparison/...` | Matches preferred-feature rows across cost modes, preserves scenario-source and shortlist metadata, reports source-tag diagnostics, and flags gross edges erased by estimated costs. | Does not rerun backtests, change costs, create strategy rules, or create signals. | Exploratory |
| 31 | `scripts/run_preferred_feature_combination_backtests.py` | Preferred feature cost-mode comparison CSVs, `ml_dataset`, direction, gross/net settings | Controlled two-filter reports under `reports/preferred_feature_combination_backtests/{RUN_ID}/{DIRECTION}/` | Tests small rank-aligned two-filter combinations from preferred gross-positive, cost-erased single-filter candidates, keeping symbols and directions separate, writing zero-trade combinations to skipped output, and reporting candidate diagnostics by filter stage. | Does not run exhaustive search, create operational rules, include XAUUSD by default, add execution, position sizing, stops, targets, multi-timeframe features, or create signals. | Exploratory |
| 32 | `scripts/run_tp_sl_path_backtests.py` | Explicit fixed candidate filters or an existing preferred-feature `combination_backtest_detail.csv`, `ml_dataset` OHLC path rows, direction, TP/SL/horizon, gross/net settings | TP/SL path diagnostic reports under `reports/tp_sl_path_backtests/{RUN_ID}/{DIRECTION}/` | Evaluates already-discovered filter combinations with current-close entry, ATR-based TP/SL path exits, conservative same-bar handling, timeout at horizon close, R-multiple metrics, baseline comparison, source-combination metadata, and skipped-row audit. Batch mode evaluates only rows already present in the input CSV. | Does not optimize TP/SL values, search for new candidates, create feature pairs, add position sizing, connect to MT5, execute orders, or create signals. | Exploratory |
| 33 | `scripts/build_research_branch_outcome_report.py` | Existing TP/SL path diagnostic summary/detail CSVs, branch metadata, direction run IDs | Branch closure reports under `reports/research_branch_outcomes/{RUN_ID}/` | Summarizes already-generated TP/SL path diagnostic outputs into a research-only closure record with classification counts, best rejected rows, and rejected-combination reasons. | Does not rerun backtests, search combinations, optimize TP/SL, add features, connect to MT5, execute orders, or create signals. | Final scoring |
| 34 | `scripts/run_preferred_horizon_cost_diagnostics.py` | Matrix dimensions, local cost configs, existing preferred-feature workflow scripts, or an existing matrix run ID | Matrix planning, optional orchestration reports, and zero-tested diagnostics under `reports/preferred_horizon_cost_diagnostics/{RUN_ID}/` | Builds a controlled h5/h10/h20 by p50/p75/p90 matrix for FX and separate XAUUSD groups, records child commands, can run existing preferred-feature, cost comparison, combination, TP/SL path, and branch-outcome scripts, and can diagnose existing zero-tested branches without rerunning child scripts. Branch decisions distinguish closed branches from branches with zero tested TP/SL path combinations. | Does not duplicate backtest logic, optimize TP/SL, add features, search beyond the controlled preferred-feature flow, connect to MT5, execute orders, or create signals. | Utility |
| 35 | `scripts/diagnose_preferred_horizon_prerequisites.py` | `ml_dataset`, preferred feature hypothesis shortlist folders, groups, symbols, horizons, target family | Prerequisite diagnostics under `reports/preferred_horizon_prerequisites/{RUN_ID}/` | Checks whether preferred target columns, target class balance, preferred shortlist files, and candidate feature names are present before preferred-feature horizon runs. | Does not run backtests, generate labels, build shortlists, search combinations, optimize TP/SL, add features, connect to MT5, execute orders, or create signals. | Utility |
| 36 | `scripts/build_preferred_horizon_shortlists.py` | Target-specific ML research inputs, configured horizons, target-run symbols, and stability symbols | Preferred horizon shortlist build manifest under `reports/ml_research/preferred_horizon_shortlist_builds/{RUN_ID}/`, plus preferred stability and shortlist files under their existing roots | Reuses existing target comparison, preferred-target feature stability, and preferred feature hypothesis shortlist scripts to build h5/h10/h20 preferred ranking and shortlist inputs with the same methodology as h10. | Does not run backtests, search feature combinations, optimize TP/SL, add features, connect to MT5, execute orders, or create signals. | Utility |
| 37 | `scripts/validate_regime_candidate_stress.py` | One explicit symbol/direction/regime/target candidate, optional exact candidate summary or fixed conditions, `ml_dataset`, optional base/stress cost configs | Regime candidate stress reports under `reports/regime_candidate_stress/{RUN_ID}/` | Replays one fixed historical candidate with exact-feature-combination scope when provided, sequential/no-overlap metrics, cost-stress comparison, effective-cost-field diagnostics, optional research-only stress spread policy, random baseline summaries, yearly and walk-forward summaries. | Does not search candidates, change TP/SL, alter target families, add features, connect to MT5, execute orders, size positions, or create signals. | Validation |
| 38 | `scripts/build_regime_candidate_review_package.py` | Existing regime candidate stress output folder | Review package under `reports/regime_candidate_review/{RUN_ID}/` | Reads existing stress CSV outputs and summarizes exact-scope validity, conservative cost stress, random baseline, yearly, walk-forward, exit-profile, equity, drawdown, and concentration diagnostics into a research-only classification. | Does not rerun validation, search candidates, change TP/SL, alter target families, add features, or read beyond the provided CSV folder. | Final scoring |
| 39 | `scripts/run_rule_based_regime_candidate_backtest.py` | Existing ready review package and/or stress output folder, `ml_dataset`, fixed cost configs | Rule-replay audit under `reports/rule_based_regime_candidate_backtests/{RUN_ID}/` | Reconstructs one exact reviewed candidate, replays the fixed rule on historical rows with the same TP/SL path assumptions and conservative stress-spread policy, then compares generated trade/equity files with the previous stress-validation outputs. | Does not search candidates, add filters, weaken conditions, change TP/SL, add features, add multi-timeframe logic, or write outside the run-scoped report folder. | Validation |
| 40 | `scripts/build_rule_based_regime_candidate_review.py` | Existing rule-replay output folder | Extended rule review under `reports/rule_based_regime_candidate_review/{RUN_ID}/` | Reads existing rule-replay CSV outputs and summarizes monthly, yearly, rolling-window, exit-profile, entry-hour, drawdown-sequence, and concentration diagnostics into a research-only classification. | Does not rerun the replay, read the database, recompute entries, add filters, weaken conditions, change TP/SL, add features, add multi-timeframe logic, or write outside the run-scoped review folder. | Final scoring |
| 41 | `scripts/build_controlled_rule_research_expansion.py` | Existing extended rule review folder and optional rule-replay output folder | Controlled expansion package under `reports/controlled_rule_research_expansion/{RUN_ID}/` | Reads existing review/replay CSV outputs and prepares entry-hour, chronological subperiod, nuanced timeout-severity, drawdown, concentration, baseline-plan, and cost-sensitivity-plan diagnostics for the already validated rule. | Does not rerun the replay, read the database, recompute entries, search features, add filters, weaken conditions, change TP/SL, add multi-timeframe logic, or write outside the run-scoped expansion folder. | Final scoring |
| 42 | `scripts/build_timeout_fragility_audit.py` | Existing controlled expansion folder and existing rule-replay output folder for one already validated candidate | Timeout fragility audit under `reports/timeout_fragility_audit/{RUN_ID}/` | Reads existing CSV outputs and audits only the stress TIMEOUT bucket with yearly, monthly, entry-hour, subperiod, rolling-window, sequence, and timeout-vs-non-timeout diagnostics before baseline and cost-sensitivity review. | Does not rerun the replay, read the database, recompute entries, search features, add filters, weaken conditions, change TP/SL, add multi-timeframe logic, or write outside the run-scoped audit folder. | Final scoring |
| 43 | `scripts/build_timeout_root_cause_review.py` | Existing timeout fragility audit folder and existing rule-replay output folder, with optional read-only `ml_dataset` enrichment | Timeout root-cause review under `reports/timeout_root_cause_review/{RUN_ID}/` | Reads existing CSV outputs and diagnoses whether TIMEOUT fragility is driven by sequence concentration, calendar/hour clustering, costs, or optional read-only feature context before returning to baseline and cost-sensitivity review. | Does not rerun replay or stress validation, recompute entries, search features, add filters, weaken conditions, change exit logic, optimize TP/SL, add multi-timeframe logic, or write outside the run-scoped review folder. | Final scoring |
| 44 | `scripts/build_timeout_sequence_drilldown_review.py` | Existing timeout root-cause review folder, timeout audit folder, and rule-replay output folder, with optional read-only `ml_dataset` enrichment | Timeout sequence drilldown under `reports/timeout_sequence_drilldown_review/{RUN_ID}/` | Reads existing CSV outputs and drills into the largest TIMEOUT drawdown sequence with calendar, entry-hour, cost, gross_R proxy, sequence-vs-timeout, and optional read-only feature-context diagnostics. | Does not rerun replay, recompute entries, search features, add filters, weaken conditions, change exit logic, optimize TP/SL, add multi-timeframe logic, or write outside the run-scoped drilldown folder. | Final scoring |
| 45 | `scripts/build_rule_candidate_gate_decision_report.py` | Existing candidate review, rule replay, rule review, controlled expansion, timeout audit, timeout root-cause, and timeout sequence report folders | Gate decision report under `reports/rule_candidate_gate_decisions/{RUN_ID}/` | Summarizes the full fixed-candidate validation chain and decides whether to reject, retain timeout review, or allow only limited offline baseline/cost-sensitivity review with an unresolved timeout caveat. | Does not rerun replay or validation, recompute entries, search features, add filters, weaken conditions, change TP/SL, add multi-timeframe logic, or write outside the run-scoped gate folder. | Final scoring |
| 46 | `scripts/build_timeout_policy_sensitivity_review.py` | Existing rule-replay folder, timeout audit/root-cause/sequence summaries, `ml_dataset`, and fixed cost configs | Timeout policy sensitivity review under `reports/timeout_policy_sensitivity_review/{RUN_ID}/` | Compares current h10 timeout handling, biased timeout-excluded diagnostics, and h20/h40/h80 future-bar sensitivity for existing h10 timeout entries only. | Does not rerun replay, recompute entries, search features, add filters, weaken conditions, change TP/SL, optimize horizons, add multi-timeframe logic, or write outside the run-scoped sensitivity folder. | Final scoring |
| 47 | `scripts/run_candidate_audit_pipeline.py` | Existing stress-output folder, database path, fixed cost configs, and explicit `--dry-run` or `--execute` mode | Manifest, command plan, stage results, summary, warnings, logs, and report under `reports/candidate_audit_pipeline/{RUN_ID}/` | Plans the fixed-candidate audit chain in dry-run mode or runs existing child scripts in controlled execution mode with stage gating and stop-on-failure/rejection defaults. | Does not search features, add filters, change methodology, create signals, imply live readiness, or run without an explicit mode. Codex should use help/tests/dry-run only; real execution is user-run for heavy candidates. | Utility |
| 48 | `scripts/run_hypothesis_discovery_pipeline.py` | Existing exploratory backtest outputs, symbols, direction, costs, and explicit `--dry-run` or `--execute` mode | Manifest, command plan, stage results, summary, warnings, logs, and report under `reports/hypothesis_discovery_pipeline/{RUN_ID}/`; planned combined outputs under `reports/backtests/combined/runs/{RUN_ID}/{DIRECTION}/{SYMBOL}_{TIMEFRAME}_h{H}/` when executed | Plans or runs the minimal upstream discovery chain: `evaluate_backtest_results.py`, `select_research_hypotheses.py`, and one `backtest_combined_hypotheses.py` command per symbol. | Does not import data, regenerate features, run validation, create signals, imply live readiness, or run without an explicit mode. Codex should use help/tests/dry-run only; real execution is user-run for heavy outputs. | Utility |
| 49 | `scripts/run_combined_validation_pipeline.py` | Existing combined run ID or explicit combined input dir, symbols, direction, costs, and explicit `--dry-run` or `--execute` mode | Manifest, command plan, stage results, summary, warnings, logs, and report under `reports/combined_validation_pipeline/{RUN_ID}/` plus existing combined evaluation, yearly validation, and scorecard child outputs when executed | Plans or runs the combined validation sub-pipeline: `evaluate_combined_hypotheses.py`, `validate_hypotheses_by_year.py`, and `build_final_feature_scorecard.py`. | Does not import data, regenerate features, run discovery backtests, create signals, imply live readiness, or run without an explicit mode. Codex should use help/tests/dry-run only; real execution is user-run for heavy outputs. | Utility |

Cost-aware research, validation, and post-validation scripts default to `--cost-mode estimated --return-mode net`. Use `--cost-mode none --return-mode gross` explicitly for gross comparison runs. Existing report outputs still require explicit `--overwrite` or `--overwrite-validation` to regenerate, and estimated net returns remain offline cost accounting rather than real execution simulation.

The two current orchestration scripts preflight cost/return settings before launching child stages. Estimated orchestration requires an explicit readable JSON `--cost-config`; gross/none remains available for comparison runs. This validation is only a run-configuration guard and does not make any output live-ready.

`scripts/research_pipeline_utils.py` contains shared orchestration-only primitives for future wrappers: command planning, dry-run execution records, manifest writing, overwrite guards, command logs, and status aggregation. It does not implement research methodology, cost math, feature safety, condition parsing, candidate-audit schemas, metrics, or trading behavior.

`scripts/run_candidate_audit_pipeline.py` supports dry-run planning and explicit controlled execution mode. Execution uses stage-summary gating, writes per-stage results and logs, stops on failure or rejection by default, and remains offline research-only. Codex should not run `--execute` on real candidate outputs.

`scripts/run_hypothesis_discovery_pipeline.py` is the first clean wrapper for the upstream hypothesis discovery chain that produces run-scoped combined hypothesis outputs. It is exploratory-only, uses shared orchestration utilities, and prepares inputs that `scripts/run_combined_validation_pipeline.py` can consume later.

`scripts/run_combined_validation_pipeline.py` is the clearer future wrapper for combined hypothesis validation. It writes run-scoped orchestration artifacts and uses the shared orchestration utilities for dry-run planning, command logs, manifests, and stage results. `scripts/run_research_validation_pipeline.py` remains available for compatibility while the new wrapper stabilizes.

For current FX M15 h10 ML research guidance, use `long_tp_2atr_sl_1atr_hit_first_10` for long and `short_tp_2atr_sl_1atr_hit_first_10` for short when generating preferred ML rankings. `target_up_10`, `target_down_10`, `target_long_good_10`, and `target_short_good_10` remain benchmark/reference targets. XAUUSD remains a separate-review symbol until conservative recommended-threshold diagnostics improve. This guidance does not alter `run_full_research_pipeline.py` defaults or any backtest selection logic.

`scripts/run_full_research_pipeline.py --run-final-review` is a shortcut for `--run-random-baseline`, `--run-baseline-diagnostics`, and `--run-research-decision-report`. Final-review overwrites require `--overwrite-final-review`. Diagnostics default to 100 random runs in the full-pipeline orchestration because they can be slow; use the standalone diagnostics script with 250+ runs for heavier final review.

## Reading Order

For a normal research run, start with the final validation and scorecard reports, then inspect intermediate CSVs only when debugging a specific feature, symbol, direction, or cost assumption.

The pipeline remains offline and research-only at every step.

## Detailed Usage Reference

- [Manual calendar export](#manual-metatrader-5-export-step)
- [CSV/database workflow](#automated-repository-workflow)
- [Historical bar import](#historical-price-bars-from-metatrader-5)
- [Price features](#price-feature-generation), [market features](#market-feature-generation), and [dataset generation](#ml-dataset-generation)
- [Research command examples](#research-command-examples)
- [Troubleshooting](#common-errors)

[Back to README](../../README.md) | [Report interpretation](OUTPUTS_AND_REPORTS.md) | [Methodology](METHODOLOGY_GUARDRAILS.md)

Commands below run from the repository root and are examples, not a sequence to
execute blindly. They require local inputs absent from the public snapshot.
Terminal-connected acquisition is separate from offline testing. Install the
MetaTrader5 connector only in a separate environment for supervised acquisition.
No command here is a demo-trading launch procedure.

## Manual MetaTrader 5 Export Step

Economic-calendar acquisition requires a manual MT5 export. These instructions concern research data preparation, not demo execution.

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

Historical OHLCV import is read-only and uses the official MetaTrader 5 Python package. It initializes a terminal connection and retrieves bars with `copy_rates_range()`; symbol selection and connection shutdown are also part of the import workflow. It does not send orders and does not use order execution APIs.

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

## Research Command Examples

Descriptions, output inventories, and interpretation remain in the pipeline map
above and [Outputs And Reports](OUTPUTS_AND_REPORTS.md). Replace `RUN_ID`,
`GROUP_ID`, and other uppercase placeholders with local identifiers. Existing
outputs require explicit overwrite flags; use them only when regeneration is
intended. Gross and net comparisons, symbols, and directions remain separate.

The full research pipeline imports from MT5 unless `--skip-price-import` is set.
For offline research, use both `--skip-calendar-import` and `--skip-price-import`
and supply an existing local database and a verified cost config. Heavy research
execution is a separate user-run workflow, not part of the offline test suite.

### ML Research Reports

Run the default research analysis:

```powershell
python scripts/ml_research.py --symbol EURUSD --timeframe M15
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

Analyze one folder only:

```powershell
python scripts/analyze_research_reports.py --input-dir reports\ml_research\long\EURUSD_M15_h10
```

Build the preferred FX target feature-stability report after target-specific ML reports exist:

```powershell
python scripts/build_preferred_target_feature_stability.py
```

Build a preferred feature hypothesis shortlist from the stability report:

```powershell
python scripts/build_preferred_feature_hypothesis_shortlist.py
```

Run controlled preferred-feature backtests from the shortlist:

```powershell
python scripts/run_preferred_feature_backtests.py
```

Compare an existing gross/none preferred-feature run with an estimated/net run:

```powershell
python scripts/compare_preferred_feature_backtest_cost_modes.py --gross-run-id GROSS_RUN_ID --net-run-id NET_RUN_ID
```

Run small controlled preferred-feature combination backtests from the cost-mode comparison:

```powershell
python scripts/run_preferred_feature_combination_backtests.py --gross-run-id GROSS_RUN_ID --net-run-id NET_RUN_ID
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

### Backtest Research Reports

Run one exploratory backtest:

```powershell
python scripts/backtest_research.py --symbol EURUSD --timeframe M15 --target-horizon 10
```

Evaluate all symbol/timeframe/horizon backtest folders:

```powershell
python scripts/evaluate_backtest_results.py
```

Select robust research hypotheses:

```powershell
python scripts/select_research_hypotheses.py
```

### Combined Hypothesis Research

The minimal hypothesis discovery wrapper can plan the upstream chain that produces run-scoped combined outputs for validation:

```powershell
python scripts/run_hypothesis_discovery_pipeline.py --run-id RUN_ID --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-config config/cost_model.example.json --dry-run
```

Run one combined backtest:

```powershell
python scripts/backtest_combined_hypotheses.py --symbol EURUSD --timeframe M15 --target-horizon 10
```

Evaluate combined hypotheses across all combined result folders:

```powershell
python scripts/evaluate_combined_hypotheses.py
```

Use a fixed run ID when needed:

```powershell
python scripts/evaluate_combined_hypotheses.py --run-id RUN_ID
```

### Year-by-Year Combined Hypothesis Validation

Run validation for a known combined-evaluation run:

```powershell
python scripts/validate_hypotheses_by_year.py --run-id RUN_ID --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10
```

Or pass the selected combinations file directly:

```powershell
python scripts/validate_hypotheses_by_year.py --hypotheses-file reports\backtests\combined\evaluations\RUN_ID\long\selected_combined_hypotheses.csv --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long
```

Useful controls:

```powershell
python scripts/validate_hypotheses_by_year.py --run-id RUN_ID --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --start-year 2020 --end-year 2026 --min-trades-per-year 100 --min-positive-year-ratio 0.75 --min-positive-symbol-ratio 0.75
python scripts/validate_hypotheses_by_year.py --run-id RUN_ID --symbols EURUSD GBPUSD USDJPY XAUUSD --years 2022 2023 2024 2025
python scripts/validate_hypotheses_by_year.py --run-id RUN_ID --include-incomplete-years
```

### Random Baseline Robustness Tests

Run cross-pair final candidates for a known run:

```powershell
python scripts/run_random_baseline_tests.py --run-id RUN_ID --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-mode estimated --return-mode net --cost-config config/cost_model.example.json --strict-cost-config --overwrite
```

Include pair-specific candidates too:

```powershell
python scripts/run_random_baseline_tests.py --run-id RUN_ID --direction short --symbols EURUSD GBPUSD USDJPY XAUUSD --include-pair-specific --cost-mode estimated --return-mode net --cost-config config/cost_model.example.json --strict-cost-config --overwrite
```

### Candidate Baseline Diagnostics

Run long diagnostics:

```powershell
python scripts/run_candidate_baseline_diagnostics.py --run-id RUN_ID --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-mode estimated --return-mode net --strict-cost-config --cost-config config/cost_model.example.json --random-runs 250 --overwrite
```

Run short diagnostics:

```powershell
python scripts/run_candidate_baseline_diagnostics.py --run-id RUN_ID --direction short --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-mode estimated --return-mode net --strict-cost-config --cost-config config/cost_model.example.json --random-runs 250 --overwrite
```

### Research Decision Report

Build the report after validation and random baseline outputs exist:

```powershell
python scripts/build_research_decision_report.py --run-id RUN_ID --direction long --cost-mode estimated --return-mode net --overwrite
python scripts/build_research_decision_report.py --run-id RUN_ID --direction short --cost-mode estimated --return-mode net --overwrite
```

Run the clearer combined validation pipeline wrapper in dry-run mode before any manual execution:

```powershell
python scripts/run_combined_validation_pipeline.py --run-id RUN_ID --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-config config/cost_model.example.json --dry-run
```

`scripts/run_combined_validation_pipeline.py` writes a manifest, command plan, stage results, summary, warnings, and markdown report under `reports\combined_validation_pipeline\{RUN_ID}\`. Controlled execution requires explicit `--execute` and should be user-run only for heavy research outputs. The older `scripts/run_research_validation_pipeline.py` remains available as a compatibility runner:

```powershell
python scripts/run_research_validation_pipeline.py --run-id RUN_ID --direction long --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --cost-config config/cost_model.example.json
```

### Full Research Pipeline

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

Useful skip flags:

```powershell
python scripts/run_full_research_pipeline.py --cost-config config/cost_model.example.json --skip-checks
python scripts/run_full_research_pipeline.py --cost-config config/cost_model.example.json --continue-on-error
```

You can also rebuild only the scorecard for an existing run:

```powershell
python scripts/build_final_feature_scorecard.py --run-id RUN_ID --direction long --overwrite
```

### Horizon Consistency Report

Example:

```powershell
python scripts/build_horizon_consistency_report.py --group-id GROUP_ID --direction long --h5-run-id RUN_ID_H5 --h10-run-id RUN_ID_H10 --h20-run-id RUN_ID_H20 --cost-mode estimated --return-mode net --overwrite
```

### Walk-Forward Research Validation

Run it directly:

```powershell
python scripts/run_walk_forward_research.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --train-start-year 2020 --first-test-year 2022 --last-test-year 2025 --overwrite
python scripts/run_walk_forward_research.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction short --train-start-year 2020 --first-test-year 2022 --last-test-year 2025 --overwrite
```

By default, walk-forward searches combinations up to 2 conditions. Larger combinations are controlled by beam search instead of exhaustive brute force:

```powershell
python scripts/run_walk_forward_research.py --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --max-combination-size 5 --max-seed-conditions 12 --max-candidates-per-level 50 --overwrite
```

The full pipeline can optionally run walk-forward after the final scorecard:

```powershell
python scripts/run_full_research_pipeline.py --skip-calendar-import --skip-price-import --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction long --cost-config config/cost_model.example.json --start-year 2022 --end-year 2024 --overwrite-validation --run-walk-forward
python scripts/run_full_research_pipeline.py --skip-calendar-import --skip-price-import --symbols EURUSD GBPUSD USDJPY XAUUSD --timeframe M15 --target-horizon 10 --direction short --cost-config config/cost_model.example.json --start-year 2022 --end-year 2024 --overwrite-validation --run-walk-forward
```

### Overlapping Label Controls

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

## Common Errors

`CSV missing`: run the MQL5 script manually in MetaTrader 5 and copy `economic_calendar.csv` into `data\economic_calendar.csv`, or pass `--csv-source` with the path to the MT5 `MQL5\Files` CSV.

`Database missing`: run `python scripts/init_database.py`, or run `python scripts/run_pipeline.py` without `--import-only`.

`Empty CSV`: the importer exits gracefully with zero rows read, inserted, and skipped. Re-run the MT5 export if records were expected.

`Wrong delimiter`: the importer detects comma or semicolon automatically and falls back to comma. If the header still cannot be read, it prints the detected delimiter and columns.

`Missing required columns`: the importer prints the required columns, detected columns, detected delimiter, and a hint that the CSV header or delimiter may be wrong.

`Duplicate value_id rows`: duplicate rows are skipped non-destructively. Existing database rows are not deleted or overwritten.

`MetaTrader5 package missing`: install it with `python -m pip install MetaTrader5` in the same environment used to run the scripts.

`ML research dependencies missing`: install the offline dependency set listed in the [README](../../README.md#offline-testing) in the environment used for research. The full requirements file also includes the terminal connector.

`Symbol unavailable`: open MetaTrader 5, verify that the symbol exists in Market Watch, and retry. The importer attempts `mt5.symbol_select(symbol, True)` before failing.
