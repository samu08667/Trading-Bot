import argparse
import csv
from collections import defaultdict
from pathlib import Path

from research_metrics import normalize_direction


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = BASE_DIR / "reports" / "ml_research"

REPORT_FILES = {
    "correlations": "correlations.csv",
    "mutual_information": "mutual_information.csv",
    "random_forest": "random_forest_importance.csv",
    "permutation": "permutation_importance.csv",
    "model_metrics": "model_metrics.csv",
}

OUTPUT_RANKING = "summary_feature_ranking.csv"
OUTPUT_SUMMARY = "research_summary.txt"
OUTPUT_AGGREGATE = "aggregate_feature_ranking.csv"


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


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


def has_report_files(path: Path) -> bool:
    return all((path / file_name).exists() for file_name in REPORT_FILES.values())


def discover_report_dirs(input_dir: Path | None, direction: str) -> list[Path]:
    root = input_dir or DEFAULT_REPORT_DIR / direction
    if input_dir is None and not root.exists():
        legacy_root = DEFAULT_REPORT_DIR
        if direction == "long" and legacy_root.exists():
            root = legacy_root
    if not root.exists():
        raise FileNotFoundError(f"Input report directory not found: {root}")

    if input_dir is None:
        report_dirs = sorted(
            path for path in root.iterdir()
            if path.is_dir() and has_report_files(path)
        )
        if report_dirs:
            return report_dirs
        if has_report_files(root):
            return [root]
        raise FileNotFoundError(f"No ML research report folders found under {root}")

    if has_report_files(root):
        return [root]

    report_dirs = sorted(
        path for path in root.iterdir()
        if path.is_dir() and has_report_files(path)
    )
    if not report_dirs:
        raise FileNotFoundError(f"No ML research report folders found under {root}")
    return report_dirs


def ranked_features(
    rows: list[dict[str, str]],
    score_column: str,
    *,
    positive_only: bool = False,
) -> dict[str, int]:
    scored_rows = []
    for row in rows:
        feature = row.get("feature", "").strip()
        score = to_float(row.get(score_column))
        if not feature or score is None:
            continue
        if positive_only and score <= 0:
            continue
        scored_rows.append((feature, score))

    scored_rows.sort(key=lambda item: item[1], reverse=True)
    return {feature: index + 1 for index, (feature, _score) in enumerate(scored_rows)}


def collect_feature_names(*rankings: dict[str, int]) -> set[str]:
    features: set[str] = set()
    for ranking in rankings:
        features.update(ranking)
    return features


def rank_points(rank: int | None, top_n: int) -> int:
    if rank is None:
        return 0
    return int(rank <= top_n)


def interpretation(score: int) -> str:
    if score >= 4:
        return "strong"
    if score >= 2:
        return "interesting"
    if score == 1:
        return "weak"
    return "ignore"


