"""Plan or run the combined hypothesis validation sub-pipeline."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

try:
    from research_costs import validate_orchestrator_cost_preflight
    from research_pipeline_utils import (
        CommandRunner,
        PipelineCommand,
        PipelineCommandResult,
        aggregate_status,
        default_run_id,
        ensure_output_dir,
        render_command,
        run_command,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )
    from run_research_validation_pipeline import (
        DEFAULT_COMBINED_EVALUATIONS_DIR,
        DEFAULT_DB_PATH,
        DEFAULT_FINAL_SCORECARD_OUTPUT_DIR,
        DEFAULT_SYMBOLS,
        DEFAULT_TARGET_HORIZON,
        DEFAULT_TIMEFRAME,
        DEFAULT_VALIDATION_OUTPUT_DIR,
        normalize_symbols,
        resolve_combined_input,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_combined_validation_pipeline
    from scripts.research_costs import validate_orchestrator_cost_preflight
    from scripts.research_pipeline_utils import (
        CommandRunner,
        PipelineCommand,
        PipelineCommandResult,
        aggregate_status,
        default_run_id,
        ensure_output_dir,
        render_command,
        run_command,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )
    from scripts.run_research_validation_pipeline import (
        DEFAULT_COMBINED_EVALUATIONS_DIR,
        DEFAULT_DB_PATH,
        DEFAULT_FINAL_SCORECARD_OUTPUT_DIR,
        DEFAULT_SYMBOLS,
        DEFAULT_TARGET_HORIZON,
        DEFAULT_TIMEFRAME,
        DEFAULT_VALIDATION_OUTPUT_DIR,
        normalize_symbols,
        resolve_combined_input,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "combined_validation_pipeline"

MANIFEST_FILE = "combined_validation_manifest.json"
COMMAND_PLAN_FILE = "combined_validation_command_plan.csv"
STAGE_RESULTS_FILE = "combined_validation_stage_results.csv"
SUMMARY_FILE = "combined_validation_summary.csv"
REPORT_FILE = "combined_validation_report.md"
WARNINGS_FILE = "combined_validation_warnings.csv"

DECISION_SCOPE = "combined_validation_pipeline"
PIPELINE_SCOPE = "combined_validation_research_orchestration"
FINAL_CLASSIFICATION_DRY_RUN = "COMBINED_VALIDATION_PIPELINE_DRY_RUN_PLANNED"
FINAL_CLASSIFICATION_COMPLETED = "COMBINED_VALIDATION_PIPELINE_COMPLETED"
FINAL_CLASSIFICATION_FAILED = "COMBINED_VALIDATION_PIPELINE_FAILED"
FINAL_CLASSIFICATION_STOPPED = "COMBINED_VALIDATION_PIPELINE_STOPPED"

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
    "stage",
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
    "stage",
    "stage_name",
    "status",
    "planned",
    "executed",
    "skipped",
    "failed",
    "required",
    "command",
    "returncode",
    "started_at",
    "finished_at",
    "duration_seconds",
    "error_message",
    "stdout_log",
    "stderr_log",
    "planned_output_dir",
    "expected_outputs",
    "skip_reason",
    "failure_reason",
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
    "forbidden_actions",
    "next_action",
]


@dataclass(frozen=True)
class StageSpec:
    stage: str
    script_name: str
    description: str
    output_dir_key: str
    expected_files: tuple[str, ...]
    heavy: bool = True
    required: bool = True


STAGE_SPECS = [
    StageSpec(
        stage="combined_evaluation",
        script_name="evaluate_combined_hypotheses.py",
        description="Evaluate existing combined hypothesis outputs and select validation candidates.",
        output_dir_key="combined_evaluation_dir",
        expected_files=("selected_combined_hypotheses.csv",),
    ),
    StageSpec(
        stage="yearly_validation",
        script_name="validate_hypotheses_by_year.py",
        description="Validate selected combined hypotheses by year and symbol.",
        output_dir_key="validation_output_dir",
        expected_files=(
            "final_research_candidates.csv",
            "final_research_candidates_report.md",
            "pair_specific_candidates.csv",
            "pair_specific_candidates_report.md",
        ),
    ),
    StageSpec(
        stage="final_feature_scorecard",
        script_name="build_final_feature_scorecard.py",
        description="Build the final feature and condition scorecards from validation evidence.",
        output_dir_key="scorecard_output_dir",
        expected_files=(
            "final_feature_scorecard.csv",
            "pair_specific_feature_scorecard.csv",
            "final_feature_scorecard_report.md",
        ),
    ),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or run the research-only combined validation pipeline. "
            "This wrapper evaluates combined hypotheses, validates them by year, "
            "and builds the final feature scorecard."
        )
    )
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--target-horizon", type=int, default=DEFAULT_TARGET_HORIZON)
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--run-id")
    parser.add_argument("--combined-input-dir", "--combined-run-dir", dest="combined_input_dir", type=Path)
    parser.add_argument("--combined-evaluations-dir", type=Path, default=DEFAULT_COMBINED_EVALUATIONS_DIR)
    parser.add_argument("--validation-output-dir", type=Path, default=DEFAULT_VALIDATION_OUTPUT_DIR)
    parser.add_argument("--scorecard-output-dir", type=Path, default=DEFAULT_FINAL_SCORECARD_OUTPUT_DIR)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--evaluate-min-trades", type=int, default=300)
    parser.add_argument("--evaluate-min-symbols", type=int, default=2)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--years", nargs="+", type=int)
    parser.add_argument("--include-incomplete-years", action="store_true")
    parser.add_argument("--min-trades-per-year", type=int, default=100)
    parser.add_argument("--min-positive-year-ratio", type=float, default=0.75)
    parser.add_argument("--min-positive-symbol-ratio", type=float, default=0.75)
    parser.add_argument("--overwrite-validation", action="store_true")
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
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


def _resolve_run_id(run_id: str | None, fallback: str) -> str:
    value = str(run_id or fallback or "").strip()
    if not value:
        value = default_run_id()
    if "/" in value or "\\" in value:
        raise ValueError("--run-id must be a single path segment, not a nested path.")
    return value


def _script_path(script_name: str) -> str:
    return str(SCRIPTS_DIR / script_name)


def _stage_output_dirs(args: argparse.Namespace, run_id: str) -> dict[str, Path]:
    return {
        "combined_evaluation_dir": Path(args.combined_evaluations_dir) / run_id / args.direction,
        "validation_output_dir": Path(args.validation_output_dir) / run_id / args.direction,
        "scorecard_output_dir": Path(args.scorecard_output_dir) / run_id / args.direction,
    }


def _expected_outputs(spec: StageSpec, stage_dirs: Mapping[str, Path]) -> list[Path]:
    output_dir = stage_dirs[spec.output_dir_key]
    return [output_dir / name for name in spec.expected_files]


def _cost_mode_args(cost_mode: str, return_mode: str) -> list[str]:
    return ["--cost-mode", cost_mode, "--return-mode", return_mode]


def _cost_estimation_args(args: argparse.Namespace, cost_mode: str, return_mode: str) -> list[str]:
    values = _cost_mode_args(cost_mode, return_mode)
    if args.cost_config is not None:
        values.extend(["--cost-config", str(args.cost_config)])
    if args.strict_cost_config:
        values.append("--strict-cost-config")
    return values


def build_stage_commands(
    *,
    args: argparse.Namespace,
    run_id: str,
    combined_input_dir: Path,
    symbols: Sequence[str],
    timeframe: str,
    cost_mode: str,
    return_mode: str,
) -> tuple[list[PipelineCommand], dict[str, Path]]:
    stage_dirs = _stage_output_dirs(args, run_id)
    selected_hypotheses_file = stage_dirs["combined_evaluation_dir"] / "selected_combined_hypotheses.csv"
    python_executable = str(args.python_executable or sys.executable)
    commands = [
        PipelineCommand(
            stage="combined_evaluation",
            args=[
                python_executable,
                _script_path("evaluate_combined_hypotheses.py"),
                "--input-dir",
                str(combined_input_dir),
                "--output-dir",
                str(args.combined_evaluations_dir),
                "--run-id",
                run_id,
                "--direction",
                args.direction,
                "--min-trades",
                args.evaluate_min_trades,
                "--min-symbols",
                args.evaluate_min_symbols,
                "--top-n",
                args.top_n,
                *_cost_mode_args(cost_mode, return_mode),
            ],
            cwd=BASE_DIR,
            expected_outputs=_expected_outputs(STAGE_SPECS[0], stage_dirs),
            heavy=True,
            required=True,
            description=STAGE_SPECS[0].description,
        ),
        PipelineCommand(
            stage="yearly_validation",
            args=[
                python_executable,
                _script_path("validate_hypotheses_by_year.py"),
                "--hypotheses-file",
                str(selected_hypotheses_file),
                "--run-id",
                run_id,
                "--direction",
                args.direction,
                "--symbols",
                *symbols,
                "--timeframe",
                timeframe,
                "--target-horizon",
                args.target_horizon,
                "--db-path",
                str(args.db_path),
                "--output-dir",
                str(args.validation_output_dir),
                "--min-trades-per-year",
                args.min_trades_per_year,
                "--min-positive-year-ratio",
                args.min_positive_year_ratio,
                "--min-positive-symbol-ratio",
                args.min_positive_symbol_ratio,
                *_cost_estimation_args(args, cost_mode, return_mode),
            ],
            cwd=BASE_DIR,
            expected_outputs=_expected_outputs(STAGE_SPECS[1], stage_dirs),
            heavy=True,
            required=True,
            description=STAGE_SPECS[1].description,
        ),
        PipelineCommand(
            stage="final_feature_scorecard",
            args=[
                python_executable,
                _script_path("build_final_feature_scorecard.py"),
                "--run-id",
                run_id,
                "--direction",
                args.direction,
                "--validation-dir",
                str(args.validation_output_dir),
                "--combined-evaluations-dir",
                str(args.combined_evaluations_dir),
                "--output-dir",
                str(args.scorecard_output_dir),
                "--min-trades-per-year",
                args.min_trades_per_year,
                *_cost_mode_args(cost_mode, return_mode),
            ],
            cwd=BASE_DIR,
            expected_outputs=_expected_outputs(STAGE_SPECS[2], stage_dirs),
            heavy=True,
            required=True,
            description=STAGE_SPECS[2].description,
        ),
    ]

    if args.start_year is not None:
        commands[1].args.extend(["--start-year", str(args.start_year)])
    if args.end_year is not None:
        commands[1].args.extend(["--end-year", str(args.end_year)])
    if args.years:
        commands[1].args.append("--years")
        commands[1].args.extend(str(year) for year in args.years)
    if args.include_incomplete_years:
        commands[1].args.append("--include-incomplete-years")
    if args.overwrite_validation:
        commands[1].args.append("--overwrite")
        commands[2].args.append("--overwrite")

    return commands, stage_dirs


def _command_plan_row_builder(
    stage_dirs: Mapping[str, Path],
) -> Any:
    def row_builder(index: int, command: PipelineCommand) -> dict[str, object]:
        spec = next(item for item in STAGE_SPECS if item.stage == command.stage)
        return {
            "command_order": index,
            "stage_order": index,
            "stage_name": command.stage,
            "planned_output_dir": str(stage_dirs[spec.output_dir_key]),
        }

    return row_builder


def _planned_command_rows(commands: Sequence[PipelineCommand], stage_dirs: Mapping[str, Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, command in enumerate(commands, start=1):
        spec = next(item for item in STAGE_SPECS if item.stage == command.stage)
        rows.append(
            {
                "command_order": index,
                "stage_order": index,
                "stage": command.stage,
                "stage_name": command.stage,
                "command": render_command(command),
                "heavy": bool(command.heavy),
                "required": bool(command.required),
                "description": command.description,
                "cwd": str(command.cwd or ""),
                "expected_outputs": [str(path) for path in command.expected_outputs],
                "planned_output_dir": str(stage_dirs[spec.output_dir_key]),
            }
        )
    return rows


def _stage_result_row(
    *,
    index: int,
    command: PipelineCommand,
    status: str,
    planned_output_dir: Path,
    result: PipelineCommandResult | None = None,
    skip_reason: str = "",
    failure_reason: str = "",
) -> dict[str, object]:
    return {
        "command_order": index,
        "stage_order": index,
        "stage": command.stage,
        "stage_name": command.stage,
        "status": status,
        "planned": "true",
        "executed": _bool_text(status == "executed"),
        "skipped": _bool_text(status == "skipped"),
        "failed": _bool_text(status == "failed"),
        "required": _bool_text(command.required),
        "command": render_command(command),
        "returncode": "" if result is None or result.returncode is None else result.returncode,
        "started_at": "" if result is None else result.started_at,
        "finished_at": "" if result is None else result.finished_at,
        "duration_seconds": "" if result is None else result.duration_seconds,
        "error_message": failure_reason,
        "stdout_log": "" if result is None or result.stdout_log is None else str(result.stdout_log),
        "stderr_log": "" if result is None or result.stderr_log is None else str(result.stderr_log),
        "planned_output_dir": str(planned_output_dir),
        "expected_outputs": ";".join(str(path) for path in command.expected_outputs),
        "skip_reason": skip_reason,
        "failure_reason": failure_reason,
    }


def _planned_stage_results(commands: Sequence[PipelineCommand], stage_dirs: Mapping[str, Path]) -> list[dict[str, object]]:
    rows = []
    for index, command in enumerate(commands, start=1):
        spec = next(item for item in STAGE_SPECS if item.stage == command.stage)
        rows.append(
            _stage_result_row(
                index=index,
                command=command,
                status="planned",
                planned_output_dir=stage_dirs[spec.output_dir_key],
            )
        )
    return rows


def _missing_expected_outputs(command: PipelineCommand) -> list[Path]:
    return [Path(path) for path in command.expected_outputs if not Path(path).exists()]


def _execute_stage_commands(
    *,
    args: argparse.Namespace,
    commands: Sequence[PipelineCommand],
    stage_dirs: Mapping[str, Path],
    log_dir: Path,
    runner: CommandRunner | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    stop_reason = ""
    for index, command in enumerate(commands, start=1):
        spec = next(item for item in STAGE_SPECS if item.stage == command.stage)
        planned_output_dir = stage_dirs[spec.output_dir_key]
        if stop_reason:
            rows.append(
                _stage_result_row(
                    index=index,
                    command=command,
                    status="skipped",
                    planned_output_dir=planned_output_dir,
                    skip_reason=stop_reason,
                )
            )
            continue

        result = run_command(command, runner=runner, log_dir=log_dir)
        failure_reason = result.error_message
        status = "executed" if result.status == "success" else "failed"
        if status == "executed":
            missing = _missing_expected_outputs(command)
            if missing:
                status = "failed"
                failure_reason = "Missing expected output after successful stage: " + "; ".join(
                    str(path) for path in missing
                )
        row = _stage_result_row(
            index=index,
            command=command,
            status=status,
            planned_output_dir=planned_output_dir,
            result=result,
            failure_reason=failure_reason,
        )
        rows.append(row)
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
                stage=str(row.get("stage") or ""),
                args=[""],
                status=status_map.get(str(row.get("status") or ""), "skipped"),
            )
            for row in stage_results
        ]
    )


def _next_action(final_classification: str) -> str:
    if final_classification == FINAL_CLASSIFICATION_DRY_RUN:
        return "Review the command plan. To execute manually, rerun with --execute. Heavy stages must be user-run only."
    if final_classification == FINAL_CLASSIFICATION_COMPLETED:
        return "Review the combined validation and final scorecard outputs before any downstream research-only review."
    if final_classification == FINAL_CLASSIFICATION_FAILED:
        return "Review combined_validation_stage_results.csv and logs before rerunning with corrected inputs."
    return "Review skipped stages and decide whether the run should be repeated with corrected inputs."


def _warning_rows(*, dry_run: bool, stage_results: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    rows = [
        _warning_row(
            warning_code="RESEARCH_ONLY_PIPELINE_ARTIFACT",
            severity="info",
            blocking=False,
            message="Combined validation pipeline outputs are offline research artifacts only.",
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
                message="Execution mode runs existing offline validation child commands only; outputs remain research-only.",
                related_stage=DECISION_SCOPE,
            )
        )
    for row in stage_results:
        if row.get("status") == "failed":
            rows.append(
                _warning_row(
                    warning_code="PIPELINE_STAGE_FAILED",
                    severity="blocking",
                    blocking=True,
                    message=str(row.get("failure_reason") or "Stage failed."),
                    related_stage=str(row.get("stage") or ""),
                )
            )
        elif row.get("status") == "skipped":
            rows.append(
                _warning_row(
                    warning_code="PIPELINE_STAGE_SKIPPED",
                    severity="review",
                    blocking=False,
                    message=str(row.get("skip_reason") or "Stage skipped."),
                    related_stage=str(row.get("stage") or ""),
                )
            )
    return rows


def _write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    run_id: str,
    output_dir: Path,
    combined_input_dir: Path,
    commands: Sequence[PipelineCommand],
    stage_dirs: Mapping[str, Path],
    stage_results: Sequence[Mapping[str, object]],
    warnings: Sequence[Mapping[str, object]],
    final_classification: str,
    next_action: str,
    overwrite: bool,
) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Report already exists; pass --overwrite to replace it: {path}")

    lines = [
        "# Combined Validation Pipeline Report",
        "",
        "## Research-Only Warning",
        "This wrapper is for offline research validation only. It does not create operational instructions.",
        "",
        "## Mode",
        (
            "Dry-run mode planned the child commands only; no child scripts were executed."
            if args.dry_run
            else "Execution mode ran existing offline validation child commands through the shared runner."
        ),
        "",
        "## Input Sources",
        f"- run_id: `{run_id}`",
        f"- combined_input_dir: `{combined_input_dir}`",
        f"- output_dir: `{output_dir}`",
        f"- direction: `{args.direction}`",
        f"- symbols: `{' '.join(normalize_symbols(args.symbols))}`",
        f"- timeframe: `{str(args.timeframe).strip().upper()}`",
        f"- target_horizon: `{args.target_horizon}`",
        f"- cost_mode: `{args.cost_mode}`",
        f"- return_mode: `{args.return_mode}`",
        "",
        "## Stage Table",
        "| Order | Stage | Status | Required | Command |",
        "|---:|---|---|---|---|",
    ]
    result_by_stage = {str(row.get("stage")): row for row in stage_results}
    for index, command in enumerate(commands, start=1):
        rendered = render_command(command).replace("|", "\\|")
        row = result_by_stage.get(command.stage, {})
        lines.append(
            f"| {index} | `{command.stage}` | `{row.get('status', '')}` | "
            f"{str(bool(command.required)).lower()} | `{rendered}` |"
        )

    lines.extend(["", "## Outputs"])
    for command in commands:
        spec = next(item for item in STAGE_SPECS if item.stage == command.stage)
        lines.append(f"- `{command.stage}` -> `{stage_dirs[spec.output_dir_key]}`")
        for expected_output in command.expected_outputs:
            lines.append(f"  - `{expected_output}`")

    report_blocking_warnings = sum(1 for row in warnings if _is_blocking(row))
    lines.extend(
        [
            "",
            "## Warnings",
            f"- total_warnings: `{len(warnings)}`",
            f"- blocking_warnings: `{report_blocking_warnings}`",
            f"- non_blocking_warnings: `{len(warnings) - report_blocking_warnings}`",
            "Detailed row-level warnings are preserved in `combined_validation_warnings.csv`.",
        ]
    )
    if warnings:
        for row in warnings:
            lines.append(f"- `{row.get('warning_code')}`: {row.get('message')}")
    else:
        lines.append("- None.")

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
    symbols = normalize_symbols(args.symbols)
    if not symbols:
        raise ValueError("At least one symbol is required.")
    timeframe = str(args.timeframe).strip().upper()
    cost_mode, return_mode = validate_orchestrator_cost_preflight(
        cost_mode=args.cost_mode,
        return_mode=args.return_mode,
        cost_config_path=args.cost_config,
    )
    resolved_run_id, combined_input_dir = resolve_combined_input(args)
    run_id = _resolve_run_id(args.run_id, resolved_run_id)
    output_dir = Path(args.output_root) / run_id
    ensure_output_dir(output_dir, overwrite=args.overwrite)

    commands, stage_dirs = build_stage_commands(
        args=args,
        run_id=run_id,
        combined_input_dir=combined_input_dir,
        symbols=symbols,
        timeframe=timeframe,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )
    log_dir = output_dir / "logs"
    stage_results = (
        _planned_stage_results(commands, stage_dirs)
        if args.dry_run
        else _execute_stage_commands(
            args=args,
            commands=commands,
            stage_dirs=stage_dirs,
            log_dir=log_dir,
            runner=runner,
        )
    )
    final_classification = _final_classification(dry_run=bool(args.dry_run), stage_results=stage_results)
    aggregated_stage_status = _aggregate_stage_status(stage_results)
    next_action = _next_action(final_classification)
    warnings = _warning_rows(dry_run=bool(args.dry_run), stage_results=stage_results)
    blocking_warnings_count = sum(1 for row in warnings if _is_blocking(row))
    executed_stage_count = sum(1 for row in stage_results if row.get("executed") == "true")
    skipped_stage_count = sum(1 for row in stage_results if row.get("skipped") == "true")
    failed_stage_count = sum(1 for row in stage_results if row.get("failed") == "true")

    manifest_path = output_dir / MANIFEST_FILE
    command_plan_path = output_dir / COMMAND_PLAN_FILE
    stage_results_path = output_dir / STAGE_RESULTS_FILE
    summary_path = output_dir / SUMMARY_FILE
    report_path = output_dir / REPORT_FILE
    warnings_path = output_dir / WARNINGS_FILE

    command_plan_rows = _planned_command_rows(commands, stage_dirs)
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
        else final_classification.removeprefix("COMBINED_VALIDATION_PIPELINE_").lower()
    )

    write_manifest(
        manifest_path,
        {
            "generated_at": utc_now_iso(),
            "completed_at": utc_now_iso(),
            "run_id": run_id,
            "output_dir": str(output_dir),
            "dry_run": bool(args.dry_run),
            "execute": bool(args.execute),
            "planned_stages": [command.stage for command in commands],
            "planned_commands": command_plan_rows,
            "stage_results": stage_results,
            "aggregated_stage_status": aggregated_stage_status,
            "status": status,
            "pipeline_scope": PIPELINE_SCOPE,
            "final_classification": final_classification,
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_warnings_count,
            "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
            "input_sources": {
                "combined_input_dir": str(combined_input_dir),
                "combined_evaluations_dir": str(args.combined_evaluations_dir),
                "validation_output_dir": str(args.validation_output_dir),
                "scorecard_output_dir": str(args.scorecard_output_dir),
                "db_path": str(args.db_path),
                "cost_config": "" if args.cost_config is None else str(args.cost_config),
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
        row_builder=_command_plan_row_builder(stage_dirs),
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
        output_dir=output_dir,
        combined_input_dir=combined_input_dir,
        commands=commands,
        stage_dirs=stage_dirs,
        stage_results=stage_results,
        warnings=warnings,
        final_classification=final_classification,
        next_action=next_action,
        overwrite=args.overwrite,
    )

    return {
        "output_dir": output_dir,
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
    print(f"Combined validation pipeline artifacts written to {outputs['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
