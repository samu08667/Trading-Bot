from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts import build_exit_policy_paired_attribution as attribution


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def trade(
    policy_id: str,
    raw_signal_index: int,
    *,
    exit_reason: str,
    r_multiple: float,
    pips: float,
    holding_bars: int,
    entry_time: str,
    exit_time: str,
) -> dict[str, object]:
    return {
        "run_id": "source_unit",
        "policy_id": policy_id,
        "trade_index": raw_signal_index,
        "raw_signal_index": raw_signal_index,
        "signal_id": f"signal_{raw_signal_index:03d}",
        "entry_time_server": entry_time,
        "exit_time_server": exit_time,
        "entry_price": "1.25000",
        "exit_price": "1.24900",
        "tp_price": "1.24850",
        "sl_price": "1.25100",
        "exit_reason": exit_reason,
        "R_multiple": r_multiple,
        "pips": pips,
        "holding_bars": holding_bars,
        "missed_tp_after_time_exit": "false",
        "would_have_hit_tp_after_time_exit": "false",
        "would_have_hit_sl_after_time_exit": "false",
    }


def make_source_report(tmp_path: Path) -> Path:
    source = tmp_path / "source_report"
    trade_fields = [
        "run_id",
        "policy_id",
        "trade_index",
        "raw_signal_index",
        "signal_id",
        "entry_time_server",
        "exit_time_server",
        "entry_price",
        "exit_price",
        "tp_price",
        "sl_price",
        "exit_reason",
        "R_multiple",
        "pips",
        "holding_bars",
        "missed_tp_after_time_exit",
        "would_have_hit_tp_after_time_exit",
        "would_have_hit_sl_after_time_exit",
    ]
    rows = [
        trade(
            "current_10_bars",
            1,
            exit_reason="tp",
            r_multiple=1.5,
            pips=15.0,
            holding_bars=4,
            entry_time="2025-01-02 22:00:00",
            exit_time="2025-01-02 23:00:00",
        ),
        trade(
            "max_holding_30",
            1,
            exit_reason="tp",
            r_multiple=1.5,
            pips=15.0,
            holding_bars=4,
            entry_time="2025-01-02 22:00:00",
            exit_time="2025-01-02 23:00:00",
        ),
        trade(
            "current_10_bars",
            2,
            exit_reason="time_exit",
            r_multiple=0.2,
            pips=2.0,
            holding_bars=10,
            entry_time="2025-02-03 22:00:00",
            exit_time="2025-02-04 00:30:00",
        ),
        trade(
            "max_holding_30",
            2,
            exit_reason="tp",
            r_multiple=1.5,
            pips=15.0,
            holding_bars=14,
            entry_time="2025-02-03 22:00:00",
            exit_time="2025-02-04 01:30:00",
        ),
        trade(
            "current_10_bars",
            3,
            exit_reason="time_exit",
            r_multiple=0.3,
            pips=3.0,
            holding_bars=10,
            entry_time="2025-04-07 22:00:00",
            exit_time="2025-04-08 00:30:00",
        ),
        trade(
            "max_holding_30",
            3,
            exit_reason="sl",
            r_multiple=-1.0,
            pips=-10.0,
            holding_bars=16,
            entry_time="2025-04-07 22:00:00",
            exit_time="2025-04-08 02:00:00",
        ),
    ]
    write_csv(source / attribution.TRADES_FILE, trade_fields, rows)
    write_csv(
        source / attribution.SUMMARY_FILE,
        ["run_id", "policy_id", "trade_count"],
        [
            {"run_id": "source_unit", "policy_id": "current_10_bars", "trade_count": 3},
            {"run_id": "source_unit", "policy_id": "max_holding_30", "trade_count": 3},
        ],
    )
    write_csv(
        source / attribution.BY_MONTH_FILE,
        ["run_id", "policy_id", "period"],
        [],
    )
    write_csv(
        source / attribution.WALK_FORWARD_FILE,
        ["run_id", "policy_id", "period", "period_start", "period_end"],
        [
            {
                "run_id": "source_unit",
                "policy_id": "current_10_bars",
                "period": "wf_block_001",
                "period_start": "2025-01-01 00:00:00",
                "period_end": "2025-03-31 23:59:59",
            },
            {
                "run_id": "source_unit",
                "policy_id": "current_10_bars",
                "period": "wf_block_002",
                "period_start": "2025-04-01 00:00:00",
                "period_end": "2025-06-30 23:59:59",
            },
        ],
    )
    return source


