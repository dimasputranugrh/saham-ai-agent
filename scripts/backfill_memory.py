#!/usr/bin/env python3
"""
scripts/backfill_memory.py

Backfill database memori agen saham dengan data historis intraday LQ45.
Menggunakan mode BACKTEST dengan validasi same-session, batas cutoff sore 14:00,
dan zero future data leakage.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Set working directory ke root repo
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import config
from memory.database import MemoryDatabase
from memory.learning_loop import LearningLoopOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BackfillMemory")


def load_tickers_from_watchlist() -> list[str]:
    wl_path = config.WATCHLIST_FILE
    if wl_path.exists():
        try:
            with open(wl_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return [str(t).strip().upper() for t in data if t]
        except Exception as e:
            logger.warning(f"Gagal baca watchlist: {e}")
    return ["BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "ANTM.JK"]


def main():
    parser = argparse.ArgumentParser(description="Backfill memory database with historical intraday data.")
    parser.add_argument(
        "--period",
        type=str,
        default="60d",
        help="Periode data intraday yfinance (maksimal 60d untuk 15m). Default: 60d",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="15m",
        help="Timeframe candle. Default: 15m",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=6,
        help="Horizon evaluasi (jumlah bar). Default: 6 bar (90 menit)",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="Daftar ticker spesifik (misal BBCA.JK BBRI.JK). Default: ambil dari data/watchlist.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batasi jumlah ticker yang diproses.",
    )

    args = parser.parse_args()

    tickers = args.tickers or load_tickers_from_watchlist()
    if args.limit:
        tickers = tickers[: args.limit]

    logger.info(f"Memulai backfill memori untuk {len(tickers)} ticker: {', '.join(tickers)}")
    logger.info(f"Parameter: period={args.period}, timeframe={args.timeframe}, horizon={args.horizon} bar")

    db = MemoryDatabase(config.MEMORY_DB_PATH)
    orchestrator = LearningLoopOrchestrator(db)

    # Catat data awal
    with db.connect() as conn:
        before_pred = conn.execute("SELECT COUNT(*) FROM analysis_history").fetchone()[0]
        before_out = conn.execute("SELECT COUNT(*) FROM prediction_outcomes").fetchone()[0]
        before_lessons = conn.execute("SELECT COUNT(*) FROM strategy_lessons").fetchone()[0]

    # Jalankan walk-forward backtest
    results = orchestrator.run_walk_forward_backtest(
        tickers=tickers,
        timeframe=args.timeframe,
        horizon_bars=args.horizon,
        period=args.period,
        full_history=True,
    )

    # Catat data akhir
    with db.connect() as conn:
        after_pred = conn.execute("SELECT COUNT(*) FROM analysis_history").fetchone()[0]
        after_out = conn.execute("SELECT COUNT(*) FROM prediction_outcomes").fetchone()[0]
        after_lessons = conn.execute("SELECT COUNT(*) FROM strategy_lessons").fetchone()[0]

    logger.info("=== HASIL BACKFILL HISTORIS ===")
    logger.info(f"Prediksi baru dibuat: {results.get('walk_forward_predictions_created', 0)} (Total di DB: {after_pred}, bertambah {after_pred - before_pred})")
    logger.info(f"Trade baru dievaluasi: {results.get('walk_forward_outcomes_evaluated', 0)} (Total di DB: {after_out}, bertambah {after_out - before_out})")
    logger.info(f"Strategy lessons tervalidasi: {after_lessons} (sebelumnya: {before_lessons})")
    logger.info("Database memori berhasil diperkaya dan siap digunakan tim AI!")


if __name__ == "__main__":
    main()
