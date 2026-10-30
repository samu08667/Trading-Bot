"""MetaTrader 5 connection helpers for read-only market-data access."""


class MT5ConnectionError(RuntimeError):
    """Raised when MetaTrader 5 cannot be initialized."""


class MT5Client:
    """Small wrapper around MetaTrader 5 initialization and shutdown.

    This client intentionally exposes only connection lifecycle methods and the raw
    MetaTrader5 module for read-only data retrieval. It does not implement any order
    management or trading execution capability.
    """

    def __init__(self, mt5_module=None):
        self._mt5 = mt5_module
        self._connected = False

    @property
    def mt5(self):
        if self._mt5 is None:
            import MetaTrader5 as mt5

            self._mt5 = mt5
        return self._mt5

    def initialize(self) -> None:
        """Initialize the MetaTrader 5 terminal connection."""

        if not self.mt5.initialize():
            error = self.mt5.last_error()
            raise MT5ConnectionError(
                f"Connessione a MetaTrader 5 non riuscita. last_error={error}"
            )
        self._connected = True

    def shutdown(self) -> None:
        """Close the MetaTrader 5 terminal connection when it was opened."""

        if self._connected:
            self.mt5.shutdown()
            self._connected = False

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.shutdown()
        return False
