import argparse
import csv
import math
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from scripts.run_tp_sl_path_backtests import (
    PathConfig,
    build_outputs,
    evaluate_rows,
    run_tp_sl_path_backtests,
    simulate_path_exit,
)


def config(
    *,
    direction: str = "long",
    horizon: int = 10,
    tp_atr: float = 2.0,
    sl_atr: float = 1.0,
    cost_mode: str = "none",
    return_mode: str = "gross",
) -> PathConfig:
    return PathConfig(
        symbol="XTEST",
        timeframe="M15",
        direction=direction,
        horizon=horizon,
        tp_atr=tp_atr,
        sl_atr=sl_atr,
        atr_column="atr_20",
        same_bar_policy="stop_first",
        filters=("binary_feature:feature_flag:1",),
        cost_mode=cost_mode,
        return_mode=return_mode,
        min_trades=1,
    )


def row(
    index: int,
    *,
    close: float = 100.0,
    high: float = 100.5,
    low: float = 99.5,
    atr: float | None = 1.0,
    flag: int = 1,
    context_flag: int = 1,
) -> dict[str, object]:
    timestamp = datetime(2024, 1, 1) + timedelta(minutes=15 * index)
    return {
        "symbol": "XTEST",
        "timeframe": "M15",
        "time_server": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "atr_20": atr,
        "feature_flag": flag,
        "context_flag": context_flag,
        "spread": 0,
    }


def path_rows(length: int = 12) -> list[dict[str, object]]:
    return [row(index) for index in range(length)]


def test_long_tp_hit_first() -> None:
    rows = path_rows()
    rows[3].update({"high": 102.1, "low": 99.5})

    outcome, reason = simulate_path_exit(rows, 0, config=config(), cost_config={})

    assert reason is None
    assert outcome is not None
    assert outcome.exit_reason == "tp"
    assert outcome.exit_bars == 3
    assert math.isclose(outcome.selected_R, 2.0)


def test_long_sl_hit_first() -> None:
    rows = path_rows()
    rows[2].update({"high": 100.5, "low": 98.9})

    outcome, reason = simulate_path_exit(rows, 0, config=config(), cost_config={})

    assert reason is None
    assert outcome is not None
    assert outcome.exit_reason == "sl"
    assert outcome.exit_bars == 2
    assert math.isclose(outcome.selected_R, -1.0)


def test_long_same_bar_tp_and_sl_conflict_uses_stop_first() -> None:
    rows = path_rows()
    rows[1].update({"high": 102.1, "low": 98.9})

    outcome, reason = simulate_path_exit(rows, 0, config=config(), cost_config={})

    assert reason is None
    assert outcome is not None
    assert outcome.exit_reason == "sl"
    assert outcome.same_bar_conflict is True
    assert math.isclose(outcome.selected_R, -1.0)


def test_long_timeout_exits_at_horizon_close() -> None:
    rows = path_rows()
    rows[10].update({"close": 101.0, "high": 101.5, "low": 99.5})

    outcome, reason = simulate_path_exit(rows, 0, config=config(), cost_config={})

    assert reason is None
    assert outcome is not None
    assert outcome.exit_reason == "timeout"
    assert outcome.exit_bars == 10
    assert math.isclose(outcome.selected_R, 1.0)


def test_short_tp_hit_first() -> None:
    rows = path_rows()
    rows[4].update({"high": 100.5, "low": 97.9})

    outcome, reason = simulate_path_exit(rows, 0, config=config(direction="short"), cost_config={})

    assert reason is None
    assert outcome is not None
    assert outcome.exit_reason == "tp"
    assert outcome.exit_bars == 4
    assert math.isclose(outcome.selected_R, 2.0)


def test_short_sl_hit_first() -> None:
    rows = path_rows()
    rows[5].update({"high": 101.1, "low": 99.5})

    outcome, reason = simulate_path_exit(rows, 0, config=config(direction="short"), cost_config={})

    assert reason is None
    assert outcome is not None
    assert outcome.exit_reason == "sl"
    assert outcome.exit_bars == 5
    assert math.isclose(outcome.selected_R, -1.0)


