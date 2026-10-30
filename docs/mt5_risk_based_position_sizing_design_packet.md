# MT5 Risk-Based Position Sizing Design Packet

## Scope

This packet documents the localized entry-sizing patch for
`GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5`. It changes only entry volume
selection. It does not change signal logic, feature formulas, SL/TP price logic,
OrderCheck gates, entry `OrderSend` count, lifecycle close, StrategySpec values,
retry policy, scheduler policy, or live-account boundaries.

Current status: implemented and runtime-validated in demo/tester evidence. The
fixed-lot regression remains backward compatible, risk-based sizing is opt-in,
the policy cap is 0.5% of `ACCOUNT_EQUITY`, and lifecycle close continues to use
the actual open position volume rather than entry sizing.

## Safe Defaults

```text
InpUseRiskBasedSizing = false
InpVolumeLots = 0.01
InpRiskPercentPerTrade = 0.5
InpMaxRiskPercentPerTrade = 0.5
```

With `InpUseRiskBasedSizing=false`, the EA keeps the validated fixed-lot entry
behavior. The risk inputs are logged for audit, but the 0.5% risk cap is enforced
only when risk-based sizing is enabled.

## 0.5% Equity Policy

When `InpUseRiskBasedSizing=true`, the account basis is `ACCOUNT_EQUITY`:

```text
risk_amount_account_currency = ACCOUNT_EQUITY * InpRiskPercentPerTrade / 100.0
```

The allowed risk-based policy is 0.5% per trade. `InpMaxRiskPercentPerTrade`
must remain 0.5 and `InpRiskPercentPerTrade` must be greater than zero and not
greater than that cap when `InpUseRiskBasedSizing=true`. Invalid risk inputs in
risk-based mode block before `OrderCheck` and before entry `OrderSend`.

For example, equity 1000 EUR implies risk amount 5 EUR. With the existing
1 ATR SL and 1.5 ATR TP, the gross theoretical TP audit target is about 7.50 EUR
before spread, slippage, commission, and lifecycle exits.

## Formula

The EA uses the already computed strategy prices:

```text
entry_price = sell request bid
sl_price = strategy SL preview normalized to symbol digits
tp_price = strategy TP preview normalized to symbol digits
sl_distance = abs(entry_price - sl_price)
```

For one lot, the preferred broker-aware calculation is:

```text
OrderCalcProfit(ORDER_TYPE_SELL, symbol, 1.0, entry_price, sl_price, profit)
loss_per_1_lot_at_sl = abs(profit)
```

This avoids hardcoded pip values and avoids assuming USD account currency. If
that calculation is unavailable, the fallback uses `SYMBOL_TRADE_TICK_SIZE`,
`SYMBOL_TRADE_TICK_VALUE_LOSS`, and then `SYMBOL_TRADE_TICK_VALUE`. If neither
path can produce a positive loss value, the entry blocks with
`sizing_tick_value_unavailable`.

```text
raw_risk_volume_lots = risk_amount_account_currency / loss_per_1_lot_at_sl
```

The expected gross TP amount is audited with `OrderCalcProfit` at TP when
available, otherwise with the strategy 1.5 risk/reward ratio.

## Volume Normalization

The calculated volume is floored to the broker volume step. It is never rounded
up because rounding up can exceed the 0.5% cap.

Required broker properties:

```text
SYMBOL_VOLUME_MIN
SYMBOL_VOLUME_MAX
SYMBOL_VOLUME_STEP
```

Blocking statuses:

```text
sizing_volume_below_min_lot
sizing_volume_above_max_lot
sizing_effective_risk_exceeds_policy
```

The first patch does not cap to max lot automatically. Above-max volume blocks
before `OrderCheck`.

## Pipeline Placement

Sizing happens before:

```text
request digest
OrderCheck
send preflight
entry OrderSend
```

If sizing fails, `OrderCheck` is not called and no entry send can occur. The
existing demo-only, live-forbidden, spread, one-position-only, pending-order,
Friday cutoff, request digest, and no-retry gates remain in force.

## Logging

New log:

```text
position_sizing_log.csv
```

Key fields:

```text
sizing_mode
fixed_volume_lots
risk_percent_per_trade
max_risk_percent_per_trade
risk_account_basis
account_equity
account_balance
risk_amount_account_currency
entry_price
sl_price
tp_price
sl_distance_price
loss_per_1_lot_at_sl
raw_risk_volume_lots
normalized_risk_volume_lots
volume_min
volume_max
volume_step
effective_risk_amount
effective_risk_percent
expected_tp_amount
risk_reward_ratio
sizing_status
sizing_block_reason
sizing_digest
```

`position_sizing_log.csv` may include `sizing_phase` values such as
`order_check` and `send_preflight`, but `sizing_phase`, timestamps, run id,
`attempt_id`, `signal_id`, and other log-row context are not part of the
canonical `sizing_digest`. The digest is phase-invariant so an unchanged economic
request can pass the OrderCheck-to-send-preflight digest comparison.

The main entry logs also carry sizing fields: `decision_log.csv`,
`order_check_log.csv`, `send_preflight_log.csv`, and `order_send_log.csv`.
`run_final_summary_log.csv` also includes in-memory sizing counters for fixed
and risk-based sizing evaluations, passed and blocked sizing statuses, main
sizing block reasons, and min/max observed effective risk percent plus final
volume lots. These counters summarize sizing audit events; they do not change
entry gates or parse runtime CSV files.

## Lifecycle Boundary

Integrated lifecycle close remains unchanged. It closes the actual open position
volume only. Risk sizing is an entry request concern and must not alter close
request volume or close gates.

## Static Guard Expectations

Future guards should verify:

- risk-based sizing defaults off;
- risk percent and max risk percent default to 0.5;
- `OrderCalcProfit` is used for the one-lot SL loss calculation;
- sizing happens before `OrderCheck` and entry send;
- request digest includes sizing fields;
- `position_sizing_log.csv` exists;
- total `OrderSend(` count remains 2;
- no `OrderSendAsync`, `PositionClose`, `CTrade`, `trade.Buy`, `trade.Sell`,
  `Sleep`, `OnTimer`, retry loop, scheduler, martingale, or grid path is added.