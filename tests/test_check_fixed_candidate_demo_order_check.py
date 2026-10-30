import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_fixed_candidate_demo_order_check as checker


FUTURE_EXPIRY = "2099-01-01T00:00:00+00:00"
EXPIRED_EXPIRY = "2020-01-01T00:00:00+00:00"
DEMO_MODULE_ORDER_CHECK_ARGS = [
    "--allow-real-order-check",
    "--module-validation-demo-execution",
    "--module-validation-acknowledgment",
    checker.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
    "--allow-expired-signal-for-demo-module-validation",
    "--expired-signal-override-acknowledgment",
    checker.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
]
CLIENT_REJECT_RESEND_ORDER_CHECK_ARGS = [
    *DEMO_MODULE_ORDER_CHECK_ARGS,
    "--allow-new-demo-send-after-client-reject-flat",
    "--client-reject-resend-acknowledgment",
    checker.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
]
REQUEST_INTENT_FIELDS = [
    "run_id",
    "candidate_id",
    "symbol",
    "timeframe",
    "direction",
    "side",
    "order_type_intent",
    "volume_lots",
    "entry_reference_price",
    "sl_price",
    "tp_price",
    "risk_amount",
    "risk_percent",
    "broker_margin_estimate",
    "broker_margin_usage_ratio",
    "spread_current_points",
    "signal_time_server",
    "signal_id",
    "idempotency_key",
    "approval_record_id",
    "approval_record_digest",
    "approval_scope",
    "request_construction_mode",
    "broker_payload_constructed",
    "executable_order_object_constructed",
    "order_check_allowed_now",
    "order_send_allowed_now",
    "order_execution_allowed",
]
REQUEST_FIELD_FIELDS = [
    "run_id",
    "field_name",
    "intended_value",
    "source",
    "required_for_future_order_check",
    "broker_payload_field_now",
    "executable_now",
    "safety_note",
]


def created_at_utc(*, minutes_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, content: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def canonical_registry(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
        "horizon_bars": 10,
    }
    content.update(overrides)
    return content


def demo_policy(**boundary_overrides: object) -> dict[str, object]:
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
        "policy_id": "fixture_policy",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
        "safety_boundaries": boundaries,
    }


def request_manifest(status: str = "request_construction_dry_run_available_non_executable", **overrides: object) -> dict[str, object]:
    intent_created = status in {
        "request_construction_dry_run_available_non_executable",
        "request_construction_dry_run_available_with_stale_override_for_demo_module_validation",
    }
    content: dict[str, object] = {
        "request_construction_status": status,
        "created_at_utc": created_at_utc(),
        "request_intent_created": intent_created,
        "broker_payload_constructed": False,
        "executable_order_object_constructed": False,
        "order_check_called": False,
        "order_send_called": False,
        "order_execution_performed": False,
        "order_check_allowed_now": False,
        "order_send_allowed_now": False,
        "request_construction_mode": "dry_run_non_executable"
        if intent_created
        else "fixture_or_blocked_no_intent",
    }
    if status == "request_construction_dry_run_available_with_stale_override_for_demo_module_validation":
        content.update(
            {
                "module_validation_demo_execution": True,
                "stale_override_used": True,
                "strategy_valid": False,
                "production_valid": False,
                "order_check_allowed_for_demo_module_validation_only": True,
                "order_send_allowed_for_demo_module_validation_only": False,
            }
        )
    content.update(overrides)
    return content


def readiness_manifest(status: str = "order_check_readiness_plan_available_no_order_check", **overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "order_check_readiness_status": status,
        "created_at_utc": created_at_utc(),
        "future_order_check_ready": status == "order_check_readiness_plan_available_no_order_check",
        "order_check_allowed_now": False,
        "order_check_callable_future_only": True,
        "order_send_allowed_now": False,
        "order_execution_allowed": False,
        "broker_payload_constructed": False,
        "executable_order_object_constructed": False,
        "order_check_called": False,
        "order_send_called": False,
    }
    content.update(overrides)
    return content


def intent_row(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "run_id": "request_fixture",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "side": "sell",
        "order_type_intent": "market_sell",
        "volume_lots": 0.07,
        "entry_reference_price": 1.25,
        "sl_price": 1.26,
        "tp_price": 1.235,
        "risk_amount": 5.0,
        "risk_percent": 0.5,
        "broker_margin_estimate": 270.0,
        "broker_margin_usage_ratio": 0.27,
        "spread_current_points": 3.0,
        "signal_time_server": "2099-01-01 00:00:00",
        "signal_id": "signal_fixture",
        "idempotency_key": "idem_fixture",
        "approval_record_id": "approval_fixture",
        "approval_record_digest": "a" * 64,
        "approval_scope": "future_request_construction_only",
        "request_construction_mode": "dry_run_non_executable",
        "broker_payload_constructed": "false",
        "executable_order_object_constructed": "false",
        "order_check_allowed_now": "false",
        "order_send_allowed_now": "false",
        "order_execution_allowed": "false",
    }
    content.update(overrides)
    return content


def client_reject_flat_state(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "state_status": "send_rejected_no_position_no_order",
        "last_retcode": checker.CLIENT_AUTOTRADING_DISABLED_RETCODE,
        "order_execution_performed": False,
        "crash_recovery_required": False,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "broker_order_ticket": 0,
        "broker_deal_ticket": 0,
        "broker_position_ticket": "",
        "signal_id": "signal_fixture",
        "idempotency_key": "idem_fixture",
        "send_attempt_id": "previous-send",
        "send_started_at_utc": "2026-06-27T13:10:52+00:00",
        "send_completed_at_utc": "2026-06-27T13:10:53+00:00",
    }
    content.update(overrides)
    return content


def market_closed_flat_state(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "state_status": "execution_rejected",
        "last_retcode": 10018,
        "reconciliation_status": "broker_local_reconciliation_clean_after_reject_no_broker_state",
        "order_execution_performed": False,
        "crash_recovery_required": True,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "broker_order_ticket": 0,
        "broker_deal_ticket": 0,
        "broker_position_ticket": "",
        "broker_position_detected_after_send": False,
        "broker_pending_order_detected_after_send": False,
        "broker_position_count_after_send": 0,
        "broker_pending_order_count_after_send": 0,
        "signal_id": "previous-signal",
        "idempotency_key": "previous-idem",
        "send_attempt_id": "previous-send",
    }
    content.update(overrides)
    return content


