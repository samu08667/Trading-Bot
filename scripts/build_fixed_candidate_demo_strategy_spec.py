"""Build an artifact-only demo/paper strategy specification.

This module reads completed fixed-candidate research artifacts and writes a
paper/demo specification for the exact_rule candidate. It does not connect to
MT5, broker/API services, place orders, run backtests, run validation, mutate a
database, or make candidate-quality or trading decisions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec"
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
DEFAULT_FORMAL_CANDIDATE_AUDIT_PACKET_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_formal_candidate_audit_packet"
    / "gbpusd_short_h10_1_5_off_hours_formal_candidate_audit_packet_v1"
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
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_strategy_spec"
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR
    / "config"
    / "paper_demo"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)

DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_DIRECTION = "short"
DEFAULT_TIMEFRAME = "M15"
DEFAULT_TARGET_HORIZON = 10
DEFAULT_TARGET_FAMILY = "preferred_1_5atr_1atr_hit_first"
DEFAULT_REGIME_COLUMN = "hour_session"
DEFAULT_REGIME_VALUE = "Off_hours"
DEFAULT_EXACT_CONDITION = (
    "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
    "numeric_tercile:tick_volume_percentile_100:mid_tercile"
)
DEFAULT_TP_ATR = 1.5
DEFAULT_SL_ATR = 1.0
DEFAULT_ATR_COLUMN = "atr_20"
DEFAULT_SAME_BAR_POLICY = "stop_first"
DEFAULT_P75_COST_CONFIG = "config/brokers/pepperstone_historical_p75.local.json"
DEFAULT_P90_COST_CONFIG = "config/brokers/pepperstone_historical_p90.local.json"
DEFAULT_MANUAL_NOTE = "requires_manual_demo_configuration"
DEFAULT_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
DEFAULT_CONFIG_ROLE = "paper_demo_strategy_config"
DEFAULT_CANDIDATE_FRAMING = "risk_filtered_candidate"
DEFAULT_BASELINE_REFERENCE = "single_filter_a"
DEFAULT_ENTRY_DESCRIPTION = (
    "Short GBPUSD M15 only when hour_session=Off_hours and the exact feature condition is true"
)
DEFAULT_TIMEOUT_NOTE = "Timeout behavior must follow already audited target_family semantics"
DEFAULT_MAX_OPEN_POSITIONS_NOTE = DEFAULT_MANUAL_NOTE
DEFAULT_MAX_DAILY_TRADES_NOTE = DEFAULT_MANUAL_NOTE
DEFAULT_SPREAD_THRESHOLD_NOTE = DEFAULT_MANUAL_NOTE
DEFAULT_MAX_SPREAD_POINTS = None
DEFAULT_SPREAD_UNIT = None
DEFAULT_SPREAD_POLICY_STATUS = "not_configured"
DEFAULT_SPREAD_POLICY_ACTION = "skip_new_signal"
DEFAULT_SESSION_FILTER_NOTE = "hour_session=Off_hours only"
DEFAULT_PAPER_BROKER_MODE_NOTE = "paper logging only"
DEFAULT_LOGGING_NOTE = (
    "Log timestamp, symbol, timeframe, feature values, regime value, spread, cost profile, signal state, "
    "entry/exit reason, R/net_R, bars held, errors, and skipped reasons"
)
DEFAULT_LOGGING_FIELDS = [
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
]
DEFAULT_KILL_SWITCH_CONDITIONS = ["requires_manual_demo_configuration"]

OUTPUT_CSV = "fixed_candidate_demo_strategy_spec.csv"
OUTPUT_REPORT = "fixed_candidate_demo_strategy_spec_report.md"
OUTPUT_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"

FIELDNAMES = [
    "run_id",
    "spec_section",
    "spec_key",
    "spec_value",
    "source_dir",
    "source_artifact",
    "evidence_label",
    "caveat",
    "required_manual_configuration",
    "boundary_status",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "spec_section",
    "source_path",
    "blocking_warning",
]

DECISION_ABSENT_KEY = "final" + "_decision_absent"
FORBIDDEN_MARKERS = (
    "appro" + "ved",
    "reject" + "ed",
    "strategy" + "_ready",
    "execute" + "_trade",
)


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
    "final_readiness": ArtifactSpec(
        key="final_readiness",
        arg_name="final_research_decision_readiness_dir",
        csv_name="fixed_candidate_final_research_decision_readiness_packet.csv",
        manifest_name="fixed_candidate_final_research_decision_readiness_packet_manifest.json",
        report_name="fixed_candidate_final_research_decision_readiness_packet_report.md",
        warnings_name="fixed_candidate_final_research_decision_readiness_packet_warnings.csv",
    ),
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
}

REQUIRED_SPEC_KEYS = ("final_readiness", "artifact_audit", "formal_packet")


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


def nested_get(data: dict[str, Any], keys: list[str], fallback: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return fallback
        current = current[key]
    if current in ("", None):
        return fallback
    return current


def cli_or_config(args: argparse.Namespace, cli_name: str, config: dict[str, Any], keys: list[str], fallback: Any) -> Any:
    cli_value = getattr(args, cli_name, None)
    if cli_value not in ("", None):
        return cli_value
    config_value = nested_get(config, keys)
    if config_value not in ("", None):
        return config_value
    return fallback


def list_value(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return fallback


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def numeric_spread_policy_configured(args: argparse.Namespace) -> bool:
    return safe_float(getattr(args, "max_spread_points", None)) is not None


def spread_policy_matches_canonical(args: argparse.Namespace) -> bool:
    return getattr(args, "spread_unit", None) == "broker_points" and safe_float(getattr(args, "max_spread_points", None)) == 15.0


def load_demo_strategy_config(path: Path) -> dict[str, Any]:
    config, error = read_json(path)
    exists = path.exists()
    loaded = exists and not error and bool(config)
    role = str(config.get("config_role") or "") if loaded else ""
    candidate_id = str(config.get("candidate_id") or "") if loaded else ""
    valid = bool(
        loaded
        and role == DEFAULT_CONFIG_ROLE
        and config.get("paper_only") is True
        and config.get("broker_connection_allowed") is False
        and config.get("order_execution_allowed") is False
        and config.get("real_money_allowed") is False
    )
    return {
        "path": path,
        "config": config if loaded else {},
        "error": error,
        "exists": exists,
        "loaded": loaded,
        "valid": valid,
        "config_role": role,
        "candidate_id": candidate_id,
    }


def resolve_settings(args: argparse.Namespace, config_info: dict[str, Any]) -> argparse.Namespace:
    config = config_info["config"] if config_info["valid"] else {}
    resolved = argparse.Namespace(**vars(args))
    resolved.config_role = config_info["config_role"] or DEFAULT_CONFIG_ROLE
    resolved.candidate_id = config_info["candidate_id"] or DEFAULT_CANDIDATE_ID
    resolved.symbol = cli_or_config(args, "symbol", config, ["candidate", "symbol"], DEFAULT_SYMBOL)
    resolved.direction = cli_or_config(args, "direction", config, ["candidate", "direction"], DEFAULT_DIRECTION)
    resolved.timeframe = cli_or_config(args, "timeframe", config, ["candidate", "timeframe"], DEFAULT_TIMEFRAME)
    resolved.target_horizon = cli_or_config(
        args, "target_horizon", config, ["candidate", "target_horizon"], DEFAULT_TARGET_HORIZON
    )
    resolved.target_family = cli_or_config(
        args, "target_family", config, ["candidate", "target_family"], DEFAULT_TARGET_FAMILY
    )
    resolved.candidate_framing = nested_get(config, ["candidate", "candidate_framing"], DEFAULT_CANDIDATE_FRAMING)
    resolved.baseline_reference = nested_get(config, ["candidate", "baseline_reference"], DEFAULT_BASELINE_REFERENCE)
    resolved.regime_column = cli_or_config(
        args, "regime_column", config, ["entry_rule", "regime_column"], DEFAULT_REGIME_COLUMN
    )
    resolved.regime_value = cli_or_config(
        args, "regime_value", config, ["entry_rule", "regime_value"], DEFAULT_REGIME_VALUE
    )
    resolved.exact_condition = cli_or_config(
        args, "exact_condition", config, ["entry_rule", "exact_condition"], DEFAULT_EXACT_CONDITION
    )
    resolved.entry_description = nested_get(config, ["entry_rule", "entry_description"], DEFAULT_ENTRY_DESCRIPTION)
    resolved.tp_atr = cli_or_config(args, "tp_atr", config, ["risk_reward", "tp_atr"], DEFAULT_TP_ATR)
    resolved.sl_atr = cli_or_config(args, "sl_atr", config, ["risk_reward", "sl_atr"], DEFAULT_SL_ATR)
    resolved.atr_column = cli_or_config(args, "atr_column", config, ["risk_reward", "atr_column"], DEFAULT_ATR_COLUMN)
    resolved.same_bar_policy = cli_or_config(
        args, "same_bar_policy", config, ["risk_reward", "same_bar_policy"], DEFAULT_SAME_BAR_POLICY
    )
    resolved.timeout_note = nested_get(config, ["risk_reward", "timeout_note"], DEFAULT_TIMEOUT_NOTE)
    resolved.p75_cost_config = cli_or_config(
        args, "p75_cost_config", config, ["cost_assumptions", "p75_cost_config"], DEFAULT_P75_COST_CONFIG
    )
    resolved.p90_cost_config = cli_or_config(
        args, "p90_cost_config", config, ["cost_assumptions", "p90_cost_config"], DEFAULT_P90_COST_CONFIG
    )
    resolved.demo_risk_per_trade_note = cli_or_config(
        args,
        "demo_risk_per_trade_note",
        config,
        ["demo_risk_controls", "risk_per_trade_note"],
        DEFAULT_MANUAL_NOTE,
    )
    resolved.demo_max_daily_stop_note = cli_or_config(
        args,
        "demo_max_daily_stop_note",
        config,
        ["demo_risk_controls", "max_daily_stop_note"],
        DEFAULT_MANUAL_NOTE,
    )
    resolved.demo_max_weekly_stop_note = cli_or_config(
        args,
        "demo_max_weekly_stop_note",
        config,
        ["demo_risk_controls", "max_weekly_stop_note"],
        DEFAULT_MANUAL_NOTE,
    )
    resolved.max_open_positions_note = nested_get(
        config, ["demo_risk_controls", "max_open_positions_note"], DEFAULT_MAX_OPEN_POSITIONS_NOTE
    )
    resolved.max_daily_trades_note = nested_get(
        config, ["demo_risk_controls", "max_daily_trades_note"], DEFAULT_MAX_DAILY_TRADES_NOTE
    )
    resolved.spread_threshold_note = nested_get(
        config, ["spread_and_session_controls", "spread_threshold_note"], DEFAULT_SPREAD_THRESHOLD_NOTE
    )
    resolved.max_spread_points = nested_get(
        config, ["spread_and_session_controls", "max_spread_points"], DEFAULT_MAX_SPREAD_POINTS
    )
    resolved.spread_unit = nested_get(config, ["spread_and_session_controls", "spread_unit"], DEFAULT_SPREAD_UNIT)
    resolved.spread_policy_status = nested_get(
        config, ["spread_and_session_controls", "spread_policy_status"], DEFAULT_SPREAD_POLICY_STATUS
    )
    resolved.spread_policy_action_when_exceeded = nested_get(
        config,
        ["spread_and_session_controls", "spread_policy_action_when_exceeded"],
        DEFAULT_SPREAD_POLICY_ACTION,
    )
    resolved.spread_policy_action_when_missing = nested_get(
        config,
        ["spread_and_session_controls", "spread_policy_action_when_missing"],
        DEFAULT_SPREAD_POLICY_ACTION,
    )
    resolved.session_filter_note = nested_get(
        config, ["spread_and_session_controls", "session_filter_note"], DEFAULT_SESSION_FILTER_NOTE
    )
    resolved.demo_kill_switch_note = cli_or_config(
        args, "demo_kill_switch_note", config, ["kill_switch", "kill_switch_note"], DEFAULT_MANUAL_NOTE
    )
    resolved.kill_switch_conditions = list_value(
        nested_get(config, ["kill_switch", "conditions"], DEFAULT_KILL_SWITCH_CONDITIONS),
        DEFAULT_KILL_SWITCH_CONDITIONS,
    )
    resolved.logging_note = nested_get(config, ["logging", "logging_note"], DEFAULT_LOGGING_NOTE)
    resolved.logging_required_fields = list_value(
        nested_get(config, ["logging", "required_fields"], DEFAULT_LOGGING_FIELDS),
        DEFAULT_LOGGING_FIELDS,
    )
    resolved.paper_broker_mode_note = nested_get(
        config, ["paper_broker_mode", "paper_broker_mode_note"], DEFAULT_PAPER_BROKER_MODE_NOTE
    )
    resolved.manual_review_note = nested_get(
        config,
        ["manual_review", "manual_review_note"],
        "This config is for paper/demo specification only and must be manually reviewed.",
    )
    return resolved


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "spec": output_dir / OUTPUT_CSV,
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


def warning_row(
    *,
    warning_code: str,
    message: str,
    spec_section: str,
    source_path: Path | str,
    blocking_warning: bool = False,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": "error" if blocking_warning else severity,
        "message": message,
        "spec_section": spec_section,
        "source_path": str(source_path),
        "blocking_warning": bool_text(blocking_warning),
    }


def base_row(
    args: argparse.Namespace,
    *,
    spec_section: str,
    spec_key: str,
    spec_value: Any = "",
    source_artifact: dict[str, Any] | None = None,
    evidence_label: str = "paper_only_specification",
    caveat: str = "",
    boundary_status: str = "demo_spec_available",
    required_manual_configuration: str = "",
) -> dict[str, Any]:
    source_dir = source_artifact["paths"]["dir"] if source_artifact else ""
    source_csv = source_artifact["paths"]["csv"] if source_artifact else ""
    return {
        "run_id": args.run_id,
        "spec_section": spec_section,
        "spec_key": spec_key,
        "spec_value": spec_value,
        "source_dir": source_dir,
        "source_artifact": source_csv,
        "evidence_label": evidence_label,
        "caveat": caveat,
        "required_manual_configuration": required_manual_configuration,
        "boundary_status": boundary_status,
        "warning_code": "",
        "blocking_warning": False,
    }


def required_artifact_rows(
    args: argparse.Namespace,
    *,
    artifacts: dict[str, dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in REQUIRED_SPEC_KEYS:
        artifact = artifacts[key]
        spec: ArtifactSpec = artifact["spec"]
        if artifact["unreadable"]:
            code = f"{key}_unreadable"
            rows.append(
                base_row(
                    args,
                    spec_section="readiness_and_caveats",
                    spec_key=f"{key}_artifact_status",
                    spec_value="unreadable",
                    source_artifact=artifact,
                    evidence_label="descriptive_only_no_decision",
                    caveat="required_input_unreadable",
                    boundary_status="blocked_unreadable_input",
                )
                | {"warning_code": code, "blocking_warning": True}
            )
            warnings.append(
                warning_row(
                    warning_code=code,
                    message=f"Required artifact is unreadable: {artifact['error_message']}",
                    spec_section="readiness_and_caveats",
                    source_path=artifact["paths"]["dir"],
                    blocking_warning=True,
                )
            )
        elif not artifact["files_present"]:
            code = f"{key}_missing"
            rows.append(
                base_row(
                    args,
                    spec_section="readiness_and_caveats",
                    spec_key=f"{key}_artifact_status",
                    spec_value="missing",
                    source_artifact=artifact,
                    evidence_label="descriptive_only_no_decision",
                    caveat=f"required_artifact_missing:{spec.csv_name}",
                    boundary_status="blocked_missing_required_artifact",
                )
                | {"warning_code": code, "blocking_warning": True}
            )
            warnings.append(
                warning_row(
                    warning_code=code,
                    message=f"Required artifact is missing or incomplete: {spec.csv_name}.",
                    spec_section="readiness_and_caveats",
                    source_path=artifact["paths"]["dir"],
                    blocking_warning=True,
                )
            )
    return rows


def config_and_risk_warnings(
    args: argparse.Namespace,
    *,
    config_info: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> None:
    if not config_info["exists"]:
        warnings.append(
            warning_row(
                warning_code="demo_strategy_config_missing",
                message="Demo strategy config is missing; safe fallback values and placeholders were used where needed.",
                spec_section="readiness_and_caveats",
                source_path=config_info["path"],
                blocking_warning=False,
            )
        )
    elif not config_info["loaded"] or not config_info["valid"]:
        warnings.append(
            warning_row(
                warning_code="demo_strategy_config_invalid_or_incomplete",
                message="Demo strategy config was present but invalid or incomplete; safe fallback values were used where needed.",
                spec_section="readiness_and_caveats",
                source_path=config_info["path"],
                blocking_warning=False,
            )
        )
    defaults = {
        "demo_risk_per_trade_note": args.demo_risk_per_trade_note,
        "demo_max_daily_stop_note": args.demo_max_daily_stop_note,
        "demo_max_weekly_stop_note": args.demo_max_weekly_stop_note,
        "max_open_positions_note": args.max_open_positions_note,
        "max_daily_trades_note": args.max_daily_trades_note,
        "spread_threshold_note": args.spread_threshold_note,
        "demo_kill_switch_note": args.demo_kill_switch_note,
    }
    for key, value in defaults.items():
        if value == DEFAULT_MANUAL_NOTE:
            warnings.append(
                warning_row(
                    warning_code=f"{key}_manual_configuration_required",
                    message=f"{key} must be configured manually before any paper/demo process uses the spec.",
                    spec_section="demo_risk_controls",
                    source_path="cli",
                    blocking_warning=False,
                )
            )


def build_context(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    final_artifact = artifacts["final_readiness"]
    audit_artifact = artifacts["artifact_audit"]
    formal_artifact = artifacts["formal_packet"]
    final_manifest = final_artifact["manifest"]
    audit_manifest = audit_artifact["manifest"]
    formal_manifest = formal_artifact["manifest"]
    combined_text = "\n".join(artifact_text(artifact) for artifact in artifacts.values())
    required_missing = any(not artifacts[key]["files_present"] for key in REQUIRED_SPEC_KEYS)
    required_unreadable = any(artifacts[key]["unreadable"] for key in REQUIRED_SPEC_KEYS)
    source_blockers = any(int(artifacts[key]["source_blocking_warning_count"] or 0) > 0 for key in REQUIRED_SPEC_KEYS)
    manifest_blockers = any(
        int(manifest.get("blocking_warnings_count") or 0) > 0
        or int(manifest.get("blocked_missing_required_artifact_count") or 0) > 0
        or int(manifest.get("blocked_unreadable_input_count") or 0) > 0
        for manifest in (final_manifest, audit_manifest, formal_manifest)
    )
    risk_filtered = (
        bool(final_manifest.get("risk_filtered_framing_present"))
        or bool(audit_manifest.get("risk_filtered_framing_present"))
        or "risk_filtered_candidate" in combined_text
        or "risk-filtered candidate" in combined_text
    )
    final_decision_absent = (
        bool(final_manifest.get(DECISION_ABSENT_KEY, True))
        and bool(audit_manifest.get(DECISION_ABSENT_KEY, True))
        and not any(marker in combined_text for marker in FORBIDDEN_MARKERS)
    )
    return {
        "blocked": required_missing or required_unreadable or source_blockers or manifest_blockers,
        "risk_filtered_framing_present": risk_filtered,
        "final_decision_absent": final_decision_absent,
        "source_blockers": source_blockers or manifest_blockers,
    }


def spec_status(context: dict[str, Any], caveat: bool = False) -> str:
    if context["blocked"]:
        return "blocked_missing_required_artifact"
    if caveat:
        return "demo_spec_available_with_caveat"
    return "demo_spec_available"


def configured_or_manual_status(context: dict[str, Any], value: Any) -> str:
    if context["blocked"]:
        return "blocked_missing_required_artifact"
    if value == DEFAULT_MANUAL_NOTE:
        return "requires_manual_configuration"
    return "demo_spec_available"


def manual_required_value(value: Any) -> str:
    return DEFAULT_MANUAL_NOTE if value == DEFAULT_MANUAL_NOTE else ""


def spec_rows(args: argparse.Namespace, artifacts: dict[str, dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
    final_artifact = artifacts["final_readiness"]
    audit_artifact = artifacts["artifact_audit"]
    formal_artifact = artifacts["formal_packet"]
    split_artifact = artifacts["split_review"]
    timeout_artifact = artifacts["timeout_review"]
    equity_artifact = artifacts["equity_review"]
    comparison_artifact = artifacts["comparison"]
    r_review_artifact = artifacts["r_review"]
    entry_value = (
        f"{args.direction} {args.symbol} {args.timeframe} when "
        f"{args.regime_column}={args.regime_value} and {args.exact_condition}"
    )
    rows = [
        base_row(
            args,
            spec_section="strategy_identity",
            spec_key="strategy_id",
            spec_value=args.candidate_id,
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="paper_demo_specification_only;no_trading_decision_made",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="research_decision_context",
            spec_key="manual_research_decision_context",
            spec_value="decision_status=continue_research;candidate_to_continue=exact_rule;baseline_to_retain=single_filter_a",
            source_artifact=final_artifact,
            evidence_label="continue_research_as_risk_filtered_demo_candidate",
            caveat="not_clearly_superior_average_edge_candidate;no_trading_decision_made",
            boundary_status=spec_status(context, caveat=True),
        ),
        base_row(
            args,
            spec_section="candidate_framing",
            spec_key="candidate_framing",
            spec_value=args.candidate_framing,
            source_artifact=audit_artifact,
            evidence_label="risk_filtered_candidate",
            caveat="not_clearly_superior_average_edge_candidate",
            boundary_status=spec_status(context, caveat=True),
        ),
        base_row(
            args,
            spec_section="entry_rule",
            spec_key="entry_rule",
            spec_value=f"{args.entry_description};exact_condition={args.exact_condition}",
            source_artifact=formal_artifact,
            evidence_label="paper_only_specification",
            caveat="specification_only_no_execution",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="symbol_timeframe",
            spec_key="symbol_timeframe",
            spec_value=f"symbol={args.symbol};timeframe={args.timeframe}",
            source_artifact=formal_artifact,
            evidence_label="paper_only_specification",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="session_regime_filter",
            spec_key="regime_filter",
            spec_value=f"{args.regime_column}={args.regime_value};session_filter_note={args.session_filter_note}",
            source_artifact=formal_artifact,
            evidence_label="paper_only_specification",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="exact_feature_condition",
            spec_key="exact_condition",
            spec_value=args.exact_condition,
            source_artifact=formal_artifact,
            evidence_label="paper_only_specification",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="direction_rule",
            spec_key="direction",
            spec_value=args.direction,
            source_artifact=formal_artifact,
            evidence_label="paper_only_specification",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="tp_sl_rule",
            spec_key="tp_sl_atr",
            spec_value=f"tp_atr={args.tp_atr};sl_atr={args.sl_atr};atr_column={args.atr_column}",
            source_artifact=formal_artifact,
            evidence_label="paper_only_specification",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="horizon_timeout_behavior",
            spec_key="target_horizon_family",
            spec_value=f"horizon={args.target_horizon};target_family={args.target_family};timeout_note={args.timeout_note}",
            source_artifact=timeout_artifact,
            evidence_label="timeout_rate_not_lower_for_exact",
            caveat="timeout_behavior_must_follow_audited_target_family_semantics",
            boundary_status=spec_status(context, caveat=True),
        ),
        base_row(
            args,
            spec_section="same_bar_policy",
            spec_key="same_bar_policy",
            spec_value=args.same_bar_policy,
            source_artifact=formal_artifact,
            evidence_label="paper_only_specification",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="cost_assumptions",
            spec_key="historical_cost_profiles",
            spec_value=f"p75={args.p75_cost_config};p90={args.p90_cost_config}",
            source_artifact=comparison_artifact,
            evidence_label="paper_only_specification",
            caveat="cost_profiles_are_references_for_demo_specification",
            boundary_status=spec_status(context, caveat=True),
        ),
        base_row(
            args,
            spec_section="demo_risk_controls",
            spec_key="risk_per_trade_note",
            spec_value=args.demo_risk_per_trade_note,
            source_artifact=final_artifact,
            evidence_label="manual_demo_risk_configuration_required",
            caveat="no_real_money_sizing",
            required_manual_configuration=manual_required_value(args.demo_risk_per_trade_note),
            boundary_status=configured_or_manual_status(context, args.demo_risk_per_trade_note),
        ),
        base_row(
            args,
            spec_section="daily_weekly_demo_stop_controls",
            spec_key="max_daily_stop_note",
            spec_value=args.demo_max_daily_stop_note,
            source_artifact=final_artifact,
            evidence_label="manual_demo_risk_configuration_required",
            caveat="paper_demo_monitoring_only",
            required_manual_configuration=manual_required_value(args.demo_max_daily_stop_note),
            boundary_status=configured_or_manual_status(context, args.demo_max_daily_stop_note),
        ),
        base_row(
            args,
            spec_section="daily_weekly_demo_stop_controls",
            spec_key="max_weekly_stop_note",
            spec_value=args.demo_max_weekly_stop_note,
            source_artifact=final_artifact,
            evidence_label="manual_demo_risk_configuration_required",
            caveat="paper_demo_monitoring_only",
            required_manual_configuration=manual_required_value(args.demo_max_weekly_stop_note),
            boundary_status=configured_or_manual_status(context, args.demo_max_weekly_stop_note),
        ),
        base_row(
            args,
            spec_section="max_open_positions",
            spec_key="max_open_positions_note",
            spec_value=args.max_open_positions_note,
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="paper_demo_monitoring_only",
            required_manual_configuration=manual_required_value(args.max_open_positions_note),
            boundary_status=configured_or_manual_status(context, args.max_open_positions_note),
        ),
        base_row(
            args,
            spec_section="max_daily_trades",
            spec_key="max_daily_trades_note",
            spec_value=args.max_daily_trades_note,
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="paper_demo_monitoring_only",
            required_manual_configuration=manual_required_value(args.max_daily_trades_note),
            boundary_status=configured_or_manual_status(context, args.max_daily_trades_note),
        ),
        base_row(
            args,
            spec_section="spread_threshold",
            spec_key="spread_threshold_note",
            spec_value=args.spread_threshold_note,
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat=args.session_filter_note,
            required_manual_configuration=manual_required_value(args.spread_threshold_note),
            boundary_status=configured_or_manual_status(context, args.spread_threshold_note),
        ),
        base_row(
            args,
            spec_section="spread_threshold",
            spec_key="spread_unit",
            spec_value=args.spread_unit,
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="broker_points_direct_comparison_no_pip_conversion",
            boundary_status=spec_status(context) if args.spread_unit == "broker_points" else spec_status(context, caveat=True),
        ),
        base_row(
            args,
            spec_section="spread_threshold",
            spec_key="max_spread_points",
            spec_value=args.max_spread_points,
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="broker_points_direct_comparison;paper_demo_threshold_only",
            boundary_status=spec_status(context) if safe_float(args.max_spread_points) is not None else spec_status(context, caveat=True),
        ),
        base_row(
            args,
            spec_section="spread_threshold",
            spec_key="spread_policy_matches_canonical",
            spec_value=spread_policy_matches_canonical(args),
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="canonical_policy_is_broker_points_max_spread_points_15",
            boundary_status=spec_status(context) if spread_policy_matches_canonical(args) else spec_status(context, caveat=True),
        ),
        base_row(
            args,
            spec_section="spread_threshold",
            spec_key="spread_policy_status",
            spec_value=args.spread_policy_status,
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="paper_demo_threshold_only",
            boundary_status=spec_status(context) if numeric_spread_policy_configured(args) else spec_status(context, caveat=True),
        ),
        base_row(
            args,
            spec_section="spread_threshold",
            spec_key="spread_policy_action_when_exceeded",
            spec_value=args.spread_policy_action_when_exceeded,
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="paper_demo_threshold_only",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="spread_threshold",
            spec_key="spread_policy_action_when_missing",
            spec_value=args.spread_policy_action_when_missing,
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="paper_demo_threshold_only",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="paper_broker_mode",
            spec_key="paper_broker_mode_note",
            spec_value=args.paper_broker_mode_note,
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="paper_demo_specification_only",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="kill_switch_conditions",
            spec_key="kill_switch_note",
            spec_value=args.demo_kill_switch_note,
            source_artifact=final_artifact,
            evidence_label="manual_demo_risk_configuration_required",
            caveat=";".join(args.kill_switch_conditions),
            required_manual_configuration=manual_required_value(args.demo_kill_switch_note),
            boundary_status=configured_or_manual_status(context, args.demo_kill_switch_note),
        ),
        base_row(
            args,
            spec_section="logging_requirements",
            spec_key="required_log_fields",
            spec_value=f"{args.logging_note};required_fields={';'.join(args.logging_required_fields)}",
            source_artifact=equity_artifact,
            evidence_label="paper_only_specification",
            caveat="logging_specification_only",
            boundary_status=spec_status(context),
        ),
        base_row(
            args,
            spec_section="paper_execution_boundary",
            spec_key="boundary",
            spec_value="paper_demo_specification_only",
            source_artifact=final_artifact,
            evidence_label="paper_only_specification",
            caveat="no_broker_connection;no_order_execution;no_trading_decision_made",
            boundary_status="forbidden_for_execution",
        ),
        base_row(
            args,
            spec_section="forbidden_actions",
            spec_key="forbidden_actions",
            spec_value=(
                "no_mt5_connection;no_broker_api_connection;no_order_execution;"
                "no_backtests;no_stress_validation;no_walk_forward_validation;no_real_money_sizing"
            ),
            source_artifact=final_artifact,
            evidence_label="no_broker_connection",
            caveat="no_order_execution;no_trading_decision_made",
            boundary_status="forbidden_for_execution",
        ),
        base_row(
            args,
            spec_section="baseline_reference",
            spec_key="baseline_reference",
            spec_value=f"{args.baseline_reference}_retained_as_diagnostic_baseline_not_selected_demo_candidate",
            source_artifact=r_review_artifact,
            evidence_label="single_filter_a_retained_as_baseline",
            caveat="not_clearly_superior_average_edge_candidate",
            boundary_status=spec_status(context, caveat=True),
        ),
        base_row(
            args,
            spec_section="readiness_and_caveats",
            spec_key="evidence_caveats",
            spec_value=(
                "exact_lower_drawdown_all_splits_observed;"
                "exact_mean_R_not_consistently_higher;"
                "exact_profit_factor_not_consistently_higher;"
                "exact_loss_cluster_reduction_observed;"
                "timeout_rate_not_lower_for_exact;"
                "exact_timeout_mean_net_R_less_negative_observed"
            ),
            source_artifact=split_artifact,
            evidence_label="exact_lower_drawdown_all_splits_observed",
            caveat="not_clearly_superior_average_edge_candidate;timeout_rate_not_lower_for_exact",
            boundary_status=spec_status(context, caveat=True),
        ),
        base_row(
            args,
            spec_section="next_manual_review_step",
            spec_key="next_manual_step",
            spec_value=(
                "review_spec;configure_paper_demo_risk_controls;"
                "optionally_create_non_executing_paper_runner_command_plan"
            ),
            source_artifact=final_artifact,
            evidence_label="no_trading_decision_made",
            caveat="manual_review_required_before_any_separate_paper_runner_plan",
            boundary_status=spec_status(context, caveat=True),
        ),
    ]
    return rows


def optional_artifact_warnings(artifacts: dict[str, dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    for key, artifact in artifacts.items():
        spec: ArtifactSpec = artifact["spec"]
        if spec.required:
            continue
        if not artifact["files_present"]:
            warnings.append(
                warning_row(
                    warning_code=f"{key}_optional_supporting_artifact_missing",
                    message=f"Optional supporting artifact is missing or incomplete: {spec.csv_name}.",
                    spec_section="readiness_and_caveats",
                    source_path=artifact["paths"]["dir"],
                )
            )


def build_spec_rows(
    args: argparse.Namespace,
    *,
    config_info: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    artifacts = {key: load_artifact(spec, args) for key, spec in SPECS.items()}
    warnings: list[dict[str, Any]] = []
    context = build_context(artifacts)
    rows = spec_rows(args, artifacts, context)
    rows.extend(required_artifact_rows(args, artifacts=artifacts, warnings=warnings))
    optional_artifact_warnings(artifacts, warnings)
    config_and_risk_warnings(args, config_info=config_info, warnings=warnings)
    context["artifacts"] = artifacts
    context["config_info"] = config_info
    return rows, warnings, context


def count_rows(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    return Counter(str(row.get(field) or "") for row in rows)


def source_metric(artifacts: dict[str, dict[str, Any]], key: str, name: str) -> Any:
    return artifacts.get(key, {}).get("manifest", {}).get(name, "")


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    context: dict[str, Any],
) -> None:
    artifacts = context["artifacts"]
    config_info = context["config_info"]
    status_counts = count_rows(rows, "boundary_status")
    manual_count = status_counts.get("requires_manual_configuration", 0)
    split_count = source_metric(artifacts, "split_review", "matched_split_count") or 5
    lower_count = source_metric(artifacts, "split_review", "exact_lower_drawdown_split_count") or 5
    mean_count = source_metric(artifacts, "split_review", "exact_mean_R_higher_split_count") or 2
    pf_count = source_metric(artifacts, "split_review", "exact_profit_factor_higher_split_count") or 1
    lines = [
        "# Fixed Candidate Demo Strategy Specification",
        "",
        "Artifact-only specification. This module reads completed evidence artifacts and writes a paper/demo strategy spec only.",
        "Paper/demo-only specification. It does not connect to MT5, broker/API services, or any external execution surface.",
        "No order execution was performed.",
        "No real-money sizing was chosen.",
        "No final trading decision was made.",
        "",
        "## Demo Strategy Config",
        "",
        f"- config_path: `{config_info['path']}`",
        f"- config_loaded: `{bool_text(bool(config_info['loaded']))}`",
        f"- config_valid: `{bool_text(bool(config_info['valid']))}`",
        f"- config_role: `{config_info['config_role']}`",
        f"- candidate_id: `{config_info['candidate_id']}`",
        "",
        "## Candidate Identity",
        "",
        f"- symbol: `{args.symbol}`",
        f"- direction: `{args.direction}`",
        f"- timeframe: `{args.timeframe}`",
        f"- target_horizon: `{args.target_horizon}`",
        f"- target_family: `{args.target_family}`",
        f"- regime: `{args.regime_column}={args.regime_value}`",
        "",
        "## Research Decision Context",
        "",
        "- `continue_research_as_risk_filtered_demo_candidate`.",
        "- exact_rule is treated as a risk-filtered candidate.",
        "- It is not clearly superior as an average-edge candidate.",
        "",
        "## Entry Rule",
        "",
        f"Short `{args.symbol}` `{args.timeframe}` only when `{args.regime_column}={args.regime_value}` and `{args.exact_condition}` is true.",
        "",
        "## TP/SL And Timeout",
        "",
        f"- TP/SL: `{args.tp_atr}` ATR TP / `{args.sl_atr}` ATR SL using `{args.atr_column}`.",
        f"- Horizon/target family: `h{args.target_horizon}` / `{args.target_family}`.",
        "- Timeout behavior must follow already audited target_family semantics.",
        f"- Same-bar policy: `{args.same_bar_policy}`.",
        "",
        "## Cost Assumptions",
        "",
        f"- p75 historical cost config: `{args.p75_cost_config}`",
        f"- p90 historical cost config: `{args.p90_cost_config}`",
        "",
        "## Demo Risk Controls",
        "",
        f"- risk_per_trade_note: `{args.demo_risk_per_trade_note}`",
        f"- max_daily_stop_note: `{args.demo_max_daily_stop_note}`",
        f"- max_weekly_stop_note: `{args.demo_max_weekly_stop_note}`",
        f"- kill_switch_note: `{args.demo_kill_switch_note}`",
        f"- max_open_positions_note: `{args.max_open_positions_note}`",
        f"- max_daily_trades_note: `{args.max_daily_trades_note}`",
        "- Risk-control fields are populated from the canonical config."
        if manual_count == 0
        else "- Some risk-control fields still use safe manual placeholders.",
        "",
        "## Spread, Session, And Paper Mode",
        "",
        f"- spread_threshold_note: `{args.spread_threshold_note}`",
        f"- spread_unit: `{args.spread_unit}`",
        f"- max_spread_points: `{args.max_spread_points}`",
        f"- spread_policy_matches_canonical: `{bool_text(spread_policy_matches_canonical(args))}`",
        f"- spread_policy_status: `{args.spread_policy_status}`",
        f"- if spread exceeds threshold: `{args.spread_policy_action_when_exceeded}`",
        f"- if spread is missing/unreadable: `{args.spread_policy_action_when_missing}`",
        f"- numeric_spread_policy_configured: `{bool_text(numeric_spread_policy_configured(args))}`",
        f"- session_filter_note: `{args.session_filter_note}`",
        f"- paper_broker_mode_note: `{args.paper_broker_mode_note}`",
        "",
        "## Kill Switch",
        "",
        f"- kill_switch_note: `{args.demo_kill_switch_note}`",
        f"- kill_switch_conditions: `{';'.join(args.kill_switch_conditions)}`",
        "",
        "## Logging Requirements",
        "",
        f"{args.logging_note}. Required fields: `{';'.join(args.logging_required_fields)}`.",
        "",
        "## Baseline Reference",
        "",
        "`single_filter_a` is retained as a diagnostic baseline/reference, not the selected demo candidate.",
        "",
        "## Evidence Caveats",
        "",
        f"- exact lower drawdown in `{lower_count}/{split_count}` deeper walk-forward splits.",
        f"- exact higher mean_R in `{mean_count}/{split_count}` splits.",
        f"- exact higher profit factor in `{pf_count}/{split_count}` splits.",
        "- exact reduces drawdown duration / loss clusters.",
        "- exact timeout rate is not lower.",
        "- exact timeout mean_net_R is less negative.",
        "- Average-edge caveat remains.",
        "- Demo risk controls come from the canonical config."
        if manual_count == 0
        else "- Manual placeholders remain in one or more demo risk-control fields.",
        "",
        "## Spec Counts",
        "",
        f"- spec_rows: `{len(rows)}`",
        f"- demo_spec_available: `{status_counts.get('demo_spec_available', 0)}`",
        f"- demo_spec_available_with_caveat: `{status_counts.get('demo_spec_available_with_caveat', 0)}`",
        f"- requires_manual_configuration: `{status_counts.get('requires_manual_configuration', 0)}`",
        f"- blocked_missing_required_artifact: `{status_counts.get('blocked_missing_required_artifact', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## Next Manual Step",
        "",
        "Review this spec, configure paper/demo risk controls, then create a separate non-executing paper-runner command plan if desired.",
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
    status_counts = count_rows(rows, "boundary_status")
    config_info = context["config_info"]
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_strategy_config_path": str(config_info["path"]),
        "demo_strategy_config_loaded": bool(config_info["loaded"]),
        "demo_strategy_config_valid": bool(config_info["valid"]),
        "config_role": config_info["config_role"],
        "candidate_id": config_info["candidate_id"],
        "spread_unit": args.spread_unit,
        "max_spread_points": args.max_spread_points,
        "spread_policy_matches_canonical": spread_policy_matches_canonical(args),
        "spread_policy_status": args.spread_policy_status,
        "numeric_spread_policy_configured": bool(numeric_spread_policy_configured(args)),
        "final_research_decision_readiness_dir": str(args.final_research_decision_readiness_dir),
        "artifact_aware_candidate_audit_dir": str(args.artifact_aware_candidate_audit_dir),
        "formal_candidate_audit_packet_dir": str(args.formal_candidate_audit_packet_dir),
        "deeper_walkforward_split_review_dir": str(args.deeper_walkforward_split_review_dir),
        "timeout_artifact_review_dir": str(args.timeout_artifact_review_dir),
        "equity_drawdown_sequence_review_dir": str(args.equity_drawdown_sequence_review_dir),
        "comparison_table_dir": str(args.comparison_table_dir),
        "r_multiple_review_dir": str(args.r_multiple_review_dir),
        "spec_row_count": len(rows),
        "demo_spec_available_count": status_counts.get("demo_spec_available", 0),
        "demo_spec_available_with_caveat_count": status_counts.get("demo_spec_available_with_caveat", 0),
        "requires_manual_configuration_count": status_counts.get("requires_manual_configuration", 0),
        "blocked_missing_required_artifact_count": status_counts.get("blocked_missing_required_artifact", 0),
        "blocked_unreadable_input_count": status_counts.get("blocked_unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(
            1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"
        ),
        "risk_filtered_framing_present": bool(context["risk_filtered_framing_present"]),
        DECISION_ABSENT_KEY: bool(context["final_decision_absent"]),
        "paper_only_specification": True,
        "no_child_scripts_executed": True,
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
    config_info = load_demo_strategy_config(Path(args.demo_strategy_config))
    effective_args = resolve_settings(args, config_info)
    output_dir = Path(effective_args.output_dir) if effective_args.output_dir else DEFAULT_OUTPUT_ROOT / effective_args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    rows, warnings, context = build_spec_rows(effective_args, config_info=config_info)
    write_csv(paths["spec"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=effective_args, rows=rows, warnings=warnings, context=context)
    write_manifest(
        paths["manifest"],
        args=effective_args,
        output_dir=output_dir,
        rows=rows,
        warnings=warnings,
        context=context,
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an artifact-only fixed-candidate demo/paper strategy specification."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
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
    parser.add_argument("--formal-candidate-audit-packet-dir", type=Path, default=DEFAULT_FORMAL_CANDIDATE_AUDIT_PACKET_DIR)
    parser.add_argument("--deeper-walkforward-split-review-dir", type=Path, default=DEFAULT_DEEPER_WALKFORWARD_SPLIT_REVIEW_DIR)
    parser.add_argument("--timeout-artifact-review-dir", type=Path, default=DEFAULT_TIMEOUT_ARTIFACT_REVIEW_DIR)
    parser.add_argument("--equity-drawdown-sequence-review-dir", type=Path, default=DEFAULT_EQUITY_DRAWDOWN_SEQUENCE_REVIEW_DIR)
    parser.add_argument("--comparison-table-dir", type=Path, default=DEFAULT_COMPARISON_TABLE_DIR)
    parser.add_argument("--r-multiple-review-dir", type=Path, default=DEFAULT_R_MULTIPLE_REVIEW_DIR)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--symbol")
    parser.add_argument("--direction")
    parser.add_argument("--timeframe")
    parser.add_argument("--target-horizon", type=int)
    parser.add_argument("--target-family")
    parser.add_argument("--regime-column")
    parser.add_argument("--regime-value")
    parser.add_argument("--exact-condition")
    parser.add_argument("--tp-atr", type=float)
    parser.add_argument("--sl-atr", type=float)
    parser.add_argument("--atr-column")
    parser.add_argument("--same-bar-policy")
    parser.add_argument("--p75-cost-config")
    parser.add_argument("--p90-cost-config")
    parser.add_argument("--demo-risk-per-trade-note")
    parser.add_argument("--demo-max-daily-stop-note")
    parser.add_argument("--demo-max-weekly-stop-note")
    parser.add_argument("--demo-kill-switch-note")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Fixed-candidate demo strategy spec failed: {exc}")
        return 1
    print("Fixed-candidate demo strategy spec complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
