"""Plan or run the upstream hypothesis discovery sub-pipeline."""

from __future__ import annotations

import argparse
import csv
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
        require_existing_path,
        run_command,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_hypothesis_discovery_pipeline
    from scripts.research_costs import validate_orchestrator_cost_preflight
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
DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
DEFAULT_TIMEFRAME = "M15"
DEFAULT_TARGET_HORIZON = 10
DEFAULT_INPUT_BACKTEST_ROOT = BASE_DIR / "reports" / "backtests"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "hypothesis_discovery_pipeline"
DEFAULT_COMBINED_OUTPUT_ROOT = BASE_DIR / "reports" / "backtests" / "combined" / "runs"
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"

MANIFEST_FILE = "hypothesis_discovery_manifest.json"
COMMAND_PLAN_FILE = "hypothesis_discovery_command_plan.csv"
STAGE_RESULTS_FILE = "hypothesis_discovery_stage_results.csv"
SUMMARY_FILE = "hypothesis_discovery_summary.csv"
REPORT_FILE = "hypothesis_discovery_report.md"
WARNINGS_FILE = "hypothesis_discovery_warnings.csv"

DECISION_SCOPE = "hypothesis_discovery_pipeline"
PIPELINE_SCOPE = "hypothesis_discovery_research_orchestration"
FINAL_CLASSIFICATION_DRY_RUN = "HYPOTHESIS_DISCOVERY_PIPELINE_DRY_RUN_PLANNED"
FINAL_CLASSIFICATION_COMPLETED = "HYPOTHESIS_DISCOVERY_PIPELINE_COMPLETED"
FINAL_CLASSIFICATION_COMPLETED_WITH_UNCOMBINABLE_SYMBOLS = (
    "HYPOTHESIS_DISCOVERY_PIPELINE_COMPLETED_WITH_UNCOMBINABLE_SYMBOLS"
)
FINAL_CLASSIFICATION_FAILED = "HYPOTHESIS_DISCOVERY_PIPELINE_FAILED"
FINAL_CLASSIFICATION_STOPPED = "HYPOTHESIS_DISCOVERY_PIPELINE_STOPPED"
FINAL_CLASSIFICATION_STOPPED_NO_COMBINABLE_HYPOTHESES = (
    "HYPOTHESIS_DISCOVERY_PIPELINE_STOPPED_NO_COMBINABLE_HYPOTHESES"
)
INSUFFICIENT_HYPOTHESES_MESSAGE = "Need at least two usable select/watchlist hypotheses to combine."
INSUFFICIENT_HYPOTHESES_FAILURE_REASON = "Insufficient selected/watchlist hypotheses for combined backtest."
INSUFFICIENT_HYPOTHESES_WARNING_CODE = "insufficient_selected_hypotheses_for_combined_backtest"

FORBIDDEN_ACTIONS = [
    "live " + "trading",
    "trading " + "signal",
    "broker " + "execution",
    "position " + "sizing",
    "TP/SL " + "optimization",
    "new feature search beyond existing selected hypotheses",
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
    "symbol",
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
    "symbol",
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
    "planned_command_count",
    "executed_command_count",
    "skipped_command_count",
    "failed_command_count",
    "warnings_count",
    "blocking_warnings_count",
    "non_blocking_warnings_count",
    "combined_output_dir",
    "forbidden_actions",
    "next_action",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or run the research-only hypothesis discovery pipeline that prepares "
            "run-scoped combined hypothesis outputs for combined validation."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--target-horizon", type=int, choices=(5, 10, 20), default=DEFAULT_TARGET_HORIZON)
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--input-backtest-root",
        type=Path,
        default=DEFAULT_INPUT_BACKTEST_ROOT,
        help="Root directory containing direction subfolders such as long/short.",
    )
    input_group.add_argument(
        "--input-backtest-dir",
        type=Path,
        help="Direction-specific exploratory backtest folder; direction is not appended.",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--combined-output-root", type=Path, default=DEFAULT_COMBINED_OUTPUT_ROOT)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--evaluate-min-trades", type=int, default=200)
    parser.add_argument("--evaluate-good-trades", type=int, default=500)
    parser.add_argument("--select-top-n", type=int, default=5)
    parser.add_argument("--select-min-symbols", type=int, default=2)
    parser.add_argument("--select-min-score-to-select", type=int, default=7)
    parser.add_argument("--combined-max-combination-size", type=int, default=3)
    parser.add_argument("--combined-min-trades", type=int, default=300)
    parser.add_argument("--combined-top-hypotheses", type=int, default=10)
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--stop-on-failure", action=argparse.BooleanOptionalAction, default=True)
    return parser


