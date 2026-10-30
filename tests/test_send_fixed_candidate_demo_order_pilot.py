import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import send_fixed_candidate_demo_order_pilot as pilot


FUTURE_EXPIRY = "2099-01-01T00:00:00+00:00"
EXPIRED_EXPIRY = "2020-01-01T00:00:00+00:00"


def created_at_utc(*, minutes_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def readiness_manifest(*, fixture: bool = False, **overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "run_id": "send_readiness_live_v1",
        "created_at_utc": created_at_utc(),
        "order_send_pilot_readiness_status": "order_send_pilot_readiness_plan_available_no_send",
        "readiness_patch_status": "order_send_pilot_readiness_audit_gaps_closed_no_send",
        "future_order_send_ready": True,
        "source_nature": "passed_order_check",
    }
    if fixture:
        content.update(
            {
                "run_id": "send_readiness_fixture_v1",
                "order_send_pilot_readiness_status": "order_send_pilot_readiness_plan_fixture_only_no_order_check_pass",
                "future_order_send_ready": False,
                "source_nature": "fixture_or_blocked",
            }
        )
    content.update(overrides)
    return content


def order_check_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "run_id": "order_check_live_v1",
        "created_at_utc": created_at_utc(),
        "order_check_status": "order_check_available_passed_no_send",
        "order_check_called": True,
        "order_check_call_count": 1,
        "order_check_passed": True,
        "order_check_retcode": 0,
        "order_send_called": False,
        "source_nature": "real_order_check",
    }
    content.update(overrides)
    return content


def request_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "run_id": "request_construction_live_v1",
        "created_at_utc": created_at_utc(),
        "request_construction_status": "request_construction_dry_run_available_non_executable",
        "request_intent_created": True,
        "broker_payload_constructed": False,
        "executable_order_object_constructed": False,
        "source_nature": "approved_non_fixture",
    }
    content.update(overrides)
    return content


def module_validation_request_manifest(**overrides: object) -> dict[str, object]:
    content = request_manifest(
        request_construction_status="request_construction_dry_run_available_with_stale_override_for_demo_module_validation",
        module_validation_demo_execution=True,
        stale_override_used=True,
        expired_signal_override_used=True,
        strategy_valid=False,
        production_valid=False,
        order_check_allowed_for_demo_module_validation_only=True,
        order_send_allowed_for_demo_module_validation_only=False,
    )
    content.update(overrides)
    return content


def module_validation_readiness_manifest(**overrides: object) -> dict[str, object]:
    content = readiness_manifest(
        module_validation_demo_execution=True,
        stale_override_used=True,
        expired_signal_override_used=True,
        strategy_valid=False,
        production_valid=False,
        send_readiness_for_demo_module_validation_only=True,
    )
    content.update(overrides)
    return content


def request_intent(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "side": "sell",
        "volume_lots": 0.07,
        "entry_reference_price": 1.25,
        "sl_price": 1.26,
        "tp_price": 1.235,
        "signal_id": "signal-live-1",
        "idempotency_key": "idem-live-1",
        "approval_record_id": "approval-live-1",
        "approval_record_digest": "a" * 64,
    }
    content.update(overrides)
    return content


def approval_record(**overrides: object) -> dict[str, object]:
    content = request_intent()
    content.update(
        {
            "created_at_utc": created_at_utc(),
            "approval_status": "approved_for_future_request_construction_only",
            "approval_scope": "future_request_construction_only",
            "approval_revoked": False,
            "approval_expiry_time_utc": FUTURE_EXPIRY,
            "record_hash_or_digest": "a" * 64,
        }
    )
    content.update(overrides)
    return content


def reconciliation_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "reconciliation_status": "broker_local_reconciliation_clean_no_local_no_broker",
        "created_at_utc": created_at_utc(),
        "broker_position_count_symbol": 0,
        "broker_pending_order_count_symbol": 0,
    }
    content.update(overrides)
    return content


def margin_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "validation_status": "broker_safe_margin_validation_available",
        "created_at_utc": created_at_utc(),
        "source_nature": "live_data_shadow_signal",
        "account_mode_label": "demo",
        "account_currency": "EUR",
        "account_equity_policy_status": "within_10pct",
        "broker_margin_usage_ratio": 0.27,
        "spread_within_policy": True,
        "stepped_volume_lots": 0.07,
        "margin_calc_volume_lots": 0.07,
    }
    content.update(overrides)
    return content


def freshness_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "freshness_status": "live_signal_freshness_fresh_current_or_latest_signal",
        "created_at_utc": created_at_utc(),
        "is_fresh": True,
        "is_stale": False,
        "bars_elapsed": 1,
    }
    content.update(overrides)
    return content


def duplicate_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "plan_status": "duplicate_protection_plan_available_no_order",
        "max_open_positions": 1,
        "plan_actionable": False,
    }
    content.update(overrides)
    return content


def manual_plan_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "plan_status": "manual_approval_kill_switch_plan_available_no_order",
        "kill_switch_executed": False,
        "plan_actionable": False,
    }
    content.update(overrides)
    return content


def registry(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
    }
    content.update(overrides)
    return content


def policy(**boundary_overrides: object) -> dict[str, object]:
    boundaries: dict[str, object] = {
        "real_money_allowed": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "order_check_allowed": False,
        "order_calc_allowed": False,
        "manual_approval_required_before_any_future_demo_order": True,
    }
    boundaries.update(boundary_overrides)
    return {
        "policy_id": "demo_execution_policy_v1",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
        "safety_boundaries": boundaries,
    }


