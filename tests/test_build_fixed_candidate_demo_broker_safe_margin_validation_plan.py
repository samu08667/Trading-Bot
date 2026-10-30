from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_broker_safe_margin_validation_plan as broker_margin


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
        "max_margin_usage_warning_ratio": 0.5,
        "max_margin_usage_warning_amount": 500.0,
        "max_margin_usage_ratio": 0.7,
        "max_margin_usage_amount": 700.0,
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "safety_boundaries": {
            "real_money_allowed": False,
            "order_execution_allowed": False,
            "order_request_construction_allowed": False,
            "order_check_allowed": False,
            "order_calc_allowed": False,
            "manual_approval_required_before_any_future_demo_order": True,
        },
    }
    data.update(overrides)
    return data


def margin_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "plan_status": "margin_feasibility_plan_fixture_only",
        "source_nature": "synthetic_fixture",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "intended_demo_equity": 1000.0,
        "risk_percent": 0.5,
        "risk_amount": 5.0,
        "max_margin_usage_ratio": 0.7,
        "approximate_margin_usage_ratio": 0.5832666666666666,
        "estimated_margin_quote": 583.2666666666667,
        "margin_usage_ratio_status": "quote_currency_approximation_not_broker_validated",
        "estimated_margin_account_currency_status": "requires_currency_conversion_or_broker_validation",
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
        "order_calc_margin_forbidden_here": True,
        "broker_margin_validation_required_future": True,
        "margin_estimate_static_artifact_only": True,
    }
    data.update(overrides)
    return data


def write_margin_artifacts(
    root: Path,
    *,
    manifest_data: dict[str, object] | None = None,
    write_manifest: bool = True,
    warning_rows: list[dict[str, object]] | None = None,
) -> Path:
    if write_manifest:
        write_json(root / broker_margin.SOURCE_MANIFEST, manifest_data or margin_manifest())
    (root / broker_margin.SOURCE_REPORT).parent.mkdir(parents=True, exist_ok=True)
    (root / broker_margin.SOURCE_REPORT).write_text("source report\n", encoding="utf-8")
    write_csv(root / broker_margin.SOURCE_MAIN_CSV, [], ["source"])
    write_csv(root / broker_margin.SOURCE_FORMULA_CSV, [], ["formula"])
    write_csv(root / broker_margin.SOURCE_REQUIREMENTS_CSV, [], ["requirement"])
    warnings = warning_rows
    if warnings is None:
        warnings = [
            {
                "run_id": "source",
                "warning_code": "margin_usage_above_warning_threshold",
                "severity": "warning",
                "message": "Static margin approximation exceeds warning threshold.",
                "source": "source",
                "blocking_warning": False,
            }
        ]
    write_csv(root / broker_margin.SOURCE_WARNINGS_CSV, warnings, broker_margin.WARNING_FIELDNAMES)
    return root


