import argparse
import csv
from pathlib import Path

from scripts.build_preferred_feature_hypothesis_shortlist import (
    build_preferred_feature_hypothesis_shortlist,
    feature_family,
    input_path_for,
)


STABILITY_FIELDS = [
    "direction",
    "timeframe",
    "horizon",
    "target",
    "feature",
    "symbols_seen",
    "correlation_topn_count",
    "mutual_info_topn_count",
    "random_forest_topn_count",
    "permutation_topn_count",
    "average_directional_spearman_rank",
    "average_mutual_info_rank",
    "average_random_forest_rank",
    "average_permutation_rank",
    "stability_score",
    "feature_family",
    "notes",
]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=STABILITY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def stability_row(direction: str, feature: str, symbols_seen: int, score: int) -> dict[str, object]:
    return {
        "direction": direction,
        "timeframe": "M15",
        "horizon": 10,
        "target": f"{direction}_tp_2atr_sl_1atr_hit_first_10",
        "feature": feature,
        "symbols_seen": symbols_seen,
        "correlation_topn_count": symbols_seen,
        "mutual_info_topn_count": symbols_seen,
        "random_forest_topn_count": symbols_seen,
        "permutation_topn_count": symbols_seen,
        "average_directional_spearman_rank": 2.0,
        "average_mutual_info_rank": 3.0,
        "average_random_forest_rank": 4.0,
        "average_permutation_rank": 5.0,
        "stability_score": score,
        "feature_family": "old_family",
        "notes": "source_note",
    }


def test_reads_long_short_stability_files_and_filters_rows(tmp_path: Path) -> None:
    input_root = tmp_path / "stability"
    output_root = tmp_path / "shortlist"
    write_csv(
        input_path_for(input_root, direction="long", timeframe="M15", horizon=10),
        [
            stability_row("long", "ma_diff_atr_20", 3, 14),
            stability_row("long", "ma_fast", 3, 13),
            stability_row("long", "return_5", 3, 12),
            stability_row("long", "day_of_week", 2, 20),
            stability_row("long", "range_to_atr_20", 3, 11),
        ],
    )
    write_csv(
        input_path_for(input_root, direction="short", timeframe="M15", horizon=10),
        [
            stability_row("short", "spread_to_atr_20", 3, 15),
            stability_row("short", "tick_volume_ratio_20", 3, 12),
        ],
    )

    outputs = build_preferred_feature_hypothesis_shortlist(
        argparse.Namespace(
            input_root=input_root,
            output_root=output_root,
            timeframe="M15",
            horizon=10,
            directions=["long", "short"],
            min_symbols=3,
            min_stability_score=12,
        )
    )

    long_rows = read_csv(outputs["long"]["preferred_feature_hypotheses_csv"])
    short_rows = read_csv(outputs["short"]["preferred_feature_hypotheses_csv"])

    assert {row["feature"] for row in long_rows} == {"ma_diff_atr_20", "ma_fast", "return_5"}
    assert {row["feature"] for row in short_rows} == {"spread_to_atr_20", "tick_volume_ratio_20"}
    assert {row["direction"] for row in long_rows} == {"long"}
    assert {row["direction"] for row in short_rows} == {"short"}


def test_shortlist_excludes_future_target_and_leakage_columns(tmp_path: Path) -> None:
    input_root = tmp_path / "stability"
    output_root = tmp_path / "shortlist"
    write_csv(
        input_path_for(input_root, direction="long", timeframe="M15", horizon=5),
        [
            stability_row("long", "return_5", 3, 12),
            stability_row("long", "long_tp_2atr_sl_1atr_hit_first_5", 3, 99),
            stability_row("long", "long_triple_barrier_2_1_5", 3, 99),
            stability_row("long", "bars_to_first_barrier_5", 3, 99),
            stability_row("long", "future_return_5", 3, 99),
        ],
    )

    outputs = build_preferred_feature_hypothesis_shortlist(
        argparse.Namespace(
            input_root=input_root,
            output_root=output_root,
            timeframe="M15",
            horizon=5,
            directions=["long"],
            min_symbols=3,
            min_stability_score=12,
        )
    )
    rows = read_csv(outputs["long"]["preferred_feature_hypotheses_csv"])

    assert {row["feature"] for row in rows} == {"return_5"}
    report_text = outputs["long"]["preferred_feature_hypotheses_report"].read_text(encoding="utf-8")
    assert "Excluded future/target/leakage feature rows: 4" in report_text


