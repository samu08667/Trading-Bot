from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_no_order_dry_run_plan as plan


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def demo_config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "schema_version": 1,
        "config_role": "paper_demo_strategy_config",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "paper_only": True,
        "broker_connection_allowed": False,
        "order_execution_allowed": False,
        "real_money_allowed": False,
        "candidate": {
            "symbol": "GBPUSD",
            "direction": "short",
            "timeframe": "M15",
            "target_horizon": 10,
            "target_family": "preferred_1_5atr_1atr_hit_first",
        },
        "entry_rule": {
            "regime_column": "hour_session",
            "regime_value": "Off_hours",
            "exact_condition": (
                "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
                "numeric_tercile:tick_volume_percentile_100:mid_tercile"
            ),
        },
        "risk_reward": {
            "tp_atr": 1.5,
            "sl_atr": 1.0,
            "atr_column": "atr_20",
            "same_bar_policy": "stop_first",
        },
        "demo_risk_controls": {
            "risk_per_trade_note": "1% demo equity per trade; paper/demo only; no real-money sizing",
            "max_open_positions_note": "Maximum 1 open paper/demo trade at a time",
        },
        "spread_and_session_controls": {
            "max_spread_points": 15.0,
            "spread_unit": "broker_points",
            "spread_policy_status": "configured_numeric_threshold",
        },
        "kill_switch": {
            "conditions": [
                "required_data_missing",
                "required_features_missing",
                "spread_abnormal_or_not_configured",
                "atr_calculation_failed",
                "timeframe_mismatch",
                "session_mismatch",
                "existing_paper_demo_trade_open",
            ]
        },
        "logging": {"required_fields": ["timestamp", "symbol", "signal_state", "kill_switch_state"]},
    }
    config.update(overrides)
    return config