def request_field_rows(**overrides: object) -> list[dict[str, object]]:
    rows = []
    for name in ("action_intent", "symbol", "volume", "type_intent", "price_reference", "sl", "tp"):
        row: dict[str, object] = {
            "run_id": "request_fixture",
            "field_name": name,
            "intended_value": "fixture_value",
            "source": "fixture",
            "required_for_future_order_check": "true",
            "broker_payload_field_now": "false",
            "executable_now": "false",
            "safety_note": "descriptor_only",
        }
        row.update(overrides)
        rows.append(row)
    return rows


def readiness_input_rows() -> list[dict[str, object]]:
    rows = []
    for name in ("action_intent", "symbol", "volume", "type_intent", "price_reference", "sl", "tp"):
        rows.append(
            {
                "run_id": "readiness_fixture",
                "field_name": name,
                "intended_value": "fixture_value",
                "source": "fixture",
                "required_for_future_order_check": "true",
                "must_be_rechecked_before_order_check": "true",
                "broker_payload_field_now": "false",
                "executable_now": "false",
                "safety_note": "descriptor_only",
            }
        )
    return rows


def readiness_broker_rows() -> list[dict[str, object]]:
    return [
        {
            "run_id": "readiness_fixture",
            "future_mt5_field": name,
            "mapping_description": "future descriptor",
            "source_or_future_source": "fixture",
            "available_now": "false",
            "requires_broker_read_at_order_check_time": "false",
            "executable_now": "false",
            "safety_note": "descriptor_only",
        }
        for name in ("action", "symbol", "volume", "type", "price", "sl", "tp")
    ]


def pre_recheck_rows() -> list[dict[str, object]]:
    return [
        {
            "run_id": "readiness_fixture",
            "recheck_name": "recheck_signal_freshness",
            "timing": "immediately_before_future_order_check",
            "required": "true",
            "blocking_if_failed": "true",
            "expected_value": "fresh",
            "safety_note": "future recheck",
        }
    ]


def approval_record(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "approval_record_id": "approval_fixture",
        "created_at_utc": created_at_utc(),
        "approval_status": "approved_for_future_request_construction_only",
        "approval_scope": "future_request_construction_only",
        "approval_does_not_execute_order": True,
        "approval_does_not_construct_request": True,
        "approval_requires_final_pre_request_recheck": True,
        "approval_revoked": False,
        "record_hash_or_digest": "a" * 64,
        "approval_expiry_time_utc": FUTURE_EXPIRY,
        "signal_id": "signal_fixture",
        "idempotency_key": "idem_fixture",
    }
    content.update(overrides)
    return content


def schema_manifest() -> dict[str, object]:
    return {
        "schema_status": "manual_approval_record_schema_available_no_order",
        "schema_patch_status": "schema_audit_gaps_closed_no_order",
    }


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


def write_sources(
    tmp_path: Path,
    *,
    request_manifest_payload: dict[str, object] | None = None,
    readiness_manifest_payload: dict[str, object] | None = None,
    approval_payload: dict[str, object] | None = None,
    write_approval: bool = True,
    recon_payload: dict[str, object] | None = None,
    margin_payload: dict[str, object] | None = None,
    freshness_payload: dict[str, object] | None = None,
    duplicate_payload: dict[str, object] | None = None,
    manual_payload: dict[str, object] | None = None,
    registry_payload: dict[str, object] | None = None,
    policy_payload: dict[str, object] | None = None,
    future_state_payload: dict[str, object] | None = None,
) -> dict[str, Path]:
    request_dir = tmp_path / "request"
    readiness_dir = tmp_path / "readiness"
    schema_dir = tmp_path / "schema"
    recon_dir = tmp_path / "recon"
    margin_dir = tmp_path / "margin"
    freshness_dir = tmp_path / "freshness"
    duplicate_dir = tmp_path / "duplicate"
    manual_dir = tmp_path / "manual"
    write_json(tmp_path / "config" / "canonical.json", registry_payload or canonical_registry())
    write_json(tmp_path / "config" / "policy.json", policy_payload or demo_policy())
    write_csv(request_dir / checker.REQUEST_INTENT, [intent_row()], REQUEST_INTENT_FIELDS)
    write_csv(request_dir / checker.REQUEST_FIELDS, request_field_rows(), REQUEST_FIELD_FIELDS)
    request_data = request_manifest_payload or request_manifest()
    request_data.setdefault("request_intent_digest", checker.sha256_file(request_dir / checker.REQUEST_INTENT))
    request_data.setdefault("request_fields_digest", checker.sha256_file(request_dir / checker.REQUEST_FIELDS))
    write_json(request_dir / checker.REQUEST_MANIFEST, request_data)
    write_json(readiness_dir / checker.READINESS_MANIFEST, readiness_manifest_payload or readiness_manifest())
    write_csv(readiness_dir / checker.READINESS_INPUTS, readiness_input_rows(), checker.PREVIEW_FIELDNAMES[:0] + [
        "run_id",
        "field_name",
        "intended_value",
        "source",
        "required_for_future_order_check",
        "must_be_rechecked_before_order_check",
        "broker_payload_field_now",
        "executable_now",
        "safety_note",
    ])
    write_csv(readiness_dir / checker.READINESS_BROKER_FIELDS, readiness_broker_rows(), [
        "run_id",
        "future_mt5_field",
        "mapping_description",
        "source_or_future_source",
        "available_now",
        "requires_broker_read_at_order_check_time",
        "executable_now",
        "safety_note",
    ])
    write_csv(readiness_dir / checker.READINESS_PRE_RECHECKS, pre_recheck_rows(), [
        "run_id",
        "recheck_name",
        "timing",
        "required",
        "blocking_if_failed",
        "expected_value",
        "safety_note",
    ])
    write_json(schema_dir / checker.SCHEMA_MANIFEST, schema_manifest())
    approval_path = tmp_path / "state" / "approval.json"
    if write_approval:
        write_json(approval_path, approval_payload or approval_record())
    write_json(recon_dir / checker.BROKER_RECON_MANIFEST, recon_payload or reconciliation_manifest())
    write_json(margin_dir / checker.MARGIN_MANIFEST, margin_payload or margin_manifest())
    write_json(margin_dir / checker.MARGIN_SNAPSHOT, margin_payload or margin_manifest())
    write_json(freshness_dir / checker.FRESHNESS_MANIFEST, freshness_payload or freshness_manifest())
    write_json(duplicate_dir / checker.DUPLICATE_MANIFEST, duplicate_payload or duplicate_manifest())
    write_json(manual_dir / checker.MANUAL_PLAN_MANIFEST, manual_payload or manual_plan_manifest())
    future_state = tmp_path / "state" / "future_state.json"
    if future_state_payload is not None:
        write_json(future_state, future_state_payload)
    return {
        "request": request_dir,
        "readiness": readiness_dir,
        "approval": approval_path,
        "schema": schema_dir,
        "recon": recon_dir,
        "margin": margin_dir,
        "freshness": freshness_dir,
        "duplicate": duplicate_dir,
        "manual": manual_dir,
        "registry": tmp_path / "config" / "canonical.json",
        "policy": tmp_path / "config" / "policy.json",
        "future_state": future_state,
    }


