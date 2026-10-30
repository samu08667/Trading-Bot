"""Build an artifact-only summary of a fixed-candidate paper cycle.

This module consolidates already-written paper/demo artifacts: the demo config,
demo strategy spec, paper signal logger readiness, numeric-tercile thresholds,
one paper signal logger run, and one or more paper trade tracker runs. It does
not run the paper signal logger or trade tracker, query or mutate the database,
generate data, connect to MT5, connect to broker/API services, execute orders,
run validation/backtests, or make candidate-quality or trading decisions.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_paper_cycle_summary"
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
DEFAULT_PAPER_SIGNAL_LOGGER_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_signal_logger"
    / "gbpusd_short_h10_1_5_off_hours_paper_signal_logger_v2"
)
DEFAULT_PAPER_TRADE_TRACKER_DIRS = [
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_trade_tracker"
    / "gbpusd_short_h10_1_5_off_hours_paper_trade_tracker_v1",
    BASE_DIR
    / "reports"
    / "fixed_candidate_paper_trade_tracker"
    / "gbpusd_short_h10_1_5_off_hours_paper_trade_tracker_v2",
]
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_paper_cycle_summary"

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

SIGNAL_LOG_CSV = "fixed_candidate_paper_signal_log.csv"
SIGNAL_STATE_JSON = "fixed_candidate_paper_signal_state.json"
SIGNAL_REPORT = "fixed_candidate_paper_signal_logger_report.md"
SIGNAL_WARNINGS = "fixed_candidate_paper_signal_logger_warnings.csv"
SIGNAL_MANIFEST = "fixed_candidate_paper_signal_logger_manifest.json"

TRACKER_CSV = "fixed_candidate_paper_trade_tracker.csv"
TRACKER_STATE_JSON = "fixed_candidate_paper_trade_tracker_state.json"
TRACKER_STATE_HISTORY = "fixed_candidate_paper_trade_tracker_state_history.csv"
TRACKER_REPORT = "fixed_candidate_paper_trade_tracker_report.md"
TRACKER_WARNINGS = "fixed_candidate_paper_trade_tracker_warnings.csv"
TRACKER_MANIFEST = "fixed_candidate_paper_trade_tracker_manifest.json"

OUTPUT_CSV = "fixed_candidate_paper_cycle_summary.csv"
OUTPUT_REPORT = "fixed_candidate_paper_cycle_summary_report.md"
OUTPUT_WARNINGS = "fixed_candidate_paper_cycle_summary_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_paper_cycle_summary_manifest.json"

FIELDNAMES = [
    "run_id",
    "row_type",
    "lifecycle_step",
    "artifact_status",
    "source_dir",
    "source_file",
    "open_signal_id",
    "signal_state",
    "trade_status",
    "entry_time_server",
    "exit_time_server",
    "entry_price",
    "exit_price",
    "tp_price",
    "sl_price",
    "bars_elapsed",
    "horizon_bars",
    "R_multiple",
    "evidence_label",
    "caveat",
    "warning_code",
    "blocking_warning",
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


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_dt(value: Any) -> datetime | None:
    if value in ("", None):
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
        "summary": output_dir / OUTPUT_CSV,
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


def base_row(args: argparse.Namespace, row_type: str, lifecycle_step: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "row_type": row_type,
        "lifecycle_step": lifecycle_step,
        "artifact_status": "available",
        "source_dir": "",
        "source_file": "",
        "open_signal_id": "",
        "signal_state": "",
        "trade_status": "",
        "entry_time_server": "",
        "exit_time_server": "",
        "entry_price": "",
        "exit_price": "",
        "tp_price": "",
        "sl_price": "",
        "bars_elapsed": "",
        "horizon_bars": "",
        "R_multiple": "",
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


def load_signal_logger(root: Path) -> dict[str, Any]:
    bundle = load_bundle(root, SIGNAL_LOG_CSV, SIGNAL_MANIFEST, SIGNAL_REPORT, SIGNAL_WARNINGS)
    state, state_error = read_json(root / SIGNAL_STATE_JSON)
    bundle["state_path"] = root / SIGNAL_STATE_JSON
    bundle["state"] = state
    bundle["state_error"] = state_error
    bundle["loaded"] = bundle["loaded"] and (not state_error) and (root / SIGNAL_STATE_JSON).exists()
    bundle["files_present"] = bundle["files_present"] and (root / SIGNAL_STATE_JSON).exists()
    bundle["error"] = labels(bundle["error"], state_error)
    return bundle


def load_tracker(root: Path, input_order: int) -> dict[str, Any]:
    bundle = load_bundle(root, TRACKER_CSV, TRACKER_MANIFEST, TRACKER_REPORT, TRACKER_WARNINGS)
    state, state_error = read_json(root / TRACKER_STATE_JSON)
    history_rows, history_error = read_csv_rows(root / TRACKER_STATE_HISTORY)
    bundle["state_path"] = root / TRACKER_STATE_JSON
    bundle["state"] = state
    bundle["state_error"] = state_error
    bundle["history_path"] = root / TRACKER_STATE_HISTORY
    bundle["history"] = history_rows
    bundle["input_order"] = input_order
    bundle["loaded"] = bundle["loaded"] and (not state_error) and (not history_error) and (root / TRACKER_STATE_JSON).exists()
    bundle["files_present"] = (
        bundle["files_present"] and (root / TRACKER_STATE_JSON).exists() and (root / TRACKER_STATE_HISTORY).exists()
    )
    bundle["error"] = labels(bundle["error"], state_error, history_error)
    return bundle


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


def source_artifact_warnings(args: argparse.Namespace, warnings: list[dict[str, Any]], name: str, bundle: dict[str, Any]) -> None:
    if bundle.get("loaded"):
        return
    status = artifact_status(bundle)
    add_warning(
        warnings,
        args=args,
        warning_code=f"{name}_{status}",
        message=f"{name} artifact is {status}.",
        source=bundle.get("dir", ""),
        blocking_warning=True,
    )


def signal_summary(signal: dict[str, Any]) -> dict[str, Any]:
    manifest = signal["manifest"]
    state = signal["state"]
    signal_row = signal["rows"][0] if signal["rows"] else {}
    return {
        "open_signal_id": state.get("open_signal_id") or signal_row.get("signal_id") or "",
        "signal_state": manifest.get("signal_state") or signal_row.get("signal_state") or "",
        "entry_time_server": state.get("entry_time_server") or manifest.get("evaluated_row_time_server") or signal_row.get("time_server") or "",
        "entry_price": state.get("entry_price") or signal_row.get("entry_reference_price") or "",
        "tp_price": state.get("tp_price") or signal_row.get("tp_price") or "",
        "sl_price": state.get("sl_price") or signal_row.get("sl_price") or "",
        "horizon_bars": state.get("horizon_bars") or signal_row.get("horizon_bars") or "",
    }


def tracker_generated_at(tracker: dict[str, Any]) -> tuple[datetime | None, int]:
    return parse_dt(tracker["manifest"].get("generated_at")), int(tracker.get("input_order") or 0)


def latest_tracker(trackers: list[dict[str, Any]]) -> dict[str, Any] | None:
    loaded = [tracker for tracker in trackers if tracker.get("loaded")]
    if not loaded:
        return None
    with_dates = [tracker for tracker in loaded if tracker_generated_at(tracker)[0] is not None]
    if with_dates:
        return max(with_dates, key=lambda tracker: tracker_generated_at(tracker)[0] or datetime.min.replace(tzinfo=timezone.utc))
    return max(loaded, key=lambda tracker: tracker.get("input_order") or 0)


def tracker_summary(tracker: dict[str, Any]) -> dict[str, Any]:
    manifest = tracker["manifest"]
    state = tracker["state"]
    summary_row = next((row for row in reversed(tracker["rows"]) if row.get("row_type") == "summary"), {})
    return {
        "open_signal_id": manifest.get("open_signal_id") or state.get("open_signal_id") or summary_row.get("open_signal_id") or "",
        "trade_status": manifest.get("trade_status") or state.get("trade_status") or summary_row.get("trade_status") or "",
        "entry_time_server": manifest.get("entry_time_server") or state.get("entry_time_server") or "",
        "exit_time_server": manifest.get("exit_time_server") or state.get("close_time_server") or summary_row.get("time_server") or "",
        "entry_price": manifest.get("entry_price") or state.get("entry_price") or summary_row.get("entry_price") or "",
        "exit_price": manifest.get("exit_price") or state.get("exit_price") or summary_row.get("exit_price") or "",
        "tp_price": manifest.get("tp_price") or state.get("tp_price") or summary_row.get("tp_price") or "",
        "sl_price": manifest.get("sl_price") or state.get("sl_price") or summary_row.get("sl_price") or "",
        "bars_elapsed": manifest.get("bars_elapsed_after") or state.get("bars_elapsed") or summary_row.get("bars_elapsed") or summary_row.get("bar_index_after_entry") or "",
        "horizon_bars": manifest.get("horizon_bars") or state.get("horizon_bars") or summary_row.get("horizon_bars") or "",
        "R_multiple": manifest.get("R_multiple") or state.get("R_multiple") or summary_row.get("R_multiple") or "",
        "exit_reason": manifest.get("final_exit_reason") or manifest.get("exit_reason") or state.get("exit_reason") or summary_row.get("exit_reason") or "",
        "has_open_paper_trade_after": manifest.get("has_open_paper_trade_after")
        if "has_open_paper_trade_after" in manifest
        else state.get("has_open_paper_trade"),
    }


def classify_cycle(signal_loaded: bool, trackers: list[dict[str, Any]]) -> str:
    if not signal_loaded or not trackers or any(not tracker.get("loaded") for tracker in trackers):
        return "paper_cycle_incomplete"
    latest = latest_tracker(trackers)
    if latest is None:
        return "paper_cycle_incomplete"
    status = str(tracker_summary(latest).get("trade_status") or "")
    exit_reason = str(tracker_summary(latest).get("exit_reason") or "")
    has_open = tracker_summary(latest).get("has_open_paper_trade_after")
    if status == "paper_trade_closed_tp" or exit_reason == "paper_tp_hit":
        return "paper_cycle_completed_tp"
    if status == "paper_trade_closed_sl" or exit_reason == "paper_sl_hit":
        return "paper_cycle_completed_sl"
    if status == "paper_trade_closed_timeout" or exit_reason == "paper_timeout":
        return "paper_cycle_completed_timeout"
    if status == "paper_trade_still_open" or has_open is True:
        return "paper_cycle_still_open"
    return "paper_cycle_incomplete"


def evidence_for_cycle_status(status: str) -> str:
    return {
        "paper_cycle_completed_tp": "paper_trade_closed_tp",
        "paper_cycle_completed_sl": "paper_trade_closed_sl",
        "paper_cycle_completed_timeout": "paper_trade_closed_timeout",
        "paper_cycle_still_open": "paper_trade_still_open_observed",
        "paper_cycle_incomplete": "paper_cycle_incomplete",
    }.get(status, "paper_cycle_incomplete")


def build_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
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
    signal = load_signal_logger(Path(args.paper_signal_logger_dir))
    trackers = [load_tracker(Path(path), index) for index, path in enumerate(args.paper_trade_tracker_dirs)]

    if not config:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_config_missing",
            message="Demo strategy config is missing or unreadable.",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    elif config_error:
        add_warning(
            warnings,
            args=args,
            warning_code="demo_strategy_config_unreadable",
            message=f"Demo strategy config is unreadable: {config_error}",
            source=args.demo_strategy_config,
            blocking_warning=True,
        )
    for name, bundle in [
        ("demo_strategy_spec", spec),
        ("paper_signal_logger_readiness", readiness),
        ("numeric_tercile_thresholds", thresholds),
        ("paper_signal_logger", signal),
    ]:
        source_artifact_warnings(args, warnings, name, bundle)
    for index, tracker in enumerate(trackers, start=1):
        source_artifact_warnings(args, warnings, f"paper_trade_tracker_{index}", tracker)

    signal_info = signal_summary(signal) if signal.get("loaded") else {}
    latest = latest_tracker(trackers)
    latest_info = tracker_summary(latest) if latest else {}
    final_cycle_status = classify_cycle(bool(signal.get("loaded")), trackers)
    paper_only_boundary_confirmed = bool(
        config.get("paper_only") is True
        and config.get("broker_connection_allowed") is False
        and config.get("order_execution_allowed") is False
        and config.get("real_money_allowed") is False
        and safety_ok_from_manifest(spec["manifest"])
        and safety_ok_from_manifest(readiness["manifest"])
        and safety_ok_from_manifest(thresholds["manifest"])
        and safety_ok_from_manifest(signal["manifest"])
        and all(safety_ok_from_manifest(tracker["manifest"]) for tracker in trackers if tracker.get("loaded"))
    )

    config_row = base_row(args, "config_context", "config_context")
    config_row.update(
        {
            "artifact_status": "available" if config and not config_error else "unreadable" if config_error else "missing",
            "source_file": args.demo_strategy_config,
            "evidence_label": "paper_only_boundary_confirmed" if config.get("paper_only") is True else "",
            "caveat": "paper_only_config_context",
            "warning_code": "demo_strategy_config_unreadable" if config_error else "",
            "blocking_warning": bool(config_error or not config),
        }
    )
    rows.append(config_row)

    for row_type, step, bundle, evidence in [
        ("spec_context", "demo_spec_context", spec, "paper_only_boundary_confirmed"),
        ("readiness_context", "readiness_context", readiness, "paper_only_boundary_confirmed"),
        ("threshold_context", "threshold_context", thresholds, "numeric_tercile_thresholds_available"),
    ]:
        row = base_row(args, row_type, step)
        row.update(
            {
                "artifact_status": artifact_status(bundle),
                "source_dir": bundle["dir"],
                "source_file": bundle.get("manifest_path") or bundle.get("json_path") or "",
                "evidence_label": evidence if bundle.get("loaded") else "",
                "warning_code": f"{step}_{artifact_status(bundle)}" if not bundle.get("loaded") else "",
                "blocking_warning": not bundle.get("loaded"),
            }
        )
        rows.append(row)

    signal_row = base_row(args, "signal_logger", "signal_logger_open_event")
    signal_row.update(
        {
            "artifact_status": artifact_status(signal),
            "source_dir": signal["dir"],
            "source_file": signal["csv_path"],
            "open_signal_id": signal_info.get("open_signal_id", ""),
            "signal_state": signal_info.get("signal_state", ""),
            "entry_time_server": signal_info.get("entry_time_server", ""),
            "entry_price": signal_info.get("entry_price", ""),
            "tp_price": signal_info.get("tp_price", ""),
            "sl_price": signal_info.get("sl_price", ""),
            "horizon_bars": signal_info.get("horizon_bars", ""),
            "evidence_label": "paper_signal_opened" if signal_info.get("signal_state") == "paper_signal_opened" else "",
            "warning_code": "paper_signal_logger_unavailable" if not signal.get("loaded") else "",
            "blocking_warning": not signal.get("loaded"),
        }
    )
    rows.append(signal_row)

    for index, tracker in enumerate(trackers, start=1):
        info = tracker_summary(tracker) if tracker.get("loaded") else {}
        linked = bool(
            signal_info.get("open_signal_id")
            and info.get("open_signal_id")
            and signal_info.get("open_signal_id") == info.get("open_signal_id")
        )
        if tracker.get("loaded") and signal_info.get("open_signal_id") and not linked:
            add_warning(
                warnings,
                args=args,
                warning_code="tracker_open_signal_id_mismatch",
                message="Tracker open_signal_id does not match the signal logger open_signal_id.",
                source=tracker["dir"],
                blocking_warning=False,
            )
        tracker_row = base_row(args, "trade_tracker", f"tracker_observation_v{index}")
        tracker_row.update(
            {
                "artifact_status": artifact_status(tracker),
                "source_dir": tracker["dir"],
                "source_file": tracker["csv_path"],
                "open_signal_id": info.get("open_signal_id", ""),
                "trade_status": info.get("trade_status", ""),
                "entry_time_server": info.get("entry_time_server", ""),
                "exit_time_server": info.get("exit_time_server", ""),
                "entry_price": info.get("entry_price", ""),
                "exit_price": info.get("exit_price", ""),
                "tp_price": info.get("tp_price", ""),
                "sl_price": info.get("sl_price", ""),
                "bars_elapsed": info.get("bars_elapsed", ""),
                "horizon_bars": info.get("horizon_bars", ""),
                "R_multiple": info.get("R_multiple", ""),
                "evidence_label": evidence_for_cycle_status(classify_cycle(True, [tracker]))
                if tracker.get("loaded")
                else "",
                "caveat": "linked_by_open_signal_id" if linked else "open_signal_id_link_not_confirmed",
                "warning_code": "paper_trade_tracker_unavailable" if not tracker.get("loaded") else "",
                "blocking_warning": not tracker.get("loaded"),
            }
        )
        rows.append(tracker_row)

    outcome = base_row(args, "cycle_outcome", "final_cycle_outcome")
    outcome.update(
        {
            "artifact_status": "available" if final_cycle_status != "paper_cycle_incomplete" else "missing",
            "open_signal_id": latest_info.get("open_signal_id") or signal_info.get("open_signal_id", ""),
            "signal_state": signal_info.get("signal_state", ""),
            "trade_status": latest_info.get("trade_status", ""),
            "entry_time_server": latest_info.get("entry_time_server") or signal_info.get("entry_time_server", ""),
            "exit_time_server": latest_info.get("exit_time_server", ""),
            "entry_price": latest_info.get("entry_price") or signal_info.get("entry_price", ""),
            "exit_price": latest_info.get("exit_price", ""),
            "tp_price": latest_info.get("tp_price") or signal_info.get("tp_price", ""),
            "sl_price": latest_info.get("sl_price") or signal_info.get("sl_price", ""),
            "bars_elapsed": latest_info.get("bars_elapsed", ""),
            "horizon_bars": latest_info.get("horizon_bars") or signal_info.get("horizon_bars", ""),
            "R_multiple": latest_info.get("R_multiple", ""),
            "evidence_label": labels(evidence_for_cycle_status(final_cycle_status), "paper_cycle_completed")
            if final_cycle_status.startswith("paper_cycle_completed")
            else evidence_for_cycle_status(final_cycle_status),
            "caveat": "one_cycle_only_not_statistical_evidence",
            "warning_code": "paper_cycle_incomplete" if final_cycle_status == "paper_cycle_incomplete" else "",
            "blocking_warning": final_cycle_status == "paper_cycle_incomplete",
        }
    )
    rows.append(outcome)

    caveat = base_row(args, "caveat", "caveats")
    caveat.update(
        {
            "artifact_status": "available_with_caveat",
            "open_signal_id": outcome["open_signal_id"],
            "trade_status": final_cycle_status,
            "evidence_label": "one_cycle_only_not_statistical_evidence",
            "caveat": "not_candidate_approval_not_statistical_evidence_no_real_execution",
        }
    )
    rows.append(caveat)

    next_step = (
        "rerun_paper_signal_logger_only_when_data_fresh_and_no_open_trade"
        if final_cycle_status.startswith("paper_cycle_completed")
        else "rerun_paper_trade_tracker_after_feature_refresh"
        if final_cycle_status == "paper_cycle_still_open"
        else "fix_missing_or_unreadable_paper_artifacts"
    )
    next_row = base_row(args, "next_step", "next_manual_step")
    next_row.update(
        {
            "artifact_status": "available",
            "open_signal_id": outcome["open_signal_id"],
            "trade_status": final_cycle_status,
            "evidence_label": next_step,
            "caveat": "manual_step_only_no_trading_decision_made",
        }
    )
    rows.append(next_row)

    missing_count = sum(1 for bundle in [spec, readiness, thresholds, signal, *trackers] if artifact_status(bundle) == "missing")
    unreadable_count = sum(1 for bundle in [spec, readiness, thresholds, signal, *trackers] if artifact_status(bundle) == "unreadable")
    metadata = {
        "config": config,
        "spec": spec,
        "readiness": readiness,
        "thresholds": thresholds,
        "signal": signal,
        "trackers": trackers,
        "signal_info": signal_info,
        "latest_tracker": latest,
        "latest_info": latest_info,
        "final_cycle_status": final_cycle_status,
        "paper_only_boundary_confirmed": paper_only_boundary_confirmed,
        "source_artifact_count": 5 + len(trackers),
        "missing_source_artifact_count": missing_count + (0 if config and not config_error else 1),
        "unreadable_source_artifact_count": unreadable_count + (1 if config_error else 0),
        "recommended_next_step": next_step,
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
    latest = metadata["latest_info"]
    final_status = metadata["final_cycle_status"]
    lines = [
        "# Fixed Candidate Paper Cycle Summary",
        "",
        "Artifact-only paper cycle summary. This module only consolidates completed local paper artifacts.",
        "One-cycle-only summary. This is not statistical evidence.",
        "No MT5, broker/API, or external connection was performed.",
        "No order execution was performed.",
        "No database mutation was performed.",
        "No data generation or feature refresh was performed.",
        "No trading decision was made.",
        "",
        "## Input Overview",
        "",
        f"- demo_strategy_config: `{args.demo_strategy_config}`",
        f"- demo_strategy_spec_dir: `{args.demo_strategy_spec_dir}`",
        f"- paper_signal_logger_readiness_dir: `{args.paper_signal_logger_readiness_dir}`",
        f"- numeric_tercile_thresholds_dir: `{args.numeric_tercile_thresholds_dir}`",
        f"- paper_signal_logger_dir: `{args.paper_signal_logger_dir}`",
        f"- paper_trade_tracker_dirs: `{', '.join(str(path) for path in args.paper_trade_tracker_dirs)}`",
        "",
        "## Signal Logger Summary",
        "",
        f"- open_signal_id: `{metadata['signal_info'].get('open_signal_id', '')}`",
        f"- signal_state: `{metadata['signal_info'].get('signal_state', '')}`",
        f"- entry_time_server: `{metadata['signal_info'].get('entry_time_server', '')}`",
        f"- entry_price: `{metadata['signal_info'].get('entry_price', '')}`",
        f"- tp_price: `{metadata['signal_info'].get('tp_price', '')}`",
        f"- sl_price: `{metadata['signal_info'].get('sl_price', '')}`",
        "",
        "## Tracker Timeline Summary",
        "",
    ]
    for tracker in metadata["trackers"]:
        info = tracker_summary(tracker) if tracker.get("loaded") else {}
        lines.extend(
            [
                f"- {tracker['dir']}: `{info.get('trade_status', artifact_status(tracker))}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Final Paper Cycle Outcome",
            "",
            f"- final_cycle_status: `{final_status}`",
            f"- final_exit_reason: `{latest.get('exit_reason', '')}`",
            f"- final_R_multiple: `{latest.get('R_multiple', '')}`",
            f"- final_bars_elapsed: `{latest.get('bars_elapsed', '')}`",
            f"- has_open_paper_trade_after: `{latest.get('has_open_paper_trade_after', '')}`",
            "",
            "## Caveats",
            "",
            "- One paper cycle only.",
            "- Not candidate approval.",
            "- Not live/demo broker performance.",
            "- No real execution.",
            "",
            "## Next Manual Step",
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
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    latest = metadata["latest_info"]
    signal = metadata["signal_info"]
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "demo_strategy_config_path": str(args.demo_strategy_config),
        "demo_strategy_spec_dir": str(args.demo_strategy_spec_dir),
        "paper_signal_logger_readiness_dir": str(args.paper_signal_logger_readiness_dir),
        "numeric_tercile_thresholds_dir": str(args.numeric_tercile_thresholds_dir),
        "paper_signal_logger_dir": str(args.paper_signal_logger_dir),
        "paper_trade_tracker_dirs": [str(path) for path in args.paper_trade_tracker_dirs],
        "source_artifact_count": metadata["source_artifact_count"],
        "missing_source_artifact_count": metadata["missing_source_artifact_count"],
        "unreadable_source_artifact_count": metadata["unreadable_source_artifact_count"],
        "cycle_row_count": len(rows),
        "final_cycle_status": metadata["final_cycle_status"],
        "open_signal_id": latest.get("open_signal_id") or signal.get("open_signal_id", ""),
        "entry_time_server": latest.get("entry_time_server") or signal.get("entry_time_server", ""),
        "exit_time_server": latest.get("exit_time_server", ""),
        "entry_price": safe_float(latest.get("entry_price") or signal.get("entry_price")),
        "exit_price": safe_float(latest.get("exit_price")),
        "tp_price": safe_float(latest.get("tp_price") or signal.get("tp_price")),
        "sl_price": safe_float(latest.get("sl_price") or signal.get("sl_price")),
        "final_exit_reason": latest.get("exit_reason", ""),
        "final_R_multiple": safe_float(latest.get("R_multiple")),
        "final_bars_elapsed": safe_int(latest.get("bars_elapsed")),
        "horizon_bars": safe_int(latest.get("horizon_bars") or signal.get("horizon_bars")),
        "has_open_paper_trade_after": latest.get("has_open_paper_trade_after"),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
        "paper_only_boundary_confirmed": bool(metadata["paper_only_boundary_confirmed"]),
        "no_child_scripts_executed": True,
        "no_paper_signal_logger_executed": True,
        "no_paper_trade_tracker_executed": True,
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
        "recommended_next_step": metadata["recommended_next_step"],
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    rows, warnings, metadata = build_rows(args)
    write_csv(paths["summary"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build artifact-only fixed-candidate paper cycle summary.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--demo-strategy-config", type=Path, default=DEFAULT_DEMO_STRATEGY_CONFIG)
    parser.add_argument("--demo-strategy-spec-dir", type=Path, default=DEFAULT_DEMO_STRATEGY_SPEC_DIR)
    parser.add_argument(
        "--paper-signal-logger-readiness-dir",
        type=Path,
        default=DEFAULT_PAPER_SIGNAL_LOGGER_READINESS_DIR,
    )
    parser.add_argument("--numeric-tercile-thresholds-dir", type=Path, default=DEFAULT_NUMERIC_TERCILE_THRESHOLDS_DIR)
    parser.add_argument("--paper-signal-logger-dir", type=Path, default=DEFAULT_PAPER_SIGNAL_LOGGER_DIR)
    parser.add_argument(
        "--paper-trade-tracker-dirs",
        type=Path,
        nargs="+",
        default=DEFAULT_PAPER_TRADE_TRACKER_DIRS,
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate paper cycle summary failed: {exc}")
        return 1
    print("Fixed-candidate paper cycle summary complete.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
