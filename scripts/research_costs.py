from __future__ import annotations

import json
import math
from pathlib import Path
import re
from statistics import mean, median
from typing import Any, Iterable

try:
    from research_metrics import (
        calculate_performance_concentration_metrics,
        calculate_return_metrics,
        directional_return,
        safe_float,
    )
except ModuleNotFoundError:  # pragma: no cover - used when imported as scripts.research_costs
    from scripts.research_metrics import (
        calculate_performance_concentration_metrics,
        calculate_return_metrics,
        directional_return,
        safe_float,
    )


DEFAULT_POINT_SIZES = {
    "EURUSD": 0.00001,
    "GBPUSD": 0.00001,
    "AUDUSD": 0.00001,
    "USDCAD": 0.00001,
    "USDCHF": 0.00001,
    "USDJPY": 0.001,
}

DEFAULT_SYMBOL_COSTS = {
    "EURUSD": {"point_size": 0.00001, "fallback_spread_points": 12},
    "GBPUSD": {"point_size": 0.00001, "fallback_spread_points": 15},
    "AUDUSD": {"point_size": 0.00001, "fallback_spread_points": None},
    "USDCAD": {"point_size": 0.00001, "fallback_spread_points": None},
    "USDCHF": {"point_size": 0.00001, "fallback_spread_points": None},
    "USDJPY": {"point_size": 0.001, "fallback_spread_points": 12},
}

DEFAULT_COST_CONFIG = {
    "default": {
        "slippage_bps_round_trip": 0.0,
        "commission_bps_round_trip": 0.0,
        "fallback_spread_points": None,
    },
    "symbols": DEFAULT_SYMBOL_COSTS,
}

COST_CONFIG_METADATA_KEY = "__cost_config_metadata__"


def normalize_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    compact = re.sub(r"[^A-Z0-9]", "", text)
    for known in sorted(DEFAULT_POINT_SIZES, key=len, reverse=True):
        if compact.startswith(known):
            return known
    return compact or text


def default_point_size(symbol: str) -> float | None:
    return DEFAULT_POINT_SIZES.get(normalize_symbol(symbol))


def load_cost_config(path: Path | None = None) -> dict[str, Any]:
    config: dict[str, Any] = {
        "default": dict(DEFAULT_COST_CONFIG["default"]),
        "symbols": {
            symbol: dict(values)
            for symbol, values in DEFAULT_SYMBOL_COSTS.items()
        },
    }
    metadata: dict[str, Any] = {
        "source": "internal_defaults" if path is None else str(Path(path)),
        "explicit_default_keys": set(),
        "explicit_symbol_keys": {},
    }
    if path is None:
        config[COST_CONFIG_METADATA_KEY] = metadata
        return config
    with Path(path).open("r", encoding="utf-8") as config_file:
        loaded = json.load(config_file)
    if not isinstance(loaded, dict):
        raise ValueError("Cost config must be a JSON object.")
    if isinstance(loaded.get("default"), dict):
        config["default"].update(loaded["default"])
        metadata["explicit_default_keys"] = set(loaded["default"].keys())
    if isinstance(loaded.get("symbols"), dict):
        for symbol, values in loaded["symbols"].items():
            if isinstance(values, dict):
                normalized = normalize_symbol(symbol)
                config["symbols"][normalized] = values
                metadata["explicit_symbol_keys"][normalized] = set(values.keys())
    config[COST_CONFIG_METADATA_KEY] = metadata
    return config


def symbol_cost_config(config: dict[str, Any], symbol: str) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    merged = dict(config.get("default") or {})
    symbols = config.get("symbols") or {}
    if isinstance(symbols.get(normalized), dict):
        merged.update(symbols[normalized])
    return merged


def point_size_for_symbol(symbol: str, config: dict[str, Any] | None = None) -> float | None:
    if config is not None:
        point_size = safe_float(symbol_cost_config(config, symbol).get("point_size"))
        if point_size is not None and math.isfinite(point_size) and point_size > 0:
            return point_size
    return default_point_size(symbol)


