import json
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

TIMEZONE = "Asia/Jakarta"
DSU_MORNING_TIME = os.getenv("DSU_MORNING_TIME", "08:15").strip()
MARKET_CLOSE_TIME = os.getenv("MARKET_CLOSE_TIME", "16:15").strip()
MIN_INTRADAY_ALERT_SCORE = int(os.getenv("MIN_INTRADAY_ALERT_SCORE", "68"))

WATCHLIST_FILE = BASE_DIR / "data" / "watchlist.json"
PORTFOLIO_FILE = BASE_DIR / "data" / "portfolio.json"


def load_portfolio() -> dict[str, dict]:
    """Memuat daftar saham yang sedang dipegang/dibeli oleh Bos."""
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PORTFOLIO_FILE.exists():
        try:
            data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_portfolio(portfolio: dict[str, dict]) -> dict[str, dict]:
    """Menyimpan daftar saham yang sedang dipegang oleh Bos."""
    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_FILE.write_text(json.dumps(portfolio, indent=2), encoding="utf-8")
    return portfolio


def normalize_ticker(ticker: str) -> str:
    """
    Normalisasi kode saham:
    - Jika 4 huruf alfabet (contoh: BBCA, TLKM, ANTM) dan bukan ticker populer US,
      otomatis tambahkan .JK untuk Bursa Efek Indonesia (BEI).
    - Jika sudah ada titik (.JK) atau tanda strip (BTC-USD) atau indeks (^JKSE), biarkan.
    """
    t = ticker.strip().upper()
    if not t:
        return ""
    if "." in t or "-" in t or t.startswith("^"):
        return t
    us_popular = {"AAPL", "NVDA", "MSFT", "GOOG", "AMZN", "META", "TSLA", "AMD", "NFLX", "COIN", "PLTR"}
    if len(t) == 4 and t.isalpha() and t not in us_popular:
        return f"{t}.JK"
    return t


def load_watchlist() -> list[str]:
    """Memuat daftar saham pantauan dari file JSON atau .env."""
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    if WATCHLIST_FILE.exists():
        try:
            data = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return [normalize_ticker(x) for x in data if normalize_ticker(x)]
        except Exception:
            pass

    raw = os.getenv(
        "DEFAULT_WATCHLIST",
        "BBCA.JK,BBRI.JK,BMRI.JK,TLKM.JK,ASII.JK,BREN.JK,AMMN.JK,GOTO.JK,ANTM.JK,ADRO.JK,MDKA.JK,PGAS.JK",
    )
    tickers = [normalize_ticker(x) for x in raw.split(",") if x.strip()]
    save_watchlist(tickers)
    return tickers


def save_watchlist(tickers: list[str]) -> list[str]:
    """Menyimpan daftar saham pantauan ke file JSON."""
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    cleaned = []
    for t in tickers:
        norm = normalize_ticker(t)
        if norm and norm not in cleaned:
            cleaned.append(norm)
    WATCHLIST_FILE.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    return cleaned
