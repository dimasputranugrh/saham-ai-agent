import asyncio
import datetime as dt
import logging
import pytz
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
from agents.team import (
    analyze_single_stock_with_team,
    chat_with_ai_team,
    generate_intraday_scanner_alert,
    generate_morning_dsu_report,
)

logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("SahamAIBot")


async def _send_safe_markdown(message_or_bot, text: str, chat_id: int | str | None = None):
    """Mengirim pesan Telegram dengan fallback plain text jika ada karakter Markdown yang bentrok."""
    try:
        if chat_id is not None:
            await message_or_bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
        else:
            await message_or_bot.reply_text(text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        if chat_id is not None:
            await message_or_bot.send_message(chat_id=chat_id, text=text)
        else:
            await message_or_bot.reply_text(text=text)


def _auto_register_chat_id(chat_id: int | str) -> bool:
    """Otomatis menyimpan TELEGRAM_CHAT_ID ke memori dan file .env saat Bos pertama kali chat."""
    str_id = str(chat_id)
    if not config.TELEGRAM_CHAT_ID or config.TELEGRAM_CHAT_ID.startswith("masukkan_"):
        config.TELEGRAM_CHAT_ID = str_id
        env_file = config.BASE_DIR / ".env"
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
            content = content.replace(
                "TELEGRAM_CHAT_ID=masukkan_chat_id_telegram_anda_disini",
                f"TELEGRAM_CHAT_ID={str_id}",
            )
            env_file.write_text(content, encoding="utf-8")
        return True
    return False


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    auto_saved = _auto_register_chat_id(chat_id)
    status_id = (
        f"✅ *Chat ID Anda (`{chat_id}`) sudah otomatis terdaftar!* Mulai besok pagi jam *{config.DSU_MORNING_TIME} WIB*, laporan DSU & sinyal jam bursa akan otomatis dikirim ke sini."
        if auto_saved or str(chat_id) == config.TELEGRAM_CHAT_ID
        else f"🆔 *Telegram Chat ID Anda:* `{chat_id}`"
    )
    welcome = (
        "👔 *Selamat datang Bos di Meja Trading Karyawan AI Anda!*\n\n"
        f"{status_id}\n\n"
        "👥 *Tim Karyawan AI Anda:*\n"
        "• 👨‍💻 *Budi* — Analis Teknikal & Intraday (VWAP, RSI, MACD, Volume)\n"
        "• 👩‍💼 *Sari* — Analis Berita & Sentimen Pasar\n"
        "• 🛡️ *Hendra* — Manajer Risiko (Area Beli, TP, Cut Loss, Jam Masuk)\n"
        "• 🎯 *Arif* — Kepala Riset & Pemimpin DSU\n\n"
        "⌨️ *Perintah yang Tersedia:*\n"
        "• `/dsu` — Panggil rapat DSU pagi sekarang juga\n"
        "• `/scan` — Cari saham yang bagus dibeli *jam segini*\n"
        "• `/cek <KODE>` — Bedah 1 saham (contoh: `/cek BBCA` atau `/cek ANTM`)\n"
        "• `/watchlist` — Lihat / tambah / hapus daftar saham pantauan\n\n"
        "💬 _Silakan langsung coba ketik `/dsu` atau `/cek BBCA` sekarang!_"
    )
    await _send_safe_markdown(update.message, welcome)


async def cmd_dsu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_msg = await update.message.reply_text(
        "⏳ *Memanggil Budi, Sari, Hendra, dan Arif untuk rapat DSU...*\n_Sedang mengambil data market & berita terbaru..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    report = await asyncio.to_thread(generate_morning_dsu_report)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, report)


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_msg = await update.message.reply_text(
        "📡 *Memindai pergerakan harga & lonjakan volume intraday di watchlist...*",
        parse_mode=ParseMode.MARKDOWN,
    )
    _, report = await asyncio.to_thread(generate_intraday_scanner_alert, 0)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, report)


async def cmd_cek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "📌 Gunakan format: `/cek <KODE_SAHAM>`\nContoh: `/cek BBCA` atau `/cek BREN`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    ticker = context.args[0]
    wait_msg = await update.message.reply_text(
        f"🔍 *Tim AI sedang menganalisis grafik 15m, Daily, dan berita untuk {ticker.upper()}...*",
        parse_mode=ParseMode.MARKDOWN,
    )
    report = await asyncio.to_thread(analyze_single_stock_with_team, ticker)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, report)


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = config.load_watchlist()
    if not context.args:
        clean_list = ", ".join([t.replace(".JK", "") for t in current])
        msg = (
            f"📋 *Watchlist Saham Pantauan ({len(current)} emiten):*\n"
            f"`{clean_list}`\n\n"
            "💡 *Cara Mengubah Watchlist:*\n"
            "• Tambah saham: `/watchlist +BRMS` atau `/watchlist +ICBP`\n"
            "• Hapus saham: `/watchlist -GOTO`"
        )
        await _send_safe_markdown(update.message, msg)
        return

    arg = context.args[0].strip().upper()
    if arg.startswith("+"):
        norm = config.normalize_ticker(arg[1:])
        if norm and norm not in current:
            current.append(norm)
            config.save_watchlist(current)
            await update.message.reply_text(f"✅ Saham *{norm}* berhasil ditambahkan ke pantauan karyawan AI!", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"ℹ️ Saham *{norm}* sudah ada di dalam watchlist.", parse_mode=ParseMode.MARKDOWN)
    elif arg.startswith("-"):
        norm = config.normalize_ticker(arg[1:])
        if norm in current:
            current.remove(norm)
            config.save_watchlist(current)
            await update.message.reply_text(f"🗑️ Saham *{norm}* berhasil dihapus dari watchlist.", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"⚠️ Saham *{norm}* tidak ditemukan di watchlist.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("Gunakan tanda `+` untuk menambah atau `-` untuk menghapus. Contoh: `/watchlist +BBNI`", parse_mode=ParseMode.MARKDOWN)


async def handle_free_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_text = update.message.text.strip()
    wait_msg = await update.message.reply_text("💬 _Tim AI sedang menyiapkan jawaban..._", parse_mode=ParseMode.MARKDOWN)
    reply = await asyncio.to_thread(chat_with_ai_team, user_text)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, reply)


