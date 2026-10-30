"""Shared condition parsing for offline research validation scripts.

The helpers in this module parse already-selected research conditions. They do
not search for new strategies, create live signals, or connect to MetaTrader5.
"""

from __future__ import annotations

import re

try:
    from research_metrics import safe_float
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.condition_utils
    from scripts.research_metrics import safe_float

try:
    from feature_safety import FUTURE_TARGET_SKIP_REASON, is_future_or_target_column
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.condition_utils
    from scripts.feature_safety import FUTURE_TARGET_SKIP_REASON, is_future_or_target_column

try:
    from session_utils import hour_in_session, normalize_session_name
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.condition_utils
    from scripts.session_utils import hour_in_session, normalize_session_name


RAW_PRICE_FEATURES = {"open", "high", "low", "close"}
NUMERIC_TERCILE_SKIP_REASON = "numeric_tercile_skipped_to_avoid_temporal_leakage"
RAW_PRICE_SKIP_REASON = "raw_price_level_excluded"

DAY_NAME_TO_INT = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def to_float(value: object) -> float | None:
    return safe_float(value)


def to_int(value: object) -> int | None:
    parsed = to_float(value)
    return int(parsed) if parsed is not None else None


def split_combination(combination_key: str) -> list[str]:
    return [item.strip() for item in re.split(r"\s+AND\s+", combination_key.strip(), flags=re.IGNORECASE) if item.strip()]


def normalized_condition_parts(condition_key: str) -> list[str]:
    return [part.strip() for part in condition_key.split(":") if part.strip()]


def condition_contains_numeric_tercile(condition_key: str) -> bool:
    parts = [part.lower() for part in normalized_condition_parts(condition_key)]
    return "numeric_tercile" in parts


def combination_contains_numeric_tercile(combination_key: str) -> bool:
    return any(condition_contains_numeric_tercile(item) for item in split_combination(combination_key))


def condition_contains_raw_price_feature(condition_key: str) -> bool:
    parts = [part.lower() for part in normalized_condition_parts(condition_key)]
    return any(part in RAW_PRICE_FEATURES for part in parts)


def combination_contains_raw_price_feature(combination_key: str) -> bool:
    return any(condition_contains_raw_price_feature(item) for item in split_combination(combination_key))


def condition_contains_future_or_target_feature(condition_key: str) -> bool:
    return any(is_future_or_target_column(part) for part in normalized_condition_parts(condition_key))


def combination_contains_future_or_target_feature(combination_key: str) -> bool:
    return any(condition_contains_future_or_target_feature(item) for item in split_combination(combination_key))


def parse_condition_key(condition_key: str) -> tuple[str, str, str]:
    parts = normalized_condition_parts(condition_key)
    if len(parts) == 2:
        scenario_type, bucket = parts
        if scenario_type == "day_of_week":
            return "day_of_week", "day_of_week", bucket
        if scenario_type == "ma_diff" and bucket in {"ma_diff_gt_0", "ma_diff_lt_0"}:
            return "ma_diff", "ma_diff", bucket
        if scenario_type == "hour_session":
            return "hour_session", "hour", bucket
        if bucket in {"0", "1"}:
            return "binary_feature", scenario_type, bucket
        raise ValueError(f"Unsupported condition format: {condition_key!r}")

    if len(parts) >= 3:
        scenario_type = parts[0]
        feature = parts[1]
        bucket = ":".join(parts[2:])
        if scenario_type == feature and bucket in {"0", "1"}:
            return "binary_feature", feature, bucket
        if scenario_type == "day_of_week":
            return "day_of_week", "day_of_week", bucket
        if scenario_type == "ma_diff" and bucket in {"ma_diff_gt_0", "ma_diff_lt_0"}:
            return "ma_diff", "ma_diff", bucket
        if scenario_type == "hour_session":
            return "hour_session", "hour", bucket
        return scenario_type, feature, bucket

    raise ValueError(f"Unsupported condition format: {condition_key!r}")


def require_feature(rows: list[dict[str, object]], feature: str, table_name: str = "ml_dataset") -> None:
    if not rows or feature not in rows[0]:
        raise ValueError(f"Feature {feature!r} not found in {table_name}.")


