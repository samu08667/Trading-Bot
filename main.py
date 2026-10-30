"""Entry point for the read-only MetaTrader 5 research bot."""

from src.config import load_config
from src.data_loader import load_market_data
from src.mt5_client import MT5Client


def main() -> None:
    config = load_config()

    print("Trading research bot read-only avviato")
    print(f"Modalità: {config.trading_mode}")
    print(f"Symbol: {config.mt5_symbol}")
    print(f"Timeframe: {config.mt5_timeframe}")
    print(f"Candele richieste: {config.mt5_bars}")

    with MT5Client() as client:
        data = load_market_data(client.mt5, config)

    print("Ultime candele scaricate:")
    print(data.tail())

    if config.save_raw_data:
        print("Dati grezzi salvati in data/raw/.")


if __name__ == "__main__":
    main()