def build_feature_ranking(input_dir: Path, top_n: int, direction: str) -> list[dict[str, object]]:
    correlations = read_csv_dicts(input_dir / REPORT_FILES["correlations"])
    mutual_information = read_csv_dicts(input_dir / REPORT_FILES["mutual_information"])
    random_forest = read_csv_dicts(input_dir / REPORT_FILES["random_forest"])
    permutation = read_csv_dicts(input_dir / REPORT_FILES["permutation"])

    pearson_ranks = ranked_features(correlations, "abs_pearson")
    spearman_ranks = ranked_features(correlations, "abs_spearman")
    mutual_information_ranks = ranked_features(mutual_information, "mutual_information")
    random_forest_ranks = ranked_features(random_forest, "importance")
    permutation_ranks = ranked_features(permutation, "importance_mean", positive_only=True)

    rows = []
    for feature in sorted(
        collect_feature_names(
            pearson_ranks,
            spearman_ranks,
            mutual_information_ranks,
            random_forest_ranks,
            permutation_ranks,
        )
    ):
        pearson_rank = pearson_ranks.get(feature)
        spearman_rank = spearman_ranks.get(feature)
        mutual_information_rank = mutual_information_ranks.get(feature)
        random_forest_rank = random_forest_ranks.get(feature)
        permutation_rank = permutation_ranks.get(feature)
        total_score = (
            rank_points(pearson_rank, top_n)
            + rank_points(spearman_rank, top_n)
            + rank_points(mutual_information_rank, top_n)
            + rank_points(random_forest_rank, top_n)
            + rank_points(permutation_rank, top_n)
        )
        rows.append(
            {
                "direction": direction,
                "report_dir": str(input_dir),
                "feature": feature,
                "total_score": total_score,
                "pearson_rank": pearson_rank,
                "spearman_rank": spearman_rank,
                "mutual_information_rank": mutual_information_rank,
                "random_forest_rank": random_forest_rank,
                "permutation_rank": permutation_rank,
                "interpretation": interpretation(total_score),
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            -int(row["total_score"]),
            row["pearson_rank"] or 999999,
            row["spearman_rank"] or 999999,
            row["feature"],
        ),
    )


