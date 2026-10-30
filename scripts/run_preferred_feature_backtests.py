"""Run controlled backtests for preferred feature hypotheses.

This script is a research-only orchestrator. It reads the preferred feature
hypothesis shortlist, passes those features into the existing
``backtest_research.py`` single-feature bucket workflow, and consolidates the
resulting scenario rows. It does not define a strategy, train a model, connect
to a broker, or provide operational guidance.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Callable

BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from backtest_research import (
        DATABASE_PATH as BACKTEST_DATABASE_PATH,
        OUTPUT_SUMMARY as BACKTEST_SUMMARY_FILE,
        run_backtest as run_single_feature_backtest,
    )
    from research_costs import validate_cost_args
    from research_metrics import csv_safe_value, normalize_direction
    from feature_safety import is_future_or_target_column
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_preferred_feature_backtests
    from scripts.backtest_research import (
        DATABASE_PATH as BACKTEST_DATABASE_PATH,
        OUTPUT_SUMMARY as BACKTEST_SUMMARY_FILE,
        run_backtest as run_single_feature_backtest,
    )
    from scripts.research_costs import validate_cost_args
    from scripts.research_metrics import csv_safe_value, normalize_direction
    from scripts.feature_safety import is_future_or_target_column


DEFAULT_INPUT_ROOT = BASE_DIR / "reports" / "ml_research" / "preferred_feature_hypotheses"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "preferred_feature_backtests"
DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY")
DEFAULT_DIRECTIONS = ("long", "short")
SHORTLIST_FILE = "preferred_feature_hypotheses.csv"
SUMMARY_FILE = "preferred_feature_backtest_summary.csv"
DETAIL_FILE = "preferred_feature_backtest_detail.csv"
REPORT_FILE = "preferred_feature_backtest_report.md"
SKIPPED_FILE = "skipped_features.csv"
COST_COMPARISON_FILE = "cost_comparison.csv"
OUTPUT_FILES = (SUMMARY_FILE, DETAIL_FILE, REPORT_FILE, SKIPPED_FILE, COST_COMPARISON_FILE)

PREFERRED_FEATURES = {
    "long": [
        "return_5",
        "return_1",
        "return_20",
        "tick_volume_percentile_100",
        "tick_volume_zscore_100",
        "tick_volume_ratio_20",
        "close_to_ma_fast_atr_20",
        "range_to_atr_20",
        "volume_vs_session_avg",
        "spread_return",
        "ma_diff_atr_20",
    ],
    "short": [
        "return_5",
        "return_1",
        "return_20",
        "range_to_atr_20",
        "close_to_ma_fast_atr_20",
        "close_to_ma_slow_atr_20",
        "ma_diff_atr_20",
        "spread_return",
        "spread_to_atr_20",
        "tick_volume_percentile_100",
        "tick_volume_ratio_20",
        "volume_vs_session_avg",
    ],
}

SUMMARY_FIELDNAMES = [
    "symbol",
    "timeframe",
    "horizon",
    "direction",
    "feature",
    "feature_family",
    "scenario",
    "condition",
    "scenario_condition_tested",
    "condition_type",
    "condition_value",
    "bucket",
    "scenario_source",
    "is_preferred_shortlist_feature",
    "feature_in_shortlist",
    "trades_count",
    "mean_return",
    "median_return",
    "win_rate",
    "profit_factor",
    "max_drawdown",
    "cumulative_return",
    "payoff_ratio",
    "breakeven_winrate_margin",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "top_5_percent_trades_contribution_pct",
    "baseline_trades_count",
    "baseline_mean_return",
    "baseline_median_return",
    "baseline_profit_factor",
    "baseline_win_rate",
    "baseline_max_drawdown",
    "mean_return_vs_baseline",
    "profit_factor_vs_baseline",
    "win_rate_vs_baseline",
    "drawdown_vs_baseline",
    "cost_mode",
    "return_mode",
    "skip_reason",
    "notes",
]

DETAIL_FIELDNAMES = [
    "source_file",
    "source_status",
    "symbol",
    "timeframe",
    "horizon",
    "direction",
    "feature",
    "feature_family",
    "scenario",
    "condition",
    "scenario_condition_tested",
    "condition_type",
    "condition_value",
    "scenario_name",
    "scenario_type",
    "bucket",
    "scenario_source",
    "is_preferred_shortlist_feature",
    "feature_in_shortlist",
    "sample_flag",
    "trades_count",
    "mean_return",
    "median_return",
    "win_rate",
    "profit_factor",
    "max_drawdown",
    "cumulative_return",
    "payoff_ratio",
    "breakeven_winrate",
    "breakeven_winrate_margin",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "top_5_percent_trades_contribution_pct",
    "baseline_trades_count",
    "baseline_mean_return",
    "baseline_median_return",
    "baseline_profit_factor",
    "baseline_win_rate",
    "baseline_max_drawdown",
    "mean_return_vs_baseline",
    "profit_factor_vs_baseline",
    "win_rate_vs_baseline",
    "drawdown_vs_baseline",
    "cost_mode",
    "return_mode",
    "cost_config_source",
    "point_size_source",
    "spread_source_used",
    "symbols_using_default_costs",
    "skip_reason",
    "notes",
]

SKIPPED_FIELDNAMES = [
    "source_file",
    "source_status",
    "symbol",
    "timeframe",
    "horizon",
    "direction",
    "feature",
    "feature_family",
    "scenario",
    "condition",
    "scenario_condition_tested",
    "condition_type",
    "condition_value",
    "bucket",
    "scenario_source",
    "is_preferred_shortlist_feature",
    "feature_in_shortlist",
    "trades_count",
    "cost_mode",
    "return_mode",
    "skip_reason",
    "notes",
]

COST_COMPARISON_FIELDNAMES = [
    "symbol",
    "timeframe",
    "horizon",
    "direction",
    "feature",
    "feature_family",
    "scenario_condition_tested",
    "condition_type",
    "bucket",
    "condition_value",
    "gross_mean_return",
    "net_mean_return",
    "mean_return_cost_impact",
    "gross_profit_factor",
    "net_profit_factor",
    "profit_factor_cost_impact",
    "costs_erased_gross_edge",
    "notes",
]


BacktestRunner = Callable[[argparse.Namespace], None]


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def safe_int(value: object) -> int:
    parsed = safe_float(value)
    return int(parsed) if parsed is not None else 0


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def metric_delta(value: object, baseline: object) -> float | None:
    parsed_value = safe_float(value)
    parsed_baseline = safe_float(baseline)
    if parsed_value is None or parsed_baseline is None:
        return None
    return parsed_value - parsed_baseline


def fallback_feature_family(feature: str, scenario_type: str = "") -> str:
    name = feature.strip().lower()
    if name in {"return_1", "return_5", "return_20"}:
        return "momentum/returns"
    if name in {
        "atr_14",
        "atr_20",
        "atr_50",
        "candle_range",
        "true_range",
        "volatility_20",
        "volatility_100",
        "volatility_ratio_20_100",
        "range_to_atr_20",
        "body_to_atr_20",
    } or "wick_to_atr" in name:
        return "volatility/range"
    if name in {"ma_fast", "ma_slow", "ma_diff", "ma_diff_atr_20", "close_to_ma_fast_atr_20", "close_to_ma_slow_atr_20"}:
        return "trend/ma"
    if name in {"spread_price", "spread_return", "spread_to_atr_20", "spread_avg_20", "spread_to_volume_ratio"}:
        return "spread/liquidity"
    if name in {
        "tick_volume_avg_20",
        "tick_volume_ratio_20",
        "tick_volume_zscore_100",
        "tick_volume_percentile_100",
        "volume_spike_20",
        "volume_dry_up_20",
        "volume_vs_hour_avg",
        "volume_vs_session_avg",
    }:
        return "volume/liquidity"
    if name in {"hour", "day_of_week", "hour_session"} or scenario_type in {"hour_session", "day_of_week"}:
        return "session/calendar"
    if "news" in name or "blackout" in name or "post_news" in name or name.startswith("minutes_to") or name.startswith("minutes_from"):
        return "news_risk"
    return "other"


def csv_value(value: object) -> object:
    return csv_safe_value(value)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def shortlist_path(input_root: Path, *, direction: str, timeframe: str, horizon: int) -> Path:
    return input_root / direction / f"{timeframe}_h{horizon}" / SHORTLIST_FILE


def direction_output_dir(output_root: Path, *, run_id: str, direction: str) -> Path:
    return output_root / run_id / direction


def symbol_output_dir(
    output_root: Path,
    *,
    run_id: str,
    direction: str,
    symbol: str,
    timeframe: str,
    horizon: int,
) -> Path:
    return direction_output_dir(output_root, run_id=run_id, direction=direction) / "symbol_runs" / (
        f"{symbol}_{timeframe}_h{horizon}"
    )


def ranking_input_path(
    output_root: Path,
    *,
    run_id: str,
    direction: str,
    symbol: str,
    timeframe: str,
    horizon: int,
) -> Path:
    return direction_output_dir(output_root, run_id=run_id, direction=direction) / "ranking_inputs" / (
        f"{symbol}_{timeframe}_h{horizon}_preferred_features.csv"
    )


def normalize_symbols(symbols: list[object]) -> list[str]:
    normalized = []
    seen = set()
    for value in symbols:
        symbol = str(value or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    if not normalized:
        raise ValueError("--symbols must include at least one symbol.")
    return normalized


def normalized_token(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")


def is_raw_scale_dependent(row: dict[str, str]) -> bool:
    token = normalized_token(row.get("normalized_or_raw"))
    return token == "raw_scale_dependent" or ("raw" in token and "scale" in token)


def is_high_caution(row: dict[str, str]) -> bool:
    return normalized_token(row.get("caution_level")) == "high"


def is_controlled_testing_candidate(row: dict[str, str]) -> bool:
    return "controlled combination testing" in str(row.get("recommended_usage") or "").strip().lower()


def eligible_shortlist_row(row: dict[str, str]) -> bool:
    feature = str(row.get("feature") or "").strip()
    if not feature:
        return False
    if is_future_or_target_column(feature):
        return False
    if is_raw_scale_dependent(row) or is_high_caution(row):
        return False
    return is_controlled_testing_candidate(row)


def priority_index(direction: str, feature: str) -> int:
    preferred = PREFERRED_FEATURES[normalize_direction(direction)]
    try:
        return preferred.index(feature)
    except ValueError:
        return len(preferred) + 100


def load_shortlist_rows(
    *,
    input_root: Path,
    direction: str,
    timeframe: str,
    horizon: int,
) -> tuple[list[dict[str, str]], list[str]]:
    path = shortlist_path(input_root, direction=direction, timeframe=timeframe, horizon=horizon)
    if not path.exists():
        return [], [f"Missing shortlist: {path}"]
    rows = read_csv_rows(path)
    return rows, []


def select_priority_features(
    rows: list[dict[str, str]],
    *,
    direction: str,
    max_features: int | None,
) -> list[dict[str, str]]:
    if max_features is not None and max_features <= 0:
        raise ValueError("--max-features must be greater than zero when provided.")

    best_by_feature: dict[str, dict[str, str]] = {}
    for row in rows:
        if not eligible_shortlist_row(row):
            continue
        feature = str(row.get("feature") or "").strip()
        existing = best_by_feature.get(feature)
        if existing is None or safe_int(row.get("stability_score")) > safe_int(existing.get("stability_score")):
            best_by_feature[feature] = row

    selected = sorted(
        best_by_feature.values(),
        key=lambda row: (
            priority_index(direction, str(row.get("feature") or "")),
            -safe_int(row.get("stability_score")),
            str(row.get("feature") or ""),
        ),
    )
    if max_features is not None:
        return selected[:max_features]
    return selected


def feature_metadata(selected_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {
        str(row.get("feature") or "").strip(): row
        for row in selected_rows
        if str(row.get("feature") or "").strip()
    }


def write_ranking_input(path: Path, selected_rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "feature",
        "feature_family",
        "stability_score",
        "recommended_usage",
        "caution_level",
        "source",
    ]
    rows = []
    for row in selected_rows:
        rows.append(
            {
                "feature": row.get("feature", ""),
                "feature_family": row.get("feature_family", ""),
                "stability_score": row.get("stability_score", ""),
                "recommended_usage": row.get("recommended_usage", ""),
                "caution_level": row.get("caution_level", ""),
                "source": "preferred_feature_hypotheses",
            }
        )
    write_csv(path, rows, fieldnames)


def ensure_direction_outputs_writable(output_dir: Path, overwrite: bool) -> None:
    existing = [output_dir / file_name for file_name in OUTPUT_FILES if (output_dir / file_name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Preferred feature backtest outputs already exist under {output_dir}. Pass --overwrite to regenerate them."
        )


def run_or_reuse_symbol_backtest(
    *,
    output_root: Path,
    run_id: str,
    symbol: str,
    timeframe: str,
    horizon: int,
    direction: str,
    selected_rows: list[dict[str, str]],
    cost_mode: str,
    return_mode: str,
    cost_config: Path | None,
    strict_cost_config: bool,
    db_path: Path,
    overwrite: bool,
    runner: BacktestRunner,
) -> tuple[Path, str]:
    output_dir = symbol_output_dir(
        output_root,
        run_id=run_id,
        direction=direction,
        symbol=symbol,
        timeframe=timeframe,
        horizon=horizon,
    )
    summary_path = output_dir / BACKTEST_SUMMARY_FILE
    if summary_path.exists() and not overwrite:
        return summary_path, "reused_existing_backtest_research_summary"

    ranking_path = ranking_input_path(
        output_root,
        run_id=run_id,
        direction=direction,
        symbol=symbol,
        timeframe=timeframe,
        horizon=horizon,
    )
    write_ranking_input(ranking_path, selected_rows)
    runner(
        argparse.Namespace(
            symbol=symbol,
            timeframe=timeframe,
            target_horizon=horizon,
            direction=direction,
            ranking_path=ranking_path,
            top_features=len(selected_rows),
            cost_mode=cost_mode,
            cost_config=cost_config,
            strict_cost_config=strict_cost_config,
            return_mode=return_mode,
            db_path=db_path,
            output_dir=output_dir,
        )
    )
    if not summary_path.exists():
        raise FileNotFoundError(f"Expected backtest summary was not produced: {summary_path}")
    return summary_path, "generated_by_backtest_research"


def scenario_condition(row: dict[str, str]) -> str:
    scenario_name = str(row.get("scenario_name") or row.get("scenario") or "").strip()
    if scenario_name:
        return scenario_name
    scenario_type = str(row.get("scenario_type") or "").strip()
    feature = str(row.get("feature") or "").strip()
    bucket = str(row.get("bucket") or "").strip()
    parts = [part for part in (scenario_type, feature, bucket) if part]
    return ":".join(parts)


STANDARD_CONTEXT_TYPES = {"hour_session", "day_of_week", "ma_diff", "news_feature"}
STANDARD_CONTEXT_FEATURES = {
    "hour",
    "day_of_week",
    "ma_diff",
    "volume_spike_20",
    "volume_dry_up_20",
    "tick_volume_ratio_20",
    "tick_volume_zscore_100",
    "tick_volume_percentile_100",
    "spread_to_volume_ratio",
    "volume_vs_hour_avg",
    "volume_vs_session_avg",
    "blackout_window_30m",
    "has_high_impact_news_next_30m",
    "post_news_window_30m",
}


def scenario_source_for(feature: str, scenario_type: str, feature_in_shortlist: bool) -> str:
    if feature_in_shortlist:
        return "preferred_shortlist_feature"
    if scenario_type in STANDARD_CONTEXT_TYPES or feature in STANDARD_CONTEXT_FEATURES:
        return "standard_context_scenario"
    if feature:
        return "extra_default_scenario"
    return "unknown"


def is_baseline_row(row: dict[str, str]) -> bool:
    scenario = str(row.get("scenario_name") or row.get("scenario") or "").strip().lower()
    scenario_type = str(row.get("scenario_type") or "").strip().lower()
    feature = str(row.get("feature") or "").strip().lower()
    bucket = str(row.get("bucket") or "").strip().lower()
    return scenario_type == "baseline" or scenario.startswith("baseline:") or (feature == "all" and bucket == "all")


def baseline_metrics(rows: list[dict[str, str]]) -> dict[str, object]:
    baseline = next((row for row in rows if is_baseline_row(row)), None)
    if baseline is None:
        return {
            "baseline_trades_count": "",
            "baseline_mean_return": "",
            "baseline_median_return": "",
            "baseline_profit_factor": "",
            "baseline_win_rate": "",
            "baseline_max_drawdown": "",
        }
    return {
        "baseline_trades_count": safe_int(baseline.get("trades_count")),
        "baseline_mean_return": baseline.get("mean_return", ""),
        "baseline_median_return": baseline.get("median_return", ""),
        "baseline_profit_factor": baseline.get("profit_factor", ""),
        "baseline_win_rate": baseline.get("win_rate", ""),
        "baseline_max_drawdown": baseline.get("max_drawdown", ""),
    }


def skip_reason_for_row(row: dict[str, str]) -> str:
    trades_count = safe_int(row.get("trades_count"))
    if trades_count == 0:
        return "zero_trades_for_condition"
    return ""


def detail_rows_from_backtest_summary(
    *,
    summary_path: Path,
    source_status: str,
    selected_metadata: dict[str, dict[str, str]],
    fallback_symbol: str,
    fallback_timeframe: str,
    fallback_horizon: int,
    direction: str,
    cost_mode: str,
    return_mode: str,
    strict_shortlist_only: bool,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    raw_rows = read_csv_rows(summary_path)
    baseline = baseline_metrics(raw_rows)
    rows: list[dict[str, object]] = []
    skipped_rows: list[dict[str, object]] = []
    seen_features: set[str] = set()
    for row in raw_rows:
        feature = str(row.get("feature") or "").strip()
        seen_features.add(feature)
        if is_baseline_row(row):
            continue
        feature_in_shortlist = feature in selected_metadata
        if strict_shortlist_only and not feature_in_shortlist:
            continue
        metadata = selected_metadata.get(feature, {})
        condition = scenario_condition(row)
        condition_type = row.get("scenario_type", "")
        bucket = row.get("bucket", "")
        condition_value = bucket
        scenario_source = scenario_source_for(feature, condition_type, feature_in_shortlist)
        skip_reason = skip_reason_for_row(row)
        common = {
            "source_file": str(summary_path),
            "source_status": source_status,
            "symbol": str(row.get("symbol") or fallback_symbol).strip().upper(),
            "timeframe": str(row.get("timeframe") or fallback_timeframe).strip().upper(),
            "horizon": row.get("target_horizon") or fallback_horizon,
            "direction": normalize_direction(row.get("direction") or direction),
            "feature": feature,
            "feature_family": metadata.get("feature_family", "") or fallback_feature_family(feature, condition_type),
            "scenario": condition,
            "condition": condition,
            "scenario_condition_tested": condition,
            "condition_type": condition_type,
            "condition_value": condition_value,
            "scenario_name": row.get("scenario_name", ""),
            "scenario_type": condition_type,
            "bucket": bucket,
            "scenario_source": scenario_source,
            "is_preferred_shortlist_feature": bool_text(scenario_source == "preferred_shortlist_feature"),
            "feature_in_shortlist": bool_text(feature_in_shortlist),
            "trades_count": safe_int(row.get("trades_count")),
            "cost_mode": row.get("cost_mode") or cost_mode,
            "return_mode": row.get("return_mode") or return_mode,
            "skip_reason": skip_reason,
        }
        if skip_reason:
            skipped_rows.append(
                {
                    **common,
                    "notes": "condition was produced by backtest_research.py but was not testable as a normal row",
                }
            )
            continue

        rows.append(
            {
                **common,
                "sample_flag": row.get("sample_flag", ""),
                "mean_return": row.get("mean_return", ""),
                "median_return": row.get("median_return", ""),
                "win_rate": row.get("win_rate", ""),
                "profit_factor": row.get("profit_factor", ""),
                "max_drawdown": row.get("max_drawdown", ""),
                "cumulative_return": row.get("cumulative_return", ""),
                "payoff_ratio": row.get("payoff_ratio", ""),
                "breakeven_winrate": row.get("breakeven_winrate", ""),
                "breakeven_winrate_margin": row.get("breakeven_winrate_margin", ""),
                "monthly_positive_ratio": row.get("monthly_positive_ratio", ""),
                "quarterly_positive_ratio": row.get("quarterly_positive_ratio", ""),
                "top_5_percent_trades_contribution_pct": row.get("top_5_percent_trades_contribution_pct", ""),
                **baseline,
                "mean_return_vs_baseline": metric_delta(row.get("mean_return"), baseline["baseline_mean_return"]),
                "profit_factor_vs_baseline": metric_delta(row.get("profit_factor"), baseline["baseline_profit_factor"]),
                "win_rate_vs_baseline": metric_delta(row.get("win_rate"), baseline["baseline_win_rate"]),
                "drawdown_vs_baseline": metric_delta(row.get("max_drawdown"), baseline["baseline_max_drawdown"]),
                "cost_config_source": row.get("cost_config_source", ""),
                "point_size_source": row.get("point_size_source", ""),
                "spread_source_used": row.get("spread_source_used", ""),
                "symbols_using_default_costs": row.get("symbols_using_default_costs", ""),
                "notes": "single-feature bucket from backtest_research.py",
            }
        )

    for feature, metadata in selected_metadata.items():
        if feature in seen_features:
            continue
        skipped_rows.append(
            {
                "source_file": str(summary_path),
                "source_status": source_status,
                "symbol": fallback_symbol,
                "timeframe": fallback_timeframe,
                "horizon": fallback_horizon,
                "direction": direction,
                "feature": feature,
                "feature_family": metadata.get("feature_family", ""),
                "scenario": "",
                "condition": "",
                "scenario_condition_tested": "",
                "condition_type": "",
                "condition_value": "",
                "bucket": "",
                "scenario_source": "preferred_shortlist_feature",
                "is_preferred_shortlist_feature": "true",
                "feature_in_shortlist": "true",
                "trades_count": 0,
                "cost_mode": cost_mode,
                "return_mode": return_mode,
                "skip_reason": "feature_not_available_in_backtest_output",
                "notes": "backtest_research.py did not return any scenario rows for this selected feature",
            }
        )
    return rows, skipped_rows


def summary_row_from_detail(row: dict[str, object]) -> dict[str, object]:
    return {field: row.get(field, "") for field in SUMMARY_FIELDNAMES}


def average_numeric(rows: list[dict[str, object]], column: str) -> float | None:
    values = [safe_float(row.get(column)) for row in rows]
    finite = [value for value in values if value is not None]
    if not finite:
        return None
    return sum(finite) / len(finite)


def aggregate_summary_rows(detail_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, ...], list[dict[str, object]]] = defaultdict(list)
    for row in detail_rows:
        key = (
            str(row.get("timeframe") or ""),
            str(row.get("horizon") or ""),
            str(row.get("direction") or ""),
            str(row.get("feature") or ""),
            str(row.get("scenario_condition_tested") or ""),
            str(row.get("condition_type") or ""),
            str(row.get("condition_value") or ""),
            str(row.get("scenario_source") or ""),
            str(row.get("cost_mode") or "") + "|" + str(row.get("return_mode") or ""),
        )
        grouped[key].append(row)

    aggregate_rows = []
    numeric_average_columns = [
        "mean_return",
        "median_return",
        "win_rate",
        "profit_factor",
        "max_drawdown",
        "cumulative_return",
        "payoff_ratio",
        "breakeven_winrate_margin",
        "monthly_positive_ratio",
        "quarterly_positive_ratio",
        "top_5_percent_trades_contribution_pct",
        "baseline_mean_return",
        "baseline_median_return",
        "baseline_profit_factor",
        "baseline_win_rate",
        "baseline_max_drawdown",
        "mean_return_vs_baseline",
        "profit_factor_vs_baseline",
        "win_rate_vs_baseline",
        "drawdown_vs_baseline",
    ]
    for rows in grouped.values():
        symbols = sorted({str(row.get("symbol") or "") for row in rows if row.get("symbol")})
        if len(symbols) < 2:
            continue
        first = rows[0]
        aggregate = {
            "symbol": "ALL",
            "timeframe": first.get("timeframe", ""),
            "horizon": first.get("horizon", ""),
            "direction": first.get("direction", ""),
            "feature": first.get("feature", ""),
            "feature_family": first.get("feature_family", ""),
            "scenario": first.get("scenario", ""),
            "condition": first.get("condition", ""),
            "scenario_condition_tested": first.get("scenario_condition_tested", ""),
            "condition_type": first.get("condition_type", ""),
            "condition_value": first.get("condition_value", ""),
            "bucket": first.get("bucket", ""),
            "scenario_source": first.get("scenario_source", ""),
            "is_preferred_shortlist_feature": first.get("is_preferred_shortlist_feature", ""),
            "feature_in_shortlist": first.get("feature_in_shortlist", ""),
            "trades_count": sum(safe_int(row.get("trades_count")) for row in rows),
            "baseline_trades_count": sum(safe_int(row.get("baseline_trades_count")) for row in rows),
            "cost_mode": first.get("cost_mode", ""),
            "return_mode": first.get("return_mode", ""),
            "skip_reason": "",
            "notes": f"aggregate across {len(symbols)} symbols: {', '.join(symbols)}",
        }
        for column in numeric_average_columns:
            aggregate[column] = average_numeric(rows, column)
        aggregate_rows.append(aggregate)
    return aggregate_rows


def build_summary_rows(detail_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    per_symbol = [summary_row_from_detail(row) for row in detail_rows]
    aggregate = aggregate_summary_rows(detail_rows)
    return sorted(
        per_symbol + aggregate,
        key=lambda row: (
            str(row.get("feature") or ""),
            str(row.get("scenario_condition_tested") or ""),
            str(row.get("symbol") or ""),
        ),
    )


def family_summary(selected_rows: list[dict[str, str]]) -> list[str]:
    if not selected_rows:
        return ["- None."]
    counts = Counter(str(row.get("feature_family") or "other") for row in selected_rows)
    return [f"- {family}: {count} selected features" for family, count in counts.most_common()]


def selected_feature_lines(selected_rows: list[dict[str, str]]) -> list[str]:
    if not selected_rows:
        return ["- None."]
    lines = []
    for row in selected_rows:
        lines.append(
            "- `{feature}`: family={family}, score={score}, usage={usage}".format(
                feature=row.get("feature", ""),
                family=row.get("feature_family", ""),
                score=row.get("stability_score", ""),
                usage=row.get("recommended_usage", ""),
            )
        )
    return lines


def top_summary_lines(summary_rows: list[dict[str, object]], limit: int = 15) -> list[str]:
    candidates = [row for row in summary_rows if row.get("symbol") != "ALL"]
    if not candidates:
        return ["- None."]
    candidates.sort(
        key=lambda row: (
            safe_float(row.get("profit_factor")) if safe_float(row.get("profit_factor")) is not None else -1.0,
            safe_int(row.get("trades_count")),
        ),
        reverse=True,
    )
    lines = []
    for row in candidates[:limit]:
        lines.append(
            "- {symbol} `{feature}` `{scenario}`: trades={trades}, mean_return={mean_return}, profit_factor={pf}".format(
                symbol=row.get("symbol", ""),
                feature=row.get("feature", ""),
                scenario=row.get("scenario_condition_tested", ""),
                trades=row.get("trades_count", ""),
                mean_return=row.get("mean_return", ""),
                pf=row.get("profit_factor", ""),
            )
        )
    return lines


def row_is_absolute_failure(row: dict[str, object]) -> bool:
    mean_return = safe_float(row.get("mean_return"))
    profit_factor = safe_float(row.get("profit_factor"))
    return (
        mean_return is not None and mean_return <= 0
    ) or (
        profit_factor is not None and profit_factor < 1
    )


def row_is_better_than_baseline(row: dict[str, object]) -> bool:
    mean_delta = safe_float(row.get("mean_return_vs_baseline"))
    pf_delta = safe_float(row.get("profit_factor_vs_baseline"))
    win_delta = safe_float(row.get("win_rate_vs_baseline"))
    return any(value is not None and value > 0 for value in (mean_delta, pf_delta, win_delta))


def best_vs_baseline_lines(summary_rows: list[dict[str, object]], limit: int = 15) -> list[str]:
    candidates = [row for row in summary_rows if row.get("symbol") != "ALL" and row_is_better_than_baseline(row)]
    if not candidates:
        return ["- None."]
    candidates.sort(
        key=lambda row: (
            safe_float(row.get("mean_return_vs_baseline")) or float("-inf"),
            safe_float(row.get("profit_factor_vs_baseline")) or float("-inf"),
            safe_float(row.get("win_rate_vs_baseline")) or float("-inf"),
        ),
        reverse=True,
    )
    return [
        (
            "- {symbol} `{feature}` `{condition}`: mean_delta={mean_delta}, "
            "pf_delta={pf_delta}, win_delta={win_delta}, mean_return={mean_return}, pf={pf}"
        ).format(
            symbol=row.get("symbol", ""),
            feature=row.get("feature", ""),
            condition=row.get("scenario_condition_tested", ""),
            mean_delta=row.get("mean_return_vs_baseline", ""),
            pf_delta=row.get("profit_factor_vs_baseline", ""),
            win_delta=row.get("win_rate_vs_baseline", ""),
            mean_return=row.get("mean_return", ""),
            pf=row.get("profit_factor", ""),
        )
        for row in candidates[:limit]
    ]


def less_bad_lines(summary_rows: list[dict[str, object]], limit: int = 15) -> list[str]:
    candidates = [
        row
        for row in summary_rows
        if row.get("symbol") != "ALL" and row_is_absolute_failure(row) and row_is_better_than_baseline(row)
    ]
    if not candidates:
        return ["- None."]
    candidates.sort(
        key=lambda row: (
            safe_float(row.get("mean_return_vs_baseline")) or float("-inf"),
            safe_float(row.get("profit_factor_vs_baseline")) or float("-inf"),
        ),
        reverse=True,
    )
    return [
        (
            "- {symbol} `{feature}` `{condition}`: still fails absolute checks, "
            "but mean_delta={mean_delta}, pf_delta={pf_delta}"
        ).format(
            symbol=row.get("symbol", ""),
            feature=row.get("feature", ""),
            condition=row.get("scenario_condition_tested", ""),
            mean_delta=row.get("mean_return_vs_baseline", ""),
            pf_delta=row.get("profit_factor_vs_baseline", ""),
        )
        for row in candidates[:limit]
    ]


def absolute_failure_lines(summary_rows: list[dict[str, object]], limit: int = 20) -> list[str]:
    candidates = [row for row in summary_rows if row.get("symbol") != "ALL" and row_is_absolute_failure(row)]
    if not candidates:
        return ["- None."]
    candidates.sort(
        key=lambda row: (
            safe_float(row.get("mean_return")) if safe_float(row.get("mean_return")) is not None else float("-inf"),
            safe_float(row.get("profit_factor")) if safe_float(row.get("profit_factor")) is not None else float("-inf"),
        )
    )
    return [
        "- {symbol} `{feature}` `{condition}`: mean_return={mean_return}, profit_factor={pf}, baseline_mean={baseline}".format(
            symbol=row.get("symbol", ""),
            feature=row.get("feature", ""),
            condition=row.get("scenario_condition_tested", ""),
            mean_return=row.get("mean_return", ""),
            pf=row.get("profit_factor", ""),
            baseline=row.get("baseline_mean_return", ""),
        )
        for row in candidates[:limit]
    ]


def skipped_feature_lines(skipped_rows: list[dict[str, object]], limit: int = 20) -> list[str]:
    if not skipped_rows:
        return ["- None."]
    return [
        "- {symbol} `{feature}` `{condition}`: {reason}".format(
            symbol=row.get("symbol", ""),
            feature=row.get("feature", ""),
            condition=row.get("scenario_condition_tested", "") or row.get("condition", ""),
            reason=row.get("skip_reason", ""),
        )
        for row in skipped_rows[:limit]
    ]


def write_report(
    path: Path,
    *,
    direction: str,
    symbols: list[str],
    timeframe: str,
    horizon: int,
    cost_mode: str,
    return_mode: str,
    selected_rows: list[dict[str, str]],
    summary_rows: list[dict[str, object]],
    skipped_rows: list[dict[str, object]],
    cost_comparison_rows: list[dict[str, object]],
    warnings: list[str],
) -> None:
    direction_title = "Long" if direction == "long" else "Short"
    lines = [
        f"# Preferred Feature Backtest Report - {direction_title}",
        "",
        "This report is research-only. Feature filters are not trading signals, and these results are exploratory.",
        "",
        "## Configuration",
        "",
        f"- Direction: `{direction}`",
        f"- Symbols: {', '.join(symbols)}",
        f"- Timeframe: `{timeframe}`",
        f"- Horizon: `{horizon}`",
        f"- Cost mode: `{cost_mode}`",
        f"- Return mode: `{return_mode}`",
        "",
        "## Selected Features",
        "",
        *selected_feature_lines(selected_rows),
        "",
        "## Feature Families",
        "",
        *family_summary(selected_rows),
        "",
        "## Best Rows vs Baseline",
        "",
        *best_vs_baseline_lines(summary_rows),
        "",
        "## Rows Less Bad Than Baseline",
        "",
        *less_bad_lines(summary_rows),
        "",
        "## Rows Failing Absolute Profitability",
        "",
        *absolute_failure_lines(summary_rows),
        "",
        "## Skipped / Untestable Features",
        "",
        *skipped_feature_lines(skipped_rows),
        "",
        "## Scenario Source Warning",
        "",
        "- `preferred_shortlist_feature` rows come from the preferred shortlist.",
        "- `standard_context_scenario` and `extra_default_scenario` rows come from the existing backtest workflow and are diagnostic context unless `--strict-shortlist-only` was used.",
        "- Compare scenario sources before interpreting a row as preferred-feature evidence.",
        "",
        "## Top Exploratory Rows",
        "",
        *top_summary_lines(summary_rows),
        "",
        "## Cost-Aware Interpretation",
        "",
        "- Estimated-net rows should be read against their own same-symbol baseline before treating a feature as promising.",
        "- Rows that are less bad than baseline still fail if mean return is non-positive or profit factor is below 1.",
        "- Zero-trade conditions are written to `skipped_features.csv` instead of being mixed with tested rows.",
    ]
    if cost_comparison_rows:
        erased_count = sum(1 for row in cost_comparison_rows if row.get("costs_erased_gross_edge") == "true")
        lines.append(
            f"- Gross/net comparison rows loaded: {len(cost_comparison_rows)}; costs_erased_gross_edge rows: {erased_count}."
        )
    else:
        lines.append("- Gross/net comparison was not requested or no matching gross run was available.")

    lines.extend(
        [
            "",
            "## Warnings",
            "",
            "- Cost-aware net results are estimates and depend on local cost configuration quality.",
            "- This report does not establish strategy validity or deployment readiness.",
            "- The next research step for any surviving feature is yearly validation or walk-forward review.",
        ]
    )
    if warnings:
        lines.extend(["", "## Missing Or Partial Inputs", ""])
        lines.extend(f"- {warning}" for warning in warnings)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def comparison_key(row: dict[str, object]) -> tuple[str, str, str, str, str, str, str, str]:
    return (
        str(row.get("symbol") or ""),
        str(row.get("timeframe") or ""),
        str(row.get("horizon") or row.get("target_horizon") or ""),
        str(row.get("direction") or ""),
        str(row.get("feature") or ""),
        str(row.get("scenario_condition_tested") or row.get("condition") or ""),
        str(row.get("condition_type") or row.get("scenario_type") or ""),
        str(row.get("condition_value") or row.get("bucket") or ""),
    )


def build_cost_comparison_rows(
    *,
    output_root: Path,
    gross_comparison_run_id: str | None,
    direction: str,
    detail_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not gross_comparison_run_id:
        return []
    gross_path = output_root / gross_comparison_run_id / direction / DETAIL_FILE
    if not gross_path.exists():
        return []

    gross_rows = read_csv_rows(gross_path)
    gross_by_key = {comparison_key(row): row for row in gross_rows}
    comparison_rows: list[dict[str, object]] = []
    for net_row in detail_rows:
        gross_row = gross_by_key.get(comparison_key(net_row))
        if gross_row is None:
            continue
        gross_mean = safe_float(gross_row.get("mean_return"))
        net_mean = safe_float(net_row.get("mean_return"))
        gross_pf = safe_float(gross_row.get("profit_factor"))
        net_pf = safe_float(net_row.get("profit_factor"))
        erased_edge = (
            gross_mean is not None
            and net_mean is not None
            and gross_mean > 0
            and net_mean <= 0
        ) or (
            gross_pf is not None
            and net_pf is not None
            and gross_pf >= 1
            and net_pf < 1
        )
        comparison_rows.append(
            {
                "symbol": net_row.get("symbol", ""),
                "timeframe": net_row.get("timeframe", ""),
                "horizon": net_row.get("horizon", ""),
                "direction": net_row.get("direction", ""),
                "feature": net_row.get("feature", ""),
                "feature_family": net_row.get("feature_family", ""),
                "scenario_condition_tested": net_row.get("scenario_condition_tested", ""),
                "condition_type": net_row.get("condition_type", ""),
                "bucket": net_row.get("bucket", ""),
                "condition_value": net_row.get("condition_value", ""),
                "gross_mean_return": gross_row.get("mean_return", ""),
                "net_mean_return": net_row.get("mean_return", ""),
                "mean_return_cost_impact": metric_delta(net_row.get("mean_return"), gross_row.get("mean_return")),
                "gross_profit_factor": gross_row.get("profit_factor", ""),
                "net_profit_factor": net_row.get("profit_factor", ""),
                "profit_factor_cost_impact": metric_delta(net_row.get("profit_factor"), gross_row.get("profit_factor")),
                "costs_erased_gross_edge": "true" if erased_edge else "false",
                "notes": f"compared with gross run {gross_comparison_run_id}",
            }
        )
    return comparison_rows


def build_direction_outputs(
    *,
    input_root: Path,
    output_root: Path,
    run_id: str,
    symbols: list[str],
    timeframe: str,
    horizon: int,
    direction: str,
    cost_mode: str,
    return_mode: str,
    cost_config: Path | None,
    strict_cost_config: bool,
    db_path: Path,
    max_features: int | None,
    overwrite: bool,
    gross_comparison_run_id: str | None,
    strict_shortlist_only: bool,
    runner: BacktestRunner,
) -> dict[str, Path]:
    normalized_direction = normalize_direction(direction)
    output_dir = direction_output_dir(output_root, run_id=run_id, direction=normalized_direction)
    ensure_direction_outputs_writable(output_dir, overwrite)

    shortlist_rows, warnings = load_shortlist_rows(
        input_root=input_root,
        direction=normalized_direction,
        timeframe=timeframe,
        horizon=horizon,
    )
    selected_rows = select_priority_features(
        shortlist_rows,
        direction=normalized_direction,
        max_features=max_features,
    )
    selected_metadata = feature_metadata(selected_rows)

    detail_rows: list[dict[str, object]] = []
    skipped_rows: list[dict[str, object]] = []
    if selected_rows:
        for symbol in symbols:
            summary_path, source_status = run_or_reuse_symbol_backtest(
                output_root=output_root,
                run_id=run_id,
                symbol=symbol,
                timeframe=timeframe,
                horizon=horizon,
                direction=normalized_direction,
                selected_rows=selected_rows,
                cost_mode=cost_mode,
                return_mode=return_mode,
                cost_config=cost_config,
                strict_cost_config=strict_cost_config,
                db_path=db_path,
                overwrite=overwrite,
                runner=runner,
            )
            symbol_rows, symbol_skipped_rows = detail_rows_from_backtest_summary(
                summary_path=summary_path,
                source_status=source_status,
                selected_metadata=selected_metadata,
                fallback_symbol=symbol,
                fallback_timeframe=timeframe,
                fallback_horizon=horizon,
                direction=normalized_direction,
                cost_mode=cost_mode,
                return_mode=return_mode,
                strict_shortlist_only=strict_shortlist_only,
            )
            if not symbol_rows:
                warnings.append(f"No selected feature scenarios found in {summary_path}")
            detail_rows.extend(symbol_rows)
            skipped_rows.extend(symbol_skipped_rows)
    else:
        warnings.append("No shortlist rows met the controlled-testing and caution filters.")

    summary_rows = build_summary_rows(detail_rows)
    cost_comparison_rows = build_cost_comparison_rows(
        output_root=output_root,
        gross_comparison_run_id=gross_comparison_run_id,
        direction=normalized_direction,
        detail_rows=detail_rows,
    )
    summary_path = output_dir / SUMMARY_FILE
    detail_path = output_dir / DETAIL_FILE
    skipped_path = output_dir / SKIPPED_FILE
    cost_comparison_path = output_dir / COST_COMPARISON_FILE
    report_path = output_dir / REPORT_FILE
    write_csv(summary_path, summary_rows, SUMMARY_FIELDNAMES)
    write_csv(detail_path, detail_rows, DETAIL_FIELDNAMES)
    write_csv(skipped_path, skipped_rows, SKIPPED_FIELDNAMES)
    if cost_comparison_rows:
        write_csv(cost_comparison_path, cost_comparison_rows, COST_COMPARISON_FIELDNAMES)
    write_report(
        report_path,
        direction=normalized_direction,
        symbols=symbols,
        timeframe=timeframe,
        horizon=horizon,
        cost_mode=cost_mode,
        return_mode=return_mode,
        selected_rows=selected_rows,
        summary_rows=summary_rows,
        skipped_rows=skipped_rows,
        cost_comparison_rows=cost_comparison_rows,
        warnings=warnings,
    )
    outputs = {
        "preferred_feature_backtest_summary": summary_path,
        "preferred_feature_backtest_detail": detail_path,
        "skipped_features": skipped_path,
        "preferred_feature_backtest_report": report_path,
    }
    if cost_comparison_rows:
        outputs["cost_comparison"] = cost_comparison_path
    return outputs


def run_preferred_feature_backtests(
    args: argparse.Namespace,
    *,
    runner: BacktestRunner = run_single_feature_backtest,
) -> dict[str, dict[str, Path]]:
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    timeframe = str(args.timeframe).strip().upper()
    if not timeframe:
        raise ValueError("--timeframe cannot be empty.")
    horizon = int(args.horizon)
    symbols = normalize_symbols(list(args.symbols))
    directions = [normalize_direction(direction) for direction in args.directions]
    max_features = args.max_features if args.max_features is None else int(args.max_features)
    run_id = str(getattr(args, "run_id", "") or current_run_id())

    outputs: dict[str, dict[str, Path]] = {}
    for direction in directions:
        outputs[direction] = build_direction_outputs(
            input_root=Path(args.input_root),
            output_root=Path(args.output_root),
            run_id=run_id,
            symbols=symbols,
            timeframe=timeframe,
            horizon=horizon,
            direction=direction,
            cost_mode=cost_mode,
            return_mode=return_mode,
            cost_config=args.cost_config,
            strict_cost_config=bool(args.strict_cost_config),
            db_path=Path(getattr(args, "db_path", BACKTEST_DATABASE_PATH)),
            max_features=max_features,
            overwrite=bool(args.overwrite),
            gross_comparison_run_id=getattr(args, "gross_comparison_run_id", None),
            strict_shortlist_only=bool(getattr(args, "strict_shortlist_only", False)),
            runner=runner,
        )
    return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run research-only preferred feature backtests using the existing single-feature backtest workflow."
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--directions", nargs="+", choices=DEFAULT_DIRECTIONS, default=list(DEFAULT_DIRECTIONS))
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT, help=f"Default: {DEFAULT_INPUT_ROOT}")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=f"Default: {DEFAULT_OUTPUT_ROOT}")
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--max-features", type=int)
    parser.add_argument("--run-id", help="Optional output run ID. Defaults to a timestamp when omitted.")
    parser.add_argument(
        "--gross-comparison-run-id",
        help="Optional gross/none preferred-feature run ID to compare against the current estimated/net output.",
    )
    parser.add_argument(
        "--strict-shortlist-only",
        action="store_true",
        help="Keep only scenarios whose feature is in the preferred shortlist; default keeps and tags standard context rows.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--db-path", type=Path, default=BACKTEST_DATABASE_PATH, help=f"Default: {BACKTEST_DATABASE_PATH}")
    return parser.parse_args(argv)


def main() -> int:
    try:
        outputs = run_preferred_feature_backtests(parse_args())
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"Preferred feature backtests failed: {exc}")
        return 1

    print("Preferred feature backtests complete.")
    for direction, paths in outputs.items():
        print(f"Direction: {direction}")
        for label, path in paths.items():
            print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
