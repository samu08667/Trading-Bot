from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts import consolidate_fixed_candidate_baseline_outputs as consolidator


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_matrix(path: Path, rows: list[tuple[str, str]] | None = None) -> None:
    rows = rows or consolidator.EXPECTED_ROWS
    write_csv(
        path,
        ["baseline_type", "cost_profile", "cost_config_path", "artifact_status"],
        [
            {
                "baseline_type": baseline_type,
                "cost_profile": cost_profile,
                "cost_config_path": f"config/brokers/{cost_profile}.json",
                "artifact_status": "planned_not_run",
            }
            for baseline_type, cost_profile in rows
        ],
    )


def write_baseline_output(root: Path, baseline_type: str, cost_profile: str, *, skipped: bool = False) -> Path:
    output_dir = root / f"{baseline_type}_{cost_profile}" / "unit_run" / "short"
    if skipped:
        write_csv(
            output_dir / "skipped_baseline_diagnostics_candidates.csv",
            ["candidate_scope", "symbol", "combination_key", "direction", "cost_mode", "return_mode", "skip_reason"],
            [
                {
                    "candidate_scope": "fixed_row_direct",
                    "symbol": "GBPUSD",
                    "combination_key": "filter_a AND filter_b",
                    "direction": "short",
                    "cost_mode": "estimated",
                    "return_mode": "net",
                    "skip_reason": "unit_skip",
                }
            ],
        )
        return root / f"{baseline_type}_{cost_profile}"

    write_csv(
        output_dir / "baseline_diagnostics_detail.csv",
        [
            "candidate_scope",
            "symbol",
            "combination_key",
            "baseline_type",
            "baseline_key",
            "direction",
            "cost_mode",
            "return_mode",
            "candidate_trades_count",
            "baseline_trades_count",
            "candidate_mean_return",
            "baseline_mean_return",
            "candidate_profit_factor",
            "baseline_profit_factor",
            "candidate_cumulative_return",
            "baseline_cumulative_return",
            "candidate_max_drawdown",
            "baseline_max_drawdown",
            "candidate_monthly_positive_ratio",
            "baseline_monthly_positive_ratio",
            "candidate_top_5_percent_trades_contribution_pct",
            "baseline_top_5_percent_trades_contribution_pct",
        ],
        [
            {
                "candidate_scope": "fixed_row_direct",
                "symbol": "GBPUSD",
                "combination_key": "filter_a AND filter_b",
                "baseline_type": baseline_type,
                "baseline_key": "hour_session=Off_hours" if baseline_type == "broad_regime_baseline" else "filter_a",
                "direction": "short",
                "cost_mode": "estimated",
                "return_mode": "net",
                "candidate_trades_count": "",
                "baseline_trades_count": "123",
                "candidate_mean_return": "",
                "baseline_mean_return": "0.1",
                "candidate_profit_factor": "",
                "baseline_profit_factor": "1.2",
                "candidate_cumulative_return": "",
                "baseline_cumulative_return": "12.3",
                "candidate_max_drawdown": "",
                "baseline_max_drawdown": "0.4",
                "candidate_monthly_positive_ratio": "",
                "baseline_monthly_positive_ratio": "0.5",
                "candidate_top_5_percent_trades_contribution_pct": "",
                "baseline_top_5_percent_trades_contribution_pct": "10",
            }
        ],
    )
    write_csv(
        output_dir / "baseline_diagnostics_summary.csv",
        [
            "candidate_scope",
            "symbol",
            "combination_key",
            "direction",
            "cost_mode",
            "return_mode",
            "final_baseline_diagnostic_classification",
            "trades_count",
        ],
        [
            {
                "candidate_scope": "fixed_row_direct",
                "symbol": "GBPUSD",
                "combination_key": "filter_a AND filter_b",
                "direction": "short",
                "cost_mode": "estimated",
                "return_mode": "net",
                "final_baseline_diagnostic_classification": "fixed_row_diagnostic_only",
                "trades_count": "123",
            }
        ],
    )
    write_csv(
        output_dir / "skipped_baseline_diagnostics_candidates.csv",
        ["candidate_scope", "symbol", "combination_key", "direction", "cost_mode", "return_mode", "skip_reason"],
        [],
    )
    (output_dir / "baseline_diagnostics_report.md").write_text("# Report\n", encoding="utf-8")
    return root / f"{baseline_type}_{cost_profile}"


def make_args(tmp_path: Path, *extra: str) -> object:
    matrix_csv = tmp_path / "matrix.csv"
    write_matrix(matrix_csv)
    return consolidator.build_parser().parse_args(
        [
            "--run-id",
            "unit",
            "--baseline-output-root",
            str(tmp_path / "raw_outputs"),
            "--matrix-csv",
            str(matrix_csv),
            "--output-dir",
            str(tmp_path / "out"),
            *extra,
        ]
    )


def test_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        consolidator.build_parser().parse_args(["--help"])

    assert exc.value.code == 0


