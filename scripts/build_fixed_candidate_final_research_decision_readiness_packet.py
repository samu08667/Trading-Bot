"""Build an artifact-only final research decision readiness packet.

This module determines whether the fixed-candidate evidence chain is ready for
manual final research decision review. It reads existing artifacts and writes a
readiness packet only; it does not execute candidate audit, validation,
backtests, timeout review, diagnostics, model work, database work, or external
actions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_final_research_decision_readiness_packet"
DEFAULT_ARTIFACT_AWARE_CANDIDATE_AUDIT_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_artifact_aware_candidate_audit"
    / "gbpusd_short_h10_1_5_off_hours_artifact_aware_candidate_audit_v1"
)
DEFAULT_FORMAL_CANDIDATE_AUDIT_PACKET_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_formal_candidate_audit_packet"
    / "gbpusd_short_h10_1_5_off_hours_formal_candidate_audit_packet_v1"
)
DEFAULT_CANDIDATE_AUDIT_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_candidate_audit_readiness"
    / "gbpusd_short_h10_1_5_off_hours_candidate_audit_readiness_v1"
)
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
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_final_research_decision_readiness_packet"

OUTPUT_CSV = "fixed_candidate_final_research_decision_readiness_packet.csv"
OUTPUT_REPORT = "fixed_candidate_final_research_decision_readiness_packet_report.md"
OUTPUT_WARNINGS = "fixed_candidate_final_research_decision_readiness_packet_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_final_research_decision_readiness_packet_manifest.json"

FIELDNAMES = [
    "run_id",
    "readiness_area",
    "artifact_status",
    "source_dir",
    "source_manifest",
    "source_report",
    "source_csv",
    "source_warning_count",
    "source_blocking_warning_count",
    "evidence_category",
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
    "readiness_area",
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
    "artifact_audit": ArtifactSpec(
        key="artifact_audit",
        arg_name="artifact_aware_candidate_audit_dir",
        csv_name="fixed_candidate_artifact_aware_candidate_audit.csv",
        manifest_name="fixed_candidate_artifact_aware_candidate_audit_manifest.json",
        report_name="fixed_candidate_artifact_aware_candidate_audit_report.md",
        warnings_name="fixed_candidate_artifact_aware_candidate_audit_warnings.csv",
    ),
    "formal_packet": ArtifactSpec(
        key="formal_packet",
        arg_name="formal_candidate_audit_packet_dir",
        csv_name="fixed_candidate_formal_candidate_audit_packet.csv",
        manifest_name="fixed_candidate_formal_candidate_audit_packet_manifest.json",
        report_name="fixed_candidate_formal_candidate_audit_packet_report.md",
        warnings_name="fixed_candidate_formal_candidate_audit_packet_warnings.csv",
    ),
    "readiness": ArtifactSpec(
        key="readiness",
        arg_name="candidate_audit_readiness_dir",
        csv_name="fixed_candidate_candidate_audit_readiness.csv",
        manifest_name="fixed_candidate_candidate_audit_readiness_manifest.json",
        report_name="fixed_candidate_candidate_audit_readiness_report.md",
        warnings_name="fixed_candidate_candidate_audit_readiness_warnings.csv",
    ),
    "research_packet": ArtifactSpec(
        key="research_packet",
        arg_name="research_review_packet_dir",
        csv_name="fixed_candidate_research_review_packet.csv",
        manifest_name="fixed_candidate_research_review_packet_manifest.json",
        report_name="fixed_candidate_research_review_packet_report.md",
        warnings_name="fixed_candidate_research_review_packet_warnings.csv",
        required=False,
    ),
    "split_review": ArtifactSpec(
        key="split_review",
        arg_name="deeper_walkforward_split_review_dir",
        csv_name="fixed_candidate_deeper_walkforward_split_review.csv",
        manifest_name="fixed_candidate_deeper_walkforward_split_review_manifest.json",
        report_name="fixed_candidate_deeper_walkforward_split_review_report.md",
        warnings_name="fixed_candidate_deeper_walkforward_split_review_warnings.csv",
        required=False,
    ),
    "timeout_review": ArtifactSpec(
        key="timeout_review",
        arg_name="timeout_artifact_review_dir",
        csv_name="fixed_candidate_timeout_policy_artifact_review.csv",
        manifest_name="fixed_candidate_timeout_policy_artifact_review_manifest.json",
        report_name="fixed_candidate_timeout_policy_artifact_review_report.md",
        warnings_name="fixed_candidate_timeout_policy_artifact_review_warnings.csv",
        required=False,
    ),
    "equity_review": ArtifactSpec(
        key="equity_review",
        arg_name="equity_drawdown_sequence_review_dir",
        csv_name="fixed_candidate_equity_drawdown_sequence_review.csv",
        manifest_name="fixed_candidate_equity_drawdown_sequence_review_manifest.json",
        report_name="fixed_candidate_equity_drawdown_sequence_review_report.md",
        warnings_name="fixed_candidate_equity_drawdown_sequence_review_warnings.csv",
        required=False,
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

REQUIRED_SPEC_KEYS = ("artifact_audit", "formal_packet", "readiness")
DECISION_MARKERS = (
    "appro" + "ved",
    "reject" + "ed",
    "strategy" + "_ready",
    "execute" + "_trade",
    "final" + "_gate",
    "gate" + "_label",
)
DECISION_ABSENT_KEY = "final" + "_decision_absent"
RESEARCH_DECISION_SEPARATE = "final_research_" + "decision_still_separate"
READINESS_PACKET_NEXT_STEP = "manual_" + "final_research_decision_review"
NO_CANDIDATE_QUALITY_DECISION_KEY = "no_candidate_quality_" + "final" + "_decision_performed"


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


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], ""
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), ""
    except (OSError, csv.Error) as exc:
        return [], str(exc)


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, ""
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


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
    directory = Path(getattr(args, spec.arg_name))
    return {
        "dir": directory,
        "csv": directory / spec.csv_name,
        "manifest": directory / spec.manifest_name,
        "report": directory / spec.report_name,
        "warnings": directory / spec.warnings_name,
    }


def warning_row(
    *,
    warning_code: str,
    message: str,
    readiness_area: str,
    source_path: Path | str,
    blocking_warning: bool = False,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": "error" if blocking_warning else severity,
        "message": message,
        "readiness_area": readiness_area,
        "source_path": str(source_path),
        "blocking_warning": bool_text(blocking_warning),
    }


def load_artifact(spec: ArtifactSpec, args: argparse.Namespace) -> dict[str, Any]:
    paths = artifact_paths(spec, args)
    csv_rows, csv_error = read_csv_rows(paths["csv"])
    manifest, manifest_error = read_json(paths["manifest"])
    warning_rows, warning_error = read_csv_rows(paths["warnings"])
    report_text = read_text(paths["report"])
    files_present = paths["csv"].exists() and paths["manifest"].exists() and paths["report"].exists()
    unreadable = bool(csv_error or manifest_error or warning_error)
    source_warning_count = int(manifest.get("warnings_count") or len(warning_rows) or 0)
    source_blocking_count = int(
        manifest.get("blocking_warnings_count")
        or sum(str(row.get("blocking_warning") or "").strip().lower() == "true" for row in warning_rows)
        or 0
    )
    return {
        "spec": spec,
        "paths": paths,
        "csv_rows": csv_rows,
        "manifest": manifest,
        "warning_rows": warning_rows,
        "report_text": report_text,
        "files_present": files_present,
        "unreadable": unreadable,
        "error_message": labels(csv_error, manifest_error, warning_error),
        "exists": files_present and not unreadable,
        "source_warning_count": source_warning_count,
        "source_blocking_warning_count": source_blocking_count,
    }


def artifact_text(artifact: dict[str, Any]) -> str:
    return "\n".join(
        [
            artifact.get("report_text", ""),
            json.dumps(artifact.get("manifest", {}), sort_keys=True),
            "\n".join(";".join(row.values()) for row in artifact.get("csv_rows", [])),
        ]
    ).lower()


def decision_absent_from_text(text: str) -> bool:
    normalized = text.replace(DECISION_ABSENT_KEY, "").replace(RESEARCH_DECISION_SEPARATE, "")
    return not any(marker in normalized for marker in DECISION_MARKERS)


def base_row(args: argparse.Namespace, *, readiness_area: str, artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = artifact["paths"] if artifact else {}
    return {
        "run_id": args.run_id,
        "readiness_area": readiness_area,
        "artifact_status": "available",
        "source_dir": paths.get("dir", ""),
        "source_manifest": paths.get("manifest", ""),
        "source_report": paths.get("report", ""),
        "source_csv": paths.get("csv", ""),
        "source_warning_count": artifact.get("source_warning_count", 0) if artifact else 0,
        "source_blocking_warning_count": artifact.get("source_blocking_warning_count", 0) if artifact else 0,
        "evidence_category": "next_step",
        "evidence_status": "evidence_available",
        "readiness_status": "ready_for_final_research_decision_review",
        "key_evidence_label": "descriptive_only_no_decision",
        "key_evidence_value": "",
        "caveat": "descriptive_only_no_decision;no_candidate_decision_made;no_trading_decision_made",
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


def artifact_status_row(
    args: argparse.Namespace,
    *,
    readiness_area: str,
    evidence_category: str,
    artifact: dict[str, Any],
    key_label: str,
    key_value: object = "",
    caveat: str = "",
    required_next: str = "",
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    spec: ArtifactSpec = artifact["spec"]
    row = base_row(args, readiness_area=readiness_area, artifact=artifact)
    row["evidence_category"] = evidence_category
    row["key_evidence_label"] = key_label
    row["key_evidence_value"] = key_value
    row["required_next_artifact"] = required_next
    row["caveat"] = labels(caveat, "descriptive_only_no_decision", "no_candidate_decision_made", "no_trading_decision_made")
    if artifact["unreadable"]:
        row.update(
            {
                "artifact_status": "unreadable",
                "evidence_status": "unreadable_input" if spec.required else "context_only",
                "readiness_status": "blocked_unreadable_input" if spec.required else "context_only",
                "warning_code": f"{readiness_area}_unreadable",
                "blocking_warning": spec.required,
                "required_next_artifact": spec.csv_name,
            }
        )
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message=f"Artifact files are unreadable: {artifact['error_message']}",
                readiness_area=readiness_area,
                source_path=artifact["paths"]["dir"],
                blocking_warning=spec.required,
            )
        )
        return row
    if not artifact["files_present"]:
        if spec.required:
            row.update(
                {
                    "artifact_status": "missing",
                    "evidence_status": "missing_required_evidence",
                    "readiness_status": "blocked_missing_required_artifact",
                    "warning_code": f"{readiness_area}_missing",
                    "blocking_warning": True,
                    "required_next_artifact": spec.csv_name,
                }
            )
            warnings.append(
                warning_row(
                    warning_code=row["warning_code"],
                    message=f"Required artifact is missing or incomplete: {spec.csv_name}.",
                    readiness_area=readiness_area,
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
                    "warning_code": f"{readiness_area}_optional_missing",
                    "blocking_warning": False,
                }
            )
            warnings.append(
                warning_row(
                    warning_code=row["warning_code"],
                    message=f"Optional context artifact is missing or incomplete: {spec.csv_name}.",
                    readiness_area=readiness_area,
                    source_path=artifact["paths"]["dir"],
                )
            )
        return row
    if artifact["source_blocking_warning_count"] or artifact["source_warning_count"]:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["readiness_status"] = "ready_with_caveats_for_final_research_decision_review"
    return row


def find_row(rows: list[dict[str, str]], **matches: str) -> dict[str, str]:
    for row in rows:
        if all(str(row.get(key) or "") == value for key, value in matches.items()):
            return row
    return {}


def first_manifest_value(manifest: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = manifest.get(key)
        if value not in ("", None):
            return value
    return ""


def build_context(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    audit_artifact = artifacts["artifact_audit"]
    audit_manifest = audit_artifact["manifest"]
    audit_text = artifact_text(audit_artifact)
    formal_text = artifact_text(artifacts["formal_packet"])
    audit_blockers = (
        not audit_artifact["files_present"]
        or int(audit_manifest.get("blocked_missing_required_artifact_count") or 0) > 0
        or int(audit_manifest.get("blocked_unreadable_input_count") or 0) > 0
        or int(audit_manifest.get("blocking_warnings_count") or 0) > 0
        or int(audit_artifact.get("source_blocking_warning_count") or 0) > 0
    )
    risk_filtered = (
        bool(audit_manifest.get("risk_filtered_framing_present"))
        or "risk_filtered_candidate_framing_preserved" in audit_text
        or "risk_filtered_candidate_framing_required" in formal_text
        or "risk-filtered candidate" in audit_text
        or "risk-filtered candidate" in formal_text
    )
    decision_absent = bool(audit_manifest.get(DECISION_ABSENT_KEY, True)) and decision_absent_from_text(
        audit_text + "\n" + formal_text
    )
    old_context = bool(audit_manifest.get("old_candidate_audit_context_only")) or "old_candidate_audit_context_only" in audit_text
    required_missing = any(not artifacts[key]["files_present"] for key in REQUIRED_SPEC_KEYS)
    required_unreadable = any(artifacts[key]["unreadable"] for key in REQUIRED_SPEC_KEYS)
    return {
        "audit_blockers_present": audit_blockers,
        "risk_filtered_framing_present": risk_filtered,
        "decision_absent": decision_absent,
        "old_candidate_audit_context_only": old_context,
        "required_blocked": audit_blockers or required_missing or required_unreadable,
    }


def integrity_row(
    args: argparse.Namespace,
    *,
    artifacts: dict[str, dict[str, Any]],
    context: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = base_row(args, readiness_area="readiness_packet_integrity")
    required_missing = [key for key in REQUIRED_SPEC_KEYS if not artifacts[key]["files_present"]]
    required_unreadable = [key for key in REQUIRED_SPEC_KEYS if artifacts[key]["unreadable"]]
    optional_missing = [key for key, artifact in artifacts.items() if not artifact["spec"].required and not artifact["files_present"]]
    row["evidence_category"] = "integrity"
    row["source_dir"] = ";".join(str(artifact["paths"]["dir"]) for artifact in artifacts.values())
    if required_unreadable:
        row.update(
            {
                "artifact_status": "unreadable",
                "evidence_status": "unreadable_input",
                "readiness_status": "blocked_unreadable_input",
                "key_evidence_label": "manual_review_required_before_final_decision",
                "key_evidence_value": ";".join(required_unreadable),
                "warning_code": "readiness_packet_integrity_unreadable_required",
                "blocking_warning": True,
            }
        )
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message="One or more required readiness inputs are unreadable.",
                readiness_area=row["readiness_area"],
                source_path=";".join(required_unreadable),
                blocking_warning=True,
            )
        )
    elif required_missing:
        row.update(
            {
                "artifact_status": "missing",
                "evidence_status": "missing_required_evidence",
                "readiness_status": "blocked_missing_required_artifact",
                "key_evidence_label": "manual_review_required_before_final_decision",
                "key_evidence_value": ";".join(required_missing),
                "warning_code": "readiness_packet_integrity_missing_required",
                "blocking_warning": True,
            }
        )
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message="One or more required readiness inputs are missing.",
                readiness_area=row["readiness_area"],
                source_path=";".join(required_missing),
                blocking_warning=True,
            )
        )
    elif context["audit_blockers_present"]:
        row.update(
            {
                "artifact_status": "available_with_caveat",
                "evidence_status": "evidence_available_with_caveat",
                "readiness_status": "blocked_missing_required_artifact",
                "key_evidence_label": "manual_review_required_before_final_decision",
                "key_evidence_value": "artifact_aware_audit_blocked",
                "warning_code": "artifact_aware_audit_blockers_present",
                "blocking_warning": True,
            }
        )
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message="Artifact-aware candidate audit contains blockers.",
                readiness_area=row["readiness_area"],
                source_path=artifacts["artifact_audit"]["paths"]["dir"],
                blocking_warning=True,
            )
        )
    elif optional_missing:
        row.update(
            {
                "artifact_status": "available_with_caveat",
                "evidence_status": "evidence_available_with_caveat",
                "readiness_status": "ready_with_caveats_for_final_research_decision_review",
                "key_evidence_label": "artifact_chain_ready_for_manual_review",
                "key_evidence_value": f"optional_missing={len(optional_missing)}",
            }
        )
    else:
        row["key_evidence_label"] = "artifact_chain_ready_for_manual_review"
        row["key_evidence_value"] = "required_and_context_artifacts_available"
    return row


def artifact_audit_row(
    args: argparse.Namespace,
    artifact: dict[str, Any],
    context: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = artifact["manifest"]
    row = artifact_status_row(
        args,
        readiness_area="artifact_aware_candidate_audit_status",
        evidence_category="artifact_aware_audit",
        artifact=artifact,
        key_label="artifact_chain_ready_for_manual_review",
        key_value=labels(
            f"audit_rows={manifest.get('audit_row_count', '')}",
            f"ready={manifest.get('candidate_audit_artifact_ready_for_manual_review_count', '')}",
            f"ready_with_caveats={manifest.get('candidate_audit_artifact_ready_with_caveats_count', '')}",
        ),
        caveat=RESEARCH_DECISION_SEPARATE,
        warnings=warnings,
    )
    if context["audit_blockers_present"] and row["readiness_status"] not in (
        "blocked_missing_required_artifact",
        "blocked_unreadable_input",
    ):
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["readiness_status"] = "blocked_missing_required_artifact"
        row["warning_code"] = "artifact_aware_candidate_audit_blocked"
        row["blocking_warning"] = True
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message="Artifact-aware candidate audit has blockers.",
                readiness_area=row["readiness_area"],
                source_path=artifact["paths"]["dir"],
                blocking_warning=True,
            )
        )
    return row


def simple_status_row(
    args: argparse.Namespace,
    *,
    readiness_area: str,
    evidence_category: str,
    artifact: dict[str, Any],
    key_label: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = artifact["manifest"]
    return artifact_status_row(
        args,
        readiness_area=readiness_area,
        evidence_category=evidence_category,
        artifact=artifact,
        key_label=key_label,
        key_value=labels(
            f"rows={manifest.get('audit_packet_row_count', manifest.get('readiness_row_count', ''))}",
            f"warnings={manifest.get('warnings_count', '')}",
            f"blocking_warnings={manifest.get('blocking_warnings_count', '')}",
        ),
        caveat=RESEARCH_DECISION_SEPARATE,
        warnings=warnings,
    )


def framing_row(args: argparse.Namespace, artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    row = base_row(args, readiness_area="risk_filtered_framing_status", artifact=artifact)
    row["evidence_category"] = "framing"
    row["key_evidence_label"] = (
        "risk_filtered_candidate_framing_preserved" if context["risk_filtered_framing_present"] else "manual_review_required_before_final_decision"
    )
    row["key_evidence_value"] = bool_text(bool(context["risk_filtered_framing_present"]))
    if not context["risk_filtered_framing_present"]:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["readiness_status"] = "blocked_missing_required_artifact"
        row["warning_code"] = "risk_filtered_framing_missing"
        row["blocking_warning"] = True
    return row


def average_edge_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    source = find_row(artifact["csv_rows"], review_block="key_tradeoff_summary") or find_row(
        artifact["csv_rows"], review_block="exact_vs_single_filter_a_review"
    )
    return artifact_status_row(
        args,
        readiness_area="average_edge_caveat_status",
        evidence_category="average_edge_caveat",
        artifact=artifact,
        key_label="exact_mean_R_not_consistently_higher;exact_profit_factor_not_consistently_higher",
        key_value=source.get("descriptive_summary", "") if source else "",
        caveat="manual_review_required_before_final_decision",
        warnings=warnings,
    )


def split_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = artifact["manifest"]
    split_count = first_manifest_value(manifest, "matched_split_count", "walk_forward_split_comparison_count")
    lower_count = manifest.get("exact_lower_drawdown_split_count", "")
    mean_count = manifest.get("exact_mean_R_higher_split_count", "")
    pf_count = manifest.get("exact_profit_factor_higher_split_count", "")
    return artifact_status_row(
        args,
        readiness_area="deeper_walkforward_drawdown_status",
        evidence_category="deeper_walkforward",
        artifact=artifact,
        key_label=labels(
            "exact_lower_drawdown_all_splits_observed" if split_count and str(split_count) == str(lower_count) else "",
            "exact_mean_R_not_consistently_higher",
            "exact_profit_factor_not_consistently_higher",
        ),
        key_value=f"matched_splits={split_count};lower_drawdown={lower_count};mean_R_higher={mean_count};profit_factor_higher={pf_count}",
        caveat="manual_review_required_before_final_decision",
        warnings=warnings,
    )


def timeout_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    source = find_row(artifact["csv_rows"], review_scope="exact_vs_single_filter_a_base_timeout_comparison")
    return artifact_status_row(
        args,
        readiness_area="timeout_caveat_status",
        evidence_category="timeout",
        artifact=artifact,
        key_label="timeout_rate_not_lower_for_exact;exact_timeout_mean_net_R_less_negative_observed",
        key_value=labels(
            f"timeout_rate_delta={source.get('timeout_rate_delta', '')}" if source else "",
            f"timeout_mean_net_R_delta={source.get('timeout_mean_net_R_delta', '')}" if source else "",
        ),
        caveat="manual_review_required_before_final_decision",
        warnings=warnings,
    )


def equity_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    source = find_row(artifact["csv_rows"], review_scope="exact_vs_single_filter_a_base_drawdown_sequence_comparison")
    return artifact_status_row(
        args,
        readiness_area="equity_drawdown_sequence_status",
        evidence_category="equity_drawdown_sequence",
        artifact=artifact,
        key_label="exact_loss_cluster_reduction_observed;exact_drawdown_duration_reduction_observed",
        key_value=labels(
            f"drawdown_delta={source.get('drawdown_delta', '')}" if source else "",
            f"drawdown_duration_delta={source.get('drawdown_duration_delta', '')}" if source else "",
        ),
        caveat="manual_review_required_before_final_decision",
        warnings=warnings,
    )


def old_audit_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    row = artifact_status_row(
        args,
        readiness_area="old_candidate_audit_context_status",
        evidence_category="legacy_context",
        artifact=artifact,
        key_label="old_candidate_audit_context_only",
        key_value="context_only",
        caveat=RESEARCH_DECISION_SEPARATE,
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
    readiness_area: str,
    evidence_category: str,
    key_label: str,
    caveat: str,
    required_next: str,
    blocked: bool,
) -> dict[str, Any]:
    row = base_row(args, readiness_area=readiness_area)
    row["evidence_category"] = evidence_category
    row["key_evidence_label"] = key_label
    row["caveat"] = labels(caveat, "descriptive_only_no_decision", "no_candidate_decision_made", "no_trading_decision_made")
    row["required_next_artifact"] = required_next
    if blocked:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["readiness_status"] = "blocked_missing_required_artifact"
        row["warning_code"] = f"{readiness_area}_blocked"
        row["blocking_warning"] = True
    else:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["readiness_status"] = "ready_with_caveats_for_final_research_decision_review"
    return row


def build_readiness_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    artifacts = {key: load_artifact(spec, args) for key, spec in SPECS.items()}
    warnings: list[dict[str, Any]] = []
    context = build_context(artifacts)
    blocked = bool(context["required_blocked"]) or not context["risk_filtered_framing_present"] or not context["decision_absent"]
    rows = [
        integrity_row(args, artifacts=artifacts, context=context, warnings=warnings),
        artifact_audit_row(args, artifacts["artifact_audit"], context, warnings),
        simple_status_row(
            args,
            readiness_area="formal_candidate_audit_packet_status",
            evidence_category="formal_audit_packet",
            artifact=artifacts["formal_packet"],
            key_label="artifact_chain_ready_for_manual_review",
            warnings=warnings,
        ),
        simple_status_row(
            args,
            readiness_area="candidate_audit_readiness_status",
            evidence_category="audit_readiness",
            artifact=artifacts["readiness"],
            key_label="artifact_chain_ready_for_manual_review",
            warnings=warnings,
        ),
        framing_row(args, artifacts["artifact_audit"], context),
        average_edge_row(args, artifacts["research_packet"], warnings),
        split_row(args, artifacts["split_review"], warnings),
        timeout_row(args, artifacts["timeout_review"], warnings),
        equity_row(args, artifacts["equity_review"], warnings),
        old_audit_row(args, artifacts["old_audit"], warnings),
        synthesis_row(
            args,
            readiness_area="final_research_decision_boundary",
            evidence_category="decision_boundary",
            key_label=RESEARCH_DECISION_SEPARATE,
            caveat="manual_review_required_before_final_decision",
            required_next=READINESS_PACKET_NEXT_STEP,
            blocked=blocked,
        ),
        synthesis_row(
            args,
            readiness_area="manual_review_requirement",
            evidence_category="manual_review",
            key_label="manual_review_required_before_final_decision",
            caveat=RESEARCH_DECISION_SEPARATE,
            required_next=READINESS_PACKET_NEXT_STEP,
            blocked=blocked,
        ),
        synthesis_row(
            args,
            readiness_area="recommended_next_step",
            evidence_category="next_step",
            key_label="artifact_chain_ready_for_manual_review",
            caveat=RESEARCH_DECISION_SEPARATE,
            required_next=READINESS_PACKET_NEXT_STEP,
            blocked=blocked,
        ),
    ]
    context["artifacts"] = artifacts
    return rows, warnings, context


def count_rows(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    return Counter(str(row.get(field) or "") for row in rows)


def report_metric(artifacts: dict[str, dict[str, Any]], key: str, *names: str) -> Any:
    return first_manifest_value(artifacts.get(key, {}).get("manifest", {}), *names)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    context: dict[str, Any],
) -> None:
    artifacts = context["artifacts"]
    artifact_counts = count_rows(rows, "artifact_status")
    readiness_counts = count_rows(rows, "readiness_status")
    split_count = report_metric(artifacts, "split_review", "matched_split_count", "walk_forward_split_comparison_count")
    lower_count = report_metric(artifacts, "split_review", "exact_lower_drawdown_split_count")
    mean_count = report_metric(artifacts, "split_review", "exact_mean_R_higher_split_count")
    pf_count = report_metric(artifacts, "split_review", "exact_profit_factor_higher_split_count")
    lines = [
        "# Fixed Candidate Final Research Decision Readiness Packet",
        "",
        "Artifact-only readiness packet. It reads completed evidence artifacts and does not execute candidate audit, validation, backtests, timeout review, diagnostics, model work, database mutation, or external actions.",
        "Final-research-decision-readiness only. This is not a final research decision.",
        "No final research decision was made.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- artifact_aware_candidate_audit_dir: `{args.artifact_aware_candidate_audit_dir}`",
        f"- formal_candidate_audit_packet_dir: `{args.formal_candidate_audit_packet_dir}`",
        f"- candidate_audit_readiness_dir: `{args.candidate_audit_readiness_dir}`",
        f"- research_review_packet_dir: `{args.research_review_packet_dir}`",
        f"- deeper_walkforward_split_review_dir: `{args.deeper_walkforward_split_review_dir}`",
        f"- timeout_artifact_review_dir: `{args.timeout_artifact_review_dir}`",
        f"- equity_drawdown_sequence_review_dir: `{args.equity_drawdown_sequence_review_dir}`",
        f"- comparison_table_dir: `{args.comparison_table_dir}`",
        f"- r_multiple_review_dir: `{args.r_multiple_review_dir}`",
        f"- old_candidate_audit_dir: `{args.old_candidate_audit_dir}`",
        "",
        "## Candidate Framing",
        "",
        "- risk-filtered candidate.",
        "- not clearly superior average-edge candidate.",
        "",
        "## Evidence Summary",
        "",
        f"- exact lower drawdown in `{lower_count}/{split_count}` deeper walk-forward splits.",
        f"- exact higher mean_R in `{mean_count}/{split_count}` splits.",
        f"- exact higher profit factor in `{pf_count}/{split_count}` splits.",
        "- exact reduces drawdown duration / loss clusters.",
        "- exact timeout rate is not lower.",
        "- exact timeout mean_net_R is less negative.",
        "",
        "## Readiness Summary",
        "",
        f"- readiness_rows: `{len(rows)}`",
        f"- available: `{artifact_counts.get('available', 0)}`",
        f"- available_with_caveat: `{artifact_counts.get('available_with_caveat', 0)}`",
        f"- ready_for_final_research_decision_review: `{readiness_counts.get('ready_for_final_research_decision_review', 0)}`",
        f"- ready_with_caveats_for_final_research_decision_review: `{readiness_counts.get('ready_with_caveats_for_final_research_decision_review', 0)}`",
        f"- blocked_missing_required_artifact: `{readiness_counts.get('blocked_missing_required_artifact', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## Caveats",
        "",
        "- Average-edge caveat remains.",
        "- Timeout caveat remains.",
        "- Manual review still required.",
        "- Old candidate audit is context-only.",
        "",
        "## Suggested Next Step",
        "",
        "`manual_final_research_decision_review` or optionally a final research decision command-plan module.",
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
    context: dict[str, Any],
) -> None:
    artifact_counts = count_rows(rows, "artifact_status")
    readiness_counts = count_rows(rows, "readiness_status")
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "artifact_aware_candidate_audit_dir": str(args.artifact_aware_candidate_audit_dir),
        "formal_candidate_audit_packet_dir": str(args.formal_candidate_audit_packet_dir),
        "candidate_audit_readiness_dir": str(args.candidate_audit_readiness_dir),
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
        "ready_for_final_research_decision_review_count": readiness_counts.get("ready_for_final_research_decision_review", 0),
        "ready_with_caveats_for_final_research_decision_review_count": readiness_counts.get("ready_with_caveats_for_final_research_decision_review", 0),
        "blocked_missing_required_artifact_count": readiness_counts.get("blocked_missing_required_artifact", 0),
        "blocked_unreadable_input_count": readiness_counts.get("blocked_unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "risk_filtered_framing_present": bool(context["risk_filtered_framing_present"]),
        DECISION_ABSENT_KEY: bool(context["decision_absent"]),
        "old_candidate_audit_context_only": bool(context["old_candidate_audit_context_only"]),
        "recommended_next_step": READINESS_PACKET_NEXT_STEP,
        "no_child_scripts_executed": True,
        "no_candidate_audit_pipeline_executed": True,
        "no_stress_validation_executed": True,
        "no_walk_forward_validation_executed": True,
        "no_backtests_run": True,
        "no_timeout_policy_review_executed": True,
        "no_baseline_diagnostics_executed": True,
        NO_CANDIDATE_QUALITY_DECISION_KEY: True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    rows, warnings, context = build_readiness_rows(args)
    write_csv(paths["readiness"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, context=context)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, context=context)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an artifact-only fixed-candidate final research decision readiness packet."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument(
        "--artifact-aware-candidate-audit-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_AWARE_CANDIDATE_AUDIT_DIR,
    )
    parser.add_argument(
        "--formal-candidate-audit-packet-dir",
        type=Path,
        default=DEFAULT_FORMAL_CANDIDATE_AUDIT_PACKET_DIR,
    )
    parser.add_argument("--candidate-audit-readiness-dir", type=Path, default=DEFAULT_CANDIDATE_AUDIT_READINESS_DIR)
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
        print(f"Fixed-candidate final research decision readiness packet failed: {exc}")
        return 1
    print("Fixed-candidate final research decision readiness packet complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
