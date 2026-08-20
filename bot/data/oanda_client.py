import pandas as pd
from oandapyV20 import API
from oandapyV20.endpoints import accounts, instruments, orders, positions, trades

from bot.config import Config


class OandaClient:
    """Thin wrapper around oandapyV20 for the calls this bot needs."""

    def __init__(self, config: Config):
        if not config.oanda_api_key or not config.oanda_account_id:
            raise RuntimeError(
                "OANDA_API_KEY and OANDA_ACCOUNT_ID must be set in .env to use OandaClient "
                "(only needed for automatic execution — not required for analysis/backtesting)."
            )
        self.config = config
        self.instrument = config.pair.replace("/", "_")
        self.api = API(
            access_token=config.oanda_api_key,
            environment=config.oanda_environment,
        )
        self.account_id = config.oanda_account_id

    def get_candles(self, count: int = 300) -> pd.DataFrame:
        """Fetch the last `count` completed candles as a DataFrame."""
        params = {
            "count": count,
            "granularity": self.config.granularity,
            "price": "M",  # midpoint prices
        }
        req = instruments.InstrumentsCandles(
            instrument=self.instrument, params=params
        )
        resp = self.api.request(req)

        rows = []
        for c in resp["candles"]:
            if not c["complete"]:
                continue
            rows.append(
                {
                    "time": pd.to_datetime(c["time"]),
                    "open": float(c["mid"]["o"]),
                    "high": float(c["mid"]["h"]),
                    "low": float(c["mid"]["l"]),
                    "close": float(c["mid"]["c"]),
                    "volume": int(c["volume"]),
                }
            )
        df = pd.DataFrame(rows).set_index("time")
        return df

    def get_account_balance(self) -> float:
        req = accounts.AccountSummary(accountID=self.account_id)
        resp = self.api.request(req)
        return float(resp["account"]["balance"])

    def get_open_trades(self) -> list:
        req = trades.OpenTrades(accountID=self.account_id)
        resp = self.api.request(req)
        return resp.get("trades", [])

    def get_open_positions(self) -> list:
        req = positions.OpenPositions(accountID=self.account_id)
        resp = self.api.request(req)
        return resp.get("positions", [])

    def place_market_order(
        self,
        units: int,
        stop_loss_price: float,
        take_profit_price: float,
    ) -> dict:
        """units > 0 for long, units < 0 for short."""
        data = {
            "order": {
                "type": "MARKET",
                "instrument": self.instrument,
                "units": str(units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {
                    "price": f"{stop_loss_price:.5f}"
                },
                "takeProfitOnFill": {
                    "price": f"{take_profit_price:.5f}"
                },
            }
        }
        req = orders.OrderCreate(accountID=self.account_id, data=data)
        return self.api.request(req)

    def close_all_positions(self) -> None:
        for pos in self.get_open_positions():
            instrument = pos["instrument"]
            long_units = pos.get("long", {}).get("units", "0")
            short_units = pos.get("short", {}).get("units", "0")
            data = {}
            if float(long_units) != 0:
                data["longUnits"] = "ALL"
            if float(short_units) != 0:
                data["shortUnits"] = "ALL"
            if data:
                req = positions.PositionClose(
                    accountID=self.account_id, instrument=instrument, data=data
                )
                self.api.request(req)
