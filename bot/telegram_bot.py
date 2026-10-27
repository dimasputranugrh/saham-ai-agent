import asyncio
import datetime as dt
import logging
import time
import uuid
from functools import wraps
import pytz
from telegram import BotCommand, Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

import config
from agents.dev_architect import ask_project_architect, is_authorized_owner, upgrade_project_code
from agents.team import (
    analyze_single_stock_with_team,
    chat_with_ai_team,
    evaluate_portfolio_sell_signals,
    generate_intraday_scanner_alert,
    generate_morning_dsu_report,
    generate_sectoral_news_catalyst_report,
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
# Jangan log URL API Telegram: URL itu memuat token bot.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Menu command bawaan Telegram. /agy sengaja tidak didaftarkan; penggantinya /tanya.
BOT_COMMANDS = [
    BotCommand("start", "Mulai bot & lihat status"),
    BotCommand("menu", "Tampilkan menu & daftar perintah"),
    BotCommand("dashboard", "Link dashboard monitoring"),
    BotCommand("dsu", "Rapat DSU pagi"),
    BotCommand("scan", "Scan saham intraday"),
    BotCommand("berita", "Radar berita & katalis sektor"),
    BotCommand("cek", "Bedah 1 saham + voting 6 AI"),
    BotCommand("beli", "Catat saham yang sudah dibeli"),
    BotCommand("pegang", "Cek portofolio & sinyal jual"),
    BotCommand("jual", "Hapus saham dari portofolio"),
    BotCommand("sb_saldo", "Cek saldo Stockbit"),
    BotCommand("sb_beli", "Order beli via Stockbit"),
    BotCommand("sb_jual", "Order jual via Stockbit"),
    BotCommand("evaluasi", "Rapor akurasi & self-learning"),
    BotCommand("rapor_ai", "Rapor performa 6 AI"),
    BotCommand("ganti_ai", "Ganti AI yang kurang akurat"),
    BotCommand("tanya", "Tanya AI Architect tentang project"),
    BotCommand("upgrade", "Minta AI upgrade kode project"),
    BotCommand("memori", "Lihat memori historis saham"),
    BotCommand("watchlist", "Kelola daftar saham pantauan"),
]


async def _post_init(app: Application) -> None:
    """Sinkronkan menu command Telegram agar /agy lama tergantikan /tanya."""
    try:
        await app.bot.set_my_commands(BOT_COMMANDS)
    except Exception as e:
        logger.warning("Gagal menyinkronkan menu command Telegram: %s", e)


# Order live hanya dieksekusi setelah pemilik menekan tombol konfirmasi.
_PENDING_SB_ORDERS: dict[str, tuple[float, str, str, int, float]] = {}
_PROCESSED_CALLBACK_IDS: set[str] = set()


def owner_only(func):
    """Semua perintah selain /start wajib berasal dari TELEGRAM_CHAT_ID yang valid."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        if chat is None or not is_authorized_owner(chat.id):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ Akses ditolak. Perintah ini hanya untuk pemilik bot.",
                )
            return None
        return await func(update, context)
    return wrapper


async def _send_safe_markdown(message_or_bot, text: str, chat_id: int | str | None = None, reply_markup=None):
    """Mengirim pesan Telegram dengan fallback plain text jika ada karakter Markdown yang bentrok."""
    kwargs = {"reply_markup": reply_markup} if reply_markup else {}
    try:
        if chat_id is not None:
            await message_or_bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN, **kwargs)
        else:
            await message_or_bot.reply_text(text=text, parse_mode=ParseMode.MARKDOWN, **kwargs)
    except Exception:
        if chat_id is not None:
            await message_or_bot.send_message(chat_id=chat_id, text=text, **kwargs)
        else:
            await message_or_bot.reply_text(text=text, **kwargs)


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Membuat Inline Keyboard interaktif dengan WebApp dan quick action buttons."""
    web_url = f"{config.PUBLIC_BASE_URL}/chart"
    keyboard = [
        [
            InlineKeyboardButton("📈 Buka Chart TradingView", web_app=WebAppInfo(url=web_url)),
            InlineKeyboardButton("🏢 Kantor AI Live", url=f"{config.PUBLIC_BASE_URL}/live"),
        ],
        [
            InlineKeyboardButton("📡 Scan Pasar", callback_data="btn_scan"),
            InlineKeyboardButton("📰 Radar Berita", callback_data="btn_berita"),
        ],
        [
            InlineKeyboardButton("💼 Portofolio", callback_data="btn_pegang"),
            InlineKeyboardButton("☀️ Rapat DSU", callback_data="btn_dsu"),
        ],
        [
            InlineKeyboardButton("📊 Rapor AI", callback_data="btn_rapor"),
            InlineKeyboardButton("🎯 Evaluasi Akurasi", callback_data="btn_evaluasi"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_scan_keyboard(qualified_list) -> InlineKeyboardMarkup | None:
    """Membuat tombol 1-Click Beli Demo dan Buka Chart untuk saham rekomendasi scanner."""
    if not qualified_list:
        return None
    rows = []
    for s in qualified_list[:3]:
        code = s.ticker.replace(".JK", "")
        p = int(round(s.current_price))
        rows.append([
            InlineKeyboardButton(f"🛒 Beli Demo {code} (10 Lot)", callback_data=f"buy_demo_{code}_{p}_10"),
            InlineKeyboardButton(f"📈 Chart {code}", web_app=WebAppInfo(url=f"{config.PUBLIC_BASE_URL}/chart?ticker={code}")),
        ])
    rows.append([InlineKeyboardButton("💼 Cek Portofolio Saya", callback_data="btn_pegang")])
    return InlineKeyboardMarkup(rows)


def get_portfolio_keyboard() -> InlineKeyboardMarkup | None:
    """Membuat tombol aksi cepat jual dan chart untuk saham yang sedang dipegang."""
    portfolio = config.load_portfolio()
    if not portfolio:
        return None
    rows = []
    for norm in portfolio:
        code = norm.replace(".JK", "")
        rows.append([
            InlineKeyboardButton(f"💰 Jual {code}", callback_data=f"sell_demo_{code}"),
            InlineKeyboardButton(f"📈 Chart {code}", web_app=WebAppInfo(url=f"{config.PUBLIC_BASE_URL}/chart?ticker={code}")),
        ])
    rows.append([InlineKeyboardButton("🔄 Refresh Portofolio", callback_data="btn_pegang")])
    return InlineKeyboardMarkup(rows)


def _auto_register_chat_id(chat_id: int | str) -> bool:
    """Opsional saja: default-nya owner harus diisi manual di .env agar chat pertama tidak otomatis jadi owner."""
    str_id = str(chat_id)
    if not config.ALLOW_AUTO_REGISTER_OWNER:
        return False
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
        "• 👨‍💻 *Bastian* — Head of Macro & Sector Intel (Katalis Berita 7 Sektor & Komoditas)\n"
        "• 👩‍💼 *Serena* — VP of Technical Screener (Breakout, VWAP, Volume Spike)\n"
        "• 🛡️ *Damian* — Chief Risk Officer (Area Beli, TP1/TP2, Rem Darurat Cut Loss)\n"
        "• 🎯 *Chief Arthur* — Supreme Decider & Pemimpin Sidang Konsensus 6 AI\n\n"
        "⌨️ *Perintah yang Tersedia:*\n"
        "• `/dashboard` — Link website monitoring & rekap harga saham (bisa dibuka di browser HP)\n"
        "• `/dsu` — Panggil rapat DSU pagi sekarang juga\n"
        "• `/scan` — Cari saham yang bagus dibeli *jam segini*\n"
        "• `/berita` — Radar perbandingan berita 7 sektor & peluang Masa Depan (Swing)\n"
        "• `/cek <KODE>` — Bedah 1 saham + Voting 6 AI (contoh: `/cek BBCA`)\n"
        "• `/beli <KODE> <HARGA>` — Lapor kalau Bos sudah beli biar diingatkan kapan jual!\n"
        "• `/pegang` — Cek saham yang sedang Bos pegang: sudah waktunya jual atau belum\n"
        "• `/jual <KODE>` — Hapus saham dari pantauan jual kalau sudah laku\n"
        "• `/evaluasi` — Lihat rapor akurasi, Win Rate, Expectancy, & Self-Learning AI\n"
        "• `/rapor_ai` — Rapor Mingguan 6 AI (Siapa paling jago vs Siapa harus diganti)\n"
        "• `/ganti_ai` — Ganti AI yang kurang akurat dengan model AI gratis lain\n"
        "• `/tanya <pertanyaan>` — Tanya AI Architect tentang kode/project ini\n"
        "• `/upgrade <instruksi>` — Perintahkan AI meng-upgrade kode project & push ke GitHub\n"
        "• `/memori <KODE>` — Lihat ingatan & pelajaran historis AI pada saham tertentu\n"
        "• `/watchlist` — Lihat / tambah / hapus daftar saham pantauan\n"
        "• `/help` atau `/menu` — Tampilkan daftar perintah ini kapan saja\n\n"
        "💬 _Atau langsung ketik pertanyaan biasa tanpa garis miring `/`, nanti Tim AI langsung menjawab!_"
    )
    await _send_safe_markdown(update.message, welcome, reply_markup=get_main_menu_keyboard())


@owner_only
async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengirim link dashboard monitoring web ke Bos."""
    msg = (
        "📊 *DASHBOARD MONITORING HARGA SAHAM*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Bos bisa memantau rekap harga, target TP/SL, dan sinyal 6 AI secara real-time lewat browser di link berikut:\n\n"
        "🌐 *Link Dashboard:*\n"
        f"{config.PUBLIC_BASE_URL}/\n\n"
        "📈 *TradingView Chart WebApp:*\n"
        f"{config.PUBLIC_BASE_URL}/chart\n\n"
        "✨ _Tampilan ramah HP, auto-refresh tiap 60 detik, dan bisa dibuka dari mana saja!_"
    )
    await _send_safe_markdown(update.message, msg, reply_markup=get_main_menu_keyboard())


@owner_only
async def cmd_dsu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_msg = await update.message.reply_text(
        "⏳ *Memanggil Bastian, Serena, Damian, dan Chief Arthur untuk rapat DSU...*\n_Sedang mengambil data market & berita terbaru..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    report = await asyncio.to_thread(generate_morning_dsu_report)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, report)


@owner_only
async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_msg = await update.message.reply_text(
        "📡 *Memindai pergerakan harga & lonjakan volume intraday di watchlist...*",
        parse_mode=ParseMode.MARKDOWN,
    )
    qualified, report = await asyncio.to_thread(generate_intraday_scanner_alert, 0)
    await wait_msg.delete()
    reply_markup = get_scan_keyboard(qualified)
    await _send_safe_markdown(update.message, report, reply_markup=reply_markup)


@owner_only
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

    clean_code = ticker.upper().replace(".JK", "")
    snap = await asyncio.to_thread(analyze_ticker_quant, config.normalize_ticker(clean_code))
    price_val = int(round(snap.current_price)) if snap and snap.current_price > 0 else 5000
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🛒 Beli Demo {clean_code} (10 Lot)", callback_data=f"buy_demo_{clean_code}_{price_val}_10"),
            InlineKeyboardButton(f"📈 Buka Chart {clean_code}", web_app=WebAppInfo(url=f"{config.PUBLIC_BASE_URL}/chart?ticker={clean_code}")),
        ],
        [
            InlineKeyboardButton("💼 Cek Portofolio Saya", callback_data="btn_pegang"),
        ]
    ])
    await _send_safe_markdown(update.message, report, reply_markup=keyboard)


@owner_only
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


@owner_only
async def cmd_beli(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mencatat saham yang baru dibeli Bos supaya dipantau jam jualnya oleh Hendra & Arif."""
    _auto_register_chat_id(update.effective_chat.id)
    if len(context.args) < 2:
        await update.message.reply_text(
            "🛒 *Cara Lapor Beli Saham:*\n"
            "Ketik: `/beli <KODE> <HARGA_BELI> [LOT]`\n"
            "Contoh: `/beli BBCA 5250 10`\n\n"
            "_Kalau LOT tidak diisi, default 1 lot. Nanti Damian & Chief Arthur akan otomatis menjaga saham ini._",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker_raw = context.args[0]
    price_raw = context.args[1].replace(".", "").replace(",", "")
    try:
        buy_price = float(price_raw)
        lots = int(context.args[2]) if len(context.args) > 2 else 1
    except ValueError:
        await update.message.reply_text("⚠️ Format: `/beli BBCA 5250 10` (harga dan lot harus angka).", parse_mode=ParseMode.MARKDOWN)
        return
    if lots <= 0:
        await update.message.reply_text("⚠️ Jumlah lot harus lebih dari 0.", parse_mode=ParseMode.MARKDOWN)
        return

    norm = config.normalize_ticker(ticker_raw)
    snap = await asyncio.to_thread(analyze_ticker_quant, norm)
    tp1 = snap.take_profit_1 if snap and snap.take_profit_1 > buy_price else round(buy_price * 1.04)
    tp2 = snap.take_profit_2 if snap and snap.take_profit_2 > tp1 else round(buy_price * 1.08)
    sl = snap.stop_loss if snap and snap.stop_loss < buy_price else round(buy_price * 0.96)

    try:
        config.apply_trade("BUY", norm, lots, buy_price, plan={"tp1": tp1, "tp2": tp2, "sl": sl}, note="lapor beli")
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}", parse_mode=ParseMode.MARKDOWN)
        return

    code = norm.replace(".JK", "")
    msg = (
        f"✅ *Siap Bos! Saham {code} {lots} lot di harga Rp {buy_price:,.0f} sudah dicatat Damian & Chief Arthur!*\n\n"
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


@owner_only
async def cmd_pegang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    wait_msg = await update.message.reply_text("💼 _Mengecek harga terbaru saham yang sedang Bos pegang..._", parse_mode=ParseMode.MARKDOWN)
    report = await asyncio.to_thread(evaluate_portfolio_sell_signals, True)
    await wait_msg.delete()
    reply_markup = get_portfolio_keyboard()
    await _send_safe_markdown(update.message, report, reply_markup=reply_markup)


@owner_only
async def cmd_jual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Ketik `/jual <KODE> [LOT] [HARGA]` jika sahamnya sudah Bos jual.\n"
            "Contoh: `/jual BBCA 10 5450`. Tanpa LOT = jual semua; tanpa HARGA = harga pasar sekarang.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    norm = config.normalize_ticker(context.args[0])
    portfolio = config.load_portfolio()
    if norm not in portfolio:
        await update.message.reply_text(f"ℹ️ Saham *{norm.replace('.JK', '')}* belum ada di catatan `/pegang`.", parse_mode=ParseMode.MARKDOWN)
        return
    held = int(portfolio[norm].get("lots", 1))
    try:
        lots = int(context.args[1]) if len(context.args) > 1 else held
        if len(context.args) > 2:
            sell_price = float(context.args[2].replace(".", "").replace(",", ""))
        else:
            snap = await asyncio.to_thread(analyze_ticker_quant, norm)
            sell_price = float(snap.current_price) if snap and snap.current_price > 0 else float(portfolio[norm].get("buy_price", 0))
    except ValueError:
        await update.message.reply_text("⚠️ Format: `/jual BBCA 10 5450` (lot dan harga harus angka).", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        result = config.apply_trade("SELL", norm, lots, sell_price, note="jual manual")
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}", parse_mode=ParseMode.MARKDOWN)
        return
    realized = result["ledger"]["trades"][-1].get("realized_pnl", 0.0)
    text = (
        f"🎉 *Saham {norm.replace('.JK', '')} terjual {result['lots']} lot @ Rp {sell_price:,.0f}*\n"
        f"• Realized P&L: *Rp {realized:,.0f}*\n"
        f"• Sisa posisi: *{config.load_portfolio().get(norm, {}).get('lots', 0)} lot*"
    ).replace(",", ".")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@owner_only
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


async def _execute_sb_order(side: str, ticker_raw: str, lots: int, price: float, reply_msg):
    """Eksekusi order terverifikasi + catat ledger; dipakai command dan tombol konfirmasi."""
    wait_msg = await reply_msg.reply_text(
        f"🤖 *Robot sedang masuk ke Stockbit untuk {side} {ticker_raw.upper()} ({lots} Lot @ Rp {price:,.0f})...*",
        parse_mode=ParseMode.MARKDOWN,
    )
    ok, caption, img_path = await execute_stockbit_order(side, ticker_raw, lots, price)
    await wait_msg.delete()

    if ok:
        norm = config.normalize_ticker(ticker_raw)
        try:
            if side == "BUY":
                snap = await asyncio.to_thread(analyze_ticker_quant, norm)
                tp1 = snap.take_profit_1 if snap and snap.take_profit_1 > price else round(price * 1.04)
                tp2 = snap.take_profit_2 if snap and snap.take_profit_2 > tp1 else round(price * 1.08)
                sl = snap.stop_loss if snap and snap.stop_loss < price else round(price * 0.96)
                config.apply_trade("BUY", norm, lots, price, plan={"tp1": tp1, "tp2": tp2, "sl": sl}, note="stockbit verified")
            else:
                config.apply_trade("SELL", norm, lots, price, note="stockbit verified")
        except ValueError as e:
            caption += f"\n\n⚠️ Order terkirim, tapi portfolio gagal diperbarui: {e}"

    if ok and img_path and img_path.exists():
        with open(img_path, "rb") as photo_file:
            await reply_msg.reply_photo(photo=photo_file, caption=caption, parse_mode=ParseMode.MARKDOWN)
    else:
        await _send_safe_markdown(reply_msg, caption)


async def _request_sb_confirmation(message, side: str, ticker_raw: str, lots: int, price: float):
    token = uuid.uuid4().hex[:12]
    now = time.time()
    for old_token, item in list(_PENDING_SB_ORDERS.items()):
        if now - item[0] > 600:
            _PENDING_SB_ORDERS.pop(old_token, None)
    _PENDING_SB_ORDERS[token] = (now, side, ticker_raw, lots, price)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Konfirmasi", callback_data=f"sb_confirm_{token}"),
        InlineKeyboardButton("❌ Batal", callback_data=f"sb_cancel_{token}"),
    ]])
    await message.reply_text(
        f"🛡️ *KONFIRMASI ORDER {side}*\n"
        f"• Saham: `{ticker_raw.upper()}`\n• Lot: `{lots}`\n• Harga: `Rp {price:,.0f}`\n\n"
        "Tekan ✅ dalam 10 menit. Tanpa konfirmasi, order tidak dikirim ke Stockbit.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


@owner_only
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

    if config.STOCKBIT_REQUIRE_CONFIRMATION:
        await _request_sb_confirmation(update.message, "BUY", ticker_raw, lots, price)
        return
    await _execute_sb_order("BUY", ticker_raw, lots, price, update.message)


@owner_only
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

    if config.STOCKBIT_REQUIRE_CONFIRMATION:
        await _request_sb_confirmation(update.message, "SELL", ticker_raw, lots, price)
        return
    await _execute_sb_order("SELL", ticker_raw, lots, price, update.message)


@owner_only
async def cmd_evaluasi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    mode = context.args[0].upper() if context.args else None
    wait_msg = await update.message.reply_text("📊 _Mengevaluasi hasil prediksi historis & menghitung metrik performa strategi..._", parse_mode=ParseMode.MARKDOWN)
    report = await asyncio.to_thread(get_performance_dashboard_report, mode)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, report)


@owner_only
async def cmd_memori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    ticker = context.args[0] if context.args else "TLKM"
    report = await asyncio.to_thread(get_ticker_memory_report, ticker)
    await _send_safe_markdown(update.message, report)


@owner_only
async def cmd_rapor_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    wait_msg = await update.message.reply_text(
        "🏆 _Menghitung akurasi masing-masing dari 6 AI & menyusun Rapor Mingguan..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    report = await asyncio.to_thread(get_weekly_ai_report)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, report)


@owner_only
async def cmd_ganti_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    args = list(context.args) if context.args else []
    report = await asyncio.to_thread(swap_panel_ai_model, args)
    await _send_safe_markdown(update.message, report)


@owner_only
async def cmd_tanya(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    _auto_register_chat_id(chat_id)
    query = " ".join(context.args) if context.args else ""
    wait_msg = await update.message.reply_text(
        "🤖 _AI Architect sedang memeriksa kode project Anda..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    reply = await asyncio.to_thread(ask_project_architect, query, chat_id)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, reply)


@owner_only
async def cmd_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    _auto_register_chat_id(chat_id)
    instruction = " ".join(context.args) if context.args else ""
    wait_msg = await update.message.reply_text(
        "🛠️ _AI Architect sedang menyusun upgrade kode, menguji sintaks, & sinkronisasi ke GitHub..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    reply = await asyncio.to_thread(upgrade_project_code, instruction, chat_id)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, reply)


@owner_only
async def cmd_berita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _auto_register_chat_id(update.effective_chat.id)
    wait_msg = await update.message.reply_text(
        "🌍 _Membandingkan puluhan artikel berita dari 7 Sektor Utama BEI (Rokok/Cukai, Bank, Energi, Tambang, Konsumer, Properti, Telko)..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    report = await asyncio.to_thread(generate_sectoral_news_catalyst_report)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, report)


@owner_only
async def handle_free_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_text = update.message.text.strip()
    wait_msg = await update.message.reply_text("💬 _Tim AI sedang menyiapkan jawaban..._", parse_mode=ParseMode.MARKDOWN)
    reply = await asyncio.to_thread(chat_with_ai_team, user_text)
    await wait_msg.delete()
    await _send_safe_markdown(update.message, reply)


@owner_only
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani klik tombol interaktif pada Inline Keyboard Telegram."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("sb_confirm_") or data.startswith("sb_cancel_"):
        if query.id in _PROCESSED_CALLBACK_IDS:
            return
        _PROCESSED_CALLBACK_IDS.add(query.id)
        if len(_PROCESSED_CALLBACK_IDS) > 500:
            _PROCESSED_CALLBACK_IDS.clear()
        token = data.split("_", 2)[2]
        item = _PENDING_SB_ORDERS.pop(token, None)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        if item is None or time.time() - item[0] > 600:
            await query.message.reply_text("⌛ Konfirmasi order sudah kedaluwarsa. Silakan ulangi perintah.")
            return
        _, side, ticker_raw, lots, price = item
        if data.startswith("sb_cancel_"):
            await query.message.reply_text("❌ Order dibatalkan. Tidak ada yang dikirim ke Stockbit.")
            return
        await _execute_sb_order(side, ticker_raw, lots, price, query.message)
        return

    if data == "btn_scan":
        wait_msg = await query.message.reply_text("📡 *Memindai pergerakan harga & lonjakan volume intraday di watchlist...*", parse_mode=ParseMode.MARKDOWN)
        qualified, report = await asyncio.to_thread(generate_intraday_scanner_alert, 0)
        await wait_msg.delete()
        reply_markup = get_scan_keyboard(qualified)
        await _send_safe_markdown(query.message, report, reply_markup=reply_markup)
    elif data == "btn_berita":
        wait_msg = await query.message.reply_text("📰 *Bastian sedang mengompilasi intelijen 7 sektor & pergerakan komoditas dunia...*", parse_mode=ParseMode.MARKDOWN)
        report = await asyncio.to_thread(generate_sectoral_news_catalyst_report)
        await wait_msg.delete()
        await _send_safe_markdown(query.message, report)
    elif data == "btn_pegang":
        report = await asyncio.to_thread(evaluate_portfolio_sell_signals, True)
        reply_markup = get_portfolio_keyboard()
        await _send_safe_markdown(query.message, report, reply_markup=reply_markup)
    elif data == "btn_dsu":
        wait_msg = await query.message.reply_text("⏳ *Memanggil Bastian, Serena, Damian, dan Chief Arthur untuk rapat DSU...*", parse_mode=ParseMode.MARKDOWN)
        report = await asyncio.to_thread(generate_morning_dsu_report)
        await wait_msg.delete()
        await _send_safe_markdown(query.message, report)
    elif data == "btn_rapor":
        report = await asyncio.to_thread(get_weekly_ai_report)
        await _send_safe_markdown(query.message, report)
    elif data == "btn_evaluasi":
        report = await asyncio.to_thread(get_performance_dashboard_report)
        await _send_safe_markdown(query.message, report)
    elif data.startswith("buy_demo_"):
        parts = data.split("_")
        ticker_code = parts[2]
        norm = config.normalize_ticker(ticker_code)
        snap = await asyncio.to_thread(analyze_ticker_quant, norm)

        price = float(parts[3]) if len(parts) > 3 and parts[3].isdigit() else (snap.current_price if snap and snap.current_price > 0 else 5000.0)
        lots = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 10

        tp1 = snap.take_profit_1 if snap and snap.take_profit_1 > price else round(price * 1.04)
        tp2 = snap.take_profit_2 if snap and snap.take_profit_2 > tp1 else round(price * 1.08)
        sl = snap.stop_loss if snap and snap.stop_loss < price else round(price * 0.96)

        try:
            config.apply_trade("BUY", norm, lots, price, plan={"tp1": tp1, "tp2": tp2, "sl": sl}, note="demo telegram")
        except ValueError as e:
            await query.message.reply_text(f"⚠️ {e}")
            return

        total_modal = price * lots * 100
        code = norm.replace(".JK", "")
        tp1_pct = ((tp1 - price) / price) * 100 if price > 0 else 0
        tp2_pct = ((tp2 - price) / price) * 100 if price > 0 else 0
        sl_pct = ((sl - price) / price) * 100 if price > 0 else 0

        msg = (
            f"🛒 *BERHASIL BELI DEMO OTOMATIS!* 🎉\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• 🏢 *Saham:* `{code}`\n"
            f"• 📦 *Volume:* `{lots}` Lot ({(lots * 100):,} lembar)\n"
            f"• 💵 *Harga Beli:* `Rp {price:,.0f}`\n"
            f"• 💰 *Total Modal Virtual:* `Rp {total_modal:,.0f}`\n\n"
            f"🎯 *Rencana Pengawalan Otomatis AI:*\n"
            f"• 💰 *Target Aman 1 (TP1):* Rp {tp1:,.0f} (+{tp1_pct:.1f}%) ➡️ Jual 5 Lot\n"
            f"• 🚀 *Target Panen 2 (TP2):* Rp {tp2:,.0f} (+{tp2_pct:.1f}%) ➡️ Jual 5 Lot\n"
            f"• 🛑 *Rem Darurat (SL):* < Rp {sl:,.0f} ({sl_pct:.1f}%)\n\n"
            f"🛡️ _Damian & Chief Arthur sedang mengawal ketat saham ini. Bos akan otomatis menerima alarm notifikasi di Telegram saat harganya menyentuh TP1, TP2, atau batas rem SL!_"
        ).replace(",", ".")

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💼 Cek Portofolio Saya", callback_data="btn_pegang"),
                InlineKeyboardButton(f"📈 Buka Chart {code}", web_app=WebAppInfo(url=f"{config.PUBLIC_BASE_URL}/chart?ticker={code}")),
            ]
        ])
        await _send_safe_markdown(query.message, msg, reply_markup=keyboard)
    elif data.startswith("sell_demo_"):
        ticker_code = data.split("_")[2]
        norm = config.normalize_ticker(ticker_code)
        portfolio = config.load_portfolio()
        if norm in portfolio:
            item = portfolio[norm]
            buy_p = item.get("buy_price", 0)
            snap = await asyncio.to_thread(analyze_ticker_quant, norm)
            curr_p = snap.current_price if snap and snap.current_price > 0 else buy_p
            try:
                config.apply_trade("SELL", norm, int(item.get("lots", 1)), curr_p, note="demo telegram")
            except ValueError as e:
                await query.message.reply_text(f"⚠️ {e}")
                return
            gain_pct = ((curr_p - buy_p) / buy_p * 100) if buy_p > 0 else 0
            emoji = "🎉 CUAN" if gain_pct >= 0 else "🛑 CUT LOSS"
            msg = (
                f"{emoji}! Saham *{norm.replace('.JK', '')}* berhasil dijual!\n"
                f"• Modal Beli: Rp {buy_p:,.0f}\n"
                f"• Harga Jual: Rp {curr_p:,.0f} ({gain_pct:+.2f}%)\n\n"
                f"Saham telah dikeluarkan dari daftar pantauan portofolio."
            ).replace(",", ".")
            reply_markup = get_portfolio_keyboard()
            await _send_safe_markdown(query.message, msg, reply_markup=reply_markup)
        else:
            await query.message.reply_text(f"Saham {ticker_code} sudah tidak ada di portofolio.", parse_mode=ParseMode.MARKDOWN)


# =====================================================================
# JADWAL OTOMATIS HARIAN (SENIN - JUMAT WIB)
# =====================================================================

async def scheduled_morning_dsu(context: ContextTypes.DEFAULT_TYPE):
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        logger.warning("TELEGRAM_CHAT_ID belum diatur. Lewati pengiriman DSU pagi.")
        return
    if not config.is_idx_trading_day():
        logger.info("Hari ini bursa libur. Lewati DSU pagi.")
        return
    logger.info("Menjalankan DSU Pagi otomatis...")
    report = await asyncio.to_thread(generate_morning_dsu_report)
    await _send_safe_markdown(context.bot, report, chat_id=chat_id)


async def scheduled_intraday_scan(context: ContextTypes.DEFAULT_TYPE):
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        return
    if not config.is_idx_trading_day():
        logger.info("Hari ini bursa libur. Lewati scanner intraday.")
        return
    logger.info("Menjalankan Scanner Intraday otomatis...")
    qualified, report = await asyncio.to_thread(generate_intraday_scanner_alert, config.MIN_INTRADAY_ALERT_SCORE)
    sell_alert = await asyncio.to_thread(evaluate_portfolio_sell_signals, False)
    if qualified:
        reply_markup = get_scan_keyboard(qualified)
        await _send_safe_markdown(context.bot, report, chat_id=chat_id, reply_markup=reply_markup)
    elif sell_alert:
        reply_markup = get_portfolio_keyboard()
        await _send_safe_markdown(context.bot, sell_alert, chat_id=chat_id, reply_markup=reply_markup)
    else:
        logger.info("Tidak ada sinyal beli baru maupun sinyal jual darurat pada jam ini.")


async def scheduled_market_close(context: ContextTypes.DEFAULT_TYPE):
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        return
    if not config.is_idx_trading_day():
        logger.info("Hari ini bursa libur. Lewati evaluasi penutupan.")
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
    """Mengirim Rapor Mingguan 6 AI setiap hari Jumat sore (16:20 WIB)."""
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        return
    logger.info("Mengirim Rapor Mingguan 6 AI otomatis...")
    report = await asyncio.to_thread(get_weekly_ai_report)
    await _send_safe_markdown(context.bot, report, chat_id=chat_id)


async def scheduled_sector_news_radar(context: ContextTypes.DEFAULT_TYPE):
    """Memantau & membandingkan puluhan artikel berita lintas sektor setiap beberapa jam sekali."""
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        return
    logger.info("Menjalankan Radar Berita Lintas Sektor & Peluang Masa Depan otomatis...")
    report = await asyncio.to_thread(generate_sectoral_news_catalyst_report)
    await _send_safe_markdown(context.bot, report, chat_id=chat_id)


async def scheduled_weekend_news_radar(context: ContextTypes.DEFAULT_TYPE):
    """Memindai berita 7 sektor & pergerakan komoditas dunia pada Sabtu dan Minggu pagi untuk persiapan hari Senin."""
    chat_id = config.TELEGRAM_CHAT_ID
    if not chat_id or chat_id.startswith("masukkan_"):
        return
    logger.info("Menjalankan Radar Berita Akhir Pekan (Sabtu/Minggu)...")
    report = await asyncio.to_thread(generate_sectoral_news_catalyst_report)
    header = "☕ *RADAR BERITA AKHIR PEKAN (INTELIJEN HARI SENIN)* 📰\n_Bursa memang libur, tapi arus berita & katalis emiten tidak pernah tidur!_\n\n"
    await _send_safe_markdown(context.bot, header + report, chat_id=chat_id)


def start_telegram_bot():
    token = config.TELEGRAM_BOT_TOKEN
    if not token or token.startswith("masukkan_"):
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN belum diisi di file .env! Silakan isi terlebih dahulu atau jalankan `cli_demo.py` untuk uji coba di terminal."
        )

    app = Application.builder().token(token).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_start))
    app.add_handler(CommandHandler("bantuan", cmd_start))
    app.add_handler(CommandHandler("dashboard", cmd_dashboard))
    app.add_handler(CommandHandler("web", cmd_dashboard))
    app.add_handler(CommandHandler("dsu", cmd_dsu))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("berita", cmd_berita))
    app.add_handler(CommandHandler("sektor", cmd_berita))
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
    app.add_handler(CommandHandler("tanya", cmd_tanya))
    app.add_handler(CommandHandler("upgrade", cmd_upgrade))
    app.add_handler(CommandHandler("memori", cmd_memori))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
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

        # 5. Rapor Mingguan 6 AI setiap hari Jumat sore (16:20 WIB)
        job_queue.run_daily(
            scheduled_weekly_ai_report,
            time=dt.time(hour=16, minute=20, tzinfo=wib),
            days=(5,),
            name="weekly_ai_report_friday",
        )

        # 6. Radar Berita Lintas 7 Sektor & Peluang Masa Depan (11:30 WIB Siang & 14:15 WIB Sesi 2)
        for nh, nm in [(11, 30), (14, 15)]:
            job_queue.run_daily(
                scheduled_sector_news_radar,
                time=dt.time(hour=nh, minute=nm, tzinfo=wib),
                days=(1, 2, 3, 4, 5),
                name=f"sector_news_radar_{nh:02d}_{nm:02d}",
            )

        # 7. Radar Berita Akhir Pekan (Sabtu & Minggu Pagi jam 09:30 WIB)
        # Catatan: PTB JobQueue menggunakan index 0=Minggu (Sun), 1=Senin, ..., 6=Sabtu (Sat)
        job_queue.run_daily(
            scheduled_weekend_news_radar,
            time=dt.time(hour=9, minute=30, tzinfo=wib),
            days=(0, 6),
            name="weekend_news_radar_0930",
        )

    logger.info("🤖 Karyawan AI Saham siap bekerja! Menunggu perintah di Telegram & menjalankan jadwal harian...")
    app.run_polling(drop_pending_updates=False)
