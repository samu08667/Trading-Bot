from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_paper_signal_logger_readiness as readiness


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


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
            "candidate_framing": "risk_filtered_candidate",
            "baseline_reference": "single_filter_a",
        },
        "entry_rule": {
            "regime_column": "hour_session",
            "regime_value": "Off_hours",
            "exact_condition": "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND numeric_tercile:tick_volume_percentile_100:mid_tercile",
            "entry_description": "Short GBPUSD M15 only when hour_session=Off_hours and the exact feature condition is true",
        },
        "risk_reward": {
            "tp_atr": 1.5,
            "sl_atr": 1.0,
            "atr_column": "atr_20",
            "same_bar_policy": "stop_first",
            "timeout_note": "Close/evaluate after h10 is reached in all cases if neither TP nor SL is hit first",
        },
        "cost_assumptions": {
            "p75_cost_config": "config/brokers/pepperstone_historical_p75.local.json",
            "p90_cost_config": "config/brokers/pepperstone_historical_p90.local.json",
        },
        "demo_risk_controls": {
            "risk_per_trade_note": "1% demo equity per trade; paper/demo only; no real-money sizing",
            "max_daily_stop_note": "No fixed daily stop for initial paper/demo monitoring; daily PnL must still be logged",
            "max_weekly_stop_note": "No fixed weekly stop for initial paper/demo monitoring; weekly PnL must still be logged",
            "max_open_positions_note": "Maximum 1 open paper/demo trade at a time",
            "max_daily_trades_note": "No fixed max daily trade count; signals remain limited by the one-open-trade rule and logging requirements",
        },
        "spread_and_session_controls": {
            "spread_threshold_note": "Skip new paper/demo signals if spread exceeds max_spread_points",
            "max_spread_points": 15.0,
            "spread_unit": "broker_points",
            "spread_policy_status": "configured_numeric_threshold",
            "spread_policy_action_when_exceeded": "skip_new_signal",
            "spread_policy_action_when_missing": "skip_new_signal",
            "session_filter_note": "hour_session=Off_hours only",
        },
        "kill_switch": {
            "kill_switch_note": "Disable new paper/demo signals if required data is missing",
            "conditions": list(readiness.REQUIRED_KILL_SWITCH_CONDITIONS),
        },
        "logging": {
            "logging_note": "Log paper signal decisions and skipped reasons",
            "required_fields": list(readiness.REQUIRED_LOGGING_FIELDS),
        },
        "paper_broker_mode": {
            "paper_broker_mode_note": "Paper logging now; demo broker preparation later",
        },
    }
    config.update(overrides)
    return config


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_demo_spec_dir(path: Path) -> None:
    write_csv(
        path / readiness.SPEC_CSV,
        ["spec_section", "spec_key", "spec_value"],
        [{"spec_section": "paper_execution_boundary", "spec_key": "boundary", "spec_value": "paper_only"}],
    )
    write_json(
        path / readiness.SPEC_MANIFEST,
        {
            "run_id": "fixture_demo_spec",
            "paper_only_specification": True,
            "no_broker_connection_performed": True,
            "no_order_execution_performed": True,
            "no_trading_decision_performed": True,
            "warnings_count": 0,
            "blocking_warnings_count": 0,
        },
    )
    (path / readiness.SPEC_REPORT).write_text("# Demo spec\npaper/local only\n", encoding="utf-8")
    write_csv(path / readiness.SPEC_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_command_plan_dir(path: Path) -> None:
    write_csv(
        path / readiness.PLAN_CSV,
        ["plan_step", "command_status"],
        [{"plan_step": "paper_runner_script_status", "command_status": "implementation_required"}],
    )
    write_json(
        path / readiness.PLAN_MANIFEST,
        {
            "run_id": "fixture_command_plan",
            "paper_only_boundary_confirmed": True,
            "no_broker_connection_allowed": True,
            "no_order_execution_allowed": True,
            "real_money_not_allowed": True,
            "warnings_count": 0,
            "blocking_warnings_count": 0,
        },
    )
    (path / readiness.PLAN_REPORT).write_text("# Command plan\ncommand-plan-only\n", encoding="utf-8")
    write_csv(path / readiness.PLAN_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_feature_db(path: Path, table: str = "price_features", *, missing_column: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(readiness.REQUIRED_SOURCE_COLUMNS) + ["symbol", "timeframe", "tick_volume"]
    if missing_column:
        columns = [column for column in columns if column != missing_column]
    with sqlite3.connect(path) as connection:
        column_sql = ", ".join(f'"{column}" TEXT' for column in columns)
        connection.execute(f'CREATE TABLE "{table}" ({column_sql})')
    return path


def threshold_json() -> dict[str, object]:
    return {
        "schema_version": 1,
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "features": {
            "close_to_ma_fast_atr_20": {
                "high_tercile": {"lower_bound": 0.75},
            },
            "tick_volume_percentile_100": {
                "mid_tercile": {"lower_bound": 0.33, "upper_bound": 0.66},
            },
        },
    }


def make_args(
    tmp_path: Path,
    *,
    config: dict[str, object] | None = None,
    table: str = "price_features",
    db_missing: bool = False,
    missing_column: str | None = None,
    threshold_missing: bool = False,
    threshold_payload: object | None = None,
    invalid_threshold_text: str | None = None,
) -> object:
    spec_dir = tmp_path / "demo_spec"
    plan_dir = tmp_path / "command_plan"
    write_demo_spec_dir(spec_dir)
    write_command_plan_dir(plan_dir)
    config_path = write_json(tmp_path / "config" / "demo_strategy_config.json", config or demo_config())
    db_path = tmp_path / "db" / "trading_bot.db"
    if not db_missing:
        write_feature_db(db_path, table=table, missing_column=missing_column)
    threshold_path = tmp_path / "thresholds" / "fixed_candidate_numeric_tercile_thresholds.json"
    if not threshold_missing:
        if invalid_threshold_text is not None:
            threshold_path.parent.mkdir(parents=True, exist_ok=True)
            threshold_path.write_text(invalid_threshold_text, encoding="utf-8")
        else:
            write_json(threshold_path, threshold_payload if threshold_payload is not None else threshold_json())
    return readiness.build_parser().parse_args(
        [
            "--run-id",
            "unit_paper_signal_logger_readiness",
            "--demo-strategy-spec-dir",
            str(spec_dir),
            "--demo-strategy-config",
            str(config_path),
            "--paper-runner-command-plan-dir",
            str(plan_dir),
            "--feature-source-db",
            str(db_path),
            "--feature-source-table",
            table,
            "--tercile-thresholds-json",
            str(threshold_path),
            "--state-json",
            str(tmp_path / "state" / "paper_signal_state.json"),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        readiness.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))

    assert outputs["readiness"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_valid_inputs_and_source_schema_produce_readiness_rows(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])

    assert any(row["readiness_area"] == "feature_source_db_gate" for row in rows)
    assert any(row["readiness_area"] == "required_columns_gate" for row in rows)
    assert any(row["readiness_area"] == "numeric_tercile_threshold_artifact_gate" for row in rows)


def test_price_features_table_is_allowlisted(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, table="price_features"))
    rows = read_csv(outputs["readiness"])
    table_gate = next(row for row in rows if row["readiness_area"] == "feature_source_table_gate")

    assert table_gate["readiness_status"] == "ready_for_paper_signal_logger_implementation"
    assert table_gate["evidence_label"] == "feature_source_table_allowlisted"


def test_market_features_table_is_allowlisted(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, table="market_features"))
    rows = read_csv(outputs["readiness"])
    table_gate = next(row for row in rows if row["readiness_area"] == "feature_source_table_gate")

    assert table_gate["readiness_status"] == "ready_for_paper_signal_logger_implementation"
    assert table_gate["evidence_label"] == "feature_source_table_allowlisted"


def test_ml_dataset_table_is_blocked_by_leakage_risk(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, table="ml_dataset"))
    rows = read_csv(outputs["readiness"])
    table_gate = next(row for row in rows if row["readiness_area"] == "feature_source_table_gate")

    assert table_gate["readiness_status"] == "blocked_by_leakage_risk"
    assert table_gate["evidence_label"] == "ml_dataset_blocked_for_signal_input"


