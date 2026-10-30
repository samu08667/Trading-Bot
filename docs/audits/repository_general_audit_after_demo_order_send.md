# Repository General Audit After Demo Order Send

## 1. Executive summary

This repository has evolved from an offline research bot into a controlled demo signal-to-order validation system. The demo pipeline has reached real MT5 `order_send` once-per-run behavior and has received a real broker rejection (`10018 Market closed`) without execution. The safety posture is materially stronger than a typical prototype: the execution path is split into gated modules, records no-order evidence, binds digests, enforces demo-only checks, caps send attempts at one, uses explicit operator acknowledgments, and has mocked tests for order-check/order-send paths.

The main risk now is not an obvious missing safety gate. The main risk is drift: many execution-sensitive scripts are large, status-string driven, and still duplicate candidate/policy constants and artifact contracts. A shared state helper now exists, but the broader pipeline still needs a formal state machine and a shared contract/spec layer for statuses, artifact names, and policy fields.

No critical live-execution defect was found in this static audit. The highest priority issues are repository hygiene for tracked runtime state, formalization of post-send reject finalization beyond `10027`, and refactoring the long execution modules after the demo lifecycle is stable.

## 2. Scope

Audited statically:

- `scripts/run_fixed_candidate_demo_signal_to_order_pilot_once.py`
- `scripts/build_fixed_candidate_demo_request_construction_dry_run.py`
- `scripts/check_fixed_candidate_demo_order_check.py`
- `scripts/build_fixed_candidate_demo_order_send_pilot_readiness_plan.py`
- `scripts/send_fixed_candidate_demo_order_pilot.py`
- `scripts/fixed_candidate_demo_state_contracts.py`
- `scripts/finalize_fixed_candidate_demo_send_rejected_state.py`
- `scripts/check_fixed_candidate_demo_broker_local_state_reconciliation.py`
- `scripts/check_fixed_candidate_demo_broker_safe_margin_validation.py`
- `config/fixed_candidate_current_canonical.json`
- `config/fixed_candidate_demo_execution_policy.json`
- related tests under `tests/`
- `README.md`, `docs/research/*`, `.gitignore`, `.git/info/exclude`
- repository directories: `scripts`, `src`, `tests`, `config`, `state`, `reports`, `docs`, `graphify-out`

No runtime trading, broker mutation, live pipeline execution, backtest, replay, or paper workflow was executed.

## 3. Branch and working tree

Branch checked:

- `candidate/gbpusd-shadow-validation`

Initial working tree:

- `M state/fixed_candidate_demo_state/gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record.json`
- `M state/fixed_candidate_demo_state/gbpusd_short_h10_1_5_off_hours_demo_state.json`

These are runtime state artifacts. They were read for audit context only and were not modified.

The requested audit file was created under `docs/audits/`. The directory did not exist and was created as permitted by the prompt.

## 4. Commands executed

Read-only/static commands:

- `git branch --show-current`
- `git status --short`
- `Get-ChildItem -Force`
- `Get-ChildItem -Force -Name scripts`
- `Get-ChildItem -Force -Name tests`
- `Get-ChildItem -Force -Name config`
- `Get-Content -Raw -LiteralPath .gitignore`
- `Get-Content -Raw -LiteralPath .git\info\exclude`
- `Test-Path docs\audits`
- `rg --files scripts src tests config docs`
- `Get-ChildItem -Recurse -File state`
- `Get-ChildItem -Recurse -File reports`
- `Get-Content -Raw` for canonical config, execution policy, current state, approval record
- targeted `rg` scans for MT5 calls, state statuses, idempotency, retry, scheduler, constants, and status strings
- line-count scans for largest scripts and tests
- `git ls-files state config`
- `git ls-files reports`
- `git status --short --ignored state config reports graphify-out`

Write commands limited to the audit output:

- `New-Item -ItemType Directory docs\audits`
- file creation: `docs/audits/repository_general_audit_after_demo_order_send.md`

Two read-only exploratory commands had PowerShell quoting/parameter errors while trying to read multiple paths in one call. They had no side effects and were replaced with narrower commands.

## 5. Commands not executed

Not executed:

