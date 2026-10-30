import argparse
import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import subprocess
import sys

try:
    from research_metrics import normalize_direction, target_column_for_direction
    from research_costs import validate_orchestrator_cost_preflight
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_full_research_pipeline
    from scripts.research_metrics import normalize_direction, target_column_for_direction
    from scripts.research_costs import validate_orchestrator_cost_preflight


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"
LOGS_DIR = BASE_DIR / "logs"

DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
DEFAULT_TIMEFRAME = "M15"
DEFAULT_FROM_DATE = "2022-01-01"
DEFAULT_TO_DATE = "2025-12-31"
DEFAULT_TARGET_HORIZON = 10

COMBINED_RUNS_DIR = BASE_DIR / "reports" / "backtests" / "combined" / "runs"
COMBINED_EVALUATIONS_DIR = BASE_DIR / "reports" / "backtests" / "combined" / "evaluations"
VALIDATION_OUTPUT_DIR = BASE_DIR / "reports" / "validation" / "by_year"
FINAL_SCORECARD_OUTPUT_DIR = BASE_DIR / "reports" / "final_feature_scorecard"
WALK_FORWARD_OUTPUT_DIR = BASE_DIR / "reports" / "walk_forward"
RANDOM_BASELINE_OUTPUT_DIR = BASE_DIR / "reports" / "random_baseline"
BASELINE_DIAGNOSTICS_OUTPUT_DIR = BASE_DIR / "reports" / "baseline_diagnostics"
RESEARCH_DECISION_OUTPUT_DIR = BASE_DIR / "reports" / "research_decision"
SELECTED_COMBINED_FILE = "selected_combined_hypotheses.csv"

FINAL_CANDIDATES_FILE = "final_research_candidates.csv"
PAIR_SPECIFIC_CANDIDATES_FILE = "pair_specific_candidates.csv"

RANDOM_BASELINE_OUTPUT_FILES = [
    "random_baseline_detail.csv",
    "random_baseline_summary.csv",
    "random_baseline_report.md",
    "skipped_random_baseline_candidates.csv",
]
BASELINE_DIAGNOSTICS_OUTPUT_FILES = [
    "baseline_diagnostics_detail.csv",
    "baseline_diagnostics_summary.csv",
    "baseline_diagnostics_report.md",
    "skipped_baseline_diagnostics_candidates.csv",
]
RESEARCH_DECISION_OUTPUT_FILES = [
    "research_decision_report.md",
    "research_decision_summary.csv",
    "research_decision_warnings.csv",
]

FINAL_REVIEW_RANDOM_BASELINE = "random_baseline"
FINAL_REVIEW_BASELINE_DIAGNOSTICS = "baseline_diagnostics"
FINAL_REVIEW_RESEARCH_DECISION = "research_decision_report"


@dataclass
class FinalReviewState:
    enabled: bool = False
    requested_steps: list[str] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    skipped_reason: str = ""
    candidate_counts: dict[str, int] = field(default_factory=dict)
    random_baseline_output_path: Path | None = None
    baseline_diagnostics_output_path: Path | None = None
    research_decision_report_output_path: Path | None = None
    warnings: list[str] = field(default_factory=list)


class PipelineAbort(RuntimeError):
    pass