def args_for(tmp_path: Path, paths: dict[str, Path], *extra: str) -> object:
    argv = [
        "--run-id",
        "order_check_fixture",
        "--request-construction-dry-run-dir",
        str(paths["request"]),
        "--order-check-readiness-plan-dir",
        str(paths["readiness"]),
        "--manual-approval-record-json",
        str(paths["approval"]),
        "--manual-approval-record-schema-dir",
        str(paths["schema"]),
        "--broker-local-reconciliation-dir",
        str(paths["recon"]),
        "--broker-safe-margin-validation-dir",
        str(paths["margin"]),
        "--live-signal-freshness-dir",
        str(paths["freshness"]),
        "--duplicate-protection-plan-dir",
        str(paths["duplicate"]),
        "--manual-approval-kill-switch-plan-dir",
        str(paths["manual"]),
        "--canonical-registry",
        str(paths["registry"]),
        "--demo-execution-policy",
        str(paths["policy"]),
        "--future-state-json",
        str(paths["future_state"]),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    argv.extend(extra)
    return checker.build_parser().parse_args(argv)


def build(tmp_path: Path, *extra: str, **kwargs: object) -> tuple[dict[str, Path], dict[str, object], dict[str, Path]]:
    paths = write_sources(tmp_path, **kwargs)
    outputs = checker.build_outputs(args_for(tmp_path, paths, *extra))
    return outputs, read_json(outputs["manifest"]), paths


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = "demo"
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_SELL = 2
    ORDER_TIME_GTC = 3
    ORDER_FILLING_IOC = 4
    TRADE_RETCODE_DONE = 0
    TRADE_RETCODE_PLACED = 10008

    def __init__(
        self,
        *,
        retcode: int = 0,
        result_comment: str = "fake-result",
        initialize_success: bool = True,
        trade_mode: str = "demo",
        currency: str = "EUR",
        symbol_available: bool = True,
        tick_available: bool = True,
        spread: object = 3,
        raise_on_check: bool = False,
        return_none: bool = False,
        result_without_retcode: bool = False,
        last_error_value: object = (10030, "fake last error"),
        action: object = 1,
        order_type: object = 2,
        type_time: object = 3,
        type_filling: object = 4,
    ) -> None:
        self.TRADE_ACTION_DEAL = action
        self.ORDER_TYPE_SELL = order_type
        self.ORDER_TIME_GTC = type_time
        self.ORDER_FILLING_IOC = type_filling
        self.retcode = retcode
        self.result_comment = result_comment
        self.initialize_success = initialize_success
        self.trade_mode = trade_mode
        self.currency = currency
        self.symbol_available = symbol_available
        self.tick_available = tick_available
        self.spread = spread
        self.raise_on_check = raise_on_check
        self.return_none = return_none
        self.result_without_retcode = result_without_retcode
        self.last_error_value = last_error_value
        self.order_check_calls = 0
        self.order_send_calls = 0
        self.shutdown_calls = 0
        self.last_check_args: dict[str, object] | None = None

    def initialize(self) -> bool:
        return self.initialize_success

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def terminal_info(self) -> object:
        return SimpleNamespace(connected=True)

    def account_info(self) -> object:
        return SimpleNamespace(trade_mode=self.trade_mode, currency=self.currency, equity=1000.0, balance=1000.0)

    def symbol_info(self, _symbol: str) -> object | None:
        if not self.symbol_available:
            return None
        return SimpleNamespace(name="GBPUSD", visible=True, volume_min=0.01, volume_max=100.0, volume_step=0.01, point=0.00001, digits=5, spread=self.spread)

    def symbol_info_tick(self, _symbol: str) -> object | None:
        if not self.tick_available:
            return None
        return SimpleNamespace(bid=1.25, ask=1.2501)

    def order_check(self, check_args: dict[str, object]) -> object | None:
        self.order_check_calls += 1
        self.last_check_args = dict(check_args)
        if self.raise_on_check:
            raise RuntimeError("fake order-check exception")
        if self.return_none:
            return None
        if self.result_without_retcode:
            return SimpleNamespace(comment=self.result_comment, balance=1000.0, equity=1000.0, margin=270.0)
        return SimpleNamespace(retcode=self.retcode, comment=self.result_comment, balance=1000.0, equity=1000.0, margin=270.0)

    def order_send(self, _ignored: object) -> None:
        self.order_send_calls += 1

    def last_error(self) -> object:
        return self.last_error_value


def install_fake_mt5(monkeypatch: pytest.MonkeyPatch, fake: FakeMT5) -> FakeMT5:
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    return fake


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        checker.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_broker_safe_comment_abbreviates_long_values() -> None:
    comment = checker.build_broker_safe_comment(
        "gbpusd_short_h10_1_5_off_hours_demo_extra_long",
        "idempotencykey0123456789",
    )

    assert isinstance(comment, str)
    assert len(comment) <= checker.BROKER_COMMENT_MAX_LENGTH
    assert comment.endswith("456789")
    assert checker.broker_comment_is_safe(comment)


def test_broker_safe_comment_sanitizes_problematic_characters() -> None:
    comment = checker.build_broker_safe_comment(
        "GBP/USD short demo!",
        "idem key:/ç-ABC123!!",
    )

    assert len(comment) <= checker.BROKER_COMMENT_MAX_LENGTH
    assert comment.endswith("abc123")
    assert all(char.isascii() and char.isalnum() for char in comment)
    assert " " not in comment
    assert ":" not in comment
    assert "_" not in comment
    assert checker.broker_comment_is_safe(comment)


def test_fixture_only_request_construction_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(
        tmp_path,
        request_manifest_payload=request_manifest("request_construction_dry_run_fixture_only_no_approval_record"),
    )
    assert manifest["order_check_status"] == "order_check_blocked_fixture_only_no_request_intent"


def test_fixture_only_readiness_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(
        tmp_path,
        readiness_manifest_payload=readiness_manifest("order_check_readiness_plan_fixture_only_no_request_intent"),
    )
    assert manifest["order_check_status"] == "order_check_blocked_fixture_only_no_order_check_readiness"


def test_dry_run_with_valid_non_fixture_artifacts_calls_no_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, "--dry-run")
    assert manifest["order_check_status"] == "order_check_dry_run_no_broker_call"
    assert fake.order_check_calls == 0


