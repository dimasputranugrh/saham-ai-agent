import json
import os
import shutil
import threading
import time
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from rich.console import Console
from rich.panel import Panel

import config
from bot.telegram_bot import start_telegram_bot

console = Console()


class HealthCheckHandler(BaseHTTPRequestHandler):
    _rate_buckets: dict[str, list[float]] = defaultdict(list)

    def _client_ip(self) -> str:
        return self.client_address[0] if self.client_address else "unknown"

    def _rate_limited(self, limit: int = 120, window: int = 60) -> bool:
        now = time.time()
        bucket = self._rate_buckets[self._client_ip()]
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            return True
        bucket.append(now)
        return False

    def _api_authorized(self, parsed) -> bool:
        if not config.API_AUTH_TOKEN:
            return True
        supplied = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if not supplied:
            supplied = (parse_qs(parsed.query).get("token") or [""])[0]
        return supplied == config.API_AUTH_TOKEN

    def _send_error_json(self, status: int, message: str):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/portfolio/buy-demo":
            if not config.ENABLE_DEMO_TRADING:
                self._send_error_json(403, "Demo trading dinonaktifkan. Set ENABLE_DEMO_TRADING=true untuk mengaktifkan.")
                return
            if not self._api_authorized(parsed):
                self._send_error_json(401, "Token API tidak valid.")
                return
            if self._rate_limited():
                self._send_error_json(429, "Terlalu banyak permintaan.")
                return
            self._handle_buy_demo(parsed)
            return
        self._send_error_json(404, "Endpoint tidak ditemukan.")

    def _handle_buy_demo(self, parsed):
        try:
            qs = parse_qs(parsed.query)
            ticker = qs.get("ticker", ["BBCA"])[0]
            lots = int(qs.get("lots", ["10"])[0])
            if not 1 <= lots <= 100:
                self._send_error_json(400, "lots harus antara 1 dan 100.")
                return
            from analyzer.technical import analyze_ticker_quant
            norm = config.normalize_ticker(ticker)
            snap = analyze_ticker_quant(norm)
            price = snap.current_price if snap and snap.current_price > 0 else 5000.0
            tp1 = snap.take_profit_1 if snap and snap.take_profit_1 > price else round(price * 1.04)
            tp2 = snap.take_profit_2 if snap and snap.take_profit_2 > tp1 else round(price * 1.08)
            sl = snap.stop_loss if snap and snap.stop_loss < price else round(price * 0.96)

            config.apply_trade(
                "BUY",
                norm,
                lots,
                price,
                plan={"tp1": tp1, "tp2": tp2, "sl": sl},
                note="demo chart",
            )

            resp = json.dumps({
                "status": "ok",
                "ticker": norm.replace(".JK", ""),
                "price": price,
                "lots": lots,
                "tp1": tp1,
                "tp2": tp2,
                "sl": sl,
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        except Exception as e:
            self._send_error_json(500, str(e))

    def do_GET(self):
        if self.path == "/healthz" or "health" in self.path:
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok","service":"saham-ai-agent"}')
            return

        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if not self._api_authorized(parsed):
                self._send_error_json(401, "Token API tidak valid.")
                return
            if self._rate_limited():
                self._send_error_json(429, "Terlalu banyak permintaan.")
                return

        # Real-time API & SSE Stream
        if self.path == "/api/live/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                from bot.live_office import get_live_office_data
                data = json.dumps(get_live_office_data())
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass
            return

        # API Rekomendasi Saham Bagus (Picks) Real-Time
        if self.path.startswith("/api/picks") or self.path.startswith("/api/chart/picks"):
            try:
                from bot.chart_view import get_top_picks
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                force = qs.get("refresh", ["0"])[0] in {"1", "true", "yes"}
                picks_data = get_top_picks(force_refresh=force)
                data = json.dumps(picks_data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"error":"{str(e)}"}}'.encode())
                return

        # Mutasi portfolio hanya lewat POST + ENABLE_DEMO_TRADING.
        if parsed.path.startswith("/api/portfolio/buy-demo"):
            self._send_error_json(405, "Gunakan POST untuk endpoint ini.")
            return

        # API Data Candlestick & Overlays TradingView Lightweight Charts
        if self.path.startswith("/api/chart"):
            try:
                from bot.chart_view import get_candlestick_chart_data
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                ticker = qs.get("ticker", ["BBCA"])[0]
                tf = qs.get("timeframe", ["15m"])[0]
                chart_data = get_candlestick_chart_data(ticker, tf)
                data = json.dumps(chart_data).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"error":"{str(e)}"}}'.encode())
                return

        # Real-time API Virtual Office Karyawan AI
        if self.path.startswith("/api/live") or self.path.startswith("/api/office"):
            try:
                from bot.live_office import get_live_office_data
                data = json.dumps(get_live_office_data()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"error":"{str(e)}"}}'.encode())
                return

        if self.path.startswith("/api"):
            try:
                from bot.dashboard import get_dashboard_summary
                data = json.dumps(get_dashboard_summary()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"error":"{str(e)}"}}'.encode())
                return

        # Halaman Virtual Office Karyawan AI (/live atau /office)
        if self.path.startswith("/live") or self.path.startswith("/office"):
            try:
                from bot.live_office import render_live_office_html
                html_content = render_live_office_html().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_content)))
                self.end_headers()
                self.wfile.write(html_content)
                return
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"status":"error","page":"live","error":"{str(e)}"}}'.encode())
                return

        # Halaman Terminal TradingView AI (/chart atau /twa)
        if self.path.startswith("/chart") or self.path.startswith("/twa"):
            try:
                from bot.chart_view import render_tradingview_chart_html
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                ticker = qs.get("ticker", ["BBCA"])[0]
                html_content = render_tradingview_chart_html(ticker).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_content)))
                self.end_headers()
                self.wfile.write(html_content)
                return
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"status":"error","page":"chart","error":"{str(e)}"}}'.encode())
                return

        # Render Web Dashboard Monitoring & Rekap Saham Utama (Root /)
        try:
            from bot.dashboard import render_dashboard_html
            html_content = render_dashboard_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content)))
            self.end_headers()
            self.wfile.write(html_content)
        except Exception as e:
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(f'{{"status":"ok","service":"saham-ai-agent","note":"{str(e)}"}}'.encode())

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        pass


