import pandas as pd
import requests

from bot.config import Config

BASE_URL = "https://api.twelvedata.com"


class TwelveDataError(RuntimeError):
    pass


class TwelveDataClient:
    """Market data client for Twelve Data — no broker account required,
    works regardless of country (it's a data vendor, not a regulated broker).
    """

    def __init__(self, config: Config):
        self.config = config

    def get_candles(self, outputsize: int = 300) -> pd.DataFrame:
        params = {
            "symbol": self.config.pair,
            "interval": self.config.granularity,
            "outputsize": outputsize,
            "apikey": self.config.twelvedata_api_key,
            "order": "ASC",
        }
        resp = requests.get(f"{BASE_URL}/time_series", params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()

        if payload.get("status") == "error":
            raise TwelveDataError(payload.get("message", "Unknown Twelve Data error"))

        values = payload.get("values", [])
        if not values:
            raise TwelveDataError(f"No candle data returned for {self.config.pair}.")

        df = pd.DataFrame(values)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        for col in ("open", "high", "low", "close"):
            df[col] = df[col].astype(float)
        return df[["open", "high", "low", "close"]]

    def get_latest_price(self) -> float:
        params = {"symbol": self.config.pair, "apikey": self.config.twelvedata_api_key}
        resp = requests.get(f"{BASE_URL}/price", params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        if "price" not in payload:
            raise TwelveDataError(payload.get("message", "Unknown Twelve Data error"))
        return float(payload["price"])
