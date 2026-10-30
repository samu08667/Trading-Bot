from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_fixed_candidate_demo_signal_to_order_pilot_once as pilot


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def existing_approval_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "approval_status": "approved_for_future_request_construction_only",
        "approval_scope": "future_request_construction_only",
        "approval_revoked": False,
        "signal_id": "signal_fixture",
        "idempotency_key": "idem_fixture",
        "digest_binding_verified": True,
        "approval_does_not_construct_request": True,
        "approval_does_not_execute_order": True,
        "record_hash_or_digest": "b" * 64,
        "bound_upstream_artifact_digests": {},
    }
    record.update(overrides)
    return record


def value_after(command: list[str], flag: str) -> str:
    index = command.index(flag)
    return command[index + 1]


def args_for(tmp_path: Path, *extra: str, ack: bool = True, demo: bool = True) -> object:
    argv = [
        "--run-id",
        "orchestrator-test",
        "--operator-identity-ref",
        "operator_fixture",
        "--output-dir",
        str(tmp_path / "out"),
    ]
    if demo:
        argv.append("--demo-account-only")
    if ack:
        argv.extend(["--operator-final-acknowledgment", pilot.SEND_CONFIRMATION])
    argv.extend(extra)
    return pilot.build_parser().parse_args(argv)


class FakeRunner:
    def __init__(self, scenario: dict[str, object] | None = None) -> None:
        self.scenario = scenario or {}
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str]) -> object:
        self.calls.append([str(item) for item in command])
        script_name = Path(str(command[1])).name
        if self.scenario.get("raise_on") == script_name:
            raise RuntimeError(f"simulated failure in {script_name}")
        output_dir = Path(value_after([str(item) for item in command], "--output-dir"))
        output_dir.mkdir(parents=True, exist_ok=True)
        writer = {
            "run_fixed_candidate_demo_shadow_signal_once.py": self.write_shadow,
            "run_fixed_candidate_demo_manual_approval_prep_pipeline_once.py": self.write_prep,
            "create_fixed_candidate_demo_manual_approval_record.py": self.write_approval,
            "build_fixed_candidate_demo_request_construction_dry_run.py": self.write_request,
            "check_fixed_candidate_demo_order_check.py": self.write_order_check,
            "build_fixed_candidate_demo_order_send_pilot_readiness_plan.py": self.write_readiness,
            "send_fixed_candidate_demo_order_pilot.py": self.write_send,
        }[script_name]
        writer(output_dir, [str(item) for item in command])
        return SimpleNamespace(returncode=int(self.scenario.get(f"{script_name}:returncode", 0)), stdout="", stderr="")

    def script_call_count(self, script_name: str) -> int:
        return sum(1 for command in self.calls if Path(command[1]).name == script_name)

    def write_shadow(self, output_dir: Path, _command: list[str]) -> None:
        write_json(
            output_dir / pilot.SHADOW_MANIFEST,
            {
                "shadow_status": self.scenario.get("shadow_status", "shadow_signal_detected"),
                "shadow_decision_label": "shadow_signal_detected",
                "signal_id": "signal_fixture",
                "idempotency_key": "idem_fixture",
            },
        )

    def write_prep(self, output_dir: Path, command: list[str]) -> None:
        expired_override_valid = (
            "--module-validation-demo-execution" in command
            and "--allow-expired-signal-for-demo-module-validation" in command
            and "--expired-signal-override-acknowledgment" in command
            and pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT in command
        )
        expired_signal_case = bool(self.scenario.get("prep_expired_signal"))
        prep_status = str(
            self.scenario.get(
                "prep_status",
                (
                    "manual_approval_prep_pipeline_completed_dry_run_ready_for_manual_real_approval_decision"
                    if not expired_signal_case or expired_override_valid
                    else "manual_approval_prep_pipeline_blocked_approval_dry_run"
                ),
            )
        )
        approval_step_dir_name = str(
            self.scenario.get("prep_approval_step_dir_name", pilot.PREP_APPROVAL_DRY_RUN_STEP_DIR)
        )
        approval_step_dir = (
            output_dir.parent / approval_step_dir_name
            if self.scenario.get("prep_approval_step_dir_outside")
            else output_dir / approval_step_dir_name
        )
        dirs = {
            "would_signal_review_dir": output_dir / "01_would_signal_review",
            "broker_safe_margin_validation_dir": output_dir / "06_broker_safe_margin_validation",
            "duplicate_protection_plan_dir": output_dir / "08_duplicate_protection_plan",
            "manual_approval_kill_switch_plan_dir": output_dir / "09_manual_approval_kill_switch_plan",
            "future_request_construction_readiness_plan_dir": output_dir / "11_future_request_construction_readiness_plan",
            "broker_local_reconciliation_dir": output_dir / "12_broker_local_reconciliation",
            "live_signal_freshness_dir": output_dir / "13_live_signal_freshness",
            "manual_approval_gate_dry_run_dir": output_dir / "14_manual_approval_gate_dry_run",
        }
        if not self.scenario.get("omit_prep_approval_dir_from_manifest"):
            dirs["approval_record_creation_dry_run_dir"] = approval_step_dir
        for directory in [*dirs.values(), approval_step_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        write_json(
            output_dir / pilot.PREP_MANIFEST,
            {
                "pipeline_status": prep_status,
                "blocking_warnings_count": int(
                    self.scenario.get(
                        "prep_blocking_warnings_count",
                        0 if not expired_signal_case or expired_override_valid else 1,
                    )
                ),
                "module_validation_demo_execution": "--module-validation-demo-execution" in command,
                "expired_signal_override_used": expired_signal_case and expired_override_valid,
                **{key: str(value) for key, value in dirs.items()},
            },
        )
        if self.scenario.get("prep_approval_dry_run_status") or (expired_signal_case and not expired_override_valid):
            with (output_dir / pilot.PREP_CHILD_RESULTS).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["step_name", "manifest_status", "manifest_path", "output_dir"],
                )
                writer.writeheader()
                include_paths = not self.scenario.get("omit_prep_child_result_paths")
                writer.writerow(
                    {
                        "step_name": "approval_record_creation_dry_run",
                        "manifest_status": str(
                            self.scenario.get(
                                "prep_approval_dry_run_status",
                                "manual_approval_record_creation_dry_run_no_record_created",
                            )
                        ),
                        "manifest_path": str(approval_step_dir / pilot.APPROVAL_MANIFEST) if include_paths else "",
                        "output_dir": str(approval_step_dir) if include_paths else "",
                    }
                )
        if self.scenario.get("prep_inner_warning_code") or (expired_signal_case and not expired_override_valid):
            inner_dir = approval_step_dir
            inner_dir.mkdir(parents=True, exist_ok=True)
            with (inner_dir / pilot.APPROVAL_WARNINGS).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["warning_code", "message", "source", "blocking_warning"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "warning_code": str(
                            self.scenario.get("prep_inner_warning_code", "blocked_expired_signal")
                        ),
                        "message": str(
                            self.scenario.get("prep_inner_warning_message", "Gate failed: approval_expiry_time")
                        ),
                        "source": str(self.scenario.get("prep_inner_warning_source", "")),
                        "blocking_warning": str(self.scenario.get("prep_inner_warning_blocking", True)).lower(),
                    }
                )

    def bound_artifact(self, root: Path, directory: str, filename: str) -> dict[str, str]:
        path = write_json(root / directory / filename, {"status": "ok"})
        return {"path": str(path), "sha256_digest": "a" * 64, "status_field": "status", "status_value": "ok"}

    def bound_artifact_in_dir(self, directory: Path, filename: str) -> dict[str, str]:
        path = write_json(directory / filename, {"status": "ok"})
        return {"path": str(path), "sha256_digest": "a" * 64, "status_field": "status", "status_value": "ok"}

    def write_approval(self, output_dir: Path, command: list[str]) -> None:
        record_path = output_dir / "approval_record.json"
        bound_root = output_dir / "bound"
        if self.scenario.get("approval_binds_cli_artifacts"):
            bound_upstreams = {
                "future_request_readiness_plan_manifest": self.bound_artifact_in_dir(
                    Path(value_after(command, "--future-request-readiness-plan-dir")),
                    "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json",
                ),
                "broker_local_reconciliation_manifest": self.bound_artifact_in_dir(
                    Path(value_after(command, "--broker-local-reconciliation-dir")),
                    "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json",
                ),
                "broker_safe_margin_validation_manifest": self.bound_artifact_in_dir(
                    Path(value_after(command, "--broker-safe-margin-validation-dir")),
                    "fixed_candidate_demo_broker_safe_margin_validation_manifest.json",
                ),
                "broker_safe_margin_validation_margin_snapshot": self.bound_artifact_in_dir(
                    Path(value_after(command, "--broker-safe-margin-validation-dir")),
                    "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json",
                ),
                "live_signal_freshness_manifest": self.bound_artifact_in_dir(
                    Path(value_after(command, "--live-signal-freshness-dir")),
                    "fixed_candidate_demo_live_signal_freshness_manifest.json",
                ),
                "duplicate_protection_plan_manifest": self.bound_artifact_in_dir(
                    Path(value_after(command, "--duplicate-protection-plan-dir")),
                    "fixed_candidate_demo_duplicate_protection_plan_manifest.json",
                ),
                "manual_approval_kill_switch_plan_manifest": self.bound_artifact_in_dir(
                    Path(value_after(command, "--manual-approval-kill-switch-plan-dir")),
                    "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json",
                ),
            }
        else:
            bound_upstreams = {
                "future_request_readiness_plan_manifest": self.bound_artifact(
                    bound_root,
                    "future_request",
                    "fixed_candidate_demo_future_request_construction_readiness_plan_manifest.json",
                ),
                "broker_local_reconciliation_manifest": self.bound_artifact(
                    bound_root,
                    "reconciliation",
                    "fixed_candidate_demo_broker_local_state_reconciliation_manifest.json",
                ),
                "broker_safe_margin_validation_manifest": self.bound_artifact(
                    bound_root,
                    "margin",
                    "fixed_candidate_demo_broker_safe_margin_validation_manifest.json",
                ),
                "broker_safe_margin_validation_margin_snapshot": self.bound_artifact(
                    bound_root,
                    "margin",
                    "fixed_candidate_demo_broker_safe_margin_validation_margin_snapshot.json",
                ),
                "live_signal_freshness_manifest": self.bound_artifact(
                    bound_root,
                    "freshness",
                    "fixed_candidate_demo_live_signal_freshness_manifest.json",
                ),
                "duplicate_protection_plan_manifest": self.bound_artifact(
                    bound_root,
                    "duplicate",
                    "fixed_candidate_demo_duplicate_protection_plan_manifest.json",
                ),
                "manual_approval_kill_switch_plan_manifest": self.bound_artifact(
                    bound_root,
                    "manual",
                    "fixed_candidate_demo_manual_approval_kill_switch_plan_manifest.json",
                ),
            }
        record = {
            "approval_status": "approved_for_future_request_construction_only",
            "approval_scope": "future_request_construction_only",
            "approval_revoked": False,
            "signal_id": "signal_fixture",
            "idempotency_key": "idem_fixture",
            "digest_binding_verified": True,
            "approval_does_not_construct_request": True,
            "approval_does_not_execute_order": True,
            "record_hash_or_digest": "b" * 64,
            "bound_upstream_artifact_digests": bound_upstreams,
        }
        write_json(record_path, record)
        write_json(
            output_dir / pilot.APPROVAL_MANIFEST,
            {
                "creation_status": self.scenario.get(
                    "approval_creation_status",
                    "manual_approval_record_created_for_future_request_construction_only",
                ),
                "approval_record_created": bool(self.scenario.get("approval_record_created", True)),
                "approval_status": "approved_for_future_request_construction_only",
                "approval_scope": "future_request_construction_only",
                "future_approval_record_json": str(record_path),
                "signal_id": "signal_fixture",
                "idempotency_key": "idem_fixture",
            },
        )

    def write_request(self, output_dir: Path, command: list[str]) -> None:
        stale_override = "--allow-stale-upstream-artifacts-for-demo-module-validation" in command
        expired_override = "--allow-expired-signal-for-demo-module-validation" in command
        status = self.scenario.get(
            "request_status",
            "request_construction_dry_run_available_with_stale_override_for_demo_module_validation"
            if stale_override
            else "request_construction_dry_run_available_non_executable",
        )
        write_json(
            output_dir / pilot.REQUEST_MANIFEST,
            {
                "request_construction_status": status,
                "signal_id": "signal_fixture",
                "idempotency_key": "idem_fixture",
                "module_validation_demo_execution": "--module-validation-demo-execution" in command,
                "stale_override_used": stale_override,
                "stale_artifact_count": int(self.scenario.get("request_stale_artifact_count", 0)),
                "blocking_stale_artifact_count": int(
                    self.scenario.get(
                        "request_blocking_stale_artifact_count",
                        1 if status == "request_construction_dry_run_blocked_stale_upstream_artifact" else 0,
                    )
                ),
                "expired_signal_override_used": expired_override,
                "strategy_valid": False if stale_override or expired_override else True,
                "production_valid": False if stale_override or expired_override else True,
                "order_check_allowed_for_demo_module_validation_only": stale_override,
                "order_send_allowed_for_demo_module_validation_only": False,
                "broker_payload_constructed": False,
                "executable_order_object_constructed": False,
                "order_check_called": False,
                "order_send_called": False,
            },
        )

    def write_order_check(self, output_dir: Path, command: list[str]) -> None:
        status = str(self.scenario.get("order_check_status", "order_check_available_passed_no_send"))
        module_validation = "--module-validation-demo-execution" in command
        expired_override = "--allow-expired-signal-for-demo-module-validation" in command
        client_reject_resend = "--allow-new-demo-send-after-client-reject-flat" in command
        write_json(
            output_dir / pilot.ORDER_CHECK_MANIFEST,
            {
                "order_check_status": status,
                "signal_id": "signal_fixture",
                "idempotency_key": "idem_fixture",
                "module_validation_demo_execution": module_validation,
                "expired_signal_override_used": expired_override,
                "strategy_valid": False if module_validation or expired_override else True,
                "production_valid": False if module_validation or expired_override else True,
                "explicit_second_demo_send_after_client_reject_flat": client_reject_resend,
                "previous_send_retcode": 10027 if client_reject_resend else "",
                "previous_state_status": "send_rejected_no_position_no_order" if client_reject_resend else "",
                "automatic_retry_allowed": False,
                "retry_performed": False,
                "new_operator_authorized_attempt": client_reject_resend,
                "order_check_called": status == "order_check_available_passed_no_send",
                "order_check_call_count": 1 if status == "order_check_available_passed_no_send" else 0,
                "order_check_passed": status == "order_check_available_passed_no_send",
                "order_check_retcode": 0 if status == "order_check_available_passed_no_send" else 10013,
                "order_send_called": False,
            },
        )

    def write_readiness(self, output_dir: Path, command: list[str]) -> None:
        module_validation = "--module-validation-demo-execution" in command
        stale_override = "--allow-stale-upstream-artifacts-for-demo-module-validation" in command
        expired_override = "--allow-expired-signal-for-demo-module-validation" in command
        client_reject_resend = "--allow-new-demo-send-after-client-reject-flat" in command
        write_json(
            output_dir / pilot.SEND_READINESS_MANIFEST,
            {
                "order_send_pilot_readiness_status": self.scenario.get(
                    "readiness_status",
                    "order_send_pilot_readiness_plan_available_no_send",
                ),
                "module_validation_demo_execution": module_validation,
                "stale_override_used": stale_override,
                "expired_signal_override_used": expired_override,
                "explicit_second_demo_send_after_client_reject_flat": client_reject_resend,
                "previous_send_retcode": 10027 if client_reject_resend else "",
                "previous_state_status": "send_rejected_no_position_no_order" if client_reject_resend else "",
                "automatic_retry_allowed": False,
                "retry_performed": False,
                "new_operator_authorized_attempt": client_reject_resend,
                "strategy_valid": False if module_validation or stale_override or expired_override or client_reject_resend else True,
                "production_valid": False if module_validation or stale_override or expired_override or client_reject_resend else True,
                "send_readiness_for_demo_module_validation_only": module_validation and stale_override,
            },
        )

    def write_send(self, output_dir: Path, command: list[str]) -> None:
        status = str(
            self.scenario.get("send_status", "order_send_pilot_sent_success_deal_reconciliation_required")
        )
        call_count = int(self.scenario.get("send_call_count", 1))
        module_validation = "--module-validation-demo-execution" in command
        expired_override = "--allow-expired-signal-for-demo-module-validation" in command
        client_reject_resend = "--allow-new-demo-send-after-client-reject-flat" in command
        write_json(
            output_dir / pilot.SEND_MANIFEST,
            {
                "order_send_pilot_status": status,
                "order_send_called": call_count == 1,
                "order_send_call_count": call_count,
                "order_send_attempt_count": call_count,
                "module_validation_demo_execution": module_validation,
                "expired_signal_override_used": expired_override,
                "strategy_valid": False if module_validation or expired_override else True,
                "production_valid": False if module_validation or expired_override else True,
                "send_allowed_for_demo_module_validation_only": module_validation,
                "explicit_second_demo_send_after_client_reject_flat": client_reject_resend,
                "previous_send_retcode": 10027 if client_reject_resend else "",
                "previous_state_status": "send_rejected_no_position_no_order" if client_reject_resend else "",
                "automatic_retry_allowed": False,
                "retry_performed": False,
                "new_operator_authorized_attempt": client_reject_resend,
                "no_retry_performed": True,
                "no_loop_added": True,
                "no_scheduler_added": True,
                "order_execution_performed": status in pilot.SUCCESS_SEND_STATUSES,
                "order_ticket": "123456" if status in pilot.SUCCESS_SEND_STATUSES else "",
                "state_status": "reconciliation_required",
                "future_state_json_written": status in pilot.SUCCESS_SEND_STATUSES,
                "reconciliation_status": "post_send_reconciliation_required",
            },
        )
        write_json(
            output_dir / pilot.SEND_RESULT,
            {"retcode": 10009, "order": "123456", "comment": "fixture", "order_send_called": call_count == 1},
        )


