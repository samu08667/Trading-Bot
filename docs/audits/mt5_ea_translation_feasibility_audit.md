# MT5 EA Translation Feasibility Audit

Generated for the fixed candidate `gbpusd_short_h10_1_5_off_hours` on branch
`candidate/gbpusd-shadow-validation`.

This audit is read-only with respect to code, configuration, runtime reports,
database, broker state, and MT5. The only artifact created by this task is this
Markdown audit.

## 1. Executive summary

The current Python demo signal-to-order path has validated the technical wiring
through MT5 `order_send` while keeping the execution path heavily gated. The
candidate itself is a simple deterministic rule, not an ML model served online:
short `GBPUSD` on `M15` when the server-hour session is `Off_hours` and two
train-only numeric tercile conditions are satisfied.

An MQL5 Expert Advisor translation is feasible, but only if treated as a
controlled reimplementation of the current Python StrategySpec and feature
generator. The highest-risk work is not the MT5 order API call; it is feature
equivalence and temporal alignment:

- Python currently reads the latest row from the local `price_features` table.
- Feature generation uses closed historical bars ordered by `time_server`.
- `atr_20` is a simple rolling mean of true range over 20 bars.
- `ma_fast` is a simple rolling mean of close over 20 bars.
- `close_to_ma_fast_atr_20 = (close - ma_fast) / atr_20`.
- `tick_volume_percentile_100` is an inclusive rolling percentile rank over the
  current and prior 99 bars, computed as count of values `<= current` divided by
  100.
- `hour_session` comes from broker/server hour, with `Off_hours` equal to hours
  22 and 23.

Recommendation: build an EA in phases. First implement signal evaluation and
logging only, compare it against Python on frozen bar datasets, then add
`OrderCheck`, and only after equivalence evidence add single-shot demo
`OrderSend`. Do not move Python research, walk-forward validation, threshold
calibration, digest-bound approval workflow, or report generation into the EA.

## 2. Current Python strategy specification

Primary sources inspected:

- `config/fixed_candidate_current_canonical.json`
- `config/fixed_candidate_demo_execution_policy.json`
- `config/paper_demo/gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json`
- `reports/fixed_candidate_demo_strategy_spec/gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v5_spread15/fixed_candidate_demo_strategy_spec_manifest.json`
- `reports/fixed_candidate_demo_strategy_spec/gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v5_spread15/fixed_candidate_demo_strategy_spec_report.md`
- `reports/fixed_candidate_demo_strategy_spec/gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v5_spread15/fixed_candidate_demo_strategy_spec.csv`
- `reports/fixed_candidate_train_only_numeric_tercile_thresholds/gbpusd_short_h10_1_5_off_hours_train_only_numeric_tercile_thresholds_train_to_2024_12_31_v1/fixed_candidate_train_only_numeric_tercile_thresholds.json`
- `scripts/generate_price_features.py`
- `scripts/session_utils.py`
- `scripts/run_fixed_candidate_demo_no_order_dry_run.py`
- `scripts/run_fixed_candidate_demo_no_order_cycle_once.py`
- `scripts/run_fixed_candidate_demo_shadow_signal_once.py`
- `scripts/build_fixed_candidate_demo_would_signal_review.py`
- `scripts/build_fixed_candidate_demo_order_shadow_plan.py`
- `scripts/build_fixed_candidate_demo_order_request_shadow_design.py`
- `scripts/build_fixed_candidate_demo_request_construction_dry_run.py`
- `scripts/check_fixed_candidate_demo_order_check.py`
- `scripts/send_fixed_candidate_demo_order_pilot.py`
- linked tests for the dry-run, shadow signal, request construction,
  order-check, and order-send modules
- `docs/audits/repository_general_audit_after_demo_order_send.md`
- `graphify-out/GRAPH_REPORT.md`

Canonical candidate identity:

