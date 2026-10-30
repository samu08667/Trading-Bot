from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import run_fixed_candidate_local_paper_cycle_once as orchestrator


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


def safety_fields() -> dict[str, bool]:
    return {
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_trading_decision_performed": True,
    }


def demo_config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "schema_version": 1,
        "config_role": "paper_demo_strategy_config",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "paper_only": True,
        "broker_connection_allowed": False,
        "order_execution_allowed": False,
        "real_money_allowed": False,
    }
    config.update(overrides)
    return config


def state_payload(*, open_trade: bool = False) -> dict[str, object]:
    return {
        "has_open_paper_trade": open_trade,
        "open_signal_id": "fixture_signal" if open_trade else "",
        "entry_time_server": "2026-05-27 22:45:00" if open_trade else "",
        "entry_price": 1.34308 if open_trade else None,
        "tp_price": 1.34217475 if open_trade else None,
        "sl_price": 1.3436835 if open_trade else None,
        "bars_elapsed": 0,
        "horizon_bars": 10,
        "last_seen_time_server": "2026-05-27 22:45:00" if open_trade else "",
    }


def write_spec_dir(path: Path) -> None:
    write_csv(path / orchestrator.SPEC_CSV, ["spec_section", "spec_key"], [{"spec_section": "paper", "spec_key": "ok"}])
    write_json(
        path / orchestrator.SPEC_MANIFEST,
        {"paper_only_specification": True, "warnings_count": 0, "blocking_warnings_count": 0, **safety_fields()},
    )
    (path / orchestrator.SPEC_REPORT).write_text("# Spec\n", encoding="utf-8")
    write_csv(path / orchestrator.SPEC_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_readiness_dir(path: Path) -> None:
    write_csv(
        path / orchestrator.READINESS_CSV,
        ["readiness_area", "readiness_status"],
        [{"readiness_area": "paper_boundary", "readiness_status": "ready"}],
    )
    write_json(
        path / orchestrator.READINESS_MANIFEST,
        {"paper_only_boundary_confirmed": True, "warnings_count": 0, "blocking_warnings_count": 0, **safety_fields()},
    )
    (path / orchestrator.READINESS_REPORT).write_text("# Readiness\n", encoding="utf-8")
    write_csv(path / orchestrator.READINESS_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_thresholds_dir(path: Path) -> None:
    write_json(path / orchestrator.THRESHOLDS_JSON, {"schema_version": 1, "candidate_id": "fixture"})
    write_json(path / orchestrator.THRESHOLDS_MANIFEST, {"threshold_json_valid": True, **safety_fields()})
    (path / orchestrator.THRESHOLDS_REPORT).write_text("# Thresholds\n", encoding="utf-8")
    write_csv(path / orchestrator.THRESHOLDS_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_signal_logger_dir(path: Path, *, unsafe: bool = False) -> None:
    write_csv(
        path / orchestrator.SIGNAL_CSV,
        ["run_id", "signal_state"],
        [{"run_id": "previous_signal", "signal_state": "paper_signal_opened"}],
    )
    fields = safety_fields()
    if unsafe:
        fields["no_order_execution_performed"] = False
    write_json(path / orchestrator.SIGNAL_MANIFEST, {"signal_state": "paper_signal_opened", **fields})
    (path / orchestrator.SIGNAL_REPORT).write_text("# Signal\n", encoding="utf-8")
    write_csv(path / orchestrator.SIGNAL_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_tracker_dir(path: Path) -> None:
    write_csv(
        path / orchestrator.TRACKER_CSV,
        ["run_id", "trade_status"],
        [{"run_id": "previous_tracker", "trade_status": "paper_trade_closed_tp"}],
    )
    write_json(path / orchestrator.TRACKER_MANIFEST, {"trade_status": "paper_trade_closed_tp", **safety_fields()})
    (path / orchestrator.TRACKER_REPORT).write_text("# Tracker\n", encoding="utf-8")
    write_csv(path / orchestrator.TRACKER_WARNINGS, ["warning_code", "blocking_warning"], [])


def make_args(
    tmp_path: Path,
    *,
    open_trade: bool = False,
    state_missing: bool = False,
    unsafe_previous_signal: bool = False,
    dry_run: bool = False,
) -> object:
    config_path = write_json(tmp_path / "config" / "demo.json", demo_config())
    spec_dir = tmp_path / "spec"
    readiness_dir = tmp_path / "readiness"
    thresholds_dir = tmp_path / "thresholds"
    signal_dir = tmp_path / "previous_signal"
    tracker_1 = tmp_path / "previous_tracker_1"
    tracker_2 = tmp_path / "previous_tracker_2"
    write_spec_dir(spec_dir)
    write_readiness_dir(readiness_dir)
    write_thresholds_dir(thresholds_dir)
    write_signal_logger_dir(signal_dir, unsafe=unsafe_previous_signal)
    write_tracker_dir(tracker_1)
    write_tracker_dir(tracker_2)
    state_path = tmp_path / "state" / "previous_state.json"
    if not state_missing:
        write_json(state_path, state_payload(open_trade=open_trade))
    argv = [
        "--run-id",
        "unit_local_paper_cycle_once",
        "--demo-strategy-config",
        str(config_path),
        "--demo-strategy-spec-dir",
        str(spec_dir),
        "--paper-signal-logger-readiness-dir",
        str(readiness_dir),
        "--numeric-tercile-thresholds-dir",
        str(thresholds_dir),
        "--feature-source-db",
        str(tmp_path / "db" / "trading_bot.db"),
        "--previous-paper-state-json",
        str(state_path),
        "--previous-paper-signal-logger-dir",
        str(signal_dir),
        "--previous-paper-trade-tracker-dirs",
        str(tracker_1),
        str(tracker_2),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    if dry_run:
        argv.append("--dry-run")
    return orchestrator.build_parser().parse_args(argv)


def output_dir_from_command(command: list[str]) -> Path:
    return Path(command[command.index("--output-dir") + 1])


def role_from_command(command: list[str]) -> str:
    script = Path(command[1]).name
    if "freshness" in script:
        return "freshness"
    if "paper_signal_logger" in script:
        return "signal_logger"
    if "paper_trade_tracker" in script:
        return "trade_tracker"
    if "paper_cycle_summary" in script:
        return "cycle_summary"
    raise AssertionError(f"unexpected child script: {script}")


def fake_child_runner_factory(
    *,
    stale: bool = False,
    signal_state: str = "paper_signal_skipped",
    tracker_open_after: bool = True,
    tracker_trade_status: str = "paper_trade_still_open",
    final_cycle_status: str = "paper_cycle_completed_tp",
    fail_role: str | None = None,
    executed_roles: list[str] | None = None,
) -> object:
    roles = executed_roles if executed_roles is not None else []

    def fake_runner(command: list[str], stdout_log: Path, stderr_log: Path) -> int:
        role = role_from_command(command)
        roles.append(role)
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stdout_log.write_text(f"{role} stdout", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        if fail_role == role:
            return 1
        output_dir = output_dir_from_command(command)
        output_dir.mkdir(parents=True, exist_ok=True)
        if role == "freshness":
            write_json(
                output_dir / orchestrator.FRESHNESS_MANIFEST,
                {
                    "stale_input_source": stale,
                    "freshness_ready_for_manual_single_shot_paper_logging": not stale,
                    "recommended_next_step": "manual_feature_source_refresh_required" if stale else "manual_single_shot_paper_logger_rerun_allowed",
                },
            )
        elif role == "signal_logger":
            write_json(
                output_dir / orchestrator.SIGNAL_CHILD_MANIFEST,
                {
                    "signal_state": signal_state,
                    "has_open_paper_trade_after": signal_state == "paper_signal_opened",
                    "no_broker_connection_performed": True,
                    "no_order_execution_performed": True,
                },
            )
        elif role == "trade_tracker":
            write_json(
                output_dir / orchestrator.TRACKER_CHILD_MANIFEST,
                {
                    "trade_status": tracker_trade_status,
                    "has_open_paper_trade_after": tracker_open_after,
                    "no_broker_connection_performed": True,
                    "no_order_execution_performed": True,
                },
            )
        elif role == "cycle_summary":
            write_json(
                output_dir / orchestrator.CYCLE_SUMMARY_MANIFEST,
                {
                    "final_cycle_status": final_cycle_status,
                    "recommended_next_step": "rerun_paper_signal_logger_only_when_data_fresh_and_no_open_trade",
                },
            )
        return 0

    return fake_runner


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        orchestrator.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_dry_run_writes_command_plan_and_executes_no_child_scripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("child script should not run in dry-run")

    monkeypatch.setattr(orchestrator, "run_child_command", fail_if_called)
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=True, dry_run=True))
    manifest = read_json(outputs["manifest"])
    commands = read_csv(outputs["child_commands"])

    assert manifest["orchestrator_status"] == "dry_run_planned_only"
    assert manifest["child_executed_count"] == 0
    assert commands
    assert all(row["executed"] == "false" for row in commands)


def test_output_artifacts_are_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "run_child_command", fake_child_runner_factory())
    outputs = orchestrator.build_outputs(make_args(tmp_path))

    assert outputs["orchestrator"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()
    assert outputs["child_commands"].exists()
    assert outputs["child_results"].exists()


def test_stale_freshness_stops_before_signal_or_tracker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[str] = []
    monkeypatch.setattr(orchestrator, "run_child_command", fake_child_runner_factory(stale=True, executed_roles=executed))
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=False))
    manifest = read_json(outputs["manifest"])

    assert executed == ["freshness"]
    assert manifest["orchestrator_status"] == "blocked_stale_input_source"
    assert manifest["recommended_next_step"] == "manual_feature_source_refresh_required"


def test_fresh_no_open_trade_runs_signal_logger_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[str] = []
    monkeypatch.setattr(
        orchestrator,
        "run_child_command",
        fake_child_runner_factory(signal_state="paper_signal_opened", executed_roles=executed),
    )
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=False))
    manifest = read_json(outputs["manifest"])

    assert executed == ["freshness", "signal_logger"]
    assert manifest["orchestrator_status"] == "paper_signal_opened"
    assert manifest["signal_state"] == "paper_signal_opened"


