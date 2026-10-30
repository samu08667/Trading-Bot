from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_recent_signal_opportunity_scan as scan


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
    }
    payload.update(overrides)
    return payload


def demo_policy(**boundary_overrides: object) -> dict[str, object]:
    boundaries: dict[str, object] = {
        "paper_only_until_explicit_future_change": True,
        "real_money_allowed": False,
        "broker_connection_allowed_for_this_policy_file": False,
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


def row_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "time_server": "2026-06-01 22:00:00",
        "open": 1.2499,
        "high": 1.2502,
        "low": 1.2497,
        "close": 1.25,
        "atr_20": 0.0006,
        "spread": 6.0,
        "hour_session": "Off_hours",
        "close_to_ma_fast_atr_20": 0.7,
        "tick_volume_percentile_100": 0.2,
        "tick_volume": 123,
        "volume": 123,
    }
    payload.update(overrides)
    return payload


def create_db(tmp_path: Path, rows: list[dict[str, object]], *, table: str = "price_features", omit_columns: set[str] | None = None) -> Path:
    omit_columns = omit_columns or set()
    db_path = tmp_path / "features.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        ("symbol", "TEXT"),
        ("timeframe", "TEXT"),
        ("time_server", "TEXT"),
        ("open", "REAL"),
        ("high", "REAL"),
        ("low", "REAL"),
        ("close", "REAL"),
        ("atr_20", "REAL"),
        ("spread", "REAL"),
        ("hour_session", "TEXT"),
        ("close_to_ma_fast_atr_20", "REAL"),
        ("tick_volume_percentile_100", "REAL"),
        ("tick_volume", "REAL"),
        ("volume", "REAL"),
    ]
    active = [(name, kind) for name, kind in columns if name not in omit_columns]
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"CREATE TABLE {table} ({', '.join(f'{name} {kind}' for name, kind in active)})")
        column_names = [name for name, _kind in active]
        placeholders = ", ".join("?" for _ in column_names)
        for row in rows:
            connection.execute(
                f"INSERT INTO {table} ({', '.join(column_names)}) VALUES ({placeholders})",
                [row.get(name) for name in column_names],
            )
    return db_path


def fixture_paths(tmp_path: Path, *, rows: list[dict[str, object]] | None = None) -> dict[str, Path]:
    registry = write_json(tmp_path / "config" / "canonical.json", canonical_registry())
    policy = write_json(tmp_path / "config" / "policy.json", demo_policy())
    db_path = create_db(tmp_path, rows if rows is not None else [row_payload()])
    return {"registry": registry, "policy": policy, "db": db_path}