def write_sources(
    tmp_path: Path,
    *,
    fixture_readiness: bool = False,
    readiness_payload: dict[str, object] | None = None,
    order_check_payload: dict[str, object] | None = None,
    request_payload: dict[str, object] | None = None,
    intent_payload: dict[str, object] | None = None,
    approval_payload: dict[str, object] | None = None,
    reconciliation_payload: dict[str, object] | None = None,
    margin_payload: dict[str, object] | None = None,
    margin_snapshot_payload: dict[str, object] | None = None,
    freshness_payload: dict[str, object] | None = None,
    duplicate_payload: dict[str, object] | None = None,
    manual_payload: dict[str, object] | None = None,
    registry_payload: dict[str, object] | None = None,
    policy_payload: dict[str, object] | None = None,
    future_state_payload: dict[str, object] | None = None,
) -> dict[str, Path]:
    readiness_dir = tmp_path / "readiness"
    order_check_dir = tmp_path / "order_check"
    request_dir = tmp_path / "request"
    recon_dir = tmp_path / "reconciliation"
    margin_dir = tmp_path / "margin"
    freshness_dir = tmp_path / "freshness"
    duplicate_dir = tmp_path / "duplicate"
    manual_dir = tmp_path / "manual"
    state_dir = tmp_path / "state"
    write_json(readiness_dir / pilot.READINESS_MANIFEST, readiness_payload or readiness_manifest(fixture=fixture_readiness))
    for file_name in pilot.READINESS_CONTRACT_FILES:
        write_csv(readiness_dir / file_name, [{"contract": "available"}], ["contract"])
    intent_data = intent_payload or request_intent()
    approval_data = approval_payload or approval_record()
    request_data = request_payload or request_manifest()
    write_json(order_check_dir / pilot.ORDER_CHECK_RESULT, {"retcode": 0, "order_check_passed": True})
    write_csv(order_check_dir / pilot.ORDER_CHECK_BOUND_INTENT, [intent_data], list(intent_data))
    write_csv(request_dir / pilot.REQUEST_INTENT, [intent_data], list(intent_data))
    write_csv(request_dir / pilot.REQUEST_FIELDS, [{"field_name": "symbol", "intended_value": "GBPUSD"}], ["field_name", "intended_value"])
    request_data.setdefault("request_intent_digest", pilot.sha256_file(request_dir / pilot.REQUEST_INTENT))
    request_data.setdefault("request_fields_digest", pilot.sha256_file(request_dir / pilot.REQUEST_FIELDS))
    write_json(request_dir / pilot.REQUEST_MANIFEST, request_data)
    order_data = order_check_payload or order_check_manifest()
    order_data.setdefault("approval_record_digest", approval_data.get("record_hash_or_digest", ""))
    order_data.setdefault("request_intent_digest", request_data["request_intent_digest"])
    order_data.setdefault("request_fields_digest", request_data["request_fields_digest"])
    order_data.setdefault("order_check_result_digest", pilot.sha256_file(order_check_dir / pilot.ORDER_CHECK_RESULT))
    order_data.setdefault("digest_algorithm", "sha256")
    order_data.setdefault("digest_canonicalization", "canonical_json_or_documented_csv_rule")
    order_data.setdefault("order_check_manifest_digest", pilot.sha256_payload_excluding(order_data, {"order_check_manifest_digest"}))
    write_json(order_check_dir / pilot.ORDER_CHECK_MANIFEST, order_data)
    approval_path = write_json(state_dir / "approval.json", approval_data)
    write_json(recon_dir / pilot.RECONCILIATION_MANIFEST, reconciliation_payload or reconciliation_manifest())
    write_json(margin_dir / pilot.MARGIN_MANIFEST, margin_payload or margin_manifest())
    write_json(margin_dir / pilot.MARGIN_SNAPSHOT, margin_snapshot_payload or margin_payload or margin_manifest())
    write_json(freshness_dir / pilot.FRESHNESS_MANIFEST, freshness_payload or freshness_manifest())
    write_json(duplicate_dir / pilot.DUPLICATE_MANIFEST, duplicate_payload or duplicate_manifest())
    write_json(manual_dir / pilot.MANUAL_PLAN_MANIFEST, manual_payload or manual_plan_manifest())
    registry_path = write_json(tmp_path / "registry.json", registry_payload or registry())
    policy_path = write_json(tmp_path / "policy.json", policy_payload or policy())
    future_state = state_dir / "future_state.json"
    if future_state_payload is not None:
        write_json(future_state, future_state_payload)
    return {
        "readiness_dir": readiness_dir,
        "order_check_dir": order_check_dir,
        "request_dir": request_dir,
        "approval": approval_path,
        "reconciliation_dir": recon_dir,
        "margin_dir": margin_dir,
        "freshness_dir": freshness_dir,
        "duplicate_dir": duplicate_dir,
        "manual_dir": manual_dir,
        "registry": registry_path,
        "policy": policy_path,
        "future_state": future_state,
    }


def args_for(tmp_path: Path, paths: dict[str, Path], *extra: str) -> object:
    argv = [
        "--run-id",
        "pilot-test-v1",
        "--order-send-pilot-readiness-plan-dir",
        str(paths["readiness_dir"]),
        "--order-check-dir",
        str(paths["order_check_dir"]),
        "--request-construction-dry-run-dir",
        str(paths["request_dir"]),
        "--manual-approval-record-json",
        str(paths["approval"]),
        "--broker-local-reconciliation-dir",
        str(paths["reconciliation_dir"]),
        "--broker-safe-margin-validation-dir",
        str(paths["margin_dir"]),
        "--live-signal-freshness-dir",
        str(paths["freshness_dir"]),
        "--duplicate-protection-plan-dir",
        str(paths["duplicate_dir"]),
        "--manual-approval-kill-switch-plan-dir",
        str(paths["manual_dir"]),
        "--canonical-registry",
        str(paths["registry"]),
        "--demo-execution-policy",
        str(paths["policy"]),
        "--future-state-json",
        str(paths["future_state"]),
        "--output-dir",
        str(tmp_path / "out"),
        "--mt5-package",
        "fake_mt5",
        "--overwrite",
    ]
    argv.extend(extra)
    return pilot.build_parser().parse_args(argv)


def build(tmp_path: Path, *extra: str, force_real_without_allow: bool = False, **kwargs: object) -> tuple[dict[str, Path], dict[str, object], dict[str, Path]]:
    paths = write_sources(tmp_path, **kwargs)
    args = args_for(tmp_path, paths, *extra)
    if force_real_without_allow:
        args.dry_run = False
    outputs = pilot.build_outputs(args)
    return outputs, read_json(outputs["manifest"]), paths


def test_broker_safe_comment_abbreviates_long_values() -> None:
    comment = pilot.build_broker_safe_comment(
        "gbpusd_short_h10_1_5_off_hours_demo_extra_long",
        "idempotencykey0123456789",
    )

    assert isinstance(comment, str)
    assert len(comment) <= pilot.BROKER_COMMENT_MAX_LENGTH
    assert comment.endswith("456789")
    assert pilot.broker_comment_is_safe(comment)


