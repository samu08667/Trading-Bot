"""Single-shot fixed-candidate demo signal-to-order pilot orchestrator.

This module is a thin wrapper around the existing safety modules. It does not
import MT5, construct broker payloads itself, poll, schedule, loop, or retry.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
SYMBOL = "GBPUSD"
TIMEFRAME = "M15"
DIRECTION = "short"
SEND_CONFIRMATION = "confirm_single_demo_send_only"
EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT = "acknowledge_expired_signal_for_demo_module_validation_only"
CLIENT_REJECT_RESEND_ACKNOWLEDGMENT = "acknowledge_new_demo_send_after_client_reject_flat_no_position_no_order"

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_signal_to_order_pilot_once"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_signal_to_order_pilot"
DEFAULT_APPROVAL_RECORD_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_manual_approval_record.json"
)

SHADOW_SCRIPT = BASE_DIR / "scripts" / "run_fixed_candidate_demo_shadow_signal_once.py"
PREP_SCRIPT = BASE_DIR / "scripts" / "run_fixed_candidate_demo_manual_approval_prep_pipeline_once.py"
APPROVAL_SCRIPT = BASE_DIR / "scripts" / "create_fixed_candidate_demo_manual_approval_record.py"
REQUEST_SCRIPT = BASE_DIR / "scripts" / "build_fixed_candidate_demo_request_construction_dry_run.py"
ORDER_CHECK_SCRIPT = BASE_DIR / "scripts" / "check_fixed_candidate_demo_order_check.py"
SEND_READINESS_SCRIPT = BASE_DIR / "scripts" / "build_fixed_candidate_demo_order_send_pilot_readiness_plan.py"
SEND_SCRIPT = BASE_DIR / "scripts" / "send_fixed_candidate_demo_order_pilot.py"

SHADOW_MANIFEST = "fixed_candidate_demo_shadow_signal_once_manifest.json"
PREP_MANIFEST = "fixed_candidate_demo_manual_approval_prep_pipeline_manifest.json"
PREP_CHILD_RESULTS = "fixed_candidate_demo_manual_approval_prep_pipeline_child_results.csv"
PREP_WARNINGS = "fixed_candidate_demo_manual_approval_prep_pipeline_warnings.csv"
PREP_APPROVAL_DRY_RUN_STEP_DIR = "15_approval_record_creation_dry_run"
APPROVAL_WARNINGS = "fixed_candidate_demo_manual_approval_record_creation_warnings.csv"
APPROVAL_STATUS = "fixed_candidate_demo_manual_approval_record_creation_status.csv"
APPROVAL_MANIFEST = "fixed_candidate_demo_manual_approval_record_creation_manifest.json"
REQUEST_MANIFEST = "fixed_candidate_demo_request_construction_dry_run_manifest.json"
ORDER_CHECK_MANIFEST = "fixed_candidate_demo_order_check_manifest.json"
SEND_READINESS_MANIFEST = "fixed_candidate_demo_order_send_pilot_readiness_plan_manifest.json"
SEND_MANIFEST = "fixed_candidate_demo_order_send_pilot_manifest.json"
SEND_RESULT = "fixed_candidate_demo_order_send_pilot_send_result_snapshot.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_signal_to_order_pilot_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_signal_to_order_pilot_report.md"
OUTPUT_STATUS = "fixed_candidate_demo_signal_to_order_pilot_status.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_signal_to_order_pilot_warnings.csv"
OUTPUT_CHILD_COMMANDS = "fixed_candidate_demo_signal_to_order_pilot_child_commands.csv"
OUTPUT_CHILD_RESULTS = "fixed_candidate_demo_signal_to_order_pilot_child_results.csv"
OUTPUT_NO_ORDER_UNTIL_SEND = "fixed_candidate_demo_signal_to_order_pilot_no_order_until_send_evidence.csv"
OUTPUT_FINAL_EXECUTION = "fixed_candidate_demo_signal_to_order_pilot_final_execution_evidence.csv"
OUTPUT_IDEMPOTENCY_JSON = "fixed_candidate_demo_signal_to_order_pilot_idempotency_summary.json"
OUTPUT_IDEMPOTENCY_CSV = "fixed_candidate_demo_signal_to_order_pilot_idempotency_summary.csv"
OUTPUT_BROKER_RESPONSE = "fixed_candidate_demo_signal_to_order_pilot_broker_response_redacted.json"
OUTPUT_FINAL_STATE_JSON = "fixed_candidate_demo_signal_to_order_pilot_final_state_summary.json"
OUTPUT_FINAL_STATE_CSV = "fixed_candidate_demo_signal_to_order_pilot_final_state_summary.csv"

REQUEST_AVAILABLE_STATUSES = {
    "request_construction_dry_run_available_non_executable",
    "request_construction_dry_run_available_with_stale_override_for_demo_module_validation",
}
SUCCESS_SEND_STATUSES = {
    "order_send_pilot_sent_success_deal_reconciliation_required",
    "order_send_pilot_sent_success_placed_reconciliation_required",
}
DUPLICATE_OR_IDEMPOTENCY_SEND_STATUSES = {
    "order_send_pilot_blocked_existing_active_idempotency_key",
    "order_send_pilot_blocked_future_state_incompatible",
    "order_send_pilot_blocked_duplicate_protection",
}

WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
CHILD_COMMAND_FIELDNAMES = ["run_id", "step_index", "step_name", "command", "output_dir", "manifest_path"]
CHILD_RESULT_FIELDNAMES = [
    "run_id",
    "step_index",
    "step_name",
    "returncode",
    "child_status",
    "manifest_status",
    "manifest_path",
    "stdout_tail",
    "stderr_tail",
]
STATUS_FIELDNAMES = [
    "run_id",
    "final_status",
    "signal_id",
    "idempotency_key",
    "order_check_called",
    "order_check_passed",
    "order_send_called",
    "order_send_attempt_count",
    "order_send_result_status",
]


def utc_now_text() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def output_dir_for(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "status": output_dir / OUTPUT_STATUS,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "child_commands": output_dir / OUTPUT_CHILD_COMMANDS,
        "child_results": output_dir / OUTPUT_CHILD_RESULTS,
        "no_order_until_send": output_dir / OUTPUT_NO_ORDER_UNTIL_SEND,
        "final_execution": output_dir / OUTPUT_FINAL_EXECUTION,
        "idempotency_json": output_dir / OUTPUT_IDEMPOTENCY_JSON,
        "idempotency_csv": output_dir / OUTPUT_IDEMPOTENCY_CSV,
        "broker_response": output_dir / OUTPUT_BROKER_RESPONSE,
        "final_state_json": output_dir / OUTPUT_FINAL_STATE_JSON,
        "final_state_csv": output_dir / OUTPUT_FINAL_STATE_CSV,
    }


def stage_dirs(output_dir: Path) -> dict[str, Path]:
    return {
        "shadow": output_dir / "01_shadow_signal_once",
        "prep": output_dir / "02_manual_approval_prep_pipeline",
        "approval": output_dir / "03_approval_record_creation_real",
        "request": output_dir / "04_request_construction_dry_run",
        "order_check": output_dir / "05_order_check",
        "send_readiness": output_dir / "06_order_send_readiness",
        "send": output_dir / "07_order_send_pilot",
    }


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def tail(text: str, limit: int = 600) -> str:
    return text[-limit:] if len(text) > limit else text


def command_text(command: list[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in command])


def run_child_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command],
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
        shell=False,
        check=False,
    )


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
    warning_code: str,
    message: str,
    source: str | Path,
    blocking: bool = True,
    severity: str = "error",
) -> None:
    warnings.append(
        {
            "run_id": args.run_id,
            "warning_code": warning_code,
            "severity": severity,
            "message": message,
            "source": str(source),
            "blocking_warning": bool_text(blocking),
        }
    )


def manifest_status(step_name: str, manifest: dict[str, Any]) -> str:
    keys = {
        "shadow_signal": "shadow_status",
        "manual_approval_prep": "pipeline_status",
        "approval_record_creation": "creation_status",
        "request_construction": "request_construction_status",
        "order_check": "order_check_status",
        "send_readiness": "order_send_pilot_readiness_status",
        "order_send": "order_send_pilot_status",
    }
    return str(manifest.get(keys.get(step_name, ""), ""))


def child_result_row(
    args: argparse.Namespace,
    *,
    index: int,
    step_name: str,
    completed: subprocess.CompletedProcess[str],
    manifest_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "step_index": index,
        "step_name": step_name,
        "returncode": completed.returncode,
        "child_status": "success" if completed.returncode == 0 and manifest_path.exists() else "failed",
        "manifest_status": manifest_status(step_name, manifest),
        "manifest_path": str(manifest_path),
        "stdout_tail": tail(completed.stdout or ""),
        "stderr_tail": tail(completed.stderr or ""),
    }


def failed_child_result_row(
    args: argparse.Namespace,
    *,
    index: int,
    step_name: str,
    manifest_path: Path,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "step_index": index,
        "step_name": step_name,
        "returncode": "exception",
        "child_status": "failed",
        "manifest_status": "",
        "manifest_path": str(manifest_path),
        "stdout_tail": "",
        "stderr_tail": str(exc),
    }


def run_step(
    args: argparse.Namespace,
    ctx: dict[str, Any],
    *,
    index: int,
    step_name: str,
    command: list[str],
    output_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    ctx["child_commands"].append(
        {
            "run_id": args.run_id,
            "step_index": index,
            "step_name": step_name,
            "command": command_text(command),
            "output_dir": str(output_dir),
            "manifest_path": str(manifest_path),
        }
    )
    try:
        completed = run_child_command(command)
    except Exception as exc:
        ctx["child_results"].append(
            failed_child_result_row(args, index=index, step_name=step_name, manifest_path=manifest_path, exc=exc)
        )
        raise
    manifest = read_json(manifest_path)
    ctx["child_results"].append(
        child_result_row(
            args,
            index=index,
            step_name=step_name,
            completed=completed,
            manifest_path=manifest_path,
            manifest=manifest,
        )
    )
    return manifest


def child_base_command(script: Path, run_id: str, output_dir: Path) -> list[str]:
    return [sys.executable, str(script), "--run-id", run_id, "--output-dir", str(output_dir), "--overwrite"]


def path_from_manifest(manifest: dict[str, Any], key: str) -> Path:
    value = manifest.get(key, "")
    return Path(str(value)) if value else Path()


def bound_digest_dir(record: dict[str, Any], key: str, fallback: Path) -> Path:
    bound = record.get("bound_upstream_artifact_digests", {})
    if isinstance(bound, dict):
        entry = bound.get(key, {})
        if isinstance(entry, dict) and entry.get("path"):
            return Path(str(entry["path"])).parent
    return fallback


def repo_path(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    return BASE_DIR / path


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def row_indicates_existing_active_approval(row: dict[str, str]) -> bool:
    warning_code = str(row.get("warning_code", "")).strip().lower()
    row_text = json.dumps(row, sort_keys=True).lower()
    has_existing_marker = (
        "existing_active_approval_record" in row_text
        or "existing active approval record" in row_text
    )
    if warning_code == "blocked_existing_active_approval_record":
        return True
    if "blocked_existing_active_approval_record" in row_text:
        return True
    if not has_existing_marker:
        return False
    blocking_flag = str(
        row.get("blocking_warning", row.get("is_blocking", row.get("blocking", "")))
    ).strip().lower()
    if blocking_flag in {"1", "true", "yes", "y"}:
        return True
    for key in ("warning_code", "status", "creation_status", "manifest_status", "child_status"):
        if str(row.get(key, "")).strip().lower().startswith("blocked"):
            return True
    severity = str(row.get("severity", "")).strip().lower()
    message = str(row.get("message", "")).strip().lower()
    return severity in {"error", "critical"} and "gate failed" in message


def text_indicates_existing_active_approval(text: str) -> bool:
    lowered = text.lower()
    if "blocked_existing_active_approval_record" in lowered:
        return True
    has_existing_marker = (
        "existing_active_approval_record" in lowered
        or "existing active approval record" in lowered
    )
    blocking_tokens = (
        '"blocking_warning": true',
        '"is_blocking": true',
        '"blocking": true',
        '"warning_code": "blocked',
        '"status": "blocked',
        '"creation_status": "blocked',
        '"manifest_status": "blocked',
        '"child_status": "blocked',
    )
    return has_existing_marker and any(token in lowered for token in blocking_tokens)


def artifact_indicates_existing_active_approval(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if path.suffix.lower() == ".csv":
        rows = read_csv_rows(path)
        if rows:
            return any(row_indicates_existing_active_approval(row) for row in rows)
    text = path.read_text(encoding="utf-8", errors="replace")
    return text_indicates_existing_active_approval(text)


def prep_approval_step_dirs(prep: dict[str, Any], prep_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    for key in (
        "approval_record_creation_dry_run_dir",
        "manual_approval_record_creation_dry_run_dir",
        "approval_record_creation_dir",
    ):
        path = repo_path(prep.get(key))
        if path is not None:
            dirs.append(path)

    for row in read_csv_rows(prep_dir / PREP_CHILD_RESULTS):
        row_text = json.dumps(row, sort_keys=True).lower()
        if "approval_record_creation" not in row_text and "approval_dry_run" not in row_text:
            continue
        for key in ("manifest_path", "manifest_json", "output_dir", "child_output_dir", "report_dir"):
            path = repo_path(row.get(key, ""))
            if path is None:
                continue
            dirs.append(path.parent if path.suffix else path)

    dirs.append(prep_dir / PREP_APPROVAL_DRY_RUN_STEP_DIR)
    return unique_paths(dirs)


def prep_existing_active_approval_primary_files(prep: dict[str, Any], prep_dir: Path) -> list[Path]:
    paths = [
        prep_dir / PREP_CHILD_RESULTS,
        prep_dir / PREP_WARNINGS,
    ]
    for step_dir in prep_approval_step_dirs(prep, prep_dir):
        paths.extend(
            [
                step_dir / APPROVAL_WARNINGS,
                step_dir / APPROVAL_STATUS,
                step_dir / APPROVAL_MANIFEST,
            ]
        )
    return unique_paths(paths)


def prep_blocked_existing_active_approval(prep: dict[str, Any], prep_dir: Path) -> bool:
    if prep.get("pipeline_status") != "manual_approval_prep_pipeline_blocked_approval_dry_run":
        return False
    if text_indicates_existing_active_approval(json.dumps(prep, sort_keys=True)):
        return True
    primary_paths = prep_existing_active_approval_primary_files(prep, prep_dir)
    if any(artifact_indicates_existing_active_approval(path) for path in primary_paths):
        return True
    if not prep_dir.exists():
        return False
    primary_keys = {str(path) for path in primary_paths}
    for path in prep_dir.rglob("*"):
        if str(path) in primary_keys or path.suffix.lower() not in {".csv", ".json"}:
            continue
        if artifact_indicates_existing_active_approval(path):
            return True
    return False


def validate_existing_approval_record(record: dict[str, Any]) -> tuple[bool, str]:
    checks = {
        "approval_status": record.get("approval_status") == "approved_for_future_request_construction_only",
        "approval_scope": record.get("approval_scope") == "future_request_construction_only",
        "approval_revoked": record.get("approval_revoked") is False,
        "signal_id": bool(record.get("signal_id")),
        "idempotency_key": bool(record.get("idempotency_key")),
        "digest_binding_verified": record.get("digest_binding_verified") is True,
        "approval_does_not_construct_request": record.get("approval_does_not_construct_request") is True,
        "approval_does_not_execute_order": record.get("approval_does_not_execute_order") is True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return not failed, ",".join(failed)


def append_resume_child_result(args: argparse.Namespace, ctx: dict[str, Any], approval_record_path: Path, status: str) -> None:
    ctx["child_results"].append(
        {
            "run_id": args.run_id,
            "step_index": 3,
            "step_name": "resume_existing_active_approval_record",
            "returncode": "not_run",
            "child_status": "resumed" if status == "valid_existing_active_approval_record" else "failed",
            "manifest_status": status,
            "manifest_path": str(approval_record_path),
            "stdout_tail": "",
            "stderr_tail": "",
        }
    )


def request_stop_requested(args: argparse.Namespace) -> bool:
    return bool(args.stop_after_request_construction)


def order_check_stop_requested(args: argparse.Namespace) -> bool:
    return bool(args.stop_after_order_check or args.stop_before_order_send)


def can_reach_order_check(args: argparse.Namespace) -> bool:
    return not request_stop_requested(args)


def can_reach_order_send(args: argparse.Namespace) -> bool:
    return not request_stop_requested(args) and not order_check_stop_requested(args)


def expired_signal_override_requested(args: argparse.Namespace) -> bool:
    return bool(args.allow_expired_signal_for_demo_module_validation or args.expired_signal_override_acknowledgment)


def expired_signal_override_allowed(args: argparse.Namespace) -> bool:
    return (
        args.module_validation_demo_execution is True
        and args.allow_expired_signal_for_demo_module_validation is True
        and args.expired_signal_override_acknowledgment == EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT
    )


def preflight_block(args: argparse.Namespace, ctx: dict[str, Any]) -> str:
    if expired_signal_override_requested(args) and not expired_signal_override_allowed(args):
        add_warning(
            ctx["warnings"],
            args=args,
            warning_code="invalid_expired_signal_override",
            message=(
                "Expired signal override requires --module-validation-demo-execution, "
                "--allow-expired-signal-for-demo-module-validation, and the exact acknowledgment."
            ),
            source="orchestrator_cli",
        )
        return "demo_signal_to_order_pilot_blocked_manual_approval_prep"
    if can_reach_order_check(args) and not args.demo_account_only:
        add_warning(
            ctx["warnings"],
            args=args,
            warning_code="demo_account_only_required",
            message="--demo-account-only is required before order_check/order_send paths.",
            source="orchestrator_cli",
        )
        return "demo_signal_to_order_pilot_blocked_non_demo_account"
    if can_reach_order_send(args) and args.operator_final_acknowledgment != SEND_CONFIRMATION:
        add_warning(
            ctx["warnings"],
            args=args,
            warning_code="operator_final_acknowledgment_required",
            message=f"--operator-final-acknowledgment must be {SEND_CONFIRMATION} before order_send.",
            source="orchestrator_cli",
        )
        return "demo_signal_to_order_pilot_blocked_order_send_result"
    return ""


def approval_record_path_from_manifest(manifest: dict[str, Any]) -> Path:
    return Path(str(manifest.get("future_approval_record_json") or ""))


def map_send_status(status: str) -> str:
    if status in SUCCESS_SEND_STATUSES:
        return "demo_signal_to_order_pilot_completed_order_sent"
    if status == "order_send_pilot_blocked_non_demo_account":
        return "demo_signal_to_order_pilot_blocked_non_demo_account"
    if status in DUPLICATE_OR_IDEMPOTENCY_SEND_STATUSES:
        return "demo_signal_to_order_pilot_blocked_duplicate_or_idempotency"
    if status in {
        "order_send_pilot_blocked_broker_local_reconciliation",
        "order_send_pilot_blocked_duplicate_protection",
        "order_send_pilot_blocked_existing_active_idempotency_key",
    }:
        return "demo_signal_to_order_pilot_blocked_duplicate_or_idempotency"
    return "demo_signal_to_order_pilot_blocked_order_send_result"


def update_identity_from_manifest(ctx: dict[str, Any], manifest: dict[str, Any]) -> None:
    for key in ("signal_id", "idempotency_key"):
        if manifest.get(key):
            ctx[key] = manifest[key]


def execute(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    dirs = stage_dirs(output_dir)
    ctx: dict[str, Any] = {
        "warnings": [],
        "child_commands": [],
        "child_results": [],
        "module_validation_demo_execution": bool(args.module_validation_demo_execution),
        "strategy_valid": not bool(args.module_validation_demo_execution),
        "production_valid": not bool(args.module_validation_demo_execution),
        "stale_override_used": False,
        "expired_signal_override_used": False,
        "demo_account_verified": False,
        "request_construction_performed": False,
        "order_check_called": False,
        "order_check_passed": False,
        "order_send_called": False,
        "order_send_attempt_count": 0,
        "order_send_result_status": "",
        "order_ticket": "",
        "order_execution_performed": False,
        "signal_id": "",
        "idempotency_key": "",
        "approval_record_json": "",
        "resumed_existing_active_approval_record": False,
        "resume_reason": "",
        "final_status": "",
        "manifests": {},
    }
    block_status = preflight_block(args, ctx)
    if block_status:
        ctx["final_status"] = block_status
        return ctx

    shadow_manifest_path = dirs["shadow"] / SHADOW_MANIFEST
    shadow_command = child_base_command(SHADOW_SCRIPT, f"{args.run_id}_shadow_signal", dirs["shadow"])
    shadow_command.append("--run-cycle")
    shadow = run_step(
        args,
        ctx,
        index=1,
        step_name="shadow_signal",
        command=shadow_command,
        output_dir=dirs["shadow"],
        manifest_path=shadow_manifest_path,
    )
    ctx["manifests"]["shadow"] = shadow
    update_identity_from_manifest(ctx, shadow)
    if shadow.get("shadow_status") != "shadow_signal_detected":
        ctx["final_status"] = "demo_signal_to_order_pilot_blocked_no_valid_signal"
        return ctx

    prep_manifest_path = dirs["prep"] / PREP_MANIFEST
    prep_command = child_base_command(PREP_SCRIPT, f"{args.run_id}_manual_approval_prep", dirs["prep"])
    prep_command.extend(
        [
            "--shadow-signal-dir",
            str(dirs["shadow"]),
            "--operator-decision-label",
            "approve_for_future_request_construction_only",
            "--operator-identity-ref",
            args.operator_identity_ref,
            "--operator-warning-acknowledgment",
            args.operator_final_acknowledgment or "operator_acknowledges_demo_pilot_risks",
            "--allow-broker-read-checks",
        ]
    )
    if args.module_validation_demo_execution:
        prep_command.append("--module-validation-demo-execution")
    if args.allow_expired_signal_for_demo_module_validation:
        prep_command.append("--allow-expired-signal-for-demo-module-validation")
    if args.expired_signal_override_acknowledgment:
        prep_command.extend(
            [
                "--expired-signal-override-acknowledgment",
                args.expired_signal_override_acknowledgment,
            ]
        )
    prep = run_step(
        args,
        ctx,
        index=2,
        step_name="manual_approval_prep",
        command=prep_command,
        output_dir=dirs["prep"],
        manifest_path=prep_manifest_path,
    )
    ctx["manifests"]["prep"] = prep
    if prep.get("expired_signal_override_used") is True:
        ctx["expired_signal_override_used"] = True
        ctx["strategy_valid"] = False
        ctx["production_valid"] = False
    prep_ok = (
        prep.get("pipeline_status")
        == "manual_approval_prep_pipeline_completed_dry_run_ready_for_manual_real_approval_decision"
        and int(prep.get("blocking_warnings_count") or 0) == 0
    )
    approval_record_path = Path()
    approval_record: dict[str, Any] = {}
    if not prep_ok:
        if args.resume_existing_active_approval_record and prep_blocked_existing_active_approval(prep, dirs["prep"]):
            approval_record_path = DEFAULT_APPROVAL_RECORD_JSON
            approval_record = read_json(approval_record_path)
            record_ok, record_error = validate_existing_approval_record(approval_record)
            append_resume_child_result(
                args,
                ctx,
                approval_record_path,
                "valid_existing_active_approval_record" if record_ok else f"invalid_existing_active_approval_record:{record_error}",
            )
            if not record_ok:
                add_warning(
                    ctx["warnings"],
                    args=args,
                    warning_code="invalid_existing_active_approval_record",
                    message=f"Existing active approval record failed resume validation: {record_error}",
                    source=approval_record_path,
                )
                ctx["final_status"] = "demo_signal_to_order_pilot_blocked_approval_record_creation"
                return ctx
            ctx["approval_record_json"] = str(approval_record_path)
            ctx["resumed_existing_active_approval_record"] = True
            ctx["resume_reason"] = "existing_active_approval_record"
            update_identity_from_manifest(ctx, approval_record)
        else:
            ctx["final_status"] = "demo_signal_to_order_pilot_blocked_manual_approval_prep"
            return ctx
    else:
        approval_manifest_path = dirs["approval"] / APPROVAL_MANIFEST
        approval_command = child_base_command(APPROVAL_SCRIPT, f"{args.run_id}_approval_record_creation", dirs["approval"])
        approval_command.extend(
            [
                "--manual-approval-gate-dry-run-dir",
                str(path_from_manifest(prep, "manual_approval_gate_dry_run_dir")),
                "--would-signal-review-dir",
                str(path_from_manifest(prep, "would_signal_review_dir")),
                "--live-signal-freshness-dir",
                str(path_from_manifest(prep, "live_signal_freshness_dir")),
                "--broker-local-reconciliation-dir",
                str(path_from_manifest(prep, "broker_local_reconciliation_dir")),
                "--broker-safe-margin-validation-dir",
                str(path_from_manifest(prep, "broker_safe_margin_validation_dir")),
                "--duplicate-protection-plan-dir",
                str(path_from_manifest(prep, "duplicate_protection_plan_dir")),
                "--manual-approval-kill-switch-plan-dir",
                str(path_from_manifest(prep, "manual_approval_kill_switch_plan_dir")),
                "--future-request-readiness-plan-dir",
                str(path_from_manifest(prep, "future_request_construction_readiness_plan_dir")),
                "--operator-decision-label",
                "approve_for_future_request_construction_only",
                "--operator-identity-ref",
                args.operator_identity_ref,
                "--operator-warning-acknowledgment",
                args.operator_final_acknowledgment or "operator_acknowledges_demo_pilot_risks",
            ]
        )
        if args.module_validation_demo_execution:
            approval_command.append("--module-validation-demo-execution")
        if args.allow_expired_signal_for_demo_module_validation:
            approval_command.append("--allow-expired-signal-for-demo-module-validation")
        if args.expired_signal_override_acknowledgment:
            approval_command.extend(
                [
                    "--expired-signal-override-acknowledgment",
                    args.expired_signal_override_acknowledgment,
                ]
            )
        approval = run_step(
            args,
            ctx,
            index=3,
            step_name="approval_record_creation",
            command=approval_command,
            output_dir=dirs["approval"],
            manifest_path=approval_manifest_path,
        )
        ctx["manifests"]["approval"] = approval
        update_identity_from_manifest(ctx, approval)
        if approval.get("expired_signal_override_used") is True:
            ctx["expired_signal_override_used"] = True
            ctx["strategy_valid"] = False
            ctx["production_valid"] = False
        approval_record_path = approval_record_path_from_manifest(approval)
        ctx["approval_record_json"] = str(approval_record_path)
        if (
            approval.get("creation_status") != "manual_approval_record_created_for_future_request_construction_only"
            or approval.get("approval_record_created") is not True
            or approval.get("approval_scope") != "future_request_construction_only"
            or not approval.get("future_approval_record_json")
        ):
            ctx["final_status"] = "demo_signal_to_order_pilot_blocked_approval_record_creation"
            return ctx
        approval_record = read_json(approval_record_path)
    request_manifest_path = dirs["request"] / REQUEST_MANIFEST
    request_command = child_base_command(REQUEST_SCRIPT, f"{args.run_id}_request_construction", dirs["request"])
    request_command.extend(
        [
            "--manual-approval-record-json",
            str(approval_record_path),
            "--future-request-readiness-plan-dir",
            str(
                bound_digest_dir(
                    approval_record,
                    "future_request_readiness_plan_manifest",
                    path_from_manifest(prep, "future_request_construction_readiness_plan_dir"),
                )
            ),
            "--broker-local-reconciliation-dir",
            str(
                bound_digest_dir(
                    approval_record,
                    "broker_local_reconciliation_manifest",
                    path_from_manifest(prep, "broker_local_reconciliation_dir"),
                )
            ),
            "--broker-safe-margin-validation-dir",
            str(
                bound_digest_dir(
                    approval_record,
                    "broker_safe_margin_validation_manifest",
                    path_from_manifest(prep, "broker_safe_margin_validation_dir"),
                )
            ),
            "--live-signal-freshness-dir",
            str(
                bound_digest_dir(
                    approval_record,
                    "live_signal_freshness_manifest",
                    path_from_manifest(prep, "live_signal_freshness_dir"),
                )
            ),
            "--duplicate-protection-plan-dir",
            str(
                bound_digest_dir(
                    approval_record,
                    "duplicate_protection_plan_manifest",
                    path_from_manifest(prep, "duplicate_protection_plan_dir"),
                )
            ),
            "--manual-approval-kill-switch-plan-dir",
            str(
                bound_digest_dir(
                    approval_record,
                    "manual_approval_kill_switch_plan_manifest",
                    path_from_manifest(prep, "manual_approval_kill_switch_plan_dir"),
                )
            ),
        ]
    )
    if args.module_validation_demo_execution:
        request_command.append("--module-validation-demo-execution")
    if args.allow_stale_upstream_artifacts_for_demo_module_validation:
        request_command.append("--allow-stale-upstream-artifacts-for-demo-module-validation")
    if args.module_validation_acknowledgment:
        request_command.extend(["--module-validation-acknowledgment", args.module_validation_acknowledgment])
    if args.allow_expired_signal_for_demo_module_validation:
        request_command.append("--allow-expired-signal-for-demo-module-validation")
    if args.expired_signal_override_acknowledgment:
        request_command.extend(
            [
                "--expired-signal-override-acknowledgment",
                args.expired_signal_override_acknowledgment,
            ]
        )
    if args.allow_new_demo_send_after_client_reject_flat:
        request_command.append("--allow-new-demo-send-after-client-reject-flat")
    if args.client_reject_resend_acknowledgment:
        request_command.extend(["--client-reject-resend-acknowledgment", args.client_reject_resend_acknowledgment])
    request = run_step(
        args,
        ctx,
        index=4,
        step_name="request_construction",
        command=request_command,
        output_dir=dirs["request"],
        manifest_path=request_manifest_path,
    )
    ctx["manifests"]["request"] = request
    update_identity_from_manifest(ctx, request)
    ctx["request_construction_performed"] = True
    ctx["stale_override_used"] = bool(request.get("stale_override_used"))
    ctx["expired_signal_override_used"] = bool(
        ctx.get("expired_signal_override_used") or request.get("expired_signal_override_used")
    )
    ctx["request_stale_artifact_count"] = request.get("stale_artifact_count", "")
    ctx["request_blocking_stale_artifact_count"] = request.get("blocking_stale_artifact_count", "")
    ctx["request_fresh_artifact_dirs"] = {
        "future_request_readiness_plan_dir": str(
            bound_digest_dir(
                approval_record,
                "future_request_readiness_plan_manifest",
                path_from_manifest(prep, "future_request_construction_readiness_plan_dir"),
            )
        ),
        "broker_local_reconciliation_dir": str(
            bound_digest_dir(
                approval_record,
                "broker_local_reconciliation_manifest",
                path_from_manifest(prep, "broker_local_reconciliation_dir"),
            )
        ),
        "broker_safe_margin_validation_dir": str(
            bound_digest_dir(
                approval_record,
                "broker_safe_margin_validation_manifest",
                path_from_manifest(prep, "broker_safe_margin_validation_dir"),
            )
        ),
        "live_signal_freshness_dir": str(
            bound_digest_dir(
                approval_record,
                "live_signal_freshness_manifest",
                path_from_manifest(prep, "live_signal_freshness_dir"),
            )
        ),
        "duplicate_protection_plan_dir": str(
            bound_digest_dir(
                approval_record,
                "duplicate_protection_plan_manifest",
                path_from_manifest(prep, "duplicate_protection_plan_dir"),
            )
        ),
        "manual_approval_kill_switch_plan_dir": str(
            bound_digest_dir(
                approval_record,
                "manual_approval_kill_switch_plan_manifest",
                path_from_manifest(prep, "manual_approval_kill_switch_plan_dir"),
            )
        ),
    }
    ctx["explicit_new_signal_after_market_closed_flat"] = bool(
        request.get("explicit_new_signal_after_market_closed_flat")
    )
    if request.get("previous_send_retcode") not in (None, ""):
        ctx["previous_send_retcode"] = request.get("previous_send_retcode", "")
    if request.get("previous_state_status") not in (None, ""):
        ctx["previous_state_status"] = request.get("previous_state_status", "")
    if args.module_validation_demo_execution or ctx["stale_override_used"] or ctx["expired_signal_override_used"]:
        ctx["strategy_valid"] = False
        ctx["production_valid"] = False
    if (
        request.get("request_construction_status") not in REQUEST_AVAILABLE_STATUSES
        or request.get("broker_payload_constructed") is not False
        or request.get("executable_order_object_constructed") is not False
        or request.get("order_check_called") is not False
        or request.get("order_send_called") is not False
    ):
        ctx["final_status"] = "demo_signal_to_order_pilot_blocked_request_construction"
        return ctx
    if args.stop_after_request_construction:
        ctx["final_status"] = "demo_signal_to_order_pilot_completed_stopped_after_request_construction"
        return ctx

    order_check_manifest_path = dirs["order_check"] / ORDER_CHECK_MANIFEST
    order_check_command = child_base_command(ORDER_CHECK_SCRIPT, f"{args.run_id}_order_check", dirs["order_check"])
    order_check_command.extend(
        [
            "--request-construction-dry-run-dir",
            str(dirs["request"]),
            "--manual-approval-record-json",
            str(approval_record_path),
            "--broker-local-reconciliation-dir",
            str(path_from_manifest(prep, "broker_local_reconciliation_dir")),
            "--broker-safe-margin-validation-dir",
            str(path_from_manifest(prep, "broker_safe_margin_validation_dir")),
            "--live-signal-freshness-dir",
            str(path_from_manifest(prep, "live_signal_freshness_dir")),
            "--duplicate-protection-plan-dir",
            str(path_from_manifest(prep, "duplicate_protection_plan_dir")),
            "--manual-approval-kill-switch-plan-dir",
            str(path_from_manifest(prep, "manual_approval_kill_switch_plan_dir")),
            "--allow-real-order-check",
        ]
    )
    if args.module_validation_demo_execution:
        order_check_command.append("--module-validation-demo-execution")
    if args.module_validation_acknowledgment:
        order_check_command.extend(["--module-validation-acknowledgment", args.module_validation_acknowledgment])
    if args.allow_expired_signal_for_demo_module_validation:
        order_check_command.append("--allow-expired-signal-for-demo-module-validation")
    if args.expired_signal_override_acknowledgment:
        order_check_command.extend(
            [
                "--expired-signal-override-acknowledgment",
                args.expired_signal_override_acknowledgment,
            ]
        )
    if args.allow_new_demo_send_after_client_reject_flat:
        order_check_command.append("--allow-new-demo-send-after-client-reject-flat")
    if args.client_reject_resend_acknowledgment:
        order_check_command.extend(["--client-reject-resend-acknowledgment", args.client_reject_resend_acknowledgment])
    order_check = run_step(
        args,
        ctx,
        index=5,
        step_name="order_check",
        command=order_check_command,
        output_dir=dirs["order_check"],
        manifest_path=order_check_manifest_path,
    )
    ctx["manifests"]["order_check"] = order_check
    update_identity_from_manifest(ctx, order_check)
    ctx["expired_signal_override_used"] = bool(
        ctx.get("expired_signal_override_used") or order_check.get("expired_signal_override_used")
    )
    if args.module_validation_demo_execution or order_check.get("module_validation_demo_execution") is True:
        ctx["module_validation_demo_execution"] = True
        ctx["strategy_valid"] = False
        ctx["production_valid"] = False
    ctx["order_check_called"] = bool(order_check.get("order_check_called"))
    ctx["order_check_passed"] = bool(order_check.get("order_check_passed"))
    ctx["demo_account_verified"] = order_check.get("order_check_status") != "order_check_blocked_non_demo_account"
    if order_check.get("order_check_status") == "order_check_blocked_non_demo_account":
        ctx["final_status"] = "demo_signal_to_order_pilot_blocked_non_demo_account"
        return ctx
    if order_check.get("order_check_status") != "order_check_available_passed_no_send":
        ctx["final_status"] = "demo_signal_to_order_pilot_blocked_order_check"
        return ctx
    if args.stop_after_order_check or args.stop_before_order_send:
        ctx["final_status"] = "demo_signal_to_order_pilot_completed_stopped_after_order_check"
        return ctx

    readiness_manifest_path = dirs["send_readiness"] / SEND_READINESS_MANIFEST
    readiness_command = child_base_command(SEND_READINESS_SCRIPT, f"{args.run_id}_send_readiness", dirs["send_readiness"])
    readiness_command.extend(
        [
            "--order-check-dir",
            str(dirs["order_check"]),
            "--request-construction-dry-run-dir",
            str(dirs["request"]),
            "--manual-approval-record-json",
            str(approval_record_path),
            "--broker-local-reconciliation-dir",
            str(path_from_manifest(prep, "broker_local_reconciliation_dir")),
            "--broker-safe-margin-validation-dir",
            str(path_from_manifest(prep, "broker_safe_margin_validation_dir")),
            "--live-signal-freshness-dir",
            str(path_from_manifest(prep, "live_signal_freshness_dir")),
            "--duplicate-protection-plan-dir",
            str(path_from_manifest(prep, "duplicate_protection_plan_dir")),
            "--manual-approval-kill-switch-plan-dir",
            str(path_from_manifest(prep, "manual_approval_kill_switch_plan_dir")),
            "--future-request-readiness-plan-dir",
            str(path_from_manifest(prep, "future_request_construction_readiness_plan_dir")),
        ]
    )
    if args.module_validation_demo_execution:
        readiness_command.append("--module-validation-demo-execution")
    if args.allow_stale_upstream_artifacts_for_demo_module_validation:
        readiness_command.append("--allow-stale-upstream-artifacts-for-demo-module-validation")
    if args.module_validation_acknowledgment:
        readiness_command.extend(["--module-validation-acknowledgment", args.module_validation_acknowledgment])
    if args.allow_expired_signal_for_demo_module_validation:
        readiness_command.append("--allow-expired-signal-for-demo-module-validation")
    if args.expired_signal_override_acknowledgment:
        readiness_command.extend(
            [
                "--expired-signal-override-acknowledgment",
                args.expired_signal_override_acknowledgment,
            ]
        )
    if args.allow_new_demo_send_after_client_reject_flat:
        readiness_command.append("--allow-new-demo-send-after-client-reject-flat")
    if args.client_reject_resend_acknowledgment:
        readiness_command.extend(["--client-reject-resend-acknowledgment", args.client_reject_resend_acknowledgment])
    readiness = run_step(
        args,
        ctx,
        index=6,
        step_name="send_readiness",
        command=readiness_command,
        output_dir=dirs["send_readiness"],
        manifest_path=readiness_manifest_path,
    )
    ctx["manifests"]["send_readiness"] = readiness
    if readiness.get("order_send_pilot_readiness_status") != "order_send_pilot_readiness_plan_available_no_send":
        ctx["final_status"] = "demo_signal_to_order_pilot_blocked_send_readiness"
        return ctx

    send_manifest_path = dirs["send"] / SEND_MANIFEST
    send_command = child_base_command(SEND_SCRIPT, f"{args.run_id}_order_send", dirs["send"])
    send_command.extend(
        [
            "--order-send-pilot-readiness-plan-dir",
            str(dirs["send_readiness"]),
            "--order-check-dir",
            str(dirs["order_check"]),
            "--request-construction-dry-run-dir",
            str(dirs["request"]),
            "--manual-approval-record-json",
            str(approval_record_path),
            "--broker-local-reconciliation-dir",
            str(path_from_manifest(prep, "broker_local_reconciliation_dir")),
            "--broker-safe-margin-validation-dir",
            str(path_from_manifest(prep, "broker_safe_margin_validation_dir")),
            "--live-signal-freshness-dir",
            str(path_from_manifest(prep, "live_signal_freshness_dir")),
            "--duplicate-protection-plan-dir",
            str(path_from_manifest(prep, "duplicate_protection_plan_dir")),
            "--manual-approval-kill-switch-plan-dir",
            str(path_from_manifest(prep, "manual_approval_kill_switch_plan_dir")),
            "--allow-real-order-send",
            "--operator-final-send-confirmation",
            args.operator_final_acknowledgment,
            "--max-order-send-attempts",
            str(args.max_order_send_attempts),
        ]
    )
    if args.module_validation_demo_execution:
        send_command.append("--module-validation-demo-execution")
    if args.allow_stale_upstream_artifacts_for_demo_module_validation:
        send_command.append("--allow-stale-upstream-artifacts-for-demo-module-validation")
    if args.module_validation_acknowledgment:
        send_command.extend(["--module-validation-acknowledgment", args.module_validation_acknowledgment])
    if args.allow_expired_signal_for_demo_module_validation:
        send_command.append("--allow-expired-signal-for-demo-module-validation")
    if args.expired_signal_override_acknowledgment:
        send_command.extend(
            [
                "--expired-signal-override-acknowledgment",
                args.expired_signal_override_acknowledgment,
            ]
        )
    if args.allow_new_demo_send_after_client_reject_flat:
        send_command.append("--allow-new-demo-send-after-client-reject-flat")
    if args.client_reject_resend_acknowledgment:
        send_command.extend(["--client-reject-resend-acknowledgment", args.client_reject_resend_acknowledgment])
    send = run_step(
        args,
        ctx,
        index=7,
        step_name="order_send",
        command=send_command,
        output_dir=dirs["send"],
        manifest_path=send_manifest_path,
    )
    ctx["manifests"]["send"] = send
    ctx["order_send_result_status"] = str(send.get("order_send_pilot_status") or "")
    ctx["order_send_called"] = bool(send.get("order_send_called"))
    ctx["order_send_attempt_count"] = int(send.get("order_send_call_count") or 0)
    ctx["order_ticket"] = str(send.get("order_ticket") or send.get("broker_order_ticket") or "")
    ctx["order_execution_performed"] = bool(send.get("order_execution_performed"))
    ctx["explicit_second_demo_send_after_client_reject_flat"] = bool(
        send.get("explicit_second_demo_send_after_client_reject_flat")
    )
    ctx["previous_send_retcode"] = send.get("previous_send_retcode", "")
    ctx["previous_state_status"] = send.get("previous_state_status", "")
    ctx["new_operator_authorized_attempt"] = bool(send.get("new_operator_authorized_attempt"))
    if ctx["order_send_attempt_count"] > 1:
        ctx["final_status"] = "demo_signal_to_order_pilot_blocked_order_send_result"
        return ctx
    ctx["final_status"] = map_send_status(ctx["order_send_result_status"])
    return ctx


def idempotency_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "signal_id": ctx.get("signal_id", ""),
        "idempotency_key": ctx.get("idempotency_key", ""),
        "order_send_attempt_count": ctx.get("order_send_attempt_count", 0),
        "no_retry_performed": True,
        "no_second_order_send_called": bool(int(ctx.get("order_send_attempt_count") or 0) <= 1),
        "final_status": ctx.get("final_status", ""),
    }


def final_state_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    send = ctx.get("manifests", {}).get("send", {})
    return {
        "state_status": send.get("state_status", ""),
        "future_state_json_written": bool(send.get("future_state_json_written", False)),
        "reconciliation_status": send.get("reconciliation_status", ""),
        "order_ticket": ctx.get("order_ticket", ""),
        "final_status": ctx.get("final_status", ""),
    }


def redacted_broker_response(ctx: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    result = read_json(stage_dirs(output_dir)["send"] / SEND_RESULT)
    allowed = {
        "retcode",
        "retcode_name",
        "comment",
        "request_id",
        "order",
        "deal",
        "order_send_result_category",
        "order_send_called",
    }
    return {key: result.get(key, "") for key in sorted(allowed)}


def manifest_payload(args: argparse.Namespace, ctx: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "candidate_id": CANDIDATE_ID,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "direction": DIRECTION,
        "signal_id": ctx.get("signal_id", ""),
        "idempotency_key": ctx.get("idempotency_key", ""),
        "operator_identity_ref": args.operator_identity_ref,
        "module_validation_demo_execution": bool(ctx.get("module_validation_demo_execution")),
        "strategy_valid": bool(ctx.get("strategy_valid")),
        "production_valid": bool(ctx.get("production_valid")),
        "demo_account_verified": bool(ctx.get("demo_account_verified")),
        "stale_override_used": bool(ctx.get("stale_override_used")),
        "expired_signal_override_used": bool(ctx.get("expired_signal_override_used")),
        "request_construction_performed": bool(ctx.get("request_construction_performed")),
        "order_check_called": bool(ctx.get("order_check_called")),
        "order_check_passed": bool(ctx.get("order_check_passed")),
        "order_send_called": bool(ctx.get("order_send_called")),
        "order_send_attempt_count": int(ctx.get("order_send_attempt_count") or 0),
        "order_send_result_status": ctx.get("order_send_result_status", ""),
        "order_ticket": ctx.get("order_ticket", ""),
        "order_execution_performed": bool(ctx.get("order_execution_performed")),
        "explicit_second_demo_send_after_client_reject_flat": bool(
            ctx.get("explicit_second_demo_send_after_client_reject_flat")
        ),
        "explicit_new_signal_after_market_closed_flat": bool(
            ctx.get("explicit_new_signal_after_market_closed_flat")
        ),
        "previous_send_retcode": ctx.get("previous_send_retcode", ""),
        "previous_state_status": ctx.get("previous_state_status", ""),
        "request_stale_artifact_count": ctx.get("request_stale_artifact_count", ""),
        "request_blocking_stale_artifact_count": ctx.get("request_blocking_stale_artifact_count", ""),
        "request_fresh_artifact_dirs": ctx.get("request_fresh_artifact_dirs", {}),
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "new_operator_authorized_attempt": bool(ctx.get("new_operator_authorized_attempt")),
        "resumed_existing_active_approval_record": bool(ctx.get("resumed_existing_active_approval_record")),
        "resume_reason": ctx.get("resume_reason", ""),
        "no_loop_added": True,
        "no_scheduler_added": True,
        "no_retry_performed": True,
        "max_order_send_attempts": int(args.max_order_send_attempts),
        "approval_record_json": ctx.get("approval_record_json", ""),
        "final_status": ctx.get("final_status", ""),
        "warnings_count": len(ctx.get("warnings", [])),
        "blocking_warnings_count": sum(1 for row in ctx.get("warnings", []) if row.get("blocking_warning") == "true"),
        "child_command_count": len(ctx.get("child_commands", [])),
        "child_result_count": len(ctx.get("child_results", [])),
        "created_at_utc": utc_now_text(),
        "output_files": {key: str(value) for key, value in paths.items()},
    }


def status_row(args: argparse.Namespace, ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "final_status": ctx.get("final_status", ""),
        "signal_id": ctx.get("signal_id", ""),
        "idempotency_key": ctx.get("idempotency_key", ""),
        "order_check_called": bool(ctx.get("order_check_called")),
        "order_check_passed": bool(ctx.get("order_check_passed")),
        "order_send_called": bool(ctx.get("order_send_called")),
        "order_send_attempt_count": int(ctx.get("order_send_attempt_count") or 0),
        "order_send_result_status": ctx.get("order_send_result_status", ""),
    }


def no_order_until_send_row(args: argparse.Namespace, ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "request_construction_performed": bool(ctx.get("request_construction_performed")),
        "order_check_called": bool(ctx.get("order_check_called")),
        "order_send_called_before_send_step": False,
        "order_execution_performed_before_send_step": False,
        "broker_payload_constructed_by_orchestrator": False,
        "executable_order_object_constructed_by_orchestrator": False,
        "no_loop_added": True,
        "no_scheduler_added": True,
        "no_retry_performed": True,
    }


def final_execution_row(args: argparse.Namespace, ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "order_send_called": bool(ctx.get("order_send_called")),
        "order_send_attempt_count": int(ctx.get("order_send_attempt_count") or 0),
        "order_execution_performed": bool(ctx.get("order_execution_performed")),
        "order_send_result_status": ctx.get("order_send_result_status", ""),
        "order_ticket": ctx.get("order_ticket", ""),
        "no_retry_performed": True,
        "no_loop_added": True,
        "no_scheduler_added": True,
    }


def write_report(path: Path, args: argparse.Namespace, ctx: dict[str, Any]) -> None:
    lines = [
        "# Fixed Candidate Demo Signal-to-Order Pilot",
        "",
        "Single-shot wrapper over existing fixed-candidate demo safety modules.",
        "",
        "The orchestrator does not import MT5, construct broker payloads, add loops, add schedulers, or retry sends.",
        "",
        "## Result",
        "",
        f"- final_status: `{ctx.get('final_status', '')}`",
        f"- signal_id: `{ctx.get('signal_id', '')}`",
        f"- idempotency_key: `{ctx.get('idempotency_key', '')}`",
        f"- module_validation_demo_execution: `{bool_text(bool(ctx.get('module_validation_demo_execution')))}`",
        f"- expired_signal_override_used: `{bool_text(bool(ctx.get('expired_signal_override_used')))}`",
        f"- strategy_valid: `{bool_text(bool(ctx.get('strategy_valid')))}`",
        f"- production_valid: `{bool_text(bool(ctx.get('production_valid')))}`",
        f"- order_check_called: `{bool_text(bool(ctx.get('order_check_called')))}`",
        f"- order_send_called: `{bool_text(bool(ctx.get('order_send_called')))}`",
        f"- order_send_attempt_count: `{int(ctx.get('order_send_attempt_count') or 0)}`",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(args: argparse.Namespace, output_dir: Path, ctx: dict[str, Any]) -> dict[str, Path]:
    paths = output_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(paths["manifest"], manifest_payload(args, ctx, paths))
    write_report(paths["report"], args, ctx)
    write_csv(paths["status"], [status_row(args, ctx)], STATUS_FIELDNAMES)
    write_csv(paths["warnings"], ctx.get("warnings", []), WARNING_FIELDNAMES)
    write_csv(paths["child_commands"], ctx.get("child_commands", []), CHILD_COMMAND_FIELDNAMES)
    write_csv(paths["child_results"], ctx.get("child_results", []), CHILD_RESULT_FIELDNAMES)
    write_csv(paths["no_order_until_send"], [no_order_until_send_row(args, ctx)], list(no_order_until_send_row(args, ctx)))
    write_csv(paths["final_execution"], [final_execution_row(args, ctx)], list(final_execution_row(args, ctx)))
    idem = idempotency_summary(ctx)
    state = final_state_summary(ctx)
    write_json(paths["idempotency_json"], idem)
    write_csv(paths["idempotency_csv"], [idem], list(idem))
    write_json(paths["broker_response"], redacted_broker_response(ctx, output_dir))
    write_json(paths["final_state_json"], state)
    write_csv(paths["final_state_csv"], [state], list(state))
    return paths


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for(args)
    ctx: dict[str, Any]
    try:
        ctx = execute(args, output_dir)
    except Exception as exc:
        ctx = {
            "warnings": [],
            "child_commands": [],
            "child_results": [],
            "module_validation_demo_execution": bool(args.module_validation_demo_execution),
            "strategy_valid": False if args.module_validation_demo_execution else True,
            "production_valid": False if args.module_validation_demo_execution else True,
            "stale_override_used": False,
            "expired_signal_override_used": False,
            "resumed_existing_active_approval_record": False,
            "resume_reason": "",
            "final_status": "demo_signal_to_order_pilot_error_unexpected",
            "order_send_attempt_count": 0,
            "order_send_called": False,
            "order_execution_performed": False,
            "manifests": {},
        }
        add_warning(
            ctx["warnings"],
            args=args,
            warning_code="demo_signal_to_order_pilot_error_unexpected",
            message=str(exc),
            source="orchestrator",
        )
    return write_outputs(args, output_dir, ctx)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one fixed-candidate demo signal-to-order pilot sequence.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--operator-identity-ref", required=True)
    parser.add_argument("--operator-final-acknowledgment", default="")
    parser.add_argument("--demo-account-only", action="store_true")
    parser.add_argument("--max-order-send-attempts", type=int, choices=[1], default=1)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--stop-after-request-construction", action="store_true")
    parser.add_argument("--stop-after-order-check", action="store_true")
    parser.add_argument("--stop-before-order-send", action="store_true")
    parser.add_argument("--module-validation-demo-execution", action="store_true")
    parser.add_argument("--allow-stale-upstream-artifacts-for-demo-module-validation", action="store_true")
    parser.add_argument("--module-validation-acknowledgment", default="")
    parser.add_argument("--allow-expired-signal-for-demo-module-validation", action="store_true")
    parser.add_argument("--expired-signal-override-acknowledgment", default="")
    parser.add_argument("--allow-new-demo-send-after-client-reject-flat", action="store_true")
    parser.add_argument("--client-reject-resend-acknowledgment", default="")
    parser.add_argument("--resume-existing-active-approval-record", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = build_outputs(args)
    manifest = read_json(paths["manifest"])
    print("Fixed-candidate demo signal-to-order pilot complete.")
    print(f"final_status: {manifest.get('final_status')}")
    for key, path in paths.items():
        print(f"{key}: {path}")
    return 0 if str(manifest.get("final_status", "")).startswith("demo_signal_to_order_pilot_completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
