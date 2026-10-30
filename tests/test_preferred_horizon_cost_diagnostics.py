import argparse
import csv
import re
from pathlib import Path

import pytest

import scripts.run_preferred_horizon_cost_diagnostics as diagnostics
from scripts.run_preferred_horizon_cost_diagnostics import (
    DECISION_CANDIDATES,
    DECISION_CLOSED,
    DECISION_NO_TESTED,
    DECISION_REVIEW,
    MATRIX_FIELDNAMES,
    branch_id_for,
    branch_decision_from_metrics,
    build_branch_matrix,
    child_commands,
    run_preferred_horizon_cost_diagnostics,
    write_csv,
    write_report,
)


def write_cost_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"symbols":{"EURUSD":{"point_size":0.00001},"GBPUSD":{"point_size":0.00001},"USDJPY":{"point_size":0.001},"XAUUSD":{"point_size":0.01}}}',
        encoding="utf-8",
    )


def args(tmp_path: Path) -> argparse.Namespace:
    p50 = tmp_path / "config" / "p50.local.json"
    p75 = tmp_path / "config" / "p75.local.json"
    p90 = tmp_path / "config" / "p90.local.json"
    for path in (p50, p75, p90):
        write_cost_config(path)
    return argparse.Namespace(
        timeframe="M15",
        horizons=[5, 10, 20],
        groups=["fx", "xauusd"],
        cost_profiles=["p50", "p75", "p90"],
        cost_config_p50=p50,
        cost_config_p75=p75,
        cost_config_p90=p90,
        skip_missing_cost_configs=False,
        target_family="preferred_2atr_1atr_hit_first",
        tp_atr=2.0,
        sl_atr=1.0,
        atr_column="atr_20",
        same_bar_policy="stop_first",
        return_mode="net",
        continue_on_error=False,
        dry_run=True,
        summarize_existing_run_id=None,
        diagnose_zero_tested_run_id=None,
        run_id="matrix_unit_run",
        output_root=tmp_path / "reports",
        python_executable="python",
        overwrite=False,
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def write_matrix_summary_for_branch(run_args: argparse.Namespace, branch) -> dict[str, object]:
    output_dir = run_args.output_root / branch.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    row = diagnostics.matrix_row_for_branch(
        branch,
        status="completed",
        notes="No tested combinations.",
        decision=DECISION_NO_TESTED,
    )
    for direction in ("long", "short"):
        row[f"{direction}_input_combinations"] = 0
        row[f"{direction}_tested_combinations"] = 0
        row[f"{direction}_scartare_count"] = 0
        row[f"{direction}_da_approfondire_count"] = 0
        row[f"{direction}_candidata_count"] = 0
    write_csv(output_dir / "matrix_summary.csv", [row], MATRIX_FIELDNAMES)
    return row


def write_minimal_child_outputs(
    matrix_row: dict[str, object],
    direction: str,
    *,
    preferred_rows: int = 1,
    cost_rows: list[dict[str, object]] | None = None,
    shortlist_rows: int = 1,
    primary_candidates: int = 1,
    secondary_candidates: int = 1,
    combinations_built: int = 1,
    combination_detail_rows: int = 0,
    tp_sl_summary_rows: int = 0,
) -> None:
    gross_path = diagnostics.preferred_feature_summary_path_from_row(matrix_row, direction, "gross")
    net_path = diagnostics.preferred_feature_summary_path_from_row(matrix_row, direction, "net")
    preferred_payload = [{"symbol": "EURUSD"} for _ in range(preferred_rows)]
    write_csv(gross_path, preferred_payload, ["symbol"])
    write_csv(net_path, preferred_payload, ["symbol"])

    cost_path = diagnostics.preferred_cost_comparison_path_from_row(matrix_row, direction)
    cost_payload = cost_rows
    if cost_payload is None:
        cost_payload = [{"gross_positive": "true", "net_positive": "false", "cost_erased_edge": "true"}]
    write_csv(cost_path, cost_payload, ["gross_positive", "net_positive", "cost_erased_edge"])

    candidate_path = diagnostics.candidate_diagnostics_path_from_row(matrix_row, direction)
    candidate_payload = [
        {
            "direction": direction,
            "symbol": "ALL",
            "input_rows_loaded": len(cost_payload),
            "rows_after_net_filter": sum(
                1
                for row in cost_payload
                if str(row.get("gross_positive")).lower() == "true"
                and (
                    str(row.get("cost_erased_edge")).lower() == "true"
                    or str(row.get("net_positive")).lower() != "true"
                )
            ),
            "rows_after_shortlist_filter": shortlist_rows,
            "primary_candidates": primary_candidates,
            "secondary_candidates": secondary_candidates,
            "combinations_built": combinations_built,
            "skipped_rows": 0,
            "notes": "unit test diagnostics",
        }
    ]
    write_csv(
        candidate_path,
        candidate_payload,
        [
            "direction",
            "symbol",
            "input_rows_loaded",
            "rows_after_net_filter",
            "rows_after_shortlist_filter",
            "primary_candidates",
            "secondary_candidates",
            "combinations_built",
            "skipped_rows",
            "notes",
        ],
    )

    combination_rows = [{"combination_id": f"combo_{index}"} for index in range(combination_detail_rows)]
    write_csv(diagnostics.combination_detail_path_from_row(matrix_row, direction), combination_rows, ["combination_id"])
    write_csv(diagnostics.combination_skipped_path_from_row(matrix_row, direction), [], ["skip_reason"])
    summary_rows = [{"classification": "SCARTARE"} for _ in range(tp_sl_summary_rows)]
    write_csv(diagnostics.tp_sl_summary_path_from_row(matrix_row, direction), summary_rows, ["classification"])
    write_csv(diagnostics.tp_sl_skipped_path_from_row(matrix_row, direction), [], ["skip_reason"])


def test_matrix_branch_generation_for_fx_and_xauusd_groups(tmp_path: Path) -> None:
    run_args = args(tmp_path)

    branches = build_branch_matrix(run_args, "matrix_unit_run")

    assert len(branches) == 18
    assert sum(1 for branch in branches if branch.group_name == "fx") == 9
    assert sum(1 for branch in branches if branch.group_name == "xauusd") == 9
    assert all(branch.symbols == ("EURUSD", "GBPUSD", "USDJPY") for branch in branches if branch.group_name == "fx")
    assert all(branch.symbols == ("XAUUSD",) for branch in branches if branch.group_name == "xauusd")


def test_horizon_cost_combinations_are_generated_correctly(tmp_path: Path) -> None:
    run_args = args(tmp_path)

    branches = build_branch_matrix(run_args, "matrix_unit_run")
    combos = {(branch.group_name, branch.horizon, branch.cost_profile) for branch in branches}

    for group in ("fx", "xauusd"):
        for horizon in (5, 10, 20):
            for profile in ("p50", "p75", "p90"):
                assert (group, horizon, profile) in combos


def test_branch_ids_are_deterministic_and_readable() -> None:
    assert (
        branch_id_for(
            timeframe="M15",
            horizon=5,
            tp_atr=2.0,
            sl_atr=1.0,
            cost_profile="p50",
            group_name="fx",
        )
        == "M15_h5_preferred_2atr_1atr_p50_fx"
    )


def test_one_and_half_atr_target_family_infers_branch_targets_and_commands(tmp_path: Path) -> None:
    run_args = args(tmp_path)
    run_args.target_family = "preferred_1_5atr_1atr_hit_first"
    run_args.horizons = [5]
    run_args.groups = ["fx"]
    run_args.cost_profiles = ["p75"]

    branch = build_branch_matrix(run_args, "matrix_unit_run")[0]
    commands = child_commands(branch, run_args, tmp_path / "reports" / "matrix_unit_run")
    command_text = " ".join(" ".join(command.command) for command in commands)
    outcome = diagnostics.branch_outcome_command(
        branch,
        run_args,
        tmp_path / "reports" / "matrix_unit_run",
        DECISION_CLOSED,
    )

    assert branch.branch_id == "M15_h5_preferred_1_5atr_1atr_p75_fx"
    assert branch.target_family == "preferred_1_5atr_1atr_hit_first"
    assert branch.target_long == "long_tp_1_5atr_sl_1atr_hit_first_5"
    assert branch.target_short == "short_tp_1_5atr_sl_1atr_hit_first_5"
    assert "--tp-atr 1.5 --sl-atr 1.0" in command_text
    assert "--input-root" in command_text
    assert "preferred_feature_hypotheses\\preferred_1_5atr_1atr_hit_first" in command_text
    assert "preferred_1_5atr_1atr_hit_first" in outcome.command


def test_missing_cost_config_fails_clearly(tmp_path: Path) -> None:
    run_args = args(tmp_path)
    run_args.cost_config_p90 = tmp_path / "missing_p90.local.json"

    with pytest.raises(FileNotFoundError, match="Missing required cost config files"):
        run_preferred_horizon_cost_diagnostics(run_args)


def test_missing_cost_config_can_be_skipped(tmp_path: Path) -> None:
    run_args = args(tmp_path)
    run_args.cost_config_p90 = tmp_path / "missing_p90.local.json"
    run_args.skip_missing_cost_configs = True

    outputs = run_preferred_horizon_cost_diagnostics(run_args)
    summary_rows = read_csv_rows(outputs["matrix_summary"])
    skipped_rows = read_csv_rows(outputs["skipped_branches"])

    assert len(summary_rows) == 12
    assert len(skipped_rows) == 6
    assert {row["reason"] for row in skipped_rows} == {"missing_cost_config"}


def test_dry_run_writes_matrix_summary_report_and_skipped_csv(tmp_path: Path) -> None:
    run_args = args(tmp_path)

    outputs = run_preferred_horizon_cost_diagnostics(run_args)

    assert outputs["matrix_summary"].exists()
    assert outputs["matrix_report"].exists()
    assert outputs["skipped_branches"].exists()
    assert outputs["branch_manifest"].exists()

    summary_rows = read_csv_rows(outputs["matrix_summary"])
    assert len(summary_rows) == 18
    assert {row["status"] for row in summary_rows} == {"dry_run_planned"}
    assert {row["branch_decision"] for row in summary_rows} == {"PLANNED"}


def test_child_command_construction_has_no_live_terms_and_no_tp_sl_optimization(tmp_path: Path) -> None:
    run_args = args(tmp_path)
    branch = build_branch_matrix(run_args, "matrix_unit_run")[0]

    commands = child_commands(branch, run_args, tmp_path / "reports" / "matrix_unit_run")
    command_text = " ".join(" ".join(command.command) for command in commands).lower()

    blocked = [
        "order_" + "send",
        "place_" + "order",
        "execute_" + "trade",
        "open_" + "position",
        "close_" + "position",
        "trade_" + "send",
        "position_" + "open",
        "position_" + "close",
    ]
    assert all(term not in command_text for term in blocked)
    assert "--tp-atr 2.0 --sl-atr 1.0" in command_text
    assert "optimiz" not in command_text


def test_report_contains_warning_and_avoids_blocked_language(tmp_path: Path) -> None:
    run_args = args(tmp_path)

    outputs = run_preferred_horizon_cost_diagnostics(run_args)
    report_text = outputs["matrix_report"].read_text(encoding="utf-8")
    lower_report = report_text.lower()

    assert "## Research-only warning" in report_text
    assert "No TP/SL optimization." in report_text
    assert "No new features." in report_text
    assert "No new combinations searched" in report_text
    assert "buy" not in lower_report
    assert "sell" not in lower_report
    assert "live signal" not in lower_report


def test_zero_tested_rows_produces_no_tested_decision() -> None:
    row = {
        "long_tested_combinations": 0,
        "short_tested_combinations": 0,
        "long_scartare_count": 0,
        "short_scartare_count": 0,
        "long_da_approfondire_count": 0,
        "short_da_approfondire_count": 0,
        "long_candidata_count": 0,
        "short_candidata_count": 0,
    }

    assert branch_decision_from_metrics(row) == DECISION_NO_TESTED


def test_closed_no_survivor_requires_tested_rows_and_all_scartare() -> None:
    row = {
        "long_tested_combinations": 2,
        "short_tested_combinations": 1,
        "long_scartare_count": 2,
        "short_scartare_count": 1,
        "long_da_approfondire_count": 0,
        "short_da_approfondire_count": 0,
        "long_candidata_count": 0,
        "short_candidata_count": 0,
    }

    assert branch_decision_from_metrics(row) == DECISION_CLOSED


def test_needs_review_requires_da_approfondire_count() -> None:
    row = {
        "long_tested_combinations": 2,
        "short_tested_combinations": 0,
        "long_scartare_count": 1,
        "short_scartare_count": 0,
        "long_da_approfondire_count": 1,
        "short_da_approfondire_count": 0,
        "long_candidata_count": 0,
        "short_candidata_count": 0,
    }

    assert branch_decision_from_metrics(row) == DECISION_REVIEW


def test_candidates_found_requires_candidate_count() -> None:
    row = {
        "long_tested_combinations": 2,
        "short_tested_combinations": 0,
        "long_scartare_count": 1,
        "short_scartare_count": 0,
        "long_da_approfondire_count": 1,
        "short_da_approfondire_count": 0,
        "long_candidata_count": 1,
        "short_candidata_count": 0,
    }

    assert branch_decision_from_metrics(row) == DECISION_CANDIDATES


def test_zero_tested_rows_do_not_appear_under_da_approfondire(tmp_path: Path) -> None:
    run_args = args(tmp_path)
    branch = build_branch_matrix(run_args, "matrix_unit_run")[0]
    matrix_rows = [
        {
            "branch_id": branch.branch_id,
            "status": "completed",
            "branch_decision": DECISION_NO_TESTED,
            "long_tested_combinations": 0,
            "short_tested_combinations": 0,
            "best_long_mean_R": "",
            "best_short_mean_R": "",
            "notes": "No tested combinations.",
        },
        {
            "branch_id": "review_branch",
            "status": "completed",
            "branch_decision": DECISION_REVIEW,
            "long_tested_combinations": 1,
            "short_tested_combinations": 0,
            "best_long_mean_R": "0.01",
            "best_short_mean_R": "",
            "notes": "Completed child diagnostics.",
        },
    ]
    report_path = tmp_path / "matrix_report.md"

    write_report(
        report_path,
        run_id="matrix_unit_run",
        args=run_args,
        branches=[branch],
        matrix_rows=matrix_rows,
        skipped_rows=[],
    )
    report_text = report_path.read_text(encoding="utf-8")
    da_section = report_text.split("## Branches with any DA_APPROFONDIRE", 1)[1].split(
        "## Branches with zero tested combinations",
        1,
    )[0]
    zero_section = report_text.split("## Branches with zero tested combinations", 1)[1].split(
        "## Branches fully closed",
        1,
    )[0]

    assert branch.branch_id not in da_section
    assert "review_branch" in da_section
    assert branch.branch_id in zero_section


def test_summarize_existing_run_rebuilds_summary_without_child_execution(tmp_path: Path) -> None:
    run_args = args(tmp_path)
    run_id = "existing_matrix_run"
    output_dir = run_args.output_root / run_id
    output_dir.mkdir(parents=True)
    branch = build_branch_matrix(run_args, run_id)[0]
    old_row = {
        "run_id": run_id,
        "branch_id": branch.branch_id,
        "group_name": branch.group_name,
        "symbols": " ".join(branch.symbols),
        "timeframe": branch.timeframe,
        "horizon": branch.horizon,
        "cost_profile": branch.cost_profile,
        "cost_config": str(branch.cost_config),
        "tp_atr": branch.tp_atr,
        "sl_atr": branch.sl_atr,
        "atr_column": branch.atr_column,
        "same_bar_policy": branch.same_bar_policy,
        "target_long": branch.target_long,
        "target_short": branch.target_short,
        "preferred_feature_backtest_run_id_gross": branch.gross_run_id,
        "preferred_feature_backtest_run_id_net": branch.net_run_id,
        "cost_mode_comparison_path_long": "",
        "cost_mode_comparison_path_short": "",
        "combination_run_id": branch.combination_run_id,
        "tp_sl_path_run_id_long": branch.tp_sl_run_id,
        "tp_sl_path_run_id_short": branch.tp_sl_run_id,
        "branch_outcome_run_id": branch.branch_outcome_run_id,
        "long_input_combinations": 0,
        "long_tested_combinations": 0,
        "long_scartare_count": 0,
        "long_da_approfondire_count": 0,
        "long_candidata_count": 0,
        "short_input_combinations": 0,
        "short_tested_combinations": 0,
        "short_scartare_count": 0,
        "short_da_approfondire_count": 0,
        "short_candidata_count": 0,
        "best_long_mean_R": "",
        "best_long_profit_factor_R": "",
        "best_short_mean_R": "",
        "best_short_profit_factor_R": "",
        "branch_decision": DECISION_REVIEW,
        "status": "completed",
        "notes": "Completed child diagnostics.",
    }
    write_csv(output_dir / "matrix_summary.csv", [old_row], MATRIX_FIELDNAMES)

    summarize_args = args(tmp_path)
    summarize_args.summarize_existing_run_id = run_id

    def fail_runner(_command):
        raise AssertionError("summarize-existing-run must not execute child commands")

    outputs = run_preferred_horizon_cost_diagnostics(summarize_args, runner=fail_runner)
    summary_rows = read_csv_rows(outputs["matrix_summary"])
    report_text = outputs["matrix_report"].read_text(encoding="utf-8")

    assert outputs["skipped_branches"].exists()
    assert summary_rows[0]["branch_decision"] == DECISION_NO_TESTED
    assert "No tested combinations." in summary_rows[0]["notes"]
    assert "## Branches with zero tested combinations" in report_text
    assert branch.branch_id in report_text


def test_zero_tested_diagnostics_detect_empty_combination_detail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "BASE_DIR", tmp_path)
    run_args = args(tmp_path)
    run_args.diagnose_zero_tested_run_id = run_args.run_id
    branch = build_branch_matrix(run_args, run_args.run_id)[0]
    matrix_row = write_matrix_summary_for_branch(run_args, branch)
    write_minimal_child_outputs(matrix_row, "long", combination_detail_rows=0)
    write_minimal_child_outputs(matrix_row, "short", combination_detail_rows=0)

    outputs = run_preferred_horizon_cost_diagnostics(run_args)
    rows = read_csv_rows(outputs["zero_tested_diagnostics"])
    long_row = next(row for row in rows if row["direction"] == "long")

    assert outputs["zero_tested_report"].exists()
    assert long_row["zero_tested_reason"] == "empty_combination_detail_csv"


