# Outputs And Reports

When modifying the pipeline, update this document if the change affects scripts, outputs, methodology, or next actions.

This document classifies generated artifacts so future research prompts can focus on the right files. Generated files under `data/`, `reports/`, and `logs/` are local artifacts and should not be committed unless a future policy explicitly says otherwise.

## Primary Reports To Read

After a complete research run, read these first:

- `reports/validation/by_year/{RUN_ID}/{DIRECTION}/final_research_candidates_report.md`
- `reports/validation/by_year/{RUN_ID}/{DIRECTION}/final_research_candidates.csv`
- `reports/validation/by_year/{RUN_ID}/{DIRECTION}/pair_specific_candidates_report.md`
- `reports/validation/by_year/{RUN_ID}/{DIRECTION}/pair_specific_candidates.csv`
- `reports/final_feature_scorecard/{RUN_ID}/{DIRECTION}/final_feature_scorecard_report.md`
- `reports/final_feature_scorecard/{RUN_ID}/{DIRECTION}/final_feature_scorecard.csv`
- `reports/final_feature_scorecard/{RUN_ID}/{DIRECTION}/pair_specific_feature_scorecard.csv`

If the hypothesis discovery pipeline wrapper was used in dry-run or controlled execution mode, read the wrapper artifacts first:

- `reports/hypothesis_discovery_pipeline/{RUN_ID}/hypothesis_discovery_manifest.json`
- `reports/hypothesis_discovery_pipeline/{RUN_ID}/hypothesis_discovery_command_plan.csv`
- `reports/hypothesis_discovery_pipeline/{RUN_ID}/hypothesis_discovery_stage_results.csv`
- `reports/hypothesis_discovery_pipeline/{RUN_ID}/hypothesis_discovery_summary.csv`
- `reports/hypothesis_discovery_pipeline/{RUN_ID}/hypothesis_discovery_report.md`
- `reports/hypothesis_discovery_pipeline/{RUN_ID}/hypothesis_discovery_warnings.csv`

The hypothesis discovery wrapper plans or runs the exploratory upstream chain that prepares run-scoped combined outputs under `reports/backtests/combined/runs/{RUN_ID}/{DIRECTION}/`. Its outputs are discovery inputs for combined validation, not validated strategy evidence. Codex should use help/tests/dry-run only; real execution is user-run because it may invoke combined backtests.

If the combined validation pipeline wrapper was used in dry-run or controlled execution mode, read the wrapper artifacts first:

- `reports/combined_validation_pipeline/{RUN_ID}/combined_validation_manifest.json`
- `reports/combined_validation_pipeline/{RUN_ID}/combined_validation_command_plan.csv`
- `reports/combined_validation_pipeline/{RUN_ID}/combined_validation_stage_results.csv`
- `reports/combined_validation_pipeline/{RUN_ID}/combined_validation_summary.csv`
- `reports/combined_validation_pipeline/{RUN_ID}/combined_validation_report.md`
- `reports/combined_validation_pipeline/{RUN_ID}/combined_validation_warnings.csv`

Dry-run mode plans commands only. Controlled execution requires explicit `--execute`, runs existing validation child scripts through the shared runner, and writes logs under the run folder. `scripts/run_research_validation_pipeline.py` remains available as the compatibility runner. Codex should use help/tests/dry-run only; real execution is user-run because it may invoke heavy validation stages.

If walk-forward was run, also read:

- `reports/walk_forward/{RUN_ID}/{DIRECTION}/walk_forward_report.md`
- `reports/walk_forward/{RUN_ID}/{DIRECTION}/walk_forward_candidates.csv`
- `reports/walk_forward/{RUN_ID}/{DIRECTION}/pair_specific_walk_forward_report.md`
- `reports/walk_forward/{RUN_ID}/{DIRECTION}/pair_specific_walk_forward_candidates.csv`

If random baseline robustness was run, also read:

- `reports/random_baseline/{RUN_ID}/{DIRECTION}/random_baseline_report.md`
- `reports/random_baseline/{RUN_ID}/{DIRECTION}/random_baseline_summary.csv`
- `reports/random_baseline/{RUN_ID}/{DIRECTION}/skipped_random_baseline_candidates.csv`

If candidate baseline diagnostics were run, also read:

