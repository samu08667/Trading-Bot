from __future__ import annotations

import csv
import json
import subprocess
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_fixed_candidate_demo_no_order_cycle_once as cycle


@pytest.fixture(autouse=True)
def no_real_mt5_collection(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if "collect_mt5_time_basis" in request.node.name:
        return
    monkeypatch.setattr(cycle, "collect_mt5_time_basis", lambda _args: cycle.mt5_time_basis_unavailable("mocked_unit_test"))


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
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "paper_only": True,
        "broker_connection_allowed": False,
        "order_execution_allowed": False,
        "real_money_allowed": False,
        "spread_and_session_controls": {
            "spread_unit": "broker_points",
            "max_spread_points": 15.0,
        },
    }
    config.update(overrides)
    return config


def no_order_flags() -> dict[str, bool]:
    return {
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_candidate_quality_final_decision_performed": True,
        "no_trading_decision_performed": True,
    }


def plan_manifest(status: str = "demo_no_order_dry_run_plan_available_with_caveats") -> dict[str, object]:
    return {
        "run_id": "fixture_plan",
        "plan_status": status,
        "recommended_next_step": "implement_run_fixed_candidate_demo_no_order_dry_run",
        **no_order_flags(),
    }


def environment_manifest(status: str = "environment_check_available_with_caveats") -> dict[str, object]:
    return {
        "run_id": "fixture_env",
        "environment_check_status": status,
        "is_demo_account": True,
        "spread_policy_matches_canonical": True,
        "spread_within_config_gate": True,
        **no_order_flags(),
    }


def write_fixture_sources(
    tmp_path: Path,
    *,
    config_payload: dict[str, object] | None = None,
    plan_status: str = "demo_no_order_dry_run_plan_available_with_caveats",
    env_status: str = "environment_check_available_with_caveats",
) -> dict[str, Path]:
    config_path = write_json(tmp_path / "config" / "demo.json", config_payload or demo_config())
    plan_dir = tmp_path / "plan"
    env_dir = tmp_path / "env"
    spec_dir = tmp_path / "spec"
    thresholds_path = tmp_path / "thresholds" / "thresholds.json"
    write_json(plan_dir / cycle.PLAN_MANIFEST, plan_manifest(plan_status))
    write_json(env_dir / cycle.ENV_MANIFEST, environment_manifest(env_status))
    write_json(thresholds_path, {"schema_version": 1})
    canonical_path = write_json(
        tmp_path / "config" / "fixed_candidate_current_canonical.json",
        {
            "candidate_id": "gbpusd_short_h10_1_5_off_hours",
            "numeric_tercile_thresholds_json": str(thresholds_path),
        },
    )
    spec_dir.mkdir(parents=True, exist_ok=True)
    return {"config": config_path, "plan": plan_dir, "env": env_dir, "spec": spec_dir, "thresholds": thresholds_path, "canonical": canonical_path}


