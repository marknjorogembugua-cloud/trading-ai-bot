import logging

from bot.config import Config
from bot.data.oanda_client import OandaClient
from bot.risk.position_sizing import calculate_units
from bot.strategy.ema_crossover import Signal

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, config: Config, client: OandaClient):
        self.config = config
        self.client = client

    def handle_signal(self, signal: Signal) -> None:
        open_trades = self.client.get_open_trades()
        if len(open_trades) >= self.config.max_open_trades:
            logger.info(
                "Signal %s ignored: already at max_open_trades (%d)",
                signal.direction,
                self.config.max_open_trades,
            )
            return

        stop_distance = signal.atr * self.config.atr_stop_mult
        target_distance = signal.atr * self.config.atr_target_mult

        if signal.direction == "LONG":
            stop_loss_price = signal.price - stop_distance
            take_profit_price = signal.price + target_distance
        else:
            stop_loss_price = signal.price + stop_distance
            take_profit_price = signal.price - target_distance

        balance = self.client.get_account_balance()
        units = calculate_units(
            account_balance=balance,
            risk_per_trade=self.config.risk_per_trade,
            entry_price=signal.price,
            stop_loss_price=stop_loss_price,
            direction=signal.direction,
        )

        if units == 0:
            logger.warning("Calculated position size is 0 units, skipping trade.")
            return

        logger.info(
            "Placing %s order: %d units @ ~%.5f | SL %.5f | TP %.5f",
            signal.direction,
            units,
            signal.price,
            stop_loss_price,
            take_profit_price,
        )
        result = self.client.place_market_order(
            units=units,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )
        logger.info("Order response: %s", result)
