import json
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import pandas as pd
from http.server import HTTPServer

import main
from analyzer.bandarmologi import analyze_bandarmologi_footprint
from bot.chart_view import render_tradingview_chart_html
from bot.telegram_bot import get_main_menu_keyboard


class TestAdvancedFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start main.HealthCheckHandler on a free test port in a background thread
        cls.port = 18889
        cls.server = HTTPServer(("127.0.0.1", cls.port), main.HealthCheckHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_bandarmologi_accumulation(self):
        """Uji deteksi akumulasi bandarmologi saat CMF tinggi dan harga tutup di atas."""
        dates = pd.date_range("2026-01-01", periods=15, freq="D")
        df_daily = pd.DataFrame({
            "Open": [5000 + i * 10 for i in range(15)],
            "High": [5100 + i * 10 for i in range(15)],
            "Low": [4980 + i * 10 for i in range(15)],
            "Close": [5090 + i * 10 for i in range(15)],
            "Volume": [1000000] * 15,
        }, index=dates)

        res = analyze_bandarmologi_footprint("BBCA.JK", df_daily, cmf_val=0.15, vol_ratio=1.8)
        self.assertIn("AKUMULASI", res["status"])
        self.assertIn("AK (UBS)", res["top_buyers_estimate"])
        self.assertGreater(res["top_broker_concentration_pct"], 50.0)

    def test_bandarmologi_distribution(self):
        """Uji deteksi distribusi bandarmologi saat CMF negatif deras."""
        dates = pd.date_range("2026-01-01", periods=15, freq="D")
        df_daily = pd.DataFrame({
            "Open": [5100 - i * 10 for i in range(15)],
            "High": [5110 - i * 10 for i in range(15)],
            "Low": [4900 - i * 10 for i in range(15)],
            "Close": [4910 - i * 10 for i in range(15)],
            "Volume": [2000000] * 15,
        }, index=dates)

        res = analyze_bandarmologi_footprint("BBRI.JK", df_daily, cmf_val=-0.12, vol_ratio=2.0)
        self.assertIn("DISTRIBUSI", res["status"])
        self.assertIn("YP (Mirae)", res["top_buyers_estimate"])

    def test_tradingview_chart_html_generation(self):
        """Uji rendering template TradingView Lightweight Charts v4."""
        html = render_tradingview_chart_html("BBCA")
        self.assertIn("lightweight-charts", html)
        self.assertIn("BBCA", html)
        self.assertIn("chartContainer", html)
        self.assertIn("Telegram.WebApp", html)

    def test_telegram_main_menu_keyboard(self):
        """Uji inline keyboard Telegram dengan tombol WebApp TradingView & Live Office."""
        markup = get_main_menu_keyboard()
        self.assertIsNotNone(markup)
        buttons = markup.inline_keyboard
        flat_buttons = [btn for row in buttons for btn in row]
        chart_btn = next((b for b in flat_buttons if "TradingView" in b.text), None)
        self.assertIsNotNone(chart_btn)
        self.assertIsNotNone(chart_btn.web_app)
        self.assertTrue(chart_btn.web_app.url.endswith("/chart"))

        live_btn = next((b for b in flat_buttons if "Kantor AI Live" in b.text), None)
        self.assertIsNotNone(live_btn)
        self.assertTrue(live_btn.url.endswith("/live"))

    @patch("bot.chart_view.get_candlestick_chart_data")
    def test_http_api_chart_endpoint(self, mock_get_chart):
        """Uji endpoint HTTP /api/chart dengan mock data."""
        mock_get_chart.return_value = {
            "ticker": "BBCA",
            "candles": [{"time": 1700000000, "open": 5000, "high": 5100, "low": 4900, "close": 5050}],
            "levels": {"take_profit_1": 5250, "stop_loss": 4900},
            "bandarmologi": {"status": "AKUMULASI MASIF"},
        }
        url = f"http://127.0.0.1:{self.port}/api/chart?ticker=BBCA"
        with urllib.request.urlopen(url, timeout=5) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertIn("ticker", data)
            self.assertIn("candles", data)
            self.assertIn("levels", data)

    def test_http_chart_html_endpoints(self):
        """Uji endpoint HTTP /chart dan alias /twa."""
        for path in ["/chart?ticker=BBCA", "/twa?ticker=BBCA"]:
            url = f"http://127.0.0.1:{self.port}{path}"
            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertEqual(response.status, 200)
                html = response.read().decode()
                self.assertIn("TradingView", html)
                self.assertIn("Saham Lagi Bagus", html)

    @patch("bot.chart_view.get_top_picks")
    def test_http_api_picks_endpoint(self, mock_get_picks):
        """Uji endpoint HTTP /api/picks untuk mengambil daftar saham yang lagi bagus."""
        mock_get_picks.return_value = {
            "cached": False,
            "updated_at": "21:20:00 WIB",
            "picks": [
                {"ticker": "BBCA", "quant_score": 82, "direction": "BUY", "is_buy": True, "change_pct": 1.5},
                {"ticker": "TLKM", "quant_score": 74, "direction": "BUY", "is_buy": True, "change_pct": 0.8},
            ]
        }
        url = f"http://127.0.0.1:{self.port}/api/picks?refresh=1"
        with urllib.request.urlopen(url, timeout=5) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertIn("picks", data)
            self.assertEqual(len(data["picks"]), 2)
            self.assertEqual(data["picks"][0]["ticker"], "BBCA")
            self.assertTrue(data["picks"][0]["is_buy"])

    def test_job_queue_day_indices(self):
        """Pastikan semua tuple days pada telegram JobQueue berada dalam rentang valid 0..6 (Sun..Sat)."""
        from telegram.ext import JobQueue
        cron_len = len(JobQueue._CRON_MAPPING)
        self.assertEqual(cron_len, 7)

        # Cek kode di bot/telegram_bot.py
        import inspect
        import bot.telegram_bot as tb
        src = inspect.getsource(tb.start_telegram_bot)
        import re
        day_tuples = re.findall(r"days=\(([^)]+)\)", src)
        for dt_str in day_tuples:
            indices = [int(x.strip()) for x in dt_str.split(",") if x.strip()]
            for idx in indices:
                self.assertTrue(0 <= idx < 7, f"Index hari {idx} di luar rentang JobQueue (0..6)")


if __name__ == "__main__":
    unittest.main()
