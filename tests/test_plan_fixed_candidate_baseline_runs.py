from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pytest

from scripts import plan_fixed_candidate_baseline_runs as plan_module
from scripts import run_candidate_baseline_diagnostics as diagnostics_module


MATRIX_FIELDS = [
    "run_id",
    "candidate_id",
    "symbol",
    "direction",
    "timeframe",
    "target_horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "feature_condition",
    "baseline_type",
    "baseline_filter",
    "cost_profile",
    "cost_config_path",
    "tp_atr",
    "sl_atr",
    "same_bar_policy",
    "candidate_scope",
    "artifact_status",
    "artifact_source",
    "planned_source",
    "trade_count",
    "mean_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "yearly_positive_ratio",
    "timeout_rate",
    "tp_hit_rate",
    "sl_hit_rate",
    "warning_code",
    "blocking_warning",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def matrix_row(
    baseline_type: str,
    cost_profile: str,
    artifact_status: str,
    *,
    baseline_filter: str = "",
) -> dict[str, object]:
    return {
        "run_id": "matrix",
        "candidate_id": "gbpusd_short_m15_h10",
        "symbol": "GBPUSD",
        "direction": "short",
        "timeframe": "M15",
        "target_horizon": "10",
        "target_family": "preferred_1_5atr_1atr_hit_first",
        "regime_column": "hour_session",
        "regime_value": "Off_hours",
        "feature_condition": "filter_a AND filter_b",
        "baseline_type": baseline_type,
        "baseline_filter": baseline_filter,
        "cost_profile": cost_profile,
        "cost_config_path": f"config/{cost_profile}.json",
        "tp_atr": "1.5",
        "sl_atr": "1.0",
        "same_bar_policy": "stop_first",
        "candidate_scope": "exact_feature_combination",
        "artifact_status": artifact_status,
        "artifact_source": "",
        "planned_source": "",
        "trade_count": "",
        "mean_R": "",
        "profit_factor_R": "",
        "cumulative_R": "",
        "max_drawdown_R": "",
        "monthly_positive_ratio": "",
        "quarterly_positive_ratio": "",
        "yearly_positive_ratio": "",
        "timeout_rate": "",
        "tp_hit_rate": "",
        "sl_hit_rate": "",
        "warning_code": "",
        "blocking_warning": "false",
    }


def write_matrix(path: Path) -> None:
    rows = [
        matrix_row("exact_rule", "p75", "available", baseline_filter="filter_a AND filter_b"),
        matrix_row("exact_rule", "p90", "available", baseline_filter="filter_a AND filter_b"),
        matrix_row("broad_regime_baseline", "p75", "planned_not_run"),
        matrix_row("broad_regime_baseline", "p90", "planned_not_run"),
        matrix_row("single_filter_a", "p75", "planned_not_run", baseline_filter="filter_a"),
        matrix_row("single_filter_a", "p90", "planned_not_run", baseline_filter="filter_a"),
        matrix_row("single_filter_b", "p75", "planned_not_run", baseline_filter="filter_b"),
        matrix_row("single_filter_b", "p90", "planned_not_run", baseline_filter="filter_b"),
        matrix_row("no_feature_off_hours", "p75", "not_applicable"),
        matrix_row("no_feature_off_hours", "p90", "not_applicable"),
    ]
    write_csv(path, MATRIX_FIELDS, rows)


def write_numeric_tercile_matrix(path: Path) -> None:
    rows = [
        matrix_row("broad_regime_baseline", "p75", "planned_not_run"),
        matrix_row(
            "single_filter_a",
            "p75",
            "planned_not_run",
            baseline_filter="numeric_tercile:close_to_ma_fast_atr_20:high_tercile",
        ),
        matrix_row(
            "single_filter_b",
            "p90",
            "planned_not_run",
            baseline_filter="numeric_tercile:tick_volume_percentile_100:mid_tercile",
        ),
    ]
    write_csv(path, MATRIX_FIELDS, rows)


def write_run_plan(path: Path) -> None:
    rows = [
        {
            "run_id": "unit",
            "source_matrix_csv": "matrix.csv",
            "baseline_type": "broad_regime_baseline",
            "baseline_filter": "",
            "cost_profile": "p75",
            "cost_config_path": "config/p75.json",
            "symbol": "GBPUSD",
            "direction": "short",
            "timeframe": "M15",
            "target_horizon": "10",
            "target_family": "preferred_1_5atr_1atr_hit_first",
            "regime_column": "hour_session",
            "regime_value": "Off_hours",
            "tp_atr": "1.5",
            "sl_atr": "1.0",
            "db_path": "data/unit.db",
            "baseline_script": "scripts/run_candidate_baseline_diagnostics.py",
            "python_executable": "python",
            "manual_command": 'python scripts/run_candidate_baseline_diagnostics.py --baseline-type broad_regime_baseline --baseline-filter "" --cost-config config/p75.json',
            "expected_output_dir": str(path.parent / "broad_p75"),
            "command_status": "planned_manual_command",
            "command_warning_code": "",
            "blocking_warning": "false",
        },
        {
            "run_id": "unit",
            "source_matrix_csv": "matrix.csv",
            "baseline_type": "single_filter_a",
            "baseline_filter": "filter_a",
            "cost_profile": "p90",
            "cost_config_path": "config/p90.json",
            "symbol": "GBPUSD",
            "direction": "short",
            "timeframe": "M15",
            "target_horizon": "10",
            "target_family": "preferred_1_5atr_1atr_hit_first",
            "regime_column": "hour_session",
            "regime_value": "Off_hours",
            "tp_atr": "1.5",
            "sl_atr": "1.0",
            "db_path": "data/unit.db",
            "baseline_script": "scripts/run_candidate_baseline_diagnostics.py",
            "python_executable": "python",
            "manual_command": "python scripts/run_candidate_baseline_diagnostics.py --baseline-type single_filter_a --cost-config config/p90.json",
            "expected_output_dir": str(path.parent / "single_a_p90"),
            "command_status": "planned_manual_command",
            "command_warning_code": "",
            "blocking_warning": "false",
        },
        {
            "run_id": "unit",
            "source_matrix_csv": "matrix.csv",
            "baseline_type": "exact_rule",
            "baseline_filter": "filter_a AND filter_b",
            "cost_profile": "p75",
            "cost_config_path": "config/p75.json",
            "symbol": "GBPUSD",
            "direction": "short",
            "timeframe": "M15",
            "target_horizon": "10",
            "target_family": "preferred_1_5atr_1atr_hit_first",
            "regime_column": "hour_session",
            "regime_value": "Off_hours",
            "tp_atr": "1.5",
            "sl_atr": "1.0",
            "db_path": "data/unit.db",
            "baseline_script": "scripts/run_candidate_baseline_diagnostics.py",
            "python_executable": "python",
            "manual_command": "",
            "expected_output_dir": str(path.parent / "exact_p75"),
            "command_status": "skipped_available",
            "command_warning_code": "",
            "blocking_warning": "false",
        },
    ]
    write_csv(path, plan_module.PLAN_FIELDNAMES, rows)


def write_baseline_script_without_direct_mapping(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "import argparse",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--run-id')",
                "parser.add_argument('--direction')",
                "parser.add_argument('--symbols', nargs='+')",
                "parser.add_argument('--timeframe')",
                "parser.add_argument('--target-horizon')",
                "parser.add_argument('--db-path')",
                "parser.add_argument('--output-dir')",
                "parser.add_argument('--cost-config')",
            ]
        ),
        encoding="utf-8",
    )


