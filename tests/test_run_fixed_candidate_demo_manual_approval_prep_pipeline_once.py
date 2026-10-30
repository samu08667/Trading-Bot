import csv
import json
import subprocess
from pathlib import Path

import pytest

from scripts import run_fixed_candidate_demo_manual_approval_prep_pipeline_once as pipeline


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def shadow_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "fixture_shadow",
        "shadow_status": "shadow_signal_detected",
        "source_nature": "live_data_shadow_signal",
        "shadow_decision_label": "shadow_signal_detected",
        "cycle_status": "demo_no_order_cycle_completed_would_signal",
        "manual_review_required": True,
        "blocking_warnings_count": 0,
        "unsafe_no_order_flag_count": 0,
        "missing_no_order_flag_count": 0,
        "no_order_boundary_confirmed": True,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "order_request_construction_allowed": False,
        "order_execution_allowed": False,
        "order_execution_performed": False,
        "order_check_called": False,
        "order_send_called": False,
        "order_request_constructed": False,
        "demo_broker_approval_performed": False,
        "future_state_json_written": False,
        "live_alignment_status": "live_data_aligned_with_mt5_latest_bar",
        "live_spread_gate_status": "live_spread_within_policy",
        "current_broker_spread_points": 2.0,
        "current_broker_spread_within_policy": True,
    }
    payload.update(overrides)
    return payload


def write_shadow(tmp_path: Path, payload: dict[str, object] | None = None) -> Path:
    shadow_dir = tmp_path / "shadow"
    write_json(shadow_dir / pipeline.SHADOW_MANIFEST, payload or shadow_manifest())
    return shadow_dir


def args_for(tmp_path: Path, shadow_dir: Path | None = None, *extra: str) -> object:
    argv = [
        "--run-id",
        "fixture_pipeline",
        "--shadow-signal-dir",
        str(shadow_dir or tmp_path / "missing_shadow"),
        "--output-dir",
        str(tmp_path / "pipeline_out"),
        "--canonical-registry",
        str(tmp_path / "canonical.json"),
        "--demo-execution-policy",
        str(tmp_path / "policy.json"),
        "--future-state-json",
        str(tmp_path / "future_state.json"),
        "--future-approval-record-json",
        str(tmp_path / "approval_record.json"),
        "--operator-decision-label",
        "approve_for_future_request_construction_only",
        "--operator-identity-ref",
        "operator_fixture",
        "--operator-warning-acknowledgment",
        "acknowledged_schema_warning_no_execution",
        "--overwrite",
    ]
    argv.extend(extra)
    return pipeline.build_parser().parse_args(argv)


def load_shadow_status(tmp_path: Path, payload: dict[str, object]) -> tuple[str | None, list[dict[str, object]]]:
    shadow_dir = write_shadow(tmp_path, payload)
    warnings: list[dict[str, object]] = []
    _manifest, status = pipeline.load_shadow(args_for(tmp_path, shadow_dir), warnings)  # type: ignore[arg-type]
    return status, warnings


def safe_manifest_for(step: pipeline.StepSpec, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": f"fixture_{step.key}",
        step.status_field: step.acceptable_statuses[0],
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_margin_called": True,
        "no_order_calc_profit_called": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_scheduler_added": True,
        "no_loop_added": True,
        "no_background_task_added": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
        "order_execution_allowed": False,
        "future_state_json_written": False,
        "blocking_warnings_count": 0,
    }
    if step.key == "broker_safe_margin_validation":
        payload["broker_margin_usage_ratio"] = 0.25
        payload["stepped_volume_lots"] = 0.05
        payload["validation_status"] = "broker_safe_margin_validation_available"
    if step.key == "broker_local_reconciliation":
        payload["reconciliation_status"] = "broker_local_reconciliation_clean_no_local_no_broker"
    if step.key == "live_signal_freshness":
        payload["freshness_status"] = "live_signal_freshness_fresh_current_or_latest_signal"
    if step.key == "approval_record_creation_dry_run":
        payload["creation_status"] = "manual_approval_record_creation_dry_run_no_record_created"
        payload["approval_record_created"] = False
        payload["future_approval_record_written"] = False
    if step.key == "approval_record_creation_real":
        payload["creation_status"] = "manual_approval_record_created_for_future_request_construction_only"
        payload["approval_record_created"] = True
        payload["future_approval_record_written"] = True
    payload.update(overrides)
    return payload


