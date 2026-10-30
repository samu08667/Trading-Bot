from __future__ import annotations

import argparse
import csv
import random
import sqlite3
import sys
from pathlib import Path
from statistics import median
from typing import Any

try:
    from condition_utils import (
        NUMERIC_TERCILE_SKIP_REASON,
        RAW_PRICE_FEATURES,
        RAW_PRICE_SKIP_REASON,
        build_predicate,
        combination_contains_raw_price_feature,
        parse_condition_key,
        precheck_combination_skip_reason,
        split_combination,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_candidate_baseline_diagnostics
    from scripts.condition_utils import (
        NUMERIC_TERCILE_SKIP_REASON,
        RAW_PRICE_FEATURES,
        RAW_PRICE_SKIP_REASON,
        build_predicate,
        combination_contains_raw_price_feature,
        parse_condition_key,
        precheck_combination_skip_reason,
        split_combination,
    )

try:
    from research_costs import (
        cost_report_warnings,
        load_cost_config,
        strategy_return_components,
        validate_cost_args,
        validate_estimated_cost_config,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_candidate_baseline_diagnostics
    from scripts.research_costs import (
        cost_report_warnings,
        load_cost_config,
        strategy_return_components,
        validate_cost_args,
        validate_estimated_cost_config,
    )

try:
    from research_metrics import (
        calculate_performance_concentration_metrics,
        calculate_return_metrics,
        csv_safe_value,
        normalize_direction,
        safe_float,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_candidate_baseline_diagnostics
    from scripts.research_metrics import (
        calculate_performance_concentration_metrics,
        calculate_return_metrics,
        csv_safe_value,
        normalize_direction,
        safe_float,
    )


DETAIL_FIELDS = [
    "candidate_scope",
    "symbol",
    "combination_key",
    "baseline_type",
    "baseline_key",
    "direction",
    "cost_mode",
    "return_mode",
    "candidate_trades_count",
    "baseline_trades_count",
    "candidate_mean_return",
    "baseline_mean_return",
    "mean_return_delta",
    "candidate_profit_factor",
    "baseline_profit_factor",
    "profit_factor_delta",
    "candidate_payoff_ratio",
    "baseline_payoff_ratio",
    "payoff_ratio_delta",
    "candidate_breakeven_winrate",
    "baseline_breakeven_winrate",
    "breakeven_winrate_delta",
    "candidate_breakeven_winrate_margin",
    "baseline_breakeven_winrate_margin",
    "breakeven_winrate_margin_delta",
    "candidate_max_drawdown",
    "baseline_max_drawdown",
    "max_drawdown_delta",
    "candidate_cumulative_return",
    "baseline_cumulative_return",
    "cumulative_return_delta",
    "candidate_monthly_positive_ratio",
    "baseline_monthly_positive_ratio",
    "candidate_top_5_percent_trades_contribution_pct",
    "baseline_top_5_percent_trades_contribution_pct",
]

SUMMARY_FIELDS = [
    "candidate_scope",
    "symbol",
    "combination_key",
    "direction",
    "cost_mode",
    "return_mode",
    "final_baseline_diagnostic_classification",
    "diagnostic_score",
    "primary_reason",
    "trades_count",
    "all_candles_result",
    "best_single_filter_key",
    "best_single_filter_result",
    "best_leave_one_out_key",
    "best_leave_one_out_result",
    "random_percentile",
    "conditional_random_percentile",
    "empirical_p_value_vs_random",
    "empirical_p_value_vs_conditional_random",
    "concentration_flags",
    "next_step_note",
]

SKIPPED_FIELDS = [
    "candidate_scope",
    "symbol",
    "combination_key",
    "direction",
    "cost_mode",
    "return_mode",
    "skip_reason",
]

DIRECT_BASELINE_TYPES = {
    "broad_regime_baseline",
    "single_filter_a",
    "single_filter_b",
}


def normalize_symbols(values: list[str] | None) -> list[str]:
    if not values:
        return []
    symbols: list[str] = []
    for value in values:
        for part in str(value).replace(",", " ").split():
            symbol = part.strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols


def comparable_float(value: Any) -> float | None:
    parsed = safe_float(value)
    if parsed is None:
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def percentile_higher_is_better(candidate_value: float | None, random_values: list[float | None]) -> float | None:
    candidate = comparable_float(candidate_value)
    values = [value for value in (comparable_float(item) for item in random_values) if value is not None]
    if candidate is None or not values:
        return None
    below_or_equal = sum(1 for value in values if value <= candidate)
    return below_or_equal / len(values)


def empirical_p_value_higher_is_better(candidate_value: float | None, random_values: list[float | None]) -> float | None:
    candidate = comparable_float(candidate_value)
    values = [value for value in (comparable_float(item) for item in random_values) if value is not None]
    if candidate is None or not values:
        return None
    at_least_candidate = sum(1 for value in values if value >= candidate)
    return (at_least_candidate + 1) / (len(values) + 1)


def random_sample_rows(rows: list[dict[str, Any]], sample_size: int, rng: random.Random) -> list[dict[str, Any]]:
    if sample_size <= 0:
        return []
    if sample_size > len(rows):
        raise ValueError("Cannot sample more rows than available without replacement.")
    return rng.sample(rows, sample_size)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_paths: list[Path], overwrite: bool) -> None:
    existing = [path for path in output_paths if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")


def candidate_file_path(validation_dir: Path, run_id: str, direction: str, scope: str) -> Path:
    filename = "final_research_candidates.csv" if scope == "cross_pair" else "pair_specific_candidates.csv"
    return validation_dir / run_id / direction / filename


def candidate_is_final(row: dict[str, str], scope: str) -> bool:
    if scope == "cross_pair":
        classification = str(row.get("final_classification") or "").strip()
        return classification in {"", "select", "watchlist"}
    classification = str(row.get("pair_specific_classification") or "").strip()
    return classification in {"select_pair_specific", "watchlist_pair_specific"}


def row_matches_mode(row: dict[str, str], direction: str, cost_mode: str, return_mode: str) -> bool:
    row_direction = (row.get("direction") or direction).strip().lower()
    row_cost_mode = (row.get("cost_mode") or cost_mode).strip().lower()
    row_return_mode = (row.get("return_mode") or return_mode).strip().lower()
    return row_direction == direction and row_cost_mode == cost_mode and row_return_mode == return_mode


def load_candidate_file(path: Path, scope: str, direction: str, cost_mode: str, return_mode: str) -> list[dict[str, str]]:
    rows = read_csv_rows(path)
    candidates: list[dict[str, str]] = []
    for row in rows:
        combination_key = (row.get("combination_key") or "").strip()
        if not combination_key:
            continue
        if not candidate_is_final(row, scope):
            continue
        if not row_matches_mode(row, direction, cost_mode, return_mode):
            continue
        item = dict(row)
        item["candidate_scope"] = scope
        candidates.append(item)
    return candidates


def load_universe_rows(
    db_path: Path,
    symbols: list[str],
    timeframe: str,
    target_horizon: int,
) -> list[dict[str, Any]]:
    if not symbols:
        return []
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    return_column = f"future_return_{target_horizon}"
    placeholders = ", ".join("?" for _ in symbols)
    query = (
        f"SELECT * FROM ml_dataset "
        f"WHERE UPPER(symbol) IN ({placeholders}) "
        "AND timeframe = ? "
        f"AND {return_column} IS NOT NULL"
    )
    params = [*symbols, timeframe]
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def group_rows_by_symbol(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            grouped.setdefault(symbol, []).append(row)
    return grouped


def direct_fixed_row_requested(args: argparse.Namespace) -> bool:
    fields = (
        "baseline_type",
        "baseline_filter",
        "feature_condition",
        "regime_column",
        "regime_value",
        "target_family",
    )
    return any(str(getattr(args, field, "") or "").strip() for field in fields)


def validate_direct_fixed_row_args(args: argparse.Namespace) -> None:
    if not direct_fixed_row_requested(args):
        return
    required = ["baseline_type", "feature_condition", "regime_column", "regime_value"]
    missing = [field for field in required if not str(getattr(args, field, "") or "").strip()]
    if missing:
        raise ValueError(
            "Direct fixed-row baseline mode requires: " + ", ".join(f"--{field.replace('_', '-')}" for field in missing)
        )
    if args.baseline_type not in DIRECT_BASELINE_TYPES:
        raise ValueError(
            "--baseline-type must be one of: " + ", ".join(sorted(DIRECT_BASELINE_TYPES))
        )
    if args.baseline_type.startswith("single_filter") and not str(args.baseline_filter or "").strip():
        raise ValueError("--baseline-filter is required for single-filter fixed-row baselines.")


def filter_universe_by_regime(
    rows: list[dict[str, Any]],
    regime_column: str,
    regime_value: str,
) -> list[dict[str, Any]]:
    column = str(regime_column or "").strip()
    expected = str(regime_value or "").strip()
    if not column or not expected:
        return rows
    return [row for row in rows if str(row.get(column) or "").strip() == expected]


def infer_pair_symbol(candidate: dict[str, str]) -> str:
    for key in ("symbol", "pair", "instrument"):
        value = (candidate.get(key) or "").strip().upper()
        if value:
            return value
    return ""


def selected_return_metrics(
    rows: list[dict[str, Any]],
    return_column: str,
    direction: str,
    cost_config: dict[str, Any],
    cost_mode: str,
    return_mode: str,
) -> dict[str, Any]:
    selected_returns: list[float] = []
    timestamps: list[Any] = []

    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        gross_return, _cost, net_return = strategy_return_components(
            row,
            symbol=symbol,
            return_column=return_column,
            direction=direction,
            cost_config=cost_config,
            cost_mode=cost_mode,
        )
        selected_return = gross_return if return_mode == "gross" else net_return
        if selected_return is None:
            continue
        selected_returns.append(selected_return)
        timestamps.append(row.get("time_server") or row.get("timestamp"))

    metrics = calculate_return_metrics(selected_returns)
    concentration = calculate_performance_concentration_metrics(selected_returns, timestamps)
    metrics.update(concentration)
    return metrics


def apply_condition(rows: list[dict[str, Any]], combination_key: str) -> list[dict[str, Any]]:
    predicate = build_predicate(rows, combination_key, table_name="ml_dataset")
    return [row for row in rows if predicate(row)]


def apply_condition_with_options(
    rows: list[dict[str, Any]],
    combination_key: str,
    *,
    allow_numeric_tercile: bool = False,
) -> list[dict[str, Any]]:
    predicate = build_predicate(
        rows,
        combination_key,
        table_name="ml_dataset",
        allow_numeric_tercile=allow_numeric_tercile,
    )
    return [row for row in rows if predicate(row)]


def validate_combination_or_skip(combination_key: str, rows: list[dict[str, Any]]) -> str | None:
    skip_reason = precheck_combination_skip_reason(combination_key)
    if skip_reason:
        return skip_reason
    try:
        for condition in split_combination(combination_key):
            parse_condition_key(condition)
        if rows:
            build_predicate(rows, combination_key, table_name="ml_dataset")
    except ValueError as exc:
        message = str(exc)
        if any(feature in combination_key for feature in RAW_PRICE_FEATURES):
            return RAW_PRICE_SKIP_REASON
        if "numeric_tercile" in combination_key:
            return NUMERIC_TERCILE_SKIP_REASON
        return f"unparsable_condition: {message}"
    return None


def validate_direct_baseline_filter_or_skip(
    combination_key: str,
    rows: list[dict[str, Any]],
    *,
    allow_numeric_tercile: bool,
) -> str | None:
    if combination_contains_raw_price_feature(combination_key):
        return RAW_PRICE_SKIP_REASON
    skip_reason = precheck_combination_skip_reason(combination_key)
    if skip_reason and not (allow_numeric_tercile and skip_reason == NUMERIC_TERCILE_SKIP_REASON):
        return skip_reason
    try:
        for condition in split_combination(combination_key):
            parse_condition_key(condition)
        if rows:
            build_predicate(
                rows,
                combination_key,
                table_name="ml_dataset",
                allow_numeric_tercile=allow_numeric_tercile,
            )
    except ValueError as exc:
        message = str(exc)
        if any(feature in combination_key for feature in RAW_PRICE_FEATURES):
            return RAW_PRICE_SKIP_REASON
        if "numeric_tercile" in combination_key:
            return NUMERIC_TERCILE_SKIP_REASON
        return f"unparsable_condition: {message}"
    return None


def leave_one_out_keys(conditions: list[str]) -> list[str]:
    if len(conditions) < 2:
        return []
    keys: list[str] = []
    for omitted_index in range(len(conditions)):
        remaining = [condition for index, condition in enumerate(conditions) if index != omitted_index]
        key = " AND ".join(remaining)
        if key and key not in keys:
            keys.append(key)
    return keys


def metric_delta(candidate_metrics: dict[str, Any], baseline_metrics: dict[str, Any], metric: str) -> float | None:
    candidate_value = comparable_float(candidate_metrics.get(metric))
    baseline_value = comparable_float(baseline_metrics.get(metric))
    if candidate_value is None or baseline_value is None:
        return None
    return candidate_value - baseline_value


def comparison_detail_row(
    candidate: dict[str, str],
    baseline_type: str,
    baseline_key: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
    candidate_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_scope": candidate["candidate_scope"],
        "symbol": candidate.get("symbol") or "",
        "combination_key": candidate["combination_key"],
        "baseline_type": baseline_type,
        "baseline_key": baseline_key,
        "direction": direction,
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "candidate_trades_count": candidate_metrics.get("trades_count"),
        "baseline_trades_count": baseline_metrics.get("trades_count"),
        "candidate_mean_return": candidate_metrics.get("mean_return"),
        "baseline_mean_return": baseline_metrics.get("mean_return"),
        "mean_return_delta": metric_delta(candidate_metrics, baseline_metrics, "mean_return"),
        "candidate_profit_factor": candidate_metrics.get("profit_factor"),
        "baseline_profit_factor": baseline_metrics.get("profit_factor"),
        "profit_factor_delta": metric_delta(candidate_metrics, baseline_metrics, "profit_factor"),
        "candidate_payoff_ratio": candidate_metrics.get("payoff_ratio"),
        "baseline_payoff_ratio": baseline_metrics.get("payoff_ratio"),
        "payoff_ratio_delta": metric_delta(candidate_metrics, baseline_metrics, "payoff_ratio"),
        "candidate_breakeven_winrate": candidate_metrics.get("breakeven_winrate"),
        "baseline_breakeven_winrate": baseline_metrics.get("breakeven_winrate"),
        "breakeven_winrate_delta": metric_delta(candidate_metrics, baseline_metrics, "breakeven_winrate"),
        "candidate_breakeven_winrate_margin": candidate_metrics.get("breakeven_winrate_margin"),
        "baseline_breakeven_winrate_margin": baseline_metrics.get("breakeven_winrate_margin"),
        "breakeven_winrate_margin_delta": metric_delta(
            candidate_metrics,
            baseline_metrics,
            "breakeven_winrate_margin",
        ),
        "candidate_max_drawdown": candidate_metrics.get("max_drawdown"),
        "baseline_max_drawdown": baseline_metrics.get("max_drawdown"),
        "max_drawdown_delta": metric_delta(candidate_metrics, baseline_metrics, "max_drawdown"),
        "candidate_cumulative_return": candidate_metrics.get("cumulative_return"),
        "baseline_cumulative_return": baseline_metrics.get("cumulative_return"),
        "cumulative_return_delta": metric_delta(candidate_metrics, baseline_metrics, "cumulative_return"),
        "candidate_monthly_positive_ratio": candidate_metrics.get("monthly_positive_ratio"),
        "baseline_monthly_positive_ratio": baseline_metrics.get("monthly_positive_ratio"),
        "candidate_top_5_percent_trades_contribution_pct": candidate_metrics.get(
            "top_5_percent_trades_contribution_pct"
        ),
        "baseline_top_5_percent_trades_contribution_pct": baseline_metrics.get(
            "top_5_percent_trades_contribution_pct"
        ),
    }


def median_metrics(metrics_list: list[dict[str, Any]]) -> dict[str, Any]:
    if not metrics_list:
        return {}
    merged: dict[str, Any] = {}
    keys = set().union(*(metrics.keys() for metrics in metrics_list))
    for key in keys:
        values = [comparable_float(metrics.get(key)) for metrics in metrics_list]
        numeric_values = [value for value in values if value is not None]
        merged[key] = median(numeric_values) if numeric_values else None
    return merged


def build_random_metrics(
    universe_rows: list[dict[str, Any]],
    sample_size: int,
    random_runs: int,
    rng: random.Random,
    return_column: str,
    direction: str,
    cost_config: dict[str, Any],
    cost_mode: str,
    return_mode: str,
) -> list[dict[str, Any]]:
    if sample_size <= 0 or sample_size > len(universe_rows):
        return []
    metrics_list: list[dict[str, Any]] = []
    for _ in range(random_runs):
        sample_rows = random_sample_rows(universe_rows, sample_size, rng)
        metrics_list.append(
            selected_return_metrics(
                sample_rows,
                return_column=return_column,
                direction=direction,
                cost_config=cost_config,
                cost_mode=cost_mode,
                return_mode=return_mode,
            )
        )
    return metrics_list


def result_vs_baseline(candidate_metrics: dict[str, Any], baseline_metrics: dict[str, Any] | None) -> str:
    if not baseline_metrics:
        return "missing"
    mean_delta = metric_delta(candidate_metrics, baseline_metrics, "mean_return")
    profit_factor_delta = metric_delta(candidate_metrics, baseline_metrics, "profit_factor")
    drawdown_delta = metric_delta(candidate_metrics, baseline_metrics, "max_drawdown")

    mean_ok = mean_delta is not None and mean_delta > 0
    pf_ok = profit_factor_delta is None or profit_factor_delta >= 0
    drawdown_ok = drawdown_delta is None or drawdown_delta >= -0.05
    return "beat" if mean_ok and pf_ok and drawdown_ok else "not_beat"


def best_baseline_by_mean(baselines: list[tuple[str, dict[str, Any]]]) -> tuple[str, dict[str, Any]] | None:
    candidates = [
        (key, metrics)
        for key, metrics in baselines
        if comparable_float(metrics.get("mean_return")) is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: comparable_float(item[1].get("mean_return")) or float("-inf"))


def concentration_flags(metrics: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    top_5 = comparable_float(metrics.get("top_5_percent_trades_contribution_pct"))
    best_month = comparable_float(metrics.get("best_month_contribution_pct"))
    monthly_ratio = comparable_float(metrics.get("monthly_positive_ratio"))
    quarterly_ratio = comparable_float(metrics.get("quarterly_positive_ratio"))
    if top_5 is not None and top_5 > 70:
        flags.append("top_5_percent_trades_concentration")
    if best_month is not None and best_month > 60:
        flags.append("best_month_concentration")
    if monthly_ratio is not None and monthly_ratio < 0.4:
        flags.append("low_monthly_positive_ratio")
    if quarterly_ratio is not None and quarterly_ratio < 0.4:
        flags.append("low_quarterly_positive_ratio")
    return flags


def classify_candidate(
    candidate_metrics: dict[str, Any],
    min_trades: int,
    all_result: str,
    single_result: str,
    leave_one_out_result: str,
    random_percentile: float | None,
    conditional_random_percentile: float | None,
    empirical_p_value_vs_random: float | None,
    empirical_p_value_vs_conditional_random: float | None,
    flags: list[str],
) -> tuple[str, int, str, str]:
    trades_count = int(candidate_metrics.get("trades_count") or 0)
    if trades_count < min_trades:
        return (
            "low_sample",
            0,
            f"Trades count {trades_count} is below min_trades {min_trades}.",
            "Increase sample or keep this only as a low-sample diagnostic.",
        )

    random_ok = random_percentile is None or random_percentile >= 0.6
    random_strong = random_percentile is not None and random_percentile >= 0.7
    conditional_ok = conditional_random_percentile is None or conditional_random_percentile >= 0.6
    conditional_strong = conditional_random_percentile is not None and conditional_random_percentile >= 0.7
    p_random_ok = empirical_p_value_vs_random is None or empirical_p_value_vs_random <= 0.4
    p_conditional_ok = (
        empirical_p_value_vs_conditional_random is None
        or empirical_p_value_vs_conditional_random <= 0.4
    )
    severe_concentration = bool(flags)

    if all_result != "beat":
        return (
            "not_better_than_context",
            10,
            "Candidate does not beat the all-candles context.",
            "Do not promote without stronger contextual evidence.",
        )

    if single_result == "not_beat" or conditional_random_percentile is not None and not conditional_ok:
        return (
            "mostly_single_filter_effect",
            45,
            "Candidate advantage does not clearly survive the best single-filter or conditional random baseline.",
            "Inspect whether one filter explains most of the result before any future backtest.",
        )

    if leave_one_out_result == "not_beat" or not random_ok or not p_random_ok or not p_conditional_ok:
        return (
            "not_better_than_context",
            30,
            "Candidate does not clearly beat random, conditional random, or leave-one-out context.",
            "Keep as research evidence only; do not promote to rule-based testing.",
        )

    if (
        single_result == "beat"
        and leave_one_out_result in {"beat", "missing"}
        and random_strong
        and conditional_strong
        and p_random_ok
        and p_conditional_ok
        and not severe_concentration
    ):
        return (
            "adds_incremental_value",
            85,
            "Candidate beats all-candles, single-filter, leave-one-out, and random context.",
            "Eligible for a future research-only rule-based backtest, not for live use.",
        )

    return (
        "mostly_single_filter_effect",
        55,
        "Evidence is positive but not strong enough to separate combination value from contextual effects.",
        "Review diagnostics and keep the candidate in research-only follow-up.",
    )


def process_candidate(
    candidate: dict[str, str],
    universe_rows: list[dict[str, Any]],
    return_column: str,
    direction: str,
    cost_config: dict[str, Any],
    cost_mode: str,
    return_mode: str,
    random_runs: int,
    min_trades: int,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None]:
    combination_key = candidate["combination_key"]
    if not universe_rows:
        skipped = {
            "candidate_scope": candidate["candidate_scope"],
            "symbol": candidate.get("symbol") or "",
            "combination_key": combination_key,
            "direction": direction,
            "cost_mode": cost_mode,
            "return_mode": return_mode,
            "skip_reason": "empty_universe",
        }
        return [], None, skipped

    skip_reason = validate_combination_or_skip(combination_key, universe_rows)
    if skip_reason:
        skipped = {
            "candidate_scope": candidate["candidate_scope"],
            "symbol": candidate.get("symbol") or "",
            "combination_key": combination_key,
            "direction": direction,
            "cost_mode": cost_mode,
            "return_mode": return_mode,
            "skip_reason": skip_reason,
        }
        return [], None, skipped

    candidate_rows = apply_condition(universe_rows, combination_key)
    candidate_metrics = selected_return_metrics(
        candidate_rows,
        return_column=return_column,
        direction=direction,
        cost_config=cost_config,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )

    detail_rows: list[dict[str, Any]] = []
    all_metrics = selected_return_metrics(
        universe_rows,
        return_column=return_column,
        direction=direction,
        cost_config=cost_config,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )
    detail_rows.append(
        comparison_detail_row(
            candidate,
            baseline_type="all_candles",
            baseline_key="all_candles",
            direction=direction,
            cost_mode=cost_mode,
            return_mode=return_mode,
            candidate_metrics=candidate_metrics,
            baseline_metrics=all_metrics,
        )
    )

    conditions = split_combination(combination_key)
    single_baselines: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []
    for condition in conditions:
        condition_rows = apply_condition(universe_rows, condition)
        metrics = selected_return_metrics(
            condition_rows,
            return_column=return_column,
            direction=direction,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
        )
        single_baselines.append((condition, metrics, condition_rows))
        detail_rows.append(
            comparison_detail_row(
                candidate,
                baseline_type="single_filter",
                baseline_key=condition,
                direction=direction,
                cost_mode=cost_mode,
                return_mode=return_mode,
                candidate_metrics=candidate_metrics,
                baseline_metrics=metrics,
            )
        )

    leave_one_out_baselines: list[tuple[str, dict[str, Any]]] = []
    for key in leave_one_out_keys(conditions):
        loo_rows = apply_condition(universe_rows, key)
        metrics = selected_return_metrics(
            loo_rows,
            return_column=return_column,
            direction=direction,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
        )
        leave_one_out_baselines.append((key, metrics))
        detail_rows.append(
            comparison_detail_row(
                candidate,
                baseline_type="leave_one_out",
                baseline_key=key,
                direction=direction,
                cost_mode=cost_mode,
                return_mode=return_mode,
                candidate_metrics=candidate_metrics,
                baseline_metrics=metrics,
            )
        )

    candidate_trade_count = int(candidate_metrics.get("trades_count") or 0)
    random_metrics = build_random_metrics(
        universe_rows,
        sample_size=candidate_trade_count,
        random_runs=random_runs,
        rng=rng,
        return_column=return_column,
        direction=direction,
        cost_config=cost_config,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )
    random_percentile = percentile_higher_is_better(
        comparable_float(candidate_metrics.get("mean_return")),
        [metrics.get("mean_return") for metrics in random_metrics],
    )
    empirical_p_value_vs_random = empirical_p_value_higher_is_better(
        comparable_float(candidate_metrics.get("mean_return")),
        [metrics.get("mean_return") for metrics in random_metrics],
    )
    random_median = median_metrics(random_metrics)
    if random_median:
        random_median["trades_count"] = candidate_trade_count
        detail_rows.append(
            comparison_detail_row(
                candidate,
                baseline_type="random_universe_median",
                baseline_key="random_same_trade_count",
                direction=direction,
                cost_mode=cost_mode,
                return_mode=return_mode,
                candidate_metrics=candidate_metrics,
                baseline_metrics=random_median,
            )
        )

    conditional_percentiles: list[float] = []
    conditional_p_values: list[float] = []
    conditional_median_rows: list[dict[str, Any]] = []
    for condition, _metrics, condition_rows in single_baselines:
        conditional_metrics = build_random_metrics(
            condition_rows,
            sample_size=candidate_trade_count,
            random_runs=random_runs,
            rng=rng,
            return_column=return_column,
            direction=direction,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
        )
        percentile = percentile_higher_is_better(
            comparable_float(candidate_metrics.get("mean_return")),
            [metrics.get("mean_return") for metrics in conditional_metrics],
        )
        p_value = empirical_p_value_higher_is_better(
            comparable_float(candidate_metrics.get("mean_return")),
            [metrics.get("mean_return") for metrics in conditional_metrics],
        )
        if percentile is not None:
            conditional_percentiles.append(percentile)
        if p_value is not None:
            conditional_p_values.append(p_value)
        conditional_median = median_metrics(conditional_metrics)
        if conditional_median:
            conditional_median["trades_count"] = candidate_trade_count
            conditional_median_rows.append(conditional_median)
            detail_rows.append(
                comparison_detail_row(
                    candidate,
                    baseline_type="conditional_random_median",
                    baseline_key=condition,
                    direction=direction,
                    cost_mode=cost_mode,
                    return_mode=return_mode,
                    candidate_metrics=candidate_metrics,
                    baseline_metrics=conditional_median,
                )
            )

    conditional_random_percentile = min(conditional_percentiles) if conditional_percentiles else None
    empirical_p_value_vs_conditional_random = max(conditional_p_values) if conditional_p_values else None

    best_single = best_baseline_by_mean([(key, metrics) for key, metrics, _rows in single_baselines])
    best_leave_one_out = best_baseline_by_mean(leave_one_out_baselines)
    all_result = result_vs_baseline(candidate_metrics, all_metrics)
    best_single_key = best_single[0] if best_single else ""
    best_single_result = result_vs_baseline(candidate_metrics, best_single[1]) if best_single else "missing"
    best_leave_one_out_key = best_leave_one_out[0] if best_leave_one_out else ""
    best_leave_one_out_result = (
        result_vs_baseline(candidate_metrics, best_leave_one_out[1])
        if best_leave_one_out
        else "missing"
    )
    flags = concentration_flags(candidate_metrics)
    classification, diagnostic_score, primary_reason, next_step_note = classify_candidate(
        candidate_metrics=candidate_metrics,
        min_trades=min_trades,
        all_result=all_result,
        single_result=best_single_result,
        leave_one_out_result=best_leave_one_out_result,
        random_percentile=random_percentile,
        conditional_random_percentile=conditional_random_percentile,
        empirical_p_value_vs_random=empirical_p_value_vs_random,
        empirical_p_value_vs_conditional_random=empirical_p_value_vs_conditional_random,
        flags=flags,
    )

    summary = {
        "candidate_scope": candidate["candidate_scope"],
        "symbol": candidate.get("symbol") or "",
        "combination_key": combination_key,
        "direction": direction,
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "final_baseline_diagnostic_classification": classification,
        "diagnostic_score": diagnostic_score,
        "primary_reason": primary_reason,
        "trades_count": candidate_metrics.get("trades_count"),
        "all_candles_result": all_result,
        "best_single_filter_key": best_single_key,
        "best_single_filter_result": best_single_result,
        "best_leave_one_out_key": best_leave_one_out_key,
        "best_leave_one_out_result": best_leave_one_out_result,
        "random_percentile": random_percentile,
        "conditional_random_percentile": conditional_random_percentile,
        "empirical_p_value_vs_random": empirical_p_value_vs_random,
        "empirical_p_value_vs_conditional_random": empirical_p_value_vs_conditional_random,
        "concentration_flags": ";".join(flags),
        "next_step_note": next_step_note,
    }
    return detail_rows, summary, None


def process_direct_fixed_row_candidate(
    args: argparse.Namespace,
    universe_rows: list[dict[str, Any]],
    return_column: str,
    direction: str,
    cost_config: dict[str, Any],
    cost_mode: str,
    return_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    validate_direct_fixed_row_args(args)
    scoped_rows = filter_universe_by_regime(universe_rows, args.regime_column, args.regime_value)
    candidate = {
        "candidate_scope": "fixed_row_direct",
        "symbol": ",".join(normalize_symbols(args.symbols)),
        "combination_key": args.feature_condition,
    }
    if not scoped_rows:
        skipped = {
            "candidate_scope": candidate["candidate_scope"],
            "symbol": candidate["symbol"],
            "combination_key": args.feature_condition,
            "direction": direction,
            "cost_mode": cost_mode,
            "return_mode": return_mode,
            "skip_reason": "empty_regime_universe",
        }
        return [], [], [skipped]

    if args.baseline_type == "broad_regime_baseline":
        baseline_rows = scoped_rows
        baseline_key = f"{args.regime_column}={args.regime_value}"
    else:
        baseline_skip_reason = validate_direct_baseline_filter_or_skip(
            args.baseline_filter,
            scoped_rows,
            allow_numeric_tercile=args.allow_numeric_tercile_baseline_filter,
        )
        if baseline_skip_reason:
            skipped = {
                "candidate_scope": candidate["candidate_scope"],
                "symbol": candidate["symbol"],
                "combination_key": args.feature_condition,
                "direction": direction,
                "cost_mode": cost_mode,
                "return_mode": return_mode,
                "skip_reason": f"baseline_filter_{baseline_skip_reason}",
            }
            return [], [], [skipped]
        baseline_rows = apply_condition_with_options(
            scoped_rows,
            args.baseline_filter,
            allow_numeric_tercile=args.allow_numeric_tercile_baseline_filter,
        )
        baseline_key = args.baseline_filter

    baseline_metrics = selected_return_metrics(
        baseline_rows,
        return_column=return_column,
        direction=direction,
        cost_config=cost_config,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )
    detail = comparison_detail_row(
        candidate,
        baseline_type=args.baseline_type,
        baseline_key=baseline_key,
        direction=direction,
        cost_mode=cost_mode,
        return_mode=return_mode,
        candidate_metrics={},
        baseline_metrics=baseline_metrics,
    )
    summary = {
        "candidate_scope": candidate["candidate_scope"],
        "symbol": candidate["symbol"],
        "combination_key": args.feature_condition,
        "direction": direction,
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "final_baseline_diagnostic_classification": "fixed_row_diagnostic_only",
        "diagnostic_score": "",
        "primary_reason": "Direct fixed-row baseline diagnostic only; exact feature condition is metadata only.",
        "trades_count": baseline_metrics.get("trades_count"),
        "all_candles_result": "",
        "best_single_filter_key": "",
        "best_single_filter_result": "",
        "best_leave_one_out_key": "",
        "best_leave_one_out_result": "",
        "random_percentile": "",
        "conditional_random_percentile": "",
        "empirical_p_value_vs_random": "",
        "empirical_p_value_vs_conditional_random": "",
        "concentration_flags": "",
        "next_step_note": "Review row-level diagnostics as research-only context.",
    }
    return [detail], [summary], []


def build_markdown_report(
    run_id: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
    symbols: list[str],
    timeframe: str,
    target_horizon: int,
    random_runs: int,
    min_trades: int,
    detail_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    skipped_rows: list[dict[str, Any]],
    random_baseline_path: Path,
) -> str:
    counts: dict[str, int] = {}
    for row in summary_rows:
        classification = str(row.get("final_baseline_diagnostic_classification") or "unknown")
        counts[classification] = counts.get(classification, 0) + 1
    counts["skipped"] = len(skipped_rows)

    def candidate_table(rows: list[dict[str, Any]]) -> list[str]:
        lines = [
            "| scope | symbol | combination_key | score | trades | random_pct | conditional_pct | reason |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for row in rows[:15]:
            lines.append(
                "| {scope} | {symbol} | {key} | {score} | {trades} | {random_pct} | {conditional_pct} | {reason} |".format(
                    scope=row.get("candidate_scope", ""),
                    symbol=row.get("symbol", ""),
                    key=str(row.get("combination_key", "")).replace("|", "\\|"),
                    score=csv_safe_value(row.get("diagnostic_score")),
                    trades=csv_safe_value(row.get("trades_count")),
                    random_pct=csv_safe_value(row.get("random_percentile")),
                    conditional_pct=csv_safe_value(row.get("conditional_random_percentile")),
                    reason=str(row.get("primary_reason", "")).replace("|", "\\|"),
                )
            )
        if len(lines) == 2:
            lines.append("| none |  |  |  |  |  |  |  |")
        return lines

    top_incremental = [
        row
        for row in sorted(
            summary_rows,
            key=lambda item: comparable_float(item.get("diagnostic_score")) or 0,
            reverse=True,
        )
        if row.get("final_baseline_diagnostic_classification") == "adds_incremental_value"
    ]
    mostly_single = [
        row
        for row in summary_rows
        if row.get("final_baseline_diagnostic_classification") == "mostly_single_filter_effect"
    ]
    not_better = [
        row
        for row in summary_rows
        if row.get("final_baseline_diagnostic_classification") == "not_better_than_context"
    ]
    fixed_row_diagnostics = [
        row
        for row in summary_rows
        if row.get("final_baseline_diagnostic_classification") == "fixed_row_diagnostic_only"
    ]

    if random_baseline_path.exists():
        reference_rows = read_csv_rows(random_baseline_path)
        random_baseline_note = (
            f"Optional random baseline reference found: `{random_baseline_path}` "
            f"({len(reference_rows)} detail rows)."
        )
    else:
        random_baseline_note = f"Optional random baseline reference not found: `{random_baseline_path}`."

    lines = [
        "# Baseline Diagnostics Report",
        "",
        "Research-only diagnostic. This report does not create strategies, does not generate operational alerts, does not provide buy/sell recommendations, and is not live-ready.",
        "",
        "This diagnostic does not search for new strategies. It only checks whether already-final candidates add incremental value over their own single-filter, leave-one-out, and contextual random baselines.",
        "",
        "## Run context",
        "",
        f"- run_id: `{run_id}`",
        f"- direction: `{direction}`",
        f"- cost_mode: `{cost_mode}`",
        f"- return_mode: `{return_mode}`",
        f"- symbols: `{', '.join(symbols)}`",
        f"- timeframe: `{timeframe}`",
        f"- target_horizon: `{target_horizon}`",
        f"- random_runs: `{random_runs}`",
        f"- min_trades: `{min_trades}`",
        f"- comparisons: `{len(detail_rows)}`",
        f"- skipped_candidates: `{len(skipped_rows)}`",
        f"- {random_baseline_note}",
        "",
        "## Counts by classification",
        "",
        "| classification | count |",
        "| --- | ---: |",
    ]
    for classification in [
        "fixed_row_diagnostic_only",
        "adds_incremental_value",
        "mostly_single_filter_effect",
        "not_better_than_context",
        "low_sample",
        "skipped",
    ]:
        lines.append(f"| {classification} | {counts.get(classification, 0)} |")

    if fixed_row_diagnostics:
        lines.extend(
            [
                "",
                "## Direct Fixed-Row Diagnostics",
                "",
                (
                    "`fixed_row_direct` mode is a row-level baseline diagnostic. "
                    "It is not an incremental-value classification and does not make a candidate-quality decision."
                ),
                "",
            ]
        )
        lines.extend(candidate_table(fixed_row_diagnostics))

    lines.extend(["", "## Top adds_incremental_value", ""])
    lines.extend(candidate_table(top_incremental))
    lines.extend(["", "## Declassified as mostly_single_filter_effect", ""])
    lines.extend(candidate_table(mostly_single))
    lines.extend(["", "## Not better than context", ""])
    lines.extend(candidate_table(not_better))
    lines.extend(["", "## Skipped", ""])
    if skipped_rows:
        lines.extend(
            [
                "| scope | symbol | combination_key | reason |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row in skipped_rows[:30]:
            lines.append(
                "| {scope} | {symbol} | {key} | {reason} |".format(
                    scope=row.get("candidate_scope", ""),
                    symbol=row.get("symbol", ""),
                    key=str(row.get("combination_key", "")).replace("|", "\\|"),
                    reason=str(row.get("skip_reason", "")).replace("|", "\\|"),
                )
            )
    else:
        lines.append("No candidates were skipped.")

    lines.extend(
        [
            "",
            "## Methodology",
            "",
            "For each final candidate, the script compares the full filter combination against all candles in the same universe, each single filter, leave-one-out filters, a random same-trade-count baseline, and conditional random same-trade-count baselines inside each single-filter universe.",
            "",
            "Cross-pair candidates use the requested symbol universe. Pair-specific candidates use only the candidate symbol. Long and short, gross and net, and cross-pair and pair-specific outputs remain separate.",
            "",
            "## Guardrails",
            "",
            "- No live trading.",
            "- No broker order API calls.",
            "- No buy/sell recommendations.",
            "- No autonomous position opening or closing.",
            "- No strategy-ready interpretation.",
            "- Candidate evidence remains research-only and must still pass later validation before any operational discussion.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run research-only baseline diagnostics for already-final candidates."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--direction", choices=["long", "short"], default="long")
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--target-horizon", type=int, default=10)
    parser.add_argument("--db-path", default="data/trading_bot.db")
    parser.add_argument("--validation-dir", default="reports/validation/by_year")
    parser.add_argument("--random-baseline-dir", default="reports/random_baseline")
    parser.add_argument("--output-dir", default="reports/baseline_diagnostics")
    parser.add_argument("--cost-mode", choices=["none", "estimated"], default="estimated")
    parser.add_argument("--return-mode", choices=["gross", "net"], default="net")
    parser.add_argument("--cost-config", default="config/cost_model.example.json")
    parser.add_argument(
        "--baseline-type",
        choices=sorted(DIRECT_BASELINE_TYPES),
        default="",
        help="Direct fixed-row baseline type. Activates fixed-row mode when provided with the required context flags.",
    )
    parser.add_argument("--baseline-filter", default="", help="Active filter for single-filter fixed-row baselines.")
    parser.add_argument(
        "--feature-condition",
        default="",
        help="Original exact-rule feature condition metadata for fixed-row mode; not applied as an active baseline filter.",
    )
    parser.add_argument("--regime-column", default="", help="Active regime column for fixed-row baselines.")
    parser.add_argument("--regime-value", default="", help="Active regime value for fixed-row baselines.")
    parser.add_argument("--target-family", default="", help="Target-family metadata for fixed-row baseline context.")
    parser.add_argument(
        "--allow-numeric-tercile-baseline-filter",
        action="store_true",
        help=(
            "Direct fixed-row mode only: allow a numeric_tercile baseline filter after explicit review. "
            "Default behavior keeps numeric_tercile filters skipped."
        ),
    )
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--random-runs", type=int, default=250)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-candidates", type=int, default=50)
    parser.add_argument("--include-cross-pair", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-pair-specific", action="store_true")
    parser.add_argument("--min-trades", type=int, default=100)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validate_direct_fixed_row_args(args)
    direction = normalize_direction(args.direction)
    cost_mode = args.cost_mode
    return_mode = args.return_mode
    validate_cost_args(cost_mode=cost_mode, return_mode=return_mode)

    symbols = normalize_symbols(args.symbols)
    if not symbols:
        raise ValueError("--symbols must include at least one symbol.")

    validation_dir = Path(args.validation_dir)
    output_dir = Path(args.output_dir) / args.run_id / direction
    random_baseline_path = (
        Path(args.random_baseline_dir)
        / args.run_id
        / direction
        / "random_baseline_detail.csv"
    )
    detail_path = output_dir / "baseline_diagnostics_detail.csv"
    summary_path = output_dir / "baseline_diagnostics_summary.csv"
    report_path = output_dir / "baseline_diagnostics_report.md"
    skipped_path = output_dir / "skipped_baseline_diagnostics_candidates.csv"
    ensure_outputs_writable([detail_path, summary_path, report_path, skipped_path], args.overwrite)

    cost_config = load_cost_config(args.cost_config if cost_mode == "estimated" else None)
    universe_rows = load_universe_rows(
        db_path=Path(args.db_path),
        symbols=symbols,
        timeframe=args.timeframe,
        target_horizon=args.target_horizon,
    )
    rows_by_symbol = group_rows_by_symbol(universe_rows)
    if cost_mode == "estimated":
        cost_report = validate_estimated_cost_config(
            symbols=symbols,
            rows_by_symbol=rows_by_symbol,
            config=cost_config,
            strict=args.strict_cost_config,
        )
        for warning in cost_report_warnings(cost_report):
            print(f"WARNING: {warning}", file=sys.stderr)

    if direct_fixed_row_requested(args):
        detail_rows, summary_rows, skipped_rows = process_direct_fixed_row_candidate(
            args,
            universe_rows=universe_rows,
            return_column=f"future_return_{args.target_horizon}",
            direction=direction,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
        )
        write_csv(detail_path, DETAIL_FIELDS, detail_rows)
        write_csv(summary_path, SUMMARY_FIELDS, summary_rows)
        write_csv(skipped_path, SKIPPED_FIELDS, skipped_rows)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            build_markdown_report(
                run_id=args.run_id,
                direction=direction,
                cost_mode=cost_mode,
                return_mode=return_mode,
                symbols=symbols,
                timeframe=args.timeframe,
                target_horizon=args.target_horizon,
                random_runs=0,
                min_trades=args.min_trades,
                detail_rows=detail_rows,
                summary_rows=summary_rows,
                skipped_rows=skipped_rows,
                random_baseline_path=random_baseline_path,
            ),
            encoding="utf-8",
        )
        print(f"Wrote {detail_path}")
        print(f"Wrote {summary_path}")
        print(f"Wrote {report_path}")
        print(f"Wrote {skipped_path}")
        return 0

    candidates: list[dict[str, str]] = []
    if args.include_cross_pair:
        candidates.extend(
            load_candidate_file(
                candidate_file_path(validation_dir, args.run_id, direction, "cross_pair"),
                scope="cross_pair",
                direction=direction,
                cost_mode=cost_mode,
                return_mode=return_mode,
            )
        )
    if args.include_pair_specific:
        candidates.extend(
            load_candidate_file(
                candidate_file_path(validation_dir, args.run_id, direction, "pair_specific"),
                scope="pair_specific",
                direction=direction,
                cost_mode=cost_mode,
                return_mode=return_mode,
            )
        )
    candidates = candidates[: args.max_candidates]

    rng = random.Random(args.seed)
    return_column = f"future_return_{args.target_horizon}"
    detail_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_scope = candidate["candidate_scope"]
        candidate_symbol = infer_pair_symbol(candidate)
        candidate["symbol"] = candidate_symbol if candidate_scope == "pair_specific" else candidate.get("symbol", "")
        if candidate_scope == "pair_specific":
            if not candidate_symbol:
                skipped_rows.append(
                    {
                        "candidate_scope": candidate_scope,
                        "symbol": "",
                        "combination_key": candidate["combination_key"],
                        "direction": direction,
                        "cost_mode": cost_mode,
                        "return_mode": return_mode,
                        "skip_reason": "pair_specific_candidate_missing_symbol",
                    }
                )
                continue
            scoped_rows = [row for row in universe_rows if str(row.get("symbol") or "").upper() == candidate_symbol]
        else:
            scoped_rows = universe_rows

        rows, summary, skipped = process_candidate(
            candidate,
            universe_rows=scoped_rows,
            return_column=return_column,
            direction=direction,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
            random_runs=args.random_runs,
            min_trades=args.min_trades,
            rng=rng,
        )
        detail_rows.extend(rows)
        if summary:
            summary_rows.append(summary)
        if skipped:
            skipped_rows.append(skipped)

    write_csv(detail_path, DETAIL_FIELDS, detail_rows)
    write_csv(summary_path, SUMMARY_FIELDS, summary_rows)
    write_csv(skipped_path, SKIPPED_FIELDS, skipped_rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_markdown_report(
            run_id=args.run_id,
            direction=direction,
            cost_mode=cost_mode,
            return_mode=return_mode,
            symbols=symbols,
            timeframe=args.timeframe,
            target_horizon=args.target_horizon,
            random_runs=args.random_runs,
            min_trades=args.min_trades,
            detail_rows=detail_rows,
            summary_rows=summary_rows,
            skipped_rows=skipped_rows,
            random_baseline_path=random_baseline_path,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {detail_path}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {report_path}")
    print(f"Wrote {skipped_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
