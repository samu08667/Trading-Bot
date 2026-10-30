from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

import pytest

from scripts import run_fixed_candidate_train_only_threshold_oos_replay as replay


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def canonical_registry(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "max_spread_points": 15.0,
    }
    payload.update(overrides)
    return payload


def train_only_thresholds(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "threshold_lineage": "train_only",
        "calibration_scope": "train_window_only",
        "train_end_time": "2024-12-31 23:59:59",
        "full_sample_thresholds_used": False,
        "oos_rows_used_for_thresholds": False,
        "required_conditions": {
            "close_to_ma_fast_atr_20": "high_tercile",
            "tick_volume_percentile_100": "mid_tercile",
        },
        "features": {
            "close_to_ma_fast_atr_20": {
                "low_mid_cutoff": 1.0,
                "mid_high_cutoff": 2.0,
            },
            "tick_volume_percentile_100": {
                "low_mid_cutoff": 10.0,
                "mid_high_cutoff": 20.0,
            },
        },
    }
    payload.update(overrides)
    return payload


def fixture_rows() -> list[dict[str, object]]:
    return [
        {
            "time_server": "2024-12-31 23:59:59",
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "hour_session": "Off_hours",
            "spread": 10.0,
            "close_to_ma_fast_atr_20": 3.0,
            "tick_volume_percentile_100": 15.0,
            "close_to_ma_fast_atr_20_bucket": "low_tercile",
            "tick_volume_percentile_100_bucket": "low_tercile",
            "R_multiple": 99.0,
            "exit_reason": "paper_tp_hit",
        },
        {
            "time_server": "2025-01-01 00:00:00",
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "hour_session": "London",
            "spread": 10.0,
            "close_to_ma_fast_atr_20": 3.0,
            "tick_volume_percentile_100": 15.0,
            "close_to_ma_fast_atr_20_bucket": "low_tercile",
            "tick_volume_percentile_100_bucket": "low_tercile",
            "R_multiple": 99.0,
            "exit_reason": "paper_tp_hit",
        },
        {
            "time_server": "2025-01-01 00:01:00",
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "hour_session": "Off_hours",
            "spread": 10.0,
            "close_to_ma_fast_atr_20": 2.5,
            "tick_volume_percentile_100": 15.0,
            "close_to_ma_fast_atr_20_bucket": "low_tercile",
            "tick_volume_percentile_100_bucket": "low_tercile",
            "R_multiple": 1.5,
            "exit_reason": "paper_tp_hit",
        },
        {
            "time_server": "2025-01-01 00:02:00",
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "hour_session": "Off_hours",
            "spread": 10.0,
            "close_to_ma_fast_atr_20": 2.5,
            "tick_volume_percentile_100": 25.0,
            "close_to_ma_fast_atr_20_bucket": "high_tercile",
            "tick_volume_percentile_100_bucket": "mid_tercile",
            "R_multiple": 4.0,
            "exit_reason": "paper_tp_hit",
        },
        {
            "time_server": "2025-01-01 00:03:00",
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "hour_session": "Off_hours",
            "spread": 10.0,
            "close_to_ma_fast_atr_20": 0.5,
            "tick_volume_percentile_100": 15.0,
            "close_to_ma_fast_atr_20_bucket": "high_tercile",
            "tick_volume_percentile_100_bucket": "mid_tercile",
            "R_multiple": 5.0,
            "exit_reason": "paper_tp_hit",
        },
        {
            "time_server": "2025-01-01 00:04:00",
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "hour_session": "Off_hours",
            "spread": 20.0,
            "close_to_ma_fast_atr_20": 2.5,
            "tick_volume_percentile_100": 15.0,
            "close_to_ma_fast_atr_20_bucket": "high_tercile",
            "tick_volume_percentile_100_bucket": "mid_tercile",
            "R_multiple": 6.0,
            "exit_reason": "paper_tp_hit",
        },
        {
            "time_server": "2025-01-01 00:05:00",
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "hour_session": "Off_hours",
            "spread": 10.0,
            "close_to_ma_fast_atr_20": 2.5,
            "tick_volume_percentile_100": 15.0,
            "close_to_ma_fast_atr_20_bucket": "low_tercile",
            "tick_volume_percentile_100_bucket": "low_tercile",
            "R_multiple": -1.0,
            "exit_reason": "paper_sl_hit",
        },
        {
            "time_server": "2025-01-01 00:06:00",
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "hour_session": "Off_hours",
            "spread": 10.0,
            "close_to_ma_fast_atr_20": 3.0,
            "tick_volume_percentile_100": 12.0,
            "close_to_ma_fast_atr_20_bucket": "low_tercile",
            "tick_volume_percentile_100_bucket": "low_tercile",
            "R_multiple": 0.5,
            "exit_reason": "paper_timeout",
        },
    ]


