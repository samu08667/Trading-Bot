from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import build_fixed_candidate_deeper_walkforward_run_specs as wf_specs


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_fake_stress_script(path: Path, *, complete: bool = True) -> None:
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
        "--condition",
        "--walk-forward-splits",
        "--overwrite",
    ]
    if not complete:
        options.remove("--walk-forward-splits")
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


def write_packet_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "fixed_candidate_research_review_packet_manifest.json").write_text("{}", encoding="utf-8")


def make_args(tmp_path: Path, *, include_broad: bool = False, stress_script: Path | None = None) -> object:
    script = stress_script or tmp_path / "validate_regime_candidate_stress.py"
    if stress_script is None:
        write_fake_stress_script(script)
    packet_dir = tmp_path / "research_packet"
    write_packet_dir(packet_dir)
    args = [
        "--run-id",
        "unit_deeper_wf",
        "--output-dir",
        str(tmp_path / "out"),
        "--stress-script",
        str(script),
        "--research-review-packet-dir",
        str(packet_dir),
        "--db-path",
        "data/unit.db",
        "--p75-cost-config",
        "config/p75.json",
        "--p90-cost-config",
        "config/p90.json",
        "--overwrite",
    ]
    if include_broad:
        args.append("--include-broad-context")
    return wf_specs.parse_args(args)


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        wf_specs.parse_args(["--help"])

    assert exc.value.code == 0


def test_output_artifacts_are_written(tmp_path: Path) -> None:
    outputs = wf_specs.build_outputs(make_args(tmp_path))

    assert outputs["row_specs"].exists()
    assert outputs["command_plan"].exists()
    assert outputs["report"].exists()
    assert outputs["warnings"].exists()
    assert outputs["manifest"].exists()


def test_exact_rule_spec_includes_full_two_filter_condition(tmp_path: Path) -> None:
    outputs = wf_specs.build_outputs(make_args(tmp_path))
    specs = {row["review_target"]: row for row in read_csv(outputs["row_specs"])}
    commands = {row["review_target"]: row["manual_command"] for row in read_csv(outputs["command_plan"])}

    assert specs["exact_rule"]["condition_to_apply"] == (
        "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
        "numeric_tercile:tick_volume_percentile_100:mid_tercile"
    )
    assert '--condition "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND numeric_tercile:tick_volume_percentile_100:mid_tercile"' in commands["exact_rule"]


def test_single_filter_a_spec_includes_only_filter_a(tmp_path: Path) -> None:
    outputs = wf_specs.build_outputs(make_args(tmp_path))
    specs = {row["review_target"]: row for row in read_csv(outputs["row_specs"])}
    command = next(row["manual_command"] for row in read_csv(outputs["command_plan"]) if row["review_target"] == "single_filter_a")

    assert specs["single_filter_a"]["condition_to_apply"] == "numeric_tercile:close_to_ma_fast_atr_20:high_tercile"
    assert "--condition numeric_tercile:close_to_ma_fast_atr_20:high_tercile" in command
    assert "tick_volume_percentile_100" not in command


def test_broad_regime_baseline_is_omitted_by_default(tmp_path: Path) -> None:
    outputs = wf_specs.build_outputs(make_args(tmp_path))
    targets = {row["review_target"] for row in read_csv(outputs["row_specs"])}

    assert targets == {"exact_rule", "single_filter_a"}


def test_broad_regime_baseline_is_included_when_requested_and_has_no_condition(tmp_path: Path) -> None:
    outputs = wf_specs.build_outputs(make_args(tmp_path, include_broad=True))
    specs = {row["review_target"]: row for row in read_csv(outputs["row_specs"])}
    commands = {row["review_target"]: row["manual_command"] for row in read_csv(outputs["command_plan"])}

    assert "broad_regime_baseline" in specs
    assert specs["broad_regime_baseline"]["source_role"] == "context_baseline"
    assert specs["broad_regime_baseline"]["condition_to_apply"] == ""
    assert "--condition" not in commands["broad_regime_baseline"]


def test_command_plan_uses_stress_validator_and_walk_forward_options(tmp_path: Path) -> None:
    outputs = wf_specs.build_outputs(make_args(tmp_path))
    commands = read_csv(outputs["command_plan"])

    assert len(commands) == 2
    assert all(row["command_status"] == "planned_manual_command" for row in commands)
    assert all("validate_regime_candidate_stress.py" in row["manual_command"] for row in commands)
    assert all("--walk-forward-splits 5" in row["manual_command"] for row in commands)
    assert all("--cost-config config/p75.json" in row["manual_command"] for row in commands)
    assert all("--stress-cost-config config/p90.json" in row["manual_command"] for row in commands)
    assert all("--stress-spread-policy max_row_or_fallback" in row["manual_command"] for row in commands)
    assert all("--horizon 10" in row["manual_command"] for row in commands)
    assert all("--overwrite" in row["manual_command"] for row in commands)


def test_command_plan_omits_unsupported_flags(tmp_path: Path) -> None:
    outputs = wf_specs.build_outputs(make_args(tmp_path))
    commands = read_csv(outputs["command_plan"])

    assert all("--candidate-summary-csv" not in row["manual_command"] for row in commands)
    assert all("--random-baseline-iterations" not in row["manual_command"] for row in commands)
    assert all("--accept-broad-regime-scope" not in row["manual_command"] for row in commands)


def test_missing_cli_support_marks_unsupported_by_stress_script_cli(tmp_path: Path) -> None:
    stress_script = tmp_path / "incomplete_stress.py"
    write_fake_stress_script(stress_script, complete=False)

    outputs = wf_specs.build_outputs(make_args(tmp_path, stress_script=stress_script))
    specs = read_csv(outputs["row_specs"])
    commands = read_csv(outputs["command_plan"])
    warnings = read_csv(outputs["warnings"])

    assert {row["spec_status"] for row in specs} == {"unsupported_by_stress_script_cli"}
    assert {row["command_status"] for row in commands} == {"unsupported_by_stress_script_cli"}
    assert all(row["manual_command"] == "" for row in commands)
    assert {row["warning_code"] for row in warnings} == {"stress_cli_mapping_incomplete"}


def test_manifest_counts_match_specs_and_warnings(tmp_path: Path) -> None:
    outputs = wf_specs.build_outputs(make_args(tmp_path, include_broad=True))
    specs = read_csv(outputs["row_specs"])
    commands = read_csv(outputs["command_plan"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["row_spec_count"] == len(specs)
    assert manifest["command_plan_row_count"] == len(commands)
    assert manifest["planned_manual_command_count"] == sum(
        row["command_status"] == "planned_manual_command" for row in commands
    )
    assert manifest["unsupported_by_stress_script_cli_count"] == sum(
        row["spec_status"] == "unsupported_by_stress_script_cli" for row in specs
    )
    assert manifest["missing_required_input_count"] == sum(
        row["spec_status"] == "missing_required_input" for row in specs
    )
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_stress_validation_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_timeout_policy_review_executed"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_candidate_audit_executed"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_states_command_plan_only_and_no_decision(tmp_path: Path) -> None:
    outputs = wf_specs.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "command-plan-only" in report
    assert "does not execute" in report
    assert "No stress validation, walk-forward validation, backtests" in report
    assert "No candidate-quality conclusion" in report
    assert "trading decision" in report
    assert "Generated commands are heavy/manual" in report


def test_no_child_or_heavy_commands_are_executed() -> None:
    source = Path(wf_specs.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
    assert "run_tp_sl_path_backtests.py" not in source