def test_fresh_open_trade_runs_tracker_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[str] = []
    monkeypatch.setattr(
        orchestrator,
        "run_child_command",
        fake_child_runner_factory(tracker_open_after=True, executed_roles=executed),
    )
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=True))
    manifest = read_json(outputs["manifest"])

    assert executed == ["freshness", "trade_tracker"]
    assert manifest["orchestrator_status"] == "paper_trade_still_open_after_tracker"
    assert manifest["final_has_open_paper_trade"] is True


def test_tracker_closes_trade_then_cycle_summary_is_built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[str] = []
    monkeypatch.setattr(
        orchestrator,
        "run_child_command",
        fake_child_runner_factory(
            tracker_open_after=False,
            tracker_trade_status="paper_trade_closed_tp",
            final_cycle_status="paper_cycle_completed_tp",
            executed_roles=executed,
        ),
    )
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=True))
    manifest = read_json(outputs["manifest"])

    assert executed == ["freshness", "trade_tracker", "cycle_summary"]
    assert manifest["orchestrator_status"] == "paper_trade_closed_and_summary_built"
    assert manifest["final_cycle_status"] == "paper_cycle_completed_tp"


def test_tracker_still_open_does_not_build_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[str] = []
    monkeypatch.setattr(
        orchestrator,
        "run_child_command",
        fake_child_runner_factory(tracker_open_after=True, executed_roles=executed),
    )
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=True))
    manifest = read_json(outputs["manifest"])

    assert executed == ["freshness", "trade_tracker"]
    assert manifest["orchestrator_status"] == "paper_trade_still_open_after_tracker"


