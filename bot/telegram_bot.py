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
from agents.dev_architect import ask_project_architect, upgrade_project_code
from agents.team import (
    analyze_single_stock_with_team,
    chat_with_ai_team,
    evaluate_portfolio_sell_signals,
    generate_intraday_scanner_alert,
    generate_morning_dsu_report,
    get_performance_dashboard_report,
    get_ticker_memory_report,
    get_weekly_ai_report,
    swap_panel_ai_model,
)
from memory.learning_loop import LearningLoopOrchestrator
from analyzer.technical import analyze_ticker_quant
from broker.stockbit import capture_stockbit_portfolio, execute_stockbit_order

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
        "• `/beli <KODE> <HARGA>` — Lapor kalau Bos sudah beli (contoh: `/beli BBCA 5250`) biar diingatkan kapan jual!\n"
        "• `/pegang` — Cek saham yang sedang Bos pegang: sudah waktunya jual atau belum\n"
        "• `/jual <KODE>` — Hapus saham dari pantauan jual kalau sudah laku\n"
        "• `/sb_beli <KODE> <LOT> <HARGA>` — Eksekusi Beli otomatis di Stockbit (contoh: `/sb_beli BBCA 1 5250`)\n"
        "• `/sb_jual <KODE> <LOT> <HARGA>` — Eksekusi Jual otomatis di Stockbit (contoh: `/sb_jual BBCA 1 5450`)\n"
        "• `/sb_saldo` — Potret Portofolio & Saldo RDN Stockbit Anda sekarang\n"
        "• `/evaluasi` — Lihat rapor akurasi, Win Rate, Expectancy, & Self-Learning AI\n"
        "• `/rapor_ai` — Rapor Mingguan 5 AI (Siapa paling jago vs Siapa harus diganti)\n"
        "• `/ganti_ai` — Ganti AI yang kurang akurat dengan model AI gratis lain\n"
        "• `/agy <pertanyaan>` — Tanya Antigravity Architect tentang kode/project ini\n"
        "• `/upgrade <instruksi>` — Perintahkan AI meng-upgrade kode project & push ke GitHub\n"
        "• `/memori <KODE>` — Lihat ingatan & pelajaran historis AI pada saham tertentu\n"
        "• `/watchlist` — Lihat / tambah / hapus daftar saham pantauan\n\n"
        "💬 _Silakan langsung coba ketik `/cek BBCA` atau `/rapor_ai` sekarang!_"
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


