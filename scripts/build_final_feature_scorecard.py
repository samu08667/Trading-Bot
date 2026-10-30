import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
import math
from pathlib import Path
import re
from statistics import median

try:
    from research_metrics import normalize_direction
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_final_feature_scorecard
    from scripts.research_metrics import normalize_direction


BASE_DIR = Path(__file__).resolve().parents[1]

DEFAULT_VALIDATION_DIR = BASE_DIR / "reports" / "validation" / "by_year"
DEFAULT_COMBINED_EVALUATIONS_DIR = BASE_DIR / "reports" / "backtests" / "combined" / "evaluations"
DEFAULT_ML_RESEARCH_DIR = BASE_DIR / "reports" / "ml_research"
DEFAULT_BACKTESTS_DIR = BASE_DIR / "reports" / "backtests"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "final_feature_scorecard"

FINAL_CANDIDATES_FILE = "final_research_candidates.csv"
VALIDATION_SUMMARY_FILE = "by_year_validation_summary.csv"
VALIDATION_DETAIL_FILE = "by_year_validation_detail.csv"
PAIR_SPECIFIC_CANDIDATES_FILE = "pair_specific_candidates.csv"
SKIPPED_HYPOTHESES_FILE = "skipped_hypotheses.csv"
SELECTED_COMBINED_FILE = "selected_combined_hypotheses.csv"
AGGREGATE_FEATURE_RANKING_FILE = "aggregate_feature_ranking.csv"
CROSS_PAIR_SUMMARY_FILE = "cross_pair_summary.csv"
EVALUATED_BACKTEST_RESULTS_FILE = "evaluated_backtest_results.csv"

OUTPUT_SCORECARD = "final_feature_scorecard.csv"
OUTPUT_PAIR_SPECIFIC_SCORECARD = "pair_specific_feature_scorecard.csv"
OUTPUT_REPORT = "final_feature_scorecard_report.md"

RAW_PRICE_FEATURES = {"open", "high", "low", "close"}
POSITIVE_ML_LABELS = {"strong", "interesting"}
POSITIVE_BACKTEST_LABELS = {"robust", "promising"}
DEFAULT_MIN_TRADES_PER_YEAR = 100

CSV_FIELDS = [
    "feature",
    "condition",
    "feature_condition_key",
    "rule_role",
    "tradability_note",
    "direction",
    "cost_mode",
    "return_mode",
    "total_score",
    "final_feature_classification",
    "appears_in_select_count",
    "appears_in_watchlist_count",
    "appears_in_reject_count",
    "avg_positive_year_ratio",
    "avg_positive_symbol_ratio",
    "avg_trades_per_year",
    "min_trades_in_any_year",
    "avg_profit_factor_improvement_pct",
    "median_profit_factor_improvement_pct",
    "avg_max_drawdown_improvement_pct",
    "worst_year_profit_factor_improvement_pct",
    "worst_year_drawdown_improvement_pct",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "best_month_contribution_pct",
    "top_5_percent_trades_contribution_pct",
    "max_flat_period_bars",
    "ml_support",
    "backtest_support",
    "penalty_points",
    "bonus_points",
    "exclusion_reason",
    "notes",
]

PAIR_SPECIFIC_CSV_FIELDS = [
    "symbol",
    "feature",
    "condition",
    "direction",
    "cost_mode",
    "return_mode",
    "feature_condition_key",
    "rule_role",
    "tradability_note",
    "pair_specific_score",
    "pair_specific_classification",
    "appears_in_select_pair_specific_count",
    "appears_in_watchlist_pair_specific_count",
    "avg_positive_year_ratio",
    "avg_trades_per_year",
    "avg_profit_factor_improvement_pct",
    "avg_max_drawdown_improvement_pct",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "best_month_contribution_pct",
    "top_5_percent_trades_contribution_pct",
    "max_flat_period_bars",
    "notes",
]


@dataclass(frozen=True)
class ParsedCondition:
    raw_condition: str
    scenario_type: str
    feature: str
    condition: str
    contains_numeric_tercile: bool

    @property
    def key(self) -> str:
        return f"{self.feature}:{self.condition}"


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def read_optional_csv(path: Path, warnings: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        warnings.append(f"Optional input not found: {path}")
        return []
    return read_csv_dicts(path)


def to_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def to_int(value: object) -> int:
    parsed = to_float(value)
    return int(parsed) if parsed is not None else 0


def average(values: list[object]) -> float | None:
    usable = [float(value) for value in (to_float(item) for item in values) if value is not None]
    return sum(usable) / len(usable) if usable else None


def median_value(values: list[object]) -> float | None:
    usable = [float(value) for value in (to_float(item) for item in values) if value is not None]
    return median(usable) if usable else None


def minimum(values: list[object]) -> float | None:
    usable = [float(value) for value in (to_float(item) for item in values) if value is not None]
    return min(usable) if usable else None


def maximum(values: list[object]) -> float | None:
    usable = [float(value) for value in (to_float(item) for item in values) if value is not None]
    return max(usable) if usable else None


def concentration_penalties(row: dict[str, str] | dict[str, object]) -> list[str]:
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


def csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return value


def normalized_cost_mode(value: object) -> str:
    mode = str(value or "none").strip().lower()
    return mode if mode in {"none", "estimated"} else "none"


def normalized_return_mode(value: object) -> str:
    mode = str(value or "gross").strip().lower()
    return mode if mode in {"gross", "net"} else "gross"


def row_matches_modes(row: dict[str, str], cost_mode: str, return_mode: str) -> bool:
    return (
        normalized_cost_mode(row.get("cost_mode")) == cost_mode
        and normalized_return_mode(row.get("return_mode")) == return_mode
    )


def filter_rows_by_modes(
    rows: list[dict[str, str]],
    *,
    cost_mode: str,
    return_mode: str,
    source: str,
    warnings: list[str],
) -> list[dict[str, str]]:
    kept = [row for row in rows if row_matches_modes(row, cost_mode, return_mode)]
    skipped = len(rows) - len(kept)
    if skipped:
        warnings.append(
            f"{source}: skipped {skipped} rows with a different cost_mode/return_mode "
            f"than {cost_mode}/{return_mode}."
        )
    return kept


def split_combination(combination_key: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"\s+AND\s+", combination_key.strip(), flags=re.IGNORECASE)
        if item.strip()
    ]


def parse_condition(condition_key: str) -> ParsedCondition | None:
    parts = [part.strip() for part in condition_key.split(":") if part.strip()]
    if len(parts) < 2:
        return None

    scenario_type = parts[0]
    contains_numeric_tercile = any(part.lower() == "numeric_tercile" for part in parts)

    if len(parts) == 2:
        feature = scenario_type
        condition = parts[1]
    else:
        feature_token = parts[1]
        condition = ":".join(parts[2:])
        if scenario_type == "day_of_week":
            feature = "day_of_week"
        elif scenario_type == "ma_diff":
            feature = "ma_diff"
        elif scenario_type == "hour_session":
            feature = "hour_session"
        elif scenario_type in {"news_feature", "binary_feature", "numeric_tercile"}:
            feature = feature_token
        elif scenario_type == feature_token:
            feature = feature_token
        else:
            feature = feature_token or scenario_type

    feature = feature.strip()
    condition = condition.strip()
    if not feature or not condition:
        return None

    return ParsedCondition(
        raw_condition=condition_key.strip(),
        scenario_type=scenario_type,
        feature=feature,
        condition=condition,
        contains_numeric_tercile=contains_numeric_tercile,
    )


