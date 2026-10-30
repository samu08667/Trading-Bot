import argparse
import csv
from collections import defaultdict
from datetime import datetime
import math
from pathlib import Path
import sqlite3
from statistics import median

try:
    from condition_utils import (
        FUTURE_TARGET_SKIP_REASON,
        NUMERIC_TERCILE_SKIP_REASON,
        RAW_PRICE_SKIP_REASON,
        build_predicate,
        combination_contains_future_or_target_feature,
        combination_contains_numeric_tercile,
        combination_contains_raw_price_feature,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.validate_hypotheses_by_year
    from scripts.condition_utils import (
        FUTURE_TARGET_SKIP_REASON,
        NUMERIC_TERCILE_SKIP_REASON,
        RAW_PRICE_SKIP_REASON,
        build_predicate,
        combination_contains_future_or_target_feature,
        combination_contains_numeric_tercile,
        combination_contains_raw_price_feature,
    )

try:
    from research_metrics import (
        calculate_max_drawdown_improvement_pct,
        calculate_profit_factor_improvement_pct,
        calculate_return_metrics,
        csv_safe_value,
        directional_return,
        normalize_direction,
        safe_float,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.validate_hypotheses_by_year
    from scripts.research_metrics import (
        calculate_max_drawdown_improvement_pct,
        calculate_profit_factor_improvement_pct,
        calculate_return_metrics,
        csv_safe_value,
        directional_return,
        normalize_direction,
        safe_float,
    )

try:
    from research_costs import (
        cost_report_fields,
        cost_report_warnings,
        cost_adjusted_return_metrics,
        load_cost_config,
        validate_estimated_cost_config,
        validate_cost_args,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.validate_hypotheses_by_year
    from scripts.research_costs import (
        cost_report_fields,
        cost_report_warnings,
        cost_adjusted_return_metrics,
        load_cost_config,
        validate_estimated_cost_config,
        validate_cost_args,
    )

try:
    from time_split_utils import downsample_non_overlapping_rows
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.validate_hypotheses_by_year
    from scripts.time_split_utils import downsample_non_overlapping_rows


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_EVALUATIONS_DIR = BASE_DIR / "reports" / "backtests" / "combined" / "evaluations"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "validation" / "by_year"
TABLE_NAME = "ml_dataset"
SELECTED_COMBINED_FILE = "selected_combined_hypotheses.csv"

DETAIL_OUTPUT = "by_year_validation_detail.csv"
SUMMARY_OUTPUT = "by_year_validation_summary.csv"
CANDIDATES_OUTPUT = "final_research_candidates.csv"
REPORT_OUTPUT = "final_research_candidates_report.md"
SKIPPED_OUTPUT = "skipped_hypotheses.csv"
PAIR_SPECIFIC_OUTPUT = "pair_specific_candidates.csv"
PAIR_SPECIFIC_REPORT_OUTPUT = "pair_specific_candidates_report.md"

CATASTROPHIC_DRAWDOWN_WORSENING_PCT = -50.0
FULL_YEAR_START_TOLERANCE_DAY = 7
FULL_YEAR_END_TOLERANCE_DAY = 24
FINAL_CLASSIFICATION_ORDER = {
    "select": 0,
    "watchlist": 1,
    "reject": 2,
}


def to_float(value: object) -> float | None:
    return safe_float(value)


def to_int(value: object) -> int | None:
    parsed = to_float(value)
    return int(parsed) if parsed is not None else None


def is_finite(value: object) -> bool:
    parsed = to_float(value)
    return parsed is not None and math.isfinite(parsed)


def average(values: list[object]) -> float | None:
    usable = [float(to_float(value)) for value in values if is_finite(value)]
    return sum(usable) / len(usable) if usable else None


def median_value(values: list[object]) -> float | None:
    usable = [float(to_float(value)) for value in values if is_finite(value)]
    return median(usable) if usable else None


def minimum(values: list[object]) -> float | None:
    usable = [float(to_float(value)) for value in values if is_finite(value)]
    return min(usable) if usable else None


def maximum(values: list[object]) -> float | None:
    usable = [float(to_float(value)) for value in values if is_finite(value)]
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


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def normalize_symbols(values: list[str] | None) -> list[str]:
    symbols: list[str] = []
    for value in values or []:
        for token in value.split(","):
            symbol = token.strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols


def table_columns(connection: sqlite3.Connection) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})")}


def ensure_dataset(connection: sqlite3.Connection, return_column: str) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    ).fetchone()
    if exists is None:
        raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")

    columns = table_columns(connection)
    if return_column not in columns:
        raise ValueError(f"Column {return_column!r} not found in {TABLE_NAME}.")


