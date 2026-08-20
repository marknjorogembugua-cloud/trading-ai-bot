# Forex Analysis Bot (advisory — technical + fundamental, regime-adaptive)

Analyzes a forex pair and prints a BUY / SELL / NO TRADE signal with entry,
stop-loss, take-profit, R:R, and explicit caveats. **Advisory only** — it
does not place trades. No broker account needed (data-only APIs), so it
works regardless of what's available in your country.

It switches strategy based on market regime: **trend-following** (EMA
crossover) when ADX shows a trending market, **mean-reversion** (Bollinger
Bands + RSI extremes) when it doesn't — because backtesting showed trend
crossovers lose money in choppy conditions and mean-reversion does better
there. See "What's actually been validated" below before trusting either.

## How it works

- `bot/data/twelvedata_client.py` — OHLC candles from Twelve Data (free, no broker account, no country restriction).
- `bot/data/economic_calendar.py` — upcoming high-impact events from Finnhub; vetoes signals right before major news. Degrades gracefully if unset/unavailable.
- `bot/strategy/ema_crossover.py` — EMA(fast/slow), ATR, RSI, ADX indicators + `EMACrossoverStrategy` (trend-following).
- `bot/strategy/mean_reversion.py` — Bollinger Bands + `MeanReversionStrategy` (range-fading).
- `bot/strategy/structure.py` — support/resistance from clustered swing highs/lows.
- `bot/strategy/base.py` — the `Strategy` interface both strategies implement, so the backtest engine doesn't duplicate trade-management code per strategy.
- `bot/strategy/combined_signal.py` — the live advisory logic: picks trend or range regime by ADX, only signals when the regime-appropriate factors agree, applies the fundamental veto.
- `bot/analyze.py` — CLI: analyze one or more timeframes, prints a chat-style report, optionally sends a push notification.
- `bot/backtest/engine.py` — generic backtest engine, works with either strategy.
- `bot/backtest/optimize.py` — walk-forward parameter search per strategy (see "Self-training" below).
- `bot/notify/push.py` — free push notifications via ntfy.sh.
- `bot/risk/position_sizing.py` — sizes a trade to risk `RISK_PER_TRADE` of account balance.
- `bot/main.py`, `bot/data/oanda_client.py`, `bot/execution/` — **legacy/optional**, only relevant if you later get a broker with API execution access in your country. Not used by the advisory flow.

## Setup

1. Free API key at **https://twelvedata.com** (market data — required).
2. Free API key at **https://finnhub.io** (economic calendar — optional).
3. Install the **ntfy** app (Android/iOS/web, https://ntfy.sh) if you want push notifications — no signup needed, just subscribe to your `NTFY_TOPIC`.
4. Install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
5. ```bash
   cp .env.example .env
   # fill in TWELVEDATA_API_KEY (required), FINNHUB_API_KEY and NTFY_TOPIC (optional)
   ```

## Get a signal

```bash
source .venv/bin/activate
python -m bot.analyze --balance 10000
python -m bot.analyze --balance 10000 --timeframes 5min,15min,30min   # scan multiple timeframes
```

Sends a push notification (if `NTFY_TOPIC` is set) whenever a timeframe
produces a real BUY/SELL, not on NO TRADE.

## Backtest

```bash
python -m bot.backtest.engine --strategy ema_crossover --count 3000 --balance 10000
python -m bot.backtest.engine --strategy mean_reversion --count 3000 --balance 10000
```

Add `GRANULARITY=15min` (or `5min`, `30min`, `4h`, ...) before the command to
test a different timeframe. Technical-only — fundamentals aren't part of the
backtest (not reliably backtestable with a free calendar API); treat the
fundamental filter as a live-only safety check.

## What's actually been validated (as of this session, EUR/USD)

| Strategy | 1h | 4h | 30min | 15min | 5min |
|---|---|---|---|---|---|
| EMA crossover (trend) | -10.7% | -7.9% | -12.5% | +1.8% | -0.3% |
| Mean reversion (range) | +19.2%, 2/3 folds profitable OOS | not tested | +9.4% | -0.02% | +0.5% |

Takeaways, stated plainly:
- Trend-following lost money on every timeframe except a marginal +1.8% at 15min. **Not validated as profitable.**
- Mean-reversion did meaningfully better on 1h and 30min, including surviving walk-forward out-of-sample testing at 1h (2/3 folds profitable, consistent parameters chosen each fold — a real signal, not noise).
- 5min and 15min samples are small (7-30 trades over ~1-4 weeks of data) — not enough to draw a real conclusion either way, and neither backtest models spread/slippage, which matters most at short timeframes where the ATR-based stop is tightest relative to typical spread cost.
- **None of this is a guarantee.** Paper-verify (compare the live tool's calls to what actually happens) before ever risking real money, regardless of what the backtest says.

## "Self-training" — what this actually does

Not indefinite self-learning — that would mostly be overfitting dressed up.
`bot/backtest/optimize.py` runs **walk-forward optimization**: grid-searches
parameters on a window of past data, then checks whether they held up on
the *next* window it didn't see, and says so plainly when they don't.

```bash
python -m bot.backtest.optimize --strategy ema_crossover --count 3000 --folds 4
python -m bot.backtest.optimize --strategy mean_reversion --count 3000 --folds 4
```

Run occasionally (e.g. monthly), review the output, manually decide whether
to change defaults. A decision aid, not an autonomous update.

## Screenshot-based analysis (manual, in chat)

`CHART_ANALYSIS.md` defines a separate protocol for when you paste a
TradingView screenshot into chat instead of running the CLI.

## Notifications

- **Push (done)**: free via ntfy.sh, no signup. Set `NTFY_TOPIC` in `.env` and subscribe to it in the ntfy app.
- **Voice calls (not set up)**: needs a paid telephony provider (e.g. Africa's Talking, Twilio) with your own billing — skipped for now in favor of push notifications, which are free and instant. Revisit if push alone isn't enough.

## Automatic execution (not set up — optional, future)

The advisory flow needs no broker. If you later want automatic order
placement, you'd need a broker with API access available in Kenya — e.g.
**Deriv** (well-documented WebSocket API) or check whether **Exness**/**HFM**
offer API access for your account type. `bot/main.py` + `bot/data/oanda_client.py`
show the pattern (OANDA itself isn't available in Kenya) — the same shape
would apply to a different broker, but the client code would need rewriting
against that broker's actual API.

## Notes / simplifications

- Position sizing assumes the account's home currency equals the quote
  currency of the pair (true for a USD-denominated account trading
  `EUR/USD`, `GBP/USD`). Cross pairs need currency conversion.
- No spread/slippage modeling in the backtest.
- Structure detection (support/resistance) uses simple swing-point
  clustering — a reasonable first pass, not a substitute for your own
  chart reading.
- Regime switch (trend vs range) is driven by `ADX_THRESHOLD` in `.env`
  (default 20). Backtest results above use this same default.
