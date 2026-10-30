import argparse
import csv
from pathlib import Path

try:
    from research_metrics import csv_safe_value, normalize_direction
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.select_research_hypotheses
    from scripts.research_metrics import csv_safe_value, normalize_direction


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = BASE_DIR / "reports" / "backtests"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "backtests"
CROSS_PAIR_FILE = "cross_pair_summary.csv"
EVALUATED_FILE = "evaluated_backtest_results.csv"
OUTPUT_CSV = "selected_research_hypotheses.csv"
OUTPUT_MD = "selected_research_hypotheses.md"

DECISION_ORDER = {
    "select": 0,
    "watchlist": 1,
    "weak": 2,
    "reject": 3,
}


def to_float(value: str | None) -> float:
    if value is None:
        return 0.0
    value = value.strip()
    if value == "":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def to_int(value: str | None) -> int:
    return int(to_float(value))


def drawdown_improvement_value(row: dict[str, str]) -> float:
    if "avg_max_drawdown_improvement_pct" in row:
        return to_float(row.get("avg_max_drawdown_improvement_pct"))

    # Deprecated compatibility: older reports used avg_max_drawdown_pct_change
    # with the opposite sign and ratio units. Convert to improvement percentage.
    deprecated = row.get("avg_max_drawdown_pct_change")
    if deprecated not in (None, ""):
        return -to_float(deprecated) * 100

    return 0.0


def profit_factor_improvement_value(row: dict[str, str]) -> float:
    if "avg_profit_factor_improvement_pct" in row:
        return to_float(row.get("avg_profit_factor_improvement_pct"))

    # Deprecated compatibility: older reports used avg_profit_factor_pct_change
    # with ratio units, where 0.05 meant 5%.
    deprecated = row.get("avg_profit_factor_pct_change")
    if deprecated not in (None, ""):
        return to_float(deprecated) * 100

    return 0.0


def row_profit_factor_improvement_value(row: dict[str, str]) -> str:
    value = row.get("profit_factor_improvement_pct")
    if value not in (None, ""):
        return value

    # Deprecated compatibility: older evaluated reports used ratio units.
    deprecated = row.get("profit_factor_pct_change")
    if deprecated not in (None, ""):
        return str(to_float(deprecated) * 100)

    return ""


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def decision(score: int, min_score_to_select: int) -> str:
    if score >= min_score_to_select:
        return "select"
    if 4 <= score <= 6:
        return "watchlist"
    if 1 <= score <= 3:
        return "weak"
    return "reject"


def add_reason(reasons: list[str], condition: bool, text: str, score_delta: int) -> int:
    if condition:
        reasons.append(text)
        return score_delta
    return 0


def score_hypothesis(row: dict[str, str], min_symbols: int) -> tuple[int, str]:
    robustness_label = row.get("robustness_label", "").strip()
    strong_count = to_int(row.get("strong_count"))
    interesting_count = to_int(row.get("interesting_count"))
    strong_interesting = strong_count + interesting_count
    avg_score = to_float(row.get("avg_score"))
    avg_pf_improvement = profit_factor_improvement_value(row)
    avg_dd_improvement = drawdown_improvement_value(row)

    score = 0
    reasons: list[str] = []

    score += add_reason(reasons, robustness_label == "robust", "robust across tested pairs (+2)", 2)
    score += add_reason(reasons, robustness_label == "promising", "promising across tested pairs (+1)", 1)
    score += add_reason(reasons, strong_interesting >= 2, "at least two strong/interesting results (+1)", 1)
    score += add_reason(reasons, strong_interesting >= 3, "at least three strong/interesting results (+1)", 1)
    score += add_reason(reasons, avg_score >= 2, "average score >= 2 (+1)", 1)
    score += add_reason(reasons, avg_score >= 3, "average score >= 3 (+1)", 1)
    score += add_reason(reasons, avg_pf_improvement > 0, "average profit factor improvement pct > 0 (+1)", 1)
    score += add_reason(reasons, avg_pf_improvement >= 5, "average profit factor improvement pct >= 5 (+1)", 1)
    score += add_reason(reasons, avg_dd_improvement > 0, "average max drawdown improvement > 0 (+1)", 1)
    score += add_reason(reasons, avg_dd_improvement >= 10, "average max drawdown improvement >= 10% (+1)", 1)

    score += add_reason(reasons, robustness_label == "pair_specific", "pair-specific only (-2)", -2)
    score += add_reason(reasons, robustness_label == "weak", "weak cross-pair robustness (-3)", -3)
    score += add_reason(
        reasons,
        strong_interesting < min_symbols,
        f"strong/interesting count below min_symbols={min_symbols} (-2)",
        -2,
    )
    score += add_reason(
        reasons,
        avg_pf_improvement > 0 and avg_dd_improvement < 0,
        "profit factor improves while drawdown worsens (-2)",
        -2,
    )
    score += add_reason(reasons, avg_pf_improvement <= 0, "average profit factor improvement pct <= 0 (-1)", -1)
    score += add_reason(reasons, avg_dd_improvement <= 0, "average max drawdown improvement <= 0 (-1)", -1)

    return score, "; ".join(reasons) if reasons else "no scoring conditions triggered"