def test_missing_previous_state_blocks_after_freshness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[str] = []
    monkeypatch.setattr(orchestrator, "run_child_command", fake_child_runner_factory(executed_roles=executed))
    outputs = orchestrator.build_outputs(make_args(tmp_path, state_missing=True))
    manifest = read_json(outputs["manifest"])

    assert executed == ["freshness"]
    assert manifest["orchestrator_status"] == "blocked_missing_or_unreadable_state"


def test_child_script_allowlist_blocks_unknown_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(orchestrator.CHILD_SCRIPT_PATHS, "freshness", Path("scripts/not_allowed_child.py"))

    def fail_if_called(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("unknown child script should be blocked before execution")

    monkeypatch.setattr(orchestrator, "run_child_command", fail_if_called)
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=False))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["orchestrator_status"] == "blocked_by_config"
    assert any(warning["warning_code"] == "child_script_not_allowlisted" for warning in warnings)


def test_child_failure_stops_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "run_child_command", fake_child_runner_factory(fail_role="freshness"))
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=False))
    manifest = read_json(outputs["manifest"])

    assert manifest["orchestrator_status"] == "failed_child_script"
    assert manifest["child_failed_count"] == 1


def test_previous_artifact_unsafe_boundary_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("unsafe previous artifact should block before child execution")

    monkeypatch.setattr(orchestrator, "run_child_command", fail_if_called)
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=False, unsafe_previous_signal=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["orchestrator_status"] == "blocked_by_previous_artifact_boundary"
    assert manifest["child_executed_count"] == 0


def test_child_outputs_are_inside_orchestrator_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "run_child_command", fake_child_runner_factory(signal_state="paper_signal_opened"))
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=False))
    output_root = outputs["manifest"].parent.resolve()
    results = read_csv(outputs["child_results"])

    assert results
    for result in results:
        assert Path(result["output_dir"]).resolve().is_relative_to(output_root)


def test_manifest_counts_match_csv_warnings_and_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "run_child_command", fake_child_runner_factory(signal_state="paper_signal_opened"))
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=False))
    warnings = read_csv(outputs["warnings"])
    commands = read_csv(outputs["child_commands"])
    results = read_csv(outputs["child_results"])
    manifest = read_json(outputs["manifest"])

    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(
        1 for warning in warnings if warning["blocking_warning"].lower() == "true"
    )
    assert manifest["child_command_count"] == len(commands)
    assert manifest["child_executed_count"] == sum(1 for command in commands if command["executed"] == "true")
    assert manifest["child_failed_count"] == sum(1 for result in results if result["status"] == "failed")


def test_report_includes_no_loop_no_refresh_no_connection_caveats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "run_child_command", fake_child_runner_factory(signal_state="paper_signal_opened"))
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=False))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "does not loop, schedule itself, or stay resident" in report
    assert "No feature refresh was performed." in report
    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No order execution was performed." in report
    assert "No database mutation was performed." in report


def test_no_real_heavy_or_child_commands_run_without_fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("real child command should not be executed")

    monkeypatch.setattr(orchestrator, "run_child_command", fail_if_called)
    outputs = orchestrator.build_outputs(make_args(tmp_path, open_trade=False, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["orchestrator_status"] == "dry_run_planned_only"
