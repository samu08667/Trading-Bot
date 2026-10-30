from __future__ import annotations

import csv
import importlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_fixed_candidate_demo_environment as check


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
        "logging": {"required_fields": ["timestamp", "symbol", "timeframe", "signal_state", "kill_switch_state"]},
    }
    config.update(overrides)
    return config


def plan_manifest(plan_status: str = "demo_environment_check_plan_available_with_caveats") -> dict[str, object]:
    return {
        "run_id": "fixture_environment_plan",
        "plan_status": plan_status,
        "recommended_next_step": "implement_check_fixed_candidate_demo_environment",
        "requirement_row_count": 18,
        "future_artifact_row_count": 8,
        "blocking_requirement_count": 18,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_feature_refresh_performed": True,
        "no_trading_decision_performed": True,
    }


def requirement_rows() -> list[dict[str, object]]:
    areas = [
        "account_mode_check",
        "terminal_connection_check",
        "symbol_visibility_check",
        "symbol_contract_check",
        "symbol_contract_check",
        "symbol_contract_check",
        "symbol_contract_check",
        "spread_unit_check",
        "risk_sizing_check",
        "one_open_trade_state_check",
        "duplicate_protection_check",
        "sl_tp_attachment_check",
        "timeout_h10_handling_check",
        "broker_state_reconciliation_check",
        "crash_restart_recovery_check",
        "kill_switch_check",
        "audit_logging_check",
        "dry_run_no_order_check",
    ]
    return [
        {
            "run_id": "fixture_environment_plan",
            "requirement_area": area,
            "requirement_name": f"{area} requirement",
            "required_fields": "[]",
            "expected_condition": "future read-only/no-order evidence",
            "blocking_if_failed": True,
            "future_artifact": "future.csv",
            "future_checker_script": "scripts/check_fixed_candidate_demo_environment.py",
            "check_mode": "future_read_only_no_order_check",
            "caveat": "fixture",
        }
        for area in areas
    ]


def future_artifact_rows() -> list[dict[str, object]]:
    return [
        {
            "run_id": "fixture_environment_plan",
            "future_artifact_name": name,
            "future_artifact_role": "fixture",
            "produced_by_future_script": "scripts/check_fixed_candidate_demo_environment.py",
            "required_before": "manual review",
            "blocking_if_missing": True,
            "caveat": "fixture",
        }
        for name in [
            check.OUTPUT_MANIFEST,
            check.OUTPUT_REPORT,
            check.OUTPUT_CHECKLIST,
            check.OUTPUT_WARNINGS,
            check.OUTPUT_REQUIREMENTS,
            check.OUTPUT_ACCOUNT_SNAPSHOT,
            check.OUTPUT_SYMBOL_SNAPSHOT,
            check.OUTPUT_NO_ORDER,
        ]
    ]


def write_fixture_sources(
    tmp_path: Path,
    *,
    config_payload: dict[str, object] | None = None,
    plan_status: str = "demo_environment_check_plan_available_with_caveats",
    missing_plan_manifest: bool = False,
) -> dict[str, Path]:
    config_path = tmp_path / "config" / "demo_config.json"
    write_json(config_path, config_payload if config_payload is not None else demo_config())
    plan_dir = tmp_path / "environment_plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    if not missing_plan_manifest:
        write_json(plan_dir / check.PLAN_MANIFEST, plan_manifest(plan_status))
    (plan_dir / check.PLAN_REPORT).write_text("# Environment plan\n", encoding="utf-8")
    write_csv(plan_dir / check.PLAN_REQUIREMENTS, [
        "run_id",
        "requirement_area",
        "requirement_name",
        "required_fields",
        "expected_condition",
        "blocking_if_failed",
        "future_artifact",
        "future_checker_script",
        "check_mode",
        "caveat",
    ], requirement_rows())
    write_csv(plan_dir / check.PLAN_FUTURE_ARTIFACTS, [
        "run_id",
        "future_artifact_name",
        "future_artifact_role",
        "produced_by_future_script",
        "required_before",
        "blocking_if_missing",
        "caveat",
    ], future_artifact_rows())
    write_csv(plan_dir / check.PLAN_WARNINGS, check.WARNING_FIELDNAMES, [])
    return {"config": config_path, "plan": plan_dir}


