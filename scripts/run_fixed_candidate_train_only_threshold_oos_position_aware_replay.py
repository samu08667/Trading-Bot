from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts import run_fixed_candidate_train_only_threshold_oos_outcome_replay as base


DEFAULT_RUN_ID = "gbpusd_short_h10_1_5_off_hours_train_only_threshold_oos_position_aware_replay_v1"
DEFAULT_OUTPUT_ROOT = base.BASE_DIR / "reports" / "fixed_candidate_train_only_threshold_oos_position_aware_replay"
DEFAULT_SIGNAL_LEVEL_MANIFEST = (
    base.BASE_DIR
    / "reports"
    / "fixed_candidate_train_only_threshold_oos_outcome_replay"
    / "gbpusd_short_h10_1_5_off_hours_train_only_threshold_oos_outcome_replay_train_to_2024_12_31_v1"
    / "manifest.json"
)

MAX_OPEN_POSITIONS = 1

STATUS_AVAILABLE = "train_only_threshold_oos_position_aware_replay_available"
STATUS_AVAILABLE_NO_COMPARISON = (
    "train_only_threshold_oos_position_aware_replay_available_without_signal_level_comparison"
)
STATUS_MISSING_THRESHOLD = "train_only_threshold_oos_position_aware_replay_blocked_missing_threshold_artifact"
STATUS_NON_TRAIN_ONLY = "train_only_threshold_oos_position_aware_replay_blocked_non_train_only_thresholds"
STATUS_MISSING_DB = "train_only_threshold_oos_position_aware_replay_blocked_missing_db"
STATUS_MISSING_TABLE = "train_only_threshold_oos_position_aware_replay_blocked_missing_table"
STATUS_MISSING_COLUMNS = "train_only_threshold_oos_position_aware_replay_blocked_missing_columns"
STATUS_EMPTY_OOS = "train_only_threshold_oos_position_aware_replay_blocked_empty_oos_window"
STATUS_NONCANONICAL = "train_only_threshold_oos_position_aware_replay_blocked_noncanonical_candidate"
STATUS_MAX_OPEN_NOT_ONE = "train_only_threshold_oos_position_aware_replay_blocked_max_open_positions_not_one"
STATUS_OUTPUT_EXISTS = "train_only_threshold_oos_position_aware_replay_blocked_output_exists_without_overwrite"

VERDICT_RETAINS_EDGE = "position_aware_retains_edge"
VERDICT_DEGRADES_POSITIVE = "position_aware_degrades_but_positive"
VERDICT_NOT_SUPPORTED = "position_aware_edge_not_supported"
VERDICT_COMPARISON_UNAVAILABLE = "position_aware_comparison_unavailable"

OUTPUT_FILES = {
    "manifest": "manifest.json",
    "report": "report.md",
    "summary": "summary.csv",
    "accepted_trades": "accepted_trades.csv",
    "skipped_signals": "skipped_signals.csv",
    "equity_curve": "equity_curve.csv",
    "monthly_summary": "monthly_summary.csv",
    "condition_counts": "condition_counts.csv",
    "bucket_counts": "bucket_counts.csv",
    "comparison_vs_signal_level": "comparison_vs_signal_level.csv",
    "warnings": "warnings.csv",
    "no_order_evidence": "no_order_evidence.csv",
}

SUMMARY_FIELDS = [
    "run_id",
    "replay_status",
    "candidate_id",
    "symbol",
    "timeframe",
    "train_end_time",
    "oos_start_time",
    "oos_end_time",
    "oos_row_count",
    "off_hours_oos_row_count",
    "raw_rule_match_count",
    "accepted_trade_count",
    "skipped_overlap_signal_count",
    "overlap_skip_rate",
    "mean_R",
    "median_R",
    "sum_R",
    "profit_factor_R",
    "win_rate_R_positive",
    "max_drawdown_R",
    "tp_hit_count",
    "sl_hit_count",
    "timeout_count",
    "timeout_rate",
    "signal_level_comparison_available",
    "retained_trade_ratio",
    "sum_R_retention_ratio",
    "drawdown_change",
    "position_aware_verdict",
]