def write_feature_db(
    path: Path,
    *,
    include_table: bool = True,
    missing_columns: set[str] | None = None,
    include_outcomes: bool = True,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "time_server",
        "symbol",
        "timeframe",
        "hour_session",
        "spread",
        "close_to_ma_fast_atr_20",
        "tick_volume_percentile_100",
        "close_to_ma_fast_atr_20_bucket",
        "tick_volume_percentile_100_bucket",
    ]
    if include_outcomes:
        columns.extend(["R_multiple", "exit_reason"])
    for column in missing_columns or set():
        columns.remove(column)
    with sqlite3.connect(path) as connection:
        if include_table:
            defs = []
            for column in columns:
                column_type = "REAL" if column in {"spread", "close_to_ma_fast_atr_20", "tick_volume_percentile_100", "R_multiple"} else "TEXT"
                defs.append(f"{replay.quote_identifier(column)} {column_type}")
            connection.execute(f"CREATE TABLE {replay.quote_identifier('price_features')} ({', '.join(defs)})")
            for row in fixture_rows():
                values = [row.get(column) for column in columns]
                placeholders = ",".join("?" for _ in columns)
                connection.execute(
                    f"INSERT INTO {replay.quote_identifier('price_features')} "
                    f"({', '.join(replay.quote_identifier(column) for column in columns)}) VALUES ({placeholders})",
                    values,
                )
    return path


def make_args(
    tmp_path: Path,
    *,
    db_path: Path | None = None,
    threshold_payload: dict[str, object] | None = None,
    canonical_payload: dict[str, object] | None = None,
    output_dir: Path | None = None,
    overwrite: bool = True,
    oos_start_time: str | None = None,
    oos_end_time: str | None = None,
) -> object:
    threshold_path = write_json(tmp_path / "thresholds.json", threshold_payload or train_only_thresholds())
    canonical_path = write_json(tmp_path / "canonical.json", canonical_payload or canonical_registry())
    if db_path is None:
        db_path = write_feature_db(tmp_path / "db" / "trading_bot.db")
    args = [
        "--run-id",
        "unit_oos_replay",
        "--db-path",
        str(db_path),
        "--feature-table",
        "price_features",
        "--train-only-thresholds",
        str(threshold_path),
        "--canonical-registry",
        str(canonical_path),
        "--symbol",
        "GBPUSD",
        "--timeframe",
        "M15",
        "--session-column",
        "hour_session",
        "--required-session",
        "Off_hours",
        "--max-spread-points",
        "15.0",
        "--output-dir",
        str(output_dir or tmp_path / "out"),
    ]
    if oos_start_time is not None:
        args.extend(["--oos-start-time", oos_start_time])
    if oos_end_time is not None:
        args.extend(["--oos-end-time", oos_end_time])
    if overwrite:
        args.append("--overwrite")
    return replay.build_parser().parse_args(args)


