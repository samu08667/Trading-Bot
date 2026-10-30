"""Read-only OHLCV data loading utilities for MetaTrader 5."""

from pathlib import Path

import pandas as pd

from src.config import AppConfig


_TIMEFRAME_NAMES = {
    "M1": "TIMEFRAME_M1",
    "M2": "TIMEFRAME_M2",
    "M3": "TIMEFRAME_M3",
    "M4": "TIMEFRAME_M4",
    "M5": "TIMEFRAME_M5",
    "M6": "TIMEFRAME_M6",
    "M10": "TIMEFRAME_M10",
    "M12": "TIMEFRAME_M12",
    "M15": "TIMEFRAME_M15",
    "M20": "TIMEFRAME_M20",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H2": "TIMEFRAME_H2",
    "H3": "TIMEFRAME_H3",
    "H4": "TIMEFRAME_H4",
    "H6": "TIMEFRAME_H6",
    "H8": "TIMEFRAME_H8",
    "H12": "TIMEFRAME_H12",
    "D1": "TIMEFRAME_D1",
    "W1": "TIMEFRAME_W1",
    "MN1": "TIMEFRAME_MN1",
}


def resolve_timeframe(mt5_module, timeframe: str) -> int:
    """Resolve a validated timeframe name to the MetaTrader 5 constant."""

    constant_name = _TIMEFRAME_NAMES.get(timeframe.upper())
    if constant_name is None:
        raise ValueError(f"Timeframe non supportato: {timeframe}")
    return getattr(mt5_module, constant_name)


def fetch_ohlcv(mt5_module, symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
    """Fetch historical OHLCV candles using read-only MetaTrader 5 rates APIs."""

    if bars <= 0:
        raise ValueError("bars deve essere maggiore di zero.")

    timeframe_value = resolve_timeframe(mt5_module, timeframe)
    rates = mt5_module.copy_rates_from_pos(symbol, timeframe_value, 0, bars)
    if rates is None:
        error = mt5_module.last_error()
        raise RuntimeError(f"Download dati OHLCV non riuscito per {symbol}. last_error={error}")

    data = pd.DataFrame(rates)
    if data.empty:
        raise RuntimeError(f"Nessuna candela ricevuta per {symbol}.")

    data["time"] = pd.to_datetime(data["time"], unit="s", utc=True)
    return data[["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]]


def save_raw_data(data: pd.DataFrame, config: AppConfig, output_dir: str | Path = "data/raw") -> Path:
    """Persist downloaded raw candles to CSV when explicitly requested."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    file_path = destination / f"{config.mt5_symbol}_{config.mt5_timeframe}_{config.mt5_bars}.csv"
    data.to_csv(file_path, index=False)
    return file_path


def load_market_data(mt5_module, config: AppConfig) -> pd.DataFrame:
    """Load and optionally persist configured OHLCV data."""

    data = fetch_ohlcv(
        mt5_module=mt5_module,
        symbol=config.mt5_symbol,
        timeframe=config.mt5_timeframe,
        bars=config.mt5_bars,
    )
    if config.save_raw_data:
        save_raw_data(data, config)
    return data