- MT5 real initialization for this audit
- real `order_check`
- real `order_send`
- full demo pilot send
- watcher, scheduler, paper runner, replay, or backtest
- live pipeline rerun
- database mutation
- state finalization
- report cleanup
- config changes
- tests, because the prompt prioritized static audit and the working tree already contained runtime state modifications
- commit, branch switch, delete, reset, checkout

## 6. Architecture map

### Top-level layout

| Area | Role | Notes |
|---|---|---|
| `scripts/` | Main operational and research command surface | Very script-heavy; many modules include their own CLI, IO, gate logic, schema constants, and reports. |
| `src/` | Small reusable library layer | Contains research/read-only helpers (`config`, `mt5_client`, `risk`, `features`, etc.). Execution pipeline logic mostly lives in `scripts/`, not `src/`. |
| `tests/` | Broad mocked unit/contract coverage | Strong coverage for fixed-candidate demo modules, but fixture duplication is high. |
| `config/` | Canonical and paper/demo configs | Current execution policy is explicit and conservative. Local broker configs are ignored. |
| `state/` | Runtime state and manual approval record | Currently tracked by Git and modified locally; this is the largest hygiene risk. |
| `reports/` | Runtime/research artifacts | Mostly ignored, with `.gitkeep` tracked. Many nested ignored paths are very long. |
| `docs/` | Stable docs and now audits | Research docs are versioned; audit output belongs here. |
| `graphify-out/` | Generated graph output | Ignored through `.git/info/exclude`, not repo `.gitignore`. |

### Module categories

Core reusable helpers:

- `scripts/_fixed_candidate_artifact_freshness.py`
- `scripts/fixed_candidate_demo_state_contracts.py`
- `scripts/research_metrics.py`
- `scripts/research_costs.py`
- `scripts/session_utils.py`
- `src/config.py`
- `src/risk.py`
- `src/mt5_client.py`

Runtime/live or broker-adjacent modules:

- `scripts/run_fixed_candidate_demo_shadow_signal_once.py`
- `scripts/run_fixed_candidate_demo_manual_approval_prep_pipeline_once.py`
- `scripts/create_fixed_candidate_demo_manual_approval_record.py`
- `scripts/build_fixed_candidate_demo_request_construction_dry_run.py`
- `scripts/check_fixed_candidate_demo_order_check.py`
- `scripts/build_fixed_candidate_demo_order_send_pilot_readiness_plan.py`
- `scripts/send_fixed_candidate_demo_order_pilot.py`
- `scripts/check_fixed_candidate_demo_broker_local_state_reconciliation.py`
- `scripts/check_fixed_candidate_demo_broker_safe_margin_validation.py`
- `scripts/finalize_fixed_candidate_demo_send_rejected_state.py`

Execution-sensitive modules:

- `scripts/check_fixed_candidate_demo_order_check.py`
- `scripts/send_fixed_candidate_demo_order_pilot.py`
- `scripts/check_fixed_candidate_demo_broker_local_state_reconciliation.py`
- `scripts/check_fixed_candidate_demo_broker_safe_margin_validation.py`
- `scripts/run_fixed_candidate_demo_signal_to_order_pilot_once.py`

Artifact-only audit/report modules:

- most `build_fixed_candidate_demo_*_plan.py`
- `build_fixed_candidate_*_review*.py`
- `build_timeout_*_review.py`
- `build_rule_candidate_gate_decision_report.py`

Research/offline modules:

- `run_ml_research_pipeline.py`
- `run_data_preparation_pipeline.py`
- `run_research_validation_pipeline.py`
- `run_combined_validation_pipeline.py`
- `run_hypothesis_discovery_pipeline.py`
- `run_walk_forward_research.py`
- `validate_regime_candidate_stress.py`
- `run_tp_sl_path_backtests.py`
- `backtest_*`, `evaluate_*`, `compare_*`

## 7. Execution pipeline contract map