def build_hypotheses(
    cross_pair_rows: list[dict[str, str]],
    *,
    top_n: int,
    min_symbols: int,
    min_score_to_select: int,
    direction: str,
) -> list[dict[str, object]]:
    hypotheses = []
    for row in cross_pair_rows:
        selection_score, rationale = score_hypothesis(row, min_symbols)
        item_decision = decision(selection_score, min_score_to_select)
        hypotheses.append(
            {
                "rank": 0,
                "direction": direction,
                "scenario_key": row.get("scenario_key", ""),
                "robustness_label": row.get("robustness_label", ""),
                "strong_count": to_int(row.get("strong_count")),
                "interesting_count": to_int(row.get("interesting_count")),
                "weak_count": to_int(row.get("weak_count")),
                "ignore_count": to_int(row.get("ignore_count")),
                "symbols_tested": to_int(row.get("symbols_tested")),
                "avg_score": to_float(row.get("avg_score")),
                "avg_profit_factor_improvement_pct": profit_factor_improvement_value(row),
                "avg_max_drawdown_improvement_pct": drawdown_improvement_value(row),
                "selection_score": selection_score,
                "decision": item_decision,
                "rationale": rationale,
            }
        )

    hypotheses.sort(
        key=lambda row: (
            DECISION_ORDER[str(row["decision"])],
            -int(row["selection_score"]),
            -int(row["strong_count"]) - int(row["interesting_count"]),
            str(row["scenario_key"]),
        )
    )

    selected_seen = 0
    final_rows = []
    for row in hypotheses:
        if row["decision"] == "select":
            selected_seen += 1
            if selected_seen > top_n:
                row = {**row, "decision": "watchlist"}
        final_rows.append(row)

    final_rows.sort(
        key=lambda row: (
            DECISION_ORDER[str(row["decision"])],
            -int(row["selection_score"]),
            -int(row["strong_count"]) - int(row["interesting_count"]),
            str(row["scenario_key"]),
        )
    )
    for index, row in enumerate(final_rows, start=1):
        row["rank"] = index
    return final_rows


def write_hypotheses_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "direction",
        "scenario_key",
        "robustness_label",
        "strong_count",
        "interesting_count",
        "weak_count",
        "ignore_count",
        "symbols_tested",
        "avg_score",
        "avg_profit_factor_improvement_pct",
        "avg_max_drawdown_improvement_pct",
        "selection_score",
        "decision",
        "rationale",
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe_value(value) for key, value in row.items()})


def scenario_details(evaluated_rows: list[dict[str, str]], scenario_key: str) -> list[str]:
    rows = [row for row in evaluated_rows if row.get("scenario_key") == scenario_key]
    rows.sort(key=lambda row: (row.get("symbol", ""), row.get("timeframe", ""), row.get("target_horizon", "")))
    details = []
    for row in rows[:8]:
        drawdown_improvement = row.get("max_drawdown_improvement_pct")
        if drawdown_improvement in (None, "") and row.get("max_drawdown_pct_change") not in (None, ""):
            drawdown_improvement = str(-to_float(row.get("max_drawdown_pct_change")) * 100)
        details.append(
            f"{row.get('symbol', '')} {row.get('timeframe', '')} h{row.get('target_horizon', '')}: "
            f"class={row.get('classification', '')}, score={row.get('score', '')}, "
            f"pf_improvement_pct={row_profit_factor_improvement_value(row)}, "
            f"dd_improvement={drawdown_improvement}"
        )
    return details


