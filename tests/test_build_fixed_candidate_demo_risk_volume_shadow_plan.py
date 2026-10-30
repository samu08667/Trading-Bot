from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_risk_volume_shadow_plan as risk_volume


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
        "demo_execution_policy_json": "config/fixed_candidate_demo_execution_policy.json",
        "account_currency": "EUR",
        "intended_demo_equity": 1000.0,
        "risk_percent_max": 0.5,
        "risk_amount_max": 5.0,
        "max_margin_usage_ratio": 0.7,
        "max_margin_usage_amount": 700.0,
        "max_margin_usage_warning_ratio": 0.5,
        "max_margin_usage_warning_amount": 500.0,
    }
    data.update(overrides)
    return data


def execution_policy(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "policy_id": "gbpusd_short_h10_1_5_off_hours_demo_execution_policy_v1",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "account_currency": "EUR",
        "intended_demo_equity": 1000.0,
        "risk_percent_max": 0.5,
        "risk_amount_max": 5.0,
        "max_margin_usage_ratio": 0.7,
        "max_margin_usage_amount": 700.0,
        "max_margin_usage_warning_ratio": 0.5,
        "max_margin_usage_warning_amount": 500.0,
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
        "volume_policy": {
            "rounding": "floor_to_volume_step",
            "below_min_volume": "block",
            "above_max_volume": "block",
            "risk_margin_conflict": "cap_by_margin_or_block_before_request",
            "do_not_force_full_risk_if_margin_infeasible": True,
        },
        "safety_boundaries": {
            "paper_only_until_explicit_future_change": True,
            "real_money_allowed": False,
            "broker_connection_allowed_for_this_policy_file": False,
            "order_execution_allowed": False,
            "order_request_construction_allowed": False,
            "order_check_allowed": False,
            "order_calc_allowed": False,
            "manual_approval_required_before_any_future_demo_order": True,
        },
    }
    data.update(overrides)
    return data


def design_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "design_status": "order_request_shadow_design_fixture_only",
        "source_nature": "synthetic_fixture",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "time_server": "2026-06-01 02:00:00",
        "entry_reference_price": 1.346,
        "tp_price_preview": 1.34537,
        "sl_price_preview": 1.34642,
        "design_actionable": False,
        "future_request_construction_allowed": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "demo_broker_approval_performed": False,
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
        "broker_payload_forbidden": True,
        "executable_request_object_forbidden": True,
    }
    data.update(overrides)
    return data


def env_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "environment_check_status": "environment_check_available_with_caveats",
        "is_demo_account": True,
        "spread_policy_matches_canonical": True,
        "spread_within_config_gate": True,
    }
    data.update(overrides)
    return data


def symbol_snapshot(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "symbol": "GBPUSD",
        "visible": True,
        "select": True,
        "digits": 5,
        "point": 0.00001,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "trade_tick_size": 0.0001,
        "trade_tick_value": 10.0,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
    }
    data.update(overrides)
    return data


def account_snapshot(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "account_trade_mode_label": "demo",
        "is_demo_account": True,
        "redaction_applied": True,
    }
    data.update(overrides)
    return data


def write_design_artifacts(root: Path, *, manifest_data: dict[str, object] | None = None, write_manifest: bool = True) -> Path:
    if write_manifest:
        write_json(root / risk_volume.SOURCE_DESIGN_MANIFEST, manifest_data or design_manifest())
    write_csv(root / risk_volume.SOURCE_DESIGN_MAIN_CSV, [], risk_volume.MAIN_FIELDNAMES)
    write_csv(root / risk_volume.SOURCE_DESIGN_STAGES_CSV, [], risk_volume.FORMULA_FIELDNAMES)
    write_csv(root / risk_volume.SOURCE_DESIGN_FIELDS_CSV, [], risk_volume.REQUIREMENT_FIELDNAMES)
    write_csv(root / risk_volume.SOURCE_DESIGN_WARNINGS_CSV, [], risk_volume.WARNING_FIELDNAMES)
    (root / risk_volume.SOURCE_DESIGN_REPORT).write_text("source report\n", encoding="utf-8")
    return root


def write_environment_artifacts(
    root: Path,
    *,
    env_data: dict[str, object] | None = None,
    symbol_data: dict[str, object] | None = None,
    account_data: dict[str, object] | None = None,
) -> Path:
    write_json(root / risk_volume.ENV_MANIFEST, env_data or env_manifest())
    write_json(root / risk_volume.SYMBOL_SNAPSHOT, symbol_data or symbol_snapshot())
    write_json(root / risk_volume.ACCOUNT_SNAPSHOT, account_data or account_snapshot())
    write_csv(root / risk_volume.ENV_NO_ORDER_CSV, [], risk_volume.WARNING_FIELDNAMES)
    write_csv(root / risk_volume.ENV_WARNINGS_CSV, [], risk_volume.WARNING_FIELDNAMES)
    return root