| Field | Value |
| --- | --- |
| candidate_id | `gbpusd_short_h10_1_5_off_hours` |
| symbol | `GBPUSD` |
| timeframe | `M15` |
| direction | `short` |
| side intent | `sell` / `market_sell` |
| target horizon | `10` bars |
| target family | `preferred_1_5atr_1atr_hit_first` |
| same-bar policy | `stop_first` |
| session filter | `hour_session=Off_hours` |
| spread unit | `broker_points` |
| max spread | `15.0` broker points |
| max open positions | `1` |
| account currency | `EUR` |
| intended demo equity | `1000.0` |
| risk cap | `0.5%` / `5.0 EUR` |
| margin warning cap | `0.50` usage ratio / `500 EUR` |
| margin hard cap | `0.70` usage ratio / `700 EUR` |

Entry rule:

```text
Short GBPUSD M15 only when:
  hour_session == Off_hours
  AND close_to_ma_fast_atr_20 bucket == high_tercile
  AND tick_volume_percentile_100 bucket == mid_tercile
  AND spread <= 15 broker_points
  AND required no-order/live-data gates pass
```

The candidate is explicitly framed as a risk-filtered demo candidate, not as a
final strategy-valid or production-valid trading system.

## 3. Feature and signal logic

The no-order dry-run reads one latest row from an allowlisted local feature
table, default `price_features`, in `data/trading_bot.db`. It filters by
`symbol` and `timeframe` if those columns exist and orders by `time_server DESC
LIMIT 1`. It does not refresh data, mutate the DB, connect to MT5, construct a
request, call `order_check`, or call `order_send`.

Required row columns:

- `time_server`
- `open`
- `high`
- `low`
- `close`
- `atr_20`
- `spread`
- `hour_session`
- `close_to_ma_fast_atr_20`
- `tick_volume_percentile_100`

Feature formulas from `scripts/generate_price_features.py`:

| Feature | Python logic | MQL5 feasibility | Mismatch risk |
| --- | --- | --- | --- |
| `time_server` | Imported broker/server bar time. | Direct via MT5 bar time. | High if Python DB timezone/server time differs from EA terminal series. |
| `hour_session` | `session_name(timestamp.hour)`: Asia 0-7, London 8-13, New_York 14-21, Off_hours 22-23. | Direct in MQL5 from server-hour bar time. | High if EA uses local PC time, UTC, or a different session map. |
| `true_range` | max(high-low, abs(high-prev_close), abs(low-prev_close)). | Direct in MQL5. | Low if closed bars and indexing match. |
| `atr_20` | Simple rolling mean of `true_range` over 20 bars. | Direct in MQL5, but use custom SMA-of-TR or prove `iATR` equivalence. | Medium/high because MT5 `iATR` may use Wilder smoothing depending implementation/handle expectations. |
| `ma_fast` | Simple rolling mean of close over 20 bars. | Direct with `iMA` MODE_SMA period 20 or custom. | Medium if current bar is accidentally included differently. |
| `close_to_ma_fast_atr_20` | `(close - ma_fast) / atr_20`. | Direct. | Medium because it depends on exact close, MA, ATR, and closed-bar indexing. |
| `tick_volume_percentile_100` | Inclusive rolling percentile rank over 100 bars: count(window values <= current tick_volume) / 100. | Direct with custom EA buffer. | High because percentile definition, inclusive ties, and enough-history handling must match exactly. |
| `spread` | Stored broker spread points from imported bar data; live gates later recheck current broker spread. | Direct via `SymbolInfoInteger(SYMBOL_SPREAD)` or `(ask-bid)/point`. | Medium because symbol spread can be dynamic and DB bar spread may differ from current tick spread. |

Train-only thresholds:

| Feature | Required bucket | low/mid cutoff | mid/high cutoff | Bucket rules |
| --- | --- | ---: | ---: | --- |
| `close_to_ma_fast_atr_20` | `high_tercile` | `-0.4303672057741361` | `0.5954421525644814` | low <= low_mid, mid <= mid_high, high > mid_high |
| `tick_volume_percentile_100` | `mid_tercile` | `0.14` | `0.37` | low <= low_mid, mid <= mid_high, high > mid_high |

