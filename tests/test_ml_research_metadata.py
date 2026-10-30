import csv
from datetime import datetime, timedelta
import math
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ml_research import (
    build_correlations,
    build_threshold_analysis,
    directional_returns_for_direction,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class DummyProbabilityModel:
    classes_ = [0, 1]

    def __init__(self, scores):
        self.scores = scores

    def predict_proba(self, x_test):
        np = pytest.importorskip("numpy")
        scores = np.array(self.scores[: len(x_test)])
        return np.column_stack([1 - scores, scores])


def create_ml_research_database(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE ml_dataset (
                symbol TEXT,
                timeframe TEXT,
                time_server TEXT,
                future_return_10 REAL,
                target_up_10 INTEGER,
                target_down_10 INTEGER,
                feature_alpha REAL,
                feature_beta REAL,
                feature_gamma INTEGER
            )
            """
        )
        start = datetime(2024, 1, 1, 0, 0, 0)
        rows = []
        for index in range(40):
            target_up = 1 if index % 4 in (0, 1) else 0
            target_down = 1 - target_up
            magnitude = 0.001 * (1 + (index % 5) / 10)
            future_return = magnitude if target_up else -magnitude
            rows.append(
                (
                    "EURUSD",
                    "M15",
                    (start + timedelta(minutes=15 * index)).isoformat(),
                    future_return,
                    target_up,
                    target_down,
                    index * 0.1,
                    (index % 7) * 0.2 + target_up,
                    index % 5,
                )
            )
        connection.executemany(
            """
            INSERT INTO ml_dataset (
                symbol, timeframe, time_server, future_return_10, target_up_10,
                target_down_10, feature_alpha, feature_beta, feature_gamma
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    finally:
        connection.close()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def metric_functions() -> dict[str, object]:
    metrics = pytest.importorskip("sklearn.metrics")
    return {
        "accuracy_score": metrics.accuracy_score,
        "average_precision_score": metrics.average_precision_score,
        "brier_score_loss": metrics.brier_score_loss,
        "precision_score": metrics.precision_score,
        "recall_score": metrics.recall_score,
        "f1_score": metrics.f1_score,
    }


def test_directional_returns_match_raw_for_long_and_flip_short() -> None:
    pd = pytest.importorskip("pandas")
    raw_returns = pd.Series([0.01, -0.02, 0.0])

    assert directional_returns_for_direction(raw_returns, "long").tolist() == [0.01, -0.02, 0.0]
    assert directional_returns_for_direction(raw_returns, "short").tolist() == [-0.01, 0.02, -0.0]


def test_threshold_analysis_reports_raw_and_directional_short_returns() -> None:
    pd = pytest.importorskip("pandas")
    x_test = pd.DataFrame({"feature_alpha": [1.0, 2.0, 3.0, 4.0]})
    y_test = pd.Series([0, 0, 1, 1])
    raw_returns = pd.Series([0.01, 0.02, -0.03, -0.01])
    directional_returns = directional_returns_for_direction(raw_returns, "short")

    analysis = build_threshold_analysis(
        pd,
        DummyProbabilityModel([0.10, 0.20, 0.60, 0.70]),
        x_test,
        y_test,
        raw_returns,
        directional_returns,
        metric_functions(),
    )

    threshold_row = analysis[analysis["threshold"] == 0.60].iloc[0]
    assert threshold_row["predicted_positive_count"] == 2
    assert math.isclose(threshold_row["mean_return_target_for_predicted_positive"], -0.02)
    assert math.isclose(threshold_row["median_return_target_for_predicted_positive"], -0.02)
    assert math.isclose(threshold_row["mean_raw_return_target_for_predicted_positive"], -0.02)
    assert math.isclose(threshold_row["median_raw_return_target_for_predicted_positive"], -0.02)
    assert math.isclose(threshold_row["mean_directional_return_target_for_predicted_positive"], 0.02)
    assert math.isclose(threshold_row["median_directional_return_target_for_predicted_positive"], 0.02)


def test_correlations_include_directional_return_columns_for_short() -> None:
    pd = pytest.importorskip("pandas")
    numeric_features = pd.DataFrame({"feature_alpha": [1.0, 2.0, 3.0, 4.0]})
    raw_returns = pd.Series([0.04, 0.02, -0.02, -0.04])
    directional_returns = directional_returns_for_direction(raw_returns, "short")

    correlations = build_correlations(pd, numeric_features, raw_returns, directional_returns)
    row = correlations.iloc[0]

    assert {
        "directional_pearson",
        "abs_directional_pearson",
        "directional_spearman",
        "abs_directional_spearman",
    }.issubset(correlations.columns)
    assert row["pearson"] < 0
    assert row["directional_pearson"] > 0


@pytest.mark.parametrize(
    ("direction", "expected_target"),
    [
        ("long", "target_up_10"),
        ("short", "target_down_10"),
    ],
)
def test_ml_research_writes_target_column_name_in_metadata(
    tmp_path: Path,
    direction: str,
    expected_target: str,
) -> None:
    db_path = tmp_path / "ml_research.db"
    output_dir = tmp_path / direction / "reports"
    create_ml_research_database(db_path)

    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "ml_research.py"),
        "--symbol",
        "EURUSD",
        "--timeframe",
        "M15",
        "--direction",
        direction,
        "--db-path",
        str(db_path),
        "--output-dir",
        str(output_dir),
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stdout + completed.stderr

    correlation_rows = read_csv_rows(output_dir / "correlations.csv")
    assert correlation_rows
    assert {row["target"] for row in correlation_rows} == {expected_target}
    assert all("dtype:" not in row["target"] for row in correlation_rows)
    assert {
        "directional_pearson",
        "abs_directional_pearson",
        "directional_spearman",
        "abs_directional_spearman",
    }.issubset(correlation_rows[0])

    metric_rows = read_csv_rows(output_dir / "model_metrics.csv")
    metrics = {row["metric"]: row["value"] for row in metric_rows}
    assert metrics["target"] == expected_target
    assert "dtype:" not in metrics["target"]

    threshold_rows = read_csv_rows(output_dir / "threshold_analysis.csv")
    assert [float(row["threshold"]) for row in threshold_rows] == [
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
    ]
    assert {
        "threshold",
        "predicted_positive_count",
        "predicted_positive_ratio",
        "precision",
        "recall",
        "f1",
        "accuracy",
        "base_positive_ratio",
        "lift_vs_base_precision",
        "mean_return_target_for_predicted_positive",
        "median_return_target_for_predicted_positive",
        "mean_raw_return_target_for_predicted_positive",
        "median_raw_return_target_for_predicted_positive",
        "mean_directional_return_target_for_predicted_positive",
        "median_directional_return_target_for_predicted_positive",
        "average_precision_score",
        "brier_score_loss",
    }.issubset(threshold_rows[0])