def markdown_section(
    title: str,
    rows: list[dict[str, object]],
    evaluated_rows: list[dict[str, str]],
    limit: int | None = None,
) -> list[str]:
    lines = [f"## {title}", ""]
    selected_rows = rows if limit is None else rows[:limit]
    if not selected_rows:
        lines.extend(["- none", ""])
        return lines

    for row in selected_rows:
        lines.append(
            f"### {row['rank']}. {row['scenario_key']} "
            f"({row['decision']}, score={row['selection_score']})"
        )
        lines.append("")
        lines.append(f"- Robustness: {row['robustness_label']}")
        lines.append(f"- Strong/interesting: {row['strong_count']} / {row['interesting_count']}")
        lines.append(f"- Symbols tested: {row['symbols_tested']}")
        lines.append(f"- Avg score: {row['avg_score']}")
        lines.append(f"- Avg profit factor improvement pct: {row['avg_profit_factor_improvement_pct']}")
        lines.append(f"- Avg max drawdown improvement pct: {row['avg_max_drawdown_improvement_pct']}")
        lines.append(f"- Rationale: {row['rationale']}")
        details = scenario_details(evaluated_rows, str(row["scenario_key"]))
        if details:
            lines.append("- Per-pair details:")
            for detail in details:
                lines.append(f"  - {detail}")
        lines.append("")
    return lines


def write_hypotheses_markdown(
    path: Path,
    rows: list[dict[str, object]],
    evaluated_rows: list[dict[str, str]],
    top_n: int,
    direction: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    selected = [row for row in rows if row["decision"] == "select"]
    watchlist = [row for row in rows if row["decision"] == "watchlist"]
    rejected = [row for row in rows if row["decision"] == "reject"]

    lines = [
        "# Selected Research Hypotheses",
        "",
        f"Direction: {direction}",
        "",
        "These results are for research only. They are not operational trading signals.",
        "",
    ]
    lines.extend(markdown_section("Top Selected Hypotheses", selected, evaluated_rows, top_n))
    lines.extend(markdown_section("Watchlist Scenarios", watchlist, evaluated_rows, 20))
    lines.extend(markdown_section("Main Rejected Scenarios", rejected, evaluated_rows, 20))
    lines.extend(
        [
            "## Caution",
            "",
            "- These hypotheses come from exploratory backtest reports.",
            "- They must be validated on fresh data, additional symbols, and different time windows.",
            "- Do not convert these rows into live rules without separate validation and risk controls.",
            "- This script does not use MetaTrader5, does not call order execution APIs, and does not create operational signals.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def select_hypotheses(
    input_dir: Path,
    output_dir: Path,
    top_n: int,
    min_symbols: int,
    min_score_to_select: int,
    direction: str,
) -> None:
    if top_n <= 0:
        raise ValueError("--top-n must be greater than zero.")
    if min_symbols <= 0:
        raise ValueError("--min-symbols must be greater than zero.")

    cross_pair_path = input_dir / CROSS_PAIR_FILE
    evaluated_path = input_dir / EVALUATED_FILE
    cross_pair_rows = read_csv_dicts(cross_pair_path)
    evaluated_rows = read_csv_dicts(evaluated_path)
    direction = normalize_direction(direction)
    cross_pair_rows = [
        row for row in cross_pair_rows
        if normalize_direction(row.get("direction", "long")) == direction
    ]
    evaluated_rows = [
        row for row in evaluated_rows
        if normalize_direction(row.get("direction", "long")) == direction
    ]

    hypotheses = build_hypotheses(
        cross_pair_rows,
        top_n=top_n,
        min_symbols=min_symbols,
        min_score_to_select=min_score_to_select,
        direction=direction,
    )
    output_csv = output_dir / OUTPUT_CSV
    output_md = output_dir / OUTPUT_MD
    write_hypotheses_csv(output_csv, hypotheses)
    write_hypotheses_markdown(output_md, hypotheses, evaluated_rows, top_n, direction)

    print(f"Selected hypotheses CSV written: {output_csv}")
    print(f"Selected hypotheses Markdown written: {output_md}")
    print("Top decisions:")
    for row in hypotheses[:top_n]:
        print(
            "- {scenario_key}: decision={decision}, score={selection_score}, "
            "label={robustness_label}".format(**row)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select robust research hypotheses from evaluated backtest reports."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help=f"Default: {DEFAULT_INPUT_DIR}")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help=f"Default: {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--min-symbols", type=int, default=2)
    parser.add_argument("--min-score-to-select", type=int, default=7)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        select_hypotheses(
            args.input_dir if args.input_dir != DEFAULT_INPUT_DIR else DEFAULT_INPUT_DIR / args.direction,
            args.output_dir if args.output_dir != DEFAULT_OUTPUT_DIR else DEFAULT_OUTPUT_DIR / args.direction,
            args.top_n,
            args.min_symbols,
            args.min_score_to_select,
            args.direction,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Research hypothesis selection failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
