import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_request_construction_dry_run as dry_run


FUTURE_EXPIRY = "2099-01-01T02:30:00+00:00"
EXPIRED_EXPIRY = "2020-01-01T02:30:00+00:00"


def created_at_utc(*, minutes_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
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
    payload: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
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
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
        "max_open_positions": 1,
        "risk_amount_max": 5.0,
        "risk_percent_max": 0.5,
        "max_margin_usage_ratio": 0.7,
        "safety_boundaries": boundaries,
    }


def approval_record(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "approval_record_id": "approval_fixture",
        "created_at_utc": created_at_utc(),
        "approval_status": "approved_for_future_request_construction_only",
        "approval_scope": "future_request_construction_only",
        "approval_does_not_execute_order": True,
        "approval_does_not_construct_request": True,
        "approval_requires_final_pre_request_recheck": True,
        "approval_revoked": False,
        "record_hash_or_digest": "a" * 64,
        "digest_algorithm": "SHA-256",
        "digest_binding_verified": True,
        "missing_digest_count": 0,
        "digest_mismatch_count": 0,
        "canonical_serialization_rule": "canonical_json_sorted_keys_utf8_no_extra_whitespace",
        "bound_upstream_artifact_digests": {},
        "approval_expiry_time_utc": FUTURE_EXPIRY,
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "signal_time_server": "2099-01-01 00:00:00",
        "operator_decision_label": "approve_for_future_request_construction_only",
        "volume_lots": 0.07,
        "entry_reference_price": 1.25,
        "sl_price": 1.26,
        "tp_price": 1.235,
        "risk_amount": 5.0,
        "risk_percent": 0.5,
        "broker_margin_estimate": 270.0,
        "broker_margin_usage_ratio": 0.27,
        "spread_current_points": 3.0,
    }
    signal_id = dry_run.deterministic_signal_id(payload)
    payload["signal_id"] = signal_id
    payload["idempotency_key"] = signal_id
    payload.update(overrides)
    if "signal_id" not in overrides and "idempotency_key" not in overrides:
        signal_id = dry_run.deterministic_signal_id(payload)
        payload["signal_id"] = signal_id
        payload["idempotency_key"] = signal_id
    return payload


def schema_manifest() -> dict[str, object]:
    return {
        "schema_status": "manual_approval_record_schema_available_no_order",
        "schema_patch_status": "schema_audit_gaps_closed_no_order",
    }


def future_request_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "plan_status": "future_request_construction_readiness_plan_available_no_order",
        "created_at_utc": created_at_utc(),
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
    }
    payload.update(overrides)
    return payload


def reconciliation_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "reconciliation_status": "broker_local_reconciliation_clean_no_local_no_broker",
        "created_at_utc": created_at_utc(),
        "broker_position_count_symbol": 0,
        "broker_pending_order_count_symbol": 0,
    }
    payload.update(overrides)
    return payload


def margin_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "validation_status": "broker_safe_margin_validation_available",
        "created_at_utc": created_at_utc(),
        "source_nature": "live_data_shadow_signal",
        "account_mode_label": "demo",
        "account_currency": "EUR",
        "account_equity_policy_status": "within_10pct",
        "broker_margin_usage_ratio": 0.27,
        "broker_margin_estimate": 270.0,
        "spread_within_policy": True,
        "spread_current_points": 3.0,
        "stepped_volume_lots": 0.07,
    }
    payload.update(overrides)
    return payload


def margin_snapshot(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "validation_status": "broker_safe_margin_validation_available",
        "created_at_utc": created_at_utc(),
        "broker_margin_usage_ratio": 0.27,
        "broker_margin_estimate": 270.0,
        "spread_current_points": 3.0,
        "margin_calc_volume_lots": 0.07,
    }
    payload.update(overrides)
    return payload


def freshness_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "freshness_status": "live_signal_freshness_fresh_current_or_latest_signal",
        "created_at_utc": created_at_utc(),
        "is_fresh": True,
        "is_stale": False,
        "bars_elapsed": 1,
    }
    payload.update(overrides)
    return payload


