from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_manual_approval_record_schema as schema


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


def gate_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_gate",
        "gate_status": "manual_approval_gate_dry_run_passed_non_actionable",
        "source_nature": "live_data_shadow_signal",
        "signal_time_server": "2026-06-01 22:15:00",
        "manual_approval_allowed_now": False,
        "manual_approval_performed": False,
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
        "order_execution_allowed": False,
        "future_state_json_written": False,
    }
    payload.update(overrides)
    return payload


def freshness_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_freshness",
        "freshness_status": "live_signal_freshness_fresh_current_or_latest_signal",
        "is_fresh": True,
        "is_stale": False,
        "bars_elapsed": 0,
        "future_manual_approval_allowed_now": False,
        "request_construction_allowed_now": False,
    }
    payload.update(overrides)
    return payload


def reconciliation_manifest(**overrides: object) -> dict[str, object]:
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


def margin_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_margin",
        "validation_status": "broker_safe_margin_validation_available",
        "source_nature": "live_data_shadow_signal",
        "account_mode_label": "demo",
        "broker_margin_usage_ratio": 0.27044,
        "spread_within_policy": True,
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


def write_fixture_sources(
    tmp_path: Path,
    *,
    registry_payload: dict[str, object] | None = None,
    policy_payload: dict[str, object] | None = None,
    gate_payload: dict[str, object] | None = None,
    freshness_payload: dict[str, object] | None = None,
    recon_payload: dict[str, object] | None = None,
    margin_payload: dict[str, object] | None = None,
    duplicate_payload: dict[str, object] | None = None,
    manual_payload: dict[str, object] | None = None,
    future_payload: dict[str, object] | None = None,
    missing_gate: bool = False,
    create_future_record: bool = False,
    create_state: bool = False,
) -> dict[str, Path]:
    gate_dir = tmp_path / "gate"
    freshness_dir = tmp_path / "freshness"
    recon_dir = tmp_path / "recon"
    margin_dir = tmp_path / "margin"
    duplicate_dir = tmp_path / "duplicate"
    manual_dir = tmp_path / "manual"
    future_dir = tmp_path / "future"
    if not missing_gate:
        write_json(gate_dir / schema.GATE_MANIFEST, gate_payload or gate_manifest())
    write_json(freshness_dir / schema.FRESHNESS_MANIFEST, freshness_payload or freshness_manifest())
    write_json(recon_dir / schema.BROKER_RECON_MANIFEST, recon_payload or reconciliation_manifest())
    write_json(margin_dir / schema.MARGIN_MANIFEST, margin_payload or margin_manifest())
    write_json(margin_dir / schema.MARGIN_SNAPSHOT, {"run_id": "fixture_margin_snapshot"})
    write_json(duplicate_dir / schema.DUPLICATE_MANIFEST, duplicate_payload or duplicate_plan())
    write_json(manual_dir / schema.MANUAL_PLAN_MANIFEST, manual_payload or manual_plan())
    write_json(future_dir / schema.FUTURE_REQUEST_MANIFEST, future_payload or future_request())
    registry = write_json(tmp_path / "config" / "canonical.json", registry_payload or canonical_registry())
    policy = write_json(tmp_path / "config" / "policy.json", policy_payload or demo_policy())
    future_record = tmp_path / "state" / "approval_record.json"
    future_state = tmp_path / "state" / "future_state.json"
    if create_future_record:
        write_json(future_record, {"existing": True})
    if create_state:
        write_json(future_state, {"state": "fixture"})
    return {
        "gate": gate_dir,
        "freshness": freshness_dir,
        "recon": recon_dir,
        "margin": margin_dir,
        "duplicate": duplicate_dir,
        "manual": manual_dir,
        "future": future_dir,
        "registry": registry,
        "policy": policy,
        "future_record": future_record,
        "future_state": future_state,
    }


def make_args(tmp_path: Path, paths: dict[str, Path]) -> object:
    return schema.build_parser().parse_args(
        [
            "--run-id",
            "unit_schema",
            "--manual-approval-gate-dry-run-dir",
            str(paths["gate"]),
            "--live-signal-freshness-dir",
            str(paths["freshness"]),
            "--broker-local-reconciliation-dir",
            str(paths["recon"]),
            "--broker-safe-margin-validation-dir",
            str(paths["margin"]),
            "--duplicate-protection-plan-dir",
            str(paths["duplicate"]),
            "--manual-approval-kill-switch-plan-dir",
            str(paths["manual"]),
            "--future-request-readiness-plan-dir",
            str(paths["future"]),
            "--canonical-registry",
            str(paths["registry"]),
            "--demo-execution-policy",
            str(paths["policy"]),
            "--future-approval-record-json",
            str(paths["future_record"]),
            "--future-state-json",
            str(paths["future_state"]),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def build_and_manifest(tmp_path: Path, paths: dict[str, Path]) -> tuple[dict[str, Path], dict[str, object]]:
    outputs = schema.build_outputs(make_args(tmp_path, paths))
    return outputs, read_json(outputs["manifest"])


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        schema.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_happy_path_produces_schema_available(tmp_path: Path) -> None:
    outputs, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))

    assert manifest["schema_status"] == "manual_approval_record_schema_available_no_order"
    for key in [
        "manifest",
        "report",
        "fields",
        "bindings",
        "expiry",
        "scope",
        "rechecks",
        "blocks",
        "audit",
        "warnings",
        "no_order",
        "allowed_statuses",
        "operator_decisions",
        "post_approval_rechecks",
        "digest_rules",
        "upstream_digests",
        "signal_id_rule",
    ]:
        assert outputs[key].exists()


