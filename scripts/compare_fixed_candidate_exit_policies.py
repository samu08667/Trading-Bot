"""Compare fixed GBPUSD candidate exit policies offline.

This research script keeps the fixed-candidate entry rule unchanged and varies
only the exit policy. It reads local SQLite data through a read-only URI and
does not import the MT5 package, build broker requests, call order APIs, mutate the
database, or modify execution configuration.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts import run_fixed_candidate_train_only_threshold_oos_outcome_replay as base


DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "exit_policy_comparison"
DEFAULT_STRATEGY_SPEC = (
    BASE_DIR / "config" / "strategy_specs" / "gbpusd_short_h10_1_5_off_hours_strategy_spec.json"
)

STATUS_AVAILABLE = "exit_policy_comparison_available"
STATUS_MISSING_THRESHOLD = "exit_policy_comparison_blocked_missing_threshold_artifact"
STATUS_NON_TRAIN_ONLY = "exit_policy_comparison_blocked_non_train_only_thresholds"
STATUS_MISSING_DB = "exit_policy_comparison_blocked_missing_db"
STATUS_MISSING_TABLE = "exit_policy_comparison_blocked_missing_table"
STATUS_MISSING_COLUMNS = "exit_policy_comparison_blocked_missing_columns"
STATUS_EMPTY_OOS = "exit_policy_comparison_blocked_empty_oos_window"
STATUS_NONCANONICAL = "exit_policy_comparison_blocked_noncanonical_candidate"
STATUS_OUTPUT_EXISTS = "exit_policy_comparison_blocked_output_exists_without_overwrite"

SUMMARY_FILE = "exit_policy_summary.csv"
BY_MONTH_FILE = "exit_policy_by_month.csv"
BY_QUARTER_FILE = "exit_policy_by_quarter.csv"
TRADES_FILE = "exit_policy_trades.csv"
DRAWDOWN_FILE = "exit_policy_drawdown.csv"
MANIFEST_FILE = "exit_policy_manifest.json"
BY_YEAR_FILE = "exit_policy_by_year.csv"
WALK_FORWARD_FILE = "exit_policy_walk_forward_blocks.csv"

OUTPUT_FILES = {
    "summary": SUMMARY_FILE,
    "by_month": BY_MONTH_FILE,
    "by_quarter": BY_QUARTER_FILE,
    "trades": TRADES_FILE,
    "drawdown": DRAWDOWN_FILE,
    "manifest": MANIFEST_FILE,
    "by_year": BY_YEAR_FILE,
    "walk_forward_blocks": WALK_FORWARD_FILE,
}

FRIDAY_FORCED_FLAT = time(23, 45)
PIP_SIZE = 0.0001

NO_ORDER_EVIDENCE = {
    "no_mt5_import_performed": True,
    "no_mt5_connection_performed": True,
    "no_broker_api_query_performed": True,
    "no_order_check_called": True,
    "no_order_send_called": True,
    "no_order_calc_margin_called": True,
    "no_order_calc_profit_called": True,
    "no_positions_get_called": True,
    "no_orders_get_called": True,
    "no_history_orders_get_called": True,
    "no_history_deals_get_called": True,
    "no_order_execution_performed": True,
    "no_broker_payload_constructed": True,
    "no_executable_order_object_constructed": True,
    "no_db_mutation_performed": True,
    "no_future_state_json_written": True,
    "no_child_scripts_executed": True,
    "no_scheduler_added": True,
    "no_loop_added": True,
    "no_background_task_added": True,
    "strategy_spec_not_modified": True,
    "demo_live_config_not_modified": True,
    "ea_not_modified": True,
}

METRIC_FIELDS = [
    "raw_signal_count",
    "skipped_overlap_signal_count",
    "trade_count",
    "win_rate",
    "loss_rate",
    "tp_count",
    "sl_count",
    "time_exit_count",
    "friday_forced_flat_count",
    "open_at_data_end_count",
    "avg_pips",
    "total_pips",
    "avg_R",
    "total_R",
    "expectancy_R",
    "profit_factor",
    "max_drawdown_R",
    "worst_losing_streak",
    "avg_holding_bars",
    "median_holding_bars",
    "max_holding_bars_observed",
    "exposure_time",
    "exposure_time_hours",
    "avg_MAE_R",
    "avg_MFE_R",
    "missed_tp_after_time_exit",
    "would_have_hit_tp_after_time_exit",
    "would_have_hit_sl_after_time_exit",
]

SUMMARY_FIELDS = [
    "run_id",
    "comparison_status",
    "policy_id",
    "policy_description",
    "max_holding_bars_policy",
    "friday_forced_flat_enabled",
    "no_weekend_hold",
    *METRIC_FIELDS,
]

PERIOD_FIELDS = [
    "run_id",
    "policy_id",
    "period",
    "period_start",
    "period_end",
    *METRIC_FIELDS,
]

TRADE_FIELDS = [
    "run_id",
    "policy_id",
    "trade_index",
    "raw_signal_index",
    "signal_id",
    "entry_row_index",
    "exit_row_index",
    "entry_time_server",
    "exit_time_server",
    "entry_price",
    "exit_price",
    "tp_price",
    "sl_price",
    "direction",
    "exit_reason",
    "R_multiple",
    "pips",
    "holding_bars",
    "max_holding_bars_policy",
    "friday_forced_flat_enabled",
    "no_weekend_hold",
    "same_bar_policy",
    "same_bar_conflict",
    "spread",
    base.FEATURE_A,
    f"{base.FEATURE_A}_bucket",
    base.FEATURE_B,
    f"{base.FEATURE_B}_bucket",
    "MAE_R",
    "MFE_R",
    "missed_tp_after_time_exit",
    "would_have_hit_tp_after_time_exit",
    "would_have_hit_sl_after_time_exit",
    "censored_at_data_end",
]

DRAWDOWN_FIELDS = [
    "run_id",
    "policy_id",
    "trade_index",
    "signal_id",
    "entry_time_server",
    "exit_time_server",
    "exit_reason",
    "R_multiple",
    "cumulative_R",
    "peak_cumulative_R",
    "drawdown_R",
]


@dataclass(frozen=True)
class ExitPolicy:
    policy_id: str
    description: str
    max_holding_bars: int | None
    friday_forced_flat: bool
    no_weekend_hold: bool


DEFAULT_POLICIES = (
    ExitPolicy(
        policy_id="current_10_bars",
        description="SL/TP plus max_holding_bars=10 plus Friday forced flat/no weekend",
        max_holding_bars=10,
        friday_forced_flat=True,
        no_weekend_hold=True,
    ),
    ExitPolicy(
        policy_id="tp_sl_friday_only",
        description="SL/TP plus Friday forced flat/no weekend, no time exit",
        max_holding_bars=None,
        friday_forced_flat=True,
        no_weekend_hold=True,
    ),
    ExitPolicy(
        policy_id="tp_sl_only_research",
        description="SL/TP only research benchmark, no time exit and no Friday forced flat",
        max_holding_bars=None,
        friday_forced_flat=False,
        no_weekend_hold=False,
    ),
    ExitPolicy(
        policy_id="max_holding_20",
        description="SL/TP plus max_holding_bars=20 plus Friday forced flat/no weekend",
        max_holding_bars=20,
        friday_forced_flat=True,
        no_weekend_hold=True,
    ),
    ExitPolicy(
        policy_id="max_holding_30",
        description="SL/TP plus max_holding_bars=30 plus Friday forced flat/no weekend",
        max_holding_bars=30,
        friday_forced_flat=True,
        no_weekend_hold=True,
    ),
    ExitPolicy(
        policy_id="max_holding_40",
        description="SL/TP plus max_holding_bars=40 plus Friday forced flat/no weekend",
        max_holding_bars=40,
        friday_forced_flat=True,
        no_weekend_hold=True,
    ),
)

EXTENDED_POLICIES = (
    ExitPolicy(
        policy_id="max_holding_48",
        description="SL/TP plus max_holding_bars=48 plus Friday forced flat/no weekend",
        max_holding_bars=48,
        friday_forced_flat=True,
        no_weekend_hold=True,
    ),
    ExitPolicy(
        policy_id="max_holding_96",
        description="SL/TP plus max_holding_bars=96 plus Friday forced flat/no weekend",
        max_holding_bars=96,
        friday_forced_flat=True,
        no_weekend_hold=True,
    ),
)


@dataclass(frozen=True)
class BlockedStatusError(Exception):
    status: str
    message: str

    def __str__(self) -> str:
        return f"{self.status}: {self.message}"


def current_run_id() -> str:
    return datetime.now().strftime("gbpusd_exit_policy_comparison_%Y%m%d_%H%M%S")


def output_dir_for_args(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    return Path(args.output_root) / str(args.run_id)


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {label: output_dir / file_name for label, file_name in OUTPUT_FILES.items()}


def ensure_output_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = output_paths(output_dir)
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise BlockedStatusError(STATUS_OUTPUT_EXISTS, "Output files already exist; use --overwrite.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: base.csv_value(row.get(field)) for field in fieldnames})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def timeframe_minutes(timeframe: str) -> int:
    normalized = str(timeframe or "").strip().upper()
    if normalized == "M15":
        return 15
    if normalized.startswith("M") and normalized[1:].isdigit():
        return int(normalized[1:])
    if normalized.startswith("H") and normalized[1:].isdigit():
        return int(normalized[1:]) * 60
    if normalized.startswith("D") and normalized[1:].isdigit():
        return int(normalized[1:]) * 1440
    raise ValueError(f"Unsupported timeframe: {timeframe!r}")


def finite_float(value: Any) -> float | None:
    parsed = base.safe_float(value)
    if parsed is None or not math.isfinite(parsed):
        return None
    return parsed


def parse_server_time(value: Any) -> datetime | None:
    return base.parse_time_text(str(value or ""))


def is_friday_forced_flat_due(entry_time: datetime | None, row_time: datetime | None) -> bool:
    if entry_time is None or row_time is None:
        return False
    if row_time < entry_time:
        return False
    return row_time.weekday() == 4 and row_time.time() >= FRIDAY_FORCED_FLAT


def short_r(entry_price: float, exit_price: float, sl_price: float) -> float | None:
    risk = sl_price - entry_price
    if risk <= 0:
        return None
    return (entry_price - exit_price) / risk


def short_pips(entry_price: float, exit_price: float) -> float:
    return (entry_price - exit_price) / PIP_SIZE


def barrier_hit_after_exit(
    rows: list[dict[str, Any]],
    *,
    exit_row_index: int,
    tp_price: float,
    sl_price: float,
) -> str:
    for future_row in rows[exit_row_index + 1 :]:
        low = finite_float(future_row.get("low"))
        high = finite_float(future_row.get("high"))
        if low is None or high is None:
            continue
        tp_hit = low <= tp_price
        sl_hit = high >= sl_price
        if tp_hit and sl_hit:
            return "sl"
        if sl_hit:
            return "sl"
        if tp_hit:
            return "tp"
    return ""


def row_exit_record(
    *,
    run_id: str,
    policy: ExitPolicy,
    trade_index: int,
    raw_signal_index: int,
    signal_id: str,
    entry_index: int,
    exit_index: int,
    entry: dict[str, Any],
    exit_row: dict[str, Any],
    gate: dict[str, Any],
    entry_price: float,
    exit_price: float,
    tp_price: float,
    sl_price: float,
    exit_reason: str,
    holding_bars: int,
    same_bar_conflict: bool,
    mae_r: float,
    mfe_r: float,
    censored_at_data_end: bool,
) -> dict[str, Any]:
    r_multiple = short_r(entry_price, exit_price, sl_price)
    return {
        "run_id": run_id,
        "policy_id": policy.policy_id,
        "trade_index": trade_index,
        "raw_signal_index": raw_signal_index,
        "signal_id": signal_id,
        "entry_row_index": entry_index,
        "exit_row_index": exit_index,
        "entry_time_server": entry.get("time_server", ""),
        "exit_time_server": exit_row.get("time_server", ""),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "direction": base.DEFAULT_DIRECTION,
        "exit_reason": exit_reason,
        "R_multiple": r_multiple,
        "pips": short_pips(entry_price, exit_price),
        "holding_bars": holding_bars,
        "max_holding_bars_policy": policy.max_holding_bars,
        "friday_forced_flat_enabled": policy.friday_forced_flat,
        "no_weekend_hold": policy.no_weekend_hold,
        "same_bar_policy": base.SAME_BAR_POLICY,
        "same_bar_conflict": same_bar_conflict,
        "spread": gate["spread"],
        base.FEATURE_A: gate["feature_a"],
        f"{base.FEATURE_A}_bucket": gate["bucket_a"],
        base.FEATURE_B: gate["feature_b"],
        f"{base.FEATURE_B}_bucket": gate["bucket_b"],
        "MAE_R": mae_r,
        "MFE_R": mfe_r,
        "missed_tp_after_time_exit": False,
        "would_have_hit_tp_after_time_exit": False,
        "would_have_hit_sl_after_time_exit": False,
        "censored_at_data_end": censored_at_data_end,
    }


def simulate_trade_for_policy(
    *,
    rows: list[dict[str, Any]],
    entry_index: int,
    gate: dict[str, Any],
    policy: ExitPolicy,
    run_id: str,
    signal_id: str,
    trade_index: int,
    raw_signal_index: int,
    warnings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    entry = rows[entry_index]
    entry_price = finite_float(entry.get("close"))
    atr = finite_float(entry.get(base.ATR_COLUMN))
    if entry_price is None or atr is None or atr <= 0:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="invalid_entry_price_or_atr",
                message="A matching entry row had invalid close or ATR and was skipped.",
                source=entry.get("time_server", ""),
                blocking_warning=False,
            )
        )
        return None

    tp_price = entry_price - base.TP_ATR * atr
    sl_price = entry_price + base.SL_ATR * atr
    risk = sl_price - entry_price
    if risk <= 0:
        return None

    entry_time = parse_server_time(entry.get("time_server"))
    mae_r = 0.0
    mfe_r = 0.0
    last_exit_candidate: tuple[int, int, dict[str, Any], float] | None = None

    for offset, path_row in enumerate(rows[entry_index + 1 :], start=1):
        path_index = entry_index + offset
        low = finite_float(path_row.get("low"))
        high = finite_float(path_row.get("high"))
        close = finite_float(path_row.get("close"))
        if low is None or high is None:
            warnings.append(
                base.warning_row(
                    run_id=run_id,
                    warning_code="missing_future_ohlc",
                    message="Future path row had missing high/low; trade path was censored at prior data.",
                    source=path_row.get("time_server", ""),
                    blocking_warning=False,
                )
            )
            break
        if close is not None:
            last_exit_candidate = (path_index, offset, path_row, close)

        mae_r = max(mae_r, max(0.0, high - entry_price) / risk)
        mfe_r = max(mfe_r, max(0.0, entry_price - low) / risk)
        tp_hit = low <= tp_price
        sl_hit = high >= sl_price
        same_bar_conflict = tp_hit and sl_hit
        exit_reason = ""
        exit_price: float | None = None

        if same_bar_conflict:
            exit_reason = "sl"
            exit_price = sl_price
            warnings.append(
                base.warning_row(
                    run_id=run_id,
                    warning_code="same_bar_stop_first_applied",
                    message="TP and SL touched inside the same bar; stop_first policy selected SL.",
                    source=path_row.get("time_server", ""),
                    blocking_warning=False,
                )
            )
        elif sl_hit:
            exit_reason = "sl"
            exit_price = sl_price
        elif tp_hit:
            exit_reason = "tp"
            exit_price = tp_price
        elif (
            policy.friday_forced_flat
            and close is not None
            and is_friday_forced_flat_due(entry_time, parse_server_time(path_row.get("time_server")))
        ):
            exit_reason = "friday_forced_flat"
            exit_price = close
        elif policy.max_holding_bars is not None and offset >= policy.max_holding_bars and close is not None:
            exit_reason = "time_exit"
            exit_price = close

        if exit_reason and exit_price is not None:
            trade = row_exit_record(
                run_id=run_id,
                policy=policy,
                trade_index=trade_index,
                raw_signal_index=raw_signal_index,
                signal_id=signal_id,
                entry_index=entry_index,
                exit_index=path_index,
                entry=entry,
                exit_row=path_row,
                gate=gate,
                entry_price=entry_price,
                exit_price=exit_price,
                tp_price=tp_price,
                sl_price=sl_price,
                exit_reason=exit_reason,
                holding_bars=offset,
                same_bar_conflict=same_bar_conflict,
                mae_r=mae_r,
                mfe_r=mfe_r,
                censored_at_data_end=False,
            )
            if exit_reason == "time_exit":
                later_hit = barrier_hit_after_exit(rows, exit_row_index=path_index, tp_price=tp_price, sl_price=sl_price)
                trade["would_have_hit_tp_after_time_exit"] = later_hit == "tp"
                trade["would_have_hit_sl_after_time_exit"] = later_hit == "sl"
                trade["missed_tp_after_time_exit"] = later_hit == "tp"
            return trade

    if last_exit_candidate is None:
        return None
    exit_index, holding_bars, exit_row, exit_price = last_exit_candidate
    return row_exit_record(
        run_id=run_id,
        policy=policy,
        trade_index=trade_index,
        raw_signal_index=raw_signal_index,
        signal_id=signal_id,
        entry_index=entry_index,
        exit_index=exit_index,
        entry=entry,
        exit_row=exit_row,
        gate=gate,
        entry_price=entry_price,
        exit_price=exit_price,
        tp_price=tp_price,
        sl_price=sl_price,
        exit_reason="open_at_data_end",
        holding_bars=holding_bars,
        same_bar_conflict=False,
        mae_r=mae_r,
        mfe_r=mfe_r,
        censored_at_data_end=True,
    )


def replay_policy_rows(
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    cutoffs: dict[str, dict[str, float]],
    policy: ExitPolicy,
    warnings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    trades: list[dict[str, Any]] = []
    raw_signal_count = 0
    skipped_overlap_count = 0
    active_exit_index: int | None = None

    for index, row in enumerate(rows):
        gate = base.entry_gate(row, cutoffs, args)
        if not gate["rule_match"]:
            continue
        raw_signal_count += 1
        signal_id = f"{args.run_id}_signal_{raw_signal_count:06d}"
        if active_exit_index is not None and index <= active_exit_index:
            skipped_overlap_count += 1
            continue
        trade = simulate_trade_for_policy(
            rows=rows,
            entry_index=index,
            gate=gate,
            policy=policy,
            run_id=str(args.run_id),
            signal_id=signal_id,
            trade_index=len(trades) + 1,
            raw_signal_index=raw_signal_count,
            warnings=warnings,
        )
        if trade is None:
            continue
        active_exit_index = int(trade["exit_row_index"])
        trades.append(trade)

    return trades, raw_signal_count, skipped_overlap_count


def profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if not values or losses == 0:
        return None
    return gains / losses


def max_drawdown(values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return drawdown


def worst_losing_streak(values: list[float]) -> int:
    worst = 0
    current = 0
    for value in values:
        if value < 0:
            current += 1
            worst = max(worst, current)
        else:
            current = 0
    return worst


def bool_count(rows: list[dict[str, Any]], field: str) -> int:
    return sum(1 for row in rows if bool(row.get(field)))


def metrics_for_trades(
    trades: list[dict[str, Any]],
    *,
    raw_signal_count: int | None = None,
    skipped_overlap_count: int | None = None,
    timeframe: str = base.DEFAULT_TIMEFRAME,
) -> dict[str, Any]:
    values = [value for trade in trades if (value := finite_float(trade.get("R_multiple"))) is not None]
    pips = [value for trade in trades if (value := finite_float(trade.get("pips"))) is not None]
    holding = [int(float(trade.get("holding_bars") or 0)) for trade in trades]
    mae_values = [value for trade in trades if (value := finite_float(trade.get("MAE_R"))) is not None]
    mfe_values = [value for trade in trades if (value := finite_float(trade.get("MFE_R"))) is not None]
    count = len(values)
    minutes = timeframe_minutes(timeframe)
    exposure_hours = sum(holding) * minutes / 60.0
    total_r = sum(values) if values else None
    return {
        "raw_signal_count": raw_signal_count,
        "skipped_overlap_signal_count": skipped_overlap_count,
        "trade_count": count,
        "win_rate": (sum(1 for value in values if value > 0) / count) if count else None,
        "loss_rate": (sum(1 for value in values if value < 0) / count) if count else None,
        "tp_count": sum(1 for trade in trades if trade.get("exit_reason") == "tp"),
        "sl_count": sum(1 for trade in trades if trade.get("exit_reason") == "sl"),
        "time_exit_count": sum(1 for trade in trades if trade.get("exit_reason") == "time_exit"),
        "friday_forced_flat_count": sum(1 for trade in trades if trade.get("exit_reason") == "friday_forced_flat"),
        "open_at_data_end_count": sum(1 for trade in trades if trade.get("exit_reason") == "open_at_data_end"),
        "avg_pips": (sum(pips) / len(pips)) if pips else None,
        "total_pips": sum(pips) if pips else None,
        "avg_R": (sum(values) / count) if count else None,
        "total_R": total_r,
        "expectancy_R": (sum(values) / count) if count else None,
        "profit_factor": profit_factor(values),
        "max_drawdown_R": max_drawdown(values),
        "worst_losing_streak": worst_losing_streak(values),
        "avg_holding_bars": (sum(holding) / len(holding)) if holding else None,
        "median_holding_bars": statistics.median(holding) if holding else None,
        "max_holding_bars_observed": max(holding) if holding else None,
        "exposure_time": exposure_hours,
        "exposure_time_hours": exposure_hours,
        "avg_MAE_R": (sum(mae_values) / len(mae_values)) if mae_values else None,
        "avg_MFE_R": (sum(mfe_values) / len(mfe_values)) if mfe_values else None,
        "missed_tp_after_time_exit": bool_count(trades, "missed_tp_after_time_exit"),
        "would_have_hit_tp_after_time_exit": bool_count(trades, "would_have_hit_tp_after_time_exit"),
        "would_have_hit_sl_after_time_exit": bool_count(trades, "would_have_hit_sl_after_time_exit"),
    }


def summary_row(
    *,
    run_id: str,
    status: str,
    policy: ExitPolicy,
    trades: list[dict[str, Any]],
    raw_signal_count: int,
    skipped_overlap_count: int,
    timeframe: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "comparison_status": status,
        "policy_id": policy.policy_id,
        "policy_description": policy.description,
        "max_holding_bars_policy": policy.max_holding_bars,
        "friday_forced_flat_enabled": policy.friday_forced_flat,
        "no_weekend_hold": policy.no_weekend_hold,
        **metrics_for_trades(
            trades,
            raw_signal_count=raw_signal_count,
            skipped_overlap_count=skipped_overlap_count,
            timeframe=timeframe,
        ),
    }


def drawdown_rows(run_id: str, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cumulative = 0.0
    peak = 0.0
    rows: list[dict[str, Any]] = []
    for trade in trades:
        value = finite_float(trade.get("R_multiple"))
        if value is None:
            continue
        cumulative += value
        peak = max(peak, cumulative)
        rows.append(
            {
                "run_id": run_id,
                "policy_id": trade.get("policy_id", ""),
                "trade_index": trade.get("trade_index", ""),
                "signal_id": trade.get("signal_id", ""),
                "entry_time_server": trade.get("entry_time_server", ""),
                "exit_time_server": trade.get("exit_time_server", ""),
                "exit_reason": trade.get("exit_reason", ""),
                "R_multiple": value,
                "cumulative_R": cumulative,
                "peak_cumulative_R": peak,
                "drawdown_R": peak - cumulative,
            }
        )
    return rows


def period_label(timestamp: datetime, period: str) -> tuple[str, datetime, datetime]:
    if period == "year":
        start = datetime(timestamp.year, 1, 1)
        end = datetime(timestamp.year, 12, 31, 23, 59, 59)
        return str(timestamp.year), start, end
    if period == "quarter":
        quarter = (timestamp.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start = datetime(timestamp.year, start_month, 1)
        end = add_months(start, 3) - timedelta(seconds=1)
        return f"{timestamp.year}-Q{quarter}", start, end
    if period == "month":
        start = datetime(timestamp.year, timestamp.month, 1)
        end = add_months(start, 1) - timedelta(seconds=1)
        return f"{timestamp.year}-{timestamp.month:02d}", start, end
    raise ValueError(f"Unsupported period: {period}")


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def period_breakdown_rows(
    *,
    run_id: str,
    trades_by_policy: dict[str, list[dict[str, Any]]],
    period: str,
    timeframe: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for policy_id, trades in sorted(trades_by_policy.items()):
        grouped: dict[str, tuple[datetime, datetime, list[dict[str, Any]]]] = {}
        for trade in trades:
            timestamp = parse_server_time(trade.get("entry_time_server"))
            if timestamp is None:
                continue
            label, start, end = period_label(timestamp, period)
            if label not in grouped:
                grouped[label] = (start, end, [])
            grouped[label][2].append(trade)
        for label in sorted(grouped):
            start, end, grouped_trades = grouped[label]
            output.append(
                {
                    "run_id": run_id,
                    "policy_id": policy_id,
                    "period": label,
                    "period_start": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "period_end": end.strftime("%Y-%m-%d %H:%M:%S"),
                    **metrics_for_trades(grouped_trades, timeframe=timeframe),
                }
            )
    return output


def walk_forward_label(
    timestamp: datetime,
    *,
    anchor: datetime,
    block_months: int,
) -> tuple[str, datetime, datetime]:
    month_delta = (timestamp.year - anchor.year) * 12 + (timestamp.month - anchor.month)
    block_index = max(0, month_delta // block_months)
    start = add_months(datetime(anchor.year, anchor.month, 1), block_index * block_months)
    end = add_months(start, block_months) - timedelta(seconds=1)
    return f"wf_block_{block_index + 1:03d}", start, end


def walk_forward_rows(
    *,
    run_id: str,
    trades_by_policy: dict[str, list[dict[str, Any]]],
    anchor_time: str,
    block_months: int,
    timeframe: str,
) -> list[dict[str, Any]]:
    anchor = parse_server_time(anchor_time) or datetime(2025, 1, 1)
    output: list[dict[str, Any]] = []
    for policy_id, trades in sorted(trades_by_policy.items()):
        grouped: dict[str, tuple[datetime, datetime, list[dict[str, Any]]]] = {}
        for trade in trades:
            timestamp = parse_server_time(trade.get("entry_time_server"))
            if timestamp is None:
                continue
            label, start, end = walk_forward_label(timestamp, anchor=anchor, block_months=block_months)
            if label not in grouped:
                grouped[label] = (start, end, [])
            grouped[label][2].append(trade)
        for label in sorted(grouped):
            start, end, grouped_trades = grouped[label]
            output.append(
                {
                    "run_id": run_id,
                    "policy_id": policy_id,
                    "period": label,
                    "period_start": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "period_end": end.strftime("%Y-%m-%d %H:%M:%S"),
                    **metrics_for_trades(grouped_trades, timeframe=timeframe),
                }
            )
    return output


def selected_policies(include_extended: bool) -> tuple[ExitPolicy, ...]:
    if include_extended:
        return (*DEFAULT_POLICIES, *EXTENDED_POLICIES)
    return DEFAULT_POLICIES


def derive_status(
    *,
    threshold_missing: bool,
    non_train_only: bool,
    noncanonical: bool,
    db_exists: bool,
    table_exists: bool,
    missing_columns: list[str],
    oos_row_count: int,
) -> str:
    if threshold_missing:
        return STATUS_MISSING_THRESHOLD
    if noncanonical:
        return STATUS_NONCANONICAL
    if non_train_only:
        return STATUS_NON_TRAIN_ONLY
    if not db_exists:
        return STATUS_MISSING_DB
    if not table_exists:
        return STATUS_MISSING_TABLE
    if missing_columns:
        return STATUS_MISSING_COLUMNS
    if oos_row_count == 0:
        return STATUS_EMPTY_OOS
    return STATUS_AVAILABLE


def build_model(args: argparse.Namespace) -> dict[str, Any]:
    run_id = str(args.run_id)
    threshold_path = Path(args.train_only_thresholds)
    canonical_path = Path(args.canonical_registry)
    strategy_spec_path = Path(args.strategy_spec)
    db_path = Path(args.db_path)
    threshold_payload, threshold_error = base.read_json_object(threshold_path)
    canonical_payload, canonical_error = base.read_json_object(canonical_path)
    warnings: list[dict[str, Any]] = []

    if threshold_error:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="missing_threshold_artifact",
                message=f"Train-only threshold artifact missing or unreadable: {threshold_error}",
                source=threshold_path,
                blocking_warning=True,
            )
        )
    non_train_errors, threshold_noncanonical = (
        base.threshold_validation_errors(threshold_payload, args) if threshold_payload else ([], [])
    )
    if non_train_errors:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="non_train_only_thresholds",
                message="Threshold artifact failed train-only checks: " + ", ".join(non_train_errors),
                source=threshold_path,
                blocking_warning=True,
            )
        )
    canonical_errors = base.canonical_mismatches(args, canonical_payload, canonical_error)
    noncanonical_items = [*threshold_noncanonical, *canonical_errors]
    if noncanonical_items:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="noncanonical_candidate",
                message="Candidate identity/config checks failed: " + ", ".join(noncanonical_items),
                source=f"{threshold_path};{canonical_path}",
                blocking_warning=True,
            )
        )

    db_exists = db_path.exists()
    table_exists = False
    columns: set[str] = set()
    schema_error = ""
    if db_exists:
        table_exists, columns, schema_error = base.inspect_table(db_path, str(args.feature_table))
    else:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="missing_db",
                message="Configured SQLite DB does not exist.",
                source=db_path,
                blocking_warning=True,
            )
        )
    if db_exists and not table_exists:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="missing_table",
                message=f"Feature table missing or unreadable: {schema_error}",
                source=args.feature_table,
                blocking_warning=True,
            )
        )
    missing_columns = sorted(base.required_columns(args) - columns) if table_exists else []
    if missing_columns:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="missing_columns",
                message="Feature table is missing required columns: " + ", ".join(missing_columns),
                source=args.feature_table,
                blocking_warning=True,
            )
        )

    train_end_time = str(threshold_payload.get("train_end_time") or "")
    oos_start_time = str(args.oos_start_time or "")
    oos_end_time = str(args.oos_end_time or "")
    source_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    oos_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    offhours_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    rows: list[dict[str, Any]] = []
    cutoffs = base.threshold_cutoffs(threshold_payload) if threshold_payload else {}
    can_query = (
        db_exists
        and table_exists
        and not missing_columns
        and not threshold_error
        and not non_train_errors
        and not noncanonical_items
        and bool(train_end_time)
        and bool(cutoffs)
    )
    if can_query:
        with base.connect_read_only(db_path) as connection:
            source_filters, source_params = base.source_filters(args, columns)
            source_info = base.one_row_window_query(
                connection=connection,
                table_name=str(args.feature_table),
                filters=source_filters,
                params=source_params,
            )
            if not oos_end_time:
                oos_end_time = source_info["max_time_server"]
            if not oos_start_time:
                first_filters = [*source_filters, f"{base.quote_identifier('time_server')} > ?"]
                first_params = [*source_params, train_end_time]
                first_info = base.one_row_window_query(
                    connection=connection,
                    table_name=str(args.feature_table),
                    filters=first_filters,
                    params=first_params,
                )
                oos_start_time = first_info["min_time_server"] or base.plus_one_second_text(train_end_time)
            oos_filters = [
                *source_filters,
                f"{base.quote_identifier('time_server')} > ?",
                f"{base.quote_identifier('time_server')} >= ?",
            ]
            oos_params: list[Any] = [*source_params, train_end_time, oos_start_time]
            if oos_end_time:
                oos_filters.append(f"{base.quote_identifier('time_server')} <= ?")
                oos_params.append(oos_end_time)
            oos_info = base.one_row_window_query(
                connection=connection,
                table_name=str(args.feature_table),
                filters=oos_filters,
                params=oos_params,
            )
            off_filters = [*oos_filters, f"{base.quote_identifier(str(args.session_column))} = ?"]
            off_params = [*oos_params, str(args.required_session)]
            offhours_info = base.one_row_window_query(
                connection=connection,
                table_name=str(args.feature_table),
                filters=off_filters,
                params=off_params,
            )
            rows = base.fetch_price_rows(
                connection=connection,
                table_name=str(args.feature_table),
                columns=columns,
                filters=oos_filters,
                params=oos_params,
                session_column=str(args.session_column),
            )
    if can_query and int(oos_info["row_count"] or 0) == 0:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="empty_oos_window",
                message="No OOS rows were available after train_end_time.",
                source=args.feature_table,
                blocking_warning=True,
            )
        )

    status = derive_status(
        threshold_missing=bool(threshold_error),
        non_train_only=bool(non_train_errors),
        noncanonical=bool(noncanonical_items),
        db_exists=db_exists,
        table_exists=table_exists,
        missing_columns=missing_columns,
        oos_row_count=int(oos_info["row_count"] or 0),
    )

    trades_by_policy: dict[str, list[dict[str, Any]]] = {}
    raw_signal_counts: dict[str, int] = {}
    skipped_overlap_counts: dict[str, int] = {}
    if status == STATUS_AVAILABLE:
        for policy in selected_policies(bool(args.include_extended_holdings)):
            trades, raw_signal_count, skipped_overlap_count = replay_policy_rows(
                args=args,
                rows=rows,
                cutoffs=cutoffs,
                policy=policy,
                warnings=warnings,
            )
            trades_by_policy[policy.policy_id] = trades
            raw_signal_counts[policy.policy_id] = raw_signal_count
            skipped_overlap_counts[policy.policy_id] = skipped_overlap_count

    policies = selected_policies(bool(args.include_extended_holdings))
    summary_rows = [
        summary_row(
            run_id=run_id,
            status=status,
            policy=policy,
            trades=trades_by_policy.get(policy.policy_id, []),
            raw_signal_count=raw_signal_counts.get(policy.policy_id, 0),
            skipped_overlap_count=skipped_overlap_counts.get(policy.policy_id, 0),
            timeframe=str(args.timeframe),
        )
        for policy in policies
    ]
    all_trades = [trade for policy in policies for trade in trades_by_policy.get(policy.policy_id, [])]
    all_drawdown_rows = [
        row
        for policy in policies
        for row in drawdown_rows(run_id, trades_by_policy.get(policy.policy_id, []))
    ]

    output_files: dict[str, str] = {}
    manifest = {
        "run_id": run_id,
        "comparison_status": status,
        "candidate_id": base.EXPECTED_CANDIDATE_ID,
        "symbol": str(args.symbol),
        "timeframe": str(args.timeframe),
        "direction": base.DEFAULT_DIRECTION,
        "train_only_threshold_artifact": str(threshold_path),
        "threshold_lineage": threshold_payload.get("threshold_lineage", ""),
        "calibration_scope": threshold_payload.get("calibration_scope", ""),
        "train_end_time": train_end_time,
        "oos_start_time": oos_start_time,
        "oos_end_time": oos_end_time,
        "source_row_count": source_info["row_count"],
        "source_min_time_server": source_info["min_time_server"],
        "source_max_time_server": source_info["max_time_server"],
        "oos_row_count": oos_info["row_count"],
        "off_hours_oos_row_count": offhours_info["row_count"],
        "tp_atr": base.TP_ATR,
        "sl_atr": base.SL_ATR,
        "same_bar_policy": base.SAME_BAR_POLICY,
        "max_spread_points": float(args.max_spread_points),
        "feature_table": str(args.feature_table),
        "db_path": str(db_path),
        "strategy_spec": str(strategy_spec_path),
        "walk_forward_block_months": int(args.walk_forward_block_months),
        "policies": [policy.__dict__ for policy in policies],
        "raw_signal_counts_by_policy": raw_signal_counts,
        "skipped_overlap_counts_by_policy": skipped_overlap_counts,
        "missing_required_columns": missing_columns,
        "canonical_registry_sha256": (
            base.sha256_file(canonical_path) if canonical_path.exists() and not canonical_error else ""
        ),
        "threshold_artifact_sha256": (
            base.sha256_file(threshold_path) if threshold_path.exists() and not threshold_error else ""
        ),
        "strategy_spec_sha256": base.sha256_file(strategy_spec_path) if strategy_spec_path.exists() else "",
        "warnings": warnings,
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(bool(warning["blocking_warning"]) for warning in warnings),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_files": output_files,
        **NO_ORDER_EVIDENCE,
    }
    return {
        "manifest": manifest,
        "summary": summary_rows,
        "by_month": period_breakdown_rows(
            run_id=run_id,
            trades_by_policy=trades_by_policy,
            period="month",
            timeframe=str(args.timeframe),
        ),
        "by_quarter": period_breakdown_rows(
            run_id=run_id,
            trades_by_policy=trades_by_policy,
            period="quarter",
            timeframe=str(args.timeframe),
        ),
        "by_year": period_breakdown_rows(
            run_id=run_id,
            trades_by_policy=trades_by_policy,
            period="year",
            timeframe=str(args.timeframe),
        ),
        "walk_forward_blocks": walk_forward_rows(
            run_id=run_id,
            trades_by_policy=trades_by_policy,
            anchor_time=oos_start_time,
            block_months=int(args.walk_forward_block_months),
            timeframe=str(args.timeframe),
        ),
        "trades": all_trades,
        "drawdown": all_drawdown_rows,
    }


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for_args(args)
    paths = ensure_output_writable(output_dir, bool(args.overwrite))
    model = build_model(args)
    model["manifest"]["output_files"] = {label: str(path) for label, path in paths.items()}
    write_csv(paths["summary"], model["summary"], SUMMARY_FIELDS)
    write_csv(paths["by_month"], model["by_month"], PERIOD_FIELDS)
    write_csv(paths["by_quarter"], model["by_quarter"], PERIOD_FIELDS)
    write_csv(paths["by_year"], model["by_year"], PERIOD_FIELDS)
    write_csv(paths["walk_forward_blocks"], model["walk_forward_blocks"], PERIOD_FIELDS)
    write_csv(paths["trades"], model["trades"], TRADE_FIELDS)
    write_csv(paths["drawdown"], model["drawdown"], DRAWDOWN_FIELDS)
    write_json(paths["manifest"], model["manifest"])
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare offline exit policies for the fixed GBPUSD candidate without touching MT5 execution."
    )
    parser.add_argument("--run-id", default=current_run_id())
    parser.add_argument("--db-path", type=Path, default=base.DEFAULT_DB_PATH)
    parser.add_argument("--feature-table", default=base.DEFAULT_FEATURE_TABLE)
    parser.add_argument("--train-only-thresholds", type=Path, default=base.DEFAULT_TRAIN_ONLY_THRESHOLDS)
    parser.add_argument("--canonical-registry", type=Path, default=base.DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--strategy-spec", type=Path, default=DEFAULT_STRATEGY_SPEC)
    parser.add_argument("--symbol", default=base.DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=base.DEFAULT_TIMEFRAME)
    parser.add_argument("--oos-start-time")
    parser.add_argument("--oos-end-time")
    parser.add_argument("--session-column", default=base.DEFAULT_SESSION_COLUMN)
    parser.add_argument("--required-session", default=base.DEFAULT_REQUIRED_SESSION)
    parser.add_argument("--max-spread-points", type=float, default=base.DEFAULT_MAX_SPREAD_POINTS)
    parser.add_argument("--include-extended-holdings", action="store_true")
    parser.add_argument("--walk-forward-block-months", type=int, default=6)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except BlockedStatusError as exc:
        print(f"Exit-policy comparison blocked: {exc}")
        return 1
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Exit-policy comparison failed: {exc}")
        return 1
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    print("Exit-policy comparison complete.")
    print(f"comparison_status: {manifest['comparison_status']}")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0 if manifest["comparison_status"] == STATUS_AVAILABLE else 1


if __name__ == "__main__":
    raise SystemExit(main())



