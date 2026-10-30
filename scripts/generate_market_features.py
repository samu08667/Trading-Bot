import argparse
from bisect import bisect_left, bisect_right
from datetime import datetime
from pathlib import Path
import re
import sqlite3

try:
    from regime_classification import REGIME_CLASSIFICATION_COLUMNS, with_regime_labels
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.regime_classification import REGIME_CLASSIFICATION_COLUMNS, with_regime_labels


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
PRICE_FEATURES_TABLE = "price_features"
ECONOMIC_EVENTS_TABLE = "economic_events"
MARKET_FEATURES_TABLE = "market_features"

SYMBOL_CURRENCY_MAP = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "USDJPY": ("USD", "JPY"),
    "XAUUSD": ("USD",),
    "XAGUSD": ("USD",),
}

PRICE_FEATURE_COLUMNS = [
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
]

MARKET_FEATURE_COLUMNS = [
    "symbol",
    "timeframe",
    "time_server",
    *PRICE_FEATURE_COLUMNS,
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
    "source",
]


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


def parse_time_server(value: str) -> datetime:
    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    raise ValueError(f"Unsupported time_server format: {value!r}")


def normalize_symbol(symbol: str) -> str:
    cleaned = re.sub(r"[^A-Z]", "", symbol.upper())
    for base_symbol in SYMBOL_CURRENCY_MAP:
        if cleaned.startswith(base_symbol):
            return base_symbol
    return cleaned


def parse_currency_list(value: str) -> tuple[str, ...]:
    currencies = []
    for item in value.split(","):
        currency = item.strip().upper()
        if currency and currency not in currencies:
            currencies.append(currency)
    return tuple(currencies)


def resolve_relevant_currencies(symbol: str, override: str | None) -> tuple[str, ...]:
    if override:
        currencies = parse_currency_list(override)
        if currencies:
            return currencies

    normalized_symbol = normalize_symbol(symbol)
    return SYMBOL_CURRENCY_MAP.get(normalized_symbol, ())


def fetch_price_features(connection: sqlite3.Connection, symbol: str, timeframe: str) -> list[sqlite3.Row]:
    available_columns = table_columns(connection, PRICE_FEATURES_TABLE)
    regime_columns = set(REGIME_CLASSIFICATION_COLUMNS)
    missing_required_columns = [
        column for column in PRICE_FEATURE_COLUMNS if column not in available_columns and column not in regime_columns
    ]
    if missing_required_columns:
        raise sqlite3.OperationalError(
            f"{PRICE_FEATURES_TABLE} is missing required columns: {', '.join(missing_required_columns)}"
        )
    price_columns = [
        quote_identifier(column) if column in available_columns else f"NULL AS {quote_identifier(column)}"
        for column in PRICE_FEATURE_COLUMNS
    ]
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            f"""
            SELECT
                symbol,
                timeframe,
                time_server,
                {", ".join(price_columns)}
            FROM {PRICE_FEATURES_TABLE}
            WHERE symbol = ? AND timeframe = ?
            ORDER BY time_server ASC
            """,
            (symbol, timeframe),
        ).fetchall()
    finally:
        connection.row_factory = None


def fetch_economic_events(
    connection: sqlite3.Connection,
    currencies: tuple[str, ...],
) -> list[dict[str, object]]:
    if not currencies:
        return []

    placeholders = ", ".join("?" for _ in currencies)
    rows = connection.execute(
        f"""
        SELECT time_server, currency, importance
        FROM {ECONOMIC_EVENTS_TABLE}
        WHERE currency IN ({placeholders})
          AND importance >= 0
          AND time_server IS NOT NULL
          AND TRIM(time_server) != ''
        ORDER BY time_server ASC
        """,
        currencies,
    ).fetchall()

    events = []
    for time_server, currency, importance in rows:
        try:
            event_time = parse_time_server(str(time_server))
        except ValueError:
            continue

        events.append(
            {
                "time": event_time,
                "currency": currency,
                "importance": int(importance) if importance is not None else 0,
            }
        )

    events.sort(key=lambda event: event["time"])
    return events


def max_importance(events: list[dict[str, object]]) -> int | None:
    if not events:
        return None
    return max(int(event["importance"]) for event in events)


