"""Research-only stress validation for one explicit regime candidate.

This utility replays one fixed historical candidate with optional bar-level
same-symbol no-overlap. It does not add features, optimize TP/SL settings,
create operational rules, size positions, or use broker APIs.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import dataclass, field, replace
from datetime import datetime
import hashlib
import math
from pathlib import Path
import random
import re
import sys
from typing import Any, Callable


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from research_costs import (
        bps_cost,
        cost_config_source,
        fallback_spread_source_for_symbol,
        load_cost_config,
        point_size_for_symbol,
        point_size_source_for_symbol,
        symbol_cost_config,
    )
    from research_metrics import csv_safe_value, parse_metric_timestamp
    from diagnose_regime_filter_candidates import (
        filters_from_source_row,
        infer_direction,
        infer_group,
        infer_horizon,
        infer_symbol,
        infer_target_family,
        infer_timeframe,
        read_csv_with_headers,
        safe_int,
    )
    from run_tp_sl_path_backtests import (
        DATABASE_PATH,
        DEFAULT_ATR_COLUMN,
        DEFAULT_SAME_BAR_POLICY,
        PathConfig,
        PathOutcome,
        cost_in_R,
        finite_value,
        hit_flags,
        load_path_rows,
        predicate_for_filters,
        price_levels,
        selected_exit,
        simulate_path_exit,
    )
    from target_families import normalize_direction, target_family_spec
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.research_costs import (
        bps_cost,
        cost_config_source,
        fallback_spread_source_for_symbol,
        load_cost_config,
        point_size_for_symbol,
        point_size_source_for_symbol,
        symbol_cost_config,
    )
    from scripts.research_metrics import csv_safe_value, parse_metric_timestamp
    from scripts.diagnose_regime_filter_candidates import (
        filters_from_source_row,
        infer_direction,
        infer_group,
        infer_horizon,
        infer_symbol,
        infer_target_family,
        infer_timeframe,
        read_csv_with_headers,
        safe_int,
    )
    from scripts.run_tp_sl_path_backtests import (
        DATABASE_PATH,
        DEFAULT_ATR_COLUMN,
        DEFAULT_SAME_BAR_POLICY,
        PathConfig,
        PathOutcome,
        cost_in_R,
        finite_value,
        hit_flags,
        load_path_rows,
        predicate_for_filters,
        price_levels,
        selected_exit,
        simulate_path_exit,
    )
    from scripts.target_families import normalize_direction, target_family_spec


DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "regime_candidate_stress"
SUMMARY_FILE = "candidate_stress_summary.csv"
REPORT_FILE = "candidate_stress_report.md"
BASE_TRADE_LOG_FILE = "trade_log_base.csv"
BASE_EQUITY_CURVE_FILE = "equity_curve_base.csv"
STRESS_TRADE_LOG_FILE = "trade_log_stress.csv"
STRESS_EQUITY_CURVE_FILE = "equity_curve_stress.csv"
YEARLY_FILE = "yearly_validation.csv"
WALK_FORWARD_FILE = "walk_forward_validation.csv"
RANDOM_BASELINE_FILE = "random_baseline_summary.csv"

MIN_SEQUENTIAL_TRADES = 50
STRESS_SPREAD_POLICY_STANDARD = "standard"
STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK = "max_row_or_fallback"
STRESS_SPREAD_POLICY_FALLBACK_OVERRIDE = "fallback_override"
STRESS_SPREAD_POLICIES = (
    STRESS_SPREAD_POLICY_STANDARD,
    STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK,
    STRESS_SPREAD_POLICY_FALLBACK_OVERRIDE,
)

FINAL_LABELS = {
    "STRESS_REJECTED",
    "STRESS_REVIEW_RETAINED",
    "NEEDS_WALK_FORWARD_REVIEW",
    "INSUFFICIENT_SEQUENTIAL_TRADES",
    "RANDOM_BASELINE_NOT_PASSED",
    "COST_STRESS_NOT_PASSED",
    "EXACT_CANDIDATE_NOT_AVAILABLE",
}

SUMMARY_FIELDNAMES = [
    "symbol",
    "direction",
    "timeframe",
    "target_family",
    "horizon",
    "regime_column",
    "regime_value",
    "tp_atr",
    "sl_atr",
    "atr_column",
    "same_bar_policy",
    "bar_level_no_overlap",
    "candidate_scope",
    "accept_broad_regime_scope",
    "feature_condition",
    "exact_candidate_not_available_reason",
    "source_rows_loaded",
    "rows_matching_symbol_direction_regime",
    "rows_matching_feature_condition",
    "candidate_entries_before_no_overlap",
    "filtered_out_reason_counts",
    "sequential_trades_count",
    "skipped_due_to_overlap",
    "mean_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
    "max_consecutive_losses",
    "max_consecutive_non_positive_trades",
    "tp_hit_rate",
    "sl_hit_rate",
    "timeout_rate",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "yearly_positive_ratio",
    "top_5_percent_contribution_pct",
    "max_trades_in_one_month",
    "top_month_contribution_pct",
    "base_cost_config_path",
    "stress_cost_config_path",
    "stress_spread_policy",
    "base_cost_config_hash",
    "stress_cost_config_hash",
    "base_cost_config_source",
    "stress_cost_config_source",
    "base_point_size_source",
    "stress_point_size_source",
    "base_point_size",
    "stress_point_size",
    "base_spread_source_used",
    "stress_spread_source_used",
    "base_spread_source_counts",
    "stress_spread_source_counts",
    "base_row_level_spread_count",
    "stress_row_level_spread_count",
    "base_fallback_spread_count",
    "stress_fallback_spread_count",
    "base_max_row_or_fallback_count",
    "stress_max_row_or_fallback_count",
    "base_fallback_spread_source",
    "stress_fallback_spread_source",
    "base_fallback_spread_points",
    "stress_fallback_spread_points",
    "base_fallback_spread_used",
    "stress_fallback_spread_used",
    "base_slippage_bps_round_trip",
    "stress_slippage_bps_round_trip",
    "base_commission_bps_round_trip",
    "stress_commission_bps_round_trip",
    "base_total_cost_R",
    "stress_total_cost_R",
    "mean_cost_R_base",
    "mean_cost_R_stress",
    "cost_R_delta_mean",
    "net_R_delta_mean",
    "cost_stress_no_effect_explanation",
    "stress_applied",
    "stress_changed_cost_R",
    "stress_cost_R_changed",
    "stress_cost_no_effect_warning",
    "stress_cost_config_requested",
    "stress_cost_not_available_reason",
    "stress_sequential_trades_count",
    "stress_mean_R",
    "stress_profit_factor_R",
    "stress_cumulative_R",
    "stress_max_drawdown_R",
    "stress_mean_R_delta",
    "stress_profit_factor_R_delta",
    "random_baseline_iterations",
    "random_baseline_available",
    "random_baseline_not_available_reason",
    "random_mean_R_mean",
    "random_mean_R_median",
    "random_mean_R_p95",
    "random_profit_factor_R_mean",
    "random_profit_factor_R_p95",
    "random_max_drawdown_R_median",
    "candidate_mean_R_vs_random_p95",
    "candidate_profit_factor_R_vs_random_p95",
    "candidate_percentile_vs_random_mean_R",
    "final_research_label",
]

TRADE_LOG_FIELDNAMES = [
    "symbol",
    "direction",
    "target_family",
    "horizon",
    "regime_column",
    "regime_value",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "exit_reason",
    "bars_held",
    "tp_atr",
    "sl_atr",
    "R",
    "cost_R",
    "net_R",
]

EQUITY_FIELDNAMES = [
    "trade_index",
    "exit_time",
    "cumulative_R",
    "drawdown_R",
]

YEARLY_FIELDNAMES = [
    "year",
    "trades_count",
    "mean_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
    "tp_hit_rate",
    "sl_hit_rate",
    "timeout_rate",
]

WALK_FORWARD_FIELDNAMES = [
    "split_id",
    "train_start",
    "train_end",
    "test_start",
    "test_end",
    "train_trades",
    "train_mean_R",
    "train_profit_factor_R",
    "test_trades",
    "test_mean_R",
    "test_profit_factor_R",
    "test_max_drawdown_R",
    "test_classification",
]

RANDOM_FIELDNAMES = [
    "iterations",
    "random_mean_R_mean",
    "random_mean_R_median",
    "random_mean_R_p95",
    "random_profit_factor_R_mean",
    "random_profit_factor_R_p95",
    "random_max_drawdown_R_median",
    "candidate_mean_R_vs_random_p95",
    "candidate_profit_factor_R_vs_random_p95",
    "candidate_percentile_vs_random_mean_R",
    "random_baseline_available",
    "random_baseline_not_available_reason",
]


@dataclass(frozen=True)
class CandidateSpec:
    symbol: str
    direction: str
    timeframe: str
    horizon: int
    target_family: str
    regime_column: str
    regime_value: str
    tp_atr: float
    sl_atr: float
    atr_column: str
    same_bar_policy: str


@dataclass(frozen=True)
class CandidateScope:
    name: str
    filter_sets: tuple[tuple[str, ...], ...] = ()
    condition_text: str = ""
    exact_candidate_not_available_reason: str = ""


@dataclass
class ReplayAudit:
    source_rows_loaded: int = 0
    rows_matching_symbol_direction_regime: int = 0
    rows_matching_feature_condition: int | None = None
    candidate_entries_before_no_overlap: int = 0
    filtered_out_reason_counts: Counter[str] = field(default_factory=Counter)

    def as_summary_fields(self) -> dict[str, object]:
        return {
            "source_rows_loaded": self.source_rows_loaded,
            "rows_matching_symbol_direction_regime": self.rows_matching_symbol_direction_regime,
            "rows_matching_feature_condition": self.rows_matching_feature_condition,
            "candidate_entries_before_no_overlap": self.candidate_entries_before_no_overlap,
            "filtered_out_reason_counts": serialize_counter(self.filtered_out_reason_counts),
        }


@dataclass(frozen=True)
class ReplayEvent:
    spec: CandidateSpec
    config: PathConfig
    outcome: PathOutcome
    entry_timestamp: datetime | None
    exit_timestamp: datetime | None
    exit_row_index: int


@dataclass(frozen=True)
class ReplayResult:
    events: list[ReplayEvent]
    skipped_due_to_overlap: int


RowLoader = Callable[[Path, str, str], list[dict[str, object]]]


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_horizon(value: object) -> int:
    text = str(value or "").strip().lower()
    if text.startswith("h"):
        text = text[1:]
    horizon = int(text)
    if horizon <= 0:
        raise ValueError("--horizon must be greater than zero.")
    return horizon


def resolve_candidate_spec(args: argparse.Namespace) -> CandidateSpec:
    family = target_family_spec(args.target_family)
    tp_atr = float(args.tp_atr)
    sl_atr = float(args.sl_atr)
    if tp_atr <= 0 or sl_atr <= 0:
        raise ValueError("--tp-atr and --sl-atr must be greater than zero.")
    if not math.isclose(tp_atr, family.tp_atr) or not math.isclose(sl_atr, family.sl_atr):
        raise ValueError(
            f"--tp-atr/--sl-atr must match {family.name}: "
            f"{family.tp_atr:g}/{family.sl_atr:g}."
        )
    return CandidateSpec(
        symbol=str(args.symbol).strip().upper(),
        direction=normalize_direction(args.direction),
        timeframe=str(args.timeframe).strip().upper(),
        horizon=parse_horizon(args.horizon),
        target_family=family.name,
        regime_column=str(args.regime_column).strip(),
        regime_value=str(args.regime_value).strip(),
        tp_atr=tp_atr,
        sl_atr=sl_atr,
        atr_column=str(args.atr_column).strip(),
        same_bar_policy=str(args.same_bar_policy).strip(),
    )


def split_filter_text(value: object) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text or text == "ALL_VALID_ROWS":
        return ()
    parts: list[str] = []
    for chunk in text.split("|"):
        for item in re.split(r"\s+AND\s+", chunk.strip(), flags=re.IGNORECASE):
            item = item.strip()
            if item:
                parts.append(item)
    return tuple(parts)


def condition_filters_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    filters: list[str] = []
    for condition in getattr(args, "condition", None) or []:
        filters.extend(split_filter_text(condition))
    return tuple(filters)


def split_source_files(value: object) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    return tuple(item.strip() for item in re.split(r"[|;]", text) if item.strip())


def resolve_source_path(label: str) -> Path:
    path = Path(label)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def summary_row_matches_spec(row: dict[str, str], spec: CandidateSpec) -> bool:
    row_symbol = str(row.get("symbol") or "").strip().upper()
    row_direction = str(row.get("direction") or "").strip().lower()
    row_family = str(row.get("target_family") or "").strip()
    row_regime_column = str(row.get("regime_column") or "").strip()
    row_regime_value = str(row.get("regime_value") or "").strip()
    try:
        row_horizon = parse_horizon(row.get("horizon"))
    except (TypeError, ValueError):
        return False
    return (
        row_symbol == spec.symbol
        and row_direction == spec.direction
        and row_family == spec.target_family
        and row_horizon == spec.horizon
        and row_regime_column == spec.regime_column
        and row_regime_value == spec.regime_value
    )


def direct_filter_sets_from_summary_row(row: dict[str, str]) -> tuple[tuple[str, ...], ...]:
    for field in (
        "feature_condition",
        "feature_conditions",
        "condition",
        "conditions",
        "filters",
        "source_filters",
        "combination_key",
    ):
        filters = split_filter_text(row.get(field))
        if filters:
            return (filters,)
    filters = tuple(
        item
        for item in (
            str(row.get("source_scenario_1") or row.get("scenario_1") or "").strip(),
            str(row.get("source_scenario_2") or row.get("scenario_2") or "").strip(),
        )
        if item
    )
    return (filters,) if filters else ()


def source_row_matches_summary(
    source_row: dict[str, str],
    path: Path,
    *,
    spec: CandidateSpec,
    group: str,
) -> bool:
    symbol = infer_symbol(source_row, path)
    if symbol != spec.symbol:
        return False
    if infer_direction(source_row, path) != spec.direction:
        return False
    if infer_target_family(source_row, path) != spec.target_family:
        return False
    if safe_int(infer_horizon(source_row, path)) != spec.horizon:
        return False
    if group and infer_group(source_row, path, symbol) != group:
        return False
    timeframe = infer_timeframe(source_row, path)
    return not timeframe or timeframe == spec.timeframe


def filter_sets_from_summary_sources(row: dict[str, str], spec: CandidateSpec) -> tuple[tuple[str, ...], ...]:
    source_files = split_source_files(row.get("source_files"))
    group = str(row.get("group") or "").strip().upper()
    filter_sets: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for label in source_files:
        path = resolve_source_path(label)
        if not path.exists():
            continue
        source_rows, _headers = read_csv_with_headers(path)
        for source_row in source_rows:
            if not source_row_matches_summary(source_row, path, spec=spec, group=group):
                continue
            filters = filters_from_source_row(source_row)
            if filters and filters not in seen:
                seen.add(filters)
                filter_sets.append(filters)
    return tuple(filter_sets)


def condition_text_from_filter_sets(filter_sets: tuple[tuple[str, ...], ...]) -> str:
    if not filter_sets:
        return ""
    return " OR ".join(" AND ".join(filters) for filters in filter_sets)


def candidate_scope_from_summary(args: argparse.Namespace, spec: CandidateSpec) -> CandidateScope:
    if not args.candidate_summary_csv or not args.candidate_id:
        return CandidateScope(
            name="exact_feature_combination",
            exact_candidate_not_available_reason=(
                "--candidate-summary-csv and --candidate-id must be provided together for summary-based exact mode"
            ),
        )
    path = Path(args.candidate_summary_csv)
    if not path.exists():
        return CandidateScope(
            name="exact_feature_combination",
            exact_candidate_not_available_reason=f"candidate summary CSV was not found: {path}",
        )
    rows, _headers = read_csv_with_headers(path)
    selected = next((row for row in rows if str(row.get("candidate_id") or "").strip() == args.candidate_id), None)
    if selected is None:
        return CandidateScope(
            name="exact_feature_combination",
            exact_candidate_not_available_reason=f"candidate_id {args.candidate_id!r} was not found in {path}",
        )
    if not summary_row_matches_spec(selected, spec):
        return CandidateScope(
            name="exact_feature_combination",
            exact_candidate_not_available_reason=(
                "candidate summary row does not match the explicit symbol/direction/regime/target arguments"
            ),
        )
    filter_sets = direct_filter_sets_from_summary_row(selected)
    if not filter_sets:
        filter_sets = filter_sets_from_summary_sources(selected, spec)
    if not filter_sets:
        return CandidateScope(
            name="exact_feature_combination",
            exact_candidate_not_available_reason=(
                "exact filters could not be reconstructed from the candidate summary row or its source_files"
            ),
        )
    return CandidateScope(
        name="exact_feature_combination",
        filter_sets=filter_sets,
        condition_text=condition_text_from_filter_sets(filter_sets),
    )


def resolve_candidate_scope(args: argparse.Namespace, spec: CandidateSpec) -> CandidateScope:
    explicit_filters = condition_filters_from_args(args)
    requested_summary = bool(args.candidate_summary_csv or args.candidate_id)
    if explicit_filters and requested_summary:
        return CandidateScope(
            name="exact_feature_combination",
            exact_candidate_not_available_reason=(
                "--condition cannot be combined with --candidate-summary-csv/--candidate-id"
            ),
        )
    if explicit_filters:
        return CandidateScope(
            name="exact_feature_combination",
            filter_sets=(explicit_filters,),
            condition_text=condition_text_from_filter_sets((explicit_filters,)),
        )
    if requested_summary:
        return candidate_scope_from_summary(args, spec)
    return CandidateScope(name="broad_regime_only")


def prepare_scope_predicate(
    rows: list[dict[str, object]],
    scope: CandidateScope,
) -> tuple[CandidateScope, Callable[[dict[str, object]], bool] | None]:
    if scope.name != "exact_feature_combination":
        return scope, None
    if scope.exact_candidate_not_available_reason:
        return scope, None
    predicates = []
    try:
        for filter_set in scope.filter_sets:
            predicates.append(predicate_for_filters(rows, filter_set))
    except ValueError as exc:
        return (
            replace(scope, exact_candidate_not_available_reason=f"exact feature condition could not be applied: {exc}"),
            None,
        )
    if not predicates:
        return (
            replace(scope, exact_candidate_not_available_reason="exact feature condition was empty"),
            None,
        )
    return scope, lambda row: any(predicate(row) for predicate in predicates)


def serialize_counter(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return ";".join(f"{key}={counter[key]}" for key in sorted(counter))


def path_config_for_spec(spec: CandidateSpec, *, cost_mode: str, return_mode: str) -> PathConfig:
    return PathConfig(
        symbol=spec.symbol,
        timeframe=spec.timeframe,
        direction=spec.direction,
        horizon=spec.horizon,
        tp_atr=spec.tp_atr,
        sl_atr=spec.sl_atr,
        atr_column=spec.atr_column,
        same_bar_policy=spec.same_bar_policy,
        filters=(),
        cost_mode=cost_mode,
        return_mode=return_mode,
        min_trades=0,
    )


def value_matches_regime(row_value: object, expected: str) -> bool:
    actual = str(row_value if row_value is not None else "").strip()
    if actual == expected:
        return True
    expected_number = finite_value(expected)
    actual_number = finite_value(actual)
    return expected_number is not None and actual_number is not None and expected_number == actual_number


def eligible_row_indexes(
    rows: list[dict[str, object]],
    spec: CandidateSpec,
    *,
    scope: CandidateScope | None = None,
    scope_predicate: Callable[[dict[str, object]], bool] | None = None,
    audit: ReplayAudit | None = None,
) -> list[int]:
    indexes: list[int] = []
    exact_mode = scope is not None and scope.name == "exact_feature_combination"
    feature_matches = 0
    for index, row in enumerate(rows):
        if not value_matches_regime(row.get(spec.regime_column), spec.regime_value):
            if audit is not None:
                audit.filtered_out_reason_counts["regime_mismatch"] += 1
            continue
        if audit is not None:
            audit.rows_matching_symbol_direction_regime += 1
        if exact_mode:
            if scope_predicate is None or not scope_predicate(row):
                if audit is not None:
                    audit.filtered_out_reason_counts["feature_condition_false"] += 1
                continue
            feature_matches += 1
        indexes.append(index)
    if audit is not None and exact_mode:
        audit.rows_matching_feature_condition = feature_matches
    return indexes


def close_at_exit(rows: list[dict[str, object]], row_index: int) -> float | None:
    if row_index < 0 or row_index >= len(rows):
        return None
    return finite_value(rows[row_index].get("close"))


def simulate_exit_allow_end_of_data(
    rows: list[dict[str, object]],
    row_index: int,
    *,
    config: PathConfig,
    cost_config: dict[str, Any],
) -> tuple[PathOutcome | None, str | None]:
    outcome, reason = simulate_path_exit(rows, row_index, config=config, cost_config=cost_config)
    if outcome is not None or reason != "insufficient_future_bars":
        return outcome, reason

    row = rows[row_index]
    entry_price = finite_value(row.get("close"))
    atr = finite_value(row.get(config.atr_column))
    if entry_price is None or entry_price <= 0:
        return None, "invalid_entry_close"
    if atr is None or atr <= 0:
        return None, "invalid_or_missing_atr"

    sl_distance = config.sl_atr * atr
    if sl_distance <= 0:
        return None, "invalid_sl_distance"

    tp_price, sl_price = price_levels(entry_price, atr, config)
    future_rows = rows[row_index + 1 :]
    gross_R: float | None = None
    exit_reason = "end_of_data"
    exit_bars = len(future_rows)
    exit_time = row.get("time_server")
    same_bar_conflict = False

    for bars_ahead, future_row in enumerate(future_rows, start=1):
        high_price = finite_value(future_row.get("high"))
        low_price = finite_value(future_row.get("low"))
        if high_price is None or low_price is None:
            return None, "missing_future_ohlc"
        take_hit, stop_hit = hit_flags(high_price, low_price, tp_price, sl_price, config.direction)
        selected, conflict = selected_exit(
            take_hit=take_hit,
            stop_hit=stop_hit,
            same_bar_policy=config.same_bar_policy,
        )
        if selected is None:
            continue
        exit_reason = selected
        exit_bars = bars_ahead
        exit_time = future_row.get("time_server")
        same_bar_conflict = conflict
        gross_R = (config.tp_atr * atr) / sl_distance if selected == "tp" else -1.0
        break

    if gross_R is None:
        exit_row = rows[-1] if future_rows else row
        exit_time = exit_row.get("time_server")
        horizon_close = finite_value(exit_row.get("close"))
        if horizon_close is None:
            return None, "missing_end_of_data_close"
        move = horizon_close - entry_price if config.direction == "long" else entry_price - horizon_close
        gross_R = move / sl_distance

    estimated_cost_return, cost_R = cost_in_R(
        row=row,
        symbol=config.symbol,
        entry_price=entry_price,
        sl_distance=sl_distance,
        cost_config=cost_config,
        cost_mode=config.cost_mode,
    )
    net_R = float(gross_R) - cost_R
    selected_R = net_R if config.return_mode == "net" else float(gross_R)
    return (
        PathOutcome(
            row=row,
            row_index=row_index,
            time_server=row.get("time_server"),
            exit_time=exit_time,
            exit_bars=int(exit_bars),
            exit_reason=exit_reason,
            entry_price=entry_price,
            atr=atr,
            sl_distance=sl_distance,
            tp_price=tp_price,
            sl_price=sl_price,
            gross_R=float(gross_R),
            estimated_cost_return=estimated_cost_return,
            cost_R=cost_R,
            net_R=net_R,
            selected_R=selected_R,
            same_bar_conflict=same_bar_conflict,
        ),
        None,
    )


def configured_fallback_spread(symbol: str, cost_config: dict[str, Any]) -> tuple[str, float | None]:
    fallback_source, fallback_spread = fallback_spread_source_for_symbol(symbol, cost_config)
    if fallback_spread is not None and fallback_spread >= 0:
        return fallback_source, fallback_spread
    return fallback_source, None


def row_level_spread(row: dict[str, object]) -> tuple[str, float | None]:
    spread = nonnegative_finite_value(row.get("spread"))
    if spread is not None:
        return "spread", spread
    spread_avg = nonnegative_finite_value(row.get("spread_avg_20"))
    if spread_avg is not None:
        return "spread_avg_20", spread_avg
    return "missing", None


def selected_spread_for_policy(
    row: dict[str, object],
    symbol: str,
    cost_config: dict[str, Any],
    stress_spread_policy: str,
) -> tuple[str, float | None]:
    point_size = point_size_for_symbol(symbol, cost_config)
    if point_size is None or point_size <= 0:
        return "missing_point_size", None

    row_source, row_spread = row_level_spread(row)
    fallback_source, fallback_spread = configured_fallback_spread(symbol, cost_config)

    if stress_spread_policy == STRESS_SPREAD_POLICY_FALLBACK_OVERRIDE:
        if fallback_spread is not None:
            return fallback_source, fallback_spread
        if row_spread is not None:
            return row_source, row_spread
        return "missing", None

    if stress_spread_policy == STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK:
        if row_spread is not None and fallback_spread is not None:
            if fallback_spread > row_spread:
                return fallback_source, fallback_spread
            return row_source, row_spread
        if fallback_spread is not None:
            return fallback_source, fallback_spread
        if row_spread is not None:
            return row_source, row_spread
        return "missing", None

    if row_spread is not None:
        return row_source, row_spread
    if fallback_spread is not None:
        return fallback_source, fallback_spread
    return "missing", None


def max_row_or_fallback_selected(
    row: dict[str, object],
    symbol: str,
    cost_config: dict[str, Any],
    stress_spread_policy: str,
) -> bool:
    if stress_spread_policy != STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK:
        return False
    selected_source, _selected_spread = selected_spread_for_policy(
        row,
        symbol,
        cost_config,
        stress_spread_policy,
    )
    if "fallback_spread_points" not in selected_source:
        return False
    _row_source, row_spread = row_level_spread(row)
    _fallback_source, fallback_spread = configured_fallback_spread(symbol, cost_config)
    return row_spread is not None and fallback_spread is not None and fallback_spread > row_spread


def cost_row_for_spread_policy(
    row: dict[str, object],
    symbol: str,
    cost_config: dict[str, Any],
    stress_spread_policy: str,
) -> dict[str, object]:
    if stress_spread_policy == STRESS_SPREAD_POLICY_STANDARD:
        return row
    _source, selected_spread = selected_spread_for_policy(row, symbol, cost_config, stress_spread_policy)
    if selected_spread is None:
        return row
    cost_row = dict(row)
    cost_row["spread"] = selected_spread
    return cost_row


def outcome_with_spread_policy(
    outcome: PathOutcome,
    *,
    config: PathConfig,
    cost_config: dict[str, Any],
    stress_spread_policy: str,
) -> PathOutcome:
    if stress_spread_policy == STRESS_SPREAD_POLICY_STANDARD or config.cost_mode != "estimated":
        return outcome
    cost_row = cost_row_for_spread_policy(
        outcome.row,
        config.symbol,
        cost_config,
        stress_spread_policy,
    )
    estimated_cost_return, cost_R = cost_in_R(
        row=cost_row,
        symbol=config.symbol,
        entry_price=outcome.entry_price,
        sl_distance=outcome.sl_distance,
        cost_config=cost_config,
        cost_mode=config.cost_mode,
    )
    net_R = float(outcome.gross_R) - cost_R
    selected_R = net_R if config.return_mode == "net" else float(outcome.gross_R)
    return replace(
        outcome,
        estimated_cost_return=estimated_cost_return,
        cost_R=cost_R,
        net_R=net_R,
        selected_R=selected_R,
    )


def collect_replay_events(
    rows: list[dict[str, object]],
    spec: CandidateSpec,
    *,
    config: PathConfig,
    cost_config: dict[str, Any],
    scope: CandidateScope | None = None,
    scope_predicate: Callable[[dict[str, object]], bool] | None = None,
    audit: ReplayAudit | None = None,
    stress_spread_policy: str = STRESS_SPREAD_POLICY_STANDARD,
) -> list[ReplayEvent]:
    events: list[ReplayEvent] = []
    for row_index in eligible_row_indexes(
        rows,
        spec,
        scope=scope,
        scope_predicate=scope_predicate,
        audit=audit,
    ):
        outcome, reason = simulate_exit_allow_end_of_data(
            rows,
            row_index,
            config=config,
            cost_config=cost_config,
        )
        if outcome is None:
            if audit is not None:
                audit.filtered_out_reason_counts[f"path_unavailable:{reason or 'unknown'}"] += 1
            continue
        outcome = outcome_with_spread_policy(
            outcome,
            config=config,
            cost_config=cost_config,
            stress_spread_policy=stress_spread_policy,
        )
        events.append(
            ReplayEvent(
                spec=spec,
                config=config,
                outcome=outcome,
                entry_timestamp=parse_metric_timestamp(outcome.time_server),
                exit_timestamp=parse_metric_timestamp(outcome.exit_time),
                exit_row_index=row_index + int(outcome.exit_bars),
            )
        )
    if audit is not None:
        audit.candidate_entries_before_no_overlap = len(events)
        if scope is not None and scope.name == "exact_feature_combination" and audit.rows_matching_feature_condition is None:
            audit.rows_matching_feature_condition = 0
    return sorted(
        events,
        key=lambda event: (
            event.entry_timestamp or datetime.max,
            event.outcome.row_index,
        ),
    )


def apply_bar_level_no_overlap(events: list[ReplayEvent], enabled: bool) -> ReplayResult:
    if not enabled:
        return ReplayResult(events=list(events), skipped_due_to_overlap=0)
    accepted: list[ReplayEvent] = []
    open_until_by_symbol: dict[str, tuple[datetime | None, int]] = {}
    skipped = 0
    for event in events:
        symbol = event.config.symbol
        open_until_time, open_until_index = open_until_by_symbol.get(symbol, (None, -1))
        overlaps_by_time = (
            event.entry_timestamp is not None
            and open_until_time is not None
            and event.entry_timestamp <= open_until_time
        )
        overlaps_by_index = event.outcome.row_index <= open_until_index
        if overlaps_by_time or overlaps_by_index:
            skipped += 1
            continue
        accepted.append(event)
        current_until = open_until_by_symbol.get(symbol)
        if current_until is None or event.exit_row_index >= current_until[1]:
            open_until_by_symbol[symbol] = (event.exit_timestamp, event.exit_row_index)
    return ReplayResult(events=accepted, skipped_due_to_overlap=skipped)


def period_key(timestamp_value: object, period: str) -> tuple[int, int] | None:
    timestamp = parse_metric_timestamp(timestamp_value)
    if timestamp is None:
        return None
    if period == "month":
        return timestamp.year, timestamp.month
    if period == "quarter":
        return timestamp.year, (timestamp.month - 1) // 3 + 1
    if period == "year":
        return timestamp.year, 1
    raise ValueError(f"Unsupported period: {period}")


def positive_period_ratio(periods: dict[tuple[int, int], float]) -> float | None:
    if not periods:
        return None
    values = [periods[key] for key in sorted(periods)]
    return sum(1 for value in values if value > 0) / len(values)


def profit_factor(values: list[float]) -> float | None:
    profit = sum(value for value in values if value > 0)
    loss = sum(abs(value) for value in values if value < 0)
    if loss == 0:
        return None if profit == 0 else float("inf")
    return profit / loss


def finite_or_infinite(value: object) -> float | None:
    try:
        parsed = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if parsed is None or math.isnan(parsed):
        return None
    return parsed


def equity_curve_rows(events: list[ReplayEvent]) -> list[dict[str, object]]:
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


def max_consecutive(values: list[float], predicate: Callable[[float], bool]) -> int:
    current = 0
    maximum = 0
    for value in values:
        if predicate(value):
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def replay_metrics(events: list[ReplayEvent], skipped_due_to_overlap: int = 0) -> dict[str, object]:
    values = [float(event.outcome.selected_R) for event in events]
    count = len(values)
    if count == 0:
        return {
            "sequential_trades_count": 0,
            "skipped_due_to_overlap": skipped_due_to_overlap,
            "mean_R": None,
            "profit_factor_R": None,
            "cumulative_R": 0.0,
            "max_drawdown_R": None,
            "max_consecutive_losses": 0,
            "max_consecutive_non_positive_trades": 0,
            "tp_hit_rate": None,
            "sl_hit_rate": None,
            "timeout_rate": None,
            "monthly_positive_ratio": None,
            "quarterly_positive_ratio": None,
            "yearly_positive_ratio": None,
            "top_5_percent_contribution_pct": None,
            "max_trades_in_one_month": 0,
            "top_month_contribution_pct": None,
        }

    monthly_R: dict[tuple[int, int], float] = {}
    quarterly_R: dict[tuple[int, int], float] = {}
    yearly_R: dict[tuple[int, int], float] = {}
    monthly_counts: dict[tuple[int, int], int] = {}
    for event, value in zip(events, values):
        for period, target in (("month", monthly_R), ("quarter", quarterly_R), ("year", yearly_R)):
            key = period_key(event.outcome.exit_time, period)
            if key is not None:
                target[key] = target.get(key, 0.0) + value
                if period == "month":
                    monthly_counts[key] = monthly_counts.get(key, 0) + 1

    curve = equity_curve_rows(events)
    max_drawdown = max((float(row["drawdown_R"]) for row in curve), default=0.0)
    positive_values = sorted((value for value in values if value > 0), reverse=True)
    positive_total = sum(positive_values)
    top_5 = None
    if positive_total > 0:
        top_count = max(1, math.ceil(count * 0.05))
        top_5 = sum(positive_values[:top_count]) / positive_total * 100
    cumulative = sum(values)
    top_month = None
    if cumulative > 0 and monthly_R:
        top_month = max(monthly_R.values()) / cumulative * 100
    return {
        "sequential_trades_count": count,
        "skipped_due_to_overlap": skipped_due_to_overlap,
        "mean_R": cumulative / count,
        "profit_factor_R": profit_factor(values),
        "cumulative_R": cumulative,
        "max_drawdown_R": max_drawdown,
        "max_consecutive_losses": max_consecutive(values, lambda value: value < 0),
        "max_consecutive_non_positive_trades": max_consecutive(values, lambda value: value <= 0),
        "tp_hit_rate": sum(1 for event in events if event.outcome.exit_reason == "tp") / count,
        "sl_hit_rate": sum(1 for event in events if event.outcome.exit_reason == "sl") / count,
        "timeout_rate": sum(1 for event in events if event.outcome.exit_reason in {"timeout", "end_of_data"}) / count,
        "monthly_positive_ratio": positive_period_ratio(monthly_R),
        "quarterly_positive_ratio": positive_period_ratio(quarterly_R),
        "yearly_positive_ratio": positive_period_ratio(yearly_R),
        "top_5_percent_contribution_pct": top_5,
        "max_trades_in_one_month": max(monthly_counts.values(), default=0),
        "top_month_contribution_pct": top_month,
    }


def grouped_metrics(events: list[ReplayEvent], key_fn: Callable[[ReplayEvent], object]) -> dict[object, dict[str, object]]:
    groups: dict[object, list[ReplayEvent]] = {}
    for event in events:
        key = key_fn(event)
        if key is not None:
            groups.setdefault(key, []).append(event)
    return {key: replay_metrics(group) for key, group in sorted(groups.items(), key=lambda item: item[0])}


def yearly_rows(events: list[ReplayEvent]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    metrics_by_year = grouped_metrics(events, lambda event: period_key(event.outcome.exit_time, "year"))
    for key, metrics in metrics_by_year.items():
        year = key[0] if isinstance(key, tuple) else key
        rows.append(
            {
                "year": year,
                "trades_count": metrics.get("sequential_trades_count"),
                "mean_R": metrics.get("mean_R"),
                "profit_factor_R": metrics.get("profit_factor_R"),
                "cumulative_R": metrics.get("cumulative_R"),
                "max_drawdown_R": metrics.get("max_drawdown_R"),
                "tp_hit_rate": metrics.get("tp_hit_rate"),
                "sl_hit_rate": metrics.get("sl_hit_rate"),
                "timeout_rate": metrics.get("timeout_rate"),
            }
        )
    return rows


def walk_forward_rows(events: list[ReplayEvent], splits: int) -> list[dict[str, object]]:
    if splits <= 0 or len(events) < 2:
        return []
    sorted_events = sorted(events, key=lambda event: event.entry_timestamp or datetime.max)
    rows: list[dict[str, object]] = []
    for split_id in range(1, splits + 1):
        test_start_index = max(1, math.floor(len(sorted_events) * split_id / (splits + 1)))
        test_end_index = math.floor(len(sorted_events) * (split_id + 1) / (splits + 1))
        train_events = sorted_events[:test_start_index]
        test_events = sorted_events[test_start_index:test_end_index]
        if not train_events or not test_events:
            continue
        train = replay_metrics(train_events)
        test = replay_metrics(test_events)
        test_classification = "review" if (
            finite_value(test.get("mean_R")) is not None
            and float(test["mean_R"]) > 0
            and finite_value(test.get("profit_factor_R")) is not None
            and float(test["profit_factor_R"]) > 1
        ) else "weak"
        rows.append(
            {
                "split_id": split_id,
                "train_start": train_events[0].outcome.time_server,
                "train_end": train_events[-1].outcome.exit_time,
                "test_start": test_events[0].outcome.time_server,
                "test_end": test_events[-1].outcome.exit_time,
                "train_trades": train.get("sequential_trades_count"),
                "train_mean_R": train.get("mean_R"),
                "train_profit_factor_R": train.get("profit_factor_R"),
                "test_trades": test.get("sequential_trades_count"),
                "test_mean_R": test.get("mean_R"),
                "test_profit_factor_R": test.get("profit_factor_R"),
                "test_max_drawdown_R": test.get("max_drawdown_R"),
                "test_classification": test_classification,
            }
        )
    return rows


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def median_value(values: list[float]) -> float | None:
    return percentile(values, 0.5)


def summarize_random_baseline(
    candidate_metrics: dict[str, object],
    random_metrics: list[dict[str, object]],
    iterations: int,
) -> dict[str, object]:
    mean_values = [float(value) for value in (row.get("mean_R") for row in random_metrics) if finite_value(value) is not None]
    pf_values = [
        float(value)
        for value in (row.get("profit_factor_R") for row in random_metrics)
        if finite_value(value) is not None
    ]
    dd_values = [
        float(value)
        for value in (row.get("max_drawdown_R") for row in random_metrics)
        if finite_value(value) is not None
    ]
    random_mean_p95 = percentile(mean_values, 0.95)
    random_pf_p95 = percentile(pf_values, 0.95)
    candidate_mean = finite_value(candidate_metrics.get("mean_R"))
    candidate_pf = finite_value(candidate_metrics.get("profit_factor_R"))
    candidate_percentile = None
    if candidate_mean is not None and mean_values:
        candidate_percentile = sum(1 for value in mean_values if value <= candidate_mean) / len(mean_values)
    return {
        "iterations": iterations,
        "random_mean_R_mean": sum(mean_values) / len(mean_values) if mean_values else None,
        "random_mean_R_median": median_value(mean_values),
        "random_mean_R_p95": random_mean_p95,
        "random_profit_factor_R_mean": sum(pf_values) / len(pf_values) if pf_values else None,
        "random_profit_factor_R_p95": random_pf_p95,
        "random_max_drawdown_R_median": median_value(dd_values),
        "candidate_mean_R_vs_random_p95": (
            candidate_mean - random_mean_p95
            if candidate_mean is not None and random_mean_p95 is not None
            else None
        ),
        "candidate_profit_factor_R_vs_random_p95": (
            candidate_pf - random_pf_p95
            if candidate_pf is not None and random_pf_p95 is not None
            else None
        ),
        "candidate_percentile_vs_random_mean_R": candidate_percentile,
        "random_baseline_available": bool(random_metrics),
        "random_baseline_not_available_reason": "",
    }


def unavailable_random_baseline(iterations: int) -> dict[str, object]:
    return {
        "iterations": iterations,
        "random_mean_R_mean": None,
        "random_mean_R_median": None,
        "random_mean_R_p95": None,
        "random_profit_factor_R_mean": None,
        "random_profit_factor_R_p95": None,
        "random_max_drawdown_R_median": None,
        "candidate_mean_R_vs_random_p95": None,
        "candidate_profit_factor_R_vs_random_p95": None,
        "candidate_percentile_vs_random_mean_R": None,
        "random_baseline_available": False,
        "random_baseline_not_available_reason": (
            "real-data random baseline was not available for this run; no random result was produced"
            if iterations > 0
            else ""
        ),
    }


def unavailable_random_baseline_with_reason(iterations: int, reason: str) -> dict[str, object]:
    summary = unavailable_random_baseline(iterations)
    summary["random_baseline_not_available_reason"] = reason if iterations > 0 else ""
    return summary


def event_key(event: ReplayEvent) -> tuple[int, object]:
    return event.outcome.row_index, event.outcome.time_server


def config_hash(path: Path | None) -> str:
    if path is None:
        return "internal_defaults"
    path = Path(path)
    if not path.exists():
        return "missing"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:16]


def cost_summary_for_events(events: list[ReplayEvent]) -> dict[str, object]:
    costs = [float(event.outcome.cost_R) for event in events if finite_value(event.outcome.cost_R) is not None]
    return {
        "total_cost_R": sum(costs) if costs else 0.0,
        "mean_cost_R": sum(costs) / len(costs) if costs else None,
    }


def cost_stress_diagnostics(
    base_events: list[ReplayEvent],
    stress_events: list[ReplayEvent] | None,
) -> dict[str, object]:
    base_costs = cost_summary_for_events(base_events)
    diagnostics: dict[str, object] = {
        "base_total_cost_R": base_costs["total_cost_R"],
        "mean_cost_R_base": base_costs["mean_cost_R"],
        "stress_total_cost_R": None,
        "mean_cost_R_stress": None,
        "cost_R_delta_mean": None,
        "net_R_delta_mean": None,
        "stress_changed_cost_R": False,
        "stress_cost_R_changed": False,
        "stress_cost_no_effect_warning": False,
    }
    if stress_events is None:
        return diagnostics
    stress_costs = cost_summary_for_events(stress_events)
    diagnostics["stress_total_cost_R"] = stress_costs["total_cost_R"]
    diagnostics["mean_cost_R_stress"] = stress_costs["mean_cost_R"]
    base_by_key = {event_key(event): event for event in base_events}
    cost_deltas: list[float] = []
    net_deltas: list[float] = []
    for stress_event in stress_events:
        base_event = base_by_key.get(event_key(stress_event))
        if base_event is None:
            continue
        cost_deltas.append(float(stress_event.outcome.cost_R) - float(base_event.outcome.cost_R))
        net_deltas.append(float(stress_event.outcome.net_R) - float(base_event.outcome.net_R))
    diagnostics["cost_R_delta_mean"] = sum(cost_deltas) / len(cost_deltas) if cost_deltas else None
    diagnostics["net_R_delta_mean"] = sum(net_deltas) / len(net_deltas) if net_deltas else None
    stress_changed_cost_R = any(abs(delta) > 1e-12 for delta in cost_deltas)
    diagnostics["stress_changed_cost_R"] = stress_changed_cost_R
    diagnostics["stress_cost_R_changed"] = stress_changed_cost_R
    delta_cost = finite_value(diagnostics["cost_R_delta_mean"])
    delta_net = finite_value(diagnostics["net_R_delta_mean"])
    diagnostics["stress_cost_no_effect_warning"] = (
        delta_cost is not None
        and delta_net is not None
        and abs(delta_cost) <= 1e-12
        and abs(delta_net) <= 1e-12
    )
    return diagnostics


def nonnegative_finite_value(value: object) -> float | None:
    parsed = finite_value(value)
    return parsed if parsed is not None and parsed >= 0 else None


def row_spread_source_used(
    row: dict[str, object],
    symbol: str,
    cost_config: dict[str, Any],
    stress_spread_policy: str = STRESS_SPREAD_POLICY_STANDARD,
) -> str:
    source, _spread = selected_spread_for_policy(row, symbol, cost_config, stress_spread_policy)
    return source


def single_or_mixed_source(counter: Counter[str]) -> str:
    if not counter:
        return "not_applicable"
    if len(counter) == 1:
        return next(iter(counter))
    return "mixed"


def effective_cost_diagnostics(
    prefix: str,
    *,
    spec: CandidateSpec,
    config: PathConfig,
    cost_config: dict[str, Any],
    events: list[ReplayEvent],
    stress_spread_policy: str = STRESS_SPREAD_POLICY_STANDARD,
) -> dict[str, object]:
    if config.cost_mode != "estimated":
        return {
            f"{prefix}_cost_config_source": "not_applicable",
            f"{prefix}_point_size_source": "not_applicable",
            f"{prefix}_point_size": None,
            f"{prefix}_spread_source_used": "not_applicable",
            f"{prefix}_spread_source_counts": "",
            f"{prefix}_row_level_spread_count": 0,
            f"{prefix}_fallback_spread_count": 0,
            f"{prefix}_max_row_or_fallback_count": 0,
            f"{prefix}_fallback_spread_source": "not_applicable",
            f"{prefix}_fallback_spread_points": None,
            f"{prefix}_fallback_spread_used": False,
            f"{prefix}_slippage_bps_round_trip": None,
            f"{prefix}_commission_bps_round_trip": None,
        }

    symbol_config = symbol_cost_config(cost_config, spec.symbol)
    fallback_source, fallback_spread = fallback_spread_source_for_symbol(spec.symbol, cost_config)
    spread_counter = Counter(
        row_spread_source_used(event.outcome.row, spec.symbol, cost_config, stress_spread_policy)
        for event in events
    )
    row_level_count = sum(
        1
        for event in events
        if row_level_spread(event.outcome.row)[1] is not None
    )
    fallback_count = sum(
        count
        for source, count in spread_counter.items()
        if "fallback_spread_points" in source
    )
    max_row_or_fallback_count = sum(
        1
        for event in events
        if max_row_or_fallback_selected(
            event.outcome.row,
            spec.symbol,
            cost_config,
            stress_spread_policy,
        )
    )
    fallback_used = any("fallback_spread_points" in source for source in spread_counter)
    return {
        f"{prefix}_cost_config_source": cost_config_source(cost_config),
        f"{prefix}_point_size_source": point_size_source_for_symbol(spec.symbol, cost_config),
        f"{prefix}_point_size": point_size_for_symbol(spec.symbol, cost_config),
        f"{prefix}_spread_source_used": single_or_mixed_source(spread_counter),
        f"{prefix}_spread_source_counts": serialize_counter(spread_counter),
        f"{prefix}_row_level_spread_count": row_level_count,
        f"{prefix}_fallback_spread_count": fallback_count,
        f"{prefix}_max_row_or_fallback_count": max_row_or_fallback_count,
        f"{prefix}_fallback_spread_source": fallback_source,
        f"{prefix}_fallback_spread_points": fallback_spread,
        f"{prefix}_fallback_spread_used": fallback_used,
        f"{prefix}_slippage_bps_round_trip": bps_cost(
            symbol_config,
            "slippage_bps_per_side",
            "slippage_bps_round_trip",
        )
        * 10000.0,
        f"{prefix}_commission_bps_round_trip": bps_cost(
            symbol_config,
            "commission_bps_per_side",
            "commission_bps_round_trip",
        )
        * 10000.0,
    }


def equal_effective_cost_value(left: object, right: object) -> bool:
    left_number = finite_value(left)
    right_number = finite_value(right)
    if left_number is not None or right_number is not None:
        return left_number is not None and right_number is not None and math.isclose(
            left_number,
            right_number,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    return str(left) == str(right)


def cost_no_effect_explanation(
    spec: CandidateSpec,
    *,
    base_diagnostics: dict[str, object],
    stress_diagnostics: dict[str, object],
    stress_cost_diagnostics: dict[str, object],
    stress_spread_policy: str,
) -> str:
    if not bool(stress_cost_diagnostics.get("stress_cost_no_effect_warning")):
        return ""

    base_source_counts = str(base_diagnostics.get("base_spread_source_counts") or "")
    stress_source_counts = str(stress_diagnostics.get("stress_spread_source_counts") or "")
    same_core_fields = all(
        equal_effective_cost_value(
            base_diagnostics.get(f"base_{field}"),
            stress_diagnostics.get(f"stress_{field}"),
        )
        for field in (
            "point_size_source",
            "point_size",
            "spread_source_used",
            "spread_source_counts",
            "slippage_bps_round_trip",
            "commission_bps_round_trip",
        )
    )
    fallback_differs = not equal_effective_cost_value(
        base_diagnostics.get("base_fallback_spread_points"),
        stress_diagnostics.get("stress_fallback_spread_points"),
    )
    fallback_unused = not bool(base_diagnostics.get("base_fallback_spread_used")) and not bool(
        stress_diagnostics.get("stress_fallback_spread_used")
    )
    if same_core_fields and fallback_differs and fallback_unused:
        if stress_spread_policy == STRESS_SPREAD_POLICY_MAX_ROW_OR_FALLBACK:
            return (
                f"No cost effect: stress spread policy max_row_or_fallback was selected, but no replayed "
                f"{spec.symbol} trade used configured fallback_spread_points "
                f"(base={base_source_counts}, stress={stress_source_counts}). The configured fallback spread was "
                "not larger than the available row-level spread on those rows, so stress kept the historical "
                "row-level spread and cost_R/net_R stayed unchanged."
            )
        if base_source_counts == stress_source_counts and base_source_counts.startswith("spread="):
            return (
                f"No cost effect: every replayed {spec.symbol} trade used the row-level spread field "
                f"({base_source_counts}) before configured fallback_spread_points were considered. "
                "The p75/p90 fallback_spread_points values therefore did not enter cost_R; "
                "point_size, slippage_bps_round_trip, and commission_bps_round_trip were effectively identical."
            )
        return (
            f"No cost effect: configured fallback_spread_points differed for {spec.symbol}, but the replayed rows "
            f"used the same non-fallback spread sources in both configs "
            f"(base={base_source_counts}, stress={stress_source_counts}). "
            "The fallback values therefore did not enter cost_R; other effective cost fields matched."
        )
    if same_core_fields:
        return (
            "No cost effect: the matched base and stress replay trades used the same effective point size, "
            "spread source, slippage, and commission fields."
        )
    return (
        "No cost effect: cost_R and net_R matched across paired replay trades. Review the effective cost fields "
        "and spread source counts to identify which configured values were reached by the cost source priority."
    )


def run_random_baseline(
    rows: list[dict[str, object]],
    spec: CandidateSpec,
    *,
    config: PathConfig,
    cost_config: dict[str, Any],
    no_overlap: bool,
    candidate_metrics: dict[str, object],
    candidate_pre_overlap_count: int,
    scope: CandidateScope,
    iterations: int,
    seed: int,
) -> dict[str, object]:
    if iterations <= 0:
        return unavailable_random_baseline(0)
    if scope.name != "exact_feature_combination" or scope.exact_candidate_not_available_reason:
        return unavailable_random_baseline_with_reason(
            iterations,
            "real-data random baseline requires an exact feature-combination scope",
        )
    target_count = int(candidate_metrics.get("sequential_trades_count") or 0)
    if target_count <= 0:
        return unavailable_random_baseline_with_reason(
            iterations,
            "candidate had no sequential trades to match",
        )
    broad_events = collect_replay_events(
        rows,
        spec,
        config=config,
        cost_config=cost_config,
        scope=CandidateScope(name="broad_regime_only"),
    )
    if len(broad_events) <= target_count:
        return unavailable_random_baseline_with_reason(
            iterations,
            "broad regime universe is not larger than the candidate sequential count",
        )
    rng = random.Random(seed)
    sample_size = min(len(broad_events), max(candidate_pre_overlap_count, target_count))
    random_metrics: list[dict[str, object]] = []
    for _iteration in range(iterations):
        sampled_events = sorted(
            rng.sample(broad_events, sample_size),
            key=lambda event: (event.entry_timestamp or datetime.max, event.outcome.row_index),
        )
        replay = apply_bar_level_no_overlap(sampled_events, no_overlap)
        matched_events = replay.events[:target_count]
        if not matched_events:
            continue
        random_metrics.append(replay_metrics(matched_events, replay.skipped_due_to_overlap))
    if not random_metrics:
        return unavailable_random_baseline_with_reason(
            iterations,
            "random sampling produced no sequential replay metrics",
        )
    return summarize_random_baseline(candidate_metrics, random_metrics, iterations)


def trade_log_rows(events: list[ReplayEvent]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for event in events:
        rows.append(
            {
                "symbol": event.spec.symbol,
                "direction": event.spec.direction,
                "target_family": event.spec.target_family,
                "horizon": event.spec.horizon,
                "regime_column": event.spec.regime_column,
                "regime_value": event.spec.regime_value,
                "entry_time": event.outcome.time_server,
                "exit_time": event.outcome.exit_time,
                "entry_price": event.outcome.entry_price,
                "exit_price": exit_price_from_outcome(event),
                "exit_reason": str(event.outcome.exit_reason or "").upper(),
                "bars_held": event.outcome.exit_bars,
                "tp_atr": event.spec.tp_atr,
                "sl_atr": event.spec.sl_atr,
                "R": event.outcome.selected_R,
                "cost_R": event.outcome.cost_R,
                "net_R": event.outcome.net_R,
            }
        )
    return rows


def exit_price_from_outcome(event: ReplayEvent) -> float | None:
    outcome = event.outcome
    if outcome.exit_reason == "tp":
        return outcome.tp_price
    if outcome.exit_reason == "sl":
        return outcome.sl_price
    gross_move = outcome.gross_R * outcome.sl_distance
    if event.spec.direction == "long":
        return outcome.entry_price + gross_move
    return outcome.entry_price - gross_move


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe_value(row.get(field)) for field in fieldnames})


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "candidate_stress_summary": output_dir / SUMMARY_FILE,
        "candidate_stress_report": output_dir / REPORT_FILE,
        "trade_log_base": output_dir / BASE_TRADE_LOG_FILE,
        "equity_curve_base": output_dir / BASE_EQUITY_CURVE_FILE,
        "trade_log_stress": output_dir / STRESS_TRADE_LOG_FILE,
        "equity_curve_stress": output_dir / STRESS_EQUITY_CURVE_FILE,
        "yearly_validation": output_dir / YEARLY_FILE,
        "walk_forward_validation": output_dir / WALK_FORWARD_FILE,
        "random_baseline_summary": output_dir / RANDOM_BASELINE_FILE,
    }


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> None:
    paths = output_paths(output_dir)
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Regime candidate stress outputs already exist under {output_dir}. Pass --overwrite to regenerate them."
        )


def final_research_label(
    base_metrics: dict[str, object],
    *,
    stress_metrics: dict[str, object] | None,
    stress_requested: bool,
    stress_applied: bool,
    stress_no_effect: bool,
    random_summary: dict[str, object],
    random_requested: bool,
    candidate_scope: CandidateScope,
    broad_scope_accepted: bool,
    walk_forward: list[dict[str, object]],
) -> str:
    if candidate_scope.exact_candidate_not_available_reason:
        return "EXACT_CANDIDATE_NOT_AVAILABLE"
    if int(base_metrics.get("sequential_trades_count") or 0) < MIN_SEQUENTIAL_TRADES:
        return "INSUFFICIENT_SEQUENTIAL_TRADES"
    mean_R = finite_value(base_metrics.get("mean_R"))
    pf = finite_or_infinite(base_metrics.get("profit_factor_R"))
    yearly = finite_value(base_metrics.get("yearly_positive_ratio"))
    if mean_R is None or pf is None or yearly is None or mean_R <= 0 or pf <= 1 or yearly < 0.5:
        return "STRESS_REJECTED"
    if stress_requested and (not stress_applied or stress_no_effect):
        return "STRESS_REVIEW_RETAINED"
    if stress_requested and stress_metrics:
        stress_mean = finite_value(stress_metrics.get("mean_R"))
        stress_pf = finite_or_infinite(stress_metrics.get("profit_factor_R"))
        if stress_mean is None or stress_pf is None or stress_mean <= 0 or stress_pf <= 1:
            return "COST_STRESS_NOT_PASSED"
    if random_requested and not bool(random_summary.get("random_baseline_available")):
        return "STRESS_REVIEW_RETAINED"
    random_mean_delta = finite_value(random_summary.get("candidate_mean_R_vs_random_p95"))
    random_pf_delta = finite_value(random_summary.get("candidate_profit_factor_R_vs_random_p95"))
    if random_mean_delta is not None and random_mean_delta <= 0:
        return "RANDOM_BASELINE_NOT_PASSED"
    if random_pf_delta is not None and random_pf_delta <= 0:
        return "RANDOM_BASELINE_NOT_PASSED"
    scope_can_advance = candidate_scope.name == "exact_feature_combination" or broad_scope_accepted
    if scope_can_advance and not any(str(row.get("test_classification") or "") == "weak" for row in walk_forward):
        return "NEEDS_WALK_FORWARD_REVIEW"
    return "STRESS_REVIEW_RETAINED"


def report_text(
    spec: CandidateSpec,
    summary: dict[str, object],
    random_summary: dict[str, object],
    yearly: list[dict[str, object]],
    walk_forward: list[dict[str, object]],
) -> str:
    lines = [
        "# Regime Candidate Stress Report",
        "",
        "## Research-Only Warning",
        "",
        "- Offline descriptive stress validation for one fixed historical regime candidate.",
        "- No new features, TP/SL search, sizing, broker actions, or operational rules are added.",
        "",
        "## Candidate Definition",
        "",
        f"- Symbol: `{spec.symbol}`",
        f"- Direction: `{spec.direction}`",
        f"- Timeframe: `{spec.timeframe}`",
        f"- Horizon: `h{spec.horizon}`",
        f"- Target family: `{spec.target_family}`",
        f"- Regime: `{spec.regime_column}={spec.regime_value}`",
        f"- TP/SL: `{spec.tp_atr:g}ATR/{spec.sl_atr:g}ATR`",
        f"- Candidate scope: `{summary.get('candidate_scope')}`",
        f"- Feature condition: `{summary.get('feature_condition')}`",
        f"- Exact-scope unavailable reason: `{summary.get('exact_candidate_not_available_reason')}`",
        "",
        "## Source Row Reconstruction",
        "",
        f"- Source rows loaded: `{summary.get('source_rows_loaded')}`",
        f"- Rows matching symbol/direction/regime: `{summary.get('rows_matching_symbol_direction_regime')}`",
        f"- Rows matching feature condition: `{summary.get('rows_matching_feature_condition')}`",
        f"- Entries before no-overlap: `{summary.get('candidate_entries_before_no_overlap')}`",
        f"- Filtered-out reasons: `{summary.get('filtered_out_reason_counts')}`",
        "",
        "## Base Sequential Metrics",
        "",
        f"- Trades: `{summary.get('sequential_trades_count')}`",
        f"- Skipped for overlap: `{summary.get('skipped_due_to_overlap')}`",
        f"- Mean R: `{csv_safe_value(summary.get('mean_R'))}`",
        f"- Profit factor R: `{csv_safe_value(summary.get('profit_factor_R'))}`",
        f"- Cumulative R: `{csv_safe_value(summary.get('cumulative_R'))}`",
        f"- Max drawdown R: `{csv_safe_value(summary.get('max_drawdown_R'))}`",
        "",
        "## Cost Stress",
        "",
        f"- Stress config requested: `{summary.get('stress_cost_config_requested')}`",
        f"- Stress applied: `{summary.get('stress_applied')}`",
        f"- Stress spread policy: `{summary.get('stress_spread_policy')}`",
        f"- Base config hash: `{summary.get('base_cost_config_hash')}`",
        f"- Stress config hash: `{summary.get('stress_cost_config_hash')}`",
        f"- Base cost config source: `{summary.get('base_cost_config_source')}`",
        f"- Stress cost config source: `{summary.get('stress_cost_config_source')}`",
        f"- Base point size: `{summary.get('base_point_size')}` from `{summary.get('base_point_size_source')}`",
        f"- Stress point size: `{summary.get('stress_point_size')}` from `{summary.get('stress_point_size_source')}`",
        f"- Base spread source used: `{summary.get('base_spread_source_used')}` "
        f"({summary.get('base_spread_source_counts')})",
        f"- Stress spread source used: `{summary.get('stress_spread_source_used')}` "
        f"({summary.get('stress_spread_source_counts')})",
        f"- Base row-level/fallback spread counts: `{summary.get('base_row_level_spread_count')}` / "
        f"`{summary.get('base_fallback_spread_count')}`",
        f"- Stress row-level/fallback spread counts: `{summary.get('stress_row_level_spread_count')}` / "
        f"`{summary.get('stress_fallback_spread_count')}`",
        f"- Base max-row-or-fallback fallback-selection count: `{summary.get('base_max_row_or_fallback_count')}`",
        f"- Stress max-row-or-fallback fallback-selection count: `{summary.get('stress_max_row_or_fallback_count')}`",
        f"- Base fallback spread points: `{summary.get('base_fallback_spread_points')}` "
        f"from `{summary.get('base_fallback_spread_source')}`, used=`{summary.get('base_fallback_spread_used')}`",
        f"- Stress fallback spread points: `{summary.get('stress_fallback_spread_points')}` "
        f"from `{summary.get('stress_fallback_spread_source')}`, used=`{summary.get('stress_fallback_spread_used')}`",
        f"- Base slippage/commission bps round trip: `{summary.get('base_slippage_bps_round_trip')}` / "
        f"`{summary.get('base_commission_bps_round_trip')}`",
        f"- Stress slippage/commission bps round trip: `{summary.get('stress_slippage_bps_round_trip')}` / "
        f"`{summary.get('stress_commission_bps_round_trip')}`",
        f"- Not available reason: `{summary.get('stress_cost_not_available_reason')}`",
        f"- Stress changed cost R: `{summary.get('stress_changed_cost_R')}`",
        f"- No-effect warning: `{summary.get('stress_cost_no_effect_warning')}`",
        f"- No-effect explanation: `{summary.get('cost_stress_no_effect_explanation')}`",
        f"- Mean cost R base: `{csv_safe_value(summary.get('mean_cost_R_base'))}`",
        f"- Mean cost R stress: `{csv_safe_value(summary.get('mean_cost_R_stress'))}`",
        f"- Mean cost R delta: `{csv_safe_value(summary.get('cost_R_delta_mean'))}`",
        f"- Mean net R delta: `{csv_safe_value(summary.get('net_R_delta_mean'))}`",
        f"- Stress mean R: `{csv_safe_value(summary.get('stress_mean_R'))}`",
        f"- Stress profit factor R: `{csv_safe_value(summary.get('stress_profit_factor_R'))}`",
        "",
        "## Random Baseline",
        "",
        f"- Iterations requested: `{random_summary.get('iterations')}`",
        f"- Available: `{random_summary.get('random_baseline_available')}`",
        f"- Not available reason: `{random_summary.get('random_baseline_not_available_reason')}`",
        f"- Random mean R p95: `{csv_safe_value(random_summary.get('random_mean_R_p95'))}`",
        "",
        "## Yearly Validation Summary",
        "",
        f"- Years covered: `{len(yearly)}`",
        f"- Yearly positive ratio: `{csv_safe_value(summary.get('yearly_positive_ratio'))}`",
        "",
        "## Walk-Forward Summary",
        "",
        f"- Splits written: `{len(walk_forward)}`",
        "",
        "## Clustering Diagnostics",
        "",
        f"- Max rows in one month: `{summary.get('max_trades_in_one_month')}`",
        f"- Top month contribution pct: `{csv_safe_value(summary.get('top_month_contribution_pct'))}`",
        f"- Top 5 percent contribution pct: `{csv_safe_value(summary.get('top_5_percent_contribution_pct'))}`",
        "",
        "## Final Research Label",
        "",
        f"- `{summary.get('final_research_label')}`",
    ]
    return "\n".join(lines) + "\n"


def stress_replay(
    rows: list[dict[str, object]],
    spec: CandidateSpec,
    *,
    config: PathConfig,
    cost_config: dict[str, Any],
    no_overlap: bool,
    scope: CandidateScope | None = None,
    scope_predicate: Callable[[dict[str, object]], bool] | None = None,
    audit: ReplayAudit | None = None,
    stress_spread_policy: str = STRESS_SPREAD_POLICY_STANDARD,
) -> ReplayResult:
    events = collect_replay_events(
        rows,
        spec,
        config=config,
        cost_config=cost_config,
        scope=scope,
        scope_predicate=scope_predicate,
        audit=audit,
        stress_spread_policy=stress_spread_policy,
    )
    return apply_bar_level_no_overlap(events, no_overlap)


def run_candidate_stress(
    args: argparse.Namespace,
    *,
    row_loader: RowLoader = load_path_rows,
) -> dict[str, Path]:
    spec = resolve_candidate_spec(args)
    run_id = str(args.run_id or current_run_id())
    output_dir = Path(args.output_root) / run_id
    ensure_outputs_writable(output_dir, bool(args.overwrite))
    paths = output_paths(output_dir)

    rows = row_loader(Path(args.db_path), spec.symbol, spec.timeframe)
    rows = sorted(rows, key=lambda row: str(row.get("time_server") or ""))
    if not rows:
        raise ValueError(f"No rows found for {spec.symbol} {spec.timeframe}.")

    scope = resolve_candidate_scope(args, spec)
    scope, scope_predicate = prepare_scope_predicate(rows, scope)
    audit = ReplayAudit(source_rows_loaded=len(rows))

    base_cost_mode = "estimated" if args.cost_config else "none"
    base_return_mode = "net" if args.cost_config else "gross"
    base_config = path_config_for_spec(spec, cost_mode=base_cost_mode, return_mode=base_return_mode)
    base_cost_config = load_cost_config(args.cost_config)
    if scope.exact_candidate_not_available_reason:
        eligible_row_indexes(rows, spec, scope=CandidateScope(name="broad_regime_only"), audit=audit)
        base_result = ReplayResult(events=[], skipped_due_to_overlap=0)
    else:
        base_result = stress_replay(
            rows,
            spec,
            config=base_config,
            cost_config=base_cost_config,
            no_overlap=bool(args.bar_level_no_overlap),
            scope=scope,
            scope_predicate=scope_predicate,
            audit=audit,
        )
    base_metrics = replay_metrics(base_result.events, base_result.skipped_due_to_overlap)
    base_effective_cost_fields = effective_cost_diagnostics(
        "base",
        spec=spec,
        config=base_config,
        cost_config=base_cost_config,
        events=base_result.events,
    )

    stress_metrics: dict[str, object] | None = None
    stress_result: ReplayResult | None = None
    stress_reason = ""
    stress_applied = False
    stress_cost_diagnostics = cost_stress_diagnostics(base_result.events, None)
    stress_effective_cost_fields = effective_cost_diagnostics(
        "stress",
        spec=spec,
        config=path_config_for_spec(spec, cost_mode="none", return_mode="gross"),
        cost_config={},
        events=[],
    )
    if args.stress_cost_config:
        if scope.exact_candidate_not_available_reason:
            stress_reason = "exact candidate scope was not available; no stress result was produced"
        elif not Path(args.stress_cost_config).exists():
            stress_reason = "stress cost config was not found; no stress result was produced"
        else:
            try:
                stress_config = path_config_for_spec(spec, cost_mode="estimated", return_mode="net")
                stress_cost_config = load_cost_config(args.stress_cost_config)
                stress_result = stress_replay(
                    rows,
                    spec,
                    config=stress_config,
                    cost_config=stress_cost_config,
                    no_overlap=bool(args.bar_level_no_overlap),
                    scope=scope,
                    scope_predicate=scope_predicate,
                    stress_spread_policy=str(args.stress_spread_policy),
                )
                stress_metrics = replay_metrics(stress_result.events, stress_result.skipped_due_to_overlap)
                stress_cost_diagnostics = cost_stress_diagnostics(base_result.events, stress_result.events)
                stress_effective_cost_fields = effective_cost_diagnostics(
                    "stress",
                    spec=spec,
                    config=stress_config,
                    cost_config=stress_cost_config,
                    events=stress_result.events,
                    stress_spread_policy=str(args.stress_spread_policy),
                )
                stress_applied = True
                write_csv(paths["trade_log_stress"], trade_log_rows(stress_result.events), TRADE_LOG_FIELDNAMES)
                write_csv(paths["equity_curve_stress"], equity_curve_rows(stress_result.events), EQUITY_FIELDNAMES)
            except (OSError, ValueError) as exc:
                stress_reason = f"stress cost recomputation was not available: {exc}"

    random_summary = run_random_baseline(
        rows,
        spec,
        config=base_config,
        cost_config=base_cost_config,
        no_overlap=bool(args.bar_level_no_overlap),
        candidate_metrics=base_metrics,
        candidate_pre_overlap_count=audit.candidate_entries_before_no_overlap,
        scope=scope,
        iterations=int(args.random_baseline_iterations),
        seed=int(args.random_seed),
    )

    yearly = yearly_rows(base_result.events)
    walk_forward = walk_forward_rows(base_result.events, int(args.walk_forward_splits))
    final_label = final_research_label(
        base_metrics,
        stress_metrics=stress_metrics,
        stress_requested=bool(args.stress_cost_config),
        stress_applied=stress_applied,
        stress_no_effect=bool(stress_cost_diagnostics.get("stress_cost_no_effect_warning")),
        random_summary=random_summary,
        random_requested=int(args.random_baseline_iterations) > 0,
        candidate_scope=scope,
        broad_scope_accepted=bool(args.accept_broad_regime_scope),
        walk_forward=walk_forward,
    )
    if final_label not in FINAL_LABELS:
        raise AssertionError(f"Unexpected final label: {final_label}")
    no_effect_explanation = cost_no_effect_explanation(
        spec,
        base_diagnostics=base_effective_cost_fields,
        stress_diagnostics=stress_effective_cost_fields,
        stress_cost_diagnostics=stress_cost_diagnostics,
        stress_spread_policy=str(args.stress_spread_policy),
    )

    summary = {
        "symbol": spec.symbol,
        "direction": spec.direction,
        "timeframe": spec.timeframe,
        "target_family": spec.target_family,
        "horizon": spec.horizon,
        "regime_column": spec.regime_column,
        "regime_value": spec.regime_value,
        "tp_atr": spec.tp_atr,
        "sl_atr": spec.sl_atr,
        "atr_column": spec.atr_column,
        "same_bar_policy": spec.same_bar_policy,
        "bar_level_no_overlap": int(bool(args.bar_level_no_overlap)),
        "candidate_scope": scope.name,
        "accept_broad_regime_scope": int(bool(args.accept_broad_regime_scope)),
        "feature_condition": scope.condition_text,
        "exact_candidate_not_available_reason": scope.exact_candidate_not_available_reason,
        **audit.as_summary_fields(),
        **base_metrics,
        "base_cost_config_path": str(args.cost_config) if args.cost_config else "internal_defaults",
        "stress_cost_config_path": str(args.stress_cost_config) if args.stress_cost_config else "",
        "stress_spread_policy": str(args.stress_spread_policy),
        "base_cost_config_hash": config_hash(args.cost_config),
        "stress_cost_config_hash": config_hash(args.stress_cost_config) if args.stress_cost_config else "",
        **base_effective_cost_fields,
        **stress_effective_cost_fields,
        "stress_applied": stress_applied,
        "stress_cost_config_requested": bool(args.stress_cost_config),
        "stress_cost_not_available_reason": stress_reason,
        **stress_cost_diagnostics,
        "cost_stress_no_effect_explanation": no_effect_explanation,
        "random_baseline_iterations": int(args.random_baseline_iterations),
        "random_baseline_available": random_summary.get("random_baseline_available"),
        "random_baseline_not_available_reason": random_summary.get("random_baseline_not_available_reason"),
        "random_mean_R_mean": random_summary.get("random_mean_R_mean"),
        "random_mean_R_median": random_summary.get("random_mean_R_median"),
        "random_mean_R_p95": random_summary.get("random_mean_R_p95"),
        "random_profit_factor_R_mean": random_summary.get("random_profit_factor_R_mean"),
        "random_profit_factor_R_p95": random_summary.get("random_profit_factor_R_p95"),
        "random_max_drawdown_R_median": random_summary.get("random_max_drawdown_R_median"),
        "candidate_mean_R_vs_random_p95": random_summary.get("candidate_mean_R_vs_random_p95"),
        "candidate_profit_factor_R_vs_random_p95": random_summary.get("candidate_profit_factor_R_vs_random_p95"),
        "candidate_percentile_vs_random_mean_R": random_summary.get("candidate_percentile_vs_random_mean_R"),
        "final_research_label": final_label,
    }
    if stress_metrics:
        base_mean = finite_value(base_metrics.get("mean_R"))
        stress_mean = finite_value(stress_metrics.get("mean_R"))
        base_pf = finite_or_infinite(base_metrics.get("profit_factor_R"))
        stress_pf = finite_or_infinite(stress_metrics.get("profit_factor_R"))
        summary.update(
            {
                "stress_sequential_trades_count": stress_metrics.get("sequential_trades_count"),
                "stress_mean_R": stress_metrics.get("mean_R"),
                "stress_profit_factor_R": stress_metrics.get("profit_factor_R"),
                "stress_cumulative_R": stress_metrics.get("cumulative_R"),
                "stress_max_drawdown_R": stress_metrics.get("max_drawdown_R"),
                "stress_mean_R_delta": (
                    stress_mean - base_mean
                    if stress_mean is not None and base_mean is not None
                    else None
                ),
                "stress_profit_factor_R_delta": (
                    stress_pf - base_pf
                    if stress_pf is not None and base_pf is not None and math.isfinite(stress_pf) and math.isfinite(base_pf)
                    else None
                ),
            }
        )

    write_csv(paths["trade_log_base"], trade_log_rows(base_result.events), TRADE_LOG_FIELDNAMES)
    write_csv(paths["equity_curve_base"], equity_curve_rows(base_result.events), EQUITY_FIELDNAMES)
    write_csv(paths["candidate_stress_summary"], [summary], SUMMARY_FIELDNAMES)
    write_csv(paths["yearly_validation"], yearly, YEARLY_FIELDNAMES)
    write_csv(paths["walk_forward_validation"], walk_forward, WALK_FORWARD_FIELDNAMES)
    write_csv(paths["random_baseline_summary"], [random_summary], RANDOM_FIELDNAMES)
    paths["candidate_stress_report"].parent.mkdir(parents=True, exist_ok=True)
    paths["candidate_stress_report"].write_text(
        report_text(spec, summary, random_summary, yearly, walk_forward),
        encoding="utf-8",
    )

    return paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stress-validate one explicit regime candidate using offline historical rows."
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--direction", required=True, choices=("long", "short"))
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--horizon", required=True)
    parser.add_argument("--target-family", required=True)
    parser.add_argument("--regime-column", required=True)
    parser.add_argument("--regime-value", required=True)
    parser.add_argument("--tp-atr", required=True, type=float)
    parser.add_argument("--sl-atr", required=True, type=float)
    parser.add_argument("--atr-column", required=True, default=DEFAULT_ATR_COLUMN)
    parser.add_argument(
        "--same-bar-policy",
        required=True,
        choices=("stop_first", "take_first"),
        default=DEFAULT_SAME_BAR_POLICY,
    )
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH)
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--stress-cost-config", type=Path)
    parser.add_argument(
        "--stress-spread-policy",
        choices=STRESS_SPREAD_POLICIES,
        default=STRESS_SPREAD_POLICY_STANDARD,
        help=(
            "Research-only spread source for stress cost replay: standard keeps row-level spread priority; "
            "max_row_or_fallback uses max(row spread or spread_avg_20, configured fallback); "
            "fallback_override uses configured fallback spread when available."
        ),
    )
    parser.add_argument("--bar-level-no-overlap", action="store_true")
    parser.add_argument(
        "--condition",
        action="append",
        default=[],
        help="Exact feature condition to apply, using existing condition syntax joined by AND.",
    )
    parser.add_argument("--candidate-summary-csv", type=Path)
    parser.add_argument("--candidate-id")
    parser.add_argument(
        "--accept-broad-regime-scope",
        action="store_true",
        help="Allow broad_regime_only scope to qualify for the stronger research-review label.",
    )
    parser.add_argument("--random-baseline-iterations", type=int, default=0)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--walk-forward-splits", type=int, default=3)
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.random_baseline_iterations < 0:
        raise ValueError("--random-baseline-iterations must be >= 0.")
    if args.walk_forward_splits < 0:
        raise ValueError("--walk-forward-splits must be >= 0.")
    return args


def main() -> int:
    try:
        outputs = run_candidate_stress(parse_args())
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"Regime candidate stress validation failed: {exc}")
        return 1
    print("Regime candidate stress validation complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
