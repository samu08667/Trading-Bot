"""Build feature-stability diagnostics for preferred FX ML targets.

This utility reads target-specific ``ml_research.py`` outputs and summarizes
which features recur across FX symbols for the currently preferred h10
triple-barrier research targets. It does not train models, change thresholds,
or alter pipeline selection behavior.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from research_metrics import normalize_direction
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_preferred_target_feature_stability
    from scripts.research_metrics import normalize_direction
try:
    from feature_safety import is_future_or_target_column
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_preferred_target_feature_stability
    from scripts.feature_safety import is_future_or_target_column
try:
    from target_families import (
        PREFERRED_2ATR_1ATR_HIT_FIRST,
        supported_target_family_names,
        target_column_for_family,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_preferred_target_feature_stability
    from scripts.target_families import (
        PREFERRED_2ATR_1ATR_HIT_FIRST,
        supported_target_family_names,
        target_column_for_family,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_ROOT = BASE_DIR / "reports" / "ml_research" / "target_runs"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "ml_research" / "preferred_target_feature_stability"
DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY")
DEFAULT_DIRECTIONS = ("long", "short")

CORRELATION_FILE = "correlations.csv"
MUTUAL_INFORMATION_FILE = "mutual_information.csv"
RANDOM_FOREST_FILE = "random_forest_importance.csv"
PERMUTATION_FILE = "permutation_importance.csv"
STABILITY_CSV_FILE = "feature_stability.csv"
STABILITY_REPORT_FILE = "feature_stability_report.md"

FIELDNAMES = [
    "direction",
    "timeframe",
    "horizon",
    "target",
    "feature",
    "symbols_seen",
    "correlation_topn_count",
    "mutual_info_topn_count",
    "random_forest_topn_count",
    "permutation_topn_count",
    "average_directional_spearman_rank",
    "average_mutual_info_rank",
    "average_random_forest_rank",
    "average_permutation_rank",
    "stability_score",
    "feature_family",
    "notes",
]

METRIC_SPECS = {
    "correlation": {
        "file": CORRELATION_FILE,
        "score_columns": ("abs_directional_spearman", "abs_spearman"),
        "count_field": "correlation_topn_count",
        "average_rank_field": "average_directional_spearman_rank",
    },
    "mutual_info": {
        "file": MUTUAL_INFORMATION_FILE,
        "score_columns": ("mutual_information", "score"),
        "count_field": "mutual_info_topn_count",
        "average_rank_field": "average_mutual_info_rank",
    },
    "random_forest": {
        "file": RANDOM_FOREST_FILE,
        "score_columns": ("importance", "feature_importance"),
        "count_field": "random_forest_topn_count",
        "average_rank_field": "average_random_forest_rank",
    },
    "permutation": {
        "file": PERMUTATION_FILE,
        "score_columns": ("importance_mean", "importance"),
        "count_field": "permutation_topn_count",
        "average_rank_field": "average_permutation_rank",
    },
}


@dataclass(frozen=True)
class MetricRanking:
    ranks: dict[str, int]
    top_features: set[str]
    score_column: str


@dataclass(frozen=True)
class SymbolReport:
    symbol: str
    report_dir: Path
    rankings: dict[str, MetricRanking]
    warnings: list[str]


@dataclass(frozen=True)
class StabilityDiagnostics:
    requested_symbols: list[str]
    loaded_symbols: list[str]
    missing_report_dirs: list[Path]
    warnings: list[str]


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


def csv_value(value: object) -> object:
    return "" if value is None else value


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def preferred_target(
    direction: str,
    horizon: int,
    target_family: str = PREFERRED_2ATR_1ATR_HIT_FIRST,
) -> str:
    return target_column_for_family(normalize_direction(direction), target_family, horizon)


def target_report_dir(
    reports_root: Path,
    *,
    direction: str,
    symbol: str,
    timeframe: str,
    horizon: int,
    target: str,
) -> Path:
    return reports_root / direction / f"{symbol}_{timeframe}_h{horizon}" / target


def output_dir_for(output_root: Path, *, direction: str, timeframe: str, horizon: int) -> Path:
    return output_root / direction / f"{timeframe}_h{horizon}"


def choose_score_column(rows: list[dict[str, str]], candidates: tuple[str, ...]) -> str | None:
    if not rows:
        return None
    for column in candidates:
        if any(safe_float(row.get(column)) is not None for row in rows):
            return column
    return None


def rank_features(rows: list[dict[str, str]], score_columns: tuple[str, ...], top_n: int) -> MetricRanking | None:
    score_column = choose_score_column(rows, score_columns)
    if score_column is None:
        return None

    scored: list[tuple[str, float]] = []
    for row in rows:
        feature = str(row.get("feature") or "").strip()
        if is_future_or_target_column(feature):
            continue
        score = safe_float(row.get(score_column))
        if not feature or score is None:
            continue
        scored.append((feature, score))

    if not scored:
        return None

    scored.sort(key=lambda item: (-item[1], item[0]))
    ranks = {feature: index + 1 for index, (feature, _score) in enumerate(scored)}
    top_features = {feature for feature, rank in ranks.items() if rank <= top_n}
    return MetricRanking(ranks=ranks, top_features=top_features, score_column=score_column)


def load_symbol_report(
    report_dir: Path,
    *,
    symbol: str,
    top_n: int,
) -> SymbolReport:
    rankings: dict[str, MetricRanking] = {}
    warnings: list[str] = []
    for metric_name, spec in METRIC_SPECS.items():
        path = report_dir / str(spec["file"])
        if not path.exists():
            warnings.append(f"{symbol}: missing {path.name}")
            continue
        rows = read_csv_rows(path)
        ranking = rank_features(rows, spec["score_columns"], top_n)  # type: ignore[arg-type]
        if ranking is None:
            warnings.append(f"{symbol}: no usable feature scores in {path.name}")
            continue
        rankings[metric_name] = ranking
    return SymbolReport(symbol=symbol, report_dir=report_dir, rankings=rankings, warnings=warnings)


def load_symbol_reports(
    *,
    reports_root: Path,
    symbols: list[str],
    direction: str,
    timeframe: str,
    horizon: int,
    target: str,
    top_n: int,
) -> tuple[list[SymbolReport], StabilityDiagnostics]:
    loaded: list[SymbolReport] = []
    missing_report_dirs: list[Path] = []
    warnings: list[str] = []

    for raw_symbol in symbols:
        symbol = raw_symbol.strip().upper()
        report_dir = target_report_dir(
            reports_root,
            direction=direction,
            symbol=symbol,
            timeframe=timeframe,
            horizon=horizon,
            target=target,
        )
        if not report_dir.exists():
            missing_report_dirs.append(report_dir)
            continue
        symbol_report = load_symbol_report(report_dir, symbol=symbol, top_n=top_n)
        loaded.append(symbol_report)
        warnings.extend(symbol_report.warnings)

    diagnostics = StabilityDiagnostics(
        requested_symbols=[symbol.strip().upper() for symbol in symbols],
        loaded_symbols=[report.symbol for report in loaded],
        missing_report_dirs=missing_report_dirs,
        warnings=warnings,
    )
    return loaded, diagnostics


def average(values: list[int]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def feature_family(feature: str) -> str:
    name = feature.strip().lower()
    spread_features = {
        "spread_price",
        "spread_return",
        "spread_to_atr_20",
        "spread_to_volume_ratio",
        "spread_avg_20",
    }
    volume_features = {
        "tick_volume_avg_20",
        "tick_volume_ratio_20",
        "tick_volume_zscore_100",
        "tick_volume_percentile_100",
        "volume_spike_20",
        "volume_dry_up_20",
        "volume_vs_hour_avg",
        "volume_vs_session_avg",
    }
    volatility_features = {
        "atr_14",
        "atr_20",
        "atr_50",
        "volatility_20",
        "volatility_100",
        "volatility_ratio_20_100",
        "range_to_atr_20",
        "body_to_atr_20",
    }
    trend_features = {
        "ma_fast",
        "ma_slow",
        "ma_diff",
        "ma_diff_atr_20",
        "close_to_ma_fast_atr_20",
        "close_to_ma_slow_atr_20",
    }
    session_features = {"hour", "day_of_week", "hour_session"}

    if name in spread_features:
        return "spread/liquidity"
    if name in volume_features:
        return "volume/liquidity"
    if name in volatility_features or "wick_to_atr" in name:
        return "volatility/range"
    if name in trend_features:
        return "trend/ma"
    if name in session_features or "session" in name:
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


def build_stability_rows(
    *,
    symbol_reports: list[SymbolReport],
    direction: str,
    timeframe: str,
    horizon: int,
    target: str,
    top_n: int,
) -> list[dict[str, Any]]:
    features: set[str] = set()
    for report in symbol_reports:
        for ranking in report.rankings.values():
            features.update(ranking.top_features)

    rows: list[dict[str, Any]] = []
    for feature in sorted(features):
        metric_counts = {metric_name: 0 for metric_name in METRIC_SPECS}
        metric_ranks: dict[str, list[int]] = {metric_name: [] for metric_name in METRIC_SPECS}
        symbols_seen: set[str] = set()

        for report in symbol_reports:
            symbol_has_topn_hit = False
            for metric_name, ranking in report.rankings.items():
                rank = ranking.ranks.get(feature)
                if rank is None or rank > top_n:
                    continue
                metric_counts[metric_name] += 1
                metric_ranks[metric_name].append(rank)
                symbol_has_topn_hit = True
            if symbol_has_topn_hit:
                symbols_seen.add(report.symbol)

        notes: list[str] = []
        if len(symbols_seen) == 1:
            notes.append("symbol_specific_only")
        if len(symbols_seen) == len(symbol_reports) and symbol_reports:
            notes.append("seen_in_all_loaded_symbols")

        total_metric_hits = sum(metric_counts.values())
        stability_score = len(symbols_seen) + total_metric_hits
        rows.append(
            {
                "direction": direction,
                "timeframe": timeframe,
                "horizon": horizon,
                "target": target,
                "feature": feature,
                "symbols_seen": len(symbols_seen),
                "correlation_topn_count": metric_counts["correlation"],
                "mutual_info_topn_count": metric_counts["mutual_info"],
                "random_forest_topn_count": metric_counts["random_forest"],
                "permutation_topn_count": metric_counts["permutation"],
                "average_directional_spearman_rank": average(metric_ranks["correlation"]),
                "average_mutual_info_rank": average(metric_ranks["mutual_info"]),
                "average_random_forest_rank": average(metric_ranks["random_forest"]),
                "average_permutation_rank": average(metric_ranks["permutation"]),
                "stability_score": stability_score,
                "feature_family": feature_family(feature),
                "notes": "; ".join(notes),
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            -int(row["stability_score"]),
            -int(row["symbols_seen"]),
            float(row["average_directional_spearman_rank"] or 999999),
            str(row["feature"]),
        ),
    )


def write_stability_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in FIELDNAMES})


def markdown_value(value: object) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def top_feature_lines(rows: list[dict[str, Any]], limit: int = 15) -> list[str]:
    if not rows:
        return ["- None available."]
    lines = []
    for row in rows[:limit]:
        lines.append(
            "- `{feature}`: score={score}, symbols={symbols}, family={family}, "
            "corr={corr}, mi={mi}, rf={rf}, perm={perm}".format(
                feature=row["feature"],
                score=markdown_value(row["stability_score"]),
                symbols=markdown_value(row["symbols_seen"]),
                family=markdown_value(row["feature_family"]),
                corr=markdown_value(row["correlation_topn_count"]),
                mi=markdown_value(row["mutual_info_topn_count"]),
                rf=markdown_value(row["random_forest_topn_count"]),
                perm=markdown_value(row["permutation_topn_count"]),
            )
        )
    return lines


def family_summary_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- None available."]
    family_counts = Counter(str(row["feature_family"]) for row in rows)
    family_scores: dict[str, list[float]] = {}
    for row in rows:
        family_scores.setdefault(str(row["feature_family"]), []).append(float(row["stability_score"]))
    lines = []
    for family, count in family_counts.most_common():
        avg_score = sum(family_scores[family]) / len(family_scores[family])
        lines.append(f"- {family}: {count} features, average stability_score={avg_score:.2f}")
    return lines


def symbol_specific_lines(rows: list[dict[str, Any]], limit: int = 20) -> list[str]:
    symbol_specific = [row for row in rows if int(row["symbols_seen"]) == 1]
    if not symbol_specific:
        return ["- None."]
    return [
        f"- `{row['feature']}`: score={row['stability_score']}, family={row['feature_family']}"
        for row in symbol_specific[:limit]
    ]


def write_stability_report(
    path: Path,
    *,
    rows: list[dict[str, Any]],
    diagnostics: StabilityDiagnostics,
    direction: str,
    timeframe: str,
    horizon: int,
    target: str,
    top_n: int,
) -> None:
    direction_title = "Long" if direction == "long" else "Short"
    lines = [
        f"# Preferred Target Feature Stability Report - {direction_title}",
        "",
        "This report is research-only diagnostic evidence for hypothesis discovery. It does not establish strategy validity or operational guidance.",
        "",
        "## Configuration",
        "",
        f"- Direction: `{direction}`",
        f"- Timeframe: `{timeframe}`",
        f"- Horizon: `{horizon}`",
        f"- Target: `{target}`",
        f"- Top N per metric: `{top_n}`",
        f"- Requested symbols: {', '.join(diagnostics.requested_symbols) or 'None'}",
        f"- Loaded symbols: {', '.join(diagnostics.loaded_symbols) or 'None'}",
        "",
        f"## Top Stable Features For {direction_title}",
        "",
        *top_feature_lines(rows),
        "",
        "## Recurring Feature Families",
        "",
        *family_summary_lines(rows),
        "",
        "## Symbol-Specific Features",
        "",
        *symbol_specific_lines(rows),
        "",
        "## Missing Or Partial Inputs",
        "",
    ]
    if diagnostics.missing_report_dirs:
        lines.extend(f"- Missing report folder: `{path}`" for path in diagnostics.missing_report_dirs)
    else:
        lines.append("- No missing report folders.")
    if diagnostics.warnings:
        lines.extend(f"- {warning}" for warning in diagnostics.warnings)
    else:
        lines.append("- No partial metric warnings.")

    lines.extend(
        [
            "",
            "## Warnings",
            "",
            "- Correlation ranking uses `abs_directional_spearman` when available, otherwise `abs_spearman`.",
            "- Permutation importance can be noisy; treat it as one descriptive input.",
            "- The stability score is a simple recurrence count across symbols and metric families.",
            "- XAUUSD is intentionally excluded from the default FX symbol set until stronger threshold diagnostics appear.",
            "- Feature stability is only for hypothesis discovery and does not prove strategy validity.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_direction_feature_stability(
    *,
    reports_root: Path,
    output_root: Path,
    symbols: list[str],
    timeframe: str,
    horizon: int,
    direction: str,
    top_n: int,
    target_family: str = PREFERRED_2ATR_1ATR_HIT_FIRST,
) -> dict[str, Path]:
    if top_n <= 0:
        raise ValueError("--top-n must be greater than zero.")

    normalized_direction = normalize_direction(direction)
    normalized_timeframe = timeframe.strip().upper()
    target = preferred_target(normalized_direction, horizon, target_family)
    symbol_reports, diagnostics = load_symbol_reports(
        reports_root=reports_root,
        symbols=symbols,
        direction=normalized_direction,
        timeframe=normalized_timeframe,
        horizon=horizon,
        target=target,
        top_n=top_n,
    )
    rows = build_stability_rows(
        symbol_reports=symbol_reports,
        direction=normalized_direction,
        timeframe=normalized_timeframe,
        horizon=horizon,
        target=target,
        top_n=top_n,
    )

    output_dir = output_dir_for(output_root, direction=normalized_direction, timeframe=normalized_timeframe, horizon=horizon)
    csv_path = output_dir / STABILITY_CSV_FILE
    report_path = output_dir / STABILITY_REPORT_FILE
    write_stability_csv(csv_path, rows)
    write_stability_report(
        report_path,
        rows=rows,
        diagnostics=diagnostics,
        direction=normalized_direction,
        timeframe=normalized_timeframe,
        horizon=horizon,
        target=target,
        top_n=top_n,
    )
    return {"feature_stability_csv": csv_path, "feature_stability_report": report_path}


def build_preferred_target_feature_stability(args: argparse.Namespace) -> dict[str, dict[str, Path]]:
    symbols = [str(symbol).strip().upper() for symbol in args.symbols if str(symbol).strip()]
    if not symbols:
        raise ValueError("--symbols must include at least one symbol.")

    outputs: dict[str, dict[str, Path]] = {}
    for direction in args.directions:
        normalized_direction = normalize_direction(direction)
        outputs[normalized_direction] = build_direction_feature_stability(
            reports_root=Path(args.reports_root),
            output_root=Path(args.output_root),
            symbols=symbols,
            timeframe=str(args.timeframe),
            horizon=int(args.horizon),
            direction=normalized_direction,
            top_n=int(args.top_n),
            target_family=str(getattr(args, "target_family", PREFERRED_2ATR_1ATR_HIT_FIRST)),
        )
    return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build research-only feature stability diagnostics for preferred FX ML targets."
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--directions", nargs="+", choices=DEFAULT_DIRECTIONS, default=list(DEFAULT_DIRECTIONS))
    parser.add_argument(
        "--target-family",
        choices=supported_target_family_names(),
        default=PREFERRED_2ATR_1ATR_HIT_FIRST,
    )
    parser.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT, help=f"Default: {DEFAULT_REPORTS_ROOT}")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=f"Default: {DEFAULT_OUTPUT_ROOT}")
    parser.add_argument("--top-n", type=int, default=30)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        outputs = build_preferred_target_feature_stability(args)
    except (ValueError, OSError) as exc:
        print(f"Preferred target feature stability failed: {exc}")
        return 1

    print("Preferred target feature stability complete.")
    for direction, paths in outputs.items():
        print(f"Direction: {direction}")
        print(f"Feature stability CSV: {paths['feature_stability_csv']}")
        print(f"Feature stability report: {paths['feature_stability_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
