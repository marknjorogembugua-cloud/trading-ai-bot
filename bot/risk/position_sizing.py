def calculate_units(
    account_balance: float,
    risk_per_trade: float,
    entry_price: float,
    stop_loss_price: float,
    direction: str,
) -> int:
    """
    Position size so that a stop-out loses ~risk_per_trade of account_balance.

    NOTE: this assumes the account's home currency matches the quote currency
    of the instrument (e.g. a USD-denominated OANDA account trading EUR_USD),
    so a 1-unit price move maps directly to a 1-unit currency P&L. For pairs
    where that doesn't hold (e.g. a USD account trading EUR_GBP), convert the
    risk amount into the quote currency before sizing.
    """
    stop_distance = abs(entry_price - stop_loss_price)
    if stop_distance <= 0:
        return 0

    risk_amount = account_balance * risk_per_trade
    units = int(risk_amount / stop_distance)

    return units if direction == "LONG" else -units
