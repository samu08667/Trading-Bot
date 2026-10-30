"""Build a synthetic would-signal no-order cycle fixture for downstream checks.

This module is artifact-only. It does not read market data, query a database,
connect externally, construct broker requests, execute orders, or run child
scripts. The generated artifacts exist only to exercise downstream review
logic that consumes a completed no-order cycle with a would_signal child.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_would_signal_fixture_cycle"
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_would_signal_fixture_cycle"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_SYMBOL = "GBPUSD"
EXPECTED_TIMEFRAME = "M15"
EXPECTED_DIRECTION = "short"
EXPECTED_SPREAD_UNIT = "broker_points"
EXPECTED_MAX_SPREAD_POINTS = 15.0
EXPECTED_SESSION = "Off_hours"
EXPECTED_CLOSE_BUCKET = "high_tercile"
EXPECTED_VOLUME_BUCKET = "mid_tercile"
TP_ATR = 1.5
SL_ATR = 1.0
HORIZON_BARS = 10
SAME_BAR_POLICY = "stop_first"
TIMEOUT_POLICY = "h10"

PARENT_MANIFEST = "fixed_candidate_demo_no_order_cycle_once_manifest.json"
PARENT_REPORT = "fixed_candidate_demo_no_order_cycle_once_report.md"
PARENT_MAIN_CSV = "fixed_candidate_demo_no_order_cycle_once.csv"
PARENT_CHILD_COMMANDS_CSV = "fixed_candidate_demo_no_order_cycle_once_child_commands.csv"
PARENT_CHILD_RESULTS_CSV = "fixed_candidate_demo_no_order_cycle_once_child_results.csv"
PARENT_WARNINGS_CSV = "fixed_candidate_demo_no_order_cycle_once_warnings.csv"

CHILD_MANIFEST = "fixed_candidate_demo_no_order_dry_run_manifest.json"
CHILD_REPORT = "fixed_candidate_demo_no_order_dry_run_report.md"
CHILD_DECISION_CSV = "fixed_candidate_demo_no_order_dry_run_decision.csv"
CHILD_CHECKLIST_CSV = "fixed_candidate_demo_no_order_dry_run_checklist.csv"
CHILD_WARNINGS_CSV = "fixed_candidate_demo_no_order_dry_run_warnings.csv"
CHILD_NO_ORDER_EVIDENCE_CSV = "fixed_candidate_demo_no_order_dry_run_no_order_evidence.csv"
CHILD_STATE_PREVIEW_JSON = "fixed_candidate_demo_no_order_dry_run_state_preview.json"
CHILD_INPUT_ROW_SNAPSHOT_JSON = "fixed_candidate_demo_no_order_dry_run_input_row_snapshot.json"

NO_ORDER_FLAGS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_demo_broker_approval_performed",
    "no_candidate_quality_final_decision_performed",
    "no_trading_decision_performed",
)

PARENT_MAIN_FIELDNAMES = [
    "run_id",
    "cycle_area",
    "cycle_status",
    "artifact_status",
    "source_path",
    "observed_value",
    "expected_value",
    "evidence_label",
    "caveat",
    "warning_code",
    "blocking_warning",
]
PARENT_CHILD_COMMAND_FIELDNAMES = [
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
PARENT_CHILD_RESULT_FIELDNAMES = [
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
CHILD_DECISION_FIELDNAMES = [
    "run_id",
    "decision_label",
    "dry_run_status",
    "time_server",
    "symbol",
    "timeframe",
    "direction",
    "session_observed",
    "spread",
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
CHILD_CHECKLIST_FIELDNAMES = [
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
NO_ORDER_EVIDENCE_FIELDNAMES = [
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


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return bool_text(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def close_float(left: Any, right: float) -> bool:
    left_float = safe_float(left)
    return left_float is not None and abs(left_float - right) <= 1e-9


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


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


def warning_row(
    *,
    run_id: str,
    warning_code: str,
    severity: str,
    message: str,
    source: Path | str,
    blocking_warning: bool,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "source": str(source),
        "blocking_warning": blocking_warning,
    }


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in warnings if row.get("blocking_warning") is True]


def no_order_flag_payload() -> dict[str, bool]:
    return {flag: True for flag in NO_ORDER_FLAGS}


def default_output_dir(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / str(args.run_id)


def child_output_dir(output_dir: Path, run_id: str) -> Path:
    return output_dir / "children" / f"demo_no_order_dry_run_{run_id}"


def output_paths(output_dir: Path, run_id: str) -> dict[str, Path]:
    child_dir = child_output_dir(output_dir, run_id)
    return {
        "parent_manifest": output_dir / PARENT_MANIFEST,
        "parent_report": output_dir / PARENT_REPORT,
        "parent_main": output_dir / PARENT_MAIN_CSV,
        "parent_child_commands": output_dir / PARENT_CHILD_COMMANDS_CSV,
        "parent_child_results": output_dir / PARENT_CHILD_RESULTS_CSV,
        "parent_warnings": output_dir / PARENT_WARNINGS_CSV,
        "child_manifest": child_dir / CHILD_MANIFEST,
        "child_report": child_dir / CHILD_REPORT,
        "child_decision": child_dir / CHILD_DECISION_CSV,
        "child_checklist": child_dir / CHILD_CHECKLIST_CSV,
        "child_warnings": child_dir / CHILD_WARNINGS_CSV,
        "child_no_order_evidence": child_dir / CHILD_NO_ORDER_EVIDENCE_CSV,
        "child_state_preview": child_dir / CHILD_STATE_PREVIEW_JSON,
        "child_input_row_snapshot": child_dir / CHILD_INPUT_ROW_SNAPSHOT_JSON,
    }


def ensure_outputs_writable(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    paths["parent_manifest"].parent.mkdir(parents=True, exist_ok=True)
    paths["child_manifest"].parent.mkdir(parents=True, exist_ok=True)


def canonical_registry_valid(registry: dict[str, Any]) -> bool:
    return (
        registry.get("candidate_id") == EXPECTED_CANDIDATE_ID
        and registry.get("symbol") == EXPECTED_SYMBOL
        and registry.get("timeframe") == EXPECTED_TIMEFRAME
        and registry.get("direction") == EXPECTED_DIRECTION
        and registry.get("spread_unit") == EXPECTED_SPREAD_UNIT
        and close_float(registry.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS)
    )


def validate_inputs(args: argparse.Namespace, registry: dict[str, Any], registry_error: str) -> tuple[str, list[dict[str, Any]]]:
    warnings = [
        warning_row(
            run_id=args.run_id,
            warning_code="synthetic_fixture_not_actionable",
            severity="info",
            message="This would-signal cycle is synthetic and is not actionable market evidence.",
            source=args.output_dir or DEFAULT_OUTPUT_ROOT,
            blocking_warning=False,
        )
    ]
    status = "would_signal_fixture_available"

    if registry_error == "missing":
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="canonical_registry_missing",
                severity="error",
                message="Canonical registry is missing.",
                source=args.canonical_registry,
                blocking_warning=True,
            )
        )
        status = "blocked_missing_required_artifact"
    elif registry_error:
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="canonical_registry_unreadable",
                severity="error",
                message=f"Canonical registry is unreadable: {registry_error}",
                source=args.canonical_registry,
                blocking_warning=True,
            )
        )
        status = "blocked_unreadable_input"
    elif not canonical_registry_valid(registry):
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="canonical_registry_boundary_mismatch",
                severity="error",
                message="Canonical registry does not match fixed-candidate spread15 boundaries.",
                source=args.canonical_registry,
                blocking_warning=True,
            )
        )
        status = "blocked_by_config_boundary"

    entry = safe_float(args.entry_reference_price)
    atr_20 = safe_float(args.atr_20)
    spread = safe_float(args.spread)
    if args.source_mode != "synthetic_fixture":
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="source_mode_not_synthetic_fixture",
                severity="error",
                message="This builder only supports source_mode=synthetic_fixture.",
                source="cli",
                blocking_warning=True,
            )
        )
        status = "blocked_invalid_fixture_inputs"
    if entry is None or entry <= 0:
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="entry_reference_price_invalid",
                severity="error",
                message="Entry reference price must be numeric and positive.",
                source="cli",
                blocking_warning=True,
            )
        )
        status = "blocked_invalid_fixture_inputs"
    if atr_20 is None or atr_20 <= 0:
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="atr_20_invalid",
                severity="error",
                message="atr_20 must be numeric and positive.",
                source="cli",
                blocking_warning=True,
            )
        )
        status = "blocked_invalid_fixture_inputs"
    if spread is None or spread < 0 or spread > EXPECTED_MAX_SPREAD_POINTS:
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="spread_not_within_canonical_fixture_gate",
                severity="error",
                message="Fixture spread must be numeric, non-negative, and no greater than 15.0 broker_points.",
                source="cli",
                blocking_warning=True,
            )
        )
        status = "blocked_invalid_fixture_inputs"
    if not str(args.fixture_time_server).strip():
        warnings.append(
            warning_row(
                run_id=args.run_id,
                warning_code="fixture_time_server_missing",
                severity="error",
                message="Fixture time_server must be provided.",
                source="cli",
                blocking_warning=True,
            )
        )
        status = "blocked_invalid_fixture_inputs"
    return status, warnings


def cycle_status_for_fixture(fixture_status: str) -> str:
    if fixture_status == "would_signal_fixture_available":
        return "demo_no_order_cycle_completed_would_signal"
    if fixture_status == "blocked_missing_required_artifact":
        return "blocked_missing_required_artifact"
    if fixture_status == "blocked_unreadable_input":
        return "blocked_unreadable_input"
    if fixture_status == "blocked_by_config_boundary":
        return "blocked_by_config_boundary"
    return "blocked_invalid_fixture_inputs"


def dry_run_status_for_fixture(fixture_status: str) -> str:
    if fixture_status == "would_signal_fixture_available":
        return "demo_no_order_dry_run_would_signal"
    return fixture_status


def decision_label_for_fixture(fixture_status: str) -> str:
    return "would_signal" if fixture_status == "would_signal_fixture_available" else "would_block"


def recommended_next_step(fixture_status: str) -> str:
    if fixture_status == "would_signal_fixture_available":
        return "run_shadow_signal_once_existing_cycle_fixture"
    if fixture_status in {"blocked_missing_required_artifact", "blocked_unreadable_input"}:
        return "fix_missing_or_unreadable_fixture_inputs"
    return "fix_fixture_input_boundaries"


def preview_prices(entry_reference_price: float, atr_20: float) -> tuple[float, float]:
    return entry_reference_price - TP_ATR * atr_20, entry_reference_price + SL_ATR * atr_20


def parent_rows(
    *,
    args: argparse.Namespace,
    fixture_status: str,
    cycle_status: str,
    child_manifest_path: Path,
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "run_id": args.run_id,
            "cycle_area": "source_mode",
            "cycle_status": cycle_status,
            "artifact_status": fixture_status,
            "source_path": "synthetic_fixture",
            "observed_value": args.source_mode,
            "expected_value": "synthetic_fixture",
            "evidence_label": "synthetic_fixture_not_actionable",
            "caveat": "not_live_market_data_not_replay_not_actionable",
            "warning_code": "",
            "blocking_warning": False,
        },
        {
            "run_id": args.run_id,
            "cycle_area": "child_dry_run_manifest",
            "cycle_status": cycle_status,
            "artifact_status": "available" if fixture_status == "would_signal_fixture_available" else "blocked",
            "source_path": child_manifest_path,
            "observed_value": "would_signal" if fixture_status == "would_signal_fixture_available" else "would_block",
            "expected_value": "would_signal",
            "evidence_label": "fixture_would_signal_child_manifest_created",
            "caveat": "synthetic_child_manifest_for_downstream_contract_testing",
            "warning_code": "",
            "blocking_warning": False,
        },
        {
            "run_id": args.run_id,
            "cycle_area": "no_order_boundary",
            "cycle_status": cycle_status,
            "artifact_status": "confirmed",
            "source_path": "fixture_builder",
            "observed_value": "all no-order flags true",
            "expected_value": "no order path constructed or executed",
            "evidence_label": "no_order_boundary_confirmed",
            "caveat": "fixture builder does not connect externally or run children",
            "warning_code": "",
            "blocking_warning": False,
        },
        {
            "run_id": args.run_id,
            "cycle_area": "warnings",
            "cycle_status": cycle_status,
            "artifact_status": "written",
            "source_path": PARENT_WARNINGS_CSV,
            "observed_value": len(warnings),
            "expected_value": "no blocking warnings for valid fixture",
            "evidence_label": "fixture_warnings_recorded",
            "caveat": "info warning marks fixture as non-actionable",
            "warning_code": "",
            "blocking_warning": bool(blocking_warnings(warnings)),
        },
    ]


def child_decision_row(args: argparse.Namespace, fixture_status: str, entry: float | None, atr_20: float | None, spread: float | None) -> dict[str, Any]:
    valid = fixture_status == "would_signal_fixture_available" and entry is not None and atr_20 is not None
    tp_price, sl_price = preview_prices(entry, atr_20) if valid else ("", "")
    return {
        "run_id": args.run_id,
        "decision_label": decision_label_for_fixture(fixture_status),
        "dry_run_status": dry_run_status_for_fixture(fixture_status),
        "time_server": args.fixture_time_server,
        "symbol": EXPECTED_SYMBOL,
        "timeframe": EXPECTED_TIMEFRAME,
        "direction": EXPECTED_DIRECTION,
        "session_observed": EXPECTED_SESSION,
        "spread": spread if spread is not None else "",
        "spread_unit": EXPECTED_SPREAD_UNIT,
        "max_spread_points": EXPECTED_MAX_SPREAD_POINTS,
        "close": entry if entry is not None else "",
        "atr_20": atr_20 if atr_20 is not None else "",
        "close_to_ma_fast_atr_20": "synthetic_high_bucket_value",
        "close_to_ma_fast_atr_20_bucket": EXPECTED_CLOSE_BUCKET,
        "tick_volume_percentile_100": "synthetic_mid_bucket_value",
        "tick_volume_percentile_100_bucket": EXPECTED_VOLUME_BUCKET,
        "entry_reference_price": entry if valid else "",
        "tp_price_preview": tp_price,
        "sl_price_preview": sl_price,
        "horizon_bars": HORIZON_BARS,
        "same_bar_policy": SAME_BAR_POLICY,
        "timeout_policy": TIMEOUT_POLICY,
        "risk_percent_configured": 1.0,
        "volume_preview_status": "not_computed_no_order_calc_forbidden",
        "skip_reasons": "",
        "block_reasons": "" if valid else "fixture_input_boundary_blocked",
        "no_order_request_constructed": True,
        "no_order_execution_performed": True,
    }


def child_checklist_rows(args: argparse.Namespace, fixture_status: str) -> list[dict[str, Any]]:
    status = "passed" if fixture_status == "would_signal_fixture_available" else "blocked"
    rows = [
        ("source_mode", "synthetic_fixture_declared", args.source_mode, "synthetic_fixture", "not live market data"),
        ("signal_path", "would_signal_label_emitted", decision_label_for_fixture(fixture_status), "would_signal", "downstream shadow fixture only"),
        ("session_gate", "off_hours_fixture", EXPECTED_SESSION, EXPECTED_SESSION, "synthetic gate evidence"),
        ("spread_gate", "spread15_fixture", args.spread, "<= 15.0 broker_points", "broker_points direct comparison"),
        ("bucket_gate", "fixed_buckets_fixture", f"{EXPECTED_CLOSE_BUCKET};{EXPECTED_VOLUME_BUCKET}", "high_tercile;mid_tercile", "frozen thresholds are not recomputed"),
        ("preview_prices", "short_tp_sl_preview", "computed" if status == "passed" else "not_applicable", "no order request", "preview only"),
        ("no_order_boundary", "no_order_flags_true", "true", "true", "no request or execution path exists"),
    ]
    return [
        {
            "run_id": args.run_id,
            "check_area": area,
            "check_name": name,
            "check_status": status,
            "observed_value": observed,
            "expected_value": expected,
            "blocking_if_failed": True,
            "evidence_source": "synthetic_fixture_builder",
            "caveat": caveat,
            "warning_code": "" if status == "passed" else "fixture_input_boundary_blocked",
        }
        for area, name, observed, expected, caveat in rows
    ]


def no_order_evidence_row(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
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
        "evidence_label": "fixture_no_order_boundary_confirmed",
        "caveat": "synthetic_fixture_only_not_actionable",
    }


def build_manifests(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    paths: dict[str, Path],
    registry: dict[str, Any],
    fixture_status: str,
    warnings: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    entry = safe_float(args.entry_reference_price)
    atr_20 = safe_float(args.atr_20)
    spread = safe_float(args.spread)
    valid = fixture_status == "would_signal_fixture_available" and entry is not None and atr_20 is not None
    tp_price, sl_price = preview_prices(entry, atr_20) if valid else ("", "")
    cycle_status = cycle_status_for_fixture(fixture_status)
    dry_run_status = dry_run_status_for_fixture(fixture_status)
    decision_label = decision_label_for_fixture(fixture_status)
    child_manifest_path = paths["child_manifest"].resolve()
    no_order_flags = no_order_flag_payload()
    warning_count = len(warnings)
    blocking_count = len(blocking_warnings(warnings))

    child_manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(paths["child_manifest"].parent),
        "source_mode": args.source_mode,
        "fixture_not_live_market_data": True,
        "fixture_not_backtest_result": True,
        "fixture_not_actionable": True,
        "historical_or_synthetic_observation_only": True,
        "decision_label": decision_label,
        "dry_run_status": dry_run_status,
        "time_server": args.fixture_time_server,
        "feature_row_fresh": valid,
        "feature_row_staleness_hours": 0.0 if valid else "",
        "symbol": EXPECTED_SYMBOL,
        "timeframe": EXPECTED_TIMEFRAME,
        "direction": EXPECTED_DIRECTION,
        "session_observed": EXPECTED_SESSION,
        "spread": spread if spread is not None else "",
        "spread_unit": EXPECTED_SPREAD_UNIT,
        "max_spread_points": EXPECTED_MAX_SPREAD_POINTS,
        "spread_within_gate": bool(spread is not None and spread <= EXPECTED_MAX_SPREAD_POINTS),
        "close": entry if entry is not None else "",
        "atr_20": atr_20 if atr_20 is not None else "",
        "close_to_ma_fast_atr_20_bucket": EXPECTED_CLOSE_BUCKET,
        "tick_volume_percentile_100_bucket": EXPECTED_VOLUME_BUCKET,
        "existing_open_state_detected": False,
        "entry_reference_price": entry if valid else "",
        "tp_price_preview": tp_price,
        "sl_price_preview": sl_price,
        "horizon_bars": HORIZON_BARS,
        "same_bar_policy": SAME_BAR_POLICY,
        "timeout_policy": TIMEOUT_POLICY,
        "volume_preview_status": "not_computed_no_order_calc_forbidden",
        "skip_reason_count": 0,
        "block_reason_count": 0 if valid else blocking_count,
        "warnings_count": warning_count,
        "warning_count": warning_count,
        "blocking_warnings_count": blocking_count,
        **no_order_flags,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_demo_broker_approval_performed": True,
    }

    parent_manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "canonical_registry_path": str(args.canonical_registry),
        "source_mode": args.source_mode,
        "fixture_status": fixture_status,
        "cycle_status": cycle_status,
        "latest_child_manifest_path": str(child_manifest_path),
        "no_order_dry_run_child_output_dir": str(paths["child_manifest"].parent.resolve()),
        "child_decision_label": decision_label,
        "child_dry_run_status": dry_run_status,
        "child_feature_row_fresh": valid,
        "child_time_server": args.fixture_time_server,
        "child_session_observed": EXPECTED_SESSION,
        "child_spread": spread if spread is not None else "",
        "child_spread_within_gate": bool(spread is not None and spread <= EXPECTED_MAX_SPREAD_POINTS),
        "child_close_to_ma_fast_atr_20_bucket": EXPECTED_CLOSE_BUCKET,
        "child_tick_volume_percentile_100_bucket": EXPECTED_VOLUME_BUCKET,
        "child_skip_reason_count": 0,
        "child_block_reason_count": 0 if valid else blocking_count,
        "candidate_id": registry.get("candidate_id", EXPECTED_CANDIDATE_ID),
        "symbol": registry.get("symbol", EXPECTED_SYMBOL),
        "timeframe": registry.get("timeframe", EXPECTED_TIMEFRAME),
        "direction": registry.get("direction", EXPECTED_DIRECTION),
        "spread_unit": registry.get("spread_unit", EXPECTED_SPREAD_UNIT),
        "max_spread_points": safe_float(registry.get("max_spread_points")) if registry else EXPECTED_MAX_SPREAD_POINTS,
        "fixture_time_server": args.fixture_time_server,
        "entry_reference_price": entry if valid else "",
        "atr_20": atr_20 if atr_20 is not None else "",
        "tp_price_preview": tp_price,
        "sl_price_preview": sl_price,
        "horizon_bars": HORIZON_BARS,
        "same_bar_policy": SAME_BAR_POLICY,
        "timeout_policy": TIMEOUT_POLICY,
        "feature_row_fresh": valid,
        "feature_row_staleness_hours": 0.0 if valid else "",
        "fixture_not_live_market_data": True,
        "fixture_not_backtest_result": True,
        "fixture_not_actionable": True,
        "historical_or_synthetic_observation_only": True,
        "child_command_count": 0,
        "child_success_count": 0,
        "child_failure_count": 0,
        "mt5_bar_import_child_executed": False,
        "price_feature_generation_child_executed": False,
        "no_order_dry_run_child_executed": False,
        "no_order_boundary_confirmed": True,
        "missing_no_order_flag_count": 0,
        "unsafe_no_order_flag_count": 0,
        "missing_no_order_flags": [],
        "unsafe_no_order_flags": [],
        "warnings_count": warning_count,
        "warning_count": warning_count,
        "blocking_warnings_count": blocking_count,
        "recommended_next_step": recommended_next_step(fixture_status),
        **no_order_flags,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_replay_rerun": True,
        "no_cost_sensitivity_rerun": True,
        "no_recent_holdout_rerun": True,
        "no_paper_signal_logger_run": True,
        "no_paper_trade_tracker_run": True,
        "no_paper_orchestrator_run": True,
        "no_optimization_performed": True,
    }
    return parent_manifest, child_manifest


def write_parent_report(
    path: Path,
    *,
    args: argparse.Namespace,
    fixture_status: str,
    cycle_status: str,
    child_manifest: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> None:
    lines = [
        "# Fixed Candidate Demo Would-Signal Fixture Cycle",
        "",
        "This is a fixture-only synthetic no-order cycle artifact.",
        "It is not live market data, not a replay result, not a backtest result, and not actionable evidence.",
        "It is intended only to test downstream shadow_signal_detected handling.",
        "No MT5 connection was performed.",
        "No broker or API connection was performed.",
        "No account or symbol live query was performed.",
        "No order execution was performed.",
        "No broker order request was constructed.",
        "No order_check or order_calc call was performed.",
        "No database mutation, feature refresh, replay, paper workflow, or child script execution was performed.",
        "No demo broker approval or trading decision was made.",
        "",
        "## Fixture Overview",
        "",
        f"- run_id: `{args.run_id}`",
        f"- fixture_status: `{fixture_status}`",
        f"- cycle_status: `{cycle_status}`",
        f"- source_mode: `{args.source_mode}`",
        f"- fixture_time_server: `{args.fixture_time_server}`",
        "",
        "## Synthetic Signal Preview",
        "",
        f"- decision_label: `{child_manifest.get('decision_label', '')}`",
        f"- dry_run_status: `{child_manifest.get('dry_run_status', '')}`",
        f"- entry_reference_price: `{child_manifest.get('entry_reference_price', '')}`",
        f"- tp_price_preview: `{child_manifest.get('tp_price_preview', '')}`",
        f"- sl_price_preview: `{child_manifest.get('sl_price_preview', '')}`",
        f"- spread_policy: `{EXPECTED_SPREAD_UNIT}` / `{EXPECTED_MAX_SPREAD_POINTS}`",
        "",
        "## No-Order Boundary",
        "",
        "- no_order_execution_performed: `true`",
        "- no_order_request_constructed: `true`",
        "- no_order_send_called: `true`",
        "- no_order_check_called: `true`",
        "- no_order_calc_margin_called: `true`",
        "- no_order_calc_profit_called: `true`",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        lines.extend(f"- {row['warning_code']}: {row['message']}" for row in warnings)
    else:
        lines.append("- none")
    lines.extend(["", "## Recommended Next Step", "", f"`{recommended_next_step(fixture_status)}`", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_child_report(path: Path, *, args: argparse.Namespace, child_manifest: dict[str, Any]) -> None:
    lines = [
        "# Fixed Candidate Demo No-Order Dry-Run Fixture Child",
        "",
        "This child artifact is synthetic and fixture-only.",
        "It did not query MT5, broker/API, account, symbol, database, or live market state.",
        "It did not construct a broker request, execute an order, call order_check, or call order_calc.",
        "It exists only to let downstream artifact consumers observe a would_signal shape.",
        "",
        "## Decision",
        "",
        f"- decision_label: `{child_manifest.get('decision_label', '')}`",
        f"- dry_run_status: `{child_manifest.get('dry_run_status', '')}`",
        f"- time_server: `{args.fixture_time_server}`",
        f"- fixture_not_actionable: `{bool_text(True)}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def state_preview(args: argparse.Namespace, fixture_status: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "current_state_source": "synthetic_fixture_no_state_file",
        "existing_open_state_detected": False,
        "would_create_local_state_preview": fixture_status == "would_signal_fixture_available",
        "no_state_mutation_performed": True,
        "fixture_not_live_market_data": True,
        "fixture_not_actionable": True,
    }


def input_row_snapshot(args: argparse.Namespace, fixture_status: str) -> dict[str, Any]:
    entry = safe_float(args.entry_reference_price)
    atr_20 = safe_float(args.atr_20)
    spread = safe_float(args.spread)
    return {
        "run_id": args.run_id,
        "source_mode": args.source_mode,
        "fixture_status": fixture_status,
        "time_server": args.fixture_time_server,
        "symbol": EXPECTED_SYMBOL,
        "timeframe": EXPECTED_TIMEFRAME,
        "open": entry,
        "high": entry,
        "low": entry,
        "close": entry,
        "atr_20": atr_20,
        "spread": spread,
        "spread_unit": EXPECTED_SPREAD_UNIT,
        "hour_session": EXPECTED_SESSION,
        "close_to_ma_fast_atr_20": "synthetic_high_bucket_value",
        "tick_volume_percentile_100": "synthetic_mid_bucket_value",
        "close_to_ma_fast_atr_20_bucket": EXPECTED_CLOSE_BUCKET,
        "tick_volume_percentile_100_bucket": EXPECTED_VOLUME_BUCKET,
        "fixture_not_live_market_data": True,
        "fixture_not_backtest_result": True,
        "fixture_not_actionable": True,
    }


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = default_output_dir(args)
    paths = output_paths(output_dir, args.run_id)
    ensure_outputs_writable(paths, bool(args.overwrite))

    registry, registry_error = read_json(Path(args.canonical_registry))
    fixture_status, warnings = validate_inputs(args, registry, registry_error)
    parent_manifest, child_manifest = build_manifests(
        args=args,
        output_dir=output_dir,
        paths=paths,
        registry=registry,
        fixture_status=fixture_status,
        warnings=warnings,
    )
    cycle_status = str(parent_manifest["cycle_status"])
    entry = safe_float(args.entry_reference_price)
    atr_20 = safe_float(args.atr_20)
    spread = safe_float(args.spread)

    write_json(paths["parent_manifest"], parent_manifest)
    write_csv(
        paths["parent_main"],
        parent_rows(
            args=args,
            fixture_status=fixture_status,
            cycle_status=cycle_status,
            child_manifest_path=paths["child_manifest"],
            warnings=warnings,
        ),
        PARENT_MAIN_FIELDNAMES,
    )
    write_csv(paths["parent_child_commands"], [], PARENT_CHILD_COMMAND_FIELDNAMES)
    write_csv(paths["parent_child_results"], [], PARENT_CHILD_RESULT_FIELDNAMES)
    write_csv(paths["parent_warnings"], warnings, WARNING_FIELDNAMES)
    write_parent_report(
        paths["parent_report"],
        args=args,
        fixture_status=fixture_status,
        cycle_status=cycle_status,
        child_manifest=child_manifest,
        warnings=warnings,
    )

    write_json(paths["child_manifest"], child_manifest)
    write_csv(paths["child_decision"], [child_decision_row(args, fixture_status, entry, atr_20, spread)], CHILD_DECISION_FIELDNAMES)
    write_csv(paths["child_checklist"], child_checklist_rows(args, fixture_status), CHILD_CHECKLIST_FIELDNAMES)
    write_csv(paths["child_warnings"], warnings, WARNING_FIELDNAMES)
    write_csv(paths["child_no_order_evidence"], [no_order_evidence_row(args.run_id)], NO_ORDER_EVIDENCE_FIELDNAMES)
    write_json(paths["child_state_preview"], state_preview(args, fixture_status))
    write_json(paths["child_input_row_snapshot"], input_row_snapshot(args, fixture_status))
    write_child_report(paths["child_report"], args=args, child_manifest=child_manifest)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a synthetic would-signal no-order cycle fixture for fixed-candidate downstream tests.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--source-mode", default="synthetic_fixture")
    parser.add_argument("--fixture-time-server", default="2026-06-01 02:00:00")
    parser.add_argument("--entry-reference-price", type=float, default=1.34600)
    parser.add_argument("--atr-20", type=float, default=0.00042)
    parser.add_argument("--spread", type=float, default=3.0)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        build_outputs(args)
    except Exception as exc:
        print(f"Fixed-candidate would-signal fixture cycle failed: {exc}")
        return 1
    print("Fixed-candidate would-signal fixture cycle complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