def make_args(tmp_path: Path, paths: dict[str, Path], *, dry_run: bool = False, explicit_threshold: bool = True) -> object:
    argv = [
        "--run-id",
        "unit_demo_no_order_cycle_once",
        "--symbol",
        "GBPUSD",
        "--timeframe",
        "M15",
        "--feature-source-db",
        str(tmp_path / "trading_bot.db"),
        "--from-date",
        "2026-05-30T00:00:00Z",
        "--to-date",
        "2026-05-30T03:00:00Z",
        "--demo-no-order-dry-run-plan-dir",
        str(paths["plan"]),
        "--demo-environment-check-dir",
        str(paths["env"]),
        "--demo-strategy-config",
        str(paths["config"]),
        "--demo-strategy-spec-dir",
        str(paths["spec"]),
        "--canonical-registry",
        str(paths["canonical"]),
        "--python-executable",
        "python",
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    if explicit_threshold:
        argv.extend(["--tercile-thresholds-json", str(paths["thresholds"])])
    if dry_run:
        argv.append("--dry-run")
    return cycle.build_parser().parse_args(argv)


def child_step_from_command(command: list[str]) -> str:
    script_name = Path(command[1]).name
    if script_name == "import_price_bars.py":
        return "import_price_bars"
    if script_name == "generate_price_features.py":
        return "generate_price_features"
    if script_name == "run_fixed_candidate_demo_no_order_dry_run.py":
        return "demo_no_order_dry_run"
    raise AssertionError(f"unexpected script {script_name}")


def no_order_output_dir_from_command(command: list[str]) -> Path:
    return Path(command[command.index("--output-dir") + 1])


def fake_subprocess_run(
    *,
    decision_label: str = "would_skip",
    dry_run_status: str = "demo_no_order_dry_run_would_skip",
    fail_step: str | None = None,
    create_child_manifest: bool = True,
    omit_child_flags: set[str] | None = None,
    child_flag_overrides: dict[str, object] | None = None,
    executed: list[str] | None = None,
) -> object:
    executed_steps = executed if executed is not None else []

    def fake_run(command: list[str], **kwargs: object) -> object:
        assert kwargs.get("shell") is False
        assert isinstance(command, list)
        step = child_step_from_command(command)
        executed_steps.append(step)
        if step == fail_step:
            return SimpleNamespace(returncode=1, stdout=f"{step} stdout", stderr=f"{step} stderr")
        if step == "demo_no_order_dry_run" and create_child_manifest:
            output_dir = no_order_output_dir_from_command(command)
            flags = no_order_flags()
            for flag in omit_child_flags or set():
                flags.pop(flag, None)
            flags.update(child_flag_overrides or {})
            write_json(
                output_dir / cycle.NO_ORDER_CHILD_MANIFEST,
                {
                    "decision_label": decision_label,
                    "dry_run_status": dry_run_status,
                    "feature_row_fresh": True,
                    "time_server": "2026-05-30 01:45:00",
                    "session_observed": "Off_hours",
                    "spread": 3.0,
                    "spread_within_gate": True,
                    "close_to_ma_fast_atr_20_bucket": "low_tercile",
                    "tick_volume_percentile_100_bucket": "low_tercile",
                    "skip_reason_count": 2 if decision_label == "would_skip" else 0,
                    "block_reason_count": 1 if decision_label == "would_block" else 0,
                    **flags,
                },
            )
        return SimpleNamespace(returncode=0, stdout=f"{step} stdout tail", stderr=f"{step} stderr tail")

    return fake_run


def write_refresh_db(db_path: Path, *, bar_time: str = "", feature_time: str = "") -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS price_bars (symbol TEXT, timeframe TEXT, time_server TEXT)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS price_features (symbol TEXT, timeframe TEXT, time_server TEXT)"
        )
        connection.execute("DELETE FROM price_bars")
        connection.execute("DELETE FROM price_features")
        if bar_time:
            connection.execute(
                "INSERT INTO price_bars (symbol, timeframe, time_server) VALUES (?, ?, ?)",
                ("GBPUSD", "M15", bar_time),
            )
        if feature_time:
            connection.execute(
                "INSERT INTO price_features (symbol, timeframe, time_server) VALUES (?, ?, ?)",
                ("GBPUSD", "M15", feature_time),
            )
        connection.commit()


def insert_refresh_row(db_path: Path, table_name: str, time_server: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f"INSERT INTO {table_name} (symbol, timeframe, time_server) VALUES (?, ?, ?)",
            ("GBPUSD", "M15", time_server),
        )
        connection.commit()


def mocked_time_basis(*, latest_bar: str, spread: float = 3.0) -> dict[str, object]:
    return {
        "mt5_time_basis_status": "mt5_alignment_checked",
        "mt5_time_basis_unavailable_reason": "",
        "mt5_alignment_checked": True,
        "time_server_source": "raw_broker_server_time_or_existing_db_time_server",
        "import_time_basis": "mt5_broker_server_time_when_available",
        "pc_utc_now": "2026-06-11T18:30:00+00:00",
        "mt5_tick_time_server": "2026-06-11 21:28:48",
        "latest_mt5_closed_bar_time_server": latest_bar,
        "mt5_server_time_offset_seconds_vs_pc_utc": 10799,
        "mt5_time_basis_caveat": "mocked_unit_test",
        "current_broker_spread_points": spread,
        "current_broker_spread_source": "symbol_info.spread",
        "current_broker_spread_within_policy": spread <= 15.0,
        "current_broker_spread_policy_max_points": 15.0,
        "live_spread_gate_status": "live_spread_within_policy" if spread <= 15.0 else "blocked_current_spread_above_policy",
    }


