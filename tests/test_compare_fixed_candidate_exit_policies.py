from __future__ import annotations

from collections import Counter
import csv
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts import compare_fixed_candidate_exit_policies as compare


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
        "max_open_positions": 1,
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
    open_price: float = 1.3000,
    high: float = 1.3005,
    low: float = 1.2990,
    close: float = 1.3000,
    atr: float = 0.0010,
    feature_a: float = 0.5,
    feature_b: float = 15.0,
    symbol: str = "GBPUSD",
    timeframe: str = "M15",
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
    }


def matching_entry(time_server: str = "2025-01-01 22:00:00") -> dict[str, object]:
    return row(
        time_server,
        session="Off_hours",
        high=1.3004,
        low=1.2994,
        close=1.3000,
        feature_a=2.5,
        feature_b=15.0,
    )


def bar_time(start: str, offset: int) -> str:
    parsed = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    return (parsed + timedelta(minutes=15 * offset)).strftime("%Y-%m-%d %H:%M:%S")


def quiet_bar(time_server: str, *, close: float = 1.3000) -> dict[str, object]:
    return row(time_server, high=1.3005, low=1.2990, close=close)


def time_exit_then_tp_rows() -> list[dict[str, object]]:
    start = "2025-01-01 22:00:00"
    rows = [matching_entry(start)]
    for offset in range(1, 11):
        rows.append(quiet_bar(bar_time(start, offset), close=1.2995 if offset == 10 else 1.3000))
    rows.append(row(bar_time(start, 11), high=1.3002, low=1.2980, close=1.2983))
    return rows


def friday_rows() -> list[dict[str, object]]:
    start = "2025-01-03 22:00:00"
    rows = [matching_entry(start)]
    for offset in range(1, 8):
        rows.append(quiet_bar(bar_time(start, offset), close=1.2996))
    rows.append(row("2025-01-06 00:00:00", high=1.3000, low=1.2980, close=1.2982))
    return rows


def same_bar_conflict_rows() -> list[dict[str, object]]:
    start = "2025-01-01 22:00:00"
    return [
        matching_entry(start),
        row(bar_time(start, 1), high=1.3015, low=1.2980, close=1.3000),
    ]


def write_feature_db(path: Path, rows: list[dict[str, object]]) -> Path:
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
    ]
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
        defs = [
            f"{compare.base.quote_identifier(column)} {'REAL' if column in numeric_columns else 'TEXT'}"
            for column in columns
        ]
        connection.execute(f"CREATE TABLE {compare.base.quote_identifier('price_features')} ({', '.join(defs)})")
        for source_row in rows:
            values = [source_row.get(column) for column in columns]
            placeholders = ",".join("?" for _ in columns)
            connection.execute(
                f"INSERT INTO {compare.base.quote_identifier('price_features')} "
                f"({', '.join(compare.base.quote_identifier(column) for column in columns)}) VALUES ({placeholders})",
                values,
            )
    return path


def make_args(tmp_path: Path, rows: list[dict[str, object]]) -> object:
    threshold_path = write_json(tmp_path / "thresholds.json", train_only_thresholds())
    canonical_path = write_json(tmp_path / "canonical.json", canonical_registry())
    strategy_spec_path = write_json(tmp_path / "strategy_spec.json", {"candidate_id": "gbpusd_short_h10_1_5_off_hours"})
    db_path = write_feature_db(tmp_path / "db" / "trading_bot.db", rows)
    args = [
        "--run-id",
        "unit_exit_policy",
        "--db-path",
        str(db_path),
        "--feature-table",
        "price_features",
        "--train-only-thresholds",
        str(threshold_path),
        "--canonical-registry",
        str(canonical_path),
        "--strategy-spec",
        str(strategy_spec_path),
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
        str(tmp_path / "out"),
        "--overwrite",
    ]
    return compare.build_parser().parse_args(args)


def build_and_read(tmp_path: Path, rows: list[dict[str, object]]) -> tuple[dict[str, Path], dict[str, object]]:
    outputs = compare.build_outputs(make_args(tmp_path, rows))
    return outputs, read_json(outputs["manifest"])


def summary_by_policy(outputs: dict[str, Path]) -> dict[str, dict[str, str]]:
    return {row["policy_id"]: row for row in read_csv(outputs["summary"])}


