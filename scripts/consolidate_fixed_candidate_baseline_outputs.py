"""Consolidate fixed-candidate baseline diagnostic outputs.

This module reads already-generated fixed-row baseline diagnostic artifacts and
normalizes their availability into one compact output set. It does not execute
baseline diagnostics, backtests, child scripts, or trading workflows.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_baseline_outputs_consolidated"
DEFAULT_BASELINE_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_baseline_run_plan"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_baseline_outputs_consolidated"
DEFAULT_MATRIX_CSV = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_cost_matrix"
    / "gbpusd_short_h10_1_5_off_hours_baseline_cost_matrix_v1"
    / "fixed_candidate_baseline_cost_matrix.csv"
)

DETAIL_FILE = "baseline_diagnostics_detail.csv"
SUMMARY_FILE = "baseline_diagnostics_summary.csv"
SKIPPED_FILE = "skipped_baseline_diagnostics_candidates.csv"
REPORT_FILE = "baseline_diagnostics_report.md"

OUTPUT_CSV = "fixed_candidate_baseline_outputs_consolidated.csv"
OUTPUT_REPORT = "fixed_candidate_baseline_outputs_report.md"
OUTPUT_WARNINGS = "fixed_candidate_baseline_outputs_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_baseline_outputs_manifest.json"

EXPECTED_ROWS = [
    ("broad_regime_baseline", "p75"),
    ("broad_regime_baseline", "p90"),
    ("single_filter_a", "p75"),
    ("single_filter_a", "p90"),
    ("single_filter_b", "p75"),
    ("single_filter_b", "p90"),
]

FIELDNAMES = [
    "run_id",
    "baseline_type",
    "cost_profile",
    "cost_config_path",
    "artifact_status",
    "source_output_dir",
    "source_csv",
    "source_summary_csv",
    "source_skipped_csv",
    "source_report",
    "candidate_scope",
    "symbol",
    "direction",
    "cost_mode",
    "return_mode",
    "baseline_key",
    "combination_key",
    "final_baseline_diagnostic_classification",
    "baseline_trades_count",
    "trades_count",
    "baseline_mean_return",
    "baseline_profit_factor",
    "baseline_cumulative_return",
    "baseline_max_drawdown",
    "baseline_monthly_positive_ratio",
    "baseline_top_5_percent_trades_contribution_pct",
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


def infer_cost_profile_from_path(path: Path) -> str:
    for part in reversed(path.parts):
        match = re.search(r"(?:^|_)(p75|p90)(?:_|$)", part.lower())
        if match:
            return match.group(1)
    return ""


def infer_source_output_dir(path: Path, baseline_type: str, cost_profile: str) -> Path:
    target = f"{baseline_type}_{cost_profile}".lower()
    for parent in [path.parent, *path.parents]:
        if parent.name.lower() == target:
            return parent
    return path.parent


def expected_specs_from_matrix(path: Path) -> list[dict[str, str]]:
    rows = read_csv_rows(path)
    expected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        baseline_type = str(row.get("baseline_type") or "").strip()
        cost_profile = str(row.get("cost_profile") or "").strip()
        if baseline_type in {"broad_regime_baseline", "single_filter_a", "single_filter_b"} and cost_profile in {"p75", "p90"}:
            key = (baseline_type, cost_profile)
            if key not in seen:
                seen.add(key)
                expected.append(
                    {
                        "baseline_type": baseline_type,
                        "cost_profile": cost_profile,
                        "cost_config_path": str(row.get("cost_config_path") or ""),
                    }
                )
    return expected or [
        {"baseline_type": baseline_type, "cost_profile": cost_profile, "cost_config_path": ""}
        for baseline_type, cost_profile in EXPECTED_ROWS
    ]


def expected_rows_from_matrix(path: Path) -> list[tuple[str, str]]:
    return [
        (spec["baseline_type"], spec["cost_profile"])
        for spec in expected_specs_from_matrix(path)
    ]


def discover_detail_paths(roots: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for root in roots:
        if not root or not root.exists():
            continue
        paths.extend(sorted(root.rglob(DETAIL_FILE)))
    return paths


def output_roots(args: argparse.Namespace) -> list[Path]:
    roots: list[Path] = []
    for value in (args.baseline_output_root, args.include_broad_v4_root, args.include_single_v5_root):
        if value:
            path = Path(value)
            if path not in roots:
                roots.append(path)
    return roots


def base_row(args: argparse.Namespace, baseline_type: str, cost_profile: str, status: str) -> dict[str, Any]:
    return {
        "run_id": args.run_id,
        "baseline_type": baseline_type,
        "cost_profile": cost_profile,
        "cost_config_path": "",
        "artifact_status": status,
        "source_output_dir": "",
        "source_csv": "",
        "source_summary_csv": "",
        "source_skipped_csv": "",
        "source_report": "",
        "candidate_scope": "",
        "symbol": "",
        "direction": "",
        "cost_mode": "",
        "return_mode": "",
        "baseline_key": "",
        "combination_key": "",
        "final_baseline_diagnostic_classification": "",
        "baseline_trades_count": "",
        "trades_count": "",
        "baseline_mean_return": "",
        "baseline_profit_factor": "",
        "baseline_cumulative_return": "",
        "baseline_max_drawdown": "",
        "baseline_monthly_positive_ratio": "",
        "baseline_top_5_percent_trades_contribution_pct": "",
        "warning_code": "",
        "blocking_warning": "false",
    }


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


def row_from_detail(args: argparse.Namespace, detail_path: Path, detail_row: dict[str, str]) -> dict[str, Any]:
    baseline_type = str(detail_row.get("baseline_type") or "").strip()
    cost_profile = infer_cost_profile_from_path(detail_path)
    source_output_dir = infer_source_output_dir(detail_path, baseline_type, cost_profile)
    summary_path = detail_path.parent / SUMMARY_FILE
    skipped_path = detail_path.parent / SKIPPED_FILE
    report_path = detail_path.parent / REPORT_FILE
    summary_rows = read_csv_rows(summary_path)
    summary_row = summary_rows[0] if summary_rows else {}
    row = base_row(args, baseline_type, cost_profile, "available")
    row.update(
        {
            "source_output_dir": str(source_output_dir),
            "source_csv": str(detail_path),
            "source_summary_csv": str(summary_path) if summary_path.exists() else "",
            "source_skipped_csv": str(skipped_path) if skipped_path.exists() else "",
            "source_report": str(report_path) if report_path.exists() else "",
            "candidate_scope": detail_row.get("candidate_scope", ""),
            "symbol": detail_row.get("symbol") or summary_row.get("symbol", ""),
            "direction": detail_row.get("direction") or summary_row.get("direction", ""),
            "cost_mode": detail_row.get("cost_mode") or summary_row.get("cost_mode", ""),
            "return_mode": detail_row.get("return_mode") or summary_row.get("return_mode", ""),
            "baseline_key": detail_row.get("baseline_key", ""),
            "combination_key": detail_row.get("combination_key") or summary_row.get("combination_key", ""),
            "final_baseline_diagnostic_classification": summary_row.get("final_baseline_diagnostic_classification", ""),
            "baseline_trades_count": detail_row.get("baseline_trades_count", ""),
            "trades_count": summary_row.get("trades_count", ""),
            "baseline_mean_return": detail_row.get("baseline_mean_return", ""),
            "baseline_profit_factor": detail_row.get("baseline_profit_factor", ""),
            "baseline_cumulative_return": detail_row.get("baseline_cumulative_return", ""),
            "baseline_max_drawdown": detail_row.get("baseline_max_drawdown", ""),
            "baseline_monthly_positive_ratio": detail_row.get("baseline_monthly_positive_ratio", ""),
            "baseline_top_5_percent_trades_contribution_pct": detail_row.get(
                "baseline_top_5_percent_trades_contribution_pct",
                "",
            ),
        }
    )
    return row


def skipped_candidate_by_key(roots: list[Path]) -> dict[tuple[str, str], Path]:
    skipped: dict[tuple[str, str], Path] = {}
    for root in roots:
        if not root or not root.exists():
            continue
        for path in sorted(root.rglob(SKIPPED_FILE)):
            cost_profile = infer_cost_profile_from_path(path)
            baseline_type = ""
            source_dir = path
            for parent in path.parents:
                for expected_type, expected_cost in EXPECTED_ROWS:
                    if parent.name.lower() == f"{expected_type}_{expected_cost}":
                        baseline_type = expected_type
                        source_dir = parent
                        break
                if baseline_type:
                    break
            if baseline_type and cost_profile:
                rows = read_csv_rows(path)
                if rows:
                    skipped[(baseline_type, cost_profile)] = source_dir
    return skipped


def consolidate(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    roots = output_roots(args)
    expected = (
        expected_specs_from_matrix(Path(args.matrix_csv))
        if args.matrix_csv
        else [
            {"baseline_type": baseline_type, "cost_profile": cost_profile, "cost_config_path": ""}
            for baseline_type, cost_profile in EXPECTED_ROWS
        ]
    )
    discovered: dict[tuple[str, str], dict[str, Any]] = {}
    for detail_path in discover_detail_paths(roots):
        detail_rows = read_csv_rows(detail_path)
        if not detail_rows:
            continue
        row = row_from_detail(args, detail_path, detail_rows[0])
        key = (str(row.get("baseline_type") or ""), str(row.get("cost_profile") or ""))
        if key[0] and key[1]:
            discovered[key] = row

    skipped = skipped_candidate_by_key(roots)
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for spec in expected:
        baseline_type = spec["baseline_type"]
        cost_profile = spec["cost_profile"]
        cost_config_path = spec.get("cost_config_path", "")
        key = (baseline_type, cost_profile)
        if key in discovered:
            row = discovered[key]
            row["cost_config_path"] = cost_config_path
            rows.append(row)
            continue
        if key in skipped:
            row = base_row(args, baseline_type, cost_profile, "skipped")
            row["cost_config_path"] = cost_config_path
            row["source_output_dir"] = str(skipped[key])
            row["warning_code"] = "baseline_output_skipped"
            rows.append(row)
            warnings.append(
                warning_row(
                    warning_code="baseline_output_skipped",
                    severity="warning",
                    message="Baseline diagnostic output exists only as a skipped candidate artifact.",
                    baseline_type=baseline_type,
                    cost_profile=cost_profile,
                    source_output_dir=skipped[key],
                )
            )
            continue
        row = base_row(args, baseline_type, cost_profile, "missing")
        row["cost_config_path"] = cost_config_path
        row["warning_code"] = "baseline_output_missing"
        rows.append(row)
        warnings.append(
            warning_row(
                warning_code="baseline_output_missing",
                severity="warning",
                message="No baseline diagnostic output folder was found for this expected row.",
                baseline_type=baseline_type,
                cost_profile=cost_profile,
            )
        )
    metadata = {
        "input_roots": [str(root) for root in roots],
        "expected_row_count": len(expected),
        "discovered_detail_count": len(discovered),
    }
    return rows, warnings, metadata


def status_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("artifact_status") or "") for row in rows)


def write_report(path: Path, *, args: argparse.Namespace, rows: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    counts = status_counts(rows)
    lines = [
        "# Fixed Candidate Baseline Output Consolidation",
        "",
        "This report is artifact consolidation only. It does not execute diagnostics, run backtests, interpret candidate quality, rank baselines, compare profitability, or make trading decisions.",
        "",
        f"- Run ID: `{args.run_id}`",
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
        "| baseline_type | cost_profile | cost_config_path | status | source_output_dir |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {baseline_type} | {cost_profile} | {cost_config_path} | {status} | {source} |".format(
                baseline_type=row.get("baseline_type", ""),
                cost_profile=row.get("cost_profile", ""),
                cost_config_path=str(row.get("cost_config_path", "")).replace("|", "\\|"),
                status=row.get("artifact_status", ""),
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
        "baseline_output_root": str(args.baseline_output_root),
        "matrix_csv": str(args.matrix_csv),
        "input_roots": metadata["input_roots"],
        "consolidated_row_count": len(rows),
        "available_row_count": counts.get("available", 0),
        "missing_row_count": counts.get("missing", 0),
        "skipped_row_count": counts.get("skipped", 0),
        "unreadable_row_count": counts.get("unreadable", 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "no_child_scripts_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_backtests_run": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    output_paths = ensure_outputs_writable(output_dir, args.overwrite)
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
            "Consolidate existing fixed-candidate baseline diagnostic outputs. "
            "No diagnostics, backtests, or child scripts are executed."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--baseline-output-root", type=Path, default=DEFAULT_BASELINE_OUTPUT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--matrix-csv", type=Path, default=DEFAULT_MATRIX_CSV)
    parser.add_argument("--include-broad-v4-root", type=Path)
    parser.add_argument("--include-single-v5-root", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = build_outputs(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Fixed-candidate baseline output consolidation failed: {exc}")
        return 1
    print("Fixed-candidate baseline output consolidation complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
