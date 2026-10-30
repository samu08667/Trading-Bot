import csv
import math
from pathlib import Path

import pytest

from scripts.compare_ml_target_reports import (
    build_comparison_rows,
    comparison_row_for_target,
    default_target_candidates,
    read_csv_rows,
    read_model_metrics,
    target_run_dir,
    write_comparison_outputs,
)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_model_metrics(path: Path, target: str = "target_up_10") -> None:
    metrics = {
        "target": target,
        "direction": "long",
        "symbol": "EURUSD",
        "timeframe": "M15",
        "horizon": "10",
        "rows_total": "1000",
        "rows_train": "700",
        "rows_test": "300",
        "features_used": "12",
        "train_positive_ratio": "0.24",
        "test_positive_ratio": "0.25",
        "accuracy": "0.73",
        "precision": "0.38",
        "recall": "0.20",
        "f1": "0.26",
        "roc_auc": "0.61",
        "purge_overlap": "true",
        "embargo_bars": "2",
        "non_overlap_eval": "false",
    }
    write_csv(
        path,
        ["metric", "value"],
        [{"metric": key, "value": value} for key, value in metrics.items()],
    )


def threshold_rows() -> list[dict[str, object]]:
    return [
        {
            "threshold": "0.20",
            "predicted_positive_count": "100",
            "precision": "0.30",
            "recall": "0.70",
            "f1": "0.42",
            "base_positive_ratio": "0.25",
            "lift_vs_base_precision": "1.20",
            "mean_directional_return_target_for_predicted_positive": "0.001",
            "median_directional_return_target_for_predicted_positive": "0.0005",
            "average_precision_score": "0.35",
            "brier_score_loss": "0.19",
        },
        {
            "threshold": "0.40",
            "predicted_positive_count": "600",
            "precision": "0.40",
            "recall": "0.55",
            "f1": "0.46",
            "base_positive_ratio": "0.25",
            "lift_vs_base_precision": "1.60",
            "mean_directional_return_target_for_predicted_positive": "0.002",
            "median_directional_return_target_for_predicted_positive": "0.001",
            "average_precision_score": "0.35",
            "brier_score_loss": "0.19",
        },
        {
            "threshold": "0.60",
            "predicted_positive_count": "550",
            "precision": "0.35",
            "recall": "0.30",
            "f1": "0.32",
            "base_positive_ratio": "0.25",
            "lift_vs_base_precision": "1.40",
            "mean_directional_return_target_for_predicted_positive": "0.004",
            "median_directional_return_target_for_predicted_positive": "0.002",
            "average_precision_score": "0.35",
            "brier_score_loss": "0.19",
        },
    ]


def write_threshold_analysis(path: Path, rows: list[dict[str, object]] | None = None) -> None:
    rows = rows if rows is not None else threshold_rows()
    write_csv(path, list(rows[0].keys()), rows)


def write_target_reports(reports_root: Path, target: str, threshold_data: list[dict[str, object]] | None = None) -> Path:
    report_dir = target_run_dir(
        reports_root,
        direction="long",
        symbol="EURUSD",
        timeframe="M15",
        horizon=10,
        target=target,
    )
    write_model_metrics(report_dir / "model_metrics.csv", target)
    write_threshold_analysis(report_dir / "threshold_analysis.csv", threshold_data)
    return report_dir


def test_default_target_list_for_long_and_short_h10() -> None:
    assert default_target_candidates("long", 10) == [
        "target_up_10",
        "target_long_good_10",
        "long_tp_1atr_sl_1atr_hit_first_10",
        "long_tp_1_5atr_sl_1atr_hit_first_10",
        "long_tp_2atr_sl_1atr_hit_first_10",
    ]
    assert default_target_candidates("short", 10) == [
        "target_down_10",
        "target_short_good_10",
        "short_tp_1atr_sl_1atr_hit_first_10",
        "short_tp_1_5atr_sl_1atr_hit_first_10",
        "short_tp_2atr_sl_1atr_hit_first_10",
    ]


def test_reads_model_metrics_and_threshold_analysis(tmp_path: Path) -> None:
    report_dir = write_target_reports(tmp_path, "target_up_10")

    metrics = read_model_metrics(report_dir / "model_metrics.csv")
    threshold_data = read_csv_rows(report_dir / "threshold_analysis.csv")

    assert metrics["target"] == "target_up_10"
    assert metrics["rows_test"] == "300"
    assert threshold_data[0]["average_precision_score"] == "0.35"


