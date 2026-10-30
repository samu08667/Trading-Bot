from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import check_fixed_candidate_demo_manual_approval_gate_dry_run as gate


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
        "horizon_bars": 10,
    }
    payload.update(overrides)
    return payload


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
        "max_margin_usage_ratio": 0.7,
        "safety_boundaries": boundaries,
    }


def would_signal(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_would_signal",
        "review_status": "would_signal_review_available_no_order",
        "source_nature": "live_data_shadow_signal",
        "shadow_status": "shadow_signal_detected",
        "manual_review_required": True,
        "actionable_signal": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "time_server": "2026-06-01 22:15:00",
    }
    payload.update(overrides)
    return payload


def margin_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_margin",
        "validation_status": "broker_safe_margin_validation_available",
        "source_nature": "live_data_shadow_signal",
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
        "broker_margin_usage_ratio": 0.27044,
        "margin_calc_volume_lots": 0.07,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
    }
    payload.update(overrides)
    return payload


def duplicate_plan(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_duplicate",
        "plan_status": "duplicate_protection_plan_available_no_order",
        "source_nature": "live_data_shadow_signal",
        "max_open_positions": 1,
        "plan_actionable": False,
    }
    payload.update(overrides)
    return payload


def manual_plan(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_manual_plan",
        "plan_status": "manual_approval_kill_switch_plan_available_no_order",
        "source_nature": "live_data_shadow_signal",
        "manual_approval_performed": False,
        "kill_switch_executed": False,
        "plan_actionable": False,
    }
    payload.update(overrides)
    return payload


def future_request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_future_request",
        "plan_status": "future_request_construction_readiness_plan_available_no_order",
        "source_nature": "live_data_shadow_signal",
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
    }
    payload.update(overrides)
    return payload


def reconciliation(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_recon",
        "reconciliation_status": "broker_local_reconciliation_clean_no_local_no_broker",
        "source_nature": "live_data_shadow_signal",
        "broker_position_count_symbol": 0,
        "broker_pending_order_count_symbol": 0,
        "request_construction_allowed_now": False,
    }
    payload.update(overrides)
    return payload


def freshness_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_freshness",
        "freshness_status": "live_signal_freshness_fresh_current_or_latest_signal",
        "source_nature": "live_data_shadow_signal",
        "is_fresh": True,
        "is_stale": False,
        "bars_elapsed": 0,
        "future_manual_approval_allowed_now": False,
        "request_construction_allowed_now": False,
    }
    payload.update(overrides)
    return payload


def write_fixture_sources(
    tmp_path: Path,
    *,
    registry_payload: dict[str, object] | None = None,
    policy_payload: dict[str, object] | None = None,
    would_payload: dict[str, object] | None = None,
    margin_payload: dict[str, object] | None = None,
    margin_snapshot_payload: dict[str, object] | None = None,
    duplicate_payload: dict[str, object] | None = None,
    manual_payload: dict[str, object] | None = None,
    future_payload: dict[str, object] | None = None,
    recon_payload: dict[str, object] | None = None,
    freshness_payload: dict[str, object] | None = None,
    missing_would: bool = False,
    create_state: bool = False,
) -> dict[str, Path]:
    would_dir = tmp_path / "would"
    margin_dir = tmp_path / "margin"
    duplicate_dir = tmp_path / "duplicate"
    manual_dir = tmp_path / "manual"
    future_dir = tmp_path / "future"
    recon_dir = tmp_path / "recon"
    freshness_dir = tmp_path / "freshness"
    if not missing_would:
        write_json(would_dir / gate.WOULD_SIGNAL_MANIFEST, would_payload or would_signal())
    write_json(margin_dir / gate.MARGIN_MANIFEST, margin_payload or margin_manifest())
    write_json(margin_dir / gate.MARGIN_SNAPSHOT, margin_snapshot_payload or margin_snapshot())
    write_json(duplicate_dir / gate.DUPLICATE_MANIFEST, duplicate_payload or duplicate_plan())
    write_json(manual_dir / gate.MANUAL_PLAN_MANIFEST, manual_payload or manual_plan())
    write_json(future_dir / gate.FUTURE_REQUEST_MANIFEST, future_payload or future_request())
    write_json(recon_dir / gate.BROKER_RECON_MANIFEST, recon_payload or reconciliation())
    write_json(freshness_dir / gate.FRESHNESS_MANIFEST, freshness_payload or freshness_manifest())
    registry = write_json(tmp_path / "config" / "canonical.json", registry_payload or canonical_registry())
    policy = write_json(tmp_path / "config" / "policy.json", policy_payload or demo_policy())
    state = tmp_path / "state" / "future_state.json"
    if create_state:
        write_json(state, {"state": "existing_fixture_state"})
    return {
        "would": would_dir,
        "margin": margin_dir,
        "duplicate": duplicate_dir,
        "manual": manual_dir,
        "future": future_dir,
        "recon": recon_dir,
        "freshness": freshness_dir,
        "registry": registry,
        "policy": policy,
        "state": state,
    }


