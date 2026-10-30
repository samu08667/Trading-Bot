from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

import pytest

from scripts import run_fixed_candidate_train_only_threshold_oos_outcome_replay as outcome


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


def row(
    time_server: str,
    *,
    session: str = "London",
    spread: float = 10.0,
    open_price: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
    atr: float = 2.0,
    feature_a: float = 0.5,
    feature_b: float = 15.0,
    symbol: str = "GBPUSD",
    timeframe: str = "M15",
    bucket_a: str = "low_tercile",
    bucket_b: str = "low_tercile",
) -> dict[str, object]:
    return {
        "time_server": time_server,
        "symbol": symbol,
        "timeframe": timeframe,
        "hour_session": session,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "spread": spread,
        "atr_20": atr,
        "close_to_ma_fast_atr_20": feature_a,
        "tick_volume_percentile_100": feature_b,
        "close_to_ma_fast_atr_20_bucket": bucket_a,
        "tick_volume_percentile_100_bucket": bucket_b,
    }


def matching_entry(
    time_server: str = "2025-01-01 00:00:00",
    *,
    spread: float = 10.0,
    feature_a: float = 2.5,
    feature_b: float = 15.0,
) -> dict[str, object]:
    return row(
        time_server,
        session="Off_hours",
        spread=spread,
        open_price=100.0,
        high=100.5,
        low=99.5,
        close=100.0,
        atr=2.0,
        feature_a=feature_a,
        feature_b=feature_b,
        bucket_a="low_tercile",
        bucket_b="low_tercile",
    )


def tp_rows() -> list[dict[str, object]]:
    return [
        row("2024-12-31 23:59:59", session="Off_hours", feature_a=2.5, feature_b=15.0),
        matching_entry(),
        row("2025-01-01 00:01:00", high=101.0, low=96.0, close=98.0),
    ]


def sl_rows() -> list[dict[str, object]]:
    return [
        matching_entry(),
        row("2025-01-01 00:01:00", high=103.0, low=99.0, close=102.0),
    ]


def same_bar_rows() -> list[dict[str, object]]:
    return [
        matching_entry(),
        row("2025-01-01 00:01:00", high=103.0, low=96.0, close=100.0),
    ]


def timeout_rows() -> list[dict[str, object]]:
    rows = [matching_entry()]
    for minute in range(1, 11):
        rows.append(
            row(
                f"2025-01-01 00:{minute:02d}:00",
                high=101.0,
                low=98.0,
                close=99.0 if minute == 10 else 100.0,
            )
        )
    return rows


def write_feature_db(
    path: Path,
    *,
    rows: list[dict[str, object]] | None = None,
    include_table: bool = True,
    missing_columns: set[str] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "time_server",
        "symbol",
        "timeframe",
        "hour_session",
        "open",
        "high",
        "low",
        "close",
        "spread",
        "atr_20",
        "close_to_ma_fast_atr_20",
        "tick_volume_percentile_100",
        "close_to_ma_fast_atr_20_bucket",
        "tick_volume_percentile_100_bucket",
    ]
    for column in missing_columns or set():
        columns.remove(column)
    numeric_columns = {
        "open",
        "high",
        "low",
        "close",
        "spread",
        "atr_20",
        "close_to_ma_fast_atr_20",
        "tick_volume_percentile_100",
    }
    with sqlite3.connect(path) as connection:
        if include_table:
            defs = [
                f"{outcome.quote_identifier(column)} {'REAL' if column in numeric_columns else 'TEXT'}"
                for column in columns
            ]
            connection.execute(f"CREATE TABLE {outcome.quote_identifier('price_features')} ({', '.join(defs)})")
            for source_row in rows or tp_rows():
                values = [source_row.get(column) for column in columns]
                placeholders = ",".join("?" for _ in columns)
                connection.execute(
                    f"INSERT INTO {outcome.quote_identifier('price_features')} "
                    f"({', '.join(outcome.quote_identifier(column) for column in columns)}) VALUES ({placeholders})",
                    values,
                )
    return path


def make_args(
    tmp_path: Path,
    *,
    rows: list[dict[str, object]] | None = None,
    db_path: Path | None = None,
    threshold_payload: dict[str, object] | None = None,
    canonical_payload: dict[str, object] | None = None,
    output_dir: Path | None = None,
    overwrite: bool = True,
    oos_start_time: str | None = None,
    oos_end_time: str | None = None,
    max_spread_points: float = 15.0,
) -> object:
    threshold_path = write_json(tmp_path / "thresholds.json", threshold_payload or train_only_thresholds())
    canonical_path = write_json(tmp_path / "canonical.json", canonical_payload or canonical_registry())
    if db_path is None:
        db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", rows=rows)
    args = [
        "--run-id",
        "unit_oos_outcome",
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
        str(max_spread_points),
        "--output-dir",
        str(output_dir or tmp_path / "out"),
    ]
    if oos_start_time is not None:
        args.extend(["--oos-start-time", oos_start_time])
    if oos_end_time is not None:
        args.extend(["--oos-end-time", oos_end_time])
    if overwrite:
        args.append("--overwrite")
    return outcome.build_parser().parse_args(args)


def build_and_read(tmp_path: Path, **kwargs: object) -> tuple[dict[str, Path], dict[str, object]]:
    outputs = outcome.build_outputs(make_args(tmp_path, **kwargs))
    return outputs, read_json(outputs["manifest"])


