from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from research_costs import validate_cost_args
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_horizon_consistency_report
    from scripts.research_costs import validate_cost_args

try:
    from research_metrics import csv_safe_value, normalize_direction, safe_float
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.build_horizon_consistency_report
    from scripts.research_metrics import csv_safe_value, normalize_direction, safe_float


HORIZONS = ("h5", "h10", "h20")

SUMMARY_FIELDS = [
    "scope",
    "symbol",
    "feature",
    "condition",
    "feature_condition_key",
    "direction",
    "cost_mode",
    "return_mode",
    "h5_classification",
    "h10_classification",
    "h20_classification",
    "h5_score",
    "h10_score",
    "h20_score",
    "h5_avg_profit_factor_improvement_pct",
    "h10_avg_profit_factor_improvement_pct",
    "h20_avg_profit_factor_improvement_pct",
    "h5_avg_max_drawdown_improvement_pct",
    "h10_avg_max_drawdown_improvement_pct",
    "h20_avg_max_drawdown_improvement_pct",
    "horizon_consistency_classification",
    "consistency_score",
    "interpretation_note",
    "next_step_note",
]

WARNING_FIELDS = [
    "warning_type",
    "horizon",
    "scope",
    "path",
    "message",
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_safe_value(row.get(field)) for field in fieldnames})


