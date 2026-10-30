from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_fixed_candidate_demo_broker_local_state_reconciliation as recon


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
        "max_open_positions": 1,
    }
    payload.update(overrides)
    return payload


def demo_policy(**boundary_overrides: object) -> dict[str, object]:
    boundaries: dict[str, object] = {
        "paper_only_until_explicit_future_change": True,
        "real_money_allowed": False,
        "broker_connection_allowed_for_this_policy_file": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "order_check_allowed": False,
        "order_calc_allowed": False,
        "manual_approval_required_before_any_future_demo_order": True,
    }
    boundaries.update(boundary_overrides)
    return {
        "policy_id": "fixture_policy",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "account_currency": "EUR",
        "intended_demo_equity": 1000.0,
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
        "safety_boundaries": boundaries,
    }


def readiness_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_readiness",
        "plan_status": "future_request_construction_readiness_plan_available_no_order",
        "source_nature": "live_data_shadow_signal",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
        "order_execution_allowed": False,
    }
    payload.update(overrides)
    return payload


def margin_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_margin",
        "validation_status": "broker_safe_margin_validation_available",
        "source_nature": "live_data_shadow_signal",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "account_mode_label": "demo",
        "account_currency": "EUR",
        "account_equity_policy_status": "within_10pct",
        "broker_margin_usage_ratio": 0.27044,
        "spread_within_policy": True,
        "stepped_volume_lots": 0.07,
    }
    payload.update(overrides)
    return payload


def margin_snapshot(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_margin",
        "validation_status": "broker_safe_margin_validation_available",
        "source_nature": "live_data_shadow_signal",
        "account_mode_label": "demo",
        "account_currency": "EUR",
        "account_equity": 1000.0,
        "broker_margin_estimate": 270.44,
        "broker_margin_usage_ratio": 0.27044,
        "margin_calc_volume_lots": 0.07,
        "spread_current_points": 3.0,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
    }
    payload.update(overrides)
    return payload


def write_fixture_sources(
    tmp_path: Path,
    *,
    readiness_payload: dict[str, object] | None = None,
    margin_payload: dict[str, object] | None = None,
    margin_snapshot_payload: dict[str, object] | None = None,
    registry_payload: dict[str, object] | None = None,
    policy_payload: dict[str, object] | None = None,
    missing_readiness: bool = False,
    missing_margin: bool = False,
    missing_snapshot: bool = False,
    state_text: str | None = None,
) -> dict[str, Path]:
    readiness_dir = tmp_path / "readiness"
    margin_dir = tmp_path / "margin"
    readiness_dir.mkdir(parents=True, exist_ok=True)
    margin_dir.mkdir(parents=True, exist_ok=True)
    if not missing_readiness:
        write_json(readiness_dir / recon.READINESS_MANIFEST, readiness_payload or readiness_manifest())
    if not missing_margin:
        write_json(margin_dir / recon.MARGIN_MANIFEST, margin_payload or margin_manifest())
    if not missing_snapshot:
        write_json(margin_dir / recon.MARGIN_SNAPSHOT, margin_snapshot_payload or margin_snapshot())
    registry = write_json(tmp_path / "config" / "canonical.json", registry_payload or canonical_registry())
    policy = write_json(tmp_path / "config" / "policy.json", policy_payload or demo_policy())
    state = tmp_path / "state" / "future_state.json"
    if state_text is not None:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(state_text, encoding="utf-8")
    return {"readiness": readiness_dir, "margin": margin_dir, "registry": registry, "policy": policy, "state": state}


def make_args(tmp_path: Path, paths: dict[str, Path], *extra: str, allow_broker_read: bool = True) -> object:
    return recon.build_parser().parse_args(
        [
            "--run-id",
            "unit_broker_local_reconciliation",
            "--future-request-construction-readiness-plan-dir",
            str(paths["readiness"]),
            "--broker-safe-margin-validation-dir",
            str(paths["margin"]),
            "--canonical-registry",
            str(paths["registry"]),
            "--demo-execution-policy",
            str(paths["policy"]),
            "--future-state-json",
            str(paths["state"]),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
            *(["--allow-broker-read"] if allow_broker_read else []),
            *extra,
        ]
    )


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    def __init__(
        self,
        *,
        initialize_success: bool = True,
        trade_mode: int = 0,
        currency: str = "EUR",
        equity: float = 1000.0,
        symbol_visible: bool = True,
        positions: list[object] | None = None,
        orders: list[object] | None = None,
    ) -> None:
        self.initialize_success = initialize_success
        self.trade_mode = trade_mode
        self.currency = currency
        self.equity = equity
        self.symbol_visible = symbol_visible
        self.positions = positions if positions is not None else []
        self.orders = orders if orders is not None else []
        self.initialize_called = False
        self.shutdown_called = False
        self.positions_get_call_count = 0
        self.orders_get_call_count = 0
        self.forbidden_called: list[str] = []

    def initialize(self) -> bool:
        self.initialize_called = True
        return self.initialize_success

    def shutdown(self) -> None:
        self.shutdown_called = True

    def terminal_info(self) -> object:
        return SimpleNamespace(connected=True, trade_allowed=True, community_account=None)

    def account_info(self) -> object:
        return SimpleNamespace(
            trade_mode=self.trade_mode,
            currency=self.currency,
            equity=self.equity,
            balance=self.equity,
            leverage=30,
            trade_allowed=True,
            trade_expert=True,
        )

    def symbol_info(self, symbol: str) -> object:
        return SimpleNamespace(
            name=symbol,
            visible=self.symbol_visible,
            select=True,
            trade_mode=4,
            digits=5,
            point=0.00001,
            spread=3,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_stops_level=0,
            trade_freeze_level=0,
        )

    def positions_get(self, *, symbol: str) -> list[object]:
        self.positions_get_call_count += 1
        return self.positions

    def orders_get(self, *, symbol: str) -> list[object]:
        self.orders_get_call_count += 1
        return self.orders

    def __getattr__(self, name: str) -> object:
        forbidden = {
            "order_" + "send",
            "order_" + "check",
            "order_" + "calc_margin",
            "order_" + "calc_profit",
            "history_orders_" + "get",
            "history_deals_" + "get",
        }
        if name in forbidden:
            def fail_if_called(*_args: object, **_kwargs: object) -> None:
                self.forbidden_called.append(name)
                raise AssertionError(f"{name} must not be called")

            return fail_if_called
        raise AttributeError(name)


