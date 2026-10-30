"""Build an artifact-only walk-forward/drawdown review for one trade-off.

This module reads existing exact-rule and single-filter stress artifacts and
produces neutral descriptive rows for yearly, walk-forward, drawdown, clustering,
and selectivity review. It does not run validation, backtests, diagnostics,
candidate audit, model work, database work, or external execution.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_walkforward_drawdown_artifact_review"
DEFAULT_EXACT_STRESS_DIR = (
    BASE_DIR
    / "reports"
    / "regime_candidate_stress"
    / "gbpusd_short_h10_1_5_off_hours_stress_exec_v2"
)
DEFAULT_R_MULTIPLE_ROOT = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_r_multiple_row_specs"
    / "gbpusd_short_h10_1_5_off_hours_baseline_r_multiple_row_specs_v1"
    / "manual_r_multiple_outputs"
)
DEFAULT_SINGLE_FILTER_A_STRESS_DIR = (
    DEFAULT_R_MULTIPLE_ROOT
    / "gbpusd_short_h10_1_5_off_hours_baseline_r_multiple_row_specs_v1_single_filter_a"
)
DEFAULT_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_walkforward_drawdown_review_readiness"
    / "gbpusd_short_h10_1_5_off_hours_walkforward_drawdown_review_readiness_v1"
)
DEFAULT_COMPARISON_TABLE_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_comparison_table"
    / "gbpusd_short_h10_1_5_off_hours_baseline_comparison_table_v3"
)
DEFAULT_R_MULTIPLE_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_r_multiple_baseline_review"
    / "gbpusd_short_h10_1_5_off_hours_r_multiple_baseline_review_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_walkforward_drawdown_artifact_review"

SUMMARY_FILE = "candidate_stress_summary.csv"
YEARLY_FILES = ("yearly_validation_summary.csv", "yearly_validation.csv")
WALK_FORWARD_FILES = ("walk_forward_summary.csv", "walk_forward_validation.csv")
EQUITY_BASE_FILE = "equity_curve_base.csv"
EQUITY_STRESS_FILE = "equity_curve_stress.csv"
TRADE_BASE_FILE = "trade_log_base.csv"
TRADE_STRESS_FILE = "trade_log_stress.csv"
REPORT_FILE = "candidate_stress_report.md"
READINESS_FILE = "fixed_candidate_walkforward_drawdown_review_readiness.csv"

OUTPUT_CSV = "fixed_candidate_walkforward_drawdown_artifact_review.csv"
OUTPUT_REPORT = "fixed_candidate_walkforward_drawdown_artifact_review_report.md"
OUTPUT_WARNINGS = "fixed_candidate_walkforward_drawdown_artifact_review_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_walkforward_drawdown_artifact_review_manifest.json"

REVIEW_STATUSES = {
    "descriptive_review_available",
    "descriptive_review_available_with_caveat",
    "unavailable_missing_artifact",
    "blocked_unreadable_input",
}

FIELDNAMES = [
    "run_id",
    "review_scope",
    "artifact_status",
    "exact_source_dir",
    "baseline_source_dir",
    "exact_trades",
    "baseline_trades",
    "exact_mean_R",
    "baseline_mean_R",
    "exact_profit_factor_R",
    "baseline_profit_factor_R",
    "exact_cumulative_R",
    "baseline_cumulative_R",
    "exact_max_drawdown_R",
    "baseline_max_drawdown_R",
    "exact_yearly_positive_ratio",
    "baseline_yearly_positive_ratio",
    "exact_walk_forward_splits",
    "baseline_walk_forward_splits",
    "exact_top_month_contribution_pct",
    "baseline_top_month_contribution_pct",
    "exact_top_5_percent_contribution_pct",
    "baseline_top_5_percent_contribution_pct",
    "exact_max_rows_in_one_month",
    "baseline_max_rows_in_one_month",
    "exact_trade_count_ratio_vs_baseline",
    "descriptive_observation",
    "review_status",
    "caveat",
    "suggested_next_artifact_area",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "review_scope",
    "source_dir",
    "blocking_warning",
]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def safe_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def ratio(numerator: object, denominator: object) -> str:
    left = safe_float(numerator)
    right = safe_float(denominator)
    if left is None or right in {None, 0}:
        return ""
    return str(left / right)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "review": output_dir / OUTPUT_CSV,
        "report": output_dir / OUTPUT_REPORT,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "manifest": output_dir / OUTPUT_MANIFEST,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def first_existing_file(directory: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = directory / name
        if path.exists():
            return path
    return None


def row_count(path: Path | None) -> int:
    return len(read_csv_rows(path)) if path else 0


def first_row(path: Path) -> dict[str, str]:
    rows = read_csv_rows(path)
    return rows[0] if rows else {}


def stress_artifacts(directory: Path) -> dict[str, Any]:
    summary_path = directory / SUMMARY_FILE
    yearly_path = first_existing_file(directory, YEARLY_FILES)
    walk_forward_path = first_existing_file(directory, WALK_FORWARD_FILES)
    return {
        "directory": directory,
        "exists": directory.exists(),
        "summary_path": summary_path,
        "summary_row": first_row(summary_path) if summary_path.exists() else {},
        "yearly_path": yearly_path,
        "walk_forward_path": walk_forward_path,
        "yearly_rows": row_count(yearly_path),
        "walk_forward_rows": row_count(walk_forward_path),
        "equity_base_rows": row_count(directory / EQUITY_BASE_FILE),
        "equity_stress_rows": row_count(directory / EQUITY_STRESS_FILE),
        "trade_base_rows": row_count(directory / TRADE_BASE_FILE),
        "trade_stress_rows": row_count(directory / TRADE_STRESS_FILE),
        "report_exists": (directory / REPORT_FILE).exists(),
    }


def value(artifact: dict[str, Any], key: str) -> str:
    return str(artifact.get("summary_row", {}).get(key, "") or "")


def max_month_rows(artifact: dict[str, Any]) -> str:
    return value(artifact, "max_rows_in_one_month") or value(artifact, "max_trades_in_one_month")


def caveats(*items: str) -> str:
    return ";".join(item for item in items if item)


def warning_row(
    *,
    warning_code: str,
    severity: str,
    message: str,
    review_scope: str,
    source_dir: Path | str,
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "review_scope": review_scope,
        "source_dir": str(source_dir),
        "blocking_warning": bool_text(blocking_warning),
    }


def base_review_row(
    args: argparse.Namespace,
    *,
    review_scope: str,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    review_status: str,
    artifact_status: str = "available",
    descriptive_observation: str = "",
    caveat: str = "",
    suggested_next_artifact_area: str = "",
    warning_code: str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    if review_status not in REVIEW_STATUSES:
        raise ValueError(f"Unexpected review_status: {review_status}")
    exact_trades = value(exact, "sequential_trades_count")
    baseline_trades = value(baseline, "sequential_trades_count")
    return {
        "run_id": args.run_id,
        "review_scope": review_scope,
        "artifact_status": artifact_status,
        "exact_source_dir": str(exact.get("directory", "")),
        "baseline_source_dir": str(baseline.get("directory", "")),
        "exact_trades": exact_trades,
        "baseline_trades": baseline_trades,
        "exact_mean_R": value(exact, "mean_R"),
        "baseline_mean_R": value(baseline, "mean_R"),
        "exact_profit_factor_R": value(exact, "profit_factor_R"),
        "baseline_profit_factor_R": value(baseline, "profit_factor_R"),
        "exact_cumulative_R": value(exact, "cumulative_R"),
        "baseline_cumulative_R": value(baseline, "cumulative_R"),
        "exact_max_drawdown_R": value(exact, "max_drawdown_R"),
        "baseline_max_drawdown_R": value(baseline, "max_drawdown_R"),
        "exact_yearly_positive_ratio": value(exact, "yearly_positive_ratio"),
        "baseline_yearly_positive_ratio": value(baseline, "yearly_positive_ratio"),
        "exact_walk_forward_splits": exact.get("walk_forward_rows", ""),
        "baseline_walk_forward_splits": baseline.get("walk_forward_rows", ""),
        "exact_top_month_contribution_pct": value(exact, "top_month_contribution_pct"),
        "baseline_top_month_contribution_pct": value(baseline, "top_month_contribution_pct"),
        "exact_top_5_percent_contribution_pct": value(exact, "top_5_percent_contribution_pct"),
        "baseline_top_5_percent_contribution_pct": value(baseline, "top_5_percent_contribution_pct"),
        "exact_max_rows_in_one_month": max_month_rows(exact),
        "baseline_max_rows_in_one_month": max_month_rows(baseline),
        "exact_trade_count_ratio_vs_baseline": ratio(exact_trades, baseline_trades),
        "descriptive_observation": descriptive_observation,
        "review_status": review_status,
        "caveat": caveat,
        "suggested_next_artifact_area": suggested_next_artifact_area,
        "warning_code": warning_code,
        "blocking_warning": bool_text(blocking_warning),
    }


def missing_required_row(
    args: argparse.Namespace,
    *,
    review_scope: str,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    missing_side: str,
) -> dict[str, Any]:
    return base_review_row(
        args,
        review_scope=review_scope,
        exact=exact,
        baseline=baseline,
        review_status="unavailable_missing_artifact",
        artifact_status="missing",
        descriptive_observation="further_review_required",
        caveat="descriptive_only_no_decision",
        suggested_next_artifact_area=f"{missing_side}_candidate_stress_summary",
        warning_code=f"{missing_side}_summary_missing",
    )


def required_input_rows(
    args: argparse.Namespace,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scope, artifact, side in [
        ("exact_rule_summary_artifact_review", exact, "exact"),
        ("single_filter_a_summary_artifact_review", baseline, "single_filter_a"),
    ]:
        if not artifact["summary_row"]:
            row = missing_required_row(
                args,
                review_scope=scope,
                exact=exact,
                baseline=baseline,
                missing_side=side,
            )
            rows.append(row)
            warnings.append(
                warning_row(
                    warning_code=str(row["warning_code"]),
                    severity="warning",
                    message="Required candidate stress summary is missing.",
                    review_scope=scope,
                    source_dir=artifact["directory"],
                )
            )
            continue
        rows.append(
            base_review_row(
                args,
                review_scope=scope,
                exact=exact,
                baseline=baseline,
                review_status="descriptive_review_available",
                descriptive_observation="descriptive_only_no_decision",
                caveat="descriptive_only_no_decision",
            )
        )
    return rows


def optional_artifact_warning(
    warnings: list[dict[str, Any]],
    *,
    row: dict[str, Any],
    message: str,
    source_dir: Path | str,
) -> None:
    warnings.append(
        warning_row(
            warning_code=str(row["warning_code"]),
            severity="warning",
            message=message,
            review_scope=str(row["review_scope"]),
            source_dir=source_dir,
        )
    )


def yearly_review_row(
    args: argparse.Namespace,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    available = exact["yearly_rows"] > 0 and baseline["yearly_rows"] > 0
    row = base_review_row(
        args,
        review_scope="exact_vs_single_filter_a_yearly_review",
        exact=exact,
        baseline=baseline,
        review_status="descriptive_review_available" if available else "descriptive_review_available_with_caveat",
        artifact_status="available" if available else "missing",
        descriptive_observation="yearly_coverage_artifacts_available" if available else "further_review_required",
        caveat=caveats(
            "yearly_coverage_artifacts_available" if available else "",
            "descriptive_only_no_decision",
        ),
        suggested_next_artifact_area="" if available else "yearly_validation_artifacts",
        warning_code="" if available else "yearly_artifact_missing",
    )
    if not available:
        optional_artifact_warning(
            warnings,
            row=row,
            message="One or both yearly validation artifacts are missing.",
            source_dir=f"{exact['directory']};{baseline['directory']}",
        )
    return row


def walk_forward_review_row(
    args: argparse.Namespace,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    available = exact["walk_forward_rows"] > 0 and baseline["walk_forward_rows"] > 0
    row = base_review_row(
        args,
        review_scope="exact_vs_single_filter_a_walk_forward_review",
        exact=exact,
        baseline=baseline,
        review_status="descriptive_review_available" if available else "descriptive_review_available_with_caveat",
        artifact_status="available" if available else "missing",
        descriptive_observation="walk_forward_artifacts_available" if available else "further_review_required",
        caveat=caveats(
            "walk_forward_artifacts_available" if available else "",
            "descriptive_only_no_decision",
        ),
        suggested_next_artifact_area="" if available else "walk_forward_validation_artifacts",
        warning_code="" if available else "walk_forward_artifact_missing",
    )
    if not available:
        optional_artifact_warning(
            warnings,
            row=row,
            message="One or both walk-forward artifacts are missing.",
            source_dir=f"{exact['directory']};{baseline['directory']}",
        )
    return row


def artifact_coverage_available(exact: dict[str, Any], baseline: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(int(exact.get(f"{key}_rows", 0) or 0) > 0 and int(baseline.get(f"{key}_rows", 0) or 0) > 0 for key in keys)


def build_artifact_review(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    exact = stress_artifacts(Path(args.exact_stress_dir))
    baseline = stress_artifacts(Path(args.single_filter_a_stress_dir))
    readiness_rows = read_csv_rows(Path(args.readiness_dir) / READINESS_FILE)
    warnings: list[dict[str, Any]] = []
    rows = required_input_rows(args, exact, baseline, warnings)
    rows.append(yearly_review_row(args, exact, baseline, warnings))
    rows.append(walk_forward_review_row(args, exact, baseline, warnings))
    rows.append(
        base_review_row(
            args,
            review_scope="exact_vs_single_filter_a_drawdown_review",
            exact=exact,
            baseline=baseline,
            review_status="descriptive_review_available",
            descriptive_observation=caveats(
                "exact_lower_drawdown_observed",
                "exact_more_selective_observed",
                "single_filter_a_higher_trade_count_observed",
                "average_edge_not_clearly_higher_for_exact",
            ),
            caveat="descriptive_only_no_decision",
            suggested_next_artifact_area="drawdown_clustering_review",
        )
    )
    rows.append(
        base_review_row(
            args,
            review_scope="exact_vs_single_filter_a_clustering_review",
            exact=exact,
            baseline=baseline,
            review_status="descriptive_review_available_with_caveat",
            descriptive_observation=caveats("clustering_artifacts_available", "clustering_review_needed"),
            caveat=caveats("clustering_review_needed", "descriptive_only_no_decision"),
            suggested_next_artifact_area="trade_clustering_or_concentration_review",
        )
    )
    rows.append(
        base_review_row(
            args,
            review_scope="exact_vs_single_filter_a_trade_count_selectivity_review",
            exact=exact,
            baseline=baseline,
            review_status="descriptive_review_available",
            descriptive_observation=caveats(
                "exact_more_selective_observed",
                "single_filter_a_higher_trade_count_observed",
                "descriptive_only_no_decision",
            ),
            caveat="descriptive_only_no_decision",
            suggested_next_artifact_area="exact_vs_single_filter_a_attribution_review",
        )
    )
    rows.append(
        base_review_row(
            args,
            review_scope="next_review_area_readiness",
            exact=exact,
            baseline=baseline,
            review_status="descriptive_review_available_with_caveat",
            descriptive_observation=caveats(
                "further_review_required",
                "timeout_policy_review_still_separate",
                "descriptive_only_no_decision",
            ),
            caveat=caveats("timeout_policy_review_still_separate", "descriptive_only_no_decision"),
            suggested_next_artifact_area="timeout_policy_review;deeper_walk_forward_review;drawdown_clustering_review;exact_vs_single_filter_a_attribution_review",
        )
    )
    metadata = {
        "readiness_row_count": len(readiness_rows),
        "comparison_table_dir": str(args.comparison_table_dir or ""),
        "r_multiple_review_dir": str(args.r_multiple_review_dir or ""),
    }
    return rows, warnings, metadata


def status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("review_status") or "") for row in rows)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    counts = status_counts(rows)
    row_by_scope = {row["review_scope"]: row for row in rows}
    drawdown = row_by_scope.get("exact_vs_single_filter_a_drawdown_review", {})
    clustering = row_by_scope.get("exact_vs_single_filter_a_clustering_review", {})
    lines = [
        "# Fixed Candidate Walk-Forward / Drawdown Artifact Review",
        "",
        "Artifact-only descriptive review. It reads existing artifacts and does not execute validation, diagnostics, backtests, candidate audit, model work, database mutation, or external action.",
        "No candidate-quality conclusion, recommendation, approval, rejection, ranking, or trading decision was made.",
        "",
        "## Inputs",
        "",
        f"- exact_stress_dir: `{args.exact_stress_dir}`",
        f"- single_filter_a_stress_dir: `{args.single_filter_a_stress_dir}`",
        f"- readiness_dir: `{args.readiness_dir}`",
        "",
        "## Counts",
        "",
        f"- review_row_count: `{len(rows)}`",
        f"- descriptive_review_available: `{counts.get('descriptive_review_available', 0)}`",
        f"- descriptive_review_available_with_caveat: `{counts.get('descriptive_review_available_with_caveat', 0)}`",
        f"- unavailable_missing_artifact: `{counts.get('unavailable_missing_artifact', 0)}`",
        f"- blocked_unreadable_input: `{counts.get('blocked_unreadable_input', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## Exact vs Single Filter A Summary",
        "",
        f"- exact_trades: `{drawdown.get('exact_trades', '')}`",
        f"- single_filter_a_trades: `{drawdown.get('baseline_trades', '')}`",
        f"- exact_max_drawdown_R: `{drawdown.get('exact_max_drawdown_R', '')}`",
        f"- single_filter_a_max_drawdown_R: `{drawdown.get('baseline_max_drawdown_R', '')}`",
        f"- descriptive_observation: `{drawdown.get('descriptive_observation', '')}`",
        "",
        "## Artifact Areas",
        "",
        f"- yearly artifact review: `{row_by_scope.get('exact_vs_single_filter_a_yearly_review', {}).get('review_status', '')}`",
        f"- walk-forward artifact review: `{row_by_scope.get('exact_vs_single_filter_a_walk_forward_review', {}).get('review_status', '')}`",
        f"- drawdown artifact review: `{drawdown.get('review_status', '')}`",
        f"- clustering/concentration artifact review: `{clustering.get('review_status', '')}`",
        "",
        "## Suggested Next Artifact Areas",
        "",
        "- timeout policy review",
        "- deeper walk-forward review if artifact coverage is insufficient",
        "- drawdown/clustering review",
        "- exact-vs-single_filter_a attribution review",
        "",
        "This descriptive artifact review does not replace full walk-forward validation or timeout policy review.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    counts = status_counts(rows)
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "exact_stress_dir": str(args.exact_stress_dir),
        "single_filter_a_stress_dir": str(args.single_filter_a_stress_dir),
        "readiness_dir": str(args.readiness_dir),
        "comparison_table_dir": str(args.comparison_table_dir or ""),
        "r_multiple_review_dir": str(args.r_multiple_review_dir or ""),
        "review_row_count": len(rows),
        "descriptive_review_available_count": counts.get("descriptive_review_available", 0),
        "descriptive_review_available_with_caveat_count": counts.get("descriptive_review_available_with_caveat", 0),
        "unavailable_missing_artifact_count": counts.get("unavailable_missing_artifact", 0),
        "blocked_unreadable_input_count": counts.get("blocked_unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"),
        "readiness_row_count": metadata.get("readiness_row_count", 0),
        "no_child_scripts_executed": True,
        "no_stress_validation_executed": True,
        "no_backtests_run": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_audit_executed": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    rows, warnings, metadata = build_artifact_review(args)
    write_csv(paths["review"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build an artifact-only fixed-candidate walk-forward/drawdown review. "
            "No validation, diagnostics, backtests, or child scripts are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--exact-stress-dir", type=Path, default=DEFAULT_EXACT_STRESS_DIR)
    parser.add_argument("--single-filter-a-stress-dir", type=Path, default=DEFAULT_SINGLE_FILTER_A_STRESS_DIR)
    parser.add_argument("--readiness-dir", type=Path, default=DEFAULT_READINESS_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--comparison-table-dir", type=Path, default=DEFAULT_COMPARISON_TABLE_DIR)
    parser.add_argument("--r-multiple-review-dir", type=Path, default=DEFAULT_R_MULTIPLE_REVIEW_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate walk-forward/drawdown artifact review build failed: {exc}")
        return 1
    print("Fixed-candidate walk-forward/drawdown artifact review build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
