import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
# Fail-closed: chat ID kosong berarti belum ada owner, bukan berarti semua orang boleh.
ALLOW_AUTO_REGISTER_OWNER = os.getenv("ALLOW_AUTO_REGISTER_OWNER", "false").lower() == "true"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://saham-ai-agent.onrender.com").rstrip("/")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "").strip()
ENABLE_DEMO_TRADING = os.getenv("ENABLE_DEMO_TRADING", "false").lower() == "true"

TIMEZONE = "Asia/Jakarta"
DSU_MORNING_TIME = os.getenv("DSU_MORNING_TIME", "08:15").strip()
MARKET_CLOSE_TIME = os.getenv("MARKET_CLOSE_TIME", "16:15").strip()
MIN_INTRADAY_ALERT_SCORE = int(os.getenv("MIN_INTRADAY_ALERT_SCORE", "68"))

STOCKBIT_TRADING_PIN = os.getenv("STOCKBIT_TRADING_PIN", "").strip()
STOCKBIT_MAX_LOT = int(os.getenv("STOCKBIT_MAX_LOT", "2"))
STOCKBIT_VERIFY_ORDER = os.getenv("STOCKBIT_VERIFY_ORDER", "true").lower() == "true"
STOCKBIT_REQUIRE_CONFIRMATION = os.getenv("STOCKBIT_REQUIRE_CONFIRMATION", "true").lower() == "true"
STOCKBIT_PROFILE_DIR = BASE_DIR / "data" / "stockbit_profile"

WATCHLIST_FILE = BASE_DIR / "data" / "watchlist.json"
PORTFOLIO_FILE = BASE_DIR / "data" / "portfolio.json"
TRADE_LEDGER_FILE = BASE_DIR / "data" / "trade_ledger.json"
PAPER_INITIAL_CASH = float(os.getenv("PAPER_INITIAL_CASH", "0"))
IDX_HOLIDAYS_FILE = BASE_DIR / "data" / "idx_holidays.json"
MEMORY_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", str(BASE_DIR / "data" / "agent_memory.db")))
BACKUP_DIR = BASE_DIR / "data" / "backups"

# Default ke PAPER trading demi keamanan (Safety Phase 8)
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "PAPER").strip().upper()
ALLOW_LIVE_BROKER_EXECUTION = os.getenv("ALLOW_LIVE_BROKER_EXECUTION", "false").strip().lower() == "true"

# Biaya Transaksi & Asumsi Slippage BEI/IDX (Standar Stockbit Sekuritas)
FEE_BUY_PCT = float(os.getenv("FEE_BUY_PCT", "0.15"))      # 0.15%
FEE_SELL_PCT = float(os.getenv("FEE_SELL_PCT", "0.25"))    # 0.25%
DEFAULT_SLIPPAGE_PCT = float(os.getenv("DEFAULT_SLIPPAGE_PCT", "0.10"))  # 0.10%

# Versi Model, Prompt, dan Strategi untuk Audit Trail
AGENT_PROMPT_VERSION = "v2.1-memory-calibrated"
DEFAULT_STRATEGY_NAME = "IDX_VWAP_MOMENTUM_HYBRID"
DEFAULT_STRATEGY_VERSION = "1.0.0"

SECTOR_MAP = {
    "BBCA.JK": "FINANCE",
    "BBRI.JK": "FINANCE",
    "BMRI.JK": "FINANCE",
    "BBNI.JK": "FINANCE",
    "BRIS.JK": "FINANCE",
    "TLKM.JK": "INFRASTRUCTURE_TELCO",
    "ISAT.JK": "INFRASTRUCTURE_TELCO",
    "EXCL.JK": "INFRASTRUCTURE_TELCO",
    "ASII.JK": "INDUSTRIAL_AUTO",
    "UNTR.JK": "INDUSTRIAL_AUTO",
    "BREN.JK": "RENEWABLE_ENERGY",
    "PGEO.JK": "RENEWABLE_ENERGY",
    "AMMN.JK": "BASIC_MATERIALS_MINING",
    "ANTM.JK": "BASIC_MATERIALS_MINING",
    "MDKA.JK": "BASIC_MATERIALS_MINING",
    "BRMS.JK": "BASIC_MATERIALS_MINING",
    "INCO.JK": "BASIC_MATERIALS_MINING",
    "TINS.JK": "BASIC_MATERIALS_MINING",
    "ADRO.JK": "ENERGY_COAL",
    "PTBA.JK": "ENERGY_COAL",
    "ITMG.JK": "ENERGY_COAL",
    "MEDC.JK": "ENERGY_OIL_GAS",
    "PGAS.JK": "ENERGY_GAS",
    "AKRA.JK": "ENERGY_OIL_GAS",
    "GOTO.JK": "TECHNOLOGY",
    "HMSP.JK": "CONSUMER_TOBACCO_ROKOK",
    "GGRM.JK": "CONSUMER_TOBACCO_ROKOK",
    "WIIM.JK": "CONSUMER_TOBACCO_ROKOK",
    "ICBP.JK": "CONSUMER_FOOD_RETAIL",
    "INDF.JK": "CONSUMER_FOOD_RETAIL",
    "MYOR.JK": "CONSUMER_FOOD_RETAIL",
    "AMRT.JK": "CONSUMER_FOOD_RETAIL",
    "JPFA.JK": "CONSUMER_POULTRY",
    "CPIN.JK": "CONSUMER_POULTRY",
    "BSDE.JK": "PROPERTY_REAL_ESTATE",
    "CTRA.JK": "PROPERTY_REAL_ESTATE",
    "SMRA.JK": "PROPERTY_REAL_ESTATE",
    "PWON.JK": "PROPERTY_REAL_ESTATE",
}


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


