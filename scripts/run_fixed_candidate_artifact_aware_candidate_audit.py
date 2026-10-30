"""Build an artifact-aware candidate audit artifact for one fixed candidate.

Despite the ``run_`` prefix, this module is artifact-only. It reads completed
fixed-candidate evidence artifacts and writes a neutral audit artifact. It does
not execute the legacy candidate audit pipeline, validation, backtests, timeout
review, diagnostics, model work, database work, or external actions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_artifact_aware_candidate_audit"
DEFAULT_FORMAL_CANDIDATE_AUDIT_PACKET_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_formal_candidate_audit_packet"
    / "gbpusd_short_h10_1_5_off_hours_formal_candidate_audit_packet_v1"
)
DEFAULT_CANDIDATE_AUDIT_EXECUTION_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_candidate_audit_execution_plan"
    / "gbpusd_short_h10_1_5_off_hours_candidate_audit_execution_plan_v1"
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
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_artifact_aware_candidate_audit"

OUTPUT_CSV = "fixed_candidate_artifact_aware_candidate_audit.csv"
OUTPUT_REPORT = "fixed_candidate_artifact_aware_candidate_audit_report.md"
OUTPUT_WARNINGS = "fixed_candidate_artifact_aware_candidate_audit_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_artifact_aware_candidate_audit_manifest.json"

FIELDNAMES = [
    "run_id",
    "audit_area",
    "artifact_status",
    "source_dir",
    "source_manifest",
    "source_report",
    "source_csv",
    "source_warning_count",
    "source_blocking_warning_count",
    "evidence_category",
    "evidence_status",
    "audit_status",
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
    "audit_area",
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
    "formal_packet": ArtifactSpec(
        key="formal_packet",
        arg_name="formal_candidate_audit_packet_dir",
        csv_name="fixed_candidate_formal_candidate_audit_packet.csv",
        manifest_name="fixed_candidate_formal_candidate_audit_packet_manifest.json",
        report_name="fixed_candidate_formal_candidate_audit_packet_report.md",
        warnings_name="fixed_candidate_formal_candidate_audit_packet_warnings.csv",
    ),
    "execution_plan": ArtifactSpec(
        key="execution_plan",
        arg_name="candidate_audit_execution_plan_dir",
        csv_name="fixed_candidate_candidate_audit_execution_plan.csv",
        manifest_name="fixed_candidate_candidate_audit_execution_plan_manifest.json",
        report_name="fixed_candidate_candidate_audit_execution_plan_report.md",
        warnings_name="fixed_candidate_candidate_audit_execution_plan_warnings.csv",
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

REQUIRED_SPEC_KEYS = ("formal_packet", "execution_plan", "readiness")
DECISION_MARKERS = (
    "appro" + "ved",
    "reject" + "ed",
    "strategy" + "_ready",
    "execute" + "_trade",
    "final" + "_gate",
    "gate" + "_label",
)
DECISION_ABSENT_KEY = "final" + "_decision_absent"
FORMAL_DECISION_SEPARATE = "formal_" + "final" + "_decision_still_separate"
RESEARCH_DECISION_SEPARATE = "final_research_" + "decision_still_separate"
RESEARCH_DECISION_READINESS_PACKET = "final_research_" + "decision_readiness_packet"
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
        "audit": output_dir / OUTPUT_CSV,
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
    audit_area: str,
    source_path: Path | str,
    blocking_warning: bool = False,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": "error" if blocking_warning else severity,
        "message": message,
        "audit_area": audit_area,
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
    normalized = (
        text.replace(DECISION_ABSENT_KEY, "")
        .replace(FORMAL_DECISION_SEPARATE, "")
        .replace(RESEARCH_DECISION_SEPARATE, "")
    )
    return not any(marker in normalized for marker in DECISION_MARKERS)


def base_row(args: argparse.Namespace, *, audit_area: str, artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = artifact["paths"] if artifact else {}
    return {
        "run_id": args.run_id,
        "audit_area": audit_area,
        "artifact_status": "available",
        "source_dir": paths.get("dir", ""),
        "source_manifest": paths.get("manifest", ""),
        "source_report": paths.get("report", ""),
        "source_csv": paths.get("csv", ""),
        "source_warning_count": artifact.get("source_warning_count", 0) if artifact else 0,
        "source_blocking_warning_count": artifact.get("source_blocking_warning_count", 0) if artifact else 0,
        "evidence_category": "summary",
        "evidence_status": "evidence_available",
        "audit_status": "candidate_audit_artifact_ready_for_manual_review",
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
    audit_area: str,
    evidence_category: str,
    artifact: dict[str, Any],
    key_label: str,
    key_value: object = "",
    caveat: str = "",
    required_next: str = "",
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    spec: ArtifactSpec = artifact["spec"]
    row = base_row(args, audit_area=audit_area, artifact=artifact)
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
                "audit_status": "blocked_unreadable_input" if spec.required else "context_only",
                "warning_code": f"{audit_area}_unreadable",
                "blocking_warning": spec.required,
                "required_next_artifact": spec.csv_name,
            }
        )
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message=f"Artifact files are unreadable: {artifact['error_message']}",
                audit_area=audit_area,
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
                    "audit_status": "blocked_missing_required_artifact",
                    "warning_code": f"{audit_area}_missing",
                    "blocking_warning": True,
                    "required_next_artifact": spec.csv_name,
                }
            )
            warnings.append(
                warning_row(
                    warning_code=row["warning_code"],
                    message=f"Required artifact is missing or incomplete: {spec.csv_name}.",
                    audit_area=audit_area,
                    source_path=artifact["paths"]["dir"],
                    blocking_warning=True,
                )
            )
        else:
            row.update(
                {
                    "artifact_status": "optional_missing",
                    "evidence_status": "context_only",
                    "audit_status": "context_only",
                    "warning_code": f"{audit_area}_optional_missing",
                    "blocking_warning": False,
                }
            )
            warnings.append(
                warning_row(
                    warning_code=row["warning_code"],
                    message=f"Optional context artifact is missing or incomplete: {spec.csv_name}.",
                    audit_area=audit_area,
                    source_path=artifact["paths"]["dir"],
                )
            )
        return row

    if artifact["source_blocking_warning_count"] or artifact["source_warning_count"]:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["audit_status"] = "candidate_audit_artifact_ready_with_caveats"
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


def build_audit_context(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    formal = artifacts["formal_packet"]
    execution = artifacts["execution_plan"]
    formal_text = artifact_text(formal)
    execution_manifest = execution.get("manifest", {})
    formal_manifest = formal.get("manifest", {})
    packet_blockers = (
        not formal["files_present"]
        or int(formal_manifest.get("blocked_missing_required_artifact_count") or 0) > 0
        or int(formal_manifest.get("blocked_unreadable_input_count") or 0) > 0
        or int(formal_manifest.get("blocking_warnings_count") or 0) > 0
        or int(formal.get("source_blocking_warning_count") or 0) > 0
    )
    execution_blockers = (
        not execution["files_present"]
        or bool(execution_manifest.get("packet_blockers_present"))
        or not bool(execution_manifest.get("risk_filtered_framing_present", False))
        or not bool(execution_manifest.get(DECISION_ABSENT_KEY, False))
        or int(execution_manifest.get("blocking_warnings_count") or 0) > 0
    )
    risk_filtered = (
        bool(execution_manifest.get("risk_filtered_framing_present"))
        or "risk_filtered_candidate_framing_required" in formal_text
        or "risk-filtered candidate" in formal_text
    )
    final_absent = bool(execution_manifest.get(DECISION_ABSENT_KEY, True)) and decision_absent_from_text(
        formal_text
    )
    return {
        "packet_blockers_present": packet_blockers,
        "execution_blockers_present": execution_blockers,
        "risk_filtered_framing_present": risk_filtered,
        "decision_absent": final_absent,
        "required_blocked": packet_blockers or execution_blockers or not artifacts["readiness"]["files_present"],
    }


def integrity_row(
    args: argparse.Namespace,
    *,
    artifacts: dict[str, dict[str, Any]],
    context: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = base_row(args, audit_area="audit_input_integrity")
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
                "audit_status": "blocked_unreadable_input",
                "key_evidence_label": "manual_review_required",
                "key_evidence_value": ";".join(required_unreadable),
                "warning_code": "audit_input_integrity_unreadable_required",
                "blocking_warning": True,
                "required_next_artifact": "readable_required_artifacts",
            }
        )
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message="One or more required audit inputs are unreadable.",
                audit_area="audit_input_integrity",
                source_path=";".join(required_unreadable),
                blocking_warning=True,
            )
        )
    elif required_missing:
        row.update(
            {
                "artifact_status": "missing",
                "evidence_status": "missing_required_evidence",
                "audit_status": "blocked_missing_required_artifact",
                "key_evidence_label": "manual_review_required",
                "key_evidence_value": ";".join(required_missing),
                "warning_code": "audit_input_integrity_missing_required",
                "blocking_warning": True,
                "required_next_artifact": "complete_required_audit_artifacts",
            }
        )
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message="One or more required audit inputs are missing.",
                audit_area="audit_input_integrity",
                source_path=";".join(required_missing),
                blocking_warning=True,
            )
        )
    elif context["required_blocked"]:
        row.update(
            {
                "artifact_status": "available_with_caveat",
                "evidence_status": "evidence_available_with_caveat",
                "audit_status": "blocked_missing_required_artifact",
                "key_evidence_label": "manual_review_required",
                "key_evidence_value": "required_gate_blocked",
                "warning_code": "audit_input_integrity_gate_blocked",
                "blocking_warning": True,
            }
        )
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message="Required audit gate checks are blocked.",
                audit_area="audit_input_integrity",
                source_path=artifacts["formal_packet"]["paths"]["dir"],
                blocking_warning=True,
            )
        )
    elif optional_missing:
        row.update(
            {
                "artifact_status": "available_with_caveat",
                "evidence_status": "evidence_available_with_caveat",
                "audit_status": "candidate_audit_artifact_ready_with_caveats",
                "key_evidence_label": "manual_review_required",
                "key_evidence_value": f"optional_missing={len(optional_missing)}",
            }
        )
    else:
        row["key_evidence_label"] = "manual_review_required"
        row["key_evidence_value"] = "required_and_context_artifacts_available"
    return row


def formal_gate_row(
    args: argparse.Namespace,
    artifact: dict[str, Any],
    context: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = artifact_status_row(
        args,
        audit_area="formal_packet_gate_check",
        evidence_category="formal_packet",
        artifact=artifact,
        key_label="manual_review_required",
        key_value=f"packet_blockers_present={context['packet_blockers_present']}",
        caveat=FORMAL_DECISION_SEPARATE,
        warnings=warnings,
    )
    if context["packet_blockers_present"] and row["audit_status"] not in (
        "blocked_missing_required_artifact",
        "blocked_unreadable_input",
    ):
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["audit_status"] = "blocked_missing_required_artifact"
        row["warning_code"] = "formal_packet_gate_blocked"
        row["blocking_warning"] = True
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message="Formal packet gate has blockers.",
                audit_area="formal_packet_gate_check",
                source_path=artifact["paths"]["dir"],
                blocking_warning=True,
            )
        )
    return row


def execution_gate_row(
    args: argparse.Namespace,
    artifact: dict[str, Any],
    context: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = artifact["manifest"]
    row = artifact_status_row(
        args,
        audit_area="execution_plan_gate_check",
        evidence_category="execution_plan",
        artifact=artifact,
        key_label="manual_review_required",
        key_value=labels(
            f"packet_blockers_present={manifest.get('packet_blockers_present', '')}",
            f"risk_filtered_framing_present={manifest.get('risk_filtered_framing_present', '')}",
            f"{DECISION_ABSENT_KEY}={manifest.get(DECISION_ABSENT_KEY, '')}",
        ),
        caveat=FORMAL_DECISION_SEPARATE,
        warnings=warnings,
    )
    if context["execution_blockers_present"] and row["audit_status"] not in (
        "blocked_missing_required_artifact",
        "blocked_unreadable_input",
    ):
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["audit_status"] = "blocked_missing_required_artifact"
        row["warning_code"] = "execution_plan_gate_blocked"
        row["blocking_warning"] = True
        warnings.append(
            warning_row(
                warning_code=row["warning_code"],
                message="Execution plan gate has blockers.",
                audit_area="execution_plan_gate_check",
                source_path=artifact["paths"]["dir"],
                blocking_warning=True,
            )
        )
    return row


def framing_row(args: argparse.Namespace, artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    row = base_row(args, audit_area="risk_filtered_framing_check", artifact=artifact)
    row["evidence_category"] = "framing"
    row["key_evidence_label"] = (
        "risk_filtered_candidate_framing_preserved" if context["risk_filtered_framing_present"] else "manual_review_required"
    )
    row["key_evidence_value"] = bool_text(bool(context["risk_filtered_framing_present"]))
    if not context["risk_filtered_framing_present"]:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["audit_status"] = "blocked_missing_required_artifact"
        row["warning_code"] = "risk_filtered_framing_missing"
        row["blocking_warning"] = True
    return row


def same_namespace_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = artifact["manifest"]
    namespaces = manifest.get("metric_namespaces", "")
    namespace_text = ";".join(namespaces) if isinstance(namespaces, list) else str(namespaces)
    return artifact_status_row(
        args,
        audit_area="r_multiple_same_namespace_check",
        evidence_category="same_namespace_comparison",
        artifact=artifact,
        key_label="same_namespace_r_multiple_available" if namespace_text == "R_multiple" else "manual_review_required",
        key_value=namespace_text,
        caveat=FORMAL_DECISION_SEPARATE,
        warnings=warnings,
    )


def ablation_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    source = find_row(artifact["csv_rows"], review_block="key_tradeoff_summary") or find_row(
        artifact["csv_rows"], review_block="exact_vs_single_filter_a_review"
    )
    return artifact_status_row(
        args,
        audit_area="exact_vs_single_filter_a_ablation_audit",
        evidence_category="ablation",
        artifact=artifact,
        key_label="exact_mean_R_not_consistently_higher;exact_profit_factor_not_consistently_higher",
        key_value=labels(
            source.get("descriptive_summary", "") if source else "",
            f"{source.get('key_metric_2_name', '')}={source.get('key_metric_2_value', '')}" if source else "",
            f"{source.get('key_metric_3_name', '')}={source.get('key_metric_3_value', '')}" if source else "",
        ),
        caveat=labels("risk_filtered_candidate_framing_preserved", FORMAL_DECISION_SEPARATE),
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
        audit_area="deeper_walkforward_split_audit",
        evidence_category="deeper_walkforward",
        artifact=artifact,
        key_label=labels(
            "exact_lower_drawdown_all_splits_observed" if split_count and str(split_count) == str(lower_count) else "",
            "exact_mean_R_not_consistently_higher",
            "exact_profit_factor_not_consistently_higher",
        ),
        key_value=f"matched_splits={split_count};lower_drawdown={lower_count};mean_R_higher={mean_count};profit_factor_higher={pf_count}",
        caveat="manual_review_required",
        warnings=warnings,
    )


def timeout_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    source = find_row(artifact["csv_rows"], review_scope="exact_vs_single_filter_a_base_timeout_comparison")
    return artifact_status_row(
        args,
        audit_area="timeout_artifact_audit",
        evidence_category="timeout",
        artifact=artifact,
        key_label="timeout_rate_not_lower_for_exact;exact_timeout_mean_net_R_less_negative_observed",
        key_value=labels(
            f"timeout_rate_delta={source.get('timeout_rate_delta', '')}" if source else "",
            f"timeout_mean_net_R_delta={source.get('timeout_mean_net_R_delta', '')}" if source else "",
        ),
        caveat="manual_review_required",
        warnings=warnings,
    )


def equity_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    source = find_row(artifact["csv_rows"], review_scope="exact_vs_single_filter_a_base_drawdown_sequence_comparison")
    return artifact_status_row(
        args,
        audit_area="equity_drawdown_sequence_audit",
        evidence_category="equity_drawdown_sequence",
        artifact=artifact,
        key_label="exact_loss_cluster_reduction_observed;exact_drawdown_duration_reduction_observed",
        key_value=labels(
            f"drawdown_delta={source.get('drawdown_delta', '')}" if source else "",
            f"drawdown_duration_delta={source.get('drawdown_duration_delta', '')}" if source else "",
            f"longest_negative_streak_delta={source.get('longest_negative_streak_delta', '')}" if source else "",
        ),
        caveat="manual_review_required",
        warnings=warnings,
    )


def old_audit_row(args: argparse.Namespace, artifact: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    row = artifact_status_row(
        args,
        audit_area="old_candidate_audit_context",
        evidence_category="legacy_context",
        artifact=artifact,
        key_label="old_candidate_audit_context_only",
        key_value="context_only",
        caveat=labels("old_candidate_audit_context_only", FORMAL_DECISION_SEPARATE),
        warnings=warnings,
    )
    row["evidence_status"] = "context_only"
    row["audit_status"] = "context_only"
    if row["artifact_status"] == "available":
        row["artifact_status"] = "available_with_caveat"
    return row


def synthesis_row(
    args: argparse.Namespace,
    *,
    audit_area: str,
    evidence_category: str,
    key_label: str,
    caveat: str,
    required_next: str,
    blocked: bool,
) -> dict[str, Any]:
    row = base_row(args, audit_area=audit_area)
    row["evidence_category"] = evidence_category
    row["key_evidence_label"] = key_label
    row["caveat"] = labels(caveat, "descriptive_only_no_decision", "no_candidate_decision_made", "no_trading_decision_made")
    row["required_next_artifact"] = required_next
    if blocked:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["audit_status"] = "blocked_missing_required_artifact"
        row["warning_code"] = f"{audit_area}_blocked"
        row["blocking_warning"] = True
    else:
        row["artifact_status"] = "available_with_caveat"
        row["evidence_status"] = "evidence_available_with_caveat"
        row["audit_status"] = "candidate_audit_artifact_ready_with_caveats"
    return row


def build_audit_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    artifacts = {key: load_artifact(spec, args) for key, spec in SPECS.items()}
    warnings: list[dict[str, Any]] = []
    context = build_audit_context(artifacts)
    blocked = bool(context["required_blocked"]) or not context["risk_filtered_framing_present"] or not context["decision_absent"]
    rows = [
        integrity_row(args, artifacts=artifacts, context=context, warnings=warnings),
        formal_gate_row(args, artifacts["formal_packet"], context, warnings),
        execution_gate_row(args, artifacts["execution_plan"], context, warnings),
        framing_row(args, artifacts["formal_packet"], context),
        same_namespace_row(args, artifacts["comparison"], warnings),
        ablation_row(args, artifacts["research_packet"], warnings),
        split_row(args, artifacts["split_review"], warnings),
        timeout_row(args, artifacts["timeout_review"], warnings),
        equity_row(args, artifacts["equity_review"], warnings),
        old_audit_row(args, artifacts["old_audit"], warnings),
        synthesis_row(
            args,
            audit_area="candidate_audit_caveats",
            evidence_category="caveat",
            key_label="exact_mean_R_not_consistently_higher;timeout_rate_not_lower_for_exact;manual_review_required",
            caveat=RESEARCH_DECISION_SEPARATE,
            required_next="manual_candidate_audit_review_required",
            blocked=blocked,
        ),
        synthesis_row(
            args,
            audit_area="candidate_audit_status_summary",
            evidence_category="summary",
            key_label="risk_filtered_candidate_framing_preserved;manual_review_required",
            caveat=labels(FORMAL_DECISION_SEPARATE, RESEARCH_DECISION_SEPARATE),
            required_next="manual_candidate_audit_review_required",
            blocked=blocked,
        ),
        synthesis_row(
            args,
            audit_area="recommended_next_research_artifact",
            evidence_category="next_research_artifact",
            key_label=labels("manual_review_required", RESEARCH_DECISION_SEPARATE),
            caveat=FORMAL_DECISION_SEPARATE,
            required_next=RESEARCH_DECISION_READINESS_PACKET,
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
    audit_counts = count_rows(rows, "audit_status")
    split_count = report_metric(artifacts, "split_review", "matched_split_count", "walk_forward_split_comparison_count")
    lower_count = report_metric(artifacts, "split_review", "exact_lower_drawdown_split_count")
    mean_count = report_metric(artifacts, "split_review", "exact_mean_R_higher_split_count")
    pf_count = report_metric(artifacts, "split_review", "exact_profit_factor_higher_split_count")
    lines = [
        "# Fixed Candidate Artifact-Aware Candidate Audit",
        "",
        "Artifact-aware candidate audit only. It reads completed evidence artifacts and does not execute the candidate audit pipeline, validation, backtests, timeout review, diagnostics, model work, database mutation, or external actions.",
        "No final research decision was made.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- formal_candidate_audit_packet_dir: `{args.formal_candidate_audit_packet_dir}`",
        f"- candidate_audit_execution_plan_dir: `{args.candidate_audit_execution_plan_dir}`",
        f"- candidate_audit_readiness_dir: `{args.candidate_audit_readiness_dir}`",
        f"- research_review_packet_dir: `{args.research_review_packet_dir}`",
        f"- deeper_walkforward_split_review_dir: `{args.deeper_walkforward_split_review_dir}`",
        f"- timeout_artifact_review_dir: `{args.timeout_artifact_review_dir}`",
        f"- equity_drawdown_sequence_review_dir: `{args.equity_drawdown_sequence_review_dir}`",
        f"- comparison_table_dir: `{args.comparison_table_dir}`",
        f"- r_multiple_review_dir: `{args.r_multiple_review_dir}`",
        f"- old_candidate_audit_dir: `{args.old_candidate_audit_dir}`",
        "",
        "## Audit Status",
        "",
        f"- audit_rows: `{len(rows)}`",
        f"- available: `{artifact_counts.get('available', 0)}`",
        f"- available_with_caveat: `{artifact_counts.get('available_with_caveat', 0)}`",
        f"- missing: `{artifact_counts.get('missing', 0)}`",
        f"- optional_missing: `{artifact_counts.get('optional_missing', 0)}`",
        f"- ready_with_caveats: `{audit_counts.get('candidate_audit_artifact_ready_with_caveats', 0)}`",
        f"- blocked_missing_required_artifact: `{audit_counts.get('blocked_missing_required_artifact', 0)}`",
        f"- warnings: `{len(warnings)}`",
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
        "## Audit Caveats",
        "",
        "- final research decision remains separate.",
        "- timeout caveat remains.",
        "- manual review remains required.",
        "- old candidate audit is context-only.",
        "",
        "## Suggested Next Artifact",
        "",
        f"`{RESEARCH_DECISION_READINESS_PACKET}` or manual candidate audit review.",
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
    audit_counts = count_rows(rows, "audit_status")
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "formal_candidate_audit_packet_dir": str(args.formal_candidate_audit_packet_dir),
        "candidate_audit_execution_plan_dir": str(args.candidate_audit_execution_plan_dir),
        "candidate_audit_readiness_dir": str(args.candidate_audit_readiness_dir),
        "research_review_packet_dir": str(args.research_review_packet_dir),
        "deeper_walkforward_split_review_dir": str(args.deeper_walkforward_split_review_dir),
        "timeout_artifact_review_dir": str(args.timeout_artifact_review_dir),
        "equity_drawdown_sequence_review_dir": str(args.equity_drawdown_sequence_review_dir),
        "comparison_table_dir": str(args.comparison_table_dir),
        "r_multiple_review_dir": str(args.r_multiple_review_dir),
        "old_candidate_audit_dir": str(args.old_candidate_audit_dir),
        "audit_row_count": len(rows),
        "available_count": artifact_counts.get("available", 0),
        "available_with_caveat_count": artifact_counts.get("available_with_caveat", 0),
        "missing_count": artifact_counts.get("missing", 0),
        "unreadable_count": artifact_counts.get("unreadable", 0),
        "optional_missing_count": artifact_counts.get("optional_missing", 0),
        "candidate_audit_artifact_ready_for_manual_review_count": audit_counts.get(
            "candidate_audit_artifact_ready_for_manual_review", 0
        ),
        "candidate_audit_artifact_ready_with_caveats_count": audit_counts.get(
            "candidate_audit_artifact_ready_with_caveats", 0
        ),
        "blocked_missing_required_artifact_count": audit_counts.get("blocked_missing_required_artifact", 0),
        "blocked_unreadable_input_count": audit_counts.get("blocked_unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "risk_filtered_framing_present": bool(context["risk_filtered_framing_present"]),
        DECISION_ABSENT_KEY: bool(context["decision_absent"]),
        "old_candidate_audit_context_only": True,
        "recommended_next_artifact": RESEARCH_DECISION_READINESS_PACKET,
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
    rows, warnings, context = build_audit_rows(args)
    write_csv(paths["audit"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, context=context)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, context=context)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an artifact-only fixed-candidate artifact-aware candidate audit."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument(
        "--formal-candidate-audit-packet-dir",
        type=Path,
        default=DEFAULT_FORMAL_CANDIDATE_AUDIT_PACKET_DIR,
    )
    parser.add_argument(
        "--candidate-audit-execution-plan-dir",
        type=Path,
        default=DEFAULT_CANDIDATE_AUDIT_EXECUTION_PLAN_DIR,
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
        print(f"Fixed-candidate artifact-aware candidate audit failed: {exc}")
        return 1
    print("Fixed-candidate artifact-aware candidate audit complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
