from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_strategy_spec as spec


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


def write_artifact(
    directory: Path,
    *,
    artifact_spec: spec.ArtifactSpec,
    rows: list[dict[str, object]],
    manifest: dict[str, object] | None = None,
    report_text: str = "# Fixture report\n",
) -> None:
    fieldnames = sorted({key for row in rows for key in row}) or ["status"]
    write_csv(directory / artifact_spec.csv_name, fieldnames, rows)
    write_csv(directory / artifact_spec.warnings_name, ["warning_code", "blocking_warning"], [])
    base_manifest = {
        "run_id": "fixture",
        "warnings_count": 0,
        "blocking_warnings_count": 0,
    }
    if manifest:
        base_manifest.update(manifest)
    (directory / artifact_spec.manifest_name).write_text(json.dumps(base_manifest), encoding="utf-8")
    (directory / artifact_spec.report_name).write_text(report_text, encoding="utf-8")


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
            "exact_condition": spec.DEFAULT_EXACT_CONDITION,
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
            "conditions": ["required_data_missing", "existing_paper_demo_trade_open"],
        },
        "logging": {
            "logging_note": "Log timestamp, symbol, timeframe, feature values, regime value, spread, cost profile, signal state, entry/exit reason, R/net_R, bars held, errors, skipped reasons, daily paper PnL, weekly paper PnL, and kill-switch state",
            "required_fields": ["timestamp", "symbol", "timeframe", "spread", "daily_paper_pnl", "kill_switch_state"],
        },
        "paper_broker_mode": {
            "paper_broker_mode_note": "Paper logging now; demo broker preparation later",
        },
        "manual_review": {
            "manual_review_note": "This config is for paper/demo specification only and must be manually reviewed before any future paper runner command plan",
        },
    }
    config.update(overrides)
    return config


def write_demo_config(path: Path, config: dict[str, object] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config or demo_config(), indent=2), encoding="utf-8")
    return path


