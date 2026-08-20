import time

import pandas as pd
import requests

from bot.config import Config

BASE_URL = "https://api.twelvedata.com"

# Process-wide cache shared by every TwelveDataClient instance. On Vercel's
# Fluid Compute this survives across requests handled by the same warm
# instance, so concurrent callers (multiple open PWA tabs, the Telegram bot,
# the GitHub Actions scan) hitting the same pair/timeframe within the TTL
# reuse one API call instead of each spending their own credit — this is
# what was blowing through the free-tier 800 credits/day limit.
_CACHE_TTL_SECONDS = 90
_candle_cache: dict[tuple[str, str, int], tuple[float, pd.DataFrame]] = {}


class TwelveDataError(RuntimeError):
    pass


class TwelveDataClient:
    """Market data client for Twelve Data — no broker account required,
    works regardless of country (it's a data vendor, not a regulated broker).
    """

    def __init__(self, config: Config):
        self.config = config

    def get_candles(self, outputsize: int = 300) -> pd.DataFrame:
        cache_key = (self.config.pair, self.config.granularity, outputsize)
        cached = _candle_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

        params = {
            "symbol": self.config.pair,
            "interval": self.config.granularity,
            "outputsize": outputsize,
            "apikey": self.config.twelvedata_api_key,
            "order": "ASC",
        }
        resp = requests.get(f"{BASE_URL}/time_series", params=params, timeout=15)
        if not resp.ok:
            raise TwelveDataError(f"{resp.status_code} error from Twelve Data for {self.config.pair} {self.config.granularity}.")
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
        df = df[["open", "high", "low", "close"]]

        _candle_cache[cache_key] = (time.monotonic(), df)
        return df

    def get_latest_price(self) -> float:
        params = {"symbol": self.config.pair, "apikey": self.config.twelvedata_api_key}
        resp = requests.get(f"{BASE_URL}/price", params=params, timeout=15)
        if not resp.ok:
            raise TwelveDataError(f"{resp.status_code} error from Twelve Data for {self.config.pair}.")
        payload = resp.json()
        if "price" not in payload:
            raise TwelveDataError(payload.get("message", "Unknown Twelve Data error"))
        return float(payload["price"])
