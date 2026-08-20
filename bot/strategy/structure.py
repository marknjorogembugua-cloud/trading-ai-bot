from dataclasses import dataclass

import pandas as pd


@dataclass
class Level:
    price: float
    kind: str  # "support" or "resistance"
    touches: int


def find_swing_points(df: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    """A swing high/low is a candle whose high/low is the most extreme
    within `lookback` candles on both sides."""
    df = df.copy()
    df["swing_high"] = (
        df["high"] == df["high"].rolling(2 * lookback + 1, center=True).max()
    )
    df["swing_low"] = (
        df["low"] == df["low"].rolling(2 * lookback + 1, center=True).min()
    )
    return df


def find_key_levels(
    df: pd.DataFrame, lookback: int = 3, cluster_pct: float = 0.001, max_levels: int = 4
) -> list[Level]:
    """
    Clusters recent swing highs/lows into support/resistance levels.
    cluster_pct: swing points within this fraction of price get merged into one level.
    """
    swings = find_swing_points(df, lookback=lookback)
    highs = swings.loc[swings["swing_high"], "high"].tolist()
    lows = swings.loc[swings["swing_low"], "low"].tolist()

    def cluster(prices: list[float], kind: str) -> list[Level]:
        if not prices:
            return []
        prices = sorted(prices)
        clusters: list[list[float]] = [[prices[0]]]
        for p in prices[1:]:
            if abs(p - clusters[-1][-1]) / clusters[-1][-1] <= cluster_pct:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        levels = [
            Level(price=sum(c) / len(c), kind=kind, touches=len(c)) for c in clusters
        ]
        levels.sort(key=lambda lv: lv.touches, reverse=True)
        return levels[:max_levels]

    return cluster(highs, "resistance") + cluster(lows, "support")


def nearest_levels(
    levels: list[Level], current_price: float
) -> tuple[Level | None, Level | None]:
    """Returns (nearest support below price, nearest resistance above price)."""
    supports = sorted(
        (lv for lv in levels if lv.kind == "support" and lv.price < current_price),
        key=lambda lv: current_price - lv.price,
    )
    resistances = sorted(
        (lv for lv in levels if lv.kind == "resistance" and lv.price > current_price),
        key=lambda lv: lv.price - current_price,
    )
    return (supports[0] if supports else None, resistances[0] if resistances else None)
