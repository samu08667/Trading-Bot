"""Plan the fixed-candidate audit chain without executing child scripts."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Sequence

try:
    from candidate_audit_schema import COMMON_WARNING_FIELDNAMES, warning_row
    from research_costs import load_cost_config
    from research_pipeline_utils import (
        CommandRunner,
        PipelineCommand,
        PipelineCommandResult,
        aggregate_status,
        default_run_id,
        ensure_output_dir,
        render_command,
        require_existing_path,
        run_command,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.run_candidate_audit_pipeline
    from scripts.candidate_audit_schema import COMMON_WARNING_FIELDNAMES, warning_row
    from scripts.research_costs import load_cost_config
    from scripts.research_pipeline_utils import (
        CommandRunner,
        PipelineCommand,
        PipelineCommandResult,
        aggregate_status,
        default_run_id,
        ensure_output_dir,
        render_command,
        require_existing_path,
        run_command,
        utc_now_iso,
        write_command_plan_csv,
        write_manifest,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "reports" / "candidate_audit_pipeline"

MANIFEST_FILE = "candidate_audit_manifest.json"
COMMAND_PLAN_FILE = "candidate_audit_command_plan.csv"
SUMMARY_FILE = "candidate_audit_pipeline_summary.csv"
REPORT_FILE = "candidate_audit_pipeline_report.md"
WARNINGS_FILE = "candidate_audit_pipeline_warnings.csv"
STAGE_RESULTS_FILE = "candidate_audit_stage_results.csv"

FINAL_CLASSIFICATION = "CANDIDATE_AUDIT_PIPELINE_DRY_RUN_PLANNED"
FINAL_CLASSIFICATION_COMPLETED = "CANDIDATE_AUDIT_PIPELINE_COMPLETED"
FINAL_CLASSIFICATION_COMPLETED_WITH_SKIPS = "CANDIDATE_AUDIT_PIPELINE_COMPLETED_WITH_SKIPS"
FINAL_CLASSIFICATION_STOPPED = "CANDIDATE_AUDIT_PIPELINE_STOPPED"
FINAL_CLASSIFICATION_FAILED = "CANDIDATE_AUDIT_PIPELINE_FAILED"
DECISION_SCOPE = "candidate_audit_pipeline"
PIPELINE_SCOPE = "candidate_audit_research_orchestration"
NEXT_ACTION = (
    "Review the command plan. To execute the planned audit chain manually, rerun with --execute. "
    "Heavy stages must be user-run only."
)

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

COMMAND_PLAN_FIELDNAMES = [
    "command_order",
    "stage_order",
    "stage",
    "stage_name",
    "command",
    "heavy",
    "required",
    "conditional",
    "condition_source_stage",
    "condition_label_column",
    "condition_expected_values",
    "skip_if_condition_not_met",
    "expected_outputs",
    "planned_output_dir",
    "gating_note",
]

SUMMARY_FIELDNAMES = [
    "run_id",
    "final_classification",
    "decision_scope",
    "pipeline_scope",
    "dry_run",
    "execute",
    "planned_stage_count",
    "executed_stage_count",
    "skipped_stage_count",
    "failed_stage_count",
    "required_stage_count",
    "conditional_stage_count",
    "warnings_count",
    "blocking_warnings_count",
    "non_blocking_warnings_count",
    "forbidden_actions",
    "next_action",
]

STAGE_RESULT_FIELDNAMES = [
    "command_order",
    "stage_order",
    "stage",
    "stage_name",
    "status",
    "planned",
    "executed",
    "skipped",
    "failed",
    "required",
    "conditional",
    "condition_source_stage",
    "condition_label_column",
    "condition_expected_values",
    "command",
    "returncode",
    "started_at",
    "finished_at",
    "duration_seconds",
    "error_message",
    "stdout_log",
    "stderr_log",
    "summary_csv",
    "label_column",
    "final_classification",
    "warnings_count",
    "blocking_warnings_count",
    "skip_reason",
    "failure_reason",
]

SUMMARY_LABEL_COLUMNS = [
    "final_classification",
    "final_research_label",
    "final_gate_decision",
    "final_timeout_audit_classification",
    "final_timeout_root_cause_classification",
    "final_timeout_sequence_classification",
    "final_timeout_policy_sensitivity_classification",
    "final_research_only_classification",
]

REJECTION_OR_FAILURE_MARKERS = (
    "REJECT",
    "REJECTED",
    "FAIL",
    "FAILED",
    "FAILURE",
    "MISMATCH",
    "NOT_MATCHED",
    "BLOCKED",
)


@dataclass(frozen=True)
class StageSpec:
    stage: str
    script_name: str
    output_dir_name: str
    gating_note: str
    expected_files: tuple[str, ...]
    heavy: bool = False
    required: bool = True
    conditional: bool = False
    condition_source_stage: str = ""
    condition_label_column: str = ""
    condition_expected_values: tuple[str, ...] = ()
    skip_if_condition_not_met: bool = False


STAGE_SPECS = [
    StageSpec(
        stage="candidate_review",
        script_name="build_regime_candidate_review_package.py",
        output_dir_name="candidate_review",
        gating_note="Required first stage; packages existing stress validation outputs.",
        expected_files=(
            "candidate_review_report.md",
            "candidate_review_summary.csv",
            "candidate_review_warnings.csv",
        ),
    ),
    StageSpec(
        stage="rule_replay",
        script_name="run_rule_based_regime_candidate_backtest.py",
        output_dir_name="rule_replay",
        gating_note="Requires candidate_review to be ready in execution mode.",
        expected_files=(
            "rule_based_backtest_report.md",
            "rule_based_backtest_summary.csv",
            "rule_based_backtest_detail.csv",
        ),
        heavy=True,
    ),
    StageSpec(
        stage="rule_review",
        script_name="build_rule_based_regime_candidate_review.py",
        output_dir_name="rule_review",
        gating_note="Requires rule_replay matched in execution mode.",
        expected_files=(
            "rule_based_review_report.md",
            "rule_based_review_summary.csv",
            "rule_based_review_warnings.csv",
        ),
    ),
    StageSpec(
        stage="controlled_expansion",
        script_name="build_controlled_rule_research_expansion.py",
        output_dir_name="controlled_expansion",
        gating_note="Requires rule_review ready in execution mode.",
        expected_files=(
            "controlled_rule_expansion_report.md",
            "controlled_rule_expansion_summary.csv",
            "controlled_rule_expansion_warnings.csv",
        ),
    ),
    StageSpec(
        stage="timeout_audit",
        script_name="build_timeout_fragility_audit.py",
        output_dir_name="timeout_audit",
        gating_note="Conditional in future if controlled expansion retains timeout review.",
        expected_files=(
            "timeout_fragility_audit_report.md",
            "timeout_fragility_audit_summary.csv",
            "timeout_fragility_audit_warnings.csv",
        ),
        required=False,
        conditional=True,
        condition_source_stage="controlled_expansion",
        condition_label_column="final_classification or final_research_only_classification",
        condition_expected_values=("CONTROLLED_EXPANSION_RETAINED_FOR_TIMEOUT_REVIEW",),
        skip_if_condition_not_met=True,
    ),
    StageSpec(
        stage="timeout_root_cause",
        script_name="build_timeout_root_cause_review.py",
        output_dir_name="timeout_root_cause",
        gating_note="Conditional in future if timeout audit retains review.",
        expected_files=(
            "timeout_root_cause_report.md",
            "timeout_root_cause_summary.csv",
            "timeout_root_cause_warnings.csv",
        ),
        required=False,
        conditional=True,
        condition_source_stage="timeout_audit",
        condition_label_column="final_classification or final_timeout_audit_classification",
        condition_expected_values=("TIMEOUT_AUDIT_RETAINED_FOR_REVIEW",),
        skip_if_condition_not_met=True,
    ),
    StageSpec(
        stage="timeout_sequence_drilldown",
        script_name="build_timeout_sequence_drilldown_review.py",
        output_dir_name="timeout_sequence_drilldown",
        gating_note="Conditional in future if root-cause review retains material sequence review.",
        expected_files=(
            "timeout_sequence_drilldown_report.md",
            "timeout_sequence_drilldown_summary.csv",
            "timeout_sequence_drilldown_warnings.csv",
        ),
        required=False,
        conditional=True,
        condition_source_stage="timeout_root_cause",
        condition_label_column="final_classification or final_timeout_root_cause_classification",
        condition_expected_values=("TIMEOUT_ROOT_CAUSE_RETAINED_FOR_REVIEW",),
        skip_if_condition_not_met=True,
    ),
    StageSpec(
        stage="timeout_policy_sensitivity",
        script_name="build_timeout_policy_sensitivity_review.py",
        output_dir_name="timeout_policy_sensitivity",
        gating_note="Conditional in future when timeout caveat requires alternative-policy sensitivity review.",
        expected_files=(
            "timeout_policy_sensitivity_report.md",
            "timeout_policy_sensitivity_summary.csv",
            "timeout_policy_sensitivity_warnings.csv",
        ),
        heavy=True,
        required=False,
        conditional=True,
        condition_source_stage="timeout_sequence_drilldown or gate_precheck",
        condition_label_column="final_classification or final_timeout_sequence_classification",
        condition_expected_values=("TIMEOUT_SEQUENCE_RETAINED_FOR_REVIEW",),
        skip_if_condition_not_met=True,
    ),
    StageSpec(
        stage="gate_decision",
        script_name="build_rule_candidate_gate_decision_report.py",
        output_dir_name="gate_decision",
        gating_note="Final stage; should include only available optional timeout-policy inputs in execution mode.",
        expected_files=(
            "rule_candidate_gate_decision_report.md",
            "rule_candidate_gate_decision_summary.csv",
            "rule_candidate_gate_decision_warnings.csv",
        ),
    ),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the fixed-candidate audit chain with explicit mode selection. "
            "Use --dry-run for planning and --execute for controlled child-stage execution."
        )
    )
    parser.add_argument("--stress-output-dir", type=Path)
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--cost-config", type=Path)
    parser.add_argument("--stress-cost-config", type=Path)
    parser.add_argument("--stress-spread-policy", default="standard")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stop-on-failure", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--timeout-policy", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--include-timeout-policy-sensitivity", action="store_true")
    parser.add_argument("--skip-timeout-policy-sensitivity", action="store_true")
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--continue-after-reject", action="store_true")
    parser.add_argument("--forensic-only", action="store_true")
    return parser


def _resolve_run_id(run_id: str, stress_output_dir: Path | None) -> str:
    value = str(run_id or "").strip()
    if not value and stress_output_dir is not None:
        value = stress_output_dir.name.strip()
    if not value:
        value = default_run_id()
    if "/" in value or "\\" in value:
        raise ValueError("--run-id must be a single path segment, not a nested path.")
    return value


def _validate_json_config(path: Path | None, *, label: str) -> Path:
    if path is None:
        raise ValueError(f"Missing {label}: candidate audit dry-run planning requires a readable JSON cost config.")
    config_path = require_existing_path(path, label=label, kind="file")
    try:
        load_cost_config(config_path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {label} JSON: {config_path}: {exc.msg}") from exc
    except OSError as exc:
        raise ValueError(f"{label} is not readable: {config_path}: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"Invalid {label}: {config_path}: {exc}") from exc
    return config_path


def _validate_inputs(args: argparse.Namespace) -> dict[str, Path]:
    if bool(args.dry_run) == bool(args.execute):
        if args.dry_run:
            raise ValueError("Choose only one of --dry-run or --execute.")
        raise ValueError("Choose either --dry-run or --execute.")
    if args.stress_output_dir is None:
        raise ValueError("Missing --stress-output-dir: candidate audit pipeline requires an existing stress output folder.")
    if args.db_path is None:
        raise ValueError("Missing --db-path: candidate audit pipeline requires a database path for planned replay stages.")

    stress_output_dir = require_existing_path(args.stress_output_dir, label="--stress-output-dir", kind="dir")
    db_path = require_existing_path(args.db_path, label="--db-path", kind="file")
    cost_config = _validate_json_config(args.cost_config, label="--cost-config")
    stress_cost_config = _validate_json_config(args.stress_cost_config, label="--stress-cost-config")

    if args.include_timeout_policy_sensitivity and args.skip_timeout_policy_sensitivity:
        raise ValueError(
            "Choose only one timeout-policy sensitivity flag: "
            "--include-timeout-policy-sensitivity or --skip-timeout-policy-sensitivity."
        )

    return {
        "stress_output_dir": stress_output_dir,
        "db_path": db_path,
        "cost_config": cost_config,
        "stress_cost_config": stress_cost_config,
    }


def _stage_output_dirs(output_dir: Path) -> dict[str, Path]:
    return {spec.stage: output_dir / spec.output_dir_name for spec in STAGE_SPECS}


def _append_common_output_args(args: list[str], *, output_root: Path, run_id: str, overwrite: bool) -> list[str]:
    args.extend(["--output-root", str(output_root), "--run-id", run_id])
    if overwrite:
        args.append("--overwrite")
    return args


def _include_timeout_policy_sensitivity(args: argparse.Namespace) -> tuple[bool, str]:
    if args.skip_timeout_policy_sensitivity:
        return False, "Skipped by explicit dry-run planning flag."
    if args.include_timeout_policy_sensitivity:
        return True, "Included by explicit dry-run planning flag."
    if args.timeout_policy == "always":
        return True, "Included by timeout_policy=always."
    return True, "Included in auto planning as a conditional future sensitivity stage."


def _expected_outputs(spec: StageSpec, output_dir: Path) -> list[Path]:
    return [output_dir / name for name in spec.expected_files]


def _condition_expected_values_text(spec: StageSpec) -> str:
    return ";".join(spec.condition_expected_values)


def _stage_metadata(
    *,
    spec: StageSpec,
    planned_output_dir: Path,
    expected_outputs: Sequence[Path],
    planned: bool,
    skip_reason: str = "",
) -> dict[str, object]:
    return {
        "stage": spec.stage,
        "script_name": spec.script_name,
        "planned": bool(planned),
        "skip_reason": skip_reason,
        "heavy": bool(spec.heavy),
        "required": bool(spec.required),
        "conditional": bool(spec.conditional),
        "condition_source_stage": spec.condition_source_stage,
        "condition_label_column": spec.condition_label_column,
        "condition_expected_values": _condition_expected_values_text(spec),
        "skip_if_condition_not_met": bool(spec.skip_if_condition_not_met),
        "planned_output_dir": str(planned_output_dir),
        "expected_outputs": [str(path) for path in expected_outputs],
        "gating_note": spec.gating_note,
    }


def _build_stage_commands(
    *,
    args: argparse.Namespace,
    paths: dict[str, Path],
    pipeline_output_dir: Path,
) -> tuple[list[PipelineCommand], dict[str, dict[str, object]], list[dict[str, str]], list[dict[str, object]]]:
    stage_dirs = _stage_output_dirs(pipeline_output_dir)
    include_timeout_policy_sensitivity, skip_reason = _include_timeout_policy_sensitivity(args)
    skipped_stages: list[dict[str, str]] = []
    metadata: dict[str, dict[str, object]] = {}
    all_stage_metadata: list[dict[str, object]] = []
    commands: list[PipelineCommand] = []
    python_executable = str(args.python_executable or sys.executable)

    def script(name: str) -> str:
        return str(SCRIPTS_DIR / name)

    for spec in STAGE_SPECS:
        stage_dir = stage_dirs[spec.stage]
        expected_outputs = _expected_outputs(spec, stage_dir)
        if spec.stage == "timeout_policy_sensitivity" and not include_timeout_policy_sensitivity:
            skipped_stages.append({"stage": spec.stage, "reason": skip_reason})
            all_stage_metadata.append(
                _stage_metadata(
                    spec=spec,
                    planned_output_dir=stage_dir,
                    expected_outputs=expected_outputs,
                    planned=False,
                    skip_reason=skip_reason,
                )
            )
            continue

        command_args: list[str]

        if spec.stage == "candidate_review":
            command_args = [
                python_executable,
                script(spec.script_name),
                "--stress-output-dir",
                str(paths["stress_output_dir"]),
            ]
        elif spec.stage == "rule_replay":
            command_args = [
                python_executable,
                script(spec.script_name),
                "--review-package-dir",
                str(stage_dirs["candidate_review"]),
                "--stress-output-dir",
                str(paths["stress_output_dir"]),
                "--db-path",
                str(paths["db_path"]),
                "--cost-config",
                str(paths["cost_config"]),
                "--stress-cost-config",
                str(paths["stress_cost_config"]),
                "--stress-spread-policy",
                str(args.stress_spread_policy),
            ]
        elif spec.stage == "rule_review":
            command_args = [
                python_executable,
                script(spec.script_name),
                "--rule-replay-dir",
                str(stage_dirs["rule_replay"]),
            ]
        elif spec.stage == "controlled_expansion":
            command_args = [
                python_executable,
                script(spec.script_name),
                "--rule-review-dir",
                str(stage_dirs["rule_review"]),
                "--rule-replay-dir",
                str(stage_dirs["rule_replay"]),
            ]
        elif spec.stage == "timeout_audit":
            command_args = [
                python_executable,
                script(spec.script_name),
                "--controlled-expansion-dir",
                str(stage_dirs["controlled_expansion"]),
                "--rule-replay-dir",
                str(stage_dirs["rule_replay"]),
            ]
        elif spec.stage == "timeout_root_cause":
            command_args = [
                python_executable,
                script(spec.script_name),
                "--timeout-audit-dir",
                str(stage_dirs["timeout_audit"]),
                "--rule-replay-dir",
                str(stage_dirs["rule_replay"]),
                "--controlled-expansion-dir",
                str(stage_dirs["controlled_expansion"]),
                "--db-path",
                str(paths["db_path"]),
            ]
        elif spec.stage == "timeout_sequence_drilldown":
            command_args = [
                python_executable,
                script(spec.script_name),
                "--timeout-root-cause-dir",
                str(stage_dirs["timeout_root_cause"]),
                "--timeout-audit-dir",
                str(stage_dirs["timeout_audit"]),
                "--rule-replay-dir",
                str(stage_dirs["rule_replay"]),
                "--db-path",
                str(paths["db_path"]),
            ]
        elif spec.stage == "timeout_policy_sensitivity":
            command_args = [
                python_executable,
                script(spec.script_name),
                "--rule-replay-dir",
                str(stage_dirs["rule_replay"]),
                "--timeout-audit-dir",
                str(stage_dirs["timeout_audit"]),
                "--timeout-root-cause-dir",
                str(stage_dirs["timeout_root_cause"]),
                "--timeout-sequence-dir",
                str(stage_dirs["timeout_sequence_drilldown"]),
                "--db-path",
                str(paths["db_path"]),
                "--cost-config",
                str(paths["cost_config"]),
                "--stress-cost-config",
                str(paths["stress_cost_config"]),
                "--stress-spread-policy",
                str(args.stress_spread_policy),
            ]
        elif spec.stage == "gate_decision":
            command_args = [
                python_executable,
                script(spec.script_name),
                "--candidate-review-dir",
                str(stage_dirs["candidate_review"]),
                "--rule-replay-dir",
                str(stage_dirs["rule_replay"]),
                "--rule-review-dir",
                str(stage_dirs["rule_review"]),
                "--controlled-expansion-dir",
                str(stage_dirs["controlled_expansion"]),
                "--timeout-audit-dir",
                str(stage_dirs["timeout_audit"]),
                "--timeout-root-cause-dir",
                str(stage_dirs["timeout_root_cause"]),
                "--timeout-sequence-dir",
                str(stage_dirs["timeout_sequence_drilldown"]),
            ]
            if include_timeout_policy_sensitivity:
                command_args.extend(
                    [
                        "--timeout-policy-sensitivity-dir",
                        str(stage_dirs["timeout_policy_sensitivity"]),
                    ]
                )
        else:  # pragma: no cover - defensive for future stage edits
            raise ValueError(f"Unhandled candidate audit stage: {spec.stage}")

        command_args = _append_common_output_args(
            command_args,
            output_root=pipeline_output_dir,
            run_id=spec.output_dir_name,
            overwrite=args.overwrite,
        )
        command = PipelineCommand(
            stage=spec.stage,
            args=command_args,
            cwd=REPO_ROOT,
            expected_outputs=expected_outputs,
            heavy=spec.heavy,
            required=spec.required,
            description=spec.gating_note,
        )
        commands.append(command)
        metadata[spec.stage] = {
            "heavy": spec.heavy,
            "required": spec.required,
            "conditional": spec.conditional,
            "condition_source_stage": spec.condition_source_stage,
            "condition_label_column": spec.condition_label_column,
            "condition_expected_values": _condition_expected_values_text(spec),
            "skip_if_condition_not_met": spec.skip_if_condition_not_met,
            "planned_output_dir": stage_dir,
            "gating_note": spec.gating_note,
            "expected_outputs": expected_outputs,
        }
        all_stage_metadata.append(
            _stage_metadata(
                spec=spec,
                planned_output_dir=stage_dir,
                expected_outputs=expected_outputs,
                planned=True,
            )
        )

    return commands, metadata, skipped_stages, all_stage_metadata


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, object]], *, overwrite: bool) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists; pass --overwrite to replace it: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return path


def _bool_text(value: object) -> str:
    return str(bool(value)).lower()


def _int_from_row(row: dict[str, object], key: str) -> int:
    try:
        return int(str(row.get(key, "") or "0"))
    except ValueError:
        return 0


def _summary_path_for_command(command: PipelineCommand) -> Path:
    for expected_output in command.expected_outputs:
        path = Path(expected_output)
        if path.name.endswith("_summary.csv"):
            return path
    raise ValueError(f"No summary CSV expected output is configured for stage: {command.stage}")


def _first_non_empty_label(row: dict[str, object]) -> tuple[str, str]:
    for column in SUMMARY_LABEL_COLUMNS:
        value = str(row.get(column) or "").strip()
        if value:
            return column, value
    return "", ""


def read_stage_summary_label(summary_csv_path: Path) -> dict[str, object]:
    if not summary_csv_path.exists():
        raise FileNotFoundError(f"Missing required stage summary CSV: {summary_csv_path}")
    with summary_csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Stage summary CSV has no rows: {summary_csv_path}")
    row = rows[0]
    label_column, final_label = _first_non_empty_label(row)
    return {
        "summary_csv": str(summary_csv_path),
        "row": row,
        "label_column": label_column,
        "final_classification": final_label,
        "warnings_count": _int_from_row(row, "warnings_count"),
        "blocking_warnings_count": _int_from_row(row, "blocking_warnings_count"),
    }


def _is_rejection_or_failure_label(label: str) -> bool:
    normalized = str(label or "").upper()
    return any(marker in normalized for marker in REJECTION_OR_FAILURE_MARKERS)


def stage_passed_for_next(stage: str, summary_info: dict[str, object]) -> tuple[bool, str, str]:
    blocking_warnings = int(summary_info.get("blocking_warnings_count") or 0)
    if blocking_warnings > 0:
        return False, f"{stage} produced {blocking_warnings} blocking warning(s).", "blocking"
    final_label = str(summary_info.get("final_classification") or "").strip()
    if not final_label:
        return False, f"{stage} summary does not contain a supported final classification label.", "invalid"
    if _is_rejection_or_failure_label(final_label):
        return False, f"{stage} final classification is a rejection/failure state: {final_label}.", "rejection"
    return True, "", ""


def _condition_sources(metadata: dict[str, object]) -> list[str]:
    return [
        source.strip()
        for source in str(metadata.get("condition_source_stage") or "").split(" or ")
        if source.strip()
    ]


def should_run_conditional_stage(
    stage: str,
    metadata: dict[str, object],
    previous_stage_labels: dict[str, dict[str, object]],
) -> tuple[bool, str]:
    expected_values = {
        value.strip()
        for value in str(metadata.get("condition_expected_values") or "").split(";")
        if value.strip()
    }
    sources = _condition_sources(metadata)
    for source in sources:
        summary_info = previous_stage_labels.get(source)
        if not summary_info:
            continue
        final_label = str(summary_info.get("final_classification") or "").strip()
        if final_label in expected_values:
            return True, ""
        return (
            False,
            f"{stage} condition not met: {source} final classification was {final_label or '<missing>'}.",
        )
    return False, f"{stage} condition source was not available: {metadata.get('condition_source_stage', '')}."


def _stage_result_row(
    *,
    stage_order: int,
    stage_metadata: dict[str, object],
    command: PipelineCommand | None,
    status: str,
    result: PipelineCommandResult | None = None,
    summary_info: dict[str, object] | None = None,
    skip_reason: str = "",
    failure_reason: str = "",
) -> dict[str, object]:
    rendered_command = render_command(command) if command is not None else ""
    return {
        "command_order": stage_order,
        "stage_order": stage_order,
        "stage": stage_metadata["stage"],
        "stage_name": stage_metadata["stage"],
        "status": status,
        "planned": _bool_text(stage_metadata.get("planned", True)),
        "executed": _bool_text(status in {"executed", "stopped"}),
        "skipped": _bool_text(status == "skipped"),
        "failed": _bool_text(status == "failed"),
        "required": _bool_text(stage_metadata.get("required")),
        "conditional": _bool_text(stage_metadata.get("conditional")),
        "condition_source_stage": stage_metadata.get("condition_source_stage", ""),
        "condition_label_column": stage_metadata.get("condition_label_column", ""),
        "condition_expected_values": stage_metadata.get("condition_expected_values", ""),
        "command": rendered_command,
        "returncode": "" if result is None or result.returncode is None else result.returncode,
        "started_at": "" if result is None else result.started_at,
        "finished_at": "" if result is None else result.finished_at,
        "duration_seconds": "" if result is None else result.duration_seconds,
        "error_message": failure_reason,
        "stdout_log": "" if result is None or result.stdout_log is None else str(result.stdout_log),
        "stderr_log": "" if result is None or result.stderr_log is None else str(result.stderr_log),
        "summary_csv": "" if summary_info is None else summary_info.get("summary_csv", ""),
        "label_column": "" if summary_info is None else summary_info.get("label_column", ""),
        "final_classification": "" if summary_info is None else summary_info.get("final_classification", ""),
        "warnings_count": "" if summary_info is None else summary_info.get("warnings_count", ""),
        "blocking_warnings_count": "" if summary_info is None else summary_info.get("blocking_warnings_count", ""),
        "skip_reason": skip_reason,
        "failure_reason": failure_reason,
    }


def _without_arg_pairs(command: PipelineCommand, option_names: set[str]) -> PipelineCommand:
    filtered_args: list[str] = []
    skip_next = False
    for arg in command.args:
        if skip_next:
            skip_next = False
            continue
        if arg in option_names:
            skip_next = True
            continue
        filtered_args.append(str(arg))
    return PipelineCommand(
        stage=command.stage,
        args=filtered_args,
        cwd=command.cwd,
        env=command.env,
        expected_outputs=command.expected_outputs,
        heavy=command.heavy,
        required=command.required,
        description=command.description,
    )


def _execution_command_for_stage(command: PipelineCommand, available_stage_dirs: set[str]) -> PipelineCommand:
    if command.stage != "gate_decision":
        return command
    optional_stage_args = {
        "timeout_audit": "--timeout-audit-dir",
        "timeout_root_cause": "--timeout-root-cause-dir",
        "timeout_sequence_drilldown": "--timeout-sequence-dir",
        "timeout_policy_sensitivity": "--timeout-policy-sensitivity-dir",
    }
    omitted = {
        option
        for stage, option in optional_stage_args.items()
        if stage not in available_stage_dirs
    }
    return _without_arg_pairs(command, omitted)


def _planned_stage_results(
    all_stage_metadata: Sequence[dict[str, object]],
    commands: Sequence[PipelineCommand],
) -> list[dict[str, object]]:
    command_by_stage = {command.stage: command for command in commands}
    rows: list[dict[str, object]] = []
    for index, stage_metadata in enumerate(all_stage_metadata, start=1):
        stage = str(stage_metadata["stage"])
        status = "planned" if bool(stage_metadata.get("planned", True)) else "skipped"
        rows.append(
            _stage_result_row(
                stage_order=index,
                stage_metadata=stage_metadata,
                command=command_by_stage.get(stage),
                status=status,
                skip_reason=str(stage_metadata.get("skip_reason", "")),
            )
        )
    return rows


def _execute_stage_commands(
    *,
    args: argparse.Namespace,
    commands: Sequence[PipelineCommand],
    metadata: dict[str, dict[str, object]],
    all_stage_metadata: Sequence[dict[str, object]],
    log_dir: Path,
    runner: CommandRunner | None,
) -> list[dict[str, object]]:
    command_by_stage = {command.stage: command for command in commands}
    stage_results: list[dict[str, object]] = []
    previous_stage_labels: dict[str, dict[str, object]] = {}
    available_stage_dirs: set[str] = set()
    terminal_skip_reason = ""

    for index, stage_metadata in enumerate(all_stage_metadata, start=1):
        stage = str(stage_metadata["stage"])
        command = command_by_stage.get(stage)

        if terminal_skip_reason:
            stage_results.append(
                _stage_result_row(
                    stage_order=index,
                    stage_metadata=stage_metadata,
                    command=command,
                    status="skipped",
                    skip_reason=terminal_skip_reason,
                )
            )
            continue

        if not bool(stage_metadata.get("planned", True)):
            stage_results.append(
                _stage_result_row(
                    stage_order=index,
                    stage_metadata=stage_metadata,
                    command=command,
                    status="skipped",
                    skip_reason=str(stage_metadata.get("skip_reason", "")),
                )
            )
            continue

        if command is None:
            failure_reason = f"No planned command is available for stage: {stage}"
            stage_results.append(
                _stage_result_row(
                    stage_order=index,
                    stage_metadata=stage_metadata,
                    command=None,
                    status="failed",
                    failure_reason=failure_reason,
                )
            )
            if args.stop_on_failure:
                terminal_skip_reason = f"Not run because pipeline failed at {stage}: {failure_reason}"
            continue

        if bool(metadata[stage].get("conditional")):
            should_run, skip_reason = should_run_conditional_stage(stage, metadata[stage], previous_stage_labels)
            if not should_run:
                stage_results.append(
                    _stage_result_row(
                        stage_order=index,
                        stage_metadata=stage_metadata,
                        command=command,
                        status="skipped",
                        skip_reason=skip_reason,
                    )
                )
                continue

        execution_command = _execution_command_for_stage(command, available_stage_dirs)
        result = run_command(execution_command, runner=runner, log_dir=log_dir)
        if result.status != "success":
            failure_reason = result.error_message or f"{stage} failed with exit code {result.returncode}."
            stage_results.append(
                _stage_result_row(
                    stage_order=index,
                    stage_metadata=stage_metadata,
                    command=execution_command,
                    status="failed",
                    result=result,
                    failure_reason=failure_reason,
                )
            )
            if args.stop_on_failure:
                terminal_skip_reason = f"Not run because pipeline failed at {stage}: {failure_reason}"
            continue

        try:
            summary_info = read_stage_summary_label(_summary_path_for_command(execution_command))
        except (FileNotFoundError, ValueError) as exc:
            failure_reason = str(exc)
            stage_results.append(
                _stage_result_row(
                    stage_order=index,
                    stage_metadata=stage_metadata,
                    command=execution_command,
                    status="failed",
                    result=result,
                    failure_reason=failure_reason,
                )
            )
            if args.stop_on_failure:
                terminal_skip_reason = f"Not run because pipeline failed at {stage}: {failure_reason}"
            continue

        previous_stage_labels[stage] = summary_info
        available_stage_dirs.add(stage)
        if bool(metadata[stage].get("required")):
            passed, failure_reason, reason_type = stage_passed_for_next(stage, summary_info)
            if not passed:
                if reason_type == "rejection" and args.continue_after_reject:
                    stage_results.append(
                        _stage_result_row(
                            stage_order=index,
                            stage_metadata=stage_metadata,
                            command=execution_command,
                            status="executed",
                            result=result,
                            summary_info=summary_info,
                            failure_reason=failure_reason,
                        )
                    )
                    continue
                status = "stopped" if reason_type in {"blocking", "rejection"} else "failed"
                stage_results.append(
                    _stage_result_row(
                        stage_order=index,
                        stage_metadata=stage_metadata,
                        command=execution_command,
                        status=status,
                        result=result,
                        summary_info=summary_info,
                        failure_reason=failure_reason,
                    )
                )
                terminal_skip_reason = f"Not run because pipeline {status} at {stage}: {failure_reason}"
                continue

        stage_results.append(
            _stage_result_row(
                stage_order=index,
                stage_metadata=stage_metadata,
                command=execution_command,
                status="executed",
                result=result,
                summary_info=summary_info,
            )
        )

    return stage_results


def _pipeline_final_classification(*, dry_run: bool, stage_results: Sequence[dict[str, object]]) -> str:
    if dry_run:
        return FINAL_CLASSIFICATION
    if any(str(row.get("status")) == "failed" for row in stage_results):
        return FINAL_CLASSIFICATION_FAILED
    if any(str(row.get("status")) == "stopped" for row in stage_results):
        return FINAL_CLASSIFICATION_STOPPED
    if any(str(row.get("status")) == "skipped" for row in stage_results):
        return FINAL_CLASSIFICATION_COMPLETED_WITH_SKIPS
    return FINAL_CLASSIFICATION_COMPLETED


def _aggregate_stage_status(stage_results: Sequence[dict[str, object]]) -> str:
    status_map = {
        "planned": "dry_run",
        "executed": "success",
        "failed": "failed",
        "skipped": "skipped",
        "stopped": "partial",
    }
    return aggregate_status(
        [
            PipelineCommandResult(
                stage=str(row.get("stage") or row.get("stage_name") or ""),
                args=[""],
                status=status_map.get(str(row.get("status") or ""), "skipped"),
            )
            for row in stage_results
        ]
    )


def _next_action_for_classification(final_classification: str) -> str:
    if final_classification == FINAL_CLASSIFICATION:
        return NEXT_ACTION
    if final_classification == FINAL_CLASSIFICATION_FAILED:
        return "Review candidate_audit_stage_results.csv and logs before rerunning with corrected inputs."
    if final_classification == FINAL_CLASSIFICATION_STOPPED:
        return "Review the stopped stage label or blocking warnings before deciding whether forensic continuation is appropriate."
    if final_classification == FINAL_CLASSIFICATION_COMPLETED_WITH_SKIPS:
        return "Review skipped conditional stages and the gate decision output if generated."
    return "Review the generated gate decision output and stage results."


def _warning_rows(
    skipped_stages: Sequence[dict[str, str]],
    *,
    execute: bool,
    stage_results: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    rows = [
        warning_row(
            warning_code="RESEARCH_ONLY_PLANNING_ARTIFACT",
            severity="info",
            blocking=False,
            message="Candidate audit pipeline outputs are offline research planning artifacts only.",
            related_stage=DECISION_SCOPE,
        ),
    ]
    if execute:
        rows.append(
            warning_row(
                warning_code="CONTROLLED_EXECUTION_RESEARCH_ONLY",
                severity="review",
                blocking=False,
                message="Execution mode runs existing offline audit child commands only; outputs remain research-only.",
                related_stage=DECISION_SCOPE,
            )
        )
    else:
        rows.append(
            warning_row(
                warning_code="DRY_RUN_ONLY_EXECUTION_NOT_RUN",
                severity="info",
                blocking=False,
                message=(
                    "This dry-run only planned child commands; no child scripts were executed. "
                    "Execution requires explicit --execute."
                ),
                related_stage=DECISION_SCOPE,
            )
        )
    for skipped in skipped_stages:
        rows.append(
            warning_row(
                warning_code="PLANNED_STAGE_SKIPPED",
                severity="info",
                blocking=False,
                message=skipped.get("reason", ""),
                related_stage=skipped.get("stage", ""),
            )
        )
    for stage_result in stage_results:
        status = str(stage_result.get("status", ""))
        if status == "skipped" and stage_result.get("skip_reason"):
            rows.append(
                warning_row(
                    warning_code="PIPELINE_STAGE_SKIPPED",
                    severity="info",
                    blocking=False,
                    message=stage_result.get("skip_reason", ""),
                    related_stage=stage_result.get("stage", ""),
                )
            )
        elif status == "failed":
            rows.append(
                warning_row(
                    warning_code="PIPELINE_STAGE_FAILED",
                    severity="blocking",
                    blocking=True,
                    message=stage_result.get("failure_reason", ""),
                    related_stage=stage_result.get("stage", ""),
                )
            )
        elif status == "stopped":
            rows.append(
                warning_row(
                    warning_code="PIPELINE_STAGE_STOPPED",
                    severity="blocking",
                    blocking=True,
                    message=stage_result.get("failure_reason", ""),
                    related_stage=stage_result.get("stage", ""),
                )
            )
    return rows


def _write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    run_id: str,
    output_dir: Path,
    commands: Sequence[PipelineCommand],
    metadata: dict[str, dict[str, object]],
    skipped_stages: Sequence[dict[str, str]],
    stage_results: Sequence[dict[str, object]],
    warnings: Sequence[dict[str, object]],
    final_classification: str,
    next_action: str,
    status: str,
    overwrite: bool,
) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Report already exists; pass --overwrite to replace it: {path}")

    lines = [
        "# Candidate Audit Pipeline Report",
        "",
        "## Research-Only Warning",
        "This plan is for offline fixed-candidate research audit tooling only. It is not an operational system and does not create operational instructions.",
        "",
        "## Execution Mode Warning",
        (
            "Controlled execution mode was used. Child stages may have run through the shared runner, "
            "but all outputs remain offline research artifacts."
            if args.execute
            else (
                "Dry-run mode was used. No child scripts were executed while producing this plan. "
                "Execution mode exists but requires explicit --execute and must be user-run only for heavy stages."
            )
        ),
        "",
        "## Input Sources",
        f"- run_id: `{run_id}`",
        f"- output_dir: `{output_dir}`",
        f"- stress_output_dir: `{args.stress_output_dir}`",
        f"- db_path: `{args.db_path}`",
        f"- cost_config: `{args.cost_config}`",
        f"- stress_cost_config: `{args.stress_cost_config}`",
        f"- stress_spread_policy: `{args.stress_spread_policy}`",
        f"- timeout_policy: `{args.timeout_policy}`",
        f"- dry_run: `{str(bool(args.dry_run)).lower()}`",
        f"- execute: `{str(bool(args.execute)).lower()}`",
        f"- continue_after_reject: `{str(bool(args.continue_after_reject)).lower()}`",
        f"- forensic_only: `{str(bool(args.forensic_only)).lower()}`",
        "",
        "## Planned Audit Chain",
    ]
    for index, command in enumerate(commands, start=1):
        lines.append(f"{index}. `{command.stage}`")

    if skipped_stages:
        lines.extend(["", "Skipped stages:"])
        for skipped in skipped_stages:
            lines.append(f"- `{skipped['stage']}`: {skipped['reason']}")

    lines.extend(
        [
            "",
            "## Planned Command Table",
            "| Order | Stage | Heavy | Required | Conditional | Command |",
            "|---:|---|---|---|---|---|",
        ]
    )
    for index, command in enumerate(commands, start=1):
        rendered = render_command(command).replace("|", "\\|")
        stage_metadata = metadata[command.stage]
        lines.append(
            f"| {index} | `{command.stage}` | {str(bool(command.heavy)).lower()} | "
            f"{str(bool(command.required)).lower()} | "
            f"{str(bool(stage_metadata['conditional'])).lower()} | `{rendered}` |"
        )

    required_commands = [command for command in commands if bool(metadata[command.stage]["required"])]
    conditional_commands = [command for command in commands if bool(metadata[command.stage]["conditional"])]

    lines.extend(["", "## Required Stages"])
    for command in required_commands:
        note = metadata[command.stage]["gating_note"]
        lines.append(f"- `{command.stage}`: {note}")

    lines.extend(["", "## Conditional Stages"])
    if conditional_commands:
        for command in conditional_commands:
            stage_metadata = metadata[command.stage]
            lines.append(
                f"- `{command.stage}`: source `{stage_metadata['condition_source_stage']}`, "
                f"label `{stage_metadata['condition_label_column']}`, "
                f"expected `{stage_metadata['condition_expected_values']}`. "
                f"{stage_metadata['gating_note']}"
            )
    else:
        lines.append("- None planned.")

    lines.extend(
        [
            "",
            "## Stage Results",
            "| Order | Stage | Status | Required | Conditional | Return Code | Label | Skip/Failure Reason |",
            "|---:|---|---|---|---|---:|---|---|",
        ]
    )
    for row in stage_results:
        reason = str(row.get("failure_reason") or row.get("skip_reason") or "").replace("|", "\\|")
        label = str(row.get("final_classification") or "").replace("|", "\\|")
        lines.append(
            f"| {row.get('stage_order', '')} | `{row.get('stage', '')}` | `{row.get('status', '')}` | "
            f"{row.get('required', '')} | {row.get('conditional', '')} | {row.get('returncode', '')} | "
            f"`{label}` | {reason} |"
        )

    skipped_result_rows = [row for row in stage_results if row.get("status") == "skipped"]
    lines.extend(["", "## Skipped Stages"])
    if skipped_result_rows:
        for row in skipped_result_rows:
            lines.append(f"- `{row.get('stage', '')}`: {row.get('skip_reason', '')}")
    else:
        lines.append("- None.")

    failure_rows = [row for row in stage_results if row.get("status") in {"failed", "stopped"}]
    lines.extend(["", "## Failures"])
    if failure_rows:
        for row in failure_rows:
            lines.append(f"- `{row.get('stage', '')}`: {row.get('failure_reason', '')}")
    else:
        lines.append("- None.")

    blocking_warnings_count = sum(1 for row in warnings if bool(row.get("blocking")))
    lines.extend(
        [
            "",
            "## Warning Summary",
            f"- total_warnings: `{len(warnings)}`",
            f"- blocking_warnings: `{blocking_warnings_count}`",
            f"- non_blocking_warnings: `{len(warnings) - blocking_warnings_count}`",
            "Detailed row-level warnings are preserved in `candidate_audit_pipeline_warnings.csv`.",
        ]
    )

    gate_rows = [row for row in stage_results if row.get("stage") == "gate_decision" and row.get("status") == "executed"]
    lines.extend(["", "## Final Gate Decision Pointer"])
    if gate_rows:
        gate_output_dir = metadata["gate_decision"]["planned_output_dir"]
        lines.append(f"- `{gate_output_dir}`")
    else:
        lines.append("- Gate decision was not generated in this run.")

    lines.extend(["", "## Stage Gating Notes"])
    for command in commands:
        note = metadata[command.stage]["gating_note"]
        lines.append(f"- `{command.stage}`: {note}")

    lines.extend(["", "## Outputs That Would Be Generated By Child Stages"])
    for command in commands:
        lines.append(f"- `{command.stage}` -> `{metadata[command.stage]['planned_output_dir']}`")
        for expected_output in command.expected_outputs:
            lines.append(f"  - `{expected_output}`")

    lines.extend(["", "## Forbidden Actions"])
    for action in FORBIDDEN_ACTIONS:
        lines.append(f"- {action}")

    lines.extend(
        [
            "",
            "## Final Pipeline Classification",
            f"`{final_classification}`",
            "",
            "## Next Action",
            next_action,
            "",
            "## Status",
            f"`{status}`",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _planned_command_rows(
    commands: Sequence[PipelineCommand],
    metadata: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    rows = []
    for index, command in enumerate(commands, start=1):
        rows.append(
            {
                "command_order": index,
                "stage_order": index,
                "stage": command.stage,
                "stage_name": command.stage,
                "command": render_command(command),
                "heavy": str(bool(command.heavy)).lower(),
                "required": str(bool(command.required)).lower(),
                "conditional": str(bool(metadata[command.stage]["conditional"])).lower(),
                "condition_source_stage": metadata[command.stage]["condition_source_stage"],
                "condition_label_column": metadata[command.stage]["condition_label_column"],
                "condition_expected_values": metadata[command.stage]["condition_expected_values"],
                "skip_if_condition_not_met": str(bool(metadata[command.stage]["skip_if_condition_not_met"])).lower(),
                "expected_outputs": ";".join(str(path) for path in command.expected_outputs),
                "planned_output_dir": str(metadata[command.stage]["planned_output_dir"]),
                "gating_note": metadata[command.stage]["gating_note"],
            }
        )
    return rows


def run_pipeline(args: argparse.Namespace, *, runner: CommandRunner | None = None) -> dict[str, Path]:
    paths = _validate_inputs(args)
    run_id = _resolve_run_id(args.run_id, paths["stress_output_dir"])
    output_dir = Path(args.output_root) / run_id
    ensure_output_dir(output_dir, overwrite=args.overwrite)

    commands, metadata, skipped_stages, all_stage_metadata = _build_stage_commands(
        args=args,
        paths=paths,
        pipeline_output_dir=output_dir,
    )
    log_dir = output_dir / "logs"
    if args.dry_run:
        stage_results = _planned_stage_results(all_stage_metadata, commands)
    else:
        stage_results = _execute_stage_commands(
            args=args,
            commands=commands,
            metadata=metadata,
            all_stage_metadata=all_stage_metadata,
            log_dir=log_dir,
            runner=runner,
        )
    final_classification = _pipeline_final_classification(
        dry_run=bool(args.dry_run),
        stage_results=stage_results,
    )
    next_action = _next_action_for_classification(final_classification)
    status = (
        "dry_run"
        if final_classification == FINAL_CLASSIFICATION
        else final_classification.removeprefix("CANDIDATE_AUDIT_PIPELINE_").lower()
    )
    aggregated_stage_status = _aggregate_stage_status(stage_results)
    warnings = _warning_rows(
        skipped_stages,
        execute=bool(args.execute),
        stage_results=stage_results,
    )
    blocking_warnings_count = sum(1 for row in warnings if bool(row.get("blocking")))
    required_stage_count = sum(1 for row in all_stage_metadata if bool(row.get("required")))
    conditional_stage_count = sum(1 for row in all_stage_metadata if bool(row.get("conditional")))
    executed_stage_count = sum(1 for row in stage_results if row.get("executed") == "true")
    skipped_stage_count = sum(1 for row in stage_results if row.get("skipped") == "true")
    failed_stage_count = sum(1 for row in stage_results if row.get("failed") == "true")

    manifest_path = output_dir / MANIFEST_FILE
    command_plan_path = output_dir / COMMAND_PLAN_FILE
    summary_path = output_dir / SUMMARY_FILE
    report_path = output_dir / REPORT_FILE
    warnings_path = output_dir / WARNINGS_FILE
    stage_results_path = output_dir / STAGE_RESULTS_FILE

    stage_rows = _planned_command_rows(commands, metadata)
    output_artifacts = {
        "manifest": str(manifest_path),
        "command_plan": str(command_plan_path),
        "summary": str(summary_path),
        "report": str(report_path),
        "warnings": str(warnings_path),
        "stage_results": str(stage_results_path),
    }
    log_paths = sorted(
        {
            str(row.get("stdout_log"))
            for row in stage_results
            if str(row.get("stdout_log") or "").strip()
        }
        | {
            str(row.get("stderr_log"))
            for row in stage_results
            if str(row.get("stderr_log") or "").strip()
        }
    )

    write_manifest(
        manifest_path,
        {
            "run_id": run_id,
            "output_dir": str(output_dir),
            "dry_run": bool(args.dry_run),
            "execute": bool(args.execute),
            "pipeline_scope": PIPELINE_SCOPE,
            "stress_output_dir": str(paths["stress_output_dir"]),
            "db_path": str(paths["db_path"]),
            "cost_config": str(paths["cost_config"]),
            "stress_cost_config": str(paths["stress_cost_config"]),
            "stress_spread_policy": str(args.stress_spread_policy),
            "timeout_policy": str(args.timeout_policy),
            "include_timeout_policy_sensitivity": any(
                command.stage == "timeout_policy_sensitivity" for command in commands
            ),
            "continue_after_reject": bool(args.continue_after_reject),
            "forensic_only": bool(args.forensic_only),
            "planned_stages": [command.stage for command in commands],
            "stage_metadata": all_stage_metadata,
            "planned_commands": stage_rows,
            "stage_results": stage_results,
            "aggregated_stage_status": aggregated_stage_status,
            "skipped_stages": list(skipped_stages),
            "output_artifacts": output_artifacts,
            "logs": log_paths,
            "forbidden_actions": FORBIDDEN_ACTIONS,
            "final_classification": final_classification,
            "warnings_count": len(warnings),
            "blocking_warnings_count": blocking_warnings_count,
            "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
            "status": status,
            "completed_at": utc_now_iso(),
        },
        overwrite=args.overwrite,
    )

    def command_plan_row_builder(index: int, command: PipelineCommand) -> dict[str, object]:
        return {
            "command_order": index,
            "stage_order": index,
            "stage_name": command.stage,
            "conditional": str(bool(metadata[command.stage]["conditional"])).lower(),
            "condition_source_stage": metadata[command.stage]["condition_source_stage"],
            "condition_label_column": metadata[command.stage]["condition_label_column"],
            "condition_expected_values": metadata[command.stage]["condition_expected_values"],
            "skip_if_condition_not_met": str(bool(metadata[command.stage]["skip_if_condition_not_met"])).lower(),
            "expected_outputs": ";".join(str(path) for path in command.expected_outputs),
            "planned_output_dir": str(metadata[command.stage]["planned_output_dir"]),
            "gating_note": metadata[command.stage]["gating_note"],
        }

    write_command_plan_csv(
        command_plan_path,
        commands,
        overwrite=args.overwrite,
        fieldnames=COMMAND_PLAN_FIELDNAMES,
        row_builder=command_plan_row_builder,
    )

    _write_csv(
        summary_path,
        SUMMARY_FIELDNAMES,
        [
            {
                "run_id": run_id,
                "final_classification": final_classification,
                "decision_scope": DECISION_SCOPE,
                "pipeline_scope": PIPELINE_SCOPE,
                "dry_run": _bool_text(args.dry_run),
                "execute": _bool_text(args.execute),
                "planned_stage_count": len(commands),
                "executed_stage_count": executed_stage_count,
                "skipped_stage_count": skipped_stage_count,
                "failed_stage_count": failed_stage_count,
                "required_stage_count": required_stage_count,
                "conditional_stage_count": conditional_stage_count,
                "warnings_count": len(warnings),
                "blocking_warnings_count": blocking_warnings_count,
                "non_blocking_warnings_count": len(warnings) - blocking_warnings_count,
                "forbidden_actions": ";".join(FORBIDDEN_ACTIONS),
                "next_action": next_action,
            }
        ],
        overwrite=args.overwrite,
    )
    _write_csv(stage_results_path, STAGE_RESULT_FIELDNAMES, stage_results, overwrite=args.overwrite)
    _write_csv(warnings_path, COMMON_WARNING_FIELDNAMES, warnings, overwrite=args.overwrite)
    _write_report(
        report_path,
        args=args,
        run_id=run_id,
        output_dir=output_dir,
        commands=commands,
        metadata=metadata,
        skipped_stages=skipped_stages,
        stage_results=stage_results,
        warnings=warnings,
        final_classification=final_classification,
        next_action=next_action,
        status=status,
        overwrite=args.overwrite,
    )

    return {
        "output_dir": output_dir,
        "manifest": manifest_path,
        "command_plan": command_plan_path,
        "summary": summary_path,
        "report": report_path,
        "warnings": warnings_path,
        "stage_results": stage_results_path,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        outputs = run_pipeline(args)
    except (FileExistsError, FileNotFoundError, NotImplementedError, OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Candidate audit dry-run plan written to {outputs['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
