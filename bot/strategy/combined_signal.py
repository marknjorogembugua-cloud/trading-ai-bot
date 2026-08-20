from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from bot.config import Config
from bot.data.economic_calendar import EconomicCalendar
from bot.data.twelvedata_client import TwelveDataClient
from bot.risk.position_sizing import calculate_units
from bot.strategy.ema_crossover import add_indicators
from bot.strategy.mean_reversion import add_bollinger_bands
from bot.strategy.structure import find_key_levels, nearest_levels


@dataclass
class Analysis:
    pair: str
    granularity: str
    current_price: float
    regime: str  # "trending" | "ranging"
    signal: str  # "BUY" | "SELL" | "NO TRADE"
    confidence: str  # "Low" | "Medium" | "High"
    reasoning: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward: Optional[float] = None
    suggested_units: Optional[int] = None


def _trend_factor(last, fast_ema: int, slow_ema: int, reasoning: list[str]) -> Optional[str]:
    if last["ema_fast"] > last["ema_slow"]:
        reasoning.append(f"Trend: EMA{fast_ema} above EMA{slow_ema} — uptrend structure.")
        return "bullish"
    if last["ema_fast"] < last["ema_slow"]:
        reasoning.append(f"Trend: EMA{fast_ema} below EMA{slow_ema} — downtrend structure.")
        return "bearish"
    reasoning.append("Trend: EMAs flat/equal — no clear trend.")
    return None


def _momentum_factor(last, reasoning: list[str], caveats: list[str]) -> Optional[str]:
    rsi = last["rsi"]
    if rsi >= 70:
        caveats.append(f"RSI is overbought ({rsi:.1f}) — pullback risk even if trend is up.")
    if rsi <= 30:
        caveats.append(f"RSI is oversold ({rsi:.1f}) — bounce risk even if trend is down.")

    if rsi > 55:
        reasoning.append(f"Momentum: RSI {rsi:.1f} favors buyers.")
        return "bullish"
    if rsi < 45:
        reasoning.append(f"Momentum: RSI {rsi:.1f} favors sellers.")
        return "bearish"
    reasoning.append(f"Momentum: RSI {rsi:.1f} is neutral.")
    return None


def _structure_factor(
    df: pd.DataFrame, current_price: float, reasoning: list[str]
) -> tuple[Optional[str], Optional[float], Optional[float]]:
    levels = find_key_levels(df)
    support, resistance = nearest_levels(levels, current_price)
    support_price = support.price if support else None
    resistance_price = resistance.price if resistance else None

    if support_price is not None:
        reasoning.append(f"Nearest support: {support_price:.5f} ({support.touches} touches).")
    if resistance_price is not None:
        reasoning.append(f"Nearest resistance: {resistance_price:.5f} ({resistance.touches} touches).")

    last_close = df.iloc[-1]["close"]
    last_low = df.iloc[-1]["low"]
    last_high = df.iloc[-1]["high"]
    candle_range = last_high - last_low
    if candle_range <= 0:
        return None, support_price, resistance_price

    close_position = (last_close - last_low) / candle_range

    near_support = support_price is not None and abs(current_price - support_price) / current_price <= 0.0015
    near_resistance = resistance_price is not None and abs(current_price - resistance_price) / current_price <= 0.0015

    if near_support and close_position > 0.6:
        reasoning.append("Price action: rejection candle off support (closed in upper part of range).")
        return "bullish", support_price, resistance_price
    if near_resistance and close_position < 0.4:
        reasoning.append("Price action: rejection candle off resistance (closed in lower part of range).")
        return "bearish", support_price, resistance_price

    reasoning.append("Price action: no clean reaction at a key level on the latest candle.")
    return None, support_price, resistance_price


def _trend_regime_signal(
    df: pd.DataFrame, config: Config, current_price: float, reasoning: list[str], caveats: list[str]
) -> tuple[str, str, Optional[float], Optional[float]]:
    """Backtested: EMACrossoverStrategy. Returns (direction, confidence, stop_loss, take_profit)."""
    last = df.iloc[-1]
    trend = _trend_factor(last, config.fast_ema, config.slow_ema, reasoning)
    momentum = _momentum_factor(last, reasoning, caveats)
    structure, support_price, resistance_price = _structure_factor(df, current_price, reasoning)

    factors = [trend, momentum, structure]
    bullish_count = factors.count("bullish")
    bearish_count = factors.count("bearish")

    if bullish_count >= 2 and bullish_count > bearish_count:
        direction = "BUY"
    elif bearish_count >= 2 and bearish_count > bullish_count:
        direction = "SELL"
    else:
        direction = "NO TRADE"
    confidence = "High" if max(bullish_count, bearish_count) == 3 else "Medium"

    if direction == "NO TRADE":
        return direction, confidence, None, None

    atr = float(last["atr"])
    stop_distance = atr * config.atr_stop_mult
    target_distance = atr * config.atr_target_mult
    if direction == "BUY":
        stop_loss = current_price - stop_distance
        take_profit = current_price + target_distance
        if resistance_price and resistance_price < take_profit:
            caveats.append(
                f"Resistance at {resistance_price:.5f} sits before the ATR-based target "
                f"({take_profit:.5f}) — price may stall there."
            )
    else:
        stop_loss = current_price + stop_distance
        take_profit = current_price - target_distance
        if support_price and support_price > take_profit:
            caveats.append(
                f"Support at {support_price:.5f} sits before the ATR-based target "
                f"({take_profit:.5f}) — price may stall there."
            )
    return direction, confidence, stop_loss, take_profit