def write_baseline_script_with_direct_mapping(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "import argparse",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--run-id')",
                "parser.add_argument('--direction')",
                "parser.add_argument('--symbols', nargs='+')",
                "parser.add_argument('--timeframe')",
                "parser.add_argument('--target-horizon')",
                "parser.add_argument('--target-family')",
                "parser.add_argument('--db-path')",
                "parser.add_argument('--output-dir')",
                "parser.add_argument('--cost-config')",
                "parser.add_argument('--baseline-type')",
                "parser.add_argument('--baseline-filter')",
                "parser.add_argument('--feature-condition')",
                "parser.add_argument('--regime-column')",
                "parser.add_argument('--regime-value')",
                "parser.add_argument('--allow-numeric-tercile-baseline-filter')",
            ]
        ),
        encoding="utf-8",
    )


def make_args(tmp_path: Path, *, direct_mapping: bool = False) -> object:
    matrix_csv = tmp_path / "matrix.csv"
    baseline_script = tmp_path / "run_candidate_baseline_diagnostics.py"
    write_matrix(matrix_csv)
    if direct_mapping:
        write_baseline_script_with_direct_mapping(baseline_script)
    else:
        write_baseline_script_without_direct_mapping(baseline_script)
    return plan_module.build_parser().parse_args(
        [
            "--run-id",
            "unit",
            "--matrix-csv",
            str(matrix_csv),
            "--output-dir",
            str(tmp_path / "out"),
            "--baseline-script",
            str(baseline_script),
            "--db-path",
            "data/unit.db",
        ]
    )