class FakeRunner:
    def __init__(
        self,
        output_root: Path,
        *,
        returncode_for: str | None = None,
        missing_manifest_for: str | None = None,
        status_override: tuple[str, str] | None = None,
        safety_violation_for: str | None = None,
        margin_ratio: float | None = None,
    ) -> None:
        self.output_root = output_root
        self.returncode_for = returncode_for
        self.missing_manifest_for = missing_manifest_for
        self.status_override = status_override
        self.safety_violation_for = safety_violation_for
        self.margin_ratio = margin_ratio
        self.calls: list[list[str]] = []
        self.shell_values: list[object] = []

    def __call__(self, command: list[str], *, capture_output: bool, text: bool, shell: bool, timeout: int) -> subprocess.CompletedProcess[str]:
        assert isinstance(command, list)
        assert capture_output is True
        assert text is True
        self.shell_values.append(shell)
        self.calls.append(command)
        step = self.step_for_command(command)
        if step is None:
            return subprocess.CompletedProcess(command, 1, "", "unexpected script")
        if self.returncode_for == step.key:
            return subprocess.CompletedProcess(command, 1, "stdout tail", "stderr tail")
        if self.missing_manifest_for != step.key:
            output_dir = Path(command[command.index("--output-dir") + 1])
            manifest = safe_manifest_for(step)
            if self.status_override and self.status_override[0] == step.key:
                manifest[step.status_field] = self.status_override[1]
            if step.key == "broker_safe_margin_validation" and self.margin_ratio is not None:
                manifest["broker_margin_usage_ratio"] = self.margin_ratio
                manifest["validation_status"] = "broker_safe_margin_validation_available_with_margin_warning"
            if self.safety_violation_for == step.key:
                manifest["broker_payload_constructed"] = True
            write_json(output_dir / step.manifest_name, manifest)
        return subprocess.CompletedProcess(command, 0, "child stdout tail", "child stderr tail")

    @staticmethod
    def step_for_command(command: list[str]) -> pipeline.StepSpec | None:
        script_name = Path(command[1]).name
        if script_name == "create_fixed_candidate_demo_manual_approval_record.py":
            return pipeline.BASE_STEPS[-1] if "--dry-run" in command else pipeline.REAL_APPROVAL_STEP
        for step in pipeline.BASE_STEPS:
            if Path(step.script).name == script_name:
                return step
        return None


def run_with_fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake: FakeRunner, *extra: str) -> tuple[dict[str, Path], dict[str, object], FakeRunner]:
    shadow_dir = write_shadow(tmp_path)
    monkeypatch.setattr(pipeline.subprocess, "run", fake)
    outputs = pipeline.build_outputs(args_for(tmp_path, shadow_dir, *extra))
    return outputs, read_json(outputs["manifest"]), fake


def child_command_args(outputs: dict[str, Path], step_key: str) -> tuple[list[str], dict[str, str]]:
    commands = read_csv(outputs["child_commands"])
    row = next(item for item in commands if item["step_key"] == step_key)
    return json.loads(row["command_args_json"]), row


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        pipeline.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_pipeline_blocks_if_shadow_signal_dir_is_missing(tmp_path: Path) -> None:
    outputs = pipeline.build_outputs(args_for(tmp_path))
    manifest = read_json(outputs["manifest"])

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_shadow_signal_not_detected"