def env_manifest(
    *,
    status: str = "environment_check_available_with_caveats",
    spread_unit: str = "broker_points",
    max_spread_points: float = 15.0,
    spread_current_points: float = 6.0,
    spread_within_gate: bool = True,
    spread_policy_matches: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_environment_check",
        "environment_check_status": status,
        "recommended_next_step": "build_fixed_candidate_demo_no_order_dry_run_plan",
        "account_mode_label": "demo",
        "is_demo_account": True,
        "terminal_info_available": True,
        "account_info_available": True,
        "symbol_info_available": True,
        "symbol_tick_available": True,
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "spread_unit": spread_unit,
        "max_spread_points": max_spread_points,
        "spread_current_points": spread_current_points,
        "spread_within_config_gate": spread_within_gate,
        "spread_policy_matches_canonical": spread_policy_matches,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "point": 0.00001,
        "digits": 5,
        "trade_tick_size": 0.00001,
        "trade_tick_value": 0.8576,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
        "failed_blocking_requirement_count": 0,
        "blocking_warnings_count": 0,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_db_mutation_performed": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    return payload


def account_snapshot(*, demo: bool = True) -> dict[str, object]:
    return {
        "account_trade_mode_raw": 0 if demo else 2,
        "account_trade_mode_label": "demo" if demo else "real",
        "leverage": 100,
        "currency": "USD",
        "balance_present": True,
        "equity_present": True,
        "margin_mode": 2,
        "trade_allowed": True,
        "trade_expert": True,
        "is_demo_account": demo,
        "redaction_applied": True,
    }


def symbol_snapshot(
    *,
    spread_unit: str = "broker_points",
    max_spread_points: float = 15.0,
    spread_current_points: float = 6.0,
    spread_within_gate: bool = True,
) -> dict[str, object]:
    return {
        "symbol": "GBPUSD",
        "visible": True,
        "select": True,
        "trade_mode": 4,
        "trade_contract_size": 100000.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "point": 0.00001,
        "digits": 5,
        "trade_tick_size": 0.00001,
        "trade_tick_value": 0.8576,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
        "spread": int(spread_current_points),
        "spread_float": True,
        "bid": 1.25001,
        "ask": 1.25007,
        "time": 1770000000,
        "currency_base": "GBP",
        "currency_profit": "USD",
        "currency_margin": "GBP",
        "spread_unit": spread_unit,
        "max_spread_points": max_spread_points,
        "spread_current_points": spread_current_points,
        "spread_within_config_gate": spread_within_gate,
    }


def thresholds_json() -> dict[str, object]:
    return {
        "schema_version": 1,
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "features": {
            "close_to_ma_fast_atr_20": {
                "lower_tercile_boundary": -0.45,
                "upper_tercile_boundary": 0.59,
            },
            "tick_volume_percentile_100": {
                "lower_tercile_boundary": 0.15,
                "upper_tercile_boundary": 0.37,
            },
        },
    }


def env_plan_manifest(plan_status: str = "demo_environment_check_plan_available_with_caveats") -> dict[str, object]:
    return {
        "run_id": "fixture_environment_plan",
        "plan_status": plan_status,
        "recommended_next_step": "implement_check_fixed_candidate_demo_environment",
        "config_spread_policy_matches_canonical": True,
        "config_spread_unit": "broker_points",
        "config_max_spread_points": 15.0,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_trading_decision_performed": True,
    }


def readiness_manifest() -> dict[str, object]:
    return {
        "run_id": "fixture_demo_readiness",
        "readiness_status": "demo_readiness_plan_available_with_caveats",
        "recommended_next_step": "build_fixed_candidate_demo_environment_check_plan",
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_trading_decision_performed": True,
    }


def spec_manifest() -> dict[str, object]:
    return {
        "run_id": "fixture_demo_spec",
        "paper_only_specification": True,
        "max_spread_points": 15.0,
        "spread_unit": "broker_points",
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_trading_decision_performed": True,
    }


def write_fixture_sources(
    tmp_path: Path,
    *,
    config_payload: dict[str, object] | None = None,
    env_status: str = "environment_check_available_with_caveats",
    missing_env_manifest: bool = False,
    missing_account_snapshot: bool = False,
    missing_symbol_snapshot: bool = False,
    account_demo: bool = True,
    spread_unit: str = "broker_points",
    max_spread_points: float = 15.0,
    spread_current_points: float = 6.0,
    spread_within_gate: bool = True,
    spread_policy_matches: bool = True,
) -> dict[str, Path]:
    config_path = tmp_path / "config" / "demo_config.json"
    write_json(config_path, config_payload if config_payload is not None else demo_config())

    env_dir = tmp_path / "environment_check"
    env_dir.mkdir(parents=True, exist_ok=True)
    if not missing_env_manifest:
        write_json(
            env_dir / plan.ENV_MANIFEST,
            env_manifest(
                status=env_status,
                spread_unit=spread_unit,
                max_spread_points=max_spread_points,
                spread_current_points=spread_current_points,
                spread_within_gate=spread_within_gate,
                spread_policy_matches=spread_policy_matches,
            ),
        )
    (env_dir / plan.ENV_REPORT).write_text("# Environment check\n", encoding="utf-8")
    write_csv(env_dir / plan.ENV_CHECKLIST, ["run_id", "check_area", "check_status"], [{"run_id": "fixture", "check_area": "ok", "check_status": "passed"}])
    write_csv(env_dir / plan.ENV_REQUIREMENTS, ["run_id", "requirement_area", "check_status"], [{"run_id": "fixture", "requirement_area": "ok", "check_status": "passed"}])
    write_csv(env_dir / plan.ENV_WARNINGS, plan.WARNING_FIELDNAMES, [])
    if not missing_account_snapshot:
        write_json(env_dir / plan.ENV_ACCOUNT_SNAPSHOT, account_snapshot(demo=account_demo))
    if not missing_symbol_snapshot:
        write_json(
            env_dir / plan.ENV_SYMBOL_SNAPSHOT,
            symbol_snapshot(
                spread_unit=spread_unit,
                max_spread_points=max_spread_points,
                spread_current_points=spread_current_points,
                spread_within_gate=spread_within_gate,
            ),
        )
    write_csv(
        env_dir / plan.ENV_NO_ORDER,
        [
            "run_id",
            "no_order_execution_performed",
            "no_order_request_constructed",
            "mt5_order_send_used",
            "mt5_order_check_used",
            "mt5_order_calc_margin_used",
            "mt5_order_calc_profit_used",
        ],
        [
            {
                "run_id": "fixture",
                "no_order_execution_performed": "true",
                "no_order_request_constructed": "true",
                "mt5_order_send_used": "false",
                "mt5_order_check_used": "false",
                "mt5_order_calc_margin_used": "false",
                "mt5_order_calc_profit_used": "false",
            }
        ],
    )

    env_plan_dir = tmp_path / "environment_plan"
    env_plan_dir.mkdir(parents=True, exist_ok=True)
    write_json(env_plan_dir / plan.ENV_PLAN_MANIFEST, env_plan_manifest())
    write_csv(env_plan_dir / plan.ENV_PLAN_REQUIREMENTS, ["run_id", "requirement_area"], [{"run_id": "fixture", "requirement_area": "ok"}])
    write_csv(env_plan_dir / plan.ENV_PLAN_FUTURE_ARTIFACTS, ["run_id", "future_artifact_name"], [{"run_id": "fixture", "future_artifact_name": "ok"}])
    write_csv(env_plan_dir / plan.ENV_PLAN_WARNINGS, plan.WARNING_FIELDNAMES, [])

    readiness_dir = tmp_path / "demo_readiness"
    readiness_dir.mkdir(parents=True, exist_ok=True)
    write_json(readiness_dir / plan.READINESS_MANIFEST, readiness_manifest())
    write_csv(readiness_dir / plan.READINESS_CHECKLIST, ["run_id", "checklist_area"], [{"run_id": "fixture", "checklist_area": "ok"}])
    write_csv(readiness_dir / plan.READINESS_WARNINGS, plan.WARNING_FIELDNAMES, [])

    spec_dir = tmp_path / "demo_spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    write_json(spec_dir / plan.SPEC_MANIFEST, spec_manifest())
    write_csv(spec_dir / plan.SPEC_CSV, ["run_id", "row"], [{"run_id": "fixture", "row": "ok"}])
    write_csv(spec_dir / plan.SPEC_WARNINGS, plan.WARNING_FIELDNAMES, [])

    thresholds_path = tmp_path / "thresholds" / "fixed_candidate_numeric_tercile_thresholds.json"
    write_json(thresholds_path, thresholds_json())

    return {
        "config": config_path,
        "env": env_dir,
        "env_plan": env_plan_dir,
        "readiness": readiness_dir,
        "spec": spec_dir,
        "thresholds": thresholds_path,
    }


def make_args(tmp_path: Path, paths: dict[str, Path]) -> object:
    return plan.build_parser().parse_args(
        [
            "--run-id",
            "unit_demo_no_order_dry_run_plan",
            "--demo-environment-check-dir",
            str(paths["env"]),
            "--demo-environment-check-plan-dir",
            str(paths["env_plan"]),
            "--demo-readiness-plan-dir",
            str(paths["readiness"]),
            "--demo-strategy-spec-dir",
            str(paths["spec"]),
            "--demo-strategy-config",
            str(paths["config"]),
            "--tercile-thresholds-json",
            str(paths["thresholds"]),
            "--future-no-order-dry-run-script",
            str(tmp_path / "scripts" / "run_fixed_candidate_demo_no_order_dry_run.py"),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))

    assert outputs["plan"].exists()
    assert outputs["requirements"].exists()
    assert outputs["future_artifacts"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_valid_source_chain_produces_available_with_caveats(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "demo_no_order_dry_run_plan_available_with_caveats"
    assert manifest["recommended_next_step"] == "implement_run_fixed_candidate_demo_no_order_dry_run"
    assert manifest["spread_unit"] == "broker_points"
    assert manifest["max_spread_points"] == 15.0


def test_dry_run_only_environment_check_status_holds(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, env_status="dry_run_no_mt5_query_performed")
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "hold_before_no_order_dry_run"


def test_blocked_environment_check_status_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, env_status="blocked_mt5_initialize_failed")
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_environment_check_status"


def test_unsafe_config_boundary_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, config_payload=demo_config(paper_only=False))
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_config_boundary"
    assert manifest["blocking_warnings_count"] >= 1


def test_missing_environment_check_manifest_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_env_manifest=True)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_required_artifact"


