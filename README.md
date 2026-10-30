# Trading-Bot

Offline trading research and a guarded **GBPUSD M15 demo-only candidate**.
Python tools prepare data, evaluate hypotheses, and validate a fixed strategy;
MQL5 prototypes translate that candidate into explicitly gated demo execution.

**Status:** research and demo prototype. Production readiness, live-account
support, and unattended execution are not established or supported.
Offline results do not establish future profitability.

## Navigation

- [Current candidate](#current-candidate)
- [Implementation status](#implementation-status)
- [Architecture](#architecture)
- [Offline testing](#offline-testing)
- [Limitations](#limitations)
- [Documentation](#documentation)
- [Source and artifact policy](#source-and-artifact-policy)

## Current candidate

The fixed candidate is `gbpusd_short_h10_1_5_off_hours`.
Its active EA is
[GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5](mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5).

| Property | Current scope |
| --- | --- |
| Instrument / timeframe | GBPUSD / M15 |
| Direction | Short only |
| Session | Off-hours: server hours 22 and 23, subject to Friday restrictions |
| Inputs | Closed bars; ATR-normalized price distance and tick-volume context |
| Threshold lineage | Frozen train-only thresholds; generic full-sample terciles remain exploratory |
| Spread limit | 15 broker points, not pips |
| Position limit | One open position |
| Research TP / SL | 1.5 ATR target / 1 ATR stop |
| Time exit | Ten post-entry M15 bar completions; Friday forced-flat policy |
| Sizing | Opt-in 0.5% equity risk sizing; fixed-lot compatibility mode |

The detailed rule and lifecycle contract are in the
[strategy specification](config/strategy_specs/gbpusd_short_h10_1_5_off_hours_strategy_spec.json).
The [demo policy](config/fixed_candidate_demo_execution_policy.json) records an
intended EUR 1,000 demo equity, EUR 5 maximum risk, 50% margin warning, and 70%
hard margin cap. These are policy values, not an account balance or authorization
to trade. The risk cap is enforced in the opt-in risk-sizing path; fixed-lot
mode retains its own behavior and logs risk for review.

Older paper-only 1% examples are not the current demo policy. Numeric risk
limits do not replace account, margin, spread, reconciliation, or approval gates.

## Implementation status

| Area | Implemented | Validation boundary |
| --- | --- | --- |
| Research | SQLite data preparation, features, ML diagnostics, backtests, yearly and walk-forward validation | Offline evidence and hypothesis triage |
| Python demo path | Shadow planning, readiness checks, approvals, freshness guards, duplicate protection, gated one-shot pilots | Real demo calls require the complete non-fixture gate chain |
| MQL5 entry | Raw-source signal parity, `OrderCheck`, request preflight/digest, one entry `OrderSend` call site | Demo account and explicit EA inputs required |
| MQL5 lifecycle | Watch, close preflight, one close `OrderSend` call site, ten-bar and Friday exits | Restart/recovery limitations remain |
| Observability | Session identifiers, transaction history lookup, deal classification and costs | Latest observability patch still needs supervised MT5 validation |

The time-exit alignment (`AUD-001`) and first-tick entry freshness (`AUD-002`)
fixes have code and deterministic offline tests. They still require
deterministic Strategy Tester and supervised demo evidence. A new smoke with
automatic entry/lifecycle remains blocked pending the Strategy Tester checks,
as recorded in the [smoke runbook](docs/demo_live_smoke_runbook.md#readiness-classification).

The Python pilot and MQL5 EA are separate execution paths. Neither a CLI flag
nor an EA input alone grants execution permission. See the
[current project state](docs/research/PROJECT_STATE.md#current-fixed-candidate-demo-execution-stage)
for the detailed gate chain and implementation notes.

## Architecture

Research and execution currently share this repository and codebase, including
feature calculations and fixed-candidate definitions. Future research development
is moving to a separate repository. That separation is in progress; the research
tools here remain part of this snapshot.

| Location | Responsibility |
| --- | --- |
| [src/](src/) | Python market-data access, features, research, backtest and risk helpers |
| [scripts/](scripts/) | Data preparation, research orchestration, diagnostics and gated demo stages |
| [mt5_ea_prototypes/](mt5_ea_prototypes/) | Signal-only, OrderCheck, lifecycle-watch and demo-send prototypes; raw-bar exporter |
| [mql5/](mql5/) | Manual economic-calendar exporter |
| [config/](config/) | Candidate definitions, policy files and versioned examples |
| [tests/](tests/) | Synthetic/mocked Python tests and MQL5 source checks |
| [docs/](docs/) | Research references, design packets, audits and supervised runbooks |
| `data/`, `reports/`, `logs/`, `models/` | Local generated artifacts; tracked empty placeholders only |

Research data flows from calendar exports and historical bars through SQLite
feature tables and supervised datasets into offline diagnostics and reports.
`main.py` is a terminal-connected, read-only data entry point; it is not an
offline test command or a trading service launcher.

Detailed script roles are mapped in
[Pipeline Steps](docs/research/PIPELINE_STEPS.md). Terminal-connected acquisition
and offline research are documented separately from the demo execution path.

## Offline testing

Use a fresh environment with the offline dependencies only. From the repository
root on Windows PowerShell:

```powershell
python -m venv .venv-offline
.\.venv-offline\Scripts\python.exe -m pip install numpy pandas scikit-learn pytest python-dotenv
.\.venv-offline\Scripts\python.exe -m pytest -q
```

On other platforms, use `.venv-offline/bin/python` for the same commands.
The test suite uses synthetic data and mocked broker interfaces. MQL5 tests
inspect source and modeled behavior; they do not compile an EA, run Strategy
Tester, or establish broker execution parity.

Do not install `MetaTrader5` in this offline environment. `requirements.txt`
includes the terminal connector for separately supervised workflows; installing
the full list is unnecessary for offline testing. Do not run `main.py`, MT5
importers, or demo-pilot commands as part of this check.

Research runs beyond the tests require local datasets and sometimes previously
generated reports that are absent from this public snapshot. See
[usage and prerequisites](docs/research/PIPELINE_STEPS.md#detailed-usage-reference)
before running the research pipeline. The full pipeline imports from MT5 unless
its price-import stage is explicitly skipped.

## Limitations

- No production-readiness claim, live-account support, scheduler, daemon, or
  unattended operating procedure.
- No retry loop in the guarded execution prototypes. Uncertain broker outcomes
  require reconciliation and review.
- EA session state is in memory. Restarted or externally discovered positions
  remain unresolved under the current manual-review policy; durable recovery
  is not complete.
- Latest timing, freshness, and deal-observability changes need MT5 validation.
  Offline tests are not terminal or broker acceptance tests.
- Deal-time synchronized Bid/Ask capture and the replay-versus-broker Bid/Ask
  mismatch remain unresolved.
- Research cost models are estimates. Tick volume is broker-feed context,
  not centralized exchange volume; fitted thresholds require time-safe lineage.
- Historical evidence and generated threshold/report artifacts referenced by
  some configurations are not distributed. A clean clone is not a ready-to-run
  demo deployment.

See [methodology guardrails](docs/research/METHODOLOGY_GUARDRAILS.md) for leakage,
label overlap, cost, and interpretation constraints, and
[next actions](docs/research/NEXT_ACTIONS.md) for planned work.

## Documentation

| Read this for | Reference |
| --- | --- |
| Current capabilities, gates and candidate lineage | [Project State](docs/research/PROJECT_STATE.md) |
| Script map, data preparation, command examples and troubleshooting | [Pipeline Steps](docs/research/PIPELINE_STEPS.md) |
| Which reports to read and how to interpret metrics | [Outputs And Reports](docs/research/OUTPUTS_AND_REPORTS.md) |
| Time safety, validation boundaries and research discipline | [Methodology Guardrails](docs/research/METHODOLOGY_GUARDRAILS.md) |
| Spread units, estimated net returns and broker cost examples | [Cost Model](docs/research/COST_MODEL.md) |
| Planned research and demo-hardening work | [Next Actions](docs/research/NEXT_ACTIONS.md) |
| Research regime labels | [Regime Classification](docs/research/REGIME_CLASSIFICATION.md) |
| Raw-source signal parity | [Parity Workflow](docs/mt5_raw_source_parity_workflow.md) |
| EA inputs, preflight, logs and lifecycle modes | [Demo-Only EA](docs/mt5_order_send_demo_only_ea_scaffold.md) |
| Opt-in sizing design | [Risk-Based Sizing](docs/mt5_risk_based_position_sizing_design_packet.md) |
| Supervised smoke prerequisites and stop conditions | [Smoke Runbook](docs/demo_live_smoke_runbook.md) |

Design packets and audits record their own implementation stage. Historical
findings can predate later fixes; use the project state and smoke readiness
classification for the current boundary.

## Source and artifact policy

This public repository began as an independent source snapshot. Original
history and operational evidence are preserved privately; historical commit
references in the documentation may not resolve here.

The publication contains source, tests, configuration examples, documentation,
and empty directory placeholders. Keep credentials, `.env`, local broker
configuration, databases, generated reports, runtime CSVs, logs, state,
actual approval records, compiled EAs, and private terminal exports out of Git.
See [.gitignore](.gitignore) for the tracked exclusion rules.

Documentation and tests do not authorize broker actions, terminal launches,
or changes to an existing demo deployment.