def ensure_outputs_writable(paths: list[Path], overwrite: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Output files already exist: {joined}. Use --overwrite to replace them.")


def warning_row(
    warning_type: str,
    *,
    horizon: str = "",
    scope: str = "",
    path: Path | str = "",
    message: str,
) -> dict[str, str]:
    return {
        "warning_type": warning_type,
        "horizon": horizon,
        "scope": scope,
        "path": str(path),
        "message": message,
    }


def row_matches_mode(row: dict[str, str], direction: str, cost_mode: str, return_mode: str) -> bool:
    row_direction = str(row.get("direction") or direction).strip().lower()
    row_cost_mode = str(row.get("cost_mode") or cost_mode).strip().lower()
    row_return_mode = str(row.get("return_mode") or return_mode).strip().lower()
    return row_direction == direction and row_cost_mode == cost_mode and row_return_mode == return_mode


def score_from_row(row: dict[str, str]) -> float | None:
    return safe_float(row.get("total_score") or row.get("pair_specific_score"))


def classification_from_row(row: dict[str, str], scope: str) -> str:
    if scope == "pair_specific":
        return str(row.get("pair_specific_classification") or row.get("final_feature_classification") or "").strip()
    return str(row.get("final_feature_classification") or row.get("pair_specific_classification") or "").strip()


def normalized_symbol(row: dict[str, str], scope: str) -> str:
    if scope == "pair_specific":
        return str(row.get("symbol") or "").strip().upper()
    return ""


def comparable_key(row: dict[str, str], scope: str) -> tuple[str, str, str]:
    key = str(row.get("feature_condition_key") or "").strip()
    if not key:
        feature = str(row.get("feature") or "").strip()
        condition = str(row.get("condition") or "").strip()
        key = f"{feature}:{condition}" if feature or condition else ""
    return scope, normalized_symbol(row, scope), key


def choose_best_row(existing: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return candidate
    existing_score = safe_float(existing.get("score"))
    candidate_score = safe_float(candidate.get("score"))
    if candidate_score is None:
        return existing
    if existing_score is None or candidate_score > existing_score:
        return candidate
    return existing


def load_scorecard_rows(
    path: Path,
    *,
    horizon: str,
    scope: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
    warnings: list[dict[str, str]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not path.exists():
        warnings.append(
            warning_row(
                "missing_input_file",
                horizon=horizon,
                scope=scope,
                path=path,
                message=f"{scope} scorecard file not found for {horizon}.",
            )
        )
        return {}

    rows = read_csv_rows(path)
    if not rows:
        warnings.append(
            warning_row(
                "empty_input_file",
                horizon=horizon,
                scope=scope,
                path=path,
                message=f"{scope} scorecard file is empty for {horizon}.",
            )
        )
        return {}

    loaded: dict[tuple[str, str, str], dict[str, Any]] = {}
    skipped_mode = 0
    skipped_key = 0
    for row in rows:
        if not row_matches_mode(row, direction, cost_mode, return_mode):
            skipped_mode += 1
            continue
        scope_key, symbol, feature_condition_key = comparable_key(row, scope)
        if not feature_condition_key:
            skipped_key += 1
            continue
        score = score_from_row(row)
        loaded_row = {
            "scope": scope_key,
            "symbol": symbol,
            "feature": str(row.get("feature") or "").strip(),
            "condition": str(row.get("condition") or "").strip(),
            "feature_condition_key": feature_condition_key,
            "classification": classification_from_row(row, scope),
            "score": score,
            "avg_positive_year_ratio": safe_float(row.get("avg_positive_year_ratio")),
            "avg_positive_symbol_ratio": safe_float(row.get("avg_positive_symbol_ratio")),
            "avg_profit_factor_improvement_pct": safe_float(row.get("avg_profit_factor_improvement_pct")),
            "avg_max_drawdown_improvement_pct": safe_float(row.get("avg_max_drawdown_improvement_pct")),
            "monthly_positive_ratio": safe_float(row.get("monthly_positive_ratio")),
            "quarterly_positive_ratio": safe_float(row.get("quarterly_positive_ratio")),
            "best_month_contribution_pct": safe_float(row.get("best_month_contribution_pct")),
            "top_5_percent_trades_contribution_pct": safe_float(row.get("top_5_percent_trades_contribution_pct")),
        }
        key = (scope_key, symbol, feature_condition_key)
        loaded[key] = choose_best_row(loaded.get(key), loaded_row)

    if skipped_mode:
        warnings.append(
            warning_row(
                "mode_filter_skipped_rows",
                horizon=horizon,
                scope=scope,
                path=path,
                message=(
                    f"Skipped {skipped_mode} rows with direction/cost/return mode different "
                    f"from {direction}/{cost_mode}/{return_mode}."
                ),
            )
        )
    if skipped_key:
        warnings.append(
            warning_row(
                "missing_feature_condition_key",
                horizon=horizon,
                scope=scope,
                path=path,
                message=f"Skipped {skipped_key} rows without feature_condition_key.",
            )
        )
    return loaded


def load_optional_candidates(
    path: Path,
    *,
    horizon: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
    warnings: list[dict[str, str]],
) -> int:
    if not path.exists():
        warnings.append(
            warning_row(
                "missing_optional_validation_candidates",
                horizon=horizon,
                scope="cross_pair",
                path=path,
                message=f"Optional final_research_candidates.csv not found for {horizon}.",
            )
        )
        return 0
    rows = read_csv_rows(path)
    matching = [row for row in rows if row_matches_mode(row, direction, cost_mode, return_mode)]
    if rows and not matching:
        warnings.append(
            warning_row(
                "optional_candidates_mode_mismatch",
                horizon=horizon,
                scope="cross_pair",
                path=path,
                message=f"No optional candidate rows matched {direction}/{cost_mode}/{return_mode}.",
            )
        )
    return len(matching)


def is_positive_classification(classification: str) -> bool:
    value = classification.strip().lower()
    return value in {
        "strong",
        "interesting",
        "strong_pair_specific",
        "interesting_pair_specific",
        "select",
        "watchlist",
        "select_pair_specific",
        "watchlist_pair_specific",
    }


def is_weak_or_negative(metrics: dict[str, Any] | None) -> bool:
    if not metrics:
        return False
    classification = str(metrics.get("classification") or "").lower()
    score = safe_float(metrics.get("score"))
    pf = safe_float(metrics.get("avg_profit_factor_improvement_pct"))
    dd = safe_float(metrics.get("avg_max_drawdown_improvement_pct"))
    if classification in {"weak", "weak_pair_specific", "excluded", "reject", "reject_pair_specific"}:
        return True
    if score is not None and score <= 0:
        return True
    if pf is not None and pf < 0:
        return True
    if dd is not None and dd < -10:
        return True
    return False


def is_disastrous(metrics: dict[str, Any] | None) -> bool:
    if not metrics:
        return False
    classification = str(metrics.get("classification") or "").lower()
    score = safe_float(metrics.get("score"))
    pf = safe_float(metrics.get("avg_profit_factor_improvement_pct"))
    dd = safe_float(metrics.get("avg_max_drawdown_improvement_pct"))
    if classification in {"excluded", "reject", "reject_pair_specific"}:
        return True
    if score is not None and score <= -3:
        return True
    if pf is not None and pf <= -10:
        return True
    if dd is not None and dd <= -25:
        return True
    return False


def is_good(metrics: dict[str, Any] | None) -> bool:
    if not metrics:
        return False
    classification = str(metrics.get("classification") or "")
    score = safe_float(metrics.get("score"))
    pf = safe_float(metrics.get("avg_profit_factor_improvement_pct"))
    dd = safe_float(metrics.get("avg_max_drawdown_improvement_pct"))
    if not is_positive_classification(classification):
        return False
    if score is not None and score < 2:
        return False
    if pf is not None and pf < 0:
        return False
    if dd is not None and dd < -10:
        return False
    return True


def has_metric_contradiction(horizon_rows: dict[str, dict[str, Any] | None]) -> bool:
    present = [row for row in horizon_rows.values() if row]
    pf_values = [safe_float(row.get("avg_profit_factor_improvement_pct")) for row in present]
    dd_values = [safe_float(row.get("avg_max_drawdown_improvement_pct")) for row in present]
    pf_values = [value for value in pf_values if value is not None]
    dd_values = [value for value in dd_values if value is not None]
    if pf_values and max(pf_values) >= 5 and min(pf_values) <= -5:
        return True
    if dd_values and max(dd_values) >= 10 and min(dd_values) <= -20:
        return True
    return False


def average_score(horizon_rows: dict[str, dict[str, Any] | None]) -> float:
    values = [
        value
        for value in (safe_float(row.get("score")) for row in horizon_rows.values() if row)
        if value is not None
    ]
    return sum(values) / len(values) if values else 0.0


def classify_horizon_consistency(
    horizon_rows: dict[str, dict[str, Any] | None],
) -> tuple[str, int, str, str]:
    present_count = sum(1 for row in horizon_rows.values() if row)
    if present_count < 2:
        return (
            "insufficient_evidence",
            0,
            "Present on fewer than two horizons.",
            "Collect comparable h5/h10/h20 evidence before interpreting this row.",
        )

    good = {horizon: is_good(row) for horizon, row in horizon_rows.items()}
    weak = {horizon: is_weak_or_negative(row) for horizon, row in horizon_rows.items()}
    disastrous = {horizon: is_disastrous(row) for horizon, row in horizon_rows.items()}
    good_count = sum(1 for value in good.values() if value)
    contradiction = has_metric_contradiction(horizon_rows)
    base_score = max(0, min(100, round(50 + average_score(horizon_rows) * 5)))

    if good["h10"] and good["h20"] and not good["h5"] and not disastrous["h5"] and not contradiction:
        return (
            "consistent_medium_slow",
            max(base_score, 75),
            "Weak or absent at h5, but coherent on h10 and h20.",
            "Treat as a possible medium/slow research effect; still require random baseline, diagnostics, and rule-based testing.",
        )

    if good["h5"] and not good["h10"] and not good["h20"]:
        if disastrous["h10"] or disastrous["h20"] or contradiction:
            classification = "unstable_across_horizons"
            note = "Positive at h5 but contradicted by weaker longer horizons."
            score = min(base_score, 30)
        else:
            classification = "short_horizon_only"
            note = "Evidence appears concentrated at h5 and is not confirmed by h10/h20."
            score = max(min(base_score, 60), 45)
        return (
            classification,
            score,
            note,
            "Review as a short-horizon research lead only; do not generalize to slower horizons.",
        )

    if good["h20"] and not good["h5"] and not good["h10"]:
        if disastrous["h5"] or disastrous["h10"] or contradiction:
            classification = "unstable_across_horizons"
            note = "Positive at h20 but contradicted by shorter horizons."
            score = min(base_score, 30)
        else:
            classification = "long_horizon_only"
            note = "Evidence appears only at h20 and is not confirmed by h5/h10."
            score = max(min(base_score, 60), 45)
        return (
            classification,
            score,
            note,
            "Review as a slower-horizon research lead only; do not convert into a strategy.",
        )

    if good_count >= 2 and not any(disastrous.values()) and not contradiction:
        return (
            "consistent_across_horizons",
            max(base_score, 80),
            "Positive evidence appears on at least two nearby horizons without major contradiction.",
            "Eligible for further research-only review after random baseline, diagnostics, and rule-based tests.",
        )

    if good_count == 0:
        return (
            "insufficient_evidence" if not any(weak.values()) else "unstable_across_horizons",
            min(base_score, 20),
            "No horizon provides clearly positive comparable evidence.",
            "Do not prioritize without stronger horizon evidence.",
        )

    return (
        "unstable_across_horizons",
        min(base_score, 35),
        "Evidence is positive on one horizon but weak, negative, or contradictory on nearby horizons.",
        "Declassify until a future run shows more stable behavior across horizons.",
    )


def summary_row_from_key(
    key: tuple[str, str, str],
    horizon_rows: dict[str, dict[str, Any] | None],
    *,
    direction: str,
    cost_mode: str,
    return_mode: str,
) -> dict[str, Any]:
    representative = next((row for row in horizon_rows.values() if row), {})
    classification, score, note, next_step_note = classify_horizon_consistency(horizon_rows)
    row: dict[str, Any] = {
        "scope": key[0],
        "symbol": key[1],
        "feature": representative.get("feature", ""),
        "condition": representative.get("condition", ""),
        "feature_condition_key": key[2],
        "direction": direction,
        "cost_mode": cost_mode,
        "return_mode": return_mode,
        "horizon_consistency_classification": classification,
        "consistency_score": score,
        "interpretation_note": note,
        "next_step_note": next_step_note,
    }
    for horizon in HORIZONS:
        horizon_row = horizon_rows.get(horizon) or {}
        row[f"{horizon}_classification"] = horizon_row.get("classification", "")
        row[f"{horizon}_score"] = horizon_row.get("score", "")
        row[f"{horizon}_avg_profit_factor_improvement_pct"] = horizon_row.get(
            "avg_profit_factor_improvement_pct", ""
        )
        row[f"{horizon}_avg_max_drawdown_improvement_pct"] = horizon_row.get(
            "avg_max_drawdown_improvement_pct", ""
        )
    return row


def table_for(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| scope | symbol | feature_condition_key | h5 | h10 | h20 | score | note |",
        "| --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in rows[:20]:
        lines.append(
            "| {scope} | {symbol} | {key} | {h5} | {h10} | {h20} | {score} | {note} |".format(
                scope=row.get("scope", ""),
                symbol=row.get("symbol", ""),
                key=str(row.get("feature_condition_key", "")).replace("|", "\\|"),
                h5=row.get("h5_classification", ""),
                h10=row.get("h10_classification", ""),
                h20=row.get("h20_classification", ""),
                score=csv_safe_value(row.get("consistency_score")),
                note=str(row.get("interpretation_note", "")).replace("|", "\\|"),
            )
        )
    if len(lines) == 2:
        lines.append("| none |  |  |  |  |  |  |  |")
    return lines


def build_markdown_report(
    *,
    group_id: str,
    direction: str,
    cost_mode: str,
    return_mode: str,
    run_ids: dict[str, str],
    summary_rows: list[dict[str, Any]],
    warnings: list[dict[str, str]],
    optional_candidate_counts: dict[str, int],
) -> str:
    counts = Counter(str(row.get("horizon_consistency_classification") or "") for row in summary_rows)
    sorted_rows = sorted(
        summary_rows,
        key=lambda row: safe_float(row.get("consistency_score")) or 0,
        reverse=True,
    )

    def rows_for(classification: str) -> list[dict[str, Any]]:
        return [row for row in sorted_rows if row.get("horizon_consistency_classification") == classification]

    lines = [
        "# Horizon Consistency Report",
        "",
        "Research-only horizon comparison. This report does not rerun backtests, does not search for strategies, does not create live signals, and does not provide buy/sell recommendations.",
        "",
        "## Group Context",
        "",
        f"- Group ID: `{group_id}`",
        f"- Direction: `{direction}`",
        f"- Cost mode: `{cost_mode}`",
        f"- Return mode: `{return_mode}`",
        f"- h5 run ID: `{run_ids['h5']}`",
        f"- h10 run ID: `{run_ids['h10']}`",
        f"- h20 run ID: `{run_ids['h20']}`",
        f"- Summary rows: `{len(summary_rows)}`",
        f"- Optional validation candidates read: `{sum(optional_candidate_counts.values())}`",
        "",
        "## Counts",
        "",
        "| classification | count |",
        "| --- | ---: |",
    ]
    for classification in (
        "consistent_across_horizons",
        "consistent_medium_slow",
        "short_horizon_only",
        "long_horizon_only",
        "unstable_across_horizons",
        "insufficient_evidence",
    ):
        lines.append(f"| {classification} | {counts.get(classification, 0)} |")

    sections = [
        ("Consistent Across Horizons", "consistent_across_horizons"),
        ("Consistent Medium Slow", "consistent_medium_slow"),
        ("Short Horizon Only", "short_horizon_only"),
        ("Long Horizon Only", "long_horizon_only"),
        ("Unstable Across Horizons", "unstable_across_horizons"),
    ]
    for title, classification in sections:
        lines.extend(["", f"## {title}", ""])
        lines.extend(table_for(rows_for(classification)))

    lines.extend(["", "## Warnings And Missing Inputs", ""])
    if warnings:
        lines.extend(["| type | horizon | scope | message |", "| --- | --- | --- | --- |"])
        for warning in warnings[:80]:
            lines.append(
                "| {warning_type} | {horizon} | {scope} | {message} |".format(
                    warning_type=warning.get("warning_type", ""),
                    horizon=warning.get("horizon", ""),
                    scope=warning.get("scope", ""),
                    message=str(warning.get("message", "")).replace("|", "\\|"),
                )
            )
        if len(warnings) > 80:
            lines.append(f"| additional_warnings_omitted |  |  | {len(warnings) - 80} |")
    else:
        lines.append("No warnings.")

    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- This is not a buy/sell report.",
            "- This is not a complete strategy.",
            "- It compares already-produced scorecard evidence across h5, h10, and h20 only.",
            "- Any promising row still needs random baseline robustness, candidate baseline diagnostics, and a separate rule-based research backtest.",
            "- Keep long and short separate.",
            "- Keep gross and net separate.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_horizon_consistency_report(args: argparse.Namespace) -> dict[str, Path]:
    direction = normalize_direction(args.direction)
    cost_mode, return_mode = validate_cost_args(args.cost_mode, args.return_mode)
    run_ids = {
        "h5": args.h5_run_id,
        "h10": args.h10_run_id,
        "h20": args.h20_run_id,
    }
    output_dir = Path(args.output_dir) / args.group_id / direction
    report_path = output_dir / "horizon_consistency_report.md"
    summary_path = output_dir / "horizon_consistency_summary.csv"
    warnings_path = output_dir / "horizon_consistency_warnings.csv"
    ensure_outputs_writable([report_path, summary_path, warnings_path], args.overwrite)

    warnings: list[dict[str, str]] = []
    horizon_data: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = {horizon: {} for horizon in HORIZONS}
    optional_candidate_counts: dict[str, int] = {}

    for horizon in HORIZONS:
        run_id = run_ids[horizon]
        cross_path = Path(args.scorecard_dir) / run_id / direction / "final_feature_scorecard.csv"
        horizon_data[horizon].update(
            load_scorecard_rows(
                cross_path,
                horizon=horizon,
                scope="cross_pair",
                direction=direction,
                cost_mode=cost_mode,
                return_mode=return_mode,
                warnings=warnings,
            )
        )
        if args.include_pair_specific:
            pair_path = Path(args.scorecard_dir) / run_id / direction / "pair_specific_feature_scorecard.csv"
            horizon_data[horizon].update(
                load_scorecard_rows(
                    pair_path,
                    horizon=horizon,
                    scope="pair_specific",
                    direction=direction,
                    cost_mode=cost_mode,
                    return_mode=return_mode,
                    warnings=warnings,
                )
            )
        candidate_path = Path(args.validation_dir) / run_id / direction / "final_research_candidates.csv"
        optional_candidate_counts[horizon] = load_optional_candidates(
            candidate_path,
            horizon=horizon,
            direction=direction,
            cost_mode=cost_mode,
            return_mode=return_mode,
            warnings=warnings,
        )

    all_keys = sorted(set().union(*(set(horizon_data[horizon]) for horizon in HORIZONS)))
    summary_rows = [
        summary_row_from_key(
            key,
            {horizon: horizon_data[horizon].get(key) for horizon in HORIZONS},
            direction=direction,
            cost_mode=cost_mode,
            return_mode=return_mode,
        )
        for key in all_keys
    ]
    summary_rows.sort(
        key=lambda row: (
            str(row.get("scope") or ""),
            str(row.get("symbol") or ""),
            -(safe_float(row.get("consistency_score")) or 0),
            str(row.get("feature_condition_key") or ""),
        )
    )

    write_csv(summary_path, SUMMARY_FIELDS, summary_rows)
    write_csv(warnings_path, WARNING_FIELDS, warnings)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_markdown_report(
            group_id=args.group_id,
            direction=direction,
            cost_mode=cost_mode,
            return_mode=return_mode,
            run_ids=run_ids,
            summary_rows=summary_rows,
            warnings=warnings,
            optional_candidate_counts=optional_candidate_counts,
        ),
        encoding="utf-8",
    )
    return {
        "report": report_path,
        "summary": summary_path,
        "warnings": warnings_path,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only h5/h10/h20 feature-condition consistency report."
    )
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--direction", choices=["long", "short"], default="long")
    parser.add_argument("--h5-run-id", required=True)
    parser.add_argument("--h10-run-id", required=True)
    parser.add_argument("--h20-run-id", required=True)
    parser.add_argument("--scorecard-dir", default="reports/final_feature_scorecard")
    parser.add_argument("--validation-dir", default="reports/validation/by_year")
    parser.add_argument("--output-dir", default="reports/horizon_consistency")
    parser.add_argument("--cost-mode", choices=["none", "estimated"], default="estimated")
    parser.add_argument("--return-mode", choices=["gross", "net"], default="net")
    parser.add_argument("--include-pair-specific", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        paths = build_horizon_consistency_report(parse_args(argv))
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as exc:
        print(f"Horizon consistency report failed: {exc}")
        return 1
    print("Files created:")
    print(f"- {paths['report']}")
    print(f"- {paths['summary']}")
    print(f"- {paths['warnings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
