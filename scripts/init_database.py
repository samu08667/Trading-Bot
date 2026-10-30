from pathlib import Path
import sqlite3

try:
    from target_families import (
        barrier_bars_column,
        barrier_hit_first_column,
        triple_barrier_column,
        triple_barrier_label_specs,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.target_families import (
        barrier_bars_column,
        barrier_hit_first_column,
        triple_barrier_column,
        triple_barrier_label_specs,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "trading_bot.db"
TABLE_NAME = "economic_events"
PRICE_BARS_TABLE_NAME = "price_bars"
PRICE_FEATURES_TABLE_NAME = "price_features"
MARKET_FEATURES_TABLE_NAME = "market_features"
ML_DATASET_TABLE_NAME = "ml_dataset"

VOLUME_FEATURE_COLUMNS = {
    "tick_volume_ratio_20": "REAL",
    "tick_volume_zscore_100": "REAL",
    "tick_volume_percentile_100": "REAL",
    "volume_spike_20": "INTEGER",
    "volume_dry_up_20": "INTEGER",
    "spread_to_volume_ratio": "REAL",
    "volume_vs_hour_avg": "REAL",
    "volume_vs_session_avg": "REAL",
    "hour_session": "TEXT",
}

REGIME_CLASSIFICATION_COLUMNS = {
    "session": "TEXT",
    "spread_liquidity_regime": "TEXT",
    "volatility_regime": "TEXT",
    "range_regime": "TEXT",
    "volume_liquidity_regime": "TEXT",
}

PRICE_CONTEXT_FEATURE_COLUMNS = {
    "true_range": "REAL",
    "atr_14": "REAL",
    "atr_20": "REAL",
    "atr_50": "REAL",
    "range_to_atr_20": "REAL",
    "body_to_atr_20": "REAL",
    "upper_wick_to_atr_20": "REAL",
    "lower_wick_to_atr_20": "REAL",
    "close_to_ma_fast_atr_20": "REAL",
    "close_to_ma_slow_atr_20": "REAL",
    "ma_diff_atr_20": "REAL",
    "volatility_100": "REAL",
    "volatility_ratio_20_100": "REAL",
    "spread_price": "REAL",
    "spread_return": "REAL",
    "spread_to_atr_20": "REAL",
}

PRICE_FEATURE_EXTENSION_COLUMNS = {
    **PRICE_CONTEXT_FEATURE_COLUMNS,
    **VOLUME_FEATURE_COLUMNS,
    **REGIME_CLASSIFICATION_COLUMNS,
}

ML_FUTURE_LABEL_COLUMNS = {}
for _horizon in (5, 10, 20):
    ML_FUTURE_LABEL_COLUMNS.update(
        {
            f"future_max_return_{_horizon}": "REAL",
            f"future_min_return_{_horizon}": "REAL",
            f"future_range_{_horizon}": "REAL",
            f"long_mfe_{_horizon}": "REAL",
            f"long_mae_{_horizon}": "REAL",
            f"short_mfe_{_horizon}": "REAL",
            f"short_mae_{_horizon}": "REAL",
            f"target_long_good_{_horizon}": "INTEGER",
            f"target_short_good_{_horizon}": "INTEGER",
        }
    )

ML_TRIPLE_BARRIER_LABEL_COLUMNS = {}
for _horizon in (5, 10, 20):
    for _direction, _tp_atr, _sl_atr in triple_barrier_label_specs():
        ML_TRIPLE_BARRIER_LABEL_COLUMNS.update(
            {
                barrier_hit_first_column(_direction, _tp_atr, _sl_atr, _horizon): "INTEGER",
                barrier_bars_column(_direction, _tp_atr, _sl_atr, _horizon): "INTEGER",
                triple_barrier_column(_direction, _tp_atr, _sl_atr, _horizon): "INTEGER",
            }
        )

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    value_id INTEGER UNIQUE,
    event_id INTEGER,
    time_server TEXT,
    currency TEXT,
    event_name TEXT,
    event_code TEXT,
    importance INTEGER,
    impact_type INTEGER,
    actual REAL,
    forecast REAL,
    previous REAL,
    revised_previous REAL,
    period TEXT,
    revision INTEGER,
    source TEXT DEFAULT 'MT5',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_PRICE_BARS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PRICE_BARS_TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    time_server TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    tick_volume INTEGER,
    spread INTEGER,
    real_volume INTEGER,
    source TEXT DEFAULT 'MT5',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timeframe, time_server)
)
"""

CREATE_PRICE_FEATURES_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PRICE_FEATURES_TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    time_server TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    tick_volume INTEGER,
    spread INTEGER,
    return_1 REAL,
    return_5 REAL,
    return_20 REAL,
    candle_range REAL,
    body_size REAL,
    upper_wick REAL,
    lower_wick REAL,
    true_range REAL,
    atr_14 REAL,
    atr_20 REAL,
    atr_50 REAL,
    range_to_atr_20 REAL,
    body_to_atr_20 REAL,
    upper_wick_to_atr_20 REAL,
    lower_wick_to_atr_20 REAL,
    volatility_20 REAL,
    volatility_100 REAL,
    volatility_ratio_20_100 REAL,
    ma_fast REAL,
    ma_slow REAL,
    ma_diff REAL,
    close_to_ma_fast_atr_20 REAL,
    close_to_ma_slow_atr_20 REAL,
    ma_diff_atr_20 REAL,
    spread_avg_20 REAL,
    spread_price REAL,
    spread_return REAL,
    spread_to_atr_20 REAL,
    tick_volume_avg_20 REAL,
    tick_volume_ratio_20 REAL,
    tick_volume_zscore_100 REAL,
    tick_volume_percentile_100 REAL,
    volume_spike_20 INTEGER,
    volume_dry_up_20 INTEGER,
    spread_to_volume_ratio REAL,
    volume_vs_hour_avg REAL,
    volume_vs_session_avg REAL,
    session TEXT,
    spread_liquidity_regime TEXT,
    volatility_regime TEXT,
    range_regime TEXT,
    volume_liquidity_regime TEXT,
    hour_session TEXT,
    hour INTEGER,
    day_of_week INTEGER,
    source TEXT DEFAULT 'price_bars',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timeframe, time_server)
)
"""

