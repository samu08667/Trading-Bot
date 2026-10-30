import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_manual_approval_record_schema as schema
from scripts import create_fixed_candidate_demo_manual_approval_record as creator


FUTURE_SIGNAL_TIME = "2099-01-01 00:00:00"
EXPIRED_SIGNAL_TIME = "2020-01-01 00:00:00"


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
        "risk_amount_max": 5.0,
        "risk_percent_max": 0.5,
        "safety_boundaries": boundaries,
    }


def gate_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_gate",
        "gate_status": "manual_approval_gate_dry_run_passed_non_actionable",
        "source_nature": "live_data_shadow_signal",
        "signal_time_server": FUTURE_SIGNAL_TIME,
        "entry_reference_price": 1.25,
        "sl_price": 1.26,
        "tp_price": 1.235,
        "would_signal_review_run_id": "fixture_would_signal_review",
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


def would_signal_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_would_signal_review",
        "review_status": "would_signal_review_available_no_order",
        "created_at_utc": created_at_utc(),
        "source_nature": "live_data_shadow_signal",
        "time_server": FUTURE_SIGNAL_TIME,
        "entry_reference_price": 1.25,
        "sl_price_preview": 1.26,
        "tp_price_preview": 1.235,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
    }
    payload.update(overrides)
    return payload


def freshness_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_freshness",
        "created_at_utc": created_at_utc(),
        "freshness_status": "live_signal_freshness_fresh_current_or_latest_signal",
        "source_nature": "live_data_shadow_signal",
        "signal_time_server": FUTURE_SIGNAL_TIME,
        "is_fresh": True,
        "is_stale": False,
        "bars_elapsed": 1,
    }
    payload.update(overrides)
    return payload


def reconciliation_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_recon",
        "created_at_utc": created_at_utc(),
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
        "created_at_utc": created_at_utc(),
        "validation_status": "broker_safe_margin_validation_available",
        "source_nature": "live_data_shadow_signal",
        "account_mode_label": "demo",
        "broker_margin_estimate": 270.44,
        "broker_margin_usage_ratio": 0.27044,
        "spread_current_points": 3.0,
        "spread_within_policy": True,
        "stepped_volume_lots": 0.07,
        "risk_amount_max": 5.0,
        "risk_percent_max": 0.5,
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