def test_real_mode_without_allow_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    args = args_for(tmp_path, paths)
    args.dry_run = False
    outputs = checker.build_outputs(args)
    manifest = read_json(outputs["manifest"])
    assert manifest["order_check_status"] == "order_check_blocked_real_mode_not_allowed"


def test_real_mode_with_mocked_mt5_calls_order_check_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    gates = read_csv(outputs["gate_checks"])
    broker_snapshot = read_json(outputs["broker_snapshot"])
    result_snapshot = read_json(outputs["result_snapshot"])

    assert manifest["order_check_status"] == "order_check_available_passed_no_send"
    assert fake.order_check_calls == 1
    assert manifest["current_broker_spread_points"] == 3.0
    assert manifest["max_spread_points"] == 15.0
    assert manifest["current_spread_within_policy"] is True
    assert manifest["spread_rechecked_immediately_before_order_check"] is True
    assert broker_snapshot["current_broker_spread_points"] == 3.0
    assert broker_snapshot["current_spread_within_policy"] is True
    assert broker_snapshot["spread_rechecked_immediately_before_order_check"] is True
    assert result_snapshot["current_broker_spread_points"] == 3.0
    assert result_snapshot["current_spread_within_policy"] is True
    assert result_snapshot["spread_rechecked_immediately_before_order_check"] is True
    assert result_snapshot["payload_required_fields_present"] is True
    assert result_snapshot["payload_missing_fields"] == []
    assert result_snapshot["payload_redacted_keys"] == checker.ORDER_CHECK_REQUIRED_PAYLOAD_FIELDS
    assert result_snapshot["comment_length"] <= checker.BROKER_COMMENT_MAX_LENGTH
    assert result_snapshot["comment_redacted_preview"]
    assert result_snapshot["comment_broker_safe"] is True
    assert set(fake.last_check_args or {}) == set(checker.ORDER_CHECK_REQUIRED_PAYLOAD_FIELDS)
    assert (fake.last_check_args or {})["action"] == fake.TRADE_ACTION_DEAL
    assert (fake.last_check_args or {})["symbol"] == "GBPUSD"
    assert (fake.last_check_args or {})["volume"] == 0.07
    assert (fake.last_check_args or {})["type"] == fake.ORDER_TYPE_SELL
    assert (fake.last_check_args or {})["price"] == 1.25
    assert (fake.last_check_args or {})["sl"] == 1.26
    assert (fake.last_check_args or {})["tp"] == 1.235
    assert (fake.last_check_args or {})["deviation"] == 10
    assert (fake.last_check_args or {})["magic"] == 151015
    assert checker.broker_comment_is_safe((fake.last_check_args or {})["comment"])
    assert len(str((fake.last_check_args or {})["comment"])) <= checker.BROKER_COMMENT_MAX_LENGTH
    assert (fake.last_check_args or {})["type_time"] == fake.ORDER_TIME_GTC
    assert (fake.last_check_args or {})["type_filling"] == fake.ORDER_FILLING_IOC
    assert any(
        row["check_name"] == "current_broker_spread_immediate_recheck"
        and row["gate_status"] == "passed"
        and row["observed_value"] == "3.0"
        and row["expected_value"] == "<= 15.0"
        and row["blocking_if_failed"] == "true"
        for row in gates
    )
    assert manifest["digest_binding_required"] is True
    assert manifest["digest_binding_verified"] is True
    assert manifest["order_check_result_digest"]
    assert manifest["order_check_manifest_digest"]


def test_real_mode_missing_request_intent_digest_blocks_before_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    request_data = request_manifest()
    request_data["request_intent_digest"] = ""
    outputs, manifest, _paths = build(
        tmp_path,
        "--allow-real-order-check",
        request_manifest_payload=request_data,
    )
    evidence = read_csv(outputs["no_order"])[0]

    assert manifest["order_check_status"] == "order_check_blocked_missing_digest_binding"
    assert manifest["digest_binding_verified"] is False
    assert manifest["missing_digest_count"] == 1
    assert manifest["order_check_call_count"] == 0
    assert fake.order_check_calls == 0
    assert evidence["no_mt5_import_performed"] == "true"


def test_real_mode_approval_digest_mismatch_blocks_before_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        "--allow-real-order-check",
        approval_payload=approval_record(record_hash_or_digest="b" * 64),
    )

    assert manifest["order_check_status"] == "order_check_blocked_digest_mismatch"
    assert manifest["digest_binding_verified"] is False
    assert manifest["digest_mismatch_count"] == 1
    assert manifest["order_check_call_count"] == 0
    assert fake.order_check_calls == 0


