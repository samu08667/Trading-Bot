from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_margin_feasibility_plan as margin


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


def risk_volume_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "plan_status": "risk_volume_shadow_plan_fixture_only",
        "source_nature": "synthetic_fixture",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "risk_percent": 0.5,
        "risk_amount": 5.0,
        "entry_reference_price": 1.25,
        "tp_price_preview": 1.249,
        "sl_price_preview": 1.251,
        "risk_distance_price": 0.001,
        "raw_volume_lots": 0.05,
        "stepped_volume_lots": 0.05,
        "volume_preview_status": "shadow_volume_preview_available_not_broker_validated",
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "plan_actionable": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "future_request_construction_allowed": False,
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
        "margin_validation_forbidden_here": True,
        "profit_validation_forbidden_here": True,
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


def account_snapshot(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "account_trade_mode_label": "demo",
        "is_demo_account": True,
        "redaction_applied": True,
        "leverage": 100,
        "currency": "EUR",
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
        "trade_contract_size": 100000.0,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
    }
    data.update(overrides)
    return data


def write_risk_volume_artifacts(root: Path, *, manifest_data: dict[str, object] | None = None, write_manifest: bool = True) -> Path:
    if write_manifest:
        write_json(root / margin.SOURCE_RISK_VOLUME_MANIFEST, manifest_data or risk_volume_manifest())
    write_csv(root / margin.SOURCE_RISK_VOLUME_MAIN_CSV, [], margin.MAIN_FIELDNAMES)
    write_csv(root / margin.SOURCE_RISK_VOLUME_FORMULA_CSV, [], margin.FORMULA_FIELDNAMES)
    write_csv(root / margin.SOURCE_RISK_VOLUME_REQUIREMENTS_CSV, [], margin.REQUIREMENT_FIELDNAMES)
    write_csv(root / margin.SOURCE_RISK_VOLUME_WARNINGS_CSV, [], margin.WARNING_FIELDNAMES)
    (root / margin.SOURCE_RISK_VOLUME_REPORT).write_text("source report\n", encoding="utf-8")
    return root


def write_env_artifacts(
    root: Path,
    *,
    env_data: dict[str, object] | None = None,
    account_data: dict[str, object] | None = None,
    symbol_data: dict[str, object] | None = None,
) -> Path:
    write_json(root / margin.ENV_MANIFEST, env_data or env_manifest())
    write_json(root / margin.ACCOUNT_SNAPSHOT, account_data or account_snapshot())
    write_json(root / margin.SYMBOL_SNAPSHOT, symbol_data or symbol_snapshot())
    write_csv(root / margin.ENV_NO_ORDER_CSV, [], margin.WARNING_FIELDNAMES)
    write_csv(root / margin.ENV_WARNINGS_CSV, [], margin.WARNING_FIELDNAMES)
    return root


