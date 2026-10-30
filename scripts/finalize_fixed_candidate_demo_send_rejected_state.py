"""Finalize a demo send state after a confirmed client-side reject.

This module is intentionally narrow. It does not call MT5, read broker state,
send orders, check orders, delete state, or retry. It only consumes an existing
broker/local reconciliation artifact and updates the local demo state when the
client-side reject is already proven flat.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
SYMBOL = "GBPUSD"
TIMEFRAME = "M15"
DIRECTION = "short"
DEFAULT_FUTURE_STATE_JSON = (
    BASE_DIR
    / "state"
    / "fixed_candidate_demo_state"
    / "gbpusd_short_h10_1_5_off_hours_demo_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_send_rejected_state_finalization"

BROKER_LOCAL_RECONCILIATION_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
BROKER_LOCAL_RECONCILIATION_LOCAL_STATE = (
    "fixed_candidate_demo_broker_local_state_reconciliation_local_state_snapshot.json"
)

OUTPUT_MANIFEST = "fixed_candidate_demo_send_rejected_state_finalization_manifest.json"
OUTPUT_STATUS = "fixed_candidate_demo_send_rejected_state_finalization_status.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_send_rejected_state_finalization_warnings.csv"
OUTPUT_BEFORE_STATE = "fixed_candidate_demo_send_rejected_state_finalization_before_state_snapshot.json"
OUTPUT_AFTER_STATE = "fixed_candidate_demo_send_rejected_state_finalization_after_state_preview.json"
OUTPUT_REPORT = "fixed_candidate_demo_send_rejected_state_finalization_report.md"
OUTPUT_NO_ORDER = "fixed_candidate_demo_send_rejected_state_finalization_no_order_evidence.csv"

FINALIZATION_ACKNOWLEDGMENT = "acknowledge_finalize_client_reject_no_position_no_order"
EXPECTED_RECONCILIATION_STATUS = "broker_local_reconciliation_clean_no_local_no_broker"
FINAL_RECONCILIATION_STATUS = "broker_local_reconciliation_clean_after_client_reject_no_broker_state"
FINAL_STATE_STATUS = "send_rejected_no_position_no_order"
FINALIZATION_REASON = "client_autotrading_disabled_no_broker_state"

COMPLETED_STATUS = "send_rejected_state_finalization_completed_client_reject_no_position_no_order"

STATUS_FIELDNAMES = [
    "run_id",
    "finalization_status",
    "state_status_before",
    "state_status_after",
    "reconciliation_status_before",
    "reconciliation_status_after",
    "expected_retcode",
    "observed_retcode",
    "broker_position_count_symbol",
    "broker_pending_order_count_symbol",
    "idempotency_key_match",
    "future_state_json_written",
]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
NO_ORDER_FIELDNAMES = [
    "run_id",
    "no_order_send_called",
    "no_order_check_called",
    "no_broker_mutation_performed",
    "no_broker_api_called_by_finalizer",
    "broker_read_performed_by_finalizer",
    "state_deleted",
    "audit_trail_preserved",
    "retry_performed",
    "automatic_retry_allowed",
    "no_scheduler_added",
    "no_loop_added",
    "future_state_json_written",
    "evidence_label",
]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def safe_int(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(data, dict):
        return {}, "JSON root must be an object"
    return data, ""


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, path)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def output_paths(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "status": output_dir / OUTPUT_STATUS,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "before_state_snapshot": output_dir / OUTPUT_BEFORE_STATE,
        "after_state_preview": output_dir / OUTPUT_AFTER_STATE,
        "report": output_dir / OUTPUT_REPORT,
        "no_order_evidence": output_dir / OUTPUT_NO_ORDER,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def warning_row(
    args: argparse.Namespace,
    warning_code: str,
    message: str,
    source: Path | str,
    *,
    blocking: bool = True,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "warning_code": warning_code,
        "severity": "error" if blocking else "warning",
        "message": message,
        "source": str(source),
        "blocking_warning": blocking,
    }


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [warning for warning in warnings if warning.get("blocking_warning") is True]


def empty_ticket(value: Any) -> bool:
    return value in (None, "", 0, "0")


def first_block_status(warnings: list[dict[str, Any]]) -> str:
    blocks = blocking_warnings(warnings)
    if not blocks:
        return COMPLETED_STATUS
    code = str(blocks[0].get("warning_code") or "blocked")
    return f"send_rejected_state_finalization_blocked_{code}"


def read_inputs(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.broker_local_reconciliation_dir / BROKER_LOCAL_RECONCILIATION_MANIFEST
    local_snapshot_path = args.broker_local_reconciliation_dir / BROKER_LOCAL_RECONCILIATION_LOCAL_STATE
    state, state_error = read_json(args.future_state_json)
    reconciliation, reconciliation_error = read_json(manifest_path)
    local_snapshot, local_snapshot_error = read_json(local_snapshot_path)
    return {
        "state": state,
        "state_error": state_error,
        "reconciliation": reconciliation,
        "reconciliation_error": reconciliation_error,
        "local_snapshot": local_snapshot,
        "local_snapshot_error": local_snapshot_error,
        "paths": {
            "future_state_json": args.future_state_json,
            "reconciliation_manifest": manifest_path,
            "reconciliation_local_state_snapshot": local_snapshot_path,
        },
    }


def validate_inputs(args: argparse.Namespace, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    state = inputs["state"]
    reconciliation = inputs["reconciliation"]
    local_snapshot = inputs["local_snapshot"]
    paths = inputs["paths"]

    if inputs["state_error"]:
        warnings.append(
            warning_row(args, "state_unavailable", inputs["state_error"], paths["future_state_json"])
        )
    if inputs["reconciliation_error"]:
        warnings.append(
            warning_row(
                args,
                "reconciliation_manifest_unavailable",
                inputs["reconciliation_error"],
                paths["reconciliation_manifest"],
            )
        )
    if inputs["local_snapshot_error"]:
        warnings.append(
            warning_row(
                args,
                "reconciliation_local_state_snapshot_unavailable",
                inputs["local_snapshot_error"],
                paths["reconciliation_local_state_snapshot"],
            )
        )
    if warnings:
        return warnings

    if args.operator_acknowledgment != FINALIZATION_ACKNOWLEDGMENT:
        warnings.append(
            warning_row(
                args,
                "operator_acknowledgment_invalid",
                "Operator acknowledgment does not match the required finalization acknowledgment.",
                "operator_acknowledgment",
            )
        )
    if state.get("state_status") != "reconciliation_hold":
        warnings.append(
            warning_row(
                args,
                "state_status_not_reconciliation_hold",
                "Current state is not in reconciliation_hold.",
                paths["future_state_json"],
            )
        )
    if safe_int(state.get("last_retcode")) != int(args.expected_retcode):
        warnings.append(
            warning_row(
                args,
                "last_retcode_mismatch",
                "Current state last_retcode does not match expected retcode.",
                paths["future_state_json"],
            )
        )
    if str(state.get("idempotency_key") or "") != args.expected_idempotency_key:
        warnings.append(
            warning_row(
                args,
                "idempotency_key_mismatch",
                "Current state idempotency_key does not match expected idempotency_key.",
                paths["future_state_json"],
            )
        )
    if not empty_ticket(state.get("broker_order_ticket")):
        warnings.append(
            warning_row(args, "broker_order_ticket_present", "Current state has a broker order ticket.", paths["future_state_json"])
        )
    if not empty_ticket(state.get("broker_deal_ticket")):
        warnings.append(
            warning_row(args, "broker_deal_ticket_present", "Current state has a broker deal ticket.", paths["future_state_json"])
        )
    if reconciliation.get("reconciliation_status") != EXPECTED_RECONCILIATION_STATUS:
        warnings.append(
            warning_row(
                args,
                "reconciliation_status_not_clean_flat",
                "Broker/local reconciliation did not report clean no-local/no-broker.",
                paths["reconciliation_manifest"],
            )
        )
    if safe_int(reconciliation.get("broker_position_count_symbol")) != 0:
        warnings.append(
            warning_row(
                args,
                "broker_position_count_not_zero",
                "Broker/local reconciliation reported one or more broker positions.",
                paths["reconciliation_manifest"],
            )
        )
    if safe_int(reconciliation.get("broker_pending_order_count_symbol")) != 0:
        warnings.append(
            warning_row(
                args,
                "broker_pending_order_count_not_zero",
                "Broker/local reconciliation reported one or more pending broker orders.",
                paths["reconciliation_manifest"],
            )
        )
    if local_snapshot.get("local_state_exists") is not True:
        warnings.append(
            warning_row(
                args,
                "reconciliation_local_state_missing",
                "Reconciliation local state snapshot does not confirm local_state_exists=true.",
                paths["reconciliation_local_state_snapshot"],
            )
        )
    snapshot_state = local_snapshot.get("local_state")
    if not isinstance(snapshot_state, dict):
        warnings.append(
            warning_row(
                args,
                "reconciliation_local_state_invalid",
                "Reconciliation local state snapshot is missing a local_state object.",
                paths["reconciliation_local_state_snapshot"],
            )
        )
    else:
        snapshot_checks = (
            ("idempotency_key", args.expected_idempotency_key),
            ("state_status", "reconciliation_hold"),
            ("last_retcode", int(args.expected_retcode)),
        )
        for field, expected in snapshot_checks:
            observed = safe_int(snapshot_state.get(field)) if field == "last_retcode" else snapshot_state.get(field)
            if observed != expected:
                warnings.append(
                    warning_row(
                        args,
                        f"reconciliation_local_state_{field}_mismatch",
                        f"Reconciliation local state snapshot field {field} does not match expected value.",
                        paths["reconciliation_local_state_snapshot"],
                    )
                )
    return warnings


def finalized_state(args: argparse.Namespace, state: dict[str, Any], reconciliation: dict[str, Any]) -> dict[str, Any]:
    after = dict(state)
    after["state_status"] = FINAL_STATE_STATUS
    after["reconciliation_status"] = FINAL_RECONCILIATION_STATUS
    after["crash_recovery_required"] = False
    after["automatic_retry_allowed"] = False
    after["retry_performed"] = False
    after["order_execution_performed"] = False
    after["finalized_at_utc"] = utc_now_text()
    after["finalization_reason"] = FINALIZATION_REASON
    after["finalization_run_id"] = args.run_id
    after["finalization_broker_local_reconciliation_run_id"] = reconciliation.get("run_id", "")
    after["finalization_broker_local_reconciliation_dir"] = str(args.broker_local_reconciliation_dir)
    after["finalization_preserved_send_audit_trail"] = True
    return after


def write_manifest(
    path: Path,
    args: argparse.Namespace,
    outputs: dict[str, Path],
    inputs: dict[str, Any],
    status: str,
    warnings: list[dict[str, Any]],
    after: dict[str, Any],
    *,
    state_written: bool,
) -> None:
    state = inputs["state"]
    reconciliation = inputs["reconciliation"]
    manifest = {
        "run_id": args.run_id,
        "created_at_utc": utc_now_text(),
        "finalization_status": status,
        "candidate_id": state.get("candidate_id", CANDIDATE_ID),
        "symbol": state.get("symbol", SYMBOL),
        "timeframe": state.get("timeframe", TIMEFRAME),
        "direction": state.get("direction", DIRECTION),
        "future_state_json": str(args.future_state_json),
        "future_state_json_written": state_written,
        "broker_local_reconciliation_dir": str(args.broker_local_reconciliation_dir),
        "broker_local_reconciliation_status": reconciliation.get("reconciliation_status", ""),
        "broker_position_count_symbol": reconciliation.get("broker_position_count_symbol"),
        "broker_pending_order_count_symbol": reconciliation.get("broker_pending_order_count_symbol"),
        "local_state_exists": reconciliation.get("local_state_exists"),
        "state_status_before": state.get("state_status", ""),
        "state_status_after": after.get("state_status", state.get("state_status", "")),
        "reconciliation_status_before": state.get("reconciliation_status", ""),
        "reconciliation_status_after": after.get("reconciliation_status", state.get("reconciliation_status", "")),
        "expected_retcode": int(args.expected_retcode),
        "observed_retcode": safe_int(state.get("last_retcode")),
        "idempotency_key": state.get("idempotency_key", ""),
        "idempotency_key_match": state.get("idempotency_key") == args.expected_idempotency_key,
        "send_attempt_id": state.get("send_attempt_id", ""),
        "signal_id": state.get("signal_id", ""),
        "broker_order_ticket": state.get("broker_order_ticket", ""),
        "broker_deal_ticket": state.get("broker_deal_ticket", ""),
        "finalization_reason": after.get("finalization_reason", ""),
        "operator_acknowledgment_valid": args.operator_acknowledgment == FINALIZATION_ACKNOWLEDGMENT,
        "order_execution_performed": after.get("order_execution_performed", False),
        "automatic_retry_allowed": after.get("automatic_retry_allowed", False),
        "retry_performed": after.get("retry_performed", False),
        "state_deleted": False,
        "audit_trail_preserved": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_broker_mutation_performed": True,
        "no_broker_api_called_by_finalizer": True,
        "broker_read_performed_by_finalizer": False,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "output_files": {key: str(value) for key, value in outputs.items()},
    }
    write_json(path, manifest)


def status_row(args: argparse.Namespace, inputs: dict[str, Any], status: str, after: dict[str, Any], *, state_written: bool) -> dict[str, Any]:
    state = inputs["state"]
    reconciliation = inputs["reconciliation"]
    return {
        "run_id": args.run_id,
        "finalization_status": status,
        "state_status_before": state.get("state_status", ""),
        "state_status_after": after.get("state_status", state.get("state_status", "")),
        "reconciliation_status_before": state.get("reconciliation_status", ""),
        "reconciliation_status_after": after.get("reconciliation_status", state.get("reconciliation_status", "")),
        "expected_retcode": int(args.expected_retcode),
        "observed_retcode": safe_int(state.get("last_retcode")),
        "broker_position_count_symbol": reconciliation.get("broker_position_count_symbol"),
        "broker_pending_order_count_symbol": reconciliation.get("broker_pending_order_count_symbol"),
        "idempotency_key_match": state.get("idempotency_key") == args.expected_idempotency_key,
        "future_state_json_written": state_written,
    }


def no_order_row(args: argparse.Namespace, *, state_written: bool) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_broker_mutation_performed": True,
        "no_broker_api_called_by_finalizer": True,
        "broker_read_performed_by_finalizer": False,
        "state_deleted": False,
        "audit_trail_preserved": True,
        "retry_performed": False,
        "automatic_retry_allowed": False,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "future_state_json_written": state_written,
        "evidence_label": "state_finalization_only_no_broker_or_order_action",
    }


def write_report(path: Path, args: argparse.Namespace, status: str, inputs: dict[str, Any], warnings: list[dict[str, Any]], *, state_written: bool) -> None:
    state = inputs["state"]
    reconciliation = inputs["reconciliation"]
    lines = [
        "# Fixed Candidate Demo Send Rejected State Finalization",
        "",
        f"- run_id: `{args.run_id}`",
        f"- finalization_status: `{status}`",
        f"- future_state_json_written: `{str(state_written).lower()}`",
        f"- state_status_before: `{state.get('state_status', '')}`",
        f"- last_retcode: `{state.get('last_retcode', '')}`",
        f"- reconciliation_status_artifact: `{reconciliation.get('reconciliation_status', '')}`",
        f"- broker_position_count_symbol: `{reconciliation.get('broker_position_count_symbol', '')}`",
        f"- broker_pending_order_count_symbol: `{reconciliation.get('broker_pending_order_count_symbol', '')}`",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        "",
        "No order_send, order_check, broker mutation, retry, loop, or scheduler is performed by this module.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / args.run_id
    outputs = output_paths(output_dir, args.overwrite)
    inputs = read_inputs(args)
    warnings = validate_inputs(args, inputs)
    status = first_block_status(warnings)
    state_written = False
    after = dict(inputs["state"])

    write_json(outputs["before_state_snapshot"], inputs["state"])
    if not blocking_warnings(warnings):
        after = finalized_state(args, inputs["state"], inputs["reconciliation"])
        write_json(outputs["after_state_preview"], after)
        atomic_write_json(args.future_state_json, after)
        state_written = True
    else:
        after["after_state_preview_status"] = "blocked_no_state_write"
        write_json(outputs["after_state_preview"], after)

    write_csv(outputs["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(outputs["status"], [status_row(args, inputs, status, after, state_written=state_written)], STATUS_FIELDNAMES)
    write_csv(outputs["no_order_evidence"], [no_order_row(args, state_written=state_written)], NO_ORDER_FIELDNAMES)
    write_report(outputs["report"], args, status, inputs, warnings, state_written=state_written)
    write_manifest(outputs["manifest"], args, outputs, inputs, status, warnings, after, state_written=state_written)
    return 0 if state_written else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--future-state-json", type=Path, default=DEFAULT_FUTURE_STATE_JSON)
    parser.add_argument("--broker-local-reconciliation-dir", type=Path, required=True)
    parser.add_argument("--expected-idempotency-key", required=True)
    parser.add_argument("--expected-retcode", type=int, required=True)
    parser.add_argument("--operator-acknowledgment", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
