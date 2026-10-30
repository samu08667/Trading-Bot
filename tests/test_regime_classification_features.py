import re
from pathlib import Path

from scripts.regime_classification import (
    REGIME_CLASSIFICATION_SOURCE_COLUMNS,
    assert_no_regime_source_leakage,
    classify_range_regime,
    classify_session,
    classify_session_from_hour,
    classify_spread_liquidity_regime,
    classify_volatility_regime,
    classify_volume_liquidity_regime,
    missing_regime_source_groups,
    with_regime_labels,
)
from scripts.check_ml_dataset import check_ml_dataset


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_session_classification_from_timestamp_and_hour() -> None:
    assert classify_session_from_hour(2) == "Asia"
    assert classify_session_from_hour(10) == "London"
    assert classify_session_from_hour(14) == "London_NewYork_Overlap"
    assert classify_session_from_hour(18) == "New_York"
    assert classify_session_from_hour(23) == "Off_hours"
    assert classify_session({"time_server": "2024-01-01 14:15:00"}) == "London_NewYork_Overlap"


def test_spread_liquidity_regime_classification() -> None:
    assert classify_spread_liquidity_regime({"spread_to_atr_20": 0.03}) == "low_spread"
    assert classify_spread_liquidity_regime({"spread_to_atr_20": 0.10}) == "normal_spread"
    assert classify_spread_liquidity_regime({"spread_to_atr_20": 0.20}) == "high_spread"
    assert classify_spread_liquidity_regime({"spread_to_atr_20": 0.40}) == "extreme_spread"
    assert classify_spread_liquidity_regime({"spread_return": 0.00010}) == "normal_spread"


def test_volatility_regime_classification() -> None:
    assert classify_volatility_regime({"volatility_ratio_20_100": 0.50}) == "low_volatility"
    assert classify_volatility_regime({"volatility_ratio_20_100": 1.00}) == "normal_volatility"
    assert classify_volatility_regime({"volatility_ratio_20_100": 1.50}) == "high_volatility"
    assert classify_volatility_regime({"volatility_ratio_20_100": 2.00}) == "extreme_volatility"
    assert classify_volatility_regime({"volatility_100": 0.0020}) == "high_volatility"


def test_range_regime_classification() -> None:
    assert classify_range_regime({"range_to_atr_20": 0.50}) == "compressed_range"
    assert classify_range_regime({"range_to_atr_20": 1.00}) == "normal_range"
    assert classify_range_regime({"range_to_atr_20": 1.80}) == "expanded_range"
    assert classify_range_regime({"range_to_atr_20": 2.50}) == "extreme_range"


def test_volume_liquidity_regime_classification() -> None:
    assert classify_volume_liquidity_regime({"volume_dry_up_20": 1}) == "dry_volume"
    assert classify_volume_liquidity_regime({"volume_spike_20": 1}) == "volume_spike"
    assert classify_volume_liquidity_regime({"tick_volume_zscore_100": 1.2}) == "high_volume"
    assert classify_volume_liquidity_regime({"tick_volume_percentile_100": 0.5}) == "normal_volume"
    assert classify_volume_liquidity_regime({"volume_vs_session_avg": 0.6}) == "dry_volume"


def test_missing_source_columns_are_reported_by_regime_group() -> None:
    missing = missing_regime_source_groups({"time_server", "hour", "range_to_atr_20"})

    assert "session" not in missing
    assert "range_regime" not in missing
    assert "spread_liquidity_regime" in missing
    assert "volatility_regime" in missing
    assert "volume_liquidity_regime" in missing


def test_missing_regime_labels_are_derived_from_current_row_sources() -> None:
    row = {
        "time_server": "2024-01-01 14:15:00",
        "spread_to_atr_20": 0.20,
        "volatility_ratio_20_100": 0.50,
        "range_to_atr_20": 2.50,
        "volume_dry_up_20": 1,
    }

    enriched = with_regime_labels(row)

    assert "session" not in row
    assert enriched["session"] == "London_NewYork_Overlap"
    assert enriched["spread_liquidity_regime"] == "high_spread"
    assert enriched["volatility_regime"] == "low_volatility"
    assert enriched["range_regime"] == "extreme_range"
    assert enriched["volume_liquidity_regime"] == "dry_volume"


def test_ml_dataset_regime_schema_only_reports_presence_and_non_null_counts(
    tmp_path,
    capsys,
) -> None:
    db_path = tmp_path / "schema_check.db"
    import sqlite3

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE ml_dataset (
                time_server TEXT,
                session TEXT,
                spread_liquidity_regime TEXT,
                volatility_regime TEXT,
                range_regime TEXT,
                volume_liquidity_regime TEXT,
                spread_to_atr_20 REAL,
                volatility_ratio_20_100 REAL,
                range_to_atr_20 REAL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO ml_dataset (
                time_server,
                session,
                spread_liquidity_regime,
                volatility_regime,
                range_regime,
                volume_liquidity_regime,
                spread_to_atr_20,
                volatility_ratio_20_100,
                range_to_atr_20
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2024-01-01 00:00:00", "Asia", "low_spread", "normal_volatility", "normal_range", None, 0.03, 1.0, 1.0),
                ("2024-01-01 00:15:00", None, None, None, None, None, 0.20, 1.5, 2.0),
            ],
        )

    check_ml_dataset(db_path, regime_schema_only=True)
    output = capsys.readouterr().out

    assert "- session: present, non_null=1/2" in output
    assert "- spread_liquidity_regime: present, non_null=1/2" in output
    assert "- spread_liquidity_regime: present sources=spread_to_atr_20" in output
    assert "- volume_liquidity_regime: missing any of" in output


def test_regime_classification_sources_do_not_use_future_targets_or_news_values() -> None:
    assert_no_regime_source_leakage()
    flattened = {
        source
        for source_columns in REGIME_CLASSIFICATION_SOURCE_COLUMNS.values()
        for source in source_columns
    }

    assert all("future" not in source for source in flattened)
    assert all("target" not in source for source in flattened)
    assert all("actual" not in source for source in flattened)
    assert all("forecast" not in source for source in flattened)
    assert all("surprise" not in source for source in flattened)


def test_regime_classification_changes_do_not_import_live_execution_api() -> None:
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
    files = [
        REPO_ROOT / "scripts" / "regime_classification.py",
        REPO_ROOT / "scripts" / "generate_price_features.py",
        REPO_ROOT / "scripts" / "generate_market_features.py",
        REPO_ROOT / "scripts" / "generate_ml_dataset.py",
        REPO_ROOT / "scripts" / "check_ml_dataset.py",
        REPO_ROOT / "scripts" / "diagnose_regime_filter_candidates.py",
        REPO_ROOT / "scripts" / "run_regime_filtered_candidate_diagnostics.py",
    ]

    matches = {
        str(path.relative_to(REPO_ROOT)): blocked.findall(path.read_text(encoding="utf-8"))
        for path in files
    }

    assert matches == {str(path.relative_to(REPO_ROOT)): [] for path in files}