def cost_config_source(config: dict[str, Any]) -> str:
    metadata = config.get(COST_CONFIG_METADATA_KEY)
    if isinstance(metadata, dict):
        return str(metadata.get("source") or "manual_config")
    return "manual_config"


def _explicit_default_keys(config: dict[str, Any]) -> set[str]:
    metadata = config.get(COST_CONFIG_METADATA_KEY)
    if isinstance(metadata, dict):
        keys = metadata.get("explicit_default_keys")
        return set(keys) if isinstance(keys, (set, list, tuple)) else set()
    default_config = config.get("default")
    return set(default_config.keys()) if isinstance(default_config, dict) else set()


def _explicit_symbol_keys(config: dict[str, Any], symbol: str) -> set[str]:
    normalized = normalize_symbol(symbol)
    metadata = config.get(COST_CONFIG_METADATA_KEY)
    if isinstance(metadata, dict):
        symbol_keys = metadata.get("explicit_symbol_keys")
        if isinstance(symbol_keys, dict):
            keys = symbol_keys.get(normalized)
            return set(keys) if isinstance(keys, (set, list, tuple)) else set()
        return set()
    symbols = config.get("symbols")
    symbol_config = symbols.get(normalized) if isinstance(symbols, dict) else None
    return set(symbol_config.keys()) if isinstance(symbol_config, dict) else set()


def _explicit_symbol_float(config: dict[str, Any], symbol: str, key: str) -> float | None:
    if key not in _explicit_symbol_keys(config, symbol):
        return None
    symbols = config.get("symbols")
    symbol_config = symbols.get(normalize_symbol(symbol)) if isinstance(symbols, dict) else None
    if not isinstance(symbol_config, dict):
        return None
    return finite_or_none(symbol_config.get(key))


def _explicit_default_float(config: dict[str, Any], key: str) -> float | None:
    if key not in _explicit_default_keys(config):
        return None
    default_config = config.get("default")
    if not isinstance(default_config, dict):
        return None
    return finite_or_none(default_config.get(key))


def point_size_source_for_symbol(symbol: str, config: dict[str, Any]) -> str:
    explicit_symbol = _explicit_symbol_float(config, symbol, "point_size")
    if explicit_symbol is not None and explicit_symbol > 0:
        return "cost_config_symbol"
    explicit_default = _explicit_default_float(config, "point_size")
    if explicit_default is not None and explicit_default > 0:
        return "cost_config_default"
    if default_point_size(symbol) is not None:
        return "internal_default"
    return "missing"


def fallback_spread_source_for_symbol(symbol: str, config: dict[str, Any]) -> tuple[str, float | None]:
    explicit_symbol = _explicit_symbol_float(config, symbol, "fallback_spread_points")
    if explicit_symbol is not None and explicit_symbol >= 0:
        return "cost_config_symbol_fallback_spread_points", explicit_symbol
    explicit_default = _explicit_default_float(config, "fallback_spread_points")
    if explicit_default is not None and explicit_default >= 0:
        return "cost_config_default_fallback_spread_points", explicit_default
    symbol_config = symbol_cost_config(config, symbol)
    fallback = finite_or_none(symbol_config.get("fallback_spread_points"))
    if fallback is not None and fallback >= 0:
        return "internal_default_fallback_spread_points", fallback
    return "missing", None


def has_finite_nonnegative(rows: Iterable[dict[str, object]], key: str) -> bool:
    for row in rows:
        value = finite_or_none(row.get(key))
        if value is not None and value >= 0:
            return True
    return False


def spread_source_used_for_symbol(
    symbol: str,
    config: dict[str, Any],
    rows: Iterable[dict[str, object]],
) -> str:
    rows_list = list(rows)
    if has_finite_nonnegative(rows_list, "spread"):
        return "spread"
    if has_finite_nonnegative(rows_list, "spread_avg_20"):
        return "spread_avg_20"
    fallback_source, _fallback_value = fallback_spread_source_for_symbol(symbol, config)
    return fallback_source


