import asyncio
from rich.console import Console
from rich.panel import Panel
import config

console = Console()


async def main():
    console.print(
        Panel(
            "[bold cyan]🔐 LOGIN 1-KALI STOCKBIT SEKURITAS[/bold cyan]\n\n"
            "Sebentar lagi jendela browser [bold]stockbit.com/login[/bold] akan terbuka.\n"
            "1. Silakan login ke akun Stockbit Anda seperti biasa (bisa pakai Google atau Email/Username + OTP).\n"
            "2. Setelah berhasil masuk ke halaman utama Stockbit, [bold green]tutup saja jendela browsernya[/bold green] (atau tekan Ctrl+C di sini).\n"
            "3. Sesi login Anda akan otomatis tersimpan di folder rahasia [bold]data/stockbit_profile[/bold]!",
            title="🤖 Koneksi Robot Stockbit",
        )
    )
    from playwright.async_api import async_playwright

    config.STOCKBIT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(config.STOCKBIT_PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 840},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://stockbit.com/login")
        console.print("[bold yellow]⏳ Silakan login di jendela browser yang terbuka... (Menunggu sampai jendela ditutup)[/bold yellow]")
        try:
            await page.wait_for_event("close", timeout=600000)
        except Exception:
            pass
        await context.close()
    console.print("[bold green]✅ Sesi Stockbit berhasil disimpan! Sekarang Anda bisa beli/jual langsung dari Telegram![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