Signal acceptance checks in the Python path:

- symbol must be `GBPUSD`
- timeframe must be `M15`
- direction must be `short`
- `session_observed` must be `Off_hours`
- `spread_unit` must be `broker_points`
- spread must be numeric and <= `15.0`
- `close_to_ma_fast_atr_20_bucket` must be `high_tercile`
- `tick_volume_percentile_100_bucket` must be `mid_tercile`
- block reason count must be zero
- feature row must be fresh/aligned in live paths
- local state must not already show an open paper/demo trade

Rule-by-rule translation status:

| Rule | Direct MQL5? | Export from Python? | Historical/precomputed needed? | Notes |
| --- | --- | --- | --- | --- |
| Candidate identity | Yes | Optional | No | Hardcode as EA inputs or load StrategySpec JSON/CSV. |
| Session map | Yes | No | No | Must use broker server hour and the `hour_session` map, not the older `session` doc bucket. |
| ATR 20 | Yes | No | 20+ prior bars | Prefer custom SMA true range for exact Python equivalence. |
| MA fast 20 | Yes | No | 20+ prior closes | Use closed bars only. |
| Close-to-MA ATR feature | Yes | No | ATR/MA buffers | Exact arithmetic required. |
| Tick-volume percentile 100 | Yes | No | 100 closed bars | Custom implementation required; inclusive `<=` tie handling. |
| Tercile thresholds | Yes after export | Yes | Train-only thresholds | Do not recalibrate in EA. Export constants from Python StrategySpec. |
| Spread gate | Yes | No | Current tick/symbol info | Recheck immediately before signal/order; units must be broker points. |
| Freshness/live alignment | Partly | Optional | Current terminal bar state | EA naturally runs on terminal bars, but Python freshness semantics need an EA equivalent. |
| One-position-only | Yes | No | Broker positions/orders | EA must scan positions and pending orders by symbol/magic/comment before any send. |

## 4. Risk/SL/TP/execution logic

SL/TP preview:

- Entry reference price in the signal layer is the closed feature row `close`.
- For short:
  - `tp_price_preview = close - 1.5 * atr_20`
  - `sl_price_preview = close + 1.0 * atr_20`
- The would-signal review checks that TP is below entry and SL is above entry.
- It also checks TP distance is approximately `1.5 ATR` and SL distance is
  approximately `1.0 ATR` with a tolerance used by the review.

Horizon/timeout:

- Horizon is `h10`, meaning 10 M15 bars.
- Target family is `preferred_1_5atr_1atr_hit_first`.
- Timeout note: close/evaluate after h10 if neither TP nor SL is hit first.
- Same-bar policy is `stop_first` in research labeling.

Execution intent:

- Request construction emits a non-executable request intent only.
- It binds `volume_lots`, `entry_reference_price`, `sl_price`, `tp_price`,
  `risk_amount`, `risk_percent`, `broker_margin_estimate`,
  `broker_margin_usage_ratio`, current spread, signal id, idempotency key, and
  approval record metadata.
- The dry-run request intent explicitly marks:
  - `broker_payload_constructed=false`
  - `executable_order_object_constructed=false`
  - `order_check_allowed_now=false`
  - `order_send_allowed_now=false`
  - `order_execution_allowed=false`

Risk and volume:

- Canonical demo execution policy uses `intended_demo_equity=1000.0`,
  `risk_percent_max=0.5`, and `risk_amount_max=5.0`.
- The risk/volume shadow plan computes:
  - `risk_distance_price = sl_price_preview - entry_reference_price` for short
  - `risk_amount = demo_equity * risk_percent / 100`
  - `value_per_price_unit_per_lot = trade_tick_value / trade_tick_size`
  - `risk_per_lot = risk_distance_price * value_per_price_unit_per_lot`
  - `raw_volume_lots = risk_amount / risk_per_lot`
  - `stepped_volume_lots = floor(raw_volume_lots / volume_step) * volume_step`
