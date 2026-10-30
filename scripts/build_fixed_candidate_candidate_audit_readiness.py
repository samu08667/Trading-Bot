"""Build an artifact-only candidate-audit readiness review for one fixed candidate.

This module reads completed fixed-candidate evidence artifacts and summarizes
whether the artifact chain is ready for candidate-audit planning. It does not
run candidate audit, validation, backtests, timeout review, diagnostics, model
work, database work, or external actions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_candidate_audit_readiness"
DEFAULT_RESEARCH_REVIEW_PACKET_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_research_review_packet"
    / "gbpusd_short_h10_1_5_off_hours_research_review_packet_v1"
)
DEFAULT_DEEPER_WALKFORWARD_SPLIT_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_deeper_walkforward_split_review"
    / "gbpusd_short_h10_1_5_off_hours_deeper_walkforward_split_review_v1"
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
DEFAULT_OLD_CANDIDATE_AUDIT_DIR = (
    BASE_DIR
    / "reports"
    / "candidate_audit_pipeline"
    / "gbpusd_short_h10_1_5_off_hours_candidate_audit_exec_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_candidate_audit_readiness"

OUTPUT_CSV = "fixed_candidate_candidate_audit_readiness.csv"
OUTPUT_REPORT = "fixed_candidate_candidate_audit_readiness_report.md"
OUTPUT_WARNINGS = "fixed_candidate_candidate_audit_readiness_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_candidate_audit_readiness_manifest.json"

FIELDNAMES = [
    "run_id",
    "readiness_block",
    "artifact_status",
    "source_dir",
    "source_manifest",
    "source_report",
    "source_csv",
    "source_warning_count",
    "source_blocking_warning_count",
    "evidence_status",
    "readiness_status",
    "key_evidence_label",
    "key_evidence_value",
    "caveat",
    "required_next_artifact",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "readiness_block",
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
    "research_packet": ArtifactSpec(
        key="research_packet",
        arg_name="research_review_packet_dir",
        csv_name="fixed_candidate_research_review_packet.csv",
        manifest_name="fixed_candidate_research_review_packet_manifest.json",
        report_name="fixed_candidate_research_review_packet_report.md",
        warnings_name="fixed_candidate_research_review_packet_warnings.csv",
    ),
    "split_review": ArtifactSpec(
        key="split_review",
        arg_name="deeper_walkforward_split_review_dir",
        csv_name="fixed_candidate_deeper_walkforward_split_review.csv",
        manifest_name="fixed_candidate_deeper_walkforward_split_review_manifest.json",
        report_name="fixed_candidate_deeper_walkforward_split_review_report.md",
        warnings_name="fixed_candidate_deeper_walkforward_split_review_warnings.csv",
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
    "comparison": ArtifactSpec(
        key="comparison",
        arg_name="comparison_table_dir",
        csv_name="fixed_candidate_baseline_comparison_table.csv",
        manifest_name="fixed_candidate_baseline_comparison_manifest.json",
        report_name="fixed_candidate_baseline_comparison_report.md",
        warnings_name="fixed_candidate_baseline_comparison_warnings.csv",
        required=False,
    ),
    "r_review": ArtifactSpec(
        key="r_review",
        arg_name="r_multiple_review_dir",
        csv_name="fixed_candidate_r_multiple_baseline_review.csv",
        manifest_name="fixed_candidate_r_multiple_baseline_review_manifest.json",
        report_name="fixed_candidate_r_multiple_baseline_review_report.md",
        warnings_name="fixed_candidate_r_multiple_baseline_review_warnings.csv",
        required=False,
    ),
    "old_audit": ArtifactSpec(
        key="old_audit",
        arg_name="old_candidate_audit_dir",
        csv_name="candidate_audit_pipeline_summary.csv",
        manifest_name="candidate_audit_manifest.json",
        report_name="candidate_audit_pipeline_report.md",
        warnings_name="candidate_audit_pipeline_warnings.csv",
        required=False,
    ),
}

REQUIRED_SPEC_KEYS = ("research_packet", "split_review", "timeout_review", "equity_review")


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


def labels(*values: str) -> str:
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


def artifact_paths(spec: ArtifactSpec, args: argparse.Namespace) -> dict[str, Path]:
    source_dir = Path(getattr(args, spec.arg_name))
    return {
        "dir": source_dir,
        "csv": source_dir / spec.csv_name,
        "manifest": source_dir / spec.manifest_name,
        "report": source_dir / spec.report_name,
        "warnings": source_dir / spec.warnings_name,
    }


def warning_row(
    *,
    warning_code: str,
    message: str,
    readiness_block: str,
    source_path: Path | str,
    blocking_warning: bool = False,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": "error" if blocking_warning else severity,
        "message": message,
        "readiness_block": readiness_block,
        "source_path": str(source_path),
        "blocking_warning": bool_text(blocking_warning),
    }


def load_artifact(spec: ArtifactSpec, args: argparse.Namespace) -> dict[str, Any]:
    paths = artifact_paths(spec, args)
    exists = paths["csv"].exists() and paths["manifest"].exists() and paths["report"].exists()
    warnings_rows = read_csv_rows(paths["warnings"])
    warning_count = len(warnings_rows)
    blocking_count = sum(
        str(row.get("blocking_warning") or row.get("blocking") or "").strip().lower() == "true"
        for row in warnings_rows
    )
    return {
        "spec": spec,
        "paths": paths,
        "exists": exists,
        "csv_rows": read_csv_rows(paths["csv"]) if paths["csv"].exists() else [],
        "manifest": read_json(paths["manifest"]) if paths["manifest"].exists() else {},
        "source_warning_count": warning_count,
        "source_blocking_warning_count": blocking_count,
    }


def base_row(
    args: argparse.Namespace,
    *,
    readiness_block: str,
    artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths = artifact["paths"] if artifact else {}
    return {
        "run_id": args.run_id,
        "readiness_block": readiness_block,
        "artifact_status": "available",
        "source_dir": paths.get("dir", ""),
        "source_manifest": paths.get("manifest", ""),
        "source_report": paths.get("report", ""),
        "source_csv": paths.get("csv", ""),
        "source_warning_count": artifact.get("source_warning_count", 0) if artifact else 0,
        "source_blocking_warning_count": artifact.get("source_blocking_warning_count", 0) if artifact else 0,
        "evidence_status": "descriptive_evidence_available",
        "readiness_status": "ready_for_candidate_audit_planning",
        "key_evidence_label": "descriptive_only_no_decision",
        "key_evidence_value": "",
        "caveat": "descriptive_only_no_decision;no_strategy_decision_made",
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


def artifact_status_row(
    args: argparse.Namespace,
    *,
    readiness_block: str,
    artifact: dict[str, Any],
    key_label: str,
    key_value: object = "",
    caveat: str = "",
    required_next: str = "",
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    spec: ArtifactSpec = artifact["spec"]
    row = base_row(args, readiness_block=readiness_block, artifact=artifact)
    row["key_evidence_label"] = key_label
    row["key_evidence_value"] = key_value
    row["required_next_artifact"] = required_next
    row["caveat"] = labels(caveat, "descriptive_only_no_decision", "no_strategy_decision_made")
    if not artifact["exists"]:
        if spec.required:
            row.update(
                {
                    "artifact_status": "missing",
                    "evidence_status": "missing_required_evidence",
                    "readiness_status": "blocked_missing_required_artifact",
                    "warning_code": f"{readiness_block}_missing",
                    "blocking_warning": True,
                    "required_next_artifact": spec.csv_name,
                }
            )
            warnings.append(
                warning_row(
                    warning_code=f"{readiness_block}_missing",
                    message=f"Required evidence artifact is missing or incomplete: {spec.csv_name}.",
                    readiness_block=readiness_block,
                    source_path=artifact["paths"]["dir"],
                    blocking_warning=True,
                )
            )
        else:
            row.update(
                {
                    "artifact_status": "optional_missing",
                    "evidence_status": "context_only",
                    "readiness_status": "context_only",
                    "warning_code": f"{readiness_block}_optional_missing",
                    "blocking_warning": False,
                }
            )
            warnings.append(
                warning_row(
                    warning_code=f"{readiness_block}_optional_missing",
                    message=f"Optional context artifact is missing or incomplete: {spec.csv_name}.",
                    readiness_block=readiness_block,
                    source_path=artifact["paths"]["dir"],
                )
            )
        return row

    if artifact.get("source_blocking_warning_count", 0):
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "descriptive_evidence_available_with_caveat"
        row["readiness_status"] = "ready_with_caveat_for_candidate_audit_planning"
    return row


def find_row(rows: list[dict[str, str]], **matches: str) -> dict[str, str]:
    for row in rows:
        if all(str(row.get(key) or "") == value for key, value in matches.items()):
            return row
    return {}


def artifact_chain_row(
    args: argparse.Namespace,
    *,
    artifacts: dict[str, dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = base_row(args, readiness_block="artifact_chain_integrity")
    missing_required = [key for key in REQUIRED_SPEC_KEYS if not artifacts[key]["exists"]]
    missing_optional = [key for key in ("comparison", "r_review", "old_audit") if not artifacts[key]["exists"]]
    if missing_required:
        row.update(
            {
                "artifact_status": "missing",
                "evidence_status": "missing_required_evidence",
                "readiness_status": "blocked_missing_required_artifact",
                "key_evidence_label": "required_artifact_missing",
                "key_evidence_value": ";".join(missing_required),
                "caveat": "formal_candidate_audit_still_separate;descriptive_only_no_decision;no_strategy_decision_made",
                "required_next_artifact": "complete_required_readiness_artifacts",
                "warning_code": "artifact_chain_required_missing",
                "blocking_warning": True,
            }
        )
        warnings.append(
            warning_row(
                warning_code="artifact_chain_required_missing",
                message="One or more required readiness inputs are missing.",
                readiness_block="artifact_chain_integrity",
                source_path=";".join(missing_required),
                blocking_warning=True,
            )
        )
    elif missing_optional:
        row.update(
            {
                "artifact_status": "available_with_caveat",
                "evidence_status": "descriptive_evidence_available_with_caveat",
                "readiness_status": "ready_with_caveat_for_candidate_audit_planning",
                "key_evidence_label": "optional_context_missing",
                "key_evidence_value": ";".join(missing_optional),
                "caveat": "formal_candidate_audit_still_separate;descriptive_only_no_decision;no_strategy_decision_made",
            }
        )
    else:
        row["key_evidence_label"] = "candidate_audit_command_plan_recommended"
        row["key_evidence_value"] = "required_and_context_artifacts_available"
        row["caveat"] = "formal_candidate_audit_still_separate;descriptive_only_no_decision;no_strategy_decision_made"
    return row


def comparison_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = artifact.get("manifest", {})
    namespaces = manifest.get("metric_namespaces", [])
    same_namespace = namespaces == ["R_multiple"] or namespaces == "R_multiple"
    label = "same_namespace_r_multiple_available" if same_namespace else "descriptive_only_no_decision"
    value = ";".join(namespaces) if isinstance(namespaces, list) else namespaces
    return artifact_status_row(
        args,
        readiness_block="r_multiple_comparison_readiness",
        artifact=artifact,
        key_label=label,
        key_value=value,
        caveat="formal_candidate_audit_still_separate",
        warnings=warnings,
    )


def ablation_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    source = find_row(artifact.get("csv_rows", []), review_block="exact_vs_single_filter_a_review")
    evidence = labels(
        "exact_mean_R_not_consistently_higher",
        "exact_profit_factor_not_consistently_higher",
        "descriptive_only_no_decision",
    )
    value_parts = [
        f"delta_mean_R={source.get('key_metric_2_value', '')}" if source else "",
        f"delta_max_drawdown_R={source.get('key_metric_3_value', '')}" if source else "",
    ]
    return artifact_status_row(
        args,
        readiness_block="exact_vs_single_filter_a_ablation_readiness",
        artifact=artifact,
        key_label=evidence,
        key_value=labels(*value_parts),
        caveat="formal_candidate_audit_still_separate",
        warnings=warnings,
    )


def split_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = artifact.get("manifest", {})
    split_count = manifest.get("walk_forward_split_comparison_count", "")
    lower_count = manifest.get("exact_lower_drawdown_split_count", "")
    mean_count = manifest.get("exact_mean_R_higher_split_count", "")
    pf_count = manifest.get("exact_profit_factor_higher_split_count", "")
    label = labels(
        "exact_lower_drawdown_all_splits_observed"
        if split_count and str(split_count) == str(lower_count)
        else "",
        "exact_mean_R_not_consistently_higher",
        "exact_profit_factor_not_consistently_higher",
    )
    return artifact_status_row(
        args,
        readiness_block="deeper_walkforward_split_readiness",
        artifact=artifact,
        key_label=label,
        key_value=f"splits={split_count};lower_drawdown={lower_count};mean_R_higher={mean_count};pf_higher={pf_count}",
        caveat="formal_candidate_audit_still_separate",
        warnings=warnings,
    )


def timeout_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    source = find_row(artifact.get("csv_rows", []), review_scope="exact_vs_single_filter_a_base_timeout_comparison")
    return artifact_status_row(
        args,
        readiness_block="timeout_artifact_readiness",
        artifact=artifact,
        key_label="timeout_rate_not_lower_for_exact;exact_timeout_mean_net_R_less_negative_observed",
        key_value=labels(
            f"timeout_rate_delta={source.get('timeout_rate_delta', '')}" if source else "",
            f"timeout_mean_net_R_delta={source.get('timeout_mean_net_R_delta', '')}" if source else "",
        ),
        caveat="formal_candidate_audit_still_separate",
        warnings=warnings,
    )


def equity_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    source = find_row(
        artifact.get("csv_rows", []),
        review_scope="exact_vs_single_filter_a_base_drawdown_sequence_comparison",
    )
    return artifact_status_row(
        args,
        readiness_block="equity_drawdown_sequence_readiness",
        artifact=artifact,
        key_label="exact_loss_cluster_reduction_observed",
        key_value=labels(
            f"drawdown_delta={source.get('drawdown_delta', '')}" if source else "",
            f"drawdown_duration_delta={source.get('drawdown_duration_delta', '')}" if source else "",
            f"longest_negative_streak_delta={source.get('longest_negative_streak_delta', '')}" if source else "",
        ),
        caveat="formal_candidate_audit_still_separate",
        warnings=warnings,
    )


def old_audit_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    row = artifact_status_row(
        args,
        readiness_block="old_candidate_audit_context",
        artifact=artifact,
        key_label="old_candidate_audit_does_not_consume_new_chain",
        key_value="context_only",
        caveat="old_candidate_audit_does_not_consume_new_chain;formal_candidate_audit_still_separate",
        warnings=warnings,
    )
    row["evidence_status"] = "context_only"
    row["readiness_status"] = "context_only"
    if row["artifact_status"] == "available":
        row["artifact_status"] = "available_with_caveat"
    return row


def synthesis_row(
    args: argparse.Namespace,
    *,
    readiness_block: str,
    key_label: str,
    caveat: str,
    required_next_artifact: str,
    blocked: bool,
) -> dict[str, Any]:
    row = base_row(args, readiness_block=readiness_block)
    row["key_evidence_label"] = key_label
    row["caveat"] = labels(caveat, "descriptive_only_no_decision", "no_strategy_decision_made")
    row["required_next_artifact"] = required_next_artifact
    if blocked:
        row["artifact_status"] = "missing"
        row["evidence_status"] = "missing_required_evidence"
        row["readiness_status"] = "blocked_missing_required_artifact"
        row["warning_code"] = f"{readiness_block}_blocked"
        row["blocking_warning"] = True
    else:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "descriptive_evidence_available_with_caveat"
        row["readiness_status"] = "ready_with_caveat_for_candidate_audit_planning"
    return row


def build_readiness_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    artifacts = {key: load_artifact(spec, args) for key, spec in SPECS.items()}
    warnings: list[dict[str, Any]] = []
    required_blocked = any(not artifacts[key]["exists"] for key in REQUIRED_SPEC_KEYS)
    rows = [
        artifact_chain_row(args, artifacts=artifacts, warnings=warnings),
        comparison_row(args, artifacts["comparison"], warnings),
        ablation_row(args, artifacts["research_packet"], warnings),
        split_row(args, artifacts["split_review"], warnings),
        timeout_row(args, artifacts["timeout_review"], warnings),
        equity_row(args, artifacts["equity_review"], warnings),
        old_audit_row(args, artifacts["old_audit"], warnings),
        synthesis_row(
            args,
            readiness_block="candidate_audit_planning_readiness",
            key_label="candidate_audit_command_plan_recommended",
            caveat="formal_candidate_audit_still_separate",
            required_next_artifact="build_fixed_candidate_candidate_audit_command_plan.py",
            blocked=required_blocked,
        ),
        synthesis_row(
            args,
            readiness_block="remaining_caveats",
            key_label=labels(
                "exact_mean_R_not_consistently_higher",
                "exact_profit_factor_not_consistently_higher",
                "timeout_rate_not_lower_for_exact",
                "formal_candidate_audit_still_separate",
            ),
            caveat="formal_candidate_audit_still_separate",
            required_next_artifact="candidate_audit_command_plan_artifact",
            blocked=required_blocked,
        ),
        synthesis_row(
            args,
            readiness_block="recommended_next_artifact",
            key_label="candidate_audit_command_plan_recommended",
            caveat="formal_candidate_audit_still_separate",
            required_next_artifact="build_fixed_candidate_candidate_audit_command_plan.py",
            blocked=required_blocked,
        ),
    ]
    return rows, warnings, artifacts


def status_counts(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    return Counter(str(row.get(field) or "") for row in rows)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    readiness_counts = status_counts(rows, "readiness_status")
    artifact_counts = status_counts(rows, "artifact_status")
    lines = [
        "# Fixed Candidate Candidate-Audit Readiness",
        "",
        "Artifact-only candidate-audit readiness review. It reads completed evidence artifacts and does not execute candidate audit, validation, backtests, timeout review, diagnostics, model work, database mutation, or external actions.",
        "No candidate-quality conclusion or trading decision was made.",
        "",
        "## Evidence Chain",
        "",
        f"- research_review_packet_dir: `{args.research_review_packet_dir}`",
        f"- deeper_walkforward_split_review_dir: `{args.deeper_walkforward_split_review_dir}`",
        f"- timeout_artifact_review_dir: `{args.timeout_artifact_review_dir}`",
        f"- equity_drawdown_sequence_review_dir: `{args.equity_drawdown_sequence_review_dir}`",
        f"- comparison_table_dir: `{args.comparison_table_dir}`",
        f"- r_multiple_review_dir: `{args.r_multiple_review_dir}`",
        f"- old_candidate_audit_dir: `{args.old_candidate_audit_dir}`",
        "",
        "## Readiness Summary",
        "",
        f"- rows: `{len(rows)}`",
        f"- available: `{artifact_counts.get('available', 0)}`",
        f"- available_with_caveat: `{artifact_counts.get('available_with_caveat', 0)}`",
        f"- optional_missing: `{artifact_counts.get('optional_missing', 0)}`",
        f"- ready_with_caveat_for_candidate_audit_planning: `{readiness_counts.get('ready_with_caveat_for_candidate_audit_planning', 0)}`",
        f"- blocked_missing_required_artifact: `{readiness_counts.get('blocked_missing_required_artifact', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## Old Candidate Audit Context",
        "",
        "The old candidate audit is context-only here because it does not consume the newer fixed-candidate evidence chain.",
        "",
        "## Caveats",
        "",
        "- exact_rule is risk-filtered evidence and does not clearly improve average edge metrics versus single_filter_a.",
        "- timeout_rate is not lower for exact_rule in the reviewed artifacts.",
        "- formal candidate audit is still separate.",
        "",
        "## Recommended Next Artifact",
        "",
        "`build_fixed_candidate_candidate_audit_command_plan.py`",
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
    artifact_counts = status_counts(rows, "artifact_status")
    readiness_counts = status_counts(rows, "readiness_status")
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "research_review_packet_dir": str(args.research_review_packet_dir),
        "deeper_walkforward_split_review_dir": str(args.deeper_walkforward_split_review_dir),
        "timeout_artifact_review_dir": str(args.timeout_artifact_review_dir),
        "equity_drawdown_sequence_review_dir": str(args.equity_drawdown_sequence_review_dir),
        "comparison_table_dir": str(args.comparison_table_dir),
        "r_multiple_review_dir": str(args.r_multiple_review_dir),
        "old_candidate_audit_dir": str(args.old_candidate_audit_dir),
        "readiness_row_count": len(rows),
        "available_count": artifact_counts.get("available", 0),
        "available_with_caveat_count": artifact_counts.get("available_with_caveat", 0),
        "missing_count": artifact_counts.get("missing", 0),
        "unreadable_count": artifact_counts.get("unreadable", 0),
        "optional_missing_count": artifact_counts.get("optional_missing", 0),
        "ready_for_candidate_audit_planning_count": readiness_counts.get(
            "ready_for_candidate_audit_planning", 0
        ),
        "ready_with_caveat_for_candidate_audit_planning_count": readiness_counts.get(
            "ready_with_caveat_for_candidate_audit_planning", 0
        ),
        "blocked_missing_required_artifact_count": readiness_counts.get("blocked_missing_required_artifact", 0),
        "blocked_unreadable_input_count": readiness_counts.get("blocked_unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "no_child_scripts_executed": True,
        "no_candidate_audit_executed": True,
        "no_stress_validation_executed": True,
        "no_walk_forward_validation_executed": True,
        "no_backtests_run": True,
        "no_timeout_policy_review_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    rows, warnings, _artifacts = build_readiness_rows(args)
    write_csv(paths["readiness"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an artifact-only fixed-candidate candidate-audit readiness review."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--research-review-packet-dir", type=Path, default=DEFAULT_RESEARCH_REVIEW_PACKET_DIR)
    parser.add_argument(
        "--deeper-walkforward-split-review-dir",
        type=Path,
        default=DEFAULT_DEEPER_WALKFORWARD_SPLIT_REVIEW_DIR,
    )
    parser.add_argument("--timeout-artifact-review-dir", type=Path, default=DEFAULT_TIMEOUT_ARTIFACT_REVIEW_DIR)
    parser.add_argument(
        "--equity-drawdown-sequence-review-dir",
        type=Path,
        default=DEFAULT_EQUITY_DRAWDOWN_SEQUENCE_REVIEW_DIR,
    )
    parser.add_argument("--comparison-table-dir", type=Path, default=DEFAULT_COMPARISON_TABLE_DIR)
    parser.add_argument("--r-multiple-review-dir", type=Path, default=DEFAULT_R_MULTIPLE_REVIEW_DIR)
    parser.add_argument("--old-candidate-audit-dir", type=Path, default=DEFAULT_OLD_CANDIDATE_AUDIT_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Fixed-candidate candidate-audit readiness failed: {exc}")
        return 1
    print("Fixed-candidate candidate-audit readiness complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
