"""
Generic event-driven backtest — works with any Strategy (see
bot/strategy/base.py). Strategy modules decide *when* and *where* to enter
(direction, stop, target); this engine just replays candles, manages the
trade lifecycle, sizes positions by risk, and reports performance. Shared
across EMACrossoverStrategy (trend-following) and MeanReversionStrategy
(range-fading) so neither duplicates this logic.

Assumptions (kept intentionally simple for a first pass):
- One position open at a time.
- Entry at the close of the signal candle, no slippage/spread modeled.
- Exit on whichever of stop-loss / take-profit is hit first, checked against
  each subsequent candle's high/low. If both would be hit within the same
  candle, the stop-loss is assumed to hit first (conservative).
"""

import argparse
from dataclasses import dataclass

import pandas as pd

from bot.config import Config
from bot.data.twelvedata_client import TwelveDataClient
from bot.strategy.base import Strategy
from bot.strategy.ema_crossover import EMACrossoverStrategy
from bot.strategy.mean_reversion import MeanReversionStrategy

STRATEGIES: dict[str, type] = {
    "ema_crossover": EMACrossoverStrategy,
    "mean_reversion": MeanReversionStrategy,
}


@dataclass
class Trade:
    direction: str
    entry_time: pd.Timestamp
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_time: pd.Timestamp = None
    exit_price: float = None
    pnl: float = None


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    config: Config,
    starting_balance: float,
    risk_per_trade: float,
) -> tuple[list[Trade], pd.Series]:
    df = strategy.prepare(df, config)

    trades: list[Trade] = []
    equity = starting_balance
    equity_curve = []
    open_trade: Trade | None = None

    for i in range(len(df)):
        time = df.index[i]
        row = df.iloc[i]

        if open_trade is not None:
            hit_stop = (
                row["low"] <= open_trade.stop_loss
                if open_trade.direction == "LONG"
                else row["high"] >= open_trade.stop_loss
            )
            hit_target = (
                row["high"] >= open_trade.take_profit
                if open_trade.direction == "LONG"
                else row["low"] <= open_trade.take_profit
            )

            exit_price = None
            if hit_stop:
                exit_price = open_trade.stop_loss
            elif hit_target:
                exit_price = open_trade.take_profit

            if exit_price is not None:
                direction_mult = 1 if open_trade.direction == "LONG" else -1
                price_diff = (exit_price - open_trade.entry_price) * direction_mult
                units = risk_amount_to_units(
                    equity, risk_per_trade, open_trade.entry_price, open_trade.stop_loss
                )
                pnl = price_diff * units
                open_trade.exit_time = time
                open_trade.exit_price = exit_price
                open_trade.pnl = pnl
                equity += pnl
                trades.append(open_trade)
                open_trade = None

        if open_trade is None:
            signal = strategy.generate_entry(df, i, config)
            if signal is not None:
                open_trade = Trade(
                    direction=signal.direction,
                    entry_time=time,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )

        equity_curve.append((time, equity))

    # Mark-to-market any trade still open at the end of the window, so it's
    # counted in the results instead of silently vanishing from the report.
    if open_trade is not None and len(df) > 0:
        last_row = df.iloc[-1]
        direction_mult = 1 if open_trade.direction == "LONG" else -1
        price_diff = (last_row["close"] - open_trade.entry_price) * direction_mult
        units = risk_amount_to_units(
            equity, risk_per_trade, open_trade.entry_price, open_trade.stop_loss
        )
        pnl = price_diff * units
        open_trade.exit_time = df.index[-1]
        open_trade.exit_price = last_row["close"]
        open_trade.pnl = pnl
        equity += pnl
        trades.append(open_trade)
        if equity_curve:
            equity_curve[-1] = (equity_curve[-1][0], equity)

    equity_series = pd.Series(
        [e for _, e in equity_curve], index=[t for t, _ in equity_curve]
    )
    return trades, equity_series


def risk_amount_to_units(
    balance: float, risk_per_trade: float, entry_price: float, stop_loss_price: float
) -> float:
    stop_distance = abs(entry_price - stop_loss_price)
    if stop_distance <= 0:
        return 0.0
    return (balance * risk_per_trade) / stop_distance


def print_report(trades: list[Trade], equity_series: pd.Series, starting_balance: float):
    if not trades:
        print("No trades were generated over this period.")
        return

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    total_pnl = sum(t.pnl for t in trades)
    ending_balance = starting_balance + total_pnl

    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    max_drawdown = drawdown.min() * 100

    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0.0
    realized_rr = (avg_win / abs(avg_loss)) if avg_loss else float("nan")

    # Planned R:R — averaged across actual trades taken, from each trade's own
    # entry/stop/target (works for any strategy, not just fixed ATR multiples).
    planned_rrs = [
        abs(t.take_profit - t.entry_price) / abs(t.entry_price - t.stop_loss)
        for t in trades
        if t.entry_price != t.stop_loss
    ]
    planned_rr = sum(planned_rrs) / len(planned_rrs) if planned_rrs else float("nan")
    breakeven_win_rate = 1 / (1 + planned_rr) * 100 if planned_rr and planned_rr > 0 else float("nan")

    print("=== Backtest Report ===")
    print(f"Trades:          {len(trades)}")
    print(f"Wins / Losses:   {len(wins)} / {len(losses)}")
    print(f"Win rate:        {len(wins) / len(trades) * 100:.1f}%")
    print(f"Starting balance:{starting_balance:,.2f}")
    print(f"Ending balance:  {ending_balance:,.2f}")
    print(f"Total return:    {(ending_balance / starting_balance - 1) * 100:.2f}%")
    print(f"Max drawdown:    {max_drawdown:.2f}%")
    if wins:
        print(f"Avg win:         {avg_win:,.2f}")
    if losses:
        print(f"Avg loss:        {avg_loss:,.2f}")
    print(f"Planned R:R:     1:{planned_rr:.2f}  (avg target/stop distance across trades taken)")
    if losses and wins:
        print(f"Realized R:R:    1:{realized_rr:.2f}  (avg win / avg loss, actual P&L)")
    print(f"Breakeven win rate at this R:R: {breakeven_win_rate:.1f}% "
          f"(you're at {len(wins) / len(trades) * 100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Backtest a strategy")
    parser.add_argument("--strategy", choices=list(STRATEGIES), default="ema_crossover")
    parser.add_argument("--count", type=int, default=2000, help="Number of candles to fetch")
    parser.add_argument("--balance", type=float, default=10000.0, help="Starting balance")
    args = parser.parse_args()

    config = Config.load()
    client = TwelveDataClient(config)
    strategy = STRATEGIES[args.strategy]()

    print(f"Fetching {args.count} candles for {config.pair} ({config.granularity})...")
    df = client.get_candles(outputsize=args.count)
    print(f"Fetched {len(df)} candles.")
    print(f"Strategy: {strategy.name}")

    trades, equity_series = run_backtest(
        df,
        strategy=strategy,
        config=config,
        starting_balance=args.balance,
        risk_per_trade=config.risk_per_trade,
    )
    print_report(trades, equity_series, args.balance)


if __name__ == "__main__":
    main()
