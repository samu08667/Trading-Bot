"""Run one controlled local paper-cycle orchestration step.

This single-shot orchestrator chooses which existing local paper/artifact
script to run next: freshness readiness, paper signal logger, paper trade
tracker, or paper cycle summary. It never loops, schedules itself, refreshes
features, generates data, mutates the database, connects to MT5, connects to
broker/API services, executes orders, runs validation/backtests, or makes
candidate-quality or trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_local_paper_cycle_once"
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR
    / "config"
    / "paper_demo"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)
DEFAULT_DEMO_STRATEGY_SPEC_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_strategy_spec"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v4"
)
DEFAULT_PAPER_SIGNAL_LOGGER_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger_readiness"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_readiness_v3"
)
DEFAULT_NUMERIC_TERCILE_THRESHOLDS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_numeric_tercile_thresholds"
    / "gbpusd_short_h10_1_5_off_hours_numeric_tercile_thresholds_v1"
)
DEFAULT_FEATURE_SOURCE_DB = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_FEATURE_SOURCE_TABLE = "price_features"
DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_MAX_STALENESS_HOURS = 24.0
DEFAULT_PREVIOUS_PAPER_STATE_JSON = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_trade_tracker"
    / "gbpusd_short_h10_1_5_off_hours_paper_trade_tracker_v2"
    / "fixed_candidate_paper_trade_tracker_state.json"
)
DEFAULT_PREVIOUS_PAPER_SIGNAL_LOGGER_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_v2"
)
DEFAULT_PREVIOUS_PAPER_TRADE_TRACKER_DIRS = [
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_trade_tracker"
    / "gbpusd_short_h10_1_5_off_hours_paper_trade_tracker_v1",
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_trade_tracker"
    / "gbpusd_short_h10_1_5_off_hours_paper_trade_tracker_v2",
]
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_local_paper_cycle_once"

CHILD_SCRIPT_PATHS = {
    "freshness": BASE_DIR / "scripts" / "build_fixed_candidate_paper_input_freshness_readiness.py",
    "signal_logger": BASE_DIR / "scripts" / "run_fixed_candidate_paper_signal_logger.py",
    "trade_tracker": BASE_DIR / "scripts" / "run_fixed_candidate_paper_trade_tracker.py",
    "cycle_summary": BASE_DIR / "scripts" / "build_fixed_candidate_paper_cycle_summary.py",
}
ALLOWED_CHILD_SCRIPT_KEYS = {
    "scripts/build_fixed_candidate_paper_input_freshness_readiness.py",
    "scripts/run_fixed_candidate_paper_signal_logger.py",
    "scripts/run_fixed_candidate_paper_trade_tracker.py",
    "scripts/build_fixed_candidate_paper_cycle_summary.py",
}

SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_REPORT = "fixed_candidate_demo_strategy_spec_report.md"
SPEC_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"
SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"

READINESS_CSV = "fixed_candidate_paper_signal_logger_readiness.csv"
READINESS_REPORT = "fixed_candidate_paper_signal_logger_readiness_report.md"
READINESS_WARNINGS = "fixed_candidate_paper_signal_logger_readiness_warnings.csv"
READINESS_MANIFEST = "fixed_candidate_paper_signal_logger_readiness_manifest.json"

THRESHOLDS_JSON = "fixed_candidate_numeric_tercile_thresholds.json"
THRESHOLDS_REPORT = "fixed_candidate_numeric_tercile_thresholds_report.md"
THRESHOLDS_WARNINGS = "fixed_candidate_numeric_tercile_thresholds_warnings.csv"
THRESHOLDS_MANIFEST = "fixed_candidate_numeric_tercile_thresholds_manifest.json"

SIGNAL_CSV = "fixed_candidate_paper_signal_log.csv"
SIGNAL_REPORT = "fixed_candidate_paper_signal_logger_report.md"
SIGNAL_WARNINGS = "fixed_candidate_paper_signal_logger_warnings.csv"
SIGNAL_MANIFEST = "fixed_candidate_paper_signal_logger_manifest.json"

TRACKER_CSV = "fixed_candidate_paper_trade_tracker.csv"
TRACKER_REPORT = "fixed_candidate_paper_trade_tracker_report.md"
TRACKER_WARNINGS = "fixed_candidate_paper_trade_tracker_warnings.csv"
TRACKER_MANIFEST = "fixed_candidate_paper_trade_tracker_manifest.json"

FRESHNESS_MANIFEST = "fixed_candidate_paper_input_freshness_readiness_manifest.json"
SIGNAL_CHILD_MANIFEST = "fixed_candidate_paper_signal_logger_manifest.json"
TRACKER_CHILD_MANIFEST = "fixed_candidate_paper_trade_tracker_manifest.json"
CYCLE_SUMMARY_MANIFEST = "fixed_candidate_paper_cycle_summary_manifest.json"

OUTPUT_CSV = "fixed_candidate_local_paper_cycle_once.csv"
OUTPUT_REPORT = "fixed_candidate_local_paper_cycle_once_report.md"
OUTPUT_WARNINGS = "fixed_candidate_local_paper_cycle_once_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_local_paper_cycle_once_manifest.json"
OUTPUT_CHILD_COMMANDS = "fixed_candidate_local_paper_cycle_once_child_commands.csv"
OUTPUT_CHILD_RESULTS = "fixed_candidate_local_paper_cycle_once_child_results.csv"

FIELDNAMES = [
    "run_id",
    "row_type",
    "step_order",
    "step_name",
    "artifact_status",
    "orchestrator_status",
    "child_script",
    "child_command",
    "child_output_dir",
    "child_returncode",
    "source_path",
    "observed_value",
    "expected_value",
    "evidence_label",
    "caveat",
    "warning_code",
    "blocking_warning",
]

COMMAND_FIELDNAMES = [
    "run_id",
    "command_order",
    "child_role",
    "child_script",
    "command",
    "output_dir",
    "planned",
    "executed",
    "allowed_child_script",
    "heavy",
    "requires_manual_refresh",
    "no_broker_api_mt5",
    "no_order_execution",
]

RESULT_FIELDNAMES = [
    "run_id",
    "command_order",
    "child_role",
    "child_script",
    "output_dir",
    "returncode",
    "status",
    "started_at",
    "finished_at",
    "stdout_log",
    "stderr_log",
    "manifest_path",
    "child_status_summary",
]

WARNING_FIELDNAMES = [
    "run_id",
    "warning_code",
    "severity",
    "message",
    "source",
    "blocking_warning",
]

SAFETY_FIELDS = (
    "no_broker_connection_performed",
    "no_order_execution_performed",
    "no_db_mutation_performed",
    "no_data_generation_performed",
    "no_trading_decision_performed",
)


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


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def labels(*values: str) -> str:
    return ";".join(value for value in values if value)


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, ""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(value, dict):
        return {}, "JSON root must be an object"
    return value, ""


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], ""
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), ""
    except (OSError, csv.Error) as exc:
        return [], str(exc)


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
        "orchestrator": output_dir / OUTPUT_CSV,
        "report": output_dir / OUTPUT_REPORT,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "manifest": output_dir / OUTPUT_MANIFEST,
        "child_commands": output_dir / OUTPUT_CHILD_COMMANDS,
        "child_results": output_dir / OUTPUT_CHILD_RESULTS,
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
        "blocking_warning": bool_text(blocking_warning),
    }


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
    warning_code: str,
    message: str,
    source: Path | str,
    blocking_warning: bool = False,
    severity: str = "warning",
) -> None:
    warnings.append(
        warning_row(
            run_id=args.run_id,
            warning_code=warning_code,
            message=message,
            source=source,
            blocking_warning=blocking_warning,
            severity=severity,
        )
    )


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [warning for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"]


def base_row(args: argparse.Namespace, row_type: str, step_order: int, step_name: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "row_type": row_type,
        "step_order": step_order,
        "step_name": step_name,
        "artifact_status": "available",
        "orchestrator_status": "",
        "child_script": "",
        "child_command": "",
        "child_output_dir": "",
        "child_returncode": "",
        "source_path": "",
        "observed_value": "",
        "expected_value": "",
        "evidence_label": "",
        "caveat": "no_trading_decision_made",
        "warning_code": "",
        "blocking_warning": False,
    }


def load_bundle(root: Path, csv_name: str, manifest_name: str, report_name: str, warnings_name: str) -> dict[str, Any]:
    csv_path = root / csv_name
    manifest_path = root / manifest_name
    report_path = root / report_name
    warnings_path = root / warnings_name
    rows, csv_error = read_csv_rows(csv_path)
    manifest, manifest_error = read_json(manifest_path)
    warning_rows, warnings_error = read_csv_rows(warnings_path)
    report = read_text(report_path)
    files_present = csv_path.exists() and manifest_path.exists() and report_path.exists()
    return {
        "dir": root,
        "csv_path": csv_path,
        "manifest_path": manifest_path,
        "report_path": report_path,
        "warnings_path": warnings_path,
        "rows": rows,
        "manifest": manifest,
        "warnings": warning_rows,
        "report": report,
        "files_present": files_present,
        "error": labels(csv_error, manifest_error, warnings_error),
        "loaded": files_present and not (csv_error or manifest_error or warnings_error),
    }


def load_json_artifact(root: Path, json_name: str, manifest_name: str, report_name: str, warnings_name: str) -> dict[str, Any]:
    json_path = root / json_name
    manifest_path = root / manifest_name
    report_path = root / report_name
    warnings_path = root / warnings_name
    payload, json_error = read_json(json_path)
    manifest, manifest_error = read_json(manifest_path)
    warning_rows, warnings_error = read_csv_rows(warnings_path)
    report = read_text(report_path)
    files_present = json_path.exists() and manifest_path.exists() and report_path.exists()
    return {
        "dir": root,
        "json_path": json_path,
        "manifest_path": manifest_path,
        "report_path": report_path,
        "warnings_path": warnings_path,
        "payload": payload,
        "manifest": manifest,
        "warnings": warning_rows,
        "report": report,
        "files_present": files_present,
        "error": labels(json_error, manifest_error, warnings_error),
        "loaded": files_present and not (json_error or manifest_error or warnings_error),
    }


def artifact_status(bundle: dict[str, Any]) -> str:
    if bundle.get("loaded"):
        return "available"
    if bundle.get("files_present"):
        return "unreadable"
    return "missing"


def safety_ok_from_manifest(manifest: dict[str, Any]) -> bool:
    for field in SAFETY_FIELDS:
        if field in manifest and manifest.get(field) is not True:
            return False
    return True


def script_key(path: Path) -> str:
    normalized = path.as_posix().replace("\\", "/")
    if "/scripts/" in normalized:
        return "scripts/" + normalized.rsplit("/scripts/", 1)[1]
    if normalized.startswith("scripts/"):
        return normalized
    return normalized


def is_allowed_child_script(path: Path) -> bool:
    return script_key(path) in ALLOWED_CHILD_SCRIPT_KEYS


def command_to_string(command: list[str]) -> str:
    return subprocess.list2cmdline([str(item) for item in command])


def make_command(
    args: argparse.Namespace,
    *,
    role: str,
    order: int,
    output_dir: Path,
    extra_args: list[str],
) -> dict[str, Any]:
    script = Path(CHILD_SCRIPT_PATHS[role])
    command = [str(args.python_executable), str(script), *extra_args, "--output-dir", str(output_dir), "--overwrite"]
    allowed = is_allowed_child_script(script)
    return {
        "run_id": args.run_id,
        "command_order": order,
        "child_role": role,
        "child_script": str(script),
        "command": command_to_string(command),
        "command_list": command,
        "output_dir": str(output_dir),
        "planned": True,
        "executed": False,
        "allowed_child_script": allowed,
        "heavy": False,
        "requires_manual_refresh": False,
        "no_broker_api_mt5": True,
        "no_order_execution": True,
    }


def child_manifest_name(role: str) -> str:
    return {
        "freshness": FRESHNESS_MANIFEST,
        "signal_logger": SIGNAL_CHILD_MANIFEST,
        "trade_tracker": TRACKER_CHILD_MANIFEST,
        "cycle_summary": CYCLE_SUMMARY_MANIFEST,
    }[role]


def run_child_command(command: list[str], stdout_log: Path, stderr_log: Path) -> int:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    stdout_log.write_text(result.stdout or "", encoding="utf-8")
    stderr_log.write_text(result.stderr or "", encoding="utf-8")
    return int(result.returncode)


def execute_child(args: argparse.Namespace, command_row: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(command_row["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now_text()
    stdout_log = output_dir / f"{command_row['child_role']}_stdout.log"
    stderr_log = output_dir / f"{command_row['child_role']}_stderr.log"
    returncode = run_child_command(list(command_row["command_list"]), stdout_log, stderr_log)
    finished_at = utc_now_text()
    manifest_path = output_dir / child_manifest_name(str(command_row["child_role"]))
    manifest, manifest_error = read_json(manifest_path)
    status = "success" if returncode == 0 and not manifest_error and manifest_path.exists() else "failed"
    summary = ""
    if manifest:
        summary = labels(
            str(manifest.get("recommended_next_step") or ""),
            str(manifest.get("signal_state") or ""),
            str(manifest.get("trade_status") or ""),
            str(manifest.get("final_cycle_status") or ""),
            "stale_input_source" if manifest.get("stale_input_source") is True else "",
        )
    elif manifest_error:
        summary = manifest_error
    command_row["executed"] = True
    return {
        "run_id": args.run_id,
        "command_order": command_row["command_order"],
        "child_role": command_row["child_role"],
        "child_script": command_row["child_script"],
        "output_dir": command_row["output_dir"],
        "returncode": returncode,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout_log": stdout_log,
        "stderr_log": stderr_log,
        "manifest_path": manifest_path,
        "manifest": manifest,
        "child_status_summary": summary,
    }


def not_executed_result(args: argparse.Namespace, command_row: dict[str, Any], status: str = "not_executed") -> dict[str, Any]:
    manifest_path = Path(command_row["output_dir"]) / child_manifest_name(str(command_row["child_role"]))
    return {
        "run_id": args.run_id,
        "command_order": command_row["command_order"],
        "child_role": command_row["child_role"],
        "child_script": command_row["child_script"],
        "output_dir": command_row["output_dir"],
        "returncode": "",
        "status": status,
        "started_at": "",
        "finished_at": "",
        "stdout_log": "",
        "stderr_log": "",
        "manifest_path": manifest_path,
        "manifest": {},
        "child_status_summary": status,
    }


def load_previous_context(args: argparse.Namespace) -> dict[str, Any]:
    config, config_error = read_json(Path(args.demo_strategy_config))
    spec = load_bundle(Path(args.demo_strategy_spec_dir), SPEC_CSV, SPEC_MANIFEST, SPEC_REPORT, SPEC_WARNINGS)
    readiness = load_bundle(
        Path(args.paper_signal_logger_readiness_dir),
        READINESS_CSV,
        READINESS_MANIFEST,
        READINESS_REPORT,
        READINESS_WARNINGS,
    )
    thresholds = load_json_artifact(
        Path(args.numeric_tercile_thresholds_dir),
        THRESHOLDS_JSON,
        THRESHOLDS_MANIFEST,
        THRESHOLDS_REPORT,
        THRESHOLDS_WARNINGS,
    )
    state, state_error = read_json(Path(args.previous_paper_state_json))
    signal = load_bundle(Path(args.previous_paper_signal_logger_dir), SIGNAL_CSV, SIGNAL_MANIFEST, SIGNAL_REPORT, SIGNAL_WARNINGS)
    return {
        "config": config,
        "config_error": config_error,
        "config_exists": Path(args.demo_strategy_config).exists(),
        "spec": spec,
        "readiness": readiness,
        "thresholds": thresholds,
        "state": state,
        "state_error": state_error,
        "state_exists": Path(args.previous_paper_state_json).exists(),
        "signal": signal,
        "trackers": [
            load_bundle(Path(path), TRACKER_CSV, TRACKER_MANIFEST, TRACKER_REPORT, TRACKER_WARNINGS)
            for path in args.previous_paper_trade_tracker_dirs
        ],
    }


def add_gate_rows(args: argparse.Namespace, context: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    config_ok = bool(
        context["config_exists"]
        and not context["config_error"]
        and context["config"].get("paper_only") is True
        and context["config"].get("broker_connection_allowed") is False
        and context["config"].get("order_execution_allowed") is False
        and context["config"].get("real_money_allowed") is False
    )
    gates = [
        ("config_gate", "config_gate", Path(args.demo_strategy_config), config_ok, "paper_only_boundary_confirmed"),
        (
            "spec_gate",
            "spec_gate",
            Path(args.demo_strategy_spec_dir),
            context["spec"].get("loaded") and context["spec"]["manifest"].get("paper_only_specification") is True,
            "paper_only_boundary_confirmed",
        ),
        (
            "readiness_gate",
            "readiness_gate",
            Path(args.paper_signal_logger_readiness_dir),
            context["readiness"].get("loaded") and safety_ok_from_manifest(context["readiness"]["manifest"]),
            "paper_only_boundary_confirmed",
        ),
        (
            "thresholds_gate",
            "thresholds_gate",
            Path(args.numeric_tercile_thresholds_dir),
            context["thresholds"].get("loaded"),
            "numeric_tercile_thresholds_available",
        ),
    ]
    for index, (row_type, step_name, source_path, ok, label) in enumerate(gates, start=1):
        row = base_row(args, row_type, index, step_name)
        row.update(
            {
                "artifact_status": "available" if ok else "missing",
                "source_path": source_path,
                "observed_value": bool_text(bool(ok)),
                "expected_value": "true",
                "evidence_label": label if ok else "",
                "warning_code": "" if ok else f"{step_name}_blocked",
                "blocking_warning": not ok,
            }
        )
        rows.append(row)


def validate_initial_context(args: argparse.Namespace, context: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    config_ok = bool(
        context["config_exists"]
        and not context["config_error"]
        and context["config"].get("paper_only") is True
        and context["config"].get("broker_connection_allowed") is False
        and context["config"].get("order_execution_allowed") is False
        and context["config"].get("real_money_allowed") is False
    )
    spec_ok = bool(context["spec"].get("loaded") and context["spec"]["manifest"].get("paper_only_specification") is True)
    readiness_ok = bool(context["readiness"].get("loaded") and safety_ok_from_manifest(context["readiness"]["manifest"]))
    thresholds_ok = bool(context["thresholds"].get("loaded"))
    if not config_ok:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_only_boundary_not_confirmed",
            message="Demo strategy config does not preserve required local paper-only boundary flags.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    if not spec_ok:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_spec_unreadable_or_missing",
            message="Demo strategy spec is missing, unreadable, or does not confirm paper-only specification.",
            source=args.demo_strategy_spec_dir,
            blocking_warning=True,
        )
    if not readiness_ok:
        add_warning(
            warnings,
            args=args,
            warning_code="paper_signal_logger_readiness_unreadable_or_missing",
            message="Paper signal logger readiness artifact is missing, unreadable, or does not preserve safety boundaries.",
            source=args.paper_signal_logger_readiness_dir,
            blocking_warning=True,
        )
    if not thresholds_ok:
        add_warning(
            warnings,
            args=args,
            warning_code="numeric_tercile_thresholds_unreadable_or_missing",
            message="Numeric tercile threshold artifact is missing or unreadable.",
            source=args.numeric_tercile_thresholds_dir,
            blocking_warning=True,
        )
    unsafe_previous = []
    for name, bundle in [("previous_paper_signal_logger", context["signal"])] + [
        (f"previous_paper_trade_tracker_{index}", tracker)
        for index, tracker in enumerate(context["trackers"], start=1)
    ]:
        if bundle.get("loaded") and not safety_ok_from_manifest(bundle["manifest"]):
            unsafe_previous.append(name)
            add_warning(
                warnings,
                args=args,
                warning_code="previous_artifact_boundary_not_confirmed",
                message=f"{name} manifest does not preserve required local paper-only safety fields.",
                source=bundle["dir"],
                blocking_warning=True,
            )
    return {
        "config_ok": config_ok,
        "spec_ok": spec_ok,
        "readiness_ok": readiness_ok,
        "thresholds_ok": thresholds_ok,
        "previous_artifacts_ok": not unsafe_previous,
        "paper_only_boundary_confirmed": config_ok and spec_ok and readiness_ok and thresholds_ok and not unsafe_previous,
    }


def thresholds_json_path(args: argparse.Namespace) -> Path:
    return Path(args.numeric_tercile_thresholds_dir) / THRESHOLDS_JSON


def build_freshness_command(args: argparse.Namespace, output_dir: Path, order: int) -> dict[str, Any]:
    return make_command(
        args,
        role="freshness",
        order=order,
        output_dir=output_dir,
        extra_args=[
            "--run-id",
            f"{args.run_id}_freshness_readiness",
            "--demo-strategy-config",
            str(args.demo_strategy_config),
            "--demo-strategy-spec-dir",
            str(args.demo_strategy_spec_dir),
            "--paper-signal-logger-readiness-dir",
            str(args.paper_signal_logger_readiness_dir),
            "--paper-signal-logger-dir",
            str(args.previous_paper_signal_logger_dir),
            "--feature-source-db",
            str(args.feature_source_db),
            "--feature-source-table",
            str(args.feature_source_table),
            "--symbol",
            str(args.symbol),
            "--timeframe",
            str(args.timeframe),
            "--max-staleness-hours",
            str(args.max_staleness_hours),
        ],
    )


def build_signal_command(args: argparse.Namespace, output_dir: Path, order: int) -> dict[str, Any]:
    return make_command(
        args,
        role="signal_logger",
        order=order,
        output_dir=output_dir,
        extra_args=[
            "--run-id",
            f"{args.run_id}_paper_signal_logger",
            "--demo-strategy-config",
            str(args.demo_strategy_config),
            "--demo-strategy-spec-dir",
            str(args.demo_strategy_spec_dir),
            "--paper-signal-logger-readiness-dir",
            str(args.paper_signal_logger_readiness_dir),
            "--tercile-thresholds-json",
            str(thresholds_json_path(args)),
            "--feature-source-db",
            str(args.feature_source_db),
            "--feature-source-table",
            str(args.feature_source_table),
            "--state-json",
            str(args.previous_paper_state_json),
        ],
    )


def build_tracker_command(args: argparse.Namespace, output_dir: Path, order: int) -> dict[str, Any]:
    return make_command(
        args,
        role="trade_tracker",
        order=order,
        output_dir=output_dir,
        extra_args=[
            "--run-id",
            f"{args.run_id}_paper_trade_tracker",
            "--demo-strategy-config",
            str(args.demo_strategy_config),
            "--demo-strategy-spec-dir",
            str(args.demo_strategy_spec_dir),
            "--paper-signal-logger-dir",
            str(args.previous_paper_signal_logger_dir),
            "--paper-signal-state-json",
            str(args.previous_paper_state_json),
            "--feature-source-db",
            str(args.feature_source_db),
            "--feature-source-table",
            str(args.feature_source_table),
            "--symbol",
            str(args.symbol),
            "--timeframe",
            str(args.timeframe),
        ],
    )


def build_summary_command(args: argparse.Namespace, output_dir: Path, tracker_child_output_dir: Path, order: int) -> dict[str, Any]:
    tracker_dirs = [str(path) for path in args.previous_paper_trade_tracker_dirs] + [str(tracker_child_output_dir)]
    return make_command(
        args,
        role="cycle_summary",
        order=order,
        output_dir=output_dir,
        extra_args=[
            "--run-id",
            f"{args.run_id}_paper_cycle_summary",
            "--demo-strategy-config",
            str(args.demo_strategy_config),
            "--demo-strategy-spec-dir",
            str(args.demo_strategy_spec_dir),
            "--paper-signal-logger-readiness-dir",
            str(args.paper_signal_logger_readiness_dir),
            "--numeric-tercile-thresholds-dir",
            str(args.numeric_tercile_thresholds_dir),
            "--paper-signal-logger-dir",
            str(args.previous_paper_signal_logger_dir),
            "--paper-trade-tracker-dirs",
            *tracker_dirs,
        ],
    )


def add_command_row(rows: list[dict[str, Any]], args: argparse.Namespace, command: dict[str, Any], status: str, step_name: str, row_type: str) -> None:
    row = base_row(args, row_type, int(command["command_order"]), step_name)
    row.update(
        {
            "orchestrator_status": status,
            "child_script": command["child_script"],
            "child_command": command["command"],
            "child_output_dir": command["output_dir"],
            "evidence_label": f"{command['child_role']}_planned",
            "caveat": "single_shot_local_child_script_only",
            "warning_code": "" if command["allowed_child_script"] else "child_script_not_allowlisted",
            "blocking_warning": not bool(command["allowed_child_script"]),
        }
    )
    rows.append(row)


def check_command_allowlist(args: argparse.Namespace, commands: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> bool:
    ok = True
    for command in commands:
        if not command["allowed_child_script"]:
            ok = False
            add_warning(
                warnings,
                args=args,
                warning_code="child_script_not_allowlisted",
                message=f"Child script is outside the local paper allowlist: {command['child_script']}",
                source=command["child_script"],
                blocking_warning=True,
            )
    return ok


def previous_has_open_trade(context: dict[str, Any]) -> bool | None:
    state = context.get("state") or {}
    if not state:
        return None
    return bool(state.get("has_open_paper_trade"))


def build_artifacts(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any]:
    output_dir = paths["manifest"].parent
    child_dirs = {
        "freshness": output_dir / "child_freshness_readiness",
        "signal_logger": output_dir / "child_paper_signal_logger",
        "trade_tracker": output_dir / "child_paper_trade_tracker",
        "cycle_summary": output_dir / "child_paper_cycle_summary",
    }
    rows: list[dict[str, Any]] = []
    command_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    context = load_previous_context(args)
    add_gate_rows(args, context, rows)
    validation = validate_initial_context(args, context, warnings)
    has_open_before = previous_has_open_trade(context)
    state_row = base_row(args, "previous_state_context", 5, "previous_state_context")
    state_row.update(
        {
            "artifact_status": "available" if context["state_exists"] and not context["state_error"] else "missing",
            "source_path": args.previous_paper_state_json,
            "observed_value": has_open_before,
            "expected_value": "readable_previous_state",
            "evidence_label": "previous_state_has_open_trade"
            if has_open_before is True
            else "previous_state_has_no_open_trade"
            if has_open_before is False
            else "",
            "warning_code": "previous_state_unreadable_or_missing" if has_open_before is None else "",
            "blocking_warning": False,
        }
    )
    rows.append(state_row)

    freshness_command = build_freshness_command(args, child_dirs["freshness"], 1)
    command_rows.append(freshness_command)
    add_command_row(rows, args, freshness_command, "dry_run_planned_only" if args.dry_run else "", "freshness_step", "freshness_step")
    if args.dry_run:
        if has_open_before is True:
            tracker_command = build_tracker_command(args, child_dirs["trade_tracker"], 2)
            command_rows.append(tracker_command)
            add_command_row(rows, args, tracker_command, "dry_run_planned_only", "trade_tracker_step", "trade_tracker_step")
        elif has_open_before is False:
            signal_command = build_signal_command(args, child_dirs["signal_logger"], 2)
            command_rows.append(signal_command)
            add_command_row(rows, args, signal_command, "dry_run_planned_only", "signal_logger_step", "signal_logger_step")
        check_command_allowlist(args, command_rows, warnings)
        result_rows = [not_executed_result(args, command, "not_executed_dry_run") for command in command_rows]
        return finalize_outputs(
            args=args,
            paths=paths,
            rows=rows,
            command_rows=command_rows,
            result_rows=result_rows,
            warnings=warnings,
            status="dry_run_planned_only",
            recommended_next_step="review_child_command_plan",
            context=context,
            validation=validation,
            child_dirs=child_dirs,
            latest_child_manifest_path="",
            final_has_open=has_open_before,
        )

    if not validation["paper_only_boundary_confirmed"]:
        status = "blocked_by_previous_artifact_boundary" if not validation["previous_artifacts_ok"] else "blocked_by_config"
        check_command_allowlist(args, command_rows, warnings)
        result_rows = [not_executed_result(args, command, "not_executed_blocked") for command in command_rows]
        return finalize_outputs(
            args=args,
            paths=paths,
            rows=rows,
            command_rows=command_rows,
            result_rows=result_rows,
            warnings=warnings,
            status=status,
            recommended_next_step="fix_config_or_previous_artifact_boundary",
            context=context,
            validation=validation,
            child_dirs=child_dirs,
            latest_child_manifest_path="",
            final_has_open=has_open_before,
        )
    if not check_command_allowlist(args, command_rows, warnings):
        result_rows = [not_executed_result(args, command, "not_executed_blocked") for command in command_rows]
        return finalize_outputs(
            args=args,
            paths=paths,
            rows=rows,
            command_rows=command_rows,
            result_rows=result_rows,
            warnings=warnings,
            status="blocked_by_config",
            recommended_next_step="fix_child_script_allowlist",
            context=context,
            validation=validation,
            child_dirs=child_dirs,
            latest_child_manifest_path="",
            final_has_open=has_open_before,
        )

    freshness_result = execute_child(args, freshness_command)
    result_rows.append(freshness_result)
    if freshness_result["status"] != "success":
        add_warning(
            warnings,
            args=args,
            warning_code="failed_child_script",
            message="Freshness readiness child script failed.",
            source=freshness_command["child_script"],
            blocking_warning=True,
        )
        return finalize_outputs(
            args=args,
            paths=paths,
            rows=rows,
            command_rows=command_rows,
            result_rows=result_rows,
            warnings=warnings,
            status="failed_child_script",
            recommended_next_step="inspect_child_logs",
            context=context,
            validation=validation,
            child_dirs=child_dirs,
            latest_child_manifest_path=str(freshness_result["manifest_path"]),
            final_has_open=has_open_before,
        )
    freshness_manifest = freshness_result["manifest"]
    if freshness_manifest.get("stale_input_source") is True:
        decision = base_row(args, "decision_step", 2, "freshness_decision")
        decision.update(
            {
                "orchestrator_status": "blocked_stale_input_source",
                "observed_value": "stale_input_source=true",
                "expected_value": "stale_input_source=false",
                "evidence_label": "stale_input_source_detected",
                "caveat": "manual_feature_source_refresh_required",
            }
        )
        rows.append(decision)
        return finalize_outputs(
            args=args,
            paths=paths,
            rows=rows,
            command_rows=command_rows,
            result_rows=result_rows,
            warnings=warnings,
            status="blocked_stale_input_source",
            recommended_next_step="manual_feature_source_refresh_required",
            context=context,
            validation=validation,
            child_dirs=child_dirs,
            latest_child_manifest_path=str(freshness_result["manifest_path"]),
            final_has_open=has_open_before,
        )

    if has_open_before is None:
        add_warning(
            warnings,
            args=args,
            warning_code="previous_state_unreadable_or_missing",
            message="Previous paper state is missing or unreadable; no child logger/tracker step was run.",
            source=args.previous_paper_state_json,
            blocking_warning=True,
        )
        return finalize_outputs(
            args=args,
            paths=paths,
            rows=rows,
            command_rows=command_rows,
            result_rows=result_rows,
            warnings=warnings,
            status="blocked_missing_or_unreadable_state",
            recommended_next_step="fix_or_review_previous_paper_state",
            context=context,
            validation=validation,
            child_dirs=child_dirs,
            latest_child_manifest_path=str(freshness_result["manifest_path"]),
            final_has_open=None,
        )

    if has_open_before is True:
        tracker_command = build_tracker_command(args, child_dirs["trade_tracker"], 2)
        command_rows.append(tracker_command)
        add_command_row(rows, args, tracker_command, "", "trade_tracker_step", "trade_tracker_step")
        if not check_command_allowlist(args, [tracker_command], warnings):
            result_rows.append(not_executed_result(args, tracker_command, "not_executed_blocked"))
            return finalize_outputs(
                args=args,
                paths=paths,
                rows=rows,
                command_rows=command_rows,
                result_rows=result_rows,
                warnings=warnings,
                status="blocked_by_config",
                recommended_next_step="fix_child_script_allowlist",
                context=context,
                validation=validation,
                child_dirs=child_dirs,
                latest_child_manifest_path=str(freshness_result["manifest_path"]),
                final_has_open=True,
            )
        tracker_result = execute_child(args, tracker_command)
        result_rows.append(tracker_result)
        if tracker_result["status"] != "success":
            add_warning(
                warnings,
                args=args,
                warning_code="failed_child_script",
                message="Paper trade tracker child script failed.",
                source=tracker_command["child_script"],
                blocking_warning=True,
            )
            return finalize_outputs(
                args=args,
                paths=paths,
                rows=rows,
                command_rows=command_rows,
                result_rows=result_rows,
                warnings=warnings,
                status="failed_child_script",
                recommended_next_step="inspect_child_logs",
                context=context,
                validation=validation,
                child_dirs=child_dirs,
                latest_child_manifest_path=str(tracker_result["manifest_path"]),
                final_has_open=True,
            )
        tracker_manifest = tracker_result["manifest"]
        if tracker_manifest.get("has_open_paper_trade_after") is True:
            return finalize_outputs(
                args=args,
                paths=paths,
                rows=rows,
                command_rows=command_rows,
                result_rows=result_rows,
                warnings=warnings,
                status="paper_trade_still_open_after_tracker",
                recommended_next_step="rerun_tracker_after_feature_refresh",
                context=context,
                validation=validation,
                child_dirs=child_dirs,
                latest_child_manifest_path=str(tracker_result["manifest_path"]),
                final_has_open=True,
                trade_status=str(tracker_manifest.get("trade_status") or ""),
            )
        summary_command = build_summary_command(args, child_dirs["cycle_summary"], child_dirs["trade_tracker"], 3)
        command_rows.append(summary_command)
        add_command_row(rows, args, summary_command, "", "cycle_summary_step", "cycle_summary_step")
        if not check_command_allowlist(args, [summary_command], warnings):
            result_rows.append(not_executed_result(args, summary_command, "not_executed_blocked"))
            return finalize_outputs(
                args=args,
                paths=paths,
                rows=rows,
                command_rows=command_rows,
                result_rows=result_rows,
                warnings=warnings,
                status="blocked_by_config",
                recommended_next_step="fix_child_script_allowlist",
                context=context,
                validation=validation,
                child_dirs=child_dirs,
                latest_child_manifest_path=str(tracker_result["manifest_path"]),
                final_has_open=False,
                trade_status=str(tracker_manifest.get("trade_status") or ""),
            )
        summary_result = execute_child(args, summary_command)
        result_rows.append(summary_result)
        if summary_result["status"] != "success":
            add_warning(
                warnings,
                args=args,
                warning_code="failed_child_script",
                message="Paper cycle summary child script failed.",
                source=summary_command["child_script"],
                blocking_warning=True,
            )
            return finalize_outputs(
                args=args,
                paths=paths,
                rows=rows,
                command_rows=command_rows,
                result_rows=result_rows,
                warnings=warnings,
                status="failed_child_script",
                recommended_next_step="inspect_child_logs",
                context=context,
                validation=validation,
                child_dirs=child_dirs,
                latest_child_manifest_path=str(summary_result["manifest_path"]),
                final_has_open=False,
                trade_status=str(tracker_manifest.get("trade_status") or ""),
            )
        return finalize_outputs(
            args=args,
            paths=paths,
            rows=rows,
            command_rows=command_rows,
            result_rows=result_rows,
            warnings=warnings,
            status="paper_trade_closed_and_summary_built",
            recommended_next_step="review_paper_cycle_summary",
            context=context,
            validation=validation,
            child_dirs=child_dirs,
            latest_child_manifest_path=str(summary_result["manifest_path"]),
            final_has_open=False,
            trade_status=str(tracker_manifest.get("trade_status") or ""),
            final_cycle_status=str(summary_result["manifest"].get("final_cycle_status") or ""),
        )

    signal_command = build_signal_command(args, child_dirs["signal_logger"], 2)
    command_rows.append(signal_command)
    add_command_row(rows, args, signal_command, "", "signal_logger_step", "signal_logger_step")
    if not check_command_allowlist(args, [signal_command], warnings):
        result_rows.append(not_executed_result(args, signal_command, "not_executed_blocked"))
        return finalize_outputs(
            args=args,
            paths=paths,
            rows=rows,
            command_rows=command_rows,
            result_rows=result_rows,
            warnings=warnings,
            status="blocked_by_config",
            recommended_next_step="fix_child_script_allowlist",
            context=context,
            validation=validation,
            child_dirs=child_dirs,
            latest_child_manifest_path=str(freshness_result["manifest_path"]),
            final_has_open=False,
        )
    signal_result = execute_child(args, signal_command)
    result_rows.append(signal_result)
    if signal_result["status"] != "success":
        add_warning(
            warnings,
            args=args,
            warning_code="failed_child_script",
            message="Paper signal logger child script failed.",
            source=signal_command["child_script"],
            blocking_warning=True,
        )
        return finalize_outputs(
            args=args,
            paths=paths,
            rows=rows,
            command_rows=command_rows,
            result_rows=result_rows,
            warnings=warnings,
            status="failed_child_script",
            recommended_next_step="inspect_child_logs",
            context=context,
            validation=validation,
            child_dirs=child_dirs,
            latest_child_manifest_path=str(signal_result["manifest_path"]),
            final_has_open=False,
        )
    signal_manifest = signal_result["manifest"]
    signal_state = str(signal_manifest.get("signal_state") or "")
    status = "paper_signal_opened" if signal_state == "paper_signal_opened" else "paper_signal_skipped"
    return finalize_outputs(
        args=args,
        paths=paths,
        rows=rows,
        command_rows=command_rows,
        result_rows=result_rows,
        warnings=warnings,
        status=status,
        recommended_next_step="track_open_paper_trade_next" if status == "paper_signal_opened" else "rerun_when_fresh_data_available",
        context=context,
        validation=validation,
        child_dirs=child_dirs,
        latest_child_manifest_path=str(signal_result["manifest_path"]),
        final_has_open=bool(signal_manifest.get("has_open_paper_trade_after")),
        signal_state=signal_state,
    )


def finalize_outputs(
    *,
    args: argparse.Namespace,
    paths: dict[str, Path],
    rows: list[dict[str, Any]],
    command_rows: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    status: str,
    recommended_next_step: str,
    context: dict[str, Any],
    validation: dict[str, Any],
    child_dirs: dict[str, Path],
    latest_child_manifest_path: str,
    final_has_open: bool | None,
    signal_state: str = "",
    trade_status: str = "",
    final_cycle_status: str = "",
) -> dict[str, Any]:
    outcome = base_row(args, "orchestrator_outcome", 99, "orchestrator_outcome")
    outcome.update(
        {
            "orchestrator_status": status,
            "observed_value": status,
            "expected_value": "single_shot_local_artifact_step",
            "evidence_label": labels(
                "freshness_checked" if command_rows else "",
                "no_broker_connection_performed",
                "no_order_execution_performed",
                "no_db_mutation_performed",
                "no_data_generation_performed",
                "no_trading_decision_made",
            ),
            "caveat": "local_paper_orchestrator_not_broker_or_demo_execution",
            "blocking_warning": status.startswith("blocked") or status == "failed_child_script",
            "warning_code": status if status.startswith("blocked") or status == "failed_child_script" else "",
        }
    )
    rows.append(outcome)
    next_row = base_row(args, "next_step", 100, "recommended_next_manual_step")
    next_row.update(
        {
            "orchestrator_status": status,
            "observed_value": recommended_next_step,
            "evidence_label": recommended_next_step,
            "caveat": "manual_step_only_no_trading_decision_made",
        }
    )
    rows.append(next_row)
    write_csv(paths["orchestrator"], rows, FIELDNAMES)
    write_csv(paths["child_commands"], command_rows, COMMAND_FIELDNAMES)
    write_csv(paths["child_results"], result_rows, RESULT_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    metadata = {
        "status": status,
        "recommended_next_step": recommended_next_step,
        "context": context,
        "validation": validation,
        "child_dirs": child_dirs,
        "latest_child_manifest_path": latest_child_manifest_path,
        "final_has_open": final_has_open,
        "signal_state": signal_state,
        "trade_status": trade_status,
        "final_cycle_status": final_cycle_status,
    }
    write_report(paths["report"], args=args, rows=rows, command_rows=command_rows, result_rows=result_rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=paths["manifest"].parent, rows=rows, command_rows=command_rows, result_rows=result_rows, warnings=warnings, metadata=metadata)
    return metadata


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    command_rows: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    lines = [
        "# Fixed Candidate Local Paper Cycle Once",
        "",
        "Single-shot local orchestrator artifact. This run does not loop, schedule itself, or stay resident.",
        "No feature refresh was performed.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation was performed.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- demo_strategy_spec_dir: `{args.demo_strategy_spec_dir}`",
        f"- paper_signal_logger_readiness_dir: `{args.paper_signal_logger_readiness_dir}`",
        f"- numeric_tercile_thresholds_dir: `{args.numeric_tercile_thresholds_dir}`",
        f"- previous_paper_state_json: `{args.previous_paper_state_json}`",
        f"- previous_paper_signal_logger_dir: `{args.previous_paper_signal_logger_dir}`",
        f"- previous_paper_trade_tracker_dirs: `{', '.join(str(path) for path in args.previous_paper_trade_tracker_dirs)}`",
        "",
        "## Previous State Summary",
        "",
        f"- previous_has_open_paper_trade: `{previous_has_open_trade(metadata['context'])}`",
        "",
        "## Child Command Plan Summary",
        "",
        f"- child_command_count: `{len(command_rows)}`",
        f"- child_executed_count: `{sum(str(row.get('executed')).lower() == 'true' for row in command_rows)}`",
        "",
        "## Executed Child Steps Summary",
        "",
    ]
    for result in result_rows:
        lines.append(
            f"- {result.get('child_role')}: `{result.get('status')}` `{result.get('child_status_summary', '')}`"
        )
    lines.extend(
        [
            "",
            "## Freshness Decision",
            "",
            f"`{metadata['status']}`",
            "",
            "## Final Orchestrator Outcome",
            "",
            f"- orchestrator_status: `{metadata['status']}`",
            f"- signal_state: `{metadata['signal_state']}`",
            f"- trade_status: `{metadata['trade_status']}`",
            f"- final_cycle_status: `{metadata['final_cycle_status']}`",
            "",
            "## Recommended Next Manual Step",
            "",
            f"`{metadata['recommended_next_step']}`",
            "",
            "## Warnings",
            "",
            f"- warnings_count: `{len(warnings)}`",
            f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    rows: list[dict[str, Any]],
    command_rows: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "paper_signal_logger_readiness_dir": str(args.paper_signal_logger_readiness_dir),
        "numeric_tercile_thresholds_dir": str(args.numeric_tercile_thresholds_dir),
        "feature_source_db": str(args.feature_source_db),
        "feature_source_table": str(args.feature_source_table),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "max_staleness_hours": float(args.max_staleness_hours),
        "previous_paper_state_json": str(args.previous_paper_state_json),
        "previous_paper_signal_logger_dir": str(args.previous_paper_signal_logger_dir),
        "previous_paper_trade_tracker_dirs": [str(path) for path in args.previous_paper_trade_tracker_dirs],
        "dry_run": bool(args.dry_run),
        "orchestrator_status": metadata["status"],
        "recommended_next_step": metadata["recommended_next_step"],
        "child_command_count": len(command_rows),
        "child_executed_count": sum(str(row.get("executed")).lower() == "true" for row in command_rows),
        "child_failed_count": sum(1 for row in result_rows if row.get("status") == "failed"),
        "freshness_child_output_dir": str(metadata["child_dirs"]["freshness"]),
        "paper_signal_logger_child_output_dir": str(metadata["child_dirs"]["signal_logger"]),
        "paper_trade_tracker_child_output_dir": str(metadata["child_dirs"]["trade_tracker"]),
        "paper_cycle_summary_child_output_dir": str(metadata["child_dirs"]["cycle_summary"]),
        "latest_child_manifest_path": metadata["latest_child_manifest_path"],
        "previous_has_open_paper_trade": previous_has_open_trade(metadata["context"]),
        "final_has_open_paper_trade": metadata["final_has_open"],
        "signal_state": metadata["signal_state"],
        "trade_status": metadata["trade_status"],
        "final_cycle_status": metadata["final_cycle_status"],
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "paper_only_boundary_confirmed": bool(metadata["validation"].get("paper_only_boundary_confirmed")),
        "no_child_scripts_outside_allowlist_executed": True,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_backtests_run": True,
        "no_stress_validation_executed": True,
        "no_walk_forward_validation_executed": True,
        "no_timeout_policy_review_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    build_artifacts(args, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one controlled fixed-candidate local paper cycle step.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--paper-signal-logger-readiness-dir", type=Path, default=DEFAULT_PAPER_SIGNAL_LOGGER_READINESS_DIR)
    parser.add_argument("--numeric-tercile-thresholds-dir", type=Path, default=DEFAULT_NUMERIC_TERCILE_THRESHOLDS_DIR)
    parser.add_argument("--feature-source-db", type=Path, default=DEFAULT_FEATURE_SOURCE_DB)
    parser.add_argument("--feature-source-table", default=DEFAULT_FEATURE_SOURCE_TABLE)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--max-staleness-hours", type=float, default=DEFAULT_MAX_STALENESS_HOURS)
    parser.add_argument("--previous-paper-state-json", type=Path, default=DEFAULT_PREVIOUS_PAPER_STATE_JSON)
    parser.add_argument("--previous-paper-signal-logger-dir", type=Path, default=DEFAULT_PREVIOUS_PAPER_SIGNAL_LOGGER_DIR)
    parser.add_argument(
        "--previous-paper-trade-tracker-dirs",
        type=Path,
        nargs="+",
        default=DEFAULT_PREVIOUS_PAPER_TRADE_TRACKER_DIRS,
    )
    parser.add_argument("--python-executable", default="python")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate local paper cycle once failed: {exc}")
        return 1
    print("Fixed-candidate local paper cycle once complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