def write_feature_ranking(output_dir: Path, rows: list[dict[str, object]]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / OUTPUT_RANKING
    fieldnames = [
        "direction",
        "report_dir",
        "feature",
        "total_score",
        "pearson_rank",
        "spearman_rank",
        "mutual_information_rank",
        "random_forest_rank",
        "permutation_rank",
        "interpretation",
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_model_metrics(input_dir: Path) -> list[dict[str, str]]:
    return read_csv_dicts(input_dir / REPORT_FILES["model_metrics"])


def format_model_metrics(metrics: list[dict[str, str]]) -> list[str]:
    preferred_metrics = [
        "symbol",
        "timeframe",
        "horizon",
        "target",
        "return_target",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "rows_total",
        "rows_train",
        "rows_test",
        "features_used",
        "train_positive_ratio",
        "test_positive_ratio",
    ]
    metric_map = {
        row.get("metric", ""): row.get("value", "")
        for row in metrics
        if row.get("metric")
    }

    lines = []
    for metric in preferred_metrics:
        if metric in metric_map:
            lines.append(f"- {metric}: {metric_map[metric]}")
    if not lines:
        lines.append("- No model metrics available.")
    return lines


def feature_lines(rows: list[dict[str, object]], label: str, limit: int = 20) -> list[str]:
    selected = [row for row in rows if row["interpretation"] == label]
    if not selected:
        return ["- none"]

    lines = []
    for row in selected[:limit]:
        lines.append(
            "- {feature}: score={total_score}, pearson={pearson_rank}, "
            "spearman={spearman_rank}, mi={mutual_information_rank}, "
            "rf={random_forest_rank}, permutation={permutation_rank}".format(**row)
        )
    return lines


def write_research_summary(
    output_dir: Path,
    ranking_rows: list[dict[str, object]],
    model_metrics: list[dict[str, str]],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / OUTPUT_SUMMARY
    lines = [
        "ML Research Summary",
        "",
        f"Report directory: {output_dir}",
        "",
        "Model metrics",
        *format_model_metrics(model_metrics),
        "",
        "Top strong features",
        *feature_lines(ranking_rows, "strong"),
        "",
        "Top interesting features",
        *feature_lines(ranking_rows, "interesting"),
        "",
        "Prudent operational notes",
        "- This report is for offline research only.",
        "- Strong or interesting features are hypotheses, not trading rules.",
        "- Validate stability across symbols, timeframes, date ranges, and out-of-sample data.",
        "- Do not use these rankings as live signals without separate validation and risk controls.",
        "- This script does not run backtests, place orders, or call order execution APIs.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def aggregate_rankings(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["feature"])].append(row)

    aggregate_rows = []
    for feature, feature_rows in grouped.items():
        total_scores = [int(row["total_score"]) for row in feature_rows]
        strong_count = sum(1 for row in feature_rows if row["interpretation"] == "strong")
        interesting_count = sum(1 for row in feature_rows if row["interpretation"] == "interesting")
        weak_count = sum(1 for row in feature_rows if row["interpretation"] == "weak")
        ignore_count = sum(1 for row in feature_rows if row["interpretation"] == "ignore")
        aggregate_rows.append(
            {
                "direction": str(feature_rows[0].get("direction", "")),
                "feature": feature,
                "reports_count": len(feature_rows),
                "avg_total_score": sum(total_scores) / len(total_scores),
                "max_total_score": max(total_scores),
                "strong_count": strong_count,
                "interesting_count": interesting_count,
                "weak_count": weak_count,
                "ignore_count": ignore_count,
                "report_dirs": " | ".join(sorted(str(row["report_dir"]) for row in feature_rows)),
            }
        )

    return sorted(
        aggregate_rows,
        key=lambda row: (
            -int(row["strong_count"]),
            -int(row["interesting_count"]),
            -float(row["avg_total_score"]),
            str(row["feature"]),
        ),
    )


def write_aggregate_ranking(output_dir: Path, rows: list[dict[str, object]]) -> Path | None:
    if not rows:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / OUTPUT_AGGREGATE
    fieldnames = [
        "direction",
        "feature",
        "reports_count",
        "avg_total_score",
        "max_total_score",
        "strong_count",
        "interesting_count",
        "weak_count",
        "ignore_count",
        "report_dirs",
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def analyze_one_report_dir(input_dir: Path, output_dir: Path, top_n: int, direction: str) -> list[dict[str, object]]:
    ranking_rows = build_feature_ranking(input_dir, top_n, direction)
    model_metrics = read_model_metrics(input_dir)
    ranking_path = write_feature_ranking(output_dir, ranking_rows)
    summary_path = write_research_summary(output_dir, ranking_rows, model_metrics)

    print(f"Analyzed ML research directory: {input_dir}")
    print(f"Feature ranking written: {ranking_path}")
    print(f"Research summary written: {summary_path}")
    print("Top ranked features:")
    for row in ranking_rows[:top_n]:
        print(f"- {row['feature']}: score={row['total_score']} ({row['interpretation']})")
    return ranking_rows


def analyze_reports(input_dir: Path | None, output_dir: Path | None, top_n: int, direction: str) -> None:
    if top_n <= 0:
        raise ValueError("--top-n must be greater than zero.")

    direction = normalize_direction(direction)
    report_dirs = discover_report_dirs(input_dir, direction)
    all_ranking_rows: list[dict[str, object]] = []
    single_dir_mode = len(report_dirs) == 1 and (input_dir is not None and has_report_files(input_dir))

    print("ML research directories selected for analysis:")
    for report_dir in report_dirs:
        print(f"- {report_dir}")

    for report_dir in report_dirs:
        destination = output_dir if single_dir_mode and output_dir is not None else report_dir
        all_ranking_rows.extend(analyze_one_report_dir(report_dir, destination, top_n, direction))

    if len(report_dirs) > 1:
        aggregate_output_dir = output_dir or DEFAULT_REPORT_DIR / direction
        aggregate_rows = aggregate_rankings(all_ranking_rows)
        aggregate_path = write_aggregate_ranking(aggregate_output_dir, aggregate_rows)
        if aggregate_path is not None:
            print(f"Aggregate feature ranking written: {aggregate_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze ML research report CSVs and build robust feature rankings."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="Optional report folder. If omitted, all reports/ml_research/* folders are analyzed.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional output folder. For multi-folder analysis, per-symbol rankings remain in each folder.",
    )
    parser.add_argument("--top-n", type=int, default=20, help="Top N features per report to score. Default: 20")
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        analyze_reports(args.input_dir, args.output_dir, args.top_n, args.direction)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Research report analysis failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
