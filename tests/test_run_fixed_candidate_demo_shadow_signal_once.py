from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_fixed_candidate_demo_shadow_signal_once as shadow


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def canonical_registry(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
    }
    payload.update(overrides)
    return payload


def no_order_flags() -> dict[str, bool]:
    return {
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_trading_decision_performed": True,
    }


def status_for_decision(decision_label: str) -> str:
    return {
        "would_skip": "demo_no_order_cycle_completed_would_skip",
        "would_signal": "demo_no_order_cycle_completed_would_signal",
        "would_block": "demo_no_order_cycle_completed_would_block",
    }[decision_label]


def write_cycle_artifacts(
    root: Path,
    *,
    decision_label: str = "would_skip",
    omit_cycle_flags: set[str] | None = None,
    cycle_flag_overrides: dict[str, object] | None = None,
    omit_child_flags: set[str] | None = None,
    child_flag_overrides: dict[str, object] | None = None,
    child_overrides: dict[str, object] | None = None,
    write_child: bool = True,
) -> Path:
    child_dir = root / "children" / "dry_run"
    child_manifest_path = child_dir / shadow.CHILD_DRY_RUN_MANIFEST
    cycle_flags: dict[str, object] = {
        **no_order_flags(),
        "no_order_boundary_confirmed": True,
        "missing_no_order_flag_count": 0,
        "unsafe_no_order_flag_count": 0,
    }
    for flag in omit_cycle_flags or set():
        cycle_flags.pop(flag, None)
    cycle_flags.update(cycle_flag_overrides or {})
    write_json(
        root / shadow.CYCLE_MANIFEST,
        {
            "cycle_status": status_for_decision(decision_label),
            "latest_child_manifest_path": str(child_manifest_path),
            "db_refresh_before_shadow_enabled": True,
            "mt5_time_basis_checked": True,
            "latest_mt5_closed_bar_time_server": "2026-05-30 01:45:00",
            "latest_db_price_bar_time_server_before_import": "2026-05-30 01:15:00",
            "latest_db_feature_time_server_before_generation": "2026-05-30 01:15:00",
            "effective_import_from_date": "2026-05-29T23:15:00Z",
            "effective_import_to_date": "2026-05-30T01:46:00Z",
            "effective_import_to_date_source": "latest_mt5_closed_bar_time_server",
            "latest_db_price_bar_time_server_after_import": "2026-05-30 01:45:00",
            "latest_db_feature_time_server_after_generation": "2026-05-30 01:45:00",
            "imported_rows_count": 2,
            "generated_features_count": 100,
            "latest_db_price_bar_time_server": "2026-05-30 01:45:00",
            "latest_db_feature_time_server": "2026-05-30 01:45:00",
            "db_lag_bars_vs_mt5_latest_closed_bar": 0.0,
            "db_lag_minutes_vs_mt5_latest_closed_bar": 0.0,
            "live_alignment_status": "live_data_aligned_with_mt5_latest_bar",
            "child_time_server": "2026-05-30 01:45:00",
            "child_session_observed": "Off_hours",
            "child_spread": 3.0,
            "child_spread_within_gate": True,
            "child_close_to_ma_fast_atr_20_bucket": "high_tercile",
            "child_tick_volume_percentile_100_bucket": "mid_tercile",
            "child_skip_reason_count": 0,
            "child_block_reason_count": 1 if decision_label == "would_block" else 0,
            **cycle_flags,
        },
    )
    if write_child:
        child_flags = no_order_flags()
        for flag in omit_child_flags or set():
            child_flags.pop(flag, None)
        child_flags.update(child_flag_overrides or {})
        child_payload = {
            "decision_label": decision_label,
            "dry_run_status": f"demo_no_order_dry_run_{decision_label}",
            "time_server": "2026-05-30 01:45:00",
            "session_observed": "Off_hours",
            "spread": 3.0,
            "spread_unit": "broker_points",
            "max_spread_points": 15.0,
            "spread_within_gate": True,
            "close": 1.2345,
            "atr_20": 0.0004,
            "close_to_ma_fast_atr_20_bucket": "high_tercile",
            "tick_volume_percentile_100_bucket": "mid_tercile",
            "skip_reason_count": 0 if decision_label != "would_skip" else 1,
            "block_reason_count": 1 if decision_label == "would_block" else 0,
            "volume_preview_status": "not_computed_no_order_calc_forbidden",
            **child_flags,
        }
        if decision_label == "would_signal":
            child_payload.update(
                {
                    "entry_reference_price": 1.2345,
                    "tp_price_preview": 1.2339,
                    "sl_price_preview": 1.2349,
                }
            )
        child_payload.update(child_overrides or {})
        write_json(child_manifest_path, child_payload)
    return root


