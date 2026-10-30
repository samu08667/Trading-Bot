from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_order_shadow_plan as plan


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


def base_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "review_status": "would_signal_review_fixture_only",
        "source_nature": "synthetic_fixture",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "time_server": "2026-06-01 02:00:00",
        "session_observed": "Off_hours",
        "spread": 3.0,
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "close": 1.346,
        "atr_20": 0.00042,
        "entry_reference_price": 1.346,
        "tp_price_preview": 1.34537,
        "sl_price_preview": 1.34642,
        "close_to_ma_fast_atr_20_bucket": "high_tercile",
        "tick_volume_percentile_100_bucket": "mid_tercile",
        "manual_review_required": True,
        "actionable_signal": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "demo_broker_approval_performed": False,
        "fixture_not_live_market_data": True,
        "fixture_not_actionable": True,
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


def write_review_artifacts(root: Path, *, manifest_payload: dict[str, object] | None = None, write_manifest: bool = True) -> Path:
    manifest = manifest_payload or base_manifest()
    if write_manifest:
        write_json(root / plan.SOURCE_MANIFEST, manifest)
    write_csv(root / plan.SOURCE_MAIN_CSV, [], plan.MAIN_FIELDNAMES)
    write_csv(root / plan.SOURCE_CHECKLIST_CSV, [], plan.REQUIREMENT_FIELDNAMES)
    write_csv(root / plan.SOURCE_WARNINGS_CSV, [], plan.WARNING_FIELDNAMES)
    (root / plan.SOURCE_REPORT).write_text("source report\n", encoding="utf-8")
    return root


