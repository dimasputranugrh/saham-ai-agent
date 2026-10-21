import os
import shutil
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

import config
from bot.telegram_bot import start_telegram_bot

console = Console()


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok","service":"saham-ai-agent"}')

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
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
                "3. [bold]TELEGRAM_CHAT_ID[/bold] (Bisa dikosongkan dulu, nanti ketik /start di bot Anda untuk melihat ID-nya)\n\n"
                "💡 [italic]Sambil menunggu token diisi, Anda bisa langsung mengetes kerja 4 Karyawan AI di terminal dengan perintah:[/italic]\n"
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
