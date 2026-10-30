"""Research-only validation for selected regime-filter review rows.

The script takes ``REGIME_DEPENDENT_REVIEW`` rows from an existing regime
diagnostic CSV and replays a stricter offline check for a small selected set.
It reuses the existing historical TP/SL path logic and source branch outputs;
it does not add features, timeframes, sizing, broker actions, or deployment
rules.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import datetime
import math
from pathlib import Path
import re
import sys
from typing import Any, Callable


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from diagnose_regime_filter_candidates import (
        BLANK_VALUE,
        CLASS_REVIEW,
        finite_value,
        infer_direction,
        infer_group,
        infer_horizon,
        infer_symbol,
        infer_target_family,
        infer_timeframe,
        filters_from_source_row,
        read_csv_with_headers,
        regime_value,
        safe_int,
        source_file_label,
    )
    from regime_classification import with_regime_labels_for_rows
    from research_costs import load_cost_config
    from research_metrics import csv_safe_value, parse_metric_timestamp
    from run_tp_sl_path_backtests import (
        DATABASE_PATH,
        DEFAULT_ATR_COLUMN,
        DEFAULT_SAME_BAR_POLICY,
        PathConfig,
        load_path_rows,
        predicate_for_filters,
        simulate_path_exit,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.diagnose_regime_filter_candidates import (
        BLANK_VALUE,
        CLASS_REVIEW,
        finite_value,
        infer_direction,
        infer_group,
        infer_horizon,
        infer_symbol,
        infer_target_family,
        infer_timeframe,
        filters_from_source_row,
        read_csv_with_headers,
        regime_value,
        safe_int,
        source_file_label,
    )
    from scripts.regime_classification import with_regime_labels_for_rows
    from scripts.research_costs import load_cost_config
    from scripts.research_metrics import csv_safe_value, parse_metric_timestamp
    from scripts.run_tp_sl_path_backtests import (
        DATABASE_PATH,
        DEFAULT_ATR_COLUMN,
        DEFAULT_SAME_BAR_POLICY,
        PathConfig,
        load_path_rows,
        predicate_for_filters,
        simulate_path_exit,
    )


DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "regime_filtered_candidate_diagnostics"
DEFAULT_ALLOWED_REGIME_COLUMNS = (
    "hour_session",
    "session",
    "volume_liquidity_regime",
    "volume_dry_up_20",
    "volume_spike_20",
    "spread_liquidity_regime",
    "volatility_regime",
    "range_regime",
    "blackout_window_30m",
)
PREFERRED_REGIME_PRIORITY = {
    "hour_session": 0,
    "session": 1,
    "volume_liquidity_regime": 2,
    "volume_dry_up_20": 3,
    "volume_spike_20": 4,
    "blackout_window_30m": 5,
    "spread_liquidity_regime": 6,
    "volatility_regime": 7,
    "range_regime": 8,
}
NEWS_EQUIVALENT_COLUMNS = {
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
}

CLASS_REJECTED = "REGIME_REJECTED"
CLASS_RETAINED = "REGIME_REVIEW_RETAINED"
CLASS_YEARLY = "NEEDS_YEARLY_VALIDATION"
CLASS_INSUFFICIENT = "INSUFFICIENT_TRADES"

SUMMARY_FILE = "regime_filtered_candidate_summary.csv"
REPORT_FILE = "regime_filtered_candidate_report.md"

TARGET_FAMILY_RE = re.compile(
    r"^(?:preferred_)?(?P<tp>[0-9]+(?:_[0-9]+)?)atr_(?P<sl>[0-9]+(?:_[0-9]+)?)atr_hit_first$"
)

FIELDNAMES = [
    "selection_rank",
    "candidate_id",
    "target_family",
    "horizon",
    "group",
    "direction",
    "symbol",
    "regime_column",
    "regime_value",
    "tp_atr",
    "sl_atr",
    "source_files",
    "source_rows_matched",
    "tested_source_rows",
    "trades_count",
    "tp_hit_rate",
    "sl_hit_rate",
    "timeout_rate",
    "mean_R",
    "profit_factor_R",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "yearly_breakdown",
    "yearly_positive_ratio",
    "baseline_trades_count",
    "baseline_mean_R",
    "baseline_profit_factor_R",
    "mean_R_vs_baseline",
    "profit_factor_R_vs_baseline",
    "random_baseline_mean_R",
    "random_baseline_profit_factor_R",
    "top_5_percent_trades_contribution_pct",
    "sequential_trades_count",
    "skipped_due_to_overlap",
    "sequential_mean_R",
    "sequential_profit_factor_R",
    "sequential_tp_hit_rate",
    "sequential_sl_hit_rate",
    "sequential_timeout_rate",
    "sequential_max_drawdown_R",
    "sequential_max_consecutive_losses",
    "sequential_monthly_positive_ratio",
    "sequential_quarterly_positive_ratio",
    "sequential_yearly_positive_ratio",
    "sequential_top_5_percent_contribution_pct",
    "sequential_vs_row_level_mean_R_delta",
    "sequential_vs_row_level_profit_factor_delta",
    "stress_cost_config_requested",
    "stress_cost_not_available_reason",
    "random_baseline_iterations",
    "random_mean_R_mean",
    "random_mean_R_p95",
    "random_profit_factor_R_mean",
    "random_profit_factor_R_p95",
    "sequential_mean_R_vs_random_p95",
    "random_baseline_not_available_reason",
    "overlap_policy",
    "classification",
    "notes",
]

TRADE_LOG_FIELDNAMES = [
    "candidate_id",
    "symbol",
    "direction",
    "target_family",
    "horizon",
    "regime_column",
    "regime_value",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_reason",
    "bars_held",
    "tp_atr",
    "sl_atr",
    "R",
    "cost_R",
    "net_R",
    "skipped_due_to_overlap_count",
]

EQUITY_CURVE_FIELDNAMES = [
    "trade_index",
    "exit_time",
    "cumulative_R",
    "drawdown_R",
]


@dataclass(frozen=True)
class ReviewRow:
    source_index: int
    row: dict[str, str]
    target_family: str
    horizon: int
    group: str
    direction: str
    symbol: str
    regime_column: str
    regime_value: str
    trades_count: int
    mean_R: float
    profit_factor_R: float
    source_files: tuple[str, ...]


@dataclass(frozen=True)
class SourceBranchRow:
    path: Path
    row_number: int
    row: dict[str, str]
    target_family: str
    horizon: int
    group: str
    direction: str
    symbol: str
    timeframe: str


@dataclass(frozen=True)
class CandidateReplayEvent:
    candidate_id: str
    review: ReviewRow
    source: SourceBranchRow
    config: PathConfig
    outcome: Any
    entry_timestamp: datetime | None
    exit_timestamp: datetime | None
    exit_row_index: int
    source_label: str


@dataclass
class SequentialReplayResult:
    accepted_by_candidate: dict[str, list[CandidateReplayEvent]] = field(default_factory=dict)
    skipped_by_candidate: dict[str, int] = field(default_factory=dict)


@dataclass
class RunningStats:
    trades_count: int = 0
    tp_hit_count: int = 0
    sl_hit_count: int = 0
    timeout_count: int = 0
    sum_R: float = 0.0
    profit_R: float = 0.0
    loss_R: float = 0.0
    monthly_R: dict[tuple[int, int], float] = field(default_factory=dict)
    quarterly_R: dict[tuple[int, int], float] = field(default_factory=dict)
    yearly_R: dict[int, float] = field(default_factory=dict)
    yearly_counts: dict[int, int] = field(default_factory=dict)
    positive_R_values: list[float] = field(default_factory=list)

    def update_outcome(self, outcome: Any) -> None:
        value = finite_value(getattr(outcome, "selected_R", None))
        if value is None:
            return
        self.trades_count += 1
        self.sum_R += value
        if value > 0:
            self.profit_R += value
            self.positive_R_values.append(value)
        elif value < 0:
            self.loss_R += abs(value)
        reason = str(getattr(outcome, "exit_reason", "") or "")
        if reason == "tp":
            self.tp_hit_count += 1
        elif reason == "sl":
            self.sl_hit_count += 1
        elif reason == "timeout":
            self.timeout_count += 1
        timestamp = parse_metric_timestamp(getattr(outcome, "time_server", None))
        if timestamp is None:
            return
        month_key = (timestamp.year, timestamp.month)
        quarter_key = (timestamp.year, (timestamp.month - 1) // 3 + 1)
        self.monthly_R[month_key] = self.monthly_R.get(month_key, 0.0) + value
        self.quarterly_R[quarter_key] = self.quarterly_R.get(quarter_key, 0.0) + value
        self.yearly_R[timestamp.year] = self.yearly_R.get(timestamp.year, 0.0) + value
        self.yearly_counts[timestamp.year] = self.yearly_counts.get(timestamp.year, 0) + 1

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
                "yearly_breakdown": "",
                "yearly_positive_ratio": None,
                "top_5_percent_trades_contribution_pct": None,
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
            "yearly_breakdown": self.yearly_breakdown(),
            "yearly_positive_ratio": positive_period_ratio({(year, 1): value for year, value in self.yearly_R.items()}),
            "top_5_percent_trades_contribution_pct": self.top_trade_contribution_pct(),
        }

    def profit_factor_R(self) -> float | None:
        if self.loss_R == 0:
            return None if self.profit_R == 0 else float("inf")
        return self.profit_R / self.loss_R

    def yearly_breakdown(self) -> str:
        if not self.yearly_R:
            return ""
        parts: list[str] = []
        for year in sorted(self.yearly_R):
            count = self.yearly_counts.get(year, 0)
            mean_R = self.yearly_R[year] / count if count else 0.0
            parts.append(f"{year}:trades={count},mean_R={mean_R:.6f},sum_R={self.yearly_R[year]:.6f}")
        return " | ".join(parts)

    def top_trade_contribution_pct(self) -> float | None:
        positive_total = sum(self.positive_R_values)
        if positive_total <= 0:
            return None
        top_count = max(1, math.ceil(self.trades_count * 0.05))
        top_positive = sum(sorted(self.positive_R_values, reverse=True)[:top_count])
        return top_positive / positive_total * 100


RowLoader = Callable[[Path, str, str], list[dict[str, object]]]


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def positive_period_ratio(periods: dict[tuple[int, int], float]) -> float | None:
    if not periods:
        return None
    values = [periods[key] for key in sorted(periods)]
    return sum(1 for value in values if value > 0) / len(values)


def parse_target_family(value: object) -> tuple[float, float]:
    text = str(value or "").strip()
    match = TARGET_FAMILY_RE.match(text)
    if not match:
        raise ValueError(f"Unsupported target_family: {text!r}")
    return float(match.group("tp").replace("_", ".")), float(match.group("sl").replace("_", "."))


def sanitize_path_token(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_.")
    return text or "blank"


def decimal_token(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value).replace(".", "_")


def candidate_id_for_review(review: ReviewRow) -> str:
    tp_atr, sl_atr = parse_target_family(review.target_family)
    parts = (
        review.target_family,
        f"h{review.horizon}",
        review.group,
        review.symbol,
        review.direction,
        review.regime_column,
        review.regime_value,
        f"tp{decimal_token(tp_atr)}atr",
        f"sl{decimal_token(sl_atr)}atr",
    )
    return sanitize_path_token("__".join(str(part) for part in parts))


def review_row_from_csv_row(row: dict[str, str], index: int) -> ReviewRow | None:
    if str(row.get("classification_suggestion") or "").strip() != CLASS_REVIEW:
        return None
    mean_R = finite_value(row.get("mean_R"))
    profit_factor_R = finite_value(row.get("profit_factor_R"))
    if mean_R is None or profit_factor_R is None:
        return None
    source_files = tuple(
        item.strip()
        for item in str(row.get("source_files") or "").split("|")
        if item.strip()
    )
    return ReviewRow(
        source_index=index,
        row=row,
        target_family=str(row.get("target_family") or "").strip(),
        horizon=safe_int(row.get("horizon")),
        group=str(row.get("group") or "").strip(),
        direction=str(row.get("direction") or "").strip().lower(),
        symbol=str(row.get("symbol") or "").strip().upper(),
        regime_column=str(row.get("regime_column") or "").strip(),
        regime_value=str(row.get("regime_value") or "").strip(),
        trades_count=safe_int(row.get("trades_count")),
        mean_R=mean_R,
        profit_factor_R=profit_factor_R,
        source_files=source_files,
    )


def regime_priority(column: str) -> int:
    if column in PREFERRED_REGIME_PRIORITY:
        return PREFERRED_REGIME_PRIORITY[column]
    if column in NEWS_EQUIVALENT_COLUMNS:
        return 20
    return 10


def news_dedupe_key(row: ReviewRow) -> tuple[object, ...] | None:
    if row.regime_column not in NEWS_EQUIVALENT_COLUMNS:
        return None
    return (
        row.target_family,
        row.horizon,
        row.group,
        row.direction,
        row.symbol,
        "news_context",
    )


def selection_identity(row: ReviewRow) -> tuple[object, ...]:
    return (
        row.target_family,
        row.horizon,
        row.group,
        row.direction,
        row.symbol,
        row.regime_column,
        row.regime_value,
    )


def overlap_identity(row: ReviewRow, policy: str) -> tuple[object, ...] | None:
    if policy == "allow_overlap":
        return None
    return row.target_family, row.horizon, row.group, row.direction, row.symbol


def select_review_rows(
    rows: list[dict[str, str]],
    *,
    min_trades: int,
    min_mean_R: float,
    min_profit_factor_R: float,
    allowed_regime_columns: tuple[str, ...],
    max_candidates: int,
    overlap_policy: str,
) -> list[ReviewRow]:
    allowed = set(allowed_regime_columns)
    review_rows: list[ReviewRow] = []
    for index, row in enumerate(rows, start=1):
        review = review_row_from_csv_row(row, index)
        if review is None:
            continue
        if allowed and review.regime_column not in allowed:
            continue
        if review.trades_count < min_trades:
            continue
        if review.mean_R < min_mean_R or review.profit_factor_R < min_profit_factor_R:
            continue
        review_rows.append(review)

    review_rows.sort(
        key=lambda row: (
            regime_priority(row.regime_column),
            -row.mean_R,
            -row.profit_factor_R,
            -row.trades_count,
            row.source_index,
        )
    )

    selected: list[ReviewRow] = []
    seen_exact: set[tuple[object, ...]] = set()
    seen_news: set[tuple[object, ...]] = set()
    seen_overlap: set[tuple[object, ...]] = set()
    for row in review_rows:
        exact_key = selection_identity(row)
        if exact_key in seen_exact:
            continue
        news_key = news_dedupe_key(row)
        if news_key is not None and news_key in seen_news:
            continue
        overlap_key = overlap_identity(row, overlap_policy)
        if overlap_key is not None and overlap_key in seen_overlap:
            continue
        selected.append(row)
        seen_exact.add(exact_key)
        if news_key is not None:
            seen_news.add(news_key)
        if overlap_key is not None:
            seen_overlap.add(overlap_key)
        if len(selected) >= max_candidates:
            break
    return selected


def resolve_source_path(label: str) -> Path:
    path = Path(label)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def source_branch_row_from_csv(path: Path, row: dict[str, str], row_number: int) -> SourceBranchRow:
    symbol = infer_symbol(row, path)
    return SourceBranchRow(
        path=path,
        row_number=row_number,
        row=row,
        target_family=infer_target_family(row, path),
        horizon=safe_int(infer_horizon(row, path)),
        group=infer_group(row, path, symbol),
        direction=infer_direction(row, path),
        symbol=symbol,
        timeframe=infer_timeframe(row, path),
    )


def load_source_branch_rows(review: ReviewRow) -> list[SourceBranchRow]:
    source_rows: list[SourceBranchRow] = []
    for label in review.source_files:
        path = resolve_source_path(label)
        if not path.exists():
            continue
        rows, _headers = read_csv_with_headers(path)
        for index, row in enumerate(rows, start=1):
            source = source_branch_row_from_csv(path, row, index)
            if source.target_family != review.target_family:
                continue
            if source.horizon != review.horizon:
                continue
            if source.group != review.group:
                continue
            if source.direction != review.direction:
                continue
            if source.symbol != review.symbol:
                continue
            source_rows.append(source)
    return source_rows


def path_config_from_source(review: ReviewRow, source: SourceBranchRow, min_trades: int) -> PathConfig:
    tp_atr, sl_atr = parse_target_family(review.target_family)
    return PathConfig(
        symbol=review.symbol,
        timeframe=source.timeframe,
        direction=review.direction,
        horizon=review.horizon,
        tp_atr=tp_atr,
        sl_atr=sl_atr,
        atr_column=str(source.row.get("atr_column") or DEFAULT_ATR_COLUMN).strip(),
        same_bar_policy=str(source.row.get("same_bar_policy") or DEFAULT_SAME_BAR_POLICY).strip(),
        filters=filters_from_source_row(source.row),
        cost_mode=str(source.row.get("cost_mode") or "estimated").strip(),
        return_mode=str(source.row.get("return_mode") or "net").strip(),
        min_trades=min_trades,
    )


def row_matches_regime(row: dict[str, object], column: str, expected: str) -> bool:
    if expected == BLANK_VALUE:
        return not str(row.get(column) if row.get(column) is not None else "").strip()
    current = regime_value(row.get(column))
    if current == expected:
        return True
    expected_number = finite_value(expected)
    current_number = finite_value(current)
    return expected_number is not None and current_number is not None and expected_number == current_number


def collect_candidate_replay_events(
    review: ReviewRow,
    *,
    candidate_id: str,
    source_rows: list[SourceBranchRow],
    db_path: Path,
    cost_config: dict[str, Any],
    min_trades: int,
    row_loader: RowLoader,
) -> tuple[list[CandidateReplayEvent], list[str]]:
    events: list[CandidateReplayEvent] = []
    notes: list[str] = []
    row_cache: dict[tuple[str, str], list[dict[str, object]]] = {}
    seen_entries: set[tuple[str, str, int, object, tuple[str, ...]]] = set()

    for source in source_rows:
        config = path_config_from_source(review, source, min_trades)
        cache_key = (config.symbol, config.timeframe)
        if cache_key not in row_cache:
            row_cache[cache_key] = with_regime_labels_for_rows(
                row_loader(db_path, config.symbol, config.timeframe)
            )
        rows = row_cache[cache_key]
        if not rows:
            notes.append(f"no historical rows for {config.symbol} {config.timeframe}")
            continue
        if review.regime_column not in rows[0]:
            notes.append(f"missing regime column {review.regime_column}")
            continue
        predicate = predicate_for_filters(rows, config.filters)
        for row_index, row in enumerate(rows):
            if not row_matches_regime(row, review.regime_column, review.regime_value):
                continue
            if not predicate(row):
                continue
            dedupe_key = (
                config.symbol,
                config.direction,
                row_index,
                row.get("time_server"),
                config.filters,
            )
            if dedupe_key in seen_entries:
                continue
            outcome, _reason = simulate_path_exit(
                rows,
                row_index,
                config=config,
                cost_config=cost_config,
            )
            if outcome is None:
                continue
            seen_entries.add(dedupe_key)
            events.append(
                CandidateReplayEvent(
                    candidate_id=candidate_id,
                    review=review,
                    source=source,
                    config=config,
                    outcome=outcome,
                    entry_timestamp=parse_metric_timestamp(outcome.time_server),
                    exit_timestamp=parse_metric_timestamp(outcome.exit_time),
                    exit_row_index=row_index + int(outcome.exit_bars),
                    source_label=source_file_label(source.path),
                )
            )
    return events, sorted(set(notes))


def replay_events_without_symbol_overlap(events: list[CandidateReplayEvent]) -> SequentialReplayResult:
    result = SequentialReplayResult()
    open_until_by_symbol: dict[str, tuple[datetime | None, int]] = {}
    sorted_events = sorted(
        events,
        key=lambda event: (
            event.entry_timestamp or datetime.max,
            event.config.symbol,
            event.outcome.row_index,
            event.candidate_id,
        ),
    )

    for event in sorted_events:
        symbol = event.config.symbol
        open_until_time, open_until_index = open_until_by_symbol.get(symbol, (None, -1))
        overlaps_by_time = (
            event.entry_timestamp is not None
            and open_until_time is not None
            and event.entry_timestamp <= open_until_time
        )
        overlaps_by_index = event.outcome.row_index <= open_until_index
        if overlaps_by_time or overlaps_by_index:
            result.skipped_by_candidate[event.candidate_id] = (
                result.skipped_by_candidate.get(event.candidate_id, 0) + 1
            )
            continue
        result.accepted_by_candidate.setdefault(event.candidate_id, []).append(event)
        current_until = open_until_by_symbol.get(symbol)
        event_until = (event.exit_timestamp, event.exit_row_index)
        if current_until is None or event.exit_row_index >= current_until[1]:
            open_until_by_symbol[symbol] = event_until
    return result


def sequential_stats_from_events(events: list[CandidateReplayEvent]) -> dict[str, object]:
    if not events:
        return {
            "sequential_trades_count": 0,
            "sequential_mean_R": None,
            "sequential_profit_factor_R": None,
            "sequential_tp_hit_rate": None,
            "sequential_sl_hit_rate": None,
            "sequential_timeout_rate": None,
            "sequential_max_drawdown_R": None,
            "sequential_max_consecutive_losses": 0,
            "sequential_monthly_positive_ratio": None,
            "sequential_quarterly_positive_ratio": None,
            "sequential_yearly_positive_ratio": None,
            "sequential_top_5_percent_contribution_pct": None,
        }

    values = [float(event.outcome.selected_R) for event in events]
    profit_R = sum(value for value in values if value > 0)
    loss_R = sum(abs(value) for value in values if value < 0)
    tp_count = sum(1 for event in events if event.outcome.exit_reason == "tp")
    sl_count = sum(1 for event in events if event.outcome.exit_reason == "sl")
    timeout_count = sum(1 for event in events if event.outcome.exit_reason == "timeout")
    monthly_R: dict[tuple[int, int], float] = {}
    quarterly_R: dict[tuple[int, int], float] = {}
    yearly_R: dict[tuple[int, int], float] = {}
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    consecutive_losses = 0
    max_consecutive_losses = 0

    for event, value in zip(events, values):
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
        if value < 0:
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0
        timestamp = parse_metric_timestamp(event.outcome.exit_time)
        if timestamp is None:
            continue
        month_key = (timestamp.year, timestamp.month)
        quarter_key = (timestamp.year, (timestamp.month - 1) // 3 + 1)
        year_key = (timestamp.year, 1)
        monthly_R[month_key] = monthly_R.get(month_key, 0.0) + value
        quarterly_R[quarter_key] = quarterly_R.get(quarter_key, 0.0) + value
        yearly_R[year_key] = yearly_R.get(year_key, 0.0) + value

    positive_values = sorted((value for value in values if value > 0), reverse=True)
    positive_total = sum(positive_values)
    top_contribution = None
    if positive_total > 0:
        top_count = max(1, math.ceil(len(values) * 0.05))
        top_contribution = sum(positive_values[:top_count]) / positive_total * 100

    return {
        "sequential_trades_count": len(values),
        "sequential_mean_R": sum(values) / len(values),
        "sequential_profit_factor_R": None if loss_R == 0 and profit_R == 0 else (float("inf") if loss_R == 0 else profit_R / loss_R),
        "sequential_tp_hit_rate": tp_count / len(values),
        "sequential_sl_hit_rate": sl_count / len(values),
        "sequential_timeout_rate": timeout_count / len(values),
        "sequential_max_drawdown_R": max_drawdown,
        "sequential_max_consecutive_losses": max_consecutive_losses,
        "sequential_monthly_positive_ratio": positive_period_ratio(monthly_R),
        "sequential_quarterly_positive_ratio": positive_period_ratio(quarterly_R),
        "sequential_yearly_positive_ratio": positive_period_ratio(yearly_R),
        "sequential_top_5_percent_contribution_pct": top_contribution,
    }


def equity_curve_rows(events: list[CandidateReplayEvent]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    cumulative = 0.0
    peak = 0.0
    for index, event in enumerate(events, start=1):
        cumulative += float(event.outcome.selected_R)
        peak = max(peak, cumulative)
        rows.append(
            {
                "trade_index": index,
                "exit_time": event.outcome.exit_time,
                "cumulative_R": cumulative,
                "drawdown_R": peak - cumulative,
            }
        )
    return rows


def trade_log_rows(events: list[CandidateReplayEvent], skipped_due_to_overlap: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for event in events:
        outcome = event.outcome
        rows.append(
            {
                "candidate_id": event.candidate_id,
                "symbol": event.config.symbol,
                "direction": event.config.direction,
                "target_family": event.review.target_family,
                "horizon": event.review.horizon,
                "regime_column": event.review.regime_column,
                "regime_value": event.review.regime_value,
                "entry_time": outcome.time_server,
                "exit_time": outcome.exit_time,
                "entry_price": outcome.entry_price,
                "exit_reason": str(outcome.exit_reason or "").upper(),
                "bars_held": outcome.exit_bars,
                "tp_atr": event.config.tp_atr,
                "sl_atr": event.config.sl_atr,
                "R": outcome.selected_R,
                "cost_R": outcome.cost_R,
                "net_R": outcome.net_R,
                "skipped_due_to_overlap_count": skipped_due_to_overlap,
            }
        )
    return rows


def apply_sequential_metrics(
    row: dict[str, object],
    *,
    events: list[CandidateReplayEvent],
    skipped_due_to_overlap: int,
    min_trades: int,
    min_mean_R: float,
    min_profit_factor_R: float,
    min_yearly_positive_ratio: float,
    min_period_positive_ratio: float,
) -> None:
    metrics = sequential_stats_from_events(events)
    row.update(metrics)
    row["skipped_due_to_overlap"] = skipped_due_to_overlap
    row["sequential_vs_row_level_mean_R_delta"] = metric_delta(
        row.get("sequential_mean_R"),
        row.get("mean_R"),
    )
    row["sequential_vs_row_level_profit_factor_delta"] = metric_delta(
        row.get("sequential_profit_factor_R"),
        row.get("profit_factor_R"),
    )
    row["classification"] = classify_sequential_validation_row(
        row,
        min_trades=min_trades,
        min_mean_R=min_mean_R,
        min_profit_factor_R=min_profit_factor_R,
        min_yearly_positive_ratio=min_yearly_positive_ratio,
        min_period_positive_ratio=min_period_positive_ratio,
    )


def validate_review_row(
    review: ReviewRow,
    *,
    source_rows: list[SourceBranchRow],
    db_path: Path,
    cost_config: dict[str, Any],
    min_trades: int,
    min_mean_R: float,
    min_profit_factor_R: float,
    min_years: int,
    min_yearly_positive_ratio: float,
    min_period_positive_ratio: float,
    overlap_policy: str,
    row_loader: RowLoader,
) -> dict[str, object]:
    tp_atr, sl_atr = parse_target_family(review.target_family)
    stats = RunningStats()
    baseline_stats = RunningStats()
    tested_source_rows = 0
    notes: list[str] = []
    source_labels: set[str] = set()
    row_cache: dict[tuple[str, str], list[dict[str, object]]] = {}

    for source in source_rows:
        config = path_config_from_source(review, source, min_trades)
        cache_key = (config.symbol, config.timeframe)
        if cache_key not in row_cache:
            row_cache[cache_key] = with_regime_labels_for_rows(
                row_loader(db_path, config.symbol, config.timeframe)
            )
        rows = row_cache[cache_key]
        if not rows:
            notes.append(f"no historical rows for {config.symbol} {config.timeframe}")
            continue
        if review.regime_column not in rows[0]:
            notes.append(f"missing regime column {review.regime_column}")
            continue
        predicate = predicate_for_filters(rows, config.filters)
        tested_source_rows += 1
        source_labels.add(source_file_label(source.path))
        for row_index, row in enumerate(rows):
            if not row_matches_regime(row, review.regime_column, review.regime_value):
                continue
            outcome, _reason = simulate_path_exit(
                rows,
                row_index,
                config=config,
                cost_config=cost_config,
            )
            if outcome is None:
                continue
            baseline_stats.update_outcome(outcome)
            if predicate(row):
                stats.update_outcome(outcome)

    metrics = stats.as_metrics()
    baseline = baseline_stats.as_metrics()
    mean_delta = metric_delta(metrics.get("mean_R"), baseline.get("mean_R"))
    profit_delta = metric_delta(metrics.get("profit_factor_R"), baseline.get("profit_factor_R"))
    classification = classify_validation_row(
        metrics,
        mean_delta=mean_delta,
        profit_delta=profit_delta,
        min_trades=min_trades,
        min_mean_R=min_mean_R,
        min_profit_factor_R=min_profit_factor_R,
        min_years=min_years,
        min_yearly_positive_ratio=min_yearly_positive_ratio,
        min_period_positive_ratio=min_period_positive_ratio,
    )
    if overlap_policy == "no_overlap_per_symbol":
        notes.append("selection-level no_overlap_per_symbol applied")
    if not source_rows:
        notes.append("source branch rows unavailable")
    notes.append("random baseline not loaded; regime baseline reported")

    return {
        "target_family": review.target_family,
        "horizon": review.horizon,
        "group": review.group,
        "direction": review.direction,
        "symbol": review.symbol,
        "regime_column": review.regime_column,
        "regime_value": review.regime_value,
        "tp_atr": tp_atr,
        "sl_atr": sl_atr,
        "source_files": " | ".join(sorted(source_labels or set(review.source_files))),
        "source_rows_matched": len(source_rows),
        "tested_source_rows": tested_source_rows,
        "trades_count": metrics.get("trades_count"),
        "tp_hit_rate": metrics.get("tp_hit_rate"),
        "sl_hit_rate": metrics.get("sl_hit_rate"),
        "timeout_rate": metrics.get("timeout_rate"),
        "mean_R": metrics.get("mean_R"),
        "profit_factor_R": metrics.get("profit_factor_R"),
        "monthly_positive_ratio": metrics.get("monthly_positive_ratio"),
        "quarterly_positive_ratio": metrics.get("quarterly_positive_ratio"),
        "yearly_breakdown": metrics.get("yearly_breakdown"),
        "yearly_positive_ratio": metrics.get("yearly_positive_ratio"),
        "baseline_trades_count": baseline.get("trades_count"),
        "baseline_mean_R": baseline.get("mean_R"),
        "baseline_profit_factor_R": baseline.get("profit_factor_R"),
        "mean_R_vs_baseline": mean_delta,
        "profit_factor_R_vs_baseline": profit_delta,
        "random_baseline_mean_R": "",
        "random_baseline_profit_factor_R": "",
        "top_5_percent_trades_contribution_pct": metrics.get("top_5_percent_trades_contribution_pct"),
        "overlap_policy": overlap_policy,
        "classification": classification,
        "notes": "; ".join(sorted(set(item for item in notes if item))),
    }


def metric_delta(value: object, baseline: object) -> float | None:
    parsed_value = finite_value(value)
    parsed_baseline = finite_value(baseline)
    if parsed_value is None or parsed_baseline is None:
        return None
    return parsed_value - parsed_baseline


def classify_validation_row(
    metrics: dict[str, object],
    *,
    mean_delta: float | None,
    profit_delta: float | None,
    min_trades: int,
    min_mean_R: float,
    min_profit_factor_R: float,
    min_years: int,
    min_yearly_positive_ratio: float,
    min_period_positive_ratio: float,
) -> str:
    trades_count = safe_int(metrics.get("trades_count"))
    if trades_count < min_trades:
        return CLASS_INSUFFICIENT
    mean_R = finite_value(metrics.get("mean_R"))
    profit_factor_R = finite_value(metrics.get("profit_factor_R"))
    if mean_R is None or profit_factor_R is None:
        return CLASS_REJECTED
    if mean_R < min_mean_R or profit_factor_R < min_profit_factor_R:
        return CLASS_REJECTED
    if mean_delta is not None and mean_delta <= 0:
        return CLASS_REJECTED
    if profit_delta is not None and profit_delta <= 0:
        return CLASS_REJECTED
    yearly_ratio = finite_value(metrics.get("yearly_positive_ratio"))
    yearly_breakdown = str(metrics.get("yearly_breakdown") or "")
    year_count = len([part for part in yearly_breakdown.split("|") if part.strip()])
    monthly = finite_value(metrics.get("monthly_positive_ratio"))
    quarterly = finite_value(metrics.get("quarterly_positive_ratio"))
    if year_count < min_years:
        return CLASS_YEARLY
    if yearly_ratio is None or yearly_ratio < min_yearly_positive_ratio:
        return CLASS_YEARLY
    if monthly is not None and monthly < min_period_positive_ratio:
        return CLASS_YEARLY
    if quarterly is not None and quarterly < min_period_positive_ratio:
        return CLASS_YEARLY
    return CLASS_RETAINED


def finite_or_infinite_value(value: object) -> float | None:
    try:
        parsed = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if parsed is None or math.isnan(parsed):
        return None
    return parsed


def classify_sequential_validation_row(
    metrics: dict[str, object],
    *,
    min_trades: int,
    min_mean_R: float,
    min_profit_factor_R: float,
    min_yearly_positive_ratio: float,
    min_period_positive_ratio: float,
) -> str:
    trades_count = safe_int(metrics.get("sequential_trades_count"))
    if trades_count < min_trades:
        return CLASS_INSUFFICIENT
    mean_R = finite_value(metrics.get("sequential_mean_R"))
    profit_factor_R = finite_or_infinite_value(metrics.get("sequential_profit_factor_R"))
    if mean_R is None or profit_factor_R is None:
        return CLASS_REJECTED
    if mean_R <= min_mean_R or profit_factor_R <= min_profit_factor_R:
        return CLASS_REJECTED
    yearly = finite_value(metrics.get("sequential_yearly_positive_ratio"))
    quarterly = finite_value(metrics.get("sequential_quarterly_positive_ratio"))
    if yearly is None or yearly < min_yearly_positive_ratio:
        return CLASS_REJECTED
    if quarterly is None or quarterly < min_period_positive_ratio:
        return CLASS_REJECTED
    return CLASS_YEARLY


def default_row_loader(db_path: Path, symbol: str, timeframe: str) -> list[dict[str, object]]:
    return load_path_rows(db_path, symbol, timeframe)


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] = FIELDNAMES) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe_value(row.get(field)) for field in fieldnames})


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


def report_lines(rows: list[dict[str, object]], limit: int = 20) -> list[str]:
    if not rows:
        return ["- None."]
    return [
        "- {target} h{horizon} {group} {direction} {symbol} `{column}={value}`: class={classification}, trades={trades}, mean_R={mean_R}, profit_factor_R={pf}".format(
            target=row.get("target_family", ""),
            horizon=row.get("horizon", ""),
            group=row.get("group", ""),
            direction=row.get("direction", ""),
            symbol=row.get("symbol", ""),
            column=row.get("regime_column", ""),
            value=row.get("regime_value", ""),
            classification=row.get("classification", ""),
            trades=row.get("trades_count", ""),
            mean_R=num_text(row.get("mean_R")),
            pf=num_text(row.get("profit_factor_R")),
        )
        for row in rows[:limit]
    ]


def write_report(
    path: Path,
    *,
    input_csv: Path,
    selected_count: int,
    output_rows: list[dict[str, object]],
    args: argparse.Namespace,
) -> None:
    counts: dict[str, int] = {}
    for row in output_rows:
        classification = str(row.get("classification") or "")
        counts[classification] = counts.get(classification, 0) + 1
    lines = [
        "# Regime-Filtered Candidate Diagnostics",
        "",
        "## Research-Only Warning",
        "",
        "- Offline validation for selected historical regime review rows only.",
        "- No new features, multi-timeframe inputs, TP/SL optimization, sizing, broker actions, or deployment rules are added.",
        "- Labels remain review outcomes only.",
        "",
        "## Inputs",
        "",
        f"- Regime diagnostics CSV: `{input_csv}`",
        f"- Selected rows: `{selected_count}`",
        f"- Max candidates: `{args.max_candidates}`",
        f"- Allowed regime columns: `{', '.join(args.allowed_regime_column)}`",
        f"- Overlap policy: `{args.overlap_policy}`",
        f"- Bar-level no-overlap: `{bool(args.bar_level_no_overlap)}`",
        f"- Stress cost config requested: `{bool(args.stress_cost_config)}`",
        f"- Random baseline iterations requested: `{int(args.random_baseline_iterations)}`",
        "",
        "## Classification Counts",
        "",
        f"- {CLASS_REJECTED}: `{counts.get(CLASS_REJECTED, 0)}`",
        f"- {CLASS_RETAINED}: `{counts.get(CLASS_RETAINED, 0)}`",
        f"- {CLASS_YEARLY}: `{counts.get(CLASS_YEARLY, 0)}`",
        f"- {CLASS_INSUFFICIENT}: `{counts.get(CLASS_INSUFFICIENT, 0)}`",
        "",
        "## Reviewed Rows",
        "",
        *report_lines(output_rows),
        "",
        "## Guardrails",
        "",
        "- Deduplication collapses equivalent news timing views for the same branch context.",
        "- `no_overlap_per_symbol` is a selection-level policy unless `--bar-level-no-overlap` is enabled.",
        "- Bar-level replay is sequential offline validation only.",
        "- No output label changes the research-only status.",
    ]
    if bool(args.bar_level_no_overlap):
        lines.extend(
            [
                "",
                "## Sequential Outputs",
                "",
                "- Trade logs are written under `trade_logs/`.",
                "- Equity curves are written under `equity_curves/`.",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_optional_preparation_fields(row: dict[str, object], args: argparse.Namespace) -> None:
    stress_config = getattr(args, "stress_cost_config", None)
    random_iterations = int(getattr(args, "random_baseline_iterations", 0) or 0)
    row["stress_cost_config_requested"] = str(stress_config) if stress_config else ""
    row["stress_cost_not_available_reason"] = (
        "stress cost recomputation is not implemented in this diagnostic; no stress result was produced"
        if stress_config
        else ""
    )
    row["random_baseline_iterations"] = random_iterations
    row["random_baseline_not_available_reason"] = (
        "random baseline generation is not implemented in this diagnostic; no random result was produced"
        if random_iterations > 0
        else ""
    )


def append_note(row: dict[str, object], note: str) -> None:
    existing = [part.strip() for part in str(row.get("notes") or "").split(";") if part.strip()]
    if note and note not in existing:
        existing.append(note)
    row["notes"] = "; ".join(existing)


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> None:
    existing = [output_dir / file_name for file_name in (SUMMARY_FILE, REPORT_FILE) if (output_dir / file_name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Regime-filtered diagnostics outputs already exist under {output_dir}. Pass --overwrite to regenerate them."
        )


def run_regime_filtered_candidate_diagnostics(
    args: argparse.Namespace,
    *,
    row_loader: RowLoader = default_row_loader,
) -> dict[str, Path]:
    run_id = str(args.run_id or current_run_id())
    output_dir = Path(args.output_root) / run_id
    ensure_outputs_writable(output_dir, bool(args.overwrite))

    regime_rows, _headers = read_csv_with_headers(Path(args.regime_diagnostics_csv))
    selected = select_review_rows(
        regime_rows,
        min_trades=int(args.min_trades),
        min_mean_R=float(args.min_mean_R),
        min_profit_factor_R=float(args.min_profit_factor_R),
        allowed_regime_columns=tuple(args.allowed_regime_column),
        max_candidates=int(args.max_candidates),
        overlap_policy=str(args.overlap_policy),
    )

    output_rows: list[dict[str, object]] = []
    all_replay_events: list[CandidateReplayEvent] = []
    cost_config = load_cost_config(args.cost_config)
    for rank, review in enumerate(selected, start=1):
        source_rows = load_source_branch_rows(review)
        candidate_id = candidate_id_for_review(review)
        result = validate_review_row(
            review,
            source_rows=source_rows,
            db_path=Path(args.db_path),
            cost_config=cost_config,
            min_trades=int(args.validation_min_trades),
            min_mean_R=float(args.validation_min_mean_R),
            min_profit_factor_R=float(args.validation_min_profit_factor_R),
            min_years=int(args.min_years),
            min_yearly_positive_ratio=float(args.min_yearly_positive_ratio),
            min_period_positive_ratio=float(args.min_period_positive_ratio),
            overlap_policy=str(args.overlap_policy),
            row_loader=row_loader,
        )
        result["candidate_id"] = candidate_id
        result["selection_rank"] = rank
        apply_optional_preparation_fields(result, args)
        if bool(args.bar_level_no_overlap):
            replay_events, replay_notes = collect_candidate_replay_events(
                review,
                candidate_id=candidate_id,
                source_rows=source_rows,
                db_path=Path(args.db_path),
                cost_config=cost_config,
                min_trades=int(args.validation_min_trades),
                row_loader=row_loader,
            )
            all_replay_events.extend(replay_events)
            for note in replay_notes:
                append_note(result, note)
        output_rows.append(result)

    if bool(args.bar_level_no_overlap):
        replay_result = replay_events_without_symbol_overlap(all_replay_events)
        trade_log_dir = output_dir / "trade_logs"
        equity_curve_dir = output_dir / "equity_curves"
        for row in output_rows:
            candidate_id = str(row.get("candidate_id") or "")
            accepted_events = replay_result.accepted_by_candidate.get(candidate_id, [])
            skipped_due_to_overlap = replay_result.skipped_by_candidate.get(candidate_id, 0)
            apply_sequential_metrics(
                row,
                events=accepted_events,
                skipped_due_to_overlap=skipped_due_to_overlap,
                min_trades=int(args.validation_min_trades),
                min_mean_R=float(args.validation_min_mean_R),
                min_profit_factor_R=float(args.validation_min_profit_factor_R),
                min_yearly_positive_ratio=float(args.min_yearly_positive_ratio),
                min_period_positive_ratio=float(args.min_period_positive_ratio),
            )
            append_note(row, "bar-level no-overlap replay applied")
            write_csv(
                trade_log_dir / f"{candidate_id}_trade_log.csv",
                trade_log_rows(accepted_events, skipped_due_to_overlap),
                TRADE_LOG_FIELDNAMES,
            )
            write_csv(
                equity_curve_dir / f"{candidate_id}_equity_curve.csv",
                equity_curve_rows(accepted_events),
                EQUITY_CURVE_FIELDNAMES,
            )

    summary_path = output_dir / SUMMARY_FILE
    report_path = output_dir / REPORT_FILE
    write_csv(summary_path, output_rows)
    write_report(
        report_path,
        input_csv=Path(args.regime_diagnostics_csv),
        selected_count=len(selected),
        output_rows=output_rows,
        args=args,
    )
    return {
        "regime_filtered_candidate_summary": summary_path,
        "regime_filtered_candidate_report": report_path,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run research-only validation for selected regime review rows."
    )
    parser.add_argument("regime_diagnostics_csv", type=Path)
    parser.add_argument("--min-trades", type=int, default=200)
    parser.add_argument("--min-mean-R", type=float, default=0.0, dest="min_mean_R")
    parser.add_argument("--min-profit-factor-R", type=float, default=1.0, dest="min_profit_factor_R")
    parser.add_argument("--allowed-regime-column", action="append")
    parser.add_argument("--max-candidates", type=int, default=20)
    parser.add_argument("--overlap-policy", choices=("no_overlap_per_symbol", "allow_overlap"), default="no_overlap_per_symbol")
    parser.add_argument(
        "--bar-level-no-overlap",
        action="store_true",
        help="Replay selected rows chronologically and skip same-symbol entries while an earlier same-symbol row is open.",
    )
    parser.add_argument("--validation-min-trades", type=int, default=200)
    parser.add_argument("--validation-min-mean-R", type=float, default=0.0, dest="validation_min_mean_R")
    parser.add_argument("--validation-min-profit-factor-R", type=float, default=1.05, dest="validation_min_profit_factor_R")
    parser.add_argument("--min-years", type=int, default=2)
    parser.add_argument("--min-yearly-positive-ratio", type=float, default=0.5)
    parser.add_argument("--min-period-positive-ratio", type=float, default=0.5)
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--stress-cost-config", type=Path)
    parser.add_argument("--random-baseline-iterations", type=int, default=0)
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=f"Default: {DEFAULT_OUTPUT_ROOT}")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    args.allowed_regime_column = args.allowed_regime_column or list(DEFAULT_ALLOWED_REGIME_COLUMNS)
    return args


def main() -> int:
    try:
        outputs = run_regime_filtered_candidate_diagnostics(parse_args())
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"Regime-filtered diagnostics failed: {exc}")
        return 1
    print("Regime-filtered diagnostics complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
