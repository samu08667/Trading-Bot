"""Consolidate existing ML research artifacts without running ML research."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
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
DEFAULT_REPORTS_ROOT = BASE_DIR / "reports" / "ml_research"
DEFAULT_OUTPUT_ROOT = BASE_DIR / "reports" / "ml_research_pipeline"

MANIFEST_FILE = "ml_research_manifest.json"
COMMAND_PLAN_FILE = "ml_research_command_plan.csv"
STAGE_RESULTS_FILE = "ml_research_stage_results.csv"
SUMMARY_FILE = "ml_research_summary.csv"
REPORT_FILE = "ml_research_report.md"
WARNINGS_FILE = "ml_research_warnings.csv"
INPUTS_FILE = "ml_research_inputs.csv"
ARTIFACT_INVENTORY_FILE = "ml_research_artifact_inventory.csv"
MISSING_ARTIFACTS_FILE = "ml_research_missing_artifacts.csv"
SCHEMA_CHECKS_FILE = "ml_research_schema_checks.csv"

DECISION_SCOPE = "ml_research_pipeline"
PIPELINE_SCOPE = "ml_artifact_consolidation_only"

FINAL_CLASSIFICATION_DRY_RUN = "ML_RESEARCH_PIPELINE_DRY_RUN_PLANNED"
FINAL_CLASSIFICATION_COMPLETED = "ML_RESEARCH_PIPELINE_COMPLETED"
FINAL_CLASSIFICATION_COMPLETED_WITH_WARNINGS = "ML_RESEARCH_PIPELINE_COMPLETED_WITH_WARNINGS"
FINAL_CLASSIFICATION_FAILED = "ML_RESEARCH_PIPELINE_FAILED"
FINAL_CLASSIFICATION_STOPPED = "ML_RESEARCH_PIPELINE_STOPPED"

ARTIFACTS_READY = "ML_ARTIFACTS_READY_FOR_REVIEW"
ARTIFACTS_REVIEW_REQUIRED = "ML_ARTIFACTS_REVIEW_REQUIRED"
ARTIFACTS_BLOCKED = "ML_ARTIFACTS_BLOCKED_MISSING_REQUIRED_INPUTS"
ARTIFACTS_NOT_READY = "ML_ARTIFACTS_NOT_READY"

STANDARD_REPORT_FILES = (
    "correlations.csv",
    "mutual_information.csv",
    "random_forest_importance.csv",
    "permutation_importance.csv",
    "model_metrics.csv",
    "threshold_analysis.csv",
    "feature_summary.csv",
)
TARGET_COMPARISON_FILES = ("target_comparison.csv", "target_comparison_report.md")
PREFERRED_STABILITY_FILES = ("feature_stability.csv", "feature_stability_report.md")
PREFERRED_SHORTLIST_FILES = ("preferred_feature_hypotheses.csv", "preferred_feature_hypotheses_report.md")
PREFERRED_HORIZON_BUILD_FILES = (
    "preferred_horizon_shortlist_manifest.csv",
    "preferred_horizon_shortlist_report.md",
)

KNOWN_SCHEMA_COLUMNS: dict[str, tuple[str, ...]] = {
    "correlations.csv": ("feature",),
    "mutual_information.csv": ("feature",),
    "random_forest_importance.csv": ("feature",),
    "permutation_importance.csv": ("feature",),
    "model_metrics.csv": ("metric", "value"),
    "threshold_analysis.csv": ("threshold",),
    "feature_summary.csv": ("feature",),
    "target_comparison.csv": ("target",),
    "feature_stability.csv": ("feature",),
    "preferred_feature_hypotheses.csv": ("feature",),
    "preferred_horizon_shortlist_manifest.csv": ("run_id",),
}

STAGE_SPECS = (
    ("inventory_existing_reports", "Inventory existing ML research artifacts."),
    ("validate_standard_report_sets", "Check standard ML report file presence and CSV headers."),
    ("validate_target_run_report_sets", "Check existing target-run report file presence and CSV headers."),
    ("validate_target_comparisons", "Check existing target comparison artifacts and CSV headers."),
    ("validate_preferred_stability", "Check existing preferred stability artifacts and CSV headers."),
    ("validate_preferred_shortlists", "Check existing preferred shortlist and build artifacts."),
    ("write_consolidated_status", "Write consolidated research-only status artifacts."),
)

FORBIDDEN_ACTIONS = [
    "live " + "trading",
    "broker " + "execution",
    "order_" + "send",
    "place_" + "order",
    "open_" + "position",
    "close_" + "position",
    "live " + "signals",
    "position " + "sizing",
    "TP/SL " + "optimization",
    "model " + "deployment",
    "live " + "prediction",
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
    "input_root_count",
    "artifact_group_count",
    "inventoried_artifact_count",
    "missing_artifact_count",
    "schema_check_count",
    "warnings_count",
    "blocking_warnings_count",
    "non_blocking_warnings_count",
    "full_inventory_performed",
    "no_model_quality_evaluation_performed",
    "no_candidate_quality_evaluation_performed",
    "no_trading_decision_performed",
    "forbidden_actions",
    "next_action",
]

WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "blocking",
    "message",
    "related_stage",
    "related_artifact",
    "metric_value",
]

INPUT_FIELDNAMES = [
    "input_type",
    "enabled",
    "required",
    "path",
    "exists",
    "artifact_group_count",
    "artifact_count",
    "expected_key_files",
    "notes",
]

ARTIFACT_INVENTORY_FIELDNAMES = [
    "artifact_root_type",
    "artifact_group_type",
    "artifact_group",
    "artifact_group_path",
    "relative_path",
    "suffix",
    "size_bytes",
]

MISSING_ARTIFACT_FIELDNAMES = [
    "artifact_group_type",
    "artifact_group",
    "artifact_group_path",
    "missing_file",
    "required",
    "blocking",
    "notes",
]

SCHEMA_CHECK_FIELDNAMES = [
    "artifact_group_type",
    "artifact_group",
    "csv_path",
    "exists",
    "header_present",
    "required_columns",
    "header_columns",
    "missing_columns",
    "status",
    "notes",
]

ARTIFACT_SUFFIXES = {".csv", ".json", ".md", ".txt"}
REPORT_DIR_RE = re.compile(r"^(?P<symbol>[A-Z0-9]+)_(?P<timeframe>[A-Z0-9]+)_h(?P<horizon>\d+)$")


@dataclass(frozen=True)
class ArtifactGroup:
    group_type: str
    name: str
    path: Path
    expected_files: tuple[str, ...]
    required: bool = False
    root_type: str = "reports_root"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory and validate already-produced ML research artifacts. "
            "Execution mode performs only internal artifact consolidation checks."
        )
    )
    parser.add_argument("--run-id")
    parser.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT)
    parser.add_argument("--direction", choices=("long", "short", "all"), default="all")
    parser.add_argument("--timeframe", default="")
    parser.add_argument("--horizons", nargs="+", type=int)
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--target-family", default="preferred_2atr_1atr_hit_first")
    parser.add_argument("--include-target-runs", action="store_true")
    parser.add_argument("--include-preferred-artifacts", action="store_true")
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
    related_artifact: str = "",
    metric_value: object = "",
) -> dict[str, object]:
    if severity not in {"info", "review", "blocking"}:
        raise ValueError(f"Unsupported warning severity: {severity}")
    return {
        "warning_code": warning_code,
        "severity": severity,
        "blocking": _bool_text(blocking),
        "message": message,
        "related_stage": related_stage,
        "related_artifact": related_artifact,
        "metric_value": metric_value,
    }


def _is_blocking(row: Mapping[str, object]) -> bool:
    return str(row.get("blocking") or "").strip().lower() in {"true", "1", "yes"}


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


def _normalize_symbols(values: Sequence[object] | None) -> set[str]:
    symbols: set[str] = set()
    for value in values or []:
        for token in str(value).split(","):
            symbol = token.strip().upper()
            if symbol:
                symbols.add(symbol)
    return symbols


def _normalize_horizons(values: Sequence[int] | None) -> set[int]:
    horizons = {int(value) for value in values or []}
    if any(value <= 0 for value in horizons):
        raise ValueError("--horizons must contain positive integers.")
    return horizons


def _selected_directions(direction: str) -> list[str]:
    return ["long", "short"] if direction == "all" else [direction]


def _matches_filters(
    path: Path,
    *,
    symbols: set[str],
    timeframe: str,
    horizons: set[int],
) -> bool:
    match = REPORT_DIR_RE.match(path.name)
    if match is None:
        return False
    if symbols and match.group("symbol").upper() not in symbols:
        return False
    if timeframe and match.group("timeframe").upper() != timeframe.upper():
        return False
    if horizons and int(match.group("horizon")) not in horizons:
        return False
    return True


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
        "artifact_inventory": output_dir / ARTIFACT_INVENTORY_FILE,
        "missing_artifacts": output_dir / MISSING_ARTIFACTS_FILE,
        "schema_checks": output_dir / SCHEMA_CHECKS_FILE,
    }


def _stage_order(stage_name: str) -> int:
    for index, (stage, _description) in enumerate(STAGE_SPECS, start=1):
        if stage_name == stage:
            return index
    raise ValueError(f"Unknown ML research pipeline stage: {stage_name}")


def build_stage_commands(paths: Mapping[str, Path]) -> list[PipelineCommand]:
    stage_outputs = {
        "inventory_existing_reports": (paths["inputs"], paths["artifact_inventory"]),
        "validate_standard_report_sets": (paths["missing_artifacts"], paths["schema_checks"]),
        "validate_target_run_report_sets": (paths["missing_artifacts"], paths["schema_checks"]),
        "validate_target_comparisons": (paths["missing_artifacts"], paths["schema_checks"]),
        "validate_preferred_stability": (paths["missing_artifacts"], paths["schema_checks"]),
        "validate_preferred_shortlists": (paths["missing_artifacts"], paths["schema_checks"]),
        "write_consolidated_status": (paths["summary"], paths["report"], paths["warnings"]),
    }
    return [
        PipelineCommand(
            stage=stage_name,
            args=["internal", stage_name],
            cwd=BASE_DIR,
            expected_outputs=stage_outputs[stage_name],
            heavy=False,
            required=True,
            description=description,
        )
        for stage_name, description in STAGE_SPECS
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


def _scan_standard_groups(
    reports_root: Path,
    *,
    directions: Sequence[str],
    symbols: set[str],
    timeframe: str,
    horizons: set[int],
) -> list[ArtifactGroup]:
    groups: list[ArtifactGroup] = []
    seen: set[Path] = set()
    for direction in directions:
        direction_root = reports_root / direction
        if direction_root.exists():
            for path in sorted(direction_root.iterdir()):
                if path.is_dir() and _matches_filters(path, symbols=symbols, timeframe=timeframe, horizons=horizons):
                    seen.add(path.resolve())
                    groups.append(
                        ArtifactGroup(
                            "standard_report_set",
                            f"{direction}/{path.name}",
                            path,
                            STANDARD_REPORT_FILES,
                            required=True,
                        )
                    )
    for path in sorted(reports_root.iterdir()):
        if path.is_dir() and _matches_filters(path, symbols=symbols, timeframe=timeframe, horizons=horizons):
            resolved = path.resolve()
            if resolved not in seen:
                groups.append(
                    ArtifactGroup(
                        "standard_report_set",
                        path.name,
                        path,
                        STANDARD_REPORT_FILES,
                        required=True,
                    )
                )
    return groups


def _scan_target_run_groups(
    reports_root: Path,
    *,
    directions: Sequence[str],
    symbols: set[str],
    timeframe: str,
    horizons: set[int],
) -> list[ArtifactGroup]:
    root = reports_root / "target_runs"
    groups: list[ArtifactGroup] = []
    if not root.exists():
        return groups
    for direction in directions:
        direction_root = root / direction
        if not direction_root.exists():
            continue
        for report_set in sorted(direction_root.iterdir()):
            if not report_set.is_dir() or not _matches_filters(
                report_set,
                symbols=symbols,
                timeframe=timeframe,
                horizons=horizons,
            ):
                continue
            for target_dir in sorted(report_set.iterdir()):
                if target_dir.is_dir():
                    groups.append(
                        ArtifactGroup(
                            "target_run_report_set",
                            f"{direction}/{report_set.name}/{target_dir.name}",
                            target_dir,
                            STANDARD_REPORT_FILES,
                            root_type="target_runs",
                        )
                    )
    return groups


def _scan_target_comparison_groups(
    reports_root: Path,
    *,
    directions: Sequence[str],
    symbols: set[str],
    timeframe: str,
    horizons: set[int],
) -> list[ArtifactGroup]:
    root = reports_root / "target_comparison"
    groups: list[ArtifactGroup] = []
    if not root.exists():
        return groups
    for direction in directions:
        direction_root = root / direction
        if not direction_root.exists():
            continue
        for path in sorted(direction_root.iterdir()):
            if path.is_dir() and _matches_filters(path, symbols=symbols, timeframe=timeframe, horizons=horizons):
                groups.append(
                    ArtifactGroup(
                        "target_comparison",
                        f"{direction}/{path.name}",
                        path,
                        TARGET_COMPARISON_FILES,
                        root_type="target_comparison",
                    )
                )
    return groups


def _scan_leaf_groups(
    root: Path,
    *,
    group_type: str,
    expected_files: tuple[str, ...],
    root_type: str,
    directions: Sequence[str] = (),
    timeframe: str = "",
    horizons: set[int] | None = None,
    target_family: str = "",
) -> list[ArtifactGroup]:
    if not root.exists():
        return []
    groups: list[ArtifactGroup] = []
    for path in sorted(root.rglob("*")):
        if (
            path.is_dir()
            and any((path / file_name).exists() for file_name in expected_files)
            and _preferred_leaf_matches(
                path,
                root=root,
                directions=directions,
                timeframe=timeframe,
                horizons=horizons or set(),
                target_family=target_family,
            )
        ):
            groups.append(
                ArtifactGroup(
                    group_type,
                    str(path.relative_to(root)),
                    path,
                    expected_files,
                    root_type=root_type,
                )
            )
    return groups


def _preferred_leaf_matches(
    path: Path,
    *,
    root: Path,
    directions: Sequence[str],
    timeframe: str,
    horizons: set[int],
    target_family: str,
) -> bool:
    parts = path.relative_to(root).parts
    if parts and parts[0].startswith("preferred_") and target_family and parts[0] != target_family:
        return False
    direction_parts = {part for part in parts if part in {"long", "short"}}
    if directions and direction_parts and direction_parts.isdisjoint(set(directions)):
        return False
    horizon_parts = []
    for part in parts:
        match = re.match(r"^(?P<timeframe>[A-Za-z0-9]+)_h(?P<horizon>\d+)$", part)
        if match is not None:
            horizon_parts.append((match.group("timeframe").upper(), int(match.group("horizon"))))
    if timeframe and horizon_parts and all(item[0] != timeframe.upper() for item in horizon_parts):
        return False
    if horizons and horizon_parts and all(item[1] not in horizons for item in horizon_parts):
        return False
    return True


def discover_artifact_groups(args: argparse.Namespace) -> list[ArtifactGroup]:
    reports_root = Path(args.reports_root)
    directions = _selected_directions(args.direction)
    symbols = _normalize_symbols(args.symbols)
    horizons = _normalize_horizons(args.horizons)
    timeframe = str(args.timeframe or "").strip().upper()

    groups = _scan_standard_groups(
        reports_root,
        directions=directions,
        symbols=symbols,
        timeframe=timeframe,
        horizons=horizons,
    )
    if args.include_target_runs:
        groups.extend(
            _scan_target_run_groups(
                reports_root,
                directions=directions,
                symbols=symbols,
                timeframe=timeframe,
                horizons=horizons,
            )
        )
        groups.extend(
            _scan_target_comparison_groups(
                reports_root,
                directions=directions,
                symbols=symbols,
                timeframe=timeframe,
                horizons=horizons,
            )
        )
    if args.include_preferred_artifacts:
        groups.extend(
            _scan_leaf_groups(
                reports_root / "preferred_target_feature_stability",
                group_type="preferred_stability",
                expected_files=PREFERRED_STABILITY_FILES,
                root_type="preferred_target_feature_stability",
                directions=directions,
                timeframe=timeframe,
                horizons=horizons,
                target_family=str(args.target_family or ""),
            )
        )
        groups.extend(
            _scan_leaf_groups(
                reports_root / "preferred_feature_hypotheses",
                group_type="preferred_shortlist",
                expected_files=PREFERRED_SHORTLIST_FILES,
                root_type="preferred_feature_hypotheses",
                directions=directions,
                timeframe=timeframe,
                horizons=horizons,
                target_family=str(args.target_family or ""),
            )
        )
        groups.extend(
            _scan_leaf_groups(
                reports_root / "preferred_horizon_shortlist_builds",
                group_type="preferred_horizon_shortlist_build",
                expected_files=PREFERRED_HORIZON_BUILD_FILES,
                root_type="preferred_horizon_shortlist_builds",
            )
        )
    return groups


def _artifact_inventory_rows(groups: Sequence[ArtifactGroup]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in groups:
        for path in sorted(group.path.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in ARTIFACT_SUFFIXES:
                continue
            rows.append(
                {
                    "artifact_root_type": group.root_type,
                    "artifact_group_type": group.group_type,
                    "artifact_group": group.name,
                    "artifact_group_path": str(group.path.resolve()),
                    "relative_path": str(path.relative_to(group.path)),
                    "suffix": path.suffix.lower(),
                    "size_bytes": path.stat().st_size,
                }
            )
    return rows


def _missing_artifact_rows(groups: Sequence[ArtifactGroup]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in groups:
        for file_name in group.expected_files:
            if (group.path / file_name).exists():
                continue
            rows.append(
                {
                    "artifact_group_type": group.group_type,
                    "artifact_group": group.name,
                    "artifact_group_path": str(group.path.resolve()),
                    "missing_file": file_name,
                    "required": _bool_text(group.required),
                    "blocking": "false",
                    "notes": "Expected artifact file was not present; availability review required.",
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


def _schema_check_rows(groups: Sequence[ArtifactGroup]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in groups:
        for file_name in group.expected_files:
            if not file_name.endswith(".csv"):
                continue
            path = group.path / file_name
            exists = path.exists()
            headers = _csv_headers(path) if exists and path.is_file() else []
            required_columns = KNOWN_SCHEMA_COLUMNS.get(file_name, ())
            missing = [column for column in required_columns if column not in headers]
            if not exists:
                status = "missing"
            elif not headers:
                status = "missing_header"
            elif missing:
                status = "missing_columns"
            else:
                status = "ok"
            rows.append(
                {
                    "artifact_group_type": group.group_type,
                    "artifact_group": group.name,
                    "csv_path": str(path.resolve()) if exists else str(path),
                    "exists": _bool_text(exists),
                    "header_present": _bool_text(bool(headers)),
                    "required_columns": ";".join(required_columns),
                    "header_columns": ";".join(headers),
                    "missing_columns": ";".join(missing),
                    "status": status,
                    "notes": "Header presence check only; values were not interpreted.",
                }
            )
    return rows


def _input_rows(args: argparse.Namespace, groups: Sequence[ArtifactGroup], artifact_rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    reports_root = Path(args.reports_root)
    root_specs = [
        ("reports_root", True, True, reports_root, STANDARD_REPORT_FILES),
        ("target_runs", bool(args.include_target_runs), False, reports_root / "target_runs", STANDARD_REPORT_FILES),
        (
            "target_comparison",
            bool(args.include_target_runs),
            False,
            reports_root / "target_comparison",
            TARGET_COMPARISON_FILES,
        ),
        (
            "preferred_target_feature_stability",
            bool(args.include_preferred_artifacts),
            False,
            reports_root / "preferred_target_feature_stability",
            PREFERRED_STABILITY_FILES,
        ),
        (
            "preferred_feature_hypotheses",
            bool(args.include_preferred_artifacts),
            False,
            reports_root / "preferred_feature_hypotheses",
            PREFERRED_SHORTLIST_FILES,
        ),
        (
            "preferred_horizon_shortlist_builds",
            bool(args.include_preferred_artifacts),
            False,
            reports_root / "preferred_horizon_shortlist_builds",
            PREFERRED_HORIZON_BUILD_FILES,
        ),
    ]
    rows: list[dict[str, object]] = []
    for input_type, enabled, required, path, expected_files in root_specs:
        matching_groups = [group for group in groups if group.root_type == input_type or input_type == "reports_root" and group.root_type == "reports_root"]
        matching_artifacts = [row for row in artifact_rows if row.get("artifact_root_type") == input_type]
        rows.append(
            {
                "input_type": input_type,
                "enabled": _bool_text(enabled),
                "required": _bool_text(required),
                "path": str(path.resolve()) if path.exists() else str(path),
                "exists": _bool_text(path.exists()),
                "artifact_group_count": len(matching_groups),
                "artifact_count": len(matching_artifacts),
                "expected_key_files": ";".join(expected_files),
                "notes": "disabled" if not enabled else "enabled artifact root",
            }
        )
    return rows


def _warning_rows(
    *,
    args: argparse.Namespace,
    groups: Sequence[ArtifactGroup],
    input_rows: Sequence[Mapping[str, object]],
    missing_rows: Sequence[Mapping[str, object]],
    schema_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    rows = [
        _warning_row(
            warning_code="research_only_artifact_consolidation",
            severity="info",
            blocking=False,
            message="This wrapper inventories existing ML research artifacts only.",
            related_stage=DECISION_SCOPE,
        ),
        _warning_row(
            warning_code="no_quality_or_trading_decision",
            severity="info",
            blocking=False,
            message="No model-quality, candidate-quality, profitability, or trading decision was made.",
            related_stage=DECISION_SCOPE,
        ),
    ]
    standard_groups = [group for group in groups if group.group_type == "standard_report_set"]
    if not standard_groups:
        rows.append(
            _warning_row(
                warning_code="no_standard_report_sets_discovered",
                severity="review",
                blocking=False,
                message="No standard ML report sets were discovered under the reports root.",
                related_stage="validate_standard_report_sets",
                related_artifact=str(args.reports_root),
            )
        )
    for row in input_rows:
        enabled = str(row.get("enabled") or "") == "true"
        required = str(row.get("required") or "") == "true"
        exists = str(row.get("exists") or "") == "true"
        group_count = int(row.get("artifact_group_count") or 0)
        if enabled and not exists and not required:
            rows.append(
                _warning_row(
                    warning_code="optional_artifact_root_missing",
                    severity="review",
                    blocking=False,
                    message=f"Optional artifact root is missing: {row.get('input_type')}",
                    related_stage="inventory_existing_reports",
                    related_artifact=str(row.get("path") or ""),
                )
            )
        elif enabled and exists and not required and group_count == 0:
            rows.append(
                _warning_row(
                    warning_code="optional_artifact_group_not_discovered",
                    severity="review",
                    blocking=False,
                    message=f"Optional artifact root has no discovered groups: {row.get('input_type')}",
                    related_stage="inventory_existing_reports",
                    related_artifact=str(row.get("path") or ""),
                )
            )
    for row in missing_rows:
        rows.append(
            _warning_row(
                warning_code="missing_expected_ml_artifact",
                severity="review",
                blocking=False,
                message=f"Expected ML artifact is missing: {row.get('missing_file')}",
                related_stage="write_consolidated_status",
                related_artifact=str(row.get("artifact_group_path") or ""),
                metric_value=str(row.get("missing_file") or ""),
            )
        )
    for row in schema_rows:
        if row.get("status") != "ok":
            rows.append(
                _warning_row(
                    warning_code="schema_presence_check_warning",
                    severity="review",
                    blocking=False,
                    message=f"CSV header presence check requires review: {row.get('status')}",
                    related_stage="write_consolidated_status",
                    related_artifact=str(row.get("csv_path") or ""),
                    metric_value=str(row.get("status") or ""),
                )
            )
    return rows


def _artifact_readiness(warnings: Sequence[Mapping[str, object]], groups: Sequence[ArtifactGroup]) -> str:
    if any(_is_blocking(row) for row in warnings):
        return ARTIFACTS_BLOCKED
    if not groups:
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
        return "Review the command plan. Re-run with --execute to write inventory and check artifacts."
    if final_classification == FINAL_CLASSIFICATION_COMPLETED:
        return "Review the generated artifact inventory and schema checks manually."
    if final_classification == FINAL_CLASSIFICATION_COMPLETED_WITH_WARNINGS:
        return "Review missing-artifact and schema-check warnings before using the artifact set downstream."
    if final_classification == FINAL_CLASSIFICATION_FAILED:
        return "Resolve blocking input issues and rerun the artifact consolidation wrapper."
    return "Review stopped stages before rerunning."


def _warning_count(warnings: Sequence[Mapping[str, object]], *, blocking: bool | None = None) -> int:
    if blocking is None:
        return len(warnings)
    return sum(1 for row in warnings if _is_blocking(row) is blocking)


def _grouped_warning_lines(warnings: Sequence[Mapping[str, object]]) -> list[str]:
    if not warnings:
        return ["- None."]

    lines = [
        f"- total_warnings: `{_warning_count(warnings)}`",
        f"- blocking_warnings: `{_warning_count(warnings, blocking=True)}`",
        f"- non_blocking_warnings: `{_warning_count(warnings, blocking=False)}`",
    ]
    codes = sorted({str(row.get("warning_code") or "") for row in warnings})
    for code in codes:
        rows = [row for row in warnings if str(row.get("warning_code") or "") == code]
        affected = {str(row.get("related_artifact") or "") for row in rows if str(row.get("related_artifact") or "")}
        blocking_count = _warning_count(rows, blocking=True)
        lines.append(
            f"- `{code}`: `{len(rows)}` total, `{len(affected)}` artifacts/groups affected, "
            f"`{blocking_count}` blocking"
        )
        if code == "missing_expected_ml_artifact":
            missing_files = sorted({str(row.get("metric_value") or "unknown") for row in rows})
            for file_name in missing_files:
                file_rows = [row for row in rows if str(row.get("metric_value") or "unknown") == file_name]
                file_affected = {
                    str(row.get("related_artifact") or "")
                    for row in file_rows
                    if str(row.get("related_artifact") or "")
                }
                lines.append(
                    f"  - missing_file `{file_name}`: `{len(file_rows)}` total, "
                    f"`{len(file_affected)}` groups affected"
                )
        elif code == "schema_presence_check_warning":
            statuses = sorted({str(row.get("metric_value") or "unknown") for row in rows})
            for status in statuses:
                status_rows = [row for row in rows if str(row.get("metric_value") or "unknown") == status]
                lines.append(f"  - status `{status}`: `{len(status_rows)}` total")
    return lines


def _write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    run_id: str,
    groups: Sequence[ArtifactGroup],
    input_rows: Sequence[Mapping[str, object]],
    artifact_rows: Sequence[Mapping[str, object]],
    missing_rows: Sequence[Mapping[str, object]],
    schema_rows: Sequence[Mapping[str, object]],
    warnings: Sequence[Mapping[str, object]],
    final_classification: str,
    artifact_readiness: str,
    next_action: str,
    overwrite: bool,
) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Report already exists; pass --overwrite to replace it: {path}")
    mode_text = (
        "Dry-run mode wrote wrapper planning artifacts only."
        if args.dry_run
        else "Execution mode wrote internal inventory and consolidation artifacts only."
    )
    lines = [
        "# ML Research Pipeline Report",
        "",
        "## Research-Only Caveat",
        (
            "This wrapper consolidates existing ML research artifacts only. "
            "It did not run model training, generate predictions, evaluate profitability, "
            "or make model-quality, candidate-quality, or trading decisions."
        ),
        "",
        "## Pipeline Scope",
        f"`{PIPELINE_SCOPE}`",
        "",
        "## Mode",
        mode_text,
        f"- full_inventory_performed: `{_bool_text(not args.dry_run)}`",
        f"- dry_run_planning_only: `{_bool_text(args.dry_run)}`",
        "",
        "## Inputs",
        f"- run_id: `{run_id}`",
        f"- reports_root: `{args.reports_root}`",
        f"- direction: `{args.direction}`",
        f"- timeframe: `{args.timeframe or ''}`",
        f"- horizons: `{', '.join(str(item) for item in args.horizons or [])}`",
        f"- symbols: `{', '.join(args.symbols or [])}`",
        f"- target_family: `{args.target_family}`",
        f"- include_target_runs: `{_bool_text(args.include_target_runs)}`",
        f"- include_preferred_artifacts: `{_bool_text(args.include_preferred_artifacts)}`",
        "",
        "## Artifact Groups",
        f"- discovered_group_count: `{len(groups)}`",
        f"- inventoried_artifact_count: `{len(artifact_rows)}`",
        f"- missing_artifact_count: `{len(missing_rows)}`",
        f"- schema_check_count: `{len(schema_rows)}`",
        "",
        "## Input Roots",
        "| Input Type | Enabled | Exists | Groups | Artifacts |",
        "|---|---|---|---:|---:|",
    ]
    for row in input_rows:
        lines.append(
            f"| `{row.get('input_type')}` | {row.get('enabled')} | {row.get('exists')} | "
            f"{row.get('artifact_group_count')} | {row.get('artifact_count')} |"
        )
    lines.extend(
        [
            "",
            "## Schema Checks",
            "Only CSV header presence was checked; metric values were not interpreted.",
            "",
            "## Warnings",
            (
                "Missing expected ML artifacts indicate incomplete existing artifact sets, "
                "not a pipeline execution failure."
            ),
        ]
    )
    lines.extend(_grouped_warning_lines(warnings))
    lines.extend(["", "Detailed row-level warnings are preserved in `ml_research_warnings.csv`."])
    lines.extend(
        [
            "",
            "## Explicit Non-Decisions",
            "No model-quality, candidate-quality, profitability, or trading decision was made.",
            "- no_model_quality_evaluation_performed: `true`",
            "- no_candidate_quality_evaluation_performed: `true`",
            "- no_trading_decision_performed: `true`",
            "- no_profitability_evaluation_performed: `true`",
            "",
            "## Final Classification",
            f"`{final_classification}`",
            "",
            "## Artifact Readiness",
            f"`{artifact_readiness}`",
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


def _empty_execute_rows() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    return [], [], [], []


def run_pipeline(args: argparse.Namespace) -> dict[str, Path]:
    _validate_mode(args)
    reports_root = require_existing_path(args.reports_root, label="--reports-root", kind="dir")
    args.reports_root = reports_root
    _normalize_horizons(args.horizons)
    run_id = _resolve_run_id(args.run_id)
    paths = build_pipeline_paths(args, run_id)
    ensure_output_dir(paths["output_dir"], overwrite=args.overwrite)
    commands = build_stage_commands(paths)

    if args.dry_run:
        groups: list[ArtifactGroup] = []
        input_rows, artifact_rows, missing_rows, schema_rows = _empty_execute_rows()
        warnings = [
            _warning_row(
                warning_code="dry_run_only_execution_not_run",
                severity="info",
                blocking=False,
                message="Dry-run mode planned internal consolidation stages only.",
                related_stage=DECISION_SCOPE,
            ),
            _warning_row(
                warning_code="no_quality_or_trading_decision",
                severity="info",
                blocking=False,
                message="No model-quality, candidate-quality, profitability, or trading decision was made.",
                related_stage=DECISION_SCOPE,
            ),
        ]
        stage_results = _planned_stage_results(commands)
    else:
        groups = discover_artifact_groups(args)
        artifact_rows = _artifact_inventory_rows(groups)
        input_rows = _input_rows(args, groups, artifact_rows)
        missing_rows = _missing_artifact_rows(groups)
        schema_rows = _schema_check_rows(groups)
        warnings = _warning_rows(
            args=args,
            groups=groups,
            input_rows=input_rows,
            missing_rows=missing_rows,
            schema_rows=schema_rows,
        )
        stage_results = _executed_stage_results(commands)
        _write_csv(paths["inputs"], INPUT_FIELDNAMES, input_rows, overwrite=args.overwrite)
        _write_csv(paths["artifact_inventory"], ARTIFACT_INVENTORY_FIELDNAMES, artifact_rows, overwrite=args.overwrite)
        _write_csv(paths["missing_artifacts"], MISSING_ARTIFACT_FIELDNAMES, missing_rows, overwrite=args.overwrite)
        _write_csv(paths["schema_checks"], SCHEMA_CHECK_FIELDNAMES, schema_rows, overwrite=args.overwrite)

    final_classification = _final_classification(dry_run=bool(args.dry_run), warnings=warnings)
    artifact_readiness = _artifact_readiness(warnings, groups)
    next_action = _next_action(final_classification)
    aggregated_stage_status = _aggregate_stage_status(stage_results)
    output_artifacts = {
        "manifest": str(paths["manifest"]),
        "command_plan": str(paths["command_plan"]),
        "stage_results": str(paths["stage_results"]),
        "summary": str(paths["summary"]),
        "report": str(paths["report"]),
        "warnings": str(paths["warnings"]),
        "inputs": str(paths["inputs"]),
        "artifact_inventory": str(paths["artifact_inventory"]),
        "missing_artifacts": str(paths["missing_artifacts"]),
        "schema_checks": str(paths["schema_checks"]),
    }

    _write_csv(paths["warnings"], WARNING_FIELDNAMES, warnings, overwrite=args.overwrite)
    _write_csv(paths["stage_results"], STAGE_RESULTS_FIELDNAMES, stage_results, overwrite=args.overwrite)
    write_command_plan_csv(
        paths["command_plan"],
        commands,
        overwrite=args.overwrite,
        fieldnames=COMMAND_PLAN_FIELDNAMES,
        row_builder=_command_plan_row_builder(),
    )
    executed_stage_count = sum(1 for row in stage_results if row.get("executed") == "true")
    skipped_stage_count = sum(1 for row in stage_results if row.get("skipped") == "true")
    failed_stage_count = sum(1 for row in stage_results if row.get("failed") == "true")
    blocking_warnings_count = sum(1 for row in warnings if _is_blocking(row))
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
                "input_root_count": len(input_rows),
                "artifact_group_count": len(groups),
                "inventoried_artifact_count": len(artifact_rows),
                "missing_artifact_count": len(missing_rows),
                "schema_check_count": len(schema_rows),
                "warnings_count": len(warnings),
                "blocking_warnings_count": blocking_warnings_count,
                "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
                "full_inventory_performed": _bool_text(not args.dry_run),
                "no_model_quality_evaluation_performed": "true",
                "no_candidate_quality_evaluation_performed": "true",
                "no_trading_decision_performed": "true",
                "forbidden_actions": ";".join(FORBIDDEN_ACTIONS),
                "next_action": next_action,
            }
        ],
        overwrite=args.overwrite,
    )
    _write_report(
        paths["report"],
        args=args,
        run_id=run_id,
        groups=groups,
        input_rows=input_rows,
        artifact_rows=artifact_rows,
        missing_rows=missing_rows,
        schema_rows=schema_rows,
        warnings=warnings,
        final_classification=final_classification,
        artifact_readiness=artifact_readiness,
        next_action=next_action,
        overwrite=args.overwrite,
    )
    status = (
        "dry_run"
        if final_classification == FINAL_CLASSIFICATION_DRY_RUN
        else final_classification.removeprefix("ML_RESEARCH_PIPELINE_").lower()
    )
    write_manifest(
        paths["manifest"],
        {
            "generated_at": utc_now_iso(),
            "completed_at": utc_now_iso(),
            "run_id": run_id,
            "output_dir": str(paths["output_dir"]),
            "reports_root": str(reports_root.resolve()),
            "target_family": str(args.target_family),
            "python_executable": str(args.python_executable or ""),
            "stop_on_failure": bool(args.stop_on_failure),
            "dry_run": bool(args.dry_run),
            "execute": bool(args.execute),
            "planned_stages": [stage for stage, _description in STAGE_SPECS],
            "planned_commands": _planned_command_rows(commands),
            "stage_results": stage_results,
            "aggregated_stage_status": aggregated_stage_status,
            "status": status,
            "pipeline_scope": PIPELINE_SCOPE,
            "dry_run_planning_only": bool(args.dry_run),
            "full_inventory_performed": not bool(args.dry_run),
            "artifact_readiness_label": artifact_readiness,
            "final_classification": final_classification,
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_warnings_count,
            "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
            "artifact_group_count": len(groups),
            "inventoried_artifact_count": len(artifact_rows),
            "missing_artifact_count": len(missing_rows),
            "schema_check_count": len(schema_rows),
            "output_artifacts": output_artifacts,
            "forbidden_actions": FORBIDDEN_ACTIONS,
            "no_model_quality_evaluation_performed": True,
            "no_candidate_quality_evaluation_performed": True,
            "no_trading_decision_performed": True,
        },
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
    print(f"ML research pipeline artifacts written to {outputs['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