def fake_refresh_subprocess_run(
    *,
    db_path: Path,
    imported_bar_time: str,
    generated_feature_time: str,
    decision_label: str = "would_signal",
    dry_run_status: str = "demo_no_order_dry_run_would_signal",
    live_alignment_status: str = "live_data_aligned_with_mt5_latest_bar",
    live_spread_gate_status: str = "live_spread_within_policy",
    current_spread: object = 3.0,
    executed: list[list[str]] | None = None,
) -> object:
    seen = executed if executed is not None else []

    def fake_run(command: list[str], **kwargs: object) -> object:
        assert kwargs.get("shell") is False
        assert isinstance(command, list)
        seen.append(command)
        step = child_step_from_command(command)
        if step == "import_price_bars":
            insert_refresh_row(db_path, "price_bars", imported_bar_time)
            return SimpleNamespace(returncode=0, stdout="Price bars import complete.\nRows inserted: 5\n", stderr="")
        if step == "generate_price_features":
            insert_refresh_row(db_path, "price_features", generated_feature_time)
            return SimpleNamespace(returncode=0, stdout="Price feature generation complete.\nRows generated: 999\n", stderr="")
        if step == "demo_no_order_dry_run":
            output_dir = no_order_output_dir_from_command(command)
            spread_from_command = command[command.index("--current-broker-spread-points") + 1]
            spread_value = float(spread_from_command) if current_spread == "from_command" else float(current_spread)
            write_json(
                output_dir / cycle.NO_ORDER_CHILD_MANIFEST,
                {
                    "decision_label": decision_label,
                    "dry_run_status": dry_run_status,
                    "feature_row_fresh": True,
                    "time_server": generated_feature_time,
                    "evaluated_feature_time_server": generated_feature_time,
                    "latest_db_price_bar_time_server": imported_bar_time,
                    "latest_db_feature_time_server": generated_feature_time,
                    "latest_mt5_closed_bar_time_server": "2026-06-11 21:15:00",
                    "db_lag_bars_vs_mt5_latest_closed_bar": 0.0 if live_alignment_status == "live_data_aligned_with_mt5_latest_bar" else 5.0,
                    "db_lag_minutes_vs_mt5_latest_closed_bar": 0.0 if live_alignment_status == "live_data_aligned_with_mt5_latest_bar" else 75.0,
                    "live_alignment_status": live_alignment_status,
                    "session_observed": "Off_hours",
                    "spread": 0.0,
                    "feature_row_spread_broker_points": 0.0,
                    "feature_row_spread_source": "db_candle_spread",
                    "spread_source": "db_candle_spread",
                    "spread_within_gate": True,
                    "current_broker_spread_points": spread_value,
                    "current_broker_spread_source": "symbol_info.spread",
                    "current_broker_spread_within_policy": spread_value <= 15.0,
                    "current_broker_spread_policy_max_points": 15.0,
                    "live_spread_gate_status": live_spread_gate_status,
                    "close_to_ma_fast_atr_20_bucket": "high_tercile",
                    "tick_volume_percentile_100_bucket": "mid_tercile",
                    "skip_reason_count": 0,
                    "block_reason_count": 1 if decision_label == "would_block" else 0,
                    **no_order_flags(),
                },
            )
        return SimpleNamespace(returncode=0, stdout=f"{step} stdout tail", stderr="")

    return fake_run


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        cycle.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