- `reports/baseline_diagnostics/{RUN_ID}/{DIRECTION}/baseline_diagnostics_report.md`
- `reports/baseline_diagnostics/{RUN_ID}/{DIRECTION}/baseline_diagnostics_summary.csv`
- `reports/baseline_diagnostics/{RUN_ID}/{DIRECTION}/skipped_baseline_diagnostics_candidates.csv`

If horizon consistency was run across h5/h10/h20 runs, also read:

- `reports/horizon_consistency/{GROUP_ID}/{DIRECTION}/horizon_consistency_report.md`
- `reports/horizon_consistency/{GROUP_ID}/{DIRECTION}/horizon_consistency_summary.csv`
- `reports/horizon_consistency/{GROUP_ID}/{DIRECTION}/horizon_consistency_warnings.csv`

If the research decision report was built, read it first for final research-only triage:

- `reports/research_decision/{RUN_ID}/{DIRECTION}/research_decision_report.md`
- `reports/research_decision/{RUN_ID}/{DIRECTION}/research_decision_summary.csv`
- `reports/research_decision/{RUN_ID}/{DIRECTION}/research_decision_warnings.csv`

If a research branch outcome report was built, read it as the closure record for a rejected branch:

- `reports/research_branch_outcomes/{RUN_ID}/branch_outcome_report.md`
- `reports/research_branch_outcomes/{RUN_ID}/branch_outcome_summary.csv`
- `reports/research_branch_outcomes/{RUN_ID}/rejected_combinations.csv`

If a preferred horizon/cost diagnostic matrix was planned or run, read:

- `reports/preferred_horizon_cost_diagnostics/{RUN_ID}/matrix_report.md`
- `reports/preferred_horizon_cost_diagnostics/{RUN_ID}/matrix_summary.csv`
- `reports/preferred_horizon_cost_diagnostics/{RUN_ID}/skipped_branches.csv`
- `reports/preferred_horizon_cost_diagnostics/{RUN_ID}/branch_manifest.json`
- `reports/preferred_horizon_cost_diagnostics/{RUN_ID}/zero_tested_diagnostics.md` when `NO_TESTED_COMBINATIONS` branches need root-cause inspection
- `reports/preferred_horizon_cost_diagnostics/{RUN_ID}/zero_tested_diagnostics.csv` when per-direction zero-tested counts are needed

If preferred horizon prerequisites were diagnosed, read:

- `reports/preferred_horizon_prerequisites/{RUN_ID}/prerequisite_diagnostics.md`
- `reports/preferred_horizon_prerequisites/{RUN_ID}/prerequisite_diagnostics.csv`

If preferred horizon shortlist inputs were built, read:

- `reports/ml_research/preferred_horizon_shortlist_builds/{RUN_ID}/preferred_horizon_shortlist_report.md`
- `reports/ml_research/preferred_horizon_shortlist_builds/{RUN_ID}/preferred_horizon_shortlist_manifest.csv`
- The matching preferred-target stability and preferred feature hypothesis files listed in the manifest.

If historical spread calibration was run, read:

- `reports/cost_model/historical_spreads/{RUN_ID}/spread_audit_report.md`
- `reports/cost_model/historical_spreads/{RUN_ID}/spread_by_symbol.csv`
- `reports/cost_model/historical_spreads/{RUN_ID}/spread_config_candidates.csv`

If MT5 recent spread comparison was run, read:

- `reports/cost_model/mt5_spread_comparison/{RUN_ID}/spread_comparison_report.md`
- `reports/cost_model/mt5_spread_comparison/{RUN_ID}/spread_comparison.csv`
- `reports/cost_model/mt5_spread_comparison/{RUN_ID}/mt5_recent_spread_by_symbol.csv`

If preferred-target feature stability was built, read:

- `reports/ml_research/preferred_target_feature_stability/{DIRECTION}/{TIMEFRAME}_h{H}/feature_stability_report.md`
- `reports/ml_research/preferred_target_feature_stability/{DIRECTION}/{TIMEFRAME}_h{H}/feature_stability.csv`

If preferred feature hypotheses were shortlisted, read:

- `reports/ml_research/preferred_feature_hypotheses/{DIRECTION}/{TIMEFRAME}_h{H}/preferred_feature_hypotheses_report.md`
- `reports/ml_research/preferred_feature_hypotheses/{DIRECTION}/{TIMEFRAME}_h{H}/preferred_feature_hypotheses.csv`

