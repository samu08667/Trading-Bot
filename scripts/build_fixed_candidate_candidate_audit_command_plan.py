"""Build an artifact-only command plan for fixed-candidate candidate audit.

This module reads the candidate-audit readiness artifact and produces a manual
command plan for the next fixed-candidate audit artifact. It does not execute
candidate audit, validation, backtests, timeout review, diagnostics, model
work, database work, or external actions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_candidate_audit_command_plan"
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
DEFAULT_FORMAL_AUDIT_PACKET_SCRIPT = BASE_DIR / "scripts" / "build_fixed_candidate_formal_candidate_audit_packet.py"
DEFAULT_OLD_CANDIDATE_AUDIT_SCRIPT = BASE_DIR / "scripts" / "run_candidate_audit_pipeline.py"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_candidate_audit_command_plan"

READINESS_CSV = "fixed_candidate_candidate_audit_readiness.csv"
READINESS_REPORT = "fixed_candidate_candidate_audit_readiness_report.md"
READINESS_MANIFEST = "fixed_candidate_candidate_audit_readiness_manifest.json"
READINESS_WARNINGS = "fixed_candidate_candidate_audit_readiness_warnings.csv"

OUTPUT_CSV = "fixed_candidate_candidate_audit_command_plan.csv"
OUTPUT_REPORT = "fixed_candidate_candidate_audit_command_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_candidate_audit_command_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_candidate_audit_command_plan_manifest.json"

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
    "plan_step",
    "source_path",
    "blocking_warning",
]

FORMAL_AUDIT_REQUIRED_FLAGS = (
    "--run-id",
    "--research-review-packet-dir",
    "--deeper-walkforward-split-review-dir",
    "--timeout-artifact-review-dir",
    "--equity-drawdown-sequence-review-dir",
    "--candidate-audit-readiness-dir",
    "--output-dir",
    "--overwrite",
)

NEW_EVIDENCE_CHAIN_FLAGS = (
    "--candidate-audit-readiness-dir",
    "--research-review-packet-dir",
    "--deeper-walkforward-split-review-dir",
    "--timeout-artifact-review-dir",
    "--equity-drawdown-sequence-review-dir",
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


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "command_plan": output_dir / OUTPUT_CSV,
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


def readiness_paths(args: argparse.Namespace) -> dict[str, Path]:
    root = Path(args.candidate_audit_readiness_dir)
    return {
        "dir": root,
        "csv": root / READINESS_CSV,
        "manifest": root / READINESS_MANIFEST,
        "report": root / READINESS_REPORT,
        "warnings": root / READINESS_WARNINGS,
    }


def readiness_blockers(paths: dict[str, Path]) -> tuple[bool, dict[str, Any], list[dict[str, str]]]:
    manifest = read_json(paths["manifest"])
    warnings = read_csv_rows(paths["warnings"])
    blocked = (
        not paths["csv"].exists()
        or not paths["manifest"].exists()
        or not paths["report"].exists()
        or int(manifest.get("blocked_missing_required_artifact_count") or 0) > 0
        or int(manifest.get("blocked_unreadable_input_count") or 0) > 0
        or int(manifest.get("blocking_warnings_count") or 0) > 0
        or any(str(row.get("blocking_warning") or row.get("blocking") or "").lower() == "true" for row in warnings)
    )
    return blocked, manifest, warnings


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
        "readiness_status": "",
        "caveat": "no_candidate_decision_made;no_trading_decision_made",
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


def build_formal_manual_command(args: argparse.Namespace) -> str:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    expected_output_dir = output_dir / "manual_formal_audit_packet"
    parts = [
        args.python_executable,
        str(args.formal_audit_packet_script),
        "--run-id",
        f"{args.run_id}_formal_packet",
        "--candidate-audit-readiness-dir",
        str(args.candidate_audit_readiness_dir),
        "--research-review-packet-dir",
        str(args.research_review_packet_dir),
        "--deeper-walkforward-split-review-dir",
        str(args.deeper_walkforward_split_review_dir),
        "--timeout-artifact-review-dir",
        str(args.timeout_artifact_review_dir),
        "--equity-drawdown-sequence-review-dir",
        str(args.equity_drawdown_sequence_review_dir),
        "--output-dir",
        str(expected_output_dir),
        "--overwrite",
    ]
    return " ".join(quote_arg(part) for part in parts)


def build_plan_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    readiness = readiness_paths(args)
    blocked, readiness_manifest, readiness_warning_rows = readiness_blockers(readiness)
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    formal_script = Path(args.formal_audit_packet_script)
    old_script = Path(args.old_candidate_audit_script)
    formal_supported, formal_missing_flags = script_supports_flags(formal_script, FORMAL_AUDIT_REQUIRED_FLAGS)
    old_supported, old_missing_flags = script_supports_flags(old_script, NEW_EVIDENCE_CHAIN_FLAGS)
    readiness_status = "blocked_by_readiness" if blocked else "readiness_no_blockers"

    rows: list[dict[str, Any]] = []

    gate = base_row(args, plan_step="readiness_gate_check", plan_role="readiness_gate")
    gate.update(
        {
            "source_dir": readiness["dir"],
            "readiness_status": readiness_status,
            "caveat": labels("readiness_no_blockers" if not blocked else "", "no_candidate_decision_made", "no_trading_decision_made"),
        }
    )
    if blocked:
        gate.update(
            {
                "command_status": "blocked_by_readiness",
                "warning_code": "readiness_blockers_present",
                "blocking_warning": True,
                "required_next_artifact": READINESS_CSV,
            }
        )
        warnings.append(
            warning_row(
                warning_code="readiness_blockers_present",
                message="Candidate-audit readiness contains blockers or is missing required files.",
                plan_step="readiness_gate_check",
                source_path=readiness["dir"],
                blocking_warning=True,
            )
        )
    rows.append(gate)

    preferred = base_row(args, plan_step="preferred_formal_audit_packet_path", plan_role="preferred_new_artifact_path")
    preferred.update(
        {
            "source_script": formal_script,
            "expected_output_dir": output_dir / "manual_formal_audit_packet",
            "readiness_status": readiness_status,
            "caveat": "new_formal_audit_packet_recommended;risk_filtered_candidate_framing_required;no_candidate_decision_made;no_trading_decision_made",
            "required_next_artifact": "build_fixed_candidate_formal_candidate_audit_packet.py",
        }
    )
    if blocked:
        preferred["command_status"] = "blocked_by_readiness"
    rows.append(preferred)

    script_status = base_row(args, plan_step="formal_audit_packet_script_status", plan_role="formal_audit_packet")
    script_status.update(
        {
            "source_script": formal_script,
            "expected_output_dir": output_dir / "manual_formal_audit_packet",
            "readiness_status": readiness_status,
            "required_next_artifact": "build_fixed_candidate_formal_candidate_audit_packet.py",
        }
    )
    if blocked:
        script_status["command_status"] = "blocked_by_readiness"
    elif not formal_script.exists():
        script_status.update(
            {
                "artifact_status": "missing",
                "command_status": "implementation_required",
                "warning_code": "formal_audit_packet_script_missing",
                "caveat": "implementation_required_before_manual_audit;new_formal_audit_packet_recommended;no_candidate_decision_made;no_trading_decision_made",
            }
        )
    elif not formal_supported:
        script_status.update(
            {
                "command_status": "unsupported_by_script_cli",
                "compatibility_status": "unknown_requires_manual_review",
                "warning_code": "formal_audit_packet_cli_incomplete",
                "caveat": labels(
                    "implementation_required_before_manual_audit",
                    "missing_flags=" + ",".join(formal_missing_flags),
                    "no_candidate_decision_made",
                    "no_trading_decision_made",
                ),
            }
        )
    else:
        script_status.update(
            {
                "command_status": "no_command_needed",
                "compatibility_status": "compatible_with_new_evidence_chain",
                "caveat": "manual_execution_only_after_review;risk_filtered_candidate_framing_required;no_candidate_decision_made;no_trading_decision_made",
            }
        )
    rows.append(script_status)

    formal_command = base_row(args, plan_step="formal_audit_packet_command", plan_role="formal_audit_packet")
    formal_command.update(
        {
            "source_script": formal_script,
            "expected_output_dir": output_dir / "manual_formal_audit_packet",
            "readiness_status": readiness_status,
            "required_next_artifact": "fixed_candidate_formal_candidate_audit_packet",
        }
    )
    if blocked:
        formal_command["command_status"] = "blocked_by_readiness"
    elif formal_supported:
        formal_command.update(
            {
                "command_status": "planned_manual_command",
                "compatibility_status": "compatible_with_new_evidence_chain",
                "manual_command": build_formal_manual_command(args),
                "caveat": "manual_execution_only_after_review;risk_filtered_candidate_framing_required;no_candidate_decision_made;no_trading_decision_made",
            }
        )
    else:
        formal_command.update(
            {
                "command_status": "implementation_required" if not formal_script.exists() else "unsupported_by_script_cli",
                "compatibility_status": "unknown_requires_manual_review",
                "caveat": "implementation_required_before_manual_audit;new_formal_audit_packet_recommended;no_candidate_decision_made;no_trading_decision_made",
                "warning_code": "formal_audit_packet_not_plannable",
            }
        )
    rows.append(formal_command)

    legacy = base_row(args, plan_step="legacy_candidate_audit_context", plan_role="legacy_context")
    legacy.update(
        {
            "source_dir": args.old_candidate_audit_dir,
            "source_script": old_script,
            "command_status": "context_only_no_command",
            "compatibility_status": "context_only",
            "caveat": "old_candidate_audit_context_only;old_candidate_audit_does_not_consume_new_chain;no_candidate_decision_made;no_trading_decision_made",
        }
    )
    if not Path(args.old_candidate_audit_dir).exists():
        legacy["artifact_status"] = "missing"
    rows.append(legacy)

    compat = base_row(args, plan_step="old_candidate_audit_compatibility_check", plan_role="compatibility_check")
    compat.update(
        {
            "source_script": old_script,
            "command_status": "context_only_no_command",
            "compatibility_status": "compatible_with_new_evidence_chain" if old_supported else "not_compatible_with_new_evidence_chain",
            "caveat": labels(
                "old_candidate_audit_context_only",
                "" if old_supported else "old_candidate_audit_does_not_consume_new_chain",
                "no_candidate_decision_made",
                "no_trading_decision_made",
            ),
            "warning_code": "" if old_supported else "old_candidate_audit_not_compatible",
        }
    )
    if not old_script.exists():
        compat["command_status"] = "missing_script"
        compat["compatibility_status"] = "unknown_requires_manual_review"
        compat["warning_code"] = "old_candidate_audit_script_missing"
    elif old_missing_flags:
        compat["required_next_artifact"] = "new_formal_audit_packet_path"
    rows.append(compat)

    guidance = base_row(args, plan_step="manual_execution_guidance", plan_role="manual_guidance")
    guidance.update(
        {
            "command_status": "no_command_needed" if not blocked else "blocked_by_readiness",
            "readiness_status": readiness_status,
            "caveat": "manual_execution_only_after_review;risk_filtered_candidate_framing_required;no_candidate_decision_made;no_trading_decision_made",
            "required_next_artifact": "review_command_plan_before_manual_execution",
        }
    )
    rows.append(guidance)

    next_artifact = base_row(args, plan_step="next_artifact_expected", plan_role="next_artifact")
    if blocked:
        next_command_status = "blocked_by_readiness"
    elif not formal_script.exists():
        next_command_status = "implementation_required"
    elif formal_supported:
        next_command_status = "no_command_needed"
    else:
        next_command_status = "unsupported_by_script_cli"
    next_artifact.update(
        {
            "command_status": next_command_status,
            "readiness_status": readiness_status,
            "source_script": formal_script,
            "expected_output_dir": output_dir / "manual_formal_audit_packet",
            "required_next_artifact": "build_fixed_candidate_formal_candidate_audit_packet.py",
            "caveat": "new_formal_audit_packet_recommended;risk_filtered_candidate_framing_required;no_candidate_decision_made;no_trading_decision_made",
        }
    )
    rows.append(next_artifact)

    metadata = {
        "readiness_manifest": readiness_manifest,
        "readiness_warnings": readiness_warning_rows,
        "readiness_blockers_present": blocked,
        "formal_supported": formal_supported,
        "formal_missing_flags": formal_missing_flags,
        "old_supported": old_supported,
        "old_missing_flags": old_missing_flags,
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
        "# Fixed Candidate Candidate-Audit Command Plan",
        "",
        "Command-plan-only artifact. It reads readiness inputs and does not execute candidate audit, validation, backtests, timeout review, diagnostics, model work, database mutation, or external actions.",
        "No candidate-quality conclusion or trading decision was made.",
        "",
        "## Readiness Gate",
        "",
        f"- candidate_audit_readiness_dir: `{args.candidate_audit_readiness_dir}`",
        f"- readiness_blockers_present: `{str(metadata['readiness_blockers_present']).lower()}`",
        "",
        "## Preferred Path",
        "",
        f"- preferred_next_artifact: `build_fixed_candidate_formal_candidate_audit_packet.py`",
        f"- formal_audit_packet_script: `{args.formal_audit_packet_script}`",
        f"- formal_audit_packet_script_exists: `{str(Path(args.formal_audit_packet_script).exists()).lower()}`",
        f"- implementation_required_count: `{status_counts.get('implementation_required', 0)}`",
        "",
        "## Legacy Context",
        "",
        "The old candidate audit is context-only because it does not consume the newer fixed-candidate evidence chain.",
        f"- old_candidate_audit_script: `{args.old_candidate_audit_script}`",
        f"- old_candidate_audit_compatibility: `{'compatible_with_new_evidence_chain' if metadata['old_supported'] else 'not_compatible_with_new_evidence_chain'}`",
        "",
        "## Caveats",
        "",
        "- The current candidate must keep risk-filtered candidate framing.",
        "- Manual execution is only appropriate after reviewing this command plan.",
        "- The next step is to implement the formal audit packet module when the script is missing.",
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
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "candidate_audit_readiness_dir": str(args.candidate_audit_readiness_dir),
        "research_review_packet_dir": str(args.research_review_packet_dir),
        "deeper_walkforward_split_review_dir": str(args.deeper_walkforward_split_review_dir),
        "timeout_artifact_review_dir": str(args.timeout_artifact_review_dir),
        "equity_drawdown_sequence_review_dir": str(args.equity_drawdown_sequence_review_dir),
        "old_candidate_audit_dir": str(args.old_candidate_audit_dir),
        "formal_audit_packet_script": str(args.formal_audit_packet_script),
        "old_candidate_audit_script": str(args.old_candidate_audit_script),
        "plan_row_count": len(rows),
        "planned_manual_command_count": statuses.get("planned_manual_command", 0),
        "implementation_required_count": statuses.get("implementation_required", 0),
        "context_only_count": statuses.get("context_only_no_command", 0),
        "blocked_by_readiness_count": statuses.get("blocked_by_readiness", 0),
        "unsupported_by_script_cli_count": statuses.get("unsupported_by_script_cli", 0),
        "missing_script_count": statuses.get("missing_script", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "readiness_blockers_present": bool(metadata["readiness_blockers_present"]),
        "old_candidate_audit_context_only": True,
        "preferred_next_artifact": "build_fixed_candidate_formal_candidate_audit_packet.py",
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
    write_csv(paths["command_plan"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an artifact-only fixed-candidate candidate-audit command plan."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
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
    parser.add_argument("--formal-audit-packet-script", type=Path, default=DEFAULT_FORMAL_AUDIT_PACKET_SCRIPT)
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
        print(f"Fixed-candidate candidate-audit command plan failed: {exc}")
        return 1
    print("Fixed-candidate candidate-audit command plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
