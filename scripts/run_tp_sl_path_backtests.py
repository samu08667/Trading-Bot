"""Run research-only TP/SL path-exit diagnostics for fixed filter candidates.

The script evaluates already-discovered filters against historical OHLC paths in
``ml_dataset``. It does not connect to MetaTrader5 and does not contain broker
execution, order routing, or position-management logic.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
from datetime import datetime
import math
from pathlib import Path
import re
import sqlite3
import sys
from statistics import mean, median
from typing import Any, Callable


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from condition_utils import build_predicate
    from regime_classification import with_regime_labels
    from research_costs import (
        cost_report_fields,
        cost_report_warnings,
        estimate_total_cost_return,
        load_cost_config,
        validate_cost_args,
        validate_estimated_cost_config,
    )
    from research_metrics import csv_safe_value, normalize_direction, parse_metric_timestamp, safe_float
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_tp_sl_path_backtests
    from scripts.condition_utils import build_predicate
    from scripts.regime_classification import with_regime_labels
    from scripts.research_costs import (
        cost_report_fields,
        cost_report_warnings,
        estimate_total_cost_return,
        load_cost_config,
        validate_cost_args,
        validate_estimated_cost_config,
    )
    from scripts.research_metrics import csv_safe_value, normalize_direction, parse_metric_timestamp, safe_float


DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "tp_sl_path_backtests"
TABLE_NAME = "ml_dataset"

DETAIL_FILE = "tp_sl_path_backtest_detail.csv"
SUMMARY_FILE = "tp_sl_path_backtest_summary.csv"
REPORT_FILE = "tp_sl_path_backtest_report.md"
SKIPPED_FILE = "skipped_tp_sl_path_rows.csv"
OUTPUT_FILES = (DETAIL_FILE, SUMMARY_FILE, REPORT_FILE, SKIPPED_FILE)

DEFAULT_SYMBOL = "USDJPY"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_DIRECTION = "long"
DEFAULT_HORIZON = 10
DEFAULT_TP_ATR = 2.0
DEFAULT_SL_ATR = 1.0
DEFAULT_ATR_COLUMN = "atr_20"
DEFAULT_SAME_BAR_POLICY = "stop_first"
DEFAULT_MIN_TRADES = 200


SOURCE_METADATA_FIELDNAMES = [
    "source_input_row_number",
    "source_combination_id",
    "source_feature_1",
    "source_scenario_1",
    "source_feature_family_1",
    "source_feature_2",
    "source_scenario_2",
    "source_feature_family_2",
    "source_close_to_close_mean_return",
    "source_close_to_close_profit_factor",
    "source_close_to_close_notes",
]

REQUIRED_COMBINATION_COLUMNS = [
    "symbol",
    "direction",
    "feature_1",
    "scenario_1",
    "feature_family_1",
    "feature_2",
    "scenario_2",
    "feature_family_2",
    "combination_id",
]

SUMMARY_FIELDNAMES = [
    "scope",
    "symbol",
    "direction",
    "timeframe",
    "horizon",
    "tp_atr",
    "sl_atr",
    "atr_column",
    "same_bar_policy",
    "filters",
    *SOURCE_METADATA_FIELDNAMES,
    "trades_count",
    "tp_hit_count",
    "sl_hit_count",
    "timeout_count",
    "same_bar_conflict_count",
    "tp_hit_rate",
    "sl_hit_rate",
    "timeout_rate",
    "win_rate_R",
    "mean_R",
    "median_R",
    "profit_factor_R",
    "expectancy_R",
    "cumulative_R",
    "max_drawdown_R",
    "payoff_ratio_R",
    "breakeven_winrate",
    "breakeven_winrate_margin",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "top_5_percent_trades_contribution_pct",
    "baseline_trades_count",
    "baseline_tp_hit_rate",
    "baseline_mean_R",
    "baseline_profit_factor_R",
    "mean_R_vs_baseline",
    "profit_factor_R_vs_baseline",
    "candidate_skipped_path_rows_count",
    "baseline_skipped_path_rows_count",
    "cost_mode",
    "return_mode",
    "classification",
    "notes",
    "cost_config_source",
    "point_size_source",
    "spread_source_used",
    "symbols_using_default_costs",
]

DETAIL_FIELDNAMES = [
    "symbol",
    "direction",
    "timeframe",
    "time_server",
    "row_index",
    "entry_price",
    "atr",
    "sl_distance",
    "tp_price",
    "sl_price",
    "exit_time",
    "exit_bars",
    "exit_reason",
    "gross_R",
    "estimated_cost_return",
    "cost_R",
    "net_R",
    "selected_R",
    "same_bar_conflict",
    "filters",
    *SOURCE_METADATA_FIELDNAMES,
    "cost_mode",
    "return_mode",
]

SKIPPED_FIELDNAMES = [
    "scope",
    "symbol",
    "direction",
    "timeframe",
    "time_server",
    "row_index",
    "skip_reason",
    "filters",
    *SOURCE_METADATA_FIELDNAMES,
]


@dataclass(frozen=True)
class PathConfig:
    symbol: str
    timeframe: str
    direction: str
    horizon: int
    tp_atr: float
    sl_atr: float
    atr_column: str
    same_bar_policy: str
    filters: tuple[str, ...]
    cost_mode: str
    return_mode: str
    min_trades: int


@dataclass(frozen=True)
class CombinationCandidate:
    source_row_number: int
    source_row: dict[str, str]
    output_direction: str
    config: PathConfig
    source_metadata: dict[str, object]


@dataclass(frozen=True)
class PathOutcome:
    row: dict[str, object]
    row_index: int
    time_server: object
    exit_time: object
    exit_bars: int
    exit_reason: str
    entry_price: float
    atr: float
    sl_distance: float
    tp_price: float
    sl_price: float
    gross_R: float
    estimated_cost_return: float
    cost_R: float
    net_R: float
    selected_R: float
    same_bar_conflict: bool


RowPredicate = Callable[[dict[str, object]], bool]


TARGET_LABEL_RE = re.compile(
    r"^(long|short)_tp_([0-9]+(?:[._][0-9]+)?)atr_sl_([0-9]+(?:[._][0-9]+)?)atr_hit_first_([0-9]+)$"
)


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def read_csv_with_headers(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"Combination input CSV not found: {path}")
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def first_nonempty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def infer_direction_from_path(path: Path) -> str | None:
    for part in reversed(path.parts):
        lowered = part.lower()
        if lowered in {"long", "short"}:
            return lowered
    return None


def output_direction_for_skip(
    row: dict[str, str],
    *,
    args_direction: object,
    input_path: Path,
) -> str:
    try:
        direction_text = str(row.get("direction") or "").strip()
        if direction_text:
            return normalize_direction(direction_text)
    except ValueError:
        pass
    try:
        if args_direction:
            return normalize_direction(args_direction)
    except ValueError:
        pass
    return infer_direction_from_path(input_path) or "unknown"


def source_metadata_from_row(row: dict[str, str], source_row_number: int) -> dict[str, object]:
    return {
        "source_input_row_number": source_row_number,
        "source_combination_id": first_nonempty(row.get("source_combination_id"), row.get("combination_id")),
        "source_feature_1": first_nonempty(row.get("source_feature_1"), row.get("feature_1")),
        "source_scenario_1": first_nonempty(row.get("source_scenario_1"), row.get("scenario_1")),
        "source_feature_family_1": first_nonempty(row.get("source_feature_family_1"), row.get("feature_family_1")),
        "source_feature_2": first_nonempty(row.get("source_feature_2"), row.get("feature_2")),
        "source_scenario_2": first_nonempty(row.get("source_scenario_2"), row.get("scenario_2")),
        "source_feature_family_2": first_nonempty(row.get("source_feature_family_2"), row.get("feature_family_2")),
        "source_close_to_close_mean_return": first_nonempty(
            row.get("source_close_to_close_mean_return"),
            row.get("mean_return"),
        ),
        "source_close_to_close_profit_factor": first_nonempty(
            row.get("source_close_to_close_profit_factor"),
            row.get("profit_factor"),
        ),
        "source_close_to_close_notes": first_nonempty(row.get("source_close_to_close_notes"), row.get("notes")),
    }


def missing_combination_fields(row: dict[str, str]) -> list[str]:
    return [field for field in REQUIRED_COMBINATION_COLUMNS if not str(row.get(field) or "").strip()]


def skipped_combination_row(
    *,
    row: dict[str, str],
    source_row_number: int,
    output_direction: str,
    timeframe: str,
    skip_reason: str,
    source_metadata: dict[str, object] | None = None,
    filters: tuple[str, ...] = (),
) -> dict[str, object]:
    metadata = source_metadata or source_metadata_from_row(row, source_row_number)
    symbol = str(row.get("symbol") or "").strip().upper()
    return {
        "scope": "combination",
        "symbol": symbol,
        "direction": output_direction,
        "timeframe": timeframe,
        "time_server": "",
        "row_index": "",
        "skip_reason": skip_reason,
        "filters": " | ".join(filters),
        **metadata,
    }


def parse_target_label(label: str) -> dict[str, object]:
    match = TARGET_LABEL_RE.match(str(label or "").strip())
    if not match:
        raise ValueError(
            "--target-label must look like long_tp_2atr_sl_1atr_hit_first_10 "
            "or short_tp_1_5atr_sl_1atr_hit_first_10."
        )
    direction, tp_atr, sl_atr, horizon = match.groups()
    return {
        "direction": direction,
        "tp_atr": float(tp_atr.replace("_", ".")),
        "sl_atr": float(sl_atr.replace("_", ".")),
        "horizon": int(horizon),
    }


def resolve_config(args: argparse.Namespace) -> PathConfig:
    target_values = parse_target_label(args.target_label) if getattr(args, "target_label", None) else {}
    direction = normalize_direction(args.direction or target_values.get("direction") or DEFAULT_DIRECTION)
    horizon = int(args.horizon if args.horizon is not None else target_values.get("horizon", DEFAULT_HORIZON))
    tp_atr = float(args.tp_atr if args.tp_atr is not None else target_values.get("tp_atr", DEFAULT_TP_ATR))
    sl_atr = float(args.sl_atr if args.sl_atr is not None else target_values.get("sl_atr", DEFAULT_SL_ATR))
    if horizon <= 0:
        raise ValueError("--horizon must be greater than zero.")
    if tp_atr <= 0:
        raise ValueError("--tp-atr must be greater than zero.")
    if sl_atr <= 0:
        raise ValueError("--sl-atr must be greater than zero.")
    filters = tuple(str(item).strip() for item in (args.filters or []) if str(item).strip())
    combination_input_csv = getattr(args, "combination_input_csv", None)
    if filters and combination_input_csv:
        raise ValueError("--filter cannot be combined with --combination-input-csv; CSV rows define the filters.")
    if not filters and not combination_input_csv:
        raise ValueError("At least one --filter is required for this fixed-candidate diagnostic.")
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    return PathConfig(
        symbol=str(args.symbol or DEFAULT_SYMBOL).strip().upper(),
        timeframe=str(args.timeframe or DEFAULT_TIMEFRAME).strip().upper(),
        direction=direction,
        horizon=horizon,
        tp_atr=tp_atr,
        sl_atr=sl_atr,
        atr_column=str(args.atr_column or DEFAULT_ATR_COLUMN).strip(),
        same_bar_policy=str(args.same_bar_policy or DEFAULT_SAME_BAR_POLICY).strip(),
        filters=filters,
        cost_mode=cost_mode,
        return_mode=return_mode,
        min_trades=int(args.min_trades),
    )


def candidate_from_combination_row(
    row: dict[str, str],
    *,
    source_row_number: int,
    base_config: PathConfig,
    args_direction: object,
    input_path: Path,
) -> tuple[CombinationCandidate | None, dict[str, object] | None]:
    output_direction = output_direction_for_skip(row, args_direction=args_direction, input_path=input_path)
    metadata = source_metadata_from_row(row, source_row_number)

    symbol = str(row.get("symbol") or "").strip().upper()
    row_direction_text = str(row.get("direction") or "").strip()
    if not symbol:
        return None, skipped_combination_row(
            row=row,
            source_row_number=source_row_number,
            output_direction=output_direction,
            timeframe=base_config.timeframe,
            skip_reason="missing_symbol",
            source_metadata=metadata,
        )
    if not row_direction_text:
        return None, skipped_combination_row(
            row=row,
            source_row_number=source_row_number,
            output_direction=output_direction,
            timeframe=base_config.timeframe,
            skip_reason="missing_direction",
            source_metadata=metadata,
        )
    try:
        row_direction = normalize_direction(row_direction_text)
    except ValueError as exc:
        return None, skipped_combination_row(
            row=row,
            source_row_number=source_row_number,
            output_direction=output_direction,
            timeframe=base_config.timeframe,
            skip_reason=f"invalid_direction:{exc}",
            source_metadata=metadata,
        )

    missing_fields = missing_combination_fields(row)
    if missing_fields:
        return None, skipped_combination_row(
            row=row,
            source_row_number=source_row_number,
            output_direction=row_direction,
            timeframe=base_config.timeframe,
            skip_reason="missing_required_combination_fields:" + ",".join(missing_fields),
            source_metadata=metadata,
        )

    filters = (
        str(row.get("scenario_1") or "").strip(),
        str(row.get("scenario_2") or "").strip(),
    )
    candidate_config = replace(
        base_config,
        symbol=symbol,
        direction=row_direction,
        filters=filters,
    )
    return (
        CombinationCandidate(
            source_row_number=source_row_number,
            source_row=row,
            output_direction=row_direction,
            config=candidate_config,
            source_metadata=metadata,
        ),
        None,
    )


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def load_path_rows(db_path: Path, symbol: str, timeframe: str) -> list[dict[str, object]]:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        if not table_exists(connection, TABLE_NAME):
            raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")
        rows = connection.execute(
            f"""
            SELECT *
            FROM {TABLE_NAME}
            WHERE symbol = ?
              AND timeframe = ?
            ORDER BY time_server ASC
            """,
            (symbol, timeframe),
        ).fetchall()
    return [with_regime_labels(dict(row)) for row in rows]


def finite_value(value: object) -> float | None:
    parsed = safe_float(value)
    return parsed if parsed is not None and math.isfinite(parsed) else None


def skip_row(
    config: PathConfig,
    row: dict[str, object],
    row_index: int,
    scope: str,
    reason: str,
    source_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "scope": scope,
        "symbol": config.symbol,
        "direction": config.direction,
        "timeframe": config.timeframe,
        "time_server": row.get("time_server"),
        "row_index": row_index,
        "skip_reason": reason,
        "filters": " | ".join(config.filters),
        **(source_metadata or {}),
    }


def price_levels(entry_price: float, atr: float, config: PathConfig) -> tuple[float, float]:
    if config.direction == "long":
        return entry_price + config.tp_atr * atr, entry_price - config.sl_atr * atr
    return entry_price - config.tp_atr * atr, entry_price + config.sl_atr * atr


def hit_flags(high_price: float, low_price: float, tp_price: float, sl_price: float, direction: str) -> tuple[bool, bool]:
    if direction == "long":
        return high_price >= tp_price, low_price <= sl_price
    return low_price <= tp_price, high_price >= sl_price


def selected_exit(
    *,
    take_hit: bool,
    stop_hit: bool,
    same_bar_policy: str,
) -> tuple[str | None, bool]:
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


def cost_in_R(
    *,
    row: dict[str, object],
    symbol: str,
    entry_price: float,
    sl_distance: float,
    cost_config: dict[str, Any],
    cost_mode: str,
) -> tuple[float, float]:
    if cost_mode != "estimated":
        return 0.0, 0.0
    cost_return = estimate_total_cost_return(row, symbol, cost_config)
    cost_R = (cost_return * entry_price) / sl_distance if sl_distance > 0 else 0.0
    return cost_return, cost_R


def simulate_path_exit(
    rows: list[dict[str, object]],
    row_index: int,
    *,
    config: PathConfig,
    cost_config: dict[str, Any],
) -> tuple[PathOutcome | None, str | None]:
    row = rows[row_index]
    entry_price = finite_value(row.get("close"))
    if entry_price is None or entry_price <= 0:
        return None, "invalid_entry_close"

    atr = finite_value(row.get(config.atr_column))
    if atr is None or atr <= 0:
        return None, "invalid_or_missing_atr"

    if row_index + config.horizon >= len(rows):
        return None, "insufficient_future_bars"

    sl_distance = config.sl_atr * atr
    if sl_distance <= 0:
        return None, "invalid_sl_distance"

    tp_price, sl_price = price_levels(entry_price, atr, config)
    future_rows = rows[row_index + 1 : row_index + config.horizon + 1]
    gross_R: float | None = None
    exit_reason: str | None = None
    exit_bars: int | None = None
    exit_time: object = None
    same_bar_conflict = False

    for bars_ahead, future_row in enumerate(future_rows, start=1):
        high_price = finite_value(future_row.get("high"))
        low_price = finite_value(future_row.get("low"))
        if high_price is None or low_price is None:
            return None, "missing_future_ohlc"
        take_hit, stop_hit = hit_flags(high_price, low_price, tp_price, sl_price, config.direction)
        selected, conflict = selected_exit(
            take_hit=take_hit,
            stop_hit=stop_hit,
            same_bar_policy=config.same_bar_policy,
        )
        if selected is None:
            continue
        exit_reason = selected
        exit_bars = bars_ahead
        exit_time = future_row.get("time_server")
        same_bar_conflict = conflict
        gross_R = (config.tp_atr * atr) / sl_distance if selected == "tp" else -1.0
        break

    if exit_reason is None:
        horizon_row = future_rows[-1]
        horizon_close = finite_value(horizon_row.get("close"))
        if horizon_close is None:
            return None, "missing_horizon_close"
        exit_reason = "timeout"
        exit_bars = config.horizon
        exit_time = horizon_row.get("time_server")
        move = horizon_close - entry_price if config.direction == "long" else entry_price - horizon_close
        gross_R = move / sl_distance

    estimated_cost_return, cost_R = cost_in_R(
        row=row,
        symbol=config.symbol,
        entry_price=entry_price,
        sl_distance=sl_distance,
        cost_config=cost_config,
        cost_mode=config.cost_mode,
    )
    net_R = float(gross_R) - cost_R
    selected_R = net_R if config.return_mode == "net" else float(gross_R)

    return (
        PathOutcome(
            row=row,
            row_index=row_index,
            time_server=row.get("time_server"),
            exit_time=exit_time,
            exit_bars=int(exit_bars),
            exit_reason=exit_reason,
            entry_price=entry_price,
            atr=atr,
            sl_distance=sl_distance,
            tp_price=tp_price,
            sl_price=sl_price,
            gross_R=float(gross_R),
            estimated_cost_return=estimated_cost_return,
            cost_R=cost_R,
            net_R=net_R,
            selected_R=selected_R,
            same_bar_conflict=same_bar_conflict,
        ),
        None,
    )


def predicate_for_filters(
    rows_for_thresholds: list[dict[str, object]],
    filters: tuple[str, ...],
) -> RowPredicate:
    if not filters:
        return lambda _row: True
    combination_key = " AND ".join(filters)
    return build_predicate(
        rows_for_thresholds,
        combination_key,
        TABLE_NAME,
        allow_numeric_tercile=True,
    )


def evaluate_rows(
    rows: list[dict[str, object]],
    *,
    config: PathConfig,
    filters: tuple[str, ...],
    cost_config: dict[str, Any],
    scope: str,
    rows_for_thresholds: list[dict[str, object]] | None = None,
    source_metadata: dict[str, object] | None = None,
) -> tuple[list[PathOutcome], list[dict[str, object]]]:
    predicate = predicate_for_filters(rows_for_thresholds or rows, filters)
    outcomes: list[PathOutcome] = []
    skipped: list[dict[str, object]] = []
    for row_index, row in enumerate(rows):
        if not predicate(row):
            continue
        outcome, reason = simulate_path_exit(
            rows,
            row_index,
            config=config,
            cost_config=cost_config,
        )
        if outcome is None:
            skipped.append(
                skip_row(
                    config,
                    row,
                    row_index,
                    scope,
                    reason or "unknown_skip_reason",
                    source_metadata=source_metadata,
                )
            )
            continue
        outcomes.append(outcome)
    return outcomes, skipped


def profit_factor(values: list[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return None if gains == 0 else float("inf")
    return gains / losses


def payoff_ratio(values: list[float]) -> float | None:
    positives = [value for value in values if value > 0]
    negatives = [value for value in values if value < 0]
    if not positives or not negatives:
        return None
    avg_positive = mean(positives)
    avg_negative = mean(negatives)
    if avg_positive <= 0 or avg_negative == 0:
        return None
    return avg_positive / abs(avg_negative)


def breakeven_winrate(payoff: float | None) -> float | None:
    if payoff is None or not math.isfinite(payoff) or payoff <= 0:
        return None
    return 1 / (1 + payoff)


def max_drawdown_R(values: list[float]) -> float | None:
    if not values:
        return None
    cumulative = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        worst = min(worst, cumulative - peak)
    return worst


def period_key(timestamp_value: object, period: str) -> tuple[int, int] | None:
    timestamp = parse_metric_timestamp(timestamp_value)
    if timestamp is None:
        return None
    if period == "month":
        return timestamp.year, timestamp.month
    if period == "quarter":
        return timestamp.year, (timestamp.month - 1) // 3 + 1
    raise ValueError(f"Unsupported period: {period}")


def period_positive_ratio(outcomes: list[PathOutcome], period: str) -> float | None:
    grouped: dict[tuple[int, int], float] = {}
    for outcome in outcomes:
        key = period_key(outcome.time_server, period)
        if key is None:
            continue
        grouped[key] = grouped.get(key, 0.0) + outcome.selected_R
    if not grouped:
        return None
    values = [grouped[key] for key in sorted(grouped)]
    return sum(1 for value in values if value > 0) / len(values)


def top_trade_contribution_pct(values: list[float], top_fraction: float = 0.05) -> float | None:
    positive_total = sum(value for value in values if value > 0)
    if positive_total <= 0:
        return None
    top_count = max(1, math.ceil(len(values) * top_fraction))
    top_positive = sum(value for value in sorted(values, reverse=True)[:top_count] if value > 0)
    return top_positive / positive_total * 100


def metrics_from_outcomes(outcomes: list[PathOutcome]) -> dict[str, object]:
    values = [outcome.selected_R for outcome in outcomes]
    count = len(values)
    positives = [value for value in values if value > 0]
    payoff = payoff_ratio(values)
    breakeven = breakeven_winrate(payoff)
    win_rate = (len(positives) / count) if count else None
    tp_hit_count = sum(1 for outcome in outcomes if outcome.exit_reason == "tp")
    sl_hit_count = sum(1 for outcome in outcomes if outcome.exit_reason == "sl")
    timeout_count = sum(1 for outcome in outcomes if outcome.exit_reason == "timeout")
    return {
        "trades_count": count,
        "tp_hit_count": tp_hit_count,
        "sl_hit_count": sl_hit_count,
        "timeout_count": timeout_count,
        "same_bar_conflict_count": sum(1 for outcome in outcomes if outcome.same_bar_conflict),
        "tp_hit_rate": (tp_hit_count / count) if count else None,
        "sl_hit_rate": (sl_hit_count / count) if count else None,
        "timeout_rate": (timeout_count / count) if count else None,
        "win_rate_R": win_rate,
        "mean_R": mean(values) if values else None,
        "median_R": median(values) if values else None,
        "profit_factor_R": profit_factor(values),
        "expectancy_R": mean(values) if values else None,
        "cumulative_R": sum(values) if values else None,
        "max_drawdown_R": max_drawdown_R(values),
        "payoff_ratio_R": payoff,
        "breakeven_winrate": breakeven,
        "breakeven_winrate_margin": (win_rate - breakeven) if win_rate is not None and breakeven is not None else None,
        "monthly_positive_ratio": period_positive_ratio(outcomes, "month"),
        "quarterly_positive_ratio": period_positive_ratio(outcomes, "quarter"),
        "top_5_percent_trades_contribution_pct": top_trade_contribution_pct(values),
    }


def metric_delta(value: object, baseline: object) -> float | None:
    parsed_value = finite_value(value)
    parsed_baseline = finite_value(baseline)
    if parsed_value is None or parsed_baseline is None:
        return None
    return parsed_value - parsed_baseline


def classify_candidate(metrics: dict[str, object], baseline: dict[str, object], min_trades: int) -> tuple[str, str]:
    mean_R = finite_value(metrics.get("mean_R"))
    profit = finite_value(metrics.get("profit_factor_R"))
    mean_delta = metric_delta(metrics.get("mean_R"), baseline.get("mean_R"))
    profit_delta = metric_delta(metrics.get("profit_factor_R"), baseline.get("profit_factor_R"))
    trades_count = int(metrics.get("trades_count") or 0)
    top_contribution = finite_value(metrics.get("top_5_percent_trades_contribution_pct"))
    monthly = finite_value(metrics.get("monthly_positive_ratio"))
    quarterly = finite_value(metrics.get("quarterly_positive_ratio"))

    baseline_beaten = (
        mean_delta is not None
        and profit_delta is not None
        and mean_delta > 0
        and profit_delta > 0
    )
    concentration_ok = top_contribution is None or top_contribution <= 50.0
    periods_ok = (
        monthly is not None
        and quarterly is not None
        and monthly >= 0.55
        and quarterly >= 0.55
    )
    enough_trades = trades_count >= min_trades

    if (
        mean_R is not None
        and profit is not None
        and mean_R > 0
        and profit > 1.05
        and baseline_beaten
        and enough_trades
        and concentration_ok
        and periods_ok
    ):
        return "CANDIDATA_A_TEST_SUCCESSIVI", "passes the stricter fixed-diagnostic thresholds"
    if (
        mean_R is not None
        and profit is not None
        and mean_R > 0
        and profit > 1.0
        and baseline_beaten
        and enough_trades
    ):
        return "DA_APPROFONDIRE", "positive but weak or borderline on the conservative checks"
    return "SCARTARE", "does not beat the fixed diagnostic guardrails"


def summary_row(
    *,
    scope: str,
    filters: tuple[str, ...],
    metrics: dict[str, object],
    baseline: dict[str, object],
    config: PathConfig,
    cost_fields: dict[str, str],
    classification: str = "",
    notes: str = "",
    source_metadata: dict[str, object] | None = None,
    extra_fields: dict[str, object] | None = None,
) -> dict[str, object]:
    row = {
        "scope": scope,
        "symbol": config.symbol,
        "direction": config.direction,
        "timeframe": config.timeframe,
        "horizon": config.horizon,
        "tp_atr": config.tp_atr,
        "sl_atr": config.sl_atr,
        "atr_column": config.atr_column,
        "same_bar_policy": config.same_bar_policy,
        "filters": " | ".join(filters) if filters else "ALL_VALID_ROWS",
        "baseline_trades_count": baseline.get("trades_count"),
        "baseline_tp_hit_rate": baseline.get("tp_hit_rate"),
        "baseline_mean_R": baseline.get("mean_R"),
        "baseline_profit_factor_R": baseline.get("profit_factor_R"),
        "mean_R_vs_baseline": metric_delta(metrics.get("mean_R"), baseline.get("mean_R")),
        "profit_factor_R_vs_baseline": metric_delta(metrics.get("profit_factor_R"), baseline.get("profit_factor_R")),
        "candidate_skipped_path_rows_count": "",
        "baseline_skipped_path_rows_count": "",
        "cost_mode": config.cost_mode,
        "return_mode": config.return_mode,
        "classification": classification,
        "notes": notes,
        **cost_fields,
    }
    if source_metadata:
        row.update(source_metadata)
    if extra_fields:
        row.update(extra_fields)
    row.update(metrics)
    return row


def detail_row(
    outcome: PathOutcome,
    config: PathConfig,
    source_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "symbol": config.symbol,
        "direction": config.direction,
        "timeframe": config.timeframe,
        "time_server": outcome.time_server,
        "row_index": outcome.row_index,
        "entry_price": outcome.entry_price,
        "atr": outcome.atr,
        "sl_distance": outcome.sl_distance,
        "tp_price": outcome.tp_price,
        "sl_price": outcome.sl_price,
        "exit_time": outcome.exit_time,
        "exit_bars": outcome.exit_bars,
        "exit_reason": outcome.exit_reason,
        "gross_R": outcome.gross_R,
        "estimated_cost_return": outcome.estimated_cost_return,
        "cost_R": outcome.cost_R,
        "net_R": outcome.net_R,
        "selected_R": outcome.selected_R,
        "same_bar_conflict": int(outcome.same_bar_conflict),
        "filters": " | ".join(config.filters),
        **(source_metadata or {}),
        "cost_mode": config.cost_mode,
        "return_mode": config.return_mode,
    }


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe_value(row.get(field)) for field in fieldnames})


def pct_text(value: object) -> str:
    parsed = finite_value(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.2%}"


def num_text(value: object, digits: int = 6) -> str:
    parsed = finite_value(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.{digits}f}"


def report_filter_lines(filters: tuple[str, ...]) -> list[str]:
    return [f"- `{item}`" for item in filters] if filters else ["- none"]


def report_single_filter_lines(rows: list[dict[str, object]]) -> list[str]:
    selected = [row for row in rows if str(row.get("scope", "")).startswith("single_filter_")]
    if not selected:
        return ["- Single-filter baselines were not available for this run."]
    return [
        "- `{filters}`: trades={trades}, mean_R={mean_R}, profit_factor_R={pf}, mean_R_vs_baseline={delta}".format(
            filters=row.get("filters", ""),
            trades=row.get("trades_count", ""),
            mean_R=num_text(row.get("mean_R")),
            pf=num_text(row.get("profit_factor_R")),
            delta=num_text(row.get("mean_R_vs_baseline")),
        )
        for row in selected
    ]


def write_report(
    path: Path,
    *,
    config: PathConfig,
    candidate_row: dict[str, object],
    baseline_row: dict[str, object],
    summary_rows: list[dict[str, object]],
    skipped_rows: list[dict[str, object]],
    cost_warnings: list[str],
) -> None:
    lines = [
        "# TP/SL Path Backtest Report",
        "",
        "## Research-only warning",
        "",
        "- Offline diagnostic for fixed historical filters only.",
        "- Not operational guidance, not broker execution, and not deployment-ready.",
        "",
        "## Configuration",
        "",
        f"- Symbol: `{config.symbol}`",
        f"- Timeframe: `{config.timeframe}`",
        f"- Direction: `{config.direction}`",
        f"- Horizon bars: `{config.horizon}`",
        f"- TP ATR multiple: `{config.tp_atr}`",
        f"- SL ATR multiple: `{config.sl_atr}`",
        f"- ATR column: `{config.atr_column}`",
        f"- Same-bar policy: `{config.same_bar_policy}`",
        f"- Cost mode: `{config.cost_mode}`",
        f"- Return mode: `{config.return_mode}`",
        f"- Cost config source: `{candidate_row.get('cost_config_source', '')}`",
        f"- Point-size source: `{candidate_row.get('point_size_source', '')}`",
        f"- Spread source used: `{candidate_row.get('spread_source_used', '')}`",
        "",
        "## Path-exit assumptions",
        "",
        "- Entry price is the current row close.",
        "- TP and SL levels use the current-row ATR value.",
        "- For long rows, TP is entry plus TP ATR multiple times ATR; SL is entry minus SL ATR multiple times ATR.",
        "- For short rows, TP is entry minus TP ATR multiple times ATR; SL is entry plus SL ATR multiple times ATR.",
        "- When one future OHLC bar touches both levels, `stop_first` classifies the SL first.",
        "- When neither level is touched within the horizon, the row exits at the horizon close.",
        "- Net R subtracts estimated round-trip costs converted into SL-distance R units.",
        "",
        "## Candidate filters",
        "",
        *report_filter_lines(config.filters),
        "",
        "## Main result",
        "",
        f"- Classification: `{candidate_row.get('classification', '')}`",
        f"- Notes: {candidate_row.get('notes', '')}",
        f"- Trades: `{candidate_row.get('trades_count', '')}`",
        f"- TP hit rate: `{pct_text(candidate_row.get('tp_hit_rate'))}`",
        f"- SL hit rate: `{pct_text(candidate_row.get('sl_hit_rate'))}`",
        f"- Timeout rate: `{pct_text(candidate_row.get('timeout_rate'))}`",
        f"- Mean R: `{num_text(candidate_row.get('mean_R'))}`",
        f"- Profit factor R: `{num_text(candidate_row.get('profit_factor_R'))}`",
        f"- Expectancy R: `{num_text(candidate_row.get('expectancy_R'))}`",
        f"- Max drawdown R: `{num_text(candidate_row.get('max_drawdown_R'))}`",
        f"- Monthly positive ratio: `{pct_text(candidate_row.get('monthly_positive_ratio'))}`",
        f"- Quarterly positive ratio: `{pct_text(candidate_row.get('quarterly_positive_ratio'))}`",
        f"- Top 5 percent contribution pct: `{num_text(candidate_row.get('top_5_percent_trades_contribution_pct'), 2)}`",
        "",
        "## Baseline comparison",
        "",
        f"- Baseline trades: `{baseline_row.get('trades_count', '')}`",
        f"- Baseline TP hit rate: `{pct_text(baseline_row.get('tp_hit_rate'))}`",
        f"- Baseline mean R: `{num_text(baseline_row.get('mean_R'))}`",
        f"- Baseline profit factor R: `{num_text(baseline_row.get('profit_factor_R'))}`",
        f"- Mean R vs baseline: `{num_text(candidate_row.get('mean_R_vs_baseline'))}`",
        f"- Profit factor R vs baseline: `{num_text(candidate_row.get('profit_factor_R_vs_baseline'))}`",
        "",
        "### Single-filter baselines",
        "",
        *report_single_filter_lines(summary_rows),
        "",
        "## Skipped rows",
        "",
        f"- Candidate skipped rows: `{len(skipped_rows)}`",
    ]
    if skipped_rows[:10]:
        lines.extend(
            f"- Row `{row.get('row_index')}` at `{row.get('time_server')}`: `{row.get('skip_reason')}`"
            for row in skipped_rows[:10]
        )
    lines.extend(
        [
            "",
            "## Methodology warnings",
            "",
            "- This run does not optimize TP, SL, horizon, features, or thresholds.",
            "- Numeric tercile filters are applied as fixed diagnostic buckets on the loaded historical universe.",
            "- Estimated net R depends on cost assumptions and broker point-size quality.",
            "- Same-bar OHLC ordering is unknown, so the default policy is conservative.",
            "- Rows with invalid ATR, invalid entry close, or incomplete future path are skipped.",
            "",
            "## Interpretation guardrails",
            "",
            "- `SCARTARE`: discard for now under these fixed assumptions.",
            "- `DA_APPROFONDIRE`: worth deeper offline review, but still weak or borderline.",
            "- `CANDIDATA_A_TEST_SUCCESSIVI`: may deserve later offline follow-up tests.",
            "- A favorable label here is not a deployment artifact.",
        ]
    )
    if cost_warnings:
        lines.extend(["", "## Cost warnings", ""])
        lines.extend(f"- {warning}" for warning in cost_warnings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def output_dir_for(output_root: Path, run_id: str, direction: str) -> Path:
    return Path(output_root) / run_id / direction


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> None:
    existing = [output_dir / file_name for file_name in OUTPUT_FILES if (output_dir / file_name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"TP/SL path backtest outputs already exist under {output_dir}. Pass --overwrite to regenerate them."
        )


def build_outputs(
    *,
    rows: list[dict[str, object]],
    config: PathConfig,
    cost_config: dict[str, Any],
    cost_fields: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    baseline_outcomes, baseline_skipped = evaluate_rows(
        rows,
        config=config,
        filters=(),
        cost_config=cost_config,
        scope="baseline_all",
    )
    rows_for_thresholds = [outcome.row for outcome in baseline_outcomes] or rows
    baseline_metrics = metrics_from_outcomes(baseline_outcomes)

    candidate_outcomes, candidate_skipped = evaluate_rows(
        rows,
        config=config,
        filters=config.filters,
        cost_config=cost_config,
        scope="candidate",
        rows_for_thresholds=rows_for_thresholds,
    )
    candidate_metrics = metrics_from_outcomes(candidate_outcomes)
    classification, notes = classify_candidate(candidate_metrics, baseline_metrics, config.min_trades)

    candidate_row = summary_row(
        scope="candidate",
        filters=config.filters,
        metrics=candidate_metrics,
        baseline=baseline_metrics,
        config=config,
        cost_fields=cost_fields,
        classification=classification,
        notes=notes,
        extra_fields={
            "candidate_skipped_path_rows_count": len(candidate_skipped),
            "baseline_skipped_path_rows_count": len(baseline_skipped),
        },
    )
    baseline_row = summary_row(
        scope="baseline_all",
        filters=(),
        metrics=baseline_metrics,
        baseline=baseline_metrics,
        config=config,
        cost_fields=cost_fields,
        classification="",
        notes="same symbol, direction, timeframe, horizon, and valid path rows",
        extra_fields={
            "candidate_skipped_path_rows_count": "",
            "baseline_skipped_path_rows_count": len(baseline_skipped),
        },
    )

    summary_rows = [candidate_row, baseline_row]
    for index, filter_key in enumerate(config.filters, start=1):
        single_outcomes, _single_skipped = evaluate_rows(
            rows,
            config=config,
            filters=(filter_key,),
            cost_config=cost_config,
            scope=f"single_filter_{index}",
            rows_for_thresholds=rows_for_thresholds,
        )
        single_metrics = metrics_from_outcomes(single_outcomes)
        summary_rows.append(
            summary_row(
                scope=f"single_filter_{index}",
                filters=(filter_key,),
                metrics=single_metrics,
                baseline=baseline_metrics,
                config=config,
                cost_fields=cost_fields,
                classification="",
                notes="single-filter baseline",
            )
        )

    detail_rows = [detail_row(outcome, config) for outcome in candidate_outcomes]
    return detail_rows, summary_rows, candidate_skipped


def missing_path_columns(rows: list[dict[str, object]], atr_column: str) -> list[str]:
    if not rows:
        return []
    required_columns = {"time_server", "high", "low", "close", atr_column}
    return sorted(column for column in required_columns if column not in rows[0])


def build_batch_candidate_row(
    *,
    rows: list[dict[str, object]],
    candidate: CombinationCandidate,
    cost_config: dict[str, Any],
    cost_fields: dict[str, str],
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    config = candidate.config
    metadata = candidate.source_metadata
    baseline_outcomes, baseline_skipped = evaluate_rows(
        rows,
        config=config,
        filters=(),
        cost_config=cost_config,
        scope="baseline_all",
    )
    rows_for_thresholds = [outcome.row for outcome in baseline_outcomes] or rows
    baseline_metrics = metrics_from_outcomes(baseline_outcomes)

    candidate_outcomes, candidate_skipped = evaluate_rows(
        rows,
        config=config,
        filters=config.filters,
        cost_config=cost_config,
        scope="candidate_path_row",
        rows_for_thresholds=rows_for_thresholds,
        source_metadata=metadata,
    )
    if not candidate_outcomes:
        skip_reason = (
            "no_valid_trades_after_path_validation"
            if candidate_skipped
            else "no_rows_matched_combination_filters"
        )
        return None, [
            *candidate_skipped,
            skipped_combination_row(
                row=candidate.source_row,
                source_row_number=candidate.source_row_number,
                output_direction=candidate.output_direction,
                timeframe=config.timeframe,
                skip_reason=skip_reason,
                source_metadata=metadata,
                filters=config.filters,
            ),
        ]

    candidate_metrics = metrics_from_outcomes(candidate_outcomes)
    classification, notes = classify_candidate(candidate_metrics, baseline_metrics, config.min_trades)
    return (
        summary_row(
            scope="combination",
            filters=config.filters,
            metrics=candidate_metrics,
            baseline=baseline_metrics,
            config=config,
            cost_fields=cost_fields,
            classification=classification,
            notes=notes,
            source_metadata=metadata,
            extra_fields={
                "candidate_skipped_path_rows_count": len(candidate_skipped),
                "baseline_skipped_path_rows_count": len(baseline_skipped),
            },
        ),
        candidate_skipped,
    )


def classification_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    labels = ["SCARTARE", "DA_APPROFONDIRE", "CANDIDATA_A_TEST_SUCCESSIVI"]
    counts = {label: 0 for label in labels}
    for row in rows:
        label = str(row.get("classification") or "")
        if label:
            counts[label] = counts.get(label, 0) + 1
    return counts


def batch_top_lines(rows: list[dict[str, object]], column: str, limit: int = 10) -> list[str]:
    selected = [
        row
        for row in rows
        if finite_value(row.get(column)) is not None
    ]
    if not selected:
        return ["- None."]
    selected.sort(
        key=lambda row: (
            -(finite_value(row.get(column)) or float("-inf")),
            str(row.get("symbol") or ""),
            str(row.get("source_combination_id") or ""),
        )
    )
    return [
        "- {symbol} `{combo}`: trades={trades}, mean_R={mean_R}, profit_factor_R={pf}, classification={classification}".format(
            symbol=row.get("symbol", ""),
            combo=row.get("source_combination_id", ""),
            trades=row.get("trades_count", ""),
            mean_R=num_text(row.get("mean_R")),
            pf=num_text(row.get("profit_factor_R")),
            classification=row.get("classification", ""),
        )
        for row in selected[:limit]
    ]


def improved_but_failed_lines(rows: list[dict[str, object]], limit: int = 20) -> list[str]:
    selected = [
        row
        for row in rows
        if row.get("classification") == "SCARTARE"
        and (finite_value(row.get("mean_R_vs_baseline")) or 0.0) > 0
        and (finite_value(row.get("profit_factor_R_vs_baseline")) or 0.0) > 0
    ]
    if not selected:
        return ["- None."]
    selected.sort(
        key=lambda row: (
            -(finite_value(row.get("mean_R_vs_baseline")) or float("-inf")),
            -(finite_value(row.get("profit_factor_R_vs_baseline")) or float("-inf")),
        )
    )
    return [
        "- {symbol} `{combo}`: mean_R_vs_baseline={mean_delta}, profit_factor_R_vs_baseline={pf_delta}, mean_R={mean_R}, profit_factor_R={pf}".format(
            symbol=row.get("symbol", ""),
            combo=row.get("source_combination_id", ""),
            mean_delta=num_text(row.get("mean_R_vs_baseline")),
            pf_delta=num_text(row.get("profit_factor_R_vs_baseline")),
            mean_R=num_text(row.get("mean_R")),
            pf=num_text(row.get("profit_factor_R")),
        )
        for row in selected[:limit]
    ]


def skipped_combination_lines(rows: list[dict[str, object]], limit: int = 25) -> list[str]:
    selected = [row for row in rows if str(row.get("scope") or "") == "combination"]
    if not selected:
        return ["- None."]
    return [
        "- row {source_row} {symbol} `{combo}`: {reason}".format(
            source_row=row.get("source_input_row_number", ""),
            symbol=row.get("symbol", ""),
            combo=row.get("source_combination_id", ""),
            reason=row.get("skip_reason", ""),
        )
        for row in selected[:limit]
    ]


def write_batch_report(
    path: Path,
    *,
    direction: str,
    config: PathConfig,
    input_path: Path,
    input_count: int,
    result_rows: list[dict[str, object]],
    skipped_rows: list[dict[str, object]],
    cost_warnings: list[str],
) -> None:
    counts = classification_counts(result_rows)
    skipped_combinations_count = sum(1 for row in skipped_rows if str(row.get("scope") or "") == "combination")
    lines = [
        "# TP/SL Path Backtest Batch Report",
        "",
        "## Research-only warning",
        "",
        "- Offline diagnostic for fixed historical filter rows only.",
        "- Not operational guidance, not broker execution, and not deployment-ready.",
        "",
        "## Configuration",
        "",
        f"- Direction output: `{direction}`",
        f"- Timeframe: `{config.timeframe}`",
        f"- Horizon bars: `{config.horizon}`",
        f"- TP ATR multiple: `{config.tp_atr}`",
        f"- SL ATR multiple: `{config.sl_atr}`",
        f"- ATR column: `{config.atr_column}`",
        f"- Same-bar policy: `{config.same_bar_policy}`",
        f"- Cost mode: `{config.cost_mode}`",
        f"- Return mode: `{config.return_mode}`",
        "",
        "## Batch input",
        "",
        f"- Input CSV: `{input_path}`",
        f"- Input combination rows: `{input_count}`",
        f"- Tested combinations: `{len(result_rows)}`",
        f"- Skipped combinations: `{skipped_combinations_count}`",
        "",
        "## Path-exit assumptions",
        "",
        "- Entry price is the current row close.",
        "- TP and SL levels use the current-row ATR value.",
        "- Direction-specific TP and SL levels are checked against the next historical OHLC bars.",
        f"- Same-bar TP/SL touches use `{config.same_bar_policy}`.",
        "- When neither level is touched within the horizon, the row exits at the horizon close.",
        "- Net R subtracts estimated round-trip costs converted into SL-distance R units.",
        "",
        "## Summary by classification",
        "",
        f"- SCARTARE: `{counts.get('SCARTARE', 0)}`",
        f"- DA_APPROFONDIRE: `{counts.get('DA_APPROFONDIRE', 0)}`",
        f"- CANDIDATA_A_TEST_SUCCESSIVI: `{counts.get('CANDIDATA_A_TEST_SUCCESSIVI', 0)}`",
        "",
        "## Top path-exit rows by profit_factor_R",
        "",
        *batch_top_lines(result_rows, "profit_factor_R"),
        "",
        "## Top path-exit rows by mean_R",
        "",
        *batch_top_lines(result_rows, "mean_R"),
        "",
        "## Rows that improved versus baseline but still failed",
        "",
        *improved_but_failed_lines(result_rows),
        "",
        "## Skipped combinations",
        "",
        *skipped_combination_lines(skipped_rows),
        "",
        "## Methodology warnings",
        "",
        "- This run does not optimize TP, SL, horizon, features, or thresholds.",
        "- No new feature pairs are created; each tested row comes from the provided combination CSV.",
        "- Numeric tercile filters are applied as fixed diagnostic buckets on the loaded historical universe.",
        "- Estimated net R depends on cost assumptions and broker point-size quality.",
        "- Same-bar OHLC ordering is unknown, so conservative ordering should be preferred.",
        "- Rows with invalid ATR, invalid entry close, or incomplete future path are skipped or counted in candidate audit columns.",
        "",
        "## Interpretation guardrails",
        "",
        "- `SCARTARE`: discard for now under these fixed assumptions.",
        "- `DA_APPROFONDIRE`: worth deeper offline review, but still weak or borderline.",
        "- `CANDIDATA_A_TEST_SUCCESSIVI`: may deserve later offline follow-up tests.",
        "- A favorable label here is not a deployment artifact.",
    ]
    if cost_warnings:
        lines.extend(["", "## Cost warnings", ""])
        lines.extend(f"- {warning}" for warning in cost_warnings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def batch_output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "tp_sl_path_backtest_detail": output_dir / DETAIL_FILE,
        "tp_sl_path_backtest_summary": output_dir / SUMMARY_FILE,
        "tp_sl_path_backtest_report": output_dir / REPORT_FILE,
        "skipped_tp_sl_path_rows": output_dir / SKIPPED_FILE,
    }


def flatten_direction_outputs(outputs_by_direction: dict[str, dict[str, Path]]) -> dict[str, Path]:
    if len(outputs_by_direction) == 1:
        return next(iter(outputs_by_direction.values()))
    flattened: dict[str, Path] = {}
    for direction, outputs in sorted(outputs_by_direction.items()):
        for label, path in outputs.items():
            flattened[f"{direction}_{label}"] = path
    return flattened


def run_combination_batch_backtests(args: argparse.Namespace, base_config: PathConfig) -> dict[str, Path]:
    input_path = Path(args.combination_input_csv)
    source_rows, _headers = read_csv_with_headers(input_path)
    run_id = str(args.run_id or current_run_id())
    cost_config = load_cost_config(args.cost_config)

    candidates_by_direction: dict[str, list[CombinationCandidate]] = {}
    skipped_by_direction: dict[str, list[dict[str, object]]] = {}
    for source_row_number, row in enumerate(source_rows, start=1):
        candidate, skipped = candidate_from_combination_row(
            row,
            source_row_number=source_row_number,
            base_config=base_config,
            args_direction=getattr(args, "direction", None),
            input_path=input_path,
        )
        if skipped is not None:
            direction = str(skipped.get("direction") or "unknown")
            skipped_by_direction.setdefault(direction, []).append(skipped)
            continue
        if candidate is not None:
            candidates_by_direction.setdefault(candidate.output_direction, []).append(candidate)

    output_directions = sorted(set(candidates_by_direction) | set(skipped_by_direction))
    if not output_directions:
        fallback_direction = (
            normalize_direction(args.direction)
            if getattr(args, "direction", None)
            else infer_direction_from_path(input_path) or base_config.direction
        )
        output_directions = [fallback_direction]

    output_root = Path(args.output_root)
    output_dirs = {
        direction: output_dir_for(output_root, run_id, direction)
        for direction in output_directions
    }
    for output_dir in output_dirs.values():
        ensure_outputs_writable(output_dir, bool(args.overwrite))

    row_cache: dict[tuple[str, str], list[dict[str, object]]] = {}
    cost_report_cache: dict[str, dict[str, dict[str, object]]] = {}
    warnings_by_direction: dict[str, list[str]] = {direction: [] for direction in output_directions}
    result_rows_by_direction: dict[str, list[dict[str, object]]] = {
        direction: [] for direction in output_directions
    }
    skipped_by_direction = {
        direction: list(skipped_by_direction.get(direction, []))
        for direction in output_directions
    }

    for direction in output_directions:
        for candidate in candidates_by_direction.get(direction, []):
            config = candidate.config
            cache_key = (config.symbol, config.timeframe)
            if cache_key not in row_cache:
                row_cache[cache_key] = load_path_rows(Path(args.db_path), config.symbol, config.timeframe)
            rows = row_cache[cache_key]
            if not rows:
                skipped_by_direction[direction].append(
                    skipped_combination_row(
                        row=candidate.source_row,
                        source_row_number=candidate.source_row_number,
                        output_direction=direction,
                        timeframe=config.timeframe,
                        skip_reason="no_ml_dataset_rows_for_symbol_timeframe",
                        source_metadata=candidate.source_metadata,
                        filters=config.filters,
                    )
                )
                continue

            missing_columns = missing_path_columns(rows, config.atr_column)
            if missing_columns:
                skipped_by_direction[direction].append(
                    skipped_combination_row(
                        row=candidate.source_row,
                        source_row_number=candidate.source_row_number,
                        output_direction=direction,
                        timeframe=config.timeframe,
                        skip_reason="ml_dataset_missing_required_columns:" + ",".join(missing_columns),
                        source_metadata=candidate.source_metadata,
                        filters=config.filters,
                    )
                )
                continue

            if config.cost_mode == "estimated" and config.symbol not in cost_report_cache:
                cost_report = validate_estimated_cost_config(
                    symbols=[config.symbol],
                    rows_by_symbol={config.symbol: rows},
                    config=cost_config,
                    strict=bool(args.strict_cost_config),
                )
                cost_report_cache[config.symbol] = cost_report
                cost_warnings = cost_report_warnings(cost_report)
                warnings_by_direction[direction].extend(cost_warnings)
                for warning in cost_warnings:
                    print(f"Warning: {warning}")
            cost_report = cost_report_cache.get(config.symbol, {})
            cost_fields = cost_report_fields(cost_report, config.symbol)

            try:
                result_row, candidate_skipped = build_batch_candidate_row(
                    rows=rows,
                    candidate=candidate,
                    cost_config=cost_config,
                    cost_fields=cost_fields,
                )
            except ValueError as exc:
                skipped_by_direction[direction].append(
                    skipped_combination_row(
                        row=candidate.source_row,
                        source_row_number=candidate.source_row_number,
                        output_direction=direction,
                        timeframe=config.timeframe,
                        skip_reason=f"filter_parse_or_apply_failed:{exc}",
                        source_metadata=candidate.source_metadata,
                        filters=config.filters,
                    )
                )
                continue

            skipped_by_direction[direction].extend(candidate_skipped)
            if result_row is not None:
                result_rows_by_direction[direction].append(result_row)

    outputs_by_direction: dict[str, dict[str, Path]] = {}
    for direction in output_directions:
        direction_config = replace(base_config, direction=direction, filters=())
        outputs = batch_output_paths(output_dirs[direction])
        result_rows = result_rows_by_direction[direction]
        skipped_rows = skipped_by_direction[direction]
        write_csv(outputs["tp_sl_path_backtest_detail"], result_rows, SUMMARY_FIELDNAMES)
        write_csv(outputs["tp_sl_path_backtest_summary"], result_rows, SUMMARY_FIELDNAMES)
        write_csv(outputs["skipped_tp_sl_path_rows"], skipped_rows, SKIPPED_FIELDNAMES)
        write_batch_report(
            outputs["tp_sl_path_backtest_report"],
            direction=direction,
            config=direction_config,
            input_path=input_path,
            input_count=len(source_rows),
            result_rows=result_rows,
            skipped_rows=skipped_rows,
            cost_warnings=warnings_by_direction.get(direction, []),
        )
        outputs_by_direction[direction] = outputs

    return flatten_direction_outputs(outputs_by_direction)


def run_tp_sl_path_backtests(args: argparse.Namespace) -> dict[str, Path]:
    config = resolve_config(args)
    if getattr(args, "combination_input_csv", None):
        return run_combination_batch_backtests(args, config)
    run_id = str(args.run_id or current_run_id())
    output_dir = output_dir_for(Path(args.output_root), run_id, config.direction)
    ensure_outputs_writable(output_dir, bool(args.overwrite))

    rows = load_path_rows(Path(args.db_path), config.symbol, config.timeframe)
    if not rows:
        raise ValueError(f"No ml_dataset rows found for {config.symbol} {config.timeframe}.")

    required_columns = {"time_server", "high", "low", "close", config.atr_column}
    missing_columns = sorted(column for column in required_columns if column not in rows[0])
    if missing_columns:
        raise ValueError(f"ml_dataset is missing required columns: {', '.join(missing_columns)}")

    cost_config = load_cost_config(args.cost_config)
    cost_report: dict[str, dict[str, object]] = {}
    cost_warnings: list[str] = []
    if config.cost_mode == "estimated":
        cost_report = validate_estimated_cost_config(
            symbols=[config.symbol],
            rows_by_symbol={config.symbol: rows},
            config=cost_config,
            strict=bool(args.strict_cost_config),
        )
        cost_warnings = cost_report_warnings(cost_report)
        for warning in cost_warnings:
            print(f"Warning: {warning}")
    cost_fields = cost_report_fields(cost_report, config.symbol)

    detail_rows, summary_rows, skipped_rows = build_outputs(
        rows=rows,
        config=config,
        cost_config=cost_config,
        cost_fields=cost_fields,
    )

    detail_path = output_dir / DETAIL_FILE
    summary_path = output_dir / SUMMARY_FILE
    skipped_path = output_dir / SKIPPED_FILE
    report_path = output_dir / REPORT_FILE
    write_csv(detail_path, detail_rows, DETAIL_FIELDNAMES)
    write_csv(summary_path, summary_rows, SUMMARY_FIELDNAMES)
    write_csv(skipped_path, skipped_rows, SKIPPED_FIELDNAMES)
    write_report(
        report_path,
        config=config,
        candidate_row=summary_rows[0],
        baseline_row=summary_rows[1],
        summary_rows=summary_rows,
        skipped_rows=skipped_rows,
        cost_warnings=cost_warnings,
    )
    return {
        "tp_sl_path_backtest_detail": detail_path,
        "tp_sl_path_backtest_summary": summary_path,
        "tp_sl_path_backtest_report": report_path,
        "skipped_tp_sl_path_rows": skipped_path,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run research-only fixed-filter TP/SL path-exit diagnostics."
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--direction", choices=("long", "short"))
    parser.add_argument("--horizon", type=int)
    parser.add_argument("--tp-atr", type=float, dest="tp_atr")
    parser.add_argument("--sl-atr", type=float, dest="sl_atr")
    parser.add_argument("--atr-column", default=DEFAULT_ATR_COLUMN)
    parser.add_argument("--same-bar-policy", choices=("stop_first", "take_first"), default=DEFAULT_SAME_BAR_POLICY)
    parser.add_argument("--filter", action="append", dest="filters", default=[])
    parser.add_argument("--combination-input-csv", type=Path)
    parser.add_argument("--target-label")
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=f"Default: {DEFAULT_OUTPUT_ROOT}")
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    parser.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    try:
        outputs = run_tp_sl_path_backtests(parse_args())
    except (FileExistsError, FileNotFoundError, OSError, ValueError, sqlite3.Error) as exc:
        print(f"TP/SL path backtest failed: {exc}")
        return 1
    print("TP/SL path backtest complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