def test_real_mode_high_current_spread_blocks_before_order_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5(spread=16))
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    gates = read_csv(outputs["gate_checks"])
    broker_snapshot = read_json(outputs["broker_snapshot"])
    result_snapshot = read_json(outputs["result_snapshot"])

    assert manifest["order_check_status"] == "order_check_blocked_current_spread_policy"
    assert manifest["order_check_called"] is False
    assert manifest["order_check_call_count"] == 0
    assert manifest["current_broker_spread_points"] == 16.0
    assert manifest["max_spread_points"] == 15.0
    assert manifest["current_spread_within_policy"] is False
    assert manifest["spread_rechecked_immediately_before_order_check"] is True
    assert fake.order_check_calls == 0
    assert broker_snapshot["current_broker_spread_points"] == 16.0
    assert broker_snapshot["current_spread_within_policy"] is False
    assert result_snapshot["blocked_before_order_check"] is True
    assert result_snapshot["current_broker_spread_points"] == 16.0
    assert any(
        row["check_name"] == "current_broker_spread_immediate_recheck"
        and row["gate_status"] == "failed"
        and row["observed_value"] == "16.0"
        and row["expected_value"] == "<= 15.0"
        and row["warning_code"] == "order_check_blocked_current_spread_policy"
        and row["blocking_if_failed"] == "true"
        for row in gates
    )


def test_real_mode_missing_current_spread_blocks_before_order_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5(spread=None))
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    gates = read_csv(outputs["gate_checks"])
    broker_snapshot = read_json(outputs["broker_snapshot"])
    result_snapshot = read_json(outputs["result_snapshot"])

    assert manifest["order_check_status"] == "order_check_blocked_current_spread_unavailable"
    assert manifest["order_check_call_count"] == 0
    assert manifest["current_broker_spread_points"] == ""
    assert manifest["current_spread_within_policy"] is False
    assert manifest["spread_rechecked_immediately_before_order_check"] is True
    assert fake.order_check_calls == 0
    assert broker_snapshot["current_broker_spread_points"] == ""
    assert result_snapshot["blocked_before_order_check"] is True
    assert any(
        row["check_name"] == "current_broker_spread_immediate_recheck"
        and row["gate_status"] == "failed"
        and row["observed_value"] == "unavailable_or_non_numeric"
        and row["warning_code"] == "order_check_blocked_current_spread_unavailable"
        for row in gates
    )


def test_real_mode_non_numeric_current_spread_blocks_before_order_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5(spread="wide"))
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    gates = read_csv(outputs["gate_checks"])

    assert manifest["order_check_status"] == "order_check_blocked_current_spread_unavailable"
    assert manifest["order_check_call_count"] == 0
    assert manifest["current_broker_spread_points"] == ""
    assert manifest["current_spread_within_policy"] is False
    assert manifest["spread_rechecked_immediately_before_order_check"] is True
    assert fake.order_check_calls == 0
    assert any(
        row["check_name"] == "current_broker_spread_immediate_recheck"
        and row["gate_status"] == "failed"
        and row["observed_value"] == "unavailable_or_non_numeric"
        for row in gates
    )


def test_stale_request_construction_artifact_blocks_real_order_check_before_mt5_import(tmp_path: Path) -> None:
    outputs, manifest, _paths = build(
        tmp_path,
        "--allow-real-order-check",
        request_manifest_payload=request_manifest(created_at_utc=created_at_utc(minutes_ago=16)),
    )
    evidence = read_csv(outputs["no_order"])[0]
    rows = read_csv(outputs["artifact_freshness"])

    assert manifest["order_check_status"] == "order_check_blocked_stale_upstream_artifact"
    assert manifest["order_check_called"] is False
    assert evidence["no_mt5_import_performed"] == "true"
    assert any(row["artifact_name"] == "request_construction" and row["status"] == "stale" for row in rows)


def test_missing_timestamp_blocks_real_order_check_before_mt5_import(tmp_path: Path) -> None:
    payload = request_manifest()
    payload.pop("created_at_utc")
    outputs, manifest, _paths = build(
        tmp_path,
        "--allow-real-order-check",
        request_manifest_payload=payload,
    )
    evidence = read_csv(outputs["no_order"])[0]
    rows = read_csv(outputs["artifact_freshness"])

    assert manifest["order_check_status"] == "order_check_blocked_stale_upstream_artifact"
    assert evidence["no_mt5_import_performed"] == "true"
    assert any(row["artifact_name"] == "request_construction" and row["status"] == "missing_timestamp" for row in rows)


def test_dry_run_stale_artifact_records_warning_without_mt5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    outputs, manifest, _paths = build(
        tmp_path,
        "--dry-run",
        request_manifest_payload=request_manifest(created_at_utc=created_at_utc(minutes_ago=16)),
    )
    warnings = read_csv(outputs["warnings"])
    rows = read_csv(outputs["artifact_freshness"])

    assert manifest["order_check_status"] == "order_check_dry_run_no_broker_call"
    assert fake.order_check_calls == 0
    assert any(row["status"] == "stale" and row["blocking_if_stale"] == "false" for row in rows)
    assert any(row["warning_code"] == "stale_upstream_artifact_warning" and row["blocking_warning"] == "false" for row in warnings)


def test_real_mode_never_calls_order_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    assert manifest["order_send_called"] is False
    assert fake.order_send_calls == 0


def test_real_mode_writes_no_future_state_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, paths = build(tmp_path, "--allow-real-order-check")
    assert manifest["future_state_json_written"] is False
    assert not paths["future_state"].exists()


def test_real_mode_does_not_write_executable_request_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_mt5(monkeypatch, FakeMT5())
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    preview = read_csv(outputs["payload_preview"])
    result = read_json(outputs["result_snapshot"])
    assert manifest["broker_payload_written"] is False
    assert all(row["executable_now"] == "false" for row in preview)
    assert result["raw_request_payload_written"] is False


def test_order_check_pass_retcode_produces_passed_no_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5(retcode=0))
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    result_snapshot = read_json(outputs["result_snapshot"])
    assert manifest["order_check_status"] == "order_check_available_passed_no_send"
    assert manifest["order_check_passed"] is True
    assert result_snapshot["result_available"] is True
    assert result_snapshot["retcode"] == 0
    assert result_snapshot["comment"] == "fake-result"
    assert fake.order_check_calls == 1
    assert fake.order_send_calls == 0


