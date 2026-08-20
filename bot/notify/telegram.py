import logging

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def send_message(bot_token: str, chat_id: str, text: str) -> bool:
    if not bot_token or not chat_id:
        logger.info("Telegram not configured — skipping message.")
        return False
    try:
        resp = requests.post(
            f"{TELEGRAM_API}/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.warning("Telegram message failed.", exc_info=True)
        return False
