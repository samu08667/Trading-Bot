"""Export a read-only Python-vs-MQL5 parity dataset for the fixed candidate.

The exporter reads existing feature rows from a local SQLite database opened in
read-only mode and writes a CSV for signal-only EA parity work. It does not
connect to any broker surface, mutate the database, refresh features, build a
broker payload, or perform trade operations.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STRATEGY_SPEC = (
    BASE_DIR
    / "config"
    / "strategy_specs"
    / "gbpusd_short_h10_1_5_off_hours_strategy_spec.json"
)
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_FEATURE_TABLE = "price_features"
ALLOWLISTED_FEATURE_TABLES = {"price_features", "market_features"}

SOURCE_COLUMNS = [
    "symbol",
    "timeframe",
    "time_server",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "atr_20",
    "ma_fast",
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
    "hour_session",
]

EXPORT_FIELDNAMES = [
    "time_server",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "atr_20",
    "ma_fast",
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
    "hour_session",
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100_bucket",
    "signal_bool",
    "entry_reference_price",
    "sl_price_preview",
    "tp_price_preview",
    "max_holding_bars",
    "max_exit_time_server",
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def quote_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQLite identifier: {value!r}")
    return f'"{value}"'


def bucket_for_value(value: float | None, low_mid_cutoff: float, mid_high_cutoff: float) -> str:
    if value is None:
        return "unreadable"
    if value <= low_mid_cutoff:
        return "low_tercile"
    if value <= mid_high_cutoff:
        return "mid_tercile"
    return "high_tercile"


def feature_threshold(spec: dict[str, Any], feature_name: str) -> tuple[float, float, str]:
    feature = spec["features"][feature_name]
    return (
        float(feature["low_mid_cutoff"]),
        float(feature["mid_high_cutoff"]),
        str(feature["required_bucket"]),
    )


def max_holding_bars(spec: dict[str, Any]) -> int:
    lifecycle = spec.get("trade_lifecycle", {})
    value = lifecycle.get("max_holding_bars", spec.get("sl_tp", {}).get("horizon_bars"))
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("StrategySpec max_holding_bars must be a positive integer.")
    return parsed


def table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})")}


def validate_feature_table(connection: sqlite3.Connection, table_name: str) -> None:
    if table_name not in ALLOWLISTED_FEATURE_TABLES:
        raise ValueError(f"Feature table is not allowlisted for parity export: {table_name}")
    columns = table_columns(connection, table_name)
    missing = [column for column in SOURCE_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"Feature table {table_name!r} is missing required columns: {', '.join(missing)}")


def fetch_feature_rows(
    *,
    db_path: Path,
    table_name: str,
    symbol: str,
    timeframe: str,
    limit: int,
) -> list[dict[str, Any]]:
    if limit <= 0:
        raise ValueError("--limit must be a positive integer.")
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    selected = ", ".join(quote_identifier(column) for column in SOURCE_COLUMNS)
    table = quote_identifier(table_name)
    query = f"""
        SELECT {selected}
        FROM (
            SELECT {selected}
            FROM {table}
            WHERE symbol = ? AND timeframe = ?
            ORDER BY time_server DESC
            LIMIT ?
        )
        ORDER BY time_server ASC
    """
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        validate_feature_table(connection, table_name)
        rows = connection.execute(query, (symbol, timeframe, limit)).fetchall()
    return [dict(row) for row in rows]


def parity_row(
    source: dict[str, Any],
    spec: dict[str, Any],
    *,
    max_exit_time_server: Any = "",
) -> dict[str, Any]:
    close_lower, close_upper, close_required = feature_threshold(spec, "close_to_ma_fast_atr_20")
    volume_lower, volume_upper, volume_required = feature_threshold(spec, "tick_volume_percentile_100")
    close_value = safe_float(source.get("close"))
    atr_value = safe_float(source.get("atr_20"))
    spread_value = safe_float(source.get("spread"))
    close_feature = safe_float(source.get("close_to_ma_fast_atr_20"))
    volume_feature = safe_float(source.get("tick_volume_percentile_100"))
    close_bucket = bucket_for_value(close_feature, close_lower, close_upper)
    volume_bucket = bucket_for_value(volume_feature, volume_lower, volume_upper)
    direction = str(spec["direction"])
    signal_bool = (
        source.get("hour_session") == spec["session"]["required_value"]
        and close_bucket == close_required
        and volume_bucket == volume_required
        and spread_value is not None
        and spread_value <= float(spec["spread_policy"]["max_spread_points"])
        and close_value is not None
        and close_value > 0
        and atr_value is not None
        and atr_value > 0
    )
    entry_reference_price: float | None = None
    sl_price_preview: float | None = None
    tp_price_preview: float | None = None
    if signal_bool:
        entry_reference_price = close_value
        if direction == "short":
            sl_price_preview = close_value + float(spec["sl_tp"]["sl_atr"]) * atr_value
            tp_price_preview = close_value - float(spec["sl_tp"]["tp_atr"]) * atr_value
        else:
            sl_price_preview = close_value - float(spec["sl_tp"]["sl_atr"]) * atr_value
            tp_price_preview = close_value + float(spec["sl_tp"]["tp_atr"]) * atr_value
    return {
        "time_server": source.get("time_server"),
        "open": source.get("open"),
        "high": source.get("high"),
        "low": source.get("low"),
        "close": source.get("close"),
        "tick_volume": source.get("tick_volume"),
        "spread": source.get("spread"),
        "atr_20": source.get("atr_20"),
        "ma_fast": source.get("ma_fast"),
        "close_to_ma_fast_atr_20": source.get("close_to_ma_fast_atr_20"),
        "tick_volume_percentile_100": source.get("tick_volume_percentile_100"),
        "hour_session": source.get("hour_session"),
        "close_to_ma_fast_atr_20_bucket": close_bucket,
        "tick_volume_percentile_100_bucket": volume_bucket,
        "signal_bool": signal_bool,
        "entry_reference_price": entry_reference_price,
        "sl_price_preview": sl_price_preview,
        "tp_price_preview": tp_price_preview,
        "max_holding_bars": max_holding_bars(spec),
        "max_exit_time_server": max_exit_time_server,
    }


def build_parity_rows(source_rows: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    holding_bars = max_holding_bars(spec)
    parity_rows: list[dict[str, Any]] = []
    for index, source in enumerate(source_rows):
        exit_index = index + holding_bars
        exit_time = source_rows[exit_index].get("time_server") if exit_index < len(source_rows) else ""
        parity_rows.append(parity_row(source, spec, max_exit_time_server=exit_time))
    return parity_rows


def write_csv(path: Path, rows: list[dict[str, Any]], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output CSV already exists: {path}. Use --overwrite to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in EXPORT_FIELDNAMES})


def export_parity_dataset(
    *,
    strategy_spec_path: Path,
    db_path: Path,
    feature_table: str,
    output_csv: Path,
    limit: int,
    overwrite: bool,
) -> dict[str, Any]:
    spec = read_json(strategy_spec_path)
    rows = fetch_feature_rows(
        db_path=db_path,
        table_name=feature_table,
        symbol=str(spec["symbol"]),
        timeframe=str(spec["timeframe"]),
        limit=limit,
    )
    parity_rows = build_parity_rows(rows, spec)
    write_csv(output_csv, parity_rows, overwrite=overwrite)
    return {
        "strategy_spec": str(strategy_spec_path),
        "db_path": str(db_path),
        "feature_table": feature_table,
        "output_csv": str(output_csv),
        "rows_exported": len(parity_rows),
        "signal_rows": sum(1 for row in parity_rows if row["signal_bool"] is True),
        "read_only_db": True,
        "broker_connection_performed": False,
        "trade_operation_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a read-only fixed-candidate Python/MQL5 EA signal parity dataset."
    )
    parser.add_argument("--strategy-spec", type=Path, default=DEFAULT_STRATEGY_SPEC)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--feature-table", default=DEFAULT_FEATURE_TABLE)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = export_parity_dataset(
            strategy_spec_path=args.strategy_spec,
            db_path=args.db_path,
            feature_table=args.feature_table,
            output_csv=args.output_csv,
            limit=args.limit,
            overwrite=bool(args.overwrite),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Fixed-candidate EA parity dataset export failed: {exc}")
        return 1
    print("Fixed-candidate EA parity dataset export complete.")
    print(f"Rows exported: {summary['rows_exported']}")
    print(f"Signal rows: {summary['signal_rows']}")
    print(f"Output CSV: {summary['output_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
