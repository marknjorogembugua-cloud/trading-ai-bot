from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class Signal:
    direction: str  # "LONG" or "SHORT"
    price: float
    atr: float


def add_indicators(
    df: pd.DataFrame,
    fast_ema: int,
    slow_ema: int,
    atr_period: int,
    rsi_period: int = 14,
) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=fast_ema, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=slow_ema, adjust=False).mean()

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(atr_period).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)  # neutral when no loss/gain yet

    df["adx"] = _adx(df, atr_period)

    return df


def _adx(df: pd.DataFrame, period: int) -> pd.Series:
    """Average Directional Index — measures trend strength (not direction).
    Used to filter out crossover signals during ranging/choppy markets,
    where simple MA crossovers are most prone to whipsaw losses.
    """
    up_move = df["high"].diff()
    down_move = -df["low"].diff()

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx.fillna(0)


def generate_signal(
    df: pd.DataFrame, fast_ema: int, slow_ema: int, atr_period: int
) -> Optional[Signal]:
    """
    Trend-following EMA crossover:
    - LONG when the fast EMA crosses above the slow EMA
    - SHORT when the fast EMA crosses below the slow EMA
    Returns None if there is no fresh crossover on the most recent completed candle.
    """
    df = add_indicators(df, fast_ema, slow_ema, atr_period)
    df = df.dropna(subset=["ema_fast", "ema_slow", "atr"])

    if len(df) < 2:
        return None

    prev = df.iloc[-2]
    last = df.iloc[-1]

    crossed_up = prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
    crossed_down = prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]

    if crossed_up:
        return Signal(direction="LONG", price=last["close"], atr=last["atr"])
    if crossed_down:
        return Signal(direction="SHORT", price=last["close"], atr=last["atr"])
    return None


class EMACrossoverStrategy:
    """Trend-following: enter on an EMA fast/slow crossover, filtered by ADX
    (skip signals in a non-trending/choppy market). Implements bot.strategy.base.Strategy."""

    name = "ema_crossover"

    def prepare(self, df: pd.DataFrame, config) -> pd.DataFrame:
        return add_indicators(
            df, config.fast_ema, config.slow_ema, config.atr_period, config.rsi_period
        )

    def generate_entry(self, df: pd.DataFrame, i: int, config):
        from bot.strategy.base import EntrySignal  # local import avoids a cycle

        if i < 1:
            return None
        prev, row = df.iloc[i - 1], df.iloc[i]
        if pd.isna(row["ema_fast"]) or pd.isna(row["adx"]) or pd.isna(row["atr"]):
            return None

        crossed_up = prev["ema_fast"] <= prev["ema_slow"] and row["ema_fast"] > row["ema_slow"]
        crossed_down = prev["ema_fast"] >= prev["ema_slow"] and row["ema_fast"] < row["ema_slow"]
        if not (crossed_up or crossed_down):
            return None
        if row["adx"] < config.adx_threshold:
            return None

        direction = "LONG" if crossed_up else "SHORT"
        entry_price = row["close"]
        stop_distance = row["atr"] * config.atr_stop_mult
        target_distance = row["atr"] * config.atr_target_mult
        if direction == "LONG":
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + target_distance
        else:
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - target_distance

        return EntrySignal(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=f"EMA{config.fast_ema}/{config.slow_ema} crossover, ADX {row['adx']:.1f}",
        )
