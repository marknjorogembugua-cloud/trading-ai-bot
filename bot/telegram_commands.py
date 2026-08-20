import dataclasses
import re

from bot.config import Config
from bot.data.economic_calendar import EconomicCalendar
from bot.data.twelvedata_client import TwelveDataClient
from bot.strategy.combined_signal import analyze

TIMEFRAMES = ["5min", "15min", "30min", "1h"]
PAIR_RE = re.compile(r"^[A-Z]{3}/[A-Z]{3}$")

HELP_TEXT = (
    "<b>FX Signals bot</b>\n"
    "/signal [PAIR] — current read across all timeframes (default EUR/USD)\n"
    "e.g. <code>/signal GBP/USD</code>\n"
    "/help — show this message"
)


def run_signal(pair):
    base_config = Config.load()
    if pair:
        base_config = dataclasses.replace(base_config, pair=pair)

    calendar = EconomicCalendar(base_config)
    lines = [f"<b>{base_config.pair}</b>"]
    for tf in TIMEFRAMES:
        config = dataclasses.replace(base_config, granularity=tf)
        client = TwelveDataClient(config)
        try:
            r = analyze(config, client, calendar)
            if r.signal == "NO TRADE":
                lines.append(f"{tf}: {r.signal}")
            else:
                lines.append(
                    f"{tf}: <b>{r.signal}</b> ({r.confidence}) — "
                    f"Entry {r.entry:.5f} SL {r.stop_loss:.5f} TP {r.take_profit:.5f} "
                    f"R:R 1:{r.risk_reward:.2f}"
                )
        except Exception as e:
            lines.append(f"{tf}: error — {e}")
    return "\n".join(lines)


def handle_command(text):
    parts = text.strip().split()
    if not parts:
        return HELP_TEXT

    cmd = parts[0].lower().split("@")[0]
    if cmd in ("/start", "/help"):
        return HELP_TEXT
    if cmd == "/signal":
        pair = parts[1].upper() if len(parts) > 1 else None
        if pair and not PAIR_RE.match(pair):
            return "Invalid pair format — use e.g. GBP/USD."
        return run_signal(pair)
    return "Unknown command. " + HELP_TEXT