- Volume is blocked if below `volume_min` or above `volume_max`.
- The policy does not force full risk if margin is infeasible.
- Broker-safe margin validation later confirms demo account, EUR currency,
  equity policy, symbol contract, current spread, and `order_calc_margin` usage
  ratio <= `0.70`.

Order-check/order-send payload currently used by Python:

| Field | Current Python mapping |
| --- | --- |
| `action` | `TRADE_ACTION_DEAL` |
| `symbol` | `GBPUSD` |
| `volume` | request intent `volume_lots` |
| `type` | `ORDER_TYPE_SELL` |
| `price` | current tick `bid` at check/send time |
| `sl` | request intent `sl_price` |
| `tp` | request intent `tp_price` |
| `deviation` | `10` |
| `magic` | `151015` |
| `comment` | broker-safe ASCII alphanumeric string, max 20 chars, candidate prefix plus idempotency suffix |
| `type_time` | `ORDER_TIME_GTC` |
| `type_filling` | `ORDER_FILLING_IOC` |

Important execution nuance:

- The signal entry reference is the closed bar close.
- The actual order payload price is current bid for the single check/send.
- SL/TP are carried from the signal/approval record, not recomputed from the
  current bid in the order-check/send modules.
- An EA must explicitly decide whether to preserve this behavior or introduce a
  new slippage/staleness rule. Changing this is a strategy/execution contract
  change and should not be hidden inside the port.

## 5. MQL5 translation feasibility

Overall feasibility: yes for demo-only single-shot EA execution, after
equivalence validation.

Recommended implementation level:

- Put deterministic signal evaluation in MQL5.
- Keep offline research, threshold calibration, candidate selection, audit
  reports, and walk-forward analysis in Python.
- Export a small StrategySpec from Python or hand-author a locked EA input set.
- Do not embed the full Python pipeline, digest-binding system, or approval
  workflow in MQL5 unless there is a deliberate architecture migration.

Translation matrix:

| Component | MQL5 feasibility | Preferred approach |
| --- | --- | --- |
| Symbol/timeframe/direction | High | EA inputs with runtime guard. |
| Off-hours session | High | Use broker server bar hour from closed M15 bar. |
| ATR/MA features | High with care | Custom calculations or proven indicator equivalence. |
| Tick-volume percentile | Medium | Custom rolling buffer, 100 closed bars, inclusive ties. |
| Train-only thresholds | High | Export constants from Python StrategySpec; never recalibrate in EA. |
| Signal yes/no | High after feature parity | Evaluate only on newly closed M15 bar. |
| Spread gate | High | Use `SYMBOL_SPREAD` or tick bid/ask converted to points. |
| Volume/risk | Medium | Use MT5 symbol contract values; preserve floor-to-step and caps. |
| SL/TP | Medium | Normalize to symbol digits and validate stops/freeze levels. |
| OrderCheck | High | Use `OrderCheck` exactly once per candidate event. |
| OrderSend | High but execution-sensitive | One explicit attempt only, no retry. |
| Digest/idempotency approval | Low for direct port | Keep as Python-side governance or implement a simpler EA state lock. |
| Reporting | Medium | EA logs CSV/JSON-like lines; Python consumes logs for audit. |

## 6. Python-vs-MT5 mismatch risks

Highest-risk mismatch points:

1. Time basis and timezone
   - Python uses `time_server` from imported broker bars.
   - EA must use MT5 server-time bars, not PC local time or UTC conversion.
   - `Off_hours` is hours 22 and 23 in `hour_session`.

2. Closed bar vs current bar
   - Python evaluates the latest row in `price_features`, which represents an
     imported/generated bar row.
   - EA should evaluate on a newly closed M15 bar, typically shift 1, and must
     not let current forming-bar values leak into features.