# =====================================================================
# JADWAL OTOMATIS HARIAN (SENIN - JUMAT WIB)
# =====================================================================

async def scheduled_morning_dsu(context: ContextTypes.DEFAULT_TYPE):
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        logger.warning("TELEGRAM_CHAT_ID belum diatur. Lewati pengiriman DSU pagi.")
        return
    logger.info("Menjalankan DSU Pagi otomatis...")
    report = await asyncio.to_thread(generate_morning_dsu_report)
    await _send_safe_markdown(context.bot, report, chat_id=chat_id)


async def scheduled_intraday_scan(context: ContextTypes.DEFAULT_TYPE):
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        return
    logger.info("Menjalankan Scanner Intraday otomatis...")
    qualified, report = await asyncio.to_thread(generate_intraday_scanner_alert, config.MIN_INTRADAY_ALERT_SCORE)
    if qualified:
        await _send_safe_markdown(context.bot, report, chat_id=chat_id)
    else:
        logger.info("Tidak ada saham yang melewati skor ambang batas intraday pada jam ini.")


async def scheduled_market_close(context: ContextTypes.DEFAULT_TYPE):
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        return
    logger.info("Menjalankan Evaluasi Penutupan Pasar...")
    _, report = await asyncio.to_thread(generate_intraday_scanner_alert, 0)
    close_header = "🔔 *EVALUASI PENUTUPAN PASAR SORE (CLOSING MARKET)*\nBerikut posisi akhir & peluang JJS / Swing untuk besok:\n\n"
    await _send_safe_markdown(context.bot, close_header + report, chat_id=chat_id)


def start_telegram_bot():
    token = config.TELEGRAM_BOT_TOKEN
    if not token or token.startswith("masukkan_"):
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN belum diisi di file .env! Silakan isi terlebih dahulu atau jalankan `cli_demo.py` untuk uji coba di terminal."
        )

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("dsu", cmd_dsu))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("cek", cmd_cek))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_chat))

    # Atur Jadwal Kerja Otomatis Karyawan AI (Senin - Jumat, Zona Waktu WIB)
    wib = pytz.timezone(config.TIMEZONE)
    job_queue = app.job_queue

    if job_queue:
        # 1. DSU Pagi (Default 08:15 WIB, Senin - Jumat)
        dsu_h, dsu_m = [int(x) for x in config.DSU_MORNING_TIME.split(":")]
        job_queue.run_daily(
            scheduled_morning_dsu,
            time=dt.time(hour=dsu_h, minute=dsu_m, tzinfo=wib),
            days=(1, 2, 3, 4, 5),
            name="morning_dsu",
        )

        # 2. Intraday Scanner pada Jam Bursa BEI (09:15, 10:00, 11:00, 13:45, 14:30, 15:30 WIB)
        scan_times = [(9, 15), (10, 0), (11, 0), (13, 45), (14, 30), (15, 30)]
        for sh, sm in scan_times:
            job_queue.run_daily(
                scheduled_intraday_scan,
                time=dt.time(hour=sh, minute=sm, tzinfo=wib),
                days=(1, 2, 3, 4, 5),
                name=f"intraday_scan_{sh:02d}_{sm:02d}",
            )

        # 3. Evaluasi Penutupan Pasar (Default 16:15 WIB)
        close_h, close_m = [int(x) for x in config.MARKET_CLOSE_TIME.split(":")]
        job_queue.run_daily(
            scheduled_market_close,
            time=dt.time(hour=close_h, minute=close_m, tzinfo=wib),
            days=(1, 2, 3, 4, 5),
            name="market_close",
        )

    logger.info("🤖 Karyawan AI Saham siap bekerja! Menunggu perintah di Telegram & menjalankan jadwal harian...")
    app.run_polling(drop_pending_updates=True)
