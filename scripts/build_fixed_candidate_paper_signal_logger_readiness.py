"""Build an artifact-only readiness packet for a future paper signal logger.

This module checks local paper/demo boundaries, a read-only SQLite feature
schema, and the required numeric-tercile threshold artifact. It does not
implement or run a paper signal logger, connect to MT5, connect to broker/API
services, execute orders, run backtests, run validation, generate data, mutate a
database, or make candidate-quality or trading decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_readiness"
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
    / "gbpusd_short_h10_1_5_off_hours_demo_strategy_spec_v3"
)
DEFAULT_PAPER_RUNNER_COMMAND_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_runner_command_plan"
    / "gbpusd_short_h10_1_5_off_hours_paper_runner_command_plan_v1"
)
DEFAULT_FEATURE_SOURCE_DB = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_FEATURE_SOURCE_TABLE = "price_features"
DEFAULT_TERCILE_THRESHOLDS_JSON = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_numeric_tercile_thresholds"
    / "gbpusd_short_h10_1_5_off_hours_numeric_tercile_thresholds_v1"
    / "fixed_candidate_numeric_tercile_thresholds.json"
)
DEFAULT_STATE_JSON = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_v1"
    / "fixed_candidate_paper_signal_state.json"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_paper_signal_logger_readiness"

SPEC_CSV = "fixed_candidate_demo_strategy_spec.csv"
SPEC_REPORT = "fixed_candidate_demo_strategy_spec_report.md"
SPEC_WARNINGS = "fixed_candidate_demo_strategy_spec_warnings.csv"
SPEC_MANIFEST = "fixed_candidate_demo_strategy_spec_manifest.json"

PLAN_CSV = "fixed_candidate_paper_runner_command_plan.csv"
PLAN_REPORT = "fixed_candidate_paper_runner_command_plan_report.md"
PLAN_WARNINGS = "fixed_candidate_paper_runner_command_plan_warnings.csv"
PLAN_MANIFEST = "fixed_candidate_paper_runner_command_plan_manifest.json"

OUTPUT_CSV = "fixed_candidate_paper_signal_logger_readiness.csv"
OUTPUT_REPORT = "fixed_candidate_paper_signal_logger_readiness_report.md"
OUTPUT_WARNINGS = "fixed_candidate_paper_signal_logger_readiness_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_paper_signal_logger_readiness_manifest.json"

FIELDNAMES = [
    "run_id",
    "readiness_area",
    "artifact_status",
    "readiness_status",
    "source_path",
    "source_table",
    "source_column",
    "required_value",
    "observed_value",
    "evidence_label",
    "caveat",
    "required_next_artifact",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "readiness_area",
    "source_path",
    "blocking_warning",
]

ALLOWLISTED_FEATURE_TABLES = {"price_features", "market_features"}
BLOCKED_SIGNAL_INPUT_TABLES = {"ml_dataset"}
REQUIRED_SOURCE_COLUMNS = (
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
    "hour_session",
    "atr_20",
    "spread",
    "spread_avg_20",
    "time_server",
    "open",
    "high",
    "low",
    "close",
)
OPTIONAL_SOURCE_COLUMNS = ("symbol", "timeframe", "volume", "tick_volume")

REQUIRED_KILL_SWITCH_CONDITIONS = (
    "required_data_missing",
    "required_features_missing",
    "spread_abnormal_or_not_configured",
    "atr_calculation_failed",
    "timeframe_mismatch",
    "session_mismatch",
    "existing_paper_demo_trade_open",
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

REQUIRED_THRESHOLD_BUCKETS = {
    "close_to_ma_fast_atr_20": "high_tercile",
    "tick_volume_percentile_100": "mid_tercile",
}


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
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(loaded, dict):
        return {}, "JSON root must be an object"
    return loaded, ""


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
        "readiness": output_dir / OUTPUT_CSV,
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


def warning_row(
    *,
    warning_code: str,
    message: str,
    readiness_area: str,
    source_path: Path | str,
    blocking_warning: bool,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": "error" if blocking_warning else severity,
        "message": message,
        "readiness_area": readiness_area,
        "source_path": str(source_path),
        "blocking_warning": bool_text(blocking_warning),
    }


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    warning_code: str,
    message: str,
    readiness_area: str,
    source_path: Path | str,
    blocking_warning: bool = False,
    severity: str = "warning",
) -> None:
    warnings.append(
        warning_row(
            warning_code=warning_code,
            message=message,
            readiness_area=readiness_area,
            source_path=source_path,
            blocking_warning=blocking_warning,
            severity=severity,
        )
    )


def base_row(args: argparse.Namespace, readiness_area: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "readiness_area": readiness_area,
        "artifact_status": "available",
        "readiness_status": "ready_for_paper_signal_logger_implementation",
        "source_path": "",
        "source_table": "",
        "source_column": "",
        "required_value": "",
        "observed_value": "",
        "evidence_label": "",
        "caveat": "no_trading_decision_made",
        "required_next_artifact": "",
        "warning_code": "",
        "blocking_warning": False,
    }


def artifact_paths(root: Path, csv_name: str, manifest_name: str, report_name: str, warnings_name: str) -> dict[str, Path]:
    return {
        "dir": root,
        "csv": root / csv_name,
        "manifest": root / manifest_name,
        "report": root / report_name,
        "warnings": root / warnings_name,
    }


def load_artifact_bundle(
    root: Path,
    *,
    csv_name: str,
    manifest_name: str,
    report_name: str,
    warnings_name: str,
) -> dict[str, Any]:
    paths = artifact_paths(root, csv_name, manifest_name, report_name, warnings_name)
    rows, csv_error = read_csv_rows(paths["csv"])
    manifest, manifest_error = read_json(paths["manifest"])
    warnings, warnings_error = read_csv_rows(paths["warnings"])
    report_text = read_text(paths["report"])
    files_present = paths["csv"].exists() and paths["manifest"].exists() and paths["report"].exists()
    unreadable = bool(csv_error or manifest_error or warnings_error)
    return {
        "paths": paths,
        "rows": rows,
        "manifest": manifest,
        "warnings": warnings,
        "report_text": report_text,
        "files_present": files_present,
        "unreadable": unreadable,
        "error_message": labels(csv_error, manifest_error, warnings_error),
    }


def list_config_value(config: dict[str, Any], *keys: str) -> list[str]:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            return []
        current = current.get(key)
    if not isinstance(current, list):
        return []
    return [str(item) for item in current]


def nested_config_value(config: dict[str, Any], *keys: str) -> Any:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_config_state(path: Path) -> dict[str, Any]:
    config, error = read_json(path)
    exists = path.exists()
    loaded = exists and not error and bool(config)
    logging_fields = list_config_value(config, "logging", "required_fields") if loaded else []
    kill_conditions = list_config_value(config, "kill_switch", "conditions") if loaded else []
    missing_logging_fields = [field for field in REQUIRED_LOGGING_FIELDS if field not in logging_fields]
    missing_kill_conditions = [
        condition for condition in REQUIRED_KILL_SWITCH_CONDITIONS if condition not in kill_conditions
    ]
    spread_threshold_note = str(
        nested_config_value(config, "spread_and_session_controls", "spread_threshold_note") or ""
    )
    max_spread_points = nested_config_value(config, "spread_and_session_controls", "max_spread_points")
    max_spread_points_value = safe_float(max_spread_points)
    spread_policy_status = str(
        nested_config_value(config, "spread_and_session_controls", "spread_policy_status") or ""
    )
    spread_policy_action_when_exceeded = str(
        nested_config_value(config, "spread_and_session_controls", "spread_policy_action_when_exceeded") or ""
    )
    spread_policy_action_when_missing = str(
        nested_config_value(config, "spread_and_session_controls", "spread_policy_action_when_missing") or ""
    )
    numeric_spread_policy = max_spread_points_value is not None
    paper_boundary_ok = bool(
        loaded
        and config.get("paper_only") is True
        and config.get("broker_connection_allowed") is False
        and config.get("order_execution_allowed") is False
        and config.get("real_money_allowed") is False
    )
    contract_ok = bool(logging_fields and kill_conditions and not missing_logging_fields and not missing_kill_conditions)
    return {
        "path": path,
        "config": config if loaded else {},
        "error": error,
        "exists": exists,
        "loaded": loaded,
        "config_role": str(config.get("config_role") or "") if loaded else "",
        "candidate_id": str(config.get("candidate_id") or "") if loaded else "",
        "paper_boundary_ok": paper_boundary_ok,
        "paper_only": bool(loaded and config.get("paper_only") is True),
        "broker_connection_allowed_false": bool(loaded and config.get("broker_connection_allowed") is False),
        "order_execution_allowed_false": bool(loaded and config.get("order_execution_allowed") is False),
        "real_money_allowed_false": bool(loaded and config.get("real_money_allowed") is False),
        "logging_fields": logging_fields,
        "missing_logging_fields": missing_logging_fields,
        "kill_conditions": kill_conditions,
        "missing_kill_conditions": missing_kill_conditions,
        "spread_threshold_note": spread_threshold_note,
        "max_spread_points": max_spread_points,
        "max_spread_points_value": max_spread_points_value,
        "spread_policy_status": spread_policy_status,
        "spread_policy_action_when_exceeded": spread_policy_action_when_exceeded,
        "spread_policy_action_when_missing": spread_policy_action_when_missing,
        "numeric_spread_policy": numeric_spread_policy,
        "contract_ok": contract_ok,
    }


def inspect_sqlite_schema(db_path: Path, table_name: str) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "db_exists": False,
            "table_exists": False,
            "columns": set(),
            "error": "",
        }
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            table_row = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            if not table_row:
                return {
                    "db_exists": True,
                    "table_exists": False,
                    "columns": set(),
                    "error": "",
                }
            columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})")}
            return {
                "db_exists": True,
                "table_exists": True,
                "columns": columns,
                "error": "",
            }
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return {
            "db_exists": True,
            "table_exists": False,
            "columns": set(),
            "error": str(exc),
        }


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def threshold_container(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("features", "feature_thresholds", "thresholds"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return data


def bucket_has_boundaries(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return any(item is not None and item != "" for item in value.values())
    if isinstance(value, list):
        return bool(value)
    return True


def load_threshold_state(path: Path) -> dict[str, Any]:
    data, error = read_json(path)
    exists = path.exists()
    loaded = exists and not error and bool(data)
    missing_features: list[str] = []
    missing_buckets: list[str] = []
    valid = False
    if loaded:
        features = threshold_container(data)
        for feature, bucket in REQUIRED_THRESHOLD_BUCKETS.items():
            feature_entry = features.get(feature)
            if not isinstance(feature_entry, dict):
                missing_features.append(feature)
                continue
            bucket_entry = feature_entry.get(bucket)
            if not bucket_has_boundaries(bucket_entry):
                missing_buckets.append(f"{feature}:{bucket}")
        valid = bool(
            data.get("schema_version") is not None
            and data.get("candidate_id")
            and not missing_features
            and not missing_buckets
        )
    return {
        "path": path,
        "data": data if loaded else {},
        "error": error,
        "exists": exists,
        "loaded": loaded,
        "valid": valid,
        "schema_version_present": bool(loaded and data.get("schema_version") is not None),
        "candidate_id_present": bool(loaded and data.get("candidate_id")),
        "missing_features": missing_features,
        "missing_buckets": missing_buckets,
    }


def artifact_gate_status(bundle: dict[str, Any]) -> str:
    if not bundle["files_present"]:
        return "blocked_missing_required_artifact"
    if bundle["unreadable"]:
        return "blocked_unreadable_input"
    return "ready_for_paper_signal_logger_implementation"


def add_artifact_gate(
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    *,
    bundle: dict[str, Any],
    readiness_area: str,
    source_path: Path,
    evidence_label: str,
) -> None:
    status = artifact_gate_status(bundle)
    row = base_row(args, readiness_area)
    row.update(
        {
            "source_path": source_path,
            "artifact_status": "available" if status == "ready_for_paper_signal_logger_implementation" else "missing",
            "readiness_status": status,
            "evidence_label": evidence_label,
            "observed_value": bool_text(status == "ready_for_paper_signal_logger_implementation"),
        }
    )
    if status != "ready_for_paper_signal_logger_implementation":
        warning_code = f"{readiness_area}_blocked"
        row.update(
            {
                "artifact_status": "unreadable" if status == "blocked_unreadable_input" else "missing",
                "warning_code": warning_code,
                "blocking_warning": True,
                "required_next_artifact": source_path,
            }
        )
        add_warning(
            warnings,
            warning_code=warning_code,
            message=f"{readiness_area} is missing or unreadable.",
            readiness_area=readiness_area,
            source_path=source_path,
            blocking_warning=True,
        )
    rows.append(row)


def build_readiness_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    demo_spec = load_artifact_bundle(
        Path(args.demo_strategy_spec_dir),
        csv_name=SPEC_CSV,
        manifest_name=SPEC_MANIFEST,
        report_name=SPEC_REPORT,
        warnings_name=SPEC_WARNINGS,
    )
    command_plan = load_artifact_bundle(
        Path(args.paper_runner_command_plan_dir),
        csv_name=PLAN_CSV,
        manifest_name=PLAN_MANIFEST,
        report_name=PLAN_REPORT,
        warnings_name=PLAN_WARNINGS,
    )
    config = load_config_state(Path(args.demo_strategy_config))
    schema = inspect_sqlite_schema(Path(args.feature_source_db), str(args.feature_source_table))
    threshold = load_threshold_state(Path(args.tercile_thresholds_json))

    add_artifact_gate(
        args,
        rows,
        warnings,
        bundle=demo_spec,
        readiness_area="demo_strategy_spec_gate",
        source_path=Path(args.demo_strategy_spec_dir),
        evidence_label="paper_only_boundary_confirmed",
    )
    add_artifact_gate(
        args,
        rows,
        warnings,
        bundle=command_plan,
        readiness_area="paper_runner_command_plan_gate",
        source_path=Path(args.paper_runner_command_plan_dir),
        evidence_label="paper_signal_logger_required",
    )

    config_row = base_row(args, "canonical_config_gate")
    config_row.update(
        {
            "source_path": config["path"],
            "observed_value": bool_text(bool(config["loaded"])),
            "evidence_label": "canonical_demo_strategy_config_loaded",
            "required_value": "config_role=paper_demo_strategy_config",
        }
    )
    if not config["exists"]:
        config_row.update(
            {
                "artifact_status": "missing",
                "readiness_status": "blocked_missing_required_artifact",
                "warning_code": "canonical_demo_strategy_config_missing",
                "blocking_warning": True,
                "required_next_artifact": config["path"],
            }
        )
        add_warning(
            warnings,
            warning_code="canonical_demo_strategy_config_missing",
            message="Canonical demo strategy config is missing.",
            readiness_area="canonical_config_gate",
            source_path=config["path"],
            blocking_warning=True,
        )
    elif not config["loaded"]:
        config_row.update(
            {
                "artifact_status": "unreadable",
                "readiness_status": "blocked_unreadable_input",
                "warning_code": "canonical_demo_strategy_config_unreadable",
                "blocking_warning": True,
                "required_next_artifact": config["path"],
            }
        )
        add_warning(
            warnings,
            warning_code="canonical_demo_strategy_config_unreadable",
            message=f"Canonical demo strategy config is unreadable: {config['error']}",
            readiness_area="canonical_config_gate",
            source_path=config["path"],
            blocking_warning=True,
        )
    elif config["config_role"] != "paper_demo_strategy_config":
        config_row.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_config",
                "warning_code": "canonical_demo_strategy_config_role_invalid",
                "blocking_warning": True,
                "required_next_artifact": "valid_paper_demo_strategy_config",
            }
        )
        add_warning(
            warnings,
            warning_code="canonical_demo_strategy_config_role_invalid",
            message="Canonical demo strategy config has an unexpected config_role.",
            readiness_area="canonical_config_gate",
            source_path=config["path"],
            blocking_warning=True,
        )
    rows.append(config_row)

    paper_boundary = base_row(args, "paper_boundary_gate")
    paper_boundary.update(
        {
            "source_path": config["path"],
            "required_value": "paper_only=true;broker_connection_allowed=false;order_execution_allowed=false;real_money_allowed=false",
            "observed_value": labels(
                f"paper_only={bool_text(config['paper_only'])}",
                f"broker_connection_allowed_false={bool_text(config['broker_connection_allowed_false'])}",
                f"order_execution_allowed_false={bool_text(config['order_execution_allowed_false'])}",
                f"real_money_allowed_false={bool_text(config['real_money_allowed_false'])}",
            ),
            "evidence_label": "paper_only_boundary_confirmed",
            "caveat": "no_broker_connection_performed;no_order_execution_performed;no_trading_decision_made",
        }
    )
    spec_manifest = demo_spec["manifest"]
    spec_boundary_ok = bool(
        demo_spec["files_present"]
        and not demo_spec["unreadable"]
        and spec_manifest.get("paper_only_specification") is True
        and spec_manifest.get("no_broker_connection_performed") is True
        and spec_manifest.get("no_order_execution_performed") is True
        and spec_manifest.get("no_trading_decision_performed") is True
    )
    if not (config["paper_boundary_ok"] and spec_boundary_ok):
        paper_boundary.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_config",
                "warning_code": "paper_boundary_not_confirmed",
                "blocking_warning": True,
                "required_next_artifact": "valid_paper_only_demo_strategy_spec_and_config",
            }
        )
        add_warning(
            warnings,
            warning_code="paper_boundary_not_confirmed",
            message="Paper-only boundary is not confirmed by both demo spec and canonical config.",
            readiness_area="paper_boundary_gate",
            source_path=config["path"],
            blocking_warning=True,
        )
    rows.append(paper_boundary)

    db_gate = base_row(args, "feature_source_db_gate")
    db_gate.update(
        {
            "source_path": args.feature_source_db,
            "source_table": args.feature_source_table,
            "observed_value": bool_text(bool(schema["db_exists"])),
            "evidence_label": "feature_source_db_available",
            "caveat": "no_db_mutation_performed",
        }
    )
    if schema["error"]:
        db_gate.update(
            {
                "artifact_status": "unreadable",
                "readiness_status": "blocked_unreadable_input",
                "warning_code": "feature_source_db_unreadable",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            warning_code="feature_source_db_unreadable",
            message=f"Feature source DB schema could not be inspected: {schema['error']}",
            readiness_area="feature_source_db_gate",
            source_path=args.feature_source_db,
            blocking_warning=True,
        )
    elif not schema["db_exists"]:
        db_gate.update(
            {
                "artifact_status": "missing",
                "readiness_status": "blocked_missing_required_artifact",
                "warning_code": "feature_source_db_missing",
                "blocking_warning": True,
                "required_next_artifact": args.feature_source_db,
            }
        )
        add_warning(
            warnings,
            warning_code="feature_source_db_missing",
            message="Feature source DB is missing.",
            readiness_area="feature_source_db_gate",
            source_path=args.feature_source_db,
            blocking_warning=True,
        )
    rows.append(db_gate)

    table_name = str(args.feature_source_table)
    table_allowlisted = table_name in ALLOWLISTED_FEATURE_TABLES
    leakage_blocked = table_name in BLOCKED_SIGNAL_INPUT_TABLES
    table_gate = base_row(args, "feature_source_table_gate")
    table_gate.update(
        {
            "source_path": args.feature_source_db,
            "source_table": table_name,
            "required_value": ",".join(sorted(ALLOWLISTED_FEATURE_TABLES)),
            "observed_value": table_name,
            "evidence_label": "feature_source_table_allowlisted" if table_allowlisted else "",
        }
    )
    if leakage_blocked:
        table_gate.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_leakage_risk",
                "evidence_label": "ml_dataset_blocked_for_signal_input",
                "warning_code": "feature_source_table_leakage_risk",
                "blocking_warning": True,
                "required_next_artifact": "use_price_features_or_market_features",
            }
        )
        add_warning(
            warnings,
            warning_code="feature_source_table_leakage_risk",
            message="ml_dataset is blocked as a primary paper signal input because it contains future/target columns.",
            readiness_area="feature_source_table_gate",
            source_path=args.feature_source_db,
            blocking_warning=True,
        )
    elif not table_allowlisted:
        table_gate.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_config",
                "warning_code": "feature_source_table_not_allowlisted",
                "blocking_warning": True,
                "required_next_artifact": "allowlisted_feature_source_table",
            }
        )
        add_warning(
            warnings,
            warning_code="feature_source_table_not_allowlisted",
            message="Feature source table is not allowlisted for paper signal input.",
            readiness_area="feature_source_table_gate",
            source_path=args.feature_source_db,
            blocking_warning=True,
        )
    elif not schema["table_exists"] and schema["db_exists"] and not schema["error"]:
        table_gate.update(
            {
                "artifact_status": "missing",
                "readiness_status": "blocked_missing_required_artifact",
                "warning_code": "feature_source_table_missing",
                "blocking_warning": True,
                "required_next_artifact": table_name,
            }
        )
        add_warning(
            warnings,
            warning_code="feature_source_table_missing",
            message="Allowlisted feature source table is missing from the DB.",
            readiness_area="feature_source_table_gate",
            source_path=args.feature_source_db,
            blocking_warning=True,
        )
    rows.append(table_gate)

    leakage_gate = base_row(args, "leakage_surface_gate")
    leakage_gate.update(
        {
            "source_path": args.feature_source_db,
            "source_table": table_name,
            "required_value": "non_target_feature_table",
            "observed_value": "blocked" if leakage_blocked else "allowlisted_non_target_source",
            "evidence_label": "ml_dataset_blocked_for_signal_input" if leakage_blocked else "feature_source_table_allowlisted",
            "caveat": "no_db_mutation_performed;no_trading_decision_made",
        }
    )
    if leakage_blocked:
        leakage_gate.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_leakage_risk",
                "warning_code": "leakage_surface_blocked",
                "blocking_warning": True,
                "required_next_artifact": "use_price_features_or_market_features",
            }
        )
    rows.append(leakage_gate)

    missing_required_columns = [
        column for column in REQUIRED_SOURCE_COLUMNS if column not in set(schema["columns"])
    ]
    available_optional_columns = [
        column for column in OPTIONAL_SOURCE_COLUMNS if column in set(schema["columns"])
    ]
    columns_gate = base_row(args, "required_columns_gate")
    columns_gate.update(
        {
            "source_path": args.feature_source_db,
            "source_table": table_name,
            "source_column": ";".join(REQUIRED_SOURCE_COLUMNS),
            "required_value": "all_required_columns_present",
            "observed_value": "missing=" + ",".join(missing_required_columns) if missing_required_columns else "all_present",
            "evidence_label": "required_columns_available" if not missing_required_columns else "",
            "caveat": labels("optional_columns=" + ",".join(available_optional_columns) if available_optional_columns else ""),
        }
    )
    if missing_required_columns:
        columns_gate.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_missing_required_column",
                "warning_code": "feature_source_required_columns_missing",
                "blocking_warning": True,
                "required_next_artifact": "feature_source_with_required_columns",
            }
        )
        add_warning(
            warnings,
            warning_code="feature_source_required_columns_missing",
            message=f"Feature source table is missing required columns: {', '.join(missing_required_columns)}",
            readiness_area="required_columns_gate",
            source_path=args.feature_source_db,
            blocking_warning=True,
        )
    rows.append(columns_gate)

    threshold_gate = base_row(args, "numeric_tercile_threshold_artifact_gate")
    threshold_gate.update(
        {
            "source_path": args.tercile_thresholds_json,
            "required_value": "fixed_candidate_numeric_tercile_thresholds.json",
            "observed_value": bool_text(bool(threshold["exists"])),
            "evidence_label": "numeric_tercile_threshold_artifact_available"
            if threshold["exists"]
            else "numeric_tercile_threshold_artifact_missing",
            "caveat": "numeric_tercile_threshold_artifact_required",
            "required_next_artifact": "fixed_candidate_numeric_tercile_thresholds.json",
        }
    )
    if not threshold["exists"]:
        threshold_gate.update(
            {
                "artifact_status": "missing",
                "readiness_status": "blocked_missing_threshold_artifact",
                "warning_code": "numeric_tercile_threshold_artifact_missing",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            warning_code="numeric_tercile_threshold_artifact_missing",
            message="Numeric tercile threshold artifact is required before paper signal logger implementation.",
            readiness_area="numeric_tercile_threshold_artifact_gate",
            source_path=args.tercile_thresholds_json,
            blocking_warning=True,
        )
    elif not threshold["loaded"]:
        threshold_gate.update(
            {
                "artifact_status": "unreadable",
                "readiness_status": "blocked_unreadable_input",
                "warning_code": "numeric_tercile_threshold_artifact_unreadable",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            warning_code="numeric_tercile_threshold_artifact_unreadable",
            message=f"Numeric tercile threshold artifact is unreadable: {threshold['error']}",
            readiness_area="numeric_tercile_threshold_artifact_gate",
            source_path=args.tercile_thresholds_json,
            blocking_warning=True,
        )
    rows.append(threshold_gate)

    threshold_schema = base_row(args, "threshold_schema_gate")
    threshold_schema.update(
        {
            "source_path": args.tercile_thresholds_json,
            "required_value": "schema_version;candidate_id;required_feature_buckets",
            "observed_value": labels(
                f"schema_version_present={bool_text(threshold['schema_version_present'])}",
                f"candidate_id_present={bool_text(threshold['candidate_id_present'])}",
                "missing_features=" + ",".join(threshold["missing_features"]) if threshold["missing_features"] else "",
                "missing_buckets=" + ",".join(threshold["missing_buckets"]) if threshold["missing_buckets"] else "",
            ),
            "evidence_label": "threshold_schema_valid" if threshold["valid"] else "",
            "required_next_artifact": "fixed_candidate_numeric_tercile_thresholds.json",
        }
    )
    if threshold["exists"] and threshold["loaded"] and not threshold["valid"]:
        threshold_schema.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_config",
                "evidence_label": "threshold_schema_missing_required_feature"
                if threshold["missing_features"]
                else "",
                "warning_code": "numeric_tercile_threshold_schema_invalid",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            warning_code="numeric_tercile_threshold_schema_invalid",
            message="Numeric tercile threshold artifact is missing schema fields, candidate_id, required features, or required bucket boundaries.",
            readiness_area="threshold_schema_gate",
            source_path=args.tercile_thresholds_json,
            blocking_warning=True,
        )
    elif not threshold["exists"]:
        threshold_schema.update(
            {
                "artifact_status": "missing",
                "readiness_status": "blocked_missing_threshold_artifact",
                "evidence_label": "numeric_tercile_threshold_artifact_required",
                "warning_code": "numeric_tercile_threshold_artifact_missing",
                "blocking_warning": True,
            }
        )
    elif threshold["exists"] and not threshold["loaded"]:
        threshold_schema.update(
            {
                "artifact_status": "unreadable",
                "readiness_status": "blocked_unreadable_input",
                "warning_code": "numeric_tercile_threshold_artifact_unreadable",
                "blocking_warning": True,
            }
        )
    rows.append(threshold_schema)

    state_gate = base_row(args, "state_file_plan_gate")
    state_path = Path(args.state_json)
    state_gate.update(
        {
            "source_path": state_path,
            "required_value": "state_json_path_provided",
            "observed_value": str(state_path),
            "evidence_label": "state_json_planned_not_created",
            "caveat": "state_json_planned_not_created;no_db_mutation_performed",
        }
    )
    if not str(state_path):
        state_gate.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_config",
                "warning_code": "state_json_path_missing",
                "blocking_warning": True,
            }
        )
        add_warning(
            warnings,
            warning_code="state_json_path_missing",
            message="State JSON path must be provided for one-open-paper-trade planning.",
            readiness_area="state_file_plan_gate",
            source_path="",
            blocking_warning=True,
        )
    rows.append(state_gate)

    logging_gate = base_row(args, "logging_contract_gate")
    logging_gate.update(
        {
            "source_path": config["path"],
            "required_value": ";".join(REQUIRED_LOGGING_FIELDS),
            "observed_value": ";".join(config["logging_fields"]),
            "evidence_label": "logging_contract_available" if not config["missing_logging_fields"] else "",
            "caveat": "paper_signal_log_csv;events_jsonl;state_json;state_history;report;warnings;manifest",
        }
    )
    if config["missing_logging_fields"]:
        logging_gate.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_config",
                "warning_code": "logging_contract_missing_required_fields",
                "blocking_warning": True,
                "required_next_artifact": "complete_logging_contract_config",
            }
        )
        add_warning(
            warnings,
            warning_code="logging_contract_missing_required_fields",
            message=f"Logging contract is missing fields: {', '.join(config['missing_logging_fields'])}",
            readiness_area="logging_contract_gate",
            source_path=config["path"],
            blocking_warning=True,
        )
    rows.append(logging_gate)

    kill_gate = base_row(args, "kill_switch_contract_gate")
    kill_gate.update(
        {
            "source_path": config["path"],
            "required_value": ";".join(REQUIRED_KILL_SWITCH_CONDITIONS),
            "observed_value": ";".join(config["kill_conditions"]),
            "evidence_label": "kill_switch_contract_available" if not config["missing_kill_conditions"] else "",
        }
    )
    if config["missing_kill_conditions"]:
        kill_gate.update(
            {
                "artifact_status": "blocked",
                "readiness_status": "blocked_by_config",
                "warning_code": "kill_switch_contract_missing_required_conditions",
                "blocking_warning": True,
                "required_next_artifact": "complete_kill_switch_contract_config",
            }
        )
        add_warning(
            warnings,
            warning_code="kill_switch_contract_missing_required_conditions",
            message=f"Kill-switch contract is missing conditions: {', '.join(config['missing_kill_conditions'])}",
            readiness_area="kill_switch_contract_gate",
            source_path=config["path"],
            blocking_warning=True,
        )
    rows.append(kill_gate)

    spread_gate = base_row(args, "spread_policy_gate")
    spread_gate.update(
        {
            "artifact_status": "available_with_caveat" if not config["numeric_spread_policy"] else "available",
            "readiness_status": "ready_with_caveat_for_paper_signal_logger_implementation"
            if not config["numeric_spread_policy"]
            else "ready_for_paper_signal_logger_implementation",
            "source_path": config["path"],
            "required_value": "explicit_or_skip-safe_spread_policy",
            "observed_value": labels(
                f"spread_threshold_note={config['spread_threshold_note']}",
                f"max_spread_points={config['max_spread_points']}",
                f"spread_policy_status={config['spread_policy_status']}",
                f"action_when_exceeded={config['spread_policy_action_when_exceeded']}",
                f"action_when_missing={config['spread_policy_action_when_missing']}",
            ),
            "evidence_label": "spread_threshold_not_numeric_yet"
            if not config["numeric_spread_policy"]
            else "numeric_spread_policy_configured",
            "caveat": "future_logger_should_skip_signals_until_numeric_threshold_or_explicit_spread_policy_is_configured"
            if not config["numeric_spread_policy"]
            else "",
        }
    )
    if config["loaded"] and not config["numeric_spread_policy"]:
        spread_gate["warning_code"] = "spread_threshold_not_numeric_yet"
        add_warning(
            warnings,
            warning_code="spread_threshold_not_numeric_yet",
            message="Spread threshold is not numeric yet; future logger should skip new signals until a numeric threshold or explicit spread policy is configured.",
            readiness_area="spread_policy_gate",
            source_path=config["path"],
            blocking_warning=False,
        )
    rows.append(spread_gate)

    timeout_gate = base_row(args, "timeout_tracking_plan_gate")
    timeout_gate.update(
        {
            "artifact_status": "available_with_caveat",
            "readiness_status": "ready_with_caveat_for_paper_signal_logger_implementation",
            "source_path": config["path"],
            "required_value": "stateful_h10_tracking",
            "observed_value": "target_horizon=10",
            "evidence_label": "timeout_tracking_should_be_stateful",
            "caveat": "future_logger_must_track_h10_with_state_and_new_local_bars_only",
        }
    )
    rows.append(timeout_gate)

    blocking_statuses = {
        "blocked_missing_required_artifact",
        "blocked_missing_required_column",
        "blocked_missing_threshold_artifact",
        "blocked_unreadable_input",
        "blocked_by_leakage_risk",
        "blocked_by_config",
    }
    blocked_rows = [row for row in rows if row["readiness_status"] in blocking_statuses]
    caveat_rows = [
        row for row in rows if row["readiness_status"] == "ready_with_caveat_for_paper_signal_logger_implementation"
    ]

    readiness = base_row(args, "future_logger_implementation_readiness")
    if blocked_rows:
        first_block = str(blocked_rows[0]["readiness_status"])
        readiness.update(
            {
                "artifact_status": "blocked",
                "readiness_status": first_block,
                "evidence_label": "numeric_tercile_threshold_artifact_required"
                if any(row["readiness_status"] == "blocked_missing_threshold_artifact" for row in blocked_rows)
                else "paper_signal_logger_readiness_blocked",
                "required_next_artifact": "fixed_candidate_numeric_tercile_thresholds.json"
                if any(row["readiness_status"] == "blocked_missing_threshold_artifact" for row in blocked_rows)
                else "resolve_blocking_readiness_items",
                "warning_code": "future_logger_implementation_readiness_blocked",
                "blocking_warning": True,
            }
        )
    elif caveat_rows:
        readiness.update(
            {
                "artifact_status": "available_with_caveat",
                "readiness_status": "ready_with_caveat_for_paper_signal_logger_implementation",
                "evidence_label": "paper_signal_logger_readiness_available_with_caveat",
                "required_next_artifact": "implement_run_fixed_candidate_paper_signal_logger.py",
            }
        )
    else:
        readiness.update(
            {
                "evidence_label": "paper_signal_logger_readiness_available",
                "required_next_artifact": "implement_run_fixed_candidate_paper_signal_logger.py",
            }
        )
    rows.append(readiness)

    next_required = base_row(args, "next_required_artifact")
    if threshold["exists"] and threshold["valid"] and not blocked_rows:
        next_status = "ready_with_caveat_for_paper_signal_logger_implementation" if caveat_rows else "ready_for_paper_signal_logger_implementation"
        next_artifact = "implement_run_fixed_candidate_paper_signal_logger.py"
    elif not threshold["exists"]:
        next_status = "blocked_missing_threshold_artifact"
        next_artifact = "fixed_candidate_numeric_tercile_thresholds.json"
    elif threshold["exists"] and not threshold["valid"]:
        next_status = "blocked_by_config" if threshold["loaded"] else "blocked_unreadable_input"
        next_artifact = "valid_fixed_candidate_numeric_tercile_thresholds.json"
    else:
        next_status = str(blocked_rows[0]["readiness_status"]) if blocked_rows else "ready_with_caveat_for_paper_signal_logger_implementation"
        next_artifact = "resolve_blocking_readiness_items"
    next_required.update(
        {
            "artifact_status": "available_with_caveat" if next_status.startswith("ready_with") else ("blocked" if next_status.startswith("blocked") else "available"),
            "readiness_status": next_status,
            "evidence_label": "numeric_tercile_threshold_artifact_required"
            if next_artifact.endswith("thresholds.json")
            else "paper_signal_logger_required",
            "required_next_artifact": next_artifact,
        }
    )
    rows.append(next_required)

    metadata = {
        "demo_spec": demo_spec,
        "command_plan": command_plan,
        "config": config,
        "schema": schema,
        "threshold": threshold,
        "feature_source_table_allowlisted": table_allowlisted,
        "required_columns_available": not missing_required_columns,
        "missing_required_columns": missing_required_columns,
        "available_optional_columns": available_optional_columns,
        "paper_only_boundary_confirmed": bool(config["paper_boundary_ok"] and spec_boundary_ok),
        "blocked_rows": blocked_rows,
        "caveat_rows": caveat_rows,
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
    status_counts = count_rows(rows, "readiness_status")
    config = metadata["config"]
    schema = metadata["schema"]
    threshold = metadata["threshold"]
    next_row = next((row for row in rows if row["readiness_area"] == "next_required_artifact"), {})
    lines = [
        "# Fixed Candidate Paper Signal Logger Readiness",
        "",
        "Readiness-only artifact. This does not implement or run a paper signal logger.",
        "Paper/local-only review. No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation was performed.",
        "No trading decision was made.",
        "",
        "## Inputs",
        "",
        f"- demo_strategy_spec_dir: `{args.demo_strategy_spec_dir}`",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- paper_runner_command_plan_dir: `{args.paper_runner_command_plan_dir}`",
        f"- feature_source_db: `{args.feature_source_db}`",
        f"- feature_source_table: `{args.feature_source_table}`",
        f"- tercile_thresholds_json: `{args.tercile_thresholds_json}`",
        f"- state_json: `{args.state_json}`",
        "",
        "## Recommended Local Source Table",
        "",
        "`price_features` is the default recommended source. `market_features` is also allowlisted. `ml_dataset` is blocked for primary signal input because it contains future/target columns.",
        "",
        "## Feature Availability Summary",
        "",
        f"- feature_source_db_exists: `{bool_text(bool(schema['db_exists']))}`",
        f"- feature_source_table_exists: `{bool_text(bool(schema['table_exists']))}`",
        f"- feature_source_table_allowlisted: `{bool_text(bool(metadata['feature_source_table_allowlisted']))}`",
        f"- required_columns_available: `{bool_text(bool(metadata['required_columns_available']))}`",
        f"- missing_required_columns: `{','.join(metadata['missing_required_columns'])}`",
        f"- available_optional_columns: `{','.join(metadata['available_optional_columns'])}`",
        "",
        "## Leakage Risk Summary",
        "",
        "The readiness packet blocks `ml_dataset` as a primary signal input. Future paper logging should read only non-target feature columns from an allowlisted source.",
        "",
        "## Numeric Tercile Threshold Artifact",
        "",
        f"- threshold_artifact_exists: `{bool_text(bool(threshold['exists']))}`",
        f"- threshold_artifact_valid: `{bool_text(bool(threshold['valid']))}`",
        f"- missing_threshold_features: `{','.join(threshold['missing_features'])}`",
        f"- missing_threshold_buckets: `{','.join(threshold['missing_buckets'])}`",
        "",
        "## Spread Policy Caveat",
        "",
        f"- spread_threshold_note: `{config['spread_threshold_note']}`",
        f"- max_spread_points: `{config['max_spread_points']}`",
        f"- spread_policy_status: `{config['spread_policy_status']}`",
        f"- numeric_spread_policy: `{bool_text(bool(config['numeric_spread_policy']))}`",
        "If the spread threshold is not numeric, the future logger should skip new signals until a numeric threshold or explicit spread policy is configured.",
        "",
        "## Timeout Tracking Plan",
        "",
        "Timeout/h10 tracking should be stateful and based only on new local bars observed after a paper signal is opened.",
        "",
        "## Logging And State Output Recommendation",
        "",
        "Use a signal CSV, events JSONL, state JSON, state history, report, warnings CSV, and manifest. The state JSON path is planned only and was not created.",
        "",
        "## Readiness Summary",
        "",
        f"- readiness_row_count: `{len(rows)}`",
        f"- ready_for_paper_signal_logger_implementation_count: `{status_counts.get('ready_for_paper_signal_logger_implementation', 0)}`",
        f"- ready_with_caveat_for_paper_signal_logger_implementation_count: `{status_counts.get('ready_with_caveat_for_paper_signal_logger_implementation', 0)}`",
        f"- blocked_missing_threshold_artifact_count: `{status_counts.get('blocked_missing_threshold_artifact', 0)}`",
        f"- blocking_warnings_count: `{sum(str(warning.get('blocking_warning')).lower() == 'true' for warning in warnings)}`",
        "",
        "## Exact Next Required Artifact",
        "",
        f"`{next_row.get('required_next_artifact', '')}`",
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
    statuses = count_rows(rows, "readiness_status")
    warning_blockers = sum(1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true")
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "paper_runner_command_plan_dir": str(args.paper_runner_command_plan_dir),
        "feature_source_db": str(args.feature_source_db),
        "feature_source_table": str(args.feature_source_table),
        "tercile_thresholds_json": str(args.tercile_thresholds_json),
        "state_json": str(args.state_json),
        "readiness_row_count": len(rows),
        "ready_for_paper_signal_logger_implementation_count": statuses.get(
            "ready_for_paper_signal_logger_implementation", 0
        ),
        "ready_with_caveat_for_paper_signal_logger_implementation_count": statuses.get(
            "ready_with_caveat_for_paper_signal_logger_implementation", 0
        ),
        "blocked_missing_required_artifact_count": statuses.get("blocked_missing_required_artifact", 0),
        "blocked_missing_required_column_count": statuses.get("blocked_missing_required_column", 0),
        "blocked_missing_threshold_artifact_count": statuses.get("blocked_missing_threshold_artifact", 0),
        "blocked_unreadable_input_count": statuses.get("blocked_unreadable_input", 0),
        "blocked_by_leakage_risk_count": statuses.get("blocked_by_leakage_risk", 0),
        "blocked_by_config_count": statuses.get("blocked_by_config", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": warning_blockers,
        "feature_source_db_exists": bool(metadata["schema"]["db_exists"]),
        "feature_source_table_exists": bool(metadata["schema"]["table_exists"]),
        "feature_source_table_allowlisted": bool(metadata["feature_source_table_allowlisted"]),
        "required_columns_available": bool(metadata["required_columns_available"]),
        "tercile_thresholds_json_exists": bool(metadata["threshold"]["exists"]),
        "tercile_thresholds_json_valid": bool(metadata["threshold"]["valid"]),
        "paper_only_boundary_confirmed": bool(metadata["paper_only_boundary_confirmed"]),
        "numeric_spread_policy_configured": bool(metadata["config"]["numeric_spread_policy"]),
        "max_spread_points": metadata["config"]["max_spread_points"],
        "spread_policy_status": metadata["config"]["spread_policy_status"],
        "no_child_scripts_executed": True,
        "no_paper_runner_executed": True,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
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
    rows, warnings, metadata = build_readiness_rows(args)
    write_csv(paths["readiness"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an artifact-only readiness packet for a future fixed-candidate paper signal logger."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument(
        "--paper-runner-command-plan-dir",
        type=Path,
        default=DEFAULT_PAPER_RUNNER_COMMAND_PLAN_DIR,
    )
    parser.add_argument("--feature-source-db", type=Path, default=DEFAULT_FEATURE_SOURCE_DB)
    parser.add_argument("--feature-source-table", default=DEFAULT_FEATURE_SOURCE_TABLE)
    parser.add_argument("--tercile-thresholds-json", type=Path, default=DEFAULT_TERCILE_THRESHOLDS_JSON)
    parser.add_argument("--state-json", type=Path, default=DEFAULT_STATE_JSON)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, sqlite3.Error, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate paper signal logger readiness failed: {exc}")
        return 1
    print("Fixed-candidate paper signal logger readiness complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