3. ATR equivalence
   - Python `atr_20` is a simple rolling mean of true range.
   - MT5 `iATR` equivalence must be tested; if not exact, implement custom TR
     SMA in EA.

4. MA equivalence
   - Python `ma_fast` is simple rolling mean of close over 20 bars.
   - EA should use closed-bar SMA over the same bar set.

5. Tick-volume percentile
   - Python percentile rank includes the current bar and counts values `<=`
     current over the 100-bar window.
   - Different tie handling or using a 99-prior-only window can change bucket.

6. Tercile thresholds
   - Thresholds are train-only and fixed.
   - EA must not recompute thresholds on live data.

7. Spread points
   - Python uses broker points with max `15.0`.
   - EA must use point-based spread, not pips, price units, or spread-to-ATR.

8. Rounding, digits, and point
   - GBPUSD currently expects 5 digits and point around `0.00001`.
   - SL/TP and entry reference must be normalized with `NormalizeDouble` and
     checked against broker stop/freeze levels.

9. Entry reference vs current execution price
   - Python signal uses closed-bar close as entry reference, but order payload
     uses current bid.
   - EA needs an explicit stale/slippage/price-distance guard before send.

10. Filling mode
    - Python pilot uses `ORDER_FILLING_IOC`.
    - EA should inspect symbol-supported filling modes and either require IOC or
      block with a clear reason.

11. Trade session and trade allowed flags
    - Python send path checks demo account and terminal/account trade flags.
    - EA must check `TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)`,
      account trade mode, account trade allowed, and symbol trade mode.

12. Duplicate/one-position logic
    - Python uses local state, broker/local reconciliation, duplicate
      protection, idempotency, and max open positions.
    - EA must at least enforce no open/pending GBPUSD trade for its magic/comment
      and ideally persist a signal id/idempotency key.

13. State recovery
    - Python has explicit recovery/finalization logic for client-side rejects and
      reconciliation holds.
    - EA should log every pre-send and post-send state transition, never retry,
      and leave recovery to operator/Python audit until a separate EA recovery
      contract exists.

## 7. Proposed EA architecture

EA purpose:

- Demo-only executor for the fixed StrategySpec.
- Single signal evaluation on closed M15 bars.
- Optional single `OrderCheck`.
- Optional single `OrderSend` only after explicit input flags and safety checks.
- No scheduler, no retry loop, no martingale/grid/re-entry automation.

Suggested EA inputs:

```text
input string CandidateId = "gbpusd_short_h10_1_5_off_hours";
input string ExpectedSymbol = "GBPUSD";
input ENUM_TIMEFRAMES ExpectedTimeframe = PERIOD_M15;
input bool DemoAccountOnly = true;
input bool EnableOrderCheck = true;
input bool EnableOrderSend = false;
input bool ConfirmSingleDemoSendOnly = false;
input double MaxSpreadPoints = 15.0;
input double RiskPercentMax = 0.5;
input double RiskAmountMax = 5.0;
input double MaxMarginUsageRatio = 0.70;
input int MaxOpenPositions = 1;
input int HorizonBars = 10;
input double TpAtr = 1.5;
input double SlAtr = 1.0;
input int AtrPeriod = 20;
input int MaFastPeriod = 20;
input int VolumePercentileWindow = 100;
input double CloseToMaFastLowMid = -0.4303672057741361;
input double CloseToMaFastMidHigh = 0.5954421525644814;
input double TickVolumePctLowMid = 0.14;
input double TickVolumePctMidHigh = 0.37;
input int MagicNumber = 151015;
input int DeviationPoints = 10;
input bool NoAutomaticRetry = true;
```

Recommended internal modules:

1. StrategySpec loader/guard
   - Verify symbol, timeframe, direction, thresholds, spread policy, and risk
     caps.
   - Either hardcode constants or load from a read-only StrategySpec file copied
     from Python artifacts.

2. Closed-bar detector
   - Run signal evaluation only once per newly closed M15 bar.
   - Persist last evaluated bar time in a local terminal global variable or file.