def analyze_symbol_cost_config(
    symbol: str,
    config: dict[str, Any],
    rows: Iterable[dict[str, object]],
) -> dict[str, object]:
    normalized = normalize_symbol(symbol)
    rows_list = list(rows)
    point_source = point_size_source_for_symbol(normalized, config)
    spread_source = spread_source_used_for_symbol(normalized, config, rows_list)
    point_size = point_size_for_symbol(normalized, config)
    _fallback_source, fallback_spread = fallback_spread_source_for_symbol(normalized, config)
    uses_default_point_size = point_source == "internal_default"
    uses_default_spread = spread_source == "internal_default_fallback_spread_points"
    uses_default_costs = uses_default_point_size or uses_default_spread
    warnings: list[str] = []

    if uses_default_point_size:
        warnings.append(
            f"Cost config warning for {normalized}: using internal default point_size={point_size}. "
            "Broker point_size can differ; configure symbols.<SYMBOL>.point_size or use --strict-cost-config."
        )
    elif point_source == "missing":
        warnings.append(
            f"Cost config warning for {normalized}: no point_size configured and no internal default is available; "
            "spread cost will be unavailable."
        )

    if uses_default_spread:
        warnings.append(
            f"Cost config warning for {normalized}: using internal fallback_spread_points={fallback_spread} "
            "because neither spread nor spread_avg_20 is available in the data."
        )
    elif spread_source == "missing":
        warnings.append(
            f"Cost config warning for {normalized}: no spread source available. Provide fallback_spread_points "
            "or include spread/spread_avg_20 in ml_dataset."
        )

    return {
        "symbol": normalized,
        "cost_config_source": cost_config_source(config),
        "point_size_source": point_source,
        "spread_source_used": spread_source,
        "uses_default_point_size": uses_default_point_size,
        "uses_default_spread": uses_default_spread,
        "uses_default_costs": uses_default_costs,
        "warnings": warnings,
    }


def validate_estimated_cost_config(
    *,
    symbols: Iterable[str],
    rows_by_symbol: dict[str, list[dict[str, object]]],
    config: dict[str, Any],
    strict: bool,
) -> dict[str, dict[str, object]]:
    report: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    for symbol in symbols:
        normalized = normalize_symbol(symbol)
        analysis = analyze_symbol_cost_config(
            normalized,
            config,
            rows_by_symbol.get(normalized) or rows_by_symbol.get(str(symbol)) or [],
        )
        report[normalized] = analysis
        if strict:
            if analysis["point_size_source"] != "cost_config_symbol":
                errors.append(
                    f"{normalized}: --strict-cost-config requires explicit symbols.{normalized}.point_size "
                    "in the cost config."
                )
            if analysis["spread_source_used"] == "missing":
                errors.append(
                    f"{normalized}: --strict-cost-config requires fallback_spread_points in the cost config "
                    "or finite spread/spread_avg_20 values in the data."
                )
    if errors:
        raise ValueError("Strict cost config validation failed:\n- " + "\n- ".join(errors))
    return report


def format_symbol_sources(report: dict[str, dict[str, object]], key: str) -> str:
    return "; ".join(
        f"{symbol}={report[symbol].get(key, '')}"
        for symbol in sorted(report)
    )


def symbols_using_default_costs(report: dict[str, dict[str, object]]) -> list[str]:
    return [
        symbol
        for symbol in sorted(report)
        if bool(report[symbol].get("uses_default_costs"))
    ]


def cost_report_warnings(report: dict[str, dict[str, object]]) -> list[str]:
    warnings: list[str] = []
    for symbol in sorted(report):
        warnings.extend(str(item) for item in report[symbol].get("warnings", []))
    return warnings