If preferred feature backtests were run, read:

- `reports/preferred_feature_backtests/{RUN_ID}/{DIRECTION}/preferred_feature_backtest_report.md`
- `reports/preferred_feature_backtests/{RUN_ID}/{DIRECTION}/preferred_feature_backtest_summary.csv`
- `reports/preferred_feature_backtests/{RUN_ID}/{DIRECTION}/preferred_feature_backtest_detail.csv`
- `reports/preferred_feature_backtests/{RUN_ID}/{DIRECTION}/skipped_features.csv`

If preferred feature cost modes were compared, read:

- `reports/preferred_feature_backtests/cost_mode_comparison/{GROSS_RUN_ID}_vs_{NET_RUN_ID}/{DIRECTION}/cost_mode_comparison_report.md`
- `reports/preferred_feature_backtests/cost_mode_comparison/{GROSS_RUN_ID}_vs_{NET_RUN_ID}/{DIRECTION}/cost_mode_comparison.csv`

If controlled preferred feature combinations were run, read:

- `reports/preferred_feature_combination_backtests/{RUN_ID}/{DIRECTION}/combination_backtest_report.md`
- `reports/preferred_feature_combination_backtests/{RUN_ID}/{DIRECTION}/combination_backtest_summary.csv`
- `reports/preferred_feature_combination_backtests/{RUN_ID}/{DIRECTION}/combination_backtest_detail.csv`
- `reports/preferred_feature_combination_backtests/{RUN_ID}/{DIRECTION}/skipped_combinations.csv`
- `reports/preferred_feature_combination_backtests/{RUN_ID}/{DIRECTION}/candidate_diagnostics.csv`

If a fixed TP/SL path-exit diagnostic was run, read:

- `reports/tp_sl_path_backtests/{RUN_ID}/{DIRECTION}/tp_sl_path_backtest_report.md`
- `reports/tp_sl_path_backtests/{RUN_ID}/{DIRECTION}/tp_sl_path_backtest_summary.csv`
- `reports/tp_sl_path_backtests/{RUN_ID}/{DIRECTION}/tp_sl_path_backtest_detail.csv`
- `reports/tp_sl_path_backtests/{RUN_ID}/{DIRECTION}/skipped_tp_sl_path_rows.csv`

Batch TP/SL diagnostics can read an existing preferred-feature `combination_backtest_detail.csv` through `--combination-input-csv`. In that mode, detail and summary rows are candidate-level rows copied from the existing combinations, include source-combination metadata, and do not represent newly generated pairs.

If the fixed-candidate audit chain was run, read the chain in order:

- `reports/regime_candidate_review/{RUN_ID}/candidate_review_report.md`
- `reports/regime_candidate_review/{RUN_ID}/candidate_review_summary.csv`
- `reports/regime_candidate_review/{RUN_ID}/candidate_review_warnings.csv`
- `reports/rule_based_regime_candidate_backtests/{RUN_ID}/rule_based_backtest_report.md`
- `reports/rule_based_regime_candidate_backtests/{RUN_ID}/rule_based_backtest_summary.csv`
- `reports/rule_based_regime_candidate_review/{RUN_ID}/rule_based_review_report.md`
- `reports/rule_based_regime_candidate_review/{RUN_ID}/rule_based_review_summary.csv`
- `reports/controlled_rule_research_expansion/{RUN_ID}/controlled_rule_expansion_report.md`
- `reports/controlled_rule_research_expansion/{RUN_ID}/controlled_rule_expansion_summary.csv`
- `reports/timeout_fragility_audit/{RUN_ID}/timeout_fragility_audit_report.md`
- `reports/timeout_root_cause_review/{RUN_ID}/timeout_root_cause_report.md`
- `reports/timeout_sequence_drilldown_review/{RUN_ID}/timeout_sequence_drilldown_report.md`
- `reports/timeout_policy_sensitivity_review/{RUN_ID}/timeout_policy_sensitivity_report.md`
- `reports/rule_candidate_gate_decisions/{RUN_ID}/rule_candidate_gate_decision_report.md`

If the fixed-candidate audit pipeline wrapper was used in dry-run or controlled execution mode, read the run artifacts first:

