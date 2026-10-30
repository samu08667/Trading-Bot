"""Plan manual fixed-candidate baseline runs from a normalized matrix.

This module reads the fixed-candidate baseline/cost matrix and produces a
manual run plan for rows marked planned_not_run. It never executes child
scripts, baseline diagnostics, backtests, or research workflows.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_baseline_run_plan"
DEFAULT_MATRIX_CSV = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_cost_matrix"
    / "gbpusd_short_h10_1_5_off_hours_baseline_cost_matrix"
    / "fixed_candidate_baseline_cost_matrix.csv"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_baseline_run_plan"
DEFAULT_BASELINE_SCRIPT = BASE_DIR / "scripts" / "run_candidate_baseline_diagnostics.py"
DEFAULT_DB_PATH = "data/trading_bot.db"
DEFAULT_P75_COST_CONFIG = "config/brokers/pepperstone_historical_p75.local.json"
DEFAULT_P90_COST_CONFIG = "config/brokers/pepperstone_historical_p90.local.json"

PLAN_FILE = "fixed_candidate_baseline_run_plan.csv"
REPORT_FILE = "fixed_candidate_baseline_run_plan_report.md"
WARNINGS_FILE = "fixed_candidate_baseline_run_plan_warnings.csv"
MANIFEST_FILE = "fixed_candidate_baseline_run_plan_manifest.json"
DEFAULT_RUN_PLAN_CSV = DEFAULT_OUTPUT_ROOT / DEFAULT_RUN_ID / PLAN_FILE

PLANNED_STATUS = "planned_not_run"
COMMAND_STATUSES = {
    "planned_manual_command",
    "needs_manual_mapping",
    "skipped_available",
    "skipped_missing",
    "skipped_deferred",
    "skipped_not_applicable",
}
SKIP_STATUS_BY_ARTIFACT_STATUS = {
    "available": "skipped_available",
    "missing": "skipped_missing",
    "deferred": "skipped_deferred",
    "not_applicable": "skipped_not_applicable",
}
DIRECT_MAPPING_OPTIONS = {
    "--baseline-type",
    "--baseline-filter",
    "--feature-condition",
    "--regime-column",
    "--regime-value",
    "--target-family",
}
NUMERIC_TERCILE_OPT_IN_OPTION = "--allow-numeric-tercile-baseline-filter"

PLAN_FIELDNAMES = [
    "run_id",
    "source_matrix_csv",
    "baseline_type",
    "baseline_filter",
    "cost_profile",
    "cost_config_path",
    "symbol",
    "direction",
    "timeframe",
    "target_horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "tp_atr",
    "sl_atr",
    "db_path",
    "baseline_script",
    "python_executable",
    "manual_command",
    "expected_output_dir",
    "command_status",
    "command_warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "baseline_type",
    "cost_profile",
    "source_matrix_csv",
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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Matrix CSV not found: {path}")
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "run_plan": output_dir / PLAN_FILE,
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


def inspect_baseline_script_cli(path: Path) -> set[str]:
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


def append_option(command_parts: list[str], option: str, value: object, *, include_empty: bool = False) -> None:
    text = str(value or "")
    if not text and not include_empty:
        return
    command_parts.extend([option, text])


def cost_config_for_row(row: dict[str, str], args: argparse.Namespace) -> str:
    if row.get("cost_config_path"):
        return str(row["cost_config_path"])
    if row.get("cost_profile") == "p90":
        return str(args.p90_cost_config)
    return str(args.p75_cost_config)


def expected_output_dir(output_dir: Path, row: dict[str, str]) -> Path:
    return output_dir / "manual_baseline_outputs" / f"{row.get('baseline_type', 'unknown')}_{row.get('cost_profile', 'unknown')}"


def can_map_row_safely(cli_options: set[str]) -> tuple[bool, list[str]]:
    missing = sorted(DIRECT_MAPPING_OPTIONS - cli_options)
    return not missing, missing


def baseline_filter_needs_numeric_tercile_opt_in(row: dict[str, str]) -> bool:
    return "numeric_tercile" in str(row.get("baseline_filter") or "").lower()


def build_manual_command(
    *,
    row: dict[str, str],
    args: argparse.Namespace,
    output_dir: Path,
    cost_config_path: str,
) -> str:
    command_parts = [
        args.python_executable,
        str(args.baseline_script),
    ]
    append_option(command_parts, "--run-id", args.run_id, include_empty=True)
    append_option(command_parts, "--direction", row.get("direction", ""), include_empty=True)
    append_option(command_parts, "--symbols", row.get("symbol", ""), include_empty=True)
    append_option(command_parts, "--timeframe", row.get("timeframe", ""), include_empty=True)
    append_option(command_parts, "--target-horizon", row.get("target_horizon", ""), include_empty=True)
    append_option(command_parts, "--target-family", row.get("target_family", ""), include_empty=True)
    append_option(command_parts, "--db-path", args.db_path, include_empty=True)
    append_option(command_parts, "--output-dir", str(expected_output_dir(output_dir, row)), include_empty=True)
    append_option(command_parts, "--cost-mode", "estimated", include_empty=True)
    append_option(command_parts, "--return-mode", "net", include_empty=True)
    append_option(command_parts, "--cost-config", cost_config_path, include_empty=True)
    append_option(command_parts, "--baseline-type", row.get("baseline_type", ""), include_empty=True)
    append_option(command_parts, "--baseline-filter", row.get("baseline_filter", ""))
    if baseline_filter_needs_numeric_tercile_opt_in(row):
        command_parts.append(NUMERIC_TERCILE_OPT_IN_OPTION)
    append_option(command_parts, "--feature-condition", row.get("feature_condition", ""), include_empty=True)
    append_option(command_parts, "--regime-column", row.get("regime_column", ""), include_empty=True)
    append_option(command_parts, "--regime-value", row.get("regime_value", ""), include_empty=True)
    return " ".join(quote_arg(part) for part in command_parts)


def sanitize_manual_command_for_print(row: dict[str, str]) -> str:
    command = str(row.get("manual_command") or "").strip()
    if str(row.get("baseline_filter") or "").strip():
        return command
    command = re.sub(r"\s+--baseline-filter\s+\"\"", "", command)
    command = re.sub(r"\s+--baseline-filter\s+''", "", command)
    return command.strip()


def warning_row(
    *,
    warning_code: str,
    severity: str,
    message: str,
    baseline_type: str = "",
    cost_profile: str = "",
    source_matrix_csv: Path | str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "baseline_type": baseline_type,
        "cost_profile": cost_profile,
        "source_matrix_csv": str(source_matrix_csv),
        "blocking_warning": bool_text(blocking_warning),
    }


def plan_row(
    *,
    args: argparse.Namespace,
    source_matrix_csv: Path,
    output_dir: Path,
    matrix_row: dict[str, str],
    command_status: str,
    warning_code: str = "",
    manual_command: str = "",
) -> dict[str, Any]:
    if command_status not in COMMAND_STATUSES:
        raise ValueError(f"Unexpected command_status: {command_status}")
    cost_config_path = cost_config_for_row(matrix_row, args)
    return {
        "run_id": args.run_id,
        "source_matrix_csv": str(source_matrix_csv),
        "baseline_type": matrix_row.get("baseline_type", ""),
        "baseline_filter": matrix_row.get("baseline_filter", ""),
        "cost_profile": matrix_row.get("cost_profile", ""),
        "cost_config_path": cost_config_path,
        "symbol": matrix_row.get("symbol", ""),
        "direction": matrix_row.get("direction", ""),
        "timeframe": matrix_row.get("timeframe", ""),
        "target_horizon": matrix_row.get("target_horizon", ""),
        "target_family": matrix_row.get("target_family", ""),
        "regime_column": matrix_row.get("regime_column", ""),
        "regime_value": matrix_row.get("regime_value", ""),
        "tp_atr": matrix_row.get("tp_atr", ""),
        "sl_atr": matrix_row.get("sl_atr", ""),
        "db_path": args.db_path,
        "baseline_script": str(args.baseline_script),
        "python_executable": args.python_executable,
        "manual_command": manual_command,
        "expected_output_dir": str(expected_output_dir(output_dir, matrix_row)),
        "command_status": command_status,
        "command_warning_code": warning_code,
        "blocking_warning": bool_text(False),
    }


def build_plan(args: argparse.Namespace, output_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    source_matrix_csv = Path(args.matrix_csv)
    matrix_rows = read_csv_rows(source_matrix_csv)
    cli_options = inspect_baseline_script_cli(Path(args.baseline_script))
    safely_mappable, missing_mapping_options = can_map_row_safely(cli_options)
    run_plan: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not Path(args.baseline_script).exists():
        warnings.append(
            warning_row(
                warning_code="baseline_script_missing",
                severity="error",
                message="The configured baseline script was not found.",
                source_matrix_csv=source_matrix_csv,
                blocking_warning=True,
            )
        )

    for matrix_row in matrix_rows:
        artifact_status = str(matrix_row.get("artifact_status") or "").strip()
        if artifact_status != PLANNED_STATUS:
            command_status = SKIP_STATUS_BY_ARTIFACT_STATUS.get(artifact_status, "skipped_missing")
            run_plan.append(
                plan_row(
                    args=args,
                    source_matrix_csv=source_matrix_csv,
                    output_dir=output_dir,
                    matrix_row=matrix_row,
                    command_status=command_status,
                )
            )
            continue

        cost_config_path = cost_config_for_row(matrix_row, args)
        if (
            safely_mappable
            and baseline_filter_needs_numeric_tercile_opt_in(matrix_row)
            and NUMERIC_TERCILE_OPT_IN_OPTION not in cli_options
        ):
            warning_code = "baseline_numeric_tercile_opt_in_missing"
            warnings.append(
                warning_row(
                    warning_code=warning_code,
                    severity="warning",
                    message=(
                        "Configured baseline script lacks --allow-numeric-tercile-baseline-filter "
                        "needed for this planned numeric_tercile row."
                    ),
                    baseline_type=matrix_row.get("baseline_type", ""),
                    cost_profile=matrix_row.get("cost_profile", ""),
                    source_matrix_csv=source_matrix_csv,
                    blocking_warning=False,
                )
            )
            run_plan.append(
                plan_row(
                    args=args,
                    source_matrix_csv=source_matrix_csv,
                    output_dir=output_dir,
                    matrix_row=matrix_row,
                    command_status="needs_manual_mapping",
                    warning_code=warning_code,
                )
            )
        elif safely_mappable:
            manual_command = build_manual_command(
                row=matrix_row,
                args=args,
                output_dir=output_dir,
                cost_config_path=cost_config_path,
            )
            run_plan.append(
                plan_row(
                    args=args,
                    source_matrix_csv=source_matrix_csv,
                    output_dir=output_dir,
                    matrix_row=matrix_row,
                    command_status="planned_manual_command",
                    manual_command=manual_command,
                )
            )
        else:
            warning_code = "baseline_cli_mapping_incomplete"
            message = (
                "Configured baseline script lacks direct row-mapping CLI options: "
                + ", ".join(missing_mapping_options)
            )
            warnings.append(
                warning_row(
                    warning_code=warning_code,
                    severity="warning",
                    message=message,
                    baseline_type=matrix_row.get("baseline_type", ""),
                    cost_profile=matrix_row.get("cost_profile", ""),
                    source_matrix_csv=source_matrix_csv,
                    blocking_warning=False,
                )
            )
            run_plan.append(
                plan_row(
                    args=args,
                    source_matrix_csv=source_matrix_csv,
                    output_dir=output_dir,
                    matrix_row=matrix_row,
                    command_status="needs_manual_mapping",
                    warning_code=warning_code,
                )
            )

    cli_info = {
        "baseline_script_exists": Path(args.baseline_script).exists(),
        "inspected_cli_options": sorted(cli_options),
        "missing_direct_mapping_options": missing_mapping_options,
        "direct_mapping_available": safely_mappable,
    }
    return run_plan, warnings, cli_info


def command_status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("command_status") or "") for row in rows)


def normalized_filter_values(values: list[str] | None) -> set[str]:
    return {str(value).strip() for value in values or [] if str(value).strip()}


def planned_manual_command_rows(
    *,
    run_plan_csv: Path,
    baseline_types: list[str] | None = None,
    cost_profiles: list[str] | None = None,
    skip_existing_output_dirs: bool = False,
) -> list[dict[str, str]]:
    baseline_filter = normalized_filter_values(baseline_types)
    cost_filter = normalized_filter_values(cost_profiles)
    rows = read_csv_rows(run_plan_csv)
    selected: list[dict[str, str]] = []
    for row in rows:
        if row.get("command_status") != "planned_manual_command":
            continue
        if baseline_filter and row.get("baseline_type") not in baseline_filter:
            continue
        if cost_filter and row.get("cost_profile") not in cost_filter:
            continue
        if skip_existing_output_dirs and Path(row.get("expected_output_dir") or "").exists():
            continue
        if not str(row.get("manual_command") or "").strip():
            continue
        selected.append(row)
    return selected


def print_planned_manual_commands(args: argparse.Namespace) -> list[str]:
    run_plan_csv = Path(args.run_plan_csv)
    rows = planned_manual_command_rows(
        run_plan_csv=run_plan_csv,
        baseline_types=args.baseline_type,
        cost_profiles=args.cost_profile,
        skip_existing_output_dirs=args.skip_existing_output_dirs,
    )
    commands = [sanitize_manual_command_for_print(row) for row in rows]
    for command in commands:
        print(command)
    return commands


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    run_plan: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    cli_info: dict[str, Any],
) -> None:
    counts = command_status_counts(run_plan)
    warning_counts = Counter(str(row.get("warning_code") or "unknown") for row in warnings)
    lines = [
        "# Fixed Candidate Baseline Run Plan",
        "",
        "This artifact is research-only and module-only; it is not a pipeline or workflow.",
        "No child scripts were executed. No baseline diagnostics were executed. No backtests were run.",
        "No candidate-quality evaluation, profitability conclusion, or trading decision was made.",
        "",
        "## Inputs",
        "",
        f"- Run ID: `{args.run_id}`",
        f"- Matrix CSV: `{args.matrix_csv}`",
        f"- Baseline script inspected: `{args.baseline_script}`",
        "",
        "## CLI Mapping Inspection",
        "",
        f"- Direct row mapping available: `{bool_text(bool(cli_info['direct_mapping_available']))}`",
        f"- Missing direct mapping options: `{', '.join(cli_info['missing_direct_mapping_options']) or 'none'}`",
        "",
        "## Command Status Counts",
        "",
        f"- planned_manual_command: {counts.get('planned_manual_command', 0)}",
        f"- needs_manual_mapping: {counts.get('needs_manual_mapping', 0)}",
        f"- skipped_available: {counts.get('skipped_available', 0)}",
        f"- skipped_missing: {counts.get('skipped_missing', 0)}",
        f"- skipped_deferred: {counts.get('skipped_deferred', 0)}",
        f"- skipped_not_applicable: {counts.get('skipped_not_applicable', 0)}",
        "",
        "## Planned Rows",
        "",
    ]
    planned_rows = [
        row
        for row in run_plan
        if row["command_status"] in {"planned_manual_command", "needs_manual_mapping"}
    ]
    if planned_rows:
        lines.extend(
            [
                (
                    f"- `{row['baseline_type']}` `{row['cost_profile']}`: "
                    f"{row['command_status']} ({row.get('command_warning_code') or 'no warning'})"
                )
                for row in planned_rows
            ]
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Warning Summary", ""])
    if warning_counts:
        lines.extend([f"- `{code}`: {count}" for code, count in sorted(warning_counts.items())])
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Manual Follow-Up",
            "",
            (
                "Rows marked `needs_manual_mapping` require an explicit offline command design before "
                "any manual run."
            ),
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    run_plan: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    cli_info: dict[str, Any],
) -> None:
    counts = command_status_counts(run_plan)
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "matrix_csv": str(args.matrix_csv),
        "baseline_script": str(args.baseline_script),
        "baseline_script_cli": cli_info,
        "run_plan_row_count": len(run_plan),
        "planned_manual_command_count": counts.get("planned_manual_command", 0),
        "needs_manual_mapping_count": counts.get("needs_manual_mapping", 0),
        "skipped_row_count": sum(counts.get(status, 0) for status in SKIP_STATUS_BY_ARTIFACT_STATUS.values()),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "no_child_scripts_executed": True,
        "no_backtests_run": True,
        "no_baseline_diagnostics_run": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    output_paths = ensure_outputs_writable(output_dir, args.overwrite)
    run_plan, warnings, cli_info = build_plan(args, output_dir)
    write_csv(output_paths["run_plan"], run_plan, PLAN_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(output_paths["report"], args=args, run_plan=run_plan, warnings=warnings, cli_info=cli_info)
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_dir,
        run_plan=run_plan,
        warnings=warnings,
        cli_info=cli_info,
    )
    return output_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan manual fixed-candidate baseline runs from a matrix. "
            "No child scripts, baseline diagnostics, or backtests are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--matrix-csv", type=Path, default=DEFAULT_MATRIX_CSV)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--p75-cost-config", default=DEFAULT_P75_COST_CONFIG)
    parser.add_argument("--p90-cost-config", default=DEFAULT_P90_COST_CONFIG)
    parser.add_argument("--baseline-script", type=Path, default=DEFAULT_BASELINE_SCRIPT)
    parser.add_argument("--python-executable", default="python")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--print-commands-only",
        action="store_true",
        help="Read a run-plan CSV and print planned manual commands only. Does not write artifacts.",
    )
    parser.add_argument("--run-plan-csv", type=Path, default=DEFAULT_RUN_PLAN_CSV)
    parser.add_argument("--baseline-type", nargs="+", help="Filter printed commands by baseline_type.")
    parser.add_argument("--cost-profile", nargs="+", help="Filter printed commands by cost_profile.")
    parser.add_argument(
        "--skip-existing-output-dirs",
        action="store_true",
        help="When printing commands, skip rows whose expected_output_dir already exists.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.print_commands_only:
            print_planned_manual_commands(args)
            return 0
        outputs = build_outputs(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"Fixed-candidate baseline run planning failed: {exc}")
        return 1
    print("Fixed-candidate baseline run planning complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