def make_args(
    tmp_path: Path,
    *,
    registry_data: dict[str, object] | None = None,
    policy_data: dict[str, object] | None = None,
    risk_dir: Path | None = None,
    env_dir: Path | None = None,
    intended_demo_equity: float | None = None,
    max_margin_usage_ratio: float | None = None,
) -> object:
    registry_path = write_json(tmp_path / "registry.json", registry_data or canonical_registry())
    policy_path = write_json(tmp_path / "policy.json", policy_data or execution_policy())
    if risk_dir is None:
        risk_dir = write_risk_volume_artifacts(tmp_path / "risk")
    if env_dir is None:
        env_dir = write_env_artifacts(tmp_path / "env")
    argv = [
        "--run-id",
        "unit_margin_feasibility_plan",
        "--risk-volume-shadow-plan-dir",
        str(risk_dir),
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
    if intended_demo_equity is not None:
        argv.extend(["--intended-demo-equity", str(intended_demo_equity)])
    if max_margin_usage_ratio is not None:
        argv.extend(["--max-margin-usage-ratio", str(max_margin_usage_ratio)])
    return margin.build_parser().parse_args(argv)


def build_valid_fixture_plan(tmp_path: Path) -> dict[str, Path]:
    return margin.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        margin.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_risk_volume_with_policy_equity1000_risk05_produces_fixture_only(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "margin_feasibility_plan_fixture_only"
    assert manifest["source_nature"] == "synthetic_fixture"
    assert manifest["policy_intended_demo_equity"] == pytest.approx(1000.0)
    assert manifest["policy_risk_percent_max"] == pytest.approx(0.5)
    assert manifest["policy_risk_amount_max"] == pytest.approx(5.0)
    assert manifest["policy_max_margin_usage_ratio"] == pytest.approx(0.7)
    assert manifest["policy_max_margin_usage_amount"] == pytest.approx(700.0)
    assert manifest["policy_max_margin_usage_warning_ratio"] == pytest.approx(0.5)
    assert manifest["policy_max_margin_usage_warning_amount"] == pytest.approx(500.0)


def test_missing_volume_preview_produces_formula_only_status(tmp_path: Path) -> None:
    risk_dir = write_risk_volume_artifacts(
        tmp_path / "risk",
        manifest_data=risk_volume_manifest(
            risk_amount=None,
            raw_volume_lots=None,
            stepped_volume_lots=None,
            volume_preview_status="blocked_missing_demo_equity",
        ),
    )
    outputs = margin.build_outputs(make_args(tmp_path, risk_dir=risk_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "margin_feasibility_formula_only_missing_volume"
    assert manifest["recommended_next_step"] == "rerun_risk_volume_shadow_plan_with_execution_policy_equity1000_risk05"


def test_static_margin_formulas_compute_from_artifacts(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["estimated_notional_base"] == pytest.approx(5000.0)
    assert manifest["estimated_notional_quote"] == pytest.approx(6250.0)
    assert manifest["estimated_margin_quote"] == pytest.approx(62.5)


def test_approximate_margin_usage_ratio_computed(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["approximate_margin_usage_ratio"] == pytest.approx(0.0625)
    assert manifest["margin_usage_ratio_status"] == "quote_currency_approximation_not_broker_validated"


def test_margin_usage_above_warning_below_cap_stays_fixture_only_with_warning(tmp_path: Path) -> None:
    risk_dir = write_risk_volume_artifacts(
        tmp_path / "risk",
        manifest_data=risk_volume_manifest(
            entry_reference_price=1.346,
            raw_volume_lots=0.13881071428568556,
            stepped_volume_lots=0.13,
        ),
    )
    env_dir = write_env_artifacts(tmp_path / "env", account_data=account_snapshot(leverage=30))
    outputs = margin.build_outputs(make_args(tmp_path, risk_dir=risk_dir, env_dir=env_dir))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["approximate_margin_usage_ratio"] == pytest.approx(0.5832666666666666)
    assert manifest["max_margin_usage_ratio"] == pytest.approx(0.7)
    assert manifest["max_margin_usage_warning_ratio"] == pytest.approx(0.5)
    assert manifest["plan_status"] == "margin_feasibility_plan_fixture_only"
    assert any(row["warning_code"] == "margin_usage_above_warning_threshold" for row in warnings)


def test_high_margin_usage_produces_hold(tmp_path: Path) -> None:
    env_dir = write_env_artifacts(tmp_path / "env", account_data=account_snapshot(leverage=10))
    outputs = margin.build_outputs(make_args(tmp_path, env_dir=env_dir, max_margin_usage_ratio=0.1))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "margin_feasibility_hold_requires_broker_margin_validation"
    assert manifest["blocking_warnings_count"] == 0


def test_policy_override_warnings_are_written(tmp_path: Path) -> None:
    outputs = margin.build_outputs(make_args(tmp_path, intended_demo_equity=2000.0, max_margin_usage_ratio=0.25))
    warnings = read_csv(outputs["warnings"])
    warning_codes = {row["warning_code"] for row in warnings}

    assert "intended_demo_equity_policy_override" in warning_codes
    assert "max_margin_usage_ratio_policy_override" in warning_codes


def test_noncanonical_registry_blocks(tmp_path: Path) -> None:
    outputs = margin.build_outputs(make_args(tmp_path, registry_data=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_config_boundary"


def test_non_demo_account_snapshot_blocks(tmp_path: Path) -> None:
    env_dir = write_env_artifacts(tmp_path / "env", account_data=account_snapshot(is_demo_account=False))
    outputs = margin.build_outputs(make_args(tmp_path, env_dir=env_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_account_snapshot"


def test_missing_symbol_contract_fields_blocks(tmp_path: Path) -> None:
    symbol_data = symbol_snapshot()
    symbol_data.pop("trade_contract_size")
    env_dir = write_env_artifacts(tmp_path / "env", symbol_data=symbol_data)
    outputs = margin.build_outputs(make_args(tmp_path, env_dir=env_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_symbol_contract"


def test_missing_no_order_flag_blocks(tmp_path: Path) -> None:
    source = risk_volume_manifest()
    source.pop("no_order_check_called")
    risk_dir = write_risk_volume_artifacts(tmp_path / "risk", manifest_data=source)
    outputs = margin.build_outputs(make_args(tmp_path, risk_dir=risk_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_no_order_boundary"


def test_unsafe_no_order_flag_false_blocks(tmp_path: Path) -> None:
    risk_dir = write_risk_volume_artifacts(tmp_path / "risk", manifest_data=risk_volume_manifest(no_order_request_constructed=False))
    outputs = margin.build_outputs(make_args(tmp_path, risk_dir=risk_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_no_order_boundary"


def test_risk_percent_above_one_blocks(tmp_path: Path) -> None:
    risk_dir = write_risk_volume_artifacts(tmp_path / "risk", manifest_data=risk_volume_manifest(risk_percent=2.0))
    outputs = margin.build_outputs(make_args(tmp_path, risk_dir=risk_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_volume_preview"


def test_report_contains_policy_equity_risk_and_margin_language(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Intended demo equity: 1000 EUR." in report
    assert "Risk percent max: 0.5%." in report
    assert "Risk amount max: 5 EUR." in report
    assert "Max margin usage policy: 70%" in report
    assert "Margin usage above 50%" in report


def test_report_contains_no_order_margin_mt5_db_scheduler_caveats(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5" in report
    assert "No database query or mutation" in report
    assert "No broker request dictionary" in report
    assert "No order execution" in report
    assert "No order_check, order_calc_margin, or order_calc_profit" in report
    assert "No broker margin validation" in report
    assert "No scheduler, loop, or background task" in report


def test_formula_rows_include_static_estimate_caveats(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["formula"])

    assert rows
    assert all("static_artifact_estimate_only" in row["caveat"] for row in rows)
    assert all("not_broker_validated" in row["caveat"] for row in rows)


def test_requirements_include_future_margin_and_state_checks(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["requirements"])
    names = {row["requirement_name"] for row in rows}

    assert {
        "equity_free_margin_current_read_only_check",
        "broker_margin_future_validation",
        "state_reconciliation",
        "duplicate_protection",
        "kill_switch_state",
        "manual_approval_gate",
    } <= names


def test_static_source_has_no_forbidden_call_signatures() -> None:
    source = Path("scripts/build_fixed_candidate_demo_margin_feasibility_plan.py").read_text(encoding="utf-8")
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
    source = Path("scripts/build_fixed_candidate_demo_margin_feasibility_plan.py").read_text(encoding="utf-8")
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
    source = Path("scripts/build_fixed_candidate_demo_margin_feasibility_plan.py").read_text(encoding="utf-8")
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