def patch_mt5(monkeypatch: pytest.MonkeyPatch, fake: FakeMT5) -> FakeMT5:
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    return fake


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        recon.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_dry_run_writes_artifacts_and_does_not_import_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_import(_name: str) -> object:
        raise AssertionError("MT5 must not be imported in dry-run")

    monkeypatch.setattr(recon.importlib, "import_module", fail_import)
    outputs = recon.build_outputs(make_args(tmp_path, paths, "--dry-run"))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_dry_run_no_broker_read"
    assert manifest["allow_broker_read"] is True
    assert manifest["broker_read_performed"] is False
    assert manifest["mt5_import_performed"] is False
    assert manifest["mt5_connection_performed"] is False
    assert manifest["positions_get_called"] is False
    assert manifest["orders_get_called"] is False
    for key in ["manifest", "report", "checklist", "broker_snapshot", "local_state_snapshot", "matching_fields", "status", "warnings", "no_order"]:
        assert outputs[key].exists()


def test_default_without_allow_broker_read_does_not_import_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)

    def fail_import(_name: str) -> object:
        raise AssertionError("MT5 must not be imported without --allow-broker-read")

    monkeypatch.setattr(recon.importlib, "import_module", fail_import)
    outputs = recon.build_outputs(make_args(tmp_path, paths, allow_broker_read=False))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_dry_run_no_broker_read"
    assert manifest["allow_broker_read"] is False
    assert manifest["dry_run"] is True
    assert manifest["broker_read_performed"] is False
    assert manifest["positions_get_called"] is False
    assert manifest["orders_get_called"] is False


def test_happy_path_mocked_demo_zero_positions_orders_is_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_clean_no_local_no_broker"
    assert manifest["broker_position_count_symbol"] == 0
    assert manifest["broker_pending_order_count_symbol"] == 0
    assert fake.positions_get_call_count == 1
    assert fake.orders_get_call_count == 1
    assert fake.shutdown_called is True


def test_non_demo_account_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(trade_mode=FakeMT5.ACCOUNT_TRADE_MODE_REAL))
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_non_demo_account"


def test_account_currency_mismatch_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(currency="USD"))
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_account_currency_mismatch"


def test_account_equity_outside_policy_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(equity=1200.0))
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_account_equity_outside_policy"


def test_missing_readiness_manifest_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path, missing_readiness=True)
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_missing_readiness_manifest"
    assert fake.initialize_called is False


def test_unsafe_readiness_boundary_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path, readiness_payload=readiness_manifest(request_construction_allowed_now=True))
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_unsafe_readiness_boundary"
    assert fake.initialize_called is False


def test_missing_margin_validation_manifest_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path, missing_margin=True)
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_missing_margin_validation_manifest"
    assert fake.initialize_called is False


def test_unacceptable_margin_validation_status_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path, margin_payload=margin_manifest(validation_status="blocked"))
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_unacceptable_margin_validation_status"
    assert fake.initialize_called is False


def test_observed_margin_volume_passes_when_manifest_and_snapshot_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(
        tmp_path,
        margin_payload=margin_manifest(stepped_volume_lots=0.05, broker_margin_usage_ratio=0.19364),
        margin_snapshot_payload=margin_snapshot(margin_calc_volume_lots=0.05, broker_margin_usage_ratio=0.19364),
    )
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_clean_no_local_no_broker"
    assert fake.initialize_called is True
    assert fake.positions_get_call_count == 1
    assert fake.orders_get_call_count == 1


