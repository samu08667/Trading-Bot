from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
TABLE_NAME = "economic_events"


def table_exists(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    )
    return cursor.fetchone() is not None


def scalar(connection: sqlite3.Connection, query: str) -> int | str | None:
    return connection.execute(query).fetchone()[0]


def print_group_counts(connection: sqlite3.Connection, column: str) -> None:
    print(f"Events by {column}:")
    rows = connection.execute(
        f"""
        SELECT
            COALESCE(NULLIF(TRIM(CAST({column} AS TEXT)), ''), '(empty)') AS value,
            COUNT(*) AS total
        FROM {TABLE_NAME}
        GROUP BY value
        ORDER BY total DESC, value ASC
        """
    ).fetchall()

    if not rows:
        print("- none: 0")
        return

    for value, total in rows:
        print(f"- {value}: {total}")


def check_database(db_path: Path = DATABASE_PATH) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        if not table_exists(connection):
            raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")

        total_events = scalar(connection, f"SELECT COUNT(*) FROM {TABLE_NAME}")
        min_time = scalar(connection, f"SELECT MIN(time_server) FROM {TABLE_NAME}")
        max_time = scalar(connection, f"SELECT MAX(time_server) FROM {TABLE_NAME}")
        duplicate_value_ids = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT value_id
                FROM {TABLE_NAME}
                WHERE value_id IS NOT NULL
                GROUP BY value_id
                HAVING COUNT(*) > 1
            )
            """,
        )
        missing_time_server = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            WHERE time_server IS NULL OR TRIM(time_server) = ''
            """,
        )
        missing_currency = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            WHERE currency IS NULL OR TRIM(currency) = ''
            """,
        )

        print("Economic events database check")
        print(f"Database path: {db_path}")
        print(f"Total events: {total_events}")
        print(f"MIN(time_server): {min_time}")
        print(f"MAX(time_server): {max_time}")
        print_group_counts(connection, "currency")
        print_group_counts(connection, "importance")
        print(f"Duplicate value_id count: {duplicate_value_ids}")
        print(f"Rows with time_server NULL or empty: {missing_time_server}")
        print(f"Rows with currency NULL or empty: {missing_currency}")


def main() -> int:
    try:
        check_database()
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(f"Database check failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