def make_args(tmp_path: Path, paths: dict[str, Path], *extra: str) -> object:
    return scan.build_parser().parse_args(
        [
            "--run-id",
            "unit_recent_signal_scan",
            "--db-path",
            str(paths["db"]),
            "--canonical-registry",
            str(paths["registry"]),
            "--demo-execution-policy",
            str(paths["policy"]),
            "--symbol",
            "GBPUSD",
            "--timeframe",
            "M15",
            "--limit",
            "500",
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
            *extra,
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        scan.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written_on_happy_path(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    outputs = scan.build_outputs(make_args(tmp_path, paths))

    for key in [
        "summary",
        "condition_counts",
        "recent_rows",
        "full_matches",
        "near_misses",
        "missing_breakdown",
        "report",
        "warnings",
        "manifest",
    ]:
        assert outputs[key].exists()


def test_full_match_status_when_at_least_one_row_matches_all_conditions(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    full_matches = read_csv(outputs["full_matches"])

    assert manifest["scan_status"] == "recent_signal_opportunity_scan_available_with_matches"
    assert manifest["full_match_rows"] == 1
    assert full_matches[0]["historical_or_recent_observation_only"] == "true"
    assert full_matches[0]["manual_review_required"] == "false"


def test_near_miss_only_status(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path, rows=[row_payload(tick_volume_percentile_100=0.8)])
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])
    near_misses = read_csv(outputs["near_misses"])

    assert manifest["scan_status"] == "recent_signal_opportunity_scan_available_near_misses_only"
    assert manifest["near_miss_rows"] == 1
    assert "missing_volume_bucket" in near_misses[0]["missing_conditions"]


def test_no_recent_matches_status(tmp_path: Path) -> None:
    paths = fixture_paths(
        tmp_path,
        rows=[row_payload(hour_session="New_York", close_to_ma_fast_atr_20=-1.0, tick_volume_percentile_100=0.8)],
    )
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["scan_status"] == "recent_signal_opportunity_scan_available_no_recent_matches"
    assert manifest["full_match_rows"] == 0
    assert manifest["near_miss_rows"] == 0


def test_missing_db_blocks(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    missing_db = tmp_path / "missing.db"
    paths["db"] = missing_db
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["scan_status"] == "blocked_missing_db"


def test_missing_table_blocks(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    paths["db"] = create_db(tmp_path / "other", [row_payload()], table="market_features")
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["scan_status"] == "blocked_missing_required_table"


def test_missing_required_columns_blocks(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    paths["db"] = create_db(tmp_path / "missing_col", [row_payload()], omit_columns={"spread"})
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["scan_status"] == "blocked_missing_required_columns"


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    write_json(paths["registry"], canonical_registry(max_spread_points=2.5))
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["scan_status"] == "blocked_noncanonical_candidate"


def test_noncanonical_demo_execution_policy_blocks(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    write_json(paths["policy"], demo_policy(order_request_construction_allowed=True))
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["scan_status"] == "blocked_noncanonical_demo_execution_policy"


def test_read_only_db_uri_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = fixture_paths(tmp_path)
    original_connect = sqlite3.connect
    calls: list[tuple[object, dict[str, object]]] = []

    def tracking_connect(database: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        calls.append((database, dict(kwargs)))
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(scan.sqlite3, "connect", tracking_connect)
    scan.build_outputs(make_args(tmp_path, paths))

    assert any("mode=ro" in str(database) and kwargs.get("uri") is True for database, kwargs in calls)


def test_condition_count_rows_are_present(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    counts = read_csv(outputs["condition_counts"])
    names = {row["condition_name"] for row in counts}

    assert "scanned_rows" in names
    assert "full_match_rows" in names
    assert "bucket_pair_match_rows" in names


def test_missing_condition_breakdown_rows_are_present(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path, rows=[row_payload(hour_session="London", spread=20.0)])
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    rows = read_csv(outputs["missing_breakdown"])
    names = {row["missing_condition"] for row in rows}

    assert "missing_session" in names
    assert "missing_spread_gate" in names


def test_latest_timestamp_fields_are_present(tmp_path: Path) -> None:
    paths = fixture_paths(
        tmp_path,
        rows=[
            row_payload(time_server="2026-06-01 22:00:00", hour_session="London", tick_volume_percentile_100=0.8),
            row_payload(time_server="2026-06-01 22:15:00"),
        ],
    )
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    manifest = read_json(outputs["manifest"])

    assert manifest["latest_row_time_server"] == "2026-06-01 22:15:00"
    assert manifest["latest_full_match_time_server"] == "2026-06-01 22:15:00"


def test_full_matches_are_observation_only_and_non_actionable(tmp_path: Path) -> None:
    paths = fixture_paths(tmp_path)
    outputs = scan.build_outputs(make_args(tmp_path, paths))
    summary = read_csv(outputs["summary"])[0]
    full_match = read_csv(outputs["full_matches"])[0]

    assert summary["historical_or_recent_observation_only"] == "true"
    assert summary["manual_review_required"] == "false"
    assert full_match["historical_or_recent_observation_only"] == "true"
    assert full_match["manual_review_required"] == "false"


def test_recommended_next_step_changes_by_scan_result(tmp_path: Path) -> None:
    full_paths = fixture_paths(tmp_path / "full")
    full_manifest = read_json(scan.build_outputs(make_args(tmp_path / "full", full_paths))["manifest"])
    near_paths = fixture_paths(tmp_path / "near", rows=[row_payload(tick_volume_percentile_100=0.8)])
    near_manifest = read_json(scan.build_outputs(make_args(tmp_path / "near", near_paths))["manifest"])
    none_paths = fixture_paths(
        tmp_path / "none",
        rows=[row_payload(hour_session="New_York", close_to_ma_fast_atr_20=-1.0, tick_volume_percentile_100=0.8)],
    )
    none_manifest = read_json(scan.build_outputs(make_args(tmp_path / "none", none_paths))["manifest"])

    assert full_manifest["recommended_next_step"] == "review_recent_match_timestamps_and_run_shadow_signal_on_current_live_row_if_relevant"
    assert near_manifest["recommended_next_step"] == "continue_no_order_monitoring_focus_on_missing_conditions"
    assert none_manifest["recommended_next_step"] == "continue_no_order_monitoring_or_expand_recent_scan_window_without_changing_strategy"


def test_static_safety_grep_confirms_forbidden_broker_order_calls_are_absent() -> None:
    source = Path(scan.__file__).read_text(encoding="utf-8")
    forbidden = [
        "order_" + "send(",
        "order_" + "check(",
        "order_" + "calc_margin(",
        "order_" + "calc_profit(",
        "positions_" + "get(",
        "orders_" + "get(",
        "history_orders_" + "get(",
        "history_deals_" + "get(",
        "Meta" + "Trader5",
        "mt5" + ".initialize",
    ]

    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_scheduler_or_background_markers() -> None:
    source = Path(scan.__file__).read_text(encoding="utf-8")
    forbidden = ["while True", "BackgroundScheduler", "threading.", "asyncio.", "schedule.every"]

    for token in forbidden:
        assert token not in source


def test_static_safety_grep_confirms_no_strategy_optimization_or_tuning_terms() -> None:
    source = Path(scan.__file__).read_text(encoding="utf-8").lower()

    assert "optimiz" not in source
    assert "tuning" not in source