def duplicate_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "plan_status": "duplicate_protection_plan_available_no_order",
        "max_open_positions": 1,
        "plan_actionable": False,
    }
    payload.update(overrides)
    return payload


def manual_plan_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "plan_status": "manual_approval_kill_switch_plan_available_no_order",
        "manual_approval_performed": False,
        "kill_switch_executed": False,
        "plan_actionable": False,
    }
    payload.update(overrides)
    return payload


def bound_upstream_artifact_digests(paths: dict[str, Path]) -> dict[str, dict[str, str]]:
    specs = {
        "future_request_readiness_plan_manifest": (paths["future_request"], "plan_status", "future_request_construction_readiness_plan_available_no_order"),
        "broker_local_reconciliation_manifest": (paths["reconciliation"], "reconciliation_status", "broker_local_reconciliation_clean_no_local_no_broker"),
        "broker_safe_margin_validation_manifest": (paths["margin"], "validation_status", "broker_safe_margin_validation_available"),
        "broker_safe_margin_validation_margin_snapshot": (paths["margin_snapshot"], "validation_status", "broker_safe_margin_validation_available"),
        "live_signal_freshness_manifest": (paths["freshness"], "freshness_status", "live_signal_freshness_fresh_current_or_latest_signal"),
        "duplicate_protection_plan_manifest": (paths["duplicate"], "plan_status", "duplicate_protection_plan_available_no_order"),
        "manual_approval_kill_switch_plan_manifest": (paths["manual_plan"], "plan_status", "manual_approval_kill_switch_plan_available_no_order"),
    }
    return {
        name: {
            "path": str(path),
            "sha256_digest": dry_run.sha256_file(path),
            "status_field": status_field,
            "status_value": status_value,
        }
        for name, (path, status_field, status_value) in specs.items()
    }


def write_sources(
    tmp_path: Path,
    *,
    approval_payload: dict[str, object] | None = None,
    write_approval: bool = True,
    auto_bind_approval_digests: bool = True,
    registry_payload: dict[str, object] | None = None,
    policy_payload: dict[str, object] | None = None,
    future_request_payload: dict[str, object] | None = None,
    recon_payload: dict[str, object] | None = None,
    margin_payload: dict[str, object] | None = None,
    margin_snapshot_payload: dict[str, object] | None = None,
    freshness_payload: dict[str, object] | None = None,
    duplicate_payload: dict[str, object] | None = None,
    manual_payload: dict[str, object] | None = None,
    future_state_payload: dict[str, object] | None = None,
) -> dict[str, Path]:
    schema_dir = tmp_path / "schema"
    future_dir = tmp_path / "future_request"
    recon_dir = tmp_path / "recon"
    margin_dir = tmp_path / "margin"
    freshness_dir = tmp_path / "freshness"
    duplicate_dir = tmp_path / "duplicate"
    manual_dir = tmp_path / "manual"
    approval_path = tmp_path / "state" / "approval.json"
    registry = write_json(tmp_path / "config" / "canonical.json", registry_payload or canonical_registry())
    policy = write_json(tmp_path / "config" / "policy.json", policy_payload or demo_policy())
    write_json(schema_dir / dry_run.SCHEMA_MANIFEST, schema_manifest())
    write_csv(schema_dir / dry_run.SCHEMA_ALLOWED_STATUSES, [{"status": "approved_for_future_request_construction_only"}], ["status"])
    write_csv(schema_dir / dry_run.SCHEMA_OPERATOR_DECISIONS, [{"label": "approve_for_future_request_construction_only"}], ["label"])
    write_csv(
        schema_dir / dry_run.SCHEMA_POST_APPROVAL_RECHECKS,
        [{"check_name": "freshness", "required": "true", "blocking_if_failed": "true"}],
        ["check_name", "required", "blocking_if_failed"],
    )
    write_csv(
        schema_dir / dry_run.SCHEMA_DIGEST_RULES,
        [{"rule_name": "approval_record_digest_algorithm", "rule_value": "SHA-256"}],
        ["rule_name", "rule_value"],
    )
    future_manifest = write_json(future_dir / dry_run.FUTURE_REQUEST_MANIFEST, future_request_payload or future_request_manifest())
    recon_manifest = write_json(recon_dir / dry_run.BROKER_RECON_MANIFEST, recon_payload or reconciliation_manifest())
    margin_manifest_path = write_json(margin_dir / dry_run.MARGIN_MANIFEST, margin_payload or margin_manifest())
    margin_snapshot_path = write_json(margin_dir / dry_run.MARGIN_SNAPSHOT, margin_snapshot_payload or margin_snapshot())
    freshness = write_json(freshness_dir / dry_run.FRESHNESS_MANIFEST, freshness_payload or freshness_manifest())
    duplicate = write_json(duplicate_dir / dry_run.DUPLICATE_MANIFEST, duplicate_payload or duplicate_manifest())
    manual = write_json(manual_dir / dry_run.MANUAL_PLAN_MANIFEST, manual_payload or manual_plan_manifest())
    future_state = tmp_path / "state" / "future_state.json"
    if future_state_payload is not None:
        write_json(future_state, future_state_payload)
    if write_approval:
        approval = approval_payload or approval_record()
        if auto_bind_approval_digests:
            approval["bound_upstream_artifact_digests"] = bound_upstream_artifact_digests(
                {
                    "future_request": future_manifest,
                    "reconciliation": recon_manifest,
                    "margin": margin_manifest_path,
                    "margin_snapshot": margin_snapshot_path,
                    "freshness": freshness,
                    "duplicate": duplicate,
                    "manual_plan": manual,
                }
            )
            approval["digest_binding_verified"] = True
            approval["missing_digest_count"] = 0
            approval["digest_mismatch_count"] = 0
        write_json(approval_path, approval)
    return {
        "approval": approval_path,
        "schema": schema_dir,
        "registry": registry,
        "policy": policy,
        "future": future_dir,
        "recon": recon_dir,
        "margin": margin_dir,
        "freshness": freshness_dir,
        "duplicate": duplicate_dir,
        "manual": manual_dir,
        "future_state": future_state,
    }


