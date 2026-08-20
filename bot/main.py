"""
Legacy/optional automatic execution loop — places real orders via OANDA.
Not used in advisory mode (see bot/analyze.py, which just reports signals
in chat and requires no broker). Only run this if you later get access to
a broker with API execution support in your country and deliberately want
the bot to trade for you.
"""

import logging
import time
from pathlib import Path

from bot.config import Config
from bot.data.oanda_client import OandaClient
from bot.execution.order_manager import OrderManager
from bot.strategy.ema_crossover import generate_signal

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def run() -> None:
    config = Config.load()
    client = OandaClient(config)
    order_manager = OrderManager(config, client)

    logger.info(
        "Starting bot | pair=%s granularity=%s environment=%s",
        config.pair,
        config.granularity,
        config.oanda_environment,
    )
    if config.oanda_environment != "practice":
        logger.warning(
            "OANDA_ENVIRONMENT is not 'practice' — this will place LIVE orders "
            "with real money. Ctrl+C now if that isn't intended."
        )

    last_seen_candle_time = None

    while True:
        try:
            df = client.get_candles(count=max(config.slow_ema, config.atr_period) + 50)
            if df.empty:
                logger.warning("No candle data returned, retrying next cycle.")
            else:
                latest_candle_time = df.index[-1]
                if latest_candle_time != last_seen_candle_time:
                    last_seen_candle_time = latest_candle_time
                    signal = generate_signal(
                        df, config.fast_ema, config.slow_ema, config.atr_period
                    )
                    if signal:
                        logger.info(
                            "New signal on candle %s: %s @ %.5f (ATR=%.5f)",
                            latest_candle_time,
                            signal.direction,
                            signal.price,
                            signal.atr,
                        )
                        order_manager.handle_signal(signal)
                    else:
                        logger.info("No new signal on candle %s.", latest_candle_time)
        except Exception:
            logger.exception("Error in main loop iteration")

        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    run()
