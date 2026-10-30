"""Build a final research-only decision report from validated outputs.

The report summarizes existing validation, random-baseline, optional
scorecard, and optional walk-forward outputs. It does not generate signals,
search for new strategies, connect to MetaTrader5, or perform any live trading
action.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Iterable

try:
    from condition_utils import precheck_combination_skip_reason
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_research_decision_report
    from scripts.condition_utils import precheck_combination_skip_reason

try:
    from research_costs import validate_cost_args
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_research_decision_report
    from scripts.research_costs import validate_cost_args

try:
    from research_metrics import csv_safe_value, normalize_direction, safe_float
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_research_decision_report
    from scripts.research_metrics import csv_safe_value, normalize_direction, safe_float


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_VALIDATION_DIR = BASE_DIR / "reports" / "validation" / "by_year"
DEFAULT_RANDOM_BASELINE_DIR = BASE_DIR / "reports" / "random_baseline"
DEFAULT_SCORECARD_DIR = BASE_DIR / "reports" / "final_feature_scorecard"
DEFAULT_WALK_FORWARD_DIR = BASE_DIR / "reports" / "walk_forward"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports" / "research_decision"

REPORT_OUTPUT = "research_decision_report.md"
SUMMARY_OUTPUT = "research_decision_summary.csv"
WARNINGS_OUTPUT = "research_decision_warnings.csv"

DECISION_REJECT = "SCARTARE"
DECISION_REVIEW = "DA_APPROFONDIRE"
DECISION_CANDIDATE = "CANDIDATA_A_TEST_SUCCESSIVI"

MIN_TRADES = 100
MIN_AVG_TRADES_PER_YEAR = 100.0
MIN_POSITIVE_YEAR_RATIO = 0.50
MIN_POSITIVE_SYMBOL_RATIO = 0.50
MAX_BEST_MONTH_CONTRIBUTION = 60.0
MAX_TOP_TRADES_CONTRIBUTION = 70.0
MIN_MONTHLY_POSITIVE_RATIO = 0.45
MIN_QUARTERLY_POSITIVE_RATIO = 0.50
SEVERE_DRAWDOWN_WORSENING = -50.0
SEVERE_WORST_YEAR_PF = -25.0


SUMMARY_FIELDNAMES = [
    "candidate_scope",
    "symbol",
    "combination_key",
    "decision",
    "decision_score",
    "primary_reason",
    "next_step_note",
    "direction",
    "cost_mode",
    "return_mode",
    "validation_classification",
    "random_baseline_classification",
    "trades_count",
    "avg_trades_per_year",
    "min_trades_in_any_year",
    "positive_year_ratio",
    "positive_symbol_ratio",
    "avg_profit_factor_improvement_pct",
    "avg_max_drawdown_improvement_pct",
    "worst_year_profit_factor_improvement_pct",
    "worst_year_drawdown_improvement_pct",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "best_month_contribution_pct",
    "top_5_percent_trades_contribution_pct",
    "cumulative_return_percentile",
    "profit_factor_percentile",
    "mean_return_percentile",
    "win_rate_percentile",
    "max_drawdown_percentile",
    "cumulative_return_empirical_p_value",
    "mean_return_empirical_p_value",
    "source_files_used",
]

WARNING_FIELDNAMES = [
    "warning_type",
    "candidate_scope",
    "symbol",
    "combination_key",
    "message",
    "source_file",
]


def to_float(value: object) -> float | None:
    return safe_float(value)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return [dict(row) for row in reader]


def output_paths(output_dir: Path, run_id: str, direction: str) -> dict[str, Path]:
    base = output_dir / run_id / direction
    return {
        "report": base / REPORT_OUTPUT,
        "summary": base / SUMMARY_OUTPUT,
        "warnings": base / WARNINGS_OUTPUT,
    }


def ensure_can_write(paths: Iterable[Path], overwrite: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Research decision output already exists. Pass --overwrite to regenerate: "
            + ", ".join(str(path) for path in existing)
        )


def warning_record(
    warning_type: str,
    message: str,
    *,
    candidate_scope: str = "",
    symbol: str = "",
    combination_key: str = "",
    source_file: Path | str = "",
) -> dict[str, object]:
    return {
        "warning_type": warning_type,
        "candidate_scope": candidate_scope,
        "symbol": symbol,
        "combination_key": combination_key,
        "message": message,
        "source_file": str(source_file),
    }


def add_file_warning_if_missing(
    warnings: list[dict[str, object]],
    path: Path,
    warning_type: str,
    message: str,
) -> bool:
    if path.exists():
        return False
    warnings.append(warning_record(warning_type, message, source_file=path))
    return True


def candidate_file(validation_dir: Path, run_id: str, direction: str, scope: str) -> Path:
    filename = "final_research_candidates.csv" if scope == "cross_pair" else "pair_specific_candidates.csv"
    return validation_dir / run_id / direction / filename


def skipped_validation_file(validation_dir: Path, run_id: str, direction: str) -> Path:
    return validation_dir / run_id / direction / "skipped_hypotheses.csv"


def random_detail_file(random_baseline_dir: Path, run_id: str, direction: str) -> Path:
    return random_baseline_dir / run_id / direction / "random_baseline_detail.csv"


def random_summary_file(random_baseline_dir: Path, run_id: str, direction: str) -> Path:
    return random_baseline_dir / run_id / direction / "random_baseline_summary.csv"


def skipped_random_file(random_baseline_dir: Path, run_id: str, direction: str) -> Path:
    return random_baseline_dir / run_id / direction / "skipped_random_baseline_candidates.csv"


def optional_input_paths(args: argparse.Namespace, direction: str) -> list[Path]:
    return [
        args.scorecard_dir / args.run_id / direction / "final_feature_scorecard.csv",
        args.scorecard_dir / args.run_id / direction / "pair_specific_feature_scorecard.csv",
        args.walk_forward_dir / args.run_id / direction / "walk_forward_candidates.csv",
        args.walk_forward_dir / args.run_id / direction / "pair_specific_walk_forward_candidates.csv",
    ]


def row_matches_modes(row: dict[str, str], direction: str, cost_mode: str, return_mode: str) -> bool:
    row_direction = str(row.get("direction") or direction).strip().lower()
    row_cost_mode = str(row.get("cost_mode") or cost_mode).strip().lower()
    row_return_mode = str(row.get("return_mode") or return_mode).strip().lower()
    return row_direction == direction and row_cost_mode == cost_mode and row_return_mode == return_mode


def load_candidates_for_scope(
    path: Path,
    scope: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
    warnings: list[dict[str, object]],
) -> list[dict[str, object]]:
    if add_file_warning_if_missing(
        warnings,
        path,
        "missing_candidate_file",
        f"Candidate file for {scope} is missing.",
    ):
        return []

    rows = read_csv_rows(path)
    if not rows:
        warnings.append(
            warning_record(
                "empty_candidate_file",
                f"Candidate file for {scope} is empty.",
                candidate_scope=scope,
                source_file=path,
            )
        )
        return []

    candidates: list[dict[str, object]] = []
    for row in rows:
        combination_key = str(row.get("combination_key") or "").strip()
        if not combination_key:
            warnings.append(
                warning_record(
                    "empty_combination_key",
                    "Skipped row with empty combination_key.",
                    candidate_scope=scope,
                    source_file=path,
                )
            )
            continue
        if not row_matches_modes(row, direction, cost_mode, return_mode):
            warnings.append(
                warning_record(
                    "mode_mismatch_skipped",
                    "Candidate row does not match requested direction/cost_mode/return_mode.",
                    candidate_scope=scope,
                    symbol=str(row.get("symbol") or ""),
                    combination_key=combination_key,
                    source_file=path,
                )
            )
            continue
        candidate = dict(row)
        candidate["candidate_scope"] = scope
        candidate["source_file"] = str(path)
        candidates.append(candidate)
    return candidates


def random_key(scope: str, combination_key: str, symbol: str) -> tuple[str, str, str]:
    return scope, combination_key, symbol if scope == "pair_specific" else ""


def normalize_random_scope(row: dict[str, str]) -> str:
    return str(row.get("candidate_scope") or row.get("candidate_type") or "").strip() or "cross_pair"


def load_random_detail(
    path: Path,
    direction: str,
    cost_mode: str,
    return_mode: str,
    warnings: list[dict[str, object]],
) -> dict[tuple[str, str, str], dict[str, object]]:
    if add_file_warning_if_missing(
        warnings,
        path,
        "missing_random_baseline_detail",
        "Random baseline detail file is missing; candidates will be treated as mixed evidence.",
    ):
        return {}
    rows = read_csv_rows(path)
    if not rows:
        warnings.append(warning_record("empty_random_baseline_detail", "Random baseline detail file is empty.", source_file=path))
        return {}

    detail: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in rows:
        if not row_matches_modes(row, direction, cost_mode, return_mode):
            continue
        scope = normalize_random_scope(row)
        combination_key = str(row.get("combination_key") or "").strip()
        symbol = str(row.get("symbol") or "").strip().upper()
        if combination_key:
            detail[random_key(scope, combination_key, symbol)] = dict(row)
    return detail


def load_skipped_rows(
    path: Path,
    warning_type: str,
    warnings: list[dict[str, object]],
) -> None:
    if not path.exists():
        warnings.append(warning_record(f"missing_{warning_type}", f"Skipped file is missing: {path}", source_file=path))
        return
    for row in read_csv_rows(path):
        warnings.append(
            warning_record(
                warning_type,
                str(row.get("skip_reason") or row.get("message") or "Skipped candidate/condition."),
                candidate_scope=str(row.get("candidate_type") or row.get("candidate_scope") or ""),
                symbol=str(row.get("symbol") or ""),
                combination_key=str(row.get("combination_key") or ""),
                source_file=row.get("source_file") or path,
            )
        )


def validation_classification(candidate: dict[str, object]) -> str:
    return str(candidate.get("final_classification") or candidate.get("pair_specific_classification") or "").strip()


def random_classification(random_row: dict[str, object] | None) -> str:
    if not random_row:
        return "missing"
    return str(random_row.get("random_baseline_classification") or "").strip() or "missing"


def candidate_symbol(candidate: dict[str, object]) -> str:
    return str(candidate.get("symbol") or "").strip().upper()


def selected_or_default(candidate: dict[str, object], random_row: dict[str, object] | None, field: str) -> object:
    if random_row and str(random_row.get(field) or "").strip() != "":
        return random_row.get(field)
    return candidate.get(field)


def severe_concentration(candidate: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    best_month = to_float(candidate.get("best_month_contribution_pct"))
    top_trades = to_float(candidate.get("top_5_percent_trades_contribution_pct"))
    monthly_ratio = to_float(candidate.get("monthly_positive_ratio"))
    quarterly_ratio = to_float(candidate.get("quarterly_positive_ratio"))
    if best_month is not None and best_month > MAX_BEST_MONTH_CONTRIBUTION:
        reasons.append("performance_too_concentrated_best_month")
    if top_trades is not None and top_trades > MAX_TOP_TRADES_CONTRIBUTION:
        reasons.append("performance_too_concentrated_top_trades")
    if monthly_ratio is not None and monthly_ratio < MIN_MONTHLY_POSITIVE_RATIO:
        reasons.append("low_monthly_positive_ratio")
    if quarterly_ratio is not None and quarterly_ratio < MIN_QUARTERLY_POSITIVE_RATIO:
        reasons.append("low_quarterly_positive_ratio")
    return reasons


def disqualifying_reasons(
    candidate: dict[str, object],
    random_row: dict[str, object] | None,
    cost_mode: str,
    return_mode: str,
) -> list[str]:
    scope = str(candidate.get("candidate_scope") or "")
    reasons: list[str] = []
    classification = validation_classification(candidate)
    random_status = random_classification(random_row)
    combination_key = str(candidate.get("combination_key") or "")
    precheck_skip = precheck_combination_skip_reason(combination_key)
    if precheck_skip:
        reasons.append(precheck_skip)
    if classification in {"reject", "reject_pair_specific"}:
        reasons.append("validation_reject")
    if random_status == "not_better_than_random":
        reasons.append("not_better_than_random")
    if random_status == "low_sample":
        reasons.append("random_baseline_low_sample")
    if return_mode == "net" and cost_mode == "none":
        reasons.append("net_without_estimated_costs")

    trades_count = to_float(selected_or_default(candidate, random_row, "trades_count"))
    avg_trades = to_float(candidate.get("avg_trades_per_year"))
    min_trades = to_float(candidate.get("min_trades_in_any_year"))
    if trades_count is not None and trades_count < MIN_TRADES:
        reasons.append("sample_too_low")
    if avg_trades is not None and avg_trades < MIN_AVG_TRADES_PER_YEAR:
        reasons.append("avg_trades_per_year_too_low")
    if min_trades is not None and min_trades < MIN_TRADES:
        reasons.append("min_trades_in_any_year_too_low")

    positive_year_ratio = to_float(candidate.get("positive_year_ratio"))
    if positive_year_ratio is not None and positive_year_ratio < MIN_POSITIVE_YEAR_RATIO:
        reasons.append("positive_year_ratio_low")
    positive_symbol_ratio = to_float(candidate.get("positive_symbol_ratio"))
    if scope == "cross_pair" and positive_symbol_ratio is not None and positive_symbol_ratio < MIN_POSITIVE_SYMBOL_RATIO:
        reasons.append("positive_symbol_ratio_low")

    avg_pf = to_float(candidate.get("avg_profit_factor_improvement_pct"))
    if avg_pf is not None and avg_pf < 0:
        reasons.append("profit_factor_improvement_negative")
    avg_drawdown = to_float(candidate.get("avg_max_drawdown_improvement_pct"))
    if avg_drawdown is not None and avg_drawdown < 0:
        reasons.append("drawdown_worsened")
    worst_pf = to_float(candidate.get("worst_year_profit_factor_improvement_pct"))
    if worst_pf is not None and worst_pf < SEVERE_WORST_YEAR_PF:
        reasons.append("worst_year_profit_factor_very_negative")
    worst_drawdown = to_float(candidate.get("worst_year_drawdown_improvement_pct"))
    if worst_drawdown is not None and worst_drawdown < SEVERE_DRAWDOWN_WORSENING:
        reasons.append("worst_year_drawdown_very_negative")
    reasons.extend(severe_concentration(candidate))
    return reasons


def mixed_evidence_reasons(candidate: dict[str, object], random_row: dict[str, object] | None) -> list[str]:
    reasons: list[str] = []
    classification = validation_classification(candidate)
    random_status = random_classification(random_row)
    scope = str(candidate.get("candidate_scope") or "")
    if classification in {"watchlist", "watchlist_pair_specific"}:
        reasons.append("validation_watchlist")
    if random_status in {"missing", "weak_vs_random"}:
        reasons.append("random_baseline_weak_or_missing")
    if scope == "pair_specific":
        reasons.append("pair_specific_not_generalizable")
    avg_pf = to_float(candidate.get("avg_profit_factor_improvement_pct"))
    avg_drawdown = to_float(candidate.get("avg_max_drawdown_improvement_pct"))
    if avg_pf is not None and avg_drawdown is not None and (avg_pf <= 0 or avg_drawdown <= 0):
        reasons.append("mixed_profit_drawdown_evidence")
    if severe_concentration(candidate):
        reasons.append("concentration_needs_review")
    return reasons


def decision_score(candidate: dict[str, object], random_row: dict[str, object] | None, decision: str) -> int:
    score = 45.0
    classification = validation_classification(candidate)
    random_status = random_classification(random_row)
    if classification in {"select", "select_pair_specific"}:
        score += 25
    elif classification in {"watchlist", "watchlist_pair_specific"}:
        score += 8
    elif classification in {"reject", "reject_pair_specific"}:
        score -= 45
    score += {
        "robust_vs_random": 25,
        "interesting_vs_random": 15,
        "weak_vs_random": 2,
        "missing": -4,
        "not_better_than_random": -35,
        "low_sample": -25,
    }.get(random_status, 0)
    for field in ("positive_year_ratio", "positive_symbol_ratio", "monthly_positive_ratio", "quarterly_positive_ratio"):
        value = to_float(candidate.get(field))
        if value is not None:
            score += max(min(value, 1.0), 0.0) * 4
    if to_float(candidate.get("avg_profit_factor_improvement_pct")) is not None:
        score += max(min(float(to_float(candidate.get("avg_profit_factor_improvement_pct")) or 0) / 10, 8), -12)
    if to_float(candidate.get("avg_max_drawdown_improvement_pct")) is not None:
        score += max(min(float(to_float(candidate.get("avg_max_drawdown_improvement_pct")) or 0) / 10, 8), -12)
    if decision == DECISION_REJECT:
        score = min(score, 35)
    elif decision == DECISION_REVIEW:
        score = min(max(score, 36), 74)
    else:
        score = max(score, 75)
    return int(round(max(min(score, 100), 0)))


def decide_candidate(
    candidate: dict[str, object],
    random_row: dict[str, object] | None,
    cost_mode: str,
    return_mode: str,
) -> tuple[str, int, str, str]:
    disqualifiers = disqualifying_reasons(candidate, random_row, cost_mode, return_mode)
    mixed = mixed_evidence_reasons(candidate, random_row)
    classification = validation_classification(candidate)
    random_status = random_classification(random_row)

    if disqualifiers:
        decision = DECISION_REJECT
        reason = disqualifiers[0]
        next_step = "Do not use for future strategy design unless the rejected evidence is corrected by a new research run."
    elif (
        classification in {"select", "select_pair_specific"}
        and random_status in {"robust_vs_random", "interesting_vs_random"}
        and not mixed
    ):
        decision = DECISION_CANDIDATE
        reason = f"{classification}+{random_status}"
        next_step = "Eligible only for a future rule-based research backtest with explicit costs, risk, exits, and no live execution."
    else:
        decision = DECISION_REVIEW
        reason = mixed[0] if mixed else "evidence_mixed_or_incomplete"
        next_step = "Review evidence manually and rerun validation/random baseline before any future rule-based research backtest."
    return decision, decision_score(candidate, random_row, decision), reason, next_step


def random_lookup_key(candidate: dict[str, object]) -> tuple[str, str, str]:
    scope = str(candidate.get("candidate_scope") or "")
    combination_key = str(candidate.get("combination_key") or "")
    symbol = candidate_symbol(candidate)
    return scope, combination_key, symbol if scope == "pair_specific" else ""


def build_summary_row(
    candidate: dict[str, object],
    random_row: dict[str, object] | None,
    cost_mode: str,
    return_mode: str,
    extra_sources: list[str],
) -> dict[str, object]:
    decision, score, reason, next_step = decide_candidate(candidate, random_row, cost_mode, return_mode)
    scope = str(candidate.get("candidate_scope") or "")
    source_files = [str(candidate.get("source_file") or "")]
    if random_row:
        source_files.append(str(random_row.get("source_file") or ""))
    source_files.extend(extra_sources)
    source_files = sorted({item for item in source_files if item})
    return {
        "candidate_scope": scope,
        "symbol": candidate_symbol(candidate),
        "combination_key": candidate.get("combination_key", ""),
        "decision": decision,
        "decision_score": score,
        "primary_reason": reason,
        "next_step_note": next_step,
        "direction": candidate.get("direction", ""),
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "validation_classification": validation_classification(candidate),
        "random_baseline_classification": random_classification(random_row),
        "trades_count": selected_or_default(candidate, random_row, "trades_count"),
        "avg_trades_per_year": candidate.get("avg_trades_per_year", ""),
        "min_trades_in_any_year": candidate.get("min_trades_in_any_year", ""),
        "positive_year_ratio": candidate.get("positive_year_ratio", ""),
        "positive_symbol_ratio": candidate.get("positive_symbol_ratio", ""),
        "avg_profit_factor_improvement_pct": candidate.get("avg_profit_factor_improvement_pct", ""),
        "avg_max_drawdown_improvement_pct": candidate.get("avg_max_drawdown_improvement_pct", ""),
        "worst_year_profit_factor_improvement_pct": candidate.get("worst_year_profit_factor_improvement_pct", ""),
        "worst_year_drawdown_improvement_pct": candidate.get("worst_year_drawdown_improvement_pct", ""),
        "monthly_positive_ratio": candidate.get("monthly_positive_ratio", ""),
        "quarterly_positive_ratio": candidate.get("quarterly_positive_ratio", ""),
        "best_month_contribution_pct": candidate.get("best_month_contribution_pct", ""),
        "top_5_percent_trades_contribution_pct": candidate.get("top_5_percent_trades_contribution_pct", ""),
        "cumulative_return_percentile": selected_or_default(candidate, random_row, "cumulative_return_percentile"),
        "profit_factor_percentile": selected_or_default(candidate, random_row, "profit_factor_percentile"),
        "mean_return_percentile": selected_or_default(candidate, random_row, "mean_return_percentile"),
        "win_rate_percentile": selected_or_default(candidate, random_row, "win_rate_percentile"),
        "max_drawdown_percentile": selected_or_default(candidate, random_row, "max_drawdown_percentile"),
        "cumulative_return_empirical_p_value": selected_or_default(
            candidate,
            random_row,
            "cumulative_return_empirical_p_value",
        ),
        "mean_return_empirical_p_value": selected_or_default(candidate, random_row, "mean_return_empirical_p_value"),
        "source_files_used": ";".join(source_files),
    }


def sort_summary_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    decision_rank = {
        DECISION_CANDIDATE: 0,
        DECISION_REVIEW: 1,
        DECISION_REJECT: 2,
    }
    return sorted(
        rows,
        key=lambda row: (
            decision_rank.get(str(row.get("decision")), 99),
            -int(float(row.get("decision_score") or 0)),
            str(row.get("candidate_scope") or ""),
            str(row.get("symbol") or ""),
            str(row.get("combination_key") or ""),
        ),
    )


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe_value(row.get(key)) for key in fieldnames})


def markdown_table(rows: list[dict[str, object]], limit: int = 20) -> list[str]:
    if not rows:
        return ["No candidates in this section."]
    lines = [
        "| Decision | Score | Scope | Symbol | Combination | Random | Reason |",
        "|---|---:|---|---|---|---|---|",
    ]
    for row in rows[:limit]:
        combination = str(row.get("combination_key") or "").replace("|", "\\|")
        lines.append(
            "| {decision} | {score} | {scope} | {symbol} | {combination} | {random} | {reason} |".format(
                decision=row.get("decision", ""),
                score=row.get("decision_score", ""),
                scope=row.get("candidate_scope", ""),
                symbol=row.get("symbol", ""),
                combination=combination,
                random=row.get("random_baseline_classification", ""),
                reason=str(row.get("primary_reason") or "").replace("|", "\\|"),
            )
        )
    return lines


def write_report(
    path: Path,
    *,
    run_id: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
    summary_rows: list[dict[str, object]],
    warnings: list[dict[str, object]],
) -> None:
    counts = Counter(str(row.get("decision") or "") for row in summary_rows)
    cross_pair_rows = [row for row in summary_rows if row.get("candidate_scope") == "cross_pair"]
    pair_specific_rows = [row for row in summary_rows if row.get("candidate_scope") == "pair_specific"]
    lines = [
        "# Research Decision Report",
        "",
        "This report is research-only. It summarizes existing validation outputs and does not generate live signals, buy/sell recommendations, complete strategies, or order-execution instructions.",
        "",
        "## Run Context",
        "",
        f"- Run ID: {run_id}",
        f"- Direction: {direction}",
        f"- Cost mode: {cost_mode}",
        f"- Return mode: {return_mode}",
        "- Candidate scopes are evaluated separately: cross-pair and pair-specific rows are not merged.",
        "",
        "## Decision Counts",
        "",
        f"- {DECISION_CANDIDATE}: {counts.get(DECISION_CANDIDATE, 0)}",
        f"- {DECISION_REVIEW}: {counts.get(DECISION_REVIEW, 0)}",
        f"- {DECISION_REJECT}: {counts.get(DECISION_REJECT, 0)}",
        f"- Total candidates reviewed: {len(summary_rows)}",
        "",
        "## Top Candidates",
        "",
        *markdown_table(summary_rows, 20),
        "",
        "## Cross-Pair",
        "",
        *markdown_table(cross_pair_rows, 50),
        "",
        "## Pair-Specific",
        "",
        *markdown_table(pair_specific_rows, 50),
        "",
        "## Skipped And Warnings",
        "",
    ]
    if warnings:
        warning_counts = Counter(str(row.get("warning_type") or "") for row in warnings)
        lines.extend(f"- {name}: {count}" for name, count in sorted(warning_counts.items()))
    else:
        lines.append("- No warnings recorded.")
    lines.extend(
        [
            "",
            "## Next Research Steps",
            "",
            f"- `{DECISION_CANDIDATE}` means only that the candidate may deserve a future rule-based research backtest.",
            "- Review random baseline, yearly validation, concentration, and optional walk-forward evidence before designing any rule.",
            "- Keep long and short, gross and net, and cross-pair and pair-specific candidates separated in follow-up work.",
            "",
            "## Final Guardrails",
            "",
            "- No row in this report is live-ready.",
            "- No row is a buy/sell recommendation.",
            "- No row is a complete strategy.",
            "- Do not use this report for autonomous execution or position management.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_optional_sources(args: argparse.Namespace, direction: str, warnings: list[dict[str, object]]) -> list[str]:
    sources: list[str] = []
    for path in optional_input_paths(args, direction):
        if path.exists():
            sources.append(str(path))
            if not read_csv_rows(path):
                warnings.append(warning_record("empty_optional_input", "Optional input exists but is empty.", source_file=path))
        else:
            warnings.append(warning_record("missing_optional_input", "Optional input is missing.", source_file=path))
    return sources


def build_research_decision_report(args: argparse.Namespace) -> dict[str, Path]:
    direction = normalize_direction(args.direction)
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    if not args.include_cross_pair and not args.include_pair_specific:
        raise ValueError("At least one of --include-cross-pair or --include-pair-specific must be enabled.")

    paths = output_paths(args.output_dir, args.run_id, direction)
    ensure_can_write(paths.values(), args.overwrite)

    warnings: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    if args.include_cross_pair:
        candidates.extend(
            load_candidates_for_scope(
                candidate_file(args.validation_dir, args.run_id, direction, "cross_pair"),
                "cross_pair",
                direction,
                cost_mode,
                return_mode,
                warnings,
            )
        )
    if args.include_pair_specific:
        candidates.extend(
            load_candidates_for_scope(
                candidate_file(args.validation_dir, args.run_id, direction, "pair_specific"),
                "pair_specific",
                direction,
                cost_mode,
                return_mode,
                warnings,
            )
        )

    random_detail_path = random_detail_file(args.random_baseline_dir, args.run_id, direction)
    random_rows = load_random_detail(random_detail_path, direction, cost_mode, return_mode, warnings)
    random_summary_path = random_summary_file(args.random_baseline_dir, args.run_id, direction)
    if add_file_warning_if_missing(
        warnings,
        random_summary_path,
        "missing_random_baseline_summary",
        "Random baseline summary file is missing.",
    ) is False and not read_csv_rows(random_summary_path):
        warnings.append(warning_record("empty_random_baseline_summary", "Random baseline summary file is empty.", source_file=random_summary_path))

    load_skipped_rows(skipped_validation_file(args.validation_dir, args.run_id, direction), "skipped_validation_candidate", warnings)
    load_skipped_rows(skipped_random_file(args.random_baseline_dir, args.run_id, direction), "skipped_random_baseline_candidate", warnings)
    optional_sources = load_optional_sources(args, direction, warnings)

    summary_rows: list[dict[str, object]] = []
    for candidate in candidates:
        key = random_lookup_key(candidate)
        random_row = random_rows.get(key)
        if random_row:
            random_row["source_file"] = str(random_detail_path)
        else:
            warnings.append(
                warning_record(
                    "missing_random_baseline_for_candidate",
                    "Candidate has no matching random baseline row.",
                    candidate_scope=str(candidate.get("candidate_scope") or ""),
                    symbol=candidate_symbol(candidate),
                    combination_key=str(candidate.get("combination_key") or ""),
                    source_file=random_detail_path,
                )
            )
        summary_rows.append(build_summary_row(candidate, random_row, cost_mode, return_mode, optional_sources))

    summary_rows = sort_summary_rows(summary_rows)
    write_csv(paths["summary"], summary_rows, SUMMARY_FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(
        paths["report"],
        run_id=args.run_id,
        direction=direction,
        cost_mode=cost_mode,
        return_mode=return_mode,
        summary_rows=summary_rows,
        warnings=warnings,
    )

    print(f"Research decision report written: {paths['report'].resolve()}")
    print(f"Research decision summary written: {paths['summary'].resolve()}")
    print(f"Research decision warnings written: {paths['warnings'].resolve()}")
    print(f"Candidates reviewed: {len(summary_rows)}")
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a research-only final decision report from validation outputs.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--direction", choices=("long", "short"), default="long")
    parser.add_argument("--validation-dir", type=Path, default=DEFAULT_VALIDATION_DIR)
    parser.add_argument("--random-baseline-dir", type=Path, default=DEFAULT_RANDOM_BASELINE_DIR)
    parser.add_argument("--scorecard-dir", type=Path, default=DEFAULT_SCORECARD_DIR)
    parser.add_argument("--walk-forward-dir", type=Path, default=DEFAULT_WALK_FORWARD_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cost-mode", choices=("none", "estimated"), default="estimated")
    parser.add_argument("--return-mode", choices=("gross", "net"), default="net")
    parser.add_argument("--include-cross-pair", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-pair-specific", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        build_research_decision_report(parse_args())
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as exc:
        print(f"Research decision report failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