def normalize_symbols(values: Sequence[str]) -> list[str]:
    symbols: list[str] = []
    for value in values:
        for token in str(value).split(","):
            symbol = token.strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols


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


def _script_path(script_name: str) -> str:
    return str(SCRIPTS_DIR / script_name)


def _stage_group(stage: str) -> str:
    return "combined_backtest" if stage.startswith("combined_backtest_") else stage


def _is_combined_backtest_stage(stage: object) -> bool:
    return _stage_group(str(stage or "")) == "combined_backtest"


def _stage_order(stage: str) -> int:
    stage_group = _stage_group(stage)
    if stage_group == "backtest_evaluation":
        return 1
    if stage_group == "hypothesis_selection":
        return 2
    if stage_group == "combined_backtest":
        return 3
    raise ValueError(f"Unknown hypothesis discovery stage: {stage}")


def _command_symbol(command: PipelineCommand) -> str:
    if command.stage.startswith("combined_backtest_"):
        return command.stage.removeprefix("combined_backtest_")
    return ""


def _planned_output_dir(command: PipelineCommand) -> Path:
    if not command.expected_outputs:
        return Path("")
    return Path(command.expected_outputs[0]).parent


def _cost_mode_args(cost_mode: str, return_mode: str) -> list[str]:
    return ["--cost-mode", cost_mode, "--return-mode", return_mode]


def _cost_estimation_args(args: argparse.Namespace, cost_mode: str, return_mode: str) -> list[str]:
    values = _cost_mode_args(cost_mode, return_mode)
    if args.cost_config is not None:
        values.extend(["--cost-config", str(args.cost_config)])
    if args.strict_cost_config:
        values.append("--strict-cost-config")
    return values


def build_pipeline_paths(args: argparse.Namespace, run_id: str) -> dict[str, Path]:
    if args.input_backtest_dir is not None:
        direction_input_dir = Path(args.input_backtest_dir)
        input_backtest_root = direction_input_dir.parent
    else:
        input_backtest_root = Path(args.input_backtest_root)
        if input_backtest_root.name.lower() == str(args.direction).lower():
            raise ValueError(
                "--input-backtest-root should point to the parent directory containing long/short. "
                "Use --input-backtest-dir for a direction-specific folder."
            )
        direction_input_dir = input_backtest_root / args.direction
    combined_output_dir = Path(args.combined_output_root) / run_id / args.direction
    return {
        "artifact_output_dir": Path(args.output_root) / run_id,
        "input_backtest_root": input_backtest_root,
        "direction_input_dir": direction_input_dir,
        "discovery_output_dir": direction_input_dir,
        "combined_output_dir": combined_output_dir,
    }


