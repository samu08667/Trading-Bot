"""Analyze historical spread samples from the local SQLite database.

This script is offline research tooling only. It reads existing SQLite rows,
summarizes spread behavior, and can write ignored local cost-config candidates.
It does not connect to MetaTrader5, create signals, or perform live trading.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
from statistics import mean, median, pstdev
from typing import Any, Iterable

try:
    from session_utils import session_name
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.analyze_historical_spreads
    from scripts.session_utils import session_name


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "cost_model" / "historical_spreads"
DEFAULT_OUTPUT_CONFIG_DIR = BASE_DIR / "config" / "brokers"

PRICE_BARS_TABLE = "price_bars"
PRICE_FEATURES_TABLE = "price_features"

SPREAD_BY_SYMBOL_FILE = "spread_by_symbol.csv"
SPREAD_BY_HOUR_FILE = "spread_by_hour.csv"
SPREAD_BY_SESSION_FILE = "spread_by_session.csv"
SPREAD_AUDIT_REPORT_FILE = "spread_audit_report.md"
SPREAD_CONFIG_CANDIDATES_FILE = "spread_config_candidates.csv"

PROTECTED_OUTPUT_FILES = (
    SPREAD_BY_SYMBOL_FILE,
    SPREAD_BY_HOUR_FILE,
    SPREAD_BY_SESSION_FILE,
    SPREAD_AUDIT_REPORT_FILE,
    SPREAD_CONFIG_CANDIDATES_FILE,
)

PERCENTILE_ROLES = {
    75: "base/conservative",
    90: "conservative/stress",
    95: "stress",
}


@dataclass(frozen=True)
class SpreadSource:
    table: str
    column: str

    @property
    def label(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass(frozen=True)
class SpreadSample:
    symbol: str
    timeframe: str
    time_server: str
    spread_points: float


def normalize_symbols(values: Iterable[str] | None) -> list[str]:
    symbols: list[str] = []
    for value in values or []:
        for token in str(value).split(","):
            symbol = token.strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols


def validate_date(value: str | None, flag_name: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{flag_name} must use YYYY-MM-DD format.") from exc
    return text


def parse_time_hour(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).hour
    except ValueError:
        if len(text) >= 13 and text[11:13].isdigit():
            hour = int(text[11:13])
            return hour if 0 <= hour <= 23 else None
    return None


def finite_nonnegative(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def table_columns(connection: sqlite3.Connection, table: str) -> set[str] | None:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if row is None:
        return None
    return {str(item[1]) for item in connection.execute(f"PRAGMA table_info({table})")}


def detect_spread_source(connection: sqlite3.Connection) -> SpreadSource:
    price_bars_columns = table_columns(connection, PRICE_BARS_TABLE)
    if price_bars_columns is not None and "spread" in price_bars_columns:
        return SpreadSource(PRICE_BARS_TABLE, "spread")

    price_features_columns = table_columns(connection, PRICE_FEATURES_TABLE)
    if price_features_columns is not None and "spread_avg_20" in price_features_columns:
        return SpreadSource(PRICE_FEATURES_TABLE, "spread_avg_20")

    raise ValueError(
        "No supported historical spread column found. Expected price_bars.spread "
        "or price_features.spread_avg_20."
    )


def ensure_source_columns(connection: sqlite3.Connection, source: SpreadSource) -> None:
    columns = table_columns(connection, source.table)
    required = {"symbol", "timeframe", "time_server", source.column}
    missing = sorted(required - (columns or set()))
    if missing:
        raise ValueError(f"Table {source.table!r} is missing required columns: {', '.join(missing)}.")


def load_spread_samples(
    db_path: Path,
    *,
    symbols: list[str],
    timeframe: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[SpreadSource, list[SpreadSample]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    if not symbols:
        raise ValueError("--symbols must include at least one symbol.")

    start_date = validate_date(start_date, "--start-date")
    end_date = validate_date(end_date, "--end-date")
    placeholders = ",".join("?" for _ in symbols)
    params: list[object] = [*symbols, timeframe]
    date_filters = ""
    if start_date is not None:
        date_filters += " AND substr(time_server, 1, 10) >= ?"
        params.append(start_date)
    if end_date is not None:
        date_filters += " AND substr(time_server, 1, 10) <= ?"
        params.append(end_date)

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        source = detect_spread_source(connection)
        ensure_source_columns(connection, source)
        rows = connection.execute(
            f"""
            SELECT
                symbol,
                timeframe,
                time_server,
                {source.column} AS spread_points
            FROM {source.table}
            WHERE symbol IN ({placeholders})
              AND timeframe = ?
              AND time_server IS NOT NULL
              AND {source.column} IS NOT NULL
              {date_filters}
            ORDER BY symbol ASC, time_server ASC
            """,
            params,
        ).fetchall()

    samples: list[SpreadSample] = []
    for row in rows:
        spread = finite_nonnegative(row["spread_points"])
        if spread is None:
            continue
        samples.append(
            SpreadSample(
                symbol=str(row["symbol"]).upper(),
                timeframe=str(row["timeframe"]),
                time_server=str(row["time_server"]),
                spread_points=spread,
            )
        )
    return source, samples


def percentile(sorted_values: list[float], percentile_value: int) -> float | None:
    if not sorted_values:
        return None
    index = int((len(sorted_values) - 1) * (percentile_value / 100))
    return sorted_values[index]


def rounded(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def spread_stats(values: list[float]) -> dict[str, object]:
    sorted_values = sorted(values)
    return {
        "spread_count": len(sorted_values),
        "spread_mean_points": rounded(mean(sorted_values)) if sorted_values else None,
        "spread_median_points": rounded(median(sorted_values)) if sorted_values else None,
        "spread_p75_points": rounded(percentile(sorted_values, 75)),
        "spread_p90_points": rounded(percentile(sorted_values, 90)),
        "spread_p95_points": rounded(percentile(sorted_values, 95)),
        "spread_min_points": rounded(min(sorted_values)) if sorted_values else None,
        "spread_max_points": rounded(max(sorted_values)) if sorted_values else None,
        "spread_std_points": rounded(pstdev(sorted_values)) if len(sorted_values) > 1 else 0.0 if sorted_values else None,
    }


def group_samples_by_symbol(samples: list[SpreadSample]) -> dict[str, list[SpreadSample]]:
    grouped: dict[str, list[SpreadSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.symbol, []).append(sample)
    return grouped


def summarize_by_symbol(source: SpreadSource, symbols: list[str], samples: list[SpreadSample]) -> tuple[list[dict[str, object]], list[str]]:
    grouped = group_samples_by_symbol(samples)
    rows: list[dict[str, object]] = []
    skipped: list[str] = []
    for symbol in symbols:
        symbol_samples = grouped.get(symbol, [])
        if not symbol_samples:
            skipped.append(symbol)
            continue
        values = [sample.spread_points for sample in symbol_samples]
        times = [sample.time_server for sample in symbol_samples]
        rows.append(
            {
                "symbol": symbol,
                "spread_source": source.label,
                **spread_stats(values),
                "first_timestamp": min(times),
                "last_timestamp": max(times),
            }
        )
    return rows, skipped


def summarize_by_hour(source: SpreadSource, samples: list[SpreadSample]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[float]] = {}
    for sample in samples:
        hour = parse_time_hour(sample.time_server)
        if hour is None:
            continue
        grouped.setdefault((sample.symbol, hour), []).append(sample.spread_points)
    rows: list[dict[str, object]] = []
    for (symbol, hour), values in sorted(grouped.items()):
        rows.append({"symbol": symbol, "hour": hour, "spread_source": source.label, **spread_stats(values)})
    return rows


def summarize_by_session(source: SpreadSource, samples: list[SpreadSample]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[float]] = {}
    for sample in samples:
        hour = parse_time_hour(sample.time_server)
        session = session_name(hour)
        if session is None:
            continue
        grouped.setdefault((sample.symbol, session), []).append(sample.spread_points)
    rows: list[dict[str, object]] = []
    for (symbol, session), values in sorted(grouped.items()):
        rows.append({"symbol": symbol, "hour_session": session, "spread_source": source.label, **spread_stats(values)})
    return rows


def infer_point_size(symbol: str) -> float | None:
    compact = re.sub(r"[^A-Z0-9]", "", str(symbol or "").upper())
    if compact.startswith(("XAUUSD", "XAGUSD")):
        return None
    base = compact[:6]
    if len(base) == 6 and base.isalpha():
        return 0.001 if base.endswith("JPY") else 0.00001
    return None


def percentile_field(percentile_value: int) -> str:
    return f"spread_p{percentile_value}_points"


def config_filename(prefix: str, percentile_value: int) -> str:
    return f"{prefix}_p{percentile_value}.local.json"


def is_versionable_broker_example_config(path: Path) -> bool:
    return path.name.endswith(".example.json")


def candidate_config_rows(
    symbol_rows: list[dict[str, object]],
    percentiles: list[int],
    *,
    config_prefix: str,
    generated_configs: dict[int, Path] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    generated_configs = generated_configs or {}
    for symbol_row in symbol_rows:
        symbol = str(symbol_row["symbol"])
        point_size = infer_point_size(symbol)
        for percentile_value in percentiles:
            fallback = symbol_row.get(percentile_field(percentile_value))
            rows.append(
                {
                    "symbol": symbol,
                    "percentile": percentile_value,
                    "percentile_role": PERCENTILE_ROLES.get(percentile_value, "custom"),
                    "fallback_spread_points": fallback,
                    "point_size": point_size,
                    "spread_count": symbol_row.get("spread_count"),
                    "spread_source": symbol_row.get("spread_source"),
                    "config_filename": (
                        str(generated_configs[percentile_value])
                        if percentile_value in generated_configs
                        else config_filename(config_prefix, percentile_value)
                    ),
                }
            )
    return rows


def build_cost_config(
    *,
    symbol_rows: list[dict[str, object]],
    percentile_value: int,
    broker_name: str,
    account_type: str,
    db_path: Path,
    timeframe: str,
    start_date: str | None,
    end_date: str | None,
    spread_source: SpreadSource,
    slippage_bps_round_trip: float,
    xauusd_slippage_bps_round_trip: float,
    commission_bps_round_trip: float,
    xauusd_commission_bps_round_trip: float,
    created_at: str,
) -> dict[str, Any]:
    symbols: dict[str, dict[str, object]] = {}
    for row in symbol_rows:
        symbol = str(row["symbol"])
        fallback = row.get(percentile_field(percentile_value))
        point_size = infer_point_size(symbol)
        if fallback is None or point_size is None:
            continue
        symbol_config: dict[str, object] = {
            "point_size": point_size,
            "fallback_spread_points": fallback,
        }
        if symbol.startswith("XAUUSD"):
            symbol_config["slippage_bps_round_trip"] = xauusd_slippage_bps_round_trip
            symbol_config["commission_bps_round_trip"] = xauusd_commission_bps_round_trip
        symbols[symbol] = symbol_config

    return {
        "metadata": {
            "broker": broker_name,
            "account_type": account_type,
            "purpose": "offline_research_only",
            "generated_from": "local_sqlite_historical_spreads",
            "db_path": str(db_path),
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "spread_source": spread_source.label,
            "percentile_used": percentile_value,
            "created_at": created_at,
            "commission_slippage_warning": "commission_bps_round_trip and slippage_bps_round_trip are research assumptions and must be verified before use.",
            "net_return_warning": "Estimated net returns remain offline estimates, not real execution simulations or broker-official performance.",
        },
        "default": {
            "slippage_bps_round_trip": slippage_bps_round_trip,
            "commission_bps_round_trip": commission_bps_round_trip,
            "fallback_spread_points": None,
        },
        "symbols": symbols,
    }


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Config already exists: {path}. Pass --overwrite to regenerate it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def output_dir_for_run(base_output_dir: Path, run_id: str, overwrite: bool) -> Path:
    output_dir = base_output_dir / run_id
    existing = [output_dir / name for name in PROTECTED_OUTPUT_FILES if (output_dir / name).exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Historical spread output already exists under {output_dir}. Pass --overwrite to regenerate it.")
    return output_dir


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_audit_report(
    path: Path,
    *,
    run_id: str,
    db_path: Path,
    timeframe: str,
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
    spread_source: SpreadSource,
    symbol_rows: list[dict[str, object]],
    skipped_symbols: list[str],
    generated_config_paths: dict[int, Path],
    config_percentiles: list[int],
) -> None:
    lines = [
        "# Historical Spread Audit Report",
        "",
        "This report is research-only. It analyzes spread samples already stored in the local SQLite database and does not connect to a broker or MetaTrader5.",
        "",
        "## Run Context",
        "",
        f"- Run ID: {run_id}",
        f"- Database: {db_path}",
        f"- Timeframe: {timeframe}",
        f"- Symbols requested: {' '.join(symbols)}",
        f"- Start date: {start_date or 'not set'}",
        f"- End date: {end_date or 'not set'}",
        f"- Spread source: {spread_source.label}",
        "",
        "## Percentile Interpretation",
        "",
        "- p75: base/conservative.",
        "- p90: conservative/stress.",
        "- p95: stress.",
        "",
        "## Symbol Samples",
        "",
    ]
    if symbol_rows:
        for row in symbol_rows:
            lines.append(
                f"- {row['symbol']}: {row['spread_count']} samples, "
                f"p75={row['spread_p75_points']}, p90={row['spread_p90_points']}, p95={row['spread_p95_points']}"
            )
    else:
        lines.append("- No valid spread samples found.")
    lines.extend(["", "## Skipped Symbols", ""])
    if skipped_symbols:
        lines.extend(f"- {symbol}: no valid spread samples." for symbol in skipped_symbols)
    else:
        lines.append("- None.")
    lines.extend(["", "## Generated Configs", ""])
    if generated_config_paths:
        for percentile_value in config_percentiles:
            path_for_percentile = generated_config_paths.get(percentile_value)
            if path_for_percentile is not None:
                lines.append(f"- p{percentile_value}: {path_for_percentile}")
    else:
        lines.append("- None. Pass --generate-config to write ignored .local.json candidates.")
    lines.extend(
        [
            "",
            "## Warnings",
            "",
            "- Local generated configs are offline estimates and are not broker-official.",
            "- Commission and slippage values are assumptions.",
            "- Net returns remain estimates, not real execution simulations.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_local_configs(
    *,
    args: argparse.Namespace,
    symbol_rows: list[dict[str, object]],
    spread_source: SpreadSource,
    created_at: str,
) -> dict[int, Path]:
    generated: dict[int, Path] = {}
    for percentile_value in args.config_percentiles:
        path = args.output_config_dir / config_filename(args.config_prefix, percentile_value)
        payload = build_cost_config(
            symbol_rows=symbol_rows,
            percentile_value=percentile_value,
            broker_name=args.broker_name,
            account_type=args.account_type,
            db_path=args.db_path,
            timeframe=args.timeframe,
            start_date=args.start_date,
            end_date=args.end_date,
            spread_source=spread_source,
            slippage_bps_round_trip=args.slippage_bps_round_trip,
            xauusd_slippage_bps_round_trip=args.xauusd_slippage_bps_round_trip,
            commission_bps_round_trip=args.commission_bps_round_trip,
            xauusd_commission_bps_round_trip=args.xauusd_commission_bps_round_trip,
            created_at=created_at,
        )
        write_json(path, payload, args.overwrite)
        generated[percentile_value] = path
    return generated


def validate_percentiles(values: list[int]) -> list[int]:
    if not values:
        raise ValueError("--config-percentiles must include at least one percentile.")
    normalized: list[int] = []
    for value in values:
        if value <= 0 or value >= 100:
            raise ValueError("--config-percentiles values must be between 1 and 99.")
        if value not in normalized:
            normalized.append(value)
    return normalized


def run_analysis(args: argparse.Namespace, *, run_id: str | None = None, created_at: str | None = None) -> dict[str, Path]:
    args.symbols = normalize_symbols(args.symbols)
    args.config_percentiles = validate_percentiles([int(value) for value in args.config_percentiles])
    args.start_date = validate_date(args.start_date, "--start-date")
    args.end_date = validate_date(args.end_date, "--end-date")
    run_id = run_id or current_run_id()
    created_at = created_at or current_timestamp()
    output_dir = output_dir_for_run(args.output_dir, run_id, args.overwrite)

    spread_source, samples = load_spread_samples(
        args.db_path,
        symbols=args.symbols,
        timeframe=args.timeframe,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    symbol_rows, skipped_symbols = summarize_by_symbol(spread_source, args.symbols, samples)
    hour_rows = summarize_by_hour(spread_source, samples)
    session_rows = summarize_by_session(spread_source, samples)

    generated_config_paths: dict[int, Path] = {}
    if args.generate_config:
        generated_config_paths = generate_local_configs(
            args=args,
            symbol_rows=symbol_rows,
            spread_source=spread_source,
            created_at=created_at,
        )

    config_candidate_rows = candidate_config_rows(
        symbol_rows,
        args.config_percentiles,
        config_prefix=args.config_prefix,
        generated_configs=generated_config_paths,
    )

    by_symbol_path = output_dir / SPREAD_BY_SYMBOL_FILE
    by_hour_path = output_dir / SPREAD_BY_HOUR_FILE
    by_session_path = output_dir / SPREAD_BY_SESSION_FILE
    report_path = output_dir / SPREAD_AUDIT_REPORT_FILE
    config_candidates_path = output_dir / SPREAD_CONFIG_CANDIDATES_FILE

    write_csv(
        by_symbol_path,
        symbol_rows,
        [
            "symbol",
            "spread_source",
            "spread_count",
            "spread_mean_points",
            "spread_median_points",
            "spread_p75_points",
            "spread_p90_points",
            "spread_p95_points",
            "spread_min_points",
            "spread_max_points",
            "spread_std_points",
            "first_timestamp",
            "last_timestamp",
        ],
    )
    write_csv(
        by_hour_path,
        hour_rows,
        [
            "symbol",
            "hour",
            "spread_source",
            "spread_count",
            "spread_mean_points",
            "spread_median_points",
            "spread_p75_points",
            "spread_p90_points",
            "spread_p95_points",
            "spread_min_points",
            "spread_max_points",
            "spread_std_points",
        ],
    )
    write_csv(
        by_session_path,
        session_rows,
        [
            "symbol",
            "hour_session",
            "spread_source",
            "spread_count",
            "spread_mean_points",
            "spread_median_points",
            "spread_p75_points",
            "spread_p90_points",
            "spread_p95_points",
            "spread_min_points",
            "spread_max_points",
            "spread_std_points",
        ],
    )
    write_csv(
        config_candidates_path,
        config_candidate_rows,
        [
            "symbol",
            "percentile",
            "percentile_role",
            "fallback_spread_points",
            "point_size",
            "spread_count",
            "spread_source",
            "config_filename",
        ],
    )
    write_audit_report(
        report_path,
        run_id=run_id,
        db_path=args.db_path,
        timeframe=args.timeframe,
        symbols=args.symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        spread_source=spread_source,
        symbol_rows=symbol_rows,
        skipped_symbols=skipped_symbols,
        generated_config_paths=generated_config_paths,
        config_percentiles=args.config_percentiles,
    )

    print(f"Output directory: {output_dir.resolve()}")
    print(f"Spread source: {spread_source.label}")
    print(f"Symbols analyzed: {len(symbol_rows)}")
    if skipped_symbols:
        print(f"Symbols skipped: {' '.join(skipped_symbols)}")
    if generated_config_paths:
        print("Generated local config files:")
        for path in generated_config_paths.values():
            print(f"- {path.resolve()}")

    return {
        "spread_by_symbol": by_symbol_path,
        "spread_by_hour": by_hour_path,
        "spread_by_session": by_session_path,
        "spread_audit_report": report_path,
        "spread_config_candidates": config_candidates_path,
        **{f"config_p{key}": value for key, value in generated_config_paths.items()},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze local SQLite historical spreads for offline cost-model calibration."
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--broker-name", default="Pepperstone")
    parser.add_argument("--account-type", default="Razor")
    parser.add_argument("--generate-config", action="store_true")
    parser.add_argument("--config-percentiles", nargs="+", type=int, default=[75, 90, 95])
    parser.add_argument("--output-config-dir", type=Path, default=DEFAULT_OUTPUT_CONFIG_DIR)
    parser.add_argument("--config-prefix", default="pepperstone_historical")
    parser.add_argument("--slippage-bps-round-trip", type=float, default=0.2)
    parser.add_argument("--xauusd-slippage-bps-round-trip", type=float, default=0.5)
    parser.add_argument("--commission-bps-round-trip", type=float, default=0.7)
    parser.add_argument("--xauusd-commission-bps-round-trip", type=float, default=0.0)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main() -> int:
    try:
        run_analysis(parse_args())
    except (FileNotFoundError, FileExistsError, ValueError, sqlite3.Error, OSError) as exc:
        print(f"Historical spread analysis failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
