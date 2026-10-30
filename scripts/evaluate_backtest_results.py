import argparse
import csv
from collections import defaultdict
from pathlib import Path

from research_metrics import (
    calculate_max_drawdown_improvement_pct,
    calculate_profit_factor_improvement_pct,
    csv_safe_value,
    normalize_direction,
)
from research_costs import validate_cost_args


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = BASE_DIR / "reports" / "backtests"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "backtests"
INPUT_FILE_NAME = "backtest_research_summary.csv"
OUTPUT_EVALUATED = "evaluated_backtest_results.csv"
OUTPUT_CROSS_PAIR = "cross_pair_summary.csv"
OUTPUT_DECISION = "research_decision_summary.txt"

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
PATH_TOKEN_EXCLUSIONS = {
    "BACKTEST",
    "BACKTESTS",
    "REPORT",
    "REPORTS",
    "RESEARCH",
    "SUMMARY",
    "RESULT",
    "RESULTS",
}


def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def to_int(value: str | None) -> int:
    parsed = to_float(value)
    return int(parsed) if parsed is not None else 0


def profit_factor_improvement_pct(value: float | None, baseline: float | None) -> float | None:
    return calculate_profit_factor_improvement_pct(value, baseline)


def max_drawdown_improvement_pct(value: float | None, baseline: float | None) -> float | None:
    return calculate_max_drawdown_improvement_pct(value, baseline)


def infer_metadata(path: Path, row: dict[str, str]) -> tuple[str, str, str]:
    symbol = (row.get("symbol") or "").strip().upper()
    timeframe = (row.get("timeframe") or "").strip().upper()
    target_horizon = (row.get("target_horizon") or "").strip()
    if symbol and timeframe and target_horizon:
        return symbol, timeframe, target_horizon

    candidates = [path.parent.name, path.stem]
    for candidate in candidates:
        normalized = candidate.upper().replace("-", "_").replace(".", "_")
        parts = [part for part in normalized.split("_") if part]
        for part in parts:
            if part in TIMEFRAMES and not timeframe:
                timeframe = part
            elif part.startswith("H") and part[1:].isdigit() and not target_horizon:
                target_horizon = part[1:]
        for part in parts:
            if (
                part not in TIMEFRAMES
                and part not in PATH_TOKEN_EXCLUSIONS
                and not (part.startswith("H") and part[1:].isdigit())
                and not symbol
            ):
                symbol = part
        if symbol and timeframe and target_horizon:
            return symbol, timeframe, target_horizon

    return symbol or "UNKNOWN", timeframe or "UNKNOWN", target_horizon or "UNKNOWN"


def find_summary_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    if input_dir.is_file():
        return [input_dir] if input_dir.name == INPUT_FILE_NAME else []

    nested_files = sorted(
        path for path in input_dir.rglob(INPUT_FILE_NAME)
        if path.parent != input_dir
        and "combined" not in {part.lower() for part in path.parts}
        and "evaluations" not in {part.lower() for part in path.parts}
    )
    if nested_files:
        return nested_files

    root_file = input_dir / INPUT_FILE_NAME
    return [root_file] if root_file.exists() else []


def read_summary_file(path: Path) -> list[dict[str, object]]:
    rows = []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            symbol, timeframe, target_horizon = infer_metadata(path, row)
            scenario = (row.get("scenario_name") or row.get("scenario") or "").strip()
            if not scenario:
                continue
            rows.append(
                {
                    "source_file": str(path),
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "target_horizon": target_horizon,
                    "direction": (row.get("direction") or "long").strip().lower(),
                    "cost_mode": (row.get("cost_mode") or "none").strip().lower(),
                    "return_mode": (row.get("return_mode") or "gross").strip().lower(),
                    "scenario": scenario,
                    "scenario_key": scenario or f"{row.get('feature', '')}:{row.get('bucket', '')}",
                    "scenario_type": row.get("scenario_type", ""),
                    "feature": row.get("feature", ""),
                    "bucket": row.get("bucket", ""),
                    "sample_flag": row.get("sample_flag", ""),
                    "trades_count": to_int(row.get("trades_count")),
                    "profit_factor": to_float(row.get("profit_factor")),
                    "max_drawdown": to_float(row.get("max_drawdown")),
                    "win_rate": to_float(row.get("win_rate")),
                    "mean_return": to_float(row.get("mean_return")),
                    "median_return": to_float(row.get("median_return")),
                    "cumulative_return": to_float(row.get("cumulative_return")),
                    "avg_positive_return": to_float(row.get("avg_positive_return")),
                    "avg_negative_return": to_float(row.get("avg_negative_return")),
                    "payoff_ratio": to_float(row.get("payoff_ratio")),
                    "breakeven_winrate": to_float(row.get("breakeven_winrate")),
                    "breakeven_winrate_margin": to_float(row.get("breakeven_winrate_margin")),
                    "avg_estimated_cost_return": to_float(row.get("avg_estimated_cost_return")),
                    "gross_profit_factor": to_float(row.get("gross_profit_factor")),
                    "net_profit_factor": to_float(row.get("net_profit_factor")),
                    "gross_max_drawdown": to_float(row.get("gross_max_drawdown")),
                    "net_max_drawdown": to_float(row.get("net_max_drawdown")),
                    "gross_cumulative_return": to_float(row.get("gross_cumulative_return")),
                    "net_cumulative_return": to_float(row.get("net_cumulative_return")),
                }
            )
    return rows


