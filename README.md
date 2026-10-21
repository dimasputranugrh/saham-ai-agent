# 🤖 Saham AI Agent — Tim Karyawan AI Analisis Saham (IHSG & Global)

Sistem **Multi-Agent AI Trading Desk** pribadi yang bekerja otomatis dari pagi hingga penutupan bursa sore hari dan melapor langsung ke **Telegram** Anda.

---

## 👥 Struktur 4 Karyawan AI Anda

1. 👨‍💻 **Budi (Quant & Technical Analyst)**
   - Menghitung indikator teknikal **Intraday (15m)** & **Daily (1D)** secara matematis menggunakan Python (`VWAP`, `EMA 9/20/21/50`, `SMA 200`, `RSI 14`, `MACD Histogram`, `Bollinger Bands`, dan `Volume Spike Ratio`).
2. 👩‍💼 **Sari (News & Macro Sentiment Analyst)**
   - Memantau kondisi **IHSG (`^JKSE`)** dan mengambil berita terbaru terkait pasar modal Indonesia maupun emiten spesifik dari Google News Indonesia.
3. 🛡️ **Hendra (Risk & Execution Manager)**
   - Menghitung titik **Support & Resistance**, **Area Beli (Entry)**, **Target Profit (TP1 & TP2)**, serta **Batas Cut Loss (Stop Loss)** berbasis **ATR (Average True Range)** yang sudah dibulatkan mengikuti aturan **Fraksi Harga Saham BEI (IDX)**.
4. 🎯 **Arif (Kepala Riset / Lead Trader)**
   - Memimpin rapat pagi **DSU (Daily Standup Update)** dan memberikan rekomendasi **Jam Eksekusi Terbaik** (*Sesi 1 Pagi* vs *Buy on Weakness* vs *JJS Sesi 2*).

---

## ⏰ Jadwal Kerja Otomatis (Senin – Jumat WIB)

| Jam (WIB) | Aktivitas Otomatis |
| :--- | :--- |
| **08:15 WIB** | 📋 **Morning DSU (Daily Standup Update)** — Laporan persiapan sebelum pasar buka jam 09:00. |
| **09:15, 10:00, 11:00 WIB** | 🚨 **Scanner Sesi 1 ("Beli Jam Segini")** — Mengirim alert ke Telegram jika ada saham di watchlist yang menembus skor kuantitatif & lonjakan volume. |
| **13:45, 14:30, 15:30 WIB** | 🚨 **Scanner Sesi 2 & JJS** — Memantau peluang sesi siang/sore menjelang penutupan. |
| **16:15 WIB** | 🔔 **Evaluasi Penutupan Pasar (Closing Wrap)** — Ringkasan akhir hari & persiapan Swing besok. |

---

## 🚀 Cara Menjalankan (3 Langkah Mudah)

### Langkah 1: Siapkan Kunci API di File `.env`
Buka file `.env` lalu isi 3 baris berikut:
1. **`GEMINI_API_KEY`**:
   - Buka [Google AI Studio](https://aistudio.google.com/app/apikey), login akun Google Anda, lalu klik **Create API Key** (Gratis).
2. **`TELEGRAM_BOT_TOKEN`**:
   - Buka aplikasi Telegram, cari **`@BotFather`** (centang biru).
   - Ketik `/newbot`, beri nama bot Anda (misal: `Asisten Saham Bos`), lalu beri username berakhiran `bot` (misal: `saham_bos_ai_bot`).
   - Salin **HTTP API Token** yang diberikan `@BotFather` ke `TELEGRAM_BOT_TOKEN`.
3. **`TELEGRAM_CHAT_ID`**:
   - Jalankan bot terlebih dahulu, lalu buka bot Anda di Telegram dan ketik `/start`.
   - Bot akan langsung menampilkan angka **Telegram Chat ID** Anda. Salin angka tersebut ke `TELEGRAM_CHAT_ID` di `.env`.

---

### Langkah 2: Uji Coba Langsung di Terminal (Tanpa Telegram Sekalipun!)
Anda bisa langsung mengetes kecerdasan 4 karyawan AI Anda sekarang juga lewat terminal:

```bash
cd /home/dimas/projects/saham-ai-agent

# 1. Tes Rapat Pagi DSU
.venv/bin/python cli_demo.py dsu

# 2. Tes Scanner "Beli Jam Segini"
.venv/bin/python cli_demo.py scan

# 3. Tes Bedah Lengkap 1 Saham (Contoh: BBCA, ANTM, BREN, TLKM)
.venv/bin/python cli_demo.py cek BBCA
```

---

### Langkah 3: Jalankan Bot Telegram & Jadwal Otomatis
Untuk menyalakan di komputer saat ini:
```bash
cd /home/dimas/projects/saham-ai-agent
.venv/bin/python main.py
```

#### Menjalankan 24/7 di VPS / Background dengan Docker (Agar Laptop Tidak Perlu Nyala Terus)
Jika Anda sudah menyewa VPS murah (atau menjalankan Docker di server), cukup jalankan 1 perintah ini:
```bash
docker compose up -d --build
```
Aplikasi akan berjalan terus di latar belakang (`restart: unless-stopped`) dan otomatis bangun sesuai jadwal WIB!
