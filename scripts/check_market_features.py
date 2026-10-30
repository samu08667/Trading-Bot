from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
TABLE_NAME = "market_features"
NEWS_FEATURE_COLUMNS = [
    "relevant_currencies",
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
]
VOLUME_FEATURE_COLUMNS = [
    "tick_volume_ratio_20",
    "tick_volume_zscore_100",
    "tick_volume_percentile_100",
    "volume_spike_20",
    "volume_dry_up_20",
    "spread_to_volume_ratio",
    "volume_vs_hour_avg",
    "volume_vs_session_avg",
]
ATR_FEATURE_COLUMNS = [
    "true_range",
    "atr_14",
    "atr_20",
    "atr_50",
    "range_to_atr_20",
    "body_to_atr_20",
    "upper_wick_to_atr_20",
    "lower_wick_to_atr_20",
    "close_to_ma_fast_atr_20",
    "close_to_ma_slow_atr_20",
    "ma_diff_atr_20",
    "volatility_100",
    "volatility_ratio_20_100",
    "spread_price",
    "spread_return",
    "spread_to_atr_20",
]


def table_exists(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    )
    return cursor.fetchone() is not None


def scalar(connection: sqlite3.Connection, query: str) -> int | float | str | None:
    return connection.execute(query).fetchone()[0]


def print_group_counts(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        f"""
        SELECT
            symbol,
            timeframe,
            COUNT(*) AS total,
            MIN(time_server) AS min_time_server,
            MAX(time_server) AS max_time_server,
            SUM(CASE WHEN blackout_window_30m = 1 THEN 1 ELSE 0 END) AS blackout_30m,
            SUM(CASE WHEN has_high_impact_news_next_30m = 1 THEN 1 ELSE 0 END) AS high_next_30m
        FROM {TABLE_NAME}
        GROUP BY symbol, timeframe
        ORDER BY symbol ASC, timeframe ASC
        """
    ).fetchall()

    print("Market features by symbol/timeframe:")
    if not rows:
        print("- none: 0")
        return

    for symbol, timeframe, total, min_time, max_time, blackout_30m, high_next_30m in rows:
        print(
            f"- {symbol} {timeframe}: {total} rows, "
            f"MIN(time_server)={min_time}, MAX(time_server)={max_time}, "
            f"blackout_window_30m={blackout_30m}, "
            f"has_high_impact_news_next_30m={high_next_30m}"
        )


def print_basic_stats(connection: sqlite3.Connection, column: str) -> None:
    row = connection.execute(
        f"""
        SELECT
            COUNT({column}) AS non_null_count,
            MIN({column}) AS min_value,
            AVG({column}) AS avg_value,
            MAX({column}) AS max_value
        FROM {TABLE_NAME}
        """
    ).fetchone()
    non_null_count, min_value, avg_value, max_value = row
    avg_text = "NULL" if avg_value is None else f"{avg_value:.4f}"
    print(
        f"{column}: count={non_null_count}, "
        f"min={min_value}, avg={avg_text}, max={max_value}"
    )


def table_columns(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    return {str(row[1]) for row in rows}


def missing_news_feature_count(connection: sqlite3.Connection) -> int:
    null_checks = " OR ".join(f"{column} IS NULL" for column in NEWS_FEATURE_COLUMNS)
    return int(
        scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            WHERE {null_checks}
            """,
        )
    )


def check_market_features(db_path: Path = DATABASE_PATH) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        if not table_exists(connection):
            raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")

        total_rows = scalar(connection, f"SELECT COUNT(*) FROM {TABLE_NAME}")
        min_time = scalar(connection, f"SELECT MIN(time_server) FROM {TABLE_NAME}")
        max_time = scalar(connection, f"SELECT MAX(time_server) FROM {TABLE_NAME}")

        print("Market features database check")
        print(f"Database path: {db_path}")
        print(f"Total market_features rows: {total_rows}")
        print(f"MIN(time_server): {min_time}")
        print(f"MAX(time_server): {max_time}")
        print_group_counts(connection)
        print("Minutes statistics:")
        print_basic_stats(connection, "minutes_to_next_news")
        print_basic_stats(connection, "minutes_from_last_news")
        print("Volume/liquidity feature statistics:")
        available_columns = table_columns(connection)
        for column in VOLUME_FEATURE_COLUMNS:
            if column in available_columns:
                print_basic_stats(connection, column)
        print("ATR/range feature statistics:")
        for column in ATR_FEATURE_COLUMNS:
            if column in available_columns:
                print_basic_stats(connection, column)
        print(f"Rows with missing news features: {missing_news_feature_count(connection)}")


def main() -> int:
    try:
        check_market_features()
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(f"Market features check failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
