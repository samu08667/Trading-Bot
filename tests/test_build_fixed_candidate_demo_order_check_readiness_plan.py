import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_order_check_readiness_plan as plan


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, content: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
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
        "risk_percent_max": 0.5,
        "risk_amount_max": 5.0,
        "max_margin_usage_ratio": 0.7,
        "safety_boundaries": boundaries,
    }


def request_manifest(status: str = "request_construction_dry_run_available_non_executable", **overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "request_construction_status": status,
        "request_intent_created": status == "request_construction_dry_run_available_non_executable",
        "request_construction_mode": "dry_run_non_executable"
        if status == "request_construction_dry_run_available_non_executable"
        else "fixture_or_blocked_no_intent",
        "broker_payload_constructed": False,
        "executable_order_object_constructed": False,
        "order_check_called": False,
        "order_send_called": False,
        "order_execution_performed": False,
        "future_state_json_written": False,
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
        "broker_payload_constructed": False,
        "executable_order_object_constructed": False,
        "order_check_allowed_now": False,
        "order_send_allowed_now": False,
        "order_execution_allowed": False,
    }
    content.update(overrides)
    return content


def request_field_rows(**overrides: object) -> list[dict[str, object]]:
    rows = []
    for name in ("action_intent", "symbol", "volume", "type_intent", "price_reference", "sl", "tp"):
        row: dict[str, object] = {
            "run_id": "request_fixture",
            "field_name": name,
            "intended_value": "future_value",
            "source": "fixture",
            "required_for_future_order_check": "true",
            "broker_payload_field_now": "false",
            "executable_now": "false",
            "safety_note": "descriptor_only",
        }
        row.update(overrides)
        rows.append(row)
    return rows


def schema_manifest() -> dict[str, object]:
    return {
        "schema_status": "manual_approval_record_schema_available_no_order",
        "schema_patch_status": "schema_audit_gaps_closed_no_order",
    }


def future_request_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "plan_status": "future_request_construction_readiness_plan_available_no_order",
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
    }
    content.update(overrides)
    return content


def reconciliation_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "reconciliation_status": "broker_local_reconciliation_clean_no_local_no_broker",
        "broker_position_count_symbol": 0,
        "broker_pending_order_count_symbol": 0,
    }
    content.update(overrides)
    return content


def margin_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "validation_status": "broker_safe_margin_validation_available",
        "account_mode_label": "demo",
        "broker_margin_usage_ratio": 0.27,
        "broker_margin_estimate": 270.0,
        "spread_within_policy": True,
        "spread_current_points": 3.0,
    }
    content.update(overrides)
    return content


def freshness_manifest(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "freshness_status": "live_signal_freshness_fresh_current_or_latest_signal",
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
        "manual_approval_performed": False,
        "kill_switch_executed": False,
        "plan_actionable": False,
    }
    content.update(overrides)
    return content


