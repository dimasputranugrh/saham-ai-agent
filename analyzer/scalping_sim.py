from datetime import datetime
import numpy as np
import pandas as pd
import pytz
import yfinance as yf
from analyzer.technical import compute_rsi, compute_vwap, round_idx_tick

FEE_BUY_PCT = 0.0015   # 0.15% (Standar Stockbit Sekuritas)
FEE_SELL_PCT = 0.0025  # 0.25% (Standar Stockbit Sekuritas termasuk pajak PPh 0.1%)


def get_idx_tick_size(price: float) -> int:
    if price < 200:
        return 1
    elif price < 500:
        return 2
    elif price < 2000:
        return 5
    elif price < 5000:
        return 10
    return 25


def run_scalping_audit():
    wib = pytz.timezone("Asia/Jakarta")
    now_wib = datetime.now(wib)
    print(f"=== AUDIT DATA REAL-TIME & HISTORIS INTRADAY (1M & 5M) ===")
    print(f"Waktu Sistem Saat Ini: {now_wib.strftime('%Y-%m-%d %H:%M:%S WIB')}")

    # 1. Cek IHSG (^JKSE)
    ihsg = yf.Ticker("^JKSE")
    df_ihsg_d = ihsg.history(period="1mo", interval="1d")
    df_ihsg_5m = ihsg.history(period="5d", interval="5m")
    if not df_ihsg_d.empty:
        last_ihsg = df_ihsg_d.iloc[-1]
        prev_ihsg = df_ihsg_d.iloc[-2]
        chg_ihsg = (last_ihsg["Close"] - prev_ihsg["Close"]) / prev_ihsg["Close"] * 100
        ema20_ihsg = df_ihsg_d["Close"].ewm(span=20, adjust=False).mean().iloc[-1]
        rsi_ihsg = compute_rsi(df_ihsg_d["Close"], 14).iloc[-1]
        print(
            f"\n[IHSG ^JKSE] Last Date: {df_ihsg_d.index[-1].strftime('%Y-%m-%d')} | "
            f"Open: {last_ihsg['Open']:.2f} | High: {last_ihsg['High']:.2f} | Low: {last_ihsg['Low']:.2f} | "
            f"Close: {last_ihsg['Close']:.2f} ({chg_ihsg:+.2f}%) | EMA20: {ema20_ihsg:.2f} | RSI(14): {rsi_ihsg:.1f}"
        )

    # Kandidat saham likuid BEI yang harga 1 lot-nya terjangkau modal Rp 1.000.000
    candidates = [
        "TLKM.JK", "ASII.JK", "BREN.JK", "ANTM.JK", "ADRO.JK",
        "PGAS.JK", "MDKA.JK", "BBRI.JK", "BMRI.JK", "GOTO.JK",
    ]

    for tk_name in candidates:
        tk = yf.Ticker(tk_name)
        df_1m = tk.history(period="5d", interval="1m", auto_adjust=True)
        df_5m = tk.history(period="5d", interval="5m", auto_adjust=True)
        if df_5m is None or df_5m.empty:
            continue

        df_5m.index = df_5m.index.tz_convert(wib)
        df_5m["VWAP"] = compute_vwap(df_5m)
        df_5m["EMA9"] = df_5m["Close"].ewm(span=9, adjust=False).mean()
        df_5m["EMA21"] = df_5m["Close"].ewm(span=21, adjust=False).mean()
        df_5m["RSI"] = compute_rsi(df_5m["Close"], 14)
        df_5m["VOL_MA20"] = df_5m["Volume"].rolling(20).mean()

        last_date = df_5m.index[-1].date()
        day_5m = df_5m[df_5m.index.date == last_date].copy()

        day_1m = pd.DataFrame()
        if df_1m is not None and not df_1m.empty:
            df_1m.index = df_1m.index.tz_convert(wib)
            df_1m["VWAP"] = compute_vwap(df_1m)
            df_1m["EMA9"] = df_1m["Close"].ewm(span=9, adjust=False).mean()
            df_1m["EMA21"] = df_1m["Close"].ewm(span=21, adjust=False).mean()
            df_1m["RSI"] = compute_rsi(df_1m["Close"], 14)
            day_1m = df_1m[df_1m.index.date == last_date].copy()

        last_row = day_5m.iloc[-1]
        close_p = float(last_row["Close"])
        tick = get_idx_tick_size(close_p)
        spread_pct = (tick / close_p) * 100.0
        total_vol_shares = float(day_5m["Volume"].sum())
        total_val_idr = float((day_5m["Close"] * day_5m["Volume"]).sum())

        # Ambil metrik 1m terakhir jika tersedia
        info_1m = "N/A"
        if not day_1m.empty:
            r1 = day_1m.iloc[-1]
            info_1m = (
                f"Last 1m ({day_1m.index[-1].strftime('%H:%M')}): Close={r1['Close']:.0f}, "
                f"VWAP={r1['VWAP']:.0f}, EMA9={r1['EMA9']:.0f}, EMA21={r1['EMA21']:.0f}, RSI={r1['RSI']:.1f}"
            )

        print(f"\n--- {tk_name} (Tanggal Bursa Terakhir: {last_date}) ---")
        print(
            f"Close: Rp {close_p:,.0f} (Last 5m: {day_5m.index[-1].strftime('%H:%M WIB')}) | "
            f"1 Lot = Rp {close_p*100:,.0f} | Tick/Spread Minimal: Rp {tick} ({spread_pct:.2f}%)"
        )
        print(
            f"Total Volume Hari Ini: {total_vol_shares/1e6:.2f} Juta Lembar | "
            f"Nilai Transaksi Intraday: Rp {total_val_idr/1e9:.2f} Miliar"
        )
        print(
            f"Indikator 5m Terakhir: VWAP=Rp {last_row['VWAP']:,.0f} | "
            f"EMA9=Rp {last_row['EMA9']:,.0f} | EMA21=Rp {last_row['EMA21']:,.0f} | RSI={last_row['RSI']:.1f}"
        )
        print(f"Indikator 1m Terakhir: {info_1m}")

        # Cek Jendela 1: 09:00 - 10:00 WIB & Jendela 2: 13:30 - 14:30 WIB
        w1 = day_5m.between_time("09:00", "10:00")
        w2 = day_5m.between_time("13:30", "14:30")
        if not w1.empty:
            w1_vol = w1["Volume"].sum()
            print(
                f"  [Window 09:00-10:00 WIB (5m)] Open={w1['Open'].iloc[0]:.0f}, High={w1['High'].max():.0f}, "
                f"Low={w1['Low'].min():.0f}, Close={w1['Close'].iloc[-1]:.0f}, Vol={w1_vol/1e6:.2f}M, "
                f"VWAP@09:15={w1['VWAP'].iloc[min(3, len(w1)-1)]:.0f}, RSI_range={w1['RSI'].min():.1f}-{w1['RSI'].max():.1f}"
            )
            for ts, row in w1.iterrows():
                print(
                    f"    {ts.strftime('%H:%M')}: O={row['Open']:.0f} H={row['High']:.0f} L={row['Low']:.0f} "
                    f"C={row['Close']:.0f} V={row['Volume']:.0f} VWAP={row['VWAP']:.0f} EMA9={row['EMA9']:.0f} EMA21={row['EMA21']:.0f} RSI={row['RSI']:.1f}"
                )
        if not w2.empty:
            w2_vol = w2["Volume"].sum()
            print(
                f"  [Window 13:30-14:30 WIB (5m)] Open={w2['Open'].iloc[0]:.0f}, High={w2['High'].max():.0f}, "
                f"Low={w2['Low'].min():.0f}, Close={w2['Close'].iloc[-1]:.0f}, Vol={w2_vol/1e6:.2f}M, "
                f"RSI_range={w2['RSI'].min():.1f}-{w2['RSI'].max():.1f}"
            )
            for ts, row in w2.iterrows():
                print(
                    f"    {ts.strftime('%H:%M')}: O={row['Open']:.0f} H={row['High']:.0f} L={row['Low']:.0f} "
                    f"C={row['Close']:.0f} V={row['Volume']:.0f} VWAP={row['VWAP']:.0f} EMA9={row['EMA9']:.0f} EMA21={row['EMA21']:.0f} RSI={row['RSI']:.1f}"
                )


if __name__ == "__main__":
    run_scalping_audit()