| Step | Producer | Consumer | Artifact/status | Critical fields | Blocking gates | Drift risk |
|---|---|---|---|---|---|---|
| Shadow signal | `run_fixed_candidate_demo_shadow_signal_once.py` | prep pipeline/orchestrator | `shadow_signal_detected` | candidate, symbol, direction, signal time, price, SL, TP | no valid signal blocks | Medium: child paths become deeply nested. |
| Manual approval prep | `run_fixed_candidate_demo_manual_approval_prep_pipeline_once.py` | approval creation/orchestrator | `manual_approval_prep_pipeline_completed...` | child artifact dirs, warning counts | any blocking warning, approval dry-run block | Medium: status reason sometimes lives in child warnings. |
| Approval record | `create_fixed_candidate_demo_manual_approval_record.py` | request construction | `manual_approval_record_created_for_future_request_construction_only` | scope, status, expiry, digest bindings, signal/idempotency | expired, revoked, active existing record, digest mismatch | High: approval record has absolute bound paths. |
| Request construction | `build_fixed_candidate_demo_request_construction_dry_run.py` | order_check | `request_construction_dry_run_available_*` | non-executable intent, no broker payload, digests | freshness, broker/local, margin, duplicate, kill switch, state compatibility | Medium: many status strings and fields repeated. |
| Order check | `check_fixed_candidate_demo_order_check.py` | send readiness | `order_check_available_passed_no_send` | payload fields, retcode, result digest, no send | no real flag, non-demo, payload invalid, digest, state, margin/spread | Medium: long module, many responsibilities. |
| Send readiness | `build_fixed_candidate_demo_order_send_pilot_readiness_plan.py` | send pilot | `order_send_pilot_readiness_plan_available_no_send` | order_check status, request status, state contract | order_check fail, approval expiry, broker/local, margin, duplicate, kill switch | Medium: improved, but planner still duplicates contracts. |
| Order send | `send_fixed_candidate_demo_order_pilot.py` | state/reports/operator | success/reject/blocked statuses | real payload, state claim, retcode, tickets, broker/local post-read | max attempts, final ack, demo account, order_check, readiness, state, duplicate | High: monolithic and stateful. |
| Post-send reconciliation | `send_fixed_candidate_demo_order_pilot.py` bounded read | state/report/finalizers | `broker_local_reconciliation_*_after_*` | positions/orders counts, tickets, result category | unexpected broker state routes hold | High: broker-side reject finalization not yet generalized. |
| State finalization | `finalize_fixed_candidate_demo_send_rejected_state.py` | future rerun path | `send_rejected_no_position_no_order` | state status, retcode, flat reconciliation, ack | only 10027/reconciliation_hold path currently | High: needs generalized reject-flat finalizer. |

## 8. State and idempotency audit

Current state file observed:

- `state_status`: `execution_rejected`
- `last_retcode`: `10018`
- `order_execution_performed`: `false`
- `broker_order_ticket`: `0`
- `broker_deal_ticket`: `0`
- `broker_position_ticket`: empty
- `broker_position_count_after_send`: `0`
- `broker_pending_order_count_after_send`: `0`
- `reconciliation_status`: `broker_local_reconciliation_clean_after_reject_no_broker_state`
- `crash_recovery_required`: `true`
- `automatic_retry_allowed`: `false`
- `retry_performed`: `false`
- `explicit_second_demo_send_after_client_reject_flat`: `true`

Interpretation:

- The current state is safe from an execution perspective: no ticket/deal/position is recorded and retry is disabled.
- It is not final from a lifecycle perspective: `crash_recovery_required=true` remains after a known broker-side reject (`10018 Market closed`) with clean post-send broker/local state.
- `finalize_fixed_candidate_demo_send_rejected_state.py` currently targets the earlier `10027` client-side reject path and requires `state_status == reconciliation_hold`; it does not directly model `execution_rejected + clean_after_reject_no_broker_state`.

State taxonomy observed:

- active/unresolved: `pre_send_pending`, `send_in_progress`, `reconciliation_hold`, `open_reconciliation_required`, `pending_reconciliation_required`
- broker state detected: `broker_position_detected`, `broker_pending_order_detected`
- terminal-ish reject: `send_rejected_no_position_no_order`, `execution_rejected`
- special explicit path: `explicit_second_demo_send_after_client_reject_flat`

Audit conclusion:

- A formal state machine is now warranted. Status strings are acting as a distributed state machine across multiple scripts.
- `fixed_candidate_demo_state_contracts.py` is a good start, but it currently centralizes only one explicit second-send contract.
- The next state contract should cover broker-side rejects with no broker state, including `10018 Market closed`.

## 9. Safety gate audit

Observed protections:

- `max_order_send_attempts == 1` is enforced in the orchestrator and send pilot.
- The orchestrator does not import MT5 or construct broker payloads; it shells out to gated child modules.
- `order_send` requires passed `order_check` and send readiness.
- `order_check` never calls `order_send`.
- `request_construction` writes non-executable intent and explicitly records no broker payload/order object.
- `send_fixed_candidate_demo_order_pilot.py` writes a durable state claim before the send attempt.
- `send_fixed_candidate_demo_order_pilot.py` performs bounded pre-send and post-send broker/local reads.
- `no_retry_performed`, `no_loop_added`, `no_scheduler_added`, and related evidence fields are recorded.
- duplicate protection, kill switch, margin hard cap, spread policy, digest binding, and freshness gates are represented repeatedly.
- demo account/currency/symbol/tick checks are present in order_check/send.

Safety concerns:

- The no-loop/no-scheduler guarantee is mostly by code review/tests and manifest evidence, not by a static guard in CI.
- `positions_get/orders_get` are intentionally used in reconciliation/send paths; this is appropriate but should remain isolated.
- The send pilot is large enough that accidental future broadening of behavior is plausible without a stricter state machine and static safety tests.

## 10. Runtime artifact audit

Good patterns:

- Every major module writes manifest/report/status/warnings/no-order evidence.
- Digest binding is used across approval, request construction, order_check, and send.
- Broker responses are redacted.
- Artifact freshness exists and is shared through `_fixed_candidate_artifact_freshness.py`.
- Runtime reports are mostly ignored by Git.

Issues:

- Approval records bind upstream artifact paths as absolute Windows paths. This is good for local audit precision but poor for portability and replay on another machine.
- `reports/` contains many deeply nested ignored directories; `git status --ignored` emitted many `Filename too long` warnings.
- Artifact naming is verbose and duplicated across modules.
- Reports are comprehensive but operator readability varies; failures often require drilling into several child directories.
- `state/` is tracked and currently modified, unlike most runtime reports.

## 11. Test coverage audit

Strengths:

- There is broad mocked coverage for demo modules.
- `test_check_fixed_candidate_demo_order_check.py` covers payload validity, MT5 fake result handling, and no-send boundary.
- `test_send_fixed_candidate_demo_order_pilot.py` covers fake MT5 send, retcode categories, no retry, duplicate/idempotency gates, and client reject paths.
- `test_run_fixed_candidate_demo_signal_to_order_pilot_once.py` covers orchestrator stop gates and child command propagation.
- `test_fixed_candidate_demo_state_contracts.py` covers the shared client-reject-flat contract.
- Many artifact-only modules have explicit tests proving they do not call forbidden broker functions.

Gaps:

- No single high-level state-machine test enumerates allowed transitions.
- Retcode `10018 Market closed` should get focused tests for reject-flat lifecycle/finalization.
- Some test files are very large and duplicate fixture builders.
- There is no obvious static CI guard that scans execution-sensitive files for forbidden loop/retry/scheduler expansion.
- End-to-end mocked coverage exists for the orchestrator, but the fixture model could be factored into a reusable scenario builder.

## 12. Code quality audit

Largest execution-related scripts:

- `send_fixed_candidate_demo_order_pilot.py`: 2098 lines
- `check_fixed_candidate_demo_order_check.py`: 1797 lines
- `build_fixed_candidate_demo_order_send_pilot_readiness_plan.py`: 1692 lines
- `build_fixed_candidate_demo_request_construction_dry_run.py`: 1450 lines
- `run_fixed_candidate_demo_manual_approval_prep_pipeline_once.py`: 1261 lines
- `run_fixed_candidate_demo_shadow_signal_once.py`: 1231 lines

Main quality risks:

- Long scripts mix CLI parsing, input loading, validation, state evaluation, CSV/JSON writing, report rendering, and runtime actions.
- Candidate constants, spread cap, margin cap, account currency, and status names are repeated in multiple modules.
- CSV fieldnames and output filenames are repeatedly declared.
- Many status strings are raw literals rather than enum-like constants.
- The `scripts/` layer is doing library work that should gradually migrate into reusable `src/` or `scripts/*_contracts.py` modules.

Positive recent change:

