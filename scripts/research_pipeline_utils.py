"""Small orchestration primitives for future research pipeline wrappers."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable, Mapping, Sequence


PIPELINE_MANIFEST_SCHEMA_VERSION = "1"
COMMAND_PLAN_FIELDNAMES = [
    "stage",
    "command",
    "heavy",
    "required",
    "description",
    "cwd",
    "expected_outputs",
]


@dataclass
class PipelineCommand:
    stage: str
    args: Sequence[object]
    cwd: Path | str | None = None
    env: Mapping[str, object] | None = None
    expected_outputs: Sequence[Path | str] = field(default_factory=list)
    heavy: bool = False
    required: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        stage = str(self.stage or "").strip()
        if not stage:
            raise ValueError("PipelineCommand.stage is required.")
        args = [str(arg) for arg in self.args]
        if not args:
            raise ValueError("PipelineCommand.args must contain at least one executable argument.")
        cwd = Path(self.cwd) if self.cwd is not None else None
        env = {str(key): str(value) for key, value in self.env.items()} if self.env is not None else None
        expected_outputs = [Path(path) for path in self.expected_outputs]

        self.stage = stage
        self.args = args
        self.cwd = cwd
        self.env = env
        self.expected_outputs = expected_outputs
        self.description = str(self.description or "")


@dataclass
class PipelineCommandResult:
    stage: str
    args: Sequence[object]
    returncode: int | None = None
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0
    stdout_log: Path | str | None = None
    stderr_log: Path | str | None = None
    status: str = "skipped"
    error_message: str = ""

    def __post_init__(self) -> None:
        self.stage = str(self.stage or "").strip()
        self.args = [str(arg) for arg in self.args]
        self.stdout_log = Path(self.stdout_log) if self.stdout_log is not None else None
        self.stderr_log = Path(self.stderr_log) if self.stderr_log is not None else None
        self.status = str(self.status or "").strip().lower()
        self.error_message = str(self.error_message or "")


CommandRunner = Callable[[PipelineCommand], object]
CommandPlanRowBuilder = Callable[[int, PipelineCommand], Mapping[str, object]]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_run_id(now: datetime | None = None) -> str:
    value = now or datetime.now()
    return value.strftime("%Y%m%d_%H%M%S")


def render_command(command: PipelineCommand) -> str:
    return subprocess.list2cmdline(list(command.args))


def _safe_stage_stem(stage: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stage.strip()).strip("._")
    return stem or "command"


def _completed_attr(completed: object, name: str, default: object = "") -> object:
    return getattr(completed, name, default)


def _write_command_logs(
    *,
    log_dir: Path | str,
    stage: str,
    stdout: str,
    stderr: str,
) -> tuple[Path, Path]:
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = _safe_stage_stem(stage)
    stdout_path = directory / f"{stem}.stdout.log"
    stderr_path = directory / f"{stem}.stderr.log"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return stdout_path, stderr_path


def run_command(
    command: PipelineCommand,
    *,
    runner: CommandRunner | None = None,
    dry_run: bool = False,
    log_dir: Path | str | None = None,
) -> PipelineCommandResult:
    started_at = utc_now_iso()
    started = time.perf_counter()

    if dry_run:
        return PipelineCommandResult(
            stage=command.stage,
            args=command.args,
            returncode=None,
            started_at=started_at,
            finished_at=started_at,
            duration_seconds=0.0,
            status="dry_run",
        )

    stdout = ""
    stderr = ""
    returncode: int | None = None
    error_message = ""

    try:
        if runner is not None:
            completed = runner(command)
        else:
            env = None
            if command.env is not None:
                env = os.environ.copy()
                env.update(command.env)
            completed = subprocess.run(
                list(command.args),
                cwd=command.cwd,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        returncode = int(_completed_attr(completed, "returncode", 0))
        stdout = str(_completed_attr(completed, "stdout", "") or "")
        stderr = str(_completed_attr(completed, "stderr", "") or "")
    except Exception as exc:
        returncode = None
        stderr = str(exc)
        error_message = f"{command.stage} failed to start: {exc}"

    finished_at = utc_now_iso()
    duration = round(time.perf_counter() - started, 6)
    stdout_log: Path | None = None
    stderr_log: Path | None = None
    if log_dir is not None:
        stdout_log, stderr_log = _write_command_logs(
            log_dir=log_dir,
            stage=command.stage,
            stdout=stdout,
            stderr=stderr,
        )

    status = "success" if returncode == 0 else "failed"
    if status == "failed" and not error_message:
        error_message = f"{command.stage} failed with exit code {returncode}."

    return PipelineCommandResult(
        stage=command.stage,
        args=command.args,
        returncode=returncode,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        status=status,
        error_message=error_message,
    )


def ensure_output_dir(path: Path | str, *, overwrite: bool = False) -> Path:
    output_dir = Path(path)
    if output_dir.exists():
        if not output_dir.is_dir():
            raise FileExistsError(f"Output path exists and is not a directory: {output_dir}")
        if not overwrite:
            raise FileExistsError(f"Output directory already exists; pass overwrite=True to reuse it: {output_dir}")
        return output_dir
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir


def write_manifest(
    path: Path | str,
    data: Mapping[str, Any],
    *,
    overwrite: bool = False,
    schema_version: str = PIPELINE_MANIFEST_SCHEMA_VERSION,
) -> Path:
    manifest_path = Path(path)
    if manifest_path.exists() and not overwrite:
        raise FileExistsError(f"Manifest already exists; pass overwrite=True to replace it: {manifest_path}")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload.setdefault("schema_version", schema_version)
    payload.setdefault("generated_at", utc_now_iso())
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def aggregate_status(results: Sequence[PipelineCommandResult]) -> str:
    if not results:
        return "skipped"
    statuses = [str(result.status or "").strip().lower() for result in results]
    allowed = {"success", "failed", "skipped", "dry_run", "partial"}
    unknown = sorted(set(statuses) - allowed)
    if unknown:
        raise ValueError(f"Unknown pipeline result status: {', '.join(unknown)}")
    if "partial" in statuses:
        return "partial"
    if len(set(statuses)) == 1:
        return statuses[0]
    return "partial"


def write_command_plan_csv(
    path: Path | str,
    commands: Sequence[PipelineCommand],
    *,
    overwrite: bool = False,
    fieldnames: Sequence[str] | None = None,
    row_builder: CommandPlanRowBuilder | None = None,
) -> Path:
    plan_path = Path(path)
    if plan_path.exists() and not overwrite:
        raise FileExistsError(f"Command plan already exists; pass overwrite=True to replace it: {plan_path}")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    selected_fieldnames = list(fieldnames or COMMAND_PLAN_FIELDNAMES)
    with plan_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=selected_fieldnames)
        writer.writeheader()
        for index, command in enumerate(commands, start=1):
            row: dict[str, object] = {
                "stage": command.stage,
                "command": render_command(command),
                "heavy": str(bool(command.heavy)).lower(),
                "required": str(bool(command.required)).lower(),
                "description": command.description,
                "cwd": str(command.cwd or ""),
                "expected_outputs": ";".join(str(path) for path in command.expected_outputs),
            }
            if row_builder is not None:
                row.update(row_builder(index, command))
            writer.writerow({field: row.get(field, "") for field in selected_fieldnames})
    return plan_path


def build_run_paths(output_root: Path | str, run_id: str) -> dict[str, Path]:
    root = Path(output_root)
    run_dir = root / str(run_id)
    return {
        "output_root": root,
        "run_dir": run_dir,
        "logs_dir": run_dir / "logs",
        "manifest": run_dir / "manifest.json",
        "command_plan": run_dir / "command_plan.csv",
    }


def require_existing_path(path: Path | str, *, label: str = "path", kind: str = "any") -> Path:
    if kind not in {"any", "file", "dir"}:
        raise ValueError("--kind must be one of: any, file, dir.")
    checked = Path(path)
    if not checked.exists():
        raise FileNotFoundError(f"{label} does not exist: {checked}")
    if kind == "file" and not checked.is_file():
        raise ValueError(f"{label} is not a file: {checked}")
    if kind == "dir" and not checked.is_dir():
        raise ValueError(f"{label} is not a directory: {checked}")
    return checked