SKIPPED_SIGNAL_FIELDS = [
    "run_id",
    "signal_id",
    "time_server",
    "skip_reason",
    "active_trade_exit_time",
    "spread",
    base.FEATURE_A,
    f"{base.FEATURE_A}_bucket",
    base.FEATURE_B,
    f"{base.FEATURE_B}_bucket",
]

MONTHLY_FIELDS = [
    "run_id",
    "month",
    "accepted_trade_count",
    "sum_R",
    "mean_R",
    "tp_hit_count",
    "sl_hit_count",
    "timeout_count",
]

COMPARISON_FIELDS = [
    "run_id",
    "signal_level_comparison_available",
    "signal_level_trade_count",
    "signal_level_sum_R",
    "signal_level_profit_factor_R",
    "signal_level_max_drawdown_R",
    "accepted_trade_count",
    "sum_R",
    "profit_factor_R",
    "max_drawdown_R",
    "retained_trade_ratio",
    "sum_R_retention_ratio",
    "drawdown_change",
    "position_aware_verdict",
]


def output_dir_for_args(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    return DEFAULT_OUTPUT_ROOT / str(args.run_id)


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {label: output_dir / file_name for label, file_name in OUTPUT_FILES.items()}


def ensure_output_writable(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    paths = output_paths(output_dir)
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise base.BlockedStatusError(STATUS_OUTPUT_EXISTS, "Output files already exist; use --overwrite.")
    output_dir.mkdir(parents=True, exist_ok=True)
    return paths


def safe_int(value: Any) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def max_open_position_errors(args: argparse.Namespace, canonical: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if safe_int(args.max_open_positions) != MAX_OPEN_POSITIONS:
        errors.append("cli_max_open_positions")
    canonical_value = safe_int(canonical.get("max_open_positions"))
    if canonical_value not in (None, MAX_OPEN_POSITIONS):
        errors.append("canonical_max_open_positions")
    return errors


def read_optional_signal_manifest(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing_signal_level_manifest"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"unreadable_signal_level_manifest:{exc}"
    if not isinstance(payload, dict):
        return {}, "signal_level_manifest_not_object"
    return payload, ""


def ratio(numerator: Any, denominator: Any) -> float | None:
    num = base.safe_float(numerator)
    den = base.safe_float(denominator)
    if num is None or den in (None, 0.0):
        return None
    return num / den


def comparison_verdict(
    *,
    comparison_available: bool,
    accepted_trade_count: int,
    sum_r: Any,
    profit_factor_r: Any,
    retained_trade_ratio: float | None,
    sum_r_retention_ratio: float | None,
) -> str:
    if not comparison_available:
        return VERDICT_COMPARISON_UNAVAILABLE
    sum_value = base.safe_float(sum_r)
    profit_factor = base.safe_float(profit_factor_r)
    if accepted_trade_count == 0 or sum_value is None or sum_value <= 0 or profit_factor is None or profit_factor <= 1.0:
        return VERDICT_NOT_SUPPORTED
    if (
        retained_trade_ratio is not None
        and sum_r_retention_ratio is not None
        and retained_trade_ratio >= 0.8
        and sum_r_retention_ratio >= 0.8
    ):
        return VERDICT_RETAINS_EDGE
    return VERDICT_DEGRADES_POSITIVE


def compare_with_signal_level(
    *,
    run_id: str,
    signal_manifest: dict[str, Any],
    stats: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    comparison_available = bool(signal_manifest)
    signal_trade_count = signal_manifest.get("trade_count") if comparison_available else None
    signal_sum_r = signal_manifest.get("sum_R") if comparison_available else None
    signal_profit_factor = signal_manifest.get("profit_factor_R") if comparison_available else None
    signal_max_drawdown = signal_manifest.get("max_drawdown_R") if comparison_available else None
    retained_ratio = ratio(stats.get("accepted_trade_count"), signal_trade_count)
    sum_retention = ratio(stats.get("sum_R"), signal_sum_r)
    accepted_drawdown = base.safe_float(stats.get("max_drawdown_R"))
    signal_drawdown = base.safe_float(signal_max_drawdown)
    drawdown_change = None
    if accepted_drawdown is not None and signal_drawdown is not None:
        drawdown_change = accepted_drawdown - signal_drawdown
    verdict = comparison_verdict(
        comparison_available=comparison_available,
        accepted_trade_count=int(stats.get("accepted_trade_count") or 0),
        sum_r=stats.get("sum_R"),
        profit_factor_r=stats.get("profit_factor_R"),
        retained_trade_ratio=retained_ratio,
        sum_r_retention_ratio=sum_retention,
    )
    row = {
        "run_id": run_id,
        "signal_level_comparison_available": comparison_available,
        "signal_level_trade_count": signal_trade_count,
        "signal_level_sum_R": signal_sum_r,
        "signal_level_profit_factor_R": signal_profit_factor,
        "signal_level_max_drawdown_R": signal_max_drawdown,
        "accepted_trade_count": stats.get("accepted_trade_count"),
        "sum_R": stats.get("sum_R"),
        "profit_factor_R": stats.get("profit_factor_R"),
        "max_drawdown_R": stats.get("max_drawdown_R"),
        "retained_trade_ratio": retained_ratio,
        "sum_R_retention_ratio": sum_retention,
        "drawdown_change": drawdown_change,
        "position_aware_verdict": verdict,
    }
    return row, verdict


def replay_position_aware_rows(
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    train_end_time: str,
    cutoffs: dict[str, dict[str, float]],
    warnings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int, int]:
    accepted_trades: list[dict[str, Any]] = []
    skipped_signals: list[dict[str, Any]] = []
    bucket_a_counts = {"low_tercile": 0, "mid_tercile": 0, "high_tercile": 0, "missing": 0}
    bucket_b_counts = {"low_tercile": 0, "mid_tercile": 0, "high_tercile": 0, "missing": 0}
    condition_counts = {
        "session_pass": 0,
        "spread_pass": 0,
        f"{base.FEATURE_A}_high_tercile": 0,
        f"{base.FEATURE_B}_mid_tercile": 0,
        "raw_rule_match": 0,
        "accepted_trade": 0,
        "skipped_overlap_signal": 0,
    }
    active_trade_exit_time = ""
    raw_rule_match_count = 0
    skipped_overlap_count = 0
    for index, row in enumerate(rows):
        time_server = str(row.get("time_server") or "")
        if time_server <= train_end_time:
            continue
        gate = base.entry_gate(row, cutoffs, args)
        bucket_a_counts[gate["bucket_a"]] += 1
        bucket_b_counts[gate["bucket_b"]] += 1
        if gate["session_pass"]:
            condition_counts["session_pass"] += 1
        if gate["spread_pass"]:
            condition_counts["spread_pass"] += 1
        if gate["bucket_a"] == "high_tercile":
            condition_counts[f"{base.FEATURE_A}_high_tercile"] += 1
        if gate["bucket_b"] == "mid_tercile":
            condition_counts[f"{base.FEATURE_B}_mid_tercile"] += 1
        if not gate["rule_match"]:
            continue
        raw_rule_match_count += 1
        condition_counts["raw_rule_match"] += 1
        signal_id = f"{args.run_id}_{raw_rule_match_count:06d}"
        if active_trade_exit_time and time_server <= active_trade_exit_time:
            skipped_overlap_count += 1
            condition_counts["skipped_overlap_signal"] += 1
            skipped_signals.append(
                {
                    "run_id": str(args.run_id),
                    "signal_id": signal_id,
                    "time_server": time_server,
                    "skip_reason": "overlaps_active_trade",
                    "active_trade_exit_time": active_trade_exit_time,
                    "spread": gate["spread"],
                    base.FEATURE_A: gate["feature_a"],
                    f"{base.FEATURE_A}_bucket": gate["bucket_a"],
                    base.FEATURE_B: gate["feature_b"],
                    f"{base.FEATURE_B}_bucket": gate["bucket_b"],
                }
            )
            continue
        trade = base.simulate_trade(
            rows=rows,
            entry_index=index,
            gate=gate,
            run_id=str(args.run_id),
            signal_id=signal_id,
            trade_index=len(accepted_trades) + 1,
            warnings=warnings,
        )
        if trade is None:
            continue
        accepted_trades.append(trade)
        condition_counts["accepted_trade"] += 1
        active_trade_exit_time = str(trade.get("exit_time_server") or time_server)
    bucket_rows = [
        *base.count_rows(base.FEATURE_A, bucket_a_counts),
        *base.count_rows(base.FEATURE_B, bucket_b_counts),
    ]
    condition_rows = base.count_rows("condition", condition_counts)
    return (
        accepted_trades,
        skipped_signals,
        bucket_rows,
        condition_rows,
        raw_rule_match_count,
        skipped_overlap_count,
    )


def monthly_summary(run_id: str, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = {}
    reasons: dict[str, dict[str, int]] = {}
    for trade in trades:
        month = str(trade.get("entry_time_server") or "")[:7]
        if not month:
            continue
        value = base.safe_float(trade.get("R_multiple"))
        grouped.setdefault(month, [])
        reasons.setdefault(month, {"paper_tp_hit": 0, "paper_sl_hit": 0, "paper_timeout": 0})
        if value is not None:
            grouped[month].append(value)
        reason = str(trade.get("exit_reason") or "")
        if reason in reasons[month]:
            reasons[month][reason] += 1
    rows: list[dict[str, Any]] = []
    for month in sorted(grouped):
        values = grouped[month]
        rows.append(
            {
                "run_id": run_id,
                "month": month,
                "accepted_trade_count": len(values),
                "sum_R": sum(values) if values else None,
                "mean_R": (sum(values) / len(values)) if values else None,
                "tp_hit_count": reasons[month]["paper_tp_hit"],
                "sl_hit_count": reasons[month]["paper_sl_hit"],
                "timeout_count": reasons[month]["paper_timeout"],
            }
        )
    return rows


def accepted_trade_metrics(trades: list[dict[str, Any]], raw_rule_match_count: int, skipped_overlap_count: int) -> dict[str, Any]:
    stats = base.metrics(trades)
    accepted_count = int(stats["trade_count"])
    stats["accepted_trade_count"] = accepted_count
    stats["raw_rule_match_count"] = raw_rule_match_count
    stats["skipped_overlap_signal_count"] = skipped_overlap_count
    stats["overlap_skip_rate"] = (skipped_overlap_count / raw_rule_match_count) if raw_rule_match_count else None
    return stats


def derive_status(
    *,
    threshold_missing: bool,
    non_train_only: bool,
    noncanonical: bool,
    max_open_errors: bool,
    db_exists: bool,
    table_exists: bool,
    missing_columns: list[str],
    oos_row_count: int,
    comparison_available: bool,
) -> str:
    if threshold_missing:
        return STATUS_MISSING_THRESHOLD
    if noncanonical:
        return STATUS_NONCANONICAL
    if non_train_only:
        return STATUS_NON_TRAIN_ONLY
    if max_open_errors:
        return STATUS_MAX_OPEN_NOT_ONE
    if not db_exists:
        return STATUS_MISSING_DB
    if not table_exists:
        return STATUS_MISSING_TABLE
    if missing_columns:
        return STATUS_MISSING_COLUMNS
    if oos_row_count == 0:
        return STATUS_EMPTY_OOS
    if not comparison_available:
        return STATUS_AVAILABLE_NO_COMPARISON
    return STATUS_AVAILABLE


def build_model(args: argparse.Namespace) -> dict[str, Any]:
    run_id = str(args.run_id)
    threshold_path = Path(args.train_only_thresholds)
    canonical_path = Path(args.canonical_registry)
    db_path = Path(args.db_path)
    signal_manifest_path = Path(args.signal_level_oos_replay_manifest)
    threshold_payload, threshold_error = base.read_json_object(threshold_path)
    canonical_payload, canonical_error = base.read_json_object(canonical_path)
    signal_manifest, signal_manifest_error = read_optional_signal_manifest(signal_manifest_path)
    warnings: list[dict[str, Any]] = []
    if threshold_error:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="missing_threshold_artifact",
                message=f"Threshold artifact missing or unreadable: {threshold_error}",
                source=threshold_path,
                blocking_warning=True,
            )
        )
    non_train_errors, threshold_noncanonical = (
        base.threshold_validation_errors(threshold_payload, args) if threshold_payload else ([], [])
    )
    if non_train_errors:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="non_train_only_thresholds",
                message="Threshold artifact failed train-only checks: " + ", ".join(non_train_errors),
                source=threshold_path,
                blocking_warning=True,
            )
        )
    canonical_errors = base.canonical_mismatches(args, canonical_payload, canonical_error)
    max_open_errors = max_open_position_errors(args, canonical_payload)
    noncanonical_items = [*threshold_noncanonical, *canonical_errors]
    if noncanonical_items:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="noncanonical_candidate",
                message="Candidate identity or required condition mismatch: " + ", ".join(noncanonical_items),
                source=canonical_path,
                blocking_warning=True,
            )
        )
    if max_open_errors:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="max_open_positions_not_one",
                message="Position-aware replay requires max_open_positions = 1: " + ", ".join(max_open_errors),
                source=canonical_path,
                blocking_warning=True,
            )
        )
    if signal_manifest_error:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="signal_level_comparison_unavailable",
                message=f"Signal-level OOS replay manifest not available for comparison: {signal_manifest_error}",
                source=signal_manifest_path,
                blocking_warning=False,
            )
        )
    db_exists = db_path.exists()
    if not db_exists:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="missing_db",
                message="SQLite DB is missing.",
                source=db_path,
                blocking_warning=True,
            )
        )
    table_exists = False
    columns: set[str] = set()
    schema_error = ""
    connection: sqlite3.Connection | None = None
    if db_exists:
        try:
            connection = base.connect_read_only(db_path)
            table_exists, columns, schema_error = base.inspect_table(db_path, str(args.feature_table))
        except sqlite3.Error as exc:
            schema_error = str(exc)
    if db_exists and not table_exists:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="missing_table",
                message=f"Feature table missing or unreadable: {schema_error}",
                source=args.feature_table,
                blocking_warning=True,
            )
        )
    missing_columns = sorted(base.required_columns(args) - columns) if table_exists else []
    if missing_columns:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="missing_columns",
                message="Feature table is missing required columns: " + ", ".join(missing_columns),
                source=args.feature_table,
                blocking_warning=True,
            )
        )

    train_end_time = str(threshold_payload.get("train_end_time") or "")
    source_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    oos_start_time = str(args.oos_start_time or "")
    oos_end_time = str(args.oos_end_time or "")
    oos_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    offhours_info = {"row_count": 0, "min_time_server": "", "max_time_server": ""}
    rows: list[dict[str, Any]] = []
    accepted_trades: list[dict[str, Any]] = []
    skipped_signals: list[dict[str, Any]] = []
    bucket_counts: list[dict[str, Any]] = []
    condition_counts: list[dict[str, Any]] = []
    raw_rule_match_count = 0
    skipped_overlap_count = 0
    cutoffs = base.threshold_cutoffs(threshold_payload) if threshold_payload else {}
    can_query = (
        db_exists
        and table_exists
        and not missing_columns
        and not threshold_error
        and not non_train_errors
        and not noncanonical_items
        and not max_open_errors
        and bool(train_end_time)
        and bool(cutoffs)
        and connection is not None
    )
    if can_query and connection is not None:
        source_filters, source_params = base.source_filters(args, columns)
        source_info = base.one_row_window_query(
            connection=connection,
            table_name=str(args.feature_table),
            filters=source_filters,
            params=source_params,
        )
        first_after_filters = [*source_filters, f"{base.quote_identifier('time_server')} > ?"]
        first_after_params = [*source_params, train_end_time]
        first_after = base.one_row_window_query(
            connection=connection,
            table_name=str(args.feature_table),
            filters=first_after_filters,
            params=first_after_params,
        )
        if not oos_start_time:
            oos_start_time = first_after["min_time_server"] or base.plus_one_second_text(train_end_time)
        if not oos_end_time:
            oos_end_time = first_after["max_time_server"]
        oos_filters = [
            *source_filters,
            f"{base.quote_identifier('time_server')} > ?",
            f"{base.quote_identifier('time_server')} >= ?",
        ]
        oos_params: list[Any] = [*source_params, train_end_time, oos_start_time]
        if oos_end_time:
            oos_filters.append(f"{base.quote_identifier('time_server')} <= ?")
            oos_params.append(oos_end_time)
        oos_info = base.one_row_window_query(
            connection=connection,
            table_name=str(args.feature_table),
            filters=oos_filters,
            params=oos_params,
        )
        off_filters = [*oos_filters, f"{base.quote_identifier(str(args.session_column))} = ?"]
        off_params = [*oos_params, str(args.required_session)]
        offhours_info = base.one_row_window_query(
            connection=connection,
            table_name=str(args.feature_table),
            filters=off_filters,
            params=off_params,
        )
        rows = base.fetch_price_rows(
            connection=connection,
            table_name=str(args.feature_table),
            columns=columns,
            filters=oos_filters,
            params=oos_params,
            session_column=str(args.session_column),
        )
        if rows:
            (
                accepted_trades,
                skipped_signals,
                bucket_counts,
                condition_counts,
                raw_rule_match_count,
                skipped_overlap_count,
            ) = replay_position_aware_rows(
                args=args,
                rows=rows,
                train_end_time=train_end_time,
                cutoffs=cutoffs,
                warnings=warnings,
            )
    if connection is not None:
        connection.close()
    if can_query and oos_info["row_count"] == 0:
        warnings.append(
            base.warning_row(
                run_id=run_id,
                warning_code="empty_oos_window",
                message="No OOS rows found after applying train-end and OOS filters.",
                source=args.feature_table,
                blocking_warning=True,
            )
        )

    stats = accepted_trade_metrics(accepted_trades, raw_rule_match_count, skipped_overlap_count)
    comparison_row, verdict = compare_with_signal_level(
        run_id=run_id,
        signal_manifest=signal_manifest,
        stats=stats,
    )
    replay_status = derive_status(
        threshold_missing=bool(threshold_error),
        non_train_only=bool(non_train_errors),
        noncanonical=bool(noncanonical_items),
        max_open_errors=bool(max_open_errors),
        db_exists=db_exists,
        table_exists=table_exists,
        missing_columns=missing_columns,
        oos_row_count=int(oos_info["row_count"] or 0),
        comparison_available=bool(signal_manifest),
    )
    manifest = {
        "run_id": run_id,
        "replay_status": replay_status,
        "candidate_id": base.EXPECTED_CANDIDATE_ID,
        "symbol": str(args.symbol),
        "timeframe": str(args.timeframe),
        "direction": base.DEFAULT_DIRECTION,
        "train_only_threshold_artifact": str(threshold_path),
        "signal_level_oos_replay_manifest": str(signal_manifest_path),
        "threshold_lineage": threshold_payload.get("threshold_lineage", ""),
        "calibration_scope": threshold_payload.get("calibration_scope", ""),
        "train_end_time": train_end_time,
        "oos_start_time": oos_start_time,
        "oos_end_time": oos_end_time,
        "source_row_count": source_info["row_count"],
        "source_min_time_server": source_info["min_time_server"],
        "source_max_time_server": source_info["max_time_server"],
        "oos_row_count": oos_info["row_count"],
        "off_hours_oos_row_count": offhours_info["row_count"],
        "raw_rule_match_count": raw_rule_match_count,
        "accepted_trade_count": stats["accepted_trade_count"],
        "skipped_overlap_signal_count": skipped_overlap_count,
        "overlap_skip_rate": stats["overlap_skip_rate"],
        "max_open_positions": safe_int(args.max_open_positions),
        "tp_atr": base.TP_ATR,
        "sl_atr": base.SL_ATR,
        "horizon_bars": base.HORIZON_BARS,
        "same_bar_policy": base.SAME_BAR_POLICY,
        "max_spread_points": float(args.max_spread_points),
        "feature_table": str(args.feature_table),
        "db_path": str(db_path),
        "missing_required_columns": missing_columns,
        "signal_level_comparison_available": bool(signal_manifest),
        "retained_trade_ratio": comparison_row["retained_trade_ratio"],
        "sum_R_retention_ratio": comparison_row["sum_R_retention_ratio"],
        "drawdown_change": comparison_row["drawdown_change"],
        "position_aware_verdict": verdict,
        "canonical_registry_sha256": (
            base.sha256_file(canonical_path) if canonical_path.exists() and not canonical_error else ""
        ),
        "threshold_artifact_sha256": (
            base.sha256_file(threshold_path) if threshold_path.exists() and not threshold_error else ""
        ),
        "warnings_count": len(warnings),
        "blocking_warnings_count": sum(bool(warning["blocking_warning"]) for warning in warnings),
        "created_at_utc": base.utc_now_text(),
        "output_files": {},
        **stats,
        **base.NO_ORDER_EVIDENCE,
    }
    summary = [{field: manifest.get(field) for field in SUMMARY_FIELDS}]
    no_order_evidence = [
        {"evidence_name": key, "value": value, "note": "artifact_only_position_aware_oos_replay"}
        for key, value in base.NO_ORDER_EVIDENCE.items()
    ]
    return {
        "manifest": manifest,
        "summary": summary,
        "accepted_trades": accepted_trades,
        "skipped_signals": skipped_signals,
        "equity_curve": base.equity_curve(run_id, accepted_trades),
        "monthly_summary": monthly_summary(run_id, accepted_trades),
        "condition_counts": condition_counts,
        "bucket_counts": bucket_counts,
        "comparison_vs_signal_level": [comparison_row],
        "warnings": warnings,
        "no_order_evidence": no_order_evidence,
    }


