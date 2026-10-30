from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_fixed_candidate_demo_no_order_dry_run as run


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


def recent_time_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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


def thresholds_json() -> dict[str, object]:
    return {
        "schema_version": 1,
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "threshold_lineage": "train_only",
        "calibration_scope": "train_window_only",
        "full_sample_thresholds_used": False,
        "oos_rows_used_for_thresholds": False,
        "features": {
            "close_to_ma_fast_atr_20": {
                "low_mid_cutoff": -0.45968425469893365,
                "mid_high_cutoff": 0.5951568132962021,
            },
            "tick_volume_percentile_100": {
                "low_mid_cutoff": 0.15,
                "mid_high_cutoff": 0.37,
            },
        },
    }


def legacy_thresholds_json() -> dict[str, object]:
    return {
        "schema_version": 1,
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "features": {
            "close_to_ma_fast_atr_20": {
                "lower_tercile_boundary": -0.45968425469893365,
                "upper_tercile_boundary": 0.5951568132962021,
            },
            "tick_volume_percentile_100": {
                "lower_tercile_boundary": 0.15,
                "upper_tercile_boundary": 0.37,
            },
        },
    }


def demo_execution_policy() -> dict[str, object]:
    return {
        "policy_id": "fixed_candidate_demo_execution_policy",
        "risk_percent_max": 0.5,
        "risk_amount_max": 5.0,
        "max_open_positions": 1,
    }


def plan_manifest(status: str = "demo_no_order_dry_run_plan_available_with_caveats") -> dict[str, object]:
    return {
        "run_id": "fixture_no_order_plan",
        "plan_status": status,
        "recommended_next_step": "implement_run_fixed_candidate_demo_no_order_dry_run",
        "environment_check_status": "environment_check_available_with_caveats",
        "account_mode_label": "demo",
        "is_demo_account": True,
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "spread_current_points": 6.0,
        "spread_within_config_gate": True,
        "spread_policy_matches_canonical": True,
        "blocking_warnings_count": 0,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_db_mutation_performed": True,
        "no_demo_broker_approval_performed": True,
    }


def env_manifest(
    *,
    status: str = "environment_check_available_with_caveats",
    spread_unit: str = "broker_points",
    max_spread_points: float = 15.0,
    spread_current_points: float = 6.0,
    spread_within_gate: bool = True,
) -> dict[str, object]:
    return {
        "run_id": "fixture_environment_check",
        "environment_check_status": status,
        "account_mode_label": "demo",
        "is_demo_account": True,
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "spread_unit": spread_unit,
        "max_spread_points": max_spread_points,
        "spread_current_points": spread_current_points,
        "spread_within_config_gate": spread_within_gate,
        "spread_policy_matches_canonical": spread_unit == "broker_points" and max_spread_points == 15.0,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_db_mutation_performed": True,
        "no_demo_broker_approval_performed": True,
    }


def account_snapshot(*, demo: bool = True) -> dict[str, object]:
    return {
        "account_trade_mode_raw": 0 if demo else 2,
        "account_trade_mode_label": "demo" if demo else "real",
        "is_demo_account": demo,
        "redaction_applied": True,
        "balance_present": True,
        "equity_present": True,
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
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "point": 0.00001,
        "digits": 5,
        "trade_tick_size": 0.00001,
        "trade_tick_value": 1.0,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
        "spread": spread_current_points,
        "spread_unit": spread_unit,
        "max_spread_points": max_spread_points,
        "spread_current_points": spread_current_points,
        "spread_within_config_gate": spread_within_gate,
    }


def spec_manifest() -> dict[str, object]:
    return {
        "run_id": "fixture_spec",
        "paper_only_specification": True,
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_trading_decision_performed": True,
    }


