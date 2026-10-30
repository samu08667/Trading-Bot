from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from scripts import compare_fixed_candidate_numeric_tercile_threshold_artifacts as comparison


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def old_threshold_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "calibration_scope": {"symbol": "GBPUSD", "timeframe": "M15"},
        "features": {
            "close_to_ma_fast_atr_20": {
                "lower_tercile_boundary": -0.45,
                "upper_tercile_boundary": 0.60,
                "non_null_count": 8000,
                "required_bucket_for_candidate": "high_tercile",
            },
            "tick_volume_percentile_100": {
                "lower_tercile_boundary": 0.15,
                "upper_tercile_boundary": 0.37,
                "non_null_count": 7900,
                "required_bucket_for_candidate": "mid_tercile",
            },
        },
    }
    payload.update(overrides)
    return payload


def new_threshold_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "threshold_lineage": "train_only",
        "calibration_scope": "train_window_only",
        "train_end_time": "2024-12-31 23:59:59",
        "required_conditions": {
            "close_to_ma_fast_atr_20": "high_tercile",
            "tick_volume_percentile_100": "mid_tercile",
        },
        "features": {
            "close_to_ma_fast_atr_20": {
                "low_mid_cutoff": -0.43,
                "mid_high_cutoff": 0.60,
                "non_null_count": 5500,
            },
            "tick_volume_percentile_100": {
                "low_mid_cutoff": 0.14,
                "mid_high_cutoff": 0.37,
                "non_null_count": 5490,
            },
        },
    }
    payload.update(overrides)
    return payload


def make_args(
    tmp_path: Path,
    *,
    old_payload: dict[str, object] | None = None,
    new_payload: dict[str, object] | None = None,
    output_dir: Path | None = None,
    overwrite: bool = True,
) -> object:
    old_path = write_json(tmp_path / "old.json", old_payload or old_threshold_payload())
    new_path = write_json(tmp_path / "new.json", new_payload or new_threshold_payload())
    args = [
        "--run-id",
        "unit_threshold_comparison",
        "--old-thresholds-json",
        str(old_path),
        "--new-thresholds-json",
        str(new_path),
        "--output-dir",
        str(output_dir or tmp_path / "out"),
    ]
    if overwrite:
        args.append("--overwrite")
    return comparison.build_parser().parse_args(args)


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        comparison.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_outputs_are_written(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))

    assert outputs["manifest"].exists()
    assert outputs["feature_comparison"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["no_order_evidence"].exists()


def test_compares_candidate_identity_required_conditions_and_lineage(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))
    manifest = read_json(outputs["manifest"])

    assert manifest["comparison_status"] == "threshold_artifact_comparison_available"
    assert manifest["candidate_id_old"] == "gbpusd_short_h10_1_5_off_hours"
    assert manifest["candidate_id_new"] == "gbpusd_short_h10_1_5_off_hours"
    assert manifest["required_conditions_old"] == manifest["required_conditions_new"]
    assert manifest["new_threshold_lineage"] == "train_only"


def test_feature_csv_contains_absolute_and_relative_deltas(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["feature_comparison"])
    close_low = next(
        row for row in rows if row["feature_name"] == "close_to_ma_fast_atr_20" and row["boundary"] == "low_mid_cutoff"
    )

    assert float(close_low["absolute_delta"]) == pytest.approx(0.02)
    assert float(close_low["relative_delta"]) == pytest.approx(0.0444444444)
    assert close_low["drift_classification"] == "low_drift"


def test_drift_classification_boundaries() -> None:
    assert comparison.classify_drift(0.0, 0.0) == "no_drift"
    assert comparison.classify_drift(0.005, 0.50) == "low_drift"
    assert comparison.classify_drift(0.03, 0.10) == "moderate_drift"
    assert comparison.classify_drift(0.30, 0.50) == "high_drift"


def test_recommendation_changes_for_large_drift(tmp_path: Path) -> None:
    new_payload = new_threshold_payload(
        features={
            "close_to_ma_fast_atr_20": {
                "low_mid_cutoff": 10.0,
                "mid_high_cutoff": 20.0,
                "non_null_count": 5500,
            },
            "tick_volume_percentile_100": {
                "low_mid_cutoff": 0.14,
                "mid_high_cutoff": 0.37,
                "non_null_count": 5490,
            },
        }
    )
    outputs = comparison.build_outputs(make_args(tmp_path, new_payload=new_payload))
    manifest = read_json(outputs["manifest"])

    assert manifest["overall_drift_classification"] == "high_drift"
    assert manifest["recommended_next_step"] == "oos_replay_required_prior_evidence_more_suspect"


def test_candidate_mismatch_blocks_comparison_status(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path, new_payload=new_threshold_payload(candidate_id="other")))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["comparison_status"] == "threshold_artifact_comparison_blocked_input_mismatch_or_missing"
    assert any(row["warning_code"] == "candidate_id_mismatch" for row in warnings)


def test_missing_new_artifact_blocks(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    Path(args.new_thresholds_json).unlink()
    outputs = comparison.build_outputs(args)
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["comparison_status"] == "threshold_artifact_comparison_blocked_input_mismatch_or_missing"
    assert any(row["warning_code"] == "new_threshold_artifact_unreadable" for row in warnings)


def test_output_exists_without_overwrite_blocks(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    args = make_args(tmp_path, output_dir=output_dir)
    comparison.build_outputs(args)
    args.overwrite = False

    with pytest.raises(FileExistsError):
        comparison.build_outputs(args)


def test_no_order_evidence_is_written(tmp_path: Path) -> None:
    outputs = comparison.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["no_order_evidence"])
    evidence = {row["evidence_name"]: row["value"] for row in rows}

    assert evidence["no_db_read_performed"] == "true"
    assert evidence["no_mt5_import_performed"] == "true"
    assert evidence["no_order_send_called"] == "true"
    assert evidence["no_canonical_config_update_performed"] == "true"


def test_static_safety_no_db_mt5_order_broker_scheduler_calls() -> None:
    source = Path(comparison.__file__).read_text(encoding="utf-8")

    assert "sqlite3" not in source
    assert "MetaTrader5" not in source
    assert "mt5." not in source
    assert not re.search(
        r"\.(order_check|order_send|order_calc_margin|order_calc_profit|positions_get|orders_get|"
        r"history_orders_get|history_deals_get)\s*\(",
        source,
    )
    assert "subprocess" not in source
    assert not re.search(r"\b(threading|apscheduler|schedule)\b", source)
