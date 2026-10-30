import argparse
import csv
from pathlib import Path

from scripts.run_preferred_feature_combination_backtests import (
    PreferredCandidate,
    build_controlled_combinations,
    cost_mode_comparison_path,
    run_preferred_feature_combination_backtests,
)


COMPARISON_FIELDS = [
    "symbol",
    "direction",
    "feature",
    "feature_family",
    "scenario",
    "scenario_source",
    "is_preferred_shortlist_feature",
    "feature_in_shortlist",
    "condition_type",
    "condition_value",
    "gross_trades_count",
    "gross_mean_return",
    "gross_profit_factor",
    "net_trades_count",
    "net_mean_return",
    "net_profit_factor",
    "gross_positive",
    "net_positive",
    "cost_erased_edge",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def comparison_row(
    *,
    symbol: str,
    direction: str,
    feature: str,
    family: str,
    scenario: str,
    condition_type: str = "numeric_tercile",
    condition_value: str = "high_tercile",
    scenario_source: str = "preferred_shortlist_feature",
    feature_in_shortlist: str = "true",
    is_preferred_shortlist_feature: str = "true",
    gross_trades_count: int = 300,
    net_trades_count: int = 300,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "direction": direction,
        "feature": feature,
        "feature_family": family,
        "scenario": scenario,
        "scenario_source": scenario_source,
        "is_preferred_shortlist_feature": is_preferred_shortlist_feature,
        "feature_in_shortlist": feature_in_shortlist,
        "condition_type": condition_type,
        "condition_value": condition_value,
        "gross_trades_count": gross_trades_count,
        "gross_mean_return": 0.001,
        "gross_profit_factor": 1.2,
        "net_trades_count": net_trades_count,
        "net_mean_return": -0.0001,
        "net_profit_factor": 0.9,
        "gross_positive": "true",
        "net_positive": "false",
        "cost_erased_edge": "true",
    }


def candidate(feature: str, family: str, index: int) -> PreferredCandidate:
    return PreferredCandidate(
        symbol="EURUSD",
        direction="long",
        feature=feature,
        feature_family=family,
        scenario=f"numeric_tercile:{feature}:high_tercile",
        condition_type="numeric_tercile",
        condition_value="high_tercile",
        gross_trades_count=300,
        net_trades_count=300,
        gross_mean_return=0.001 + index / 10000,
        gross_profit_factor=1.2 + index / 100,
        source_rank=index,
    )


def args_for(tmp_path: Path, *, directions: list[str] | None = None, symbols: list[str] | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        symbols=symbols or ["EURUSD", "GBPUSD", "USDJPY"],
        timeframe="M15",
        horizon=10,
        directions=directions or ["long", "short"],
        gross_run_id="gross_run",
        net_run_id="net_run",
        cost_mode="estimated",
        return_mode="net",
        cost_config=None,
        strict_cost_config=False,
        min_gross_profit_factor=1.02,
        min_gross_mean_return=0.0,
        max_combinations_per_symbol_direction=30,
        reports_root=tmp_path / "preferred_feature_backtests",
        output_root=tmp_path / "preferred_feature_combination_backtests",
        db_path=tmp_path / "test.db",
        run_id="combo_run",
        overwrite=False,
    )


def synthetic_rows(*, overlap: bool) -> list[dict[str, object]]:
    rows = []
    for index in range(12):
        if overlap:
            spread_value = 12 - index
        else:
            spread_value = index
        rows.append(
            {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "time_server": f"2024-01-{index + 1:02d} 00:00:00",
                "close": 1.0,
                "spread": 0,
                "return_1": index,
                "return_5": index,
                "spread_return": spread_value,
                "future_return_10": 0.002 if index % 2 == 0 else -0.0005,
            }
        )
    return rows


def write_default_comparison_inputs(args: argparse.Namespace) -> None:
    write_csv(
        cost_mode_comparison_path(args.reports_root, args.gross_run_id, args.net_run_id, "long"),
        COMPARISON_FIELDS,
        [
            comparison_row(
                symbol="EURUSD",
                direction="long",
                feature="return_5",
                family="momentum/returns",
                scenario="numeric_tercile:return_5:high_tercile",
            ),
            comparison_row(
                symbol="EURUSD",
                direction="long",
                feature="spread_return",
                family="spread/liquidity",
                scenario="numeric_tercile:spread_return:low_tercile",
                condition_value="low_tercile",
            ),
            comparison_row(
                symbol="XAUUSD",
                direction="long",
                feature="return_5",
                family="momentum/returns",
                scenario="numeric_tercile:return_5:high_tercile",
            ),
            comparison_row(
                symbol="XAUUSD",
                direction="long",
                feature="spread_return",
                family="spread/liquidity",
                scenario="numeric_tercile:spread_return:low_tercile",
                condition_value="low_tercile",
            ),
        ],
    )
    write_csv(
        cost_mode_comparison_path(args.reports_root, args.gross_run_id, args.net_run_id, "short"),
        COMPARISON_FIELDS,
        [
            comparison_row(
                symbol="GBPUSD",
                direction="short",
                feature="return_1",
                family="momentum/returns",
                scenario="numeric_tercile:return_1:high_tercile",
            ),
            comparison_row(
                symbol="GBPUSD",
                direction="short",
                feature="spread_return",
                family="spread/liquidity",
                scenario="numeric_tercile:spread_return:low_tercile",
                condition_value="low_tercile",
            ),
        ],
    )


def write_comparison_inputs(
    args: argparse.Namespace,
    direction: str,
    rows: list[dict[str, object]],
) -> None:
    write_csv(
        cost_mode_comparison_path(args.reports_root, args.gross_run_id, args.net_run_id, direction),
        COMPARISON_FIELDS,
        rows,
    )


def no_call_loader(_db_path: Path, symbol: str, _timeframe: str, _return_column: str) -> list[dict[str, object]]:
    raise AssertionError(f"row_loader should not be called for {symbol}")


def test_candidate_combinations_are_controlled_and_family_allowed() -> None:
    candidates = [
        candidate("return_5", "momentum/returns", 1),
        candidate("ma_diff_atr_20", "trend/ma", 2),
        candidate("spread_return", "spread/liquidity", 3),
        candidate("range_to_atr_20", "volatility/range", 4),
        candidate("hour", "session/calendar", 5),
    ]

    pairs, skipped = build_controlled_combinations(candidates, max_combinations=30)

    assert len(pairs) == 2
    assert len(pairs) < 4
    for pair in pairs:
        families = {pair.primary.feature_family, pair.secondary.feature_family}
        assert families & {"momentum/returns", "trend/ma"}
        assert families & {"volume/liquidity", "volatility/range", "spread/liquidity"}
    assert skipped[0]["skip_reason"] == "candidate_family_not_allowed_for_controlled_pairing"


def test_empty_cost_mode_comparison_input_reports_no_eligible_candidates(tmp_path: Path) -> None:
    args = args_for(tmp_path, directions=["long"], symbols=["EURUSD"])
    write_comparison_inputs(args, "long", [])

    outputs = run_preferred_feature_combination_backtests(args, row_loader=no_call_loader)
    report_text = outputs["long"]["combination_backtest_report"].read_text(encoding="utf-8")
    diagnostics = read_csv(outputs["long"]["candidate_diagnostics"])

    assert "No eligible candidates loaded from cost_mode_comparison.csv." in report_text
    assert "cost_mode_comparison rows loaded: 0" in report_text
    assert diagnostics[-1]["symbol"] == "ALL"
    assert diagnostics[-1]["input_rows_loaded"] == "0"


def test_standard_context_rows_do_not_become_candidates(tmp_path: Path) -> None:
    args = args_for(tmp_path, directions=["long"], symbols=["EURUSD"])
    write_comparison_inputs(
        args,
        "long",
        [
            comparison_row(
                symbol="EURUSD",
                direction="long",
                feature="day_of_week",
                family="session/calendar",
                scenario="day_of_week:day_of_week:Monday",
                scenario_source="standard_context_scenario",
                feature_in_shortlist="false",
                is_preferred_shortlist_feature="false",
            )
        ],
    )

    outputs = run_preferred_feature_combination_backtests(args, row_loader=no_call_loader)
    diagnostics = read_csv(outputs["long"]["candidate_diagnostics"])
    skipped_rows = read_csv(outputs["long"]["skipped_combinations"])

    assert diagnostics[-1]["rows_after_symbol_filter"] == "1"
    assert diagnostics[-1]["rows_after_shortlist_filter"] == "0"
    assert diagnostics[-1]["eligible_candidates_total"] == "0"
    assert skipped_rows == []


def test_preferred_candidates_with_only_primary_families_write_skipped_rows(tmp_path: Path) -> None:
    args = args_for(tmp_path, directions=["long"], symbols=["EURUSD"])
    write_comparison_inputs(
        args,
        "long",
        [
            comparison_row(
                symbol="EURUSD",
                direction="long",
                feature="return_5",
                family="momentum/returns",
                scenario="numeric_tercile:return_5:high_tercile",
            ),
            comparison_row(
                symbol="EURUSD",
                direction="long",
                feature="ma_diff_atr_20",
                family="trend/ma",
                scenario="numeric_tercile:ma_diff_atr_20:high_tercile",
            ),
        ],
    )

    outputs = run_preferred_feature_combination_backtests(args, row_loader=no_call_loader)
    skipped_rows = read_csv(outputs["long"]["skipped_combinations"])
    diagnostics = read_csv(outputs["long"]["candidate_diagnostics"])

    assert {row["skip_reason"] for row in skipped_rows} == {"no_secondary_family_candidates"}
    assert diagnostics[-1]["primary_candidates"] == "2"
    assert diagnostics[-1]["secondary_candidates"] == "0"


def test_preferred_candidates_with_only_secondary_families_write_skipped_rows(tmp_path: Path) -> None:
    args = args_for(tmp_path, directions=["long"], symbols=["EURUSD"])
    write_comparison_inputs(
        args,
        "long",
        [
            comparison_row(
                symbol="EURUSD",
                direction="long",
                feature="spread_return",
                family="spread/liquidity",
                scenario="numeric_tercile:spread_return:low_tercile",
                condition_value="low_tercile",
            ),
            comparison_row(
                symbol="EURUSD",
                direction="long",
                feature="range_to_atr_20",
                family="volatility/range",
                scenario="numeric_tercile:range_to_atr_20:high_tercile",
            ),
        ],
    )

    outputs = run_preferred_feature_combination_backtests(args, row_loader=no_call_loader)
    skipped_rows = read_csv(outputs["long"]["skipped_combinations"])
    diagnostics = read_csv(outputs["long"]["candidate_diagnostics"])

    assert {row["skip_reason"] for row in skipped_rows} == {"no_primary_family_candidates"}
    assert diagnostics[-1]["primary_candidates"] == "0"
    assert diagnostics[-1]["secondary_candidates"] == "2"


def test_combination_runner_keeps_direction_symbol_defaults_and_report_language(tmp_path: Path) -> None:
    args = args_for(tmp_path)
    write_default_comparison_inputs(args)
    calls: list[tuple[str, str]] = []

    def row_loader(_db_path: Path, symbol: str, _timeframe: str, _return_column: str) -> list[dict[str, object]]:
        calls.append((symbol, _return_column))
        return synthetic_rows(overlap=True)

    outputs = run_preferred_feature_combination_backtests(args, row_loader=row_loader)
    long_rows = read_csv(outputs["long"]["combination_backtest_detail"])
    short_rows = read_csv(outputs["short"]["combination_backtest_detail"])
    report_text = outputs["long"]["combination_backtest_report"].read_text(encoding="utf-8").lower()

    assert {row["direction"] for row in long_rows} == {"long"}
    assert {row["direction"] for row in short_rows} == {"short"}
    assert {row["symbol"] for row in long_rows} == {"EURUSD"}
    assert {symbol for symbol, _return_column in calls} == {"EURUSD", "GBPUSD"}
    assert "XAUUSD" not in {row["symbol"] for row in long_rows + short_rows}
    assert "candidate diagnostics" in report_text
    assert "cost_mode_comparison rows loaded" in report_text
    assert "combinations built" in report_text
    assert "research-only warning" in report_text
    assert "candidate selection logic" in report_text
    assert "net survivors" in report_text
    assert "gross-only candidates" in report_text
    assert "cost-erased combinations" in report_text
    assert "less bad than baseline" in report_text
    assert "skipped combinations" in report_text
    assert "methodology warnings" in report_text
    assert "buy" not in report_text
    assert "sell" not in report_text
    assert "live signal" not in report_text


def test_zero_trade_combinations_are_written_to_skipped(tmp_path: Path) -> None:
    args = args_for(tmp_path, directions=["long"], symbols=["EURUSD"])
    write_comparison_inputs(
        args,
        "long",
        [
            comparison_row(
                symbol="EURUSD",
                direction="long",
                feature="return_5",
                family="momentum/returns",
                scenario="numeric_tercile:return_5:high_tercile",
                gross_trades_count=0,
                net_trades_count=0,
            ),
            comparison_row(
                symbol="EURUSD",
                direction="long",
                feature="spread_return",
                family="spread/liquidity",
                scenario="numeric_tercile:spread_return:low_tercile",
                condition_value="low_tercile",
                gross_trades_count=0,
                net_trades_count=0,
            ),
        ],
    )

    outputs = run_preferred_feature_combination_backtests(args, row_loader=no_call_loader)
    detail_rows = read_csv(outputs["long"]["combination_backtest_detail"])
    skipped_rows = read_csv(outputs["long"]["skipped_combinations"])

    assert detail_rows == []
    assert {row["feature_1"] for row in skipped_rows} == {"return_5", "spread_return"}
    assert {row["skip_reason"] for row in skipped_rows} == {"zero_trades_in_cost_mode_comparison_row"}
