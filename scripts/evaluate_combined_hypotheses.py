import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from research_metrics import (
    calculate_max_drawdown_improvement_pct,
    calculate_profit_factor_improvement_pct,
    csv_safe_value,
    normalize_direction,
)
from research_costs import validate_cost_args


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = BASE_DIR / "reports" / "backtests" / "combined"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "backtests" / "combined" / "evaluations"
INPUT_FILE_NAME = "combined_hypotheses_summary.csv"
OUTPUT_EVALUATED = "evaluated_combined_hypotheses.csv"
OUTPUT_SELECTED = "selected_combined_hypotheses.csv"
OUTPUT_REPORT = "combined_hypotheses_decision_report.md"

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
DECISION_ORDER = {
    "strong": 0,
    "interesting": 1,
    "watchlist": 2,
    "reject": 3,
}


def to_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: object) -> int:
    parsed = to_float(value)
    return int(parsed) if parsed is not None else 0


def diff(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def profit_factor_improvement_pct(value: float | None, baseline: float | None) -> float | None:
    return calculate_profit_factor_improvement_pct(value, baseline)


def max_drawdown_improvement_pct(value: float | None, baseline: float | None) -> float | None:
    return calculate_max_drawdown_improvement_pct(value, baseline)


def average(values: list[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return sum(usable) / len(usable)


def maximum(values: list[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    return max(usable) if usable else None


def concentration_penalties(row: dict[str, object]) -> list[str]:
    penalties = []
    monthly_ratio = to_float(row.get("monthly_positive_ratio"))
    quarterly_ratio = to_float(row.get("quarterly_positive_ratio"))
    best_month = to_float(row.get("best_month_contribution_pct"))
    top_trades = to_float(row.get("top_5_percent_trades_contribution_pct"))
    if monthly_ratio is not None and monthly_ratio < 0.45:
        penalties.append("monthly_positive_ratio < 0.45")
    if quarterly_ratio is not None and quarterly_ratio < 0.50:
        penalties.append("quarterly_positive_ratio < 0.50")
    if best_month is not None and best_month > 60:
        penalties.append("best_month_contribution_pct > 60")
    if top_trades is not None and top_trades > 70:
        penalties.append("top_5_percent_trades_contribution_pct > 70")
    return penalties


def safe_key(value: object) -> str:
    return str(value or "").strip()


def find_summary_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    if input_dir.is_file():
        return [input_dir] if input_dir.name == INPUT_FILE_NAME else []
    return sorted(
        path for path in input_dir.rglob(INPUT_FILE_NAME)
        if path.parent != input_dir
        and "evaluations" not in {part.lower() for part in path.parts}
    )


def infer_metadata(path: Path, row: dict[str, str]) -> tuple[str, str, str]:
    symbol = safe_key(row.get("symbol")).upper()
    timeframe = safe_key(row.get("timeframe")).upper()
    target_horizon = safe_key(row.get("target_horizon"))
    if symbol and timeframe and target_horizon:
        return symbol, timeframe, target_horizon

    tokens = []
    for candidate in (path.parent.name, path.stem):
        normalized = candidate.upper().replace("-", "_").replace(".", "_")
        tokens.extend(part for part in normalized.split("_") if part)

    for token in tokens:
        if token in TIMEFRAMES and not timeframe:
            timeframe = token
        elif token.startswith("H") and token[1:].isdigit() and not target_horizon:
            target_horizon = token[1:]

    ignored = {"COMBINED", "HYPOTHESES", "SUMMARY", "BACKTEST", "BACKTESTS", "REPORTS"}
    for token in tokens:
        if token not in ignored and token not in TIMEFRAMES and not token.startswith("H") and not symbol:
            symbol = token

    return symbol or "UNKNOWN", timeframe or "UNKNOWN", target_horizon or "UNKNOWN"


def baseline_from_delta(value: float | None, delta_value: float | None) -> float | None:
    if value is None or delta_value is None:
        return None
    return value - delta_value


def read_summary_file(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for raw in reader:
            combination_key = safe_key(raw.get("combination_key"))
            if not combination_key:
                continue

            symbol, timeframe, target_horizon = infer_metadata(path, raw)
            profit_factor = to_float(raw.get("profit_factor"))
            max_drawdown = to_float(raw.get("max_drawdown"))
            win_rate = to_float(raw.get("win_rate"))
            mean_return = to_float(raw.get("mean_return"))

            profit_factor_delta = to_float(raw.get("profit_factor_delta_vs_baseline"))
            max_drawdown_delta = to_float(raw.get("max_drawdown_delta_vs_baseline"))
            win_rate_delta = to_float(raw.get("win_rate_delta_vs_baseline"))
            mean_return_delta = to_float(raw.get("mean_return_delta_vs_baseline"))
            baseline_drawdown = baseline_from_delta(max_drawdown, max_drawdown_delta)
            drawdown_improvement = to_float(raw.get("max_drawdown_improvement_pct"))
            if drawdown_improvement is None:
                drawdown_improvement = max_drawdown_improvement_pct(max_drawdown, baseline_drawdown)

            rows.append(
                {
                    "source_file": str(path),
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "target_horizon": target_horizon,
                    "direction": safe_key(raw.get("direction")) or "long",
                    "cost_mode": safe_key(raw.get("cost_mode")) or "none",
                    "return_mode": safe_key(raw.get("return_mode")) or "gross",
                    "combination_key": combination_key,
                    "combination_size": to_int(raw.get("combination_size")),
                    "features": safe_key(raw.get("features")),
                    "buckets": safe_key(raw.get("buckets")),
                    "sample_flag": safe_key(raw.get("sample_flag")),
                    "backtest_score": to_int(raw.get("score")),
                    "trades_count": to_int(raw.get("trades_count")),
                    "mean_return": mean_return,
                    "median_return": to_float(raw.get("median_return")),
                    "win_rate": win_rate,
                    "cumulative_return": to_float(raw.get("cumulative_return")),
                    "max_drawdown": max_drawdown,
                    "profit_factor": profit_factor,
                    "monthly_positive_ratio": to_float(raw.get("monthly_positive_ratio")),
                    "quarterly_positive_ratio": to_float(raw.get("quarterly_positive_ratio")),
                    "best_month_contribution_pct": to_float(raw.get("best_month_contribution_pct")),
                    "top_5_percent_trades_contribution_pct": to_float(
                        raw.get("top_5_percent_trades_contribution_pct")
                    ),
                    "max_flat_period_bars": to_float(raw.get("max_flat_period_bars")),
                    "avg_positive_return": to_float(raw.get("avg_positive_return")),
                    "avg_negative_return": to_float(raw.get("avg_negative_return")),
                    "payoff_ratio": to_float(raw.get("payoff_ratio")),
                    "breakeven_winrate": to_float(raw.get("breakeven_winrate")),
                    "breakeven_winrate_margin": to_float(raw.get("breakeven_winrate_margin")),
                    "baseline_profit_factor": baseline_from_delta(profit_factor, profit_factor_delta),
                    "baseline_max_drawdown": baseline_drawdown,
                    "baseline_win_rate": baseline_from_delta(win_rate, win_rate_delta),
                    "baseline_mean_return": baseline_from_delta(mean_return, mean_return_delta),
                    "max_drawdown_improvement_pct": drawdown_improvement,
                    "avg_estimated_cost_return": to_float(raw.get("avg_estimated_cost_return")),
                    "gross_profit_factor": to_float(raw.get("gross_profit_factor")),
                    "net_profit_factor": to_float(raw.get("net_profit_factor")),
                    "gross_max_drawdown": to_float(raw.get("gross_max_drawdown")),
                    "net_max_drawdown": to_float(raw.get("net_max_drawdown")),
                    "gross_cumulative_return": to_float(raw.get("gross_cumulative_return")),
                    "net_cumulative_return": to_float(raw.get("net_cumulative_return")),
                }
            )
    return rows


def read_all_rows(paths: list[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in paths:
        rows.extend(read_summary_file(path))
    return rows


def parse_conditions(combination_key: str) -> list[tuple[str, str, str]]:
    conditions = []
    for item in combination_key.split(" AND "):
        parts = item.split(":")
        if len(parts) >= 3:
            conditions.append((parts[0], parts[1], ":".join(parts[2:])))
    return conditions


def is_temporal_only(combination_key: str) -> bool:
    conditions = parse_conditions(combination_key)
    if not conditions:
        return False
    temporal_types = {"day_of_week", "hour", "hour_session"}
    temporal_features = {"day_of_week", "hour"}
    return all(item[0] in temporal_types or item[1] in temporal_features for item in conditions)


def has_specific_filter(combination_key: str) -> bool:
    conditions = parse_conditions(combination_key)
    specific_types = {"day_of_week", "hour", "hour_session", "numeric_tercile", "news_feature", "binary_feature"}
    return any(item[0] in specific_types for item in conditions)


def is_positive_result(row: dict[str, object]) -> bool:
    trades_count = int(row["trades_count"])
    pf_improvement = row["profit_factor_improvement_pct"]
    dd_improvement = row["max_drawdown_improvement_pct"]
    win_delta = row["win_rate_delta"]
    mean_delta = row["mean_return_delta"]
    return (
        trades_count > 0
        and pf_improvement is not None
        and pf_improvement > 0
        and dd_improvement is not None
        and dd_improvement >= 0
        and ((win_delta is not None and win_delta > 0) or (mean_delta is not None and mean_delta > 0))
    )


def classify(score: int) -> str:
    if score >= 8:
        return "strong"
    if 5 <= score <= 7:
        return "interesting"
    if 3 <= score <= 4:
        return "watchlist"
    return "reject"


def add_reason(reasons: list[str], condition: bool, text: str, points: int) -> int:
    if condition:
        reasons.append(f"{text} ({points:+d})")
        return points
    return 0


def score_row(row: dict[str, object], min_trades: int) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []
    trades_count = int(row["trades_count"])
    pf = row["profit_factor"]
    baseline_pf = row["baseline_profit_factor"]
    dd_improvement = row["max_drawdown_improvement_pct"]
    pf_improvement = row["profit_factor_improvement_pct"]

    score += add_reason(reasons, trades_count >= min_trades, "trades_count >= min_trades", 2)
    score += add_reason(reasons, trades_count >= 1000, "trades_count >= 1000", 1)
    score += add_reason(reasons, pf is not None and baseline_pf is not None and pf > baseline_pf, "profit_factor > baseline", 2)
    score += add_reason(reasons, pf_improvement is not None and pf_improvement >= 5, "profit_factor improves at least 5%", 1)
    score += add_reason(reasons, pf_improvement is not None and pf_improvement >= 10, "profit_factor improves at least 10%", 1)
    score += add_reason(reasons, dd_improvement is not None and dd_improvement > 0, "max_drawdown improvement > 0", 1)
    score += add_reason(reasons, dd_improvement is not None and dd_improvement >= 10, "max_drawdown improvement >= 10%", 1)
    score += add_reason(reasons, row["win_rate_delta"] is not None and row["win_rate_delta"] > 0, "win_rate improves", 1)
    score += add_reason(reasons, row["mean_return_delta"] is not None and row["mean_return_delta"] > 0, "mean_return improves", 1)

    score += add_reason(reasons, trades_count < min_trades, "trades_count < min_trades", -3)
    score += add_reason(
        reasons,
        pf_improvement is not None and pf_improvement > 0 and dd_improvement is not None and dd_improvement < 0,
        "profit_factor improves while max_drawdown worsens",
        -2,
    )
    score += add_reason(reasons, dd_improvement is not None and dd_improvement <= 0, "max_drawdown improvement <= 0", -1)
    score += add_reason(
        reasons,
        int(row["combination_size"]) > 3,
        "combination has more than three conditions",
        -1,
    )
    score += add_reason(
        reasons,
        has_specific_filter(str(row["combination_key"])) and trades_count < min_trades,
        "specific filters with low sample",
        -1,
    )
    for risk in concentration_penalties(row):
        score += add_reason(reasons, True, risk, -1)

    return score, "; ".join(reasons) if reasons else "no scoring conditions triggered"


def evaluate_rows(rows: list[dict[str, object]], min_trades: int) -> list[dict[str, object]]:
    evaluated = []
    for row in rows:
        row = dict(row)
        row["profit_factor_delta"] = diff(row["profit_factor"], row["baseline_profit_factor"])
        row["profit_factor_improvement_pct"] = profit_factor_improvement_pct(row["profit_factor"], row["baseline_profit_factor"])
        row["max_drawdown_delta"] = diff(row["max_drawdown"], row["baseline_max_drawdown"])
        if row.get("max_drawdown_improvement_pct") is None:
            row["max_drawdown_improvement_pct"] = max_drawdown_improvement_pct(
                row["max_drawdown"],
                row["baseline_max_drawdown"],
            )
        row["win_rate_delta"] = diff(row["win_rate"], row["baseline_win_rate"])
        row["mean_return_delta"] = diff(row["mean_return"], row["baseline_mean_return"])
        row["positive_result"] = 1 if is_positive_result(row) else 0
        row["row_score"], row["row_rationale"] = score_row(row, min_trades)
        row["row_classification"] = classify(int(row["row_score"]))
        evaluated.append(row)
    return evaluated


def unique_test_key(row: dict[str, object]) -> str:
    return "{symbol}|{timeframe}|{target_horizon}|{direction}".format(**row)


def aggregate_combination(
    combination_key: str,
    rows: list[dict[str, object]],
    min_trades: int,
    min_symbols: int,
) -> dict[str, object]:
    symbols_tested = sorted({str(row["symbol"]) for row in rows})
    positive_symbols = sorted({str(row["symbol"]) for row in rows if int(row["positive_result"]) == 1})
    tests_tested = sorted({unique_test_key(row) for row in rows})
    positive_tests = sorted({unique_test_key(row) for row in rows if int(row["positive_result"]) == 1})

    avg_trades_count = average([float(row["trades_count"]) for row in rows])
    avg_score = average([float(row["row_score"]) for row in rows])
    avg_pf_improvement = average([row["profit_factor_improvement_pct"] for row in rows])
    avg_dd_improvement = average([row["max_drawdown_improvement_pct"] for row in rows])
    avg_win_delta = average([row["win_rate_delta"] for row in rows])
    avg_mean_delta = average([row["mean_return_delta"] for row in rows])
    concentration_row = {
        "monthly_positive_ratio": average([to_float(row.get("monthly_positive_ratio")) for row in rows]),
        "quarterly_positive_ratio": average([to_float(row.get("quarterly_positive_ratio")) for row in rows]),
        "best_month_contribution_pct": maximum([to_float(row.get("best_month_contribution_pct")) for row in rows]),
        "top_5_percent_trades_contribution_pct": maximum(
            [to_float(row.get("top_5_percent_trades_contribution_pct")) for row in rows]
        ),
        "max_flat_period_bars": maximum([to_float(row.get("max_flat_period_bars")) for row in rows]),
    }

    max_combination_size = max(int(row["combination_size"]) for row in rows)
    low_sample_count = sum(1 for row in rows if str(row["sample_flag"]) == "low_sample" or int(row["trades_count"]) < min_trades)

    score = 0
    reasons: list[str] = []
    score += add_reason(reasons, avg_trades_count is not None and avg_trades_count >= min_trades, "average trades_count >= min_trades", 2)
    score += add_reason(reasons, avg_trades_count is not None and avg_trades_count >= 1000, "average trades_count >= 1000", 1)
    score += add_reason(reasons, avg_pf_improvement is not None and avg_pf_improvement > 0, "average profit_factor > baseline", 2)
    score += add_reason(reasons, avg_pf_improvement is not None and avg_pf_improvement >= 5, "average profit_factor improves at least 5%", 1)
    score += add_reason(reasons, avg_pf_improvement is not None and avg_pf_improvement >= 10, "average profit_factor improves at least 10%", 1)
    score += add_reason(reasons, avg_dd_improvement is not None and avg_dd_improvement > 0, "average max_drawdown improvement > 0", 1)
    score += add_reason(reasons, avg_dd_improvement is not None and avg_dd_improvement >= 10, "average max_drawdown improvement >= 10%", 1)
    score += add_reason(reasons, avg_win_delta is not None and avg_win_delta > 0, "average win_rate improves", 1)
    score += add_reason(reasons, avg_mean_delta is not None and avg_mean_delta > 0, "average mean_return improves", 1)
    score += add_reason(reasons, len(positive_symbols) >= min_symbols, "positive on at least min_symbols pairs", 2)
    score += add_reason(reasons, len(positive_symbols) >= 3, "positive on at least three pairs", 1)

    score += add_reason(reasons, avg_trades_count is not None and avg_trades_count < min_trades, "average trades_count < min_trades", -3)
    score += add_reason(
        reasons,
        avg_pf_improvement is not None and avg_pf_improvement > 0 and avg_dd_improvement is not None and avg_dd_improvement < 0,
        "profit_factor improves while max_drawdown worsens",
        -2,
    )
    score += add_reason(reasons, len(positive_symbols) == 1, "works on only one pair", -2)
    score += add_reason(reasons, is_temporal_only(combination_key), "contains only specific temporal filters", -2)
    score += add_reason(reasons, max_combination_size > 3, "contains more than three conditions", -1)
    score += add_reason(
        reasons,
        has_specific_filter(combination_key) and low_sample_count > 0,
        "specific conditions include low-sample rows",
        -1,
    )
    score += add_reason(reasons, avg_pf_improvement is not None and avg_pf_improvement <= 0, "average profit_factor improvement pct <= 0", -2)
    score += add_reason(reasons, avg_dd_improvement is not None and avg_dd_improvement <= 0, "average max_drawdown improvement <= 0", -1)
    score += add_reason(reasons, avg_dd_improvement is not None and avg_dd_improvement < 0, "average max_drawdown improvement < 0", -2)
    for risk in concentration_penalties(concentration_row):
        score += add_reason(reasons, True, risk, -1)

    return {
        "rank": 0,
        "direction": str(rows[0].get("direction", "long")),
        "cost_mode": str(rows[0].get("cost_mode", "none")),
        "return_mode": str(rows[0].get("return_mode", "gross")),
        "combination_key": combination_key,
        "symbols_tested": len(symbols_tested),
        "positive_symbols": len(positive_symbols),
        "tests_tested": len(tests_tested),
        "positive_tests": len(positive_tests),
        "avg_score": avg_score,
        "avg_profit_factor_improvement_pct": avg_pf_improvement,
        "avg_max_drawdown_improvement_pct": avg_dd_improvement,
        **concentration_row,
        "avg_win_rate_delta": avg_win_delta,
        "avg_mean_return_delta": avg_mean_delta,
        "avg_trades_count": avg_trades_count,
        "selection_score": score,
        "classification": classify(score),
        "rationale": "; ".join(reasons) if reasons else "no scoring conditions triggered",
    }


def aggregate_rows(evaluated: list[dict[str, object]], min_trades: int, min_symbols: int) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in evaluated:
        grouped[str(row["combination_key"])].append(row)

    aggregated = [
        aggregate_combination(combination_key, group_rows, min_trades, min_symbols)
        for combination_key, group_rows in grouped.items()
    ]
    aggregated.sort(
        key=lambda row: (
            DECISION_ORDER[str(row["classification"])],
            -int(row["selection_score"]),
            -float(row["avg_score"] or 0),
            -float(row["avg_profit_factor_improvement_pct"] or 0),
            str(row["combination_key"]),
        )
    )
    for index, row in enumerate(aggregated, start=1):
        row["rank"] = index
    return aggregated


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe_value(value) for key, value in row.items()})


def write_evaluated(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "run_id",
        "source_file",
        "symbol",
        "timeframe",
        "target_horizon",
        "direction",
        "cost_mode",
        "return_mode",
        "combination_key",
        "combination_size",
        "features",
        "buckets",
        "sample_flag",
        "trades_count",
        "profit_factor",
        "baseline_profit_factor",
        "profit_factor_delta",
        "profit_factor_improvement_pct",
        "max_drawdown",
        "baseline_max_drawdown",
        "max_drawdown_delta",
        "max_drawdown_improvement_pct",
        "monthly_positive_ratio",
        "quarterly_positive_ratio",
        "best_month_contribution_pct",
        "top_5_percent_trades_contribution_pct",
        "max_flat_period_bars",
        "win_rate",
        "baseline_win_rate",
        "win_rate_delta",
        "mean_return",
        "baseline_mean_return",
        "mean_return_delta",
        "median_return",
        "cumulative_return",
        "avg_positive_return",
        "avg_negative_return",
        "payoff_ratio",
        "breakeven_winrate",
        "breakeven_winrate_margin",
        "avg_estimated_cost_return",
        "gross_profit_factor",
        "net_profit_factor",
        "gross_max_drawdown",
        "net_max_drawdown",
        "gross_cumulative_return",
        "net_cumulative_return",
        "positive_result",
        "row_score",
        "row_classification",
        "row_rationale",
    ]
    write_csv(path, rows, fieldnames)


def write_selected(path: Path, rows: list[dict[str, object]], top_n: int) -> None:
    fieldnames = [
        "run_id",
        "rank",
        "direction",
        "cost_mode",
        "return_mode",
        "combination_key",
        "symbols_tested",
        "positive_symbols",
        "avg_score",
        "avg_profit_factor_improvement_pct",
        "avg_max_drawdown_improvement_pct",
        "monthly_positive_ratio",
        "quarterly_positive_ratio",
        "best_month_contribution_pct",
        "top_5_percent_trades_contribution_pct",
        "max_flat_period_bars",
        "avg_win_rate_delta",
        "avg_trades_count",
        "selection_score",
        "classification",
        "rationale",
    ]
    write_csv(path, rows[:top_n], fieldnames)


def markdown_section(title: str, rows: list[dict[str, object]], limit: int) -> list[str]:
    lines = [f"## {title}", ""]
    if not rows:
        lines.extend(["- none", ""])
        return lines
    for row in rows[:limit]:
        lines.append(f"### {row['rank']}. {row['combination_key']}")
        lines.append("")
        lines.append(f"- Classification: {row['classification']}")
        lines.append(f"- Selection score: {row['selection_score']}")
        lines.append(f"- Symbols tested: {row['symbols_tested']}")
        lines.append(f"- Positive symbols: {row['positive_symbols']}")
        lines.append(f"- Avg score: {row['avg_score']}")
        lines.append(f"- Avg profit factor improvement pct: {row['avg_profit_factor_improvement_pct']}")
        lines.append(f"- Avg max drawdown improvement pct: {row['avg_max_drawdown_improvement_pct']}")
        lines.append(f"- Monthly positive ratio: {row.get('monthly_positive_ratio')}")
        lines.append(f"- Best month contribution pct: {row.get('best_month_contribution_pct')}")
        lines.append(f"- Top 5 percent trades contribution pct: {row.get('top_5_percent_trades_contribution_pct')}")
        lines.append(f"- Avg trades count: {row['avg_trades_count']}")
        lines.append(f"- Rationale: {row['rationale']}")
        lines.append("")
    return lines


def write_report(
    path: Path,
    rows: list[dict[str, object]],
    top_n: int,
    run_id: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
) -> None:
    strong = [row for row in rows if row["classification"] == "strong"]
    interesting_watchlist = [
        row for row in rows
        if row["classification"] in {"interesting", "watchlist"}
    ]
    rejected = [row for row in rows if row["classification"] == "reject"]

    lines = [
        "# Combined Hypotheses Decision Report",
        "",
        f"Run ID: {run_id}",
        f"Direction: {direction}",
        f"Cost mode: {cost_mode}",
        f"Return mode: {return_mode}",
        f"Ranking basis: {'estimated net returns' if return_mode == 'net' else 'gross returns'}",
        "",
        "These results are research-only rankings of combined filters, not operational trading signals.",
        "",
    ]
    lines.extend(markdown_section("Top Strong Combinations", strong, top_n))
    lines.extend(markdown_section("Interesting And Watchlist Combinations", interesting_watchlist, top_n))
    lines.extend(markdown_section("Rejected Combinations And Main Reasons", rejected, top_n))
    lines.extend(
        [
            "## Caution",
            "",
            "- These combinations are exploratory research outputs only.",
            "- `cumulative_return` is compounded: product(1 + returns) - 1.",
            "- They do not create live signals, do not optimize parameters, and do not call MetaTrader5 or order execution APIs.",
            "- Any strong or interesting result still needs separate validation before any future research step.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    run_id = args.run_id.strip() if args.run_id else datetime.now().strftime("%Y%m%d_%H%M%S")
    if not run_id:
        raise ValueError("--run-id cannot be empty.")
    direction = normalize_direction(args.direction)
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)

    input_dir = args.input_dir
    if input_dir == DEFAULT_INPUT_DIR:
        input_dir = DEFAULT_INPUT_DIR / "runs" / run_id / direction
    paths = find_summary_files(input_dir)
    if not paths:
        raise FileNotFoundError(f"No {INPUT_FILE_NAME} files found under {input_dir}")

    rows = read_all_rows(paths)
    rows = [row for row in rows if normalize_direction(row.get("direction", "long")) == direction]
    rows = [
        row for row in rows
        if str(row.get("cost_mode", "none")) == cost_mode
        and str(row.get("return_mode", "gross")) == return_mode
    ]
    if not rows:
        raise ValueError(f"No {direction} {cost_mode}/{return_mode} combined hypothesis rows found.")

    evaluated = evaluate_rows(rows, args.min_trades)
    aggregated = aggregate_rows(evaluated, args.min_trades, args.min_symbols)
    for row in evaluated:
        row["run_id"] = run_id
    for row in aggregated:
        row["run_id"] = run_id

    output_dir = Path(args.output_dir) / run_id / direction
    evaluated_path = output_dir / OUTPUT_EVALUATED
    selected_path = output_dir / OUTPUT_SELECTED
    report_path = output_dir / OUTPUT_REPORT

    write_evaluated(evaluated_path, evaluated)
    write_selected(selected_path, aggregated, args.top_n)
    write_report(report_path, aggregated, args.top_n, run_id, direction, cost_mode, return_mode)

    print(f"Run ID: {run_id}")
    print(f"Output directory: {output_dir}")
    print(f"Cost mode: {cost_mode}")
    print(f"Return mode: {return_mode}")
    print("Files created:")
    print(f"- {evaluated_path}")
    print(f"- {selected_path}")
    print(f"- {report_path}")
    print(f"Combined summary files read: {len(paths)}")
    print(f"Rows evaluated: {len(evaluated)}")
    print(f"Combinations aggregated: {len(aggregated)}")
    print("Top combined hypotheses:")
    for row in aggregated[: args.top_n]:
        print(
            "- {combination_key}: class={classification}, score={selection_score}, "
            "symbols={symbols_tested}, positive={positive_symbols}".format(**row)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate combined hypothesis reports and select robust research candidates."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help=f"Default: {DEFAULT_INPUT_DIR}")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help=f"Default: {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--run-id", help="Default: current local timestamp in YYYYMMDD_HHMMSS format")
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--min-trades", type=int, default=300)
    parser.add_argument("--min-symbols", type=int, default=2)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    return parser.parse_args()


def main() -> int:
    try:
        run(parse_args())
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Combined hypotheses evaluation failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
