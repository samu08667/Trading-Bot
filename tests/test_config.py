import pytest

from src.config import AppConfig, load_config


REQUIRED_ENV = {
    "TRADING_MODE": "research",
    "MT5_SYMBOL": "EURUSD",
    "MT5_TIMEFRAME": "M15",
    "MT5_BARS": "100",
    "SAVE_RAW_DATA": "false",
}


def set_required_env(monkeypatch, **overrides):
    values = REQUIRED_ENV | overrides
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_load_config_accepts_research_mode(monkeypatch):
    set_required_env(monkeypatch, TRADING_MODE="research")

    config = load_config(env_file=None)

    assert config.trading_mode == "research"
    assert isinstance(config, AppConfig)


def test_load_config_accepts_demo_mode(monkeypatch):
    set_required_env(monkeypatch, TRADING_MODE="demo")

    config = load_config(env_file=None)

    assert config.trading_mode == "demo"


def test_load_config_rejects_invalid_trading_mode(monkeypatch):
    set_required_env(monkeypatch, TRADING_MODE="live")

    with pytest.raises(ValueError, match="TRADING_MODE non valido"):
        load_config(env_file=None)


def test_load_config_validates_required_values(monkeypatch):
    set_required_env(
        monkeypatch,
        TRADING_MODE="research",
        MT5_SYMBOL="GBPUSD",
        MT5_TIMEFRAME="H1",
        MT5_BARS="250",
        SAVE_RAW_DATA="true",
    )

    config = load_config(env_file=None)

    assert config.mt5_symbol == "GBPUSD"
    assert config.mt5_timeframe == "H1"
    assert config.mt5_bars == 250
    assert config.save_raw_data is True


def test_load_config_rejects_non_positive_bars(monkeypatch):
    set_required_env(monkeypatch, MT5_BARS="0")

    with pytest.raises(ValueError, match="MT5_BARS deve essere maggiore di zero"):
        load_config(env_file=None)
