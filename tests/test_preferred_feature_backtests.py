import argparse
import csv
from pathlib import Path

from scripts.run_preferred_feature_backtests import (
    BACKTEST_SUMMARY_FILE,
    run_preferred_feature_backtests,
    shortlist_path,
    symbol_output_dir,
)


SHORTLIST_FIELDS = [
    "direction",
    "timeframe",
    "horizon",
    "target",
    "feature",
    "feature_family",
    "tradability_role",
    "normalized_or_raw",
    "recommended_usage",
    "caution_level",
    "symbols_seen",
    "stability_score",
    "notes",
]

BACKTEST_FIELDS = [
    "symbol",
    "timeframe",
    "target_horizon",
    "direction",
    "cost_mode",
    "return_mode",
    "scenario_name",
    "scenario_type",
    "feature",
    "bucket",
    "sample_flag",
    "trades_count",
    "mean_return",
    "median_return",
    "win_rate",
    "cumulative_return",
    "max_drawdown",
    "profit_factor",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "top_5_percent_trades_contribution_pct",
    "avg_positive_return",
    "avg_negative_return",
    "payoff_ratio",
    "breakeven_winrate",
    "breakeven_winrate_margin",
    "cost_config_source",
    "point_size_source",
    "spread_source_used",
    "symbols_using_default_costs",
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


def shortlist_row(
    direction: str,
    feature: str,
    family: str = "momentum/returns",
    norm: str = "preferred_normalized",
    usage: str = "candidate for controlled combination testing",
    caution: str = "low",
    score: int = 12,
) -> dict[str, object]:
    return {
        "direction": direction,
        "timeframe": "M15",
        "horizon": 10,
        "target": f"{direction}_tp_2atr_sl_1atr_hit_first_10",
        "feature": feature,
        "feature_family": family,
        "tradability_role": "context_only",
        "normalized_or_raw": norm,
        "recommended_usage": usage,
        "caution_level": caution,
        "symbols_seen": 3,
        "stability_score": score,
        "notes": "",
    }


def write_shortlist(input_root: Path, direction: str, rows: list[dict[str, object]]) -> None:
    write_csv(
        shortlist_path(input_root, direction=direction, timeframe="M15", horizon=10),
        SHORTLIST_FIELDS,
        rows,
    )


def backtest_row(symbol: str, direction: str, feature: str, index: int = 1) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timeframe": "M15",
        "target_horizon": 10,
        "direction": direction,
        "cost_mode": "estimated",
        "return_mode": "net",
        "scenario_name": f"numeric_tercile:{feature}:high_tercile",
        "scenario_type": "numeric_tercile",
        "feature": feature,
        "bucket": "high_tercile",
        "sample_flag": "ok",
        "trades_count": 250 + index,
        "mean_return": 0.001 * index,
        "median_return": 0.0005 * index,
        "win_rate": 0.51,
        "cumulative_return": 0.10,
        "max_drawdown": -0.04,
        "profit_factor": 1.10 + index / 100,
        "monthly_positive_ratio": 0.60,
        "quarterly_positive_ratio": 0.65,
        "top_5_percent_trades_contribution_pct": 35.0,
        "avg_positive_return": 0.003,
        "avg_negative_return": -0.002,
        "payoff_ratio": 1.5,
        "breakeven_winrate": 0.4,
        "breakeven_winrate_margin": 0.11,
        "cost_config_source": "test",
        "point_size_source": "test",
        "spread_source_used": "spread",
        "symbols_using_default_costs": "",
    }


def fake_backtest_runner(calls: list[tuple[str, str]]):
    def runner(args: argparse.Namespace) -> None:
        calls.append((args.direction, args.symbol))
        ranking_rows = read_csv(args.ranking_path)
        rows = [
            {
                **backtest_row(args.symbol, args.direction, "all", 0),
                "scenario_name": "baseline:all:all",
                "scenario_type": "baseline",
                "bucket": "all",
            }
        ]
        for index, ranking_row in enumerate(ranking_rows, start=1):
            rows.append(backtest_row(args.symbol, args.direction, ranking_row["feature"], index))
        rows.append(
            {
                **backtest_row(args.symbol, args.direction, "day_of_week", 9),
                "scenario_name": "day_of_week:day_of_week:Monday",
                "scenario_type": "day_of_week",
                "bucket": "Monday",
            }
        )
        write_csv(Path(args.output_dir) / BACKTEST_SUMMARY_FILE, BACKTEST_FIELDS, rows)

    return runner