CREATE_MARKET_FEATURES_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {MARKET_FEATURES_TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    time_server TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    tick_volume INTEGER,
    spread INTEGER,
    return_1 REAL,
    return_5 REAL,
    return_20 REAL,
    candle_range REAL,
    body_size REAL,
    upper_wick REAL,
    lower_wick REAL,
    true_range REAL,
    atr_14 REAL,
    atr_20 REAL,
    atr_50 REAL,
    range_to_atr_20 REAL,
    body_to_atr_20 REAL,
    upper_wick_to_atr_20 REAL,
    lower_wick_to_atr_20 REAL,
    volatility_20 REAL,
    volatility_100 REAL,
    volatility_ratio_20_100 REAL,
    ma_fast REAL,
    ma_slow REAL,
    ma_diff REAL,
    close_to_ma_fast_atr_20 REAL,
    close_to_ma_slow_atr_20 REAL,
    ma_diff_atr_20 REAL,
    spread_avg_20 REAL,
    spread_price REAL,
    spread_return REAL,
    spread_to_atr_20 REAL,
    tick_volume_avg_20 REAL,
    tick_volume_ratio_20 REAL,
    tick_volume_zscore_100 REAL,
    tick_volume_percentile_100 REAL,
    volume_spike_20 INTEGER,
    volume_dry_up_20 INTEGER,
    spread_to_volume_ratio REAL,
    volume_vs_hour_avg REAL,
    volume_vs_session_avg REAL,
    session TEXT,
    spread_liquidity_regime TEXT,
    volatility_regime TEXT,
    range_regime TEXT,
    volume_liquidity_regime TEXT,
    hour_session TEXT,
    hour INTEGER,
    day_of_week INTEGER,
    relevant_currencies TEXT,
    minutes_to_next_news REAL,
    minutes_from_last_news REAL,
    has_news_next_30m INTEGER,
    has_news_next_60m INTEGER,
    has_high_impact_news_next_30m INTEGER,
    has_high_impact_news_next_60m INTEGER,
    has_high_impact_news_prev_30m INTEGER,
    has_high_impact_news_prev_60m INTEGER,
    blackout_window_30m INTEGER,
    blackout_window_60m INTEGER,
    post_news_window_30m INTEGER,
    post_news_window_60m INTEGER,
    news_count_next_60m INTEGER,
    news_count_prev_60m INTEGER,
    max_importance_next_60m INTEGER,
    max_importance_prev_60m INTEGER,
    next_news_currency TEXT,
    next_news_importance INTEGER,
    last_news_currency TEXT,
    last_news_importance INTEGER,
    source TEXT DEFAULT 'price_features+economic_events',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timeframe, time_server)
)
"""

CREATE_ML_DATASET_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {ML_DATASET_TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    time_server TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    tick_volume INTEGER,
    spread INTEGER,
    return_1 REAL,
    return_5 REAL,
    return_20 REAL,
    candle_range REAL,
    body_size REAL,
    upper_wick REAL,
    lower_wick REAL,
    true_range REAL,
    atr_14 REAL,
    atr_20 REAL,
    atr_50 REAL,
    range_to_atr_20 REAL,
    body_to_atr_20 REAL,
    upper_wick_to_atr_20 REAL,
    lower_wick_to_atr_20 REAL,
    volatility_20 REAL,
    volatility_100 REAL,
    volatility_ratio_20_100 REAL,
    ma_fast REAL,
    ma_slow REAL,
    ma_diff REAL,
    close_to_ma_fast_atr_20 REAL,
    close_to_ma_slow_atr_20 REAL,
    ma_diff_atr_20 REAL,
    spread_avg_20 REAL,
    spread_price REAL,
    spread_return REAL,
    spread_to_atr_20 REAL,
    tick_volume_avg_20 REAL,
    tick_volume_ratio_20 REAL,
    tick_volume_zscore_100 REAL,
    tick_volume_percentile_100 REAL,
    volume_spike_20 INTEGER,
    volume_dry_up_20 INTEGER,
    spread_to_volume_ratio REAL,
    volume_vs_hour_avg REAL,
    volume_vs_session_avg REAL,
    session TEXT,
    spread_liquidity_regime TEXT,
    volatility_regime TEXT,
    range_regime TEXT,
    volume_liquidity_regime TEXT,
    hour_session TEXT,
    hour INTEGER,
    day_of_week INTEGER,
    relevant_currencies TEXT,
    minutes_to_next_news REAL,
    minutes_from_last_news REAL,
    has_news_next_30m INTEGER,
    has_news_next_60m INTEGER,
    has_high_impact_news_next_30m INTEGER,
    has_high_impact_news_next_60m INTEGER,
    has_high_impact_news_prev_30m INTEGER,
    has_high_impact_news_prev_60m INTEGER,
    blackout_window_30m INTEGER,
    blackout_window_60m INTEGER,
    post_news_window_30m INTEGER,
    post_news_window_60m INTEGER,
    news_count_next_60m INTEGER,
    news_count_prev_60m INTEGER,
    max_importance_next_60m INTEGER,
    max_importance_prev_60m INTEGER,
    next_news_currency TEXT,
    next_news_importance INTEGER,
    last_news_currency TEXT,
    last_news_importance INTEGER,
    future_return_5 REAL,
    future_return_10 REAL,
    future_return_20 REAL,
    future_max_return_5 REAL,
    future_min_return_5 REAL,
    future_range_5 REAL,
    long_mfe_5 REAL,
    long_mae_5 REAL,
    short_mfe_5 REAL,
    short_mae_5 REAL,
    target_long_good_5 INTEGER,
    target_short_good_5 INTEGER,
    future_max_return_10 REAL,
    future_min_return_10 REAL,
    future_range_10 REAL,
    long_mfe_10 REAL,
    long_mae_10 REAL,
    short_mfe_10 REAL,
    short_mae_10 REAL,
    target_long_good_10 INTEGER,
    target_short_good_10 INTEGER,
    long_tp_1atr_sl_1atr_hit_first_10 INTEGER,
    long_triple_barrier_1_1_10 INTEGER,
    long_tp_1atr_sl_1atr_bars_to_first_barrier_10 INTEGER,
    long_tp_1_5atr_sl_1atr_hit_first_10 INTEGER,
    long_triple_barrier_1_5_1_10 INTEGER,
    long_tp_1_5atr_sl_1atr_bars_to_first_barrier_10 INTEGER,
    long_tp_2atr_sl_1atr_hit_first_10 INTEGER,
    long_triple_barrier_2_1_10 INTEGER,
    long_tp_2atr_sl_1atr_bars_to_first_barrier_10 INTEGER,
    short_tp_1atr_sl_1atr_hit_first_10 INTEGER,
    short_triple_barrier_1_1_10 INTEGER,
    short_tp_1atr_sl_1atr_bars_to_first_barrier_10 INTEGER,
    short_tp_1_5atr_sl_1atr_hit_first_10 INTEGER,
    short_triple_barrier_1_5_1_10 INTEGER,
    short_tp_1_5atr_sl_1atr_bars_to_first_barrier_10 INTEGER,
    short_tp_2atr_sl_1atr_hit_first_10 INTEGER,
    short_triple_barrier_2_1_10 INTEGER,
    short_tp_2atr_sl_1atr_bars_to_first_barrier_10 INTEGER,
    future_max_return_20 REAL,
    future_min_return_20 REAL,
    future_range_20 REAL,
    long_mfe_20 REAL,
    long_mae_20 REAL,
    short_mfe_20 REAL,
    short_mae_20 REAL,
    target_long_good_20 INTEGER,
    target_short_good_20 INTEGER,
    target_up_5 INTEGER,
    target_up_10 INTEGER,
    target_up_20 INTEGER,
    target_down_5 INTEGER,
    target_down_10 INTEGER,
    target_down_20 INTEGER,
    source TEXT DEFAULT 'market_features',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timeframe, time_server)
)
"""

