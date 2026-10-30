"""Compare offline ML research diagnostics across supervised targets.

This utility is research-only. It reads or generates `ml_research.py` outputs
under target-specific folders, then summarizes model and threshold diagnostics
without creating trading signals or changing model-training behavior.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sqlite3
import subprocess
import sys

try:
    from research_metrics import normalize_direction
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.compare_ml_target_reports
    from scripts.research_metrics import normalize_direction
try:
    from target_families import barrier_hit_first_column, preferred_hit_first_columns
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.compare_ml_target_reports
    from scripts.target_families import barrier_hit_first_column, preferred_hit_first_columns


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_REPORTS_ROOT = BASE_DIR / "reports" / "ml_research"
ML_DATASET_TABLE = "ml_dataset"
MODEL_METRICS_FILE = "model_metrics.csv"
THRESHOLD_ANALYSIS_FILE = "threshold_analysis.csv"
COMPARISON_CSV_FILE = "target_comparison.csv"
COMPARISON_REPORT_FILE = "target_comparison_report.md"
COMPARISON_OUTPUT_FILES = (COMPARISON_CSV_FILE, COMPARISON_REPORT_FILE)

COMPARISON_FIELDNAMES = [
    "symbol",
    "timeframe",
    "direction",
    "horizon",
    "target",
    "rows_total",
    "rows_train",
    "rows_test",
    "features_used",
    "train_positive_ratio",
    "test_positive_ratio",
    "base_positive_ratio",
    "accuracy",
    "precision",
    "recall",
    "f1",
    "roc_auc",
    "average_precision_score",
    "average_precision_lift_vs_base",
    "brier_score_loss",
    "purge_overlap",
    "embargo_bars",
    "non_overlap_eval",
    "best_f1_threshold",
    "best_f1_predicted_positive_count",
    "best_f1_precision",
    "best_f1_recall",
    "best_f1_value",
    "best_f1_lift",
    "best_lift_threshold",
    "best_lift_predicted_positive_count",
    "best_lift_precision",
    "best_lift_recall",
    "best_lift_value",
    "best_directional_return_threshold",
    "best_directional_return_predicted_positive_count",
    "best_directional_return_mean",
    "best_directional_return_median",
    "recommended_research_threshold",
    "recommended_predicted_positive_count",
    "recommended_precision",
    "recommended_recall",
    "recommended_lift_vs_base_precision",
    "recommended_mean_directional_return",
    "recommended_median_directional_return",
    "low_sample_threshold",
    "no_threshold_passed",
    "missing_reports",
    "notes",
]


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def safe_int(value: object) -> int | None:
    parsed = safe_float(value)
    if parsed is None:
        return None
    return int(parsed)


def safe_ratio(numerator: object, denominator: object) -> float | None:
    num = safe_float(numerator)
    den = safe_float(denominator)
    if num is None or den is None or den == 0:
        return None
    return num / den


def csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return bool_text(value)
    return value


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def read_model_metrics(path: Path) -> dict[str, str]:
    rows = read_csv_rows(path)
    return {
        str(row.get("metric", "")).strip(): str(row.get("value", "")).strip()
        for row in rows
        if str(row.get("metric", "")).strip()
    }


def validate_target_name(target: str) -> str:
    name = str(target or "").strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name or ".." in name.split("_"):
        raise ValueError(f"Unsafe target name: {target!r}")
    return name


def default_target_candidates(direction: str, horizon: int) -> list[str]:
    normalized = normalize_direction(direction)
    if normalized == "long":
        return [
            f"target_up_{horizon}",
            f"target_long_good_{horizon}",
            barrier_hit_first_column("long", 1.0, 1.0, horizon),
            *preferred_hit_first_columns("long", horizon),
        ]
    return [
        f"target_down_{horizon}",
        f"target_short_good_{horizon}",
        barrier_hit_first_column("short", 1.0, 1.0, horizon),
        *preferred_hit_first_columns("short", horizon),
    ]


def ml_dataset_columns(db_path: Path) -> set[str]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found while deriving target list: {db_path}")
    with sqlite3.connect(db_path) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (ML_DATASET_TABLE,),
        ).fetchone()
        if table is None:
            raise sqlite3.OperationalError(f"Table {ML_DATASET_TABLE!r} does not exist.")
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({ML_DATASET_TABLE})")}


def resolve_targets(
    *,
    direction: str,
    horizon: int,
    db_path: Path,
    explicit_targets: list[str] | None = None,
) -> list[str]:
    if explicit_targets:
        return [validate_target_name(target) for target in explicit_targets]

    candidates = default_target_candidates(direction, horizon)
    if horizon == 10:
        return candidates

    columns = ml_dataset_columns(db_path)
    targets = [target for target in candidates if target in columns]
    if not targets:
        raise ValueError(
            f"No default {direction} h{horizon} target columns were found in {ML_DATASET_TABLE}."
        )
    return targets


def target_run_dir(
    reports_root: Path,
    *,
    direction: str,
    symbol: str,
    timeframe: str,
    horizon: int,
    target: str,
) -> Path:
    return (
        reports_root
        / "target_runs"
        / direction
        / f"{symbol}_{timeframe}_h{horizon}"
        / validate_target_name(target)
    )


def comparison_output_dir(
    reports_root: Path,
    *,
    direction: str,
    symbol: str,
    timeframe: str,
    horizon: int,
) -> Path:
    return reports_root / "target_comparison" / direction / f"{symbol}_{timeframe}_h{horizon}"


def ensure_can_write_comparison(output_dir: Path, overwrite: bool) -> None:
    existing = [output_dir / file_name for file_name in COMPARISON_OUTPUT_FILES if (output_dir / file_name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Comparison output already exists under {output_dir}. Pass --overwrite to regenerate it."
        )


def run_ml_research_for_target(
    *,
    symbol: str,
    timeframe: str,
    direction: str,
    horizon: int,
    target: str,
    db_path: Path,
    output_dir: Path,
    purge_overlap: bool,
    embargo_bars: int,
    non_overlap_eval: bool,
) -> None:
    command = [
        sys.executable,
        str(BASE_DIR / "scripts" / "ml_research.py"),
        "--symbol",
        symbol,
        "--timeframe",
        timeframe,
        "--direction",
        direction,
        "--target",
        target,
        "--return-target",
        f"future_return_{horizon}",
        "--db-path",
        str(db_path),
        "--output-dir",
        str(output_dir),
        "--embargo-bars",
        str(embargo_bars),
    ]
    if purge_overlap:
        command.append("--purge-overlap")
    if non_overlap_eval:
        command.append("--non-overlap-eval")

    completed = subprocess.run(command, cwd=BASE_DIR, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        details = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        raise RuntimeError(f"ml_research.py failed for target {target!r}.\n{details}")


def row_score(row: dict[str, str], column: str) -> float:
    value = safe_float(row.get(column))
    return value if value is not None else float("-inf")


def threshold_count(row: dict[str, str]) -> int:
    return safe_int(row.get("predicted_positive_count")) or 0


def best_threshold_row(
    rows: list[dict[str, str]],
    score_column: str,
    *,
    min_predicted_positive_count: int | None = None,
) -> dict[str, str] | None:
    candidates = [
        row
        for row in rows
        if safe_float(row.get(score_column)) is not None
        and (
            min_predicted_positive_count is None
            or threshold_count(row) >= min_predicted_positive_count
        )
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: row_score(row, score_column))


def recommended_threshold_row(
    rows: list[dict[str, str]],
    *,
    min_predicted_positive_count: int,
) -> dict[str, str] | None:
    eligible = []
    for row in rows:
        lift = safe_float(row.get("lift_vs_base_precision"))
        mean_directional = safe_float(row.get("mean_directional_return_target_for_predicted_positive"))
        median_directional = safe_float(row.get("median_directional_return_target_for_predicted_positive"))
        if (
            threshold_count(row) >= min_predicted_positive_count
            and lift is not None
            and mean_directional is not None
            and median_directional is not None
            and lift > 1.25
            and mean_directional > 0
            and median_directional > 0
        ):
            eligible.append(row)

    if not eligible:
        return None
    return max(
        eligible,
        key=lambda row: (
            row_score(row, "lift_vs_base_precision"),
            row_score(row, "mean_directional_return_target_for_predicted_positive"),
        ),
    )


def first_numeric(rows: list[dict[str, str]], column: str) -> float | None:
    for row in rows:
        value = safe_float(row.get(column))
        if value is not None:
            return value
    return None


def first_threshold_metadata(rows: list[dict[str, str]]) -> dict[str, float | None]:
    return {
        "base_positive_ratio": first_numeric(rows, "base_positive_ratio"),
        "average_precision_score": first_numeric(rows, "average_precision_score"),
        "brier_score_loss": first_numeric(rows, "brier_score_loss"),
    }


def require_directional_columns(rows: list[dict[str, str]], target: str) -> None:
    if not rows:
        return
    required = {
        "mean_directional_return_target_for_predicted_positive",
        "median_directional_return_target_for_predicted_positive",
    }
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(
            "threshold_analysis.csv is missing directional return columns for "
            f"{target}. Rerun scripts/ml_research.py after the directional-return update. "
            f"Missing columns: {', '.join(missing)}"
        )


def empty_comparison_row(
    *,
    symbol: str,
    timeframe: str,
    direction: str,
    horizon: int,
    target: str,
    missing_reports: bool,
    notes: str,
) -> dict[str, object]:
    row = {field: "" for field in COMPARISON_FIELDNAMES}
    row.update(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "horizon": horizon,
            "target": target,
            "low_sample_threshold": "",
            "no_threshold_passed": "",
            "missing_reports": bool_text(missing_reports),
            "notes": notes,
        }
    )
    return row


def comparison_row_for_target(
    *,
    symbol: str,
    timeframe: str,
    direction: str,
    horizon: int,
    target: str,
    report_dir: Path,
    min_predicted_positive_count: int,
) -> dict[str, object]:
    metrics_path = report_dir / MODEL_METRICS_FILE
    threshold_path = report_dir / THRESHOLD_ANALYSIS_FILE
    missing = [
        path.name
        for path in (metrics_path, threshold_path)
        if not path.exists()
    ]
    if missing:
        return empty_comparison_row(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            horizon=horizon,
            target=target,
            missing_reports=True,
            notes=f"missing reports: {', '.join(missing)}",
        )

    metrics = read_model_metrics(metrics_path)
    threshold_rows = read_csv_rows(threshold_path)
    require_directional_columns(threshold_rows, target)

    threshold_metadata = first_threshold_metadata(threshold_rows)
    base_positive_ratio = threshold_metadata["base_positive_ratio"]
    average_precision_score = threshold_metadata["average_precision_score"]
    average_precision_lift = safe_ratio(average_precision_score, base_positive_ratio)

    best_f1 = best_threshold_row(threshold_rows, "f1")
    best_lift = best_threshold_row(
        threshold_rows,
        "lift_vs_base_precision",
        min_predicted_positive_count=min_predicted_positive_count,
    )
    best_directional = best_threshold_row(
        threshold_rows,
        "mean_directional_return_target_for_predicted_positive",
        min_predicted_positive_count=min_predicted_positive_count,
    )
    recommended = recommended_threshold_row(
        threshold_rows,
        min_predicted_positive_count=min_predicted_positive_count,
    )
    has_min_count_row = any(threshold_count(row) >= min_predicted_positive_count for row in threshold_rows)
    low_sample_threshold = not has_min_count_row
    no_threshold_passed = recommended is None
    notes: list[str] = []
    if low_sample_threshold:
        notes.append(f"no threshold has predicted_positive_count >= {min_predicted_positive_count}")
    if no_threshold_passed:
        notes.append("no threshold passed conservative diagnostic criteria")

    row: dict[str, object] = {
        "symbol": metrics.get("symbol", symbol),
        "timeframe": metrics.get("timeframe", timeframe),
        "direction": metrics.get("direction", direction),
        "horizon": metrics.get("horizon", horizon),
        "target": metrics.get("target", target),
        "rows_total": metrics.get("rows_total", ""),
        "rows_train": metrics.get("rows_train", ""),
        "rows_test": metrics.get("rows_test", ""),
        "features_used": metrics.get("features_used", ""),
        "train_positive_ratio": metrics.get("train_positive_ratio", ""),
        "test_positive_ratio": metrics.get("test_positive_ratio", ""),
        "base_positive_ratio": base_positive_ratio,
        "accuracy": metrics.get("accuracy", ""),
        "precision": metrics.get("precision", ""),
        "recall": metrics.get("recall", ""),
        "f1": metrics.get("f1", ""),
        "roc_auc": metrics.get("roc_auc", ""),
        "average_precision_score": average_precision_score,
        "average_precision_lift_vs_base": average_precision_lift,
        "brier_score_loss": threshold_metadata["brier_score_loss"],
        "purge_overlap": metrics.get("purge_overlap", ""),
        "embargo_bars": metrics.get("embargo_bars", ""),
        "non_overlap_eval": metrics.get("non_overlap_eval", ""),
        "best_f1_threshold": best_f1.get("threshold", "") if best_f1 else "",
        "best_f1_predicted_positive_count": (
            best_f1.get("predicted_positive_count", "") if best_f1 else ""
        ),
        "best_f1_precision": best_f1.get("precision", "") if best_f1 else "",
        "best_f1_recall": best_f1.get("recall", "") if best_f1 else "",
        "best_f1_value": best_f1.get("f1", "") if best_f1 else "",
        "best_f1_lift": best_f1.get("lift_vs_base_precision", "") if best_f1 else "",
        "best_lift_threshold": best_lift.get("threshold", "") if best_lift else "",
        "best_lift_predicted_positive_count": (
            best_lift.get("predicted_positive_count", "") if best_lift else ""
        ),
        "best_lift_precision": best_lift.get("precision", "") if best_lift else "",
        "best_lift_recall": best_lift.get("recall", "") if best_lift else "",
        "best_lift_value": best_lift.get("lift_vs_base_precision", "") if best_lift else "",
        "best_directional_return_threshold": best_directional.get("threshold", "") if best_directional else "",
        "best_directional_return_predicted_positive_count": (
            best_directional.get("predicted_positive_count", "") if best_directional else ""
        ),
        "best_directional_return_mean": (
            best_directional.get("mean_directional_return_target_for_predicted_positive", "")
            if best_directional
            else ""
        ),
        "best_directional_return_median": (
            best_directional.get("median_directional_return_target_for_predicted_positive", "")
            if best_directional
            else ""
        ),
        "recommended_research_threshold": recommended.get("threshold", "") if recommended else "",
        "recommended_predicted_positive_count": (
            recommended.get("predicted_positive_count", "") if recommended else ""
        ),
        "recommended_precision": recommended.get("precision", "") if recommended else "",
        "recommended_recall": recommended.get("recall", "") if recommended else "",
        "recommended_lift_vs_base_precision": (
            recommended.get("lift_vs_base_precision", "") if recommended else ""
        ),
        "recommended_mean_directional_return": (
            recommended.get("mean_directional_return_target_for_predicted_positive", "")
            if recommended
            else ""
        ),
        "recommended_median_directional_return": (
            recommended.get("median_directional_return_target_for_predicted_positive", "")
            if recommended
            else ""
        ),
        "low_sample_threshold": bool_text(low_sample_threshold),
        "no_threshold_passed": bool_text(no_threshold_passed),
        "missing_reports": bool_text(False),
        "notes": "; ".join(notes),
    }
    return row


def build_comparison_rows(
    *,
    reports_root: Path,
    symbol: str,
    timeframe: str,
    direction: str,
    horizon: int,
    targets: list[str],
    min_predicted_positive_count: int,
) -> list[dict[str, object]]:
    return [
        comparison_row_for_target(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            horizon=horizon,
            target=target,
            report_dir=target_run_dir(
                reports_root,
                direction=direction,
                symbol=symbol,
                timeframe=timeframe,
                horizon=horizon,
                target=target,
            ),
            min_predicted_positive_count=min_predicted_positive_count,
        )
        for target in targets
    ]


def write_comparison_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=COMPARISON_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in COMPARISON_FIELDNAMES})


def markdown_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return text if text else ""


def row_float(row: dict[str, object], column: str) -> float | None:
    return safe_float(row.get(column))


def best_row_by(rows: list[dict[str, object]], *columns: str) -> dict[str, object] | None:
    candidates = [
        row
        for row in rows
        if row.get("missing_reports") != "true" and any(row_float(row, column) is not None for column in columns)
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: tuple(
            row_float(row, column) if row_float(row, column) is not None else float("-inf")
            for column in columns
        ),
    )


def write_comparison_report(
    path: Path,
    *,
    rows: list[dict[str, object]],
    targets: list[str],
    min_predicted_positive_count: int,
) -> None:
    missing_rows = [row for row in rows if row.get("missing_reports") == "true"]
    low_sample_rows = [row for row in rows if row.get("low_sample_threshold") == "true"]
    best_ap = best_row_by(rows, "average_precision_lift_vs_base")
    recommended_rows = [
        row
        for row in rows
        if row.get("recommended_research_threshold") not in ("", None)
        and row.get("missing_reports") != "true"
    ]
    best_recommended = best_row_by(
        recommended_rows,
        "recommended_lift_vs_base_precision",
        "recommended_mean_directional_return",
    )

    lines = [
        "# ML Target Comparison Report",
        "",
        "This report is research-only. Recommended research thresholds are diagnostic filters only and are not trading signals.",
        "",
        "## Targets Compared",
        "",
        *[f"- `{target}`" for target in targets],
        "",
        "## Missing Reports",
        "",
    ]
    if missing_rows:
        lines.extend(f"- `{row['target']}`: {row.get('notes', '')}" for row in missing_rows)
    else:
        lines.append("- None.")

    lines.extend(["", "## Best Average Precision Lift", ""])
    if best_ap:
        lines.append(
            "- `{target}` with average_precision_lift_vs_base={lift}".format(
                target=best_ap.get("target", ""),
                lift=markdown_value(best_ap.get("average_precision_lift_vs_base")),
            )
        )
    else:
        lines.append("- Not available.")

    lines.extend(["", "## Best Recommended Research Threshold Quality", ""])
    if best_recommended:
        lines.append(
            "- `{target}` at threshold {threshold}, lift={lift}, mean_directional_return={mean_return}".format(
                target=best_recommended.get("target", ""),
                threshold=markdown_value(best_recommended.get("recommended_research_threshold")),
                lift=markdown_value(best_recommended.get("recommended_lift_vs_base_precision")),
                mean_return=markdown_value(best_recommended.get("recommended_mean_directional_return")),
            )
        )
    else:
        lines.append("- No target passed the conservative diagnostic criteria.")

    lines.extend(["", "## Warnings", ""])
    if low_sample_rows:
        lines.extend(
            f"- `{row['target']}` has no threshold with predicted_positive_count >= {min_predicted_positive_count}."
            for row in low_sample_rows
        )
    else:
        lines.append("- No low-sample threshold warnings.")
    lines.extend(
        [
            "- Accuracy can be misleading for imbalanced targets; compare it with precision, recall, F1, ROC AUC, average precision, base-rate lift, and directional-return diagnostics.",
            "- Average precision should be compared with `base_positive_ratio`; the lift column performs that base-rate comparison.",
            "- For short research, use directional-return columns because raw future returns are sign-flipped for interpretation.",
            "- Triple-barrier and future-path targets are supervised research labels only.",
            "- This comparison does not change model thresholds, generate operational signals, or alter pipeline selection methodology.",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_comparison_outputs(output_dir: Path, rows: list[dict[str, object]], targets: list[str], min_count: int) -> dict[str, Path]:
    csv_path = output_dir / COMPARISON_CSV_FILE
    report_path = output_dir / COMPARISON_REPORT_FILE
    write_comparison_csv(csv_path, rows)
    write_comparison_report(report_path, rows=rows, targets=targets, min_predicted_positive_count=min_count)
    return {"target_comparison_csv": csv_path, "target_comparison_report": report_path}


def compare_ml_targets(args: argparse.Namespace) -> dict[str, Path]:
    if args.embargo_bars < 0:
        raise ValueError("--embargo-bars cannot be negative.")
    if args.min_predicted_positive_count < 0:
        raise ValueError("--min-predicted-positive-count cannot be negative.")

    symbol = args.symbol.strip().upper()
    timeframe = args.timeframe.strip().upper()
    direction = normalize_direction(args.direction)
    reports_root = Path(args.reports_root)
    targets = resolve_targets(
        direction=direction,
        horizon=args.horizon,
        db_path=Path(args.db_path),
        explicit_targets=args.targets,
    )
    output_dir = comparison_output_dir(
        reports_root,
        direction=direction,
        symbol=symbol,
        timeframe=timeframe,
        horizon=args.horizon,
    )
    ensure_can_write_comparison(output_dir, args.overwrite)

    if args.run_ml_research:
        for target in targets:
            run_ml_research_for_target(
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                horizon=args.horizon,
                target=target,
                db_path=Path(args.db_path),
                output_dir=target_run_dir(
                    reports_root,
                    direction=direction,
                    symbol=symbol,
                    timeframe=timeframe,
                    horizon=args.horizon,
                    target=target,
                ),
                purge_overlap=args.purge_overlap,
                embargo_bars=args.embargo_bars,
                non_overlap_eval=args.non_overlap_eval,
            )

    rows = build_comparison_rows(
        reports_root=reports_root,
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        horizon=args.horizon,
        targets=targets,
        min_predicted_positive_count=args.min_predicted_positive_count,
    )
    return write_comparison_outputs(output_dir, rows, targets, args.min_predicted_positive_count)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare research-only ML target diagnostics without changing the standard ml_research output path."
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--direction", choices=("long", "short"), required=True)
    parser.add_argument("--horizon", type=int, choices=(5, 10, 20), default=10)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help=f"Default: {DEFAULT_DB_PATH}")
    parser.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT, help=f"Default: {DEFAULT_REPORTS_ROOT}")
    parser.add_argument("--run-ml-research", action="store_true")
    parser.add_argument("--purge-overlap", action="store_true")
    parser.add_argument("--embargo-bars", type=int, default=0)
    parser.add_argument("--non-overlap-eval", action="store_true")
    parser.add_argument("--targets", nargs="+")
    parser.add_argument("--min-predicted-positive-count", type=int, default=500)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite target_comparison.csv and target_comparison_report.md when they already exist.",
    )
    return parser.parse_args()


def main() -> int:
    try:
        paths = compare_ml_targets(parse_args())
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError, sqlite3.Error, OSError) as exc:
        print(f"ML target comparison failed: {exc}")
        return 1

    print("ML target comparison complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