def args_for(
    tmp_path: Path,
    *,
    symbols: list[str] | None = None,
    directions: list[str] | None = None,
    run_id: str = "test_run",
    overwrite: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        symbols=symbols or ["EURUSD", "GBPUSD", "USDJPY"],
        timeframe="M15",
        horizon=10,
        directions=directions or ["long", "short"],
        input_root=tmp_path / "preferred_feature_hypotheses",
        output_root=tmp_path / "preferred_feature_backtests",
        cost_mode="estimated",
        return_mode="net",
        cost_config=None,
        strict_cost_config=False,
        max_features=None,
        overwrite=overwrite,
        gross_comparison_run_id=None,
        strict_shortlist_only=False,
        db_path=tmp_path / "test.db",
        run_id=run_id,
    )


def test_reads_long_short_shortlists_and_excludes_xauusd_by_default(tmp_path: Path) -> None:
    args = args_for(tmp_path)
    write_shortlist(
        args.input_root,
        "long",
        [
            shortlist_row("long", "return_5", score=20),
            shortlist_row("long", "spread_return", "spread/liquidity", score=15),
            shortlist_row(
                "long",
                "ma_fast",
                "trend/ma",
                norm="raw_scale_dependent",
                usage="prefer normalized variant",
                caution="high",
                score=30,
            ),
        ],
    )
    write_shortlist(
        args.input_root,
        "short",
        [
            shortlist_row("short", "return_1", score=18),
            shortlist_row("short", "spread_to_atr_20", "spread/liquidity", score=16),
        ],
    )
    calls: list[tuple[str, str]] = []

    outputs = run_preferred_feature_backtests(args, runner=fake_backtest_runner(calls))

    assert {symbol for _direction, symbol in calls} == {"EURUSD", "GBPUSD", "USDJPY"}
    assert "XAUUSD" not in {symbol for _direction, symbol in calls}

    long_rows = read_csv(outputs["long"]["preferred_feature_backtest_summary"])
    short_rows = read_csv(outputs["short"]["preferred_feature_backtest_summary"])

    assert {row["direction"] for row in long_rows} == {"long"}
    assert {row["direction"] for row in short_rows} == {"short"}
    return_row = next(row for row in long_rows if row["symbol"] == "EURUSD" and row["feature"] == "return_5")
    assert return_row["scenario"] == "numeric_tercile:return_5:high_tercile"
    assert return_row["condition_type"] == "numeric_tercile"
    assert return_row["bucket"] == "high_tercile"
    assert return_row["condition_value"] == "high_tercile"
    assert return_row["scenario_source"] == "preferred_shortlist_feature"
    assert return_row["is_preferred_shortlist_feature"] == "true"
    assert return_row["feature_in_shortlist"] == "true"
    assert return_row["baseline_trades_count"] == "250"
    assert return_row["baseline_mean_return"] == "0.0"
    assert return_row["baseline_median_return"] == "0.0"
    assert return_row["baseline_profit_factor"] == "1.1"
    assert return_row["baseline_win_rate"] == "0.51"
    assert return_row["baseline_max_drawdown"] == "-0.04"
    assert float(return_row["mean_return_vs_baseline"]) > 0
    assert float(return_row["profit_factor_vs_baseline"]) > 0
    assert float(return_row["win_rate_vs_baseline"]) == 0
    assert float(return_row["drawdown_vs_baseline"]) == 0
    context_row = next(row for row in long_rows if row["symbol"] == "EURUSD" and row["feature"] == "day_of_week")
    assert context_row["scenario_source"] == "standard_context_scenario"
    assert context_row["is_preferred_shortlist_feature"] == "false"
    assert context_row["feature_in_shortlist"] == "false"
    assert "ma_fast" not in {row["feature"] for row in long_rows}
    assert {"return_5", "spread_return"}.issubset({row["feature"] for row in long_rows})
    assert "ALL" in {row["symbol"] for row in long_rows}


def test_strict_shortlist_only_excludes_non_shortlist_scenarios(tmp_path: Path) -> None:
    args = args_for(tmp_path, symbols=["EURUSD"], directions=["long"])
    args.strict_shortlist_only = True
    write_shortlist(args.input_root, "long", [shortlist_row("long", "return_5", score=20)])

    outputs = run_preferred_feature_backtests(args, runner=fake_backtest_runner([]))
    rows = read_csv(outputs["long"]["preferred_feature_backtest_summary"])

    assert {row["feature"] for row in rows if row["symbol"] != "ALL"} == {"return_5"}


