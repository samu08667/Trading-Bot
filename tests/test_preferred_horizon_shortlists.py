import argparse
import csv
from pathlib import Path
import re

from scripts.build_preferred_horizon_shortlists import build_preferred_horizon_shortlists
from scripts.build_preferred_target_feature_stability import preferred_target


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def fake_target_runner(calls: list[argparse.Namespace]):
    def _runner(args: argparse.Namespace) -> dict[str, Path]:
        calls.append(args)
        reports_root = Path(args.reports_root)
        symbol = args.symbol
        direction = args.direction
        timeframe = args.timeframe
        horizon = args.horizon
        target = args.targets[0]
        report_dir = reports_root / "target_runs" / direction / f"{symbol}_{timeframe}_h{horizon}" / target
        ranking_rows = [
            {"feature": "return_5", "score": 0.90},
            {"feature": "ma_diff_atr_20", "score": 0.80},
            {"feature": target, "score": 0.70},
        ]
        write_csv(
            report_dir / "correlations.csv",
            ["feature", "abs_directional_spearman", "abs_spearman"],
            [
                {
                    "feature": row["feature"],
                    "abs_directional_spearman": row["score"],
                    "abs_spearman": row["score"],
                }
                for row in ranking_rows
            ],
        )
        write_csv(
            report_dir / "mutual_information.csv",
            ["feature", "mutual_information"],
            [{"feature": row["feature"], "mutual_information": row["score"]} for row in ranking_rows],
        )
        write_csv(
            report_dir / "random_forest_importance.csv",
            ["feature", "importance"],
            [{"feature": row["feature"], "importance": row["score"]} for row in ranking_rows],
        )
        write_csv(
            report_dir / "permutation_importance.csv",
            ["feature", "importance_mean"],
            [{"feature": row["feature"], "importance_mean": row["score"]} for row in ranking_rows],
        )
        write_csv(report_dir / "model_metrics.csv", ["metric", "value"], [{"metric": "target", "value": target}])
        write_csv(
            report_dir / "threshold_analysis.csv",
            ["threshold", "precision", "predicted_positive_count"],
            [{"threshold": 0.5, "precision": 0.5, "predicted_positive_count": 1000}],
        )
        write_csv(report_dir / "feature_summary.csv", ["feature"], [{"feature": "return_5"}])

        comparison_dir = reports_root / "target_comparison" / direction / f"{symbol}_{timeframe}_h{horizon}"
        comparison_csv = comparison_dir / "target_comparison.csv"
        comparison_report = comparison_dir / "target_comparison_report.md"
        write_csv(comparison_csv, ["symbol", "target"], [{"symbol": symbol, "target": target}])
        comparison_report.write_text("research-only target comparison\n", encoding="utf-8")
        return {"target_comparison_csv": comparison_csv, "target_comparison_report": comparison_report}

    return _runner


def base_args(tmp_path: Path, *, horizons: list[int]) -> argparse.Namespace:
    return argparse.Namespace(
        timeframe="M15",
        horizons=horizons,
        directions=["long", "short"],
        target_family="preferred_2atr_1atr_hit_first",
        target_run_symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
        stability_symbols=["EURUSD", "GBPUSD", "USDJPY"],
        db_path=tmp_path / "data" / "test.db",
        reports_root=tmp_path / "ml_research",
        stability_output_root=tmp_path / "preferred_target_feature_stability",
        shortlist_output_root=tmp_path / "preferred_feature_hypotheses",
        output_root=tmp_path / "builds",
        run_id="unit_run",
        top_n=30,
        min_symbols=3,
        min_stability_score=12,
        min_predicted_positive_count=500,
        purge_overlap=False,
        embargo_bars=0,
        non_overlap_eval=False,
        skip_ml_research=False,
        overwrite=False,
    )


def test_h5_and_h20_preferred_shortlists_can_be_generated(tmp_path: Path) -> None:
    calls: list[argparse.Namespace] = []

    outputs = build_preferred_horizon_shortlists(
        base_args(tmp_path, horizons=[5, 20]),
        target_runner=fake_target_runner(calls),
    )

    assert outputs["manifest"].exists()
    assert outputs["report"].exists()
    assert len(calls) == 16
    for horizon in (5, 20):
        for direction in ("long", "short"):
            path = (
                tmp_path
                / "preferred_feature_hypotheses"
                / "preferred_2atr_1atr_hit_first"
                / direction
                / f"M15_h{horizon}"
                / "preferred_feature_hypotheses.csv"
            )
            rows = read_csv(path)
            assert {row["feature"] for row in rows} == {"ma_diff_atr_20", "return_5"}
            assert all("hit_first" not in row["feature"] for row in rows)


def test_h10_target_naming_remains_unchanged(tmp_path: Path) -> None:
    calls: list[argparse.Namespace] = []

    build_preferred_horizon_shortlists(
        base_args(tmp_path, horizons=[10]),
        target_runner=fake_target_runner(calls),
    )

    assert preferred_target("long", 10) == "long_tp_2atr_sl_1atr_hit_first_10"
    assert preferred_target("short", 10) == "short_tp_2atr_sl_1atr_hit_first_10"
    assert {call.horizon for call in calls} == {10}


def test_one_and_half_atr_target_family_builds_safe_target_shortlists(tmp_path: Path) -> None:
    run_args = base_args(tmp_path, horizons=[10])
    run_args.target_family = "preferred_1_5atr_1atr_hit_first"
    calls: list[argparse.Namespace] = []

    outputs = build_preferred_horizon_shortlists(
        run_args,
        target_runner=fake_target_runner(calls),
    )

    rows = read_csv(outputs["manifest"])
    assert {call.targets[0] for call in calls} == {
        "long_tp_1_5atr_sl_1atr_hit_first_10",
        "short_tp_1_5atr_sl_1atr_hit_first_10",
    }
    assert {row["target_family"] for row in rows} == {"preferred_1_5atr_1atr_hit_first"}
    assert all("preferred_1_5atr_1atr_hit_first" in row["preferred_feature_hypotheses_csv"] for row in rows if row["row_type"] == "shortlist")
    assert preferred_target("long", 10, "preferred_1_5atr_1atr_hit_first") == (
        "long_tp_1_5atr_sl_1atr_hit_first_10"
    )
    for direction in ("long", "short"):
        shortlist = read_csv(
            tmp_path
            / "preferred_feature_hypotheses"
            / "preferred_1_5atr_1atr_hit_first"
            / direction
            / "M15_h10"
            / "preferred_feature_hypotheses.csv"
        )
        assert {row["feature"] for row in shortlist} == {"ma_diff_atr_20", "return_5"}
        assert all("hit_first" not in row["feature"] for row in shortlist)


def test_report_contains_research_warning_and_no_blocked_language(tmp_path: Path) -> None:
    outputs = build_preferred_horizon_shortlists(
        base_args(tmp_path, horizons=[5]),
        target_runner=fake_target_runner([]),
    )

    text = outputs["report"].read_text(encoding="utf-8").lower()
    assert "research-only warning" in text
    assert "buy" not in text
    assert "sell" not in text
    assert "live signal" not in text


def test_no_metatrader_or_live_execution_imports_are_introduced() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [
        root / "scripts" / "build_preferred_horizon_shortlists.py",
        root / "scripts" / "build_preferred_feature_hypothesis_shortlist.py",
        root / "scripts" / "build_preferred_target_feature_stability.py",
    ]
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

    for path in paths:
        assert blocked.findall(path.read_text(encoding="utf-8")) == []
