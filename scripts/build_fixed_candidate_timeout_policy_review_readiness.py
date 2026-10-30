"""Build an artifact-only timeout policy review-readiness table.

This module inspects existing exact-rule and single-filter stress artifacts to
see whether timeout behavior can be reviewed from already-produced trade logs.
It does not run validation, diagnostics, backtests, timeout review, candidate
audit, model work, database work, or external execution.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_timeout_policy_review_readiness"
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
DEFAULT_WALKFORWARD_DRAWDOWN_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_walkforward_drawdown_artifact_review"
    / "gbpusd_short_h10_1_5_off_hours_walkforward_drawdown_artifact_review_v1"
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
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_timeout_policy_review_readiness"

SUMMARY_FILE = "candidate_stress_summary.csv"
TRADE_BASE_FILE = "trade_log_base.csv"
TRADE_STRESS_FILE = "trade_log_stress.csv"
REPORT_FILE = "candidate_stress_report.md"
YEARLY_FILES = ("yearly_validation_summary.csv", "yearly_validation.csv")
WALK_FORWARD_FILES = ("walk_forward_summary.csv", "walk_forward_validation.csv")

OUTPUT_CSV = "fixed_candidate_timeout_policy_review_readiness.csv"
OUTPUT_REPORT = "fixed_candidate_timeout_policy_review_readiness_report.md"
OUTPUT_WARNINGS = "fixed_candidate_timeout_policy_review_readiness_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_timeout_policy_review_readiness_manifest.json"

EXPLICIT_TIMEOUT_COLUMNS = {"timeout", "timeout_flag", "is_timeout", "timed_out"}
OUTCOME_COLUMNS = {"outcome", "exit_reason", "hit_first", "exit_type", "result"}
CONTEXT_COLUMNS = {
    "bars_held",
    "holding_period",
    "selected_R",
    "net_R",
    "gross_R",
    "R",
    "target_family",
    "horizon",
}

FIELDNAMES = [
    "run_id",
    "review_scope",
    "artifact_status",
    "exact_source_dir",
    "baseline_source_dir",
    "exact_trade_log_base_path",
    "baseline_trade_log_base_path",
    "exact_trade_log_stress_path",
    "baseline_trade_log_stress_path",
    "exact_available_columns",
    "baseline_available_columns",
    "exact_timeout_columns_detected",
    "baseline_timeout_columns_detected",
    "exact_trade_count",
    "baseline_trade_count",
    "exact_timeout_count",
    "baseline_timeout_count",
    "exact_timeout_rate",
    "baseline_timeout_rate",
    "exact_outcome_columns_detected",
    "baseline_outcome_columns_detected",
    "exact_target_family",
    "baseline_target_family",
    "exact_horizon",
    "baseline_horizon",
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
    "source_path",
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


def join_values(values: list[str] | tuple[str, ...] | set[str]) -> str:
    return ";".join(value for value in sorted(values) if value)


def caveats(*values: str) -> str:
    return ";".join(value for value in values if value)


def normalized_column(name: str) -> str:
    return name.strip().lower()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_csv_fieldnames(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or [])


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


def first_row(path: Path) -> dict[str, str]:
    rows = read_csv_rows(path)
    return rows[0] if rows else {}


def timeout_flag_is_true(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "timeout", "timed_out"}


def outcome_is_timeout(value: str) -> bool:
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    return "timeout" in text or "time_out" in text


def timeout_count_from_rows(rows: list[dict[str, str]], explicit_columns: list[str], outcome_columns: list[str]) -> int:
    count = 0
    for row in rows:
        if any(timeout_flag_is_true(row.get(column, "")) for column in explicit_columns):
            count += 1
            continue
        if any(outcome_is_timeout(row.get(column, "")) for column in outcome_columns):
            count += 1
    return count


def timeout_rate_text(count: int | None, total: int) -> str:
    if count is None or total <= 0:
        return ""
    return str(count / total)


def value_from(summary: dict[str, str], rows: list[dict[str, str]], key: str) -> str:
    if summary.get(key):
        return summary[key]
    for row in rows:
        if row.get(key):
            return row[key]
    return ""


def analyze_trade_artifacts(directory: Path) -> dict[str, Any]:
    summary_path = directory / SUMMARY_FILE
    base_path = directory / TRADE_BASE_FILE
    stress_path = directory / TRADE_STRESS_FILE
    base_rows = read_csv_rows(base_path)
    stress_rows = read_csv_rows(stress_path)
    primary_rows = base_rows if base_rows else stress_rows
    fieldnames = sorted(set(read_csv_fieldnames(base_path)) | set(read_csv_fieldnames(stress_path)))
    normalized_lookup = {normalized_column(column): column for column in fieldnames}
    explicit_timeout_columns = [
        normalized_lookup[name]
        for name in EXPLICIT_TIMEOUT_COLUMNS
        if name in normalized_lookup
    ]
    outcome_columns = [
        normalized_lookup[name]
        for name in OUTCOME_COLUMNS
        if name in normalized_lookup
    ]
    context_columns = [
        normalized_lookup[name]
        for name in CONTEXT_COLUMNS
        if name in normalized_lookup
    ]
    timeout_columns_detected = sorted(set(explicit_timeout_columns) | set(outcome_columns))
    timeout_count: int | None = None
    if timeout_columns_detected:
        timeout_count = timeout_count_from_rows(primary_rows, explicit_timeout_columns, outcome_columns)
    summary = first_row(summary_path) if summary_path.exists() else {}
    return {
        "directory": directory,
        "exists": directory.exists(),
        "summary_path": summary_path,
        "summary_exists": summary_path.exists(),
        "summary_row": summary,
        "base_path": base_path,
        "base_exists": base_path.exists(),
        "stress_path": stress_path,
        "stress_exists": stress_path.exists(),
        "report_path": directory / REPORT_FILE,
        "report_exists": (directory / REPORT_FILE).exists(),
        "yearly_path": first_existing_file(directory, YEARLY_FILES),
        "walk_forward_path": first_existing_file(directory, WALK_FORWARD_FILES),
        "available_columns": fieldnames,
        "timeout_columns_detected": timeout_columns_detected,
        "outcome_columns_detected": outcome_columns,
        "context_columns_detected": context_columns,
        "trade_count": len(primary_rows),
        "timeout_count": timeout_count,
        "timeout_rate": timeout_rate_text(timeout_count, len(primary_rows)),
        "target_family": value_from(summary, primary_rows, "target_family"),
        "horizon": value_from(summary, primary_rows, "horizon"),
    }


def artifact_status(artifact: dict[str, Any]) -> str:
    if not artifact["exists"]:
        return "missing"
    if not artifact["base_exists"] and not artifact["stress_exists"]:
        return "missing"
    return "available"


def timeout_ready(artifact: dict[str, Any]) -> bool:
    return (
        artifact_status(artifact) == "available"
        and artifact["trade_count"] > 0
        and bool(artifact["timeout_columns_detected"])
    )


def base_row(args: argparse.Namespace, *, review_scope: str, exact: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "review_scope": review_scope,
        "artifact_status": "available",
        "exact_source_dir": exact["directory"],
        "baseline_source_dir": baseline["directory"],
        "exact_trade_log_base_path": exact["base_path"] if exact["base_exists"] else "",
        "baseline_trade_log_base_path": baseline["base_path"] if baseline["base_exists"] else "",
        "exact_trade_log_stress_path": exact["stress_path"] if exact["stress_exists"] else "",
        "baseline_trade_log_stress_path": baseline["stress_path"] if baseline["stress_exists"] else "",
        "exact_available_columns": join_values(exact["available_columns"]),
        "baseline_available_columns": join_values(baseline["available_columns"]),
        "exact_timeout_columns_detected": join_values(exact["timeout_columns_detected"]),
        "baseline_timeout_columns_detected": join_values(baseline["timeout_columns_detected"]),
        "exact_trade_count": exact["trade_count"],
        "baseline_trade_count": baseline["trade_count"],
        "exact_timeout_count": exact["timeout_count"],
        "baseline_timeout_count": baseline["timeout_count"],
        "exact_timeout_rate": exact["timeout_rate"],
        "baseline_timeout_rate": baseline["timeout_rate"],
        "exact_outcome_columns_detected": join_values(exact["outcome_columns_detected"]),
        "baseline_outcome_columns_detected": join_values(baseline["outcome_columns_detected"]),
        "exact_target_family": exact["target_family"],
        "baseline_target_family": baseline["target_family"],
        "exact_horizon": exact["horizon"],
        "baseline_horizon": baseline["horizon"],
        "readiness_status": "ready_for_timeout_artifact_review",
        "caveat": caveats(
            "timeout_columns_detected",
            "outcome_columns_detected",
            "descriptive_only_no_decision",
            "no_path_recomputation_performed",
        ),
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    warning_code: str,
    message: str,
    review_scope: str,
    source_path: Path | str,
    blocking: bool = False,
    severity: str = "warning",
) -> None:
    warnings.append(
        {
            "warning_code": warning_code,
            "severity": "error" if blocking else severity,
            "message": message,
            "review_scope": review_scope,
            "source_path": source_path,
            "blocking_warning": blocking,
        }
    )


def artifact_availability_row(
    args: argparse.Namespace,
    *,
    scope: str,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    artifact: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = base_row(args, review_scope=scope, exact=exact, baseline=baseline)
    row["artifact_status"] = artifact_status(artifact)
    if not artifact["exists"]:
        row["readiness_status"] = "unavailable_missing_artifact"
        row["caveat"] = caveats("trade_logs_missing", "requires_timeout_artifact_generation")
        row["required_next_artifact"] = "stress_output_directory_with_trade_logs"
        row["warning_code"] = f"{scope}_source_dir_missing"
        row["blocking_warning"] = True
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="Required stress output directory is missing.",
            review_scope=scope,
            source_path=artifact["directory"],
            blocking=True,
        )
    elif not artifact["base_exists"] and not artifact["stress_exists"]:
        row["readiness_status"] = "unavailable_missing_artifact"
        row["caveat"] = caveats("trade_logs_missing", "requires_timeout_artifact_generation")
        row["required_next_artifact"] = "trade_log_base_or_trade_log_stress_with_timeout_or_outcome_columns"
        row["warning_code"] = f"{scope}_trade_logs_missing"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="No trade log artifact was found for timeout readiness review.",
            review_scope=scope,
            source_path=artifact["directory"],
        )
    elif not artifact["timeout_columns_detected"]:
        row["readiness_status"] = "blocked_requires_timeout_artifact"
        row["caveat"] = caveats("timeout_columns_missing", "requires_timeout_artifact_generation")
        row["required_next_artifact"] = "trade_log_with_timeout_flag_or_timeout_outcome_values"
        row["warning_code"] = f"{scope}_timeout_columns_missing"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="Trade logs are present but no timeout-detectable columns or values were found.",
            review_scope=scope,
            source_path=artifact["directory"],
        )
    elif not artifact["summary_exists"]:
        row["readiness_status"] = "ready_with_caveat"
        row["caveat"] = caveats(row["caveat"], "trade_logs_present")
        row["warning_code"] = f"{scope}_summary_missing"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="Summary artifact is missing; timeout readiness was inferred from trade logs only.",
            review_scope=scope,
            source_path=artifact["summary_path"],
        )
    else:
        row["caveat"] = caveats(row["caveat"], "trade_logs_present")
    return row


def combined_status(exact: dict[str, Any], baseline: dict[str, Any]) -> tuple[str, str, str, str, bool]:
    if not exact["exists"] or not baseline["exists"]:
        return (
            "unavailable_missing_artifact",
            "trade_logs_missing;requires_timeout_artifact_generation",
            "stress_output_directories_with_trade_logs",
            "required_stress_dir_missing",
            True,
        )
    if artifact_status(exact) != "available" or artifact_status(baseline) != "available":
        return (
            "unavailable_missing_artifact",
            "trade_logs_missing;requires_timeout_artifact_generation",
            "trade_logs_with_timeout_or_outcome_columns",
            "trade_logs_missing",
            False,
        )
    if not timeout_ready(exact) or not timeout_ready(baseline):
        return (
            "blocked_requires_timeout_artifact",
            "timeout_columns_missing;requires_timeout_artifact_generation",
            "trade_logs_with_timeout_flag_or_timeout_outcome_values",
            "timeout_columns_missing",
            False,
        )
    return (
        "ready_for_timeout_artifact_review",
        "timeout_columns_detected;outcome_columns_detected;descriptive_only_no_decision;no_path_recomputation_performed",
        "",
        "",
        False,
    )


def combined_review_row(
    args: argparse.Namespace,
    *,
    review_scope: str,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = base_row(args, review_scope=review_scope, exact=exact, baseline=baseline)
    status, caveat, required_next, warning_code, blocking = combined_status(exact, baseline)
    row["readiness_status"] = status
    row["caveat"] = caveat
    row["required_next_artifact"] = required_next
    row["warning_code"] = warning_code
    row["blocking_warning"] = blocking
    if warning_code:
        add_warning(
            warnings,
            warning_code=f"{review_scope}_{warning_code}",
            message="Exact-rule and single-filter A artifacts are not both ready for timeout artifact review.",
            review_scope=review_scope,
            source_path=f"{exact['directory']};{baseline['directory']}",
            blocking=blocking,
        )
    return row


def next_requirement_row(
    args: argparse.Namespace,
    *,
    exact: dict[str, Any],
    baseline: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = combined_review_row(
        args,
        review_scope="next_timeout_artifact_requirement",
        exact=exact,
        baseline=baseline,
        warnings=warnings,
    )
    if row["readiness_status"] == "ready_for_timeout_artifact_review":
        row["readiness_status"] = "ready_with_caveat"
        row["caveat"] = caveats(
            "timeout_policy_review_still_separate",
            "exact_vs_single_filter_a_timeout_review_pending",
            "descriptive_only_no_decision",
            "no_path_recomputation_performed",
        )
        row["required_next_artifact"] = "separate_timeout_policy_artifact_review"
    return row


def build_readiness_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    exact = analyze_trade_artifacts(Path(args.exact_stress_dir))
    baseline = analyze_trade_artifacts(Path(args.single_filter_a_stress_dir))
    warnings: list[dict[str, Any]] = []
    rows = [
        artifact_availability_row(
            args,
            scope="exact_rule_timeout_artifact_availability",
            exact=exact,
            baseline=baseline,
            artifact=exact,
            warnings=warnings,
        ),
        artifact_availability_row(
            args,
            scope="single_filter_a_timeout_artifact_availability",
            exact=exact,
            baseline=baseline,
            artifact=baseline,
            warnings=warnings,
        ),
        combined_review_row(
            args,
            review_scope="exact_vs_single_filter_a_timeout_column_coverage",
            exact=exact,
            baseline=baseline,
            warnings=warnings,
        ),
        combined_review_row(
            args,
            review_scope="exact_vs_single_filter_a_timeout_descriptive_counts",
            exact=exact,
            baseline=baseline,
            warnings=warnings,
        ),
        combined_review_row(
            args,
            review_scope="exact_vs_single_filter_a_timeout_review_readiness",
            exact=exact,
            baseline=baseline,
            warnings=warnings,
        ),
        next_requirement_row(args, exact=exact, baseline=baseline, warnings=warnings),
    ]
    metadata = {
        "walkforward_drawdown_review_dir_exists": Path(args.walkforward_drawdown_review_dir).exists(),
        "comparison_table_dir": str(args.comparison_table_dir or ""),
        "r_multiple_review_dir": str(args.r_multiple_review_dir or ""),
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
    row_by_scope = {row["review_scope"]: row for row in rows}
    coverage = row_by_scope.get("exact_vs_single_filter_a_timeout_column_coverage", {})
    readiness = row_by_scope.get("exact_vs_single_filter_a_timeout_review_readiness", {})
    lines = [
        "# Fixed Candidate Timeout Policy Review Readiness",
        "",
        "Artifact-only readiness review. It reads existing stress and trade-log artifacts and does not execute timeout review, validation, diagnostics, backtests, candidate audit, model work, database mutation, or external execution.",
        "No candidate-quality conclusion or trading decision was made.",
        "No path outcomes were recomputed; timeout behavior is only summarized when current artifacts expose timeout-detectable fields or values.",
        "",
        "## Inputs",
        "",
        f"- exact_stress_dir: `{args.exact_stress_dir}`",
        f"- single_filter_a_stress_dir: `{args.single_filter_a_stress_dir}`",
        f"- walkforward_drawdown_review_dir: `{args.walkforward_drawdown_review_dir}`",
        f"- comparison_table_dir: `{args.comparison_table_dir or ''}`",
        f"- r_multiple_review_dir: `{args.r_multiple_review_dir or ''}`",
        "",
        "## Counts",
        "",
        f"- review_row_count: `{len(rows)}`",
        f"- ready_for_timeout_artifact_review: `{counts.get('ready_for_timeout_artifact_review', 0)}`",
        f"- ready_with_caveat: `{counts.get('ready_with_caveat', 0)}`",
        f"- blocked_requires_timeout_artifact: `{counts.get('blocked_requires_timeout_artifact', 0)}`",
        f"- unavailable_missing_artifact: `{counts.get('unavailable_missing_artifact', 0)}`",
        f"- blocked_unreadable_input: `{counts.get('blocked_unreadable_input', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## Detected Columns",
        "",
        f"- exact_available_columns: `{coverage.get('exact_available_columns', '')}`",
        f"- single_filter_a_available_columns: `{coverage.get('baseline_available_columns', '')}`",
        f"- exact_timeout_columns_detected: `{coverage.get('exact_timeout_columns_detected', '')}`",
        f"- single_filter_a_timeout_columns_detected: `{coverage.get('baseline_timeout_columns_detected', '')}`",
        f"- exact_outcome_columns_detected: `{coverage.get('exact_outcome_columns_detected', '')}`",
        f"- single_filter_a_outcome_columns_detected: `{coverage.get('baseline_outcome_columns_detected', '')}`",
        "",
        "## Timeout Readiness Summary",
        "",
        f"- readiness_status: `{readiness.get('readiness_status', '')}`",
        f"- exact_trade_count: `{readiness.get('exact_trade_count', '')}`",
        f"- single_filter_a_trade_count: `{readiness.get('baseline_trade_count', '')}`",
        f"- exact_timeout_count: `{readiness.get('exact_timeout_count', '')}`",
        f"- single_filter_a_timeout_count: `{readiness.get('baseline_timeout_count', '')}`",
        f"- exact_timeout_rate: `{readiness.get('exact_timeout_rate', '')}`",
        f"- single_filter_a_timeout_rate: `{readiness.get('baseline_timeout_rate', '')}`",
        "",
        "## Required Next Artifact",
        "",
        f"- `{readiness.get('required_next_artifact', '') or 'separate_timeout_policy_artifact_review'}`",
        "",
        "This readiness artifact does not replace a true timeout policy review.",
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
        "walkforward_drawdown_review_dir": str(args.walkforward_drawdown_review_dir),
        "comparison_table_dir": str(args.comparison_table_dir or ""),
        "r_multiple_review_dir": str(args.r_multiple_review_dir or ""),
        "review_row_count": len(rows),
        "ready_for_timeout_artifact_review_count": counts.get("ready_for_timeout_artifact_review", 0),
        "ready_with_caveat_count": counts.get("ready_with_caveat", 0),
        "blocked_requires_timeout_artifact_count": counts.get("blocked_requires_timeout_artifact", 0),
        "unavailable_missing_artifact_count": counts.get("unavailable_missing_artifact", 0),
        "blocked_unreadable_input_count": counts.get("blocked_unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "walkforward_drawdown_review_dir_exists": metadata.get("walkforward_drawdown_review_dir_exists", False),
        "no_child_scripts_executed": True,
        "no_stress_validation_executed": True,
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
    rows, warnings, metadata = build_readiness_rows(args)
    write_csv(paths["readiness"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build an artifact-only timeout policy review-readiness table. "
            "No timeout review, validation, diagnostics, backtests, or child scripts are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--exact-stress-dir", type=Path, default=DEFAULT_EXACT_STRESS_DIR)
    parser.add_argument("--single-filter-a-stress-dir", type=Path, default=DEFAULT_SINGLE_FILTER_A_STRESS_DIR)
    parser.add_argument("--walkforward-drawdown-review-dir", type=Path, default=DEFAULT_WALKFORWARD_DRAWDOWN_REVIEW_DIR)
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
        print(f"Fixed-candidate timeout policy review-readiness build failed: {exc}")
        return 1
    print("Fixed-candidate timeout policy review-readiness build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
