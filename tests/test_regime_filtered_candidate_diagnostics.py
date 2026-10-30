import argparse
import csv
import re
from datetime import datetime, timedelta
from pathlib import Path

from scripts.run_regime_filtered_candidate_diagnostics import (
    CLASS_REJECTED,
    parse_target_family,
    run_regime_filtered_candidate_diagnostics,
    select_review_rows,
)


REGIME_FIELDS = [
    "target_family",
    "horizon",
    "group",
    "direction",
    "symbol",
    "regime_column",
    "regime_value",
    "trades_count",
    "mean_R",
    "profit_factor_R",
    "classification_suggestion",
    "source_files",
]

SOURCE_FIELDS = [
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
    "mean_R",
    "profit_factor_R",
    "cost_mode",
    "return_mode",
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


def regime_row(**overrides: object) -> dict[str, object]:
    row = {
        "target_family": "preferred_1_5atr_1atr_hit_first",
        "horizon": "10",
        "group": "FX",
        "direction": "short",
        "symbol": "GBPUSD",
        "regime_column": "hour_session",
        "regime_value": "Off_hours",
        "trades_count": "250",
        "mean_R": "0.4",
        "profit_factor_R": "2.0",
        "classification_suggestion": "REGIME_DEPENDENT_REVIEW",
        "source_files": "",
    }
    row.update(overrides)
    return row


def source_row(**overrides: object) -> dict[str, object]:
    row = {
        "scope": "candidate",
        "symbol": "EURUSD",
        "direction": "long",
        "timeframe": "M15",
        "horizon": "1",
        "tp_atr": "1.0",
        "sl_atr": "1.0",
        "atr_column": "atr_20",
        "same_bar_policy": "stop_first",
        "filters": "binary_feature:feature_flag:1",
        "trades_count": "10",
        "mean_R": "0.2",
        "profit_factor_R": "1.5",
        "cost_mode": "none",
        "return_mode": "gross",
    }
    row.update(overrides)
    return row


def args_for(tmp_path: Path, regime_csv: Path) -> argparse.Namespace:
    return argparse.Namespace(
        regime_diagnostics_csv=regime_csv,
        min_trades=1,
        min_mean_R=0.0,
        min_profit_factor_R=1.0,
        allowed_regime_column=["hour_session", "volume_dry_up_20", "volume_spike_20", "blackout_window_30m"],
        max_candidates=10,
        overlap_policy="allow_overlap",
        bar_level_no_overlap=False,
        validation_min_trades=1,
        validation_min_mean_R=0.0,
        validation_min_profit_factor_R=1.0,
        min_years=1,
        min_yearly_positive_ratio=0.0,
        min_period_positive_ratio=0.0,
        cost_config=None,
        stress_cost_config=None,
        random_baseline_iterations=0,
        db_path=tmp_path / "unused.db",
        run_id="unit_run",
        output_root=tmp_path / "reports",
        overwrite=False,
    )


def synthetic_rows(trade_count: int = 10) -> list[dict[str, object]]:
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
                "hour_session": "Off_hours",
                "spread": 0,
            }
        )
    for index in range(trade_count):
        future = rows[index + 1]
        if index < 6:
            future["high"] = 101.1
            future["low"] = 99.5
        else:
            future["high"] = 100.5
            future["low"] = 98.9
    return rows


def sequence_rows(outcomes: list[str], *, symbol: str = "EURUSD", direction: str = "long") -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = datetime(2024, 1, 1)
    row_count = len(outcomes) * 2 + 1
    for index in range(row_count):
        timestamp = start + timedelta(minutes=15 * index)
        rows.append(
            {
                "symbol": symbol,
                "timeframe": "M15",
                "time_server": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.0,
                "atr_20": 1.0,
                "feature_flag": 1,
                "hour_session": "Off_hours",
                "spread": 0,
            }
        )
    for trade_index, outcome in enumerate(outcomes):
        exit_row = rows[trade_index * 2 + 1]
        if direction == "long":
            if outcome == "tp":
                exit_row["high"] = 101.1
                exit_row["low"] = 99.5
            elif outcome == "sl":
                exit_row["high"] = 100.5
                exit_row["low"] = 98.9
        else:
            if outcome == "tp":
                exit_row["high"] = 100.5
                exit_row["low"] = 98.9
            elif outcome == "sl":
                exit_row["high"] = 101.1
                exit_row["low"] = 99.5
    return rows


