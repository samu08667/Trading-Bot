from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
TABLE_NAME = "price_bars"


def table_exists(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    )
    return cursor.fetchone() is not None


def scalar(connection: sqlite3.Connection, query: str) -> int | float | str | None:
    return connection.execute(query).fetchone()[0]


def check_price_bars(db_path: Path = DATABASE_PATH) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        if not table_exists(connection):
            raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")

        total_bars = scalar(connection, f"SELECT COUNT(*) FROM {TABLE_NAME}")
        duplicate_bars = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT symbol, timeframe, time_server
                FROM {TABLE_NAME}
                GROUP BY symbol, timeframe, time_server
                HAVING COUNT(*) > 1
            )
            """,
        )
        missing_ohlc = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            WHERE open IS NULL
               OR high IS NULL
               OR low IS NULL
               OR close IS NULL
            """
        )
        groups = connection.execute(
            f"""
            SELECT
                symbol,
                timeframe,
                COUNT(*) AS total,
                MIN(time_server) AS min_time_server,
                MAX(time_server) AS max_time_server,
                AVG(spread) AS avg_spread,
                MIN(spread) AS min_spread,
                MAX(spread) AS max_spread
            FROM {TABLE_NAME}
            GROUP BY symbol, timeframe
            ORDER BY symbol ASC, timeframe ASC
            """
        ).fetchall()

        print("Price bars database check")
        print(f"Database path: {db_path}")
        print(f"Total bars: {total_bars}")
        print("Bars by symbol/timeframe:")
        if not groups:
            print("- none: 0")
        else:
            for (
                symbol,
                timeframe,
                total,
                min_time_server,
                max_time_server,
                avg_spread,
                min_spread,
                max_spread,
            ) in groups:
                if avg_spread is None:
                    avg_spread_text = "NULL"
                else:
                    avg_spread_text = f"{avg_spread:.2f}"

                print(
                    f"- {symbol} {timeframe}: {total} bars, "
                    f"MIN(time_server)={min_time_server}, "
                    f"MAX(time_server)={max_time_server}, "
                    f"spread avg/min/max={avg_spread_text}/{min_spread}/{max_spread}"
                )

        print(f"Duplicate symbol/timeframe/time_server count: {duplicate_bars}")
        print(f"Rows with missing OHLC: {missing_ohlc}")


def main() -> int:
    try:
        check_price_bars()
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(f"Price bars check failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
