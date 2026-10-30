"""Build deeper walk-forward row specs and manual command plans.

This module is artifact-only and command-plan-only. It prepares manual commands
for deeper walk-forward validation of the fixed candidate and critical
single-filter baseline through the existing offline stress validator. It does
not execute generated commands, validation, backtests, diagnostics, audits,
model work, database work, or external actions.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_deeper_walkforward_run_specs"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "fixed_candidate_deeper_walkforward_run_specs" / DEFAULT_RUN_ID
DEFAULT_STRESS_SCRIPT = BASE_DIR / "scripts" / "validate_regime_candidate_stress.py"
DEFAULT_PYTHON_EXECUTABLE = "python"
DEFAULT_DB_PATH = "data/trading_bot.db"
DEFAULT_P75_COST_CONFIG = "config/brokers/pepperstone_historical_p75.local.json"
DEFAULT_P90_COST_CONFIG = "config/brokers/pepperstone_historical_p90.local.json"
DEFAULT_STRESS_SPREAD_POLICY = "max_row_or_fallback"
DEFAULT_SAME_BAR_POLICY = "stop_first"
DEFAULT_EXACT_CONDITION = (
    "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
    "numeric_tercile:tick_volume_percentile_100:mid_tercile"
)
DEFAULT_SINGLE_FILTER_A_CONDITION = "numeric_tercile:close_to_ma_fast_atr_20:high_tercile"
DEFAULT_RESEARCH_REVIEW_PACKET_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_research_review_packet"
    / "gbpusd_short_h10_1_5_off_hours_research_review_packet_v1"
)
DEFAULT_MANUAL_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_deeper_walkforward_runs"

ROW_SPECS_FILE = "fixed_candidate_deeper_walkforward_run_specs.csv"
COMMAND_PLAN_FILE = "fixed_candidate_deeper_walkforward_command_plan.csv"
REPORT_FILE = "fixed_candidate_deeper_walkforward_run_specs_report.md"
WARNINGS_FILE = "fixed_candidate_deeper_walkforward_run_specs_warnings.csv"
MANIFEST_FILE = "fixed_candidate_deeper_walkforward_run_specs_manifest.json"

REVIEW_TARGETS = ("exact_rule", "single_filter_a")
OPTIONAL_CONTEXT_TARGET = "broad_regime_baseline"
SOURCE_ROLES = {
    "exact_rule": "primary_candidate",
    "single_filter_a": "critical_baseline",
    "broad_regime_baseline": "context_baseline",
}
SPEC_STATUSES = {
    "spec_ready",
    "needs_manual_mapping",
    "missing_required_input",
    "unsupported_by_stress_script_cli",
}
COMMAND_STATUSES = {
    "planned_manual_command",
    "needs_manual_mapping",
    "missing_required_input",
    "unsupported_by_stress_script_cli",
}

COMMON_REQUIRED_CLI_OPTIONS = {
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
    "--walk-forward-splits",
}
CONDITION_OPTION = "--condition"
OPTIONAL_OVERWRITE_OPTION = "--overwrite"

ROW_SPEC_FIELDNAMES = [
    "run_id",
    "review_target",
    "source_role",
    "symbol",
    "direction",
    "timeframe",
    "target_horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "condition_to_apply",
    "tp_atr",
    "sl_atr",
    "atr_column",
    "same_bar_policy",
    "p75_cost_config",
    "p90_cost_config",
    "stress_spread_policy",
    "walk_forward_splits",
    "expected_output_dir",
    "spec_status",
    "warning_code",
    "blocking_warning",
]

COMMAND_PLAN_FIELDNAMES = [
    "run_id",
    "review_target",
    "command_order",
    "manual_command",
    "command_status",
    "expected_output_dir",
    "stress_script",
    "python_executable",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "review_target",
    "source_path",
    "blocking_warning",
]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "row_specs": output_dir / ROW_SPECS_FILE,
        "command_plan": output_dir / COMMAND_PLAN_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "manifest": output_dir / MANIFEST_FILE,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def inspect_stress_script_cli(path: Path) -> set[str]:
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"add_argument\(\s*[\"'](--[A-Za-z0-9_-]+)[\"']", text))


def quote_arg(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    if re.search(r'\s|["&|<>]', text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def append_option(command_parts: list[str], option: str, value: object) -> None:
    command_parts.extend([option, str(value)])


def expected_manual_output_root(run_id: str) -> Path:
    return DEFAULT_MANUAL_OUTPUT_ROOT / run_id / "manual_outputs"


def expected_output_dir(args: argparse.Namespace, review_target: str) -> Path:
    return expected_manual_output_root(args.run_id) / review_target


def condition_for_target(args: argparse.Namespace, review_target: str) -> str:
    if review_target == "exact_rule":
        return str(args.exact_condition or "")
    if review_target == "single_filter_a":
        return str(args.single_filter_a_condition or "")
    return ""


def selected_targets(include_broad_context: bool) -> list[str]:
    targets = list(REVIEW_TARGETS)
    if include_broad_context:
        targets.append(OPTIONAL_CONTEXT_TARGET)
    return targets


def required_cli_options_for_target(review_target: str) -> set[str]:
    required = set(COMMON_REQUIRED_CLI_OPTIONS)
    if review_target in {"exact_rule", "single_filter_a"}:
        required.add(CONDITION_OPTION)
    return required


def missing_cli_options(cli_options: set[str], review_target: str) -> list[str]:
    return sorted(required_cli_options_for_target(review_target) - cli_options)


def warning_row(
    *,
    warning_code: str,
    severity: str,
    message: str,
    review_target: str = "",
    source_path: Path | str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "review_target": review_target,
        "source_path": str(source_path),
        "blocking_warning": bool_text(blocking_warning),
    }


def build_manual_command(
    *,
    args: argparse.Namespace,
    review_target: str,
    condition_to_apply: str,
    cli_options: set[str],
) -> str:
    command_parts = [str(args.python_executable), str(args.stress_script)]
    append_option(command_parts, "--symbol", args.symbol)
    append_option(command_parts, "--direction", args.direction)
    append_option(command_parts, "--timeframe", args.timeframe)
    append_option(command_parts, "--horizon", args.target_horizon)
    append_option(command_parts, "--target-family", args.target_family)
    append_option(command_parts, "--regime-column", args.regime_column)
    append_option(command_parts, "--regime-value", args.regime_value)
    append_option(command_parts, "--tp-atr", args.tp_atr)
    append_option(command_parts, "--sl-atr", args.sl_atr)
    append_option(command_parts, "--atr-column", args.atr_column)
    append_option(command_parts, "--same-bar-policy", args.same_bar_policy)
    append_option(command_parts, "--db-path", args.db_path)
    append_option(command_parts, "--cost-config", args.p75_cost_config)
    append_option(command_parts, "--stress-cost-config", args.p90_cost_config)
    append_option(command_parts, "--stress-spread-policy", args.stress_spread_policy)
    append_option(command_parts, "--walk-forward-splits", args.walk_forward_splits)
    if condition_to_apply:
        append_option(command_parts, "--condition", condition_to_apply)
    append_option(command_parts, "--run-id", review_target)
    append_option(command_parts, "--output-root", expected_manual_output_root(args.run_id))
    if OPTIONAL_OVERWRITE_OPTION in cli_options:
        command_parts.append("--overwrite")
    return " ".join(quote_arg(part) for part in command_parts)


def row_spec(
    *,
    args: argparse.Namespace,
    review_target: str,
    condition_to_apply: str,
    spec_status: str,
    warning_code: str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    if spec_status not in SPEC_STATUSES:
        raise ValueError(f"Unexpected spec_status: {spec_status}")
    return {
        "run_id": args.run_id,
        "review_target": review_target,
        "source_role": SOURCE_ROLES[review_target],
        "symbol": args.symbol,
        "direction": args.direction,
        "timeframe": args.timeframe,
        "target_horizon": args.target_horizon,
        "target_family": args.target_family,
        "regime_column": args.regime_column,
        "regime_value": args.regime_value,
        "condition_to_apply": condition_to_apply,
        "tp_atr": args.tp_atr,
        "sl_atr": args.sl_atr,
        "atr_column": args.atr_column,
        "same_bar_policy": args.same_bar_policy,
        "p75_cost_config": args.p75_cost_config,
        "p90_cost_config": args.p90_cost_config,
        "stress_spread_policy": args.stress_spread_policy,
        "walk_forward_splits": args.walk_forward_splits,
        "expected_output_dir": expected_output_dir(args, review_target),
        "spec_status": spec_status,
        "warning_code": warning_code,
        "blocking_warning": bool_text(blocking_warning),
    }


def command_plan_row(
    *,
    args: argparse.Namespace,
    review_target: str,
    command_order: int,
    manual_command: str,
    command_status: str,
    warning_code: str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    if command_status not in COMMAND_STATUSES:
        raise ValueError(f"Unexpected command_status: {command_status}")
    return {
        "run_id": args.run_id,
        "review_target": review_target,
        "command_order": command_order,
        "manual_command": manual_command,
        "command_status": command_status,
        "expected_output_dir": expected_output_dir(args, review_target),
        "stress_script": args.stress_script,
        "python_executable": args.python_executable,
        "warning_code": warning_code,
        "blocking_warning": bool_text(blocking_warning),
    }


def build_specs(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    cli_options = inspect_stress_script_cli(Path(args.stress_script))
    stress_script_exists = Path(args.stress_script).exists()
    research_packet_exists = Path(args.research_review_packet_dir).exists()
    targets = selected_targets(bool(args.include_broad_context))
    specs: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for index, review_target in enumerate(targets, start=1):
        condition_to_apply = condition_for_target(args, review_target)
        target_missing_cli = missing_cli_options(cli_options, review_target)
        warning_code = ""
        blocking = False
        if not stress_script_exists:
            spec_status = "missing_required_input"
            command_status = "missing_required_input"
            warning_code = "stress_script_missing"
            blocking = True
            warnings.append(
                warning_row(
                    warning_code=warning_code,
                    severity="error",
                    message="Stress script is missing; no manual command was planned.",
                    review_target=review_target,
                    source_path=args.stress_script,
                    blocking_warning=True,
                )
            )
        elif not research_packet_exists:
            spec_status = "missing_required_input"
            command_status = "missing_required_input"
            warning_code = "research_review_packet_missing"
            blocking = True
            warnings.append(
                warning_row(
                    warning_code=warning_code,
                    severity="error",
                    message="Research review packet directory is missing; no manual command was planned.",
                    review_target=review_target,
                    source_path=args.research_review_packet_dir,
                    blocking_warning=True,
                )
            )
        elif target_missing_cli:
            spec_status = "unsupported_by_stress_script_cli"
            command_status = "unsupported_by_stress_script_cli"
            warning_code = "stress_cli_mapping_incomplete"
            warnings.append(
                warning_row(
                    warning_code=warning_code,
                    severity="warning",
                    message=(
                        "Configured stress script lacks required CLI options for this row: "
                        + ", ".join(target_missing_cli)
                    ),
                    review_target=review_target,
                    source_path=args.stress_script,
                )
            )
        else:
            spec_status = "spec_ready"
            command_status = "planned_manual_command"

        manual_command = ""
        if command_status == "planned_manual_command":
            manual_command = build_manual_command(
                args=args,
                review_target=review_target,
                condition_to_apply=condition_to_apply,
                cli_options=cli_options,
            )
        specs.append(
            row_spec(
                args=args,
                review_target=review_target,
                condition_to_apply=condition_to_apply,
                spec_status=spec_status,
                warning_code=warning_code,
                blocking_warning=blocking,
            )
        )
        commands.append(
            command_plan_row(
                args=args,
                review_target=review_target,
                command_order=index,
                manual_command=manual_command,
                command_status=command_status,
                warning_code=warning_code,
                blocking_warning=blocking,
            )
        )

    all_required = set(COMMON_REQUIRED_CLI_OPTIONS) | {CONDITION_OPTION}
    cli_info = {
        "stress_script_exists": stress_script_exists,
        "inspected_cli_options": sorted(cli_options),
        "required_cli_options_available": sorted(all_required - cli_options) == [],
        "missing_cli_options": sorted(all_required - cli_options),
        "overwrite_option_available": OPTIONAL_OVERWRITE_OPTION in cli_options,
        "research_review_packet_dir_exists": research_packet_exists,
    }
    return specs, commands, warnings, cli_info


def status_counts(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    return Counter(str(row.get(field) or "") for row in rows)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    specs: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    cli_info: dict[str, Any],
) -> None:
    spec_counts = status_counts(specs, "spec_status")
    command_counts = status_counts(commands, "command_status")
    lines = [
        "# Fixed Candidate Deeper Walk-Forward Run Specs",
        "",
        "This artifact is command-plan-only. It prepares manual commands and does not execute them.",
        "No stress validation, walk-forward validation, backtests, timeout review, baseline diagnostics, or candidate audit was run.",
        "No candidate-quality conclusion, ranking, or trading decision was made.",
        "",
        "## Stress Script CLI Mapping",
        "",
        f"- stress_script: `{args.stress_script}`",
        f"- stress_script_exists: `{bool_text(bool(cli_info['stress_script_exists']))}`",
        f"- required_cli_options_available: `{bool_text(bool(cli_info['required_cli_options_available']))}`",
        f"- missing_cli_options: `{', '.join(cli_info['missing_cli_options']) or 'none'}`",
        f"- overwrite_option_available: `{bool_text(bool(cli_info['overwrite_option_available']))}`",
        "",
        "## Planned Targets",
        "",
        "- `exact_rule`: full two-filter condition.",
        "- `single_filter_a`: filter A only.",
        "- `broad_regime_baseline`: only when requested; regime only and no condition.",
        "",
        "## Counts",
        "",
        f"- spec_ready: `{spec_counts.get('spec_ready', 0)}`",
        f"- unsupported_by_stress_script_cli: `{spec_counts.get('unsupported_by_stress_script_cli', 0)}`",
        f"- missing_required_input: `{spec_counts.get('missing_required_input', 0)}`",
        f"- planned_manual_command: `{command_counts.get('planned_manual_command', 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "Generated commands are heavy/manual artifacts for the user to run separately.",
        "Next expected artifact after manual execution: deeper walk-forward outputs for exact_rule and single_filter_a.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    specs: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    cli_info: dict[str, Any],
) -> None:
    spec_counts = status_counts(specs, "spec_status")
    command_counts = status_counts(commands, "command_status")
    blocking_warnings = [row for row in warnings if str(row.get("blocking_warning")).lower() == "true"]
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "stress_script": str(args.stress_script),
        "stress_script_exists": cli_info["stress_script_exists"],
        "required_cli_options_available": cli_info["required_cli_options_available"],
        "missing_cli_options": cli_info["missing_cli_options"],
        "row_spec_count": len(specs),
        "command_plan_row_count": len(commands),
        "planned_manual_command_count": command_counts.get("planned_manual_command", 0),
        "needs_manual_mapping_count": spec_counts.get("needs_manual_mapping", 0),
        "missing_required_input_count": spec_counts.get("missing_required_input", 0),
        "unsupported_by_stress_script_cli_count": spec_counts.get("unsupported_by_stress_script_cli", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings),
        "no_child_scripts_executed": True,
        "no_stress_validation_executed": True,
        "no_backtests_run": True,
        "no_timeout_policy_review_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_audit_executed": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir)
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    specs, commands, warnings, cli_info = build_specs(args)
    write_csv(paths["row_specs"], specs, ROW_SPEC_FIELDNAMES)
    write_csv(paths["command_plan"], commands, COMMAND_PLAN_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, specs=specs, commands=commands, warnings=warnings, cli_info=cli_info)
    write_manifest(
        paths["manifest"],
        args=args,
        output_dir=output_dir,
        specs=specs,
        commands=commands,
        warnings=warnings,
        cli_info=cli_info,
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build artifact-only deeper walk-forward row specs and manual command plans."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--stress-script", type=Path, default=DEFAULT_STRESS_SCRIPT)
    parser.add_argument("--python-executable", default=DEFAULT_PYTHON_EXECUTABLE)
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--direction", choices=("long", "short"), default="short")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--target-horizon", default="10")
    parser.add_argument("--target-family", default="preferred_1_5atr_1atr_hit_first")
    parser.add_argument("--regime-column", default="hour_session")
    parser.add_argument("--regime-value", default="Off_hours")
    parser.add_argument("--tp-atr", default="1.5")
    parser.add_argument("--sl-atr", default="1.0")
    parser.add_argument("--atr-column", default="atr_20")
    parser.add_argument("--same-bar-policy", choices=("stop_first", "take_first"), default=DEFAULT_SAME_BAR_POLICY)
    parser.add_argument("--p75-cost-config", default=DEFAULT_P75_COST_CONFIG)
    parser.add_argument("--p90-cost-config", default=DEFAULT_P90_COST_CONFIG)
    parser.add_argument("--stress-spread-policy", default=DEFAULT_STRESS_SPREAD_POLICY)
    parser.add_argument("--walk-forward-splits", default="5")
    parser.add_argument("--include-broad-context", action="store_true")
    parser.add_argument("--exact-condition", default=DEFAULT_EXACT_CONDITION)
    parser.add_argument("--single-filter-a-condition", default=DEFAULT_SINGLE_FILTER_A_CONDITION)
    parser.add_argument("--research-review-packet-dir", type=Path, default=DEFAULT_RESEARCH_REVIEW_PACKET_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main() -> int:
    try:
        paths = build_outputs(parse_args())
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 1
    print(f"Wrote row specs: {paths['row_specs']}")
    print(f"Wrote command plan: {paths['command_plan']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
