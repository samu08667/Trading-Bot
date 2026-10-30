"""Fuse fixed-candidate exact-rule and baseline artifacts into one table.

This module is artifact-only. It reads already-produced stress-validation and
baseline-consolidation outputs, normalizes them into a compact comparison
table, and writes provenance metadata. It does not execute diagnostics,
backtests, child scripts, database work, or trading workflows.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_baseline_comparison_table"
DEFAULT_EXACT_STRESS_DIR = (
    BASE_DIR
    / "reports"
    / "regime_candidate_stress"
    / "gbpusd_short_h10_1_5_off_hours_stress_exec_v2"
)
DEFAULT_BASELINE_CONSOLIDATED_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_r_multiple_outputs_consolidated"
    / "gbpusd_short_h10_1_5_off_hours_baseline_r_multiple_outputs_v1"
)
DEFAULT_MATRIX_CSV = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_cost_matrix"
    / "gbpusd_short_h10_1_5_off_hours_baseline_cost_matrix_v1"
    / "fixed_candidate_baseline_cost_matrix.csv"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_baseline_comparison_table"

EXACT_SUMMARY_FILE = "candidate_stress_summary.csv"
EXACT_REPORT_FILE = "candidate_stress_report.md"
BASELINE_CONSOLIDATED_FILE = "fixed_candidate_baseline_outputs_consolidated.csv"
BASELINE_REPORT_FILE = "fixed_candidate_baseline_outputs_report.md"
BASELINE_R_MULTIPLE_CONSOLIDATED_FILE = "fixed_candidate_baseline_r_multiple_outputs_consolidated.csv"
BASELINE_R_MULTIPLE_REPORT_FILE = "fixed_candidate_baseline_r_multiple_outputs_report.md"

OUTPUT_CSV = "fixed_candidate_baseline_comparison_table.csv"
OUTPUT_REPORT = "fixed_candidate_baseline_comparison_report.md"
OUTPUT_WARNINGS = "fixed_candidate_baseline_comparison_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_baseline_comparison_manifest.json"

EXPECTED_EXACT_ROWS = [("exact_rule", "p75"), ("exact_rule", "p90")]
EXPECTED_BASELINE_ROWS = [
    ("broad_regime_baseline", "p75"),
    ("broad_regime_baseline", "p90"),
    ("single_filter_a", "p75"),
    ("single_filter_a", "p90"),
    ("single_filter_b", "p75"),
    ("single_filter_b", "p90"),
]
STATUS_VALUES = {"available", "missing", "skipped", "unreadable", "not_applicable"}
EXACT_METRIC_NAMESPACE = "R_multiple"
EXACT_METRIC_UNIT = "R"
BASELINE_METRIC_NAMESPACE = "net_return"
BASELINE_METRIC_UNIT = "return_fraction"
R_MULTIPLE_BASELINE_METRIC_NAMESPACE = "R_multiple"
R_MULTIPLE_BASELINE_METRIC_UNIT = "R"
EXACT_COMPARABILITY_NOTE = (
    "Exact-rule metrics are R-multiple path metrics from stress validation; "
    "they are directly namespace-compatible only with other R-multiple path metrics."
)
BASELINE_COMPARABILITY_NOTE = (
    "Baseline metrics are selected net return fractions from baseline diagnostics; "
    "they are not directly numerically comparable to exact-rule R metrics unless normalized."
)
R_MULTIPLE_BASELINE_COMPARABILITY_NOTE = (
    "Baseline metrics are R-multiple path metrics from stress validation and share the exact-rule metric namespace."
)

FIELDNAMES = [
    "run_id",
    "row_type",
    "baseline_type",
    "cost_profile",
    "artifact_status",
    "metric_namespace",
    "metric_unit",
    "metric_comparability_note",
    "symbol",
    "direction",
    "timeframe",
    "target_horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "feature_condition",
    "baseline_filter",
    "cost_config_path",
    "source_artifact_type",
    "source_output_dir",
    "source_csv",
    "source_report",
    "trades",
    "mean_return",
    "profit_factor",
    "cumulative_return",
    "max_drawdown",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "yearly_positive_ratio",
    "timeout_rate",
    "tp_hit_rate",
    "sl_hit_rate",
    "exact_mean_R",
    "exact_profit_factor_R",
    "exact_cumulative_R",
    "exact_max_drawdown_R",
    "baseline_mean_R",
    "baseline_profit_factor_R",
    "baseline_cumulative_R",
    "baseline_max_drawdown_R",
    "baseline_mean_return",
    "baseline_profit_factor",
    "baseline_cumulative_return",
    "baseline_max_drawdown",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "row_type",
    "baseline_type",
    "cost_profile",
    "artifact_status",
    "source_path",
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


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
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
        "comparison": output_dir / OUTPUT_CSV,
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


def matrix_lookup(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_csv_rows(path)
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (
            str(row.get("baseline_type") or "").strip(),
            str(row.get("cost_profile") or "").strip(),
        )
        if key[0] and key[1] and key not in lookup:
            lookup[key] = row
    return lookup


def first_matrix_row(lookup: dict[tuple[str, str], dict[str, str]]) -> dict[str, str]:
    for key in [*EXPECTED_EXACT_ROWS, *EXPECTED_BASELINE_ROWS]:
        if key in lookup:
            return lookup[key]
    return {}


def row_base(
    *,
    args: argparse.Namespace,
    row_type: str,
    baseline_type: str,
    cost_profile: str,
    artifact_status: str,
    matrix_row: dict[str, str] | None = None,
) -> dict[str, Any]:
    if artifact_status not in STATUS_VALUES:
        raise ValueError(f"Unexpected artifact_status: {artifact_status}")
    matrix_row = matrix_row or {}
    metric_namespace = EXACT_METRIC_NAMESPACE if row_type == "exact_rule" else BASELINE_METRIC_NAMESPACE
    metric_unit = EXACT_METRIC_UNIT if row_type == "exact_rule" else BASELINE_METRIC_UNIT
    metric_note = EXACT_COMPARABILITY_NOTE if row_type == "exact_rule" else BASELINE_COMPARABILITY_NOTE
    return {
        "run_id": args.run_id,
        "row_type": row_type,
        "baseline_type": baseline_type,
        "cost_profile": cost_profile,
        "artifact_status": artifact_status,
        "metric_namespace": metric_namespace,
        "metric_unit": metric_unit,
        "metric_comparability_note": metric_note,
        "symbol": matrix_row.get("symbol", ""),
        "direction": matrix_row.get("direction", ""),
        "timeframe": matrix_row.get("timeframe", ""),
        "target_horizon": matrix_row.get("target_horizon", ""),
        "target_family": matrix_row.get("target_family", ""),
        "regime_column": matrix_row.get("regime_column", ""),
        "regime_value": matrix_row.get("regime_value", ""),
        "feature_condition": matrix_row.get("feature_condition", ""),
        "baseline_filter": matrix_row.get("baseline_filter", ""),
        "cost_config_path": matrix_row.get("cost_config_path", ""),
        "source_artifact_type": "",
        "source_output_dir": "",
        "source_csv": "",
        "source_report": "",
        "trades": "",
        "mean_return": "",
        "profit_factor": "",
        "cumulative_return": "",
        "max_drawdown": "",
        "monthly_positive_ratio": "",
        "quarterly_positive_ratio": "",
        "yearly_positive_ratio": "",
        "timeout_rate": "",
        "tp_hit_rate": "",
        "sl_hit_rate": "",
        "exact_mean_R": "",
        "exact_profit_factor_R": "",
        "exact_cumulative_R": "",
        "exact_max_drawdown_R": "",
        "baseline_mean_R": "",
        "baseline_profit_factor_R": "",
        "baseline_cumulative_R": "",
        "baseline_max_drawdown_R": "",
        "baseline_mean_return": "",
        "baseline_profit_factor": "",
        "baseline_cumulative_return": "",
        "baseline_max_drawdown": "",
        "warning_code": "",
        "blocking_warning": "false",
    }


def warning_row(
    *,
    warning_code: str,
    severity: str,
    message: str,
    row_type: str,
    baseline_type: str,
    cost_profile: str,
    artifact_status: str,
    source_path: Path | str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "row_type": row_type,
        "baseline_type": baseline_type,
        "cost_profile": cost_profile,
        "artifact_status": artifact_status,
        "source_path": str(source_path),
        "blocking_warning": bool_text(blocking_warning),
    }


def add_warning(
    warnings: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    warning_code: str,
    severity: str,
    message: str,
    source_path: Path | str = "",
    blocking_warning: bool = False,
) -> None:
    row["warning_code"] = warning_code
    row["blocking_warning"] = bool_text(blocking_warning)
    warnings.append(
        warning_row(
            warning_code=warning_code,
            severity=severity,
            message=message,
            row_type=str(row.get("row_type") or ""),
            baseline_type=str(row.get("baseline_type") or ""),
            cost_profile=str(row.get("cost_profile") or ""),
            artifact_status=str(row.get("artifact_status") or ""),
            source_path=source_path,
            blocking_warning=blocking_warning,
        )
    )


def exact_summary_matches(summary_row: dict[str, str], matrix_row: dict[str, str]) -> bool:
    if not matrix_row:
        return True
    checks = [
        ("symbol", str.upper),
        ("direction", str.lower),
        ("timeframe", str.upper),
        ("target_family", str),
        ("regime_column", str),
        ("regime_value", str),
        ("feature_condition", str),
    ]
    for field, transform in checks:
        expected = normalize_text(matrix_row.get(field))
        if not expected:
            continue
        actual = normalize_text(summary_row.get(field))
        if transform(actual) != transform(expected):
            return False
    expected_horizon = normalize_text(matrix_row.get("target_horizon"))
    if expected_horizon and normalize_text(summary_row.get("horizon")) != expected_horizon:
        return False
    return True


def select_exact_summary_row(summary_rows: list[dict[str, str]], matrix_meta: dict[str, str]) -> dict[str, str] | None:
    for row in summary_rows:
        if exact_summary_matches(row, matrix_meta):
            return row
    return summary_rows[0] if summary_rows else None


def value_with_prefix(row: dict[str, str], cost_profile: str, key: str) -> str:
    if cost_profile == "p90":
        stress_key = f"stress_{key}"
        if row.get(stress_key, "") != "":
            return row.get(stress_key, "")
    return row.get(key, "")


def build_exact_rows(
    *,
    args: argparse.Namespace,
    lookup: dict[tuple[str, str], dict[str, str]],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    exact_dir = Path(args.exact_stress_dir)
    summary_path = exact_dir / EXACT_SUMMARY_FILE
    report_path = exact_dir / EXACT_REPORT_FILE
    matrix_meta = lookup.get(("exact_rule", "p75")) or lookup.get(("exact_rule", "p90")) or first_matrix_row(lookup)
    rows: list[dict[str, Any]] = []

    if not summary_path.exists():
        for baseline_type, cost_profile in EXPECTED_EXACT_ROWS:
            matrix_row = lookup.get((baseline_type, cost_profile)) or matrix_meta
            row = row_base(
                args=args,
                row_type="exact_rule",
                baseline_type=baseline_type,
                cost_profile=cost_profile,
                artifact_status="missing",
                matrix_row=matrix_row,
            )
            add_warning(
                warnings,
                row,
                warning_code="exact_stress_summary_missing",
                severity="error",
                message="candidate_stress_summary.csv was not found.",
                source_path=summary_path,
                blocking_warning=True,
            )
            rows.append(row)
        return rows

    summary_row = select_exact_summary_row(read_csv_rows(summary_path), matrix_meta)
    if summary_row is None:
        for baseline_type, cost_profile in EXPECTED_EXACT_ROWS:
            matrix_row = lookup.get((baseline_type, cost_profile)) or matrix_meta
            row = row_base(
                args=args,
                row_type="exact_rule",
                baseline_type=baseline_type,
                cost_profile=cost_profile,
                artifact_status="missing",
                matrix_row=matrix_row,
            )
            add_warning(
                warnings,
                row,
                warning_code="exact_rule_row_missing",
                severity="error",
                message="candidate_stress_summary.csv did not contain an exact-rule row.",
                source_path=summary_path,
                blocking_warning=True,
            )
            rows.append(row)
        return rows

    for baseline_type, cost_profile in EXPECTED_EXACT_ROWS:
        matrix_row = lookup.get((baseline_type, cost_profile)) or matrix_meta
        row = row_base(
            args=args,
            row_type="exact_rule",
            baseline_type=baseline_type,
            cost_profile=cost_profile,
            artifact_status="available",
            matrix_row=matrix_row,
        )
        row.update(
            {
                "symbol": summary_row.get("symbol") or row["symbol"],
                "direction": summary_row.get("direction") or row["direction"],
                "timeframe": summary_row.get("timeframe") or row["timeframe"],
                "target_horizon": summary_row.get("horizon") or row["target_horizon"],
                "target_family": summary_row.get("target_family") or row["target_family"],
                "regime_column": summary_row.get("regime_column") or row["regime_column"],
                "regime_value": summary_row.get("regime_value") or row["regime_value"],
                "feature_condition": summary_row.get("feature_condition") or row["feature_condition"],
                "baseline_filter": summary_row.get("feature_condition") or row["baseline_filter"],
                "cost_config_path": (
                    summary_row.get("base_cost_config_path")
                    if cost_profile == "p75"
                    else summary_row.get("stress_cost_config_path")
                )
                or row["cost_config_path"],
                "source_artifact_type": "candidate_stress_summary",
                "source_output_dir": str(exact_dir),
                "source_csv": str(summary_path),
                "source_report": str(report_path) if report_path.exists() else "",
                "trades": value_with_prefix(summary_row, cost_profile, "sequential_trades_count"),
                "exact_mean_R": value_with_prefix(summary_row, cost_profile, "mean_R"),
                "exact_profit_factor_R": value_with_prefix(summary_row, cost_profile, "profit_factor_R"),
                "exact_cumulative_R": value_with_prefix(summary_row, cost_profile, "cumulative_R"),
                "exact_max_drawdown_R": value_with_prefix(summary_row, cost_profile, "max_drawdown_R"),
                "monthly_positive_ratio": value_with_prefix(summary_row, cost_profile, "monthly_positive_ratio"),
                "quarterly_positive_ratio": value_with_prefix(summary_row, cost_profile, "quarterly_positive_ratio"),
                "yearly_positive_ratio": value_with_prefix(summary_row, cost_profile, "yearly_positive_ratio"),
                "timeout_rate": value_with_prefix(summary_row, cost_profile, "timeout_rate"),
                "tp_hit_rate": value_with_prefix(summary_row, cost_profile, "tp_hit_rate"),
                "sl_hit_rate": value_with_prefix(summary_row, cost_profile, "sl_hit_rate"),
            }
        )
        rows.append(row)
    return rows


def baseline_source_lookup(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_csv_rows(path)
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (
            str(row.get("baseline_type") or "").strip(),
            str(row.get("cost_profile") or "").strip(),
        )
        if key[0] and key[1] and key not in lookup:
            lookup[key] = row
    return lookup


def baseline_consolidated_artifact(baseline_dir: Path) -> tuple[Path, Path, str]:
    r_multiple_path = baseline_dir / BASELINE_R_MULTIPLE_CONSOLIDATED_FILE
    if r_multiple_path.exists():
        return (
            r_multiple_path,
            baseline_dir / BASELINE_R_MULTIPLE_REPORT_FILE,
            R_MULTIPLE_BASELINE_METRIC_NAMESPACE,
        )
    return (
        baseline_dir / BASELINE_CONSOLIDATED_FILE,
        baseline_dir / BASELINE_REPORT_FILE,
        BASELINE_METRIC_NAMESPACE,
    )


def build_baseline_rows(
    *,
    args: argparse.Namespace,
    lookup: dict[tuple[str, str], dict[str, str]],
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    baseline_dir = Path(args.baseline_consolidated_dir)
    consolidated_path, consolidated_report, baseline_metric_namespace = baseline_consolidated_artifact(baseline_dir)
    matrix_meta = first_matrix_row(lookup)
    rows: list[dict[str, Any]] = []

    if not consolidated_path.exists():
        for baseline_type, cost_profile in EXPECTED_BASELINE_ROWS:
            matrix_row = lookup.get((baseline_type, cost_profile)) or matrix_meta
            row = row_base(
                args=args,
                row_type="baseline",
                baseline_type=baseline_type,
                cost_profile=cost_profile,
                artifact_status="missing",
                matrix_row=matrix_row,
            )
            add_warning(
                warnings,
                row,
                warning_code="baseline_consolidated_missing",
                severity="error",
                message=(
                    "No supported baseline consolidated artifact was found. Expected either "
                    f"{BASELINE_R_MULTIPLE_CONSOLIDATED_FILE} or {BASELINE_CONSOLIDATED_FILE}."
                ),
                source_path=consolidated_path,
                blocking_warning=True,
            )
            rows.append(row)
        return rows

    source_rows = baseline_source_lookup(consolidated_path)
    for baseline_type, cost_profile in EXPECTED_BASELINE_ROWS:
        matrix_row = lookup.get((baseline_type, cost_profile)) or matrix_meta
        source_row = source_rows.get((baseline_type, cost_profile))
        if source_row is None:
            row = row_base(
                args=args,
                row_type="baseline",
                baseline_type=baseline_type,
                cost_profile=cost_profile,
                artifact_status="missing",
                matrix_row=matrix_row,
            )
            add_warning(
                warnings,
                row,
                warning_code="baseline_row_missing",
                severity="error",
                message="The baseline consolidated artifact did not contain this expected row.",
                source_path=consolidated_path,
                blocking_warning=True,
            )
            rows.append(row)
            continue

        status = str(source_row.get("artifact_status") or "unreadable").strip()
        status = status if status in STATUS_VALUES else "unreadable"
        row = row_base(
            args=args,
            row_type="baseline",
            baseline_type=baseline_type,
            cost_profile=cost_profile,
            artifact_status=status,
            matrix_row=matrix_row,
        )
        if baseline_metric_namespace == R_MULTIPLE_BASELINE_METRIC_NAMESPACE:
            row.update(
                {
                    "metric_namespace": source_row.get("metric_namespace") or R_MULTIPLE_BASELINE_METRIC_NAMESPACE,
                    "metric_unit": source_row.get("metric_unit") or R_MULTIPLE_BASELINE_METRIC_UNIT,
                    "metric_comparability_note": R_MULTIPLE_BASELINE_COMPARABILITY_NOTE,
                    "symbol": source_row.get("symbol") or row["symbol"],
                    "direction": source_row.get("direction") or row["direction"],
                    "timeframe": source_row.get("timeframe") or row["timeframe"],
                    "target_horizon": source_row.get("target_horizon") or row["target_horizon"],
                    "target_family": source_row.get("target_family") or row["target_family"],
                    "regime_column": source_row.get("regime_column") or row["regime_column"],
                    "regime_value": source_row.get("regime_value") or row["regime_value"],
                    "feature_condition": source_row.get("exact_feature_condition_metadata") or row["feature_condition"],
                    "baseline_filter": row["baseline_filter"] or source_row.get("condition_to_apply", ""),
                    "cost_config_path": source_row.get("cost_config_path") or row["cost_config_path"],
                    "source_artifact_type": "fixed_candidate_baseline_r_multiple_outputs_consolidated",
                    "source_output_dir": source_row.get("source_output_dir", ""),
                    "source_csv": source_row.get("source_summary_csv") or str(consolidated_path),
                    "source_report": source_row.get("source_report_md")
                    or (str(consolidated_report) if consolidated_report.exists() else ""),
                    "trades": source_row.get("trades", ""),
                    "baseline_mean_R": source_row.get("mean_R", ""),
                    "baseline_profit_factor_R": source_row.get("profit_factor_R", ""),
                    "baseline_cumulative_R": source_row.get("cumulative_R", ""),
                    "baseline_max_drawdown_R": source_row.get("max_drawdown_R", ""),
                    "yearly_positive_ratio": source_row.get("yearly_positive_ratio", ""),
                    "warning_code": source_row.get("warning_code", ""),
                    "blocking_warning": source_row.get("blocking_warning") or "false",
                }
            )
        else:
            row.update(
                {
                    "symbol": source_row.get("symbol") or row["symbol"],
                    "direction": source_row.get("direction") or row["direction"],
                    "feature_condition": source_row.get("combination_key") or row["feature_condition"],
                    "baseline_filter": row["baseline_filter"] or source_row.get("baseline_key", ""),
                    "cost_config_path": source_row.get("cost_config_path") or row["cost_config_path"],
                    "source_artifact_type": "fixed_candidate_baseline_outputs_consolidated",
                    "source_output_dir": source_row.get("source_output_dir", ""),
                    "source_csv": source_row.get("source_csv") or str(consolidated_path),
                    "source_report": source_row.get("source_report")
                    or (str(consolidated_report) if consolidated_report.exists() else ""),
                    "trades": source_row.get("baseline_trades_count") or source_row.get("trades_count", ""),
                    "mean_return": source_row.get("baseline_mean_return", ""),
                    "profit_factor": source_row.get("baseline_profit_factor", ""),
                    "cumulative_return": source_row.get("baseline_cumulative_return", ""),
                    "max_drawdown": source_row.get("baseline_max_drawdown", ""),
                    "baseline_mean_return": source_row.get("baseline_mean_return", ""),
                    "baseline_profit_factor": source_row.get("baseline_profit_factor", ""),
                    "baseline_cumulative_return": source_row.get("baseline_cumulative_return", ""),
                    "baseline_max_drawdown": source_row.get("baseline_max_drawdown", ""),
                    "monthly_positive_ratio": source_row.get("baseline_monthly_positive_ratio", ""),
                    "warning_code": source_row.get("warning_code", ""),
                    "blocking_warning": source_row.get("blocking_warning") or "false",
                }
            )
        if status != "available":
            add_warning(
                warnings,
                row,
                warning_code=row["warning_code"] or f"baseline_row_{status}",
                severity="warning" if status in {"missing", "skipped"} else "error",
                message=f"Baseline row status is {status}.",
                source_path=consolidated_path,
                blocking_warning=status in {"missing", "unreadable"},
            )
        rows.append(row)
    return rows


def add_metric_namespace_caveat(warnings: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    namespaces = sorted({str(row.get("metric_namespace") or "") for row in rows if row.get("metric_namespace")})
    if len(namespaces) <= 1:
        return
    warnings.append(
        warning_row(
            warning_code="mixed_metric_namespace_caveat",
            severity="info",
            message=(
                "Comparison table contains both R-multiple exact-rule metrics and net-return baseline metrics. "
                "Values are artifact-preserved and not directly numerically comparable unless normalized."
            ),
            row_type="comparison_table",
            baseline_type="",
            cost_profile="",
            artifact_status="available",
            source_path="",
            blocking_warning=False,
        )
    )


def build_comparison(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    matrix_path = Path(args.matrix_csv)
    lookup = matrix_lookup(matrix_path) if matrix_path.exists() else {}
    warnings: list[dict[str, Any]] = []
    if not matrix_path.exists():
        warnings.append(
            warning_row(
                warning_code="matrix_csv_missing",
                severity="warning",
                message="Matrix CSV was not found; metadata fields may be incomplete.",
                row_type="",
                baseline_type="",
                cost_profile="",
                artifact_status="missing",
                source_path=matrix_path,
                blocking_warning=False,
            )
        )
    rows = [
        *build_exact_rows(args=args, lookup=lookup, warnings=warnings),
        *build_baseline_rows(args=args, lookup=lookup, warnings=warnings),
    ]
    add_metric_namespace_caveat(warnings, rows)
    metadata = {
        "exact_stress_dir": str(args.exact_stress_dir),
        "baseline_consolidated_dir": str(args.baseline_consolidated_dir),
        "matrix_csv": str(args.matrix_csv),
    }
    return rows, warnings, metadata


def status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("artifact_status") or "") for row in rows)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    counts = status_counts(rows)
    exact_rows = [row for row in rows if row.get("row_type") == "exact_rule"]
    baseline_rows = [row for row in rows if row.get("row_type") == "baseline"]
    exact_missing = [row for row in exact_rows if row.get("artifact_status") != "available"]
    baseline_missing = [row for row in baseline_rows if row.get("artifact_status") != "available"]
    namespaces = sorted({str(row.get("metric_namespace") or "") for row in rows if row.get("metric_namespace")})
    mixed_namespaces = len(namespaces) > 1
    if mixed_namespaces:
        metric_caveat = (
            "Metric-unit caveat: exact-rule rows use R-multiple metrics from stress validation, while baseline rows "
            "use net-return metrics from baseline diagnostics. They are not directly numerically comparable unless normalized."
        )
    else:
        metric_caveat = (
            "Metric namespace: exact-rule and baseline rows share the R-multiple/path namespace when R-multiple "
            "baseline consolidated artifacts are supplied. Values are still artifact-preserved for human review only."
        )
    lines = [
        "# Fixed Candidate Baseline Comparison Table",
        "",
        "Research-only artifact fusion. This module does not execute diagnostics, run stress validation, run backtests, run candidate audit, train models, mutate databases, or call live/broker APIs.",
        "",
        "This table preserves artifact values for later human review. It does not rank baselines, does not compare profitability, does not evaluate candidate quality, and does not make a trading decision.",
        "",
        metric_caveat,
        "",
        "Note: p75/p90 baseline diagnostics or stress replays may be identical when row-level spread fields are used before fallback spread from the cost config.",
        "",
        "## Run Context",
        "",
        f"- run_id: `{args.run_id}`",
        f"- exact_stress_dir: `{args.exact_stress_dir}`",
        f"- baseline_consolidated_dir: `{args.baseline_consolidated_dir}`",
        f"- matrix_csv: `{args.matrix_csv}`",
        "",
        "## Counts",
        "",
        f"- comparison_row_count: `{len(rows)}`",
        f"- exact_rule_row_count: `{len(exact_rows)}`",
        f"- baseline_row_count: `{len(baseline_rows)}`",
        f"- available: `{counts.get('available', 0)}`",
        f"- missing: `{counts.get('missing', 0)}`",
        f"- skipped: `{counts.get('skipped', 0)}`",
        f"- unreadable: `{counts.get('unreadable', 0)}`",
        f"- warnings: `{len(warnings)}`",
        f"- metric_namespaces: `{', '.join(namespaces)}`",
        "",
        "## Metric Namespaces",
        "",
        f"- `{EXACT_METRIC_NAMESPACE}` (`{EXACT_METRIC_UNIT}`): stress-validation metrics in R multiples.",
    ]
    if BASELINE_METRIC_NAMESPACE in namespaces:
        lines.append(
            f"- `{BASELINE_METRIC_NAMESPACE}` (`{BASELINE_METRIC_UNIT}`): baseline diagnostic metrics in selected net-return fractions."
        )
    if mixed_namespaces:
        lines.append("- These namespaces are artifact-preserved and should not be numerically compared without a normalization step.")
    else:
        lines.append("- Exact-rule and baseline rows in this table use the same metric namespace.")
    lines.extend(["", "## Exact Rule Rows", ""])
    if exact_missing:
        lines.extend([f"- `{row['cost_profile']}`: {row['artifact_status']}" for row in exact_rows])
    else:
        lines.append("- exact_rule p75/p90 rows are present.")
    lines.extend(["", "## Baseline Rows", ""])
    if baseline_missing:
        lines.extend(
            [
                f"- `{row['baseline_type']}` `{row['cost_profile']}`: {row['artifact_status']}"
                for row in baseline_rows
            ]
        )
    else:
        lines.append("- broad_regime_baseline, single_filter_a, and single_filter_b p75/p90 rows are present.")
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- No child scripts were executed.",
            "- No baseline diagnostics were executed.",
            "- No stress validation was executed.",
            "- No backtests were run.",
            "- No candidate-quality evaluation was performed.",
            "- No profitability conclusion was made.",
            "- No trading decision was made.",
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
) -> None:
    counts = status_counts(rows)
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "exact_stress_dir": str(args.exact_stress_dir),
        "baseline_consolidated_dir": str(args.baseline_consolidated_dir),
        "matrix_csv": str(args.matrix_csv),
        "comparison_row_count": len(rows),
        "exact_rule_row_count": sum(1 for row in rows if row.get("row_type") == "exact_rule"),
        "baseline_row_count": sum(1 for row in rows if row.get("row_type") == "baseline"),
        "available_row_count": counts.get("available", 0),
        "missing_row_count": counts.get("missing", 0),
        "skipped_row_count": counts.get("skipped", 0),
        "unreadable_row_count": counts.get("unreadable", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "metric_namespaces": sorted(
            {str(row.get("metric_namespace") or "") for row in rows if row.get("metric_namespace")}
        ),
        "mixed_metric_namespaces": len(
            {str(row.get("metric_namespace") or "") for row in rows if row.get("metric_namespace")}
        )
        > 1,
        "no_child_scripts_executed": True,
        "no_backtests_run": True,
        "no_stress_validation_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    output_paths = ensure_outputs_writable(output_dir, args.overwrite)
    rows, warnings, _metadata = build_comparison(args)
    write_csv(output_paths["comparison"], rows, FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(output_paths["report"], args=args, rows=rows, warnings=warnings)
    write_manifest(output_paths["manifest"], args=args, output_dir=output_dir, rows=rows, warnings=warnings)
    return output_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build an artifact-only fixed-candidate baseline comparison table. "
            "No diagnostics, stress validation, backtests, or child scripts are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--exact-stress-dir", type=Path, default=DEFAULT_EXACT_STRESS_DIR)
    parser.add_argument("--baseline-consolidated-dir", type=Path, default=DEFAULT_BASELINE_CONSOLIDATED_DIR)
    parser.add_argument("--matrix-csv", type=Path, default=DEFAULT_MATRIX_CSV)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate baseline comparison table build failed: {exc}")
        return 1
    print("Fixed-candidate baseline comparison table build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