def install_fake(monkeypatch: pytest.MonkeyPatch, scenario: dict[str, object] | None = None) -> FakeRunner:
    fake = FakeRunner(scenario)
    monkeypatch.setattr(pilot, "run_child_command", fake)
    return fake


def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *extra: str, scenario: dict[str, object] | None = None, **kwargs: object) -> tuple[dict[str, Path], dict[str, object], FakeRunner]:
    scenario = scenario or {}
    existing_record_path = tmp_path / "state" / "existing_approval_record.json"
    monkeypatch.setattr(pilot, "DEFAULT_APPROVAL_RECORD_JSON", existing_record_path)
    existing_overrides = scenario.get("existing_approval_overrides", {})
    assert isinstance(existing_overrides, dict)
    if not scenario.get("existing_approval_missing"):
        write_json(existing_record_path, existing_approval_record(**existing_overrides))
    fake = install_fake(monkeypatch, scenario)
    outputs = pilot.build_outputs(args_for(tmp_path, *extra, **kwargs))
    return outputs, read_json(outputs["manifest"]), fake


def test_valid_path_reaches_mocked_order_send_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(tmp_path, monkeypatch)
    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_order_sent"
    assert manifest["order_send_attempt_count"] == 1
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 1


def test_module_validation_full_path_reaches_mocked_order_send_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only",
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        scenario={"prep_expired_signal": True},
    )
    send_command = next(
        command for command in fake.calls if Path(command[1]).name == "send_fixed_candidate_demo_order_pilot.py"
    )
    order_check_command = next(
        command for command in fake.calls if Path(command[1]).name == "check_fixed_candidate_demo_order_check.py"
    )
    request_command = next(
        command
        for command in fake.calls
        if Path(command[1]).name == "build_fixed_candidate_demo_request_construction_dry_run.py"
    )
    readiness_command = next(
        command
        for command in fake.calls
        if Path(command[1]).name == "build_fixed_candidate_demo_order_send_pilot_readiness_plan.py"
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_order_sent"
    assert manifest["order_send_attempt_count"] == 1
    assert manifest["no_retry_performed"] is True
    assert manifest["no_loop_added"] is True
    assert manifest["no_scheduler_added"] is True
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 1
    assert "--max-order-send-attempts" in send_command
    assert "1" in send_command
    assert "--module-validation-demo-execution" in send_command
    assert "--allow-stale-upstream-artifacts-for-demo-module-validation" in send_command
    assert "--module-validation-acknowledgment" in send_command
    assert "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only" in send_command
    assert "--allow-expired-signal-for-demo-module-validation" in send_command
    assert "--expired-signal-override-acknowledgment" in send_command
    assert pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT in send_command


def test_module_validation_client_reject_resend_flags_propagate_to_order_send(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only",
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        "--allow-new-demo-send-after-client-reject-flat",
        "--client-reject-resend-acknowledgment",
        pilot.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT,
        scenario={"prep_expired_signal": True},
    )
    send_command = next(
        command for command in fake.calls if Path(command[1]).name == "send_fixed_candidate_demo_order_pilot.py"
    )
    order_check_command = next(
        command for command in fake.calls if Path(command[1]).name == "check_fixed_candidate_demo_order_check.py"
    )
    request_command = next(
        command
        for command in fake.calls
        if Path(command[1]).name == "build_fixed_candidate_demo_request_construction_dry_run.py"
    )
    readiness_command = next(
        command
        for command in fake.calls
        if Path(command[1]).name == "build_fixed_candidate_demo_order_send_pilot_readiness_plan.py"
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_order_sent"
    assert manifest["explicit_second_demo_send_after_client_reject_flat"] is True
    assert manifest["previous_send_retcode"] == 10027
    assert manifest["previous_state_status"] == "send_rejected_no_position_no_order"
    assert manifest["automatic_retry_allowed"] is False
    assert manifest["retry_performed"] is False
    assert manifest["new_operator_authorized_attempt"] is True
    assert "--allow-new-demo-send-after-client-reject-flat" in send_command
    assert "--client-reject-resend-acknowledgment" in send_command
    assert pilot.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT in send_command
    assert "--allow-new-demo-send-after-client-reject-flat" in order_check_command
    assert "--client-reject-resend-acknowledgment" in order_check_command
    assert pilot.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT in order_check_command
    assert "--allow-new-demo-send-after-client-reject-flat" in request_command
    assert "--client-reject-resend-acknowledgment" in request_command
    assert pilot.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT in request_command
    assert "--allow-new-demo-send-after-client-reject-flat" in readiness_command
    assert "--client-reject-resend-acknowledgment" in readiness_command
    assert pilot.CLIENT_REJECT_RESEND_ACKNOWLEDGMENT in readiness_command


def test_stop_after_request_construction_skips_order_check_and_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(tmp_path, monkeypatch, "--stop-after-request-construction", ack=False)
    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_stopped_after_request_construction"
    assert fake.script_call_count("check_fixed_candidate_demo_order_check.py") == 0
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0


def test_orchestrator_passes_fresh_prep_artifact_dirs_to_request_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        ack=False,
        scenario={"approval_binds_cli_artifacts": True},
    )
    request_command = next(
        command
        for command in fake.calls
        if Path(command[1]).name == "build_fixed_candidate_demo_request_construction_dry_run.py"
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_stopped_after_request_construction"
    assert "02_manual_approval_prep_pipeline" in value_after(request_command, "--broker-local-reconciliation-dir")
    assert "12_broker_local_reconciliation" in value_after(request_command, "--broker-local-reconciliation-dir")
    assert "02_manual_approval_prep_pipeline" in value_after(request_command, "--broker-safe-margin-validation-dir")
    assert "06_broker_safe_margin_validation" in value_after(request_command, "--broker-safe-margin-validation-dir")
    assert "02_manual_approval_prep_pipeline" in value_after(request_command, "--live-signal-freshness-dir")
    assert "13_live_signal_freshness" in value_after(request_command, "--live-signal-freshness-dir")
    assert manifest["request_stale_artifact_count"] == 0
    assert manifest["request_blocking_stale_artifact_count"] == 0


def test_orchestrator_normal_path_does_not_enable_stale_override_when_request_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        ack=False,
        scenario={"request_status": "request_construction_dry_run_blocked_stale_upstream_artifact"},
    )
    request_command = next(
        command
        for command in fake.calls
        if Path(command[1]).name == "build_fixed_candidate_demo_request_construction_dry_run.py"
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_request_construction"
    assert "--allow-stale-upstream-artifacts-for-demo-module-validation" not in request_command
    assert manifest["stale_override_used"] is False
    assert fake.script_call_count("check_fixed_candidate_demo_order_check.py") == 0
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0


def test_stop_after_order_check_skips_order_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(tmp_path, monkeypatch, "--stop-after-order-check", ack=False)
    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_stopped_after_order_check"
    assert fake.script_call_count("check_fixed_candidate_demo_order_check.py") == 1
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0


def test_stop_before_order_send_skips_order_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(tmp_path, monkeypatch, "--stop-before-order-send", ack=False)
    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_stopped_after_order_check"
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0


def test_no_valid_signal_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(tmp_path, monkeypatch, scenario={"shadow_status": "shadow_no_signal"})
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_no_valid_signal"
    assert fake.script_call_count("run_fixed_candidate_demo_manual_approval_prep_pipeline_once.py") == 0


def test_manual_approval_prep_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _fake = build(tmp_path, monkeypatch, scenario={"prep_status": "manual_approval_prep_pipeline_blocked_child_failure"})
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_manual_approval_prep"


def test_existing_active_approval_without_resume_flag_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_inner_warning_code": "blocked_existing_active_approval_record",
        },
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_manual_approval_prep"
    assert manifest["resumed_existing_active_approval_record"] is False
    assert fake.script_call_count("create_fixed_candidate_demo_manual_approval_record.py") == 0
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 0


def test_existing_active_approval_with_resume_flag_proceeds_to_request_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--resume-existing-active-approval-record",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_inner_warning_code": "blocked_existing_active_approval_record",
        },
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_stopped_after_request_construction"
    assert manifest["resumed_existing_active_approval_record"] is True
    assert manifest["resume_reason"] == "existing_active_approval_record"
    assert manifest["approval_record_json"]
    assert manifest["signal_id"] == "signal_fixture"
    assert manifest["idempotency_key"] == "idem_fixture"
    assert fake.script_call_count("create_fixed_candidate_demo_manual_approval_record.py") == 0
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 1