def parse_combination(
    combination_key: str,
    *,
    source: str,
    warnings: list[str],
) -> list[ParsedCondition]:
    if not combination_key.strip():
        warnings.append(f"Empty combination_key in {source}; skipped.")
        return []

    parsed_conditions: list[ParsedCondition] = []
    for raw_condition in split_combination(combination_key):
        parsed = parse_condition(raw_condition)
        if parsed is None:
            warnings.append(
                f"Could not parse condition {raw_condition!r} from combination {combination_key!r} in {source}."
            )
            continue
        parsed_conditions.append(parsed)

    if not parsed_conditions:
        warnings.append(f"No parsable conditions found in combination {combination_key!r} from {source}.")
    return parsed_conditions


def exclusion_reasons(parsed: ParsedCondition, extra_reason: str | None = None) -> list[str]:
    reasons = []
    feature_lower = parsed.feature.lower()
    extra_lower = (extra_reason or "").lower()
    if feature_lower in RAW_PRICE_FEATURES:
        reasons.append("raw_price_level_excluded")
    if parsed.contains_numeric_tercile or "numeric_tercile" in extra_lower:
        reasons.append("numeric_tercile_not_time_safe")
    if "raw_price" in extra_lower and "raw_price_level_excluded" not in reasons:
        reasons.append("raw_price_level_excluded")
    return reasons


def rule_role_for(feature: object, condition: object = "", exclusion_reason: object = "") -> str:
    feature_text = str(feature or "").strip().lower()
    condition_text = str(condition or "").strip().lower()
    exclusion_text = str(exclusion_reason or "").strip().lower()
    combined = f"{feature_text}:{condition_text}"

    if feature_text in RAW_PRICE_FEATURES or "raw_price_level_excluded" in exclusion_text:
        return "not_tradable_alone"
    if "numeric_tercile" in combined or "numeric_tercile" in exclusion_text:
        return "not_tradable_alone"
    if feature_text == "ma_diff":
        return "trend_filter"
    if feature_text.startswith("return_"):
        return "momentum_filter"
    if feature_text in {"volatility_20", "volatility_100", "volatility_ratio_20_100"}:
        return "volatility_regime_filter"
    if (
        feature_text in {
            "true_range",
            "atr_14",
            "atr_20",
            "atr_50",
            "range_to_atr_20",
            "body_to_atr_20",
            "upper_wick_to_atr_20",
            "lower_wick_to_atr_20",
            "close_to_ma_fast_atr_20",
            "close_to_ma_slow_atr_20",
            "ma_diff_atr_20",
        }
    ):
        return "volatility_regime_filter"
    if feature_text in {"spread_avg_20", "spread_price", "spread_return", "spread_to_volume_ratio", "spread_to_atr_20"}:
        return "execution_quality_filter"
    if feature_text in {
        "tick_volume_avg_20",
        "tick_volume_ratio_20",
        "tick_volume_zscore_100",
        "tick_volume_percentile_100",
        "volume_spike_20",
        "volume_dry_up_20",
        "volume_vs_hour_avg",
        "volume_vs_session_avg",
    }:
        return "volume_liquidity_filter"
    if feature_text in {"hour", "hour_session"}:
        return "session_filter"
    if feature_text == "day_of_week":
        return "calendar_filter"
    if (
        feature_text.startswith("blackout_window_")
        or feature_text.startswith("post_news_window_")
        or feature_text.startswith("has_news_")
        or feature_text.startswith("has_high_impact_news_")
        or feature_text.startswith("minutes_to_next_news")
        or feature_text.startswith("minutes_from_last_news")
    ):
        return "news_risk_filter"
    return "context_filter"


def tradability_note_for(rule_role: str, feature: object, exclusion_reason: object = "") -> str:
    feature_text = str(feature or "")
    exclusion_text = str(exclusion_reason or "")
    if rule_role == "not_tradable_alone":
        if "numeric_tercile" in exclusion_text:
            return "Not tradable alone; numeric_tercile buckets remain excluded until thresholds are computed train-only."
        if "raw_price_level_excluded" in exclusion_text or feature_text.lower() in RAW_PRICE_FEATURES:
            return "Not tradable alone; raw price levels are excluded because absolute scales differ across symbols."
        return "Not tradable alone; keep as research context until converted into a time-safe rule."
    if rule_role in {"trend_filter", "momentum_filter", "entry_bias"}:
        return "Potential entry or directional-bias ingredient for future rule-based backtests; not a complete strategy."
    if rule_role == "news_risk_filter":
        return "Risk or news-context filter for future rule-based backtests; not standalone entry logic."
    if rule_role == "volume_liquidity_filter":
        return "Volume/liquidity context filter; should confirm or filter another setup, not define direction alone."
    if rule_role == "execution_quality_filter":
        return "Execution or liquidity-quality filter for future rule-based backtests; not alpha by itself."
    return "Context filter for future rule-based backtests; combine with explicit entry, exit, cost, and risk rules."


def add_points(condition: bool, points: int, notes: list[str], text: str) -> tuple[int, int, int]:
    if not condition:
        return 0, 0, 0
    notes.append(f"{text} ({points:+d})")
    if points > 0:
        return points, points, 0
    return points, 0, points