- `fixed_candidate_demo_state_contracts.py` centralizes the explicit second-send-after-client-reject-flat contract without broker or file IO.

## 13. Research/offline audit

The research/offline layer is broad and mostly well-labelled as non-execution:

- ML/data pipelines: `run_ml_research_pipeline.py`, `run_data_preparation_pipeline.py`, `ml_research.py`
- backtests/validation: `run_walk_forward_research.py`, `validate_regime_candidate_stress.py`, `run_tp_sl_path_backtests.py`, `backtest_*`
- candidate audit/review: `run_candidate_audit_pipeline.py`, `build_fixed_candidate_*_review*.py`, `build_timeout_*`
- report fusion: `consolidate_*`, `compare_*`

Risks:

- Research scripts are also monolithic.
- Research and demo/live concepts share the fixed-candidate namespace and artifacts.
- `README.md` has grown to include both offline research state and demo-pilot operational policy; it is useful but dense.

Opportunity:

- Split long-term domain concepts into:
  - `StrategySpec`: symbol/timeframe/direction/features/thresholds/research evidence.
  - `ExecutionSpec`: account mode, risk, spread, margin, max positions, state machine, broker payload rules.
  - `ArtifactContract`: producer/consumer filenames, required statuses, digest fields.

## 14. Git hygiene audit

Observed:

- `state/fixed_candidate_demo_state/gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record.json` is tracked and modified.
- `state/fixed_candidate_demo_state/gbpusd_short_h10_1_5_off_hours_demo_state.json` is tracked and modified.
- `reports/` runtime directories are ignored, with only `.gitkeep` tracked for major roots.
- local configs under `config/*.local.json` and `config/brokers/*.json` are ignored as intended.
- `graphify-out/` is ignored only via `.git/info/exclude`, not repo `.gitignore`.
- `git status --ignored` reports many ignored report directories and multiple `Filename too long` warnings.

Risk:

- Runtime state can be accidentally committed because `state/` is tracked.
- Long nested report paths can break tooling on Windows or make cleanup/archival brittle.

## 15. Findings table

| ID | Severity | Title | Files/areas | Risk | Fix | Priority timing |
|---|---|---|---|---|---|---|
| C0 | Critical | No critical live-execution defect found in static audit | execution path | No immediate critical defect found; continue conservative handling. | None now; keep stop gates. | now |
| H1 | High | Runtime state is tracked and dirty | `state/`, `.gitignore` | Accidental commit of approval/state/idempotency runtime data. | Move runtime state to ignored path or untrack after preserving templates. | after demo lifecycle |
| H2 | High | Broker-side reject-flat finalization is not generalized | `send_fixed_candidate_demo_order_pilot.py`, `finalize_*` | Current `10018 Market closed` leaves `crash_recovery_required=true` despite flat state. | Add controlled finalizer for broker-side reject flat. | now |
| H3 | High | Execution modules are monolithic | order_check/send/readiness/request scripts | Drift and subtle contract mismatches. | Extract contracts, IO schemas, MT5 adapters, report writers. | after demo lifecycle |
| H4 | High | Policy constants duplicated | config + execution modules | Margin/spread/currency drift. | Central `ExecutionPolicy` loader/spec. | after demo lifecycle |
| M1 | Medium | Status strings are not typed | all pipeline modules | Fragile producer/consumer matching. | Shared status enums or contract registry. | after demo lifecycle |
| M2 | Medium | Absolute artifact paths in approval record | state approval record | Poor portability and replay outside local machine. | Store repo-relative path plus absolute observed path. | later |
| M3 | Medium | Report paths too deeply nested | `reports/` | Windows path length warnings; cleanup friction. | Shorten run IDs/child nesting, add report retention policy. | now/later |
| M4 | Medium | Fixture builders duplicated | tests | Test maintenance cost and inconsistent scenarios. | Shared fixture/scenario builder for demo pipeline. | after demo lifecycle |
| M5 | Medium | Static safety grep not centralized | tests/scripts | Future code could add loop/retry/scheduler unnoticed. | Add one execution-safety static test suite. | now |
| L1 | Low | `graphify-out/` ignored only locally | `.git/info/exclude` | Teammate machines may see generated files. | Add to `.gitignore` if repo-wide generated output. | later |
| L2 | Low | `src/` underused for reusable logic | `src/`, `scripts/` | Scripts keep accumulating library logic. | Move pure helpers into library layer gradually. | later |
| L3 | Low | README operational section is dense | `README.md` | Operator cognition cost. | Split demo-pilot runbook into docs. | later |

