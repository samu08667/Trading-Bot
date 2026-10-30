"""Build an artifact-only command plan for a future paper signal logger.

This module reads the fixed-candidate demo strategy specification and canonical
paper/demo config, then writes a command-plan artifact. It does not implement or
run a paper runner, connect to MT5, connect to broker/API services, place
orders, run backtests, run validation, mutate a database, or make candidate or
trading decisions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_paper_runner_command_plan"
DEFAULT_DEMO_STRATEGY_SPEC_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_strategy_spec"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v3"
)
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR
    / "config"
    / "paper_demo"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)
DEFAULT_FINAL_RESEARCH_DECISION_READINESS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_final_research_decision_readiness_packet"
    / "gbpusd_short_h10_1_5_off_hours_final_research_decision_readiness_packet_v1"
)
DEFAULT_ARTIFACT_AWARE_CANDIDATE_AUDIT_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_artifact_aware_candidate_audit"
    / "gbpusd_short_h10_1_5_off_hours_artifact_aware_candidate_audit_v1"
)
DEFAULT_PAPER_RUNNER_SCRIPT = BASE_DIR / "scripts" / "run_fixed_candidate_paper_signal_logger.py"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_paper_runner_command_plan"

SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_REPORT = "fixed_candidate_demo_strategy_spec_report.md"
SPEC_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"
SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"

OUTPUT_CSV = "fixed_candidate_paper_runner_command_plan.csv"
OUTPUT_REPORT = "fixed_candidate_paper_runner_command_plan_report.md"
OUTPUT_WARNINGS = "fixed_candidate_paper_runner_command_plan_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_paper_runner_command_plan_manifest.json"

FIELDNAMES = [
    "run_id",
    "plan_step",
    "plan_role",
    "artifact_status",
    "command_status",
    "source_dir",
    "source_config",
    "source_script",
    "expected_output_dir",
    "manual_command",
    "compatibility_status",
    "boundary_status",
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

PAPER_RUNNER_REQUIRED_FLAGS = (
    "--demo-strategy-spec-dir",
    "--demo-strategy-config",
    "--output-dir",
    "--run-id",
    "--overwrite",
)

REQUIRED_LOGGING_FIELDS = (
    "timestamp",
    "symbol",
    "timeframe",
    "feature_values",
    "regime_value",
    "spread",
    "cost_profile",
    "signal_state",
    "entry_reason",
    "exit_reason",
    "R",
    "net_R",
    "bars_held",
    "errors",
    "skipped_reasons",
    "daily_paper_pnl",
    "weekly_paper_pnl",
    "kill_switch_state",
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


def spec_paths(args: argparse.Namespace) -> dict[str, Path]:
    root = Path(args.demo_strategy_spec_dir)
    return {
        "dir": root,
        "csv": root / SPEC_CSV,
        "manifest": root / SPEC_MANIFEST,
        "report": root / SPEC_REPORT,
        "warnings": root / SPEC_WARNINGS,
    }


def load_spec_state(args: argparse.Namespace) -> dict[str, Any]:
    paths = spec_paths(args)
    rows, csv_error = read_csv_rows(paths["csv"])
    manifest, manifest_error = read_json(paths["manifest"])
    warnings, warnings_error = read_csv_rows(paths["warnings"])
    report_text = read_text(paths["report"])
    files_present = paths["csv"].exists() and paths["manifest"].exists() and paths["report"].exists()
    unreadable = bool(csv_error or manifest_error or warnings_error)
    blockers = (
        not files_present
        or unreadable
        or manifest.get("demo_strategy_config_loaded") is not True
        or manifest.get("demo_strategy_config_valid") is not True
        or manifest.get("paper_only_specification") is not True
        or manifest.get("no_broker_connection_performed") is not True
        or manifest.get("no_order_execution_performed") is not True
        or manifest.get("no_trading_decision_performed") is not True
        or int(manifest.get("warnings_count") or 0) != 0
        or int(manifest.get("blocking_warnings_count") or 0) != 0
        or any(str(row.get("blocking_warning") or "").lower() == "true" for row in warnings)
    )
    return {
        "paths": paths,
        "rows": rows,
        "manifest": manifest,
        "warnings": warnings,
        "report_text": report_text,
        "files_present": files_present,
        "unreadable": unreadable,
        "error_message": labels(csv_error, manifest_error, warnings_error),
        "blocked": blockers,
    }


def list_config_value(config: dict[str, Any], *keys: str) -> list[str]:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            return []
        current = current.get(key)
    if isinstance(current, list):
        return [str(item) for item in current]
    return []


def nested_config_value(config: dict[str, Any], *keys: str) -> Any:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def load_config_state(path: Path) -> dict[str, Any]:
    config, error = read_json(path)
    exists = path.exists()
    loaded = exists and not error and bool(config)
    config_role = str(config.get("config_role") or "") if loaded else ""
    candidate_id = str(config.get("candidate_id") or "") if loaded else ""
    logging_fields = list_config_value(config, "logging", "required_fields") if loaded else []
    kill_conditions = list_config_value(config, "kill_switch", "conditions") if loaded else []
    missing_logging_fields = [field for field in REQUIRED_LOGGING_FIELDS if field not in logging_fields]
    max_open = nested_config_value(config, "demo_risk_controls", "max_open_positions_note") if loaded else None
    max_daily = nested_config_value(config, "demo_risk_controls", "max_daily_trades_note") if loaded else None
    spread = nested_config_value(config, "spread_and_session_controls", "spread_threshold_note") if loaded else None
    paper_boundary_ok = bool(
        loaded
        and config.get("paper_only") is True
        and config.get("broker_connection_allowed") is False
        and config.get("order_execution_allowed") is False
        and config.get("real_money_allowed") is False
    )
    required_contract_ok = bool(max_open and max_daily and spread and logging_fields and kill_conditions)
    config_valid = bool(loaded and config_role == "paper_demo_strategy_config" and paper_boundary_ok and required_contract_ok)
    blocked = bool(
        not config_valid
        or config.get("paper_only") is not True
        or config.get("broker_connection_allowed") is not False
        or config.get("order_execution_allowed") is not False
        or config.get("real_money_allowed") is not False
        or not logging_fields
        or not kill_conditions
        or not max_open
        or not max_daily
        or not spread
    )
    return {
        "path": path,
        "config": config if loaded else {},
        "error": error,
        "exists": exists,
        "loaded": loaded,
        "config_valid": config_valid,
        "config_role": config_role,
        "candidate_id": candidate_id,
        "paper_only_boundary_confirmed": bool(loaded and config.get("paper_only") is True),
        "no_broker_connection_allowed": bool(loaded and config.get("broker_connection_allowed") is False),
        "no_order_execution_allowed": bool(loaded and config.get("order_execution_allowed") is False),
        "real_money_not_allowed": bool(loaded and config.get("real_money_allowed") is False),
        "logging_fields": logging_fields,
        "missing_logging_fields": missing_logging_fields,
        "kill_switch_conditions": kill_conditions,
        "max_open_positions_note": max_open or "",
        "max_daily_trades_note": max_daily or "",
        "spread_threshold_note": spread or "",
        "blocked": blocked,
    }


def base_row(args: argparse.Namespace, *, plan_step: str, plan_role: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "plan_step": plan_step,
        "plan_role": plan_role,
        "artifact_status": "available",
        "command_status": "no_command_needed",
        "source_dir": "",
        "source_config": "",
        "source_script": "",
        "expected_output_dir": "",
        "manual_command": "",
        "compatibility_status": "not_applicable",
        "boundary_status": "not_applicable",
        "caveat": "no_trading_decision_made",
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


def add_blocking_warning(
    warnings: list[dict[str, Any]],
    *,
    warning_code: str,
    message: str,
    plan_step: str,
    source_path: Path | str,
) -> None:
    warnings.append(
        warning_row(
            warning_code=warning_code,
            message=message,
            plan_step=plan_step,
            source_path=source_path,
            blocking_warning=True,
        )
    )


def build_manual_command(args: argparse.Namespace, output_dir: Path) -> str:
    expected_output_dir = output_dir / "manual_paper_signal_logger"
    parts = [
        args.python_executable,
        str(args.paper_runner_script),
        "--run-id",
        f"{args.run_id}_paper_signal_logger",
        "--demo-strategy-spec-dir",
        str(args.demo_strategy_spec_dir),
        "--demo-strategy-config",
        str(args.demo_strategy_config),
        "--output-dir",
        str(expected_output_dir),
        "--overwrite",
    ]
    return " ".join(quote_arg(part) for part in parts)


def build_plan_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    spec = load_spec_state(args)
    config = load_config_state(Path(args.demo_strategy_config))
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paper_script = Path(args.paper_runner_script)
    script_supported, script_missing_flags = script_supports_flags(paper_script, PAPER_RUNNER_REQUIRED_FLAGS)
    blocked_by_spec = bool(spec["blocked"])
    blocked_by_config = bool(config["blocked"])
    blocked = blocked_by_spec or blocked_by_config

    rows: list[dict[str, Any]] = []

    spec_gate = base_row(args, plan_step="demo_strategy_spec_gate_check", plan_role="spec_gate")
    spec_gate.update(
        {
            "source_dir": spec["paths"]["dir"],
            "boundary_status": "paper_only_boundary_confirmed" if not blocked_by_spec else "blocked_boundary_violation",
            "caveat": "demo_strategy_spec_clean;no_trading_decision_made",
        }
    )
    if blocked_by_spec:
        spec_gate.update(
            {
                "artifact_status": "missing" if not spec["files_present"] else "available_with_caveat",
                "command_status": "blocked_by_spec",
                "warning_code": "demo_strategy_spec_gate_blocked",
                "blocking_warning": True,
                "required_next_artifact": SPEC_CSV,
            }
        )
        add_blocking_warning(
            warnings,
            warning_code="demo_strategy_spec_gate_blocked",
            message="Demo strategy spec is missing, unreadable, has warnings, or does not preserve the paper/demo boundary.",
            plan_step="demo_strategy_spec_gate_check",
            source_path=spec["paths"]["dir"],
        )
    rows.append(spec_gate)

    config_gate = base_row(args, plan_step="canonical_config_gate_check", plan_role="config_gate")
    config_gate.update(
        {
            "source_config": config["path"],
            "boundary_status": "paper_only_boundary_confirmed" if config["config_valid"] else "blocked_boundary_violation",
            "caveat": labels(
                "canonical_demo_strategy_config_loaded" if config["loaded"] else "",
                "no_trading_decision_made",
            ),
        }
    )
    if blocked_by_config:
        config_gate.update(
            {
                "artifact_status": "missing" if not config["exists"] else "available_with_caveat",
                "command_status": "blocked_by_config",
                "warning_code": "canonical_config_gate_blocked",
                "blocking_warning": True,
                "required_next_artifact": "valid_canonical_demo_strategy_config",
            }
        )
        add_blocking_warning(
            warnings,
            warning_code="canonical_config_gate_blocked",
            message="Canonical demo strategy config is missing, invalid, or violates the paper/demo boundary contract.",
            plan_step="canonical_config_gate_check",
            source_path=config["path"],
        )
    rows.append(config_gate)

    paper_boundary = base_row(args, plan_step="paper_only_boundary_check", plan_role="paper_boundary")
    paper_boundary.update(
        {
            "source_config": config["path"],
            "boundary_status": "paper_only_boundary_confirmed"
            if config["paper_only_boundary_confirmed"]
            else "blocked_boundary_violation",
            "caveat": "paper_only_boundary_confirmed;no_trading_decision_made",
        }
    )
    if not config["paper_only_boundary_confirmed"]:
        paper_boundary.update(
            {
                "command_status": "blocked_by_config",
                "warning_code": "paper_only_boundary_not_confirmed",
                "blocking_warning": True,
            }
        )
        add_blocking_warning(
            warnings,
            warning_code="paper_only_boundary_not_confirmed",
            message="Config does not set paper_only=true.",
            plan_step="paper_only_boundary_check",
            source_path=config["path"],
        )
    rows.append(paper_boundary)

    no_external = base_row(args, plan_step="no_broker_no_order_boundary_check", plan_role="paper_boundary")
    boundary_ok = (
        config["no_broker_connection_allowed"]
        and config["no_order_execution_allowed"]
        and config["real_money_not_allowed"]
    )
    no_external.update(
        {
            "source_config": config["path"],
            "boundary_status": "no_broker_no_order_boundary_confirmed" if boundary_ok else "blocked_boundary_violation",
            "caveat": "no_broker_connection_allowed;no_order_execution_allowed;real_money_not_allowed;no_trading_decision_made",
        }
    )
    if not boundary_ok:
        no_external.update(
            {
                "command_status": "blocked_by_config",
                "warning_code": "no_broker_no_order_boundary_failed",
                "blocking_warning": True,
            }
        )
        add_blocking_warning(
            warnings,
            warning_code="no_broker_no_order_boundary_failed",
            message="Config permits a boundary that is not allowed for this command plan.",
            plan_step="no_broker_no_order_boundary_check",
            source_path=config["path"],
        )
    rows.append(no_external)

    risk = base_row(args, plan_step="risk_controls_contract_check", plan_role="risk_controls")
    risk_ok = bool(config["max_open_positions_note"] and config["max_daily_trades_note"] and config["spread_threshold_note"])
    risk.update(
        {
            "source_config": config["path"],
            "boundary_status": "requires_manual_review" if risk_ok else "blocked_boundary_violation",
            "caveat": labels(
                "max_one_open_paper_trade_required" if config["max_open_positions_note"] else "",
                "spread_threshold_not_numeric_yet" if config["spread_threshold_note"] else "",
                "no_trading_decision_made",
            ),
        }
    )
    if not risk_ok:
        risk.update(
            {
                "command_status": "blocked_by_config",
                "warning_code": "risk_controls_contract_missing",
                "blocking_warning": True,
                "required_next_artifact": "complete_demo_risk_controls_config",
            }
        )
        add_blocking_warning(
            warnings,
            warning_code="risk_controls_contract_missing",
            message="Config is missing max open positions, max daily trades, or spread threshold notes.",
            plan_step="risk_controls_contract_check",
            source_path=config["path"],
        )
    rows.append(risk)

    logging = base_row(args, plan_step="logging_contract_check", plan_role="logging_contract")
    logging_ok = bool(config["logging_fields"]) and not config["missing_logging_fields"]
    logging.update(
        {
            "source_config": config["path"],
            "boundary_status": "requires_manual_review" if logging_ok else "blocked_boundary_violation",
            "caveat": labels(
                "logging_contract_available" if logging_ok else "",
                "missing_logging_fields=" + ",".join(config["missing_logging_fields"]) if config["missing_logging_fields"] else "",
                "no_trading_decision_made",
            ),
        }
    )
    if not logging_ok:
        logging.update(
            {
                "command_status": "blocked_by_config",
                "warning_code": "logging_contract_missing",
                "blocking_warning": True,
                "required_next_artifact": "complete_logging_contract_config",
            }
        )
        add_blocking_warning(
            warnings,
            warning_code="logging_contract_missing",
            message="Config logging.required_fields is missing or incomplete.",
            plan_step="logging_contract_check",
            source_path=config["path"],
        )
    rows.append(logging)

    kill = base_row(args, plan_step="kill_switch_contract_check", plan_role="kill_switch")
    kill_ok = bool(config["kill_switch_conditions"])
    kill.update(
        {
            "source_config": config["path"],
            "boundary_status": "requires_manual_review" if kill_ok else "blocked_boundary_violation",
            "caveat": labels(
                "kill_switch_contract_available" if kill_ok else "",
                "no_trading_decision_made",
            ),
        }
    )
    if not kill_ok:
        kill.update(
            {
                "command_status": "blocked_by_config",
                "warning_code": "kill_switch_contract_missing",
                "blocking_warning": True,
                "required_next_artifact": "complete_kill_switch_contract_config",
            }
        )
        add_blocking_warning(
            warnings,
            warning_code="kill_switch_contract_missing",
            message="Config kill_switch.conditions is missing or empty.",
            plan_step="kill_switch_contract_check",
            source_path=config["path"],
        )
    rows.append(kill)

    script_status = base_row(args, plan_step="paper_runner_script_status", plan_role="paper_runner_script")
    script_status.update(
        {
            "source_script": paper_script,
            "expected_output_dir": output_dir / "manual_paper_signal_logger",
            "required_next_artifact": "run_fixed_candidate_paper_signal_logger.py",
            "caveat": "paper_signal_logger_required;manual_review_required_before_runner;no_trading_decision_made",
        }
    )
    if blocked:
        script_status["command_status"] = "blocked_by_config" if blocked_by_config else "blocked_by_spec"
    elif not paper_script.exists():
        script_status.update(
            {
                "artifact_status": "missing",
                "command_status": "implementation_required",
                "warning_code": "paper_runner_script_missing",
                "required_next_artifact": "implement_run_fixed_candidate_paper_signal_logger",
            }
        )
    elif not script_supported:
        script_status.update(
            {
                "command_status": "unsupported_by_script_cli",
                "compatibility_status": "unknown_requires_manual_review",
                "warning_code": "paper_runner_script_cli_incomplete",
                "required_next_artifact": "paper_signal_logger_safe_cli_contract",
                "caveat": labels(
                    "missing_flags=" + ",".join(script_missing_flags),
                    "manual_review_required_before_runner",
                    "no_trading_decision_made",
                ),
            }
        )
    else:
        script_status.update(
            {
                "command_status": "no_command_needed",
                "compatibility_status": "compatible_with_paper_demo_spec",
                "caveat": "paper_signal_logger_required;manual_review_required_before_runner;no_trading_decision_made",
            }
        )
    rows.append(script_status)

    command = base_row(args, plan_step="paper_runner_command", plan_role="paper_runner_script")
    command.update(
        {
            "source_dir": spec["paths"]["dir"],
            "source_config": config["path"],
            "source_script": paper_script,
            "expected_output_dir": output_dir / "manual_paper_signal_logger",
            "required_next_artifact": "paper_signal_logger_outputs",
            "caveat": "manual_review_required_before_runner;no_trading_decision_made",
        }
    )
    if blocked:
        command["command_status"] = "blocked_by_config" if blocked_by_config else "blocked_by_spec"
    elif paper_script.exists() and script_supported:
        command.update(
            {
                "command_status": "planned_manual_command",
                "compatibility_status": "compatible_with_paper_demo_spec",
                "manual_command": build_manual_command(args, output_dir),
            }
        )
    elif not paper_script.exists():
        command.update(
            {
                "artifact_status": "missing",
                "command_status": "implementation_required",
                "required_next_artifact": "implement_run_fixed_candidate_paper_signal_logger",
                "warning_code": "paper_runner_command_not_available",
            }
        )
    else:
        command.update(
            {
                "command_status": "unsupported_by_script_cli",
                "compatibility_status": "unknown_requires_manual_review",
                "required_next_artifact": "paper_signal_logger_safe_cli_contract",
                "warning_code": "paper_runner_command_unsupported",
            }
        )
    rows.append(command)

    guidance = base_row(args, plan_step="manual_execution_guidance", plan_role="manual_guidance")
    guidance.update(
        {
            "command_status": "no_command_needed" if not blocked else ("blocked_by_config" if blocked_by_config else "blocked_by_spec"),
            "boundary_status": "requires_manual_review",
            "caveat": "manual_review_required_before_runner;paper_signal_logger_required;no_trading_decision_made",
            "required_next_artifact": "review_command_plan_before_any_manual_signal_logger_work",
        }
    )
    rows.append(guidance)

    next_artifact = base_row(args, plan_step="next_artifact_expected", plan_role="next_artifact")
    if blocked:
        next_status = "blocked_by_config" if blocked_by_config else "blocked_by_spec"
        required_next = "fix_demo_strategy_spec_or_config"
    elif not paper_script.exists():
        next_status = "implementation_required"
        required_next = "implement_run_fixed_candidate_paper_signal_logger"
    elif script_supported:
        next_status = "no_command_needed"
        required_next = "paper_signal_logger_manual_command_ready"
    else:
        next_status = "unsupported_by_script_cli"
        required_next = "paper_signal_logger_safe_cli_contract"
    next_artifact.update(
        {
            "command_status": next_status,
            "source_script": paper_script,
            "expected_output_dir": output_dir / "manual_paper_signal_logger",
            "required_next_artifact": required_next,
            "caveat": "paper_signal_logger_required;manual_review_required_before_runner;no_trading_decision_made",
        }
    )
    rows.append(next_artifact)

    metadata = {
        "blocked_by_spec": blocked_by_spec,
        "blocked_by_config": blocked_by_config,
        "paper_runner_script_exists": paper_script.exists(),
        "script_supported": script_supported,
        "script_missing_flags": script_missing_flags,
        **config,
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
    statuses = count_rows(rows, "command_status")
    lines = [
        "# Fixed Candidate Paper-Runner Command Plan",
        "",
        "Command-plan-only artifact. This is a paper/demo plan for a future local paper signal logger.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No real-money sizing was chosen.",
        "No trading decision was made.",
        "",
        "## Demo Strategy Spec Status",
        "",
        f"- demo_strategy_spec_dir: `{args.demo_strategy_spec_dir}`",
        f"- blocked_by_spec: `{bool_text(bool(metadata['blocked_by_spec']))}`",
        "",
        "## Canonical Config Status",
        "",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- demo_strategy_config_loaded: `{bool_text(bool(metadata['loaded']))}`",
        f"- demo_strategy_config_valid: `{bool_text(bool(metadata['config_valid']))}`",
        f"- config_role: `{metadata['config_role']}`",
        f"- candidate_id: `{metadata['candidate_id']}`",
        "",
        "## Paper-Only Boundary",
        "",
        f"- paper_only_boundary_confirmed: `{bool_text(bool(metadata['paper_only_boundary_confirmed']))}`",
        f"- no_broker_connection_allowed: `{bool_text(bool(metadata['no_broker_connection_allowed']))}`",
        f"- no_order_execution_allowed: `{bool_text(bool(metadata['no_order_execution_allowed']))}`",
        f"- real_money_not_allowed: `{bool_text(bool(metadata['real_money_not_allowed']))}`",
        "",
        "## Risk-Control Contract",
        "",
        f"- max_open_positions_note: `{metadata['max_open_positions_note']}`",
        f"- max_daily_trades_note: `{metadata['max_daily_trades_note']}`",
        f"- spread_threshold_note: `{metadata['spread_threshold_note']}`",
        "",
        "## Logging Contract",
        "",
        f"- logging_required_fields: `{';'.join(metadata['logging_fields'])}`",
        "",
        "## Kill-Switch Contract",
        "",
        f"- kill_switch_conditions: `{';'.join(metadata['kill_switch_conditions'])}`",
        "",
        "## Future Paper Signal Logger Script",
        "",
        f"- paper_runner_script: `{args.paper_runner_script}`",
        f"- paper_runner_script_exists: `{bool_text(bool(metadata['paper_runner_script_exists']))}`",
        f"- planned_manual_command_count: `{statuses.get('planned_manual_command', 0)}`",
        f"- implementation_required_count: `{statuses.get('implementation_required', 0)}`",
        "",
        "## Next Artifact",
        "",
        "`implement_run_fixed_candidate_paper_signal_logger` if the script is missing; otherwise review the planned manual command.",
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
    recommended = (
        "fix_demo_strategy_spec_or_config"
        if metadata["blocked_by_spec"] or metadata["blocked_by_config"]
        else (
            "paper_signal_logger_manual_command_ready"
            if metadata["paper_runner_script_exists"] and metadata["script_supported"]
            else "implement_run_fixed_candidate_paper_signal_logger"
        )
    )
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "demo_strategy_config_loaded": bool(metadata["loaded"]),
        "demo_strategy_config_valid": bool(metadata["config_valid"]),
        "config_role": metadata["config_role"],
        "candidate_id": metadata["candidate_id"],
        "paper_runner_script": str(args.paper_runner_script),
        "paper_runner_script_exists": bool(metadata["paper_runner_script_exists"]),
        "plan_row_count": len(rows),
        "planned_manual_command_count": statuses.get("planned_manual_command", 0),
        "implementation_required_count": statuses.get("implementation_required", 0),
        "blocked_by_spec_count": statuses.get("blocked_by_spec", 0),
        "blocked_by_config_count": statuses.get("blocked_by_config", 0),
        "unsupported_by_script_cli_count": statuses.get("unsupported_by_script_cli", 0),
        "missing_script_count": statuses.get("missing_script", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "paper_only_boundary_confirmed": bool(metadata["paper_only_boundary_confirmed"]),
        "no_broker_connection_allowed": bool(metadata["no_broker_connection_allowed"]),
        "no_order_execution_allowed": bool(metadata["no_order_execution_allowed"]),
        "real_money_not_allowed": bool(metadata["real_money_not_allowed"]),
        "recommended_next_artifact": recommended,
        "no_child_scripts_executed": True,
        "no_paper_runner_executed": True,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
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
    rows, warnings, metadata = build_plan_rows(args)
    write_csv(paths["command_plan"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an artifact-only command plan for a fixed-candidate paper signal logger."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument(
        "--final-research-decision-readiness-dir",
        type=Path,
        default=DEFAULT_FINAL_RESEARCH_DECISION_READINESS_DIR,
    )
    parser.add_argument(
        "--artifact-aware-candidate-audit-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_AWARE_CANDIDATE_AUDIT_DIR,
    )
    parser.add_argument("--paper-runner-script", type=Path, default=DEFAULT_PAPER_RUNNER_SCRIPT)
    parser.add_argument("--python-executable", default="python")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate paper-runner command plan failed: {exc}")
        return 1
    print("Fixed-candidate paper-runner command plan complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