def report_text(model: dict[str, Any]) -> str:
    manifest = model["manifest"]
    lines = [
        "# Fixed Candidate Train-Only Threshold OOS Position-Aware Replay",
        "",
        "Artifact-only OOS replay using frozen train-only thresholds and max_open_positions = 1.",
        "",
        "## Status",
        "",
        f"- replay_status: `{manifest['replay_status']}`",
        f"- train_end_time: `{manifest['train_end_time']}`",
        f"- oos_start_time: `{manifest['oos_start_time']}`",
        f"- oos_end_time: `{manifest['oos_end_time']}`",
        f"- raw_rule_match_count: `{manifest['raw_rule_match_count']}`",
        f"- accepted_trade_count: `{manifest['accepted_trade_count']}`",
        f"- skipped_overlap_signal_count: `{manifest['skipped_overlap_signal_count']}`",
        f"- overlap_skip_rate: `{manifest['overlap_skip_rate']}`",
        "",
        "## Metrics",
        "",
        f"- mean_R: `{manifest['mean_R']}`",
        f"- median_R: `{manifest['median_R']}`",
        f"- sum_R: `{manifest['sum_R']}`",
        f"- profit_factor_R: `{manifest['profit_factor_R']}`",
        f"- win_rate_R_positive: `{manifest['win_rate_R_positive']}`",
        f"- max_drawdown_R: `{manifest['max_drawdown_R']}`",
        "",
        "## Signal-Level Comparison",
        "",
        f"- signal_level_comparison_available: `{manifest['signal_level_comparison_available']}`",
        f"- retained_trade_ratio: `{manifest['retained_trade_ratio']}`",
        f"- sum_R_retention_ratio: `{manifest['sum_R_retention_ratio']}`",
        f"- position_aware_verdict: `{manifest['position_aware_verdict']}`",
        "",
        "No MT5, broker API, order_check, order_send, DB mutation, future-state mutation, or scheduler behavior is performed.",
    ]
    return "\n".join(lines) + "\n"