def make_args(
    tmp_path: Path,
    *,
    registry_data: dict[str, object] | None = None,
    design_dir: Path | None = None,
    env_dir: Path | None = None,
    policy_data: dict[str, object] | None = None,
    risk_percent: float | None = None,
    demo_equity: float | None = None,
) -> object:
    registry_path = write_json(tmp_path / "registry.json", registry_data or canonical_registry())
    policy_path = write_json(tmp_path / "policy.json", policy_data or execution_policy())
    if design_dir is None:
        design_dir = write_design_artifacts(tmp_path / "design")
    if env_dir is None:
        env_dir = write_environment_artifacts(tmp_path / "env")
    argv = [
        "--run-id",
        "unit_risk_volume_shadow_plan",
        "--order-request-shadow-design-dir",
        str(design_dir),
        "--demo-environment-check-dir",
        str(env_dir),
        "--canonical-registry",
        str(registry_path),
        "--demo-execution-policy",
        str(policy_path),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    if risk_percent is not None:
        argv.extend(["--risk-percent", str(risk_percent)])
    if demo_equity is not None:
        argv.extend(["--demo-equity", str(demo_equity)])
    return risk_volume.build_parser().parse_args(argv)


def build_valid_fixture_plan(
    tmp_path: Path,
    *,
    demo_equity: float | None = None,
    risk_percent: float | None = None,
) -> dict[str, Path]:
    return risk_volume.build_outputs(make_args(tmp_path, demo_equity=demo_equity, risk_percent=risk_percent))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        risk_volume.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_design_produces_fixture_only_plan(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "risk_volume_shadow_plan_fixture_only"
    assert manifest["source_nature"] == "synthetic_fixture"


def test_fixture_plan_has_plan_actionable_false(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_actionable"] is False
    assert manifest["order_execution_allowed"] is False


def test_fixture_plan_recommended_next_step_waits(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["recommended_next_step"] == "wait_for_live_shadow_signal_or_continue_no_order_monitoring"


def test_live_data_like_design_produces_available_no_order(tmp_path: Path) -> None:
    design_dir = write_design_artifacts(
        tmp_path / "design",
        manifest_data=design_manifest(
            design_status="order_request_shadow_design_available_no_order",
            source_nature="live_data_shadow_signal",
        ),
    )
    outputs = risk_volume.build_outputs(make_args(tmp_path, design_dir=design_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "risk_volume_shadow_plan_available_no_order"
    assert manifest["source_nature"] == "live_data_shadow_signal"


def test_live_data_like_plan_still_disallows_order_and_request(tmp_path: Path) -> None:
    design_dir = write_design_artifacts(
        tmp_path / "design",
        manifest_data=design_manifest(
            design_status="order_request_shadow_design_available_no_order",
            source_nature="live_data_shadow_signal",
        ),
    )
    outputs = risk_volume.build_outputs(make_args(tmp_path, design_dir=design_dir, demo_equity=10000))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_execution_allowed"] is False
    assert manifest["order_request_construction_allowed"] is False
    assert manifest["future_request_construction_allowed"] is False


def test_policy_defaults_compute_volume_preview(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["policy_intended_demo_equity"] == pytest.approx(1000.0)
    assert manifest["policy_risk_percent_max"] == pytest.approx(0.5)
    assert manifest["policy_risk_amount_max"] == pytest.approx(5.0)
    assert manifest["policy_max_margin_usage_ratio"] == pytest.approx(0.7)
    assert manifest["policy_max_margin_usage_amount"] == pytest.approx(700.0)
    assert manifest["policy_max_margin_usage_warning_ratio"] == pytest.approx(0.5)
    assert manifest["policy_max_margin_usage_warning_amount"] == pytest.approx(500.0)
    assert manifest["demo_equity"] == pytest.approx(1000.0)
    assert manifest["risk_percent"] == pytest.approx(0.5)
    assert manifest["risk_amount"] == pytest.approx(5.0)
    assert manifest["volume_preview_status"] == "shadow_volume_preview_available_not_broker_validated"


def test_cli_demo_equity_override_computes_volume_preview_and_warns(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path, demo_equity=10000)
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["risk_amount"] == pytest.approx(50.0)
    assert manifest["raw_volume_lots"] == pytest.approx(1.190476, rel=1e-5)
    assert manifest["stepped_volume_lots"] == pytest.approx(1.19)
    assert manifest["volume_preview_status"] == "shadow_volume_preview_available_not_broker_validated"
    assert any(row["warning_code"] == "demo_equity_policy_override" for row in warnings)


def test_cli_risk_percent_override_warns(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path, risk_percent=1.0)
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["risk_percent"] == pytest.approx(1.0)
    assert manifest["risk_amount"] == pytest.approx(10.0)
    assert any(row["warning_code"] == "risk_percent_policy_override" for row in warnings)


def test_volume_below_min_produces_blocked_below_min_status(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path, demo_equity=1)
    manifest = read_json(outputs["manifest"])

    assert manifest["volume_preview_status"] == "blocked_below_min_volume"


def test_risk_percent_above_one_blocks(tmp_path: Path) -> None:
    outputs = risk_volume.build_outputs(make_args(tmp_path, risk_percent=2.0, demo_equity=10000))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_risk_policy"


def test_bad_short_tp_sl_preview_blocks(tmp_path: Path) -> None:
    design_dir = write_design_artifacts(tmp_path / "design", manifest_data=design_manifest(tp_price_preview=1.3465))
    outputs = risk_volume.build_outputs(make_args(tmp_path, design_dir=design_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_signal_price_preview"


def test_noncanonical_registry_blocks(tmp_path: Path) -> None:
    outputs = risk_volume.build_outputs(make_args(tmp_path, registry_data=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_config_boundary"


def test_environment_artifact_not_demo_blocks(tmp_path: Path) -> None:
    env_dir = write_environment_artifacts(tmp_path / "env", env_data=env_manifest(is_demo_account=False))
    outputs = risk_volume.build_outputs(make_args(tmp_path, env_dir=env_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_environment_artifact"


def test_symbol_contract_missing_required_field_blocks(tmp_path: Path) -> None:
    symbol_data = symbol_snapshot()
    symbol_data.pop("volume_step")
    env_dir = write_environment_artifacts(tmp_path / "env", symbol_data=symbol_data)
    outputs = risk_volume.build_outputs(make_args(tmp_path, env_dir=env_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_symbol_contract"


def test_stop_level_formula_is_computed(tmp_path: Path) -> None:
    env_dir = write_environment_artifacts(tmp_path / "env", symbol_data=symbol_snapshot(trade_stops_level=10, point=0.00001))
    outputs = risk_volume.build_outputs(make_args(tmp_path, env_dir=env_dir, demo_equity=10000))
    formulas = read_csv(outputs["formula"])
    stop_formula = next(row for row in formulas if row["formula_name"] == "stop_distance_min_price")

    assert float(stop_formula["computed_value"]) == pytest.approx(0.0001)


def test_formula_csv_includes_expected_formulas_and_values(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path, demo_equity=10000)
    formulas = read_csv(outputs["formula"])
    names = {row["formula_name"] for row in formulas}

    assert {
        "risk_amount",
        "risk_distance_price",
        "value_per_price_unit_per_lot",
        "risk_per_lot",
        "raw_volume_lots",
        "stepped_volume_lots",
        "stop_distance_min_price",
    } <= names
    assert any(row["formula_name"] == "risk_amount" and float(row["computed_value"]) == pytest.approx(50.0) for row in formulas)


def test_requirements_include_future_safety_checks(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["requirements"])
    names = {row["requirement_name"] for row in rows}

    assert {
        "account_demo_reconfirmed",
        "symbol_contract_reconfirmed",
        "spread_rechecked",
        "stop_levels_rechecked",
        "volume_min_max_step_rechecked",
        "margin_adequacy_future_check",
        "duplicate_protection",
        "state_reconciliation",
        "kill_switch_state",
        "manual_approval_gate",
        "audit_logging",
    } <= names


def test_report_contains_fixture_non_actionable_disclaimer(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "synthetic fixture" in report
    assert "non-actionable" in report


def test_report_contains_no_request_order_calc_margin_profit_mt5_db_scheduler_caveats(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path, demo_equity=10000)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5" in report
    assert "No database query or mutation" in report
    assert "No broker request dictionary" in report
    assert "No order execution" in report
    assert "No order_check or order_calc" in report
    assert "No margin or profit validation" in report
    assert "No scheduler, loop, or background task" in report


def test_static_source_has_no_forbidden_call_signatures() -> None:
    source = Path("scripts/build_fixed_candidate_demo_risk_volume_shadow_plan.py").read_text(encoding="utf-8")
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
    source = Path("scripts/build_fixed_candidate_demo_risk_volume_shadow_plan.py").read_text(encoding="utf-8")
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
    source = Path("scripts/build_fixed_candidate_demo_risk_volume_shadow_plan.py").read_text(encoding="utf-8")
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
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_db_query_performed"] is True
    assert manifest["no_order_execution_performed"] is True
