"""Recompute fixed-candidate parity features from MT5 raw M15 bars.

This exporter is deliberately offline and read-only. It consumes a raw bar CSV
created by the MQL5 raw-bars exporter, recomputes the Python feature contract
from those bars, and writes a parity CSV suitable for comparison with the
signal-only MQL5 prototype. It does not open the project database, connect to
MT5, build broker payloads, or perform trade operations.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STRATEGY_SPEC = (
    BASE_DIR
    / "config"
    / "strategy_specs"
    / "gbpusd_short_h10_1_5_off_hours_strategy_spec.json"
)

RAW_FIELDNAMES = [
    "time_server",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
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

EXPECTED_BAR_DELTA = timedelta(minutes=15)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_time_server(value: str) -> datetime:
    for date_format in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
    ):
        try:
            return datetime.strptime(str(value).strip(), date_format)
        except ValueError:
            continue
    raise ValueError(f"Unsupported time_server format: {value!r}")


def format_time_server(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def safe_int(value: Any) -> int | None:
    parsed = safe_float(value)
    if parsed is None:
        return None
    return int(parsed)


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def true_range(high_price: float, low_price: float, previous_close: float | None) -> float:
    candle_range = high_price - low_price
    if previous_close is None:
        return candle_range
    return max(
        candle_range,
        abs(high_price - previous_close),
        abs(low_price - previous_close),
    )


def rolling_mean(values: list[float | int | None], index: int, window: int) -> float | None:
    if index + 1 < window:
        return None
    window_values = values[index - window + 1 : index + 1]
    if any(value is None for value in window_values):
        return None
    return sum(float(value) for value in window_values) / window


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


def hour_session(timestamp: datetime) -> str:
    if 0 <= timestamp.hour <= 7:
        return "Asia"
    if 8 <= timestamp.hour <= 13:
        return "London"
    if 14 <= timestamp.hour <= 21:
        return "New_York"
    return "Off_hours"


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


def parse_hhmm(value: str) -> tuple[int, int]:
    parts = str(value).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Expected HH:MM time value, got: {value!r}")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Invalid HH:MM time value: {value!r}")
    return hour, minute


def same_day_time(timestamp: datetime, hhmm: str) -> datetime:
    hour, minute = parse_hhmm(hhmm)
    return timestamp.replace(hour=hour, minute=minute, second=0, microsecond=0)


def lifecycle_policy(spec: dict[str, Any]) -> dict[str, Any]:
    lifecycle = spec.get("trade_lifecycle", {})
    return {
        "no_weekend_hold": bool(lifecycle.get("no_weekend_hold", False)),
        "forced_friday_exit_enabled": bool(lifecycle.get("forced_friday_exit_enabled", False)),
        "friday_last_entry_time_server": str(
            lifecycle.get("friday_last_entry_time_server", "23:15")
        ),
        "friday_forced_flat_time_server": str(
            lifecycle.get("friday_forced_flat_time_server", "23:45")
        ),
    }


def entry_allowed_by_lifecycle(timestamp: datetime, spec: dict[str, Any]) -> bool:
    policy = lifecycle_policy(spec)
    if not policy["no_weekend_hold"]:
        return True
    if timestamp.weekday() != 4:
        return True
    last_entry_time = same_day_time(timestamp, policy["friday_last_entry_time_server"])
    return timestamp <= last_entry_time


def is_weekend_gap(previous_time: datetime, current_time: datetime) -> bool:
    cursor = previous_time + EXPECTED_BAR_DELTA
    while cursor < current_time:
        if cursor.weekday() in {5, 6}:
            return True
        cursor += EXPECTED_BAR_DELTA
    return previous_time.weekday() == 4 and current_time.weekday() == 0


def read_raw_bar_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = [column for column in RAW_FIELDNAMES if column not in fieldnames]
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path} contains no raw bar rows.")

    parsed_rows: list[dict[str, Any]] = []
    seen_times: set[datetime] = set()
    for row_index, row in enumerate(rows):
        timestamp = parse_time_server(str(row.get("time_server", "")))
        if timestamp in seen_times:
            raise ValueError(f"Duplicate raw time_server in {path}: {format_time_server(timestamp)}")
        seen_times.add(timestamp)
        open_price = safe_float(row.get("open"))
        high_price = safe_float(row.get("high"))
        low_price = safe_float(row.get("low"))
        close_price = safe_float(row.get("close"))
        tick_volume = safe_int(row.get("tick_volume"))
        spread = safe_int(row.get("spread"))
        if None in {open_price, high_price, low_price, close_price, tick_volume, spread}:
            raise ValueError(f"Raw row {row_index} has invalid OHLCV/spread values.")
        parsed_rows.append(
            {
                "time_server": timestamp,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "tick_volume": tick_volume,
                "spread": spread,
            }
        )

    return sorted(parsed_rows, key=lambda row: row["time_server"])


def detect_gaps(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for previous, current in zip(raw_rows, raw_rows[1:]):
        previous_time = previous["time_server"]
        current_time = current["time_server"]
        delta = current_time - previous_time
        if delta <= EXPECTED_BAR_DELTA:
            continue
        missing_bar_count = int(delta / EXPECTED_BAR_DELTA) - 1
        gaps.append(
            {
                "previous_time_server": format_time_server(previous_time),
                "current_time_server": format_time_server(current_time),
                "gap_minutes": int(delta.total_seconds() // 60),
                "missing_m15_bar_count": missing_bar_count,
                "weekend_gap": is_weekend_gap(previous_time, current_time),
            }
        )
    return gaps


def max_exit_time_for_row(
    *,
    timestamp: datetime,
    raw_times: set[datetime],
    holding_bars: int,
    spec: dict[str, Any],
) -> str:
    tenth_future_bar = timestamp + holding_bars * EXPECTED_BAR_DELTA
    candidates: list[datetime] = []
    if tenth_future_bar in raw_times:
        candidates.append(tenth_future_bar)

    policy = lifecycle_policy(spec)
    if (
        policy["no_weekend_hold"]
        and policy["forced_friday_exit_enabled"]
        and timestamp.weekday() == 4
    ):
        forced_flat_time = same_day_time(timestamp, policy["friday_forced_flat_time_server"])
        if timestamp <= forced_flat_time:
            candidates.append(forced_flat_time)

    return format_time_server(min(candidates)) if candidates else ""


def build_raw_source_parity_rows(
    raw_rows: list[dict[str, Any]],
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    close_lower, close_upper, close_required = feature_threshold(spec, "close_to_ma_fast_atr_20")
    volume_lower, volume_upper, volume_required = feature_threshold(spec, "tick_volume_percentile_100")
    holding_bars = max_holding_bars(spec)
    raw_times = {row["time_server"] for row in raw_rows}
    closes = [row["close"] for row in raw_rows]
    tick_volumes = [row["tick_volume"] for row in raw_rows]
    true_ranges = [
        true_range(
            high_price=float(row["high"]),
            low_price=float(row["low"]),
            previous_close=closes[index - 1] if index >= 1 else None,
        )
        for index, row in enumerate(raw_rows)
    ]
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows):
        atr_20 = rolling_mean(true_ranges, index, 20)
        ma_fast = rolling_mean(closes, index, 20)
        tick_volume_percentile_100 = rolling_percentile_rank(tick_volumes, index, 100)
        close_to_ma_fast_atr_20 = safe_ratio(
            row["close"] - ma_fast if ma_fast is not None else None,
            atr_20,
        )
        if (
            atr_20 is None
            or ma_fast is None
            or tick_volume_percentile_100 is None
            or close_to_ma_fast_atr_20 is None
        ):
            continue

        close_bucket = bucket_for_value(close_to_ma_fast_atr_20, close_lower, close_upper)
        volume_bucket = bucket_for_value(tick_volume_percentile_100, volume_lower, volume_upper)
        current_hour_session = hour_session(row["time_server"])
        signal_bool = (
            current_hour_session == spec["session"]["required_value"]
            and close_bucket == close_required
            and volume_bucket == volume_required
            and float(row["spread"]) <= float(spec["spread_policy"]["max_spread_points"])
            and float(row["close"]) > 0
            and atr_20 > 0
        )
        entry_reference_price: float | None = None
        sl_price_preview: float | None = None
        tp_price_preview: float | None = None
        if signal_bool:
            entry_reference_price = row["close"]
            if spec["direction"] == "short":
                sl_price_preview = row["close"] + float(spec["sl_tp"]["sl_atr"]) * atr_20
                tp_price_preview = row["close"] - float(spec["sl_tp"]["tp_atr"]) * atr_20
            else:
                sl_price_preview = row["close"] - float(spec["sl_tp"]["sl_atr"]) * atr_20
                tp_price_preview = row["close"] + float(spec["sl_tp"]["tp_atr"]) * atr_20

        rows.append(
            {
                "time_server": format_time_server(row["time_server"]),
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "tick_volume": row["tick_volume"],
                "spread": row["spread"],
                "atr_20": atr_20,
                "ma_fast": ma_fast,
                "close_to_ma_fast_atr_20": close_to_ma_fast_atr_20,
                "tick_volume_percentile_100": tick_volume_percentile_100,
                "hour_session": current_hour_session,
                "close_to_ma_fast_atr_20_bucket": close_bucket,
                "tick_volume_percentile_100_bucket": volume_bucket,
                "signal_bool": signal_bool,
                "entry_reference_price": entry_reference_price,
                "sl_price_preview": sl_price_preview,
                "tp_price_preview": tp_price_preview,
                "max_holding_bars": holding_bars,
                "max_exit_time_server": max_exit_time_for_row(
                    timestamp=row["time_server"],
                    raw_times=raw_times,
                    holding_bars=holding_bars,
                    spec=spec,
                ),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output CSV already exists: {path}. Use --overwrite to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in EXPORT_FIELDNAMES})


def write_diagnostics(path: Path, diagnostics: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Diagnostics JSON already exists: {path}. Use --overwrite to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8")


def export_raw_source_parity_dataset(
    *,
    strategy_spec_path: Path,
    mt5_raw_csv: Path,
    output_csv: Path,
    overwrite: bool,
    diagnostics_json: Path | None = None,
) -> dict[str, Any]:
    spec = read_json(strategy_spec_path)
    raw_rows = read_raw_bar_rows(mt5_raw_csv)
    gaps = detect_gaps(raw_rows)
    parity_rows = build_raw_source_parity_rows(raw_rows, spec)
    write_csv(output_csv, parity_rows, overwrite=overwrite)
    diagnostics_path = diagnostics_json or output_csv.with_suffix(".diagnostics.json")
    diagnostics = {
        "strategy_spec": str(strategy_spec_path),
        "mt5_raw_csv": str(mt5_raw_csv),
        "output_csv": str(output_csv),
        "raw_rows_read": len(raw_rows),
        "rows_exported": len(parity_rows),
        "signal_rows": sum(1 for row in parity_rows if row["signal_bool"] is True),
        "gap_count": len(gaps),
        "non_weekend_gap_count": sum(1 for gap in gaps if not gap["weekend_gap"]),
        "gaps": gaps,
        "lifecycle_policy": lifecycle_policy(spec),
        "feature_source": "mt5_raw_bars_csv",
        "database_read_performed": False,
        "mt5_connection_performed": False,
        "order_check_performed": False,
        "order_send_performed": False,
        "trade_operation_performed": False,
    }
    write_diagnostics(diagnostics_path, diagnostics, overwrite=overwrite)
    return diagnostics | {"diagnostics_json": str(diagnostics_path)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recompute fixed-candidate EA parity features from an MT5 raw-bar CSV."
    )
    parser.add_argument("--strategy-spec", type=Path, default=DEFAULT_STRATEGY_SPEC)
    parser.add_argument("--mt5-raw-csv", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--diagnostics-json", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = export_raw_source_parity_dataset(
            strategy_spec_path=args.strategy_spec,
            mt5_raw_csv=args.mt5_raw_csv,
            output_csv=args.output_csv,
            diagnostics_json=args.diagnostics_json,
            overwrite=bool(args.overwrite),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Fixed-candidate MT5 raw-source parity export failed: {exc}")
        return 1
    print("Fixed-candidate MT5 raw-source parity export complete.")
    print(f"Raw rows read: {summary['raw_rows_read']}")
    print(f"Rows exported: {summary['rows_exported']}")
    print(f"Signal rows: {summary['signal_rows']}")
    print(f"Gap count: {summary['gap_count']}")
    print(f"Non-weekend gap count: {summary['non_weekend_gap_count']}")
    print(f"Output CSV: {summary['output_csv']}")
    print(f"Diagnostics JSON: {summary['diagnostics_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