def make_args(tmp_path: Path, paths: dict[str, Path]) -> object:
    return gate.build_parser().parse_args(
        [
            "--run-id",
            "unit_manual_approval_gate",
            "--would-signal-review-dir",
            str(paths["would"]),
            "--broker-safe-margin-validation-dir",
            str(paths["margin"]),
            "--duplicate-protection-plan-dir",
            str(paths["duplicate"]),
            "--manual-approval-kill-switch-plan-dir",
            str(paths["manual"]),
            "--future-request-readiness-plan-dir",
            str(paths["future"]),
            "--broker-local-reconciliation-dir",
            str(paths["recon"]),
            "--live-signal-freshness-dir",
            str(paths["freshness"]),
            "--canonical-registry",
            str(paths["registry"]),
            "--demo-execution-policy",
            str(paths["policy"]),
            "--future-state-json",
            str(paths["state"]),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def build_and_manifest(tmp_path: Path, paths: dict[str, Path]) -> tuple[dict[str, Path], dict[str, object]]:
    outputs = gate.build_outputs(make_args(tmp_path, paths))
    return outputs, read_json(outputs["manifest"])


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        gate.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_happy_path_produces_passed_non_actionable(tmp_path: Path) -> None:
    outputs, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_passed_non_actionable"
    for key in ["manifest", "report", "gate_checks", "upstream", "operator_checklist", "block_conditions", "audit_preview", "warnings", "no_order"]:
        assert outputs[key].exists()


def test_happy_path_keeps_manual_approval_allowed_false(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))

    assert manifest["manual_approval_allowed_now"] is False


def test_happy_path_keeps_manual_approval_performed_false(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))

    assert manifest["manual_approval_performed"] is False
    assert manifest["no_manual_approval_performed"] is True


def test_happy_path_keeps_request_construction_false(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))

    assert manifest["request_construction_allowed_now"] is False
    assert manifest["broker_request_constructed"] is False
    assert manifest["broker_payload_constructed"] is False
    assert manifest["order_object_constructed"] is False


def test_stale_freshness_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(
        tmp_path,
        freshness_payload=freshness_manifest(
            freshness_status="live_signal_freshness_stale_beyond_horizon",
            is_fresh=False,
            is_stale=True,
            bars_elapsed=11,
        ),
    )
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_stale_signal"


def test_broker_local_reconciliation_not_clean_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, recon_payload=reconciliation(reconciliation_status="broker_local_reconciliation_hold_broker_pending_order_detected"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_broker_local_reconciliation"


def test_margin_validation_above_hard_cap_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(
        tmp_path,
        margin_payload=margin_manifest(broker_margin_usage_ratio=0.71),
        margin_snapshot_payload=margin_snapshot(broker_margin_usage_ratio=0.71),
    )
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_margin_policy"


def test_observed_margin_volume_passes_broker_safe_margin_gate(tmp_path: Path) -> None:
    paths = write_fixture_sources(
        tmp_path,
        margin_payload=margin_manifest(stepped_volume_lots=0.05, broker_margin_usage_ratio=0.19362),
        margin_snapshot_payload=margin_snapshot(margin_calc_volume_lots=0.05, broker_margin_usage_ratio=0.19362),
    )
    outputs, manifest = build_and_manifest(tmp_path, paths)
    margin_gate = next(row for row in read_csv(outputs["gate_checks"]) if row["gate_name"] == "gate_broker_safe_margin")

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_passed_non_actionable"
    assert margin_gate["gate_status"] == "passed"


def test_margin_volume_mismatch_between_manifest_and_snapshot_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(
        tmp_path,
        margin_payload=margin_manifest(stepped_volume_lots=0.05),
        margin_snapshot_payload=margin_snapshot(margin_calc_volume_lots=0.07),
    )
    outputs, manifest = build_and_manifest(tmp_path, paths)
    margin_gate = next(row for row in read_csv(outputs["gate_checks"]) if row["gate_name"] == "gate_broker_safe_margin")

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_margin_policy"
    assert margin_gate["gate_status"] == "failed_blocking"


def test_margin_validation_non_demo_account_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, margin_payload=margin_manifest(account_mode_label="real"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_margin_policy"


def test_margin_validation_spread_outside_policy_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, margin_payload=margin_manifest(spread_within_policy=False))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_margin_policy"


def test_margin_warning_status_below_hard_cap_passes_broker_safe_margin_gate(tmp_path: Path) -> None:
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
    outputs, manifest = build_and_manifest(tmp_path, paths)
    margin_gate = next(row for row in read_csv(outputs["gate_checks"]) if row["gate_name"] == "gate_broker_safe_margin")

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_passed_non_actionable"
    assert margin_gate["gate_status"] == "passed"


def test_duplicate_protection_unavailable_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, duplicate_payload=duplicate_plan(plan_status="hold"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_duplicate_protection"


def test_unsafe_demo_policy_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, policy_payload=demo_policy(order_execution_allowed=True))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_noncanonical_demo_execution_policy"


def test_missing_upstream_artifact_blocks(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, missing_would=True))

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_missing_upstream_artifact"