def build_and_read(tmp_path: Path, **kwargs: object) -> tuple[dict[str, Path], dict[str, object]]:
    outputs = replay.build_outputs(make_args(tmp_path, **kwargs))
    return outputs, read_json(outputs["manifest"])


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        replay.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_missing_threshold_artifact_blocks(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    Path(args.train_only_thresholds).unlink()
    outputs = replay.build_outputs(args)
    manifest = read_json(outputs["manifest"])

    assert manifest["replay_status"] == replay.STATUS_MISSING_THRESHOLD


def test_non_train_only_threshold_artifact_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(
        tmp_path,
        threshold_payload=train_only_thresholds(threshold_lineage="full_sample"),
    )

    assert manifest["replay_status"] == replay.STATUS_NON_TRAIN_ONLY


def test_missing_db_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(tmp_path, db_path=tmp_path / "db" / "missing.db")

    assert manifest["replay_status"] == replay.STATUS_MISSING_DB


def test_missing_table_blocks(tmp_path: Path) -> None:
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", include_table=False)
    _outputs, manifest = build_and_read(tmp_path, db_path=db_path)

    assert manifest["replay_status"] == replay.STATUS_MISSING_TABLE


def test_missing_columns_block(tmp_path: Path) -> None:
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", missing_columns={"spread"})
    _outputs, manifest = build_and_read(tmp_path, db_path=db_path)

    assert manifest["replay_status"] == replay.STATUS_MISSING_COLUMNS
    assert "spread" in manifest["missing_required_columns"]


def test_empty_oos_window_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(tmp_path, oos_start_time="2030-01-01 00:00:00")

    assert manifest["replay_status"] == replay.STATUS_EMPTY_OOS


def test_noncanonical_candidate_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(tmp_path, canonical_payload=canonical_registry(candidate_id="other"))

    assert manifest["replay_status"] == replay.STATUS_NONCANONICAL


def test_bucketing_uses_train_only_cutoffs_not_db_bucket_labels(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path)
    matches = read_csv(outputs["matches"])

    assert manifest["rule_match_count"] == 3
    assert matches[0][f"{replay.FEATURE_A}_bucket"] == "high_tercile"
    assert matches[0][f"{replay.FEATURE_B}_bucket"] == "mid_tercile"


def test_rows_before_or_equal_to_train_end_time_are_excluded(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path)
    matches = read_csv(outputs["matches"])

    assert manifest["source_row_count"] == 8
    assert manifest["oos_row_count"] == 7
    assert all(row["time_server"] != "2024-12-31 23:59:59" for row in matches)


def test_default_oos_start_is_first_row_after_train_end_time(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(tmp_path)

    assert manifest["oos_start_time"] == "2025-01-01 00:00:00"


def test_session_filter_is_applied(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(tmp_path)

    assert manifest["oos_row_count"] == 7
    assert manifest["off_hours_oos_row_count"] == 6


def test_spread_gate_is_applied(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path)
    condition_rows = {row["condition_name"]: row for row in read_csv(outputs["condition_counts"])}

    assert manifest["spread_pass_count"] == 5
    assert condition_rows["spread_gate"]["pass_count"] == "5"


def test_rule_match_count_is_correct(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(tmp_path)

    assert manifest["rule_match_count"] == 3


def test_bucket_counts_are_written(tmp_path: Path) -> None:
    outputs, _manifest = build_and_read(tmp_path)
    rows = read_csv(outputs["bucket_counts"])
    counts = {(row["feature_name"], row["bucket"]): row["count"] for row in rows}

    assert counts[(replay.FEATURE_A, "high_tercile")] == "5"
    assert counts[(replay.FEATURE_B, "mid_tercile")] == "5"


def test_signal_only_status_when_outcomes_missing(tmp_path: Path) -> None:
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", include_outcomes=False)
    _outputs, manifest = build_and_read(tmp_path, db_path=db_path)

    assert manifest["replay_status"] == replay.STATUS_AVAILABLE_SIGNAL_ONLY
    assert manifest["outcome_columns_available"] is False


def test_outcome_metrics_status_when_outcomes_present(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(tmp_path)

    assert manifest["replay_status"] == replay.STATUS_AVAILABLE_WITH_OUTCOMES
    assert manifest["outcome_columns_available"] is True
    assert manifest["trade_count"] == 3
    assert manifest["mean_R"] == pytest.approx(1.0 / 3.0)
    assert manifest["median_R"] == pytest.approx(0.5)
    assert manifest["sum_R"] == pytest.approx(1.0)
    assert manifest["profit_factor_R"] == pytest.approx(2.0)
    assert manifest["win_rate_R_positive"] == pytest.approx(2.0 / 3.0)
    assert manifest["max_drawdown_R"] == pytest.approx(1.0)
    assert manifest["tp_hit_count"] == 1
    assert manifest["sl_hit_count"] == 1
    assert manifest["timeout_count"] == 1


def test_no_order_evidence_is_written(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path)
    evidence = {row["evidence_name"]: row["value"] for row in read_csv(outputs["no_order_evidence"])}

    assert manifest["no_order_send_called"] is True
    assert evidence["no_mt5_import_performed"] == "true"
    assert evidence["no_db_mutation_performed"] == "true"


def test_output_exists_without_overwrite_blocks(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    args = make_args(tmp_path, output_dir=output_dir)
    replay.build_outputs(args)
    args.overwrite = False

    with pytest.raises(replay.BlockedStatusError) as exc:
        replay.build_outputs(args)

    assert exc.value.status == replay.STATUS_OUTPUT_EXISTS


def test_static_safety_grep_confirms_no_mt5_order_broker_history_scheduler_calls() -> None:
    source = Path(replay.__file__).read_text(encoding="utf-8")

    assert "MetaTrader5" not in source
    assert "mt5." not in source
    assert not re.search(
        r"\.(order_check|order_send|order_calc_margin|order_calc_profit|positions_get|orders_get|"
        r"history_orders_get|history_deals_get)\s*\(",
        source,
    )
    assert "subprocess" not in source
    assert not re.search(r"\b(threading|apscheduler|schedule)\b", source)


def test_static_safety_grep_confirms_no_db_mutation_statements() -> None:
    source = Path(replay.__file__).read_text(encoding="utf-8")

    assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|REPLACE|CREATE)\b", source)
