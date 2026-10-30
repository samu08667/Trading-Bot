from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_would_signal_review as review


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def canonical_registry(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
    }
    payload.update(overrides)
    return payload


def no_order_flags(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_trading_decision_performed": True,
    }
    payload.update(overrides)
    return payload


def write_shadow_artifacts(
    root: Path,
    *,
    fixture_source: bool = True,
    shadow_status: str = "shadow_signal_detected",
    manifest_overrides: dict[str, object] | None = None,
    packet_overrides: dict[str, object] | None = None,
    signal_overrides: dict[str, object] | None = None,
    price_overrides: dict[str, object] | None = None,
    write_manifest: bool = True,
    write_packet: bool = True,
) -> Path:
    signal_evidence: dict[str, object] = {
        "decision_label": "would_signal",
        "dry_run_status": "demo_no_order_dry_run_would_signal",
        "session_observed": "Off_hours",
        "spread": 3.0,
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "close_to_ma_fast_atr_20_bucket": "high_tercile",
        "tick_volume_percentile_100_bucket": "mid_tercile",
        "skip_reason_count": 0,
        "block_reason_count": 0,
    }
    signal_evidence.update(signal_overrides or {})
    price_preview: dict[str, object] = {
        "close": 1.34600,
        "atr_20": 0.00042,
        "entry_reference_price": 1.34600,
        "tp_price_preview": 1.34537,
        "sl_price_preview": 1.34642,
    }
    price_preview.update(price_overrides or {})
    child_manifest_path = root / "children" / "dry_run" / "fixed_candidate_demo_no_order_dry_run_manifest.json"
    cycle_manifest_path = root / "cycle_manifest.json"

    manifest: dict[str, object] = {
        "shadow_status": shadow_status,
        "shadow_decision_label": "shadow_signal_detected" if shadow_status == "shadow_signal_detected" else "no_signal",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "time_server": "2026-06-01 02:00:00",
        "manual_review_required": shadow_status == "shadow_signal_detected",
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "demo_broker_approval_performed": False,
        "session_observed": signal_evidence["session_observed"],
        "spread": signal_evidence["spread"],
        "spread_unit": signal_evidence["spread_unit"],
        "max_spread_points": signal_evidence["max_spread_points"],
        "close": price_preview["close"],
        "atr_20": price_preview["atr_20"],
        "entry_reference_price": price_preview["entry_reference_price"],
        "tp_price_preview": price_preview["tp_price_preview"],
        "sl_price_preview": price_preview["sl_price_preview"],
        "close_to_ma_fast_atr_20_bucket": signal_evidence["close_to_ma_fast_atr_20_bucket"],
        "tick_volume_percentile_100_bucket": signal_evidence["tick_volume_percentile_100_bucket"],
        "cycle_manifest_path": str(cycle_manifest_path),
        "child_dry_run_manifest_path": str(child_manifest_path),
        **no_order_flags(),
    }
    manifest.update(manifest_overrides or {})
    packet: dict[str, object] = {
        "run_id": "source_shadow",
        "shadow_status": shadow_status,
        "manual_review_required": shadow_status == "shadow_signal_detected",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "time_server": "2026-06-01 02:00:00",
        "signal_evidence": signal_evidence,
        "price_preview": price_preview,
        "no_order_boundary": {
            "cycle_no_order_boundary_confirmed": True,
            "no_order_execution_performed": True,
            "no_order_request_constructed": True,
            "no_demo_broker_approval_performed": True,
        },
    }
    packet.update(packet_overrides or {})
    if fixture_source:
        write_json(
            cycle_manifest_path,
            {
                "source_mode": "synthetic_fixture",
                "fixture_not_live_market_data": True,
                "fixture_not_actionable": True,
                "historical_or_synthetic_observation_only": True,
            },
        )
        write_json(
            child_manifest_path,
            {
                "source_mode": "synthetic_fixture",
                "fixture_not_live_market_data": True,
                "fixture_not_actionable": True,
                "historical_or_synthetic_observation_only": True,
            },
        )
    if write_manifest:
        write_json(root / review.SHADOW_MANIFEST, manifest)
    if write_packet:
        write_json(root / review.SHADOW_REVIEW_PACKET, packet)
    write_csv(root / review.SHADOW_NO_ORDER_EVIDENCE_CSV, [{**no_order_flags(), "run_id": "source"}], ["run_id", *review.NO_ORDER_TRUE_FIELDS])
    write_csv(root / review.SHADOW_WARNINGS_CSV, [], review.WARNING_FIELDNAMES)
    write_csv(root / review.SHADOW_MAIN_CSV, [], review.MAIN_FIELDNAMES)
    (root / review.SHADOW_REPORT).write_text("source report\n", encoding="utf-8")
    return root


