from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_state_reconciliation_plan as state_plan


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
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
    data: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
    }
    data.update(overrides)
    return data


def execution_policy(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "account_currency": "EUR",
        "intended_demo_equity": 1000.0,
        "risk_percent_max": 0.5,
        "risk_amount_max": 5.0,
        "max_margin_usage_warning_ratio": 0.5,
        "max_margin_usage_warning_amount": 500.0,
        "max_margin_usage_ratio": 0.7,
        "max_margin_usage_amount": 700.0,
        "max_open_positions": 1,
        "safety_boundaries": {
            "real_money_allowed": False,
            "order_execution_allowed": False,
            "order_request_construction_allowed": False,
            "order_check_allowed": False,
            "manual_approval_required_before_any_future_demo_order": True,
        },
    }
    data.update(overrides)
    return data


def margin_validation_manifest(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "run_id": "source_margin_validation",
        "validation_status": "broker_safe_margin_validation_fixture_only_available_with_margin_warning",
        "source_nature": "synthetic_fixture",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "broker_margin_usage_ratio": 0.50167,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_profit_called": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    data.update(overrides)
    return data


def margin_snapshot(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "run_id": "source_margin_validation",
        "validation_status": "broker_safe_margin_validation_fixture_only_available_with_margin_warning",
        "source_nature": "synthetic_fixture",
        "account_mode_label": "demo",
        "account_currency": "EUR",
        "account_equity": 1000.0,
        "broker_margin_estimate": 501.67,
        "broker_margin_usage_ratio": 0.50167,
        "no_order_request_constructed": True,
        "no_order_execution_performed": True,
        "not_execution_approval": True,
    }
    data.update(overrides)
    return data


def no_order_evidence(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "run_id": "source_margin_validation",
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "no_order_send_called": True,
        "no_order_check_called": True,
        "no_order_calc_profit_called": True,
        "no_positions_get_called": True,
        "no_orders_get_called": True,
        "no_history_orders_get_called": True,
        "no_history_deals_get_called": True,
        "no_trading_decision_performed": True,
        "no_demo_broker_approval_performed": True,
    }
    data.update(overrides)
    return data


def write_source_artifacts(
    root: Path,
    *,
    manifest_data: dict[str, object] | None = None,
    snapshot_data: dict[str, object] | None = None,
    no_order_data: dict[str, object] | None = None,
    missing_manifest: bool = False,
    missing_snapshot: bool = False,
    missing_no_order: bool = False,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if not missing_manifest:
        write_json(root / state_plan.SOURCE_MANIFEST, manifest_data or margin_validation_manifest())
    if not missing_snapshot:
        write_json(root / state_plan.SOURCE_MARGIN_SNAPSHOT, snapshot_data or margin_snapshot())
    if not missing_no_order:
        write_csv(root / state_plan.SOURCE_NO_ORDER, [no_order_data or no_order_evidence()], list(no_order_evidence().keys()))
    (root / state_plan.SOURCE_REPORT).write_text("source report\n", encoding="utf-8")
    write_csv(root / state_plan.SOURCE_CHECKLIST, [], ["run_id"])
    write_csv(root / state_plan.SOURCE_WARNINGS, [], state_plan.WARNING_FIELDNAMES)
    return root


def make_args(
    tmp_path: Path,
    *,
    registry_data: dict[str, object] | None = None,
    policy_data: dict[str, object] | None = None,
    source_dir: Path | None = None,
) -> object:
    registry_path = write_json(tmp_path / "registry.json", registry_data or canonical_registry())
    policy_path = write_json(tmp_path / "policy.json", policy_data or execution_policy())
    if source_dir is None:
        source_dir = write_source_artifacts(tmp_path / "source")
    argv = [
        "--run-id",
        "unit_state_reconciliation_plan",
        "--broker-safe-margin-validation-dir",
        str(source_dir),
        "--canonical-registry",
        str(registry_path),
        "--demo-execution-policy",
        str(policy_path),
        "--future-state-json",
        str(tmp_path / "state" / "future_state.json"),
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    return state_plan.build_parser().parse_args(argv)


def build_valid_fixture_plan(tmp_path: Path) -> dict[str, Path]:
    return state_plan.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        state_plan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written_on_happy_path(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)

    for path in outputs.values():
        assert path.exists()


def test_fixture_source_produces_fixture_only(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "state_reconciliation_plan_fixture_only"
    assert manifest["plan_actionable"] is False
    assert manifest["recommended_next_step"] == "wait_for_live_shadow_signal_or_continue_no_order_monitoring"


def test_live_data_source_produces_available_no_order(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=margin_validation_manifest(
            validation_status="broker_safe_margin_validation_available_with_margin_warning",
            source_nature="live_data_shadow_signal",
        ),
        snapshot_data=margin_snapshot(
            validation_status="broker_safe_margin_validation_available_with_margin_warning",
            source_nature="live_data_shadow_signal",
        ),
    )
    outputs = state_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "state_reconciliation_plan_available_no_order"
    assert manifest["recommended_next_step"] == "build_fixed_candidate_demo_duplicate_protection_plan"


def test_missing_manifest_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_manifest=True)
    outputs = state_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_broker_safe_margin_validation_manifest"


def test_missing_margin_snapshot_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_snapshot=True)
    outputs = state_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_margin_snapshot"


def test_missing_no_order_evidence_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", missing_no_order=True)
    outputs = state_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_missing_no_order_evidence"


def test_bad_no_order_evidence_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(tmp_path / "source", no_order_data=no_order_evidence(no_order_send_called=False))
    outputs = state_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_unsafe_no_order_evidence"


def test_unacceptable_margin_validation_status_blocks(tmp_path: Path) -> None:
    source_dir = write_source_artifacts(
        tmp_path / "source",
        manifest_data=margin_validation_manifest(validation_status="blocked_mt5_import_failed"),
    )
    outputs = state_plan.build_outputs(make_args(tmp_path, source_dir=source_dir))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_unacceptable_margin_validation_status"


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    outputs = state_plan.build_outputs(make_args(tmp_path, registry_data=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_noncanonical_candidate"


def test_noncanonical_demo_execution_policy_blocks(tmp_path: Path) -> None:
    outputs = state_plan.build_outputs(make_args(tmp_path, policy_data=execution_policy(max_margin_usage_ratio=0.5)))
    manifest = read_json(outputs["manifest"])

    assert manifest["plan_status"] == "blocked_noncanonical_demo_execution_policy"


def test_state_schema_required_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["state_schema"])
    fields = {row["state_field"] for row in rows}

    assert set(state_plan.STATE_FIELDS) <= fields


def test_idempotency_composition_row_is_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["idempotency"])
    components = [row["component_name"] for row in rows if row["idempotency_area"] == "composition"]

    assert components == [
        "candidate_id",
        "symbol",
        "timeframe",
        "direction",
        "signal_time_server",
        "entry_reference_price",
        "sl_price",
        "tp_price",
    ]
    assert all(row["not_broker_request_field"] == "true" for row in rows)


def test_duplicate_protection_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["idempotency"])
    names = {row["component_name"] for row in rows}

    assert {
        "no_duplicate_signal_time_server",
        "no_duplicate_idempotency_key",
        "block_when_local_state_open_or_pending",
    } <= names


def test_failure_mode_rows_are_present(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["failure_modes"])
    modes = {row["failure_mode"] for row in rows}

    assert {
        "crash_before_state_write",
        "crash_after_manual_approval_before_future_execution",
        "broker_says_open_local_state_missing",
        "duplicate_run_on_same_signal",
        "stale_state_older_than_horizon",
    } <= modes


def test_future_broker_reads_are_future_only_and_not_executed(tmp_path: Path) -> None:
    outputs = build_valid_fixture_plan(tmp_path)
    rows = read_csv(outputs["future_broker_reads"])
    calls = {row["future_call_name"]: row for row in rows}

    assert {"positions_get", "orders_get", "history_orders_get", "history_deals_get"} <= set(calls)
    assert all(row["current_module_called"] == "false" for row in rows)
    assert calls["positions_get"]["allowed_only_in_future_reconciliation_module"] == "true"


def test_static_safety_grep_confirms_forbidden_calls_absent() -> None:
    source = Path(state_plan.__file__).read_text(encoding="utf-8")
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


def test_no_scheduler_loop_background_markers() -> None:
    source = Path(state_plan.__file__).read_text(encoding="utf-8")
    forbidden = ["Task Scheduler", "schtasks", "while True", "APScheduler", "threading.Timer"]

    for token in forbidden:
        assert token not in source
