"""Build walk-forward/drawdown review-readiness artifacts for one candidate.

This module reads already-produced exact-rule and single-filter stress output
folders and summarizes whether the existing artifacts are ready for the next
human review step. It does not run stress validation, backtests, diagnostics,
candidate audit, model work, database work, or operational workflows.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_walkforward_drawdown_review_readiness"
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
DEFAULT_R_MULTIPLE_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_r_multiple_baseline_review"
    / "gbpusd_short_h10_1_5_off_hours_r_multiple_baseline_review_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_walkforward_drawdown_review_readiness"

SUMMARY_FILE = "candidate_stress_summary.csv"
YEARLY_FILES = ("yearly_validation_summary.csv", "yearly_validation.csv")
WALK_FORWARD_FILES = ("walk_forward_summary.csv", "walk_forward_validation.csv")
EQUITY_BASE_FILE = "equity_curve_base.csv"
EQUITY_STRESS_FILE = "equity_curve_stress.csv"
TRADE_BASE_FILE = "trade_log_base.csv"
TRADE_STRESS_FILE = "trade_log_stress.csv"
REPORT_FILE = "candidate_stress_report.md"
R_MULTIPLE_REVIEW_FILE = "fixed_candidate_r_multiple_baseline_review.csv"

OUTPUT_CSV = "fixed_candidate_walkforward_drawdown_review_readiness.csv"
OUTPUT_REPORT = "fixed_candidate_walkforward_drawdown_review_readiness_report.md"
OUTPUT_WARNINGS = "fixed_candidate_walkforward_drawdown_review_readiness_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_walkforward_drawdown_review_readiness_manifest.json"

READINESS_STATUSES = {
    "ready_for_artifact_review",
    "ready_with_caveat",
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
    "readiness_status",
    "caveat",
    "required_next_artifact",
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
        "readiness": output_dir / OUTPUT_CSV,
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


def stress_artifact_summary(directory: Path) -> dict[str, Any]:
    summary_path = directory / SUMMARY_FILE
    yearly_path = first_existing_file(directory, YEARLY_FILES)
    walk_forward_path = first_existing_file(directory, WALK_FORWARD_FILES)
    report_path = directory / REPORT_FILE
    artifact_paths = {
        "summary": summary_path,
        "yearly": yearly_path,
        "walk_forward": walk_forward_path,
        "equity_base": directory / EQUITY_BASE_FILE,
        "equity_stress": directory / EQUITY_STRESS_FILE,
        "trade_base": directory / TRADE_BASE_FILE,
        "trade_stress": directory / TRADE_STRESS_FILE,
        "report": report_path,
    }
    summary_row = first_row(summary_path) if summary_path.exists() else {}
    return {
        "directory": directory,
        "exists": directory.exists(),
        "summary_path": summary_path,
        "summary_row": summary_row,
        "yearly_path": yearly_path,
        "walk_forward_path": walk_forward_path,
        "yearly_rows": row_count(yearly_path),
        "walk_forward_rows": row_count(walk_forward_path),
        "equity_base_rows": row_count(artifact_paths["equity_base"]),
        "equity_stress_rows": row_count(artifact_paths["equity_stress"]),
        "trade_base_rows": row_count(artifact_paths["trade_base"]),
        "trade_stress_rows": row_count(artifact_paths["trade_stress"]),
        "artifact_paths": artifact_paths,
    }


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


def caveat_text(*labels: str) -> str:
    return ";".join(label for label in labels if label)


def value(summary: dict[str, Any], key: str) -> str:
    return str(summary.get("summary_row", {}).get(key, "") or "")


def base_readiness_row(
    args: argparse.Namespace,
    *,
    review_scope: str,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    readiness_status: str,
    artifact_status: str = "available",
    caveat: str = "",
    required_next_artifact: str = "",
    warning_code: str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    if readiness_status not in READINESS_STATUSES:
        raise ValueError(f"Unexpected readiness_status: {readiness_status}")
    return {
        "run_id": args.run_id,
        "review_scope": review_scope,
        "artifact_status": artifact_status,
        "exact_source_dir": str(exact.get("directory", "")),
        "baseline_source_dir": str(baseline.get("directory", "")),
        "exact_trades": value(exact, "sequential_trades_count"),
        "baseline_trades": value(baseline, "sequential_trades_count"),
        "exact_mean_R": value(exact, "mean_R"),
        "baseline_mean_R": value(baseline, "mean_R"),
        "exact_profit_factor_R": value(exact, "profit_factor_R"),
        "baseline_profit_factor_R": value(baseline, "profit_factor_R"),
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
        "readiness_status": readiness_status,
        "caveat": caveat,
        "required_next_artifact": required_next_artifact,
        "warning_code": warning_code,
        "blocking_warning": bool_text(blocking_warning),
    }


def add_warning_for_row(
    warnings: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    warning_code: str,
    severity: str,
    message: str,
    source_dir: Path | str,
    blocking_warning: bool = False,
) -> None:
    row["warning_code"] = warning_code
    row["blocking_warning"] = bool_text(blocking_warning)
    warnings.append(
        warning_row(
            warning_code=warning_code,
            severity=severity,
            message=message,
            review_scope=str(row.get("review_scope", "")),
            source_dir=source_dir,
            blocking_warning=blocking_warning,
        )
    )


def availability_row(
    args: argparse.Namespace,
    *,
    review_scope: str,
    target: dict[str, Any],
    peer: dict[str, Any],
    warnings: list[dict[str, Any]],
    target_name: str,
) -> dict[str, Any]:
    missing = []
    if not target["exists"]:
        missing.append("stress_output_dir")
    if not target["summary_row"]:
        missing.append(SUMMARY_FILE)
    for key in ("equity_base", "equity_stress", "trade_base", "trade_stress", "report"):
        path = target["artifact_paths"][key]
        if not path.exists():
            missing.append(path.name)
    if missing:
        row = base_readiness_row(
            args,
            review_scope=review_scope,
            exact=target if target_name == "exact_rule" else peer,
            baseline=target if target_name != "exact_rule" else peer,
            readiness_status="unavailable_missing_artifact",
            artifact_status="missing",
            caveat=caveat_text("descriptive_only_no_decision", "timeout_policy_review_still_separate"),
            required_next_artifact=";".join(missing),
        )
        add_warning_for_row(
            warnings,
            row,
            warning_code=f"{target_name}_artifact_missing",
            severity="warning",
            message=f"Missing expected artifact(s): {', '.join(missing)}",
            source_dir=target["directory"],
        )
        return row
    return base_readiness_row(
        args,
        review_scope=review_scope,
        exact=target if target_name == "exact_rule" else peer,
        baseline=target if target_name != "exact_rule" else peer,
        readiness_status="ready_for_artifact_review",
        caveat=caveat_text("descriptive_only_no_decision", "timeout_policy_review_still_separate"),
    )


def coverage_row(
    args: argparse.Namespace,
    *,
    review_scope: str,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    artifact_name: str,
) -> dict[str, Any]:
    exact_count = exact["yearly_rows"] if artifact_name == "yearly" else exact["walk_forward_rows"]
    baseline_count = baseline["yearly_rows"] if artifact_name == "yearly" else baseline["walk_forward_rows"]
    ready = exact_count > 0 and baseline_count > 0
    caveat = caveat_text(
        "yearly_artifacts_present" if artifact_name == "yearly" and ready else "",
        "walk_forward_artifacts_present" if artifact_name == "walk_forward" and ready else "",
        "descriptive_only_no_decision",
        "timeout_policy_review_still_separate",
    )
    return base_readiness_row(
        args,
        review_scope=review_scope,
        exact=exact,
        baseline=baseline,
        readiness_status="ready_for_artifact_review" if ready else "ready_with_caveat",
        artifact_status="available" if ready else "missing",
        caveat=caveat,
        required_next_artifact="" if ready else f"{artifact_name}_coverage_artifacts",
        warning_code="" if ready else f"{artifact_name}_coverage_incomplete",
    )


def drawdown_row(args: argparse.Namespace, exact: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return base_readiness_row(
        args,
        review_scope="exact_vs_single_filter_a_drawdown_artifact_review",
        exact=exact,
        baseline=baseline,
        readiness_status="ready_for_artifact_review",
        caveat=caveat_text(
            "exact_more_selective",
            "exact_lower_drawdown_observed",
            "single_filter_a_higher_trade_count",
            "average_edge_not_clearly_higher_for_exact",
            "descriptive_only_no_decision",
        ),
        required_next_artifact="drawdown_clustering_review_table",
    )


def clustering_row(args: argparse.Namespace, exact: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    has_concentration_fields = bool(value(exact, "top_month_contribution_pct") or value(exact, "top_5_percent_contribution_pct"))
    status = "ready_with_caveat" if has_concentration_fields else "ready_with_caveat"
    return base_readiness_row(
        args,
        review_scope="exact_vs_single_filter_a_clustering_artifact_review",
        exact=exact,
        baseline=baseline,
        readiness_status=status,
        caveat=caveat_text("clustering_review_needed", "descriptive_only_no_decision"),
        required_next_artifact="trade_clustering_or_concentration_review",
    )


def next_review_row(
    args: argparse.Namespace,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    r_review_rows: list[dict[str, str]],
) -> dict[str, Any]:
    core_ready = exact["summary_row"] and baseline["summary_row"] and exact["walk_forward_rows"] and baseline["walk_forward_rows"]
    caveat = caveat_text(
        "exact_more_selective",
        "exact_lower_drawdown_observed",
        "single_filter_a_higher_trade_count",
        "average_edge_not_clearly_higher_for_exact",
        "walk_forward_artifacts_present" if exact["walk_forward_rows"] and baseline["walk_forward_rows"] else "",
        "yearly_artifacts_present" if exact["yearly_rows"] and baseline["yearly_rows"] else "",
        "clustering_review_needed",
        "timeout_policy_review_still_separate",
        "descriptive_only_no_decision",
    )
    return base_readiness_row(
        args,
        review_scope="exact_vs_single_filter_a_next_review_readiness",
        exact=exact,
        baseline=baseline,
        readiness_status="ready_with_caveat" if core_ready and r_review_rows else "unavailable_missing_artifact",
        artifact_status="available" if core_ready and r_review_rows else "missing",
        caveat=caveat,
        required_next_artifact="walk_forward_drawdown_clustering_review" if core_ready else "missing_source_artifacts",
    )


def build_readiness(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    exact = stress_artifact_summary(Path(args.exact_stress_dir))
    single_a = stress_artifact_summary(Path(args.single_filter_a_stress_dir))
    r_review_path = Path(args.r_multiple_review_dir) / R_MULTIPLE_REVIEW_FILE
    r_review_rows = read_csv_rows(r_review_path)
    warnings: list[dict[str, Any]] = []
    rows = [
        availability_row(
            args,
            review_scope="exact_rule_artifact_availability",
            target=exact,
            peer=single_a,
            warnings=warnings,
            target_name="exact_rule",
        ),
        availability_row(
            args,
            review_scope="single_filter_a_artifact_availability",
            target=single_a,
            peer=exact,
            warnings=warnings,
            target_name="single_filter_a",
        ),
        coverage_row(
            args,
            review_scope="exact_vs_single_filter_a_yearly_coverage",
            exact=exact,
            baseline=single_a,
            artifact_name="yearly",
        ),
        coverage_row(
            args,
            review_scope="exact_vs_single_filter_a_walk_forward_coverage",
            exact=exact,
            baseline=single_a,
            artifact_name="walk_forward",
        ),
        drawdown_row(args, exact, single_a),
        clustering_row(args, exact, single_a),
        next_review_row(args, exact, single_a, r_review_rows),
    ]
    for row in rows:
        if row.get("warning_code") and not any(w.get("review_scope") == row.get("review_scope") for w in warnings):
            warnings.append(
                warning_row(
                    warning_code=str(row["warning_code"]),
                    severity="warning",
                    message="Readiness row has a non-blocking caveat.",
                    review_scope=str(row["review_scope"]),
                    source_dir=str(row.get("exact_source_dir") or row.get("baseline_source_dir")),
                )
            )
    metadata = {
        "r_multiple_review_csv": str(r_review_path),
        "r_multiple_review_row_count": len(r_review_rows),
        "include_broad_dir": str(args.include_broad_dir or ""),
        "include_single_filter_b_dir": str(args.include_single_filter_b_dir or ""),
    }
    return rows, warnings, metadata


def status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("readiness_status") or "") for row in rows)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    counts = status_counts(rows)
    summary = {row["review_scope"]: row for row in rows}
    tradeoff = summary.get("exact_vs_single_filter_a_drawdown_artifact_review", {})
    lines = [
        "# Fixed Candidate Walk-Forward / Drawdown Review Readiness",
        "",
        "Artifact-only review-readiness report. It reads existing stress and review artifacts only.",
        "No stress validation, backtests, diagnostics, candidate audit, model work, database mutation, or operational action was executed.",
        "No candidate-quality conclusion or trading decision was made.",
        "",
        "## Inputs",
        "",
        f"- exact_stress_dir: `{args.exact_stress_dir}`",
        f"- single_filter_a_stress_dir: `{args.single_filter_a_stress_dir}`",
        f"- r_multiple_review_dir: `{args.r_multiple_review_dir}`",
        "",
        "## Counts",
        "",
        f"- review_row_count: `{len(rows)}`",
        f"- ready_for_artifact_review: `{counts.get('ready_for_artifact_review', 0)}`",
        f"- ready_with_caveat: `{counts.get('ready_with_caveat', 0)}`",
        f"- unavailable_missing_artifact: `{counts.get('unavailable_missing_artifact', 0)}`",
        f"- blocked_unreadable_input: `{counts.get('blocked_unreadable_input', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## Exact vs Single Filter A Trade-Off Summary",
        "",
        f"- exact_trades: `{tradeoff.get('exact_trades', '')}`",
        f"- single_filter_a_trades: `{tradeoff.get('baseline_trades', '')}`",
        f"- exact_max_drawdown_R: `{tradeoff.get('exact_max_drawdown_R', '')}`",
        f"- single_filter_a_max_drawdown_R: `{tradeoff.get('baseline_max_drawdown_R', '')}`",
        f"- caveat_labels: `{tradeoff.get('caveat', '')}`",
        "",
        "## Coverage Availability",
        "",
        f"- yearly coverage row: `{summary.get('exact_vs_single_filter_a_yearly_coverage', {}).get('readiness_status', '')}`",
        f"- walk-forward coverage row: `{summary.get('exact_vs_single_filter_a_walk_forward_coverage', {}).get('readiness_status', '')}`",
        "",
        "## Next Artifact Areas",
        "",
        "- walk-forward review",
        "- timeout policy review",
        "- drawdown/clustering review",
        "- exact-vs-single_filter_a attribution review",
        "",
        "Descriptive artifact readiness does not replace a full walk-forward or timeout review.",
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
        "r_multiple_review_dir": str(args.r_multiple_review_dir),
        "review_row_count": len(rows),
        "ready_for_artifact_review_count": counts.get("ready_for_artifact_review", 0),
        "ready_with_caveat_count": counts.get("ready_with_caveat", 0),
        "unavailable_missing_artifact_count": counts.get("unavailable_missing_artifact", 0),
        "blocked_unreadable_input_count": counts.get("blocked_unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"),
        "r_multiple_review_csv": metadata.get("r_multiple_review_csv", ""),
        "r_multiple_review_row_count": metadata.get("r_multiple_review_row_count", 0),
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
    rows, warnings, metadata = build_readiness(args)
    write_csv(paths["readiness"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build artifact-only walk-forward/drawdown review-readiness artifacts. "
            "No validation, diagnostics, backtests, or child scripts are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--exact-stress-dir", type=Path, default=DEFAULT_EXACT_STRESS_DIR)
    parser.add_argument("--single-filter-a-stress-dir", type=Path, default=DEFAULT_SINGLE_FILTER_A_STRESS_DIR)
    parser.add_argument("--r-multiple-review-dir", type=Path, default=DEFAULT_R_MULTIPLE_REVIEW_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--include-broad-dir", type=Path)
    parser.add_argument("--include-single-filter-b-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate walk-forward/drawdown review-readiness build failed: {exc}")
        return 1
    print("Fixed-candidate walk-forward/drawdown review-readiness build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
