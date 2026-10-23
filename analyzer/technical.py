from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Optional
import math
import numpy as np
import pandas as pd
import pytz
import yfinance as yf

import config


def get_idx_tick_size(price: float, is_idx: bool = True) -> float:
    if not is_idx:
        return 0.01
    if price < 200:
        return 1.0
    elif price < 500:
        return 2.0
    elif price < 2000:
        return 5.0
    elif price < 5000:
        return 10.0
    return 25.0


def round_idx_tick(price: float, is_idx: bool = True) -> float:
    """
    Membulatkan harga sesuai aturan Fraksi Harga Saham BEI (IDX):
    - Harga < 200       : kelipatan Rp 1
    - Harga 200 - 500   : kelipatan Rp 2
    - Harga 500 - 2000  : kelipatan Rp 5
    - Harga 2000 - 5000 : kelipatan Rp 10
    - Harga >= 5000     : kelipatan Rp 25
    Untuk saham US/Crypto, bulatkan 2 desimal.
    """
    if price is None or math.isnan(price) or price <= 0:
        return 0.0
    if not is_idx:
        return round(float(price), 2)
    p = float(price)
    if p < 200:
        tick = 1
    elif p < 500:
        tick = 2
    elif p < 2000:
        tick = 5
    elif p < 5000:
        tick = 10
    else:
        tick = 25
    return float(int(round(p / tick) * tick))


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def compute_macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift(1)).abs()
    low_close = (df["Low"] - df["Close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def compute_bollinger(
    series: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = mid + (std * std_dev)
    lower = mid - (std * std_dev)
    return upper, mid, lower


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Menghitung Intraday VWAP (Volume Weighted Average Price) untuk hari berjalan."""
    if df.empty:
        return pd.Series(dtype=float)
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
    tp_vol = typical_price * df["Volume"]
    # Kelompokkan per tanggal agar VWAP di-reset setiap pembukaan pasar pagi
    dates = df.index.date
    cum_tp_vol = tp_vol.groupby(dates).cumsum()
    cum_vol = df["Volume"].groupby(dates).cumsum().replace(0, np.nan)
    return (cum_tp_vol / cum_vol).ffill()


def compute_cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Menghitung Chaikin Money Flow (CMF 20) sebagai proxy aliran dana institusi & asing di BEI.
    - CMF > +0.08: Akumulasi institusi kuat (Inflow).
    - CMF < -0.08: Distribusi / Guyuran asing/institusi masif (Outflow).
    """
    if df.empty or len(df) < 5:
        return pd.Series(0.0, index=df.index)
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    vol = df["Volume"]
    hl_diff = (high - low).replace(0, np.nan)
    mf_multiplier = ((close - low) - (high - close)) / hl_diff
    mf_volume = mf_multiplier.fillna(0.0) * vol
    sum_mfv = mf_volume.rolling(period, min_periods=5).sum()
    sum_vol = vol.rolling(period, min_periods=5).sum().replace(0, np.nan)
    return (sum_mfv / sum_vol).fillna(0.0)


@dataclass
class TechnicalSnapshot:
    ticker: str
    is_idx: bool
    timestamp_wib: str
    last_bar_time: str
    current_price: float
    prev_close: float
    change_pct: float
    day_high: float
    day_low: float
    # Indikator Intraday (15m) - Untuk eksekusi "Beli Jam Segini"
    intraday_vwap: float
    intraday_ema9: float
    intraday_ema21: float
    intraday_rsi: float
    intraday_macd_hist: float
    intraday_vol_spike_ratio: float
    intraday_status: str
    # Indikator Harian (Daily 1D) - Untuk Swing & Tren Utama
    daily_ema20: float
    daily_ema50: float
    daily_sma200: float
    daily_rsi: float
    daily_macd_line: float
    daily_macd_signal: float
    daily_macd_hist: float
    daily_bb_upper: float
    daily_bb_lower: float
    daily_atr: float
    daily_vol_ratio: float
    daily_trend: str
    # Support, Resistance & Rencana Trading Kuantitatif (Hard Math)
    support_1: float
    support_2: float
    resistance_1: float
    resistance_2: float
    entry_low: float
    entry_high: float
    take_profit_1: float
    take_profit_2: float
    stop_loss: float
    reward_to_risk: float
    # Skor Kuantitatif (0-100) & Alasan Algoritma
    quant_score: int
    action_label: str
    best_execution_window: str
    best_sell_window: str
    signals_detected: list[str]
    # Phase 2-5 Audit, Epistemic Separation, & Persistent Memory Fields
    setup_type: str = "GENERAL_SETUP"
    direction: str = "WAIT"
    tick_size: float = 1.0
    spread_pct: float = 0.0
    last_bar_iso: str = ""
    volume_shares: float = 0.0
    supporting_evidence: list[str] = field(default_factory=list)
    opposing_evidence: list[str] = field(default_factory=list)
    technical_facts: list[str] = field(default_factory=list)
    interpretations: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    invalidation_conditions: str = ""
    estimated_risk_pct: float = 0.0
    estimated_gross_return_pct: float = 0.0
    estimated_net_return_pct: float = 0.0
    data_is_valid: bool = True
    validation_notes: str = "Valid OHLCV data"
    # Institutional & Advanced Quant Fields (Freqtrade, TradingAgents, FinRL inspired)
    cmf_20: float = 0.0
    foreign_flow_status: str = "NETRAL"
    recommended_lots: int = 1
    trailing_stop_plan: str = "Aktif jika gain >= +1.5% (kunci modal BEP +0.5%)"
    bandarmologi_summary: str = "Netral"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_ticker_quant(ticker: str) -> Optional[TechnicalSnapshot]:
    """
    Mengambil data real-time/terbaru dari Yahoo Finance (Daily 6 bulan + Intraday 15m 5 hari)
    dan menghitung seluruh indikator teknikal serta level Entry, TP, dan CL secara presisi.
    """
    is_idx = ticker.upper().endswith(".JK")
    try:
        tk = yf.Ticker(ticker)
        df_daily = tk.history(period="9mo", interval="1d", auto_adjust=False)
        if df_daily is None or df_daily.empty or len(df_daily) < 30:
            return None

        df_intra = tk.history(period="5d", interval="15m", auto_adjust=False)
    except Exception:
        return None

    df_daily = df_daily.dropna(subset=["Close", "High", "Low"]).copy()
    if len(df_daily) < 30:
        return None

    # --- 1. Perhitungan Indikator Daily (Swing & Tren Utama) ---
    close_d = df_daily["Close"]
    df_daily["EMA20"] = close_d.ewm(span=20, adjust=False).mean()
    df_daily["EMA50"] = close_d.ewm(span=50, adjust=False).mean()
    df_daily["SMA200"] = (
        close_d.rolling(200).mean()
        if len(close_d) >= 200
        else close_d.ewm(span=100, adjust=False).mean()
    )
    df_daily["RSI"] = compute_rsi(close_d, 14)
    macd_l, macd_s, macd_h = compute_macd(close_d)
    df_daily["MACD"] = macd_l
    df_daily["MACD_SIGNAL"] = macd_s
    df_daily["MACD_HIST"] = macd_h
    bb_u, bb_m, bb_l = compute_bollinger(close_d, 20, 2.0)
    df_daily["BB_UPPER"] = bb_u
    df_daily["BB_LOWER"] = bb_l
    df_daily["ATR"] = compute_atr(df_daily, 14)
    df_daily["VOL_MA20"] = df_daily["Volume"].rolling(20).mean().replace(0, np.nan)
    df_daily["CMF"] = compute_cmf(df_daily, 20)

    last_d = df_daily.iloc[-1]
    prev_d = df_daily.iloc[-2] if len(df_daily) >= 2 else last_d

    current_price = float(last_d["Close"])
    prev_close = float(prev_d["Close"])
    day_high = float(last_d["High"])
    day_low = float(last_d["Low"])
    cmf_val = round(float(last_d["CMF"]), 3) if not np.isnan(last_d["CMF"]) else 0.0

    # --- 2. Perhitungan Indikator Intraday 15 Menit (Untuk Sinyal "Jam Segini") ---
    intra_vwap = current_price
    intra_ema9 = current_price
    intra_ema21 = current_price
    intra_rsi = float(last_d["RSI"])
    intra_macd_hist = 0.0
    intra_vol_spike = 1.0
    last_bar_str = str(df_daily.index[-1].strftime("%Y-%m-%d"))
    last_bar_iso = pd.Timestamp(df_daily.index[-1]).tz_localize("Asia/Jakarta").isoformat() if df_daily.index[-1].tzinfo is None else df_daily.index[-1].tz_convert("Asia/Jakarta").isoformat()

    if df_intra is not None and not df_intra.empty and len(df_intra) >= 15:
        df_intra = df_intra.dropna(subset=["Close", "High", "Low"]).copy()
        if len(df_intra) >= 15:
            c_i = df_intra["Close"]
            df_intra["VWAP"] = compute_vwap(df_intra)
            df_intra["EMA9"] = c_i.ewm(span=9, adjust=False).mean()
            df_intra["EMA21"] = c_i.ewm(span=21, adjust=False).mean()
            df_intra["RSI"] = compute_rsi(c_i, 14)
            _, _, m_hist_i = compute_macd(c_i)
            df_intra["MACD_HIST"] = m_hist_i
            vol_ma_i = df_intra["Volume"].rolling(20).mean().replace(0, np.nan)
            df_intra["VOL_RATIO"] = (df_intra["Volume"] / vol_ma_i).fillna(1.0)

            last_i = df_intra.iloc[-1]
            current_price = float(last_i["Close"])
            intra_vwap = float(last_i["VWAP"]) if not np.isnan(last_i["VWAP"]) else current_price
            intra_ema9 = float(last_i["EMA9"])
            intra_ema21 = float(last_i["EMA21"])
            intra_rsi = float(last_i["RSI"])
            intra_macd_hist = float(last_i["MACD_HIST"])
            # Ambil rasio lonjakan volume maksimum di 2 candle 15-menit terakhir
            recent_vol_ratios = df_intra["VOL_RATIO"].iloc[-2:].values
            intra_vol_spike = float(np.nanmax(recent_vol_ratios)) if len(recent_vol_ratios) else 1.0

            try:
                bar_dt = df_intra.index[-1]
                if bar_dt.tzinfo is not None:
                    bar_dt = bar_dt.astimezone(pytz.timezone("Asia/Jakarta"))
                else:
                    bar_dt = pytz.timezone("Asia/Jakarta").localize(bar_dt)
                last_bar_str = bar_dt.strftime("%Y-%m-%d %H:%M WIB")
                last_bar_iso = bar_dt.isoformat()
            except Exception:
                pass

    change_pct = ((current_price - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0

    # --- 3. Support, Resistance & Pivot Points ---
    recent_20 = df_daily.iloc[-20:]
    swing_low_20 = float(recent_20["Low"].min())
    swing_high_20 = float(recent_20["High"].max())
    recent_5 = df_daily.iloc[-5:]
    swing_low_5 = float(recent_5["Low"].min())
    swing_high_5 = float(recent_5["High"].max())

    atr_val = float(last_d["ATR"]) if not np.isnan(last_d["ATR"]) and last_d["ATR"] > 0 else (current_price * 0.025)

    # Support 1 (Intraday/Daily dekat) & Support 2 (Swing bawah)
    raw_s1 = max(swing_low_5, current_price - 1.0 * atr_val)
    if raw_s1 >= current_price * 0.992:
        raw_s1 = current_price - 0.9 * atr_val
    raw_s2 = min(swing_low_20, raw_s1 - 1.2 * atr_val)

    # Resistance 1 (Target Intraday/Harian) & Resistance 2 (Target Swing)
    raw_r1 = current_price + 1.2 * atr_val
    if swing_high_5 > current_price * 1.015:
        raw_r1 = min(swing_high_5, current_price + 1.5 * atr_val)
    raw_r2 = max(raw_r1 + 1.4 * atr_val, min(swing_high_20, current_price + 3.0 * atr_val))

    support_1 = round_idx_tick(raw_s1, is_idx)
    support_2 = round_idx_tick(raw_s2, is_idx)
    if support_2 >= support_1:
        support_2 = round_idx_tick(support_1 * 0.96, is_idx)

    resistance_1 = round_idx_tick(raw_r1, is_idx)
    resistance_2 = round_idx_tick(raw_r2, is_idx)
    if resistance_2 <= resistance_1:
        resistance_2 = round_idx_tick(resistance_1 * 1.04, is_idx)

    # --- 4. Sistem Scoring Kuantitatif (0 - 100) & Deteksi Sinyal ---
    score = 50
    signals: list[str] = []

    ema20_d = float(last_d["EMA20"])
    ema50_d = float(last_d["EMA50"])
    sma200_d = float(last_d["SMA200"])
    rsi_d = float(last_d["RSI"])
    macd_h_d = float(last_d["MACD_HIST"])
    prev_macd_h_d = float(prev_d["MACD_HIST"]) if not np.isnan(prev_d["MACD_HIST"]) else 0.0
    vol_ratio_d = (
        float(last_d["Volume"] / last_d["VOL_MA20"])
        if not np.isnan(last_d["VOL_MA20"]) and last_d["VOL_MA20"] > 0
        else 1.0
    )

    # Evaluasi Tren Harian (Swing)
    if current_price > ema20_d > ema50_d:
        score += 12
        daily_trend = "UPTREND KUAT (Bullish Alignment)"
        signals.append("Harga di atas EMA20 & EMA50 Daily (Uptrend)")
    elif current_price > ema20_d:
        score += 6
        daily_trend = "BULLISH REBOUND (Di atas EMA20)"
        signals.append("Harga bertahan di atas EMA20 Daily")
    elif current_price < ema20_d < ema50_d:
        score -= 12
        daily_trend = "DOWNTREND (Bearish)"
        signals.append("Harga di bawah EMA20 & EMA50 Daily (Tekanan Jual)")
    else:
        daily_trend = "SIDEWAYS / KONSOLIDASI"

    if current_price > sma200_d:
        score += 5
    else:
        score -= 5

    # Evaluasi Momentum MACD & RSI Daily
    if macd_h_d > 0 and macd_h_d > prev_macd_h_d:
        score += 8
        signals.append("Histogram MACD Daily positif & menguat")
    elif macd_h_d > prev_macd_h_d and prev_macd_h_d < 0:
        score += 4
        signals.append("MACD Daily mulai melandai (Potensi Golden Cross)")
    elif macd_h_d < 0 and macd_h_d < prev_macd_h_d:
        score -= 8

    if 45 <= rsi_d <= 67:
        score += 6
        signals.append(f"RSI Daily sehat di zona {rsi_d:.1f} (Ruang naik masih luas)")
    elif 30 <= rsi_d < 45:
        score += 4
        signals.append(f"RSI Daily dekat area Oversold ({rsi_d:.1f}) - Potensi pantulan")
    elif rsi_d < 30:
        score += 5
        signals.append(f"RSI Daily Oversold ekstrem ({rsi_d:.1f}) - Siap-siap Technical Rebound")
    elif rsi_d > 75:
        score -= 8
        signals.append(f"RSI Daily Overbought ({rsi_d:.1f}) - Rawan profit taking")

    # Evaluasi Intraday 15m (Kunci untuk "Beli Jam Segini")
    if current_price >= intra_vwap and intra_ema9 >= intra_ema21:
        score += 12
        intraday_status = "BULLISH INTRADAY (Di atas VWAP & EMA9>EMA21)"
        signals.append(f"Intraday 15m di atas VWAP ({round_idx_tick(intra_vwap, is_idx):.0f}) & EMA9 > EMA21")
    elif current_price >= intra_vwap:
        score += 6
        intraday_status = "ACCUMULATION (Bertahan di atas VWAP)"
        signals.append(f"Intraday bertahan di atas harga rata-rata bandar/VWAP ({round_idx_tick(intra_vwap, is_idx):.0f})")
    else:
        score -= 7
        intraday_status = "DI BAWAH VWAP (Tunggu pantulan / Buy on Weakness)"
        signals.append(f"Harga intraday masih di bawah VWAP ({round_idx_tick(intra_vwap, is_idx):.0f})")

    if intra_macd_hist > 0 and 45 <= intra_rsi <= 70:
        score += 6
        signals.append(f"Momentum 15m positif (RSI 15m: {intra_rsi:.1f})")

    # Evaluasi Lonjakan Volume (Volume Spike)
    max_vol_surge = max(vol_ratio_d, intra_vol_spike)
    if max_vol_surge >= 1.8 and change_pct > 0:
        score += 12
        signals.append(f"Lonjakan Volume Akumulasi {max_vol_surge:.1f}x rata-rata!")
    elif max_vol_surge >= 1.3 and change_pct > 0:
        score += 6
        signals.append(f"Volume transaksi meningkat ({max_vol_surge:.1f}x rata-rata)")
    elif max_vol_surge >= 1.6 and change_pct < -1.0:
        score -= 10
        signals.append(f"Waspada distribusi volume besar ({max_vol_surge:.1f}x) saat harga turun")

    score = int(max(5, min(98, score)))

    # --- 5. Kalkulasi Area Beli, Take Profit, dan Cut Loss berbasis ATR & VWAP ---
    if current_price >= intra_vwap:
        raw_entry_low = max(support_1, min(intra_vwap, current_price - 0.25 * atr_val))
        raw_entry_high = current_price
    else:
        # Jika di bawah VWAP, arahkan Buy on Weakness dekat Support 1
        raw_entry_low = support_1
        raw_entry_high = min(current_price, support_1 + 0.35 * atr_val)

    entry_low = round_idx_tick(raw_entry_low, is_idx)
    entry_high = round_idx_tick(max(raw_entry_low, raw_entry_high), is_idx)
    if entry_low == entry_high:
        entry_low = round_idx_tick(entry_high * 0.99, is_idx)

    # Stop Loss di bawah Support 1 / 1.0x ATR (perketat risiko maksimal ~2.5% agar terhindar dari rugi dalam)
    raw_sl = min(entry_low - 0.75 * atr_val, support_1 - 0.35 * atr_val)
    raw_sl = max(raw_sl, entry_high * 0.975)  # Batasi risiko maksimal ~2.5%
    stop_loss = round_idx_tick(raw_sl, is_idx)
    if stop_loss >= entry_low:
        stop_loss = round_idx_tick(entry_low * 0.985, is_idx)

    risk_per_share = max(entry_high - stop_loss, entry_high * 0.012)
    min_tp1_threshold = entry_high * 1.025  # Minimal potensi cuan kotor +2.5% agar RRR sehat
    tp1 = round_idx_tick(max(resistance_1, entry_high + 2.0 * risk_per_share, min_tp1_threshold), is_idx)
    tp2 = round_idx_tick(max(resistance_2, entry_high + 3.2 * risk_per_share, entry_high * 1.045), is_idx)

    rr_ratio = round((tp1 - entry_high) / risk_per_share, 2) if risk_per_share > 0 else 2.0

    # --- 6. Evaluasi Spread Bid-Ask, Bukti Pendukung vs Penentang, & Setup Classification ---
    tick_sz = get_idx_tick_size(current_price, is_idx)
    spread_pct = round((tick_sz / current_price) * 100.0, 4) if current_price > 0 else 0.0
    total_fee_slip_pct = config.FEE_BUY_PCT + config.FEE_SELL_PCT + config.DEFAULT_SLIPPAGE_PCT
    atr_pct = round((atr_val / current_price) * 100.0, 2) if current_price > 0 else 0.0

    supporting_ev: list[str] = list(signals)
    opposing_ev: list[str] = []

    # Deteksi Bahaya Pisau Jatuh (Downtrend Knife Protection - cegah kerugian seperti di BBRI/BMRI)
    is_downtrend = current_price < ema20_d < ema50_d
    if is_downtrend:
        score -= 15
        opposing_ev.append(
            f"DOWNTREND STRUKTURAL: Harga (Rp {current_price:,.0f}) di bawah EMA20 (Rp {ema20_d:,.0f}) & EMA50 (Rp {ema50_d:,.0f}). Dilarang tangkap pisau jatuh!"
        )
    elif current_price < ema20_d:
        opposing_ev.append(f"Harga (Rp {current_price:,.0f}) masih di bawah EMA20 Daily (Rp {ema20_d:,.0f})")

    # Evaluasi Aliran Dana Asing / Institusi via CMF (Chaikin Money Flow)
    sector_name = config.SECTOR_MAP.get(ticker.upper(), "OTHER")
    is_big_bank = sector_name == "FINANCE" or ticker.upper() in {"BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK"}
    if cmf_val >= 0.08:
        foreign_flow_status = "AKUMULASI KUAT (Big Money Inflow)"
        score += 8
        signals.append(f"Arus dana institusi/asing positif kuat (CMF: {cmf_val:+.2f})")
    elif cmf_val >= 0.02:
        foreign_flow_status = "AKUMULASI RINGAN (Inflow Terpantau)"
        score += 4
        signals.append(f"Arus dana institusi positif (CMF: {cmf_val:+.2f})")
    elif cmf_val <= -0.08:
        foreign_flow_status = "DISTRIBUSI MASIF (Guyuran Dana Asing/Institusi)"
        score -= 12
        opposing_ev.append(f"Guyuran/Distribusi dana institusi masif (CMF: {cmf_val:+.2f})")
    elif cmf_val <= -0.03:
        foreign_flow_status = "DISTRIBUSI RINGAN (Outflow Terpantau)"
        score -= 6
        opposing_ev.append(f"Tekanan jual/outflow dana institusi (CMF: {cmf_val:+.2f})")
    else:
        foreign_flow_status = "NETRAL (Aliran Dana Berimbang)"

    if is_big_bank and cmf_val < -0.04:
        score -= 14
        opposing_ev.append(
            f"ARUS DANA PERBANKAN NEGATIF: CMF ({cmf_val:+.2f}) mendeteksi aksi keluar dana asing dari saham bank!"
        )

    if current_price < intra_vwap:
        opposing_ev.append(f"Harga masih di bawah VWAP Intraday (Rp {intra_vwap:,.0f})")
    if max_vol_surge < 1.0:
        opposing_ev.append(f"Volume transaksi relatif sepi ({max_vol_surge:.2f}x rata-rata)")
    if spread_pct > 0.70:
        score -= 18
        opposing_ev.append(
            f"Spread minimum 1 tick terlalu lebar ({spread_pct:.2f}% per tick) dibanding biaya transaksi ({total_fee_slip_pct:.2f}%)"
        )
    if atr_pct > 5.5:
        score -= 10
        opposing_ev.append(
            f"Volatilitas ATR harian terlalu liar ({atr_pct:.1f}% dari harga). Risiko slippage & gap down ekstrem."
        )

    score = int(max(5, min(98, score)))

    est_risk_pct = round(((entry_high - stop_loss) / entry_high) * 100.0, 2) if entry_high > 0 else 0.0
    est_gross_ret_pct = round(((tp1 - entry_high) / entry_high) * 100.0, 2) if entry_high > 0 else 0.0
    est_net_ret_pct = round(est_gross_ret_pct - total_fee_slip_pct, 2)

    # Deteksi Jam Sepi BEI (Cegah posisi gantung / Time Exit akibat likuiditas mengering)
    wib_now = datetime.now(pytz.timezone("Asia/Jakarta"))
    hour_float = wib_now.hour + wib_now.minute / 60.0
    is_midday_lull = 11.25 <= hour_float <= 13.75

    # Tentukan Setup Type & Direction secara objektif (Diperketat untuk melindungi modal riil)
    if is_downtrend and max_vol_surge < 1.80:
        # Saham downtrend tanpa akumulasi volume masif: Wajib AVOID agar tidak nyangkut
        setup_type = "DOWNTREND_FALLING_KNIFE_AVOID"
        direction = "AVOID"
    elif is_big_bank and cmf_val < -0.05:
        # Bank jumbo sedang diguyur asing: Wajib AVOID (Cegah kerugian berulang di BBRI/BMRI)
        setup_type = "INSTITUTIONAL_BANK_OUTFLOW_AVOID"
        direction = "AVOID"
    elif spread_pct > 0.70 or atr_pct > 5.5:
        # Volatilitas liar / spread lebar (seperti BREN): WAIT
        setup_type = "HIGH_SPREAD_OR_EXTREME_VOLATILITY_WAIT"
        direction = "WAIT"
    elif est_net_ret_pct < 1.20:
        setup_type = "LOW_NET_EDGE_WAIT"
        direction = "WAIT"
    elif is_midday_lull and max_vol_surge < 1.60:
        setup_type = "MIDDAY_LULL_WAIT"
        direction = "WAIT"
        opposing_ev.append("Sesi Istirahat/Sepi (11:15 - 13:45 WIB): Tahan beli agar tidak gantung dan kena Time Exit.")
    elif current_price >= intra_vwap and current_price > ema20_d and max_vol_surge >= 1.25 and cmf_val >= -0.02:
        setup_type = "VWAP_BREAKOUT_UPTREND"
        direction = "BUY" if score >= 68 else "WAIT"
    elif current_price >= intra_vwap and rsi_d < 45 and not is_downtrend and cmf_val >= 0.0:
        setup_type = "OVERSOLD_VWAP_RECLAIM"
        direction = "BUY" if score >= 66 and max_vol_surge >= 1.15 else "WAIT"
    elif current_price >= intra_vwap and score >= 75 and max_vol_surge >= 1.50 and current_price > ema20_d and cmf_val >= 0.0:
        # Hanya boleh BUY jika ada volume spike kuat & tren harian aman di atas EMA20 & CMF positif
        setup_type = "INTRADAY_VWAP_SUPPORT"
        direction = "BUY"
    elif current_price >= intra_vwap and score >= 58:
        # Hover di atas VWAP tanpa volume konfirmasi: WAIT demi keamanan (hindari drawdown)
        setup_type = "INTRADAY_VWAP_SUPPORT_WAIT"
        direction = "WAIT"
    elif score < 45:
        setup_type = "BEARISH_BELOW_VWAP"
        direction = "AVOID"
    else:
        setup_type = "CONSOLIDATION_WAIT"
        direction = "WAIT"

    # Dynamic Position Sizing (FinRL / Kelly Criterion style)
    max_lots = max(1, config.STOCKBIT_MAX_LOT)
    if is_downtrend or spread_pct > 0.45 or atr_pct > 4.5 or is_midday_lull or cmf_val < 0.0:
        recommended_lots = 1
    elif direction == "BUY" and score >= 76 and cmf_val >= 0.05:
        recommended_lots = max_lots
    else:
        recommended_lots = max(1, max_lots // 2)

    trailing_plan = f"Jika gain >= +1.5%, naikkan SL ke Rp {round_idx_tick(entry_high * 1.005, is_idx):,.0f} (BEP +0.5%)"

    # Evaluasi Bandarmologi & Aliran Broker BEI
    try:
        from analyzer.bandarmologi import analyze_bandarmologi_footprint
        bnd = analyze_bandarmologi_footprint(ticker, df_daily, cmf_val, max_vol_surge)
        bandar_summary = bnd.get("summary", "Aliran dana berimbang.")
        if "AKUMULASI" in bnd.get("status", ""):
            signals.append(f"Bandarmologi: {bnd['status']}")
        elif "DISTRIBUSI" in bnd.get("status", ""):
            opposing_ev.append(f"Bandarmologi: {bnd['status']}")
    except Exception:
        bandar_summary = "Aliran dana broker terpantau berimbang."

    tech_facts = [
        f"Harga terakhir={round_idx_tick(current_price, is_idx):.0f} pada {last_bar_str} ({change_pct:+.2f}%)",
        f"VWAP 15m={round_idx_tick(intra_vwap, is_idx):.0f}, EMA9 15m={round_idx_tick(intra_ema9, is_idx):.0f}, EMA21 15m={round_idx_tick(intra_ema21, is_idx):.0f}",
        f"EMA20 Daily={round_idx_tick(ema20_d, is_idx):.0f}, EMA50 Daily={round_idx_tick(ema50_d, is_idx):.0f}, RSI Daily={rsi_d:.1f}, RSI 15m={intra_rsi:.1f}",
        f"Volume Ratio={max_vol_surge:.2f}x, ATR(14)={atr_val:.1f}, Tick Size={tick_sz:.0f} ({spread_pct:.2f}%)",
    ]
    interpretations = [
        f"Tren Harian: {daily_trend}; Status Intraday: {intraday_status}",
        f"Setup diklasifikasikan sebagai {setup_type} dengan estimasi net return {est_net_ret_pct:+.2f}% setelah biaya {total_fee_slip_pct:.2f}%.",
    ]
    assumptions = [
        f"Asumsi biaya beli {config.FEE_BUY_PCT:.2f}% + biaya jual {config.FEE_SELL_PCT:.2f}% + slippage {config.DEFAULT_SLIPPAGE_PCT:.2f}%.",
        "Order Book Level 2 real-time tidak tersedia dari feed yfinance; likuiditas diestimasi dari rasio volume & fraksi tick BEI.",
    ]
    invalidation_cond = (
        f"Sinyal batal jika candle 15m tutup di bawah Stop Loss (Rp {stop_loss:,.0f}) "
        f"atau jatuh kembali ke bawah VWAP (Rp {round_idx_tick(intra_vwap, is_idx):,.0f}) dengan tekanan volume jual."
    ).replace(",", ".")

    # --- 7. Rekomendasi Aksi & Jam Eksekusi Terbaik ---
    wib_now = datetime.now(pytz.timezone("Asia/Jakarta"))
    hour_float = wib_now.hour + wib_now.minute / 60.0

    if direction == "BUY" and score >= 75:
        action_label = "STRONG BUY (Momentum & Intraday Kuat)"
        if 9.0 <= hour_float <= 11.5:
            best_window = "Sesi 1 Pagi (09:15 - 10:30 WIB) saat konfirmasi bertahan di atas VWAP"
        elif 13.5 <= hour_float <= 15.8:
            best_window = "Sesi 2 Sore (14:00 - 15:30 WIB) untuk Momentum / JJS (Jajan Sore)"
        else:
            best_window = "Pantau Pembukaan Sesi 1 (09:15 - 09:45 WIB) atau Sesi 2 (14:00 - 15:30 WIB)"
        best_sell = (
            f"Pasang Jual Otomatis di TP1 (Rp {tp1:,.0f}). Biasanya tercapai jam 10:45-11:30 WIB, "
            "jam 14:30-15:45 WIB, atau besok pagi jam 09:05-09:30 WIB saat lonjakan buka pasar."
        ).replace(",", ".")
    elif direction == "BUY" and score >= 60:
        action_label = "BUY ON WEAKNESS (Antri di Area Support / VWAP)"
        best_window = "Tunggu koreksi wajar jam 10:15 - 11:15 WIB atau 13:45 - 14:30 WIB di Area Beli"
        best_sell = (
            f"Simpan 1-4 hari (Swing) dan pasang antrian jual di TP1 (Rp {tp1:,.0f}). "
            "Jam jual terbaik biasanya pagi hari (09:10 - 10:00 WIB) saat harga memantul naik, "
            f"atau wajib jual jam 15:30-15:45 WIB jika harga turun jebol Rem Darurat (< Rp {stop_loss:,.0f})."
        ).replace(",", ".")
    elif direction == "WAIT":
        action_label = "WAIT & SEE (Tunggu Breakout / Konfirmasi Volume)"
        best_window = "Jangan buru-buru masuk; tunggu tembus VWAP/Resistance dengan volume & spread memadai"
        best_sell = "Jika sudah terlanjur punya, manfaatkan kenaikan jam 09:15-10:00 WIB untuk jual di dekat Resistance."
    else:
        action_label = "AVOID / HINDARI DULU (Tekanan Jual Masih Dominan)"
        best_window = "Hindari beli baru; tunggu struktur harga membaik"
        best_sell = f"Jika masih pegang saham ini dan jam 15:30 WIB harganya di bawah Rp {stop_loss:,.0f}, segera jual agar tidak nyangkut."

    return TechnicalSnapshot(
        ticker=ticker.upper(),
        is_idx=is_idx,
        timestamp_wib=wib_now.strftime("%Y-%m-%d %H:%M WIB"),
        last_bar_time=last_bar_str,
        current_price=round_idx_tick(current_price, is_idx),
        prev_close=round_idx_tick(prev_close, is_idx),
        change_pct=round(change_pct, 2),
        day_high=round_idx_tick(day_high, is_idx),
        day_low=round_idx_tick(day_low, is_idx),
        intraday_vwap=round_idx_tick(intra_vwap, is_idx),
        intraday_ema9=round_idx_tick(intra_ema9, is_idx),
        intraday_ema21=round_idx_tick(intra_ema21, is_idx),
        intraday_rsi=round(intra_rsi, 1),
        intraday_macd_hist=round(intra_macd_hist, 3),
        intraday_vol_spike_ratio=round(intra_vol_spike, 2),
        intraday_status=intraday_status,
        daily_ema20=round_idx_tick(ema20_d, is_idx),
        daily_ema50=round_idx_tick(ema50_d, is_idx),
        daily_sma200=round_idx_tick(sma200_d, is_idx),
        daily_rsi=round(rsi_d, 1),
        daily_macd_line=round(float(last_d["MACD"]), 2),
        daily_macd_signal=round(float(last_d["MACD_SIGNAL"]), 2),
        daily_macd_hist=round(macd_h_d, 2),
        daily_bb_upper=round_idx_tick(float(last_d["BB_UPPER"]), is_idx),
        daily_bb_lower=round_idx_tick(float(last_d["BB_LOWER"]), is_idx),
        daily_atr=round(atr_val, 2),
        daily_vol_ratio=round(vol_ratio_d, 2),
        daily_trend=daily_trend,
        support_1=support_1,
        support_2=support_2,
        resistance_1=resistance_1,
        resistance_2=resistance_2,
        entry_low=entry_low,
        entry_high=entry_high,
        take_profit_1=tp1,
        take_profit_2=tp2,
        stop_loss=stop_loss,
        reward_to_risk=rr_ratio,
        quant_score=score,
        action_label=action_label,
        best_execution_window=best_window,
        best_sell_window=best_sell,
        signals_detected=signals,
        setup_type=setup_type,
        direction=direction,
        tick_size=tick_sz,
        spread_pct=spread_pct,
        last_bar_iso=last_bar_iso,
        volume_shares=float(last_d["Volume"]),
        supporting_evidence=supporting_ev,
        opposing_evidence=opposing_ev,
        technical_facts=tech_facts,
        interpretations=interpretations,
        assumptions=assumptions,
        invalidation_conditions=invalidation_cond,
        estimated_risk_pct=est_risk_pct,
        estimated_gross_return_pct=est_gross_ret_pct,
        estimated_net_return_pct=est_net_ret_pct,
        data_is_valid=True,
        validation_notes="Valid OHLCV Daily + 15m Intraday snapshot",
        cmf_20=cmf_val,
        foreign_flow_status=foreign_flow_status,
        recommended_lots=recommended_lots,
        trailing_stop_plan=trailing_plan,
        bandarmologi_summary=bandar_summary,
    )


def get_ihsg_overview() -> dict[str, Any]:
    """Mengambil kondisi terkini IHSG (^JKSE) sebagai acuan pasar saat DSU."""
    try:
        tk = yf.Ticker("^JKSE")
        df = tk.history(period="1mo", interval="1d")
        if df is None or df.empty or len(df) < 2:
            return {"status": "Data IHSG belum tersedia"}
        last = df.iloc[-1]
        prev = df.iloc[-2]
        close = float(last["Close"])
        prev_close = float(prev["Close"])
        chg = ((close - prev_close) / prev_close) * 100.0
        ema20 = float(df["Close"].ewm(span=20, adjust=False).mean().iloc[-1])
        if close >= ema20 and chg >= 0:
            regime = "BULLISH_UPTREND"
        elif close >= ema20 and chg < 0:
            regime = "BULLISH_PULLBACK"
        elif close < ema20 and chg >= 0:
            regime = "BEARISH_RECOVERY"
        else:
            regime = "BEARISH_DOWNTREND"
        return {
            "index": "IHSG (^JKSE)",
            "last_close": round(close, 2),
            "change_pct": round(chg, 2),
            "above_ema20": close >= ema20,
            "regime": regime,
            "summary": f"IHSG di level {close:,.2f} ({chg:+.2f}%), {'di atas' if close >= ema20 else 'di bawah'} EMA20 ({ema20:,.2f}) [Rezim: {regime}]",
        }
    except Exception as e:
        return {"status": f"Gagal memuat IHSG: {e}", "regime": "NEUTRAL"}


def scan_watchlist_quant(tickers: list[str]) -> list[TechnicalSnapshot]:
    """Memindai daftar saham dan mengurutkannya dari skor kuantitatif tertinggi."""
    results: list[TechnicalSnapshot] = []
    for t in tickers:
        snap = analyze_ticker_quant(t)
        if snap is not None:
            results.append(snap)
    results.sort(key=lambda x: (x.quant_score, x.change_pct), reverse=True)
    return results