def make_args(
    tmp_path: Path,
    *,
    registry_payload: dict[str, object] | None = None,
    existing_cycle_dir: Path | None = None,
    run_cycle: bool = False,
    dry_run: bool = False,
    no_order_cycle_script: Path | None = None,
    cycle_output_dir: Path | None = None,
) -> object:
    registry_path = write_json(tmp_path / "registry.json", registry_payload or canonical_registry())
    argv = [
        "--run-id",
        "unit_shadow_signal_once",
        "--canonical-registry",
        str(registry_path),
        "--no-order-cycle-script",
        str(no_order_cycle_script or shadow.DEFAULT_NO_ORDER_CYCLE_SCRIPT),
        "--python-executable",
        "python",
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    if existing_cycle_dir is not None:
        argv.extend(["--existing-no-order-cycle-dir", str(existing_cycle_dir)])
    if run_cycle:
        argv.append("--run-cycle")
    if dry_run:
        argv.append("--dry-run")
    if cycle_output_dir is not None:
        argv.extend(["--cycle-output-dir", str(cycle_output_dir)])
    return shadow.build_parser().parse_args(argv)


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        shadow.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_dry_run_plan_only_writes_artifacts_and_executes_no_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child should not run")

    monkeypatch.setattr(subprocess, "run", fail_if_called)
    outputs = shadow.build_outputs(make_args(tmp_path, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "shadow_signal_plan_only"
    assert manifest["child_command_count"] == 0
    for path in outputs.values():
        assert path.exists()


def test_existing_cycle_would_skip_maps_to_shadow_no_signal(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_skip")
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "shadow_no_signal"
    assert manifest["shadow_decision_label"] == "no_signal"
    assert manifest["recommended_next_step"] == "monitor_next_feature_row_or_run_shadow_again_later"


def test_existing_cycle_would_signal_maps_to_shadow_signal_detected(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_signal")
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "shadow_signal_detected"
    assert manifest["manual_review_required"] is True
    assert manifest["entry_reference_price"] == 1.2345


def test_shadow_manifest_writes_explicit_false_direct_order_safety_fields(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_signal")
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_execution_performed"] is False
    assert manifest["order_check_called"] is False
    assert manifest["order_send_called"] is False
    assert manifest["order_request_constructed"] is False
    assert manifest["demo_broker_approval_performed"] is False
    assert manifest["future_state_json_written"] is False
    assert manifest["no_order_execution_performed"] is True
    assert manifest["no_order_check_called"] is True
    assert manifest["no_order_send_called"] is True


def test_shadow_signal_detected_prints_valid_signal_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_signal")
    registry_path = write_json(tmp_path / "registry.json", canonical_registry())
    result = shadow.main(
        [
            "--run-id",
            "unit_shadow_signal_once",
            "--canonical-registry",
            str(registry_path),
            "--existing-no-order-cycle-dir",
            str(cycle_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert "status: SIGNAL DETECTED" in output
    assert "RESULT: VALID SIGNAL - proceed with manual approval prep dry-run" in output


def test_shadow_no_signal_prints_no_valid_signal_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_skip")
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))

    shadow.print_console_summary_from_outputs(outputs)
    output = capsys.readouterr().out

    assert "status: NO SIGNAL" in output
    assert "RESULT: NO VALID SIGNAL - wait for next M15 candle" in output


@pytest.mark.parametrize(
    ("overrides", "expected_line"),
    [
        (
            {"close_to_ma_fast_atr_20_bucket": "low_tercile"},
            "- close_to_ma_fast_atr_20_bucket expected high_tercile observed low_tercile",
        ),
        (
            {"tick_volume_percentile_100_bucket": "high_tercile"},
            "- tick_volume_percentile_100_bucket expected mid_tercile observed high_tercile",
        ),
        (
            {"session_observed": "London"},
            "- session_observed expected Off_hours observed London",
        ),
    ],
)
def test_console_summary_shows_missing_required_condition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    overrides: dict[str, object],
    expected_line: str,
) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_skip", child_overrides=overrides)
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))

    shadow.print_console_summary_from_outputs(outputs)
    output = capsys.readouterr().out

    assert "missing_conditions:" in output
    assert expected_line in output


def test_console_summary_shows_spread_blocked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cycle_dir = write_cycle_artifacts(
        tmp_path / "cycle",
        decision_label="would_skip",
        child_overrides={"spread": 20.0, "spread_within_gate": False},
    )
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))

    shadow.print_console_summary_from_outputs(outputs)
    output = capsys.readouterr().out

    assert "feature_row_spread_broker_points: 20.0 broker_points [BLOCKED]" in output
    assert "- spread expected <= 15.0 broker_points observed 20.0" in output


def test_console_summary_prints_alignment_times_separately(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cycle_dir = write_cycle_artifacts(
        tmp_path / "cycle",
        decision_label="would_block",
        child_overrides={
            "evaluated_feature_time_server": "2026-06-10 22:45:00",
            "latest_db_price_bar_time_server": "2026-06-10 22:45:00",
            "latest_db_feature_time_server": "2026-06-10 22:45:00",
            "latest_mt5_closed_bar_time_server": "2026-06-11 01:15:00",
            "db_lag_bars_vs_mt5_latest_closed_bar": 10.0,
            "live_alignment_status": "live_data_blocked_db_lagging_mt5_latest_bar",
        },
    )
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))

    shadow.print_console_summary_from_outputs(outputs)
    output = capsys.readouterr().out

    assert "evaluated_feature_time_server: 2026-06-10 22:45:00" in output
    assert "latest_db_price_bar_time_server: 2026-06-10 22:45:00" in output
    assert "latest_db_feature_time_server: 2026-06-10 22:45:00" in output
    assert "latest_mt5_closed_bar_time_server: 2026-06-11 01:15:00" in output
    assert "db_lag_bars_vs_mt5_latest_closed_bar: 10.0" in output


def test_console_summary_exposes_refresh_import_generation_fields(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_skip")
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))

    shadow.print_console_summary_from_outputs(outputs)
    output = capsys.readouterr().out

    assert "db_refresh_before_shadow_enabled: true" in output
    assert "mt5_time_basis_checked: true" in output
    assert "effective_import_from_date: 2026-05-29T23:15:00Z" in output
    assert "effective_import_to_date: 2026-05-30T01:46:00Z" in output
    assert "effective_import_to_date_source: latest_mt5_closed_bar_time_server" in output
    assert "latest_db_price_bar_time_server_before_import: 2026-05-30 01:15:00" in output