def make_numeric_args(tmp_path: Path) -> object:
    matrix_csv = tmp_path / "numeric_matrix.csv"
    baseline_script = tmp_path / "run_candidate_baseline_diagnostics.py"
    write_numeric_tercile_matrix(matrix_csv)
    write_baseline_script_with_direct_mapping(baseline_script)
    return plan_module.build_parser().parse_args(
        [
            "--run-id",
            "unit",
            "--matrix-csv",
            str(matrix_csv),
            "--output-dir",
            str(tmp_path / "out"),
            "--baseline-script",
            str(baseline_script),
            "--db-path",
            "data/unit.db",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        plan_module.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_candidate_baseline_diagnostics_help_includes_direct_mapping_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        diagnostics_module.parse_args(["--help"])

    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--baseline-type" in help_text
    assert "--baseline-filter" in help_text
    assert "--feature-condition" in help_text
    assert "--regime-column" in help_text
    assert "--regime-value" in help_text
    assert "--target-family" in help_text
    assert "--allow-numeric-tercile-baseline-filter" in help_text
    assert "not applied as an active baseline filter" in " ".join(help_text.split())


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path))

    assert outputs["run_plan"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_print_commands_only_prints_planned_manual_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_plan_csv = tmp_path / "run_plan.csv"
    write_run_plan(run_plan_csv)
    args = plan_module.build_parser().parse_args(
        ["--print-commands-only", "--run-plan-csv", str(run_plan_csv)]
    )

    commands = plan_module.print_planned_manual_commands(args)
    output_lines = capsys.readouterr().out.strip().splitlines()

    assert commands == output_lines
    assert len(output_lines) == 2
    assert all("run_candidate_baseline_diagnostics.py" in line for line in output_lines)
    assert all("skipped_available" not in line for line in output_lines)
    assert all('--baseline-filter ""' not in line for line in output_lines)


def test_print_commands_only_filters_by_baseline_type_and_cost_profile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_plan_csv = tmp_path / "run_plan.csv"
    write_run_plan(run_plan_csv)
    args = plan_module.build_parser().parse_args(
        [
            "--print-commands-only",
            "--run-plan-csv",
            str(run_plan_csv),
            "--baseline-type",
            "single_filter_a",
            "--cost-profile",
            "p90",
        ]
    )

    commands = plan_module.print_planned_manual_commands(args)
    output = capsys.readouterr().out

    assert commands == [
        "python scripts/run_candidate_baseline_diagnostics.py --baseline-type single_filter_a --cost-config config/p90.json"
    ]
    assert "single_filter_a" in output
    assert "broad_regime_baseline" not in output


def test_print_commands_only_skips_existing_output_dirs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_plan_csv = tmp_path / "run_plan.csv"
    write_run_plan(run_plan_csv)
    (tmp_path / "broad_p75").mkdir()
    args = plan_module.build_parser().parse_args(
        [
            "--print-commands-only",
            "--run-plan-csv",
            str(run_plan_csv),
            "--skip-existing-output-dirs",
        ]
    )

    commands = plan_module.print_planned_manual_commands(args)
    output = capsys.readouterr().out

    assert commands == [
        "python scripts/run_candidate_baseline_diagnostics.py --baseline-type single_filter_a --cost-config config/p90.json"
    ]
    assert "single_filter_a" in output
    assert "broad_regime_baseline" not in output


def test_generated_broad_regime_commands_omit_empty_baseline_filter(tmp_path: Path) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path, direct_mapping=True))
    rows = [
        row
        for row in read_csv(outputs["run_plan"])
        if row["baseline_type"] == "broad_regime_baseline"
    ]

    assert len(rows) == 2
    assert all(row["command_status"] == "planned_manual_command" for row in rows)
    assert all("--baseline-filter" not in row["manual_command"] for row in rows)


