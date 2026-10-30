"""Orchestrate research-only preferred horizon and cost diagnostics.

This script builds a controlled matrix across symbol groups, horizons, and
cost profiles, then either records the planned child research commands or runs
the existing child scripts. It does not implement a new backtester, search new
feature pairs, optimize TP/SL values, or add broker execution logic.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Iterable

try:
    from target_families import (
        PREFERRED_2ATR_1ATR_HIT_FIRST,
        family_scoped_root,
        format_atr_multiplier,
        supported_target_family_names,
        target_column_for_family,
        target_family_for_multipliers,
        target_family_spec,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.target_families import (
        PREFERRED_2ATR_1ATR_HIT_FIRST,
        family_scoped_root,
        format_atr_multiplier,
        supported_target_family_names,
        target_column_for_family,
        target_family_for_multipliers,
        target_family_spec,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "preferred_horizon_cost_diagnostics"
DEFAULT_SHORTLIST_ROOT = BASE_DIR / "reports" / "ml_research" / "preferred_feature_hypotheses"
DEFAULT_COST_CONFIGS = {
    "p50": BASE_DIR / "config" / "brokers" / "pepperstone_historical_p50.local.json",
    "p75": BASE_DIR / "config" / "brokers" / "pepperstone_historical_p75.local.json",
    "p90": BASE_DIR / "config" / "brokers" / "pepperstone_historical_p90.local.json",
}
GROUP_SYMBOLS = {
    "fx": ("EURUSD", "GBPUSD", "USDJPY"),
    "xauusd": ("XAUUSD",),
}
DIRECTIONS = ("long", "short")
CLASSIFICATION_CANDIDATE = "CANDIDATA_A_TEST_SUCCESSIVI"
CLASSIFICATION_REVIEW = "DA_APPROFONDIRE"
CLASSIFICATION_REJECT = "SCARTARE"
DECISION_CLOSED = "CLOSED_NO_SURVIVOR"
DECISION_NO_TESTED = "NO_TESTED_COMBINATIONS"
DECISION_REVIEW = "NEEDS_REVIEW"
DECISION_CANDIDATES = "CANDIDATES_FOUND"

MATRIX_SUMMARY_FILE = "matrix_summary.csv"
MATRIX_REPORT_FILE = "matrix_report.md"
SKIPPED_BRANCHES_FILE = "skipped_branches.csv"
BRANCH_MANIFEST_FILE = "branch_manifest.json"
ZERO_TESTED_DIAGNOSTICS_FILE = "zero_tested_diagnostics.csv"
ZERO_TESTED_REPORT_FILE = "zero_tested_diagnostics.md"
OUTPUT_FILES = (
    MATRIX_SUMMARY_FILE,
    MATRIX_REPORT_FILE,
    SKIPPED_BRANCHES_FILE,
    BRANCH_MANIFEST_FILE,
)

MATRIX_FIELDNAMES = [
    "run_id",
    "branch_id",
    "group_name",
    "symbols",
    "timeframe",
    "horizon",
    "cost_profile",
    "cost_config",
    "target_family",
    "tp_atr",
    "sl_atr",
    "atr_column",
    "same_bar_policy",
    "target_long",
    "target_short",
    "preferred_feature_backtest_run_id_gross",
    "preferred_feature_backtest_run_id_net",
    "cost_mode_comparison_path_long",
    "cost_mode_comparison_path_short",
    "combination_run_id",
    "tp_sl_path_run_id_long",
    "tp_sl_path_run_id_short",
    "branch_outcome_run_id",
    "long_input_combinations",
    "long_tested_combinations",
    "long_scartare_count",
    "long_da_approfondire_count",
    "long_candidata_count",
    "short_input_combinations",
    "short_tested_combinations",
    "short_scartare_count",
    "short_da_approfondire_count",
    "short_candidata_count",
    "best_long_mean_R",
    "best_long_profit_factor_R",
    "best_short_mean_R",
    "best_short_profit_factor_R",
    "branch_decision",
    "status",
    "notes",
]

SKIPPED_FIELDNAMES = [
    "run_id",
    "branch_id",
    "group_name",
    "symbols",
    "timeframe",
    "horizon",
    "cost_profile",
    "cost_config",
    "reason",
    "command",
    "exit_code",
    "log_path",
]

ZERO_TESTED_FIELDNAMES = [
    "run_id",
    "branch_id",
    "group_name",
    "symbols",
    "timeframe",
    "horizon",
    "cost_profile",
    "direction",
    "preferred_feature_backtest_summary_rows",
    "preferred_feature_backtest_summary_rows_gross",
    "preferred_feature_backtest_summary_rows_net",
    "cost_mode_comparison_rows",
    "gross_positive_rows",
    "net_positive_rows",
    "cost_erased_rows",
    "cost_erased_or_net_nonpositive_rows",
    "rows_after_preferred_shortlist_source_criteria",
    "primary_family_candidates",
    "secondary_family_candidates",
    "combinations_built",
    "combination_detail_rows",
    "tp_sl_input_rows",
    "tp_sl_tested_rows",
    "combination_skipped_rows",
    "tp_sl_skipped_rows",
    "skipped_rows",
    "zero_tested_reason",
    "diagnostic_notes",
]


@dataclass(frozen=True)
class Branch:
    run_id: str
    branch_id: str
    group_name: str
    symbols: tuple[str, ...]
    timeframe: str
    horizon: int
    cost_profile: str
    cost_config: Path
    target_family: str
    tp_atr: float
    sl_atr: float
    atr_column: str
    same_bar_policy: str
    return_mode: str

    @property
    def target_long(self) -> str:
        return target_column_for_family("long", self.target_family, self.horizon)

    @property
    def target_short(self) -> str:
        return target_column_for_family("short", self.target_family, self.horizon)

    @property
    def gross_run_id(self) -> str:
        return f"{self.run_id}_{self.branch_id}_gross"

    @property
    def net_run_id(self) -> str:
        return f"{self.run_id}_{self.branch_id}_net"

    @property
    def combination_run_id(self) -> str:
        return f"{self.run_id}_{self.branch_id}_combo"

    @property
    def tp_sl_run_id(self) -> str:
        return f"{self.run_id}_{self.branch_id}_tp_sl"

    @property
    def branch_outcome_run_id(self) -> str:
        return f"{self.run_id}_{self.branch_id}_outcome"


@dataclass(frozen=True)
class ChildCommand:
    step: str
    command: tuple[str, ...]
    log_path: Path | None = None


CommandRunner = Callable[[ChildCommand], int]


def current_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def format_multiplier(value: float) -> str:
    return format_atr_multiplier(value)


def branch_id_for(
    *,
    timeframe: str,
    horizon: int,
    tp_atr: float,
    sl_atr: float,
    cost_profile: str,
    group_name: str,
) -> str:
    return (
        f"{timeframe}_h{int(horizon)}_preferred_"
        f"{format_multiplier(tp_atr)}atr_{format_multiplier(sl_atr)}atr_"
        f"{cost_profile}_{group_name}"
    )


def normalize_groups(groups: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for value in groups:
        group_name = str(value or "").strip().lower()
        if group_name not in GROUP_SYMBOLS:
            raise ValueError(f"Unsupported group {value!r}. Expected one of: {', '.join(sorted(GROUP_SYMBOLS))}.")
        if group_name not in normalized:
            normalized.append(group_name)
    if not normalized:
        raise ValueError("--groups must include at least one group.")
    return normalized


def normalize_cost_profiles(values: Iterable[str]) -> list[str]:
    profiles: list[str] = []
    for value in values:
        profile = str(value or "").strip().lower()
        if profile not in DEFAULT_COST_CONFIGS:
            raise ValueError("Unsupported cost profile {profile!r}. Expected p50, p75, or p90.")
        if profile not in profiles:
            profiles.append(profile)
    if not profiles:
        raise ValueError("--cost-profiles must include at least one profile.")
    return profiles


def normalize_horizons(values: Iterable[int]) -> list[int]:
    horizons: list[int] = []
    for value in values:
        horizon = int(value)
        if horizon <= 0:
            raise ValueError("--horizons values must be positive.")
        if horizon not in horizons:
            horizons.append(horizon)
    if not horizons:
        raise ValueError("--horizons must include at least one horizon.")
    return horizons


def cost_config_mapping(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "p50": Path(args.cost_config_p50),
        "p75": Path(args.cost_config_p75),
        "p90": Path(args.cost_config_p90),
    }


def build_branch_matrix(args: argparse.Namespace, run_id: str) -> list[Branch]:
    timeframe = str(args.timeframe).strip().upper()
    if not timeframe:
        raise ValueError("--timeframe cannot be empty.")
    groups = normalize_groups(args.groups)
    horizons = normalize_horizons(args.horizons)
    profiles = normalize_cost_profiles(args.cost_profiles)
    configs = cost_config_mapping(args)
    family = target_family_spec(str(getattr(args, "target_family", PREFERRED_2ATR_1ATR_HIT_FIRST)))
    branches: list[Branch] = []
    for group_name in groups:
        for horizon in horizons:
            for profile in profiles:
                branch_id = branch_id_for(
                    timeframe=timeframe,
                    horizon=horizon,
                    tp_atr=family.tp_atr,
                    sl_atr=family.sl_atr,
                    cost_profile=profile,
                    group_name=group_name,
                )
                branches.append(
                    Branch(
                        run_id=run_id,
                        branch_id=branch_id,
                        group_name=group_name,
                        symbols=GROUP_SYMBOLS[group_name],
                        timeframe=timeframe,
                        horizon=horizon,
                        cost_profile=profile,
                        cost_config=configs[profile],
                        target_family=family.name,
                        tp_atr=family.tp_atr,
                        sl_atr=family.sl_atr,
                        atr_column=str(args.atr_column),
                        same_bar_policy=str(args.same_bar_policy),
                        return_mode=str(args.return_mode),
                    )
                )
    return branches


def output_dir_for(output_root: Path, run_id: str) -> Path:
    return output_root / run_id


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_dir_for(output_root, run_id)
    return {
        "matrix_summary": output_dir / MATRIX_SUMMARY_FILE,
        "matrix_report": output_dir / MATRIX_REPORT_FILE,
        "skipped_branches": output_dir / SKIPPED_BRANCHES_FILE,
        "branch_manifest": output_dir / BRANCH_MANIFEST_FILE,
    }


def zero_tested_output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_dir_for(output_root, run_id)
    return {
        "zero_tested_diagnostics": output_dir / ZERO_TESTED_DIAGNOSTICS_FILE,
        "zero_tested_report": output_dir / ZERO_TESTED_REPORT_FILE,
    }


def ensure_outputs_writable(paths: Iterable[Path], overwrite: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Preferred horizon/cost diagnostic outputs already exist. Pass --overwrite to regenerate: "
            + ", ".join(str(path) for path in existing)
        )


def repo_path(*parts: str) -> str:
    return str(Path(*parts))


def maybe_overwrite(args: argparse.Namespace) -> list[str]:
    return ["--overwrite"] if bool(args.overwrite) else []


def child_commands(branch: Branch, args: argparse.Namespace, output_dir: Path) -> list[ChildCommand]:
    python_executable = str(args.python_executable)
    overwrite = maybe_overwrite(args)
    symbols = list(branch.symbols)
    common_directions = ["--directions", *DIRECTIONS]
    cost_config_text = str(branch.cost_config)
    shortlist_root = str(family_scoped_root(DEFAULT_SHORTLIST_ROOT, branch.target_family))
    logs_dir = output_dir / "logs"

    commands = [
        ChildCommand(
            step="preferred_feature_backtest_gross",
            command=(
                python_executable,
                repo_path("scripts", "run_preferred_feature_backtests.py"),
                "--symbols",
                *symbols,
                "--timeframe",
                branch.timeframe,
                "--horizon",
                str(branch.horizon),
                *common_directions,
                "--cost-mode",
                "none",
                "--return-mode",
                "gross",
                "--run-id",
                branch.gross_run_id,
                "--input-root",
                shortlist_root,
                "--strict-shortlist-only",
                *overwrite,
            ),
            log_path=logs_dir / f"{branch.branch_id}_preferred_feature_backtest_gross.log",
        ),
        ChildCommand(
            step="preferred_feature_backtest_net",
            command=(
                python_executable,
                repo_path("scripts", "run_preferred_feature_backtests.py"),
                "--symbols",
                *symbols,
                "--timeframe",
                branch.timeframe,
                "--horizon",
                str(branch.horizon),
                *common_directions,
                "--cost-mode",
                "estimated",
                "--return-mode",
                branch.return_mode,
                "--cost-config",
                cost_config_text,
                "--strict-cost-config",
                "--run-id",
                branch.net_run_id,
                "--input-root",
                shortlist_root,
                "--strict-shortlist-only",
                *overwrite,
            ),
            log_path=logs_dir / f"{branch.branch_id}_preferred_feature_backtest_net.log",
        ),
        ChildCommand(
            step="cost_mode_comparison",
            command=(
                python_executable,
                repo_path("scripts", "compare_preferred_feature_backtest_cost_modes.py"),
                "--gross-run-id",
                branch.gross_run_id,
                "--net-run-id",
                branch.net_run_id,
                *common_directions,
            ),
            log_path=logs_dir / f"{branch.branch_id}_cost_mode_comparison.log",
        ),
        ChildCommand(
            step="controlled_combination_backtest",
            command=(
                python_executable,
                repo_path("scripts", "run_preferred_feature_combination_backtests.py"),
                "--symbols",
                *symbols,
                "--timeframe",
                branch.timeframe,
                "--horizon",
                str(branch.horizon),
                *common_directions,
                "--gross-run-id",
                branch.gross_run_id,
                "--net-run-id",
                branch.net_run_id,
                "--cost-mode",
                "estimated",
                "--return-mode",
                branch.return_mode,
                "--cost-config",
                cost_config_text,
                "--strict-cost-config",
                "--run-id",
                branch.combination_run_id,
                *overwrite,
            ),
            log_path=logs_dir / f"{branch.branch_id}_controlled_combination_backtest.log",
        ),
    ]

    for direction in DIRECTIONS:
        commands.append(
            ChildCommand(
                step=f"tp_sl_path_batch_{direction}",
                command=(
                    python_executable,
                    repo_path("scripts", "run_tp_sl_path_backtests.py"),
                    "--combination-input-csv",
                    str(combination_detail_path(branch, direction)),
                    "--timeframe",
                    branch.timeframe,
                    "--horizon",
                    str(branch.horizon),
                    "--tp-atr",
                    str(branch.tp_atr),
                    "--sl-atr",
                    str(branch.sl_atr),
                    "--atr-column",
                    branch.atr_column,
                    "--same-bar-policy",
                    branch.same_bar_policy,
                    "--cost-mode",
                    "estimated",
                    "--return-mode",
                    branch.return_mode,
                    "--strict-cost-config",
                    "--cost-config",
                    cost_config_text,
                    "--run-id",
                    branch.tp_sl_run_id,
                    *overwrite,
                ),
                log_path=logs_dir / f"{branch.branch_id}_tp_sl_path_batch_{direction}.log",
            )
        )

    return commands


def branch_outcome_command(branch: Branch, args: argparse.Namespace, output_dir: Path, decision: str) -> ChildCommand:
    return ChildCommand(
        step="branch_outcome_report",
        command=(
            str(args.python_executable),
            repo_path("scripts", "build_research_branch_outcome_report.py"),
            "--branch-id",
            branch.branch_id,
            "--branch-title",
            branch_title(branch),
            "--symbols",
            *branch.symbols,
            "--directions",
            *DIRECTIONS,
            "--timeframe",
            branch.timeframe,
            "--horizon",
            str(branch.horizon),
            "--target-family",
            branch.target_family,
            "--cost-mode",
            "estimated",
            "--return-mode",
            branch.return_mode,
            "--long-tp-sl-run-id",
            branch.tp_sl_run_id,
            "--short-tp-sl-run-id",
            branch.tp_sl_run_id,
            "--decision",
            decision,
            "--run-id",
            branch.branch_outcome_run_id,
            *maybe_overwrite(args),
        ),
        log_path=output_dir / "logs" / f"{branch.branch_id}_branch_outcome_report.log",
    )


def command_text(command: Iterable[str]) -> str:
    return " ".join(str(part) for part in command)


def run_child_command(command: ChildCommand) -> int:
    assert command.log_path is not None
    command.log_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        list(command.command),
        cwd=BASE_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    command.log_path.write_text(result.stdout or "", encoding="utf-8")
    return int(result.returncode)


def preferred_cost_comparison_path(branch: Branch, direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "preferred_feature_backtests"
        / "cost_mode_comparison"
        / f"{branch.gross_run_id}_vs_{branch.net_run_id}"
        / direction
        / "cost_mode_comparison.csv"
    )


def preferred_feature_summary_path_from_row(row: dict[str, object], direction: str, mode: str) -> Path:
    run_id_key = (
        "preferred_feature_backtest_run_id_gross"
        if mode == "gross"
        else "preferred_feature_backtest_run_id_net"
    )
    return (
        BASE_DIR
        / "reports"
        / "preferred_feature_backtests"
        / str(row.get(run_id_key) or "")
        / direction
        / "preferred_feature_backtest_summary.csv"
    )


def preferred_cost_comparison_path_from_row(row: dict[str, object], direction: str) -> Path:
    text = str(row.get(f"cost_mode_comparison_path_{direction}") or "").strip()
    if text:
        return Path(text)
    return (
        BASE_DIR
        / "reports"
        / "preferred_feature_backtests"
        / "cost_mode_comparison"
        / f"{row.get('preferred_feature_backtest_run_id_gross')}_vs_{row.get('preferred_feature_backtest_run_id_net')}"
        / direction
        / "cost_mode_comparison.csv"
    )


def combination_detail_path(branch: Branch, direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "preferred_feature_combination_backtests"
        / branch.combination_run_id
        / direction
        / "combination_backtest_detail.csv"
    )


def combination_detail_path_from_row(row: dict[str, object], direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "preferred_feature_combination_backtests"
        / str(row.get("combination_run_id") or "")
        / direction
        / "combination_backtest_detail.csv"
    )


def combination_skipped_path_from_row(row: dict[str, object], direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "preferred_feature_combination_backtests"
        / str(row.get("combination_run_id") or "")
        / direction
        / "skipped_combinations.csv"
    )


def candidate_diagnostics_path_from_row(row: dict[str, object], direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "preferred_feature_combination_backtests"
        / str(row.get("combination_run_id") or "")
        / direction
        / "candidate_diagnostics.csv"
    )


def tp_sl_summary_path(branch: Branch, direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "tp_sl_path_backtests"
        / branch.tp_sl_run_id
        / direction
        / "tp_sl_path_backtest_summary.csv"
    )


def tp_sl_summary_path_from_row(row: dict[str, object], direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "tp_sl_path_backtests"
        / str(row.get(f"tp_sl_path_run_id_{direction}") or row.get("tp_sl_path_run_id") or "")
        / direction
        / "tp_sl_path_backtest_summary.csv"
    )


def tp_sl_detail_path(branch: Branch, direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "tp_sl_path_backtests"
        / branch.tp_sl_run_id
        / direction
        / "tp_sl_path_backtest_detail.csv"
    )


def tp_sl_detail_path_from_row(row: dict[str, object], direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "tp_sl_path_backtests"
        / str(row.get(f"tp_sl_path_run_id_{direction}") or row.get("tp_sl_path_run_id") or "")
        / direction
        / "tp_sl_path_backtest_detail.csv"
    )


def tp_sl_skipped_path_from_row(row: dict[str, object], direction: str) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "tp_sl_path_backtests"
        / str(row.get(f"tp_sl_path_run_id_{direction}") or row.get("tp_sl_path_run_id") or "")
        / direction
        / "skipped_tp_sl_path_rows.csv"
    )


def branch_outcome_report_path(branch: Branch) -> Path:
    return (
        BASE_DIR
        / "reports"
        / "research_branch_outcomes"
        / branch.branch_outcome_run_id
        / "branch_outcome_report.md"
    )


def branch_title(branch: Branch) -> str:
    return (
        f"{branch.timeframe} h{branch.horizon} preferred "
        f"{format_multiplier(branch.tp_atr)}ATR/{format_multiplier(branch.sl_atr)}ATR "
        f"{branch.cost_profile} {branch.group_name} branch"
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return [dict(row) for row in csv.DictReader(csv_file)]


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed


def int_value(value: object) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def bool_value(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def best_metric(rows: list[dict[str, str]], column: str) -> float | None:
    values = [safe_float(row.get(column)) for row in rows]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def direction_metrics(branch: Branch, direction: str) -> dict[str, object]:
    summary_rows = read_csv_rows(tp_sl_summary_path(branch, direction))
    combination_rows = read_csv_rows(combination_detail_path(branch, direction))
    scartare = sum(1 for row in summary_rows if row.get("classification") == CLASSIFICATION_REJECT)
    review = sum(1 for row in summary_rows if row.get("classification") == CLASSIFICATION_REVIEW)
    candidate = sum(1 for row in summary_rows if row.get("classification") == CLASSIFICATION_CANDIDATE)
    return {
        f"{direction}_input_combinations": len(combination_rows),
        f"{direction}_tested_combinations": len(summary_rows),
        f"{direction}_scartare_count": scartare,
        f"{direction}_da_approfondire_count": review,
        f"{direction}_candidata_count": candidate,
        f"best_{direction}_mean_R": best_metric(summary_rows, "mean_R"),
        f"best_{direction}_profit_factor_R": best_metric(summary_rows, "profit_factor_R"),
    }


def branch_decision_from_metrics(row: dict[str, object]) -> str:
    candidata = int(row.get("long_candidata_count") or 0) + int(row.get("short_candidata_count") or 0)
    review = int(row.get("long_da_approfondire_count") or 0) + int(row.get("short_da_approfondire_count") or 0)
    tested = int(row.get("long_tested_combinations") or 0) + int(row.get("short_tested_combinations") or 0)
    scartare = int(row.get("long_scartare_count") or 0) + int(row.get("short_scartare_count") or 0)
    if candidata > 0:
        return DECISION_CANDIDATES
    if review > 0:
        return DECISION_REVIEW
    if tested == 0:
        return DECISION_NO_TESTED
    if tested > 0 and tested == scartare:
        return DECISION_CLOSED
    return DECISION_REVIEW


def zero_tested_reason_for_direction(branch: Branch, direction: str) -> str | None:
    summary_path = tp_sl_summary_path(branch, direction)
    combination_path = combination_detail_path(branch, direction)
    tp_sl_detail = tp_sl_detail_path(branch, direction)
    summary_rows = read_csv_rows(summary_path)
    if summary_rows:
        return None
    combination_rows = read_csv_rows(combination_path)
    if not combination_path.exists():
        return f"{direction}: missing path batch input"
    if not combination_rows:
        return f"{direction}: no combination rows"
    if summary_path.exists() and tp_sl_detail.exists() and not read_csv_rows(tp_sl_detail):
        return f"{direction}: child output exists but no detail rows"
    if summary_path.exists() and not summary_rows:
        return f"{direction}: empty input CSV"
    return f"{direction}: no tested TP/SL path rows"


def zero_tested_notes(branch: Branch, row: dict[str, object]) -> str:
    total_tested = int(row.get("long_tested_combinations") or 0) + int(row.get("short_tested_combinations") or 0)
    if total_tested > 0:
        return "Completed child diagnostics."
    reasons = [
        reason
        for direction in DIRECTIONS
        if (reason := zero_tested_reason_for_direction(branch, direction)) is not None
    ]
    if reasons:
        return "No tested combinations. " + "; ".join(reasons) + "."
    return "No tested combinations."


def empty_direction_metrics(direction: str) -> dict[str, object]:
    return {
        f"{direction}_input_combinations": "",
        f"{direction}_tested_combinations": "",
        f"{direction}_scartare_count": "",
        f"{direction}_da_approfondire_count": "",
        f"{direction}_candidata_count": "",
        f"best_{direction}_mean_R": "",
        f"best_{direction}_profit_factor_R": "",
    }


def matrix_row_for_branch(
    branch: Branch,
    *,
    status: str,
    notes: str,
    decision: str = "",
    include_metrics: bool = False,
) -> dict[str, object]:
    row: dict[str, object] = {
        "run_id": branch.run_id,
        "branch_id": branch.branch_id,
        "group_name": branch.group_name,
        "symbols": " ".join(branch.symbols),
        "timeframe": branch.timeframe,
        "horizon": branch.horizon,
        "cost_profile": branch.cost_profile,
        "cost_config": str(branch.cost_config),
        "target_family": branch.target_family,
        "tp_atr": branch.tp_atr,
        "sl_atr": branch.sl_atr,
        "atr_column": branch.atr_column,
        "same_bar_policy": branch.same_bar_policy,
        "target_long": branch.target_long,
        "target_short": branch.target_short,
        "preferred_feature_backtest_run_id_gross": branch.gross_run_id,
        "preferred_feature_backtest_run_id_net": branch.net_run_id,
        "cost_mode_comparison_path_long": str(preferred_cost_comparison_path(branch, "long")),
        "cost_mode_comparison_path_short": str(preferred_cost_comparison_path(branch, "short")),
        "combination_run_id": branch.combination_run_id,
        "tp_sl_path_run_id_long": branch.tp_sl_run_id,
        "tp_sl_path_run_id_short": branch.tp_sl_run_id,
        "branch_outcome_run_id": branch.branch_outcome_run_id,
        "branch_decision": decision,
        "status": status,
        "notes": notes,
    }
    if include_metrics:
        row.update(direction_metrics(branch, "long"))
        row.update(direction_metrics(branch, "short"))
        row["branch_decision"] = branch_decision_from_metrics(row)
        row["notes"] = zero_tested_notes(branch, row) if row["branch_decision"] == DECISION_NO_TESTED else notes
    else:
        row.update(empty_direction_metrics("long"))
        row.update(empty_direction_metrics("short"))
    return row


def branch_from_matrix_row(row: dict[str, object], run_id: str) -> Branch:
    symbols = tuple(str(row.get("symbols") or "").split())
    if not symbols:
        group_name = str(row.get("group_name") or "fx")
        symbols = GROUP_SYMBOLS.get(group_name, ())
    tp_atr = float(row.get("tp_atr") or 2.0)
    sl_atr = float(row.get("sl_atr") or 1.0)
    target_family = str(row.get("target_family") or "").strip()
    if not target_family:
        target_family = target_family_for_multipliers(tp_atr, sl_atr) or PREFERRED_2ATR_1ATR_HIT_FIRST
    return Branch(
        run_id=run_id,
        branch_id=str(row.get("branch_id") or ""),
        group_name=str(row.get("group_name") or ""),
        symbols=symbols,
        timeframe=str(row.get("timeframe") or "M15"),
        horizon=int(row.get("horizon") or 10),
        cost_profile=str(row.get("cost_profile") or ""),
        cost_config=Path(str(row.get("cost_config") or "")),
        target_family=target_family,
        tp_atr=tp_atr,
        sl_atr=sl_atr,
        atr_column=str(row.get("atr_column") or "atr_20"),
        same_bar_policy=str(row.get("same_bar_policy") or "stop_first"),
        return_mode=str(row.get("return_mode") or "net"),
    )


def skipped_branch_row(
    branch: Branch,
    *,
    reason: str,
    command: str = "",
    exit_code: object = "",
    log_path: Path | str = "",
) -> dict[str, object]:
    return {
        "run_id": branch.run_id,
        "branch_id": branch.branch_id,
        "group_name": branch.group_name,
        "symbols": " ".join(branch.symbols),
        "timeframe": branch.timeframe,
        "horizon": branch.horizon,
        "cost_profile": branch.cost_profile,
        "cost_config": str(branch.cost_config),
        "reason": reason,
        "command": command,
        "exit_code": exit_code,
        "log_path": str(log_path),
    }


def csv_safe(value: object) -> object:
    if value is None:
        return ""
    return value


def existing_zero_tested_notes(row: dict[str, object]) -> str:
    total_tested = int(row.get("long_tested_combinations") or 0) + int(row.get("short_tested_combinations") or 0)
    if total_tested > 0:
        return str(row.get("notes") or "Completed child diagnostics.")
    existing_notes = str(row.get("notes") or "")
    if existing_notes.startswith("No tested combinations."):
        return existing_notes
    return (
        "No tested combinations. Existing child outputs produced zero TP/SL path rows; "
        "inspect combination inputs, skipped outputs, and path detail files for the branch-specific cause."
    )


def aggregate_candidate_diagnostics(rows: list[dict[str, str]]) -> dict[str, int | str]:
    if not rows:
        return {
            "input_rows_loaded": 0,
            "rows_after_net_filter": 0,
            "rows_after_shortlist_filter": 0,
            "primary_candidates": 0,
            "secondary_candidates": 0,
            "combinations_built": 0,
            "skipped_rows": 0,
            "notes": "",
        }
    all_rows = [row for row in rows if str(row.get("symbol") or "").upper() == "ALL"]
    source_rows = all_rows or rows
    columns = [
        "input_rows_loaded",
        "rows_after_net_filter",
        "rows_after_shortlist_filter",
        "primary_candidates",
        "secondary_candidates",
        "combinations_built",
        "skipped_rows",
    ]
    totals = {column: sum(int_value(row.get(column)) for row in source_rows) for column in columns}
    notes = "; ".join(
        sorted({str(row.get("notes") or "").strip() for row in source_rows if str(row.get("notes") or "").strip()})
    )
    totals["notes"] = notes
    return totals


def count_cost_mode_rows(rows: list[dict[str, str]]) -> dict[str, int]:
    gross_positive = 0
    net_positive = 0
    cost_erased = 0
    cost_erased_or_net_nonpositive = 0
    for row in rows:
        gross = bool_value(row.get("gross_positive"))
        net = bool_value(row.get("net_positive"))
        erased = bool_value(row.get("cost_erased_edge"))
        if gross:
            gross_positive += 1
        if net:
            net_positive += 1
        if erased:
            cost_erased += 1
        if gross and (erased or not net):
            cost_erased_or_net_nonpositive += 1
    return {
        "gross_positive_rows": gross_positive,
        "net_positive_rows": net_positive,
        "cost_erased_rows": cost_erased,
        "cost_erased_or_net_nonpositive_rows": cost_erased_or_net_nonpositive,
    }


def missing_child_outputs(paths: dict[str, Path], metrics: dict[str, object]) -> list[str]:
    missing: list[str] = []
    for key, path in paths.items():
        if key in {"tp_sl_detail", "combination_skipped", "tp_sl_skipped"}:
            continue
        if not path.exists():
            missing.append(key)
    return missing


def determine_zero_tested_reason(metrics: dict[str, object], missing_outputs: list[str]) -> str:
    missing = set(missing_outputs)
    if {"preferred_gross_summary", "preferred_net_summary"}.issubset(missing):
        return "missing_child_output"
    if int_value(metrics.get("preferred_feature_backtest_summary_rows")) == 0:
        return "no_preferred_backtest_rows"
    if "cost_mode_comparison" in missing:
        return "missing_child_output"
    if int_value(metrics.get("gross_positive_rows")) == 0:
        return "no_gross_positive_rows"
    if int_value(metrics.get("cost_erased_or_net_nonpositive_rows")) == 0:
        return "no_cost_erased_or_net_nonpositive_rows"
    if "candidate_diagnostics" in missing:
        return "missing_child_output"
    if int_value(metrics.get("rows_after_preferred_shortlist_source_criteria")) == 0:
        return "no_preferred_shortlist_rows"
    if int_value(metrics.get("primary_family_candidates")) == 0:
        return "no_primary_family_candidates"
    if int_value(metrics.get("secondary_family_candidates")) == 0:
        return "no_secondary_family_candidates"
    if int_value(metrics.get("combinations_built")) == 0:
        return "no_combinations_built"
    if "combination_detail" in missing:
        return "missing_child_output"
    if int_value(metrics.get("combination_detail_rows")) == 0:
        return "empty_combination_detail_csv"
    if "tp_sl_summary" in missing:
        return "missing_child_output"
    if int_value(metrics.get("tp_sl_input_rows")) == 0:
        return "tp_sl_batch_empty_input"
    if int_value(metrics.get("tp_sl_tested_rows")) == 0 and int_value(metrics.get("tp_sl_skipped_rows")) > 0:
        return "tp_sl_batch_all_rows_skipped"
    return "missing_child_output"


def zero_tested_diagnostic_row(matrix_row: dict[str, object], direction: str) -> dict[str, object]:
    paths = {
        "preferred_gross_summary": preferred_feature_summary_path_from_row(matrix_row, direction, "gross"),
        "preferred_net_summary": preferred_feature_summary_path_from_row(matrix_row, direction, "net"),
        "cost_mode_comparison": preferred_cost_comparison_path_from_row(matrix_row, direction),
        "candidate_diagnostics": candidate_diagnostics_path_from_row(matrix_row, direction),
        "combination_detail": combination_detail_path_from_row(matrix_row, direction),
        "combination_skipped": combination_skipped_path_from_row(matrix_row, direction),
        "tp_sl_summary": tp_sl_summary_path_from_row(matrix_row, direction),
        "tp_sl_detail": tp_sl_detail_path_from_row(matrix_row, direction),
        "tp_sl_skipped": tp_sl_skipped_path_from_row(matrix_row, direction),
    }
    gross_summary_rows = read_csv_rows(paths["preferred_gross_summary"])
    net_summary_rows = read_csv_rows(paths["preferred_net_summary"])
    cost_rows = read_csv_rows(paths["cost_mode_comparison"])
    candidate_rows = read_csv_rows(paths["candidate_diagnostics"])
    combination_rows = read_csv_rows(paths["combination_detail"])
    combination_skipped_rows = read_csv_rows(paths["combination_skipped"])
    tp_sl_summary_rows = read_csv_rows(paths["tp_sl_summary"])
    tp_sl_skipped_rows = read_csv_rows(paths["tp_sl_skipped"])

    cost_counts = count_cost_mode_rows(cost_rows)
    candidate_counts = aggregate_candidate_diagnostics(candidate_rows)
    metrics: dict[str, object] = {
        "run_id": matrix_row.get("run_id"),
        "branch_id": matrix_row.get("branch_id"),
        "group_name": matrix_row.get("group_name"),
        "symbols": matrix_row.get("symbols"),
        "timeframe": matrix_row.get("timeframe"),
        "horizon": matrix_row.get("horizon"),
        "cost_profile": matrix_row.get("cost_profile"),
        "direction": direction,
        "preferred_feature_backtest_summary_rows": len(gross_summary_rows) + len(net_summary_rows),
        "preferred_feature_backtest_summary_rows_gross": len(gross_summary_rows),
        "preferred_feature_backtest_summary_rows_net": len(net_summary_rows),
        "cost_mode_comparison_rows": len(cost_rows),
        **cost_counts,
        "rows_after_preferred_shortlist_source_criteria": candidate_counts["rows_after_shortlist_filter"],
        "primary_family_candidates": candidate_counts["primary_candidates"],
        "secondary_family_candidates": candidate_counts["secondary_candidates"],
        "combinations_built": candidate_counts["combinations_built"],
        "combination_detail_rows": len(combination_rows),
        "tp_sl_input_rows": len(combination_rows),
        "tp_sl_tested_rows": len(tp_sl_summary_rows),
        "combination_skipped_rows": len(combination_skipped_rows),
        "tp_sl_skipped_rows": len(tp_sl_skipped_rows),
        "skipped_rows": len(combination_skipped_rows) + len(tp_sl_skipped_rows),
    }
    missing = missing_child_outputs(paths, metrics)
    metrics["zero_tested_reason"] = determine_zero_tested_reason(metrics, missing)
    note_parts: list[str] = []
    if missing:
        note_parts.append("missing outputs: " + ", ".join(missing))
    candidate_notes = str(candidate_counts.get("notes") or "").strip()
    if candidate_notes:
        note_parts.append(f"candidate diagnostics: {candidate_notes}")
    if not note_parts:
        note_parts.append("diagnosed from existing child CSV outputs")
    metrics["diagnostic_notes"] = "; ".join(note_parts)
    return metrics


def should_diagnose_zero_tested_direction(row: dict[str, object], direction: str) -> bool:
    if str(row.get("status") or "").lower() in {"failed", "dry_run_planned"}:
        return False
    return int_value(row.get(f"{direction}_tested_combinations")) == 0


def zero_tested_reason_lines(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["- None."]
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("zero_tested_reason") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return [f"- `{reason}`: `{count}`" for reason, count in sorted(counts.items())]


def zero_tested_table_lines(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["- None."]
    lines = [
        "| Branch | Direction | Preferred rows | Gross positive | Shortlist rows | Primary | Secondary | Combinations | TP/SL tested | Reason |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row.get('branch_id')}` | `{row.get('direction')}` | "
            f"`{row.get('preferred_feature_backtest_summary_rows')}` | "
            f"`{row.get('gross_positive_rows')}` | "
            f"`{row.get('rows_after_preferred_shortlist_source_criteria')}` | "
            f"`{row.get('primary_family_candidates')}` | "
            f"`{row.get('secondary_family_candidates')}` | "
            f"`{row.get('combinations_built')}` | "
            f"`{row.get('tp_sl_tested_rows')}` | "
            f"`{row.get('zero_tested_reason')}` |"
        )
    return lines


def write_zero_tested_report(path: Path, *, run_id: str, rows: list[dict[str, object]]) -> None:
    lines = [
        "# Zero-Tested Branch Diagnostics",
        "",
        "## Research-only warning",
        "",
        "- Retrospective diagnostic over existing matrix outputs only.",
        "- No backtests are rerun and no child scripts are called.",
        "- Not operational guidance, not broker execution, and not deployment-ready.",
        "",
        "## Configuration",
        "",
        f"- Matrix run ID: `{run_id}`",
        f"- Diagnostic rows: `{len(rows)}`",
        "",
        "## Summary by zero_tested_reason",
        "",
        *zero_tested_reason_lines(rows),
        "",
        "## Direction diagnostics",
        "",
        *zero_tested_table_lines(rows),
        "",
        "## Methodology guardrails",
        "",
        "- Fixed TP/SL and horizon are read from the existing branch row.",
        "- No TP/SL optimization.",
        "- No new features.",
        "- No new combinations searched.",
        "- XAUUSD remains separate from the FX group.",
        "",
        "## Interpretation notes",
        "",
        "- `no_preferred_backtest_rows` means the preferred-feature backtest summary was empty before cost comparison.",
        "- `no_preferred_shortlist_rows` means rows did not pass the preferred shortlist/source criteria used by the combination script.",
        "- `empty_combination_detail_csv` means the path diagnostic had no combination rows to evaluate.",
        "- `missing_child_output` means one or more expected child CSV files could not be found.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe(row.get(field)) for field in fieldnames})


def branch_line(row: dict[str, object]) -> str:
    return (
        f"| `{row.get('branch_id', '')}` | `{row.get('status', '')}` | "
        f"`{row.get('branch_decision', '')}` | `{row.get('long_tested_combinations', '')}` | "
        f"`{row.get('short_tested_combinations', '')}` | `{row.get('best_long_mean_R', '')}` | "
        f"`{row.get('best_short_mean_R', '')}` |"
    )


def rows_matching(rows: list[dict[str, object]], decision: str) -> list[str]:
    selected = [row for row in rows if row.get("branch_decision") == decision]
    if not selected:
        return ["- None."]
    return [f"- `{row.get('branch_id')}`" for row in selected]


def skipped_lines(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["- None."]
    return [f"- `{row.get('branch_id')}`: {row.get('reason')}" for row in rows]


def failed_or_skipped_lines(matrix_rows: list[dict[str, object]], skipped_rows: list[dict[str, object]]) -> list[str]:
    lines = [
        f"- `{row.get('branch_id')}`: {row.get('notes')}"
        for row in matrix_rows
        if str(row.get("status") or "").lower() == "failed"
    ]
    lines.extend(skipped_lines(skipped_rows) if skipped_rows else [])
    return lines or ["- None."]


def write_report(
    path: Path,
    *,
    run_id: str,
    args: argparse.Namespace,
    branches: list[Branch],
    matrix_rows: list[dict[str, object]],
    skipped_rows: list[dict[str, object]],
) -> None:
    groups = sorted({branch.group_name for branch in branches})
    horizons = sorted({branch.horizon for branch in branches})
    profiles = sorted({branch.cost_profile for branch in branches})
    lines = [
        "# Preferred Horizon/Cost Diagnostics Matrix",
        "",
        "## Research-only warning",
        "",
        "- Offline orchestration over existing research scripts only.",
        "- Not operational guidance, not broker execution, and not deployment-ready.",
        "",
        "## Configuration",
        "",
        f"- Run ID: `{run_id}`",
        f"- Timeframe: `{args.timeframe}`",
        f"- Return mode: `{args.return_mode}`",
        f"- Target family: `{args.target_family}`",
        f"- TP ATR multiple: `{args.tp_atr}`",
        f"- SL ATR multiple: `{args.sl_atr}`",
        f"- ATR column: `{args.atr_column}`",
        f"- Same-bar policy: `{args.same_bar_policy}`",
        f"- Dry run: `{bool(args.dry_run)}`",
        "",
        "## Matrix dimensions",
        "",
        f"- Groups: `{', '.join(groups)}`",
        f"- Horizons: `{', '.join(str(item) for item in horizons)}`",
        f"- Cost profiles: `{', '.join(profiles)}`",
        f"- Total branches: `{len(branches)}`",
        "",
        "## Cost config mapping",
        "",
    ]
    for profile, path_value in cost_config_mapping(args).items():
        if profile in profiles:
            lines.append(f"- {profile}: `{path_value}`")
    lines.extend(
        [
            "",
            "## Branch results table",
            "",
            "| Branch | Status | Decision | Long tested | Short tested | Best long mean_R | Best short mean_R |",
            "|---|---:|---:|---:|---:|---:|---:|",
            *[branch_line(row) for row in matrix_rows],
            "",
            "## Branches with any CANDIDATA_A_TEST_SUCCESSIVI",
            "",
            *rows_matching(matrix_rows, DECISION_CANDIDATES),
            "",
            "## Branches with any DA_APPROFONDIRE",
            "",
            *rows_matching(matrix_rows, DECISION_REVIEW),
            "",
            "## Branches with zero tested combinations",
            "",
            *rows_matching(matrix_rows, DECISION_NO_TESTED),
            "",
            "## Branches fully closed / CLOSED_NO_SURVIVOR",
            "",
            *rows_matching(matrix_rows, DECISION_CLOSED),
            "",
            "## Failed or skipped branches",
            "",
            *failed_or_skipped_lines(matrix_rows, skipped_rows),
            "",
            "## Methodology guardrails",
            "",
            f"- Fixed TP={args.tp_atr:g}ATR, SL={args.sl_atr:g}ATR, horizon from the branch matrix.",
            "- No TP/SL optimization.",
            "- No new features.",
            "- No new combinations searched beyond the controlled preferred-feature flow.",
            "- XAUUSD is handled separately from the FX group.",
            "",
            "## Interpretation notes",
            "",
            "- `CLOSED_NO_SURVIVOR` means no review or candidate classifications appeared in the fixed TP/SL path rows.",
            "- `NO_TESTED_COMBINATIONS` means the branch completed but no TP/SL path rows were tested.",
            "- `NEEDS_REVIEW` means at least one row deserves additional offline review, but no candidate classification appeared.",
            "- `CANDIDATES_FOUND` means at least one row passed the strict candidate label in the child diagnostics.",
            "- Cost sensitivity is descriptive and depends on the configured local cost files.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def manifest_branch(branch: Branch, commands: list[ChildCommand], status: str, decision: str = "") -> dict[str, object]:
    return {
        "branch_id": branch.branch_id,
        "group_name": branch.group_name,
        "symbols": list(branch.symbols),
        "timeframe": branch.timeframe,
        "horizon": branch.horizon,
        "cost_profile": branch.cost_profile,
        "cost_config": str(branch.cost_config),
        "target_family": branch.target_family,
        "target_long": branch.target_long,
        "target_short": branch.target_short,
        "status": status,
        "branch_decision": decision,
        "child_run_ids": {
            "preferred_feature_backtest_gross": branch.gross_run_id,
            "preferred_feature_backtest_net": branch.net_run_id,
            "combination": branch.combination_run_id,
            "tp_sl_path": branch.tp_sl_run_id,
            "branch_outcome": branch.branch_outcome_run_id,
        },
        "paths": {
            "cost_mode_comparison_long": str(preferred_cost_comparison_path(branch, "long")),
            "cost_mode_comparison_short": str(preferred_cost_comparison_path(branch, "short")),
            "combination_detail_long": str(combination_detail_path(branch, "long")),
            "combination_detail_short": str(combination_detail_path(branch, "short")),
            "tp_sl_summary_long": str(tp_sl_summary_path(branch, "long")),
            "tp_sl_summary_short": str(tp_sl_summary_path(branch, "short")),
            "branch_outcome_report": str(branch_outcome_report_path(branch)),
        },
        "commands": [
            {
                "step": command.step,
                "command": list(command.command),
                "log_path": str(command.log_path or ""),
            }
            for command in commands
        ],
    }


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def infer_existing_run_report_args(args: argparse.Namespace, rows: list[dict[str, object]]) -> argparse.Namespace:
    inferred = argparse.Namespace(**vars(args))
    if rows:
        first = rows[0]
        inferred.timeframe = str(first.get("timeframe") or args.timeframe)
        inferred.tp_atr = float(first.get("tp_atr") or args.tp_atr)
        inferred.sl_atr = float(first.get("sl_atr") or args.sl_atr)
        inferred.target_family = str(
            first.get("target_family")
            or target_family_for_multipliers(inferred.tp_atr, inferred.sl_atr)
            or args.target_family
        )
        inferred.atr_column = str(first.get("atr_column") or args.atr_column)
        inferred.same_bar_policy = str(first.get("same_bar_policy") or args.same_bar_policy)
        inferred.return_mode = str(first.get("return_mode") or args.return_mode)
        inferred.horizons = sorted({int(row.get("horizon") or 0) for row in rows if str(row.get("horizon") or "").strip()})
        inferred.groups = sorted({str(row.get("group_name") or "") for row in rows if str(row.get("group_name") or "").strip()})
        inferred.cost_profiles = sorted(
            {str(row.get("cost_profile") or "") for row in rows if str(row.get("cost_profile") or "").strip()}
        )
        for profile in ("p50", "p75", "p90"):
            profile_paths = [
                Path(str(row.get("cost_config") or ""))
                for row in rows
                if str(row.get("cost_profile") or "") == profile and str(row.get("cost_config") or "").strip()
            ]
            if profile_paths:
                setattr(inferred, f"cost_config_{profile}", profile_paths[0])
    inferred.dry_run = False
    return inferred


def summarize_existing_run(args: argparse.Namespace) -> dict[str, Path]:
    run_id = str(args.summarize_existing_run_id)
    output_root = Path(args.output_root)
    outputs = output_paths(output_root, run_id)
    summary_path = outputs["matrix_summary"]
    report_path = outputs["matrix_report"]
    skipped_path = outputs["skipped_branches"]
    if not summary_path.exists():
        raise FileNotFoundError(f"Existing matrix summary not found: {summary_path}")

    matrix_rows: list[dict[str, object]] = [dict(row) for row in read_csv_rows(summary_path)]
    if not skipped_path.exists():
        write_csv(skipped_path, [], SKIPPED_FIELDNAMES)
    skipped_rows: list[dict[str, object]] = [dict(row) for row in read_csv_rows(skipped_path)]

    for row in matrix_rows:
        decision = branch_decision_from_metrics(row)
        row["branch_decision"] = decision
        if decision == DECISION_NO_TESTED:
            row["notes"] = existing_zero_tested_notes(row)

    branches = [branch_from_matrix_row(row, run_id) for row in matrix_rows]
    report_args = infer_existing_run_report_args(args, matrix_rows)
    write_csv(summary_path, matrix_rows, MATRIX_FIELDNAMES)
    write_report(
        report_path,
        run_id=run_id,
        args=report_args,
        branches=branches,
        matrix_rows=matrix_rows,
        skipped_rows=skipped_rows,
    )
    print(f"Summarized existing run without rerunning child scripts: {run_id}", flush=True)
    return outputs


def diagnose_zero_tested_run(args: argparse.Namespace) -> dict[str, Path]:
    run_id = str(args.diagnose_zero_tested_run_id)
    output_root = Path(args.output_root)
    matrix_summary = output_paths(output_root, run_id)["matrix_summary"]
    outputs = zero_tested_output_paths(output_root, run_id)
    if not matrix_summary.exists():
        raise FileNotFoundError(f"Existing matrix summary not found: {matrix_summary}")

    matrix_rows: list[dict[str, object]] = [dict(row) for row in read_csv_rows(matrix_summary)]
    diagnostic_rows: list[dict[str, object]] = []
    for row in matrix_rows:
        for direction in DIRECTIONS:
            if should_diagnose_zero_tested_direction(row, direction):
                diagnostic_rows.append(zero_tested_diagnostic_row(row, direction))

    write_csv(outputs["zero_tested_diagnostics"], diagnostic_rows, ZERO_TESTED_FIELDNAMES)
    write_zero_tested_report(outputs["zero_tested_report"], run_id=run_id, rows=diagnostic_rows)
    print(f"Diagnosed zero-tested branches without rerunning child scripts: {run_id}", flush=True)
    return outputs


def validate_or_skip_branches(
    branches: list[Branch],
    *,
    skip_missing_cost_configs: bool,
) -> tuple[list[Branch], list[dict[str, object]]]:
    valid: list[Branch] = []
    skipped: list[dict[str, object]] = []
    missing = [branch for branch in branches if not branch.cost_config.exists()]
    if missing and not skip_missing_cost_configs:
        missing_text = "\n- ".join(f"{branch.branch_id}: {branch.cost_config}" for branch in missing)
        raise FileNotFoundError("Missing required cost config files:\n- " + missing_text)
    for branch in branches:
        if not branch.cost_config.exists():
            skipped.append(skipped_branch_row(branch, reason="missing_cost_config"))
            continue
        valid.append(branch)
    return valid, skipped


def execute_branch(
    branch: Branch,
    args: argparse.Namespace,
    output_dir: Path,
    runner: CommandRunner,
) -> tuple[dict[str, object], list[dict[str, object]], list[ChildCommand]]:
    commands = child_commands(branch, args, output_dir)
    skipped: list[dict[str, object]] = []
    for command in commands:
        print(
            f"[{branch.branch_id}] step {command.step}",
            flush=True,
        )
        exit_code = runner(command)
        if exit_code != 0:
            skipped.append(
                skipped_branch_row(
                    branch,
                    reason=f"child_command_failed:{command.step}",
                    command=command_text(command.command),
                    exit_code=exit_code,
                    log_path=command.log_path or "",
                )
            )
            row = matrix_row_for_branch(
                branch,
                status="failed",
                notes=f"Child command failed at {command.step}.",
            )
            if not bool(args.continue_on_error):
                raise RuntimeError(
                    f"Child command failed for {branch.branch_id} at {command.step}; "
                    f"exit_code={exit_code}; log={command.log_path}"
                )
            return row, skipped, commands

    row = matrix_row_for_branch(
        branch,
        status="completed",
        notes="Completed child diagnostics.",
        include_metrics=True,
    )
    outcome = branch_outcome_command(branch, args, output_dir, str(row["branch_decision"]))
    commands = [*commands, outcome]
    print(f"[{branch.branch_id}] step {outcome.step}", flush=True)
    exit_code = runner(outcome)
    if exit_code != 0:
        skipped.append(
            skipped_branch_row(
                branch,
                reason=f"child_command_failed:{outcome.step}",
                command=command_text(outcome.command),
                exit_code=exit_code,
                log_path=outcome.log_path or "",
            )
        )
        row["status"] = "failed"
        row["notes"] = f"Child command failed at {outcome.step}."
        if not bool(args.continue_on_error):
            raise RuntimeError(
                f"Child command failed for {branch.branch_id} at {outcome.step}; "
                f"exit_code={exit_code}; log={outcome.log_path}"
            )
    return row, skipped, commands


def run_preferred_horizon_cost_diagnostics(
    args: argparse.Namespace,
    *,
    runner: CommandRunner = run_child_command,
) -> dict[str, Path]:
    if not getattr(args, "target_family", None):
        args.target_family = PREFERRED_2ATR_1ATR_HIT_FIRST
    family = target_family_spec(str(args.target_family))
    args.tp_atr = family.tp_atr
    args.sl_atr = family.sl_atr

    if getattr(args, "diagnose_zero_tested_run_id", None):
        return diagnose_zero_tested_run(args)
    if getattr(args, "summarize_existing_run_id", None):
        return summarize_existing_run(args)

    run_id = str(args.run_id or current_run_id())
    output_root = Path(args.output_root)
    output_dir = output_dir_for(output_root, run_id)
    outputs = output_paths(output_root, run_id)
    ensure_outputs_writable(outputs.values(), bool(args.overwrite))

    all_branches = build_branch_matrix(args, run_id)
    branches, skipped_rows = validate_or_skip_branches(
        all_branches,
        skip_missing_cost_configs=bool(args.skip_missing_cost_configs),
    )
    matrix_rows: list[dict[str, object]] = []
    manifest_branches: list[dict[str, object]] = []

    total = len(branches)
    for index, branch in enumerate(branches, start=1):
        print(
            f"Branch {index}/{total}: group={branch.group_name} h={branch.horizon} cost={branch.cost_profile}",
            flush=True,
        )
        commands = child_commands(branch, args, output_dir)
        if bool(args.dry_run):
            matrix_rows.append(
                matrix_row_for_branch(
                    branch,
                    status="dry_run_planned",
                    notes="Dry run only; child scripts were not executed.",
                    decision="PLANNED",
                )
            )
            manifest_branches.append(manifest_branch(branch, commands, "dry_run_planned", "PLANNED"))
            continue

        row, branch_skipped, commands_with_outcome = execute_branch(branch, args, output_dir, runner)
        matrix_rows.append(row)
        skipped_rows.extend(branch_skipped)
        manifest_branches.append(
            manifest_branch(
                branch,
                commands_with_outcome,
                str(row.get("status") or ""),
                str(row.get("branch_decision") or ""),
            )
        )

    manifest = {
        "run_id": run_id,
        "dry_run": bool(args.dry_run),
        "output_root": str(output_dir),
        "branches_total": len(all_branches),
        "branches_planned_or_run": len(branches),
        "branches_skipped": len(skipped_rows),
        "branches": manifest_branches,
        "skipped_branches": skipped_rows,
    }

    write_csv(outputs["matrix_summary"], matrix_rows, MATRIX_FIELDNAMES)
    write_csv(outputs["skipped_branches"], skipped_rows, SKIPPED_FIELDNAMES)
    write_manifest(outputs["branch_manifest"], manifest)
    write_report(
        outputs["matrix_report"],
        run_id=run_id,
        args=args,
        branches=branches,
        matrix_rows=matrix_rows,
        skipped_rows=skipped_rows,
    )
    return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run or plan research-only preferred horizon/cost diagnostics."
    )
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--horizons", nargs="+", type=int, default=[5, 10, 20])
    parser.add_argument("--groups", nargs="+", choices=tuple(GROUP_SYMBOLS), default=["fx", "xauusd"])
    parser.add_argument("--cost-profiles", nargs="+", choices=("p50", "p75", "p90"), default=["p50", "p75", "p90"])
    parser.add_argument("--cost-config-p50", type=Path, default=DEFAULT_COST_CONFIGS["p50"])
    parser.add_argument("--cost-config-p75", type=Path, default=DEFAULT_COST_CONFIGS["p75"])
    parser.add_argument("--cost-config-p90", type=Path, default=DEFAULT_COST_CONFIGS["p90"])
    parser.add_argument("--skip-missing-cost-configs", action="store_true")
    parser.add_argument(
        "--target-family",
        choices=supported_target_family_names(),
        default=PREFERRED_2ATR_1ATR_HIT_FIRST,
    )
    parser.add_argument("--tp-atr", type=float, default=2.0)
    parser.add_argument("--sl-atr", type=float, default=1.0)
    parser.add_argument("--atr-column", default="atr_20")
    parser.add_argument("--same-bar-policy", choices=("stop_first", "take_first"), default="stop_first")
    parser.add_argument("--return-mode", choices=("net",), default="net")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summarize-existing-run-id")
    parser.add_argument("--diagnose-zero-tested-run-id")
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=f"Default: {DEFAULT_OUTPUT_ROOT}")
    parser.add_argument("--python-executable", default="python")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    try:
        outputs = run_preferred_horizon_cost_diagnostics(parse_args())
    except (FileExistsError, FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"Preferred horizon/cost diagnostics failed: {exc}")
        return 1
    print("Preferred horizon/cost diagnostics complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
