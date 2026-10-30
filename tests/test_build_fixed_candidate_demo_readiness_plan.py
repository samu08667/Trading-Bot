from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_readiness_plan as plan


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
            "timeout_note": "Close/evaluate after h10 is reached in all cases if neither TP nor SL is hit first",
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
        "logging": {"required_fields": ["timestamp", "symbol"]},
    }
    config.update(overrides)
    return config


def base_manifest(status_key: str, status_value: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_source",
        status_key: status_value,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_optimization_performed": True,
        "no_trading_decision_performed": True,
    }
    payload.update(overrides)
    return payload


def write_bundle(
    root: Path,
    csv_name: str,
    manifest_name: str,
    report_name: str,
    warnings_name: str,
    manifest: dict[str, object],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    write_csv(root / csv_name, ["run_id", "row"], [{"run_id": "fixture", "row": "ok"}])
    write_json(root / manifest_name, manifest)
    (root / report_name).write_text("# Report\n", encoding="utf-8")
    write_csv(root / warnings_name, plan.WARNING_FIELDNAMES, [])


def write_fixture_sources(
    tmp_path: Path,
    *,
    config_payload: dict[str, object] | None = None,
    missing_config: bool = False,
    replay_status: str = "continue_paper_validation",
    cost_status: str = "continue_paper_validation_with_cost_caveat",
    holdout_status: str = "continue_paper_validation_recent_period_ok",
    missing_replay_review: bool = False,
    missing_cost_review: bool = False,
    missing_holdout_review: bool = False,
) -> dict[str, Path]:
    config_path = tmp_path / "config" / "demo_config.json"
    if not missing_config:
        write_json(config_path, config_payload if config_payload is not None else demo_config())
    spec_dir = tmp_path / "spec"
    replay_dir = tmp_path / "replay_review"
    cost_dir = tmp_path / "cost_review"
    holdout_dir = tmp_path / "holdout_review"
    write_bundle(
        spec_dir,
        plan.SPEC_CSV,
        plan.SPEC_MANIFEST,
        plan.SPEC_REPORT,
        plan.SPEC_WARNINGS,
        {
            "paper_only_specification": True,
            "no_broker_connection_performed": True,
            "no_order_execution_performed": True,
            "no_db_mutation_performed": True,
            "no_data_generation_performed": True,
            "no_feature_refresh_performed": True,
            "no_optimization_performed": True,
            "no_trading_decision_performed": True,
        },
    )
    if not missing_replay_review:
        write_bundle(
            replay_dir,
            plan.REPLAY_REVIEW_CSV,
            plan.REPLAY_REVIEW_MANIFEST,
            plan.REPLAY_REVIEW_REPORT,
            plan.REPLAY_REVIEW_WARNINGS,
            base_manifest("review_status", replay_status),
        )
    if not missing_cost_review:
        write_bundle(
            cost_dir,
            plan.COST_REVIEW_CSV,
            plan.COST_REVIEW_MANIFEST,
            plan.COST_REVIEW_REPORT,
            plan.COST_REVIEW_WARNINGS,
            base_manifest(
                "review_status",
                cost_status,
                timeout_negative_under_severe=True,
                timeout_negative_under_stress=True,
            ),
        )
    if not missing_holdout_review:
        write_bundle(
            holdout_dir,
            plan.HOLDOUT_REVIEW_CSV,
            plan.HOLDOUT_REVIEW_MANIFEST,
            plan.HOLDOUT_REVIEW_REPORT,
            plan.HOLDOUT_REVIEW_WARNINGS,
            base_manifest("review_status", holdout_status),
        )
    return {
        "config": config_path,
        "spec": spec_dir,
        "replay": replay_dir,
        "cost": cost_dir,
        "holdout": holdout_dir,
    }


def make_args(tmp_path: Path, paths: dict[str, Path]) -> object:
    return plan.build_parser().parse_args(
        [
            "--run-id",
            "unit_demo_readiness_plan",
            "--demo-strategy-config",
            str(paths["config"]),
            "--demo-strategy-spec-dir",
            str(paths["spec"]),
            "--replay-review-dir",
            str(paths["replay"]),
            "--cost-sensitivity-review-dir",
            str(paths["cost"]),
            "--recent-period-holdout-review-dir",
            str(paths["holdout"]),
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

    assert "demo_strategy_spec_v5_spread15" in str(args.demo_strategy_spec_dir)
    assert "fixed_rule_replay_spread15_review_v1" in str(args.replay_review_dir)
    assert "replay_cost_sensitivity_review_spread15_v1" in str(args.cost_sensitivity_review_dir)
    assert "recent_period_holdout_review_spread15_v1" in str(args.recent_period_holdout_review_dir)


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))

    assert outputs["plan"].exists()
    assert outputs["checklist"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_valid_source_chain_produces_available_with_caveats(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["readiness_status"] == "demo_readiness_plan_available_with_caveats"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_demo_environment_check_plan"
    assert manifest["spread_unit"] == "broker_points"
    assert manifest["max_spread_points"] == 15.0
    assert manifest["spread_policy_matches_canonical"] is True


def test_weak_hold_source_status_holds_before_demo_readiness(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, holdout_status="hold_for_recent_period_weakness")
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["readiness_status"] == "hold_before_demo_readiness"


def test_blocked_source_status_blocks_by_source_review_status(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, cost_status="blocked_missing_required_artifact")
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["readiness_status"] == "blocked_by_source_review_status"


def test_unsafe_config_boundary_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, config_payload=demo_config(paper_only=False))
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["readiness_status"] == "blocked_by_config_boundary"
    assert manifest["blocking_warnings_count"] >= 1


def test_missing_config_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_config=True)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["readiness_status"] == "blocked_missing_required_artifact"


def test_missing_replay_review_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_replay_review=True)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["readiness_status"] == "blocked_missing_required_artifact"


def test_missing_cost_sensitivity_review_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_cost_review=True)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["readiness_status"] == "blocked_missing_required_artifact"


def test_missing_recent_holdout_review_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_holdout_review=True)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["readiness_status"] == "blocked_missing_required_artifact"


def test_checklist_contains_required_future_check_areas(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    checklist = read_csv(outputs["checklist"])
    text = "\n".join(f"{row['checklist_area']} {row['checklist_item']}" for row in checklist)

    for expected in [
        "broker_environment",
        "account_safety",
        "symbol_contract",
        "execution_safety",
        "state_reconciliation",
        "kill_switch",
        "audit_logging",
    ]:
        assert expected in text
    assert "confirm dry-run/no-order execution test before any demo order" in text


def test_manifest_counts_match_csvs_warnings_and_checklist(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])
    checklist = read_csv(outputs["checklist"])

    assert manifest["checklist_row_count"] == len(checklist)
    assert manifest["blocking_checklist_item_count"] == sum(
        1 for row in checklist if row["blocking_if_failed"].lower() == "true"
    )
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(
        1 for warning in warnings if warning["blocking_warning"].lower() == "true"
    )


def test_report_includes_no_broker_api_mt5_order_db_mutation_demo_approval_caveats(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = plan.build_outputs(make_args(tmp_path, paths))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5, broker/API, or external connection was performed." in report
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