def test_generated_single_filter_commands_keep_baseline_filter(tmp_path: Path) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path, direct_mapping=True))
    rows = [
        row
        for row in read_csv(outputs["run_plan"])
        if row["baseline_type"] in {"single_filter_a", "single_filter_b"}
    ]

    assert len(rows) == 4
    assert all(row["command_status"] == "planned_manual_command" for row in rows)
    assert all("--baseline-filter" in row["manual_command"] for row in rows)
    assert any("--baseline-filter filter_a" in row["manual_command"] for row in rows)
    assert any("--baseline-filter filter_b" in row["manual_command"] for row in rows)


def test_generated_numeric_tercile_single_filter_commands_include_explicit_opt_in(tmp_path: Path) -> None:
    outputs = plan_module.build_outputs(make_numeric_args(tmp_path))
    rows = read_csv(outputs["run_plan"])
    broad = next(row for row in rows if row["baseline_type"] == "broad_regime_baseline")
    single_rows = [row for row in rows if row["baseline_type"] in {"single_filter_a", "single_filter_b"}]

    assert "--allow-numeric-tercile-baseline-filter" not in broad["manual_command"]
    assert "--baseline-filter" not in broad["manual_command"]
    assert len(single_rows) == 2
    assert all("--baseline-filter numeric_tercile:" in row["manual_command"] for row in single_rows)
    assert all("--allow-numeric-tercile-baseline-filter" in row["manual_command"] for row in single_rows)


def test_only_planned_not_run_rows_are_selected_for_mapping(tmp_path: Path) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["run_plan"])
    selected = [row for row in rows if row["command_status"] == "needs_manual_mapping"]

    assert len(selected) == 6
    assert {row["baseline_type"] for row in selected} == {
        "broad_regime_baseline",
        "single_filter_a",
        "single_filter_b",
    }


def test_available_and_not_applicable_rows_are_skipped(tmp_path: Path) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["run_plan"])

    exact_rows = [row for row in rows if row["baseline_type"] == "exact_rule"]
    no_feature_rows = [row for row in rows if row["baseline_type"] == "no_feature_off_hours"]
    assert {row["command_status"] for row in exact_rows} == {"skipped_available"}
    assert {row["command_status"] for row in no_feature_rows} == {"skipped_not_applicable"}


@pytest.mark.parametrize("baseline_type", ["broad_regime_baseline", "single_filter_a", "single_filter_b"])
def test_planned_baseline_rows_are_marked_needs_manual_mapping(tmp_path: Path, baseline_type: str) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path))
    rows = [
        row
        for row in read_csv(outputs["run_plan"])
        if row["baseline_type"] == baseline_type
    ]

    assert {row["cost_profile"] for row in rows} == {"p75", "p90"}
    assert {row["command_status"] for row in rows} == {"needs_manual_mapping"}
    assert {row["command_warning_code"] for row in rows} == {"baseline_cli_mapping_incomplete"}
    assert all(row["manual_command"] == "" for row in rows)


@pytest.mark.parametrize("baseline_type", ["broad_regime_baseline", "single_filter_a", "single_filter_b"])
def test_planned_rows_become_manual_commands_when_mapping_is_supported(tmp_path: Path, baseline_type: str) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path, direct_mapping=True))
    rows = [
        row
        for row in read_csv(outputs["run_plan"])
        if row["baseline_type"] == baseline_type
    ]

    assert {row["cost_profile"] for row in rows} == {"p75", "p90"}
    assert {row["command_status"] for row in rows} == {"planned_manual_command"}
    assert all("--baseline-type" in row["manual_command"] for row in rows)
    assert all("--regime-column hour_session" in row["manual_command"] for row in rows)
    assert all("--regime-value Off_hours" in row["manual_command"] for row in rows)
    assert all("--cost-config config/" in row["manual_command"] for row in rows)
    assert all("--db-path data/unit.db" in row["manual_command"] for row in rows)
    assert all("--symbols GBPUSD" in row["manual_command"] for row in rows)
    assert all("--direction short" in row["manual_command"] for row in rows)
    assert all("--timeframe M15" in row["manual_command"] for row in rows)
    assert all("--target-horizon 10" in row["manual_command"] for row in rows)
    assert all("--target-family preferred_1_5atr_1atr_hit_first" in row["manual_command"] for row in rows)
    assert all('--feature-condition "filter_a AND filter_b"' in row["manual_command"] for row in rows)
    if baseline_type.startswith("single_filter"):
        assert all("--baseline-filter filter_" in row["manual_command"] for row in rows)


