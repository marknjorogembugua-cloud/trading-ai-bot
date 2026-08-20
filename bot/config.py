import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # Market data (required for analysis/backtest/optimize)
    twelvedata_api_key: str

    # Fundamental filter (optional — degrades gracefully if unset)
    finnhub_api_key: Optional[str]

    # Push notifications (optional — ntfy.sh topic, degrades gracefully if unset)
    ntfy_topic: Optional[str]

    # Legacy/optional: only needed if you later wire up automatic execution
    # through a broker that supports your country.
    oanda_api_key: Optional[str]
    oanda_account_id: Optional[str]
    oanda_environment: str

    pair: str  # e.g. "EUR/USD"
    granularity: str  # e.g. "1h" (Twelve Data interval format)

    fast_ema: int
    slow_ema: int
    atr_period: int
    rsi_period: int
    atr_stop_mult: float
    atr_target_mult: float
    adx_threshold: float

    risk_per_trade: float
    max_open_trades: int

    poll_interval_seconds: int

    @property
    def base_currency(self) -> str:
        return self.pair.split("/")[0]

    @property
    def quote_currency(self) -> str:
        return self.pair.split("/")[1]

    @classmethod
    def load(cls) -> "Config":
        twelvedata_key = os.getenv("TWELVEDATA_API_KEY", "")
        if not twelvedata_key:
            raise RuntimeError(
                "TWELVEDATA_API_KEY must be set in .env. Copy .env.example to .env, "
                "sign up for a free key at https://twelvedata.com, and fill it in."
            )

        return cls(
            twelvedata_api_key=twelvedata_key,
            finnhub_api_key=os.getenv("FINNHUB_API_KEY") or None,
            ntfy_topic=os.getenv("NTFY_TOPIC") or None,
            oanda_api_key=os.getenv("OANDA_API_KEY") or None,
            oanda_account_id=os.getenv("OANDA_ACCOUNT_ID") or None,
            oanda_environment=os.getenv("OANDA_ENVIRONMENT", "practice"),
            pair=os.getenv("PAIR", "EUR/USD"),
            granularity=os.getenv("GRANULARITY", "1h"),
            fast_ema=int(os.getenv("FAST_EMA", "20")),
            slow_ema=int(os.getenv("SLOW_EMA", "50")),
            atr_period=int(os.getenv("ATR_PERIOD", "14")),
            rsi_period=int(os.getenv("RSI_PERIOD", "14")),
            atr_stop_mult=float(os.getenv("ATR_STOP_MULT", "1.5")),
            atr_target_mult=float(os.getenv("ATR_TARGET_MULT", "3.0")),
            adx_threshold=float(os.getenv("ADX_THRESHOLD", "20.0")),
            risk_per_trade=float(os.getenv("RISK_PER_TRADE", "0.01")),
            max_open_trades=int(os.getenv("MAX_OPEN_TRADES", "1")),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
        )