def test_discovers_expected_folders_and_consolidates_available_rows(tmp_path: Path) -> None:
    root = tmp_path / "raw_outputs"
    write_baseline_output(root, "broad_regime_baseline", "p75")
    write_baseline_output(root, "single_filter_a", "p90")

    outputs = consolidator.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["consolidated"])

    broad = next(row for row in rows if row["baseline_type"] == "broad_regime_baseline" and row["cost_profile"] == "p75")
    single = next(row for row in rows if row["baseline_type"] == "single_filter_a" and row["cost_profile"] == "p90")
    assert broad["artifact_status"] == "available"
    assert broad["cost_config_path"] == "config/brokers/p75.json"
    assert broad["baseline_trades_count"] == "123"
    assert broad["final_baseline_diagnostic_classification"] == "fixed_row_diagnostic_only"
    assert single["artifact_status"] == "available"
    assert single["baseline_key"] == "filter_a"


def test_flags_missing_folders(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["consolidated"])
    warnings = read_csv(outputs["warnings"])

    assert len(rows) == 6
    assert {row["artifact_status"] for row in rows} == {"missing"}
    assert len(warnings) == 6
    assert {row["warning_code"] for row in warnings} == {"baseline_output_missing"}


def test_preserves_source_paths(tmp_path: Path) -> None:
    root = tmp_path / "raw_outputs"
    source_dir = write_baseline_output(root, "broad_regime_baseline", "p75")

    outputs = consolidator.build_outputs(make_args(tmp_path))
    row = next(
        row
        for row in read_csv(outputs["consolidated"])
        if row["baseline_type"] == "broad_regime_baseline" and row["cost_profile"] == "p75"
    )

    assert row["source_output_dir"] == str(source_dir)
    assert row["cost_config_path"] == "config/brokers/p75.json"
    assert row["source_csv"].endswith("baseline_diagnostics_detail.csv")
    assert row["source_summary_csv"].endswith("baseline_diagnostics_summary.csv")
    assert row["source_skipped_csv"].endswith("skipped_baseline_diagnostics_candidates.csv")
    assert row["source_report"].endswith("baseline_diagnostics_report.md")


def test_marks_skipped_outputs(tmp_path: Path) -> None:
    root = tmp_path / "raw_outputs"
    write_baseline_output(root, "single_filter_b", "p75", skipped=True)

    outputs = consolidator.build_outputs(make_args(tmp_path))
    row = next(
        row
        for row in read_csv(outputs["consolidated"])
        if row["baseline_type"] == "single_filter_b" and row["cost_profile"] == "p75"
    )

    assert row["artifact_status"] == "skipped"
    assert row["warning_code"] == "baseline_output_skipped"


def test_manifest_counts_match_csv_and_warnings(tmp_path: Path) -> None:
    root = tmp_path / "raw_outputs"
    write_baseline_output(root, "broad_regime_baseline", "p75")
    write_baseline_output(root, "single_filter_b", "p75", skipped=True)

    outputs = consolidator.build_outputs(make_args(tmp_path))
    rows = read_csv(outputs["consolidated"])
    warnings = read_csv(outputs["warnings"])
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert manifest["consolidated_row_count"] == len(rows)
    assert manifest["available_row_count"] == sum(row["artifact_status"] == "available" for row in rows)
    assert manifest["missing_row_count"] == sum(row["artifact_status"] == "missing" for row in rows)
    assert manifest["skipped_row_count"] == sum(row["artifact_status"] == "skipped" for row in rows)
    assert manifest["warnings_count"] == len(warnings)
    assert manifest["blocking_warnings_count"] == sum(row["blocking_warning"] == "true" for row in warnings)
    assert manifest["no_child_scripts_executed"] is True
    assert manifest["no_baseline_diagnostics_executed"] is True
    assert manifest["no_backtests_run"] is True
    assert manifest["no_candidate_quality_evaluation_performed"] is True
    assert manifest["no_trading_decision_performed"] is True


def test_report_states_no_candidate_or_trading_decision(tmp_path: Path) -> None:
    outputs = consolidator.build_outputs(make_args(tmp_path))
    report = outputs["report"].read_text(encoding="utf-8")

    assert "artifact consolidation only" in report
    assert "does not execute diagnostics" in report
    assert "does not execute diagnostics" in report
    assert "cost_config_path" in report
    assert "interpret candidate quality" in report
    assert "make trading decisions" in report


def test_include_specific_roots(tmp_path: Path) -> None:
    matrix_csv = tmp_path / "matrix.csv"
    write_matrix(matrix_csv)
    broad_root = tmp_path / "broad_v4"
    single_root = tmp_path / "single_v5"
    write_baseline_output(broad_root, "broad_regime_baseline", "p75")
    write_baseline_output(single_root, "single_filter_a", "p75")
    args = consolidator.build_parser().parse_args(
        [
            "--run-id",
            "unit",
            "--baseline-output-root",
            str(tmp_path / "empty"),
            "--include-broad-v4-root",
            str(broad_root),
            "--include-single-v5-root",
            str(single_root),
            "--matrix-csv",
            str(matrix_csv),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    outputs = consolidator.build_outputs(args)
    rows = read_csv(outputs["consolidated"])

    assert any(row["baseline_type"] == "broad_regime_baseline" and row["artifact_status"] == "available" for row in rows)
    assert any(row["baseline_type"] == "single_filter_a" and row["artifact_status"] == "available" for row in rows)


def test_no_child_scripts_are_executed() -> None:
    source = Path(consolidator.__file__).read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "run_candidate_baseline_diagnostics.py --" not in source
