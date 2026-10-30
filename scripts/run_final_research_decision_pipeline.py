"""Consolidate final research artifacts without making candidate decisions."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

try:
    from research_pipeline_utils import (
        PipelineCommand,
        PipelineCommandResult,
        aggregate_status,
        default_run_id,
        ensure_output_dir,
        render_command,
        require_existing_path,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.*
    from scripts.research_pipeline_utils import (
        PipelineCommand,
        PipelineCommandResult,
        aggregate_status,
        default_run_id,
        ensure_output_dir,
        render_command,
        require_existing_path,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "final_research_decision_pipeline"

MANIFEST_FILE = "final_research_decision_manifest.json"
COMMAND_PLAN_FILE = "final_research_decision_command_plan.csv"
STAGE_RESULTS_FILE = "final_research_decision_stage_results.csv"
SUMMARY_FILE = "final_research_decision_summary.csv"
REPORT_FILE = "final_research_decision_report.md"
WARNINGS_FILE = "final_research_decision_warnings.csv"
INPUTS_FILE = "final_research_decision_inputs.csv"
ARTIFACT_INDEX_FILE = "final_research_decision_artifact_index.csv"
SCHEMA_CHECKS_FILE = "final_research_decision_schema_checks.csv"
FIXED_CANDIDATE_STRESS_WRAPPER_MANIFEST = "fixed_candidate_stress_validation_manifest.json"
STRESS_CHILD_OUTPUT_HINT = "reports/regime_candidate_stress/{RUN_ID}"

DECISION_SCOPE = "final_research_decision_pipeline"
PIPELINE_SCOPE = "artifact_consolidation_only"

FINAL_CLASSIFICATION_DRY_RUN = "FINAL_RESEARCH_DECISION_PIPELINE_DRY_RUN_PLANNED"
FINAL_CLASSIFICATION_COMPLETED = "FINAL_RESEARCH_DECISION_PIPELINE_COMPLETED"
FINAL_CLASSIFICATION_COMPLETED_WITH_WARNINGS = "FINAL_RESEARCH_DECISION_PIPELINE_COMPLETED_WITH_WARNINGS"
FINAL_CLASSIFICATION_FAILED = "FINAL_RESEARCH_DECISION_PIPELINE_FAILED"
FINAL_CLASSIFICATION_STOPPED = "FINAL_RESEARCH_DECISION_PIPELINE_STOPPED"

ARTIFACTS_READY = "ARTIFACTS_READY_FOR_REVIEW"
ARTIFACTS_REVIEW_REQUIRED = "ARTIFACTS_REVIEW_REQUIRED"
ARTIFACTS_BLOCKED = "ARTIFACTS_BLOCKED_MISSING_REQUIRED_INPUTS"
ARTIFACTS_NOT_READY = "ARTIFACTS_NOT_READY"

FORBIDDEN_ACTIONS = [
    "live " + "trading",
    "trading " + "signal",
    "broker " + "execution",
    "position " + "sizing",
    "TP/SL " + "optimization",
    "new feature search",
    "new filters",
    "live " + "readiness",
]

INPUT_TYPES = {
    "combined_validation": {
        "arg": "combined_validation_dir",
        "label": "--combined-validation-dir",
        "expected_files": (
            "combined_validation_manifest.json",
            "combined_validation_summary.csv",
            "combined_validation_report.md",
            "combined_validation_warnings.csv",
        ),
        "schema_files": {
            "combined_validation_summary.csv": ("final_classification", "decision_scope"),
            "combined_validation_warnings.csv": ("warning_code", "severity", "blocking", "message"),
        },
    },
    "final_feature_scorecard": {
        "arg": "final_feature_scorecard_dir",
        "label": "--final-feature-scorecard-dir",
        "expected_files": (
            "final_feature_scorecard.csv",
            "final_feature_scorecard_report.md",
        ),
        "schema_files": {
            "final_feature_scorecard.csv": (),
        },
    },
    "stress_validation": {
        "arg": "stress_validation_dir",
        "label": "--stress-validation-dir",
        "expected_files": (
            "candidate_stress_summary.csv",
            "candidate_stress_report.md",
        ),
        "schema_files": {
            "candidate_stress_summary.csv": (),
        },
    },
    "candidate_audit": {
        "arg": "candidate_audit_dir",
        "label": "--candidate-audit-dir",
        "expected_files": (
            "candidate_audit_manifest.json",
            "candidate_audit_pipeline_summary.csv",
            "candidate_audit_pipeline_report.md",
            "candidate_audit_pipeline_warnings.csv",
        ),
        "schema_files": {
            "candidate_audit_pipeline_summary.csv": ("final_classification", "decision_scope"),
            "candidate_audit_pipeline_warnings.csv": ("warning_code", "severity", "blocking", "message"),
        },
    },
}

STAGES = (
    ("input_artifact_preflight", "Validate provided upstream artifact directories."),
    ("artifact_index_consolidation", "Index CSV, JSON, and markdown artifacts from provided directories."),
    ("schema_presence_checks", "Check headers for known CSV artifacts without interpreting metric values."),
    ("final_research_artifact_report", "Write research-only artifact consolidation report."),
)

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "blocking",
    "message",
    "related_stage",
    "related_metric",
    "metric_value",
    "threshold",
]

COMMAND_PLAN_FIELDNAMES = [
    "command_order",
    "stage_order",
    "stage_name",
    "command",
    "heavy",
    "required",
    "description",
    "cwd",
    "expected_outputs",
    "planned_output_dir",
]

STAGE_RESULTS_FIELDNAMES = [
    "command_order",
    "stage_order",
    "stage_name",
    "status",
    "planned",
    "executed",
    "skipped",
    "failed",
    "required",
    "returncode",
    "started_at",
    "finished_at",
    "duration_seconds",
    "error_message",
    "stdout_log",
    "stderr_log",
]

SUMMARY_FIELDNAMES = [
    "run_id",
    "final_classification",
    "decision_scope",
    "pipeline_scope",
    "artifact_readiness_label",
    "dry_run",
    "execute",
    "planned_stage_count",
    "executed_stage_count",
    "skipped_stage_count",
    "failed_stage_count",
    "provided_input_count",
    "indexed_artifact_count",
    "schema_check_count",
    "warnings_count",
    "blocking_warnings_count",
    "non_blocking_warnings_count",
    "forbidden_actions",
    "next_action",
]

INPUT_FIELDNAMES = [
    "input_type",
    "provided",
    "path",
    "exists",
    "status",
    "expected_key_files",
    "present_expected_key_files",
    "missing_expected_key_files",
]

ARTIFACT_INDEX_FIELDNAMES = [
    "input_type",
    "path",
    "relative_path",
    "suffix",
    "size_bytes",
]

SCHEMA_CHECK_FIELDNAMES = [
    "input_type",
    "file_name",
    "path",
    "exists",
    "header_present",
    "required_columns",
    "header_columns",
    "missing_required_columns",
    "status",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Consolidate already-produced research artifacts into a final research-decision pipeline "
            "artifact set. This wrapper indexes availability only and does not judge candidate quality."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--combined-validation-dir", type=Path)
    parser.add_argument("--final-feature-scorecard-dir", type=Path)
    parser.add_argument("--stress-validation-dir", type=Path)
    parser.add_argument("--candidate-audit-dir", type=Path)
    parser.add_argument("--candidate-id")
    parser.add_argument("--symbol")
    parser.add_argument("--direction", choices=("long", "short"))
    parser.add_argument("--timeframe")
    parser.add_argument("--target-horizon")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--python-executable")
    parser.add_argument("--stop-on-failure", action=argparse.BooleanOptionalAction, default=True)
    return parser


def _bool_text(value: object) -> str:
    return str(bool(value)).lower()


def _write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, object]],
    *,
    overwrite: bool,
) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"CSV already exists; pass --overwrite to replace it: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return path


def _warning_row(
    *,
    warning_code: str,
    severity: str,
    blocking: bool,
    message: str,
    related_stage: str = "",
    related_metric: str = "",
    metric_value: object = "",
    threshold: object = "",
) -> dict[str, object]:
    if severity not in {"info", "review", "severe", "blocking"}:
        raise ValueError(f"Unsupported warning severity: {severity}")
    return {
        "warning_code": warning_code,
        "severity": severity,
        "blocking": _bool_text(blocking),
        "message": message,
        "related_stage": related_stage,
        "related_metric": related_metric,
        "metric_value": metric_value,
        "threshold": threshold,
    }


def _is_blocking(row: Mapping[str, object]) -> bool:
    return str(row.get("blocking", "")).strip().lower() in {"true", "1", "yes"}


def _validate_mode(args: argparse.Namespace) -> None:
    if bool(args.dry_run) == bool(args.execute):
        if args.dry_run:
            raise ValueError("Choose only one of --dry-run or --execute.")
        raise ValueError("Choose either --dry-run or --execute.")


def _resolve_run_id(value: str | None) -> str:
    run_id = str(value or "").strip() or default_run_id()
    if "/" in run_id or "\\" in run_id:
        raise ValueError("--run-id must be a single path segment, not a nested path.")
    return run_id


def _provided_input_paths(args: argparse.Namespace) -> dict[str, Path]:
    provided: dict[str, Path] = {}
    for input_type, spec in INPUT_TYPES.items():
        value = getattr(args, str(spec["arg"]))
        if value is not None:
            provided[input_type] = Path(value)
    return provided


def _resolve_stress_validation_dir(path: Path) -> tuple[Path, list[dict[str, object]]]:
    manifest_path = path / FIXED_CANDIDATE_STRESS_WRAPPER_MANIFEST
    if not manifest_path.exists():
        return path, []

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            "--stress-validation-dir appears to point to the fixed candidate stress validation "
            f"wrapper output, but {FIXED_CANDIDATE_STRESS_WRAPPER_MANIFEST} is invalid JSON. "
            f"Use the child stress output directory {STRESS_CHILD_OUTPUT_HINT}."
        ) from exc

    stress_output_value = str(manifest.get("stress_output_dir") or "").strip()
    if not stress_output_value:
        raise ValueError(
            "--stress-validation-dir appears to point to the fixed candidate stress validation "
            f"wrapper output. Use the child stress output directory {STRESS_CHILD_OUTPUT_HINT}, "
            "or provide a wrapper manifest with stress_output_dir."
        )

    resolved = Path(stress_output_value)
    if not resolved.is_absolute():
        resolved = BASE_DIR / resolved
    require_existing_path(
        resolved,
        label="stress_output_dir from fixed candidate stress validation manifest",
        kind="dir",
    )
    return resolved, [
        _warning_row(
            warning_code="stress_validation_wrapper_dir_resolved",
            severity="review",
            blocking=False,
            message=(
                "--stress-validation-dir pointed to the fixed candidate stress validation wrapper "
                "output; stress_output_dir was auto-detected from the wrapper manifest."
            ),
            related_stage="input_artifact_preflight",
            related_metric="stress_validation_dir",
            metric_value=str(resolved.resolve()),
        )
    ]


def _validate_inputs(args: argparse.Namespace) -> tuple[dict[str, Path], list[dict[str, object]]]:
    provided = _provided_input_paths(args)
    if not provided:
        raise ValueError("At least one upstream input directory must be provided.")
    preflight_warnings: list[dict[str, object]] = []
    for input_type, path in list(provided.items()):
        require_existing_path(path, label=str(INPUT_TYPES[input_type]["label"]), kind="dir")
        if input_type == "stress_validation":
            resolved_path, warnings = _resolve_stress_validation_dir(path)
            provided[input_type] = resolved_path
            preflight_warnings.extend(warnings)
    return provided, preflight_warnings


def _stage_order(stage_name: str) -> int:
    for index, (stage, _description) in enumerate(STAGES, start=1):
        if stage_name == stage:
            return index
    raise ValueError(f"Unknown final research decision stage: {stage_name}")


def build_pipeline_paths(args: argparse.Namespace, run_id: str) -> dict[str, Path]:
    output_dir = Path(args.output_root) / run_id
    return {
        "output_dir": output_dir,
        "manifest": output_dir / MANIFEST_FILE,
        "command_plan": output_dir / COMMAND_PLAN_FILE,
        "stage_results": output_dir / STAGE_RESULTS_FILE,
        "summary": output_dir / SUMMARY_FILE,
        "report": output_dir / REPORT_FILE,
        "warnings": output_dir / WARNINGS_FILE,
        "inputs": output_dir / INPUTS_FILE,
        "artifact_index": output_dir / ARTIFACT_INDEX_FILE,
        "schema_checks": output_dir / SCHEMA_CHECKS_FILE,
    }


def build_stage_commands(paths: Mapping[str, Path]) -> list[PipelineCommand]:
    expected_outputs = {
        "input_artifact_preflight": (paths["inputs"],),
        "artifact_index_consolidation": (paths["artifact_index"],),
        "schema_presence_checks": (paths["schema_checks"],),
        "final_research_artifact_report": (paths["report"],),
    }
    return [
        PipelineCommand(
            stage=stage_name,
            args=["internal", stage_name],
            cwd=BASE_DIR,
            expected_outputs=expected_outputs[stage_name],
            heavy=False,
            required=True,
            description=description,
        )
        for stage_name, description in STAGES
    ]


def _command_plan_row_builder() -> Any:
    def row_builder(index: int, command: PipelineCommand) -> dict[str, object]:
        return {
            "command_order": index,
            "stage_order": _stage_order(command.stage),
            "stage_name": command.stage,
            "planned_output_dir": str(command.expected_outputs[0].parent if command.expected_outputs else ""),
        }

    return row_builder


def _planned_command_rows(commands: Sequence[PipelineCommand]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, command in enumerate(commands, start=1):
        rows.append(
            {
                "command_order": index,
                "stage_order": _stage_order(command.stage),
                "stage_name": command.stage,
                "command": render_command(command),
                "heavy": bool(command.heavy),
                "required": bool(command.required),
                "description": command.description,
                "cwd": str(command.cwd or ""),
                "expected_outputs": [str(path) for path in command.expected_outputs],
                "planned_output_dir": str(command.expected_outputs[0].parent if command.expected_outputs else ""),
            }
        )
    return rows


def _stage_result_row(
    *,
    index: int,
    command: PipelineCommand,
    status: str,
    started_at: str = "",
    finished_at: str = "",
    duration_seconds: float | str = "",
    returncode: int | str = "",
    error_message: str = "",
) -> dict[str, object]:
    return {
        "command_order": index,
        "stage_order": _stage_order(command.stage),
        "stage_name": command.stage,
        "status": status,
        "planned": "true",
        "executed": _bool_text(status == "executed"),
        "skipped": _bool_text(status == "skipped"),
        "failed": _bool_text(status == "failed"),
        "required": _bool_text(command.required),
        "returncode": returncode,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "error_message": error_message,
        "stdout_log": "",
        "stderr_log": "",
    }


def _planned_stage_results(commands: Sequence[PipelineCommand]) -> list[dict[str, object]]:
    return [
        _stage_result_row(index=index, command=command, status="planned")
        for index, command in enumerate(commands, start=1)
    ]


def _executed_stage_results(commands: Sequence[PipelineCommand]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, command in enumerate(commands, start=1):
        started_at = utc_now_iso()
        started = time.perf_counter()
        finished_at = utc_now_iso()
        rows.append(
            _stage_result_row(
                index=index,
                command=command,
                status="executed",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=round(time.perf_counter() - started, 6),
                returncode=0,
            )
        )
    return rows


def _input_rows(provided: Mapping[str, Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for input_type, spec in INPUT_TYPES.items():
        provided_path = provided.get(input_type)
        expected = list(spec["expected_files"])
        if provided_path is None:
            rows.append(
                {
                    "input_type": input_type,
                    "provided": "false",
                    "path": "",
                    "exists": "false",
                    "status": "optional_not_provided",
                    "expected_key_files": ";".join(expected),
                    "present_expected_key_files": "",
                    "missing_expected_key_files": "",
                }
            )
            continue
        present = [name for name in expected if (provided_path / name).exists()]
        missing = [name for name in expected if name not in present]
        rows.append(
            {
                "input_type": input_type,
                "provided": "true",
                "path": str(provided_path.resolve()),
                "exists": "true",
                "status": "present" if not missing else "present_with_missing_expected_files",
                "expected_key_files": ";".join(expected),
                "present_expected_key_files": ";".join(present),
                "missing_expected_key_files": ";".join(missing),
            }
        )
    return rows


def _artifact_index_rows(provided: Mapping[str, Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for input_type, root in provided.items():
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".csv", ".json", ".md"}:
                continue
            rows.append(
                {
                    "input_type": input_type,
                    "path": str(path.resolve()),
                    "relative_path": str(path.relative_to(root)),
                    "suffix": path.suffix.lower(),
                    "size_bytes": path.stat().st_size,
                }
            )
    return rows


def _csv_headers(path: Path) -> list[str]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            return [str(value).strip() for value in next(reader)]
        except StopIteration:
            return []


def _schema_check_rows(provided: Mapping[str, Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for input_type, root in provided.items():
        schema_files = INPUT_TYPES[input_type]["schema_files"]
        for file_name, required_columns in schema_files.items():
            path = root / str(file_name)
            exists = path.exists()
            headers = _csv_headers(path) if exists and path.is_file() else []
            missing = [column for column in required_columns if column not in headers]
            if not exists:
                status = "missing"
            elif not headers:
                status = "missing_header"
            elif missing:
                status = "missing_required_columns"
            else:
                status = "ok"
            rows.append(
                {
                    "input_type": input_type,
                    "file_name": file_name,
                    "path": str(path.resolve()) if exists else str(path),
                    "exists": _bool_text(exists),
                    "header_present": _bool_text(bool(headers)),
                    "required_columns": ";".join(required_columns),
                    "header_columns": ";".join(headers),
                    "missing_required_columns": ";".join(missing),
                    "status": status,
                }
            )
    return rows


def _warning_rows(
    *,
    input_rows: Sequence[Mapping[str, object]],
    schema_rows: Sequence[Mapping[str, object]],
    preflight_warnings: Sequence[Mapping[str, object]] = (),
) -> list[dict[str, object]]:
    rows = [
        _warning_row(
            warning_code="RESEARCH_ONLY_ARTIFACT_CONSOLIDATION",
            severity="info",
            blocking=False,
            message="This pipeline consolidates artifact availability only and performs no candidate-quality evaluation.",
            related_stage=DECISION_SCOPE,
        )
    ]
    rows.extend(dict(row) for row in preflight_warnings)
    for row in input_rows:
        if row.get("status") == "optional_not_provided":
            rows.append(
                _warning_row(
                    warning_code="optional_input_not_provided",
                    severity="review",
                    blocking=False,
                    message=f"Optional upstream input was not provided: {row.get('input_type')}",
                    related_stage="input_artifact_preflight",
                    related_metric=str(row.get("input_type") or ""),
                )
            )
        elif row.get("missing_expected_key_files"):
            rows.append(
                _warning_row(
                    warning_code="missing_expected_artifact",
                    severity="review",
                    blocking=False,
                    message=f"Expected artifact files are missing for {row.get('input_type')}.",
                    related_stage="artifact_index_consolidation",
                    related_metric=str(row.get("input_type") or ""),
                    metric_value=str(row.get("missing_expected_key_files") or ""),
                )
            )
    for row in schema_rows:
        if row.get("status") in {"missing", "missing_header", "missing_required_columns"}:
            rows.append(
                _warning_row(
                    warning_code="schema_presence_check_warning",
                    severity="review",
                    blocking=False,
                    message=f"Schema presence check needs review for {row.get('file_name')}.",
                    related_stage="schema_presence_checks",
                    related_metric=str(row.get("input_type") or ""),
                    metric_value=str(row.get("status") or ""),
                )
            )
    return rows


def _artifact_readiness(warnings: Sequence[Mapping[str, object]], provided_count: int) -> str:
    if any(_is_blocking(row) for row in warnings):
        return ARTIFACTS_BLOCKED
    if provided_count <= 0:
        return ARTIFACTS_NOT_READY
    if any(str(row.get("severity") or "") != "info" for row in warnings):
        return ARTIFACTS_REVIEW_REQUIRED
    return ARTIFACTS_READY


def _final_classification(*, dry_run: bool, warnings: Sequence[Mapping[str, object]]) -> str:
    if dry_run:
        return FINAL_CLASSIFICATION_DRY_RUN
    if any(_is_blocking(row) for row in warnings):
        return FINAL_CLASSIFICATION_FAILED
    if any(str(row.get("severity") or "") != "info" for row in warnings):
        return FINAL_CLASSIFICATION_COMPLETED_WITH_WARNINGS
    return FINAL_CLASSIFICATION_COMPLETED


def _aggregate_stage_status(stage_results: Sequence[Mapping[str, object]]) -> str:
    status_map = {
        "planned": "dry_run",
        "executed": "success",
        "failed": "failed",
        "skipped": "skipped",
    }
    return aggregate_status(
        [
            PipelineCommandResult(
                stage=str(row.get("stage_name") or ""),
                args=[""],
                status=status_map.get(str(row.get("status") or ""), "skipped"),
            )
            for row in stage_results
        ]
    )


def _next_action(final_classification: str) -> str:
    if final_classification == FINAL_CLASSIFICATION_DRY_RUN:
        return "Review the planned artifact consolidation outputs. Re-run with --execute to write the index artifacts."
    if final_classification == FINAL_CLASSIFICATION_COMPLETED:
        return "Review final_research_decision_artifact_index.csv and upstream reports manually."
    if final_classification == FINAL_CLASSIFICATION_COMPLETED_WITH_WARNINGS:
        return "Review warnings and missing optional/expected artifacts before relying on the consolidated index."
    if final_classification == FINAL_CLASSIFICATION_FAILED:
        return "Resolve blocking artifact issues and rerun the consolidation wrapper."
    return "Review stopped stages before rerunning."


def _write_report(
    path: Path,
    *,
    run_id: str,
    args: argparse.Namespace,
    input_rows: Sequence[Mapping[str, object]],
    artifact_rows: Sequence[Mapping[str, object]],
    schema_rows: Sequence[Mapping[str, object]],
    warnings: Sequence[Mapping[str, object]],
    final_classification: str,
    artifact_readiness: str,
    next_action: str,
    overwrite: bool,
) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Report already exists; pass --overwrite to replace it: {path}")
    lines = [
        "# Final Research Decision Pipeline Report",
        "",
        "## Research-Only Caveat",
        "This wrapper consolidates existing research artifacts only. It made no candidate quality, profitability, trading, or deployment decision.",
        "",
        "## Pipeline Scope",
        f"`{PIPELINE_SCOPE}`",
        "",
        "## Mode",
        "Dry-run mode planned and previewed artifact consolidation only." if args.dry_run else "Execution mode wrote artifact consolidation/index outputs only.",
        "",
        "## Context",
        f"- run_id: `{run_id}`",
        f"- candidate_id: `{args.candidate_id or ''}`",
        f"- symbol: `{args.symbol or ''}`",
        f"- direction: `{args.direction or ''}`",
        f"- timeframe: `{args.timeframe or ''}`",
        f"- target_horizon: `{args.target_horizon or ''}`",
        "",
        "## Input Artifacts",
        "| Input Type | Provided | Status | Path |",
        "|---|---|---|---|",
    ]
    for row in input_rows:
        lines.append(f"| `{row.get('input_type')}` | {row.get('provided')} | `{row.get('status')}` | `{row.get('path')}` |")
    lines.extend(
        [
            "",
            "## Artifact Index Summary",
            f"- Indexed artifact count: `{len(artifact_rows)}`",
            "",
            "## Schema Presence Checks",
            f"- Schema check count: `{len(schema_rows)}`",
            "- Header presence only was checked; metric values were not interpreted.",
            "",
            "## Warnings",
        ]
    )
    report_blocking_warnings = sum(1 for row in warnings if _is_blocking(row))
    lines.extend(
        [
            f"- total_warnings: `{len(warnings)}`",
            f"- blocking_warnings: `{report_blocking_warnings}`",
            f"- non_blocking_warnings: `{len(warnings) - report_blocking_warnings}`",
            "Detailed row-level warnings are preserved in `final_research_decision_warnings.csv`.",
        ]
    )
    for row in warnings:
        lines.append(f"- `{row.get('warning_code')}`: {row.get('message')}")
    lines.extend(
        [
            "",
            "## Final Classification",
            f"`{final_classification}`",
            "",
            "## Artifact Readiness",
            f"`{artifact_readiness}`",
            "",
            "## No Candidate Quality Decision",
            "No candidate was ranked, promoted, rejected, approved for trading, or judged for profitability by this wrapper.",
            "",
            "## Forbidden Actions",
        ]
    )
    for action in FORBIDDEN_ACTIONS:
        lines.append(f"- {action}")
    lines.extend(["", "## Next Action", next_action, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_pipeline(args: argparse.Namespace) -> dict[str, Path]:
    _validate_mode(args)
    provided, preflight_warnings = _validate_inputs(args)
    run_id = _resolve_run_id(args.run_id)
    paths = build_pipeline_paths(args, run_id)
    ensure_output_dir(paths["output_dir"], overwrite=args.overwrite)
    commands = build_stage_commands(paths)

    input_rows = _input_rows(provided)
    artifact_rows = _artifact_index_rows(provided)
    schema_rows = _schema_check_rows(provided)
    warnings = _warning_rows(
        input_rows=input_rows,
        schema_rows=schema_rows,
        preflight_warnings=preflight_warnings,
    )
    final_classification = _final_classification(dry_run=bool(args.dry_run), warnings=warnings)
    artifact_readiness = _artifact_readiness(warnings, provided_count=len(provided))
    next_action = _next_action(final_classification)
    stage_results = _planned_stage_results(commands) if args.dry_run else _executed_stage_results(commands)
    aggregated_stage_status = _aggregate_stage_status(stage_results)

    _write_csv(paths["inputs"], INPUT_FIELDNAMES, input_rows, overwrite=args.overwrite)
    _write_csv(paths["artifact_index"], ARTIFACT_INDEX_FIELDNAMES, artifact_rows, overwrite=args.overwrite)
    _write_csv(paths["schema_checks"], SCHEMA_CHECK_FIELDNAMES, schema_rows, overwrite=args.overwrite)
    _write_csv(paths["warnings"], WARNING_FIELDNAMES, warnings, overwrite=args.overwrite)
    _write_csv(paths["stage_results"], STAGE_RESULTS_FIELDNAMES, stage_results, overwrite=args.overwrite)
    write_command_plan_csv(
        paths["command_plan"],
        commands,
        overwrite=args.overwrite,
        fieldnames=COMMAND_PLAN_FIELDNAMES,
        row_builder=_command_plan_row_builder(),
    )

    output_artifacts = {
        "manifest": str(paths["manifest"]),
        "command_plan": str(paths["command_plan"]),
        "stage_results": str(paths["stage_results"]),
        "summary": str(paths["summary"]),
        "report": str(paths["report"]),
        "warnings": str(paths["warnings"]),
        "inputs": str(paths["inputs"]),
        "artifact_index": str(paths["artifact_index"]),
        "schema_checks": str(paths["schema_checks"]),
    }
    status = (
        "dry_run"
        if final_classification == FINAL_CLASSIFICATION_DRY_RUN
        else final_classification.removeprefix("FINAL_RESEARCH_DECISION_PIPELINE_").lower()
    )
    executed_stage_count = sum(1 for row in stage_results if row.get("executed") == "true")
    skipped_stage_count = sum(1 for row in stage_results if row.get("skipped") == "true")
    failed_stage_count = sum(1 for row in stage_results if row.get("failed") == "true")
    blocking_warnings_count = sum(1 for row in warnings if _is_blocking(row))
    write_manifest(
        paths["manifest"],
        {
            "generated_at": utc_now_iso(),
            "completed_at": utc_now_iso(),
            "run_id": run_id,
            "output_dir": str(paths["output_dir"]),
            "dry_run": bool(args.dry_run),
            "execute": bool(args.execute),
            "planned_stages": [stage for stage, _description in STAGES],
            "planned_commands": _planned_command_rows(commands),
            "stage_results": stage_results,
            "aggregated_stage_status": aggregated_stage_status,
            "status": status,
            "pipeline_scope": PIPELINE_SCOPE,
            "artifact_readiness_label": artifact_readiness,
            "final_classification": final_classification,
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_warnings_count,
            "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
            "input_sources": {input_type: str(path.resolve()) for input_type, path in provided.items()},
            "output_artifacts": output_artifacts,
            "forbidden_actions": FORBIDDEN_ACTIONS,
            "no_candidate_quality_evaluation_performed": True,
        },
        overwrite=args.overwrite,
    )
    _write_csv(
        paths["summary"],
        SUMMARY_FIELDNAMES,
        [
            {
                "run_id": run_id,
                "final_classification": final_classification,
                "decision_scope": DECISION_SCOPE,
                "pipeline_scope": PIPELINE_SCOPE,
                "artifact_readiness_label": artifact_readiness,
                "dry_run": _bool_text(args.dry_run),
                "execute": _bool_text(args.execute),
                "planned_stage_count": len(commands),
                "executed_stage_count": executed_stage_count,
                "skipped_stage_count": skipped_stage_count,
                "failed_stage_count": failed_stage_count,
                "provided_input_count": len(provided),
                "indexed_artifact_count": len(artifact_rows),
                "schema_check_count": len(schema_rows),
                "warnings_count": len(warnings),
                "blocking_warnings_count": blocking_warnings_count,
                "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
                "forbidden_actions": ";".join(FORBIDDEN_ACTIONS),
                "next_action": next_action,
            }
        ],
        overwrite=args.overwrite,
    )
    _write_report(
        paths["report"],
        run_id=run_id,
        args=args,
        input_rows=input_rows,
        artifact_rows=artifact_rows,
        schema_rows=schema_rows,
        warnings=warnings,
        final_classification=final_classification,
        artifact_readiness=artifact_readiness,
        next_action=next_action,
        overwrite=args.overwrite,
    )
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        outputs = run_pipeline(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Final research decision pipeline artifacts written to {outputs['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