def write_all_artifacts(tmp_path: Path, *, omit: str | None = None, risk_framing: bool = True) -> dict[str, Path]:
    dirs = {
        "final_readiness": tmp_path / "final_readiness",
        "artifact_audit": tmp_path / "artifact_audit",
        "formal_packet": tmp_path / "formal_packet",
        "split_review": tmp_path / "split_review",
        "timeout_review": tmp_path / "timeout_review",
        "equity_review": tmp_path / "equity_review",
        "comparison": tmp_path / "comparison",
        "r_review": tmp_path / "r_review",
    }
    if omit != "final_readiness":
        write_artifact(
            dirs["final_readiness"],
            artifact_spec=spec.SPECS["final_readiness"],
            rows=[
                {
                    "readiness_area": "risk_filtered_framing_status",
                    "key_evidence_label": "risk_filtered_candidate_framing_preserved"
                    if risk_framing
                    else "manual_review_required",
                }
            ],
            manifest={
                "readiness_row_count": 13,
                "risk_filtered_framing_present": risk_framing,
                spec.DECISION_ABSENT_KEY: True,
                "blocked_missing_required_artifact_count": 0,
                "blocked_unreadable_input_count": 0,
            },
            report_text="# Final readiness\nrisk-filtered candidate\n" if risk_framing else "# Final readiness\n",
        )
    if omit != "artifact_audit":
        write_artifact(
            dirs["artifact_audit"],
            artifact_spec=spec.SPECS["artifact_audit"],
            rows=[
                {
                    "audit_area": "risk_filtered_framing_check",
                    "key_evidence_label": "risk_filtered_candidate_framing_preserved",
                }
            ],
            manifest={
                "audit_row_count": 13,
                "risk_filtered_framing_present": risk_framing,
                spec.DECISION_ABSENT_KEY: True,
                "blocked_missing_required_artifact_count": 0,
                "blocked_unreadable_input_count": 0,
            },
            report_text="# Artifact-aware audit\nrisk-filtered candidate\n" if risk_framing else "# Artifact-aware audit\n",
        )
    if omit != "formal_packet":
        write_artifact(
            dirs["formal_packet"],
            artifact_spec=spec.SPECS["formal_packet"],
            rows=[
                {
                    "audit_area": "risk_filtered_candidate_framing",
                    "key_evidence_label": "risk_filtered_candidate_framing_required",
                }
            ],
            manifest={
                "audit_packet_row_count": 13,
                "blocked_missing_required_artifact_count": 0,
                "blocked_unreadable_input_count": 0,
            },
            report_text="# Formal packet\nrisk-filtered candidate\n",
        )
    if omit != "split_review":
        write_artifact(
            dirs["split_review"],
            artifact_spec=spec.SPECS["split_review"],
            rows=[{"review_scope": "walk_forward_split_summary"}],
            manifest={
                "matched_split_count": 5,
                "exact_lower_drawdown_split_count": 5,
                "exact_mean_R_higher_split_count": 2,
                "exact_profit_factor_higher_split_count": 1,
            },
        )
    if omit != "timeout_review":
        write_artifact(
            dirs["timeout_review"],
            artifact_spec=spec.SPECS["timeout_review"],
            rows=[{"review_scope": "timeout_caveat", "timeout_rate_delta": "0.025"}],
            manifest={"review_row_count": 15},
        )
    if omit != "equity_review":
        write_artifact(
            dirs["equity_review"],
            artifact_spec=spec.SPECS["equity_review"],
            rows=[{"review_scope": "loss_cluster_review"}],
            manifest={"review_row_count": 8},
        )
    if omit != "comparison":
        write_artifact(
            dirs["comparison"],
            artifact_spec=spec.SPECS["comparison"],
            rows=[{"row_type": "exact_rule", "metric_namespace": "R_multiple"}],
            manifest={"comparison_row_count": 8, "metric_namespaces": ["R_multiple"]},
        )
    if omit != "r_review":
        write_artifact(
            dirs["r_review"],
            artifact_spec=spec.SPECS["r_review"],
            rows=[{"review_scope": "exact_vs_single_filter_a"}],
            manifest={"review_row_count": 10},
        )
    return dirs


