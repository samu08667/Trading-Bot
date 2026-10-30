"""Build a research-only timeout policy sensitivity diagnostic.

This script reads existing rule-replay and timeout review outputs, then uses
the existing replay trade log as the fixed entry universe. Optional future-bar
inspection is read-only against ``ml_dataset`` and is limited to already
existing h10 timeout entries. It does not rerun candidate discovery, recompute
candidate entries, add filters, change TP/SL settings, optimize horizons, or
provide operational instructions.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import sqlite3
import statistics
import sys
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from research_costs import (
        estimate_total_cost_return,
        fallback_spread_source_for_symbol,
        load_cost_config,
        point_size_for_symbol,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.research_costs import (
        estimate_total_cost_return,
        fallback_spread_source_for_symbol,
        load_cost_config,
        point_size_for_symbol,
    )

try:
    from candidate_audit_schema import (
        add_common_summary_fields,
        forbidden_actions_text,
        next_action_row,
        warning_row,
        with_common_next_action_fields,
        with_common_summary_fields,
        with_common_warning_fields,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.candidate_audit_schema import (
        add_common_summary_fields,
        forbidden_actions_text,
        next_action_row,
        warning_row,
        with_common_next_action_fields,
        with_common_summary_fields,
        with_common_warning_fields,
    )


DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "timeout_policy_sensitivity_review"

REPLAY_STRESS_TRADE_LOG_FILE = "rule_based_trade_log_stress.csv"
REPLAY_BASE_TRADE_LOG_FILE = "rule_based_trade_log_base.csv"
REPLAY_SUMMARY_FILE = "rule_based_backtest_summary.csv"
REPLAY_WARNINGS_FILE = "rule_based_warnings.csv"

TIMEOUT_AUDIT_SUMMARY_FILE = "timeout_fragility_audit_summary.csv"
TIMEOUT_ROOT_SUMMARY_FILE = "timeout_root_cause_summary.csv"
TIMEOUT_SEQUENCE_SUMMARY_FILE = "timeout_sequence_drilldown_summary.csv"

SUMMARY_FILE = "timeout_policy_sensitivity_summary.csv"
REPORT_FILE = "timeout_policy_sensitivity_report.md"
WARNINGS_FILE = "timeout_policy_sensitivity_warnings.csv"
MODES_FILE = "timeout_policy_sensitivity_modes.csv"
TIMEOUT_TRADES_FILE = "timeout_policy_sensitivity_timeout_trades.csv"
EXTENDED_HORIZONS_FILE = "timeout_policy_sensitivity_extended_horizons.csv"
EXIT_TRANSITION_FILE = "timeout_policy_sensitivity_exit_transition.csv"
NEXT_ACTIONS_FILE = "timeout_policy_sensitivity_next_actions.csv"

OUTPUT_FILES = (
    SUMMARY_FILE,
    REPORT_FILE,
    WARNINGS_FILE,
    MODES_FILE,
    TIMEOUT_TRADES_FILE,
    EXTENDED_HORIZONS_FILE,
    EXIT_TRANSITION_FILE,
    NEXT_ACTIONS_FILE,
)

CLEARED_LABEL = "TIMEOUT_POLICY_SENSITIVITY_CLEARED_FOR_LIMITED_BASELINE_COST_REVIEW"
RETAINED_LABEL = "TIMEOUT_POLICY_SENSITIVITY_RETAINED_FOR_TIMEOUT_REVIEW"
REJECTED_LABEL = "TIMEOUT_POLICY_SENSITIVITY_REJECTED"

EXTENDED_HORIZON_CAPS = (20, 40, 80)
STRESS_SPREAD_POLICY_STANDARD = "standard"
STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK = "max_row_or_fallback"
STRESS_SPREAD_POLICY_FALLBACK_OVERRIDE = "fallback_override"

TIMEOUT_LOSS_SMALL_RATIO_MAX = 0.05
EXTENDED_SL_DOMINANCE_RATE = 0.70
EXTENDED_WORSE_TIMEOUT_RATIO = 0.05
EXTENDED_DRAWDOWN_REVIEW_RATIO = 0.05
EXTENDED_DRAWDOWN_BLOCKING_RATIO = 0.10

FORBIDDEN_ACTIONS = [
    "live trading",
    "trading signals",
    "broker execution",
    "position sizing",
    "TP/SL optimization",
    "new filters",
    "new feature search",
    "live readiness",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "blocking",
    "message",
    "related_metric",
    "metric_value",
    "threshold",
]
WARNING_FIELDNAMES = with_common_warning_fields(WARNING_FIELDNAMES)

SUMMARY_FIELDNAMES = [
    "run_id",
    "rule_replay_dir",
    "timeout_audit_dir",
    "timeout_root_cause_dir",
    "timeout_sequence_dir",
    "db_path",
    "cost_config",
    "stress_cost_config",
    "stress_spread_policy",
    "output_dir",
    "final_timeout_policy_sensitivity_classification",
    "can_return_to_limited_baseline_cost_review",
    "warnings_count",
    "blocking_warnings_count",
    "symbol",
    "direction",
    "timeframe",
    "horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "feature_condition",
    "tp_atr",
    "sl_atr",
    "atr_column",
    "same_bar_policy",
    "prior_timeout_audit_classification",
    "prior_timeout_root_cause_classification",
    "prior_timeout_sequence_classification",
    "stress_trades",
    "stress_mean_R",
    "stress_profit_factor_R",
    "stress_cumulative_R",
    "stress_max_drawdown_R",
    "stress_timeout_count",
    "stress_timeout_rate",
    "stress_timeout_cumulative_R",
    "stress_timeout_mean_R",
    "timeout_loss_ratio_of_stress_cumulative_R",
    "timeout_excluded_trades",
    "timeout_excluded_mean_R",
    "timeout_excluded_profit_factor_R",
    "timeout_excluded_cumulative_R",
    "extended_h20_tp_rate",
    "extended_h20_sl_rate",
    "extended_h20_still_timeout_rate",
    "extended_h20_timeout_subset_cumulative_R",
    "extended_h20_delta_vs_h10_timeout_R",
    "extended_h40_tp_rate",
    "extended_h40_sl_rate",
    "extended_h40_still_timeout_rate",
    "extended_h40_timeout_subset_cumulative_R",
    "extended_h40_delta_vs_h10_timeout_R",
    "extended_h80_tp_rate",
    "extended_h80_sl_rate",
    "extended_h80_still_timeout_rate",
    "extended_h80_timeout_subset_cumulative_R",
    "extended_h80_delta_vs_h10_timeout_R",
    "max_extended_sl_rate",
    "min_extended_timeout_subset_delta_R",
    "max_replacement_drawdown_delta_R",
    "db_future_path_unavailable_count",
]
SUMMARY_FIELDNAMES = with_common_summary_fields(SUMMARY_FIELDNAMES)

MODE_FIELDNAMES = [
    "mode",
    "scope",
    "horizon_cap",
    "diagnostic_label",
    "trades",
    "trades_retained",
    "trades_excluded",
    "excluded_timeout_share",
    "mean_R",
    "median_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
    "tp_count",
    "tp_rate",
    "sl_count",
    "sl_rate",
    "timeout_count",
    "timeout_rate",
    "timeout_cumulative_R",
    "timeout_mean_R",
    "delta_cumulative_R_vs_current_h10",
    "delta_max_drawdown_R_vs_current_h10",
]

TIMEOUT_TRADE_FIELDNAMES = [
    "timeout_trade_index",
    "stress_trade_index",
    "entry_time",
    "original_exit_time",
    "entry_price",
    "original_exit_price",
    "original_bars_held",
    "original_R",
    "original_cost_R",
    "original_net_R",
    "original_gross_R_proxy",
    "h20_outcome",
    "h20_R",
    "h20_delta_R",
    "h20_additional_bars",
    "h40_outcome",
    "h40_R",
    "h40_delta_R",
    "h40_additional_bars",
    "h80_outcome",
    "h80_R",
    "h80_delta_R",
    "h80_additional_bars",
]

EXTENDED_FIELDNAMES = [
    "horizon_cap",
    "diagnostic_label",
    "timeout_trades_inspected",
    "path_unavailable_count",
    "tp_after_timeout_count",
    "tp_after_timeout_rate",
    "sl_after_timeout_count",
    "sl_after_timeout_rate",
    "still_timeout_count",
    "still_timeout_rate",
    "timeout_subset_mean_R",
    "timeout_subset_cumulative_R",
    "original_h10_timeout_subset_cumulative_R",
    "delta_vs_original_h10_timeout_R",
    "average_additional_bars_held",
    "max_additional_bars_held",
    "replacement_total_trades",
    "replacement_mean_R",
    "replacement_cumulative_R",
    "replacement_profit_factor_R",
    "replacement_max_drawdown_R",
    "replacement_delta_cumulative_R_vs_current_h10",
    "replacement_delta_max_drawdown_R_vs_current_h10",
]

TRANSITION_FIELDNAMES = [
    "horizon_cap",
    "from_exit_reason",
    "to_exit_reason",
    "count",
    "rate",
    "cumulative_R",
    "mean_R",
]

NEXT_ACTION_FIELDNAMES = with_common_next_action_fields(["action_type", "status", "message"])


@dataclass(frozen=True)
class Inputs:
    rule_replay_dir: Path
    timeout_audit_dir: Path
    timeout_root_cause_dir: Path
    timeout_sequence_dir: Path
    replay_summary: dict[str, str]
    replay_warnings: list[dict[str, str]]
    stress_trades: list[dict[str, str]]
    base_trades: list[dict[str, str]]
    timeout_audit_summary: dict[str, str]
    timeout_root_summary: dict[str, str]
    timeout_sequence_summary: dict[str, str]


@dataclass(frozen=True)
class CandidateMeta:
    symbol: str
    direction: str
    timeframe: str
    horizon: int
    target_family: str
    regime_column: str
    regime_value: str
    feature_condition: str
    tp_atr: float
    sl_atr: float
    atr_column: str
    same_bar_policy: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only timeout policy sensitivity diagnostic from existing replay outputs."
    )
    parser.add_argument("--rule-replay-dir", required=True)
    parser.add_argument("--timeout-audit-dir", required=True)
    parser.add_argument("--timeout-root-cause-dir", required=True)
    parser.add_argument("--timeout-sequence-dir", required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--cost-config", required=True)
    parser.add_argument("--stress-cost-config", required=True)
    parser.add_argument(
        "--stress-spread-policy",
        default=STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK,
        choices=(
            STRESS_SPREAD_POLICY_STANDARD,
            STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK,
            STRESS_SPREAD_POLICY_FALLBACK_OVERRIDE,
        ),
    )
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-id")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input file: {path}")
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def first_csv_row(path: Path) -> dict[str, str]:
    rows = read_csv_rows(path)
    if not rows:
        raise ValueError(f"Required summary CSV is empty: {path}")
    return rows[0]


def load_inputs(args: argparse.Namespace) -> Inputs:
    replay_dir = Path(args.rule_replay_dir)
    audit_dir = Path(args.timeout_audit_dir)
    root_dir = Path(args.timeout_root_cause_dir)
    sequence_dir = Path(args.timeout_sequence_dir)
    return Inputs(
        rule_replay_dir=replay_dir,
        timeout_audit_dir=audit_dir,
        timeout_root_cause_dir=root_dir,
        timeout_sequence_dir=sequence_dir,
        replay_summary=first_csv_row(replay_dir / REPLAY_SUMMARY_FILE),
        replay_warnings=read_csv_rows(replay_dir / REPLAY_WARNINGS_FILE),
        stress_trades=read_csv_rows(replay_dir / REPLAY_STRESS_TRADE_LOG_FILE),
        base_trades=read_csv_rows(replay_dir / REPLAY_BASE_TRADE_LOG_FILE),
        timeout_audit_summary=first_csv_row(audit_dir / TIMEOUT_AUDIT_SUMMARY_FILE),
        timeout_root_summary=first_csv_row(root_dir / TIMEOUT_ROOT_SUMMARY_FILE),
        timeout_sequence_summary=first_csv_row(sequence_dir / TIMEOUT_SEQUENCE_SUMMARY_FILE),
    )


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "output_dir": output_dir,
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "modes": output_dir / MODES_FILE,
        "timeout_trades": output_dir / TIMEOUT_TRADES_FILE,
        "extended_horizons": output_dir / EXTENDED_HORIZONS_FILE,
        "exit_transition": output_dir / EXIT_TRANSITION_FILE,
        "next_actions": output_dir / NEXT_ACTIONS_FILE,
    }


def ensure_can_write(paths: dict[str, Path], overwrite: bool) -> None:
    output_dir = paths["output_dir"]
    if not output_dir.exists():
        return
    existing = [path for key, path in paths.items() if key != "output_dir" and path.exists()]
    if existing and not overwrite:
        formatted = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist; pass --overwrite to replace them: {formatted}")


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def finite_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else parsed


def parse_horizon(value: object) -> int:
    text = str(value or "").strip().lower()
    if text.startswith("h"):
        text = text[1:]
    horizon = int(text)
    if horizon <= 0:
        raise ValueError("horizon must be greater than zero")
    return horizon


def parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def candidate_meta(inputs: Inputs) -> CandidateMeta:
    source = inputs.replay_summary
    return CandidateMeta(
        symbol=str(source.get("symbol") or "").strip().upper(),
        direction=str(source.get("direction") or "").strip().lower(),
        timeframe=str(source.get("timeframe") or "").strip().upper(),
        horizon=parse_horizon(source.get("horizon")),
        target_family=str(source.get("target_family") or "").strip(),
        regime_column=str(source.get("regime_column") or "").strip(),
        regime_value=str(source.get("regime_value") or "").strip(),
        feature_condition=str(source.get("feature_condition") or "").strip(),
        tp_atr=float(str(source.get("tp_atr") or "0").strip()),
        sl_atr=float(str(source.get("sl_atr") or "0").strip()),
        atr_column=str(source.get("atr_column") or "atr_20").strip(),
        same_bar_policy=str(source.get("same_bar_policy") or "stop_first").strip(),
    )


def normalize_exit_reason(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"tp", "take_profit"}:
        return "tp"
    if text in {"sl", "stop_loss"}:
        return "sl"
    if text in {"timeout", "end_of_data"}:
        return "timeout"
    return text or "other"


def trade_r(row: dict[str, object]) -> float:
    return finite_float(row.get("R")) or 0.0


def row_cost(row: dict[str, object]) -> float:
    return finite_float(row.get("cost_R")) or 0.0


def gross_proxy(row: dict[str, object]) -> float:
    return trade_r(row) + row_cost(row)


def mean(values: Iterable[float]) -> float | None:
    selected = list(values)
    return statistics.fmean(selected) if selected else None


def median(values: Iterable[float]) -> float | None:
    selected = list(values)
    return statistics.median(selected) if selected else None


def profit_factor(values: Iterable[float]) -> float | None:
    selected = list(values)
    if not selected:
        return None
    gains = sum(value for value in selected if value > 0)
    losses = abs(sum(value for value in selected if value < 0))
    if losses == 0:
        return math.inf if gains > 0 else None
    return gains / losses


def max_drawdown(values: Iterable[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return max_dd


def rate(count: int, total: int) -> float | None:
    return count / total if total else None


def mode_metrics(
    *,
    mode: str,
    scope: str,
    horizon_cap: object,
    diagnostic_label: str,
    rows: list[dict[str, object]],
    total_source_count: int | None = None,
    current_values: list[float] | None = None,
    retained_count: int | None = None,
) -> dict[str, object]:
    values = [trade_r(row) for row in rows]
    total = len(rows)
    source_total = total_source_count if total_source_count is not None else total
    tp_count = sum(1 for row in rows if normalize_exit_reason(row.get("exit_reason")) == "tp")
    sl_count = sum(1 for row in rows if normalize_exit_reason(row.get("exit_reason")) == "sl")
    timeout_rows = [row for row in rows if normalize_exit_reason(row.get("exit_reason")) == "timeout"]
    timeout_values = [trade_r(row) for row in timeout_rows]
    current_sum = sum(current_values) if current_values is not None else None
    current_dd = max_drawdown(current_values) if current_values is not None else None
    return {
        "mode": mode,
        "scope": scope,
        "horizon_cap": horizon_cap,
        "diagnostic_label": diagnostic_label,
        "trades": total,
        "trades_retained": retained_count if retained_count is not None else total,
        "trades_excluded": max(source_total - total, 0),
        "excluded_timeout_share": rate(max(source_total - total, 0), source_total),
        "mean_R": mean(values),
        "median_R": median(values),
        "profit_factor_R": profit_factor(values),
        "cumulative_R": sum(values),
        "max_drawdown_R": max_drawdown(values),
        "tp_count": tp_count,
        "tp_rate": rate(tp_count, total),
        "sl_count": sl_count,
        "sl_rate": rate(sl_count, total),
        "timeout_count": len(timeout_rows),
        "timeout_rate": rate(len(timeout_rows), total),
        "timeout_cumulative_R": sum(timeout_values),
        "timeout_mean_R": mean(timeout_values),
        "delta_cumulative_R_vs_current_h10": (sum(values) - current_sum) if current_sum is not None else "",
        "delta_max_drawdown_R_vs_current_h10": (max_drawdown(values) - current_dd) if current_dd is not None else "",
    }


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)).fetchone()
    return row is not None


def load_db_rows(db_path: Path, symbol: str, timeframe: str) -> list[dict[str, object]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        if not table_exists(connection, "ml_dataset"):
            raise sqlite3.OperationalError("Table 'ml_dataset' does not exist.")
        rows = connection.execute(
            """
            SELECT *
            FROM ml_dataset
            WHERE symbol = ?
              AND timeframe = ?
            ORDER BY time_server ASC
            """,
            (symbol, timeframe),
        ).fetchall()
    return [dict(row) for row in rows]


def selected_spread_for_policy(
    row: dict[str, object],
    symbol: str,
    cost_config: dict[str, object],
    stress_spread_policy: str,
) -> float | None:
    if point_size_for_symbol(symbol, cost_config) is None:
        return None
    row_spread = finite_float(row.get("spread"))
    if row_spread is None:
        row_spread = finite_float(row.get("spread_avg_20"))
    _fallback_source, fallback_spread = fallback_spread_source_for_symbol(symbol, cost_config)
    if stress_spread_policy == STRESS_SPREAD_POLICY_FALLBACK_OVERRIDE:
        return fallback_spread if fallback_spread is not None else row_spread
    if stress_spread_policy == STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK:
        if row_spread is not None and fallback_spread is not None:
            return max(row_spread, fallback_spread)
        return fallback_spread if fallback_spread is not None else row_spread
    return row_spread if row_spread is not None else fallback_spread


def cost_adjusted_entry_row(
    row: dict[str, object],
    *,
    symbol: str,
    cost_config: dict[str, object],
    stress_spread_policy: str,
) -> dict[str, object]:
    if stress_spread_policy == STRESS_SPREAD_POLICY_STANDARD:
        return row
    selected = selected_spread_for_policy(row, symbol, cost_config, stress_spread_policy)
    if selected is None:
        return row
    adjusted = dict(row)
    adjusted["spread"] = selected
    return adjusted


def price_levels(entry_price: float, atr: float, meta: CandidateMeta) -> tuple[float, float]:
    if meta.direction == "long":
        return entry_price + meta.tp_atr * atr, entry_price - meta.sl_atr * atr
    return entry_price - meta.tp_atr * atr, entry_price + meta.sl_atr * atr


def hit_flags(high_price: float, low_price: float, tp_price: float, sl_price: float, direction: str) -> tuple[bool, bool]:
    if direction == "long":
        return high_price >= tp_price, low_price <= sl_price
    return low_price <= tp_price, high_price >= sl_price


def selected_exit(take_hit: bool, stop_hit: bool, same_bar_policy: str) -> tuple[str | None, bool]:
    if take_hit and stop_hit:
        if same_bar_policy == "stop_first":
            return "sl", True
        if same_bar_policy == "take_first":
            return "tp", True
        raise ValueError(f"Unsupported same-bar policy: {same_bar_policy}")
    if stop_hit:
        return "sl", False
    if take_hit:
        return "tp", False
    return None, False


def diagnostic_cost_r(
    entry_row: dict[str, object],
    *,
    meta: CandidateMeta,
    entry_price: float,
    sl_distance: float,
    stress_cost_config: dict[str, object],
    stress_spread_policy: str,
) -> tuple[float, float]:
    adjusted = cost_adjusted_entry_row(
        entry_row,
        symbol=meta.symbol,
        cost_config=stress_cost_config,
        stress_spread_policy=stress_spread_policy,
    )
    cost_return = estimate_total_cost_return(adjusted, meta.symbol, stress_cost_config)
    cost_R = (cost_return * entry_price) / sl_distance if sl_distance > 0 else 0.0
    return cost_return, cost_R


def extended_outcome(
    trade: dict[str, object],
    *,
    timeout_trade_index: int,
    stress_trade_index: int,
    cap: int,
    meta: CandidateMeta,
    db_rows: list[dict[str, object]],
    db_index_by_time: dict[str, int],
    stress_cost_config: dict[str, object],
    stress_spread_policy: str,
) -> dict[str, object]:
    original_R = trade_r(trade)
    entry_time = str(trade.get("entry_time") or "")
    if entry_time not in db_index_by_time:
        return unavailable_extended_row(trade, timeout_trade_index, stress_trade_index, cap, "entry_time_not_found")
    row_index = db_index_by_time[entry_time]
    if row_index + cap >= len(db_rows):
        return unavailable_extended_row(trade, timeout_trade_index, stress_trade_index, cap, "insufficient_future_bars")
    entry_row = db_rows[row_index]
    entry_price = finite_float(trade.get("entry_price")) or finite_float(entry_row.get("close"))
    atr = finite_float(entry_row.get(meta.atr_column))
    if entry_price is None or entry_price <= 0 or atr is None or atr <= 0:
        return unavailable_extended_row(trade, timeout_trade_index, stress_trade_index, cap, "invalid_entry_price_or_atr")
    sl_distance = meta.sl_atr * atr
    if sl_distance <= 0:
        return unavailable_extended_row(trade, timeout_trade_index, stress_trade_index, cap, "invalid_sl_distance")

    tp_price, sl_price = price_levels(entry_price, atr, meta)
    selected: str | None = None
    selected_exit_time: object = ""
    selected_bars = cap
    same_bar_conflict = False
    for bars_ahead in range(meta.horizon + 1, cap + 1):
        future_row = db_rows[row_index + bars_ahead]
        high_price = finite_float(future_row.get("high"))
        low_price = finite_float(future_row.get("low"))
        if high_price is None or low_price is None:
            return unavailable_extended_row(trade, timeout_trade_index, stress_trade_index, cap, "missing_future_ohlc")
        take_hit, stop_hit = hit_flags(high_price, low_price, tp_price, sl_price, meta.direction)
        chosen, conflict = selected_exit(take_hit, stop_hit, meta.same_bar_policy)
        if chosen is not None:
            selected = chosen
            selected_exit_time = future_row.get("time_server")
            selected_bars = bars_ahead
            same_bar_conflict = conflict
            break

    if selected == "tp":
        gross_R = meta.tp_atr / meta.sl_atr
        outcome = "tp_after_timeout"
    elif selected == "sl":
        gross_R = -1.0
        outcome = "sl_after_timeout"
    else:
        cap_row = db_rows[row_index + cap]
        cap_close = finite_float(cap_row.get("close"))
        if cap_close is None:
            return unavailable_extended_row(trade, timeout_trade_index, stress_trade_index, cap, "missing_cap_close")
        move = cap_close - entry_price if meta.direction == "long" else entry_price - cap_close
        gross_R = move / sl_distance
        selected_exit_time = cap_row.get("time_server")
        outcome = f"still_timeout_at_h{cap}"

    _cost_return, cost_R = diagnostic_cost_r(
        entry_row,
        meta=meta,
        entry_price=entry_price,
        sl_distance=sl_distance,
        stress_cost_config=stress_cost_config,
        stress_spread_policy=stress_spread_policy,
    )
    net_R = gross_R - cost_R
    return {
        "horizon_cap": cap,
        "timeout_trade_index": timeout_trade_index,
        "stress_trade_index": stress_trade_index,
        "entry_time": entry_time,
        "exit_time": selected_exit_time,
        "outcome": outcome,
        "path_status": "ok",
        "bars_held": selected_bars,
        "additional_bars_held": max(selected_bars - meta.horizon, 0),
        "entry_price": entry_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "gross_R_proxy": gross_R,
        "cost_R": cost_R,
        "net_R": net_R,
        "R": net_R,
        "delta_vs_original_R": net_R - original_R,
        "original_R": original_R,
        "same_bar_conflict": same_bar_conflict,
    }


def unavailable_extended_row(
    trade: dict[str, object],
    timeout_trade_index: int,
    stress_trade_index: int,
    cap: int,
    reason: str,
) -> dict[str, object]:
    original_R = trade_r(trade)
    return {
        "horizon_cap": cap,
        "timeout_trade_index": timeout_trade_index,
        "stress_trade_index": stress_trade_index,
        "entry_time": trade.get("entry_time", ""),
        "exit_time": "",
        "outcome": "future_path_unavailable",
        "path_status": reason,
        "bars_held": "",
        "additional_bars_held": "",
        "entry_price": trade.get("entry_price", ""),
        "tp_price": "",
        "sl_price": "",
        "gross_R_proxy": gross_proxy(trade),
        "cost_R": row_cost(trade),
        "net_R": trade.get("net_R", ""),
        "R": original_R,
        "delta_vs_original_R": 0.0,
        "original_R": original_R,
        "same_bar_conflict": "",
    }


def stress_trade_indexes(rows: list[dict[str, object]]) -> dict[int, int]:
    return {id(row): index for index, row in enumerate(rows, start=1)}


def timeout_rows_with_indexes(rows: list[dict[str, object]]) -> list[tuple[int, int, dict[str, object]]]:
    output: list[tuple[int, int, dict[str, object]]] = []
    timeout_index = 0
    for stress_index, row in enumerate(rows, start=1):
        if normalize_exit_reason(row.get("exit_reason")) != "timeout":
            continue
        timeout_index += 1
        output.append((timeout_index, stress_index, row))
    return output


def replacement_rows_for_cap(
    stress_rows: list[dict[str, object]],
    extended_rows: list[dict[str, object]],
    cap: int,
) -> list[dict[str, object]]:
    by_stress_index = {
        int(row["stress_trade_index"]): row
        for row in extended_rows
        if int(row.get("horizon_cap") or 0) == cap
    }
    output: list[dict[str, object]] = []
    for stress_index, row in enumerate(stress_rows, start=1):
        replacement = by_stress_index.get(stress_index)
        if replacement is None:
            output.append(dict(row))
            continue
        new_row = dict(row)
        new_row["exit_reason"] = replacement.get("outcome")
        new_row["exit_time"] = replacement.get("exit_time") or row.get("exit_time")
        new_row["bars_held"] = replacement.get("bars_held") or row.get("bars_held")
        new_row["R"] = replacement.get("R")
        new_row["cost_R"] = replacement.get("cost_R")
        new_row["net_R"] = replacement.get("net_R")
        output.append(new_row)
    return output


def aggregate_extended_rows(
    *,
    cap: int,
    cap_rows: list[dict[str, object]],
    stress_rows: list[dict[str, object]],
    current_stress_values: list[float],
) -> dict[str, object]:
    inspected = len(cap_rows)
    available = [row for row in cap_rows if row.get("path_status") == "ok"]
    values = [finite_float(row.get("R")) or 0.0 for row in cap_rows]
    original_values = [finite_float(row.get("original_R")) or 0.0 for row in cap_rows]
    tp_count = sum(1 for row in available if str(row.get("outcome")) == "tp_after_timeout")
    sl_count = sum(1 for row in available if str(row.get("outcome")) == "sl_after_timeout")
    still_count = sum(1 for row in available if str(row.get("outcome")).startswith("still_timeout"))
    unavailable_count = inspected - len(available)
    additional_bars = [
        int(finite_float(row.get("additional_bars_held")) or 0)
        for row in available
        if finite_float(row.get("additional_bars_held")) is not None
    ]
    replacement = replacement_rows_for_cap(stress_rows, cap_rows, cap)
    replacement_values = [trade_r(row) for row in replacement]
    current_cumulative = sum(current_stress_values)
    current_dd = max_drawdown(current_stress_values)
    return {
        "horizon_cap": f"h{cap}",
        "diagnostic_label": "diagnostic_replacement_only_not_validated_rule",
        "timeout_trades_inspected": inspected,
        "path_unavailable_count": unavailable_count,
        "tp_after_timeout_count": tp_count,
        "tp_after_timeout_rate": rate(tp_count, inspected),
        "sl_after_timeout_count": sl_count,
        "sl_after_timeout_rate": rate(sl_count, inspected),
        "still_timeout_count": still_count,
        "still_timeout_rate": rate(still_count, inspected),
        "timeout_subset_mean_R": mean(values),
        "timeout_subset_cumulative_R": sum(values),
        "original_h10_timeout_subset_cumulative_R": sum(original_values),
        "delta_vs_original_h10_timeout_R": sum(values) - sum(original_values),
        "average_additional_bars_held": mean(additional_bars),
        "max_additional_bars_held": max(additional_bars) if additional_bars else None,
        "replacement_total_trades": len(replacement),
        "replacement_mean_R": mean(replacement_values),
        "replacement_cumulative_R": sum(replacement_values),
        "replacement_profit_factor_R": profit_factor(replacement_values),
        "replacement_max_drawdown_R": max_drawdown(replacement_values),
        "replacement_delta_cumulative_R_vs_current_h10": sum(replacement_values) - current_cumulative,
        "replacement_delta_max_drawdown_R_vs_current_h10": max_drawdown(replacement_values) - current_dd,
    }


def transition_rows(cap_rows: list[dict[str, object]], cap: int) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    total = len(cap_rows)
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in cap_rows:
        grouped.setdefault(str(row.get("outcome") or "unknown"), []).append(row)
    for outcome in sorted(grouped):
        rows = grouped[outcome]
        values = [finite_float(row.get("R")) or 0.0 for row in rows]
        output.append(
            {
                "horizon_cap": f"h{cap}",
                "from_exit_reason": "h10_timeout",
                "to_exit_reason": outcome,
                "count": len(rows),
                "rate": rate(len(rows), total),
                "cumulative_R": sum(values),
                "mean_R": mean(values),
            }
        )
    return output


def timeout_trade_output_rows(
    timeout_rows: list[tuple[int, int, dict[str, object]]],
    extended_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_key = {
        (int(row.get("timeout_trade_index") or 0), int(row.get("horizon_cap") or 0)): row
        for row in extended_rows
    }
    output: list[dict[str, object]] = []
    for timeout_index, stress_index, trade in timeout_rows:
        row = {
            "timeout_trade_index": timeout_index,
            "stress_trade_index": stress_index,
            "entry_time": trade.get("entry_time", ""),
            "original_exit_time": trade.get("exit_time", ""),
            "entry_price": trade.get("entry_price", ""),
            "original_exit_price": trade.get("exit_price", ""),
            "original_bars_held": trade.get("bars_held", ""),
            "original_R": trade_r(trade),
            "original_cost_R": row_cost(trade),
            "original_net_R": trade.get("net_R", ""),
            "original_gross_R_proxy": gross_proxy(trade),
        }
        for cap in EXTENDED_HORIZON_CAPS:
            extended = by_key.get((timeout_index, cap), {})
            row[f"h{cap}_outcome"] = extended.get("outcome", "")
            row[f"h{cap}_R"] = extended.get("R", "")
            row[f"h{cap}_delta_R"] = extended.get("delta_vs_original_R", "")
            row[f"h{cap}_additional_bars"] = extended.get("additional_bars_held", "")
        output.append(row)
    return output


def add_warning(
    warnings: list[dict[str, object]],
    *,
    warning_code: str,
    severity: str,
    blocking: bool,
    message: str,
    related_metric: str = "",
    metric_value: object = "",
    threshold: object = "",
) -> None:
    warnings.append(
        warning_row(
            warning_code=warning_code,
            severity=severity,
            blocking=blocking,
            message=message,
            related_stage="timeout_policy_sensitivity",
            related_metric=related_metric,
            metric_value=metric_value,
            threshold=threshold,
        )
    )


def warning_lines(warnings: list[dict[str, object]]) -> list[str]:
    if not warnings:
        return ["- None."]
    return [
        f"- {warning.get('severity')} `{warning.get('warning_code')}`: {warning.get('message')}"
        for warning in warnings
    ]


def table_lines(rows: list[dict[str, object]], columns: list[str], *, limit: int | None = None) -> list[str]:
    selected = rows[:limit] if limit else rows
    if not selected:
        return ["_No rows._"]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in selected:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    if limit and len(rows) > limit:
        lines.append(f"_Showing {limit} of {len(rows)} rows._")
    return lines


def build_next_actions(classification: str) -> list[dict[str, object]]:
    if classification == CLEARED_LABEL:
        message = "Candidate can return to limited offline baseline and cost-sensitivity review with timeout caveat preserved."
    elif classification == RETAINED_LABEL:
        message = "Candidate should remain in timeout review before baseline and cost-sensitivity review."
    else:
        message = (
            "Alternative timeout policies are rejected; candidate should not continue to baseline or "
            "cost-sensitivity review under current timeout policy evidence."
        )
    forbidden = forbidden_actions_text(FORBIDDEN_ACTIONS)
    rows = [
        next_action_row(
            action_type="explicit_next_action",
            status=classification,
            message=message,
            forbidden_actions=forbidden,
        )
    ]
    rows.extend(
        next_action_row(
            action_type="forbidden_action",
            status="forbidden",
            message=action,
            forbidden_actions=forbidden,
        )
        for action in FORBIDDEN_ACTIONS
    )
    return rows


def classify(
    *,
    current_mode: dict[str, object],
    excluded_mode: dict[str, object],
    summary_values: dict[str, object],
    warnings: list[dict[str, object]],
) -> str:
    if any(bool_value(warning.get("blocking")) for warning in warnings):
        return REJECTED_LABEL
    current_strong = (
        (finite_float(current_mode.get("mean_R")) or 0.0) > 0
        and (finite_float(current_mode.get("cumulative_R")) or 0.0) > 0
        and (finite_float(current_mode.get("profit_factor_R")) or 0.0) > 1
    )
    if not current_strong:
        return REJECTED_LABEL
    excluded_strong = (
        (finite_float(excluded_mode.get("mean_R")) or 0.0) > 0
        and (finite_float(excluded_mode.get("cumulative_R")) or 0.0) > 0
        and (finite_float(excluded_mode.get("profit_factor_R")) or 0.0) > 1
    )
    if not excluded_strong:
        return RETAINED_LABEL
    timeout_loss_ratio = finite_float(summary_values.get("timeout_loss_ratio_of_stress_cumulative_R")) or 0.0
    if timeout_loss_ratio > TIMEOUT_LOSS_SMALL_RATIO_MAX:
        return RETAINED_LABEL
    if int(summary_values.get("db_future_path_unavailable_count") or 0) > 0:
        return RETAINED_LABEL
    if (finite_float(summary_values.get("min_extended_timeout_subset_delta_R")) or 0.0) < 0:
        return RETAINED_LABEL
    return CLEARED_LABEL


def add_policy_warnings(
    warnings: list[dict[str, object]],
    *,
    summary_values: dict[str, object],
    extended_rows: list[dict[str, object]],
) -> None:
    add_warning(
        warnings,
        warning_code="timeout_excluded_bias_warning",
        severity="review",
        blocking=False,
        message="Timeout-excluded diagnostics remove unresolved timeout trades and must not be interpreted as validated performance.",
        related_metric="timeout_excluded_trades",
        metric_value=summary_values.get("timeout_excluded_trades"),
        threshold="diagnostic only",
    )
    add_warning(
        warnings,
        warning_code="extended_horizon_not_validated_rule",
        severity="review",
        blocking=False,
        message="Extended h20/h40/h80 outcomes are sensitivity diagnostics only and do not redefine the validated h10 rule.",
        related_metric="extended_horizon_caps",
        metric_value="h20,h40,h80",
        threshold="diagnostic only",
    )
    add_warning(
        warnings,
        warning_code="h10_timeout_caveat_unresolved",
        severity="review",
        blocking=False,
        message="The h10 timeout caveat remains unresolved and must remain attached to any limited next review.",
        related_metric="prior_timeout_classifications",
        metric_value=(
            f"{summary_values.get('prior_timeout_audit_classification')} | "
            f"{summary_values.get('prior_timeout_root_cause_classification')} | "
            f"{summary_values.get('prior_timeout_sequence_classification')}"
        ),
        threshold="cleared timeout chain",
    )
    missing_count = int(summary_values.get("db_future_path_unavailable_count") or 0)
    if missing_count:
        add_warning(
            warnings,
            warning_code="db_future_path_unavailable",
            severity="review",
            blocking=False,
            message="Some original h10 timeout entries could not be extended because future DB path rows were unavailable.",
            related_metric="db_future_path_unavailable_count",
            metric_value=missing_count,
            threshold=0,
        )
    max_sl_rate = finite_float(summary_values.get("max_extended_sl_rate")) or 0.0
    if max_sl_rate >= EXTENDED_SL_DOMINANCE_RATE:
        add_warning(
            warnings,
            warning_code="extended_horizon_sl_dominance_warning",
            severity="blocking",
            blocking=True,
            message="Extended horizon diagnostics show h10 timeouts mostly becoming SL under at least one cap.",
            related_metric="max_extended_sl_rate",
            metric_value=max_sl_rate,
            threshold=f"< {EXTENDED_SL_DOMINANCE_RATE}",
        )
    stress_cumulative = finite_float(summary_values.get("stress_cumulative_R")) or 0.0
    min_delta = finite_float(summary_values.get("min_extended_timeout_subset_delta_R")) or 0.0
    if stress_cumulative > 0 and min_delta < -EXTENDED_WORSE_TIMEOUT_RATIO * stress_cumulative:
        add_warning(
            warnings,
            warning_code="timeout_policy_blocking_failure",
            severity="blocking",
            blocking=True,
            message="Extended horizon timeout subset becomes materially worse than the original h10 timeout subset.",
            related_metric="min_extended_timeout_subset_delta_R",
            metric_value=min_delta,
            threshold=f">= {-EXTENDED_WORSE_TIMEOUT_RATIO * stress_cumulative}",
        )
    dd_delta = finite_float(summary_values.get("max_replacement_drawdown_delta_R")) or 0.0
    if stress_cumulative > 0 and dd_delta > EXTENDED_DRAWDOWN_BLOCKING_RATIO * stress_cumulative:
        severity = "blocking"
        blocking = True
    elif stress_cumulative > 0 and dd_delta > EXTENDED_DRAWDOWN_REVIEW_RATIO * stress_cumulative:
        severity = "review"
        blocking = False
    else:
        severity = ""
        blocking = False
    if severity:
        add_warning(
            warnings,
            warning_code="extended_horizon_drawdown_warning",
            severity=severity,
            blocking=blocking,
            message="Diagnostic replacement with extended timeout outcomes increases full-candidate drawdown.",
            related_metric="max_replacement_drawdown_delta_R",
            metric_value=dd_delta,
            threshold=f"<= {EXTENDED_DRAWDOWN_REVIEW_RATIO} review ratio",
        )


def build_summary_values(
    *,
    run_id: str,
    args: argparse.Namespace,
    paths: dict[str, Path],
    inputs: Inputs,
    meta: CandidateMeta,
    stress_current: dict[str, object],
    stress_excluded: dict[str, object],
    extended_summary_rows: list[dict[str, object]],
) -> dict[str, object]:
    stress_cumulative = finite_float(stress_current.get("cumulative_R")) or 0.0
    timeout_cumulative = finite_float(stress_current.get("timeout_cumulative_R")) or 0.0
    timeout_loss_ratio = abs(timeout_cumulative) / stress_cumulative if timeout_cumulative < 0 and stress_cumulative > 0 else 0.0
    summary: dict[str, object] = {
        "run_id": run_id,
        "rule_replay_dir": str(inputs.rule_replay_dir),
        "timeout_audit_dir": str(inputs.timeout_audit_dir),
        "timeout_root_cause_dir": str(inputs.timeout_root_cause_dir),
        "timeout_sequence_dir": str(inputs.timeout_sequence_dir),
        "db_path": str(args.db_path),
        "cost_config": str(args.cost_config),
        "stress_cost_config": str(args.stress_cost_config),
        "stress_spread_policy": str(args.stress_spread_policy),
        "output_dir": str(paths["output_dir"]),
        "final_timeout_policy_sensitivity_classification": "",
        "can_return_to_limited_baseline_cost_review": False,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "symbol": meta.symbol,
        "direction": meta.direction,
        "timeframe": meta.timeframe,
        "horizon": f"h{meta.horizon}",
        "target_family": meta.target_family,
        "regime_column": meta.regime_column,
        "regime_value": meta.regime_value,
        "feature_condition": meta.feature_condition,
        "tp_atr": meta.tp_atr,
        "sl_atr": meta.sl_atr,
        "atr_column": meta.atr_column,
        "same_bar_policy": meta.same_bar_policy,
        "prior_timeout_audit_classification": inputs.timeout_audit_summary.get("final_timeout_audit_classification", ""),
        "prior_timeout_root_cause_classification": inputs.timeout_root_summary.get("final_timeout_root_cause_classification", ""),
        "prior_timeout_sequence_classification": inputs.timeout_sequence_summary.get("final_timeout_sequence_classification", ""),
        "stress_trades": stress_current.get("trades"),
        "stress_mean_R": stress_current.get("mean_R"),
        "stress_profit_factor_R": stress_current.get("profit_factor_R"),
        "stress_cumulative_R": stress_current.get("cumulative_R"),
        "stress_max_drawdown_R": stress_current.get("max_drawdown_R"),
        "stress_timeout_count": stress_current.get("timeout_count"),
        "stress_timeout_rate": stress_current.get("timeout_rate"),
        "stress_timeout_cumulative_R": stress_current.get("timeout_cumulative_R"),
        "stress_timeout_mean_R": stress_current.get("timeout_mean_R"),
        "timeout_loss_ratio_of_stress_cumulative_R": timeout_loss_ratio,
        "timeout_excluded_trades": stress_excluded.get("trades"),
        "timeout_excluded_mean_R": stress_excluded.get("mean_R"),
        "timeout_excluded_profit_factor_R": stress_excluded.get("profit_factor_R"),
        "timeout_excluded_cumulative_R": stress_excluded.get("cumulative_R"),
        "max_extended_sl_rate": 0.0,
        "min_extended_timeout_subset_delta_R": 0.0,
        "max_replacement_drawdown_delta_R": 0.0,
        "db_future_path_unavailable_count": 0,
    }
    deltas: list[float] = []
    dd_deltas: list[float] = []
    sl_rates: list[float] = []
    missing_total = 0
    for row in extended_summary_rows:
        cap = str(row.get("horizon_cap") or "")
        prefix = f"extended_{cap}_"
        summary[f"{prefix}tp_rate"] = row.get("tp_after_timeout_rate")
        summary[f"{prefix}sl_rate"] = row.get("sl_after_timeout_rate")
        summary[f"{prefix}still_timeout_rate"] = row.get("still_timeout_rate")
        summary[f"{prefix}timeout_subset_cumulative_R"] = row.get("timeout_subset_cumulative_R")
        summary[f"{prefix}delta_vs_h10_timeout_R"] = row.get("delta_vs_original_h10_timeout_R")
        if finite_float(row.get("delta_vs_original_h10_timeout_R")) is not None:
            deltas.append(float(row["delta_vs_original_h10_timeout_R"]))
        if finite_float(row.get("replacement_delta_max_drawdown_R_vs_current_h10")) is not None:
            dd_deltas.append(float(row["replacement_delta_max_drawdown_R_vs_current_h10"]))
        if finite_float(row.get("sl_after_timeout_rate")) is not None:
            sl_rates.append(float(row["sl_after_timeout_rate"]))
        missing_total += int(finite_float(row.get("path_unavailable_count")) or 0)
    summary["max_extended_sl_rate"] = max(sl_rates) if sl_rates else 0.0
    summary["min_extended_timeout_subset_delta_R"] = min(deltas) if deltas else 0.0
    summary["max_replacement_drawdown_delta_R"] = max(dd_deltas) if dd_deltas else 0.0
    summary["db_future_path_unavailable_count"] = missing_total
    return summary


def interpretation_text(classification: str) -> str:
    if classification == CLEARED_LABEL:
        return "Timeout policy sensitivity does not reveal a blocking timeout-policy failure, but the diagnostic caveat remains attached to the next limited offline review."
    if classification == RETAINED_LABEL:
        return "Timeout policy sensitivity remains mixed or incomplete, so the candidate should stay in timeout review before baseline and cost-sensitivity review."
    return "Timeout policy sensitivity reveals a blocking timeout-policy concern under the current diagnostic evidence."


def report_text(
    *,
    summary: dict[str, object],
    mode_rows: list[dict[str, object]],
    extended_rows: list[dict[str, object]],
    transition_rows_output: list[dict[str, object]],
    warnings: list[dict[str, object]],
    next_actions: list[dict[str, object]],
) -> str:
    forbidden_rows = [row for row in next_actions if row["action_type"] == "forbidden_action"]
    classification = str(summary.get("final_timeout_policy_sensitivity_classification") or "")
    return "\n".join(
        [
            "# Timeout Policy Sensitivity Review",
            "",
            "## Research-Only Warning",
            "",
            "This diagnostic reads existing replay outputs and inspects future bars only for existing h10 timeout entries. Timeout-excluded and extended-horizon modes are biased diagnostics, not replacement rules.",
            "",
            "## Candidate Definition",
            "",
            f"- Symbol: `{summary.get('symbol')}`",
            f"- Direction: `{summary.get('direction')}`",
            f"- Timeframe: `{summary.get('timeframe')}`",
            f"- Horizon: `{summary.get('horizon')}`",
            f"- Target family: `{summary.get('target_family')}`",
            f"- Regime: `{summary.get('regime_column')}={summary.get('regime_value')}`",
            f"- Feature condition: `{summary.get('feature_condition')}`",
            f"- TP/SL ATR: `{summary.get('tp_atr')}` / `{summary.get('sl_atr')}`",
            f"- Same-bar policy: `{summary.get('same_bar_policy')}`",
            f"- Stress spread policy: `{summary.get('stress_spread_policy')}`",
            "",
            "## Input Sources",
            "",
            f"- Rule replay: `{summary.get('rule_replay_dir')}`",
            f"- Timeout audit: `{summary.get('timeout_audit_dir')}`",
            f"- Timeout root-cause: `{summary.get('timeout_root_cause_dir')}`",
            f"- Timeout sequence: `{summary.get('timeout_sequence_dir')}`",
            f"- DB path: `{summary.get('db_path')}`",
            "",
            "## Prior Timeout Caveat State",
            "",
            f"- Timeout audit: `{summary.get('prior_timeout_audit_classification')}`",
            f"- Timeout root-cause: `{summary.get('prior_timeout_root_cause_classification')}`",
            f"- Timeout sequence: `{summary.get('prior_timeout_sequence_classification')}`",
            "",
            "## Mode A: Current H10 Timeout Policy",
            "",
            *table_lines([row for row in mode_rows if row["mode"] == "current_h10_timeout"], ["scope", "trades", "mean_R", "profit_factor_R", "cumulative_R", "timeout_count", "timeout_cumulative_R"]),
            "",
            "## Mode B: Timeout-Excluded Diagnostic",
            "",
            *table_lines([row for row in mode_rows if row["mode"] == "timeout_excluded_diagnostic"], ["scope", "trades", "trades_excluded", "excluded_timeout_share", "mean_R", "profit_factor_R", "cumulative_R"]),
            "",
            "## Mode C: Extended Horizon Diagnostic H20/H40/H80",
            "",
            *table_lines(extended_rows, ["horizon_cap", "tp_after_timeout_rate", "sl_after_timeout_rate", "still_timeout_rate", "timeout_subset_cumulative_R", "delta_vs_original_h10_timeout_R"]),
            "",
            "## Exit Transition Table",
            "",
            *table_lines(transition_rows_output, ["horizon_cap", "from_exit_reason", "to_exit_reason", "count", "rate", "cumulative_R"]),
            "",
            "## Full-Candidate Diagnostic Replacement Summary",
            "",
            *table_lines([row for row in mode_rows if row["mode"] == "extended_horizon_diagnostic"], ["horizon_cap", "diagnostic_label", "trades", "mean_R", "profit_factor_R", "cumulative_R", "max_drawdown_R", "delta_cumulative_R_vs_current_h10"]),
            "",
            "## Interpretation",
            "",
            interpretation_text(classification),
            "",
            "## Warnings",
            "",
            *warning_lines(warnings),
            "",
            "## Final Timeout Policy Sensitivity Classification",
            "",
            f"`{classification}`",
            "",
            "## Explicit Next Action",
            "",
            next_actions[0]["message"],
            "",
            "## Forbidden Actions",
            "",
            *table_lines(forbidden_rows, ["message"]),
            "",
        ]
    )


def build_timeout_policy_sensitivity_review(args: argparse.Namespace) -> dict[str, Path]:
    run_id = str(args.run_id or Path(args.rule_replay_dir).name).strip()
    if not run_id:
        raise ValueError("--run-id is required when --rule-replay-dir has no final path name")
    paths = output_paths(Path(args.output_root), run_id)
    ensure_can_write(paths, bool(args.overwrite))
    inputs = load_inputs(args)
    meta = candidate_meta(inputs)
    _base_cost_config = load_cost_config(Path(args.cost_config))
    stress_cost_config = load_cost_config(Path(args.stress_cost_config))

    current_stress_values = [trade_r(row) for row in inputs.stress_trades]
    current_base_values = [trade_r(row) for row in inputs.base_trades]
    stress_current = mode_metrics(
        mode="current_h10_timeout",
        scope="stress",
        horizon_cap=f"h{meta.horizon}",
        diagnostic_label="validated_h10_policy",
        rows=inputs.stress_trades,
    )
    base_current = mode_metrics(
        mode="current_h10_timeout",
        scope="base",
        horizon_cap=f"h{meta.horizon}",
        diagnostic_label="validated_h10_policy",
        rows=inputs.base_trades,
    )
    stress_non_timeout = [row for row in inputs.stress_trades if normalize_exit_reason(row.get("exit_reason")) in {"tp", "sl"}]
    base_non_timeout = [row for row in inputs.base_trades if normalize_exit_reason(row.get("exit_reason")) in {"tp", "sl"}]
    stress_excluded = mode_metrics(
        mode="timeout_excluded_diagnostic",
        scope="stress",
        horizon_cap=f"h{meta.horizon}",
        diagnostic_label="biased_timeout_excluded_not_validated_rule",
        rows=stress_non_timeout,
        total_source_count=len(inputs.stress_trades),
    )
    base_excluded = mode_metrics(
        mode="timeout_excluded_diagnostic",
        scope="base",
        horizon_cap=f"h{meta.horizon}",
        diagnostic_label="biased_timeout_excluded_not_validated_rule",
        rows=base_non_timeout,
        total_source_count=len(inputs.base_trades),
    )

    db_rows = load_db_rows(Path(args.db_path), meta.symbol, meta.timeframe)
    db_index_by_time = {str(row.get("time_server") or ""): index for index, row in enumerate(db_rows)}
    timeout_indexed = timeout_rows_with_indexes(inputs.stress_trades)
    extended_detail_rows: list[dict[str, object]] = []
    for cap in EXTENDED_HORIZON_CAPS:
        for timeout_index, stress_index, trade in timeout_indexed:
            extended_detail_rows.append(
                extended_outcome(
                    trade,
                    timeout_trade_index=timeout_index,
                    stress_trade_index=stress_index,
                    cap=cap,
                    meta=meta,
                    db_rows=db_rows,
                    db_index_by_time=db_index_by_time,
                    stress_cost_config=stress_cost_config,
                    stress_spread_policy=str(args.stress_spread_policy),
                )
            )

    extended_summary_rows = [
        aggregate_extended_rows(
            cap=cap,
            cap_rows=[row for row in extended_detail_rows if int(row.get("horizon_cap") or 0) == cap],
            stress_rows=inputs.stress_trades,
            current_stress_values=current_stress_values,
        )
        for cap in EXTENDED_HORIZON_CAPS
    ]
    transition_output_rows = [
        transition
        for cap in EXTENDED_HORIZON_CAPS
        for transition in transition_rows(
            [row for row in extended_detail_rows if int(row.get("horizon_cap") or 0) == cap],
            cap,
        )
    ]
    replacement_mode_rows = []
    for cap in EXTENDED_HORIZON_CAPS:
        replacement = replacement_rows_for_cap(
            inputs.stress_trades,
            [row for row in extended_detail_rows if int(row.get("horizon_cap") or 0) == cap],
            cap,
        )
        replacement_mode_rows.append(
            mode_metrics(
                mode="extended_horizon_diagnostic",
                scope="stress",
                horizon_cap=f"h{cap}",
                diagnostic_label="diagnostic_replacement_only_not_validated_rule",
                rows=replacement,
                current_values=current_stress_values,
            )
        )
    mode_rows = [stress_current, base_current, stress_excluded, base_excluded, *replacement_mode_rows]
    summary_values = build_summary_values(
        run_id=run_id,
        args=args,
        paths=paths,
        inputs=inputs,
        meta=meta,
        stress_current=stress_current,
        stress_excluded=stress_excluded,
        extended_summary_rows=extended_summary_rows,
    )
    warnings: list[dict[str, object]] = []
    add_policy_warnings(warnings, summary_values=summary_values, extended_rows=extended_detail_rows)
    classification = classify(
        current_mode=stress_current,
        excluded_mode=stress_excluded,
        summary_values=summary_values,
        warnings=warnings,
    )
    blocking_count = sum(1 for warning in warnings if bool_value(warning.get("blocking")))
    summary_values.update(
        {
            "final_timeout_policy_sensitivity_classification": classification,
            "can_return_to_limited_baseline_cost_review": classification == CLEARED_LABEL,
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_count,
        }
    )
    next_actions = build_next_actions(classification)
    add_common_summary_fields(
        summary_values,
        decision_scope="timeout_policy_sensitivity",
        final_classification=classification,
        next_action=next_actions[0]["message"] if next_actions else "",
    )
    timeout_trade_rows = timeout_trade_output_rows(timeout_indexed, extended_detail_rows)

    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_csv(paths["summary"], [summary_values], SUMMARY_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["modes"], mode_rows, MODE_FIELDNAMES)
    write_csv(paths["timeout_trades"], timeout_trade_rows, TIMEOUT_TRADE_FIELDNAMES)
    write_csv(paths["extended_horizons"], extended_summary_rows, EXTENDED_FIELDNAMES)
    write_csv(paths["exit_transition"], transition_output_rows, TRANSITION_FIELDNAMES)
    write_csv(paths["next_actions"], next_actions, NEXT_ACTION_FIELDNAMES)
    paths["report"].write_text(
        report_text(
            summary=summary_values,
            mode_rows=mode_rows,
            extended_rows=extended_summary_rows,
            transition_rows_output=transition_output_rows,
            warnings=warnings,
            next_actions=next_actions,
        ),
        encoding="utf-8",
    )
    return paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outputs = build_timeout_policy_sensitivity_review(args)
    print(f"Wrote timeout policy sensitivity review to {outputs['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
