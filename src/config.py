"""Configuration loading and validation for the read-only research bot."""

from dataclasses import dataclass
from pathlib import Path
import os



ALLOWED_TRADING_MODES = {"demo", "research"}
ALLOWED_TIMEFRAMES = {
    "M1",
    "M2",
    "M3",
    "M4",
    "M5",
    "M6",
    "M10",
    "M12",
    "M15",
    "M20",
    "M30",
    "H1",
    "H2",
    "H3",
    "H4",
    "H6",
    "H8",
    "H12",
    "D1",
    "W1",
    "MN1",
}


@dataclass(frozen=True)
class AppConfig:
    """Validated application settings for market-data research only."""

    trading_mode: str
    mt5_symbol: str
    mt5_timeframe: str
    mt5_bars: int
    save_raw_data: bool


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(
        "SAVE_RAW_DATA deve essere un booleano valido: true/false, yes/no oppure 1/0."
    )


def _parse_positive_int(name: str, value: str | None, *, default: int) -> int:
    raw_value = value if value not in (None, "") else str(default)
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} deve essere un numero intero positivo.") from exc

    if parsed <= 0:
        raise ValueError(f"{name} deve essere maggiore di zero.")

    return parsed


def load_config(env_file: str | Path | None = ".env") -> AppConfig:
    """Load settings from environment variables and validate them.

    The optional ``env_file`` argument is useful for tests and local development. Values
    already present in the environment take precedence over values from the dotenv file.
    """

    if env_file is not None:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_file, override=False)

    trading_mode = os.getenv("TRADING_MODE", "research").strip().lower()
    if trading_mode not in ALLOWED_TRADING_MODES:
        allowed = ", ".join(sorted(ALLOWED_TRADING_MODES))
        raise ValueError(
            f"TRADING_MODE non valido: '{trading_mode}'. Valori ammessi: {allowed}. "
            "Il programma è limitato a modalità read-only demo/research."
        )

    mt5_symbol = os.getenv("MT5_SYMBOL", "EURUSD").strip()
    if not mt5_symbol:
        raise ValueError("MT5_SYMBOL non può essere vuoto.")

    mt5_timeframe = os.getenv("MT5_TIMEFRAME", "M15").strip().upper()
    if mt5_timeframe not in ALLOWED_TIMEFRAMES:
        allowed = ", ".join(sorted(ALLOWED_TIMEFRAMES))
        raise ValueError(f"MT5_TIMEFRAME non valido: '{mt5_timeframe}'. Valori ammessi: {allowed}.")

    mt5_bars = _parse_positive_int("MT5_BARS", os.getenv("MT5_BARS"), default=100)
    save_raw_data = _parse_bool(os.getenv("SAVE_RAW_DATA"), default=False)

    return AppConfig(
        trading_mode=trading_mode,
        mt5_symbol=mt5_symbol,
        mt5_timeframe=mt5_timeframe,
        mt5_bars=mt5_bars,
        save_raw_data=save_raw_data,
    )