def test_missing_db_creates_blocked_missing_required_artifact(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, db_missing=True))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    db_gate = next(row for row in rows if row["readiness_area"] == "feature_source_db_gate")

    assert db_gate["readiness_status"] == "blocked_missing_required_artifact"
    assert any(row["warning_code"] == "feature_source_db_missing" for row in warnings)


def test_missing_required_feature_column_blocks_readiness(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, missing_column="atr_20"))
    rows = read_csv(outputs["readiness"])
    columns = next(row for row in rows if row["readiness_area"] == "required_columns_gate")

    assert columns["readiness_status"] == "blocked_missing_required_column"
    assert "atr_20" in columns["observed_value"]


def test_missing_tercile_threshold_json_blocks_threshold_gate(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, threshold_missing=True))
    rows = read_csv(outputs["readiness"])
    threshold_gate = next(
        row for row in rows if row["readiness_area"] == "numeric_tercile_threshold_artifact_gate"
    )

    assert threshold_gate["readiness_status"] == "blocked_missing_threshold_artifact"
    assert threshold_gate["evidence_label"] == "numeric_tercile_threshold_artifact_missing"


def test_valid_threshold_json_is_accepted(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    threshold_schema = next(row for row in rows if row["readiness_area"] == "threshold_schema_gate")

    assert threshold_schema["readiness_status"] == "ready_for_paper_signal_logger_implementation"
    assert threshold_schema["evidence_label"] == "threshold_schema_valid"


def test_invalid_threshold_json_creates_blocked_unreadable_input(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, invalid_threshold_text="{not-json"))
    rows = read_csv(outputs["readiness"])
    threshold_gate = next(
        row for row in rows if row["readiness_area"] == "numeric_tercile_threshold_artifact_gate"
    )

    assert threshold_gate["readiness_status"] == "blocked_unreadable_input"


