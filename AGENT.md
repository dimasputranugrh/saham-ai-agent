# AGENT PROJECT CONTEXT: SAHAM-AI-AGENT

> **File Referensi Otomatis untuk AI Assistant (Antigravity CLI / Cursor / Claude)**  
> Dibuat khusus untuk Bos Dimas agar setiap sesi baru langsung memahami seluruh arsitektur, riwayat keputusan, dan konfigurasi project tanpa perlu dijelaskan ulang.

---

## 1. Ringkasan & Visi Project
Project ini adalah **AI Stock Agent untuk Saham Indonesia (BEI/IDX)** dengan fitur:
- **Multi-Horizon:** Bukan hanya *scalping* cepat (intraday 15m/VWAP), tetapi juga **Swing & Investasi Masa Depan** berbasis katalis berita dan tren harian.
- **Bahasa Laporan:** Selalu gunakan **"Bahasa Bayi"** (bahasa sehari-hari yang sangat mudah dipahami pemula tanpa jargon rumit), namun di belakang layar perhitungan matematika dan logikanya 100% disiplin kuantitatif.
- **Mode Eksekusi:** Wajib selalu default ke **`PAPER` (Simulasi / Tanpa Uang Asli)** selama masa pengujian. Dilarang mengubah ke live broker tanpa otorisasi eksplisit Bos Dimas.
- **Biaya Transaksi BEI:** Fee beli 0.15%, fee jual 0.25%, slippage 0.10% (Total potongan 0.40% wajib selalu diperhitungkan dalam return bersih).

---

## 2. Struktur Tim 5 AI + 1 Supreme Arbiter (Ensemble Consensus)
Analisis saham tidak hanya mengandalkan 1 AI, melainkan melalui sidang panel 5 AI lintas perusahaan:

1. **`AI_1` — Momentum Scalper:** `gemini-3.6-flash` (Google) $\rightarrow$ Fokus lonjakan volume intraday & VWAP.
2. **`AI_2` — Risk & Trap Auditor:** `openai/gpt-oss-120b` via Groq (OpenAI 120B) $\rightarrow$ Mengaudit risiko jebakan bandar (*bull trap*) & spread.
3. **`AI_3` — Bandar & Aliran Dana:** `nvidia/nemotron-3-ultra-550b-a55b:free` via OpenRouter (NVIDIA 550B) $\rightarrow$ Membaca akumulasi bandar.
4. **`AI_4` — Trend & Swing Guard:** `qwen/qwen3.8-27b` via Groq (Alibaba Qwen 3.8) $\rightarrow$ Menjaga keselarasan tren harian & Risk/Reward.
5. **`AI_5` — Quant Bayesian Memory:** `quant-bayesian-v1` (Lokal Python) $\rightarrow$ Murni rumus matematika & database memori tanpa bias LLM.
6. **Chief Arthur (Supreme Decider / Final Arbiter):** Menghitung suara setuju (`buy_count / 5`) dan persentase kelayakan (`% Works`), lalu memutuskan **BUY** (jika $\ge 3$ AI setuju dan $\ge 60\%$ Works) atau **WAIT**.
7. **Tim DSU Harian:** Bastian (Macro Intel), Serena (Market Screener), Damian (Chief Risk Officer), dan Chief Arthur.

---

## 3. Persistent SQLite Memory (`data/agent_memory.db`)
Database SQLite berjalan dalam mode WAL dengan 9 tabel terintegrasi:
1. `market_snapshots`: Rekam kondisi harga, volume, VWAP, RSI, MACD, spread saat analisis dibuat.
2. `analysis_history`: Rekam prediksi awal (Entry, TP1, TP2, SL) yang bersifat **immutable** (tidak boleh diubah setelah dibuat).
3. `prediction_outcomes`: Rekam hasil nyata setelah horizon waktu selesai (Win TP, Loss SL, Ambiguous Bar Order).
4. `strategy_lessons`: Pelajaran statistik (Win Rate, Profit Factor, Expectancy) per setup dan rezim IHSG.
5. `strategy_versions`: Parameter strategi aktif dan riwayat perbaikan out-of-sample / rollback.
6. `ai_panel_registry`: Konfigurasi slot 5 AI aktif (bisa diganti lewat `/ganti_ai`).
7. `ai_panel_votes`: Rekam suara dan akurasi masing-masing AI untuk rapor mingguan.
8. `sector_news_investigations`: Rekam hasil investigasi perbandingan 30+ artikel berita 7 sektor BEI.
9. `conversation_knowledge_log`: Rekam seluruh aturan dari Bos Dimas dan tanya-jawab Telegram.

---

