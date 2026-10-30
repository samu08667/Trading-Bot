import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
TABLE_NAME = "price_bars"
SUPPORTED_TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}


def parse_utc_datetime(value: str) -> datetime:
    raw_value = value.strip()
    if raw_value.endswith("Z"):
        raw_value = raw_value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid datetime {value!r}. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    return parsed


def format_time_server(timestamp: int) -> str:
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def resolve_timeframe(mt5_module, timeframe: str) -> int:
    constant_name = f"TIMEFRAME_{timeframe.upper()}"
    try:
        return getattr(mt5_module, constant_name)
    except AttributeError as exc:
        raise ValueError(f"Unsupported MetaTrader 5 timeframe: {timeframe}") from exc


def ensure_table_exists(connection: sqlite3.Connection) -> None:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    )
    if cursor.fetchone() is None:
        raise sqlite3.OperationalError(
            f"Table {TABLE_NAME!r} does not exist. Run python scripts/init_database.py first."
        )


def ensure_symbol_available(mt5_module, symbol: str) -> None:
    symbol_info = mt5_module.symbol_info(symbol)
    if symbol_info is not None and getattr(symbol_info, "visible", False):
        return

    if not mt5_module.symbol_select(symbol, True):
        error = mt5_module.last_error()
        raise RuntimeError(f"Symbol {symbol!r} is not available. last_error={error}")


def import_price_bars(
    *,
    symbol: str,
    timeframe: str,
    from_date: datetime,
    to_date: datetime,
    db_path: Path,
) -> dict[str, int]:
    if to_date < from_date:
        raise ValueError("--to-date must be greater than or equal to --from-date.")

    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 Python package is required to import price bars.") from exc

    if not mt5.initialize():
        error = mt5.last_error()
        raise RuntimeError(f"MetaTrader 5 initialize failed. last_error={error}")

    try:
        ensure_symbol_available(mt5, symbol)
        timeframe_value = resolve_timeframe(mt5, timeframe)
        rates = mt5.copy_rates_range(symbol, timeframe_value, from_date, to_date)
        if rates is None:
            error = mt5.last_error()
            raise RuntimeError(f"copy_rates_range failed for {symbol} {timeframe}. last_error={error}")
    finally:
        mt5.shutdown()

    rows_downloaded = len(rates)
    rows_inserted = 0
    rows_skipped = 0

    insert_sql = f"""
        INSERT OR IGNORE INTO {TABLE_NAME} (
            symbol,
            timeframe,
            time_server,
            open,
            high,
            low,
            close,
            tick_volume,
            spread,
            real_volume,
            source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MT5')
    """

    with sqlite3.connect(db_path) as connection:
        ensure_table_exists(connection)

        for rate in rates:
            before_count = connection.total_changes
            connection.execute(
                insert_sql,
                (
                    symbol,
                    timeframe,
                    format_time_server(rate["time"]),
                    float(rate["open"]),
                    float(rate["high"]),
                    float(rate["low"]),
                    float(rate["close"]),
                    int(rate["tick_volume"]),
                    int(rate["spread"]),
                    int(rate["real_volume"]),
                ),
            )
            if connection.total_changes > before_count:
                rows_inserted += 1
            else:
                rows_skipped += 1

        connection.commit()

    return {
        "rows_downloaded": rows_downloaded,
        "rows_inserted": rows_inserted,
        "rows_skipped": rows_skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import read-only historical OHLCV price bars from MetaTrader 5 into SQLite."
    )
    parser.add_argument("--symbol", required=True, help="MetaTrader 5 symbol, for example EURUSD.")
    parser.add_argument("--timeframe", required=True, choices=sorted(SUPPORTED_TIMEFRAMES))
    parser.add_argument("--from-date", required=True, type=parse_utc_datetime)
    parser.add_argument("--to-date", required=True, type=parse_utc_datetime)
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        result = import_price_bars(
            symbol=args.symbol.strip().upper(),
            timeframe=args.timeframe.upper(),
            from_date=args.from_date,
            to_date=args.to_date,
            db_path=args.db_path,
        )
    except (RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"Price bars import failed: {exc}")
        return 1

    print("Price bars import complete.")
    print(f"Symbol: {args.symbol.strip().upper()}")
    print(f"Timeframe: {args.timeframe.upper()}")
    print(f"From date: {args.from_date.isoformat()}")
    print(f"To date: {args.to_date.isoformat()}")
    print(f"Rows downloaded: {result['rows_downloaded']}")
    print(f"Rows inserted: {result['rows_inserted']}")
    print(f"Rows skipped: {result['rows_skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
