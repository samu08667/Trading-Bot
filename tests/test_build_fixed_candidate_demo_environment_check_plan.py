from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_environment_check_plan as plan


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


def readiness_manifest(readiness_status: str = "demo_readiness_plan_available_with_caveats") -> dict[str, object]:
    return {
        "run_id": "fixture_demo_readiness",
        "readiness_status": readiness_status,
        "recommended_next_step": "build_fixed_candidate_demo_environment_check_plan",
        "checklist_row_count": 18,
        "blocking_checklist_item_count": 18,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_trading_decision_performed": True,
    }


def readiness_checklist_rows() -> list[dict[str, object]]:
    items = [
        ("broker_environment", "confirm account is demo, not real"),
        ("broker_environment", "confirm terminal/broker connection only in separate future check"),
        ("symbol_contract", "confirm GBPUSD symbol visible/tradable in demo account"),
        ("symbol_contract", "confirm min lot, max lot, lot step"),
        ("symbol_contract", "confirm point/tick size"),
        ("symbol_contract", "confirm stop level and freeze level"),
        ("spread_policy", "confirm spread source and spread sanity"),
        ("spread_policy", "confirm max spread gate uses same units as broker symbol"),
        ("account_safety", "confirm volume/risk calculation uses demo balance only"),
        ("state_safety", "confirm one-open-trade enforcement"),
        ("execution_safety", "confirm no duplicate order protection"),
        ("execution_safety", "confirm SL/TP attached at placement"),
        ("timeout_policy", "confirm timeout h10 closure logic"),
        ("state_reconciliation", "confirm reconciliation between local state and broker state"),
        ("state_reconciliation", "confirm crash/restart recovery"),
        ("kill_switch", "confirm kill-switch behavior"),
        ("audit_logging", "confirm full audit log"),
        ("execution_safety", "confirm dry-run/no-order execution test before any demo order"),
    ]
    return [
        {
            "run_id": "fixture_demo_readiness",
            "checklist_area": area,
            "checklist_item": item,
            "required_before": "future environment check",
            "check_status": "not_checked_future_artifact_required",
            "source_or_future_artifact": "build_fixed_candidate_demo_environment_check_plan",
            "blocking_if_failed": True,
            "caveat": "future_manual_check_required",
        }
        for area, item in items
    ]


def write_fixture_sources(
    tmp_path: Path,
    *,
    config_payload: dict[str, object] | None = None,
    readiness_status: str = "demo_readiness_plan_available_with_caveats",
    missing_manifest: bool = False,
    missing_checklist: bool = False,
) -> dict[str, Path]:
    config_path = tmp_path / "config" / "demo_config.json"
    write_json(config_path, config_payload if config_payload is not None else demo_config())

    readiness_dir = tmp_path / "demo_readiness"
    readiness_dir.mkdir(parents=True, exist_ok=True)
    if not missing_manifest:
        write_json(readiness_dir / plan.READINESS_PLAN_MANIFEST, readiness_manifest(readiness_status))
    (readiness_dir / plan.READINESS_PLAN_REPORT).write_text("# Demo readiness\n", encoding="utf-8")
    write_csv(readiness_dir / plan.READINESS_PLAN_CSV, ["run_id", "readiness_area"], [{"run_id": "fixture", "readiness_area": "ok"}])
    if not missing_checklist:
        write_csv(readiness_dir / plan.READINESS_PLAN_CHECKLIST, [
            "run_id",
            "checklist_area",
            "checklist_item",
            "required_before",
            "check_status",
            "source_or_future_artifact",
            "blocking_if_failed",
            "caveat",
        ], readiness_checklist_rows())
    write_csv(readiness_dir / plan.READINESS_PLAN_WARNINGS, plan.WARNING_FIELDNAMES, [])

    spec_dir = tmp_path / "demo_spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        spec_dir / plan.SPEC_MANIFEST,
        {
            "paper_only_specification": True,
            "no_broker_connection_performed": True,
            "no_order_execution_performed": True,
            "no_trading_decision_performed": True,
        },
    )
    write_csv(spec_dir / plan.SPEC_CSV, ["run_id", "row"], [{"run_id": "fixture", "row": "ok"}])
    (spec_dir / plan.SPEC_REPORT).write_text("# Demo spec\n", encoding="utf-8")

    return {"config": config_path, "readiness": readiness_dir, "spec": spec_dir}


def make_args(tmp_path: Path, paths: dict[str, Path]) -> object:
    return plan.build_parser().parse_args(
        [
            "--run-id",
            "unit_demo_environment_check_plan",
            "--demo-readiness-plan-dir",
            str(paths["readiness"]),
            "--demo-strategy-config",
            str(paths["config"]),
            "--demo-strategy-spec-dir",
            str(paths["spec"]),
            "--future-environment-check-script",
            str(tmp_path / "scripts" / "check_fixed_candidate_demo_environment.py"),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_default_paths_reference_spread15_canonical_chain() -> None:
    args = plan.build_parser().parse_args([])

    assert "demo_readiness_plan_spread15_v1" in str(args.demo_readiness_plan_dir)
    assert "demo_strategy_spec_v5_spread15" in str(args.demo_strategy_spec_dir)


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))

    assert outputs["plan"].exists()
    assert outputs["requirements"].exists()
    assert outputs["future_artifacts"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_valid_demo_readiness_plan_produces_available_with_caveats(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "demo_environment_check_plan_available_with_caveats"
    assert manifest["recommended_next_step"] == "implement_check_fixed_candidate_demo_environment"
    assert manifest["spread_unit"] == "broker_points"
    assert manifest["max_spread_points"] == 15.0
    assert manifest["spread_policy_matches_canonical"] is True


def test_blocked_demo_readiness_status_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, readiness_status="blocked_by_config_boundary")
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_demo_readiness_status"


def test_unsafe_config_boundary_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, config_payload=demo_config(paper_only=False))
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_by_config_boundary"
    assert manifest["blocking_warnings_count"] >= 1


def test_missing_demo_readiness_manifest_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_manifest=True)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_required_artifact"


def test_missing_checklist_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_checklist=True)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_required_artifact"


def test_requirements_include_core_future_check_areas(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    requirements = read_csv(outputs["requirements"])
    areas = {row["requirement_area"] for row in requirements}

    for expected in [
        "account_mode_check",
        "terminal_connection_check",
        "symbol_contract_check",
        "spread_unit_check",
        "risk_sizing_check",
        "broker_state_reconciliation_check",
        "kill_switch_check",
        "audit_logging_check",
        "dry_run_no_order_check",
    ]:
        assert expected in areas


def test_future_artifacts_include_manifest_report_checklist_and_warnings(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    future_artifacts = read_csv(outputs["future_artifacts"])
    names = {row["future_artifact_name"] for row in future_artifacts}

    assert "fixed_candidate_demo_environment_check_manifest.json" in names
    assert "fixed_candidate_demo_environment_check_report.md" in names
    assert "fixed_candidate_demo_environment_check_checklist.csv" in names
    assert "fixed_candidate_demo_environment_check_warnings.csv" in names


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


def test_report_includes_no_connection_query_order_db_and_demo_approval_caveats(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No account query was performed." in report
    assert "No symbol query was performed." in report
    assert "No order execution was performed." in report
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
