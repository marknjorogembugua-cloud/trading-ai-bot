from dataclasses import dataclass
from typing import Optional, Protocol

import pandas as pd

from bot.config import Config


@dataclass
class EntrySignal:
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str = ""


class Strategy(Protocol):
    """Common interface so the backtest engine and live analyzer can run
    any strategy without duplicating trade-management/reporting code."""

    name: str

    def prepare(self, df: pd.DataFrame, config: Config) -> pd.DataFrame:
        """Add whatever indicator columns this strategy needs."""
        ...

    def generate_entry(
        self, df: pd.DataFrame, i: int, config: Config
    ) -> Optional[EntrySignal]:
        """Look at df.iloc[i] (and earlier rows via df.iloc[:i+1] if needed)
        and return an EntrySignal if this bar is a valid entry, else None."""
        ...
