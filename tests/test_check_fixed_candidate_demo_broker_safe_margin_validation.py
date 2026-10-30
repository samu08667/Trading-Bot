from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_fixed_candidate_demo_broker_safe_margin_validation as check


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def canonical_registry(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
    }
    data.update(overrides)
    return data


def execution_policy(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "account_currency": "EUR",
        "intended_demo_equity": 1000.0,
        "risk_percent_max": 0.5,
        "risk_amount_max": 5.0,
        "max_margin_usage_warning_ratio": 0.5,
        "max_margin_usage_ratio": 0.7,
        "max_margin_usage_amount": 700.0,
        "safety_boundaries": {
            "real_money_allowed": False,
            "order_execution_allowed": False,
            "order_request_construction_allowed": False,
            "order_check_allowed": False,
            "order_calc_allowed": False,
            "manual_approval_required_before_any_future_demo_order": True,
        },
    }
    data.update(overrides)
    return data


def plan_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "plan_status": "broker_safe_margin_validation_plan_available",
        "source_nature": "live_data_shadow_signal",
        "future_order_calc_margin_allowed_only_in_separate_module": True,
        "future_order_send_allowed": False,
        "future_order_check_allowed": False,
        "future_order_calc_profit_allowed": False,
        "future_positions_orders_history_allowed": False,
    }
    data.update(overrides)
    return data


def risk_volume_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "plan_status": "risk_volume_shadow_plan_available_no_order",
        "source_nature": "live_data_shadow_signal",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "demo_equity": 1000.0,
        "risk_percent": 0.5,
        "risk_amount": 5.0,
        "entry_reference_price": 1.25,
        "stepped_volume_lots": 0.13,
        "volume_preview_status": "shadow_volume_preview_available_not_broker_validated",
        "plan_actionable": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "demo_broker_approval_performed": False,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_trading_decision_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_db_query_performed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
    }
    data.update(overrides)
    return data


def margin_feasibility_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "plan_status": "margin_feasibility_plan_available_no_order",
        "source_nature": "live_data_shadow_signal",
        "approximate_margin_usage_ratio": 0.58,
        "estimated_margin_quote": 583.0,
        "max_margin_usage_ratio": 0.7,
        "margin_estimate_static_artifact_only": True,
        "plan_actionable": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "demo_broker_approval_performed": False,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_demo_broker_approval_performed": True,
        "no_trading_decision_performed": True,
        "no_mt5_connection_performed": True,
        "no_broker_connection_performed": True,
        "no_account_query_performed": True,
        "no_symbol_query_performed": True,
        "no_db_query_performed": True,
        "no_db_mutation_performed": True,
        "no_child_scripts_executed": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
    }
    data.update(overrides)
    return data


def write_sources(
    tmp_path: Path,
    *,
    plan_data: dict[str, object] | None = None,
    risk_data: dict[str, object] | None = None,
    margin_data: dict[str, object] | None = None,
    registry_data: dict[str, object] | None = None,
    policy_data: dict[str, object] | None = None,
    missing_risk: bool = False,
) -> dict[str, Path]:
    registry_path = write_json(tmp_path / "registry.json", registry_data or canonical_registry())
    policy_path = write_json(tmp_path / "policy.json", policy_data or execution_policy())
    plan_dir = tmp_path / "broker_safe_plan"
    risk_dir = tmp_path / "risk_volume"
    margin_dir = tmp_path / "margin_feasibility"
    write_json(plan_dir / check.PLAN_MANIFEST, plan_data or plan_manifest())
    if not missing_risk:
        write_json(risk_dir / check.RISK_VOLUME_MANIFEST, risk_data or risk_volume_manifest())
    write_json(margin_dir / check.MARGIN_FEASIBILITY_MANIFEST, margin_data or margin_feasibility_manifest())
    return {"registry": registry_path, "policy": policy_path, "plan": plan_dir, "risk": risk_dir, "margin": margin_dir}


