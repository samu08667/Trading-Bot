import argparse
import csv
from pathlib import Path
import re
import sqlite3

from scripts.diagnose_preferred_horizon_prerequisites import (
    diagnose_preferred_horizon_prerequisites,
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
]


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def create_db(path: Path, *, extra_columns: dict[str, str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = {
        "symbol": "TEXT",
        "timeframe": "TEXT",
        **extra_columns,
    }
    with sqlite3.connect(path) as connection:
        column_sql = ", ".join(f"{quote_identifier(name)} {column_type}" for name, column_type in columns.items())
        connection.execute(f"CREATE TABLE ml_dataset ({column_sql})")
        for row in rows:
            values = {column: row.get(column) for column in columns}
            names = list(values)
            placeholders = ", ".join("?" for _ in names)
            name_sql = ", ".join(quote_identifier(name) for name in names)
            connection.execute(
                f"INSERT INTO ml_dataset ({name_sql}) VALUES ({placeholders})",
                [values[name] for name in names],
            )


def balanced_rows(target_column: str, *, feature: str = "return_5", count: int = 240) -> list[dict[str, object]]:
    rows = []
    for index in range(count):
        rows.append(
            {
                "symbol": "EURUSD",
                "timeframe": "M15",
                target_column: 1 if index % 2 == 0 else 0,
                feature: float(index),
            }
        )
    return rows


def write_shortlist(
    root: Path,
    *,
    direction: str = "long",
    horizon: int = 10,
    feature: str = "return_5",
    rows_count: int = 1,
    target: str | None = None,
    target_family: str = "preferred_2atr_1atr_hit_first",
) -> Path:
    path = root / target_family / direction / f"M15_h{horizon}" / "preferred_feature_hypotheses.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=SHORTLIST_FIELDS)
        writer.writeheader()
        for _ in range(rows_count):
            writer.writerow(
                {
                    "direction": direction,
                    "timeframe": "M15",
                    "horizon": horizon,
                    "target": target or f"{direction}_tp_2atr_sl_1atr_hit_first_{horizon}",
                    "feature": feature,
                    "feature_family": "momentum/returns",
                    "tradability_role": "momentum_filter",
                    "normalized_or_raw": "preferred_normalized",
                    "recommended_usage": "candidate for controlled combination testing",
                    "caution_level": "low",
                    "symbols_seen": 3,
                    "stability_score": 15,
                }
            )
    return path


def args(tmp_path: Path, db_path: Path, shortlist_root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        timeframe="M15",
        horizons=[10],
        groups=["fx"],
        directions=["long"],
        target_family="preferred_2atr_1atr_hit_first",
        symbols_fx=["EURUSD"],
        symbols_xauusd=["XAUUSD"],
        db_path=db_path,
        shortlist_root=shortlist_root,
        output_root=tmp_path / "reports",
        run_id="prereq_unit_run",
        min_non_null_target_rows=200,
        min_positive_target_rows=50,
        min_negative_target_rows=50,
        min_positive_rate=0.05,
        max_positive_rate=0.95,
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def first_result(tmp_path: Path, db_path: Path, shortlist_root: Path) -> dict[str, str]:
    outputs = diagnose_preferred_horizon_prerequisites(args(tmp_path, db_path, shortlist_root))
    return read_rows(outputs["prerequisite_diagnostics"])[0]


def test_missing_target_column(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "test.db"
    shortlist_root = tmp_path / "shortlists"
    create_db(
        db_path,
        extra_columns={"return_5": "REAL"},
        rows=[{"symbol": "EURUSD", "timeframe": "M15", "return_5": 0.1}],
    )
    write_shortlist(shortlist_root)

    row = first_result(tmp_path, db_path, shortlist_root)

    assert row["root_cause"] == "target_column_missing"
    assert row["target_column_exists"] == "false"


def test_target_exists_but_all_null(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "test.db"
    shortlist_root = tmp_path / "shortlists"
    target = "long_tp_2atr_sl_1atr_hit_first_10"
    create_db(
        db_path,
        extra_columns={target: "INTEGER", "return_5": "REAL"},
        rows=[
            {"symbol": "EURUSD", "timeframe": "M15", target: None, "return_5": 0.1}
            for _ in range(240)
        ],
    )
    write_shortlist(shortlist_root)

    row = first_result(tmp_path, db_path, shortlist_root)

    assert row["root_cause"] == "target_all_null"
    assert row["non_null_target_rows"] == "0"


def test_target_sparse_or_unbalanced(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "test.db"
    shortlist_root = tmp_path / "shortlists"
    target = "long_tp_2atr_sl_1atr_hit_first_10"
    rows = []
    for index in range(240):
        rows.append(
            {
                "symbol": "EURUSD",
                "timeframe": "M15",
                target: 1 if index == 0 else 0,
                "return_5": float(index),
            }
        )
    create_db(db_path, extra_columns={target: "INTEGER", "return_5": "REAL"}, rows=rows)
    write_shortlist(shortlist_root)

    row = first_result(tmp_path, db_path, shortlist_root)

    assert row["root_cause"] == "target_too_unbalanced"
    assert row["positive_count"] == "1"


def test_missing_preferred_shortlist(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "test.db"
    shortlist_root = tmp_path / "shortlists"
    target = "long_tp_2atr_sl_1atr_hit_first_10"
    create_db(
        db_path,
        extra_columns={target: "INTEGER", "return_5": "REAL"},
        rows=balanced_rows(target),
    )

    row = first_result(tmp_path, db_path, shortlist_root)

    assert row["root_cause"] == "preferred_shortlist_missing"
    assert row["preferred_shortlist_exists"] == "false"


def test_empty_preferred_shortlist(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "test.db"
    shortlist_root = tmp_path / "shortlists"
    target = "long_tp_2atr_sl_1atr_hit_first_10"
    create_db(
        db_path,
        extra_columns={target: "INTEGER", "return_5": "REAL"},
        rows=balanced_rows(target),
    )
    write_shortlist(shortlist_root, rows_count=0)

    row = first_result(tmp_path, db_path, shortlist_root)

    assert row["root_cause"] == "preferred_shortlist_empty"
    assert row["preferred_shortlist_rows"] == "0"


def test_sufficient_prerequisites(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "test.db"
    shortlist_root = tmp_path / "shortlists"
    target = "long_tp_2atr_sl_1atr_hit_first_10"
    create_db(
        db_path,
        extra_columns={target: "INTEGER", "return_5": "REAL"},
        rows=balanced_rows(target),
    )
    write_shortlist(shortlist_root, feature="return_5")

    row = first_result(tmp_path, db_path, shortlist_root)

    assert row["root_cause"] == "sufficient_prerequisites_available"
    assert row["candidate_features_available_for_backtest"] == "1"
    assert row["strict_shortlist_only_would_produce_zero_rows"] == "false"


def test_h5_and_h20_sufficient_when_targets_and_shortlists_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "test.db"
    shortlist_root = tmp_path / "shortlists"
    target_h5 = "long_tp_2atr_sl_1atr_hit_first_5"
    target_h20 = "long_tp_2atr_sl_1atr_hit_first_20"
    rows = []
    for index in range(240):
        rows.append(
            {
                "symbol": "EURUSD",
                "timeframe": "M15",
                target_h5: 1 if index % 2 == 0 else 0,
                target_h20: 1 if index % 3 == 0 else 0,
                "return_5": float(index),
            }
        )
    create_db(
        db_path,
        extra_columns={target_h5: "INTEGER", target_h20: "INTEGER", "return_5": "REAL"},
        rows=rows,
    )
    write_shortlist(shortlist_root, horizon=5, feature="return_5")
    write_shortlist(shortlist_root, horizon=20, feature="return_5")
    run_args = args(tmp_path, db_path, shortlist_root)
    run_args.horizons = [5, 20]

    outputs = diagnose_preferred_horizon_prerequisites(run_args)
    rows = read_rows(outputs["prerequisite_diagnostics"])

    assert {row["horizon"] for row in rows} == {"5", "20"}
    assert {row["root_cause"] for row in rows} == {"sufficient_prerequisites_available"}


def test_one_and_half_atr_target_family_maps_to_safe_target_column(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "test.db"
    shortlist_root = tmp_path / "shortlists"
    target = "long_tp_1_5atr_sl_1atr_hit_first_10"
    create_db(
        db_path,
        extra_columns={target: "INTEGER", "return_5": "REAL"},
        rows=balanced_rows(target),
    )
    write_shortlist(shortlist_root, target=target, target_family="preferred_1_5atr_1atr_hit_first")
    run_args = args(tmp_path, db_path, shortlist_root)
    run_args.target_family = "preferred_1_5atr_1atr_hit_first"

    outputs = diagnose_preferred_horizon_prerequisites(run_args)
    row = read_rows(outputs["prerequisite_diagnostics"])[0]

    assert row["target_column"] == target
    assert row["root_cause"] == "sufficient_prerequisites_available"
    assert row["positive_rate_flag"] == "within_initial_range"


def test_report_contains_research_warning_and_avoids_blocked_language(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "test.db"
    shortlist_root = tmp_path / "shortlists"
    target = "long_tp_2atr_sl_1atr_hit_first_10"
    create_db(
        db_path,
        extra_columns={target: "INTEGER", "return_5": "REAL"},
        rows=balanced_rows(target),
    )
    write_shortlist(shortlist_root)

    outputs = diagnose_preferred_horizon_prerequisites(args(tmp_path, db_path, shortlist_root))
    report_text = outputs["prerequisite_report"].read_text(encoding="utf-8")
    lower_report = report_text.lower()

    assert "## Research-only warning" in report_text
    assert "No backtests are run" in report_text
    assert "buy" not in lower_report
    assert "sell" not in lower_report
    assert "live signal" not in lower_report


def test_no_metatrader5_or_live_api_imports_are_introduced() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_preferred_horizon_prerequisites.py"
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
