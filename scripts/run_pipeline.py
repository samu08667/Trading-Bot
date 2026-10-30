import argparse
import shutil
import sqlite3
from pathlib import Path

from import_calendar_csv import import_calendar_csv
from init_database import init_database


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_MODELS_DIR = BASE_DIR / "models"
DEFAULT_LOGS_DIR = BASE_DIR / "logs"
DEFAULT_CSV_PATH = DEFAULT_DATA_DIR / "economic_calendar.csv"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "trading_bot.db"


def create_required_folders() -> list[Path]:
    folders = [DEFAULT_DATA_DIR, DEFAULT_MODELS_DIR, DEFAULT_LOGS_DIR]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
    return folders


def copy_csv_source(csv_source: Path, csv_path: Path) -> None:
    if not csv_source.exists():
        raise FileNotFoundError(f"CSV source not found: {csv_source}")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(csv_source, csv_path)


def missing_csv_message(csv_path: Path) -> str:
    return (
        f"CSV file not found: {csv_path}\n"
        "To import economic calendar data, either:\n"
        "1. run the MQL5 export script in MetaTrader 5 and copy the CSV into "
        "data/economic_calendar.csv; or\n"
        "2. pass --csv-source with the path to the MT5 MQL5/Files CSV."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare repository-side trading bot data from an exported MT5 economic calendar CSV."
    )
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH, help="CSV import path.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--csv-source", type=Path, help="Optional external CSV path to copy before import.")
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Create required folders and initialize the database only. Do not import CSV data.",
    )
    parser.add_argument(
        "--import-only",
        action="store_true",
        help="Import CSV data only. Assume the database and economic_events table already exist.",
    )
    args = parser.parse_args()

    if args.init_only and args.import_only:
        parser.error("--init-only and --import-only cannot be used together.")

    return args


def print_report(
    *,
    folders: list[Path],
    db_path: Path,
    csv_path: Path,
    csv_source: Path | None,
    csv_copied: bool,
    rows_read: int,
    rows_inserted: int,
    rows_skipped: int,
    status: str,
) -> None:
    print("Pipeline report")
    print("Folders checked or created:")
    for folder in folders:
        print(f"- {folder}")
    print(f"Database path: {db_path}")
    print(f"CSV path: {csv_path}")
    if csv_source is None:
        print("CSV copied from --csv-source: no")
    else:
        copied_text = "yes" if csv_copied else "no"
        print(f"CSV copied from --csv-source: {copied_text} ({csv_source})")
    print(f"Rows read: {rows_read}")
    print(f"Rows inserted: {rows_inserted}")
    print(f"Rows skipped: {rows_skipped}")
    print(f"Final status: {status}")


def main() -> int:
    args = parse_args()
    folders = create_required_folders()
    csv_copied = False
    rows_read = 0
    rows_inserted = 0
    rows_skipped = 0

    try:
        if args.csv_source is not None and not args.init_only:
            copy_csv_source(args.csv_source, args.csv_path)
            csv_copied = True

        if not args.import_only:
            init_database(args.db_path)

        if not args.init_only:
            if not args.csv_path.exists():
                print(missing_csv_message(args.csv_path))
                print_report(
                    folders=folders,
                    db_path=args.db_path,
                    csv_path=args.csv_path,
                    csv_source=args.csv_source,
                    csv_copied=csv_copied,
                    rows_read=rows_read,
                    rows_inserted=rows_inserted,
                    rows_skipped=rows_skipped,
                    status="failed",
                )
                return 1

            result = import_calendar_csv(args.csv_path, args.db_path)
            rows_read = result["rows_read"]
            rows_inserted = result["rows_inserted"]
            rows_skipped = result["rows_skipped"]

    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"Pipeline failed: {exc}")
        print_report(
            folders=folders,
            db_path=args.db_path,
            csv_path=args.csv_path,
            csv_source=args.csv_source,
            csv_copied=csv_copied,
            rows_read=rows_read,
            rows_inserted=rows_inserted,
            rows_skipped=rows_skipped,
            status="failed",
        )
        return 1

    print_report(
        folders=folders,
        db_path=args.db_path,
        csv_path=args.csv_path,
        csv_source=args.csv_source,
        csv_copied=csv_copied,
        rows_read=rows_read,
        rows_inserted=rows_inserted,
        rows_skipped=rows_skipped,
        status="success",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