class FakeMT5:
    TIMEFRAME_M15 = object()

    def __init__(self, *, tick_time: int | None, bar_time: int | None, spread: object = 3, point: float = 0.00001) -> None:
        self.tick_time = tick_time
        self.bar_time = bar_time
        self.spread = spread
        self.point = point
        self.calls: list[tuple[object, ...]] = []

    def symbol_info(self, symbol: str) -> dict[str, object]:
        self.calls.append(("symbol_info", symbol))
        return {"spread": self.spread, "point": self.point}

    def symbol_info_tick(self, symbol: str) -> dict[str, object] | None:
        self.calls.append(("symbol_info_tick", symbol))
        return None if self.tick_time is None else {"time": self.tick_time, "bid": 1.25, "ask": 1.25003}

    def copy_rates_from_pos(self, symbol: str, timeframe: object, start_pos: int, count: int) -> list[dict[str, object]] | None:
        self.calls.append(("copy_rates_from_pos", symbol, timeframe, start_pos, count))
        return None if self.bar_time is None else [{"time": self.bar_time, "spread": 3}]


def epoch(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc).timestamp())


def test_collect_mt5_time_basis_uses_mocked_tick_and_closed_bar_without_hardcoded_offset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths)
    fake = FakeMT5(
        tick_time=epoch(2026, 6, 11, 1, 28, 48),
        bar_time=epoch(2026, 6, 11, 1, 15),
    )
    monkeypatch.setattr(cycle, "utc_now", lambda: datetime(2026, 6, 10, 22, 28, 49, tzinfo=timezone.utc))

    evidence = cycle.collect_mt5_time_basis(args, mt5_module=fake)

    assert evidence["mt5_time_basis_status"] == "mt5_alignment_checked"
    assert evidence["pc_utc_now"] == "2026-06-10T22:28:49+00:00"
    assert evidence["mt5_tick_time_server"] == "2026-06-11 01:28:48"
    assert evidence["latest_mt5_closed_bar_time_server"] == "2026-06-11 01:15:00"
    assert evidence["mt5_server_time_offset_seconds_vs_pc_utc"] == 10799
    assert evidence["current_broker_spread_points"] == 3.0
    assert evidence["current_broker_spread_source"] == "symbol_info.spread"
    assert evidence["current_broker_spread_within_policy"] is True
    assert evidence["live_spread_gate_status"] == "live_spread_within_policy"
    assert ("symbol_info", "GBPUSD") in fake.calls
    assert ("copy_rates_from_pos", "GBPUSD", fake.TIMEFRAME_M15, 1, 1) in fake.calls


def test_collect_mt5_time_basis_reports_unavailable_when_latest_bar_missing(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths)
    evidence = cycle.collect_mt5_time_basis(args, mt5_module=FakeMT5(tick_time=epoch(2026, 6, 11, 1, 28, 48), bar_time=None))

    assert evidence["mt5_time_basis_status"] == "live_data_mt5_time_basis_unavailable"
    assert evidence["latest_mt5_closed_bar_time_server"] == ""
    assert evidence["mt5_alignment_checked"] is False


def test_collect_mt5_time_basis_uses_tick_spread_fallback_when_symbol_spread_missing(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths)
    fake = FakeMT5(
        tick_time=epoch(2026, 6, 11, 1, 28, 48),
        bar_time=epoch(2026, 6, 11, 1, 15),
        spread=None,
    )

    evidence = cycle.collect_mt5_time_basis(args, mt5_module=fake)

    assert evidence["mt5_time_basis_status"] == "mt5_alignment_checked"
    assert evidence["current_broker_spread_points"] == pytest.approx(3.0)
    assert evidence["current_broker_spread_source"] == "tick_ask_bid_div_point"
    assert evidence["current_broker_spread_within_policy"] is True