def _range_regime_signal(
    df: pd.DataFrame, config: Config, current_price: float, reasoning: list[str], caveats: list[str]
) -> tuple[str, str, Optional[float], Optional[float]]:
    """Backtested: MeanReversionStrategy. Returns (direction, confidence, stop_loss, take_profit)."""
    last = df.iloc[-1]
    reasoning.append(
        f"Bollinger bands: lower {last['bb_lower']:.5f} / mid {last['bb_mid']:.5f} / upper {last['bb_upper']:.5f}."
    )
    reasoning.append(f"Momentum: RSI {last['rsi']:.1f}.")

    touched_lower = last["low"] <= last["bb_lower"]
    touched_upper = last["high"] >= last["bb_upper"]
    atr = float(last["atr"])

    if touched_lower and last["rsi"] <= 30:
        reasoning.append("Price pierced the lower band with RSI oversold — reversion-long setup.")
        stop_loss = last["low"] - atr
        take_profit = last["bb_mid"]
        if take_profit <= current_price:
            return "NO TRADE", "N/A", None, None
        return "BUY", "Medium", stop_loss, take_profit

    if touched_upper and last["rsi"] >= 70:
        reasoning.append("Price pierced the upper band with RSI overbought — reversion-short setup.")
        stop_loss = last["high"] + atr
        take_profit = last["bb_mid"]
        if take_profit >= current_price:
            return "NO TRADE", "N/A", None, None
        return "SELL", "Medium", stop_loss, take_profit

    reasoning.append("No band-touch + RSI-extreme confluence on the latest candle.")
    return "NO TRADE", "N/A", None, None


def analyze(
    config: Config,
    market_client: TwelveDataClient,
    calendar: EconomicCalendar,
    account_balance: Optional[float] = None,
) -> Analysis:
    df = market_client.get_candles(outputsize=300)
    df = add_indicators(df, config.fast_ema, config.slow_ema, config.atr_period, config.rsi_period)
    df = add_bollinger_bands(df, period=20, num_std=2.0)
    df = df.dropna(subset=["ema_fast", "ema_slow", "atr", "rsi", "adx", "bb_mid"])

    last = df.iloc[-1]
    current_price = float(last["close"])
    adx = float(last["adx"])

    reasoning: list[str] = []
    caveats: list[str] = []

    trending = adx >= config.adx_threshold
    regime = "trending" if trending else "ranging"
    reasoning.append(f"Regime: ADX {adx:.1f} → {regime} market.")

    if trending:
        reasoning.append("Using trend-following read (EMA/RSI/structure) — backtested edge in trending conditions.")
        direction, confidence, stop_loss, take_profit = _trend_regime_signal(
            df, config, current_price, reasoning, caveats
        )
    else:
        reasoning.append("Using mean-reversion read (Bollinger/RSI extremes) — backtested edge in ranging conditions.")
        direction, confidence, stop_loss, take_profit = _range_regime_signal(
            df, config, current_price, reasoning, caveats
        )

    # Fundamental veto: don't signal into a high-impact release.
    event = calendar.high_impact_soon([config.base_currency, config.quote_currency], hours_ahead=6)
    if event and direction != "NO TRADE":
        caveats.append(
            f"Fundamental veto: high-impact {event.currency} event "
            f"'{event.event}' at {event.datetime_utc.isoformat()} (within 6h) — "
            f"signal downgraded to NO TRADE. Re-check after the release."
        )
        direction = "NO TRADE"
        confidence = "Low"
    elif not calendar.enabled:
        caveats.append(
            "No FINNHUB_API_KEY set — fundamental/news filter was skipped entirely. "
            "Check an economic calendar yourself before trading around major releases."
        )

    analysis = Analysis(
        pair=config.pair,
        granularity=config.granularity,
        current_price=current_price,
        regime=regime,
        signal=direction,
        confidence=confidence if direction != "NO TRADE" else "N/A",
        reasoning=reasoning,
        caveats=caveats,
    )

    if direction == "NO TRADE" or stop_loss is None or take_profit is None:
        return analysis

    rr = abs(take_profit - current_price) / abs(current_price - stop_loss)

    analysis.entry = current_price
    analysis.stop_loss = stop_loss
    analysis.take_profit = take_profit
    analysis.risk_reward = rr

    if account_balance is not None:
        units = calculate_units(
            account_balance=account_balance,
            risk_per_trade=config.risk_per_trade,
            entry_price=current_price,
            stop_loss_price=stop_loss,
            direction="LONG" if direction == "BUY" else "SHORT",
        )
        analysis.suggested_units = abs(units)

    return analysis


def format_report(analysis: Analysis) -> str:
    lines = [
        f"{analysis.pair} / {analysis.granularity} ({analysis.regime})",
        f"Signal: {analysis.signal}",
    ]
    if analysis.signal != "NO TRADE":
        lines.append(f"Confidence: {analysis.confidence}")

    lines.append("")
    lines.append("Reasoning:")
    for r in analysis.reasoning:
        lines.append(f"- {r}")

    if analysis.signal != "NO TRADE":
        lines.append("")
        lines.append("Risk:")
        lines.append(f"- Entry: {analysis.entry:.5f}")
        lines.append(f"- Stop-loss: {analysis.stop_loss:.5f}")
        lines.append(f"- Take-profit: {analysis.take_profit:.5f}")
        lines.append(f"- R:R: 1:{analysis.risk_reward:.2f}")
        if analysis.suggested_units is not None:
            lines.append(f"- Suggested size: {analysis.suggested_units} units")

    if analysis.caveats:
        lines.append("")
        lines.append("Caveats:")
        for c in analysis.caveats:
            lines.append(f"- {c}")

    return "\n".join(lines)