def test_resume_detection_uses_declared_approval_child_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--resume-existing-active-approval-record",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_approval_step_dir_name": "approval_record_creation_from_child_manifest",
            "prep_approval_step_dir_outside": True,
            "prep_inner_warning_code": "blocked_existing_active_approval_record",
        },
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_stopped_after_request_construction"
    assert manifest["resumed_existing_active_approval_record"] is True
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 1


def test_resume_detection_fallback_scans_unlisted_prep_child_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--resume-existing-active-approval-record",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_approval_step_dir_name": "unexpected_nested_approval_record_creation_step",
            "omit_prep_approval_dir_from_manifest": True,
            "omit_prep_child_result_paths": True,
            "prep_inner_warning_code": "blocked_existing_active_approval_record",
        },
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_stopped_after_request_construction"
    assert manifest["resumed_existing_active_approval_record"] is True
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 1


def test_blocked_approval_dry_run_with_different_warning_does_not_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--resume-existing-active-approval-record",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_inner_warning_code": "blocked_manual_approval_gate",
        },
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_manual_approval_prep"
    assert manifest["resumed_existing_active_approval_record"] is False
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 0


def test_blocked_approval_dry_run_with_nonblocking_existing_record_text_does_not_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--resume-existing-active-approval-record",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_inner_warning_code": "info_existing_active_approval_record",
            "prep_inner_warning_message": "existing_active_approval_record not blocked mention only",
            "prep_inner_warning_blocking": False,
        },
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_manual_approval_prep"
    assert manifest["resumed_existing_active_approval_record"] is False
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 0