def enable_bar_level(args: argparse.Namespace) -> argparse.Namespace:
    args.bar_level_no_overlap = True
    args.validation_min_trades = 1
    args.validation_min_mean_R = 0.0
    args.validation_min_profit_factor_R = 1.0
    args.min_yearly_positive_ratio = 0.0
    args.min_period_positive_ratio = 0.0
    return args


def test_selects_only_review_rows() -> None:
    rows = [
        regime_row(classification_suggestion="WEAK"),
        regime_row(symbol="EURUSD", classification_suggestion="REGIME_DEPENDENT_REVIEW"),
    ]

    selected = select_review_rows(
        rows,
        min_trades=1,
        min_mean_R=0.0,
        min_profit_factor_R=1.0,
        allowed_regime_columns=("hour_session",),
        max_candidates=10,
        overlap_policy="allow_overlap",
    )

    assert len(selected) == 1
    assert selected[0].symbol == "EURUSD"


def test_applies_minimum_metric_filters() -> None:
    rows = [
        regime_row(symbol="EURUSD", trades_count="10", mean_R="0.5", profit_factor_R="2.0"),
        regime_row(symbol="GBPUSD", trades_count="200", mean_R="-0.1", profit_factor_R="2.0"),
        regime_row(symbol="USDJPY", trades_count="200", mean_R="0.5", profit_factor_R="0.9"),
    ]

    selected = select_review_rows(
        rows,
        min_trades=100,
        min_mean_R=0.0,
        min_profit_factor_R=1.0,
        allowed_regime_columns=("hour_session",),
        max_candidates=10,
        overlap_policy="allow_overlap",
    )

    assert selected == []


def test_deduplicates_equivalent_news_columns() -> None:
    rows = [
        regime_row(regime_column="has_news_next_30m", regime_value="0", mean_R="0.9"),
        regime_row(regime_column="blackout_window_30m", regime_value="0", mean_R="0.3"),
        regime_row(regime_column="post_news_window_30m", regime_value="0", mean_R="0.8"),
    ]

    selected = select_review_rows(
        rows,
        min_trades=1,
        min_mean_R=0.0,
        min_profit_factor_R=1.0,
        allowed_regime_columns=("has_news_next_30m", "blackout_window_30m", "post_news_window_30m"),
        max_candidates=10,
        overlap_policy="allow_overlap",
    )

    assert len(selected) == 1
    assert selected[0].regime_column == "blackout_window_30m"


def test_maps_target_family_to_tp_sl() -> None:
    assert parse_target_family("preferred_1_5atr_1atr_hit_first") == (1.5, 1.0)
    assert parse_target_family("preferred_2atr_1atr_hit_first") == (2.0, 1.0)