def test_invalid_or_missing_atr_rows_are_skipped() -> None:
    rows = path_rows()
    rows[0]["atr_20"] = None

    outcome, reason = simulate_path_exit(rows, 0, config=config(), cost_config={})

    assert outcome is None
    assert reason == "invalid_or_missing_atr"


def test_candidate_filters_are_applied_correctly() -> None:
    cfg = config(horizon=1, tp_atr=1.0)
    rows = [
        row(0, close=100.0, flag=1),
        row(1, close=100.0, high=101.1, low=99.5, flag=0),
        row(2, close=100.0, high=101.1, low=99.5, flag=0),
    ]

    outcomes, skipped = evaluate_rows(
        rows,
        config=cfg,
        filters=("binary_feature:feature_flag:1",),
        cost_config={},
        scope="candidate",
    )

    assert skipped == []
    assert len(outcomes) == 1
    assert outcomes[0].row_index == 0


def test_baseline_rows_are_computed_separately_from_candidate_rows() -> None:
    cfg = config(horizon=1, tp_atr=1.0)
    rows = [
        row(0, close=100.0, flag=1),
        row(1, close=100.0, high=101.1, low=99.5, flag=0),
        row(2, close=100.0, high=101.1, low=99.5, flag=0),
    ]

    _detail_rows, summary_rows, _skipped = build_outputs(
        rows=rows,
        config=cfg,
        cost_config={},
        cost_fields={
            "cost_config_source": "not_applicable",
            "point_size_source": "not_applicable",
            "spread_source_used": "not_applicable",
            "symbols_using_default_costs": "",
        },
    )

    assert summary_rows[0]["scope"] == "candidate"
    assert summary_rows[1]["scope"] == "baseline_all"
    assert summary_rows[0]["trades_count"] == 1
    assert summary_rows[1]["trades_count"] == 2
    assert summary_rows[0]["baseline_trades_count"] == 2


def test_estimated_net_cost_adjustment_changes_R_result() -> None:
    rows = path_rows()
    rows[0]["spread"] = 10
    rows[3].update({"high": 102.1, "low": 99.5})
    cost_config = {"default": {}, "symbols": {"XTEST": {"point_size": 0.01}}}

    gross_outcome, _gross_reason = simulate_path_exit(
        rows,
        0,
        config=config(cost_mode="estimated", return_mode="gross"),
        cost_config=cost_config,
    )
    net_outcome, _net_reason = simulate_path_exit(
        rows,
        0,
        config=config(cost_mode="estimated", return_mode="net"),
        cost_config=cost_config,
    )

    assert gross_outcome is not None
    assert net_outcome is not None
    assert gross_outcome.selected_R == gross_outcome.gross_R
    assert net_outcome.selected_R == net_outcome.net_R
    assert net_outcome.selected_R < gross_outcome.selected_R
    assert math.isclose(net_outcome.cost_R, 0.1)


def write_ml_dataset(db_path: Path) -> None:
    rows = [
        row(0, close=100.0, flag=1),
        row(1, close=100.0, high=101.1, low=99.5, flag=0),
        row(2, close=100.0, high=101.1, low=99.5, flag=0),
    ]
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE ml_dataset (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                atr_20 REAL,
                feature_flag INTEGER,
                context_flag INTEGER,
                spread REAL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO ml_dataset (
                symbol, timeframe, time_server, open, high, low, close, atr_20, feature_flag, context_flag, spread
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["symbol"],
                    item["timeframe"],
                    item["time_server"],
                    item["open"],
                    item["high"],
                    item["low"],
                    item["close"],
                    item["atr_20"],
                    item["feature_flag"],
                    item["context_flag"],
                    item["spread"],
                )
                for item in rows
            ],
        )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def cli_args(tmp_path: Path, db_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        symbol="XTEST",
        timeframe="M15",
        direction="long",
        horizon=1,
        tp_atr=1.0,
        sl_atr=1.0,
        atr_column="atr_20",
        same_bar_policy="stop_first",
        filters=["binary_feature:feature_flag:1"],
        combination_input_csv=None,
        target_label=None,
        cost_mode="none",
        return_mode="gross",
        strict_cost_config=False,
        cost_config=None,
        run_id="unit_run",
        output_root=tmp_path / "reports",
        db_path=db_path,
        min_trades=1,
        overwrite=False,
    )


