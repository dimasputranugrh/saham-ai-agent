import asyncio
from pathlib import Path
from typing import Tuple, Optional

import config
from analyzer.technical import round_idx_tick


def is_session_ready() -> bool:
    """Mengecek apakah folder sesi login Stockbit sudah pernah dibuat."""
    return config.STOCKBIT_PROFILE_DIR.exists() and any(config.STOCKBIT_PROFILE_DIR.iterdir())


async def _unlock_pin_if_needed(page, pin: str):
    """Membuka gembok Trading PIN Stockbit jika halaman meminta input 6 angka PIN."""
    if not pin or pin.startswith("masukkan_") or len(pin) < 4:
        return
    try:
        # Cek apakah ada teks perintah masukkan PIN atau kotak password PIN
        pin_inputs = await page.query_selector_all('input[type="password"], input[inputmode="numeric"]')
        if pin_inputs:
            await pin_inputs[0].click()
            await page.keyboard.type(pin, delay=80)
            await asyncio.sleep(1.2)
    except Exception:
        pass


async def _verify_order_submission(page) -> tuple[bool, str]:
    """Cek indikator konfirmasi di DOM. Kalau tidak yakin, jangan anggap order sukses."""
    try:
        body = (await page.content()).lower()
    except Exception:
        return False, "halaman tidak bisa dibaca"
    success_markers = (
        "order berhasil",
        "pesanan berhasil",
        "order submitted",
        "order placed",
        "open order",
        "antrian order",
        "success",
    )
    if any(marker in body for marker in success_markers):
        return True, "indikator sukses ditemukan"
    return False, "indikator sukses tidak ditemukan"


async def capture_stockbit_portfolio() -> Tuple[bool, str, Optional[Path]]:
    """
    Membuka halaman Portofolio Stockbit secara tersembunyi (Headless),
    memasukkan PIN Trading jika diminta, lalu memotret layar (Screenshot) untuk dikirim ke Telegram Bos.
    """
    if not is_session_ready():
        return (
            False,
            "⚠️ *Sesi Login Stockbit belum ada!*\nSilakan jalankan perintah login 1 kali di terminal komputer Anda:\n`cd /home/dimas/projects/saham-ai-agent && .venv/bin/python login_stockbit.py`",
            None,
        )

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return (
            False,
            "⚠️ Modul Playwright sedang diinstal. Mohon tunggu sebentar lalu coba lagi.",
            None,
        )

    screenshot_path = config.BASE_DIR / "data" / "stockbit_portfolio.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(config.STOCKBIT_PROFILE_DIR),
                headless=True,
                viewport={"width": 1366, "height": 860},
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://stockbit.com/securities/portfolio", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3.0)

            if "login" in page.url.lower():
                await context.close()
                return (
                    False,
                    "⚠️ *Sesi Stockbit Anda sudah kadaluarsa / belum login.*\nSilakan login ulang lewat `python login_stockbit.py`.",
                    None,
                )

            await _unlock_pin_if_needed(page, config.STOCKBIT_TRADING_PIN)
            await asyncio.sleep(2.0)
            await page.screenshot(path=str(screenshot_path), full_page=False)
            await context.close()
            return True, "📸 *Berikut tampilan Portofolio & Saldo RDN Stockbit Anda saat ini, Bos:*", screenshot_path
    except Exception as e:
        return False, f"⚠️ Gagal membuka Stockbit: `{e}`", None


