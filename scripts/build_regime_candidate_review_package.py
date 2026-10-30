"""Build a research-only review package from regime candidate stress outputs.

The script reads existing CSV outputs from one stress-validation run and writes
a compact review package. It does not rerun validation, change candidate
definitions, alter TP/SL settings, add features, or create operational
instructions.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import dataclass
import math
from pathlib import Path
import sys
from typing import Any

try:
    from candidate_audit_schema import (
        add_common_summary_fields,
        normalize_warning_severity,
        warning_row,
        with_common_summary_fields,
        with_common_warning_fields,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.candidate_audit_schema import (
        add_common_summary_fields,
        normalize_warning_severity,
        warning_row,
        with_common_summary_fields,
        with_common_warning_fields,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "regime_candidate_review"

SUMMARY_FILE = "candidate_stress_summary.csv"
BASE_TRADE_LOG_FILE = "trade_log_base.csv"
STRESS_TRADE_LOG_FILE = "trade_log_stress.csv"
BASE_EQUITY_CURVE_FILE = "equity_curve_base.csv"
STRESS_EQUITY_CURVE_FILE = "equity_curve_stress.csv"
YEARLY_FILE = "yearly_validation.csv"
WALK_FORWARD_FILE = "walk_forward_validation.csv"
RANDOM_BASELINE_FILE = "random_baseline_summary.csv"

REPORT_FILE = "candidate_review_report.md"
REVIEW_SUMMARY_FILE = "candidate_review_summary.csv"
WARNINGS_FILE = "candidate_review_warnings.csv"
OUTPUT_FILES = (REPORT_FILE, REVIEW_SUMMARY_FILE, WARNINGS_FILE)

MIN_SEQUENTIAL_TRADES = 50
CONSERVATIVE_STRESS_POLICY = "max_row_or_fallback"
SEVERE_TOP_MONTH_CONTRIBUTION_PCT = 50.0
SEVERE_TOP_5_CONTRIBUTION_PCT = 50.0

READY_LABEL = "READY_FOR_RULE_BASED_RESEARCH_BACKTEST_REVIEW"
RETAINED_LABEL = "REVIEW_PACKAGE_RETAINED"
REJECTED_LABEL = "REVIEW_PACKAGE_REJECTED"

REQUIRED_INPUT_FILES = (SUMMARY_FILE,)
EXPECTED_INPUT_FILES = (
    SUMMARY_FILE,
    BASE_TRADE_LOG_FILE,
    STRESS_TRADE_LOG_FILE,
    BASE_EQUITY_CURVE_FILE,
    STRESS_EQUITY_CURVE_FILE,
    YEARLY_FILE,
    WALK_FORWARD_FILE,
    RANDOM_BASELINE_FILE,
)
REQUIRED_CANDIDATE_METADATA_FIELDS = (
    "symbol",
    "direction",
    "timeframe",
    "horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "feature_condition",
)

WARNING_FIELDNAMES = [
    "severity",
    "check",
    "blocks_ready",
    "message",
]
WARNING_FIELDNAMES = with_common_warning_fields(WARNING_FIELDNAMES)

SUMMARY_FIELDNAMES = [
    "run_id",
    "stress_output_dir",
    "review_output_dir",
    "final_research_only_classification",
    "ready_for_rule_based_research_backtest_review",
    "warnings_count",
    "blocking_warnings_count",
    "symbol",
    "direction",
    "timeframe",
    "horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "feature_condition",
    "tp_atr",
    "sl_atr",
    "candidate_scope",
    "exact_candidate_not_available_reason",
    "stress_spread_policy",
    "stress_applied",
    "stress_changed_cost_R",
    "stress_cost_no_effect_warning",
    "sequential_trades_count",
    "stress_sequential_trades_count",
    "base_mean_R",
    "base_profit_factor_R",
    "stress_mean_R",
    "stress_profit_factor_R",
    "stress_mean_R_delta",
    "stress_profit_factor_R_delta",
    "mean_cost_R_base",
    "mean_cost_R_stress",
    "cost_R_delta_mean",
    "net_R_delta_mean",
    "yearly_positive_ratio",
    "yearly_rows_count",
    "yearly_non_positive_count",
    "random_baseline_available",
    "candidate_mean_R_vs_random_p95",
    "candidate_profit_factor_R_vs_random_p95",
    "walk_forward_rows_count",
    "weak_walk_forward_count",
    "max_drawdown_R",
    "stress_max_drawdown_R",
    "top_month_contribution_pct",
    "top_5_percent_contribution_pct",
    "base_tp_count",
    "base_sl_count",
    "base_timeout_count",
    "base_other_exit_count",
    "base_tp_rate",
    "base_sl_rate",
    "base_timeout_rate",
    "stress_tp_count",
    "stress_sl_count",
    "stress_timeout_count",
    "stress_other_exit_count",
    "stress_tp_rate",
    "stress_sl_rate",
    "stress_timeout_rate",
    "base_equity_final_cumulative_R",
    "base_equity_max_drawdown_R",
    "stress_equity_final_cumulative_R",
    "stress_equity_max_drawdown_R",
]
SUMMARY_FIELDNAMES = with_common_summary_fields(SUMMARY_FIELDNAMES)


@dataclass(frozen=True)
class ReviewInputs:
    stress_summary: dict[str, str]
    base_trade_rows: list[dict[str, str]]
    stress_trade_rows: list[dict[str, str]]
    base_equity_rows: list[dict[str, str]]
    stress_equity_rows: list[dict[str, str]]
    yearly_rows: list[dict[str, str]]
    walk_forward_rows: list[dict[str, str]]
    random_rows: list[dict[str, str]]
    missing_expected_files: list[str]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only review package from existing regime candidate stress CSVs."
    )
    parser.add_argument("--stress-output-dir", required=True, type=Path)
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, type=Path)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
    return value


def read_review_inputs(stress_output_dir: Path) -> ReviewInputs:
    missing_required = [
        filename for filename in REQUIRED_INPUT_FILES if not (stress_output_dir / filename).exists()
    ]
    if missing_required:
        joined = ", ".join(missing_required)
        raise FileNotFoundError(f"Missing required review input file(s): {joined}")

    missing_expected = [
        filename for filename in EXPECTED_INPUT_FILES if not (stress_output_dir / filename).exists()
    ]
    summary_rows = read_csv_rows(stress_output_dir / SUMMARY_FILE)
    if not summary_rows:
        raise ValueError(f"{SUMMARY_FILE} contains no rows")

    def optional_rows(filename: str) -> list[dict[str, str]]:
        path = stress_output_dir / filename
        return read_csv_rows(path) if path.exists() else []

    return ReviewInputs(
        stress_summary=summary_rows[0],
        base_trade_rows=optional_rows(BASE_TRADE_LOG_FILE),
        stress_trade_rows=optional_rows(STRESS_TRADE_LOG_FILE),
        base_equity_rows=optional_rows(BASE_EQUITY_CURVE_FILE),
        stress_equity_rows=optional_rows(STRESS_EQUITY_CURVE_FILE),
        yearly_rows=optional_rows(YEARLY_FILE),
        walk_forward_rows=optional_rows(WALK_FORWARD_FILE),
        random_rows=optional_rows(RANDOM_BASELINE_FILE),
        missing_expected_files=missing_expected,
    )


def finite_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else parsed


def bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def int_value(value: object) -> int | None:
    parsed = finite_float(value)
    if parsed is None or not math.isfinite(parsed):
        return None
    return int(parsed)


def add_warning(
    warnings: list[dict[str, object]],
    *,
    severity: str,
    check: str,
    message: str,
    blocks_ready: bool = True,
) -> None:
    normalized_severity = normalize_warning_severity(severity)
    warnings.append(
        warning_row(
            warning_code=check,
            severity=normalized_severity,
            blocking=blocks_ready,
            message=message,
            related_stage="candidate_review",
            related_metric=check,
            check=check,
            blocks_ready=bool(blocks_ready),
        )
    )


def next_action_for_classification(classification: str) -> str:
    if classification == READY_LABEL:
        return "Candidate may be considered for a future offline rule-based research backtester."
    if classification == RETAINED_LABEL:
        return "Candidate remains in research review before any rule-replay audit."
    return "Candidate should not continue to rule-replay audit under current evidence."


def missing_candidate_metadata(row: dict[str, object]) -> list[str]:
    return [field for field in REQUIRED_CANDIDATE_METADATA_FIELDS if not str(row.get(field) or "").strip()]


def exit_profile(rows: list[dict[str, str]], prefix: str) -> dict[str, object]:
    counter: Counter[str] = Counter()
    for row in rows:
        reason = str(row.get("exit_reason") or "").strip().lower()
        if reason in {"tp", "take_profit"}:
            counter["tp"] += 1
        elif reason in {"sl", "stop_loss"}:
            counter["sl"] += 1
        elif reason in {"timeout", "end_of_data"}:
            counter["timeout"] += 1
        else:
            counter["other"] += 1
    total = sum(counter.values())

    def rate(key: str) -> float | None:
        return counter[key] / total if total else None

    return {
        f"{prefix}_tp_count": counter["tp"],
        f"{prefix}_sl_count": counter["sl"],
        f"{prefix}_timeout_count": counter["timeout"],
        f"{prefix}_other_exit_count": counter["other"],
        f"{prefix}_tp_rate": rate("tp"),
        f"{prefix}_sl_rate": rate("sl"),
        f"{prefix}_timeout_rate": rate("timeout"),
    }


def equity_summary(rows: list[dict[str, str]], prefix: str) -> dict[str, object]:
    cumulative_values = [finite_float(row.get("cumulative_R")) for row in rows]
    drawdown_values = [finite_float(row.get("drawdown_R")) for row in rows]
    cumulative_values = [value for value in cumulative_values if value is not None and math.isfinite(value)]
    drawdown_values = [value for value in drawdown_values if value is not None and math.isfinite(value)]
    return {
        f"{prefix}_equity_final_cumulative_R": cumulative_values[-1] if cumulative_values else None,
        f"{prefix}_equity_max_drawdown_R": max(drawdown_values) if drawdown_values else None,
    }


def weak_walk_forward_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row for row in rows
        if str(row.get("test_classification") or "").strip().lower() == "weak"
    ]


def yearly_non_positive_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    weak_rows: list[dict[str, str]] = []
    for row in rows:
        mean_r = finite_float(row.get("mean_R"))
        cumulative_r = finite_float(row.get("cumulative_R"))
        if (mean_r is not None and mean_r <= 0) or (cumulative_r is not None and cumulative_r <= 0):
            weak_rows.append(row)
    return weak_rows


def first_random_row(inputs: ReviewInputs) -> dict[str, str]:
    return inputs.random_rows[0] if inputs.random_rows else {}


def build_summary_and_warnings(
    *,
    run_id: str,
    stress_output_dir: Path,
    review_output_dir: Path,
    inputs: ReviewInputs,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    source = inputs.stress_summary
    random_source = first_random_row(inputs)
    warnings: list[dict[str, object]] = []

    for filename in inputs.missing_expected_files:
        add_warning(
            warnings,
            severity="warning",
            check=f"missing_{filename.replace('.', '_')}",
            message=f"Expected input file is missing: {filename}",
        )

    missing_metadata = missing_candidate_metadata(source)
    if missing_metadata:
        add_warning(
            warnings,
            severity="warning",
            check="candidate_metadata_missing",
            message="Candidate metadata is missing required field(s): " + ", ".join(missing_metadata),
        )

    candidate_scope = str(source.get("candidate_scope") or "").strip()
    exact_reason = str(source.get("exact_candidate_not_available_reason") or "").strip()
    stress_policy = str(source.get("stress_spread_policy") or "").strip()
    stress_applied = bool_value(source.get("stress_applied"))
    stress_changed_cost = bool_value(
        source.get("stress_changed_cost_R")
        if source.get("stress_changed_cost_R") not in {None, ""}
        else source.get("stress_cost_R_changed")
    )
    stress_no_effect = bool_value(source.get("stress_cost_no_effect_warning"))
    sequential_trades = int_value(source.get("sequential_trades_count"))
    stress_mean_r = finite_float(source.get("stress_mean_R"))
    stress_pf = finite_float(source.get("stress_profit_factor_R"))
    yearly_ratio = finite_float(source.get("yearly_positive_ratio"))
    random_available = bool_value(random_source.get("random_baseline_available"))
    mean_vs_random = finite_float(random_source.get("candidate_mean_R_vs_random_p95"))
    pf_vs_random = finite_float(random_source.get("candidate_profit_factor_R_vs_random_p95"))
    max_drawdown = finite_float(source.get("max_drawdown_R"))
    top_month_pct = finite_float(source.get("top_month_contribution_pct"))
    top_5_pct = finite_float(source.get("top_5_percent_contribution_pct"))

    if candidate_scope != "exact_feature_combination":
        add_warning(
            warnings,
            severity="error",
            check="candidate_scope",
            message="Candidate scope is not exact_feature_combination.",
        )
    if exact_reason:
        add_warning(
            warnings,
            severity="error",
            check="exact_candidate_reconstruction",
            message=f"Exact candidate reconstruction has a reason: {exact_reason}",
        )
    if stress_policy != CONSERVATIVE_STRESS_POLICY:
        add_warning(
            warnings,
            severity="warning",
            check="stress_spread_policy",
            message="Conservative review expects stress_spread_policy=max_row_or_fallback.",
        )
    if not stress_applied:
        add_warning(
            warnings,
            severity="error",
            check="stress_applied",
            message="Stress cost replay was not applied.",
        )
    if not stress_changed_cost:
        add_warning(
            warnings,
            severity="error",
            check="stress_changed_cost_R",
            message="Stress cost replay did not change cost_R.",
        )
    if stress_no_effect:
        add_warning(
            warnings,
            severity="error",
            check="stress_cost_no_effect_warning",
            message="Stress replay produced a no-effect warning.",
        )
    if sequential_trades is None or sequential_trades < MIN_SEQUENTIAL_TRADES:
        add_warning(
            warnings,
            severity="warning",
            check="sequential_trades_count",
            message=f"Sequential trade count is below {MIN_SEQUENTIAL_TRADES}.",
        )
    if stress_mean_r is None or stress_mean_r <= 0:
        add_warning(
            warnings,
            severity="error",
            check="stress_mean_R",
            message="Stress mean_R is not positive.",
        )
    if stress_pf is None or stress_pf <= 1:
        add_warning(
            warnings,
            severity="error",
            check="stress_profit_factor_R",
            message="Stress profit_factor_R is not above 1.",
        )
    if yearly_ratio is None or not math.isclose(yearly_ratio, 1.0, rel_tol=0.0, abs_tol=1e-12):
        add_warning(
            warnings,
            severity="warning",
            check="yearly_positive_ratio",
            message="yearly_positive_ratio is below 1.0 or missing.",
        )
    if not inputs.yearly_rows:
        add_warning(
            warnings,
            severity="warning",
            check="yearly_validation_rows",
            message="No yearly validation rows were available for package review.",
        )
    non_positive_years = yearly_non_positive_rows(inputs.yearly_rows)
    if non_positive_years:
        add_warning(
            warnings,
            severity="warning",
            check="yearly_validation_positive",
            message=f"{len(non_positive_years)} yearly row(s) were non-positive.",
        )
    if not random_available:
        add_warning(
            warnings,
            severity="warning",
            check="random_baseline_available",
            message="Random baseline was not available.",
        )
    if mean_vs_random is None or mean_vs_random <= 0:
        add_warning(
            warnings,
            severity="warning",
            check="candidate_mean_R_vs_random_p95",
            message="Candidate mean_R did not beat random p95 by a positive margin.",
        )
    if pf_vs_random is None or pf_vs_random <= 0:
        add_warning(
            warnings,
            severity="warning",
            check="candidate_profit_factor_R_vs_random_p95",
            message="Candidate profit_factor_R did not beat random p95 by a positive margin.",
        )
    weak_wf = weak_walk_forward_rows(inputs.walk_forward_rows)
    if not inputs.walk_forward_rows:
        add_warning(
            warnings,
            severity="warning",
            check="walk_forward_rows",
            message="No walk-forward rows were available for package review.",
        )
    if weak_wf:
        add_warning(
            warnings,
            severity="warning",
            check="walk_forward_weak_split",
            message=f"{len(weak_wf)} walk-forward split(s) were classified as weak.",
        )
    if max_drawdown is None:
        add_warning(
            warnings,
            severity="warning",
            check="max_drawdown_R",
            message="max_drawdown_R is missing from the stress summary.",
        )
    if top_month_pct is None:
        add_warning(
            warnings,
            severity="warning",
            check="top_month_contribution_pct",
            message="top_month_contribution_pct is not available.",
            blocks_ready=False,
        )
    elif top_month_pct > SEVERE_TOP_MONTH_CONTRIBUTION_PCT:
        add_warning(
            warnings,
            severity="error",
            check="severe_top_month_concentration",
            message="top_month_contribution_pct exceeds the severe concentration threshold.",
        )
    if top_5_pct is None:
        add_warning(
            warnings,
            severity="warning",
            check="top_5_percent_contribution_pct",
            message="top_5_percent_contribution_pct is not available.",
            blocks_ready=False,
        )
    elif top_5_pct > SEVERE_TOP_5_CONTRIBUTION_PCT:
        add_warning(
            warnings,
            severity="error",
            check="severe_top_5_percent_concentration",
            message="top_5_percent_contribution_pct exceeds the severe concentration threshold.",
        )

    base_exit = exit_profile(inputs.base_trade_rows, "base")
    stress_exit = exit_profile(inputs.stress_trade_rows, "stress")
    base_equity = equity_summary(inputs.base_equity_rows, "base")
    stress_equity = equity_summary(inputs.stress_equity_rows, "stress")

    blocking_count = sum(1 for warning in warnings if bool(warning.get("blocks_ready")))
    readiness_checks = {
        "exact_scope": candidate_scope == "exact_feature_combination" and not exact_reason,
        "conservative_policy": stress_policy == CONSERVATIVE_STRESS_POLICY,
        "stress_changed": stress_applied and stress_changed_cost and not stress_no_effect,
        "sample_size": sequential_trades is not None and sequential_trades >= MIN_SEQUENTIAL_TRADES,
        "stress_positive": stress_mean_r is not None and stress_mean_r > 0 and stress_pf is not None and stress_pf > 1,
        "random_beaten": random_available and mean_vs_random is not None and mean_vs_random > 0 and pf_vs_random is not None and pf_vs_random > 0,
        "yearly_positive": yearly_ratio is not None
        and math.isclose(yearly_ratio, 1.0, rel_tol=0.0, abs_tol=1e-12)
        and bool(inputs.yearly_rows)
        and not non_positive_years,
        "walk_forward": bool(inputs.walk_forward_rows) and not weak_wf,
        "concentration": not any(
            str(warning.get("severity")) == "blocking" and str(warning.get("check")).startswith("severe_")
            for warning in warnings
        ),
        "no_blocking_warnings": blocking_count == 0,
    }
    ready = all(readiness_checks.values())
    has_error = any(str(warning.get("severity")) == "blocking" for warning in warnings)
    if ready:
        classification = READY_LABEL
    elif has_error:
        classification = REJECTED_LABEL
    else:
        classification = RETAINED_LABEL

    summary: dict[str, object] = {
        "run_id": run_id,
        "stress_output_dir": str(stress_output_dir),
        "review_output_dir": str(review_output_dir),
        "final_research_only_classification": classification,
        "ready_for_rule_based_research_backtest_review": ready,
        "warnings_count": len(warnings),
        "blocking_warnings_count": blocking_count,
        "symbol": source.get("symbol", ""),
        "direction": source.get("direction", ""),
        "timeframe": source.get("timeframe", ""),
        "horizon": source.get("horizon", ""),
        "target_family": source.get("target_family", ""),
        "regime_column": source.get("regime_column", ""),
        "regime_value": source.get("regime_value", ""),
        "feature_condition": source.get("feature_condition", ""),
        "tp_atr": source.get("tp_atr", ""),
        "sl_atr": source.get("sl_atr", ""),
        "candidate_scope": candidate_scope,
        "exact_candidate_not_available_reason": exact_reason,
        "stress_spread_policy": stress_policy,
        "stress_applied": stress_applied,
        "stress_changed_cost_R": stress_changed_cost,
        "stress_cost_no_effect_warning": stress_no_effect,
        "sequential_trades_count": sequential_trades,
        "stress_sequential_trades_count": int_value(source.get("stress_sequential_trades_count")),
        "base_mean_R": finite_float(source.get("mean_R")),
        "base_profit_factor_R": finite_float(source.get("profit_factor_R")),
        "stress_mean_R": stress_mean_r,
        "stress_profit_factor_R": stress_pf,
        "stress_mean_R_delta": finite_float(source.get("stress_mean_R_delta")),
        "stress_profit_factor_R_delta": finite_float(source.get("stress_profit_factor_R_delta")),
        "mean_cost_R_base": finite_float(source.get("mean_cost_R_base")),
        "mean_cost_R_stress": finite_float(source.get("mean_cost_R_stress")),
        "cost_R_delta_mean": finite_float(source.get("cost_R_delta_mean")),
        "net_R_delta_mean": finite_float(source.get("net_R_delta_mean")),
        "yearly_positive_ratio": yearly_ratio,
        "yearly_rows_count": len(inputs.yearly_rows),
        "yearly_non_positive_count": len(non_positive_years),
        "random_baseline_available": random_available,
        "candidate_mean_R_vs_random_p95": mean_vs_random,
        "candidate_profit_factor_R_vs_random_p95": pf_vs_random,
        "walk_forward_rows_count": len(inputs.walk_forward_rows),
        "weak_walk_forward_count": len(weak_wf),
        "max_drawdown_R": max_drawdown,
        "stress_max_drawdown_R": finite_float(source.get("stress_max_drawdown_R")),
        "top_month_contribution_pct": top_month_pct,
        "top_5_percent_contribution_pct": top_5_pct,
        **base_exit,
        **stress_exit,
        **base_equity,
        **stress_equity,
    }
    add_common_summary_fields(
        summary,
        decision_scope="candidate_review",
        final_classification=classification,
        next_action=next_action_for_classification(classification),
    )
    return summary, warnings


def table_lines(rows: list[dict[str, str]], columns: list[str], limit: int | None = None) -> list[str]:
    selected = rows[:limit] if limit is not None else rows
    if not selected:
        return ["No rows available."]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in selected:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return lines


def report_text(
    *,
    summary: dict[str, object],
    warnings: list[dict[str, object]],
    inputs: ReviewInputs,
) -> str:
    warning_lines = [
        f"- {warning['severity']} `{warning['check']}`: {warning['message']}"
        for warning in warnings
    ] or ["No warnings."]
    lines = [
        "# Regime Candidate Review Package",
        "",
        "## Research-Only Warning",
        "",
        "This package is an offline research review only. It reads previously generated CSV files and does not recompute performance, change assumptions, or create operational instructions.",
        "",
        "## Candidate Definition",
        "",
        f"- Symbol: `{summary.get('symbol')}`",
        f"- Direction: `{summary.get('direction')}`",
        f"- Timeframe: `{summary.get('timeframe')}`",
        f"- Horizon: `{summary.get('horizon')}`",
        f"- Target family: `{summary.get('target_family')}`",
        f"- Regime: `{summary.get('regime_column')}={summary.get('regime_value')}`",
        f"- Feature condition: `{summary.get('feature_condition')}`",
        f"- TP/SL ATR: `{summary.get('tp_atr')}` / `{summary.get('sl_atr')}`",
        "",
        "## Source Reconstruction Summary",
        "",
        f"- Candidate scope: `{summary.get('candidate_scope')}`",
        f"- Exact candidate not available reason: `{summary.get('exact_candidate_not_available_reason')}`",
        f"- Sequential trades: `{summary.get('sequential_trades_count')}`",
        f"- Stress sequential trades: `{summary.get('stress_sequential_trades_count')}`",
        "- R columns: source trade logs keep `R`, `cost_R`, and `net_R` separate; base and stress outputs are summarized separately.",
        "",
        "## Base vs Stress Metrics",
        "",
        f"- Base mean_R / PF: `{summary.get('base_mean_R')}` / `{summary.get('base_profit_factor_R')}`",
        f"- Stress mean_R / PF: `{summary.get('stress_mean_R')}` / `{summary.get('stress_profit_factor_R')}`",
        f"- Stress mean_R delta: `{summary.get('stress_mean_R_delta')}`",
        f"- Stress PF delta: `{summary.get('stress_profit_factor_R_delta')}`",
        f"- Mean cost_R base/stress: `{summary.get('mean_cost_R_base')}` / `{summary.get('mean_cost_R_stress')}`",
        f"- Mean cost_R delta: `{summary.get('cost_R_delta_mean')}`",
        f"- Mean net_R delta: `{summary.get('net_R_delta_mean')}`",
        "",
        "## Cost Stress Interpretation",
        "",
        f"- Stress spread policy: `{summary.get('stress_spread_policy')}`",
        f"- Stress applied: `{summary.get('stress_applied')}`",
        f"- Stress changed cost_R: `{summary.get('stress_changed_cost_R')}`",
        f"- Stress no-effect warning: `{summary.get('stress_cost_no_effect_warning')}`",
        "",
        "## Random Baseline Interpretation",
        "",
        f"- Random baseline available: `{summary.get('random_baseline_available')}`",
        f"- Candidate mean_R vs random p95: `{summary.get('candidate_mean_R_vs_random_p95')}`",
        f"- Candidate PF vs random p95: `{summary.get('candidate_profit_factor_R_vs_random_p95')}`",
        "",
        "## Yearly Validation Summary",
        "",
        f"- Yearly positive ratio: `{summary.get('yearly_positive_ratio')}`",
        f"- Yearly rows: `{summary.get('yearly_rows_count')}`",
        f"- Non-positive yearly rows: `{summary.get('yearly_non_positive_count')}`",
        "",
        *table_lines(inputs.yearly_rows, ["year", "trades_count", "mean_R", "profit_factor_R", "cumulative_R", "max_drawdown_R"]),
        "",
        "## Walk-Forward Summary",
        "",
        f"- Walk-forward rows: `{summary.get('walk_forward_rows_count')}`",
        f"- Weak walk-forward rows: `{summary.get('weak_walk_forward_count')}`",
        "",
        *table_lines(inputs.walk_forward_rows, ["split_id", "train_trades", "test_trades", "test_mean_R", "test_profit_factor_R", "test_classification"]),
        "",
        "## Exit Profile Summary",
        "",
        f"- Base TP/SL/timeout/other counts: `{summary.get('base_tp_count')}` / `{summary.get('base_sl_count')}` / `{summary.get('base_timeout_count')}` / `{summary.get('base_other_exit_count')}`",
        f"- Base TP/SL/timeout rates: `{summary.get('base_tp_rate')}` / `{summary.get('base_sl_rate')}` / `{summary.get('base_timeout_rate')}`",
        f"- Stress TP/SL/timeout/other counts: `{summary.get('stress_tp_count')}` / `{summary.get('stress_sl_count')}` / `{summary.get('stress_timeout_count')}` / `{summary.get('stress_other_exit_count')}`",
        f"- Stress TP/SL/timeout rates: `{summary.get('stress_tp_rate')}` / `{summary.get('stress_sl_rate')}` / `{summary.get('stress_timeout_rate')}`",
        "",
        "## Equity/Drawdown Summary",
        "",
        f"- Base final cumulative_R: `{summary.get('base_equity_final_cumulative_R')}`",
        f"- Base max drawdown_R from equity curve: `{summary.get('base_equity_max_drawdown_R')}`",
        f"- Stress final cumulative_R: `{summary.get('stress_equity_final_cumulative_R')}`",
        f"- Stress max drawdown_R from equity curve: `{summary.get('stress_equity_max_drawdown_R')}`",
        f"- Summary max_drawdown_R: `{summary.get('max_drawdown_R')}`",
        f"- Summary stress max_drawdown_R: `{summary.get('stress_max_drawdown_R')}`",
        "",
        "## Concentration Diagnostics",
        "",
        f"- Top month contribution pct: `{summary.get('top_month_contribution_pct')}`",
        f"- Top 5 percent contribution pct: `{summary.get('top_5_percent_contribution_pct')}`",
        "",
        "## Warnings",
        "",
        *warning_lines,
        "",
        "## Final Research-Only Classification",
        "",
        f"`{summary.get('final_research_only_classification')}`",
        "",
        "## Explicit Next Action",
        "",
        str(summary.get("next_action") or ""),
        "",
    ]
    return "\n".join(lines)


def output_paths(output_root: Path, run_id: str) -> dict[str, Path]:
    output_dir = output_root / run_id
    return {
        "output_dir": output_dir,
        "candidate_review_report": output_dir / REPORT_FILE,
        "candidate_review_summary": output_dir / REVIEW_SUMMARY_FILE,
        "candidate_review_warnings": output_dir / WARNINGS_FILE,
    }


def ensure_can_write(paths: dict[str, Path], overwrite: bool) -> None:
    existing = [path for key, path in paths.items() if key != "output_dir" and path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Review package output already exists; pass --overwrite to replace: {joined}")


def run_review_package(args: argparse.Namespace) -> dict[str, Path]:
    stress_output_dir = Path(args.stress_output_dir)
    if not stress_output_dir.exists():
        raise FileNotFoundError(f"Stress output directory does not exist: {stress_output_dir}")
    run_id = str(args.run_id or stress_output_dir.name).strip()
    if not run_id:
        raise ValueError("--run-id is required when --stress-output-dir has no final path name")
    paths = output_paths(Path(args.output_root), run_id)
    ensure_can_write(paths, bool(args.overwrite))

    inputs = read_review_inputs(stress_output_dir)
    summary, warnings = build_summary_and_warnings(
        run_id=run_id,
        stress_output_dir=stress_output_dir,
        review_output_dir=paths["output_dir"],
        inputs=inputs,
    )
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    write_csv(paths["candidate_review_summary"], [summary], SUMMARY_FIELDNAMES)
    write_csv(paths["candidate_review_warnings"], warnings, WARNING_FIELDNAMES)
    paths["candidate_review_report"].write_text(
        report_text(summary=summary, warnings=warnings, inputs=inputs),
        encoding="utf-8",
    )
    return paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        paths = run_review_package(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Review package written to {paths['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