def test_direct_broad_regime_baseline_does_not_apply_exact_feature_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"symbol": "GBPUSD", "hour_session": "Off_hours"},
        {"symbol": "GBPUSD", "hour_session": "Off_hours"},
        {"symbol": "GBPUSD", "hour_session": "London"},
    ]
    condition_calls: list[str] = []

    def fail_apply_condition(_rows: list[dict[str, object]], key: str) -> list[dict[str, object]]:
        condition_calls.append(key)
        raise AssertionError(f"unexpected active condition: {key}")

    def fake_metrics(selected_rows: list[dict[str, object]], **_kwargs: object) -> dict[str, object]:
        return {"trades_count": len(selected_rows), "mean_return": len(selected_rows)}

    monkeypatch.setattr(diagnostics_module, "apply_condition", fail_apply_condition)
    monkeypatch.setattr(diagnostics_module, "selected_return_metrics", fake_metrics)

    args = diagnostics_module.parse_args(
        [
            "--run-id",
            "unit",
            "--symbols",
            "GBPUSD",
            "--direction",
            "short",
            "--baseline-type",
            "broad_regime_baseline",
            "--feature-condition",
            "filter_a AND filter_b",
            "--regime-column",
            "hour_session",
            "--regime-value",
            "Off_hours",
        ]
    )

    detail, summary, skipped = diagnostics_module.process_direct_fixed_row_candidate(
        args,
        universe_rows=rows,
        return_column="future_return_10",
        direction="short",
        cost_config={},
        cost_mode="none",
        return_mode="gross",
    )

    assert condition_calls == []
    assert skipped == []
    assert detail[0]["baseline_key"] == "hour_session=Off_hours"
    assert detail[0]["baseline_trades_count"] == 2
    assert detail[0]["candidate_trades_count"] is None
    assert summary[0]["trades_count"] == 2
    assert summary[0]["combination_key"] == "filter_a AND filter_b"
    assert "metadata only" in summary[0]["primary_reason"]


def test_fixed_row_diagnostic_only_is_counted_in_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"symbol": "GBPUSD", "hour_session": "Off_hours"},
        {"symbol": "GBPUSD", "hour_session": "Off_hours"},
    ]

    def fail_apply_condition(_rows: list[dict[str, object]], key: str) -> list[dict[str, object]]:
        raise AssertionError(f"unexpected active condition: {key}")

    def fake_metrics(selected_rows: list[dict[str, object]], **_kwargs: object) -> dict[str, object]:
        return {"trades_count": len(selected_rows), "mean_return": len(selected_rows)}

    monkeypatch.setattr(diagnostics_module, "apply_condition", fail_apply_condition)
    monkeypatch.setattr(diagnostics_module, "selected_return_metrics", fake_metrics)
    args = diagnostics_module.parse_args(
        [
            "--run-id",
            "unit",
            "--symbols",
            "GBPUSD",
            "--direction",
            "short",
            "--baseline-type",
            "broad_regime_baseline",
            "--feature-condition",
            "filter_a AND filter_b",
            "--regime-column",
            "hour_session",
            "--regime-value",
            "Off_hours",
        ]
    )

    detail, summary, skipped = diagnostics_module.process_direct_fixed_row_candidate(
        args,
        universe_rows=rows,
        return_column="future_return_10",
        direction="short",
        cost_config={},
        cost_mode="none",
        return_mode="gross",
    )
    report = diagnostics_module.build_markdown_report(
        run_id="unit",
        direction="short",
        cost_mode="none",
        return_mode="gross",
        symbols=["GBPUSD"],
        timeframe="M15",
        target_horizon=10,
        random_runs=0,
        min_trades=100,
        detail_rows=detail,
        summary_rows=summary,
        skipped_rows=skipped,
        random_baseline_path=tmp_path / "missing_random_baseline.csv",
    )

    assert "- comparisons: `1`" in report
    assert "| fixed_row_diagnostic_only | 1 |" in report
    assert "| skipped | 0 |" in report
    assert "`fixed_row_direct` mode is a row-level baseline diagnostic" in report
    assert "not an incremental-value classification" in report
    assert "does not make a candidate-quality decision" in report