def test_order_check_fail_retcode_produces_failed_no_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5(retcode=10013, result_comment="invalid stops"))
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    result_snapshot = read_json(outputs["result_snapshot"])
    assert manifest["order_check_status"] == "order_check_available_failed_no_send"
    assert manifest["order_check_passed"] is False
    assert result_snapshot["result_available"] is True
    assert result_snapshot["retcode"] == 10013
    assert result_snapshot["comment"] == "invalid stops"
    assert fake.order_check_calls == 1
    assert fake.order_send_calls == 0


def test_order_check_none_result_records_mt5_last_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(
        monkeypatch,
        FakeMT5(return_none=True, last_error_value=(10030, "invalid request")),
    )
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    result_snapshot = read_json(outputs["result_snapshot"])

    assert manifest["order_check_status"] == "order_check_available_failed_no_send"
    assert manifest["order_check_called"] is True
    assert manifest["order_check_call_count"] == 1
    assert manifest["order_check_retcode"] is None
    assert result_snapshot["result_available"] is False
    assert result_snapshot["mt5_last_error"] == [10030, "invalid request"]
    assert result_snapshot["order_check_exception"] is False
    assert result_snapshot["payload_required_fields_present"] is True
    assert result_snapshot["payload_missing_fields"] == []
    assert result_snapshot["payload_redacted_keys"] == checker.ORDER_CHECK_REQUIRED_PAYLOAD_FIELDS
    assert result_snapshot["order_check_result_type"] == "NoneType"
    assert fake.order_check_calls == 1
    assert fake.order_send_calls == 0


def test_order_check_result_without_retcode_records_nonparsable_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install_fake_mt5(
        monkeypatch,
        FakeMT5(result_without_retcode=True, result_comment="missing retcode", last_error_value=(10031, "no retcode")),
    )
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    result_snapshot = read_json(outputs["result_snapshot"])

    assert manifest["order_check_status"] == "order_check_available_failed_no_send"
    assert manifest["order_check_retcode"] is None
    assert result_snapshot["result_available"] is True
    assert result_snapshot["comment"] == "missing retcode"
    assert result_snapshot["mt5_last_error"] == [10031, "no retcode"]
    assert result_snapshot["order_check_result_type"] == "SimpleNamespace"
    assert fake.order_check_calls == 1
    assert fake.order_send_calls == 0


def test_order_check_missing_required_payload_field_blocks_before_mt5_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5(type_filling=None))
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    result_snapshot = read_json(outputs["result_snapshot"])

    assert manifest["order_check_status"] == "order_check_blocked_invalid_order_check_payload"
    assert manifest["order_check_called"] is False
    assert manifest["order_check_call_count"] == 0
    assert result_snapshot["blocked_before_order_check"] is True
    assert result_snapshot["payload_required_fields_present"] is False
    assert result_snapshot["payload_missing_fields"] == ["type_filling"]
    assert result_snapshot["payload_redacted_keys"] == checker.ORDER_CHECK_REQUIRED_PAYLOAD_FIELDS
    assert result_snapshot["raw_request_payload_written"] is False
    assert fake.order_check_calls == 0
    assert fake.order_send_calls == 0


def test_order_check_placeholder_payload_field_blocks_before_mt5_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5(type_time="good_till_cancelled_policy"))
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    result_snapshot = read_json(outputs["result_snapshot"])

    assert manifest["order_check_status"] == "order_check_blocked_invalid_order_check_payload"
    assert manifest["order_check_called"] is False
    assert manifest["order_check_call_count"] == 0
    assert result_snapshot["blocked_before_order_check"] is True
    assert result_snapshot["payload_required_fields_present"] is False
    assert result_snapshot["payload_placeholder_fields"] == ["type_time"]
    assert result_snapshot["raw_request_payload_written"] is False
    assert fake.order_check_calls == 0
    assert fake.order_send_calls == 0


def test_order_check_invalid_comment_blocks_before_mt5_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    monkeypatch.setattr(
        checker,
        "build_broker_safe_comment",
        lambda _candidate_id, _idempotency_key: "bad comment:with spaces",
    )
    outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    result_snapshot = read_json(outputs["result_snapshot"])

    assert manifest["order_check_status"] == "order_check_blocked_invalid_order_check_payload"
    assert manifest["order_check_called"] is False
    assert manifest["order_check_call_count"] == 0
    assert result_snapshot["blocked_before_order_check"] is True
    assert result_snapshot["payload_required_fields_present"] is False
    assert result_snapshot["payload_invalid_fields"] == ["comment"]
    assert result_snapshot["comment_broker_safe"] is False
    assert result_snapshot["comment_length"] > checker.BROKER_COMMENT_MAX_LENGTH
    assert fake.order_check_calls == 0
    assert fake.order_send_calls == 0


def test_missing_approval_record_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, write_approval=False)
    assert manifest["order_check_status"] == "order_check_blocked_missing_approval_record"


def test_expired_approval_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY))
    assert manifest["order_check_status"] == "order_check_blocked_expired_approval"


def test_stale_signal_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(
        tmp_path,
        freshness_payload=freshness_manifest(
            freshness_status="live_signal_freshness_stale_beyond_horizon",
            is_fresh=False,
            is_stale=True,
            bars_elapsed=11,
        ),
    )
    assert manifest["order_check_status"] == "order_check_blocked_stale_signal"


def test_broker_local_reconciliation_hold_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, recon_payload=reconciliation_manifest(reconciliation_status="hold", broker_position_count_symbol=1))
    assert manifest["order_check_status"] == "order_check_blocked_broker_local_reconciliation"


def test_margin_policy_breach_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, margin_payload=margin_manifest(broker_margin_usage_ratio=0.71))
    assert manifest["order_check_status"] == "order_check_blocked_margin_policy"


def test_margin_warning_status_under_hard_cap_passes_dry_run_gate(tmp_path: Path) -> None:
    warning_status = "broker_safe_margin_validation_available_with_margin_warning"
    _outputs, manifest, _paths = build(
        tmp_path,
        margin_payload=margin_manifest(validation_status=warning_status, broker_margin_usage_ratio=0.6),
    )
    assert manifest["order_check_status"] == "order_check_dry_run_no_broker_call"