def build_news_features(
    candle_time: datetime,
    events: list[dict[str, object]],
    event_times: list[datetime],
    event_timestamps: list[float],
) -> dict[str, object]:
    next_index = bisect_left(event_times, candle_time)
    prev_index = next_index - 1

    next_event = events[next_index] if next_index < len(events) else None
    last_event = events[prev_index] if prev_index >= 0 else None

    minutes_to_next = None
    if next_event is not None:
        minutes_to_next = (next_event["time"] - candle_time).total_seconds() / 60

    minutes_from_last = None
    if last_event is not None:
        minutes_from_last = (candle_time - last_event["time"]).total_seconds() / 60

    next_30_end = candle_time.timestamp() + 30 * 60
    next_60_end = candle_time.timestamp() + 60 * 60
    prev_30_start = candle_time.timestamp() - 30 * 60
    prev_60_start = candle_time.timestamp() - 60 * 60
    candle_ts = candle_time.timestamp()

    next_30 = events[next_index:bisect_right(event_timestamps, next_30_end)]
    next_60 = events[next_index:bisect_right(event_timestamps, next_60_end)]
    prev_30 = events[bisect_left(event_timestamps, prev_30_start):bisect_left(event_timestamps, candle_ts)]
    prev_60 = events[bisect_left(event_timestamps, prev_60_start):bisect_left(event_timestamps, candle_ts)]

    high_next_30 = any(int(event["importance"]) >= 2 for event in next_30)
    high_next_60 = any(int(event["importance"]) >= 2 for event in next_60)
    high_prev_30 = any(int(event["importance"]) >= 2 for event in prev_30)
    high_prev_60 = any(int(event["importance"]) >= 2 for event in prev_60)

    return {
        "minutes_to_next_news": minutes_to_next,
        "minutes_from_last_news": minutes_from_last,
        "has_news_next_30m": int(bool(next_30)),
        "has_news_next_60m": int(bool(next_60)),
        "has_high_impact_news_next_30m": int(high_next_30),
        "has_high_impact_news_next_60m": int(high_next_60),
        "has_high_impact_news_prev_30m": int(high_prev_30),
        "has_high_impact_news_prev_60m": int(high_prev_60),
        "blackout_window_30m": int(high_next_30),
        "blackout_window_60m": int(high_next_60),
        "post_news_window_30m": int(high_prev_30),
        "post_news_window_60m": int(high_prev_60),
        "news_count_next_60m": len(next_60),
        "news_count_prev_60m": len(prev_60),
        "max_importance_next_60m": max_importance(next_60),
        "max_importance_prev_60m": max_importance(prev_60),
        "next_news_currency": next_event["currency"] if next_event is not None else None,
        "next_news_importance": next_event["importance"] if next_event is not None else None,
        "last_news_currency": last_event["currency"] if last_event is not None else None,
        "last_news_importance": last_event["importance"] if last_event is not None else None,
    }


def generate_market_feature_rows(
    price_rows: list[sqlite3.Row],
    events: list[dict[str, object]],
    relevant_currencies: tuple[str, ...],
) -> tuple[list[dict[str, object]], int]:
    generated = []
    skipped = 0
    event_times = [event["time"] for event in events]
    event_timestamps = [event_time.timestamp() for event_time in event_times]
    relevant_currencies_text = ",".join(relevant_currencies)

    for row in price_rows:
        try:
            candle_time = parse_time_server(str(row["time_server"]))
        except ValueError:
            skipped += 1
            continue

        news_features = build_news_features(candle_time, events, event_times, event_timestamps)
        market_row = with_regime_labels({
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "time_server": row["time_server"],
            "relevant_currencies": relevant_currencies_text,
            "source": "price_features+economic_events",
            **{column: row[column] for column in PRICE_FEATURE_COLUMNS},
            **news_features,
        })
        generated.append(market_row)

    return generated, skipped


def insert_market_features(connection: sqlite3.Connection, rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0

    placeholders = ", ".join("?" for _ in MARKET_FEATURE_COLUMNS)
    insert_sql = f"""
        INSERT OR REPLACE INTO {MARKET_FEATURES_TABLE} ({", ".join(MARKET_FEATURE_COLUMNS)})
        VALUES ({placeholders})
    """
    values = [tuple(row[column] for column in MARKET_FEATURE_COLUMNS) for row in rows]
    connection.executemany(insert_sql, values)
    return len(values)


def generate_market_features(
    *,
    symbol: str,
    timeframe: str,
    db_path: Path,
    news_currencies: str | None,
) -> dict[str, int]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    relevant_currencies = resolve_relevant_currencies(symbol, news_currencies)
    if not relevant_currencies:
        raise ValueError(
            f"No news currency mapping found for {symbol!r}. Pass --news-currencies to override."
        )

    with sqlite3.connect(db_path) as connection:
        for table_name in (PRICE_FEATURES_TABLE, ECONOMIC_EVENTS_TABLE, MARKET_FEATURES_TABLE):
            if not table_exists(connection, table_name):
                raise sqlite3.OperationalError(
                    f"Table {table_name!r} does not exist. Run python scripts/init_database.py first."
                )

        price_rows = fetch_price_features(connection, symbol, timeframe)
        economic_events = fetch_economic_events(connection, relevant_currencies)
        market_rows, rows_skipped = generate_market_feature_rows(
            price_rows,
            economic_events,
            relevant_currencies,
        )
        rows_changed = insert_market_features(connection, market_rows)
        connection.commit()

    return {
        "rows_price_features_read": len(price_rows),
        "economic_events_considered": len(economic_events),
        "rows_generated": len(market_rows),
        "rows_inserted_updated": rows_changed,
        "rows_skipped": rows_skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate market features by combining price features with economic calendar timing."
    )
    parser.add_argument("--symbol", required=True, help="Symbol to process, for example EURUSD.")
    parser.add_argument("--timeframe", required=True, help="Timeframe to process, for example M15.")
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    parser.add_argument(
        "--news-currencies",
        help='Optional comma-separated override, for example "USD,EUR".',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbol = args.symbol.strip().upper()
    timeframe = args.timeframe.strip().upper()

    try:
        result = generate_market_features(
            symbol=symbol,
            timeframe=timeframe,
            db_path=args.db_path,
            news_currencies=args.news_currencies,
        )
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"Market feature generation failed: {exc}")
        return 1

    print("Market feature generation complete.")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Rows price_features read: {result['rows_price_features_read']}")
    print(f"Economic events considered: {result['economic_events_considered']}")
    print(f"Rows generated: {result['rows_generated']}")
    print(f"Rows inserted/updated: {result['rows_inserted_updated']}")
    print(f"Rows skipped: {result['rows_skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
