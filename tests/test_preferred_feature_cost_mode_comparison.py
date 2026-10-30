import argparse
import csv
from pathlib import Path

from scripts.compare_preferred_feature_backtest_cost_modes import (
    FIELDNAMES,
    compare_cost_modes,
    summary_path,
)


SUMMARY_FIELDS = [
    "symbol",
    "timeframe",
    "horizon",
    "direction",
    "feature",
    "feature_family",
    "scenario",
    "scenario_condition_tested",
    "condition_type",
    "condition_value",
    "bucket",
    "scenario_source",
    "is_preferred_shortlist_feature",
    "feature_in_shortlist",
    "trades_count",
    "mean_return",
    "median_return",
    "win_rate",
    "profit_factor",
    "max_drawdown",
    "baseline_mean_return",
    "mean_return_vs_baseline",
    "profit_factor_vs_baseline",
    "win_rate_vs_baseline",
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


def compare_args(reports_root: Path, output_root: Path, gross_run_id: str, net_run_id: str) -> argparse.Namespace:
    return argparse.Namespace(
        reports_root=reports_root,
        output_root=output_root,
        gross_run_id=gross_run_id,
        net_run_id=net_run_id,
        directions=["long"],
    )


def summary_row(
    *,
    symbol: str,
    direction: str,
    feature: str,
    mean_return: float,
    profit_factor: float,
    win_rate: float = 0.52,
) -> dict[str, object]:
    scenario = f"numeric_tercile:{feature}:high_tercile"
    return {
        "symbol": symbol,
        "timeframe": "M15",
        "horizon": 10,
        "direction": direction,
        "feature": feature,
        "feature_family": "momentum/returns",
        "scenario": scenario,
        "scenario_condition_tested": scenario,
        "condition_type": "numeric_tercile",
        "condition_value": "high_tercile",
        "bucket": "high_tercile",
        "scenario_source": "preferred_shortlist_feature",
        "is_preferred_shortlist_feature": "true",
        "feature_in_shortlist": "true",
        "trades_count": 500,
        "mean_return": mean_return,
        "median_return": mean_return / 2,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": -0.04,
        "baseline_mean_return": -0.0005,
        "mean_return_vs_baseline": mean_return - (-0.0005),
        "profit_factor_vs_baseline": profit_factor - 0.9,
        "win_rate_vs_baseline": win_rate - 0.48,
    }


def test_cost_mode_comparison_detects_cost_erased_edge_and_writes_report(tmp_path: Path) -> None:
    reports_root = tmp_path / "preferred_feature_backtests"
    output_root = reports_root / "cost_mode_comparison"
    gross_run_id = "gross_run"
    net_run_id = "net_run"
    write_csv(
        summary_path(reports_root, gross_run_id, "long"),
        SUMMARY_FIELDS,
        [summary_row(symbol="EURUSD", direction="long", feature="return_5", mean_return=0.001, profit_factor=1.2)],
    )
    write_csv(
        summary_path(reports_root, net_run_id, "long"),
        SUMMARY_FIELDS,
        [summary_row(symbol="EURUSD", direction="long", feature="return_5", mean_return=-0.0002, profit_factor=0.8)],
    )

    outputs = compare_cost_modes(compare_args(reports_root, output_root, gross_run_id, net_run_id))
    rows = read_csv(outputs["long"]["cost_mode_comparison_csv"])
    report_text = outputs["long"]["cost_mode_comparison_report"].read_text(encoding="utf-8").lower()

    assert set(FIELDNAMES).issubset(rows[0].keys())
    assert rows[0]["cost_erased_edge"] == "true"
    assert rows[0]["gross_positive"] == "true"
    assert rows[0]["net_positive"] == "false"
    assert rows[0]["scenario_source"] == "preferred_shortlist_feature"
    assert rows[0]["is_preferred_shortlist_feature"] == "true"
    assert rows[0]["feature_in_shortlist"] == "true"
    assert rows[0]["less_bad_than_baseline_net"] == "true"
    assert "research-only" in report_text
    assert "gross edge candidates" in report_text
    assert "cost-erased candidates" in report_text
    assert "net survivors" in report_text
    assert "source tag diagnostics" in report_text
    assert "scenario_source counts" in report_text
    assert "feature_in_shortlist counts" in report_text
    assert "is_preferred_shortlist_feature counts" in report_text
    assert "gross_positive count by scenario_source" in report_text
    assert "gross_positive + preferred_shortlist_feature count" in report_text
    assert "buy" not in report_text
    assert "sell" not in report_text
    assert "live signal" not in report_text


def test_cost_mode_comparison_skips_zero_trade_rows_and_populates_legacy_flags(tmp_path: Path) -> None:
    reports_root = tmp_path / "preferred_feature_backtests"
    output_root = reports_root / "cost_mode_comparison"
    gross_run_id = "gross_run"
    net_run_id = "net_run"
    zero_gross = {
        **summary_row(symbol="EURUSD", direction="long", feature="spread_return", mean_return=0.001, profit_factor=1.2),
        "trades_count": 0,
    }
    zero_net = {
        **summary_row(symbol="EURUSD", direction="long", feature="spread_return", mean_return=-0.0002, profit_factor=0.8),
        "trades_count": 0,
    }
    legacy_gross = {
        **summary_row(symbol="EURUSD", direction="long", feature="return_5", mean_return=0.001, profit_factor=1.2),
        "scenario_source": "",
        "is_preferred_shortlist_feature": "",
        "feature_in_shortlist": "",
    }
    legacy_net = {
        **summary_row(symbol="EURUSD", direction="long", feature="return_5", mean_return=-0.0002, profit_factor=0.8),
        "scenario_source": "",
        "is_preferred_shortlist_feature": "",
        "feature_in_shortlist": "",
    }
    write_csv(summary_path(reports_root, gross_run_id, "long"), SUMMARY_FIELDS, [zero_gross, legacy_gross])
    write_csv(summary_path(reports_root, net_run_id, "long"), SUMMARY_FIELDS, [zero_net, legacy_net])

    outputs = compare_cost_modes(compare_args(reports_root, output_root, gross_run_id, net_run_id))
    rows = read_csv(outputs["long"]["cost_mode_comparison_csv"])

    assert {row["feature"] for row in rows} == {"return_5"}
    assert rows[0]["scenario_source"] == "unknown"
    assert rows[0]["is_preferred_shortlist_feature"] == "false"
    assert rows[0]["feature_in_shortlist"] == "false"


def test_cost_mode_comparison_uses_preferred_tag_when_only_one_side_has_it(tmp_path: Path) -> None:
    reports_root = tmp_path / "preferred_feature_backtests"
    output_root = reports_root / "cost_mode_comparison"
    gross_run_id = "gross_run"
    net_run_id = "net_run"
    gross_row = {
        **summary_row(symbol="EURUSD", direction="long", feature="return_5", mean_return=0.001, profit_factor=1.2),
        "scenario_source": "unknown",
        "is_preferred_shortlist_feature": "false",
        "feature_in_shortlist": "false",
    }
    net_row = summary_row(symbol="EURUSD", direction="long", feature="return_5", mean_return=-0.0002, profit_factor=0.8)
    write_csv(summary_path(reports_root, gross_run_id, "long"), SUMMARY_FIELDS, [gross_row])
    write_csv(summary_path(reports_root, net_run_id, "long"), SUMMARY_FIELDS, [net_row])

    outputs = compare_cost_modes(compare_args(reports_root, output_root, gross_run_id, net_run_id))
    rows = read_csv(outputs["long"]["cost_mode_comparison_csv"])

    assert rows[0]["scenario_source"] == "preferred_shortlist_feature"
    assert rows[0]["is_preferred_shortlist_feature"] == "true"
    assert rows[0]["feature_in_shortlist"] == "true"
    assert "source tag resolved" in rows[0]["notes"]


def test_cost_mode_comparison_reports_missing_metadata_columns(tmp_path: Path) -> None:
    reports_root = tmp_path / "preferred_feature_backtests"
    output_root = reports_root / "cost_mode_comparison"
    gross_run_id = "gross_run"
    net_run_id = "net_run"
    legacy_fields = [
        field
        for field in SUMMARY_FIELDS
        if field not in {"scenario_source", "is_preferred_shortlist_feature", "feature_in_shortlist"}
    ]
    gross_row = summary_row(symbol="EURUSD", direction="long", feature="return_5", mean_return=0.001, profit_factor=1.2)
    net_row = summary_row(symbol="EURUSD", direction="long", feature="return_5", mean_return=-0.0002, profit_factor=0.8)
    write_csv(summary_path(reports_root, gross_run_id, "long"), legacy_fields, [gross_row])
    write_csv(summary_path(reports_root, net_run_id, "long"), legacy_fields, [net_row])

    outputs = compare_cost_modes(compare_args(reports_root, output_root, gross_run_id, net_run_id))
    rows = read_csv(outputs["long"]["cost_mode_comparison_csv"])
    report_text = outputs["long"]["cost_mode_comparison_report"].read_text(encoding="utf-8").lower()

    assert rows[0]["scenario_source"] == "unknown"
    assert rows[0]["is_preferred_shortlist_feature"] == "false"
    assert rows[0]["feature_in_shortlist"] == "false"
    assert "metadata warnings" in report_text
    assert "missing `scenario_source`" in report_text