async def cmd_beli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mencatat saham yang baru dibeli Bos supaya dipantau jam jualnya oleh Hendra & Arif."""
    _auto_register_chat_id(update.effective_chat.id)
    if len(context.args) < 2:
        await update.message.reply_text(
            "🛒 *Cara Lapor Beli Saham:*\n"
            "Ketik: `/beli <KODE> <HARGA_BELI>`\n"
            "Contoh: `/beli BBCA 5250`\n\n"
            "_Nanti Hendra & Arif akan otomatis menjaga saham ini dan memberi tahu Bos kapan harus JUAL!_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker_raw = context.args[0]
    price_raw = context.args[1].replace(".", "").replace(",", "")
    try:
        buy_price = float(price_raw)
    except ValueError:
        await update.message.reply_text("⚠️ Harga beli harus berupa angka. Contoh: `/beli BBCA 5250`", parse_mode=ParseMode.MARKDOWN)
        return

    norm = config.normalize_ticker(ticker_raw)
    snap = await asyncio.to_thread(analyze_ticker_quant, norm)
    tp1 = snap.take_profit_1 if snap and snap.take_profit_1 > buy_price else round(buy_price * 1.04)
    tp2 = snap.take_profit_2 if snap and snap.take_profit_2 > tp1 else round(buy_price * 1.08)
    sl = snap.stop_loss if snap and snap.stop_loss < buy_price else round(buy_price * 0.96)

    portfolio = config.load_portfolio()
    portfolio[norm] = {
        "buy_price": buy_price,
        "tp1": tp1,
        "tp2": tp2,
        "sl": sl,
        "bought_at": dt.datetime.now(pytz.timezone(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M WIB"),
    }
    config.save_portfolio(portfolio)

    code = norm.replace(".JK", "")
    msg = (
        f"✅ *Siap Bos! Saham {code} di harga Rp {buy_price:,.0f} sudah dicatat Hendra & Arif!*\n\n"
        f"🎯 *Rencana Jual Otomatis Anda:*\n"
        f"• 💰 *Target Jual Untung 1 (TP1):* Rp {tp1:,.0f} (+{((tp1-buy_price)/buy_price*100):.1f}%)\n"
        f"• 🚀 *Target Jual Untung 2 (TP2):* Rp {tp2:,.0f} (+{((tp2-buy_price)/buy_price*100):.1f}%)\n"
        f"• 🛑 *Batas Rem Darurat (SL):* < Rp {sl:,.0f} ({((sl-buy_price)/buy_price*100):.1f}%)\n\n"
        f"⏰ *Kapan Harus Jual?*\n"
        f"1. *Pasang Antrian Jual Otomatis (Auto-Order)* di aplikasi sekuritas Anda pada harga *Rp {tp1:,.0f}*.\n"
        f"2. Biasanya harga menyentuh target jual pada *jam 09:15 - 10:30 WIB* (lonjakan pagi) atau *jam 14:30 - 15:45 WIB* (sesi sore).\n"
        f"3. Setiap jam bursa, kami akan otomatis mengecek saham *{code}* ini dan mengirim pesan ke Telegram Bos kalau sudah waktunya **JUAL SEKARANG**!\n\n"
        f"_Ketik `/pegang` kapan saja untuk cek status jualnya._"
    ).replace(",", ".")
    await _send_safe_markdown(update.message, msg)


async def cmd_pegang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    wait_msg = await update.message.reply_text("💼 _Mengecek harga terbaru saham yang sedang Bos pegang..._", parse_mode=ParseMode.MARKDOWN)
    report = await asyncio.to_thread(evaluate_portfolio_sell_signals, True)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, report)


async def cmd_jual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Ketik `/jual <KODE>` jika sahamnya sudah Bos jual. Contoh: `/jual BBCA`", parse_mode=ParseMode.MARKDOWN)
        return
    norm = config.normalize_ticker(context.args[0])
    portfolio = config.load_portfolio()
    if norm in portfolio:
        del portfolio[norm]
        config.save_portfolio(portfolio)
        await update.message.reply_text(f"🎉 Mantap Bos! Saham *{norm.replace('.JK', '')}* sudah dihapus dari daftar pantauan jual.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"ℹ️ Saham *{norm.replace('.JK', '')}* belum ada di catatan `/pegang`.", parse_mode=ParseMode.MARKDOWN)


async def cmd_sb_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memotret Portofolio & Saldo RDN Stockbit di belakang layar dan mengirim fotonya ke Telegram."""
    _auto_register_chat_id(update.effective_chat.id)
    wait_msg = await update.message.reply_text("🤖 _Sedang membuka Stockbit Anda di belakang layar & memotret Portofolio..._", parse_mode=ParseMode.MARKDOWN)
    ok, caption, img_path = await capture_stockbit_portfolio()
    await wait_msg.delete()
    if ok and img_path and img_path.exists():
        with open(img_path, "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file, caption=caption, parse_mode=ParseMode.MARKDOWN)
    else:
        await _send_safe_markdown(update.message, caption)


async def cmd_sb_beli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eksekusi Beli otomatis ke Stockbit + otomatis masuk pantauan jual Hendra & Arif."""
    _auto_register_chat_id(update.effective_chat.id)
    if len(context.args) < 3:
        await update.message.reply_text(
            "🛒 *Cara Beli Otomatis ke Stockbit:*\n"
            "Ketik: `/sb_beli <KODE> <JUMLAH_LOT> <HARGA>`\n"
            "Contoh: `/sb_beli BBCA 1 5250` _(Beli BBCA 1 Lot di harga Rp 5.250)_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker_raw = context.args[0]
    try:
        lots = int(context.args[1])
        price = float(context.args[2].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("⚠️ Format salah. Contoh: `/sb_beli BBCA 1 5250`", parse_mode=ParseMode.MARKDOWN)
        return

    wait_msg = await update.message.reply_text(
        f"🤖 *Robot sedang masuk ke Stockbit untuk BELI {ticker_raw.upper()} ({lots} Lot @ Rp {price:,.0f})...*",
        parse_mode=ParseMode.MARKDOWN,
    )
    ok, caption, img_path = await execute_stockbit_order("BUY", ticker_raw, lots, price)
    await wait_msg.delete()

    if ok:
        # Otomatis daftarkan ke pantauan portofolio Hendra & Arif!
        norm = config.normalize_ticker(ticker_raw)
        snap = await asyncio.to_thread(analyze_ticker_quant, norm)
        tp1 = snap.take_profit_1 if snap and snap.take_profit_1 > price else round(price * 1.04)
        tp2 = snap.take_profit_2 if snap and snap.take_profit_2 > tp1 else round(price * 1.08)
        sl = snap.stop_loss if snap and snap.stop_loss < price else round(price * 0.96)
        portfolio = config.load_portfolio()
        portfolio[norm] = {
            "buy_price": price,
            "lots": lots,
            "tp1": tp1,
            "tp2": tp2,
            "sl": sl,
            "bought_at": dt.datetime.now(pytz.timezone(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M WIB"),
        }
        config.save_portfolio(portfolio)

    if ok and img_path and img_path.exists():
        with open(img_path, "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file, caption=caption, parse_mode=ParseMode.MARKDOWN)
    else:
        await _send_safe_markdown(update.message, caption)


async def cmd_sb_jual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eksekusi Jual otomatis ke Stockbit."""
    _auto_register_chat_id(update.effective_chat.id)
    if len(context.args) < 3:
        await update.message.reply_text(
            "💰 *Cara Jual Otomatis ke Stockbit:*\n"
            "Ketik: `/sb_jual <KODE> <JUMLAH_LOT> <HARGA>`\n"
            "Contoh: `/sb_jual BBCA 1 5450` _(Jual BBCA 1 Lot di harga Rp 5.450)_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker_raw = context.args[0]
    try:
        lots = int(context.args[1])
        price = float(context.args[2].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("⚠️ Format salah. Contoh: `/sb_jual BBCA 1 5450`", parse_mode=ParseMode.MARKDOWN)
        return

    wait_msg = await update.message.reply_text(
        f"🤖 *Robot sedang masuk ke Stockbit untuk JUAL {ticker_raw.upper()} ({lots} Lot @ Rp {price:,.0f})...*",
        parse_mode=ParseMode.MARKDOWN,
    )
    ok, caption, img_path = await execute_stockbit_order("SELL", ticker_raw, lots, price)
    await wait_msg.delete()

    if ok and img_path and img_path.exists():
        with open(img_path, "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file, caption=caption, parse_mode=ParseMode.MARKDOWN)
    else:
        await _send_safe_markdown(update.message, caption)


async def cmd_evaluasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    mode = context.args[0].upper() if context.args else None
    wait_msg = await update.message.reply_text("📊 _Mengevaluasi hasil prediksi historis & menghitung metrik performa strategi..._", parse_mode=ParseMode.MARKDOWN)
    report = await asyncio.to_thread(get_performance_dashboard_report, mode)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, report)


async def cmd_memori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    ticker = context.args[0] if context.args else "TLKM"
    report = await asyncio.to_thread(get_ticker_memory_report, ticker)
    await _send_safe_markdown(update.message, report)


async def cmd_rapor_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    wait_msg = await update.message.reply_text(
        "🏆 _Menghitung akurasi masing-masing dari 5 AI & menyusun Rapor Mingguan..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    report = await asyncio.to_thread(get_weekly_ai_report)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, report)


async def cmd_ganti_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    args = list(context.args) if context.args else []
    report = await asyncio.to_thread(swap_panel_ai_model, args)
    await _send_safe_markdown(update.message, report)


async def cmd_agy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    _auto_register_chat_id(chat_id)
    query = " ".join(context.args) if context.args else ""
    wait_msg = await update.message.reply_text(
        "🤖 _Antigravity Architect sedang memeriksa kode project Anda..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    reply = await asyncio.to_thread(ask_project_architect, query, chat_id)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, reply)


async def cmd_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    _auto_register_chat_id(chat_id)
    instruction = " ".join(context.args) if context.args else ""
    wait_msg = await update.message.reply_text(
        "🛠️ _Antigravity Architect sedang menyusun upgrade kode, menguji sintaks, & sinkronisasi ke GitHub..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    reply = await asyncio.to_thread(upgrade_project_code, instruction, chat_id)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, reply)


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
    sell_alert = await asyncio.to_thread(evaluate_portfolio_sell_signals, False)
    if qualified:
        await _send_safe_markdown(context.bot, report, chat_id=chat_id)
    elif sell_alert:
        await _send_safe_markdown(context.bot, sell_alert, chat_id=chat_id)
    else:
        logger.info("Tidak ada sinyal beli baru maupun sinyal jual darurat pada jam ini.")


async def scheduled_market_close(context: ContextTypes.DEFAULT_TYPE):
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        return
    logger.info("Menjalankan Evaluasi Penutupan Pasar & Self-Learning Loop...")
    orchestrator = LearningLoopOrchestrator()
    await asyncio.to_thread(orchestrator.run_evaluation_and_learning_cycle)
    _, report = await asyncio.to_thread(generate_intraday_scanner_alert, 0)
    perf_summary = await asyncio.to_thread(get_performance_dashboard_report)
    close_header = "🔔 *EVALUASI PENUTUPAN PASAR SORE (CLOSING MARKET)*\nBerikut posisi akhir & peluang JJS / Swing untuk besok:\n\n"
    await _send_safe_markdown(context.bot, close_header + report + "\n\n" + perf_summary, chat_id=chat_id)


async def scheduled_learning_evaluation(context: ContextTypes.DEFAULT_TYPE):
    """Menjalankan siklus evaluasi hasil prediksi & pembaruan strategy_lessons secara idempoten."""
    logger.info("Menjalankan siklus evaluasi prediksi & pembelajaran strategi otomatis...")
    orchestrator = LearningLoopOrchestrator()
    await asyncio.to_thread(orchestrator.run_evaluation_and_learning_cycle)


async def scheduled_weekly_ai_report(context: ContextTypes.DEFAULT_TYPE):
    """Mengirim Rapor Mingguan 5 AI setiap hari Jumat sore (16:20 WIB)."""
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        return
    logger.info("Mengirim Rapor Mingguan 5 AI otomatis...")
    report = await asyncio.to_thread(get_weekly_ai_report)
    await _send_safe_markdown(context.bot, report, chat_id=chat_id)


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
    app.add_handler(CommandHandler("beli", cmd_beli))
    app.add_handler(CommandHandler("pegang", cmd_pegang))
    app.add_handler(CommandHandler("portofolio", cmd_pegang))
    app.add_handler(CommandHandler("jual", cmd_jual))
    app.add_handler(CommandHandler("sb_saldo", cmd_sb_saldo))
    app.add_handler(CommandHandler("sb_portofolio", cmd_sb_saldo))
    app.add_handler(CommandHandler("sb_beli", cmd_sb_beli))
    app.add_handler(CommandHandler("sb_jual", cmd_sb_jual))
    app.add_handler(CommandHandler("evaluasi", cmd_evaluasi))
    app.add_handler(CommandHandler("performa", cmd_evaluasi))
    app.add_handler(CommandHandler("rapor_ai", cmd_rapor_ai))
    app.add_handler(CommandHandler("panel_ai", cmd_rapor_ai))
    app.add_handler(CommandHandler("ganti_ai", cmd_ganti_ai))
    app.add_handler(CommandHandler("agy", cmd_agy))
    app.add_handler(CommandHandler("upgrade", cmd_upgrade))
    app.add_handler(CommandHandler("memori", cmd_memori))
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

        # 4. Siklus Evaluasi Prediksi & Self-Learning Otomatis (12:05 WIB istirahat siang & 16:30 WIB setelah tutup pasar)
        for lh, lm in [(12, 5), (16, 30)]:
            job_queue.run_daily(
                scheduled_learning_evaluation,
                time=dt.time(hour=lh, minute=lm, tzinfo=wib),
                days=(1, 2, 3, 4, 5),
                name=f"learning_eval_{lh:02d}_{lm:02d}",
            )
        close_h, close_m = [int(x) for x in config.MARKET_CLOSE_TIME.split(":")]
        job_queue.run_daily(
            scheduled_market_close,
            time=dt.time(hour=close_h, minute=close_m, tzinfo=wib),
            days=(1, 2, 3, 4, 5),
            name="market_close",
        )

        # 5. Rapor Mingguan 5 AI setiap hari Jumat sore (16:20 WIB)
        job_queue.run_daily(
            scheduled_weekly_ai_report,
            time=dt.time(hour=16, minute=20, tzinfo=wib),
            days=(5,),
            name="weekly_ai_report_friday",
        )

    logger.info("🤖 Karyawan AI Saham siap bekerja! Menunggu perintah di Telegram & menjalankan jadwal harian...")
    app.run_polling(drop_pending_updates=True)
