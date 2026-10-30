import argparse
from datetime import datetime
from pathlib import Path
import subprocess
import sys

try:
    from research_costs import validate_orchestrator_cost_preflight
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_research_validation_pipeline
    from scripts.research_costs import validate_orchestrator_cost_preflight


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"

DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
DEFAULT_TIMEFRAME = "M15"
DEFAULT_TARGET_HORIZON = 10
DEFAULT_COMBINED_INPUT_DIR = BASE_DIR / "reports" / "backtests" / "combined"
DEFAULT_COMBINED_RUNS_DIR = DEFAULT_COMBINED_INPUT_DIR / "runs"
DEFAULT_COMBINED_EVALUATIONS_DIR = DEFAULT_COMBINED_INPUT_DIR / "evaluations"
DEFAULT_VALIDATION_OUTPUT_DIR = BASE_DIR / "reports" / "validation" / "by_year"
DEFAULT_DB_PATH = BASE_DIR / "data" / "trading_bot.db"
COMBINED_SUMMARY_FILE = "combined_hypotheses_summary.csv"
DEFAULT_FINAL_SCORECARD_OUTPUT_DIR = BASE_DIR / "reports" / "final_feature_scorecard"


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


def run_step(step_name: str, command: list[str]) -> None:
    print("")
    print(f"STEP: {step_name}")
    print(f"Command: {subprocess.list2cmdline(command)}")
    completed = subprocess.run(command, cwd=BASE_DIR, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{step_name} failed with exit code {completed.returncode}")
    print(f"Step completed: {step_name}")


def has_combined_summaries(path: Path) -> bool:
    return path.exists() and any(path.rglob(COMBINED_SUMMARY_FILE))


def latest_combined_run_dir(direction: str) -> Path | None:
    if not DEFAULT_COMBINED_RUNS_DIR.exists():
        return None
    candidates = [
        path
        for path in DEFAULT_COMBINED_RUNS_DIR.iterdir()
        if path.is_dir() and has_combined_summaries(path / direction)
    ]
    if direction == "long":
        candidates.extend(
            path
            for path in DEFAULT_COMBINED_RUNS_DIR.iterdir()
            if path.is_dir() and has_combined_summaries(path)
        )
    return sorted(candidates)[-1] if candidates else None


def resolve_combined_input(args: argparse.Namespace) -> tuple[str, Path]:
    if args.combined_input_dir is not None:
        combined_input_dir = Path(args.combined_input_dir)
        if not has_combined_summaries(combined_input_dir):
            raise FileNotFoundError(
                f"No {COMBINED_SUMMARY_FILE} files found under explicit --combined-input-dir: {combined_input_dir}"
            )
        inferred_name = combined_input_dir.parent.name if combined_input_dir.name in {"long", "short"} else combined_input_dir.name
        run_id = args.run_id.strip() if args.run_id else inferred_name
        if not run_id:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        return run_id, combined_input_dir

    if args.run_id:
        run_id = args.run_id.strip()
        if not run_id:
            raise ValueError("--run-id cannot be empty.")
        combined_input_dir = DEFAULT_COMBINED_RUNS_DIR / run_id / args.direction
        if args.direction == "long" and not has_combined_summaries(combined_input_dir):
            legacy_combined_input_dir = DEFAULT_COMBINED_RUNS_DIR / run_id
            if has_combined_summaries(legacy_combined_input_dir):
                combined_input_dir = legacy_combined_input_dir
        if not has_combined_summaries(combined_input_dir):
            raise FileNotFoundError(
                f"Combined run not found or empty: {combined_input_dir}. "
                "Pass --combined-input-dir explicitly if you want to evaluate a non-run directory."
            )
        return run_id, combined_input_dir

    latest = latest_combined_run_dir(args.direction)
    if latest is None:
        raise FileNotFoundError(
            f"No combined run found under {DEFAULT_COMBINED_RUNS_DIR}. "
            "Pass --run-id or --combined-input-dir explicitly."
        )
    directed = latest / args.direction
    if has_combined_summaries(directed):
        return latest.name, directed
    return latest.name, latest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the research-only post-backtest validation pipeline: "
            "evaluate combined hypotheses, then validate selected/watchlist combinations by year."
        )
    )
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--target-horizon", type=int, default=DEFAULT_TARGET_HORIZON)
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--run-id")
    parser.add_argument("--combined-input-dir", type=Path)
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
    return parser


