"""Consolidate controlled deeper walk-forward manual outputs.

This module reads already-generated exact-rule and single-filter A stress
artifacts and normalizes their summary, walk-forward, yearly, and artifact
availability rows. It does not execute validation, backtests, timeout review,
baseline diagnostics, candidate audit, model work, database work, or external
actions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_deeper_walkforward_outputs_consolidated"
DEFAULT_DEEPER_WALKFORWARD_OUTPUT_ROOT = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_deeper_walkforward_runs"
    / "gbpusd_short_h10_1_5_off_hours_deeper_walkforward_run_specs_v1"
    / "manual_outputs"
)
DEFAULT_RUN_SPECS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_deeper_walkforward_run_specs"
    / "gbpusd_short_h10_1_5_off_hours_deeper_walkforward_run_specs_v1"
)
DEFAULT_RESEARCH_REVIEW_PACKET_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_research_review_packet"
    / "gbpusd_short_h10_1_5_off_hours_research_review_packet_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_deeper_walkforward_outputs_consolidated"

SUMMARY_FILE = "candidate_stress_summary.csv"
REPORT_FILE = "candidate_stress_report.md"
WALK_FORWARD_FILE = "walk_forward_validation.csv"
YEARLY_FILE = "yearly_validation.csv"
EQUITY_BASE_FILE = "equity_curve_base.csv"
EQUITY_STRESS_FILE = "equity_curve_stress.csv"
TRADE_BASE_FILE = "trade_log_base.csv"
TRADE_STRESS_FILE = "trade_log_stress.csv"
RANDOM_BASELINE_FILE = "random_baseline_summary.csv"

OUTPUT_CSV = "fixed_candidate_deeper_walkforward_outputs_consolidated.csv"
OUTPUT_REPORT = "fixed_candidate_deeper_walkforward_outputs_report.md"
OUTPUT_WARNINGS = "fixed_candidate_deeper_walkforward_outputs_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_deeper_walkforward_outputs_manifest.json"

REVIEW_TARGETS = ("exact_rule", "single_filter_a")
ARTIFACT_STATUSES = {"available", "available_with_caveat", "missing", "unreadable"}

FIELDNAMES = [
    "run_id",
    "review_target",
    "row_type",
    "cost_profile",
    "split_id",
    "year",
    "artifact_status",
    "source_output_dir",
    "source_summary_csv",
    "source_report_md",
    "source_walk_forward_csv",
    "source_yearly_csv",
    "source_equity_curve_base_csv",
    "source_equity_curve_stress_csv",
    "source_trade_log_base_csv",
    "source_trade_log_stress_csv",
    "symbol",
    "direction",
    "timeframe",
    "target_horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "condition_to_apply",
    "trades",
    "mean_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
    "stress_mean_R",
    "stress_profit_factor_R",
    "yearly_positive_ratio",
    "walk_forward_splits",
    "max_rows_in_one_month",
    "top_month_contribution_pct",
    "top_5_percent_contribution_pct",
    "final_research_label",
    "metric_namespace",
    "metric_unit",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "review_target",
    "source_output_dir",
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
        "consolidated": output_dir / OUTPUT_CSV,
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


def warning_row(
    *,
    warning_code: str,
    severity: str,
    message: str,
    review_target: str,
    source_output_dir: Path | str,
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "review_target": review_target,
        "source_output_dir": str(source_output_dir),
        "blocking_warning": bool_text(blocking_warning),
    }


def resolve_target_dir(args: argparse.Namespace, review_target: str) -> Path:
    explicit = getattr(args, f"{review_target}_dir", None)
    if explicit:
        return Path(explicit)
    return Path(args.deeper_walkforward_output_root) / review_target


def source_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "walk_forward": output_dir / WALK_FORWARD_FILE,
        "yearly": output_dir / YEARLY_FILE,
        "equity_base": output_dir / EQUITY_BASE_FILE,
        "equity_stress": output_dir / EQUITY_STRESS_FILE,
        "trade_base": output_dir / TRADE_BASE_FILE,
        "trade_stress": output_dir / TRADE_STRESS_FILE,
        "random": output_dir / RANDOM_BASELINE_FILE,
    }


def first_summary_row(path: Path) -> dict[str, str]:
    rows = read_csv_rows(path)
    return rows[0] if rows else {}


def base_row(
    *,
    args: argparse.Namespace,
    review_target: str,
    row_type: str,
    status: str,
    output_dir: Path,
    paths: dict[str, Path],
) -> dict[str, Any]:
    if status not in ARTIFACT_STATUSES:
        raise ValueError(f"Unexpected artifact_status: {status}")
    return {
        "run_id": args.run_id,
        "review_target": review_target,
        "row_type": row_type,
        "cost_profile": "",
        "split_id": "",
        "year": "",
        "artifact_status": status,
        "source_output_dir": output_dir,
        "source_summary_csv": paths["summary"] if paths["summary"].exists() else "",
        "source_report_md": paths["report"] if paths["report"].exists() else "",
        "source_walk_forward_csv": paths["walk_forward"] if paths["walk_forward"].exists() else "",
        "source_yearly_csv": paths["yearly"] if paths["yearly"].exists() else "",
        "source_equity_curve_base_csv": paths["equity_base"] if paths["equity_base"].exists() else "",
        "source_equity_curve_stress_csv": paths["equity_stress"] if paths["equity_stress"].exists() else "",
        "source_trade_log_base_csv": paths["trade_base"] if paths["trade_base"].exists() else "",
        "source_trade_log_stress_csv": paths["trade_stress"] if paths["trade_stress"].exists() else "",
        "symbol": "",
        "direction": "",
        "timeframe": "",
        "target_horizon": "",
        "target_family": "",
        "regime_column": "",
        "regime_value": "",
        "condition_to_apply": "",
        "trades": "",
        "mean_R": "",
        "profit_factor_R": "",
        "cumulative_R": "",
        "max_drawdown_R": "",
        "stress_mean_R": "",
        "stress_profit_factor_R": "",
        "yearly_positive_ratio": "",
        "walk_forward_splits": "",
        "max_rows_in_one_month": "",
        "top_month_contribution_pct": "",
        "top_5_percent_contribution_pct": "",
        "final_research_label": "",
        "metric_namespace": "R_multiple",
        "metric_unit": "R",
        "warning_code": "",
        "blocking_warning": bool_text(False),
    }


def apply_summary_fields(row: dict[str, Any], summary: dict[str, str]) -> None:
    row.update(
        {
            "symbol": summary.get("symbol", ""),
            "direction": summary.get("direction", ""),
            "timeframe": summary.get("timeframe", ""),
            "target_horizon": summary.get("horizon", ""),
            "target_family": summary.get("target_family", ""),
            "regime_column": summary.get("regime_column", ""),
            "regime_value": summary.get("regime_value", ""),
            "condition_to_apply": summary.get("feature_condition", ""),
            "yearly_positive_ratio": summary.get("yearly_positive_ratio", ""),
            "max_rows_in_one_month": summary.get("max_trades_in_one_month", ""),
            "top_month_contribution_pct": summary.get("top_month_contribution_pct", ""),
            "top_5_percent_contribution_pct": summary.get("top_5_percent_contribution_pct", ""),
            "final_research_label": summary.get("final_research_label", ""),
        }
    )


def summary_rows(
    *,
    args: argparse.Namespace,
    review_target: str,
    output_dir: Path,
    paths: dict[str, Path],
    summary: dict[str, str],
    status: str,
    warning_code: str = "",
    blocking: bool = False,
) -> list[dict[str, Any]]:
    base = base_row(args=args, review_target=review_target, row_type="summary_base", status=status, output_dir=output_dir, paths=paths)
    apply_summary_fields(base, summary)
    base.update(
        {
            "cost_profile": "p75",
            "trades": summary.get("sequential_trades_count", ""),
            "mean_R": summary.get("mean_R", ""),
            "profit_factor_R": summary.get("profit_factor_R", ""),
            "cumulative_R": summary.get("cumulative_R", ""),
            "max_drawdown_R": summary.get("max_drawdown_R", ""),
            "stress_mean_R": summary.get("stress_mean_R", ""),
            "stress_profit_factor_R": summary.get("stress_profit_factor_R", ""),
            "walk_forward_splits": summary.get("walk_forward_splits") or len(read_csv_rows(paths["walk_forward"])),
            "warning_code": warning_code,
            "blocking_warning": bool_text(blocking),
        }
    )
    stress = base_row(args=args, review_target=review_target, row_type="summary_stress", status=status, output_dir=output_dir, paths=paths)
    apply_summary_fields(stress, summary)
    stress.update(
        {
            "cost_profile": "p90",
            "trades": summary.get("stress_sequential_trades_count") or summary.get("sequential_trades_count", ""),
            "mean_R": summary.get("stress_mean_R", ""),
            "profit_factor_R": summary.get("stress_profit_factor_R", ""),
            "cumulative_R": summary.get("stress_cumulative_R", ""),
            "max_drawdown_R": summary.get("stress_max_drawdown_R", ""),
            "stress_mean_R": summary.get("stress_mean_R", ""),
            "stress_profit_factor_R": summary.get("stress_profit_factor_R", ""),
            "walk_forward_splits": summary.get("walk_forward_splits") or len(read_csv_rows(paths["walk_forward"])),
            "warning_code": warning_code,
            "blocking_warning": bool_text(blocking),
        }
    )
    return [base, stress]


def walk_forward_rows(
    *,
    args: argparse.Namespace,
    review_target: str,
    output_dir: Path,
    paths: dict[str, Path],
    summary: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in read_csv_rows(paths["walk_forward"]):
        row = base_row(args=args, review_target=review_target, row_type="walk_forward_split", status="available", output_dir=output_dir, paths=paths)
        apply_summary_fields(row, summary)
        row.update(
            {
                "cost_profile": "p75",
                "split_id": source.get("split_id", source.get("split", "")),
                "trades": source.get("test_trades", ""),
                "mean_R": source.get("test_mean_R", ""),
                "profit_factor_R": source.get("test_profit_factor_R", ""),
                "max_drawdown_R": source.get("test_max_drawdown_R", ""),
                "walk_forward_splits": summary.get("walk_forward_splits") or len(read_csv_rows(paths["walk_forward"])),
            }
        )
        rows.append(row)
    return rows


def yearly_rows(
    *,
    args: argparse.Namespace,
    review_target: str,
    output_dir: Path,
    paths: dict[str, Path],
    summary: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in read_csv_rows(paths["yearly"]):
        row = base_row(args=args, review_target=review_target, row_type="yearly_validation", status="available", output_dir=output_dir, paths=paths)
        apply_summary_fields(row, summary)
        row.update(
            {
                "cost_profile": "p75",
                "year": source.get("year", ""),
                "trades": source.get("trades_count", ""),
                "mean_R": source.get("mean_R", ""),
                "profit_factor_R": source.get("profit_factor_R", ""),
                "cumulative_R": source.get("cumulative_R", ""),
                "max_drawdown_R": source.get("max_drawdown_R", ""),
            }
        )
        rows.append(row)
    return rows


def optional_missing(paths: dict[str, Path]) -> list[str]:
    optional = [
        "report",
        "walk_forward",
        "yearly",
        "equity_base",
        "equity_stress",
        "trade_base",
        "trade_stress",
        "random",
    ]
    return [name for name in optional if not paths[name].exists()]


def artifact_availability_row(
    *,
    args: argparse.Namespace,
    review_target: str,
    output_dir: Path,
    paths: dict[str, Path],
    summary: dict[str, str],
    missing_optional: list[str],
    summary_status: str,
) -> dict[str, Any]:
    status = summary_status
    warning_code = ""
    if summary_status == "available" and missing_optional:
        status = "available_with_caveat"
        warning_code = "optional_artifacts_missing"
    row = base_row(args=args, review_target=review_target, row_type="artifact_availability", status=status, output_dir=output_dir, paths=paths)
    apply_summary_fields(row, summary)
    row.update(
        {
            "trades": summary.get("sequential_trades_count", ""),
            "mean_R": summary.get("mean_R", ""),
            "profit_factor_R": summary.get("profit_factor_R", ""),
            "max_drawdown_R": summary.get("max_drawdown_R", ""),
            "stress_mean_R": summary.get("stress_mean_R", ""),
            "stress_profit_factor_R": summary.get("stress_profit_factor_R", ""),
            "walk_forward_splits": summary.get("walk_forward_splits") or len(read_csv_rows(paths["walk_forward"])),
            "warning_code": warning_code,
        }
    )
    return row


def consolidate_target(args: argparse.Namespace, review_target: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    output_dir = resolve_target_dir(args, review_target)
    paths = source_paths(output_dir)
    warnings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    summary = first_summary_row(paths["summary"])
    if not output_dir.exists():
        warnings.append(
            warning_row(
                warning_code="output_dir_missing",
                severity="error",
                message="Expected deeper walk-forward output directory is missing.",
                review_target=review_target,
                source_output_dir=output_dir,
                blocking_warning=True,
            )
        )
        rows.extend(
            summary_rows(
                args=args,
                review_target=review_target,
                output_dir=output_dir,
                paths=paths,
                summary={},
                status="missing",
                warning_code="output_dir_missing",
                blocking=True,
            )
        )
        rows.append(
            artifact_availability_row(
                args=args,
                review_target=review_target,
                output_dir=output_dir,
                paths=paths,
                summary={},
                missing_optional=[],
                summary_status="missing",
            )
        )
        return rows, warnings
    if not paths["summary"].exists() or not summary:
        warnings.append(
            warning_row(
                warning_code="required_summary_missing",
                severity="error",
                message="Required candidate_stress_summary.csv is missing or empty.",
                review_target=review_target,
                source_output_dir=output_dir,
                blocking_warning=True,
            )
        )
        rows.extend(
            summary_rows(
                args=args,
                review_target=review_target,
                output_dir=output_dir,
                paths=paths,
                summary={},
                status="missing",
                warning_code="required_summary_missing",
                blocking=True,
            )
        )
        rows.append(
            artifact_availability_row(
                args=args,
                review_target=review_target,
                output_dir=output_dir,
                paths=paths,
                summary={},
                missing_optional=[],
                summary_status="missing",
            )
        )
        return rows, warnings

    missing_optional = optional_missing(paths)
    if missing_optional:
        warnings.append(
            warning_row(
                warning_code="optional_artifacts_missing",
                severity="warning",
                message="Optional output artifacts are missing: " + ", ".join(missing_optional),
                review_target=review_target,
                source_output_dir=output_dir,
            )
        )
    rows.extend(
        summary_rows(
            args=args,
            review_target=review_target,
            output_dir=output_dir,
            paths=paths,
            summary=summary,
            status="available",
        )
    )
    rows.extend(walk_forward_rows(args=args, review_target=review_target, output_dir=output_dir, paths=paths, summary=summary))
    rows.extend(yearly_rows(args=args, review_target=review_target, output_dir=output_dir, paths=paths, summary=summary))
    rows.append(
        artifact_availability_row(
            args=args,
            review_target=review_target,
            output_dir=output_dir,
            paths=paths,
            summary=summary,
            missing_optional=missing_optional,
            summary_status="available",
        )
    )
    return rows, warnings


def build_consolidated_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for review_target in REVIEW_TARGETS:
        target_rows, target_warnings = consolidate_target(args, review_target)
        rows.extend(target_rows)
        warnings.extend(target_warnings)
    return rows, warnings


def status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("artifact_status") or "") for row in rows)


def row_type_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("row_type") or "") for row in rows)


def write_report(path: Path, *, args: argparse.Namespace, rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    status = status_counts(rows)
    types = row_type_counts(rows)
    summaries = {
        (row["review_target"], row["row_type"]): row
        for row in rows
        if row.get("row_type") == "summary_base"
    }
    exact = summaries.get(("exact_rule", "summary_base"), {})
    single = summaries.get(("single_filter_a", "summary_base"), {})
    lines = [
        "# Fixed Candidate Deeper Walk-Forward Outputs Consolidated",
        "",
        "Artifact-only consolidation. It reads completed manual output artifacts and does not execute validation, walk-forward validation, backtests, timeout review, diagnostics, candidate audit, model work, database mutation, or external actions.",
        "No candidate-quality conclusion, ranking, or trading decision was made.",
        "",
        "## Inputs",
        "",
        f"- deeper_walkforward_output_root: `{args.deeper_walkforward_output_root}`",
        f"- exact_rule_dir: `{resolve_target_dir(args, 'exact_rule')}`",
        f"- single_filter_a_dir: `{resolve_target_dir(args, 'single_filter_a')}`",
        f"- run_specs_dir: `{args.run_specs_dir}`",
        f"- research_review_packet_dir: `{args.research_review_packet_dir}`",
        "",
        "## Artifact Availability",
        "",
        f"- available: `{status.get('available', 0)}`",
        f"- available_with_caveat: `{status.get('available_with_caveat', 0)}`",
        f"- missing: `{status.get('missing', 0)}`",
        f"- unreadable: `{status.get('unreadable', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## Summary Rows",
        "",
        f"- exact_rule trades: `{exact.get('trades', '')}` mean_R: `{exact.get('mean_R', '')}` max_drawdown_R: `{exact.get('max_drawdown_R', '')}`",
        f"- single_filter_a trades: `{single.get('trades', '')}` mean_R: `{single.get('mean_R', '')}` max_drawdown_R: `{single.get('max_drawdown_R', '')}`",
        "",
        "## Preserved Row Counts",
        "",
        f"- walk_forward_split rows: `{types.get('walk_forward_split', 0)}`",
        f"- yearly_validation rows: `{types.get('yearly_validation', 0)}`",
        f"- artifact_availability rows: `{types.get('artifact_availability', 0)}`",
        "",
        "This consolidation does not replace deeper walk-forward review.",
        "Next suggested artifact area: split-by-split exact vs single_filter_a review.",
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
) -> None:
    status = status_counts(rows)
    types = row_type_counts(rows)
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "deeper_walkforward_output_root": str(args.deeper_walkforward_output_root),
        "exact_rule_dir": str(resolve_target_dir(args, "exact_rule")),
        "single_filter_a_dir": str(resolve_target_dir(args, "single_filter_a")),
        "run_specs_dir": str(args.run_specs_dir),
        "research_review_packet_dir": str(args.research_review_packet_dir),
        "consolidated_row_count": len(rows),
        "exact_rule_row_count": sum(1 for row in rows if row.get("review_target") == "exact_rule"),
        "single_filter_a_row_count": sum(1 for row in rows if row.get("review_target") == "single_filter_a"),
        "summary_row_count": types.get("summary_base", 0) + types.get("summary_stress", 0),
        "walk_forward_row_count": types.get("walk_forward_split", 0),
        "yearly_row_count": types.get("yearly_validation", 0),
        "artifact_availability_row_count": types.get("artifact_availability", 0),
        "available_count": status.get("available", 0),
        "available_with_caveat_count": status.get("available_with_caveat", 0),
        "missing_count": status.get("missing", 0),
        "unreadable_count": status.get("unreadable", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"),
        "no_child_scripts_executed": True,
        "no_stress_validation_executed": True,
        "no_walk_forward_validation_executed": True,
        "no_backtests_run": True,
        "no_timeout_policy_review_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_audit_executed": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    rows, warnings = build_consolidated_rows(args)
    write_csv(paths["consolidated"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Consolidate existing fixed-candidate deeper walk-forward manual outputs."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--deeper-walkforward-output-root", type=Path, default=DEFAULT_DEEPER_WALKFORWARD_OUTPUT_ROOT)
    parser.add_argument("--exact-rule-dir", type=Path)
    parser.add_argument("--single-filter-a-dir", type=Path)
    parser.add_argument("--run-specs-dir", type=Path, default=DEFAULT_RUN_SPECS_DIR)
    parser.add_argument("--research-review-packet-dir", type=Path, default=DEFAULT_RESEARCH_REVIEW_PACKET_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate deeper walk-forward output consolidation failed: {exc}")
        return 1
    print("Fixed-candidate deeper walk-forward output consolidation complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
