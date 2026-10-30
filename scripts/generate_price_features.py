import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sqlite3

try:
    from regime_classification import build_regime_labels
    from session_utils import session_name
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.generate_price_features
    from scripts.regime_classification import build_regime_labels
    from scripts.session_utils import session_name


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
PRICE_BARS_TABLE = "price_bars"
PRICE_FEATURES_TABLE = "price_features"
DEFAULT_POINT_SIZES = {
    "EURUSD": 0.00001,
    "GBPUSD": 0.00001,
    "AUDUSD": 0.00001,
    "USDCAD": 0.00001,
    "USDCHF": 0.00001,
    "USDJPY": 0.001,
}
SYMBOL_METADATA_CONFIG_PATH = BASE_DIR / "config" / "symbol_metadata.local.json"


FEATURE_COLUMNS = [
    "symbol",
    "timeframe",
    "time_server",
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
    "source",
]


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def parse_time_server(value: str) -> datetime:
    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    raise ValueError(f"Unsupported time_server format: {value!r}")


def safe_return(current_close: float, previous_close: float | None) -> float | None:
    if previous_close in (None, 0):
        return None
    return current_close / previous_close - 1


def rolling_mean(values: list[float | int | None], index: int, window: int) -> float | None:
    if index + 1 < window:
        return None

    window_values = values[index - window + 1 : index + 1]
    if any(value is None for value in window_values):
        return None
    return sum(float(value) for value in window_values) / window


def rolling_std(values: list[float | None], index: int, window: int) -> float | None:
    if index + 1 < window:
        return None

    window_values = values[index - window + 1 : index + 1]
    if any(value is None for value in window_values):
        return None

    numeric_values = [float(value) for value in window_values]
    mean = sum(numeric_values) / window
    variance = sum((value - mean) ** 2 for value in numeric_values) / window
    return variance ** 0.5


def rolling_percentile_rank(values: list[float | int | None], index: int, window: int) -> float | None:
    if index + 1 < window:
        return None

    current = values[index]
    window_values = values[index - window + 1 : index + 1]
    if current is None or any(value is None for value in window_values):
        return None

    numeric_values = [float(value) for value in window_values]
    current_value = float(current)
    return sum(1 for value in numeric_values if value <= current_value) / len(numeric_values)


def safe_ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def safe_positive_float(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def normalize_symbol(symbol: object) -> str:
    text = str(symbol or "").strip().upper()
    compact = re.sub(r"[^A-Z0-9]", "", text)
    for known in sorted(DEFAULT_POINT_SIZES, key=len, reverse=True):
        if compact.startswith(known):
            return known
    if compact.startswith("XAUUSD"):
        return "XAUUSD"
    return compact or text


def point_size_from_config(symbol: str, config_path: Path) -> tuple[float | None, str]:
    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    normalized_symbol = normalize_symbol(symbol)

    for raw_symbol, values in config.items():
        if raw_symbol in {"default", "metadata", "symbols"}:
            continue
        if normalize_symbol(raw_symbol) == normalized_symbol and isinstance(values, dict):
            point_size = safe_positive_float(values.get("point_size"))
            if point_size is not None:
                return point_size, "symbol_metadata_config_symbol"

    symbols = config.get("symbols")
    if isinstance(symbols, dict):
        for raw_symbol, values in symbols.items():
            if normalize_symbol(raw_symbol) == normalized_symbol and isinstance(values, dict):
                point_size = safe_positive_float(values.get("point_size"))
                if point_size is not None:
                    return point_size, "point_size_config_symbol"

    default_config = config.get("default")
    if isinstance(default_config, dict):
        point_size = safe_positive_float(default_config.get("point_size"))
        if point_size is not None:
            return point_size, "point_size_config_default"

    return None, "missing"


def resolve_point_size(
    symbol: str,
    *,
    point_size: float | None = None,
    point_size_config: Path | None = None,
    strict: bool = False,
) -> tuple[float | None, str]:
    explicit_point_size = safe_positive_float(point_size)
    if explicit_point_size is not None:
        return explicit_point_size, "explicit"
    if point_size is not None:
        raise ValueError("--point-size must be a finite positive number.")

    if point_size_config is not None:
        configured_point_size, source = point_size_from_config(symbol, point_size_config)
        if configured_point_size is not None:
            return configured_point_size, source

    normalized_symbol = normalize_symbol(symbol)
    default_point_size = DEFAULT_POINT_SIZES.get(normalized_symbol)
    if default_point_size is not None:
        return default_point_size, "internal_fx_default"

    if strict:
        raise ValueError(
            f"No point_size available for {normalized_symbol or symbol!r}. "
            "Pass --point-size, or --point-size-config with either top-level "
            "<SYMBOL>.point_size from config/symbol_metadata.local.json or "
            "symbols.<SYMBOL>.point_size from a cost config."
        )
    return None, "missing"


def true_range(high_price: float, low_price: float, previous_close: float | None) -> float:
    candle_range = high_price - low_price
    if previous_close is None:
        return candle_range
    return max(
        candle_range,
        abs(high_price - previous_close),
        abs(low_price - previous_close),
    )


def volume_flag(ratio: float | None, *, threshold: float, mode: str) -> int | None:
    if ratio is None:
        return None
    if mode == "gte":
        return int(ratio >= threshold)
    if mode == "lte":
        return int(ratio <= threshold)
    raise ValueError(f"Unsupported volume flag mode: {mode}")


def fetch_price_bars(connection: sqlite3.Connection, symbol: str, timeframe: str) -> list[sqlite3.Row]:
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            f"""
            SELECT
                symbol,
                timeframe,
                time_server,
                open,
                high,
                low,
                close,
                tick_volume,
                spread
            FROM {PRICE_BARS_TABLE}
            WHERE symbol = ? AND timeframe = ?
            ORDER BY time_server ASC
            """,
            (symbol, timeframe),
        ).fetchall()
    finally:
        connection.row_factory = None


