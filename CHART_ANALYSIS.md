# Chart Analysis Protocol (screenshot-based, discretionary)

How I analyze a TradingView screenshot you send in chat and turn it into a
BUY / SELL / NO TRADE call with explicit risk. This is a **discretionary,
advisory** system — I'm reading a static image, not live data, and no
chart-reading method (mine or anyone else's) predicts price with certainty.
The value here is a consistent process and honest risk disclosure, not a
guarantee of winning trades.

## What to include in the screenshot

For a usable read I need to actually see:
- Symbol and timeframe (top-left of a TradingView chart)
- Enough candle history to judge trend/structure (don't crop too tight)
- Any indicators you personally use (EMAs, RSI, MACD, volume, etc.) — if the
  chart is bare price action, I'll work from price structure alone and say so
- Current price

If any of that's missing or ambiguous in the image, I'll say so rather than guess.

## The checklist I run every time

1. **Context** — symbol, timeframe, current price, what indicators are visible.
2. **Trend structure** — higher-highs/higher-lows (uptrend), lower-highs/lower-lows
   (downtrend), or range. Based on swing points, not vibes.
3. **Key levels** — nearest support/resistance, prior swing highs/lows, visible
   round numbers or supply/demand zones.
4. **Price action at the level** — is price reacting at a key level right now
   (rejection wick, engulfing candle, breakout with follow-through), or is it
   sitting in the middle of nowhere?
5. **Indicator confluence** (only using what's actually drawn on your chart) —
   e.g. RSI overbought/oversold, MACD cross, price vs. moving averages.
6. **Decision rule** — I only call BUY or SELL when at least **two independent
   factors agree** (e.g. structure + level + one indicator). One factor alone
   → **NO TRADE / WAIT**, stated explicitly. This is the main defense against
   noise: most screenshots should honestly result in "no clean setup," not a
   signal every time.
7. **Risk, every time a signal is given**:
   - Entry price (approx, from the screenshot)
   - Stop-loss: placed beyond the invalidating structure (past the swing
     point/level that proves the idea wrong), not an arbitrary pip count
   - Take-profit: next meaningful level
   - Risk:Reward ratio — I flag it if it's below **1:1.5**, since a low R:R
     needs a much higher win rate to be worth taking
   - Suggested position size, if you tell me your account balance and risk %
     (default 1%, matching the bot's `RISK_PER_TRADE`) — same formula as
     `bot/risk/position_sizing.py`
   - **Invalidation condition** — the specific price action that means "this
     idea was wrong, get out" (usually the stop-loss level itself)

## Response format

Every analysis I give will follow this shape:

```
SYMBOL / TIMEFRAME
Signal: BUY | SELL | NO TRADE
Confidence: Low | Medium | High  (based on how many factors agree)

Reasoning:
- Trend: ...
- Key level: ...
- Price action: ...
- Indicator confluence: ...

If NO TRADE: what would need to change for a valid setup

Risk (only if signal is BUY/SELL):
- Entry: ~X
- Stop-loss: X (invalidation: ...)
- Take-profit: X
- R:R: 1:X
- Suggested size: X units (at Y% risk on $Z balance) — only if balance given

Caveats specific to this chart: (e.g. "no visible higher-timeframe context",
"choppy range, low-confidence setup", "screenshot doesn't show volume")
```

## Hard limits, stated once

- I only see what's in the screenshot — no multi-timeframe context, no order
  book, no news/economic calendar, no live price after the screenshot was taken.
- Technical analysis is inherently probabilistic. "High confidence" means
  more factors align, not that the trade will win.
- This is a manual/discretionary complement to the automated
  `bot/strategy/ema_crossover.py` system, not a replacement for backtesting.
  A discretionary screenshot read can't be backtested the way the coded
  strategy can — treat signals from this protocol as a second opinion, not
  a system with a known historical win rate.
- Always paper-trade any signal from this protocol before risking real money,
  same as the automated bot.
