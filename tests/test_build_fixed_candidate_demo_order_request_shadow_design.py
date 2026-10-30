from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_order_request_shadow_design as design


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
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
    data: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
    }
    data.update(overrides)
    return data


def source_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "plan_status": "order_shadow_plan_fixture_only",
        "source_nature": "synthetic_fixture",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "time_server": "2026-06-01 02:00:00",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "entry_reference_price": 1.346,
        "tp_price_preview": 1.34537,
        "sl_price_preview": 1.34642,
        "future_order_path_allowed": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "demo_broker_approval_performed": False,
        "actionable_signal": False,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_trading_decision_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_db_query_performed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
    }
    data.update(overrides)
    return data


def write_source_artifacts(root: Path, *, manifest_data: dict[str, object] | None = None, write_manifest: bool = True) -> Path:
    if write_manifest:
        write_json(root / design.SOURCE_MANIFEST, manifest_data or source_manifest())
    write_csv(root / design.SOURCE_MAIN_CSV, [], design.MAIN_FIELDNAMES)
    write_csv(root / design.SOURCE_REQUIREMENTS_CSV, [], design.STAGE_FIELDNAMES)
    write_csv(root / design.SOURCE_FUTURE_FIELDS_CSV, [], design.INTENT_FIELDNAMES)
    write_csv(root / design.SOURCE_WARNINGS_CSV, [], design.WARNING_FIELDNAMES)
    (root / design.SOURCE_REPORT).write_text("source report\n", encoding="utf-8")
    return root