def write_combination_input_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "direction",
        "combination_id",
        "feature_1",
        "scenario_1",
        "feature_family_1",
        "feature_2",
        "scenario_2",
        "feature_family_2",
        "mean_return",
        "profit_factor",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for item in rows:
            writer.writerow(item)


def valid_combination_rows() -> list[dict[str, object]]:
    return [
        {
            "symbol": "XTEST",
            "direction": "long",
            "combination_id": "combo_a",
            "feature_1": "feature_flag",
            "scenario_1": "binary_feature:feature_flag:1",
            "feature_family_1": "trend/ma",
            "feature_2": "context_flag",
            "scenario_2": "binary_feature:context_flag:1",
            "feature_family_2": "volume/liquidity",
            "mean_return": "0.0001",
            "profit_factor": "1.1",
            "notes": "source close-to-close row",
        },
        {
            "symbol": "XTEST",
            "direction": "long",
            "combination_id": "combo_b",
            "feature_1": "feature_flag",
            "scenario_1": "binary_feature:feature_flag:0",
            "feature_family_1": "momentum/returns",
            "feature_2": "context_flag",
            "scenario_2": "binary_feature:context_flag:1",
            "feature_family_2": "spread/liquidity",
            "mean_return": "0.0002",
            "profit_factor": "1.2",
            "notes": "second source row",
        },
    ]


def batch_cli_args(tmp_path: Path, db_path: Path, input_csv: Path) -> argparse.Namespace:
    args = cli_args(tmp_path, db_path)
    args.filters = []
    args.combination_input_csv = input_csv
    args.run_id = "batch_unit_run"
    args.direction = "long"
    return args