def is_baseline(row: dict[str, object]) -> bool:
    scenario = str(row["scenario"])
    return (
        row.get("scenario_type") == "baseline"
        or scenario.startswith("baseline:")
        or (row.get("feature") == "all" and row.get("bucket") == "all")
    )


def classify(score: int) -> str:
    if score >= 4:
        return "strong"
    if score >= 2:
        return "interesting"
    if score == 1:
        return "weak"
    return "ignore"


def score_row(
    row: dict[str, object],
    baseline: dict[str, object],
    min_trades: int,
    good_trades: int,
) -> tuple[int, dict[str, float | None]]:
    profit_factor_delta = diff(row["profit_factor"], baseline["profit_factor"])
    profit_factor_improvement = profit_factor_improvement_pct(row["profit_factor"], baseline["profit_factor"])
    max_drawdown_delta = diff(row["max_drawdown"], baseline["max_drawdown"])
    drawdown_improvement = max_drawdown_improvement_pct(row["max_drawdown"], baseline["max_drawdown"])
    win_rate_delta = diff(row["win_rate"], baseline["win_rate"])
    mean_return_delta = diff(row["mean_return"], baseline["mean_return"])

    score = 0
    if int(row["trades_count"]) >= good_trades:
        score += 1
    if is_greater(row["profit_factor"], baseline["profit_factor"]):
        score += 1
    if profit_factor_improvement is not None and profit_factor_improvement >= 5:
        score += 1
    if drawdown_improvement is not None and drawdown_improvement > 0:
        score += 1
    if drawdown_improvement is not None and drawdown_improvement >= 10:
        score += 1
    if is_greater(row["win_rate"], baseline["win_rate"]):
        score += 1
    if is_greater(row["mean_return"], baseline["mean_return"]):
        score += 1
    if int(row["trades_count"]) < min_trades:
        score -= 2
    if drawdown_improvement is not None and drawdown_improvement <= 0:
        score -= 1
    if (
        profit_factor_improvement is not None
        and profit_factor_improvement > 0
        and drawdown_improvement is not None
        and drawdown_improvement < 0
    ):
        score -= 2

    deltas = {
        "profit_factor_delta": profit_factor_delta,
        "profit_factor_improvement_pct": profit_factor_improvement,
        "max_drawdown_delta": max_drawdown_delta,
        "max_drawdown_improvement_pct": drawdown_improvement,
        "win_rate_delta": win_rate_delta,
        "mean_return_delta": mean_return_delta,
    }
    return score, deltas


def diff(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def is_greater(value: float | None, baseline: float | None) -> bool:
    return value is not None and baseline is not None and value > baseline


def evaluate_rows(rows: list[dict[str, object]], min_trades: int, good_trades: int) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["symbol"]), str(row["timeframe"]), str(row["target_horizon"]))].append(row)

    evaluated = []
    for (_symbol, _timeframe, _target_horizon), group_rows in grouped.items():
        baseline_rows = [row for row in group_rows if is_baseline(row)]
        if not baseline_rows:
            raise ValueError(
                f"Baseline not found for {_symbol} {_timeframe} h{_target_horizon}."
            )
        baseline = baseline_rows[0]

        for row in group_rows:
            score, deltas = score_row(row, baseline, min_trades, good_trades)
            evaluated.append(
                {
                    **row,
                    "baseline_profit_factor": baseline["profit_factor"],
                    "baseline_max_drawdown": baseline["max_drawdown"],
                    "baseline_win_rate": baseline["win_rate"],
                    "baseline_mean_return": baseline["mean_return"],
                    **deltas,
                    "score": score,
                    "classification": classify(score),
                }
            )

    return sorted(
        evaluated,
        key=lambda row: (
            -int(row["score"]),
            str(row["scenario"]),
            str(row["symbol"]),
            str(row["timeframe"]),
        ),
    )