def score_validation_row(row: dict[str, str], min_trades_per_year: int) -> tuple[int, int, int, list[str]]:
    score = 0
    bonus_points = 0
    penalty_points = 0
    notes: list[str] = []

    classification = (row.get("final_classification") or "").strip().lower()
    for condition, points, text in (
        (classification == "select", 3, "classification select"),
        (classification == "watchlist", 2, "classification watchlist"),
        (classification == "reject", -3, "classification reject"),
    ):
        delta, bonus, penalty = add_points(condition, points, notes, text)
        score += delta
        bonus_points += bonus
        penalty_points += penalty

    positive_year_ratio = to_float(row.get("positive_year_ratio"))
    if positive_year_ratio is not None:
        if positive_year_ratio >= 0.75:
            delta, bonus, penalty = add_points(True, 2, notes, "positive_year_ratio >= 0.75")
        elif positive_year_ratio >= 0.50:
            delta, bonus, penalty = add_points(True, 1, notes, "positive_year_ratio >= 0.50")
        else:
            delta, bonus, penalty = add_points(True, -2, notes, "positive_year_ratio < 0.50")
        score += delta
        bonus_points += bonus
        penalty_points += penalty

    positive_symbol_ratio = to_float(row.get("positive_symbol_ratio"))
    if positive_symbol_ratio is not None:
        if positive_symbol_ratio >= 0.75:
            delta, bonus, penalty = add_points(True, 2, notes, "positive_symbol_ratio >= 0.75")
        elif positive_symbol_ratio >= 0.50:
            delta, bonus, penalty = add_points(True, 1, notes, "positive_symbol_ratio >= 0.50")
        else:
            delta, bonus, penalty = add_points(True, -2, notes, "positive_symbol_ratio < 0.50")
        score += delta
        bonus_points += bonus
        penalty_points += penalty

    avg_pf = to_float(row.get("avg_profit_factor_improvement_pct"))
    if avg_pf is not None:
        if avg_pf >= 5:
            delta, bonus, penalty = add_points(True, 2, notes, "avg_profit_factor_improvement_pct >= 5")
        elif avg_pf > 0:
            delta, bonus, penalty = add_points(True, 1, notes, "avg_profit_factor_improvement_pct > 0")
        elif avg_pf < 0:
            delta, bonus, penalty = add_points(True, -2, notes, "avg_profit_factor_improvement_pct < 0")
        else:
            delta = bonus = penalty = 0
        score += delta
        bonus_points += bonus
        penalty_points += penalty

    avg_dd = to_float(row.get("avg_max_drawdown_improvement_pct"))
    if avg_dd is not None:
        if avg_dd >= 10:
            delta, bonus, penalty = add_points(True, 2, notes, "avg_max_drawdown_improvement_pct >= 10")
        elif avg_dd >= 0:
            delta, bonus, penalty = add_points(True, 1, notes, "avg_max_drawdown_improvement_pct >= 0")
        else:
            delta, bonus, penalty = add_points(True, -2, notes, "avg_max_drawdown_improvement_pct < 0")
        score += delta
        bonus_points += bonus
        penalty_points += penalty

    avg_trades = to_float(row.get("avg_trades_per_year"))
    min_trades = to_float(row.get("min_trades_in_any_year"))
    delta, bonus, penalty = add_points(
        avg_trades is not None and avg_trades >= min_trades_per_year,
        1,
        notes,
        "avg_trades_per_year >= min_trades_per_year",
    )
    score += delta
    bonus_points += bonus
    penalty_points += penalty

    delta, bonus, penalty = add_points(
        min_trades is not None and min_trades < min_trades_per_year,
        -2,
        notes,
        "min_trades_in_any_year < min_trades_per_year",
    )
    score += delta
    bonus_points += bonus
    penalty_points += penalty

    worst_dd = to_float(row.get("worst_year_drawdown_improvement_pct"))
    delta, bonus, penalty = add_points(
        worst_dd is not None and worst_dd < -25,
        -3,
        notes,
        "worst_year_drawdown_improvement_pct < -25",
    )
    score += delta
    bonus_points += bonus
    penalty_points += penalty

    worst_pf = to_float(row.get("worst_year_profit_factor_improvement_pct"))
    delta, bonus, penalty = add_points(
        worst_pf is not None and worst_pf < -10,
        -3,
        notes,
        "worst_year_profit_factor_improvement_pct < -10",
    )
    score += delta
    bonus_points += bonus
    penalty_points += penalty

    for risk in concentration_penalties(row):
        delta, bonus, penalty = add_points(True, -1, notes, risk)
        score += delta
        bonus_points += bonus
        penalty_points += penalty

    return score, bonus_points, penalty_points, notes


def empty_aggregate(parsed: ParsedCondition) -> dict[str, object]:
    return {
        "feature": parsed.feature,
        "condition": parsed.condition,
        "feature_condition_key": parsed.key,
        "direction": "",
        "cost_mode": "",
        "return_mode": "",
        "total_score": 0,
        "bonus_points": 0,
        "penalty_points": 0,
        "appears_in_select_count": 0,
        "appears_in_watchlist_count": 0,
        "appears_in_reject_count": 0,
        "positive_year_ratios": [],
        "positive_symbol_ratios": [],
        "avg_trades_values": [],
        "min_trades_values": [],
        "avg_pf_values": [],
        "median_pf_values": [],
        "avg_dd_values": [],
        "worst_pf_values": [],
        "worst_dd_values": [],
        "monthly_positive_ratios": [],
        "quarterly_positive_ratios": [],
        "best_month_contribution_pcts": [],
        "top_5_percent_trades_contribution_pcts": [],
        "max_flat_period_bars_values": [],
        "ml_support": "none",
        "backtest_support": "none",
        "exclusion_reasons": set(),
        "notes": set(),
    }


def ensure_aggregate(
    aggregates: dict[str, dict[str, object]],
    parsed: ParsedCondition,
) -> dict[str, object]:
    if parsed.key not in aggregates:
        aggregates[parsed.key] = empty_aggregate(parsed)
    return aggregates[parsed.key]


def add_validation_row(
    aggregate: dict[str, object],
    row: dict[str, str],
    row_score: int,
    row_bonus: int,
    row_penalty: int,
    row_notes: list[str],
) -> None:
    aggregate["total_score"] = int(aggregate["total_score"]) + row_score
    aggregate["bonus_points"] = int(aggregate["bonus_points"]) + row_bonus
    aggregate["penalty_points"] = int(aggregate["penalty_points"]) + row_penalty

    classification = (row.get("final_classification") or "").strip().lower()
    if classification == "select":
        aggregate["appears_in_select_count"] = int(aggregate["appears_in_select_count"]) + 1
    elif classification == "watchlist":
        aggregate["appears_in_watchlist_count"] = int(aggregate["appears_in_watchlist_count"]) + 1
    elif classification == "reject":
        aggregate["appears_in_reject_count"] = int(aggregate["appears_in_reject_count"]) + 1

    for source_key, target_key in (
        ("positive_year_ratio", "positive_year_ratios"),
        ("positive_symbol_ratio", "positive_symbol_ratios"),
        ("avg_trades_per_year", "avg_trades_values"),
        ("min_trades_in_any_year", "min_trades_values"),
        ("avg_profit_factor_improvement_pct", "avg_pf_values"),
        ("median_profit_factor_improvement_pct", "median_pf_values"),
        ("avg_max_drawdown_improvement_pct", "avg_dd_values"),
        ("worst_year_profit_factor_improvement_pct", "worst_pf_values"),
        ("worst_year_drawdown_improvement_pct", "worst_dd_values"),
        ("monthly_positive_ratio", "monthly_positive_ratios"),
        ("quarterly_positive_ratio", "quarterly_positive_ratios"),
        ("best_month_contribution_pct", "best_month_contribution_pcts"),
        ("top_5_percent_trades_contribution_pct", "top_5_percent_trades_contribution_pcts"),
        ("max_flat_period_bars", "max_flat_period_bars_values"),
    ):
        parsed_value = to_float(row.get(source_key))
        if parsed_value is not None:
            aggregate[target_key].append(parsed_value)  # type: ignore[index]

    aggregate["notes"].update(row_notes)  # type: ignore[union-attr]