DESIRED_COLUMNS = [
    "id",
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
    "source",
    "created_at",
]

ALTERABLE_COLUMNS = {
    "id": "INTEGER",
    "value_id": "INTEGER",
    "event_id": "INTEGER",
    "time_server": "TEXT",
    "currency": "TEXT",
    "event_name": "TEXT",
    "event_code": "TEXT",
    "importance": "INTEGER",
    "impact_type": "INTEGER",
    "actual": "REAL",
    "forecast": "REAL",
    "previous": "REAL",
    "revised_previous": "REAL",
    "period": "TEXT",
    "revision": "INTEGER",
    "source": "TEXT DEFAULT 'MT5'",
    "created_at": "TEXT",
}


def init_database(db_path: Path) -> None:
    """Create or conservatively migrate the local SQLite data schema."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        if _table_exists(connection):
            _migrate_existing_table(connection)
        else:
            connection.execute(CREATE_TABLE_SQL)

        _create_indexes(connection)
        _ensure_price_bars_schema(connection)
        _ensure_price_features_schema(connection)
        _ensure_market_features_schema(connection)
        _ensure_ml_dataset_schema(connection)
        connection.commit()


def _table_exists(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    )
    return cursor.fetchone() is not None


def _get_columns(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    finally:
        connection.row_factory = None
    return {row["name"]: row for row in rows}


def _has_duplicate_value_ids(connection: sqlite3.Connection) -> bool:
    columns = _get_columns(connection)
    if "value_id" not in columns:
        return False

    duplicate = connection.execute(
        f"""
        SELECT value_id
        FROM {TABLE_NAME}
        WHERE value_id IS NOT NULL
        GROUP BY value_id
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    ).fetchone()
    return duplicate is not None


