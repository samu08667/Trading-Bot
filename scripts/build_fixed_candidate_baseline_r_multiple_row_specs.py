"""Build fixed-candidate baseline R-multiple row specs and manual commands.

This module is artifact-only and command-plan-only. It prepares explicit
manual commands for replaying fixed baseline rows through the existing
TP/SL/path stress validator. It does not run stress validation, backtests,
baseline diagnostics, data generation, or trading workflows.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_baseline_r_multiple_row_specs"
DEFAULT_OUTPUT_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_r_multiple_row_specs"
    / DEFAULT_RUN_ID
)
DEFAULT_FEATURE_CONDITION = (
    "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
    "numeric_tercile:tick_volume_percentile_100:mid_tercile"
)
DEFAULT_FILTER_A = "numeric_tercile:close_to_ma_fast_atr_20:high_tercile"
DEFAULT_FILTER_B = "numeric_tercile:tick_volume_percentile_100:mid_tercile"
DEFAULT_DB_PATH = "data/trading_bot.db"
DEFAULT_P75_COST_CONFIG = "config/brokers/pepperstone_historical_p75.local.json"
DEFAULT_P90_COST_CONFIG = "config/brokers/pepperstone_historical_p90.local.json"
DEFAULT_STRESS_SCRIPT = BASE_DIR / "scripts" / "validate_regime_candidate_stress.py"
DEFAULT_PYTHON_EXECUTABLE = "python"
DEFAULT_STRESS_SPREAD_POLICY = "max_row_or_fallback"
DEFAULT_SAME_BAR_POLICY = "stop_first"

ROW_SPECS_FILE = "fixed_candidate_baseline_r_multiple_row_specs.csv"
COMMAND_PLAN_FILE = "fixed_candidate_baseline_r_multiple_command_plan.csv"
REPORT_FILE = "fixed_candidate_baseline_r_multiple_row_specs_report.md"
WARNINGS_FILE = "fixed_candidate_baseline_r_multiple_row_specs_warnings.csv"
MANIFEST_FILE = "fixed_candidate_baseline_r_multiple_row_specs_manifest.json"

BASELINE_TYPES = ("broad_regime_baseline", "single_filter_a", "single_filter_b")
SPEC_STATUSES = {
    "spec_ready",
    "needs_manual_mapping",
    "missing_required_input",
    "unsupported_baseline_type",
}
COMMAND_STATUSES = {
    "planned_manual_command",
    "needs_manual_mapping",
    "missing_required_input",
    "unsupported_baseline_type",
}

COMMON_STRESS_OPTIONS = {
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
}
CONDITION_OPTION = "--condition"

ROW_SPEC_FIELDNAMES = [
    "run_id",
    "baseline_type",
    "expected_cost_profiles",
    "symbol",
    "direction",
    "timeframe",
    "target_horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "tp_atr",
    "sl_atr",
    "atr_column",
    "condition_to_apply",
    "exact_feature_condition_metadata",
    "db_path",
    "p75_cost_config",
    "p90_cost_config",
    "stress_spread_policy",
    "expected_output_dir",
    "spec_status",
    "warning_code",
    "blocking_warning",
]

COMMAND_PLAN_FIELDNAMES = [
    "run_id",
    "baseline_type",
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
    "baseline_type",
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


def parse_baseline_types(values: list[str] | None) -> list[str]:
    selected: list[str] = []
    for value in values or BASELINE_TYPES:
        for item in str(value).split(","):
            normalized = item.strip()
            if normalized and normalized not in selected:
                selected.append(normalized)
    return selected


def condition_for_baseline(args: argparse.Namespace, baseline_type: str) -> str:
    if baseline_type == "broad_regime_baseline":
        return ""
    if baseline_type == "single_filter_a":
        return str(args.baseline_filter_a or "")
    if baseline_type == "single_filter_b":
        return str(args.baseline_filter_b or "")
    return ""


def expected_output_dir(output_dir: Path, run_id: str, baseline_type: str) -> Path:
    return output_dir / "manual_r_multiple_outputs" / f"{run_id}_{baseline_type}"


def stress_run_id(run_id: str, baseline_type: str) -> str:
    return f"{run_id}_{baseline_type}"


def missing_required_cli_options(cli_options: set[str], *, baseline_type: str) -> list[str]:
    required = set(COMMON_STRESS_OPTIONS)
    if baseline_type in {"single_filter_a", "single_filter_b"}:
        required.add(CONDITION_OPTION)
    return sorted(required - cli_options)


def warning_row(
    *,
    warning_code: str,
    severity: str,
    message: str,
    baseline_type: str = "",
    source_path: Path | str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "baseline_type": baseline_type,
        "source_path": str(source_path),
        "blocking_warning": bool_text(blocking_warning),
    }


def build_manual_command(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    baseline_type: str,
    condition_to_apply: str,
) -> str:
    output_root = output_dir / "manual_r_multiple_outputs"
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
    if condition_to_apply:
        append_option(command_parts, "--condition", condition_to_apply)
    append_option(command_parts, "--run-id", stress_run_id(args.run_id, baseline_type))
    append_option(command_parts, "--output-root", output_root)
    command_parts.append("--overwrite")
    return " ".join(quote_arg(part) for part in command_parts)


def row_spec(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    baseline_type: str,
    condition_to_apply: str,
    spec_status: str,
    warning_code: str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    if spec_status not in SPEC_STATUSES:
        raise ValueError(f"Unexpected spec_status: {spec_status}")
    return {
        "run_id": args.run_id,
        "baseline_type": baseline_type,
        "expected_cost_profiles": "p75;p90",
        "symbol": args.symbol,
        "direction": args.direction,
        "timeframe": args.timeframe,
        "target_horizon": args.target_horizon,
        "target_family": args.target_family,
        "regime_column": args.regime_column,
        "regime_value": args.regime_value,
        "tp_atr": args.tp_atr,
        "sl_atr": args.sl_atr,
        "atr_column": args.atr_column,
        "condition_to_apply": condition_to_apply,
        "exact_feature_condition_metadata": args.feature_condition,
        "db_path": args.db_path,
        "p75_cost_config": args.p75_cost_config,
        "p90_cost_config": args.p90_cost_config,
        "stress_spread_policy": args.stress_spread_policy,
        "expected_output_dir": str(expected_output_dir(output_dir, args.run_id, baseline_type)),
        "spec_status": spec_status,
        "warning_code": warning_code,
        "blocking_warning": bool_text(blocking_warning),
    }


def command_plan_row(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    baseline_type: str,
    manual_command: str,
    command_status: str,
    warning_code: str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    if command_status not in COMMAND_STATUSES:
        raise ValueError(f"Unexpected command_status: {command_status}")
    return {
        "run_id": args.run_id,
        "baseline_type": baseline_type,
        "manual_command": manual_command,
        "command_status": command_status,
        "expected_output_dir": str(expected_output_dir(output_dir, args.run_id, baseline_type)),
        "stress_script": str(args.stress_script),
        "python_executable": args.python_executable,
        "warning_code": warning_code,
        "blocking_warning": bool_text(blocking_warning),
    }


def build_row_specs(
    args: argparse.Namespace,
    output_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    cli_options = inspect_stress_script_cli(Path(args.stress_script))
    selected_baseline_types = parse_baseline_types(args.baseline_types)
    specs: list[dict[str, Any]] = []
    command_plan: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    stress_script_exists = Path(args.stress_script).exists()
    if not stress_script_exists:
        warnings.append(
            warning_row(
                warning_code="stress_script_missing",
                severity="error",
                message="The configured stress script was not found.",
                source_path=args.stress_script,
                blocking_warning=True,
            )
        )

    for baseline_type in selected_baseline_types:
        condition_to_apply = condition_for_baseline(args, baseline_type)
        if baseline_type not in BASELINE_TYPES:
            warning_code = "unsupported_baseline_type"
            warnings.append(
                warning_row(
                    warning_code=warning_code,
                    severity="warning",
                    message="The requested baseline type is not supported by this fixed-candidate row-spec module.",
                    baseline_type=baseline_type,
                    source_path=args.stress_script,
                    blocking_warning=False,
                )
            )
            specs.append(
                row_spec(
                    args=args,
                    output_dir=output_dir,
                    baseline_type=baseline_type,
                    condition_to_apply="",
                    spec_status="unsupported_baseline_type",
                    warning_code=warning_code,
                )
            )
            command_plan.append(
                command_plan_row(
                    args=args,
                    output_dir=output_dir,
                    baseline_type=baseline_type,
                    manual_command="",
                    command_status="unsupported_baseline_type",
                    warning_code=warning_code,
                )
            )
            continue

        missing_options = missing_required_cli_options(cli_options, baseline_type=baseline_type)
        if not stress_script_exists:
            warning_code = "stress_script_missing"
            spec_status = "missing_required_input"
            command_status = "missing_required_input"
            blocking = True
        elif missing_options:
            warning_code = "stress_cli_mapping_incomplete"
            spec_status = "needs_manual_mapping"
            command_status = "needs_manual_mapping"
            blocking = False
            warnings.append(
                warning_row(
                    warning_code=warning_code,
                    severity="warning",
                    message=(
                        "Configured stress script lacks required CLI options for this row: "
                        + ", ".join(missing_options)
                    ),
                    baseline_type=baseline_type,
                    source_path=args.stress_script,
                    blocking_warning=False,
                )
            )
        else:
            warning_code = ""
            spec_status = "spec_ready"
            command_status = "planned_manual_command"
            blocking = False

        manual_command = ""
        if command_status == "planned_manual_command":
            manual_command = build_manual_command(
                args=args,
                output_dir=output_dir,
                baseline_type=baseline_type,
                condition_to_apply=condition_to_apply,
            )

        specs.append(
            row_spec(
                args=args,
                output_dir=output_dir,
                baseline_type=baseline_type,
                condition_to_apply=condition_to_apply,
                spec_status=spec_status,
                warning_code=warning_code,
                blocking_warning=blocking,
            )
        )
        command_plan.append(
            command_plan_row(
                args=args,
                output_dir=output_dir,
                baseline_type=baseline_type,
                manual_command=manual_command,
                command_status=command_status,
                warning_code=warning_code,
                blocking_warning=blocking,
            )
        )

    cli_info = {
        "stress_script_exists": stress_script_exists,
        "inspected_cli_options": sorted(cli_options),
        "common_missing_cli_options": sorted(COMMON_STRESS_OPTIONS - cli_options),
        "condition_option_available": CONDITION_OPTION in cli_options,
    }
    return specs, command_plan, warnings, cli_info


def status_counts(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    return Counter(str(row.get(field) or "") for row in rows)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    specs: list[dict[str, Any]],
    command_plan: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    cli_info: dict[str, Any],
) -> None:
    spec_counts = status_counts(specs, "spec_status")
    command_counts = status_counts(command_plan, "command_status")
    warning_counts = Counter(str(row.get("warning_code") or "unknown") for row in warnings)
    lines = [
        "# Fixed Candidate Baseline R-Multiple Row Specs",
        "",
        "This artifact is research-only, artifact-only, and command-plan-only.",
        "No generated commands were executed. No stress validation, baseline diagnostics, or backtests were run.",
        "No net-return baseline rows were converted into R-multiple rows.",
        "No candidate-quality evaluation, profitability conclusion, ranking, or trading decision was made.",
        "",
        "## CLI Mapping Inspection",
        "",
        f"- Stress script inspected: `{args.stress_script}`",
        f"- Stress script exists: `{bool_text(bool(cli_info['stress_script_exists']))}`",
        f"- Common missing CLI options: `{', '.join(cli_info['common_missing_cli_options']) or 'none'}`",
        f"- Condition option available: `{bool_text(bool(cli_info['condition_option_available']))}`",
        "",
        "## Row Semantics",
        "",
        "- `broad_regime_baseline`: regime only; no `--condition` is planned.",
        "- `single_filter_a`: regime plus baseline filter A only.",
        "- `single_filter_b`: regime plus baseline filter B only.",
        "- The exact two-filter feature condition is preserved as metadata only.",
        "",
        "## Spec Counts",
        "",
        f"- spec_ready: {spec_counts.get('spec_ready', 0)}",
        f"- needs_manual_mapping: {spec_counts.get('needs_manual_mapping', 0)}",
        f"- missing_required_input: {spec_counts.get('missing_required_input', 0)}",
        f"- unsupported_baseline_type: {spec_counts.get('unsupported_baseline_type', 0)}",
        "",
        "## Command Counts",
        "",
        f"- planned_manual_command: {command_counts.get('planned_manual_command', 0)}",
        f"- needs_manual_mapping: {command_counts.get('needs_manual_mapping', 0)}",
        f"- missing_required_input: {command_counts.get('missing_required_input', 0)}",
        f"- unsupported_baseline_type: {command_counts.get('unsupported_baseline_type', 0)}",
        "",
        "## Planned Manual Commands",
        "",
    ]
    planned = [row for row in command_plan if row.get("command_status") == "planned_manual_command"]
    if planned:
        for row in planned:
            lines.append(f"- `{row['baseline_type']}` -> `{row['expected_output_dir']}`")
    else:
        lines.append("- None.")
    lines.extend(["", "## Warning Summary", ""])
    if warning_counts:
        lines.extend([f"- `{code}`: {count}" for code, count in sorted(warning_counts.items())])
    else:
        lines.append("- None.")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    specs: list[dict[str, Any]],
    command_plan: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    cli_info: dict[str, Any],
) -> None:
    spec_counts = status_counts(specs, "spec_status")
    command_counts = status_counts(command_plan, "command_status")
    blocking_warnings = [row for row in warnings if str(row.get("blocking_warning")).lower() == "true"]
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "stress_script": str(args.stress_script),
        "stress_script_cli": cli_info,
        "target_candidate": {
            "symbol": args.symbol,
            "direction": args.direction,
            "timeframe": args.timeframe,
            "target_horizon": args.target_horizon,
            "target_family": args.target_family,
            "regime_column": args.regime_column,
            "regime_value": args.regime_value,
            "tp_atr": args.tp_atr,
            "sl_atr": args.sl_atr,
            "atr_column": args.atr_column,
            "same_bar_policy": args.same_bar_policy,
            "feature_condition_metadata": args.feature_condition,
            "baseline_filter_a": args.baseline_filter_a,
            "baseline_filter_b": args.baseline_filter_b,
        },
        "row_spec_count": len(specs),
        "command_plan_row_count": len(command_plan),
        "spec_ready_count": spec_counts.get("spec_ready", 0),
        "needs_manual_mapping_count": spec_counts.get("needs_manual_mapping", 0),
        "missing_required_input_count": spec_counts.get("missing_required_input", 0),
        "unsupported_baseline_type_count": spec_counts.get("unsupported_baseline_type", 0),
        "planned_manual_command_count": command_counts.get("planned_manual_command", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": len(blocking_warnings),
        "non_blocking_warnings_count": len(warnings) - len(blocking_warnings),
        "no_child_scripts_executed": True,
        "no_stress_validation_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_backtests_run": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
        "no_net_return_to_r_multiple_conversion_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir)
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    specs, command_plan, warnings, cli_info = build_row_specs(args, output_dir)
    write_csv(paths["row_specs"], specs, ROW_SPEC_FIELDNAMES)
    write_csv(paths["command_plan"], command_plan, COMMAND_PLAN_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(
        paths["report"],
        args=args,
        specs=specs,
        command_plan=command_plan,
        warnings=warnings,
        cli_info=cli_info,
    )
    write_manifest(
        paths["manifest"],
        args=args,
        output_dir=output_dir,
        specs=specs,
        command_plan=command_plan,
        warnings=warnings,
        cli_info=cli_info,
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build artifact-only row specs and manual commands for fixed-candidate "
            "baseline R-multiple generation."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--baseline-types", nargs="+", default=list(BASELINE_TYPES))
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
    parser.add_argument("--baseline-filter-a", default=DEFAULT_FILTER_A)
    parser.add_argument("--baseline-filter-b", default=DEFAULT_FILTER_B)
    parser.add_argument("--feature-condition", default=DEFAULT_FEATURE_CONDITION)
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--p75-cost-config", default=DEFAULT_P75_COST_CONFIG)
    parser.add_argument("--p90-cost-config", default=DEFAULT_P90_COST_CONFIG)
    parser.add_argument("--stress-spread-policy", default=DEFAULT_STRESS_SPREAD_POLICY)
    parser.add_argument("--stress-script", type=Path, default=DEFAULT_STRESS_SCRIPT)
    parser.add_argument("--python-executable", default=DEFAULT_PYTHON_EXECUTABLE)
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