def test_happy_path_sets_future_approval_record_created_false(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))

    assert manifest["future_approval_record_created"] is False


def test_happy_path_sets_manual_approval_performed_false(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))

    assert manifest["manual_approval_performed"] is False
    assert manifest["no_manual_approval_performed"] is True


def test_happy_path_sets_request_construction_allowed_false(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))

    assert manifest["request_construction_allowed_now"] is False
    assert manifest["broker_request_constructed"] is False
    assert manifest["broker_payload_constructed"] is False
    assert manifest["order_object_constructed"] is False


def test_required_schema_fields_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    field_names = {row["field_name"] for row in read_csv(outputs["fields"])}

    assert {
        "approval_record_id",
        "approval_status",
        "approval_scope",
        "signal_time_server",
        "record_hash_or_digest",
        "bound_upstream_artifact_digests",
        "digest_algorithm",
        "canonical_serialization_rule",
        "operator_decision_label_enum",
        "signal_id_derivation_rule",
        "approval_expiry_formula",
        "post_approval_pre_request_recheck_required",
    }.issubset(field_names)


def test_required_bindings_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    bindings = {row["binding_name"] for row in read_csv(outputs["bindings"])}

    assert {"one signal_time_server", "one idempotency_key", "one broker_safe_margin_validation_run_id", "one candidate_id/symbol/timeframe/direction tuple"}.issubset(bindings)


def test_expiry_revocation_rows_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    rules = {row["rule_name"] for row in read_csv(outputs["expiry"])}

    assert {"explicit_approval_expiry_formula", "expires_after_horizon_bars", "manual_revocation_allowed", "revoked_approval_cannot_be_reused"}.issubset(rules)
    formula = next(row for row in read_csv(outputs["expiry"]) if row["rule_name"] == "explicit_approval_expiry_formula")
    assert "approval_expiry_time_utc = signal_time_server + horizon_bars * timeframe_minutes" in formula["trigger_condition"]
    assert "150" in formula["effect"]


def test_authorization_scope_rows_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    scopes = {row["scope_name"] for row in read_csv(outputs["scope"])}

    assert "future_request_construction_only" in scopes
    assert "approval_does_not_execute_an_order" in scopes
    assert "approval_does_not_authorize_request_construction_unless_post-approval/pre-request_rechecks_pass" in scopes


def test_forbidden_scopes_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    forbidden = {row["scope_name"] for row in read_csv(outputs["scope"]) if row["scope_status"] == "forbidden_scope"}

    assert {"execute_order", "send_order", "bypass_kill_switch", "bypass_margin_policy"}.issubset(forbidden)


def test_pre_approval_recheck_rows_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    rechecks = {row["recheck_name"] for row in read_csv(outputs["rechecks"])}

    assert {"signal still fresh", "broker/local reconciliation still clean", "request construction still disabled until after approval record creation"}.issubset(rechecks)


def test_block_condition_rows_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    blocks = {row["block_condition"] for row in read_csv(outputs["blocks"])}

    assert {
        "stale signal",
        "missing signal_id or idempotency_key",
        "missing_signal_id",
        "missing_idempotency_key",
        "unknown_operator_decision_label",
        "forbidden_operator_decision_label",
        "upstream_artifact_digest_mismatch",
        "digest_algorithm_missing",
        "canonical_serialization_missing",
        "post_approval_pre_request_recheck_missing",
        "approval would imply execution",
    }.issubset(blocks)


