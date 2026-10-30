from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_demo_would_signal_fixture_cycle as fixture
from scripts import run_fixed_candidate_demo_shadow_signal_once as shadow


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def canonical_registry(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "gbpusd_short_h10_1_5_off_hours",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "short",
        "spread_unit": "broker_points",
        "max_spread_points": 15.0,
    }
    payload.update(overrides)
    return payload


def make_args(
    tmp_path: Path,
    *,
    registry_payload: dict[str, object] | None = None,
    output_name: str = "out",
    overwrite: bool = True,
    entry_reference_price: float = 1.34600,
    atr_20: float = 0.00042,
    spread: float = 3.0,
    source_mode: str = "synthetic_fixture",
) -> object:
    registry_path = write_json(tmp_path / "registry.json", registry_payload or canonical_registry())
    argv = [
        "--run-id",
        "unit_would_signal_fixture",
        "--canonical-registry",
        str(registry_path),
        "--source-mode",
        source_mode,
        "--fixture-time-server",
        "2026-06-01 02:00:00",
        "--entry-reference-price",
        str(entry_reference_price),
        "--atr-20",
        str(atr_20),
        "--spread",
        str(spread),
        "--output-dir",
        str(tmp_path / output_name),
    ]
    if overwrite:
        argv.append("--overwrite")
    return fixture.build_parser().parse_args(argv)


def build_valid_fixture(tmp_path: Path) -> dict[str, Path]:
    return fixture.build_outputs(make_args(tmp_path))


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        fixture.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = build_valid_fixture(tmp_path)

    for path in outputs.values():
        assert path.exists(), path


def test_parent_cycle_status_is_completed_would_signal(tmp_path: Path) -> None:
    outputs = build_valid_fixture(tmp_path)
    manifest = read_json(outputs["parent_manifest"])

    assert manifest["cycle_status"] == "demo_no_order_cycle_completed_would_signal"
    assert manifest["fixture_status"] == "would_signal_fixture_available"
    assert manifest["child_command_count"] == 0
    assert manifest["mt5_bar_import_child_executed"] is False
    assert manifest["price_feature_generation_child_executed"] is False
    assert manifest["no_order_dry_run_child_executed"] is False


def test_child_decision_status_is_would_signal(tmp_path: Path) -> None:
    outputs = build_valid_fixture(tmp_path)
    child_manifest = read_json(outputs["child_manifest"])
    decision_rows = read_csv(outputs["child_decision"])

    assert child_manifest["decision_label"] == "would_signal"
    assert child_manifest["dry_run_status"] == "demo_no_order_dry_run_would_signal"
    assert decision_rows[0]["decision_label"] == "would_signal"
    assert decision_rows[0]["dry_run_status"] == "demo_no_order_dry_run_would_signal"


def test_tp_sl_preview_for_short_is_correct(tmp_path: Path) -> None:
    outputs = fixture.build_outputs(make_args(tmp_path, entry_reference_price=1.34600, atr_20=0.00042))
    child_manifest = read_json(outputs["child_manifest"])

    assert child_manifest["entry_reference_price"] == pytest.approx(1.34600)
    assert child_manifest["tp_price_preview"] == pytest.approx(1.34537)
    assert child_manifest["sl_price_preview"] == pytest.approx(1.34642)
    assert child_manifest["same_bar_policy"] == "stop_first"
    assert child_manifest["horizon_bars"] == 10


def test_no_order_flags_are_present_true(tmp_path: Path) -> None:
    outputs = build_valid_fixture(tmp_path)
    parent_manifest = read_json(outputs["parent_manifest"])
    child_manifest = read_json(outputs["child_manifest"])
    no_order_rows = read_csv(outputs["child_no_order_evidence"])
    flags = [
        "no_order_execution_performed",
        "no_order_request_constructed",
        "no_order_send_called",
        "no_order_check_called",
        "no_order_calc_margin_called",
        "no_order_calc_profit_called",
        "no_demo_broker_approval_performed",
        "no_trading_decision_performed",
    ]

    for flag in flags:
        assert parent_manifest[flag] is True
        assert child_manifest[flag] is True
    assert parent_manifest["no_order_boundary_confirmed"] is True
    assert parent_manifest["missing_no_order_flag_count"] == 0
    assert parent_manifest["unsafe_no_order_flag_count"] == 0
    assert no_order_rows[0]["no_order_execution_performed"] == "true"
    assert no_order_rows[0]["no_order_request_constructed"] == "true"


def test_latest_child_manifest_path_points_to_existing_file(tmp_path: Path) -> None:
    outputs = build_valid_fixture(tmp_path)
    parent_manifest = read_json(outputs["parent_manifest"])
    child_path = Path(str(parent_manifest["latest_child_manifest_path"]))

    assert child_path.is_absolute()
    assert child_path.exists()
    assert child_path == outputs["child_manifest"].resolve()


def test_synthetic_caveats_are_in_manifest_and_report(tmp_path: Path) -> None:
    outputs = build_valid_fixture(tmp_path)
    manifest = read_json(outputs["parent_manifest"])
    report = outputs["parent_report"].read_text(encoding="utf-8")

    assert manifest["fixture_not_live_market_data"] is True
    assert manifest["fixture_not_backtest_result"] is True
    assert manifest["fixture_not_actionable"] is True
    assert "fixture-only synthetic" in report
    assert "not live market data" in report
    assert "not actionable evidence" in report
    assert "downstream shadow_signal_detected" in report


