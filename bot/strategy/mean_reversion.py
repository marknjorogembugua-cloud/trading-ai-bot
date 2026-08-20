from typing import Optional

import pandas as pd

from bot.strategy.ema_crossover import add_indicators  # reuse ATR/RSI/ADX calc
from bot.strategy.base import EntrySignal


def add_bollinger_bands(df: pd.DataFrame, period: int, num_std: float) -> pd.DataFrame:
    df = df.copy()
    df["bb_mid"] = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    df["bb_upper"] = df["bb_mid"] + num_std * std
    df["bb_lower"] = df["bb_mid"] - num_std * std
    return df


class MeanReversionStrategy:
    """
    Range/reversion strategy — the counterpart to EMACrossoverStrategy's
    trend-following bet. Enters when price pierces a Bollinger Band AND RSI
    confirms an extreme (oversold at the lower band, overbought at the
    upper band), betting on a reversion back toward the mean.

    Target: the Bollinger midline (mean), not a fixed ATR multiple — that's
    the actual thesis of a mean-reversion trade.
    Stop: beyond the recent extreme, buffered by ATR so normal noise near
    the band doesn't stop the trade out immediately.

    Best suited to ranging/choppy markets — the ADX regime filter here
    works in the OPPOSITE direction of the trend-following strategy: it
    requires ADX to be LOW (i.e. skips signals when the market is trending
    strongly, since a trending market can pierce a band and keep going).
    """

    name = "mean_reversion"

    def __init__(self, bb_period: int = 20, bb_std: float = 2.0,
                 rsi_oversold: float = 30.0, rsi_overbought: float = 70.0,
                 stop_atr_mult: float = 1.0, max_adx_for_entry: float = 25.0):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.stop_atr_mult = stop_atr_mult
        self.max_adx_for_entry = max_adx_for_entry

    def prepare(self, df: pd.DataFrame, config) -> pd.DataFrame:
        df = add_indicators(df, config.fast_ema, config.slow_ema, config.atr_period, config.rsi_period)
        df = add_bollinger_bands(df, self.bb_period, self.bb_std)
        return df

    def generate_entry(self, df: pd.DataFrame, i: int, config) -> Optional[EntrySignal]:
        row = df.iloc[i]
        if pd.isna(row.get("bb_lower")) or pd.isna(row.get("atr")) or pd.isna(row.get("adx")):
            return None

        # Only take reversion trades when the market isn't strongly trending —
        # a real trend can pierce a band and keep going against a reversion bet.
        if row["adx"] > self.max_adx_for_entry:
            return None

        entry_price = row["close"]
        atr = row["atr"]

        touched_lower = row["low"] <= row["bb_lower"]
        touched_upper = row["high"] >= row["bb_upper"]

        if touched_lower and row["rsi"] <= self.rsi_oversold:
            stop_loss = row["low"] - atr * self.stop_atr_mult
            take_profit = row["bb_mid"]
            if take_profit <= entry_price:
                return None  # degenerate: no room to target the mean
            return EntrySignal(
                direction="LONG",
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"Lower band touch + RSI {row['rsi']:.1f} oversold, ADX {row['adx']:.1f}",
            )

        if touched_upper and row["rsi"] >= self.rsi_overbought:
            stop_loss = row["high"] + atr * self.stop_atr_mult
            take_profit = row["bb_mid"]
            if take_profit >= entry_price:
                return None
            return EntrySignal(
                direction="SHORT",
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=f"Upper band touch + RSI {row['rsi']:.1f} overbought, ADX {row['adx']:.1f}",
            )

        return None
