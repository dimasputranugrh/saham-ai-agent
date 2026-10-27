from datetime import datetime
import logging
import sys
import pytz
import requests
import config
from agents.dev_architect import ask_project_architect, is_authorized_owner, upgrade_project_code
from agents.team import (
    analyze_single_stock_with_team,
    chat_with_ai_team,
    generate_intraday_scanner_alert,
    generate_morning_dsu_report,
    generate_sectoral_news_catalyst_report,
    get_performance_dashboard_report,
    get_ticker_memory_report,
    evaluate_portfolio_sell_signals,
    get_weekly_ai_report,
    swap_panel_ai_model,
)
from memory.learning_loop import LearningLoopOrchestrator
from analyzer.technical import analyze_ticker_quant

logger = logging.getLogger("SahamAICloud")


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

            if not is_authorized_owner(chat_id):
                if text.startswith("/start"):
                    send_telegram_direct(
                        f"🆔 Chat ID Anda: `{chat_id}`\n"
                        "Minta pemilik mengisi `TELEGRAM_CHAT_ID` di `.env` untuk mengaktifkan bot.",
                        chat_id,
                    )
                else:
                    send_telegram_direct("⛔ Akses ditolak. Perintah ini hanya untuk pemilik bot.", chat_id)
                continue

            try:
                if text.startswith("/start") or text.startswith("/help") or text.startswith("/menu") or text.startswith("/bantuan"):
                    help_msg = (
                        "👔 *DAFTAR PERINTAH TIM KARYAWAN AI SAHAM*\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "• `/cek <KODE>` — Bedah 1 saham + Voting 6 AI (contoh: `/cek BBCA`)\n"
                        "• `/scan` — Cari saham bagus buat dibeli jam ini\n"
                        "• `/berita` — Radar perbandingan berita 7 sektor & peluang Masa Depan\n"
                        "• `/dsu` — Laporan rapat pagi lengkap\n"
                        "• `/rapor_ai` — Rapor Mingguan 6 AI (Urutan AI terbaik vs terburuk)\n"
                        "• `/ganti_ai` — Ganti AI yang kurang akurat dengan AI gratis lain\n"
                        "• `/evaluasi` — Rapor akurasi, Win Rate, & Self-Learning strategi\n"
                        "• `/memori <KODE>` — Lihat ingatan database pada saham tertentu\n"
                        "• `/tanya <pertanyaan>` — Tanya AI Architect tentang kode project ini\n"
                        "• `/upgrade <instruksi>` — Suruh AI meng-upgrade kode project & push ke GitHub\n"
                        "• `/beli <KODE> <HARGA>` — Catat saham yang dibeli agar dipantau jam jualnya\n"
                        "• `/pegang` — Cek apakah saham yang dipegang sudah waktunya jual\n"
                        "• `/watchlist` — Lihat / ubah daftar saham pantauan\n\n"
                        "💬 _Atau langsung ketik pertanyaan biasa tanpa garis miring `/`, nanti Tim AI langsung menjawab!_"
                    )
                    send_telegram_direct(help_msg, chat_id)
                elif text.startswith("/dashboard") or text.startswith("/web"):
                    dash_msg = (
                        "📊 *DASHBOARD MONITORING HARGA SAHAM*\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "Bos bisa memantau rekap harga, target TP/SL, dan sinyal 6 AI secara real-time lewat browser:\n\n"
                        "🌐 *Link Dashboard:*\n"
                        f"{config.PUBLIC_BASE_URL}/\n\n"
                        "✨ _Tampilan mobile-friendly, auto-refresh tiap 60 detik, dan bisa dibuka dari HP atau laptop!_"
                    )
                    send_telegram_direct(dash_msg, chat_id)
                elif text.startswith("/dsu"):
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
                elif text.startswith("/tanya"):
                    query = text[len("/tanya"):].strip()
                    send_telegram_direct(ask_project_architect(query, chat_id), chat_id)
                elif text.startswith("/upgrade"):
                    inst = text[len("/upgrade"):].strip()
                    send_telegram_direct(upgrade_project_code(inst, chat_id), chat_id)
                elif text.startswith("/memori"):
                    parts = text.split()
                    ticker = parts[1] if len(parts) > 1 else "TLKM"
                    send_telegram_direct(get_ticker_memory_report(ticker), chat_id)
                elif text.startswith("/beli"):
                    parts = text.split()
                    if len(parts) < 3:
                        send_telegram_direct("Format: `/beli <KODE> <HARGA> [LOT]`", chat_id)
                    else:
                        try:
                            norm = config.normalize_ticker(parts[1])
                            buy_price = float(parts[2].replace(".", "").replace(",", ""))
                            lots = int(parts[3]) if len(parts) > 3 else 1
                            snap = analyze_ticker_quant(norm)
                            tp1 = snap.take_profit_1 if snap and snap.take_profit_1 > buy_price else round(buy_price * 1.04)
                            tp2 = snap.take_profit_2 if snap and snap.take_profit_2 > tp1 else round(buy_price * 1.08)
                            sl = snap.stop_loss if snap and snap.stop_loss < buy_price else round(buy_price * 0.96)
                            config.apply_trade("BUY", norm, lots, buy_price, plan={"tp1": tp1, "tp2": tp2, "sl": sl}, note="cloud beli")
                            send_telegram_direct(f"✅ Dicatat: {norm.replace('.JK','')} {lots} lot @ Rp {buy_price:,.0f}. TP1 {tp1:,.0f} / SL {sl:,.0f}.", chat_id)
                        except Exception:
                            logger.exception("Gagal mencatat /beli")
                            send_telegram_direct("⚠️ Gagal mencatat pembelian. Cek format dan angka.", chat_id)
                elif text.startswith("/jual"):
                    parts = text.split()
                    if len(parts) < 2:
                        send_telegram_direct("Format: `/jual <KODE> [LOT] [HARGA]`", chat_id)
                    else:
                        try:
                            norm = config.normalize_ticker(parts[1])
                            portfolio = config.load_portfolio()
                            if norm not in portfolio:
                                send_telegram_direct(f"ℹ️ {norm.replace('.JK','')} tidak ada di portfolio.", chat_id)
                            else:
                                held = int(portfolio[norm].get("lots", 1))
                                lots = int(parts[2]) if len(parts) > 2 else held
                                if len(parts) > 3:
                                    sell_price = float(parts[3].replace(".", "").replace(",", ""))
                                else:
                                    snap = analyze_ticker_quant(norm)
                                    sell_price = float(snap.current_price) if snap and snap.current_price else float(portfolio[norm].get("buy_price", 0))
                                result = config.apply_trade("SELL", norm, lots, sell_price, note="cloud jual")
                                realized = result["ledger"]["trades"][-1].get("realized_pnl", 0.0)
                                send_telegram_direct(f"🎉 {norm.replace('.JK','')} terjual {lots} lot @ Rp {sell_price:,.0f}. P&L Rp {realized:,.0f}.", chat_id)
                        except Exception:
                            logger.exception("Gagal mencatat /jual")
                            send_telegram_direct("⚠️ Gagal mencatat penjualan. Cek format dan angka.", chat_id)
                elif text.startswith("/pegang") or text.startswith("/portofolio"):
                    send_telegram_direct(evaluate_portfolio_sell_signals(True), chat_id)
                elif text.startswith("/watchlist"):
                    parts = text.split()
                    if len(parts) == 1:
                        send_telegram_direct("📋 Watchlist: " + ", ".join(config.load_watchlist()), chat_id)
                    elif parts[1].startswith("+"):
                        tickers = config.load_watchlist()
                        norm = config.normalize_ticker(parts[1][1:])
                        if norm and norm not in tickers:
                            tickers.append(norm)
                        config.save_watchlist(tickers)
                        send_telegram_direct(f"✅ {norm} ditambahkan.", chat_id)
                    elif parts[1].startswith("-"):
                        tickers = config.load_watchlist()
                        norm = config.normalize_ticker(parts[1][1:])
                        if norm in tickers:
                            tickers.remove(norm)
                        config.save_watchlist(tickers)
                        send_telegram_direct(f"🗑️ {norm} dihapus.", chat_id)
                elif not text.startswith("/"):
                    send_telegram_direct(chat_with_ai_team(text), chat_id)
            except Exception:
                logger.exception("Satu perintah Telegram gagal; lanjut ke perintah berikutnya")

        if last_update_id is not None:
            requests.get(f"{base_url}/getUpdates", params={"offset": last_update_id + 1}, timeout=10)
    except Exception:
        logger.exception("Gagal memproses pesan Telegram cloud")


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
    if mode in ("dsu", "scan", "close") and not config.is_idx_trading_day():
        logger.info("Hari ini bursa libur. Mode %s dilewati.", mode)
        return
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
        # Jika hari Jumat (weekday == 4), otomatis kirim Rapor Mingguan 6 AI!
        now_wib = datetime.now(pytz.timezone(config.TIMEZONE))
        if now_wib.weekday() == 4:
            send_telegram_direct(get_weekly_ai_report())
    elif mode == "weekly_ai":
        send_telegram_direct(get_weekly_ai_report())
    elif mode in ("weekend_news", "weekend"):
        header = "☕ *RADAR BERITA AKHIR PEKAN (INTELIJEN HARI SENIN)* 📰\n_Bursa memang libur, tapi arus berita & katalis emiten tidak pernah tidur!_\n\n"
        send_telegram_direct(header + generate_sectoral_news_catalyst_report())


if __name__ == "__main__":
    main()