- `reports/candidate_audit_pipeline/{RUN_ID}/candidate_audit_manifest.json`
- `reports/candidate_audit_pipeline/{RUN_ID}/candidate_audit_command_plan.csv`
- `reports/candidate_audit_pipeline/{RUN_ID}/candidate_audit_stage_results.csv`
- `reports/candidate_audit_pipeline/{RUN_ID}/candidate_audit_pipeline_summary.csv`
- `reports/candidate_audit_pipeline/{RUN_ID}/candidate_audit_pipeline_report.md`
- `reports/candidate_audit_pipeline/{RUN_ID}/candidate_audit_pipeline_warnings.csv`

Dry-run mode plans commands only. Controlled execution mode requires explicit `--execute`, runs existing child scripts through the shared runner, writes logs under the run folder, and uses stage-summary gating to stop on failures, blocking warnings, or rejection labels by default. Codex should use help/tests/dry-run only; real `--execute` runs are user-run because they may invoke heavy child stages.

Candidate-audit outputs are offline research diagnostics only. They are not live signals, not broker-execution instructions, and not live-readiness reports. Summary CSVs expose common fields such as `candidate_id`, `decision_scope`, `final_classification`, warning counts, and `next_action` while preserving stage-specific labels. Warning CSVs expose `warning_code`, `severity`, `blocking`, `message`, `related_stage`, `related_metric`, `metric_value`, and `threshold`. Next-action CSVs expose `action_type`, `status`, `message`, and `forbidden_actions` where applicable.

Timeout-excluded diagnostics are biased and must not be read as validated performance. Extended h20/h40/h80 timeout diagnostics are sensitivity-only checks for existing h10 timeout entries, not replacement rules. `TIMEOUT_POLICY_SENSITIVITY_REJECTED` rejects alternative timeout policies, not necessarily the original h10 candidate if the original h10 stress metrics remain strong. A gate decision may allow limited offline baseline/cost-sensitivity review only with the original h10 timeout rule and an unresolved timeout caveat.

## Intermediate CSV

Most CSV files are intermediate research artifacts. They are useful for debugging and traceability, but they are not meant to be read manually one by one after every run.

Examples include:

- `reports/ml_research/.../correlations.csv`
- `reports/ml_research/.../mutual_information.csv`
- `reports/ml_research/.../random_forest_importance.csv`
- `reports/ml_research/.../permutation_importance.csv`
- `reports/ml_research/.../model_metrics.csv`
- `reports/ml_research/.../threshold_analysis.csv`
- `reports/ml_research/.../feature_summary.csv`
- `reports/ml_research/.../summary_feature_ranking.csv`
- `reports/ml_research/.../aggregate_feature_ranking.csv`
- `reports/ml_research/target_runs/{DIRECTION}/{SYMBOL}_{TIMEFRAME}_h{H}/{TARGET}/*.csv`
- `reports/ml_research/target_comparison/{DIRECTION}/{SYMBOL}_{TIMEFRAME}_h{H}/target_comparison.csv`
- `reports/ml_research/target_comparison/{DIRECTION}/{SYMBOL}_{TIMEFRAME}_h{H}/target_comparison_report.md`
- `reports/ml_research/preferred_target_feature_stability/{DIRECTION}/{TIMEFRAME}_h{H}/feature_stability.csv`
- `reports/ml_research/preferred_target_feature_stability/{DIRECTION}/{TIMEFRAME}_h{H}/feature_stability_report.md`
- `reports/ml_research/preferred_feature_hypotheses/{DIRECTION}/{TIMEFRAME}_h{H}/preferred_feature_hypotheses.csv`
- `reports/ml_research/preferred_feature_hypotheses/{DIRECTION}/{TIMEFRAME}_h{H}/preferred_feature_hypotheses_report.md`
- `reports/preferred_feature_backtests/{RUN_ID}/{DIRECTION}/preferred_feature_backtest_summary.csv`
- `reports/preferred_feature_backtests/{RUN_ID}/{DIRECTION}/preferred_feature_backtest_detail.csv`
- `reports/preferred_feature_backtests/{RUN_ID}/{DIRECTION}/skipped_features.csv`
- `reports/preferred_feature_backtests/{RUN_ID}/{DIRECTION}/cost_comparison.csv`
- `reports/preferred_feature_backtests/cost_mode_comparison/{GROSS_RUN_ID}_vs_{NET_RUN_ID}/{DIRECTION}/cost_mode_comparison.csv`
- `reports/preferred_feature_backtests/cost_mode_comparison/{GROSS_RUN_ID}_vs_{NET_RUN_ID}/{DIRECTION}/cost_mode_comparison_report.md`
- `reports/preferred_feature_combination_backtests/{RUN_ID}/{DIRECTION}/combination_backtest_summary.csv`
- `reports/preferred_feature_combination_backtests/{RUN_ID}/{DIRECTION}/combination_backtest_detail.csv`
- `reports/preferred_feature_combination_backtests/{RUN_ID}/{DIRECTION}/skipped_combinations.csv`
- `reports/preferred_feature_combination_backtests/{RUN_ID}/{DIRECTION}/candidate_diagnostics.csv`
- `reports/tp_sl_path_backtests/{RUN_ID}/{DIRECTION}/tp_sl_path_backtest_summary.csv`
- `reports/tp_sl_path_backtests/{RUN_ID}/{DIRECTION}/tp_sl_path_backtest_detail.csv`
- `reports/tp_sl_path_backtests/{RUN_ID}/{DIRECTION}/skipped_tp_sl_path_rows.csv`
- `reports/backtests/.../*.csv`
- `reports/backtests/combined/.../*.csv`
- `reports/backtests/combined/evaluations/{RUN_ID}/{DIRECTION}/*.csv`
- `reports/cost_model/historical_spreads/{RUN_ID}/*.csv`
- `reports/cost_model/mt5_spread_comparison/{RUN_ID}/*.csv`
- `reports/validation/by_year/{RUN_ID}/{DIRECTION}/by_year_validation_detail.csv`
- `reports/validation/by_year/{RUN_ID}/{DIRECTION}/by_year_validation_summary.csv`
- `reports/validation/by_year/{RUN_ID}/{DIRECTION}/skipped_hypotheses.csv`
- `reports/random_baseline/{RUN_ID}/{DIRECTION}/random_baseline_detail.csv`
- `reports/baseline_diagnostics/{RUN_ID}/{DIRECTION}/baseline_diagnostics_detail.csv`
- `reports/horizon_consistency/{GROUP_ID}/{DIRECTION}/horizon_consistency_warnings.csv`
- `reports/research_decision/{RUN_ID}/{DIRECTION}/research_decision_warnings.csv`
- `reports/research_branch_outcomes/{RUN_ID}/branch_outcome_summary.csv`
- `reports/research_branch_outcomes/{RUN_ID}/rejected_combinations.csv`
- `reports/preferred_horizon_cost_diagnostics/{RUN_ID}/matrix_summary.csv`
- `reports/preferred_horizon_cost_diagnostics/{RUN_ID}/skipped_branches.csv`
- `reports/walk_forward/{RUN_ID}/{DIRECTION}/walk_forward_detail.csv`
- `reports/walk_forward/{RUN_ID}/{DIRECTION}/walk_forward_summary.csv`

## Debug And Diagnostic Files

Diagnostic output usually comes from checker scripts or detailed intermediate reports.

Use these when a run looks wrong, a feature is missing, or a dataset may not contain expected rows:

- `scripts/check_database.py`
- `scripts/check_price_bars.py`
- `scripts/check_price_features.py`
- `scripts/check_market_features.py`
- `scripts/check_ml_dataset.py`
- `scripts/check_ml_research_outputs.py`
- Detailed validation and walk-forward CSVs under the matching `RUN_ID` and `DIRECTION`.

`check_price_features.py` includes diagnostics for ATR/range, volatility context, and unit-consistent spread columns when present. `check_ml_dataset.py` includes diagnostics for close-to-close future returns, future max/min/range labels, MFE/MAE labels, long/short good-path targets, and h5/h10/h20 triple-barrier research labels. These dataset labels are supervised research targets only and should not be interpreted as generated signals.

`threshold_analysis.csv` is an ML diagnostic report. It compares fixed probability thresholds on the held-out test set, including base-rate lift plus raw and direction-aware return-target summaries for predicted positives. For short research, raw `future_return_{H}` is sign-flipped in directional-return columns, so negative raw returns become favorable directional returns. This file should be used to understand threshold sensitivity only; it is not a trading signal file and does not change the default model threshold.