def test_run_cycle_computes_effective_import_to_date_from_latest_mt5_closed_bar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths)
    write_refresh_db(Path(args.feature_source_db), bar_time="2026-06-11 20:00:00", feature_time="2026-06-11 20:00:00")
    executed: list[list[str]] = []
    monkeypatch.setattr(cycle, "collect_mt5_time_basis", lambda _args: mocked_time_basis(latest_bar="2026-06-11 21:15:00"))
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_refresh_subprocess_run(
            db_path=Path(args.feature_source_db),
            imported_bar_time="2026-06-11 21:15:00",
            generated_feature_time="2026-06-11 21:15:00",
            executed=executed,
        ),
    )

    outputs = cycle.build_outputs(args)
    manifest = read_json(outputs["manifest"])
    import_command = next(command for command in executed if child_step_from_command(command) == "import_price_bars")

    assert import_command[import_command.index("--from-date") + 1] == "2026-06-11T18:00:00Z"
    assert import_command[import_command.index("--to-date") + 1] == "2026-06-11T21:16:00Z"
    assert manifest["effective_import_to_date"] == "2026-06-11T21:16:00Z"
    assert manifest["effective_import_to_date_source"] == "latest_mt5_closed_bar_time_server"
    assert manifest["cycle_status"] == "demo_no_order_cycle_completed_would_signal"


def test_stale_db_imports_generates_and_aligns_to_latest_mt5_closed_bar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths)
    write_refresh_db(Path(args.feature_source_db), bar_time="2026-06-11 20:00:00", feature_time="2026-06-11 20:00:00")
    monkeypatch.setattr(cycle, "collect_mt5_time_basis", lambda _args: mocked_time_basis(latest_bar="2026-06-11 21:15:00"))
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_refresh_subprocess_run(
            db_path=Path(args.feature_source_db),
            imported_bar_time="2026-06-11 21:15:00",
            generated_feature_time="2026-06-11 21:15:00",
        ),
    )

    outputs = cycle.build_outputs(args)
    manifest = read_json(outputs["manifest"])

    assert manifest["db_refresh_before_shadow_enabled"] is True
    assert manifest["mt5_time_basis_checked"] is True
    assert manifest["latest_db_price_bar_time_server_before_import"] == "2026-06-11 20:00:00"
    assert manifest["latest_db_feature_time_server_before_generation"] == "2026-06-11 20:00:00"
    assert manifest["latest_db_price_bar_time_server_after_import"] == "2026-06-11 21:15:00"
    assert manifest["latest_db_feature_time_server_after_generation"] == "2026-06-11 21:15:00"
    assert manifest["db_lag_bars_vs_mt5_latest_closed_bar"] == 0.0
    assert manifest["live_alignment_status"] == "live_data_aligned_with_mt5_latest_bar"
    assert manifest["imported_rows_count"] == 5
    assert manifest["generated_features_count"] == 999


def test_db_remaining_stale_after_refresh_blocks_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths)
    write_refresh_db(Path(args.feature_source_db), bar_time="2026-06-11 20:00:00", feature_time="2026-06-11 20:00:00")
    monkeypatch.setattr(cycle, "collect_mt5_time_basis", lambda _args: mocked_time_basis(latest_bar="2026-06-11 21:15:00"))
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_refresh_subprocess_run(
            db_path=Path(args.feature_source_db),
            imported_bar_time="2026-06-11 20:00:00",
            generated_feature_time="2026-06-11 20:00:00",
            decision_label="would_signal",
            dry_run_status="demo_no_order_dry_run_would_signal",
            live_alignment_status="live_data_blocked_db_lagging_mt5_latest_bar",
        ),
    )

    outputs = cycle.build_outputs(args)
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "demo_no_order_cycle_completed_would_block"
    assert manifest["live_alignment_status"] == "live_data_blocked_db_lagging_mt5_latest_bar"
    assert manifest["db_lag_bars_vs_mt5_latest_closed_bar"] == 5.0
    assert manifest["recommended_next_step"] == "fix_demo_no_order_cycle_blocker"


def test_mt5_basis_unavailable_does_not_fake_alignment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths)
    write_refresh_db(Path(args.feature_source_db), bar_time="2026-06-11 20:00:00", feature_time="2026-06-11 20:00:00")
    monkeypatch.setattr(cycle, "collect_mt5_time_basis", lambda _args: cycle.mt5_time_basis_unavailable("mocked_unavailable"))
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run(decision_label="would_block", dry_run_status="demo_no_order_dry_run_would_block"))

    outputs = cycle.build_outputs(args)
    manifest = read_json(outputs["manifest"])

    assert manifest["mt5_time_basis_checked"] is False
    assert manifest["latest_mt5_closed_bar_time_server"] == ""
    assert manifest["effective_import_to_date_source"] == "explicit_cli_to_date"
    assert manifest["live_alignment_status"] == "live_data_mt5_time_basis_unavailable"


