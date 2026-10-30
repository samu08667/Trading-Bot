"""Research-only regime labels built from current and past-known features.

The thresholds here are deterministic descriptive buckets. They are intended
for offline diagnostics and are not deployment-ready calibration rules.
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Mapping


REGIME_CLASSIFICATION_COLUMNS = (
    "session",
    "spread_liquidity_regime",
    "volatility_regime",
    "range_regime",
    "volume_liquidity_regime",
)

REGIME_CLASSIFICATION_SOURCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "session": ("time_server", "hour"),
    "spread_liquidity_regime": (
        "spread_to_atr_20",
        "cost_to_atr",
        "estimated_cost_R",
        "spread_return",
        "spread_to_volume_ratio",
    ),
    "volatility_regime": ("volatility_ratio_20_100", "volatility_100"),
    "range_regime": ("range_to_atr_20",),
    "volume_liquidity_regime": (
        "volume_spike_20",
        "volume_dry_up_20",
        "tick_volume_zscore_100",
        "tick_volume_percentile_100",
        "volume_vs_session_avg",
    ),
}

LEAKAGE_GUARDRAIL_BLOCKED_TOKENS = (
    "future",
    "target",
    "mfe",
    "mae",
    "hit_first",
    "triple_barrier",
    "bars_to_first_barrier",
    "actual",
    "forecast",
    "surprise",
)


def finite_float(value: object) -> float | None:
    try:
        parsed = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if parsed is None or not math.isfinite(parsed):
        return None
    return parsed


def parse_time_server(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return None


def classify_session_from_hour(hour: int | None) -> str | None:
    """Classify server-hour session, keeping London/New York overlap explicit."""
    if hour is None or hour < 0 or hour > 23:
        return None
    if 0 <= hour <= 7:
        return "Asia"
    if 8 <= hour <= 12:
        return "London"
    if 13 <= hour <= 16:
        return "London_NewYork_Overlap"
    if 17 <= hour <= 21:
        return "New_York"
    return "Off_hours"


def classify_session(row: Mapping[str, object]) -> str | None:
    hour = finite_float(row.get("hour"))
    if hour is not None:
        return classify_session_from_hour(int(hour))
    timestamp = parse_time_server(row.get("time_server"))
    return classify_session_from_hour(timestamp.hour) if timestamp is not None else None


def classify_spread_liquidity_regime(row: Mapping[str, object]) -> str | None:
    value = first_finite(row, ("spread_to_atr_20", "cost_to_atr", "estimated_cost_R"))
    if value is not None:
        return bucket_value(
            value,
            low_cutoff=0.05,
            normal_cutoff=0.15,
            high_cutoff=0.30,
            labels=("low_spread", "normal_spread", "high_spread", "extreme_spread"),
        )

    spread_return = finite_float(row.get("spread_return"))
    if spread_return is not None:
        return bucket_value(
            spread_return,
            low_cutoff=0.00005,
            normal_cutoff=0.00015,
            high_cutoff=0.00030,
            labels=("low_spread", "normal_spread", "high_spread", "extreme_spread"),
        )

    spread_to_volume = finite_float(row.get("spread_to_volume_ratio"))
    if spread_to_volume is not None:
        return bucket_value(
            spread_to_volume,
            low_cutoff=0.05,
            normal_cutoff=0.15,
            high_cutoff=0.30,
            labels=("low_spread", "normal_spread", "high_spread", "extreme_spread"),
        )
    return None


def classify_volatility_regime(row: Mapping[str, object]) -> str | None:
    ratio = finite_float(row.get("volatility_ratio_20_100"))
    if ratio is not None:
        return bucket_value(
            ratio,
            low_cutoff=0.75,
            normal_cutoff=1.25,
            high_cutoff=1.75,
            labels=("low_volatility", "normal_volatility", "high_volatility", "extreme_volatility"),
        )

    volatility = finite_float(row.get("volatility_100"))
    if volatility is not None:
        return bucket_value(
            volatility,
            low_cutoff=0.0005,
            normal_cutoff=0.0015,
            high_cutoff=0.0030,
            labels=("low_volatility", "normal_volatility", "high_volatility", "extreme_volatility"),
        )
    return None


def classify_range_regime(row: Mapping[str, object]) -> str | None:
    value = finite_float(row.get("range_to_atr_20"))
    if value is None:
        return None
    return bucket_value(
        value,
        low_cutoff=0.60,
        normal_cutoff=1.40,
        high_cutoff=2.20,
        labels=("compressed_range", "normal_range", "expanded_range", "extreme_range"),
    )


def classify_volume_liquidity_regime(row: Mapping[str, object]) -> str | None:
    spike = finite_float(row.get("volume_spike_20"))
    dry_up = finite_float(row.get("volume_dry_up_20"))
    if spike == 1:
        return "volume_spike"
    if dry_up == 1:
        return "dry_volume"

    zscore = finite_float(row.get("tick_volume_zscore_100"))
    percentile = finite_float(row.get("tick_volume_percentile_100"))
    session_ratio = finite_float(row.get("volume_vs_session_avg"))

    if zscore is None and percentile is None and session_ratio is None and spike is None and dry_up is None:
        return None
    if any(value is not None and value >= threshold for value, threshold in ((zscore, 2.0), (percentile, 0.90), (session_ratio, 1.50))):
        return "volume_spike"
    if any(value is not None and value >= threshold for value, threshold in ((zscore, 1.0), (percentile, 0.75), (session_ratio, 1.25))):
        return "high_volume"
    if any(value is not None and value <= threshold for value, threshold in ((zscore, -1.0), (percentile, 0.20), (session_ratio, 0.70))):
        return "dry_volume"
    return "normal_volume"


def build_regime_labels(row: Mapping[str, object]) -> dict[str, str | None]:
    return {
        "session": classify_session(row),
        "spread_liquidity_regime": classify_spread_liquidity_regime(row),
        "volatility_regime": classify_volatility_regime(row),
        "range_regime": classify_range_regime(row),
        "volume_liquidity_regime": classify_volume_liquidity_regime(row),
    }


def with_regime_labels(row: Mapping[str, object], *, replace_blank: bool = True) -> dict[str, object]:
    """Return a row copy with missing descriptive regime labels populated.

    This is a compatibility bridge for older research tables that already have
    the current-row source columns but were created before the regime-label
    columns existed.
    """
    enriched = dict(row)
    labels = build_regime_labels(enriched)
    for column, label in labels.items():
        if column not in enriched or (replace_blank and is_blank_label(enriched.get(column))):
            enriched[column] = label
    return enriched


def with_regime_labels_for_rows(rows: list[Mapping[str, object]], *, replace_blank: bool = True) -> list[dict[str, object]]:
    return [with_regime_labels(row, replace_blank=replace_blank) for row in rows]


def is_blank_label(value: object) -> bool:
    return value is None or str(value).strip() == ""


def missing_regime_source_groups(columns: set[str]) -> dict[str, tuple[str, ...]]:
    missing: dict[str, tuple[str, ...]] = {}
    for regime_column, source_columns in REGIME_CLASSIFICATION_SOURCE_COLUMNS.items():
        if not any(column in columns for column in source_columns):
            missing[regime_column] = source_columns
    return missing


def assert_no_regime_source_leakage() -> None:
    leaking = [
        source_column
        for source_columns in REGIME_CLASSIFICATION_SOURCE_COLUMNS.values()
        for source_column in source_columns
        if any(token in source_column.lower() for token in LEAKAGE_GUARDRAIL_BLOCKED_TOKENS)
    ]
    if leaking:
        raise AssertionError(f"Regime classification source columns include unsafe fields: {leaking}")


def first_finite(row: Mapping[str, object], columns: tuple[str, ...]) -> float | None:
    for column in columns:
        value = finite_float(row.get(column))
        if value is not None:
            return value
    return None


def bucket_value(
    value: float,
    *,
    low_cutoff: float,
    normal_cutoff: float,
    high_cutoff: float,
    labels: tuple[str, str, str, str],
) -> str:
    if value <= low_cutoff:
        return labels[0]
    if value <= normal_cutoff:
        return labels[1]
    if value <= high_cutoff:
        return labels[2]
    return labels[3]