def load_ml_support(path: Path, warnings: list[str]) -> set[str]:
    rows = read_optional_csv(path, warnings)
    supported = set()
    for row in rows:
        feature = (row.get("feature") or "").strip()
        interpretation = (row.get("interpretation") or "").strip().lower()
        strong_count = to_int(row.get("strong_count"))
        interesting_count = to_int(row.get("interesting_count"))
        if feature and (interpretation in POSITIVE_ML_LABELS or strong_count > 0 or interesting_count > 0):
            supported.add(feature)
    return supported


def load_backtest_support(
    cross_pair_path: Path,
    evaluated_path: Path,
    warnings: list[str],
    *,
    cost_mode: str,
    return_mode: str,
) -> tuple[set[str], set[str]]:
    cross_rows = filter_rows_by_modes(
        read_optional_csv(cross_pair_path, warnings),
        cost_mode=cost_mode,
        return_mode=return_mode,
        source=str(cross_pair_path),
        warnings=warnings,
    )
    evaluated_rows = filter_rows_by_modes(
        read_optional_csv(evaluated_path, warnings),
        cost_mode=cost_mode,
        return_mode=return_mode,
        source=str(evaluated_path),
        warnings=warnings,
    )
    cross_supported = set()
    evaluated_supported = set()

    for row in cross_rows:
        label = (row.get("robustness_label") or "").strip().lower()
        avg_score = to_float(row.get("avg_score"))
        has_label = bool(label)
        if has_label and label not in POSITIVE_BACKTEST_LABELS:
            continue
        if not has_label and (avg_score is None or avg_score <= 0):
            continue
        scenario_key = row.get("scenario_key") or ""
        for parsed in parse_combination(scenario_key, source=str(cross_pair_path), warnings=warnings):
            cross_supported.add(parsed.feature)

    for row in evaluated_rows:
        classification = (row.get("classification") or "").strip().lower()
        if classification not in {"strong", "interesting"}:
            continue
        scenario_key = row.get("scenario_key") or row.get("scenario") or ""
        for parsed in parse_combination(scenario_key, source=str(evaluated_path), warnings=warnings):
            evaluated_supported.add(parsed.feature)

    return cross_supported, evaluated_supported


def apply_support_bonus(
    aggregates: dict[str, dict[str, object]],
    *,
    ml_supported_features: set[str],
    cross_backtest_supported_features: set[str],
    evaluated_backtest_supported_features: set[str],
) -> None:
    for aggregate in aggregates.values():
        feature = str(aggregate["feature"])
        notes = aggregate["notes"]  # type: ignore[assignment]
        if feature in ml_supported_features:
            aggregate["ml_support"] = "strong_or_interesting"
            aggregate["total_score"] = int(aggregate["total_score"]) + 1
            aggregate["bonus_points"] = int(aggregate["bonus_points"]) + 1
            notes.add("ML aggregate support (+1)")

        if feature in cross_backtest_supported_features:
            aggregate["backtest_support"] = "cross_pair_positive"
            aggregate["total_score"] = int(aggregate["total_score"]) + 1
            aggregate["bonus_points"] = int(aggregate["bonus_points"]) + 1
            notes.add("cross-pair backtest support (+1)")
        elif feature in evaluated_backtest_supported_features:
            aggregate["backtest_support"] = "evaluated_positive"
            notes.add("evaluated backtest support observed")


def classification_for(aggregate: dict[str, object]) -> str:
    if aggregate["exclusion_reasons"]:  # type: ignore[index]
        return "excluded"

    avg_year_ratio = average(aggregate["positive_year_ratios"])  # type: ignore[arg-type]
    avg_symbol_ratio = average(aggregate["positive_symbol_ratios"])  # type: ignore[arg-type]
    avg_dd = average(aggregate["avg_dd_values"])  # type: ignore[arg-type]
    has_select = int(aggregate["appears_in_select_count"]) > 0
    total_score = int(aggregate["total_score"])

    if (
        total_score >= 8
        and has_select
        and avg_year_ratio is not None
        and avg_year_ratio >= 0.75
        and avg_symbol_ratio is not None
        and avg_symbol_ratio >= 0.75
        and avg_dd is not None
        and avg_dd >= 0
    ):
        return "strong"
    if total_score > 0:
        return "interesting"
    return "weak"


def finalize_rows(aggregates: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for aggregate in aggregates.values():
        exclusion_reason = "; ".join(sorted(aggregate["exclusion_reasons"]))  # type: ignore[arg-type]
        notes = "; ".join(sorted(aggregate["notes"]))  # type: ignore[arg-type]
        rule_role = rule_role_for(aggregate["feature"], aggregate["condition"], exclusion_reason)
        rows.append(
            {
                "feature": aggregate["feature"],
                "condition": aggregate["condition"],
                "feature_condition_key": aggregate["feature_condition_key"],
                "rule_role": rule_role,
                "tradability_note": tradability_note_for(rule_role, aggregate["feature"], exclusion_reason),
                "direction": aggregate["direction"],
                "cost_mode": aggregate["cost_mode"],
                "return_mode": aggregate["return_mode"],
                "total_score": aggregate["total_score"],
                "final_feature_classification": classification_for(aggregate),
                "appears_in_select_count": aggregate["appears_in_select_count"],
                "appears_in_watchlist_count": aggregate["appears_in_watchlist_count"],
                "appears_in_reject_count": aggregate["appears_in_reject_count"],
                "avg_positive_year_ratio": average(aggregate["positive_year_ratios"]),  # type: ignore[arg-type]
                "avg_positive_symbol_ratio": average(aggregate["positive_symbol_ratios"]),  # type: ignore[arg-type]
                "avg_trades_per_year": average(aggregate["avg_trades_values"]),  # type: ignore[arg-type]
                "min_trades_in_any_year": minimum(aggregate["min_trades_values"]),  # type: ignore[arg-type]
                "avg_profit_factor_improvement_pct": average(aggregate["avg_pf_values"]),  # type: ignore[arg-type]
                "median_profit_factor_improvement_pct": median_value(aggregate["median_pf_values"]),  # type: ignore[arg-type]
                "avg_max_drawdown_improvement_pct": average(aggregate["avg_dd_values"]),  # type: ignore[arg-type]
                "worst_year_profit_factor_improvement_pct": minimum(aggregate["worst_pf_values"]),  # type: ignore[arg-type]
                "worst_year_drawdown_improvement_pct": minimum(aggregate["worst_dd_values"]),  # type: ignore[arg-type]
                "monthly_positive_ratio": average(aggregate["monthly_positive_ratios"]),  # type: ignore[arg-type]
                "quarterly_positive_ratio": average(aggregate["quarterly_positive_ratios"]),  # type: ignore[arg-type]
                "best_month_contribution_pct": maximum(aggregate["best_month_contribution_pcts"]),  # type: ignore[arg-type]
                "top_5_percent_trades_contribution_pct": maximum(aggregate["top_5_percent_trades_contribution_pcts"]),  # type: ignore[arg-type]
                "max_flat_period_bars": maximum(aggregate["max_flat_period_bars_values"]),  # type: ignore[arg-type]
                "ml_support": aggregate["ml_support"],
                "backtest_support": aggregate["backtest_support"],
                "penalty_points": aggregate["penalty_points"],
                "bonus_points": aggregate["bonus_points"],
                "exclusion_reason": exclusion_reason,
                "notes": notes,
            }
        )

    class_order = {"strong": 0, "interesting": 1, "weak": 2, "excluded": 3}
    rows.sort(
        key=lambda row: (
            class_order.get(str(row["final_feature_classification"]), 99),
            -int(row["total_score"]),
            str(row["feature_condition_key"]),
        )
    )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in CSV_FIELDS})


