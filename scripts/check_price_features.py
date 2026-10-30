from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
TABLE_NAME = "price_features"
MAIN_FEATURE_COLUMNS = [
    "return_1",
    "return_5",
    "return_20",
    "candle_range",
    "body_size",
    "volatility_20",
    "volatility_100",
    "ma_fast",
    "ma_slow",
    "ma_diff",
    "spread_avg_20",
    "spread_price",
    "spread_return",
    "tick_volume_avg_20",
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
    "volatility_ratio_20_100",
    "spread_to_atr_20",
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


def table_exists(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    )
    return cursor.fetchone() is not None


def scalar(connection: sqlite3.Connection, query: str) -> int | float | str | None:
    return connection.execute(query).fetchone()[0]


def table_columns(connection: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})")}


def print_group_counts(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        f"""
        SELECT
            symbol,
            timeframe,
            COUNT(*) AS total,
            MIN(time_server) AS min_time_server,
            MAX(time_server) AS max_time_server
        FROM {TABLE_NAME}
        GROUP BY symbol, timeframe
        ORDER BY symbol ASC, timeframe ASC
        """
    ).fetchall()

    print("Features by symbol/timeframe:")
    if not rows:
        print("- none: 0")
        return

    for symbol, timeframe, total, min_time_server, max_time_server in rows:
        print(
            f"- {symbol} {timeframe}: {total} rows, "
            f"MIN(time_server)={min_time_server}, MAX(time_server)={max_time_server}"
        )


def print_null_counts(connection: sqlite3.Connection) -> None:
    columns = table_columns(connection)
    print("NULL counts in main features:")
    for column in MAIN_FEATURE_COLUMNS:
        if column not in columns:
            print(f"- {column}: missing column")
            continue
        count = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            WHERE {column} IS NULL
            """,
        )
        print(f"- {column}: {count}")


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

    if avg_value is None:
        avg_text = "NULL"
    else:
        avg_text = f"{avg_value:.10f}"

    print(
        f"{column}: count={non_null_count}, "
        f"min={min_value}, avg={avg_text}, max={max_value}"
    )


def print_volume_feature_stats(connection: sqlite3.Connection) -> None:
    columns = table_columns(connection)
    print("Volume/liquidity feature statistics:")
    for column in VOLUME_FEATURE_COLUMNS:
        if column not in columns:
            print(f"- {column}: missing column")
            continue
        print_basic_stats(connection, column)


def print_atr_feature_stats(connection: sqlite3.Connection) -> None:
    columns = table_columns(connection)
    print("ATR/range feature statistics:")
    for column in ATR_FEATURE_COLUMNS:
        if column not in columns:
            print(f"- {column}: missing column")
            continue
        print_basic_stats(connection, column)


def check_price_features(db_path: Path = DATABASE_PATH) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        if not table_exists(connection):
            raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")

        total_features = scalar(connection, f"SELECT COUNT(*) FROM {TABLE_NAME}")
        min_time = scalar(connection, f"SELECT MIN(time_server) FROM {TABLE_NAME}")
        max_time = scalar(connection, f"SELECT MAX(time_server) FROM {TABLE_NAME}")

        print("Price features database check")
        print(f"Database path: {db_path}")
        print(f"Total features: {total_features}")
        print(f"MIN(time_server): {min_time}")
        print(f"MAX(time_server): {max_time}")
        print_group_counts(connection)
        print_null_counts(connection)
        print("Basic statistics:")
        print_basic_stats(connection, "return_1")
        print_basic_stats(connection, "volatility_20")
        if "volatility_100" in table_columns(connection):
            print_basic_stats(connection, "volatility_100")
        print_basic_stats(connection, "spread_avg_20")
        print_atr_feature_stats(connection)
        print_volume_feature_stats(connection)


def main() -> int:
    try:
        check_price_features()
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(f"Price features check failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
