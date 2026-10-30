"""Check live shadow-signal freshness for the fixed GBPUSD candidate.

This module reads existing no-order artifacts and the latest local feature
timestamp through a read-only SQLite connection. It does not import MT5,
query broker/account/symbol state, construct broker payloads, execute orders,
mutate the database, run child scripts, schedule work, or approve demo action.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
CANDIDATE_SYMBOL = "GBPUSD"
CANDIDATE_TIMEFRAME = "M15"
CANDIDATE_DIRECTION = "short"
TIMEFRAME_MINUTES = 15
MAX_AGE_BARS = 10
MAX_AGE_MINUTES = TIMEFRAME_MINUTES * MAX_AGE_BARS
FEATURE_TABLE = "price_features"

DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_live_signal_freshness"
DEFAULT_WOULD_SIGNAL_REVIEW_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_would_signal_review"
    / "gbpusd_short_h10_1_5_off_hours_demo_would_signal_review_live_v1"
)
DEFAULT_BROKER_LOCAL_RECONCILIATION_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_broker_local_state_reconciliation"
    / "gbpusd_short_h10_1_5_off_hours_demo_broker_local_state_reconciliation_real_v1"
)
DEFAULT_FUTURE_REQUEST_READINESS_PLAN_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_future_request_construction_readiness_plan"
    / "gbpusd_short_h10_1_5_off_hours_demo_future_request_construction_readiness_plan_live_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_DEMO_EXECUTION_POLICY = BASE_DIR / "config" / "fixed_candidate_demo_execution_policy.json"
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_live_signal_freshness"

WOULD_SIGNAL_MANIFEST = "fixed_candidate_demo_would_signal_review_manifest.json"
BROKER_LOCAL_RECONCILIATION_MANIFEST = "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json"
FUTURE_REQUEST_READINESS_MANIFEST = "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json"

OUTPUT_MANIFEST = "fixed_candidate_demo_live_signal_freshness_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_live_signal_freshness_report.md"
OUTPUT_STATUS = "fixed_candidate_demo_live_signal_freshness_status.csv"
OUTPUT_TIMING = "fixed_candidate_demo_live_signal_freshness_timing.csv"
OUTPUT_UPSTREAM = "fixed_candidate_demo_live_signal_freshness_upstream_evidence.csv"
OUTPUT_WARNINGS = "fixed_candidate_demo_live_signal_freshness_warnings.csv"
OUTPUT_NO_ORDER = "fixed_candidate_demo_live_signal_freshness_no_order_evidence.csv"

STATUS_FIELDNAMES = [
    "run_id",
    "freshness_status",
    "status_area",
    "observed_value",
    "expected_value",
    "blocking_if_failed",
    "caveat",
]
TIMING_FIELDNAMES = [
    "run_id",
    "signal_time_server",
    "latest_feature_time_server",
    "timeframe_minutes",
    "max_age_bars",
    "max_age_minutes",
    "elapsed_minutes",
    "bars_elapsed",
    "is_fresh",
    "is_stale",
    "future_manual_approval_allowed_now",
    "request_construction_allowed_now",
]
UPSTREAM_FIELDNAMES = [
    "run_id",
    "source_area",
    "source_path",
    "source_status",
    "observed_value",
    "expected_value",
    "evidence_label",
    "blocking_if_failed",
]
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]
NO_ORDER_FIELDNAMES = [
    "run_id",
    "no_mt5_import_performed",
    "no_mt5_connection_performed",
    "no_broker_api_query_performed",
    "no_positions_get_called",
    "no_orders_get_called",
    "no_history_orders_get_called",
    "no_history_deals_get_called",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_broker_payload_constructed",
    "no_executable_order_object_constructed",
    "no_db_mutation_performed",
    "no_child_scripts_executed",
    "no_scheduler_added",
    "no_loop_added",
    "no_background_task_added",
    "no_trading_decision_performed",
    "no_demo_broker_approval_performed",
    "evidence_label",
    "caveat",
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


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(value, dict):
        return {}, "JSON root must be an object"
    return value, ""


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


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


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [warning for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"]


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "status": output_dir / OUTPUT_STATUS,
        "timing": output_dir / OUTPUT_TIMING,
        "upstream": output_dir / OUTPUT_UPSTREAM,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "no_order": output_dir / OUTPUT_NO_ORDER,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def parse_time_server(value: Any) -> tuple[datetime | None, str]:
    if value in ("", None):
        return None, "missing"
    text = str(value).strip()
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc), ""
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc), ""
        except ValueError:
            pass
    return None, f"unparseable timestamp: {text}"


def validate_canonical_registry(registry: dict[str, Any]) -> bool:
    horizon = registry.get("horizon_bars")
    max_open = registry.get("max_open_positions")
    return (
        registry.get("candidate_id") == CANDIDATE_ID
        and registry.get("symbol") == CANDIDATE_SYMBOL
        and registry.get("timeframe") == CANDIDATE_TIMEFRAME
        and registry.get("direction") == CANDIDATE_DIRECTION
        and registry.get("spread_unit") == "broker_points"
        and safe_float(registry.get("max_spread_points")) == 15.0
        and (max_open in ("", None) or safe_float(max_open) == 1.0)
        and (horizon in ("", None) or safe_float(horizon) == float(MAX_AGE_BARS))
    )


def validate_demo_policy(policy: dict[str, Any]) -> bool:
    boundaries = policy.get("safety_boundaries")
    if not isinstance(boundaries, dict):
        return False
    return (
        policy.get("candidate_id") == CANDIDATE_ID
        and policy.get("symbol") == CANDIDATE_SYMBOL
        and policy.get("timeframe") == CANDIDATE_TIMEFRAME
        and policy.get("direction") == CANDIDATE_DIRECTION
        and policy.get("spread_unit") == "broker_points"
        and safe_float(policy.get("max_spread_points")) == 15.0
        and safe_float(policy.get("max_open_positions")) == 1.0
        and boundaries.get("real_money_allowed") is False
        and boundaries.get("order_execution_allowed") is False
        and boundaries.get("order_request_construction_allowed") is False
        and boundaries.get("order_check_allowed") is False
        and boundaries.get("order_calc_allowed") is False
        and boundaries.get("manual_approval_required_before_any_future_demo_order") is True
    )


def no_order_flags_ok(manifest: dict[str, Any]) -> bool:
    for flag in ("no_order_execution_performed", "no_order_request_constructed"):
        if flag in manifest and manifest.get(flag) is not True:
            return False
    return True


def validate_would_signal_review(manifest: dict[str, Any]) -> tuple[bool, str]:
    alignment_status = str(manifest.get("live_alignment_status") or "")
    alignment_ok = not alignment_status or alignment_status == "live_data_aligned_with_mt5_latest_bar"
    checks = (
        manifest.get("review_status") == "would_signal_review_available_no_order",
        manifest.get("source_nature") == "live_data_shadow_signal",
        manifest.get("shadow_status") == "shadow_signal_detected",
        manifest.get("manual_review_required") is True,
        manifest.get("actionable_signal") is False,
        manifest.get("order_execution_allowed") is False,
        manifest.get("order_request_construction_allowed") is False,
        no_order_flags_ok(manifest),
        alignment_ok,
    )
    if not alignment_ok:
        return False, "blocked_upstream_live_alignment_status"
    return (all(checks), "" if all(checks) else "blocked_unacceptable_would_signal_review_status")


def validate_broker_reconciliation(manifest: dict[str, Any]) -> tuple[bool, str]:
    checks = (
        manifest.get("reconciliation_status") == "broker_local_reconciliation_clean_no_local_no_broker",
        manifest.get("source_nature") == "live_data_shadow_signal",
        int(manifest.get("broker_position_count_symbol", -1)) == 0,
        int(manifest.get("broker_pending_order_count_symbol", -1)) == 0,
        manifest.get("request_construction_allowed_now") is False,
        no_order_flags_ok(manifest),
    )
    return (all(checks), "" if all(checks) else "blocked_unacceptable_broker_local_reconciliation_status")


def validate_future_request_readiness(manifest: dict[str, Any]) -> tuple[bool, str]:
    if not manifest:
        return True, ""
    false_flags = (
        "request_construction_allowed_now",
        "broker_request_constructed",
        "broker_payload_constructed",
        "order_object_constructed",
    )
    checks = (
        manifest.get("plan_status") == "future_request_construction_readiness_plan_available_no_order",
        manifest.get("source_nature") == "live_data_shadow_signal",
        all(manifest.get(flag) in (False, None) for flag in false_flags),
    )
    return (all(checks), "" if all(checks) else "blocked_unacceptable_future_request_readiness_status")


def inspect_latest_feature_time(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"status": "blocked_db_missing", "columns": [], "latest_time_server": ""}
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (FEATURE_TABLE,),
            ).fetchone()
            if not table_exists:
                return {"status": "blocked_missing_required_table", "columns": [], "latest_time_server": ""}
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({quote_identifier(FEATURE_TABLE)})")]
            if "time_server" not in columns:
                return {"status": "blocked_missing_required_columns", "columns": columns, "latest_time_server": ""}
            filters: list[str] = []
            values: list[Any] = []
            if "symbol" in columns:
                filters.append("symbol = ?")
                values.append(CANDIDATE_SYMBOL)
            if "timeframe" in columns:
                filters.append("timeframe = ?")
                values.append(CANDIDATE_TIMEFRAME)
            where = f" WHERE {' AND '.join(filters)}" if filters else ""
            query = f"SELECT time_server FROM {quote_identifier(FEATURE_TABLE)}{where} ORDER BY time_server DESC LIMIT 1"
            row = connection.execute(query, values).fetchone()
    except sqlite3.Error as exc:
        return {"status": "blocked_freshness_unverifiable", "columns": [], "latest_time_server": "", "error": str(exc)}
    if row is None:
        return {"status": "blocked_freshness_unverifiable", "columns": columns, "latest_time_server": "", "error": "no feature rows found"}
    return {"status": "ok", "columns": columns, "latest_time_server": row[0]}


def load_inputs(args: argparse.Namespace, warnings: list[dict[str, Any]]) -> dict[str, Any]:
    would_path = Path(args.would_signal_review_dir) / WOULD_SIGNAL_MANIFEST
    recon_path = Path(args.broker_local_reconciliation_dir) / BROKER_LOCAL_RECONCILIATION_MANIFEST
    future_path = Path(args.future_request_readiness_plan_dir) / FUTURE_REQUEST_READINESS_MANIFEST
    paths = {
        "registry": Path(args.canonical_registry),
        "policy": Path(args.demo_execution_policy),
        "would_signal": would_path,
        "broker_reconciliation": recon_path,
        "future_request_readiness": future_path,
    }
    registry, registry_error = read_json(paths["registry"])
    policy, policy_error = read_json(paths["policy"])
    would_signal, would_error = read_json(would_path)
    broker_reconciliation, recon_error = read_json(recon_path)
    future_request, future_error = ({}, "missing")
    if future_path.exists():
        future_request, future_error = read_json(future_path)

    for name, error in (
        ("canonical_registry", registry_error),
        ("demo_execution_policy", policy_error),
        ("would_signal_review", would_error),
        ("broker_local_reconciliation", recon_error),
    ):
        if error:
            source = paths["registry"] if name == "canonical_registry" else paths["policy"] if name == "demo_execution_policy" else would_path if name == "would_signal_review" else recon_path
            warnings.append(warning_row(run_id=args.run_id, warning_code=f"{name}_unreadable", message=error, source=source, blocking_warning=True))
    if future_path.exists() and future_error:
        warnings.append(warning_row(run_id=args.run_id, warning_code="future_request_readiness_unreadable", message=future_error, source=future_path, blocking_warning=True))
    return {
        "registry": registry,
        "policy": policy,
        "would_signal": would_signal,
        "broker_reconciliation": broker_reconciliation,
        "future_request": future_request,
        "errors": {
            "registry": registry_error,
            "policy": policy_error,
            "would_signal": would_error,
            "broker_reconciliation": recon_error,
            "future_request": future_error,
        },
        "paths": paths,
    }


def initial_block_status(inputs: dict[str, Any]) -> str | None:
    errors = inputs["errors"]
    if errors["would_signal"] == "missing":
        return "blocked_missing_would_signal_review"
    if errors["broker_reconciliation"] == "missing":
        return "blocked_missing_broker_local_reconciliation"
    if errors["registry"] or not validate_canonical_registry(inputs["registry"]):
        return "blocked_noncanonical_candidate"
    if errors["policy"] or not validate_demo_policy(inputs["policy"]):
        return "blocked_noncanonical_demo_execution_policy"
    would_ok, would_status = validate_would_signal_review(inputs["would_signal"])
    if not would_ok:
        return would_status
    recon_ok, recon_status = validate_broker_reconciliation(inputs["broker_reconciliation"])
    if not recon_ok:
        return recon_status
    future_ok, future_status = validate_future_request_readiness(inputs["future_request"])
    if not future_ok:
        return future_status
    return None


def signal_time_value(would_signal: dict[str, Any]) -> Any:
    return would_signal.get("signal_time_server") or would_signal.get("time_server")


def classify_freshness(signal_time: datetime | None, latest_time: datetime | None, feature_status: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "freshness_status": feature_status if feature_status != "ok" else "blocked_freshness_unverifiable",
        "elapsed_minutes": None,
        "bars_elapsed": None,
        "is_fresh": False,
        "is_stale": False,
    }
    if signal_time is None or latest_time is None:
        result["freshness_status"] = "blocked_freshness_unverifiable"
        return result
    diff_minutes = (latest_time - signal_time).total_seconds() / 60.0
    if diff_minutes < -TIMEFRAME_MINUTES:
        result.update(
            {
                "freshness_status": "blocked_feature_data_inconsistent",
                "elapsed_minutes": diff_minutes,
                "bars_elapsed": 0,
            }
        )
        return result
    if diff_minutes <= 0:
        result.update(
            {
                "freshness_status": "live_signal_freshness_fresh_current_or_latest_signal",
                "elapsed_minutes": 0.0,
                "bars_elapsed": 0,
                "is_fresh": True,
                "is_stale": False,
            }
        )
        return result
    bars_elapsed = int(diff_minutes // TIMEFRAME_MINUTES)
    is_fresh = bars_elapsed <= MAX_AGE_BARS
    result.update(
        {
            "freshness_status": "live_signal_freshness_fresh_within_horizon" if is_fresh else "live_signal_freshness_stale_beyond_horizon",
            "elapsed_minutes": diff_minutes,
            "bars_elapsed": bars_elapsed,
            "is_fresh": is_fresh,
            "is_stale": not is_fresh,
        }
    )
    return result


def recommended_next_step(status: str) -> str:
    if status in {
        "live_signal_freshness_fresh_current_or_latest_signal",
        "live_signal_freshness_fresh_within_horizon",
    }:
        return "build_or_run_manual_approval_dry_run_gate_only"
    if status == "live_signal_freshness_stale_beyond_horizon":
        return "wait_for_new_live_data_would_signal"
    return "refresh_no_order_live_data_and_rerun_freshness_check"


def no_order_evidence_row(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "no_mt5_import_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_api_query_performed": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_broker_payload_constructed": True,
        "no_executable_order_object_constructed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
        "evidence_label": "read_only_live_signal_freshness_no_order_boundary",
        "caveat": "freshness_check_only_no_approval",
    }


def status_rows(args: argparse.Namespace, result: dict[str, Any]) -> list[dict[str, Any]]:
    blocked = str(result["freshness_status"]).startswith("blocked_")
    return [
        {
            "run_id": args.run_id,
            "freshness_status": result["freshness_status"],
            "status_area": "signal_freshness",
            "observed_value": result.get("bars_elapsed"),
            "expected_value": f"<= {MAX_AGE_BARS} M15 bars",
            "blocking_if_failed": blocked or result["is_stale"],
            "caveat": "does_not_authorize_approval_or_request",
        },
        {
            "run_id": args.run_id,
            "freshness_status": result["freshness_status"],
            "status_area": "future_manual_approval_allowed_now",
            "observed_value": False,
            "expected_value": False,
            "blocking_if_failed": False,
            "caveat": "always_false_in_this_module",
        },
    ]


def timing_row(args: argparse.Namespace, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "signal_time_server": result.get("signal_time_server", ""),
        "latest_feature_time_server": result.get("latest_feature_time_server", ""),
        "timeframe_minutes": TIMEFRAME_MINUTES,
        "max_age_bars": MAX_AGE_BARS,
        "max_age_minutes": MAX_AGE_MINUTES,
        "elapsed_minutes": result.get("elapsed_minutes"),
        "bars_elapsed": result.get("bars_elapsed"),
        "is_fresh": result.get("is_fresh", False),
        "is_stale": result.get("is_stale", False),
        "future_manual_approval_allowed_now": False,
        "request_construction_allowed_now": False,
    }


def upstream_rows(args: argparse.Namespace, inputs: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    future_status = inputs["future_request"].get("plan_status", "missing_optional")
    return [
        {
            "run_id": args.run_id,
            "source_area": "canonical_registry",
            "source_path": inputs["paths"]["registry"],
            "source_status": "passed" if validate_canonical_registry(inputs["registry"]) else "failed",
            "observed_value": inputs["registry"].get("candidate_id"),
            "expected_value": CANDIDATE_ID,
            "evidence_label": "canonical_candidate_confirmed",
            "blocking_if_failed": not validate_canonical_registry(inputs["registry"]),
        },
        {
            "run_id": args.run_id,
            "source_area": "demo_execution_policy",
            "source_path": inputs["paths"]["policy"],
            "source_status": "passed" if validate_demo_policy(inputs["policy"]) else "failed",
            "observed_value": inputs["policy"].get("policy_id"),
            "expected_value": "no request/no execution policy",
            "evidence_label": "demo_policy_no_order_confirmed",
            "blocking_if_failed": not validate_demo_policy(inputs["policy"]),
        },
        {
            "run_id": args.run_id,
            "source_area": "would_signal_review",
            "source_path": inputs["paths"]["would_signal"],
            "source_status": "passed" if validate_would_signal_review(inputs["would_signal"])[0] else "failed",
            "observed_value": inputs["would_signal"].get("review_status"),
            "expected_value": "would_signal_review_available_no_order",
            "evidence_label": "live_would_signal_review_confirmed",
            "blocking_if_failed": not validate_would_signal_review(inputs["would_signal"])[0],
        },
        {
            "run_id": args.run_id,
            "source_area": "broker_local_reconciliation",
            "source_path": inputs["paths"]["broker_reconciliation"],
            "source_status": "passed" if validate_broker_reconciliation(inputs["broker_reconciliation"])[0] else "failed",
            "observed_value": inputs["broker_reconciliation"].get("reconciliation_status"),
            "expected_value": "broker_local_reconciliation_clean_no_local_no_broker",
            "evidence_label": "broker_local_reconciliation_confirmed",
            "blocking_if_failed": not validate_broker_reconciliation(inputs["broker_reconciliation"])[0],
        },
        {
            "run_id": args.run_id,
            "source_area": "future_request_readiness",
            "source_path": inputs["paths"]["future_request_readiness"],
            "source_status": "passed" if validate_future_request_readiness(inputs["future_request"])[0] else "failed",
            "observed_value": future_status,
            "expected_value": "optional, if present then no-order readiness",
            "evidence_label": "future_request_readiness_optional_validated",
            "blocking_if_failed": not validate_future_request_readiness(inputs["future_request"])[0],
        },
        {
            "run_id": args.run_id,
            "source_area": "feature_source",
            "source_path": args.db_path,
            "source_status": "passed" if not str(result["freshness_status"]).startswith("blocked_") else "failed",
            "observed_value": result.get("latest_feature_time_server", ""),
            "expected_value": "latest local feature timestamp readable",
            "evidence_label": "latest_feature_time_read_only",
            "blocking_if_failed": str(result["freshness_status"]).startswith("blocked_"),
        },
    ]


def add_freshness_warning(args: argparse.Namespace, warnings: list[dict[str, Any]], status: str) -> None:
    if status == "live_signal_freshness_stale_beyond_horizon":
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="stale_signal_blocks_future_manual_approval",
                message="The live shadow signal is beyond the fixed h10 freshness horizon.",
                source=args.would_signal_review_dir,
                blocking_warning=True,
            )
        )
    elif status in {
        "live_signal_freshness_fresh_current_or_latest_signal",
        "live_signal_freshness_fresh_within_horizon",
    }:
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="freshness_check_does_not_authorize_approval_or_execution",
                message="Freshness evidence does not authorize request construction, approval, or execution.",
                source=args.would_signal_review_dir,
                blocking_warning=False,
            )
        )


def build_result(args: argparse.Namespace, inputs: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    status = initial_block_status(inputs)
    signal_raw = signal_time_value(inputs["would_signal"])
    signal_dt, signal_error = parse_time_server(signal_raw)
    latest_raw = ""
    latest_dt: datetime | None = None
    latest_error = ""

    if status is None:
        if signal_error:
            status = "blocked_freshness_unverifiable"
            warnings.append(warning_row(run_id=args.run_id, warning_code="signal_time_unparseable", message=signal_error, source=inputs["paths"]["would_signal"], blocking_warning=True))
        else:
            feature = inspect_latest_feature_time(Path(args.db_path))
            if feature["status"] != "ok":
                status = str(feature["status"])
                warnings.append(warning_row(run_id=args.run_id, warning_code=status, message=str(feature.get("error") or status), source=args.db_path, blocking_warning=True))
            else:
                latest_raw = str(feature["latest_time_server"])
                latest_dt, latest_error = parse_time_server(latest_raw)
                if latest_error:
                    status = "blocked_freshness_unverifiable"
                    warnings.append(warning_row(run_id=args.run_id, warning_code="feature_time_unparseable", message=latest_error, source=args.db_path, blocking_warning=True))

    freshness = classify_freshness(signal_dt, latest_dt, "ok") if status is None else {
        "freshness_status": status,
        "elapsed_minutes": None,
        "bars_elapsed": None,
        "is_fresh": False,
        "is_stale": False,
    }
    add_freshness_warning(args, warnings, freshness["freshness_status"])
    return {
        **freshness,
        "candidate_id": inputs["registry"].get("candidate_id", CANDIDATE_ID),
        "symbol": inputs["registry"].get("symbol", CANDIDATE_SYMBOL),
        "timeframe": inputs["registry"].get("timeframe", CANDIDATE_TIMEFRAME),
        "direction": inputs["registry"].get("direction", CANDIDATE_DIRECTION),
        "source_nature": inputs["would_signal"].get("source_nature", ""),
        "signal_time_server": str(signal_raw or ""),
        "latest_feature_time_server": latest_raw,
        "evaluated_feature_time_server": inputs["would_signal"].get("evaluated_feature_time_server", signal_raw or ""),
        "latest_db_price_bar_time_server": inputs["would_signal"].get("latest_db_price_bar_time_server", ""),
        "latest_db_feature_time_server": inputs["would_signal"].get("latest_db_feature_time_server", latest_raw),
        "latest_mt5_closed_bar_time_server": inputs["would_signal"].get("latest_mt5_closed_bar_time_server", ""),
        "db_lag_bars_vs_mt5_latest_closed_bar": inputs["would_signal"].get("db_lag_bars_vs_mt5_latest_closed_bar", ""),
        "db_lag_minutes_vs_mt5_latest_closed_bar": inputs["would_signal"].get("db_lag_minutes_vs_mt5_latest_closed_bar", ""),
        "live_alignment_status": inputs["would_signal"].get("live_alignment_status", ""),
        "recommended_next_step": recommended_next_step(freshness["freshness_status"]),
    }


def write_report(path: Path, args: argparse.Namespace, result: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    lines = [
        "# Fixed Candidate Demo Live Signal Freshness",
        "",
        "Read-only no-order freshness recheck for an existing live shadow signal.",
        "No MT5 import or connection was performed.",
        "No broker/API query was performed.",
        "No broker state read was performed.",
        "No order execution was performed.",
        "No order request, broker payload, or executable order object was constructed.",
        "No order send, check, calc, or history function was called.",
        "No database mutation was performed; the feature timestamp was read through a read-only SQLite connection.",
        "No child scripts, import, feature generation, shadow wrapper, scheduler, loop, or background task were run.",
        "No parameter search or threshold change was performed.",
        "This freshness check is not future-performance proof, demo approval, manual approval, or a trading decision.",
        "",
        "## Inputs",
        "",
        f"- would_signal_review_dir: `{args.would_signal_review_dir}`",
        f"- broker_local_reconciliation_dir: `{args.broker_local_reconciliation_dir}`",
        f"- future_request_readiness_plan_dir: `{args.future_request_readiness_plan_dir}`",
        f"- canonical_registry: `{args.canonical_registry}`",
        f"- demo_execution_policy: `{args.demo_execution_policy}`",
        f"- db_path: `{args.db_path}`",
        f"- feature_table: `{FEATURE_TABLE}`",
        "",
        "## Timing",
        "",
        f"- freshness_status: `{result['freshness_status']}`",
        f"- signal_time_server: `{result['signal_time_server']}`",
        f"- latest_feature_time_server: `{result['latest_feature_time_server']}`",
        f"- evaluated_feature_time_server: `{result['evaluated_feature_time_server']}`",
        f"- latest_db_price_bar_time_server: `{result['latest_db_price_bar_time_server']}`",
        f"- latest_db_feature_time_server: `{result['latest_db_feature_time_server']}`",
        f"- latest_mt5_closed_bar_time_server: `{result['latest_mt5_closed_bar_time_server']}`",
        f"- db_lag_bars_vs_mt5_latest_closed_bar: `{result['db_lag_bars_vs_mt5_latest_closed_bar']}`",
        f"- db_lag_minutes_vs_mt5_latest_closed_bar: `{result['db_lag_minutes_vs_mt5_latest_closed_bar']}`",
        f"- live_alignment_status: `{result['live_alignment_status']}`",
        f"- elapsed_minutes: `{result['elapsed_minutes']}`",
        f"- bars_elapsed: `{result['bars_elapsed']}`",
        f"- max_age_bars: `{MAX_AGE_BARS}`",
        f"- max_age_minutes: `{MAX_AGE_MINUTES}`",
        f"- is_fresh: `{bool_text(bool(result['is_fresh']))}`",
        f"- is_stale: `{bool_text(bool(result['is_stale']))}`",
        "",
        "## Approval Boundary",
        "",
        "- future_manual_approval_allowed_now: `false`",
        "- request_construction_allowed_now: `false`",
        "",
        "## Warnings",
        "",
        f"- warnings_count: `{len(warnings)}`",
        f"- blocking_warnings_count: `{len(blocking_warnings(warnings))}`",
        "",
        "## Recommended Next Step",
        "",
        f"`{result['recommended_next_step']}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(path: Path, args: argparse.Namespace, output_dir: Path, result: dict[str, Any], paths: dict[str, Path], warnings: list[dict[str, Any]]) -> None:
    manifest = {
        "run_id": args.run_id,
        "created_at_utc": utc_now_text(),
        "output_dir": str(output_dir),
        "freshness_status": result["freshness_status"],
        "candidate_id": result["candidate_id"],
        "symbol": result["symbol"],
        "timeframe": result["timeframe"],
        "direction": result["direction"],
        "source_nature": result["source_nature"],
        "signal_time_server": result["signal_time_server"],
        "latest_feature_time_server": result["latest_feature_time_server"],
        "evaluated_feature_time_server": result["evaluated_feature_time_server"],
        "latest_db_price_bar_time_server": result["latest_db_price_bar_time_server"],
        "latest_db_feature_time_server": result["latest_db_feature_time_server"],
        "latest_mt5_closed_bar_time_server": result["latest_mt5_closed_bar_time_server"],
        "db_lag_bars_vs_mt5_latest_closed_bar": result["db_lag_bars_vs_mt5_latest_closed_bar"],
        "db_lag_minutes_vs_mt5_latest_closed_bar": result["db_lag_minutes_vs_mt5_latest_closed_bar"],
        "live_alignment_status": result["live_alignment_status"],
        "elapsed_minutes": result["elapsed_minutes"],
        "bars_elapsed": result["bars_elapsed"],
        "max_age_bars": MAX_AGE_BARS,
        "max_age_minutes": MAX_AGE_MINUTES,
        "is_fresh": result["is_fresh"],
        "is_stale": result["is_stale"],
        "future_manual_approval_allowed_now": False,
        "request_construction_allowed_now": False,
        "recommended_next_step": result["recommended_next_step"],
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "output_files": {key: str(value) for key, value in paths.items()},
        "no_mt5_import_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_api_query_performed": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_broker_payload_constructed": True,
        "no_executable_order_object_constructed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_artifacts(args: argparse.Namespace, paths: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    inputs = load_inputs(args, warnings)
    result = build_result(args, inputs, warnings)
    write_csv(paths["status"], status_rows(args, result), STATUS_FIELDNAMES)
    write_csv(paths["timing"], [timing_row(args, result)], TIMING_FIELDNAMES)
    write_csv(paths["upstream"], upstream_rows(args, inputs, result), UPSTREAM_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["no_order"], [no_order_evidence_row(args)], NO_ORDER_FIELDNAMES)
    write_report(paths["report"], args, result, warnings)
    write_manifest(paths["manifest"], args, output_dir, result, paths, warnings)
    return {"result": result, "warnings": warnings}


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    build_artifacts(args, paths, output_dir)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check fixed-candidate live signal freshness through local read-only feature data.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--would-signal-review-dir", type=Path, default=DEFAULT_WOULD_SIGNAL_REVIEW_DIR)
    parser.add_argument("--broker-local-reconciliation-dir", type=Path, default=DEFAULT_BROKER_LOCAL_RECONCILIATION_DIR)
    parser.add_argument("--future-request-readiness-plan-dir", type=Path, default=DEFAULT_FUTURE_REQUEST_READINESS_PLAN_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--demo-execution-policy", type=Path, default=DEFAULT_DEMO_EXECUTION_POLICY)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, csv.Error, sqlite3.Error) as exc:
        print(f"Fixed-candidate live signal freshness check failed: {exc}")
        return 1
    print("Fixed-candidate live signal freshness check complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