def test_current_live_spread_gate_still_blocks_high_spread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths)
    write_refresh_db(Path(args.feature_source_db), bar_time="2026-06-11 21:00:00", feature_time="2026-06-11 21:00:00")
    monkeypatch.setattr(cycle, "collect_mt5_time_basis", lambda _args: mocked_time_basis(latest_bar="2026-06-11 21:15:00", spread=16.0))
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_refresh_subprocess_run(
            db_path=Path(args.feature_source_db),
            imported_bar_time="2026-06-11 21:15:00",
            generated_feature_time="2026-06-11 21:15:00",
            decision_label="would_block",
            dry_run_status="demo_no_order_dry_run_would_block",
            live_spread_gate_status="blocked_current_spread_above_policy",
            current_spread=16.0,
        ),
    )

    outputs = cycle.build_outputs(args)
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "demo_no_order_cycle_completed_would_block"
    assert manifest["child_live_spread_gate_status"] == "blocked_current_spread_above_policy"
    assert manifest["recommended_next_step"] == "wait_for_current_spread_within_policy_and_rerun_live_shadow"


def test_current_live_spread_gate_passes_within_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths)
    write_refresh_db(Path(args.feature_source_db), bar_time="2026-06-11 21:00:00", feature_time="2026-06-11 21:00:00")
    monkeypatch.setattr(cycle, "collect_mt5_time_basis", lambda _args: mocked_time_basis(latest_bar="2026-06-11 21:15:00", spread=3.0))
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_refresh_subprocess_run(
            db_path=Path(args.feature_source_db),
            imported_bar_time="2026-06-11 21:15:00",
            generated_feature_time="2026-06-11 21:15:00",
            current_spread=3.0,
        ),
    )

    outputs = cycle.build_outputs(args)
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "demo_no_order_cycle_completed_would_signal"
    assert manifest["current_broker_spread_points"] == 3.0
    assert manifest["child_live_spread_gate_status"] == "live_spread_within_policy"


def test_zero_current_spread_propagates_from_cycle_to_child_dry_run_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths)
    write_refresh_db(Path(args.feature_source_db), bar_time="2026-06-11 21:00:00", feature_time="2026-06-11 21:00:00")
    monkeypatch.setattr(cycle, "collect_mt5_time_basis", lambda _args: mocked_time_basis(latest_bar="2026-06-11 21:15:00", spread=0.0))
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_refresh_subprocess_run(
            db_path=Path(args.feature_source_db),
            imported_bar_time="2026-06-11 21:15:00",
            generated_feature_time="2026-06-11 21:15:00",
            current_spread="from_command",
        ),
    )

    outputs = cycle.build_outputs(args)
    manifest = read_json(outputs["manifest"])
    child_manifest = read_json(Path(manifest["latest_child_manifest_path"]))

    assert manifest["current_broker_spread_points"] == 0.0
    assert manifest["child_current_broker_spread_points"] == 0.0
    assert child_manifest["current_broker_spread_points"] == 0.0
    assert child_manifest["current_broker_spread_within_policy"] is True
    assert child_manifest["live_spread_gate_status"] == "live_spread_within_policy"