def test_missing_account_snapshot_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_account_snapshot=True)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_required_artifact"


def test_missing_symbol_contract_snapshot_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_symbol_snapshot=True)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_required_artifact"


def test_non_demo_account_snapshot_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, account_demo=False)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_environment_check_status"
    assert manifest["blocking_warnings_count"] >= 1


def test_spread_policy_not_canonical_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(
        tmp_path,
        spread_unit="pips",
        max_spread_points=1.5,
        spread_policy_matches=False,
    )
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["plan_status"] == "blocked_by_config_boundary"
    assert any(row["warning_code"] == "spread_policy_not_canonical_or_outside_gate" for row in warnings)


def test_spread_outside_gate_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(
        tmp_path,
        spread_current_points=20.0,
        spread_within_gate=False,
    )
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_config_boundary"
    assert manifest["spread_current_points"] == 20.0


def test_requirements_include_core_no_order_decision_areas(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    requirements = read_csv(outputs["requirements"])
    areas = {row["requirement_area"] for row in requirements}

    for expected in [
        "would_skip_path",
        "would_signal_path",
        "would_block_path",
        "no_order_evidence",
        "one_open_trade_state",
        "duplicate_protection_required",
        "kill_switch_required",
        "audit_logging_required",
    ]:
        assert expected in areas


def test_future_artifacts_include_required_no_order_outputs(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    future_artifacts = read_csv(outputs["future_artifacts"])
    names = {row["future_artifact_name"] for row in future_artifacts}

    for expected in [
        "fixed_candidate_demo_no_order_dry_run_manifest.json",
        "fixed_candidate_demo_no_order_dry_run_report.md",
        "fixed_candidate_demo_no_order_dry_run_decision.csv",
        "fixed_candidate_demo_no_order_dry_run_checklist.csv",
        "fixed_candidate_demo_no_order_dry_run_warnings.csv",
        "fixed_candidate_demo_no_order_dry_run_no_order_evidence.csv",
        "fixed_candidate_demo_no_order_dry_run_state_preview.json",
    ]:
        assert expected in names


def test_manifest_counts_match_csvs_and_warnings(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    requirements = read_csv(outputs["requirements"])
    future_artifacts = read_csv(outputs["future_artifacts"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["requirement_row_count"] == len(requirements)
    assert manifest["future_artifact_row_count"] == len(future_artifacts)
    assert manifest["blocking_requirement_count"] == sum(
        1 for row in requirements if row["blocking_if_failed"].lower() == "true"
    )
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(
        1 for warning in warnings if warning["blocking_warning"].lower() == "true"
    )


def test_report_includes_no_connection_query_order_request_and_approval_caveats(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No account query was performed." in report
    assert "No symbol query was performed." in report
    assert "No order execution was performed." in report
    assert "No order request was constructed." in report
    assert "No order_check or order_calc call was performed." in report
    assert "No database mutation was performed." in report
    assert "This plan is not demo broker approval." in report


def test_no_db_queries_are_performed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("DB query should not be performed")

    monkeypatch.setattr(sqlite3, "connect", fail_if_called)
    plan.build_outputs(make_args(tmp_path, paths))


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    plan.build_outputs(make_args(tmp_path, paths))


def test_static_source_has_no_forbidden_order_function_calls() -> None:
    source = Path(plan.__file__).read_text(encoding="utf-8")
    forbidden = [
        "order_" + "send(",
        "order_" + "check(",
        "order_" + "calc_margin(",
        "order_" + "calc_profit(",
        "positions_" + "get(",
        "orders_" + "get(",
        "history_orders_" + "get(",
        "history_deals_" + "get(",
    ]

    for token in forbidden:
        assert token not in source
