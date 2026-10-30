import argparse
import csv
from pathlib import Path
import sqlite3
from statistics import mean, median

from research_metrics import (
    calculate_cumulative_return,
    calculate_max_drawdown,
    calculate_profit_factor,
    csv_safe_value,
    directional_return,
    normalize_direction,
)
from research_costs import (
    cost_report_fields,
    cost_report_warnings,
    cost_adjusted_return_metrics,
    load_cost_config,
    validate_estimated_cost_config,
    validate_cost_args,
)
try:
    from feature_safety import is_future_or_target_column
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.backtest_research
    from scripts.feature_safety import is_future_or_target_column
try:
    from session_utils import SESSION_NAMES, session_name
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.backtest_research
    from scripts.session_utils import SESSION_NAMES, session_name


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_RANKING_PATH = BASE_DIR / "reports" / "ml_research" / "summary_feature_ranking.csv"
DEFAULT_AGGREGATE_RANKING_PATH = BASE_DIR / "reports" / "ml_research" / "aggregate_feature_ranking.csv"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "backtests"
TABLE_NAME = "ml_dataset"
MIN_TRADES = 200

EXCLUDED_FEATURES = {
    "id",
    "symbol",
    "timeframe",
    "time_server",
    "source",
    "created_at",
    "tick_volume",
}

NEWS_BINARY_FEATURES = [
    "blackout_window_30m",
    "has_high_impact_news_next_30m",
    "post_news_window_30m",
]

VOLUME_BINARY_FEATURES = [
    "volume_spike_20",
    "volume_dry_up_20",
]

VOLUME_NUMERIC_FEATURES = [
    "tick_volume_ratio_20",
    "tick_volume_zscore_100",
    "tick_volume_percentile_100",
    "spread_to_volume_ratio",
    "volume_vs_hour_avg",
    "volume_vs_session_avg",
]

OUTPUT_SUMMARY = "backtest_research_summary.csv"
OUTPUT_TOP = "backtest_research_top_scenarios.csv"


def default_output_dir(symbol: str, timeframe: str, target_horizon: int, direction: str) -> Path:
    return DEFAULT_OUTPUT_DIR / direction / f"{symbol}_{timeframe}_h{target_horizon}"


def default_symbol_ranking_path(symbol: str, timeframe: str, target_horizon: int, direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "ml_research"
        / direction
        / f"{symbol}_{timeframe}_h{target_horizon}"
        / "summary_feature_ranking.csv"
    )


def default_direction_aggregate_ranking_path(direction: str) -> Path:
    return BASE_DIR / "reports" / "ml_research" / direction / "aggregate_feature_ranking.csv"


def table_exists(connection: sqlite3.Connection) -> bool:
    cursor = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    )
    return cursor.fetchone() is not None