def trades_for_policy(outputs: dict[str, Path], policy_id: str) -> list[dict[str, str]]:
    return [row for row in read_csv(outputs["trades"]) if row["policy_id"] == policy_id]


def test_current_10_bars_produces_time_exits(tmp_path: Path) -> None:
    outputs, manifest = build_and_read(tmp_path, time_exit_then_tp_rows())
    summary = summary_by_policy(outputs)
    trades = trades_for_policy(outputs, "current_10_bars")

    assert manifest["comparison_status"] == compare.STATUS_AVAILABLE
    assert int(summary["current_10_bars"]["time_exit_count"]) == 1
    assert trades[0]["exit_reason"] == "time_exit"
    assert int(trades[0]['holding_bars']) == 10
    assert trades[0]['exit_time_server'] == '2025-01-02 00:30:00'


def test_tp_sl_only_research_produces_no_time_exits(tmp_path: Path) -> None:
    outputs, _manifest = build_and_read(tmp_path, time_exit_then_tp_rows())
    summary = summary_by_policy(outputs)
    trades = trades_for_policy(outputs, "tp_sl_only_research")

    assert int(summary["tp_sl_only_research"]["time_exit_count"]) == 0
    assert int(summary["tp_sl_only_research"]["tp_count"]) == 1
    assert trades[0]["exit_reason"] == "tp"


def test_friday_forced_flat_only_where_policy_enables_it(tmp_path: Path) -> None:
    outputs, _manifest = build_and_read(tmp_path, friday_rows())
    summary = summary_by_policy(outputs)

    assert int(summary["current_10_bars"]["friday_forced_flat_count"]) == 1
    assert int(summary["tp_sl_friday_only"]["friday_forced_flat_count"]) == 1
    assert int(summary["tp_sl_only_research"]["friday_forced_flat_count"]) == 0
    assert trades_for_policy(outputs, "tp_sl_friday_only")[0]["exit_time_server"] == "2025-01-03 23:45:00"


def test_sl_tp_priority_uses_stop_first_on_same_bar_for_short(tmp_path: Path) -> None:
    outputs, _manifest = build_and_read(tmp_path, same_bar_conflict_rows())
    summary = summary_by_policy(outputs)
    trades = trades_for_policy(outputs, "current_10_bars")

    assert int(summary["current_10_bars"]["sl_count"]) == 1
    assert trades[0]["exit_reason"] == "sl"
    assert float(trades[0]["R_multiple"]) == pytest.approx(-1.0)


def test_time_exit_does_not_look_ahead_to_future_tp(tmp_path: Path) -> None:
    outputs, _manifest = build_and_read(tmp_path, time_exit_then_tp_rows())
    summary = summary_by_policy(outputs)
    current_trade = trades_for_policy(outputs, "current_10_bars")[0]

    assert int(summary["current_10_bars"]["tp_count"]) == 0
    assert int(summary["current_10_bars"]["time_exit_count"]) == 1
    assert float(current_trade["R_multiple"]) == pytest.approx(0.5)
    assert current_trade["would_have_hit_tp_after_time_exit"] == "true"


def test_trade_count_is_coherent_with_same_raw_signals_across_policies(tmp_path: Path) -> None:
    outputs, _manifest = build_and_read(tmp_path, time_exit_then_tp_rows())
    summary_rows = read_csv(outputs["summary"])
    trades = read_csv(outputs["trades"])
    trade_counts = Counter(row["policy_id"] for row in trades)

    assert {int(row["raw_signal_count"]) for row in summary_rows} == {1}
    for row in summary_rows:
        assert int(row["trade_count"]) == trade_counts[row["policy_id"]]


def test_static_safety_has_no_broker_execution_or_db_mutation_signatures() -> None:
    source = Path(compare.__file__).read_text(encoding="utf-8")

    assert "MetaTrader5" not in source
    assert "mt5." not in source
    assert not re.search(
        r"\.(order_check|order_send|order_calc_margin|order_calc_profit|positions_get|orders_get|"
        r"history_orders_get|history_deals_get)\s*\(",
        source,
    )
    assert "subprocess" not in source
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|REPLACE|CREATE)\b", source)
