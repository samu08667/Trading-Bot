import argparse
import csv
import re
from dataclasses import fields
from datetime import datetime, timedelta
from pathlib import Path

from scripts.diagnose_regime_filter_candidates import (
    OutcomeBucket,
    CLASS_INSUFFICIENT,
    CLASS_NO_EVIDENCE,
    CLASS_REVIEW,
    MISSING_VALUE,
    run_regime_filter_diagnostics,
)


SUMMARY_FIELDS = [
    "scope",
    "symbol",
    "direction",
    "timeframe",
    "horizon",
    "tp_atr",
    "sl_atr",
    "atr_column",
    "same_bar_policy",
    "filters",
    "trades_count",
    "tp_hit_count",
    "sl_hit_count",
    "timeout_count",
    "tp_hit_rate",
    "sl_hit_rate",
    "timeout_rate",
    "mean_R",
    "profit_factor_R",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "baseline_trades_count",
    "baseline_mean_R",
    "baseline_profit_factor_R",
    "mean_R_vs_baseline",
    "profit_factor_R_vs_baseline",
    "cost_mode",
    "return_mode",
    "hour_session",
]


ML_SOURCE_FIELDS = [
    field for field in SUMMARY_FIELDS if field != "hour_session"
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def base_summary_row(**overrides: object) -> dict[str, object]:
    row = {
        "scope": "candidate_path_row",
        "symbol": "EURUSD",
        "direction": "long",
        "timeframe": "M15",
        "horizon": "10",
        "tp_atr": "1.5",
        "sl_atr": "1.0",
        "atr_column": "atr_20",
        "same_bar_policy": "stop_first",
        "filters": "binary_feature:feature_flag:1",
        "trades_count": "10",
        "tp_hit_count": "6",
        "sl_hit_count": "3",
        "timeout_count": "1",
        "tp_hit_rate": "0.6",
        "sl_hit_rate": "0.3",
        "timeout_rate": "0.1",
        "mean_R": "0.2",
        "profit_factor_R": "1.4",
        "monthly_positive_ratio": "0.6",
        "quarterly_positive_ratio": "0.6",
        "baseline_trades_count": "100",
        "baseline_mean_R": "0.0",
        "baseline_profit_factor_R": "1.0",
        "mean_R_vs_baseline": "0.2",
        "profit_factor_R_vs_baseline": "0.4",
        "cost_mode": "none",
        "return_mode": "gross",
        "hour_session": "Europe",
    }
    row.update(overrides)
    return row


def args_for(tmp_path: Path, input_csv: Path, *, min_trades: int = 5) -> argparse.Namespace:
    return argparse.Namespace(
        input_root=[],
        input_csv=[input_csv],
        path_fragment=[],
        source_mode="loaded_outputs",
        regime_column=[],
        min_trades=min_trades,
        max_regime_values=25,
        max_source_rows=None,
        disable_baseline_details=False,
        cost_config=None,
        db_path=tmp_path / "unused.db",
        run_id="unit_run",
        output_root=tmp_path / "reports",
        overwrite=False,
    )


def ml_args_for(tmp_path: Path, input_csv: Path, *, min_trades: int = 5) -> argparse.Namespace:
    args = args_for(tmp_path, input_csv, min_trades=min_trades)
    args.source_mode = "ml_dataset"
    return args


def synthetic_ml_rows(trade_count: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = datetime(2024, 1, 1)
    for index in range(trade_count + 1):
        timestamp = start + timedelta(minutes=15 * index)
        rows.append(
            {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "time_server": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.0,
                "atr_20": 1.0,
                "feature_flag": 1,
                "hour_session": "Asia" if index % 2 == 0 else "Europe",
                "spread": 0,
            }
        )
    for entry_index in range(trade_count):
        future_row = rows[entry_index + 1]
        is_tp = entry_index % 4 in {0, 1}
        future_row["high"] = 101.1 if is_tp else 100.5
        future_row["low"] = 99.5 if is_tp else 98.9
    return rows


def no_call_row_loader(_db_path: Path, symbol: str, timeframe: str) -> list[dict[str, object]]:
    raise AssertionError(f"row loader should not be called for {symbol} {timeframe}")


def test_handles_missing_regime_columns(tmp_path: Path) -> None:
    input_csv = tmp_path / "20260519_193950_M15_h10_preferred_1_5atr_1atr_p75_fx_tp_sl" / "long" / "tp_sl_path_backtest_summary.csv"
    fields = [field for field in SUMMARY_FIELDS if field != "hour_session"]
    write_csv(input_csv, fields, [base_summary_row()])

    outputs = run_regime_filter_diagnostics(args_for(tmp_path, input_csv))
    rows = read_csv(outputs["regime_filter_diagnostics_csv"])
    missing_hour_rows = [
        row for row in rows if row["regime_column"] == "hour_session" and row["regime_value"] == MISSING_VALUE
    ]

    assert missing_hour_rows
    assert {row["classification_suggestion"] for row in missing_hour_rows} == {CLASS_NO_EVIDENCE}
    report_text = outputs["regime_filter_diagnostics_report"].read_text(encoding="utf-8")
    assert "Missing Regime Columns" in report_text


def test_handles_empty_input_rows(tmp_path: Path) -> None:
    input_csv = tmp_path / "tp_sl_path_backtest_summary.csv"
    write_csv(input_csv, SUMMARY_FIELDS, [])

    outputs = run_regime_filter_diagnostics(args_for(tmp_path, input_csv))
    rows = read_csv(outputs["regime_filter_diagnostics_csv"])

    assert len(rows) == 1
    assert rows[0]["classification_suggestion"] == CLASS_NO_EVIDENCE
    assert rows[0]["notes"] == "no input rows loaded from existing branch outputs"


def test_computes_regime_grouped_metrics(tmp_path: Path) -> None:
    input_csv = tmp_path / "20260519_193950_M15_h10_preferred_1_5atr_1atr_p75_fx_tp_sl" / "long" / "tp_sl_path_backtest_summary.csv"
    write_csv(
        input_csv,
        SUMMARY_FIELDS,
        [
            base_summary_row(hour_session="Asia", trades_count="10", tp_hit_count="6", sl_hit_count="3", timeout_count="1", mean_R="0.2", profit_factor_R="1.4"),
            base_summary_row(hour_session="Asia", trades_count="5", tp_hit_count="2", sl_hit_count="2", timeout_count="1", mean_R="0.1", profit_factor_R="1.2"),
        ],
    )

    outputs = run_regime_filter_diagnostics(args_for(tmp_path, input_csv, min_trades=10))
    rows = read_csv(outputs["regime_filter_diagnostics_csv"])
    asia = next(row for row in rows if row["regime_column"] == "hour_session" and row["regime_value"] == "Asia")

    assert asia["target_family"] == "preferred_1_5atr_1atr_hit_first"
    assert asia["horizon"] == "10"
    assert asia["group"] == "FX"
    assert asia["tested_rows"] == "2"
    assert asia["trades_count"] == "15"
    assert abs(float(asia["mean_R"]) - ((10 * 0.2 + 5 * 0.1) / 15)) < 1e-9
    assert abs(float(asia["tp_hit_rate"]) - (8 / 15)) < 1e-9
    assert asia["classification_suggestion"] == CLASS_REVIEW


def test_ml_dataset_uses_aggregate_buckets_without_outcome_lists(tmp_path: Path) -> None:
    field_names = {field.name for field in fields(OutcomeBucket)}
    assert "outcomes" not in field_names
    assert "baseline_outcomes" not in field_names
    assert {"stats", "baseline_stats"}.issubset(field_names)

    input_csv = tmp_path / "20260519_193950_M15_h10_preferred_1_5atr_1atr_p75_fx_tp_sl" / "long" / "tp_sl_path_backtest_summary.csv"
    source = base_summary_row(horizon="1", tp_atr="1.0", sl_atr="1.0", filters="binary_feature:feature_flag:1")
    write_csv(input_csv, ML_SOURCE_FIELDS, [source])

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return synthetic_ml_rows(20)

    outputs = run_regime_filter_diagnostics(
        ml_args_for(tmp_path, input_csv, min_trades=1),
        row_loader=row_loader,
    )
    rows = read_csv(outputs["regime_filter_diagnostics_csv"])
    asia = next(row for row in rows if row["regime_column"] == "hour_session" and row["regime_value"] == "Asia")

    assert asia["trades_count"] == "10"
    assert abs(float(asia["tp_hit_rate"]) - 0.5) < 1e-9
    assert abs(float(asia["mean_R"]) - 0.0) < 1e-9
    assert abs(float(asia["baseline_mean_R"]) - 0.0) < 1e-9
    assert abs(float(asia["mean_R_vs_baseline"]) - 0.0) < 1e-9


def test_ml_dataset_derives_missing_research_regime_columns_from_sources(tmp_path: Path) -> None:
    input_csv = tmp_path / "20260519_193950_M15_h10_preferred_1_5atr_1atr_p75_fx_tp_sl" / "long" / "tp_sl_path_backtest_summary.csv"
    source = base_summary_row(horizon="1", tp_atr="1.0", sl_atr="1.0", filters="binary_feature:feature_flag:1")
    write_csv(input_csv, ML_SOURCE_FIELDS, [source])

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        rows = synthetic_ml_rows(20)
        for row in rows:
            row.pop("session", None)
            row.pop("spread_liquidity_regime", None)
            row.pop("volatility_regime", None)
            row.pop("range_regime", None)
            row.pop("volume_liquidity_regime", None)
            row.update(
                {
                    "spread_to_atr_20": 0.20,
                    "volatility_ratio_20_100": 1.50,
                    "range_to_atr_20": 1.00,
                    "volume_spike_20": 0,
                    "volume_dry_up_20": 1,
                }
            )
        return rows

    outputs = run_regime_filter_diagnostics(
        ml_args_for(tmp_path, input_csv, min_trades=1),
        row_loader=row_loader,
    )
    rows = read_csv(outputs["regime_filter_diagnostics_csv"])
    derived = {
        (row["regime_column"], row["regime_value"])
        for row in rows
        if row["classification_suggestion"] != CLASS_NO_EVIDENCE
    }

    assert ("session", "Asia") in derived
    assert ("spread_liquidity_regime", "high_spread") in derived
    assert ("volatility_regime", "high_volatility") in derived
    assert ("range_regime", "normal_range") in derived
    assert ("volume_liquidity_regime", "dry_volume") in derived


def test_ml_dataset_handles_many_synthetic_rows_without_memory_error(tmp_path: Path) -> None:
    input_csv = tmp_path / "20260519_193950_M15_h10_preferred_1_5atr_1atr_p75_fx_tp_sl" / "long" / "tp_sl_path_backtest_summary.csv"
    source = base_summary_row(horizon="1", tp_atr="1.0", sl_atr="1.0", filters="binary_feature:feature_flag:1")
    write_csv(input_csv, ML_SOURCE_FIELDS, [source])

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return synthetic_ml_rows(5000)

    outputs = run_regime_filter_diagnostics(
        ml_args_for(tmp_path, input_csv, min_trades=1),
        row_loader=row_loader,
    )
    rows = read_csv(outputs["regime_filter_diagnostics_csv"])
    grouped = [row for row in rows if row["regime_column"] == "hour_session" and row["regime_value"] in {"Asia", "Europe"}]

    assert {row["regime_value"] for row in grouped} == {"Asia", "Europe"}
    assert sum(int(row["trades_count"]) for row in grouped) == 5000


def test_max_source_rows_limits_debug_replay(tmp_path: Path) -> None:
    input_csv = tmp_path / "20260519_193950_M15_h10_preferred_1_5atr_1atr_p75_fx_tp_sl" / "long" / "tp_sl_path_backtest_summary.csv"
    write_csv(
        input_csv,
        ML_SOURCE_FIELDS,
        [
            base_summary_row(horizon="1", tp_atr="1.0", sl_atr="1.0"),
            base_summary_row(horizon="1", tp_atr="1.0", sl_atr="1.0", symbol="GBPUSD"),
        ],
    )
    args = args_for(tmp_path, input_csv, min_trades=1)
    args.max_source_rows = 1

    outputs = run_regime_filter_diagnostics(args, row_loader=no_call_row_loader)
    rows = read_csv(outputs["regime_filter_diagnostics_csv"])
    report_text = outputs["regime_filter_diagnostics_report"].read_text(encoding="utf-8")

    assert all(row["symbol"] != "GBPUSD" for row in rows)
    assert "Loaded source rows: `1`" in report_text


def test_enforces_minimum_trades_threshold(tmp_path: Path) -> None:
    input_csv = tmp_path / "20260519_193950_M15_h10_preferred_1_5atr_1atr_p75_fx_tp_sl" / "long" / "tp_sl_path_backtest_summary.csv"
    write_csv(input_csv, SUMMARY_FIELDS, [base_summary_row(trades_count="4", hour_session="Europe")])

    outputs = run_regime_filter_diagnostics(args_for(tmp_path, input_csv, min_trades=10))
    rows = read_csv(outputs["regime_filter_diagnostics_csv"])
    europe = next(row for row in rows if row["regime_column"] == "hour_session" and row["regime_value"] == "Europe")

    assert europe["classification_suggestion"] == CLASS_INSUFFICIENT


def test_report_avoids_blocked_language(tmp_path: Path) -> None:
    input_csv = tmp_path / "tp_sl_path_backtest_summary.csv"
    write_csv(input_csv, SUMMARY_FIELDS, [base_summary_row()])

    outputs = run_regime_filter_diagnostics(args_for(tmp_path, input_csv))
    combined_text = "\n".join(path.read_text(encoding="utf-8").lower() for path in outputs.values())
    report_text = outputs["regime_filter_diagnostics_report"].read_text(encoding="utf-8").lower()

    assert "buy" not in combined_text
    assert "sell" not in combined_text
    assert "live signal" not in combined_text
    assert "trade signal" not in combined_text
    assert "strategy" not in report_text


def test_script_does_not_import_metatrader5_or_live_api_terms() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_regime_filter_candidates.py"
    text = path.read_text(encoding="utf-8")
    blocked = re.compile(
        "|".join(
            [
                "order_" + "send",
                "place_" + "order",
                "execute_" + "trade",
                "open_" + "position",
                "close_" + "position",
                "trade_" + "send",
                "position_" + "open",
                "position_" + "close",
                "import " + "Meta" + "Trader5",
                "from " + "Meta" + "Trader5",
                "mt5" + r"\.",
            ]
        )
    )

    assert blocked.findall(text) == []