def load_trade_ledger() -> dict:
    """Ledger paper/live sederhana: kas, realized P&L, dan riwayat transaksi."""
    if TRADE_LEDGER_FILE.exists():
        try:
            data = json.loads(TRADE_LEDGER_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("cash", PAPER_INITIAL_CASH)
                data.setdefault("realized_pnl", 0.0)
                data.setdefault("trades", [])
                return data
        except Exception:
            pass
    return {"cash": PAPER_INITIAL_CASH, "realized_pnl": 0.0, "trades": []}


def save_trade_ledger(ledger: dict) -> dict:
    TRADE_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRADE_LEDGER_FILE.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return ledger


def apply_trade(
    side: str,
    ticker: str,
    lots: int,
    price: float,
    plan: dict[str, float] | None = None,
    note: str = "",
) -> dict:
    """Catat BUY/SELL ke portfolio + ledger. Melempar ValueError jika input tidak valid."""
    side = side.upper()
    ticker = normalize_ticker(ticker)
    lots = int(lots)
    price = float(price)
    if side not in {"BUY", "SELL"}:
        raise ValueError("side harus BUY atau SELL")
    if lots <= 0 or price <= 0:
        raise ValueError("lots dan price harus > 0")

    portfolio = load_portfolio()
    ledger = load_trade_ledger()
    now = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")

    if side == "BUY":
        cost = price * lots * 100 * (1 + FEE_BUY_PCT / 100.0)
        # shortcut: cash check only when ledger cash > 0; set PAPER_INITIAL_CASH > 0 to enforce.
        if ledger.get("cash", 0.0) > 0 and cost > float(ledger["cash"]):
            raise ValueError(
                f"Kas paper tidak cukup: butuh Rp {cost:,.0f}, tersedia Rp {float(ledger['cash']):,.0f}"
            )
        old = portfolio.get(ticker)
        if old:
            old_lots = int(old.get("lots", 1))
            total = old_lots + lots
            old["buy_price"] = round(
                (float(old.get("buy_price", price)) * old_lots + price * lots) / total, 2
            )
            old["lots"] = total
            old["bought_at"] = now
        else:
            old = {"buy_price": price, "lots": lots, "bought_at": now}
            portfolio[ticker] = old
        if plan:
            old.update(plan)
        if ledger.get("cash", 0.0) > 0:
            ledger["cash"] = round(float(ledger["cash"]) - cost, 2)
        ledger["trades"].append(
            {
                "side": "BUY",
                "ticker": ticker,
                "lots": lots,
                "price": price,
                "fee_pct": FEE_BUY_PCT,
                "at": now,
                "note": note,
            }
        )
    else:
        pos = portfolio.get(ticker)
        if not pos:
            raise ValueError(f"{ticker} tidak ada di portfolio")
        held = int(pos.get("lots", 1))
        if lots > held:
            raise ValueError(f"Lot jual ({lots}) melebihi posisi yang dipegang ({held} lot).")
        sell_lots = lots
        buy_price = float(pos.get("buy_price", price))
        gross = price * sell_lots * 100
        sell_fee = gross * FEE_SELL_PCT / 100.0
        buy_fee = buy_price * sell_lots * 100 * FEE_BUY_PCT / 100.0
        realized = gross - buy_price * sell_lots * 100 - sell_fee - buy_fee
        if sell_lots >= held:
            portfolio.pop(ticker, None)
        else:
            pos["lots"] = held - sell_lots
        ledger["cash"] = round(float(ledger.get("cash", 0.0)) + gross - sell_fee, 2)
        ledger["realized_pnl"] = round(
            float(ledger.get("realized_pnl", 0.0)) + realized, 2
        )
        ledger["trades"].append(
            {
                "side": "SELL",
                "ticker": ticker,
                "lots": sell_lots,
                "price": price,
                "fee_pct": FEE_SELL_PCT,
                "realized_pnl": round(realized, 2),
                "at": now,
                "note": note,
            }
        )

    save_portfolio(portfolio)
    save_trade_ledger(ledger)
    return {"portfolio": portfolio, "ledger": ledger, "ticker": ticker, "lots": lots}


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


def load_idx_holidays() -> set[str]:
    """Optional libur bursa: file JSON berisi daftar 'YYYY-MM-DD'."""
    if not IDX_HOLIDAYS_FILE.exists():
        return set()
    try:
        data = json.loads(IDX_HOLIDAYS_FILE.read_text(encoding="utf-8"))
        return {str(x) for x in data if str(x).strip()}
    except Exception:
        return set()


def is_idx_trading_day(day=None) -> bool:
    """Senin-Jumat dan bukan hari libur bursa yang terdaftar."""
    from datetime import date as _date

    d = day or _date.today()
    if d.weekday() >= 5:
        return False
    return d.isoformat() not in load_idx_holidays()