def test_existing_active_approval_resume_missing_record_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--resume-existing-active-approval-record",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_inner_warning_code": "blocked_existing_active_approval_record",
            "existing_approval_missing": True,
        },
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_approval_record_creation"
    assert manifest["resumed_existing_active_approval_record"] is False
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 0


def test_existing_active_approval_resume_invalid_scope_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--resume-existing-active-approval-record",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_inner_warning_code": "blocked_existing_active_approval_record",
            "existing_approval_overrides": {"approval_scope": "wrong_scope"},
        },
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_approval_record_creation"
    assert manifest["resumed_existing_active_approval_record"] is False
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 0


def test_existing_active_approval_resume_revoked_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--resume-existing-active-approval-record",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_inner_warning_code": "blocked_existing_active_approval_record",
            "existing_approval_overrides": {"approval_revoked": True},
        },
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_approval_record_creation"
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 0


def test_resume_path_does_not_call_order_send_when_stopping_after_request_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--resume-existing-active-approval-record",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_inner_warning_code": "blocked_existing_active_approval_record",
        },
    )
    assert manifest["order_send_called"] is False
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0


def test_resume_decision_is_visible_in_child_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, manifest, _fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--resume-existing-active-approval-record",
        ack=False,
        scenario={
            "prep_status": "manual_approval_prep_pipeline_blocked_approval_dry_run",
            "prep_approval_dry_run_status": "manual_approval_record_creation_blocked",
            "prep_inner_warning_code": "blocked_existing_active_approval_record",
        },
    )
    rows = read_csv(outputs["child_results"])
    assert manifest["resumed_existing_active_approval_record"] is True
    assert any(
        row["step_name"] == "manual_approval_prep"
        and row["manifest_status"] == "manual_approval_prep_pipeline_blocked_approval_dry_run"
        for row in rows
    )
    assert any(
        row["step_name"] == "resume_existing_active_approval_record"
        and row["manifest_status"] == "valid_existing_active_approval_record"
        for row in rows
    )


