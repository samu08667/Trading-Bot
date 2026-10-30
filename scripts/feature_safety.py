"""Shared feature safety helpers for offline research scripts."""

from __future__ import annotations


FUTURE_TARGET_PREFIXES = (
    "future_return_",
    "future_max_return_",
    "future_min_return_",
    "future_range_",
    "long_mfe_",
    "long_mae_",
    "short_mfe_",
    "short_mae_",
    "long_tp_",
    "short_tp_",
    "long_triple_barrier_",
    "short_triple_barrier_",
    "bars_to_",
    "target_",
    "target_up_",
    "target_down_",
    "target_long_good_",
    "target_short_good_",
)

FUTURE_TARGET_SUBSTRINGS = (
    "triple_barrier",
    "hit_first",
    "bars_to_first_barrier",
)

METADATA_FEATURE_COLUMNS = {
    "id",
    "symbol",
    "timeframe",
    "time_server",
    "time",
    "date",
    "source",
    "created_at",
}

RAW_PRICE_FEATURES = {"open", "high", "low", "close"}
RAW_UNSCALED_FEATURES = {"tick_volume"}
RAW_SPREAD_POINT_FEATURES = {"spread"}

FUTURE_TARGET_SKIP_REASON = "future_or_target_column_excluded"


def normalized_column_name(column: object) -> str:
    return str(column or "").strip().lower()


def is_future_or_target_column(column: object) -> bool:
    name = normalized_column_name(column)
    return any(name.startswith(prefix) for prefix in FUTURE_TARGET_PREFIXES) or any(
        marker in name for marker in FUTURE_TARGET_SUBSTRINGS
    )


def is_metadata_feature_column(column: object) -> bool:
    return normalized_column_name(column) in METADATA_FEATURE_COLUMNS


def is_raw_price_feature(column: object) -> bool:
    return normalized_column_name(column) in RAW_PRICE_FEATURES


def is_raw_unscaled_feature(column: object) -> bool:
    return normalized_column_name(column) in RAW_UNSCALED_FEATURES


def is_raw_spread_point_feature(column: object) -> bool:
    return normalized_column_name(column) in RAW_SPREAD_POINT_FEATURES


def is_excluded_model_feature(column: object) -> bool:
    return (
        is_metadata_feature_column(column)
        or is_future_or_target_column(column)
        or is_raw_price_feature(column)
        or is_raw_unscaled_feature(column)
        or is_raw_spread_point_feature(column)
    )