def make_args(tmp_path: Path, paths: dict[str, Path], *, dry_run: bool = False, allow_broker_read: bool = True) -> object:
    args = [
        "--run-id",
        "unit_demo_environment_check",
        "--demo-environment-check-plan-dir",
        str(paths["plan"]),
        "--demo-strategy-config",
        str(paths["config"]),
        "--symbol",
        "GBPUSD",
        "--timeframe",
        "M15",
        "--mt5-package",
        "FakeMT5",
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    if dry_run:
        args.append("--dry-run")
    if allow_broker_read:
        args.append("--allow-broker-read")
    return check.build_parser().parse_args(args)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(
        self,
        *,
        initialize_success: bool = True,
        trade_mode: int = 0,
        symbol_info: object | None = None,
        spread: int = 2,
    ) -> None:
        self.initialize_success = initialize_success
        self.trade_mode = trade_mode
        self._symbol_info = symbol_info
        self.spread = spread
        self.shutdown_called = False

    def initialize(self) -> bool:
        return self.initialize_success

    def shutdown(self) -> None:
        self.shutdown_called = True

    def terminal_info(self) -> object:
        return SimpleNamespace(connected=True, trade_allowed=True, name="Terminal")

    def account_info(self) -> object:
        return SimpleNamespace(
            login=123456789,
            server="Sensitive-Demo-Server",
            name="Sensitive Name",
            company="Sensitive Company",
            trade_mode=self.trade_mode,
            leverage=100,
            currency="USD",
            balance=10000.0,
            equity=10000.0,
            margin_mode=2,
            trade_allowed=True,
            trade_expert=True,
        )

    def symbol_info(self, _symbol: str) -> object | None:
        if self._symbol_info == "missing":
            return None
        if self._symbol_info is not None:
            return self._symbol_info
        return SimpleNamespace(
            name="GBPUSD",
            visible=True,
            select=True,
            trade_mode=4,
            trade_contract_size=100000.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            point=0.00001,
            digits=5,
            trade_tick_size=0.00001,
            trade_tick_value=1.0,
            trade_stops_level=10,
            trade_freeze_level=0,
            spread=self.spread,
            spread_float=True,
            currency_base="GBP",
            currency_profit="USD",
            currency_margin="GBP",
        )

    def symbol_info_tick(self, _symbol: str) -> object:
        return SimpleNamespace(bid=1.25001, ask=1.25003, time=1770000000)


def patch_mt5(monkeypatch: pytest.MonkeyPatch, fake: object) -> None:
    def fake_import(name: str) -> object:
        assert name == "FakeMT5"
        return fake

    monkeypatch.setattr(importlib, "import_module", fake_import)


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        check.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_default_environment_check_plan_path_references_spread15() -> None:
    args = check.build_parser().parse_args([])

    assert "demo_environment_check_plan_spread15_v1" in str(args.demo_environment_check_plan_dir)


def test_dry_run_writes_all_artifacts_and_does_not_import_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_import(_name: str) -> object:
        raise AssertionError("MT5 should not be imported in dry-run")

    monkeypatch.setattr(importlib, "import_module", fail_import)
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "demo_environment_check_dry_run_no_broker_read"
    assert manifest["mt5_import_attempted"] is False
    assert manifest["allow_broker_read"] is True
    assert manifest["broker_read_performed"] is False
    assert manifest["mt5_import_performed"] is False
    assert manifest["mt5_connection_performed"] is False
    for key in ["manifest", "report", "checklist", "warnings", "requirements", "account_snapshot", "symbol_snapshot", "no_order"]:
        assert outputs[key].exists()


def test_default_without_allow_broker_read_does_not_import_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_import(_name: str) -> object:
        raise AssertionError("MT5 should not be imported without --allow-broker-read")

    monkeypatch.setattr(importlib, "import_module", fail_import)
    outputs = check.build_outputs(make_args(tmp_path, paths, allow_broker_read=False))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "demo_environment_check_dry_run_no_broker_read"
    assert manifest["allow_broker_read"] is False
    assert manifest["dry_run"] is True
    assert manifest["broker_read_performed"] is False
    assert manifest["mt5_import_performed"] is False


def test_valid_fake_demo_mt5_returns_available_with_caveats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5())
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "environment_check_available_with_caveats"
    assert manifest["mt5_initialize_success"] is True
    assert manifest["is_demo_account"] is True