def test_margin_volume_mismatch_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(
        tmp_path,
        margin_payload=margin_manifest(stepped_volume_lots=0.05, margin_calc_volume_lots=0.07),
    )
    assert manifest["order_check_status"] == "order_check_blocked_margin_policy"


def test_margin_artifact_non_demo_account_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, margin_payload=margin_manifest(account_mode_label="real"))
    assert manifest["order_check_status"] == "order_check_blocked_margin_policy"


def test_margin_spread_outside_policy_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, margin_payload=margin_manifest(spread_within_policy=False))
    assert manifest["order_check_status"] == "order_check_blocked_margin_policy"


def test_request_construction_stale_override_status_requires_demo_module_validation_ack(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(
        tmp_path,
        request_manifest_payload=request_manifest(
            "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
        ),
    )
    assert manifest["order_check_status"] == "order_check_blocked_module_validation_acknowledgment"


def test_request_construction_demo_module_validation_accepts_order_check_with_ack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    outputs, manifest, _paths = build(
        tmp_path,
        *DEMO_MODULE_ORDER_CHECK_ARGS,
        request_manifest_payload=request_manifest(
            "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
        ),
        readiness_manifest_payload=readiness_manifest("order_check_readiness_plan_fixture_only_no_request_intent"),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )
    warnings = read_csv(outputs["warnings"])
    assert manifest["order_check_status"] == "order_check_available_passed_no_send"
    assert manifest["order_check_called"] is True
    assert manifest["order_check_call_count"] == 1
    assert manifest["order_send_called"] is False
    assert manifest["order_execution_performed"] is False
    assert manifest["module_validation_demo_execution"] is True
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False
    assert manifest["expired_signal_override_used"] is True
    assert fake.order_check_calls == 1
    assert fake.order_send_calls == 0
    assert any(
        row["warning_code"] == "order_check_blocked_expired_approval"
        and row["blocking_warning"] == "false"
        for row in warnings
    )


def test_request_construction_demo_module_validation_missing_flag_blocks_before_order_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        "--allow-real-order-check",
        request_manifest_payload=request_manifest(
            "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
        ),
        readiness_manifest_payload=readiness_manifest("order_check_readiness_plan_fixture_only_no_request_intent"),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )
    assert manifest["order_check_status"] == "order_check_blocked_module_validation_acknowledgment"
    assert manifest["order_check_call_count"] == 0
    assert fake.order_check_calls == 0


def test_request_construction_demo_module_validation_non_demo_account_blocks_before_order_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5(trade_mode="real"))
    _outputs, manifest, _paths = build(
        tmp_path,
        *DEMO_MODULE_ORDER_CHECK_ARGS,
        request_manifest_payload=request_manifest(
            "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
        ),
        readiness_manifest_payload=readiness_manifest("order_check_readiness_plan_fixture_only_no_request_intent"),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )
    assert manifest["order_check_status"] == "order_check_blocked_non_demo_account"
    assert manifest["order_check_call_count"] == 0
    assert fake.order_check_calls == 0


@pytest.mark.parametrize(
    ("overrides", "expected_status"),
    [
        ({"freshness_payload": freshness_manifest(freshness_status="live_signal_freshness_stale", is_fresh=False, is_stale=True)}, "order_check_blocked_stale_signal"),
        ({"recon_payload": reconciliation_manifest(reconciliation_status="broker_local_reconciliation_blocked_duplicate_broker_state")}, "order_check_blocked_broker_local_reconciliation"),
        ({"margin_payload": margin_manifest(broker_margin_usage_ratio=0.71)}, "order_check_blocked_margin_policy"),
        ({"duplicate_payload": duplicate_manifest(plan_status="duplicate_protection_plan_blocked_open_position")}, "order_check_blocked_duplicate_protection"),
        ({"manual_payload": manual_plan_manifest(plan_status="manual_approval_kill_switch_plan_blocked")}, "order_check_blocked_kill_switch"),
    ],
)
def test_request_construction_demo_module_validation_does_not_bypass_safety_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    expected_status: str,
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *DEMO_MODULE_ORDER_CHECK_ARGS,
        request_manifest_payload=request_manifest(
            "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
        ),
        readiness_manifest_payload=readiness_manifest("order_check_readiness_plan_fixture_only_no_request_intent"),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
        **overrides,
    )
    assert manifest["order_check_status"] == expected_status
    assert manifest["order_check_call_count"] == 0
    assert fake.order_check_calls == 0


def test_client_reject_flat_second_order_check_without_specific_ack_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *DEMO_MODULE_ORDER_CHECK_ARGS,
        request_manifest_payload=request_manifest(
            "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
        ),
        readiness_manifest_payload=readiness_manifest("order_check_readiness_plan_fixture_only_no_request_intent"),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
        future_state_payload=client_reject_flat_state(),
    )

    assert manifest["order_check_status"] == "order_check_blocked_client_reject_resend_acknowledgment"
    assert manifest["explicit_second_demo_send_after_client_reject_flat"] is False
    assert manifest["previous_state_status"] == "send_rejected_no_position_no_order"
    assert manifest["previous_send_retcode"] == checker.CLIENT_AUTOTRADING_DISABLED_RETCODE
    assert manifest["automatic_retry_allowed"] is False
    assert manifest["retry_performed"] is False
    assert manifest["order_check_call_count"] == 0
    assert fake.order_check_calls == 0
    assert fake.order_send_calls == 0


def test_client_reject_flat_second_order_check_with_ack_calls_order_check_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *CLIENT_REJECT_RESEND_ORDER_CHECK_ARGS,
        request_manifest_payload=request_manifest(
            "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
        ),
        readiness_manifest_payload=readiness_manifest("order_check_readiness_plan_fixture_only_no_request_intent"),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
        future_state_payload=client_reject_flat_state(),
    )

    assert manifest["order_check_status"] == "order_check_available_passed_no_send"
    assert manifest["order_check_called"] is True
    assert manifest["order_check_call_count"] == 1
    assert manifest["explicit_second_demo_send_after_client_reject_flat"] is True
    assert manifest["previous_state_status"] == "send_rejected_no_position_no_order"
    assert manifest["previous_send_retcode"] == checker.CLIENT_AUTOTRADING_DISABLED_RETCODE
    assert manifest["new_operator_authorized_attempt"] is True
    assert manifest["automatic_retry_allowed"] is False
    assert manifest["retry_performed"] is False
    assert fake.order_check_calls == 1
    assert fake.order_send_calls == 0


