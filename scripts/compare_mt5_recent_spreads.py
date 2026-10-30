"""Compare recent read-only MT5 spreads with local SQLite spread history.

This diagnostic reads tick bid/ask data from the currently connected terminal
and compares it with historical spread samples already stored in SQLite. It is
research-only and does not create trading instructions or modify broker state.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import sqlite3
from statistics import mean, median, pstdev
from typing import Any, Iterable

try:
    from analyze_historical_spreads import (
        SpreadSource,
        load_spread_samples,
        normalize_symbols,
        parse_time_hour,
        percentile,
        summarize_by_symbol,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.compare_mt5_recent_spreads
    from scripts.analyze_historical_spreads import (
        SpreadSource,
        load_spread_samples,
        normalize_symbols,
        parse_time_hour,
        percentile,
        summarize_by_symbol,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "cost_model" / "mt5_spread_comparison"

MT5_RECENT_BY_SYMBOL_FILE = "mt5_recent_spread_by_symbol.csv"
HISTORICAL_BY_SYMBOL_FILE = "historical_spread_by_symbol.csv"
SPREAD_COMPARISON_FILE = "spread_comparison.csv"
MT5_BY_HOUR_FILE = "mt5_spread_by_hour.csv"
REPORT_FILE = "spread_comparison_report.md"

PROTECTED_OUTPUT_FILES = (
    MT5_RECENT_BY_SYMBOL_FILE,
    HISTORICAL_BY_SYMBOL_FILE,
    SPREAD_COMPARISON_FILE,
    MT5_BY_HOUR_FILE,
    REPORT_FILE,
)


@dataclass(frozen=True)
class RecentSpreadSample:
    symbol: str
    mt5_symbol_name: str
    time_server: str
    spread_points: float


def finite_positive(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def finite_nonnegative(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def tick_value(tick: object, key: str) -> object:
    if isinstance(tick, dict):
        return tick.get(key)
    try:
        return tick[key]  # numpy structured rows support this access.
    except (TypeError, KeyError, IndexError, ValueError):
        return getattr(tick, key, None)


def tick_timestamp(tick: object) -> int | None:
    raw = tick_value(tick, "time")
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def format_tick_time(timestamp: int | None) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def spread_points_from_ticks(ticks: Iterable[object], point_size: float) -> list[tuple[str, float]]:
    point = finite_positive(point_size)
    if point is None:
        return []
    spreads: list[tuple[str, float]] = []
    for tick in ticks:
        bid = finite_positive(tick_value(tick, "bid"))
        ask = finite_positive(tick_value(tick, "ask"))
        if bid is None or ask is None or ask < bid:
            continue
        spread = (ask - bid) / point
        if math.isfinite(spread) and spread >= 0:
            spreads.append((format_tick_time(tick_timestamp(tick)), round(spread, 6)))
    return spreads


def rounded(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def spread_stats(values: list[float]) -> dict[str, object]:
    sorted_values = sorted(values)
    return {
        "count": len(sorted_values),
        "mean": rounded(mean(sorted_values)) if sorted_values else None,
        "median": rounded(median(sorted_values)) if sorted_values else None,
        "p75": rounded(percentile(sorted_values, 75)),
        "p90": rounded(percentile(sorted_values, 90)),
        "p95": rounded(percentile(sorted_values, 95)),
        "min": rounded(min(sorted_values)) if sorted_values else None,
        "max": rounded(max(sorted_values)) if sorted_values else None,
        "std": rounded(pstdev(sorted_values)) if len(sorted_values) > 1 else 0.0 if sorted_values else None,
    }


def summarize_recent_symbol(
    *,
    symbol: str,
    mt5_symbol_name: str,
    point_size: float | None,
    digits: int | None,
    tick_spreads: list[tuple[str, float]],
) -> dict[str, object]:
    values = [spread for _timestamp, spread in tick_spreads]
    timestamps = [timestamp for timestamp, _spread in tick_spreads if timestamp]
    stats = spread_stats(values)
    return {
        "symbol": symbol,
        "mt5_symbol_name": mt5_symbol_name,
        "point_size": point_size,
        "digits": digits,
        "tick_count": stats["count"],
        "spread_mean_points": stats["mean"],
        "spread_median_points": stats["median"],
        "spread_p75_points": stats["p75"],
        "spread_p90_points": stats["p90"],
        "spread_p95_points": stats["p95"],
        "spread_min_points": stats["min"],
        "spread_max_points": stats["max"],
        "first_tick_time": min(timestamps) if timestamps else "",
        "last_tick_time": max(timestamps) if timestamps else "",
    }


def summarize_recent_by_hour(samples: list[RecentSpreadSample]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[float]] = {}
    for sample in samples:
        hour = parse_time_hour(sample.time_server)
        if hour is None:
            continue
        grouped.setdefault((sample.symbol, hour), []).append(sample.spread_points)
    rows: list[dict[str, object]] = []
    for (symbol, hour), values in sorted(grouped.items()):
        stats = spread_stats(values)
        rows.append(
            {
                "symbol": symbol,
                "hour": hour,
                "tick_count": stats["count"],
                "spread_mean_points": stats["mean"],
                "spread_median_points": stats["median"],
                "spread_p75_points": stats["p75"],
                "spread_p90_points": stats["p90"],
                "spread_p95_points": stats["p95"],
                "spread_min_points": stats["min"],
                "spread_max_points": stats["max"],
            }
        )
    return rows


def safe_ratio(numerator: object, denominator: object) -> float | None:
    num = finite_nonnegative(numerator)
    den = finite_positive(denominator)
    if num is None or den is None:
        return None
    return round(num / den, 6)


def compare_symbol_spreads(
    mt5_row: dict[str, object] | None,
    historical_row: dict[str, object] | None,
    *,
    symbol: str,
    alert_ratio: float,
) -> dict[str, object]:
    mt5_count = int(mt5_row.get("tick_count") or 0) if mt5_row else 0
    hist_count = int(historical_row.get("spread_count") or 0) if historical_row else 0
    warning_reasons: list[str] = []
    alert_reasons: list[str] = []

    if mt5_count <= 0:
        warning_reasons.append("missing_mt5_samples")
    if hist_count <= 0:
        warning_reasons.append("missing_historical_samples")

    ratios = {
        "mt5_vs_historical_p75_ratio": safe_ratio(
            mt5_row.get("spread_p75_points") if mt5_row else None,
            historical_row.get("spread_p75_points") if historical_row else None,
        ),
        "mt5_vs_historical_p90_ratio": safe_ratio(
            mt5_row.get("spread_p90_points") if mt5_row else None,
            historical_row.get("spread_p90_points") if historical_row else None,
        ),
        "mt5_vs_historical_p95_ratio": safe_ratio(
            mt5_row.get("spread_p95_points") if mt5_row else None,
            historical_row.get("spread_p95_points") if historical_row else None,
        ),
    }
    for key, label in (
        ("mt5_vs_historical_p75_ratio", "p75"),
        ("mt5_vs_historical_p90_ratio", "p90"),
    ):
        ratio = ratios[key]
        if ratio is None:
            warning_reasons.append(f"missing_or_zero_{label}_ratio")
        elif ratio >= alert_ratio:
            alert_reasons.append(f"{label}_ratio_{ratio}_gte_{alert_ratio}")

    alert_flag = bool(alert_reasons) and not warning_reasons
    reason = "; ".join(alert_reasons or warning_reasons)
    return {
        "symbol": symbol,
        "mt5_tick_count": mt5_count,
        "historical_spread_count": hist_count,
        "mt5_p50_points": mt5_row.get("spread_median_points") if mt5_row else None,
        "historical_p50_points": historical_row.get("spread_median_points") if historical_row else None,
        "mt5_p75_points": mt5_row.get("spread_p75_points") if mt5_row else None,
        "historical_p75_points": historical_row.get("spread_p75_points") if historical_row else None,
        "mt5_p90_points": mt5_row.get("spread_p90_points") if mt5_row else None,
        "historical_p90_points": historical_row.get("spread_p90_points") if historical_row else None,
        "mt5_p95_points": mt5_row.get("spread_p95_points") if mt5_row else None,
        "historical_p95_points": historical_row.get("spread_p95_points") if historical_row else None,
        **ratios,
        "alert_flag": "yes" if alert_flag else "no",
        "alert_reason": reason,
    }


def compare_spread_rows(
    mt5_rows: list[dict[str, object]],
    historical_rows: list[dict[str, object]],
    symbols: list[str],
    alert_ratio: float,
) -> list[dict[str, object]]:
    mt5_by_symbol = {str(row.get("symbol") or "").upper(): row for row in mt5_rows}
    historical_by_symbol = {str(row.get("symbol") or "").upper(): row for row in historical_rows}
    return [
        compare_symbol_spreads(
            mt5_by_symbol.get(symbol),
            historical_by_symbol.get(symbol),
            symbol=symbol,
            alert_ratio=alert_ratio,
        )
        for symbol in symbols
    ]


def mask_login(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    suffix = text[-4:] if len(text) > 4 else text[-1:]
    return f"***{suffix}"


def account_metadata(account_info: object | None) -> dict[str, object]:
    if account_info is None:
        return {"login_masked": "", "server": "", "company": "", "currency": ""}
    return {
        "login_masked": mask_login(getattr(account_info, "login", "")),
        "server": getattr(account_info, "server", ""),
        "company": getattr(account_info, "company", ""),
        "currency": getattr(account_info, "currency", ""),
    }


def terminal_metadata(terminal_info: object | None) -> dict[str, object]:
    if terminal_info is None:
        return {"name": "", "company": "", "build": "", "connected": ""}
    return {
        "name": getattr(terminal_info, "name", ""),
        "company": getattr(terminal_info, "company", ""),
        "build": getattr(terminal_info, "build", ""),
        "connected": getattr(terminal_info, "connected", ""),
    }


def resolve_symbol_name_from_candidates(requested_symbol: str, candidate_names: Iterable[str]) -> str | None:
    requested = str(requested_symbol or "").upper()
    candidates = [str(name) for name in candidate_names]
    for candidate in candidates:
        if candidate.upper() == requested:
            return candidate
    starts = [candidate for candidate in candidates if candidate.upper().startswith(requested)]
    return sorted(starts, key=lambda item: (len(item), item))[0] if starts else None


def select_mt5_symbol(mt5_module: object, requested_symbol: str) -> tuple[str | None, object | None, str | None]:
    info = mt5_module.symbol_info(requested_symbol)
    if info is None:
        selected = mt5_module.symbol_select(requested_symbol, True)
        info = mt5_module.symbol_info(requested_symbol) if selected else None
    elif not getattr(info, "visible", False):
        mt5_module.symbol_select(requested_symbol, True)
        info = mt5_module.symbol_info(requested_symbol)
    if info is None:
        return None, None, "symbol_not_available"
    return requested_symbol, info, None


def collect_mt5_recent_spreads(
    *,
    symbols: list[str],
    lookback_hours: float,
) -> tuple[list[dict[str, object]], list[RecentSpreadSample], dict[str, object], dict[str, object], list[str]]:
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 Python package is required for recent spread comparison.") from exc

    if not mt5.initialize():
        raise RuntimeError("MetaTrader 5 initialize failed.")

    warnings: list[str] = []
    rows: list[dict[str, object]] = []
    samples: list[RecentSpreadSample] = []
    try:
        account = account_metadata(mt5.account_info())
        terminal = terminal_metadata(mt5.terminal_info())
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=lookback_hours)
        tick_flag = getattr(mt5, "COPY_TICKS_INFO", 1)

        for symbol in symbols:
            mt5_symbol_name, info, warning = select_mt5_symbol(mt5, symbol)
            if warning is not None or mt5_symbol_name is None or info is None:
                warnings.append(f"{symbol}: {warning or 'symbol_not_available'}")
                rows.append(summarize_recent_symbol(symbol=symbol, mt5_symbol_name="", point_size=None, digits=None, tick_spreads=[]))
                continue

            point_size = finite_positive(getattr(info, "point", None))
            digits = getattr(info, "digits", None)
            mt5.symbol_info_tick(mt5_symbol_name)
            ticks = mt5.copy_ticks_range(mt5_symbol_name, start_time, end_time, tick_flag)
            tick_spreads = spread_points_from_ticks(ticks if ticks is not None else [], point_size or 0.0)
            if not tick_spreads:
                warnings.append(f"{symbol}: no_valid_recent_ticks")
            rows.append(
                summarize_recent_symbol(
                    symbol=symbol,
                    mt5_symbol_name=mt5_symbol_name,
                    point_size=point_size,
                    digits=digits,
                    tick_spreads=tick_spreads,
                )
            )
            samples.extend(
                RecentSpreadSample(
                    symbol=symbol,
                    mt5_symbol_name=mt5_symbol_name,
                    time_server=timestamp,
                    spread_points=spread,
                )
                for timestamp, spread in tick_spreads
            )
    finally:
        mt5.shutdown()

    return rows, samples, account, terminal, warnings


def historical_rows_from_db(
    db_path: Path,
    *,
    symbols: list[str],
    timeframe: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[SpreadSource, list[dict[str, object]], list[str]]:
    source, samples = load_spread_samples(
        db_path,
        symbols=symbols,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
    )
    rows, skipped = summarize_by_symbol(source, symbols, samples)
    for row in rows:
        row["spread_source_table"] = source.table
        row["spread_source_column"] = source.column
    return source, rows, skipped


def csv_value(value: object) -> object:
    if value is None:
        return ""
    return value


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})


def output_dir_for_run(base_output_dir: Path, run_id: str, overwrite: bool) -> Path:
    output_dir = base_output_dir / run_id
    existing = [output_dir / filename for filename in PROTECTED_OUTPUT_FILES if (output_dir / filename).exists()]
    if existing and not overwrite:
        raise FileExistsError(f"MT5 spread comparison output already exists under {output_dir}. Pass --overwrite to regenerate it.")
    return output_dir


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_report(
    path: Path,
    *,
    run_id: str,
    broker_name: str,
    account_type: str,
    symbols: list[str],
    mt5_lookback_hours: float,
    historical_start_date: str | None,
    historical_end_date: str | None,
    spread_source: SpreadSource,
    account: dict[str, object],
    terminal: dict[str, object],
    comparison_rows: list[dict[str, object]],
    warnings: list[str],
) -> None:
    alerts = [row for row in comparison_rows if row.get("alert_flag") == "yes"]
    lines = [
        "# MT5 Recent Spread Comparison Report",
        "",
        "This report is research-only and diagnostic-only. It compares recent read-only MT5 tick spreads with local historical database spreads; it is not a trading signal.",
        "",
        "## Context",
        "",
        f"- Run ID: {run_id}",
        f"- Broker name: {broker_name}",
        f"- Account type: {account_type}",
        f"- Symbols checked: {' '.join(symbols)}",
        f"- MT5 lookback hours: {mt5_lookback_hours}",
        f"- Historical start date: {historical_start_date or 'not set'}",
        f"- Historical end date: {historical_end_date or 'not set'}",
        f"- Historical spread source: {spread_source.label}",
        "",
        "## MT5 Metadata",
        "",
        f"- Account login: {account.get('login_masked', '')}",
        f"- Account server: {account.get('server', '')}",
        f"- Account company: {account.get('company', '')}",
        f"- Terminal name: {terminal.get('name', '')}",
        f"- Terminal company: {terminal.get('company', '')}",
        f"- Terminal build: {terminal.get('build', '')}",
        f"- Terminal connected: {terminal.get('connected', '')}",
        "",
        "## Comparison",
        "",
        "| Symbol | MT5 p75 | DB p75 | p75 ratio | MT5 p90 | DB p90 | p90 ratio | Alert |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in comparison_rows:
        lines.append(
            "| {symbol} | {mt5_p75_points} | {historical_p75_points} | {mt5_vs_historical_p75_ratio} | "
            "{mt5_p90_points} | {historical_p90_points} | {mt5_vs_historical_p90_ratio} | {alert_flag} |".format(
                **{key: csv_value(value) for key, value in row.items()}
            )
        )
    lines.extend(["", "## Alerts", ""])
    if alerts:
        lines.extend(f"- {row['symbol']}: {row.get('alert_reason', '')}" for row in alerts)
    else:
        lines.append("- None.")
    lines.extend(["", "## Warnings", ""])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Recent MT5 spread higher than DB historical spread may indicate broker, session, or volatility-regime mismatch.",
            "- Recent MT5 spread lower than DB historical spread does not guarantee future low costs.",
            "- This comparison is diagnostic and must not be interpreted as a trading signal.",
            "",
            "## Next Steps",
            "",
            "- Use DB p75/p90/p95 configs for historical backtests.",
            "- Use MT5 comparison to check whether current account conditions look similar to the historical DB sample.",
            "- Do not use this diagnostic for live execution.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_comparison(args: argparse.Namespace, *, run_id: str | None = None) -> dict[str, Path]:
    symbols = normalize_symbols(args.symbols)
    if not symbols:
        raise ValueError("--symbols must include at least one symbol.")
    if args.mt5_lookback_hours <= 0:
        raise ValueError("--mt5-lookback-hours must be greater than zero.")
    if args.spread_alert_ratio <= 0:
        raise ValueError("--spread-alert-ratio must be greater than zero.")

    run_id = run_id or current_run_id()
    output_dir = output_dir_for_run(args.output_dir, run_id, args.overwrite)
    mt5_rows, mt5_samples, account, terminal, mt5_warnings = collect_mt5_recent_spreads(
        symbols=symbols,
        lookback_hours=args.mt5_lookback_hours,
    )
    source, historical_rows, skipped_symbols = historical_rows_from_db(
        args.db_path,
        symbols=symbols,
        timeframe=args.timeframe,
        start_date=args.historical_start_date,
        end_date=args.historical_end_date,
    )
    comparison_rows = compare_spread_rows(mt5_rows, historical_rows, symbols, args.spread_alert_ratio)
    by_hour_rows = summarize_recent_by_hour(mt5_samples)
    warnings = list(mt5_warnings)
    warnings.extend(f"{symbol}: missing_historical_samples" for symbol in skipped_symbols)

    mt5_path = output_dir / MT5_RECENT_BY_SYMBOL_FILE
    historical_path = output_dir / HISTORICAL_BY_SYMBOL_FILE
    comparison_path = output_dir / SPREAD_COMPARISON_FILE
    by_hour_path = output_dir / MT5_BY_HOUR_FILE
    report_path = output_dir / REPORT_FILE

    write_csv(
        mt5_path,
        mt5_rows,
        [
            "symbol",
            "mt5_symbol_name",
            "point_size",
            "digits",
            "tick_count",
            "spread_mean_points",
            "spread_median_points",
            "spread_p75_points",
            "spread_p90_points",
            "spread_p95_points",
            "spread_min_points",
            "spread_max_points",
            "first_tick_time",
            "last_tick_time",
        ],
    )
    write_csv(
        historical_path,
        historical_rows,
        [
            "symbol",
            "spread_count",
            "spread_mean_points",
            "spread_median_points",
            "spread_p75_points",
            "spread_p90_points",
            "spread_p95_points",
            "spread_min_points",
            "spread_max_points",
            "first_timestamp",
            "last_timestamp",
            "spread_source_table",
            "spread_source_column",
        ],
    )
    write_csv(
        comparison_path,
        comparison_rows,
        [
            "symbol",
            "mt5_tick_count",
            "historical_spread_count",
            "mt5_p50_points",
            "historical_p50_points",
            "mt5_p75_points",
            "historical_p75_points",
            "mt5_p90_points",
            "historical_p90_points",
            "mt5_p95_points",
            "historical_p95_points",
            "mt5_vs_historical_p75_ratio",
            "mt5_vs_historical_p90_ratio",
            "mt5_vs_historical_p95_ratio",
            "alert_flag",
            "alert_reason",
        ],
    )
    write_csv(
        by_hour_path,
        by_hour_rows,
        [
            "symbol",
            "hour",
            "tick_count",
            "spread_mean_points",
            "spread_median_points",
            "spread_p75_points",
            "spread_p90_points",
            "spread_p95_points",
            "spread_min_points",
            "spread_max_points",
        ],
    )
    write_report(
        report_path,
        run_id=run_id,
        broker_name=args.broker_name,
        account_type=args.account_type,
        symbols=symbols,
        mt5_lookback_hours=args.mt5_lookback_hours,
        historical_start_date=args.historical_start_date,
        historical_end_date=args.historical_end_date,
        spread_source=source,
        account=account,
        terminal=terminal,
        comparison_rows=comparison_rows,
        warnings=warnings,
    )

    print(f"Output directory: {output_dir.resolve()}")
    print(f"Historical spread source: {source.label}")
    print(f"Symbols checked: {' '.join(symbols)}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")

    return {
        "mt5_recent_spread_by_symbol": mt5_path,
        "historical_spread_by_symbol": historical_path,
        "spread_comparison": comparison_path,
        "mt5_spread_by_hour": by_hour_path,
        "spread_comparison_report": report_path,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare recent read-only MT5 spreads with local SQLite historical spread statistics."
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--historical-start-date")
    parser.add_argument("--historical-end-date")
    parser.add_argument("--mt5-lookback-hours", type=float, default=24.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--broker-name", default="Pepperstone")
    parser.add_argument("--account-type", default="Razor")
    parser.add_argument("--spread-alert-ratio", type=float, default=1.5)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main() -> int:
    try:
        run_comparison(parse_args())
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError, sqlite3.Error, OSError) as exc:
        print(f"MT5 spread comparison failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