def test_margin_volume_mismatch_between_manifest_and_snapshot_blocks_before_broker_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(
        tmp_path,
        margin_payload=margin_manifest(stepped_volume_lots=0.05),
        margin_snapshot_payload=margin_snapshot(margin_calc_volume_lots=0.07),
    )
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_unacceptable_margin_validation_status"
    assert fake.initialize_called is False


def test_margin_ratio_above_hard_cap_blocks_before_broker_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(
        tmp_path,
        margin_payload=margin_manifest(broker_margin_usage_ratio=0.7001),
        margin_snapshot_payload=margin_snapshot(broker_margin_usage_ratio=0.7001),
    )
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_unacceptable_margin_validation_status"
    assert fake.initialize_called is False


def test_margin_manifest_non_demo_account_blocks_before_broker_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path, margin_payload=margin_manifest(account_mode_label="real"))
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_unacceptable_margin_validation_status"
    assert fake.initialize_called is False


def test_margin_spread_outside_policy_blocks_before_broker_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path, margin_payload=margin_manifest(spread_within_policy=False))
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_unacceptable_margin_validation_status"
    assert fake.initialize_called is False


def test_margin_warning_status_below_hard_cap_passes_when_volume_is_coherent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    warning_status = "broker_safe_margin_validation_available_with_margin_warning"
    paths = write_fixture_sources(
        tmp_path,
        margin_payload=margin_manifest(
            validation_status=warning_status,
            stepped_volume_lots=0.05,
            broker_margin_usage_ratio=0.6,
        ),
        margin_snapshot_payload=margin_snapshot(
            validation_status=warning_status,
            margin_calc_volume_lots=0.05,
            broker_margin_usage_ratio=0.6,
        ),
    )
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_clean_no_local_no_broker"
    assert fake.positions_get_call_count == 1
    assert fake.orders_get_call_count == 1


def test_noncanonical_candidate_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path, registry_payload=canonical_registry(symbol="EURUSD"))
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "blocked_noncanonical_candidate"
    assert fake.initialize_called is False


def test_malformed_future_state_json_holds_and_is_not_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    malformed = "{ not json"
    paths = write_fixture_sources(tmp_path, state_text=malformed)
    patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_hold_local_state_malformed"
    assert paths["state"].read_text(encoding="utf-8") == malformed


def test_missing_future_state_with_zero_broker_state_is_clean_and_not_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["local_state_status"] == "local_state_missing"
    assert manifest["reconciliation_status"] == "broker_local_reconciliation_clean_no_local_no_broker"
    assert not paths["state"].exists()


def test_broker_open_position_creates_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    position = SimpleNamespace(symbol="GBPUSD", type=FakeMT5.POSITION_TYPE_SELL, volume=0.07, sl=1.346673, tp=1.3446655)
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(positions=[position]))
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_hold_local_missing_broker_open"


def test_broker_pending_order_creates_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    order = SimpleNamespace(symbol="GBPUSD", type=2, volume_current=0.07, sl=1.346673, tp=1.3446655)
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(orders=[order]))
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_hold_broker_pending_order_detected"


def test_multiple_broker_positions_create_duplicate_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    positions = [
        SimpleNamespace(symbol="GBPUSD", type=FakeMT5.POSITION_TYPE_SELL, volume=0.07),
        SimpleNamespace(symbol="GBPUSD", type=FakeMT5.POSITION_TYPE_SELL, volume=0.07),
    ]
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5(positions=positions))
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_hold_duplicate_broker_positions"


def test_positions_get_and_orders_get_called_once_each_in_real_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    fake = patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    evidence = read_csv(outputs["no_order"])[0]

    assert fake.positions_get_call_count == 1
    assert fake.orders_get_call_count == 1
    assert evidence["positions_get_call_count"] == "1"
    assert evidence["orders_get_call_count"] == "1"


def test_forbidden_order_check_calc_history_functions_are_never_called(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    fake = patch_mt5(monkeypatch, FakeMT5())
    recon.build_outputs(make_args(tmp_path, paths))

    assert fake.forbidden_called == []


def test_no_request_dictionary_or_executable_order_object_is_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    evidence = read_csv(outputs["no_order"])[0]

    assert manifest["no_order_request_constructed"] is True
    assert evidence["no_order_request_constructed"] == "true"
    assert manifest["no_order_execution_performed"] is True


def test_no_db_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_fixture_sources(tmp_path)
    patch_mt5(monkeypatch, FakeMT5())
    outputs = recon.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["no_db_mutation_performed"] is True


def test_static_safety_grep_confirms_no_forbidden_send_check_calc_history_calls() -> None:
    source = Path(recon.__file__).read_text(encoding="utf-8")
    forbidden = [
        "order_" + "send(",
        "order_" + "check(",
        "order_" + "calc_margin(",
        "order_" + "calc_profit(",
        "history_orders_" + "get(",
        "history_deals_" + "get(",
    ]

    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_scheduler_loop_background_markers() -> None:
    source = Path(recon.__file__).read_text(encoding="utf-8")
    forbidden = ["while " + "True", "Background" + "Scheduler", "schedule" + ".every", "threading" + ".", "asyncio" + "."]

    for token in forbidden:
        assert token not in source