def write_sources(
    tmp_path: Path,
    *,
    write_request_manifest: bool = True,
    request_manifest_payload: dict[str, object] | None = None,
    write_request_intent: bool = True,
    intent_payload: dict[str, object] | None = None,
    request_fields_payload: list[dict[str, object]] | None = None,
    registry_payload: dict[str, object] | None = None,
    policy_payload: dict[str, object] | None = None,
    future_request_payload: dict[str, object] | None = None,
    recon_payload: dict[str, object] | None = None,
    margin_payload: dict[str, object] | None = None,
    freshness_payload: dict[str, object] | None = None,
    duplicate_payload: dict[str, object] | None = None,
    manual_payload: dict[str, object] | None = None,
    future_state_payload: dict[str, object] | None = None,
) -> dict[str, Path]:
    request_dir = tmp_path / "request"
    schema_dir = tmp_path / "schema"
    future_dir = tmp_path / "future_request"
    recon_dir = tmp_path / "recon"
    margin_dir = tmp_path / "margin"
    freshness_dir = tmp_path / "freshness"
    duplicate_dir = tmp_path / "duplicate"
    manual_dir = tmp_path / "manual"
    if write_request_manifest:
        write_json(request_dir / plan.REQUEST_MANIFEST, request_manifest_payload or request_manifest())
    if write_request_intent:
        write_csv(request_dir / plan.REQUEST_INTENT, [intent_payload or intent_row()], plan.FUTURE_INPUT_FIELDNAMES[:0] + [
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
        ])
    write_csv(
        request_dir / plan.REQUEST_FIELDS,
        request_fields_payload or request_field_rows(),
        [
            "run_id",
            "field_name",
            "intended_value",
            "source",
            "required_for_future_order_check",
            "broker_payload_field_now",
            "executable_now",
            "safety_note",
        ],
    )
    write_json(schema_dir / plan.SCHEMA_MANIFEST, schema_manifest())
    write_csv(
        schema_dir / plan.SCHEMA_POST_APPROVAL_RECHECKS,
        [{"recheck_name": "freshness", "required": "true", "blocking_if_failed": "true"}],
        ["recheck_name", "required", "blocking_if_failed"],
    )
    write_json(tmp_path / "config" / "canonical.json", registry_payload or canonical_registry())
    write_json(tmp_path / "config" / "policy.json", policy_payload or demo_policy())
    write_json(future_dir / plan.FUTURE_REQUEST_MANIFEST, future_request_payload or future_request_manifest())
    write_json(recon_dir / plan.BROKER_RECON_MANIFEST, recon_payload or reconciliation_manifest())
    write_json(margin_dir / plan.MARGIN_MANIFEST, margin_payload or margin_manifest())
    write_json(margin_dir / plan.MARGIN_SNAPSHOT, margin_payload or margin_manifest())
    write_json(freshness_dir / plan.FRESHNESS_MANIFEST, freshness_payload or freshness_manifest())
    write_json(duplicate_dir / plan.DUPLICATE_MANIFEST, duplicate_payload or duplicate_manifest())
    write_json(manual_dir / plan.MANUAL_PLAN_MANIFEST, manual_payload or manual_plan_manifest())
    approval_path = tmp_path / "state" / "approval.json"
    future_state_path = tmp_path / "state" / "future_state.json"
    if future_state_payload is not None:
        write_json(future_state_path, future_state_payload)
    return {
        "request": request_dir,
        "schema": schema_dir,
        "registry": tmp_path / "config" / "canonical.json",
        "policy": tmp_path / "config" / "policy.json",
        "future": future_dir,
        "recon": recon_dir,
        "margin": margin_dir,
        "freshness": freshness_dir,
        "duplicate": duplicate_dir,
        "manual": manual_dir,
        "approval": approval_path,
        "future_state": future_state_path,
    }


def args_for(tmp_path: Path, paths: dict[str, Path]) -> object:
    return plan.build_parser().parse_args(
        [
            "--run-id",
            "fixture_order_check_plan",
            "--request-construction-dry-run-dir",
            str(paths["request"]),
            "--manual-approval-record-schema-dir",
            str(paths["schema"]),
            "--future-request-readiness-plan-dir",
            str(paths["future"]),
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
            "--future-approval-record-json",
            str(paths["approval"]),
            "--future-state-json",
            str(paths["future_state"]),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def build(tmp_path: Path, **kwargs: object) -> tuple[dict[str, Path], dict[str, object]]:
    paths = write_sources(tmp_path, **kwargs)
    outputs = plan.build_outputs(args_for(tmp_path, paths))
    return outputs, read_json(outputs["manifest"])


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        plan.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_missing_request_construction_artifact_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, write_request_manifest=False)
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_blocked_missing_request_construction"


def test_fixture_only_request_construction_produces_fixture_status(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        request_manifest_payload=request_manifest("request_construction_dry_run_fixture_only_no_approval_record"),
        write_request_intent=False,
    )
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_fixture_only_no_request_intent"
    assert manifest["future_order_check_ready"] is False


def test_valid_non_executable_request_intent_produces_available(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_available_no_order_check"
    assert manifest["future_order_check_ready"] is True


def test_executable_request_intent_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, intent_payload=intent_row(executable_order_object_constructed=True))
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_blocked_request_intent_executable"


def test_missing_request_intent_blocks_for_non_fixture(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, write_request_intent=False)
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_blocked_request_intent_missing"


def test_stale_signal_blocks_non_fixture(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        freshness_payload=freshness_manifest(
            freshness_status="live_signal_freshness_stale_beyond_horizon",
            is_fresh=False,
            is_stale=True,
            bars_elapsed=11,
        ),
    )
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_blocked_stale_signal"


def test_broker_local_hold_blocks_non_fixture(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, recon_payload=reconciliation_manifest(reconciliation_status="hold", broker_position_count_symbol=1))
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_blocked_broker_local_reconciliation"


def test_margin_above_hard_cap_blocks_non_fixture(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, margin_payload=margin_manifest(broker_margin_usage_ratio=0.71))
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_blocked_margin_policy"


def test_duplicate_unavailable_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, duplicate_payload=duplicate_manifest(plan_status="hold"))
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_blocked_duplicate_protection"


