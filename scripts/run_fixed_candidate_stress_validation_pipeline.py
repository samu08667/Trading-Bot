"""Plan or run the fixed-candidate stress validation sub-pipeline."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

try:
    from research_costs import load_cost_config
    from research_pipeline_utils import (
        CommandRunner,
        PipelineCommand,
        PipelineCommandResult,
        aggregate_status,
        default_run_id,
        ensure_output_dir,
        render_command,
        require_existing_path,
        run_command,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.research_costs import load_cost_config
    from scripts.research_pipeline_utils import (
        CommandRunner,
        PipelineCommand,
        PipelineCommandResult,
        aggregate_status,
        default_run_id,
        ensure_output_dir,
        render_command,
        require_existing_path,
        run_command,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_stress_validation_pipeline"
DEFAULT_STRESS_OUTPUT_ROOT = BASE_DIR / "reports" / "regime_candidate_stress"
DEFAULT_ATR_COLUMN = "atr_20"
DEFAULT_SAME_BAR_POLICY = "stop_first"
STRESS_SPREAD_POLICIES = ("standard", "max_row_or_fallback", "fallback_override")

MANIFEST_FILE = "fixed_candidate_stress_validation_manifest.json"
COMMAND_PLAN_FILE = "fixed_candidate_stress_validation_command_plan.csv"
STAGE_RESULTS_FILE = "fixed_candidate_stress_validation_stage_results.csv"
SUMMARY_FILE = "fixed_candidate_stress_validation_summary.csv"
REPORT_FILE = "fixed_candidate_stress_validation_report.md"
WARNINGS_FILE = "fixed_candidate_stress_validation_warnings.csv"

DECISION_SCOPE = "fixed_candidate_stress_validation_pipeline"
PIPELINE_SCOPE = "fixed_candidate_stress_validation_research_orchestration"
FINAL_CLASSIFICATION_DRY_RUN = "FIXED_CANDIDATE_STRESS_VALIDATION_PIPELINE_DRY_RUN_PLANNED"
FINAL_CLASSIFICATION_COMPLETED = "FIXED_CANDIDATE_STRESS_VALIDATION_PIPELINE_COMPLETED"
FINAL_CLASSIFICATION_FAILED = "FIXED_CANDIDATE_STRESS_VALIDATION_PIPELINE_FAILED"
FINAL_CLASSIFICATION_STOPPED = "FIXED_CANDIDATE_STRESS_VALIDATION_PIPELINE_STOPPED"

FORBIDDEN_ACTIONS = [
    "live " + "trading",
    "trading " + "signal",
    "broker " + "execution",
    "position " + "sizing",
    "TP/SL " + "optimization",
    "new feature search",
    "new filters",
    "live " + "readiness",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "blocking",
    "message",
    "related_stage",
    "related_metric",
    "metric_value",
    "threshold",
]

COMMAND_PLAN_FIELDNAMES = [
    "command_order",
    "stage_order",
    "stage_name",
    "command",
    "heavy",
    "required",
    "description",
    "cwd",
    "expected_outputs",
    "planned_output_dir",
]

STAGE_RESULTS_FIELDNAMES = [
    "command_order",
    "stage_order",
    "stage_name",
    "status",
    "returncode",
    "command",
    "stdout_log",
    "stderr_log",
    "started_at",
    "finished_at",
    "duration_seconds",
    "error_message",
    "planned",
    "executed",
    "skipped",
    "failed",
    "required",
    "planned_output_dir",
    "expected_outputs",
    "skip_reason",
]

SUMMARY_FIELDNAMES = [
    "run_id",
    "final_classification",
    "decision_scope",
    "pipeline_scope",
    "dry_run",
    "execute",
    "planned_stage_count",
    "executed_stage_count",
    "skipped_stage_count",
    "failed_stage_count",
    "warnings_count",
    "blocking_warnings_count",
    "non_blocking_warnings_count",
    "stress_output_dir",
    "forbidden_actions",
    "next_action",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or run the research-only fixed-candidate stress validation pipeline. "
            "Execution requires explicit --execute and runs existing stress-validation child code only."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--direction", required=True, choices=("long", "short"))
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--target-horizon", required=True)
    parser.add_argument("--target-family", required=True)
    parser.add_argument("--regime-column", required=True)
    parser.add_argument("--regime-value", required=True)
    parser.add_argument("--tp-atr", required=True, type=float)
    parser.add_argument("--sl-atr", required=True, type=float)
    parser.add_argument("--atr-column", default=DEFAULT_ATR_COLUMN)
    parser.add_argument("--same-bar-policy", choices=("stop_first", "take_first"), default=DEFAULT_SAME_BAR_POLICY)
    parser.add_argument(
        "--feature-condition",
        action="append",
        default=[],
        help="Exact feature condition passed to validate_regime_candidate_stress.py as --condition.",
    )
    parser.add_argument("--candidate-summary-csv", type=Path)
    parser.add_argument("--candidate-id")
    parser.add_argument("--accept-broad-regime-scope", action="store_true")
    parser.add_argument("--bar-level-no-overlap", action="store_true")
    parser.add_argument("--random-baseline-iterations", type=int, default=0)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--walk-forward-splits", type=int, default=3)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--stress-cost-config", type=Path)
    parser.add_argument("--stress-spread-policy", choices=STRESS_SPREAD_POLICIES, default="standard")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--stress-output-root", type=Path, default=DEFAULT_STRESS_OUTPUT_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--stop-on-failure", action=argparse.BooleanOptionalAction, default=True)
    return parser


def _bool_text(value: object) -> str:
    return str(bool(value)).lower()


def _warning_row(
    *,
    warning_code: str,
    severity: str,
    blocking: bool,
    message: str,
    related_stage: str = "",
    related_metric: str = "",
    metric_value: object = "",
    threshold: object = "",
) -> dict[str, object]:
    if severity not in {"info", "review", "severe", "blocking"}:
        raise ValueError(f"Unsupported warning severity: {severity}")
    return {
        "warning_code": warning_code,
        "severity": severity,
        "blocking": _bool_text(blocking),
        "message": message,
        "related_stage": related_stage,
        "related_metric": related_metric,
        "metric_value": metric_value,
        "threshold": threshold,
    }


def _is_blocking(row: Mapping[str, object]) -> bool:
    return str(row.get("blocking", "")).strip().lower() in {"true", "1", "yes"}


def _write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
    *,
    overwrite: bool,
) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"CSV already exists; pass --overwrite to replace it: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return path


def _validate_mode(args: argparse.Namespace) -> None:
    if bool(args.dry_run) == bool(args.execute):
        if args.dry_run:
            raise ValueError("Choose only one of --dry-run or --execute.")
        raise ValueError("Choose either --dry-run or --execute.")


def _resolve_run_id(value: str | None) -> str:
    run_id = str(value or "").strip() or default_run_id()
    if "/" in run_id or "\\" in run_id:
        raise ValueError("--run-id must be a single path segment, not a nested path.")
    return run_id


def _validate_json_config(path: Path | None, *, label: str) -> Path | None:
    if path is None:
        return None
    config_path = require_existing_path(path, label=label, kind="file")
    try:
        load_cost_config(config_path)
    except OSError as exc:
        raise ValueError(f"{label} is not readable: {config_path}: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"Invalid {label}: {config_path}: {exc}") from exc
    return config_path


def _stage_order(stage_name: str) -> int:
    if stage_name == "stress_validation":
        return 1
    raise ValueError(f"Unknown fixed-candidate stress validation stage: {stage_name}")


def _planned_output_dir(command: PipelineCommand) -> Path:
    if not command.expected_outputs:
        return Path("")
    return Path(command.expected_outputs[0]).parent


def _script_path(script_name: str) -> str:
    return str(SCRIPTS_DIR / script_name)


def build_pipeline_paths(args: argparse.Namespace, run_id: str) -> dict[str, Path]:
    stress_output_dir = Path(args.stress_output_root) / run_id
    return {
        "artifact_output_dir": Path(args.output_root) / run_id,
        "stress_output_dir": stress_output_dir,
        "stress_output_root": Path(args.stress_output_root),
    }


def build_stage_commands(args: argparse.Namespace, run_id: str, paths: Mapping[str, Path]) -> list[PipelineCommand]:
    command_args: list[object] = [
        str(args.python_executable or sys.executable),
        _script_path("validate_regime_candidate_stress.py"),
        "--symbol",
        str(args.symbol).strip().upper(),
        "--direction",
        args.direction,
        "--timeframe",
        str(args.timeframe).strip().upper(),
        "--horizon",
        str(args.target_horizon),
        "--target-family",
        args.target_family,
        "--regime-column",
        args.regime_column,
        "--regime-value",
        args.regime_value,
        "--tp-atr",
        args.tp_atr,
        "--sl-atr",
        args.sl_atr,
        "--atr-column",
        args.atr_column,
        "--same-bar-policy",
        args.same_bar_policy,
        "--db-path",
        str(args.db_path),
        "--stress-spread-policy",
        args.stress_spread_policy,
        "--random-baseline-iterations",
        args.random_baseline_iterations,
        "--random-seed",
        args.random_seed,
        "--walk-forward-splits",
        args.walk_forward_splits,
        "--output-root",
        str(paths["stress_output_root"]),
        "--run-id",
        run_id,
    ]
    if args.cost_config is not None:
        command_args.extend(["--cost-config", str(args.cost_config)])
    if args.stress_cost_config is not None:
        command_args.extend(["--stress-cost-config", str(args.stress_cost_config)])
    if args.bar_level_no_overlap:
        command_args.append("--bar-level-no-overlap")
    for condition in args.feature_condition or []:
        command_args.extend(["--condition", condition])
    if args.candidate_summary_csv is not None:
        command_args.extend(["--candidate-summary-csv", str(args.candidate_summary_csv)])
    if args.candidate_id:
        command_args.extend(["--candidate-id", args.candidate_id])
    if args.accept_broad_regime_scope:
        command_args.append("--accept-broad-regime-scope")
    if args.overwrite:
        command_args.append("--overwrite")

    return [
        PipelineCommand(
            stage="stress_validation",
            args=command_args,
            cwd=BASE_DIR,
            expected_outputs=[
                paths["stress_output_dir"] / "candidate_stress_summary.csv",
                paths["stress_output_dir"] / "candidate_stress_report.md",
            ],
            heavy=True,
            required=True,
            description="Run fixed-candidate regime stress validation using the existing child script.",
        )
    ]


def _command_plan_row_builder() -> Any:
    def row_builder(index: int, command: PipelineCommand) -> dict[str, object]:
        return {
            "command_order": index,
            "stage_order": _stage_order(command.stage),
            "stage_name": command.stage,
            "planned_output_dir": str(_planned_output_dir(command)),
        }

    return row_builder


def _planned_command_rows(commands: Sequence[PipelineCommand]) -> list[dict[str, object]]:
    return [
        {
            "command_order": index,
            "stage_order": _stage_order(command.stage),
            "stage_name": command.stage,
            "command": render_command(command),
            "heavy": bool(command.heavy),
            "required": bool(command.required),
            "description": command.description,
            "cwd": str(command.cwd or ""),
            "expected_outputs": [str(path) for path in command.expected_outputs],
            "planned_output_dir": str(_planned_output_dir(command)),
        }
        for index, command in enumerate(commands, start=1)
    ]


def _stage_result_row(
    *,
    index: int,
    command: PipelineCommand,
    status: str,
    result: PipelineCommandResult | None = None,
    skip_reason: str = "",
    error_message: str = "",
) -> dict[str, object]:
    return {
        "command_order": index,
        "stage_order": _stage_order(command.stage),
        "stage_name": command.stage,
        "status": status,
        "returncode": "" if result is None or result.returncode is None else result.returncode,
        "command": render_command(command),
        "stdout_log": "" if result is None or result.stdout_log is None else str(result.stdout_log),
        "stderr_log": "" if result is None or result.stderr_log is None else str(result.stderr_log),
        "started_at": "" if result is None else result.started_at,
        "finished_at": "" if result is None else result.finished_at,
        "duration_seconds": "" if result is None else result.duration_seconds,
        "error_message": error_message,
        "planned": "true",
        "executed": _bool_text(status == "executed"),
        "skipped": _bool_text(status == "skipped"),
        "failed": _bool_text(status == "failed"),
        "required": _bool_text(command.required),
        "planned_output_dir": str(_planned_output_dir(command)),
        "expected_outputs": ";".join(str(path) for path in command.expected_outputs),
        "skip_reason": skip_reason,
    }


def _planned_stage_results(commands: Sequence[PipelineCommand]) -> list[dict[str, object]]:
    return [
        _stage_result_row(index=index, command=command, status="planned")
        for index, command in enumerate(commands, start=1)
    ]


def _missing_expected_outputs(command: PipelineCommand) -> list[Path]:
    return [Path(path) for path in command.expected_outputs if not Path(path).exists()]


def _execute_commands(
    *,
    args: argparse.Namespace,
    commands: Sequence[PipelineCommand],
    log_dir: Path,
    runner: CommandRunner | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    stop_reason = ""
    for index, command in enumerate(commands, start=1):
        if stop_reason:
            rows.append(_stage_result_row(index=index, command=command, status="skipped", skip_reason=stop_reason))
            continue

        result = run_command(command, runner=runner, log_dir=log_dir)
        status = "executed" if result.status == "success" else "failed"
        error_message = result.error_message
        if status == "executed":
            missing = _missing_expected_outputs(command)
            if missing:
                status = "failed"
                error_message = "Missing expected output after successful stage: " + "; ".join(
                    str(path) for path in missing
                )
        rows.append(
            _stage_result_row(
                index=index,
                command=command,
                status=status,
                result=result,
                error_message=error_message,
            )
        )
        if status == "failed" and args.stop_on_failure:
            stop_reason = f"Skipped because {command.stage} failed."
    return rows


def _final_classification(*, dry_run: bool, stage_results: Sequence[Mapping[str, object]]) -> str:
    if dry_run:
        return FINAL_CLASSIFICATION_DRY_RUN
    if any(row.get("status") == "failed" for row in stage_results):
        return FINAL_CLASSIFICATION_FAILED
    if any(row.get("status") == "skipped" for row in stage_results):
        return FINAL_CLASSIFICATION_STOPPED
    return FINAL_CLASSIFICATION_COMPLETED


def _aggregate_stage_status(stage_results: Sequence[Mapping[str, object]]) -> str:
    status_map = {
        "planned": "dry_run",
        "executed": "success",
        "failed": "failed",
        "skipped": "skipped",
    }
    return aggregate_status(
        [
            PipelineCommandResult(
                stage=str(row.get("stage_name") or ""),
                args=[""],
                status=status_map.get(str(row.get("status") or ""), "skipped"),
            )
            for row in stage_results
        ]
    )


def _next_action(final_classification: str, stress_output_dir: Path) -> str:
    if final_classification == FINAL_CLASSIFICATION_DRY_RUN:
        return "Review the command plan. To run stress validation manually, rerun with --execute."
    if final_classification == FINAL_CLASSIFICATION_COMPLETED:
        return f"Review stress outputs, then pass --stress-output-dir {stress_output_dir} to run_candidate_audit_pipeline.py."
    if final_classification == FINAL_CLASSIFICATION_FAILED:
        return "Review fixed_candidate_stress_validation_stage_results.csv and logs before rerunning."
    return "Review skipped stages and decide whether the run should be repeated with corrected inputs."


def _warning_rows(*, dry_run: bool, stage_results: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    rows = [
        _warning_row(
            warning_code="RESEARCH_ONLY_PIPELINE_ARTIFACT",
            severity="info",
            blocking=False,
            message="Fixed-candidate stress validation pipeline outputs are offline research artifacts only.",
            related_stage=DECISION_SCOPE,
        )
    ]
    if dry_run:
        rows.append(
            _warning_row(
                warning_code="DRY_RUN_ONLY_EXECUTION_NOT_RUN",
                severity="info",
                blocking=False,
                message="This dry-run only planned child commands; no child scripts were executed.",
                related_stage=DECISION_SCOPE,
            )
        )
    else:
        rows.append(
            _warning_row(
                warning_code="CONTROLLED_EXECUTION_RESEARCH_ONLY",
                severity="review",
                blocking=False,
                message="Execution mode runs existing offline stress-validation code only.",
                related_stage=DECISION_SCOPE,
            )
        )
    for row in stage_results:
        if row.get("status") == "failed":
            rows.append(
                _warning_row(
                    warning_code="PIPELINE_COMMAND_FAILED",
                    severity="blocking",
                    blocking=True,
                    message=str(row.get("error_message") or "Command failed."),
                    related_stage=str(row.get("stage_name") or ""),
                )
            )
        elif row.get("status") == "skipped":
            rows.append(
                _warning_row(
                    warning_code="PIPELINE_COMMAND_SKIPPED",
                    severity="review",
                    blocking=False,
                    message=str(row.get("skip_reason") or "Stage skipped."),
                    related_stage=str(row.get("stage_name") or ""),
                )
            )
    return rows


def _write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    run_id: str,
    paths: Mapping[str, Path],
    commands: Sequence[PipelineCommand],
    stage_results: Sequence[Mapping[str, object]],
    warnings: Sequence[Mapping[str, object]],
    final_classification: str,
    next_action: str,
    overwrite: bool,
) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Report already exists; pass --overwrite to replace it: {path}")
    result_by_order = {str(row.get("command_order")): row for row in stage_results}
    lines = [
        "# Fixed Candidate Stress Validation Pipeline Report",
        "",
        "## Research-Only Warning",
        "This wrapper is for offline fixed-candidate stress validation only.",
        "",
        "## Mode",
        "Dry-run mode planned the child command only; no child scripts were executed."
        if args.dry_run
        else "Execution mode ran existing offline stress-validation code through the shared runner.",
        "",
        "## Input Sources",
        f"- run_id: `{run_id}`",
        f"- symbol: `{str(args.symbol).strip().upper()}`",
        f"- direction: `{args.direction}`",
        f"- timeframe: `{str(args.timeframe).strip().upper()}`",
        f"- target_horizon: `{args.target_horizon}`",
        f"- target_family: `{args.target_family}`",
        f"- regime: `{args.regime_column}={args.regime_value}`",
        f"- db_path: `{args.db_path}`",
        f"- cost_config: `{args.cost_config or ''}`",
        f"- stress_cost_config: `{args.stress_cost_config or ''}`",
        f"- stress_output_dir: `{paths['stress_output_dir']}`",
        "",
        "## Planned/Executed Stage Table",
        "| Order | Stage | Status | Command |",
        "|---:|---|---|---|",
    ]
    for index, command in enumerate(commands, start=1):
        rendered = render_command(command).replace("|", "\\|")
        row = result_by_order.get(str(index), {})
        lines.append(f"| {index} | `{command.stage}` | `{row.get('status', '')}` | `{rendered}` |")

    report_blocking_warnings = sum(1 for row in warnings if _is_blocking(row))
    lines.extend(
        [
            "",
            "## Warnings",
            f"- total_warnings: `{len(warnings)}`",
            f"- blocking_warnings: `{report_blocking_warnings}`",
            f"- non_blocking_warnings: `{len(warnings) - report_blocking_warnings}`",
            "Detailed row-level warnings are preserved in `fixed_candidate_stress_validation_warnings.csv`.",
        ]
    )
    for row in warnings:
        lines.append(f"- `{row.get('warning_code')}`: {row.get('message')}")
    lines.extend(["", "## Final Classification", f"`{final_classification}`"])
    lines.extend(["", "## Next Action", next_action])
    lines.extend(["", "## Forbidden Actions"])
    for action in FORBIDDEN_ACTIONS:
        lines.append(f"- {action}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_pipeline(args: argparse.Namespace, *, runner: CommandRunner | None = None) -> dict[str, Path]:
    _validate_mode(args)
    run_id = _resolve_run_id(args.run_id)
    paths = build_pipeline_paths(args, run_id)
    require_existing_path(args.db_path, label="--db-path", kind="file")
    _validate_json_config(args.cost_config, label="--cost-config")
    _validate_json_config(args.stress_cost_config, label="--stress-cost-config")
    if args.candidate_summary_csv is not None:
        require_existing_path(args.candidate_summary_csv, label="--candidate-summary-csv", kind="file")
    ensure_output_dir(paths["artifact_output_dir"], overwrite=args.overwrite)

    commands = build_stage_commands(args, run_id, paths)
    stage_results = (
        _planned_stage_results(commands)
        if args.dry_run
        else _execute_commands(
            args=args,
            commands=commands,
            log_dir=paths["artifact_output_dir"] / "logs",
            runner=runner,
        )
    )
    final_classification = _final_classification(dry_run=bool(args.dry_run), stage_results=stage_results)
    aggregated_stage_status = _aggregate_stage_status(stage_results)
    next_action = _next_action(final_classification, paths["stress_output_dir"])
    warnings = _warning_rows(dry_run=bool(args.dry_run), stage_results=stage_results)
    blocking_warnings_count = sum(1 for row in warnings if _is_blocking(row))
    executed_stage_count = sum(1 for row in stage_results if row.get("executed") == "true")
    skipped_stage_count = sum(1 for row in stage_results if row.get("skipped") == "true")
    failed_stage_count = sum(1 for row in stage_results if row.get("failed") == "true")

    manifest_path = paths["artifact_output_dir"] / MANIFEST_FILE
    command_plan_path = paths["artifact_output_dir"] / COMMAND_PLAN_FILE
    stage_results_path = paths["artifact_output_dir"] / STAGE_RESULTS_FILE
    summary_path = paths["artifact_output_dir"] / SUMMARY_FILE
    report_path = paths["artifact_output_dir"] / REPORT_FILE
    warnings_path = paths["artifact_output_dir"] / WARNINGS_FILE
    planned_command_rows = _planned_command_rows(commands)
    output_artifacts = {
        "manifest": str(manifest_path),
        "command_plan": str(command_plan_path),
        "stage_results": str(stage_results_path),
        "summary": str(summary_path),
        "report": str(report_path),
        "warnings": str(warnings_path),
    }
    log_paths = sorted(
        {
            str(row.get("stdout_log"))
            for row in stage_results
            if str(row.get("stdout_log") or "").strip()
        }
        | {
            str(row.get("stderr_log"))
            for row in stage_results
            if str(row.get("stderr_log") or "").strip()
        }
    )
    status = (
        "dry_run"
        if final_classification == FINAL_CLASSIFICATION_DRY_RUN
        else final_classification.removeprefix("FIXED_CANDIDATE_STRESS_VALIDATION_PIPELINE_").lower()
    )

    write_manifest(
        manifest_path,
        {
            "generated_at": utc_now_iso(),
            "completed_at": utc_now_iso(),
            "run_id": run_id,
            "output_dir": str(paths["artifact_output_dir"]),
            "stress_output_dir": str(paths["stress_output_dir"]),
            "dry_run": bool(args.dry_run),
            "execute": bool(args.execute),
            "planned_stages": ["stress_validation"],
            "planned_commands": planned_command_rows,
            "stage_results": stage_results,
            "aggregated_stage_status": aggregated_stage_status,
            "status": status,
            "pipeline_scope": PIPELINE_SCOPE,
            "final_classification": final_classification,
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_warnings_count,
            "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
            "input_sources": {
                "symbol": str(args.symbol).strip().upper(),
                "direction": args.direction,
                "timeframe": str(args.timeframe).strip().upper(),
                "target_horizon": str(args.target_horizon),
                "target_family": args.target_family,
                "regime_column": args.regime_column,
                "regime_value": args.regime_value,
                "db_path": str(args.db_path),
                "cost_config": "" if args.cost_config is None else str(args.cost_config),
                "stress_cost_config": "" if args.stress_cost_config is None else str(args.stress_cost_config),
            },
            "output_artifacts": output_artifacts,
            "logs": log_paths,
            "forbidden_actions": FORBIDDEN_ACTIONS,
        },
        overwrite=args.overwrite,
    )
    write_command_plan_csv(
        command_plan_path,
        commands,
        overwrite=args.overwrite,
        fieldnames=COMMAND_PLAN_FIELDNAMES,
        row_builder=_command_plan_row_builder(),
    )
    _write_csv(stage_results_path, STAGE_RESULTS_FIELDNAMES, stage_results, overwrite=args.overwrite)
    _write_csv(warnings_path, WARNING_FIELDNAMES, warnings, overwrite=args.overwrite)
    _write_csv(
        summary_path,
        SUMMARY_FIELDNAMES,
        [
            {
                "run_id": run_id,
                "final_classification": final_classification,
                "decision_scope": DECISION_SCOPE,
                "pipeline_scope": PIPELINE_SCOPE,
                "dry_run": _bool_text(args.dry_run),
                "execute": _bool_text(args.execute),
                "planned_stage_count": len(commands),
                "executed_stage_count": executed_stage_count,
                "skipped_stage_count": skipped_stage_count,
                "failed_stage_count": failed_stage_count,
                "warnings_count": len(warnings),
                "blocking_warnings_count": blocking_warnings_count,
                "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
                "stress_output_dir": str(paths["stress_output_dir"]),
                "forbidden_actions": ";".join(FORBIDDEN_ACTIONS),
                "next_action": next_action,
            }
        ],
        overwrite=args.overwrite,
    )
    _write_report(
        report_path,
        args=args,
        run_id=run_id,
        paths=paths,
        commands=commands,
        stage_results=stage_results,
        warnings=warnings,
        final_classification=final_classification,
        next_action=next_action,
        overwrite=args.overwrite,
    )
    return {
        "output_dir": paths["artifact_output_dir"],
        "stress_output_dir": paths["stress_output_dir"],
        "manifest": manifest_path,
        "command_plan": command_plan_path,
        "stage_results": stage_results_path,
        "summary": summary_path,
        "report": report_path,
        "warnings": warnings_path,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        outputs = run_pipeline(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Fixed-candidate stress validation pipeline artifacts written to {outputs['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