def _can_rebuild_safely(connection: sqlite3.Connection, columns: dict[str, sqlite3.Row]) -> bool:
    id_column = columns.get("id")
    has_autoincrement_id = (
        id_column is not None
        and int(id_column["pk"]) == 1
        and str(id_column["type"]).upper() == "INTEGER"
    )
    return not has_autoincrement_id and not _has_duplicate_value_ids(connection)


def _migrate_existing_table(connection: sqlite3.Connection) -> None:
    columns = _get_columns(connection)
    missing_columns = [name for name in DESIRED_COLUMNS if name not in columns]

    if _can_rebuild_safely(connection, columns):
        _rebuild_table_preserving_rows(connection, columns)
        return

    for column in missing_columns:
        connection.execute(
            f"ALTER TABLE {TABLE_NAME} ADD COLUMN {column} {ALTERABLE_COLUMNS[column]}"
        )

    if "source" in missing_columns:
        connection.execute(
            f"UPDATE {TABLE_NAME} SET source = 'MT5' WHERE source IS NULL OR source = ''"
        )

    if "value_id" in _get_columns(connection) and not _has_duplicate_value_ids(connection):
        connection.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_economic_events_value_id
            ON {TABLE_NAME} (value_id)
            """
        )


def _rebuild_table_preserving_rows(
    connection: sqlite3.Connection,
    existing_columns: dict[str, sqlite3.Row],
) -> None:
    old_table = f"{TABLE_NAME}_old_migration"
    old_count = connection.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]

    connection.execute(f"ALTER TABLE {TABLE_NAME} RENAME TO {old_table}")
    connection.execute(CREATE_TABLE_SQL)

    insert_columns = [name for name in DESIRED_COLUMNS if name != "id"]
    select_expressions = []
    for column in insert_columns:
        if column in existing_columns:
            select_expressions.append(column)
        elif column == "source":
            select_expressions.append("'MT5'")
        elif column == "created_at":
            select_expressions.append("CURRENT_TIMESTAMP")
        else:
            select_expressions.append("NULL")

    connection.execute(
        f"""
        INSERT INTO {TABLE_NAME} ({", ".join(insert_columns)})
        SELECT {", ".join(select_expressions)}
        FROM {old_table}
        """
    )

    new_count = connection.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
    if new_count != old_count:
        raise sqlite3.DatabaseError(
            f"Migration aborted: copied {new_count} rows but expected {old_count}."
        )

    connection.execute(f"DROP TABLE {old_table}")


def _create_indexes(connection: sqlite3.Connection) -> None:
    if not _has_duplicate_value_ids(connection):
        connection.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_economic_events_value_id
            ON {TABLE_NAME} (value_id)
            """
        )

    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_economic_events_time_server
        ON {TABLE_NAME} (time_server)
        """
    )
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_economic_events_currency
        ON {TABLE_NAME} (currency)
        """
    )


