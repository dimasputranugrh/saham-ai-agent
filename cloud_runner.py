from datetime import datetime
import sys
import pytz
import requests
import config
from agents.dev_architect import ask_project_architect, upgrade_project_code
from agents.team import (
    analyze_single_stock_with_team,
    chat_with_ai_team,
    generate_intraday_scanner_alert,
    generate_morning_dsu_report,
    generate_sectoral_news_catalyst_report,
    get_performance_dashboard_report,
    get_ticker_memory_report,
    get_weekly_ai_report,
    swap_panel_ai_model,
)
from memory.learning_loop import LearningLoopOrchestrator


def send_telegram_direct(text: str, chat_id: str | int | None = None):
    """Mengirim pesan langsung via HTTP API Telegram (untuk mode Cloud / GitHub Actions tanpa server menyala terus)."""
    token = config.TELEGRAM_BOT_TOKEN
    target_chat_id = chat_id or config.TELEGRAM_CHAT_ID
    if not token or not target_chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID wajib diisi!")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": target_chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=30,
    )
    if not resp.ok:
        requests.post(url, json={"chat_id": target_chat_id, "text": text}, timeout=30)


def process_pending_telegram_messages():
    """
    Mengecek apakah ada pesan dari Bos di Telegram saat komputer rumah sedang mati,
    lalu membalasnya dan menandai pesan sudah dibaca.
    """
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        return
    base_url = f"https://api.telegram.org/bot{token}"
    try:
        resp = requests.get(f"{base_url}/getUpdates", params={"timeout": 2}, timeout=10).json()
        updates = resp.get("result", [])
        if not updates:
            return
        last_update_id = None
        for upd in updates:
            last_update_id = upd.get("update_id")
            msg = upd.get("message") or {}
            text = (msg.get("text") or "").strip()
            chat_id = (msg.get("chat") or {}).get("id")
            if not text or not chat_id:
                continue

            if text.startswith("/dsu"):
                send_telegram_direct(generate_morning_dsu_report(), chat_id)
            elif text.startswith("/scan"):
                _, rep = generate_intraday_scanner_alert(0)
                send_telegram_direct(rep, chat_id)
            elif text.startswith("/berita") or text.startswith("/sektor"):
                send_telegram_direct(generate_sectoral_news_catalyst_report(), chat_id)
            elif text.startswith("/cek"):
                parts = text.split()
                ticker = parts[1] if len(parts) > 1 else "BBCA"
                send_telegram_direct(analyze_single_stock_with_team(ticker), chat_id)
            elif text.startswith("/evaluasi") or text.startswith("/performa"):
                send_telegram_direct(get_performance_dashboard_report(), chat_id)
            elif text.startswith("/rapor_ai") or text.startswith("/panel_ai"):
                send_telegram_direct(get_weekly_ai_report(), chat_id)
            elif text.startswith("/ganti_ai"):
                parts = text.split()
                send_telegram_direct(swap_panel_ai_model(parts[1:]), chat_id)
            elif text.startswith("/agy"):
                query = text[len("/agy"):].strip()
                send_telegram_direct(ask_project_architect(query, chat_id), chat_id)
            elif text.startswith("/upgrade"):
                inst = text[len("/upgrade"):].strip()
                send_telegram_direct(upgrade_project_code(inst, chat_id), chat_id)
            elif text.startswith("/memori"):
                parts = text.split()
                ticker = parts[1] if len(parts) > 1 else "TLKM"
                send_telegram_direct(get_ticker_memory_report(ticker), chat_id)
            elif not text.startswith("/"):
                send_telegram_direct(chat_with_ai_team(text), chat_id)

        if last_update_id is not None:
            requests.get(f"{base_url}/getUpdates", params={"offset": last_update_id + 1}, timeout=10)
    except Exception:
        pass


def main():
    # 1. Jalankan siklus evaluasi hasil prediksi & pembelajaran sebelum analisis baru
    orchestrator = LearningLoopOrchestrator()
    try:
        orchestrator.run_evaluation_and_learning_cycle()
    except Exception:
        pass

    # 2. Proses bila ada chat tertunda dari Bos di Telegram
    process_pending_telegram_messages()

    # 3. Jalankan mode jadwal cron (dsu / scan / close / weekly_ai)
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "dsu"
    if mode == "dsu":
        report = generate_morning_dsu_report()
        send_telegram_direct(report)
    elif mode == "scan":
        _, report = generate_intraday_scanner_alert(0)
        send_telegram_direct(report)
    elif mode == "news":
        send_telegram_direct(generate_sectoral_news_catalyst_report())
    elif mode == "close":
        _, report = generate_intraday_scanner_alert(0)
        perf_report = get_performance_dashboard_report()
        header = "🔔 *LAPORAN PENUTUPAN PASAR SORE & SELF-LEARNING AI*\n"
        send_telegram_direct(header + report + "\n\n" + perf_report)
        # Jika hari Jumat (weekday == 4), otomatis kirim Rapor Mingguan 5 AI!
        now_wib = datetime.now(pytz.timezone(config.TIMEZONE))
        if now_wib.weekday() == 4:
            send_telegram_direct(get_weekly_ai_report())
    elif mode == "weekly_ai":
        send_telegram_direct(get_weekly_ai_report())


if __name__ == "__main__":
    main()