def test_unacceptable_upstream_status_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, would_payload=would_signal(review_status="hold"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_unacceptable_upstream_status"


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, registry_payload=canonical_registry(symbol="EURUSD"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["gate_status"] == "manual_approval_gate_dry_run_blocked_noncanonical_candidate"


def test_future_state_json_existing_is_recorded_but_not_written(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, create_state=True)
    before = paths["state"].read_text(encoding="utf-8")
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["future_state_json_exists"] is True
    assert manifest["future_state_json_written"] is False
    assert paths["state"].read_text(encoding="utf-8") == before


def test_gate_check_rows_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    names = {row["gate_name"] for row in read_csv(outputs["gate_checks"])}

    assert {"gate_live_signal_review", "gate_broker_safe_margin", "gate_signal_freshness", "gate_no_request_boundary"}.issubset(names)


def test_operator_checklist_preview_rows_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    items = {row["checklist_item"] for row in read_csv(outputs["operator_checklist"])}

    assert "confirm demo account only" in items
    assert "confirm no request construction" in items
    assert all(row["operator_input_requested"] == "false" for row in read_csv(outputs["operator_checklist"]))


def test_block_condition_rows_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    blocks = {row["block_condition"] for row in read_csv(outputs["block_conditions"])}

    assert {"stale signal", "margin above hard cap", "future state mutation attempted", "scheduler/loop/background detected"}.issubset(blocks)


def test_audit_preview_rows_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    audit_fields = {row["audit_field"] for row in read_csv(outputs["audit_preview"])}

    assert {"would_signal_review_run_id", "signal_time_server", "gate_dry_run_run_id", "manual_approval_performed"}.issubset(audit_fields)


def test_no_order_evidence_rows_are_present(tmp_path: Path) -> None:
    outputs, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    evidence = read_csv(outputs["no_order"])[0]

    assert evidence["no_order_execution_performed"] == "true"
    assert evidence["no_order_request_constructed"] == "true"
    assert evidence["no_future_state_json_written"] == "true"
    assert manifest["no_demo_broker_approval_performed"] is True


def test_static_safety_grep_confirms_forbidden_broker_order_calls_absent() -> None:
    source = Path(gate.__file__).read_text(encoding="utf-8")
    forbidden = [
        "Meta" + "Trader5",
        "mt5" + ".",
        "positions_" + "get(",
        "orders_" + "get(",
        "history_orders_" + "get(",
        "history_deals_" + "get(",
        "order_" + "send(",
        "order_" + "check(",
        "order_" + "calc_margin(",
        "order_" + "calc_profit(",
    ]

    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_scheduler_loop_background_markers() -> None:
    source = Path(gate.__file__).read_text(encoding="utf-8")
    forbidden = ["while " + "True", "Background" + "Scheduler", "schedule" + ".every", "threading" + ".", "asyncio" + "."]

    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_real_approval_write_behavior() -> None:
    source = Path(gate.__file__).read_text(encoding="utf-8")
    forbidden = ["input(", "approve_now", "approval_record_created\": true", "future_state_json_written\": true"]

    for token in forbidden:
        assert token not in source