def build_outputs(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = output_dir_for_args(args)
    paths = ensure_output_writable(output_dir, bool(args.overwrite))
    model = build_model(args)
    model["manifest"]["output_files"] = {label: str(path) for label, path in paths.items()}
    base.write_json(paths["manifest"], model["manifest"])
    paths["report"].write_text(report_text(model), encoding="utf-8")
    base.write_csv(paths["summary"], model["summary"], SUMMARY_FIELDS)
    base.write_csv(paths["accepted_trades"], model["accepted_trades"], base.TRADE_FIELDS)
    base.write_csv(paths["skipped_signals"], model["skipped_signals"], SKIPPED_SIGNAL_FIELDS)
    base.write_csv(paths["equity_curve"], model["equity_curve"], base.EQUITY_FIELDS)
    base.write_csv(paths["monthly_summary"], model["monthly_summary"], MONTHLY_FIELDS)
    base.write_csv(paths["condition_counts"], model["condition_counts"], base.COUNT_FIELDS)
    base.write_csv(paths["bucket_counts"], model["bucket_counts"], base.COUNT_FIELDS)
    base.write_csv(paths["comparison_vs_signal_level"], model["comparison_vs_signal_level"], COMPARISON_FIELDS)
    base.write_csv(paths["warnings"], model["warnings"], base.WARNING_FIELDS)
    base.write_csv(paths["no_order_evidence"], model["no_order_evidence"], ["evidence_name", "value", "note"])
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute artifact-only position-aware OOS outcomes using train-only fixed-candidate thresholds."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--db-path", type=Path, default=base.DEFAULT_DB_PATH)
    parser.add_argument("--feature-table", default=base.DEFAULT_FEATURE_TABLE)
    parser.add_argument("--train-only-thresholds", type=Path, default=base.DEFAULT_TRAIN_ONLY_THRESHOLDS)
    parser.add_argument("--signal-level-oos-replay-manifest", type=Path, default=DEFAULT_SIGNAL_LEVEL_MANIFEST)
    parser.add_argument("--canonical-registry", type=Path, default=base.DEFAULT_CANONICAL_REGISTRY)
    parser.add_argument("--symbol", default=base.DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=base.DEFAULT_TIMEFRAME)
    parser.add_argument("--oos-start-time")
    parser.add_argument("--oos-end-time")
    parser.add_argument("--session-column", default=base.DEFAULT_SESSION_COLUMN)
    parser.add_argument("--required-session", default=base.DEFAULT_REQUIRED_SESSION)
    parser.add_argument("--max-spread-points", type=float, default=base.DEFAULT_MAX_SPREAD_POINTS)
    parser.add_argument("--max-open-positions", type=int, default=MAX_OPEN_POSITIONS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = build_outputs(args)
    manifest = base.read_json_object(paths["manifest"])[0]
    print("Fixed-candidate train-only threshold OOS position-aware replay complete.")
    print(f"replay_status: {manifest['replay_status']}")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0 if manifest["replay_status"] in {STATUS_AVAILABLE, STATUS_AVAILABLE_NO_COMPARISON} else 1


if __name__ == "__main__":
    raise SystemExit(main())