## 16. Critical findings

No critical finding was identified in this static audit.

The current branch should still be treated as execution-sensitive because runtime state indicates a real `order_send` attempt reached MT5 and returned `10018`.

## 17. High priority findings

### H1 Runtime state is tracked and dirty

Files:

- `state/fixed_candidate_demo_state/gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record.json`
- `state/fixed_candidate_demo_state/gbpusd_short_h10_1_5_off_hours_demo_state.json`

Risk:

- Runtime approval, idempotency, and state data can be committed accidentally.

Recommended fix:

- After the demo lifecycle is frozen, migrate runtime state to ignored files or keep only sanitized templates in Git.
- Add a pre-commit/status checklist for `state/`.

Timing:

- after demo lifecycle, before broader collaboration or PR.

### H2 Broker-side reject-flat finalization is not generalized

Files:

- `scripts/send_fixed_candidate_demo_order_pilot.py`
- `scripts/finalize_fixed_candidate_demo_send_rejected_state.py`
- current state JSON

Evidence:

- Current state is `execution_rejected`, `last_retcode=10018`, no broker ticket/deal/position, clean no-broker reconciliation, `automatic_retry_allowed=false`, `retry_performed=false`, but `crash_recovery_required=true`.
- Existing finalizer is shaped around `reconciliation_hold` and client-side reject `10027`.

Recommended fix:

- Add a controlled read-only-evidence finalization module for broker-side reject flat, e.g. `finalize_fixed_candidate_demo_send_rejected_flat_state.py`.
- Require exact retcode, idempotency match, flat broker/local reconciliation, no tickets, and operator acknowledgment.

Timing:

- now, before another explicit demo send.

### H3 Execution modules are monolithic

Files:

- `scripts/send_fixed_candidate_demo_order_pilot.py`
- `scripts/check_fixed_candidate_demo_order_check.py`
- `scripts/build_fixed_candidate_demo_order_send_pilot_readiness_plan.py`
- `scripts/build_fixed_candidate_demo_request_construction_dry_run.py`

Risk:

- Large files make it easier for status contract drift to recur.

Recommended fix:

- Extract pure contracts first, then IO/schema helpers, then MT5 adapters.

Timing:

- after current demo lifecycle, not during active order-send validation.

### H4 Policy constants are duplicated

Files:

- execution modules and `config/fixed_candidate_demo_execution_policy.json`

Risk:

- Silent drift in spread/margin/currency/max-open-position gates.

Recommended fix:

- Introduce a shared `ExecutionPolicy` loader that validates canonical policy and supplies constants to modules.

Timing:

- after demo lifecycle.

## 18. Medium priority findings

### M1 Status strings are not typed

Producer/consumer contracts rely on exact literal strings across files. This has already caused several contract mismatches during the demo sequence.

Fix:

- Add a shared status registry or enum-like module.
- Keep human-readable strings, but consume them through constants.

### M2 Approval record stores absolute artifact paths

Absolute paths are good audit evidence for this workstation but make replay or review on another machine harder.

Fix:

- Store both `repo_relative_path` and `observed_absolute_path`.

### M3 Report paths are too deeply nested

`git status --ignored` emitted many `Filename too long` warnings under ignored `reports/` trees.

Fix:

- Shorten child run directory names.
- Consider `reports/.../<run_id>/children/<short_step_id>` instead of recursive full run IDs.
- Add an archival/cleanup policy for old runtime reports.

### M4 Test fixtures are duplicated

The important tests are good, but large files duplicate manifest builders and state fixtures.

Fix:

- Add `tests/fixtures/fixed_candidate_demo.py` with canonical artifact factories.

### M5 Static safety grep is scattered

Many tests assert forbidden strings module-by-module. A shared execution-safety static test would reduce accidental future broadening.

Fix:

- Add a single test that scans execution-sensitive modules for forbidden scheduler/loop/retry/real-money/bypass patterns.

## 19. Low priority findings

### L1 `graphify-out/` is ignored locally only

