# Next Actions

When modifying the pipeline, update this document if the change affects scripts, outputs, methodology, or next actions.

This file is a planning reference for future Codex or ChatGPT prompts. It should track research priorities without turning the project into a live trading system.

## Now

- For the fixed GBPUSD M15 h10 Off_hours spread15 candidate, do not add another request-construction shadow plan or an extra pilot-authorization artifact now. The existing gated chain is sufficient for the current stage.
- Continue fixed-candidate monitoring until a fresh live-data non-fixture `shadow_signal_detected` / `would_signal` chain appears. Then run and review the complete gated chain; real `order_check` and `order_send` remain blocked until every required non-fixture gate passes and all critical upstream artifacts are within the configured max-age window.
- Keep fixture and dry-run modes available for engineering validation.
- Keep the shared artifact freshness guard in `scripts/_fixed_candidate_artifact_freshness.py` active across manual approval creation, request construction dry-run, order-check, and order-send pilot stages. Each patched stage should continue writing `artifact_freshness_checks.csv` and manifest fields `artifact_freshness_policy_applied`, `stale_artifact_count`, `blocking_stale_artifact_count`, and `max_artifact_age_minutes`.
- Treat `config/fixed_candidate_demo_execution_policy.json` as the only current risk source for any future approval, request construction, `order_check`, or demo `order_send` path. The current cap is 0.5% / 5 EUR on intended 1000 EUR demo equity, account currency EUR, with max open positions 1, 50% margin warning, and 70% margin hard cap. Older `1%` references are legacy/paper-only or test fixtures unless explicitly re-reviewed.
- Treat `config/fixed_candidate_current_canonical.json` as pointing to the validated frozen train-only numeric-tercile threshold artifact: `reports/fixed_candidate_train_only_numeric_tercile_thresholds/gbpusd_short_h10_1_5_off_hours_train_only_numeric_tercile_thresholds_train_to_2024_12_31_v1/fixed_candidate_train_only_numeric_tercile_thresholds.json`. The artifact has `train_end_time=2024-12-31 23:59:59`; the old full-sample threshold artifact is historical only.
- Current fixed-candidate evidence is now based on train-only threshold validation. The 2025-2026 OOS position-aware replay passed with `max_open_positions=1` and verdict `position_aware_degrades_but_positive`; this supports resuming the real demo chain only when a fresh non-fixture signal appears and every existing gate passes.
- Only later consider extending `scripts/build_fixed_candidate_demo_order_request_shadow_design.py` to consume the newer future request construction readiness artifact if a concrete gap remains after live-data non-fixture evidence exists.
- Treat clean research runs as estimated/net by default; use `--cost-mode none --return-mode gross` only for explicit comparison runs.
- For FX M15 h10 ML ranking, use `long_tp_2atr_sl_1atr_hit_first_10` for long and `short_tp_2atr_sl_1atr_hit_first_10` for short as the preferred research targets.
- Build preferred-target feature stability reports after target-specific FX ML reports exist.
- Build preferred feature hypothesis shortlists from stability reports, then run controlled preferred-feature backtest summaries with `scripts/run_preferred_feature_backtests.py`.
- Compare gross/none and estimated/net preferred feature runs, then use `scripts/run_preferred_feature_combination_backtests.py` for small controlled two-filter follow-ups when single-filter rows are cost-erased.
- For weak close-to-close preferred-combination survivors, use `scripts/run_tp_sl_path_backtests.py` as a fixed TP/SL path-exit diagnostic before considering broader validation. Use `--combination-input-csv` only to sweep already-generated preferred-feature combination rows; do not treat it as a new search or TP/SL optimization.
- Run a clean long/short net pipeline.
- Run random baseline robustness tests for clean long/short net candidates.
- Run candidate baseline diagnostics for clean long/short net candidates.
- Use `scripts/run_full_research_pipeline.py --run-final-review` when a single run should also produce random baseline, baseline diagnostics, and the research decision report.
- Run horizon consistency after matching h5/h10/h20 scorecards exist.
- Build research decision reports for clean long/short net runs.

### Controlled Demo-Pilot Override Decision