`scripts/compare_ml_target_reports.py` compares multiple target-specific ML research folders without overwriting the standard `reports/ml_research/{DIRECTION}/{SYMBOL}_{TIMEFRAME}_h{H}/` output. With `--run-ml-research`, target-specific reports go under `reports/ml_research/target_runs/...`; comparison summaries go under `reports/ml_research/target_comparison/...`. `recommended_research_threshold` is diagnostic only and must not be interpreted as a trading signal.

For current FX M15 h10 ML report comparisons, the preferred research targets are `long_tp_2atr_sl_1atr_hit_first_10` for long and `short_tp_2atr_sl_1atr_hit_first_10` for short. The older directional and good-path targets remain benchmark/reference reports. XAUUSD target-comparison outputs should be read separately until stronger threshold diagnostics appear.

`scripts/build_preferred_target_feature_stability.py` reads preferred target-run reports for EURUSD, GBPUSD, and USDJPY by default and summarizes recurring top-N features by direction. The stability score is a simple recurrence diagnostic across symbols and metric families; it is for hypothesis discovery only and does not establish strategy validity. Permutation importance can be noisy, so read the transparent counts and average ranks alongside the score.

`scripts/build_preferred_feature_hypothesis_shortlist.py` reads preferred feature stability outputs and creates a filtered feature shortlist with family, role, normalized/raw status, recommended usage, and caution fields. It is meant to guide controlled research tests only. Raw or scale-dependent features are flagged for caution rather than removed, and normalized/contextual variants should generally be preferred when available.

`scripts/run_preferred_feature_backtests.py` reads preferred feature shortlists and runs the existing single-feature bucket backtest workflow for prioritized normalized/contextual features. Outputs are run-scoped under `reports/preferred_feature_backtests/{RUN_ID}/{DIRECTION}/` and include per-symbol plus aggregate summaries. Summary/detail rows include condition, bucket, scenario source, baseline metrics, deltas versus baseline, and return/cost mode. Zero-trade or unavailable conditions are separated into `skipped_features.csv`. XAUUSD is not included by default. The report is exploratory; feature filters are not trading signals and do not establish strategy validity. `scenario_source` distinguishes preferred shortlist features from standard/default backtest context. Use `--strict-shortlist-only` when only shortlist features should remain in the output.

`scripts/compare_preferred_feature_backtest_cost_modes.py` compares an existing gross/none preferred-feature run with an estimated/net run. It preserves `scenario_source`, `feature_in_shortlist`, `is_preferred_shortlist_feature`, and `feature_family` when those fields exist in the matched summaries, and the markdown report includes source-tag diagnostics before the candidate sections. Gross/none is diagnostic context only. A row with `cost_erased_edge=true` had positive gross criteria but did not survive estimated-net review, so it should not be treated as a survivor.

`scripts/run_preferred_feature_combination_backtests.py` reads preferred-shortlist cost-mode comparison rows and tests a small controlled set of two-filter combinations. It pairs momentum/returns or trend/MA candidates with volume/liquidity, volatility/range, or spread/liquidity candidates, keeps symbols and directions separate, and excludes XAUUSD unless it is explicitly requested. Zero-trade or unsupported combinations are written to `skipped_combinations.csv`. `candidate_diagnostics.csv` and the markdown candidate diagnostics section count rows through source loading, symbol filtering, gross filtering, net/cost-erased filtering, shortlist/source filtering, pairing, evaluation, result, and skipped stages. These rows remain exploratory research filters; net survivors still need broader validation, concentration review, and separate follow-up before any later rule-based research design.

`scripts/run_tp_sl_path_backtests.py` can now batch-evaluate those existing combination detail rows with fixed TP/SL path-exit assumptions. The batch input is not a new feature search: each tested row comes from the source CSV, malformed rows are written to `skipped_tp_sl_path_rows.csv`, and source close-to-close metrics are copied into `source_close_to_close_*` columns when available.

`scripts/build_research_branch_outcome_report.py` records the outcome of a branch after diagnostic evidence has already been generated. It reads TP/SL path summary/detail CSVs, writes a branch-level closure report, and lists rejected combinations with reasons such as non-positive mean R, profit factor at or below 1, baseline not beaten, or concentration warnings. It does not rerun diagnostics or search for alternatives.