def run_pipeline(args: argparse.Namespace) -> Path:
    symbols = normalize_symbols(args.symbols)
    if not symbols:
        raise ValueError("At least one symbol is required.")

    timeframe = args.timeframe.strip().upper()
    cost_mode, return_mode = validate_orchestrator_cost_preflight(
        cost_mode=args.cost_mode,
        return_mode=args.return_mode,
        cost_config_path=args.cost_config,
    )
    run_id, combined_input_dir = resolve_combined_input(args)
    combined_evaluation_dir = Path(args.combined_evaluations_dir) / run_id / args.direction
    selected_hypotheses_file = combined_evaluation_dir / "selected_combined_hypotheses.csv"
    cost_mode_args = ["--cost-mode", cost_mode, "--return-mode", return_mode]
    cost_estimation_args = list(cost_mode_args)
    if args.cost_config is not None:
        cost_estimation_args.extend(["--cost-config", str(args.cost_config)])
    if args.strict_cost_config:
        cost_estimation_args.append("--strict-cost-config")

    print("Research validation pipeline")
    print(f"Run ID: {run_id}")
    print(f"Symbols: {' '.join(symbols)}")
    print(f"Timeframe: {timeframe}")
    print(f"Target horizon: {args.target_horizon}")
    print(f"Direction: {args.direction}")
    print(f"Cost mode: {cost_mode}")
    print(f"Return mode: {return_mode}")
    print(f"Strict cost config: {str(args.strict_cost_config).lower()}")
    if args.cost_config is not None:
        print(f"Cost config: {args.cost_config}")
    print("This pipeline is research-only. It does not import MT5 data, create live signals, or call order APIs.")

    run_step(
        "1. evaluate combined hypotheses",
        script_command(
            "evaluate_combined_hypotheses.py",
            "--input-dir",
            combined_input_dir,
            "--output-dir",
            args.combined_evaluations_dir,
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
            *cost_mode_args,
        ),
    )

    if not selected_hypotheses_file.exists():
        raise FileNotFoundError(
            f"Selected combined hypotheses were not created: {selected_hypotheses_file}"
        )

    validation_command = script_command(
        "validate_hypotheses_by_year.py",
        "--hypotheses-file",
        selected_hypotheses_file,
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
        args.db_path,
        "--output-dir",
        args.validation_output_dir,
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
    if args.overwrite_validation:
        validation_command.append("--overwrite")

    run_step("2. validate combined hypotheses by year", validation_command)

    scorecard_command = script_command(
        "build_final_feature_scorecard.py",
        "--run-id",
        run_id,
        "--direction",
        args.direction,
        "--validation-dir",
        args.validation_output_dir,
        "--combined-evaluations-dir",
        args.combined_evaluations_dir,
        "--output-dir",
        args.scorecard_output_dir,
        "--min-trades-per-year",
        args.min_trades_per_year,
        *cost_mode_args,
    )
    if args.overwrite_validation:
        scorecard_command.append("--overwrite")
    run_step("3. build final feature scorecard", scorecard_command)

    print("")
    print("Research validation pipeline complete")
    print(f"Combined evaluation output: {combined_evaluation_dir}")
    validation_output = Path(args.validation_output_dir) / run_id / args.direction
    scorecard_output = Path(args.scorecard_output_dir) / run_id / args.direction
    print(f"Year-by-year validation output: {validation_output}")
    print(f"Cross-pair candidates report: {validation_output / 'final_research_candidates_report.md'}")
    print(f"Pair-specific candidates report: {validation_output / 'pair_specific_candidates_report.md'}")
    print(f"Cross-pair candidates CSV: {validation_output / 'final_research_candidates.csv'}")
    print(f"Pair-specific candidates CSV: {validation_output / 'pair_specific_candidates.csv'}")
    print(f"Final feature scorecard output: {scorecard_output}")
    print(f"Cross-pair feature scorecard: {scorecard_output / 'final_feature_scorecard.csv'}")
    print(f"Pair-specific feature scorecard: {scorecard_output / 'pair_specific_feature_scorecard.csv'}")
    return validation_output


def main() -> int:
    args = build_parser().parse_args()
    try:
        run_pipeline(args)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Research validation pipeline failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