def make_args(
    tmp_path: Path,
    *,
    registry_data: dict[str, object] | None = None,
    policy_data: dict[str, object] | None = None,
    margin_dir: Path | None = None,
) -> object:
    registry_path = write_json(tmp_path / "registry.json", registry_data or canonical_registry())
    policy_path = write_json(tmp_path / "policy.json", policy_data or execution_policy())
    if margin_dir is None:
        margin_dir = write_margin_artifacts(tmp_path / "margin")
    argv = [
        "--run-id",
        "unit_broker_safe_margin_validation_plan",
        "--margin-feasibility-plan-dir",
        str(margin_dir),
        "--canonical-registry",
        str(registry_path),
        "--demo-execution-policy",
        str(policy_path),
        "--future-broker-safe-margin-validation-script",
        str(tmp_path / "future_check.py"),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    return broker_margin.build_parser().parse_args(argv)


def build_valid_fixture_plan(tmp_path: Path) -> dict[str, Path]:
    return broker_margin.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        broker_margin.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_source_produces_fixture_only(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "broker_safe_margin_validation_plan_fixture_only"
    assert manifest["source_nature"] == "synthetic_fixture"
    assert manifest["plan_actionable"] is False
    assert manifest["recommended_next_step"] == "wait_for_live_shadow_signal_or_continue_no_order_monitoring"


def test_live_data_source_produces_available(tmp_path: Path) -> None:
    margin_dir = write_margin_artifacts(
        tmp_path / "margin",
        manifest_data=margin_manifest(
            plan_status="margin_feasibility_plan_available_no_order",
            source_nature="live_data_shadow_signal",
            approximate_margin_usage_ratio=0.4,
        ),
        warning_rows=[],
    )
    outputs = broker_margin.build_outputs(make_args(tmp_path, margin_dir=margin_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "broker_safe_margin_validation_plan_available"
    assert manifest["source_nature"] == "live_data_shadow_signal"
    assert manifest["recommended_next_step"] == "implement_check_fixed_candidate_demo_broker_safe_margin_validation_when_explicitly_authorized"


def test_hold_source_due_to_margin_validation_warning_produces_required_status(tmp_path: Path) -> None:
    margin_dir = write_margin_artifacts(
        tmp_path / "margin",
        manifest_data=margin_manifest(
            plan_status="margin_feasibility_hold_requires_broker_margin_validation",
            source_nature="live_data_shadow_signal",
        ),
    )
    outputs = broker_margin.build_outputs(make_args(tmp_path, margin_dir=margin_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "broker_safe_margin_validation_plan_required_due_to_margin_warning"


def test_missing_volume_source_produces_hold(tmp_path: Path) -> None:
    margin_dir = write_margin_artifacts(
        tmp_path / "margin",
        manifest_data=margin_manifest(
            plan_status="margin_feasibility_formula_only_missing_volume",
            risk_amount=None,
            approximate_margin_usage_ratio=None,
            estimated_margin_quote=None,
        ),
        warning_rows=[],
    )
    outputs = broker_margin.build_outputs(make_args(tmp_path, margin_dir=margin_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "hold_missing_volume_for_margin_validation_plan"
    assert manifest["recommended_next_step"] == "rerun_risk_volume_shadow_plan_with_policy_equity"


def test_noncanonical_registry_blocks(tmp_path: Path) -> None:
    outputs = broker_margin.build_outputs(make_args(tmp_path, registry_data=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_config_boundary"


def test_bad_execution_policy_blocks(tmp_path: Path) -> None:
    outputs = broker_margin.build_outputs(make_args(tmp_path, policy_data=execution_policy(max_margin_usage_ratio=0.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_demo_execution_policy"


def test_missing_no_order_flag_blocks(tmp_path: Path) -> None:
    source = margin_manifest()
    source.pop("no_order_check_called")
    margin_dir = write_margin_artifacts(tmp_path / "margin", manifest_data=source)
    outputs = broker_margin.build_outputs(make_args(tmp_path, margin_dir=margin_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_no_order_boundary"


def test_unsafe_no_order_flag_false_blocks(tmp_path: Path) -> None:
    margin_dir = write_margin_artifacts(tmp_path / "margin", manifest_data=margin_manifest(no_order_request_constructed=False))
    outputs = broker_margin.build_outputs(make_args(tmp_path, margin_dir=margin_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_no_order_boundary"


def test_allowed_future_calls_include_margin_estimator_only(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["allowed_calls"])
    row = next(item for item in rows if item["future_call_label"] == "future_order_calc_margin_for_margin_estimate_only")

    assert row["call_name"] == "order_calc_margin"
    assert row["allowed_future"] == "true"
    assert row["current_module_called"] == "false"
    assert "separate" in row["caveat"]


def test_forbidden_future_calls_are_listed(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["allowed_calls"])
    forbidden = {row["call_name"]: row for row in rows if row["allowed_future"] == "false"}

    assert {"order_send", "order_check", "order_calc_profit", "positions_get", "orders_get", "history_orders_get", "history_deals_get"} <= set(forbidden)
    assert all(row["current_module_called"] == "false" for row in forbidden.values())


def test_future_requirements_include_authorization_and_demo_reconfirmation(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["requirements"])
    names = {row["requirement_name"] for row in rows}

    assert "explicit_user_authorization_required" in names
    assert "account_mode_reconfirmed_demo" in names
    assert "no_broker_structure_constructed" in names
    assert "order_calc_margin_estimator_only" in names


def test_future_artifacts_include_margin_snapshot_and_no_order_evidence(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_artifacts"])
    names = {row["future_artifact_name"] for row in rows}

    assert "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json" in names
    assert "fixed_candidate_demo_broker_safe_margin_validation_no_order_evidence.csv" in names


def test_report_states_current_module_does_not_call_margin_calc(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "The current module does not call order_calc_margin." in report


def test_report_states_future_margin_calc_is_separate_authorized_module(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Future order_calc_margin may be allowed only in a separate explicitly authorized module" in report


def test_report_states_no_forbidden_order_calls(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")

    assert "does not call order_check, order_send, or order_calc_profit" in report
    assert "must not send, check, or profit-calculate orders" in report


def test_manifest_counts_match_csvs_and_warnings(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["allowed_future_call_row_count"] == len(read_csv(outputs["allowed_calls"]))
    assert manifest["requirement_row_count"] == len(read_csv(outputs["requirements"]))
    assert manifest["future_artifact_row_count"] == len(read_csv(outputs["future_artifacts"]))
    assert manifest["warnings_count"] == len(read_csv(outputs["warnings"]))


def test_static_source_has_no_forbidden_call_signatures() -> None:
    source = Path("scripts/build_fixed_candidate_demo_broker_safe_margin_validation_plan.py").read_text(encoding="utf-8")
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
    source = Path("scripts/build_fixed_candidate_demo_broker_safe_margin_validation_plan.py").read_text(encoding="utf-8")
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
    source = Path("scripts/build_fixed_candidate_demo_broker_safe_margin_validation_plan.py").read_text(encoding="utf-8")
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
    assert manifest["no_mt5_connection_performed"] is True
    assert manifest["no_order_execution_performed"] is True
