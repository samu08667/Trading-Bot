from argparse import Namespace
from pathlib import Path

import pytest

from scripts.compare_mt5_recent_spreads import (
    account_metadata,
    compare_symbol_spreads,
    output_dir_for_run,
    resolve_symbol_name_from_candidates,
    safe_ratio,
    spread_points_from_ticks,
)


def test_spread_points_from_ticks_calculates_points() -> None:
    ticks = [
        {"time": 1704067200, "bid": 1.10000, "ask": 1.10012},
        {"time": 1704067210, "bid": 1.10000, "ask": 1.10005},
    ]

    spreads = spread_points_from_ticks(ticks, 0.00001)

    assert [spread for _time, spread in spreads] == [12, 5]


def test_comparison_ratio_is_calculated() -> None:
    assert safe_ratio(15, 10) == 1.5


def test_alert_flag_true_when_ratio_crosses_threshold() -> None:
    row = compare_symbol_spreads(
        {"tick_count": 10, "spread_p75_points": 15, "spread_p90_points": 20},
        {"spread_count": 100, "spread_p75_points": 10, "spread_p90_points": 14},
        symbol="EURUSD",
        alert_ratio=1.5,
    )

    assert row["alert_flag"] == "yes"
    assert "p75_ratio" in str(row["alert_reason"])


def test_no_division_by_zero() -> None:
    assert safe_ratio(10, 0) is None


def test_missing_mt5_samples_warns_without_crashing() -> None:
    row = compare_symbol_spreads(
        {"tick_count": 0, "spread_p75_points": None, "spread_p90_points": None},
        {"spread_count": 100, "spread_p75_points": 10, "spread_p90_points": 12},
        symbol="EURUSD",
        alert_ratio=1.5,
    )

    assert row["alert_flag"] == "no"
    assert "missing_mt5_samples" in str(row["alert_reason"])


def test_missing_historical_samples_warns_without_crashing() -> None:
    row = compare_symbol_spreads(
        {"tick_count": 10, "spread_p75_points": 10, "spread_p90_points": 12},
        {"spread_count": 0, "spread_p75_points": None, "spread_p90_points": None},
        symbol="EURUSD",
        alert_ratio=1.5,
    )

    assert row["alert_flag"] == "no"
    assert "missing_historical_samples" in str(row["alert_reason"])


class AccountInfo:
    login = 123456789
    server = "Pepperstone-Demo"
    company = "Pepperstone"
    currency = "USD"


def test_account_metadata_masks_login() -> None:
    metadata = account_metadata(AccountInfo())

    assert metadata["login_masked"] == "***6789"
    assert "123456789" not in str(metadata)


def test_symbol_suffix_resolver_maps_base_to_suffix() -> None:
    assert resolve_symbol_name_from_candidates("EURUSD", ["GBPUSD", "EURUSD.a"]) == "EURUSD.a"


def test_output_already_exists_requires_overwrite(tmp_path: Path) -> None:
    output_dir = tmp_path / "reports" / "run1"
    output_dir.mkdir(parents=True)
    (output_dir / "spread_comparison.csv").write_text("symbol\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Pass --overwrite"):
        output_dir_for_run(tmp_path / "reports", "run1", overwrite=False)


def test_new_script_does_not_contain_trade_call_name() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "compare_mt5_recent_spreads.py"
    forbidden = "order" + "_send"

    assert forbidden not in script_path.read_text(encoding="utf-8")