def write_sources(
    tmp_path: Path,
    *,
    registry_payload: dict[str, object] | None = None,
    policy_payload: dict[str, object] | None = None,
    gate_payload: dict[str, object] | None = None,
    would_signal_payload: dict[str, object] | None = None,
    freshness_payload: dict[str, object] | None = None,
    recon_payload: dict[str, object] | None = None,
    margin_payload: dict[str, object] | None = None,
    duplicate_payload: dict[str, object] | None = None,
    manual_payload: dict[str, object] | None = None,
    future_payload: dict[str, object] | None = None,
    future_state_payload: dict[str, object] | None = None,
) -> dict[str, Path]:
    gate_dir = tmp_path / "gate"
    would_signal_dir = tmp_path / "would_signal"
    freshness_dir = tmp_path / "freshness"
    recon_dir = tmp_path / "recon"
    margin_dir = tmp_path / "margin"
    duplicate_dir = tmp_path / "duplicate"
    manual_dir = tmp_path / "manual"
    future_dir = tmp_path / "future"
    registry = write_json(tmp_path / "config" / "canonical.json", registry_payload or canonical_registry())
    policy = write_json(tmp_path / "config" / "policy.json", policy_payload or demo_policy())
    write_json(gate_dir / schema.GATE_MANIFEST, gate_payload or gate_manifest())
    write_json(would_signal_dir / creator.WOULD_SIGNAL_REVIEW_MANIFEST, would_signal_payload or would_signal_manifest())
    write_json(freshness_dir / schema.FRESHNESS_MANIFEST, freshness_payload or freshness_manifest())
    write_json(recon_dir / schema.BROKER_RECON_MANIFEST, recon_payload or reconciliation_manifest())
    write_json(margin_dir / schema.MARGIN_MANIFEST, margin_payload or margin_manifest())
    write_json(margin_dir / schema.MARGIN_SNAPSHOT, margin_payload or margin_manifest())
    write_json(duplicate_dir / schema.DUPLICATE_MANIFEST, duplicate_payload or duplicate_plan())
    write_json(manual_dir / schema.MANUAL_PLAN_MANIFEST, manual_payload or manual_plan())
    write_json(future_dir / schema.FUTURE_REQUEST_MANIFEST, future_payload or future_request())
    future_record = tmp_path / "state" / "approval_record.json"
    future_state = tmp_path / "state" / "future_state.json"
    if future_state_payload is not None:
        write_json(future_state, future_state_payload)
    return {
        "gate": gate_dir,
        "would_signal": would_signal_dir,
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


def build_schema(tmp_path: Path, paths: dict[str, Path]) -> Path:
    schema_dir = tmp_path / "schema_out"
    schema_dir.mkdir(parents=True, exist_ok=True)
    output_files = {
        "allowed_statuses": str(schema_dir / creator.SCHEMA_ALLOWED_STATUSES),
        "operator_decisions": str(schema_dir / creator.SCHEMA_OPERATOR_DECISIONS),
        "post_approval_rechecks": str(schema_dir / creator.SCHEMA_POST_APPROVAL_RECHECKS),
        "digest_rules": str(schema_dir / creator.SCHEMA_DIGEST_RULES),
        "upstream_digests": str(schema_dir / creator.SCHEMA_UPSTREAM_DIGESTS),
        "signal_id_rule": str(schema_dir / creator.SCHEMA_SIGNAL_ID_RULE),
    }
    write_json(
        schema_dir / creator.SCHEMA_MANIFEST,
        {
            "run_id": "fixture_schema",
            "schema_status": "manual_approval_record_schema_available_no_order",
            "schema_patch_status": "schema_audit_gaps_closed_no_order",
            "future_approval_record_created": False,
            "future_state_json_written": False,
            "manual_approval_performed": False,
            "request_construction_allowed_now": False,
            "warnings_count": 1,
            "blocking_warnings_count": 0,
            "output_files": output_files,
        },
    )
    write_csv(schema_dir / creator.SCHEMA_FIELDS, [{"field_name": "approval_record_id"}], ["field_name"])
    write_csv(schema_dir / creator.SCHEMA_BINDINGS, [{"binding_name": "signal_id"}], ["binding_name"])
    write_csv(
        schema_dir / creator.SCHEMA_EXPIRY,
        [{"rule_name": "explicit_approval_expiry_formula", "trigger_condition": "approval_expiry_time_utc = signal_time_server + horizon_bars * timeframe_minutes"}],
        ["rule_name", "trigger_condition"],
    )
    write_csv(
        schema_dir / creator.SCHEMA_SCOPE,
        [{"scope_name": "approval_does_not_execute_an_order"}, {"scope_name": "approval_does_not_call_order_check"}],
        ["scope_name"],
    )
    write_csv(schema_dir / creator.SCHEMA_PRE_APPROVAL_RECHECKS, [{"recheck_name": "signal still fresh"}], ["recheck_name"])
    write_csv(schema_dir / creator.SCHEMA_BLOCKS, [{"block_condition": "upstream_artifact_digest_mismatch"}], ["block_condition"])
    write_csv(schema_dir / creator.SCHEMA_AUDIT, [{"audit_requirement": "record hash"}], ["audit_requirement"])
    write_csv(
        schema_dir / creator.SCHEMA_WARNINGS,
        [{"run_id": "fixture_schema", "warning_code": "schema_available_design_only_no_approval_created", "severity": "warning", "message": "ack required", "source": "fixture", "blocking_warning": "false"}],
        creator.WARNING_FIELDNAMES,
    )
    write_csv(
        schema_dir / creator.SCHEMA_ALLOWED_STATUSES,
        [
            {"status": "not_created", "permits_request_construction": "false", "permits_order_execution": "false"},
            {"status": "pending_operator_review", "permits_request_construction": "false", "permits_order_execution": "false"},
            {"status": "approved_for_future_request_construction_only", "permits_request_construction": "conditional_after_final_pre_request_rechecks", "permits_order_execution": "false"},
            {"status": "rejected", "permits_request_construction": "false", "permits_order_execution": "false"},
            {"status": "expired", "permits_request_construction": "false", "permits_order_execution": "false"},
            {"status": "revoked", "permits_request_construction": "false", "permits_order_execution": "false"},
            {"status": "blocked_stale_signal", "permits_request_construction": "false", "permits_order_execution": "false"},
            {"status": "blocked_kill_switch", "permits_request_construction": "false", "permits_order_execution": "false"},
            {"status": "blocked_broker_local_reconciliation", "permits_request_construction": "false", "permits_order_execution": "false"},
            {"status": "blocked_margin_policy", "permits_request_construction": "false", "permits_order_execution": "false"},
            {"status": "blocked_duplicate_protection", "permits_request_construction": "false", "permits_order_execution": "false"},
            {"status": "blocked_unsafe_policy", "permits_request_construction": "false", "permits_order_execution": "false"},
        ],
        ["status", "permits_request_construction", "permits_order_execution"],
    )
    labels = [
        ("approve_for_future_request_construction_only", "true", "approved_for_future_request_construction_only", "conditional_after_final_pre_request_rechecks"),
        ("reject_signal", "true", "rejected", "false"),
        ("revoke_prior_approval", "true", "revoked", "false"),
        ("acknowledge_warning_only", "true", "", "false"),
        ("no_decision", "true", "", "false"),
        ("approve_trade", "false", "", "false"),
        ("approve_execution", "false", "", "false"),
        ("send_order", "false", "", "false"),
        ("execute_order", "false", "", "false"),
        ("bypass_checks", "false", "", "false"),
        ("ignore_stale_signal", "false", "", "false"),
        ("ignore_kill_switch", "false", "", "false"),
        ("ignore_margin_policy", "false", "", "false"),
        ("ignore_duplicate_protection", "false", "", "false"),
        ("ignore_broker_local_reconciliation", "false", "", "false"),
    ]
    write_csv(
        schema_dir / creator.SCHEMA_OPERATOR_DECISIONS,
        [
            {
                "label": label,
                "allowed": allowed,
                "maps_to_approval_status": mapped,
                "permits_request_construction": permits_request,
                "permits_order_execution": "false",
            }
            for label, allowed, mapped, permits_request in labels
        ],
        ["label", "allowed", "maps_to_approval_status", "permits_request_construction", "permits_order_execution"],
    )
    write_csv(
        schema_dir / creator.SCHEMA_POST_APPROVAL_RECHECKS,
        [
            {"recheck_name": "recheck_signal_freshness_still_fresh", "required": "true", "blocking_if_failed": "true"},
            {"recheck_name": "recheck_broker_local_reconciliation_clean", "required": "true", "blocking_if_failed": "true"},
        ],
        ["recheck_name", "required", "blocking_if_failed"],
    )
    write_csv(
        schema_dir / creator.SCHEMA_DIGEST_RULES,
        [
            {"rule_name": "approval_record_digest_algorithm", "rule_value": "SHA-256"},
            {"rule_name": "approval_record_canonical_serialization", "rule_value": "canonical_json_sorted_keys_utf8_no_extra_whitespace"},
            {"rule_name": "upstream_artifact_digest_algorithm", "rule_value": "SHA-256"},
            {"rule_name": "digest_recompute_requirement", "rule_value": "record_hash_or_digest_excludes_record_hash_or_digest_field_itself"},
        ],
        ["rule_name", "rule_value"],
    )
    upstream_specs = [
        ("manual_approval_gate_dry_run_manifest", paths["gate"] / schema.GATE_MANIFEST, "gate_status"),
        ("live_signal_freshness_manifest", paths["freshness"] / schema.FRESHNESS_MANIFEST, "freshness_status"),
        ("broker_local_reconciliation_manifest", paths["recon"] / schema.BROKER_RECON_MANIFEST, "reconciliation_status"),
        ("broker_safe_margin_validation_manifest", paths["margin"] / schema.MARGIN_MANIFEST, "validation_status"),
        ("broker_safe_margin_validation_margin_snapshot", paths["margin"] / schema.MARGIN_SNAPSHOT, "validation_status"),
        ("duplicate_protection_plan_manifest", paths["duplicate"] / schema.DUPLICATE_MANIFEST, "plan_status"),
        ("manual_approval_kill_switch_plan_manifest", paths["manual"] / schema.MANUAL_PLAN_MANIFEST, "plan_status"),
        ("future_request_readiness_plan_manifest", paths["future"] / schema.FUTURE_REQUEST_MANIFEST, "plan_status"),
    ]
    digest_rows = []
    for name, path, status_field in upstream_specs:
        data = read_json(path)
        digest_rows.append(
            {
                "upstream_name": name,
                "upstream_path": str(path),
                "upstream_run_id": data.get("run_id", ""),
                "upstream_status_field": status_field,
                "upstream_status_value": data.get(status_field, ""),
                "digest_algorithm": "SHA-256",
                "sha256_digest": creator.sha256_file(path),
                "required_for_future_approval_record": "true",
            }
        )
    write_csv(
        schema_dir / creator.SCHEMA_UPSTREAM_DIGESTS,
        digest_rows,
        [
            "upstream_name",
            "upstream_path",
            "upstream_run_id",
            "upstream_status_field",
            "upstream_status_value",
            "digest_algorithm",
            "sha256_digest",
            "required_for_future_approval_record",
        ],
    )
    write_csv(
        schema_dir / creator.SCHEMA_SIGNAL_ID_RULE,
        [
            {"rule_name": "signal_id_required", "required": "true", "blocking_if_failed": "true"},
            {"rule_name": "signal_id_derivation_fallback", "required": "true", "blocking_if_failed": "true"},
            {"rule_name": "signal_id_missing_block_rule", "required": "true", "blocking_if_failed": "true"},
        ],
        ["rule_name", "required", "blocking_if_failed"],
    )
    return schema_dir


def creator_args(
    tmp_path: Path,
    paths: dict[str, Path],
    schema_dir: Path,
    *,
    decision: str | None = "approve_for_future_request_construction_only",
    identity: str | None = "operator_fixture",
    acknowledgment: str | None = "acknowledged_schema_warning_no_execution",
    dry_run: bool = False,
    overwrite: bool = False,
    module_validation: bool = False,
    allow_expired_signal_override: bool = False,
    expired_signal_ack: str | None = None,
) -> object:
    argv = [
        "--run-id",
        "fixture_creation",
        "--manual-approval-record-schema-dir",
        str(schema_dir),
        "--manual-approval-gate-dry-run-dir",
        str(paths["gate"]),
        "--would-signal-review-dir",
        str(paths["would_signal"]),
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
        str(tmp_path / "creation_out"),
        "--approval-note",
        "fixture note",
        "--overwrite",
    ]
    if decision is not None:
        argv.extend(["--operator-decision-label", decision])
    if identity is not None:
        argv.extend(["--operator-identity-ref", identity])
    if acknowledgment is not None:
        argv.extend(["--operator-warning-acknowledgment", acknowledgment])
    if module_validation:
        argv.append("--module-validation-demo-execution")
    if allow_expired_signal_override:
        argv.append("--allow-expired-signal-for-demo-module-validation")
    if expired_signal_ack is not None:
        argv.extend(["--expired-signal-override-acknowledgment", expired_signal_ack])
    if dry_run:
        argv.append("--dry-run")
    if overwrite:
        argv.append("--overwrite")
    return creator.build_parser().parse_args(argv)


def build_creation(tmp_path: Path, paths: dict[str, Path], schema_dir: Path, **kwargs: object) -> tuple[dict[str, Path], dict[str, object]]:
    outputs = creator.build_outputs(creator_args(tmp_path, paths, schema_dir, **kwargs))
    return outputs, read_json(outputs["manifest"])


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        creator.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_dry_run_writes_preview_but_not_approval_record(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    outputs, manifest = build_creation(tmp_path, paths, schema_dir, decision=None, identity=None, acknowledgment=None, dry_run=True)

    assert manifest["creation_status"] == "manual_approval_record_creation_dry_run_no_record_created"
    assert manifest["approval_record_created"] is False
    assert outputs["record_preview"].exists()
    assert not paths["future_record"].exists()


def test_positive_approval_creates_record_only_when_all_gates_pass(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "manual_approval_record_created_for_future_request_construction_only"
    assert manifest["approval_record_created"] is True
    assert paths["future_record"].exists()
    assert not paths["future_state"].exists()


def test_approval_record_json_is_written_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    original_replace = creator.os.replace
    replace_calls: list[tuple[Path, Path]] = []

    def spy_replace(src: object, dst: object) -> None:
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(creator.os, "replace", spy_replace)
    outputs, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["atomic_artifact_writes_enabled"] is True
    assert manifest["atomic_write_strategy"] == "temp_file_same_directory_os_replace"
    assert any(src.parent == paths["future_record"].parent and dst == paths["future_record"] for src, dst in replace_calls)
    assert any(src.parent == outputs["manifest"].parent and dst == outputs["manifest"] for src, dst in replace_calls)


def test_approval_write_failure_does_not_leave_partial_final_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    output_manifest = tmp_path / "creation_out" / creator.OUTPUT_MANIFEST
    original_replace = creator.os.replace

    def fail_manifest_replace(src: object, dst: object) -> None:
        if Path(dst) == output_manifest:
            raise OSError("simulated manifest replace failure")
        original_replace(src, dst)

    monkeypatch.setattr(creator.os, "replace", fail_manifest_replace)

    with pytest.raises(OSError, match="simulated manifest replace failure"):
        creator.build_outputs(creator_args(tmp_path, paths, schema_dir))

    assert not paths["future_record"].exists()
    assert not any(paths["future_record"].parent.glob(f".{paths['future_record'].name}.*.tmp"))


def test_approval_write_failure_preserves_existing_valid_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    existing_record = {
        "approval_status": "rejected",
        "approval_revoked": False,
        "approval_expiry_time_utc": FUTURE_SIGNAL_TIME,
        "record_hash_or_digest": "existing",
    }
    write_json(paths["future_record"], existing_record)
    original_bytes = paths["future_record"].read_bytes()
    output_manifest = tmp_path / "creation_out" / creator.OUTPUT_MANIFEST
    original_replace = creator.os.replace

    def fail_manifest_replace(src: object, dst: object) -> None:
        if Path(dst) == output_manifest:
            raise OSError("simulated manifest replace failure")
        original_replace(src, dst)

    monkeypatch.setattr(creator.os, "replace", fail_manifest_replace)

    with pytest.raises(OSError, match="simulated manifest replace failure"):
        creator.build_outputs(creator_args(tmp_path, paths, schema_dir))

    assert paths["future_record"].read_bytes() == original_bytes
    assert read_json(paths["future_record"]) == existing_record


def test_positive_record_status_scope_and_boundaries(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    build_creation(tmp_path, paths, schema_dir)
    record = read_json(paths["future_record"])

    assert record["approval_status"] == "approved_for_future_request_construction_only"
    assert record["approval_scope"] == "future_request_construction_only"
    assert record["approval_does_not_execute_order"] is True
    assert record["approval_does_not_construct_request"] is True
    assert record["approval_requires_final_pre_request_recheck"] is True


def test_record_hash_is_present_and_excludes_itself(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    build_creation(tmp_path, paths, schema_dir)
    record = read_json(paths["future_record"])
    digest = record["record_hash_or_digest"]
    digest_input = dict(record)
    digest_input.pop("record_hash_or_digest")

    assert len(str(digest)) == 64
    assert creator.sha256_payload(digest_input) == digest


def test_record_binds_cli_upstream_paths_even_when_schema_digest_rows_are_legacy(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    rows = read_csv(schema_dir / creator.SCHEMA_UPSTREAM_DIGESTS)
    for row in rows:
        row["upstream_path"] = str(tmp_path / "legacy_global_artifact.json")
        row["sha256_digest"] = "0" * 64
    write_csv(
        schema_dir / creator.SCHEMA_UPSTREAM_DIGESTS,
        rows,
        [
            "upstream_name",
            "upstream_path",
            "upstream_run_id",
            "upstream_status_field",
            "upstream_status_value",
            "digest_algorithm",
            "sha256_digest",
            "required_for_future_approval_record",
        ],
    )
    _, manifest = build_creation(tmp_path, paths, schema_dir)
    record = read_json(paths["future_record"])
    bound = record["bound_upstream_artifact_digests"]

    assert manifest["creation_status"] == "manual_approval_record_created_for_future_request_construction_only"
    assert bound["live_signal_freshness_manifest"]["path"] == str(paths["freshness"] / creator.FRESHNESS_MANIFEST)
    assert bound["broker_local_reconciliation_manifest"]["path"] == str(paths["recon"] / creator.BROKER_RECON_MANIFEST)
    assert bound["broker_safe_margin_validation_manifest"]["path"] == str(paths["margin"] / creator.MARGIN_MANIFEST)
    assert bound["future_request_readiness_plan_manifest"]["path"] == str(paths["future"] / creator.FUTURE_REQUEST_MANIFEST)


def test_missing_upstream_digest_schema_artifact_blocks_approval_creation(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    (schema_dir / creator.SCHEMA_UPSTREAM_DIGESTS).unlink()
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "blocked_missing_upstream_artifact_digests_artifact"
    assert not paths["future_record"].exists()


def test_missing_schema_manifest_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    (schema_dir / creator.SCHEMA_MANIFEST).unlink()
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "blocked_missing_schema_manifest"


def test_missing_allowed_statuses_artifact_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    (schema_dir / creator.SCHEMA_ALLOWED_STATUSES).unlink()
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "blocked_missing_allowed_statuses_artifact"


def test_unknown_operator_label_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir, decision="mystery_label")

    assert manifest["creation_status"] == "blocked_unknown_operator_decision_label"


def test_forbidden_operator_label_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir, decision="execute_order")

    assert manifest["creation_status"] == "blocked_forbidden_operator_decision_label"


def test_missing_operator_identity_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir, identity=None)

    assert manifest["creation_status"] == "blocked_missing_operator_identity_ref"


def test_missing_warning_acknowledgment_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir, acknowledgment=None)

    assert manifest["creation_status"] == "blocked_missing_warning_acknowledgment"


def test_stale_freshness_blocks(tmp_path: Path) -> None:
    paths = write_sources(
        tmp_path,
        freshness_payload=freshness_manifest(
            freshness_status="live_signal_freshness_stale_beyond_horizon",
            is_fresh=False,
            is_stale=True,
            bars_elapsed=11,
        ),
    )
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "blocked_stale_signal"


def test_stale_freshness_artifact_age_blocks_real_approval_creation(tmp_path: Path) -> None:
    paths = write_sources(
        tmp_path,
        freshness_payload=freshness_manifest(created_at_utc=created_at_utc(minutes_ago=16)),
    )
    schema_dir = build_schema(tmp_path, paths)
    outputs, manifest = build_creation(tmp_path, paths, schema_dir)
    rows = read_csv(outputs["artifact_freshness"])

    assert manifest["creation_status"] == "manual_approval_record_creation_blocked_stale_upstream_artifact"
    assert manifest["artifact_freshness_policy_applied"] is True
    assert manifest["blocking_stale_artifact_count"] == 1
    assert not paths["future_record"].exists()
    assert any(
        row["artifact_name"] == "live_signal_freshness"
        and row["status"] == "stale"
        and row["blocking_if_stale"] == "true"
        for row in rows
    )


def test_expired_signal_blocks_positive_approval(tmp_path: Path) -> None:
    expired_gate = gate_manifest(signal_time_server=EXPIRED_SIGNAL_TIME)
    expired_freshness = freshness_manifest(signal_time_server=EXPIRED_SIGNAL_TIME)
    paths = write_sources(tmp_path, gate_payload=expired_gate, freshness_payload=expired_freshness)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "blocked_expired_signal"


def test_expired_signal_override_for_demo_module_validation_creates_non_strategy_record(tmp_path: Path) -> None:
    expired_gate = gate_manifest(signal_time_server=EXPIRED_SIGNAL_TIME)
    expired_freshness = freshness_manifest(signal_time_server=EXPIRED_SIGNAL_TIME)
    paths = write_sources(tmp_path, gate_payload=expired_gate, freshness_payload=expired_freshness)
    schema_dir = build_schema(tmp_path, paths)
    outputs, manifest = build_creation(
        tmp_path,
        paths,
        schema_dir,
        module_validation=True,
        allow_expired_signal_override=True,
        expired_signal_ack=creator.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
    )
    warnings = read_csv(outputs["warnings"])

    assert manifest["creation_status"] == "manual_approval_record_created_for_future_request_construction_only"
    assert manifest["approval_record_created"] is True
    assert manifest["module_validation_demo_execution"] is True
    assert manifest["expired_signal_override_used"] is True
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False
    assert paths["future_record"].exists()
    assert any(row["warning_code"] == "blocked_expired_signal" and row["blocking_warning"] == "false" for row in warnings)


def test_expired_signal_override_without_module_validation_blocks(tmp_path: Path) -> None:
    expired_gate = gate_manifest(signal_time_server=EXPIRED_SIGNAL_TIME)
    expired_freshness = freshness_manifest(signal_time_server=EXPIRED_SIGNAL_TIME)
    paths = write_sources(tmp_path, gate_payload=expired_gate, freshness_payload=expired_freshness)
    schema_dir = build_schema(tmp_path, paths)
    _outputs, manifest = build_creation(
        tmp_path,
        paths,
        schema_dir,
        allow_expired_signal_override=True,
        expired_signal_ack=creator.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
    )

    assert manifest["creation_status"] == "blocked_invalid_expired_signal_override"
    assert manifest["approval_record_created"] is False


@pytest.mark.parametrize("ack", [None, "", "wrong_ack"])
def test_expired_signal_override_missing_or_wrong_ack_blocks(tmp_path: Path, ack: str | None) -> None:
    expired_gate = gate_manifest(signal_time_server=EXPIRED_SIGNAL_TIME)
    expired_freshness = freshness_manifest(signal_time_server=EXPIRED_SIGNAL_TIME)
    paths = write_sources(tmp_path, gate_payload=expired_gate, freshness_payload=expired_freshness)
    schema_dir = build_schema(tmp_path, paths)
    _outputs, manifest = build_creation(
        tmp_path,
        paths,
        schema_dir,
        module_validation=True,
        allow_expired_signal_override=True,
        expired_signal_ack=ack,
    )

    assert manifest["creation_status"] == "blocked_invalid_expired_signal_override"
    assert manifest["approval_record_created"] is False


@pytest.mark.parametrize(
    ("source_overrides", "expected_status"),
    [
        ({"recon_payload": reconciliation_manifest(reconciliation_status="hold")}, "blocked_broker_local_reconciliation"),
        ({"margin_payload": margin_manifest(broker_margin_usage_ratio=0.71)}, "blocked_margin_policy"),
        ({"duplicate_payload": duplicate_plan(plan_status="hold")}, "blocked_duplicate_protection"),
        ({"manual_payload": manual_plan(plan_status="hold")}, "blocked_unsafe_policy"),
    ],
)
def test_expired_signal_override_does_not_bypass_other_creation_gates(
    tmp_path: Path, source_overrides: dict[str, object], expected_status: str
) -> None:
    expired_gate = gate_manifest(signal_time_server=EXPIRED_SIGNAL_TIME)
    expired_freshness = freshness_manifest(signal_time_server=EXPIRED_SIGNAL_TIME)
    paths = write_sources(
        tmp_path,
        gate_payload=expired_gate,
        freshness_payload=expired_freshness,
        **source_overrides,
    )
    schema_dir = build_schema(tmp_path, paths)
    _outputs, manifest = build_creation(
        tmp_path,
        paths,
        schema_dir,
        module_validation=True,
        allow_expired_signal_override=True,
        expired_signal_ack=creator.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
    )

    assert manifest["creation_status"] == expected_status
    assert manifest["approval_record_created"] is False


def test_broker_local_reconciliation_not_clean_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, recon_payload=reconciliation_manifest(reconciliation_status="hold"))
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "blocked_broker_local_reconciliation"


def test_margin_above_hard_cap_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, margin_payload=margin_manifest(broker_margin_usage_ratio=0.71))
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "blocked_margin_policy"


def test_duplicate_protection_unavailable_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, duplicate_payload=duplicate_plan(plan_status="hold"))
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "blocked_duplicate_protection"


