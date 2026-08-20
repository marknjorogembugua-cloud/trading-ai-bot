"""
Walk-forward parameter optimization — works for any strategy via a
build_fn(params) -> (strategy, config) and a param grid. See
bot/backtest/engine.py's module docstring and README's "Self-training"
section for what this does and doesn't claim: it does NOT learn
indefinitely, it re-searches parameters on past data and checks whether
they hold up on a subsequent window it didn't see. Reports the honest
result either way.
"""

import argparse
import dataclasses
import itertools

import pandas as pd

from bot.backtest.engine import run_backtest
from bot.config import Config
from bot.data.twelvedata_client import TwelveDataClient
from bot.strategy.ema_crossover import EMACrossoverStrategy
from bot.strategy.mean_reversion import MeanReversionStrategy

# --- EMA crossover grid ---
EMA_FAST_GRID = [10, 15, 20, 25]
EMA_SLOW_GRID = [40, 50, 60, 70]
EMA_ADX_GRID = [0.0, 20.0, 25.0]


def _ema_param_grid():
    return [
        {"fast_ema": f, "slow_ema": s, "adx_threshold": a}
        for f, s, a in itertools.product(EMA_FAST_GRID, EMA_SLOW_GRID, EMA_ADX_GRID)
        if f < s
    ]


def _build_ema(params: dict, base_config: Config):
    config = dataclasses.replace(
        base_config,
        fast_ema=params["fast_ema"],
        slow_ema=params["slow_ema"],
        adx_threshold=params["adx_threshold"],
    )
    return EMACrossoverStrategy(), config


# --- Mean reversion grid ---
MR_BB_PERIOD_GRID = [14, 20]
MR_BB_STD_GRID = [1.5, 2.0, 2.5]
MR_RSI_EXTREME_GRID = [(25.0, 75.0), (30.0, 70.0)]
MR_MAX_ADX_GRID = [20.0, 25.0]


def _mr_param_grid():
    return [
        {
            "bb_period": p,
            "bb_std": s,
            "rsi_oversold": lo,
            "rsi_overbought": hi,
            "max_adx_for_entry": adx,
        }
        for p, s, (lo, hi), adx in itertools.product(
            MR_BB_PERIOD_GRID, MR_BB_STD_GRID, MR_RSI_EXTREME_GRID, MR_MAX_ADX_GRID
        )
    ]


def _build_mr(params: dict, base_config: Config):
    strategy = MeanReversionStrategy(
        bb_period=params["bb_period"],
        bb_std=params["bb_std"],
        rsi_oversold=params["rsi_oversold"],
        rsi_overbought=params["rsi_overbought"],
        max_adx_for_entry=params["max_adx_for_entry"],
    )
    return strategy, base_config


STRATEGY_SETUPS = {
    "ema_crossover": (_ema_param_grid, _build_ema),
    "mean_reversion": (_mr_param_grid, _build_mr),
}


def _final_return(equity_series: pd.Series, starting_balance: float) -> float:
    if equity_series.empty:
        return 0.0
    return (equity_series.iloc[-1] / starting_balance - 1) * 100


def grid_search(df, param_grid, build_fn, base_config, starting_balance, risk_per_trade):
    """Returns (best_params, in_sample_return_pct)."""
    best_params, best_return = None, -float("inf")
    for params in param_grid:
        strategy, config = build_fn(params, base_config)
        _, equity = run_backtest(df, strategy, config, starting_balance, risk_per_trade)
        ret = _final_return(equity, starting_balance)
        if ret > best_return:
            best_params, best_return = params, ret
    return best_params, best_return


def walk_forward(df, param_grid, build_fn, base_config, n_folds, starting_balance, risk_per_trade):
    fold_size = len(df) // (n_folds + 1)
    results = []

    for i in range(n_folds):
        train = df.iloc[i * fold_size : (i + 2) * fold_size]
        test = df.iloc[(i + 2) * fold_size : (i + 3) * fold_size]
        if len(test) < 30:
            break

        best_params, in_sample_return = grid_search(
            train, param_grid, build_fn, base_config, starting_balance, risk_per_trade
        )

        strategy, config = build_fn(best_params, base_config)
        _, oos_equity = run_backtest(test, strategy, config, starting_balance, risk_per_trade)
        oos_return = _final_return(oos_equity, starting_balance)

        results.append(
            {
                "fold": i + 1,
                "params": best_params,
                "in_sample_return_pct": in_sample_return,
                "out_of_sample_return_pct": oos_return,
            }
        )
    return results


def main():
    parser = argparse.ArgumentParser(description="Walk-forward parameter optimization")
    parser.add_argument("--strategy", choices=list(STRATEGY_SETUPS), default="ema_crossover")
    parser.add_argument("--count", type=int, default=3000)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--balance", type=float, default=10000.0)
    args = parser.parse_args()

    config = Config.load()
    client = TwelveDataClient(config)
    print(f"Fetching {args.count} candles for {config.pair} ({config.granularity})...")
    df = client.get_candles(outputsize=args.count)
    print(f"Fetched {len(df)} candles.\n")

    param_grid_fn, build_fn = STRATEGY_SETUPS[args.strategy]
    param_grid = param_grid_fn()

    results = walk_forward(
        df, param_grid, build_fn, config, n_folds=args.folds,
        starting_balance=args.balance, risk_per_trade=config.risk_per_trade,
    )

    if not results:
        print("Not enough data for the requested number of folds — fetch more candles or reduce --folds.")
        return

    print(f"=== Walk-Forward Optimization: {args.strategy} ===")
    oos_positive = 0
    for r in results:
        print(f"Fold {r['fold']}: params={r['params']}")
        print(
            f"  In-sample: {r['in_sample_return_pct']:.2f}%   "
            f"Out-of-sample: {r['out_of_sample_return_pct']:.2f}%"
        )
        if r["out_of_sample_return_pct"] > 0:
            oos_positive += 1

    print()
    print(f"Out-of-sample folds profitable: {oos_positive}/{len(results)}")
    if oos_positive < len(results) / 2:
        print(
            "Fewer than half of out-of-sample folds were profitable — the "
            "optimized parameters likely don't generalize. Don't adopt them."
        )
    else:
        last_fold = results[-1]
        print(
            f"Most recent fold's params: {last_fold['params']} — review before "
            "changing .env/defaults, this is a candidate, not an automatic update."
        )


if __name__ == "__main__":
    main()
