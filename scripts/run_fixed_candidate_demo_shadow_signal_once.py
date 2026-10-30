"""Build one live-demo shadow-signal artifact from a no-order cycle.

This wrapper is single-shot. It may read an existing no-order cycle artifact or
run exactly one allowlisted no-order cycle child. It does not construct broker
requests, execute orders, run paper/replay/cost workflows, add schedulers, or
make trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_shadow_signal_once"
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_NO_ORDER_CYCLE_SCRIPT = BASE_DIR / "scripts" / "run_fixed_candidate_demo_no_order_cycle_once.py"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_shadow_signal_once"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_SYMBOL = "GBPUSD"
EXPECTED_TIMEFRAME = "M15"
EXPECTED_DIRECTION = "short"
EXPECTED_SPREAD_UNIT = "broker_points"
EXPECTED_MAX_SPREAD_POINTS = 15.0

CYCLE_MANIFEST = "fixed_candidate_demo_no_order_cycle_once_manifest.json"
CHILD_DRY_RUN_MANIFEST = "fixed_candidate_demo_no_order_dry_run_manifest.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_shadow_signal_once_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_shadow_signal_once_report.md"
OUTPUT_CSV = "fixed_candidate_demo_shadow_signal_once.csv"
OUTPUT_CHILD_COMMANDS = "fixed_candidate_demo_shadow_signal_once_child_commands.csv"
OUTPUT_CHILD_RESULTS = "fixed_candidate_demo_shadow_signal_once_child_results.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_shadow_signal_once_warnings.csv"
OUTPUT_NO_ORDER_EVIDENCE = "fixed_candidate_demo_shadow_signal_once_no_order_evidence.csv"
OUTPUT_REVIEW_PACKET = "fixed_candidate_demo_shadow_signal_once_review_packet.json"

COMPLETED_CYCLE_STATUS_TO_SHADOW = {
    "demo_no_order_cycle_completed_would_skip": ("shadow_no_signal", "no_signal"),
    "demo_no_order_cycle_completed_would_signal": ("shadow_signal_detected", "shadow_signal_detected"),
    "demo_no_order_cycle_completed_would_block": ("shadow_blocked", "blocked"),
}
COMPLETED_CYCLE_STATUS_TO_CHILD_DECISION = {
    "demo_no_order_cycle_completed_would_skip": "would_skip",
    "demo_no_order_cycle_completed_would_signal": "would_signal",
    "demo_no_order_cycle_completed_would_block": "would_block",
}
LIVE_ALIGNMENT_BLOCK_STATUSES = {
    "live_data_blocked_db_lagging_mt5_latest_bar",
    "live_data_blocked_db_ahead_of_mt5_latest_bar",
    "live_data_mt5_alignment_unparseable",
    "live_data_mt5_time_basis_unavailable",
}

NO_ORDER_FLAGS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_demo_broker_approval_performed",
    "no_trading_decision_performed",
)
CYCLE_BOUNDARY_TRUE_FIELDS = (*NO_ORDER_FLAGS, "no_order_boundary_confirmed")
CYCLE_BOUNDARY_ZERO_FIELDS = ("missing_no_order_flag_count", "unsafe_no_order_flag_count")

MAIN_FIELDNAMES = [
    "run_id",
    "shadow_status",
    "shadow_decision_label",
    "cycle_status",
    "cycle_manifest_path",
    "child_dry_run_manifest_path",
    "time_server",
    "evaluated_feature_time_server",
    "time_server_source",
    "import_time_basis",
    "db_refresh_before_shadow_enabled",
    "mt5_time_basis_checked",
    "pc_utc_now",
    "mt5_tick_time_server",
    "latest_mt5_closed_bar_time_server",
    "latest_db_price_bar_time_server_before_import",
    "latest_db_feature_time_server_before_generation",
    "effective_import_from_date",
    "effective_import_to_date",
    "effective_import_to_date_source",
    "latest_db_price_bar_time_server_after_import",
    "latest_db_feature_time_server_after_generation",
    "imported_rows_count",
    "generated_features_count",
    "latest_db_price_bar_time_server",
    "latest_db_feature_time_server",
    "db_lag_bars_vs_mt5_latest_closed_bar",
    "db_lag_minutes_vs_mt5_latest_closed_bar",
    "mt5_server_time_offset_seconds_vs_pc_utc",
    "live_alignment_status",
    "symbol",
    "timeframe",
    "session_observed",
    "spread",
    "feature_row_spread_broker_points",
    "feature_row_spread_source",
    "current_broker_spread_points",
    "current_broker_spread_source",
    "current_broker_spread_within_policy",
    "current_broker_spread_policy_max_points",
    "live_spread_gate_status",
    "spread_source",
    "spread_unit",
    "max_spread_points",
    "spread_within_gate",
    "close",
    "atr_20",
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100_bucket",
    "entry_reference_price",
    "tp_price_preview",
    "sl_price_preview",
    "skip_reason_count",
    "block_reason_count",
    "manual_review_required",
    "order_execution_allowed",
    "order_request_construction_allowed",
    "recommended_next_step",
]
COMMAND_FIELDNAMES = [
    "run_id",
    "child_step",
    "command_index",
    "command_executable",
    "command_args_json",
    "planned_only",
    "allowed_child_script",
    "check_mode",
    "caveat",
]
RESULT_FIELDNAMES = [
    "run_id",
    "child_step",
    "command_index",
    "return_code",
    "started_at",
    "completed_at",
    "duration_seconds",
    "stdout_tail",
    "stderr_tail",
    "child_status",
    "blocking_warning",
]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
NO_ORDER_EVIDENCE_FIELDNAMES = [
    "run_id",
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_demo_broker_approval_performed",
    "no_trading_decision_performed",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "evidence_label",
    "caveat",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_text() -> str:
    return utc_now().isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


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
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(payload, dict):
        return {}, "JSON root must be an object"
    return payload, ""


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_first_csv_row(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return next(csv.DictReader(handle), {}), ""
    except (OSError, csv.Error) as exc:
        return {}, str(exc)


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "main": output_dir / OUTPUT_CSV,
        "child_commands": output_dir / OUTPUT_CHILD_COMMANDS,
        "child_results": output_dir / OUTPUT_CHILD_RESULTS,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order_evidence": output_dir / OUTPUT_NO_ORDER_EVIDENCE,
        "review_packet": output_dir / OUTPUT_REVIEW_PACKET,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def warning_row(
    *,
    run_id: str,
    warning_code: str,
    message: str,
    source: Path | str,
    blocking_warning: bool,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "warning_code": warning_code,
        "severity": "error" if blocking_warning else severity,
        "message": message,
        "source": str(source),
        "blocking_warning": bool(blocking_warning),
    }


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
    warning_code: str,
    message: str,
    source: Path | str,
    blocking_warning: bool,
) -> None:
    warnings.append(
        warning_row(
            run_id=args.run_id,
            warning_code=warning_code,
            message=message,
            source=source,
            blocking_warning=blocking_warning,
        )
    )


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [warning for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"]


def resolve_path_from_manifest(value: Any) -> Path | None:
    if value in ("", None):
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    return BASE_DIR / path


def exact_no_order_cycle_script(path: Path) -> bool:
    try:
        return path.resolve() == DEFAULT_NO_ORDER_CYCLE_SCRIPT.resolve()
    except OSError:
        return False


def canonical_registry_safe(registry: dict[str, Any]) -> bool:
    return (
        registry.get("candidate_id") == EXPECTED_CANDIDATE_ID
        and registry.get("symbol") == EXPECTED_SYMBOL
        and registry.get("timeframe") == EXPECTED_TIMEFRAME
        and registry.get("direction") == EXPECTED_DIRECTION
        and registry.get("spread_unit") == EXPECTED_SPREAD_UNIT
        and safe_float(registry.get("max_spread_points")) == EXPECTED_MAX_SPREAD_POINTS
    )


def boundary_counts(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    unsafe: list[str] = []
    for field in CYCLE_BOUNDARY_TRUE_FIELDS:
        if field not in manifest:
            missing.append(field)
        elif manifest.get(field) is not True:
            unsafe.append(field)
    for field in CYCLE_BOUNDARY_ZERO_FIELDS:
        if field not in manifest:
            missing.append(field)
        elif safe_int(manifest.get(field)) != 0:
            unsafe.append(field)
    return missing, unsafe


def child_boundary_counts(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    unsafe: list[str] = []
    for field in NO_ORDER_FLAGS:
        if field not in manifest:
            missing.append(field)
        elif manifest.get(field) is not True:
            unsafe.append(field)
    return missing, unsafe


def recommended_next_step(shadow_status: str, live_spread_gate_status: str = "", live_alignment_status: str = "") -> str:
    if live_spread_gate_status in {"blocked_current_spread_above_policy", "blocked_current_spread_unavailable"}:
        return "wait_for_current_spread_within_policy_and_rerun_live_shadow"
    if live_alignment_status in LIVE_ALIGNMENT_BLOCK_STATUSES:
        return "refresh_price_bars_features_and_rerun_live_shadow"
    if shadow_status == "shadow_signal_plan_only":
        return "run_shadow_signal_once_when_ready"
    if shadow_status == "shadow_no_signal":
        return "monitor_next_feature_row_or_run_shadow_again_later"
    if shadow_status == "shadow_signal_detected":
        return "build_fixed_candidate_demo_would_signal_review"
    if shadow_status == "shadow_blocked":
        return "fix_shadow_signal_blocker"
    return "fix_shadow_signal_blocker"


def command_output_dir(args: argparse.Namespace, output_dir: Path) -> Path:
    if args.cycle_output_dir:
        return Path(args.cycle_output_dir)
    return output_dir / "children" / f"no_order_cycle_{args.run_id}"


def command_run_id(args: argparse.Namespace) -> str:
    return str(args.cycle_run_id or f"{args.run_id}_child_no_order_cycle")


def build_child_command(args: argparse.Namespace, output_dir: Path) -> dict[str, Any] | None:
    if not args.run_cycle:
        return None
    cycle_output_dir = command_output_dir(args, output_dir)
    command = [
        str(args.python_executable),
        str(args.no_order_cycle_script),
        "--run-id",
        command_run_id(args),
        "--output-dir",
        str(cycle_output_dir),
        "--overwrite",
    ]
    return {
        "child_step": "no_order_cycle_once",
        "command_index": 1,
        "script": Path(args.no_order_cycle_script),
        "command": command,
        "output_dir": cycle_output_dir,
        "timeout_seconds": 420,
        "allowed_child_script": exact_no_order_cycle_script(Path(args.no_order_cycle_script)),
        "caveat": "delegates one no-order cycle only; no order path is allowed",
    }


def command_row(args: argparse.Namespace, command: dict[str, Any], *, planned_only: bool) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "child_step": command["child_step"],
        "command_index": command["command_index"],
        "command_executable": command["command"][0],
        "command_args_json": command["command"][1:],
        "planned_only": planned_only,
        "allowed_child_script": command["allowed_child_script"],
        "check_mode": "single_shot_shadow_signal_no_order",
        "caveat": command["caveat"],
    }


def not_executed_result(args: argparse.Namespace, command: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "child_step": command["child_step"],
        "command_index": command["command_index"],
        "return_code": "",
        "started_at": "",
        "completed_at": "",
        "duration_seconds": "",
        "stdout_tail": "",
        "stderr_tail": "",
        "child_status": status,
        "blocking_warning": status not in {"not_executed_dry_run"},
    }


def tail_text(value: str, limit: int = 1000) -> str:
    return (value or "")[-limit:]


def run_child(args: argparse.Namespace, command: dict[str, Any]) -> dict[str, Any]:
    started_dt = utc_now()
    started_at = started_dt.isoformat()
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command["command"],
            shell=False,
            capture_output=True,
            text=True,
            check=False,
            timeout=int(command["timeout_seconds"]),
        )
        return_code = int(result.returncode)
        stdout_tail = tail_text(result.stdout or "")
        stderr_tail = tail_text(result.stderr or "")
        child_status = "success" if return_code == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        return_code = ""
        stdout_tail = tail_text(exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or ""))
        stderr_tail = tail_text(exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "timeout"))
        child_status = "failed"
    completed_at = utc_now().isoformat()
    return {
        "run_id": args.run_id,
        "child_step": command["child_step"],
        "command_index": command["command_index"],
        "return_code": return_code,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": round(time.perf_counter() - started, 6),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "child_status": child_status,
        "blocking_warning": child_status != "success",
    }


def cycle_manifest_path(args: argparse.Namespace, command: dict[str, Any] | None) -> Path | None:
    if args.run_cycle:
        if command is None:
            return None
        return Path(command["output_dir"]) / CYCLE_MANIFEST
    if args.existing_no_order_cycle_dir:
        return Path(args.existing_no_order_cycle_dir) / CYCLE_MANIFEST
    return None


def child_manifest_path_from_cycle(cycle_manifest: dict[str, Any]) -> Path | None:
    path = resolve_path_from_manifest(cycle_manifest.get("latest_child_manifest_path"))
    if path is not None:
        return path
    child_output = resolve_path_from_manifest(cycle_manifest.get("no_order_dry_run_child_output_dir"))
    if child_output is not None:
        return child_output / CHILD_DRY_RUN_MANIFEST
    return None


def initial_block_status(
    *,
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_error: str,
    command: dict[str, Any] | None,
    warnings: list[dict[str, Any]],
) -> str | None:
    if registry_error == "missing":
        add_warning(warnings, args=args, warning_code="canonical_registry_missing", message="Canonical registry is missing.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_missing_required_artifact"
    if registry_error:
        add_warning(warnings, args=args, warning_code="canonical_registry_unreadable", message="Canonical registry is unreadable.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_unreadable_input"
    if not canonical_registry_safe(registry):
        add_warning(warnings, args=args, warning_code="canonical_registry_boundary_unsafe", message="Canonical registry does not match spread15 fixed-candidate boundaries.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_by_config_boundary"
    if not exact_no_order_cycle_script(Path(args.no_order_cycle_script)):
        add_warning(warnings, args=args, warning_code="no_order_cycle_script_not_exact", message="No-order cycle script path is not the exact allowlisted script.", source=args.no_order_cycle_script, blocking_warning=True)
        return "blocked_by_config_boundary"
    if args.run_cycle and command is not None and command.get("allowed_child_script") is not True:
        add_warning(warnings, args=args, warning_code="child_script_not_allowlisted", message="No-order cycle child script is outside the exact allowlist.", source=args.no_order_cycle_script, blocking_warning=True)
        return "blocked_by_config_boundary"
    return None


def load_cycle_and_child(
    *,
    args: argparse.Namespace,
    command: dict[str, Any] | None,
    warnings: list[dict[str, Any]],
) -> tuple[str | None, dict[str, Any], Path | None, dict[str, Any], Path | None]:
    manifest_path = cycle_manifest_path(args, command)
    if manifest_path is None:
        return None, {}, None, {}, None
    cycle_manifest, cycle_error = read_json(manifest_path)
    if cycle_error == "missing":
        add_warning(warnings, args=args, warning_code="cycle_manifest_missing", message="No-order cycle manifest is missing.", source=manifest_path, blocking_warning=True)
        return "blocked_missing_required_artifact", {}, manifest_path, {}, None
    if cycle_error:
        add_warning(warnings, args=args, warning_code="cycle_manifest_unreadable", message="No-order cycle manifest is unreadable.", source=manifest_path, blocking_warning=True)
        return "blocked_unreadable_input", {}, manifest_path, {}, None

    missing, unsafe = boundary_counts(cycle_manifest)
    if missing or unsafe:
        add_warning(
            warnings,
            args=args,
            warning_code="cycle_no_order_boundary_violation",
            message=f"No-order cycle boundary flags are missing or unsafe. missing={missing}; unsafe={unsafe}",
            source=manifest_path,
            blocking_warning=True,
        )
        return "blocked_by_no_order_boundary", cycle_manifest, manifest_path, {}, None

    cycle_status = str(cycle_manifest.get("cycle_status") or "")
    if cycle_status not in COMPLETED_CYCLE_STATUS_TO_SHADOW:
        add_warning(warnings, args=args, warning_code="cycle_status_not_completed", message=f"No-order cycle status is not a completed would_* status: {cycle_status}", source=manifest_path, blocking_warning=True)
        return "blocked_by_cycle_status", cycle_manifest, manifest_path, {}, None

    child_path = child_manifest_path_from_cycle(cycle_manifest)
    if child_path is None:
        add_warning(warnings, args=args, warning_code="child_manifest_path_missing", message="No child no-order dry-run manifest path was recorded.", source=manifest_path, blocking_warning=True)
        return "blocked_child_manifest_missing", cycle_manifest, manifest_path, {}, None
    child_manifest, child_error = read_json(child_path)
    if child_error:
        add_warning(warnings, args=args, warning_code="child_manifest_missing_or_unreadable", message="Child no-order dry-run manifest is missing or unreadable.", source=child_path, blocking_warning=True)
        return "blocked_child_manifest_missing", cycle_manifest, manifest_path, {}, child_path
    child_missing, child_unsafe = child_boundary_counts(child_manifest)
    if child_missing or child_unsafe:
        add_warning(
            warnings,
            args=args,
            warning_code="child_no_order_boundary_violation",
            message=f"Child no-order boundary flags are missing or unsafe. missing={child_missing}; unsafe={child_unsafe}",
            source=child_path,
            blocking_warning=True,
        )
        return "blocked_by_no_order_boundary", cycle_manifest, manifest_path, child_manifest, child_path

    expected_decision = COMPLETED_CYCLE_STATUS_TO_CHILD_DECISION[cycle_status]
    if child_manifest.get("decision_label") != expected_decision:
        add_warning(
            warnings,
            args=args,
            warning_code="cycle_child_decision_mismatch",
            message=f"Cycle status expects child decision {expected_decision}, observed {child_manifest.get('decision_label')}.",
            source=child_path,
            blocking_warning=True,
        )
        return "blocked_by_cycle_status", cycle_manifest, manifest_path, child_manifest, child_path
    if expected_decision == "would_signal":
        required_preview = ("entry_reference_price", "tp_price_preview", "sl_price_preview")
        missing_preview = [field for field in required_preview if child_manifest.get(field) in ("", None)]
        if missing_preview:
            add_warning(
                warnings,
                args=args,
                warning_code="shadow_signal_preview_missing",
                message=f"Shadow signal child manifest is missing preview fields: {missing_preview}",
                source=child_path,
                blocking_warning=True,
            )
            return "blocked_by_cycle_status", cycle_manifest, manifest_path, child_manifest, child_path
    return None, cycle_manifest, manifest_path, child_manifest, child_path


def shadow_from_cycle(cycle_manifest: dict[str, Any], child_manifest: dict[str, Any] | None = None) -> tuple[str, str]:
    live_status = first_present(
        (child_manifest or {}).get("live_spread_gate_status"),
        cycle_manifest.get("child_live_spread_gate_status"),
        cycle_manifest.get("live_spread_gate_status"),
    )
    if live_status in {"blocked_current_spread_above_policy", "blocked_current_spread_unavailable"}:
        return "shadow_blocked", "blocked"
    alignment_status = first_present(
        (child_manifest or {}).get("live_alignment_status"),
        cycle_manifest.get("child_live_alignment_status"),
        cycle_manifest.get("live_alignment_status"),
    )
    if alignment_status in LIVE_ALIGNMENT_BLOCK_STATUSES:
        return "shadow_blocked", "blocked"
    cycle_status = str(cycle_manifest.get("cycle_status") or "")
    return COMPLETED_CYCLE_STATUS_TO_SHADOW.get(cycle_status, ("shadow_blocked", "blocked"))


def source_value(child_manifest: dict[str, Any], cycle_manifest: dict[str, Any], key: str) -> Any:
    value = child_manifest.get(key)
    if value in ("", None):
        return cycle_manifest.get(f"child_{key}")
    return value


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in ("", None):
            return value
    return ""


def main_row(
    *,
    args: argparse.Namespace,
    registry: dict[str, Any],
    shadow_status: str,
    shadow_decision_label: str,
    cycle_manifest: dict[str, Any],
    cycle_manifest_path_value: Path | None,
    child_manifest: dict[str, Any],
    child_manifest_path_value: Path | None,
) -> dict[str, Any]:
    manual_review_required = shadow_status == "shadow_signal_detected"
    live_spread_gate_status = first_present(child_manifest.get("live_spread_gate_status"), cycle_manifest.get("child_live_spread_gate_status"), cycle_manifest.get("live_spread_gate_status"))
    live_alignment_status = first_present(child_manifest.get("live_alignment_status"), cycle_manifest.get("child_live_alignment_status"), cycle_manifest.get("live_alignment_status"), cycle_manifest.get("mt5_time_basis_status"))
    return {
        "run_id": args.run_id,
        "shadow_status": shadow_status,
        "shadow_decision_label": shadow_decision_label,
        "cycle_status": cycle_manifest.get("cycle_status", ""),
        "cycle_manifest_path": str(cycle_manifest_path_value or ""),
        "child_dry_run_manifest_path": str(child_manifest_path_value or ""),
        "time_server": source_value(child_manifest, cycle_manifest, "time_server"),
        "evaluated_feature_time_server": first_present(source_value(child_manifest, cycle_manifest, "evaluated_feature_time_server"), source_value(child_manifest, cycle_manifest, "time_server")),
        "time_server_source": first_present(child_manifest.get("time_server_source"), cycle_manifest.get("time_server_source")),
        "import_time_basis": first_present(child_manifest.get("import_time_basis"), cycle_manifest.get("import_time_basis")),
        "db_refresh_before_shadow_enabled": cycle_manifest.get("db_refresh_before_shadow_enabled"),
        "mt5_time_basis_checked": cycle_manifest.get("mt5_time_basis_checked"),
        "pc_utc_now": first_present(child_manifest.get("pc_utc_now"), cycle_manifest.get("pc_utc_now")),
        "mt5_tick_time_server": first_present(child_manifest.get("mt5_tick_time_server"), cycle_manifest.get("mt5_tick_time_server")),
        "latest_mt5_closed_bar_time_server": first_present(child_manifest.get("latest_mt5_closed_bar_time_server"), cycle_manifest.get("latest_mt5_closed_bar_time_server")),
        "latest_db_price_bar_time_server_before_import": cycle_manifest.get("latest_db_price_bar_time_server_before_import"),
        "latest_db_feature_time_server_before_generation": cycle_manifest.get("latest_db_feature_time_server_before_generation"),
        "effective_import_from_date": cycle_manifest.get("effective_import_from_date"),
        "effective_import_to_date": cycle_manifest.get("effective_import_to_date"),
        "effective_import_to_date_source": cycle_manifest.get("effective_import_to_date_source"),
        "latest_db_price_bar_time_server_after_import": cycle_manifest.get("latest_db_price_bar_time_server_after_import"),
        "latest_db_feature_time_server_after_generation": cycle_manifest.get("latest_db_feature_time_server_after_generation"),
        "imported_rows_count": cycle_manifest.get("imported_rows_count"),
        "generated_features_count": cycle_manifest.get("generated_features_count"),
        "latest_db_price_bar_time_server": first_present(child_manifest.get("latest_db_price_bar_time_server"), cycle_manifest.get("latest_db_price_bar_time_server_after_import"), cycle_manifest.get("latest_db_price_bar_time_server"), cycle_manifest.get("child_latest_db_price_bar_time_server")),
        "latest_db_feature_time_server": first_present(child_manifest.get("latest_db_feature_time_server"), cycle_manifest.get("latest_db_feature_time_server_after_generation"), cycle_manifest.get("latest_db_feature_time_server"), cycle_manifest.get("child_latest_db_feature_time_server")),
        "db_lag_bars_vs_mt5_latest_closed_bar": first_present(child_manifest.get("db_lag_bars_vs_mt5_latest_closed_bar"), cycle_manifest.get("child_db_lag_bars_vs_mt5_latest_closed_bar"), cycle_manifest.get("db_lag_bars_vs_mt5_latest_closed_bar")),
        "db_lag_minutes_vs_mt5_latest_closed_bar": first_present(child_manifest.get("db_lag_minutes_vs_mt5_latest_closed_bar"), cycle_manifest.get("child_db_lag_minutes_vs_mt5_latest_closed_bar"), cycle_manifest.get("db_lag_minutes_vs_mt5_latest_closed_bar")),
        "mt5_server_time_offset_seconds_vs_pc_utc": first_present(child_manifest.get("mt5_server_time_offset_seconds_vs_pc_utc"), cycle_manifest.get("mt5_server_time_offset_seconds_vs_pc_utc")),
        "live_alignment_status": live_alignment_status,
        "symbol": registry.get("symbol", EXPECTED_SYMBOL),
        "timeframe": registry.get("timeframe", EXPECTED_TIMEFRAME),
        "session_observed": source_value(child_manifest, cycle_manifest, "session_observed"),
        "spread": source_value(child_manifest, cycle_manifest, "spread"),
        "feature_row_spread_broker_points": first_present(child_manifest.get("feature_row_spread_broker_points"), source_value(child_manifest, cycle_manifest, "spread")),
        "feature_row_spread_source": first_present(child_manifest.get("feature_row_spread_source"), cycle_manifest.get("child_feature_row_spread_source"), child_manifest.get("spread_source"), cycle_manifest.get("child_spread_source"), "db_candle_spread"),
        "current_broker_spread_points": first_present(child_manifest.get("current_broker_spread_points"), cycle_manifest.get("child_current_broker_spread_points")),
        "current_broker_spread_source": first_present(child_manifest.get("current_broker_spread_source"), cycle_manifest.get("child_current_broker_spread_source"), cycle_manifest.get("current_broker_spread_source")),
        "current_broker_spread_within_policy": first_present(child_manifest.get("current_broker_spread_within_policy"), cycle_manifest.get("child_current_broker_spread_within_policy"), cycle_manifest.get("current_broker_spread_within_policy")),
        "current_broker_spread_policy_max_points": first_present(child_manifest.get("current_broker_spread_policy_max_points"), cycle_manifest.get("child_current_broker_spread_policy_max_points"), cycle_manifest.get("current_broker_spread_policy_max_points"), registry.get("max_spread_points", EXPECTED_MAX_SPREAD_POINTS)),
        "live_spread_gate_status": live_spread_gate_status,
        "spread_source": first_present(child_manifest.get("spread_source"), cycle_manifest.get("child_spread_source"), "db_candle_spread"),
        "spread_unit": child_manifest.get("spread_unit") or registry.get("spread_unit", EXPECTED_SPREAD_UNIT),
        "max_spread_points": child_manifest.get("max_spread_points") or registry.get("max_spread_points", EXPECTED_MAX_SPREAD_POINTS),
        "spread_within_gate": source_value(child_manifest, cycle_manifest, "spread_within_gate"),
        "close": child_manifest.get("close", ""),
        "atr_20": child_manifest.get("atr_20", ""),
        "close_to_ma_fast_atr_20_bucket": source_value(child_manifest, cycle_manifest, "close_to_ma_fast_atr_20_bucket"),
        "tick_volume_percentile_100_bucket": source_value(child_manifest, cycle_manifest, "tick_volume_percentile_100_bucket"),
        "entry_reference_price": child_manifest.get("entry_reference_price", ""),
        "tp_price_preview": child_manifest.get("tp_price_preview", ""),
        "sl_price_preview": child_manifest.get("sl_price_preview", ""),
        "skip_reason_count": source_value(child_manifest, cycle_manifest, "skip_reason_count"),
        "block_reason_count": source_value(child_manifest, cycle_manifest, "block_reason_count"),
        "manual_review_required": manual_review_required,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "recommended_next_step": recommended_next_step(shadow_status, live_spread_gate_status, live_alignment_status),
    }


def no_order_evidence_row(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_trading_decision_performed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "evidence_label": "shadow_signal_no_order_boundary_confirmed",
        "caveat": "artifact_layer_only_no_execution_path",
    }


def review_packet(
    *,
    args: argparse.Namespace,
    registry: dict[str, Any],
    row: dict[str, Any],
    cycle_manifest: dict[str, Any],
    child_manifest: dict[str, Any],
    shadow_status: str,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "shadow_status": shadow_status,
        "manual_review_required": shadow_status == "shadow_signal_detected",
        "candidate_id": registry.get("candidate_id", EXPECTED_CANDIDATE_ID),
        "symbol": registry.get("symbol", EXPECTED_SYMBOL),
        "timeframe": registry.get("timeframe", EXPECTED_TIMEFRAME),
        "direction": registry.get("direction", EXPECTED_DIRECTION),
        "time_server": row.get("time_server", ""),
        "evaluated_feature_time_server": row.get("evaluated_feature_time_server", ""),
        "db_refresh_before_shadow_enabled": row.get("db_refresh_before_shadow_enabled", ""),
        "mt5_time_basis_checked": row.get("mt5_time_basis_checked", ""),
        "latest_db_price_bar_time_server_before_import": row.get("latest_db_price_bar_time_server_before_import", ""),
        "latest_db_feature_time_server_before_generation": row.get("latest_db_feature_time_server_before_generation", ""),
        "effective_import_from_date": row.get("effective_import_from_date", ""),
        "effective_import_to_date": row.get("effective_import_to_date", ""),
        "effective_import_to_date_source": row.get("effective_import_to_date_source", ""),
        "latest_db_price_bar_time_server_after_import": row.get("latest_db_price_bar_time_server_after_import", ""),
        "latest_db_feature_time_server_after_generation": row.get("latest_db_feature_time_server_after_generation", ""),
        "imported_rows_count": row.get("imported_rows_count", ""),
        "generated_features_count": row.get("generated_features_count", ""),
        "latest_db_price_bar_time_server": row.get("latest_db_price_bar_time_server", ""),
        "latest_db_feature_time_server": row.get("latest_db_feature_time_server", ""),
        "latest_mt5_closed_bar_time_server": row.get("latest_mt5_closed_bar_time_server", ""),
        "db_lag_bars_vs_mt5_latest_closed_bar": row.get("db_lag_bars_vs_mt5_latest_closed_bar", ""),
        "db_lag_minutes_vs_mt5_latest_closed_bar": row.get("db_lag_minutes_vs_mt5_latest_closed_bar", ""),
        "live_alignment_status": row.get("live_alignment_status", ""),
        "signal_evidence": {
            "decision_label": child_manifest.get("decision_label", ""),
            "dry_run_status": child_manifest.get("dry_run_status", ""),
            "session_observed": row.get("session_observed", ""),
            "spread": row.get("spread", ""),
            "feature_row_spread_broker_points": row.get("feature_row_spread_broker_points", ""),
            "feature_row_spread_source": row.get("feature_row_spread_source", ""),
            "current_broker_spread_points": row.get("current_broker_spread_points", ""),
            "current_broker_spread_source": row.get("current_broker_spread_source", ""),
            "current_broker_spread_within_policy": row.get("current_broker_spread_within_policy", ""),
            "current_broker_spread_policy_max_points": row.get("current_broker_spread_policy_max_points", ""),
            "live_spread_gate_status": row.get("live_spread_gate_status", ""),
            "spread_source": row.get("spread_source", ""),
            "spread_unit": row.get("spread_unit", ""),
            "max_spread_points": row.get("max_spread_points", ""),
            "close_to_ma_fast_atr_20_bucket": row.get("close_to_ma_fast_atr_20_bucket", ""),
            "tick_volume_percentile_100_bucket": row.get("tick_volume_percentile_100_bucket", ""),
            "skip_reason_count": row.get("skip_reason_count", ""),
            "block_reason_count": row.get("block_reason_count", ""),
        },
        "price_preview": {
            "entry_reference_price": row.get("entry_reference_price", ""),
            "tp_price_preview": row.get("tp_price_preview", ""),
            "sl_price_preview": row.get("sl_price_preview", ""),
            "close": row.get("close", ""),
            "atr_20": row.get("atr_20", ""),
        },
        "risk_preview_status": child_manifest.get("volume_preview_status", "not_computed_no_order_calc_forbidden"),
        "state_preview_status": child_manifest.get("existing_open_state_detected", ""),
        "no_order_boundary": {
            "cycle_no_order_boundary_confirmed": cycle_manifest.get("no_order_boundary_confirmed", False),
            "no_order_execution_performed": True,
            "no_order_request_constructed": True,
            "no_demo_broker_approval_performed": True,
        },
        "caveats": [
            "shadow_signal_artifact_only",
            "manual_review_required_before_any_future_step",
            "order_execution_forbidden",
            "order_request_construction_forbidden",
        ],
        "recommended_next_step": recommended_next_step(
            shadow_status,
            str(row.get("live_spread_gate_status") or ""),
            str(row.get("live_alignment_status") or ""),
        ),
    }


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    shadow_status: str,
    row: dict[str, Any],
    command_rows: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    lines = [
        "# Fixed Candidate Demo Shadow Signal Once",
        "",
        "Single-shot live-demo shadow signal artifact. It is not demo order execution.",
        "This wrapper is not a scheduler and does not add a loop or background task.",
        "No order execution was performed.",
        "No broker order request was constructed.",
        "No order_check or order_calc call was performed.",
        "No broker approval was performed.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- canonical_registry: `{args.canonical_registry}`",
        f"- no_order_cycle_script: `{args.no_order_cycle_script}`",
        f"- existing_no_order_cycle_dir: `{args.existing_no_order_cycle_dir or ''}`",
        f"- run_cycle: `{bool_text(bool(args.run_cycle))}`",
        f"- dry_run: `{bool_text(bool(args.dry_run))}`",
        "",
        "## Cycle Source Summary",
        "",
        f"- cycle_status: `{row.get('cycle_status', '')}`",
        f"- cycle_manifest_path: `{row.get('cycle_manifest_path', '')}`",
        f"- child_dry_run_manifest_path: `{row.get('child_dry_run_manifest_path', '')}`",
        "",
        "## Shadow Status Summary",
        "",
        f"- shadow_status: `{shadow_status}`",
        f"- shadow_decision_label: `{row.get('shadow_decision_label', '')}`",
        f"- manual_review_required: `{row.get('manual_review_required', '')}`",
        "",
        "## Live Alignment Summary",
        "",
        f"- evaluated_feature_time_server: `{row.get('evaluated_feature_time_server', '')}`",
        f"- db_refresh_before_shadow_enabled: `{row.get('db_refresh_before_shadow_enabled', '')}`",
        f"- mt5_time_basis_checked: `{row.get('mt5_time_basis_checked', '')}`",
        f"- latest_db_price_bar_time_server_before_import: `{row.get('latest_db_price_bar_time_server_before_import', '')}`",
        f"- latest_db_feature_time_server_before_generation: `{row.get('latest_db_feature_time_server_before_generation', '')}`",
        f"- effective_import_from_date: `{row.get('effective_import_from_date', '')}`",
        f"- effective_import_to_date: `{row.get('effective_import_to_date', '')}`",
        f"- effective_import_to_date_source: `{row.get('effective_import_to_date_source', '')}`",
        f"- latest_db_price_bar_time_server_after_import: `{row.get('latest_db_price_bar_time_server_after_import', '')}`",
        f"- latest_db_feature_time_server_after_generation: `{row.get('latest_db_feature_time_server_after_generation', '')}`",
        f"- imported_rows_count: `{row.get('imported_rows_count', '')}`",
        f"- generated_features_count: `{row.get('generated_features_count', '')}`",
        f"- latest_db_price_bar_time_server: `{row.get('latest_db_price_bar_time_server', '')}`",
        f"- latest_db_feature_time_server: `{row.get('latest_db_feature_time_server', '')}`",
        f"- latest_mt5_closed_bar_time_server: `{row.get('latest_mt5_closed_bar_time_server', '')}`",
        f"- db_lag_bars_vs_mt5_latest_closed_bar: `{row.get('db_lag_bars_vs_mt5_latest_closed_bar', '')}`",
        f"- db_lag_minutes_vs_mt5_latest_closed_bar: `{row.get('db_lag_minutes_vs_mt5_latest_closed_bar', '')}`",
        f"- live_alignment_status: `{row.get('live_alignment_status', '')}`",
        "",
        "## Spread Basis",
        "",
        f"- feature_row_spread_broker_points: `{row.get('feature_row_spread_broker_points', '')}`",
        f"- feature_row_spread_source: `{row.get('feature_row_spread_source', '')}`",
        f"- current_broker_spread_points: `{row.get('current_broker_spread_points', '')}`",
        f"- current_broker_spread_source: `{row.get('current_broker_spread_source', '')}`",
        f"- current_broker_spread_within_policy: `{row.get('current_broker_spread_within_policy', '')}`",
        f"- current_broker_spread_policy_max_points: `{row.get('current_broker_spread_policy_max_points', '')}`",
        f"- live_spread_gate_status: `{row.get('live_spread_gate_status', '')}`",
        f"- spread_source: `{row.get('spread_source', '')}`",
        "",
    ]
    if shadow_status == "shadow_no_signal":
        lines.extend(["## Skip Summary", "", f"- skip_reason_count: `{row.get('skip_reason_count', '')}`", ""])
    if shadow_status == "shadow_signal_detected":
        lines.extend(
            [
                "## Manual Review Packet Summary",
                "",
                f"- entry_reference_price: `{row.get('entry_reference_price', '')}`",
                f"- tp_price_preview: `{row.get('tp_price_preview', '')}`",
                f"- sl_price_preview: `{row.get('sl_price_preview', '')}`",
                "Manual review is required. No demo broker action is approved.",
                "",
            ]
        )
    if shadow_status in {"shadow_blocked", "blocked_missing_required_artifact", "blocked_unreadable_input", "blocked_by_cycle_status", "blocked_by_no_order_boundary", "blocked_child_command_failed", "blocked_child_manifest_missing", "blocked_by_config_boundary"}:
        lines.extend(["## Blocker Summary", "", f"- block_reason_count: `{row.get('block_reason_count', '')}`"])
        for warning in warnings:
            if str(warning.get("blocking_warning")).lower() == "true":
                lines.append(f"- {warning.get('warning_code')}: {warning.get('message')}")
        lines.append("")
    lines.extend(["## Child Command Plan", ""])
    if command_rows:
        for command in command_rows:
            lines.append(f"- {command['child_step']}: `{command['command_executable']} {command['command_args_json']}`")
    else:
        lines.append("- No child command planned.")
    lines.extend(["", "## Child Execution Summary", ""])
    if result_rows:
        for result in result_rows:
            lines.append(f"- {result['child_step']}: `{result['child_status']}` return_code=`{result['return_code']}`")
    else:
        lines.append("- No child command executed.")
    lines.extend(
        [
            "",
            "## No-Order Boundary Summary",
            "",
            "- no_order_execution_performed: `true`",
            "- no_order_request_constructed: `true`",
            "- no_order_check_called: `true`",
            "- no_order_calc_margin_called: `true`",
            "- no_order_calc_profit_called: `true`",
            "- no_scheduler_added: `true`",
            "- no_loop_added: `true`",
            "- no_background_task_added: `true`",
            "",
            "## Recommended Next Step",
            "",
            f"`{recommended_next_step(shadow_status, str(row.get('live_spread_gate_status') or ''), str(row.get('live_alignment_status') or ''))}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def manifest_payload(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    registry: dict[str, Any],
    row: dict[str, Any],
    shadow_status: str,
    cycle_manifest: dict[str, Any],
    cycle_manifest_path_value: Path | None,
    child_manifest_path_value: Path | None,
    command_rows: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    missing, unsafe = boundary_counts(cycle_manifest) if cycle_manifest else ([], [])
    if shadow_status == "shadow_signal_plan_only":
        missing, unsafe = [], []
    return {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "canonical_registry_path": str(args.canonical_registry),
        "no_order_cycle_script": str(args.no_order_cycle_script),
        "existing_no_order_cycle_dir": str(args.existing_no_order_cycle_dir or ""),
        "run_cycle": bool(args.run_cycle),
        "dry_run": bool(args.dry_run),
        "shadow_status": shadow_status,
        "shadow_decision_label": row.get("shadow_decision_label", ""),
        "cycle_status": row.get("cycle_status", ""),
        "cycle_manifest_path": str(cycle_manifest_path_value or ""),
        "child_dry_run_manifest_path": str(child_manifest_path_value or ""),
        "child_command_count": len(command_rows),
        "child_success_count": sum(1 for result in result_rows if result.get("child_status") == "success"),
        "child_failure_count": sum(1 for result in result_rows if result.get("child_status") == "failed"),
        "candidate_id": registry.get("candidate_id", EXPECTED_CANDIDATE_ID),
        "symbol": registry.get("symbol", EXPECTED_SYMBOL),
        "timeframe": registry.get("timeframe", EXPECTED_TIMEFRAME),
        "direction": registry.get("direction", EXPECTED_DIRECTION),
        "spread_unit": row.get("spread_unit") or registry.get("spread_unit", EXPECTED_SPREAD_UNIT),
        "max_spread_points": safe_float(row.get("max_spread_points") or registry.get("max_spread_points")),
        "time_server": row.get("time_server", ""),
        "evaluated_feature_time_server": row.get("evaluated_feature_time_server", ""),
        "time_server_source": row.get("time_server_source", ""),
        "import_time_basis": row.get("import_time_basis", ""),
        "db_refresh_before_shadow_enabled": row.get("db_refresh_before_shadow_enabled", ""),
        "mt5_time_basis_checked": row.get("mt5_time_basis_checked", ""),
        "pc_utc_now": row.get("pc_utc_now", ""),
        "mt5_tick_time_server": row.get("mt5_tick_time_server", ""),
        "latest_mt5_closed_bar_time_server": row.get("latest_mt5_closed_bar_time_server", ""),
        "latest_db_price_bar_time_server_before_import": row.get("latest_db_price_bar_time_server_before_import", ""),
        "latest_db_feature_time_server_before_generation": row.get("latest_db_feature_time_server_before_generation", ""),
        "effective_import_from_date": row.get("effective_import_from_date", ""),
        "effective_import_to_date": row.get("effective_import_to_date", ""),
        "effective_import_to_date_source": row.get("effective_import_to_date_source", ""),
        "latest_db_price_bar_time_server_after_import": row.get("latest_db_price_bar_time_server_after_import", ""),
        "latest_db_feature_time_server_after_generation": row.get("latest_db_feature_time_server_after_generation", ""),
        "imported_rows_count": row.get("imported_rows_count", ""),
        "generated_features_count": row.get("generated_features_count", ""),
        "latest_db_price_bar_time_server": row.get("latest_db_price_bar_time_server", ""),
        "latest_db_feature_time_server": row.get("latest_db_feature_time_server", ""),
        "db_lag_bars_vs_mt5_latest_closed_bar": row.get("db_lag_bars_vs_mt5_latest_closed_bar", ""),
        "db_lag_minutes_vs_mt5_latest_closed_bar": row.get("db_lag_minutes_vs_mt5_latest_closed_bar", ""),
        "mt5_server_time_offset_seconds_vs_pc_utc": row.get("mt5_server_time_offset_seconds_vs_pc_utc", ""),
        "live_alignment_status": row.get("live_alignment_status", ""),
        "session_observed": row.get("session_observed", ""),
        "spread": row.get("spread", ""),
        "feature_row_spread_broker_points": row.get("feature_row_spread_broker_points", ""),
        "feature_row_spread_source": row.get("feature_row_spread_source", ""),
        "current_broker_spread_points": row.get("current_broker_spread_points", ""),
        "current_broker_spread_source": row.get("current_broker_spread_source", ""),
        "current_broker_spread_within_policy": row.get("current_broker_spread_within_policy", ""),
        "current_broker_spread_policy_max_points": row.get("current_broker_spread_policy_max_points", ""),
        "live_spread_gate_status": row.get("live_spread_gate_status", ""),
        "spread_source": row.get("spread_source", ""),
        "spread_within_gate": row.get("spread_within_gate", ""),
        "close": row.get("close", ""),
        "atr_20": row.get("atr_20", ""),
        "close_to_ma_fast_atr_20_bucket": row.get("close_to_ma_fast_atr_20_bucket", ""),
        "tick_volume_percentile_100_bucket": row.get("tick_volume_percentile_100_bucket", ""),
        "entry_reference_price": row.get("entry_reference_price", ""),
        "tp_price_preview": row.get("tp_price_preview", ""),
        "sl_price_preview": row.get("sl_price_preview", ""),
        "manual_review_required": bool(row.get("manual_review_required")),
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "order_execution_performed": False,
        "order_check_called": False,
        "order_send_called": False,
        "order_request_constructed": False,
        "demo_broker_approval_performed": False,
        "future_state_json_written": False,
        "no_order_boundary_confirmed": not missing and not unsafe and bool(cycle_manifest),
        "missing_no_order_flag_count": len(missing),
        "unsafe_no_order_flag_count": len(unsafe),
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_trading_decision_performed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "recommended_next_step": recommended_next_step(
            shadow_status,
            str(row.get("live_spread_gate_status") or ""),
            str(row.get("live_alignment_status") or ""),
        ),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
    }


def value_is_missing(value: Any) -> bool:
    return value in ("", None)


def value_is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def console_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return bool_text(value)
    return str(value)


def condition_marker(observed: Any, expected: str) -> str:
    return "OK" if observed == expected else "MISSING"


def spread_marker(spread_within_gate: Any) -> str:
    if value_is_missing(spread_within_gate):
        return "MISSING"
    return "OK" if value_is_true(spread_within_gate) else "BLOCKED"


def console_is_blocked(manifest: dict[str, Any]) -> bool:
    shadow_status = str(manifest.get("shadow_status") or "")
    blocking_count = safe_int(manifest.get("blocking_warnings_count")) or 0
    unsafe_count = safe_int(manifest.get("unsafe_no_order_flag_count")) or 0
    return blocking_count > 0 or unsafe_count > 0 or shadow_status == "shadow_blocked" or shadow_status.startswith("blocked_")


def console_status(manifest: dict[str, Any]) -> str:
    shadow_status = str(manifest.get("shadow_status") or "")
    if console_is_blocked(manifest):
        return "BLOCKED"
    if shadow_status == "shadow_signal_detected":
        return "SIGNAL DETECTED"
    if shadow_status == "shadow_no_signal":
        return "NO SIGNAL"
    return "BLOCKED"


def console_verdict(manifest: dict[str, Any]) -> str:
    if console_is_blocked(manifest):
        return "BLOCKED - inspect warnings before continuing"
    if manifest.get("shadow_status") == "shadow_signal_detected":
        return "VALID SIGNAL - proceed with manual approval prep dry-run"
    if manifest.get("shadow_status") == "shadow_no_signal":
        return "NO VALID SIGNAL - wait for next M15 candle"
    return "REVIEW REQUIRED - inspect manifest/report"


def missing_conditions(row: dict[str, Any]) -> list[str]:
    conditions = [
        ("session_observed", "Off_hours"),
        ("close_to_ma_fast_atr_20_bucket", "high_tercile"),
        ("tick_volume_percentile_100_bucket", "mid_tercile"),
    ]
    missing = [
        f"{field} expected {expected} observed {console_value(row.get(field)) or '<missing>'}"
        for field, expected in conditions
        if row.get(field) != expected
    ]
    if not value_is_true(row.get("spread_within_gate")):
        observed = console_value(row.get("spread")) or "<missing>"
        maximum = console_value(row.get("max_spread_points")) or console_value(EXPECTED_MAX_SPREAD_POINTS)
        missing.append(f"spread expected <= {maximum} {EXPECTED_SPREAD_UNIT} observed {observed}")
    if row.get("live_spread_gate_status") in {"blocked_current_spread_above_policy", "blocked_current_spread_unavailable"}:
        observed = console_value(row.get("current_broker_spread_points")) or "<missing>"
        maximum = console_value(row.get("current_broker_spread_policy_max_points")) or console_value(row.get("max_spread_points")) or console_value(EXPECTED_MAX_SPREAD_POINTS)
        missing.append(f"current live spread expected <= {maximum} {EXPECTED_SPREAD_UNIT} observed {observed}")
    if row.get("live_alignment_status") in LIVE_ALIGNMENT_BLOCK_STATUSES:
        observed = console_value(row.get("latest_db_feature_time_server")) or "<missing>"
        expected = console_value(row.get("latest_mt5_closed_bar_time_server")) or "<missing>"
        missing.append(f"latest DB feature/bar expected aligned with MT5 latest closed bar {expected} observed {observed}")
    return missing


def print_console_summary(manifest: dict[str, Any], row: dict[str, Any]) -> None:
    spread_unit = console_value(row.get("spread_unit")) or EXPECTED_SPREAD_UNIT
    lines = [
        "=== FIXED CANDIDATE SHADOW SIGNAL SUMMARY ===",
        f"status: {console_status(manifest)}",
        f"shadow_status: {console_value(manifest.get('shadow_status'))}",
        f"shadow_decision_label: {console_value(manifest.get('shadow_decision_label'))}",
        f"cycle_status: {console_value(manifest.get('cycle_status'))}",
        f"db_refresh_before_shadow_enabled: {console_value(row.get('db_refresh_before_shadow_enabled'))}",
        f"mt5_time_basis_checked: {console_value(row.get('mt5_time_basis_checked'))}",
        f"effective_import_from_date: {console_value(row.get('effective_import_from_date'))}",
        f"effective_import_to_date: {console_value(row.get('effective_import_to_date'))}",
        f"effective_import_to_date_source: {console_value(row.get('effective_import_to_date_source'))}",
        f"latest_db_price_bar_time_server_before_import: {console_value(row.get('latest_db_price_bar_time_server_before_import'))}",
        f"latest_db_feature_time_server_before_generation: {console_value(row.get('latest_db_feature_time_server_before_generation'))}",
        f"evaluated_feature_time_server: {console_value(row.get('evaluated_feature_time_server') or row.get('time_server'))}",
        f"latest_db_price_bar_time_server: {console_value(row.get('latest_db_price_bar_time_server'))}",
        f"latest_db_feature_time_server: {console_value(row.get('latest_db_feature_time_server'))}",
        f"latest_mt5_closed_bar_time_server: {console_value(row.get('latest_mt5_closed_bar_time_server'))}",
        f"db_lag_bars_vs_mt5_latest_closed_bar: {console_value(row.get('db_lag_bars_vs_mt5_latest_closed_bar'))}",
        f"live_alignment_status: {console_value(row.get('live_alignment_status'))}",
        f"symbol: {console_value(manifest.get('symbol')) or EXPECTED_SYMBOL}",
        f"timeframe: {console_value(manifest.get('timeframe')) or EXPECTED_TIMEFRAME}",
        f"direction: {console_value(manifest.get('direction')) or EXPECTED_DIRECTION}",
        f"session_observed: {console_value(row.get('session_observed'))} [{condition_marker(row.get('session_observed'), 'Off_hours')}]",
        "expected_session: Off_hours",
        f"close_to_ma_fast_atr_20_bucket: {console_value(row.get('close_to_ma_fast_atr_20_bucket'))} [{condition_marker(row.get('close_to_ma_fast_atr_20_bucket'), 'high_tercile')}]",
        "expected_close_bucket: high_tercile",
        f"tick_volume_percentile_100_bucket: {console_value(row.get('tick_volume_percentile_100_bucket'))} [{condition_marker(row.get('tick_volume_percentile_100_bucket'), 'mid_tercile')}]",
        "expected_volume_bucket: mid_tercile",
        f"feature_row_spread_broker_points: {console_value(first_present(row.get('feature_row_spread_broker_points'), row.get('spread')))} {spread_unit} [{spread_marker(row.get('spread_within_gate'))}]",
        f"feature_row_spread_source: {console_value(row.get('feature_row_spread_source')) or 'db_candle_spread'}",
        f"current_broker_spread_points: {console_value(row.get('current_broker_spread_points'))}",
        f"current_broker_spread_source: {console_value(row.get('current_broker_spread_source'))}",
        f"current_broker_spread_within_policy: {console_value(row.get('current_broker_spread_within_policy'))}",
        f"live_spread_gate_status: {console_value(row.get('live_spread_gate_status'))}",
        f"spread_source: {console_value(row.get('spread_source')) or 'db_candle_spread'}",
        f"max_spread_points: {console_value(row.get('max_spread_points')) or console_value(EXPECTED_MAX_SPREAD_POINTS)}",
        f"manual_review_required: {console_value(row.get('manual_review_required'))}",
        f"entry_reference_price: {console_value(row.get('entry_reference_price'))}",
        f"sl_price_preview: {console_value(row.get('sl_price_preview'))}",
        f"tp_price_preview: {console_value(row.get('tp_price_preview'))}",
        f"skip_reason_count: {console_value(row.get('skip_reason_count'))}",
        f"block_reason_count: {console_value(row.get('block_reason_count'))}",
        f"recommended_next_step: {console_value(manifest.get('recommended_next_step'))}",
    ]
    missing = missing_conditions(row)
    if missing:
        lines.append("missing_conditions:")
        lines.extend(f"- {condition}" for condition in missing)
    lines.append(f"RESULT: {console_verdict(manifest)}")
    print("\n".join(lines))


def print_console_summary_from_outputs(paths: dict[str, Path]) -> None:
    manifest, manifest_error = read_json(paths["manifest"])
    row, row_error = read_first_csv_row(paths["main"])
    if manifest_error or row_error:
        raise ValueError(f"Unable to read final summary artifacts. manifest={manifest_error}; main={row_error}")
    print_console_summary(manifest, row)


def print_console_error_summary(message: str) -> None:
    print(
        "\n".join(
            [
                "=== FIXED CANDIDATE SHADOW SIGNAL SUMMARY ===",
                "status: ERROR",
                "shadow_status: ",
                "shadow_decision_label: ",
                "cycle_status: ",
                f"error: {message}",
                "RESULT: ERROR - inspect terminal error and inputs",
            ]
        )
    )


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    warnings: list[dict[str, Any]] = []
    registry, registry_error = read_json(Path(args.canonical_registry))
    command = build_child_command(args, output_dir)
    initial_status = initial_block_status(args=args, registry=registry, registry_error=registry_error, command=command, warnings=warnings)

    command_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    cycle_manifest: dict[str, Any] = {}
    child_manifest: dict[str, Any] = {}
    cycle_manifest_path_value: Path | None = None
    child_manifest_path_value: Path | None = None
    shadow_status = "shadow_signal_plan_only"
    shadow_decision_label = "plan_only"

    if command is not None:
        command_rows.append(command_row(args, command, planned_only=bool(args.dry_run)))

    if initial_status:
        shadow_status = initial_status
        shadow_decision_label = "blocked"
        if command is not None:
            result_rows.append(not_executed_result(args, command, "not_executed_blocked"))
    elif args.dry_run and (args.run_cycle or not args.existing_no_order_cycle_dir):
        shadow_status = "shadow_signal_plan_only"
        shadow_decision_label = "plan_only"
        if command is not None:
            result_rows.append(not_executed_result(args, command, "not_executed_dry_run"))
    else:
        if args.run_cycle and command is not None:
            result = run_child(args, command)
            result_rows.append(result)
            if result["child_status"] != "success":
                add_warning(warnings, args=args, warning_code="child_command_failed", message="No-order cycle child command failed.", source=args.no_order_cycle_script, blocking_warning=True)
                shadow_status = "blocked_child_command_failed"
                shadow_decision_label = "blocked"
            else:
                block_status, cycle_manifest, cycle_manifest_path_value, child_manifest, child_manifest_path_value = load_cycle_and_child(args=args, command=command, warnings=warnings)
                if block_status:
                    shadow_status = block_status
                    shadow_decision_label = "blocked"
                else:
                    shadow_status, shadow_decision_label = shadow_from_cycle(cycle_manifest, child_manifest)
        else:
            block_status, cycle_manifest, cycle_manifest_path_value, child_manifest, child_manifest_path_value = load_cycle_and_child(args=args, command=command, warnings=warnings)
            if block_status:
                shadow_status = block_status
                shadow_decision_label = "blocked"
            elif not cycle_manifest and not args.existing_no_order_cycle_dir:
                shadow_status = "blocked_missing_required_artifact"
                shadow_decision_label = "blocked"
                add_warning(warnings, args=args, warning_code="cycle_source_missing", message="Provide --existing-no-order-cycle-dir or --run-cycle unless using --dry-run plan-only.", source=output_dir, blocking_warning=True)
            else:
                shadow_status, shadow_decision_label = shadow_from_cycle(cycle_manifest, child_manifest)

    row = main_row(
        args=args,
        registry=registry,
        shadow_status=shadow_status,
        shadow_decision_label=shadow_decision_label,
        cycle_manifest=cycle_manifest,
        cycle_manifest_path_value=cycle_manifest_path_value,
        child_manifest=child_manifest,
        child_manifest_path_value=child_manifest_path_value,
    )
    packet = review_packet(args=args, registry=registry, row=row, cycle_manifest=cycle_manifest, child_manifest=child_manifest, shadow_status=shadow_status)
    manifest = manifest_payload(
        args=args,
        output_dir=output_dir,
        registry=registry,
        row=row,
        shadow_status=shadow_status,
        cycle_manifest=cycle_manifest,
        cycle_manifest_path_value=cycle_manifest_path_value,
        child_manifest_path_value=child_manifest_path_value,
        command_rows=command_rows,
        result_rows=result_rows,
        warnings=warnings,
    )

    write_json(paths["manifest"], manifest)
    write_csv(paths["main"], [row], MAIN_FIELDNAMES)
    write_csv(paths["child_commands"], command_rows, COMMAND_FIELDNAMES)
    write_csv(paths["child_results"], result_rows, RESULT_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["no_order_evidence"], [no_order_evidence_row(args)], NO_ORDER_EVIDENCE_FIELDNAMES)
    write_json(paths["review_packet"], packet)
    write_report(paths["report"], args=args, shadow_status=shadow_status, row=row, command_rows=command_rows, result_rows=result_rows, warnings=warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build one fixed-candidate demo shadow-signal artifact from a no-order cycle.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--no-order-cycle-script", type=Path, default=DEFAULT_NO_ORDER_CYCLE_SCRIPT)
    parser.add_argument("--existing-no-order-cycle-dir", type=Path)
    parser.add_argument("--run-cycle", action="store_true")
    parser.add_argument("--cycle-run-id")
    parser.add_argument("--cycle-output-dir", type=Path)
    parser.add_argument("--python-executable", default="python")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
        print_console_summary_from_outputs(paths)
    except Exception as exc:
        print(f"Fixed-candidate demo shadow signal once failed: {exc}")
        print_console_error_summary(str(exc))
        return 1
    print("Fixed-candidate demo shadow signal once complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