def build_stage_commands(
    *,
    args: argparse.Namespace,
    run_id: str,
    symbols: Sequence[str],
    timeframe: str,
    cost_mode: str,
    return_mode: str,
    paths: Mapping[str, Path],
) -> list[PipelineCommand]:
    python_executable = str(args.python_executable or sys.executable)
    discovery_output_dir = paths["discovery_output_dir"]
    combined_output_dir = paths["combined_output_dir"]
    commands = [
        PipelineCommand(
            stage="backtest_evaluation",
            args=[
                python_executable,
                _script_path("evaluate_backtest_results.py"),
                "--input-dir",
                str(paths["direction_input_dir"]),
                "--output-dir",
                str(discovery_output_dir),
                "--direction",
                args.direction,
                "--min-trades",
                args.evaluate_min_trades,
                "--good-trades",
                args.evaluate_good_trades,
                *_cost_mode_args(cost_mode, return_mode),
            ],
            cwd=BASE_DIR,
            expected_outputs=[
                discovery_output_dir / "evaluated_backtest_results.csv",
                discovery_output_dir / "cross_pair_summary.csv",
                discovery_output_dir / "research_decision_summary.txt",
            ],
            heavy=True,
            required=True,
            description="Evaluate exploratory backtest summaries against their baselines.",
        ),
        PipelineCommand(
            stage="hypothesis_selection",
            args=[
                python_executable,
                _script_path("select_research_hypotheses.py"),
                "--input-dir",
                str(discovery_output_dir),
                "--output-dir",
                str(discovery_output_dir),
                "--direction",
                args.direction,
                "--top-n",
                args.select_top_n,
                "--min-symbols",
                args.select_min_symbols,
                "--min-score-to-select",
                args.select_min_score_to_select,
            ],
            cwd=BASE_DIR,
            expected_outputs=[
                discovery_output_dir / "selected_research_hypotheses.csv",
                discovery_output_dir / "selected_research_hypotheses.md",
            ],
            heavy=False,
            required=True,
            description="Select robust research hypotheses for controlled combined testing.",
        ),
    ]

    for symbol in symbols:
        symbol_output_dir = combined_output_dir / f"{symbol}_{timeframe}_h{args.target_horizon}"
        commands.append(
            PipelineCommand(
                stage=f"combined_backtest_{symbol}",
                args=[
                    python_executable,
                    _script_path("backtest_combined_hypotheses.py"),
                    "--symbol",
                    symbol,
                    "--timeframe",
                    timeframe,
                    "--target-horizon",
                    args.target_horizon,
                    "--direction",
                    args.direction,
                    "--input-dir",
                    str(discovery_output_dir),
                    "--output-dir",
                    str(symbol_output_dir),
                    "--max-combination-size",
                    args.combined_max_combination_size,
                    "--min-trades",
                    args.combined_min_trades,
                    "--top-hypotheses",
                    args.combined_top_hypotheses,
                    "--db-path",
                    str(args.db_path),
                    *_cost_estimation_args(args, cost_mode, return_mode),
                ],
                cwd=BASE_DIR,
                expected_outputs=[
                    symbol_output_dir / "combined_hypotheses_summary.csv",
                    symbol_output_dir / "combined_hypotheses_top.csv",
                    symbol_output_dir / "combined_hypotheses_report.md",
                ],
                heavy=True,
                required=True,
                description="Backtest controlled combinations for one symbol using selected hypotheses.",
            )
        )
    return commands


def _command_plan_row_builder() -> Any:
    def row_builder(index: int, command: PipelineCommand) -> dict[str, object]:
        return {
            "command_order": index,
            "stage_order": _stage_order(command.stage),
            "stage_name": command.stage,
            "planned_output_dir": str(_planned_output_dir(command)),
            "symbol": _command_symbol(command),
        }

    return row_builder