def build_attribution(tmp_path: Path) -> dict[str, Path]:
    source = make_source_report(tmp_path)
    args = attribution.build_parser().parse_args(
        [
            "--source-report-dir",
            str(source),
            "--output-dir",
            str(tmp_path / "out"),
            "--run-id",
            "unit_attribution",
            "--overwrite",
        ]
    )
    return attribution.build_outputs(args)


def test_paired_join_produces_same_number_of_trades_and_expected_delta(tmp_path: Path) -> None:
    outputs = build_attribution(tmp_path)
    paired = read_csv(outputs["paired_trades"])

    assert len(paired) == 3
    assert [row["pair_key"] for row in paired] == [
        "1|2025-01-02 22:00:00",
        "2|2025-02-03 22:00:00",
        "3|2025-04-07 22:00:00",
    ]
    assert float(paired[1]["delta_R"]) == pytest.approx(1.3)
    assert float(paired[1]["delta_R"]) == pytest.approx(
        float(paired[1]["max30_R"]) - float(paired[1]["current_R"])
    )
    assert float(paired[2]["delta_pips"]) == pytest.approx(-13.0)
    assert int(paired[2]["delta_holding_bars"]) == 6


def test_category_assignment_for_synthetic_cases(tmp_path: Path) -> None:
    outputs = build_attribution(tmp_path)
    paired = {row["raw_signal_index"]: row for row in read_csv(outputs["paired_trades"])}

    assert paired["1"]["category"] == "same_result"
    assert paired["2"]["category"] == "current_time_exit_then_max30_tp"
    assert paired["3"]["category"] == "current_time_exit_then_max30_sl"

    current = {
        "exit_reason": "time_exit",
        "exit_time_server": "2025-01-03 00:30:00",
    }
    friday = {
        "exit_reason": "friday_forced_flat",
        "exit_time_server": "2025-01-03 23:45:00",
    }
    assert attribution.classify_pair(current, friday, 0.4, 5) == "friday_interaction"
    assert (
        attribution.classify_pair(
            current,
            {"exit_reason": "time_exit", "exit_time_server": "2025-01-03 01:30:00"},
            0.2,
            4,
        )
        == "current_time_exit_then_max30_better_non_tp"
    )
    assert (
        attribution.classify_pair(
            current,
            {"exit_reason": "time_exit", "exit_time_server": "2025-01-03 01:30:00"},
            -0.2,
            4,
        )
        == "current_time_exit_then_max30_worse_non_sl"
    )


def test_summary_aggregates_count_sum_average_and_exposure(tmp_path: Path) -> None:
    outputs = build_attribution(tmp_path)
    summary = read_csv(outputs["summary"])
    overall = next(row for row in summary if row["scope"] == "overall")

    assert int(overall["trade_count"]) == 3
    assert float(overall["sum_delta_R"]) == pytest.approx(0.0)
    assert float(overall["avg_delta_R"]) == pytest.approx(0.0)
    assert int(overall["count_max30_better"]) == 1
    assert int(overall["count_current_better"]) == 1
    assert int(overall["count_same_result"]) == 1
    assert int(overall["count_current_time_exit_then_max30_tp"]) == 1
    assert int(overall["count_current_time_exit_then_max30_sl"]) == 1
    assert float(overall["extra_exposure_hours"]) == pytest.approx(2.5)
    assert "current_time_exit_then_max30_tp=1.3" in overall["sum_delta_R_by_category"]
    assert "current_time_exit_then_max30_sl=-1.3" in overall["avg_delta_R_by_category"]


def test_period_outputs_include_month_quarter_year_and_walk_forward_block(tmp_path: Path) -> None:
    outputs = build_attribution(tmp_path)
    paired = read_csv(outputs["paired_trades"])
    by_month = read_csv(outputs["by_month"])
    by_quarter = read_csv(outputs["by_quarter"])
    by_year = read_csv(outputs["by_year"])

    assert paired[0]["walk_forward_block"] == "wf_block_001"
    assert paired[2]["walk_forward_block"] == "wf_block_002"
    assert [row["period"] for row in by_month] == ["2025-01", "2025-02", "2025-04"]
    assert [row["period"] for row in by_quarter] == ["2025-Q1", "2025-Q2"]
    assert [row["period"] for row in by_year] == ["2025"]


def test_script_has_no_mt5_broker_or_core_strategy_dependencies() -> None:
    source = Path("scripts/build_exit_policy_paired_attribution.py").read_text(encoding="utf-8")

    forbidden_snippets = [
        "MetaTrader5",
        "mt5.",
        "OrderSend",
        "OrderCheck",
        "order_send(",
        "order_check(",
        ".mq5",
        "config/strategy_specs",
    ]
    for snippet in forbidden_snippets:
        assert snippet not in source