def test_unsafe_demo_policy_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, policy_payload=demo_policy(order_execution_allowed=True))
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "blocked_noncanonical_demo_execution_policy"


def test_existing_active_approval_record_blocks_duplicate_positive_approval(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    build_creation(tmp_path, paths, schema_dir)
    _, manifest = build_creation(tmp_path, paths, schema_dir, overwrite=True)

    assert manifest["creation_status"] == "blocked_existing_active_approval_record"


def test_reject_signal_creates_rejected_record_no_request_permission(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir, decision="reject_signal")
    record = read_json(paths["future_record"])

    assert manifest["creation_status"] == "manual_approval_record_created_rejected_no_request"
    assert record["approval_status"] == "rejected"
    assert record["approval_scope"] == "no_request_no_execution"
    assert record["approval_does_not_construct_request"] is True


def test_positive_record_contains_required_schema_fields(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    build_creation(tmp_path, paths, schema_dir)
    record = read_json(paths["future_record"])

    required = {
        "approval_record_version",
        "approval_record_id",
        "approval_status",
        "approval_scope",
        "candidate_id",
        "symbol",
        "timeframe",
        "direction",
        "source_nature",
        "signal_time_server",
        "signal_id",
        "idempotency_key",
        "entry_reference_price",
        "sl_price",
        "tp_price",
        "volume_lots",
        "risk_amount",
        "risk_percent",
        "broker_margin_estimate",
        "broker_margin_usage_ratio",
        "spread_current_points",
        "bound_upstream_artifact_digests",
        "digest_algorithm",
        "canonical_serialization_rule",
        "post_approval_pre_request_recheck_required",
        "operator_decision_label_enum",
        "signal_id_derivation_rule",
        "approval_expiry_formula",
        "record_hash_or_digest",
    }
    assert required.issubset(record)


def test_signal_id_and_idempotency_are_deterministic_fallbacks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)
    source = "gbpusd_short_h10_1_5_off_hoursGBPUSDM15short2099-01-01 00:00:001.251.261.235"
    expected = creator.sha256_text(source)

    assert manifest["signal_id"] == expected
    assert manifest["idempotency_key"] == expected


def test_live_style_alias_fields_derive_signal_id_and_record_prices(tmp_path: Path) -> None:
    gate = gate_manifest(would_signal_review_run_id="")
    for key in ("signal_time_server", "entry_reference_price", "sl_price", "tp_price"):
        gate.pop(key, None)
    would_signal = would_signal_manifest(
        time_server=FUTURE_SIGNAL_TIME,
        entry_reference_price=1.34587,
        sl_price_preview=1.346673,
        tp_price_preview=1.3446655,
    )
    paths = write_sources(tmp_path, gate_payload=gate, would_signal_payload=would_signal)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)
    record = read_json(paths["future_record"])
    source = "gbpusd_short_h10_1_5_off_hoursGBPUSDM15short2099-01-01 00:00:001.345871.3466731.3446655"
    expected = creator.sha256_text(source)

    assert manifest["signal_id"] == expected
    assert manifest["idempotency_key"] == expected
    assert record["signal_time_server"] == FUTURE_SIGNAL_TIME
    assert record["entry_reference_price"] == 1.34587
    assert record["sl_price"] == 1.346673
    assert record["tp_price"] == 1.3446655
    assert record["would_signal_review_run_id"] == "fixture_would_signal_review"


