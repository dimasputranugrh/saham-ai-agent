import math
from typing import Any, Optional
import pandas as pd
import numpy as np

import config

# Pengelompokan Kode Broker Populer di Bursa Efek Indonesia (BEI / IDX)
BROKER_ASING_INSTITUSI = {
    "AK": "UBS Sekuritas",
    "BK": "J.P. Morgan Sekuritas",
    "CS": "Credit Suisse / CGS-CIMB",
    "KZ": "CLSA Sekuritas",
    "RX": "Macquarie Sekuritas",
    "ZP": "Maybank Sekuritas",
    "CG": "Citigroup Sekuritas",
    "DP": "DBS Vickers Sekuritas",
    "MS": "Morgan Stanley",
}

BROKER_RITEL_DOMESTIK = {
    "YP": "Mirae Asset Sekuritas (Ritel Terbesar)",
    "PD": "Indo Premier Sekuritas (IPOT)",
    "XC": "Ajaib Sekuritas (Ritel Milenial)",
    "XL": "Stockbit Sekuritas",
    "NI": "BNI Sekuritas (Ritel)",
    "SQ": "BCA Sekuritas (Ritel)",
    "KK": "Phillip Sekuritas",
    "MG": "Semesta Indovest (Bandar Scalper Kilat)",
}

BROKER_BUMN_INSTITUSI_LOKAL = {
    "OD": "BRI Danareksa Sekuritas (BUMN)",
    "DX": "Bahana Sekuritas (BUMN)",
    "LG": "Trimegah Sekuritas",
    "RO": "NISP Sekuritas",
}