def test_broker_safe_comment_sanitizes_problematic_characters() -> None:
    comment = pilot.build_broker_safe_comment(
        "GBP/USD short demo!",
        "idem key:/ç-ABC123!!",
    )

    assert len(comment) <= pilot.BROKER_COMMENT_MAX_LENGTH
    assert comment.endswith("abc123")
    assert all(char.isascii() and char.isalnum() for char in comment)
    assert " " not in comment
    assert ":" not in comment
    assert "_" not in comment
    assert pilot.broker_comment_is_safe(comment)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = "demo"
    TRADE_ACTION_DEAL = 1
    POSITION_TYPE_SELL = 1
    ORDER_TYPE_SELL = 2
    ORDER_TIME_GTC = 3
    ORDER_FILLING_IOC = 4
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_REJECT = 10006
    TRADE_RETCODE_REQUOTE = 10004
    TRADE_RETCODE_PRICE_CHANGED = 10020
    TRADE_RETCODE_PRICE_OFF = 10021
    TRADE_RETCODE_INVALID_STOPS = 10016
    TRADE_RETCODE_INVALID_VOLUME = 10014
    TRADE_RETCODE_INVALID_FILL = 10030
    TRADE_RETCODE_MARKET_CLOSED = 10018
    TRADE_RETCODE_NO_MONEY = 10019
    TRADE_RETCODE_TRADE_DISABLED = 10017
    TRADE_RETCODE_TOO_MANY_REQUESTS = 10024
    TRADE_RETCODE_CONNECTION = 10031
    TRADE_RETCODE_CLIENT_DISABLES_AT = 10027

    def __init__(
        self,
        *,
        retcode: int = 10009,
        result_comment: str = "mocked-result",
        result_none: bool = False,
        send_exception: Exception | None = None,
        initialize_success: bool = True,
        trade_mode: str = "demo",
        currency: str = "EUR",
        symbol_available: bool = True,
        tick_available: bool = True,
        positions: list[object] | None = None,
        orders: list[object] | None = None,
        post_positions: list[object] | None = None,
        post_orders: list[object] | None = None,
        post_positions_exception: Exception | None = None,
        post_orders_exception: Exception | None = None,
        state_path: Path | None = None,
        trade_allowed: bool = True,
    ) -> None:
        self.retcode = retcode
        self.result_comment = result_comment
        self.result_none = result_none
        self.send_exception = send_exception
        self.initialize_success = initialize_success
        self.trade_mode = trade_mode
        self.currency = currency
        self.symbol_available = symbol_available
        self.tick_available = tick_available
        self.positions = positions or []
        self.orders = orders or []
        self.post_positions = post_positions or []
        self.post_orders = post_orders or []
        self.post_positions_exception = post_positions_exception
        self.post_orders_exception = post_orders_exception
        self.state_path = state_path
        self.trade_allowed = trade_allowed
        self.order_send_call_count = 0
        self.positions_get_call_count = 0
        self.orders_get_call_count = 0
        self.shutdown_call_count = 0
        self.state_existed_before_send = False
        self.last_send_parameters: dict[str, object] | None = None

    def initialize(self) -> bool:
        return self.initialize_success

    def shutdown(self) -> None:
        self.shutdown_call_count += 1

    def terminal_info(self) -> object:
        return SimpleNamespace(connected=True, trade_allowed=self.trade_allowed)

    def account_info(self) -> object:
        return SimpleNamespace(
            trade_mode=self.trade_mode,
            currency=self.currency,
            equity=1000.0,
            balance=1000.0,
            trade_allowed=self.trade_allowed,
        )

    def symbol_info(self, _symbol: str) -> object | None:
        if not self.symbol_available:
            return None
        return SimpleNamespace(name="GBPUSD", visible=True, spread=3, volume_min=0.01, volume_max=100.0, volume_step=0.01)

    def symbol_info_tick(self, _symbol: str) -> object | None:
        return SimpleNamespace(bid=1.25, ask=1.2501) if self.tick_available else None

    def positions_get(self, *, symbol: str) -> list[object]:
        assert symbol == "GBPUSD"
        self.positions_get_call_count += 1
        if self.positions_get_call_count == 1:
            return self.positions
        if self.post_positions_exception is not None:
            raise self.post_positions_exception
        return self.post_positions

    def orders_get(self, *, symbol: str) -> list[object]:
        assert symbol == "GBPUSD"
        self.orders_get_call_count += 1
        if self.orders_get_call_count == 1:
            return self.orders
        if self.post_orders_exception is not None:
            raise self.post_orders_exception
        return self.post_orders

    def order_send(self, value: dict[str, object]) -> object | None:
        self.order_send_call_count += 1
        self.last_send_parameters = dict(value)
        self.state_existed_before_send = bool(self.state_path and self.state_path.exists())
        assert value["symbol"] == "GBPUSD"
        assert value["type"] == self.ORDER_TYPE_SELL
        if self.send_exception is not None:
            raise self.send_exception
        if self.result_none:
            return None
        return SimpleNamespace(
            retcode=self.retcode,
            comment=self.result_comment,
            order=7001 if self.retcode == self.TRADE_RETCODE_PLACED else 0,
            deal=8001 if self.retcode == self.TRADE_RETCODE_DONE else 0,
            position=9001 if self.retcode == self.TRADE_RETCODE_DONE else 0,
            volume=0.07,
            price=1.25,
        )


def install_fake(monkeypatch: pytest.MonkeyPatch, fake: FakeMT5) -> FakeMT5:
    monkeypatch.setitem(sys.modules, "fake_mt5", fake)
    return fake


def real_args() -> tuple[str, ...]:
    return ("--allow-real-order-send", "--operator-final-send-confirmation", pilot.FINAL_CONFIRMATION)


def demo_module_validation_args() -> tuple[str, ...]:
    return (
        *real_args(),
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        pilot.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
    )


def client_reject_resend_args() -> tuple[str, ...]:
    return (
        *demo_module_validation_args(),
        "--allow-new-demo-send-after-client-reject-flat",
        "--client-reject-resend-acknowledgment",
        pilot.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
    )


def client_reject_flat_state(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "approval_record_id": "approval-record-v1",
        "broker_deal_ticket": 0,
        "broker_order_ticket": 0,
        "broker_position_ticket": "",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "crash_recovery_required": False,
        "direction": "short",
        "idempotency_key": "idem-live-1",
        "last_retcode": pilot.CLIENT_AUTOTRADING_DISABLED_RETCODE,
        "order_execution_performed": False,
        "reconciliation_status": "broker_local_reconciliation_clean_after_client_reject_no_broker_state",
        "retry_performed": False,
        "automatic_retry_allowed": False,
        "send_attempt_id": "previous-send",
        "send_completed_at_utc": "2026-06-27T13:10:53+00:00",
        "send_started_at_utc": "2026-06-27T13:10:52+00:00",
        "signal_id": "signal-live-1",
        "state_status": "send_rejected_no_position_no_order",
        "symbol": "GBPUSD",
        "timeframe": "M15",
    }
    payload.update(overrides)
    return payload


def market_closed_flat_state(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "approval_record_id": "approval-record-v1",
        "broker_deal_ticket": 0,
        "broker_order_ticket": 0,
        "broker_position_ticket": "",
        "broker_position_detected_after_send": False,
        "broker_pending_order_detected_after_send": False,
        "broker_position_count_after_send": 0,
        "broker_pending_order_count_after_send": 0,
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "crash_recovery_required": True,
        "direction": "short",
        "idempotency_key": "previous-idem",
        "last_retcode": 10018,
        "order_execution_performed": False,
        "reconciliation_status": "broker_local_reconciliation_clean_after_reject_no_broker_state",
        "retry_performed": False,
        "automatic_retry_allowed": False,
        "send_attempt_id": "previous-market-closed-send",
        "send_completed_at_utc": "2026-06-27T13:10:53+00:00",
        "send_started_at_utc": "2026-06-27T13:10:52+00:00",
        "signal_id": "previous-signal",
        "state_status": "execution_rejected",
        "symbol": "GBPUSD",
        "timeframe": "M15",
    }
    payload.update(overrides)
    return payload


def matching_position(**overrides: object) -> object:
    content: dict[str, object] = {
        "symbol": "GBPUSD",
        "type": FakeMT5.POSITION_TYPE_SELL,
        "volume": 0.07,
        "sl": 1.26,
        "tp": 1.235,
        "ticket": 9001,
        "identifier": 9001,
    }
    content.update(overrides)
    return SimpleNamespace(**content)


def matching_order(**overrides: object) -> object:
    content: dict[str, object] = {
        "symbol": "GBPUSD",
        "type": FakeMT5.ORDER_TYPE_SELL,
        "volume_current": 0.07,
        "sl": 1.26,
        "tp": 1.235,
        "ticket": 7001,
        "order": 7001,
    }
    content.update(overrides)
    return SimpleNamespace(**content)


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        pilot.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_dry_run_fixture_only_blocks_and_calls_no_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, paths = build(tmp_path, "--dry-run", fixture_readiness=True)
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_fixture_only_readiness"
    assert fake.order_send_call_count == 0
    assert not paths["future_state"].exists()


def test_valid_default_dry_run_writes_no_state_and_calls_no_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, paths = build(tmp_path)
    assert manifest["order_send_pilot_status"] == "order_send_pilot_dry_run_no_send"
    assert fake.order_send_call_count == 0
    assert manifest["future_state_json_written"] is False
    assert not paths["future_state"].exists()


def test_real_mode_without_allow_flag_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, force_real_without_allow=True)
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_real_send_not_allowed"


def test_real_send_without_final_confirmation_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, "--allow-real-order-send")
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_missing_final_confirmation"
    assert fake.order_send_call_count == 0


