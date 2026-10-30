from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import check_fixed_candidate_demo_live_signal_freshness as freshness


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
        "safety_boundaries": boundaries,
    }


def would_signal_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "review_status": "would_signal_review_available_no_order",
        "source_nature": "live_data_shadow_signal",
        "shadow_status": "shadow_signal_detected",
        "manual_review_required": True,
        "actionable_signal": False,
        "order_execution_allowed": False,
        "order_request_construction_allowed": False,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "time_server": "2026-06-01 22:15:00",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
    }
    payload.update(overrides)
    return payload


def reconciliation_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "reconciliation_status": "broker_local_reconciliation_clean_no_local_no_broker",
        "source_nature": "live_data_shadow_signal",
        "broker_position_count_symbol": 0,
        "broker_pending_order_count_symbol": 0,
        "request_construction_allowed_now": False,
        "no_order_execution_performed": True,
        "no_order_request_constructed": True,
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
    }
    payload.update(overrides)
    return payload


def future_readiness_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "plan_status": "future_request_construction_readiness_plan_available_no_order",
        "source_nature": "live_data_shadow_signal",
        "request_construction_allowed_now": False,
        "broker_request_constructed": False,
        "broker_payload_constructed": False,
        "order_object_constructed": False,
    }
    payload.update(overrides)
    return payload


def create_db(path: Path, latest_time: str | None, *, missing_table: bool = False, missing_time_column: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        if missing_table:
            connection.execute("CREATE TABLE something_else (time_server TEXT)")
        elif missing_time_column:
            connection.execute("CREATE TABLE price_features (symbol TEXT, timeframe TEXT)")
            connection.execute("INSERT INTO price_features (symbol, timeframe) VALUES (?, ?)", ("GBPUSD", "M15"))
        else:
            connection.execute("CREATE TABLE price_features (time_server TEXT, symbol TEXT, timeframe TEXT)")
            if latest_time is not None:
                connection.execute(
                    "INSERT INTO price_features (time_server, symbol, timeframe) VALUES (?, ?, ?)",
                    (latest_time, "GBPUSD", "M15"),
                )
        connection.commit()
    return path


def write_fixture_sources(
    tmp_path: Path,
    *,
    latest_time: str | None = "2026-06-01 22:15:00",
    would_payload: dict[str, object] | None = None,
    recon_payload: dict[str, object] | None = None,
    registry_payload: dict[str, object] | None = None,
    policy_payload: dict[str, object] | None = None,
    future_payload: dict[str, object] | None = None,
    missing_would_signal: bool = False,
    missing_reconciliation: bool = False,
    missing_db: bool = False,
    missing_table: bool = False,
    missing_time_column: bool = False,
) -> dict[str, Path]:
    would_dir = tmp_path / "would"
    recon_dir = tmp_path / "recon"
    future_dir = tmp_path / "future"
    if not missing_would_signal:
        write_json(would_dir / freshness.WOULD_SIGNAL_MANIFEST, would_payload or would_signal_manifest())
    if not missing_reconciliation:
        write_json(recon_dir / freshness.BROKER_LOCAL_RECONCILIATION_MANIFEST, recon_payload or reconciliation_manifest())
    write_json(future_dir / freshness.FUTURE_REQUEST_READINESS_MANIFEST, future_payload or future_readiness_manifest())
    registry = write_json(tmp_path / "config" / "canonical.json", registry_payload or canonical_registry())
    policy = write_json(tmp_path / "config" / "policy.json", policy_payload or demo_policy())
    db_path = tmp_path / "db" / "features.db"
    if not missing_db:
        create_db(db_path, latest_time, missing_table=missing_table, missing_time_column=missing_time_column)
    return {
        "would": would_dir,
        "recon": recon_dir,
        "future": future_dir,
        "registry": registry,
        "policy": policy,
        "db": db_path,
    }


def make_args(tmp_path: Path, paths: dict[str, Path]) -> object:
    return freshness.build_parser().parse_args(
        [
            "--run-id",
            "unit_live_signal_freshness",
            "--would-signal-review-dir",
            str(paths["would"]),
            "--broker-local-reconciliation-dir",
            str(paths["recon"]),
            "--future-request-readiness-plan-dir",
            str(paths["future"]),
            "--canonical-registry",
            str(paths["registry"]),
            "--demo-execution-policy",
            str(paths["policy"]),
            "--db-path",
            str(paths["db"]),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )


def build_and_manifest(tmp_path: Path, paths: dict[str, Path]) -> tuple[dict[str, Path], dict[str, object]]:
    outputs = freshness.build_outputs(make_args(tmp_path, paths))
    return outputs, read_json(outputs["manifest"])


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        freshness.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_fresh_current_or_latest_signal_when_times_equal(tmp_path: Path) -> None:
    outputs, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, latest_time="2026-06-01 22:15:00"))

    assert manifest["freshness_status"] == "live_signal_freshness_fresh_current_or_latest_signal"
    assert manifest["bars_elapsed"] == 0
    assert manifest["is_fresh"] is True
    assert outputs["timing"].exists()


def test_fresh_within_horizon(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, latest_time="2026-06-02 00:45:00"))

    assert manifest["freshness_status"] == "live_signal_freshness_fresh_within_horizon"
    assert manifest["bars_elapsed"] == 10
    assert manifest["future_manual_approval_allowed_now"] is False


