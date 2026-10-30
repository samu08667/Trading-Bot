"""Research-only regime diagnostics for existing preferred TP/SL branches.

This script reads existing branch output rows, optionally replays the fixed
historical TP/SL path diagnostic against ``ml_dataset``, and groups the
resulting outcomes by regime columns that already exist. It does not create
new feature columns, TP/SL settings, operational rules, sizing, or broker
actions.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import math
from statistics import mean
import re
import sys
from typing import Any, Callable


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from regime_classification import with_regime_labels_for_rows
    from research_costs import load_cost_config
    from research_metrics import csv_safe_value, parse_metric_timestamp, safe_float
    from run_tp_sl_path_backtests import (
        DATABASE_PATH,
        DEFAULT_ATR_COLUMN,
        DEFAULT_SAME_BAR_POLICY,
        PathConfig,
        load_path_rows,
        metric_delta,
        predicate_for_filters,
        simulate_path_exit,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.regime_classification import with_regime_labels_for_rows
    from scripts.research_costs import load_cost_config
    from scripts.research_metrics import csv_safe_value, parse_metric_timestamp, safe_float
    from scripts.run_tp_sl_path_backtests import (
        DATABASE_PATH,
        DEFAULT_ATR_COLUMN,
        DEFAULT_SAME_BAR_POLICY,
        PathConfig,
        load_path_rows,
        metric_delta,
        predicate_for_filters,
        simulate_path_exit,
    )


DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "regime_filter_diagnostics"
DEFAULT_COMBINATION_ROOT = BASE_DIR / "reports" / "preferred_feature_combination_backtests"
DEFAULT_TP_SL_ROOT = BASE_DIR / "reports" / "tp_sl_path_backtests"
DEFAULT_PATH_FRAGMENTS = (
    "preferred_2atr_1atr_p75",
    "preferred_1_5atr_1atr_p75",
)
DEFAULT_MIN_TRADES = 200
INPUT_FILE_NAMES = {
    "combination_backtest_detail.csv",
    "tp_sl_path_backtest_detail.csv",
    "tp_sl_path_backtest_summary.csv",
}

CSV_FILE = "regime_filter_diagnostics.csv"
REPORT_FILE = "regime_filter_diagnostics.md"

CLASS_NO_EVIDENCE = "NO_EVIDENCE"
CLASS_WEAK = "WEAK"
CLASS_REVIEW = "REGIME_DEPENDENT_REVIEW"
CLASS_INSUFFICIENT = "INSUFFICIENT_TRADES"

MISSING_VALUE = "__MISSING__"
BLANK_VALUE = "__BLANK__"


@dataclass(frozen=True)
class RegimeExpectation:
    label: str
    columns: tuple[str, ...]


REGIME_EXPECTATIONS = (
    RegimeExpectation("session", ("session",)),
    RegimeExpectation("hour_session", ("hour_session",)),
    RegimeExpectation(
        "spread_liquidity_regime",
        (
            "spread_liquidity_regime",
            "spread_regime",
            "spread_bucket",
            "spread_tercile",
            "spread_to_volume_regime",
            "spread_to_volume_bucket",
            "spread_to_atr_regime",
            "spread_to_atr_bucket",
        ),
    ),
    RegimeExpectation(
        "volatility_regime",
        (
            "volatility_range_regime",
            "volatility_regime",
            "volatility_bucket",
            "volatility_20_regime",
            "volatility_20_bucket",
            "atr_regime",
            "atr_bucket",
        ),
    ),
    RegimeExpectation(
        "range_regime",
        (
            "range_regime",
            "range_bucket",
            "range_to_atr_20_regime",
            "range_to_atr_20_bucket",
        ),
    ),
    RegimeExpectation(
        "volume_liquidity_regime",
        (
            "volume_liquidity_regime",
            "volume_regime",
            "volume_bucket",
            "tick_volume_regime",
            "tick_volume_bucket",
            "liquidity_regime",
            "volume_spike_20",
            "volume_dry_up_20",
            "volume_vs_session_avg_regime",
            "volume_vs_session_avg_bucket",
        ),
    ),
    RegimeExpectation(
        "news blackout / timing",
        (
            "blackout_window_30m",
            "blackout_window_60m",
            "post_news_window_30m",
            "post_news_window_60m",
            "has_news_next_30m",
            "has_news_next_60m",
            "has_high_impact_news_next_30m",
            "has_high_impact_news_next_60m",
            "has_high_impact_news_prev_30m",
            "has_high_impact_news_prev_60m",
            "news_count_next_60m",
            "news_count_prev_60m",
            "minutes_to_next_news",
            "minutes_from_last_news",
            "next_news_importance",
            "last_news_importance",
        ),
    ),
)


FIELDNAMES = [
    "target_family",
    "horizon",
    "group",
    "direction",
    "symbol",
    "regime_column",
    "regime_value",
    "tested_rows",
    "trades_count",
    "mean_R",
    "profit_factor_R",
    "tp_hit_rate",
    "sl_hit_rate",
    "timeout_rate",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "baseline_mean_R",
    "baseline_profit_factor_R",
    "mean_R_vs_baseline",
    "profit_factor_R_vs_baseline",
    "baseline_comparison",
    "classification_suggestion",
    "source_files",
    "notes",
]


@dataclass(frozen=True)
class LoadedCsv:
    path: Path
    rows: list[dict[str, str]]
    headers: list[str]
    schema_kind: str


@dataclass(frozen=True)
class SourceRow:
    path: Path
    row_number: int
    row: dict[str, str]
    schema_kind: str
    target_family: str
    horizon: str
    group: str
    direction: str
    symbol: str
    timeframe: str


@dataclass
class AggregateStats:
    trades_count: int = 0
    tp_hit_count: int = 0
    sl_hit_count: int = 0
    timeout_count: int = 0
    sum_R: float = 0.0
    profit_R: float = 0.0
    loss_R: float = 0.0
    monthly_R: dict[tuple[int, int], float] = field(default_factory=dict)
    quarterly_R: dict[tuple[int, int], float] = field(default_factory=dict)

    def update_outcome(self, outcome: Any) -> None:
        value = finite_value(getattr(outcome, "selected_R", None))
        if value is None:
            return
        self.trades_count += 1
        self.sum_R += value
        if value > 0:
            self.profit_R += value
        elif value < 0:
            self.loss_R += abs(value)
        exit_reason = str(getattr(outcome, "exit_reason", "") or "")
        if exit_reason == "tp":
            self.tp_hit_count += 1
        elif exit_reason == "sl":
            self.sl_hit_count += 1
        elif exit_reason == "timeout":
            self.timeout_count += 1
        self._update_period(self.monthly_R, getattr(outcome, "time_server", None), "month", value)
        self._update_period(self.quarterly_R, getattr(outcome, "time_server", None), "quarter", value)

    def merge(self, other: "AggregateStats", *, multiplier: int = 1) -> None:
        if multiplier <= 0 or other.trades_count <= 0:
            return
        self.trades_count += other.trades_count * multiplier
        self.tp_hit_count += other.tp_hit_count * multiplier
        self.sl_hit_count += other.sl_hit_count * multiplier
        self.timeout_count += other.timeout_count * multiplier
        self.sum_R += other.sum_R * multiplier
        self.profit_R += other.profit_R * multiplier
        self.loss_R += other.loss_R * multiplier
        for key, value in other.monthly_R.items():
            self.monthly_R[key] = self.monthly_R.get(key, 0.0) + value * multiplier
        for key, value in other.quarterly_R.items():
            self.quarterly_R[key] = self.quarterly_R.get(key, 0.0) + value * multiplier

    def as_metrics(self) -> dict[str, object]:
        count = self.trades_count
        if count <= 0:
            return {
                "trades_count": 0,
                "tp_hit_rate": None,
                "sl_hit_rate": None,
                "timeout_rate": None,
                "mean_R": None,
                "profit_factor_R": None,
                "monthly_positive_ratio": None,
                "quarterly_positive_ratio": None,
            }
        return {
            "trades_count": count,
            "tp_hit_rate": self.tp_hit_count / count,
            "sl_hit_rate": self.sl_hit_count / count,
            "timeout_rate": self.timeout_count / count,
            "mean_R": self.sum_R / count,
            "profit_factor_R": self.profit_factor_R(),
            "monthly_positive_ratio": positive_period_ratio(self.monthly_R),
            "quarterly_positive_ratio": positive_period_ratio(self.quarterly_R),
        }

    @staticmethod
    def _update_period(
        periods: dict[tuple[int, int], float],
        timestamp_value: object,
        period: str,
        value: float,
    ) -> None:
        key = aggregate_period_key(timestamp_value, period)
        if key is None:
            return
        periods[key] = periods.get(key, 0.0) + value

    def profit_factor_R(self) -> float | None:
        if self.loss_R == 0:
            return None if self.profit_R == 0 else float("inf")
        return self.profit_R / self.loss_R


@dataclass
class OutcomeBucket:
    target_family: str
    horizon: str
    group: str
    direction: str
    symbol: str
    regime_column: str
    regime_value: str
    source_files: set[str] = field(default_factory=set)
    source_rows: set[tuple[str, int]] = field(default_factory=set)
    stats: AggregateStats = field(default_factory=AggregateStats)
    baseline_stats: AggregateStats = field(default_factory=AggregateStats)
    notes: set[str] = field(default_factory=set)


RowLoader = Callable[[Path, str, str], list[dict[str, object]]]


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def finite_value(value: object) -> float | None:
    parsed = safe_float(value)
    return parsed if parsed is not None and math.isfinite(parsed) else None


def safe_int(value: object) -> int:
    parsed = finite_value(value)
    return int(parsed) if parsed is not None else 0


def aggregate_period_key(timestamp_value: object, period: str) -> tuple[int, int] | None:
    timestamp = parse_metric_timestamp(timestamp_value)
    if timestamp is None:
        return None
    if period == "month":
        return timestamp.year, timestamp.month
    if period == "quarter":
        return timestamp.year, (timestamp.month - 1) // 3 + 1
    raise ValueError(f"Unsupported period: {period}")


def positive_period_ratio(period_sums: dict[tuple[int, int], float]) -> float | None:
    if not period_sums:
        return None
    values = [period_sums[key] for key in sorted(period_sums)]
    return sum(1 for value in values if value > 0) / len(values)


def read_csv_with_headers(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe_value(row.get(field)) for field in FIELDNAMES})


def schema_kind(headers: list[str]) -> str:
    header_set = set(headers)
    if {"selected_R", "exit_reason"}.issubset(header_set):
        return "tp_sl_trade_detail"
    if {"mean_R", "trades_count"}.issubset(header_set):
        return "tp_sl_summary"
    if {"mean_return", "trades_count"}.issubset(header_set):
        return "combination_summary"
    return "unknown"


def path_matches_fragments(path: Path, fragments: tuple[str, ...]) -> bool:
    if not fragments:
        return True
    text = str(path).lower()
    return any(fragment.lower() in text for fragment in fragments)


def collect_input_paths(input_roots: list[Path], fragments: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in input_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            if path.name not in INPUT_FILE_NAMES:
                continue
            if not path_matches_fragments(path, fragments):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(path)
    return sorted(paths, key=lambda item: str(item).lower())


def load_csv_inputs(paths: list[Path]) -> list[LoadedCsv]:
    loaded: list[LoadedCsv] = []
    summary_parent_dirs = {
        path.parent.resolve()
        for path in paths
        if path.name == "tp_sl_path_backtest_summary.csv"
    }
    for path in paths:
        rows, headers = read_csv_with_headers(path)
        kind = schema_kind(headers)
        if (
            path.name == "tp_sl_path_backtest_detail.csv"
            and kind == "tp_sl_summary"
            and path.parent.resolve() in summary_parent_dirs
        ):
            continue
        loaded.append(LoadedCsv(path=path, rows=rows, headers=headers, schema_kind=kind))
    return loaded


def normalize_decimal_token(value: object) -> str:
    parsed = finite_value(value)
    if parsed is None:
        return ""
    if parsed.is_integer():
        return str(int(parsed))
    return str(parsed).replace(".", "_")


def infer_target_family(row: dict[str, str], path: Path) -> str:
    explicit = str(row.get("target_family") or "").strip()
    if explicit:
        return explicit
    text = str(path).lower()
    if "preferred_1_5atr_1atr" in text:
        return "preferred_1_5atr_1atr_hit_first"
    if "preferred_2atr_1atr" in text:
        return "preferred_2atr_1atr_hit_first"
    tp_token = normalize_decimal_token(row.get("tp_atr"))
    sl_token = normalize_decimal_token(row.get("sl_atr"))
    if tp_token and sl_token:
        return f"preferred_{tp_token}atr_{sl_token}atr_hit_first"
    return "unknown"


def infer_horizon(row: dict[str, str], path: Path) -> str:
    explicit = str(row.get("horizon") or "").strip()
    if explicit:
        return explicit
    match = re.search(r"_h(\d+)_", str(path).lower())
    return match.group(1) if match else ""


def infer_group(row: dict[str, str], path: Path, symbol: str) -> str:
    explicit = str(row.get("group") or row.get("asset_group") or "").strip()
    if explicit:
        return explicit.upper()
    text = str(path).lower()
    if "_xauusd_" in text or symbol.upper() == "XAUUSD":
        return "XAUUSD"
    if "_fx_" in text or (symbol and symbol.upper() != "XAUUSD"):
        return "FX"
    return ""


def infer_direction(row: dict[str, str], path: Path) -> str:
    explicit = str(row.get("direction") or "").strip().lower()
    if explicit in {"long", "short"}:
        return explicit
    for part in reversed(path.parts):
        lowered = part.lower()
        if lowered in {"long", "short"}:
            return lowered
    return ""


def infer_symbol(row: dict[str, str], path: Path) -> str:
    explicit = str(row.get("symbol") or "").strip().upper()
    if explicit:
        return explicit
    match = re.search(r"_(xauusd|eurusd|gbpusd|usdjpy|audusd|usdcad|usdchf)_", str(path).lower())
    return match.group(1).upper() if match else ""


def infer_timeframe(row: dict[str, str], path: Path) -> str:
    explicit = str(row.get("timeframe") or "").strip().upper()
    if explicit:
        return explicit
    match = re.search(r"_(m\d+|h\d+)_", str(path).lower())
    return match.group(1).upper() if match else "M15"


def source_rows_from_loaded(loaded: list[LoadedCsv]) -> list[SourceRow]:
    source_rows: list[SourceRow] = []
    for item in loaded:
        for index, row in enumerate(item.rows, start=1):
            scope = str(row.get("scope") or "").strip().lower()
            if scope.startswith("baseline"):
                continue
            symbol = infer_symbol(row, item.path)
            source_rows.append(
                SourceRow(
                    path=item.path,
                    row_number=index,
                    row=row,
                    schema_kind=item.schema_kind,
                    target_family=infer_target_family(row, item.path),
                    horizon=infer_horizon(row, item.path),
                    group=infer_group(row, item.path, symbol),
                    direction=infer_direction(row, item.path),
                    symbol=symbol,
                    timeframe=infer_timeframe(row, item.path),
                )
            )
    return source_rows


def split_filters(value: object) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text or text == "ALL_VALID_ROWS":
        return ()
    return tuple(part.strip() for part in text.split("|") if part.strip())


def filters_from_source_row(row: dict[str, str]) -> tuple[str, ...]:
    filters = split_filters(row.get("filters"))
    if filters:
        return filters
    return tuple(
        item
        for item in (
            str(row.get("source_scenario_1") or row.get("scenario_1") or "").strip(),
            str(row.get("source_scenario_2") or row.get("scenario_2") or "").strip(),
        )
        if item
    )


def path_config_from_source(row: SourceRow, min_trades: int) -> PathConfig | None:
    horizon = safe_int(row.horizon or row.row.get("horizon"))
    tp_atr = finite_value(row.row.get("tp_atr"))
    sl_atr = finite_value(row.row.get("sl_atr"))
    if not row.symbol or not row.direction or horizon <= 0 or tp_atr is None or sl_atr is None:
        return None
    return PathConfig(
        symbol=row.symbol,
        timeframe=row.timeframe,
        direction=row.direction,
        horizon=horizon,
        tp_atr=tp_atr,
        sl_atr=sl_atr,
        atr_column=str(row.row.get("atr_column") or DEFAULT_ATR_COLUMN).strip(),
        same_bar_policy=str(row.row.get("same_bar_policy") or DEFAULT_SAME_BAR_POLICY).strip(),
        filters=filters_from_source_row(row.row),
        cost_mode=str(row.row.get("cost_mode") or "estimated").strip(),
        return_mode=str(row.row.get("return_mode") or "net").strip(),
        min_trades=min_trades,
    )


def known_regime_columns(headers: set[str], explicit_columns: tuple[str, ...]) -> tuple[list[str], list[str]]:
    if explicit_columns:
        available = [column for column in explicit_columns if column in headers]
        missing = [column for column in explicit_columns if column not in headers]
        return available, missing

    available: list[str] = []
    missing_labels: list[str] = []
    seen: set[str] = set()
    for expectation in REGIME_EXPECTATIONS:
        found = [column for column in expectation.columns if column in headers]
        if not found:
            missing_labels.append(expectation.label)
            continue
        for column in found:
            if column not in seen:
                seen.add(column)
                available.append(column)
    return available, missing_labels


def regime_value(value: object) -> str:
    text = str(value if value is not None else "").strip()
    return text if text else BLANK_VALUE


def unit_key(row: SourceRow) -> tuple[str, str, str, str, str]:
    return row.target_family, row.horizon, row.group, row.direction, row.symbol


def source_file_label(path: Path) -> str:
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def add_missing_rows(
    diagnostics: list[dict[str, object]],
    *,
    units: dict[tuple[str, str, str, str, str], int],
    missing_columns_by_unit: dict[tuple[str, str, str, str, str], set[str]],
    note: str,
) -> None:
    for key in sorted(missing_columns_by_unit):
        target_family, horizon, group, direction, symbol = key
        for column in sorted(missing_columns_by_unit[key]):
            diagnostics.append(
                {
                    "target_family": target_family,
                    "horizon": horizon,
                    "group": group,
                    "direction": direction,
                    "symbol": symbol,
                    "regime_column": column,
                    "regime_value": MISSING_VALUE,
                    "tested_rows": units.get(key, 0),
                    "trades_count": "",
                    "classification_suggestion": CLASS_NO_EVIDENCE,
                    "notes": note,
                }
            )


def add_no_evidence_column_rows(
    diagnostics: list[dict[str, object]],
    *,
    units: dict[tuple[str, str, str, str, str], int],
    columns_by_unit: dict[tuple[str, str, str, str, str], set[str]],
    note: str,
) -> None:
    add_missing_rows(
        diagnostics,
        units=units,
        missing_columns_by_unit=columns_by_unit,
        note=note,
    )


def filter_regime_columns_by_cardinality(
    rows: list[dict[str, object]],
    columns: list[str],
    max_regime_values: int,
) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    skipped: list[str] = []
    for column in columns:
        values: set[str] = set()
        for row in rows:
            values.add(regime_value(row.get(column)))
            if len(values) > max_regime_values:
                skipped.append(column)
                break
        else:
            kept.append(column)
    return kept, skipped


def classification_for_metrics(metrics: dict[str, object], min_trades: int) -> str:
    trades_count = safe_int(metrics.get("trades_count"))
    mean_r = finite_value(metrics.get("mean_R"))
    profit_factor = finite_value(metrics.get("profit_factor_R"))
    has_metric = any(
        finite_value(metrics.get(column)) is not None
        for column in ("mean_R", "profit_factor_R", "tp_hit_rate", "sl_hit_rate", "timeout_rate")
    )
    if not has_metric:
        return CLASS_NO_EVIDENCE
    if trades_count < min_trades:
        return CLASS_INSUFFICIENT
    mean_delta = finite_value(metrics.get("mean_R_vs_baseline"))
    profit_delta = finite_value(metrics.get("profit_factor_R_vs_baseline"))
    monthly = finite_value(metrics.get("monthly_positive_ratio"))
    quarterly = finite_value(metrics.get("quarterly_positive_ratio"))
    baseline_ok = (
        (mean_delta is None or mean_delta > 0)
        and (profit_delta is None or profit_delta > 0)
    )
    periods_ok = (
        (monthly is None or monthly >= 0.5)
        and (quarterly is None or quarterly >= 0.5)
    )
    if (
        mean_r is not None
        and profit_factor is not None
        and mean_r > 0
        and profit_factor > 1.0
        and baseline_ok
        and periods_ok
    ):
        return CLASS_REVIEW
    return CLASS_WEAK


def baseline_comparison_text(metrics: dict[str, object]) -> str:
    parts: list[str] = []
    mean_delta = finite_value(metrics.get("mean_R_vs_baseline"))
    profit_delta = finite_value(metrics.get("profit_factor_R_vs_baseline"))
    if mean_delta is not None:
        parts.append(f"mean_R_vs_baseline={mean_delta:.6f}")
    if profit_delta is not None:
        parts.append(f"profit_factor_R_vs_baseline={profit_delta:.6f}")
    return "; ".join(parts)


def bucket_to_row(bucket: OutcomeBucket, min_trades: int) -> dict[str, object]:
    metrics = bucket.stats.as_metrics()
    baseline = bucket.baseline_stats.as_metrics() if bucket.baseline_stats.trades_count else {}
    metrics["baseline_mean_R"] = baseline.get("mean_R")
    metrics["baseline_profit_factor_R"] = baseline.get("profit_factor_R")
    metrics["mean_R_vs_baseline"] = metric_delta(metrics.get("mean_R"), baseline.get("mean_R"))
    metrics["profit_factor_R_vs_baseline"] = metric_delta(
        metrics.get("profit_factor_R"),
        baseline.get("profit_factor_R"),
    )
    classification = classification_for_metrics(metrics, min_trades)
    return {
        "target_family": bucket.target_family,
        "horizon": bucket.horizon,
        "group": bucket.group,
        "direction": bucket.direction,
        "symbol": bucket.symbol,
        "regime_column": bucket.regime_column,
        "regime_value": bucket.regime_value,
        "tested_rows": len(bucket.source_rows),
        "trades_count": metrics.get("trades_count"),
        "mean_R": metrics.get("mean_R"),
        "profit_factor_R": metrics.get("profit_factor_R"),
        "tp_hit_rate": metrics.get("tp_hit_rate"),
        "sl_hit_rate": metrics.get("sl_hit_rate"),
        "timeout_rate": metrics.get("timeout_rate"),
        "monthly_positive_ratio": metrics.get("monthly_positive_ratio"),
        "quarterly_positive_ratio": metrics.get("quarterly_positive_ratio"),
        "baseline_mean_R": metrics.get("baseline_mean_R"),
        "baseline_profit_factor_R": metrics.get("baseline_profit_factor_R"),
        "mean_R_vs_baseline": metrics.get("mean_R_vs_baseline"),
        "profit_factor_R_vs_baseline": metrics.get("profit_factor_R_vs_baseline"),
        "baseline_comparison": baseline_comparison_text(metrics),
        "classification_suggestion": classification,
        "source_files": " | ".join(sorted(bucket.source_files)),
        "notes": "; ".join(sorted(bucket.notes)),
    }


def bucket_key(source: SourceRow, column: str, value: str) -> tuple[str, str, str, str, str, str, str]:
    return (
        source.target_family,
        source.horizon,
        source.group,
        source.direction,
        source.symbol,
        column,
        value,
    )


def ensure_bucket(
    buckets: dict[tuple[str, str, str, str, str, str, str], OutcomeBucket],
    key: tuple[str, str, str, str, str, str, str],
) -> OutcomeBucket:
    target_family, horizon, group, direction, symbol, column, value = key
    return buckets.setdefault(
        key,
        OutcomeBucket(
            target_family=target_family,
            horizon=horizon,
            group=group,
            direction=direction,
            symbol=symbol,
            regime_column=column,
            regime_value=value,
        ),
    )


def aggregate_source_by_regime(
    *,
    source: SourceRow,
    rows: list[dict[str, object]],
    config: PathConfig,
    cost_config: dict[str, Any],
    regime_columns: list[str],
    buckets: dict[tuple[str, str, str, str, str, str, str], OutcomeBucket],
    disable_baseline_details: bool,
) -> None:
    baseline_by_regime: dict[tuple[str, str, str, str, str, str, str], AggregateStats] = {}
    if not disable_baseline_details:
        for row_index in range(len(rows)):
            outcome, _reason = simulate_path_exit(
                rows,
                row_index,
                config=config,
                cost_config=cost_config,
            )
            if outcome is None:
                continue
            for column in regime_columns:
                value = regime_value(outcome.row.get(column))
                key = bucket_key(source, column, value)
                baseline_by_regime.setdefault(key, AggregateStats()).update_outcome(outcome)

    predicate = predicate_for_filters(rows, config.filters)
    candidate_counts_by_regime: dict[tuple[str, str, str, str, str, str, str], int] = {}
    source_label = source_file_label(source.path)
    for row_index, row in enumerate(rows):
        if not predicate(row):
            continue
        outcome, _reason = simulate_path_exit(
            rows,
            row_index,
            config=config,
            cost_config=cost_config,
        )
        if outcome is None:
            continue
        for column in regime_columns:
            value = regime_value(outcome.row.get(column))
            key = bucket_key(source, column, value)
            bucket = ensure_bucket(buckets, key)
            bucket.source_files.add(source_label)
            bucket.source_rows.add((source_label, source.row_number))
            bucket.stats.update_outcome(outcome)
            candidate_counts_by_regime[key] = candidate_counts_by_regime.get(key, 0) + 1

    if disable_baseline_details:
        for key in candidate_counts_by_regime:
            ensure_bucket(buckets, key).notes.add("baseline details disabled by CLI flag")
        return

    for key, candidate_count in candidate_counts_by_regime.items():
        baseline_stats = baseline_by_regime.get(key)
        if baseline_stats is None or baseline_stats.trades_count <= 0:
            ensure_bucket(buckets, key).notes.add("baseline regime aggregate unavailable")
            continue
        ensure_bucket(buckets, key).baseline_stats.merge(baseline_stats, multiplier=candidate_count)


def default_row_loader(db_path: Path, symbol: str, timeframe: str) -> list[dict[str, object]]:
    return load_path_rows(db_path, symbol, timeframe)


def build_from_ml_dataset(
    source_rows: list[SourceRow],
    *,
    db_path: Path,
    cost_config: dict[str, Any],
    min_trades: int,
    max_regime_values: int,
    disable_baseline_details: bool,
    explicit_regime_columns: tuple[str, ...],
    row_loader: RowLoader,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    diagnostics: list[dict[str, object]] = []
    units: dict[tuple[str, str, str, str, str], int] = {}
    missing_by_unit: dict[tuple[str, str, str, str, str], set[str]] = {}
    high_cardinality_by_unit: dict[tuple[str, str, str, str, str], set[str]] = {}
    buckets: dict[tuple[str, str, str, str, str, str, str], OutcomeBucket] = {}
    row_cache: dict[tuple[str, str], list[dict[str, object]]] = {}
    loaded_sources = 0
    skipped_sources = 0

    for source in source_rows:
        if source.schema_kind != "tp_sl_summary":
            continue
        units[unit_key(source)] = units.get(unit_key(source), 0) + 1
        config = path_config_from_source(source, min_trades)
        if config is None:
            skipped_sources += 1
            missing_by_unit.setdefault(unit_key(source), set()).add("tp_sl_config")
            continue
        cache_key = (config.symbol, config.timeframe)
        if cache_key not in row_cache:
            row_cache[cache_key] = with_regime_labels_for_rows(
                row_loader(db_path, config.symbol, config.timeframe)
            )
        rows = row_cache[cache_key]
        if not rows:
            skipped_sources += 1
            missing_by_unit.setdefault(unit_key(source), set()).update(
                expectation.label for expectation in REGIME_EXPECTATIONS
            )
            continue
        headers = set(rows[0].keys())
        regime_columns, missing_columns = known_regime_columns(headers, explicit_regime_columns)
        if missing_columns:
            missing_by_unit.setdefault(unit_key(source), set()).update(missing_columns)
        regime_columns, high_cardinality_columns = filter_regime_columns_by_cardinality(
            rows,
            regime_columns,
            max_regime_values,
        )
        if high_cardinality_columns:
            high_cardinality_by_unit.setdefault(unit_key(source), set()).update(high_cardinality_columns)
        if not regime_columns:
            continue

        try:
            aggregate_source_by_regime(
                source=source,
                rows=rows,
                config=config,
                cost_config=cost_config,
                regime_columns=regime_columns,
                buckets=buckets,
                disable_baseline_details=disable_baseline_details,
            )
        except ValueError as exc:
            skipped_sources += 1
            diagnostics.append(
                {
                    "target_family": source.target_family,
                    "horizon": source.horizon,
                    "group": source.group,
                    "direction": source.direction,
                    "symbol": source.symbol,
                    "regime_column": "filters",
                    "regime_value": MISSING_VALUE,
                    "tested_rows": 1,
                    "trades_count": "",
                    "classification_suggestion": CLASS_NO_EVIDENCE,
                    "source_files": source_file_label(source.path),
                    "notes": f"fixed filter replay failed: {exc}",
                }
            )
            continue

        loaded_sources += 1

    diagnostics.extend(bucket_to_row(bucket, min_trades) for bucket in buckets.values())
    add_missing_rows(
        diagnostics,
        units=units,
        missing_columns_by_unit=missing_by_unit,
        note="regime column was not present in loaded ml_dataset rows",
    )
    add_no_evidence_column_rows(
        diagnostics,
        units=units,
        columns_by_unit=high_cardinality_by_unit,
        note=f"regime column exceeded max_regime_values={max_regime_values}; no timing buckets were invented",
    )
    audit = {
        "loaded_sources": loaded_sources,
        "skipped_sources": skipped_sources,
        "input_rows": len(source_rows),
        "mode": "ml_dataset",
        "max_regime_values": max_regime_values,
        "disable_baseline_details": disable_baseline_details,
    }
    return diagnostics, audit


def weighted_average(rows: list[dict[str, str]], value_column: str, weight_column: str = "trades_count") -> float | None:
    weighted_sum = 0.0
    weight_sum = 0.0
    values_without_weights: list[float] = []
    for row in rows:
        value = finite_value(row.get(value_column))
        if value is None:
            continue
        weight = finite_value(row.get(weight_column))
        if weight is None or weight <= 0:
            values_without_weights.append(value)
            continue
        weighted_sum += value * weight
        weight_sum += weight
    if weight_sum > 0:
        return weighted_sum / weight_sum
    return mean(values_without_weights) if values_without_weights else None


def rate_from_count_or_average(rows: list[dict[str, str]], count_column: str, rate_column: str, trades_count: int) -> float | None:
    counts = [safe_int(row.get(count_column)) for row in rows if str(row.get(count_column) or "").strip()]
    if counts and trades_count > 0:
        return sum(counts) / trades_count
    return weighted_average(rows, rate_column)


def aggregate_summary_rows(rows: list[dict[str, str]]) -> dict[str, object]:
    trades_count = sum(safe_int(row.get("trades_count")) for row in rows)
    metrics: dict[str, object] = {
        "trades_count": trades_count,
        "mean_R": weighted_average(rows, "mean_R"),
        "profit_factor_R": weighted_average(rows, "profit_factor_R"),
        "tp_hit_rate": rate_from_count_or_average(rows, "tp_hit_count", "tp_hit_rate", trades_count),
        "sl_hit_rate": rate_from_count_or_average(rows, "sl_hit_count", "sl_hit_rate", trades_count),
        "timeout_rate": rate_from_count_or_average(rows, "timeout_count", "timeout_rate", trades_count),
        "monthly_positive_ratio": weighted_average(rows, "monthly_positive_ratio"),
        "quarterly_positive_ratio": weighted_average(rows, "quarterly_positive_ratio"),
        "baseline_mean_R": weighted_average(rows, "baseline_mean_R", "baseline_trades_count"),
        "baseline_profit_factor_R": weighted_average(rows, "baseline_profit_factor_R", "baseline_trades_count"),
        "mean_R_vs_baseline": weighted_average(rows, "mean_R_vs_baseline"),
        "profit_factor_R_vs_baseline": weighted_average(rows, "profit_factor_R_vs_baseline"),
    }
    return metrics


def build_loaded_output_group_row(
    key: tuple[str, str, str, str, str, str, str],
    grouped_rows: list[SourceRow],
    min_trades: int,
) -> dict[str, object]:
    target_family, horizon, group, direction, symbol, regime_column, value = key
    schema_kinds = {row.schema_kind for row in grouped_rows}
    notes: list[str] = []
    if schema_kinds == {"combination_summary"}:
        metrics: dict[str, object] = {"trades_count": sum(safe_int(row.row.get("trades_count")) for row in grouped_rows)}
        notes.append("loaded combination rows do not contain TP/SL R metrics")
    else:
        metrics = aggregate_summary_rows([row.row for row in grouped_rows])
        if len(grouped_rows) > 1:
            notes.append("summary rows aggregated with trade-count weighting where possible")
    classification = classification_for_metrics(metrics, min_trades)
    return {
        "target_family": target_family,
        "horizon": horizon,
        "group": group,
        "direction": direction,
        "symbol": symbol,
        "regime_column": regime_column,
        "regime_value": value,
        "tested_rows": len(grouped_rows),
        "trades_count": metrics.get("trades_count"),
        "mean_R": metrics.get("mean_R"),
        "profit_factor_R": metrics.get("profit_factor_R"),
        "tp_hit_rate": metrics.get("tp_hit_rate"),
        "sl_hit_rate": metrics.get("sl_hit_rate"),
        "timeout_rate": metrics.get("timeout_rate"),
        "monthly_positive_ratio": metrics.get("monthly_positive_ratio"),
        "quarterly_positive_ratio": metrics.get("quarterly_positive_ratio"),
        "baseline_mean_R": metrics.get("baseline_mean_R"),
        "baseline_profit_factor_R": metrics.get("baseline_profit_factor_R"),
        "mean_R_vs_baseline": metrics.get("mean_R_vs_baseline"),
        "profit_factor_R_vs_baseline": metrics.get("profit_factor_R_vs_baseline"),
        "baseline_comparison": baseline_comparison_text(metrics),
        "classification_suggestion": classification,
        "source_files": " | ".join(sorted({source_file_label(row.path) for row in grouped_rows})),
        "notes": "; ".join(notes),
    }


def build_from_loaded_outputs(
    source_rows: list[SourceRow],
    *,
    min_trades: int,
    max_regime_values: int,
    explicit_regime_columns: tuple[str, ...],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    diagnostics: list[dict[str, object]] = []
    groups: dict[tuple[str, str, str, str, str, str, str], list[SourceRow]] = {}
    units: dict[tuple[str, str, str, str, str], int] = {}
    missing_by_unit: dict[tuple[str, str, str, str, str], set[str]] = {}
    high_cardinality_by_unit: dict[tuple[str, str, str, str, str], set[str]] = {}

    for source in source_rows:
        units[unit_key(source)] = units.get(unit_key(source), 0) + 1
        headers = set(source.row.keys())
        regime_columns, missing_columns = known_regime_columns(headers, explicit_regime_columns)
        if missing_columns:
            missing_by_unit.setdefault(unit_key(source), set()).update(missing_columns)
        regime_columns, high_cardinality_columns = filter_regime_columns_by_cardinality(
            [source.row],
            regime_columns,
            max_regime_values,
        )
        if high_cardinality_columns:
            high_cardinality_by_unit.setdefault(unit_key(source), set()).update(high_cardinality_columns)
        for column in regime_columns:
            groups.setdefault(
                (
                    source.target_family,
                    source.horizon,
                    source.group,
                    source.direction,
                    source.symbol,
                    column,
                    regime_value(source.row.get(column)),
                ),
                [],
            ).append(source)

    diagnostics.extend(
        build_loaded_output_group_row(key, grouped_rows, min_trades)
        for key, grouped_rows in sorted(groups.items())
    )
    add_missing_rows(
        diagnostics,
        units=units,
        missing_columns_by_unit=missing_by_unit,
        note="regime column was not present in loaded output rows",
    )
    add_no_evidence_column_rows(
        diagnostics,
        units=units,
        columns_by_unit=high_cardinality_by_unit,
        note=f"regime column exceeded max_regime_values={max_regime_values}; no timing buckets were invented",
    )
    audit = {
        "loaded_sources": len(source_rows),
        "skipped_sources": 0,
        "input_rows": len(source_rows),
        "mode": "loaded_outputs",
        "max_regime_values": max_regime_values,
        "disable_baseline_details": False,
    }
    return diagnostics, audit


def empty_no_evidence_row(note: str) -> dict[str, object]:
    return {
        "target_family": "ALL",
        "horizon": "",
        "group": "ALL",
        "direction": "ALL",
        "symbol": "ALL",
        "regime_column": "ALL",
        "regime_value": MISSING_VALUE,
        "tested_rows": 0,
        "trades_count": "",
        "classification_suggestion": CLASS_NO_EVIDENCE,
        "notes": note,
    }


def sort_diagnostics(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("target_family") or ""),
            safe_int(row.get("horizon")),
            str(row.get("group") or ""),
            str(row.get("direction") or ""),
            str(row.get("symbol") or ""),
            str(row.get("regime_column") or ""),
            str(row.get("regime_value") or ""),
            str(row.get("classification_suggestion") or ""),
        ),
    )


def pct_text(value: object) -> str:
    parsed = finite_value(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.2%}"


def num_text(value: object) -> str:
    parsed = finite_value(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.6f}"


def top_review_lines(rows: list[dict[str, object]], limit: int = 20) -> list[str]:
    selected = [row for row in rows if row.get("classification_suggestion") == CLASS_REVIEW]
    if not selected:
        return ["- None."]
    selected.sort(
        key=lambda row: (
            -(finite_value(row.get("mean_R")) or float("-inf")),
            -(finite_value(row.get("profit_factor_R")) or float("-inf")),
            str(row.get("target_family") or ""),
            str(row.get("regime_column") or ""),
        )
    )
    return [
        "- {target} h{horizon} {group} {direction} {symbol} `{column}={value}`: trades={trades}, mean_R={mean_r}, profit_factor_R={pf}".format(
            target=row.get("target_family", ""),
            horizon=row.get("horizon", ""),
            group=row.get("group", ""),
            direction=row.get("direction", ""),
            symbol=row.get("symbol", ""),
            column=row.get("regime_column", ""),
            value=row.get("regime_value", ""),
            trades=row.get("trades_count", ""),
            mean_r=num_text(row.get("mean_R")),
            pf=num_text(row.get("profit_factor_R")),
        )
        for row in selected[:limit]
    ]


def missing_lines(rows: list[dict[str, object]], limit: int = 30) -> list[str]:
    selected = [row for row in rows if row.get("regime_value") == MISSING_VALUE]
    if not selected:
        return ["- None."]
    return [
        "- {target} h{horizon} {group} {direction} {symbol}: `{column}` ({notes})".format(
            target=row.get("target_family", ""),
            horizon=row.get("horizon", ""),
            group=row.get("group", ""),
            direction=row.get("direction", ""),
            symbol=row.get("symbol", ""),
            column=row.get("regime_column", ""),
            notes=row.get("notes", ""),
        )
        for row in selected[:limit]
    ]


def write_report(path: Path, rows: list[dict[str, object]], audit: dict[str, object], input_paths: list[Path], min_trades: int) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get("classification_suggestion") or "")
        counts[label] = counts.get(label, 0) + 1
    lines = [
        "# Regime Filter Diagnostics",
        "",
        "## Scope",
        "",
        "- Offline descriptive diagnostic for existing historical branch outputs only.",
        "- No new features, multi-timeframe inputs, TP/SL optimization, sizing, or broker actions are added.",
        "- Labels are review hints only and do not promote any row.",
        "",
        "## Inputs",
        "",
        f"- Source mode: `{audit.get('mode', '')}`",
        f"- Input files discovered: `{len(input_paths)}`",
        f"- Loaded source rows: `{audit.get('input_rows', 0)}`",
        f"- Replayed TP/SL rows: `{audit.get('loaded_sources', 0)}`",
        f"- Skipped source rows: `{audit.get('skipped_sources', 0)}`",
        f"- Minimum trades for review label: `{min_trades}`",
        f"- Maximum distinct values per regime column: `{audit.get('max_regime_values', '')}`",
        f"- Baseline details disabled: `{bool(audit.get('disable_baseline_details'))}`",
        "",
        "## Classification Counts",
        "",
        f"- {CLASS_NO_EVIDENCE}: `{counts.get(CLASS_NO_EVIDENCE, 0)}`",
        f"- {CLASS_INSUFFICIENT}: `{counts.get(CLASS_INSUFFICIENT, 0)}`",
        f"- {CLASS_WEAK}: `{counts.get(CLASS_WEAK, 0)}`",
        f"- {CLASS_REVIEW}: `{counts.get(CLASS_REVIEW, 0)}`",
        "",
        "## Regime-Dependent Review Areas",
        "",
        *top_review_lines(rows),
        "",
        "## Missing Regime Columns",
        "",
        *missing_lines(rows),
        "",
        "## Guardrails",
        "",
        f"- `{CLASS_INSUFFICIENT}` is forced below the configured minimum trade count.",
        f"- `{CLASS_REVIEW}` requires enough trades, positive mean R, profit factor R above 1, and no negative baseline comparison when baseline fields are available.",
        "- Missing or non-R-only evidence remains descriptive and receives no positive review label.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> None:
    existing = [output_dir / file_name for file_name in (CSV_FILE, REPORT_FILE) if (output_dir / file_name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Regime diagnostics outputs already exist under {output_dir}. Pass --overwrite to regenerate them."
        )


def run_regime_filter_diagnostics(
    args: argparse.Namespace,
    *,
    row_loader: RowLoader = default_row_loader,
) -> dict[str, Path]:
    run_id = str(args.run_id or current_run_id())
    output_dir = Path(args.output_root) / run_id
    ensure_outputs_writable(output_dir, bool(args.overwrite))

    input_paths = list(args.input_csv or [])
    if not input_paths:
        input_paths = collect_input_paths(list(args.input_root), tuple(args.path_fragment or ()))
    loaded = load_csv_inputs([Path(path) for path in input_paths])
    source_rows = source_rows_from_loaded(loaded)
    if args.max_source_rows is not None:
        source_rows = source_rows[: max(0, int(args.max_source_rows))]

    if not source_rows:
        diagnostics = [empty_no_evidence_row("no input rows loaded from existing branch outputs")]
        audit = {
            "loaded_sources": 0,
            "skipped_sources": 0,
            "input_rows": 0,
            "mode": str(args.source_mode),
            "max_regime_values": int(args.max_regime_values),
            "disable_baseline_details": bool(args.disable_baseline_details),
        }
    elif args.source_mode == "loaded_outputs":
        diagnostics, audit = build_from_loaded_outputs(
            source_rows,
            min_trades=int(args.min_trades),
            max_regime_values=int(args.max_regime_values),
            explicit_regime_columns=tuple(args.regime_column or ()),
        )
    else:
        diagnostics, audit = build_from_ml_dataset(
            source_rows,
            db_path=Path(args.db_path),
            cost_config=load_cost_config(args.cost_config),
            min_trades=int(args.min_trades),
            max_regime_values=int(args.max_regime_values),
            disable_baseline_details=bool(args.disable_baseline_details),
            explicit_regime_columns=tuple(args.regime_column or ()),
            row_loader=row_loader,
        )
        if not any(row.get("classification_suggestion") != CLASS_NO_EVIDENCE for row in diagnostics):
            loaded_diagnostics, loaded_audit = build_from_loaded_outputs(
                source_rows,
                min_trades=int(args.min_trades),
                max_regime_values=int(args.max_regime_values),
                explicit_regime_columns=tuple(args.regime_column or ()),
            )
            if any(row.get("regime_value") != MISSING_VALUE for row in loaded_diagnostics):
                diagnostics = loaded_diagnostics
                audit = {**loaded_audit, "mode": "loaded_outputs_fallback"}

    sorted_rows = sort_diagnostics(diagnostics)
    csv_path = output_dir / CSV_FILE
    report_path = output_dir / REPORT_FILE
    write_csv(csv_path, sorted_rows)
    write_report(report_path, sorted_rows, audit, [Path(path) for path in input_paths], int(args.min_trades))
    return {
        "regime_filter_diagnostics_csv": csv_path,
        "regime_filter_diagnostics_report": report_path,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build research-only regime grouped diagnostics from existing preferred branch outputs."
    )
    parser.add_argument("--input-root", action="append", type=Path)
    parser.add_argument("--input-csv", action="append", type=Path)
    parser.add_argument("--path-fragment", action="append")
    parser.add_argument("--source-mode", choices=("ml_dataset", "loaded_outputs"), default="ml_dataset")
    parser.add_argument("--regime-column", action="append")
    parser.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES)
    parser.add_argument("--max-regime-values", type=int, default=25)
    parser.add_argument("--max-source-rows", type=int)
    parser.add_argument("--disable-baseline-details", action="store_true")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=f"Default: {DEFAULT_OUTPUT_ROOT}")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    args.input_root = args.input_root or [DEFAULT_COMBINATION_ROOT, DEFAULT_TP_SL_ROOT]
    args.input_csv = args.input_csv or []
    args.path_fragment = args.path_fragment or list(DEFAULT_PATH_FRAGMENTS)
    args.regime_column = args.regime_column or []
    return args


def main() -> int:
    try:
        outputs = run_regime_filter_diagnostics(parse_args())
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"Regime filter diagnostics failed: {exc}")
        return 1
    print("Regime filter diagnostics complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
