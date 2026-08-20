import dataclasses
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import Config
from bot.data.economic_calendar import EconomicCalendar
from bot.data.twelvedata_client import TwelveDataClient
from bot.notify.telegram import send_message as send_telegram_message
from bot.strategy.combined_signal import analyze
from bot.telegram_commands import handle_command

TIMEFRAMES = ["5min", "15min", "30min", "1h"]
PAIR_RE = re.compile(r"^[A-Z]{3}/[A-Z]{3}$")


class handler(BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-App-Password, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/telegram"):
            self._send_json(200, {"ok": True})
            return
        self._handle_analyze()

    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith("/api/telegram"):
            self._handle_telegram_webhook()
            return
        self.send_response(404)
        self._cors_headers()
        self.end_headers()

    def _handle_telegram_webhook(self):
        expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        if expected_secret and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != expected_secret:
            self.send_response(401)
            self._cors_headers()
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"

        self.send_response(200)
        self._cors_headers()
        self.end_headers()

        try:
            update = json.loads(raw)
            message = update.get("message") or update.get("edited_message") or {}
            text = message.get("text", "")
            chat_id = message.get("chat", {}).get("id")
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

            if chat_id and bot_token and text:
                reply = handle_command(text)
                send_telegram_message(bot_token, str(chat_id), reply)
        except Exception:
            pass

    def _handle_analyze(self):
        expected_password = os.getenv("APP_PASSWORD")
        if expected_password and self.headers.get("X-App-Password") != expected_password:
            self._send_json(401, {"error": "Invalid or missing password."})
            return

        try:
            query = parse_qs(urlparse(self.path).query)

            if query.get("ping", [None])[0]:
                self._send_json(200, {"ok": True})
                return

            base_config = Config.load()

            requested_pair = query.get("pair", [None])[0]
            if requested_pair:
                requested_pair = requested_pair.upper()
                if PAIR_RE.match(requested_pair):
                    base_config = dataclasses.replace(base_config, pair=requested_pair)

            calendar = EconomicCalendar(base_config)

            results = []
            for tf in TIMEFRAMES:
                config = dataclasses.replace(base_config, granularity=tf)
                client = TwelveDataClient(config)
                try:
                    r = analyze(config, client, calendar)
                    results.append(
                        {
                            "timeframe": tf,
                            "pair": r.pair,
                            "regime": r.regime,
                            "signal": r.signal,
                            "confidence": r.confidence,
                            "entry": r.entry,
                            "stop_loss": r.stop_loss,
                            "take_profit": r.take_profit,
                            "risk_reward": r.risk_reward,
                            "reasoning": r.reasoning,
                            "caveats": r.caveats,
                        }
                    )
                except Exception as e:
                    results.append({"timeframe": tf, "error": str(e)})

            self._send_json(200, {"pair": base_config.pair, "results": results})
        except Exception as e:
            self._send_json(500, {"error": str(e)})