def test_feature_family_mapping_fixes() -> None:
    assert feature_family("return_1") == "momentum/returns"
    assert feature_family("candle_range") == "volatility/range"
    assert feature_family("true_range") == "volatility/range"
    assert feature_family("atr_50") == "volatility/range"
    assert feature_family("volatility_100") == "volatility/range"
    assert feature_family("volatility_ratio_20_100") == "volatility/range"
    assert feature_family("upper_wick_to_atr_20") == "volatility/range"
    assert feature_family("ma_diff_atr_20") == "trend/ma"
    assert feature_family("spread_avg_20") == "spread/liquidity"
    assert feature_family("tick_volume_zscore_100") == "volume/liquidity"
    assert feature_family("hour_session") == "session/calendar"
    assert feature_family("minutes_to_next_news") == "news_risk"


def test_marks_raw_and_normalized_features(tmp_path: Path) -> None:
    input_root = tmp_path / "stability"
    output_root = tmp_path / "shortlist"
    write_csv(
        input_path_for(input_root, direction="long", timeframe="M15", horizon=10),
        [
            stability_row("long", "ma_fast", 3, 12),
            stability_row("long", "spread_avg_20", 3, 12),
            stability_row("long", "tick_volume_ratio_20", 3, 12),
            stability_row("long", "volume_vs_session_avg", 3, 12),
        ],
    )

    outputs = build_preferred_feature_hypothesis_shortlist(
        argparse.Namespace(
            input_root=input_root,
            output_root=output_root,
            timeframe="M15",
            horizon=10,
            directions=["long"],
            min_symbols=3,
            min_stability_score=12,
        )
    )
    rows = {row["feature"]: row for row in read_csv(outputs["long"]["preferred_feature_hypotheses_csv"])}

    assert rows["ma_fast"]["normalized_or_raw"] == "raw_scale_dependent"
    assert rows["ma_fast"]["caution_level"] == "high"
    assert rows["ma_fast"]["recommended_usage"] == "prefer normalized variant"
    assert rows["spread_avg_20"]["normalized_or_raw"] == "raw_scale_dependent"
    assert rows["tick_volume_ratio_20"]["normalized_or_raw"] == "preferred_normalized"
    assert rows["tick_volume_ratio_20"]["caution_level"] == "low"
    assert rows["volume_vs_session_avg"]["normalized_or_raw"] == "preferred_normalized"


def test_writes_markdown_report_with_research_boundary_language(tmp_path: Path) -> None:
    input_root = tmp_path / "stability"
    output_root = tmp_path / "shortlist"
    write_csv(
        input_path_for(input_root, direction="long", timeframe="M15", horizon=10),
        [
            stability_row("long", "ma_diff_atr_20", 3, 14),
            stability_row("long", "ma_fast", 3, 13),
        ],
    )

    outputs = build_preferred_feature_hypothesis_shortlist(
        argparse.Namespace(
            input_root=input_root,
            output_root=output_root,
            timeframe="M15",
            horizon=10,
            directions=["long"],
            min_symbols=3,
            min_stability_score=12,
        )
    )

    report_path = outputs["long"]["preferred_feature_hypotheses_report"]
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8").lower()
    assert "research-only" in report_text
    assert "not a strategy" in report_text
    assert "controlled backtest and validation" in report_text
    assert "buy" not in report_text
    assert "sell" not in report_text
    assert "live signal" not in report_text