`scripts/run_preferred_horizon_cost_diagnostics.py` builds a controlled matrix across h5/h10/h20 horizons, p50/p75/p90 local cost configs, the FX group, and a separate XAUUSD group. Use `--dry-run` first to inspect branch IDs, commands, and planned output paths. The orchestrator calls existing scripts when not in dry-run mode and does not add new feature engineering, TP/SL optimization, or a new backtester.

Matrix branch decisions include `CANDIDATES_FOUND`, `NEEDS_REVIEW`, `CLOSED_NO_SURVIVOR`, and `NO_TESTED_COMBINATIONS`. A zero-tested branch means no TP/SL path rows were evaluated and must not be interpreted as `DA_APPROFONDIRE`; read the branch notes and skipped-branch diagnostics to understand whether combination inputs were empty, missing, or produced no path detail rows.

Use `--summarize-existing-run-id RUN_ID` when only `matrix_summary.csv`, `matrix_report.md`, and a missing `skipped_branches.csv` need to be rebuilt from an existing matrix run. This mode does not rerun child scripts or change research results.

Use `--diagnose-zero-tested-run-id RUN_ID` to build `zero_tested_diagnostics.csv` and `zero_tested_diagnostics.md` from existing child outputs. This mode counts upstream preferred-feature, cost-comparison, combination, TP/SL input, and skipped rows per branch and direction, then assigns a `zero_tested_reason` such as `no_preferred_backtest_rows`, `no_preferred_shortlist_rows`, `empty_combination_detail_csv`, or `missing_child_output`. It does not rerun backtests, call child scripts, search combinations, or change research results.

Use `scripts/diagnose_preferred_horizon_prerequisites.py` when zero-tested matrix diagnostics show `no_preferred_backtest_rows`. It checks whether the corresponding preferred target columns exist in `ml_dataset`, whether target labels have usable non-null and class-balance counts, whether the preferred feature hypothesis shortlist exists, and whether shortlist features remain available after the same safety filters used by preferred-feature backtests. It does not generate missing labels or shortlists.

Use `scripts/build_preferred_horizon_shortlists.py` when target columns exist but preferred shortlist inputs are missing for h5/h20. It reuses target-specific ML research reports, preferred-target feature stability, and preferred feature hypothesis shortlist generation. It does not run preferred-feature backtests, build combinations, or change TP/SL assumptions.

## Logs

Full pipeline logs are written under:

- `logs/full_pipeline_{RUN_ID}.log`

Logs are local run artifacts. They are useful for debugging command order and failures, but they are not research conclusions and should not be committed.

## Deprecated Or Stale Outputs To Avoid

Do not rely on:

- Reports from old `RUN_ID` folders when a newer run was generated with different scripts, direction, cost mode, symbols, or years.
- Mixed or legacy output folders that are not under the current direction-specific path.
- Gross reports when the current question is about net performance.
- Long reports when the current question is about short performance.
- Pair-specific reports when the current question is cross-pair robustness.
- Exploratory backtest outputs as if they were final validated candidates.
- Any generated CSV, DB, report, or log that is not tied to the run being analyzed.

## What To Read After A Full Run

1. Confirm the `RUN_ID`, `DIRECTION`, `return_mode`, `cost_mode`, symbols, timeframe, horizon, and validation years.
2. If available, read the research decision report for final research-only triage.
3. Read the yearly validation final candidate report.
4. Read the pair-specific candidate report for symbol-only leads.
5. Read the final feature scorecard report.
6. If enabled, read random baseline robustness, baseline diagnostics, horizon consistency, and walk-forward cross-pair and pair-specific reports.
7. Open intermediate CSVs only to investigate a specific metric, feature, symbol, year, or warning.

`scripts/run_full_research_pipeline.py` can optionally create the random baseline, baseline diagnostics, and research decision outputs with `--run-final-review`, or with the individual `--run-random-baseline`, `--run-baseline-diagnostics`, and `--run-research-decision-report` flags. Those outputs are not regenerated unless `--overwrite-final-review` is passed.

## Cross-Pair Vs Pair-Specific

Cross-pair outputs look for evidence that holds across several symbols. They are better for identifying general features and filters.

