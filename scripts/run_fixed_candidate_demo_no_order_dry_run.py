"""Run a single-shot fixed-candidate demo no-order dry-run.

This script reads local artifacts, a frozen threshold artifact, optional local
state, and one latest row from an allowlisted local feature table. It emits only
would_skip, would_signal, or would_block evidence. It does not connect to MT5 or
broker/API services, query live account or symbol state, construct requests,
execute orders, mutate the database, refresh data, rerun replay or paper
workflow, optimize parameters, or make candidate-quality or trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_no_order_dry_run"
DEFAULT_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_no_order_dry_run_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_no_order_dry_run_plan_spread15_v1"
)
DEFAULT_ENVIRONMENT_CHECK_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_environment_check"
    / "gbpusd_short_h10_1_5_off_hours_demo_environment_check_spread15_v1"
)
DEFAULT_DEMO_STRATEGY_CONFIG = (
    BASE_DIR / "config" / "paper_demo" / "gbpusd_short_h10_1_5_off_hours_demo_strategy_config.json"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_DEMO_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_DEMO_STRATEGY_SPEC_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_strategy_spec"
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v5_spread15"
)
DEFAULT_FEATURE_SOURCE_DB = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_FEATURE_SOURCE_TABLE = "price_features"
DEFAULT_STATE_JSON = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_v1"
    / "fixed_candidate_paper_signal_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_no_order_dry_run"

PLAN_MANIFEST = "fixed_candidate_demo_no_order_dry_run_plan_manifest.json"
PLAN_REPORT = "fixed_candidate_demo_no_order_dry_run_plan_report.md"
PLAN_REQUIREMENTS = "fixed_candidate_demo_no_order_dry_run_plan_requirements.csv"
PLAN_FUTURE_ARTIFACTS = "fixed_candidate_demo_no_order_dry_run_plan_future_artifacts.csv"
PLAN_WARNINGS = "fixed_candidate_demo_no_order_dry_run_plan_warnings.csv"

ENV_MANIFEST = "fixed_candidate_demo_environment_check_manifest.json"
ENV_REPORT = "fixed_candidate_demo_environment_check_report.md"
ENV_ACCOUNT_SNAPSHOT = "fixed_candidate_demo_environment_account_snapshot_redacted.json"
ENV_SYMBOL_SNAPSHOT = "fixed_candidate_demo_environment_symbol_contract_snapshot.json"
ENV_NO_ORDER = "fixed_candidate_demo_environment_dry_run_no_order_check.csv"

SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"
SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"

OUTPUT_MANIFEST = "fixed_candidate_demo_no_order_dry_run_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_no_order_dry_run_report.md"
OUTPUT_DECISION = "fixed_candidate_demo_no_order_dry_run_decision.csv"
OUTPUT_CHECKLIST = "fixed_candidate_demo_no_order_dry_run_checklist.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_no_order_dry_run_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_no_order_dry_run_no_order_evidence.csv"
OUTPUT_STATE_PREVIEW = "fixed_candidate_demo_no_order_dry_run_state_preview.json"
OUTPUT_INPUT_ROW_SNAPSHOT = "fixed_candidate_demo_no_order_dry_run_input_row_snapshot.json"

ALLOWLISTED_FEATURE_TABLES = {"price_features", "market_features"}
BLOCKED_FEATURE_TABLES = {"ml_dataset"}
REQUIRED_ROW_COLUMNS = (
    "time_server",
    "open",
    "high",
    "low",
    "close",
    "atr_20",
    "spread",
    "hour_session",
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
)
OPTIONAL_ROW_COLUMNS = ("symbol", "timeframe", "tick_volume", "volume")
REQUIRED_KILL_SWITCH_CONDITIONS = {
    "required_data_missing",
    "required_features_missing",
    "spread_abnormal_or_not_configured",
    "atr_calculation_failed",
    "timeframe_mismatch",
    "session_mismatch",
    "existing_paper_demo_trade_open",
}
NO_ORDER_FLAGS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_db_mutation_performed",
    "no_demo_broker_approval_performed",
)
REQUIRED_THRESHOLD_FEATURES = (
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
)
CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"

DECISION_FIELDNAMES = [
    "run_id",
    "decision_label",
    "dry_run_status",
    "time_server",
    "evaluated_feature_time_server",
    "time_server_source",
    "import_time_basis",
    "pc_utc_now",
    "mt5_tick_time_server",
    "latest_mt5_closed_bar_time_server",
    "latest_db_price_bar_time_server",
    "latest_db_feature_time_server",
    "db_lag_bars_vs_mt5_latest_closed_bar",
    "db_lag_minutes_vs_mt5_latest_closed_bar",
    "mt5_server_time_offset_seconds_vs_pc_utc",
    "live_alignment_status",
    "symbol",
    "timeframe",
    "direction",
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
    "close",
    "atr_20",
    "close_to_ma_fast_atr_20",
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100",
    "tick_volume_percentile_100_bucket",
    "entry_reference_price",
    "tp_price_preview",
    "sl_price_preview",
    "horizon_bars",
    "same_bar_policy",
    "timeout_policy",
    "risk_percent_configured",
    "volume_preview_status",
    "skip_reasons",
    "block_reasons",
    "no_order_request_constructed",
    "no_order_execution_performed",
]
CHECKLIST_FIELDNAMES = [
    "run_id",
    "check_area",
    "check_name",
    "check_status",
    "observed_value",
    "expected_value",
    "blocking_if_failed",
    "evidence_source",
    "caveat",
    "warning_code",
]
NO_ORDER_FIELDNAMES = [
    "run_id",
    "no_mt5_connection_performed",
    "no_broker_connection_performed",
    "no_account_query_performed",
    "no_symbol_query_performed",
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_db_mutation_performed",
    "no_data_generation_performed",
    "no_feature_refresh_performed",
    "no_trading_decision_performed",
    "evidence_label",
    "caveat",
]
WARNING_FIELDNAMES = [
    "run_id",
    "warning_code",
    "severity",
    "message",
    "source",
    "blocking_warning",
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
    if isinstance(value, (dict, list)):
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


def extract_first_number(text: Any) -> float | None:
    if not isinstance(text, str):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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


def repo_relative_path(path: Path | str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else BASE_DIR / candidate


def resolve_thresholds_path(args: argparse.Namespace) -> Path:
    explicit = getattr(args, "tercile_thresholds_json", None)
    if explicit:
        return Path(explicit)
    registry, _error = read_json(Path(args.canonical_registry))
    configured = registry.get("numeric_tercile_thresholds_json")
    if not configured:
        return BASE_DIR / "__missing_canonical_numeric_tercile_thresholds_json__"
    return repo_relative_path(str(configured))


def normalize_threshold_args(args: argparse.Namespace) -> argparse.Namespace:
    args.tercile_thresholds_json = resolve_thresholds_path(args)
    return args


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], ""
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), ""
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
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


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "decision": output_dir / OUTPUT_DECISION,
        "checklist": output_dir / OUTPUT_CHECKLIST,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
        "state_preview": output_dir / OUTPUT_STATE_PREVIEW,
        "input_row_snapshot": output_dir / OUTPUT_INPUT_ROW_SNAPSHOT,
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


def load_required_json(args: argparse.Namespace, warnings: list[dict[str, Any]], path: Path, code: str) -> dict[str, Any]:
    data, error = read_json(path)
    if not path.exists():
        add_warning(warnings, args=args, warning_code=f"{code}_missing", message="Required JSON artifact is missing.", source=path, blocking_warning=True)
    elif error:
        add_warning(warnings, args=args, warning_code=f"{code}_unreadable", message=f"Required JSON artifact is unreadable: {error}", source=path, blocking_warning=True)
    return data


def load_required_csv(args: argparse.Namespace, warnings: list[dict[str, Any]], path: Path, code: str) -> list[dict[str, str]]:
    rows, error = read_csv_rows(path)
    if not path.exists():
        add_warning(warnings, args=args, warning_code=f"{code}_missing", message="Required CSV artifact is missing.", source=path, blocking_warning=True)
    elif error:
        add_warning(warnings, args=args, warning_code=f"{code}_unreadable", message=f"Required CSV artifact is unreadable: {error}", source=path, blocking_warning=True)
    return rows


def preserve_source_warnings(args: argparse.Namespace, warnings: list[dict[str, Any]], rows: list[dict[str, str]], source_name: str) -> None:
    for row in rows:
        add_warning(
            warnings,
            args=args,
            warning_code=row.get("warning_code", f"{source_name}_source_warning"),
            message=row.get("message", "Source warning preserved."),
            source=row.get("source", source_name),
            blocking_warning=str(row.get("blocking_warning", "")).lower() == "true",
            severity=row.get("severity") or "warning",
        )


def source_paths(args: argparse.Namespace) -> dict[str, Path]:
    plan_dir = Path(args.demo_no_order_dry_run_plan_dir)
    env_dir = Path(args.demo_environment_check_dir)
    spec_dir = Path(args.demo_strategy_spec_dir)
    return {
        "canonical_registry": Path(args.canonical_registry),
        "demo_execution_policy": Path(args.demo_execution_policy_json),
        "plan_manifest": plan_dir / PLAN_MANIFEST,
        "plan_requirements": plan_dir / PLAN_REQUIREMENTS,
        "plan_future_artifacts": plan_dir / PLAN_FUTURE_ARTIFACTS,
        "plan_warnings": plan_dir / PLAN_WARNINGS,
        "env_manifest": env_dir / ENV_MANIFEST,
        "account_snapshot": env_dir / ENV_ACCOUNT_SNAPSHOT,
        "symbol_snapshot": env_dir / ENV_SYMBOL_SNAPSHOT,
        "env_no_order": env_dir / ENV_NO_ORDER,
        "spec_manifest": spec_dir / SPEC_MANIFEST,
        "spec_csv": spec_dir / SPEC_CSV,
        "spec_warnings": spec_dir / SPEC_WARNINGS,
        "config": Path(args.demo_strategy_config),
        "thresholds": Path(args.tercile_thresholds_json),
    }


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    paths = source_paths(args)
    inputs = {
        "paths": paths,
        "canonical_registry": load_required_json(args, warnings, paths["canonical_registry"], "canonical_registry"),
        "demo_execution_policy": load_required_json(args, warnings, paths["demo_execution_policy"], "demo_execution_policy"),
        "plan_manifest": load_required_json(args, warnings, paths["plan_manifest"], "no_order_plan_manifest"),
        "plan_requirements": load_required_csv(args, warnings, paths["plan_requirements"], "no_order_plan_requirements"),
        "plan_future_artifacts": load_required_csv(args, warnings, paths["plan_future_artifacts"], "no_order_plan_future_artifacts"),
        "plan_warnings": load_required_csv(args, warnings, paths["plan_warnings"], "no_order_plan_warnings"),
        "env_manifest": load_required_json(args, warnings, paths["env_manifest"], "environment_check_manifest"),
        "account_snapshot": load_required_json(args, warnings, paths["account_snapshot"], "account_snapshot"),
        "symbol_snapshot": load_required_json(args, warnings, paths["symbol_snapshot"], "symbol_contract_snapshot"),
        "env_no_order": load_required_csv(args, warnings, paths["env_no_order"], "environment_no_order_evidence"),
        "spec_manifest": load_required_json(args, warnings, paths["spec_manifest"], "demo_strategy_spec_manifest"),
        "spec_csv": load_required_csv(args, warnings, paths["spec_csv"], "demo_strategy_spec_csv"),
        "spec_warnings": load_required_csv(args, warnings, paths["spec_warnings"], "demo_strategy_spec_warnings"),
        "config": load_required_json(args, warnings, paths["config"], "demo_strategy_config"),
        "thresholds": load_required_json(args, warnings, paths["thresholds"], "tercile_thresholds_json"),
        "plan_report": read_text(Path(args.demo_no_order_dry_run_plan_dir) / PLAN_REPORT),
        "env_report": read_text(Path(args.demo_environment_check_dir) / ENV_REPORT),
    }
    preserve_source_warnings(args, warnings, inputs["plan_warnings"], "no_order_plan_warnings")
    preserve_source_warnings(args, warnings, inputs["spec_warnings"], "demo_strategy_spec_warnings")
    return inputs


def missing_source_artifact_count(paths: dict[str, Path]) -> int:
    return sum(1 for path in paths.values() if not path.exists())


def unreadable_source_artifact_count(warnings: list[dict[str, Any]]) -> int:
    return sum(1 for warning in warnings if str(warning.get("warning_code", "")).endswith("_unreadable"))


def config_boundaries(config: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    max_open_positions = extract_first_number(nested_get(config, "demo_risk_controls", "max_open_positions_note"))
    policy_max_open_positions = safe_int(policy.get("max_open_positions"))
    if policy_max_open_positions is not None:
        max_open_positions = policy_max_open_positions
    risk_percent = safe_float(policy.get("risk_percent_max"))
    risk_amount = safe_float(policy.get("risk_amount_max"))
    spread_unit = nested_get(config, "spread_and_session_controls", "spread_unit")
    max_spread_points = safe_float(nested_get(config, "spread_and_session_controls", "max_spread_points"))
    kill_conditions = nested_get(config, "kill_switch", "conditions")
    if not isinstance(kill_conditions, list):
        kill_conditions = []
    return {
        "paper_only": config.get("paper_only") is True,
        "broker_connection_allowed_false": config.get("broker_connection_allowed") is False,
        "order_execution_allowed_false": config.get("order_execution_allowed") is False,
        "real_money_allowed_false": config.get("real_money_allowed") is False,
        "max_open_positions": max_open_positions,
        "max_open_positions_is_one": max_open_positions == 1,
        "risk_percent": risk_percent,
        "risk_amount": risk_amount,
        "risk_policy_matches_canonical": risk_percent == 0.5 and risk_amount == 5.0,
        "spread_unit": spread_unit,
        "max_spread_points": max_spread_points,
        "spread_policy_matches_canonical": spread_unit == "broker_points" and max_spread_points == 15.0,
        "kill_switch_conditions_present": REQUIRED_KILL_SWITCH_CONDITIONS.issubset(set(str(item) for item in kill_conditions)),
    }


def config_boundary_safe(boundaries: dict[str, Any]) -> bool:
    return all(
        bool(boundaries[key])
        for key in (
            "paper_only",
            "broker_connection_allowed_false",
            "order_execution_allowed_false",
            "real_money_allowed_false",
            "max_open_positions_is_one",
            "risk_policy_matches_canonical",
            "spread_policy_matches_canonical",
            "kill_switch_conditions_present",
        )
    )


def no_order_boundary_confirmed(manifest: dict[str, Any]) -> bool:
    return all(manifest.get(flag) is True for flag in NO_ORDER_FLAGS)


def account_snapshot_valid(account: dict[str, Any]) -> bool:
    return (
        account.get("account_trade_mode_label") == "demo"
        and account.get("is_demo_account") is True
        and account.get("redaction_applied") is True
    )


def symbol_snapshot_valid(symbol_snapshot: dict[str, Any], args: argparse.Namespace, max_spread_points: float) -> bool:
    point = safe_float(symbol_snapshot.get("point"))
    volume_min = safe_float(symbol_snapshot.get("volume_min"))
    volume_step = safe_float(symbol_snapshot.get("volume_step"))
    spread = safe_float(symbol_snapshot.get("spread_current_points"))
    if spread is None:
        spread = safe_float(symbol_snapshot.get("spread"))
    return (
        symbol_snapshot.get("symbol") == args.symbol
        and symbol_snapshot.get("visible") is True
        and symbol_snapshot.get("select") is True
        and point is not None
        and point > 0
        and symbol_snapshot.get("digits") == 5
        and volume_min is not None
        and volume_min > 0
        and volume_step is not None
        and volume_step > 0
        and "trade_stops_level" in symbol_snapshot
        and "trade_freeze_level" in symbol_snapshot
        and symbol_snapshot.get("spread_unit") == "broker_points"
        and spread is not None
        and spread <= max_spread_points
    )


def threshold_schema_label(thresholds: dict[str, Any]) -> str:
    features = thresholds.get("features")
    if not isinstance(features, dict):
        return "unknown"
    train_only = True
    legacy = True
    for feature in REQUIRED_THRESHOLD_FEATURES:
        payload = features.get(feature)
        if not isinstance(payload, dict):
            return "unknown"
        train_only = train_only and safe_float(payload.get("low_mid_cutoff")) is not None and safe_float(payload.get("mid_high_cutoff")) is not None
        legacy = legacy and safe_float(payload.get("lower_tercile_boundary")) is not None and safe_float(payload.get("upper_tercile_boundary")) is not None
    if train_only:
        return "train_only_low_mid_mid_high"
    if legacy:
        return "legacy_full_sample_lower_upper"
    return "unknown"


def threshold_artifact_valid(thresholds: dict[str, Any], *, allow_legacy: bool = False) -> bool:
    if thresholds.get("candidate_id") != CANDIDATE_ID:
        return False
    schema_label = threshold_schema_label(thresholds)
    if schema_label == "train_only_low_mid_mid_high":
        return (
            thresholds.get("threshold_lineage") == "train_only"
            and thresholds.get("calibration_scope") == "train_window_only"
            and thresholds.get("full_sample_thresholds_used") is False
            and thresholds.get("oos_rows_used_for_thresholds") is False
        )
    if schema_label == "legacy_full_sample_lower_upper":
        return allow_legacy
    return False


def threshold_metadata(thresholds: dict[str, Any], *, allow_legacy: bool) -> dict[str, Any]:
    return {
        "threshold_lineage": thresholds.get("threshold_lineage", "legacy_full_sample" if threshold_schema_label(thresholds) == "legacy_full_sample_lower_upper" else ""),
        "calibration_scope": thresholds.get("calibration_scope", ""),
        "full_sample_thresholds_used": thresholds.get("full_sample_thresholds_used", True if threshold_schema_label(thresholds) == "legacy_full_sample_lower_upper" else None),
        "oos_rows_used_for_thresholds": thresholds.get("oos_rows_used_for_thresholds", None),
        "threshold_schema_label": threshold_schema_label(thresholds),
        "legacy_full_sample_thresholds_allowed": bool(allow_legacy),
    }


def initial_block_status(
    inputs: dict[str, Any],
    boundaries: dict[str, Any],
    warnings: list[dict[str, Any]],
    *,
    allow_legacy: bool,
) -> str | None:
    if missing_source_artifact_count(inputs["paths"]):
        return "blocked_missing_required_artifact"
    if unreadable_source_artifact_count(warnings):
        return "blocked_unreadable_input"
    if inputs["plan_manifest"].get("plan_status") != "demo_no_order_dry_run_plan_available_with_caveats":
        return "blocked_by_plan_status"
    if inputs["env_manifest"].get("environment_check_status") != "environment_check_available_with_caveats":
        return "blocked_by_environment_check_status"
    if not config_boundary_safe(boundaries):
        return "blocked_by_config_boundary"
    if not no_order_boundary_confirmed(inputs["env_manifest"]) or not no_order_boundary_confirmed(inputs["plan_manifest"]):
        return "blocked_by_no_order_boundary"
    if not account_snapshot_valid(inputs["account_snapshot"]):
        return "blocked_by_environment_check_status"
    if not symbol_snapshot_valid(inputs["symbol_snapshot"], inputs["args"], boundaries["max_spread_points"] or 15.0):
        return "blocked_by_environment_check_status"
    if not threshold_artifact_valid(inputs["thresholds"], allow_legacy=allow_legacy):
        return "blocked_by_threshold_artifact"
    if blocking_warnings(warnings):
        return "blocked_unreadable_input"
    return None


def parse_time_server(value: Any) -> datetime | None:
    if value in ("", None):
        return None
    text = str(value).strip()
    candidates = [text, text.replace("Z", "+00:00")]
    if " " in text and "T" not in text:
        candidates.append(text.replace(" ", "T"))
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def inspect_latest_db_time_server(db_path: Path, table_name: str, symbol: str, timeframe: str) -> str:
    if not db_path.exists():
        return ""
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            if table_exists is None:
                return ""
            columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})")}
            if "time_server" not in columns:
                return ""
            filters: list[str] = []
            params: list[Any] = []
            if "symbol" in columns:
                filters.append(f"{quote_identifier('symbol')} = ?")
                params.append(symbol)
            if "timeframe" in columns:
                filters.append(f"{quote_identifier('timeframe')} = ?")
                params.append(timeframe)
            where = f" WHERE {' AND '.join(filters)}" if filters else ""
            query = f"SELECT MAX({quote_identifier('time_server')}) FROM {quote_identifier(table_name)}{where}"
            row = connection.execute(query, params).fetchone()
    except sqlite3.Error:
        return ""
    return str(row[0] or "") if row else ""


def inspect_latest_db_times(args: argparse.Namespace, evaluated_time_server: str) -> dict[str, Any]:
    latest_feature = inspect_latest_db_time_server(
        Path(args.feature_source_db),
        str(args.feature_source_table),
        str(args.symbol),
        str(args.timeframe),
    )
    latest_bar = inspect_latest_db_time_server(
        Path(args.feature_source_db),
        "price_bars",
        str(args.symbol),
        str(args.timeframe),
    )
    return {
        "latest_db_price_bar_time_server": latest_bar,
        "latest_db_feature_time_server": latest_feature or evaluated_time_server,
    }


def alignment_evidence(args: argparse.Namespace, evaluated_time_server: str, db_times: dict[str, Any]) -> dict[str, Any]:
    latest_mt5 = str(args.latest_mt5_closed_bar_time_server or "").strip()
    latest_feature = str(db_times.get("latest_db_feature_time_server") or evaluated_time_server or "").strip()
    status = str(args.mt5_time_basis_status or "").strip()
    if not status:
        status = "mt5_alignment_checked" if latest_mt5 else "live_data_mt5_time_basis_unavailable"

    evidence: dict[str, Any] = {
        "time_server_source": "raw_broker_server_time_or_existing_db_time_server",
        "import_time_basis": "mt5_broker_server_time_when_available" if latest_mt5 else "mt5_time_basis_unavailable",
        "pc_utc_now": str(args.pc_utc_now or ""),
        "mt5_tick_time_server": str(args.mt5_tick_time_server or ""),
        "latest_mt5_closed_bar_time_server": latest_mt5,
        "latest_db_price_bar_time_server": str(db_times.get("latest_db_price_bar_time_server") or ""),
        "latest_db_feature_time_server": latest_feature,
        "evaluated_feature_time_server": evaluated_time_server,
        "db_lag_bars_vs_mt5_latest_closed_bar": None,
        "db_lag_minutes_vs_mt5_latest_closed_bar": None,
        "mt5_server_time_offset_seconds_vs_pc_utc": args.mt5_server_time_offset_seconds_vs_pc_utc,
        "live_alignment_status": status,
    }
    if not latest_mt5:
        if bool(args.require_mt5_alignment):
            evidence["live_alignment_status"] = "live_data_mt5_time_basis_unavailable"
        return evidence

    mt5_dt = parse_time_server(latest_mt5)
    feature_dt = parse_time_server(latest_feature)
    if mt5_dt is None or feature_dt is None:
        evidence["live_alignment_status"] = "live_data_mt5_alignment_unparseable"
        return evidence

    lag_minutes = (mt5_dt - feature_dt).total_seconds() / 60.0
    lag_bars = lag_minutes / float(args.timeframe_minutes)
    evidence["db_lag_minutes_vs_mt5_latest_closed_bar"] = round(lag_minutes, 6)
    evidence["db_lag_bars_vs_mt5_latest_closed_bar"] = round(lag_bars, 6)
    tolerance_minutes = float(args.db_lag_tolerance_bars) * float(args.timeframe_minutes)
    if lag_minutes > tolerance_minutes:
        evidence["live_alignment_status"] = "live_data_blocked_db_lagging_mt5_latest_bar"
    elif lag_minutes < -float(args.timeframe_minutes):
        evidence["live_alignment_status"] = "live_data_blocked_db_ahead_of_mt5_latest_bar"
    else:
        evidence["live_alignment_status"] = "live_data_aligned_with_mt5_latest_bar"
    return evidence


def inspect_schema(db_path: Path, table_name: str) -> dict[str, Any]:
    if table_name in BLOCKED_FEATURE_TABLES:
        return {"db_exists": db_path.exists(), "table_exists": False, "columns": set(), "error": "blocked_feature_table"}
    if table_name not in ALLOWLISTED_FEATURE_TABLES:
        return {"db_exists": db_path.exists(), "table_exists": False, "columns": set(), "error": "non_allowlisted_feature_table"}
    if not db_path.exists():
        return {"db_exists": False, "table_exists": False, "columns": set(), "error": ""}
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            table_exists = (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone()
                is not None
            )
            columns: set[str] = set()
            if table_exists:
                columns = {
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
                }
            return {"db_exists": True, "table_exists": table_exists, "columns": columns, "error": ""}
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return {"db_exists": True, "table_exists": False, "columns": set(), "error": str(exc)}


def fetch_latest_row(args: argparse.Namespace, columns: set[str]) -> dict[str, Any] | None:
    selected_columns = [column for column in [*REQUIRED_ROW_COLUMNS, *OPTIONAL_ROW_COLUMNS] if column in columns]
    filters: list[str] = []
    params: list[Any] = []
    if "symbol" in columns:
        filters.append(f"{quote_identifier('symbol')} = ?")
        params.append(args.symbol)
    if "timeframe" in columns:
        filters.append(f"{quote_identifier('timeframe')} = ?")
        params.append(args.timeframe)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = (
        f"SELECT {', '.join(quote_identifier(column) for column in selected_columns)} "
        f"FROM {quote_identifier(str(args.feature_source_table))} {where} "
        f"ORDER BY {quote_identifier('time_server')} DESC LIMIT 1"
    )
    uri = f"file:{Path(args.feature_source_db).resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    if row is None:
        return None
    return {column: row[column] for column in selected_columns}


def bucket_for_value(value: float | None, lower: float, upper: float) -> str:
    if value is None:
        return "unreadable"
    if value <= lower:
        return "low_tercile"
    if value <= upper:
        return "mid_tercile"
    return "high_tercile"


def threshold_values(thresholds: dict[str, Any]) -> dict[str, float]:
    features = thresholds["features"]
    if threshold_schema_label(thresholds) == "train_only_low_mid_mid_high":
        return {
            "close_to_ma_fast_atr_20_lower": float(features["close_to_ma_fast_atr_20"]["low_mid_cutoff"]),
            "close_to_ma_fast_atr_20_upper": float(features["close_to_ma_fast_atr_20"]["mid_high_cutoff"]),
            "tick_volume_percentile_100_lower": float(features["tick_volume_percentile_100"]["low_mid_cutoff"]),
            "tick_volume_percentile_100_upper": float(features["tick_volume_percentile_100"]["mid_high_cutoff"]),
        }
    return {
        "close_to_ma_fast_atr_20_lower": float(features["close_to_ma_fast_atr_20"]["lower_tercile_boundary"]),
        "close_to_ma_fast_atr_20_upper": float(features["close_to_ma_fast_atr_20"]["upper_tercile_boundary"]),
        "tick_volume_percentile_100_lower": float(features["tick_volume_percentile_100"]["lower_tercile_boundary"]),
        "tick_volume_percentile_100_upper": float(features["tick_volume_percentile_100"]["upper_tercile_boundary"]),
    }


def read_state(path: Path) -> tuple[dict[str, Any], str, bool]:
    if not path.exists():
        return {"has_open_paper_trade": False}, "", False
    state, error = read_json(path)
    if error:
        return {}, error, True
    return state, "", True


def config_values(config: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    spread_unit = str(nested_get(config, "spread_and_session_controls", "spread_unit") or "broker_points")
    max_spread_points = safe_float(nested_get(config, "spread_and_session_controls", "max_spread_points")) or 15.0
    return {
        "direction": str(nested_get(config, "candidate", "direction") or "short"),
        "regime_column": str(nested_get(config, "entry_rule", "regime_column") or "hour_session"),
        "regime_value": str(nested_get(config, "entry_rule", "regime_value") or "Off_hours"),
        "tp_atr": safe_float(nested_get(config, "risk_reward", "tp_atr")) or 1.5,
        "sl_atr": safe_float(nested_get(config, "risk_reward", "sl_atr")) or 1.0,
        "horizon_bars": int(nested_get(config, "candidate", "target_horizon") or 10),
        "same_bar_policy": str(nested_get(config, "risk_reward", "same_bar_policy") or "stop_first"),
        "max_spread_points": max_spread_points,
        "spread_unit": spread_unit,
        "spread_policy_matches_canonical": spread_unit == "broker_points" and max_spread_points == 15.0,
        "risk_percent": safe_float(policy.get("risk_percent_max")) or 0.5,
        "risk_amount": safe_float(policy.get("risk_amount_max")) or 5.0,
    }


def current_live_spread_gate(args: argparse.Namespace, max_spread_points: float) -> dict[str, Any]:
    current_spread = safe_float(args.current_broker_spread_points)
    source = str(args.current_broker_spread_source or "").strip()
    source_unavailable = source in {"unavailable", "not_checked_no_broker_context"}
    checked = current_spread is not None or bool(source and source != "not_checked_no_broker_context")
    live_context = bool(args.require_mt5_alignment) or checked
    if current_spread is None or source_unavailable:
        if live_context:
            return {
                "current_broker_spread_points": "",
                "current_broker_spread_source": source or "unavailable",
                "current_broker_spread_within_policy": False,
                "current_broker_spread_policy_max_points": max_spread_points,
                "live_spread_gate_status": "blocked_current_spread_unavailable",
            }
        return {
            "current_broker_spread_points": "",
            "current_broker_spread_source": "not_checked_no_broker_context",
            "current_broker_spread_within_policy": None,
            "current_broker_spread_policy_max_points": max_spread_points,
            "live_spread_gate_status": "live_spread_not_checked_no_broker_context",
        }
    within_policy = current_spread <= max_spread_points
    return {
        "current_broker_spread_points": current_spread,
        "current_broker_spread_source": source or "provided_current_broker_spread_points",
        "current_broker_spread_within_policy": within_policy,
        "current_broker_spread_policy_max_points": max_spread_points,
        "live_spread_gate_status": "live_spread_within_policy" if within_policy else "blocked_current_spread_above_policy",
    }


def evaluate_decision(
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    policy: dict[str, Any],
    thresholds: dict[str, Any],
    row: dict[str, Any] | None,
    db_times: dict[str, Any],
    state: dict[str, Any],
    state_error: str,
    schema_block_reason: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    cfg = config_values(config, policy)
    threshold = threshold_values(thresholds)
    block_reasons: list[str] = []
    skip_reasons: list[str] = []
    if schema_block_reason:
        block_reasons.append(schema_block_reason)
    if row is None and not schema_block_reason:
        block_reasons.append("latest_feature_row_missing")
    if state_error:
        block_reasons.append("state_json_unreadable")
    if state.get("has_open_paper_trade") is True:
        block_reasons.append("existing_open_local_state")

    time_server = row.get("time_server", "") if row else ""
    alignment = alignment_evidence(args, str(time_server or ""), db_times)
    parsed_time = parse_time_server(time_server)
    staleness_hours: float | None = None
    feature_row_fresh = False
    if row:
        if parsed_time is None:
            block_reasons.append("feature_time_unparseable")
        else:
            staleness_hours = max(0.0, (utc_now() - parsed_time).total_seconds() / 3600.0)
            feature_row_fresh = staleness_hours <= float(args.max_staleness_hours)
            if not feature_row_fresh:
                block_reasons.append("stale_feature_row")
    if alignment["live_alignment_status"] in {
        "live_data_blocked_db_lagging_mt5_latest_bar",
        "live_data_blocked_db_ahead_of_mt5_latest_bar",
        "live_data_mt5_alignment_unparseable",
    }:
        block_reasons.append(str(alignment["live_alignment_status"]))
        feature_row_fresh = False
        add_warning(
            warnings,
            args=args,
            warning_code=str(alignment["live_alignment_status"]),
            message="Latest local DB feature row is not aligned with the latest MT5 closed bar evidence.",
            source=args.feature_source_db,
            blocking_warning=True,
        )
    elif bool(args.require_mt5_alignment) and alignment["live_alignment_status"] == "live_data_mt5_time_basis_unavailable":
        block_reasons.append("live_data_mt5_time_basis_unavailable")
        feature_row_fresh = False
        add_warning(
            warnings,
            args=args,
            warning_code="live_data_mt5_time_basis_unavailable",
            message="MT5 latest closed bar time was required but unavailable; live alignment was not verified.",
            source=args.feature_source_db,
            blocking_warning=True,
        )

    live_spread = current_live_spread_gate(args, cfg["max_spread_points"])
    if live_spread["live_spread_gate_status"] in {"blocked_current_spread_above_policy", "blocked_current_spread_unavailable"}:
        block_reasons.append(str(live_spread["live_spread_gate_status"]))
        add_warning(
            warnings,
            args=args,
            warning_code=str(live_spread["live_spread_gate_status"]),
            message=(
                "Current live broker spread is required for live shadow/no-order continuation "
                "and is either unavailable or above policy."
            ),
            source=live_spread["current_broker_spread_source"] or "mt5_live_spread",
            blocking_warning=True,
        )

    close_value = safe_float(row.get("close")) if row else None
    atr_value = safe_float(row.get("atr_20")) if row else None
    spread_value = safe_float(row.get("spread")) if row else None
    feature_a = safe_float(row.get("close_to_ma_fast_atr_20")) if row else None
    feature_b = safe_float(row.get("tick_volume_percentile_100")) if row else None
    observed_session = str(row.get(cfg["regime_column"]) or "") if row else ""
    bucket_a = bucket_for_value(feature_a, threshold["close_to_ma_fast_atr_20_lower"], threshold["close_to_ma_fast_atr_20_upper"])
    bucket_b = bucket_for_value(feature_b, threshold["tick_volume_percentile_100_lower"], threshold["tick_volume_percentile_100_upper"])

    if row and not block_reasons:
        missing_required = []
        for column, value in (
            ("close", close_value),
            ("atr_20", atr_value),
            ("spread", spread_value),
            ("close_to_ma_fast_atr_20", feature_a),
            ("tick_volume_percentile_100", feature_b),
        ):
            if value is None:
                missing_required.append(column)
        if missing_required:
            block_reasons.append("required_row_value_missing")
            add_warning(
                warnings,
                args=args,
                warning_code="required_row_value_missing",
                message=f"Required row values are missing or unreadable: {', '.join(missing_required)}.",
                source=args.feature_source_table,
                blocking_warning=True,
            )
        if close_value is not None and close_value <= 0:
            block_reasons.append("close_unreadable_or_nonpositive")
        if atr_value is not None and atr_value <= 0:
            block_reasons.append("atr_unreadable_or_nonpositive")

    if row and not block_reasons:
        if observed_session != cfg["regime_value"]:
            skip_reasons.append("session_mismatch")
        if spread_value is not None and spread_value > cfg["max_spread_points"]:
            skip_reasons.append("spread_above_threshold")
        if bucket_a != "high_tercile":
            skip_reasons.append("close_to_ma_fast_atr_20_bucket_mismatch")
        if bucket_b != "mid_tercile":
            skip_reasons.append("tick_volume_percentile_100_bucket_mismatch")

    decision_label = "would_signal"
    dry_run_status = "demo_no_order_dry_run_would_signal"
    if block_reasons:
        decision_label = "would_block"
        dry_run_status = "demo_no_order_dry_run_would_block"
    elif skip_reasons:
        decision_label = "would_skip"
        dry_run_status = "demo_no_order_dry_run_would_skip"

    entry_reference_price: float | str = ""
    tp_price_preview: float | str = ""
    sl_price_preview: float | str = ""
    if decision_label == "would_signal" and close_value is not None and atr_value is not None:
        entry_reference_price = close_value
        if cfg["direction"] == "short":
            tp_price_preview = close_value - cfg["tp_atr"] * atr_value
            sl_price_preview = close_value + cfg["sl_atr"] * atr_value
        else:
            tp_price_preview = close_value + cfg["tp_atr"] * atr_value
            sl_price_preview = close_value - cfg["sl_atr"] * atr_value

    return {
        "decision_label": decision_label,
        "dry_run_status": dry_run_status,
        "block_reasons": list(dict.fromkeys(block_reasons)),
        "skip_reasons": list(dict.fromkeys(skip_reasons)),
        "feature_row_staleness_hours": staleness_hours,
        "feature_row_fresh": feature_row_fresh,
        "session_observed": observed_session,
        "spread": spread_value,
        "spread_unit": cfg["spread_unit"],
        "max_spread_points": cfg["max_spread_points"],
        "spread_policy_matches_canonical": cfg["spread_policy_matches_canonical"],
        "spread_within_gate": spread_value is not None and spread_value <= cfg["max_spread_points"],
        "close": close_value,
        "atr_20": atr_value,
        "feature_a": feature_a,
        "feature_b": feature_b,
        "bucket_a": bucket_a,
        "bucket_b": bucket_b,
        "entry_reference_price": entry_reference_price,
        "tp_price_preview": tp_price_preview,
        "sl_price_preview": sl_price_preview,
        "horizon_bars": cfg["horizon_bars"],
        "same_bar_policy": cfg["same_bar_policy"],
        "timeout_policy": f"h{cfg['horizon_bars']}",
        "risk_percent_configured": cfg["risk_percent"],
        "risk_amount_configured": cfg["risk_amount"],
        "volume_preview_status": "not_computed_no_order_calc_forbidden",
        "direction": cfg["direction"],
        "time_server": time_server,
        "evaluated_feature_time_server": time_server,
        "feature_row_spread_broker_points": spread_value,
        "feature_row_spread_source": "db_candle_spread",
        **live_spread,
        "spread_source": "db_candle_spread",
        **alignment,
        "symbol": row.get("symbol", args.symbol) if row else args.symbol,
        "timeframe": row.get("timeframe", args.timeframe) if row else args.timeframe,
    }


def status_for_initial_block(status: str) -> dict[str, Any]:
    return {
        "decision_label": "would_block",
        "dry_run_status": status,
        "block_reasons": [status],
        "skip_reasons": [],
        "feature_row_staleness_hours": None,
        "feature_row_fresh": False,
        "session_observed": "",
        "spread": None,
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "spread_policy_matches_canonical": True,
        "spread_within_gate": False,
        "close": None,
        "atr_20": None,
        "feature_a": None,
        "feature_b": None,
        "bucket_a": "",
        "bucket_b": "",
        "entry_reference_price": "",
        "tp_price_preview": "",
        "sl_price_preview": "",
        "horizon_bars": 10,
        "same_bar_policy": "stop_first",
        "timeout_policy": "h10",
        "risk_percent_configured": 0.5,
        "risk_amount_configured": 5.0,
        "volume_preview_status": "not_applicable",
        "direction": "short",
        "time_server": "",
        "evaluated_feature_time_server": "",
        "time_server_source": "raw_broker_server_time_or_existing_db_time_server",
        "import_time_basis": "mt5_time_basis_unavailable",
        "pc_utc_now": "",
        "mt5_tick_time_server": "",
        "latest_mt5_closed_bar_time_server": "",
        "latest_db_price_bar_time_server": "",
        "latest_db_feature_time_server": "",
        "db_lag_bars_vs_mt5_latest_closed_bar": None,
        "db_lag_minutes_vs_mt5_latest_closed_bar": None,
        "mt5_server_time_offset_seconds_vs_pc_utc": None,
        "live_alignment_status": "not_checked_initial_block",
        "feature_row_spread_broker_points": None,
        "feature_row_spread_source": "db_candle_spread",
        "current_broker_spread_points": "",
        "current_broker_spread_source": "not_checked_no_broker_context",
        "current_broker_spread_within_policy": None,
        "current_broker_spread_policy_max_points": 15.0,
        "live_spread_gate_status": "live_spread_not_checked_no_broker_context",
        "spread_source": "db_candle_spread",
        "symbol": "GBPUSD",
        "timeframe": "M15",
    }


def decision_row(args: argparse.Namespace, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "decision_label": result["decision_label"],
        "dry_run_status": result["dry_run_status"],
        "time_server": result["time_server"],
        "evaluated_feature_time_server": result["evaluated_feature_time_server"],
        "time_server_source": result["time_server_source"],
        "import_time_basis": result["import_time_basis"],
        "pc_utc_now": result["pc_utc_now"],
        "mt5_tick_time_server": result["mt5_tick_time_server"],
        "latest_mt5_closed_bar_time_server": result["latest_mt5_closed_bar_time_server"],
        "latest_db_price_bar_time_server": result["latest_db_price_bar_time_server"],
        "latest_db_feature_time_server": result["latest_db_feature_time_server"],
        "db_lag_bars_vs_mt5_latest_closed_bar": result["db_lag_bars_vs_mt5_latest_closed_bar"],
        "db_lag_minutes_vs_mt5_latest_closed_bar": result["db_lag_minutes_vs_mt5_latest_closed_bar"],
        "mt5_server_time_offset_seconds_vs_pc_utc": result["mt5_server_time_offset_seconds_vs_pc_utc"],
        "live_alignment_status": result["live_alignment_status"],
        "symbol": result["symbol"],
        "timeframe": result["timeframe"],
        "direction": result["direction"],
        "session_observed": result["session_observed"],
        "spread": result["spread"],
        "feature_row_spread_broker_points": result["feature_row_spread_broker_points"],
        "feature_row_spread_source": result["feature_row_spread_source"],
        "current_broker_spread_points": result["current_broker_spread_points"],
        "current_broker_spread_source": result["current_broker_spread_source"],
        "current_broker_spread_within_policy": result["current_broker_spread_within_policy"],
        "current_broker_spread_policy_max_points": result["current_broker_spread_policy_max_points"],
        "live_spread_gate_status": result["live_spread_gate_status"],
        "spread_source": result["spread_source"],
        "spread_unit": result["spread_unit"],
        "max_spread_points": result["max_spread_points"],
        "close": result["close"],
        "atr_20": result["atr_20"],
        "close_to_ma_fast_atr_20": result["feature_a"],
        "close_to_ma_fast_atr_20_bucket": result["bucket_a"],
        "tick_volume_percentile_100": result["feature_b"],
        "tick_volume_percentile_100_bucket": result["bucket_b"],
        "entry_reference_price": result["entry_reference_price"],
        "tp_price_preview": result["tp_price_preview"],
        "sl_price_preview": result["sl_price_preview"],
        "horizon_bars": result["horizon_bars"],
        "same_bar_policy": result["same_bar_policy"],
        "timeout_policy": result["timeout_policy"],
        "risk_percent_configured": result["risk_percent_configured"],
        "volume_preview_status": result["volume_preview_status"],
        "skip_reasons": ";".join(result["skip_reasons"]),
        "block_reasons": ";".join(result["block_reasons"]),
        "no_order_request_constructed": True,
        "no_order_execution_performed": True,
    }


def checklist_row(
    args: argparse.Namespace,
    area: str,
    name: str,
    status: str,
    observed: Any,
    expected: Any,
    evidence: Path | str,
    caveat: str,
    warning_code: str = "",
    blocking: bool = True,
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "check_area": area,
        "check_name": name,
        "check_status": status,
        "observed_value": observed,
        "expected_value": expected,
        "blocking_if_failed": blocking,
        "evidence_source": str(evidence),
        "caveat": caveat,
        "warning_code": warning_code,
    }


def build_checklist(args: argparse.Namespace, result: dict[str, Any], inputs: dict[str, Any], row: dict[str, Any] | None, schema_ok: bool) -> list[dict[str, Any]]:
    passed = "passed"
    blocked = "failed" if result["decision_label"] == "would_block" else "passed"
    skipped = "skipped" if result["decision_label"] == "would_block" else "passed"
    live_spread_check_status = (
        "failed"
        if result["live_spread_gate_status"] in {"blocked_current_spread_above_policy", "blocked_current_spread_unavailable"}
        else "skipped"
        if result["live_spread_gate_status"] == "live_spread_not_checked_no_broker_context"
        else "passed"
    )
    return [
        checklist_row(args, "source_artifacts_loaded", "source artifacts loaded", passed if not missing_source_artifact_count(inputs["paths"]) else "failed", "loaded", "all required artifacts", args.demo_no_order_dry_run_plan_dir, "artifact_only"),
        checklist_row(args, "config_canonical", "canonical config checked", passed, inputs["paths"]["config"], "spread15 paper-only config", args.demo_strategy_config, "no_settings_changed"),
        checklist_row(args, "environment_check_available", "environment check source acceptable", passed if inputs["env_manifest"].get("environment_check_status") == "environment_check_available_with_caveats" else "failed", inputs["env_manifest"].get("environment_check_status"), "environment_check_available_with_caveats", inputs["paths"]["env_manifest"], "artifact_evidence_only"),
        checklist_row(args, "demo_account_confirmed_from_artifact", "demo account confirmed from redacted snapshot", passed if account_snapshot_valid(inputs["account_snapshot"]) else "failed", inputs["account_snapshot"].get("account_trade_mode_label"), "demo", inputs["paths"]["account_snapshot"], "no_account_query"),
        checklist_row(args, "symbol_contract_confirmed_from_artifact", "symbol contract confirmed from snapshot", passed, inputs["symbol_snapshot"].get("symbol"), args.symbol, inputs["paths"]["symbol_snapshot"], "no_symbol_query"),
        checklist_row(args, "no_order_boundary_confirmed", "no-order boundary confirmed", passed if no_order_boundary_confirmed(inputs["env_manifest"]) else "failed", "source flags", "all true", inputs["paths"]["env_manifest"], "request_construction_forbidden"),
        checklist_row(args, "feature_source_read_only", "feature source read-only", passed if schema_ok else "failed", args.feature_source_table, "allowlisted read-only table", args.feature_source_db, "mode_ro_connection"),
        checklist_row(args, "latest_feature_row_loaded", "latest feature row loaded", passed if row else "failed", bool(row), True, args.feature_source_table, "latest_row_only"),
        checklist_row(args, "feature_row_freshness_checked", "feature row freshness checked", blocked if "stale_feature_row" in result["block_reasons"] or "feature_time_unparseable" in result["block_reasons"] else passed, result["feature_row_staleness_hours"], f"<= {args.max_staleness_hours} hours", args.feature_source_table, "freshness_gate"),
        checklist_row(args, "mt5_db_alignment_checked", "MT5 latest closed bar alignment checked", blocked if str(result["live_alignment_status"]).startswith("live_data_blocked") or "live_data_mt5_time_basis_unavailable" in result["block_reasons"] else passed, result["live_alignment_status"], "aligned or explicitly unavailable when not required", args.feature_source_db, "mt5_time_basis_diagnostic"),
        checklist_row(args, "session_gate_evaluated", "session gate evaluated", skipped, result["session_observed"], "Off_hours", args.feature_source_table, "would_skip_if_mismatch"),
        checklist_row(args, "spread_gate_evaluated", "spread gate evaluated", skipped, result["spread"], "<= 15.0 broker_points", args.feature_source_table, "would_skip_if_above_gate"),
        checklist_row(args, "live_spread_gate_evaluated", "current live broker spread gate evaluated", live_spread_check_status, result["current_broker_spread_points"], f"<= {result['current_broker_spread_policy_max_points']} broker_points", result["current_broker_spread_source"], result["live_spread_gate_status"], warning_code=result["live_spread_gate_status"] if live_spread_check_status == "failed" else ""),
        checklist_row(args, "required_features_evaluated", "required features evaluated", blocked if "required_row_value_missing" in result["block_reasons"] else skipped, {"close": result["close"], "atr_20": result["atr_20"]}, "required values readable", args.feature_source_table, "would_block_if_missing"),
        checklist_row(args, "frozen_tercile_buckets_evaluated", "frozen tercile buckets evaluated", skipped, {"a": result["bucket_a"], "b": result["bucket_b"]}, "high_tercile and mid_tercile", args.tercile_thresholds_json, "frozen_thresholds_only"),
        checklist_row(args, "one_open_trade_state_checked", "one-open-trade state checked", blocked if "existing_open_local_state" in result["block_reasons"] else passed, "existing_open_local_state" in result["block_reasons"], False, args.state_json, "state_not_mutated"),
        checklist_row(args, "decision_label_emitted", "decision label emitted", passed, result["decision_label"], "would_skip/would_signal/would_block", OUTPUT_DECISION, "no_trading_decision"),
        checklist_row(args, "preview_prices_no_order", "preview prices without order request", passed, result["volume_preview_status"], "not_computed_no_order_calc_forbidden", OUTPUT_DECISION, "preview_only"),
        checklist_row(args, "state_preview_written", "state preview written", passed, OUTPUT_STATE_PREVIEW, "state preview artifact", OUTPUT_STATE_PREVIEW, "no_state_mutation"),
        checklist_row(args, "no_order_evidence_written", "no-order evidence written", passed, OUTPUT_NO_ORDER, "all no-order flags true", OUTPUT_NO_ORDER, "no_external_action"),
    ]


def no_order_evidence_row(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_trading_decision_performed": True,
        "evidence_label": "no_order_boundary_confirmed",
        "caveat": "no_request_no_check_no_calc_no_execution",
    }


def recommended_next_step(status: str, live_spread_gate_status: str = "") -> str:
    if live_spread_gate_status in {"blocked_current_spread_above_policy", "blocked_current_spread_unavailable"}:
        return "wait_for_current_spread_within_policy_and_rerun_live_shadow"
    if status == "demo_no_order_dry_run_would_signal":
        return "build_fixed_candidate_demo_would_signal_review"
    if status == "demo_no_order_dry_run_would_skip":
        return "monitor_next_feature_row_or_run_again_later"
    return "fix_demo_no_order_dry_run_blocker"


def build_state_preview(args: argparse.Namespace, state: dict[str, Any], state_exists: bool, result: dict[str, Any]) -> dict[str, Any]:
    existing_open = state.get("has_open_paper_trade") is True
    return {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "current_state_source": str(args.state_json) if state_exists else "missing_optional_state_initialized_closed",
        "existing_open_state_detected": existing_open,
        "would_create_local_state_preview": result["decision_label"] == "would_signal",
        "preview_signal_time_server": result["time_server"],
        "entry_reference_price_preview": result["entry_reference_price"],
        "tp_price_preview": result["tp_price_preview"],
        "sl_price_preview": result["sl_price_preview"],
        "no_state_mutation_performed": True,
    }


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    result: dict[str, Any],
    checklist: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    existing_open_state: bool,
    thresholds: dict[str, Any],
) -> None:
    metadata = threshold_metadata(thresholds, allow_legacy=bool(args.allow_legacy_full_sample_thresholds))
    output = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_no_order_dry_run_plan_dir": str(args.demo_no_order_dry_run_plan_dir),
        "demo_environment_check_dir": str(args.demo_environment_check_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "tercile_thresholds_json": str(args.tercile_thresholds_json),
        "numeric_tercile_thresholds_json": str(args.tercile_thresholds_json),
        "canonical_registry": str(args.canonical_registry),
        **metadata,
        "feature_source_db": str(args.feature_source_db),
        "feature_source_table": args.feature_source_table,
        "state_json": str(args.state_json) if args.state_json else "",
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "dry_run_status": result["dry_run_status"],
        "decision_label": result["decision_label"],
        "time_server": result["time_server"],
        "evaluated_feature_time_server": result["evaluated_feature_time_server"],
        "time_server_source": result["time_server_source"],
        "import_time_basis": result["import_time_basis"],
        "pc_utc_now": result["pc_utc_now"],
        "mt5_tick_time_server": result["mt5_tick_time_server"],
        "latest_mt5_closed_bar_time_server": result["latest_mt5_closed_bar_time_server"],
        "latest_db_price_bar_time_server": result["latest_db_price_bar_time_server"],
        "latest_db_feature_time_server": result["latest_db_feature_time_server"],
        "db_lag_bars_vs_mt5_latest_closed_bar": result["db_lag_bars_vs_mt5_latest_closed_bar"],
        "db_lag_minutes_vs_mt5_latest_closed_bar": result["db_lag_minutes_vs_mt5_latest_closed_bar"],
        "mt5_server_time_offset_seconds_vs_pc_utc": result["mt5_server_time_offset_seconds_vs_pc_utc"],
        "live_alignment_status": result["live_alignment_status"],
        "feature_row_staleness_hours": result["feature_row_staleness_hours"],
        "feature_row_fresh": result["feature_row_fresh"],
        "session_observed": result["session_observed"],
        "spread": result["spread"],
        "feature_row_spread_broker_points": result["feature_row_spread_broker_points"],
        "feature_row_spread_source": result["feature_row_spread_source"],
        "current_broker_spread_points": result["current_broker_spread_points"],
        "current_broker_spread_source": result["current_broker_spread_source"],
        "current_broker_spread_within_policy": result["current_broker_spread_within_policy"],
        "current_broker_spread_policy_max_points": result["current_broker_spread_policy_max_points"],
        "live_spread_gate_status": result["live_spread_gate_status"],
        "spread_source": result["spread_source"],
        "spread_unit": result["spread_unit"],
        "max_spread_points": result["max_spread_points"],
        "spread_policy_matches_canonical": result["spread_policy_matches_canonical"],
        "spread_within_gate": result["spread_within_gate"],
        "close": result["close"],
        "atr_20": result["atr_20"],
        "close_to_ma_fast_atr_20_bucket": result["bucket_a"],
        "tick_volume_percentile_100_bucket": result["bucket_b"],
        "existing_open_state_detected": existing_open_state,
        "entry_reference_price": result["entry_reference_price"],
        "tp_price_preview": result["tp_price_preview"],
        "sl_price_preview": result["sl_price_preview"],
        "volume_preview_status": result["volume_preview_status"],
        "risk_percent_configured": result["risk_percent_configured"],
        "risk_amount_configured": result.get("risk_amount_configured", 5.0),
        "checklist_row_count": len(checklist),
        "decision_row_count": 1,
        "warning_count": len(warnings),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "skip_reason_count": len(result["skip_reasons"]),
        "block_reason_count": len(result["block_reasons"]),
        "recommended_next_step": recommended_next_step(result["dry_run_status"], result["live_spread_gate_status"]),
        "no_child_scripts_executed": True,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_replay_rerun": True,
        "no_cost_sensitivity_rerun": True,
        "no_recent_holdout_rerun": True,
        "no_optimization_performed": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")


def write_report(path: Path, *, args: argparse.Namespace, result: dict[str, Any], warnings: list[dict[str, Any]], thresholds: dict[str, Any]) -> None:
    metadata = threshold_metadata(thresholds, allow_legacy=bool(args.allow_legacy_full_sample_thresholds))
    lines = [
        "# Fixed Candidate Demo No-Order Dry-Run",
        "",
        "Single-shot no-order decision-path dry-run.",
        "No MT5 connection was performed.",
        "No broker/API connection was performed.",
        "No live account query was performed.",
        "No live symbol query was performed.",
        "No order execution was performed.",
        "No order request was constructed.",
        "No order_check or order_calc call was performed.",
        "No database mutation was performed.",
        "No feature refresh was performed.",
        "No replay, cost sensitivity, recent holdout, or paper workflow was rerun.",
        "No optimization or parameter search was performed.",
        "This dry-run is not future-performance proof.",
        "This dry-run is not demo broker approval.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- demo_no_order_dry_run_plan_dir: `{args.demo_no_order_dry_run_plan_dir}`",
        f"- demo_environment_check_dir: `{args.demo_environment_check_dir}`",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- demo_strategy_spec_dir: `{args.demo_strategy_spec_dir}`",
        f"- tercile_thresholds_json: `{args.tercile_thresholds_json}`",
        f"- threshold_lineage: `{metadata['threshold_lineage']}`",
        f"- calibration_scope: `{metadata['calibration_scope']}`",
        f"- threshold_schema_label: `{metadata['threshold_schema_label']}`",
        f"- legacy_full_sample_thresholds_allowed: `{bool_text(bool(metadata['legacy_full_sample_thresholds_allowed']))}`",
        f"- feature_source_db: `{args.feature_source_db}`",
        f"- feature_source_table: `{args.feature_source_table}`",
        "",
        "## Decision",
        "",
        f"- decision_label: `{result['decision_label']}`",
        f"- dry_run_status: `{result['dry_run_status']}`",
        f"- time_server: `{result['time_server']}`",
        f"- evaluated_feature_time_server: `{result['evaluated_feature_time_server']}`",
        f"- latest_db_price_bar_time_server: `{result['latest_db_price_bar_time_server']}`",
        f"- latest_db_feature_time_server: `{result['latest_db_feature_time_server']}`",
        f"- latest_mt5_closed_bar_time_server: `{result['latest_mt5_closed_bar_time_server']}`",
        f"- db_lag_bars_vs_mt5_latest_closed_bar: `{result['db_lag_bars_vs_mt5_latest_closed_bar']}`",
        f"- db_lag_minutes_vs_mt5_latest_closed_bar: `{result['db_lag_minutes_vs_mt5_latest_closed_bar']}`",
        f"- live_alignment_status: `{result['live_alignment_status']}`",
        f"- session_observed: `{result['session_observed']}`",
        f"- feature_row_spread_broker_points: `{result['feature_row_spread_broker_points']}`",
        f"- feature_row_spread_source: `{result['feature_row_spread_source']}`",
        f"- current_broker_spread_points: `{result['current_broker_spread_points']}`",
        f"- current_broker_spread_source: `{result['current_broker_spread_source']}`",
        f"- current_broker_spread_within_policy: `{result['current_broker_spread_within_policy']}`",
        f"- live_spread_gate_status: `{result['live_spread_gate_status']}`",
        f"- spread_source: `{result['spread_source']}`",
        f"- max_spread_points: `{result['max_spread_points']}`",
        f"- spread_policy_matches_canonical: `{bool_text(bool(result['spread_policy_matches_canonical']))}`",
        f"- close_to_ma_fast_atr_20_bucket: `{result['bucket_a']}`",
        f"- tick_volume_percentile_100_bucket: `{result['bucket_b']}`",
        f"- skip_reasons: `{';'.join(result['skip_reasons'])}`",
        f"- block_reasons: `{';'.join(result['block_reasons'])}`",
        "",
        "## Preview",
        "",
        f"- entry_reference_price: `{result['entry_reference_price']}`",
        f"- tp_price_preview: `{result['tp_price_preview']}`",
        f"- sl_price_preview: `{result['sl_price_preview']}`",
        f"- volume_preview_status: `{result['volume_preview_status']}`",
        "",
        "## Warnings",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{recommended_next_step(result['dry_run_status'], result['live_spread_gate_status'])}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_artifacts(args: argparse.Namespace, output_paths: dict[str, Path]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    inputs = load_inputs(args, warnings)
    inputs["args"] = args
    boundaries = config_boundaries(inputs["config"], inputs["demo_execution_policy"])

    if inputs["config"] and not config_boundary_safe(boundaries):
        add_warning(warnings, args=args, warning_code="config_boundary_unsafe", message="Canonical demo config does not satisfy spread15/no-order boundaries.", source=args.demo_strategy_config, blocking_warning=True)
    if inputs["env_manifest"] and not no_order_boundary_confirmed(inputs["env_manifest"]):
        add_warning(warnings, args=args, warning_code="no_order_boundary_not_confirmed", message="Environment source no-order flags are not all true.", source=inputs["paths"]["env_manifest"], blocking_warning=True)
    if inputs["account_snapshot"] and not account_snapshot_valid(inputs["account_snapshot"]):
        add_warning(warnings, args=args, warning_code="account_snapshot_not_demo", message="Account snapshot does not confirm a redacted demo account.", source=inputs["paths"]["account_snapshot"], blocking_warning=True)
    if inputs["symbol_snapshot"] and boundaries["max_spread_points"] is not None and not symbol_snapshot_valid(inputs["symbol_snapshot"], args, boundaries["max_spread_points"]):
        add_warning(warnings, args=args, warning_code="symbol_or_spread_snapshot_invalid", message="Symbol snapshot or broker-points spread evidence is not acceptable.", source=inputs["paths"]["symbol_snapshot"], blocking_warning=True)
    if inputs["thresholds"] and not threshold_artifact_valid(inputs["thresholds"], allow_legacy=bool(args.allow_legacy_full_sample_thresholds)):
        add_warning(
            warnings,
            args=args,
            warning_code="threshold_artifact_invalid",
            message="Current paths require train-only numeric-tercile thresholds; legacy full-sample thresholds require --allow-legacy-full-sample-thresholds.",
            source=args.tercile_thresholds_json,
            blocking_warning=True,
        )

    initial_status = initial_block_status(
        inputs,
        boundaries,
        warnings,
        allow_legacy=bool(args.allow_legacy_full_sample_thresholds),
    )
    row: dict[str, Any] | None = None
    db_times: dict[str, Any] = {
        "latest_db_price_bar_time_server": "",
        "latest_db_feature_time_server": "",
    }
    schema_ok = False
    schema_block_reason = ""
    state, state_error, state_exists = read_state(Path(args.state_json)) if args.state_json else ({"has_open_paper_trade": False}, "", False)
    if initial_status is None:
        schema = inspect_schema(Path(args.feature_source_db), str(args.feature_source_table))
        if schema["error"]:
            schema_block_reason = str(schema["error"])
            add_warning(warnings, args=args, warning_code="feature_source_blocked", message=f"Feature source blocked or unreadable: {schema_block_reason}.", source=args.feature_source_table, blocking_warning=True)
        elif not schema["db_exists"]:
            schema_block_reason = "feature_source_db_missing"
            add_warning(warnings, args=args, warning_code=schema_block_reason, message="Feature source DB is missing.", source=args.feature_source_db, blocking_warning=True)
        elif not schema["table_exists"]:
            schema_block_reason = "feature_source_table_missing"
            add_warning(warnings, args=args, warning_code=schema_block_reason, message="Feature source table is missing.", source=args.feature_source_table, blocking_warning=True)
        else:
            missing_columns = [column for column in REQUIRED_ROW_COLUMNS if column not in schema["columns"]]
            if missing_columns:
                schema_block_reason = "required_feature_columns_missing"
                add_warning(warnings, args=args, warning_code=schema_block_reason, message=f"Feature table is missing required columns: {', '.join(missing_columns)}.", source=args.feature_source_table, blocking_warning=True)
            else:
                schema_ok = True
                row = fetch_latest_row(args, set(schema["columns"]))
                db_times = inspect_latest_db_times(args, str(row.get("time_server", "") if row else ""))
                if row is None:
                    add_warning(warnings, args=args, warning_code="latest_feature_row_missing", message="No latest feature row was available for the configured scope.", source=args.feature_source_table, blocking_warning=True)

    if initial_status is not None:
        result = status_for_initial_block(initial_status)
    elif schema_block_reason in {"blocked_feature_table", "non_allowlisted_feature_table", "feature_source_db_missing", "feature_source_table_missing", "required_feature_columns_missing"}:
        result = status_for_initial_block("blocked_by_feature_source")
        result["block_reasons"] = [schema_block_reason]
    elif not threshold_artifact_valid(inputs["thresholds"], allow_legacy=bool(args.allow_legacy_full_sample_thresholds)):
        result = status_for_initial_block("blocked_by_threshold_artifact")
    else:
        result = evaluate_decision(
            args=args,
            config=inputs["config"],
            policy=inputs["demo_execution_policy"],
            thresholds=inputs["thresholds"],
            row=row,
            db_times=db_times,
            state=state,
            state_error=state_error,
            schema_block_reason=schema_block_reason,
            warnings=warnings,
        )

    existing_open_state = state.get("has_open_paper_trade") is True
    decision_rows = [decision_row(args, result)]
    checklist = build_checklist(args, result, inputs, row, schema_ok)
    no_order_rows = [no_order_evidence_row(args)]
    state_preview = build_state_preview(args, state, state_exists, result)
    input_snapshot = {"run_id": args.run_id, "row_available": row is not None, "row": row or {}, "no_db_mutation_performed": True}

    write_csv(output_paths["decision"], decision_rows, DECISION_FIELDNAMES)
    write_csv(output_paths["checklist"], checklist, CHECKLIST_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(output_paths["no_order"], no_order_rows, NO_ORDER_FIELDNAMES)
    output_paths["state_preview"].write_text(json.dumps(state_preview, indent=2, sort_keys=True), encoding="utf-8")
    output_paths["input_row_snapshot"].write_text(json.dumps(input_snapshot, indent=2, sort_keys=True, default=str), encoding="utf-8")
    write_report(output_paths["report"], args=args, result=result, warnings=warnings, thresholds=inputs["thresholds"])
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_paths["manifest"].parent,
        result=result,
        checklist=checklist,
        warnings=warnings,
        existing_open_state=existing_open_state,
        thresholds=inputs["thresholds"],
    )
    return {"result": result, "warnings": warnings, "decision_rows": decision_rows, "checklist": checklist}


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    normalize_threshold_args(args)
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    build_artifacts(args, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fixed-candidate demo no-order dry-run decision path.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-no-order-dry-run-plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--demo-environment-check-dir", type=Path, default=DEFAULT_ENVIRONMENT_CHECK_DIR)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy-json", type=Path, default=DEFAULT_DEMO_EXECUTION_POLICY)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--tercile-thresholds-json", type=Path)
    parser.add_argument("--allow-legacy-full-sample-thresholds", action="store_true")
    parser.add_argument("--feature-source-db", type=Path, default=DEFAULT_FEATURE_SOURCE_DB)
    parser.add_argument("--feature-source-table", default=DEFAULT_FEATURE_SOURCE_TABLE)
    parser.add_argument("--state-json", type=Path, default=DEFAULT_STATE_JSON)
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--max-staleness-hours", type=float, default=24.0)
    parser.add_argument("--timeframe-minutes", type=float, default=15.0)
    parser.add_argument("--db-lag-tolerance-bars", type=float, default=1.0)
    parser.add_argument("--require-mt5-alignment", action="store_true")
    parser.add_argument("--mt5-time-basis-status", default="")
    parser.add_argument("--pc-utc-now", default="")
    parser.add_argument("--mt5-tick-time-server", default="")
    parser.add_argument("--latest-mt5-closed-bar-time-server", default="")
    parser.add_argument("--mt5-server-time-offset-seconds-vs-pc-utc", default="")
    parser.add_argument("--current-broker-spread-points")
    parser.add_argument("--current-broker-spread-source", default="")
    parser.add_argument("--current-broker-spread-policy-max-points", type=float)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error, sqlite3.Error) as exc:
        print(f"Fixed-candidate demo no-order dry-run failed: {exc}")
        return 1
    print("Fixed-candidate demo no-order dry-run complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