def start_health_check_server():
    """Menjalankan HTTP server mini untuk health-check Koyeb / Cloud."""
    port = int(os.environ.get("PORT", 8000))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        console.print(f"[bold green]🌐 Health check HTTP server aktif di port {port}[/bold green]")
    except Exception as e:
        console.print(f"[bold yellow]⚠️ Peringatan: Health check server gagal start ({e})[/bold yellow]")


def ensure_env_file():
    env_path = Path(__file__).resolve().parent / ".env"
    example_path = Path(__file__).resolve().parent / ".env.example"
    if not env_path.exists() and example_path.exists():
        shutil.copy(example_path, env_path)


def main():
    ensure_env_file()
    token = config.TELEGRAM_BOT_TOKEN
    if not token or token.startswith("masukkan_"):
        console.print(
            Panel(
                "[bold yellow]⚠️ TELEGRAM_BOT_TOKEN belum diisi di file .env![/bold yellow]\n\n"
                "Silakan buka file [bold cyan]/home/dimas/projects/saham-ai-agent/.env[/bold cyan] lalu isi:\n"
                "1. [bold]GEMINI_API_KEY[/bold] (Buat gratis di https://aistudio.google.com/app/apikey)\n"
                "2. [bold]TELEGRAM_BOT_TOKEN[/bold] (Chat ke @BotFather di Telegram -> ketik /newbot)\n"
                "3. [bold]TELEGRAM_CHAT_ID[/bold] (Wajib diisi dengan ID Telegram pemilik; ketik /start ke bot untuk melihat ID-nya. Tanpa ini semua perintah ditolak.)\n\n"
                "💡 [italic]Sambil menunggu token diisi, Anda bisa langsung mengetes kerja 6 AI di terminal dengan perintah:[/italic]\n"
                "   [green].venv/bin/python cli_demo.py dsu[/green]\n"
                "   [green].venv/bin/python cli_demo.py cek BBCA[/green]",
                title="🤖 Sistem Karyawan AI Saham",
            )
        )
        return

    # Nyalakan health check endpoint agar Koyeb / Cloud statusnya selalu hijau (Healthy)
    start_health_check_server()
    start_telegram_bot()


if __name__ == "__main__":
    main()