def load_symbol_rows(db_path: Path, symbol: str, timeframe: str, return_column: str) -> list[dict[str, object]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        ensure_dataset(connection, return_column)
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


def detect_available_symbols(db_path: Path, timeframe: str, return_column: str) -> list[str]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        ensure_dataset(connection, return_column)
        rows = connection.execute(
            f"""
            SELECT DISTINCT symbol
            FROM {TABLE_NAME}
            WHERE timeframe = ?
              AND {return_column} IS NOT NULL
            ORDER BY symbol ASC
            """,
            (timeframe,),
        ).fetchall()
    return [str(row["symbol"]).upper() for row in rows]


def detect_available_years(
    db_path: Path,
    symbols: list[str],
    timeframe: str,
    return_column: str,
) -> list[int]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    if not symbols:
        return []

    placeholders = ",".join("?" for _ in symbols)
    params = [*symbols, timeframe]
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        ensure_dataset(connection, return_column)
        rows = connection.execute(
            f"""
            SELECT DISTINCT CAST(substr(time_server, 1, 4) AS INTEGER) AS year
            FROM {TABLE_NAME}
            WHERE symbol IN ({placeholders})
              AND timeframe = ?
              AND {return_column} IS NOT NULL
              AND time_server IS NOT NULL
            ORDER BY year ASC
            """,
            params,
        ).fetchall()
    return [int(row["year"]) for row in rows if row["year"] is not None]


def resolve_years(args: argparse.Namespace, available_years: list[int]) -> list[int]:
    if args.years:
        return sorted({int(year) for year in args.years})
    if not available_years:
        return []
    if args.start_year is None and args.end_year is None:
        return available_years

    start_year = args.start_year if args.start_year is not None else min(available_years)
    end_year = args.end_year if args.end_year is not None else max(available_years)
    if start_year > end_year:
        raise ValueError("--start-year cannot be greater than --end-year.")
    return list(range(start_year, end_year + 1))


def parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_year(value: object) -> int | None:
    parsed = parse_datetime(value)
    if parsed is not None:
        return parsed.year
    text = str(value or "").strip()
    prefix = text[:4]
    return int(prefix) if prefix.isdigit() else None


def is_partial_year(rows: list[dict[str, object]], year: int) -> bool:
    if not rows:
        return True
    if year >= datetime.now().year:
        return True

    dates = [parse_datetime(row.get("time_server")) for row in rows]
    usable = [item for item in dates if item is not None]
    if not usable:
        return True

    min_date = min(usable).date()
    max_date = max(usable).date()
    latest_acceptable_start = datetime(year, 1, FULL_YEAR_START_TOLERANCE_DAY).date()
    earliest_acceptable_end = datetime(year, 12, FULL_YEAR_END_TOLERANCE_DAY).date()
    return min_date > latest_acceptable_start or max_date < earliest_acceptable_end


def returns_from_rows(rows: list[dict[str, object]], return_column: str, direction: str) -> list[float]:
    values = []
    for row in rows:
        value = directional_return(row.get(return_column), direction)
        if value is not None and math.isfinite(value):
            values.append(value)
    return values


def cumulative_return(returns: list[float]) -> float | None:
    return calculate_return_metrics(returns)["cumulative_return"]


def max_drawdown(returns: list[float]) -> float | None:
    return calculate_return_metrics(returns)["max_drawdown"]


def profit_factor(returns: list[float]) -> float | None:
    return calculate_return_metrics(returns)["profit_factor"]


def metrics(
    rows: list[dict[str, object]],
    return_column: str,
    direction: str,
    symbol: str,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
) -> dict[str, object]:
    return cost_adjusted_return_metrics(
        rows,
        symbol=symbol,
        return_column=return_column,
        direction=direction,
        cost_config=cost_config,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )


def profit_factor_improvement_pct(value: float | None, baseline: float | None) -> float | None:
    return calculate_profit_factor_improvement_pct(value, baseline)


def max_drawdown_improvement_pct(value: float | None, baseline: float | None) -> float | None:
    return calculate_max_drawdown_improvement_pct(value, baseline)


def is_positive_year(row: dict[str, object]) -> bool:
    pf_improvement = to_float(row.get("profit_factor_improvement_pct"))
    dd_improvement = to_float(row.get("max_drawdown_improvement_pct"))
    return (
        int(row.get("scenario_trades_count") or 0) > 0
        and pf_improvement is not None
        and pf_improvement > 0
        and dd_improvement is not None
        and dd_improvement >= 0
    )


def latest_selected_combined_file(evaluations_dir: Path, direction: str) -> Path | None:
    if not evaluations_dir.exists():
        return None
    candidates = sorted(
        path for path in evaluations_dir.glob(f"*/{direction}/{SELECTED_COMBINED_FILE}") if path.is_file()
    )
    return candidates[-1] if candidates else None


def default_hypotheses_file(evaluations_dir: Path, run_id: str | None, direction: str) -> Path:
    if run_id:
        directed = evaluations_dir / run_id / direction / SELECTED_COMBINED_FILE
        if directed.exists() or direction != "long":
            return directed
        return evaluations_dir / run_id / SELECTED_COMBINED_FILE
    latest = latest_selected_combined_file(evaluations_dir, direction)
    if latest is None:
        raise FileNotFoundError(
            f"No {SELECTED_COMBINED_FILE} found under {evaluations_dir}. "
            "Pass --hypotheses-file or --run-id."
        )
    return latest


def infer_run_id(args: argparse.Namespace, hypotheses_file: Path | None) -> str:
    if args.run_id:
        run_id = args.run_id.strip()
        if not run_id:
            raise ValueError("--run-id cannot be empty.")
        return run_id
    if hypotheses_file is not None and hypotheses_file.name == SELECTED_COMBINED_FILE:
        parent_name = hypotheses_file.parent.name.strip()
        if parent_name in {"long", "short"}:
            run_id = hypotheses_file.parent.parent.name.strip()
        else:
            run_id = parent_name
        if run_id:
            return run_id
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def resolve_output_dir(base_output_dir: Path, run_id: str, direction: str, overwrite: bool) -> Path:
    output_dir = Path(base_output_dir) / run_id / direction
    protected_outputs = [
        DETAIL_OUTPUT,
        SUMMARY_OUTPUT,
        CANDIDATES_OUTPUT,
        REPORT_OUTPUT,
        SKIPPED_OUTPUT,
        PAIR_SPECIFIC_OUTPUT,
        PAIR_SPECIFIC_REPORT_OUTPUT,
    ]
    existing = [output_dir / name for name in protected_outputs if (output_dir / name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Validation output already exists for run {run_id!r}: {output_dir}. "
            "Pass --overwrite or choose a different --run-id/--output-dir."
        )
    return output_dir


def read_hypotheses_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Hypotheses file not found: {path}")

    if path.suffix.lower() != ".csv":
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    hypotheses = []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            decision = (row.get("decision") or "").strip().lower()
            classification = (row.get("classification") or "").strip().lower()
            if decision in {"reject", "weak"} or classification in {"reject", "weak"}:
                continue

            value = row.get("combination_key") or row.get("scenario_key") or row.get("hypothesis")
            if value:
                hypotheses.append(value.strip())
    return hypotheses


def collect_combinations(args: argparse.Namespace) -> tuple[list[str], Path | None]:
    combinations = [item.strip() for item in args.hypothesis or [] if item.strip()]
    source_path = args.hypotheses_file
    if source_path is None and not combinations:
        source_path = default_hypotheses_file(args.evaluations_dir, args.run_id, args.direction)
    if source_path is not None:
        combinations.extend(read_hypotheses_file(source_path))

    seen = set()
    unique = []
    for combination_key in combinations:
        if combination_key not in seen:
            seen.add(combination_key)
            unique.append(combination_key)
    return unique, source_path


def skip_record(combination_key: str, skip_reason: str, source_path: Path | None) -> dict[str, object]:
    return {
        "combination_key": combination_key,
        "skip_reason": skip_reason,
        "source_file": str(source_path) if source_path is not None else "manual_cli_hypothesis",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def skipped_fieldnames() -> list[str]:
    return ["combination_key", "skip_reason", "source_file", "timestamp"]


def dedupe_skipped(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    deduped = []
    for row in rows:
        key = (str(row["combination_key"]), str(row["skip_reason"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def filter_pre_skipped_combinations(
    combinations: list[str],
    source_path: Path | None,
) -> tuple[list[str], list[dict[str, object]]]:
    """Remove final-validation exclusions before any symbol-year work."""
    valid = []
    skipped = []
    for combination_key in combinations:
        if combination_contains_future_or_target_feature(combination_key):
            skipped.append(skip_record(combination_key, FUTURE_TARGET_SKIP_REASON, source_path))
            print(f"Warning: skipping {combination_key!r}: {FUTURE_TARGET_SKIP_REASON}")
            continue
        if combination_contains_numeric_tercile(combination_key):
            skipped.append(skip_record(combination_key, NUMERIC_TERCILE_SKIP_REASON, source_path))
            print(f"Warning: skipping {combination_key!r}: {NUMERIC_TERCILE_SKIP_REASON}")
            continue
        if combination_contains_raw_price_feature(combination_key):
            skipped.append(skip_record(combination_key, RAW_PRICE_SKIP_REASON, source_path))
            print(f"Warning: skipping {combination_key!r}: {RAW_PRICE_SKIP_REASON}")
            continue
        valid.append(combination_key)
    return valid, skipped


def rows_by_year(rows: list[dict[str, object]], years: list[int]) -> dict[int, list[dict[str, object]]]:
    wanted = set(years)
    grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        year = parse_year(row.get("time_server"))
        if year in wanted:
            grouped[int(year)].append(row)
    return grouped


def validate_symbol_years(
    *,
    symbol: str,
    timeframe: str,
    target_horizon: int,
    rows: list[dict[str, object]],
    years: list[int],
    combinations: list[str],
    return_column: str,
    direction: str,
    min_trades_per_year: int,
    source_path: Path | None,
    non_overlap_eval: bool,
    cost_config: dict[str, object],
    cost_mode: str,
    return_mode: str,
    cost_fields: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    grouped_rows = rows_by_year(rows, years)
    detail_rows = []
    skipped = []
    predicates = {}
    for combination in combinations:
        try:
            predicates[combination] = build_predicate(rows, combination)
        except ValueError as exc:
            reason = f"unsupported_condition: {exc}"
            skipped.append(skip_record(combination, reason, source_path))
            print(f"Warning: skipping {combination!r} for {symbol}: {reason}")

    for combination_key, predicate in predicates.items():
        for year in years:
            year_rows = grouped_rows.get(year, [])
            baseline_rows = (
                downsample_non_overlapping_rows(year_rows, timeframe, target_horizon)
                if non_overlap_eval
                else year_rows
            )
            scenario_rows = [row for row in baseline_rows if predicate(row)]
            baseline = metrics(baseline_rows, return_column, direction, symbol, cost_config, cost_mode, return_mode)
            scenario = metrics(scenario_rows, return_column, direction, symbol, cost_config, cost_mode, return_mode)
            pf_improvement = profit_factor_improvement_pct(
                to_float(scenario["profit_factor"]),
                to_float(baseline["profit_factor"]),
            )
            dd_improvement = max_drawdown_improvement_pct(
                to_float(scenario["max_drawdown"]),
                to_float(baseline["max_drawdown"]),
            )
            row = {
                "combination_key": combination_key,
                "symbol": symbol,
                "timeframe": timeframe,
                "target_horizon": target_horizon,
                "direction": direction,
                "cost_mode": cost_mode,
                "return_mode": return_mode,
                **cost_fields,
                "year": year,
                "partial_year": bool_text(is_partial_year(year_rows, year)),
                "non_overlap_eval": bool_text(non_overlap_eval),
                "rows_before_non_overlap": len(year_rows),
                "rows_after_non_overlap": len(baseline_rows),
                "baseline_trades_count": baseline["trades_count"],
                "scenario_trades_count": scenario["trades_count"],
                "mean_return": scenario["mean_return"],
                "median_return": scenario["median_return"],
                "win_rate": scenario["win_rate"],
                "cumulative_return": scenario["cumulative_return"],
                "max_drawdown": scenario["max_drawdown"],
                "profit_factor": scenario["profit_factor"],
                "avg_positive_return": scenario.get("avg_positive_return"),
                "avg_negative_return": scenario.get("avg_negative_return"),
                "payoff_ratio": scenario.get("payoff_ratio"),
                "breakeven_winrate": scenario.get("breakeven_winrate"),
                "breakeven_winrate_margin": scenario.get("breakeven_winrate_margin"),
                "monthly_positive_ratio": scenario.get("monthly_positive_ratio"),
                "quarterly_positive_ratio": scenario.get("quarterly_positive_ratio"),
                "best_month_contribution_pct": scenario.get("best_month_contribution_pct"),
                "top_5_percent_trades_contribution_pct": scenario.get("top_5_percent_trades_contribution_pct"),
                "max_flat_period_bars": scenario.get("max_flat_period_bars"),
                "avg_estimated_cost_return": scenario.get("avg_estimated_cost_return"),
                "gross_profit_factor": scenario.get("gross_profit_factor"),
                "net_profit_factor": scenario.get("net_profit_factor"),
                "gross_max_drawdown": scenario.get("gross_max_drawdown"),
                "net_max_drawdown": scenario.get("net_max_drawdown"),
                "gross_cumulative_return": scenario.get("gross_cumulative_return"),
                "net_cumulative_return": scenario.get("net_cumulative_return"),
                "profit_factor_improvement_pct": pf_improvement,
                "max_drawdown_improvement_pct": dd_improvement,
            }
            row["is_positive_year"] = bool_text(is_positive_year(row))
            row["is_low_sample_year"] = bool_text(int(row["scenario_trades_count"]) < min_trades_per_year)
            row["is_profit_factor_worse_year"] = bool_text(pf_improvement is not None and pf_improvement < 0)
            row["is_drawdown_worse_year"] = bool_text(dd_improvement is not None and dd_improvement < 0)
            detail_rows.append(row)

    return detail_rows, skipped


def classification_for_summary(
    row: dict[str, object],
    *,
    min_positive_year_ratio: float,
    min_positive_symbol_ratio: float,
    min_trades_per_year: int,
) -> tuple[str, str]:
    years_tested = int(row["years_tested"])
    if years_tested == 0:
        return "reject", "no complete symbol-year observations available for classification"

    positive_year_ratio = float(row["positive_year_ratio"])
    positive_symbol_ratio = float(row["positive_symbol_ratio"])
    avg_dd = to_float(row["avg_max_drawdown_improvement_pct"])
    worst_dd = to_float(row["worst_year_drawdown_improvement_pct"])
    min_trades = int(row["min_trades_in_any_year"])
    pf_worse_years = int(row["profit_factor_worse_years"])
    dd_worse_years = int(row["drawdown_worse_years"])
    calendar_years_tested = int(row["calendar_years_tested"])
    positive_calendar_years = int(row["positive_calendar_years"])
    positive_calendar_year_ratio = (
        positive_calendar_years / calendar_years_tested if calendar_years_tested else 0.0
    )
    concentration_risks = concentration_penalties(row)

    if dd_worse_years > years_tested / 2:
        return "reject", "drawdown worsens in the majority of tested symbol-years"
    if pf_worse_years > years_tested / 2:
        return "reject", "profit factor worsens in the majority of tested symbol-years"
    if positive_year_ratio < 0.50:
        return "reject", "positive_year_ratio is low"
    if positive_calendar_year_ratio < 0.50:
        return "reject", "performance is concentrated in too few calendar years"

    select_conditions = [
        positive_year_ratio >= min_positive_year_ratio,
        positive_symbol_ratio >= min_positive_symbol_ratio,
        avg_dd is not None and avg_dd >= 0,
        min_trades >= min_trades_per_year,
        worst_dd is not None and worst_dd >= CATASTROPHIC_DRAWDOWN_WORSENING_PCT,
    ]
    if all(select_conditions):
        return "select", "stable across years and symbols with sufficient sample and controlled drawdown"

    reasons = []
    if positive_year_ratio < min_positive_year_ratio:
        reasons.append("year stability below select threshold")
    if positive_symbol_ratio < min_positive_symbol_ratio:
        reasons.append("cross-symbol stability below select threshold")
    if avg_dd is None or avg_dd < 0:
        reasons.append("average drawdown improvement below zero")
    if min_trades < min_trades_per_year:
        reasons.append("low sample in at least one tested symbol-year")
    if worst_dd is None or worst_dd < CATASTROPHIC_DRAWDOWN_WORSENING_PCT:
        reasons.append("worst-year drawdown deterioration is too large")
    for risk in concentration_risks:
        reasons.append(f"concentration penalty: {risk}")
    return "watchlist", "; ".join(reasons) if reasons else "interesting but not stable enough for select"


def aggregate_detail_rows(
    detail_rows: list[dict[str, object]],
    *,
    include_incomplete_years: bool,
    min_positive_year_ratio: float,
    min_positive_symbol_ratio: float,
    min_trades_per_year: int,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in detail_rows:
        grouped[str(row["combination_key"])].append(row)

    summaries = []
    for combination_key, rows in grouped.items():
        eligible = [
            row for row in rows
            if int(row["baseline_trades_count"]) > 0
            and (include_incomplete_years or not as_bool(row["partial_year"]))
        ]
        symbols_tested = sorted({str(row["symbol"]) for row in eligible})
        calendar_years_tested = sorted({int(row["year"]) for row in eligible})
        positive_years = sum(1 for row in eligible if as_bool(row["is_positive_year"]))
        years_tested = len(eligible)
        positive_year_ratio = positive_years / years_tested if years_tested else 0.0

        positive_symbols = 0
        for symbol in symbols_tested:
            symbol_rows = [row for row in eligible if row["symbol"] == symbol]
            if not symbol_rows:
                continue
            symbol_positive_ratio = sum(1 for row in symbol_rows if as_bool(row["is_positive_year"])) / len(symbol_rows)
            symbol_avg_dd = average([row["max_drawdown_improvement_pct"] for row in symbol_rows])
            if symbol_positive_ratio >= min_positive_year_ratio and symbol_avg_dd is not None and symbol_avg_dd >= 0:
                positive_symbols += 1

        positive_symbol_ratio = positive_symbols / len(symbols_tested) if symbols_tested else 0.0
        positive_calendar_years = len(
            {
                int(row["year"])
                for row in eligible
                if as_bool(row["is_positive_year"])
            }
        )
        scenario_trades = [int(row["scenario_trades_count"]) for row in eligible]
        pf_improvements = [row["profit_factor_improvement_pct"] for row in eligible]
        dd_improvements = [row["max_drawdown_improvement_pct"] for row in eligible]

        summary = {
            "combination_key": combination_key,
            "direction": str(rows[0].get("direction", "long")),
            "cost_mode": str(rows[0].get("cost_mode", "none")),
            "return_mode": str(rows[0].get("return_mode", "gross")),
            "cost_config_source": str(rows[0].get("cost_config_source", "not_applicable")),
            "point_size_source": "",
            "spread_source_used": "",
            "symbols_using_default_costs": "",
            "symbols_tested": len(symbols_tested),
            "positive_symbols": positive_symbols,
            "positive_symbol_ratio": positive_symbol_ratio,
            "years_tested": years_tested,
            "positive_years": positive_years,
            "positive_year_ratio": positive_year_ratio,
            "calendar_years_tested": len(calendar_years_tested),
            "positive_calendar_years": positive_calendar_years,
            "avg_trades_per_year": average(scenario_trades),
            "min_trades_in_any_year": min(scenario_trades) if scenario_trades else 0,
            "avg_profit_factor_improvement_pct": average(pf_improvements),
            "median_profit_factor_improvement_pct": median_value(pf_improvements),
            "avg_max_drawdown_improvement_pct": average(dd_improvements),
            "worst_year_profit_factor_improvement_pct": minimum(pf_improvements),
            "worst_year_drawdown_improvement_pct": minimum(dd_improvements),
            "avg_positive_return": average([row.get("avg_positive_return") for row in eligible]),
            "avg_negative_return": average([row.get("avg_negative_return") for row in eligible]),
            "payoff_ratio": average([row.get("payoff_ratio") for row in eligible]),
            "breakeven_winrate": average([row.get("breakeven_winrate") for row in eligible]),
            "breakeven_winrate_margin": average([row.get("breakeven_winrate_margin") for row in eligible]),
            "monthly_positive_ratio": average([row.get("monthly_positive_ratio") for row in eligible]),
            "quarterly_positive_ratio": average([row.get("quarterly_positive_ratio") for row in eligible]),
            "best_month_contribution_pct": maximum([row.get("best_month_contribution_pct") for row in eligible]),
            "top_5_percent_trades_contribution_pct": maximum(
                [row.get("top_5_percent_trades_contribution_pct") for row in eligible]
            ),
            "max_flat_period_bars": maximum([row.get("max_flat_period_bars") for row in eligible]),
            "avg_estimated_cost_return": average([row.get("avg_estimated_cost_return") for row in eligible]),
            "gross_profit_factor": average([row.get("gross_profit_factor") for row in eligible]),
            "net_profit_factor": average([row.get("net_profit_factor") for row in eligible]),
            "gross_max_drawdown": average([row.get("gross_max_drawdown") for row in eligible]),
            "net_max_drawdown": average([row.get("net_max_drawdown") for row in eligible]),
            "gross_cumulative_return": average([row.get("gross_cumulative_return") for row in eligible]),
            "net_cumulative_return": average([row.get("net_cumulative_return") for row in eligible]),
            "profit_factor_worse_years": sum(1 for row in eligible if as_bool(row["is_profit_factor_worse_year"])),
            "drawdown_worse_years": sum(1 for row in eligible if as_bool(row["is_drawdown_worse_year"])),
            "low_sample_years": sum(1 for row in eligible if as_bool(row["is_low_sample_year"])),
            "partial_year_rows_excluded": sum(
                1
                for row in rows
                if int(row["baseline_trades_count"]) > 0 and as_bool(row["partial_year"])
            )
            if not include_incomplete_years
            else 0,
        }
        classification, rationale = classification_for_summary(
            summary,
            min_positive_year_ratio=min_positive_year_ratio,
            min_positive_symbol_ratio=min_positive_symbol_ratio,
            min_trades_per_year=min_trades_per_year,
        )
        summary["final_classification"] = classification
        summary["classification_rationale"] = rationale
        summaries.append(summary)

    summaries.sort(key=summary_sort_key)
    return summaries


def summary_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        FINAL_CLASSIFICATION_ORDER.get(str(row["final_classification"]), 99),
        -float(row["positive_year_ratio"] or 0),
        -float(row["positive_symbol_ratio"] or 0),
        -int(row["min_trades_in_any_year"] or 0),
        -float(row["avg_max_drawdown_improvement_pct"] or -1_000_000),
        -float(row["avg_profit_factor_improvement_pct"] or -1_000_000),
        str(row["combination_key"]),
    )


def pair_specific_score_and_classification(
    row: dict[str, object],
    *,
    min_trades_per_year: int,
    original_candidate_keys: set[str],
) -> tuple[int, str, str]:
    score = 0
    notes: list[str] = []

    positive_year_ratio = to_float(row.get("positive_year_ratio"))
    if positive_year_ratio is not None and positive_year_ratio >= 0.75:
        score += 3
        notes.append("positive_year_ratio >= 0.75 (+3)")
    elif positive_year_ratio is not None and positive_year_ratio >= 0.50:
        score += 2
        notes.append("positive_year_ratio >= 0.50 (+2)")
    else:
        score -= 3
        notes.append("positive_year_ratio < 0.50 (-3)")

    avg_pf = to_float(row.get("avg_profit_factor_improvement_pct"))
    if avg_pf is not None and avg_pf >= 5:
        score += 2
        notes.append("avg_profit_factor_improvement_pct >= 5 (+2)")
    elif avg_pf is not None and avg_pf > 0:
        score += 1
        notes.append("avg_profit_factor_improvement_pct > 0 (+1)")
    elif avg_pf is not None and avg_pf < 0:
        score -= 2
        notes.append("avg_profit_factor_improvement_pct < 0 (-2)")

    avg_dd = to_float(row.get("avg_max_drawdown_improvement_pct"))
    if avg_dd is not None and avg_dd >= 10:
        score += 2
        notes.append("avg_max_drawdown_improvement_pct >= 10 (+2)")
    elif avg_dd is not None and avg_dd >= 0:
        score += 1
        notes.append("avg_max_drawdown_improvement_pct >= 0 (+1)")
    elif avg_dd is not None and avg_dd < 0:
        score -= 2
        notes.append("avg_max_drawdown_improvement_pct < 0 (-2)")

    avg_trades = to_float(row.get("avg_trades_per_year"))
    min_trades = to_float(row.get("min_trades_in_any_year"))
    if avg_trades is not None and avg_trades >= min_trades_per_year:
        score += 1
        notes.append("avg_trades_per_year >= min_trades_per_year (+1)")
    if min_trades is not None and min_trades < min_trades_per_year:
        score -= 2
        notes.append("min_trades_in_any_year < min_trades_per_year (-2)")

    worst_dd = to_float(row.get("worst_year_drawdown_improvement_pct"))
    if worst_dd is not None and worst_dd < -25:
        score -= 3
        notes.append("worst_year_drawdown_improvement_pct < -25 (-3)")

    worst_pf = to_float(row.get("worst_year_profit_factor_improvement_pct"))
    if worst_pf is not None and worst_pf < -10:
        score -= 3
        notes.append("worst_year_profit_factor_improvement_pct < -10 (-3)")

    concentration_risks = concentration_penalties(row)
    for risk in concentration_risks:
        score -= 1
        notes.append(f"{risk} (-1)")

    if str(row["combination_key"]) in original_candidate_keys:
        score += 1
        notes.append("combined report candidate (+1)")

    drawdown_worse_years = int(row.get("drawdown_worse_years_count") or 0)
    years_tested = int(row.get("years_tested") or 0)
    low_sample_years = int(row.get("low_sample_years_count") or 0)
    drawdown_worse_majority = years_tested > 0 and drawdown_worse_years > years_tested / 2

    hard_reject = (
        years_tested == 0
        or positive_year_ratio is None
        or positive_year_ratio < 0.50
        or (avg_pf is not None and avg_pf < 0)
        or drawdown_worse_majority
        or (min_trades is not None and min_trades < min_trades_per_year)
        or (worst_dd is not None and worst_dd < -25)
        or (worst_pf is not None and worst_pf < -10)
    )
    select_conditions = [
        positive_year_ratio is not None and positive_year_ratio >= 0.75,
        avg_pf is not None and avg_pf > 0,
        avg_dd is not None and avg_dd >= 0,
        min_trades is not None and min_trades >= min_trades_per_year,
        worst_dd is not None and worst_dd > -25,
        worst_pf is not None and worst_pf > -10,
    ]

    if all(select_conditions):
        classification = "select_pair_specific"
    elif hard_reject and not (positive_year_ratio is not None and positive_year_ratio >= 0.50 and avg_pf is not None and avg_pf > 0):
        classification = "reject_pair_specific"
    elif score > 0 or low_sample_years > 0:
        classification = "watchlist_pair_specific"
    else:
        classification = "reject_pair_specific"

    if drawdown_worse_majority:
        notes.append("drawdown worsens in the majority of eligible years")
    return score, classification, "; ".join(notes)


def aggregate_pair_specific_rows(
    detail_rows: list[dict[str, object]],
    *,
    include_incomplete_years: bool,
    min_trades_per_year: int,
    original_candidate_keys: set[str],
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in detail_rows:
        key = (
            str(row["combination_key"]),
            str(row["symbol"]),
            str(row["timeframe"]),
            str(row["target_horizon"]),
            str(row.get("direction", "long")),
        )
        grouped[key].append(row)

    pair_rows = []
    for (combination_key, symbol, timeframe, target_horizon, direction), rows in grouped.items():
        rows_with_baseline = [row for row in rows if int(row["baseline_trades_count"]) > 0]
        eligible = [
            row for row in rows_with_baseline
            if include_incomplete_years or not as_bool(row["partial_year"])
        ]
        positive_years = sum(1 for row in eligible if as_bool(row["is_positive_year"]))
        years_tested = len(eligible)
        negative_years = years_tested - positive_years
        scenario_trades = [int(row["scenario_trades_count"]) for row in eligible]
        pf_improvements = [row["profit_factor_improvement_pct"] for row in eligible]
        dd_improvements = [row["max_drawdown_improvement_pct"] for row in eligible]
        drawdown_worse_years = sum(1 for row in eligible if as_bool(row["is_drawdown_worse_year"]))

        pair_row = {
            "combination_key": combination_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "target_horizon": target_horizon,
            "direction": direction,
            "cost_mode": str(rows[0].get("cost_mode", "none")),
            "return_mode": str(rows[0].get("return_mode", "gross")),
            "cost_config_source": str(rows[0].get("cost_config_source", "not_applicable")),
            "point_size_source": str(rows[0].get("point_size_source", "not_applicable")),
            "spread_source_used": str(rows[0].get("spread_source_used", "not_applicable")),
            "symbols_using_default_costs": str(rows[0].get("symbols_using_default_costs", "")),
            "years_tested": years_tested,
            "positive_years": positive_years,
            "negative_years": negative_years,
            "positive_year_ratio": positive_years / years_tested if years_tested else 0.0,
            "avg_trades_per_year": average(scenario_trades),
            "min_trades_in_any_year": min(scenario_trades) if scenario_trades else 0,
            "avg_profit_factor_improvement_pct": average(pf_improvements),
            "median_profit_factor_improvement_pct": median_value(pf_improvements),
            "avg_max_drawdown_improvement_pct": average(dd_improvements),
            "median_max_drawdown_improvement_pct": median_value(dd_improvements),
            "worst_year_profit_factor_improvement_pct": minimum(pf_improvements),
            "worst_year_drawdown_improvement_pct": minimum(dd_improvements),
            "avg_positive_return": average([row.get("avg_positive_return") for row in eligible]),
            "avg_negative_return": average([row.get("avg_negative_return") for row in eligible]),
            "payoff_ratio": average([row.get("payoff_ratio") for row in eligible]),
            "breakeven_winrate": average([row.get("breakeven_winrate") for row in eligible]),
            "breakeven_winrate_margin": average([row.get("breakeven_winrate_margin") for row in eligible]),
            "monthly_positive_ratio": average([row.get("monthly_positive_ratio") for row in eligible]),
            "quarterly_positive_ratio": average([row.get("quarterly_positive_ratio") for row in eligible]),
            "best_month_contribution_pct": maximum([row.get("best_month_contribution_pct") for row in eligible]),
            "top_5_percent_trades_contribution_pct": maximum(
                [row.get("top_5_percent_trades_contribution_pct") for row in eligible]
            ),
            "max_flat_period_bars": maximum([row.get("max_flat_period_bars") for row in eligible]),
            "avg_estimated_cost_return": average([row.get("avg_estimated_cost_return") for row in eligible]),
            "gross_profit_factor": average([row.get("gross_profit_factor") for row in eligible]),
            "net_profit_factor": average([row.get("net_profit_factor") for row in eligible]),
            "gross_max_drawdown": average([row.get("gross_max_drawdown") for row in eligible]),
            "net_max_drawdown": average([row.get("net_max_drawdown") for row in eligible]),
            "gross_cumulative_return": average([row.get("gross_cumulative_return") for row in eligible]),
            "net_cumulative_return": average([row.get("net_cumulative_return") for row in eligible]),
            "low_sample_years_count": sum(1 for row in eligible if as_bool(row["is_low_sample_year"])),
            "partial_years_count": sum(1 for row in rows_with_baseline if as_bool(row["partial_year"])),
            "drawdown_worse_years_count": drawdown_worse_years,
        }
        score, classification, notes = pair_specific_score_and_classification(
            pair_row,
            min_trades_per_year=min_trades_per_year,
            original_candidate_keys=original_candidate_keys,
        )
        pair_row["pair_specific_score"] = score
        pair_row["pair_specific_classification"] = classification
        pair_row["notes"] = notes
        pair_rows.append(pair_row)

    pair_rows.sort(
        key=lambda row: (
            str(row["symbol"]),
            {"select_pair_specific": 0, "watchlist_pair_specific": 1, "reject_pair_specific": 2}.get(
                str(row["pair_specific_classification"]),
                99,
            ),
            -int(row["pair_specific_score"]),
            -float(row["positive_year_ratio"] or 0),
            str(row["combination_key"]),
        )
    )
    return pair_rows


def pair_specific_fieldnames() -> list[str]:
    return [
        "combination_key",
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
        "years_tested",
        "positive_years",
        "negative_years",
        "positive_year_ratio",
        "avg_trades_per_year",
        "min_trades_in_any_year",
        "avg_profit_factor_improvement_pct",
        "median_profit_factor_improvement_pct",
        "avg_max_drawdown_improvement_pct",
        "median_max_drawdown_improvement_pct",
        "worst_year_profit_factor_improvement_pct",
        "worst_year_drawdown_improvement_pct",
        "avg_positive_return",
        "avg_negative_return",
        "payoff_ratio",
        "breakeven_winrate",
        "breakeven_winrate_margin",
        "monthly_positive_ratio",
        "quarterly_positive_ratio",
        "best_month_contribution_pct",
        "top_5_percent_trades_contribution_pct",
        "max_flat_period_bars",
        "avg_estimated_cost_return",
        "gross_profit_factor",
        "net_profit_factor",
        "gross_max_drawdown",
        "net_max_drawdown",
        "gross_cumulative_return",
        "net_cumulative_return",
        "low_sample_years_count",
        "partial_years_count",
        "pair_specific_score",
        "pair_specific_classification",
        "notes",
    ]


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe_value(value) for key, value in row.items()})


def detail_fieldnames() -> list[str]:
    return [
        "combination_key",
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
        "year",
        "partial_year",
        "non_overlap_eval",
        "rows_before_non_overlap",
        "rows_after_non_overlap",
        "baseline_trades_count",
        "scenario_trades_count",
        "mean_return",
        "median_return",
        "win_rate",
        "cumulative_return",
        "max_drawdown",
        "profit_factor",
        "avg_positive_return",
        "avg_negative_return",
        "payoff_ratio",
        "breakeven_winrate",
        "breakeven_winrate_margin",
        "monthly_positive_ratio",
        "quarterly_positive_ratio",
        "best_month_contribution_pct",
        "top_5_percent_trades_contribution_pct",
        "max_flat_period_bars",
        "avg_estimated_cost_return",
        "gross_profit_factor",
        "net_profit_factor",
        "gross_max_drawdown",
        "net_max_drawdown",
        "gross_cumulative_return",
        "net_cumulative_return",
        "profit_factor_improvement_pct",
        "max_drawdown_improvement_pct",
        "is_positive_year",
        "is_low_sample_year",
        "is_profit_factor_worse_year",
        "is_drawdown_worse_year",
    ]


def summary_fieldnames() -> list[str]:
    return [
        "combination_key",
        "direction",
        "cost_mode",
        "return_mode",
        "cost_config_source",
        "point_size_source",
        "spread_source_used",
        "symbols_using_default_costs",
        "symbols_tested",
        "positive_symbols",
        "positive_symbol_ratio",
        "years_tested",
        "positive_years",
        "positive_year_ratio",
        "calendar_years_tested",
        "positive_calendar_years",
        "avg_trades_per_year",
        "min_trades_in_any_year",
        "avg_profit_factor_improvement_pct",
        "median_profit_factor_improvement_pct",
        "avg_max_drawdown_improvement_pct",
        "worst_year_profit_factor_improvement_pct",
        "worst_year_drawdown_improvement_pct",
        "avg_positive_return",
        "avg_negative_return",
        "payoff_ratio",
        "breakeven_winrate",
        "breakeven_winrate_margin",
        "monthly_positive_ratio",
        "quarterly_positive_ratio",
        "best_month_contribution_pct",
        "top_5_percent_trades_contribution_pct",
        "max_flat_period_bars",
        "avg_estimated_cost_return",
        "gross_profit_factor",
        "net_profit_factor",
        "gross_max_drawdown",
        "net_max_drawdown",
        "gross_cumulative_return",
        "net_cumulative_return",
        "profit_factor_worse_years",
        "drawdown_worse_years",
        "low_sample_years",
        "partial_year_rows_excluded",
        "final_classification",
        "classification_rationale",
    ]


def fmt(value: object, digits: int = 2) -> str:
    parsed = to_float(value)
    if parsed is None:
        return "n/a"
    if math.isinf(parsed):
        return "inf" if parsed > 0 else "-inf"
    return f"{parsed:.{digits}f}"


def markdown_section(title: str, rows: list[dict[str, object]], limit: int | None = None) -> list[str]:
    lines = [f"## {title}", ""]
    selected_rows = rows if limit is None else rows[:limit]
    if not selected_rows:
        lines.extend(["- none", ""])
        return lines

    for index, row in enumerate(selected_rows, start=1):
        lines.extend(
            [
                f"### {index}. {row['combination_key']}",
                "",
                f"- Final classification: {row['final_classification']}",
                f"- Positive year ratio: {fmt(row['positive_year_ratio'])}",
                f"- Positive symbol ratio: {fmt(row['positive_symbol_ratio'])}",
                f"- Symbols tested: {row['symbols_tested']} / positive: {row['positive_symbols']}",
                f"- Symbol-year observations tested: {row['years_tested']} / positive: {row['positive_years']}",
                f"- Avg trades per year: {fmt(row['avg_trades_per_year'], 1)}",
                f"- Min trades in any year: {row['min_trades_in_any_year']}",
                f"- Avg PF improvement pct: {fmt(row['avg_profit_factor_improvement_pct'])}",
                f"- Median PF improvement pct: {fmt(row['median_profit_factor_improvement_pct'])}",
                f"- Avg max drawdown improvement pct: {fmt(row['avg_max_drawdown_improvement_pct'])}",
                f"- Worst-year PF improvement pct: {fmt(row['worst_year_profit_factor_improvement_pct'])}",
                f"- Worst-year drawdown improvement pct: {fmt(row['worst_year_drawdown_improvement_pct'])}",
                f"- Monthly positive ratio: {fmt(row.get('monthly_positive_ratio'))}",
                f"- Quarterly positive ratio: {fmt(row.get('quarterly_positive_ratio'))}",
                f"- Best month contribution pct: {fmt(row.get('best_month_contribution_pct'))}",
                f"- Top 5 percent trades contribution pct: {fmt(row.get('top_5_percent_trades_contribution_pct'))}",
                f"- Max flat period bars: {fmt(row.get('max_flat_period_bars'), 0)}",
                f"- Rationale: {row['classification_rationale']}",
                "",
            ]
        )
    return lines


def write_pair_specific_report(
    path: Path,
    rows: list[dict[str, object]],
    *,
    run_id: str,
    direction: str,
    min_trades_per_year: int,
    cost_fields: dict[str, str],
) -> None:
    selected_or_watchlist = [
        row for row in rows
        if row["pair_specific_classification"] in {"select_pair_specific", "watchlist_pair_specific"}
    ]
    rejected = [row for row in rows if row["pair_specific_classification"] == "reject_pair_specific"]
    symbols = sorted({str(row["symbol"]) for row in rows})

    lines = [
        "# Pair-Specific Research Candidates",
        "",
        "## Executive Summary",
        "",
        "These combinations are evaluated for individual symbols. They are not cross-pair robust by definition and must not be generalized to other symbols without separate testing.",
        "",
        f"- Run ID: {run_id}",
        f"- Direction: {direction}",
        f"- cost_config_source: {cost_fields['cost_config_source']}",
        f"- point_size_source: {cost_fields['point_size_source']}",
        f"- spread_source_used: {cost_fields['spread_source_used']}",
        f"- symbols_using_default_costs: {cost_fields['symbols_using_default_costs'] or 'none'}",
        f"- Pair-specific rows: {len(rows)}",
        f"- Select pair-specific: {sum(1 for row in rows if row['pair_specific_classification'] == 'select_pair_specific')}",
        f"- Watchlist pair-specific: {sum(1 for row in rows if row['pair_specific_classification'] == 'watchlist_pair_specific')}",
        f"- Reject pair-specific: {len(rejected)}",
        f"- Minimum trades per year: {min_trades_per_year}",
        "",
        "## Top Pair-Specific Candidates By Symbol",
        "",
    ]

    for symbol in symbols:
        symbol_rows = [
            row for row in selected_or_watchlist
            if row["symbol"] == symbol
        ]
        symbol_rows.sort(key=lambda row: (-int(row["pair_specific_score"]), str(row["combination_key"])))
        lines.extend(
            [
                f"### {symbol}",
                "",
                "| Rank | Combination | Direction | Classification | Score | Positive years | PF improvement | DD improvement | Trades/year |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        if not symbol_rows:
            lines.append("| - | none | - | - | - | - | - | - | - |")
        for rank, row in enumerate(symbol_rows[:20], start=1):
            lines.append(
                "| {rank} | {combination} | {direction} | {classification} | {score} | {positive}/{years} | {pf} | {dd} | {trades} |".format(
                    rank=rank,
                    combination=str(row["combination_key"]).replace("|", "\\|"),
                    direction=row["direction"],
                    classification=row["pair_specific_classification"],
                    score=row["pair_specific_score"],
                    positive=row["positive_years"],
                    years=row["years_tested"],
                    pf=fmt(row["avg_profit_factor_improvement_pct"]),
                    dd=fmt(row["avg_max_drawdown_improvement_pct"]),
                    trades=fmt(row["avg_trades_per_year"], 1),
                )
            )
        lines.append("")

    lines.extend(["## Rejected Pair-Specific Candidates", ""])
    if not rejected:
        lines.extend(["- none", ""])
    else:
        by_symbol: dict[str, int] = defaultdict(int)
        for row in rejected:
            by_symbol[str(row["symbol"])] += 1
        for symbol, count in sorted(by_symbol.items()):
            lines.append(f"- {symbol}: {count}")
        lines.append("")

    lines.extend(
        [
            "## Interpretation",
            "",
            "- Pair-specific candidates are not live strategies and do not create operational signals.",
            "- They are research leads for deciding what to test next in a separate rule-based backtest.",
            "- A pair-specific result should not be generalized to other symbols.",
            "- Any follow-up backtest still needs explicit costs, spread, slippage, risk controls, and out-of-sample checks.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(
    path: Path,
    summaries: list[dict[str, object]],
    *,
    run_id: str,
    direction: str,
    symbols: list[str],
    timeframe: str,
    target_horizon: int,
    years: list[int],
    hypotheses_file: Path | None,
    skipped_hypotheses: list[dict[str, object]],
    include_incomplete_years: bool,
    min_trades_per_year: int,
    min_positive_year_ratio: float,
    min_positive_symbol_ratio: float,
    non_overlap_eval: bool,
    detail_rows: list[dict[str, object]],
    cost_mode: str,
    return_mode: str,
    cost_fields: dict[str, str],
) -> None:
    selected = [row for row in summaries if row["final_classification"] == "select"]
    watchlist = [row for row in summaries if row["final_classification"] == "watchlist"]
    rejected = [row for row in summaries if row["final_classification"] == "reject"]

    lines = [
        "# Final Research Candidates",
        "",
        "This is an offline research validation report. It does not create live signals, does not call terminal APIs, and does not use order execution APIs.",
        "",
        f"Run ID: {run_id}",
        f"Direction: {direction}",
        f"Symbols: {' '.join(symbols)}",
        f"Timeframe: {timeframe}",
        f"Target horizon: {target_horizon}",
        f"Years requested: {' '.join(str(year) for year in years)}",
        f"Hypotheses file: {hypotheses_file if hypotheses_file is not None else 'manual CLI hypotheses'}",
        f"Include incomplete years in classification: {str(include_incomplete_years).lower()}",
        f"Minimum trades per year: {min_trades_per_year}",
        f"Minimum positive year ratio: {min_positive_year_ratio}",
        f"Minimum positive symbol ratio: {min_positive_symbol_ratio}",
        f"Non-overlap evaluation: {str(non_overlap_eval).lower()}",
        f"Cost mode: {cost_mode}",
        f"Return mode: {return_mode}",
        f"Ranking basis: {'estimated net returns' if return_mode == 'net' else 'gross returns'}",
        f"cost_config_source: {cost_fields['cost_config_source']}",
        f"point_size_source: {cost_fields['point_size_source']}",
        f"spread_source_used: {cost_fields['spread_source_used']}",
        f"symbols_using_default_costs: {cost_fields['symbols_using_default_costs'] or 'none'}",
        "",
        "Combinations are ordered by year stability, cross-symbol stability, sufficient trade count, drawdown behavior, then profit factor improvement.",
        "",
    ]
    if non_overlap_eval:
        rows_before = [row.get("rows_before_non_overlap") for row in detail_rows]
        rows_after = [row.get("rows_after_non_overlap") for row in detail_rows]
        lines.extend(
            [
                "## Non-Overlap Evaluation",
                "",
                "- `non_overlap_eval = true`: yearly baseline and scenario metrics use roughly one row every target_horizon bars.",
                f"- Average rows before non-overlap: {fmt(average(rows_before), 1)}",
                f"- Average rows after non-overlap: {fmt(average(rows_after), 1)}",
                "- This is a robustness check for overlapping future labels; it reduces sample size and may make classifications stricter.",
                "",
            ]
        )
    lines.extend(markdown_section("Selected Candidates", selected))
    lines.extend(markdown_section("Watchlist Candidates", watchlist))
    lines.extend(markdown_section("Rejected Combinations", rejected, 20))
    reason_counts: dict[str, int] = defaultdict(int)
    for row in skipped_hypotheses:
        reason_counts[str(row["skip_reason"])] += 1
    lines.extend(["## Skipped hypotheses", ""])
    if not skipped_hypotheses:
        lines.extend(["- none", ""])
    else:
        lines.append(f"- Total skipped: {len(skipped_hypotheses)}")
        for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {reason}: {count}")
        lines.append("")
    lines.extend(
        [
            "## Notes",
            "",
            "- `cumulative_return` is compounded: product(1 + returns) - 1.",
            "- Raw price levels (`open`, `high`, `low`, `close`) are skipped in final validation because absolute scales differ across symbols.",
            "- `numeric_tercile` conditions are skipped in final validation until time-safe thresholds are implemented.",
            "- `partial_year = true` marks years that do not have full-year data coverage or are the current/future year.",
            "- Performance concentration metrics penalize fragile results where profits cluster in too few months or trades; they never promote a candidate by themselves.",
            f"- Full-year coverage allows normal market-calendar edges through Jan {FULL_YEAR_START_TOLERANCE_DAY} and from Dec {FULL_YEAR_END_TOLERANCE_DAY}.",
            "- Incomplete years are written to the detail CSV. They influence classification only when `--include-incomplete-years` is passed.",
            "- `years_tested` counts eligible symbol-year observations, not just unique calendar years.",
            f"- Worst-year drawdown is considered catastrophic below {CATASTROPHIC_DRAWDOWN_WORSENING_PCT}%.",
            "- Non-finite profit factor values are treated as unavailable for improvement calculations in final CSV outputs.",
            "- This script is research-only and validates hypotheses after `evaluate_combined_hypotheses.py`.",
            f"- Direction `{direction}` is evaluated separately; long and short classifications are not mixed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    if args.target_horizon <= 0:
        raise ValueError("--target-horizon must be greater than zero.")
    if args.min_trades_per_year <= 0:
        raise ValueError("--min-trades-per-year must be greater than zero.")
    if not 0 <= args.min_positive_year_ratio <= 1:
        raise ValueError("--min-positive-year-ratio must be between 0 and 1.")
    if not 0 <= args.min_positive_symbol_ratio <= 1:
        raise ValueError("--min-positive-symbol-ratio must be between 0 and 1.")

    args.direction = normalize_direction(args.direction)
    timeframe = args.timeframe.strip().upper()
    target_horizon = int(args.target_horizon)
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    cost_config = load_cost_config(args.cost_config)
    return_column = f"future_return_{target_horizon}"
    symbols = normalize_symbols(args.symbols)
    if not symbols:
        symbols = detect_available_symbols(args.db_path, timeframe, return_column)
    if not symbols:
        raise ValueError("No symbols provided or detected in ml_dataset.")

    available_years = detect_available_years(args.db_path, symbols, timeframe, return_column)
    years = resolve_years(args, available_years)
    if not years:
        raise ValueError("No years provided or detected in ml_dataset.")

    combinations, hypotheses_file = collect_combinations(args)
    if not combinations:
        raise ValueError("No selected/watchlist combinations found to validate.")

    run_id = infer_run_id(args, hypotheses_file)
    output_dir = resolve_output_dir(args.output_dir, run_id, args.direction, args.overwrite)
    original_candidate_keys = set(combinations)
    combinations, skipped_hypotheses = filter_pre_skipped_combinations(combinations, hypotheses_file)

    rows_by_symbol: dict[str, list[dict[str, object]]] = {}
    for symbol in symbols:
        symbol_rows = load_symbol_rows(args.db_path, symbol, timeframe, return_column)
        if not symbol_rows:
            print(f"Warning: no rows found for {symbol} {timeframe}; skipping symbol.")
            continue
        rows_by_symbol[symbol] = symbol_rows

    cost_report = {}
    if cost_mode == "estimated":
        cost_report = validate_estimated_cost_config(
            symbols=symbols,
            rows_by_symbol=rows_by_symbol,
            config=cost_config,
            strict=args.strict_cost_config,
        )
        for warning in cost_report_warnings(cost_report):
            print(f"Warning: {warning}")
    run_cost_fields = cost_report_fields(cost_report)

    detail_rows = []
    for symbol in symbols:
        symbol_rows = rows_by_symbol.get(symbol, [])
        if not symbol_rows:
            continue
        symbol_detail_rows, symbol_skipped = validate_symbol_years(
            symbol=symbol,
            timeframe=timeframe,
            target_horizon=target_horizon,
            rows=symbol_rows,
            years=years,
            combinations=combinations,
            return_column=return_column,
            direction=args.direction,
            min_trades_per_year=args.min_trades_per_year,
            source_path=hypotheses_file,
            non_overlap_eval=args.non_overlap_eval,
            cost_config=cost_config,
            cost_mode=cost_mode,
            return_mode=return_mode,
            cost_fields=cost_report_fields(cost_report, symbol),
        )
        detail_rows.extend(symbol_detail_rows)
        skipped_hypotheses.extend(symbol_skipped)

    skipped_hypotheses = dedupe_skipped(skipped_hypotheses)

    summaries = aggregate_detail_rows(
        detail_rows,
        include_incomplete_years=args.include_incomplete_years,
        min_positive_year_ratio=args.min_positive_year_ratio,
        min_positive_symbol_ratio=args.min_positive_symbol_ratio,
        min_trades_per_year=args.min_trades_per_year,
    )
    pair_specific_rows = aggregate_pair_specific_rows(
        detail_rows,
        include_incomplete_years=args.include_incomplete_years,
        min_trades_per_year=args.min_trades_per_year,
        original_candidate_keys=original_candidate_keys,
    )
    candidates = [row for row in summaries if row["final_classification"] in {"select", "watchlist"}]
    for row in summaries:
        row.update(run_cost_fields)
    for row in candidates:
        row.update(run_cost_fields)
    for row in pair_specific_rows:
        row.update(cost_report_fields(cost_report, str(row.get("symbol", ""))))

    detail_path = output_dir / DETAIL_OUTPUT
    summary_path = output_dir / SUMMARY_OUTPUT
    candidates_path = output_dir / CANDIDATES_OUTPUT
    report_path = output_dir / REPORT_OUTPUT
    skipped_path = output_dir / SKIPPED_OUTPUT
    pair_specific_path = output_dir / PAIR_SPECIFIC_OUTPUT
    pair_specific_report_path = output_dir / PAIR_SPECIFIC_REPORT_OUTPUT

    write_csv(detail_path, detail_rows, detail_fieldnames())
    write_csv(summary_path, summaries, summary_fieldnames())
    write_csv(candidates_path, candidates, summary_fieldnames())
    write_csv(pair_specific_path, pair_specific_rows, pair_specific_fieldnames())
    if skipped_hypotheses:
        write_csv(skipped_path, skipped_hypotheses, skipped_fieldnames())
    write_report(
        report_path,
        summaries,
        run_id=run_id,
        direction=args.direction,
        symbols=symbols,
        timeframe=timeframe,
        target_horizon=target_horizon,
        years=years,
        hypotheses_file=hypotheses_file,
        skipped_hypotheses=skipped_hypotheses,
        include_incomplete_years=args.include_incomplete_years,
        min_trades_per_year=args.min_trades_per_year,
        min_positive_year_ratio=args.min_positive_year_ratio,
        min_positive_symbol_ratio=args.min_positive_symbol_ratio,
        non_overlap_eval=args.non_overlap_eval,
        detail_rows=detail_rows,
        cost_mode=cost_mode,
        return_mode=return_mode,
        cost_fields=run_cost_fields,
    )
    write_pair_specific_report(
        pair_specific_report_path,
        pair_specific_rows,
        run_id=run_id,
        direction=args.direction,
        min_trades_per_year=args.min_trades_per_year,
        cost_fields=run_cost_fields,
    )

    if not detail_rows:
        raise ValueError(
            f"No validation rows were produced. Outputs were still written under {output_dir}; "
            "check skipped_hypotheses.csv and the report."
        )

    classifications = defaultdict(int)
    for row in summaries:
        classifications[str(row["final_classification"])] += 1

    print(f"Run ID: {run_id}")
    print(f"Direction: {args.direction}")
    print(f"Cost mode: {cost_mode}")
    print(f"Return mode: {return_mode}")
    print(f"Strict cost config: {str(args.strict_cost_config).lower()}")
    print(f"Symbols validated: {len(symbols)}")
    print(f"Years requested: {' '.join(str(year) for year in years)}")
    print(f"Combinations validated: {len(combinations)}")
    print(f"Hypotheses skipped: {len(skipped_hypotheses)}")
    print(f"Detail rows: {len(detail_rows)}")
    print(f"Non-overlap eval: {bool_text(args.non_overlap_eval)}")
    print(f"Pair-specific rows: {len(pair_specific_rows)}")
    print(
        "Classifications: "
        + ", ".join(f"{label}={count}" for label, count in sorted(classifications.items()))
    )
    print("Files created:")
    print(f"- {detail_path}")
    print(f"- {summary_path}")
    print(f"- {candidates_path}")
    print(f"- {report_path}")
    print(f"- {pair_specific_path}")
    print(f"- {pair_specific_report_path}")
    if skipped_hypotheses:
        print(f"- {skipped_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate selected combined research hypotheses year by year across symbols."
    )
    parser.add_argument("--symbols", nargs="+", help="Symbols to validate. Default: all symbols found in ml_dataset.")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--target-horizon", type=int, default=10)
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--years", nargs="+", type=int, help="Explicit years to validate.")
    parser.add_argument("--include-incomplete-years", action="store_true")
    parser.add_argument("--min-trades-per-year", type=int, default=100)
    parser.add_argument("--min-positive-year-ratio", type=float, default=0.75)
    parser.add_argument("--min-positive-symbol-ratio", type=float, default=0.75)
    parser.add_argument("--run-id", help=f"Evaluation run ID under {DEFAULT_EVALUATIONS_DIR}.")
    parser.add_argument(
        "--hypotheses-file",
        type=Path,
        help=f"Default: latest {SELECTED_COMBINED_FILE} under {DEFAULT_EVALUATIONS_DIR}, or --run-id path.",
    )
    parser.add_argument("--hypothesis", action="append", help="Manual combination string. Can be passed multiple times.")
    parser.add_argument("--evaluations-dir", type=Path, default=DEFAULT_EVALUATIONS_DIR)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help=f"Default: {DEFAULT_DB_PATH}")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output directory. Final files are written under OUTPUT_DIR/RUN_ID. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite files in OUTPUT_DIR/RUN_ID if they exist.")
    parser.add_argument("--non-overlap-eval", action="store_true")
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    return parser.parse_args()


def main() -> int:
    try:
        run(parse_args())
    except (FileNotFoundError, ValueError, sqlite3.Error, OSError) as exc:
        print(f"Year-by-year validation failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
