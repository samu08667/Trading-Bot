import argparse
from pathlib import Path
import sqlite3

try:
    from regime_classification import (
        REGIME_CLASSIFICATION_COLUMNS,
        REGIME_CLASSIFICATION_SOURCE_COLUMNS,
    )
    from target_families import (
        barrier_bars_column,
        barrier_hit_first_column,
        triple_barrier_column,
        triple_barrier_multiplier_specs,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.regime_classification import (
        REGIME_CLASSIFICATION_COLUMNS,
        REGIME_CLASSIFICATION_SOURCE_COLUMNS,
    )
    from scripts.target_families import (
        barrier_bars_column,
        barrier_hit_first_column,
        triple_barrier_column,
        triple_barrier_multiplier_specs,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
TABLE_NAME = "ml_dataset"
HORIZONS = (5, 10, 20)
TRIPLE_BARRIER_DIRECTIONS = ("long", "short")
TRIPLE_BARRIER_SPECS = triple_barrier_multiplier_specs()
TARGET_COLUMNS = [
    "future_return_5",
    "future_return_10",
    "future_return_20",
    *[
        column
        for horizon in HORIZONS
        for column in (
            f"future_max_return_{horizon}",
            f"future_min_return_{horizon}",
            f"future_range_{horizon}",
            f"long_mfe_{horizon}",
            f"long_mae_{horizon}",
            f"short_mfe_{horizon}",
            f"short_mae_{horizon}",
            f"target_long_good_{horizon}",
            f"target_short_good_{horizon}",
        )
    ],
    *[
        column
        for horizon in HORIZONS
        for direction in TRIPLE_BARRIER_DIRECTIONS
        for tp_atr, sl_atr in TRIPLE_BARRIER_SPECS
        for column in (
            barrier_hit_first_column(direction, tp_atr, sl_atr, horizon),
            triple_barrier_column(direction, tp_atr, sl_atr, horizon),
            barrier_bars_column(direction, tp_atr, sl_atr, horizon),
        )
    ],
    "target_up_5",
    "target_up_10",
    "target_up_20",
    "target_down_5",
    "target_down_10",
    "target_down_20",
]
FUTURE_LABEL_STAT_COLUMNS = [
    "future_return_5",
    "future_return_10",
    "future_return_20",
    "future_max_return_5",
    "future_max_return_10",
    "future_max_return_20",
    "future_min_return_5",
    "future_min_return_10",
    "future_min_return_20",
    "future_range_5",
    "future_range_10",
    "future_range_20",
    "long_mfe_5",
    "long_mfe_10",
    "long_mfe_20",
    "long_mae_5",
    "long_mae_10",
    "long_mae_20",
    "short_mfe_5",
    "short_mfe_10",
    "short_mfe_20",
    "short_mae_5",
    "short_mae_10",
    "short_mae_20",
]
TRIPLE_BARRIER_DISTRIBUTION_COLUMNS = [
    column
    for horizon in HORIZONS
    for direction in TRIPLE_BARRIER_DIRECTIONS
    for tp_atr, sl_atr in TRIPLE_BARRIER_SPECS
    for column in (
        barrier_hit_first_column(direction, tp_atr, sl_atr, horizon),
        triple_barrier_column(direction, tp_atr, sl_atr, horizon),
    )
]
VOLUME_FEATURE_COLUMNS = [
    "spread_price",
    "spread_return",
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


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


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
            MAX(time_server) AS max_time_server
        FROM {TABLE_NAME}
        GROUP BY symbol, timeframe
        ORDER BY symbol ASC, timeframe ASC
        """
    ).fetchall()

    print("ML dataset by symbol/timeframe:")
    if not rows:
        print("- none: 0")
        return

    for symbol, timeframe, total, min_time, max_time in rows:
        print(
            f"- {symbol} {timeframe}: {total} rows, "
            f"MIN(time_server)={min_time}, MAX(time_server)={max_time}"
        )


def print_null_targets(connection: sqlite3.Connection) -> None:
    null_checks = " OR ".join(f"{column} IS NULL" for column in TARGET_COLUMNS)
    any_null_count = scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {TABLE_NAME}
        WHERE {null_checks}
        """,
    )

    print(f"Rows with any NULL target: {any_null_count}")
    print("NULL target counts:")
    for column in TARGET_COLUMNS:
        count = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            WHERE {column} IS NULL
            """,
        )
        print(f"- {column}: {count}")


def print_target_distribution(connection: sqlite3.Connection, column: str) -> None:
    rows = connection.execute(
        f"""
        SELECT
            COALESCE(CAST({column} AS TEXT), 'NULL') AS value,
            COUNT(*) AS total
        FROM {TABLE_NAME}
        GROUP BY value
        ORDER BY value ASC
        """
    ).fetchall()

    print(f"{column} distribution:")
    if not rows:
        print("- none: 0")
        return

    for value, total in rows:
        print(f"- {value}: {total}")


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
    avg_text = "NULL" if avg_value is None else f"{avg_value:.10f}"
    print(
        f"{column}: count={non_null_count}, "
        f"min={min_value}, avg={avg_text}, max={max_value}"
    )


def print_regime_classification_status(connection: sqlite3.Connection, available_columns: set[str]) -> None:
    total_rows = scalar(connection, f"SELECT COUNT(*) FROM {TABLE_NAME}") or 0
    print("Regime classification columns:")
    for column in REGIME_CLASSIFICATION_COLUMNS:
        if column not in available_columns:
            print(f"- {column}: missing")
            continue
        quoted = quote_identifier(column)
        non_null = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            WHERE {quoted} IS NOT NULL
              AND TRIM(CAST({quoted} AS TEXT)) != ''
            """,
        )
        distinct_values = scalar(
            connection,
            f"""
            SELECT COUNT(DISTINCT {quoted})
            FROM {TABLE_NAME}
            WHERE {quoted} IS NOT NULL
              AND TRIM(CAST({quoted} AS TEXT)) != ''
            """,
        )
        print(
            f"- {column}: present, non_null={int(non_null or 0)}/{int(total_rows)}, "
            f"distinct_non_null={int(distinct_values or 0)}"
        )

    print("Regime classification source availability:")
    for regime_column, source_columns in REGIME_CLASSIFICATION_SOURCE_COLUMNS.items():
        present = [column for column in source_columns if column in available_columns]
        if present:
            print(f"- {regime_column}: present sources={','.join(present)}")
        else:
            print(f"- {regime_column}: missing any of {','.join(source_columns)}")


def safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def positive_rate_flag(positive_rate: float | None) -> str:
    if positive_rate is None:
        return "missing"
    if positive_rate < 0.10:
        return "below_initial_range"
    if positive_rate > 0.50:
        return "above_initial_range"
    return "within_initial_range"


def print_hit_first_target_diagnostics(
    connection: sqlite3.Connection,
    *,
    tp_atr: float,
    sl_atr: float,
) -> None:
    available_columns = table_columns(connection)
    groups = connection.execute(
        f"""
        SELECT symbol, timeframe, COUNT(*) AS total_rows
        FROM {TABLE_NAME}
        GROUP BY symbol, timeframe
        ORDER BY symbol ASC, timeframe ASC
        """
    ).fetchall()
    print(f"Hit-first target diagnostics TP={tp_atr:g}ATR SL={sl_atr:g}ATR:")
    if not groups:
        print("- none: 0")
        return
    for symbol, timeframe, total_rows in groups:
        for direction in TRIPLE_BARRIER_DIRECTIONS:
            for horizon in HORIZONS:
                column = barrier_hit_first_column(direction, tp_atr, sl_atr, horizon)
                exists = column in available_columns
                if exists:
                    quoted = '"' + column.replace('"', '""') + '"'
                    valid, positives = connection.execute(
                        f"""
                        SELECT
                            SUM(CASE WHEN {quoted} IS NOT NULL THEN 1 ELSE 0 END),
                            SUM(CASE WHEN {quoted} = 1 THEN 1 ELSE 0 END)
                        FROM {TABLE_NAME}
                        WHERE symbol = ? AND timeframe = ?
                        """,
                        (symbol, timeframe),
                    ).fetchone()
                    valid_rows = int(valid or 0)
                    positive_count = int(positives or 0)
                else:
                    valid_rows = 0
                    positive_count = 0
                total = int(total_rows or 0)
                null_count = max(total - valid_rows, 0)
                negative_count = max(valid_rows - positive_count, 0)
                positive_rate = safe_ratio(positive_count, valid_rows)
                null_rate = safe_ratio(null_count, total)
                print(
                    "- {symbol} {timeframe} {direction} h{horizon} {column}: "
                    "exists={exists}, total_rows={total}, valid_rows={valid}, "
                    "null_count={nulls}, null_rate={null_rate}, positives={positives}, "
                    "negatives={negatives}, positive_rate={positive_rate}, flag={flag}".format(
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=direction,
                        horizon=horizon,
                        column=column,
                        exists=str(exists).lower(),
                        total=total,
                        valid=valid_rows,
                        nulls=null_count,
                        null_rate=null_rate,
                        positives=positive_count,
                        negatives=negative_count,
                        positive_rate=positive_rate,
                        flag=positive_rate_flag(positive_rate),
                    )
                )


def table_columns(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    return {str(row[1]) for row in rows}


def check_ml_dataset(db_path: Path = DATABASE_PATH, *, regime_schema_only: bool = False) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        if not table_exists(connection):
            raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")

        total_rows = scalar(connection, f"SELECT COUNT(*) FROM {TABLE_NAME}")
        min_time = scalar(connection, f"SELECT MIN(time_server) FROM {TABLE_NAME}")
        max_time = scalar(connection, f"SELECT MAX(time_server) FROM {TABLE_NAME}")

        print("ML dataset check")
        print(f"Database path: {db_path}")
        print(f"Total rows: {total_rows}")
        print(f"MIN(time_server): {min_time}")
        print(f"MAX(time_server): {max_time}")
        available_columns = table_columns(connection)
        if regime_schema_only:
            print_regime_classification_status(connection, available_columns)
            return
        print_group_counts(connection)
        print_null_targets(connection)
        print_target_distribution(connection, "target_up_10")
        print_target_distribution(connection, "target_down_10")
        print_target_distribution(connection, "target_long_good_10")
        print_target_distribution(connection, "target_short_good_10")
        for column in TRIPLE_BARRIER_DISTRIBUTION_COLUMNS:
            if column in available_columns:
                print_target_distribution(connection, column)
        print_hit_first_target_diagnostics(connection, tp_atr=1.5, sl_atr=1.0)
        print("Future label statistics:")
        for column in FUTURE_LABEL_STAT_COLUMNS:
            if column in available_columns:
                print_basic_stats(connection, column)
        print("Volume/liquidity feature statistics:")
        for column in VOLUME_FEATURE_COLUMNS:
            if column in available_columns:
                print_basic_stats(connection, column)
        print_regime_classification_status(connection, available_columns)
        print("Regime classification distributions:")
        for column in REGIME_CLASSIFICATION_COLUMNS:
            if column in available_columns:
                print_target_distribution(connection, column)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print lightweight diagnostics for ml_dataset.")
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    parser.add_argument(
        "--regime-schema-only",
        action="store_true",
        help="Only report regime column presence, non-null counts, and source-column availability.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        check_ml_dataset(args.db_path, regime_schema_only=bool(args.regime_schema_only))
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(f"ML dataset check failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