def make_args(
    tmp_path: Path,
    *,
    registry_payload: dict[str, object] | None = None,
    shadow_dir: Path | None = None,
) -> object:
    registry_path = write_json(tmp_path / "registry.json", registry_payload or canonical_registry())
    argv = [
        "--run-id",
        "unit_would_signal_review",
        "--shadow-signal-dir",
        str(shadow_dir or write_shadow_artifacts(tmp_path / "shadow")),
        "--canonical-registry",
        str(registry_path),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    return review.build_parser().parse_args(argv)


def build_valid_fixture_review(tmp_path: Path) -> dict[str, Path]:
    return review.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        review.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = build_valid_fixture_review(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_shadow_signal_detected_produces_fixture_only_review(tmp_path: Path) -> None:
    outputs = build_valid_fixture_review(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "would_signal_review_fixture_only"
    assert manifest["source_nature"] == "synthetic_fixture"
    assert manifest["shadow_status"] == "shadow_signal_detected"


def test_fixture_review_has_actionable_signal_false(tmp_path: Path) -> None:
    outputs = build_valid_fixture_review(tmp_path)
    manifest = read_json(outputs["manifest"])
    rows = read_csv(outputs["main"])

    assert manifest["actionable_signal"] is False
    assert rows[0]["actionable_signal"] == "false"


def test_fixture_review_recommended_next_step_waits_for_live_shadow(tmp_path: Path) -> None:
    outputs = build_valid_fixture_review(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["recommended_next_step"] == "wait_for_live_shadow_signal_or_continue_no_order_monitoring"


def test_live_data_like_shadow_signal_produces_available_no_order(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(tmp_path / "shadow", fixture_source=False)
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["source_nature"] == "live_data_shadow_signal"
    assert manifest["review_status"] == "would_signal_review_available_no_order"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_demo_order_shadow_plan"


def test_live_data_like_review_still_non_actionable_and_manual_review_required(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(tmp_path / "shadow", fixture_source=False)
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["actionable_signal"] is False
    assert manifest["manual_review_required"] is True
    assert manifest["order_execution_allowed"] is False
    assert manifest["order_request_construction_allowed"] is False


def test_shadow_no_signal_holds_no_would_signal_to_review(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(tmp_path / "shadow", fixture_source=False, shadow_status="shadow_no_signal")
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "hold_no_would_signal_to_review"


def test_missing_manifest_blocks(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(tmp_path / "shadow", write_manifest=False)
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_missing_required_artifact"


def test_missing_review_packet_blocks(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(tmp_path / "shadow", write_packet=False)
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_missing_required_artifact"


def test_missing_no_order_flag_blocks(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(tmp_path / "shadow", manifest_overrides={"no_order_check_called": None})
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_by_no_order_boundary"


def test_unsafe_no_order_flag_false_blocks(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(tmp_path / "shadow", manifest_overrides={"no_order_request_constructed": False})
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_by_no_order_boundary"


def test_wrong_session_blocks_signal_evidence(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(tmp_path / "shadow", signal_overrides={"session_observed": "London"})
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_by_signal_evidence"


def test_wrong_bucket_blocks_signal_evidence(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(
        tmp_path / "shadow",
        signal_overrides={"close_to_ma_fast_atr_20_bucket": "low_tercile"},
    )
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_by_signal_evidence"


def test_spread_above_15_blocks_signal_evidence(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(tmp_path / "shadow", signal_overrides={"spread": 20.0})
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_by_signal_evidence"


def test_bad_short_tp_sl_geometry_blocks_price_preview(tmp_path: Path) -> None:
    shadow_dir = write_shadow_artifacts(tmp_path / "shadow", price_overrides={"tp_price_preview": 1.34650})
    outputs = review.build_outputs(make_args(tmp_path, shadow_dir=shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_by_price_preview"


def test_noncanonical_registry_blocks_config_boundary(tmp_path: Path) -> None:
    outputs = review.build_outputs(make_args(tmp_path, registry_payload=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["review_status"] == "blocked_by_config_boundary"


def test_report_contains_fixture_non_actionable_disclaimer(tmp_path: Path) -> None:
    outputs = build_valid_fixture_review(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "synthetic fixture" in report
    assert "non-actionable" in report
    assert "not live market data" in report


def test_report_contains_no_order_db_mt5_caveats(tmp_path: Path) -> None:
    outputs = build_valid_fixture_review(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5" in report
    assert "No database query or mutation" in report
    assert "No order execution" in report
    assert "No broker order request" in report
    assert "No order_check or order_calc" in report


def test_static_source_has_no_forbidden_call_signatures() -> None:
    source = Path("scripts/build_fixed_candidate_demo_would_signal_review.py").read_text(encoding="utf-8")
    forbidden = [
        "MetaTrader5",
        "mt5.initialize",
        "order_send(",
        "order_check(",
        "order_calc_margin(",
        "order_calc_profit(",
        "positions_get(",
        "orders_get(",
        "history_orders_get(",
        "history_deals_get(",
    ]

    for token in forbidden:
        assert token not in source


def test_static_source_has_no_scheduler_loop_background_markers() -> None:
    source = Path("scripts/build_fixed_candidate_demo_would_signal_review.py").read_text(encoding="utf-8")
    forbidden = [
        "Task Scheduler",
        "schtasks",
        "while True",
        "APScheduler",
        "threading.Timer",
    ]

    for token in forbidden:
        assert token not in source


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path) -> None:
    outputs = build_valid_fixture_review(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_db_query_performed"] is True
    assert manifest["no_order_execution_performed"] is True