def args_for(tmp_path: Path, paths: dict[str, Path], *extra: str) -> object:
    argv = [
        "--run-id",
        "fixture_dry_run",
        "--manual-approval-record-json",
        str(paths["approval"]),
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
        "--future-state-json",
        str(paths["future_state"]),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    argv.extend(extra)
    return dry_run.build_parser().parse_args(argv)


def build(tmp_path: Path, *extra: str, **kwargs: object) -> tuple[dict[str, Path], dict[str, object]]:
    paths = write_sources(tmp_path, **kwargs)
    outputs = dry_run.build_outputs(args_for(tmp_path, paths, *extra))
    return outputs, read_json(outputs["manifest"])


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        dry_run.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_missing_approval_record_blocks_by_default(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, write_approval=False)
    outputs = dry_run.build_outputs(args_for(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_missing_approval_record"


def test_missing_approval_record_with_fixture_flag_produces_fixture_only_status(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, write_approval=False)
    outputs = dry_run.build_outputs(args_for(tmp_path, paths, "--allow-missing-approval-record-for-fixture-only"))
    manifest = read_json(outputs["manifest"])

    assert manifest["request_construction_status"] == "request_construction_dry_run_fixture_only_no_approval_record"
    assert manifest["request_intent_created"] is False


def test_valid_approval_record_produces_available_non_executable_status(tmp_path: Path) -> None:
    outputs, manifest = build(tmp_path)
    rows = read_csv(outputs["artifact_freshness"])

    assert manifest["request_construction_status"] == "request_construction_dry_run_available_non_executable"
    assert manifest["request_intent_created"] is True
    assert manifest["digest_binding_required"] is True
    assert manifest["digest_binding_verified"] is True
    assert manifest["request_intent_digest"]
    assert manifest["artifact_freshness_policy_applied"] is True
    assert manifest["stale_artifact_count"] == 0
    assert all(row["status"] == "fresh" for row in rows)


def test_request_construction_artifacts_are_written_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    original_replace = dry_run.os.replace
    replace_calls: list[tuple[Path, Path]] = []

    def spy_replace(src: object, dst: object) -> None:
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(dry_run.os, "replace", spy_replace)
    outputs = dry_run.build_outputs(args_for(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["atomic_artifact_writes_enabled"] is True
    assert manifest["atomic_write_strategy"] == "temp_file_same_directory_os_replace"
    assert any(src.parent == outputs["intent"].parent and dst == outputs["intent"] for src, dst in replace_calls)
    assert any(src.parent == outputs["manifest"].parent and dst == outputs["manifest"] for src, dst in replace_calls)


def test_request_write_failure_does_not_leave_partial_final_intent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    outputs = dry_run.output_paths(tmp_path / "out")
    original_replace = dry_run.os.replace

    def fail_manifest_replace(src: object, dst: object) -> None:
        if Path(dst) == outputs["manifest"]:
            raise OSError("simulated manifest replace failure")
        original_replace(src, dst)

    monkeypatch.setattr(dry_run.os, "replace", fail_manifest_replace)

    with pytest.raises(OSError, match="simulated manifest replace failure"):
        dry_run.build_outputs(args_for(tmp_path, paths))

    assert not outputs["intent"].exists()
    assert not outputs["fields"].exists()
    assert not any(outputs["intent"].parent.glob(f".{outputs['intent'].name}.*.tmp"))


def test_request_write_failure_preserves_existing_valid_intent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    outputs = dry_run.output_paths(tmp_path / "out")
    write_csv(
        outputs["intent"],
        [
            {
                "run_id": "existing",
                "candidate_id": "gbpusd_short_h10_1_5_off_hours",
                "symbol": "GBPUSD",
                "timeframe": "M15",
                "direction": "short",
            }
        ],
        dry_run.INTENT_FIELDNAMES,
    )
    write_csv(
        outputs["fields"],
        [{"run_id": "existing", "field_name": "existing"}],
        dry_run.FIELD_DESCRIPTOR_FIELDNAMES,
    )
    original_intent = outputs["intent"].read_bytes()
    original_fields = outputs["fields"].read_bytes()
    original_replace = dry_run.os.replace

    def fail_manifest_replace(src: object, dst: object) -> None:
        if Path(dst) == outputs["manifest"]:
            raise OSError("simulated manifest replace failure")
        original_replace(src, dst)

    monkeypatch.setattr(dry_run.os, "replace", fail_manifest_replace)

    with pytest.raises(OSError, match="simulated manifest replace failure"):
        dry_run.build_outputs(args_for(tmp_path, paths))

    assert outputs["intent"].read_bytes() == original_intent
    assert outputs["fields"].read_bytes() == original_fields


def test_stale_approval_record_artifact_age_blocks_non_fixture_request(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        approval_payload=approval_record(created_at_utc=created_at_utc(minutes_ago=16)),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_stale_upstream_artifact"
    assert manifest["request_intent_created"] is False
    assert manifest["blocking_stale_artifact_count"] == 1


def test_stale_artifact_override_requires_demo_module_acknowledgment(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        approval_payload=approval_record(created_at_utc=created_at_utc(minutes_ago=16)),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_module_validation_acknowledgment"
    assert manifest["request_intent_created"] is False
    assert manifest["stale_override_used"] is False


def test_stale_artifact_override_for_demo_module_validation_produces_non_executable_intent(tmp_path: Path) -> None:
    outputs, manifest = build(
        tmp_path,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        dry_run.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
        approval_payload=approval_record(created_at_utc=created_at_utc(minutes_ago=16)),
    )
    warnings = read_csv(outputs["warnings"])

    assert manifest["request_construction_status"] == (
        "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
    )
    assert manifest["request_intent_created"] is True
    assert manifest["module_validation_demo_execution"] is True
    assert manifest["stale_override_used"] is True
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False
    assert manifest["order_check_allowed_for_demo_module_validation_only"] is True
    assert manifest["order_send_allowed_for_demo_module_validation_only"] is False
    assert manifest["broker_payload_constructed"] is False
    assert manifest["executable_order_object_constructed"] is False
    assert manifest["order_check_called"] is False
    assert manifest["order_send_called"] is False
    assert manifest["order_execution_performed"] is False
    assert manifest["stale_artifact_count"] == 1
    assert manifest["blocking_stale_artifact_count"] == 0
    assert any(
        row["warning_code"] == "stale_upstream_artifact_warning" and row["blocking_warning"] == "false"
        for row in warnings
    )


def test_stale_artifact_override_does_not_bypass_digest_mismatch(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, approval_payload=approval_record(created_at_utc=created_at_utc(minutes_ago=16)))
    approval = read_json(paths["approval"])
    bound = approval["bound_upstream_artifact_digests"]
    assert isinstance(bound, dict)
    first_key = next(iter(bound))
    bound[first_key]["sha256_digest"] = "0" * 64
    write_json(paths["approval"], approval)

    outputs = dry_run.build_outputs(
        args_for(
            tmp_path,
            paths,
            "--module-validation-demo-execution",
            "--allow-stale-upstream-artifacts-for-demo-module-validation",
            "--module-validation-acknowledgment",
            dry_run.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
        )
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["request_construction_status"] == "request_construction_blocked_digest_mismatch"
    assert manifest["digest_mismatch_count"] == 1
    assert manifest["request_intent_created"] is False
    assert manifest["stale_override_used"] is False


def test_stale_artifact_override_does_not_bypass_margin_hard_cap(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        dry_run.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
        approval_payload=approval_record(created_at_utc=created_at_utc(minutes_ago=16)),
        margin_payload=margin_manifest(broker_margin_usage_ratio=0.71),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_margin_policy"
    assert manifest["request_intent_created"] is False
    assert manifest["stale_override_used"] is False


def test_missing_approval_digest_binding_blocks_request_construction(tmp_path: Path) -> None:
    approval = approval_record()
    approval.pop("bound_upstream_artifact_digests")
    _outputs, manifest = build(tmp_path, approval_payload=approval, auto_bind_approval_digests=False)

    assert manifest["request_construction_status"] == "request_construction_blocked_missing_digest_binding"
    assert manifest["digest_binding_verified"] is False
    assert manifest["missing_digest_count"] == 1
    assert manifest["request_intent_created"] is False


def test_digest_mismatch_on_bound_artifact_blocks_request_construction(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    approval = read_json(paths["approval"])
    bound = approval["bound_upstream_artifact_digests"]
    assert isinstance(bound, dict)
    first_key = next(iter(bound))
    bound[first_key]["sha256_digest"] = "0" * 64
    write_json(paths["approval"], approval)

    outputs = dry_run.build_outputs(args_for(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["request_construction_status"] == "request_construction_blocked_digest_mismatch"
    assert manifest["digest_mismatch_count"] == 1
    assert manifest["request_intent_created"] is False


def test_missing_bound_artifact_blocks_request_construction(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    approval = read_json(paths["approval"])
    bound = approval["bound_upstream_artifact_digests"]
    assert isinstance(bound, dict)
    bound["missing_required_artifact"] = {
        "path": str(tmp_path / "missing_required_artifact.json"),
        "sha256_digest": "1" * 64,
        "status_field": "fixture_status",
        "status_value": "ok",
    }
    write_json(paths["approval"], approval)

    outputs = dry_run.build_outputs(args_for(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["request_construction_status"] == "request_construction_blocked_missing_digest_binding"
    assert manifest["missing_digest_count"] == 1
    assert manifest["request_intent_created"] is False


def test_missing_bound_digest_field_blocks_request_construction(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    approval = read_json(paths["approval"])
    bound = approval["bound_upstream_artifact_digests"]
    assert isinstance(bound, dict)
    first_key = next(iter(bound))
    bound[first_key].pop("sha256_digest")
    write_json(paths["approval"], approval)

    outputs = dry_run.build_outputs(args_for(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["request_construction_status"] == "request_construction_blocked_missing_digest_binding"
    assert manifest["missing_digest_count"] == 1
    assert manifest["request_intent_created"] is False


def test_valid_request_intent_includes_sell_market_intent(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    intent = read_csv(outputs["intent"])[0]

    assert intent["side"] == "sell"
    assert intent["order_type_intent"] == "market_sell"


def test_valid_request_intent_includes_volume_entry_sl_tp_from_approval_record(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    intent = read_csv(outputs["intent"])[0]

    assert intent["volume_lots"] == "0.07"
    assert intent["entry_reference_price"] == "1.25"
    assert intent["sl_price"] == "1.26"
    assert intent["tp_price"] == "1.235"


def test_expired_approval_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_expired_approval"


def test_expired_approval_override_for_demo_module_validation_produces_non_executable_intent(tmp_path: Path) -> None:
    outputs, manifest = build(
        tmp_path,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        dry_run.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        dry_run.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )
    warnings = read_csv(outputs["warnings"])

    assert manifest["request_construction_status"] == "request_construction_dry_run_available_non_executable"
    assert manifest["request_intent_created"] is True
    assert manifest["module_validation_demo_execution"] is True
    assert manifest["expired_signal_override_used"] is True
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False
    assert manifest["order_check_called"] is False
    assert manifest["order_send_called"] is False
    assert manifest["order_execution_performed"] is False
    assert any(
        row["warning_code"] == "request_construction_dry_run_blocked_expired_approval"
        and row["blocking_warning"] == "false"
        for row in warnings
    )


def test_expired_approval_override_without_module_validation_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        dry_run.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_expired_approval"
    assert manifest["request_intent_created"] is False


@pytest.mark.parametrize("ack", ["", "wrong_ack"])
def test_expired_approval_override_missing_or_wrong_ack_blocks(tmp_path: Path, ack: str) -> None:
    _outputs, manifest = build(
        tmp_path,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        dry_run.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        ack,
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_expired_approval"
    assert manifest["request_intent_created"] is False


def test_expired_approval_override_does_not_bypass_digest_mismatch(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY))
    approval = read_json(paths["approval"])
    bound = approval["bound_upstream_artifact_digests"]
    assert isinstance(bound, dict)
    first_key = next(iter(bound))
    bound[first_key]["sha256_digest"] = "0" * 64
    write_json(paths["approval"], approval)

    outputs = dry_run.build_outputs(
        args_for(
            tmp_path,
            paths,
            "--module-validation-demo-execution",
            "--allow-stale-upstream-artifacts-for-demo-module-validation",
            "--module-validation-acknowledgment",
            dry_run.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
            "--allow-expired-signal-for-demo-module-validation",
            "--expired-signal-override-acknowledgment",
            dry_run.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        )
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["request_construction_status"] == "request_construction_blocked_digest_mismatch"
    assert manifest["request_intent_created"] is False


def test_expired_approval_override_does_not_bypass_margin_hard_cap(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        dry_run.MODULE_VALIDATION_STALE_OVERRIDE_ACKNOWLEDGMENT,
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        dry_run.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        approval_payload=approval_record(approval_expiry_time_utc=EXPIRED_EXPIRY),
        margin_payload=margin_manifest(broker_margin_usage_ratio=0.71),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_margin_policy"
    assert manifest["request_intent_created"] is False


def test_revoked_approval_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, approval_payload=approval_record(approval_revoked=True))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_unapproved_record"


def test_wrong_approval_scope_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, approval_payload=approval_record(approval_scope="no_request_no_execution"))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_unapproved_record"


def test_missing_signal_id_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, approval_payload=approval_record(signal_id=""))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_unapproved_record"


def test_missing_idempotency_key_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, approval_payload=approval_record(idempotency_key=""))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_unapproved_record"


def test_signal_id_idempotency_key_mismatch_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, approval_payload=approval_record(idempotency_key="different_idempotency_key"))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_unapproved_record"


def test_stale_freshness_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        freshness_payload=freshness_manifest(
            freshness_status="live_signal_freshness_stale_beyond_horizon",
            is_fresh=False,
            is_stale=True,
            bars_elapsed=11,
        ),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_stale_signal"


def test_broker_local_reconciliation_not_clean_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, recon_payload=reconciliation_manifest(reconciliation_status="hold", broker_position_count_symbol=1))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_broker_local_reconciliation"


def test_margin_above_hard_cap_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, margin_payload=margin_manifest(broker_margin_usage_ratio=0.71))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_margin_policy"


def test_margin_manifest_snapshot_observed_volume_passes(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        margin_payload=margin_manifest(stepped_volume_lots=0.05, broker_margin_usage_ratio=0.19362),
        margin_snapshot_payload=margin_snapshot(margin_calc_volume_lots=0.05, broker_margin_usage_ratio=0.19362),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_available_non_executable"


def test_margin_manifest_snapshot_volume_mismatch_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(
        tmp_path,
        margin_payload=margin_manifest(stepped_volume_lots=0.05),
        margin_snapshot_payload=margin_snapshot(margin_calc_volume_lots=0.07),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_margin_policy"


def test_margin_non_demo_account_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, margin_payload=margin_manifest(account_mode_label="real"))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_margin_policy"


def test_margin_non_eur_account_currency_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, margin_payload=margin_manifest(account_currency="USD"))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_margin_policy"


def test_margin_equity_policy_outside_10pct_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, margin_payload=margin_manifest(account_equity_policy_status="outside_10pct"))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_margin_policy"


def test_margin_spread_outside_policy_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, margin_payload=margin_manifest(spread_within_policy=False))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_margin_policy"


def test_margin_warning_status_under_hard_cap_passes(tmp_path: Path) -> None:
    warning_status = "broker_safe_margin_validation_available_with_margin_warning"
    _outputs, manifest = build(
        tmp_path,
        margin_payload=margin_manifest(validation_status=warning_status, broker_margin_usage_ratio=0.6),
        margin_snapshot_payload=margin_snapshot(validation_status=warning_status, broker_margin_usage_ratio=0.6),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_available_non_executable"


def test_duplicate_protection_unavailable_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, duplicate_payload=duplicate_manifest(plan_status="hold"))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_duplicate_protection"


def test_unsafe_demo_policy_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, policy_payload=demo_policy(order_execution_allowed=True))

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_noncanonical_demo_execution_policy"


def test_future_state_incompatible_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path, future_state_payload={"state": "open"})

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_future_state_incompatible"


def client_reject_flat_state(signal_id: str, idempotency_key: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "state_status": "send_rejected_no_position_no_order",
        "last_retcode": 10027,
        "order_execution_performed": False,
        "crash_recovery_required": False,
        "automatic_retry_allowed": False,
        "retry_performed": False,
        "broker_order_ticket": "",
        "broker_deal_ticket": "",
        "broker_position_ticket": "",
        "signal_id": signal_id,
        "idempotency_key": idempotency_key,
    }
    payload.update(overrides)
    return payload


def market_closed_flat_state(signal_id: str, idempotency_key: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
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
        "signal_id": signal_id,
        "idempotency_key": idempotency_key,
    }
    payload.update(overrides)
    return payload


def test_client_reject_flat_state_blocks_without_explicit_ack(tmp_path: Path) -> None:
    approval = approval_record()
    _outputs, manifest = build(
        tmp_path,
        approval_payload=approval,
        future_state_payload=client_reject_flat_state(
            str(approval["signal_id"]),
            str(approval["idempotency_key"]),
        ),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_future_state_incompatible"
    assert manifest["explicit_second_demo_send_after_client_reject_flat"] is False


def test_client_reject_flat_state_with_demo_ack_allows_request_construction(tmp_path: Path) -> None:
    approval = approval_record()
    _outputs, manifest = build(
        tmp_path,
        "--module-validation-demo-execution",
        "--allow-new-demo-send-after-client-reject-flat",
        "--client-reject-resend-acknowledgment",
        dry_run.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        approval_payload=approval,
        future_state_payload=client_reject_flat_state(
            str(approval["signal_id"]),
            str(approval["idempotency_key"]),
        ),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_available_non_executable"
    assert manifest["explicit_second_demo_send_after_client_reject_flat"] is True
    assert manifest["previous_state_status"] == "send_rejected_no_position_no_order"
    assert manifest["previous_send_retcode"] == 10027
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False


def test_market_closed_reject_flat_same_signal_blocks_request_construction(tmp_path: Path) -> None:
    approval = approval_record()
    _outputs, manifest = build(
        tmp_path,
        approval_payload=approval,
        future_state_payload=market_closed_flat_state(
            str(approval["signal_id"]),
            str(approval["idempotency_key"]),
        ),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_future_state_incompatible"
    assert manifest["explicit_new_signal_after_market_closed_flat"] is False
    assert manifest["previous_send_retcode"] == 10018


def test_market_closed_reject_flat_new_signal_allows_request_construction(tmp_path: Path) -> None:
    approval = approval_record()
    _outputs, manifest = build(
        tmp_path,
        approval_payload=approval,
        future_state_payload=market_closed_flat_state("previous-signal", "previous-idem"),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_available_non_executable"
    assert manifest["explicit_new_signal_after_market_closed_flat"] is True
    assert manifest["previous_state_status"] == "execution_rejected"
    assert manifest["previous_send_retcode"] == 10018
    assert manifest["new_signal_id_differs_from_previous_state"] is True
    assert manifest["new_idempotency_key_differs_from_previous_state"] is True
    assert manifest["automatic_retry_allowed"] is False
    assert manifest["retry_performed"] is False
    assert manifest["strategy_valid"] is True
    assert manifest["production_valid"] is True


def test_market_closed_reject_flat_dirty_broker_reconciliation_blocks(tmp_path: Path) -> None:
    approval = approval_record()
    _outputs, manifest = build(
        tmp_path,
        approval_payload=approval,
        future_state_payload=market_closed_flat_state("previous-signal", "previous-idem"),
        recon_payload=reconciliation_manifest(broker_position_count_symbol=1),
    )

    assert manifest["request_construction_status"] == "request_construction_dry_run_blocked_broker_local_reconciliation"
    assert manifest["request_intent_created"] is False


def test_broker_adjacent_request_fields_are_not_payload_fields_now(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    fields = read_csv(outputs["fields"])

    assert fields
    assert all(row["broker_payload_field_now"] == "false" for row in fields)


def test_broker_adjacent_request_fields_are_not_executable_now(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    fields = read_csv(outputs["fields"])

    assert fields
    assert all(row["executable_now"] == "false" for row in fields)


def test_manifest_confirms_no_broker_payload_constructed(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)

    assert manifest["broker_payload_constructed"] is False


def test_manifest_confirms_no_executable_order_object_constructed(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)

    assert manifest["executable_order_object_constructed"] is False


def test_manifest_confirms_order_check_not_called(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)

    assert manifest["order_check_called"] is False


def test_manifest_confirms_order_send_not_called(tmp_path: Path) -> None:
    _outputs, manifest = build(tmp_path)

    assert manifest["order_send_called"] is False


def test_no_future_state_json_is_written(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    assert not paths["future_state"].exists()
    outputs = dry_run.build_outputs(args_for(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["future_state_json_written"] is False
    assert not paths["future_state"].exists()


def test_no_order_evidence_rows_are_present(tmp_path: Path) -> None:
    outputs, _manifest = build(tmp_path)
    evidence = read_csv(outputs["no_order"])[0]

    assert evidence["no_order_send_called"] == "true"
    assert evidence["no_order_check_called"] == "true"
    assert evidence["no_broker_payload_constructed"] == "true"


def test_static_safety_grep_confirms_no_forbidden_broker_order_history_calls() -> None:
    source = Path(dry_run.__file__).read_text(encoding="utf-8")
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
    source = Path(dry_run.__file__).read_text(encoding="utf-8")
    forbidden = ["while " + "True", "Background" + "Scheduler", "schedule" + ".every", "threading" + ".", "asyncio" + "."]
    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_executable_request_object_construction() -> None:
    source = Path(dry_run.__file__).read_text(encoding="utf-8")
    forbidden = ["request = {", "order_request = {", "broker_payload = {", "payload = {", "executable_order_object = {"]
    for token in forbidden:
        assert token not in source