def test_direct_single_filter_baseline_applies_only_baseline_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "id": "a"},
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "id": "b"},
        {"symbol": "GBPUSD", "hour_session": "London", "id": "c"},
    ]
    validated_keys: list[str] = []
    applied_keys: list[str] = []

    def fake_validate(
        key: str,
        _rows: list[dict[str, object]],
        *,
        allow_numeric_tercile: bool,
    ) -> None:
        validated_keys.append(key)
        assert allow_numeric_tercile is False
        return None

    def fake_apply_condition(
        selected_rows: list[dict[str, object]],
        key: str,
        *,
        allow_numeric_tercile: bool,
    ) -> list[dict[str, object]]:
        applied_keys.append(key)
        assert key == "filter_a"
        assert allow_numeric_tercile is False
        return selected_rows[:1]

    def fake_metrics(selected_rows: list[dict[str, object]], **_kwargs: object) -> dict[str, object]:
        return {"trades_count": len(selected_rows), "mean_return": len(selected_rows)}

    monkeypatch.setattr(diagnostics_module, "validate_direct_baseline_filter_or_skip", fake_validate)
    monkeypatch.setattr(diagnostics_module, "apply_condition_with_options", fake_apply_condition)
    monkeypatch.setattr(diagnostics_module, "selected_return_metrics", fake_metrics)

    args = diagnostics_module.parse_args(
        [
            "--run-id",
            "unit",
            "--symbols",
            "GBPUSD",
            "--direction",
            "short",
            "--baseline-type",
            "single_filter_a",
            "--baseline-filter",
            "filter_a",
            "--feature-condition",
            "filter_a AND filter_b",
            "--regime-column",
            "hour_session",
            "--regime-value",
            "Off_hours",
        ]
    )

    detail, summary, skipped = diagnostics_module.process_direct_fixed_row_candidate(
        args,
        universe_rows=rows,
        return_column="future_return_10",
        direction="short",
        cost_config={},
        cost_mode="none",
        return_mode="gross",
    )

    assert validated_keys == ["filter_a"]
    assert applied_keys == ["filter_a"]
    assert skipped == []
    assert detail[0]["baseline_key"] == "filter_a"
    assert detail[0]["baseline_trades_count"] == 1
    assert detail[0]["candidate_trades_count"] is None
    assert summary[0]["trades_count"] == 1
    assert summary[0]["combination_key"] == "filter_a AND filter_b"


def test_direct_numeric_tercile_baseline_filter_is_skipped_by_default() -> None:
    rows = [
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "feature_x": 1.0},
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "feature_x": 2.0},
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "feature_x": 3.0},
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "feature_x": 4.0},
    ]
    args = diagnostics_module.parse_args(
        [
            "--run-id",
            "unit",
            "--symbols",
            "GBPUSD",
            "--direction",
            "short",
            "--baseline-type",
            "single_filter_a",
            "--baseline-filter",
            "numeric_tercile:feature_x:high_tercile",
            "--feature-condition",
            "metadata_only",
            "--regime-column",
            "hour_session",
            "--regime-value",
            "Off_hours",
        ]
    )

    detail, summary, skipped = diagnostics_module.process_direct_fixed_row_candidate(
        args,
        universe_rows=rows,
        return_column="future_return_10",
        direction="short",
        cost_config={},
        cost_mode="none",
        return_mode="gross",
    )

    assert detail == []
    assert summary == []
    assert skipped[0]["skip_reason"] == "baseline_filter_numeric_tercile_skipped_to_avoid_temporal_leakage"


