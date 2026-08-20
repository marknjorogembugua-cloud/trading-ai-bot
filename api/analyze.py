import dataclasses
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import Config
from bot.data.economic_calendar import EconomicCalendar
from bot.data.twelvedata_client import TwelveDataClient
from bot.strategy.combined_signal import analyze

TIMEFRAMES = ["5min", "15min", "30min"]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            base_config = Config.load()
            calendar = EconomicCalendar(base_config)

            results = []
            for tf in TIMEFRAMES:
                config = dataclasses.replace(base_config, granularity=tf)
                client = TwelveDataClient(config)
                try:
                    r = analyze(config, client, calendar, account_balance=10000)
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

            body = json.dumps({"pair": base_config.pair, "results": results}).encode()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
