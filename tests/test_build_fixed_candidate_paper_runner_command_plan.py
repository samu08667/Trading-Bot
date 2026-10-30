from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_paper_runner_command_plan as plan


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
            "spread_threshold_note": "Spread threshold is not numerically configured yet; abnormal or not configured spread blocks new paper/demo signals",
            "session_filter_note": "hour_session=Off_hours only",
        },
        "kill_switch": {
            "kill_switch_note": "Disable new paper/demo signals if required data is missing",
            "conditions": [
                "required_data_missing",
                "required_features_missing",
                "spread_abnormal_or_not_configured",
            ],
        },
        "logging": {
            "logging_note": "Log timestamp, symbol, timeframe, feature values, regime value, spread, cost profile, signal state, entry/exit reason, R/net_R, bars held, errors, skipped reasons, daily paper PnL, weekly paper PnL, and kill-switch state",
            "required_fields": list(plan.REQUIRED_LOGGING_FIELDS),
        },
        "paper_broker_mode": {
            "paper_broker_mode_note": "Paper logging now; demo broker preparation later",
        },
    }
    config.update(overrides)
    return config


def write_config(path: Path, config: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def write_demo_spec_dir(path: Path, *, warnings_count: int = 0, blocking_count: int = 0) -> None:
    write_csv(
        path / plan.SPEC_CSV,
        ["spec_section", "spec_key", "spec_value"],
        [{"spec_section": "paper_execution_boundary", "spec_key": "boundary", "spec_value": "paper_demo"}],
    )
    (path / plan.SPEC_MANIFEST).write_text(
        json.dumps(
            {
                "run_id": "fixture_demo_spec",
                "spec_row_count": 26,
                "demo_strategy_config_loaded": True,
                "demo_strategy_config_valid": True,
                "paper_only_specification": True,
                "no_broker_connection_performed": True,
                "no_order_execution_performed": True,
                "no_trading_decision_performed": True,
                "warnings_count": warnings_count,
                "blocking_warnings_count": blocking_count,
            }
        ),
        encoding="utf-8",
    )
    (path / plan.SPEC_REPORT).write_text("# Demo spec\npaper/demo-only\n", encoding="utf-8")
    write_csv(
        path / plan.SPEC_WARNINGS,
        ["warning_code", "blocking_warning"],
        [{"warning_code": "blocked", "blocking_warning": "true"}] if blocking_count else [],
    )


def write_script(path: Path, flags: tuple[str, ...]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(flags), encoding="utf-8")
    return path


def make_args(
    tmp_path: Path,
    *,
    config: dict[str, object] | None = None,
    script_exists: bool = False,
    script_compatible: bool = True,
    spec_blocked: bool = False,
) -> object:
    spec_dir = tmp_path / "demo_spec"
    write_demo_spec_dir(spec_dir, blocking_count=1 if spec_blocked else 0)
    config_path = write_config(tmp_path / "config" / "demo_strategy_config.json", config or demo_config())
    script_path = tmp_path / "scripts" / "run_fixed_candidate_paper_signal_logger.py"
    if script_exists:
        flags = plan.PAPER_RUNNER_REQUIRED_FLAGS if script_compatible else ("--run-id", "--output-dir")
        write_script(script_path, flags)
    return plan.build_parser().parse_args(
        [
            "--run-id",
            "unit_paper_runner_command_plan",
            "--demo-strategy-spec-dir",
            str(spec_dir),
            "--demo-strategy-config",
            str(config_path),
            "--final-research-decision-readiness-dir",
            str(tmp_path / "final_readiness"),
            "--artifact-aware-candidate-audit-dir",
            str(tmp_path / "artifact_audit"),
            "--paper-runner-script",
            str(script_path),
            "--python-executable",
            "python",
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
    outputs = plan.build_outputs(make_args(tmp_path))

    assert outputs["command_plan"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_valid_demo_strategy_spec_and_config_produce_clean_gate_rows(tmp_path: Path) -> None:
    outputs = plan.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["command_plan"])
    spec_gate = next(row for row in rows if row["plan_step"] == "demo_strategy_spec_gate_check")
    config_gate = next(row for row in rows if row["plan_step"] == "canonical_config_gate_check")

    assert spec_gate["command_status"] == "no_command_needed"
    assert config_gate["command_status"] == "no_command_needed"
    assert config_gate["boundary_status"] == "paper_only_boundary_confirmed"


def test_config_paper_only_false_blocks_command_plan(tmp_path: Path) -> None:
    outputs = plan.build_outputs(make_args(tmp_path, config=demo_config(paper_only=False)))
    rows = read_csv(outputs["command_plan"])
    warnings = read_csv(outputs["warnings"])

    assert any(row["command_status"] == "blocked_by_config" for row in rows)
    assert any(row["warning_code"] == "paper_only_boundary_not_confirmed" for row in warnings)


def test_config_broker_connection_allowed_true_blocks_command_plan(tmp_path: Path) -> None:
    outputs = plan.build_outputs(make_args(tmp_path, config=demo_config(broker_connection_allowed=True)))
    rows = read_csv(outputs["command_plan"])
    warnings = read_csv(outputs["warnings"])

    assert any(row["command_status"] == "blocked_by_config" for row in rows)
    assert any(row["warning_code"] == "no_broker_no_order_boundary_failed" for row in warnings)


def test_config_order_execution_allowed_true_blocks_command_plan(tmp_path: Path) -> None:
    outputs = plan.build_outputs(make_args(tmp_path, config=demo_config(order_execution_allowed=True)))
    rows = read_csv(outputs["command_plan"])
    warnings = read_csv(outputs["warnings"])

    assert any(row["command_status"] == "blocked_by_config" for row in rows)
    assert any(row["warning_code"] == "no_broker_no_order_boundary_failed" for row in warnings)


def test_missing_paper_runner_script_creates_implementation_required_row(tmp_path: Path) -> None:
    outputs = plan.build_outputs(make_args(tmp_path, script_exists=False))
    rows = read_csv(outputs["command_plan"])
    script = next(row for row in rows if row["plan_step"] == "paper_runner_script_status")

    assert script["artifact_status"] == "missing"
    assert script["command_status"] == "implementation_required"
    assert script["required_next_artifact"] == "implement_run_fixed_candidate_paper_signal_logger"


def test_existing_compatible_paper_runner_script_creates_planned_manual_command(tmp_path: Path) -> None:
    outputs = plan.build_outputs(make_args(tmp_path, script_exists=True, script_compatible=True))
    rows = read_csv(outputs["command_plan"])
    command = next(row for row in rows if row["plan_step"] == "paper_runner_command")

    assert command["command_status"] == "planned_manual_command"
    assert command["compatibility_status"] == "compatible_with_paper_demo_spec"
    assert "--demo-strategy-spec-dir" in command["manual_command"]
    assert "--demo-strategy-config" in command["manual_command"]
    assert "--output-dir" in command["manual_command"]
    assert "--run-id" in command["manual_command"]


def test_missing_required_logging_fields_blocks_by_config(tmp_path: Path) -> None:
    bad = demo_config(logging={"logging_note": "too little", "required_fields": ["timestamp"]})
    outputs = plan.build_outputs(make_args(tmp_path, config=bad))
    rows = read_csv(outputs["command_plan"])
    logging = next(row for row in rows if row["plan_step"] == "logging_contract_check")

    assert logging["command_status"] == "blocked_by_config"
    assert logging["warning_code"] == "logging_contract_missing"


def test_missing_kill_switch_conditions_blocks_by_config(tmp_path: Path) -> None:
    bad = demo_config(kill_switch={"kill_switch_note": "missing conditions", "conditions": []})
    outputs = plan.build_outputs(make_args(tmp_path, config=bad))
    rows = read_csv(outputs["command_plan"])
    kill = next(row for row in rows if row["plan_step"] == "kill_switch_contract_check")

    assert kill["command_status"] == "blocked_by_config"
    assert kill["warning_code"] == "kill_switch_contract_missing"


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = plan.build_outputs(make_args(tmp_path, script_exists=True, script_compatible=True))
    rows = read_csv(outputs["command_plan"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["plan_row_count"] == len(rows)
    assert manifest["planned_manual_command_count"] == sum(
        row["command_status"] == "planned_manual_command" for row in rows
    )
    assert manifest["implementation_required_count"] == sum(
        row["command_status"] == "implementation_required" for row in rows
    )
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["demo_strategy_config_loaded"] is True
    assert manifest["demo_strategy_config_valid"] is True
    assert manifest["paper_only_boundary_confirmed"] is True
    assert manifest["no_broker_connection_allowed"] is True
    assert manifest["no_order_execution_allowed"] is True
    assert manifest["real_money_not_allowed"] is True
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_paper_runner_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_walk_forward_validation_executed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_includes_command_plan_only_and_no_execution_caveats(tmp_path: Path) -> None:
    outputs = plan.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Command-plan-only artifact" in report
    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No order execution was performed." in report
    assert "No trading decision was made." in report


def test_csv_preserves_config_and_spec_paths(tmp_path: Path) -> None:
    outputs = plan.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["command_plan"])
    spec_gate = next(row for row in rows if row["plan_step"] == "demo_strategy_spec_gate_check")
    config_gate = next(row for row in rows if row["plan_step"] == "canonical_config_gate_check")

    assert spec_gate["source_dir"].endswith("demo_spec")
    assert config_gate["source_config"].endswith("demo_strategy_config.json")


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    plan.build_outputs(make_args(tmp_path, script_exists=True))
