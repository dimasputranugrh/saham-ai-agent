# 🤖 Saham AI Agent — Persistent Memory, Self-Learning, & Quantitative IDX Trading System

Sistem **Multi-Agent AI Saham Indonesia (BEI/IDX)** yang dilengkapi dengan **Persistent SQLite Memory (WAL Mode)**, **Immutable Prediction Audit Trail**, **Chronological Zero-Leakage Outcome Evaluator**, **Bayesian Confidence Calibration**, dan **Controlled Out-of-Sample Strategy Improvement**.

---

## 🏗️ 1. Arsitektur Akhir (End-to-End Architecture)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     DATA LAYER (yfinance + Google News RSS)                  │
│  • OHLCV Daily (1d) & Intraday (15m / 5m / 1m) + IHSG (^JKSE) Regime         │
│  • Kalkulasi Matematis: VWAP, EMA 9/20/21/50, SMA200, RSI, MACD, ATR, Tick   │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│               RETRIEVAL & CALIBRATION LAYER (memory/retrieval.py)            │
│  • Query Terstruktur: Pelajaran Strategi (VALIDATED/DEGRADED), Riwayat       │
│    Saham Sama, Rezim IHSG Sebanding, & Kesalahan Masa Lalu (Loss/Ambigu)     │
│  • Kalibrasi Confidence: Bayesian Beta-Binomial Shrinkage + Penalti Degradasi│
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│         MULTI-AGENT ANALYSIS & DECISION PIPELINE (agents/team.py)            │
│  • Pemisahan Epistemik: Fakta Terukur vs Interpretasi vs Asumsi Biaya        │
│  • Bukti Pendukung vs Bukti Penentang + Downgrade Otomatis BUY -> WAIT       │
│    bila Setup Terdegradasi atau Spread > Ambang Batas                        │
│  • Pencatatan Prediksi Immutable ke SQLite SEBELUM Hasil Aktual Diketahui    │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│     AUTOMATIC LEARNING LOOP & OUTCOME EVALUATOR (memory/evaluator.py)        │
│  • Evaluasi Kronologis Ketat (Hanya Bar > bar_cutoff_timestamp)              │
│  • Deteksi Order Ambigu (AMBIGUOUS_BAR_ORDER jika TP & SL kena di 1 candle)  │
│  • Perhitungan Net Return (Kotor - Fee Beli 0.15% - Fee Jual 0.25% - Slippage│
│  • Pembaruan strategy_lessons & Uji Out-of-Sample (Train 60% / OOS 40%)      │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 🗄️ 2. Skema Database Persistent Memory (`data/agent_memory.db`)

Database menggunakan **SQLite dengan mode `WAL` (`Write-Ahead Logging`)** dan `PRAGMA foreign_keys = ON`. Skema dikelola melalui tabel `schema_migrations`:

1. **`market_snapshots`**
   - Menyimpan kondisi pasar saat analisis dibuat: `snapshot_id`, `captured_at_wib`, `timezone`, `ticker`, `timeframe`, `last_bar_timestamp`, `price`, `open_price`, `high_price`, `low_price`, `volume`, `vwap`, `ema9`, `ema21`, `ema20`, `ema50`, `sma200`, `rsi`, `macd_hist`, `atr`, `vol_ratio`, `ihsg_close`, `ihsg_change_pct`, `ihsg_regime`, `sector`, `tick_size`, `spread_pct`, `order_book_available`, `data_source`, `data_is_valid`, `validation_notes`.
2. **`analysis_history` (Immutable Prediction Audit Trail)**
   - Dilindungi oleh SQLite Trigger `trg_analysis_history_immutable_update` dan `trg_analysis_history_immutable_delete` sehingga prediksi awal **tidak dapat diubah atau dihapus** setelah hasil aktual diketahui.
   - Kolom utama: `analysis_id`, `snapshot_id`, `created_at_wib`, `bar_cutoff_timestamp`, `ticker`, `timeframe`, `direction` (`BUY`/`SELL`/`WAIT`/`AVOID`), `execution_mode` (`PAPER`/`BACKTEST`/`LIVE`), `strategy_name`, `setup_type`, `ihsg_regime`, `technical_facts_json`, `interpretations_json`, `assumptions_json`, `supporting_evidence_json`, `opposing_evidence_json`, `entry_low`, `entry_high`, `stop_loss`, `take_profit_1`, `take_profit_2`, `horizon_bars`, `evaluate_after_wib`, `estimated_risk_pct`, `estimated_gross_return_pct`, `estimated_net_return_pct`, `raw_quant_score`, `calibrated_confidence`, `confidence_basis`, `invalidation_conditions`, `model_version`, `prompt_version`, `strategy_version`, `memory_ids_used_json`.
3. **`prediction_outcomes`**
   - Memiliki constraint `UNIQUE(analysis_id)` untuk menjamin evaluasi bersifat **idempoten** (anti-duplikasi).
   - Kolom utama: `outcome_id`, `analysis_id`, `evaluated_at_wib`, `evaluation_status` (`RESOLVED_WIN_TP1`, `RESOLVED_WIN_TP2`, `RESOLVED_LOSS_SL`, `RESOLVED_TIME_EXIT`, `AMBIGUOUS_BAR_ORDER`, `EXPIRED_NO_FILL`, `SKIPPED_WAIT`), `entry_filled`, `entry_fill_price`, `exit_price`, `gross_return_pct`, `net_return_pct`, `fee_buy_pct`, `fee_sell_pct`, `slippage_pct`, `duration_minutes`, `is_ambiguous`, `resolution_notes`.
4. **`strategy_lessons`**
   - Menyimpan agregasi performa per `(strategy_name, strategy_version, setup_type, timeframe, ihsg_regime, ticker_scope, execution_mode)`: `sample_size`, `resolved_trades`, `ambiguous_trades`, `win_rate`, `avg_win_net_pct`, `avg_loss_net_pct`, `expectancy_net_pct`, `profit_factor`, `max_drawdown_pct`, `uncertainty_level`, serta memisahkan `measured_facts_json`, `hypothesis_text`, `ai_interpretation_text`, dan `validation_status` (`CANDIDATE`, `VALIDATED`, `DEGRADED`, `REJECTED`).
5. **`strategy_versions`**
   - Menyimpan riwayat versi parameter strategi, hipotesis, ukuran sampel *Train* vs *Out-of-Sample (OOS)*, perbandingan *expectancy* dan *drawdown* terhadap *baseline*, serta mendukung **Rollback instan**.

---

## 📁 3. Daftar File yang Dibuat & Diubah

| File | Status | Deskripsi |
| :--- | :--- | :--- |
| `memory/__init__.py` | Baru | Inisialisasi paket *persistent memory & self-learning*. |
| `memory/database.py` | Baru | Manajer koneksi SQLite WAL, migrasi skema, trigger immutability, validasi data, serta online backup & restore. |
| `memory/evaluator.py` | Baru | Mesin evaluasi hasil prediksi kronologis (anti *data leakage*, deteksi candle ambigu, potongan fee & slippage, agregasi `strategy_lessons`). |
| `memory/retrieval.py` | Baru | Pengambilan memori relevan terstruktur & kalibrasi *confidence* Bayesian. |
| `memory/performance.py` | Baru | Kalkulator metrik performa (Win Rate, Expectancy, Profit Factor, Max Drawdown, Brier Score) & *Controlled Strategy Improvement* (Train/OOS + Rollback). |
| `memory/learning_loop.py` | Baru | Orkestrator siklus pembelajaran otomatis 11-langkah & *Walk-Forward Historical Backtester*. |
| `tests/test_memory_learning.py` | Baru | 11 pengujian otomatis (`unittest`) mencakup seluruh aspek memori, immutability, anti-leakage, dan keamanan Paper Trading. |
| `analyzer/technical.py` | Diperbarui | Menambahkan klasifikasi setup, *spread tick* BEI, pemisahan fakta/interpretasi/asumsi, bukti pendukung vs penentang, dan rezim IHSG. |
| `analyzer/scalping_sim.py` | Baru | Modul audit intraday 1m & 5m untuk simulasi scalping BEI. |
| `agents/team.py` | Diperbarui | Mengintegrasikan *Memory Retrieval* & *Learning Loop* ke dalam DSU, `/cek`, dan `/scan`. |
| `bot/telegram_bot.py` | Diperbarui | Menambahkan perintah `/evaluasi`, `/performa`, `/memori`, serta jadwal evaluasi otomatis (`12:05` & `16:30 WIB`). |
| `broker/stockbit.py` | Diperbarui | Menambahkan proteksi *Default Paper Trading Safety Guard* (`ALLOW_LIVE_BROKER_EXECUTION=false`). |
| `config.py` & `cli_demo.py` | Diperbarui | Menambahkan konfigurasi database, biaya transaksi, serta CLI untuk evaluasi, walk-forward, backup, dan restore. |

---

## ⚙️ 4. Instalasi & Konfigurasi Environment

### Instalasi Dependency
```bash
cd /home/dimas/projects/saham-ai-agent
.venv/bin/pip install -r requirements.txt
```

### Konfigurasi `.env`
- `GEMINI_API_KEY`: API Key Google AI Studio.
- `GEMINI_MODEL`: Default `gemini-3.6-flash` (dengan auto-fallback).
- `TELEGRAM_BOT_TOKEN` & `TELEGRAM_CHAT_ID`: Kredensial Bot Telegram.
- `EXECUTION_MODE`: Default `PAPER` (Jangan ubah ke `LIVE` kecuali ingin eksekusi sungguhan).
- `ALLOW_LIVE_BROKER_EXECUTION`: Default `false` (Sabuk pengaman agar agent tidak mengirim order broker sungguhan).
- `FEE_BUY_PCT=0.15`, `FEE_SELL_PCT=0.25`, `DEFAULT_SLIPPAGE_PCT=0.10`.

---

## 🚀 5. Cara Menjalankan Agent, Evaluasi, Backup, & Pengujian

### A. Menjalankan Bot Telegram & Scheduler Otomatis
```bash
.venv/bin/python main.py
```

### B. Menjalankan Evaluasi Hasil Prediksi & Walk-Forward Learning via CLI
```bash
# 0. Latihan walk-forward otomatis juga berjalan setiap Sabtu 08:00 WIB lewat GitHub Actions (mode train)
# 1. Jalankan Walk-Forward Backtest & Learning Loop pada data historis
.venv/bin/python cli_demo.py walkforward

# 2. Lihat Dashboard Evaluasi Performa (Win Rate, Expectancy, Profit Factor, Brier Score)
.venv/bin/python cli_demo.py evaluasi

# 3. Lihat Memori Historis & Kalibrasi Confidence untuk 1 Saham
.venv/bin/python cli_demo.py memori TLKM

# 4. Bedah Saham Lengkap dengan Injeksi Memori
.venv/bin/python cli_demo.py cek BBCA
```

### C. Cara Backup & Restore Database Memory
```bash
# Membuat backup online yang aman (tersimpan di data/backups/)
.venv/bin/python cli_demo.py backup

# Melakukan restore dari file backup
.venv/bin/python cli_demo.py restore data/backups/agent_memory_backup_YYYYMMDD_HHMMSS.db
```

### D. Menjalankan Pengujian Otomatis (Unit Tests)
```bash
.venv/bin/python -m unittest discover -s tests -v
```

### E. Aturan Same-Session Learning
- Satu prediksi = satu sesi bursa. Evaluasi memakai tanggal `created_at_wib`, sehingga prediksi DSU pre-market tetap dinilai pada bar hari itu, bukan bar kemarin.
- Tidak ada evaluasi overnight/weekend. Posisi yang belum kena TP/SL ditutup paksa di bar terakhir sesi.
- BUY baru ditahan menjadi `WAIT` jika sisa bar intraday tidak cukup untuk horizon penuh (dan walk-forward melewati sampel tersebut).
- Pelajaran strategi, kalibrasi confidence, dan laporan performa hanya memakai outcome yang tanggal buat, fill, dan exit-nya sama. Baris lama yang overnight tetap disimpan untuk audit, tetapi tidak dipakai untuk belajar.

---

## ⚠️ 6. Batasan Data & Fitur yang Memerlukan Konfigurasi Manual

1. **Keterbatasan Data Order Book Level 2 (`yfinance`)**:
   - Sumber data publik `yfinance` menyediakan *candlestick* OHLCV `1m`, `5m`, `15m`, dan `1d` namun **tidak menyediakan antrean Bid/Ask Level 2 secara *real-time* maupun urutan *tick-by-tick* di dalam satu candle**.
   - Oleh karena itu, kolom `order_book_available` dicatat secara jujur sebagai `0`, *spread* dihitung dari aturan Fraksi Harga BEI (*Tick Size*), dan setiap candle di mana *High* menyentuh *Take Profit* sekaligus *Low* menyentuh *Stop Loss* wajib ditandai sebagai **`AMBIGUOUS_BAR_ORDER`** (tidak pernah diklaim sebagai kemenangan palsu).
2. **Integrasi Eksekusi Broker (`broker/stockbit.py`)**:
   - Secara default dikunci pada mode **`PAPER`** (`ALLOW_LIVE_BROKER_EXECUTION=false`). Jika suatu saat pengguna ingin mengaktifkan eksekusi riil, pengguna harus menjalankan `login_stockbit.py` secara manual dan mengubah konfigurasi `.env` secara eksplisit.