def to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def load_rows(db_path: Path, symbol: str, timeframe: str, return_column: str) -> list[dict[str, object]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        if not table_exists(connection):
            raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")

        rows = connection.execute(
            f"""
            SELECT *
            FROM {TABLE_NAME}
            WHERE symbol = ?
              AND timeframe = ?
              AND {return_column} IS NOT NULL
            ORDER BY time_server ASC
            """,
            (symbol, timeframe),
        ).fetchall()

    return [dict(row) for row in rows]


def load_ranking_features(ranking_path: Path | None, top_features: int) -> list[str]:
    path = ranking_path
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(f"Ranking file not found: {path}")

    features = []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            feature = row.get("feature", "").strip()
            if feature and feature not in EXCLUDED_FEATURES and not is_future_or_target_column(feature):
                features.append(feature)
            if len(features) >= top_features:
                break
    return features


def numeric_values(rows: list[dict[str, object]], feature: str) -> list[float]:
    values = []
    for row in rows:
        value = to_float(row.get(feature))
        if value is not None:
            values.append(value)
    return values


def is_binary_feature(rows: list[dict[str, object]], feature: str) -> bool:
    values = {to_float(row.get(feature)) for row in rows if to_float(row.get(feature)) is not None}
    return bool(values) and values.issubset({0.0, 1.0})


def percentile(sorted_values: list[float], ratio: float) -> float | None:
    if not sorted_values:
        return None
    index = int((len(sorted_values) - 1) * ratio)
    return sorted_values[index]


def quantile_bounds(values: list[float]) -> tuple[float, float] | None:
    unique_values = sorted(set(values))
    if len(unique_values) < 3:
        return None
    low_cutoff = percentile(sorted(values), 1 / 3)
    high_cutoff = percentile(sorted(values), 2 / 3)
    if low_cutoff is None or high_cutoff is None or low_cutoff == high_cutoff:
        return None
    return low_cutoff, high_cutoff


def filter_rows_by_feature(rows: list[dict[str, object]], feature: str, mode: str) -> list[dict[str, object]]:
    if mode in {"0", "1"}:
        expected = 1.0 if mode == "1" else 0.0
        return [row for row in rows if to_float(row.get(feature)) == expected]

    values = numeric_values(rows, feature)
    bounds = quantile_bounds(values)
    if bounds is None:
        return []
    low_cutoff, high_cutoff = bounds

    if mode == "low_tercile":
        return [
            row for row in rows
            if to_float(row.get(feature)) is not None and to_float(row.get(feature)) <= low_cutoff
        ]
    if mode == "mid_tercile":
        return [
            row for row in rows
            if to_float(row.get(feature)) is not None
            and low_cutoff < to_float(row.get(feature)) <= high_cutoff
        ]
    if mode == "high_tercile":
        return [
            row for row in rows
            if to_float(row.get(feature)) is not None and to_float(row.get(feature)) > high_cutoff
        ]

    raise ValueError(f"Unsupported feature filter mode: {mode}")


def day_name(day_of_week: int | None) -> str | None:
    names = {
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
        5: "Saturday",
        6: "Sunday",
    }
    return names.get(day_of_week)


def returns_from_rows(rows: list[dict[str, object]], return_column: str, direction: str) -> list[float]:
    returns = []
    for row in rows:
        value = directional_return(row.get(return_column), direction)
        if value is not None:
            returns.append(value)
    return returns


def max_drawdown(returns: list[float]) -> float | None:
    return calculate_max_drawdown(returns)


def profit_factor(returns: list[float]) -> float | None:
    return calculate_profit_factor(returns)


def scenario_metrics(
    *,
    scenario_name: str,
    scenario_type: str,
    feature: str,
    bucket: str,
    rows: list[dict[str, object]],
    return_column: str,
    direction: str,
    symbol: str,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
) -> dict[str, object]:
    cost_metrics = cost_adjusted_return_metrics(
        rows,
        symbol=symbol,
        return_column=return_column,
        direction=direction,
        cost_config=cost_config,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )
    trades_count = int(cost_metrics["trades_count"])

    return {
        "direction": direction,
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "scenario_name": scenario_name,
        "scenario_type": scenario_type,
        "feature": feature,
        "bucket": bucket,
        "sample_flag": "ok" if trades_count >= MIN_TRADES else "low_sample",
        "trades_count": trades_count,
        "mean_return": cost_metrics["mean_return"],
        "median_return": cost_metrics["median_return"],
        "win_rate": cost_metrics["win_rate"],
        "cumulative_return": cost_metrics["cumulative_return"],
        "max_drawdown": cost_metrics["max_drawdown"],
        "profit_factor": cost_metrics["profit_factor"],
        "monthly_positive_ratio": cost_metrics["monthly_positive_ratio"],
        "quarterly_positive_ratio": cost_metrics["quarterly_positive_ratio"],
        "best_month_contribution_pct": cost_metrics["best_month_contribution_pct"],
        "top_5_percent_trades_contribution_pct": cost_metrics["top_5_percent_trades_contribution_pct"],
        "max_flat_period_bars": cost_metrics["max_flat_period_bars"],
        "avg_positive_return": cost_metrics["avg_positive_return"],
        "avg_negative_return": cost_metrics["avg_negative_return"],
        "payoff_ratio": cost_metrics["payoff_ratio"],
        "breakeven_winrate": cost_metrics["breakeven_winrate"],
        "breakeven_winrate_margin": cost_metrics["breakeven_winrate_margin"],
        "avg_estimated_cost_return": cost_metrics["avg_estimated_cost_return"],
        "median_estimated_cost_return": cost_metrics["median_estimated_cost_return"],
        "gross_mean_return": cost_metrics["gross_mean_return"],
        "net_mean_return": cost_metrics["net_mean_return"],
        "gross_profit_factor": cost_metrics["gross_profit_factor"],
        "net_profit_factor": cost_metrics["net_profit_factor"],
        "gross_max_drawdown": cost_metrics["gross_max_drawdown"],
        "net_max_drawdown": cost_metrics["net_max_drawdown"],
        "gross_cumulative_return": cost_metrics["gross_cumulative_return"],
        "net_cumulative_return": cost_metrics["net_cumulative_return"],
    }


def cumulative_return(returns: list[float]) -> float | None:
    return calculate_cumulative_return(returns)


def add_scenario(
    scenarios: list[dict[str, object]],
    seen: set[tuple[str, str, str]],
    *,
    scenario_type: str,
    feature: str,
    bucket: str,
    rows: list[dict[str, object]],
    return_column: str,
    direction: str,
    symbol: str,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
) -> None:
    key = (scenario_type, feature, bucket)
    if key in seen:
        return
    seen.add(key)
    scenario_name = f"{scenario_type}:{feature}:{bucket}"
    scenarios.append(
        scenario_metrics(
            scenario_name=scenario_name,
            scenario_type=scenario_type,
            feature=feature,
            bucket=bucket,
            rows=rows,
            return_column=return_column,
            direction=direction,
            symbol=symbol,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
        )
    )


def build_scenarios(
    rows: list[dict[str, object]],
    ranked_features: list[str],
    return_column: str,
    direction: str,
    symbol: str,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
) -> list[dict[str, object]]:
    scenarios = []
    seen: set[tuple[str, str, str]] = set()

    add_scenario(
        scenarios,
        seen,
        scenario_type="baseline",
        feature="all",
        bucket="all",
        rows=rows,
        return_column=return_column,
        direction=direction,
        symbol=symbol,
        cost_config=cost_config,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )

    available_features = set(rows[0].keys()) if rows else set()
    for feature in ranked_features:
        if feature not in available_features:
            continue
        if feature in {"hour", "day_of_week", "ma_diff"}:
            continue

        if is_binary_feature(rows, feature):
            for bucket in ("0", "1"):
                add_scenario(
                    scenarios,
                    seen,
                    scenario_type="binary_feature",
                    feature=feature,
                    bucket=bucket,
                    rows=filter_rows_by_feature(rows, feature, bucket),
                    return_column=return_column,
                    direction=direction,
                    symbol=symbol,
                    cost_config=cost_config,
                    cost_mode=cost_mode,
                    return_mode=return_mode,
                )
        else:
            for bucket in ("low_tercile", "mid_tercile", "high_tercile"):
                add_scenario(
                    scenarios,
                    seen,
                    scenario_type="numeric_tercile",
                    feature=feature,
                    bucket=bucket,
                    rows=filter_rows_by_feature(rows, feature, bucket),
                    return_column=return_column,
                    direction=direction,
                    symbol=symbol,
                    cost_config=cost_config,
                    cost_mode=cost_mode,
                    return_mode=return_mode,
                )

    for bucket in SESSION_NAMES:
        add_scenario(
            scenarios,
            seen,
            scenario_type="hour_session",
            feature="hour",
            bucket=bucket,
            rows=[row for row in rows if session_name(to_int(row.get("hour"))) == bucket],
            return_column=return_column,
            direction=direction,
            symbol=symbol,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
        )

    for day in range(7):
        bucket = day_name(day)
        add_scenario(
            scenarios,
            seen,
            scenario_type="day_of_week",
            feature="day_of_week",
            bucket=bucket or str(day),
            rows=[row for row in rows if to_int(row.get("day_of_week")) == day],
            return_column=return_column,
            direction=direction,
            symbol=symbol,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
        )

    for bucket, predicate in (
        ("ma_diff_gt_0", lambda value: value is not None and value > 0),
        ("ma_diff_lt_0", lambda value: value is not None and value < 0),
    ):
        add_scenario(
            scenarios,
            seen,
            scenario_type="ma_diff",
            feature="ma_diff",
            bucket=bucket,
            rows=[row for row in rows if predicate(to_float(row.get("ma_diff")))],
            return_column=return_column,
            direction=direction,
            symbol=symbol,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
        )

    for feature in VOLUME_BINARY_FEATURES:
        if feature not in available_features:
            continue
        for bucket in ("0", "1"):
            add_scenario(
                scenarios,
                seen,
                scenario_type="binary_feature",
                feature=feature,
                bucket=bucket,
                rows=filter_rows_by_feature(rows, feature, bucket),
                return_column=return_column,
                direction=direction,
                symbol=symbol,
                cost_config=cost_config,
                cost_mode=cost_mode,
                return_mode=return_mode,
            )

    for feature in VOLUME_NUMERIC_FEATURES:
        if feature not in available_features:
            continue
        for bucket in ("low_tercile", "high_tercile"):
            add_scenario(
                scenarios,
                seen,
                scenario_type="numeric_tercile",
                feature=feature,
                bucket=bucket,
                rows=filter_rows_by_feature(rows, feature, bucket),
                return_column=return_column,
                direction=direction,
                symbol=symbol,
                cost_config=cost_config,
                cost_mode=cost_mode,
                return_mode=return_mode,
            )

    for feature in NEWS_BINARY_FEATURES:
        if feature not in available_features:
            continue
        for bucket in ("0", "1"):
            add_scenario(
                scenarios,
                seen,
                scenario_type="news_feature",
                feature=feature,
                bucket=bucket,
                rows=filter_rows_by_feature(rows, feature, bucket),
                return_column=return_column,
                direction=direction,
                symbol=symbol,
                cost_config=cost_config,
                cost_mode=cost_mode,
                return_mode=return_mode,
            )

    return scenarios


def sort_top_scenarios(scenarios: list[dict[str, object]]) -> list[dict[str, object]]:
    eligible = [scenario for scenario in scenarios if scenario["sample_flag"] == "ok"]

    def sort_key(scenario: dict[str, object]) -> tuple[float, float, int]:
        pf = scenario["profit_factor"]
        if pf is None:
            pf_value = -1.0
        elif pf == float("inf"):
            pf_value = 1_000_000.0
        else:
            pf_value = float(pf)

        drawdown = scenario["max_drawdown"]
        drawdown_value = abs(float(drawdown)) if drawdown is not None else 1_000_000.0
        return (-pf_value, drawdown_value, -int(scenario["trades_count"]))

    return sorted(eligible, key=sort_key)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "timeframe",
        "target_horizon",
        "direction",
        "cost_mode",
        "return_mode",
        "cost_config_source",
        "point_size_source",
        "spread_source_used",
        "symbols_using_default_costs",
        "scenario_name",
        "scenario_type",
        "feature",
        "bucket",
        "sample_flag",
        "trades_count",
        "mean_return",
        "median_return",
        "win_rate",
        "cumulative_return",
        "max_drawdown",
        "profit_factor",
        "monthly_positive_ratio",
        "quarterly_positive_ratio",
        "best_month_contribution_pct",
        "top_5_percent_trades_contribution_pct",
        "max_flat_period_bars",
        "avg_positive_return",
        "avg_negative_return",
        "payoff_ratio",
        "breakeven_winrate",
        "breakeven_winrate_margin",
        "avg_estimated_cost_return",
        "median_estimated_cost_return",
        "gross_mean_return",
        "net_mean_return",
        "gross_profit_factor",
        "net_profit_factor",
        "gross_max_drawdown",
        "net_max_drawdown",
        "gross_cumulative_return",
        "net_cumulative_return",
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe_value(value) for key, value in row.items()})