def test_output_report_contains_research_only_warning(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    write_ml_dataset(db_path)

    outputs = run_tp_sl_path_backtests(cli_args(tmp_path, db_path))
    report_text = outputs["tp_sl_path_backtest_report"].read_text(encoding="utf-8")

    assert "## Research-only warning" in report_text
    assert "Offline diagnostic for fixed historical filters only." in report_text


def test_output_report_avoids_blocked_recommendation_language(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    write_ml_dataset(db_path)

    outputs = run_tp_sl_path_backtests(cli_args(tmp_path, db_path))
    report_text = outputs["tp_sl_path_backtest_report"].read_text(encoding="utf-8").lower()

    assert "buy" not in report_text
    assert "sell" not in report_text
    assert "live signal" not in report_text


def test_summary_and_detail_outputs_are_written(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    write_ml_dataset(db_path)

    outputs = run_tp_sl_path_backtests(cli_args(tmp_path, db_path))
    summary_rows = read_csv_rows(outputs["tp_sl_path_backtest_summary"])
    detail_rows = read_csv_rows(outputs["tp_sl_path_backtest_detail"])

    assert summary_rows[0]["scope"] == "candidate"
    assert detail_rows[0]["exit_reason"] == "tp"


def test_batch_mode_reads_combination_csv_and_evaluates_existing_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    write_ml_dataset(db_path)
    input_csv = tmp_path / "long" / "combination_backtest_detail.csv"
    write_combination_input_csv(input_csv, valid_combination_rows())

    outputs = run_tp_sl_path_backtests(batch_cli_args(tmp_path, db_path, input_csv))
    summary_rows = read_csv_rows(outputs["tp_sl_path_backtest_summary"])
    detail_rows = read_csv_rows(outputs["tp_sl_path_backtest_detail"])
    skipped_rows = read_csv_rows(outputs["skipped_tp_sl_path_rows"])

    assert len(summary_rows) == 2
    assert len(detail_rows) == 2
    assert {row["source_combination_id"] for row in summary_rows} == {"combo_a", "combo_b"}
    assert {row["source_combination_id"] for row in detail_rows} == {"combo_a", "combo_b"}
    assert {row["source_feature_1"] for row in summary_rows} == {"feature_flag"}
    assert {row["source_scenario_2"] for row in summary_rows} == {"binary_feature:context_flag:1"}
    assert summary_rows[0]["source_close_to_close_mean_return"] == "0.0001"
    assert not [row for row in skipped_rows if row["scope"] == "combination"]


def test_batch_mode_does_not_create_new_feature_pairs(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    write_ml_dataset(db_path)
    input_csv = tmp_path / "long" / "combination_backtest_detail.csv"
    input_rows = valid_combination_rows()
    write_combination_input_csv(input_csv, input_rows)

    outputs = run_tp_sl_path_backtests(batch_cli_args(tmp_path, db_path, input_csv))
    summary_rows = read_csv_rows(outputs["tp_sl_path_backtest_summary"])

    input_ids = {str(row["combination_id"]) for row in input_rows}
    output_ids = {row["source_combination_id"] for row in summary_rows}
    assert output_ids == input_ids
    assert all("combo_a AND combo_b" != row["source_combination_id"] for row in summary_rows)


def test_batch_mode_skips_malformed_missing_and_unparseable_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    write_ml_dataset(db_path)
    input_csv = tmp_path / "long" / "combination_backtest_detail.csv"
    rows = [
        *valid_combination_rows(),
        {
            **valid_combination_rows()[0],
            "combination_id": "malformed_missing_feature",
            "feature_2": "",
        },
        {
            **valid_combination_rows()[0],
            "combination_id": "missing_symbol",
            "symbol": "",
        },
        {
            **valid_combination_rows()[0],
            "combination_id": "missing_direction",
            "direction": "",
        },
        {
            **valid_combination_rows()[0],
            "combination_id": "unparseable_filter",
            "scenario_1": "unsupported_filter:feature_flag:1",
        },
    ]
    write_combination_input_csv(input_csv, rows)

    outputs = run_tp_sl_path_backtests(batch_cli_args(tmp_path, db_path, input_csv))
    summary_rows = read_csv_rows(outputs["tp_sl_path_backtest_summary"])
    skipped_rows = read_csv_rows(outputs["skipped_tp_sl_path_rows"])
    skipped_combinations = [row for row in skipped_rows if row["scope"] == "combination"]
    reasons = {row["source_combination_id"]: row["skip_reason"] for row in skipped_combinations}

    assert {row["source_combination_id"] for row in summary_rows} == {"combo_a", "combo_b"}
    assert reasons["malformed_missing_feature"].startswith("missing_required_combination_fields")
    assert reasons["missing_symbol"] == "missing_symbol"
    assert reasons["missing_direction"] == "missing_direction"
    assert reasons["unparseable_filter"].startswith("filter_parse_or_apply_failed")


def test_batch_report_contains_required_sections_and_classification_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    write_ml_dataset(db_path)
    input_csv = tmp_path / "long" / "combination_backtest_detail.csv"
    write_combination_input_csv(input_csv, valid_combination_rows())

    outputs = run_tp_sl_path_backtests(batch_cli_args(tmp_path, db_path, input_csv))
    report_text = outputs["tp_sl_path_backtest_report"].read_text(encoding="utf-8")

    assert "## Research-only warning" in report_text
    assert "## Batch input" in report_text
    assert "## Summary by classification" in report_text
    assert "## Top path-exit rows by profit_factor_R" in report_text
    assert "## Interpretation guardrails" in report_text


def test_batch_report_and_outputs_avoid_blocked_recommendation_language(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    write_ml_dataset(db_path)
    input_csv = tmp_path / "long" / "combination_backtest_detail.csv"
    write_combination_input_csv(input_csv, valid_combination_rows())

    outputs = run_tp_sl_path_backtests(batch_cli_args(tmp_path, db_path, input_csv))
    combined_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in outputs.values()
    )

    assert "buy" not in combined_text
    assert "sell" not in combined_text
    assert "live signal" not in combined_text


def test_explicit_filter_single_candidate_mode_still_works(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    write_ml_dataset(db_path)

    outputs = run_tp_sl_path_backtests(cli_args(tmp_path, db_path))
    summary_rows = read_csv_rows(outputs["tp_sl_path_backtest_summary"])
    detail_rows = read_csv_rows(outputs["tp_sl_path_backtest_detail"])

    assert summary_rows[0]["scope"] == "candidate"
    assert summary_rows[0]["filters"] == "binary_feature:feature_flag:1"
    assert detail_rows[0]["filters"] == "binary_feature:feature_flag:1"


def test_script_does_not_import_metatrader5_or_live_api_terms() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tp_sl_path_backtests.py"
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
