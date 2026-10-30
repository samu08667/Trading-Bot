from __future__ import annotations

import re
from pathlib import Path


DOC_PATH = Path("docs/mt5_order_send_demo_only_design_packet.md")
MQ5_DIR = Path("mt5_ea_prototypes")
EA_PATH = MQ5_DIR / "GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5"


def read_doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_design_packet_preserves_historical_boundary_and_current_surface() -> None:
    source = read_doc()
    assert "MT5 OrderSend Demo-Only Design Packet" in source
    assert "Historical design boundary as of the entry OrderSend design phase" in source
    assert "`e9601e0`" in source
    assert "The current EA surface now contains exactly two" in source
    assert "one entry and one lifecycle close" in source
    assert "At that boundary this packet was design only" in source
    assert "`OrderSend`" in source


def test_scope_and_safe_inputs_are_defined() -> None:
    source = read_doc()
    for token in [
        "demo account only",
        "`GBPUSD` only",
        "`M15` only",
        "`gbpusd_short_h10_1_5_off_hours`",
        "InpEnableOrderCheck = false",
        "InpEnableOrderSend = false",
        "InpRequireDemoAccount = true",
        "InpAllowLiveAccount = false",
        "InpMaxOrderSendAttempts = 1",
        'InpFinalSendAcknowledgment = ""',
        'confirm_single_demo_send_only',
    ]:
        assert token in source


def test_gate_sequence_and_pre_send_guards_are_defined() -> None:
    source = read_doc()
    for token in [
        "new closed M15 bar",
        "fresh broker reconciliation",
        "OrderCheck retcode/pass validation",
        "pre-send fresh broker reconciliation",
        "single OrderSend attempt",
        "request hash/digest is unchanged",
        "no previous send attempt exists",
        "Friday entry cutoff is respected",
        "no-weekend-hold policy is respected",
    ]:
        assert token in source


def test_idempotency_logging_state_and_retcode_contracts_are_defined() -> None:
    source = read_doc()
    for token in [
        "deterministic from candidate id",
        "one send attempt per `signal_id`/`attempt_id`",
        "order_send_log.csv",
        "order_send_attempt_count",
        "automatic_retry_allowed",
        "retry_allowed` is always false",
        "send_uncertain_reconciliation_hold",
        "position_closed_friday_forced_flat",
        "OnTradeTransaction",
        "reconciliation_hold",
    ]:
        assert token in source


def test_future_static_guard_requirements_are_defined() -> None:
    source = read_doc()
    for token in [
        "exactly two callable `OrderSend(` matches appear in the send-enabled EA",
        "one entry send",
        "one integrated lifecycle close",
        "`OrderSendAsync` is absent",
        "live account is forbidden",
        "final acknowledgment is required",
        "`OrderCheck` is required before send",
        "`order_send_attempt_count <= 1`",
    ]:
        assert token in source


def test_current_mq5_surface_has_two_reviewed_order_send_calls_only() -> None:
    source = EA_PATH.read_text(encoding="utf-8")
    assert len(re.findall(r"\bOrderSend\s*\(", source)) == 2
    assert "OrderSend(preflight_request, send_result)" in source
    assert "OrderSend(close_request_before_send, close_result)" in source

    for path in MQ5_DIR.glob("*.mq5"):
        if path == EA_PATH:
            continue
        other_source = path.read_text(encoding="utf-8", errors="ignore")
        assert re.search(r"\bOrderSend\s*\(", other_source) is None, path