def make_args(
    tmp_path: Path,
    *,
    omit: str | None = None,
    risk_framing: bool = True,
    missing_config: bool = False,
    config: dict[str, object] | None = None,
    extra_args: list[str] | None = None,
) -> object:
    dirs = write_all_artifacts(tmp_path, omit=omit, risk_framing=risk_framing)
    config_path = tmp_path / "paper_demo" / "demo_strategy_config.json"
    if not missing_config:
        write_demo_config(config_path, config)
    argv = [
        "--run-id",
        "unit_demo_strategy_spec",
        "--final-research-decision-readiness-dir",
        str(dirs["final_readiness"]),
        "--artifact-aware-candidate-audit-dir",
        str(dirs["artifact_audit"]),
        "--formal-candidate-audit-packet-dir",
        str(dirs["formal_packet"]),
        "--deeper-walkforward-split-review-dir",
        str(dirs["split_review"]),
        "--timeout-artifact-review-dir",
        str(dirs["timeout_review"]),
        "--equity-drawdown-sequence-review-dir",
        str(dirs["equity_review"]),
        "--comparison-table-dir",
        str(dirs["comparison"]),
        "--r-multiple-review-dir",
        str(dirs["r_review"]),
        "--demo-strategy-config",
        str(config_path),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    if extra_args:
        argv.extend(extra_args)
    return spec.build_parser().parse_args(
        argv
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        spec.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))

    assert outputs["spec"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_default_demo_strategy_config_path_is_accepted() -> None:
    args = spec.build_parser().parse_args([])

    assert args.demo_strategy_config == spec.DEFAULT_DEMO_STRATEGY_CONFIG


def test_valid_config_is_loaded(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["demo_strategy_config_loaded"] is True
    assert manifest["demo_strategy_config_valid"] is True
    assert manifest["config_role"] == "paper_demo_strategy_config"
    assert manifest["candidate_id"] == "gbpusd_short_h10_1_5_off_hours"


def test_required_artifacts_are_read_from_fixture_dirs(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["spec"])
    identity = next(row for row in rows if row["spec_section"] == "strategy_identity")
    context = next(row for row in rows if row["spec_section"] == "research_decision_context")

    assert identity["source_dir"].endswith("final_readiness")
    assert context["source_artifact"].endswith(spec.SPECS["final_readiness"].csv_name)


def test_missing_required_artifact_creates_blocked_missing_required_artifact(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path, omit="final_readiness"))
    rows = read_csv(outputs["spec"])
    warnings = read_csv(outputs["warnings"])

    blocked = [row for row in rows if row["boundary_status"] == "blocked_missing_required_artifact"]
    assert blocked
    assert any(row["warning_code"] == "final_readiness_missing" for row in warnings)
    assert any(row["blocking_warning"] == "true" for row in warnings)


def test_risk_filtered_framing_is_preserved(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path, risk_framing=True))
    rows = read_csv(outputs["spec"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    framing = next(row for row in rows if row["spec_section"] == "candidate_framing")

    assert framing["evidence_label"] == "risk_filtered_candidate"
    assert framing["spec_value"] == "risk_filtered_candidate"
    assert manifest["risk_filtered_framing_present"] is True


def test_final_decision_absence_is_verified(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest[spec.DECISION_ABSENT_KEY] is True


def test_entry_rule_contains_exact_condition_and_regime(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["spec"])
    entry = next(row for row in rows if row["spec_section"] == "entry_rule")

    assert "Off_hours" in entry["spec_value"]
    assert spec.DEFAULT_EXACT_CONDITION in entry["spec_value"]
    assert "Short GBPUSD M15" in entry["spec_value"]


def test_tp_sl_horizon_and_same_bar_policy_are_written(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["spec"])
    tp_sl = next(row for row in rows if row["spec_section"] == "tp_sl_rule")
    timeout = next(row for row in rows if row["spec_section"] == "horizon_timeout_behavior")
    same_bar = next(row for row in rows if row["spec_section"] == "same_bar_policy")

    assert "tp_atr=1.5" in tp_sl["spec_value"]
    assert "sl_atr=1.0" in tp_sl["spec_value"]
    assert "horizon=10" in timeout["spec_value"]
    assert "preferred_1_5atr_1atr_hit_first" in timeout["spec_value"]
    assert same_bar["spec_value"] == "stop_first"


def test_config_values_populate_strategy_sections(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["spec"])
    risk = next(row for row in rows if row["spec_section"] == "demo_risk_controls")
    max_open = next(row for row in rows if row["spec_section"] == "max_open_positions")
    max_daily = next(row for row in rows if row["spec_section"] == "max_daily_trades")
    spread = next(row for row in rows if row["spec_section"] == "spread_threshold")
    spread_rows = [row for row in rows if row["spec_section"] == "spread_threshold"]
    paper_mode = next(row for row in rows if row["spec_section"] == "paper_broker_mode")
    kill_switch = next(row for row in rows if row["spec_section"] == "kill_switch_conditions")
    logging = next(row for row in rows if row["spec_section"] == "logging_requirements")

    assert "1% demo equity" in risk["spec_value"]
    assert "Maximum 1 open" in max_open["spec_value"]
    assert "No fixed max daily trade count" in max_daily["spec_value"]
    assert "max_spread_points" in spread["spec_value"]
    assert any(row["spec_key"] == "spread_unit" and row["spec_value"] == "broker_points" for row in spread_rows)
    assert any(row["spec_key"] == "max_spread_points" and row["spec_value"] == "15.0" for row in spread_rows)
    assert any(row["spec_key"] == "spread_policy_matches_canonical" and row["spec_value"] == "true" for row in spread_rows)
    assert any(
        row["spec_key"] == "spread_policy_status"
        and row["spec_value"] == "configured_numeric_threshold"
        for row in spread_rows
    )
    assert "Paper logging now" in paper_mode["spec_value"]
    assert "required_data_missing" in kill_switch["caveat"]
    assert "daily_paper_pnl" in logging["spec_value"]
    assert all(
        row["boundary_status"] != "requires_manual_configuration"
        for row in [risk, max_open, max_daily, spread, paper_mode, kill_switch, logging]
    )


def test_cli_values_override_config_values(tmp_path: Path) -> None:
    outputs = spec.build_outputs(
        make_args(
            tmp_path,
            extra_args=[
                "--symbol",
                "EURUSD",
                "--demo-risk-per-trade-note",
                "custom paper risk note",
            ],
        )
    )
    rows = read_csv(outputs["spec"])
    identity = next(row for row in rows if row["spec_section"] == "symbol_timeframe")
    risk = next(row for row in rows if row["spec_section"] == "demo_risk_controls")

    assert "symbol=EURUSD" in identity["spec_value"]
    assert risk["spec_value"] == "custom paper risk note"


def test_missing_config_falls_back_safely_and_warns(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path, missing_config=True))
    warnings = read_csv(outputs["warnings"])
    rows = read_csv(outputs["spec"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    risk = next(row for row in rows if row["spec_section"] == "demo_risk_controls")

    assert manifest["demo_strategy_config_loaded"] is False
    assert manifest["demo_strategy_config_valid"] is False
    assert risk["boundary_status"] == "requires_manual_configuration"
    assert any(row["warning_code"] == "demo_strategy_config_missing" for row in warnings)


def test_valid_config_produces_no_manual_configuration_warnings(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    warning_codes = {row["warning_code"] for row in warnings}
    assert manifest["requires_manual_configuration_count"] == 0
    assert "demo_risk_per_trade_note_manual_configuration_required" not in warning_codes
    assert "demo_kill_switch_note_manual_configuration_required" not in warning_codes


def test_report_includes_paper_demo_only_and_no_execution_caveats(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "Paper/demo-only specification" in report
    assert "No order execution was performed." in report
    assert "No final trading decision was made." in report
    assert "No real-money sizing was chosen." in report
    assert "config_path:" in report
    assert "spread_unit: `broker_points`" in report
    assert "max_spread_points: `15.0`" in report
    assert "spread_policy_matches_canonical: `true`" in report
    assert "spread_policy_status: `configured_numeric_threshold`" in report
    assert "if spread exceeds threshold: `skip_new_signal`" in report
    assert "if spread is missing/unreadable: `skip_new_signal`" in report
    assert "Manual demo risk configuration is required" not in report


def test_csv_preserves_source_paths(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["spec"])
    baseline = next(row for row in rows if row["spec_section"] == "baseline_reference")

    assert baseline["source_dir"].endswith("r_review")
    assert baseline["source_artifact"].endswith(spec.SPECS["r_review"].csv_name)


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = spec.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["spec"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["spec_row_count"] == len(rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["requires_manual_configuration_count"] == sum(
        row["boundary_status"] == "requires_manual_configuration" for row in rows
    )
    assert manifest["requires_manual_configuration_count"] == 0
    assert manifest["demo_strategy_config_loaded"] is True
    assert manifest["demo_strategy_config_valid"] is True
    assert manifest["config_role"] == "paper_demo_strategy_config"
    assert manifest["candidate_id"] == "gbpusd_short_h10_1_5_off_hours"
    assert manifest["spread_unit"] == "broker_points"
    assert manifest["max_spread_points"] == 15.0
    assert manifest["spread_policy_matches_canonical"] is True
    assert manifest["spread_policy_status"] == "configured_numeric_threshold"
    assert manifest["numeric_spread_policy_configured"] is True
    assert manifest["paper_only_specification"] is True
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_broker_connection_performed"] is True
    assert manifest["no_order_execution_performed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_walk_forward_validation_executed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_no_child_or_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command execution is not allowed")

    monkeypatch.setattr("subprocess.run", fail_run, raising=False)

    spec.build_outputs(make_args(tmp_path))