3. Feature calculator
   - Custom true range, ATR SMA 20, close SMA 20, close-to-MA/ATR, and tick
     volume percentile 100.
   - Emit feature values and buckets to log.

4. Signal evaluator
   - Require `hour_session=Off_hours`.
   - Require close-to-MA/ATR high tercile.
   - Require tick-volume percentile mid tercile.
   - Require spread <= 15 broker points.
   - Require no existing position/pending order.

5. Pre-trade checks
   - Demo account only.
   - EUR account currency if preserving the current policy.
   - Terminal/account trade allowed.
   - Symbol visible and trade enabled.
   - Current bid/ask available.
   - Stop/freeze level compatibility.
   - Margin estimate with `OrderCalcMargin`.
   - Volume min/max/step and risk cap.
   - One-position-only and duplicate guard.

6. OrderCheck stage
   - Build an in-memory request equivalent to Python.
   - Call `OrderCheck` at most once per signal attempt.
   - Log request redacted fields, retcode, comment, margin/free margin details.

7. OrderSend stage
   - Disabled by default.
   - Requires explicit demo-only inputs.
   - Calls `OrderSend` at most once.
   - No retry, no loop, no automatic second send.
   - Logs retcode category and post-send position/order read.

8. State/logging
   - Persist signal id, idempotency key, bar time, entry reference, SL, TP,
     volume, order-check result, order-send attempt count, retcode, ticket/deal,
     and recovery recommendation.
   - Python can later ingest EA logs for audit.

## 8. StrategySpec proposal

Do not translate the entire Python pipeline into MQL5. Export or encode only the
minimal deterministic StrategySpec needed for the EA:

```json
{
  "candidate_id": "gbpusd_short_h10_1_5_off_hours",
  "symbol": "GBPUSD",
  "timeframe": "M15",
  "direction": "short",
  "session": {
    "column": "hour_session",
    "required_value": "Off_hours",
    "server_hours": [22, 23]
  },
  "features": {
    "atr": {"name": "atr_20", "period": 20, "method": "sma_true_range"},
    "ma_fast": {"period": 20, "method": "sma_close"},
    "close_to_ma_fast_atr_20": {
      "formula": "(close - ma_fast) / atr_20",
      "required_bucket": "high_tercile",
      "low_mid_cutoff": -0.4303672057741361,
      "mid_high_cutoff": 0.5954421525644814
    },
    "tick_volume_percentile_100": {
      "formula": "count(window_tick_volume <= current_tick_volume) / 100",
      "window": 100,
      "required_bucket": "mid_tercile",
      "low_mid_cutoff": 0.14,
      "mid_high_cutoff": 0.37
    }
  },
  "spread_policy": {
    "unit": "broker_points",
    "max_spread_points": 15.0,
    "when_missing": "block",
    "when_exceeded": "skip_or_block_before_order"
  },
  "sl_tp": {
    "entry_reference": "closed_bar_close",
    "tp_atr": 1.5,
    "sl_atr": 1.0,
    "same_bar_policy_research": "stop_first",
    "horizon_bars": 10
  },
  "risk": {
    "account_currency": "EUR",
    "intended_demo_equity": 1000.0,
    "risk_percent_max": 0.5,
    "risk_amount_max": 5.0,
    "volume_rounding": "floor_to_volume_step",
    "max_margin_usage_ratio": 0.70
  },
  "execution": {
    "demo_account_only": true,
    "max_open_positions": 1,
    "order_type": "market_sell",
    "price_source": "current_bid_at_order_check_or_send",
    "deviation": 10,
    "magic": 151015,
    "type_time": "ORDER_TIME_GTC",
    "type_filling": "ORDER_FILLING_IOC",
    "max_order_send_attempts": 1,
    "automatic_retry_allowed": false
  }
}
```

## 9. Validation plan

Phase 1: offline fixture parity