def _ensure_price_bars_schema(connection: sqlite3.Connection) -> None:
    connection.execute(CREATE_PRICE_BARS_TABLE_SQL)
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_price_bars_symbol_time
        ON {PRICE_BARS_TABLE_NAME} (symbol, timeframe, time_server)
        """
    )
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_price_bars_time
        ON {PRICE_BARS_TABLE_NAME} (time_server)
        """
    )


def _ensure_price_features_schema(connection: sqlite3.Connection) -> None:
    connection.execute(CREATE_PRICE_FEATURES_TABLE_SQL)
    _ensure_columns(connection, PRICE_FEATURES_TABLE_NAME, PRICE_FEATURE_EXTENSION_COLUMNS)
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_price_features_symbol_time
        ON {PRICE_FEATURES_TABLE_NAME} (symbol, timeframe, time_server)
        """
    )
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_price_features_time
        ON {PRICE_FEATURES_TABLE_NAME} (time_server)
        """
    )


def _ensure_market_features_schema(connection: sqlite3.Connection) -> None:
    connection.execute(CREATE_MARKET_FEATURES_TABLE_SQL)
    _ensure_columns(connection, MARKET_FEATURES_TABLE_NAME, PRICE_FEATURE_EXTENSION_COLUMNS)
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_market_features_symbol_time
        ON {MARKET_FEATURES_TABLE_NAME} (symbol, timeframe, time_server)
        """
    )
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_market_features_time
        ON {MARKET_FEATURES_TABLE_NAME} (time_server)
        """
    )


def _ensure_ml_dataset_schema(connection: sqlite3.Connection) -> None:
    connection.execute(CREATE_ML_DATASET_TABLE_SQL)
    _ensure_columns(
        connection,
        ML_DATASET_TABLE_NAME,
        {**PRICE_FEATURE_EXTENSION_COLUMNS, **ML_FUTURE_LABEL_COLUMNS, **ML_TRIPLE_BARRIER_LABEL_COLUMNS},
    )
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_ml_dataset_symbol_timeframe_time
        ON {ML_DATASET_TABLE_NAME} (symbol, timeframe, time_server)
        """
    )


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_columns(connection: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing = _table_columns(connection, table_name)
    for column_name, column_type in columns.items():
        if column_name not in existing:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def initialize_database() -> None:
    """Backward-compatible standalone helper using the default database path."""
    init_database(DATABASE_PATH)
    print(f"SQLite database is ready: {DATABASE_PATH}")


if __name__ == "__main__":
    initialize_database()