def test_real_send_with_wrong_final_confirmation_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        "--allow-real-order-send",
        "--operator-final-send-confirmation",
        "approve_multiple_sends",
    )
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_missing_final_confirmation"
    assert fake.order_send_call_count == 0


def test_real_send_fixture_only_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), fixture_readiness=True)
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_fixture_only_readiness"
    assert fake.order_send_call_count == 0


def test_real_send_without_passed_order_check_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), order_check_payload=order_check_manifest(order_check_passed=False))
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_no_passed_order_check"
    assert fake.order_send_call_count == 0


def test_real_send_passed_order_check_with_nonzero_retcode_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), order_check_payload=order_check_manifest(order_check_retcode=10013))
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_no_passed_order_check"
    assert fake.order_send_call_count == 0


def test_real_send_passed_order_check_without_call_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *real_args(),
        order_check_payload=order_check_manifest(order_check_called=False, order_check_call_count=0),
    )
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_no_passed_order_check"
    assert fake.order_send_call_count == 0


def test_real_send_max_order_send_attempts_above_one_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), "--max-order-send-attempts", "2")
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_max_attempts_not_one"
    assert fake.order_send_call_count == 0


def test_real_send_missing_approval_digest_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    intent = request_intent()
    intent.pop("approval_record_digest")
    _outputs, manifest, _paths = build(tmp_path, *real_args(), intent_payload=intent)

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_missing_digest_binding"
    assert manifest["digest_binding_verified"] is False
    assert manifest["missing_digest_count"] == 1
    assert fake.order_send_call_count == 0


def test_real_send_request_intent_digest_mismatch_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *real_args(),
        request_payload=request_manifest(request_intent_digest="b" * 64),
    )

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_digest_mismatch"
    assert manifest["digest_binding_verified"] is False
    assert manifest["digest_mismatch_count"] >= 1
    assert fake.order_send_call_count == 0


def test_real_send_order_check_result_digest_mismatch_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *real_args(),
        order_check_payload=order_check_manifest(order_check_result_digest="b" * 64),
    )

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_digest_mismatch"
    assert manifest["digest_binding_verified"] is False
    assert manifest["digest_mismatch_count"] >= 1
    assert fake.order_send_call_count == 0


def test_stale_order_check_artifact_blocks_real_send_before_mt5_import(tmp_path: Path) -> None:
    outputs, manifest, _paths = build(
        tmp_path,
        *real_args(),
        order_check_payload=order_check_manifest(created_at_utc=created_at_utc(minutes_ago=6)),
    )
    evidence = read_csv(outputs["no_order_evidence"])[0]
    rows = read_csv(outputs["artifact_freshness"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_stale_upstream_artifact"
    assert manifest["order_send_called"] is False
    assert evidence["mt5_import_performed"] == "false"
    assert any(row["artifact_name"] == "order_check" and row["status"] == "stale" for row in rows)


def test_malformed_order_check_timestamp_blocks_real_send_before_mt5_import(tmp_path: Path) -> None:
    outputs, manifest, _paths = build(
        tmp_path,
        *real_args(),
        order_check_payload=order_check_manifest(created_at_utc="not-a-timestamp"),
    )
    evidence = read_csv(outputs["no_order_evidence"])[0]
    rows = read_csv(outputs["artifact_freshness"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_stale_upstream_artifact"
    assert evidence["mt5_import_performed"] == "false"
    assert any(row["artifact_name"] == "order_check" and row["status"] == "malformed_timestamp" for row in rows)


def test_stale_signal_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *real_args(),
        freshness_payload=freshness_manifest(freshness_status="stale", is_fresh=False, is_stale=True, bars_elapsed=11),
    )
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_stale_signal"
    assert fake.order_send_call_count == 0


def test_expired_approval_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY))
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_expired_approval"
    assert fake.order_send_call_count == 0


def test_dirty_reconciliation_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *real_args(),
        reconciliation_payload=reconciliation_manifest(reconciliation_status="hold", broker_position_count_symbol=1),
    )
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_broker_local_reconciliation"
    assert fake.order_send_call_count == 0


def test_margin_breach_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), margin_payload=margin_manifest(broker_margin_usage_ratio=0.71))
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_margin_policy"
    assert fake.order_send_call_count == 0


def test_margin_warning_status_under_hard_cap_passes_dry_run_gate(tmp_path: Path) -> None:
    warning_status = "broker_safe_margin_validation_available_with_margin_warning"
    _outputs, manifest, _paths = build(
        tmp_path,
        "--dry-run",
        margin_payload=margin_manifest(validation_status=warning_status, broker_margin_usage_ratio=0.6),
    )
    assert manifest["order_send_pilot_status"] == "order_send_pilot_dry_run_no_send"


def test_margin_volume_mismatch_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *real_args(),
        margin_payload=margin_manifest(stepped_volume_lots=0.05, margin_calc_volume_lots=0.07),
    )
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_margin_policy"
    assert fake.order_send_call_count == 0


def test_margin_artifact_non_demo_account_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), margin_payload=margin_manifest(account_mode_label="real"))
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_margin_policy"
    assert fake.order_send_call_count == 0


def test_margin_spread_outside_policy_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), margin_payload=margin_manifest(spread_within_policy=False))
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_margin_policy"
    assert fake.order_send_call_count == 0


def test_duplicate_protection_unavailable_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), duplicate_payload=duplicate_manifest(plan_status="hold"))
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_duplicate_protection"
    assert fake.order_send_call_count == 0


def test_kill_switch_active_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), manual_payload=manual_plan_manifest(kill_switch_executed=True))
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_kill_switch"
    assert fake.order_send_call_count == 0


def test_incompatible_future_state_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), future_state_payload={"state_status": "open"})
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_future_state_incompatible"
    assert fake.order_send_call_count == 0


def test_existing_active_idempotency_key_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), future_state_payload={"state_status": "closed", "idempotency_key": "idem-live-1"})
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_existing_active_idempotency_key"
    assert fake.order_send_call_count == 0


def test_market_closed_flat_same_signal_blocks_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *real_args(),
        future_state_payload=market_closed_flat_state(signal_id="signal-live-1", idempotency_key="idem-live-1"),
    )

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_existing_active_idempotency_key"
    assert manifest["explicit_new_signal_after_market_closed_flat"] is False
    assert manifest["previous_send_retcode"] == 10018
    assert manifest["previous_state_status"] == "execution_rejected"
    assert fake.order_send_call_count == 0


