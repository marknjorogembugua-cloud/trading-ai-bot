import logging

import requests

logger = logging.getLogger(__name__)

NTFY_BASE_URL = "https://ntfy.sh"


def send_push(topic: str, title: str, message: str, priority: str = "high") -> bool:
    """
    Sends a push notification via ntfy.sh — free, no signup required. The
    user installs the ntfy app (Android/iOS/web) and subscribes to `topic`.

    ntfy.sh topics are public by name (anyone who knows/guesses the topic
    string can subscribe) unless self-hosted with auth — pick a long,
    hard-to-guess topic name, don't use something obvious like your name.
    """
    if not topic:
        logger.info("No NTFY_TOPIC configured — skipping push notification.")
        return False
    try:
        resp = requests.post(
            f"{NTFY_BASE_URL}/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.warning("Push notification failed.", exc_info=True)
        return False
