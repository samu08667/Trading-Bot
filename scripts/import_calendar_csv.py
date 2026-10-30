import argparse
import csv
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "economic_calendar.csv"
DATABASE_PATH = DATA_DIR / "trading_bot.db"
TABLE_NAME = "economic_events"
CSV_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")

REQUIRED_COLUMNS = [
    "value_id",
    "event_id",
    "time_server",
    "currency",
    "event_name",
    "event_code",
    "importance",
    "impact_type",
    "actual",
    "forecast",
    "previous",
    "revised_previous",
    "period",
    "revision",
]


def empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()
    return value if value else None


def detect_encoding(csv_path: Path) -> str:
    for encoding in CSV_ENCODINGS:
        try:
            with csv_path.open("r", newline="", encoding=encoding) as csv_file:
                csv_file.read()
            print(f"CSV encoding used: {encoding}")
            return encoding
        except UnicodeDecodeError:
            continue

    encodings = ", ".join(CSV_ENCODINGS)
    raise UnicodeDecodeError(
        "csv",
        b"",
        0,
        1,
        f"Could not decode CSV with any supported encoding: {encodings}",
    )


def detect_delimiter(csv_path: Path, encoding: str) -> str:
    with csv_path.open("r", newline="", encoding=encoding) as csv_file:
        sample = csv_file.read(4096)

    if not sample.strip():
        return ","

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        if dialect.delimiter in {",", ";"}:
            return dialect.delimiter
    except csv.Error:
        pass

    return ","


def row_is_empty(row: dict[str, str | list[str] | None]) -> bool:
    for value in row.values():
        if isinstance(value, list):
            if any(part and part.strip() for part in value):
                return False
        elif value is not None and value.strip():
            return False

    return True


def validate_csv_header(fieldnames: list[str] | None, delimiter: str) -> None:
    detected_columns = fieldnames or []
    missing_columns = [name for name in REQUIRED_COLUMNS if name not in detected_columns]
    if not missing_columns:
        return

    print("CSV file is missing required columns.")
    print("Required columns:")
    for column in REQUIRED_COLUMNS:
        print(f"- {column}")
    print("Detected columns:")
    for column in detected_columns:
        print(f"- {column}")
    print(f"Detected delimiter: {delimiter!r}")
    print("Hint: the CSV header or delimiter may be wrong.")
    raise ValueError("CSV file is missing required columns.")


def ensure_table_exists(connection: sqlite3.Connection) -> None:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    )
    if cursor.fetchone() is None:
        raise sqlite3.OperationalError(
            f"Table {TABLE_NAME!r} does not exist. Run python scripts/init_database.py first."
        )


def import_calendar_csv(csv_path: Path, db_path: Path) -> dict[str, int]:
    csv_path = Path(csv_path)
    db_path = Path(db_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}. Run this command first: python scripts/init_database.py"
        )

    encoding = detect_encoding(csv_path)
    delimiter = detect_delimiter(csv_path, encoding)
    rows_read = 0
    rows_inserted = 0
    rows_skipped = 0

    insert_sql = f"""
        INSERT OR IGNORE INTO {TABLE_NAME} (
            value_id,
            event_id,
            time_server,
            currency,
            event_name,
            event_code,
            importance,
            impact_type,
            actual,
            forecast,
            previous,
            revised_previous,
            period,
            revision
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    with sqlite3.connect(db_path) as connection:
        ensure_table_exists(connection)

        with csv_path.open("r", newline="", encoding=encoding) as csv_file:
            reader = csv.DictReader(csv_file, delimiter=delimiter, restkey="_extra_fields", restval=None)

            if reader.fieldnames is None:
                print(f"CSV file is empty: {csv_path}")
                return {"rows_read": 0, "rows_inserted": 0, "rows_skipped": 0}

            validate_csv_header(reader.fieldnames, delimiter)

            for row in reader:
                if row_is_empty(row):
                    continue

                rows_read += 1
                if not empty_to_none(row.get("value_id")):
                    rows_skipped += 1
                    print("Skipping row with missing value_id.")
                    continue

                before_count = connection.total_changes
                try:
                    connection.execute(
                        insert_sql,
                        tuple(empty_to_none(row.get(column)) for column in REQUIRED_COLUMNS),
                    )
                except sqlite3.Error as exc:
                    rows_skipped += 1
                    print(f"Skipping row with value_id={row.get('value_id')!r}: {exc}")
                    continue

                if connection.total_changes > before_count:
                    rows_inserted += 1
                else:
                    rows_skipped += 1

        connection.commit()

    return {
        "rows_read": rows_read,
        "rows_inserted": rows_inserted,
        "rows_skipped": rows_skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import an exported MetaTrader 5 economic calendar CSV into SQLite."
    )
    parser.add_argument("--csv-path", type=Path, default=CSV_PATH, help=f"CSV path. Default: {CSV_PATH}")
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Database path. Default: {DATABASE_PATH}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        result = import_calendar_csv(args.csv_path, args.db_path)
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"Import failed: {exc}")
        return 1

    print("Economic calendar import complete.")
    print(f"Rows read: {result['rows_read']}")
    print(f"Rows inserted: {result['rows_inserted']}")
    print(f"Rows skipped: {result['rows_skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
