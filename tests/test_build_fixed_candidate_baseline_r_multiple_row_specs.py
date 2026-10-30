from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_baseline_r_multiple_row_specs as specs_module


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_fake_stress_script(path: Path, *, include_condition: bool = True, complete: bool = True) -> None:
    options = [
        "--symbol",
        "--direction",
        "--timeframe",
        "--horizon",
        "--target-family",
        "--regime-column",
        "--regime-value",
        "--tp-atr",
        "--sl-atr",
        "--atr-column",
        "--same-bar-policy",
        "--db-path",
        "--cost-config",
        "--stress-cost-config",
        "--stress-spread-policy",
        "--run-id",
        "--output-root",
        "--overwrite",
    ]
    if include_condition:
        options.append("--condition")
    if not complete:
        options.remove("--stress-cost-config")
    path.write_text(
        "\n".join(
            [
                "import argparse",
                "parser = argparse.ArgumentParser()",
                *(f"parser.add_argument('{option}')" for option in options),
            ]
        ),
        encoding="utf-8",
    )


def make_args(tmp_path: Path, *, stress_script: Path | None = None) -> object:
    script = stress_script or tmp_path / "validate_regime_candidate_stress.py"
    if stress_script is None:
        write_fake_stress_script(script)
    return specs_module.parse_args(
        [
            "--run-id",
            "unit_r_specs",
            "--output-dir",
            str(tmp_path / "out"),
            "--stress-script",
            str(script),
            "--db-path",
            "data/unit.db",
            "--p75-cost-config",
            "config/p75.json",
            "--p90-cost-config",
            "config/p90.json",
            "--overwrite",
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        specs_module.parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = specs_module.build_outputs(make_args(tmp_path))

    assert outputs["row_specs"].exists()
    assert outputs["command_plan"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_broad_regime_spec_has_no_condition_to_apply(tmp_path: Path) -> None:
    outputs = specs_module.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["row_specs"])
    broad = next(row for row in rows if row["baseline_type"] == "broad_regime_baseline")
    command = next(
        row for row in read_csv(outputs["command_plan"]) if row["baseline_type"] == "broad_regime_baseline"
    )

    assert broad["spec_status"] == "spec_ready"
    assert broad["condition_to_apply"] == ""
    assert "--condition" not in command["manual_command"]


def test_single_filter_specs_apply_only_their_filter(tmp_path: Path) -> None:
    outputs = specs_module.build_outputs(make_args(tmp_path))
    rows = {row["baseline_type"]: row for row in read_csv(outputs["row_specs"])}
    commands = {row["baseline_type"]: row["manual_command"] for row in read_csv(outputs["command_plan"])}

    assert rows["single_filter_a"]["condition_to_apply"] == (
        "numeric_tercile:close_to_ma_fast_atr_20:high_tercile"
    )
    assert rows["single_filter_b"]["condition_to_apply"] == (
        "numeric_tercile:tick_volume_percentile_100:mid_tercile"
    )
    assert (
        "--condition numeric_tercile:close_to_ma_fast_atr_20:high_tercile"
        in commands["single_filter_a"]
    )
    assert (
        "--condition numeric_tercile:tick_volume_percentile_100:mid_tercile"
        in commands["single_filter_b"]
    )
    assert "AND" not in commands["single_filter_a"]
    assert "AND" not in commands["single_filter_b"]


def test_exact_feature_condition_is_metadata_only(tmp_path: Path) -> None:
    outputs = specs_module.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["row_specs"])
    commands = read_csv(outputs["command_plan"])

    assert all(
        row["exact_feature_condition_metadata"]
        == (
            "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
            "numeric_tercile:tick_volume_percentile_100:mid_tercile"
        )
        for row in rows
    )
    assert all("high_tercile AND numeric_tercile:tick_volume_percentile_100" not in row["manual_command"] for row in commands)


def test_command_plan_uses_stress_validator_and_cost_pair(tmp_path: Path) -> None:
    outputs = specs_module.build_outputs(make_args(tmp_path))
    commands = read_csv(outputs["command_plan"])

    assert len(commands) == 3
    assert all(row["command_status"] == "planned_manual_command" for row in commands)
    assert all("validate_regime_candidate_stress.py" in row["manual_command"] for row in commands)
    assert all("--cost-config config/p75.json" in row["manual_command"] for row in commands)
    assert all("--stress-cost-config config/p90.json" in row["manual_command"] for row in commands)
    assert all("--stress-spread-policy max_row_or_fallback" in row["manual_command"] for row in commands)
    assert all("--horizon 10" in row["manual_command"] for row in commands)
    assert all("--same-bar-policy stop_first" in row["manual_command"] for row in commands)


def test_fallback_needs_manual_mapping_when_stress_cli_lacks_required_flags(tmp_path: Path) -> None:
    stress_script = tmp_path / "incomplete_stress.py"
    write_fake_stress_script(stress_script, complete=False)

    outputs = specs_module.build_outputs(make_args(tmp_path, stress_script=stress_script))
    specs = read_csv(outputs["row_specs"])
    commands = read_csv(outputs["command_plan"])
    warnings = read_csv(outputs["warnings"])

    assert {row["spec_status"] for row in specs} == {"needs_manual_mapping"}
    assert {row["command_status"] for row in commands} == {"needs_manual_mapping"}
    assert all(row["manual_command"] == "" for row in commands)
    assert {row["warning_code"] for row in warnings} == {"stress_cli_mapping_incomplete"}


def test_manifest_counts_match_specs_and_warnings(tmp_path: Path) -> None:
    outputs = specs_module.build_outputs(make_args(tmp_path))
    specs = read_csv(outputs["row_specs"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["row_spec_count"] == len(specs)
    assert manifest["command_plan_row_count"] == len(read_csv(outputs["command_plan"]))
    assert manifest["spec_ready_count"] == 3
    assert manifest["planned_manual_command_count"] == 3
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == 0
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_states_command_plan_only_and_no_decision(tmp_path: Path) -> None:
    outputs = specs_module.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "artifact-only, and command-plan-only" in report
    assert "No generated commands were executed" in report
    assert "No stress validation, baseline diagnostics, or backtests were run" in report
    assert "No candidate-quality evaluation" in report
    assert "trading decision" in report
    assert "exact two-filter feature condition is preserved as metadata only" in report


def test_unsupported_baseline_type_is_reported_without_command(tmp_path: Path) -> None:
    args = specs_module.parse_args(
        [
            "--run-id",
            "unit_r_specs",
            "--output-dir",
            str(tmp_path / "out"),
            "--baseline-types",
            "broad_regime_baseline",
            "unknown_baseline",
            "--stress-script",
            str(tmp_path / "validate_regime_candidate_stress.py"),
            "--overwrite",
        ]
    )
    write_fake_stress_script(Path(args.stress_script))

    outputs = specs_module.build_outputs(args)
    specs = {row["baseline_type"]: row for row in read_csv(outputs["row_specs"])}
    commands = {row["baseline_type"]: row for row in read_csv(outputs["command_plan"])}

    assert specs["broad_regime_baseline"]["spec_status"] == "spec_ready"
    assert specs["unknown_baseline"]["spec_status"] == "unsupported_baseline_type"
    assert commands["unknown_baseline"]["manual_command"] == ""
