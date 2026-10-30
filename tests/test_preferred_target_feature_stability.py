import argparse
import csv
from pathlib import Path

from scripts.build_preferred_target_feature_stability import (
    build_direction_feature_stability,
    build_preferred_target_feature_stability,
    feature_family,
    preferred_target,
    target_report_dir,
)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def write_ml_feature_reports(
    reports_root: Path,
    *,
    direction: str,
    symbol: str,
    features: dict[str, list[tuple[str, float]]],
) -> Path:
    target = preferred_target(direction, 10)
    report_dir = target_report_dir(
        reports_root,
        direction=direction,
        symbol=symbol,
        timeframe="M15",
        horizon=10,
        target=target,
    )
    write_csv(
        report_dir / "correlations.csv",
        ["feature", "abs_directional_spearman", "abs_spearman"],
        [
            {
                "feature": feature,
                "abs_directional_spearman": value,
                "abs_spearman": value / 2,
            }
            for feature, value in features["correlation"]
        ],
    )
    write_csv(
        report_dir / "mutual_information.csv",
        ["feature", "mutual_information"],
        [
            {"feature": feature, "mutual_information": value}
            for feature, value in features["mutual_info"]
        ],
    )
    write_csv(
        report_dir / "random_forest_importance.csv",
        ["feature", "importance"],
        [
            {"feature": feature, "importance": value}
            for feature, value in features["random_forest"]
        ],
    )
    write_csv(
        report_dir / "permutation_importance.csv",
        ["feature", "importance_mean"],
        [
            {"feature": feature, "importance_mean": value}
            for feature, value in features["permutation"]
        ],
    )
    return report_dir


def base_features() -> dict[str, list[tuple[str, float]]]:
    return {
        "correlation": [
            ("atr_20", 0.50),
            ("tick_volume_ratio_20", 0.40),
            ("feature_alpha", 0.10),
        ],
        "mutual_info": [
            ("atr_20", 0.30),
            ("ma_diff_atr_20", 0.20),
            ("feature_alpha", 0.05),
        ],
        "random_forest": [
            ("spread_to_atr_20", 0.25),
            ("atr_20", 0.20),
            ("feature_alpha", 0.01),
        ],
        "permutation": [
            ("atr_20", 0.08),
            ("hour", 0.04),
            ("feature_alpha", 0.01),
        ],
    }


def test_reads_target_runs_structure_and_computes_topn_recurrence(tmp_path: Path) -> None:
    reports_root = tmp_path / "target_runs"
    output_root = tmp_path / "stability"
    write_ml_feature_reports(reports_root, direction="long", symbol="EURUSD", features=base_features())
    gbpusd_features = base_features()
    gbpusd_features["mutual_info"] = [
        ("atr_20", 0.35),
        ("spread_to_atr_20", 0.25),
        ("feature_alpha", 0.01),
    ]
    gbpusd_features["permutation"] = [
        ("spread_to_atr_20", 0.09),
        ("atr_20", 0.08),
        ("feature_alpha", 0.01),
    ]
    write_ml_feature_reports(reports_root, direction="long", symbol="GBPUSD", features=gbpusd_features)

    paths = build_direction_feature_stability(
        reports_root=reports_root,
        output_root=output_root,
        symbols=["EURUSD", "GBPUSD", "USDJPY"],
        timeframe="M15",
        horizon=10,
        direction="long",
        top_n=2,
    )
    rows = read_csv(paths["feature_stability_csv"])
    atr_row = next(row for row in rows if row["feature"] == "atr_20")

    assert atr_row["target"] == "long_tp_2atr_sl_1atr_hit_first_10"
    assert atr_row["symbols_seen"] == "2"
    assert atr_row["correlation_topn_count"] == "2"
    assert atr_row["mutual_info_topn_count"] == "2"
    assert atr_row["random_forest_topn_count"] == "2"
    assert atr_row["permutation_topn_count"] == "2"
    assert atr_row["stability_score"] == "10"
    assert atr_row["feature_family"] == "volatility/range"

    report_text = paths["feature_stability_report"].read_text(encoding="utf-8")
    assert "USDJPY_M15_h10" in report_text
    assert "research-only" in report_text