- The project intentionally accepts `--allow-real-order-check` and `--allow-real-order-send` as explicit operational demo-pilot overrides.
- The flags may be supplied manually by an operator or automatically by a future controlled one-shot orchestrator.
- A flag alone is never enough. Each flag is a necessary execution-stage gate, not a bypass.
- Before real demo-account `order_check`, require a fresh signal chain, valid approval record, non-fixture request-construction dry-run, available order-check readiness, clean broker/local reconciliation, safe margin and spread, passing duplicate protection, inactive kill switch, a demo EUR account, and an available symbol contract.
- Before the real demo-account `order_send` pilot, require every order-check gate plus `order_check_available_passed_no_send`, `order_send_pilot_readiness_plan_available_no_send`, final confirmation `confirm_single_demo_send_only`, an atomic `pre_send_pending` claim, no active idempotency conflict, `max_open_positions = 1`, no retry, bounded post-send reconciliation, and a stop after one send attempt.
- Dry-run and fixture paths may record stale artifact warnings as nonblocking evidence. Real and non-fixture approval, request construction, `order_check`, and `order_send` paths must block stale, missing-timestamp, or malformed-timestamp artifacts before MT5 import or any broker/order call.
- Default upstream artifact max age is 15 minutes. The `order_check` artifact max age before `order_send` is 5 minutes. Manual approval record expiry remains governed by `approval_expiry_time_utc`.
- Stale-artifact block statuses are `manual_approval_record_creation_blocked_stale_upstream_artifact`, `request_construction_dry_run_blocked_stale_upstream_artifact`, `order_check_blocked_stale_upstream_artifact`, and `order_send_pilot_blocked_stale_upstream_artifact`.
- No new execution path was added by the artifact freshness patch or the canonical threshold-pointer update, and no MT5, `order_check`, `order_send`, pipeline, database, or future-state mutation was run as part of those patches.
- No real-money or live-account trading is authorized. Risk caps are maximums, not targets to force; future order sizing must bind to the canonical policy and artifact freshness guards before any broker-adjacent path is considered.

## Next