## 4. Radar Berita Lintas 7 Sektor & Hukum Sebab-Akibat
File: [`analyzer/news.py`](file:///home/dimas/projects/saham-ai-agent/analyzer/news.py)
- **Aturan Wajib:** Jangan terpaku pada 1-2 artikel; selalu bandingkan puluhan artikel dari berbagai media keuangan (Kontan, Bisnis.com, CNBC Indonesia, Bloomberg Technoz, Investor.id, Detik).
- **Hukum Sebab-Akibat:**
  - *Cukai Rokok:* Cukai naik tinggi $\rightarrow$ HMSP, GGRM, WIIM tertekan; Cukai ditahan/batal naik $\rightarrow$ HMSP, GGRM, WIIM berpeluang naik (akumulasi dividen/swing).
  - *Suku Bunga BI Rate:* Turun/kredit tumbuh $\rightarrow$ Bank (BBCA, BBRI, BMRI, BBNI, BRIS) naik.
  - *Energi/Batu Bara/Minyak:* Harga komoditas dunia naik $\rightarrow$ ADRO, PTBA, ITMG, MEDC, PGAS panen laba.
  - *Tambang Emas/Logam:* Emas cetak rekor / hilirisasi EV $\rightarrow$ ANTM, BRMS, MDKA, AMMN diuntungkan.
  - *Konsumer/Ritel/Ayam:* Daya beli naik / makan bergizi gratis $\rightarrow$ ICBP, INDF, AMRT, JPFA, CPIN positif.
  - *Properti & Otomotif:* Insentif PPN DTP bebas pajak $\rightarrow$ BSDE, CTRA, SMRA, ASII positif.
  - *Telko & EBT:* Data center AI & energi hijau $\rightarrow$ TLKM, ISAT, EXCL, BREN positif.

---

## 5. Arsitektur Router Model AI Telegram vs Terminal CLI
File: [`agents/dev_architect.py`](file:///home/dimas/projects/saham-ai-agent/agents/dev_architect.py)
- **Di Terminal Antigravity CLI:** Bos Dimas bebas memakai **Gemini 4 Argon** atau Claude untuk ngoding berat.
- **Di Telegram (`/agy` dan `/upgrade`):**
  - **Saat Laptop Nyala (WSL):** Dijalankan via Antigravity CLI menggunakan **Gemini 3.8 Flash** dengan *Effort Routing* otomatis:
    - Ringan $\rightarrow$ `gemini-3.8-flash-low`
    - Sedang $\rightarrow$ `gemini-3.8-flash-medium`
    - Berat / Upgrade $\rightarrow$ `gemini-3.8-flash-high`
    - *(Model Argon sengaja dihemat dan TIDAK dipakai untuk Telegram).*
  - **Saat Laptop Mati (GitHub Cloud):** Dijawab otomatis oleh **Gemini 3.6 Flash** atau **OpenAI 120B (Groq)**.

---

## 6. Daftar Perintah Telegram Bot (@Agent_d_saham_bot)
- `/cek <KODE>`: Bedah saham + Sidang Voting 5 AI (`% Works`) + Vonis Chief Arthur.
- `/scan`: Pindai saham yang layak dibeli jam ini.
- `/berita` atau `/sektor`: Radar perbandingan berita 7 sektor & peluang Swing Masa Depan.
- `/dsu`: Laporan rapat harian pagi (Bastian, Serena, Damian, Chief Arthur).
- `/rapor_ai`: Rapor mingguan ranking akurasi 5 AI (siapa paling jago vs siapa harus diganti).
- `/ganti_ai <SLOT> <MODEL>`: Ganti AI yang jelek dengan model gratis lain.
- `/evaluasi`: Dashboard performa strategi, Win Rate, dan Profit Factor.
- `/memori <KODE>`: Cek ingatan database pada saham tertentu.
- `/agy <tanya>`: Tanya AI Architect tentang kodingan project ini.
- `/upgrade <instruksi>`: Perintahkan AI mengedit kode project, auto-compile test, & push ke GitHub.
- `/beli` & `/pegang` & `/jual`: Pantau status jam jual saham portofolio.
- `/help` / `/menu` / `/bantuan`: Tampilkan daftar bantuan.

---

## 7. Operasional & Otomasi Sinkronisasi
- **Perintah Lokal di WSL:**
  - `saham` $\rightarrow$ Menjalankan bot interaktif (otomatis `git pull` sebelum mulai dan `git push` saat `Ctrl+C`).
  - `saham bg` $\rightarrow$ Menjalankan bot di background.
  - `saham stop` $\rightarrow$ Mematikan bot background.
  - `saham status` $\rightarrow$ Cek status bot lokal.
- **Auto-Sync WSL Startup ([.bashrc](file:///home/dimas/.bashrc)):** Setiap kali terminal WSL dibuka, otomatis melakukan background `git pull` dari GitHub.
- **GitHub Actions Cron ([jadwal_saham_otomatis.yml](file:///home/dimas/projects/saham-ai-agent/.github/workflows/jadwal_saham_otomatis.yml)):** Berjalan otomatis pada jam bursa (08:15, 09:15, 10:15, 11:30, 13:45, 14:15, 15:15, 16:15 WIB), menjalankan evaluasi, memproses chat Telegram, dan otomatis commit & push `agent_memory.db` kembali ke GitHub.