def _planned_command_rows(commands: Sequence[PipelineCommand]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, command in enumerate(commands, start=1):
        rows.append(
            {
                "command_order": index,
                "stage_order": _stage_order(command.stage),
                "stage": command.stage,
                "stage_name": command.stage,
                "stage_group": _stage_group(command.stage),
                "command": render_command(command),
                "heavy": bool(command.heavy),
                "required": bool(command.required),
                "description": command.description,
                "cwd": str(command.cwd or ""),
                "expected_outputs": [str(path) for path in command.expected_outputs],
                "planned_output_dir": str(_planned_output_dir(command)),
                "symbol": _command_symbol(command),
            }
        )
    return rows


def _stage_result_row(
    *,
    index: int,
    command: PipelineCommand,
    status: str,
    result: PipelineCommandResult | None = None,
    skip_reason: str = "",
    failure_reason: str = "",
) -> dict[str, object]:
    return {
        "command_order": index,
        "stage_order": _stage_order(command.stage),
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
        "planned_output_dir": str(_planned_output_dir(command)),
        "expected_outputs": ";".join(str(path) for path in command.expected_outputs),
        "symbol": _command_symbol(command),
        "skip_reason": skip_reason,
        "failure_reason": failure_reason,
    }


def _planned_stage_results(commands: Sequence[PipelineCommand]) -> list[dict[str, object]]:
    return [
        _stage_result_row(index=index, command=command, status="planned")
        for index, command in enumerate(commands, start=1)
    ]


def _missing_expected_outputs(command: PipelineCommand) -> list[Path]:
    return [Path(path) for path in command.expected_outputs if not Path(path).exists()]


def _result_contains_text(result: PipelineCommandResult, needle: str) -> bool:
    for log_path in (result.stdout_log, result.stderr_log):
        if log_path is None:
            continue
        try:
            if needle in Path(log_path).read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def _is_insufficient_hypotheses_result(command: PipelineCommand, result: PipelineCommandResult) -> bool:
    return _is_combined_backtest_stage(command.stage) and _result_contains_text(
        result,
        INSUFFICIENT_HYPOTHESES_MESSAGE,
    )


def _is_insufficient_hypotheses_row(row: Mapping[str, object]) -> bool:
    return (
        row.get("status") == "failed"
        and _is_combined_backtest_stage(row.get("stage"))
        and str(row.get("failure_reason") or "") == INSUFFICIENT_HYPOTHESES_FAILURE_REASON
    )


def _combined_stage_rows(stage_results: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    return [row for row in stage_results if _is_combined_backtest_stage(row.get("stage"))]


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
            rows.append(
                _stage_result_row(
                    index=index,
                    command=command,
                    status="skipped",
                    skip_reason=stop_reason,
                )
            )
            continue

        result = run_command(command, runner=runner, log_dir=log_dir)
        failure_reason = result.error_message
        status = "executed" if result.status == "success" else "failed"
        insufficient_hypotheses = False
        if status == "failed" and _is_insufficient_hypotheses_result(command, result):
            insufficient_hypotheses = True
            failure_reason = INSUFFICIENT_HYPOTHESES_FAILURE_REASON
        if status == "executed":
            missing = _missing_expected_outputs(command)
            if missing:
                status = "failed"
                failure_reason = "Missing expected output after successful stage: " + "; ".join(
                    str(path) for path in missing
                )
        rows.append(
            _stage_result_row(
                index=index,
                command=command,
                status=status,
                result=result,
                failure_reason=failure_reason,
            )
        )
        if status == "failed" and args.stop_on_failure and not insufficient_hypotheses:
            stop_reason = f"Skipped because {command.stage} failed."
    return rows


def _final_classification(*, dry_run: bool, stage_results: Sequence[Mapping[str, object]]) -> str:
    if dry_run:
        return FINAL_CLASSIFICATION_DRY_RUN
    if any(row.get("status") == "failed" and not _is_insufficient_hypotheses_row(row) for row in stage_results):
        return FINAL_CLASSIFICATION_FAILED
    combined_rows = _combined_stage_rows(stage_results)
    insufficient_rows = [row for row in combined_rows if _is_insufficient_hypotheses_row(row)]
    if insufficient_rows:
        successful_combined_rows = [row for row in combined_rows if row.get("status") == "executed"]
        if successful_combined_rows:
            return FINAL_CLASSIFICATION_COMPLETED_WITH_UNCOMBINABLE_SYMBOLS
        return FINAL_CLASSIFICATION_STOPPED_NO_COMBINABLE_HYPOTHESES
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
                status=(
                    "partial"
                    if _is_insufficient_hypotheses_row(row)
                    else status_map.get(str(row.get("status") or ""), "skipped")
                ),
            )
            for row in stage_results
        ]
    )


def _next_action(final_classification: str, combined_output_dir: Path) -> str:
    if final_classification == FINAL_CLASSIFICATION_DRY_RUN:
        return "Review the command plan. To generate combined inputs manually, rerun with --execute. Heavy stages must be user-run only."
    if final_classification == FINAL_CLASSIFICATION_COMPLETED:
        return (
            "Review the run-scoped combined outputs, then use run_combined_validation_pipeline.py "
            f"with --combined-input-dir {combined_output_dir}."
        )
    if final_classification == FINAL_CLASSIFICATION_COMPLETED_WITH_UNCOMBINABLE_SYMBOLS:
        return (
            "Review available combined outputs and uncombinable-symbol warnings, then run combined validation "
            "only for symbols with generated combined outputs."
        )
    if final_classification == FINAL_CLASSIFICATION_STOPPED_NO_COMBINABLE_HYPOTHESES:
        return "Review selected/watchlist hypotheses; no requested symbol had enough usable hypotheses to combine."
    if final_classification == FINAL_CLASSIFICATION_FAILED:
        return "Review hypothesis_discovery_stage_results.csv and logs before rerunning with corrected inputs."
    return "Review skipped commands and decide whether the run should be repeated with corrected inputs."