- Review whether the new ATR-normalized price features and MFE/MAE supervised labels improve clean h5/h10/h20 long/short net runs.
- Compare ML research targets with `scripts/compare_ml_target_reports.py` before using ML rankings to choose follow-up research hypotheses.
- Keep `target_up_10` / `target_down_10` and `target_long_good_10` / `target_short_good_10` as benchmark/reference ML targets, and keep XAUUSD in separate review until stronger threshold diagnostics appear.
- Review performance concentration, payoff ratio, and breakeven win-rate margin on the next clean net runs.
- Prepare ignored local or broker-specific cost configs from `docs/research/COST_MODEL.md` before treating estimated-net results as broker-aware.
- Prepare `config/symbol_metadata.local.json` with verified local point sizes, such as XAUUSD `point_size=0.01` from read-only MT5 Symbol Info, before regenerating metal spread-unit features in strict mode.
- Regenerate price, market, and ML feature tables before comparing new spread-to-ATR research with older reports, because `spread_to_atr_20` now uses price-unit spread instead of raw MT5 points.
- For Pepperstone, copy `config/brokers/pepperstone_razor.example.json` or `config/brokers/pepperstone_standard.example.json` to an ignored local config, verify commission/slippage, and prefer p75/p90/p95 spread calibration before robust net runs.
- Run `scripts/analyze_historical_spreads.py` on the local DB to create p75/p90/p95 spread audits and ignored `.local.json` config candidates before strict net validation.
- Use `scripts/compare_mt5_recent_spreads.py` as a read-only diagnostic to check whether current Pepperstone demo spread conditions resemble the local historical DB sample.
- Review random baseline classifications before designing any rule-based research backtest.
- Review baseline diagnostics to identify combinations that add value beyond single filters.
- Review horizon consistency to separate short-lived, medium/slow, and unstable feature behavior.
- Review preferred feature backtest outputs as exploratory filters only; escalate survivors to yearly validation or walk-forward review before any broader research design.
- Compare gross/none and estimated/net preferred feature runs with `scripts/compare_preferred_feature_backtest_cost_modes.py` before treating any gross edge as useful.
- Review controlled preferred-feature combination backtests for net survivors, cost-erased pairs, concentration warnings, and skipped zero-trade combinations before any further validation.
- Review TP/SL path-exit diagnostics for fixed candidates against their all-row and single-filter baselines before deciding whether a candidate deserves later offline follow-up.
- For exact regime candidate stress survivors, use `scripts/build_regime_candidate_review_package.py` to package existing stress outputs before considering a future offline rule-based research backtester.
- When a regime candidate review package is ready, use `scripts/run_rule_based_regime_candidate_backtest.py` to replay the exact fixed condition and compare generated trades against the prior stress-validation outputs.
- When a rule replay matches stress validation, use `scripts/build_rule_based_regime_candidate_review.py` to summarize monthly, yearly, rolling-window, exit-profile, entry-hour, drawdown, and concentration diagnostics from the existing replay outputs.
- When an extended rule review is ready, use `scripts/build_controlled_rule_research_expansion.py` to prepare the baseline and cost-sensitivity review plan from existing review/replay outputs.
- If controlled expansion is retained for timeout review, use `scripts/build_timeout_fragility_audit.py` on the existing controlled expansion and rule-replay folders before returning to baseline and cost-sensitivity review.
- If timeout fragility audit remains retained for review, use `scripts/build_timeout_root_cause_review.py` on the existing timeout audit and rule-replay folders to diagnose sequence, calendar/hour, cost, and optional read-only feature-context causes before returning to baseline and cost-sensitivity review.
- If timeout root-cause review remains retained because the largest timeout sequence is material, use `scripts/build_timeout_sequence_drilldown_review.py` on the existing root-cause, audit, and rule-replay folders before returning to baseline and cost-sensitivity review.
- After timeout sequence drilldown, use `scripts/build_rule_candidate_gate_decision_report.py` to summarize the fixed-candidate validation chain and record whether the candidate is rejected, remains in timeout review, or can proceed only to limited offline baseline/cost-sensitivity review with the timeout caveat preserved.
- If the gate allows only limited baseline/cost-sensitivity review with the timeout caveat preserved, use `scripts/build_timeout_policy_sensitivity_review.py` to compare current h10 timeout handling, biased timeout-excluded diagnostics, and h20/h40/h80 sensitivity for existing timeout entries before deciding whether the timeout caveat remains acceptable.
- When a branch has no estimated-net single-feature survivor, no robust controlled two-filter survivor, and no fixed TP/SL path-exit survivor, use `scripts/build_research_branch_outcome_report.py` to record the research-only closure outcome.
- Use `scripts/run_preferred_horizon_cost_diagnostics.py --dry-run` before launching any h5/h10/h20 and p50/p75/p90 sensitivity matrix, keep XAUUSD separate from the FX group, and treat `NO_TESTED_COMBINATIONS` branches as input/skipped-output diagnostics rather than review candidates.
- Use `scripts/run_preferred_horizon_cost_diagnostics.py --summarize-existing-run-id RUN_ID` only for summary/report regeneration when child outputs already exist and should not be rerun.
- Use `scripts/run_preferred_horizon_cost_diagnostics.py --diagnose-zero-tested-run-id RUN_ID` when an existing matrix has `NO_TESTED_COMBINATIONS` branches and the row-loss point needs to be documented without rerunning child scripts.
- Use `scripts/diagnose_preferred_horizon_prerequisites.py` when zero-tested diagnostics classify a branch as `no_preferred_backtest_rows`, especially before rerunning h5/h20 preferred horizon work.
- If h5/h20 target columns exist but preferred shortlist inputs are missing, use `scripts/build_preferred_horizon_shortlists.py` to rebuild the preferred target rankings and shortlists with the same h10 methodology before rerunning prerequisite diagnostics.
- Review research decision warnings before promoting anything to future rule-based research.
- Build a rule-based backtest that remains research-only.
- Revisit cost-aware labels only after broker point sizes, spread sources, slippage, and commission assumptions are strict enough to keep gross and net label sets separate.
- Keep `--overwrite`, `--overwrite-validation`, and `--overwrite-final-review` explicit when regenerating outputs.

## Later

- Manual pilot mode may use the explicit CLI flags after the complete non-fixture safety chain is reviewed.
- A future controlled auto-demo mode may use the same flags only from a gated one-shot orchestrator that proves the same safety chain.
- Full scheduler/live-loop mode is not implemented or authorized.
- Explore ML-assisted strategy discovery after robust net validation evidence exists.
- Add a stock/equity adapter.
- Build a dashboard or single trader-facing report after metrics and run conventions are stable.

## Do Not Do Yet

- Real-money trading or live-account trading.
- Any real `order_check` or `order_send` without the complete non-fixture safety chain and its explicit CLI flag.
- Any ungated scheduler, loop, daemon, background task, or retry loop using the operational flags.
- Full scheduler/live-loop operation.
- Strategy optimization or threshold changes as part of demo-pilot progression.
- Complex ML before robust net walk-forward evidence.

## Maintenance Rule

When a future change affects scripts, outputs, methodology, or priorities, update the matching file in `docs/research/` in the same change.