def test_direct_numeric_tercile_baseline_filter_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "feature_x": 1.0},
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "feature_x": 2.0},
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "feature_x": 3.0},
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "feature_x": 4.0},
        {"symbol": "GBPUSD", "hour_session": "London", "feature_x": 100.0},
    ]

    def fake_metrics(selected_rows: list[dict[str, object]], **_kwargs: object) -> dict[str, object]:
        return {"trades_count": len(selected_rows), "mean_return": len(selected_rows)}

    monkeypatch.setattr(diagnostics_module, "selected_return_metrics", fake_metrics)
    args = diagnostics_module.parse_args(
        [
            "--run-id",
            "unit",
            "--symbols",
            "GBPUSD",
            "--direction",
            "short",
            "--baseline-type",
            "single_filter_a",
            "--baseline-filter",
            "numeric_tercile:feature_x:high_tercile",
            "--feature-condition",
            "metadata_only",
            "--regime-column",
            "hour_session",
            "--regime-value",
            "Off_hours",
            "--allow-numeric-tercile-baseline-filter",
        ]
    )

    detail, summary, skipped = diagnostics_module.process_direct_fixed_row_candidate(
        args,
        universe_rows=rows,
        return_column="future_return_10",
        direction="short",
        cost_config={},
        cost_mode="none",
        return_mode="gross",
    )

    assert skipped == []
    assert detail[0]["baseline_key"] == "numeric_tercile:feature_x:high_tercile"
    assert detail[0]["baseline_trades_count"] == 1
    assert detail[0]["candidate_trades_count"] is None
    assert summary[0]["trades_count"] == 1
    assert summary[0]["combination_key"] == "metadata_only"


def test_direct_numeric_tercile_opt_in_does_not_allow_raw_price_feature() -> None:
    rows = [
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "close": 1.0},
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "close": 2.0},
        {"symbol": "GBPUSD", "hour_session": "Off_hours", "close": 3.0},
    ]
    args = diagnostics_module.parse_args(
        [
            "--run-id",
            "unit",
            "--symbols",
            "GBPUSD",
            "--direction",
            "short",
            "--baseline-type",
            "single_filter_a",
            "--baseline-filter",
            "numeric_tercile:close:high_tercile",
            "--feature-condition",
            "metadata_only",
            "--regime-column",
            "hour_session",
            "--regime-value",
            "Off_hours",
            "--allow-numeric-tercile-baseline-filter",
        ]
    )

    detail, summary, skipped = diagnostics_module.process_direct_fixed_row_candidate(
        args,
        universe_rows=rows,
        return_column="future_return_10",
        direction="short",
        cost_config={},
        cost_mode="none",
        return_mode="gross",
    )

    assert detail == []
    assert summary == []
    assert skipped[0]["skip_reason"] == "baseline_filter_raw_price_level_excluded"


def cost_config_with_fallback_spread(points: float) -> dict[str, object]:
    return {
        "default": {
            "commission_bps_round_trip": 0.0,
            "fallback_spread_points": None,
            "slippage_bps_round_trip": 0.0,
        },
        "symbols": {
            "GBPUSD": {
                "fallback_spread_points": points,
                "point_size": 0.00001,
            }
        },
    }


def direct_broad_regime_args() -> object:
    return diagnostics_module.parse_args(
        [
            "--run-id",
            "unit",
            "--symbols",
            "GBPUSD",
            "--direction",
            "short",
            "--baseline-type",
            "broad_regime_baseline",
            "--feature-condition",
            "metadata_only",
            "--regime-column",
            "hour_session",
            "--regime-value",
            "Off_hours",
        ]
    )