def make_args(
    tmp_path: Path,
    paths: dict[str, Path],
    *,
    dry_run: bool = False,
    allow_broker_read: bool = True,
    allow_order_calc_margin: bool = True,
) -> object:
    argv = [
        "--run-id",
        "unit_broker_safe_margin_validation",
        "--broker-safe-margin-validation-plan-dir",
        str(paths["plan"]),
        "--risk-volume-shadow-plan-dir",
        str(paths["risk"]),
        "--margin-feasibility-plan-dir",
        str(paths["margin"]),
        "--canonical-registry",
        str(paths["registry"]),
        "--demo-execution-policy",
        str(paths["policy"]),
        "--symbol",
        "GBPUSD",
        "--direction",
        "short",
        "--mt5-package",
        "FakeMT5",
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    if dry_run:
        argv.append("--dry-run")
    if allow_broker_read:
        argv.append("--allow-broker-read")
    if allow_order_calc_margin:
        argv.append("--allow-order-calc-margin")
    return check.build_parser().parse_args(argv)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def __init__(
        self,
        *,
        initialize_success: bool = True,
        trade_mode: int = 0,
        currency: str = "EUR",
        equity: float = 1000.0,
        spread: int = 6,
        symbol_missing: bool = False,
        margin_result: float | None = 100.0,
    ) -> None:
        self.initialize_success = initialize_success
        self.trade_mode = trade_mode
        self.currency = currency
        self.equity = equity
        self.spread = spread
        self.symbol_missing = symbol_missing
        self.margin_result = margin_result
        self.shutdown_called = False
        self.margin_call_count = 0
        self.forbidden_called: list[str] = []

    def initialize(self) -> bool:
        return self.initialize_success

    def shutdown(self) -> None:
        self.shutdown_called = True

    def terminal_info(self) -> object:
        return SimpleNamespace(connected=True, trade_allowed=True)

    def account_info(self) -> object:
        return SimpleNamespace(
            login=123,
            server="Sensitive Demo Server",
            name="Sensitive Name",
            trade_mode=self.trade_mode,
            leverage=30,
            currency=self.currency,
            equity=self.equity,
            margin_free=900.0,
            trade_allowed=True,
            trade_expert=True,
        )

    def symbol_info(self, _symbol: str) -> object | None:
        if self.symbol_missing:
            return None
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
            trade_tick_value=0.85,
            trade_stops_level=0,
            trade_freeze_level=0,
            spread=self.spread,
        )

    def symbol_info_tick(self, _symbol: str) -> object:
        return SimpleNamespace(bid=1.25, ask=1.25006, time=1770000000)

    def order_calc_margin(self, side: int, symbol: str, volume: float, price: float) -> float | None:
        self.margin_call_count += 1
        assert side == self.ORDER_TYPE_SELL
        assert symbol == "GBPUSD"
        assert volume == pytest.approx(0.13)
        assert price == pytest.approx(1.25)
        return self.margin_result

    def order_send(self, *_args: object, **_kwargs: object) -> None:
        self.forbidden_called.append("order_send")
        raise AssertionError("order_send must not be called")

    def order_check(self, *_args: object, **_kwargs: object) -> None:
        self.forbidden_called.append("order_check")
        raise AssertionError("order_check must not be called")

    def order_calc_profit(self, *_args: object, **_kwargs: object) -> None:
        self.forbidden_called.append("order_calc_profit")
        raise AssertionError("order_calc_profit must not be called")

    def positions_get(self, *_args: object, **_kwargs: object) -> None:
        self.forbidden_called.append("positions_get")
        raise AssertionError("positions_get must not be called")

    def orders_get(self, *_args: object, **_kwargs: object) -> None:
        self.forbidden_called.append("orders_get")
        raise AssertionError("orders_get must not be called")

    def history_orders_get(self, *_args: object, **_kwargs: object) -> None:
        self.forbidden_called.append("history_orders_get")
        raise AssertionError("history_orders_get must not be called")

    def history_deals_get(self, *_args: object, **_kwargs: object) -> None:
        self.forbidden_called.append("history_deals_get")
        raise AssertionError("history_deals_get must not be called")


