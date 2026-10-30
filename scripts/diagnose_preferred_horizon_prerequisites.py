"""Diagnose prerequisites for preferred horizon research runs.

This read-only diagnostic checks whether existing supervised target columns
and preferred feature shortlist inputs are present before preferred-feature
backtest orchestration. It does not run backtests, add features, create new
combinations, adjust TP/SL settings, or add broker execution logic.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from run_preferred_feature_backtests import (
        DEFAULT_INPUT_ROOT as DEFAULT_SHORTLIST_ROOT,
        SHORTLIST_FILE,
        select_priority_features,
    )
    from target_families import (
        PREFERRED_2ATR_1ATR_HIT_FIRST,
        family_scoped_root,
        supported_target_family_names,
        target_column_for_family,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.run_preferred_feature_backtests import (
        DEFAULT_INPUT_ROOT as DEFAULT_SHORTLIST_ROOT,
        SHORTLIST_FILE,
        select_priority_features,
    )
    from scripts.target_families import (
        PREFERRED_2ATR_1ATR_HIT_FIRST,
        family_scoped_root,
        supported_target_family_names,
        target_column_for_family,
    )


DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "preferred_horizon_prerequisites"
DEFAULT_GROUPS = ("fx", "xauusd")
DEFAULT_DIRECTIONS = ("long", "short")
OUTPUT_CSV = "prerequisite_diagnostics.csv"
OUTPUT_REPORT = "prerequisite_diagnostics.md"
TABLE_NAME = "ml_dataset"

FIELDNAMES = [
    "run_id",
    "group_name",
    "symbol",
    "direction",
    "timeframe",
    "horizon",
    "target_family",
    "target_column",
    "target_column_exists",
    "total_rows",
    "valid_target_rows",
    "non_null_target_rows",
    "null_count",
    "positive_count",
    "negative_count",
    "positive_rate",
    "null_rate",
    "positive_rate_flag",
    "preferred_shortlist_exists",
    "preferred_shortlist_rows",
    "candidate_features_after_safety_filter",
    "candidate_features_available_for_backtest",
    "strict_shortlist_only_would_produce_zero_rows",
    "root_cause",
    "notes",
]

ROOT_CAUSES = {
    "target_column_missing",
    "target_all_null",
    "target_too_sparse",
    "target_too_unbalanced",
    "preferred_shortlist_missing",
    "preferred_shortlist_empty",
    "feature_name_mismatch",
    "no_candidate_features_after_safety_filter",
    "sufficient_prerequisites_available",
    "unknown",
}


@dataclass(frozen=True)
class DatasetStats:
    target_column_exists: bool
    total_rows: int
    non_null_target_rows: int
    positive_count: int
    negative_count: int
    feature_columns: set[str]


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def format_multiplier(value: float) -> str:
    return f"{float(value):g}".replace(".", "p")


def target_column_for(direction: str, target_family: str, horizon: int) -> str:
    return target_column_for_family(direction, target_family, horizon)


def normalize_values(values: Iterable[object], *, upper: bool = False, lower: bool = False) -> list[str]:
    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if upper:
            text = text.upper()
        if lower:
            text = text.lower()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def group_symbols(args: argparse.Namespace) -> dict[str, tuple[str, ...]]:
    groups = normalize_values(args.groups, lower=True)
    mapping = {
        "fx": tuple(normalize_values(args.symbols_fx, upper=True)),
        "xauusd": tuple(normalize_values(args.symbols_xauusd, upper=True)),
    }
    unknown = [group for group in groups if group not in mapping]
    if unknown:
        raise ValueError(f"Unsupported group(s): {', '.join(unknown)}")
    selected = {group: mapping[group] for group in groups}
    empty = [group for group, symbols in selected.items() if not symbols]
    if empty:
        raise ValueError(f"Groups require at least one symbol: {', '.join(empty)}")
    return selected


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "prerequisite_diagnostics": output_dir / OUTPUT_CSV,
        "prerequisite_report": output_dir / OUTPUT_REPORT,
    }


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return [dict(row) for row in csv.DictReader(csv_file)]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in FIELDNAMES})


def table_exists(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    ).fetchone()
    return row is not None


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def ml_dataset_columns(connection: sqlite3.Connection) -> list[str]:
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()]


def dataset_stats(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    timeframe: str,
    target_column: str,
) -> DatasetStats:
    columns = ml_dataset_columns(connection)
    column_set = set(columns)
    total_rows = int(
        connection.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe),
        ).fetchone()[0]
    )
    if target_column not in column_set:
        return DatasetStats(
            target_column_exists=False,
            total_rows=total_rows,
            non_null_target_rows=0,
            positive_count=0,
            negative_count=0,
            feature_columns=column_set,
        )

    quoted = quote_identifier(target_column)
    row = connection.execute(
        f"""
        SELECT
            SUM(CASE WHEN {quoted} IS NOT NULL THEN 1 ELSE 0 END) AS non_null_target_rows,
            SUM(CASE WHEN {quoted} = 1 THEN 1 ELSE 0 END) AS positive_count
        FROM {TABLE_NAME}
        WHERE symbol = ?
          AND timeframe = ?
        """,
        (symbol, timeframe),
    ).fetchone()
    non_null = int(row[0] or 0)
    positives = int(row[1] or 0)
    return DatasetStats(
        target_column_exists=True,
        total_rows=total_rows,
        non_null_target_rows=non_null,
        positive_count=positives,
        negative_count=max(non_null - positives, 0),
        feature_columns=column_set,
    )


def shortlist_path(shortlist_root: Path, *, direction: str, timeframe: str, horizon: int) -> Path:
    return shortlist_root / direction / f"{timeframe}_h{int(horizon)}" / SHORTLIST_FILE


def safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def positive_rate_flag(positive_rate: float | None) -> str:
    if positive_rate is None:
        return "missing"
    if positive_rate < 0.10:
        return "below_initial_range"
    if positive_rate > 0.50:
        return "above_initial_range"
    return "within_initial_range"


def classify_root_cause(
    *,
    stats: DatasetStats,
    shortlist_exists: bool,
    shortlist_rows_count: int,
    candidate_features_after_safety: int,
    candidate_features_available: int,
    min_non_null_target_rows: int,
    min_positive_target_rows: int,
    min_negative_target_rows: int,
    min_positive_rate: float,
    max_positive_rate: float,
) -> str:
    if not stats.target_column_exists:
        return "target_column_missing"
    if stats.non_null_target_rows == 0:
        return "target_all_null"
    if stats.non_null_target_rows < min_non_null_target_rows:
        return "target_too_sparse"
    positive_rate = safe_ratio(stats.positive_count, stats.non_null_target_rows)
    if (
        positive_rate is None
        or stats.positive_count < min_positive_target_rows
        or stats.negative_count < min_negative_target_rows
        or positive_rate < min_positive_rate
        or positive_rate > max_positive_rate
    ):
        return "target_too_unbalanced"
    if not shortlist_exists:
        return "preferred_shortlist_missing"
    if shortlist_rows_count == 0:
        return "preferred_shortlist_empty"
    if candidate_features_after_safety == 0:
        return "no_candidate_features_after_safety_filter"
    if candidate_features_available == 0:
        return "feature_name_mismatch"
    return "sufficient_prerequisites_available"


def diagnostic_notes(
    *,
    root_cause: str,
    shortlist_path_value: Path,
    missing_features: list[str],
) -> str:
    if root_cause == "target_column_missing":
        return "target column is absent from ml_dataset"
    if root_cause == "preferred_shortlist_missing":
        return f"missing preferred shortlist: {shortlist_path_value}"
    if root_cause == "preferred_shortlist_empty":
        return f"preferred shortlist has no rows: {shortlist_path_value}"
    if root_cause == "feature_name_mismatch":
        return "selected shortlist features not found in ml_dataset columns: " + ", ".join(missing_features[:10])
    if root_cause == "no_candidate_features_after_safety_filter":
        return "shortlist rows exist but none pass controlled-testing and caution filters"
    if root_cause in {"target_all_null", "target_too_sparse", "target_too_unbalanced"}:
        return "target distribution is not usable under the configured diagnostic thresholds"
    if root_cause == "sufficient_prerequisites_available":
        return "target and preferred shortlist prerequisites are present"
    return "unable to classify prerequisite state"


def diagnostic_row(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    group_name: str,
    symbol: str,
    direction: str,
    timeframe: str,
    horizon: int,
    target_family: str,
    shortlist_root: Path,
    min_non_null_target_rows: int,
    min_positive_target_rows: int,
    min_negative_target_rows: int,
    min_positive_rate: float,
    max_positive_rate: float,
) -> dict[str, object]:
    target_column = target_column_for(direction, target_family, horizon)
    stats = dataset_stats(connection, symbol=symbol, timeframe=timeframe, target_column=target_column)
    shortlist_path_value = shortlist_path(shortlist_root, direction=direction, timeframe=timeframe, horizon=horizon)
    shortlist_exists = shortlist_path_value.exists()
    shortlist_rows = read_csv_rows(shortlist_path_value)
    selected_rows = select_priority_features(shortlist_rows, direction=direction, max_features=None)
    selected_features = [str(row.get("feature") or "").strip() for row in selected_rows if str(row.get("feature") or "").strip()]
    available_features = [feature for feature in selected_features if feature in stats.feature_columns]
    missing_features = [feature for feature in selected_features if feature not in stats.feature_columns]
    positive_rate = safe_ratio(stats.positive_count, stats.non_null_target_rows)
    null_rate = safe_ratio(stats.total_rows - stats.non_null_target_rows, stats.total_rows)
    root_cause = classify_root_cause(
        stats=stats,
        shortlist_exists=shortlist_exists,
        shortlist_rows_count=len(shortlist_rows),
        candidate_features_after_safety=len(selected_features),
        candidate_features_available=len(available_features),
        min_non_null_target_rows=min_non_null_target_rows,
        min_positive_target_rows=min_positive_target_rows,
        min_negative_target_rows=min_negative_target_rows,
        min_positive_rate=min_positive_rate,
        max_positive_rate=max_positive_rate,
    )
    strict_zero = root_cause != "sufficient_prerequisites_available"
    return {
        "run_id": run_id,
        "group_name": group_name,
        "symbol": symbol,
        "direction": direction,
        "timeframe": timeframe,
        "horizon": horizon,
        "target_family": target_family,
        "target_column": target_column,
        "target_column_exists": bool_text(stats.target_column_exists),
        "total_rows": stats.total_rows,
        "valid_target_rows": stats.non_null_target_rows,
        "non_null_target_rows": stats.non_null_target_rows,
        "null_count": max(stats.total_rows - stats.non_null_target_rows, 0),
        "positive_count": stats.positive_count,
        "negative_count": stats.negative_count,
        "positive_rate": positive_rate,
        "null_rate": null_rate,
        "positive_rate_flag": positive_rate_flag(positive_rate),
        "preferred_shortlist_exists": bool_text(shortlist_exists),
        "preferred_shortlist_rows": len(shortlist_rows),
        "candidate_features_after_safety_filter": len(selected_features),
        "candidate_features_available_for_backtest": len(available_features),
        "strict_shortlist_only_would_produce_zero_rows": bool_text(strict_zero),
        "root_cause": root_cause if root_cause in ROOT_CAUSES else "unknown",
        "notes": diagnostic_notes(
            root_cause=root_cause,
            shortlist_path_value=shortlist_path_value,
            missing_features=missing_features,
        ),
    }


def rows_by_key(rows: list[dict[str, object]], key: str) -> list[str]:
    if not rows:
        return ["- None."]
    counts = Counter(str(row.get(key) or "") for row in rows)
    return [f"- `{name}`: `{count}`" for name, count in sorted(counts.items())]


def target_availability_lines(rows: list[dict[str, object]]) -> list[str]:
    lines = [
        "| Horizon | Direction | Target column | Exists rows | Missing rows |",
        "|---:|---:|---|---:|---:|",
    ]
    grouped: dict[tuple[object, object, object], Counter[str]] = {}
    for row in rows:
        key = (row["horizon"], row["direction"], row["target_column"])
        grouped.setdefault(key, Counter())
        grouped[key][str(row["target_column_exists"])] += 1
    for key, counts in sorted(grouped.items(), key=lambda item: (int(item[0][0]), str(item[0][1]))):
        horizon, direction, target_column = key
        lines.append(
            f"| `{horizon}` | `{direction}` | `{target_column}` | "
            f"`{counts.get('true', 0)}` | `{counts.get('false', 0)}` |"
        )
    return lines


def class_balance_lines(rows: list[dict[str, object]], limit: int = 18) -> list[str]:
    lines = [
        "| Group | Symbol | Direction | Horizon | Valid rows | Positives | Negatives | Positive rate | Positive-rate flag | NULL rate |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for row in rows[:limit]:
        lines.append(
            f"| `{row['group_name']}` | `{row['symbol']}` | `{row['direction']}` | `{row['horizon']}` | "
            f"`{row['valid_target_rows']}` | `{row['positive_count']}` | `{row['negative_count']}` | "
            f"`{row['positive_rate']}` | `{row['positive_rate_flag']}` | `{row['null_rate']}` |"
        )
    if len(rows) > limit:
        lines.append(f"| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |")
    return lines


def shortlist_availability_lines(rows: list[dict[str, object]]) -> list[str]:
    lines = [
        "| Horizon | Direction | Shortlist present rows | Shortlist missing rows | Candidate feature rows |",
        "|---:|---:|---:|---:|---:|",
    ]
    grouped: dict[tuple[object, object], dict[str, int]] = {}
    for row in rows:
        key = (row["horizon"], row["direction"])
        bucket = grouped.setdefault(key, {"present": 0, "missing": 0, "candidates": 0})
        if row["preferred_shortlist_exists"] == "true":
            bucket["present"] += 1
        else:
            bucket["missing"] += 1
        bucket["candidates"] += int(row["candidate_features_available_for_backtest"] or 0)
    for key, values in sorted(grouped.items(), key=lambda item: (int(item[0][0]), str(item[0][1]))):
        horizon, direction = key
        lines.append(
            f"| `{horizon}` | `{direction}` | `{values['present']}` | "
            f"`{values['missing']}` | `{values['candidates']}` |"
        )
    return lines


def root_cause_table_lines(rows: list[dict[str, object]], limit: int = 36) -> list[str]:
    lines = [
        "| Group | Symbol | Direction | Horizon | Target | Shortlist rows | Candidates | Root cause |",
        "|---|---|---:|---:|---|---:|---:|---|",
    ]
    for row in rows[:limit]:
        lines.append(
            f"| `{row['group_name']}` | `{row['symbol']}` | `{row['direction']}` | `{row['horizon']}` | "
            f"`{row['target_column']}` | `{row['preferred_shortlist_rows']}` | "
            f"`{row['candidate_features_available_for_backtest']}` | `{row['root_cause']}` |"
        )
    if len(rows) > limit:
        lines.append("| ... | ... | ... | ... | ... | ... | ... | ... |")
    return lines


def recommended_next_action(rows: list[dict[str, object]]) -> str:
    causes = Counter(str(row.get("root_cause") or "") for row in rows)
    if causes.get("target_column_missing"):
        return (
            "Generate or verify the missing preferred target columns for the affected horizons before rerunning "
            "preferred feature stability, shortlist, and backtest diagnostics."
        )
    if causes.get("preferred_shortlist_missing") or causes.get("preferred_shortlist_empty"):
        return "Build the missing preferred target stability and preferred feature shortlist inputs for the affected horizons."
    if causes.get("no_candidate_features_after_safety_filter") or causes.get("feature_name_mismatch"):
        return "Inspect shortlist feature names and caution filters before rerunning preferred feature backtests."
    if set(causes) == {"sufficient_prerequisites_available"}:
        return "Prerequisites are present; investigate downstream preferred backtest summaries and skipped outputs."
    return "Review the root-cause table and inspect the first failing prerequisite for each row."


def write_report(path: Path, *, run_id: str, args: argparse.Namespace, rows: list[dict[str, object]]) -> None:
    lines = [
        "# Preferred Horizon Prerequisite Diagnostics",
        "",
        "## Research-only warning",
        "",
        "- Offline prerequisite audit over existing dataset and shortlist files only.",
        "- No backtests are run, no features are added, and no combinations are searched.",
        "- Not operational guidance and not broker execution.",
        "",
        "## Configuration",
        "",
        f"- Run ID: `{run_id}`",
        f"- Timeframe: `{args.timeframe}`",
        f"- Horizons: `{', '.join(str(item) for item in args.horizons)}`",
        f"- Groups: `{', '.join(args.groups)}`",
        f"- Target family: `{args.target_family}`",
        f"- Database: `{args.db_path}`",
        f"- Shortlist root: `{args.shortlist_root}`",
        "",
        "## Summary by horizon",
        "",
        *rows_by_key(rows, "horizon"),
        "",
        "## Summary by group",
        "",
        *rows_by_key(rows, "group_name"),
        "",
        "## Target availability",
        "",
        *target_availability_lines(rows),
        "",
        "## Target class balance",
        "",
        *class_balance_lines(rows),
        "",
        "## Preferred shortlist availability",
        "",
        *shortlist_availability_lines(rows),
        "",
        "## Root cause table",
        "",
        *root_cause_table_lines(rows),
        "",
        "## Root cause summary",
        "",
        *rows_by_key(rows, "root_cause"),
        "",
        "## Recommended next action",
        "",
        f"- {recommended_next_action(rows)}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def diagnose_preferred_horizon_prerequisites(args: argparse.Namespace) -> dict[str, Path]:
    run_id = str(args.run_id or current_run_id())
    if not getattr(args, "target_family", None):
        args.target_family = PREFERRED_2ATR_1ATR_HIT_FIRST
    args.shortlist_root = family_scoped_root(Path(args.shortlist_root), str(args.target_family))
    db_path = Path(args.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    timeframe = str(args.timeframe).strip().upper()
    horizons = [int(value) for value in args.horizons]
    directions = normalize_values(args.directions, lower=True)
    groups = group_symbols(args)
    rows: list[dict[str, object]] = []
    with sqlite3.connect(db_path) as connection:
        if not table_exists(connection):
            raise sqlite3.OperationalError(f"Table {TABLE_NAME!r} does not exist.")
        for group_name, symbols in groups.items():
            for symbol in symbols:
                for direction in directions:
                    for horizon in horizons:
                        rows.append(
                            diagnostic_row(
                                connection=connection,
                                run_id=run_id,
                                group_name=group_name,
                                symbol=symbol,
                                direction=direction,
                                timeframe=timeframe,
                                horizon=horizon,
                                target_family=str(args.target_family),
                                shortlist_root=Path(args.shortlist_root),
                                min_non_null_target_rows=int(args.min_non_null_target_rows),
                                min_positive_target_rows=int(args.min_positive_target_rows),
                                min_negative_target_rows=int(args.min_negative_target_rows),
                                min_positive_rate=float(args.min_positive_rate),
                                max_positive_rate=float(args.max_positive_rate),
                            )
                        )

    outputs = output_paths(Path(args.output_root), run_id)
    write_csv(outputs["prerequisite_diagnostics"], rows)
    write_report(outputs["prerequisite_report"], run_id=run_id, args=args, rows=rows)
    return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose research-only prerequisites for preferred horizon runs."
    )
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--horizons", nargs="+", type=int, default=[5, 10, 20])
    parser.add_argument("--groups", nargs="+", default=list(DEFAULT_GROUPS))
    parser.add_argument("--directions", nargs="+", choices=DEFAULT_DIRECTIONS, default=list(DEFAULT_DIRECTIONS))
    parser.add_argument(
        "--target-family",
        choices=supported_target_family_names(),
        default=PREFERRED_2ATR_1ATR_HIT_FIRST,
    )
    parser.add_argument("--symbols-fx", nargs="+", default=["EURUSD", "GBPUSD", "USDJPY"])
    parser.add_argument("--symbols-xauusd", nargs="+", default=["XAUUSD"])
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--shortlist-root", type=Path, default=DEFAULT_SHORTLIST_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--min-non-null-target-rows", type=int, default=200)
    parser.add_argument("--min-positive-target-rows", type=int, default=50)
    parser.add_argument("--min-negative-target-rows", type=int, default=50)
    parser.add_argument("--min-positive-rate", type=float, default=0.05)
    parser.add_argument("--max-positive-rate", type=float, default=0.95)
    return parser.parse_args(argv)


def main() -> int:
    try:
        outputs = diagnose_preferred_horizon_prerequisites(parse_args())
    except (FileNotFoundError, OSError, sqlite3.Error, ValueError) as exc:
        print(f"Preferred horizon prerequisite diagnostics failed: {exc}")
        return 1
    print("Preferred horizon prerequisite diagnostics complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