def empty_pair_specific_aggregate(
    symbol: str,
    parsed: ParsedCondition,
    direction: str,
    cost_mode: str,
    return_mode: str,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "feature": parsed.feature,
        "condition": parsed.condition,
        "direction": direction,
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "feature_condition_key": parsed.key,
        "pair_specific_score_values": [],
        "appears_in_select_pair_specific_count": 0,
        "appears_in_watchlist_pair_specific_count": 0,
        "positive_year_ratios": [],
        "avg_trades_values": [],
        "avg_pf_values": [],
        "avg_dd_values": [],
        "monthly_positive_ratios": [],
        "quarterly_positive_ratios": [],
        "best_month_contribution_pcts": [],
        "top_5_percent_trades_contribution_pcts": [],
        "max_flat_period_bars_values": [],
        "notes": set(),
    }


def build_pair_specific_feature_scorecard(
    pair_specific_rows: list[dict[str, str]],
    *,
    direction: str,
    cost_mode: str,
    return_mode: str,
    warnings: list[str],
) -> list[dict[str, object]]:
    aggregates: dict[tuple[str, str], dict[str, object]] = {}
    for row in pair_specific_rows:
        row_direction = normalize_direction(row.get("direction", "long"))
        if row_direction != direction:
            continue
        symbol = (row.get("symbol") or "").strip().upper()
        combination_key = row.get("combination_key") or ""
        if not symbol:
            warnings.append(f"Pair-specific row without symbol skipped: {combination_key!r}")
            continue

        parsed_conditions = parse_combination(
            combination_key,
            source=PAIR_SPECIFIC_CANDIDATES_FILE,
            warnings=warnings,
        )
        unique_conditions = {condition.key: condition for condition in parsed_conditions}.values()
        classification = (row.get("pair_specific_classification") or "").strip()
        for parsed in unique_conditions:
            key = (symbol, parsed.key)
            if key not in aggregates:
                aggregates[key] = empty_pair_specific_aggregate(symbol, parsed, direction, cost_mode, return_mode)
            aggregate = aggregates[key]
            aggregate["pair_specific_score_values"].append(to_float(row.get("pair_specific_score")) or 0)  # type: ignore[index]
            if classification == "select_pair_specific":
                aggregate["appears_in_select_pair_specific_count"] = int(
                    aggregate["appears_in_select_pair_specific_count"]
                ) + 1
            elif classification == "watchlist_pair_specific":
                aggregate["appears_in_watchlist_pair_specific_count"] = int(
                    aggregate["appears_in_watchlist_pair_specific_count"]
                ) + 1
            for source_key, target_key in (
                ("positive_year_ratio", "positive_year_ratios"),
                ("avg_trades_per_year", "avg_trades_values"),
                ("avg_profit_factor_improvement_pct", "avg_pf_values"),
                ("avg_max_drawdown_improvement_pct", "avg_dd_values"),
                ("monthly_positive_ratio", "monthly_positive_ratios"),
                ("quarterly_positive_ratio", "quarterly_positive_ratios"),
                ("best_month_contribution_pct", "best_month_contribution_pcts"),
                ("top_5_percent_trades_contribution_pct", "top_5_percent_trades_contribution_pcts"),
                ("max_flat_period_bars", "max_flat_period_bars_values"),
            ):
                parsed_value = to_float(row.get(source_key))
                if parsed_value is not None:
                    aggregate[target_key].append(parsed_value)  # type: ignore[index]
            notes = row.get("notes")
            if notes:
                aggregate["notes"].add(notes)  # type: ignore[union-attr]

    output_rows = []
    for aggregate in aggregates.values():
        select_count = int(aggregate["appears_in_select_pair_specific_count"])
        watchlist_count = int(aggregate["appears_in_watchlist_pair_specific_count"])
        scores = aggregate["pair_specific_score_values"]  # type: ignore[assignment]
        total_score = sum(float(value) for value in scores)
        avg_year_ratio = average(aggregate["positive_year_ratios"])  # type: ignore[arg-type]
        avg_dd = average(aggregate["avg_dd_values"])  # type: ignore[arg-type]
        if select_count > 0 and avg_year_ratio is not None and avg_year_ratio >= 0.75 and avg_dd is not None and avg_dd >= 0:
            classification = "strong_pair_specific"
        elif select_count > 0 or watchlist_count > 0 or total_score > 0:
            classification = "interesting_pair_specific"
        else:
            classification = "weak_pair_specific"
        rule_role = rule_role_for(aggregate["feature"], aggregate["condition"])
        output_rows.append(
            {
                "symbol": aggregate["symbol"],
                "feature": aggregate["feature"],
                "condition": aggregate["condition"],
                "direction": aggregate["direction"],
                "cost_mode": aggregate["cost_mode"],
                "return_mode": aggregate["return_mode"],
                "feature_condition_key": aggregate["feature_condition_key"],
                "rule_role": rule_role,
                "tradability_note": tradability_note_for(rule_role, aggregate["feature"]),
                "pair_specific_score": total_score,
                "pair_specific_classification": classification,
                "appears_in_select_pair_specific_count": select_count,
                "appears_in_watchlist_pair_specific_count": watchlist_count,
                "avg_positive_year_ratio": avg_year_ratio,
                "avg_trades_per_year": average(aggregate["avg_trades_values"]),  # type: ignore[arg-type]
                "avg_profit_factor_improvement_pct": average(aggregate["avg_pf_values"]),  # type: ignore[arg-type]
                "avg_max_drawdown_improvement_pct": avg_dd,
                "monthly_positive_ratio": average(aggregate["monthly_positive_ratios"]),  # type: ignore[arg-type]
                "quarterly_positive_ratio": average(aggregate["quarterly_positive_ratios"]),  # type: ignore[arg-type]
                "best_month_contribution_pct": maximum(aggregate["best_month_contribution_pcts"]),  # type: ignore[arg-type]
                "top_5_percent_trades_contribution_pct": maximum(aggregate["top_5_percent_trades_contribution_pcts"]),  # type: ignore[arg-type]
                "max_flat_period_bars": maximum(aggregate["max_flat_period_bars_values"]),  # type: ignore[arg-type]
                "notes": "; ".join(sorted(aggregate["notes"])),  # type: ignore[arg-type]
            }
        )

    class_order = {
        "strong_pair_specific": 0,
        "interesting_pair_specific": 1,
        "weak_pair_specific": 2,
    }
    output_rows.sort(
        key=lambda row: (
            str(row["symbol"]),
            class_order.get(str(row["pair_specific_classification"]), 99),
            -float(row["pair_specific_score"] or 0),
            str(row["feature_condition_key"]),
        )
    )
    return output_rows


