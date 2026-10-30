"""Build an artifact-only split review for deeper walk-forward outputs.

This module reads the consolidated deeper walk-forward artifact table and
produces neutral exact-rule versus single-filter A split/year comparisons. It
does not execute validation, backtests, timeout review, diagnostics, candidate
audit, model work, database work, or external actions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_deeper_walkforward_split_review"
DEFAULT_CONSOLIDATED_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_deeper_walkforward_outputs_consolidated"
    / "gbpusd_short_h10_1_5_off_hours_deeper_walkforward_outputs_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_deeper_walkforward_split_review"

INPUT_CSV = "fixed_candidate_deeper_walkforward_outputs_consolidated.csv"
OUTPUT_CSV = "fixed_candidate_deeper_walkforward_split_review.csv"
OUTPUT_REPORT = "fixed_candidate_deeper_walkforward_split_review_report.md"
OUTPUT_WARNINGS = "fixed_candidate_deeper_walkforward_split_review_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_deeper_walkforward_split_review_manifest.json"

REVIEW_STATUSES = {
    "descriptive_split_review_available",
    "descriptive_split_review_available_with_caveat",
    "unavailable_missing_matching_row",
    "blocked_unreadable_input",
}

FIELDNAMES = [
    "run_id",
    "review_scope",
    "split_id",
    "year",
    "artifact_status",
    "source_consolidated_csv",
    "exact_source_output_dir",
    "baseline_source_output_dir",
    "exact_source_walk_forward_csv",
    "baseline_source_walk_forward_csv",
    "exact_source_yearly_csv",
    "baseline_source_yearly_csv",
    "exact_trades",
    "baseline_trades",
    "delta_trades",
    "trade_count_ratio_exact_to_baseline",
    "exact_mean_R",
    "baseline_mean_R",
    "delta_mean_R",
    "exact_profit_factor_R",
    "baseline_profit_factor_R",
    "delta_profit_factor_R",
    "exact_cumulative_R",
    "baseline_cumulative_R",
    "delta_cumulative_R",
    "exact_max_drawdown_R",
    "baseline_max_drawdown_R",
    "delta_max_drawdown_R",
    "exact_lower_drawdown_flag",
    "exact_mean_R_higher_flag",
    "exact_profit_factor_higher_flag",
    "descriptive_observation",
    "review_status",
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
    "split_id",
    "year",
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


def bool_text(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def caveats(*values: str) -> str:
    return ";".join(value for value in values if value)


def safe_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def delta_text(exact: object, baseline: object) -> str:
    left = safe_float(exact)
    right = safe_float(baseline)
    if left is None or right is None:
        return ""
    return str(left - right)


def ratio_text(exact: object, baseline: object) -> str:
    left = safe_float(exact)
    right = safe_float(baseline)
    if left is None or right in {None, 0}:
        return ""
    return str(left / right)


def greater_flag(exact: object, baseline: object) -> bool | None:
    left = safe_float(exact)
    right = safe_float(baseline)
    if left is None or right is None:
        return None
    return left > right


def lower_flag(exact: object, baseline: object) -> bool | None:
    left = safe_float(exact)
    right = safe_float(baseline)
    if left is None or right is None:
        return None
    return left < right


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


def input_csv_path(args: argparse.Namespace) -> Path:
    return Path(args.deeper_walkforward_consolidated_dir) / INPUT_CSV


def warning_row(
    *,
    warning_code: str,
    message: str,
    review_scope: str,
    split_id: str = "",
    year: str = "",
    blocking_warning: bool = False,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": "error" if blocking_warning else severity,
        "message": message,
        "review_scope": review_scope,
        "split_id": split_id,
        "year": year,
        "blocking_warning": bool_text(blocking_warning),
    }


def index_rows(rows: list[dict[str, str]], *, row_type: str, key_field: str) -> dict[str, dict[str, dict[str, str]]]:
    indexed = {"exact_rule": {}, "single_filter_a": {}}
    for row in rows:
        target = row.get("review_target", "")
        key = row.get(key_field, "")
        if target in indexed and row.get("row_type") == row_type and key:
            indexed[target][key] = row
    return indexed


def observation_for_row(exact_lower_drawdown: bool | None, mean_higher: bool | None, pf_higher: bool | None) -> str:
    labels = ["descriptive_only_no_decision"]
    if exact_lower_drawdown:
        labels.insert(0, "exact_lower_drawdown_observed")
    if mean_higher is False:
        labels.append("exact_mean_R_not_consistently_higher")
    if pf_higher is False:
        labels.append("exact_profit_factor_not_consistently_higher")
    labels.append("single_filter_a_higher_trade_count_observed")
    return caveats(*labels)


def comparison_row(
    *,
    args: argparse.Namespace,
    source_csv: Path,
    review_scope: str,
    key_field: str,
    key_value: str,
    exact: dict[str, str] | None,
    baseline: dict[str, str] | None,
) -> dict[str, Any]:
    row = {
        "run_id": args.run_id,
        "review_scope": review_scope,
        "split_id": key_value if key_field == "split_id" else "",
        "year": key_value if key_field == "year" else "",
        "artifact_status": "available",
        "source_consolidated_csv": source_csv,
        "exact_source_output_dir": exact.get("source_output_dir", "") if exact else "",
        "baseline_source_output_dir": baseline.get("source_output_dir", "") if baseline else "",
        "exact_source_walk_forward_csv": exact.get("source_walk_forward_csv", "") if exact else "",
        "baseline_source_walk_forward_csv": baseline.get("source_walk_forward_csv", "") if baseline else "",
        "exact_source_yearly_csv": exact.get("source_yearly_csv", "") if exact else "",
        "baseline_source_yearly_csv": baseline.get("source_yearly_csv", "") if baseline else "",
        "exact_trades": exact.get("trades", "") if exact else "",
        "baseline_trades": baseline.get("trades", "") if baseline else "",
        "delta_trades": "",
        "trade_count_ratio_exact_to_baseline": "",
        "exact_mean_R": exact.get("mean_R", "") if exact else "",
        "baseline_mean_R": baseline.get("mean_R", "") if baseline else "",
        "delta_mean_R": "",
        "exact_profit_factor_R": exact.get("profit_factor_R", "") if exact else "",
        "baseline_profit_factor_R": baseline.get("profit_factor_R", "") if baseline else "",
        "delta_profit_factor_R": "",
        "exact_cumulative_R": exact.get("cumulative_R", "") if exact else "",
        "baseline_cumulative_R": baseline.get("cumulative_R", "") if baseline else "",
        "delta_cumulative_R": "",
        "exact_max_drawdown_R": exact.get("max_drawdown_R", "") if exact else "",
        "baseline_max_drawdown_R": baseline.get("max_drawdown_R", "") if baseline else "",
        "delta_max_drawdown_R": "",
        "exact_lower_drawdown_flag": "",
        "exact_mean_R_higher_flag": "",
        "exact_profit_factor_higher_flag": "",
        "descriptive_observation": "descriptive_only_no_decision",
        "review_status": "descriptive_split_review_available",
        "caveat": "descriptive_only_no_decision",
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }
    if exact is None or baseline is None:
        row["artifact_status"] = "missing"
        row["review_status"] = "unavailable_missing_matching_row"
        row["caveat"] = "further_manual_validation_required;descriptive_only_no_decision"
        row["required_next_artifact"] = "matching_exact_rule_and_single_filter_a_rows"
        row["warning_code"] = "matching_row_missing"
        return row

    exact_lower_drawdown = lower_flag(row["exact_max_drawdown_R"], row["baseline_max_drawdown_R"])
    mean_higher = greater_flag(row["exact_mean_R"], row["baseline_mean_R"])
    pf_higher = greater_flag(row["exact_profit_factor_R"], row["baseline_profit_factor_R"])
    row.update(
        {
            "trade_count_ratio_exact_to_baseline": ratio_text(row["exact_trades"], row["baseline_trades"]),
            "delta_trades": delta_text(row["exact_trades"], row["baseline_trades"]),
            "delta_mean_R": delta_text(row["exact_mean_R"], row["baseline_mean_R"]),
            "delta_profit_factor_R": delta_text(row["exact_profit_factor_R"], row["baseline_profit_factor_R"]),
            "delta_cumulative_R": delta_text(row["exact_cumulative_R"], row["baseline_cumulative_R"]),
            "delta_max_drawdown_R": delta_text(row["exact_max_drawdown_R"], row["baseline_max_drawdown_R"]),
            "exact_lower_drawdown_flag": bool_text(exact_lower_drawdown),
            "exact_mean_R_higher_flag": bool_text(mean_higher),
            "exact_profit_factor_higher_flag": bool_text(pf_higher),
            "descriptive_observation": observation_for_row(exact_lower_drawdown, mean_higher, pf_higher),
        }
    )
    return row


def comparison_rows(
    *,
    args: argparse.Namespace,
    source_csv: Path,
    source_rows: list[dict[str, str]],
    row_type: str,
    key_field: str,
    review_scope: str,
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    indexed = index_rows(source_rows, row_type=row_type, key_field=key_field)
    keys = sorted(set(indexed["exact_rule"]) | set(indexed["single_filter_a"]))
    rows: list[dict[str, Any]] = []
    for key in keys:
        row = comparison_row(
            args=args,
            source_csv=source_csv,
            review_scope=review_scope,
            key_field=key_field,
            key_value=key,
            exact=indexed["exact_rule"].get(key),
            baseline=indexed["single_filter_a"].get(key),
        )
        rows.append(row)
        if row["review_status"] == "unavailable_missing_matching_row":
            warnings.append(
                warning_row(
                    warning_code="matching_row_missing",
                    message="A matching exact_rule or single_filter_a row is missing.",
                    review_scope=review_scope,
                    split_id=row["split_id"],
                    year=row["year"],
                )
            )
    return rows


def available_rows(rows: list[dict[str, Any]], review_scope: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("review_scope") == review_scope
        and row.get("review_status") == "descriptive_split_review_available"
    ]


def count_true(rows: list[dict[str, Any]], field: str) -> int:
    return sum(str(row.get(field)).lower() == "true" for row in rows)


def summary_row(
    *,
    args: argparse.Namespace,
    source_csv: Path,
    review_scope: str,
    source_rows: list[dict[str, Any]],
    required_next_artifact: str,
) -> dict[str, Any]:
    lower_count = count_true(source_rows, "exact_lower_drawdown_flag")
    mean_count = count_true(source_rows, "exact_mean_R_higher_flag")
    pf_count = count_true(source_rows, "exact_profit_factor_higher_flag")
    labels = ["descriptive_only_no_decision"]
    if source_rows and lower_count == len(source_rows):
        labels.insert(0, "exact_lower_drawdown_all_splits_observed")
    if source_rows and mean_count < len(source_rows):
        labels.append("exact_mean_R_not_consistently_higher")
    if source_rows and pf_count < len(source_rows):
        labels.append("exact_profit_factor_not_consistently_higher")
    labels.append("split_coverage_available" if "split" in review_scope else "yearly_coverage_available")
    return {
        "run_id": args.run_id,
        "review_scope": review_scope,
        "split_id": "",
        "year": "",
        "artifact_status": "available",
        "source_consolidated_csv": source_csv,
        "exact_source_output_dir": "",
        "baseline_source_output_dir": "",
        "exact_source_walk_forward_csv": "",
        "baseline_source_walk_forward_csv": "",
        "exact_source_yearly_csv": "",
        "baseline_source_yearly_csv": "",
        "exact_trades": "",
        "baseline_trades": "",
        "delta_trades": "",
        "trade_count_ratio_exact_to_baseline": "",
        "exact_mean_R": "",
        "baseline_mean_R": "",
        "delta_mean_R": "",
        "exact_profit_factor_R": "",
        "baseline_profit_factor_R": "",
        "delta_profit_factor_R": "",
        "exact_cumulative_R": "",
        "baseline_cumulative_R": "",
        "delta_cumulative_R": "",
        "exact_max_drawdown_R": lower_count,
        "baseline_max_drawdown_R": len(source_rows),
        "delta_max_drawdown_R": "",
        "exact_lower_drawdown_flag": "",
        "exact_mean_R_higher_flag": "",
        "exact_profit_factor_higher_flag": "",
        "descriptive_observation": caveats(*labels),
        "review_status": "descriptive_split_review_available_with_caveat",
        "caveat": "descriptive_only_no_decision",
        "required_next_artifact": required_next_artifact,
        "warning_code": "",
        "blocking_warning": False,
    }


def next_review_area_row(args: argparse.Namespace, source_csv: Path) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "review_scope": "next_review_area",
        "split_id": "",
        "year": "",
        "artifact_status": "available",
        "source_consolidated_csv": source_csv,
        "exact_source_output_dir": "",
        "baseline_source_output_dir": "",
        "exact_source_walk_forward_csv": "",
        "baseline_source_walk_forward_csv": "",
        "exact_source_yearly_csv": "",
        "baseline_source_yearly_csv": "",
        "exact_trades": "",
        "baseline_trades": "",
        "delta_trades": "",
        "trade_count_ratio_exact_to_baseline": "",
        "exact_mean_R": "",
        "baseline_mean_R": "",
        "delta_mean_R": "",
        "exact_profit_factor_R": "",
        "baseline_profit_factor_R": "",
        "delta_profit_factor_R": "",
        "exact_cumulative_R": "",
        "baseline_cumulative_R": "",
        "delta_cumulative_R": "",
        "exact_max_drawdown_R": "",
        "baseline_max_drawdown_R": "",
        "delta_max_drawdown_R": "",
        "exact_lower_drawdown_flag": "",
        "exact_mean_R_higher_flag": "",
        "exact_profit_factor_higher_flag": "",
        "descriptive_observation": "further_manual_validation_required;candidate_audit_still_separate;descriptive_only_no_decision",
        "review_status": "descriptive_split_review_available_with_caveat",
        "caveat": "candidate_audit_still_separate;descriptive_only_no_decision",
        "required_next_artifact": "manual_review_or_candidate_audit_artifact",
        "warning_code": "",
        "blocking_warning": False,
    }


def build_review_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_csv = input_csv_path(args)
    warnings: list[dict[str, Any]] = []
    if not source_csv.exists():
        warnings.append(
            warning_row(
                warning_code="consolidated_csv_missing",
                severity="error",
                message="Required consolidated deeper walk-forward CSV is missing.",
                review_scope="input_artifact",
                blocking_warning=True,
            )
        )
        row = next_review_area_row(args, source_csv)
        row["artifact_status"] = "missing"
        row["review_status"] = "blocked_unreadable_input"
        row["warning_code"] = "consolidated_csv_missing"
        row["blocking_warning"] = True
        return [row], warnings

    source_rows = read_csv_rows(source_csv)
    split_rows = comparison_rows(
        args=args,
        source_csv=source_csv,
        source_rows=source_rows,
        row_type="walk_forward_split",
        key_field="split_id",
        review_scope="walk_forward_split_comparison",
        warnings=warnings,
    )
    yearly_rows = comparison_rows(
        args=args,
        source_csv=source_csv,
        source_rows=source_rows,
        row_type="yearly_validation",
        key_field="year",
        review_scope="yearly_validation_comparison",
        warnings=warnings,
    )
    split_available = available_rows(split_rows, "walk_forward_split_comparison")
    yearly_available = available_rows(yearly_rows, "yearly_validation_comparison")
    rows = [
        *split_rows,
        *yearly_rows,
        summary_row(
            args=args,
            source_csv=source_csv,
            review_scope="walk_forward_split_summary",
            source_rows=split_available,
            required_next_artifact="split_by_split_manual_review",
        ),
        summary_row(
            args=args,
            source_csv=source_csv,
            review_scope="yearly_validation_summary",
            source_rows=yearly_available,
            required_next_artifact="yearly_manual_review",
        ),
        next_review_area_row(args, source_csv),
    ]
    return rows, warnings


def status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("review_status") or "") for row in rows)


def write_report(path: Path, *, args: argparse.Namespace, rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    split_rows = available_rows(rows, "walk_forward_split_comparison")
    yearly_rows = available_rows(rows, "yearly_validation_comparison")
    exact_lower = count_true(split_rows, "exact_lower_drawdown_flag")
    mean_higher = count_true(split_rows, "exact_mean_R_higher_flag")
    pf_higher = count_true(split_rows, "exact_profit_factor_higher_flag")
    lines = [
        "# Fixed Candidate Deeper Walk-Forward Split Review",
        "",
        "Artifact-only descriptive review. It reads consolidated deeper walk-forward artifacts and does not execute validation, walk-forward validation, backtests, timeout review, diagnostics, candidate audit, model work, database mutation, or external actions.",
        "No candidate-quality conclusion, ranking, or trading decision was made.",
        "",
        "## Inputs",
        "",
        f"- deeper_walkforward_consolidated_dir: `{args.deeper_walkforward_consolidated_dir}`",
        f"- source_csv: `{input_csv_path(args)}`",
        "",
        "## Split-By-Split Summary",
        "",
        f"- matched_split_count: `{len(split_rows)}`",
        f"- exact_lower_drawdown_split_count: `{exact_lower}`",
        f"- exact_mean_R_higher_split_count: `{mean_higher}`",
        f"- exact_profit_factor_higher_split_count: `{pf_higher}`",
        "",
        "## Yearly Summary",
        "",
        f"- matched_year_count: `{len(yearly_rows)}`",
        "",
        "This artifact does not replace final candidate audit.",
        "Suggested next artifact area: manual review or candidate audit artifact.",
        f"- warnings: `{len(warnings)}`",
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
    counts = status_counts(rows)
    split_rows = available_rows(rows, "walk_forward_split_comparison")
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "deeper_walkforward_consolidated_dir": str(args.deeper_walkforward_consolidated_dir),
        "review_row_count": len(rows),
        "walk_forward_split_comparison_count": sum(row.get("review_scope") == "walk_forward_split_comparison" for row in rows),
        "yearly_validation_comparison_count": sum(row.get("review_scope") == "yearly_validation_comparison" for row in rows),
        "descriptive_split_review_available_count": counts.get("descriptive_split_review_available", 0),
        "unavailable_missing_matching_row_count": counts.get("unavailable_missing_matching_row", 0),
        "blocked_unreadable_input_count": counts.get("blocked_unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"),
        "exact_lower_drawdown_split_count": count_true(split_rows, "exact_lower_drawdown_flag"),
        "exact_mean_R_higher_split_count": count_true(split_rows, "exact_mean_R_higher_flag"),
        "exact_profit_factor_higher_split_count": count_true(split_rows, "exact_profit_factor_higher_flag"),
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
    rows, warnings = build_review_rows(args)
    write_csv(paths["review"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an artifact-only deeper walk-forward split review."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--deeper-walkforward-consolidated-dir", type=Path, default=DEFAULT_CONSOLIDATED_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate deeper walk-forward split review failed: {exc}")
        return 1
    print("Fixed-candidate deeper walk-forward split review complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