def test_direct_fixed_row_net_metrics_use_cost_config_when_fallback_spread_is_effective() -> None:
    rows = [
        {
            "symbol": "GBPUSD",
            "hour_session": "Off_hours",
            "future_return_10": "-0.0010",
            "close": "1.2500",
            "time_server": "2024-01-31 00:00:00",
        },
        {
            "symbol": "GBPUSD",
            "hour_session": "Off_hours",
            "future_return_10": "-0.0020",
            "close": "1.2500",
            "time_server": "2024-02-29 00:00:00",
        },
    ]

    low_cost_detail, _low_summary, low_skipped = diagnostics_module.process_direct_fixed_row_candidate(
        direct_broad_regime_args(),
        universe_rows=rows,
        return_column="future_return_10",
        direction="short",
        cost_config=cost_config_with_fallback_spread(1.0),
        cost_mode="estimated",
        return_mode="net",
    )
    high_cost_detail, _high_summary, high_skipped = diagnostics_module.process_direct_fixed_row_candidate(
        direct_broad_regime_args(),
        universe_rows=rows,
        return_column="future_return_10",
        direction="short",
        cost_config=cost_config_with_fallback_spread(5.0),
        cost_mode="estimated",
        return_mode="net",
    )

    assert low_skipped == []
    assert high_skipped == []
    assert float(high_cost_detail[0]["baseline_mean_return"]) < float(low_cost_detail[0]["baseline_mean_return"])
    assert float(high_cost_detail[0]["baseline_cumulative_return"]) < float(low_cost_detail[0]["baseline_cumulative_return"])


def test_direct_fixed_row_fallback_spread_difference_has_no_effect_when_row_spread_is_present() -> None:
    rows = [
        {
            "symbol": "GBPUSD",
            "hour_session": "Off_hours",
            "future_return_10": "-0.0010",
            "close": "1.2500",
            "spread": "2.0",
            "time_server": "2024-01-31 00:00:00",
        },
        {
            "symbol": "GBPUSD",
            "hour_session": "Off_hours",
            "future_return_10": "-0.0020",
            "close": "1.2500",
            "spread": "2.0",
            "time_server": "2024-02-29 00:00:00",
        },
    ]

    low_cost_detail, _low_summary, low_skipped = diagnostics_module.process_direct_fixed_row_candidate(
        direct_broad_regime_args(),
        universe_rows=rows,
        return_column="future_return_10",
        direction="short",
        cost_config=cost_config_with_fallback_spread(1.0),
        cost_mode="estimated",
        return_mode="net",
    )
    high_cost_detail, _high_summary, high_skipped = diagnostics_module.process_direct_fixed_row_candidate(
        direct_broad_regime_args(),
        universe_rows=rows,
        return_column="future_return_10",
        direction="short",
        cost_config=cost_config_with_fallback_spread(5.0),
        cost_mode="estimated",
        return_mode="net",
    )

    assert low_skipped == []
    assert high_skipped == []
    assert math.isclose(
        float(high_cost_detail[0]["baseline_mean_return"]),
        float(low_cost_detail[0]["baseline_mean_return"]),
        rel_tol=1e-12,
    )
    assert math.isclose(
        float(high_cost_detail[0]["baseline_cumulative_return"]),
        float(low_cost_detail[0]["baseline_cumulative_return"]),
        rel_tol=1e-12,
    )


def test_supported_mapping_manifest_counts_are_consistent(tmp_path: Path) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path, direct_mapping=True))
    rows = read_csv(outputs["run_plan"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["planned_manual_command_count"] == 6
    assert manifest["needs_manual_mapping_count"] == 0
    assert manifest["skipped_row_count"] == 4
    assert manifest["warnings_count"] == len(warnings) == 0
    assert manifest["run_plan_row_count"] == len(rows)


def test_manifest_counts_match_run_plan_and_warnings(tmp_path: Path) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["run_plan"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["run_plan_row_count"] == len(rows)
    assert manifest["planned_manual_command_count"] == sum(row["command_status"] == "planned_manual_command" for row in rows)
    assert manifest["needs_manual_mapping_count"] == sum(row["command_status"] == "needs_manual_mapping" for row in rows)
    assert manifest["skipped_row_count"] == sum(row["command_status"].startswith("skipped_") for row in rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_baseline_diagnostics_run"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_states_no_child_scripts_diagnostics_or_backtests(tmp_path: Path) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "No child scripts were executed" in report
    assert "No baseline diagnostics were executed" in report
    assert "No backtests were run" in report
    assert "No candidate-quality evaluation" in report
    assert "trading decision was made" in report


def test_no_child_scripts_are_executed_in_tests(tmp_path: Path) -> None:
    outputs = plan_module.build_outputs(make_args(tmp_path))

    assert len(read_csv(outputs["run_plan"])) == 10
    assert not (tmp_path / "out" / "manual_baseline_outputs").exists()
