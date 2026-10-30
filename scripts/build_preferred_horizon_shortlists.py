"""Build preferred feature shortlist inputs for configured horizons.

This research-only orchestrator reuses the existing target-specific ML
research comparison, preferred-target feature stability, and preferred feature
hypothesis shortlist scripts. It prepares the same kind of inputs that were
previously available for h10, without running backtests, creating feature
combinations, optimizing TP/SL settings, or adding broker execution logic.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path
import sys
from typing import Callable


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from build_preferred_feature_hypothesis_shortlist import (
        DEFAULT_OUTPUT_ROOT as DEFAULT_SHORTLIST_OUTPUT_ROOT,
        build_preferred_feature_hypothesis_shortlist,
    )
    from build_preferred_target_feature_stability import (
        DEFAULT_OUTPUT_ROOT as DEFAULT_STABILITY_OUTPUT_ROOT,
        build_preferred_target_feature_stability,
        preferred_target,
    )
    from compare_ml_target_reports import (
        DEFAULT_DB_PATH,
        DEFAULT_REPORTS_ROOT,
        compare_ml_targets,
        comparison_output_dir,
        target_run_dir,
    )
    from target_families import (
        PREFERRED_2ATR_1ATR_HIT_FIRST,
        family_scoped_root,
        supported_target_family_names,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.build_preferred_feature_hypothesis_shortlist import (
        DEFAULT_OUTPUT_ROOT as DEFAULT_SHORTLIST_OUTPUT_ROOT,
        build_preferred_feature_hypothesis_shortlist,
    )
    from scripts.build_preferred_target_feature_stability import (
        DEFAULT_OUTPUT_ROOT as DEFAULT_STABILITY_OUTPUT_ROOT,
        build_preferred_target_feature_stability,
        preferred_target,
    )
    from scripts.compare_ml_target_reports import (
        DEFAULT_DB_PATH,
        DEFAULT_REPORTS_ROOT,
        compare_ml_targets,
        comparison_output_dir,
        target_run_dir,
    )
    from scripts.target_families import (
        PREFERRED_2ATR_1ATR_HIT_FIRST,
        family_scoped_root,
        supported_target_family_names,
    )


DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "ml_research" / "preferred_horizon_shortlist_builds"
DEFAULT_HORIZONS = (5, 10, 20)
DEFAULT_DIRECTIONS = ("long", "short")
DEFAULT_GROUPS = ("fx", "xauusd")
DEFAULT_SYMBOLS_FX = ("EURUSD", "GBPUSD", "USDJPY")
DEFAULT_SYMBOLS_XAUUSD = ("XAUUSD",)
DEFAULT_TARGET_RUN_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
DEFAULT_STABILITY_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY")
MANIFEST_FILE = "preferred_horizon_shortlist_manifest.csv"
REPORT_FILE = "preferred_horizon_shortlist_report.md"
TARGET_RUN_REQUIRED_FILES = (
    "correlations.csv",
    "mutual_information.csv",
    "random_forest_importance.csv",
    "permutation_importance.csv",
    "model_metrics.csv",
    "threshold_analysis.csv",
    "feature_summary.csv",
)

MANIFEST_FIELDS = [
    "run_id",
    "row_type",
    "horizon",
    "direction",
    "symbol",
    "timeframe",
    "target_family",
    "target",
    "target_run_dir",
    "target_comparison_csv",
    "target_comparison_report",
    "target_status",
    "feature_stability_csv",
    "feature_stability_report",
    "preferred_feature_hypotheses_csv",
    "preferred_feature_hypotheses_report",
    "preferred_feature_hypotheses_rows",
    "status",
    "notes",
]


TargetComparisonRunner = Callable[[argparse.Namespace], dict[str, Path]]
StabilityBuilder = Callable[[argparse.Namespace], dict[str, dict[str, Path]]]
ShortlistBuilder = Callable[[argparse.Namespace], dict[str, dict[str, Path]]]


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def normalize_values(values: list[object], *, upper: bool = False, lower: bool = False) -> list[str]:
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


def normalize_horizons(values: list[object]) -> list[int]:
    horizons: list[int] = []
    for value in values:
        horizon = int(value)
        if horizon <= 0:
            raise ValueError("Horizons must be positive integers.")
        if horizon not in horizons:
            horizons.append(horizon)
    if not horizons:
        raise ValueError("At least one horizon is required.")
    return horizons


def group_symbol_mapping(args: argparse.Namespace) -> dict[str, list[str]]:
    return {
        "fx": normalize_values(getattr(args, "symbols_fx", DEFAULT_SYMBOLS_FX), upper=True),
        "xauusd": normalize_values(getattr(args, "symbols_xauusd", DEFAULT_SYMBOLS_XAUUSD), upper=True),
    }


def normalize_groups(args: argparse.Namespace) -> list[str]:
    raw_groups = getattr(args, "groups", DEFAULT_GROUPS)
    groups = normalize_values(raw_groups, lower=True)
    unknown = [group for group in groups if group not in DEFAULT_GROUPS]
    if unknown:
        raise ValueError(f"Unsupported group(s): {', '.join(unknown)}")
    return groups or list(DEFAULT_GROUPS)


def symbols_from_groups(args: argparse.Namespace) -> list[str]:
    mapping = group_symbol_mapping(args)
    symbols: list[str] = []
    for group in normalize_groups(args):
        for symbol in mapping[group]:
            if symbol not in symbols:
                symbols.append(symbol)
    return symbols


def resolve_target_run_symbols(args: argparse.Namespace) -> list[str]:
    explicit = normalize_values(getattr(args, "target_run_symbols", None) or [], upper=True)
    symbols = explicit or symbols_from_groups(args) or list(DEFAULT_TARGET_RUN_SYMBOLS)
    if not symbols:
        raise ValueError("At least one target-run symbol is required.")
    return symbols


def resolve_stability_symbols(args: argparse.Namespace, target_symbols: list[str]) -> list[str]:
    explicit = normalize_values(getattr(args, "stability_symbols", None) or [], upper=True)
    if explicit:
        return explicit
    mapping = group_symbol_mapping(args)
    fx_symbols = [symbol for symbol in mapping["fx"] if symbol in target_symbols]
    return fx_symbols or target_symbols


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "manifest": output_dir / MANIFEST_FILE,
        "report": output_dir / REPORT_FILE,
    }


def csv_value(value: object) -> object:
    return "" if value is None else value


def read_csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return sum(1 for _row in csv.DictReader(csv_file))


def target_run_complete(path: Path) -> bool:
    return all((path / file_name).exists() for file_name in TARGET_RUN_REQUIRED_FILES)


def comparison_paths(reports_root: Path, *, direction: str, symbol: str, timeframe: str, horizon: int) -> dict[str, Path]:
    output_dir = comparison_output_dir(
        reports_root,
        direction=direction,
        symbol=symbol,
        timeframe=timeframe,
        horizon=horizon,
    )
    return {
        "target_comparison_csv": output_dir / "target_comparison.csv",
        "target_comparison_report": output_dir / "target_comparison_report.md",
    }


def run_or_reuse_target_outputs(
    *,
    args: argparse.Namespace,
    runner: TargetComparisonRunner,
    run_id: str,
    symbol: str,
    direction: str,
    horizon: int,
) -> dict[str, object]:
    reports_root = Path(args.reports_root)
    timeframe = str(args.timeframe).strip().upper()
    target = preferred_target(direction, horizon, str(args.target_family))
    target_dir = target_run_dir(
        reports_root,
        direction=direction,
        symbol=symbol,
        timeframe=timeframe,
        horizon=horizon,
        target=target,
    )
    paths = comparison_paths(
        reports_root,
        direction=direction,
        symbol=symbol,
        timeframe=timeframe,
        horizon=horizon,
    )
    comparison_complete = paths["target_comparison_csv"].exists() and paths["target_comparison_report"].exists()
    target_complete = target_run_complete(target_dir)

    status = "reused_existing_target_outputs"
    if not (target_complete and comparison_complete and not args.overwrite):
        if bool(args.skip_ml_research) and not target_complete:
            raise FileNotFoundError(f"Missing target-run reports and --skip-ml-research was provided: {target_dir}")
        should_run_ml = (not target_complete or bool(args.overwrite)) and not bool(args.skip_ml_research)
        runner(
            argparse.Namespace(
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                horizon=horizon,
                db_path=Path(args.db_path),
                reports_root=reports_root,
                run_ml_research=should_run_ml,
                purge_overlap=bool(args.purge_overlap),
                embargo_bars=int(args.embargo_bars),
                non_overlap_eval=bool(args.non_overlap_eval),
                targets=[target],
                min_predicted_positive_count=int(args.min_predicted_positive_count),
                overwrite=bool(args.overwrite),
            )
        )
        target_complete = target_run_complete(target_dir)
        comparison_complete = paths["target_comparison_csv"].exists() and paths["target_comparison_report"].exists()
        status = "generated_target_outputs" if should_run_ml else "generated_target_comparison_from_existing_reports"

    if not target_complete:
        raise FileNotFoundError(f"Target-run reports are incomplete after generation attempt: {target_dir}")
    if not comparison_complete:
        raise FileNotFoundError(f"Target-comparison outputs are incomplete after generation attempt: {paths['target_comparison_csv'].parent}")

    return {
        "run_id": run_id,
        "row_type": "target_run",
        "horizon": horizon,
        "direction": direction,
        "symbol": symbol,
        "timeframe": timeframe,
        "target_family": str(args.target_family),
        "target": target,
        "target_run_dir": target_dir,
        "target_comparison_csv": paths["target_comparison_csv"],
        "target_comparison_report": paths["target_comparison_report"],
        "target_status": status,
        "status": "ok",
        "notes": "preferred target ML ranking inputs ready",
    }


def build_stability_and_shortlist_outputs(
    *,
    args: argparse.Namespace,
    stability_builder: StabilityBuilder,
    shortlist_builder: ShortlistBuilder,
    run_id: str,
    horizon: int,
) -> list[dict[str, object]]:
    directions = normalize_values(args.directions, lower=True)
    stability_output_root = family_scoped_root(Path(args.stability_output_root), str(args.target_family))
    shortlist_output_root = family_scoped_root(Path(args.shortlist_output_root), str(args.target_family))
    stability_outputs = stability_builder(
        argparse.Namespace(
            reports_root=Path(args.reports_root) / "target_runs",
            output_root=stability_output_root,
            symbols=normalize_values(args.stability_symbols, upper=True),
            timeframe=str(args.timeframe),
            horizon=horizon,
            directions=directions,
            top_n=int(args.top_n),
            target_family=str(args.target_family),
        )
    )
    shortlist_outputs = shortlist_builder(
        argparse.Namespace(
            input_root=stability_output_root,
            output_root=shortlist_output_root,
            timeframe=str(args.timeframe),
            horizon=horizon,
            directions=directions,
            min_symbols=int(args.min_symbols),
            min_stability_score=int(args.min_stability_score),
        )
    )

    rows: list[dict[str, object]] = []
    for direction in directions:
        stability_paths = stability_outputs[direction]
        shortlist_paths = shortlist_outputs[direction]
        shortlist_csv = shortlist_paths["preferred_feature_hypotheses_csv"]
        rows.append(
            {
                "run_id": run_id,
                "row_type": "shortlist",
                "horizon": horizon,
                "direction": direction,
                "symbol": "",
                "timeframe": str(args.timeframe).strip().upper(),
                "target_family": str(args.target_family),
                "target": preferred_target(direction, horizon, str(args.target_family)),
                "feature_stability_csv": stability_paths["feature_stability_csv"],
                "feature_stability_report": stability_paths["feature_stability_report"],
                "preferred_feature_hypotheses_csv": shortlist_csv,
                "preferred_feature_hypotheses_report": shortlist_paths["preferred_feature_hypotheses_report"],
                "preferred_feature_hypotheses_rows": read_csv_row_count(shortlist_csv),
                "status": "ok",
                "notes": "preferred stability and shortlist outputs ready",
            }
        )
    return rows


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=MANIFEST_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in MANIFEST_FIELDS})


def markdown_path(value: object) -> str:
    text = str(value or "")
    return f"`{text}`" if text else ""


def write_report(path: Path, *, args: argparse.Namespace, run_id: str, rows: list[dict[str, object]]) -> None:
    target_rows = [row for row in rows if row.get("row_type") == "target_run"]
    shortlist_rows = [row for row in rows if row.get("row_type") == "shortlist"]
    target_status_counts = Counter(str(row.get("target_status") or "") for row in target_rows)
    stability_output_root = family_scoped_root(Path(args.stability_output_root), str(args.target_family))
    shortlist_output_root = family_scoped_root(Path(args.shortlist_output_root), str(args.target_family))
    lines = [
        "# Preferred Horizon Shortlist Build Report",
        "",
        "## Research-only warning",
        "",
        "- This build prepares existing preferred-feature research inputs only.",
        "- It does not run backtests, create feature combinations, optimize TP/SL settings, or add execution logic.",
        "",
        "## Configuration",
        "",
        f"- Run ID: `{run_id}`",
        f"- Timeframe: `{args.timeframe}`",
        f"- Horizons: `{', '.join(str(item) for item in args.horizons)}`",
        f"- Directions: `{', '.join(args.directions)}`",
        f"- Target family: `{args.target_family}`",
        f"- Target-run symbols: `{', '.join(args.target_run_symbols)}`",
        f"- Stability symbols: `{', '.join(args.stability_symbols)}`",
        f"- Reports root: `{args.reports_root}`",
        f"- Stability output root: `{stability_output_root}`",
        f"- Shortlist output root: `{shortlist_output_root}`",
        "",
        "## Target Ranking Inputs",
        "",
    ]
    if target_status_counts:
        lines.extend(f"- `{status}`: `{count}`" for status, count in sorted(target_status_counts.items()))
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## Preferred Shortlist Outputs",
            "",
            "| Horizon | Direction | Rows | Stability CSV | Shortlist CSV |",
            "|---:|---:|---:|---|---|",
        ]
    )
    if shortlist_rows:
        for row in sorted(shortlist_rows, key=lambda item: (int(item["horizon"]), str(item["direction"]))):
            lines.append(
                f"| `{row['horizon']}` | `{row['direction']}` | `{row.get('preferred_feature_hypotheses_rows', '')}` | "
                f"{markdown_path(row.get('feature_stability_csv'))} | "
                f"{markdown_path(row.get('preferred_feature_hypotheses_csv'))} |"
            )
    else:
        lines.append("| None | None | 0 |  |  |")

    lines.extend(
        [
            "",
            "## Methodology Notes",
            "",
            "- Preferred target names follow the safe hit-first naming convention for the selected target family.",
            "- Stability rows are built with the same top-N recurrence method used for the existing h10 inputs.",
            "- Shortlist rows use the same minimum-symbol and stability-score filters as the existing h10 inputs.",
            "- Future and target label columns are excluded by the shared feature-safety rules.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_preferred_horizon_shortlists(
    args: argparse.Namespace,
    *,
    target_runner: TargetComparisonRunner = compare_ml_targets,
    stability_builder: StabilityBuilder = build_preferred_target_feature_stability,
    shortlist_builder: ShortlistBuilder = build_preferred_feature_hypothesis_shortlist,
) -> dict[str, Path]:
    run_id = str(args.run_id or current_run_id())
    if not getattr(args, "target_family", None):
        args.target_family = PREFERRED_2ATR_1ATR_HIT_FIRST
    horizons = normalize_horizons(list(args.horizons))
    directions = normalize_values(args.directions, lower=True)
    target_symbols = resolve_target_run_symbols(args)
    args.target_run_symbols = target_symbols
    args.stability_symbols = resolve_stability_symbols(args, target_symbols)
    if not directions:
        raise ValueError("At least one direction is required.")

    rows: list[dict[str, object]] = []
    total_targets = len(horizons) * len(directions) * len(target_symbols)
    target_index = 0
    for horizon in horizons:
        for direction in directions:
            for symbol in target_symbols:
                target_index += 1
                print(
                    f"Target input {target_index}/{total_targets}: "
                    f"symbol={symbol} direction={direction} h={horizon}"
                )
                rows.append(
                    run_or_reuse_target_outputs(
                        args=args,
                        runner=target_runner,
                        run_id=run_id,
                        symbol=symbol,
                        direction=direction,
                        horizon=horizon,
                    )
                )
        rows.extend(
            build_stability_and_shortlist_outputs(
                args=args,
                stability_builder=stability_builder,
                shortlist_builder=shortlist_builder,
                run_id=run_id,
                horizon=horizon,
            )
        )

    outputs = output_paths(Path(args.output_root), run_id)
    write_manifest(outputs["manifest"], rows)
    write_report(outputs["report"], args=args, run_id=run_id, rows=rows)
    return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build research-only preferred target rankings and shortlist inputs for configured horizons."
    )
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--horizons", nargs="+", type=int, default=list(DEFAULT_HORIZONS))
    parser.add_argument("--directions", nargs="+", choices=DEFAULT_DIRECTIONS, default=list(DEFAULT_DIRECTIONS))
    parser.add_argument(
        "--target-family",
        choices=supported_target_family_names(),
        default=PREFERRED_2ATR_1ATR_HIT_FIRST,
    )
    parser.add_argument("--groups", nargs="+", choices=DEFAULT_GROUPS, default=list(DEFAULT_GROUPS))
    parser.add_argument("--symbols-fx", nargs="+", default=list(DEFAULT_SYMBOLS_FX))
    parser.add_argument("--symbols-xauusd", nargs="+", default=list(DEFAULT_SYMBOLS_XAUUSD))
    parser.add_argument("--target-run-symbols", nargs="+")
    parser.add_argument("--stability-symbols", nargs="+")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT)
    parser.add_argument("--stability-output-root", type=Path, default=DEFAULT_STABILITY_OUTPUT_ROOT)
    parser.add_argument("--shortlist-output-root", type=Path, default=DEFAULT_SHORTLIST_OUTPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--min-symbols", type=int, default=3)
    parser.add_argument("--min-stability-score", type=int, default=12)
    parser.add_argument("--min-predicted-positive-count", type=int, default=500)
    parser.add_argument("--purge-overlap", action="store_true")
    parser.add_argument("--embargo-bars", type=int, default=0)
    parser.add_argument("--non-overlap-eval", action="store_true")
    parser.add_argument("--skip-ml-research", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    try:
        outputs = build_preferred_horizon_shortlists(parse_args())
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"Preferred horizon shortlist build failed: {exc}")
        return 1
    print("Preferred horizon shortlist build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