def test_noncanonical_registry_blocks(tmp_path: Path) -> None:
    outputs = fixture.build_outputs(make_args(tmp_path, registry_payload=canonical_registry(max_spread_points=2.5)))
    manifest = read_json(outputs["parent_manifest"])
    warnings = read_csv(outputs["parent_warnings"])

    assert manifest["fixture_status"] == "blocked_by_config_boundary"
    assert manifest["cycle_status"] == "blocked_by_config_boundary"
    assert any(row["warning_code"] == "canonical_registry_boundary_mismatch" for row in warnings)


@pytest.mark.parametrize(
    ("entry_reference_price", "atr_20", "warning_code"),
    [
        (0.0, 0.00042, "entry_reference_price_invalid"),
        (1.34600, 0.0, "atr_20_invalid"),
    ],
)
def test_invalid_entry_or_atr_blocks(
    tmp_path: Path,
    entry_reference_price: float,
    atr_20: float,
    warning_code: str,
) -> None:
    outputs = fixture.build_outputs(make_args(tmp_path, entry_reference_price=entry_reference_price, atr_20=atr_20))
    manifest = read_json(outputs["parent_manifest"])
    warnings = read_csv(outputs["parent_warnings"])

    assert manifest["fixture_status"] == "blocked_invalid_fixture_inputs"
    assert any(row["warning_code"] == warning_code for row in warnings)


def test_spread_above_15_blocks_fixture(tmp_path: Path) -> None:
    outputs = fixture.build_outputs(make_args(tmp_path, spread=20.0))
    manifest = read_json(outputs["parent_manifest"])
    warnings = read_csv(outputs["parent_warnings"])

    assert manifest["fixture_status"] == "blocked_invalid_fixture_inputs"
    assert manifest["child_spread_within_gate"] is False
    assert any(row["warning_code"] == "spread_not_within_canonical_fixture_gate" for row in warnings)


def test_existing_output_without_overwrite_blocks(tmp_path: Path) -> None:
    fixture.build_outputs(make_args(tmp_path, output_name="out", overwrite=True))

    with pytest.raises(FileExistsError):
        fixture.build_outputs(make_args(tmp_path, output_name="out", overwrite=False))


def test_generated_fixture_is_consumed_by_shadow_wrapper_existing_cycle_mode(tmp_path: Path) -> None:
    registry_path = write_json(tmp_path / "registry.json", canonical_registry())
    fixture_outputs = fixture.build_outputs(
        fixture.build_parser().parse_args(
            [
                "--run-id",
                "unit_would_signal_fixture",
                "--canonical-registry",
                str(registry_path),
                "--output-dir",
                str(tmp_path / "fixture"),
                "--overwrite",
            ]
        )
    )
    shadow_args = shadow.build_parser().parse_args(
        [
            "--run-id",
            "unit_shadow_from_fixture",
            "--canonical-registry",
            str(registry_path),
            "--existing-no-order-cycle-dir",
            str(fixture_outputs["parent_manifest"].parent),
            "--output-dir",
            str(tmp_path / "shadow"),
            "--overwrite",
        ]
    )
    shadow_outputs = shadow.build_outputs(shadow_args)
    shadow_manifest = read_json(shadow_outputs["manifest"])
    review_packet = read_json(shadow_outputs["review_packet"])

    assert shadow_manifest["shadow_status"] == "shadow_signal_detected"
    assert shadow_manifest["manual_review_required"] is True
    assert review_packet["signal_evidence"]["decision_label"] == "would_signal"
    assert review_packet["manual_review_required"] is True


def test_static_source_avoids_live_import_db_and_backtest_modules() -> None:
    source = Path("scripts/build_fixed_candidate_demo_would_signal_fixture_cycle.py").read_text(encoding="utf-8")
    forbidden = [
        "import MetaTrader5",
        "import sqlite3",
        "subprocess",
        "copy_rates",
        "run_fixed_candidate_fixed_rule_replay_backtest",
        "import_price_bars",
        "generate_price_features",
    ]

    for token in forbidden:
        assert token not in source


def test_static_source_has_no_forbidden_order_function_signatures() -> None:
    source = Path("scripts/build_fixed_candidate_demo_would_signal_fixture_cycle.py").read_text(encoding="utf-8")
    forbidden = [
        "MetaTrader5",
        "mt5.initialize",
        "order_send(",
        "order_check(",
        "order_calc_margin(",
        "order_calc_profit(",
        "positions_get(",
        "orders_get(",
        "history_orders_get(",
        "history_deals_get(",
    ]

    for token in forbidden:
        assert token not in source


def test_static_source_has_no_scheduler_markers() -> None:
    source = Path("scripts/build_fixed_candidate_demo_would_signal_fixture_cycle.py").read_text(encoding="utf-8")
    forbidden = [
        "Task Scheduler",
        "schtasks",
        "while True",
        "APScheduler",
        "threading.Timer",
    ]

    for token in forbidden:
        assert token not in source


def test_no_heavy_commands_are_executed_in_tests(tmp_path: Path) -> None:
    outputs = build_valid_fixture(tmp_path)
    child_commands = read_csv(outputs["parent_child_commands"])
    child_results = read_csv(outputs["parent_child_results"])

    assert child_commands == []
    assert child_results == []
