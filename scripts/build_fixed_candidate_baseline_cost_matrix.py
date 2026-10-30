"""Build a fixed-candidate baseline/cost matrix from existing artifacts.

This module is research-only and artifact-only. It normalizes already-produced
fixed-candidate stress artifacts and controlled-expansion plans into a compact
matrix. It does not run child scripts, backtests, baseline diagnostics, data
generation, or trading workflows.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_baseline_cost_matrix"
DEFAULT_EXACT_STRESS_DIR = (
    BASE_DIR
    / "reports"
    / "regime_candidate_stress"
    / "gbpusd_short_h10_1_5_off_hours_stress_exec_v2"
)
DEFAULT_CANDIDATE_AUDIT_DIR = (
    BASE_DIR
    / "reports"
    / "candidate_audit_pipeline"
    / "gbpusd_short_h10_1_5_off_hours_candidate_audit_exec_v1"
)
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_baseline_cost_matrix"
DEFAULT_FEATURE_CONDITION = (
    "numeric_tercile:close_to_ma_fast_atr_20:high_tercile AND "
    "numeric_tercile:tick_volume_percentile_100:mid_tercile"
)
DEFAULT_FILTER_A = "numeric_tercile:close_to_ma_fast_atr_20:high_tercile"
DEFAULT_FILTER_B = "numeric_tercile:tick_volume_percentile_100:mid_tercile"
DEFAULT_P75_COST_CONFIG = "config/brokers/pepperstone_historical_p75.local.json"
DEFAULT_P90_COST_CONFIG = "config/brokers/pepperstone_historical_p90.local.json"

SUMMARY_FILE = "candidate_stress_summary.csv"
BASELINE_PLAN_FILE = "controlled_rule_expansion_baseline_plan.csv"
COST_PLAN_FILE = "controlled_rule_expansion_cost_sensitivity_plan.csv"

MATRIX_FILE = "fixed_candidate_baseline_cost_matrix.csv"
REPORT_FILE = "fixed_candidate_baseline_cost_matrix_report.md"
WARNINGS_FILE = "fixed_candidate_baseline_cost_matrix_warnings.csv"
MANIFEST_FILE = "fixed_candidate_baseline_cost_matrix_manifest.json"

STATUS_VALUES = {"available", "planned_not_run", "missing", "deferred", "not_applicable"}

FIELDNAMES = [
    "run_id",
    "candidate_id",
    "symbol",
    "direction",
    "timeframe",
    "target_horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "feature_condition",
    "baseline_type",
    "baseline_filter",
    "cost_profile",
    "cost_config_path",
    "tp_atr",
    "sl_atr",
    "same_bar_policy",
    "candidate_scope",
    "artifact_status",
    "artifact_source",
    "planned_source",
    "trade_count",
    "mean_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
    "monthly_positive_ratio",
    "quarterly_positive_ratio",
    "yearly_positive_ratio",
    "timeout_rate",
    "tp_hit_rate",
    "sl_hit_rate",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "baseline_type",
    "cost_profile",
    "artifact_status",
    "source_path",
    "blocking_warning",
]

BASELINE_DEFINITIONS = [
    {
        "baseline_type": "exact_rule",
        "baseline_filter": DEFAULT_FEATURE_CONDITION,
        "plan_item": "",
    },
    {
        "baseline_type": "broad_regime_baseline",
        "baseline_filter": "",
        "plan_item": "broad_regime_baseline",
    },
    {
        "baseline_type": "single_filter_a",
        "baseline_filter": DEFAULT_FILTER_A,
        "plan_item": "single_filter_baseline_a",
    },
    {
        "baseline_type": "single_filter_b",
        "baseline_filter": DEFAULT_FILTER_B,
        "plan_item": "single_filter_baseline_b",
    },
    {
        "baseline_type": "no_feature_off_hours",
        "baseline_filter": "",
        "plan_item": "regime_no_feature_baseline",
    },
]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def bool_text(value: bool) -> str:
    return "true" if value else "false"


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
        "matrix": output_dir / MATRIX_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "manifest": output_dir / MANIFEST_FILE,
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def candidate_id(args: argparse.Namespace) -> str:
    pieces = [
        args.symbol,
        args.direction,
        args.timeframe,
        f"h{args.target_horizon}",
        args.target_family,
        args.regime_column,
        args.regime_value,
    ]
    return "_".join(str(piece).strip().lower().replace(" ", "_") for piece in pieces if str(piece).strip())


def target_candidate(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "symbol": args.symbol,
        "direction": args.direction,
        "timeframe": args.timeframe,
        "target_horizon": args.target_horizon,
        "target_family": args.target_family,
        "regime_column": args.regime_column,
        "regime_value": args.regime_value,
        "tp_atr": args.tp_atr,
        "sl_atr": args.sl_atr,
        "feature_condition": args.feature_condition,
        "baseline_filter_a": args.baseline_filter_a,
        "baseline_filter_b": args.baseline_filter_b,
    }


def resolve_controlled_expansion_dir(args: argparse.Namespace) -> Path | None:
    if args.controlled_expansion_dir:
        return Path(args.controlled_expansion_dir)
    if args.candidate_audit_dir:
        return Path(args.candidate_audit_dir) / "controlled_expansion"
    return None


def exact_summary_row_matches(row: dict[str, str], args: argparse.Namespace) -> bool:
    return (
        normalize_text(row.get("symbol")).upper() == normalize_text(args.symbol).upper()
        and normalize_text(row.get("direction")).lower() == normalize_text(args.direction).lower()
        and normalize_text(row.get("timeframe")).upper() == normalize_text(args.timeframe).upper()
        and normalize_text(row.get("horizon")) == normalize_text(args.target_horizon)
        and normalize_text(row.get("target_family")) == normalize_text(args.target_family)
        and normalize_text(row.get("regime_column")) == normalize_text(args.regime_column)
        and normalize_text(row.get("regime_value")) == normalize_text(args.regime_value)
        and normalize_text(row.get("feature_condition")) == normalize_text(args.feature_condition)
    )


def find_exact_summary_row(summary_path: Path, args: argparse.Namespace) -> dict[str, str] | None:
    rows = read_csv_rows(summary_path)
    for row in rows:
        if exact_summary_row_matches(row, args):
            return row
    return None


def plan_rows_by_item(plan_path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv_rows(plan_path)
    return {str(row.get("plan_item") or "").strip(): row for row in rows}


def base_matrix_row(
    *,
    args: argparse.Namespace,
    candidate: str,
    baseline_type: str,
    baseline_filter: str,
    cost_profile: str,
    cost_config_path: str,
    status: str,
) -> dict[str, Any]:
    if status not in STATUS_VALUES:
        raise ValueError(f"Unexpected artifact_status: {status}")
    return {
        "run_id": args.run_id,
        "candidate_id": candidate,
        "symbol": args.symbol,
        "direction": args.direction,
        "timeframe": args.timeframe,
        "target_horizon": args.target_horizon,
        "target_family": args.target_family,
        "regime_column": args.regime_column,
        "regime_value": args.regime_value,
        "feature_condition": args.feature_condition,
        "baseline_type": baseline_type,
        "baseline_filter": baseline_filter,
        "cost_profile": cost_profile,
        "cost_config_path": cost_config_path,
        "tp_atr": args.tp_atr,
        "sl_atr": args.sl_atr,
        "same_bar_policy": "",
        "candidate_scope": "",
        "artifact_status": status,
        "artifact_source": "",
        "planned_source": "",
        "trade_count": "",
        "mean_R": "",
        "profit_factor_R": "",
        "cumulative_R": "",
        "max_drawdown_R": "",
        "monthly_positive_ratio": "",
        "quarterly_positive_ratio": "",
        "yearly_positive_ratio": "",
        "timeout_rate": "",
        "tp_hit_rate": "",
        "sl_hit_rate": "",
        "warning_code": "",
        "blocking_warning": "false",
    }


def exact_available_row(
    *,
    args: argparse.Namespace,
    candidate: str,
    summary_path: Path,
    source_row: dict[str, str],
    cost_profile: str,
) -> dict[str, Any]:
    cost_config_path = (
        source_row.get("base_cost_config_path")
        if cost_profile == "p75"
        else source_row.get("stress_cost_config_path")
    ) or (args.p75_cost_config if cost_profile == "p75" else args.p90_cost_config)
    row = base_matrix_row(
        args=args,
        candidate=candidate,
        baseline_type="exact_rule",
        baseline_filter=args.feature_condition,
        cost_profile=cost_profile,
        cost_config_path=str(cost_config_path),
        status="available",
    )
    metric_prefix = "" if cost_profile == "p75" else "stress_"
    row.update(
        {
            "same_bar_policy": source_row.get("same_bar_policy", ""),
            "candidate_scope": source_row.get("candidate_scope", ""),
            "artifact_source": str(summary_path),
            "trade_count": source_row.get(f"{metric_prefix}sequential_trades_count")
            or source_row.get("sequential_trades_count", ""),
            "mean_R": source_row.get(f"{metric_prefix}mean_R") or source_row.get("mean_R", ""),
            "profit_factor_R": source_row.get(f"{metric_prefix}profit_factor_R")
            or source_row.get("profit_factor_R", ""),
            "cumulative_R": source_row.get(f"{metric_prefix}cumulative_R") or source_row.get("cumulative_R", ""),
            "max_drawdown_R": source_row.get(f"{metric_prefix}max_drawdown_R")
            or source_row.get("max_drawdown_R", ""),
            "monthly_positive_ratio": source_row.get(f"{metric_prefix}monthly_positive_ratio")
            or source_row.get("monthly_positive_ratio", ""),
            "quarterly_positive_ratio": source_row.get(f"{metric_prefix}quarterly_positive_ratio")
            or source_row.get("quarterly_positive_ratio", ""),
            "yearly_positive_ratio": source_row.get(f"{metric_prefix}yearly_positive_ratio")
            or source_row.get("yearly_positive_ratio", ""),
            "timeout_rate": source_row.get("timeout_rate", ""),
            "tp_hit_rate": source_row.get("tp_hit_rate", ""),
            "sl_hit_rate": source_row.get("sl_hit_rate", ""),
        }
    )
    return row


def warning_row(
    *,
    warning_code: str,
    severity: str,
    message: str,
    baseline_type: str = "",
    cost_profile: str = "",
    artifact_status: str = "",
    source_path: Path | str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "baseline_type": baseline_type,
        "cost_profile": cost_profile,
        "artifact_status": artifact_status,
        "source_path": str(source_path),
        "blocking_warning": bool_text(blocking_warning),
    }


def add_status_warning(
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
            baseline_type=str(row.get("baseline_type", "")),
            cost_profile=str(row.get("cost_profile", "")),
            artifact_status=str(row.get("artifact_status", "")),
            source_path=source_path,
            blocking_warning=blocking_warning,
        )
    )


def build_matrix(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Path | None]]:
    exact_stress_dir = Path(args.exact_stress_dir) if args.exact_stress_dir else None
    candidate_audit_dir = Path(args.candidate_audit_dir) if args.candidate_audit_dir else None
    controlled_expansion_dir = resolve_controlled_expansion_dir(args)
    summary_path = exact_stress_dir / SUMMARY_FILE if exact_stress_dir else None
    baseline_plan_path = controlled_expansion_dir / BASELINE_PLAN_FILE if controlled_expansion_dir else None
    cost_plan_path = controlled_expansion_dir / COST_PLAN_FILE if controlled_expansion_dir else None

    paths: dict[str, Path | None] = {
        "exact_stress_dir": exact_stress_dir,
        "candidate_stress_summary": summary_path,
        "candidate_audit_dir": candidate_audit_dir,
        "controlled_expansion_dir": controlled_expansion_dir,
        "baseline_plan": baseline_plan_path,
        "cost_sensitivity_plan": cost_plan_path,
    }
    matrix: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    candidate = candidate_id(args)

    source_row = find_exact_summary_row(summary_path, args) if summary_path else None
    if summary_path and source_row:
        matrix.append(
            exact_available_row(
                args=args,
                candidate=candidate,
                summary_path=summary_path,
                source_row=source_row,
                cost_profile="p75",
            )
        )
        matrix.append(
            exact_available_row(
                args=args,
                candidate=candidate,
                summary_path=summary_path,
                source_row=source_row,
                cost_profile="p90",
            )
        )
    else:
        code = "candidate_stress_summary_missing" if not summary_path or not summary_path.exists() else "exact_rule_row_missing"
        message = (
            "candidate_stress_summary.csv was not found."
            if code == "candidate_stress_summary_missing"
            else "candidate_stress_summary.csv did not contain the requested candidate row."
        )
        for cost_profile, config_path in (("p75", args.p75_cost_config), ("p90", args.p90_cost_config)):
            row = base_matrix_row(
                args=args,
                candidate=candidate,
                baseline_type="exact_rule",
                baseline_filter=args.feature_condition,
                cost_profile=cost_profile,
                cost_config_path=config_path,
                status="missing",
            )
            add_status_warning(
                warnings,
                row,
                warning_code=code,
                severity="error",
                message=message,
                source_path=summary_path or "",
                blocking_warning=True,
            )
            matrix.append(row)

    baseline_plans = plan_rows_by_item(baseline_plan_path) if baseline_plan_path else {}
    for definition in BASELINE_DEFINITIONS[1:]:
        baseline_type = str(definition["baseline_type"])
        plan_item = str(definition["plan_item"])
        baseline_filter = str(definition["baseline_filter"])
        if baseline_type == "single_filter_a":
            baseline_filter = args.baseline_filter_a
        elif baseline_type == "single_filter_b":
            baseline_filter = args.baseline_filter_b

        for cost_profile, config_path in (("p75", args.p75_cost_config), ("p90", args.p90_cost_config)):
            if baseline_type == "no_feature_off_hours":
                row = base_matrix_row(
                    args=args,
                    candidate=candidate,
                    baseline_type=baseline_type,
                    baseline_filter="",
                    cost_profile=cost_profile,
                    cost_config_path=config_path,
                    status="not_applicable",
                )
                if plan_item in baseline_plans and baseline_plan_path:
                    row["planned_source"] = str(baseline_plan_path)
                add_status_warning(
                    warnings,
                    row,
                    warning_code="duplicate_baseline_definition",
                    severity="info",
                    message=(
                        "no_feature_off_hours duplicates broad_regime_baseline for this module "
                        "because no separate implementation artifact is available."
                    ),
                    source_path=baseline_plan_path or "",
                    blocking_warning=False,
                )
                matrix.append(row)
                continue

            if plan_item in baseline_plans:
                row = base_matrix_row(
                    args=args,
                    candidate=candidate,
                    baseline_type=baseline_type,
                    baseline_filter=baseline_filter,
                    cost_profile=cost_profile,
                    cost_config_path=config_path,
                    status="planned_not_run",
                )
                if baseline_plan_path:
                    row["planned_source"] = str(baseline_plan_path)
                add_status_warning(
                    warnings,
                    row,
                    warning_code="baseline_row_planned_not_run",
                    severity="info",
                    message="Controlled expansion plan exists, but this module does not run the baseline.",
                    source_path=baseline_plan_path or "",
                    blocking_warning=False,
                )
            else:
                row = base_matrix_row(
                    args=args,
                    candidate=candidate,
                    baseline_type=baseline_type,
                    baseline_filter=baseline_filter,
                    cost_profile=cost_profile,
                    cost_config_path=config_path,
                    status="missing",
                )
                add_status_warning(
                    warnings,
                    row,
                    warning_code="baseline_row_missing",
                    severity="warning",
                    message="No existing artifact or controlled expansion plan was found for this baseline row.",
                    source_path=baseline_plan_path or "",
                    blocking_warning=False,
                )
            matrix.append(row)

    if baseline_plan_path and not baseline_plan_path.exists():
        warnings.append(
            warning_row(
                warning_code="controlled_expansion_baseline_plan_missing",
                severity="warning",
                message="controlled_rule_expansion_baseline_plan.csv was not found.",
                source_path=baseline_plan_path,
                blocking_warning=False,
            )
        )
    if cost_plan_path and not cost_plan_path.exists():
        warnings.append(
            warning_row(
                warning_code="controlled_expansion_cost_plan_missing",
                severity="warning",
                message="controlled_rule_expansion_cost_sensitivity_plan.csv was not found.",
                source_path=cost_plan_path,
                blocking_warning=False,
            )
        )
    return matrix, warnings, paths


def status_counts(matrix: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("artifact_status") or "") for row in matrix)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    matrix: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    paths: dict[str, Path | None],
) -> None:
    counts = status_counts(matrix)
    exact_rows = [row for row in matrix if row["baseline_type"] == "exact_rule"]
    missing_or_planned = [
        row
        for row in matrix
        if row["artifact_status"] in {"planned_not_run", "missing", "deferred", "not_applicable"}
    ]
    warning_counts = Counter(str(row.get("warning_code") or "unknown") for row in warnings)
    lines = [
        "# Fixed Candidate Baseline/Cost Matrix",
        "",
        "This artifact is research-only and module-only; it is not a pipeline or workflow.",
        "No child scripts were executed. No baseline diagnostics were executed. No backtests were run.",
        "No candidate-quality evaluation, profitability conclusion, or trading decision was made.",
        "",
        "## Target Candidate",
        "",
        f"- Run ID: `{args.run_id}`",
        f"- Candidate ID: `{candidate_id(args)}`",
        f"- Symbol/direction/timeframe: `{args.symbol}` `{args.direction}` `{args.timeframe}`",
        f"- Horizon/target family: `h{args.target_horizon}` `{args.target_family}`",
        f"- Regime: `{args.regime_column}={args.regime_value}`",
        f"- Feature condition: `{args.feature_condition}`",
        "",
        "## Source Artifacts",
        "",
        f"- Exact stress summary: `{paths.get('candidate_stress_summary') or ''}`",
        f"- Baseline expansion plan: `{paths.get('baseline_plan') or ''}`",
        f"- Cost sensitivity plan: `{paths.get('cost_sensitivity_plan') or ''}`",
        "",
        "## Matrix Status Counts",
        "",
        f"- available: {counts.get('available', 0)}",
        f"- planned_not_run: {counts.get('planned_not_run', 0)}",
        f"- missing: {counts.get('missing', 0)}",
        f"- deferred: {counts.get('deferred', 0)}",
        f"- not_applicable: {counts.get('not_applicable', 0)}",
        "",
        "## Exact Rule Availability",
        "",
    ]
    if exact_rows:
        lines.extend(
            [
                (
                    f"- `{row['cost_profile']}`: {row['artifact_status']} "
                    f"from `{row.get('artifact_source') or row.get('planned_source') or ''}`"
                )
                for row in exact_rows
            ]
        )
    else:
        lines.append("- No exact-rule rows were produced.")
    lines.extend(["", "## Missing / Planned / Deferred Rows", ""])
    if missing_or_planned:
        lines.extend(
            [
                (
                    f"- `{row['baseline_type']}` `{row['cost_profile']}`: "
                    f"{row['artifact_status']} ({row.get('warning_code') or 'no warning'})"
                )
                for row in missing_or_planned
            ]
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Warning Summary", ""])
    if warning_counts:
        lines.extend([f"- `{code}`: {count}" for code, count in sorted(warning_counts.items())])
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Manual Follow-Up",
            "",
            (
                "This module emits no heavy commands. Missing baseline rows require a separately reviewed "
                "offline command plan before any manual run."
            ),
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    matrix: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    paths: dict[str, Path | None],
) -> None:
    counts = status_counts(matrix)
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "input_paths": {key: str(value) if value else "" for key, value in paths.items()},
        "target_candidate": target_candidate(args),
        "matrix_row_count": len(matrix),
        "available_row_count": counts.get("available", 0),
        "planned_not_run_row_count": counts.get("planned_not_run", 0),
        "missing_row_count": counts.get("missing", 0),
        "deferred_row_count": counts.get("deferred", 0),
        "not_applicable_row_count": counts.get("not_applicable", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "no_child_scripts_executed": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
        "no_backtests_run": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    output_paths = ensure_outputs_writable(output_dir, args.overwrite)
    matrix, warnings, paths = build_matrix(args)
    write_csv(output_paths["matrix"], matrix, FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(output_paths["report"], args=args, matrix=matrix, warnings=warnings, paths=paths)
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_dir,
        matrix=matrix,
        warnings=warnings,
        paths=paths,
    )
    return output_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a research-only fixed-candidate baseline/cost matrix from existing artifacts. "
            "No child scripts, diagnostics, or backtests are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--exact-stress-dir", type=Path, default=DEFAULT_EXACT_STRESS_DIR)
    parser.add_argument("--candidate-audit-dir", type=Path, default=DEFAULT_CANDIDATE_AUDIT_DIR)
    parser.add_argument("--controlled-expansion-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--direction", default="short")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--target-horizon", default="10")
    parser.add_argument("--target-family", default="preferred_1_5atr_1atr_hit_first")
    parser.add_argument("--regime-column", default="hour_session")
    parser.add_argument("--regime-value", default="Off_hours")
    parser.add_argument("--tp-atr", default="1.5")
    parser.add_argument("--sl-atr", default="1.0")
    parser.add_argument("--feature-condition", default=DEFAULT_FEATURE_CONDITION)
    parser.add_argument("--baseline-filter-a", default=DEFAULT_FILTER_A)
    parser.add_argument("--baseline-filter-b", default=DEFAULT_FILTER_B)
    parser.add_argument("--p75-cost-config", default=DEFAULT_P75_COST_CONFIG)
    parser.add_argument("--p90-cost-config", default=DEFAULT_P90_COST_CONFIG)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate baseline/cost matrix build failed: {exc}")
        return 1
    print("Fixed-candidate baseline/cost matrix build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