def robustness_label(strong_interesting_count: int) -> str:
    if strong_interesting_count >= 3:
        return "robust"
    if strong_interesting_count >= 2:
        return "promising"
    if strong_interesting_count == 1:
        return "pair_specific"
    return "weak"


def build_cross_pair_summary(evaluated: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in evaluated:
        grouped[str(row["scenario_key"])].append(row)

    summary = []
    for scenario_key, rows in grouped.items():
        labels = [str(row["classification"]) for row in rows]
        strong_count = labels.count("strong")
        interesting_count = labels.count("interesting")
        weak_count = labels.count("weak")
        ignore_count = labels.count("ignore")
        symbols = {f"{row['symbol']}:{row['timeframe']}:h{row['target_horizon']}" for row in rows}
        avg_score = sum(int(row["score"]) for row in rows) / len(rows)
        pf_changes = [
            float(row["profit_factor_improvement_pct"])
            for row in rows
            if row["profit_factor_improvement_pct"] is not None
        ]
        drawdown_improvements = [
            float(row["max_drawdown_improvement_pct"])
            for row in rows
            if row["max_drawdown_improvement_pct"] is not None
        ]
        strong_interesting = strong_count + interesting_count
        summary.append(
            {
                "direction": str(rows[0].get("direction", "long")),
                "cost_mode": str(rows[0].get("cost_mode", "none")),
                "return_mode": str(rows[0].get("return_mode", "gross")),
                "scenario_key": scenario_key,
                "symbols_tested": len(symbols),
                "strong_count": strong_count,
                "interesting_count": interesting_count,
                "weak_count": weak_count,
                "ignore_count": ignore_count,
                "avg_score": avg_score,
                "avg_profit_factor_improvement_pct": sum(pf_changes) / len(pf_changes) if pf_changes else None,
                "avg_max_drawdown_improvement_pct": (
                    sum(drawdown_improvements) / len(drawdown_improvements)
                    if drawdown_improvements
                    else None
                ),
                "robustness_label": robustness_label(strong_interesting),
            }
        )

    return sorted(
        summary,
        key=lambda row: (
            {"robust": 0, "promising": 1, "pair_specific": 2, "weak": 3}[str(row["robustness_label"])],
            -float(row["avg_score"]),
            str(row["scenario_key"]),
        ),
    )


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe_value(value) for key, value in row.items()})


