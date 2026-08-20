import argparse
import dataclasses
import logging

from bot.config import Config
from bot.data.economic_calendar import EconomicCalendar
from bot.data.twelvedata_client import TwelveDataClient
from bot.notify.push import send_push
from bot.notify.telegram import send_message as send_telegram
from bot.strategy.combined_signal import analyze, format_report

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    parser = argparse.ArgumentParser(
        description="Technical + fundamental analysis for a pair, printed as a signal report."
    )
    parser.add_argument("--balance", type=float, default=None, help="Account balance for position sizing")
    parser.add_argument(
        "--timeframes",
        type=str,
        default=None,
        help="Comma-separated Twelve Data intervals to scan, e.g. '5min,15min,30min'. "
        "Defaults to just GRANULARITY from .env if not given.",
    )
    args = parser.parse_args()

    base_config = Config.load()
    calendar = EconomicCalendar(base_config)

    timeframes = (
        [t.strip() for t in args.timeframes.split(",")]
        if args.timeframes
        else [base_config.granularity]
    )

    for tf in timeframes:
        config = dataclasses.replace(base_config, granularity=tf)
        market_client = TwelveDataClient(config)
        try:
            result = analyze(config, market_client, calendar, account_balance=args.balance)
        except Exception as e:
            print(f"{config.pair} / {tf}: failed to analyze ({e})")
            continue
        print(format_report(result))
        print()

        if result.signal != "NO TRADE" and base_config.ntfy_topic:
            send_push(
                topic=base_config.ntfy_topic,
                title=f"{result.pair} {tf}: {result.signal}",
                message=(
                    f"Entry {result.entry:.5f} | SL {result.stop_loss:.5f} | "
                    f"TP {result.take_profit:.5f} | R:R 1:{result.risk_reward:.2f} | "
                    f"Confidence {result.confidence}"
                ),
            )

        if result.signal != "NO TRADE" and base_config.telegram_bot_token:
            send_telegram(
                bot_token=base_config.telegram_bot_token,
                chat_id=base_config.telegram_chat_id,
                text=(
                    f"<b>{result.pair} {tf}: {result.signal}</b>\n"
                    f"Entry {result.entry:.5f}\n"
                    f"SL {result.stop_loss:.5f}  TP {result.take_profit:.5f}\n"
                    f"R:R 1:{result.risk_reward:.2f}  Confidence {result.confidence}"
                ),
            )


if __name__ == "__main__":
    main()
