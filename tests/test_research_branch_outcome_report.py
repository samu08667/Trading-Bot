import argparse
import csv
import re
from pathlib import Path

import pytest

from scripts.build_research_branch_outcome_report import run_branch_outcome_report


SUMMARY_FIELDNAMES = [
    "symbol",
    "direction",
    "source_combination_id",
    "source_feature_1",
    "source_scenario_1",
    "source_feature_family_1",
    "source_feature_2",
    "source_scenario_2",
    "source_feature_family_2",
    "trades_count",
    "tp_hit_rate",
    "sl_hit_rate",
    "timeout_rate",
    "mean_R",
    "profit_factor_R",
    "expectancy_R",
    "max_drawdown_R",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "top_5_percent_trades_contribution_pct",
    "baseline_mean_R",
    "baseline_profit_factor_R",
    "mean_R_vs_baseline",
    "profit_factor_R_vs_baseline",
    "classification",
]


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summary_row(
    *,
    symbol: str,
    direction: str,
    combo: str,
    mean_r: float,
    profit_factor: float,
    mean_delta: float,
    profit_delta: float,
    concentration: float = 17.0,
    classification: str = "SCARTARE",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "direction": direction,
        "source_combination_id": combo,
        "source_feature_1": "ma_diff_atr_20",
        "source_scenario_1": "numeric_tercile:ma_diff_atr_20:mid_tercile",
        "source_feature_family_1": "trend/ma",
        "source_feature_2": "volume_vs_session_avg",
        "source_scenario_2": "numeric_tercile:volume_vs_session_avg:mid_tercile",
        "source_feature_family_2": "volume/liquidity",
        "trades_count": 1000,
        "tp_hit_rate": 0.24,
        "sl_hit_rate": 0.54,
        "timeout_rate": 0.22,
        "mean_R": mean_r,
        "profit_factor_R": profit_factor,
        "expectancy_R": mean_r,
        "max_drawdown_R": -120.0,
        "monthly_positive_ratio": 0.25,
        "quarterly_positive_ratio": 0.20,
        "top_5_percent_trades_contribution_pct": concentration,
        "baseline_mean_R": -0.16,
        "baseline_profit_factor_R": 0.75,
        "mean_R_vs_baseline": mean_delta,
        "profit_factor_R_vs_baseline": profit_delta,
        "classification": classification,
    }


def write_tp_sl_outputs(root: Path, run_id: str, direction: str, rows: list[dict[str, object]]) -> None:
    base = root / run_id / direction
    write_csv(base / "tp_sl_path_backtest_summary.csv", rows, SUMMARY_FIELDNAMES)
    write_csv(
        base / "tp_sl_path_backtest_detail.csv",
        [{"symbol": row["symbol"], "direction": direction, "source_combination_id": row["source_combination_id"]} for row in rows],
        ["symbol", "direction", "source_combination_id"],
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        branch_id="M15_h10_preferred_2atr_1atr",
        branch_title="M15 h10 preferred 2ATR/1ATR branch",
        symbols=["EURUSD", "GBPUSD", "USDJPY"],
        directions=["long", "short"],
        timeframe="M15",
        horizon=10,
        target_family="preferred_2atr_1atr_hit_first",
        cost_mode="estimated",
        return_mode="net",
        long_tp_sl_run_id="long_run",
        short_tp_sl_run_id="short_run",
        decision="CLOSED_NO_SURVIVOR",
        tp_sl_root=tmp_path / "tp_sl",
        output_root=tmp_path / "branch_outcomes",
        run_id="branch_unit_run",
        overwrite=False,
    )


def prepare_inputs(tmp_path: Path) -> argparse.Namespace:
    run_args = args(tmp_path)
    write_tp_sl_outputs(
        run_args.tp_sl_root,
        "long_run",
        "long",
        [
            summary_row(
                symbol="USDJPY",
                direction="long",
                combo="long_combo_1",
                mean_r=-0.09,
                profit_factor=0.85,
                mean_delta=0.07,
                profit_delta=0.09,
            ),
            summary_row(
                symbol="GBPUSD",
                direction="long",
                combo="long_combo_2",
                mean_r=-0.12,
                profit_factor=0.80,
                mean_delta=-0.01,
                profit_delta=-0.02,
                concentration=55.0,
            ),
        ],
    )
    write_tp_sl_outputs(
        run_args.tp_sl_root,
        "short_run",
        "short",
        [
            summary_row(
                symbol="USDJPY",
                direction="short",
                combo="short_combo_1",
                mean_r=-0.07,
                profit_factor=0.88,
                mean_delta=0.08,
                profit_delta=0.12,
            )
        ],
    )
    return run_args


def test_branch_outcome_reads_long_short_and_writes_outputs(tmp_path: Path) -> None:
    run_args = prepare_inputs(tmp_path)

    outputs = run_branch_outcome_report(run_args)

    assert outputs["branch_outcome_report"].exists()
    assert outputs["branch_outcome_summary"].exists()
    assert outputs["rejected_combinations"].exists()

    summary_rows = read_csv_rows(outputs["branch_outcome_summary"])
    rejected_rows = read_csv_rows(outputs["rejected_combinations"])

    assert summary_rows[0]["decision"] == "CLOSED_NO_SURVIVOR"
    assert summary_rows[0]["long_tested_count"] == "2"
    assert summary_rows[0]["long_SCARTARE_count"] == "2"
    assert summary_rows[0]["short_tested_count"] == "1"
    assert summary_rows[0]["short_SCARTARE_count"] == "1"
    assert len(rejected_rows) == 3


def test_branch_outcome_generates_rejection_reasons(tmp_path: Path) -> None:
    run_args = prepare_inputs(tmp_path)

    outputs = run_branch_outcome_report(run_args)
    rejected_rows = read_csv_rows(outputs["rejected_combinations"])
    reasons = {row["source_combination_id"]: row["rejection_reason"] for row in rejected_rows}

    assert reasons["long_combo_1"] == "mean_R <= 0; profit_factor_R <= 1"
    assert "baseline_not_beaten" in reasons["long_combo_2"]
    assert "concentration_warning" in reasons["long_combo_2"]


def test_missing_input_files_fail_clearly(tmp_path: Path) -> None:
    run_args = args(tmp_path)

    with pytest.raises(FileNotFoundError, match="Required TP/SL path summary"):
        run_branch_outcome_report(run_args)


def test_report_contains_required_closure_language(tmp_path: Path) -> None:
    run_args = prepare_inputs(tmp_path)

    outputs = run_branch_outcome_report(run_args)
    report_text = outputs["branch_outcome_report"].read_text(encoding="utf-8")

    assert "## Research-only warning" in report_text
    assert "CLOSED_NO_SURVIVOR" in report_text
    assert "No TP/SL optimization." in report_text
    assert "No new features." in report_text
    assert "No new combinations searched." in report_text


def test_report_avoids_blocked_recommendation_language(tmp_path: Path) -> None:
    run_args = prepare_inputs(tmp_path)

    outputs = run_branch_outcome_report(run_args)
    report_text = outputs["branch_outcome_report"].read_text(encoding="utf-8").lower()

    assert "buy" not in report_text
    assert "sell" not in report_text
    assert "live signal" not in report_text


def test_script_does_not_import_metatrader5_or_live_api_terms() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_research_branch_outcome_report.py"
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