def test_missing_required_threshold_feature_creates_blocked_by_config(tmp_path: Path) -> None:
    payload = threshold_json()
    features = dict(payload["features"])  # type: ignore[index]
    features.pop("tick_volume_percentile_100")
    payload["features"] = features
    outputs = readiness.build_outputs(make_args(tmp_path, threshold_payload=payload))
    rows = read_csv(outputs["readiness"])
    threshold_schema = next(row for row in rows if row["readiness_area"] == "threshold_schema_gate")

    assert threshold_schema["readiness_status"] == "blocked_by_config"
    assert threshold_schema["evidence_label"] == "threshold_schema_missing_required_feature"


def test_numeric_spread_policy_is_ready_when_max_spread_points_is_numeric(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    spread = next(row for row in rows if row["readiness_area"] == "spread_policy_gate")

    assert spread["readiness_status"] == "ready_for_paper_signal_logger_implementation"
    assert spread["evidence_label"] == "numeric_spread_policy_configured"
    assert "max_spread_points=15.0" in spread["observed_value"]
    assert not any(row["warning_code"] == "spread_threshold_not_numeric_yet" for row in warnings)
    assert manifest["numeric_spread_policy_configured"] is True
    assert manifest["max_spread_points"] == 15.0
    assert manifest["spread_policy_status"] == "configured_numeric_threshold"


def test_spread_threshold_non_numeric_produces_ready_with_caveat(tmp_path: Path) -> None:
    non_numeric_config = demo_config(
        spread_and_session_controls={
            "spread_threshold_note": "Spread threshold is not numerically configured yet; abnormal or not configured spread blocks new paper/demo signals",
            "max_spread_points": "not_configured",
            "spread_policy_status": "not_configured",
            "spread_policy_action_when_exceeded": "skip_new_signal",
            "spread_policy_action_when_missing": "skip_new_signal",
            "session_filter_note": "hour_session=Off_hours only",
        }
    )
    outputs = readiness.build_outputs(make_args(tmp_path, config=non_numeric_config))
    rows = read_csv(outputs["readiness"])
    spread = next(row for row in rows if row["readiness_area"] == "spread_policy_gate")

    assert spread["readiness_status"] == "ready_with_caveat_for_paper_signal_logger_implementation"
    assert spread["evidence_label"] == "spread_threshold_not_numeric_yet"


def test_logging_and_kill_switch_contracts_are_checked(tmp_path: Path) -> None:
    bad_config = demo_config(
        logging={"logging_note": "missing", "required_fields": ["timestamp"]},
        kill_switch={"kill_switch_note": "missing", "conditions": ["required_data_missing"]},
    )
    outputs = readiness.build_outputs(make_args(tmp_path, config=bad_config))
    rows = read_csv(outputs["readiness"])
    logging = next(row for row in rows if row["readiness_area"] == "logging_contract_gate")
    kill = next(row for row in rows if row["readiness_area"] == "kill_switch_contract_gate")

    assert logging["readiness_status"] == "blocked_by_config"
    assert kill["readiness_status"] == "blocked_by_config"


def test_config_still_blocks_unsafe_paper_boundary_flags(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, config=demo_config(paper_only=False)))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    boundary = next(row for row in rows if row["readiness_area"] == "paper_boundary_gate")

    assert boundary["readiness_status"] == "blocked_by_config"
    assert any(row["warning_code"] == "paper_boundary_not_confirmed" for row in warnings)