def make_args(
    tmp_path: Path,
    *,
    registry_payload: dict[str, object] | None = None,
    review_dir: Path | None = None,
) -> object:
    registry_path = write_json(tmp_path / "registry.json", registry_payload or canonical_registry())
    if review_dir is None:
        review_dir = write_review_artifacts(tmp_path / "review")
    argv = [
        "--run-id",
        "unit_order_shadow_plan",
        "--would-signal-review-dir",
        str(review_dir),
        "--canonical-registry",
        str(registry_path),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    return plan.build_parser().parse_args(argv)


def build_valid_fixture_plan(tmp_path: Path) -> dict[str, Path]:
    return plan.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_review_produces_fixture_only_plan(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "order_shadow_plan_fixture_only"
    assert manifest["source_nature"] == "synthetic_fixture"


def test_fixture_plan_has_future_order_path_not_allowed(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["future_order_path_allowed"] is False
    assert manifest["order_execution_allowed"] is False
    assert manifest["order_request_construction_allowed"] is False


def test_fixture_plan_recommended_next_step_waits_for_live_shadow(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["recommended_next_step"] == "wait_for_live_shadow_signal_or_continue_no_order_monitoring"


def test_live_data_like_review_produces_available_no_order(tmp_path: Path) -> None:
    review_dir = write_review_artifacts(
        tmp_path / "review",
        manifest_payload=base_manifest(
            review_status="would_signal_review_available_no_order",
            source_nature="live_data_shadow_signal",
            fixture_not_live_market_data=False,
            fixture_not_actionable=False,
        ),
    )
    outputs = plan.build_outputs(make_args(tmp_path, review_dir=review_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "order_shadow_plan_available_no_order"
    assert manifest["source_nature"] == "live_data_shadow_signal"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_demo_order_request_shadow_design"


def test_live_data_like_plan_still_has_execution_and_construction_disallowed(tmp_path: Path) -> None:
    review_dir = write_review_artifacts(
        tmp_path / "review",
        manifest_payload=base_manifest(
            review_status="would_signal_review_available_no_order",
            source_nature="live_data_shadow_signal",
            fixture_not_live_market_data=False,
            fixture_not_actionable=False,
        ),
    )
    outputs = plan.build_outputs(make_args(tmp_path, review_dir=review_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["future_order_path_allowed"] is False
    assert manifest["order_execution_allowed"] is False
    assert manifest["order_request_construction_allowed"] is False
    assert manifest["no_order_execution_performed"] is True
    assert manifest["no_order_request_constructed"] is True


def test_hold_no_would_signal_review_produces_hold_plan(tmp_path: Path) -> None:
    review_dir = write_review_artifacts(tmp_path / "review", manifest_payload=base_manifest(review_status="hold_no_would_signal_to_review"))
    outputs = plan.build_outputs(make_args(tmp_path, review_dir=review_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "hold_no_would_signal_for_order_shadow_plan"
    assert manifest["recommended_next_step"] == "continue_no_order_monitoring"


def test_missing_review_manifest_blocks(tmp_path: Path) -> None:
    review_dir = write_review_artifacts(tmp_path / "review", write_manifest=False)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir=review_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_required_artifact"


def test_missing_no_order_flag_blocks(tmp_path: Path) -> None:
    manifest = base_manifest()
    manifest.pop("no_order_check_called")
    review_dir = write_review_artifacts(tmp_path / "review", manifest_payload=manifest)
    outputs = plan.build_outputs(make_args(tmp_path, review_dir=review_dir))
    result = read_json(outputs["manifest"])

    assert result["plan_status"] == "blocked_by_no_order_boundary"


def test_unsafe_no_order_flag_false_blocks(tmp_path: Path) -> None:
    review_dir = write_review_artifacts(tmp_path / "review", manifest_payload=base_manifest(no_order_request_constructed=False))
    outputs = plan.build_outputs(make_args(tmp_path, review_dir=review_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_no_order_boundary"


def test_bad_short_tp_sl_preview_blocks(tmp_path: Path) -> None:
    review_dir = write_review_artifacts(tmp_path / "review", manifest_payload=base_manifest(tp_price_preview=1.3465))
    outputs = plan.build_outputs(make_args(tmp_path, review_dir=review_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_signal_preview"


def test_noncanonical_registry_blocks(tmp_path: Path) -> None:
    outputs = plan.build_outputs(make_args(tmp_path, registry_payload=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_config_boundary"


def test_future_fields_csv_exists_and_does_not_contain_request_object(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    text = outputs["future_fields"].read_text(encoding="utf-8")

    assert outputs["future_fields"].exists()
    assert "request =" not in text
    assert "order_request =" not in text
    assert "TRADE_ACTION" not in text


def test_future_fields_are_future_only_and_not_constructed(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_fields"])

    assert rows
    assert all(row["future_field_only"] == "true" for row in rows)
    assert all(row["not_constructed"] == "true" for row in rows)
    assert all(row["broker_request_field"] == "false" for row in rows)


def test_requirements_include_core_future_safety_checks(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["requirements"])
    names = {row["requirement_name"] for row in rows}

    expected = {
        "manual_approval_gate_present",
        "duplicate_protection_checked",
        "crash_recovery_state_path_defined",
        "kill_switch_state_checked",
        "SL_TP_mandatory",
        "risk_percentage_capped",
        "spread_current_rechecked",
    }
    assert expected <= names


def test_report_contains_fixture_non_actionable_disclaimer(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "synthetic fixture" in report
    assert "non-actionable" in report


def test_report_contains_no_order_request_db_mt5_scheduler_caveats(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5" in report
    assert "No database query or mutation" in report
    assert "No broker order request" in report
    assert "No order execution" in report
    assert "No order_check or order_calc" in report
    assert "No scheduler, loop, or background task" in report


def test_static_source_has_no_forbidden_call_signatures() -> None:
    source = Path("scripts/build_fixed_candidate_demo_order_shadow_plan.py").read_text(encoding="utf-8")
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
    source = Path("scripts/build_fixed_candidate_demo_order_shadow_plan.py").read_text(encoding="utf-8")
    forbidden = [
        "Task Scheduler",
        "schtasks",
        "while True",
        "APScheduler",
        "threading.Timer",
    ]

    for token in forbidden:
        assert token not in source


def test_static_source_has_no_broker_request_dict_patterns() -> None:
    source = Path("scripts/build_fixed_candidate_demo_order_shadow_plan.py").read_text(encoding="utf-8")
    forbidden = [
        "request =",
        "order_request =",
        "mt5.TRADE_ACTION_DEAL",
        "TRADE_ACTION_PENDING",
    ]

    for token in forbidden:
        assert token not in source


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_db_query_performed"] is True
    assert manifest["no_order_execution_performed"] is True
