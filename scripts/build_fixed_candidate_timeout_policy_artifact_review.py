"""Build an artifact-only timeout policy artifact review.

This module reads existing exact-rule and single-filter trade logs, summarizes
their timeout-readable exit reasons, and writes neutral descriptive artifacts.
It does not run timeout review, validation, diagnostics, backtests, candidate
audit, model work, database work, or external execution.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_timeout_policy_artifact_review"
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
DEFAULT_TIMEOUT_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_timeout_policy_review_readiness"
    / "gbpusd_short_h10_1_5_off_hours_timeout_policy_review_readiness_v1"
)
DEFAULT_WALKFORWARD_DRAWDOWN_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_walkforward_drawdown_artifact_review"
    / "gbpusd_short_h10_1_5_off_hours_walkforward_drawdown_artifact_review_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_timeout_policy_artifact_review"

SUMMARY_FILE = "candidate_stress_summary.csv"
TRADE_BASE_FILE = "trade_log_base.csv"
TRADE_STRESS_FILE = "trade_log_stress.csv"
REPORT_FILE = "candidate_stress_report.md"
READINESS_FILE = "fixed_candidate_timeout_policy_review_readiness.csv"
READINESS_MANIFEST_FILE = "fixed_candidate_timeout_policy_review_readiness_manifest.json"

OUTPUT_CSV = "fixed_candidate_timeout_policy_artifact_review.csv"
OUTPUT_REPORT = "fixed_candidate_timeout_policy_artifact_review_report.md"
OUTPUT_WARNINGS = "fixed_candidate_timeout_policy_artifact_review_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_timeout_policy_artifact_review_manifest.json"

EXIT_REASON_COLUMN = "exit_reason"
OUTCOME_COLUMNS = {"exit_reason", "outcome", "hit_first"}
TIMEOUT_COLUMNS = {"exit_reason", "timeout", "timeout_flag", "is_timeout", "timed_out"}

FIELDNAMES = [
    "run_id",
    "review_scope",
    "cost_profile",
    "row_type",
    "exit_reason",
    "source_label",
    "baseline_type",
    "artifact_status",
    "source_trade_log",
    "source_summary_csv",
    "trade_count",
    "exit_reason_count",
    "exit_reason_rate",
    "mean_R",
    "mean_net_R",
    "median_net_R",
    "sum_net_R",
    "mean_cost_R",
    "mean_bars_held",
    "median_bars_held",
    "max_bars_held",
    "exact_timeout_rate",
    "single_filter_a_timeout_rate",
    "timeout_rate_delta",
    "exact_timeout_mean_net_R",
    "single_filter_a_timeout_mean_net_R",
    "timeout_mean_net_R_delta",
    "exact_timeout_mean_bars_held",
    "single_filter_a_timeout_mean_bars_held",
    "timeout_mean_bars_held_delta",
    "exact_timeout_sum_net_R",
    "single_filter_a_timeout_sum_net_R",
    "timeout_sum_net_R_delta",
    "readiness_status",
    "descriptive_observation",
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


def caveats(*values: str) -> str:
    return ";".join(value for value in values if value)


def join_values(values: list[str] | set[str] | tuple[str, ...]) -> str:
    return ";".join(value for value in sorted(values) if value)


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


def safe_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def numeric_values(rows: list[dict[str, str]], column: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = safe_float(row.get(column))
        if value is not None:
            values.append(value)
    return values


def mean_text(values: list[float]) -> str:
    if not values:
        return ""
    return str(sum(values) / len(values))


def median_text(values: list[float]) -> str:
    if not values:
        return ""
    return str(median(values))


def sum_text(values: list[float]) -> str:
    if not values:
        return ""
    return str(sum(values))


def max_text(values: list[float]) -> str:
    if not values:
        return ""
    return str(max(values))


def delta_text(left: object, right: object) -> str:
    left_value = safe_float(left)
    right_value = safe_float(right)
    if left_value is None or right_value is None:
        return ""
    return str(left_value - right_value)


def exit_reason_value(row: dict[str, str]) -> str:
    return str(row.get(EXIT_REASON_COLUMN, "")).strip()


def normalized_reason(value: str) -> str:
    return value.strip().lower()


def is_timeout_reason(value: str) -> bool:
    text = normalized_reason(value).replace("-", "_").replace(" ", "_")
    return "timeout" in text or "time_out" in text


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


def summarize_reason(rows: list[dict[str, str]], reason: str, total: int) -> dict[str, Any]:
    reason_rows = [row for row in rows if normalized_reason(exit_reason_value(row)) == normalized_reason(reason)]
    r_values = numeric_values(reason_rows, "R")
    net_values = numeric_values(reason_rows, "net_R")
    cost_values = numeric_values(reason_rows, "cost_R")
    held_values = numeric_values(reason_rows, "bars_held")
    count = len(reason_rows)
    return {
        "exit_reason_count": count,
        "exit_reason_rate": str(count / total) if total else "",
        "mean_R": mean_text(r_values),
        "mean_net_R": mean_text(net_values),
        "median_net_R": median_text(net_values),
        "sum_net_R": sum_text(net_values),
        "mean_cost_R": mean_text(cost_values),
        "mean_bars_held": mean_text(held_values),
        "median_bars_held": median_text(held_values),
        "max_bars_held": max_text(held_values),
    }


def log_artifact(source_dir: Path, source_label: str, cost_profile: str) -> dict[str, Any]:
    trade_file = TRADE_BASE_FILE if cost_profile == "p75" else TRADE_STRESS_FILE
    trade_path = source_dir / trade_file
    summary_path = source_dir / SUMMARY_FILE
    rows = read_csv_rows(trade_path)
    fieldnames = read_csv_fieldnames(trade_path)
    return {
        "source_dir": source_dir,
        "source_label": source_label,
        "baseline_type": "exact_rule" if source_label == "exact_rule" else "single_filter_a",
        "cost_profile": cost_profile,
        "trade_path": trade_path,
        "summary_path": summary_path,
        "exists": trade_path.exists(),
        "summary_exists": summary_path.exists(),
        "rows": rows,
        "fieldnames": fieldnames,
        "has_exit_reason": EXIT_REASON_COLUMN in fieldnames,
        "outcome_columns": [column for column in fieldnames if column in OUTCOME_COLUMNS],
        "timeout_columns": [column for column in fieldnames if column in TIMEOUT_COLUMNS],
    }


def base_review_row(args: argparse.Namespace, *, review_scope: str, artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "review_scope": review_scope,
        "cost_profile": artifact["cost_profile"],
        "row_type": "exit_reason_distribution",
        "exit_reason": "",
        "source_label": artifact["source_label"],
        "baseline_type": artifact["baseline_type"],
        "artifact_status": "available",
        "source_trade_log": artifact["trade_path"],
        "source_summary_csv": artifact["summary_path"] if artifact["summary_exists"] else "",
        "trade_count": len(artifact["rows"]),
        "exit_reason_count": "",
        "exit_reason_rate": "",
        "mean_R": "",
        "mean_net_R": "",
        "median_net_R": "",
        "sum_net_R": "",
        "mean_cost_R": "",
        "mean_bars_held": "",
        "median_bars_held": "",
        "max_bars_held": "",
        "exact_timeout_rate": "",
        "single_filter_a_timeout_rate": "",
        "timeout_rate_delta": "",
        "exact_timeout_mean_net_R": "",
        "single_filter_a_timeout_mean_net_R": "",
        "timeout_mean_net_R_delta": "",
        "exact_timeout_mean_bars_held": "",
        "single_filter_a_timeout_mean_bars_held": "",
        "timeout_mean_bars_held_delta": "",
        "exact_timeout_sum_net_R": "",
        "single_filter_a_timeout_sum_net_R": "",
        "timeout_sum_net_R_delta": "",
        "readiness_status": "descriptive_timeout_review_available",
        "descriptive_observation": "exit_reason_distribution_available",
        "caveat": caveats("descriptive_only_no_decision", "no_path_recomputation_performed"),
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


def blocked_or_missing_row(
    args: argparse.Namespace,
    *,
    review_scope: str,
    artifact: dict[str, Any],
    warnings: list[dict[str, Any]],
    optional: bool,
) -> dict[str, Any]:
    row = base_review_row(args, review_scope=review_scope, artifact=artifact)
    if not artifact["exists"]:
        row["artifact_status"] = "missing"
        row["readiness_status"] = (
            "descriptive_timeout_review_available_with_caveat" if optional else "unavailable_missing_artifact"
        )
        row["descriptive_observation"] = "further_timeout_policy_review_required"
        row["caveat"] = caveats("timeout_policy_review_still_separate", "descriptive_only_no_decision")
        row["required_next_artifact"] = "trade_log_with_exit_reason_and_timeout_rows"
        row["warning_code"] = f"{review_scope}_trade_log_missing"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="Trade log artifact is missing.",
            review_scope=review_scope,
            source_path=artifact["trade_path"],
            blocking=False,
        )
        return row
    if not artifact["has_exit_reason"]:
        row["artifact_status"] = "available"
        row["readiness_status"] = "blocked_requires_timeout_artifact"
        row["descriptive_observation"] = "further_timeout_policy_review_required"
        row["caveat"] = caveats("timeout_policy_review_still_separate", "descriptive_only_no_decision")
        row["required_next_artifact"] = "trade_log_with_exit_reason"
        row["warning_code"] = f"{review_scope}_exit_reason_missing"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="Trade log is present but exit_reason is missing.",
            review_scope=review_scope,
            source_path=artifact["trade_path"],
        )
        return row
    return row


def distribution_rows(
    args: argparse.Namespace,
    *,
    review_scope: str,
    artifact: dict[str, Any],
    warnings: list[dict[str, Any]],
    optional: bool = False,
) -> list[dict[str, Any]]:
    issue_row = blocked_or_missing_row(
        args,
        review_scope=review_scope,
        artifact=artifact,
        warnings=warnings,
        optional=optional,
    )
    if issue_row["readiness_status"] != "descriptive_timeout_review_available":
        return [issue_row]

    rows = artifact["rows"]
    total = len(rows)
    grouped: dict[str, str] = {}
    for reason in sorted({exit_reason_value(row) for row in rows if exit_reason_value(row)}, key=str.lower):
        grouped[normalized_reason(reason)] = reason

    output_rows: list[dict[str, Any]] = []
    for reason in grouped.values():
        row = base_review_row(args, review_scope=review_scope, artifact=artifact)
        row["exit_reason"] = reason
        row.update(summarize_reason(rows, reason, total))
        output_rows.append(row)
    if not output_rows:
        row = base_review_row(args, review_scope=review_scope, artifact=artifact)
        row["readiness_status"] = "blocked_requires_timeout_artifact"
        row["descriptive_observation"] = "further_timeout_policy_review_required"
        row["required_next_artifact"] = "trade_log_with_exit_reason_values"
        row["warning_code"] = f"{review_scope}_exit_reason_values_missing"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="Trade log has exit_reason column but no populated values.",
            review_scope=review_scope,
            source_path=artifact["trade_path"],
        )
        output_rows.append(row)
    return output_rows


def timeout_distribution(artifact: dict[str, Any]) -> dict[str, Any] | None:
    if not artifact["exists"] or not artifact["has_exit_reason"]:
        return None
    for reason in {exit_reason_value(row) for row in artifact["rows"] if exit_reason_value(row)}:
        if is_timeout_reason(reason):
            return summarize_reason(artifact["rows"], reason, len(artifact["rows"]))
    return {
        "exit_reason_count": 0,
        "exit_reason_rate": "0.0" if artifact["rows"] else "",
        "mean_net_R": "",
        "sum_net_R": "",
        "mean_bars_held": "",
    }


def comparison_row(
    args: argparse.Namespace,
    *,
    review_scope: str,
    exact: dict[str, Any],
    single: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    base = base_review_row(args, review_scope=review_scope, artifact=exact)
    base.update(
        {
            "row_type": "timeout_comparison",
            "exit_reason": "timeout",
            "source_label": "exact_rule_vs_single_filter_a",
            "baseline_type": "single_filter_a",
            "source_trade_log": f"{exact['trade_path']};{single['trade_path']}",
            "source_summary_csv": f"{exact['summary_path']};{single['summary_path']}",
            "trade_count": "",
            "exit_reason_count": "",
            "exit_reason_rate": "",
            "descriptive_observation": caveats(
                "timeout_mean_net_R_compared_descriptively",
                "timeout_bars_held_compared_descriptively",
                "descriptive_only_no_decision",
            ),
        }
    )
    if not exact["exists"] or not single["exists"]:
        base["artifact_status"] = "missing"
        base["readiness_status"] = "unavailable_missing_artifact"
        base["required_next_artifact"] = "base_or_stress_trade_logs_for_both_sources"
        base["warning_code"] = f"{review_scope}_trade_log_missing"
        add_warning(
            warnings,
            warning_code=base["warning_code"],
            message="One or both trade logs are missing for timeout comparison.",
            review_scope=review_scope,
            source_path=base["source_trade_log"],
        )
        return base
    if not exact["has_exit_reason"] or not single["has_exit_reason"]:
        base["readiness_status"] = "blocked_requires_timeout_artifact"
        base["required_next_artifact"] = "trade_logs_with_exit_reason_for_both_sources"
        base["warning_code"] = f"{review_scope}_exit_reason_missing"
        add_warning(
            warnings,
            warning_code=base["warning_code"],
            message="One or both trade logs are missing exit_reason for timeout comparison.",
            review_scope=review_scope,
            source_path=base["source_trade_log"],
        )
        return base

    exact_timeout = timeout_distribution(exact)
    single_timeout = timeout_distribution(single)
    if exact_timeout is None or single_timeout is None:
        base["readiness_status"] = "blocked_requires_timeout_artifact"
        base["required_next_artifact"] = "timeout-readable_trade_logs"
        base["warning_code"] = f"{review_scope}_timeout_distribution_unavailable"
        return base

    exact_rate = exact_timeout.get("exit_reason_rate", "")
    single_rate = single_timeout.get("exit_reason_rate", "")
    observation = "exact_timeout_rate_higher_observed"
    exact_rate_value = safe_float(exact_rate)
    single_rate_value = safe_float(single_rate)
    if exact_rate_value is not None and single_rate_value is not None and exact_rate_value < single_rate_value:
        observation = "exact_timeout_rate_lower_observed"
    base.update(
        {
            "exact_timeout_rate": exact_rate,
            "single_filter_a_timeout_rate": single_rate,
            "timeout_rate_delta": delta_text(exact_rate, single_rate),
            "exact_timeout_mean_net_R": exact_timeout.get("mean_net_R", ""),
            "single_filter_a_timeout_mean_net_R": single_timeout.get("mean_net_R", ""),
            "timeout_mean_net_R_delta": delta_text(
                exact_timeout.get("mean_net_R", ""),
                single_timeout.get("mean_net_R", ""),
            ),
            "exact_timeout_mean_bars_held": exact_timeout.get("mean_bars_held", ""),
            "single_filter_a_timeout_mean_bars_held": single_timeout.get("mean_bars_held", ""),
            "timeout_mean_bars_held_delta": delta_text(
                exact_timeout.get("mean_bars_held", ""),
                single_timeout.get("mean_bars_held", ""),
            ),
            "exact_timeout_sum_net_R": exact_timeout.get("sum_net_R", ""),
            "single_filter_a_timeout_sum_net_R": single_timeout.get("sum_net_R", ""),
            "timeout_sum_net_R_delta": delta_text(
                exact_timeout.get("sum_net_R", ""),
                single_timeout.get("sum_net_R", ""),
            ),
            "descriptive_observation": caveats(
                observation,
                "timeout_mean_net_R_compared_descriptively",
                "timeout_bars_held_compared_descriptively",
                "descriptive_only_no_decision",
            ),
        }
    )
    return base


def next_artifact_row(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "review_scope": "timeout_policy_next_artifact_area",
        "cost_profile": "",
        "row_type": "next_artifact_area",
        "exit_reason": "",
        "source_label": "exact_rule_vs_single_filter_a",
        "baseline_type": "single_filter_a",
        "artifact_status": "available",
        "source_trade_log": "",
        "source_summary_csv": "",
        "trade_count": "",
        "exit_reason_count": "",
        "exit_reason_rate": "",
        "mean_R": "",
        "mean_net_R": "",
        "median_net_R": "",
        "sum_net_R": "",
        "mean_cost_R": "",
        "mean_bars_held": "",
        "median_bars_held": "",
        "max_bars_held": "",
        "exact_timeout_rate": "",
        "single_filter_a_timeout_rate": "",
        "timeout_rate_delta": "",
        "exact_timeout_mean_net_R": "",
        "single_filter_a_timeout_mean_net_R": "",
        "timeout_mean_net_R_delta": "",
        "exact_timeout_mean_bars_held": "",
        "single_filter_a_timeout_mean_bars_held": "",
        "timeout_mean_bars_held_delta": "",
        "exact_timeout_sum_net_R": "",
        "single_filter_a_timeout_sum_net_R": "",
        "timeout_sum_net_R_delta": "",
        "readiness_status": "descriptive_timeout_review_available_with_caveat",
        "descriptive_observation": caveats(
            "timeout_policy_review_still_separate",
            "further_timeout_policy_review_required",
            "descriptive_only_no_decision",
        ),
        "caveat": caveats("timeout_policy_review_still_separate", "descriptive_only_no_decision"),
        "required_next_artifact": "separate_timeout_policy_review_artifact",
        "warning_code": "",
        "blocking_warning": False,
    }


def build_review_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    exact_base = log_artifact(Path(args.exact_stress_dir), "exact_rule", "p75")
    exact_stress = log_artifact(Path(args.exact_stress_dir), "exact_rule", "p90")
    single_base = log_artifact(Path(args.single_filter_a_stress_dir), "single_filter_a", "p75")
    single_stress = log_artifact(Path(args.single_filter_a_stress_dir), "single_filter_a", "p90")
    warnings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    rows.extend(
        distribution_rows(
            args,
            review_scope="exact_rule_base_exit_reason_distribution",
            artifact=exact_base,
            warnings=warnings,
        )
    )
    rows.extend(
        distribution_rows(
            args,
            review_scope="exact_rule_stress_exit_reason_distribution",
            artifact=exact_stress,
            warnings=warnings,
            optional=True,
        )
    )
    rows.extend(
        distribution_rows(
            args,
            review_scope="single_filter_a_base_exit_reason_distribution",
            artifact=single_base,
            warnings=warnings,
        )
    )
    rows.extend(
        distribution_rows(
            args,
            review_scope="single_filter_a_stress_exit_reason_distribution",
            artifact=single_stress,
            warnings=warnings,
            optional=True,
        )
    )
    rows.append(
        comparison_row(
            args,
            review_scope="exact_vs_single_filter_a_base_timeout_comparison",
            exact=exact_base,
            single=single_base,
            warnings=warnings,
        )
    )
    rows.append(
        comparison_row(
            args,
            review_scope="exact_vs_single_filter_a_stress_timeout_comparison",
            exact=exact_stress,
            single=single_stress,
            warnings=warnings,
        )
    )
    rows.append(next_artifact_row(args))
    artifacts = [exact_base, exact_stress, single_base, single_stress]
    metadata = {
        "detected_outcome_columns": sorted({column for artifact in artifacts for column in artifact["outcome_columns"]}),
        "detected_timeout_columns": sorted({column for artifact in artifacts for column in artifact["timeout_columns"]}),
        "timeout_readiness_rows": len(read_csv_rows(Path(args.timeout_readiness_dir) / READINESS_FILE)),
        "timeout_readiness_manifest_exists": (Path(args.timeout_readiness_dir) / READINESS_MANIFEST_FILE).exists(),
        "walkforward_drawdown_review_dir": str(args.walkforward_drawdown_review_dir or ""),
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
    comparisons = {row["review_scope"]: row for row in rows if row["row_type"] == "timeout_comparison"}
    base = comparisons.get("exact_vs_single_filter_a_base_timeout_comparison", {})
    stress = comparisons.get("exact_vs_single_filter_a_stress_timeout_comparison", {})
    distribution_scopes = Counter(row["review_scope"] for row in rows if row["row_type"] == "exit_reason_distribution")
    lines = [
        "# Fixed Candidate Timeout Policy Artifact Review",
        "",
        "Artifact-only descriptive review. It reads existing trade-log artifacts and does not execute timeout review, validation, diagnostics, backtests, candidate audit, model work, database mutation, or external execution.",
        "No candidate-quality conclusion or trading decision was made.",
        "No path outcomes were recomputed; this review only summarizes timeout-readable fields already present in artifacts.",
        "",
        "## Inputs",
        "",
        f"- exact_stress_dir: `{args.exact_stress_dir}`",
        f"- single_filter_a_stress_dir: `{args.single_filter_a_stress_dir}`",
        f"- timeout_readiness_dir: `{args.timeout_readiness_dir}`",
        f"- walkforward_drawdown_review_dir: `{args.walkforward_drawdown_review_dir or ''}`",
        "",
        "## Counts",
        "",
        f"- review_row_count: `{len(rows)}`",
        f"- descriptive_timeout_review_available: `{counts.get('descriptive_timeout_review_available', 0)}`",
        f"- descriptive_timeout_review_available_with_caveat: `{counts.get('descriptive_timeout_review_available_with_caveat', 0)}`",
        f"- blocked_requires_timeout_artifact: `{counts.get('blocked_requires_timeout_artifact', 0)}`",
        f"- unavailable_missing_artifact: `{counts.get('unavailable_missing_artifact', 0)}`",
        f"- blocked_unreadable_input: `{counts.get('blocked_unreadable_input', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## Detected Columns",
        "",
        f"- outcome_columns: `{join_values(metadata.get('detected_outcome_columns', []))}`",
        f"- timeout_columns: `{join_values(metadata.get('detected_timeout_columns', []))}`",
        "",
        "## Exit Reason Distribution Summary",
        "",
        f"- exact_rule_base_exit_reason_distribution rows: `{distribution_scopes.get('exact_rule_base_exit_reason_distribution', 0)}`",
        f"- exact_rule_stress_exit_reason_distribution rows: `{distribution_scopes.get('exact_rule_stress_exit_reason_distribution', 0)}`",
        f"- single_filter_a_base_exit_reason_distribution rows: `{distribution_scopes.get('single_filter_a_base_exit_reason_distribution', 0)}`",
        f"- single_filter_a_stress_exit_reason_distribution rows: `{distribution_scopes.get('single_filter_a_stress_exit_reason_distribution', 0)}`",
        "",
        "## Exact vs Single Filter A Timeout Comparison",
        "",
        f"- base_timeout_rate_delta: `{base.get('timeout_rate_delta', '')}`",
        f"- base_timeout_mean_net_R_delta: `{base.get('timeout_mean_net_R_delta', '')}`",
        f"- base_timeout_mean_bars_held_delta: `{base.get('timeout_mean_bars_held_delta', '')}`",
        f"- stress_timeout_rate_delta: `{stress.get('timeout_rate_delta', '')}`",
        f"- stress_timeout_mean_net_R_delta: `{stress.get('timeout_mean_net_R_delta', '')}`",
        f"- stress_timeout_mean_bars_held_delta: `{stress.get('timeout_mean_bars_held_delta', '')}`",
        "",
        "Base and stress timeout comparison availability is artifact-derived only.",
        "This artifact does not replace a separate timeout policy review.",
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
        "timeout_readiness_dir": str(args.timeout_readiness_dir),
        "walkforward_drawdown_review_dir": str(args.walkforward_drawdown_review_dir or ""),
        "review_row_count": len(rows),
        "descriptive_timeout_review_available_count": counts.get("descriptive_timeout_review_available", 0),
        "descriptive_timeout_review_available_with_caveat_count": counts.get(
            "descriptive_timeout_review_available_with_caveat", 0
        ),
        "blocked_requires_timeout_artifact_count": counts.get("blocked_requires_timeout_artifact", 0),
        "unavailable_missing_artifact_count": counts.get("unavailable_missing_artifact", 0),
        "blocked_unreadable_input_count": counts.get("blocked_unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "detected_outcome_columns": metadata.get("detected_outcome_columns", []),
        "detected_timeout_columns": metadata.get("detected_timeout_columns", []),
        "timeout_readiness_rows": metadata.get("timeout_readiness_rows", 0),
        "timeout_readiness_manifest_exists": metadata.get("timeout_readiness_manifest_exists", False),
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
    rows, warnings, metadata = build_review_rows(args)
    write_csv(paths["review"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build an artifact-only timeout policy artifact review. "
            "No timeout review, validation, diagnostics, backtests, or child scripts are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--exact-stress-dir", type=Path, default=DEFAULT_EXACT_STRESS_DIR)
    parser.add_argument("--single-filter-a-stress-dir", type=Path, default=DEFAULT_SINGLE_FILTER_A_STRESS_DIR)
    parser.add_argument("--timeout-readiness-dir", type=Path, default=DEFAULT_TIMEOUT_READINESS_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--walkforward-drawdown-review-dir", type=Path, default=DEFAULT_WALKFORWARD_DRAWDOWN_REVIEW_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate timeout policy artifact review build failed: {exc}")
        return 1
    print("Fixed-candidate timeout policy artifact review build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