def test_stale_beyond_horizon(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, latest_time="2026-06-02 01:00:00"))

    assert manifest["freshness_status"] == "live_signal_freshness_stale_beyond_horizon"
    assert manifest["bars_elapsed"] == 11
    assert manifest["is_stale"] is True
    assert manifest["recommended_next_step"] == "wait_for_new_live_data_would_signal"


def test_feature_data_inconsistent_when_latest_far_behind_signal(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, latest_time="2026-06-01 21:45:00"))

    assert manifest["freshness_status"] == "blocked_feature_data_inconsistent"
    assert manifest["future_manual_approval_allowed_now"] is False


def test_missing_db_blocks(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, missing_db=True))

    assert manifest["freshness_status"] == "blocked_db_missing"


def test_missing_table_blocks(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, missing_table=True))

    assert manifest["freshness_status"] == "blocked_missing_required_table"


def test_missing_required_columns_blocks(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, missing_time_column=True))

    assert manifest["freshness_status"] == "blocked_missing_required_columns"


def test_missing_would_signal_review_blocks(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, missing_would_signal=True))

    assert manifest["freshness_status"] == "blocked_missing_would_signal_review"


def test_unacceptable_would_signal_review_status_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, would_payload=would_signal_manifest(review_status="hold"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["freshness_status"] == "blocked_unacceptable_would_signal_review_status"


def test_upstream_blocked_live_alignment_status_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(
        tmp_path,
        would_payload=would_signal_manifest(
            live_alignment_status="live_data_blocked_db_lagging_mt5_latest_bar",
            evaluated_feature_time_server="2026-06-10 22:45:00",
            latest_mt5_closed_bar_time_server="2026-06-11 01:15:00",
        ),
    )
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["freshness_status"] == "blocked_upstream_live_alignment_status"
    assert manifest["live_alignment_status"] == "live_data_blocked_db_lagging_mt5_latest_bar"
    assert manifest["latest_mt5_closed_bar_time_server"] == "2026-06-11 01:15:00"


def test_missing_broker_local_reconciliation_blocks(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, missing_reconciliation=True))

    assert manifest["freshness_status"] == "blocked_missing_broker_local_reconciliation"


def test_unacceptable_broker_local_reconciliation_status_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, recon_payload=reconciliation_manifest(reconciliation_status="hold"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["freshness_status"] == "blocked_unacceptable_broker_local_reconciliation_status"


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, registry_payload=canonical_registry(symbol="EURUSD"))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["freshness_status"] == "blocked_noncanonical_candidate"


def test_noncanonical_demo_execution_policy_blocks(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, policy_payload=demo_policy(order_request_construction_allowed=True))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["freshness_status"] == "blocked_noncanonical_demo_execution_policy"


def test_future_request_readiness_manifest_is_optional_but_validated_if_present(tmp_path: Path) -> None:
    paths = write_fixture_sources(tmp_path, future_payload=future_readiness_manifest(request_construction_allowed_now=True))
    _, manifest = build_and_manifest(tmp_path, paths)

    assert manifest["freshness_status"] == "blocked_unacceptable_future_request_readiness_status"


def test_stale_result_keeps_manual_approval_false(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, latest_time="2026-06-02 01:15:00"))

    assert manifest["future_manual_approval_allowed_now"] is False
    assert manifest["request_construction_allowed_now"] is False


def test_fresh_result_still_keeps_manual_approval_false(tmp_path: Path) -> None:
    _, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path, latest_time="2026-06-02 00:00:00"))

    assert manifest["is_fresh"] is True
    assert manifest["future_manual_approval_allowed_now"] is False
    assert manifest["request_construction_allowed_now"] is False


def test_recommended_next_step_differs_for_fresh_stale_and_unverifiable(tmp_path: Path) -> None:
    _, fresh_manifest = build_and_manifest(tmp_path / "fresh", write_fixture_sources(tmp_path / "fresh", latest_time="2026-06-02 00:00:00"))
    _, stale_manifest = build_and_manifest(tmp_path / "stale", write_fixture_sources(tmp_path / "stale", latest_time="2026-06-02 01:15:00"))
    _, blocked_manifest = build_and_manifest(tmp_path / "blocked", write_fixture_sources(tmp_path / "blocked", missing_db=True))

    assert fresh_manifest["recommended_next_step"] == "build_or_run_manual_approval_dry_run_gate_only"
    assert stale_manifest["recommended_next_step"] == "wait_for_new_live_data_would_signal"
    assert blocked_manifest["recommended_next_step"] == "refresh_no_order_live_data_and_rerun_freshness_check"


def test_no_order_evidence_rows_are_present(tmp_path: Path) -> None:
    outputs, manifest = build_and_manifest(tmp_path, write_fixture_sources(tmp_path))
    evidence = read_csv(outputs["no_order"])[0]

    assert evidence["no_order_execution_performed"] == "true"
    assert evidence["no_order_request_constructed"] == "true"
    assert evidence["no_db_mutation_performed"] == "true"
    assert manifest["no_child_scripts_executed"] is True


def test_static_safety_grep_confirms_forbidden_broker_order_calls_absent() -> None:
    source = Path(freshness.__file__).read_text(encoding="utf-8")
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
    source = Path(freshness.__file__).read_text(encoding="utf-8")
    forbidden = ["while " + "True", "Background" + "Scheduler", "schedule" + ".every", "threading" + ".", "asyncio" + "."]

    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_optimization_or_tuning_behavior() -> None:
    source = Path(freshness.__file__).read_text(encoding="utf-8").lower()

    assert "optimiz" not in source
    assert "tuning" not in source
