"""Compare old and train-only fixed-candidate numeric-tercile artifacts.

This artifact-only comparison reads two threshold JSON files, normalizes the
legacy full-sample schema and the train-only schema, compares candidate identity,
required conditions, and per-feature tercile cutoffs, then writes comparison
artifacts. It does not read SQLite, import MT5, run replay/backtests, mutate
config, or touch broker/order paths.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]

DEFAULT_OLD_THRESHOLDS_JSON = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_numeric_tercile_thresholds"
    / "gbpusd_short_h10_1_5_off_hours_numeric_tercile_thresholds_v1"
    / "fixed_candidate_numeric_tercile_thresholds.json"
)
DEFAULT_NEW_THRESHOLDS_JSON = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_train_only_numeric_tercile_thresholds"
    / "gbpusd_short_h10_1_5_off_hours_train_only_numeric_tercile_thresholds_train_to_2024_12_31_v1"
    / "fixed_candidate_train_only_numeric_tercile_thresholds.json"
)
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_numeric_tercile_threshold_artifact_comparison_v1"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_numeric_tercile_threshold_artifact_comparison"

MANIFEST_FILE = "fixed_candidate_numeric_tercile_threshold_artifact_comparison_manifest.json"
FEATURE_COMPARISON_FILE = "fixed_candidate_numeric_tercile_threshold_artifact_comparison.csv"
REPORT_FILE = "fixed_candidate_numeric_tercile_threshold_artifact_comparison_report.md"
WARNINGS_FILE = "fixed_candidate_numeric_tercile_threshold_artifact_comparison_warnings.csv"
NO_ORDER_EVIDENCE_FILE = "fixed_candidate_numeric_tercile_threshold_artifact_comparison_no_order_evidence.csv"

LOW_ABSOLUTE_DRIFT_THRESHOLD = 0.01
MODERATE_ABSOLUTE_DRIFT_THRESHOLD = 0.05
LOW_RELATIVE_DRIFT_THRESHOLD = 0.05
MODERATE_RELATIVE_DRIFT_THRESHOLD = 0.20

EXPECTED_REQUIRED_CONDITIONS = {
    "close_to_ma_fast_atr_20": "high_tercile",
    "tick_volume_percentile_100": "mid_tercile",
}

OUTPUT_FILES = {
    "manifest": MANIFEST_FILE,
    "feature_comparison": FEATURE_COMPARISON_FILE,
    "report": REPORT_FILE,
    "warnings": WARNINGS_FILE,
    "no_order_evidence": NO_ORDER_EVIDENCE_FILE,
}

FEATURE_COMPARISON_FIELDS = [
    "feature_name",
    "boundary",
    "old_cutoff",
    "new_cutoff",
    "absolute_delta",
    "relative_delta",
    "drift_classification",
    "old_non_null_count",
    "new_non_null_count",
    "required_condition_old",
    "required_condition_new",
]

WARNING_FIELDS = [
    "run_id",
    "warning_code",
    "severity",
    "message",
    "source",
    "blocking_warning",
]

NO_ORDER_EVIDENCE = {
    "no_db_read_performed": True,
    "no_db_mutation_performed": True,
    "no_mt5_import_performed": True,
    "no_mt5_connection_performed": True,
    "no_broker_api_query_performed": True,
    "no_order_check_called": True,
    "no_order_send_called": True,
    "no_order_calc_margin_called": True,
    "no_order_calc_profit_called": True,
    "no_positions_get_called": True,
    "no_orders_get_called": True,
    "no_history_orders_get_called": True,
    "no_history_deals_get_called": True,
    "no_replay_or_backtest_run": True,
    "no_cost_sensitivity_run": True,
    "no_holdout_run": True,
    "no_canonical_config_update_performed": True,
    "no_child_scripts_executed": True,
    "no_trading_decision_performed": True,
}


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_object(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)
    if not isinstance(payload, dict):
        return {}, "JSON root is not an object"
    return payload, ""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


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
        "blocking_warning": blocking_warning,
    }


def output_dir_for_args(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    return DEFAULT_OUTPUT_ROOT / str(args.run_id)


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {label: output_dir / file_name for label, file_name in OUTPUT_FILES.items()}


def ensure_output_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = output_paths(output_dir)
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def get_nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def cutoff_value(feature_payload: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = safe_float(feature_payload.get(name))
        if value is not None:
            return value
    return None


def normalize_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    features_raw = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    required_conditions = payload.get("required_conditions")
    if not isinstance(required_conditions, dict):
        required_conditions = {
            feature: data.get("required_bucket_for_candidate")
            for feature, data in features_raw.items()
            if isinstance(data, dict) and data.get("required_bucket_for_candidate")
        }
    normalized_features: dict[str, dict[str, Any]] = {}
    for feature, feature_payload in features_raw.items():
        if not isinstance(feature_payload, dict):
            continue
        normalized_features[str(feature)] = {
            "low_mid_cutoff": cutoff_value(
                feature_payload,
                ("low_mid_cutoff", "lower_tercile_boundary", "lower_boundary"),
            ),
            "mid_high_cutoff": cutoff_value(
                feature_payload,
                ("mid_high_cutoff", "upper_tercile_boundary", "upper_boundary"),
            ),
            "non_null_count": int(feature_payload.get("non_null_count") or 0),
        }
    symbol = payload.get("symbol") or get_nested(payload, "calibration_scope", "symbol")
    timeframe = payload.get("timeframe") or get_nested(payload, "calibration_scope", "timeframe")
    return {
        "candidate_id": payload.get("candidate_id"),
        "symbol": symbol,
        "timeframe": timeframe,
        "required_conditions": {str(key): str(value) for key, value in required_conditions.items()},
        "features": normalized_features,
        "threshold_lineage": payload.get("threshold_lineage", ""),
        "calibration_scope": payload.get("calibration_scope", ""),
        "train_end_time": payload.get("train_end_time", ""),
    }


def relative_delta(old_value: float | None, absolute_delta: float | None) -> float | None:
    if old_value is None or absolute_delta is None:
        return None
    denominator = abs(old_value)
    if denominator <= 1e-12:
        return 0.0 if absolute_delta <= 1e-12 else None
    return absolute_delta / denominator


def classify_drift(abs_delta: float | None, rel_delta: float | None) -> str:
    if abs_delta is None:
        return "high_drift"
    if abs_delta <= 1e-12:
        return "no_drift"
    if abs_delta <= LOW_ABSOLUTE_DRIFT_THRESHOLD or (rel_delta is not None and rel_delta <= LOW_RELATIVE_DRIFT_THRESHOLD):
        return "low_drift"
    if (
        abs_delta <= MODERATE_ABSOLUTE_DRIFT_THRESHOLD
        or (rel_delta is not None and rel_delta <= MODERATE_RELATIVE_DRIFT_THRESHOLD)
    ):
        return "moderate_drift"
    return "high_drift"


def worst_drift(classes: list[str]) -> str:
    order = {"no_drift": 0, "low_drift": 1, "moderate_drift": 2, "high_drift": 3}
    if not classes:
        return "high_drift"
    return max(classes, key=lambda item: order.get(item, 99))


def recommended_next_step(overall_drift: str) -> str:
    if overall_drift in {"no_drift", "low_drift"}:
        return "proceed_to_oos_replay_with_train_only_artifact"
    return "oos_replay_required_prior_evidence_more_suspect"


def compare_features(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    old_features = old["features"]
    new_features = new["features"]
    feature_names = sorted(set(old_features) | set(new_features) | set(EXPECTED_REQUIRED_CONDITIONS))
    rows: list[dict[str, Any]] = []
    for feature in feature_names:
        old_feature = old_features.get(feature, {})
        new_feature = new_features.get(feature, {})
        for boundary in ("low_mid_cutoff", "mid_high_cutoff"):
            old_cutoff = old_feature.get(boundary)
            new_cutoff = new_feature.get(boundary)
            abs_delta = (
                abs(float(new_cutoff) - float(old_cutoff))
                if old_cutoff is not None and new_cutoff is not None
                else None
            )
            rel_delta = relative_delta(old_cutoff, abs_delta)
            drift_class = classify_drift(abs_delta, rel_delta)
            rows.append(
                {
                    "feature_name": feature,
                    "boundary": boundary,
                    "old_cutoff": old_cutoff,
                    "new_cutoff": new_cutoff,
                    "absolute_delta": abs_delta,
                    "relative_delta": rel_delta,
                    "drift_classification": drift_class,
                    "old_non_null_count": old_feature.get("non_null_count", 0),
                    "new_non_null_count": new_feature.get("non_null_count", 0),
                    "required_condition_old": old["required_conditions"].get(feature, ""),
                    "required_condition_new": new["required_conditions"].get(feature, ""),
                }
            )
    return rows


def identity_warnings(
    *,
    run_id: str,
    old: dict[str, Any],
    new: dict[str, Any],
    old_path: Path,
    new_path: Path,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for field in ("candidate_id", "symbol", "timeframe"):
        if str(old.get(field) or "") != str(new.get(field) or ""):
            warnings.append(
                warning_row(
                    run_id=run_id,
                    warning_code=f"{field}_mismatch",
                    message=f"{field} differs between artifacts.",
                    source=f"{old_path};{new_path}",
                    blocking_warning=True,
                )
            )
    old_conditions = old["required_conditions"]
    new_conditions = new["required_conditions"]
    if old_conditions != new_conditions:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="required_conditions_mismatch",
                message="Required numeric-tercile bucket conditions differ between artifacts.",
                source=f"{old_path};{new_path}",
                blocking_warning=True,
            )
        )
    if new.get("threshold_lineage") and new.get("threshold_lineage") != "train_only":
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="new_artifact_not_train_only",
                message="New threshold artifact does not declare threshold_lineage=train_only.",
                source=new_path,
                blocking_warning=True,
            )
        )
    return warnings


def load_artifacts(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    run_id = str(args.run_id)
    old_path = Path(args.old_thresholds_json)
    new_path = Path(args.new_thresholds_json)
    old_payload, old_error = read_json_object(old_path)
    new_payload, new_error = read_json_object(new_path)
    warnings: list[dict[str, Any]] = []
    if old_error:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="old_threshold_artifact_unreadable",
                message=f"Old threshold artifact is missing or unreadable: {old_error}",
                source=old_path,
                blocking_warning=True,
            )
        )
    if new_error:
        warnings.append(
            warning_row(
                run_id=run_id,
                warning_code="new_threshold_artifact_unreadable",
                message=f"New train-only threshold artifact is missing or unreadable: {new_error}",
                source=new_path,
                blocking_warning=True,
            )
        )
    return old_payload, new_payload, warnings


def build_model(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any]:
    run_id = str(args.run_id)
    old_path = Path(args.old_thresholds_json)
    new_path = Path(args.new_thresholds_json)
    old_payload, new_payload, warnings = load_artifacts(args)
    old_norm = normalize_artifact(old_payload)
    new_norm = normalize_artifact(new_payload)
    if old_payload and new_payload:
        warnings.extend(
            identity_warnings(
                run_id=run_id,
                old=old_norm,
                new=new_norm,
                old_path=old_path,
                new_path=new_path,
            )
        )
    comparison_rows = compare_features(old_norm, new_norm) if old_payload and new_payload else []
    drift_classes = [str(row["drift_classification"]) for row in comparison_rows]
    overall_drift = worst_drift(drift_classes)
    blocking_warnings = [warning for warning in warnings if warning["blocking_warning"]]
    created_at = utc_now_text()
    recommendation = recommended_next_step(overall_drift)
    manifest = {
        "run_id": run_id,
        "created_at_utc": created_at,
        "comparison_status": "threshold_artifact_comparison_available"
        if not blocking_warnings
        else "threshold_artifact_comparison_blocked_input_mismatch_or_missing",
        "old_thresholds_json": str(old_path),
        "new_thresholds_json": str(new_path),
        "old_thresholds_sha256": sha256_file(old_path) if old_path.exists() else "",
        "new_thresholds_sha256": sha256_file(new_path) if new_path.exists() else "",
        "candidate_id_old": old_norm.get("candidate_id", ""),
        "candidate_id_new": new_norm.get("candidate_id", ""),
        "symbol_old": old_norm.get("symbol", ""),
        "symbol_new": new_norm.get("symbol", ""),
        "timeframe_old": old_norm.get("timeframe", ""),
        "timeframe_new": new_norm.get("timeframe", ""),
        "required_conditions_old": old_norm.get("required_conditions", {}),
        "required_conditions_new": new_norm.get("required_conditions", {}),
        "new_threshold_lineage": new_norm.get("threshold_lineage", ""),
        "new_train_end_time": new_norm.get("train_end_time", ""),
        "feature_boundary_count": len(comparison_rows),
        "overall_drift_classification": overall_drift,
        "drift_thresholds": {
            "low_absolute": LOW_ABSOLUTE_DRIFT_THRESHOLD,
            "moderate_absolute": MODERATE_ABSOLUTE_DRIFT_THRESHOLD,
            "low_relative": LOW_RELATIVE_DRIFT_THRESHOLD,
            "moderate_relative": MODERATE_RELATIVE_DRIFT_THRESHOLD,
        },
        "recommended_next_step": recommendation,
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings),
        "output_files": {label: str(path) for label, path in paths.items()},
        **NO_ORDER_EVIDENCE,
    }
    return {
        "manifest": manifest,
        "comparison_rows": comparison_rows,
        "warnings": warnings,
        "no_order_evidence": [
            {"evidence_name": key, "value": value, "note": "artifact_only_json_comparison"}
            for key, value in NO_ORDER_EVIDENCE.items()
        ],
    }


def report_text(model: dict[str, Any]) -> str:
    manifest = model["manifest"]
    rows = model["comparison_rows"]
    lines = [
        "# Fixed Candidate Numeric Tercile Threshold Artifact Comparison",
        "",
        "Artifact-only comparison of the legacy threshold artifact and the train-only threshold artifact.",
        "",
        "## Summary",
        "",
        f"- comparison_status: `{manifest['comparison_status']}`",
        f"- overall_drift_classification: `{manifest['overall_drift_classification']}`",
        f"- recommended_next_step: `{manifest['recommended_next_step']}`",
        f"- new_threshold_lineage: `{manifest['new_threshold_lineage']}`",
        f"- new_train_end_time: `{manifest['new_train_end_time']}`",
        "",
        "## Identity",
        "",
        f"- candidate_id: `{manifest['candidate_id_old']}` vs `{manifest['candidate_id_new']}`",
        f"- symbol: `{manifest['symbol_old']}` vs `{manifest['symbol_new']}`",
        f"- timeframe: `{manifest['timeframe_old']}` vs `{manifest['timeframe_new']}`",
        "",
        "## Boundary Comparison",
        "",
        "| Feature | Boundary | Old Cutoff | New Cutoff | Abs Delta | Rel Delta | Drift |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["feature_name"]),
                    str(row["boundary"]),
                    str(row["old_cutoff"]),
                    str(row["new_cutoff"]),
                    str(row["absolute_delta"]),
                    str(row["relative_delta"]),
                    str(row["drift_classification"]),
                ]
            )
            + " |"
        )
    if not rows:
        lines.append("| none | none |  |  |  |  | high_drift |")
    lines.extend(
        [
            "",
            "## Safety Boundary",
            "",
            "- No DB read or mutation was performed.",
            "- No MT5, broker/API, order_check, order_send, replay, backtest, cost sensitivity, holdout, child script, or canonical config update was performed.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for_args(args)
    paths = ensure_output_writable(output_dir, bool(args.overwrite))
    model = build_model(args, paths)
    write_csv(paths["feature_comparison"], model["comparison_rows"], FEATURE_COMPARISON_FIELDS)
    write_csv(paths["warnings"], model["warnings"], WARNING_FIELDS)
    write_csv(paths["no_order_evidence"], model["no_order_evidence"], ["evidence_name", "value", "note"])
    paths["report"].write_text(report_text(model), encoding="utf-8")
    write_json(paths["manifest"], model["manifest"])
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare fixed-candidate numeric-tercile threshold artifacts without DB, replay, or broker access."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--old-thresholds-json", type=Path, default=DEFAULT_OLD_THRESHOLDS_JSON)
    parser.add_argument("--new-thresholds-json", type=Path, default=DEFAULT_NEW_THRESHOLDS_JSON)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = build_outputs(args)
    except (FileExistsError, OSError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Fixed-candidate threshold artifact comparison failed: {exc}")
        return 1
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    print("Fixed-candidate threshold artifact comparison complete.")
    print(f"comparison_status: {manifest['comparison_status']}")
    print(f"overall_drift_classification: {manifest['overall_drift_classification']}")
    print(f"recommended_next_step: {manifest['recommended_next_step']}")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0 if manifest["comparison_status"] == "threshold_artifact_comparison_available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
