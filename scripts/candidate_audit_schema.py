"""Shared schema helpers for fixed-candidate research audit outputs."""

from __future__ import annotations

from typing import Iterable


COMMON_WARNING_FIELDNAMES = [
    "warning_code",
    "severity",
    "blocking",
    "message",
    "related_stage",
    "related_metric",
    "metric_value",
    "threshold",
]

COMMON_SUMMARY_FIELDNAMES = [
    "candidate_id",
    "candidate_scope",
    "decision_scope",
    "final_classification",
    "warnings_count",
    "blocking_warnings_count",
    "next_action",
]

COMMON_NEXT_ACTION_FIELDNAMES = [
    "action_type",
    "status",
    "message",
    "forbidden_actions",
]

RESEARCH_ONLY_FORBIDDEN_ACTIONS = [
    "live trading",
    "trading signals",
    "broker execution",
    "position sizing",
    "TP/SL optimization",
    "new filters",
    "new feature search",
    "live readiness",
]


def merge_fieldnames(primary: Iterable[str], common: Iterable[str]) -> list[str]:
    merged: list[str] = []
    for field in [*primary, *common]:
        if field not in merged:
            merged.append(field)
    return merged


def with_common_warning_fields(fieldnames: Iterable[str]) -> list[str]:
    return merge_fieldnames(fieldnames, COMMON_WARNING_FIELDNAMES)


def with_common_summary_fields(fieldnames: Iterable[str]) -> list[str]:
    return merge_fieldnames(fieldnames, COMMON_SUMMARY_FIELDNAMES)


def with_common_next_action_fields(fieldnames: Iterable[str]) -> list[str]:
    return merge_fieldnames(fieldnames, COMMON_NEXT_ACTION_FIELDNAMES)


def normalize_warning_severity(severity: object) -> str:
    value = str(severity or "").strip().lower()
    if value in {"info", "review", "severe", "blocking"}:
        return value
    if value in {"warning", "warn"}:
        return "review"
    if value in {"error", "critical", "fatal"}:
        return "blocking"
    return "review"


def candidate_id_from_row(row: dict[str, object]) -> str:
    existing = str(row.get("candidate_id") or "").strip()
    if existing:
        return existing
    parts = [
        row.get("symbol"),
        row.get("direction"),
        row.get("timeframe"),
        f"h{row.get('horizon')}" if row.get("horizon") not in {None, ""} else "",
        row.get("target_family"),
        f"{row.get('regime_column')}={row.get('regime_value')}"
        if row.get("regime_column") or row.get("regime_value")
        else "",
        row.get("feature_condition"),
    ]
    text_parts = [str(part).strip() for part in parts if str(part or "").strip()]
    if text_parts:
        return " | ".join(text_parts)
    return str(row.get("run_id") or "").strip()


def warning_row(
    *,
    warning_code: object,
    severity: object,
    blocking: object,
    message: object,
    related_stage: object = "",
    related_metric: object = "",
    metric_value: object = "",
    threshold: object = "",
    **legacy_fields: object,
) -> dict[str, object]:
    normalized = normalize_warning_severity(severity)
    row: dict[str, object] = {
        "warning_code": str(warning_code or "").strip(),
        "severity": normalized,
        "blocking": bool(blocking) or normalized == "blocking",
        "message": message,
        "related_stage": related_stage,
        "related_metric": related_metric,
        "metric_value": metric_value,
        "threshold": threshold,
    }
    row.update(legacy_fields)
    return row


def add_common_summary_fields(
    summary: dict[str, object],
    *,
    decision_scope: str,
    final_classification: object,
    next_action: object = "",
) -> dict[str, object]:
    summary["candidate_id"] = candidate_id_from_row(summary)
    summary["decision_scope"] = decision_scope
    summary["final_classification"] = final_classification
    summary["next_action"] = next_action
    return summary


def forbidden_actions_text(actions: Iterable[str] | None = None) -> str:
    return "; ".join(actions or RESEARCH_ONLY_FORBIDDEN_ACTIONS)


def next_action_row(
    *,
    action_type: object,
    status: object,
    message: object,
    forbidden_actions: object = "",
    **legacy_fields: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "action_type": action_type,
        "status": status,
        "message": message,
        "forbidden_actions": forbidden_actions,
    }
    row.update(legacy_fields)
    return row
