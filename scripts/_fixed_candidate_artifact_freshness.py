"""Shared max-age checks for fixed-candidate demo artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MAX_ARTIFACT_AGE_MINUTES = 15.0
DEFAULT_MAX_ORDER_CHECK_ARTIFACT_AGE_MINUTES = 5.0
DEFAULT_MAX_FUTURE_SKEW_SECONDS = 300.0
ARTIFACT_FRESHNESS_FIELDNAMES = [
    "artifact_name",
    "path",
    "observed_timestamp",
    "current_utc",
    "age_minutes",
    "max_age_minutes",
    "future_skew_seconds",
    "max_future_skew_seconds",
    "status",
    "blocking_if_stale",
]

FRESH_STATUS = "fresh"
STALE_STATUS = "stale"
MISSING_TIMESTAMP_STATUS = "missing_timestamp"
MALFORMED_TIMESTAMP_STATUS = "malformed_timestamp"
FUTURE_TIMESTAMP_STATUS = "artifact_freshness_blocked_future_timestamp"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    if " " in text and "T" not in text:
        candidates.append(text.replace(" ", "T"))
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def artifact_timestamp(payload: dict[str, Any]) -> str:
    for field in ("created_at_utc", "generated_at"):
        value = payload.get(field)
        if value not in (None, ""):
            return str(value)
    return ""


def status_is_stale(status: Any) -> bool:
    return str(status) != FRESH_STATUS


def evaluate_artifact_freshness(
    specs: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    max_future_skew_seconds: float = DEFAULT_MAX_FUTURE_SKEW_SECONDS,
) -> list[dict[str, Any]]:
    observed_now = as_utc(now or utc_now())
    rows: list[dict[str, Any]] = []
    for spec in specs:
        payload = spec.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        observed = artifact_timestamp(payload)
        max_age = float(spec["max_age_minutes"])
        max_future_skew = float(spec.get("max_future_skew_seconds", max_future_skew_seconds))
        parsed = parse_utc_timestamp(observed)
        age_minutes: float | None = None
        future_skew_seconds: float | None = None
        if not observed:
            status = MISSING_TIMESTAMP_STATUS
        elif parsed is None:
            status = MALFORMED_TIMESTAMP_STATUS
        else:
            age_minutes = (observed_now - parsed).total_seconds() / 60.0
            future_skew_seconds = max(0.0, (parsed - observed_now).total_seconds())
            if future_skew_seconds > max_future_skew:
                status = FUTURE_TIMESTAMP_STATUS
            else:
                status = STALE_STATUS if age_minutes > max_age else FRESH_STATUS
        rows.append(
            {
                "artifact_name": str(spec["artifact_name"]),
                "path": str(Path(spec["path"])),
                "observed_timestamp": observed,
                "current_utc": observed_now.isoformat(),
                "age_minutes": "" if age_minutes is None else round(age_minutes, 6),
                "max_age_minutes": max_age,
                "future_skew_seconds": "" if future_skew_seconds is None else round(future_skew_seconds, 6),
                "max_future_skew_seconds": max_future_skew,
                "status": status,
                "blocking_if_stale": bool(spec.get("blocking_if_stale", True)),
            }
        )
    return rows


def artifact_freshness_summary(rows: list[dict[str, Any]], max_age_minutes: Any) -> dict[str, Any]:
    stale_rows = [row for row in rows if status_is_stale(row.get("status"))]
    blocking_rows = [row for row in stale_rows if row.get("blocking_if_stale") is True]
    future_rows = [row for row in rows if row.get("status") == FUTURE_TIMESTAMP_STATUS]
    blocking_future_rows = [row for row in future_rows if row.get("blocking_if_stale") is True]
    return {
        "artifact_freshness_policy_applied": True,
        "stale_artifact_count": len(stale_rows),
        "blocking_stale_artifact_count": len(blocking_rows),
        "future_dated_artifact_count": len(future_rows),
        "blocking_future_dated_artifact_count": len(blocking_future_rows),
        "max_artifact_age_minutes": max_age_minutes,
    }
