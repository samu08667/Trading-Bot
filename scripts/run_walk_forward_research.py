import argparse
import csv
from collections.abc import Callable
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from pathlib import Path
import re
import sqlite3
from statistics import median
import time

from research_metrics import (
    calculate_max_drawdown_improvement_pct,
    calculate_profit_factor_improvement_pct,
    calculate_return_metrics,
    csv_safe_value,
    directional_return,
    normalize_direction,
    safe_float,
    target_column_for_direction,
)
from research_costs import (
    cost_report_fields,
    cost_report_warnings,
    cost_adjusted_return_metrics,
    load_cost_config,
    validate_estimated_cost_config,
    validate_cost_args,
)
try:
    from feature_safety import FUTURE_TARGET_SKIP_REASON, is_future_or_target_column
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_walk_forward_research
    from scripts.feature_safety import FUTURE_TARGET_SKIP_REASON, is_future_or_target_column
try:
    from session_utils import SESSION_RANGES, hour_in_session, normalize_session_name
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_walk_forward_research
    from scripts.session_utils import SESSION_RANGES, hour_in_session, normalize_session_name
from time_split_utils import apply_purge_train_test_split, downsample_non_overlapping_rows, parse_time_server


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "walk_forward"
TABLE_NAME = "ml_dataset"

DETAIL_OUTPUT = "walk_forward_detail.csv"
SUMMARY_OUTPUT = "walk_forward_summary.csv"
CANDIDATES_OUTPUT = "walk_forward_candidates.csv"
REPORT_OUTPUT = "walk_forward_report.md"
PAIR_SPECIFIC_OUTPUT = "pair_specific_walk_forward_candidates.csv"
PAIR_SPECIFIC_REPORT_OUTPUT = "pair_specific_walk_forward_report.md"

RAW_PRICE_FEATURES = {"open", "high", "low", "close"}
RAW_UNSCALED_FEATURES = {"tick_volume"}
METADATA_COLUMNS = {"symbol", "timeframe", "time_server", "time", "date"}
MAX_COMBINATION_SIZE_LIMIT = 5
DEFAULT_MAX_SEED_CONDITIONS = 12
DEFAULT_MAX_CANDIDATES_PER_LEVEL = 50
DEFAULT_MAX_CROSS_PAIR_CANDIDATES_PER_FOLD = 50
DEFAULT_MAX_PAIR_SPECIFIC_CANDIDATES_PER_SYMBOL = 50
NUMERIC_TERCILE_WARNING = "numeric_tercile skipped until train-only thresholds are implemented."

DAY_NAME_TO_INT = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}
INT_TO_DAY_NAME = {value: key for key, value in DAY_NAME_TO_INT.items()}
@dataclass(frozen=True)
class TrainEvaluation:
    combination_key: str
    combination_size: int
    train_selection_level: int
    train_selection_score: float
    train_classification: str
    positive_symbol_ratio: float
    avg_profit_factor_improvement_pct: float | None
    avg_max_drawdown_improvement_pct: float | None
    min_trades_in_any_train_year: int
    notes: str


def normalize_symbols(values: list[str] | None) -> list[str]:
    symbols: list[str] = []
    for value in values or []:
        for token in value.split(","):
            symbol = token.strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols


def to_float(value: object) -> float | None:
    parsed = safe_float(value)
    return parsed if parsed is not None and math.isfinite(parsed) else None


def to_int(value: object) -> int | None:
    parsed = to_float(value)
    return int(parsed) if parsed is not None else None


def average(values: list[object]) -> float | None:
    usable = [float(value) for value in (to_float(item) for item in values) if value is not None]
    return sum(usable) / len(usable) if usable else None


def median_value(values: list[object]) -> float | None:
    usable = [float(value) for value in (to_float(item) for item in values) if value is not None]
    return median(usable) if usable else None


def minimum(values: list[object]) -> float | None:
    usable = [float(value) for value in (to_float(item) for item in values) if value is not None]
    return min(usable) if usable else None


def maximum(values: list[object]) -> float | None:
    usable = [float(value) for value in (to_float(item) for item in values) if value is not None]
    return max(usable) if usable else None


def concentration_penalties(row: dict[str, object]) -> list[str]:
    penalties = []
    monthly_ratio = to_float(row.get("monthly_positive_ratio"))
    quarterly_ratio = to_float(row.get("quarterly_positive_ratio"))
    best_month = to_float(row.get("best_month_contribution_pct"))
    top_trades = to_float(row.get("top_5_percent_trades_contribution_pct"))
    if monthly_ratio is not None and monthly_ratio < 0.45:
        penalties.append("monthly_positive_ratio < 0.45")
    if quarterly_ratio is not None and quarterly_ratio < 0.50:
        penalties.append("quarterly_positive_ratio < 0.50")
    if best_month is not None and best_month > 60:
        penalties.append("best_month_contribution_pct > 60")
    if top_trades is not None and top_trades > 70:
        penalties.append("top_5_percent_trades_contribution_pct > 70")
    return penalties


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def progress(message: str) -> None:
    print(f"[walk-forward] {message}", flush=True)


def format_year_range(years: list[int]) -> str:
    if not years:
        return "n/a"
    if len(years) == 1:
        return str(years[0])
    return f"{years[0]}-{years[-1]}"


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_year(value: object) -> int | None:
    parsed = parse_datetime(value)
    if parsed is not None:
        return parsed.year
    prefix = str(value or "").strip()[:4]
    return int(prefix) if prefix.isdigit() else None


def split_combination(combination_key: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"\s+AND\s+", combination_key.strip(), flags=re.IGNORECASE)
        if item.strip()
    ]


def condition_feature(condition_key: str) -> str:
    parts = [part.strip() for part in condition_key.split(":") if part.strip()]
    if not parts:
        return ""
    if parts[0] in {"day_of_week", "ma_diff", "hour_session"}:
        return parts[0]
    if len(parts) >= 3 and parts[0] in {"binary_feature", "news_feature"}:
        return parts[1]
    return parts[0] if len(parts) == 2 else parts[1]


def canonical_combination_key(conditions: list[str]) -> str:
    return " AND ".join(sorted(set(condition.strip() for condition in conditions if condition.strip())))


def combination_size(combination_key: str) -> int:
    return len(split_combination(combination_key))


def conditions_are_compatible(conditions: list[str]) -> bool:
    seen_conditions: set[str] = set()
    seen_features: set[str] = set()
    for condition in conditions:
        normalized = condition.strip()
        if not normalized or normalized in seen_conditions:
            return False
        seen_conditions.add(normalized)
        feature = condition_feature(normalized)
        if feature and feature in seen_features:
            return False
        if feature:
            seen_features.add(feature)
    return True


def expand_beam_candidate_keys(
    previous_level: list[TrainEvaluation],
    seed_conditions: list[str],
    target_size: int,
) -> list[str]:
    candidate_keys: set[str] = set()
    for evaluation in previous_level:
        existing_conditions = split_combination(evaluation.combination_key)
        for seed_condition in seed_conditions:
            conditions = [*existing_conditions, seed_condition]
            if len(set(conditions)) != target_size:
                continue
            if not conditions_are_compatible(conditions):
                continue
            candidate_key = canonical_combination_key(conditions)
            if combination_size(candidate_key) == target_size:
                candidate_keys.add(candidate_key)
    return sorted(candidate_keys)


def train_classification_rank(classification: str) -> int:
    if classification.startswith("select"):
        return 0
    if classification.startswith("watchlist"):
        return 1
    return 2


def rank_train_evaluations(evaluations: list[TrainEvaluation]) -> list[TrainEvaluation]:
    return sorted(
        evaluations,
        key=lambda item: (
            train_classification_rank(item.train_classification),
            -item.positive_symbol_ratio,
            -item.train_selection_score,
            item.combination_size,
            item.combination_key,
        ),
    )


def train_evaluation_is_selectable(item: TrainEvaluation) -> bool:
    return train_classification_rank(item.train_classification) < 2


def combination_length_penalty(
    *,
    size: int,
    avg_profit_factor_improvement_pct: float | None,
    avg_max_drawdown_improvement_pct: float | None,
    trade_ratio: float,
) -> float:
    extra_conditions = max(size - 1, 0)
    if extra_conditions == 0:
        return 0.0
    clear_improvement = (
        (avg_profit_factor_improvement_pct or 0.0) >= 5.0
        and (avg_max_drawdown_improvement_pct or 0.0) >= 5.0
    )
    base_penalty = 0.35 if clear_improvement else 1.0
    low_trade_penalty = max(0.0, 1.0 - min(trade_ratio, 1.0)) * 2.0
    return extra_conditions * (base_penalty + low_trade_penalty)


def score_train_selection(
    *,
    positive_symbol_ratio: float,
    avg_profit_factor_improvement_pct: float | None,
    avg_max_drawdown_improvement_pct: float | None,
    min_trades_in_any_train_year: int,
    min_trades_per_year: int,
    size: int,
    concentration_penalty_count: int = 0,
) -> float:
    trade_ratio = min_trades_in_any_train_year / max(min_trades_per_year, 1)
    capped_trade_ratio = min(trade_ratio, 1.0)
    pf = avg_profit_factor_improvement_pct or 0.0
    dd = avg_max_drawdown_improvement_pct or 0.0
    score = (
        positive_symbol_ratio * 10.0
        + max(pf, 0.0) / 10.0
        + max(dd, 0.0) / 10.0
        + capped_trade_ratio * 2.0
    )
    if pf < 0:
        score += pf / 5.0
    if dd < 0:
        score += dd / 5.0
    if trade_ratio < 1.0:
        score -= (1.0 - trade_ratio) * 4.0
    score -= combination_length_penalty(
        size=size,
        avg_profit_factor_improvement_pct=avg_profit_factor_improvement_pct,
        avg_max_drawdown_improvement_pct=avg_max_drawdown_improvement_pct,
        trade_ratio=trade_ratio,
    )
    score -= concentration_penalty_count * 0.5
    return score


def table_columns(connection: sqlite3.Connection) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})")}


def ensure_dataset(connection: sqlite3.Connection, return_column: str) -> set[str]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    ).fetchone()
    if exists is None:
        raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")

    columns = table_columns(connection)
    if return_column not in columns:
        raise ValueError(f"Column {return_column!r} not found in {TABLE_NAME}.")
    return columns