def generate_features(
    rows: list[sqlite3.Row],
    point_size: float | None = None,
) -> tuple[list[dict[str, object]], int]:
    features = []
    skipped = 0
    closes = [float(row["close"]) if row["close"] is not None else None for row in rows]
    spreads = [int(row["spread"]) if row["spread"] is not None else None for row in rows]
    tick_volumes = [
        int(row["tick_volume"]) if row["tick_volume"] is not None else None for row in rows
    ]
    return_1_values: list[float | None] = []
    true_range_values: list[float | None] = []
    hour_volume_sum: dict[int, float] = {}
    hour_volume_count: dict[int, int] = {}
    session_volume_sum: dict[str, float] = {}
    session_volume_count: dict[str, int] = {}

    for index, row in enumerate(rows):
        try:
            timestamp = parse_time_server(str(row["time_server"]))
            open_price = float(row["open"])
            high_price = float(row["high"])
            low_price = float(row["low"])
            close_price = float(row["close"])
        except (TypeError, ValueError):
            skipped += 1
            return_1_values.append(None)
            true_range_values.append(None)
            continue

        previous_close_1 = closes[index - 1] if index >= 1 else None
        previous_close_5 = closes[index - 5] if index >= 5 else None
        previous_close_20 = closes[index - 20] if index >= 20 else None

        return_1 = safe_return(close_price, previous_close_1)
        return_1_values.append(return_1)
        return_5 = safe_return(close_price, previous_close_5)
        return_20 = safe_return(close_price, previous_close_20)

        candle_range = high_price - low_price
        body_size = abs(close_price - open_price)
        upper_wick = high_price - max(open_price, close_price)
        lower_wick = min(open_price, close_price) - low_price
        current_true_range = true_range(high_price, low_price, previous_close_1)
        true_range_values.append(current_true_range)
        atr_14 = rolling_mean(true_range_values, index, 14)
        atr_20 = rolling_mean(true_range_values, index, 20)
        atr_50 = rolling_mean(true_range_values, index, 50)
        volatility_20 = rolling_std(return_1_values, index, 20)
        volatility_100 = rolling_std(return_1_values, index, 100)
        ma_fast = rolling_mean(closes, index, 20)
        ma_slow = rolling_mean(closes, index, 100)
        ma_diff = ma_fast - ma_slow if ma_fast is not None and ma_slow is not None else None
        tick_volume = tick_volumes[index]
        spread = spreads[index]
        row_point_size = point_size
        if row_point_size is None:
            row_point_size = DEFAULT_POINT_SIZES.get(normalize_symbol(row["symbol"]))
        spread_price = (
            float(spread) * row_point_size
            if spread is not None and spread >= 0 and row_point_size is not None
            else None
        )
        spread_avg_20 = rolling_mean(spreads, index, 20)
        tick_volume_avg_20 = rolling_mean(tick_volumes, index, 20)
        tick_volume_ratio_20 = safe_ratio(tick_volume, tick_volume_avg_20)
        tick_volume_mean_100 = rolling_mean(tick_volumes, index, 100)
        tick_volume_std_100 = rolling_std(tick_volumes, index, 100)  # type: ignore[arg-type]
        tick_volume_zscore_100 = (
            (float(tick_volume) - tick_volume_mean_100) / tick_volume_std_100
            if tick_volume is not None
            and tick_volume_mean_100 is not None
            and tick_volume_std_100 is not None
            and tick_volume_std_100 > 0
            else None
        )
        current_hour_session = session_name(timestamp.hour)
        previous_hour_mean = (
            hour_volume_sum[timestamp.hour] / hour_volume_count[timestamp.hour]
            if hour_volume_count.get(timestamp.hour)
            else None
        )
        previous_session_mean = (
            session_volume_sum[current_hour_session] / session_volume_count[current_hour_session]
            if session_volume_count.get(current_hour_session)
            else None
        )
        range_to_atr_20 = safe_ratio(candle_range, atr_20)
        body_to_atr_20 = safe_ratio(body_size, atr_20)
        upper_wick_to_atr_20 = safe_ratio(upper_wick, atr_20)
        lower_wick_to_atr_20 = safe_ratio(lower_wick, atr_20)
        volatility_ratio_20_100 = safe_ratio(volatility_20, volatility_100)
        spread_return = safe_ratio(spread_price, close_price)
        spread_to_atr_20 = safe_ratio(spread_price, atr_20)
        tick_volume_percentile_100 = rolling_percentile_rank(tick_volumes, index, 100)
        volume_spike_20 = volume_flag(tick_volume_ratio_20, threshold=1.5, mode="gte")
        volume_dry_up_20 = volume_flag(tick_volume_ratio_20, threshold=0.7, mode="lte")
        spread_to_volume_ratio = safe_ratio(spread_avg_20, tick_volume_avg_20)
        volume_vs_hour_avg = safe_ratio(tick_volume, previous_hour_mean)
        volume_vs_session_avg = safe_ratio(tick_volume, previous_session_mean)
        regime_labels = build_regime_labels(
            {
                "time_server": row["time_server"],
                "hour": timestamp.hour,
                "spread_to_atr_20": spread_to_atr_20,
                "spread_return": spread_return,
                "spread_to_volume_ratio": spread_to_volume_ratio,
                "volatility_ratio_20_100": volatility_ratio_20_100,
                "volatility_100": volatility_100,
                "range_to_atr_20": range_to_atr_20,
                "volume_spike_20": volume_spike_20,
                "volume_dry_up_20": volume_dry_up_20,
                "tick_volume_zscore_100": tick_volume_zscore_100,
                "tick_volume_percentile_100": tick_volume_percentile_100,
                "volume_vs_session_avg": volume_vs_session_avg,
            }
        )

        feature = {
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "time_server": row["time_server"],
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "tick_volume": tick_volume,
            "spread": spread,
            "return_1": return_1,
            "return_5": return_5,
            "return_20": return_20,
            "candle_range": candle_range,
            "body_size": body_size,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "true_range": current_true_range,
            "atr_14": atr_14,
            "atr_20": atr_20,
            "atr_50": atr_50,
            "range_to_atr_20": range_to_atr_20,
            "body_to_atr_20": body_to_atr_20,
            "upper_wick_to_atr_20": upper_wick_to_atr_20,
            "lower_wick_to_atr_20": lower_wick_to_atr_20,
            "volatility_20": volatility_20,
            "volatility_100": volatility_100,
            "volatility_ratio_20_100": volatility_ratio_20_100,
            "ma_fast": ma_fast,
            "ma_slow": ma_slow,
            "ma_diff": ma_diff,
            "close_to_ma_fast_atr_20": safe_ratio(
                close_price - ma_fast if ma_fast is not None else None,
                atr_20,
            ),
            "close_to_ma_slow_atr_20": safe_ratio(
                close_price - ma_slow if ma_slow is not None else None,
                atr_20,
            ),
            "ma_diff_atr_20": safe_ratio(ma_diff, atr_20),
            "spread_avg_20": spread_avg_20,
            "spread_price": spread_price,
            "spread_return": spread_return,
            "spread_to_atr_20": spread_to_atr_20,
            "tick_volume_avg_20": tick_volume_avg_20,
            "tick_volume_ratio_20": tick_volume_ratio_20,
            "tick_volume_zscore_100": tick_volume_zscore_100,
            "tick_volume_percentile_100": tick_volume_percentile_100,
            "volume_spike_20": volume_spike_20,
            "volume_dry_up_20": volume_dry_up_20,
            "spread_to_volume_ratio": spread_to_volume_ratio,
            "volume_vs_hour_avg": volume_vs_hour_avg,
            "volume_vs_session_avg": volume_vs_session_avg,
            **regime_labels,
            "hour_session": current_hour_session,
            "hour": timestamp.hour,
            "day_of_week": timestamp.weekday(),
            "source": "price_bars",
        }
        features.append(feature)
        if tick_volume is not None:
            hour_volume_sum[timestamp.hour] = hour_volume_sum.get(timestamp.hour, 0.0) + float(tick_volume)
            hour_volume_count[timestamp.hour] = hour_volume_count.get(timestamp.hour, 0) + 1
            session_volume_sum[current_hour_session] = (
                session_volume_sum.get(current_hour_session, 0.0) + float(tick_volume)
            )
            session_volume_count[current_hour_session] = session_volume_count.get(current_hour_session, 0) + 1

    return features, skipped


