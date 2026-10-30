"""Build a descriptive review of fixed-candidate R-multiple baselines.

This module reads an already-built fixed-candidate comparison table and writes
neutral descriptive deltas. It is artifact-only: it does not execute stress
validation, backtests, baseline diagnostics, candidate audit, model work,
database work, or operational workflows.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_r_multiple_baseline_review"
DEFAULT_COMPARISON_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_comparison_table"
    / "gbpusd_short_h10_1_5_off_hours_baseline_comparison_table_v3"
)
DEFAULT_COMPARISON_TABLE_CSV = DEFAULT_COMPARISON_DIR / "fixed_candidate_baseline_comparison_table.csv"
DEFAULT_COMPARISON_MANIFEST_JSON = DEFAULT_COMPARISON_DIR / "fixed_candidate_baseline_comparison_manifest.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_r_multiple_baseline_review"

OUTPUT_CSV = "fixed_candidate_r_multiple_baseline_review.csv"
OUTPUT_REPORT = "fixed_candidate_r_multiple_baseline_review_report.md"
OUTPUT_WARNINGS = "fixed_candidate_r_multiple_baseline_review_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_r_multiple_baseline_review_manifest.json"

BASELINE_TYPES = ("broad_regime_baseline", "single_filter_a", "single_filter_b")
COST_PROFILES = ("p75", "p90")
REVIEW_STATUSES = {
    "descriptive_review_available",
    "unavailable_missing_exact_row",
    "unavailable_missing_baseline_row",
    "blocked_metric_namespace_mismatch",
    "unreadable_input",
}

FIELDNAMES = [
    "run_id",
    "review_scope",
    "cost_profile",
    "exact_row_type",
    "baseline_type",
    "metric_namespace",
    "metric_unit",
    "exact_trades",
    "baseline_trades",
    "trade_count_ratio_exact_to_baseline",
    "exact_mean_R",
    "baseline_mean_R",
    "delta_mean_R",
    "exact_profit_factor_R",
    "baseline_profit_factor_R",
    "delta_profit_factor_R",
    "exact_cumulative_R",
    "baseline_cumulative_R",
    "delta_cumulative_R",
    "exact_max_drawdown_R",
    "baseline_max_drawdown_R",
    "delta_max_drawdown_R",
    "exact_yearly_positive_ratio",
    "baseline_yearly_positive_ratio",
    "delta_yearly_positive_ratio",
    "descriptive_tradeoff_note",
    "review_status",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "review_scope",
    "cost_profile",
    "baseline_type",
    "blocking_warning",
]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return repr(value)
    return str(value)


def bool_text(value: bool) -> str:
    return "true" if value else "false"


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
    if math.isnan(parsed):
        return None
    return parsed


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    return numerator / denominator


def delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
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
        "review": output_dir / OUTPUT_CSV,
        "report": output_dir / OUTPUT_REPORT,
        "warnings": output_dir / OUTPUT_WARNINGS,
        "manifest": output_dir / OUTPUT_MANIFEST,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def comparison_lookup(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], dict[str, str]]:
    lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (
            str(row.get("row_type") or "").strip(),
            str(row.get("baseline_type") or "").strip(),
            str(row.get("cost_profile") or "").strip(),
        )
        if all(key) and key not in lookup:
            lookup[key] = row
    return lookup


def warning_row(
    *,
    warning_code: str,
    severity: str,
    message: str,
    review_scope: str,
    cost_profile: str,
    baseline_type: str,
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "review_scope": review_scope,
        "cost_profile": cost_profile,
        "baseline_type": baseline_type,
        "blocking_warning": bool_text(blocking_warning),
    }


def add_warning_for_row(
    warnings: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    warning_code: str,
    severity: str,
    message: str,
    blocking_warning: bool = False,
) -> None:
    row["warning_code"] = warning_code
    row["blocking_warning"] = bool_text(blocking_warning)
    warnings.append(
        warning_row(
            warning_code=warning_code,
            severity=severity,
            message=message,
            review_scope=str(row.get("review_scope") or ""),
            cost_profile=str(row.get("cost_profile") or ""),
            baseline_type=str(row.get("baseline_type") or ""),
            blocking_warning=blocking_warning,
        )
    )


def exact_metrics(row: dict[str, str] | None) -> dict[str, float | None]:
    row = row or {}
    return {
        "trades": safe_float(row.get("trades")),
        "mean_R": safe_float(row.get("exact_mean_R")),
        "profit_factor_R": safe_float(row.get("exact_profit_factor_R")),
        "cumulative_R": safe_float(row.get("exact_cumulative_R")),
        "max_drawdown_R": safe_float(row.get("exact_max_drawdown_R")),
        "yearly_positive_ratio": safe_float(row.get("yearly_positive_ratio")),
    }


def baseline_metrics(row: dict[str, str] | None) -> dict[str, float | None]:
    row = row or {}
    return {
        "trades": safe_float(row.get("trades")),
        "mean_R": safe_float(row.get("baseline_mean_R")),
        "profit_factor_R": safe_float(row.get("baseline_profit_factor_R")),
        "cumulative_R": safe_float(row.get("baseline_cumulative_R")),
        "max_drawdown_R": safe_float(row.get("baseline_max_drawdown_R")),
        "yearly_positive_ratio": safe_float(row.get("yearly_positive_ratio")),
    }


def row_status_available(row: dict[str, str] | None) -> bool:
    return bool(row) and str(row.get("artifact_status") or "") == "available"


def row_namespace(row: dict[str, str] | None) -> str:
    return str((row or {}).get("metric_namespace") or "")


def row_unit(row: dict[str, str] | None) -> str:
    return str((row or {}).get("metric_unit") or "")


def neutral_notes(left: dict[str, float | None], right: dict[str, float | None], *, mode: str) -> str:
    notes = ["same_namespace_descriptive_only", "requires_walk_forward_or_timeout_review_before_decision"]
    left_trades = left.get("trades")
    right_trades = right.get("trades")
    if left_trades is not None and right_trades is not None:
        if left_trades < right_trades:
            notes.append("exact_more_selective" if mode == "exact_vs_baseline" else "p75_lower_trade_count")
            if mode == "exact_vs_baseline":
                notes.append("baseline_has_higher_trade_count")
        elif left_trades > right_trades and mode == "exact_vs_baseline":
            notes.append("exact_higher_trade_count")

    mean_delta = delta(left.get("mean_R"), right.get("mean_R"))
    if mean_delta is not None:
        if mean_delta < 0 and mode == "exact_vs_baseline":
            notes.append("exact_mean_R_lower_than_baseline")
        elif mean_delta > 0 and mode == "exact_vs_baseline":
            notes.append("exact_mean_R_above_baseline")
        elif mode != "exact_vs_baseline":
            notes.append("cost_profile_mean_R_difference_observed")

    pf_delta = delta(left.get("profit_factor_R"), right.get("profit_factor_R"))
    if pf_delta is not None:
        if pf_delta < 0 and mode == "exact_vs_baseline":
            notes.append("exact_profit_factor_lower_than_baseline")
        elif pf_delta > 0 and mode == "exact_vs_baseline":
            notes.append("exact_profit_factor_above_baseline")
        elif mode != "exact_vs_baseline":
            notes.append("cost_profile_profit_factor_difference_observed")

    cumulative_delta = delta(left.get("cumulative_R"), right.get("cumulative_R"))
    if cumulative_delta is not None and cumulative_delta < 0 and mode == "exact_vs_baseline" and left_trades and right_trades:
        if left_trades < right_trades:
            notes.append("exact_cumulative_R_lower_due_fewer_trades")

    drawdown_delta = delta(left.get("max_drawdown_R"), right.get("max_drawdown_R"))
    if drawdown_delta is not None and mode == "exact_vs_baseline":
        if drawdown_delta < 0:
            notes.append("exact_lower_drawdown")
        elif drawdown_delta > 0:
            notes.append("exact_higher_drawdown")

    return ";".join(dict.fromkeys(notes))


def review_row_base(args: argparse.Namespace, *, review_scope: str, cost_profile: str, baseline_type: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "review_scope": review_scope,
        "cost_profile": cost_profile,
        "exact_row_type": "exact_rule",
        "baseline_type": baseline_type,
        "metric_namespace": "",
        "metric_unit": "",
        "exact_trades": "",
        "baseline_trades": "",
        "trade_count_ratio_exact_to_baseline": "",
        "exact_mean_R": "",
        "baseline_mean_R": "",
        "delta_mean_R": "",
        "exact_profit_factor_R": "",
        "baseline_profit_factor_R": "",
        "delta_profit_factor_R": "",
        "exact_cumulative_R": "",
        "baseline_cumulative_R": "",
        "delta_cumulative_R": "",
        "exact_max_drawdown_R": "",
        "baseline_max_drawdown_R": "",
        "delta_max_drawdown_R": "",
        "exact_yearly_positive_ratio": "",
        "baseline_yearly_positive_ratio": "",
        "delta_yearly_positive_ratio": "",
        "descriptive_tradeoff_note": "",
        "review_status": "descriptive_review_available",
        "warning_code": "",
        "blocking_warning": "false",
    }


def populate_metrics(
    row: dict[str, Any],
    *,
    left: dict[str, float | None],
    right: dict[str, float | None],
    mode: str,
) -> None:
    row.update(
        {
            "exact_trades": left.get("trades"),
            "baseline_trades": right.get("trades"),
            "trade_count_ratio_exact_to_baseline": safe_divide(left.get("trades"), right.get("trades")),
            "exact_mean_R": left.get("mean_R"),
            "baseline_mean_R": right.get("mean_R"),
            "delta_mean_R": delta(left.get("mean_R"), right.get("mean_R")),
            "exact_profit_factor_R": left.get("profit_factor_R"),
            "baseline_profit_factor_R": right.get("profit_factor_R"),
            "delta_profit_factor_R": delta(left.get("profit_factor_R"), right.get("profit_factor_R")),
            "exact_cumulative_R": left.get("cumulative_R"),
            "baseline_cumulative_R": right.get("cumulative_R"),
            "delta_cumulative_R": delta(left.get("cumulative_R"), right.get("cumulative_R")),
            "exact_max_drawdown_R": left.get("max_drawdown_R"),
            "baseline_max_drawdown_R": right.get("max_drawdown_R"),
            "delta_max_drawdown_R": delta(left.get("max_drawdown_R"), right.get("max_drawdown_R")),
            "exact_yearly_positive_ratio": left.get("yearly_positive_ratio"),
            "baseline_yearly_positive_ratio": right.get("yearly_positive_ratio"),
            "delta_yearly_positive_ratio": delta(left.get("yearly_positive_ratio"), right.get("yearly_positive_ratio")),
            "descriptive_tradeoff_note": neutral_notes(left, right, mode=mode),
        }
    )


def build_pair_review(
    args: argparse.Namespace,
    *,
    exact_row: dict[str, str] | None,
    baseline_row: dict[str, str] | None,
    baseline_type: str,
    cost_profile: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = review_row_base(
        args,
        review_scope=f"exact_vs_{baseline_type}",
        cost_profile=cost_profile,
        baseline_type=baseline_type,
    )
    if not row_status_available(exact_row):
        row["review_status"] = "unavailable_missing_exact_row"
        add_warning_for_row(
            warnings,
            row,
            warning_code="missing_exact_row",
            severity="warning",
            message="Exact-rule comparison row is missing or unavailable.",
        )
        return row
    if not row_status_available(baseline_row):
        row["review_status"] = "unavailable_missing_baseline_row"
        add_warning_for_row(
            warnings,
            row,
            warning_code="missing_baseline_row",
            severity="warning",
            message="Baseline comparison row is missing or unavailable.",
        )
        return row

    namespaces = {row_namespace(exact_row), row_namespace(baseline_row)}
    if namespaces != {"R_multiple"}:
        row["metric_namespace"] = ";".join(sorted(namespace for namespace in namespaces if namespace))
        row["metric_unit"] = ";".join(sorted({row_unit(exact_row), row_unit(baseline_row)} - {""}))
        row["review_status"] = "blocked_metric_namespace_mismatch"
        add_warning_for_row(
            warnings,
            row,
            warning_code="metric_namespace_mismatch",
            severity="warning",
            message="Rows do not share the R_multiple metric namespace.",
        )
        return row

    row["metric_namespace"] = "R_multiple"
    row["metric_unit"] = "R"
    populate_metrics(row, left=exact_metrics(exact_row), right=baseline_metrics(baseline_row), mode="exact_vs_baseline")
    return row


def build_cost_sensitivity_review(
    args: argparse.Namespace,
    *,
    p75_row: dict[str, str] | None,
    p90_row: dict[str, str] | None,
    review_scope: str,
    baseline_type: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    row = review_row_base(
        args,
        review_scope=review_scope,
        cost_profile="p75_vs_p90",
        baseline_type=baseline_type,
    )
    if not row_status_available(p75_row):
        row["review_status"] = "unavailable_missing_exact_row" if baseline_type == "exact_rule" else "unavailable_missing_baseline_row"
        add_warning_for_row(
            warnings,
            row,
            warning_code="missing_p75_row",
            severity="warning",
            message="p75 row is missing or unavailable for cost-sensitivity review.",
        )
        return row
    if not row_status_available(p90_row):
        row["review_status"] = "unavailable_missing_exact_row" if baseline_type == "exact_rule" else "unavailable_missing_baseline_row"
        add_warning_for_row(
            warnings,
            row,
            warning_code="missing_p90_row",
            severity="warning",
            message="p90 row is missing or unavailable for cost-sensitivity review.",
        )
        return row

    namespaces = {row_namespace(p75_row), row_namespace(p90_row)}
    if namespaces != {"R_multiple"}:
        row["metric_namespace"] = ";".join(sorted(namespace for namespace in namespaces if namespace))
        row["metric_unit"] = ";".join(sorted({row_unit(p75_row), row_unit(p90_row)} - {""}))
        row["review_status"] = "blocked_metric_namespace_mismatch"
        add_warning_for_row(
            warnings,
            row,
            warning_code="metric_namespace_mismatch",
            severity="warning",
            message="p75/p90 rows do not share the R_multiple metric namespace.",
        )
        return row

    row["metric_namespace"] = "R_multiple"
    row["metric_unit"] = "R"
    metric_reader = exact_metrics if baseline_type == "exact_rule" else baseline_metrics
    populate_metrics(row, left=metric_reader(p75_row), right=metric_reader(p90_row), mode="cost_sensitivity")
    row["descriptive_tradeoff_note"] = row["descriptive_tradeoff_note"] + ";cost_sensitivity_p75_minus_p90"
    return row


def unreadable_rows(args: argparse.Namespace, warnings: list[dict[str, Any]], message: str) -> list[dict[str, Any]]:
    row = review_row_base(
        args,
        review_scope="exact_vs_broad_regime_baseline",
        cost_profile="p75",
        baseline_type="broad_regime_baseline",
    )
    row["review_status"] = "unreadable_input"
    add_warning_for_row(
        warnings,
        row,
        warning_code="unreadable_input",
        severity="error",
        message=message,
    )
    return [row]


def load_manifest_namespaces(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    namespaces = payload.get("metric_namespaces", [])
    return [str(item) for item in namespaces] if isinstance(namespaces, list) else []


def build_review(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    comparison_path = Path(args.comparison_table_csv)
    try:
        comparison_rows = read_csv_rows(comparison_path)
    except (FileNotFoundError, OSError, csv.Error) as exc:
        rows = unreadable_rows(args, warnings, f"Unable to read comparison table: {exc}")
        metadata = {"comparison_manifest_namespaces": load_manifest_namespaces(Path(args.comparison_manifest_json))}
        return rows, warnings, metadata

    lookup = comparison_lookup(comparison_rows)
    review_rows: list[dict[str, Any]] = []
    for baseline_type in BASELINE_TYPES:
        for cost_profile in COST_PROFILES:
            review_rows.append(
                build_pair_review(
                    args,
                    exact_row=lookup.get(("exact_rule", "exact_rule", cost_profile)),
                    baseline_row=lookup.get(("baseline", baseline_type, cost_profile)),
                    baseline_type=baseline_type,
                    cost_profile=cost_profile,
                    warnings=warnings,
                )
            )

    review_rows.append(
        build_cost_sensitivity_review(
            args,
            p75_row=lookup.get(("exact_rule", "exact_rule", "p75")),
            p90_row=lookup.get(("exact_rule", "exact_rule", "p90")),
            review_scope="exact_cost_sensitivity",
            baseline_type="exact_rule",
            warnings=warnings,
        )
    )
    for baseline_type in BASELINE_TYPES:
        review_rows.append(
            build_cost_sensitivity_review(
                args,
                p75_row=lookup.get(("baseline", baseline_type, "p75")),
                p90_row=lookup.get(("baseline", baseline_type, "p90")),
                review_scope="baseline_cost_sensitivity",
                baseline_type=baseline_type,
                warnings=warnings,
            )
        )

    namespaces = sorted({str(row.get("metric_namespace") or "") for row in review_rows if row.get("metric_namespace")})
    metadata = {
        "comparison_manifest_namespaces": load_manifest_namespaces(Path(args.comparison_manifest_json)),
        "metric_namespaces": namespaces,
    }
    return review_rows, warnings, metadata


def status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("review_status") or "") for row in rows)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    counts = status_counts(rows)
    available = [row for row in rows if row.get("review_status") == "descriptive_review_available"]
    lines = [
        "# Fixed Candidate R-Multiple Baseline Review",
        "",
        "Artifact-only descriptive review. This module reads an existing comparison table and writes neutral descriptive deltas only.",
        "No stress validation, backtests, baseline diagnostics, candidate audit, model work, database mutation, or operational action was executed.",
        "No candidate-quality evaluation, approval, rejection, recommendation, profitability conclusion, or trading decision was made.",
        "",
        "## Inputs",
        "",
        f"- comparison_table_csv: `{args.comparison_table_csv}`",
        f"- comparison_manifest_json: `{args.comparison_manifest_json}`",
        "",
        "## Counts",
        "",
        f"- review_row_count: `{len(rows)}`",
        f"- descriptive_review_available: `{counts.get('descriptive_review_available', 0)}`",
        f"- unavailable_missing_exact_row: `{counts.get('unavailable_missing_exact_row', 0)}`",
        f"- unavailable_missing_baseline_row: `{counts.get('unavailable_missing_baseline_row', 0)}`",
        f"- blocked_metric_namespace_mismatch: `{counts.get('blocked_metric_namespace_mismatch', 0)}`",
        f"- unreadable_input: `{counts.get('unreadable_input', 0)}`",
        f"- warnings: `{len(warnings)}`",
        f"- metric_namespaces: `{', '.join(metadata.get('metric_namespaces', [])) or 'none'}`",
        "",
        "## Descriptive Summaries",
        "",
    ]
    for scope in ("exact_vs_broad_regime_baseline", "exact_vs_single_filter_a", "exact_vs_single_filter_b"):
        scope_rows = [row for row in available if row.get("review_scope") == scope]
        lines.append(f"- `{scope}`: `{len(scope_rows)}` descriptive rows available.")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Descriptive deltas are not approval or rejection of a strategy.",
            "- Same-namespace R-multiple rows allow arithmetic deltas, but they do not replace walk-forward review.",
            "- Suggested next review areas: walk-forward review, timeout policy review, drawdown/clustering review, exact-vs-single_filter_a attribution review.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    counts = status_counts(rows)
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "comparison_table_csv": str(args.comparison_table_csv),
        "comparison_manifest_json": str(args.comparison_manifest_json),
        "review_row_count": len(rows),
        "descriptive_review_available_count": counts.get("descriptive_review_available", 0),
        "unavailable_missing_exact_row_count": counts.get("unavailable_missing_exact_row", 0),
        "unavailable_missing_baseline_row_count": counts.get("unavailable_missing_baseline_row", 0),
        "blocked_metric_namespace_mismatch_count": counts.get("blocked_metric_namespace_mismatch", 0),
        "unreadable_input_count": counts.get("unreadable_input", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"),
        "metric_namespaces": metadata.get("metric_namespaces", []),
        "comparison_manifest_metric_namespaces": metadata.get("comparison_manifest_namespaces", []),
        "no_child_scripts_executed": True,
        "no_stress_validation_executed": True,
        "no_backtests_run": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_audit_executed": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    rows, warnings, metadata = build_review(args)
    write_csv(paths["review"], rows, FIELDNAMES)
    write_csv(paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(paths["report"], args=args, rows=rows, warnings=warnings, metadata=metadata)
    write_manifest(paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings, metadata=metadata)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build an artifact-only descriptive R-multiple baseline review. "
            "No validation, diagnostics, backtests, or child scripts are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--comparison-table-csv", type=Path, default=DEFAULT_COMPARISON_TABLE_CSV)
    parser.add_argument("--comparison-manifest-json", type=Path, default=DEFAULT_COMPARISON_MANIFEST_JSON)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate R-multiple baseline review build failed: {exc}")
        return 1
    print("Fixed-candidate R-multiple baseline review build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