def test_canonical_registry_missing_max_open_positions_is_allowed_when_policy_enforces_one(tmp_path: Path) -> None:
    registry = canonical_registry()
    registry.pop("max_open_positions", None)
    paths = write_sources(tmp_path, registry_payload=registry)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "manual_approval_record_created_for_future_request_construction_only"


def test_truly_missing_signal_identity_inputs_still_block(tmp_path: Path) -> None:
    gate = gate_manifest()
    for key in ("signal_time_server", "entry_reference_price", "sl_price", "tp_price"):
        gate.pop(key, None)
    would_signal = would_signal_manifest(time_server="", entry_reference_price="", sl_price_preview="", tp_price_preview="")
    freshness = freshness_manifest(signal_time_server="")
    margin = margin_manifest(margin_calc_price="")
    paths = write_sources(
        tmp_path,
        gate_payload=gate,
        would_signal_payload=would_signal,
        freshness_payload=freshness,
        margin_payload=margin,
    )
    schema_dir = build_schema(tmp_path, paths)
    outputs, manifest = build_creation(tmp_path, paths, schema_dir)
    warnings = read_csv(outputs["warnings"])

    assert manifest["creation_status"] == "blocked_stale_signal"
    assert not paths["future_record"].exists()
    assert any(row["warning_code"] == "blocked_stale_signal" for row in warnings)
    assert any(row["warning_code"] == "blocked_duplicate_protection" for row in warnings)


