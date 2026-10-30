import argparse
from pathlib import Path
import sqlite3

try:
    from regime_classification import REGIME_CLASSIFICATION_COLUMNS, with_regime_labels
    from target_families import (
        barrier_bars_column,
        barrier_hit_first_column,
        triple_barrier_column,
        triple_barrier_label_specs,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.regime_classification import REGIME_CLASSIFICATION_COLUMNS, with_regime_labels
    from scripts.target_families import (
        barrier_bars_column,
        barrier_hit_first_column,
        triple_barrier_column,
        triple_barrier_label_specs,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
MARKET_FEATURES_TABLE = "market_features"
ML_DATASET_TABLE = "ml_dataset"

INPUT_COLUMNS = [
    "symbol",
    "timeframe",
    "time_server",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "return_1",
    "return_5",
    "return_20",
    "candle_range",
    "body_size",
    "upper_wick",
    "lower_wick",
    "true_range",
    "atr_14",
    "atr_20",
    "atr_50",
    "range_to_atr_20",
    "body_to_atr_20",
    "upper_wick_to_atr_20",
    "lower_wick_to_atr_20",
    "volatility_20",
    "volatility_100",
    "volatility_ratio_20_100",
    "ma_fast",
    "ma_slow",
    "ma_diff",
    "close_to_ma_fast_atr_20",
    "close_to_ma_slow_atr_20",
    "ma_diff_atr_20",
    "spread_avg_20",
    "spread_price",
    "spread_return",
    "spread_to_atr_20",
    "tick_volume_avg_20",
    "tick_volume_ratio_20",
    "tick_volume_zscore_100",
    "tick_volume_percentile_100",
    "volume_spike_20",
    "volume_dry_up_20",
    "spread_to_volume_ratio",
    "volume_vs_hour_avg",
    "volume_vs_session_avg",
    "session",
    "spread_liquidity_regime",
    "volatility_regime",
    "range_regime",
    "volume_liquidity_regime",
    "hour_session",
    "hour",
    "day_of_week",
    "relevant_currencies",
    "minutes_to_next_news",
    "minutes_from_last_news",
    "has_news_next_30m",
    "has_news_next_60m",
    "has_high_impact_news_next_30m",
    "has_high_impact_news_next_60m",
    "has_high_impact_news_prev_30m",
    "has_high_impact_news_prev_60m",
    "blackout_window_30m",
    "blackout_window_60m",
    "post_news_window_30m",
    "post_news_window_60m",
    "news_count_next_60m",
    "news_count_prev_60m",
    "max_importance_next_60m",
    "max_importance_prev_60m",
    "next_news_currency",
    "next_news_importance",
    "last_news_currency",
    "last_news_importance",
]

HORIZONS = (5, 10, 20)
TRIPLE_BARRIER_HORIZONS = HORIZONS
TRIPLE_BARRIER_SPECS = triple_barrier_label_specs()


TRIPLE_BARRIER_TARGET_COLUMNS = [
    column
    for horizon in TRIPLE_BARRIER_HORIZONS
    for direction, tp_atr, sl_atr in TRIPLE_BARRIER_SPECS
    for column in (
        barrier_hit_first_column(direction, tp_atr, sl_atr, horizon),
        triple_barrier_column(direction, tp_atr, sl_atr, horizon),
        barrier_bars_column(direction, tp_atr, sl_atr, horizon),
    )
]

# Net-aware labels intentionally stay out of ml_dataset until broker-specific
# cost assumptions can be versioned without mixing gross and net label sets.
TARGET_COLUMNS = [
    "future_return_5",
    "future_return_10",
    "future_return_20",
    "future_max_return_5",
    "future_min_return_5",
    "future_range_5",
    "long_mfe_5",
    "long_mae_5",
    "short_mfe_5",
    "short_mae_5",
    "target_long_good_5",
    "target_short_good_5",
    "future_max_return_10",
    "future_min_return_10",
    "future_range_10",
    "long_mfe_10",
    "long_mae_10",
    "short_mfe_10",
    "short_mae_10",
    "target_long_good_10",
    "target_short_good_10",
    *TRIPLE_BARRIER_TARGET_COLUMNS,
    "future_max_return_20",
    "future_min_return_20",
    "future_range_20",
    "long_mfe_20",
    "long_mae_20",
    "short_mfe_20",
    "short_mae_20",
    "target_long_good_20",
    "target_short_good_20",
    "target_up_5",
    "target_up_10",
    "target_up_20",
    "target_down_5",
    "target_down_10",
    "target_down_20",
]

ML_DATASET_COLUMNS = [*INPUT_COLUMNS, *TARGET_COLUMNS, "source"]


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def fetch_market_features(connection: sqlite3.Connection, symbol: str, timeframe: str) -> list[sqlite3.Row]:
    available_columns = table_columns(connection, MARKET_FEATURES_TABLE)
    regime_columns = set(REGIME_CLASSIFICATION_COLUMNS)
    missing_required_columns = [
        column for column in INPUT_COLUMNS if column not in available_columns and column not in regime_columns
    ]
    if missing_required_columns:
        raise sqlite3.OperationalError(
            f"{MARKET_FEATURES_TABLE} is missing required columns: {', '.join(missing_required_columns)}"
        )
    select_columns = [
        quote_identifier(column) if column in available_columns else f"NULL AS {quote_identifier(column)}"
        for column in INPUT_COLUMNS
    ]
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            f"""
            SELECT {", ".join(select_columns)}
            FROM {MARKET_FEATURES_TABLE}
            WHERE symbol = ? AND timeframe = ?
            ORDER BY time_server ASC
            """,
            (symbol, timeframe),
        ).fetchall()
    finally:
        connection.row_factory = None


def safe_future_return(current_close: float, future_close: float | None) -> float | None:
    if future_close is None or current_close == 0:
        return None
    return future_close / current_close - 1


def safe_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def future_window_extreme(
    values: list[float | None],
    index: int,
    horizon: int,
    mode: str,
) -> float | None:
    if index + horizon >= len(values):
        return None
    window = values[index + 1 : index + horizon + 1]
    if len(window) != horizon or any(value is None for value in window):
        return None
    numeric_window = [float(value) for value in window if value is not None]
    if mode == "max":
        return max(numeric_window)
    if mode == "min":
        return min(numeric_window)
    raise ValueError(f"Unsupported future window mode: {mode}")


def safe_future_price_return(current_close: float, future_price: float | None) -> float | None:
    if future_price is None or current_close == 0:
        return None
    return future_price / current_close - 1


def target_long_good(
    future_return: float | None,
    long_mfe: float | None,
    long_mae: float | None,
) -> int | None:
    if future_return is None or long_mfe is None or long_mae is None:
        return None
    return int(future_return > 0 and long_mfe > abs(long_mae))


def target_short_good(
    future_return: float | None,
    short_mfe: float | None,
    short_mae: float | None,
) -> int | None:
    if future_return is None or short_mfe is None or short_mae is None:
        return None
    return int(future_return < 0 and short_mfe > abs(short_mae))


def target_up(future_return: float | None, threshold: float) -> int | None:
    if future_return is None:
        return None
    return int(future_return > threshold)


def target_down(future_return: float | None, threshold: float) -> int | None:
    if future_return is None:
        return None
    return int(future_return < -threshold)


def triple_barrier_result(
    *,
    current_close: float,
    current_atr: float | None,
    highs: list[float | None],
    lows: list[float | None],
    index: int,
    horizon: int,
    direction: str,
    tp_atr: float,
    sl_atr: float,
) -> tuple[int | None, int | None, int | None]:
    if current_atr is None or current_atr <= 0 or current_close == 0:
        return None, None, None
    if index + horizon >= len(highs):
        return None, None, None

    future_highs = highs[index + 1 : index + horizon + 1]
    future_lows = lows[index + 1 : index + horizon + 1]
    if (
        len(future_highs) != horizon
        or len(future_lows) != horizon
        or any(value is None for value in future_highs)
        or any(value is None for value in future_lows)
    ):
        return None, None, None

    if direction == "long":
        tp_price = current_close + tp_atr * current_atr
        sl_price = current_close - sl_atr * current_atr
    elif direction == "short":
        tp_price = current_close - tp_atr * current_atr
        sl_price = current_close + sl_atr * current_atr
    else:
        raise ValueError(f"Unsupported triple-barrier direction: {direction}")

    for bars_ahead, (future_high, future_low) in enumerate(
        zip(future_highs, future_lows),
        start=1,
    ):
        high_price = float(future_high)
        low_price = float(future_low)
        if direction == "long":
            stop_hit = low_price <= sl_price
            take_hit = high_price >= tp_price
        else:
            stop_hit = high_price >= sl_price
            take_hit = low_price <= tp_price

        # OHLC bars do not reveal intrabar ordering, so same-bar TP/SL touches
        # are labeled conservatively as stop-first.
        if stop_hit:
            return -1, 0, bars_ahead
        if take_hit:
            return 1, 1, bars_ahead

    return 0, 0, None


def triple_barrier_labels(
    *,
    current_close: float,
    current_atr: float | None,
    highs: list[float | None],
    lows: list[float | None],
    index: int,
) -> dict[str, int | None]:
    labels: dict[str, int | None] = {}
    for horizon in TRIPLE_BARRIER_HORIZONS:
        for direction, tp_atr, sl_atr in TRIPLE_BARRIER_SPECS:
            triple_label, tp_hit_first, bars_to_first_barrier = triple_barrier_result(
                current_close=current_close,
                current_atr=current_atr,
                highs=highs,
                lows=lows,
                index=index,
                horizon=horizon,
                direction=direction,
                tp_atr=tp_atr,
                sl_atr=sl_atr,
            )
            labels[barrier_hit_first_column(direction, tp_atr, sl_atr, horizon)] = tp_hit_first
            labels[triple_barrier_column(direction, tp_atr, sl_atr, horizon)] = triple_label
            labels[barrier_bars_column(direction, tp_atr, sl_atr, horizon)] = bars_to_first_barrier
    return labels


def generate_rows(
    market_rows: list[sqlite3.Row],
    min_return_threshold: float,
) -> tuple[list[dict[str, object]], int]:
    generated = []
    skipped = 0
    closes: list[float | None] = []
    highs: list[float | None] = []
    lows: list[float | None] = []
    atr_20_values: list[float | None] = []

    for row in market_rows:
        closes.append(safe_float(row["close"]))
        highs.append(safe_float(row["high"]))
        lows.append(safe_float(row["low"]))
        atr_20_values.append(safe_float(row["atr_20"]))

    for index, row in enumerate(market_rows):
        current_close = closes[index]
        if current_close is None or current_close == 0:
            skipped += 1
            continue

        future_returns: dict[int, float | None] = {}
        future_max_returns: dict[int, float | None] = {}
        future_min_returns: dict[int, float | None] = {}
        future_ranges: dict[int, float | None] = {}
        long_mfes: dict[int, float | None] = {}
        long_maes: dict[int, float | None] = {}
        short_mfes: dict[int, float | None] = {}
        short_maes: dict[int, float | None] = {}
        for horizon in HORIZONS:
            future_index = index + horizon
            future_close = closes[future_index] if future_index < len(closes) else None
            future_returns[horizon] = safe_future_return(current_close, future_close)
            future_high = future_window_extreme(highs, index, horizon, "max")
            future_low = future_window_extreme(lows, index, horizon, "min")
            future_max_returns[horizon] = safe_future_price_return(current_close, future_high)
            future_min_returns[horizon] = safe_future_price_return(current_close, future_low)
            if future_max_returns[horizon] is not None and future_min_returns[horizon] is not None:
                future_ranges[horizon] = future_max_returns[horizon] - future_min_returns[horizon]
            else:
                future_ranges[horizon] = None
            long_mfes[horizon] = (
                max(future_max_returns[horizon], 0.0)
                if future_max_returns[horizon] is not None
                else None
            )
            long_maes[horizon] = (
                min(future_min_returns[horizon], 0.0)
                if future_min_returns[horizon] is not None
                else None
            )
            short_mfes[horizon] = (
                max(-future_min_returns[horizon], 0.0)
                if future_min_returns[horizon] is not None
                else None
            )
            short_maes[horizon] = (
                min(-future_max_returns[horizon], 0.0)
                if future_max_returns[horizon] is not None
                else None
            )

        dataset_row = with_regime_labels({column: row[column] for column in INPUT_COLUMNS})
        triple_barriers = triple_barrier_labels(
            current_close=current_close,
            current_atr=atr_20_values[index],
            highs=highs,
            lows=lows,
            index=index,
        )
        dataset_row.update(
            {
                "future_return_5": future_returns[5],
                "future_return_10": future_returns[10],
                "future_return_20": future_returns[20],
                "future_max_return_5": future_max_returns[5],
                "future_min_return_5": future_min_returns[5],
                "future_range_5": future_ranges[5],
                "long_mfe_5": long_mfes[5],
                "long_mae_5": long_maes[5],
                "short_mfe_5": short_mfes[5],
                "short_mae_5": short_maes[5],
                "target_long_good_5": target_long_good(
                    future_returns[5],
                    long_mfes[5],
                    long_maes[5],
                ),
                "target_short_good_5": target_short_good(
                    future_returns[5],
                    short_mfes[5],
                    short_maes[5],
                ),
                "future_max_return_10": future_max_returns[10],
                "future_min_return_10": future_min_returns[10],
                "future_range_10": future_ranges[10],
                "long_mfe_10": long_mfes[10],
                "long_mae_10": long_maes[10],
                "short_mfe_10": short_mfes[10],
                "short_mae_10": short_maes[10],
                "target_long_good_10": target_long_good(
                    future_returns[10],
                    long_mfes[10],
                    long_maes[10],
                ),
                "target_short_good_10": target_short_good(
                    future_returns[10],
                    short_mfes[10],
                    short_maes[10],
                ),
                **triple_barriers,
                "future_max_return_20": future_max_returns[20],
                "future_min_return_20": future_min_returns[20],
                "future_range_20": future_ranges[20],
                "long_mfe_20": long_mfes[20],
                "long_mae_20": long_maes[20],
                "short_mfe_20": short_mfes[20],
                "short_mae_20": short_maes[20],
                "target_long_good_20": target_long_good(
                    future_returns[20],
                    long_mfes[20],
                    long_maes[20],
                ),
                "target_short_good_20": target_short_good(
                    future_returns[20],
                    short_mfes[20],
                    short_maes[20],
                ),
                "target_up_5": target_up(future_returns[5], min_return_threshold),
                "target_up_10": target_up(future_returns[10], min_return_threshold),
                "target_up_20": target_up(future_returns[20], min_return_threshold),
                "target_down_5": target_down(future_returns[5], min_return_threshold),
                "target_down_10": target_down(future_returns[10], min_return_threshold),
                "target_down_20": target_down(future_returns[20], min_return_threshold),
                "source": "market_features",
            }
        )
        generated.append(dataset_row)

    return generated, skipped


def insert_ml_dataset(connection: sqlite3.Connection, rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0

    placeholders = ", ".join("?" for _ in ML_DATASET_COLUMNS)
    insert_sql = f"""
        INSERT OR REPLACE INTO {ML_DATASET_TABLE} ({", ".join(ML_DATASET_COLUMNS)})
        VALUES ({placeholders})
    """
    values = [tuple(row[column] for column in ML_DATASET_COLUMNS) for row in rows]
    connection.executemany(insert_sql, values)
    return len(values)


def generate_ml_dataset(
    *,
    symbol: str,
    timeframe: str,
    db_path: Path,
    min_return_threshold: float,
) -> dict[str, int]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    if min_return_threshold < 0:
        raise ValueError("--min-return-threshold must be greater than or equal to zero.")

    with sqlite3.connect(db_path) as connection:
        for table_name in (MARKET_FEATURES_TABLE, ML_DATASET_TABLE):
            if not table_exists(connection, table_name):
                raise sqlite3.OperationalError(
                    f"Table {table_name!r} does not exist. Run python scripts/init_database.py first."
                )

        market_rows = fetch_market_features(connection, symbol, timeframe)
        dataset_rows, rows_skipped = generate_rows(market_rows, min_return_threshold)
        rows_changed = insert_ml_dataset(connection, dataset_rows)
        connection.commit()

    return {
        "rows_read": len(market_rows),
        "rows_generated": len(dataset_rows),
        "rows_inserted_updated": rows_changed,
        "rows_skipped": rows_skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a supervised ML dataset table from market_features without training models."
    )
    parser.add_argument("--symbol", required=True, help="Symbol to process, for example EURUSD.")
    parser.add_argument("--timeframe", required=True, help="Timeframe to process, for example M15.")
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    parser.add_argument(
        "--min-return-threshold",
        type=float,
        default=0.0,
        help="Minimum absolute return threshold for directional targets. Default: 0.0",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbol = args.symbol.strip().upper()
    timeframe = args.timeframe.strip().upper()

    try:
        result = generate_ml_dataset(
            symbol=symbol,
            timeframe=timeframe,
            db_path=args.db_path,
            min_return_threshold=args.min_return_threshold,
        )
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"ML dataset generation failed: {exc}")
        return 1

    print("ML dataset generation complete.")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Minimum return threshold: {args.min_return_threshold}")
    print(f"Rows read: {result['rows_read']}")
    print(f"Rows generated: {result['rows_generated']}")
    print(f"Rows inserted/updated: {result['rows_inserted_updated']}")
    print(f"Rows skipped: {result['rows_skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