def test_market_closed_flat_same_signal_blocks_order_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        "--allow-real-order-check",
        future_state_payload=market_closed_flat_state(signal_id="signal_fixture", idempotency_key="idem_fixture"),
    )

    assert manifest["order_check_status"] == "order_check_blocked_future_state_incompatible"
    assert manifest["explicit_new_signal_after_market_closed_flat"] is False
    assert manifest["previous_state_status"] == "execution_rejected"
    assert manifest["previous_send_retcode"] == 10018
    assert manifest["order_check_call_count"] == 0
    assert fake.order_check_calls == 0
    assert fake.order_send_calls == 0


def test_market_closed_flat_new_signal_calls_order_check_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        "--allow-real-order-check",
        future_state_payload=market_closed_flat_state(),
    )

    assert manifest["order_check_status"] == "order_check_available_passed_no_send"
    assert manifest["order_check_called"] is True
    assert manifest["order_check_call_count"] == 1
    assert manifest["explicit_new_signal_after_market_closed_flat"] is True
    assert manifest["previous_state_status"] == "execution_rejected"
    assert manifest["previous_send_retcode"] == 10018
    assert manifest["new_signal_id_differs_from_previous_state"] is True
    assert manifest["new_idempotency_key_differs_from_previous_state"] is True
    assert manifest["automatic_retry_allowed"] is False
    assert manifest["retry_performed"] is False
    assert fake.order_check_calls == 1
    assert fake.order_send_calls == 0


@pytest.mark.parametrize(
    "state_overrides",
    [
        {"state_status": "reconciliation_hold"},
        {"order_execution_performed": True},
        {"crash_recovery_required": True},
        {"idempotency_key": "other-idem"},
        {"automatic_retry_allowed": True},
        {"retry_performed": True},
        {"broker_position_ticket": 9001},
    ],
)
def test_client_reject_flat_second_order_check_blocks_unsafe_prior_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state_overrides: dict[str, object],
) -> None:
    fake = install_fake_mt5(monkeypatch, FakeMT5())
    _outputs, manifest, _paths = build(
        tmp_path,
        *CLIENT_REJECT_RESEND_ORDER_CHECK_ARGS,
        request_manifest_payload=request_manifest(
            "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
        ),
        readiness_manifest_payload=readiness_manifest("order_check_readiness_plan_fixture_only_no_request_intent"),
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
        future_state_payload=client_reject_flat_state(**state_overrides),
    )

    assert manifest["order_check_status"] == "order_check_blocked_future_state_incompatible"
    assert manifest["order_check_call_count"] == 0
    assert fake.order_check_calls == 0
    assert fake.order_send_calls == 0


def test_duplicate_protection_unavailable_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, duplicate_payload=duplicate_manifest(plan_status="hold"))
    assert manifest["order_check_status"] == "order_check_blocked_duplicate_protection"


def test_kill_switch_active_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, manual_payload=manual_plan_manifest(kill_switch_executed=True))
    assert manifest["order_check_status"] == "order_check_blocked_kill_switch"


def test_future_state_incompatible_blocks(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, future_state_payload={"state": "open"})
    assert manifest["order_check_status"] == "order_check_blocked_future_state_incompatible"


def test_non_demo_account_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_mt5(monkeypatch, FakeMT5(trade_mode="real"))
    _outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    assert manifest["order_check_status"] == "order_check_blocked_non_demo_account"


def test_account_currency_mismatch_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_mt5(monkeypatch, FakeMT5(currency="USD"))
    _outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    assert manifest["order_check_status"] == "order_check_blocked_account_currency_mismatch"


def test_symbol_unavailable_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_mt5(monkeypatch, FakeMT5(symbol_available=False))
    _outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    assert manifest["order_check_status"] == "order_check_blocked_symbol_unavailable"


def test_tick_unavailable_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_mt5(monkeypatch, FakeMT5(tick_available=False))
    _outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    assert manifest["order_check_status"] == "order_check_blocked_tick_unavailable"


def test_order_check_exception_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_mt5(monkeypatch, FakeMT5(raise_on_check=True))
    _outputs, manifest, _paths = build(tmp_path, "--allow-real-order-check")
    assert manifest["order_check_status"] == "order_check_blocked_order_check_exception"


def test_manifest_confirms_order_send_called_false(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, "--dry-run")
    assert manifest["order_send_called"] is False


def test_manifest_confirms_order_execution_performed_false(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, "--dry-run")
    assert manifest["order_execution_performed"] is False


def test_manifest_confirms_future_state_json_written_false(tmp_path: Path) -> None:
    _outputs, manifest, _paths = build(tmp_path, "--dry-run")
    assert manifest["future_state_json_written"] is False


def test_no_order_evidence_rows_are_present(tmp_path: Path) -> None:
    outputs, _manifest, _paths = build(tmp_path, "--dry-run")
    evidence = read_csv(outputs["no_order"])[0]
    assert evidence["no_order_send_called"] == "true"
    assert evidence["no_order_execution_performed"] == "true"
    assert evidence["no_future_state_json_written"] == "true"


def test_static_safety_grep_confirms_no_order_send_call_signatures() -> None:
    source = Path(checker.__file__).read_text(encoding="utf-8")
    assert "order_send(" not in source


def test_static_safety_grep_confirms_no_scheduler_loop_background_behavior() -> None:
    source = Path(checker.__file__).read_text(encoding="utf-8")
    forbidden = ["while " + "True", "Background" + "Scheduler", "schedule" + ".every", "threading" + ".", "asyncio" + "."]
    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_executable_payload_written() -> None:
    source = Path(checker.__file__).read_text(encoding="utf-8")
    forbidden = ["request = {", "order_request = {", "broker_payload = {", "payload = {", "write_json(paths[\"payload_preview\"]"]
    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_order_check_only_intended_path() -> None:
    source = Path(checker.__file__).read_text(encoding="utf-8")
    assert source.count(".order_check(") == 1