def numeric_values(rows: list[dict[str, object]], feature: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = to_float(row.get(feature))
        if value is not None:
            values.append(value)
    return values


def percentile(sorted_values: list[float], ratio: float) -> float | None:
    if not sorted_values:
        return None
    index = int((len(sorted_values) - 1) * ratio)
    return sorted_values[index]


def tercile_bounds(rows: list[dict[str, object]], feature: str) -> tuple[float, float] | None:
    values = sorted(numeric_values(rows, feature))
    if len(set(values)) < 3:
        return None
    low = percentile(values, 1 / 3)
    high = percentile(values, 2 / 3)
    if low is None or high is None or low == high:
        return None
    return low, high


def build_condition(
    rows: list[dict[str, object]],
    condition_key: str,
    table_name: str = "ml_dataset",
    *,
    allow_numeric_tercile: bool = False,
):
    scenario_type, feature, bucket = parse_condition_key(condition_key)
    if is_future_or_target_column(feature):
        raise ValueError(FUTURE_TARGET_SKIP_REASON)
    require_feature(rows, feature, table_name)

    if scenario_type == "day_of_week" and feature == "day_of_week":
        if bucket in DAY_NAME_TO_INT:
            expected = DAY_NAME_TO_INT[bucket]
        elif bucket.isdigit() and int(bucket) in range(7):
            expected = int(bucket)
        else:
            raise ValueError(f"Unsupported day_of_week bucket: {bucket!r}")
        return lambda row, expected=expected: to_int(row.get("day_of_week")) == expected

    if scenario_type == "ma_diff":
        if bucket == "ma_diff_gt_0":
            return lambda row, feature=feature: (value := to_float(row.get(feature))) is not None and value > 0
        if bucket == "ma_diff_lt_0":
            return lambda row, feature=feature: (value := to_float(row.get(feature))) is not None and value < 0
        raise ValueError(f"Unsupported ma_diff bucket: {bucket!r}")

    if scenario_type == "hour_session" and feature == "hour":
        normalized_bucket = normalize_session_name(bucket)
        return lambda row, normalized_bucket=normalized_bucket: hour_in_session(
            to_int(row.get("hour")),
            normalized_bucket,
        )

    if scenario_type in {"binary_feature", "news_feature"} and bucket in {"0", "1"}:
        expected = float(bucket)
        return lambda row, feature=feature, expected=expected: to_float(row.get(feature)) == expected

    if scenario_type == "numeric_tercile" and allow_numeric_tercile:
        bounds = tercile_bounds(rows, feature)
        if bounds is None:
            raise ValueError(f"Unable to build numeric tercile bounds for {feature!r}.")
        low, high = bounds
        if bucket == "low_tercile":
            return lambda row, feature=feature, low=low: (
                (value := to_float(row.get(feature))) is not None and value <= low
            )
        if bucket == "mid_tercile":
            return lambda row, feature=feature, low=low, high=high: (
                (value := to_float(row.get(feature))) is not None and low < value <= high
            )
        if bucket == "high_tercile":
            return lambda row, feature=feature, high=high: (
                (value := to_float(row.get(feature))) is not None and value > high
            )
        raise ValueError(f"Unsupported numeric_tercile bucket: {bucket!r}")

    if scenario_type == "numeric_tercile":
        raise ValueError(NUMERIC_TERCILE_SKIP_REASON)

    raise ValueError(f"Unsupported hypothesis condition: {condition_key!r}")


def build_predicate(
    rows: list[dict[str, object]],
    combination_key: str,
    table_name: str = "ml_dataset",
    *,
    allow_numeric_tercile: bool = False,
):
    conditions = [
        build_condition(
            rows,
            item,
            table_name,
            allow_numeric_tercile=allow_numeric_tercile,
        )
        for item in split_combination(combination_key)
    ]
    if not conditions:
        raise ValueError(f"Combination is empty: {combination_key!r}")
    return lambda row: all(condition(row) for condition in conditions)


def precheck_combination_skip_reason(combination_key: str) -> str | None:
    if combination_contains_future_or_target_feature(combination_key):
        return FUTURE_TARGET_SKIP_REASON
    if combination_contains_numeric_tercile(combination_key):
        return NUMERIC_TERCILE_SKIP_REASON
    if combination_contains_raw_price_feature(combination_key):
        return RAW_PRICE_SKIP_REASON
    return None