def test_zero_tested_diagnostics_detect_no_preferred_shortlist_rows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "BASE_DIR", tmp_path)
    run_args = args(tmp_path)
    run_args.diagnose_zero_tested_run_id = run_args.run_id
    branch = build_branch_matrix(run_args, run_args.run_id)[0]
    matrix_row = write_matrix_summary_for_branch(run_args, branch)
    write_minimal_child_outputs(matrix_row, "long", shortlist_rows=0, primary_candidates=0, secondary_candidates=0)
    write_minimal_child_outputs(matrix_row, "short", shortlist_rows=0, primary_candidates=0, secondary_candidates=0)

    outputs = run_preferred_horizon_cost_diagnostics(run_args)
    rows = read_csv_rows(outputs["zero_tested_diagnostics"])
    long_row = next(row for row in rows if row["direction"] == "long")

    assert long_row["zero_tested_reason"] == "no_preferred_shortlist_rows"


@pytest.mark.parametrize(
    ("primary_candidates", "secondary_candidates", "expected_reason"),
    [
        (0, 1, "no_primary_family_candidates"),
        (1, 0, "no_secondary_family_candidates"),
    ],
)
def test_zero_tested_diagnostics_detect_missing_candidate_families(
    tmp_path: Path,
    monkeypatch,
    primary_candidates: int,
    secondary_candidates: int,
    expected_reason: str,
) -> None:
    monkeypatch.setattr(diagnostics, "BASE_DIR", tmp_path)
    run_args = args(tmp_path)
    run_args.run_id = f"matrix_{expected_reason}"
    run_args.diagnose_zero_tested_run_id = run_args.run_id
    branch = build_branch_matrix(run_args, run_args.run_id)[0]
    matrix_row = write_matrix_summary_for_branch(run_args, branch)
    write_minimal_child_outputs(
        matrix_row,
        "long",
        shortlist_rows=1,
        primary_candidates=primary_candidates,
        secondary_candidates=secondary_candidates,
        combinations_built=0,
    )
    write_minimal_child_outputs(
        matrix_row,
        "short",
        shortlist_rows=1,
        primary_candidates=primary_candidates,
        secondary_candidates=secondary_candidates,
        combinations_built=0,
    )

    outputs = run_preferred_horizon_cost_diagnostics(run_args)
    rows = read_csv_rows(outputs["zero_tested_diagnostics"])
    long_row = next(row for row in rows if row["direction"] == "long")

    assert long_row["zero_tested_reason"] == expected_reason