def test_kill_switch_active_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, manual_payload=manual_plan_manifest(kill_switch_executed=True))
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_blocked_kill_switch"


def test_future_state_incompatible_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, future_state_payload={"state": "open"})
    assert manifest["order_check_readiness_status"] == "order_check_readiness_plan_blocked_future_state_incompatible"


def test_future_order_check_input_descriptors_written(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["future_inputs"])
    names = {row["field_name"] for row in rows}
    assert {"action_intent", "symbol", "volume", "signal_id", "idempotency_key", "approval_record_id"} <= names


def test_future_broker_request_mappings_written(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["future_broker_fields"])
    names = {row["future_mt5_field"] for row in rows}
    assert {"action", "symbol", "volume", "type", "price", "sl", "tp"} <= names


def test_every_future_broker_row_is_not_executable_now(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["future_broker_fields"])
    assert rows
    assert all(row["executable_now"] == "false" for row in rows)


def test_every_input_descriptor_is_not_payload_now(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["future_inputs"])
    assert rows
    assert all(row["broker_payload_field_now"] == "false" for row in rows)


def test_pre_order_check_rechecks_are_all_required_and_blocking(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    rows = read_csv(outputs["pre_rechecks"])
    assert rows
    assert all(row["required"] == "true" and row["blocking_if_failed"] == "true" for row in rows)


def test_manifest_confirms_order_check_not_called(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)
    assert manifest["order_check_called"] is False


def test_manifest_confirms_order_send_not_called(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)
    assert manifest["order_send_called"] is False


def test_manifest_confirms_broker_payload_not_constructed(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)
    assert manifest["broker_payload_constructed"] is False


def test_manifest_confirms_executable_order_object_not_constructed(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)
    assert manifest["executable_order_object_constructed"] is False


def test_no_future_state_written(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    assert not paths["future_state"].exists()
    outputs = plan.build_outputs(args_for(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    assert manifest["future_state_json_written"] is False
    assert not paths["future_state"].exists()


def test_no_order_evidence_rows_are_present(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    evidence = read_csv(outputs["no_order"])[0]
    assert evidence["no_order_check_called"] == "true"
    assert evidence["no_order_send_called"] == "true"
    assert evidence["no_broker_payload_constructed"] == "true"


def test_static_safety_grep_confirms_no_forbidden_broker_order_history_calls() -> None:
    source = Path(plan.__file__).read_text(encoding="utf-8")
    forbidden = [
        "MetaTrader5",
        "mt5.initialize",
        "positions_get(",
        "orders_get(",
        "history_orders_get(",
        "history_deals_get(",
        "order_send(",
        "order_check(",
        "order_calc_margin(",
        "order_calc_profit(",
    ]
    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_scheduler_loop_background_behavior() -> None:
    source = Path(plan.__file__).read_text(encoding="utf-8")
    forbidden = ["while " + "True", "Background" + "Scheduler", "schedule" + ".every", "threading" + ".", "asyncio" + "."]
    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_executable_request_object_construction() -> None:
    source = Path(plan.__file__).read_text(encoding="utf-8")
    forbidden = ["request = {", "order_request = {", "broker_payload = {", "payload = {", "executable_order_object = {"]
    for token in forbidden:
        assert token not in source
