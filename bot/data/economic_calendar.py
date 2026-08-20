import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from bot.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://finnhub.io/api/v1"


@dataclass
class CalendarEvent:
    datetime_utc: datetime
    currency: str
    event: str
    impact: str  # "low" | "medium" | "high"


class EconomicCalendar:
    """
    Wraps Finnhub's economic calendar endpoint. This is a best-effort
    fundamental filter, not a core dependency — if the API call fails
    (missing key, rate limit, endpoint moved to a paid tier, etc.) callers
    should treat it as "no fundamental data available" and fall back to
    technical-only analysis rather than crash. Free-tier access to this
    endpoint has changed over time on Finnhub's side, so verify current
    terms when you sign up.
    """

    def __init__(self, config: Config):
        self.config = config
        self.enabled = bool(config.finnhub_api_key)

    def get_upcoming_events(
        self, currencies: list[str], hours_ahead: int = 48
    ) -> list[CalendarEvent]:
        if not self.enabled:
            logger.info("FINNHUB_API_KEY not set — skipping fundamental calendar check.")
            return []

        now = datetime.now(timezone.utc)
        params = {
            "from": now.strftime("%Y-%m-%d"),
            "to": (now + timedelta(hours=hours_ahead)).strftime("%Y-%m-%d"),
            "token": self.config.finnhub_api_key,
        }
        try:
            resp = requests.get(f"{BASE_URL}/calendar/economic", params=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            logger.warning(
                "Economic calendar fetch failed — continuing with technical-only analysis.",
                exc_info=True,
            )
            return []

        raw_events = payload.get("economicCalendar", payload.get("data", []))
        events: list[CalendarEvent] = []
        for e in raw_events:
            currency = e.get("country") or e.get("currency")
            if currency not in currencies:
                continue
            try:
                event_time = datetime.fromisoformat(e["time"]).replace(tzinfo=timezone.utc)
            except (KeyError, ValueError):
                continue
            if not (now <= event_time <= now + timedelta(hours=hours_ahead)):
                continue
            events.append(
                CalendarEvent(
                    datetime_utc=event_time,
                    currency=currency,
                    event=e.get("event", "Unknown event"),
                    impact=(e.get("impact") or "low").lower(),
                )
            )
        return sorted(events, key=lambda ev: ev.datetime_utc)

    def high_impact_soon(
        self, currencies: list[str], hours_ahead: int = 6
    ) -> Optional[CalendarEvent]:
        """Returns the nearest high-impact event within `hours_ahead`, if any."""
        for ev in self.get_upcoming_events(currencies, hours_ahead=hours_ahead):
            if ev.impact == "high":
                return ev
        return None