Pair-specific outputs look for evidence on one symbol. They can be useful for follow-up rule-based backtests, but they should not be generalized to other symbols without separate validation.

## Long Vs Short

Long and short research are separate.

- Long uses upward targets and positive future returns.
- Short uses downward targets and direction-aware returns equal to `-future_return_{H}`.

Do not merge long and short results when reading final candidates, scorecards, or walk-forward outputs.

## Gross Vs Net

Gross returns ignore estimated execution costs.

Net returns subtract estimated costs for spread, slippage, and commission. Net results are more realistic but depend on cost configuration quality and broker-specific point sizes.

Cost-aware research outputs now default to estimated/net mode. Use `--cost-mode none --return-mode gross` explicitly when a gross comparison is needed.

See `docs/research/COST_MODEL.md` before interpreting estimated-net results or adding local broker-specific configs.

Pepperstone example configs are available under `config/brokers/*.example.json`; use ignored local copies such as `config/brokers/pepperstone_razor.local.json` for broker/account-specific research runs.

When comparing reports, make sure gross reports are compared with gross reports and net reports are compared with net reports.

Estimated net returns are offline estimates, not real execution simulation. Existing report folders are not regenerated unless the relevant `--overwrite` or `--overwrite-validation` flag is passed explicitly.

## Yearly Validation Vs Walk-Forward

Yearly validation asks whether selected hypotheses are stable by symbol and by year.

Walk-forward validation asks whether candidates selected using past train years still work on future out-of-sample test years.

Walk-forward is stricter and should be preferred when deciding which research leads deserve a dedicated rule-based backtest.

## Random Baseline Robustness

Random baseline robustness asks whether final candidates beat random same-trade-count samples from the same universe. It is a post-validation diagnostic, not a candidate discovery tool.

Cross-pair random baselines sample from the requested multi-symbol universe. Pair-specific random baselines sample only from the candidate symbol. Long and short, gross and net, and cross-pair and pair-specific outputs remain separate.

## Candidate Baseline Diagnostics

Candidate baseline diagnostics ask whether a final candidate adds value beyond its context. For example, `Monday AND Asia` is compared with all candles, `Monday` only, `Asia` only, leave-one-out filters, random same-trade-count samples, and conditional random samples inside each single-filter universe.

This is not candidate discovery and not strategy generation. It tests only already-final candidates and classifies them as `adds_incremental_value`, `mostly_single_filter_effect`, `not_better_than_context`, or `low_sample`.

Cross-pair diagnostics use the requested multi-symbol universe. Pair-specific diagnostics use only the candidate symbol. Long and short, gross and net, and cross-pair and pair-specific outputs remain separate.

Diagnostics can be slow. The full-pipeline final-review orchestration defaults to 100 diagnostic random runs; use the standalone diagnostics script with 250 or more random runs when a heavier final review is needed.

## Horizon Consistency

Horizon consistency compares final feature scorecards across h5, h10, and h20. It asks whether a feature or condition behaves coherently across nearby target horizons.

It does not rerun backtests, search for new strategies, create signals, or make buy/sell recommendations. It only summarizes already-produced scorecard evidence into labels such as `consistent_across_horizons`, `consistent_medium_slow`, `short_horizon_only`, `long_horizon_only`, `unstable_across_horizons`, and `insufficient_evidence`.

Cross-pair and pair-specific rows remain separate. Long and short, gross and net, and each horizon's run ID must also remain separate.

## Research Decision Report

The research decision report summarizes final validation, random baseline, skipped-candidate, optional scorecard, and optional walk-forward outputs into `SCARTARE`, `DA_APPROFONDIRE`, and `CANDIDATA_A_TEST_SUCCESSIVI`.

It is still research-only. `CANDIDATA_A_TEST_SUCCESSIVI` means only that a candidate may deserve a future rule-based research backtest; it is not live-ready and is not a buy/sell recommendation.

## Future Trader-Facing Report

A single trader-facing report should be implemented only after runs are stable and metrics are consolidated across long, short, gross, net, yearly validation, random baseline, baseline diagnostics, horizon consistency, and walk-forward validation.

That future report should summarize decisions for a human researcher. It should not be added yet, because the current project still needs stable net walk-forward evidence and further research-only backtests before a trader-facing layer would be reliable.
