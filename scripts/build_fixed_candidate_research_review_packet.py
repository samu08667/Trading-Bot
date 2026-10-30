"""Build an artifact-only fixed-candidate research review packet.

This module consolidates completed fixed-candidate review artifacts into one
neutral packet. It reads existing CSV, manifest, warning, and report files only;
it does not run validation, backtests, timeout review, diagnostics, candidate
audit, model work, database work, or external actions.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_research_review_packet"
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
DEFAULT_WALKFORWARD_DRAWDOWN_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_walkforward_drawdown_review_readiness"
    / "gbpusd_short_h10_1_5_off_hours_walkforward_drawdown_review_readiness_v1"
)
DEFAULT_WALKFORWARD_DRAWDOWN_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_walkforward_drawdown_artifact_review"
    / "gbpusd_short_h10_1_5_off_hours_walkforward_drawdown_artifact_review_v1"
)
DEFAULT_TIMEOUT_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_timeout_policy_review_readiness"
    / "gbpusd_short_h10_1_5_off_hours_timeout_policy_review_readiness_v1"
)
DEFAULT_TIMEOUT_ARTIFACT_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_timeout_policy_artifact_review"
    / "gbpusd_short_h10_1_5_off_hours_timeout_policy_artifact_review_v1"
)
DEFAULT_EQUITY_DRAWDOWN_SEQUENCE_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_equity_drawdown_sequence_review"
    / "gbpusd_short_h10_1_5_off_hours_equity_drawdown_sequence_review_v1"
)
DEFAULT_EXACT_STRESS_DIR = (
    BASE_DIR
    / "reports"
    / "regime_candidate_stress"
    / "gbpusd_short_h10_1_5_off_hours_stress_exec_v2"
)
DEFAULT_BASELINE_R_MULTIPLE_CONSOLIDATED_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_r_multiple_outputs_consolidated"
    / "gbpusd_short_h10_1_5_off_hours_baseline_r_multiple_outputs_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_research_review_packet"

OUTPUT_CSV = "fixed_candidate_research_review_packet.csv"
OUTPUT_REPORT = "fixed_candidate_research_review_packet_report.md"
OUTPUT_WARNINGS = "fixed_candidate_research_review_packet_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_research_review_packet_manifest.json"

FIELDNAMES = [
    "run_id",
    "review_block",
    "artifact_status",
    "source_dir",
    "source_manifest",
    "source_report",
    "source_csv",
    "source_warning_count",
    "source_blocking_warning_count",
    "key_metric_1_name",
    "key_metric_1_value",
    "key_metric_2_name",
    "key_metric_2_value",
    "key_metric_3_name",
    "key_metric_3_value",
    "descriptive_summary",
    "evidence_status",
    "caveat",
    "required_next_artifact",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "review_block",
    "source_path",
    "blocking_warning",
]


@dataclass(frozen=True)
class ArtifactSpec:
    key: str
    arg_name: str
    csv_name: str
    manifest_name: str
    report_name: str
    warnings_name: str
    required: bool = True


SPECS = {
    "comparison": ArtifactSpec(
        key="comparison",
        arg_name="comparison_table_dir",
        csv_name="fixed_candidate_baseline_comparison_table.csv",
        manifest_name="fixed_candidate_baseline_comparison_manifest.json",
        report_name="fixed_candidate_baseline_comparison_report.md",
        warnings_name="fixed_candidate_baseline_comparison_warnings.csv",
    ),
    "r_review": ArtifactSpec(
        key="r_review",
        arg_name="r_multiple_review_dir",
        csv_name="fixed_candidate_r_multiple_baseline_review.csv",
        manifest_name="fixed_candidate_r_multiple_baseline_review_manifest.json",
        report_name="fixed_candidate_r_multiple_baseline_review_report.md",
        warnings_name="fixed_candidate_r_multiple_baseline_review_warnings.csv",
    ),
    "wf_readiness": ArtifactSpec(
        key="wf_readiness",
        arg_name="walkforward_drawdown_readiness_dir",
        csv_name="fixed_candidate_walkforward_drawdown_review_readiness.csv",
        manifest_name="fixed_candidate_walkforward_drawdown_review_readiness_manifest.json",
        report_name="fixed_candidate_walkforward_drawdown_review_readiness_report.md",
        warnings_name="fixed_candidate_walkforward_drawdown_review_readiness_warnings.csv",
    ),
    "wf_review": ArtifactSpec(
        key="wf_review",
        arg_name="walkforward_drawdown_review_dir",
        csv_name="fixed_candidate_walkforward_drawdown_artifact_review.csv",
        manifest_name="fixed_candidate_walkforward_drawdown_artifact_review_manifest.json",
        report_name="fixed_candidate_walkforward_drawdown_artifact_review_report.md",
        warnings_name="fixed_candidate_walkforward_drawdown_artifact_review_warnings.csv",
    ),
    "timeout_readiness": ArtifactSpec(
        key="timeout_readiness",
        arg_name="timeout_readiness_dir",
        csv_name="fixed_candidate_timeout_policy_review_readiness.csv",
        manifest_name="fixed_candidate_timeout_policy_review_readiness_manifest.json",
        report_name="fixed_candidate_timeout_policy_review_readiness_report.md",
        warnings_name="fixed_candidate_timeout_policy_review_readiness_warnings.csv",
    ),
    "timeout_review": ArtifactSpec(
        key="timeout_review",
        arg_name="timeout_artifact_review_dir",
        csv_name="fixed_candidate_timeout_policy_artifact_review.csv",
        manifest_name="fixed_candidate_timeout_policy_artifact_review_manifest.json",
        report_name="fixed_candidate_timeout_policy_artifact_review_report.md",
        warnings_name="fixed_candidate_timeout_policy_artifact_review_warnings.csv",
    ),
    "equity_review": ArtifactSpec(
        key="equity_review",
        arg_name="equity_drawdown_sequence_review_dir",
        csv_name="fixed_candidate_equity_drawdown_sequence_review.csv",
        manifest_name="fixed_candidate_equity_drawdown_sequence_review_manifest.json",
        report_name="fixed_candidate_equity_drawdown_sequence_review_report.md",
        warnings_name="fixed_candidate_equity_drawdown_sequence_review_warnings.csv",
    ),
    "baseline_r_outputs": ArtifactSpec(
        key="baseline_r_outputs",
        arg_name="baseline_r_multiple_consolidated_dir",
        csv_name="fixed_candidate_baseline_r_multiple_outputs_consolidated.csv",
        manifest_name="fixed_candidate_baseline_r_multiple_outputs_manifest.json",
        report_name="fixed_candidate_baseline_r_multiple_outputs_report.md",
        warnings_name="fixed_candidate_baseline_r_multiple_outputs_warnings.csv",
        required=False,
    ),
}


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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "packet": output_dir / OUTPUT_CSV,
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


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    warning_code: str,
    message: str,
    review_block: str,
    source_path: Path | str,
    blocking: bool = False,
) -> None:
    warnings.append(
        {
            "warning_code": warning_code,
            "severity": "error" if blocking else "warning",
            "message": message,
            "review_block": review_block,
            "source_path": source_path,
            "blocking_warning": blocking,
        }
    )


def artifact_paths(spec: ArtifactSpec, args: argparse.Namespace) -> dict[str, Path]:
    directory = Path(getattr(args, spec.arg_name))
    return {
        "dir": directory,
        "csv": directory / spec.csv_name,
        "manifest": directory / spec.manifest_name,
        "report": directory / spec.report_name,
        "warnings": directory / spec.warnings_name,
    }


def load_artifact(spec: ArtifactSpec, args: argparse.Namespace) -> dict[str, Any]:
    paths = artifact_paths(spec, args)
    manifest = read_json(paths["manifest"])
    csv_rows = read_csv_rows(paths["csv"])
    warning_rows = read_csv_rows(paths["warnings"])
    exists = paths["csv"].exists() and paths["manifest"].exists() and paths["report"].exists()
    return {
        "spec": spec,
        "paths": paths,
        "manifest": manifest,
        "csv_rows": csv_rows,
        "warning_rows": warning_rows,
        "exists": exists,
        "warnings_count": manifest.get("warnings_count", len(warning_rows)),
        "blocking_warnings_count": manifest.get(
            "blocking_warnings_count",
            sum(1 for row in warning_rows if str(row.get("blocking_warning")).lower() == "true"),
        ),
    }


def base_row(args: argparse.Namespace, *, review_block: str, artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    if artifact:
        paths = artifact["paths"]
        source_warning_count = artifact["warnings_count"]
        source_blocking_count = artifact["blocking_warnings_count"]
    else:
        paths = {"dir": "", "manifest": "", "report": "", "csv": ""}
        source_warning_count = ""
        source_blocking_count = ""
    return {
        "run_id": args.run_id,
        "review_block": review_block,
        "artifact_status": "available",
        "source_dir": paths["dir"],
        "source_manifest": paths["manifest"],
        "source_report": paths["report"],
        "source_csv": paths["csv"],
        "source_warning_count": source_warning_count,
        "source_blocking_warning_count": source_blocking_count,
        "key_metric_1_name": "",
        "key_metric_1_value": "",
        "key_metric_2_name": "",
        "key_metric_2_value": "",
        "key_metric_3_name": "",
        "key_metric_3_value": "",
        "descriptive_summary": "descriptive_only_no_decision",
        "evidence_status": "descriptive_evidence_available",
        "caveat": "descriptive_only_no_decision",
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


def set_metric(row: dict[str, Any], index: int, name: str, value: Any) -> None:
    row[f"key_metric_{index}_name"] = name
    row[f"key_metric_{index}_value"] = value


def artifact_status_row(
    args: argparse.Namespace,
    *,
    review_block: str,
    artifact: dict[str, Any],
    summary: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = base_row(args, review_block=review_block, artifact=artifact)
    spec: ArtifactSpec = artifact["spec"]
    if not artifact["exists"]:
        row["artifact_status"] = "missing"
        row["evidence_status"] = "missing_required_artifact" if spec.required else "descriptive_evidence_available_with_caveat"
        row["caveat"] = "further_manual_validation_required"
        row["required_next_artifact"] = "completed_review_artifact_directory"
        row["warning_code"] = f"{review_block}_missing"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="Expected review artifact files are missing.",
            review_block=review_block,
            source_path=artifact["paths"]["dir"],
            blocking=spec.required,
        )
        row["blocking_warning"] = spec.required
        return row
    if int(artifact["blocking_warnings_count"] or 0) > 0:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "descriptive_evidence_available_with_caveat"
        row["caveat"] = "requires_deeper_walkforward_or_timeout_validation"
    elif int(artifact["warnings_count"] or 0) > 0:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "descriptive_evidence_available_with_caveat"
        row["caveat"] = "further_manual_validation_required"
    row["descriptive_summary"] = summary
    set_metric(row, 1, "source_rows", len(artifact["csv_rows"]))
    set_metric(row, 2, "source_warnings", artifact["warnings_count"])
    set_metric(row, 3, "source_blocking_warnings", artifact["blocking_warnings_count"])
    return row


def find_row(rows: list[dict[str, str]], **criteria: str) -> dict[str, str]:
    for row in rows:
        if all(row.get(key) == value for key, value in criteria.items()):
            return row
    return {}


def comparison_status_row(args: argparse.Namespace, artifacts: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    artifact = artifacts["comparison"]
    row = artifact_status_row(
        args,
        review_block="r_multiple_comparison_table_status",
        artifact=artifact,
        summary="same_namespace_r_multiple_available;descriptive_only_no_decision",
        warnings=warnings,
    )
    manifest = artifact["manifest"]
    set_metric(row, 1, "comparison_row_count", manifest.get("comparison_row_count", ""))
    set_metric(row, 2, "metric_namespaces", ";".join(manifest.get("metric_namespaces", [])))
    set_metric(row, 3, "mixed_metric_namespaces", manifest.get("mixed_metric_namespaces", ""))
    return row


def r_review_row(
    args: argparse.Namespace,
    *,
    review_block: str,
    artifact: dict[str, Any],
    review_scope: str,
    baseline_type: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = artifact_status_row(
        args,
        review_block=review_block,
        artifact=artifact,
        summary="same_namespace_r_multiple_available;descriptive_only_no_decision",
        warnings=warnings,
    )
    rows = [source for source in artifact["csv_rows"] if source.get("review_scope") == review_scope and source.get("baseline_type") == baseline_type]
    if rows:
        p75 = next((source for source in rows if source.get("cost_profile") == "p75"), rows[0])
        set_metric(row, 1, "trade_count_ratio_exact_to_baseline", p75.get("trade_count_ratio_exact_to_baseline", ""))
        set_metric(row, 2, "delta_mean_R", p75.get("delta_mean_R", ""))
        set_metric(row, 3, "delta_max_drawdown_R", p75.get("delta_max_drawdown_R", ""))
    return row


def wf_review_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    row = artifact_status_row(
        args,
        review_block="walkforward_drawdown_artifact_review_status",
        artifact=artifact,
        summary="walkforward_artifacts_available;exact_lower_drawdown_observed;single_filter_a_higher_trade_count_observed;average_edge_not_clearly_higher_for_exact;descriptive_only_no_decision",
        warnings=warnings,
    )
    source = find_row(artifact["csv_rows"], review_scope="exact_vs_single_filter_a_drawdown_review")
    set_metric(row, 1, "exact_trades", source.get("exact_trades", ""))
    set_metric(row, 2, "baseline_trades", source.get("baseline_trades", ""))
    set_metric(row, 3, "baseline_max_drawdown_R", source.get("baseline_max_drawdown_R", ""))
    return row


def timeout_artifact_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    row = artifact_status_row(
        args,
        review_block="timeout_artifact_review_status",
        artifact=artifact,
        summary="timeout_artifacts_available;timeout_rate_not_lower_for_exact;exact_timeout_mean_net_R_less_negative_observed;descriptive_only_no_decision",
        warnings=warnings,
    )
    source = find_row(artifact["csv_rows"], review_scope="exact_vs_single_filter_a_base_timeout_comparison")
    set_metric(row, 1, "timeout_rate_delta", source.get("timeout_rate_delta", ""))
    set_metric(row, 2, "timeout_mean_net_R_delta", source.get("timeout_mean_net_R_delta", ""))
    set_metric(row, 3, "timeout_sum_net_R_delta", source.get("timeout_sum_net_R_delta", ""))
    return row


def equity_artifact_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    row = artifact_status_row(
        args,
        review_block="equity_drawdown_sequence_review_status",
        artifact=artifact,
        summary="exact_drawdown_sequence_improved_observed;exact_loss_cluster_reduction_observed;descriptive_only_no_decision",
        warnings=warnings,
    )
    source = find_row(artifact["csv_rows"], review_scope="exact_vs_single_filter_a_base_drawdown_sequence_comparison")
    set_metric(row, 1, "drawdown_delta", source.get("drawdown_delta", ""))
    set_metric(row, 2, "drawdown_duration_delta", source.get("drawdown_duration_delta", ""))
    set_metric(row, 3, "longest_negative_streak_delta", source.get("longest_negative_streak_delta", ""))
    return row


def simple_manifest_row(
    args: argparse.Namespace,
    *,
    review_block: str,
    artifact: dict[str, Any],
    summary: str,
    metric_prefix: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = artifact_status_row(args, review_block=review_block, artifact=artifact, summary=summary, warnings=warnings)
    manifest = artifact["manifest"]
    set_metric(row, 1, f"{metric_prefix}_row_count", manifest.get("review_row_count", manifest.get("comparison_row_count", "")))
    set_metric(row, 2, "warnings_count", manifest.get("warnings_count", ""))
    set_metric(row, 3, "blocking_warnings_count", manifest.get("blocking_warnings_count", ""))
    return row


def synthesis_row(args: argparse.Namespace, *, review_block: str, summary: str, caveat: str, required_next: str) -> dict[str, Any]:
    row = base_row(args, review_block=review_block)
    row["artifact_status"] = "available_with_caveat"
    row["evidence_status"] = "descriptive_evidence_available_with_caveat"
    row["descriptive_summary"] = summary
    row["caveat"] = caveat
    row["required_next_artifact"] = required_next
    return row


def optional_source_missing(args: argparse.Namespace) -> list[str]:
    missing: list[str] = []
    exact_dir = Path(args.exact_stress_dir)
    if not (exact_dir / "candidate_stress_summary.csv").exists() or not (exact_dir / "candidate_stress_report.md").exists():
        missing.append("exact_stress_source")
    return missing


def chain_integrity_row(args: argparse.Namespace, artifacts: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    row = base_row(args, review_block="artifact_chain_integrity")
    required_missing = [key for key, artifact in artifacts.items() if artifact["spec"].required and not artifact["exists"]]
    optional_missing = [key for key, artifact in artifacts.items() if not artifact["spec"].required and not artifact["exists"]]
    optional_missing.extend(optional_source_missing(args))
    if required_missing:
        row["artifact_status"] = "missing"
        row["evidence_status"] = "missing_required_artifact"
        row["warning_code"] = "artifact_chain_missing_required_review"
        row["blocking_warning"] = True
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="One or more required review artifacts are missing.",
            review_block=row["review_block"],
            source_path=";".join(required_missing),
            blocking=True,
        )
    elif optional_missing:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "descriptive_evidence_available_with_caveat"
        row["warning_code"] = "artifact_chain_optional_source_missing"
        row["caveat"] = "further_manual_validation_required"
        add_warning(
            warnings,
            warning_code=row["warning_code"],
            message="One or more optional source artifacts are missing.",
            review_block=row["review_block"],
            source_path=";".join(optional_missing),
        )
    row["source_dir"] = ";".join([*(str(artifact["paths"]["dir"]) for artifact in artifacts.values()), str(args.exact_stress_dir)])
    set_metric(row, 1, "required_artifact_count", sum(1 for artifact in artifacts.values() if artifact["spec"].required))
    set_metric(row, 2, "required_missing_count", len(required_missing))
    set_metric(row, 3, "optional_missing_count", len(optional_missing))
    row["descriptive_summary"] = "descriptive_only_no_decision"
    return row


def build_packet_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    artifacts = {key: load_artifact(spec, args) for key, spec in SPECS.items()}
    warnings: list[dict[str, Any]] = []
    rows = [
        chain_integrity_row(args, artifacts, warnings),
        comparison_status_row(args, artifacts, warnings),
        r_review_row(
            args,
            review_block="exact_vs_broad_baseline_review",
            artifact=artifacts["r_review"],
            review_scope="exact_vs_broad_regime_baseline",
            baseline_type="broad_regime_baseline",
            warnings=warnings,
        ),
        r_review_row(
            args,
            review_block="exact_vs_single_filter_a_review",
            artifact=artifacts["r_review"],
            review_scope="exact_vs_single_filter_a",
            baseline_type="single_filter_a",
            warnings=warnings,
        ),
        r_review_row(
            args,
            review_block="exact_vs_single_filter_b_review",
            artifact=artifacts["r_review"],
            review_scope="exact_vs_single_filter_b",
            baseline_type="single_filter_b",
            warnings=warnings,
        ),
        simple_manifest_row(
            args,
            review_block="walkforward_drawdown_readiness_status",
            artifact=artifacts["wf_readiness"],
            summary="walkforward_artifacts_available;descriptive_only_no_decision",
            metric_prefix="readiness",
            warnings=warnings,
        ),
        wf_review_row(args, artifacts["wf_review"], warnings),
        simple_manifest_row(
            args,
            review_block="timeout_readiness_status",
            artifact=artifacts["timeout_readiness"],
            summary="timeout_artifacts_available;descriptive_only_no_decision",
            metric_prefix="timeout_readiness",
            warnings=warnings,
        ),
        timeout_artifact_row(args, artifacts["timeout_review"], warnings),
        equity_artifact_row(args, artifacts["equity_review"], warnings),
        synthesis_row(
            args,
            review_block="key_tradeoff_summary",
            summary="exact_more_selective_observed;exact_lower_drawdown_observed;exact_drawdown_sequence_improved_observed;exact_loss_cluster_reduction_observed;single_filter_a_higher_trade_count_observed;average_edge_not_clearly_higher_for_exact;descriptive_only_no_decision",
            caveat="requires_deeper_walkforward_or_timeout_validation;descriptive_only_no_decision",
            required_next="deeper_walkforward_or_timeout_validation_artifact",
        ),
        synthesis_row(
            args,
            review_block="remaining_caveats",
            summary="requires_deeper_walkforward_or_timeout_validation;further_manual_validation_required;descriptive_only_no_decision",
            caveat="descriptive_only_no_decision",
            required_next="manual_heavy_validation_artifacts_before_candidate_audit",
        ),
        synthesis_row(
            args,
            review_block="recommended_next_research_artifact",
            summary="further_manual_validation_required;descriptive_only_no_decision",
            caveat="descriptive_only_no_decision",
            required_next="controlled_deeper_walkforward_or_timeout_policy_artifact",
        ),
    ]
    return rows, warnings


def status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("artifact_status") or "") for row in rows)


def write_report(path: Path, *, args: argparse.Namespace, rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    counts = status_counts(rows)
    row_by_block = {row["review_block"]: row for row in rows}
    single = row_by_block.get("exact_vs_single_filter_a_review", {})
    timeout = row_by_block.get("timeout_artifact_review_status", {})
    equity = row_by_block.get("equity_drawdown_sequence_review_status", {})
    lines = [
        "# Fixed Candidate Research Review Packet",
        "",
        "Artifact-only review packet. It reads completed review artifacts and does not execute validation, backtests, timeout review, diagnostics, candidate audit, model work, database mutation, or external actions.",
        "No candidate-quality conclusion or trading decision was made.",
        "",
        "## Artifact Chain",
        "",
        f"- packet_rows: `{len(rows)}`",
        f"- available: `{counts.get('available', 0)}`",
        f"- available_with_caveat: `{counts.get('available_with_caveat', 0)}`",
        f"- missing: `{counts.get('missing', 0)}`",
        f"- unreadable: `{counts.get('unreadable', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## R Multiple Summary",
        "",
        "- same-namespace R_multiple comparison artifacts are available for exact_rule and baseline rows.",
        f"- exact_vs_single_filter_a trade_count_ratio_exact_to_baseline: `{single.get('key_metric_1_value', '')}`",
        f"- exact_vs_single_filter_a delta_mean_R: `{single.get('key_metric_2_value', '')}`",
        f"- exact_vs_single_filter_a delta_max_drawdown_R: `{single.get('key_metric_3_value', '')}`",
        "",
        "## Exact vs Single Filter A Trade-Off",
        "",
        "The exact_rule appears to add selectivity, drawdown, and loss-cluster improvement versus single_filter_a.",
        "The exact_rule does not clearly improve mean_R or profit_factor_R versus single_filter_a.",
        "",
        "## Timeout Artifact Summary",
        "",
        f"- timeout_rate_delta: `{timeout.get('key_metric_1_value', '')}`",
        f"- timeout_mean_net_R_delta: `{timeout.get('key_metric_2_value', '')}`",
        "Timeout rate is slightly higher for exact_rule, while timeout mean_net_R is less negative in the reviewed artifacts.",
        "",
        "## Equity / Drawdown Sequence Summary",
        "",
        f"- drawdown_delta: `{equity.get('key_metric_1_value', '')}`",
        f"- drawdown_duration_delta: `{equity.get('key_metric_2_value', '')}`",
        f"- longest_negative_streak_delta: `{equity.get('key_metric_3_value', '')}`",
        "",
        "## Caveats And Next Artifact Area",
        "",
        "This packet does not replace true walk-forward validation, timeout policy review, or final candidate audit.",
        "Recommended next research artifact area: controlled deeper walk-forward or timeout-policy artifact review.",
        "This packet is not a strategy decision.",
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
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "comparison_table_dir": str(args.comparison_table_dir),
        "r_multiple_review_dir": str(args.r_multiple_review_dir),
        "walkforward_drawdown_readiness_dir": str(args.walkforward_drawdown_readiness_dir),
        "walkforward_drawdown_review_dir": str(args.walkforward_drawdown_review_dir),
        "timeout_readiness_dir": str(args.timeout_readiness_dir),
        "timeout_artifact_review_dir": str(args.timeout_artifact_review_dir),
        "equity_drawdown_sequence_review_dir": str(args.equity_drawdown_sequence_review_dir),
        "exact_stress_dir": str(args.exact_stress_dir),
        "baseline_r_multiple_consolidated_dir": str(args.baseline_r_multiple_consolidated_dir),
        "review_packet_row_count": len(rows),
        "available_count": counts.get("available", 0),
        "available_with_caveat_count": counts.get("available_with_caveat", 0),
        "missing_count": counts.get("missing", 0),
        "unreadable_count": counts.get("unreadable", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
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
    rows, warnings = build_packet_rows(args)
    write_csv(paths["packet"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build an artifact-only fixed-candidate research review packet. "
            "No validation, backtests, timeout review, diagnostics, or child scripts are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--comparison-table-dir", type=Path, default=DEFAULT_COMPARISON_TABLE_DIR)
    parser.add_argument("--r-multiple-review-dir", type=Path, default=DEFAULT_R_MULTIPLE_REVIEW_DIR)
    parser.add_argument("--walkforward-drawdown-readiness-dir", type=Path, default=DEFAULT_WALKFORWARD_DRAWDOWN_READINESS_DIR)
    parser.add_argument("--walkforward-drawdown-review-dir", type=Path, default=DEFAULT_WALKFORWARD_DRAWDOWN_REVIEW_DIR)
    parser.add_argument("--timeout-readiness-dir", type=Path, default=DEFAULT_TIMEOUT_READINESS_DIR)
    parser.add_argument("--timeout-artifact-review-dir", type=Path, default=DEFAULT_TIMEOUT_ARTIFACT_REVIEW_DIR)
    parser.add_argument("--equity-drawdown-sequence-review-dir", type=Path, default=DEFAULT_EQUITY_DRAWDOWN_SEQUENCE_REVIEW_DIR)
    parser.add_argument("--exact-stress-dir", type=Path, default=DEFAULT_EXACT_STRESS_DIR)
    parser.add_argument("--baseline-r-multiple-consolidated-dir", type=Path, default=DEFAULT_BASELINE_R_MULTIPLE_CONSOLIDATED_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Fixed-candidate research review packet build failed: {exc}")
        return 1
    print("Fixed-candidate research review packet build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