def test_alignment_blocker_from_cycle_prevents_manual_review(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(
        tmp_path / "cycle",
        decision_label="would_signal",
        cycle_flag_overrides={
            "latest_mt5_closed_bar_time_server": "2026-06-11 21:15:00",
            "latest_db_price_bar_time_server_after_import": "2026-06-11 20:00:00",
            "latest_db_feature_time_server_after_generation": "2026-06-11 20:00:00",
            "latest_db_price_bar_time_server": "2026-06-11 20:00:00",
            "latest_db_feature_time_server": "2026-06-11 20:00:00",
            "db_lag_bars_vs_mt5_latest_closed_bar": 5.0,
            "db_lag_minutes_vs_mt5_latest_closed_bar": 75.0,
            "live_alignment_status": "live_data_blocked_db_lagging_mt5_latest_bar",
        },
    )
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "shadow_blocked"
    assert manifest["manual_review_required"] is False
    assert manifest["live_alignment_status"] == "live_data_blocked_db_lagging_mt5_latest_bar"
    assert manifest["recommended_next_step"] == "refresh_price_bars_features_and_rerun_live_shadow"


def test_console_summary_labels_feature_and_current_spread_separately(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cycle_dir = write_cycle_artifacts(
        tmp_path / "cycle",
        decision_label="would_skip",
        child_overrides={
            "spread": 0.0,
            "feature_row_spread_broker_points": 0.0,
            "feature_row_spread_source": "db_candle_spread",
            "current_broker_spread_points": 3.0,
            "current_broker_spread_source": "symbol_info.spread",
            "current_broker_spread_within_policy": True,
            "live_spread_gate_status": "live_spread_within_policy",
            "spread_source": "db_candle_spread",
        },
    )
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))

    shadow.print_console_summary_from_outputs(outputs)
    output = capsys.readouterr().out

    assert "feature_row_spread_broker_points: 0.0 broker_points [OK]" in output
    assert "feature_row_spread_source: db_candle_spread" in output
    assert "current_broker_spread_points: 3.0" in output
    assert "current_broker_spread_source: symbol_info.spread" in output
    assert "live_spread_gate_status: live_spread_within_policy" in output
    assert "spread_source: db_candle_spread" in output