def cost_report_fields(
    report: dict[str, dict[str, object]],
    symbol: str | None = None,
) -> dict[str, str]:
    if not report:
        return {
            "cost_config_source": "not_applicable",
            "point_size_source": "not_applicable",
            "spread_source_used": "not_applicable",
            "symbols_using_default_costs": "",
        }
    normalized = normalize_symbol(symbol or "") if symbol else ""
    first_symbol = sorted(report)[0]
    selected = report.get(normalized) if normalized else None
    return {
        "cost_config_source": str(report[first_symbol].get("cost_config_source", "manual_config")),
        "point_size_source": (
            str(selected.get("point_size_source", "")) if selected else format_symbol_sources(report, "point_size_source")
        ),
        "spread_source_used": (
            str(selected.get("spread_source_used", "")) if selected else format_symbol_sources(report, "spread_source_used")
        ),
        "symbols_using_default_costs": " ".join(symbols_using_default_costs(report)),
    }


def finite_or_none(value: object) -> float | None:
    parsed = safe_float(value)
    return parsed if parsed is not None and math.isfinite(parsed) else None


def estimate_spread_cost_return(
    row: dict[str, object],
    symbol: str,
    point_size: float | None,
    spread_source: dict[str, Any] | None = None,
) -> float | None:
    if point_size is None or point_size <= 0:
        return None
    close = finite_or_none(row.get("close"))
    if close is None or close <= 0:
        return None

    spread_points = finite_or_none(row.get("spread"))
    if spread_points is None:
        spread_points = finite_or_none(row.get("spread_avg_20"))
    if spread_points is None and spread_source is not None:
        spread_points = finite_or_none(spread_source.get("fallback_spread_points"))
    if spread_points is None or spread_points < 0:
        return None

    spread_price = spread_points * point_size
    return spread_price / close


def bps_cost(config: dict[str, Any], per_side_key: str, round_trip_key: str) -> float:
    round_trip = finite_or_none(config.get(round_trip_key))
    if round_trip is not None:
        return max(round_trip, 0.0) / 10000.0
    per_side = finite_or_none(config.get(per_side_key))
    if per_side is not None:
        return max(per_side, 0.0) * 2.0 / 10000.0
    return 0.0


def estimate_slippage_cost_return(row: dict[str, object], config: dict[str, Any]) -> float:
    return bps_cost(config, "slippage_bps_per_side", "slippage_bps_round_trip")


def estimate_commission_cost_return(row: dict[str, object], config: dict[str, Any]) -> float:
    return bps_cost(config, "commission_bps_per_side", "commission_bps_round_trip")


def estimate_total_cost_return(row: dict[str, object], symbol: str, config: dict[str, Any]) -> float:
    symbol_config = symbol_cost_config(config, symbol)
    point_size = point_size_for_symbol(symbol, config)
    spread_cost = estimate_spread_cost_return(row, symbol, point_size, symbol_config)
    return (
        (spread_cost or 0.0)
        + estimate_slippage_cost_return(row, symbol_config)
        + estimate_commission_cost_return(row, symbol_config)
    )


def net_strategy_return(gross_return: object, estimated_cost_return: object) -> float | None:
    gross = finite_or_none(gross_return)
    cost = finite_or_none(estimated_cost_return)
    if gross is None:
        return None
    return gross - (cost or 0.0)


def validate_cost_args(cost_mode: str, return_mode: str) -> tuple[str, str]:
    normalized_cost_mode = str(cost_mode or "none").strip().lower()
    normalized_return_mode = str(return_mode or "gross").strip().lower()
    if normalized_cost_mode not in {"none", "estimated"}:
        raise ValueError("--cost-mode must be one of: none, estimated.")
    if normalized_return_mode not in {"gross", "net"}:
        raise ValueError("--return-mode must be one of: gross, net.")
    if normalized_return_mode == "net" and normalized_cost_mode == "none":
        raise ValueError("--return-mode net requires --cost-mode estimated; net without costs equals gross and can be misleading.")
    return normalized_cost_mode, normalized_return_mode