def test_approval_record_creation_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _fake = build(
        tmp_path,
        monkeypatch,
        scenario={"approval_creation_status": "blocked_unapproved_record", "approval_record_created": False},
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_approval_record_creation"


def test_request_construction_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _fake = build(
        tmp_path,
        monkeypatch,
        scenario={"request_status": "request_construction_dry_run_blocked_margin_policy"},
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_request_construction"


def test_order_check_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _fake = build(
        tmp_path,
        monkeypatch,
        scenario={"order_check_status": "order_check_available_failed_no_send"},
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_order_check"


def test_send_readiness_failure_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _fake = build(
        tmp_path,
        monkeypatch,
        scenario={"readiness_status": "order_send_pilot_readiness_plan_blocked_duplicate_protection"},
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_send_readiness"


def test_module_validation_flags_propagate_to_send_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only",
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        scenario={
            "prep_expired_signal": True,
            "readiness_status": "order_send_pilot_readiness_plan_blocked_probe",
        },
    )
    readiness_command = next(
        command
        for command in fake.calls
        if Path(command[1]).name == "build_fixed_candidate_demo_order_send_pilot_readiness_plan.py"
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_send_readiness"
    assert "--module-validation-demo-execution" in readiness_command
    assert "--allow-stale-upstream-artifacts-for-demo-module-validation" in readiness_command
    assert "--module-validation-acknowledgment" in readiness_command
    assert "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only" in readiness_command
    assert "--allow-expired-signal-for-demo-module-validation" in readiness_command
    assert "--expired-signal-override-acknowledgment" in readiness_command
    assert pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT in readiness_command
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0


def test_non_demo_account_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _fake = build(
        tmp_path,
        monkeypatch,
        scenario={"order_check_status": "order_check_blocked_non_demo_account"},
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_non_demo_account"


def test_idempotency_already_used_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _fake = build(
        tmp_path,
        monkeypatch,
        scenario={"send_status": "order_send_pilot_blocked_existing_active_idempotency_key", "send_call_count": 0},
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_duplicate_or_idempotency"


def test_duplicate_open_position_or_order_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _fake = build(
        tmp_path,
        monkeypatch,
        scenario={"send_status": "order_send_pilot_blocked_duplicate_protection", "send_call_count": 0},
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_duplicate_or_idempotency"


def test_max_order_send_attempts_above_one_is_rejected_by_cli(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        args_for(tmp_path, "--max-order-send-attempts", "2")


def test_missing_operator_acknowledgment_blocks_before_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(tmp_path, monkeypatch, ack=False)
    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_order_send_result"
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0


def test_no_retry_automatic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(tmp_path, monkeypatch)
    assert manifest["no_retry_performed"] is True
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 1


def test_no_loop_or_scheduler_added(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _fake = build(tmp_path, monkeypatch)
    assert manifest["no_loop_added"] is True
    assert manifest["no_scheduler_added"] is True


def test_stale_override_module_validation_marks_strategy_and_production_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, _fake = build(
        tmp_path,
        monkeypatch,
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only",
    )
    assert manifest["module_validation_demo_execution"] is True
    assert manifest["stale_override_used"] is True
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False


def test_expired_signal_without_override_blocks_manual_approval_prep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        ack=False,
        scenario={"prep_expired_signal": True},
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_manual_approval_prep"
    assert manifest["expired_signal_override_used"] is False
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 0


def test_expired_signal_override_module_validation_reaches_request_construction_stop_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only",
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        ack=False,
        scenario={"prep_expired_signal": True},
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_stopped_after_request_construction"
    assert manifest["module_validation_demo_execution"] is True
    assert manifest["expired_signal_override_used"] is True
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False
    assert manifest["order_check_called"] is False
    assert manifest["order_send_called"] is False
    assert fake.script_call_count("check_fixed_candidate_demo_order_check.py") == 0
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0


def test_expired_signal_override_module_validation_reaches_order_check_stop_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-order-check",
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only",
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        ack=False,
        scenario={"prep_expired_signal": True},
    )
    order_check_command = next(
        command for command in fake.calls if Path(command[1]).name == "check_fixed_candidate_demo_order_check.py"
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_completed_stopped_after_order_check"
    assert manifest["module_validation_demo_execution"] is True
    assert manifest["expired_signal_override_used"] is True
    assert manifest["strategy_valid"] is False
    assert manifest["production_valid"] is False
    assert manifest["order_check_called"] is True
    assert manifest["order_send_called"] is False
    assert fake.script_call_count("check_fixed_candidate_demo_order_check.py") == 1
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0
    assert "--module-validation-demo-execution" in order_check_command
    assert "--module-validation-acknowledgment" in order_check_command
    assert "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only" in order_check_command
    assert "--allow-expired-signal-for-demo-module-validation" in order_check_command
    assert "--expired-signal-override-acknowledgment" in order_check_command
    assert pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT in order_check_command


def test_expired_signal_override_without_module_validation_blocks_before_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        ack=False,
        scenario={"prep_expired_signal": True},
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_manual_approval_prep"
    assert fake.calls == []


@pytest.mark.parametrize("ack_value", ["", "wrong_ack"])
def test_expired_signal_override_missing_or_wrong_ack_blocks_before_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ack_value: str
) -> None:
    extra = [
        "--stop-after-request-construction",
        "--module-validation-demo-execution",
        "--allow-expired-signal-for-demo-module-validation",
    ]
    if ack_value:
        extra.extend(["--expired-signal-override-acknowledgment", ack_value])
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        *extra,
        ack=False,
        scenario={"prep_expired_signal": True},
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_manual_approval_prep"
    assert fake.calls == []


@pytest.mark.parametrize(
    "request_status",
    [
        "request_construction_blocked_digest_mismatch",
        "request_construction_dry_run_blocked_margin_policy",
        "request_construction_dry_run_blocked_broker_local_reconciliation",
        "request_construction_dry_run_blocked_duplicate_protection",
        "request_construction_dry_run_blocked_kill_switch",
    ],
)
def test_expired_signal_override_does_not_bypass_request_construction_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request_status: str
) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        "--stop-after-request-construction",
        "--module-validation-demo-execution",
        "--allow-stale-upstream-artifacts-for-demo-module-validation",
        "--module-validation-acknowledgment",
        "acknowledge_stale_upstream_artifacts_for_demo_module_validation_only",
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        pilot.EXPIRED_SIGNAL_OVERRIDE_ACKNOWLEDGMENT,
        ack=False,
        scenario={"prep_expired_signal": True, "request_status": request_status},
    )

    assert manifest["final_status"] == "demo_signal_to_order_pilot_blocked_request_construction"
    assert manifest["expired_signal_override_used"] is True
    assert fake.script_call_count("build_fixed_candidate_demo_request_construction_dry_run.py") == 1
    assert fake.script_call_count("check_fixed_candidate_demo_order_check.py") == 0
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0


def test_final_artifacts_contain_child_commands_and_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, _manifest, _fake = build(tmp_path, monkeypatch)
    assert len(read_csv(outputs["child_commands"])) == 7
    assert len(read_csv(outputs["child_results"])) == 7


def test_unexpected_error_is_captured_without_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _outputs, manifest, fake = build(
        tmp_path,
        monkeypatch,
        scenario={"raise_on": "run_fixed_candidate_demo_manual_approval_prep_pipeline_once.py"},
    )
    assert manifest["final_status"] == "demo_signal_to_order_pilot_error_unexpected"
    assert fake.script_call_count("send_fixed_candidate_demo_order_pilot.py") == 0