def patch_mt5(monkeypatch: pytest.MonkeyPatch, fake: object) -> None:
    def fake_import(name: str) -> object:
        assert name == "FakeMT5"
        return fake

    monkeypatch.setattr(importlib, "import_module", fake_import)


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        check.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_dry_run_writes_plan_only_artifacts_and_does_not_import_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)

    def fail_import(_name: str) -> object:
        raise AssertionError("MT5 should not be imported in dry-run")

    monkeypatch.setattr(importlib, "import_module", fail_import)
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "broker_read_dry_run_no_broker_read"
    assert manifest["order_calc_margin_called"] is False
    assert manifest["allow_broker_read"] is True
    assert manifest["allow_order_calc_margin"] is True
    assert manifest["broker_read_performed"] is False
    assert manifest["mt5_import_performed"] is False
    for path in outputs.values():
        assert path.exists()


def test_default_without_allow_flags_does_not_import_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)

    def fail_import(_name: str) -> object:
        raise AssertionError("MT5 should not be imported without --allow-broker-read")

    monkeypatch.setattr(importlib, "import_module", fail_import)
    outputs = check.build_outputs(make_args(tmp_path, paths, allow_broker_read=False, allow_order_calc_margin=False))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "broker_read_dry_run_no_broker_read"
    assert manifest["allow_broker_read"] is False
    assert manifest["allow_order_calc_margin"] is False
    assert manifest["dry_run"] is True
    assert manifest["broker_read_performed"] is False
    assert manifest["order_calc_margin_called"] is False
    assert manifest["order_calc_margin_call_count"] == 0


def test_allow_broker_read_without_order_calc_margin_blocks_before_margin_calc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = FakeMT5(margin_result=100.0)
    patch_mt5(monkeypatch, fake)
    outputs = check.build_outputs(make_args(tmp_path, paths, allow_broker_read=True, allow_order_calc_margin=False))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "broker_safe_margin_validation_blocked_missing_allow_order_calc_margin"
    assert manifest["allow_broker_read"] is True
    assert manifest["allow_order_calc_margin"] is False
    assert manifest["broker_read_performed"] is True
    assert manifest["order_calc_margin_called"] is False
    assert manifest["order_calc_margin_call_count"] == 0
    assert fake.margin_call_count == 0


def test_valid_fake_demo_account_margin_below_warning_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = FakeMT5(margin_result=100.0)
    patch_mt5(monkeypatch, fake)
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "broker_safe_margin_validation_available"
    assert manifest["broker_margin_usage_ratio"] == pytest.approx(0.1)
    assert fake.margin_call_count == 1


def test_margin_above_warning_below_cap_available_with_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = FakeMT5(margin_result=583.0)
    patch_mt5(monkeypatch, fake)
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["validation_status"] == "broker_safe_margin_validation_available_with_margin_warning"
    assert any(row["warning_code"] == "broker_margin_above_warning_threshold" for row in warnings)


def test_fixture_source_maps_to_fixture_only_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(
        tmp_path,
        plan_data=plan_manifest(plan_status="broker_safe_margin_validation_plan_fixture_only", source_nature="synthetic_fixture"),
        risk_data=risk_volume_manifest(plan_status="risk_volume_shadow_plan_fixture_only", source_nature="synthetic_fixture"),
        margin_data=margin_feasibility_manifest(plan_status="margin_feasibility_plan_fixture_only", source_nature="synthetic_fixture"),
    )
    fake = FakeMT5(margin_result=100.0)
    patch_mt5(monkeypatch, fake)
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "broker_safe_margin_validation_fixture_only"
    assert manifest["recommended_next_step"] == "wait_for_live_shadow_signal_or_continue_no_order_monitoring"


def test_margin_above_cap_produces_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(margin_result=800.0))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "broker_safe_margin_validation_hold_margin_above_policy_cap"


def test_margin_calc_none_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(margin_result=None))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "broker_safe_margin_validation_blocked_by_margin_calc_failure"


def test_non_demo_account_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(trade_mode=FakeMT5.ACCOUNT_TRADE_MODE_REAL))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "blocked_non_demo_account"


def test_currency_not_eur_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(currency="USD"))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "blocked_account_snapshot_invalid"


