"""Review one fixed-candidate demo would-signal shadow artifact.

This module is artifact-only. It reads local shadow-signal artifacts and writes
review artifacts. It does not query market infrastructure, databases, accounts,
symbols, or run child scripts. It never constructs broker requests or performs
order-related actions.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_demo_would_signal_review"
DEFAULT_SHADOW_SIGNAL_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_demo_shadow_signal_once"
    / "gbpusd_short_h10_1_5_off_hours_demo_shadow_signal_once_fixture_v1"
)
DEFAULT_CANONICAL_REGISTRY = BASE_DIR / "config" / "fixed_candidate_current_canonical.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_demo_would_signal_review"

EXPECTED_CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours"
EXPECTED_SYMBOL = "GBPUSD"
EXPECTED_TIMEFRAME = "M15"
EXPECTED_DIRECTION = "short"
EXPECTED_SESSION = "Off_hours"
EXPECTED_SPREAD_UNIT = "broker_points"
EXPECTED_MAX_SPREAD_POINTS = 15.0
EXPECTED_CLOSE_BUCKET = "high_tercile"
EXPECTED_VOLUME_BUCKET = "mid_tercile"
EXPECTED_TP_ATR = 1.5
EXPECTED_SL_ATR = 1.0
FLOAT_TOLERANCE = 1e-6

SHADOW_MANIFEST = "fixed_candidate_demo_shadow_signal_once_manifest.json"
SHADOW_REPORT = "fixed_candidate_demo_shadow_signal_once_report.md"
SHADOW_MAIN_CSV = "fixed_candidate_demo_shadow_signal_once.csv"
SHADOW_NO_ORDER_EVIDENCE_CSV = "fixed_candidate_demo_shadow_signal_once_no_order_evidence.csv"
SHADOW_REVIEW_PACKET = "fixed_candidate_demo_shadow_signal_once_review_packet.json"
SHADOW_WARNINGS_CSV = "fixed_candidate_demo_shadow_signal_once_warnings.csv"

OUTPUT_MANIFEST = "fixed_candidate_demo_would_signal_review_manifest.json"
OUTPUT_REPORT = "fixed_candidate_demo_would_signal_review_report.md"
OUTPUT_MAIN_CSV = "fixed_candidate_demo_would_signal_review.csv"
OUTPUT_CHECKLIST_CSV = "fixed_candidate_demo_would_signal_review_checklist.csv"
OUTPUT_WARNINGS_CSV = "fixed_candidate_demo_would_signal_review_warnings.csv"

NO_ORDER_TRUE_FIELDS = (
    "no_order_execution_performed",
    "no_order_request_constructed",
    "no_order_send_called",
    "no_order_check_called",
    "no_order_calc_margin_called",
    "no_order_calc_profit_called",
    "no_demo_broker_approval_performed",
    "no_trading_decision_performed",
)

MAIN_FIELDNAMES = [
    "run_id",
    "review_status",
    "source_nature",
    "shadow_status",
    "shadow_decision_label",
    "candidate_id",
    "symbol",
    "timeframe",
    "direction",
    "time_server",
    "session_observed",
    "spread",
    "spread_unit",
    "max_spread_points",
    "close",
    "atr_20",
    "entry_reference_price",
    "tp_price_preview",
    "sl_price_preview",
    "tp_distance_atr",
    "sl_distance_atr",
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100_bucket",
    "manual_review_required",
    "actionable_signal",
    "order_execution_allowed",
    "order_request_construction_allowed",
    "demo_broker_approval_performed",
    "recommended_next_step",
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
WARNING_FIELDNAMES = ["run_id", "warning_code", "severity", "message", "source", "blocking_warning"]


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


def safe_int(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def close_float(left: Any, right: float, tolerance: float = FLOAT_TOLERANCE) -> bool:
    left_float = safe_float(left)
    return left_float is not None and abs(left_float - right) <= tolerance


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


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    if not path.exists():
        return [], "missing"
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle)), ""
    except OSError as exc:
        return [], str(exc)


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


def add_warning(
    warnings: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
    warning_code: str,
    message: str,
    source: Path | str,
    blocking_warning: bool,
    severity: str | None = None,
) -> None:
    warnings.append(
        warning_row(
            run_id=args.run_id,
            warning_code=warning_code,
            severity=severity or ("error" if blocking_warning else "warning"),
            message=message,
            source=source,
            blocking_warning=blocking_warning,
        )
    )


def blocking_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in warnings if as_bool(row.get("blocking_warning")) is True]


def preserve_source_warnings(args: argparse.Namespace, source_rows: list[dict[str, str]], source_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in source_rows:
        rows.append(
            {
                "run_id": args.run_id,
                "warning_code": f"source_{row.get('warning_code', 'warning')}",
                "severity": row.get("severity", "warning"),
                "message": row.get("message", ""),
                "source": row.get("source") or str(source_path),
                "blocking_warning": as_bool(row.get("blocking_warning")) is True,
            }
        )
    return rows


def default_output_dir(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / str(args.run_id)


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "manifest": output_dir / OUTPUT_MANIFEST,
        "report": output_dir / OUTPUT_REPORT,
        "main": output_dir / OUTPUT_MAIN_CSV,
        "checklist": output_dir / OUTPUT_CHECKLIST_CSV,
        "warnings": output_dir / OUTPUT_WARNINGS_CSV,
    }


def ensure_outputs_writable(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)


def resolve_artifact_path(value: Any, source_dir: Path) -> Path | None:
    if value in ("", None):
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    candidate = source_dir / path
    if candidate.exists():
        return candidate
    return BASE_DIR / path


def nested_get(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def canonical_registry_valid(registry: dict[str, Any]) -> bool:
    return (
        registry.get("candidate_id") == EXPECTED_CANDIDATE_ID
        and registry.get("symbol") == EXPECTED_SYMBOL
        and registry.get("timeframe") == EXPECTED_TIMEFRAME
        and registry.get("direction") == EXPECTED_DIRECTION
        and registry.get("spread_unit") == EXPECTED_SPREAD_UNIT
        and close_float(registry.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS)
    )


def source_value(shadow_manifest: dict[str, Any], review_packet: dict[str, Any], field: str) -> Any:
    packet_signal = review_packet.get("signal_evidence") if isinstance(review_packet.get("signal_evidence"), dict) else {}
    packet_price = review_packet.get("price_preview") if isinstance(review_packet.get("price_preview"), dict) else {}
    return (
        shadow_manifest.get(field)
        if shadow_manifest.get(field) not in ("", None)
        else packet_signal.get(field)
        if packet_signal.get(field) not in ("", None)
        else packet_price.get(field)
        if packet_price.get(field) not in ("", None)
        else review_packet.get(field)
    )


def load_optional_source_artifacts(shadow_manifest: dict[str, Any], shadow_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    cycle_manifest: dict[str, Any] = {}
    child_manifest: dict[str, Any] = {}
    cycle_path = resolve_artifact_path(shadow_manifest.get("cycle_manifest_path"), shadow_dir)
    child_path = resolve_artifact_path(shadow_manifest.get("child_dry_run_manifest_path"), shadow_dir)
    if cycle_path is not None:
        cycle_manifest, _ = read_json(cycle_path)
    if child_path is not None:
        child_manifest, _ = read_json(child_path)
    return cycle_manifest, child_manifest


def detect_source_nature(
    review_packet: dict[str, Any],
    shadow_manifest: dict[str, Any],
    cycle_manifest: dict[str, Any],
    child_manifest: dict[str, Any],
    shadow_status: str,
) -> str:
    sources = [review_packet, shadow_manifest, cycle_manifest, child_manifest]
    fixture_markers = (
        "source_mode",
        "fixture_not_live_market_data",
        "fixture_not_actionable",
        "historical_or_synthetic_observation_only",
    )
    for source in sources:
        if not source:
            continue
        if source.get("source_mode") == "synthetic_fixture":
            return "synthetic_fixture"
        if any(source.get(marker) is True for marker in fixture_markers[1:]):
            return "synthetic_fixture"
    if shadow_status == "shadow_signal_detected":
        return "live_data_shadow_signal"
    return "not_applicable"


def boundary_flags_ok(shadow_manifest: dict[str, Any], evidence_rows: list[dict[str, str]]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for field in NO_ORDER_TRUE_FIELDS:
        value = shadow_manifest.get(field)
        if as_bool(value) is not True:
            failures.append(field)
    if as_bool(shadow_manifest.get("manual_review_required")) is not True:
        failures.append("manual_review_required")
    if as_bool(shadow_manifest.get("order_execution_allowed")) is not False:
        failures.append("order_execution_allowed")
    if as_bool(shadow_manifest.get("order_request_construction_allowed")) is not False:
        failures.append("order_request_construction_allowed")
    if as_bool(shadow_manifest.get("demo_broker_approval_performed")) is not False:
        failures.append("demo_broker_approval_performed")
    if evidence_rows:
        first = evidence_rows[0]
        for field in NO_ORDER_TRUE_FIELDS:
            if field in first and as_bool(first.get(field)) is not True:
                failures.append(f"evidence_{field}")
    return not failures, failures


def signal_evidence_ok(values: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if values.get("symbol") != EXPECTED_SYMBOL:
        failures.append("symbol")
    if values.get("timeframe") != EXPECTED_TIMEFRAME:
        failures.append("timeframe")
    if values.get("direction") != EXPECTED_DIRECTION:
        failures.append("direction")
    if values.get("session_observed") != EXPECTED_SESSION:
        failures.append("session_observed")
    if values.get("spread_unit") != EXPECTED_SPREAD_UNIT:
        failures.append("spread_unit")
    if not close_float(values.get("max_spread_points"), EXPECTED_MAX_SPREAD_POINTS):
        failures.append("max_spread_points")
    spread = safe_float(values.get("spread"))
    if spread is None or spread > EXPECTED_MAX_SPREAD_POINTS:
        failures.append("spread")
    if values.get("close_to_ma_fast_atr_20_bucket") != EXPECTED_CLOSE_BUCKET:
        failures.append("close_to_ma_fast_atr_20_bucket")
    if values.get("tick_volume_percentile_100_bucket") != EXPECTED_VOLUME_BUCKET:
        failures.append("tick_volume_percentile_100_bucket")
    block_count = safe_int(values.get("block_reason_count"))
    if block_count not in {0, None}:
        failures.append("block_reason_count")
    return not failures, failures


def price_preview_ok(values: dict[str, Any]) -> tuple[bool, list[str], float | None, float | None]:
    failures: list[str] = []
    close = safe_float(values.get("close"))
    atr_20 = safe_float(values.get("atr_20"))
    entry = safe_float(values.get("entry_reference_price"))
    tp_price = safe_float(values.get("tp_price_preview"))
    sl_price = safe_float(values.get("sl_price_preview"))
    for name, number in (
        ("close", close),
        ("atr_20", atr_20),
        ("entry_reference_price", entry),
        ("tp_price_preview", tp_price),
        ("sl_price_preview", sl_price),
    ):
        if number is None or number <= 0:
            failures.append(name)
    tp_distance_atr: float | None = None
    sl_distance_atr: float | None = None
    if not failures and atr_20 is not None and entry is not None and tp_price is not None and sl_price is not None:
        if not tp_price < entry:
            failures.append("short_tp_below_entry")
        if not sl_price > entry:
            failures.append("short_sl_above_entry")
        tp_distance_atr = (entry - tp_price) / atr_20
        sl_distance_atr = (sl_price - entry) / atr_20
        if abs(tp_distance_atr - EXPECTED_TP_ATR) > 0.02:
            failures.append("tp_distance_atr")
        if abs(sl_distance_atr - EXPECTED_SL_ATR) > 0.02:
            failures.append("sl_distance_atr")
    return not failures, failures, tp_distance_atr, sl_distance_atr


def recommended_next_step(review_status: str) -> str:
    if review_status == "would_signal_review_fixture_only":
        return "wait_for_live_shadow_signal_or_continue_no_order_monitoring"
    if review_status == "would_signal_review_available_no_order":
        return "build_fixed_candidate_demo_order_shadow_plan"
    if review_status == "hold_no_would_signal_to_review":
        return "monitor_next_feature_row_or_run_shadow_again_later"
    if review_status == "hold_source_nature_unclear":
        return "inspect_shadow_source_nature_before_next_step"
    return "fix_would_signal_review_blocker"


def review_values(
    *,
    registry: dict[str, Any],
    shadow_manifest: dict[str, Any],
    review_packet: dict[str, Any],
    source_nature: str,
    tp_distance_atr: float | None,
    sl_distance_atr: float | None,
    review_status: str,
) -> dict[str, Any]:
    return {
        "review_status": review_status,
        "source_nature": source_nature,
        "shadow_status": shadow_manifest.get("shadow_status") or review_packet.get("shadow_status", ""),
        "shadow_decision_label": shadow_manifest.get("shadow_decision_label")
        or nested_get(review_packet, "signal_evidence", "decision_label")
        or "",
        "candidate_id": registry.get("candidate_id", EXPECTED_CANDIDATE_ID),
        "symbol": registry.get("symbol", EXPECTED_SYMBOL),
        "timeframe": registry.get("timeframe", EXPECTED_TIMEFRAME),
        "direction": registry.get("direction", EXPECTED_DIRECTION),
        "time_server": source_value(shadow_manifest, review_packet, "time_server"),
        "session_observed": source_value(shadow_manifest, review_packet, "session_observed"),
        "spread": source_value(shadow_manifest, review_packet, "spread"),
        "spread_unit": source_value(shadow_manifest, review_packet, "spread_unit"),
        "max_spread_points": source_value(shadow_manifest, review_packet, "max_spread_points"),
        "close": source_value(shadow_manifest, review_packet, "close"),
        "atr_20": source_value(shadow_manifest, review_packet, "atr_20"),
        "entry_reference_price": source_value(shadow_manifest, review_packet, "entry_reference_price"),
        "tp_price_preview": source_value(shadow_manifest, review_packet, "tp_price_preview"),
        "sl_price_preview": source_value(shadow_manifest, review_packet, "sl_price_preview"),
        "tp_distance_atr": tp_distance_atr,
        "sl_distance_atr": sl_distance_atr,
        "close_to_ma_fast_atr_20_bucket": source_value(shadow_manifest, review_packet, "close_to_ma_fast_atr_20_bucket"),
        "tick_volume_percentile_100_bucket": source_value(shadow_manifest, review_packet, "tick_volume_percentile_100_bucket"),
        "manual_review_required": as_bool(shadow_manifest.get("manual_review_required")) is True
        or as_bool(review_packet.get("manual_review_required")) is True,
        "actionable_signal": False,
        "order_execution_allowed": as_bool(shadow_manifest.get("order_execution_allowed")) is True,
        "order_request_construction_allowed": as_bool(shadow_manifest.get("order_request_construction_allowed")) is True,
        "demo_broker_approval_performed": as_bool(shadow_manifest.get("demo_broker_approval_performed")) is True,
        "recommended_next_step": recommended_next_step(review_status),
    }


def checklist_row(
    *,
    run_id: str,
    check_area: str,
    check_name: str,
    passed: bool,
    observed_value: Any,
    expected_value: Any,
    blocking_if_failed: bool,
    evidence_source: Path | str,
    caveat: str,
    warning_code: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "check_area": check_area,
        "check_name": check_name,
        "check_status": "passed" if passed else "failed",
        "observed_value": observed_value,
        "expected_value": expected_value,
        "blocking_if_failed": blocking_if_failed,
        "evidence_source": str(evidence_source),
        "caveat": caveat,
        "warning_code": "" if passed else warning_code,
    }


def build_checklist(
    *,
    args: argparse.Namespace,
    registry_ok: bool,
    shadow_status_ok: bool,
    no_order_ok: bool,
    no_order_failures: list[str],
    signal_ok: bool,
    signal_failures: list[str],
    price_ok: bool,
    price_failures: list[str],
    source_nature: str,
    values: dict[str, Any],
) -> list[dict[str, Any]]:
    shadow_dir = Path(args.shadow_signal_dir)
    return [
        checklist_row(
            run_id=args.run_id,
            check_area="config",
            check_name="canonical_registry_spread15",
            passed=registry_ok,
            observed_value=f"{values.get('symbol')};{values.get('timeframe')};{values.get('spread_unit')};{values.get('max_spread_points')}",
            expected_value="GBPUSD;M15;broker_points;15.0",
            blocking_if_failed=True,
            evidence_source=args.canonical_registry,
            caveat="canonical fixed-candidate identity only",
            warning_code="canonical_registry_boundary_mismatch",
        ),
        checklist_row(
            run_id=args.run_id,
            check_area="shadow_status",
            check_name="shadow_signal_detected",
            passed=shadow_status_ok,
            observed_value=values.get("shadow_status", ""),
            expected_value="shadow_signal_detected",
            blocking_if_failed=False,
            evidence_source=shadow_dir / SHADOW_MANIFEST,
            caveat="non-signal shadows are held, not upgraded",
            warning_code="shadow_status_not_signal",
        ),
        checklist_row(
            run_id=args.run_id,
            check_area="source_nature",
            check_name="source_nature_classified",
            passed=source_nature in {"synthetic_fixture", "live_data_shadow_signal", "not_applicable"},
            observed_value=source_nature,
            expected_value="synthetic_fixture or live_data_shadow_signal",
            blocking_if_failed=True,
            evidence_source=shadow_dir,
            caveat="fixture evidence remains non-actionable",
            warning_code="source_nature_unclear",
        ),
        checklist_row(
            run_id=args.run_id,
            check_area="no_order_boundary",
            check_name="no_order_flags_safe",
            passed=no_order_ok,
            observed_value=no_order_failures,
            expected_value="all no-order flags true and allowances false",
            blocking_if_failed=True,
            evidence_source=shadow_dir / SHADOW_MANIFEST,
            caveat="review does not permit orders",
            warning_code="no_order_boundary_violation",
        ),
        checklist_row(
            run_id=args.run_id,
            check_area="signal_evidence",
            check_name="fixed_rule_buckets_and_spread",
            passed=signal_ok,
            observed_value=signal_failures,
            expected_value="Off_hours;spread<=15.0;high_tercile;mid_tercile",
            blocking_if_failed=True,
            evidence_source=shadow_dir / SHADOW_REVIEW_PACKET,
            caveat="evidence is reviewed only, not acted on",
            warning_code="signal_evidence_mismatch",
        ),
        checklist_row(
            run_id=args.run_id,
            check_area="price_preview",
            check_name="short_tp_sl_geometry",
            passed=price_ok,
            observed_value=price_failures,
            expected_value="TP below entry at 1.5 ATR and SL above entry at 1.0 ATR",
            blocking_if_failed=True,
            evidence_source=shadow_dir / SHADOW_REVIEW_PACKET,
            caveat="preview prices are not an order request",
            warning_code="price_preview_invalid",
        ),
    ]


def determine_review_status(
    *,
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_error: str,
    shadow_manifest: dict[str, Any],
    shadow_manifest_error: str,
    review_packet: dict[str, Any],
    review_packet_error: str,
    source_nature: str,
    no_order_ok: bool,
    signal_ok: bool,
    price_ok: bool,
    warnings: list[dict[str, Any]],
) -> str:
    if registry_error == "missing" or shadow_manifest_error == "missing" or review_packet_error == "missing":
        if registry_error == "missing":
            add_warning(warnings, args=args, warning_code="canonical_registry_missing", message="Canonical registry is missing.", source=args.canonical_registry, blocking_warning=True)
        if shadow_manifest_error == "missing":
            add_warning(warnings, args=args, warning_code="shadow_manifest_missing", message="Shadow signal manifest is missing.", source=Path(args.shadow_signal_dir) / SHADOW_MANIFEST, blocking_warning=True)
        if review_packet_error == "missing":
            add_warning(warnings, args=args, warning_code="shadow_review_packet_missing", message="Shadow review packet is missing.", source=Path(args.shadow_signal_dir) / SHADOW_REVIEW_PACKET, blocking_warning=True)
        return "blocked_missing_required_artifact"
    if registry_error or shadow_manifest_error or review_packet_error:
        add_warning(warnings, args=args, warning_code="required_input_unreadable", message="A required JSON input is unreadable.", source=args.shadow_signal_dir, blocking_warning=True)
        return "blocked_unreadable_input"
    if not canonical_registry_valid(registry):
        add_warning(warnings, args=args, warning_code="canonical_registry_boundary_mismatch", message="Canonical registry does not match fixed-candidate spread15 boundaries.", source=args.canonical_registry, blocking_warning=True)
        return "blocked_by_config_boundary"

    shadow_status = str(shadow_manifest.get("shadow_status") or review_packet.get("shadow_status") or "")
    if shadow_status.startswith("blocked"):
        add_warning(warnings, args=args, warning_code="shadow_status_blocked", message=f"Shadow status is blocked: {shadow_status}", source=Path(args.shadow_signal_dir) / SHADOW_MANIFEST, blocking_warning=True)
        return "blocked_by_shadow_status"
    if shadow_status != "shadow_signal_detected":
        return "hold_no_would_signal_to_review"
    if not no_order_ok:
        add_warning(warnings, args=args, warning_code="no_order_boundary_violation", message="Shadow artifact no-order boundary flags are missing or unsafe.", source=Path(args.shadow_signal_dir) / SHADOW_MANIFEST, blocking_warning=True)
        return "blocked_by_no_order_boundary"
    if not signal_ok:
        add_warning(warnings, args=args, warning_code="signal_evidence_mismatch", message="Shadow signal evidence does not match the fixed-candidate rule.", source=Path(args.shadow_signal_dir) / SHADOW_REVIEW_PACKET, blocking_warning=True)
        return "blocked_by_signal_evidence"
    if not price_ok:
        add_warning(warnings, args=args, warning_code="price_preview_invalid", message="Price preview does not match short TP/SL geometry.", source=Path(args.shadow_signal_dir) / SHADOW_REVIEW_PACKET, blocking_warning=True)
        return "blocked_by_price_preview"
    if source_nature == "synthetic_fixture":
        return "would_signal_review_fixture_only"
    if source_nature == "live_data_shadow_signal":
        return "would_signal_review_available_no_order"
    add_warning(warnings, args=args, warning_code="source_nature_unclear", message="Shadow signal source nature cannot be determined.", source=args.shadow_signal_dir, blocking_warning=True)
    return "hold_source_nature_unclear"


def row_from_values(args: argparse.Namespace, values: dict[str, Any]) -> dict[str, Any]:
    return {"run_id": args.run_id, **values}


def manifest_payload(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    values: dict[str, Any],
    warnings: list[dict[str, Any]],
    checklist_rows: list[dict[str, Any]],
    source_flags: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "shadow_signal_dir": str(args.shadow_signal_dir),
        "canonical_registry_path": str(args.canonical_registry),
        **values,
        **source_flags,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_db_query_performed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "checklist_row_count": len(checklist_rows),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings(warnings)),
    }


def write_report(path: Path, *, args: argparse.Namespace, values: dict[str, Any], warnings: list[dict[str, Any]]) -> None:
    source_nature = values.get("source_nature", "")
    lines = [
        "# Fixed Candidate Demo Would-Signal Review",
        "",
        "Artifact-only would-signal review. It reads local shadow artifacts and does not run market, database, or child workflows.",
        f"Source nature: `{source_nature}`.",
    ]
    if source_nature == "synthetic_fixture":
        lines.append("This source is a synthetic fixture: it is non-actionable and not live market data.")
    if source_nature == "live_data_shadow_signal":
        lines.append("This source is a live-data shadow artifact, but no order approval is given.")
    lines.extend(
        [
            "No MT5, broker, API, account, or symbol query was performed.",
            "No database query or mutation was performed.",
            "No order execution was performed.",
            "No broker order request was constructed.",
            "No order_check or order_calc call was performed.",
            "No scheduler, loop, or background task was added.",
            "",
            "## Signal Evidence Summary",
            "",
            f"- shadow_status: `{values.get('shadow_status', '')}`",
            f"- shadow_decision_label: `{values.get('shadow_decision_label', '')}`",
            f"- time_server: `{values.get('time_server', '')}`",
            f"- session_observed: `{values.get('session_observed', '')}`",
            f"- spread: `{values.get('spread', '')}` `{values.get('spread_unit', '')}`",
            f"- close_to_ma_fast_atr_20_bucket: `{values.get('close_to_ma_fast_atr_20_bucket', '')}`",
            f"- tick_volume_percentile_100_bucket: `{values.get('tick_volume_percentile_100_bucket', '')}`",
            "",
            "## Price Preview Summary",
            "",
            f"- entry_reference_price: `{values.get('entry_reference_price', '')}`",
            f"- tp_price_preview: `{values.get('tp_price_preview', '')}`",
            f"- sl_price_preview: `{values.get('sl_price_preview', '')}`",
            f"- tp_distance_atr: `{values.get('tp_distance_atr', '')}`",
            f"- sl_distance_atr: `{values.get('sl_distance_atr', '')}`",
            "Preview prices are reviewed as artifact fields only and are not a broker request.",
            "",
            "## No-Order Boundary Summary",
            "",
            "- actionable_signal: `false`",
            "- order_execution_allowed: `false`",
            "- order_request_construction_allowed: `false`",
            "- demo_broker_approval_performed: `false`",
            "- no_order_execution_performed: `true`",
            "- no_order_request_constructed: `true`",
            "",
            "## Review Status",
            "",
            f"`{values.get('review_status', '')}`",
            "",
            "## Recommended Next Step",
            "",
            f"`{values.get('recommended_next_step', '')}`",
            "",
            "## Warnings",
            "",
        ]
    )
    if warnings:
        lines.extend(f"- {row['warning_code']}: {row['message']}" for row in warnings)
    else:
        lines.append("- none")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = default_output_dir(args)
    paths = output_paths(output_dir)
    ensure_outputs_writable(paths, bool(args.overwrite))

    shadow_dir = Path(args.shadow_signal_dir)
    registry, registry_error = read_json(Path(args.canonical_registry))
    shadow_manifest, shadow_manifest_error = read_json(shadow_dir / SHADOW_MANIFEST)
    review_packet, review_packet_error = read_json(shadow_dir / SHADOW_REVIEW_PACKET)
    evidence_rows, _ = read_csv_rows(shadow_dir / SHADOW_NO_ORDER_EVIDENCE_CSV)
    source_warning_rows, _ = read_csv_rows(shadow_dir / SHADOW_WARNINGS_CSV)
    warnings = preserve_source_warnings(args, source_warning_rows, shadow_dir / SHADOW_WARNINGS_CSV)

    cycle_manifest, child_manifest = load_optional_source_artifacts(shadow_manifest, shadow_dir)
    shadow_status = str(shadow_manifest.get("shadow_status") or review_packet.get("shadow_status") or "")
    source_nature = detect_source_nature(review_packet, shadow_manifest, cycle_manifest, child_manifest, shadow_status)

    no_order_ok, no_order_failures = boundary_flags_ok(shadow_manifest, evidence_rows)
    preliminary_values = {
        "symbol": registry.get("symbol", source_value(shadow_manifest, review_packet, "symbol")),
        "timeframe": registry.get("timeframe", source_value(shadow_manifest, review_packet, "timeframe")),
        "direction": registry.get("direction", source_value(shadow_manifest, review_packet, "direction")),
        "session_observed": source_value(shadow_manifest, review_packet, "session_observed"),
        "spread": source_value(shadow_manifest, review_packet, "spread"),
        "spread_unit": source_value(shadow_manifest, review_packet, "spread_unit"),
        "max_spread_points": source_value(shadow_manifest, review_packet, "max_spread_points"),
        "close_to_ma_fast_atr_20_bucket": source_value(shadow_manifest, review_packet, "close_to_ma_fast_atr_20_bucket"),
        "tick_volume_percentile_100_bucket": source_value(shadow_manifest, review_packet, "tick_volume_percentile_100_bucket"),
        "block_reason_count": source_value(shadow_manifest, review_packet, "block_reason_count"),
        "close": source_value(shadow_manifest, review_packet, "close"),
        "atr_20": source_value(shadow_manifest, review_packet, "atr_20"),
        "entry_reference_price": source_value(shadow_manifest, review_packet, "entry_reference_price"),
        "tp_price_preview": source_value(shadow_manifest, review_packet, "tp_price_preview"),
        "sl_price_preview": source_value(shadow_manifest, review_packet, "sl_price_preview"),
    }
    signal_ok, signal_failures = signal_evidence_ok(preliminary_values)
    price_ok, price_failures, tp_distance_atr, sl_distance_atr = price_preview_ok(preliminary_values)

    review_status = determine_review_status(
        args=args,
        registry=registry,
        registry_error=registry_error,
        shadow_manifest=shadow_manifest,
        shadow_manifest_error=shadow_manifest_error,
        review_packet=review_packet,
        review_packet_error=review_packet_error,
        source_nature=source_nature,
        no_order_ok=no_order_ok,
        signal_ok=signal_ok,
        price_ok=price_ok,
        warnings=warnings,
    )
    values = review_values(
        registry=registry,
        shadow_manifest=shadow_manifest,
        review_packet=review_packet,
        source_nature=source_nature,
        tp_distance_atr=tp_distance_atr,
        sl_distance_atr=sl_distance_atr,
        review_status=review_status,
    )
    checklist_rows = build_checklist(
        args=args,
        registry_ok=canonical_registry_valid(registry),
        shadow_status_ok=shadow_status == "shadow_signal_detected",
        no_order_ok=no_order_ok,
        no_order_failures=no_order_failures,
        signal_ok=signal_ok,
        signal_failures=signal_failures,
        price_ok=price_ok,
        price_failures=price_failures,
        source_nature=source_nature,
        values=values,
    )
    source_flags = {
        "fixture_not_live_market_data": any(source.get("fixture_not_live_market_data") is True for source in (review_packet, shadow_manifest, cycle_manifest, child_manifest)),
        "fixture_not_actionable": any(source.get("fixture_not_actionable") is True for source in (review_packet, shadow_manifest, cycle_manifest, child_manifest)),
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_trading_decision_performed": True,
    }

    write_csv(paths["main"], [row_from_values(args, values)], MAIN_FIELDNAMES)
    write_csv(paths["checklist"], checklist_rows, CHECKLIST_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_json(paths["manifest"], manifest_payload(args=args, output_dir=output_dir, values=values, warnings=warnings, checklist_rows=checklist_rows, source_flags=source_flags))
    write_report(paths["report"], args=args, values=values, warnings=warnings)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an artifact-only review for one fixed-candidate demo would-signal shadow artifact.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--shadow-signal-dir", type=Path, default=DEFAULT_SHADOW_SIGNAL_DIR)
    parser.add_argument("--canonical-registry", type=Path, default=DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        build_outputs(args)
    except Exception as exc:
        print(f"Fixed-candidate demo would-signal review failed: {exc}")
        return 1
    print("Fixed-candidate demo would-signal review complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