def run_backtest(args: argparse.Namespace) -> None:
    if args.top_features <= 0:
        raise ValueError("--top-features must be greater than zero.")

    symbol = args.symbol.strip().upper()
    timeframe = args.timeframe.strip().upper()
    direction = normalize_direction(args.direction)
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    cost_config = load_cost_config(args.cost_config)
    return_column = f"future_return_{args.target_horizon}"
    rows = load_rows(args.db_path, symbol, timeframe, return_column)
    if not rows:
        raise ValueError(f"No valid rows found for {symbol} {timeframe} using {return_column}.")
    cost_report = {}
    if cost_mode == "estimated":
        cost_report = validate_estimated_cost_config(
            symbols=[symbol],
            rows_by_symbol={symbol: rows},
            config=cost_config,
            strict=args.strict_cost_config,
        )
        for warning in cost_report_warnings(cost_report):
            print(f"Warning: {warning}")

    ranking_path = args.ranking_path
    if ranking_path is None:
        symbol_ranking_path = default_symbol_ranking_path(symbol, timeframe, args.target_horizon, direction)
        direction_aggregate_path = default_direction_aggregate_ranking_path(direction)
        if symbol_ranking_path.exists():
            ranking_path = symbol_ranking_path
        elif direction_aggregate_path.exists():
            ranking_path = direction_aggregate_path
        elif DEFAULT_RANKING_PATH.exists():
            ranking_path = DEFAULT_RANKING_PATH
        elif DEFAULT_AGGREGATE_RANKING_PATH.exists():
            ranking_path = DEFAULT_AGGREGATE_RANKING_PATH

    ranked_features = load_ranking_features(ranking_path, args.top_features)
    if not ranked_features:
        ranked_features = [
            "return_20",
            "volatility_20",
            "ma_diff",
            "tick_volume_ratio_20",
            "volume_vs_hour_avg",
            "volume_vs_session_avg",
            "spread_to_volume_ratio",
            "volume_spike_20",
            "volume_dry_up_20",
            "spread_avg_20",
            "minutes_to_next_news",
            "minutes_from_last_news",
            "blackout_window_30m",
            "has_high_impact_news_next_30m",
            "post_news_window_30m",
        ][: args.top_features]

    scenarios = build_scenarios(
        rows,
        ranked_features,
        return_column,
        direction,
        symbol,
        cost_config,
        cost_mode,
        return_mode,
    )
    top_scenarios = sort_top_scenarios(scenarios)
    for scenario in scenarios:
        scenario["symbol"] = symbol
        scenario["timeframe"] = timeframe
        scenario["target_horizon"] = args.target_horizon
        scenario["direction"] = direction
        scenario["cost_mode"] = cost_mode
        scenario["return_mode"] = return_mode
        scenario.update(cost_report_fields(cost_report, symbol))

    if args.output_dir is None:
        output_dir = default_output_dir(symbol, timeframe, args.target_horizon, direction)
    else:
        output_dir = Path(args.output_dir)
    summary_path = output_dir / OUTPUT_SUMMARY
    top_path = output_dir / OUTPUT_TOP
    write_csv(summary_path, scenarios)
    write_csv(top_path, top_scenarios)

    print(f"Output directory: {output_dir.resolve()}")
    print(f"Backtest research summary written: {summary_path.resolve()}")
    print(f"Top scenarios written: {top_path.resolve()}")
    print(f"Rows analyzed: {len(rows)}")
    print(f"Cost mode: {cost_mode}")
    print(f"Return mode: {return_mode}")
    print(f"Strict cost config: {str(args.strict_cost_config).lower()}")
    print(f"Ranking path used: {ranking_path if ranking_path is not None else 'fallback feature list'}")
    print(f"Ranking features used: {', '.join(ranked_features)}")
    print("Best scenarios:")
    for scenario in top_scenarios[:20]:
        print(
            "- {scenario_name}: trades={trades_count}, profit_factor={profit_factor}, "
            "max_drawdown={max_drawdown}, mean_return={mean_return}, win_rate={win_rate}".format(**scenario)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run exploratory research backtests from ml_dataset feature scenarios."
    )
    parser.add_argument("--symbol", required=True, help="Symbol to analyze, for example EURUSD.")
    parser.add_argument("--timeframe", required=True, help="Timeframe to analyze, for example M15.")
    parser.add_argument("--target-horizon", type=int, choices=(5, 10, 20), default=10)
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--ranking-path", type=Path, help=f"Optional ranking CSV. Default if present: {DEFAULT_RANKING_PATH}")
    parser.add_argument("--top-features", type=int, default=10)
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional output directory. Default: reports/backtests/{DIRECTION}/{SYMBOL}_{TIMEFRAME}_h{TARGET_HORIZON}",
    )
    return parser.parse_args()


def main() -> int:
    try:
        run_backtest(parse_args())
    except (FileNotFoundError, ValueError, sqlite3.Error, OSError) as exc:
        print(f"Backtest research failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