def validate_orchestrator_cost_preflight(
    *,
    cost_mode: str,
    return_mode: str,
    cost_config_path: Path | str | None,
    require_cost_config_for_estimated: bool = True,
) -> tuple[str, str]:
    """Validate orchestration-level cost options before starting child scripts."""
    normalized_cost_mode, normalized_return_mode = validate_cost_args(cost_mode, return_mode)

    if normalized_cost_mode == "estimated" and require_cost_config_for_estimated and cost_config_path is None:
        raise ValueError(
            "Missing --cost-config: estimated research orchestration requires an explicit cost config."
        )

    if cost_config_path is None:
        return normalized_cost_mode, normalized_return_mode

    path = Path(cost_config_path)
    if not path.exists():
        raise ValueError(f"Cost config path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Cost config path is not a file: {path}")

    try:
        load_cost_config(path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid cost config JSON: {path}: {exc.msg}") from exc
    except OSError as exc:
        raise ValueError(f"Cost config file is not readable: {path}: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"Invalid cost config: {path}: {exc}") from exc

    return normalized_cost_mode, normalized_return_mode


def strategy_return_components(
    row: dict[str, object],
    *,
    symbol: str,
    return_column: str,
    direction: str,
    cost_config: dict[str, Any],
    cost_mode: str,
) -> tuple[float | None, float | None, float | None]:
    gross = directional_return(row.get(return_column), direction)
    if gross is None:
        return None, None, None
    estimated_cost = (
        estimate_total_cost_return(row, symbol, cost_config)
        if cost_mode == "estimated"
        else 0.0
    )
    return gross, estimated_cost, net_strategy_return(gross, estimated_cost)


def return_components_from_rows(
    rows: Iterable[dict[str, object]],
    *,
    symbol: str,
    return_column: str,
    direction: str,
    cost_config: dict[str, Any],
    cost_mode: str,
) -> dict[str, list[Any]]:
    gross_returns: list[float] = []
    estimated_costs: list[float] = []
    net_returns: list[float] = []
    timestamps: list[object] = []
    for row in rows:
        gross, estimated_cost, net = strategy_return_components(
            row,
            symbol=symbol,
            return_column=return_column,
            direction=direction,
            cost_config=cost_config,
            cost_mode=cost_mode,
        )
        if gross is None or net is None:
            continue
        gross_returns.append(gross)
        estimated_costs.append(estimated_cost or 0.0)
        net_returns.append(net)
        timestamps.append(row.get("time_server"))
    return {
        "gross": gross_returns,
        "cost": estimated_costs,
        "net": net_returns,
        "time_server": timestamps,
    }


def cost_adjusted_return_metrics(
    rows: Iterable[dict[str, object]],
    *,
    symbol: str,
    return_column: str,
    direction: str,
    cost_config: dict[str, Any],
    cost_mode: str,
    return_mode: str,
) -> dict[str, object]:
    components = return_components_from_rows(
        rows,
        symbol=symbol,
        return_column=return_column,
        direction=direction,
        cost_config=cost_config,
        cost_mode=cost_mode,
    )
    gross_metrics = calculate_return_metrics(components["gross"])
    net_metrics = calculate_return_metrics(components["net"])
    selected_metrics = gross_metrics if return_mode == "gross" else net_metrics
    selected_returns = components["gross"] if return_mode == "gross" else components["net"]
    concentration_metrics = calculate_performance_concentration_metrics(
        selected_returns,
        components["time_server"],
    )
    costs = components["cost"]
    return {
        **selected_metrics,
        **concentration_metrics,
        "avg_estimated_cost_return": mean(costs) if costs else None,
        "median_estimated_cost_return": median(costs) if costs else None,
        "gross_mean_return": gross_metrics.get("mean_return"),
        "net_mean_return": net_metrics.get("mean_return"),
        "gross_profit_factor": gross_metrics.get("profit_factor"),
        "net_profit_factor": net_metrics.get("profit_factor"),
        "gross_max_drawdown": gross_metrics.get("max_drawdown"),
        "net_max_drawdown": net_metrics.get("max_drawdown"),
        "gross_cumulative_return": gross_metrics.get("cumulative_return"),
        "net_cumulative_return": net_metrics.get("cumulative_return"),
    }


def cost_metadata(cost_mode: str, return_mode: str) -> dict[str, str]:
    return {"cost_mode": cost_mode, "return_mode": return_mode}