def load_rows(
    db_path: Path,
    symbols: list[str],
    timeframe: str,
    return_column: str,
) -> tuple[list[dict[str, object]], set[str]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    placeholders = ",".join("?" for _ in symbols)
    params = [*symbols, timeframe]
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        columns = ensure_dataset(connection, return_column)
        rows = connection.execute(
            f"""
            SELECT *
            FROM {TABLE_NAME}
            WHERE symbol IN ({placeholders})
              AND timeframe = ?
              AND {return_column} IS NOT NULL
              AND time_server IS NOT NULL
            ORDER BY symbol ASC, time_server ASC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows], columns


def rows_for_years(rows: list[dict[str, object]], years: set[int]) -> list[dict[str, object]]:
    return [row for row in rows if parse_year(row.get("time_server")) in years]


def year_start(year: int) -> datetime:
    return datetime(year, 1, 1)


def year_end(year: int) -> datetime:
    return datetime(year + 1, 1, 1) - timedelta(microseconds=1)


def sort_rows_by_time(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            parse_time_server(row.get("time_server")) or datetime.max,
            str(row.get("symbol") or ""),
        ),
    )


def returns_from_rows(rows: list[dict[str, object]], return_column: str, direction: str) -> list[float]:
    values = []
    for row in rows:
        value = directional_return(row.get(return_column), direction)
        if value is not None and math.isfinite(value):
            values.append(value)
    return values


def metrics(
    rows: list[dict[str, object]],
    return_column: str,
    direction: str,
    symbol: str,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
) -> dict[str, object]:
    return cost_adjusted_return_metrics(
        rows,
        symbol=symbol,
        return_column=return_column,
        direction=direction,
        cost_config=cost_config,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )


def period_evaluation(
    rows: list[dict[str, object]],
    predicate,
    return_column: str,
    direction: str,
    symbol: str,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
) -> dict[str, object]:
    baseline_rows = rows
    scenario_rows = [row for row in rows if predicate(row)]
    baseline = metrics(baseline_rows, return_column, direction, symbol, cost_config, cost_mode, return_mode)
    scenario = metrics(scenario_rows, return_column, direction, symbol, cost_config, cost_mode, return_mode)
    pf_improvement = calculate_profit_factor_improvement_pct(
        scenario.get("profit_factor"),
        baseline.get("profit_factor"),
    )
    dd_improvement = calculate_max_drawdown_improvement_pct(
        scenario.get("max_drawdown"),
        baseline.get("max_drawdown"),
    )
    return {
        "baseline_trades_count": baseline.get("trades_count"),
        "trades_count": scenario.get("trades_count"),
        "avg_estimated_cost_return": scenario.get("avg_estimated_cost_return"),
        "gross_profit_factor": scenario.get("gross_profit_factor"),
        "net_profit_factor": scenario.get("net_profit_factor"),
        "gross_max_drawdown": scenario.get("gross_max_drawdown"),
        "net_max_drawdown": scenario.get("net_max_drawdown"),
        "gross_cumulative_return": scenario.get("gross_cumulative_return"),
        "net_cumulative_return": scenario.get("net_cumulative_return"),
        "mean_return": scenario.get("mean_return"),
        "median_return": scenario.get("median_return"),
        "win_rate": scenario.get("win_rate"),
        "cumulative_return": scenario.get("cumulative_return"),
        "profit_factor": scenario.get("profit_factor"),
        "max_drawdown": scenario.get("max_drawdown"),
        "avg_positive_return": scenario.get("avg_positive_return"),
        "avg_negative_return": scenario.get("avg_negative_return"),
        "payoff_ratio": scenario.get("payoff_ratio"),
        "breakeven_winrate": scenario.get("breakeven_winrate"),
        "breakeven_winrate_margin": scenario.get("breakeven_winrate_margin"),
        "monthly_positive_ratio": scenario.get("monthly_positive_ratio"),
        "quarterly_positive_ratio": scenario.get("quarterly_positive_ratio"),
        "best_month_contribution_pct": scenario.get("best_month_contribution_pct"),
        "top_5_percent_trades_contribution_pct": scenario.get("top_5_percent_trades_contribution_pct"),
        "max_flat_period_bars": scenario.get("max_flat_period_bars"),
        "profit_factor_improvement_pct": pf_improvement,
        "max_drawdown_improvement_pct": dd_improvement,
    }


def feature_is_excluded(column: str) -> bool:
    lower = column.lower()
    return (
        lower in METADATA_COLUMNS
        or lower in RAW_PRICE_FEATURES
        or lower in RAW_UNSCALED_FEATURES
        or is_future_or_target_column(lower)
    )


def finite_column_values(rows: list[dict[str, object]], column: str) -> set[float]:
    values = set()
    for row in rows:
        value = to_float(row.get(column))
        if value is not None:
            values.add(value)
    return values


def generate_single_conditions(
    train_rows: list[dict[str, object]],
    columns: set[str],
    warnings: list[str],
) -> list[str]:
    conditions: set[str] = set()
    if not train_rows:
        return []

    if "day_of_week" in columns:
        day_values = {to_int(row.get("day_of_week")) for row in train_rows}
        for day_value in sorted(value for value in day_values if value in INT_TO_DAY_NAME):
            conditions.add(f"day_of_week:{INT_TO_DAY_NAME[int(day_value)]}")

    if "hour" in columns:
        for session_name, session_range in SESSION_RANGES.items():
            if any((hour := to_int(row.get("hour"))) is not None and hour in session_range for row in train_rows):
                conditions.add(f"hour_session:{session_name}")

    if "ma_diff" in columns:
        ma_values = [to_float(row.get("ma_diff")) for row in train_rows]
        if any(value is not None and value > 0 for value in ma_values):
            conditions.add("ma_diff:ma_diff_gt_0")
        if any(value is not None and value < 0 for value in ma_values):
            conditions.add("ma_diff:ma_diff_lt_0")

    for column in sorted(columns):
        lower = column.lower()
        if feature_is_excluded(column) or column in {"day_of_week", "hour", "ma_diff"}:
            continue
        if "numeric_tercile" in lower:
            warnings.append(NUMERIC_TERCILE_WARNING)
            continue
        values = finite_column_values(train_rows, column)
        if values and values.issubset({0.0, 1.0}):
            for value in sorted(values):
                conditions.add(f"{column}:{int(value)}")

    return sorted(conditions)


def condition_predicate(condition_key: str):
    parts = [part.strip() for part in condition_key.split(":") if part.strip()]
    if len(parts) < 2:
        raise ValueError(f"Unsupported condition format: {condition_key!r}")

    scenario_type = parts[0]
    if scenario_type == "numeric_tercile" or "numeric_tercile" in [part.lower() for part in parts]:
        raise ValueError(NUMERIC_TERCILE_WARNING)

    if len(parts) == 2:
        feature = scenario_type
        bucket = parts[1]
    else:
        feature = parts[1]
        bucket = ":".join(parts[2:])

    if is_future_or_target_column(feature):
        raise ValueError(FUTURE_TARGET_SKIP_REASON)

    if scenario_type == "day_of_week":
        if bucket not in DAY_NAME_TO_INT:
            raise ValueError(f"Unsupported day_of_week bucket: {bucket!r}")
        expected = DAY_NAME_TO_INT[bucket]
        return lambda row, expected=expected: to_int(row.get("day_of_week")) == expected

    if scenario_type == "hour_session":
        normalized_bucket = normalize_session_name(bucket)
        return lambda row, session=normalized_bucket: hour_in_session(to_int(row.get("hour")), session)

    if scenario_type == "ma_diff":
        if bucket == "ma_diff_gt_0":
            return lambda row: (value := to_float(row.get("ma_diff"))) is not None and value > 0
        if bucket == "ma_diff_lt_0":
            return lambda row: (value := to_float(row.get("ma_diff"))) is not None and value < 0
        raise ValueError(f"Unsupported ma_diff bucket: {bucket!r}")

    if bucket in {"0", "1"}:
        expected = float(bucket)
        return lambda row, feature=feature, expected=expected: to_float(row.get(feature)) == expected

    raise ValueError(f"Unsupported condition format: {condition_key!r}")


def build_predicate(combination_key: str):
    predicates = [condition_predicate(condition) for condition in split_combination(combination_key)]
    if not predicates:
        raise ValueError(f"Empty combination: {combination_key!r}")
    return lambda row: all(predicate(row) for predicate in predicates)


def min_trades_by_year(
    rows: list[dict[str, object]],
    predicate,
    train_years: list[int],
) -> int:
    counts = []
    for year in train_years:
        year_rows = [row for row in rows if parse_year(row.get("time_server")) == year]
        counts.append(sum(1 for row in year_rows if predicate(row)))
    return min(counts) if counts else 0


def train_symbol_result(
    combination_key: str,
    symbol: str,
    symbol_rows: list[dict[str, object]],
    train_years: list[int],
    return_column: str,
    direction: str,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
) -> dict[str, object]:
    predicate = build_predicate(combination_key)
    result = period_evaluation(
        symbol_rows,
        predicate,
        return_column,
        direction,
        symbol,
        cost_config,
        cost_mode,
        return_mode,
    )
    result["min_trades_in_any_train_year"] = min_trades_by_year(symbol_rows, predicate, train_years)
    return result


def classify_train_cross_pair(
    symbol_results: list[dict[str, object]],
    *,
    min_trades_per_year: int,
    min_positive_symbol_ratio: float,
    size: int,
) -> tuple[str, float, str]:
    if not symbol_results:
        return "reject_train", 0.0, "no train rows"

    positive_symbols = 0
    for row in symbol_results:
        pf = to_float(row.get("profit_factor_improvement_pct"))
        dd = to_float(row.get("max_drawdown_improvement_pct"))
        min_trades = int(row.get("min_trades_in_any_train_year") or 0)
        if pf is not None and pf > 0 and dd is not None and dd >= 0 and min_trades >= min_trades_per_year:
            positive_symbols += 1

    positive_symbol_ratio = positive_symbols / len(symbol_results)
    avg_pf = average([row.get("profit_factor_improvement_pct") for row in symbol_results])
    avg_dd = average([row.get("max_drawdown_improvement_pct") for row in symbol_results])
    min_train_trades = min(int(row.get("min_trades_in_any_train_year") or 0) for row in symbol_results)
    concentration_row = {
        "monthly_positive_ratio": average([row.get("monthly_positive_ratio") for row in symbol_results]),
        "quarterly_positive_ratio": average([row.get("quarterly_positive_ratio") for row in symbol_results]),
        "best_month_contribution_pct": maximum([row.get("best_month_contribution_pct") for row in symbol_results]),
        "top_5_percent_trades_contribution_pct": maximum(
            [row.get("top_5_percent_trades_contribution_pct") for row in symbol_results]
        ),
    }
    concentration_risks = concentration_penalties(concentration_row)
    score = score_train_selection(
        positive_symbol_ratio=positive_symbol_ratio,
        avg_profit_factor_improvement_pct=avg_pf,
        avg_max_drawdown_improvement_pct=avg_dd,
        min_trades_in_any_train_year=min_train_trades,
        min_trades_per_year=min_trades_per_year,
        size=size,
        concentration_penalty_count=len(concentration_risks),
    )

    if (
        positive_symbol_ratio >= min_positive_symbol_ratio
        and avg_pf is not None
        and avg_pf > 0
        and avg_dd is not None
        and avg_dd >= 0
        and min_train_trades >= min_trades_per_year
    ):
        return "select_train", score, "stable across train symbols"
    if positive_symbol_ratio >= 0.50 and avg_pf is not None and avg_pf > 0:
        if concentration_risks:
            risk_text = "; ".join(f"concentration penalty: {risk}" for risk in concentration_risks)
            return "watchlist_train", score, risk_text
        return "watchlist_train", score, "interesting train evidence"
    return "reject_train", score, "weak train evidence"


def evaluate_train_cross_pair(
    combination_key: str,
    train_rows_by_symbol: dict[str, list[dict[str, object]]],
    train_years: list[int],
    return_column: str,
    direction: str,
    min_trades_per_year: int,
    min_positive_symbol_ratio: float,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
) -> TrainEvaluation:
    size = combination_size(combination_key)
    symbol_results = [
        train_symbol_result(combination_key, symbol, rows, train_years, return_column, direction, cost_config, cost_mode, return_mode)
        for symbol, rows in train_rows_by_symbol.items()
        if rows
    ]
    classification, score, notes = classify_train_cross_pair(
        symbol_results,
        min_trades_per_year=min_trades_per_year,
        min_positive_symbol_ratio=min_positive_symbol_ratio,
        size=size,
    )
    positive_symbol_ratio = (
        sum(
            1
            for row in symbol_results
            if (pf := to_float(row.get("profit_factor_improvement_pct"))) is not None
            and pf > 0
            and (dd := to_float(row.get("max_drawdown_improvement_pct"))) is not None
            and dd >= 0
        )
        / len(symbol_results)
        if symbol_results
        else 0.0
    )
    return TrainEvaluation(
        combination_key=combination_key,
        combination_size=size,
        train_selection_level=size,
        train_selection_score=score,
        train_classification=classification,
        positive_symbol_ratio=positive_symbol_ratio,
        avg_profit_factor_improvement_pct=average([row.get("profit_factor_improvement_pct") for row in symbol_results]),
        avg_max_drawdown_improvement_pct=average([row.get("max_drawdown_improvement_pct") for row in symbol_results]),
        min_trades_in_any_train_year=min(
            (int(row.get("min_trades_in_any_train_year") or 0) for row in symbol_results),
            default=0,
        ),
        notes=notes,
    )


def classify_train_pair_specific(
    result: dict[str, object],
    *,
    min_trades_per_year: int,
    size: int,
) -> tuple[str, float, str]:
    pf = to_float(result.get("profit_factor_improvement_pct"))
    dd = to_float(result.get("max_drawdown_improvement_pct"))
    min_trades = int(result.get("min_trades_in_any_train_year") or 0)
    positive_symbol_ratio = 1.0 if pf is not None and pf > 0 and dd is not None and dd >= 0 else 0.0
    concentration_risks = concentration_penalties(result)
    score = score_train_selection(
        positive_symbol_ratio=positive_symbol_ratio,
        avg_profit_factor_improvement_pct=pf,
        avg_max_drawdown_improvement_pct=dd,
        min_trades_in_any_train_year=min_trades,
        min_trades_per_year=min_trades_per_year,
        size=size,
        concentration_penalty_count=len(concentration_risks),
    )
    if (
        pf is not None
        and pf > 0
        and dd is not None
        and dd >= 0
        and min_trades >= min_trades_per_year
    ):
        return "select_train_pair_specific", score, "positive train evidence for this symbol"
    if pf is not None and pf > 0 and min_trades > 0:
        if concentration_risks:
            risk_text = "; ".join(f"concentration penalty: {risk}" for risk in concentration_risks)
            return "watchlist_train_pair_specific", score, risk_text
        return "watchlist_train_pair_specific", score, "interesting train evidence for this symbol"
    return "reject_train_pair_specific", score, "weak train evidence for this symbol"


def evaluate_train_pair_specific(
    combination_key: str,
    symbol: str,
    symbol_rows: list[dict[str, object]],
    train_years: list[int],
    return_column: str,
    direction: str,
    min_trades_per_year: int,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
) -> TrainEvaluation:
    size = combination_size(combination_key)
    result = train_symbol_result(combination_key, symbol, symbol_rows, train_years, return_column, direction, cost_config, cost_mode, return_mode)
    classification, score, notes = classify_train_pair_specific(
        result,
        min_trades_per_year=min_trades_per_year,
        size=size,
    )
    pf = to_float(result.get("profit_factor_improvement_pct"))
    dd = to_float(result.get("max_drawdown_improvement_pct"))
    positive_symbol_ratio = 1.0 if pf is not None and pf > 0 and dd is not None and dd >= 0 else 0.0
    return TrainEvaluation(
        combination_key=combination_key,
        combination_size=size,
        train_selection_level=size,
        train_selection_score=score,
        train_classification=classification,
        positive_symbol_ratio=positive_symbol_ratio,
        avg_profit_factor_improvement_pct=pf,
        avg_max_drawdown_improvement_pct=dd,
        min_trades_in_any_train_year=int(result.get("min_trades_in_any_train_year") or 0),
        notes=notes,
    )


def beam_search_train_candidates(
    single_conditions: list[str],
    evaluate_candidate: Callable[[str], TrainEvaluation],
    *,
    max_combination_size: int,
    max_seed_conditions: int,
    max_candidates_per_level: int,
    warnings: list[str],
    warning_context: str,
    progress_callback: Callable[[str], None] | None = None,
) -> list[TrainEvaluation]:
    seen_keys: set[str] = set()
    level_evaluations: list[TrainEvaluation] = []
    for condition in single_conditions:
        if not conditions_are_compatible([condition]):
            continue
        combination_key = canonical_combination_key([condition])
        if combination_key in seen_keys:
            continue
        seen_keys.add(combination_key)
        try:
            level_evaluations.append(evaluate_candidate(combination_key))
        except ValueError as exc:
            warnings.append(f"{warning_context} level 1 candidate skipped: {combination_key}: {exc}")

    ranked_singles = rank_train_evaluations(level_evaluations)
    seed_evaluations = ranked_singles[:max_seed_conditions]
    seed_conditions = [item.combination_key for item in seed_evaluations]
    current_level = seed_evaluations[:max_candidates_per_level]
    all_level_evaluations = list(current_level)
    if progress_callback is not None:
        progress_callback(
            f"{warning_context}: level 1 singles evaluated={len(level_evaluations)}, "
            f"seeds={len(seed_evaluations)}, kept={len(current_level)}"
        )

    for level in range(2, max_combination_size + 1):
        candidate_keys = [
            key
            for key in expand_beam_candidate_keys(current_level, seed_conditions, level)
            if key not in seen_keys
        ]
        if progress_callback is not None:
            progress_callback(f"{warning_context}: level {level} combinations generated={len(candidate_keys)}")
        if not candidate_keys:
            break
        next_level: list[TrainEvaluation] = []
        for combination_key in candidate_keys:
            seen_keys.add(combination_key)
            try:
                next_level.append(evaluate_candidate(combination_key))
            except ValueError as exc:
                warnings.append(f"{warning_context} level {level} candidate skipped: {combination_key}: {exc}")

        current_level = rank_train_evaluations(next_level)[:max_candidates_per_level]
        if progress_callback is not None:
            progress_callback(
                f"{warning_context}: level {level} evaluated={len(next_level)}, kept={len(current_level)}"
            )
        if not current_level:
            break
        all_level_evaluations.extend(current_level)

    selected = rank_train_evaluations(
        [item for item in all_level_evaluations if train_evaluation_is_selectable(item)]
    )
    if progress_callback is not None:
        progress_callback(f"{warning_context}: selectable train candidates={len(selected)}")
    return selected


def selected_cross_pair_combinations(
    single_conditions: list[str],
    train_rows_by_symbol: dict[str, list[dict[str, object]]],
    train_years: list[int],
    return_column: str,
    direction: str,
    min_trades_per_year: int,
    min_positive_symbol_ratio: float,
    warnings: list[str],
    max_combination_size: int,
    max_seed_conditions: int,
    max_candidates_per_level: int,
    max_cross_pair_candidates_per_fold: int,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
    progress_callback: Callable[[str], None] | None = None,
) -> list[TrainEvaluation]:
    def evaluate_candidate(combination_key: str) -> TrainEvaluation:
        return evaluate_train_cross_pair(
            combination_key,
            train_rows_by_symbol,
            train_years,
            return_column,
            direction,
            min_trades_per_year,
            min_positive_symbol_ratio,
            cost_config,
            cost_mode,
            return_mode,
        )

    selected = beam_search_train_candidates(
        single_conditions,
        evaluate_candidate,
        max_combination_size=max_combination_size,
        max_seed_conditions=max_seed_conditions,
        max_candidates_per_level=max_candidates_per_level,
        warnings=warnings,
        warning_context="Cross-pair train",
        progress_callback=progress_callback,
    )
    return selected[:max_cross_pair_candidates_per_fold]


def selected_pair_specific_combinations(
    single_conditions: list[str],
    train_rows_by_symbol: dict[str, list[dict[str, object]]],
    train_years: list[int],
    return_column: str,
    direction: str,
    min_trades_per_year: int,
    warnings: list[str],
    max_combination_size: int,
    max_seed_conditions: int,
    max_candidates_per_level: int,
    max_pair_specific_candidates_per_symbol: int,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, list[TrainEvaluation]]:
    selected_by_symbol: dict[str, list[TrainEvaluation]] = {}
    for symbol, symbol_rows in train_rows_by_symbol.items():
        if progress_callback is not None:
            progress_callback(f"Pair-specific train: evaluating symbol {symbol}")

        def evaluate_candidate(combination_key: str) -> TrainEvaluation:
            return evaluate_train_pair_specific(
                combination_key,
                symbol,
                symbol_rows,
                train_years,
                return_column,
                direction,
                min_trades_per_year,
                cost_config,
                cost_mode,
                return_mode,
            )

        selected = beam_search_train_candidates(
            single_conditions,
            evaluate_candidate,
            max_combination_size=max_combination_size,
            max_seed_conditions=max_seed_conditions,
            max_candidates_per_level=max_candidates_per_level,
            warnings=warnings,
            warning_context=f"Pair-specific train {symbol}",
            progress_callback=progress_callback,
        )
        selected_by_symbol[symbol] = selected[:max_pair_specific_candidates_per_symbol]
        if progress_callback is not None:
            progress_callback(f"Pair-specific train {symbol}: selected={len(selected_by_symbol[symbol])}")
    return selected_by_symbol


def detail_row(
    *,
    run_id: str,
    direction: str,
    symbol: str,
    timeframe: str,
    target_horizon: int,
    combination_key: str,
    combination_size_value: int,
    train_selection_level: int,
    train_selection_score: float,
    cost_mode: str,
    return_mode: str,
    cost_fields: dict[str, str],
    purge_overlap: bool,
    embargo_bars: int,
    non_overlap_test: bool,
    train_rows_before_purge: int,
    train_rows_after_purge: int,
    test_rows_before_embargo: int,
    test_rows_after_embargo: int,
    test_rows_after_non_overlap: int,
    train_start_year: int,
    train_end_year: int,
    test_year: int,
    train_rows: list[dict[str, object]],
    test_rows: list[dict[str, object]],
    return_column: str,
    min_trades_per_year: int,
    cost_config: dict[str, object],
) -> dict[str, object]:
    predicate = build_predicate(combination_key)
    train = period_evaluation(train_rows, predicate, return_column, direction, symbol, cost_config, cost_mode, return_mode)
    test = period_evaluation(test_rows, predicate, return_column, direction, symbol, cost_config, cost_mode, return_mode)
    test_pf_improvement = to_float(test.get("profit_factor_improvement_pct"))
    test_dd_improvement = to_float(test.get("max_drawdown_improvement_pct"))
    test_trades = int(test.get("trades_count") or 0)
    return {
        "run_id": run_id,
        "direction": direction,
        "symbol": symbol,
        "timeframe": timeframe,
        "target_horizon": target_horizon,
        "combination_key": combination_key,
        "combination_size": combination_size_value,
        "train_selection_level": train_selection_level,
        "train_selection_score": train_selection_score,
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        **cost_fields,
        "purge_overlap": bool_text(purge_overlap),
        "embargo_bars": embargo_bars,
        "non_overlap_test": bool_text(non_overlap_test),
        "train_rows_before_purge": train_rows_before_purge,
        "train_rows_after_purge": train_rows_after_purge,
        "test_rows_before_embargo": test_rows_before_embargo,
        "test_rows_after_embargo": test_rows_after_embargo,
        "test_rows_after_non_overlap": test_rows_after_non_overlap,
        "train_start_year": train_start_year,
        "train_end_year": train_end_year,
        "test_year": test_year,
        "train_baseline_trades_count": train.get("baseline_trades_count"),
        "test_baseline_trades_count": test.get("baseline_trades_count"),
        "train_trades_count": train.get("trades_count"),
        "test_trades_count": test_trades,
        "train_avg_estimated_cost_return": train.get("avg_estimated_cost_return"),
        "test_avg_estimated_cost_return": test.get("avg_estimated_cost_return"),
        "train_gross_profit_factor": train.get("gross_profit_factor"),
        "train_net_profit_factor": train.get("net_profit_factor"),
        "test_gross_profit_factor": test.get("gross_profit_factor"),
        "test_net_profit_factor": test.get("net_profit_factor"),
        "train_gross_max_drawdown": train.get("gross_max_drawdown"),
        "train_net_max_drawdown": train.get("net_max_drawdown"),
        "test_gross_max_drawdown": test.get("gross_max_drawdown"),
        "test_net_max_drawdown": test.get("net_max_drawdown"),
        "train_mean_return": train.get("mean_return"),
        "test_mean_return": test.get("mean_return"),
        "train_median_return": train.get("median_return"),
        "test_median_return": test.get("median_return"),
        "train_win_rate": train.get("win_rate"),
        "test_win_rate": test.get("win_rate"),
        "train_cumulative_return": train.get("cumulative_return"),
        "test_cumulative_return": test.get("cumulative_return"),
        "train_profit_factor": train.get("profit_factor"),
        "test_profit_factor": test.get("profit_factor"),
        "train_max_drawdown": train.get("max_drawdown"),
        "test_max_drawdown": test.get("max_drawdown"),
        "train_avg_positive_return": train.get("avg_positive_return"),
        "test_avg_positive_return": test.get("avg_positive_return"),
        "train_avg_negative_return": train.get("avg_negative_return"),
        "test_avg_negative_return": test.get("avg_negative_return"),
        "train_payoff_ratio": train.get("payoff_ratio"),
        "test_payoff_ratio": test.get("payoff_ratio"),
        "train_breakeven_winrate": train.get("breakeven_winrate"),
        "test_breakeven_winrate": test.get("breakeven_winrate"),
        "train_breakeven_winrate_margin": train.get("breakeven_winrate_margin"),
        "test_breakeven_winrate_margin": test.get("breakeven_winrate_margin"),
        "train_monthly_positive_ratio": train.get("monthly_positive_ratio"),
        "test_monthly_positive_ratio": test.get("monthly_positive_ratio"),
        "train_quarterly_positive_ratio": train.get("quarterly_positive_ratio"),
        "test_quarterly_positive_ratio": test.get("quarterly_positive_ratio"),
        "train_best_month_contribution_pct": train.get("best_month_contribution_pct"),
        "test_best_month_contribution_pct": test.get("best_month_contribution_pct"),
        "train_top_5_percent_trades_contribution_pct": train.get("top_5_percent_trades_contribution_pct"),
        "test_top_5_percent_trades_contribution_pct": test.get("top_5_percent_trades_contribution_pct"),
        "train_max_flat_period_bars": train.get("max_flat_period_bars"),
        "test_max_flat_period_bars": test.get("max_flat_period_bars"),
        "train_profit_factor_improvement_pct": train.get("profit_factor_improvement_pct"),
        "test_profit_factor_improvement_pct": test.get("profit_factor_improvement_pct"),
        "train_max_drawdown_improvement_pct": train.get("max_drawdown_improvement_pct"),
        "test_max_drawdown_improvement_pct": test.get("max_drawdown_improvement_pct"),
        "test_is_positive": bool_text(
            test_trades > 0
            and test_pf_improvement is not None
            and test_pf_improvement > 0
            and test_dd_improvement is not None
            and test_dd_improvement >= 0
        ),
        "test_is_low_sample": bool_text(test_trades < min_trades_per_year),
    }


def classify_walk_forward_summary(
    row: dict[str, object],
    *,
    min_trades_per_year: int,
    min_positive_symbol_ratio: float,
) -> tuple[str, str]:
    folds_tested = int(row.get("folds_tested") or 0)
    positive_ratio = to_float(row.get("positive_test_fold_ratio")) or 0.0
    positive_symbol_ratio = to_float(row.get("positive_symbol_ratio")) or 0.0
    avg_pf = to_float(row.get("avg_test_profit_factor_improvement_pct"))
    avg_dd = to_float(row.get("avg_test_max_drawdown_improvement_pct"))
    min_trades = int(row.get("min_test_trades_count") or 0)
    dd_worse_folds = int(row.get("drawdown_worse_test_folds") or 0)
    pf_worse_folds = int(row.get("profit_factor_worse_test_folds") or 0)
    positive_folds = int(row.get("positive_test_folds") or 0)
    concentration_risks = concentration_penalties(row)

    if (
        positive_ratio >= 0.75
        and positive_symbol_ratio >= min_positive_symbol_ratio
        and avg_pf is not None
        and avg_pf > 0
        and avg_dd is not None
        and avg_dd >= 0
        and min_trades >= min_trades_per_year
    ):
        return "select_walk_forward", "stable out-of-sample across folds and symbols"

    concentrated = folds_tested >= 3 and positive_folds <= 1
    if positive_ratio < 0.50:
        return "reject_walk_forward", "positive_test_fold_ratio below 0.50"
    if avg_pf is not None and avg_pf < 0:
        return "reject_walk_forward", "profit factor worsens out-of-sample"
    if folds_tested and dd_worse_folds > folds_tested / 2:
        return "reject_walk_forward", "drawdown worsens in the majority of test folds"
    if folds_tested and pf_worse_folds > folds_tested / 2:
        return "reject_walk_forward", "profit factor worsens in the majority of test folds"
    if concentrated:
        return "reject_walk_forward", "positive results concentrated in too few folds"
    if concentration_risks:
        return "watchlist_walk_forward", "; ".join(
            f"concentration penalty: {risk}" for risk in concentration_risks
        )
    return "watchlist_walk_forward", "interesting out-of-sample evidence but not enough for select"


def aggregate_walk_forward_detail(
    detail_rows: list[dict[str, object]],
    *,
    min_trades_per_year: int,
    min_positive_symbol_ratio: float,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in detail_rows:
        grouped[str(row["combination_key"])].append(row)

    summaries = []
    for combination_key, rows in grouped.items():
        folds_tested = len(rows)
        positive_test_folds = sum(1 for row in rows if as_bool(row.get("test_is_positive")))
        symbols = sorted({str(row["symbol"]) for row in rows})
        positive_symbols = 0
        for symbol in symbols:
            symbol_rows = [row for row in rows if row["symbol"] == symbol]
            if not symbol_rows:
                continue
            symbol_positive_ratio = sum(1 for row in symbol_rows if as_bool(row.get("test_is_positive"))) / len(symbol_rows)
            symbol_avg_dd = average([row.get("test_max_drawdown_improvement_pct") for row in symbol_rows])
            if symbol_positive_ratio >= 0.75 and symbol_avg_dd is not None and symbol_avg_dd >= 0:
                positive_symbols += 1

        test_trades = [int(row.get("test_trades_count") or 0) for row in rows]
        pf_values = [row.get("test_profit_factor_improvement_pct") for row in rows]
        dd_values = [row.get("test_max_drawdown_improvement_pct") for row in rows]
        train_selection_scores = [row.get("train_selection_score") for row in rows]
        summary = {
            "combination_key": combination_key,
            "combination_size": int(rows[0].get("combination_size") or combination_size(combination_key)),
            "train_selection_level": int(rows[0].get("train_selection_level") or combination_size(combination_key)),
            "train_selection_score": average(train_selection_scores),
            "cost_mode": rows[0].get("cost_mode", "none"),
            "return_mode": rows[0].get("return_mode", "gross"),
            "cost_config_source": rows[0].get("cost_config_source", "not_applicable"),
            "point_size_source": "",
            "spread_source_used": "",
            "symbols_using_default_costs": "",
            "purge_overlap": rows[0].get("purge_overlap", "false"),
            "embargo_bars": rows[0].get("embargo_bars", 0),
            "non_overlap_test": rows[0].get("non_overlap_test", "false"),
            "train_rows_before_purge": average([row.get("train_rows_before_purge") for row in rows]),
            "train_rows_after_purge": average([row.get("train_rows_after_purge") for row in rows]),
            "test_rows_before_embargo": average([row.get("test_rows_before_embargo") for row in rows]),
            "test_rows_after_embargo": average([row.get("test_rows_after_embargo") for row in rows]),
            "test_rows_after_non_overlap": average([row.get("test_rows_after_non_overlap") for row in rows]),
            "direction": rows[0].get("direction") if rows else "",
            "timeframe": rows[0].get("timeframe") if rows else "",
            "target_horizon": rows[0].get("target_horizon") if rows else "",
            "folds_tested": folds_tested,
            "positive_test_folds": positive_test_folds,
            "positive_test_fold_ratio": positive_test_folds / folds_tested if folds_tested else 0.0,
            "symbols_tested": len(symbols),
            "positive_symbols": positive_symbols,
            "positive_symbol_ratio": positive_symbols / len(symbols) if symbols else 0.0,
            "avg_test_trades_count": average(test_trades),
            "min_test_trades_count": min(test_trades) if test_trades else 0,
            "avg_test_profit_factor_improvement_pct": average(pf_values),
            "median_test_profit_factor_improvement_pct": median_value(pf_values),
            "avg_test_max_drawdown_improvement_pct": average(dd_values),
            "worst_test_profit_factor_improvement_pct": minimum(pf_values),
            "worst_test_drawdown_improvement_pct": minimum(dd_values),
            "avg_positive_return": average([row.get("test_avg_positive_return") for row in rows]),
            "avg_negative_return": average([row.get("test_avg_negative_return") for row in rows]),
            "payoff_ratio": average([row.get("test_payoff_ratio") for row in rows]),
            "breakeven_winrate": average([row.get("test_breakeven_winrate") for row in rows]),
            "breakeven_winrate_margin": average([row.get("test_breakeven_winrate_margin") for row in rows]),
            "monthly_positive_ratio": average([row.get("test_monthly_positive_ratio") for row in rows]),
            "quarterly_positive_ratio": average([row.get("test_quarterly_positive_ratio") for row in rows]),
            "best_month_contribution_pct": maximum([row.get("test_best_month_contribution_pct") for row in rows]),
            "top_5_percent_trades_contribution_pct": maximum(
                [row.get("test_top_5_percent_trades_contribution_pct") for row in rows]
            ),
            "max_flat_period_bars": maximum([row.get("test_max_flat_period_bars") for row in rows]),
            "profit_factor_worse_test_folds": sum(
                1 for value in pf_values if (parsed := to_float(value)) is not None and parsed < 0
            ),
            "drawdown_worse_test_folds": sum(
                1 for value in dd_values if (parsed := to_float(value)) is not None and parsed < 0
            ),
        }
        classification, rationale = classify_walk_forward_summary(
            summary,
            min_trades_per_year=min_trades_per_year,
            min_positive_symbol_ratio=min_positive_symbol_ratio,
        )
        summary["walk_forward_classification"] = classification
        summary["classification_rationale"] = rationale
        summaries.append(summary)

    class_order = {"select_walk_forward": 0, "watchlist_walk_forward": 1, "reject_walk_forward": 2}
    summaries.sort(
        key=lambda row: (
            class_order.get(str(row["walk_forward_classification"]), 99),
            -float(row.get("positive_test_fold_ratio") or 0),
            -float(row.get("positive_symbol_ratio") or 0),
            -float(row.get("avg_test_max_drawdown_improvement_pct") or -1_000_000),
            str(row["combination_key"]),
        )
    )
    return summaries


def classify_pair_specific_summary(row: dict[str, object], min_trades_per_year: int) -> tuple[str, str]:
    folds_tested = int(row.get("folds_tested") or 0)
    positive_ratio = to_float(row.get("positive_test_fold_ratio")) or 0.0
    avg_pf = to_float(row.get("avg_test_profit_factor_improvement_pct"))
    avg_dd = to_float(row.get("avg_test_max_drawdown_improvement_pct"))
    min_trades = int(row.get("min_test_trades_count") or 0)
    dd_worse = int(row.get("drawdown_worse_test_folds") or 0)
    concentration_risks = concentration_penalties(row)

    if (
        positive_ratio >= 0.75
        and avg_pf is not None
        and avg_pf > 0
        and avg_dd is not None
        and avg_dd >= 0
        and min_trades >= min_trades_per_year
    ):
        return "select_pair_specific_walk_forward", "stable out-of-sample for this symbol"
    if positive_ratio < 0.50:
        return "reject_pair_specific_walk_forward", "positive_test_fold_ratio below 0.50"
    if avg_pf is not None and avg_pf < 0:
        return "reject_pair_specific_walk_forward", "profit factor worsens out-of-sample"
    if folds_tested and dd_worse > folds_tested / 2:
        return "reject_pair_specific_walk_forward", "drawdown worsens in the majority of test folds"
    if concentration_risks:
        return "watchlist_pair_specific_walk_forward", "; ".join(
            f"concentration penalty: {risk}" for risk in concentration_risks
        )
    return "watchlist_pair_specific_walk_forward", "interesting symbol-specific out-of-sample evidence"


def aggregate_pair_specific_detail(
    detail_rows: list[dict[str, object]],
    min_trades_per_year: int,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in detail_rows:
        grouped[(str(row["combination_key"]), str(row["symbol"]))].append(row)

    summaries = []
    for (combination_key, symbol), rows in grouped.items():
        folds_tested = len(rows)
        positive_test_folds = sum(1 for row in rows if as_bool(row.get("test_is_positive")))
        test_trades = [int(row.get("test_trades_count") or 0) for row in rows]
        pf_values = [row.get("test_profit_factor_improvement_pct") for row in rows]
        dd_values = [row.get("test_max_drawdown_improvement_pct") for row in rows]
        train_selection_scores = [row.get("train_selection_score") for row in rows]
        summary = {
            "combination_key": combination_key,
            "combination_size": int(rows[0].get("combination_size") or combination_size(combination_key)),
            "train_selection_level": int(rows[0].get("train_selection_level") or combination_size(combination_key)),
            "train_selection_score": average(train_selection_scores),
            "cost_mode": rows[0].get("cost_mode", "none"),
            "return_mode": rows[0].get("return_mode", "gross"),
            "cost_config_source": rows[0].get("cost_config_source", "not_applicable"),
            "point_size_source": rows[0].get("point_size_source", "not_applicable"),
            "spread_source_used": rows[0].get("spread_source_used", "not_applicable"),
            "symbols_using_default_costs": rows[0].get("symbols_using_default_costs", ""),
            "purge_overlap": rows[0].get("purge_overlap", "false"),
            "embargo_bars": rows[0].get("embargo_bars", 0),
            "non_overlap_test": rows[0].get("non_overlap_test", "false"),
            "train_rows_before_purge": average([row.get("train_rows_before_purge") for row in rows]),
            "train_rows_after_purge": average([row.get("train_rows_after_purge") for row in rows]),
            "test_rows_before_embargo": average([row.get("test_rows_before_embargo") for row in rows]),
            "test_rows_after_embargo": average([row.get("test_rows_after_embargo") for row in rows]),
            "test_rows_after_non_overlap": average([row.get("test_rows_after_non_overlap") for row in rows]),
            "symbol": symbol,
            "timeframe": rows[0].get("timeframe") if rows else "",
            "target_horizon": rows[0].get("target_horizon") if rows else "",
            "direction": rows[0].get("direction") if rows else "",
            "folds_tested": folds_tested,
            "positive_test_folds": positive_test_folds,
            "positive_test_fold_ratio": positive_test_folds / folds_tested if folds_tested else 0.0,
            "avg_test_trades_count": average(test_trades),
            "min_test_trades_count": min(test_trades) if test_trades else 0,
            "avg_test_profit_factor_improvement_pct": average(pf_values),
            "median_test_profit_factor_improvement_pct": median_value(pf_values),
            "avg_test_max_drawdown_improvement_pct": average(dd_values),
            "worst_test_profit_factor_improvement_pct": minimum(pf_values),
            "worst_test_drawdown_improvement_pct": minimum(dd_values),
            "avg_positive_return": average([row.get("test_avg_positive_return") for row in rows]),
            "avg_negative_return": average([row.get("test_avg_negative_return") for row in rows]),
            "payoff_ratio": average([row.get("test_payoff_ratio") for row in rows]),
            "breakeven_winrate": average([row.get("test_breakeven_winrate") for row in rows]),
            "breakeven_winrate_margin": average([row.get("test_breakeven_winrate_margin") for row in rows]),
            "monthly_positive_ratio": average([row.get("test_monthly_positive_ratio") for row in rows]),
            "quarterly_positive_ratio": average([row.get("test_quarterly_positive_ratio") for row in rows]),
            "best_month_contribution_pct": maximum([row.get("test_best_month_contribution_pct") for row in rows]),
            "top_5_percent_trades_contribution_pct": maximum(
                [row.get("test_top_5_percent_trades_contribution_pct") for row in rows]
            ),
            "max_flat_period_bars": maximum([row.get("test_max_flat_period_bars") for row in rows]),
            "profit_factor_worse_test_folds": sum(
                1 for value in pf_values if (parsed := to_float(value)) is not None and parsed < 0
            ),
            "drawdown_worse_test_folds": sum(
                1 for value in dd_values if (parsed := to_float(value)) is not None and parsed < 0
            ),
        }
        classification, notes = classify_pair_specific_summary(summary, min_trades_per_year)
        summary["pair_specific_walk_forward_classification"] = classification
        summary["notes"] = notes
        summaries.append(summary)

    class_order = {
        "select_pair_specific_walk_forward": 0,
        "watchlist_pair_specific_walk_forward": 1,
        "reject_pair_specific_walk_forward": 2,
    }
    summaries.sort(
        key=lambda row: (
            str(row["symbol"]),
            class_order.get(str(row["pair_specific_walk_forward_classification"]), 99),
            -float(row.get("positive_test_fold_ratio") or 0),
            str(row["combination_key"]),
        )
    )
    return summaries


def detail_fieldnames() -> list[str]:
    return [
        "run_id",
        "direction",
        "symbol",
        "timeframe",
        "target_horizon",
        "combination_key",
        "combination_size",
        "train_selection_level",
        "train_selection_score",
        "cost_mode",
        "return_mode",
        "cost_config_source",
        "point_size_source",
        "spread_source_used",
        "symbols_using_default_costs",
        "purge_overlap",
        "embargo_bars",
        "non_overlap_test",
        "train_rows_before_purge",
        "train_rows_after_purge",
        "test_rows_before_embargo",
        "test_rows_after_embargo",
        "test_rows_after_non_overlap",
        "train_start_year",
        "train_end_year",
        "test_year",
        "train_baseline_trades_count",
        "test_baseline_trades_count",
        "train_trades_count",
        "test_trades_count",
        "train_avg_estimated_cost_return",
        "test_avg_estimated_cost_return",
        "train_gross_profit_factor",
        "train_net_profit_factor",
        "test_gross_profit_factor",
        "test_net_profit_factor",
        "train_gross_max_drawdown",
        "train_net_max_drawdown",
        "test_gross_max_drawdown",
        "test_net_max_drawdown",
        "train_mean_return",
        "test_mean_return",
        "train_median_return",
        "test_median_return",
        "train_win_rate",
        "test_win_rate",
        "train_cumulative_return",
        "test_cumulative_return",
        "train_profit_factor",
        "test_profit_factor",
        "train_max_drawdown",
        "test_max_drawdown",
        "train_avg_positive_return",
        "test_avg_positive_return",
        "train_avg_negative_return",
        "test_avg_negative_return",
        "train_payoff_ratio",
        "test_payoff_ratio",
        "train_breakeven_winrate",
        "test_breakeven_winrate",
        "train_breakeven_winrate_margin",
        "test_breakeven_winrate_margin",
        "train_monthly_positive_ratio",
        "test_monthly_positive_ratio",
        "train_quarterly_positive_ratio",
        "test_quarterly_positive_ratio",
        "train_best_month_contribution_pct",
        "test_best_month_contribution_pct",
        "train_top_5_percent_trades_contribution_pct",
        "test_top_5_percent_trades_contribution_pct",
        "train_max_flat_period_bars",
        "test_max_flat_period_bars",
        "train_profit_factor_improvement_pct",
        "test_profit_factor_improvement_pct",
        "train_max_drawdown_improvement_pct",
        "test_max_drawdown_improvement_pct",
        "test_is_positive",
        "test_is_low_sample",
    ]


def summary_fieldnames() -> list[str]:
    return [
        "combination_key",
        "combination_size",
        "train_selection_level",
        "train_selection_score",
        "cost_mode",
        "return_mode",
        "cost_config_source",
        "point_size_source",
        "spread_source_used",
        "symbols_using_default_costs",
        "purge_overlap",
        "embargo_bars",
        "non_overlap_test",
        "train_rows_before_purge",
        "train_rows_after_purge",
        "test_rows_before_embargo",
        "test_rows_after_embargo",
        "test_rows_after_non_overlap",
        "direction",
        "timeframe",
        "target_horizon",
        "folds_tested",
        "positive_test_folds",
        "positive_test_fold_ratio",
        "symbols_tested",
        "positive_symbols",
        "positive_symbol_ratio",
        "avg_test_trades_count",
        "min_test_trades_count",
        "avg_test_profit_factor_improvement_pct",
        "median_test_profit_factor_improvement_pct",
        "avg_test_max_drawdown_improvement_pct",
        "worst_test_profit_factor_improvement_pct",
        "worst_test_drawdown_improvement_pct",
        "avg_positive_return",
        "avg_negative_return",
        "payoff_ratio",
        "breakeven_winrate",
        "breakeven_winrate_margin",
        "monthly_positive_ratio",
        "quarterly_positive_ratio",
        "best_month_contribution_pct",
        "top_5_percent_trades_contribution_pct",
        "max_flat_period_bars",
        "profit_factor_worse_test_folds",
        "drawdown_worse_test_folds",
        "walk_forward_classification",
        "classification_rationale",
    ]


def pair_specific_fieldnames() -> list[str]:
    return [
        "combination_key",
        "combination_size",
        "train_selection_level",
        "train_selection_score",
        "cost_mode",
        "return_mode",
        "cost_config_source",
        "point_size_source",
        "spread_source_used",
        "symbols_using_default_costs",
        "purge_overlap",
        "embargo_bars",
        "non_overlap_test",
        "train_rows_before_purge",
        "train_rows_after_purge",
        "test_rows_before_embargo",
        "test_rows_after_embargo",
        "test_rows_after_non_overlap",
        "symbol",
        "timeframe",
        "target_horizon",
        "direction",
        "folds_tested",
        "positive_test_folds",
        "positive_test_fold_ratio",
        "avg_test_trades_count",
        "min_test_trades_count",
        "avg_test_profit_factor_improvement_pct",
        "median_test_profit_factor_improvement_pct",
        "avg_test_max_drawdown_improvement_pct",
        "worst_test_profit_factor_improvement_pct",
        "worst_test_drawdown_improvement_pct",
        "avg_positive_return",
        "avg_negative_return",
        "payoff_ratio",
        "breakeven_winrate",
        "breakeven_winrate_margin",
        "monthly_positive_ratio",
        "quarterly_positive_ratio",
        "best_month_contribution_pct",
        "top_5_percent_trades_contribution_pct",
        "max_flat_period_bars",
        "profit_factor_worse_test_folds",
        "drawdown_worse_test_folds",
        "pair_specific_walk_forward_classification",
        "notes",
    ]


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe_value(row.get(key)) for key in fieldnames})


def fmt(value: object, digits: int = 2) -> str:
    parsed = to_float(value)
    return "n/a" if parsed is None else f"{parsed:.{digits}f}"


def report_rows(title: str, rows: list[dict[str, object]], classification_key: str, limit: int = 20) -> list[str]:
    lines = [f"## {title}", ""]
    if not rows:
        lines.extend(["- none", ""])
        return lines
    for row in rows[:limit]:
        lines.append(
            "- {combo}: class={classification}, folds={positive}/{folds}, symbol_ratio={symbol_ratio}, "
            "size={size}, train_score={train_score}, pf={pf}, dd={dd}, trades={trades}, "
            "monthly_pos={monthly}, best_month_pct={best_month}, top5_trade_pct={top_trades}".format(
                combo=row["combination_key"],
                classification=row[classification_key],
                positive=row.get("positive_test_folds"),
                folds=row.get("folds_tested"),
                symbol_ratio=fmt(row.get("positive_symbol_ratio")),
                size=row.get("combination_size", "n/a"),
                train_score=fmt(row.get("train_selection_score")),
                pf=fmt(row.get("avg_test_profit_factor_improvement_pct")),
                dd=fmt(row.get("avg_test_max_drawdown_improvement_pct")),
                trades=fmt(row.get("avg_test_trades_count"), 1),
                monthly=fmt(row.get("monthly_positive_ratio")),
                best_month=fmt(row.get("best_month_contribution_pct")),
                top_trades=fmt(row.get("top_5_percent_trades_contribution_pct")),
            )
        )
    lines.append("")
    return lines


def write_report(
    path: Path,
    *,
    run_id: str,
    direction: str,
    symbols: list[str],
    timeframe: str,
    target_horizon: int,
    train_start_year: int,
    first_test_year: int,
    last_test_year: int,
    target_column: str,
    return_column: str,
    max_combination_size: int,
    max_seed_conditions: int,
    max_candidates_per_level: int,
    max_cross_pair_candidates_per_fold: int,
    max_pair_specific_candidates_per_symbol: int,
    cost_mode: str,
    return_mode: str,
    cost_fields: dict[str, str],
    purge_overlap: bool,
    embargo_bars: int,
    non_overlap_test: bool,
    non_overlap_train_eval: bool,
    detail_rows: list[dict[str, object]],
    summaries: list[dict[str, object]],
    pair_specific_rows: list[dict[str, object]],
    warnings: list[str],
) -> None:
    selected = [row for row in summaries if row["walk_forward_classification"] == "select_walk_forward"]
    watchlist = [row for row in summaries if row["walk_forward_classification"] == "watchlist_walk_forward"]
    rejected = [row for row in summaries if row["walk_forward_classification"] == "reject_walk_forward"]
    pair_selected = [
        row for row in pair_specific_rows
        if row["pair_specific_walk_forward_classification"] != "reject_pair_specific_walk_forward"
    ]

    lines = [
        "# Walk-Forward Research Report",
        "",
        "This report is offline research only. It does not create live signals, does not load MT5, and does not use order execution APIs.",
        "",
        "## Executive Summary",
        "",
        f"- Run ID: {run_id}",
        f"- Direction: {direction}",
        f"- Symbols: {' '.join(symbols)}",
        f"- Timeframe: {timeframe}",
        f"- Target horizon: {target_horizon}",
        f"- Direction target: {target_column}",
        f"- Direction return: {'future_return_' + str(target_horizon) if direction == 'long' else '-future_return_' + str(target_horizon)}",
        f"- Cost mode: {cost_mode}",
        f"- Return mode: {return_mode}",
        f"- Ranking basis: {'estimated net returns' if return_mode == 'net' else 'gross returns'}",
        "- Performance concentration metrics penalize fragile candidates; they are not standalone promotion criteria.",
        f"- cost_config_source: {cost_fields['cost_config_source']}",
        f"- point_size_source: {cost_fields['point_size_source']}",
        f"- spread_source_used: {cost_fields['spread_source_used']}",
        f"- symbols_using_default_costs: {cost_fields['symbols_using_default_costs'] or 'none'}",
        f"- Detail rows: {len(detail_rows)}",
        f"- Cross-pair candidates: {len(selected) + len(watchlist)}",
        f"- Pair-specific rows: {len(pair_specific_rows)}",
        f"- Max combination size: {max_combination_size}",
        f"- Max seed conditions: {max_seed_conditions}",
        f"- Max candidates per beam level: {max_candidates_per_level}",
        f"- Max cross-pair candidates per fold: {max_cross_pair_candidates_per_fold}",
        f"- Max pair-specific candidates per symbol: {max_pair_specific_candidates_per_symbol}",
        "",
        "## Fold Setup",
        "",
        f"- Train start year: {train_start_year}",
        f"- First test year: {first_test_year}",
        f"- Last test year: {last_test_year}",
        "- Each fold selects hypotheses using train years only, then tests the selected hypotheses on the full future test year.",
        f"- Example final fold: train {train_start_year}-{last_test_year - 1} -> test {last_test_year}",
        "",
    ]
    lines.extend(
        [
            "## Overlapping label controls",
            "",
            f"- Purge overlap: {str(purge_overlap).lower()}",
            f"- Embargo bars: {embargo_bars}",
            f"- Non-overlap test: {str(non_overlap_test).lower()}",
            f"- Non-overlap train evaluation: {str(non_overlap_train_eval).lower()}",
            "",
            "Purge overlap removes train rows whose future label window enters the test period.",
            "Embargo creates an additional buffer by removing the first test bars after the fold boundary.",
            "`--non-overlap-test` evaluates roughly one row every target_horizon bars on test data.",
            "These controls reduce inflated apparent significance from overlapping future labels, but they also reduce sample size.",
            "",
        ]
    )
    lines.extend(report_rows("Top Walk-Forward Candidates", selected + watchlist, "walk_forward_classification"))
    lines.extend(["## Pair-Specific Walk-Forward Candidates", ""])
    if not pair_selected:
        lines.extend(["- none", ""])
    else:
        by_symbol: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in pair_selected:
            by_symbol[str(row["symbol"])].append(row)
        for symbol, rows in sorted(by_symbol.items()):
            lines.extend([f"### {symbol}", ""])
            for row in rows[:10]:
                lines.append(
                    "- {combo}: class={classification}, folds={positive}/{folds}, size={size}, train_score={train_score}, pf={pf}, dd={dd}, trades={trades}, monthly_pos={monthly}, best_month_pct={best_month}, top5_trade_pct={top_trades}".format(
                        combo=row["combination_key"],
                        classification=row["pair_specific_walk_forward_classification"],
                        positive=row["positive_test_folds"],
                        folds=row["folds_tested"],
                        size=row.get("combination_size", "n/a"),
                        train_score=fmt(row.get("train_selection_score")),
                        pf=fmt(row["avg_test_profit_factor_improvement_pct"]),
                        dd=fmt(row["avg_test_max_drawdown_improvement_pct"]),
                        trades=fmt(row["avg_test_trades_count"], 1),
                        monthly=fmt(row.get("monthly_positive_ratio")),
                        best_month=fmt(row.get("best_month_contribution_pct")),
                        top_trades=fmt(row.get("top_5_percent_trades_contribution_pct")),
                    )
                )
            lines.append("")
    lines.extend(report_rows("Rejected Candidates", rejected, "walk_forward_classification", 20))
    lines.extend(["## Warnings", ""])
    if warnings:
        for warning in sorted(set(warnings))[:80]:
            lines.append(f"- {warning}")
        if len(set(warnings)) > 80:
            lines.append(f"- Additional warnings omitted: {len(set(warnings)) - 80}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Yearly validation checks stability of hypotheses that were already found elsewhere.",
            "- Walk-forward validation is stricter: it selects using past data only and tests on a future out-of-sample year.",
            "- Cross-pair and pair-specific candidates are reported separately.",
            "- Long and short directions are written to separate output folders and are not aggregated together.",
            "- `numeric_tercile` is skipped until train-only thresholds are implemented.",
            "",
            "## Next Research-Only Action",
            "",
            "- Use selected or watchlist walk-forward rows as candidates for a separate rule-based backtest with costs, spread, slippage, SL/TP, and risk assumptions.",
            "- Do not convert this report into live signals or execution logic.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_pair_specific_report(
    path: Path,
    rows: list[dict[str, object]],
    *,
    run_id: str,
    direction: str,
    cost_fields: dict[str, str],
) -> None:
    selected = [
        row for row in rows
        if row["pair_specific_walk_forward_classification"] != "reject_pair_specific_walk_forward"
    ]
    rejected = [
        row for row in rows
        if row["pair_specific_walk_forward_classification"] == "reject_pair_specific_walk_forward"
    ]
    lines = [
        "# Pair-Specific Walk-Forward Research Candidates",
        "",
        "These rows are symbol-specific out-of-sample research leads. They are not cross-pair candidates and are not live signals.",
        "",
        f"- Run ID: {run_id}",
        f"- Direction: {direction}",
        f"- cost_config_source: {cost_fields['cost_config_source']}",
        f"- point_size_source: {cost_fields['point_size_source']}",
        f"- spread_source_used: {cost_fields['spread_source_used']}",
        f"- symbols_using_default_costs: {cost_fields['symbols_using_default_costs'] or 'none'}",
        f"- Pair-specific rows: {len(rows)}",
        f"- Selected/watchlist rows: {len(selected)}",
        f"- Rejected rows: {len(rejected)}",
        "",
        "## Top Candidates By Symbol",
        "",
    ]
    by_symbol: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in selected:
        by_symbol[str(row["symbol"])].append(row)
    if not by_symbol:
        lines.extend(["- none", ""])
    for symbol, symbol_rows in sorted(by_symbol.items()):
        lines.extend([f"### {symbol}", ""])
        for row in symbol_rows[:20]:
            lines.append(
                "- {combo}: class={classification}, folds={positive}/{folds}, size={size}, train_score={train_score}, pf={pf}, dd={dd}, trades={trades}".format(
                    combo=row["combination_key"],
                    classification=row["pair_specific_walk_forward_classification"],
                    positive=row["positive_test_folds"],
                    folds=row["folds_tested"],
                    size=row.get("combination_size", "n/a"),
                    train_score=fmt(row.get("train_selection_score")),
                    pf=fmt(row["avg_test_profit_factor_improvement_pct"]),
                    dd=fmt(row["avg_test_max_drawdown_improvement_pct"]),
                    trades=fmt(row["avg_test_trades_count"], 1),
                )
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "- Pair-specific walk-forward candidates should not be generalized to other symbols.",
            "- They are useful only as research inputs for a future symbol-specific rule-based backtest.",
            "- This report does not create signals, orders, or trading execution logic.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def resolve_output_dir(base_output_dir: Path, run_id: str, direction: str, overwrite: bool) -> Path:
    output_dir = base_output_dir / run_id / direction
    protected = [
        DETAIL_OUTPUT,
        SUMMARY_OUTPUT,
        CANDIDATES_OUTPUT,
        REPORT_OUTPUT,
        PAIR_SPECIFIC_OUTPUT,
        PAIR_SPECIFIC_REPORT_OUTPUT,
    ]
    existing = [output_dir / filename for filename in protected if (output_dir / filename).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Walk-forward output already exists under {output_dir}. Pass --overwrite to regenerate it."
        )
    return output_dir


def run(args: argparse.Namespace) -> None:
    direction = normalize_direction(args.direction)
    symbols = normalize_symbols(args.symbols)
    if not symbols:
        raise ValueError("At least one symbol is required.")
    if args.train_start_year >= args.first_test_year:
        raise ValueError("--train-start-year must be earlier than --first-test-year.")
    if args.first_test_year > args.last_test_year:
        raise ValueError("--first-test-year cannot be greater than --last-test-year.")
    if args.min_trades_per_year <= 0:
        raise ValueError("--min-trades-per-year must be greater than zero.")
    if not 0 <= args.min_positive_symbol_ratio <= 1:
        raise ValueError("--min-positive-symbol-ratio must be between 0 and 1.")
    if not 1 <= args.max_combination_size <= MAX_COMBINATION_SIZE_LIMIT:
        raise ValueError(f"--max-combination-size must be between 1 and {MAX_COMBINATION_SIZE_LIMIT}.")
    if args.embargo_bars < 0:
        raise ValueError("--embargo-bars cannot be negative.")
    for name in (
        "max_seed_conditions",
        "max_candidates_per_level",
        "max_cross_pair_candidates_per_fold",
        "max_pair_specific_candidates_per_symbol",
    ):
        if int(getattr(args, name)) <= 0:
            raise ValueError(f"--{name.replace('_', '-')} must be greater than zero.")

    run_id = args.run_id.strip() if args.run_id else datetime.now().strftime("%Y%m%d_%H%M%S")
    if not run_id:
        raise ValueError("--run-id cannot be empty.")

    timeframe = args.timeframe.strip().upper()
    target_horizon = int(args.target_horizon)
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    cost_config = load_cost_config(args.cost_config)
    target_column = target_column_for_direction(direction, target_horizon)
    return_column = f"future_return_{target_horizon}"
    all_rows, columns = load_rows(args.db_path, symbols, timeframe, return_column)
    warnings: list[str] = [NUMERIC_TERCILE_WARNING]
    if target_column not in columns:
        warnings.append(f"Target column {target_column!r} not found; walk-forward selection uses directional returns only.")

    rows_by_symbol = {
        symbol: [row for row in all_rows if str(row.get("symbol")).upper() == symbol]
        for symbol in symbols
    }
    cost_report = {}
    if cost_mode == "estimated":
        cost_report = validate_estimated_cost_config(
            symbols=symbols,
            rows_by_symbol=rows_by_symbol,
            config=cost_config,
            strict=args.strict_cost_config,
        )
        for warning in cost_report_warnings(cost_report):
            print(f"Warning: {warning}")
            warnings.append(warning)
    run_cost_fields = cost_report_fields(cost_report)
    output_dir = resolve_output_dir(args.output_dir, run_id, direction, args.overwrite)
    verbose_progress = progress if args.verbose else None
    total_folds = args.last_test_year - args.first_test_year + 1

    progress(
        f"run_id={run_id}, direction={direction}, symbols={' '.join(symbols)}, "
        f"train_start={args.train_start_year}, test_years={args.first_test_year}-{args.last_test_year}"
    )
    if args.verbose:
        progress(
            f"timeframe={timeframe}, target_horizon={target_horizon}, max_combination_size={args.max_combination_size}, "
            f"max_seed_conditions={args.max_seed_conditions}, max_candidates_per_level={args.max_candidates_per_level}, "
            f"purge_overlap={bool_text(args.purge_overlap)}, embargo_bars={args.embargo_bars}, "
            f"non_overlap_test={bool_text(args.non_overlap_test)}, "
            f"non_overlap_train_eval={bool_text(args.non_overlap_train_eval)}, "
            f"cost_mode={cost_mode}, return_mode={return_mode}"
        )

    detail_rows: list[dict[str, object]] = []
    pair_specific_detail_rows: list[dict[str, object]] = []
    for fold_index, test_year in enumerate(range(args.first_test_year, args.last_test_year + 1), start=1):
        fold_started_at = time.perf_counter()
        train_end_year = test_year - 1
        train_years = list(range(args.train_start_year, train_end_year + 1))
        train_year_set = set(train_years)
        test_year_set = {test_year}
        progress(f"fold {fold_index}/{total_folds}: train {format_year_range(train_years)} -> test {test_year}")
        train_rows_before_by_symbol = {
            symbol: rows_for_years(rows, train_year_set)
            for symbol, rows in rows_by_symbol.items()
        }
        test_rows_before_by_symbol = {
            symbol: rows_for_years(rows, test_year_set)
            for symbol, rows in rows_by_symbol.items()
        }
        train_rows_by_symbol: dict[str, list[dict[str, object]]] = {}
        test_rows_by_symbol: dict[str, list[dict[str, object]]] = {}
        overlap_counts_by_symbol: dict[str, dict[str, int]] = {}

        for symbol in symbols:
            train_before = train_rows_before_by_symbol.get(symbol, [])
            test_before = test_rows_before_by_symbol.get(symbol, [])
            if args.purge_overlap or args.embargo_bars > 0:
                train_after_purge, test_after_embargo = apply_purge_train_test_split(
                    [*train_before, *test_before],
                    train_start=year_start(args.train_start_year),
                    train_end=year_end(train_end_year),
                    test_start=year_start(test_year),
                    test_end=year_end(test_year),
                    timeframe=timeframe,
                    target_horizon=target_horizon,
                    purge_bars=None if args.purge_overlap else 0,
                    embargo_bars=args.embargo_bars,
                )
            else:
                train_after_purge = train_before
                test_after_embargo = test_before

            train_eval_rows = (
                downsample_non_overlapping_rows(train_after_purge, timeframe, target_horizon)
                if args.non_overlap_train_eval
                else train_after_purge
            )
            test_eval_rows = (
                downsample_non_overlapping_rows(test_after_embargo, timeframe, target_horizon)
                if args.non_overlap_test
                else test_after_embargo
            )
            train_rows_by_symbol[symbol] = train_eval_rows
            test_rows_by_symbol[symbol] = test_eval_rows
            overlap_counts_by_symbol[symbol] = {
                "train_rows_before_purge": len(train_before),
                "train_rows_after_purge": len(train_after_purge),
                "test_rows_before_embargo": len(test_before),
                "test_rows_after_embargo": len(test_after_embargo),
                "test_rows_after_non_overlap": len(test_eval_rows),
            }

        train_rows = sort_rows_by_time([row for rows in train_rows_by_symbol.values() for row in rows])
        if not train_rows:
            warnings.append(f"Fold test {test_year} skipped: no train rows.")
            elapsed_seconds = time.perf_counter() - fold_started_at
            progress(f"fold {fold_index}/{total_folds}: skipped in {elapsed_seconds:.1f}s, no train rows")
            continue
        single_conditions = generate_single_conditions(train_rows, columns, warnings)
        if args.verbose:
            progress(f"fold {fold_index}/{total_folds}: single conditions generated={len(single_conditions)}")
        cross_pair_candidates = selected_cross_pair_combinations(
            single_conditions,
            train_rows_by_symbol,
            train_years,
            return_column,
            direction,
            args.min_trades_per_year,
            args.min_positive_symbol_ratio,
            warnings,
            args.max_combination_size,
            args.max_seed_conditions,
            args.max_candidates_per_level,
            args.max_cross_pair_candidates_per_fold,
            cost_config,
            cost_mode,
            return_mode,
            progress_callback=verbose_progress,
        )
        if not cross_pair_candidates:
            warnings.append(f"Fold test {test_year}: no cross-pair train candidates selected.")
        if args.verbose:
            progress(f"fold {fold_index}/{total_folds}: cross-pair selected={len(cross_pair_candidates)}")

        cross_pair_symbols_logged: set[str] = set()
        for candidate in cross_pair_candidates:
            for symbol in symbols:
                overlap_counts = overlap_counts_by_symbol.get(symbol, {})
                if args.verbose and symbol not in cross_pair_symbols_logged:
                    progress(
                        f"fold {fold_index}/{total_folds}: evaluating cross-pair test rows for "
                        f"{symbol} ({len(cross_pair_candidates)} candidates)"
                    )
                    cross_pair_symbols_logged.add(symbol)
                try:
                    detail_rows.append(
                        detail_row(
                            run_id=run_id,
                            direction=direction,
                            symbol=symbol,
                            timeframe=timeframe,
                            target_horizon=target_horizon,
                            combination_key=candidate.combination_key,
                            combination_size_value=candidate.combination_size,
                            train_selection_level=candidate.train_selection_level,
                            train_selection_score=candidate.train_selection_score,
                            cost_mode=cost_mode,
                            return_mode=return_mode,
                            purge_overlap=args.purge_overlap,
                            embargo_bars=args.embargo_bars,
                            non_overlap_test=args.non_overlap_test,
                            train_rows_before_purge=int(overlap_counts.get("train_rows_before_purge", 0)),
                            train_rows_after_purge=int(overlap_counts.get("train_rows_after_purge", 0)),
                            test_rows_before_embargo=int(overlap_counts.get("test_rows_before_embargo", 0)),
                            test_rows_after_embargo=int(overlap_counts.get("test_rows_after_embargo", 0)),
                            test_rows_after_non_overlap=int(overlap_counts.get("test_rows_after_non_overlap", 0)),
                            train_start_year=args.train_start_year,
                            train_end_year=train_end_year,
                            test_year=test_year,
                            train_rows=train_rows_by_symbol.get(symbol, []),
                            test_rows=test_rows_by_symbol.get(symbol, []),
                            return_column=return_column,
                            min_trades_per_year=args.min_trades_per_year,
                            cost_config=cost_config,
                            cost_fields=cost_report_fields(cost_report, symbol),
                        )
                    )
                except ValueError as exc:
                    warnings.append(f"Fold test {test_year}: cross-pair candidate skipped: {candidate.combination_key}: {exc}")

        pair_specific_candidates = selected_pair_specific_combinations(
            single_conditions,
            train_rows_by_symbol,
            train_years,
            return_column,
            direction,
            args.min_trades_per_year,
            warnings,
            args.max_combination_size,
            args.max_seed_conditions,
            args.max_candidates_per_level,
            args.max_pair_specific_candidates_per_symbol,
            cost_config,
            cost_mode,
            return_mode,
            progress_callback=verbose_progress,
        )
        for symbol, combinations in pair_specific_candidates.items():
            overlap_counts = overlap_counts_by_symbol.get(symbol, {})
            if args.verbose:
                progress(
                    f"fold {fold_index}/{total_folds}: evaluating pair-specific test rows for "
                    f"{symbol} ({len(combinations)} candidates)"
                )
            for candidate in combinations:
                try:
                    pair_specific_detail_rows.append(
                        detail_row(
                            run_id=run_id,
                            direction=direction,
                            symbol=symbol,
                            timeframe=timeframe,
                            target_horizon=target_horizon,
                            combination_key=candidate.combination_key,
                            combination_size_value=candidate.combination_size,
                            train_selection_level=candidate.train_selection_level,
                            train_selection_score=candidate.train_selection_score,
                            cost_mode=cost_mode,
                            return_mode=return_mode,
                            purge_overlap=args.purge_overlap,
                            embargo_bars=args.embargo_bars,
                            non_overlap_test=args.non_overlap_test,
                            train_rows_before_purge=int(overlap_counts.get("train_rows_before_purge", 0)),
                            train_rows_after_purge=int(overlap_counts.get("train_rows_after_purge", 0)),
                            test_rows_before_embargo=int(overlap_counts.get("test_rows_before_embargo", 0)),
                            test_rows_after_embargo=int(overlap_counts.get("test_rows_after_embargo", 0)),
                            test_rows_after_non_overlap=int(overlap_counts.get("test_rows_after_non_overlap", 0)),
                            train_start_year=args.train_start_year,
                            train_end_year=train_end_year,
                            test_year=test_year,
                            train_rows=train_rows_by_symbol.get(symbol, []),
                            test_rows=test_rows_by_symbol.get(symbol, []),
                            return_column=return_column,
                            min_trades_per_year=args.min_trades_per_year,
                            cost_config=cost_config,
                            cost_fields=cost_report_fields(cost_report, symbol),
                        )
                    )
                except ValueError as exc:
                    warnings.append(f"Fold test {test_year}: pair-specific candidate skipped for {symbol}: {candidate.combination_key}: {exc}")
        pair_specific_counts = {
            symbol: len(combinations)
            for symbol, combinations in pair_specific_candidates.items()
        }
        pair_specific_total = sum(pair_specific_counts.values())
        elapsed_seconds = time.perf_counter() - fold_started_at
        progress(
            f"fold {fold_index}/{total_folds}: done in {elapsed_seconds:.1f}s; "
            f"singles={len(single_conditions)}, cross_pair_selected={len(cross_pair_candidates)}, "
            f"pair_specific_selected={pair_specific_total}"
        )
        if args.verbose:
            counts_text = ", ".join(f"{symbol}={count}" for symbol, count in sorted(pair_specific_counts.items()))
            progress(f"fold {fold_index}/{total_folds}: pair-specific selected by symbol: {counts_text or 'none'}")

    summaries = aggregate_walk_forward_detail(
        detail_rows,
        min_trades_per_year=args.min_trades_per_year,
        min_positive_symbol_ratio=args.min_positive_symbol_ratio,
    )
    candidates = [
        row for row in summaries
        if row["walk_forward_classification"] in {"select_walk_forward", "watchlist_walk_forward"}
    ]
    pair_specific_rows = aggregate_pair_specific_detail(pair_specific_detail_rows, args.min_trades_per_year)
    for row in summaries:
        row.update(run_cost_fields)
    for row in candidates:
        row.update(run_cost_fields)
    for row in pair_specific_rows:
        row.update(cost_report_fields(cost_report, str(row.get("symbol", ""))))

    detail_path = output_dir / DETAIL_OUTPUT
    summary_path = output_dir / SUMMARY_OUTPUT
    candidates_path = output_dir / CANDIDATES_OUTPUT
    report_path = output_dir / REPORT_OUTPUT
    pair_specific_path = output_dir / PAIR_SPECIFIC_OUTPUT
    pair_specific_report_path = output_dir / PAIR_SPECIFIC_REPORT_OUTPUT

    write_csv(detail_path, detail_rows, detail_fieldnames())
    write_csv(summary_path, summaries, summary_fieldnames())
    write_csv(candidates_path, candidates, summary_fieldnames())
    write_csv(pair_specific_path, pair_specific_rows, pair_specific_fieldnames())
    write_report(
        report_path,
        run_id=run_id,
        direction=direction,
        symbols=symbols,
        timeframe=timeframe,
        target_horizon=target_horizon,
        train_start_year=args.train_start_year,
        first_test_year=args.first_test_year,
        last_test_year=args.last_test_year,
        target_column=target_column,
        return_column=return_column,
        max_combination_size=args.max_combination_size,
        max_seed_conditions=args.max_seed_conditions,
        max_candidates_per_level=args.max_candidates_per_level,
        max_cross_pair_candidates_per_fold=args.max_cross_pair_candidates_per_fold,
        max_pair_specific_candidates_per_symbol=args.max_pair_specific_candidates_per_symbol,
        cost_mode=cost_mode,
        return_mode=return_mode,
        cost_fields=run_cost_fields,
        purge_overlap=args.purge_overlap,
        embargo_bars=args.embargo_bars,
        non_overlap_test=args.non_overlap_test,
        non_overlap_train_eval=args.non_overlap_train_eval,
        detail_rows=detail_rows,
        summaries=summaries,
        pair_specific_rows=pair_specific_rows,
        warnings=warnings,
    )
    write_pair_specific_report(
        pair_specific_report_path,
        pair_specific_rows,
        run_id=run_id,
        direction=direction,
        cost_fields=run_cost_fields,
    )

    if not detail_rows and not pair_specific_rows:
        raise ValueError(f"No walk-forward rows were produced. Outputs were written under {output_dir}; see report warnings.")

    print(f"Run ID: {run_id}")
    print(f"Direction: {direction}")
    print(f"Target: {target_column}")
    print(f"Return: {'future_return_' + str(target_horizon) if direction == 'long' else '-future_return_' + str(target_horizon)}")
    print(f"Cost mode: {cost_mode}")
    print(f"Return mode: {return_mode}")
    print(f"Strict cost config: {str(args.strict_cost_config).lower()}")
    print(f"Output directory: {output_dir}")
    print(f"Cross-pair detail rows: {len(detail_rows)}")
    print(f"Cross-pair summaries: {len(summaries)}")
    print(f"Cross-pair candidates: {len(candidates)}")
    print(f"Pair-specific rows: {len(pair_specific_rows)}")
    print(f"Max combination size: {args.max_combination_size}")
    print(f"Purge overlap: {bool_text(args.purge_overlap)}")
    print(f"Embargo bars: {args.embargo_bars}")
    print(f"Non-overlap test: {bool_text(args.non_overlap_test)}")
    print("Files created:")
    print(f"- {detail_path}")
    print(f"- {summary_path}")
    print(f"- {candidates_path}")
    print(f"- {report_path}")
    print(f"- {pair_specific_path}")
    print(f"- {pair_specific_report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run research-only walk-forward validation using train years only for hypothesis selection."
    )
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--target-horizon", type=int, default=10)
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--train-start-year", type=int, default=2020)
    parser.add_argument("--first-test-year", type=int, default=2022)
    parser.add_argument("--last-test-year", type=int, default=2025)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-trades-per-year", type=int, default=100)
    parser.add_argument("--min-positive-symbol-ratio", type=float, default=0.75)
    parser.add_argument("--max-combination-size", type=int, default=2)
    parser.add_argument("--max-seed-conditions", type=int, default=DEFAULT_MAX_SEED_CONDITIONS)
    parser.add_argument("--max-candidates-per-level", type=int, default=DEFAULT_MAX_CANDIDATES_PER_LEVEL)
    parser.add_argument(
        "--max-cross-pair-candidates-per-fold",
        type=int,
        default=DEFAULT_MAX_CROSS_PAIR_CANDIDATES_PER_FOLD,
    )
    parser.add_argument(
        "--max-pair-specific-candidates-per-symbol",
        type=int,
        default=DEFAULT_MAX_PAIR_SPECIFIC_CANDIDATES_PER_SYMBOL,
    )
    parser.add_argument("--purge-overlap", dest="purge_overlap", action="store_true")
    parser.add_argument("--no-purge-overlap", dest="purge_overlap", action="store_false")
    parser.set_defaults(purge_overlap=True)
    parser.add_argument("--embargo-bars", type=int, default=0)
    parser.add_argument("--non-overlap-test", action="store_true")
    parser.add_argument("--non-overlap-train-eval", action="store_true")
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        run(parse_args())
    except (FileNotFoundError, FileExistsError, ValueError, sqlite3.Error, OSError) as exc:
        print(f"Walk-forward research failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