def test_spread_above_15_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(spread=20))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "blocked_spread_above_policy"


def test_symbol_unavailable_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(symbol_missing=True))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "blocked_symbol_unavailable"


def test_mt5_import_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)

    def missing_import(_name: str) -> object:
        raise ImportError("missing")

    monkeypatch.setattr(importlib, "import_module", missing_import)
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "blocked_mt5_import_failed"


def test_mt5_initialize_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(initialize_success=False))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "blocked_mt5_initialize_failed"


def test_missing_risk_volume_artifact_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, missing_risk=True)
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "blocked_missing_required_artifact"


def test_missing_no_order_source_flag_blocks(tmp_path: Path) -> None:
    risk = risk_volume_manifest()
    risk.pop("no_order_check_called")
    paths = write_sources(tmp_path, risk_data=risk)
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "blocked_no_order_boundary_violation"


def test_unsafe_source_no_order_flag_false_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, risk_data=risk_volume_manifest(no_order_request_constructed=False))
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["validation_status"] == "blocked_no_order_boundary_violation"


def test_order_calc_margin_called_exactly_once_when_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = FakeMT5(margin_result=100.0)
    patch_mt5(monkeypatch, fake)
    outputs = check.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert fake.margin_call_count == 1
    assert manifest["order_calc_margin_call_count"] == 1


def test_forbidden_mt5_order_and_history_calls_are_never_called(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = FakeMT5(margin_result=100.0)
    patch_mt5(monkeypatch, fake)
    check.build_outputs(make_args(tmp_path, paths))

    assert fake.forbidden_called == []


def test_no_request_payload_dict_is_constructed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(margin_result=100.0))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    snapshot = read_json(outputs["margin_snapshot"])

    assert snapshot["no_order_request_constructed"] is True
    assert "order_request" not in snapshot
    assert "payload" not in snapshot


def test_account_sensitive_fields_are_redacted_or_omitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(margin_result=100.0))
    outputs = check.build_outputs(make_args(tmp_path, paths))
    snapshot = read_json(outputs["margin_snapshot"])

    assert snapshot["account_redaction_applied"] is True
    for field in ["login", "server", "name", "company"]:
        assert field not in snapshot


def test_report_includes_no_order_request_execution_and_approval_caveats(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No order_send was called." in report
    assert "No order_check was called." in report
    assert "No order_calc_profit was called." in report
    assert "No broker request payload was constructed." in report
    assert "No order execution was performed." in report
    assert "No demo approval was performed." in report


def test_static_source_forbids_forbidden_direct_call_signatures() -> None:
    source = Path(check.__file__).read_text(encoding="utf-8")
    forbidden = [
        "order_" + "send(",
        "order_" + "check(",
        "order_" + "calc_profit(",
        "positions_" + "get(",
        "orders_" + "get(",
        "history_orders_" + "get(",
        "history_deals_" + "get(",
    ]

    for token in forbidden:
        assert token not in source


def test_static_source_mentions_margin_estimator_without_forbidden_helpers() -> None:
    source = Path(check.__file__).read_text(encoding="utf-8")

    assert "order_calc_margin" in source


def test_static_source_has_no_scheduler_loop_background_markers() -> None:
    source = Path(check.__file__).read_text(encoding="utf-8")
    forbidden = ["Task Scheduler", "schtasks", "while True", "APScheduler", "threading.Timer"]

    for token in forbidden:
        assert token not in source


def test_static_source_has_no_broker_request_dict_patterns() -> None:
    source = Path(check.__file__).read_text(encoding="utf-8")
    forbidden = [
        "request =",
        "order_request =",
        "mt5.TRADE_ACTION_DEAL",
        "TRADE_ACTION_PENDING",
        '"action":',
        '"type":',
        '"price":',
        '"sl":',
        '"tp":',
        '"volume":',
    ]

    for token in forbidden:
        assert token not in source


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    outputs = check.build_outputs(make_args(tmp_path, paths, dry_run=True))
    manifest = read_json(outputs["manifest"])

    assert manifest["no_child_scripts_executed"] is True