def write_pair_specific_scorecard(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=PAIR_SPECIFIC_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in PAIR_SPECIFIC_CSV_FIELDS})


def format_number(value: object, digits: int = 2) -> str:
    parsed = to_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.{digits}f}"


def rows_for_roles(rows: list[dict[str, object]], roles: set[str]) -> list[dict[str, object]]:
    return [row for row in rows if str(row.get("rule_role", "")) in roles]


def not_tradable_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        row for row in rows
        if str(row.get("rule_role", "")) == "not_tradable_alone"
        or str(row.get("final_feature_classification", "")) == "excluded"
    ]


def report_section(title: str, rows: list[dict[str, object]], limit: int = 20) -> list[str]:
    lines = [f"## {title}", ""]
    if not rows:
        lines.extend(["- none", ""])
        return lines
    for row in rows[:limit]:
        lines.append(
            "- {key}: role={role}, class={classification}, score={score}, year_ratio={year_ratio}, "
            "symbol_ratio={symbol_ratio}, avg_dd={avg_dd}, avg_pf={avg_pf}, "
            "monthly_pos={monthly}, best_month_pct={best_month}, top5_trade_pct={top_trades}; {note}".format(
                key=row["feature_condition_key"],
                role=row.get("rule_role", "context_filter"),
                classification=row["final_feature_classification"],
                score=row["total_score"],
                year_ratio=format_number(row["avg_positive_year_ratio"]),
                symbol_ratio=format_number(row["avg_positive_symbol_ratio"]),
                avg_dd=format_number(row["avg_max_drawdown_improvement_pct"]),
                avg_pf=format_number(row["avg_profit_factor_improvement_pct"]),
                monthly=format_number(row.get("monthly_positive_ratio")),
                best_month=format_number(row.get("best_month_contribution_pct")),
                top_trades=format_number(row.get("top_5_percent_trades_contribution_pct")),
                note=row.get("tradability_note", ""),
            )
        )
    lines.append("")
    return lines


def pair_specific_report_section(title: str, rows: list[dict[str, object]], limit: int = 20) -> list[str]:
    lines = [f"## {title}", ""]
    if not rows:
        lines.extend(["- none", ""])
        return lines
    for row in rows[:limit]:
        lines.append(
            "- {symbol} {key}: role={role}, class={classification}, score={score}, year_ratio={year_ratio}, "
            "avg_dd={avg_dd}, avg_pf={avg_pf}, trades={trades}, monthly_pos={monthly}, "
            "best_month_pct={best_month}, top5_trade_pct={top_trades}".format(
                symbol=row["symbol"],
                key=row["feature_condition_key"],
                role=row.get("rule_role", "context_filter"),
                classification=row["pair_specific_classification"],
                score=format_number(row["pair_specific_score"], 1),
                year_ratio=format_number(row["avg_positive_year_ratio"]),
                avg_dd=format_number(row["avg_max_drawdown_improvement_pct"]),
                avg_pf=format_number(row["avg_profit_factor_improvement_pct"]),
                trades=format_number(row["avg_trades_per_year"], 1),
                monthly=format_number(row.get("monthly_positive_ratio")),
                best_month=format_number(row.get("best_month_contribution_pct")),
                top_trades=format_number(row.get("top_5_percent_trades_contribution_pct")),
            )
        )
    lines.append("")
    return lines


