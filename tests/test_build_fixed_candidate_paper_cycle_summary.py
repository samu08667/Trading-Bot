from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_paper_cycle_summary as summary


OPEN_SIGNAL_ID = "fixture_open_signal"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def safety_fields() -> dict[str, bool]:
    return {
        "no_broker_connection_performed": True,
        "no_order_execution_performed": True,
        "no_db_mutation_performed": True,
        "no_data_generation_performed": True,
        "no_trading_decision_performed": True,
    }


def demo_config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "config_role": "paper_demo_strategy_config",
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "paper_only": True,
        "broker_connection_allowed": False,
        "order_execution_allowed": False,
        "real_money_allowed": False,
    }


def write_demo_spec_dir(path: Path) -> None:
    write_csv(path / summary.SPEC_CSV, ["spec_section", "spec_key"], [{"spec_section": "paper", "spec_key": "ok"}])
    write_json(
        path / summary.SPEC_MANIFEST,
        {
            "run_id": "fixture_spec",
            "paper_only_specification": True,
            "warnings_count": 0,
            "blocking_warnings_count": 0,
            **safety_fields(),
        },
    )
    (path / summary.SPEC_REPORT).write_text("# Demo spec\n", encoding="utf-8")
    write_csv(path / summary.SPEC_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_readiness_dir(path: Path) -> None:
    write_csv(
        path / summary.READINESS_CSV,
        ["readiness_area", "readiness_status"],
        [{"readiness_area": "paper_boundary", "readiness_status": "ready"}],
    )
    write_json(
        path / summary.READINESS_MANIFEST,
        {
            "run_id": "fixture_readiness",
            "paper_only_boundary_confirmed": True,
            "warnings_count": 0,
            "blocking_warnings_count": 0,
            **safety_fields(),
        },
    )
    (path / summary.READINESS_REPORT).write_text("# Readiness\n", encoding="utf-8")
    write_csv(path / summary.READINESS_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_thresholds_dir(path: Path) -> None:
    write_json(
        path / summary.THRESHOLDS_JSON,
        {
            "schema_version": 1,
            "artifact_role": "fixed_candidate_numeric_tercile_thresholds",
            "candidate_id": "gbpusd_short_h10_1_5_off_hours",
            "features": {
                "close_to_ma_fast_atr_20": {"upper_tercile_boundary": 0.5951568132962021},
                "tick_volume_percentile_100": {"lower_tercile_boundary": 0.15, "upper_tercile_boundary": 0.37},
            },
        },
    )
    write_json(
        path / summary.THRESHOLDS_MANIFEST,
        {
            "run_id": "fixture_thresholds",
            "threshold_json_valid": True,
            "warnings_count": 0,
            "blocking_warnings_count": 0,
            **safety_fields(),
        },
    )
    (path / summary.THRESHOLDS_REPORT).write_text("# Thresholds\n", encoding="utf-8")
    write_csv(path / summary.THRESHOLDS_WARNINGS, ["warning_code", "blocking_warning"], [])


def write_signal_logger_dir(path: Path) -> None:
    write_csv(
        path / summary.SIGNAL_LOG_CSV,
        [
            "run_id",
            "signal_id",
            "time_server",
            "signal_state",
            "entry_reference_price",
            "tp_price",
            "sl_price",
            "horizon_bars",
        ],
        [
            {
                "run_id": "fixture_signal_logger",
                "signal_id": OPEN_SIGNAL_ID,
                "time_server": "2026-05-27 22:45:00",
                "signal_state": "paper_signal_opened",
                "entry_reference_price": 1.34308,
                "tp_price": 1.34217475,
                "sl_price": 1.3436835,
                "horizon_bars": 10,
            }
        ],
    )
    write_json(
        path / summary.SIGNAL_STATE_JSON,
        {
            "has_open_paper_trade": True,
            "open_signal_id": OPEN_SIGNAL_ID,
            "entry_time_server": "2026-05-27 22:45:00",
            "entry_price": 1.34308,
            "tp_price": 1.34217475,
            "sl_price": 1.3436835,
            "horizon_bars": 10,
        },
    )
    write_json(
        path / summary.SIGNAL_MANIFEST,
        {
            "run_id": "fixture_signal_logger",
            "generated_at": "2026-05-27T19:57:49+00:00",
            "evaluated_row_time_server": "2026-05-27 22:45:00",
            "signal_state": "paper_signal_opened",
            "signal_opened_count": 1,
            "signal_skipped_count": 0,
            "has_open_paper_trade_after": True,
            "warnings_count": 0,
            "blocking_warnings_count": 0,
            **safety_fields(),
        },
    )
    (path / summary.SIGNAL_REPORT).write_text("# Signal logger\n", encoding="utf-8")
    write_csv(path / summary.SIGNAL_WARNINGS, ["warning_code", "blocking_warning"], [])


def tracker_payload(
    *,
    status: str,
    exit_reason: str = "",
    r_multiple: float | None = None,
    bars_elapsed: int = 5,
    generated_at: str = "2026-05-28T01:00:00+00:00",
    open_signal_id: str = OPEN_SIGNAL_ID,
) -> dict[str, object]:
    has_open = status == "paper_trade_still_open"
    exit_time = "" if has_open else "2026-05-28 00:00:00"
    exit_price = "" if has_open else 1.34217475 if exit_reason == "paper_tp_hit" else 1.3436835 if exit_reason == "paper_sl_hit" else 1.3430
    return {
        "run_id": "fixture_tracker",
        "generated_at": generated_at,
        "open_signal_id": open_signal_id,
        "entry_time_server": "2026-05-27 22:45:00",
        "exit_time_server": exit_time,
        "entry_price": 1.34308,
        "exit_price": exit_price,
        "tp_price": 1.34217475,
        "sl_price": 1.3436835,
        "horizon_bars": 10,
        "bars_elapsed_after": bars_elapsed,
        "trade_status": status,
        "exit_reason": exit_reason,
        "R_multiple": r_multiple,
        "has_open_paper_trade_after": has_open,
        "warnings_count": 0,
        "blocking_warnings_count": 0,
        **safety_fields(),
    }


def write_tracker_dir(path: Path, payload: dict[str, object]) -> None:
    write_csv(
        path / summary.TRACKER_CSV,
        [
            "run_id",
            "open_signal_id",
            "row_type",
            "time_server",
            "trade_status",
            "exit_reason",
            "entry_price",
            "exit_price",
            "tp_price",
            "sl_price",
            "R_multiple",
        ],
        [
            {
                "run_id": payload["run_id"],
                "open_signal_id": payload["open_signal_id"],
                "row_type": "summary",
                "time_server": payload["exit_time_server"] or "2026-05-27 23:45:00",
                "trade_status": payload["trade_status"],
                "exit_reason": payload["exit_reason"],
                "entry_price": payload["entry_price"],
                "exit_price": payload["exit_price"],
                "tp_price": payload["tp_price"],
                "sl_price": payload["sl_price"],
                "R_multiple": payload["R_multiple"],
            }
        ],
    )
    write_json(
        path / summary.TRACKER_STATE_JSON,
        {
            "has_open_paper_trade": payload["has_open_paper_trade_after"],
            "open_signal_id": payload["open_signal_id"],
            "entry_time_server": payload["entry_time_server"],
            "entry_price": payload["entry_price"],
            "tp_price": payload["tp_price"],
            "sl_price": payload["sl_price"],
            "horizon_bars": payload["horizon_bars"],
            "bars_elapsed": payload["bars_elapsed_after"],
            "close_time_server": payload["exit_time_server"],
            "exit_price": payload["exit_price"],
            "exit_reason": payload["exit_reason"],
            "R_multiple": payload["R_multiple"],
            "trade_status": payload["trade_status"],
        },
    )
    write_csv(path / summary.TRACKER_STATE_HISTORY, ["run_id", "event"], [{"run_id": payload["run_id"], "event": "state_written"}])
    write_json(path / summary.TRACKER_MANIFEST, payload)
    (path / summary.TRACKER_REPORT).write_text("# Tracker\n", encoding="utf-8")
    write_csv(path / summary.TRACKER_WARNINGS, ["warning_code", "blocking_warning"], [])


def make_args(
    tmp_path: Path,
    *,
    tracker_payloads: list[dict[str, object]] | None = None,
    missing_signal_logger: bool = False,
    missing_tracker_index: int | None = None,
) -> object:
    config_path = write_json(tmp_path / "config" / "demo_config.json", demo_config())
    spec_dir = tmp_path / "spec"
    readiness_dir = tmp_path / "readiness"
    thresholds_dir = tmp_path / "thresholds"
    signal_dir = tmp_path / "signal_logger"
    write_demo_spec_dir(spec_dir)
    write_readiness_dir(readiness_dir)
    write_thresholds_dir(thresholds_dir)
    if not missing_signal_logger:
        write_signal_logger_dir(signal_dir)
    payloads = tracker_payloads or [
        tracker_payload(status="paper_trade_still_open", generated_at="2026-05-28T00:00:00+00:00"),
        tracker_payload(status="paper_trade_closed_tp", exit_reason="paper_tp_hit", r_multiple=1.5),
    ]
    tracker_dirs: list[Path] = []
    for index, payload in enumerate(payloads):
        tracker_dir = tmp_path / f"tracker_{index + 1}"
        tracker_dirs.append(tracker_dir)
        if missing_tracker_index != index:
            write_tracker_dir(tracker_dir, payload)
    argv = [
        "--run-id",
        "unit_paper_cycle_summary",
        "--demo-strategy-config",
        str(config_path),
        "--demo-strategy-spec-dir",
        str(spec_dir),
        "--paper-signal-logger-readiness-dir",
        str(readiness_dir),
        "--numeric-tercile-thresholds-dir",
        str(thresholds_dir),
        "--paper-signal-logger-dir",
        str(signal_dir),
        "--paper-trade-tracker-dirs",
        *[str(path) for path in tracker_dirs],
        "--output-dir",
        str(tmp_path / "out"),
        "--overwrite",
    ]
    return summary.build_parser().parse_args(argv)


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        summary.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = summary.build_outputs(make_args(tmp_path))

    assert outputs["summary"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_completed_tp_cycle_produces_tp_status(tmp_path: Path) -> None:
    outputs = summary.build_outputs(make_args(tmp_path))
    manifest = read_json(outputs["manifest"])

    assert manifest["final_cycle_status"] == "paper_cycle_completed_tp"
    assert manifest["final_exit_reason"] == "paper_tp_hit"
    assert manifest["final_R_multiple"] == pytest.approx(1.5)


def test_completed_sl_cycle_produces_sl_status(tmp_path: Path) -> None:
    outputs = summary.build_outputs(
        make_args(
            tmp_path,
            tracker_payloads=[
                tracker_payload(status="paper_trade_closed_sl", exit_reason="paper_sl_hit", r_multiple=-1.0),
            ],
        )
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["final_cycle_status"] == "paper_cycle_completed_sl"
    assert manifest["final_exit_reason"] == "paper_sl_hit"


def test_completed_timeout_cycle_produces_timeout_status(tmp_path: Path) -> None:
    outputs = summary.build_outputs(
        make_args(
            tmp_path,
            tracker_payloads=[
                tracker_payload(status="paper_trade_closed_timeout", exit_reason="paper_timeout", r_multiple=0.1, bars_elapsed=10),
            ],
        )
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["final_cycle_status"] == "paper_cycle_completed_timeout"
    assert manifest["final_exit_reason"] == "paper_timeout"


def test_still_open_tracker_produces_still_open_status(tmp_path: Path) -> None:
    outputs = summary.build_outputs(
        make_args(tmp_path, tracker_payloads=[tracker_payload(status="paper_trade_still_open")])
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["final_cycle_status"] == "paper_cycle_still_open"
    assert manifest["has_open_paper_trade_after"] is True


def test_missing_signal_logger_artifact_creates_incomplete_warning(tmp_path: Path) -> None:
    outputs = summary.build_outputs(make_args(tmp_path, missing_signal_logger=True))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["final_cycle_status"] == "paper_cycle_incomplete"
    assert any(warning["warning_code"] == "paper_signal_logger_missing" for warning in warnings)


def test_missing_tracker_artifact_creates_incomplete_cycle(tmp_path: Path) -> None:
    outputs = summary.build_outputs(make_args(tmp_path, missing_tracker_index=1))
    manifest = read_json(outputs["manifest"])
    warnings = read_csv(outputs["warnings"])

    assert manifest["final_cycle_status"] == "paper_cycle_incomplete"
    assert any(warning["warning_code"] == "paper_trade_tracker_2_missing" for warning in warnings)


def test_tracker_rows_are_linked_by_open_signal_id(tmp_path: Path) -> None:
    outputs = summary.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["summary"])
    tracker_rows = [row for row in rows if row["row_type"] == "trade_tracker"]

    assert tracker_rows
    assert all(row["open_signal_id"] == OPEN_SIGNAL_ID for row in tracker_rows)
    assert all(row["caveat"] == "linked_by_open_signal_id" for row in tracker_rows)


def test_final_status_uses_latest_tracker_by_generated_at(tmp_path: Path) -> None:
    outputs = summary.build_outputs(
        make_args(
            tmp_path,
            tracker_payloads=[
                tracker_payload(
                    status="paper_trade_closed_sl",
                    exit_reason="paper_sl_hit",
                    r_multiple=-1.0,
                    generated_at="2026-05-28T02:00:00+00:00",
                ),
                tracker_payload(
                    status="paper_trade_closed_tp",
                    exit_reason="paper_tp_hit",
                    r_multiple=1.5,
                    generated_at="2026-05-28T01:00:00+00:00",
                ),
            ],
        )
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["final_cycle_status"] == "paper_cycle_completed_sl"


def test_final_status_falls_back_to_provided_order_when_generated_at_missing(tmp_path: Path) -> None:
    outputs = summary.build_outputs(
        make_args(
            tmp_path,
            tracker_payloads=[
                tracker_payload(
                    status="paper_trade_closed_tp",
                    exit_reason="paper_tp_hit",
                    r_multiple=1.5,
                    generated_at="",
                ),
                tracker_payload(
                    status="paper_trade_closed_timeout",
                    exit_reason="paper_timeout",
                    r_multiple=0.1,
                    bars_elapsed=10,
                    generated_at="",
                ),
            ],
        )
    )
    manifest = read_json(outputs["manifest"])

    assert manifest["final_cycle_status"] == "paper_cycle_completed_timeout"


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    outputs = summary.build_outputs(make_args(tmp_path, missing_tracker_index=1))
    rows = read_csv(outputs["summary"])
    warnings = read_csv(outputs["warnings"])
    manifest = read_json(outputs["manifest"])

    assert manifest["cycle_row_count"] == len(rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(
        1 for warning in warnings if warning["blocking_warning"].lower() == "true"
    )
    assert manifest["missing_source_artifact_count"] >= 1


def test_report_includes_one_cycle_and_no_statistical_conclusion_caveats(tmp_path: Path) -> None:
    outputs = summary.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "One-cycle-only summary. This is not statistical evidence." in report
    assert "One paper cycle only." in report
    assert "Not candidate approval." in report


def test_report_includes_no_connection_order_db_mutation_caveats(tmp_path: Path) -> None:
    outputs = summary.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No MT5, broker/API, or external connection was performed." in report
    assert "No order execution was performed." in report
    assert "No database mutation was performed." in report
    assert "No data generation or feature refresh was performed." in report


def test_no_child_heavy_commands_are_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("child command should not be executed")

    monkeypatch.setattr("subprocess.run", fail_if_called)
    summary.build_outputs(make_args(tmp_path))
