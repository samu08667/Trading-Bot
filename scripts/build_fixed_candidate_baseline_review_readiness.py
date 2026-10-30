"""Build review-readiness artifacts for the fixed-candidate baseline table.

This module is artifact-only. It reads the already-built comparison table,
classifies which review scopes are ready within one metric namespace, and marks
cross-namespace exact-vs-baseline review as blocked until normalization exists.
It does not run diagnostics, backtests, child scripts, or trading workflows.
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
DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_baseline_review_readiness"
DEFAULT_COMPARISON_DIR = (
    BASE_DIR
    / "reports"
    / "fixed_candidate_baseline_comparison_table"
    / "gbpusd_short_h10_1_5_off_hours_baseline_comparison_table_v2"
)
DEFAULT_COMPARISON_TABLE_CSV = DEFAULT_COMPARISON_DIR / "fixed_candidate_baseline_comparison_table.csv"
DEFAULT_COMPARISON_MANIFEST_JSON = DEFAULT_COMPARISON_DIR / "fixed_candidate_baseline_comparison_manifest.json"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "fixed_candidate_baseline_review_readiness"

OUTPUT_CSV = "fixed_candidate_baseline_review_readiness.csv"
OUTPUT_REPORT = "fixed_candidate_baseline_review_readiness_report.md"
OUTPUT_WARNINGS = "fixed_candidate_baseline_review_readiness_warnings.csv"
OUTPUT_MANIFEST = "fixed_candidate_baseline_review_readiness_manifest.json"

READY_SAME = "ready_same_metric_namespace"
READY_CAVEAT = "ready_with_caveat"
BLOCKED_NORMALIZATION = "blocked_requires_normalization"
UNAVAILABLE = "unavailable_missing_artifacts"
READINESS_STATUSES = {READY_SAME, READY_CAVEAT, BLOCKED_NORMALIZATION, UNAVAILABLE}

READINESS_FIELDNAMES = [
    "run_id",
    "review_scope",
    "source_rows",
    "metric_namespaces_involved",
    "readiness_status",
    "allowed_without_normalization",
    "required_next_artifact",
    "caveat",
    "blocking_warning",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "message",
    "review_scope",
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


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def ensure_outputs_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = {
        "readiness": output_dir / OUTPUT_CSV,
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


def row_key(row: dict[str, str]) -> str:
    return ":".join(
        [
            str(row.get("row_type") or ""),
            str(row.get("baseline_type") or ""),
            str(row.get("cost_profile") or ""),
        ]
    )


def rows_for_baseline(rows: list[dict[str, str]], baseline_type: str) -> list[dict[str, str]]:
    return [row for row in rows if row.get("baseline_type") == baseline_type]


def available_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("artifact_status") == "available"]


def namespaces(rows: list[dict[str, str]]) -> list[str]:
    return sorted({str(row.get("metric_namespace") or "") for row in rows if row.get("metric_namespace")})


def source_rows_text(rows: list[dict[str, str]]) -> str:
    return ";".join(row_key(row) for row in rows)


def warning_row(
    *,
    warning_code: str,
    severity: str,
    message: str,
    review_scope: str,
    blocking_warning: bool = False,
) -> dict[str, Any]:
    return {
        "warning_code": warning_code,
        "severity": severity,
        "message": message,
        "review_scope": review_scope,
        "blocking_warning": bool_text(blocking_warning),
    }


def readiness_row(
    *,
    args: argparse.Namespace,
    review_scope: str,
    rows: list[dict[str, str]],
    readiness_status: str,
    allowed_without_normalization: bool,
    required_next_artifact: str = "",
    caveat: str = "",
    blocking_warning: bool = False,
) -> dict[str, Any]:
    if readiness_status not in READINESS_STATUSES:
        raise ValueError(f"Unexpected readiness_status: {readiness_status}")
    return {
        "run_id": args.run_id,
        "review_scope": review_scope,
        "source_rows": source_rows_text(rows),
        "metric_namespaces_involved": ";".join(namespaces(rows)),
        "readiness_status": readiness_status,
        "allowed_without_normalization": bool_text(allowed_without_normalization),
        "required_next_artifact": required_next_artifact,
        "caveat": caveat,
        "blocking_warning": bool_text(blocking_warning),
    }


def has_complete_pair(rows: list[dict[str, str]], baseline_type: str) -> bool:
    selected = available_rows(rows_for_baseline(rows, baseline_type))
    return {row.get("cost_profile") for row in selected} == {"p75", "p90"}


def same_namespace_ready(rows: list[dict[str, str]]) -> bool:
    selected = available_rows(rows)
    return bool(selected) and len(selected) == len(rows) and len(namespaces(selected)) == 1


def metric_values_for_identity(row: dict[str, str]) -> tuple[str, ...]:
    return (
        str(row.get("trades") or ""),
        str(row.get("mean_return") or row.get("baseline_mean_return") or ""),
        str(row.get("profit_factor") or row.get("baseline_profit_factor") or ""),
        str(row.get("cumulative_return") or row.get("baseline_cumulative_return") or ""),
        str(row.get("max_drawdown") or row.get("baseline_max_drawdown") or ""),
    )


def identical_p75_p90_baseline_pairs(rows: list[dict[str, str]]) -> list[str]:
    identical: list[str] = []
    for baseline_type in ["broad_regime_baseline", "single_filter_a", "single_filter_b"]:
        pair = {row.get("cost_profile"): row for row in available_rows(rows_for_baseline(rows, baseline_type))}
        if {"p75", "p90"}.issubset(pair) and metric_values_for_identity(pair["p75"]) == metric_values_for_identity(pair["p90"]):
            identical.append(baseline_type)
    return identical


def scope_row_or_unavailable(
    *,
    args: argparse.Namespace,
    review_scope: str,
    rows: list[dict[str, str]],
    ready_status: str = READY_SAME,
    allowed: bool = True,
    required_next_artifact: str = "",
    caveat: str = "",
) -> dict[str, Any]:
    if not rows or not same_namespace_ready(rows):
        return readiness_row(
            args=args,
            review_scope=review_scope,
            rows=rows,
            readiness_status=UNAVAILABLE,
            allowed_without_normalization=False,
            required_next_artifact="complete_comparison_table_rows",
            caveat="Required source rows are missing or not available.",
            blocking_warning=True,
        )
    return readiness_row(
        args=args,
        review_scope=review_scope,
        rows=rows,
        readiness_status=ready_status,
        allowed_without_normalization=allowed,
        required_next_artifact=required_next_artifact,
        caveat=caveat,
        blocking_warning=False,
    )


def build_readiness(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    comparison_csv = Path(args.comparison_table_csv)
    comparison_manifest = Path(args.comparison_manifest_json)
    rows = read_csv_rows(comparison_csv)
    manifest = read_json(comparison_manifest)
    warnings: list[dict[str, Any]] = []

    if not comparison_csv.exists():
        warnings.append(
            warning_row(
                warning_code="comparison_table_missing",
                severity="error",
                message="Comparison table CSV was not found.",
                review_scope="all",
                blocking_warning=True,
            )
        )
    if args.comparison_manifest_json and not comparison_manifest.exists():
        warnings.append(
            warning_row(
                warning_code="comparison_manifest_missing",
                severity="warning",
                message="Comparison manifest JSON was not found; CSV contents will be used as the source of truth.",
                review_scope="all",
            )
        )

    exact_rows = rows_for_baseline(rows, "exact_rule")
    baseline_rows = [
        row
        for row in rows
        if row.get("baseline_type") in {"broad_regime_baseline", "single_filter_a", "single_filter_b"}
    ]
    all_namespaces = namespaces(rows)
    if len(all_namespaces) > 1:
        warnings.append(
            warning_row(
                warning_code="mixed_metric_namespace_caveat",
                severity="info",
                message=(
                    "Comparison table contains mixed metric namespaces. Exact-vs-baseline numeric review "
                    "requires a normalized follow-up artifact."
                ),
                review_scope="normalization_required_for_cross_namespace_review",
            )
        )

    readiness: list[dict[str, Any]] = []
    readiness.append(
        scope_row_or_unavailable(
            args=args,
            review_scope="exact_rule_cost_sensitivity_review",
            rows=exact_rows,
            caveat="Exact p75/p90 review is within the R_multiple namespace only.",
        )
    )

    identical_pairs = identical_p75_p90_baseline_pairs(baseline_rows)
    baseline_cost_caveat = ""
    baseline_cost_status = READY_SAME
    if identical_pairs:
        baseline_cost_status = READY_CAVEAT
        baseline_cost_caveat = (
            "p75/p90 baseline rows have identical artifact metrics for "
            + ", ".join(identical_pairs)
            + "; this can occur when row-level spread takes precedence over fallback spread."
        )
        warnings.append(
            warning_row(
                warning_code="baseline_p75_p90_identical_caveat",
                severity="info",
                message=baseline_cost_caveat,
                review_scope="baseline_cost_sensitivity_review",
            )
        )
    readiness.append(
        scope_row_or_unavailable(
            args=args,
            review_scope="baseline_cost_sensitivity_review",
            rows=baseline_rows,
            ready_status=baseline_cost_status,
            caveat=baseline_cost_caveat or "Baseline p75/p90 review is within the net_return namespace only.",
        )
    )

    readiness.append(
        scope_row_or_unavailable(
            args=args,
            review_scope="baseline_context_review",
            rows=baseline_rows,
            caveat="Broad and single-filter baseline rows share the net_return namespace.",
        )
    )

    for review_scope, baseline_type in [
        ("exact_vs_broad_review", "broad_regime_baseline"),
        ("exact_vs_single_filter_a_review", "single_filter_a"),
        ("exact_vs_single_filter_b_review", "single_filter_b"),
    ]:
        selected_rows = exact_rows + rows_for_baseline(rows, baseline_type)
        if not has_complete_pair(rows, "exact_rule") or not has_complete_pair(rows, baseline_type):
            readiness.append(
                readiness_row(
                    args=args,
                    review_scope=review_scope,
                    rows=selected_rows,
                    readiness_status=UNAVAILABLE,
                    allowed_without_normalization=False,
                    required_next_artifact="complete_comparison_table_rows",
                    caveat="Required exact or baseline rows are missing.",
                    blocking_warning=True,
                )
            )
            continue
        readiness.append(
            readiness_row(
                args=args,
                review_scope=review_scope,
                rows=selected_rows,
                readiness_status=BLOCKED_NORMALIZATION,
                allowed_without_normalization=False,
                required_next_artifact="normalized_exact_vs_baseline_metric_table",
                caveat=(
                    "Exact-rule R_multiple metrics and baseline net_return metrics are mixed; "
                    "numeric comparison is blocked until normalization."
                ),
                blocking_warning=False,
            )
        )

    readiness.append(
        readiness_row(
            args=args,
            review_scope="normalization_required_for_cross_namespace_review",
            rows=rows,
            readiness_status=(
                UNAVAILABLE
                if not rows
                else BLOCKED_NORMALIZATION
                if len(all_namespaces) > 1
                else READY_SAME
            ),
            allowed_without_normalization=bool(rows) and len(all_namespaces) <= 1,
            required_next_artifact=(
                "complete_comparison_table_rows"
                if not rows
                else "normalized_exact_vs_baseline_metric_table"
                if len(all_namespaces) > 1
                else ""
            ),
            caveat=(
                "Required comparison table rows are missing."
                if not rows
                else "Cross-namespace exact-vs-baseline review requires normalization before numeric comparison."
                if len(all_namespaces) > 1
                else "All rows share one metric namespace."
            ),
            blocking_warning=False,
        )
    )

    metadata = {
        "comparison_manifest": manifest,
        "comparison_row_count": len(rows),
        "metric_namespaces": all_namespaces,
    }
    return readiness, warnings, metadata


def readiness_counts(readiness: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("readiness_status") or "") for row in readiness)


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    readiness: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    counts = readiness_counts(readiness)
    namespaces = metadata.get("metric_namespaces") or []
    lines = [
        "# Fixed Candidate Baseline Review Readiness",
        "",
        "Artifact-only review-readiness report. This module does not execute diagnostics, run backtests, run stress validation, run candidate audit, train models, mutate databases, or call live/broker APIs.",
        "",
        "No candidate-quality evaluation, profitability conclusion, or baseline ranking was made.",
        "No trading decision was made.",
        "",
        "Exact-vs-baseline numeric comparison is blocked until a normalization artifact exists because exact rows use R_multiple metrics and baseline rows use net_return metrics.",
        "",
        "Baseline-vs-baseline review is possible within the net_return namespace. Exact p75/p90 review is possible within the R_multiple namespace.",
        "",
        "p75/p90 baseline rows may be identical when row-level spread takes precedence over fallback spread from the cost config.",
        "",
        "## Inputs",
        "",
        f"- comparison_table_csv: `{args.comparison_table_csv}`",
        f"- comparison_manifest_json: `{args.comparison_manifest_json}`",
        f"- metric_namespaces: `{', '.join(str(item) for item in namespaces)}`",
        "",
        "## Readiness Counts",
        "",
        f"- {READY_SAME}: `{counts.get(READY_SAME, 0)}`",
        f"- {READY_CAVEAT}: `{counts.get(READY_CAVEAT, 0)}`",
        f"- {BLOCKED_NORMALIZATION}: `{counts.get(BLOCKED_NORMALIZATION, 0)}`",
        f"- {UNAVAILABLE}: `{counts.get(UNAVAILABLE, 0)}`",
        f"- warnings: `{len(warnings)}`",
        "",
        "## Review Scopes",
        "",
        "| review_scope | readiness_status | allowed_without_normalization | caveat |",
        "| --- | --- | --- | --- |",
    ]
    for row in readiness:
        lines.append(
            "| {scope} | {status} | {allowed} | {caveat} |".format(
                scope=row.get("review_scope", ""),
                status=row.get("readiness_status", ""),
                allowed=row.get("allowed_without_normalization", ""),
                caveat=str(row.get("caveat", "")).replace("|", "\\|"),
            )
        )
    lines.extend(
        [
            "",
            "## Normalization Options",
            "",
            "- Build an R-normalized baseline artifact, if path-level TP/SL and risk units are available for baseline rows.",
            "- Build a return-normalized exact-rule artifact, if exact-rule returns can be expressed in the same return fraction namespace.",
            "- Keep cross-namespace review qualitative only until one of those artifacts exists.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    output_dir: Path,
    readiness: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    counts = readiness_counts(readiness)
    manifest = {
        "run_id": args.run_id,
        "generated_at": utc_now_text(),
        "output_dir": str(output_dir),
        "comparison_table_csv": str(args.comparison_table_csv),
        "comparison_manifest_json": str(args.comparison_manifest_json),
        "source_comparison_row_count": metadata.get("comparison_row_count", 0),
        "metric_namespaces": metadata.get("metric_namespaces", []),
        "readiness_row_count": len(readiness),
        "ready_same_metric_namespace_count": counts.get(READY_SAME, 0),
        "ready_with_caveat_count": counts.get(READY_CAVEAT, 0),
        "blocked_requires_normalization_count": counts.get(BLOCKED_NORMALIZATION, 0),
        "unavailable_missing_artifacts_count": counts.get(UNAVAILABLE, 0),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(1 for warning in warnings if warning.get("blocking_warning") == "true"),
        "no_child_scripts_executed": True,
        "no_backtests_run": True,
        "no_stress_validation_executed": True,
        "no_baseline_diagnostics_executed": True,
        "no_candidate_audit_executed": True,
        "no_candidate_quality_evaluation_performed": True,
        "no_trading_decision_performed": True,
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / args.run_id
    output_paths = ensure_outputs_writable(output_dir, args.overwrite)
    readiness, warnings, metadata = build_readiness(args)
    write_csv(output_paths["readiness"], readiness, READINESS_FIELDNAMES)
    write_csv(output_paths["warnings"], warnings, WARNING_FIELDNAMES)
    write_report(output_paths["report"], args=args, readiness=readiness, warnings=warnings, metadata=metadata)
    write_manifest(
        output_paths["manifest"],
        args=args,
        output_dir=output_dir,
        readiness=readiness,
        warnings=warnings,
        metadata=metadata,
    )
    return output_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build artifact-only review-readiness artifacts for a fixed-candidate baseline comparison table. "
            "No diagnostics, backtests, stress validation, or child scripts are executed."
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
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Fixed-candidate baseline review-readiness build failed: {exc}")
        return 1
    print("Fixed-candidate baseline review-readiness build complete.")
    for label, path in outputs.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
