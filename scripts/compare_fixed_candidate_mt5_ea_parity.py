"""Compare Python and MQL5 signal-only parity CSVs for the fixed candidate.

This comparator is deliberately offline and read-only: it reads two CSV files,
writes comparison artifacts, and never connects to MT5, builds broker payloads,
or performs trade operations. Rows are joined by ``time_server``; row order is
diagnostic, not a comparison contract.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = [
    "time_server",
    "hour_session",
    "atr_20",
    "ma_fast",
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100_bucket",
    "signal_bool",
    "entry_reference_price",
    "sl_price_preview",
    "tp_price_preview",
    "max_holding_bars",
    "max_exit_time_server",
]

SIGNAL_EXACT_FIELDS = [
    "hour_session",
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100_bucket",
    "signal_bool",
    "max_holding_bars",
]

BUCKET_FIELDS = [
    "close_to_ma_fast_atr_20_bucket",
    "tick_volume_percentile_100_bucket",
]

LIFECYCLE_METADATA_FIELDS = [
    "max_exit_time_server",
]

NUMERIC_FIELDS = [
    "atr_20",
    "ma_fast",
    "close_to_ma_fast_atr_20",
    "tick_volume_percentile_100",
    "entry_reference_price",
    "sl_price_preview",
    "tp_price_preview",
]

NEAR_THRESHOLD_CUTOFFS = [
    ("close_to_ma_fast_atr_20", "close_to_ma_fast_atr_20_low_mid", -0.4303672057741361),
    ("close_to_ma_fast_atr_20", "close_to_ma_fast_atr_20_mid_high", 0.5954421525644814),
    ("tick_volume_percentile_100", "tick_volume_percentile_100_low_mid", 0.14),
    ("tick_volume_percentile_100", "tick_volume_percentile_100_mid_high", 0.37),
]

MANIFEST_NAME = "fixed_candidate_mt5_ea_parity_comparison_manifest.json"
SUMMARY_NAME = "fixed_candidate_mt5_ea_parity_comparison_summary.csv"
MISMATCHES_NAME = "fixed_candidate_mt5_ea_parity_comparison_mismatches.csv"
MISSING_TIMES_NAME = "fixed_candidate_mt5_ea_parity_comparison_missing_times.csv"
EXTRA_TIMES_NAME = "fixed_candidate_mt5_ea_parity_comparison_extra_times.csv"
NEAR_MISSES_NAME = "fixed_candidate_mt5_ea_parity_comparison_threshold_near_misses.csv"
REPORT_NAME = "fixed_candidate_mt5_ea_parity_comparison_report.md"


def normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_float(value: Any) -> float | None:
    text = normalize(value)
    if text == "":
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path} contains no rows.")
    return rows


def rows_by_time(rows: list[dict[str, str]], *, source_name: str) -> dict[str, tuple[int, dict[str, str]]]:
    indexed: dict[str, tuple[int, dict[str, str]]] = {}
    for row_index, row in enumerate(rows):
        time_server = normalize(row.get("time_server"))
        if not time_server:
            raise ValueError(f"{source_name} row {row_index} has empty time_server.")
        if time_server in indexed:
            raise ValueError(f"{source_name} contains duplicate time_server: {time_server}")
        indexed[time_server] = (row_index, row)
    return indexed


def exact_match(left: Any, right: Any) -> bool:
    return normalize(left) == normalize(right)


def numeric_match(left: Any, right: Any, tolerance: float) -> tuple[bool, float | None, str]:
    left_text = normalize(left)
    right_text = normalize(right)
    if left_text == "" and right_text == "":
        return True, None, "both_blank"
    left_number = safe_float(left_text)
    right_number = safe_float(right_text)
    if left_number is None or right_number is None:
        return False, None, "non_numeric_or_one_blank"
    absolute_diff = abs(left_number - right_number)
    return absolute_diff <= tolerance, absolute_diff, "numeric"


def add_mismatch(
    mismatches: list[dict[str, Any]],
    *,
    row_index: int | str,
    mql5_row_index: int | str,
    time_server: str,
    field: str,
    python_value: Any,
    mql5_value: Any,
    mismatch_type: str,
    absolute_diff: float | None = None,
    tolerance: float | None = None,
) -> None:
    mismatches.append(
        {
            "row_index": row_index,
            "mql5_row_index": mql5_row_index,
            "time_server": time_server,
            "field": field,
            "python_value": normalize(python_value),
            "mql5_value": normalize(mql5_value),
            "mismatch_type": mismatch_type,
            "absolute_diff": "" if absolute_diff is None else absolute_diff,
            "tolerance": "" if tolerance is None else tolerance,
        }
    )


def threshold_near_misses(
    python_rows: list[dict[str, str]],
    *,
    near_threshold_epsilon: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(python_rows):
        for field, cutoff_name, cutoff in NEAR_THRESHOLD_CUTOFFS:
            value = safe_float(row.get(field))
            if value is None:
                continue
            distance = abs(value - cutoff)
            if distance <= near_threshold_epsilon:
                rows.append(
                    {
                        "row_index": row_index,
                        "time_server": normalize(row.get("time_server")),
                        "field": field,
                        "value": value,
                        "cutoff_name": cutoff_name,
                        "cutoff": cutoff,
                        "distance": distance,
                        "near_threshold_epsilon": near_threshold_epsilon,
                        "source": "python_csv",
                    }
                )
    return rows


def rate(matches: int, total: int) -> float:
    return matches / total if total else 0.0


def write_dicts(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    rows = [{"metric": key, "value": value} for key, value in summary.items()]
    write_dicts(path, rows, ["metric", "value"])


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def write_report(path: Path, manifest: dict[str, Any]) -> None:
    acceptance = "PASS" if manifest["acceptance_passed"] else "FAIL"
    lifecycle = "PASS" if manifest["lifecycle_metadata_acceptance_passed"] else "FAIL"
    lines = [
        "# Fixed Candidate MT5 EA Signal Parity Comparison",
        "",
        f"- acceptance: `{acceptance}`",
        f"- lifecycle metadata acceptance: `{lifecycle}`",
        f"- python rows: `{manifest['python_row_count']}`",
        f"- mql5 rows: `{manifest['mql5_row_count']}`",
        f"- aligned rows: `{manifest['aligned_row_count']}`",
        f"- missing MQL5 times: `{manifest['missing_mql5_time_count']}`",
        f"- extra MQL5 times: `{manifest['extra_mql5_time_count']}`",
        f"- mismatch count: `{manifest['mismatch_count']}`",
        f"- signal parity mismatch count: `{manifest['signal_parity_mismatch_count']}`",
        f"- lifecycle metadata mismatch count: `{manifest['lifecycle_metadata_mismatch_count']}`",
        f"- threshold near miss count: `{manifest['threshold_near_miss_count']}`",
        f"- time_server_match_rate: `{manifest['time_server_match_rate']}`",
        f"- signal_bool_match_rate: `{manifest['signal_bool_match_rate']}`",
        f"- bucket_match_rate: `{manifest['bucket_match_rate']}`",
        f"- hour_session_match_rate: `{manifest['hour_session_match_rate']}`",
        f"- max_holding_bars_match_rate: `{manifest['max_holding_bars_match_rate']}`",
        f"- max_exit_time_server_match_rate: `{manifest['max_exit_time_server_match_rate']}`",
        f"- numeric_within_tolerance_rate: `{manifest['numeric_within_tolerance_rate']}`",
        "",
        "## Join Contract",
        "",
        "`time_server` is the primary key. Python rows without the same MQL5",
        "timestamp are reported as missing. MQL5 timestamps absent from Python",
        "are reported as extra.",
        "",
        "## Safety",
        "",
        "- MT5 connection performed: `false`",
        "- OrderCheck performed: `false`",
        "- OrderSend performed: `false`",
        "- trade operation performed: `false`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare_parity_csvs(
    *,
    python_csv: Path,
    mql5_csv: Path,
    output_dir: Path,
    numeric_tolerance: float = 1e-9,
    near_threshold_epsilon: float = 0.02,
    allow_extra_mql5_times: bool = False,
) -> dict[str, Any]:
    if numeric_tolerance < 0:
        raise ValueError("numeric_tolerance must be non-negative.")
    if near_threshold_epsilon < 0:
        raise ValueError("near_threshold_epsilon must be non-negative.")

    python_rows = read_csv_rows(python_csv)
    mql5_rows = read_csv_rows(mql5_csv)
    python_by_time = rows_by_time(python_rows, source_name="python_csv")
    mql5_by_time = rows_by_time(mql5_rows, source_name="mql5_csv")

    mismatches: list[dict[str, Any]] = []
    missing_times: list[dict[str, Any]] = []
    extra_times: list[dict[str, Any]] = []
    exact_match_counts = {field: 0 for field in SIGNAL_EXACT_FIELDS}
    lifecycle_match_counts = {field: 0 for field in LIFECYCLE_METADATA_FIELDS}
    numeric_match_count = 0
    aligned_row_count = 0
    signal_parity_mismatch_count = 0
    lifecycle_metadata_mismatch_count = 0

    for python_row_index, python_row in enumerate(python_rows):
        time_server = normalize(python_row.get("time_server"))
        mql5_match = mql5_by_time.get(time_server)
        if mql5_match is None:
            missing_times.append(
                {
                    "row_index": python_row_index,
                    "time_server": time_server,
                    "source": "python_csv",
                    "mismatch_type": "missing_mql5_time",
                }
            )
            add_mismatch(
                mismatches,
                row_index=python_row_index,
                mql5_row_index="",
                time_server=time_server,
                field="time_server",
                python_value=time_server,
                mql5_value="",
                mismatch_type="missing_mql5_time",
            )
            signal_parity_mismatch_count += 1
            continue

        mql5_row_index, mql5_row = mql5_match
        aligned_row_count += 1

        for field in SIGNAL_EXACT_FIELDS:
            if exact_match(python_row.get(field), mql5_row.get(field)):
                exact_match_counts[field] += 1
            else:
                add_mismatch(
                    mismatches,
                    row_index=python_row_index,
                    mql5_row_index=mql5_row_index,
                    time_server=time_server,
                    field=field,
                    python_value=python_row.get(field),
                    mql5_value=mql5_row.get(field),
                    mismatch_type="exact",
                )
                signal_parity_mismatch_count += 1

        for field in NUMERIC_FIELDS:
            matched, absolute_diff, mismatch_type = numeric_match(
                python_row.get(field),
                mql5_row.get(field),
                numeric_tolerance,
            )
            if matched:
                numeric_match_count += 1
            else:
                add_mismatch(
                    mismatches,
                    row_index=python_row_index,
                    mql5_row_index=mql5_row_index,
                    time_server=time_server,
                    field=field,
                    python_value=python_row.get(field),
                    mql5_value=mql5_row.get(field),
                    mismatch_type=mismatch_type,
                    absolute_diff=absolute_diff,
                    tolerance=numeric_tolerance,
                )
                signal_parity_mismatch_count += 1

        for field in LIFECYCLE_METADATA_FIELDS:
            if exact_match(python_row.get(field), mql5_row.get(field)):
                lifecycle_match_counts[field] += 1
            else:
                add_mismatch(
                    mismatches,
                    row_index=python_row_index,
                    mql5_row_index=mql5_row_index,
                    time_server=time_server,
                    field=field,
                    python_value=python_row.get(field),
                    mql5_value=mql5_row.get(field),
                    mismatch_type="lifecycle_metadata",
                )
                lifecycle_metadata_mismatch_count += 1

    for mql5_row_index, mql5_row in enumerate(mql5_rows):
        time_server = normalize(mql5_row.get("time_server"))
        if time_server in python_by_time:
            continue
        extra_times.append(
            {
                "mql5_row_index": mql5_row_index,
                "time_server": time_server,
                "source": "mql5_csv",
                "mismatch_type": "extra_mql5_time",
                "allowed": allow_extra_mql5_times,
            }
        )
        if not allow_extra_mql5_times:
            add_mismatch(
                mismatches,
                row_index="",
                mql5_row_index=mql5_row_index,
                time_server=time_server,
                field="time_server",
                python_value="",
                mql5_value=time_server,
                mismatch_type="extra_mql5_time",
            )
            signal_parity_mismatch_count += 1

    bucket_matches = sum(exact_match_counts[field] for field in BUCKET_FIELDS)
    bucket_total = aligned_row_count * len(BUCKET_FIELDS)
    numeric_total = aligned_row_count * len(NUMERIC_FIELDS)
    near_misses = threshold_near_misses(
        python_rows,
        near_threshold_epsilon=near_threshold_epsilon,
    )
    extra_mql5_time_blocking_count = 0 if allow_extra_mql5_times else len(extra_times)
    summary = {
        "python_row_count": len(python_rows),
        "mql5_row_count": len(mql5_rows),
        "aligned_row_count": aligned_row_count,
        "rows_compared": aligned_row_count,
        "missing_mql5_time_count": len(missing_times),
        "extra_mql5_time_count": len(extra_times),
        "extra_mql5_time_blocking_count": extra_mql5_time_blocking_count,
        "allow_extra_mql5_times": allow_extra_mql5_times,
        "mismatch_count": len(mismatches),
        "signal_parity_mismatch_count": signal_parity_mismatch_count,
        "lifecycle_metadata_mismatch_count": lifecycle_metadata_mismatch_count,
        "threshold_near_miss_count": len(near_misses),
        "time_server_match_rate": rate(aligned_row_count, len(python_rows)),
        "signal_bool_match_rate": rate(exact_match_counts["signal_bool"], aligned_row_count),
        "bucket_match_rate": rate(bucket_matches, bucket_total),
        "hour_session_match_rate": rate(exact_match_counts["hour_session"], aligned_row_count),
        "max_holding_bars_match_rate": rate(
            exact_match_counts["max_holding_bars"],
            aligned_row_count,
        ),
        "max_exit_time_server_match_rate": rate(
            lifecycle_match_counts["max_exit_time_server"],
            aligned_row_count,
        ),
        "numeric_within_tolerance_rate": rate(numeric_match_count, numeric_total),
        "numeric_tolerance": numeric_tolerance,
        "near_threshold_epsilon": near_threshold_epsilon,
    }
    signal_parity_acceptance_passed = (
        summary["missing_mql5_time_count"] == 0
        and summary["extra_mql5_time_blocking_count"] == 0
        and summary["signal_bool_match_rate"] == 1.0
        and summary["bucket_match_rate"] == 1.0
        and summary["hour_session_match_rate"] == 1.0
        and summary["max_holding_bars_match_rate"] == 1.0
        and summary["numeric_within_tolerance_rate"] == 1.0
        and signal_parity_mismatch_count == 0
    )
    lifecycle_metadata_acceptance_passed = summary["max_exit_time_server_match_rate"] == 1.0
    manifest = {
        "comparator": "fixed_candidate_mt5_ea_signal_parity",
        "join_key": "time_server",
        "python_csv": str(python_csv),
        "mql5_csv": str(mql5_csv),
        "output_dir": str(output_dir),
        "acceptance_passed": signal_parity_acceptance_passed,
        "signal_parity_acceptance_passed": signal_parity_acceptance_passed,
        "lifecycle_metadata_acceptance_passed": lifecycle_metadata_acceptance_passed,
        "mt5_connection_performed": False,
        "order_check_performed": False,
        "order_send_performed": False,
        "trade_operation_performed": False,
        **summary,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(output_dir / MANIFEST_NAME, manifest)
    write_summary(
        output_dir / SUMMARY_NAME,
        summary
        | {
            "acceptance_passed": signal_parity_acceptance_passed,
            "signal_parity_acceptance_passed": signal_parity_acceptance_passed,
            "lifecycle_metadata_acceptance_passed": lifecycle_metadata_acceptance_passed,
        },
    )
    write_dicts(
        output_dir / MISMATCHES_NAME,
        mismatches,
        [
            "row_index",
            "mql5_row_index",
            "time_server",
            "field",
            "python_value",
            "mql5_value",
            "mismatch_type",
            "absolute_diff",
            "tolerance",
        ],
    )
    write_dicts(
        output_dir / MISSING_TIMES_NAME,
        missing_times,
        ["row_index", "time_server", "source", "mismatch_type"],
    )
    write_dicts(
        output_dir / EXTRA_TIMES_NAME,
        extra_times,
        ["mql5_row_index", "time_server", "source", "mismatch_type", "allowed"],
    )
    write_dicts(
        output_dir / NEAR_MISSES_NAME,
        near_misses,
        [
            "row_index",
            "time_server",
            "field",
            "value",
            "cutoff_name",
            "cutoff",
            "distance",
            "near_threshold_epsilon",
            "source",
        ],
    )
    write_report(output_dir / REPORT_NAME, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare Python and MQL5 fixed-candidate signal-only parity CSVs."
    )
    parser.add_argument("--python-csv", type=Path, required=True)
    parser.add_argument("--mql5-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--numeric-tolerance", type=float, default=1e-9)
    parser.add_argument("--near-threshold-epsilon", type=float, default=0.02)
    parser.add_argument("--allow-extra-mql5-times", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = compare_parity_csvs(
            python_csv=args.python_csv,
            mql5_csv=args.mql5_csv,
            output_dir=args.output_dir,
            numeric_tolerance=args.numeric_tolerance,
            near_threshold_epsilon=args.near_threshold_epsilon,
            allow_extra_mql5_times=bool(args.allow_extra_mql5_times),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Fixed-candidate MQL5 signal parity comparison failed: {exc}")
        return 1

    print("Fixed-candidate MQL5 signal parity comparison complete.")
    print(f"Python rows: {manifest['python_row_count']}")
    print(f"MQL5 rows: {manifest['mql5_row_count']}")
    print(f"Aligned rows: {manifest['aligned_row_count']}")
    print(f"Mismatches: {manifest['mismatch_count']}")
    print(f"Acceptance passed: {manifest['acceptance_passed']}")
    return 0 if manifest["acceptance_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