def test_respects_explicit_symbols_including_xauusd(tmp_path: Path) -> None:
    args = args_for(tmp_path, symbols=["EURUSD", "XAUUSD"], directions=["long"])
    write_shortlist(args.input_root, "long", [shortlist_row("long", "return_5", score=20)])
    calls: list[tuple[str, str]] = []

    outputs = run_preferred_feature_backtests(args, runner=fake_backtest_runner(calls))
    rows = read_csv(outputs["long"]["preferred_feature_backtest_summary"])

    assert {symbol for _direction, symbol in calls} == {"EURUSD", "XAUUSD"}
    assert {"EURUSD", "XAUUSD", "ALL"}.issubset({row["symbol"] for row in rows})


def test_reuses_existing_synthetic_backtest_csv_without_rerunning(tmp_path: Path) -> None:
    args = args_for(tmp_path, symbols=["EURUSD"], directions=["long"], run_id="existing_run")
    write_shortlist(args.input_root, "long", [shortlist_row("long", "return_5", score=20)])
    existing_output = symbol_output_dir(
        args.output_root,
        run_id=args.run_id,
        direction="long",
        symbol="EURUSD",
        timeframe="M15",
        horizon=10,
    )
    write_csv(existing_output / BACKTEST_SUMMARY_FILE, BACKTEST_FIELDS, [backtest_row("EURUSD", "long", "return_5")])

    def failing_runner(_args: argparse.Namespace) -> None:
        raise AssertionError("runner should not be called when an existing summary can be reused")

    outputs = run_preferred_feature_backtests(args, runner=failing_runner)
    detail_rows = read_csv(outputs["long"]["preferred_feature_backtest_detail"])

    assert detail_rows[0]["source_status"] == "reused_existing_backtest_research_summary"
    assert detail_rows[0]["feature"] == "return_5"


def test_zero_trade_rows_are_moved_to_skipped_features(tmp_path: Path) -> None:
    args = args_for(tmp_path, symbols=["EURUSD"], directions=["long"], run_id="zero_trade_run")
    write_shortlist(args.input_root, "long", [shortlist_row("long", "spread_return", "spread/liquidity", score=20)])
    existing_output = symbol_output_dir(
        args.output_root,
        run_id=args.run_id,
        direction="long",
        symbol="EURUSD",
        timeframe="M15",
        horizon=10,
    )
    write_csv(
        existing_output / BACKTEST_SUMMARY_FILE,
        BACKTEST_FIELDS,
        [
            {
                **backtest_row("EURUSD", "long", "all", 0),
                "scenario_name": "baseline:all:all",
                "scenario_type": "baseline",
                "bucket": "all",
            },
            {
                **backtest_row("EURUSD", "long", "spread_return", 1),
                "trades_count": 0,
                "mean_return": "",
                "median_return": "",
                "win_rate": "",
                "profit_factor": "",
                "scenario_name": "numeric_tercile:spread_return:low_tercile",
                "bucket": "low_tercile",
            },
        ],
    )

    outputs = run_preferred_feature_backtests(args, runner=lambda _args: None)
    summary_rows = read_csv(outputs["long"]["preferred_feature_backtest_summary"])
    skipped_rows = read_csv(outputs["long"]["skipped_features"])

    assert summary_rows == []
    assert skipped_rows[0]["feature"] == "spread_return"
    assert skipped_rows[0]["condition_type"] == "numeric_tercile"
    assert skipped_rows[0]["bucket"] == "low_tercile"
    assert skipped_rows[0]["skip_reason"] == "zero_trades_for_condition"


def test_report_language_boundaries(tmp_path: Path) -> None:
    args = args_for(tmp_path, symbols=["EURUSD"], directions=["long"])
    write_shortlist(args.input_root, "long", [shortlist_row("long", "return_5", score=20)])

    outputs = run_preferred_feature_backtests(args, runner=fake_backtest_runner([]))
    report_text = outputs["long"]["preferred_feature_backtest_report"].read_text(encoding="utf-8").lower()

    assert "research-only" in report_text
    assert "not trading signals" in report_text
    assert "best rows vs baseline" in report_text
    assert "rows less bad than baseline" in report_text
    assert "skipped / untestable features" in report_text
    assert "scenario source warning" in report_text
    assert "cost-aware interpretation" in report_text
    assert "exploratory" in report_text
    assert "buy" not in report_text
    assert "sell" not in report_text
    assert "live signal" not in report_text
