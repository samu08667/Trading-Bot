"""Build a research-only shortlist from preferred target feature stability.

The shortlist translates recurring ML feature-stability rows into cautious
feature-hypothesis classifications. It is a diagnostic bridge from ML rankings
to later controlled validation; it does not train models, change backtest
selection, or create operational guidance.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from research_metrics import normalize_direction
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_preferred_feature_hypothesis_shortlist
    from scripts.research_metrics import normalize_direction
try:
    from feature_safety import is_future_or_target_column
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_preferred_feature_hypothesis_shortlist
    from scripts.feature_safety import is_future_or_target_column


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = BASE_DIR / "reports" / "ml_research" / "preferred_target_feature_stability"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "ml_research" / "preferred_feature_hypotheses"
DEFAULT_DIRECTIONS = ("long", "short")
INPUT_FILE = "feature_stability.csv"
OUTPUT_CSV_FILE = "preferred_feature_hypotheses.csv"
OUTPUT_REPORT_FILE = "preferred_feature_hypotheses_report.md"

OUTPUT_FIELDS = [
    "direction",
    "timeframe",
    "horizon",
    "target",
    "feature",
    "feature_family",
    "tradability_role",
    "normalized_or_raw",
    "recommended_usage",
    "caution_level",
    "symbols_seen",
    "stability_score",
    "correlation_topn_count",
    "mutual_info_topn_count",
    "random_forest_topn_count",
    "permutation_topn_count",
    "average_directional_spearman_rank",
    "average_mutual_info_rank",
    "average_random_forest_rank",
    "average_permutation_rank",
    "notes",
]

RAW_SCALE_DEPENDENT_FEATURES = {
    "ma_fast",
    "ma_slow",
    "ma_diff",
    "candle_range",
    "true_range",
    "atr_14",
    "atr_20",
    "atr_50",
    "tick_volume_avg_20",
    "spread_price",
    "spread_avg_20",
}

PREFERRED_NORMALIZED_FEATURES = {
    "return_1",
    "return_5",
    "return_20",
    "ma_diff_atr_20",
    "close_to_ma_fast_atr_20",
    "close_to_ma_slow_atr_20",
    "range_to_atr_20",
    "body_to_atr_20",
    "spread_to_atr_20",
    "spread_return",
    "tick_volume_ratio_20",
    "tick_volume_zscore_100",
    "tick_volume_percentile_100",
    "volume_vs_session_avg",
}


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
    if not math.isfinite(parsed):
        return None
    return parsed


def safe_int(value: object) -> int | None:
    parsed = safe_float(value)
    if parsed is None:
        return None
    return int(parsed)


def csv_value(value: object) -> object:
    return "" if value is None else value


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def input_path_for(input_root: Path, *, direction: str, timeframe: str, horizon: int) -> Path:
    return input_root / direction / f"{timeframe}_h{horizon}" / INPUT_FILE


def output_dir_for(output_root: Path, *, direction: str, timeframe: str, horizon: int) -> Path:
    return output_root / direction / f"{timeframe}_h{horizon}"


def feature_family(feature: str) -> str:
    name = feature.strip().lower()
    if name in {"return_1", "return_5", "return_20"}:
        return "momentum/returns"
    if name in {
        "candle_range",
        "true_range",
        "atr_14",
        "atr_20",
        "atr_50",
        "volatility_100",
        "volatility_ratio_20_100",
        "range_to_atr_20",
        "body_to_atr_20",
    } or "wick_to_atr" in name:
        return "volatility/range"
    if name in {
        "ma_fast",
        "ma_slow",
        "ma_diff",
        "ma_diff_atr_20",
        "close_to_ma_fast_atr_20",
        "close_to_ma_slow_atr_20",
    }:
        return "trend/ma"
    if name in {
        "spread_price",
        "spread_return",
        "spread_to_atr_20",
        "spread_avg_20",
        "spread_to_volume_ratio",
    }:
        return "spread/liquidity"
    if name in {
        "tick_volume_ratio_20",
        "tick_volume_zscore_100",
        "tick_volume_percentile_100",
        "volume_spike_20",
        "volume_dry_up_20",
        "volume_vs_hour_avg",
        "volume_vs_session_avg",
        "tick_volume_avg_20",
    }:
        return "volume/liquidity"
    if name in {"hour", "day_of_week", "hour_session"}:
        return "session/calendar"
    if (
        "news" in name
        or "event" in name
        or "importance" in name
        or "blackout" in name
        or "post_news" in name
        or name.startswith("minutes_to")
        or name.startswith("minutes_from")
    ):
        return "news_risk"
    return "other"


def tradability_role_for_family(family: str) -> str:
    return {
        "momentum/returns": "momentum_filter",
        "trend/ma": "trend_filter",
        "volatility/range": "volatility_regime_filter",
        "volume/liquidity": "liquidity_filter",
        "spread/liquidity": "spread_cost_filter",
        "session/calendar": "session_filter",
        "news_risk": "news_risk_filter",
    }.get(family, "context_only")


def normalized_or_raw(feature: str) -> str:
    name = feature.strip().lower()
    if name in RAW_SCALE_DEPENDENT_FEATURES:
        return "raw_scale_dependent"
    if name in PREFERRED_NORMALIZED_FEATURES:
        return "preferred_normalized"
    if name in {"volume_spike_20", "volume_dry_up_20"}:
        return "binary_context"
    if feature_family(name) in {"session/calendar", "news_risk"}:
        return "contextual"
    return "derived_context"


def caution_level(feature: str, family: str, norm_type: str) -> str:
    if norm_type == "raw_scale_dependent":
        return "high"
    if norm_type == "preferred_normalized":
        return "low"
    if family in {"session/calendar", "news_risk"}:
        return "medium"
    return "medium"


def recommended_usage(feature: str, family: str, norm_type: str) -> str:
    if norm_type == "raw_scale_dependent":
        return "prefer normalized variant"
    if family in {"session/calendar", "news_risk"}:
        return "use only as regime/context filter"
    if norm_type == "preferred_normalized":
        return "candidate for controlled combination testing"
    if family == "momentum/returns":
        return "use as standalone filter candidate"
    if norm_type == "binary_context":
        return "do not use alone"
    return "use only as regime/context filter"


def classification_notes(feature: str, family: str, norm_type: str, source_notes: str) -> str:
    notes: list[str] = []
    if norm_type == "raw_scale_dependent":
        notes.append("scale-dependent; compare with normalized alternatives")
    if norm_type == "preferred_normalized":
        notes.append("cleaner normalized/contextual feature")
    if family == "spread/liquidity":
        notes.append("cost/liquidity context, not a direction rule")
    if family == "volume/liquidity":
        notes.append("tick-volume/liquidity context")
    if source_notes:
        notes.append(source_notes)
    return "; ".join(notes)


def classify_row(
    row: dict[str, str],
    *,
    direction: str,
    timeframe: str,
    horizon: int,
) -> dict[str, Any]:
    feature = str(row.get("feature") or "").strip()
    family = feature_family(feature)
    norm_type = normalized_or_raw(feature)
    return {
        "direction": str(row.get("direction") or direction).strip().lower(),
        "timeframe": str(row.get("timeframe") or timeframe).strip().upper(),
        "horizon": row.get("horizon") or horizon,
        "target": row.get("target", ""),
        "feature": feature,
        "feature_family": family,
        "tradability_role": tradability_role_for_family(family),
        "normalized_or_raw": norm_type,
        "recommended_usage": recommended_usage(feature, family, norm_type),
        "caution_level": caution_level(feature, family, norm_type),
        "symbols_seen": safe_int(row.get("symbols_seen")) or 0,
        "stability_score": safe_int(row.get("stability_score")) or 0,
        "correlation_topn_count": safe_int(row.get("correlation_topn_count")) or 0,
        "mutual_info_topn_count": safe_int(row.get("mutual_info_topn_count")) or 0,
        "random_forest_topn_count": safe_int(row.get("random_forest_topn_count")) or 0,
        "permutation_topn_count": safe_int(row.get("permutation_topn_count")) or 0,
        "average_directional_spearman_rank": row.get("average_directional_spearman_rank", ""),
        "average_mutual_info_rank": row.get("average_mutual_info_rank", ""),
        "average_random_forest_rank": row.get("average_random_forest_rank", ""),
        "average_permutation_rank": row.get("average_permutation_rank", ""),
        "notes": classification_notes(feature, family, norm_type, row.get("notes", "")),
    }


def build_shortlist_rows(
    input_path: Path,
    *,
    direction: str,
    timeframe: str,
    horizon: int,
    min_symbols: int,
    min_stability_score: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    if min_symbols < 1:
        raise ValueError("--min-symbols must be at least 1.")
    if min_stability_score < 0:
        raise ValueError("--min-stability-score cannot be negative.")
    if not input_path.exists():
        return [], [f"Missing input file: {input_path}"]

    shortlisted: list[dict[str, Any]] = []
    skipped_future_or_target = 0
    for row in read_csv_rows(input_path):
        symbols_seen = safe_int(row.get("symbols_seen")) or 0
        stability_score = safe_int(row.get("stability_score")) or 0
        if symbols_seen < min_symbols or stability_score < min_stability_score:
            continue
        feature = str(row.get("feature") or "").strip()
        if not feature:
            continue
        if is_future_or_target_column(feature):
            skipped_future_or_target += 1
            continue
        shortlisted.append(
            classify_row(row, direction=direction, timeframe=timeframe, horizon=horizon)
        )

    shortlisted.sort(
        key=lambda row: (
            -int(row["stability_score"]),
            -int(row["symbols_seen"]),
            str(row["feature_family"]),
            str(row["feature"]),
        )
    )
    warnings = []
    if skipped_future_or_target:
        warnings.append(f"Excluded future/target/leakage feature rows: {skipped_future_or_target}")
    return shortlisted, warnings


def write_shortlist_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in OUTPUT_FIELDS})


def top_feature_lines(rows: list[dict[str, Any]], limit: int = 20) -> list[str]:
    if not rows:
        return ["- None."]
    return [
        (
            f"- `{row['feature']}`: score={row['stability_score']}, "
            f"symbols={row['symbols_seen']}, family={row['feature_family']}, "
            f"usage={row['recommended_usage']}, caution={row['caution_level']}"
        )
        for row in rows[:limit]
    ]


def family_summary_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- None."]
    counts = Counter(str(row["feature_family"]) for row in rows)
    return [f"- {family}: {count} shortlisted features" for family, count in counts.most_common()]


def normalized_feature_lines(rows: list[dict[str, Any]]) -> list[str]:
    normalized_rows = [row for row in rows if row["normalized_or_raw"] == "preferred_normalized"]
    if not normalized_rows:
        return ["- None."]
    return [
        f"- `{row['feature']}`: {row['recommended_usage']}"
        for row in normalized_rows[:20]
    ]


def raw_caution_lines(rows: list[dict[str, Any]]) -> list[str]:
    raw_rows = [row for row in rows if row["normalized_or_raw"] == "raw_scale_dependent"]
    if not raw_rows:
        return ["- None."]
    return [
        f"- `{row['feature']}`: {row['notes']}"
        for row in raw_rows[:20]
    ]


def write_shortlist_report(
    path: Path,
    *,
    rows: list[dict[str, Any]],
    warnings: list[str],
    direction: str,
    timeframe: str,
    horizon: int,
    min_symbols: int,
    min_stability_score: int,
) -> None:
    direction_title = "Long" if direction == "long" else "Short"
    lines = [
        f"# Preferred Feature Hypothesis Shortlist - {direction_title}",
        "",
        "This report is research-only and supports hypothesis discovery. It is not a strategy and is not ready for deployment.",
        "",
        "## Filters",
        "",
        f"- Direction: `{direction}`",
        f"- Timeframe: `{timeframe}`",
        f"- Horizon: `{horizon}`",
        f"- Minimum symbols: `{min_symbols}`",
        f"- Minimum stability score: `{min_stability_score}`",
        "",
        f"## Top Preferred Features For {direction_title}",
        "",
        *top_feature_lines(rows),
        "",
        "## Top Feature Families",
        "",
        *family_summary_lines(rows),
        "",
        "## Normalized Features Preferred For Backtesting",
        "",
        *normalized_feature_lines(rows),
        "",
        "## Raw Or Scale-Dependent Features Requiring Caution",
        "",
        *raw_caution_lines(rows),
        "",
        "## Suggested Next Research-Only Step",
        "",
        "- Use the shortlist as input to controlled backtest and validation experiments, keeping long and short separate.",
        "- Prefer normalized variants when a raw or scale-dependent feature has a close normalized alternative.",
        "- Keep XAUUSD in separate review unless its threshold and stability diagnostics improve.",
        "",
        "## Warnings",
        "",
        "- This shortlist is generated from ML feature stability diagnostics and does not prove robustness or profitability.",
        "- Features can be candidates for controlled combination testing, but they still need out-of-sample and cost-aware validation.",
    ]
    if warnings:
        lines.extend(["", "## Missing Inputs", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_direction_shortlist(
    *,
    input_root: Path,
    output_root: Path,
    direction: str,
    timeframe: str,
    horizon: int,
    min_symbols: int,
    min_stability_score: int,
) -> dict[str, Path]:
    normalized_direction = normalize_direction(direction)
    normalized_timeframe = timeframe.strip().upper()
    input_path = input_path_for(
        input_root,
        direction=normalized_direction,
        timeframe=normalized_timeframe,
        horizon=horizon,
    )
    rows, warnings = build_shortlist_rows(
        input_path,
        direction=normalized_direction,
        timeframe=normalized_timeframe,
        horizon=horizon,
        min_symbols=min_symbols,
        min_stability_score=min_stability_score,
    )
    output_dir = output_dir_for(
        output_root,
        direction=normalized_direction,
        timeframe=normalized_timeframe,
        horizon=horizon,
    )
    csv_path = output_dir / OUTPUT_CSV_FILE
    report_path = output_dir / OUTPUT_REPORT_FILE
    write_shortlist_csv(csv_path, rows)
    write_shortlist_report(
        report_path,
        rows=rows,
        warnings=warnings,
        direction=normalized_direction,
        timeframe=normalized_timeframe,
        horizon=horizon,
        min_symbols=min_symbols,
        min_stability_score=min_stability_score,
    )
    return {"preferred_feature_hypotheses_csv": csv_path, "preferred_feature_hypotheses_report": report_path}


def build_preferred_feature_hypothesis_shortlist(args: argparse.Namespace) -> dict[str, dict[str, Path]]:
    outputs: dict[str, dict[str, Path]] = {}
    for direction in args.directions:
        normalized_direction = normalize_direction(direction)
        outputs[normalized_direction] = build_direction_shortlist(
            input_root=Path(args.input_root),
            output_root=Path(args.output_root),
            direction=normalized_direction,
            timeframe=str(args.timeframe),
            horizon=int(args.horizon),
            min_symbols=int(args.min_symbols),
            min_stability_score=int(args.min_stability_score),
        )
    return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only preferred feature hypothesis shortlist from feature stability reports."
    )
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--directions", nargs="+", choices=DEFAULT_DIRECTIONS, default=list(DEFAULT_DIRECTIONS))
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT, help=f"Default: {DEFAULT_INPUT_ROOT}")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=f"Default: {DEFAULT_OUTPUT_ROOT}")
    parser.add_argument("--min-symbols", type=int, default=3)
    parser.add_argument("--min-stability-score", type=int, default=12)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        outputs = build_preferred_feature_hypothesis_shortlist(args)
    except (ValueError, OSError) as exc:
        print(f"Preferred feature hypothesis shortlist failed: {exc}")
        return 1

    print("Preferred feature hypothesis shortlist complete.")
    for direction, paths in outputs.items():
        print(f"Direction: {direction}")
        print(f"Preferred feature hypotheses CSV: {paths['preferred_feature_hypotheses_csv']}")
        print(f"Preferred feature hypotheses report: {paths['preferred_feature_hypotheses_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