class PipelineRunner:
    def __init__(self, *, run_id: str, log_path: Path, continue_on_error: bool) -> None:
        self.run_id = run_id
        self.log_path = log_path
        self.continue_on_error = continue_on_error
        self.completed_steps: list[str] = []
        self.failed_steps: list[str] = []
        self.skipped_steps: list[str] = []
        self.final_review = FinalReviewState()
        self.log_file = log_path.open("w", encoding="utf-8")

    def close(self) -> None:
        self.log_file.close()

    def emit(self, text: str = "") -> None:
        print(text)
        self.log_file.write(text + "\n")
        self.log_file.flush()

    def skip(self, step_name: str, reason: str) -> None:
        self.skipped_steps.append(step_name)
        self.emit("")
        self.emit(f"SKIP: {step_name}")
        self.emit(f"Reason: {reason}")

    def run_step(self, step_name: str, command: list[str]) -> None:
        command_text = subprocess.list2cmdline(command)
        self.emit("")
        self.emit(f"STEP: {step_name}")
        self.emit(f"Command: {command_text}")

        try:
            process = subprocess.Popen(
                command,
                cwd=BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            self.failed_steps.append(step_name)
            self.emit(f"Failed to start step: {exc}")
            if not self.continue_on_error:
                raise PipelineAbort(step_name) from exc
            return

        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            self.log_file.write(line)
            self.log_file.flush()

        return_code = process.wait()
        if return_code == 0:
            self.completed_steps.append(step_name)
            self.emit(f"Step completed: {step_name}")
            return

        self.failed_steps.append(step_name)
        self.emit(f"Step failed: {step_name} (exit code {return_code})")
        if not self.continue_on_error:
            raise PipelineAbort(step_name)


def normalize_symbols(values: list[str]) -> list[str]:
    symbols: list[str] = []
    for value in values:
        for token in value.split(","):
            symbol = token.strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols


def script_command(script_name: str, *args: object) -> list[str]:
    return [sys.executable, str(SCRIPTS_DIR / script_name), *(str(arg) for arg in args)]


def final_review_steps(args: argparse.Namespace) -> list[str]:
    if args.run_final_review:
        return [
            FINAL_REVIEW_RANDOM_BASELINE,
            FINAL_REVIEW_BASELINE_DIAGNOSTICS,
            FINAL_REVIEW_RESEARCH_DECISION,
        ]
    steps: list[str] = []
    if args.run_random_baseline:
        steps.append(FINAL_REVIEW_RANDOM_BASELINE)
    if args.run_baseline_diagnostics:
        steps.append(FINAL_REVIEW_BASELINE_DIAGNOSTICS)
    if args.run_research_decision_report:
        steps.append(FINAL_REVIEW_RESEARCH_DECISION)
    return steps


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return [dict(row) for row in csv.DictReader(csv_file)]


def candidate_row_matches(row: dict[str, str], direction: str, cost_mode: str, return_mode: str) -> bool:
    if not str(row.get("combination_key") or "").strip():
        return False
    row_direction = str(row.get("direction") or direction).strip().lower()
    row_cost_mode = str(row.get("cost_mode") or cost_mode).strip().lower()
    row_return_mode = str(row.get("return_mode") or return_mode).strip().lower()
    return row_direction == direction and row_cost_mode == cost_mode and row_return_mode == return_mode


def count_matching_candidate_rows(path: Path, direction: str, cost_mode: str, return_mode: str) -> int:
    return sum(
        1
        for row in read_csv_rows(path)
        if candidate_row_matches(row, direction, cost_mode, return_mode)
    )


def final_candidate_paths(run_id: str, direction: str) -> tuple[Path, Path]:
    validation_dir = VALIDATION_OUTPUT_DIR / run_id / direction
    return validation_dir / FINAL_CANDIDATES_FILE, validation_dir / PAIR_SPECIFIC_CANDIDATES_FILE


def final_review_candidate_counts(
    run_id: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
) -> dict[str, int]:
    cross_pair_path, pair_specific_path = final_candidate_paths(run_id, direction)
    return {
        "cross_pair": count_matching_candidate_rows(cross_pair_path, direction, cost_mode, return_mode),
        "pair_specific": count_matching_candidate_rows(pair_specific_path, direction, cost_mode, return_mode),
    }


def final_review_has_available_candidates(counts: dict[str, int], include_pair_specific: bool) -> bool:
    return counts.get("cross_pair", 0) > 0 or (include_pair_specific and counts.get("pair_specific", 0) > 0)


def final_review_output_dir(step: str, run_id: str, direction: str) -> Path:
    if step == FINAL_REVIEW_RANDOM_BASELINE:
        return RANDOM_BASELINE_OUTPUT_DIR / run_id / direction
    if step == FINAL_REVIEW_BASELINE_DIAGNOSTICS:
        return BASELINE_DIAGNOSTICS_OUTPUT_DIR / run_id / direction
    if step == FINAL_REVIEW_RESEARCH_DECISION:
        return RESEARCH_DECISION_OUTPUT_DIR / run_id / direction
    raise ValueError(f"Unknown final review step: {step}")


def final_review_output_files(step: str) -> list[str]:
    if step == FINAL_REVIEW_RANDOM_BASELINE:
        return RANDOM_BASELINE_OUTPUT_FILES
    if step == FINAL_REVIEW_BASELINE_DIAGNOSTICS:
        return BASELINE_DIAGNOSTICS_OUTPUT_FILES
    if step == FINAL_REVIEW_RESEARCH_DECISION:
        return RESEARCH_DECISION_OUTPUT_FILES
    raise ValueError(f"Unknown final review step: {step}")


def ensure_final_review_output_writable(step: str, run_id: str, direction: str, overwrite: bool) -> None:
    if overwrite:
        return
    output_dir = final_review_output_dir(step, run_id, direction)
    existing = [output_dir / filename for filename in final_review_output_files(step) if (output_dir / filename).exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"Final review output already exists for {step}: {joined}. "
            "Pass --overwrite-final-review to regenerate it."
        )


def final_review_step_label(step: str) -> str:
    labels = {
        FINAL_REVIEW_RANDOM_BASELINE: "21. final review random baseline",
        FINAL_REVIEW_BASELINE_DIAGNOSTICS: "22. final review baseline diagnostics",
        FINAL_REVIEW_RESEARCH_DECISION: "23. final review research decision report",
    }
    return labels[step]


def set_final_review_output_path(state: FinalReviewState, step: str, run_id: str, direction: str) -> None:
    output_dir = final_review_output_dir(step, run_id, direction)
    if step == FINAL_REVIEW_RANDOM_BASELINE:
        state.random_baseline_output_path = output_dir
    elif step == FINAL_REVIEW_BASELINE_DIAGNOSTICS:
        state.baseline_diagnostics_output_path = output_dir
    elif step == FINAL_REVIEW_RESEARCH_DECISION:
        state.research_decision_report_output_path = output_dir


def append_cost_config_args(command: list[object], args: argparse.Namespace) -> None:
    if args.cost_config is not None:
        command.extend(["--cost-config", str(args.cost_config)])
    if args.strict_cost_config:
        command.append("--strict-cost-config")


def build_random_baseline_command(
    args: argparse.Namespace,
    *,
    run_id: str,
    direction: str,
    symbols: list[str],
    timeframe: str,
    target_horizon: int,
    cost_mode: str,
    return_mode: str,
) -> list[object]:
    command: list[object] = [
        *script_command(
            "run_random_baseline_tests.py",
            "--run-id",
            run_id,
            "--direction",
            direction,
            "--symbols",
            *symbols,
            "--timeframe",
            timeframe,
            "--target-horizon",
            target_horizon,
            "--cost-mode",
            cost_mode,
            "--return-mode",
            return_mode,
        ),
        "--random-runs",
        args.random_baseline_runs,
    ]
    append_cost_config_args(command, args)
    if args.include_pair_specific_final_review:
        command.append("--include-pair-specific")
    if args.overwrite_final_review:
        command.append("--overwrite")
    return command


def build_baseline_diagnostics_command(
    args: argparse.Namespace,
    *,
    run_id: str,
    direction: str,
    symbols: list[str],
    timeframe: str,
    target_horizon: int,
    cost_mode: str,
    return_mode: str,
) -> list[object]:
    command: list[object] = [
        *script_command(
            "run_candidate_baseline_diagnostics.py",
            "--run-id",
            run_id,
            "--direction",
            direction,
            "--symbols",
            *symbols,
            "--timeframe",
            timeframe,
            "--target-horizon",
            target_horizon,
            "--cost-mode",
            cost_mode,
            "--return-mode",
            return_mode,
        ),
        "--random-runs",
        args.diagnostics_random_runs,
    ]
    append_cost_config_args(command, args)
    if args.diagnostics_max_candidates is not None:
        command.extend(["--max-candidates", args.diagnostics_max_candidates])
    if args.include_pair_specific_final_review:
        command.append("--include-pair-specific")
    if args.overwrite_final_review:
        command.append("--overwrite")
    return command


def build_research_decision_command(
    args: argparse.Namespace,
    *,
    run_id: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
) -> list[object]:
    command: list[object] = script_command(
        "build_research_decision_report.py",
        "--run-id",
        run_id,
        "--direction",
        direction,
        "--cost-mode",
        cost_mode,
        "--return-mode",
        return_mode,
    )
    if args.overwrite_final_review:
        command.append("--overwrite")
    return command


def record_final_review_failure(
    runner: PipelineRunner,
    state: FinalReviewState,
    step: str,
    label: str,
    message: str,
) -> None:
    if step not in state.failed_steps:
        state.failed_steps.append(step)
    if label not in runner.failed_steps:
        runner.failed_steps.append(label)
    runner.emit(message)


def run_final_review_step(
    runner: PipelineRunner,
    state: FinalReviewState,
    step: str,
    command: list[object],
    *,
    direction: str,
    overwrite: bool,
) -> None:
    label = final_review_step_label(step)
    set_final_review_output_path(state, step, runner.run_id, direction)
    try:
        ensure_final_review_output_writable(step, runner.run_id, direction, overwrite=overwrite)
    except FileExistsError as exc:
        record_final_review_failure(runner, state, step, label, str(exc))
        if not runner.continue_on_error:
            raise PipelineAbort(label) from exc
        return

    try:
        runner.run_step(label, [str(item) for item in command])
    except PipelineAbort:
        if step not in state.failed_steps:
            state.failed_steps.append(step)
        raise
    if label in runner.completed_steps and step not in state.completed_steps:
        state.completed_steps.append(step)
    if label in runner.failed_steps and step not in state.failed_steps:
        state.failed_steps.append(step)


def run_optional_final_review(
    args: argparse.Namespace,
    runner: PipelineRunner,
    *,
    symbols: list[str],
    timeframe: str,
    target_horizon: int,
    direction: str,
    cost_mode: str,
    return_mode: str,
) -> None:
    state = runner.final_review
    steps = final_review_steps(args)
    state.enabled = bool(steps)
    state.requested_steps = list(steps)
    if not steps:
        state.skipped_reason = "not requested"
        return

    counts = final_review_candidate_counts(runner.run_id, direction, cost_mode, return_mode)
    state.candidate_counts = counts
    has_candidates = final_review_has_available_candidates(counts, args.include_pair_specific_final_review)
    if not has_candidates:
        base_message = (
            f"No final candidates found for {runner.run_id}/{direction} with "
            f"cost_mode={cost_mode} return_mode={return_mode}."
        )
        runner.emit("")
        if args.skip_final_review_if_no_candidates:
            state.skipped_reason = f"{base_message} Skipping random baseline and baseline diagnostics."
            runner.emit(state.skipped_reason)
        else:
            warning = f"{base_message} --no-skip-final-review-if-no-candidates was passed, so requested final-review subprocesses will still run."
            state.warnings.append(warning)
            runner.emit(f"Warning: {warning}")
        if counts.get("pair_specific", 0) > 0 and not args.include_pair_specific_final_review:
            warning = "Pair-specific candidates exist but --include-pair-specific-final-review was not passed."
            state.warnings.append(warning)
            runner.emit(f"Warning: {warning}")

    for step in steps:
        if step == FINAL_REVIEW_RESEARCH_DECISION and any(
            failed in state.failed_steps
            for failed in (FINAL_REVIEW_RANDOM_BASELINE, FINAL_REVIEW_BASELINE_DIAGNOSTICS)
        ):
            reason = "Skipping research decision report because an earlier requested final-review step failed."
            state.skipped_reason = reason
            runner.skip(final_review_step_label(step), reason)
            continue
        if step in {FINAL_REVIEW_RANDOM_BASELINE, FINAL_REVIEW_BASELINE_DIAGNOSTICS} and not has_candidates and args.skip_final_review_if_no_candidates:
            runner.skip(final_review_step_label(step), state.skipped_reason)
            continue
        if step == FINAL_REVIEW_RESEARCH_DECISION and not has_candidates:
            warning = "Research decision report was requested with no matching final candidates; it may summarize empty or missing candidate files."
            state.warnings.append(warning)
            runner.emit(f"Warning: {warning}")

        if step == FINAL_REVIEW_RANDOM_BASELINE:
            command = build_random_baseline_command(
                args,
                run_id=runner.run_id,
                direction=direction,
                symbols=symbols,
                timeframe=timeframe,
                target_horizon=target_horizon,
                cost_mode=cost_mode,
                return_mode=return_mode,
            )
        elif step == FINAL_REVIEW_BASELINE_DIAGNOSTICS:
            command = build_baseline_diagnostics_command(
                args,
                run_id=runner.run_id,
                direction=direction,
                symbols=symbols,
                timeframe=timeframe,
                target_horizon=target_horizon,
                cost_mode=cost_mode,
                return_mode=return_mode,
            )
        elif step == FINAL_REVIEW_RESEARCH_DECISION:
            command = build_research_decision_command(
                args,
                run_id=runner.run_id,
                direction=direction,
                cost_mode=cost_mode,
                return_mode=return_mode,
            )
        else:
            raise ValueError(f"Unknown final review step: {step}")

        run_final_review_step(
            runner,
            state,
            step,
            command,
            direction=direction,
            overwrite=args.overwrite_final_review,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the full offline research pipeline through final year-by-year validation."
    )
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--from-date", default=DEFAULT_FROM_DATE)
    parser.add_argument("--to-date", default=DEFAULT_TO_DATE)
    parser.add_argument("--target-horizon", type=int, choices=(5, 10, 20), default=DEFAULT_TARGET_HORIZON)
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--years", nargs="+", type=int)
    parser.add_argument("--include-incomplete-years", action="store_true")
    parser.add_argument("--min-trades-per-year", type=int, default=100)
    parser.add_argument("--min-positive-year-ratio", type=float, default=0.75)
    parser.add_argument("--min-positive-symbol-ratio", type=float, default=0.75)
    parser.add_argument("--overwrite-validation", action="store_true")
    parser.add_argument("--skip-yearly-validation", action="store_true")
    parser.add_argument("--run-walk-forward", action="store_true")
    parser.add_argument("--purge-overlap", dest="purge_overlap", action="store_true")
    parser.add_argument("--no-purge-overlap", dest="purge_overlap", action="store_false")
    parser.set_defaults(purge_overlap=None)
    parser.add_argument("--embargo-bars", type=int, default=0)
    parser.add_argument("--non-overlap-walk-forward", action="store_true")
    parser.add_argument("--non-overlap-validation", action="store_true")
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--strict-cost-config", action="store_true")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--run-final-review", action="store_true")
    parser.add_argument("--run-random-baseline", action="store_true")
    parser.add_argument("--run-baseline-diagnostics", action="store_true")
    parser.add_argument("--run-research-decision-report", action="store_true")
    parser.add_argument("--include-pair-specific-final-review", action="store_true")
    parser.add_argument("--random-baseline-runs", type=int, default=250)
    parser.add_argument("--diagnostics-random-runs", type=int, default=100)
    parser.add_argument("--diagnostics-max-candidates", type=int)
    parser.add_argument("--skip-final-review-if-no-candidates", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--overwrite-final-review", action="store_true")
    parser.add_argument("--calendar-csv-source", type=Path)
    parser.add_argument("--skip-calendar-import", action="store_true")
    parser.add_argument("--skip-price-import", action="store_true")
    parser.add_argument("--skip-checks", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--run-id")
    return parser


def run_pipeline(args: argparse.Namespace, runner: PipelineRunner) -> Path:
    symbols = normalize_symbols(args.symbols)
    if not symbols:
        raise ValueError("At least one symbol is required.")
    if args.embargo_bars < 0:
        raise ValueError("--embargo-bars cannot be negative.")
    if args.random_baseline_runs <= 0:
        raise ValueError("--random-baseline-runs must be greater than zero.")
    if args.diagnostics_random_runs <= 0:
        raise ValueError("--diagnostics-random-runs must be greater than zero.")
    if args.diagnostics_max_candidates is not None and args.diagnostics_max_candidates <= 0:
        raise ValueError("--diagnostics-max-candidates must be greater than zero when provided.")

    timeframe = args.timeframe.strip().upper()
    direction = normalize_direction(args.direction)
    target_horizon = int(args.target_horizon)
    target_column = target_column_for_direction(direction, target_horizon)
    return_target_column = f"future_return_{target_horizon}"
    cost_mode, return_mode = validate_orchestrator_cost_preflight(
        cost_mode=args.cost_mode,
        return_mode=args.return_mode,
        cost_config_path=args.cost_config,
    )
    cost_mode_args = ["--cost-mode", cost_mode, "--return-mode", return_mode]
    cost_estimation_args = list(cost_mode_args)
    if args.cost_config is not None:
        cost_estimation_args.extend(["--cost-config", str(args.cost_config)])
    if args.strict_cost_config:
        cost_estimation_args.append("--strict-cost-config")
    combined_input_dir = COMBINED_RUNS_DIR / runner.run_id / direction
    final_output_dir = COMBINED_EVALUATIONS_DIR / runner.run_id / direction

    runner.emit(f"Run ID: {runner.run_id}")
    runner.emit(f"Symbols: {' '.join(symbols)}")
    runner.emit(f"Timeframe: {timeframe}")
    runner.emit(f"Date range: {args.from_date} -> {args.to_date}")
    runner.emit(f"Target horizon: {target_horizon}")
    runner.emit(f"Direction: {direction}")
    runner.emit(f"Purge overlap: {args.purge_overlap if args.purge_overlap is not None else 'walk-forward default'}")
    runner.emit(f"Embargo bars: {args.embargo_bars}")
    runner.emit(f"Non-overlap walk-forward: {str(args.non_overlap_walk_forward).lower()}")
    runner.emit(f"Non-overlap validation: {str(args.non_overlap_validation).lower()}")
    runner.emit(f"Cost mode: {cost_mode}")
    runner.emit(f"Return mode: {return_mode}")
    runner.emit(f"Strict cost config: {str(args.strict_cost_config).lower()}")
    runner.emit(f"Final review requested: {str(bool(final_review_steps(args))).lower()}")
    runner.emit(f"Include pair-specific final review: {str(args.include_pair_specific_final_review).lower()}")
    runner.emit(f"Overwrite final review: {str(args.overwrite_final_review).lower()}")
    if args.cost_config is not None:
        runner.emit(f"Cost config: {args.cost_config}")
    runner.emit(f"Log path: {runner.log_path}")

    runner.run_step("1. init_database", script_command("init_database.py"))

    if args.skip_calendar_import:
        runner.skip("2. calendar import", "--skip-calendar-import was passed")
    else:
        command = script_command("run_pipeline.py")
        if args.calendar_csv_source is not None:
            command.extend(["--csv-source", str(args.calendar_csv_source)])
        runner.run_step("2. calendar import", command)

    if args.skip_price_import:
        runner.skip("3. import price bars", "--skip-price-import was passed")
    else:
        for symbol in symbols:
            runner.run_step(
                f"3. import price bars {symbol}",
                script_command(
                    "import_price_bars.py",
                    "--symbol",
                    symbol,
                    "--timeframe",
                    timeframe,
                    "--from-date",
                    args.from_date,
                    "--to-date",
                    args.to_date,
                ),
            )

    if args.skip_checks:
        runner.skip("4. check price bars", "--skip-checks was passed")
    else:
        runner.run_step("4. check price bars", script_command("check_price_bars.py"))

    for symbol in symbols:
        price_feature_command = script_command("generate_price_features.py", "--symbol", symbol, "--timeframe", timeframe)
        if args.cost_config is not None:
            # Cost configs also carry symbols.<SYMBOL>.point_size, which generate_price_features accepts as metadata.
            price_feature_command.extend(["--point-size-config", str(args.cost_config)])
        if args.strict_cost_config:
            price_feature_command.append("--strict-point-size")
        runner.run_step(
            f"5. generate price features {symbol}",
            price_feature_command,
        )

    if args.skip_checks:
        runner.skip("6. check price features", "--skip-checks was passed")
    else:
        runner.run_step("6. check price features", script_command("check_price_features.py"))

    for symbol in symbols:
        runner.run_step(
            f"7. generate market features {symbol}",
            script_command("generate_market_features.py", "--symbol", symbol, "--timeframe", timeframe),
        )

    if args.skip_checks:
        runner.skip("8. check market features", "--skip-checks was passed")
    else:
        runner.run_step("8. check market features", script_command("check_market_features.py"))

    for symbol in symbols:
        runner.run_step(
            f"9. generate ML dataset {symbol}",
            script_command("generate_ml_dataset.py", "--symbol", symbol, "--timeframe", timeframe),
        )

    if args.skip_checks:
        runner.skip("10. check ML dataset", "--skip-checks was passed")
    else:
        runner.run_step("10. check ML dataset", script_command("check_ml_dataset.py"))

    for symbol in symbols:
        ml_command = script_command(
            "ml_research.py",
            "--symbol",
            symbol,
            "--timeframe",
            timeframe,
            "--target",
            target_column,
            "--return-target",
            return_target_column,
            "--direction",
            direction,
        )
        if args.purge_overlap is True:
            ml_command.append("--purge-overlap")
        ml_command.extend(["--embargo-bars", str(args.embargo_bars)])
        runner.run_step(
            f"11. ML research {symbol}",
            ml_command,
        )

    runner.run_step("12. analyze reports", script_command("analyze_research_reports.py", "--direction", direction))

    for symbol in symbols:
        runner.run_step(
            f"13. backtest research {symbol}",
            script_command(
                "backtest_research.py",
                "--symbol",
                symbol,
                "--timeframe",
                timeframe,
                "--target-horizon",
                target_horizon,
                "--direction",
                direction,
                *cost_estimation_args,
            ),
        )

    runner.run_step(
        "14. evaluate backtest",
        script_command("evaluate_backtest_results.py", "--direction", direction, *cost_mode_args),
    )
    runner.run_step("15. select hypotheses", script_command("select_research_hypotheses.py", "--direction", direction))

    for symbol in symbols:
        combined_symbol_dir = combined_input_dir / f"{symbol}_{timeframe}_h{target_horizon}"
        runner.run_step(
            f"16. backtest combined hypotheses {symbol}",
            script_command(
                "backtest_combined_hypotheses.py",
                "--symbol",
                symbol,
                "--timeframe",
                timeframe,
                "--target-horizon",
                target_horizon,
                "--direction",
                direction,
                "--output-dir",
                combined_symbol_dir,
                *cost_estimation_args,
            ),
        )

    runner.run_step(
        "17. evaluate combined hypotheses",
        script_command(
            "evaluate_combined_hypotheses.py",
            "--input-dir",
            combined_input_dir,
            "--output-dir",
            COMBINED_EVALUATIONS_DIR,
            "--run-id",
            runner.run_id,
            "--direction",
            direction,
            *cost_mode_args,
        ),
    )

    if args.skip_yearly_validation:
        runner.skip("18. validate hypotheses by year", "--skip-yearly-validation was passed")
        steps = final_review_steps(args)
        runner.final_review.enabled = bool(steps)
        runner.final_review.requested_steps = list(steps)
        if steps:
            runner.final_review.skipped_reason = "yearly validation was skipped; final review requires validation outputs."
            runner.skip("final review", runner.final_review.skipped_reason)
        else:
            runner.final_review.skipped_reason = "not requested"
        return final_output_dir

    selected_hypotheses_file = final_output_dir / SELECTED_COMBINED_FILE
    if not selected_hypotheses_file.exists():
        runner.failed_steps.append("18. validate hypotheses by year")
        raise ValueError(
            "Selected combined hypotheses file is missing; cannot run yearly validation: "
            f"{selected_hypotheses_file}"
        )

    validation_command = script_command(
        "validate_hypotheses_by_year.py",
        "--hypotheses-file",
        selected_hypotheses_file,
        "--run-id",
        runner.run_id,
        "--direction",
        direction,
        "--symbols",
        *symbols,
        "--timeframe",
        timeframe,
        "--target-horizon",
        target_horizon,
        "--output-dir",
        VALIDATION_OUTPUT_DIR,
        "--min-trades-per-year",
        args.min_trades_per_year,
        "--min-positive-year-ratio",
        args.min_positive_year_ratio,
        "--min-positive-symbol-ratio",
        args.min_positive_symbol_ratio,
        *cost_estimation_args,
    )
    if args.start_year is not None:
        validation_command.extend(["--start-year", str(args.start_year)])
    if args.end_year is not None:
        validation_command.extend(["--end-year", str(args.end_year)])
    if args.years:
        validation_command.append("--years")
        validation_command.extend(str(year) for year in args.years)
    if args.include_incomplete_years:
        validation_command.append("--include-incomplete-years")
    if args.non_overlap_validation:
        validation_command.append("--non-overlap-eval")
    if args.overwrite_validation:
        validation_command.append("--overwrite")

    runner.run_step("18. validate hypotheses by year", validation_command)

    scorecard_command = script_command(
        "build_final_feature_scorecard.py",
        "--run-id",
        runner.run_id,
        "--direction",
        direction,
        "--min-trades-per-year",
        args.min_trades_per_year,
        *cost_mode_args,
    )
    if args.overwrite_validation:
        scorecard_command.append("--overwrite")
    runner.run_step("19. build final feature scorecard", scorecard_command)

    if args.run_walk_forward:
        walk_forward_command = script_command(
            "run_walk_forward_research.py",
            "--run-id",
            runner.run_id,
            "--symbols",
            *symbols,
            "--timeframe",
            timeframe,
            "--target-horizon",
            target_horizon,
            "--direction",
            direction,
            "--min-trades-per-year",
            args.min_trades_per_year,
            "--min-positive-symbol-ratio",
            args.min_positive_symbol_ratio,
            *cost_estimation_args,
        )
        if args.purge_overlap is True:
            walk_forward_command.append("--purge-overlap")
        elif args.purge_overlap is False:
            walk_forward_command.append("--no-purge-overlap")
        walk_forward_command.extend(["--embargo-bars", str(args.embargo_bars)])
        if args.non_overlap_walk_forward:
            walk_forward_command.append("--non-overlap-test")
        if args.overwrite_validation:
            walk_forward_command.append("--overwrite")
        runner.run_step("20. run walk-forward research", walk_forward_command)
    else:
        runner.skip("20. run walk-forward research", "--run-walk-forward was not passed")

    run_optional_final_review(
        args,
        runner,
        symbols=symbols,
        timeframe=timeframe,
        target_horizon=target_horizon,
        direction=direction,
        cost_mode=cost_mode,
        return_mode=return_mode,
    )

    return final_output_dir


def print_final_report(runner: PipelineRunner, final_status: str, final_output_dir: Path) -> None:
    direction = final_output_dir.name if final_output_dir.parent.name == runner.run_id else "long"
    scorecard_output_dir = FINAL_SCORECARD_OUTPUT_DIR / runner.run_id / direction
    runner.emit("")
    runner.emit("Full research pipeline final report")
    runner.emit(f"run_id: {runner.run_id}")
    runner.emit(f"final status: {final_status}")
    runner.emit(f"evaluate_combined_hypotheses output: {final_output_dir}")
    runner.emit(f"direction: {direction}")
    runner.emit(f"yearly validation output path: reports/validation/by_year/{runner.run_id}/{direction}/")
    runner.emit("yearly validation files:")
    runner.emit(f"- reports/validation/by_year/{runner.run_id}/{direction}/final_research_candidates_report.md")
    runner.emit(f"- reports/validation/by_year/{runner.run_id}/{direction}/final_research_candidates.csv")
    runner.emit(f"- reports/validation/by_year/{runner.run_id}/{direction}/pair_specific_candidates_report.md")
    runner.emit(f"- reports/validation/by_year/{runner.run_id}/{direction}/pair_specific_candidates.csv")
    runner.emit(f"- reports/validation/by_year/{runner.run_id}/{direction}/skipped_hypotheses.csv")
    runner.emit(
        "cross-pair candidates report path: "
        f"reports/validation/by_year/{runner.run_id}/{direction}/final_research_candidates_report.md"
    )
    runner.emit(
        "pair-specific candidates report path: "
        f"reports/validation/by_year/{runner.run_id}/{direction}/pair_specific_candidates_report.md"
    )
    runner.emit(f"final feature scorecard output path: {scorecard_output_dir}")
    runner.emit("final feature scorecard files:")
    runner.emit(f"- reports/final_feature_scorecard/{runner.run_id}/{direction}/final_feature_scorecard_report.md")
    runner.emit(f"- reports/final_feature_scorecard/{runner.run_id}/{direction}/final_feature_scorecard.csv")
    runner.emit(f"- reports/final_feature_scorecard/{runner.run_id}/{direction}/pair_specific_feature_scorecard.csv")
    runner.emit(
        "cross-pair feature scorecard path: "
        f"reports/final_feature_scorecard/{runner.run_id}/{direction}/final_feature_scorecard.csv"
    )
    runner.emit(
        "pair-specific feature scorecard path: "
        f"reports/final_feature_scorecard/{runner.run_id}/{direction}/pair_specific_feature_scorecard.csv"
    )
    runner.emit(f"walk-forward output path if run: reports/walk_forward/{runner.run_id}/{direction}/")
    runner.emit("walk-forward files if run:")
    runner.emit(f"- reports/walk_forward/{runner.run_id}/{direction}/walk_forward_report.md")
    runner.emit(f"- reports/walk_forward/{runner.run_id}/{direction}/walk_forward_candidates.csv")
    runner.emit(f"- reports/walk_forward/{runner.run_id}/{direction}/pair_specific_walk_forward_candidates.csv")
    final_review = runner.final_review
    runner.emit(f"final review enabled: {'yes' if final_review.enabled else 'no'}")
    if final_review.requested_steps:
        runner.emit(f"final review requested steps: {', '.join(final_review.requested_steps)}")
    if final_review.candidate_counts:
        runner.emit(
            "final review candidate counts: "
            f"cross_pair={final_review.candidate_counts.get('cross_pair', 0)} "
            f"pair_specific={final_review.candidate_counts.get('pair_specific', 0)}"
        )
    if final_review.random_baseline_output_path is not None:
        runner.emit(f"random baseline output path: {final_review.random_baseline_output_path}")
    if final_review.baseline_diagnostics_output_path is not None:
        runner.emit(f"baseline diagnostics output path: {final_review.baseline_diagnostics_output_path}")
    if final_review.research_decision_report_output_path is not None:
        runner.emit(f"research decision report output path: {final_review.research_decision_report_output_path}")
    if final_review.skipped_reason:
        runner.emit(f"final review skipped reason: {final_review.skipped_reason}")
    if final_review.warnings:
        runner.emit("final review warnings:")
        for warning in final_review.warnings:
            runner.emit(f"- {warning}")
    runner.emit("completed final-review steps:")
    if final_review.completed_steps:
        for step in final_review.completed_steps:
            runner.emit(f"- {step}")
    else:
        runner.emit("- none")
    runner.emit("failed final-review steps:")
    if final_review.failed_steps:
        for step in final_review.failed_steps:
            runner.emit(f"- {step}")
    else:
        runner.emit("- none")
    runner.emit("completed steps:")
    if runner.completed_steps:
        for step in runner.completed_steps:
            runner.emit(f"- {step}")
    else:
        runner.emit("- none")
    runner.emit("failed steps:")
    if runner.failed_steps:
        for step in runner.failed_steps:
            runner.emit(f"- {step}")
    else:
        runner.emit("- none")
    runner.emit("skipped steps:")
    if runner.skipped_steps:
        for step in runner.skipped_steps:
            runner.emit(f"- {step}")
    else:
        runner.emit("- none")


def main() -> int:
    args = build_parser().parse_args()
    run_id = args.run_id.strip() if args.run_id else datetime.now().strftime("%Y%m%d_%H%M%S")
    if not run_id:
        print("--run-id cannot be empty.")
        return 1

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"full_pipeline_{run_id}.log"
    runner = PipelineRunner(run_id=run_id, log_path=log_path, continue_on_error=args.continue_on_error)
    final_output_dir = COMBINED_EVALUATIONS_DIR / run_id / normalize_direction(args.direction)
    final_status = "success"

    try:
        final_output_dir = run_pipeline(args, runner)
        if runner.failed_steps:
            final_status = "partial_success"
    except KeyboardInterrupt:
        final_status = "interrupted"
        runner.emit("")
        runner.emit("Pipeline interrupted by KeyboardInterrupt.")
    except (PipelineAbort, FileExistsError, ValueError, OSError) as exc:
        final_status = "failed"
        runner.emit("")
        runner.emit(f"Pipeline stopped: {exc}")
    finally:
        print_final_report(runner, final_status, final_output_dir)
        runner.close()

    if final_status == "success":
        return 0
    if final_status == "interrupted":
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