def make_args(
    tmp_path: Path,
    *,
    registry_data: dict[str, object] | None = None,
    source_dir: Path | None = None,
) -> object:
    registry_path = write_json(tmp_path / "registry.json", registry_data or canonical_registry())
    if source_dir is None:
        source_dir = write_source_artifacts(tmp_path / "source")
    argv = [
        "--run-id",
        "unit_order_request_shadow_design",
        "--order-shadow-plan-dir",
        str(source_dir),
        "--canonical-registry",
        str(registry_path),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    return design.build_parser().parse_args(argv)


def build_valid_fixture_design(tmp_path: Path) -> dict[str, Path]:
    return design.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        design.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_order_shadow_plan_produces_fixture_only_design(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["design_status"] == "order_request_shadow_design_fixture_only"
    assert manifest["source_nature"] == "synthetic_fixture"


def test_fixture_design_has_design_actionable_false(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["design_actionable"] is False
    assert manifest["future_request_construction_allowed"] is False


def test_fixture_design_recommended_next_step_waits(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["recommended_next_step"] == "wait_for_live_shadow_signal_or_continue_no_order_monitoring"


def test_live_data_like_order_shadow_plan_produces_available_no_order(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=source_manifest(
            plan_status="order_shadow_plan_available_no_order",
            source_nature="live_data_shadow_signal",
        ),
    )
    outputs = design.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["design_status"] == "order_request_shadow_design_available_no_order"
    assert manifest["source_nature"] == "live_data_shadow_signal"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_demo_risk_volume_shadow_plan"


def test_live_data_like_design_still_disallows_future_request_construction(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=source_manifest(
            plan_status="order_shadow_plan_available_no_order",
            source_nature="live_data_shadow_signal",
        ),
    )
    outputs = design.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["future_request_construction_allowed"] is False
    assert manifest["order_execution_allowed"] is False
    assert manifest["order_request_construction_allowed"] is False


def test_hold_order_shadow_plan_produces_hold_design(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=source_manifest(plan_status="hold_no_would_signal_for_order_shadow_plan"),
    )
    outputs = design.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["design_status"] == "hold_no_order_shadow_plan_available"
    assert manifest["recommended_next_step"] == "continue_no_order_monitoring"


def test_missing_plan_manifest_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", write_manifest=False)
    outputs = design.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["design_status"] == "blocked_missing_required_artifact"


def test_missing_no_order_flag_blocks(tmp_path: Path) -> None:
    data = source_manifest()
    data.pop("no_order_check_called")
    source_dir = write_source_artifacts(tmp_path / "source", manifest_data=data)
    outputs = design.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["design_status"] == "blocked_by_no_order_boundary"


def test_unsafe_no_order_flag_false_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=source_manifest(no_order_request_constructed=False),
    )
    outputs = design.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["design_status"] == "blocked_by_no_order_boundary"


def test_bad_short_tp_sl_preview_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", manifest_data=source_manifest(tp_price_preview=1.3465))
    outputs = design.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["design_status"] == "blocked_by_signal_preview"


def test_noncanonical_registry_blocks(tmp_path: Path) -> None:
    outputs = design.build_outputs(make_args(tmp_path, registry_data=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["design_status"] == "blocked_by_config_boundary"


def test_future_intent_fields_csv_contains_only_intent_names(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    rows = read_csv(outputs["intent_fields"])

    assert rows
    assert all(row["intent_field_name"].startswith("intent_") for row in rows)


def test_future_intent_fields_are_marked_not_constructed_and_not_payload(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    rows = read_csv(outputs["intent_fields"])

    assert all(row["intent_field_only"] == "true" for row in rows)
    assert all(row["not_broker_payload"] == "true" for row in rows)
    assert all(row["not_constructed"] == "true" for row in rows)
    assert all(row["future_request_construction_allowed"] == "false" for row in rows)


def test_future_intent_fields_do_not_include_standalone_broker_payload_keys(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    rows = read_csv(outputs["intent_fields"])
    names = {row["intent_field_name"] for row in rows}

    assert not {"request", "action", "type", "price", "sl", "tp", "volume"} & names


def test_validation_stages_include_required_future_gates(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    rows = read_csv(outputs["stages"])
    names = {row["stage_name"] for row in rows}

    expected = {
        "stage_05_risk_volume_shadow_calculation",
        "stage_06_duplicate_and_state_reconciliation",
        "stage_07_kill_switch_and_manual_approval",
        "stage_08_future_request_construction_gate",
        "stage_09_future_order_check_gate",
        "stage_10_future_execution_gate",
    }
    assert expected <= names


def test_request_check_and_execution_stages_cannot_run_now(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    rows = read_csv(outputs["stages"])
    gated = {
        "stage_08_future_request_construction_gate",
        "stage_09_future_order_check_gate",
        "stage_10_future_execution_gate",
    }

    for row in rows:
        if row["stage_name"] in gated:
            assert row["can_run_now"] == "false"


def test_report_contains_fixture_non_actionable_disclaimer(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "synthetic fixture" in report
    assert "non-actionable" in report


def test_report_contains_no_request_order_db_mt5_scheduler_caveats(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "not a broker request dictionary" in report
    assert "No executable request object" in report
    assert "No MT5" in report
    assert "No database query or mutation" in report
    assert "No order execution" in report
    assert "No order_check or order_calc" in report
    assert "No scheduler, loop, or background task" in report


def test_static_source_has_no_forbidden_call_signatures() -> None:
    source = Path("scripts/build_fixed_candidate_demo_order_request_shadow_design.py").read_text(encoding="utf-8")
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
    source = Path("scripts/build_fixed_candidate_demo_order_request_shadow_design.py").read_text(encoding="utf-8")
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
    source = Path("scripts/build_fixed_candidate_demo_order_request_shadow_design.py").read_text(encoding="utf-8")
    forbidden = [
        "request =",
        "order_request =",
        "mt5.TRADE_ACTION_DEAL",
        "TRADE_ACTION_PENDING",
        '"action":',
        '"type":',
        '"price":',
        '"sl":',
        '"tp":',
        '"volume":',
    ]

    for token in forbidden:
        assert token not in source


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path) -> None:
    outputs = build_valid_fixture_design(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_db_query_performed"] is True
    assert manifest["no_order_execution_performed"] is True