def test_market_closed_flat_new_signal_allows_send_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path, future_state_payload=market_closed_flat_state())
    fake = install_fake(
        monkeypatch,
        FakeMT5(state_path=paths["future_state"], retcode=FakeMT5.TRADE_RETCODE_DONE, post_positions=[matching_position()]),
    )
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args()))
    manifest = read_json(outputs["manifest"])
    state = read_json(paths["future_state"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_success_deal_reconciliation_required"
    assert manifest["explicit_new_signal_after_market_closed_flat"] is True
    assert manifest["previous_send_retcode"] == 10018
    assert manifest["previous_state_status"] == "execution_rejected"
    assert manifest["new_signal_id_differs_from_previous_state"] is True
    assert manifest["new_idempotency_key_differs_from_previous_state"] is True
    assert manifest["automatic_retry_allowed"] is False
    assert manifest["retry_performed"] is False
    assert manifest["order_send_call_count"] == 1
    assert fake.order_send_call_count == 1
    assert state["previous_send_retcode"] == 10018
    assert state["previous_state_status"] == "execution_rejected"
    assert state["automatic_retry_allowed"] is False
    assert state["retry_performed"] is False


def test_unsafe_policy_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, *real_args(), policy_payload=policy(real_money_allowed=True))
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_unsafe_policy"
    assert fake.order_send_call_count == 0


def test_non_demo_account_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = install_fake(monkeypatch, FakeMT5(trade_mode="real", state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args()))
    assert read_json(outputs["manifest"])["order_send_pilot_status"] == "order_send_pilot_blocked_non_demo_account"
    assert fake.order_send_call_count == 0


def test_currency_mismatch_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = install_fake(monkeypatch, FakeMT5(currency="USD", state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args()))
    assert read_json(outputs["manifest"])["order_send_pilot_status"] == "order_send_pilot_blocked_account_currency_mismatch"
    assert fake.order_send_call_count == 0


def test_symbol_unavailable_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = install_fake(monkeypatch, FakeMT5(symbol_available=False, state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args()))
    assert read_json(outputs["manifest"])["order_send_pilot_status"] == "order_send_pilot_blocked_symbol_unavailable"
    assert fake.order_send_call_count == 0


def test_tick_unavailable_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = install_fake(monkeypatch, FakeMT5(tick_available=False, state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args()))
    assert read_json(outputs["manifest"])["order_send_pilot_status"] == "order_send_pilot_blocked_tick_unavailable"
    assert fake.order_send_call_count == 0


def test_mt5_import_failure_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    args = args_for(tmp_path, paths, *real_args())
    args.mt5_package = "definitely_missing_mock_mt5_package"
    outputs = pilot.build_outputs(args)
    assert read_json(outputs["manifest"])["order_send_pilot_status"] == "order_send_pilot_blocked_mt5_import_failure"


def test_mt5_initialize_failure_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = install_fake(monkeypatch, FakeMT5(initialize_success=False, state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args()))
    assert read_json(outputs["manifest"])["order_send_pilot_status"] == "order_send_pilot_blocked_mt5_initialize_failure"
    assert fake.order_send_call_count == 0


def run_mocked_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake: FakeMT5) -> tuple[dict[str, Path], dict[str, object], dict[str, Path]]:
    paths = write_sources(tmp_path)
    fake.state_path = paths["future_state"]
    install_fake(monkeypatch, fake)
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args()))
    return outputs, read_json(outputs["manifest"]), paths


def test_demo_module_validation_contract_sends_once_with_expired_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = write_sources(
        tmp_path,
        readiness_payload=module_validation_readiness_manifest(),
        request_payload=module_validation_request_manifest(),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )
    fake = install_fake(monkeypatch, FakeMT5(post_positions=[matching_position()], state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *demo_module_validation_args()))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_success_deal_reconciliation_required"
    assert manifest["order_send_call_count"] == 1
    assert manifest["order_send_attempt_count"] == 1
    assert manifest["order_check_status"] == "order_check_available_passed_no_send"
    assert manifest["order_check_retcode"] == 0
    assert manifest["readiness_status"] == "order_send_pilot_readiness_plan_available_no_send"
    assert manifest["module_validation_demo_execution"] is True
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False
    assert manifest["send_allowed_for_demo_module_validation_only"] is True
    assert manifest["no_retry_performed"] is True
    assert manifest["no_loop_added"] is True
    assert manifest["no_scheduler_added"] is True
    assert fake.order_send_call_count == 1


def test_demo_module_validation_missing_ack_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(
        tmp_path,
        readiness_payload=module_validation_readiness_manifest(),
        request_payload=module_validation_request_manifest(),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args(), "--module-validation-demo-execution"))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_no_passed_order_check"
    assert manifest["send_allowed_for_demo_module_validation_only"] is False
    assert fake.order_send_call_count == 0