def test_shadow_manifest_preserves_zero_current_broker_spread(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(
        tmp_path / "cycle",
        decision_label="would_signal",
        child_overrides={
            "current_broker_spread_points": 0.0,
            "current_broker_spread_source": "symbol_info.spread",
            "current_broker_spread_within_policy": True,
            "current_broker_spread_policy_max_points": 15.0,
            "live_spread_gate_status": "live_spread_within_policy",
        },
    )
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "shadow_signal_detected"
    assert manifest["current_broker_spread_points"] == 0.0
    assert manifest["current_broker_spread_within_policy"] is True
    assert manifest["live_spread_gate_status"] == "live_spread_within_policy"


def test_console_summary_prints_zero_current_broker_spread(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cycle_dir = write_cycle_artifacts(
        tmp_path / "cycle",
        decision_label="would_signal",
        child_overrides={
            "current_broker_spread_points": 0.0,
            "current_broker_spread_source": "symbol_info.spread",
            "current_broker_spread_within_policy": True,
            "live_spread_gate_status": "live_spread_within_policy",
        },
    )
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))

    shadow.print_console_summary_from_outputs(outputs)
    output = capsys.readouterr().out

    assert "current_broker_spread_points: 0.0" in output
    assert "live_spread_gate_status: live_spread_within_policy" in output