It is in `.git/info/exclude`, not `.gitignore`.

Fix:

- Add to `.gitignore` if it is always generated.

### L2 `src/` is underused

Most reusable logic lives in `scripts/`.

Fix:

- Move pure helpers to `src/trading_bot/...` or a stable `scripts/contracts` layer when refactoring.

### L3 README is dense

The README contains important operational policy but is long.

Fix:

- Split demo-pilot runbook and safety policy into `docs/demo/`.

## 20. Refactor candidates

Recommended pure refactors, in safe order:

1. `fixed_candidate_demo_statuses.py`: central status constants.
2. `fixed_candidate_demo_artifact_contracts.py`: filenames, required fields, digest rules.
3. `fixed_candidate_demo_execution_policy.py`: load canonical policy and expose spread/margin/currency/max positions.
4. `fixed_candidate_demo_state_machine.py`: allowed states, terminal states, transition guards, finalization contracts.
5. `fixed_candidate_demo_io.py`: read/write JSON/CSV, atomic write, manifest digest helpers.
6. `fixed_candidate_demo_reports.py`: shared report/no-order evidence writers.
7. `mt5_order_payloads.py`: order_check/order_send payload construction and diagnostics.
8. test fixture builder: canonical approval/request/check/readiness/send scenario factory.

Do not combine these with behavior changes. Each should be mechanically tested.

## 21. Suggested roadmap

### Phase 0: Do not touch now

- Do not change margin/spread/volume policy.
- Do not change current strategy thresholds.
- Do not move state files while an active demo lifecycle is unresolved.
- Do not refactor send/order_check while preparing an immediate operational run.

### Phase 1: Hygiene and contracts with low risk

- Add audit/runbook docs.
- Add static safety grep test.
- Add `.gitignore` entry for `graphify-out/` if desired.
- Add a warning/pre-commit checklist for tracked `state/`.
- Add broker-side reject-flat finalization plan for `10018`.

### Phase 2: State machine and contract centralization

- Expand `fixed_candidate_demo_state_contracts.py` into a full state machine.
- Add transition tests for every state.
- Centralize status constants and artifact contracts.

### Phase 3: Refactor execution modules

- Split `send_fixed_candidate_demo_order_pilot.py`.
- Split `check_fixed_candidate_demo_order_check.py`.
- Keep runtime behavior unchanged while extracting pure functions.

### Phase 4: Separate research/live more cleanly

- Move reusable research code to `src/`.
- Move demo execution contracts to a dedicated package or namespace.
- Keep research outputs and execution artifacts visibly separated.

### Phase 5: StrategySpec / MT5 EA executor

- Define `StrategySpec` for strategy/rules/research lineage.
- Define `ExecutionSpec` for account/risk/broker/order constraints.
- If an MT5 EA executor is introduced, keep Python as contract/audit/orchestration layer unless deliberately re-architected.

## 22. What not to touch yet

Do not touch during the current demo lifecycle:

- order sizing, volume, SL, TP
- margin hard cap and spread policy
- current approval record/state except through explicit authorized finalization modules
- broker payload shape
- idempotency key derivation
- signal_id derivation
- order_check/order_send gate semantics
- duplicate protection/kill-switch gates
- report directories from prior runtime runs
- research thresholds or strategy validity classification

## 23. Recommended next step

Before another demo send attempt, perform a small focused task:

1. Audit current `execution_rejected` state for `retcode=10018`.
2. Confirm broker/local flat with an already available read-only reconciliation artifact or an explicitly authorized read-only reconciliation run.
3. Add or run a controlled finalizer for broker-side reject flat, analogous to the `10027` client-side reject finalizer, with exact operator acknowledgment.
4. Only after state is terminal and `crash_recovery_required=false`, decide whether a new explicit demo module validation send is appropriate.

## 24. Safety confirmation

During this audit:

- no real `order_send` was executed
- no real `order_check` was executed
- no MT5 real connection was initiated
- no live pipeline was run
- no watcher, scheduler, loop, retry, paper workflow, replay, or backtest was run
- no database was mutated
- no config was modified
- no runtime state was modified
- no runtime report was modified
- no commit was made
- no branch switch was performed
- the only filesystem changes were creating `docs/audits/` and this markdown audit file