- Export a fixed set of GBPUSD M15 bars from the Python DB with at least 150
  consecutive rows per sample window.
- Include columns: `time_server`, `open`, `high`, `low`, `close`, `tick_volume`,
  `spread`, Python `atr_20`, `ma_fast`, `close_to_ma_fast_atr_20`,
  `tick_volume_percentile_100`, `hour_session`, buckets, signal yes/no, entry,
  SL, TP.
- Feed the same OHLCV rows into an EA test harness or MQL5 script.
- Compare feature values row by row.

Phase 2: closed-bar live dry-run parity

- Run Python no-order shadow and EA signal-only mode side by side.
- Do not allow EA order-check/send.
- Compare the last closed bar time, features, buckets, spread, signal yes/no,
  entry reference, SL, TP, and skip/block reasons.

Phase 3: order-check parity

- Enable EA `OrderCheck` only after feature parity.
- Compare Python and EA volume, price, SL, TP, margin, retcode, and broker
  comment policy.
- Each signal attempt can call order-check at most once.

Phase 4: demo order-send pilot

- Enable send only after order-check parity and operator approval.
- One explicit send attempt only.
- No retry.
- Post-send reconciliation must confirm broker/local state and audit retcode.

Acceptance criteria:

- `hour_session` matches for 100% of sampled bars.
- ATR and MA values match within a strict numeric tolerance appropriate for
  double precision and symbol digits.
- `close_to_ma_fast_atr_20` bucket matches for 100% of sampled rows outside a
  pre-declared epsilon band around thresholds.
- `tick_volume_percentile_100` matches exactly or within 1e-12 for percentile
  values; buckets must match 100%.
- Signal yes/no matches 100% for sampled closed bars.
- Entry, SL, and TP match after symbol-digit normalization.
- Spread gate matches in broker points.
- EA never evaluates the forming bar.
- EA never sends more than one order per explicit approved attempt.

## 10. What not to translate directly

Do not translate these Python concerns directly into the EA:

- Research pipelines, hypothesis discovery, backtests, walk-forward validation,
  stress validation, and candidate selection.
- Train-only threshold generation or recalibration.
- Full manual approval prep pipeline and digest-bound record creation.
- Runtime report trees and CSV/JSON artifact orchestration.
- Stale override/module-validation override semantics used for Python module
  validation.
- DB mutation or feature-table refresh logic.
- Recovery/finalization modules for Python state, unless a separate EA recovery
  contract is designed.
- Any retry loop, scheduler, watcher, background polling engine, or production
  trading mode.
- Real-account support.

The EA should not become a second Python pipeline written in MQL5. It should be
a compact deterministic executor with auditable inputs and logs.

## 11. Recommended next step

Recommended next step: create a separate EA translation design packet before
writing MQL5 execution code.

Minimum packet contents:

- Frozen StrategySpec JSON derived from the audited values above.
- A Python-exported bar/feature parity dataset.
- An MQL5 signal-only prototype or script that reads the same bars and emits
  calculated features.
- A comparison report for ATR, MA, tick-volume percentile, buckets, signal,
  entry, SL, TP, and spread gate.
- A decision gate stating whether EA `OrderCheck` may be added.

Only after that parity report passes should the project add a demo-only EA
`OrderCheck` path. Demo `OrderSend` should remain a later, explicit one-shot
operator decision.

## 12. Safety confirmation

- No MT5 real connection was executed during this audit.
- No broker API was executed.
- No `positions_get` or `orders_get` was executed.
- No `order_check` was executed.
- No `order_send` was executed.
- No full pilot send was executed.
- No database mutation was performed.
- No runtime state was modified.
- No runtime report artifact was modified.
- No configuration or policy file was modified.
- No retry, loop, scheduler, watcher, or background task was added.
- No idempotency, duplicate-protection, kill-switch, margin, spread, or manual
  approval gate was bypassed.
- The only file created by this task is
  `docs/audits/mt5_ea_translation_feasibility_audit.md`.
