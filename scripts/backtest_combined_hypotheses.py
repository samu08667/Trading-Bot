import argparse
import csv
from itertools import combinations
from pathlib import Path
import sqlite3
from statistics import mean, median

from research_metrics import (
    calculate_cumulative_return,
    calculate_max_drawdown,
    calculate_max_drawdown_improvement_pct,
    calculate_profit_factor,
    calculate_profit_factor_improvement_pct,
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
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.backtest_combined_hypotheses
    from scripts.feature_safety import is_future_or_target_column
try:
    from session_utils import normalize_session_name, session_name
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.backtest_combined_hypotheses
    from scripts.session_utils import normalize_session_name, session_name


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_INPUT_DIR = BASE_DIR / "reports" / "backtests"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "backtests" / "combined"
HYPOTHESES_FILE = "selected_research_hypotheses.csv"
TABLE_NAME = "ml_dataset"
EXCLUDED_COMBINATION_FEATURES = {
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
}

OUTPUT_SUMMARY = "combined_hypotheses_summary.csv"
OUTPUT_TOP = "combined_hypotheses_top.csv"
OUTPUT_REPORT = "combined_hypotheses_report.md"


def default_output_dir(symbol: str, timeframe: str, target_horizon: int, direction: str) -> Path:
    return DEFAULT_OUTPUT_DIR / direction / f"{symbol}_{timeframe}_h{target_horizon}"


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


def load_ml_rows(db_path: Path, symbol: str, timeframe: str, return_column: str) -> list[dict[str, object]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (TABLE_NAME,),
        )
        if cursor.fetchone() is None:
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


def load_hypotheses(input_dir: Path, top_hypotheses: int) -> list[dict[str, str]]:
    path = input_dir / HYPOTHESES_FILE
    if not path.exists():
        raise FileNotFoundError(f"Hypotheses file not found: {path}")

    rows = []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            decision = row.get("decision", "").strip()
            if decision in {"select", "watchlist"}:
                rows.append(row)
    rows.sort(
        key=lambda row: (
            {"select": 0, "watchlist": 1}.get(row.get("decision", ""), 2),
            -int(float(row.get("selection_score") or 0)),
            int(float(row.get("rank") or 999999)),
        )
    )
    return rows[:top_hypotheses]


def parse_scenario_key(scenario_key: str) -> tuple[str, str, str] | None:
    parts = scenario_key.split(":")
    if len(parts) < 3:
        return None
    scenario_type = parts[0]
    feature = parts[1]
    bucket = ":".join(parts[2:])
    return scenario_type, feature, bucket


def numeric_values(rows: list[dict[str, object]], feature: str) -> list[float]:
    values = []
    for row in rows:
        value = to_float(row.get(feature))
        if value is not None:
            values.append(value)
    return values


def percentile(sorted_values: list[float], ratio: float) -> float | None:
    if not sorted_values:
        return None
    index = int((len(sorted_values) - 1) * ratio)
    return sorted_values[index]


def tercile_bounds(rows: list[dict[str, object]], feature: str) -> tuple[float, float] | None:
    values = sorted(numeric_values(rows, feature))
    if len(set(values)) < 3:
        return None
    low = percentile(values, 1 / 3)
    high = percentile(values, 2 / 3)
    if low is None or high is None or low == high:
        return None
    return low, high


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


def build_condition(rows: list[dict[str, object]], scenario_key: str):
    parsed = parse_scenario_key(scenario_key)
    if parsed is None:
        return None

    scenario_type, feature, bucket = parsed
    if feature.lower() in EXCLUDED_COMBINATION_FEATURES or is_future_or_target_column(feature):
        return None
    if not rows or feature not in rows[0]:
        return None

    if scenario_type in {"binary_feature", "news_feature"} and bucket in {"0", "1"}:
        expected = float(bucket)
        return {
            "scenario_key": scenario_key,
            "feature": feature,
            "bucket": bucket,
            "predicate": lambda row, feature=feature, expected=expected: to_float(row.get(feature)) == expected,
        }

    if scenario_type == "numeric_tercile":
        bounds = tercile_bounds(rows, feature)
        if bounds is None:
            return None
        low, high = bounds
        if bucket == "low_tercile":
            predicate = lambda row, feature=feature, low=low: (
                to_float(row.get(feature)) is not None and to_float(row.get(feature)) <= low
            )
        elif bucket == "mid_tercile":
            predicate = lambda row, feature=feature, low=low, high=high: (
                to_float(row.get(feature)) is not None and low < to_float(row.get(feature)) <= high
            )
        elif bucket == "high_tercile":
            predicate = lambda row, feature=feature, high=high: (
                to_float(row.get(feature)) is not None and to_float(row.get(feature)) > high
            )
        else:
            return None
        return {
            "scenario_key": scenario_key,
            "feature": feature,
            "bucket": bucket,
            "predicate": predicate,
        }

    if scenario_type == "hour_session" and feature == "hour":
        try:
            normalized_bucket = normalize_session_name(bucket)
        except ValueError:
            return None
        return {
            "scenario_key": scenario_key,
            "feature": feature,
            "bucket": normalized_bucket,
            "predicate": lambda row, bucket=normalized_bucket: session_name(to_int(row.get("hour"))) == bucket,
        }

    if scenario_type == "day_of_week" and feature == "day_of_week":
        return {
            "scenario_key": scenario_key,
            "feature": feature,
            "bucket": bucket,
            "predicate": lambda row, bucket=bucket: day_name(to_int(row.get("day_of_week"))) == bucket,
        }

    if scenario_type == "ma_diff":
        if bucket == "ma_diff_gt_0":
            predicate = lambda row: to_float(row.get("ma_diff")) is not None and to_float(row.get("ma_diff")) > 0
        elif bucket == "ma_diff_lt_0":
            predicate = lambda row: to_float(row.get("ma_diff")) is not None and to_float(row.get("ma_diff")) < 0
        else:
            return None
        return {
            "scenario_key": scenario_key,
            "feature": feature,
            "bucket": bucket,
            "predicate": predicate,
        }

    return None


def returns_from_rows(rows: list[dict[str, object]], return_column: str, direction: str) -> list[float]:
    values = []
    for row in rows:
        value = directional_return(row.get(return_column), direction)
        if value is not None:
            values.append(value)
    return values


def cumulative_return(returns: list[float]) -> float | None:
    return calculate_cumulative_return(returns)


def max_drawdown(returns: list[float]) -> float | None:
    return calculate_max_drawdown(returns)


def profit_factor(returns: list[float]) -> float | None:
    return calculate_profit_factor(returns)


def metrics(
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
    values = returns_from_rows(rows, return_column, direction)
    positives = [item for item in values if item > 0]
    negatives = [item for item in values if item < 0]
    count = int(cost_metrics["trades_count"])
    return {
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "trades_count": count,
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


def delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def profit_factor_improvement_pct(value: float | None, baseline: float | None) -> float | None:
    return calculate_profit_factor_improvement_pct(value, baseline)


def drawdown_improvement_pct(value: float | None, baseline: float | None) -> float | None:
    return calculate_max_drawdown_improvement_pct(value, baseline)


def score_combination(result: dict[str, object], baseline: dict[str, object], min_trades: int) -> int:
    score = 0
    trades_count = int(result["trades_count"])
    pf = result["profit_factor"]
    baseline_pf = baseline["profit_factor"]
    dd = result["max_drawdown"]
    baseline_dd = baseline["max_drawdown"]

    pf_improvement = profit_factor_improvement_pct(pf, baseline_pf)
    dd_improvement = drawdown_improvement_pct(dd, baseline_dd)

    if trades_count >= min_trades:
        score += 1
    if pf is not None and baseline_pf is not None and pf > baseline_pf:
        score += 1
    if pf_improvement is not None and pf_improvement >= 5:
        score += 1
    if dd_improvement is not None and dd_improvement > 0:
        score += 1
    if dd_improvement is not None and dd_improvement >= 10:
        score += 1
    if result["win_rate"] is not None and baseline["win_rate"] is not None and result["win_rate"] > baseline["win_rate"]:
        score += 1
    if result["mean_return"] is not None and baseline["mean_return"] is not None and result["mean_return"] > baseline["mean_return"]:
        score += 1
    if trades_count < min_trades:
        score -= 3
    if pf is not None and baseline_pf is not None and pf > baseline_pf and dd_improvement is not None and dd_improvement < 0:
        score -= 2
    if dd_improvement is not None and dd_improvement <= 0:
        score -= 1
    if trades_count < 200:
        score -= 2
    return score


def build_combinations(conditions: list[dict[str, object]], max_size: int):
    max_size = min(max_size, 3)
    for size in range(2, max_size + 1):
        yield from combinations(conditions, size)


def evaluate_combinations(
    rows: list[dict[str, object]],
    conditions: list[dict[str, object]],
    return_column: str,
    direction: str,
    min_trades: int,
    max_combination_size: int,
    symbol: str,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
) -> list[dict[str, object]]:
    baseline = metrics(rows, return_column, direction, symbol, cost_config, cost_mode, return_mode)
    results = []
    for combo in build_combinations(conditions, max_combination_size):
        combo_rows = [
            row for row in rows
            if all(condition["predicate"](row) for condition in combo)
        ]
        result = metrics(combo_rows, return_column, direction, symbol, cost_config, cost_mode, return_mode)
        scenario_keys = [str(condition["scenario_key"]) for condition in combo]
        features = [str(condition["feature"]) for condition in combo]
        buckets = [str(condition["bucket"]) for condition in combo]
        result.update(
            {
                "combination_key": " AND ".join(scenario_keys),
                "combination_size": len(combo),
                "features": " | ".join(features),
                "buckets": " | ".join(buckets),
                "mean_return_delta_vs_baseline": delta(result["mean_return"], baseline["mean_return"]),
                "profit_factor_delta_vs_baseline": delta(result["profit_factor"], baseline["profit_factor"]),
                "profit_factor_improvement_pct": profit_factor_improvement_pct(
                    result["profit_factor"],
                    baseline["profit_factor"],
                ),
                "max_drawdown_delta_vs_baseline": delta(result["max_drawdown"], baseline["max_drawdown"]),
                "max_drawdown_improvement_pct": drawdown_improvement_pct(
                    result["max_drawdown"],
                    baseline["max_drawdown"],
                ),
                "win_rate_delta_vs_baseline": delta(result["win_rate"], baseline["win_rate"]),
            }
        )
        result["score"] = score_combination(result, baseline, min_trades)
        result["sample_flag"] = "ok" if int(result["trades_count"]) >= min_trades else "low_sample"
        results.append(result)
    return results


def sort_top(results: list[dict[str, object]]) -> list[dict[str, object]]:
    def key(row: dict[str, object]):
        pf = row["profit_factor"]
        pf_value = -1.0 if pf is None else (1_000_000.0 if pf == float("inf") else float(pf))
        dd = row["max_drawdown"]
        dd_abs = 1_000_000.0 if dd is None else abs(float(dd))
        return (-int(row["score"]), -pf_value, dd_abs, -int(row["trades_count"]))

    return sorted(results, key=key)


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
        "combination_key",
        "combination_size",
        "features",
        "buckets",
        "sample_flag",
        "score",
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
        "mean_return_delta_vs_baseline",
        "profit_factor_delta_vs_baseline",
        "profit_factor_improvement_pct",
        "max_drawdown_delta_vs_baseline",
        "max_drawdown_improvement_pct",
        "win_rate_delta_vs_baseline",
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


def write_markdown(
    path: Path,
    rows: list[dict[str, object]],
    symbol: str,
    timeframe: str,
    target_horizon: int,
    direction: str,
    cost_mode: str,
    return_mode: str,
    cost_fields: dict[str, str],
) -> None:
    lines = [
        "# Combined Hypotheses Research Report",
        "",
        f"Symbol: {symbol}",
        f"Timeframe: {timeframe}",
        f"Target horizon: {target_horizon}",
        f"Direction: {direction}",
        f"Cost mode: {cost_mode}",
        f"Return mode: {return_mode}",
        f"cost_config_source: {cost_fields['cost_config_source']}",
        f"point_size_source: {cost_fields['point_size_source']}",
        f"spread_source_used: {cost_fields['spread_source_used']}",
        f"symbols_using_default_costs: {cost_fields['symbols_using_default_costs'] or 'none'}",
        "",
        "These combinations are exploratory research filters, not operational trading signals.",
        "",
        "## Top Combined Hypotheses",
        "",
    ]
    if not rows:
        lines.append("- none")
    for row in rows[:20]:
        lines.append(f"### {row['combination_key']}")
        lines.append("")
        lines.append(f"- Score: {row['score']}")
        lines.append(f"- Sample flag: {row['sample_flag']}")
        lines.append(f"- Trades: {row['trades_count']}")
        lines.append(f"- Profit factor: {row['profit_factor']}")
        lines.append(f"- Profit factor delta vs baseline: {row['profit_factor_delta_vs_baseline']}")
        lines.append(f"- Profit factor improvement pct: {row['profit_factor_improvement_pct']}")
        lines.append(f"- Max drawdown: {row['max_drawdown']}")
        lines.append(f"- Max drawdown delta vs baseline: {row['max_drawdown_delta_vs_baseline']}")
        lines.append(f"- Max drawdown improvement pct: {row['max_drawdown_improvement_pct']}")
        lines.append(f"- Monthly positive ratio: {row.get('monthly_positive_ratio')}")
        lines.append(f"- Best month contribution pct: {row.get('best_month_contribution_pct')}")
        lines.append(f"- Top 5 percent trades contribution pct: {row.get('top_5_percent_trades_contribution_pct')}")
        lines.append(f"- Win rate: {row['win_rate']}")
        lines.append("")
    lines.extend(
        [
            "## Caution",
            "",
            "- This is only a controlled research backtest over combined filters.",
            "- `cumulative_return` is compounded: product(1 + returns) - 1.",
            "- It does not optimize parameters and uses at most three combined filters.",
            "- It does not use MetaTrader5, does not call order execution APIs, and does not create live signals.",
            "- Any idea that looks promising needs separate out-of-sample validation.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    if args.max_combination_size < 2:
        raise ValueError("--max-combination-size must be at least 2.")
    if args.max_combination_size > 3:
        raise ValueError("--max-combination-size cannot exceed 3.")

    symbol = args.symbol.strip().upper()
    timeframe = args.timeframe.strip().upper()
    direction = normalize_direction(args.direction)
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    cost_config = load_cost_config(args.cost_config)
    return_column = f"future_return_{args.target_horizon}"
    rows = load_ml_rows(args.db_path, symbol, timeframe, return_column)
    if not rows:
        raise ValueError(f"No rows found for {symbol} {timeframe} using {return_column}.")
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
    cost_fields = cost_report_fields(cost_report, symbol)

    input_dir = args.input_dir if args.input_dir != DEFAULT_INPUT_DIR else DEFAULT_INPUT_DIR / direction
    hypotheses = load_hypotheses(input_dir, args.top_hypotheses)
    conditions = []
    seen = set()
    for hypothesis in hypotheses:
        scenario_key = hypothesis.get("scenario_key", "")
        if scenario_key in seen:
            continue
        condition = build_condition(rows, scenario_key)
        if condition is not None:
            conditions.append(condition)
            seen.add(scenario_key)

    if len(conditions) < 2:
        raise ValueError("Need at least two usable select/watchlist hypotheses to combine.")

    results = evaluate_combinations(
        rows,
        conditions,
        return_column,
        direction,
        args.min_trades,
        args.max_combination_size,
        symbol,
        cost_config,
        cost_mode,
        return_mode,
    )
    for row in results:
        row["symbol"] = symbol
        row["timeframe"] = timeframe
        row["target_horizon"] = args.target_horizon
        row["direction"] = direction
        row["cost_mode"] = cost_mode
        row["return_mode"] = return_mode
        row.update(cost_fields)
    top_results = sort_top(results)

    if args.output_dir is None:
        output_dir = default_output_dir(symbol, timeframe, args.target_horizon, direction)
    else:
        output_dir = Path(args.output_dir)
    summary_path = output_dir / OUTPUT_SUMMARY
    top_path = output_dir / OUTPUT_TOP
    report_path = output_dir / OUTPUT_REPORT
    write_csv(summary_path, results)
    write_csv(top_path, top_results)
    write_markdown(
        report_path,
        top_results,
        symbol,
        timeframe,
        args.target_horizon,
        direction,
        cost_mode,
        return_mode,
        cost_fields,
    )

    print(f"Output directory: {output_dir}")
    print(f"Combined hypotheses summary written: {summary_path}")
    print(f"Combined hypotheses top written: {top_path}")
    print(f"Combined hypotheses report written: {report_path}")
    print(f"Rows analyzed: {len(rows)}")
    print(f"Usable hypotheses combined: {len(conditions)}")
    print(f"Cost mode: {cost_mode}")
    print(f"Return mode: {return_mode}")
    print(f"Strict cost config: {str(args.strict_cost_config).lower()}")
    print("Best combined hypotheses:")
    for row in top_results[:20]:
        print(
            "- {combination_key}: score={score}, trades={trades_count}, "
            "profit_factor={profit_factor}, max_drawdown={max_drawdown}".format(**row)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest controlled combinations of selected research hypotheses."
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--target-horizon", type=int, choices=(5, 10, 20), default=10)
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help=f"Default: {DEFAULT_INPUT_DIR}")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional output directory. Default: reports/backtests/combined/{DIRECTION}/{SYMBOL}_{TIMEFRAME}_h{TARGET_HORIZON}",
    )
    parser.add_argument("--max-combination-size", type=int, default=3)
    parser.add_argument("--min-trades", type=int, default=300)
    parser.add_argument("--top-hypotheses", type=int, default=10)
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help=f"Default: {DATABASE_PATH}")
    return parser.parse_args()


def main() -> int:
    try:
        run(parse_args())
    except (FileNotFoundError, ValueError, sqlite3.Error, OSError) as exc:
        print(f"Combined hypotheses backtest failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