def test_config_still_blocks_external_connection_or_order_flags(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(
        make_args(tmp_path, config=demo_config(broker_connection_allowed=True, order_execution_allowed=True))
    )
    rows = read_csv(outputs["readiness"])
    boundary = next(row for row in rows if row["readiness_area"] == "paper_boundary_gate")

    assert boundary["readiness_status"] == "blocked_by_config"


def test_state_json_path_is_planned_but_not_created(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    state_path = Path(args.state_json)
    outputs = readiness.build_outputs(args)
    rows = read_csv(outputs["readiness"])
    state = next(row for row in rows if row["readiness_area"] == "state_file_plan_gate")

    assert state["evidence_label"] == "state_json_planned_not_created"
    assert not state_path.exists()


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["readiness"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["readiness_row_count"] == len(rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["ready_for_paper_signal_logger_implementation_count"] == sum(
        row["readiness_status"] == "ready_for_paper_signal_logger_implementation" for row in rows
    )
    assert manifest["ready_with_caveat_for_paper_signal_logger_implementation_count"] == sum(
        row["readiness_status"] == "ready_with_caveat_for_paper_signal_logger_implementation"
        for row in rows
    )
    assert manifest["feature_source_db_exists"] is True
    assert manifest["feature_source_table_exists"] is True
    assert manifest["feature_source_table_allowlisted"] is True
    assert manifest["required_columns_available"] is True
    assert manifest["tercile_thresholds_json_exists"] is True
    assert manifest["tercile_thresholds_json_valid"] is True
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_paper_runner_executed"] is True
    assert manifest["no_db_mutation_performed"] is True
    assert manifest["no_data_generation_performed"] is True


def test_report_includes_no_db_mutation_and_no_execution_caveats(tmp_path: Path) -> None:
    outputs = readiness.build_outputs(make_args(tmp_path, threshold_missing=True))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Readiness-only artifact" in report
    assert "No database mutation was performed." in report
    assert "No data generation was performed." in report
    assert "No order execution was performed." in report
    assert "No trading decision was made." in report
    assert "fixed_candidate_numeric_tercile_thresholds.json" in report


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    readiness.build_outputs(make_args(tmp_path))