def test_zero_tested_diagnostics_detect_missing_child_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "BASE_DIR", tmp_path)
    run_args = args(tmp_path)
    run_args.diagnose_zero_tested_run_id = run_args.run_id
    branch = build_branch_matrix(run_args, run_args.run_id)[0]
    write_matrix_summary_for_branch(run_args, branch)

    outputs = run_preferred_horizon_cost_diagnostics(run_args)
    rows = read_csv_rows(outputs["zero_tested_diagnostics"])
    long_row = next(row for row in rows if row["direction"] == "long")

    assert long_row["zero_tested_reason"] == "missing_child_output"
    assert "missing outputs" in long_row["diagnostic_notes"]


def test_zero_tested_report_contains_warning_and_avoids_blocked_language(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagnostics, "BASE_DIR", tmp_path)
    run_args = args(tmp_path)
    run_args.diagnose_zero_tested_run_id = run_args.run_id
    branch = build_branch_matrix(run_args, run_args.run_id)[0]
    matrix_row = write_matrix_summary_for_branch(run_args, branch)
    write_minimal_child_outputs(matrix_row, "long", preferred_rows=0)
    write_minimal_child_outputs(matrix_row, "short", preferred_rows=0)

    outputs = run_preferred_horizon_cost_diagnostics(run_args)
    report_text = outputs["zero_tested_report"].read_text(encoding="utf-8")
    lower_report = report_text.lower()

    assert "## Research-only warning" in report_text
    assert "No TP/SL optimization." in report_text
    assert "buy" not in lower_report
    assert "sell" not in lower_report
    assert "live signal" not in lower_report


def test_no_metatrader5_or_live_api_imports_are_introduced() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_preferred_horizon_cost_diagnostics.py"
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