def trades_by_index(outputs: dict[str, Path]) -> list[dict[str, str]]:
    return read_csv(outputs["trades"])


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        outcome.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_missing_threshold_artifact_blocks(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    Path(args.train_only_thresholds).unlink()
    outputs = outcome.build_outputs(args)
    manifest = read_json(outputs["manifest"])

    assert manifest["replay_status"] == outcome.STATUS_MISSING_THRESHOLD


def test_non_train_only_threshold_artifact_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(
        tmp_path,
        threshold_payload=train_only_thresholds(threshold_lineage="full_sample"),
    )

    assert manifest["replay_status"] == outcome.STATUS_NON_TRAIN_ONLY


def test_missing_db_blocks(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(tmp_path, db_path=tmp_path / "db" / "missing.db")

    assert manifest["replay_status"] == outcome.STATUS_MISSING_DB


def test_missing_table_blocks(tmp_path: Path) -> None:
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", include_table=False)
    _outputs, manifest = build_and_read(tmp_path, db_path=db_path)

    assert manifest["replay_status"] == outcome.STATUS_MISSING_TABLE


def test_missing_columns_block(tmp_path: Path) -> None:
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", missing_columns={"atr_20"})
    _outputs, manifest = build_and_read(tmp_path, db_path=db_path)

    assert manifest["replay_status"] == outcome.STATUS_MISSING_COLUMNS
    assert "atr_20" in manifest["missing_required_columns"]


def test_short_tp_hit_outcome(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path, rows=tp_rows())
    trades = trades_by_index(outputs)

    assert manifest["replay_status"] == outcome.STATUS_AVAILABLE
    assert manifest["trade_count"] == 1
    assert trades[0]["exit_reason"] == "paper_tp_hit"
    assert float(trades[0]["R_multiple"]) == pytest.approx(1.5)


def test_short_sl_hit_outcome(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path, rows=sl_rows())
    trades = trades_by_index(outputs)

    assert manifest["sl_hit_count"] == 1
    assert trades[0]["exit_reason"] == "paper_sl_hit"
    assert float(trades[0]["R_multiple"]) == pytest.approx(-1.0)


def test_timeout_outcome(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path, rows=timeout_rows())
    trades = trades_by_index(outputs)

    assert manifest["timeout_count"] == 1
    assert trades[0]["exit_reason"] == "paper_timeout"
    assert float(trades[0]["R_multiple"]) == pytest.approx(0.5)
    assert trades[0]["bars_elapsed"] == "10"


def test_same_bar_stop_first_policy(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path, rows=same_bar_rows())
    trades = trades_by_index(outputs)
    warning_codes = {row["warning_code"] for row in read_csv(outputs["warnings"])}

    assert manifest["sl_hit_count"] == 1
    assert trades[0]["exit_reason"] == "paper_sl_hit"
    assert float(trades[0]["R_multiple"]) == pytest.approx(-1.0)
    assert "same_bar_stop_first_applied" in warning_codes


def test_rows_before_or_equal_to_train_end_time_are_excluded(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path, rows=tp_rows())
    trades = trades_by_index(outputs)

    assert manifest["oos_row_count"] == 2
    assert all(row["entry_time_server"] != "2024-12-31 23:59:59" for row in trades)


def test_buckets_are_computed_from_train_only_cutoffs(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path, rows=tp_rows())
    trades = trades_by_index(outputs)

    assert manifest["rule_match_count"] == 1
    assert trades[0][f"{outcome.FEATURE_A}_bucket"] == "high_tercile"
    assert trades[0][f"{outcome.FEATURE_B}_bucket"] == "mid_tercile"


def test_spread_gate_blocks_entry(tmp_path: Path) -> None:
    _outputs, manifest = build_and_read(tmp_path, rows=[matching_entry(spread=20.0), row("2025-01-01 00:01:00")])

    assert manifest["rule_match_count"] == 0
    assert manifest["trade_count"] == 0


def test_metrics_calculation(tmp_path: Path) -> None:
    rows = [
        matching_entry("2025-01-01 00:00:00"),
        row("2025-01-01 00:01:00", high=101.0, low=96.0, close=98.0),
        matching_entry("2025-01-01 00:02:00"),
        row("2025-01-01 00:03:00", high=103.0, low=99.0, close=102.0),
        matching_entry("2025-01-01 00:04:00"),
    ]
    for minute in range(5, 15):
        rows.append(
            row(
                f"2025-01-01 00:{minute:02d}:00",
                high=101.0,
                low=98.0,
                close=99.0 if minute == 14 else 100.0,
            )
        )

    _outputs, manifest = build_and_read(tmp_path, rows=rows)

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
    outputs, manifest = build_and_read(tmp_path, rows=tp_rows())
    evidence = {row["evidence_name"]: row["value"] for row in read_csv(outputs["no_order_evidence"])}

    assert manifest["no_order_send_called"] is True
    assert evidence["no_mt5_import_performed"] == "true"
    assert evidence["no_db_mutation_performed"] == "true"


def test_static_safety_grep_confirms_no_mt5_order_broker_history_scheduler_calls() -> None:
    source = Path(outcome.__file__).read_text(encoding="utf-8")

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
    source = Path(outcome.__file__).read_text(encoding="utf-8")

    assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|REPLACE|CREATE)\b", source)