def test_missing_mt5_module_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def missing_import(_name: str) -> object:
        raise ImportError("missing")

    monkeypatch.setattr(importlib, "import_module", missing_import)
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "blocked_mt5_unavailable"


def test_initialize_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(initialize_success=False))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "blocked_mt5_initialize_failed"


def test_real_account_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(trade_mode=FakeMT5.ACCOUNT_TRADE_MODE_REAL))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "blocked_account_mode_not_demo"
    assert manifest["account_mode_label"] == "real"


def test_unknown_account_mode_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(trade_mode=99))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "blocked_account_mode_not_demo"
    assert manifest["account_mode_label"] == "unknown"


def test_missing_symbol_info_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(symbol_info="missing"))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "blocked_missing_symbol_info"


def test_spread_six_passes_under_broker_point_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(spread=6))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "environment_check_available_with_caveats"
    assert manifest["spread_within_config_gate"] is True
    assert manifest["max_spread_points"] == 15.0
    assert manifest["spread_unit"] == "broker_points"


def test_spread_above_threshold_creates_warning_without_orders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(spread=20))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["environment_check_status"] == "environment_check_failed_blocking_requirements"
    assert manifest["spread_within_config_gate"] is False
    assert any(row["warning_code"] == "spread_above_config_threshold" for row in warnings)
    assert manifest["no_order_execution_performed"] is True


def test_account_snapshot_is_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5())
    outputs = check.build_outputs(make_args(tmp_path, paths))
    account_snapshot = read_json(outputs["account_snapshot"])

    assert account_snapshot["redaction_applied"] is True
    assert "login" not in account_snapshot
    assert "server" not in account_snapshot
    assert "name" not in account_snapshot
    assert "company" not in account_snapshot


def test_symbol_contract_snapshot_includes_required_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5())
    outputs = check.build_outputs(make_args(tmp_path, paths))
    symbol_snapshot = read_json(outputs["symbol_snapshot"])

    for field in [
        "symbol",
        "visible",
        "select",
        "trade_mode",
        "volume_min",
        "volume_max",
        "volume_step",
        "point",
        "digits",
        "trade_tick_size",
        "trade_tick_value",
        "trade_stops_level",
        "trade_freeze_level",
        "spread",
        "bid",
        "ask",
    ]:
        assert field in symbol_snapshot


def test_dry_run_no_order_artifact_confirms_no_disallowed_order_functions(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    rows = read_csv(outputs["no_order"])

    assert rows[0]["no_order_execution_performed"] == "true"
    assert rows[0]["no_order_request_constructed"] == "true"
    assert rows[0]["mt5_order_send_used"] == "false"
    assert rows[0]["mt5_order_check_used"] == "false"
    assert rows[0]["mt5_order_calc_margin_used"] == "false"
    assert rows[0]["mt5_order_calc_profit_used"] == "false"


def test_unsafe_config_boundary_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, config_payload=demo_config(paper_only=False))
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "blocked_by_config_boundary"


def test_missing_plan_manifest_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, missing_plan_manifest=True)
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "blocked_by_plan_status"


def test_blocked_plan_status_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, plan_status="blocked_by_config_boundary")
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["environment_check_status"] == "blocked_by_plan_status"


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5())
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    checklist = read_csv(outputs["checklist"])
    requirements = read_csv(outputs["requirements"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["checklist_row_count"] == len(checklist)
    assert manifest["requirement_row_count"] == len(requirements)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(
        1 for warning in warnings if warning["blocking_warning"].lower() == "true"
    )


def test_report_includes_no_order_request_db_and_approval_caveats(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No order execution was performed." in report
    assert "No order request was constructed." in report
    assert "No database mutation was performed." in report
    assert "This check is not demo broker approval." in report


def test_static_source_does_not_use_forbidden_mt5_functions() -> None:
    source = Path(check.__file__).read_text(encoding="utf-8")
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


def test_no_db_queries_are_performed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("DB query should not be performed")

    monkeypatch.setattr(sqlite3, "connect", fail_if_called)
    check.build_outputs(make_args(tmp_path, paths, dry_run=True))


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    check.build_outputs(make_args(tmp_path, paths, dry_run=True))