def _warning_rows(
    *,
    dry_run: bool,
    stage_results: Sequence[Mapping[str, object]],
    final_classification: str,
) -> list[dict[str, object]]:
    rows = [
        _warning_row(
            warning_code="RESEARCH_ONLY_PIPELINE_ARTIFACT",
            severity="info",
            blocking=False,
            message="Hypothesis discovery pipeline outputs are offline exploratory research artifacts only.",
            related_stage=DECISION_SCOPE,
        ),
        _warning_row(
            warning_code="EXPLORATORY_ONLY_NOT_VALIDATED",
            severity="review",
            blocking=False,
            message="Combined hypothesis outputs are discovery inputs for later validation, not validated strategy evidence.",
            related_stage=DECISION_SCOPE,
        ),
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
                message="Execution mode runs existing offline discovery child commands only; outputs remain research-only.",
                related_stage=DECISION_SCOPE,
            )
        )
    for row in stage_results:
        if _is_insufficient_hypotheses_row(row):
            blocking = final_classification == FINAL_CLASSIFICATION_STOPPED_NO_COMBINABLE_HYPOTHESES
            rows.append(
                _warning_row(
                    warning_code=INSUFFICIENT_HYPOTHESES_WARNING_CODE,
                    severity="blocking" if blocking else "review",
                    blocking=blocking,
                    message=INSUFFICIENT_HYPOTHESES_FAILURE_REASON,
                    related_stage=str(row.get("stage") or ""),
                    related_metric="selected_watchlist_hypotheses",
                    threshold=2,
                )
            )
        elif row.get("status") == "failed":
            rows.append(
                _warning_row(
                    warning_code="PIPELINE_COMMAND_FAILED",
                    severity="blocking",
                    blocking=True,
                    message=str(row.get("failure_reason") or "Command failed."),
                    related_stage=str(row.get("stage") or ""),
                )
            )
        elif row.get("status") == "skipped":
            rows.append(
                _warning_row(
                    warning_code="PIPELINE_COMMAND_SKIPPED",
                    severity="review",
                    blocking=False,
                    message=str(row.get("skip_reason") or "Command skipped."),
                    related_stage=str(row.get("stage") or ""),
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
        "# Hypothesis Discovery Pipeline Report",
        "",
        "## Research-Only Warning",
        "This wrapper is for offline research discovery only. It does not create operational instructions.",
        "",
        "## Exploratory-Only Warning",
        "The generated combined hypothesis outputs are inputs for later validation, not validated strategy evidence.",
        "",
        "## Mode",
        (
            "Dry-run mode planned the child commands only; no child scripts were executed."
            if args.dry_run
            else "Execution mode ran existing offline discovery child commands through the shared runner."
        ),
        "",
        "## Input Sources",
        f"- run_id: `{run_id}`",
        f"- input_backtest_root: `{paths['input_backtest_root']}`",
        f"- direction_input_dir: `{paths['direction_input_dir']}`",
        f"- artifact_output_dir: `{paths['artifact_output_dir']}`",
        f"- combined_output_dir: `{paths['combined_output_dir']}`",
        f"- direction: `{args.direction}`",
        f"- symbols: `{' '.join(normalize_symbols(args.symbols))}`",
        f"- timeframe: `{str(args.timeframe).strip().upper()}`",
        f"- target_horizon: `{args.target_horizon}`",
        f"- cost_mode: `{args.cost_mode}`",
        f"- return_mode: `{args.return_mode}`",
        "",
        "## Planned Command Table",
        "| Order | Stage | Status | Symbol | Required | Command |",
        "|---:|---|---|---|---|---|",
    ]
    for index, command in enumerate(commands, start=1):
        rendered = render_command(command).replace("|", "\\|")
        row = result_by_order.get(str(index), {})
        lines.append(
            f"| {index} | `{command.stage}` | `{row.get('status', '')}` | "
            f"`{_command_symbol(command)}` | {str(bool(command.required)).lower()} | `{rendered}` |"
        )

    lines.extend(
        [
            "",
            "## Combined Output Layout",
            f"`{paths['combined_output_dir']}`",
        ]
    )
    for command in commands:
        if command.stage.startswith("combined_backtest_"):
            lines.append(f"- `{_planned_output_dir(command)}`")

    lines.extend(
        [
            "",
            "## Stage Results",
            "| Order | Stage | Status | Return Code | Skip/Failure Reason |",
            "|---:|---|---|---:|---|",
        ]
    )
    for row in stage_results:
        reason = str(row.get("failure_reason") or row.get("skip_reason") or "").replace("|", "\\|")
        lines.append(
            f"| {row.get('command_order', '')} | `{row.get('stage', '')}` | "
            f"`{row.get('status', '')}` | {row.get('returncode', '')} | {reason} |"
        )

    report_blocking_warnings = sum(1 for row in warnings if _is_blocking(row))
    lines.extend(
        [
            "",
            "## Warnings",
            f"- total_warnings: `{len(warnings)}`",
            f"- blocking_warnings: `{report_blocking_warnings}`",
            f"- non_blocking_warnings: `{len(warnings) - report_blocking_warnings}`",
            "Detailed row-level warnings are preserved in `hypothesis_discovery_warnings.csv`.",
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
    symbols = normalize_symbols(args.symbols)
    if not symbols:
        raise ValueError("At least one symbol is required.")
    timeframe = str(args.timeframe).strip().upper()
    cost_mode, return_mode = validate_orchestrator_cost_preflight(
        cost_mode=args.cost_mode,
        return_mode=args.return_mode,
        cost_config_path=args.cost_config,
    )
    run_id = _resolve_run_id(args.run_id)
    paths = build_pipeline_paths(args, run_id)
    if args.input_backtest_dir is None:
        require_existing_path(paths["input_backtest_root"], label="--input-backtest-root", kind="dir")
        require_existing_path(paths["direction_input_dir"], label="direction backtest input dir", kind="dir")
    else:
        require_existing_path(paths["direction_input_dir"], label="--input-backtest-dir", kind="dir")
    ensure_output_dir(paths["artifact_output_dir"], overwrite=args.overwrite)

    commands = build_stage_commands(
        args=args,
        run_id=run_id,
        symbols=symbols,
        timeframe=timeframe,
        cost_mode=cost_mode,
        return_mode=return_mode,
        paths=paths,
    )
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
    next_action = _next_action(final_classification, paths["combined_output_dir"])
    warnings = _warning_rows(
        dry_run=bool(args.dry_run),
        stage_results=stage_results,
        final_classification=final_classification,
    )
    blocking_warnings_count = sum(1 for row in warnings if _is_blocking(row))
    executed_command_count = sum(1 for row in stage_results if row.get("executed") == "true")
    skipped_command_count = sum(1 for row in stage_results if row.get("skipped") == "true")
    failed_command_count = sum(1 for row in stage_results if row.get("failed") == "true")

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
        else final_classification.removeprefix("HYPOTHESIS_DISCOVERY_PIPELINE_").lower()
    )

    write_manifest(
        manifest_path,
        {
            "generated_at": utc_now_iso(),
            "completed_at": utc_now_iso(),
            "run_id": run_id,
            "output_dir": str(paths["artifact_output_dir"]),
            "combined_output_dir": str(paths["combined_output_dir"]),
            "dry_run": bool(args.dry_run),
            "execute": bool(args.execute),
            "planned_stages": ["backtest_evaluation", "hypothesis_selection", "combined_backtest"],
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
                "input_backtest_root": str(paths["input_backtest_root"]),
                "input_backtest_dir": str(paths["direction_input_dir"]) if args.input_backtest_dir is not None else "",
                "direction_input_dir": str(paths["direction_input_dir"]),
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
                "planned_stage_count": 3,
                "planned_command_count": len(commands),
                "executed_command_count": executed_command_count,
                "skipped_command_count": skipped_command_count,
                "failed_command_count": failed_command_count,
                "warnings_count": len(warnings),
                "blocking_warnings_count": blocking_warnings_count,
                "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
                "combined_output_dir": str(paths["combined_output_dir"]),
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
        "combined_output_dir": paths["combined_output_dir"],
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
    print(f"Hypothesis discovery pipeline artifacts written to {outputs['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