def test_allowed_status_artifact_defines_non_execution_statuses(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    statuses = {row["status"]: row for row in read_csv(outputs["allowed_statuses"])}

    assert "approved_for_future_request_construction_only" in statuses
    approved = statuses["approved_for_future_request_construction_only"]
    assert approved["permits_request_construction"] == "conditional_after_final_pre_request_rechecks"
    assert approved["permits_order_execution"] == "false"
    assert statuses["expired"]["terminal"] == "true"
    assert statuses["expired"]["reusable"] == "false"


def test_operator_decision_labels_separate_allowed_and_forbidden_meanings(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    labels = {row["label"]: row for row in read_csv(outputs["operator_decisions"])}

    assert labels["approve_for_future_request_construction_only"]["allowed"] == "true"
    assert labels["approve_for_future_request_construction_only"]["permits_request_construction"] == "conditional_after_final_pre_request_rechecks"
    assert labels["approve_for_future_request_construction_only"]["permits_order_execution"] == "false"
    assert labels["execute_order"]["allowed"] == "false"
    assert labels["send_order"]["permits_order_execution"] == "false"


def test_post_approval_pre_request_rechecks_are_required_and_blocking(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    rechecks = {row["recheck_name"]: row for row in read_csv(outputs["post_approval_rechecks"])}

    assert "recheck_signal_freshness_still_fresh" in rechecks
    assert "recheck_broker_local_reconciliation_clean" in rechecks
    assert "recheck_signal_id_matches_approval_record" in rechecks
    assert all(row["timing"] == "post_approval_pre_request" for row in rechecks.values())
    assert all(row["required"] == "true" and row["blocking_if_failed"] == "true" for row in rechecks.values())


def test_digest_rules_and_upstream_digests_are_written(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    digest_rules = {row["rule_name"]: row for row in read_csv(outputs["digest_rules"])}
    upstream_digests = read_csv(outputs["upstream_digests"])

    assert digest_rules["approval_record_digest_algorithm"]["rule_value"] == "SHA-256"
    assert digest_rules["approval_record_canonical_serialization"]["rule_value"] == "canonical_json_sorted_keys_utf8_no_extra_whitespace"
    assert digest_rules["digest_mismatch_block_rule"]["blocking_if_missing"] == "true"
    assert len(upstream_digests) == 8
    assert all(row["digest_algorithm"] == "SHA-256" for row in upstream_digests)
    assert all(len(row["sha256_digest"]) == 64 for row in upstream_digests)


def test_signal_id_rule_artifact_defines_fallback_and_block_rule(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    rules = {row["rule_name"]: row for row in read_csv(outputs["signal_id_rule"])}

    assert "signal_id_derivation_fallback" in rules
    assert "candidate_id + symbol + timeframe + direction + signal_time_server + entry_reference_price + sl_price + tp_price" in rules["signal_id_derivation_fallback"]["rule_value"]
    assert rules["signal_id_missing_block_rule"]["blocking_if_failed"] == "true"


def test_manifest_records_schema_audit_patch_outputs(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))

    assert manifest["schema_patch_status"] == "schema_audit_gaps_closed_no_order"
    assert manifest["allowed_statuses_artifact_written"] is True
    assert manifest["operator_decision_labels_artifact_written"] is True
    assert manifest["post_approval_pre_request_rechecks_artifact_written"] is True
    assert manifest["digest_rules_artifact_written"] is True
    assert manifest["upstream_artifact_digests_artifact_written"] is True
    assert manifest["signal_id_rule_artifact_written"] is True
    assert manifest["digest_algorithm"] == "SHA-256"
    assert manifest["canonical_serialization"] == "canonical_json_sorted_keys_utf8_no_extra_whitespace"


def test_report_includes_schema_audit_patch_section(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "## Schema Audit Patch" in report
    assert "allowed approval statuses artifact" in report
    assert "post-approval/pre-request rechecks artifact" in report
    assert "schema_audit_gaps_closed_no_order" in report


def test_audit_requirement_rows_are_present(tmp_path: Path) -> None:
    outputs, _ = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    audits = {row["audit_requirement"] for row in read_csv(outputs["audit"])}

    assert "record must be immutable after creation except explicit revocation record" in audits
    assert "record must preserve no-order evidence" in audits


def test_stale_signal_blocks(tmp_path: Path) -> None:
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

    assert manifest["schema_status"] == "blocked_stale_signal"


def test_broker_local_reconciliation_not_clean_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, recon_payload=reconciliation_manifest(reconciliation_status="hold"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["schema_status"] == "blocked_broker_local_reconciliation"


def test_margin_validation_above_hard_cap_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, margin_payload=margin_manifest(broker_margin_usage_ratio=0.71))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["schema_status"] == "blocked_margin_policy"


def test_duplicate_protection_unavailable_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, duplicate_payload=duplicate_plan(plan_status="hold"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["schema_status"] == "blocked_duplicate_protection"


def test_unsafe_demo_policy_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, policy_payload=demo_policy(order_execution_allowed=True))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["schema_status"] == "blocked_noncanonical_demo_execution_policy"


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, registry_payload=canonical_registry(symbol="EURUSD"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["schema_status"] == "blocked_noncanonical_candidate"


def test_future_approval_record_path_is_not_created(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path)
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["future_approval_record_created"] is False
    assert not paths["future_record"].exists()


def test_future_state_json_is_not_written(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, create_state=True)
    before = paths["future_state"].read_text(encoding="utf-8")
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["future_state_json_written"] is False
    assert paths["future_state"].read_text(encoding="utf-8") == before


def test_static_safety_grep_confirms_forbidden_broker_order_calls_absent() -> None:
    source = Path(schema.__file__).read_text(encoding="utf-8")
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
    source = Path(schema.__file__).read_text(encoding="utf-8")
    forbidden = ["while " + "True", "Background" + "Scheduler", "schedule" + ".every", "threading" + ".", "asyncio" + "."]

    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_real_approval_write_behavior() -> None:
    source = Path(schema.__file__).read_text(encoding="utf-8")
    forbidden = ["input(", "approve_now", "approval_record_created\": true", "future_state_json_written\": true"]

    for token in forbidden:
        assert token not in source
