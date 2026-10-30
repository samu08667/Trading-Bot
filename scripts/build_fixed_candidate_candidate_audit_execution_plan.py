"""Build an artifact-only execution plan for fixed-candidate candidate audit.

This module reads the formal candidate audit packet and plans the safest next
artifact-aware audit execution path. It does not execute candidate audit,
validation, backtests, timeout review, diagnostics, model work, database work,
or external actions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_candidate_audit_execution_plan"
DEFAULT_FORMAL_CANDIDATE_AUDIT_PACKET_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_formal_candidate_audit_packet"
    / "gbpusd_short_h10_1_5_off_hours_formal_candidate_audit_packet_v1"
)
DEFAULT_CANDIDATE_AUDIT_COMMAND_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_candidate_audit_command_plan"
    / "gbpusd_short_h10_1_5_off_hours_candidate_audit_command_plan_v1"
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
DEFAULT_OLD_CANDIDATE_AUDIT_DIR = (
    BASE_DIR
    / "reports"
    / "candidate_audit_pipeline"
    / "gbpusd_short_h10_1_5_off_hours_candidate_audit_exec_v1"
)
DEFAULT_ARTIFACT_AWARE_AUDIT_SCRIPT = BASE_DIR / "scripts" / "run_fixed_candidate_artifact_aware_candidate_audit.py"
DEFAULT_OLD_CANDIDATE_AUDIT_SCRIPT = BASE_DIR / "scripts" / "run_candidate_audit_pipeline.py"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_candidate_audit_execution_plan"

PACKET_CSV = "fixed_candidate_formal_candidate_audit_packet.csv"
PACKET_REPORT = "fixed_candidate_formal_candidate_audit_packet_report.md"
PACKET_MANIFEST = "fixed_candidate_formal_candidate_audit_packet_manifest.json"
PACKET_WARNINGS = "fixed_candidate_formal_candidate_audit_packet_warnings.csv"

OUTPUT_CSV = "fixed_candidate_candidate_audit_execution_plan.csv"
OUTPUT_REPORT = "fixed_candidate_candidate_audit_execution_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_candidate_audit_execution_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_candidate_audit_execution_plan_manifest.json"

FIELDNAMES = [
    "run_id",
    "plan_step",
    "plan_role",
    "artifact_status",
    "command_status",
    "source_dir",
    "source_script",
    "expected_output_dir",
    "manual_command",
    "compatibility_status",
    "packet_status",
    "caveat",
    "required_next_artifact",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "plan_step",
    "source_path",
    "blocking_warning",
]

ARTIFACT_AWARE_REQUIRED_FLAGS = (
    "--formal-candidate-audit-packet-dir",
    "--candidate-audit-readiness-dir",
    "--research-review-packet-dir",
    "--output-dir",
    "--run-id",
    "--overwrite",
)

FORMAL_PACKET_CONTRACT_FLAGS = (
    "--formal-candidate-audit-packet-dir",
    "--candidate-audit-readiness-dir",
    "--research-review-packet-dir",
)

FINAL_DECISION_MARKERS = (
    "final_decision",
    "final_gate",
    "gate_label",
)


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
        "execution_plan": output_dir / OUTPUT_CSV,
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


def quote_arg(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    if any(char.isspace() for char in text) or any(char in text for char in ['"', "'", "&", "(", ")"]):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def script_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def script_supports_flags(path: Path, flags: tuple[str, ...]) -> tuple[bool, list[str]]:
    text = script_text(path)
    missing = [flag for flag in flags if flag not in text]
    return bool(text) and not missing, missing


def warning_row(
    *,
    warning_code: str,
    message: str,
    plan_step: str,
    source_path: Path | str,
    blocking_warning: bool = False,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": "error" if blocking_warning else severity,
        "message": message,
        "plan_step": plan_step,
        "source_path": str(source_path),
        "blocking_warning": bool_text(blocking_warning),
    }


def packet_paths(args: argparse.Namespace) -> dict[str, Path]:
    root = Path(args.formal_candidate_audit_packet_dir)
    return {
        "dir": root,
        "csv": root / PACKET_CSV,
        "manifest": root / PACKET_MANIFEST,
        "report": root / PACKET_REPORT,
        "warnings": root / PACKET_WARNINGS,
    }


def packet_state(args: argparse.Namespace) -> dict[str, Any]:
    paths = packet_paths(args)
    rows = read_csv_rows(paths["csv"])
    manifest = read_json(paths["manifest"])
    warnings = read_csv_rows(paths["warnings"])
    report_text = read_text(paths["report"])
    packet_text = "\n".join(
        [
            report_text,
            json.dumps(manifest, sort_keys=True),
            "\n".join(";".join(row.values()) for row in rows),
        ]
    ).lower()
    files_present = paths["csv"].exists() and paths["manifest"].exists() and paths["report"].exists()
    blockers = (
        not files_present
        or int(manifest.get("blocked_missing_required_artifact_count") or 0) > 0
        or int(manifest.get("blocked_unreadable_input_count") or 0) > 0
        or int(manifest.get("blocking_warnings_count") or 0) > 0
        or any(str(row.get("blocking_warning") or "").lower() == "true" for row in warnings)
    )
    risk_framing_present = "risk_filtered_candidate_framing_required" in packet_text or "risk-filtered candidate" in packet_text
    final_decision_absent = not any(marker in packet_text for marker in FINAL_DECISION_MARKERS)
    return {
        "paths": paths,
        "rows": rows,
        "manifest": manifest,
        "warnings": warnings,
        "report_text": report_text,
        "files_present": files_present,
        "packet_blockers_present": blockers,
        "risk_filtered_framing_present": risk_framing_present,
        "final_decision_absent": final_decision_absent,
    }


def base_row(args: argparse.Namespace, *, plan_step: str, plan_role: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "plan_step": plan_step,
        "plan_role": plan_role,
        "artifact_status": "available",
        "command_status": "no_command_needed",
        "source_dir": "",
        "source_script": "",
        "expected_output_dir": "",
        "manual_command": "",
        "compatibility_status": "not_applicable",
        "packet_status": "",
        "caveat": "no_candidate_decision_made;no_trading_decision_made",
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


def build_artifact_aware_manual_command(args: argparse.Namespace) -> str:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    expected_output_dir = output_dir / "manual_artifact_aware_audit"
    parts = [
        args.python_executable,
        str(args.artifact_aware_audit_script),
        "--run-id",
        f"{args.run_id}_artifact_aware_audit",
        "--formal-candidate-audit-packet-dir",
        str(args.formal_candidate_audit_packet_dir),
        "--candidate-audit-readiness-dir",
        str(args.candidate_audit_readiness_dir),
        "--research-review-packet-dir",
        str(args.research_review_packet_dir),
        "--output-dir",
        str(expected_output_dir),
        "--overwrite",
    ]
    return " ".join(quote_arg(part) for part in parts)


def build_plan_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    packet = packet_state(args)
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    artifact_script = Path(args.artifact_aware_audit_script)
    old_script = Path(args.old_candidate_audit_script)
    artifact_supported, artifact_missing_flags = script_supports_flags(artifact_script, ARTIFACT_AWARE_REQUIRED_FLAGS)
    old_supported, old_missing_flags = script_supports_flags(old_script, FORMAL_PACKET_CONTRACT_FLAGS)
    packet_blocked = bool(packet["packet_blockers_present"])
    risk_missing = not packet["risk_filtered_framing_present"]
    decision_present = not packet["final_decision_absent"]
    blocked = packet_blocked or risk_missing or decision_present
    packet_status = "blocked_by_packet" if blocked else "formal_packet_no_blockers"

    rows: list[dict[str, Any]] = []

    gate = base_row(args, plan_step="formal_packet_gate_check", plan_role="packet_gate")
    gate.update(
        {
            "source_dir": packet["paths"]["dir"],
            "packet_status": "blocked_by_packet" if packet_blocked else "formal_packet_no_blockers",
            "caveat": labels(
                "formal_packet_no_blockers" if not packet_blocked else "",
                "no_candidate_decision_made",
                "no_trading_decision_made",
            ),
        }
    )
    if packet_blocked:
        gate.update(
            {
                "artifact_status": "missing" if not packet["files_present"] else "available_with_caveat",
                "command_status": "blocked_by_packet",
                "warning_code": "formal_packet_blockers_present",
                "blocking_warning": True,
                "required_next_artifact": PACKET_CSV,
            }
        )
        warnings.append(
            warning_row(
                warning_code="formal_packet_blockers_present",
                message="Formal candidate audit packet contains blockers or is missing required files.",
                plan_step="formal_packet_gate_check",
                source_path=packet["paths"]["dir"],
                blocking_warning=True,
            )
        )
    rows.append(gate)

    framing = base_row(args, plan_step="risk_filtered_framing_check", plan_role="framing_check")
    framing.update(
        {
            "source_dir": packet["paths"]["dir"],
            "packet_status": packet_status,
            "caveat": labels(
                "risk_filtered_candidate_framing_preserved" if packet["risk_filtered_framing_present"] else "",
                "no_candidate_decision_made",
                "no_trading_decision_made",
            ),
        }
    )
    if risk_missing:
        framing.update(
            {
                "command_status": "blocked_by_packet",
                "warning_code": "risk_filtered_framing_missing",
                "blocking_warning": True,
                "required_next_artifact": "formal_packet_with_risk_filtered_framing",
            }
        )
        warnings.append(
            warning_row(
                warning_code="risk_filtered_framing_missing",
                message="Formal packet does not explicitly preserve risk-filtered candidate framing.",
                plan_step="risk_filtered_framing_check",
                source_path=packet["paths"]["dir"],
                blocking_warning=True,
            )
        )
    rows.append(framing)

    decision_absence = base_row(args, plan_step="final_decision_absence_check", plan_role="decision_absence_check")
    decision_absence.update(
        {
            "source_dir": packet["paths"]["dir"],
            "packet_status": packet_status,
            "caveat": labels(
                "no_final_decision_in_packet" if packet["final_decision_absent"] else "",
                "no_candidate_decision_made",
                "no_trading_decision_made",
            ),
        }
    )
    if decision_present:
        decision_absence.update(
            {
                "command_status": "blocked_by_packet",
                "warning_code": "final_decision_marker_present",
                "blocking_warning": True,
                "required_next_artifact": "formal_packet_without_decision_marker",
            }
        )
        warnings.append(
            warning_row(
                warning_code="final_decision_marker_present",
                message="Formal packet contains a final decision marker.",
                plan_step="final_decision_absence_check",
                source_path=packet["paths"]["dir"],
                blocking_warning=True,
            )
        )
    rows.append(decision_absence)

    script_status = base_row(args, plan_step="artifact_aware_audit_script_status", plan_role="artifact_aware_audit")
    script_status.update(
        {
            "source_script": artifact_script,
            "expected_output_dir": output_dir / "manual_artifact_aware_audit",
            "packet_status": packet_status,
            "required_next_artifact": "run_fixed_candidate_artifact_aware_candidate_audit.py",
        }
    )
    if blocked:
        script_status["command_status"] = "blocked_by_packet"
    elif not artifact_script.exists():
        script_status.update(
            {
                "artifact_status": "missing",
                "command_status": "implementation_required",
                "warning_code": "artifact_aware_audit_script_missing",
                "caveat": "artifact_aware_audit_script_required;implementation_required_before_candidate_audit_execution;no_candidate_decision_made;no_trading_decision_made",
            }
        )
    elif not artifact_supported:
        script_status.update(
            {
                "command_status": "unsupported_by_script_cli",
                "compatibility_status": "unknown_requires_manual_review",
                "warning_code": "artifact_aware_audit_cli_incomplete",
                "caveat": labels(
                    "implementation_required_before_candidate_audit_execution",
                    "missing_flags=" + ",".join(artifact_missing_flags),
                    "no_candidate_decision_made",
                    "no_trading_decision_made",
                ),
            }
        )
    else:
        script_status.update(
            {
                "command_status": "no_command_needed",
                "compatibility_status": "compatible_with_formal_packet",
                "caveat": "manual_execution_only_after_review;no_candidate_decision_made;no_trading_decision_made",
            }
        )
    rows.append(script_status)

    command = base_row(args, plan_step="artifact_aware_audit_command", plan_role="artifact_aware_audit")
    command.update(
        {
            "source_script": artifact_script,
            "expected_output_dir": output_dir / "manual_artifact_aware_audit",
            "packet_status": packet_status,
            "required_next_artifact": "artifact_aware_candidate_audit_outputs",
        }
    )
    if blocked:
        command["command_status"] = "blocked_by_packet"
    elif artifact_supported:
        command.update(
            {
                "command_status": "planned_manual_command",
                "compatibility_status": "compatible_with_formal_packet",
                "manual_command": build_artifact_aware_manual_command(args),
                "caveat": "manual_execution_only_after_review;no_candidate_decision_made;no_trading_decision_made",
            }
        )
    else:
        command.update(
            {
                "artifact_status": "missing" if not artifact_script.exists() else "available",
                "command_status": "implementation_required" if not artifact_script.exists() else "unsupported_by_script_cli",
                "compatibility_status": "unknown_requires_manual_review",
                "warning_code": "artifact_aware_audit_not_plannable",
                "caveat": "artifact_aware_audit_script_required;implementation_required_before_candidate_audit_execution;no_candidate_decision_made;no_trading_decision_made",
            }
        )
    rows.append(command)

    legacy = base_row(args, plan_step="legacy_candidate_audit_context", plan_role="legacy_context")
    legacy.update(
        {
            "source_dir": args.old_candidate_audit_dir,
            "source_script": old_script,
            "command_status": "context_only_no_command",
            "compatibility_status": "context_only",
            "packet_status": packet_status,
            "caveat": "old_candidate_audit_context_only;old_candidate_audit_not_primary_path;no_candidate_decision_made;no_trading_decision_made",
        }
    )
    if not Path(args.old_candidate_audit_dir).exists():
        legacy["artifact_status"] = "missing"
    rows.append(legacy)

    legacy_compat = base_row(args, plan_step="legacy_candidate_audit_compatibility_check", plan_role="compatibility_check")
    legacy_compat.update(
        {
            "source_script": old_script,
            "command_status": "context_only_no_command",
            "compatibility_status": "compatible_with_formal_packet" if old_supported else "not_compatible_with_formal_packet",
            "packet_status": packet_status,
            "caveat": labels(
                "old_candidate_audit_context_only",
                "old_candidate_audit_not_primary_path",
                "no_candidate_decision_made",
                "no_trading_decision_made",
            ),
            "warning_code": "" if old_supported else "old_candidate_audit_not_compatible",
            "required_next_artifact": "" if old_supported else "artifact_aware_audit_script",
        }
    )
    if not old_script.exists():
        legacy_compat["command_status"] = "missing_script"
        legacy_compat["compatibility_status"] = "unknown_requires_manual_review"
        legacy_compat["warning_code"] = "old_candidate_audit_script_missing"
    elif old_missing_flags:
        legacy_compat["required_next_artifact"] = "artifact_aware_audit_script"
    rows.append(legacy_compat)

    guidance = base_row(args, plan_step="manual_execution_guidance", plan_role="manual_guidance")
    guidance.update(
        {
            "command_status": "blocked_by_packet" if blocked else "no_command_needed",
            "packet_status": packet_status,
            "caveat": "manual_execution_only_after_review;no_candidate_decision_made;no_trading_decision_made",
            "required_next_artifact": "review_execution_plan_before_manual_execution",
        }
    )
    rows.append(guidance)

    if blocked:
        next_status = "blocked_by_packet"
    elif not artifact_script.exists():
        next_status = "implementation_required"
    elif artifact_supported:
        next_status = "no_command_needed"
    else:
        next_status = "unsupported_by_script_cli"
    next_artifact = base_row(args, plan_step="next_artifact_expected", plan_role="next_artifact")
    next_artifact.update(
        {
            "command_status": next_status,
            "source_script": artifact_script,
            "expected_output_dir": output_dir / "manual_artifact_aware_audit",
            "packet_status": packet_status,
            "required_next_artifact": "run_fixed_candidate_artifact_aware_candidate_audit.py",
            "caveat": "artifact_aware_audit_script_required;manual_execution_only_after_review;no_candidate_decision_made;no_trading_decision_made",
        }
    )
    rows.append(next_artifact)

    metadata = {
        "packet_blockers_present": blocked,
        "formal_packet_blockers_present": packet_blocked,
        "risk_filtered_framing_present": bool(packet["risk_filtered_framing_present"]),
        "final_decision_absent": bool(packet["final_decision_absent"]),
        "artifact_supported": artifact_supported,
        "artifact_missing_flags": artifact_missing_flags,
        "old_supported": old_supported,
        "old_missing_flags": old_missing_flags,
        "artifact_script_exists": artifact_script.exists(),
    }
    return rows, warnings, metadata


def count_rows(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    return Counter(str(row.get(field) or "") for row in rows)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    status_counts = count_rows(rows, "command_status")
    lines = [
        "# Fixed Candidate Candidate-Audit Execution Plan",
        "",
        "Command-plan-only artifact. It reads the formal packet and does not execute candidate audit, validation, backtests, timeout review, diagnostics, model work, database mutation, or external actions.",
        "No candidate-quality conclusion or trading decision was made.",
        "",
        "## Formal Packet Gate",
        "",
        f"- formal_candidate_audit_packet_dir: `{args.formal_candidate_audit_packet_dir}`",
        f"- packet_blockers_present: `{str(metadata['packet_blockers_present']).lower()}`",
        f"- risk_filtered_framing_present: `{str(metadata['risk_filtered_framing_present']).lower()}`",
        f"- final_decision_absent: `{str(metadata['final_decision_absent']).lower()}`",
        "",
        "## Preferred Path",
        "",
        "- preferred_next_path: `run_fixed_candidate_artifact_aware_candidate_audit.py`",
        f"- artifact_aware_audit_script: `{args.artifact_aware_audit_script}`",
        f"- artifact_aware_audit_script_exists: `{str(metadata['artifact_script_exists']).lower()}`",
        f"- implementation_required_count: `{status_counts.get('implementation_required', 0)}`",
        "",
        "## Legacy Context",
        "",
        "The old candidate audit remains context-only and is not the primary path for this formal-packet evidence chain.",
        f"- old_candidate_audit_script: `{args.old_candidate_audit_script}`",
        f"- old_candidate_audit_compatibility: `{'compatible_with_formal_packet' if metadata['old_supported'] else 'not_compatible_with_formal_packet'}`",
        "",
        "## Caveats",
        "",
        "- Manual execution is only appropriate after reviewing this execution plan.",
        "- The next step is implementing an artifact-aware audit runner or packet executor when the script is missing.",
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
    metadata: dict[str, Any],
) -> None:
    statuses = count_rows(rows, "command_status")
    preferred = (
        "run_fixed_candidate_artifact_aware_candidate_audit.py"
        if metadata["artifact_script_exists"]
        else "implementation_required"
    )
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "formal_candidate_audit_packet_dir": str(args.formal_candidate_audit_packet_dir),
        "candidate_audit_command_plan_dir": str(args.candidate_audit_command_plan_dir),
        "candidate_audit_readiness_dir": str(args.candidate_audit_readiness_dir),
        "artifact_aware_audit_script": str(args.artifact_aware_audit_script),
        "old_candidate_audit_script": str(args.old_candidate_audit_script),
        "plan_row_count": len(rows),
        "planned_manual_command_count": statuses.get("planned_manual_command", 0),
        "implementation_required_count": statuses.get("implementation_required", 0),
        "context_only_count": statuses.get("context_only_no_command", 0),
        "blocked_by_packet_count": statuses.get("blocked_by_packet", 0),
        "unsupported_by_script_cli_count": statuses.get("unsupported_by_script_cli", 0),
        "missing_script_count": statuses.get("missing_script", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "packet_blockers_present": bool(metadata["packet_blockers_present"]),
        "risk_filtered_framing_present": bool(metadata["risk_filtered_framing_present"]),
        "final_decision_absent": bool(metadata["final_decision_absent"]),
        "old_candidate_audit_context_only": True,
        "preferred_next_artifact": preferred,
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
    rows, warnings, metadata = build_plan_rows(args)
    write_csv(paths["execution_plan"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an artifact-only fixed-candidate candidate-audit execution plan."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument(
        "--formal-candidate-audit-packet-dir",
        type=Path,
        default=DEFAULT_FORMAL_CANDIDATE_AUDIT_PACKET_DIR,
    )
    parser.add_argument(
        "--candidate-audit-command-plan-dir",
        type=Path,
        default=DEFAULT_CANDIDATE_AUDIT_COMMAND_PLAN_DIR,
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
    parser.add_argument("--old-candidate-audit-dir", type=Path, default=DEFAULT_OLD_CANDIDATE_AUDIT_DIR)
    parser.add_argument("--artifact-aware-audit-script", type=Path, default=DEFAULT_ARTIFACT_AWARE_AUDIT_SCRIPT)
    parser.add_argument("--old-candidate-audit-script", type=Path, default=DEFAULT_OLD_CANDIDATE_AUDIT_SCRIPT)
    parser.add_argument("--python-executable", default="python")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Fixed-candidate candidate-audit execution plan failed: {exc}")
        return 1
    print("Fixed-candidate candidate-audit execution plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
