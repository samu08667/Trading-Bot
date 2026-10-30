"""Consolidate fixed-candidate baseline R-multiple stress outputs.

This module reads already-generated fixed-candidate baseline TP/SL/path stress
artifacts and normalizes them into one table. It does not execute stress
validation, baseline diagnostics, backtests, child scripts, or trading
workflows.
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
DEFAULT_ROW_SPECS_RUN_ID = "gbpusd_short_h10_1_5_off_hours_baseline_r_multiple_row_specs_v1"
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_baseline_r_multiple_outputs_consolidated"
DEFAULT_ROW_SPECS_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_r_multiple_row_specs"
    / DEFAULT_ROW_SPECS_RUN_ID
)
DEFAULT_R_MULTIPLE_OUTPUT_ROOT = DEFAULT_ROW_SPECS_DIR / "manual_r_multiple_outputs"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_baseline_r_multiple_outputs_consolidated"

ROW_SPECS_FILE = "fixed_candidate_baseline_r_multiple_row_specs.csv"
SUMMARY_FILE = "candidate_stress_summary.csv"
REPORT_FILE = "candidate_stress_report.md"
BASE_TRADE_LOG_FILE = "trade_log_base.csv"
STRESS_TRADE_LOG_FILE = "trade_log_stress.csv"
WALK_FORWARD_FILE = "walk_forward_validation.csv"

OUTPUT_CSV = "fixed_candidate_baseline_r_multiple_outputs_consolidated.csv"
OUTPUT_REPORT = "fixed_candidate_baseline_r_multiple_outputs_report.md"
OUTPUT_WARNINGS = "fixed_candidate_baseline_r_multiple_outputs_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_baseline_r_multiple_outputs_manifest.json"

BASELINE_TYPES = ("broad_regime_baseline", "single_filter_a", "single_filter_b")
EXPECTED_COST_PROFILES = ("p75", "p90")
ARTIFACT_STATUSES = {"available", "missing", "skipped", "unreadable"}

FIELDNAMES = [
    "run_id",
    "baseline_type",
    "cost_profile",
    "artifact_status",
    "metric_namespace",
    "metric_unit",
    "symbol",
    "direction",
    "timeframe",
    "target_horizon",
    "target_family",
    "regime_column",
    "regime_value",
    "condition_to_apply",
    "exact_feature_condition_metadata",
    "tp_atr",
    "sl_atr",
    "atr_column",
    "same_bar_policy",
    "stress_spread_policy",
    "cost_config_path",
    "stress_cost_config_path",
    "source_output_dir",
    "source_summary_csv",
    "source_report_md",
    "source_trade_csv",
    "trades",
    "mean_R",
    "profit_factor_R",
    "cumulative_R",
    "max_drawdown_R",
    "yearly_positive_ratio",
    "walk_forward_splits",
    "stress_changed_cost_R",
    "mean_cost_R",
    "stress_mean_cost_R",
    "mean_net_R_delta",
    "final_research_label",
    "warning_code",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "baseline_type",
    "cost_profile",
    "source_output_dir",
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
        "consolidated": output_dir / OUTPUT_CSV,
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


def warning_row(
    *,
    warning_code: str,
    severity: str,
    message: str,
    baseline_type: str,
    cost_profile: str,
    source_output_dir: Path | str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "baseline_type": baseline_type,
        "cost_profile": cost_profile,
        "source_output_dir": str(source_output_dir),
        "blocking_warning": bool_text(blocking_warning),
    }


def row_specs_path(row_specs_dir: Path) -> Path:
    return row_specs_dir / ROW_SPECS_FILE


def fallback_output_dir(output_root: Path, row_specs_dir: Path, baseline_type: str) -> Path:
    candidate = output_root / f"{row_specs_dir.name}_{baseline_type}"
    if candidate.exists():
        return candidate
    matches = sorted(
        path
        for path in output_root.glob(f"*{baseline_type}*")
        if path.is_dir() and (path / SUMMARY_FILE).exists()
    )
    return matches[0] if matches else candidate


def expected_specs(args: argparse.Namespace) -> list[dict[str, str]]:
    output_root = Path(args.r_multiple_output_root)
    row_specs_dir = Path(args.row_specs_dir)
    rows = read_csv_rows(row_specs_path(row_specs_dir))
    specs: list[dict[str, str]] = []
    if rows:
        for row in rows:
            baseline_type = str(row.get("baseline_type") or "").strip()
            if baseline_type not in BASELINE_TYPES:
                continue
            expected_dir = str(row.get("expected_output_dir") or "").strip()
            specs.append(
                {
                    "baseline_type": baseline_type,
                    "condition_to_apply": str(row.get("condition_to_apply") or ""),
                    "exact_feature_condition_metadata": str(row.get("exact_feature_condition_metadata") or ""),
                    "p75_cost_config": str(row.get("p75_cost_config") or ""),
                    "p90_cost_config": str(row.get("p90_cost_config") or ""),
                    "expected_output_dir": expected_dir or str(fallback_output_dir(output_root, row_specs_dir, baseline_type)),
                }
            )
    if specs:
        return specs
    return [
        {
            "baseline_type": baseline_type,
            "condition_to_apply": "",
            "exact_feature_condition_metadata": "",
            "p75_cost_config": "",
            "p90_cost_config": "",
            "expected_output_dir": str(fallback_output_dir(output_root, row_specs_dir, baseline_type)),
        }
        for baseline_type in BASELINE_TYPES
    ]


def resolve_output_dir(spec: dict[str, str], output_root: Path, row_specs_dir: Path) -> Path:
    raw_path = str(spec.get("expected_output_dir") or "").strip()
    if raw_path:
        path = Path(raw_path)
        if path.exists():
            return path
        if not path.is_absolute():
            candidate = BASE_DIR / path
            if candidate.exists():
                return candidate
        return path
    return fallback_output_dir(output_root, row_specs_dir, spec["baseline_type"])


def base_row(
    args: argparse.Namespace,
    spec: dict[str, str],
    cost_profile: str,
    status: str,
    source_output_dir: Path | str = "",
) -> dict[str, Any]:
    if status not in ARTIFACT_STATUSES:
        raise ValueError(f"Unexpected artifact_status: {status}")
    return {
        "run_id": args.run_id,
        "baseline_type": spec["baseline_type"],
        "cost_profile": cost_profile,
        "artifact_status": status,
        "metric_namespace": "R_multiple",
        "metric_unit": "R",
        "symbol": "",
        "direction": "",
        "timeframe": "",
        "target_horizon": "",
        "target_family": "",
        "regime_column": "",
        "regime_value": "",
        "condition_to_apply": spec.get("condition_to_apply", ""),
        "exact_feature_condition_metadata": spec.get("exact_feature_condition_metadata", ""),
        "tp_atr": "",
        "sl_atr": "",
        "atr_column": "",
        "same_bar_policy": "",
        "stress_spread_policy": "",
        "cost_config_path": spec.get("p75_cost_config", "") if cost_profile == "p75" else spec.get("p90_cost_config", ""),
        "stress_cost_config_path": spec.get("p90_cost_config", ""),
        "source_output_dir": str(source_output_dir),
        "source_summary_csv": "",
        "source_report_md": "",
        "source_trade_csv": "",
        "trades": "",
        "mean_R": "",
        "profit_factor_R": "",
        "cumulative_R": "",
        "max_drawdown_R": "",
        "yearly_positive_ratio": "",
        "walk_forward_splits": "",
        "stress_changed_cost_R": "",
        "mean_cost_R": "",
        "stress_mean_cost_R": "",
        "mean_net_R_delta": "",
        "final_research_label": "",
        "warning_code": "",
        "blocking_warning": "false",
    }


def walk_forward_split_count(path: Path) -> str:
    rows = read_csv_rows(path)
    return str(len(rows)) if rows else ""


def source_trade_csv(source_output_dir: Path, cost_profile: str) -> str:
    path = source_output_dir / (BASE_TRADE_LOG_FILE if cost_profile == "p75" else STRESS_TRADE_LOG_FILE)
    return str(path) if path.exists() else ""


def summary_value(summary: dict[str, str], cost_profile: str, base_key: str, stress_key: str) -> str:
    return summary.get(base_key, "") if cost_profile == "p75" else summary.get(stress_key, "")


def row_from_summary(
    args: argparse.Namespace,
    spec: dict[str, str],
    *,
    cost_profile: str,
    source_output_dir: Path,
    summary_path: Path,
    summary: dict[str, str],
) -> dict[str, Any]:
    report_path = source_output_dir / REPORT_FILE
    walk_forward_path = source_output_dir / WALK_FORWARD_FILE
    row = base_row(args, spec, cost_profile, "available", source_output_dir)
    row.update(
        {
            "symbol": summary.get("symbol", ""),
            "direction": summary.get("direction", ""),
            "timeframe": summary.get("timeframe", ""),
            "target_horizon": summary.get("horizon", ""),
            "target_family": summary.get("target_family", ""),
            "regime_column": summary.get("regime_column", ""),
            "regime_value": summary.get("regime_value", ""),
            "condition_to_apply": spec.get("condition_to_apply") or summary.get("feature_condition", ""),
            "tp_atr": summary.get("tp_atr", ""),
            "sl_atr": summary.get("sl_atr", ""),
            "atr_column": summary.get("atr_column", ""),
            "same_bar_policy": summary.get("same_bar_policy", ""),
            "stress_spread_policy": summary.get("stress_spread_policy", ""),
            "cost_config_path": (
                summary.get("base_cost_config_path", "") if cost_profile == "p75" else summary.get("stress_cost_config_path", "")
            )
            or row["cost_config_path"],
            "stress_cost_config_path": summary.get("stress_cost_config_path", "") or spec.get("p90_cost_config", ""),
            "source_summary_csv": str(summary_path),
            "source_report_md": str(report_path) if report_path.exists() else "",
            "source_trade_csv": source_trade_csv(source_output_dir, cost_profile),
            "trades": summary_value(summary, cost_profile, "sequential_trades_count", "stress_sequential_trades_count"),
            "mean_R": summary_value(summary, cost_profile, "mean_R", "stress_mean_R"),
            "profit_factor_R": summary_value(summary, cost_profile, "profit_factor_R", "stress_profit_factor_R"),
            "cumulative_R": summary_value(summary, cost_profile, "cumulative_R", "stress_cumulative_R"),
            "max_drawdown_R": summary_value(summary, cost_profile, "max_drawdown_R", "stress_max_drawdown_R"),
            "yearly_positive_ratio": summary.get("yearly_positive_ratio", ""),
            "walk_forward_splits": walk_forward_split_count(walk_forward_path),
            "stress_changed_cost_R": summary.get("stress_changed_cost_R", ""),
            "mean_cost_R": summary.get("mean_cost_R_base", "") if cost_profile == "p75" else summary.get("mean_cost_R_stress", ""),
            "stress_mean_cost_R": summary.get("mean_cost_R_stress", ""),
            "mean_net_R_delta": summary.get("net_R_delta_mean", ""),
            "final_research_label": summary.get("final_research_label", ""),
        }
    )
    return row


def missing_metric_warnings(row: dict[str, Any], source_output_dir: Path) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if row["artifact_status"] != "available":
        return warnings
    if row["cost_profile"] == "p90":
        missing = [
            field
            for field in ("mean_R", "profit_factor_R", "cumulative_R", "max_drawdown_R")
            if not str(row.get(field) or "").strip()
        ]
        if missing:
            row["warning_code"] = "stress_metric_missing"
            warnings.append(
                warning_row(
                    warning_code="stress_metric_missing",
                    severity="warning",
                    message="Stress summary row is missing one or more stress R metric fields: " + ", ".join(missing),
                    baseline_type=str(row.get("baseline_type") or ""),
                    cost_profile=str(row.get("cost_profile") or ""),
                    source_output_dir=source_output_dir,
                )
            )
    return warnings


def rows_for_spec(
    args: argparse.Namespace,
    spec: dict[str, str],
    *,
    output_root: Path,
    row_specs_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_output_dir = resolve_output_dir(spec, output_root, row_specs_dir)
    summary_path = source_output_dir / SUMMARY_FILE
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not source_output_dir.exists() or not summary_path.exists():
        for cost_profile in EXPECTED_COST_PROFILES:
            row = base_row(args, spec, cost_profile, "missing", source_output_dir)
            row["warning_code"] = "r_multiple_output_missing"
            rows.append(row)
            warnings.append(
                warning_row(
                    warning_code="r_multiple_output_missing",
                    severity="warning",
                    message="No R-multiple stress summary was found for this expected baseline output.",
                    baseline_type=spec["baseline_type"],
                    cost_profile=cost_profile,
                    source_output_dir=source_output_dir,
                )
            )
        return rows, warnings

    try:
        summary_rows = read_csv_rows(summary_path)
    except (OSError, csv.Error) as exc:
        for cost_profile in EXPECTED_COST_PROFILES:
            row = base_row(args, spec, cost_profile, "unreadable", source_output_dir)
            row["source_summary_csv"] = str(summary_path)
            row["warning_code"] = "r_multiple_summary_unreadable"
            rows.append(row)
            warnings.append(
                warning_row(
                    warning_code="r_multiple_summary_unreadable",
                    severity="error",
                    message=f"Unable to read R-multiple stress summary: {exc}",
                    baseline_type=spec["baseline_type"],
                    cost_profile=cost_profile,
                    source_output_dir=source_output_dir,
                    blocking_warning=False,
                )
            )
        return rows, warnings

    if not summary_rows:
        for cost_profile in EXPECTED_COST_PROFILES:
            row = base_row(args, spec, cost_profile, "unreadable", source_output_dir)
            row["source_summary_csv"] = str(summary_path)
            row["warning_code"] = "r_multiple_summary_empty"
            rows.append(row)
            warnings.append(
                warning_row(
                    warning_code="r_multiple_summary_empty",
                    severity="warning",
                    message="R-multiple stress summary exists but contains no rows.",
                    baseline_type=spec["baseline_type"],
                    cost_profile=cost_profile,
                    source_output_dir=source_output_dir,
                )
            )
        return rows, warnings

    summary = summary_rows[0]
    for cost_profile in EXPECTED_COST_PROFILES:
        row = row_from_summary(
            args,
            spec,
            cost_profile=cost_profile,
            source_output_dir=source_output_dir,
            summary_path=summary_path,
            summary=summary,
        )
        rows.append(row)
        warnings.extend(missing_metric_warnings(row, source_output_dir))
    return rows, warnings


def consolidate(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    output_root = Path(args.r_multiple_output_root)
    row_specs_dir = Path(args.row_specs_dir)
    specs = expected_specs(args)
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for spec in specs:
        spec_rows, spec_warnings = rows_for_spec(
            args,
            spec,
            output_root=output_root,
            row_specs_dir=row_specs_dir,
        )
        rows.extend(spec_rows)
        warnings.extend(spec_warnings)
    metadata = {
        "r_multiple_output_root": str(output_root),
        "row_specs_dir": str(row_specs_dir),
        "row_specs_csv": str(row_specs_path(row_specs_dir)),
        "expected_baseline_types": [spec["baseline_type"] for spec in specs],
    }
    return rows, warnings, metadata


def status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("artifact_status") or "") for row in rows)


def write_report(path: Path, *, args: argparse.Namespace, rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    counts = status_counts(rows)
    lines = [
        "# Fixed Candidate Baseline R-Multiple Output Consolidation",
        "",
        (
            "This report is artifact consolidation only. It does not execute stress validation, "
            "baseline diagnostics, backtests, child scripts, or trading workflows."
        ),
        "It does not interpret candidate quality, rank baselines, compare profitability, or make trading decisions.",
        (
            "The consolidated rows are same-namespace baseline R-multiple/path artifacts for later review; "
            "this report does not decide whether the exact rule is better than any baseline."
        ),
        "",
        f"- Run ID: `{args.run_id}`",
        f"- R-multiple output root: `{args.r_multiple_output_root}`",
        f"- Row specs dir: `{args.row_specs_dir}`",
        f"- Consolidated rows: `{len(rows)}`",
        f"- Warnings: `{len(warnings)}`",
        "",
        "## Status Counts",
        "",
        f"- available: {counts.get('available', 0)}",
        f"- missing: {counts.get('missing', 0)}",
        f"- skipped: {counts.get('skipped', 0)}",
        f"- unreadable: {counts.get('unreadable', 0)}",
        "",
        "## Rows",
        "",
        "| baseline_type | cost_profile | status | trades | mean_R | profit_factor_R | source_output_dir |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {baseline_type} | {cost_profile} | {status} | {trades} | {mean_R} | {profit_factor_R} | {source} |".format(
                baseline_type=row.get("baseline_type", ""),
                cost_profile=row.get("cost_profile", ""),
                status=row.get("artifact_status", ""),
                trades=row.get("trades", ""),
                mean_R=row.get("mean_R", ""),
                profit_factor_R=row.get("profit_factor_R", ""),
                source=str(row.get("source_output_dir", "")).replace("|", "\\|"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
        "r_multiple_output_root": str(args.r_multiple_output_root),
        "row_specs_dir": str(args.row_specs_dir),
        "row_specs_csv": metadata.get("row_specs_csv", ""),
        "consolidated_row_count": len(rows),
        "available_row_count": counts.get("available", 0),
        "missing_row_count": counts.get("missing", 0),
        "skipped_row_count": counts.get("skipped", 0),
        "unreadable_row_count": counts.get("unreadable", 0),
        "baseline_type_count": len({str(row.get("baseline_type") or "") for row in rows if row.get("baseline_type")}),
        "cost_profile_count": len({str(row.get("cost_profile") or "") for row in rows if row.get("cost_profile")}),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if str(warning.get("blocking_warning")).lower() == "true"),
        "no_child_scripts_executed": True,
        "no_stress_validation_executed": True,
        "no_backtests_run": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    output_paths = ensure_outputs_writable(output_dir, bool(args.overwrite))
    rows, warnings, metadata = consolidate(args)
    write_csv(output_paths["consolidated"], rows, FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(output_paths["report"], args=args, rows=rows, warnings=warnings)
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_dir,
        rows=rows,
        warnings=warnings,
        metadata=metadata,
    )
    return output_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Consolidate existing fixed-candidate baseline R-multiple stress outputs. "
            "No stress validation, backtests, or child scripts are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--r-multiple-output-root", type=Path, default=DEFAULT_R_MULTIPLE_OUTPUT_ROOT)
    parser.add_argument("--row-specs-dir", type=Path, default=DEFAULT_ROW_SPECS_DIR)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate baseline R-multiple output consolidation failed: {exc}")
        return 1
    print("Fixed-candidate baseline R-multiple output consolidation complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