def write_report(
    path: Path,
    rows: list[dict[str, object]],
    pair_specific_rows: list[dict[str, object]],
    *,
    run_id: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
    input_paths: dict[str, Path],
    final_candidates_count: int,
    validation_summary_count: int,
    validation_detail_count: int,
    pair_specific_count: int,
    selected_combined_count: int,
    skipped_count: int,
    min_trades_per_year: int,
    warnings: list[str],
) -> None:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["final_feature_classification"])].append(row)
    pair_grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in pair_specific_rows:
        pair_grouped[str(row["pair_specific_classification"])].append(row)
    entry_bias_rows = rows_for_roles(rows, {"entry_bias", "momentum_filter", "trend_filter"})
    context_rows = rows_for_roles(rows, {"session_filter", "calendar_filter", "volatility_regime_filter", "context_filter"})
    risk_news_rows = rows_for_roles(rows, {"news_risk_filter"})
    execution_quality_rows = rows_for_roles(rows, {"execution_quality_filter", "volume_liquidity_filter"})
    excluded_role_rows = not_tradable_rows(rows)

    lines = [
        "# Final Feature Scorecard",
        "",
        "This is an offline research-only aggregation report. It does not create operational instructions and does not use order execution APIs.",
        "",
        "Feature scorecard entries are ingredients for future rule-based backtests, not standalone trading strategies.",
        "",
        "## Executive Summary",
        "",
        f"- Run ID: {run_id}",
        f"- Direction: {direction}",
        f"- Cost mode: {cost_mode}",
        f"- Return mode: {return_mode}",
        f"- Ranking basis: {'Ranking based on estimated net returns.' if return_mode == 'net' else 'Ranking based on gross returns.'}",
        f"- Focus: best {direction} features and conditions",
        f"- Cross-pair feature/condition rows: {len(rows)}",
        f"- Pair-specific feature/condition rows: {len(pair_specific_rows)}",
        f"- Strong: {len(grouped['strong'])}",
        f"- Interesting: {len(grouped['interesting'])}",
        f"- Weak: {len(grouped['weak'])}",
        f"- Excluded: {len(grouped['excluded'])}",
        f"- Potential entry/bias rows: {len(entry_bias_rows)}",
        f"- Context filter rows: {len(context_rows)}",
        f"- Risk/news filter rows: {len(risk_news_rows)}",
        f"- Execution-quality filter rows: {len(execution_quality_rows)}",
        f"- Not tradable alone / excluded rows: {len(excluded_role_rows)}",
        f"- Strong pair-specific: {len(pair_grouped['strong_pair_specific'])}",
        f"- Interesting pair-specific: {len(pair_grouped['interesting_pair_specific'])}",
        f"- Weak pair-specific: {len(pair_grouped['weak_pair_specific'])}",
        f"- Validation candidates read: {final_candidates_count}",
        f"- Validation summary rows read: {validation_summary_count}",
        f"- Validation detail rows read: {validation_detail_count}",
        f"- Pair-specific candidate rows read: {pair_specific_count}",
        f"- Selected combined hypotheses read: {selected_combined_count}",
        f"- Skipped hypotheses read: {skipped_count}",
        f"- Minimum trades per year used for score penalties: {min_trades_per_year}",
        "",
        "## Inputs",
        "",
    ]
    for label, input_path in input_paths.items():
        lines.append(f"- {label}: {input_path}")
    lines.append("")

    lines.extend(["# Cross-Pair Feature Scorecard By Rule Role", ""])
    lines.extend(report_section("Potential Entry/Bias Features", entry_bias_rows))
    lines.extend(report_section("Context Filters", context_rows))
    lines.extend(report_section("Risk/News Filters", risk_news_rows))
    lines.extend(report_section("Execution-Quality Filters", execution_quality_rows))
    lines.extend(report_section("Not Tradable Alone / Excluded", excluded_role_rows))

    lines.extend(["# Pair-Specific Feature Scorecard", ""])
    lines.extend(pair_specific_report_section("Strong Pair-Specific Features", pair_grouped["strong_pair_specific"]))
    lines.extend(pair_specific_report_section("Interesting Pair-Specific Features", pair_grouped["interesting_pair_specific"]))
    lines.extend(pair_specific_report_section("Weak Pair-Specific Features", pair_grouped["weak_pair_specific"]))

    lines.extend(["## Warnings", ""])
    if warnings:
        for warning in warnings[:80]:
            lines.append(f"- {warning}")
        if len(warnings) > 80:
            lines.append(f"- Additional warnings omitted: {len(warnings) - 80}")
    else:
        lines.append("- none")
    lines.append("")

    lines.extend(
        [
            "## Interpretation",
            "",
            "- `strong` means the feature/condition scored well, appeared in at least one selected yearly candidate, had average positive year and symbol ratios of at least 0.75, and did not worsen average drawdown.",
            "- `interesting` means the score is positive but stability is not strong enough for the top tier.",
            "- `weak` means the evidence is mixed or negative.",
            "- `excluded` means the condition uses raw price levels or a non time-safe `numeric_tercile` bucket and should not be promoted from this scorecard.",
            "- `rule_role` describes how the row might be used as an ingredient: bias, context, risk/news, execution quality, or not tradable alone.",
            "- Performance concentration metrics act as penalties for fragile results; they do not promote a feature by themselves.",
            "- Pair-specific scores are separate from cross-pair scores and should not be generalized to other symbols.",
            "- Scores are research ranking aids, not trading rules.",
            "",
            "## Next Research-Only Action",
            "",
            "- Use the strongest and most interpretable rows as candidates for a future separate rule-based backtest with explicit spread, cost, slippage, sample-size, and risk-model assumptions.",
            "- Do not convert this scorecard into operational instructions or execution logic.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def latest_run_id(validation_dir: Path, direction: str) -> str:
    if not validation_dir.exists():
        raise FileNotFoundError(f"Validation directory not found: {validation_dir}")
    candidates = [
        path
        for path in validation_dir.iterdir()
        if path.is_dir()
        and (path / direction / FINAL_CANDIDATES_FILE).exists()
        and (path / direction / VALIDATION_SUMMARY_FILE).exists()
    ]
    if direction == "long":
        candidates.extend(
            path
            for path in validation_dir.iterdir()
            if path.is_dir()
            and (path / FINAL_CANDIDATES_FILE).exists()
            and (path / VALIDATION_SUMMARY_FILE).exists()
        )
    if not candidates:
        raise FileNotFoundError(
            f"No validation runs with {FINAL_CANDIDATES_FILE} and {VALIDATION_SUMMARY_FILE} found under {validation_dir}."
        )
    return sorted(candidates, key=lambda path: path.name)[-1].name


def validate_required_paths(paths: dict[str, Path]) -> None:
    missing = [f"{label}: {path}" for label, path in paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("Required input files are missing:\n" + "\n".join(missing))


def ensure_output_paths(output_dir: Path, overwrite: bool) -> tuple[Path, Path, Path]:
    scorecard_path = output_dir / OUTPUT_SCORECARD
    pair_specific_path = output_dir / OUTPUT_PAIR_SPECIFIC_SCORECARD
    report_path = output_dir / OUTPUT_REPORT
    existing = [path for path in (scorecard_path, pair_specific_path, report_path) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Final feature scorecard output already exists under {output_dir}. "
            "Pass --overwrite to regenerate it."
        )
    return scorecard_path, pair_specific_path, report_path


def build_scorecard(args: argparse.Namespace) -> Path:
    direction = normalize_direction(args.direction)
    cost_mode = normalized_cost_mode(args.cost_mode)
    return_mode = normalized_return_mode(args.return_mode)
    run_id = args.run_id.strip() if args.run_id else latest_run_id(args.validation_dir, direction)
    if not run_id:
        raise ValueError("--run-id cannot be empty.")

    validation_run_dir = Path(args.validation_dir) / run_id / direction
    combined_run_dir = Path(args.combined_evaluations_dir) / run_id / direction
    output_run_dir = Path(args.output_dir) / run_id / direction
    if direction == "long" and not (validation_run_dir / FINAL_CANDIDATES_FILE).exists():
        legacy_validation_dir = Path(args.validation_dir) / run_id
        if (legacy_validation_dir / FINAL_CANDIDATES_FILE).exists():
            validation_run_dir = legacy_validation_dir
    if direction == "long" and not (combined_run_dir / SELECTED_COMBINED_FILE).exists():
        legacy_combined_dir = Path(args.combined_evaluations_dir) / run_id
        if (legacy_combined_dir / SELECTED_COMBINED_FILE).exists():
            combined_run_dir = legacy_combined_dir

    required_paths = {
        "final_research_candidates": validation_run_dir / FINAL_CANDIDATES_FILE,
        "by_year_validation_summary": validation_run_dir / VALIDATION_SUMMARY_FILE,
        "by_year_validation_detail": validation_run_dir / VALIDATION_DETAIL_FILE,
        "selected_combined_hypotheses": combined_run_dir / SELECTED_COMBINED_FILE,
    }
    pair_specific_candidates_path = validation_run_dir / PAIR_SPECIFIC_CANDIDATES_FILE
    validate_required_paths(required_paths)
    scorecard_path, pair_specific_scorecard_path, report_path = ensure_output_paths(output_run_dir, args.overwrite)

    warnings: list[str] = []
    final_candidates = read_csv_dicts(required_paths["final_research_candidates"])
    validation_summary = read_csv_dicts(required_paths["by_year_validation_summary"])
    validation_detail = read_csv_dicts(required_paths["by_year_validation_detail"])
    pair_specific_candidates = (
        read_csv_dicts(pair_specific_candidates_path)
        if pair_specific_candidates_path.exists()
        else []
    )
    if not pair_specific_candidates_path.exists():
        warnings.append(f"Optional pair-specific candidates file not found: {pair_specific_candidates_path}")
    selected_combined = read_csv_dicts(required_paths["selected_combined_hypotheses"])

    skipped_path = validation_run_dir / SKIPPED_HYPOTHESES_FILE
    skipped_hypotheses = read_csv_dicts(skipped_path) if skipped_path.exists() else []
    if not skipped_path.exists():
        warnings.append(f"Optional skipped hypotheses file not found: {skipped_path}")

    final_candidates = filter_rows_by_modes(
        final_candidates,
        cost_mode=cost_mode,
        return_mode=return_mode,
        source=str(required_paths["final_research_candidates"]),
        warnings=warnings,
    )
    validation_summary = filter_rows_by_modes(
        validation_summary,
        cost_mode=cost_mode,
        return_mode=return_mode,
        source=str(required_paths["by_year_validation_summary"]),
        warnings=warnings,
    )
    validation_detail = filter_rows_by_modes(
        validation_detail,
        cost_mode=cost_mode,
        return_mode=return_mode,
        source=str(required_paths["by_year_validation_detail"]),
        warnings=warnings,
    )
    pair_specific_candidates = filter_rows_by_modes(
        pair_specific_candidates,
        cost_mode=cost_mode,
        return_mode=return_mode,
        source=str(pair_specific_candidates_path),
        warnings=warnings,
    )
    selected_combined = filter_rows_by_modes(
        selected_combined,
        cost_mode=cost_mode,
        return_mode=return_mode,
        source=str(required_paths["selected_combined_hypotheses"]),
        warnings=warnings,
    )
    skipped_hypotheses = filter_rows_by_modes(
        skipped_hypotheses,
        cost_mode=cost_mode,
        return_mode=return_mode,
        source=str(skipped_path),
        warnings=warnings,
    )

    ml_support_path = Path(args.ml_research_dir) / direction / AGGREGATE_FEATURE_RANKING_FILE
    if direction == "long" and not ml_support_path.exists():
        legacy_ml_support_path = Path(args.ml_research_dir) / AGGREGATE_FEATURE_RANKING_FILE
        if legacy_ml_support_path.exists():
            ml_support_path = legacy_ml_support_path
    ml_support = load_ml_support(ml_support_path, warnings)
    cross_support, evaluated_support = load_backtest_support(
        Path(args.backtests_dir) / direction / CROSS_PAIR_SUMMARY_FILE,
        Path(args.backtests_dir) / direction / EVALUATED_BACKTEST_RESULTS_FILE,
        warnings,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )

    aggregates: dict[str, dict[str, object]] = {}
    scored_condition_keys: set[str] = set()

    for row in validation_summary:
        combination_key = row.get("combination_key") or ""
        parsed_conditions = parse_combination(
            combination_key,
            source=str(required_paths["by_year_validation_summary"]),
            warnings=warnings,
        )
        if not parsed_conditions:
            continue

        row_score, row_bonus, row_penalty, row_notes = score_validation_row(row, args.min_trades_per_year)
        for parsed in {condition.key: condition for condition in parsed_conditions}.values():
            aggregate = ensure_aggregate(aggregates, parsed)
            aggregate["direction"] = direction
            aggregate["cost_mode"] = cost_mode
            aggregate["return_mode"] = return_mode
            for reason in exclusion_reasons(parsed):
                aggregate["exclusion_reasons"].add(reason)  # type: ignore[union-attr]
            add_validation_row(aggregate, row, row_score, row_bonus, row_penalty, row_notes)
            scored_condition_keys.add(parsed.key)

    for source_label, source_rows in (
        ("selected_combined_hypotheses", selected_combined),
        ("skipped_hypotheses", skipped_hypotheses),
    ):
        for row in source_rows:
            combination_key = row.get("combination_key") or row.get("scenario_key") or row.get("hypothesis") or ""
            skip_reason = row.get("skip_reason")
            parsed_conditions = parse_combination(
                combination_key,
                source=source_label,
                warnings=warnings,
            )
            for parsed in parsed_conditions:
                reasons = exclusion_reasons(parsed, skip_reason)
                if not reasons:
                    if parsed.key not in scored_condition_keys and source_label == "selected_combined_hypotheses":
                        warnings.append(
                            f"Selected condition {parsed.raw_condition!r} was not present in yearly validation summary; not scored."
                        )
                    continue
                aggregate = ensure_aggregate(aggregates, parsed)
                aggregate["direction"] = direction
                aggregate["cost_mode"] = cost_mode
                aggregate["return_mode"] = return_mode
                for reason in reasons:
                    aggregate["exclusion_reasons"].add(reason)  # type: ignore[union-attr]
                aggregate["notes"].add(f"seen in {source_label}")  # type: ignore[union-attr]
                if skip_reason:
                    aggregate["notes"].add(f"skip_reason={skip_reason}")  # type: ignore[union-attr]

    apply_support_bonus(
        aggregates,
        ml_supported_features=ml_support,
        cross_backtest_supported_features=cross_support,
        evaluated_backtest_supported_features=evaluated_support,
    )

    rows = finalize_rows(aggregates)
    pair_specific_scorecard_rows = build_pair_specific_feature_scorecard(
        pair_specific_candidates,
        direction=direction,
        cost_mode=cost_mode,
        return_mode=return_mode,
        warnings=warnings,
    )
    write_csv(scorecard_path, rows)
    write_pair_specific_scorecard(pair_specific_scorecard_path, pair_specific_scorecard_rows)
    input_paths = {
        **required_paths,
        "pair_specific_candidates": pair_specific_candidates_path,
        "skipped_hypotheses": skipped_path,
        "aggregate_feature_ranking": ml_support_path,
        "cross_pair_summary": Path(args.backtests_dir) / direction / CROSS_PAIR_SUMMARY_FILE,
        "evaluated_backtest_results": Path(args.backtests_dir) / direction / EVALUATED_BACKTEST_RESULTS_FILE,
    }
    write_report(
        report_path,
        rows,
        pair_specific_scorecard_rows,
        run_id=run_id,
        direction=direction,
        cost_mode=cost_mode,
        return_mode=return_mode,
        input_paths=input_paths,
        final_candidates_count=len(final_candidates),
        validation_summary_count=len(validation_summary),
        validation_detail_count=len(validation_detail),
        pair_specific_count=len(pair_specific_candidates),
        selected_combined_count=len(selected_combined),
        skipped_count=len(skipped_hypotheses),
        min_trades_per_year=args.min_trades_per_year,
        warnings=warnings,
    )

    print(f"Run ID: {run_id}")
    print(f"Direction: {direction}")
    print(f"Cost mode: {cost_mode}")
    print(f"Return mode: {return_mode}")
    print(f"Output directory: {output_run_dir}")
    print(f"Feature/condition rows: {len(rows)}")
    print(f"Pair-specific feature/condition rows: {len(pair_specific_scorecard_rows)}")
    print("Files created:")
    print(f"- {scorecard_path}")
    print(f"- {pair_specific_scorecard_path}")
    print(f"- {report_path}")
    if warnings:
        print(f"Warnings: {len(warnings)} (see report)")
    return output_run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a final research-only feature/condition scorecard from validation reports."
    )
    parser.add_argument("--run-id", help="Validation/evaluation run ID. If omitted, latest validation run is used.")
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--validation-dir", type=Path, default=DEFAULT_VALIDATION_DIR)
    parser.add_argument("--combined-evaluations-dir", type=Path, default=DEFAULT_COMBINED_EVALUATIONS_DIR)
    parser.add_argument("--ml-research-dir", type=Path, default=DEFAULT_ML_RESEARCH_DIR)
    parser.add_argument("--backtests-dir", type=Path, default=DEFAULT_BACKTESTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--min-trades-per-year", type=int, default=DEFAULT_MIN_TRADES_PER_YEAR)
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    return parser.parse_args()


def main() -> int:
    try:
        build_scorecard(parse_args())
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as exc:
        print(f"Final feature scorecard failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