def test_build_outputs_separate_long_and_short(tmp_path: Path) -> None:
    reports_root = tmp_path / "target_runs"
    output_root = tmp_path / "stability"
    write_ml_feature_reports(reports_root, direction="long", symbol="EURUSD", features=base_features())
    short_features = base_features()
    short_features["correlation"] = [
        ("ma_diff_atr_20", 0.60),
        ("atr_20", 0.20),
    ]
    write_ml_feature_reports(reports_root, direction="short", symbol="EURUSD", features=short_features)

    outputs = build_preferred_target_feature_stability(
        argparse.Namespace(
            reports_root=reports_root,
            output_root=output_root,
            symbols=["EURUSD"],
            timeframe="M15",
            horizon=10,
            directions=["long", "short"],
            top_n=2,
        )
    )

    assert outputs["long"]["feature_stability_csv"].exists()
    assert outputs["short"]["feature_stability_csv"].exists()
    long_rows = read_csv(outputs["long"]["feature_stability_csv"])
    short_rows = read_csv(outputs["short"]["feature_stability_csv"])
    assert {row["direction"] for row in long_rows} == {"long"}
    assert {row["direction"] for row in short_rows} == {"short"}
    assert {row["target"] for row in short_rows} == {"short_tp_2atr_sl_1atr_hit_first_10"}


def test_feature_stability_excludes_future_target_columns(tmp_path: Path) -> None:
    reports_root = tmp_path / "target_runs"
    output_root = tmp_path / "stability"
    features = base_features()
    features["correlation"] = [
        ("long_tp_2atr_sl_1atr_hit_first_5", 0.99),
        ("bars_to_first_barrier_5", 0.98),
        ("return_5", 0.50),
    ]
    features["mutual_info"] = [("future_return_5", 0.99), ("return_5", 0.50)]
    features["random_forest"] = [("long_triple_barrier_2_1_5", 0.99), ("return_5", 0.50)]
    features["permutation"] = [("return_5", 0.50)]

    target = preferred_target("long", 5)
    report_dir = target_report_dir(
        reports_root,
        direction="long",
        symbol="EURUSD",
        timeframe="M15",
        horizon=5,
        target=target,
    )
    write_csv(
        report_dir / "correlations.csv",
        ["feature", "abs_directional_spearman", "abs_spearman"],
        [{"feature": feature, "abs_directional_spearman": value, "abs_spearman": value} for feature, value in features["correlation"]],
    )
    write_csv(
        report_dir / "mutual_information.csv",
        ["feature", "mutual_information"],
        [{"feature": feature, "mutual_information": value} for feature, value in features["mutual_info"]],
    )
    write_csv(
        report_dir / "random_forest_importance.csv",
        ["feature", "importance"],
        [{"feature": feature, "importance": value} for feature, value in features["random_forest"]],
    )
    write_csv(
        report_dir / "permutation_importance.csv",
        ["feature", "importance_mean"],
        [{"feature": feature, "importance_mean": value} for feature, value in features["permutation"]],
    )

    paths = build_direction_feature_stability(
        reports_root=reports_root,
        output_root=output_root,
        symbols=["EURUSD"],
        timeframe="M15",
        horizon=5,
        direction="long",
        top_n=2,
    )
    rows = read_csv(paths["feature_stability_csv"])

    assert {row["feature"] for row in rows} == {"return_5"}
    assert {row["target"] for row in rows} == {"long_tp_2atr_sl_1atr_hit_first_5"}


def test_feature_family_mapping() -> None:
    assert feature_family("spread_to_atr_20") == "spread/liquidity"
    assert feature_family("tick_volume_ratio_20") == "volume/liquidity"
    assert feature_family("upper_wick_to_atr_20") == "volatility/range"
    assert feature_family("ma_diff_atr_20") == "trend/ma"
    assert feature_family("hour") == "session/calendar"
    assert feature_family("minutes_to_next_news") == "news_risk"
    assert feature_family("feature_alpha") == "other"


def test_report_writing_and_language_boundaries(tmp_path: Path) -> None:
    reports_root = tmp_path / "target_runs"
    output_root = tmp_path / "stability"
    write_ml_feature_reports(reports_root, direction="long", symbol="EURUSD", features=base_features())

    paths = build_direction_feature_stability(
        reports_root=reports_root,
        output_root=output_root,
        symbols=["EURUSD"],
        timeframe="M15",
        horizon=10,
        direction="long",
        top_n=2,
    )

    assert paths["feature_stability_csv"].exists()
    assert paths["feature_stability_report"].exists()
    report_text = paths["feature_stability_report"].read_text(encoding="utf-8").lower()
    assert "research-only" in report_text
    assert "hypothesis discovery" in report_text
    assert "buy" not in report_text
    assert "sell" not in report_text
    assert "live signal" not in report_text