def create_feature_db(tmp_path: Path, *, table: str = "price_features", row: dict[str, object] | None = None) -> Path:
    db_path = tmp_path / "features.db"
    payload = {
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "time_server": recent_time_text(),
        "open": 1.2499,
        "high": 1.2502,
        "low": 1.2497,
        "close": 1.25,
        "atr_20": 0.0006,
        "spread": 6.0,
        "hour_session": "Off_hours",
        "close_to_ma_fast_atr_20": 0.7,
        "tick_volume_percentile_100": 0.2,
        "tick_volume": 123,
        "volume": 123,
    }
    if row:
        payload.update(row)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f"""
            CREATE TABLE {table} (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                atr_20 REAL,
                spread REAL,
                hour_session TEXT,
                close_to_ma_fast_atr_20 REAL,
                tick_volume_percentile_100 REAL,
                tick_volume REAL,
                volume REAL
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO {table} (
                symbol, timeframe, time_server, open, high, low, close, atr_20,
                spread, hour_session, close_to_ma_fast_atr_20,
                tick_volume_percentile_100, tick_volume, volume
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["symbol"],
                payload["timeframe"],
                payload["time_server"],
                payload["open"],
                payload["high"],
                payload["low"],
                payload["close"],
                payload["atr_20"],
                payload["spread"],
                payload["hour_session"],
                payload["close_to_ma_fast_atr_20"],
                payload["tick_volume_percentile_100"],
                payload["tick_volume"],
                payload["volume"],
            ),
        )
        connection.execute(
            """
            CREATE TABLE price_bars (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                spread REAL
            )
            """
        )
        connection.execute(
            "INSERT INTO price_bars (symbol, timeframe, time_server, spread) VALUES (?, ?, ?, ?)",
            (payload["symbol"], payload["timeframe"], payload["time_server"], payload["spread"]),
        )
    return db_path


def write_fixture_sources(
    tmp_path: Path,
    *,
    config_payload: dict[str, object] | None = None,
    plan_status: str = "demo_no_order_dry_run_plan_available_with_caveats",
    env_status: str = "environment_check_available_with_caveats",
    missing_plan_manifest: bool = False,
    missing_thresholds: bool = False,
    threshold_payload: dict[str, object] | None = None,
    account_demo: bool = True,
    spread_unit: str = "broker_points",
    max_spread_points: float = 15.0,
    spread_current_points: float = 6.0,
    spread_within_gate: bool = True,
    row: dict[str, object] | None = None,
    state_payload: dict[str, object] | None = None,
) -> dict[str, Path]:
    plan_dir = tmp_path / "no_order_plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    if not missing_plan_manifest:
        write_json(plan_dir / run.PLAN_MANIFEST, plan_manifest(plan_status))
    (plan_dir / run.PLAN_REPORT).write_text("# Plan\n", encoding="utf-8")
    write_csv(plan_dir / run.PLAN_REQUIREMENTS, ["run_id", "requirement_area"], [{"run_id": "fixture", "requirement_area": "ok"}])
    write_csv(plan_dir / run.PLAN_FUTURE_ARTIFACTS, ["run_id", "future_artifact_name"], [{"run_id": "fixture", "future_artifact_name": "ok"}])
    write_csv(plan_dir / run.PLAN_WARNINGS, run.WARNING_FIELDNAMES, [])

    env_dir = tmp_path / "environment_check"
    env_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        env_dir / run.ENV_MANIFEST,
        env_manifest(
            status=env_status,
            spread_unit=spread_unit,
            max_spread_points=max_spread_points,
            spread_current_points=spread_current_points,
            spread_within_gate=spread_within_gate,
        ),
    )
    (env_dir / run.ENV_REPORT).write_text("# Environment\n", encoding="utf-8")
    write_json(env_dir / run.ENV_ACCOUNT_SNAPSHOT, account_snapshot(demo=account_demo))
    write_json(
        env_dir / run.ENV_SYMBOL_SNAPSHOT,
        symbol_snapshot(
            spread_unit=spread_unit,
            max_spread_points=max_spread_points,
            spread_current_points=spread_current_points,
            spread_within_gate=spread_within_gate,
        ),
    )
    write_csv(
        env_dir / run.ENV_NO_ORDER,
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

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    write_json(spec_dir / run.SPEC_MANIFEST, spec_manifest())
    write_csv(spec_dir / run.SPEC_CSV, ["run_id", "row"], [{"run_id": "fixture", "row": "ok"}])
    write_csv(spec_dir / run.SPEC_WARNINGS, run.WARNING_FIELDNAMES, [])

    config_path = tmp_path / "config" / "demo_config.json"
    write_json(config_path, config_payload if config_payload is not None else demo_config())

    thresholds_path = tmp_path / "thresholds" / "fixed_candidate_numeric_tercile_thresholds.json"
    if not missing_thresholds:
        write_json(thresholds_path, threshold_payload if threshold_payload is not None else thresholds_json())
    policy_path = tmp_path / "config" / "demo_execution_policy.json"
    write_json(policy_path, demo_execution_policy())
    canonical_path = tmp_path / "config" / "fixed_candidate_current_canonical.json"
    write_json(
        canonical_path,
        {
            "candidate_id": "gbpusd_short_h10_1_5_off_hours",
            "numeric_tercile_thresholds_json": str(thresholds_path),
        },
    )

    db_path = create_feature_db(tmp_path, row=row)

    state_path = tmp_path / "state" / "state.json"
    if state_payload is not None:
        write_json(state_path, state_payload)

    return {
        "plan": plan_dir,
        "env": env_dir,
        "spec": spec_dir,
        "config": config_path,
        "policy": policy_path,
        "canonical": canonical_path,
        "thresholds": thresholds_path,
        "db": db_path,
        "state": state_path,
    }


def make_args(
    tmp_path: Path,
    paths: dict[str, Path],
    *,
    table: str = "price_features",
    explicit_threshold: bool = True,
    allow_legacy: bool = False,
    extra_args: list[str] | None = None,
) -> object:
    argv = [
            "--run-id",
            "unit_demo_no_order_dry_run",
            "--demo-no-order-dry-run-plan-dir",
            str(paths["plan"]),
            "--demo-environment-check-dir",
            str(paths["env"]),
            "--demo-strategy-config",
            str(paths["config"]),
            "--canonical-registry",
            str(paths["canonical"]),
            "--demo-execution-policy-json",
            str(paths["policy"]),
            "--demo-strategy-spec-dir",
            str(paths["spec"]),
            "--feature-source-db",
            str(paths["db"]),
            "--feature-source-table",
            table,
            "--state-json",
            str(paths["state"]),
            "--symbol",
            "GBPUSD",
            "--timeframe",
            "M15",
            "--max-staleness-hours",
            "24",
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    if explicit_threshold:
        argv.extend(["--tercile-thresholds-json", str(paths["thresholds"])])
    if allow_legacy:
        argv.append("--allow-legacy-full-sample-thresholds")
    if extra_args:
        argv.extend(extra_args)
    return run.build_parser().parse_args(argv)


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        run.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = run.build_outputs(make_args(tmp_path, paths))

    for key in ["manifest", "report", "decision", "checklist", "warnings", "no_order", "state_preview", "input_row_snapshot"]:
        assert outputs[key].exists()


def test_valid_matching_row_produces_would_signal_and_preview_without_order_request(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = run.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    decision = read_csv(outputs["decision"])[0]

    assert manifest["dry_run_status"] == "demo_no_order_dry_run_would_signal"
    assert decision["decision_label"] == "would_signal"
    assert float(decision["entry_reference_price"]) == pytest.approx(1.25)
    assert float(decision["tp_price_preview"]) == pytest.approx(1.2491)
    assert float(decision["sl_price_preview"]) == pytest.approx(1.2506)
    assert decision["volume_preview_status"] == "not_computed_no_order_calc_forbidden"
    assert decision["no_order_request_constructed"] == "true"
    assert manifest["spread_unit"] == "broker_points"
    assert manifest["max_spread_points"] == 15.0
    assert manifest["spread_policy_matches_canonical"] is True
    assert manifest["threshold_lineage"] == "train_only"
    assert manifest["calibration_scope"] == "train_window_only"
    assert manifest["full_sample_thresholds_used"] is False
    assert manifest["oos_rows_used_for_thresholds"] is False
    assert manifest["threshold_schema_label"] == "train_only_low_mid_mid_high"
    assert manifest["risk_percent_configured"] == 0.5
    assert manifest["risk_amount_configured"] == 5.0
    assert manifest["current_broker_spread_points"] == ""
    assert manifest["current_broker_spread_source"] == "not_checked_no_broker_context"
    assert manifest["current_broker_spread_within_policy"] is None
    assert manifest["live_spread_gate_status"] == "live_spread_not_checked_no_broker_context"


def test_default_threshold_path_resolves_from_canonical_registry(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = run.build_outputs(make_args(tmp_path, paths, explicit_threshold=False))
    manifest = read_json(outputs["manifest"])

    assert manifest["numeric_tercile_thresholds_json"] == str(paths["thresholds"])
    assert manifest["threshold_lineage"] == "train_only"


def test_legacy_full_sample_thresholds_rejected_by_default(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, threshold_payload=legacy_thresholds_json())
    outputs = run.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["dry_run_status"] == "blocked_by_threshold_artifact"
    assert manifest["threshold_schema_label"] == "legacy_full_sample_lower_upper"
    assert manifest["legacy_full_sample_thresholds_allowed"] is False
    assert any(row["warning_code"] == "threshold_artifact_invalid" for row in warnings)


def test_legacy_full_sample_thresholds_allowed_only_with_explicit_flag(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, threshold_payload=legacy_thresholds_json())
    outputs = run.build_outputs(make_args(tmp_path, paths, allow_legacy=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["dry_run_status"] == "demo_no_order_dry_run_would_signal"
    assert manifest["threshold_schema_label"] == "legacy_full_sample_lower_upper"
    assert manifest["legacy_full_sample_thresholds_allowed"] is True


def test_session_mismatch_produces_would_skip(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, row={"hour_session": "London"})
    outputs = run.build_outputs(make_args(tmp_path, paths))
    decision = read_csv(outputs["decision"])[0]

    assert decision["decision_label"] == "would_skip"
    assert "session_mismatch" in decision["skip_reasons"]


def test_spread_above_15_produces_would_skip(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, row={"spread": 20.0})
    outputs = run.build_outputs(make_args(tmp_path, paths))
    decision = read_csv(outputs["decision"])[0]

    assert decision["decision_label"] == "would_skip"
    assert "spread_above_threshold" in decision["skip_reasons"]


def test_feature_bucket_mismatch_produces_would_skip(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, row={"close_to_ma_fast_atr_20": 0.1})
    outputs = run.build_outputs(make_args(tmp_path, paths))
    decision = read_csv(outputs["decision"])[0]

    assert decision["decision_label"] == "would_skip"
    assert "close_to_ma_fast_atr_20_bucket_mismatch" in decision["skip_reasons"]


def test_missing_required_row_value_produces_would_block(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, row={"close": None})
    outputs = run.build_outputs(make_args(tmp_path, paths))
    decision = read_csv(outputs["decision"])[0]

    assert decision["decision_label"] == "would_block"
    assert "required_row_value_missing" in decision["block_reasons"]


def test_stale_feature_row_produces_would_block(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, row={"time_server": "2000-01-01 00:00:00"})
    outputs = run.build_outputs(make_args(tmp_path, paths))
    decision = read_csv(outputs["decision"])[0]

    assert decision["decision_label"] == "would_block"
    assert "stale_feature_row" in decision["block_reasons"]


def alignment_args(
    latest_mt5: str = "2026-06-11 01:15:00",
    *,
    required: bool = True,
    current_spread: str | None = "3",
    current_spread_source: str = "symbol_info.spread",
) -> list[str]:
    args = [
        "--max-staleness-hours",
        "999999",
        "--timeframe-minutes",
        "15",
        "--db-lag-tolerance-bars",
        "1",
        "--mt5-time-basis-status",
        "mt5_alignment_checked" if latest_mt5 else "live_data_mt5_time_basis_unavailable",
        "--pc-utc-now",
        "2026-06-10T22:28:49+00:00",
        "--mt5-tick-time-server",
        "2026-06-11 01:28:48",
        "--latest-mt5-closed-bar-time-server",
        latest_mt5,
        "--mt5-server-time-offset-seconds-vs-pc-utc",
        "10799",
    ]
    if required:
        args.append("--require-mt5-alignment")
    if current_spread is not None:
        args.extend(
            [
                "--current-broker-spread-points",
                current_spread,
                "--current-broker-spread-source",
                current_spread_source,
            ]
        )
    return args


def test_latest_db_feature_equal_to_latest_mt5_closed_bar_passes_alignment(tmp_path: Path) -> None:
    bar_time = "2026-06-11 01:15:00"
    paths = write_fixture_sources(tmp_path, row={"time_server": bar_time})
    outputs = run.build_outputs(make_args(tmp_path, paths, extra_args=alignment_args(bar_time)))
    manifest = read_json(outputs["manifest"])

    assert manifest["dry_run_status"] == "demo_no_order_dry_run_would_signal"
    assert manifest["live_alignment_status"] == "live_data_aligned_with_mt5_latest_bar"
    assert manifest["current_broker_spread_points"] == 3.0
    assert manifest["current_broker_spread_source"] == "symbol_info.spread"
    assert manifest["current_broker_spread_within_policy"] is True
    assert manifest["live_spread_gate_status"] == "live_spread_within_policy"
    assert manifest["evaluated_feature_time_server"] == bar_time
    assert manifest["latest_db_feature_time_server"] == bar_time
    assert manifest["latest_mt5_closed_bar_time_server"] == bar_time
    assert manifest["db_lag_bars_vs_mt5_latest_closed_bar"] == 0.0


def test_latest_db_feature_behind_mt5_latest_closed_bar_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, row={"time_server": "2026-06-10 22:45:00"})
    outputs = run.build_outputs(make_args(tmp_path, paths, extra_args=alignment_args()))
    manifest = read_json(outputs["manifest"])
    decision = read_csv(outputs["decision"])[0]

    assert manifest["dry_run_status"] == "demo_no_order_dry_run_would_block"
    assert manifest["feature_row_fresh"] is False
    assert manifest["live_alignment_status"] == "live_data_blocked_db_lagging_mt5_latest_bar"
    assert manifest["db_lag_minutes_vs_mt5_latest_closed_bar"] == 150.0
    assert manifest["db_lag_bars_vs_mt5_latest_closed_bar"] == 10.0
    assert "live_data_blocked_db_lagging_mt5_latest_bar" in decision["block_reasons"]


def test_pc_utc_2228_and_mt5_0115_scenario_detects_lag_without_hardcoded_offset(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, row={"time_server": "2026-06-10 22:45:00"})
    outputs = run.build_outputs(make_args(tmp_path, paths, extra_args=alignment_args()))
    manifest = read_json(outputs["manifest"])

    assert manifest["pc_utc_now"] == "2026-06-10T22:28:49+00:00"
    assert manifest["mt5_tick_time_server"] == "2026-06-11 01:28:48"
    assert manifest["latest_mt5_closed_bar_time_server"] == "2026-06-11 01:15:00"
    assert manifest["mt5_server_time_offset_seconds_vs_pc_utc"] == "10799"
    assert manifest["live_alignment_status"] == "live_data_blocked_db_lagging_mt5_latest_bar"


def test_required_mt5_unavailable_blocks_and_does_not_fake_alignment(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = run.build_outputs(make_args(tmp_path, paths, extra_args=alignment_args("", required=True, current_spread=None)))
    manifest = read_json(outputs["manifest"])
    decision = read_csv(outputs["decision"])[0]

    assert manifest["dry_run_status"] == "demo_no_order_dry_run_would_block"
    assert manifest["live_alignment_status"] == "live_data_mt5_time_basis_unavailable"
    assert manifest["latest_mt5_closed_bar_time_server"] == ""
    assert "live_data_mt5_time_basis_unavailable" in decision["block_reasons"]


def test_current_live_spread_above_policy_blocks_live_signal(tmp_path: Path) -> None:
    bar_time = "2026-06-11 01:15:00"
    paths = write_fixture_sources(tmp_path, row={"time_server": bar_time, "spread": 0.0})
    outputs = run.build_outputs(make_args(tmp_path, paths, extra_args=alignment_args(bar_time, current_spread="16")))
    manifest = read_json(outputs["manifest"])
    decision = read_csv(outputs["decision"])[0]

    assert manifest["dry_run_status"] == "demo_no_order_dry_run_would_block"
    assert manifest["feature_row_spread_broker_points"] == 0.0
    assert manifest["spread_within_gate"] is True
    assert manifest["current_broker_spread_points"] == 16.0
    assert manifest["current_broker_spread_within_policy"] is False
    assert manifest["live_spread_gate_status"] == "blocked_current_spread_above_policy"
    assert "blocked_current_spread_above_policy" in decision["block_reasons"]
    assert manifest["recommended_next_step"] == "wait_for_current_spread_within_policy_and_rerun_live_shadow"


@pytest.mark.parametrize("spread_value", [0, 0.0, "0", "0.0"])
def test_current_live_spread_zero_values_are_within_policy(spread_value: object) -> None:
    gate = run.current_live_spread_gate(
        SimpleNamespace(
            current_broker_spread_points=spread_value,
            current_broker_spread_source="symbol_info.spread",
            require_mt5_alignment=True,
        ),
        15.0,
    )

    assert gate["current_broker_spread_points"] == 0.0
    assert gate["current_broker_spread_within_policy"] is True
    assert gate["live_spread_gate_status"] == "live_spread_within_policy"


@pytest.mark.parametrize("spread_value", ["", None, "not-a-number", "NaN"])
def test_current_live_spread_invalid_values_block_as_unavailable(spread_value: object) -> None:
    gate = run.current_live_spread_gate(
        SimpleNamespace(
            current_broker_spread_points=spread_value,
            current_broker_spread_source="symbol_info.spread",
            require_mt5_alignment=True,
        ),
        15.0,
    )

    assert gate["current_broker_spread_points"] == ""
    assert gate["current_broker_spread_within_policy"] is False
    assert gate["live_spread_gate_status"] == "blocked_current_spread_unavailable"


@pytest.mark.parametrize("spread_source", ["unavailable", "not_checked_no_broker_context"])
def test_current_live_spread_unavailable_source_blocks_even_with_zero(spread_source: str) -> None:
    gate = run.current_live_spread_gate(
        SimpleNamespace(
            current_broker_spread_points=0.0,
            current_broker_spread_source=spread_source,
            require_mt5_alignment=True,
        ),
        15.0,
    )

    assert gate["current_broker_spread_points"] == ""
    assert gate["current_broker_spread_source"] == spread_source
    assert gate["current_broker_spread_within_policy"] is False
    assert gate["live_spread_gate_status"] == "blocked_current_spread_unavailable"


def test_current_live_spread_unavailable_blocks_in_live_mode(tmp_path: Path) -> None:
    bar_time = "2026-06-11 01:15:00"
    paths = write_fixture_sources(tmp_path, row={"time_server": bar_time})
    outputs = run.build_outputs(make_args(tmp_path, paths, extra_args=alignment_args(bar_time, current_spread=None)))
    manifest = read_json(outputs["manifest"])
    decision = read_csv(outputs["decision"])[0]

    assert manifest["dry_run_status"] == "demo_no_order_dry_run_would_block"
    assert manifest["current_broker_spread_points"] == ""
    assert manifest["current_broker_spread_source"] == "unavailable"
    assert manifest["current_broker_spread_within_policy"] is False
    assert manifest["live_spread_gate_status"] == "blocked_current_spread_unavailable"
    assert "blocked_current_spread_unavailable" in decision["block_reasons"]


def test_zero_current_live_spread_does_not_block_otherwise_no_signal_volume_mismatch(tmp_path: Path) -> None:
    bar_time = "2026-06-11 01:15:00"
    paths = write_fixture_sources(
        tmp_path,
        row={
            "time_server": bar_time,
            "spread": 0.0,
            "close_to_ma_fast_atr_20": 2.0,
            "tick_volume_percentile_100": 0.99,
        },
    )
    outputs = run.build_outputs(make_args(tmp_path, paths, extra_args=alignment_args(bar_time, current_spread="0.0")))
    manifest = read_json(outputs["manifest"])

    assert manifest["dry_run_status"] == "demo_no_order_dry_run_would_skip"
    assert manifest["decision_label"] == "would_skip"
    assert manifest["current_broker_spread_points"] == 0.0
    assert manifest["live_spread_gate_status"] == "live_spread_within_policy"
    assert manifest["tick_volume_percentile_100_bucket"] != "mid_tercile"


def test_spread_labels_keep_db_candle_spread_separate_from_current_broker_spread(tmp_path: Path) -> None:
    bar_time = "2026-06-11 01:15:00"
    paths = write_fixture_sources(tmp_path, row={"time_server": bar_time, "spread": 0.0})
    outputs = run.build_outputs(
        make_args(
            tmp_path,
            paths,
            extra_args=[*alignment_args(bar_time), "--current-broker-spread-points", "3"],
        )
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["spread"] == 0.0
    assert manifest["feature_row_spread_broker_points"] == 0.0
    assert manifest["feature_row_spread_source"] == "db_candle_spread"
    assert manifest["current_broker_spread_points"] == 3.0
    assert manifest["current_broker_spread_source"] == "symbol_info.spread"
    assert manifest["current_broker_spread_within_policy"] is True
    assert manifest["live_spread_gate_status"] == "live_spread_within_policy"
    assert manifest["spread_source"] == "db_candle_spread"


def test_existing_open_local_state_produces_would_block(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, state_payload={"has_open_paper_trade": True, "open_signal_id": "open"})
    outputs = run.build_outputs(make_args(tmp_path, paths))
    decision = read_csv(outputs["decision"])[0]
    state_preview = read_json(outputs["state_preview"])

    assert decision["decision_label"] == "would_block"
    assert "existing_open_local_state" in decision["block_reasons"]
    assert state_preview["existing_open_state_detected"] is True


def test_missing_plan_manifest_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_plan_manifest=True)
    outputs = run.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["dry_run_status"] == "blocked_missing_required_artifact"


def test_dry_run_only_environment_check_status_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, env_status="dry_run_no_mt5_query_performed")
    outputs = run.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["dry_run_status"] == "blocked_by_environment_check_status"


def test_non_demo_account_artifact_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, account_demo=False)
    outputs = run.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["dry_run_status"] == "blocked_by_environment_check_status"


def test_noncanonical_spread_policy_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(
        tmp_path,
        spread_unit="pips",
        max_spread_points=1.5,
        spread_current_points=1.0,
    )
    outputs = run.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["dry_run_status"] == "blocked_by_environment_check_status"


def test_missing_threshold_artifact_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_thresholds=True)
    outputs = run.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["dry_run_status"] == "blocked_missing_required_artifact"
    assert manifest["decision_label"] == "would_block"


def test_blocked_feature_table_ml_dataset_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = run.build_outputs(make_args(tmp_path, paths, table="ml_dataset"))
    manifest = read_json(outputs["manifest"])

    assert manifest["dry_run_status"] == "blocked_by_feature_source"


def test_non_allowlisted_feature_table_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = run.build_outputs(make_args(tmp_path, paths, table="random_features"))
    manifest = read_json(outputs["manifest"])

    assert manifest["dry_run_status"] == "blocked_by_feature_source"


def test_read_only_db_uri_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    original_connect = sqlite3.connect
    calls: list[tuple[object, dict[str, object]]] = []

    def tracking_connect(database: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        calls.append((database, dict(kwargs)))
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(run.sqlite3, "connect", tracking_connect)
    run.build_outputs(make_args(tmp_path, paths))

    assert any("mode=ro" in str(database) and kwargs.get("uri") is True for database, kwargs in calls)


def test_no_order_evidence_confirms_all_flags(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = run.build_outputs(make_args(tmp_path, paths))
    evidence = read_csv(outputs["no_order"])[0]

    for key in [
        "no_mt5_connection_performed",
        "no_broker_connection_performed",
        "no_account_query_performed",
        "no_symbol_query_performed",
        "no_order_execution_performed",
        "no_order_request_constructed",
        "no_order_send_called",
        "no_order_check_called",
        "no_order_calc_margin_called",
        "no_order_calc_profit_called",
        "no_db_mutation_performed",
        "no_data_generation_performed",
        "no_feature_refresh_performed",
        "no_trading_decision_performed",
    ]:
        assert evidence[key] == "true"


def test_report_includes_no_connection_order_request_db_and_approval_caveats(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = run.build_outputs(make_args(tmp_path, paths))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5 connection was performed." in report
    assert "No broker/API connection was performed." in report
    assert "No live account query was performed." in report
    assert "No live symbol query was performed." in report
    assert "No order execution was performed." in report
    assert "No order request was constructed." in report
    assert "No order_check or order_calc call was performed." in report
    assert "No database mutation was performed." in report
    assert "This dry-run is not demo broker approval." in report
    assert "spread_policy_matches_canonical: `true`" in report


def test_static_source_has_no_forbidden_external_or_order_calls() -> None:
    source = Path(run.__file__).read_text(encoding="utf-8")
    forbidden = [
        "order_" + "send(",
        "order_" + "check(",
        "order_" + "calc_margin(",
        "order_" + "calc_profit(",
        "positions_" + "get(",
        "orders_" + "get(",
        "history_orders_" + "get(",
        "history_deals_" + "get(",
        "Meta" + "Trader5",
        "mt5" + ".initialize",
    ]

    for token in forbidden:
        assert token not in source


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    run.build_outputs(make_args(tmp_path, paths))