def analyze_bandarmologi_footprint(
    ticker: str,
    df_daily: pd.DataFrame,
    cmf_val: float = 0.0,
    vol_ratio: float = 1.0,
) -> dict[str, Any]:
    """
    Menganalisis jejak Bandarmologi & Konsentrasi Aliran Dana di Bursa Efek Indonesia (BEI).
    Menggabungkan Price-Volume Wyckoff, Chaikin Money Flow (CMF), dan proksi konsentrasi Top Broker.
    """
    clean_ticker = ticker.upper().replace(".JK", "")
    sector = config.SECTOR_MAP.get(ticker.upper(), "OTHER")

    if df_daily.empty or len(df_daily) < 10:
        return {
            "status": "NETRAL",
            "bandar_action": "NETRAL (Data Terbatas)",
            "top_broker_concentration_pct": 50.0,
            "foreign_flow_label": "Netral",
            "summary": "Data transaksi harian belum cukup untuk memetakan konsentrasi bandar.",
            "top_buyers_estimate": ["Asing", "Institusi"],
            "top_sellers_estimate": ["Ritel Domestik"],
            "data_basis": "PROXY_CMF_CLV_VOLUME",
            "proxy_note": "Estimasi dari harga/volume; bukan data broker summary real-time.",
        }

    last_bars = df_daily.iloc[-5:]
    close = float(last_bars["Close"].iloc[-1])
    open_p = float(last_bars["Open"].iloc[-1])
    high_p = float(last_bars["High"].iloc[-1])
    low_p = float(last_bars["Low"].iloc[-1])
    range_p = max(1.0, high_p - low_p)

    # Menghitung rasio penutupan candle terhadap rentang harian (Close Location Value)
    clv = ((close - low_p) - (high_p - close)) / range_p

    # Proksi Konsentrasi Top 3 Broker berbasis CMF & Volume Spike
    # Di BEI: Akumulasi sejati terjadi saat CMF > 0 dan candle ditutup di 40% atas rentang
    base_concentration = 52.0 + (cmf_val * 110.0)
    if vol_ratio > 1.3:
        base_concentration += min(15.0, (vol_ratio - 1.0) * 8.0)
    top3_concentration = round(max(30.0, min(88.0, base_concentration)), 1)

    is_bank_bluechip = sector == "FINANCE" or clean_ticker in {"BBCA", "BBRI", "BMRI", "BBNI"}

    if cmf_val >= 0.07 and clv >= 0.20:
        status = "AKUMULASI BESAR (Big Money / Asing)"
        bandar_action = "AKUMULASI MASIF"
        foreign_label = "Foreign & Institutional Inflow Kuat"
        top_buyers = ["AK (UBS)", "BK (JPMorgan)", "ZP (Maybank)"]
        top_sellers = ["YP (Mirae)", "PD (IPOT)", "XC (Ajaib)"]
        summary = (
            f"(Proxy CMF/CLV) Terdeteksi Akumulasi Masif dari broker asing/institusi. "
            f"Konsentrasi Top 3 Broker mencapai {top3_concentration}% barang. "
            f"Ritel terlihat banyak melepas barang (jual) ke tangan institusi."
        )
    elif cmf_val >= 0.02 or (clv >= 0.40 and vol_ratio >= 1.2):
        status = "AKUMULASI RINGAN (Koleksi Bertahap)"
        bandar_action = "AKUMULASI SEDANG"
        foreign_label = "Inflow Terpantau"
        top_buyers = ["OD (Danareksa)", "LG (Trimegah)", "CS (CGS-CIMB)"]
        top_sellers = ["YP (Mirae)", "XL (Stockbit)"]
        summary = (
            f"Bandar mengumpulkan barang bertahap di area support/VWAP. "
            f"Konsentrasi Top 3 Broker {top3_concentration}%, tekanan jual mulai reda."
        )
    elif cmf_val <= -0.07 or (is_bank_bluechip and cmf_val <= -0.04):
        status = "DISTRIBUSI MASIF (Guyuran Asing / Big Player)"
        bandar_action = "DISTRIBUSI BESAR"
        foreign_label = "Foreign Outflow / Guyuran Asing"
        top_buyers = ["YP (Mirae)", "XC (Ajaib)", "PD (IPOT)"]
        top_sellers = ["AK (UBS)", "BK (JPMorgan)", "RX (Macquarie)"]
        summary = (
            f"(Proxy CMF/CLV) WASPADA: Distribusi Masif! Broker asing/institusi giat membuang barang ke pasar ritel. "
            f"Konsentrasi penjualan tinggi, hindari menangkap pisau jatuh sampai aksi guyur mereda."
        )
    elif cmf_val <= -0.02 or clv <= -0.30:
        status = "DISTRIBUSI RINGAN (Tekanan Jual)"
        bandar_action = "DISTRIBUSI RINGAN"
        foreign_label = "Outflow Ringan"
        top_buyers = ["Ritel Campuran"]
        top_sellers = ["Institusi Lokal / Asing"]
        summary = (
            f"Tekanan jual moderat terdeteksi. Bandar belum berniat menaikkan harga hari ini."
        )
    else:
        status = "NETRAL / KONSOLIDASI (Tukar Barang)"
        bandar_action = "NETRAL"
        foreign_label = "Netral Berimbang"
        top_buyers = ["Pasar Campuran"]
        top_sellers = ["Pasar Campuran"]
        summary = "Aliran dana dan transaksi broker berimbang, saham sedang dalam fase *sideways* menunggu katalis."

    return {
        "ticker": clean_ticker,
        "status": status,
        "bandar_action": bandar_action,
        "top_broker_concentration_pct": top3_concentration,
        "foreign_flow_label": foreign_label,
        "top_buyers_estimate": top_buyers,
        "top_sellers_estimate": top_sellers,
        "summary": summary,
        "chaikin_money_flow": round(cmf_val, 3),
        "volume_surge_ratio": round(vol_ratio, 2),
        "data_basis": "PROXY_CMF_CLV_VOLUME",
        "proxy_note": "Estimasi dari CMF/CLV/volume; bukan data broker summary real-time.",
    }