def test_zero_current_broker_spread_with_volume_mismatch_is_no_signal_not_blocked(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(
        tmp_path / "cycle",
        decision_label="would_skip",
        child_overrides={
            "tick_volume_percentile_100_bucket": "high_tercile",
            "skip_reason_count": 1,
            "current_broker_spread_points": 0.0,
            "current_broker_spread_source": "symbol_info.spread",
            "current_broker_spread_within_policy": True,
            "live_spread_gate_status": "live_spread_within_policy",
        },
    )
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "shadow_no_signal"
    assert manifest["current_broker_spread_points"] == 0.0
    assert manifest["live_spread_gate_status"] == "live_spread_within_policy"
    assert manifest["manual_review_required"] is False


def test_high_current_live_spread_blocks_manual_review(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(
        tmp_path / "cycle",
        decision_label="would_block",
        child_overrides={
            "spread": 0.0,
            "feature_row_spread_broker_points": 0.0,
            "feature_row_spread_source": "db_candle_spread",
            "spread_within_gate": True,
            "current_broker_spread_points": 16.0,
            "current_broker_spread_source": "symbol_info.spread",
            "current_broker_spread_within_policy": False,
            "current_broker_spread_policy_max_points": 15.0,
            "live_spread_gate_status": "blocked_current_spread_above_policy",
            "block_reason_count": 1,
        },
    )
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "shadow_blocked"
    assert manifest["manual_review_required"] is False
    assert manifest["feature_row_spread_broker_points"] == 0.0
    assert manifest["current_broker_spread_points"] == 16.0
    assert manifest["live_spread_gate_status"] == "blocked_current_spread_above_policy"
    assert manifest["recommended_next_step"] == "wait_for_current_spread_within_policy_and_rerun_live_shadow"


def test_blocking_warning_prints_blocked_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_skip", omit_cycle_flags={"no_order_check_called"})
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))

    shadow.print_console_summary_from_outputs(outputs)
    output = capsys.readouterr().out

    assert "status: BLOCKED" in output
    assert "RESULT: BLOCKED - inspect warnings before continuing" in output


def test_console_summary_does_not_change_output_artifacts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_signal")
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    before = {name: path.read_bytes() for name, path in outputs.items()}

    shadow.print_console_summary_from_outputs(outputs)
    capsys.readouterr()
    after = {name: path.read_bytes() for name, path in outputs.items()}

    assert after == before


def test_existing_cycle_would_block_maps_to_shadow_blocked(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_block")
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "shadow_blocked"
    assert manifest["shadow_decision_label"] == "blocked"


def test_run_cycle_executes_exactly_one_allowlisted_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[list[str]] = []
    cycle_output_dir = tmp_path / "cycle_child_out"

    def fake_run(command: list[str], **kwargs: object) -> object:
        assert kwargs.get("shell") is False
        assert isinstance(command, list)
        executed.append(command)
        write_cycle_artifacts(cycle_output_dir, decision_label="would_skip")
        return SimpleNamespace(returncode=0, stdout="child stdout", stderr="child stderr")

    monkeypatch.setattr(subprocess, "run", fake_run)
    outputs = shadow.build_outputs(make_args(tmp_path, run_cycle=True, cycle_output_dir=cycle_output_dir))
    manifest = read_json(outputs["manifest"])

    assert len(executed) == 1
    assert Path(executed[0][1]).resolve() == shadow.DEFAULT_NO_ORDER_CYCLE_SCRIPT.resolve()
    assert manifest["shadow_status"] == "shadow_no_signal"
    assert manifest["child_success_count"] == 1


def test_failed_child_command_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: object) -> object:
        return SimpleNamespace(returncode=1, stdout="bad stdout", stderr="bad stderr")

    monkeypatch.setattr(subprocess, "run", fake_run)
    outputs = shadow.build_outputs(make_args(tmp_path, run_cycle=True, cycle_output_dir=tmp_path / "cycle_child_out"))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "blocked_child_command_failed"
    assert manifest["child_failure_count"] == 1


def test_missing_cycle_manifest_blocks(tmp_path: Path) -> None:
    cycle_dir = tmp_path / "missing_cycle"
    cycle_dir.mkdir()
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "blocked_missing_required_artifact"