def test_dry_run_writes_planned_commands_and_executes_no_children(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("children should not execute in dry-run")

    monkeypatch.setattr(subprocess, "run", fail_if_called)
    outputs = cycle.build_outputs(make_args(tmp_path, paths, dry_run=True))
    manifest = read_json(outputs["manifest"])
    commands = read_csv(outputs["child_commands"])

    assert manifest["cycle_status"] == "demo_no_order_cycle_plan_only"
    assert manifest["child_command_count"] == 3
    assert manifest["child_success_count"] == 0
    assert len(commands) == 3
    assert all(row["planned_only"] == "true" for row in commands)


def test_child_success_would_skip_completes_would_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run(decision_label="would_skip", dry_run_status="demo_no_order_dry_run_would_skip"))
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "demo_no_order_cycle_completed_would_skip"
    assert manifest["child_decision_label"] == "would_skip"
    assert manifest["recommended_next_step"] == "monitor_next_feature_row_or_schedule_cycle"
    assert manifest["spread_unit"] == "broker_points"
    assert manifest["max_spread_points"] == 15.0
    assert manifest["spread_policy_matches_canonical"] is True
    assert manifest["missing_no_order_flag_count"] == 0
    assert manifest["unsafe_no_order_flag_count"] == 0
    assert manifest["no_order_boundary_confirmed"] is True


def test_child_manifest_missing_required_no_order_flag_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    missing_flag = "no_order_send_called"
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run(omit_child_flags={missing_flag}))
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])
    report = outputs["report"].read_text(encoding="utf-8")

    assert manifest["cycle_status"] == "blocked_no_order_boundary_violation"
    assert manifest["missing_no_order_flag_count"] == 1
    assert manifest["unsafe_no_order_flag_count"] == 0
    assert manifest["no_order_boundary_confirmed"] is False
    assert any(row["warning_code"] == "missing_no_order_boundary_flag" for row in warnings)
    assert f"child_manifest:{missing_flag}" in report


def test_child_manifest_unsafe_no_order_flag_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    unsafe_flag = "no_order_check_called"
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run(child_flag_overrides={unsafe_flag: False}))
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])
    report = outputs["report"].read_text(encoding="utf-8")

    assert manifest["cycle_status"] == "blocked_no_order_boundary_violation"
    assert manifest["missing_no_order_flag_count"] == 0
    assert manifest["unsafe_no_order_flag_count"] == 1
    assert manifest["no_order_boundary_confirmed"] is False
    assert any(row["warning_code"] == "unsafe_no_order_boundary_flag" for row in warnings)
    assert f"child_manifest:{unsafe_flag}=False" in report


def test_child_success_would_signal_recommends_signal_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run(decision_label="would_signal", dry_run_status="demo_no_order_dry_run_would_signal"))
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "demo_no_order_cycle_completed_would_signal"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_demo_would_signal_review"


def test_child_success_would_block_completes_would_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run(decision_label="would_block", dry_run_status="demo_no_order_dry_run_would_block"))
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "demo_no_order_cycle_completed_would_block"


def test_failed_import_child_stops_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    executed: list[str] = []
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run(fail_step="import_price_bars", executed=executed))
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "blocked_child_command_failed"
    assert executed == ["import_price_bars"]


def test_failed_feature_generation_stops_before_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    executed: list[str] = []
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run(fail_step="generate_price_features", executed=executed))
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "blocked_child_command_failed"
    assert executed == ["import_price_bars", "generate_price_features"]


def test_missing_child_no_order_manifest_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run(create_child_manifest=False))
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "blocked_child_manifest_missing"


def test_config_boundary_unsafe_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, config_payload=demo_config(paper_only=False))
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "blocked_by_config_boundary"


def test_plan_status_blocked_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, plan_status="blocked_by_config_boundary")
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "blocked_by_plan_status"


def test_environment_check_blocked_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, env_status="blocked_mt5_initialize_failed")
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "blocked_by_environment_check_status"


def test_child_script_allowlist_blocks_unexpected_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patched = dict(cycle.CHILD_SCRIPT_PATHS)
    patched["import_price_bars"] = tmp_path / "scripts" / "paper_signal_logger_bad.py"
    monkeypatch.setattr(cycle, "CHILD_SCRIPT_PATHS", patched)
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_status"] == "blocked_child_command_failed"
    assert manifest["child_success_count"] == 0


def test_exact_repo_child_script_paths_are_allowlisted() -> None:
    for path in cycle.CHILD_SCRIPT_PATHS.values():
        assert cycle.is_allowed_child_script(path) is True