def test_success_deal_with_matching_position_reconciles_matched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMT5(retcode=FakeMT5.TRADE_RETCODE_DONE, post_positions=[matching_position()])
    outputs, manifest, paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        fake,
    )
    snapshot = read_json(outputs["reconciliation_snapshot"])
    send_snapshot = read_json(outputs["send_result_snapshot"])
    state = read_json(paths["future_state"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_success_deal_reconciliation_required"
    assert manifest["order_send_call_count"] == 1
    assert fake.order_send_call_count == 1
    assert fake.last_send_parameters is not None
    assert pilot.broker_comment_is_safe(fake.last_send_parameters["comment"])
    assert len(str(fake.last_send_parameters["comment"])) <= pilot.BROKER_COMMENT_MAX_LENGTH
    assert fake.last_send_parameters["volume"] == 0.07
    assert fake.last_send_parameters["sl"] == 1.26
    assert fake.last_send_parameters["tp"] == 1.235
    assert manifest["comment_broker_safe"] is True
    assert manifest["comment_length"] <= pilot.BROKER_COMMENT_MAX_LENGTH
    assert manifest["comment_redacted_preview"]
    assert send_snapshot["comment_broker_safe"] is True
    assert send_snapshot["comment_length"] <= pilot.BROKER_COMMENT_MAX_LENGTH
    assert send_snapshot["comment_redacted_preview"]
    assert manifest["digest_binding_required"] is True
    assert manifest["digest_binding_verified"] is True
    assert manifest["missing_digest_count"] == 0
    assert manifest["digest_mismatch_count"] == 0
    assert manifest["post_send_reconciliation_performed"] is True
    assert manifest["post_send_positions_get_called"] is True
    assert manifest["post_send_positions_get_call_count"] == 1
    assert manifest["post_send_orders_get_called"] is True
    assert manifest["post_send_orders_get_call_count"] == 1
    assert manifest["broker_position_detected_after_send"] is True
    assert manifest["broker_pending_order_detected_after_send"] is False
    assert manifest["broker_position_count_after_send"] == 1
    assert manifest["broker_pending_order_count_after_send"] == 0
    assert manifest["reconciliation_status"] == "broker_local_reconciliation_matched_after_send"
    assert manifest["state_status"] == "broker_position_detected"
    assert state["state_status"] == "broker_position_detected"
    assert state["reconciliation_status"] == "broker_local_reconciliation_matched_after_send"
    assert snapshot["matching_position_count"] == 1
    assert snapshot["positions"][0]["matched_expected_symbol"] is True
    assert snapshot["positions"][0]["matched_expected_side"] is True
    assert snapshot["positions"][0]["matched_expected_volume"] is True
    assert snapshot["positions"][0]["matched_expected_sl"] is True
    assert snapshot["positions"][0]["matched_expected_tp"] is True
    assert snapshot["positions"][0]["ticket_redacted"].startswith("redacted:")
    assert snapshot["raw_executable_payload_written"] is False


def test_invalid_broker_comment_blocks_before_order_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMT5()
    monkeypatch.setattr(
        pilot,
        "build_broker_safe_comment",
        lambda _candidate_id, _idempotency_key: "bad comment:with spaces",
    )
    outputs, manifest, paths = run_mocked_real(tmp_path, monkeypatch, fake)
    send_snapshot = read_json(outputs["send_result_snapshot"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_invalid_order_send_payload"
    assert manifest["order_send_called"] is False
    assert manifest["order_send_call_count"] == 0
    assert manifest["future_state_json_written"] is False
    assert not paths["future_state"].exists()
    assert manifest["comment_broker_safe"] is False
    assert manifest["comment_length"] > pilot.BROKER_COMMENT_MAX_LENGTH
    assert send_snapshot["comment_broker_safe"] is False
    assert send_snapshot["comment_length"] > pilot.BROKER_COMMENT_MAX_LENGTH
    assert send_snapshot["order_send_result_category"] == "not_called"
    assert send_snapshot["raw_executable_payload_written"] is False
    assert fake.order_send_call_count == 0
    assert fake.last_send_parameters is None


def test_success_placed_with_matching_pending_order_reconciles_matched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(retcode=FakeMT5.TRADE_RETCODE_PLACED, post_orders=[matching_order()]),
    )
    snapshot = read_json(outputs["reconciliation_snapshot"])
    state = read_json(paths["future_state"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_success_placed_reconciliation_required"
    assert manifest["order_send_call_count"] == 1
    assert manifest["reconciliation_status"] == "broker_local_reconciliation_matched_after_send"
    assert manifest["state_status"] == "broker_pending_order_detected"
    assert manifest["broker_position_detected_after_send"] is False
    assert manifest["broker_pending_order_detected_after_send"] is True
    assert state["state_status"] == "broker_pending_order_detected"
    assert snapshot["matching_pending_order_count"] == 1
    assert snapshot["orders"][0]["matched_expected_state"] is True


def test_partial_fill_with_matching_position_reconciles_matched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(retcode=FakeMT5.TRADE_RETCODE_DONE_PARTIAL, post_positions=[matching_position()]),
    )
    snapshot = read_json(outputs["reconciliation_snapshot"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_uncertain_reconciliation_hold"
    assert manifest["order_send_result_category"] == "partial_fill"
    assert manifest["reconciliation_status"] == "broker_local_reconciliation_matched_after_send"
    assert manifest["state_status"] == "broker_position_detected"
    assert snapshot["matching_position_count"] == 1


def test_success_with_no_post_send_state_goes_to_reconciliation_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, paths = run_mocked_real(tmp_path, monkeypatch, FakeMT5(retcode=FakeMT5.TRADE_RETCODE_DONE))
    snapshot = read_json(outputs["reconciliation_snapshot"])
    state = read_json(paths["future_state"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_success_deal_reconciliation_required"
    assert manifest["order_send_call_count"] == 1
    assert manifest["reconciliation_status"] == "broker_local_reconciliation_missing_after_claimed_success"
    assert manifest["state_status"] == "reconciliation_hold"
    assert manifest["broker_position_count_after_send"] == 0
    assert manifest["broker_pending_order_count_after_send"] == 0
    assert state["state_status"] == "reconciliation_hold"
    assert snapshot["broker_position_count_after_send"] == 0
    assert snapshot["broker_pending_order_count_after_send"] == 0


def test_reject_sends_exactly_once_and_never_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(tmp_path, monkeypatch, FakeMT5(retcode=FakeMT5.TRADE_RETCODE_REJECT))
    evidence = read_csv(outputs["no_order_evidence"])[0]
    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_rejected_no_retry"
    assert manifest["order_send_call_count"] == 1
    assert manifest["reconciliation_status"] == "broker_local_reconciliation_clean_after_reject_no_broker_state"
    assert manifest["state_status"] == "execution_rejected"
    assert evidence["no_order_execution_retry_performed"] == "true"


def test_client_autotrading_disabled_is_confirmed_no_send_reject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeMT5(
        retcode=FakeMT5.TRADE_RETCODE_CLIENT_DISABLES_AT,
        result_comment="AutoTrading disabled by client",
    )
    outputs, manifest, paths = run_mocked_real(tmp_path, monkeypatch, fake)
    send_snapshot = read_json(outputs["send_result_snapshot"])
    reconciliation = read_json(outputs["reconciliation_snapshot"])
    state = read_json(paths["future_state"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_client_autotrading_disabled_no_send_confirmed"
    assert manifest["order_send_result_category"] == "client_autotrading_disabled"
    assert manifest["order_send_retcode"] == FakeMT5.TRADE_RETCODE_CLIENT_DISABLES_AT
    assert manifest["order_send_retcode_name"] == "TRADE_RETCODE_CLIENT_DISABLES_AT"
    assert manifest["order_send_call_count"] == 1
    assert manifest["order_send_attempt_count"] == 1
    assert manifest["order_execution_performed"] is False
    assert manifest["no_retry_performed"] is True
    assert manifest["reconciliation_status"] == "broker_local_reconciliation_clean_after_client_reject_no_broker_state"
    assert manifest["state_status"] == "send_rejected_no_position_no_order"
    assert "finalize_state_as_send_rejected_no_position_no_order" in manifest["recommended_recovery_action"]
    assert fake.order_send_call_count == 1
    assert send_snapshot["retcode"] == FakeMT5.TRADE_RETCODE_CLIENT_DISABLES_AT
    assert send_snapshot["retcode_name"] == "TRADE_RETCODE_CLIENT_DISABLES_AT"
    assert send_snapshot["comment"] == "AutoTrading disabled by client"
    assert send_snapshot["order_send_result_category"] == "client_autotrading_disabled"
    assert send_snapshot["no_broker_ticket_returned"] is True
    assert reconciliation["broker_position_count_after_send"] == 0
    assert reconciliation["broker_pending_order_count_after_send"] == 0
    assert reconciliation["retry_performed"] is False
    assert reconciliation["second_send_allowed"] is False
    assert state["state_status"] == "send_rejected_no_position_no_order"
    assert state["reconciliation_status"] == "broker_local_reconciliation_clean_after_client_reject_no_broker_state"
    assert state["recommended_recovery_action"] == manifest["recommended_recovery_action"]
    assert state["order_execution_performed"] is False
    assert state["retry_performed"] is False
    assert state["automatic_retry_allowed"] is False
    assert state["crash_recovery_required"] is False


def test_client_autotrading_disabled_with_broker_state_stays_in_hold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(
            retcode=FakeMT5.TRADE_RETCODE_CLIENT_DISABLES_AT,
            result_comment="AutoTrading disabled by client",
            post_positions=[matching_position()],
        ),
    )
    reconciliation = read_json(outputs["reconciliation_snapshot"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_client_autotrading_disabled_no_send_confirmed"
    assert manifest["order_send_result_category"] == "client_autotrading_disabled"
    assert manifest["reconciliation_status"] == "broker_local_reconciliation_unexpected_broker_state_after_client_reject"
    assert manifest["state_status"] == "reconciliation_hold"
    assert reconciliation["broker_position_count_after_send"] == 1


def test_unknown_retcode_remains_uncertain_reconciliation_hold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs, manifest, paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(retcode=19999, result_comment="unknown broker reply"),
    )
    send_snapshot = read_json(outputs["send_result_snapshot"])
    state = read_json(paths["future_state"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_uncertain_reconciliation_hold"
    assert manifest["order_send_result_category"] == "unknown_retcode"
    assert manifest["order_send_call_count"] == 1
    assert manifest["state_status"] == "reconciliation_hold"
    assert send_snapshot["retcode_name"] == ""
    assert state["state_status"] == "reconciliation_hold"


def test_reject_with_unexpected_broker_state_goes_to_reconciliation_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(retcode=FakeMT5.TRADE_RETCODE_REJECT, post_positions=[matching_position()]),
    )
    snapshot = read_json(outputs["reconciliation_snapshot"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_rejected_no_retry"
    assert manifest["reconciliation_status"] == "broker_local_reconciliation_unexpected_broker_state_after_non_success"
    assert manifest["state_status"] == "reconciliation_hold"
    assert manifest["broker_position_detected_after_send"] is True
    assert snapshot["broker_position_count_after_send"] == 1


def test_send_exception_routes_to_hold_and_no_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(tmp_path, monkeypatch, FakeMT5(send_exception=RuntimeError("mocked failure")))
    snapshot = read_json(outputs["reconciliation_snapshot"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_order_send_exception_reconciliation_hold"
    assert manifest["state_status"] == "reconciliation_hold"
    assert manifest["order_send_call_count"] == 1
    assert manifest["post_send_reconciliation_performed"] is True
    assert snapshot["post_send_reconciliation_performed"] is True


def test_result_none_routes_to_hold_and_no_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(result_none=True, post_positions=[matching_position()]),
    )
    snapshot = read_json(outputs["reconciliation_snapshot"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_uncertain_reconciliation_hold"
    assert manifest["order_send_result_category"] == "result_none"
    assert manifest["order_send_call_count"] == 1
    assert manifest["reconciliation_status"] == "broker_local_reconciliation_unexpected_broker_state_after_non_success"
    assert manifest["state_status"] == "reconciliation_hold"
    assert snapshot["broker_position_detected_after_send"] is True


def test_timeout_routes_to_hold_and_no_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(tmp_path, monkeypatch, FakeMT5(send_exception=TimeoutError("mocked timeout")))
    snapshot = read_json(outputs["reconciliation_snapshot"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_uncertain_reconciliation_hold"
    assert manifest["order_send_result_category"] == "timeout"
    assert manifest["order_send_call_count"] == 1
    assert manifest["post_send_reconciliation_performed"] is True
    assert manifest["state_status"] == "reconciliation_hold"
    assert snapshot["post_send_reconciliation_performed"] is True


def test_post_send_positions_get_failure_goes_to_unavailable_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(post_positions_exception=RuntimeError("positions unavailable")),
    )
    snapshot = read_json(outputs["reconciliation_snapshot"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_unavailable_after_send"
    assert manifest["state_status"] == "reconciliation_hold"
    assert manifest["post_send_positions_get_call_count"] == 1
    assert manifest["post_send_orders_get_call_count"] == 0
    assert "positions_get_failed" in snapshot["query_error"]


def test_post_send_orders_get_failure_goes_to_unavailable_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(post_orders_exception=RuntimeError("orders unavailable")),
    )
    snapshot = read_json(outputs["reconciliation_snapshot"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_unavailable_after_send"
    assert manifest["state_status"] == "reconciliation_hold"
    assert manifest["post_send_positions_get_call_count"] == 1
    assert manifest["post_send_orders_get_call_count"] == 1
    assert "orders_get_failed" in snapshot["query_error"]


def test_multiple_post_send_positions_goes_to_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(post_positions=[matching_position(ticket=9001), matching_position(ticket=9002)]),
    )

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_multiple_states_after_send"
    assert manifest["state_status"] == "reconciliation_hold"
    assert manifest["broker_position_count_after_send"] == 2


def test_multiple_post_send_orders_goes_to_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(post_orders=[matching_order(ticket=7001), matching_order(ticket=7002)]),
    )

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_multiple_states_after_send"
    assert manifest["state_status"] == "reconciliation_hold"
    assert manifest["broker_pending_order_count_after_send"] == 2


def test_post_send_side_mismatch_goes_to_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(post_positions=[matching_position(type="buy")]),
    )
    snapshot = read_json(outputs["reconciliation_snapshot"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_mismatch_after_send"
    assert manifest["state_status"] == "reconciliation_hold"
    assert "side_mismatch" in snapshot["mismatch_reasons"]


def test_post_send_volume_mismatch_goes_to_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(post_positions=[matching_position(volume=0.08)]),
    )
    snapshot = read_json(outputs["reconciliation_snapshot"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_mismatch_after_send"
    assert manifest["state_status"] == "reconciliation_hold"
    assert "volume_mismatch" in snapshot["mismatch_reasons"]


def test_post_send_sl_tp_mismatch_goes_to_hold_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(post_positions=[matching_position(sl=1.2602, tp=1.2348)]),
    )
    snapshot = read_json(outputs["reconciliation_snapshot"])

    assert manifest["reconciliation_status"] == "broker_local_reconciliation_mismatch_after_send"
    assert manifest["state_status"] == "reconciliation_hold"
    assert "sl_mismatch" in snapshot["mismatch_reasons"]
    assert "tp_mismatch" in snapshot["mismatch_reasons"]


def test_no_second_send_on_rerun_with_active_idempotency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMT5()
    _outputs, first_manifest, paths = run_mocked_real(tmp_path, monkeypatch, fake)
    assert first_manifest["order_send_call_count"] == 1
    second_args = args_for(tmp_path, paths, *real_args())
    second_args.output_dir = tmp_path / "out-second"
    second_outputs = pilot.build_outputs(second_args)
    second_manifest = read_json(second_outputs["manifest"])
    assert second_manifest["order_send_pilot_status"] == "order_send_pilot_blocked_existing_active_idempotency_key"
    assert fake.order_send_call_count == 1


def test_client_reject_flat_second_send_without_specific_ack_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_sources(
        tmp_path,
        future_state_payload=client_reject_flat_state(),
        request_payload=module_validation_request_manifest(),
        readiness_payload=module_validation_readiness_manifest(),
    )
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *demo_module_validation_args()))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_client_reject_resend_acknowledgment"
    assert manifest["explicit_second_demo_send_after_client_reject_flat"] is False
    assert manifest["previous_send_retcode"] == pilot.CLIENT_AUTOTRADING_DISABLED_RETCODE
    assert manifest["previous_state_status"] == "send_rejected_no_position_no_order"
    assert manifest["automatic_retry_allowed"] is False
    assert manifest["retry_performed"] is False
    assert fake.order_send_call_count == 0


def test_client_reject_flat_second_demo_send_with_ack_calls_send_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_sources(
        tmp_path,
        future_state_payload=client_reject_flat_state(),
        request_payload=module_validation_request_manifest(),
        readiness_payload=module_validation_readiness_manifest(),
    )
    fake = install_fake(
        monkeypatch,
        FakeMT5(state_path=paths["future_state"], retcode=FakeMT5.TRADE_RETCODE_DONE, post_positions=[matching_position()]),
    )
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *client_reject_resend_args()))
    manifest = read_json(outputs["manifest"])
    state = read_json(paths["future_state"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_sent_success_deal_reconciliation_required"
    assert manifest["explicit_second_demo_send_after_client_reject_flat"] is True
    assert manifest["previous_send_retcode"] == pilot.CLIENT_AUTOTRADING_DISABLED_RETCODE
    assert manifest["previous_state_status"] == "send_rejected_no_position_no_order"
    assert manifest["new_operator_authorized_attempt"] is True
    assert manifest["automatic_retry_allowed"] is False
    assert manifest["retry_performed"] is False
    assert manifest["order_send_call_count"] == 1
    assert fake.order_send_call_count == 1
    assert state["previous_send_retcode"] == pilot.CLIENT_AUTOTRADING_DISABLED_RETCODE
    assert state["previous_state_status"] == "send_rejected_no_position_no_order"
    assert state["previous_send_attempt_id"] == "previous-send"
    assert state["new_operator_authorized_attempt"] is True


def test_client_reject_flat_second_send_blocks_when_autotrading_still_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_sources(
        tmp_path,
        future_state_payload=client_reject_flat_state(),
        request_payload=module_validation_request_manifest(),
        readiness_payload=module_validation_readiness_manifest(),
    )
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"], trade_allowed=False))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *client_reject_resend_args()))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_client_reject_resend_autotrading_disabled"
    assert manifest["order_send_called"] is False
    assert fake.order_send_call_count == 0


def test_client_reject_flat_second_send_blocks_if_state_is_reconciliation_hold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_sources(
        tmp_path,
        future_state_payload=client_reject_flat_state(state_status="reconciliation_hold"),
    )
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *client_reject_resend_args()))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_existing_active_idempotency_key"
    assert fake.order_send_call_count == 0


def test_client_reject_flat_second_send_blocks_if_broker_position_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_sources(
        tmp_path,
        future_state_payload=client_reject_flat_state(),
        reconciliation_payload=reconciliation_manifest(
            reconciliation_status="broker_local_reconciliation_hold_local_missing_broker_open",
            broker_position_count_symbol=1,
        ),
    )
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *client_reject_resend_args()))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_broker_local_reconciliation"
    assert fake.order_send_call_count == 0


def test_client_reject_flat_second_send_blocks_if_pending_order_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_sources(
        tmp_path,
        future_state_payload=client_reject_flat_state(),
        reconciliation_payload=reconciliation_manifest(
            reconciliation_status="broker_local_reconciliation_hold_broker_pending_order_detected",
            broker_pending_order_count_symbol=1,
        ),
    )
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *client_reject_resend_args()))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_broker_local_reconciliation"
    assert fake.order_send_call_count == 0


def test_client_reject_flat_second_send_blocks_if_previous_execution_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_sources(
        tmp_path,
        future_state_payload=client_reject_flat_state(order_execution_performed=True),
    )
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *client_reject_resend_args()))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_existing_active_idempotency_key"
    assert fake.order_send_call_count == 0


def test_client_reject_flat_second_send_blocks_if_idempotency_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_sources(
        tmp_path,
        future_state_payload=client_reject_flat_state(idempotency_key="other-idem"),
    )
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *client_reject_resend_args()))
    manifest = read_json(outputs["manifest"])

    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_future_state_incompatible"
    assert fake.order_send_call_count == 0


def test_state_claim_failure_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"]))

    def fail_write(_path: Path, _value: dict[str, object]) -> None:
        raise OSError("mocked state failure")

    monkeypatch.setattr(pilot, "atomic_write_json", fail_write)
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args()))
    manifest = read_json(outputs["manifest"])
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_state_claim_failed"
    assert fake.order_send_call_count == 0


def test_second_pre_send_state_write_failure_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"]))
    original = pilot.atomic_write_json
    call_count = 0

    def fail_second_write(path: Path, value: dict[str, object]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("mocked second pre-send write failure")
        original(path, value)

    monkeypatch.setattr(pilot, "atomic_write_json", fail_second_write)
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args()))
    manifest = read_json(outputs["manifest"])
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_state_claim_failed"
    assert fake.order_send_call_count == 0


def test_existing_exclusive_claim_lock_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    lock_path = paths["future_state"].with_name(f"{paths['future_state'].name}.pilot.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("other-run", encoding="utf-8")
    fake = install_fake(monkeypatch, FakeMT5(state_path=paths["future_state"]))
    outputs = pilot.build_outputs(args_for(tmp_path, paths, *real_args()))
    manifest = read_json(outputs["manifest"])
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_state_claim_failed"
    assert fake.order_send_call_count == 0


def test_pre_send_state_exists_before_mocked_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMT5()
    _outputs, _manifest, _paths = run_mocked_real(tmp_path, monkeypatch, fake)
    assert fake.state_existed_before_send is True


def test_state_is_updated_after_mocked_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, paths = run_mocked_real(
        tmp_path,
        monkeypatch,
        FakeMT5(post_positions=[matching_position()]),
    )
    state = read_json(paths["future_state"])
    assert state["state_status"] == "broker_position_detected"
    assert state["reconciliation_status"] == "broker_local_reconciliation_matched_after_send"
    assert state["last_retcode"] == FakeMT5.TRADE_RETCODE_DONE
    assert manifest["future_state_json_written"] is True


def test_bounded_pre_and_post_positions_and_orders_reads_once_each(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMT5()
    _outputs, manifest, _paths = run_mocked_real(tmp_path, monkeypatch, fake)
    assert fake.positions_get_call_count == 2
    assert fake.orders_get_call_count == 2
    assert manifest["post_send_positions_get_call_count"] == 1
    assert manifest["post_send_orders_get_call_count"] == 1
    assert manifest["order_send_call_count"] == 1


def test_broker_open_position_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMT5(positions=[SimpleNamespace(symbol="GBPUSD")])
    _outputs, manifest, _paths = run_mocked_real(tmp_path, monkeypatch, fake)
    assert manifest["order_send_pilot_status"] == "order_send_pilot_blocked_broker_local_reconciliation"
    assert fake.order_send_call_count == 0


def test_payload_preview_is_non_executable_and_no_payload_file_exists(tmp_path: Path) -> None:
    outputs, manifest, _paths = build(tmp_path)
    rows = read_csv(outputs["send_payload_preview"])
    assert rows
    assert all(row["persisted_executable_field"] == "false" for row in rows)
    assert manifest["broker_payload_written"] is False
    assert manifest["executable_order_object_written"] is False
    assert not any("payload.json" in path.name for path in outputs.values())


def test_manifest_records_no_retry_and_no_second_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _paths = run_mocked_real(tmp_path, monkeypatch, FakeMT5())
    assert manifest["no_order_execution_retry_performed"] is True
    assert manifest["no_second_order_send_called"] is True
    assert manifest["no_scheduler_added"] is True
    assert manifest["no_loop_added"] is True
    assert manifest["no_background_task_added"] is True


def test_operator_confirmation_artifact_is_bound_to_current_intent_and_check(tmp_path: Path) -> None:
    outputs, _manifest, _paths = build(tmp_path)
    row = read_csv(outputs["operator_confirmation"])[0]
    assert row["signal_id"] == "signal-live-1"
    assert row["idempotency_key"] == "idem-live-1"
    assert row["approval_record_id"] == "approval-live-1"
    assert row["request_intent_digest"]
    assert row["order_check_digest"]


def test_static_safety_has_exactly_one_order_send_call_signature() -> None:
    source = Path(pilot.__file__).read_text(encoding="utf-8")
    assert source.count("order_send(") == 1


def test_static_safety_has_no_history_read_call_signatures() -> None:
    source = Path(pilot.__file__).read_text(encoding="utf-8")
    assert "history_orders_get(" not in source
    assert "history_deals_get(" not in source


def test_static_safety_has_no_scheduler_polling_or_background_behavior() -> None:
    source = Path(pilot.__file__).read_text(encoding="utf-8")
    for token in ("while " + "True", "schedule" + ".every", "Background" + "Scheduler", "threading" + ".", "asyncio" + "."):
        assert token not in source


def test_static_safety_does_not_persist_send_parameters() -> None:
    source = Path(pilot.__file__).read_text(encoding="utf-8")
    assert 'write_json(outputs["send_payload' not in source
    assert "json.dumps(send_parameters" not in source


def test_all_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs, _manifest, _paths = build(tmp_path)
    assert all(path.exists() for path in outputs.values())


def test_report_states_default_no_send_boundary(tmp_path: Path) -> None:
    outputs, _manifest, _paths = build(tmp_path)
    report = outputs["report"].read_text(encoding="utf-8")
    assert "Default behavior is dry-run/no-send" in report
    assert "No automatic retry" in report
    assert "No live account is allowed" in report