async def execute_stockbit_order(
    side: str, ticker: str, lots: int, price: float
) -> Tuple[bool, str, Optional[Path]]:
    """
    Mengeksekusi order BELI (BUY) atau JUAL (SELL) di Stockbit Web secara otomatis di belakang layar,
    lalu mengirimkan foto screenshot bukti order ke Telegram Bos.
    """
    side = side.upper()
    code = ticker.upper().replace(".JK", "").strip()
    clean_price = int(round_idx_tick(price, is_idx=True))

    if lots <= 0:
        return False, "⚠️ Jumlah Lot minimal adalah 1 Lot.", None
    if not config.ALLOW_LIVE_BROKER_EXECUTION or config.EXECUTION_MODE != "LIVE":
        return (
            False,
            "🛡️ *Mode Keamanan PAPER TRADING Aktif (Default Safety Phase 8):*\n"
            f"Pengiriman order sungguhan ke broker (`{side} {code} {lots} Lot @ Rp {clean_price:,.0f}`) diblokir secara otomatis "
            "karena `EXECUTION_MODE=PAPER` / `ALLOW_LIVE_BROKER_EXECUTION=false`.\n"
            "Gunakan perintah `/beli` untuk simulasi Paper Trading, atau aktifkan otorisasi eksplisit di `.env` jika ingin Live Trading.",
            None,
        )
    if lots > config.STOCKBIT_MAX_LOT:
        return (
            False,
            f"🛑 *Sabuk Pengaman Aktif:* Jumlah beli/jual ({lots} Lot) melebihi batas aman `STOCKBIT_MAX_LOT={config.STOCKBIT_MAX_LOT}` di `.env`!",
            None,
        )

    if not is_session_ready():
        return (
            False,
            "⚠️ *Sesi Login Stockbit belum aktif!*\nJalankan dulu 1 kali di terminal:\n`cd /home/dimas/projects/saham-ai-agent && .venv/bin/python login_stockbit.py`",
            None,
        )

    pin = config.STOCKBIT_TRADING_PIN
    if not pin or pin.startswith("masukkan_"):
        return (
            False,
            "⚠️ *PIN Trading Stockbit belum diisi!*\nSilakan isi `STOCKBIT_TRADING_PIN=123456` di file `/home/dimas/projects/saham-ai-agent/.env` terlebih dahulu.",
            None,
        )

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False, "⚠️ Modul Playwright belum selesai terinstal.", None

    screenshot_path = config.BASE_DIR / "data" / f"order_{side.lower()}_{code}.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(config.STOCKBIT_PROFILE_DIR),
                headless=True,
                viewport={"width": 1400, "height": 900},
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(f"https://stockbit.com/symbol/{code}", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3.5)

            if "login" in page.url.lower():
                await context.close()
                return False, "⚠️ Sesi Stockbit belum login. Silakan jalankan `python login_stockbit.py`.", None

            # Klik tombol Buy / Sell pada panel Orderbook Stockbit
            target_btn_text = "Buy" if side == "BUY" else "Sell"
            clicked_tab = False
            for selector in [
                f'button:has-text("{target_btn_text}")',
                f'div[role="tab"]:has-text("{target_btn_text}")',
                f'span:has-text("{target_btn_text}")',
            ]:
                el = await page.query_selector(selector)
                if el:
                    await el.click()
                    clicked_tab = True
                    await asyncio.sleep(1.5)
                    break

            # Buka PIN jika diminta setelah klik Buy/Sell
            await _unlock_pin_if_needed(page, pin)
            await asyncio.sleep(1.5)

            # Isi Harga (Price) & Jumlah Lot (Lot) jika form input ditemukan
            inputs = await page.query_selector_all('input[type="text"], input[type="number"]')
            for inp in inputs:
                placeholder = (await inp.get_attribute("placeholder") or "").lower()
                name_attr = (await inp.get_attribute("name") or "").lower()
                if "price" in placeholder or "harga" in placeholder or "price" in name_attr:
                    await inp.click(click_count=3)
                    await inp.fill(str(clean_price))
                elif "lot" in placeholder or "lot" in name_attr:
                    await inp.click(click_count=3)
                    await inp.fill(str(lots))

            await asyncio.sleep(1.0)
            # Klik tombol Submit Order (Buy / Sell) dan Confirm jika muncul modal konfirmasi
            submit_btns = await page.query_selector_all(f'button:has-text("{target_btn_text}")')
            if len(submit_btns) < 2:
                await page.screenshot(path=str(screenshot_path), full_page=False)
                await context.close()
                return False, "⚠️ Tombol submit order tidak ditemukan. Order TIDAK dikirim.", screenshot_path

            await submit_btns[-1].click()
            await asyncio.sleep(1.2)
            confirm_btn = await page.query_selector('button:has-text("Confirm"), button:has-text("Konfirmasi"), button:has-text("Proceed")')
            if confirm_btn:
                await confirm_btn.click()
                await asyncio.sleep(1.5)

            verified, verify_note = await _verify_order_submission(page)
            await page.screenshot(path=str(screenshot_path), full_page=False)
            await context.close()

            if config.STOCKBIT_VERIFY_ORDER and not verified:
                return (
                    False,
                    f"⚠️ Order {side} {code} mungkin sudah diklik, tapi status fill belum terverifikasi ({verify_note}).\n"
                    "Portfolio TIDAK dicatat otomatis. Cek screenshot & aplikasi Stockbit sebelum mengulang order.",
                    screenshot_path,
                )

            est_total = clean_price * lots * 100
            aksi_kata = "BELI" if side == "BUY" else "JUAL"
            caption = (
                f"✅ *EKSEKUSI STOCKBIT: {aksi_kata} {code}*\n"
                f"• 📦 *Jumlah:* {lots} Lot ({lots * 100} lembar)\n"
                f"• 💵 *Harga Order:* Rp {clean_price:,.0f}\n"
                f"• 💰 *Total Nilai:* Rp {est_total:,.0f}\n"
                f"• 🔎 *Verifikasi:* {verify_note}\n\n"
                f"📸 _Berikut tangkapan layar langsung dari akun Stockbit Anda:_"
            ).replace(",", ".")
            return True, caption, screenshot_path
    except Exception as e:
        return False, f"⚠️ Terjadi kendala saat eksekusi di Stockbit: `{e}`", None
