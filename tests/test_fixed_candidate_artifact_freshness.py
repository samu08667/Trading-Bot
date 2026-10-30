from datetime import datetime, timedelta, timezone

from scripts._fixed_candidate_artifact_freshness import (
    FUTURE_TIMESTAMP_STATUS,
    MALFORMED_TIMESTAMP_STATUS,
    MISSING_TIMESTAMP_STATUS,
    STALE_STATUS,
    artifact_freshness_summary,
    evaluate_artifact_freshness,
    status_is_stale,
)


NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def freshness_row(
    timestamp: str | None,
    *,
    now: datetime = NOW,
    max_age_minutes: float = 15.0,
    max_future_skew_seconds: float = 300.0,
) -> dict[str, object]:
    payload = {} if timestamp is None else {"created_at_utc": timestamp}
    return evaluate_artifact_freshness(
        [
            {
                "artifact_name": "artifact",
                "path": "artifact.json",
                "payload": payload,
                "max_age_minutes": max_age_minutes,
                "blocking_if_stale": True,
            }
        ],
        now=now,
        max_future_skew_seconds=max_future_skew_seconds,
    )[0]


def test_current_timestamp_within_freshness_window_passes() -> None:
    row = freshness_row("2026-01-01T11:55:00+00:00", max_age_minutes=15.0)

    assert row["status"] == "fresh"
    assert row["age_minutes"] == 5.0
    assert row["future_skew_seconds"] == 0.0
    assert status_is_stale(row["status"]) is False


def test_old_timestamp_fails_as_stale() -> None:
    row = freshness_row("2026-01-01T11:44:59+00:00", max_age_minutes=15.0)

    assert row["status"] == STALE_STATUS
    assert status_is_stale(row["status"]) is True


def test_missing_timestamp_fails() -> None:
    row = freshness_row(None)

    assert row["status"] == MISSING_TIMESTAMP_STATUS
    assert row["age_minutes"] == ""
    assert row["future_skew_seconds"] == ""
    assert status_is_stale(row["status"]) is True


def test_unparseable_timestamp_fails() -> None:
    row = freshness_row("not-a-timestamp")

    assert row["status"] == MALFORMED_TIMESTAMP_STATUS
    assert row["age_minutes"] == ""
    assert row["future_skew_seconds"] == ""
    assert status_is_stale(row["status"]) is True


def test_small_future_timestamp_within_allowed_skew_passes() -> None:
    row = freshness_row("2026-01-01T12:04:59+00:00")

    assert row["status"] == "fresh"
    assert row["age_minutes"] == -4.983333
    assert row["future_skew_seconds"] == 299.0
    assert row["max_future_skew_seconds"] == 300.0
    assert status_is_stale(row["status"]) is False


def test_future_timestamp_beyond_allowed_skew_fails_with_explicit_status() -> None:
    row = freshness_row("2026-01-01T12:05:01+00:00")

    assert row["status"] == FUTURE_TIMESTAMP_STATUS
    assert row["age_minutes"] == -5.016667
    assert row["future_skew_seconds"] == 301.0
    assert row["current_utc"] == "2026-01-01T12:00:00+00:00"
    assert status_is_stale(row["status"]) is True


def test_future_timestamp_is_counted_as_blocking_in_summary() -> None:
    row = freshness_row("2026-01-01T12:05:01+00:00")
    summary = artifact_freshness_summary([row], 15.0)

    assert summary["stale_artifact_count"] == 1
    assert summary["blocking_stale_artifact_count"] == 1
    assert summary["future_dated_artifact_count"] == 1
    assert summary["blocking_future_dated_artifact_count"] == 1


def test_naive_now_is_treated_as_utc() -> None:
    row = freshness_row("2026-01-01T12:00:00+00:00", now=datetime(2026, 1, 1, 12, 0))

    assert row["status"] == "fresh"
    assert row["current_utc"] == "2026-01-01T12:00:00+00:00"


def test_per_artifact_future_skew_override_blocks_earlier() -> None:
    row = evaluate_artifact_freshness(
        [
            {
                "artifact_name": "artifact",
                "path": "artifact.json",
                "payload": {"created_at_utc": (NOW + timedelta(seconds=61)).isoformat()},
                "max_age_minutes": 15,
                "max_future_skew_seconds": 60,
                "blocking_if_stale": True,
            }
        ],
        now=NOW,
        max_future_skew_seconds=300,
    )[0]

    assert row["status"] == FUTURE_TIMESTAMP_STATUS
    assert row["max_future_skew_seconds"] == 60.0


def test_artifact_age_calculation_uses_utc_offsets() -> None:
    rows = evaluate_artifact_freshness(
        [
            {
                "artifact_name": "offset_artifact",
                "path": "artifact.json",
                "payload": {"created_at_utc": "2026-01-01T13:00:00+01:00"},
                "max_age_minutes": 1,
                "blocking_if_stale": True,
            }
        ],
        now=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert rows[0]["age_minutes"] == 0.0
    assert rows[0]["status"] == "fresh"
    assert rows[0]["current_utc"] == "2026-01-01T12:00:00+00:00"