def test_comparison_summarizes_thresholds_and_average_precision_lift(tmp_path: Path) -> None:
    report_dir = write_target_reports(tmp_path, "target_up_10")

    row = comparison_row_for_target(
        symbol="EURUSD",
        timeframe="M15",
        direction="long",
        horizon=10,
        target="target_up_10",
        report_dir=report_dir,
        min_predicted_positive_count=500,
    )

    assert math.isclose(float(row["average_precision_lift_vs_base"]), 1.4)
    assert row["best_f1_threshold"] == "0.40"
    assert row["best_lift_threshold"] == "0.40"
    assert row["best_lift_predicted_positive_count"] == "600"
    assert row["best_directional_return_threshold"] == "0.60"
    assert row["best_directional_return_mean"] == "0.004"
    assert row["recommended_research_threshold"] == "0.40"
    assert row["recommended_lift_vs_base_precision"] == "1.60"
    assert row["low_sample_threshold"] == "false"
    assert row["no_threshold_passed"] == "false"


def test_low_sample_threshold_when_no_threshold_has_enough_predictions(tmp_path: Path) -> None:
    low_count_rows = [
        {**row, "predicted_positive_count": "25"}
        for row in threshold_rows()
    ]
    report_dir = write_target_reports(tmp_path, "target_up_10", low_count_rows)

    row = comparison_row_for_target(
        symbol="EURUSD",
        timeframe="M15",
        direction="long",
        horizon=10,
        target="target_up_10",
        report_dir=report_dir,
        min_predicted_positive_count=500,
    )

    assert row["low_sample_threshold"] == "true"
    assert row["best_lift_threshold"] == ""
    assert row["best_directional_return_threshold"] == ""


def test_no_threshold_passed_when_conservative_criteria_fail(tmp_path: Path) -> None:
    weak_rows = [
        {
            **row,
            "predicted_positive_count": "600",
            "lift_vs_base_precision": "1.10",
            "mean_directional_return_target_for_predicted_positive": "-0.001",
            "median_directional_return_target_for_predicted_positive": "-0.001",
        }
        for row in threshold_rows()
    ]
    report_dir = write_target_reports(tmp_path, "target_up_10", weak_rows)

    row = comparison_row_for_target(
        symbol="EURUSD",
        timeframe="M15",
        direction="long",
        horizon=10,
        target="target_up_10",
        report_dir=report_dir,
        min_predicted_positive_count=500,
    )

    assert row["low_sample_threshold"] == "false"
    assert row["no_threshold_passed"] == "true"
    assert row["recommended_research_threshold"] == ""


def test_missing_report_handling(tmp_path: Path) -> None:
    rows = build_comparison_rows(
        reports_root=tmp_path,
        symbol="EURUSD",
        timeframe="M15",
        direction="long",
        horizon=10,
        targets=["target_up_10"],
        min_predicted_positive_count=500,
    )

    assert rows[0]["missing_reports"] == "true"
    assert "model_metrics.csv" in rows[0]["notes"]
    assert "threshold_analysis.csv" in rows[0]["notes"]


def test_missing_directional_columns_fails_clearly(tmp_path: Path) -> None:
    rows_without_directional = [
        {
            key: value
            for key, value in row.items()
            if key
            not in {
                "mean_directional_return_target_for_predicted_positive",
                "median_directional_return_target_for_predicted_positive",
            }
        }
        for row in threshold_rows()
    ]
    report_dir = write_target_reports(tmp_path, "target_up_10", rows_without_directional)

    with pytest.raises(ValueError, match="Rerun scripts/ml_research.py"):
        comparison_row_for_target(
            symbol="EURUSD",
            timeframe="M15",
            direction="long",
            horizon=10,
            target="target_up_10",
            report_dir=report_dir,
            min_predicted_positive_count=500,
        )


def test_report_file_writing_and_language_boundaries(tmp_path: Path) -> None:
    rows = [
        comparison_row_for_target(
            symbol="EURUSD",
            timeframe="M15",
            direction="long",
            horizon=10,
            target="target_up_10",
            report_dir=write_target_reports(tmp_path, "target_up_10"),
            min_predicted_positive_count=500,
        )
    ]
    paths = write_comparison_outputs(tmp_path / "comparison", rows, ["target_up_10"], 500)

    assert paths["target_comparison_csv"].exists()
    assert paths["target_comparison_report"].exists()
    report_text = paths["target_comparison_report"].read_text(encoding="utf-8").lower()
    assert "research-only" in report_text
    assert "not trading signals" in report_text
    assert "buy" not in report_text
    assert "sell" not in report_text
    assert "live signal" not in report_text