def test_expiry_uses_h10_m15_formula(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    build_creation(tmp_path, paths, schema_dir)
    record = read_json(paths["future_record"])

    assert record["approval_expiry_formula"] == "approval_expiry_time_utc = signal_time_server + horizon_bars * timeframe_minutes"
    assert record["approval_expiry_time_utc"] == "2099-01-01T02:30:00+00:00"


def test_manifest_keeps_request_execution_boundaries_false(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["future_state_json_written"] is False
    assert manifest["request_construction_allowed_now"] is False
    assert manifest["broker_request_constructed"] is False
    assert manifest["broker_payload_constructed"] is False
    assert manifest["order_object_constructed"] is False
    assert manifest["order_execution_allowed"] is False
    assert manifest["demo_approval_performed"] is False


def test_no_decision_creates_no_record(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir, decision="no_decision")

    assert manifest["creation_status"] == "manual_approval_record_not_created_no_positive_decision"
    assert not paths["future_record"].exists()


def test_acknowledge_warning_only_creates_no_record(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir, decision="acknowledge_warning_only")

    assert manifest["creation_status"] == "manual_approval_record_not_created_no_positive_decision"
    assert not paths["future_record"].exists()


def test_future_state_incompatible_blocks(tmp_path: Path) -> None:
    paths = write_sources(tmp_path, future_state_payload={"state": "open"})
    schema_dir = build_schema(tmp_path, paths)
    _, manifest = build_creation(tmp_path, paths, schema_dir)

    assert manifest["creation_status"] == "blocked_future_state_incompatible"


def test_creation_does_not_create_request_payload_or_object_artifacts(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    outputs, manifest = build_creation(tmp_path, paths, schema_dir)
    output_names = {path.name for path in outputs.values()}

    assert manifest["broker_request_constructed"] is False
    assert manifest["broker_payload_constructed"] is False
    assert manifest["order_object_constructed"] is False
    assert not any("request_payload" in name or "order_object" in name for name in output_names)


def test_no_order_evidence_rows_are_present(tmp_path: Path) -> None:
    paths = write_sources(tmp_path)
    schema_dir = build_schema(tmp_path, paths)
    outputs, _ = build_creation(tmp_path, paths, schema_dir)
    evidence = read_csv(outputs["no_order"])[0]

    assert evidence["no_order_execution_performed"] == "true"
    assert evidence["no_order_request_constructed"] == "true"
    assert evidence["no_order_check_called"] == "true"
    assert evidence["no_order_calc_margin_called"] == "true"
    assert evidence["no_future_state_json_written"] == "true"


def test_static_safety_grep_confirms_forbidden_broker_order_calls_absent() -> None:
    source = Path(creator.__file__).read_text(encoding="utf-8")
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
    source = Path(creator.__file__).read_text(encoding="utf-8")
    forbidden = ["while " + "True", "Background" + "Scheduler", "schedule" + ".every", "threading" + ".", "asyncio" + "."]
    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_request_construction_execution_behavior() -> None:
    source = Path(creator.__file__).read_text(encoding="utf-8")
    forbidden = ["subprocess", "sqlite3", "request = {", "payload = {", "execute_now", "send_now"]
    for token in forbidden:
        assert token not in source