def test_missing_child_manifest_blocks_when_cycle_completed(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_skip", write_child=False)
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "blocked_child_manifest_missing"


def test_missing_no_order_flag_blocks(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_skip", omit_cycle_flags={"no_order_check_called"})
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "blocked_by_no_order_boundary"
    assert manifest["missing_no_order_flag_count"] == 1


def test_unsafe_no_order_flag_false_blocks(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(
        tmp_path / "cycle",
        decision_label="would_skip",
        cycle_flag_overrides={"no_order_request_constructed": False},
    )
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "blocked_by_no_order_boundary"
    assert manifest["unsafe_no_order_flag_count"] == 1


def test_noncanonical_registry_spread_policy_blocks(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_skip")
    outputs = shadow.build_outputs(
        make_args(tmp_path, registry_payload=canonical_registry(max_spread_points=2.5), existing_cycle_dir=cycle_dir)
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "blocked_by_config_boundary"


def test_same_name_no_order_cycle_script_outside_repo_is_rejected(tmp_path: Path) -> None:
    fake_script = tmp_path / "scripts" / "run_fixed_candidate_demo_no_order_cycle_once.py"
    fake_script.parent.mkdir()
    fake_script.write_text("# fake\n", encoding="utf-8")
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_skip")
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir, no_order_cycle_script=fake_script))
    manifest = read_json(outputs["manifest"])

    assert manifest["shadow_status"] == "blocked_by_config_boundary"


def test_review_packet_includes_signal_evidence_for_would_signal(tmp_path: Path) -> None:
    cycle_dir = write_cycle_artifacts(tmp_path / "cycle", decision_label="would_signal")
    outputs = shadow.build_outputs(make_args(tmp_path, existing_cycle_dir=cycle_dir))
    packet = read_json(outputs["review_packet"])

    assert packet["shadow_status"] == "shadow_signal_detected"
    assert packet["manual_review_required"] is True
    assert packet["signal_evidence"]["decision_label"] == "would_signal"
    assert packet["price_preview"]["tp_price_preview"] == 1.2339


def test_no_order_evidence_confirms_no_scheduler_loop_background_and_no_order_path(tmp_path: Path) -> None:
    outputs = shadow.build_outputs(make_args(tmp_path, dry_run=True))
    rows = read_csv(outputs["no_order_evidence"])

    assert rows[0]["no_order_execution_performed"] == "true"
    assert rows[0]["no_order_request_constructed"] == "true"
    assert rows[0]["no_order_check_called"] == "true"
    assert rows[0]["no_order_calc_margin_called"] == "true"
    assert rows[0]["no_scheduler_added"] == "true"
    assert rows[0]["no_loop_added"] == "true"
    assert rows[0]["no_background_task_added"] == "true"


def test_report_includes_safety_caveats(tmp_path: Path) -> None:
    outputs = shadow.build_outputs(make_args(tmp_path, dry_run=True))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No order execution was performed." in report
    assert "No broker order request was constructed." in report
    assert "No order_check or order_calc call was performed." in report
    assert "No broker approval was performed." in report
    assert "not a scheduler" in report


def test_static_source_has_no_forbidden_order_function_calls() -> None:
    source = Path("scripts/run_fixed_candidate_demo_shadow_signal_once.py").read_text(encoding="utf-8")
    forbidden = [
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


def test_static_source_has_no_scheduler_loop_or_background_apis() -> None:
    source = Path("scripts/run_fixed_candidate_demo_shadow_signal_once.py").read_text(encoding="utf-8")
    forbidden = [
        "Task Scheduler",
        "schtasks",
        "while True",
        "schedule.",
        "APScheduler",
        "threading.Timer",
    ]

    for token in forbidden:
        assert token not in source


def test_no_replay_cost_holdout_or_paper_workflow_child_scripts_are_allowlisted() -> None:
    command = shadow.build_child_command(
        shadow.build_parser().parse_args(
            [
                "--run-id",
                "unit",
                "--run-cycle",
                "--output-dir",
                "out",
            ]
        ),
        Path("out"),
    )

    assert command is not None
    script_name = Path(command["script"]).name
    assert script_name == "run_fixed_candidate_demo_no_order_cycle_once.py"
    forbidden_parts = ("paper", "replay", "backtest", "cost", "holdout", "stress", "walk")
    assert not any(part in script_name for part in forbidden_parts)


def test_no_heavy_commands_are_executed_in_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("subprocess should not run in dry-run plan-only")

    monkeypatch.setattr(subprocess, "run", fail_if_called)
    shadow.build_outputs(make_args(tmp_path, dry_run=True))