def test_validation_outputs_metrics_and_research_warning(tmp_path: Path) -> None:
    source_csv = tmp_path / "reports" / "tp_sl_path_backtests" / "run" / "long" / "tp_sl_path_backtest_summary.csv"
    write_csv(source_csv, SOURCE_FIELDS, [source_row()])
    regime_csv = tmp_path / "regime_filter_diagnostics.csv"
    write_csv(
        regime_csv,
        REGIME_FIELDS,
        [
            regime_row(
                target_family="preferred_1atr_1atr_hit_first",
                horizon="1",
                group="FX",
                direction="long",
                symbol="EURUSD",
                source_files=str(source_csv),
            )
        ],
    )

    def row_loader(_db_path: Path, _symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return synthetic_rows(10)

    outputs = run_regime_filtered_candidate_diagnostics(
        args_for(tmp_path, regime_csv),
        row_loader=row_loader,
    )
    summary_rows = read_csv(outputs["regime_filtered_candidate_summary"])
    report_text = outputs["regime_filtered_candidate_report"].read_text(encoding="utf-8")

    assert "Research-Only Warning" in report_text
    assert len(summary_rows) == 1
    assert summary_rows[0]["trades_count"] == "10"
    assert abs(float(summary_rows[0]["mean_R"]) - 0.2) < 1e-9
    assert abs(float(summary_rows[0]["profit_factor_R"]) - 1.5) < 1e-9
    assert summary_rows[0]["classification"] in {CLASS_REJECTED, "REGIME_REVIEW_RETAINED", "NEEDS_YEARLY_VALIDATION"}


def test_bar_level_no_overlap_skips_overlapping_same_symbol_entries(tmp_path: Path) -> None:
    source_csv = tmp_path / "source.csv"
    write_csv(source_csv, SOURCE_FIELDS, [source_row(symbol="EURUSD", horizon="1")])
    regime_csv = tmp_path / "regime_filter_diagnostics.csv"
    write_csv(
        regime_csv,
        REGIME_FIELDS,
        [
            regime_row(
                target_family="preferred_1atr_1atr_hit_first",
                horizon="1",
                group="FX",
                direction="long",
                symbol="EURUSD",
                source_files=str(source_csv),
            )
        ],
    )

    def row_loader(_db_path: Path, symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sequence_rows(["tp", "tp", "tp"], symbol=symbol)

    outputs = run_regime_filtered_candidate_diagnostics(
        enable_bar_level(args_for(tmp_path, regime_csv)),
        row_loader=row_loader,
    )
    summary = read_csv(outputs["regime_filtered_candidate_summary"])[0]

    assert summary["sequential_trades_count"] == "3"
    assert summary["skipped_due_to_overlap"] == "3"


def test_opposite_direction_same_symbol_entries_are_skipped_while_open(tmp_path: Path) -> None:
    source_csv = tmp_path / "source.csv"
    write_csv(
        source_csv,
        SOURCE_FIELDS,
        [
            source_row(symbol="EURUSD", direction="long", horizon="1"),
            source_row(symbol="EURUSD", direction="short", horizon="1"),
        ],
    )
    regime_csv = tmp_path / "regime_filter_diagnostics.csv"
    write_csv(
        regime_csv,
        REGIME_FIELDS,
        [
            regime_row(target_family="preferred_1atr_1atr_hit_first", horizon="1", group="FX", direction="long", symbol="EURUSD", source_files=str(source_csv)),
            regime_row(target_family="preferred_1atr_1atr_hit_first", horizon="1", group="FX", direction="short", symbol="EURUSD", source_files=str(source_csv)),
        ],
    )

    def row_loader(_db_path: Path, symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sequence_rows(["tp", "tp"], symbol=symbol)

    outputs = run_regime_filtered_candidate_diagnostics(
        enable_bar_level(args_for(tmp_path, regime_csv)),
        row_loader=row_loader,
    )
    summaries = read_csv(outputs["regime_filtered_candidate_summary"])
    skipped_total = sum(int(row["skipped_due_to_overlap"] or 0) for row in summaries)

    assert len(summaries) == 2
    assert skipped_total > 0


def test_different_symbols_can_overlap_in_bar_level_replay(tmp_path: Path) -> None:
    source_csv = tmp_path / "source.csv"
    write_csv(
        source_csv,
        SOURCE_FIELDS,
        [
            source_row(symbol="EURUSD", direction="long", horizon="1"),
            source_row(symbol="GBPUSD", direction="long", horizon="1"),
        ],
    )
    regime_csv = tmp_path / "regime_filter_diagnostics.csv"
    write_csv(
        regime_csv,
        REGIME_FIELDS,
        [
            regime_row(target_family="preferred_1atr_1atr_hit_first", horizon="1", group="FX", direction="long", symbol="EURUSD", source_files=str(source_csv)),
            regime_row(target_family="preferred_1atr_1atr_hit_first", horizon="1", group="FX", direction="long", symbol="GBPUSD", source_files=str(source_csv)),
        ],
    )

    def row_loader(_db_path: Path, symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sequence_rows(["tp", "tp"], symbol=symbol)

    outputs = run_regime_filtered_candidate_diagnostics(
        enable_bar_level(args_for(tmp_path, regime_csv)),
        row_loader=row_loader,
    )
    summaries = read_csv(outputs["regime_filtered_candidate_summary"])

    assert {row["symbol"] for row in summaries} == {"EURUSD", "GBPUSD"}
    assert all(row["sequential_trades_count"] == "2" for row in summaries)
    assert all(row["skipped_due_to_overlap"] == "2" for row in summaries)


def test_trade_log_and_equity_curve_are_written_with_sequential_risk_metrics(tmp_path: Path) -> None:
    source_csv = tmp_path / "source.csv"
    write_csv(source_csv, SOURCE_FIELDS, [source_row(symbol="EURUSD", horizon="1")])
    regime_csv = tmp_path / "regime_filter_diagnostics.csv"
    write_csv(
        regime_csv,
        REGIME_FIELDS,
        [
            regime_row(
                target_family="preferred_1atr_1atr_hit_first",
                horizon="1",
                group="FX",
                direction="long",
                symbol="EURUSD",
                source_files=str(source_csv),
            )
        ],
    )

    def row_loader(_db_path: Path, symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sequence_rows(["sl", "sl", "tp"], symbol=symbol)

    outputs = run_regime_filtered_candidate_diagnostics(
        enable_bar_level(args_for(tmp_path, regime_csv)),
        row_loader=row_loader,
    )
    summary = read_csv(outputs["regime_filtered_candidate_summary"])[0]
    candidate_id = summary["candidate_id"]
    trade_log = tmp_path / "reports" / "unit_run" / "trade_logs" / f"{candidate_id}_trade_log.csv"
    equity_curve = tmp_path / "reports" / "unit_run" / "equity_curves" / f"{candidate_id}_equity_curve.csv"

    assert trade_log.exists()
    assert equity_curve.exists()
    assert len(read_csv(trade_log)) == 3
    equity_rows = read_csv(equity_curve)
    assert equity_rows[-1]["cumulative_R"] == "-1.0"
    assert summary["sequential_max_drawdown_R"] == "2.0"
    assert summary["sequential_max_consecutive_losses"] == "2"
    assert summary["classification"] == CLASS_REJECTED


def test_stress_cost_and_random_baseline_requests_record_clear_unsupported_reasons(tmp_path: Path) -> None:
    source_csv = tmp_path / "source.csv"
    write_csv(source_csv, SOURCE_FIELDS, [source_row(symbol="EURUSD", horizon="1")])
    regime_csv = tmp_path / "regime_filter_diagnostics.csv"
    write_csv(
        regime_csv,
        REGIME_FIELDS,
        [
            regime_row(
                target_family="preferred_1atr_1atr_hit_first",
                horizon="1",
                group="FX",
                direction="long",
                symbol="EURUSD",
                source_files=str(source_csv),
            )
        ],
    )
    args = args_for(tmp_path, regime_csv)
    args.stress_cost_config = tmp_path / "stress_cost.json"
    args.random_baseline_iterations = 10

    def row_loader(_db_path: Path, symbol: str, _timeframe: str) -> list[dict[str, object]]:
        return sequence_rows(["tp"], symbol=symbol)

    outputs = run_regime_filtered_candidate_diagnostics(args, row_loader=row_loader)
    summary = read_csv(outputs["regime_filtered_candidate_summary"])[0]

    assert summary["stress_cost_config_requested"] == str(args.stress_cost_config)
    assert "not implemented" in summary["stress_cost_not_available_reason"]
    assert summary["random_baseline_iterations"] == "10"
    assert "not implemented" in summary["random_baseline_not_available_reason"]


def test_report_avoids_blocked_language(tmp_path: Path) -> None:
    regime_csv = tmp_path / "regime_filter_diagnostics.csv"
    write_csv(regime_csv, REGIME_FIELDS, [regime_row()])

    outputs = run_regime_filtered_candidate_diagnostics(args_for(tmp_path, regime_csv))
    combined_text = "\n".join(path.read_text(encoding="utf-8").lower() for path in outputs.values())

    assert "buy" not in combined_text
    assert "sell" not in combined_text
    assert "live signal" not in combined_text
    assert "trade signal" not in combined_text
    assert "strategy" not in combined_text
    assert "promotion" not in combined_text
    assert "promote" not in combined_text


def test_script_does_not_import_metatrader5_or_live_api_terms() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_regime_filtered_candidate_diagnostics.py"
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