def upsert_features(connection: sqlite3.Connection, features: list[dict[str, object]]) -> int:
    if not features:
        return 0

    placeholders = ", ".join("?" for _ in FEATURE_COLUMNS)
    insert_sql = f"""
        INSERT OR REPLACE INTO {PRICE_FEATURES_TABLE} ({", ".join(FEATURE_COLUMNS)})
        VALUES ({placeholders})
    """

    rows = [tuple(feature[column] for column in FEATURE_COLUMNS) for feature in features]
    connection.executemany(insert_sql, rows)
    return len(rows)


def generate_price_features(
    symbol: str,
    timeframe: str,
    db_path: Path,
    *,
    point_size: float | None = None,
    point_size_config: Path | None = None,
    strict_point_size: bool = False,
) -> dict[str, int | str | float | None]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    resolved_point_size, point_size_source = resolve_point_size(
        symbol,
        point_size=point_size,
        point_size_config=point_size_config,
        strict=strict_point_size,
    )

    with sqlite3.connect(db_path) as connection:
        if not table_exists(connection, PRICE_BARS_TABLE):
            raise sqlite3.OperationalError(
                f"Table {PRICE_BARS_TABLE!r} does not exist. Import price bars first."
            )
        if not table_exists(connection, PRICE_FEATURES_TABLE):
            raise sqlite3.OperationalError(
                f"Table {PRICE_FEATURES_TABLE!r} does not exist. Run python scripts/init_database.py first."
            )

        rows = fetch_price_bars(connection, symbol, timeframe)
        features, rows_skipped = generate_features(rows, point_size=resolved_point_size)
        rows_changed = upsert_features(connection, features)
        connection.commit()

    return {
        "rows_read": len(rows),
        "rows_generated": len(features),
        "rows_inserted_updated": rows_changed,
        "rows_skipped": rows_skipped,
        "point_size": resolved_point_size,
        "point_size_source": point_size_source,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate base read-only price features from imported historical price bars."
    )
    parser.add_argument("--symbol", required=True, help="Symbol to process, for example EURUSD.")
    parser.add_argument("--timeframe", required=True, help="Timeframe to process, for example M15.")
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    parser.add_argument(
        "--point-size",
        type=float,
        help="Explicit MT5 point size for converting raw spread points into price units.",
    )
    parser.add_argument(
        "--point-size-config",
        type=Path,
        help=(
            "Optional JSON config with top-level <SYMBOL>.point_size, for example "
            f"{SYMBOL_METADATA_CONFIG_PATH}, or symbols.<SYMBOL>.point_size from a cost config."
        ),
    )
    parser.add_argument(
        "--strict-point-size",
        action="store_true",
        help=(
            "Fail if no point_size is available instead of writing NULL "
            "spread_price/spread_return/spread_to_atr_20."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbol = args.symbol.strip().upper()
    timeframe = args.timeframe.strip().upper()

    try:
        result = generate_price_features(
            symbol,
            timeframe,
            args.db_path,
            point_size=args.point_size,
            point_size_config=args.point_size_config,
            strict_point_size=args.strict_point_size,
        )
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"Price feature generation failed: {exc}")
        return 1

    print("Price feature generation complete.")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Rows read: {result['rows_read']}")
    print(f"Rows generated: {result['rows_generated']}")
    print(f"Rows inserted/updated: {result['rows_inserted_updated']}")
    print(f"Rows skipped: {result['rows_skipped']}")
    print(f"Point size: {result['point_size']}")
    print(f"Point size source: {result['point_size_source']}")
    if result["point_size_source"] == "missing":
        print(
            "Warning: point_size missing; spread_price, spread_return, and "
            "spread_to_atr_20 will be NULL for symbols without an internal default."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