def test_pipeline_blocks_if_shadow_signal_is_not_detected(tmp_path: Path) -> None:
    shadow_dir = write_shadow(tmp_path, shadow_manifest(shadow_status="shadow_no_signal"))
    outputs = pipeline.build_outputs(args_for(tmp_path, shadow_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_shadow_signal_not_detected"


def test_modern_shadow_manifest_with_direct_false_order_fields_passes_shadow_validation(tmp_path: Path) -> None:
    status, warnings = load_shadow_status(tmp_path, shadow_manifest())

    assert status is None
    assert warnings == []


def test_modern_shadow_manifest_with_missing_direct_order_fields_passes_when_no_order_evidence_is_safe(tmp_path: Path) -> None:
    payload = shadow_manifest()
    for key in (
        "order_execution_performed",
        "order_check_called",
        "order_send_called",
        "order_request_constructed",
        "demo_broker_approval_performed",
    ):
        payload.pop(key)

    status, warnings = load_shadow_status(tmp_path, payload)

    assert status is None
    assert warnings == []


def test_modern_shadow_manifest_with_null_direct_order_fields_passes_when_no_order_evidence_is_safe(tmp_path: Path) -> None:
    status, warnings = load_shadow_status(
        tmp_path,
        shadow_manifest(order_execution_performed=None, order_check_called=None, order_send_called=None),
    )

    assert status is None
    assert warnings == []


@pytest.mark.parametrize("direct_field", ["order_send_called", "order_check_called", "order_execution_performed"])
def test_shadow_validation_blocks_direct_true_order_fields(tmp_path: Path, direct_field: str) -> None:
    status, warnings = load_shadow_status(tmp_path, shadow_manifest(**{direct_field: True}))

    assert status == "manual_approval_prep_pipeline_blocked_shadow_signal_not_detected"
    assert warnings[0]["warning_code"] == "shadow_signal_not_detected"
    assert direct_field in str(warnings[0]["message"])


def test_shadow_validation_blocks_missing_no_order_send_called(tmp_path: Path) -> None:
    payload = shadow_manifest()
    payload.pop("no_order_send_called")

    status, warnings = load_shadow_status(tmp_path, payload)

    assert status == "manual_approval_prep_pipeline_blocked_shadow_signal_not_detected"
    assert "no_order_send_called" in str(warnings[0]["message"])


def test_shadow_validation_blocks_unaligned_live_signal(tmp_path: Path) -> None:
    status, warnings = load_shadow_status(
        tmp_path,
        shadow_manifest(live_alignment_status="live_data_blocked_db_lagging_mt5_latest_bar"),
    )

    assert status == "manual_approval_prep_pipeline_blocked_shadow_signal_not_detected"
    assert "live_alignment_status" in str(warnings[0]["message"])


def test_shadow_validation_blocks_live_spread_gate_not_within_policy(tmp_path: Path) -> None:
    status, warnings = load_shadow_status(
        tmp_path,
        shadow_manifest(
            live_spread_gate_status="blocked_current_spread_above_policy",
            current_broker_spread_points=16.0,
            current_broker_spread_within_policy=False,
        ),
    )

    assert status == "manual_approval_prep_pipeline_blocked_shadow_signal_not_detected"
    assert "live_spread_gate_status" in str(warnings[0]["message"])
    assert "current_broker_spread_within_policy" in str(warnings[0]["message"])


def test_shadow_validation_accepts_zero_current_spread_when_within_policy(tmp_path: Path) -> None:
    status, warnings = load_shadow_status(
        tmp_path,
        shadow_manifest(current_broker_spread_points=0.0, current_broker_spread_within_policy=True),
    )

    assert status is None
    assert warnings == []


def test_pipeline_blocks_before_broker_read_steps_without_allow_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    outputs, manifest, fake = run_with_fake(tmp_path, monkeypatch, fake)

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_broker_reads_not_allowed"
    assert manifest["allow_broker_read_checks"] is False
    assert manifest["broker_child_allow_broker_read_forwarded"] is False
    assert manifest["broker_child_allow_order_calc_margin_forwarded"] is False
    assert manifest["broker_read_children_require_explicit_flags"] is True
    assert len(fake.calls) == 5
    assert all("check_fixed_candidate_demo_broker_safe_margin_validation.py" not in command[1] for command in fake.calls)
    assert any(row["step_key"] == "broker_safe_margin_validation" for row in read_csv(outputs["child_results"]))
    margin_args, margin_row = child_command_args(outputs, "broker_safe_margin_validation")
    reconciliation_args, reconciliation_row = child_command_args(outputs, "broker_local_reconciliation")
    assert "--allow-broker-read" not in margin_args
    assert "--allow-order-calc-margin" not in margin_args
    assert "--allow-broker-read" not in reconciliation_args
    assert margin_row["allow_broker_read_forwarded"] == "false"
    assert margin_row["allow_order_calc_margin_forwarded"] == "false"
    assert reconciliation_row["allow_broker_read_forwarded"] == "false"


def test_happy_dry_run_path_completes_through_approval_record_creation_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    outputs, manifest, fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_completed_dry_run_ready_for_manual_real_approval_decision"
    assert manifest["final_step_completed"] == "approval_record_creation_dry_run"
    assert manifest["approval_record_created"] is False
    assert manifest["broker_child_allow_broker_read_forwarded"] is True
    assert manifest["broker_child_allow_order_calc_margin_forwarded"] is True
    assert len(fake.calls) == 15
    for path in outputs.values():
        assert path.exists()


def test_expired_signal_override_flags_are_forwarded_to_approval_dry_run_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    outputs, manifest, _fake = run_with_fake(
        tmp_path,
        monkeypatch,
        fake,
        "--allow-broker-read-checks",
        "--module-validation-demo-execution",
        "--allow-expired-signal-for-demo-module-validation",
        "--expired-signal-override-acknowledgment",
        "acknowledge_expired_signal_for_demo_module_validation_only",
    )
    approval_args, _approval_row = child_command_args(outputs, "approval_record_creation_dry_run")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_completed_dry_run_ready_for_manual_real_approval_decision"
    assert manifest["module_validation_demo_execution"] is True
    assert "--module-validation-demo-execution" in approval_args
    assert "--allow-expired-signal-for-demo-module-validation" in approval_args
    assert "--expired-signal-override-acknowledgment" in approval_args
    assert "acknowledge_expired_signal_for_demo_module_validation_only" in approval_args


def test_pipeline_mock_accepts_observed_margin_volume_from_child_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    _outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")
    margin_dir = Path(str(manifest["broker_safe_margin_validation_dir"]))
    margin_manifest = read_json(margin_dir / "fixed_candidate_demo_broker_safe_margin_validation_manifest.json")

    assert margin_manifest["stepped_volume_lots"] == 0.05
    assert margin_manifest["validation_status"] == "broker_safe_margin_validation_available"
    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_completed_dry_run_ready_for_manual_real_approval_decision"


def test_child_commands_forward_broker_read_flags_when_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    margin_args, margin_row = child_command_args(outputs, "broker_safe_margin_validation")
    reconciliation_args, reconciliation_row = child_command_args(outputs, "broker_local_reconciliation")

    assert manifest["broker_child_allow_broker_read_forwarded"] is True
    assert manifest["broker_child_allow_order_calc_margin_forwarded"] is True
    assert "--allow-broker-read" in margin_args
    assert "--allow-order-calc-margin" in margin_args
    assert "--allow-broker-read" in reconciliation_args
    assert "--allow-order-calc-margin" not in reconciliation_args
    assert margin_row["allow_broker_read_forwarded"] == "true"
    assert margin_row["allow_order_calc_margin_forwarded"] == "true"
    assert reconciliation_row["allow_broker_read_forwarded"] == "true"
    assert reconciliation_row["allow_order_calc_margin_forwarded"] == "false"


def test_happy_dry_run_path_does_not_create_real_approval_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    _, manifest, fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert manifest["approval_record_json_written"] is False
    assert all("--dry-run" in command or "create_fixed_candidate_demo_manual_approval_record.py" not in command[1] for command in fake.calls)


def test_real_approval_path_only_runs_when_explicitly_allowed_and_operator_fields_are_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    _, manifest, fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks", "--allow-real-approval-record")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_completed_real_approval_record_created_no_request"
    assert manifest["approval_record_created"] is True
    assert len(fake.calls) == 16
    assert "create_fixed_candidate_demo_manual_approval_record.py" in fake.calls[-1][1]
    assert "--dry-run" not in fake.calls[-1]


def test_real_approval_path_still_creates_no_request_payload_or_order_object(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    _, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks", "--allow-real-approval-record")

    assert manifest["request_construction_performed"] is False
    assert manifest["broker_payload_constructed"] is False
    assert manifest["order_object_constructed"] is False
    assert manifest["order_execution_performed"] is False


def test_child_nonzero_return_code_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out", returncode_for="order_shadow_plan")
    _outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_child_failure"
    assert manifest["failed_step"] == "order_shadow_plan"


def test_missing_child_manifest_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out", missing_manifest_for="risk_volume_shadow_plan")
    _outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_missing_manifest"
    assert manifest["failed_step"] == "risk_volume_shadow_plan"


def test_unacceptable_child_status_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out", status_override=("order_shadow_plan", "blocked_by_source"))
    _outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_step_status"
    assert manifest["failed_step"] == "order_shadow_plan"


def test_safety_boundary_violation_in_child_manifest_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out", safety_violation_for="would_signal_review")
    _outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_safety_boundary_violation"


def test_stale_freshness_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out", status_override=("live_signal_freshness", "live_signal_freshness_stale_beyond_horizon"))
    _outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_stale_signal"


def test_broker_local_reconciliation_hold_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out", status_override=("broker_local_reconciliation", "broker_local_reconciliation_hold_broker_position_exists"))
    _outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_broker_local_reconciliation"


def test_margin_above_hard_cap_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out", margin_ratio=0.8)
    _outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_margin"


def test_margin_warning_below_hard_cap_does_not_block_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out", margin_ratio=0.6)
    _outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_completed_dry_run_ready_for_manual_real_approval_decision"
    assert manifest["failed_step"] == ""


def test_approval_dry_run_blocking_warnings_block_real_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    original = fake.step_for_command

    def fake_step(command: list[str]) -> pipeline.StepSpec | None:
        return original(command)

    fake.step_for_command = staticmethod(fake_step)  # type: ignore[method-assign]
    base_call = fake.__call__

    def wrapped(command: list[str], *, capture_output: bool, text: bool, shell: bool, timeout: int) -> subprocess.CompletedProcess[str]:
        step = FakeRunner.step_for_command(command)
        if step and step.key == "approval_record_creation_dry_run":
            output_dir = Path(command[command.index("--output-dir") + 1])
            write_json(output_dir / step.manifest_name, safe_manifest_for(step, blocking_warnings_count=1))
            fake.calls.append(command)
            fake.shell_values.append(shell)
            return subprocess.CompletedProcess(command, 0, "", "")
        return base_call(command, capture_output=capture_output, text=text, shell=shell, timeout=timeout)

    monkeypatch.setattr(pipeline.subprocess, "run", wrapped)
    shadow_dir = write_shadow(tmp_path)
    outputs = pipeline.build_outputs(args_for(tmp_path, shadow_dir, "--allow-broker-read-checks", "--allow-real-approval-record"))
    manifest = read_json(outputs["manifest"])

    assert manifest["pipeline_status"] == "manual_approval_prep_pipeline_blocked_approval_dry_run"
    assert len(fake.calls) == 15


def test_child_commands_use_allowlisted_script_names_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    outputs, _manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")
    commands = read_csv(outputs["child_commands"])

    assert commands
    assert all(row["allowed_child_script"] == "true" for row in commands)
    joined = "\n".join(row["command_args_json"] for row in commands)
    assert "paper_signal_logger" not in joined
    assert "paper_trade_tracker" not in joined
    assert "run_fixed_candidate_fixed_rule_replay_backtest" not in joined


def test_child_commands_do_not_use_shell_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    assert fake.shell_values
    assert all(value is False for value in fake.shell_values)


def test_manifest_includes_all_child_output_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    _outputs, manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")

    for key in (
        "would_signal_review_dir",
        "order_shadow_plan_dir",
        "order_request_shadow_design_dir",
        "risk_volume_shadow_plan_dir",
        "margin_feasibility_plan_dir",
        "broker_safe_margin_validation_dir",
        "state_reconciliation_plan_dir",
        "duplicate_protection_plan_dir",
        "manual_approval_kill_switch_plan_dir",
        "future_broker_state_reconciliation_check_plan_dir",
        "future_request_construction_readiness_plan_dir",
        "broker_local_reconciliation_dir",
        "live_signal_freshness_dir",
        "manual_approval_gate_dry_run_dir",
        "approval_record_creation_dry_run_dir",
    ):
        assert manifest[key]


def test_no_order_evidence_rows_are_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRunner(tmp_path / "pipeline_out")
    outputs, _manifest, _fake = run_with_fake(tmp_path, monkeypatch, fake, "--allow-broker-read-checks")
    evidence = read_csv(outputs["no_order"])[0]

    assert evidence["request_construction_performed"] == "false"
    assert evidence["order_send_called"] == "false"
    assert evidence["order_execution_performed"] == "false"


def test_static_safety_grep_confirms_no_forbidden_order_history_call_signatures() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    forbidden = [
        "order_send(",
        "order_check(",
        "order_calc_profit(",
        "history_orders_get(",
        "history_deals_get(",
    ]
    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_scheduler_loop_background_behavior() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    forbidden = ["while " + "True", "Background" + "Scheduler", "schedule" + ".every", "threading" + ".", "asyncio" + "."]
    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_request_construction_execution_behavior() -> None:
    source = Path(pipeline.__file__).read_text(encoding="utf-8")
    forbidden = ["request = {", "payload = {", "execute_now", "send_now"]
    for token in forbidden:
        assert token not in source