def test_same_child_filename_outside_repo_is_not_allowlisted(tmp_path: Path) -> None:
    outside = tmp_path / "scripts" / "import_price_bars.py"
    outside.parent.mkdir(parents=True)
    outside.write_text("print('outside')\n", encoding="utf-8")

    assert cycle.is_allowed_child_script(outside) is False


def test_path_traversal_child_script_attempt_is_not_allowlisted(tmp_path: Path) -> None:
    outside = tmp_path / "repo" / ".." / "scripts" / "run_fixed_candidate_demo_no_order_dry_run.py"

    assert cycle.is_allowed_child_script(outside) is False


def test_child_command_plan_uses_only_exact_allowed_scripts(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths, dry_run=True)
    commands = cycle.build_child_commands(args, tmp_path / "out", "2026-05-30T00:00:00Z", "2026-05-30T03:00:00Z")

    assert len(commands) == 3
    assert {Path(command["script"]).resolve() for command in commands} == cycle.ALLOWED_CHILD_SCRIPT_PATHS
    assert all(command["allowed_child_script"] is True for command in commands)


def test_child_no_order_command_uses_canonical_threshold_path_by_default(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    args = make_args(tmp_path, paths, dry_run=True, explicit_threshold=False)
    cycle.normalize_threshold_args(args)
    commands = cycle.build_child_commands(args, tmp_path / "out", "2026-05-30T00:00:00Z", "2026-05-30T03:00:00Z")
    no_order_command = next(command for command in commands if command["child_step"] == "demo_no_order_dry_run")["command"]

    assert no_order_command[no_order_command.index("--tercile-thresholds-json") + 1] == str(paths["thresholds"])


def test_commands_use_shell_false_and_list_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    seen: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        assert kwargs.get("shell") is False
        assert isinstance(command, list)
        seen.append(command)
        step = child_step_from_command(command)
        if step == "demo_no_order_dry_run":
            write_json(no_order_output_dir_from_command(command) / cycle.NO_ORDER_CHILD_MANIFEST, {"decision_label": "would_skip", **no_order_flags()})
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    cycle.build_outputs(make_args(tmp_path, paths))

    assert len(seen) == 3


def test_child_results_include_stdout_stderr_tails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run())
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    results = read_csv(outputs["child_results"])

    assert any("stdout tail" in row["stdout_tail"] for row in results)
    assert any("stderr tail" in row["stderr_tail"] for row in results)


def test_manifest_counts_match_child_command_and_results_csvs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run())
    outputs = cycle.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    commands = read_csv(outputs["child_commands"])
    results = read_csv(outputs["child_results"])

    assert manifest["child_command_count"] == len(commands)
    assert manifest["child_success_count"] == sum(1 for row in results if row["child_status"] == "success")
    assert manifest["child_failure_count"] == sum(1 for row in results if row["child_status"] == "failed")


def test_report_includes_no_order_request_calc_and_approval_caveats(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = cycle.build_outputs(make_args(tmp_path, paths, dry_run=True))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No broker order execution was performed." in report
    assert "No order request was constructed." in report
    assert "No order_check or order_calc call was performed." in report
    assert "This cycle is not demo broker approval." in report


def test_static_source_has_no_forbidden_order_function_calls() -> None:
    source = Path(cycle.__file__).read_text(encoding="utf-8")
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


def test_no_replay_cost_holdout_or_paper_workflow_child_scripts_are_allowlisted() -> None:
    for path in cycle.ALLOWED_CHILD_SCRIPT_PATHS:
        lowered = str(path).lower()
        assert "paper_signal_logger" not in lowered
        assert "paper_trade_tracker" not in lowered
        assert "local_paper_cycle" not in lowered
        assert "replay" not in lowered
        assert "backtest" not in lowered
        assert "cost" not in lowered
        assert "holdout" not in lowered


def test_no_heavy_commands_are_executed_in_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("subprocess should not run in dry-run")

    monkeypatch.setattr(subprocess, "run", fail_if_called)
    cycle.build_outputs(make_args(tmp_path, paths, dry_run=True))