def write_decision_summary(
    path: Path,
    evaluated: list[dict[str, object]],
    cross_pair: list[dict[str, object]],
    min_trades: int,
    direction: str,
    cost_mode: str,
    return_mode: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    robust = [row for row in cross_pair if row["robustness_label"] in {"robust", "promising"}]
    ignored = [row for row in evaluated if row["classification"] == "ignore"]
    low_sample = [row for row in evaluated if int(row["trades_count"]) < min_trades]

    lines = [
        "Backtest Research Decision Summary",
        "",
        f"Direction: {direction}",
        f"Cost mode: {cost_mode}",
        f"Return mode: {return_mode}",
        f"Ranking basis: {'estimated net returns' if return_mode == 'net' else 'gross returns'}",
        "",
        "Top robust or promising scenarios",
    ]
    if robust:
        for row in robust[:20]:
            lines.append(
                "- {scenario_key}: label={robustness_label}, symbols_tested={symbols_tested}, "
                "strong={strong_count}, interesting={interesting_count}, avg_score={avg_score}".format(**row)
            )
    else:
        lines.append("- none")

    lines.extend(["", "Scenarios to ignore"])
    if ignored:
        for row in ignored[:30]:
            lines.append(
                "- {scenario} ({symbol} {timeframe} h{target_horizon}): score={score}, "
                "trades={trades_count}, profit_factor={profit_factor}".format(**row)
            )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "Low sample caution",
            f"- Low sample threshold: trades_count < {min_trades}",
            f"- Low sample scenario rows: {len(low_sample)}",
            "- Treat low-sample scenarios as exploratory noise unless confirmed on larger samples.",
            "- These evaluations compare scenario buckets to their own baseline only.",
            "- `cumulative_return` is compounded: product(1 + returns) - 1.",
            "- This script does not create live signals, does not use MetaTrader5, and does not call order execution APIs.",
            "- Do not convert any scenario into an operational rule without separate validation.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def evaluate_backtests(
    input_dir: Path,
    output_dir: Path,
    min_trades: int,
    good_trades: int,
    direction: str,
    cost_mode: str,
    return_mode: str,
) -> None:
    cost_mode, return_mode = validate_cost_args(cost_mode, return_mode)
    if min_trades <= 0:
        raise ValueError("--min-trades must be greater than zero.")
    if good_trades <= 0:
        raise ValueError("--good-trades must be greater than zero.")
    direction = normalize_direction(direction)

    files = find_summary_files(input_dir)
    if not files:
        raise FileNotFoundError(f"No {INPUT_FILE_NAME} files found in {input_dir}.")

    rows = []
    for path in files:
        rows.extend(read_summary_file(path))
    rows = [row for row in rows if normalize_direction(row.get("direction", "long")) == direction]
    rows = [
        row for row in rows
        if str(row.get("cost_mode", "none")) == cost_mode
        and str(row.get("return_mode", "gross")) == return_mode
    ]
    if not rows:
        raise ValueError(f"No {direction} {cost_mode}/{return_mode} scenario rows found in backtest summary files.")

    evaluated = evaluate_rows(rows, min_trades, good_trades)
    cross_pair = build_cross_pair_summary(evaluated)

    evaluated_fields = [
        "source_file",
        "symbol",
        "timeframe",
        "target_horizon",
        "direction",
        "cost_mode",
        "return_mode",
        "scenario",
        "scenario_key",
        "scenario_type",
        "feature",
        "bucket",
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
        "score",
        "classification",
    ]
    cross_pair_fields = [
        "direction",
        "cost_mode",
        "return_mode",
        "scenario_key",
        "symbols_tested",
        "strong_count",
        "interesting_count",
        "weak_count",
        "ignore_count",
        "avg_score",
        "avg_profit_factor_improvement_pct",
        "avg_max_drawdown_improvement_pct",
        "robustness_label",
    ]

    evaluated_path = output_dir / "evaluated_backtest_results.csv"
    cross_pair_path = output_dir / "cross_pair_summary.csv"
    decision_path = output_dir / "research_decision_summary.txt"
    write_csv(evaluated_path, evaluated, evaluated_fields)
    write_csv(cross_pair_path, cross_pair, cross_pair_fields)
    write_decision_summary(decision_path, evaluated, cross_pair, min_trades, direction, cost_mode, return_mode)

    print(f"Evaluated rows: {len(evaluated)}")
    print(f"Files read: {len(files)}")
    print(f"Cost mode: {cost_mode}")
    print(f"Return mode: {return_mode}")
    print(f"Evaluated results written: {evaluated_path}")
    print(f"Cross-pair summary written: {cross_pair_path}")
    print(f"Decision summary written: {decision_path}")
    print("Top evaluated scenarios:")
    for row in evaluated[:20]:
        print(
            "- {scenario} ({symbol} {timeframe} h{target_horizon}): score={score}, "
            "class={classification}, trades={trades_count}, pf_delta={profit_factor_delta}".format(**row)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate exploratory backtest research summaries against their baselines."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help=f"Default: {DEFAULT_INPUT_DIR}")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help=f"Default: {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--min-trades", type=int, default=200)
    parser.add_argument("--good-trades", type=int, default=500)
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        input_dir = args.input_dir if args.input_dir != DEFAULT_INPUT_DIR else DEFAULT_INPUT_DIR / args.direction
        output_dir = args.output_dir if args.output_dir != DEFAULT_OUTPUT_DIR else DEFAULT_OUTPUT_DIR / args.direction
        evaluate_backtests(
            input_dir,
            output_dir,
            args.min_trades,
            args.good_trades,
            args.direction,
            args.cost_mode,
            args.return_mode,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Backtest evaluation failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
