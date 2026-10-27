import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
import pytz

import config


def get_live_office_data():
    """Mengambil status real-time aktivitas & kapasitas seluruh karyawan AI."""
    db_path = config.MEMORY_DB_PATH
    tz = pytz.timezone(config.TIMEZONE)
    now_dt = datetime.now(tz)
    now_wib = now_dt.strftime("%d %B %Y • %H:%M:%S WIB")

    # 9 Karyawan AI dengan koordinat 3D di dalam ruang kantor
    agents = [
        {
            "id": "ARIF",
            "name": "Chief Arthur (Supreme Decider)",
            "role": "Chief Investment Arbiter & Consensus",
            "model": "Ensemble Judge (>=3 Buy & >=60%)",
            "color": "#a855f7",
            "hex": 0xa855f7,
            "pos": [0, 0, -3.8],
            "status": "DECIDING",
            "capacity": 85,
            "current_task": "Memimpin sidang konsensus 6 AI saham",
            "speech": "Sidang panel 6 AI dibuka. Semua rekomendasi wajib diuji % Works & konsensus.",
            "total_tasks": 0,
            "desk_type": "executive",
            "hair_color": 0x334155,
            "skin_tone": 0xfed7aa,
        },
        {
            "id": "AI_1",
            "name": "AI-1 Gemini Scalper",
            "role": "Momentum & VWAP Scalper",
            "model": "Google Gemini 3.6 Flash",
            "color": "#06b6d4",
            "hex": 0x06b6d4,
            "pos": [-4.5, 0, -1],
            "status": "WORKING",
            "capacity": 90,
            "current_task": "Menghitung lonjakan volume 15m & posisi VWAP",
            "speech": "Volume intraday spike terdeteksi! Mengecek kekuatan pembeli di atas VWAP.",
            "total_tasks": 0,
            "desk_type": "standard",
            "hair_color": 0x1e293b,
            "skin_tone": 0xfde047,
        },
        {
            "id": "AI_5",
            "name": "AI-5 Quant Bayesian",
            "role": "Quant Math & Bayesian Prob",
            "model": "Quant Bayesian v1 (Python)",
            "color": "#3b82f6",
            "hex": 0x3b82f6,
            "pos": [-4.5, 0, 2],
            "status": "WORKING",
            "capacity": 80,
            "current_task": "Komputasi matriks bayesian & fee BEI 0.40%",
            "speech": "Probabilitas matematika dihitung murni dari rekaman memori historis.",
            "total_tasks": 0,
            "desk_type": "standard",
            "hair_color": 0x475569,
            "skin_tone": 0xfed7aa,
        },
        {
            "id": "AI_2",
            "name": "AI-2 OpenAI 120B Auditor",
            "role": "Risk & Trap Guard",
            "model": "OpenAI GPT-OSS 120B (Groq)",
            "color": "#f43f5e",
            "hex": 0xf43f5e,
            "pos": [4.5, 0, -1],
            "status": "AUDITING",
            "capacity": 75,
            "current_task": "Audit potensi jebakan pucuk (bull trap) & spread",
            "speech": "Waspada! Jangan buru-buru hajar kanan jika spread bid-offer terlalu tipis.",
            "total_tasks": 0,
            "desk_type": "standard",
            "hair_color": 0x0f172a,
            "skin_tone": 0xfbcfe8,
        },
        {
            "id": "AI_4",
            "name": "AI-4 Qwen 3.8 Trend",
            "role": "Trend Alignment & Swing",
            "model": "Alibaba Qwen 3.8 27B (Groq)",
            "color": "#f59e0b",
            "hex": 0xf59e0b,
            "pos": [4.5, 0, 2],
            "status": "WORKING",
            "capacity": 70,
            "current_task": "Validasi tren EMA20/EMA50 & rasio R:R 1:2",
            "speech": "Tren harian selaras. Posisi support kuat dan Risk/Reward di atas 1:2.",
            "total_tasks": 0,
            "desk_type": "standard",
            "hair_color": 0x292524,
            "skin_tone": 0xfed7aa,
        },
        {
            "id": "AI_3",
            "name": "AI-3 Gemini 3.8 Reasoning & Flow",
            "role": "Smart Money & Flow Tracer",
            "model": "Google Gemini 3.8 Flash",
            "color": "#10b981",
            "hex": 0x10b981,
            "pos": [4.5, 0, 5],
            "status": "WORKING",
            "capacity": 85,
            "current_task": "Melacak jejak akumulasi bandar, volume spike & flow",
            "speech": "Menganalisis akumulasi bandar & kekuatan aliran dana terkini.",
            "total_tasks": 0,
            "desk_type": "standard",
            "hair_color": 0x18181b,
            "skin_tone": 0xfde047,
        },
        {
            "id": "AI_6",
            "name": "AI-6 Pattern Master",
            "role": "Candlestick & Reversal Specialist",
            "model": "Google Gemini 3.5 Flash Lite",
            "color": "#818cf8",
            "hex": 0x818cf8,
            "pos": [-4.5, 0, 5],
            "status": "WORKING",
            "capacity": 85,
            "current_task": "Audit konfirmasi pola candlestick reversal & false breakout",
            "speech": "Menganalisis pola candlestick reversal & rejection wick untuk memastikan breakout valid.",
            "total_tasks": 0,
            "desk_type": "standard",
            "hair_color": 0x312e81,
            "skin_tone": 0xfed7aa,
        },
        {
            "id": "BUDI",
            "name": "Bastian (Macro Intel)",
            "role": "Head of Macro & Sector Intel",
            "model": "Daily Standup Analyst",
            "color": "#0ea5e9",
            "hex": 0x0ea5e9,
            "pos": [-1.8, 0, 2.5],
            "status": "STANDBY",
            "capacity": 30,
            "current_task": "Monitoring radar 30+ berita keuangan 7 sektor",
            "speech": "Sentimen komoditas dan arah suku bunga BI sedang dikompilasi.",
            "total_tasks": 0,
            "desk_type": "standard",
            "hair_color": 0x334155,
            "skin_tone": 0xfed7aa,
        },
        {
            "id": "HENDRA",
            "name": "Damian (Chief Risk Officer)",
            "role": "Chief Risk Officer & Capital Guard",
            "model": "Daily Standup Controller",
            "color": "#f97316",
            "hex": 0xf97316,
            "pos": [1.8, 0, 2.5],
            "status": "STANDBY",
            "capacity": 20,
            "current_task": "Menjaga batas risiko portofolio Paper Trading",
            "speech": "Semua posisi disiplin dalam batas toleransi drawdown 1.5%.",
            "total_tasks": 0,
            "desk_type": "standard",
            "hair_color": 0x1e293b,
            "skin_tone": 0xfed7aa,
        },
        {
            "id": "SARI",
            "name": "Serena (Market Screener)",
            "role": "VP of Algorithmic Screener",
            "model": "Daily Standup Screener",
            "color": "#14b8a6",
            "hex": 0x14b8a6,
            "pos": [0, 0, 5.5],
            "status": "STANDBY",
            "capacity": 25,
            "current_task": "Menyaring kandidat breakout emiten BEI",
            "speech": "Daftar pantau saham aktif hari ini sudah siap di meja.",
            "total_tasks": 0,
            "desk_type": "standard",
            "hair_color": 0x451a03,
            "skin_tone": 0xfbcfe8,
        },
    ]

    recent_logs = []
    active_analyses_count = 0
    total_votes_recorded = 0

    if Path(db_path).exists():
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Hitung total vote per AI
            cur.execute("""
                SELECT slot_id, count(*) as cnt, MAX(created_at_wib) as last_seen
                FROM ai_panel_votes
                GROUP BY slot_id
            """)
            vote_counts = {r["slot_id"]: (r["cnt"], r["last_seen"]) for r in cur.fetchall()}

            # Ambil konfigurasi model aktif terbaru dari ai_panel_registry (agar hot-swap otomatis tercermin)
            try:
                cur.execute("SELECT slot_id, ai_name, provider, model_id FROM ai_panel_registry WHERE is_active = 1")
                panel_registry = {r["slot_id"]: r for r in cur.fetchall()}
            except Exception:
                panel_registry = {}

            # Ambil suara/reasoning terakhir per AI
            cur.execute("""
                SELECT v.*, a.direction as final_dir
                FROM ai_panel_votes v
                LEFT JOIN analysis_history a ON v.analysis_id = a.analysis_id
                WHERE v.rowid IN (
                    SELECT MAX(rowid) FROM ai_panel_votes GROUP BY slot_id
                )
            """)
            latest_votes = {r["slot_id"]: r for r in cur.fetchall()}

            total_votes_recorded = cur.execute("SELECT count(*) FROM ai_panel_votes").fetchone()[0]
            active_analyses_count = cur.execute("SELECT count(*) FROM analysis_history").fetchone()[0]

            # 10 log aktivitas voting terakhir
            cur.execute("""
                SELECT v.created_at_wib, v.ticker, v.slot_id, v.ai_name, v.vote_direction,
                       v.confidence_pct, v.reasoning_summary, a.direction as final_decision
                FROM ai_panel_votes v
                LEFT JOIN analysis_history a ON v.analysis_id = a.analysis_id
                ORDER BY v.rowid DESC
                LIMIT 10
            """)
            raw_logs = cur.fetchall()
            for r in raw_logs:
                time_str = r["created_at_wib"] or ""
                try:
                    if "T" in time_str:
                        dt = datetime.fromisoformat(time_str)
                        time_str = dt.strftime("%H:%M:%S")
                except Exception:
                    pass

                ticker_clean = (r["ticker"] or "").replace(".JK", "")
                recent_logs.append({
                    "time": time_str,
                    "ticker": ticker_clean,
                    "ai_name": r["ai_name"],
                    "vote": r["vote_direction"],
                    "confidence": f"{r['confidence_pct']:.1f}%" if r["confidence_pct"] else "-",
                    "reasoning": r["reasoning_summary"] or "",
                    "final": r["final_decision"] or "PENDING",
                })

            cur.execute("""
                SELECT ticker, direction, entry_price, take_profit_1, stop_loss, created_at_wib
                FROM analysis_history
                ORDER BY rowid DESC
                LIMIT 1
            """)
            last_analysis = cur.fetchone()

            conn.close()

            # Update per agen
            for ag in agents:
                sid = ag["id"]
                if sid in panel_registry:
                    reg = panel_registry[sid]
                    ag["name"] = reg["ai_name"]
                    ag["model"] = f"{reg['provider'].title()} {reg['model_id']}"

                if sid in vote_counts:
                    ag["total_tasks"] = vote_counts[sid][0]

                if sid in latest_votes:
                    lv = latest_votes[sid]
                    t_clean = (lv["ticker"] or "").replace(".JK", "")
                    ag["speech"] = f"[{t_clean}] {lv['reasoning_summary']}"
                    ag["current_task"] = f"Menganalisis {t_clean} ({lv['vote_direction']} • {lv['confidence_pct']:.0f}%)"
                    ag["capacity"] = min(95, 55 + (ag["total_tasks"] % 40))
                    ag["status"] = "WORKING" if lv["vote_direction"] == "BUY" else "AUDITING"

                elif sid == "ARIF":
                    ag["total_tasks"] = active_analyses_count
                    if last_analysis:
                        t_clean = (last_analysis["ticker"] or "").replace(".JK", "")
                        ag["current_task"] = f"Ketok Palu: {t_clean} -> {last_analysis['direction']}"
                        ag["speech"] = f"Vonis sidang {t_clean}: {last_analysis['direction']} (Rp {last_analysis['entry_price']:,.0f})".replace(",", ".")
                        ag["capacity"] = 85
                        ag["status"] = "DECIDING"
                elif sid in ["BUDI", "SARI", "HENDRA"]:
                    ag["total_tasks"] = max(12, active_analyses_count // 3)

        except Exception as e:
            pass

    busy_count = sum(1 for a in agents if a["status"] in ["WORKING", "AUDITING", "DECIDING"])
    idle_count = len(agents) - busy_count
    overall_office_load = int(sum(a["capacity"] for a in agents) / max(1, len(agents)))

    return {
        "status": "ok",
        "last_updated": now_wib,
        "office_metrics": {
            "total_agents": len(agents),
            "busy_agents": busy_count,
            "idle_agents": idle_count,
            "overall_load_pct": overall_office_load,
            "total_analyses_completed": active_analyses_count,
            "total_votes_cast": total_votes_recorded,
            "server_health": "100% ONLINE (Render 24/7)",
        },
        "agents": agents,
        "recent_logs": recent_logs,
    }


def render_live_office_html():
    """
    Merender Ruang Kantor Virtual 3D Halus & Modern (Bukan Kotak-Kotak).
    Menggunakan geometri halus kurva, karakter berpostur aerodinamis modern (stylized 3D avatars),
    kursi putar ergonomis melengkung, dual monitor ultrawide curved, dan pencahayaan studio hangat.
    """
    initial_data = get_live_office_data()
    agents_json = json.dumps(initial_data["agents"])

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>AI Virtual Office 3D • Saham AI Agent (Modern Curved 3D)</title>
    <!-- Three.js 3D Engine & OrbitControls -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: #050814;
            color: #f8fafc;
            overflow: hidden;
            width: 100vw;
            height: 100vh;
            user-select: none;
        }}
        .font-mono {{ font-family: 'JetBrains Mono', monospace; }}

        #webgl-container {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 1;
        }}

        /* 3D Floating Name Tags */
        .agent-nametag {{
            position: absolute;
            transform: translate(-50%, -100%);
            pointer-events: none;
            transition: opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            z-index: 20;
            white-space: nowrap;
        }}

        /* Modern Frosted Glass */
        .glass-panel {{
            background: rgba(15, 23, 42, 0.78);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(148, 163, 184, 0.15);
            box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.7);
        }}
    </style>
</head>
<body class="relative">

    <!-- Canvas 3D Three.js -->
    <div id="webgl-container"></div>

    <!-- UI Overlay: Top Navigation Bar -->
    <header class="absolute top-3 left-3 right-3 sm:top-5 sm:left-6 sm:right-6 z-30 flex justify-between items-center pointer-events-none">
        <div class="glass-panel px-4 py-2.5 rounded-2xl flex items-center gap-3 shadow-2xl pointer-events-auto">
            <div class="h-10 w-10 rounded-2xl bg-gradient-to-tr from-cyan-500 via-blue-600 to-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-cyan-500/25 text-xl">
                🏛️
            </div>
            <div>
                <h1 class="text-sm sm:text-base font-bold text-white flex items-center gap-2">
                    AI Virtual Office <span class="text-[10px] px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-extrabold border border-emerald-500/40 flex items-center gap-1.5"><span class="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping"></span> 3D STUDIO</span>
                </h1>
                <p class="text-[11px] text-slate-400 hidden sm:block">Karyawan AI 3D Halus & Modern • Putar 360° & Zoom Bebas</p>
            </div>
        </div>

        <!-- Action Controls -->
        <div class="flex items-center gap-2 pointer-events-auto">
            <button onclick="toggleAudio()" id="btn-audio" class="glass-panel px-3.5 py-2 rounded-2xl text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/80 transition flex items-center gap-1.5">
                🔇 <span class="hidden sm:inline">Suara Kantor</span>
            </button>

            <!-- Tombol Navigasi ke Chart TradingView -->
            <a href="/chart" class="px-4 py-2 rounded-2xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold shadow-lg shadow-emerald-600/30 flex items-center gap-1.5 transition">
                📊 <span class="hidden sm:inline">Terminal</span> Chart
            </a>

            <!-- Tombol Navigasi ke Web Rekap Saham Utama -->
            <a href="/" class="px-4 py-2 rounded-2xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-bold shadow-lg shadow-cyan-600/30 flex items-center gap-1.5 transition">
                📈 <span class="hidden sm:inline">Buka Rekap</span> Saham
            </a>
        </div>
    </header>

    <!-- UI Overlay: 3D Camera Angles Bar (Bottom Center) -->
    <div class="absolute bottom-4 left-1/2 -translate-x-1/2 z-30 pointer-events-none flex flex-wrap justify-center gap-2 px-3 max-w-full">
        <div class="glass-panel p-1.5 rounded-2xl flex items-center gap-1.5 shadow-2xl pointer-events-auto overflow-x-auto max-w-[94vw]">
            <button onclick="setCameraView('overview')" class="px-3.5 py-1.5 rounded-xl text-xs font-bold text-cyan-400 hover:bg-slate-800/90 transition flex items-center gap-1.5">
                🎥 Semua Meja
            </button>
            <button onclick="setCameraView('judge')" class="px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/90 transition flex items-center gap-1.5">
                ⚖️ Chief Arthur
            </button>
            <button onclick="setCameraView('scalper')" class="px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/90 transition flex items-center gap-1.5">
                ⚡ Scalper & Quant
            </button>
            <button onclick="setCameraView('auditor')" class="px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/90 transition flex items-center gap-1.5">
                🛡️ Tim Risiko
            </button>
        </div>
    </div>

    <!-- UI Overlay: Left Stats Pill (Quick Office Capacity) -->
    <div class="absolute bottom-4 left-4 z-30 hidden md:block pointer-events-none">
        <div class="glass-panel p-4 rounded-3xl space-y-2 shadow-2xl pointer-events-auto max-w-xs">
            <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center justify-between">
                <span>Beban Kerja Kantor</span>
                <span class="text-cyan-400 font-mono text-xs font-bold" id="stat-load-text">{initial_data['office_metrics']['overall_load_pct']}%</span>
            </div>
            <div class="w-48 bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-700/50">
                <div id="stat-load-bar" class="bg-gradient-to-r from-emerald-400 via-teal-400 to-cyan-400 h-full rounded-full transition-all duration-700" style="width: {initial_data['office_metrics']['overall_load_pct']}%"></div>
            </div>
            <div class="text-[11px] text-slate-300 flex justify-between pt-0.5 font-medium">
                <span>🟢 <span id="stat-busy-text">{initial_data['office_metrics']['busy_agents']}</span> AI Bekerja</span>
                <span class="text-slate-400">☕ <span id="stat-idle-text">{initial_data['office_metrics']['idle_agents']}</span> Standby</span>
            </div>
        </div>
    </div>

    <!-- UI Overlay: Right Drawer Detail Karyawan (Saat Meja Diklik di 3D) -->
    <div id="agent-drawer" class="absolute top-0 right-0 h-full w-full sm:w-96 z-40 transform translate-x-full transition-transform duration-300 pointer-events-auto p-3 sm:p-5 flex flex-col justify-between">
        <div class="glass-panel h-full rounded-3xl p-5 shadow-2xl flex flex-col justify-between overflow-y-auto border border-slate-700/70">
            <div>
                <!-- Header Drawer -->
                <div class="flex justify-between items-start pb-4 border-b border-slate-800">
                    <div class="flex items-center gap-3">
                        <div id="drawer-avatar" class="w-12 h-12 rounded-2xl bg-gradient-to-tr from-slate-800 to-slate-700 flex items-center justify-center text-2xl shadow-inner border border-slate-600">
                            🤖
                        </div>
                        <div>
                            <h2 id="drawer-name" class="text-base font-bold text-white">Nama AI</h2>
                            <p id="drawer-role" class="text-xs text-cyan-400 font-medium">Peran AI</p>
                        </div>
                    </div>
                    <button onclick="closeDrawer()" class="h-8 w-8 rounded-full bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition">
                        ✕
                    </button>
                </div>

                <!-- Info Model & Status -->
                <div class="my-4 space-y-3">
                    <div class="p-3.5 rounded-2xl bg-slate-950/80 border border-slate-800/80">
                        <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Model Engine:</div>
                        <div id="drawer-model" class="text-xs font-mono text-slate-200">Google Gemini 3.6 Flash</div>
                    </div>

                    <div class="p-3.5 rounded-2xl bg-slate-950/80 border border-slate-800/80">
                        <div class="flex justify-between items-center mb-1.5">
                            <span class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Status & Beban Kerja:</span>
                            <span id="drawer-status-badge" class="px-2.5 py-0.5 rounded-full text-[10px] font-bold border">WORKING</span>
                        </div>
                        <div class="w-full bg-slate-900 rounded-full h-2.5 overflow-hidden border border-slate-800 mt-2">
                            <div id="drawer-cap-bar" class="bg-gradient-to-r from-cyan-500 to-blue-500 h-full rounded-full transition-all duration-500" style="width: 80%"></div>
                        </div>
                        <div class="text-[11px] text-right text-slate-400 font-mono mt-1"><span id="drawer-cap-num">80</span>% Kapasitas</div>
                    </div>

                    <!-- Log Berpikir Terkini -->
                    <div class="p-4 rounded-2xl bg-gradient-to-b from-slate-950 to-slate-900 border border-slate-800/90 shadow-inner">
                        <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                            <span>💬</span> <span>Apa yang Sedang Dikerjakan:</span>
                        </div>
                        <p id="drawer-speech" class="text-xs text-slate-200 italic leading-relaxed">
                            "Menganalisis pergerakan volume intraday dan momentum harga saham..."
                        </p>
                    </div>

                    <div class="p-3.5 rounded-2xl bg-slate-950/50 border border-slate-800 text-xs text-slate-400">
                        <span class="text-slate-500">Tugas Saat Ini:</span>
                        <div id="drawer-task" class="text-slate-200 font-medium mt-0.5">Audit order book</div>
                    </div>
                </div>
            </div>

            <!-- Tombol Interaksi -->
            <div class="pt-4 border-t border-slate-800 space-y-2">
                <a href="https://t.me/Agent_d_saham_bot" target="_blank" class="w-full py-2.5 rounded-2xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-lg flex items-center justify-center gap-1.5 transition">
                    💬 Beri Tugas via Telegram ↗
                </a>
                <button onclick="closeDrawer()" class="w-full py-2 rounded-2xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition">
                    Tutup Detail
                </button>
            </div>
        </div>
    </div>

    <!-- Container Floating 2D Tags over 3D coordinates -->
    <div id="tags-container" class="pointer-events-none absolute inset-0 z-20 overflow-hidden"></div>

    <!-- Script Utama Three.js 3D Halus (Smooth Aesthetics) -->
    <script>
        const initialAgents = {agents_json};
        let scene, camera, renderer, controls;
        const deskMeshes = [];
        const characterGroups = [];
        const walkingHumans = [];
        let raycaster, mouse;
        let selectedAgentId = null;

        // Audio Ambience Kantor (Synthesized keyboard typing)
        let audioCtx = null;
        let isAudioPlaying = false;
        let audioInterval = null;

        function init3D() {{
            const container = document.getElementById('webgl-container');
            const width = window.innerWidth;
            const height = window.innerHeight;

            // 1. Scene dengan Fog Atmosferik
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x070b18);
            scene.fog = new THREE.FogExp2(0x070b18, 0.022);

            // 2. Camera
            camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 1000);
            camera.position.set(16, 13, 17);

            // 3. Renderer dengan Soft Shadow & High-Performance Tone Mapping
            renderer = new THREE.WebGLRenderer({{ antialias: true, powerPreference: "high-performance" }});
            renderer.setSize(width, height);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            renderer.shadowMap.enabled = true;
            renderer.shadowMap.type = THREE.PCFSoftShadowMap;
            renderer.toneMapping = THREE.ACESFilmicToneMapping;
            renderer.toneMappingExposure = 1.05;
            container.appendChild(renderer.domElement);

            // 4. Orbit Controls (Smooth Damping)
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.06;
            controls.maxPolarAngle = Math.PI / 2.15;
            controls.minDistance = 4;
            controls.maxDistance = 40;
            controls.target.set(0, 1.4, 0);

            // 5. Studio Three-Point Lighting (Pencahayaan Studio Lembut, Bukan Kasar)
            setupStudioLighting();

            // 6. Arsitektur Kantor Mewah (Lantai Parquet Reflektif, Dinding Kaca Skyline)
            buildLuxuryOfficeRoom();

            // 7. Meja & Karakter Manusia 3D Halus (Stylized Smooth Avatars)
            buildSmoothWorkstationsAndAvatars(initialAgents);

            raycaster = new THREE.Raycaster();
            mouse = new THREE.Vector2();

            window.addEventListener('resize', onWindowResize, false);
            window.addEventListener('pointerdown', onCanvasClick, false);

            animate();
        }}

        function setupStudioLighting() {{
            // Ambient Light Seimbang
            const ambient = new THREE.AmbientLight(0xcfd8dc, 0.55);
            scene.add(ambient);

            // Key Light Utama (Warm Soft Studio Sunlight)
            const keyLight = new THREE.DirectionalLight(0xfff7ed, 0.95);
            keyLight.position.set(14, 22, 16);
            keyLight.castShadow = true;
            keyLight.shadow.mapSize.width = 2048;
            keyLight.shadow.mapSize.height = 2048;
            keyLight.shadow.bias = -0.0005;
            const d = 16;
            keyLight.shadow.camera.left = -d;
            keyLight.shadow.camera.right = d;
            keyLight.shadow.camera.top = d;
            keyLight.shadow.camera.bottom = -d;
            scene.add(keyLight);

            // Fill Light Dingin dari Sisi Seberang
            const fillLight = new THREE.DirectionalLight(0x38bdf8, 0.4);
            fillLight.position.set(-14, 12, -10);
            scene.add(fillLight);

            // Rim Light Ungu Elegan di Area Sidang Chief Arthur
            const arthurRim = new THREE.PointLight(0xc084fc, 1.8, 22);
            arthurRim.position.set(0, 5, -4);
            scene.add(arthurRim);

            // Rim Light Cyan di Meja Scalper & Quant
            const scalperRim = new THREE.PointLight(0x22d3ee, 1.5, 20);
            scalperRim.position.set(-5, 5, 0);
            scene.add(scalperRim);
        }}

        function buildLuxuryOfficeRoom() {{
            // Lantai Kayu Glossy / Epoxy Mewah dengan Refleksi Cahaya Lembut
            const floorGeo = new THREE.PlaneGeometry(34, 28);
            const floorMat = new THREE.MeshStandardMaterial({{
                color: 0x0b1329,
                roughness: 0.25,
                metalness: 0.15,
            }});
            const floor = new THREE.Mesh(floorGeo, floorMat);
            floor.rotation.x = -Math.PI / 2;
            floor.receiveShadow = true;
            scene.add(floor);

            // Karpet Area Tengah (Meeting Lounge Rug)
            const rugGeo = new THREE.PlaneGeometry(16, 12);
            const rugMat = new THREE.MeshStandardMaterial({{ color: 0x0f172a, roughness: 0.9 }});
            const rug = new THREE.Mesh(rugGeo, rugMat);
            rug.rotation.x = -Math.PI / 2;
            rug.position.set(0, 0.015, 0.5);
            rug.receiveShadow = true;
            scene.add(rug);

            // Dinding Belakang & Kiri Modern
            const wallMat = new THREE.MeshStandardMaterial({{ color: 0x090d1a, roughness: 0.6 }});
            const backWall = new THREE.Mesh(new THREE.BoxGeometry(34, 9, 0.5), wallMat);
            backWall.position.set(0, 4.5, -14);
            backWall.receiveShadow = true;
            scene.add(backWall);

            const leftWall = new THREE.Mesh(new THREE.BoxGeometry(0.5, 9, 28), wallMat);
            leftWall.position.set(-17, 4.5, 0);
            leftWall.receiveShadow = true;
            scene.add(leftWall);

            // Papan Tulis Strategi Saham Kaca Melengkung (Frosted Glass Whiteboard)
            const wbGeo = new THREE.BoxGeometry(0.1, 4.2, 8.5);
            const wbMat = new THREE.MeshStandardMaterial({{
                color: 0xffffff,
                roughness: 0.15,
                metalness: 0.05
            }});
            const wb = new THREE.Mesh(wbGeo, wbMat);
            wb.position.set(-16.7, 4.5, -2);
            scene.add(wb);

            // Server Rack AI Cluster dengan Lampu LED Halus
            const rack = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, 5.5, 24), new THREE.MeshStandardMaterial({{ color: 0x020617, metalness: 0.85, roughness: 0.2 }}));
            rack.position.set(-15, 2.75, -11.5);
            rack.castShadow = true;
            scene.add(rack);

            // Cincin Neon Server AI
            for (let i = 0; i < 4; i++) {{
                const ring = new THREE.Mesh(new THREE.TorusGeometry(0.92, 0.03, 16, 32), new THREE.MeshBasicMaterial({{ color: i % 2 === 0 ? 0x10b981 : 0x06b6d4 }}));
                ring.rotation.x = Math.PI / 2;
                ring.position.set(-15, 1.2 + (i * 1.1), -11.5);
                scene.add(ring);
            }}

            // Tanaman Hias Sudut Ruangan
            buildOrganicPlant(14.5, 0, 9);
            buildOrganicPlant(-14.5, 0, 11);
        }}

        function buildOrganicPlant(x, y, z) {{
            const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.4, 1.1, 24), new THREE.MeshStandardMaterial({{ color: 0x475569, roughness: 0.5 }}));
            pot.position.set(x, y + 0.55, z);
            pot.castShadow = true;
            scene.add(pot);

            // Batang tanaman
            const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.08, 1.4, 12), new THREE.MeshStandardMaterial({{ color: 0x27272a }}));
            stem.position.set(x, y + 1.6, z);
            scene.add(stem);

            // Daun-daun tropis oval melengkung
            const leafMat = new THREE.MeshStandardMaterial({{ color: 0x16a34a, roughness: 0.7 }});
            for (let i = 0; i < 7; i++) {{
                const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.38, 16, 16), leafMat);
                leaf.scale.set(1.4, 0.15, 0.8);
                leaf.position.set(x + Math.sin(i * 1.2) * 0.45, y + 1.5 + (i * 0.2), z + Math.cos(i * 1.2) * 0.45);
                leaf.rotation.set(Math.sin(i) * 0.4, i * 0.9, Math.cos(i) * 0.4);
                leaf.castShadow = true;
                scene.add(leaf);
            }}
        }}

        function buildSmoothWorkstationsAndAvatars(agentsList) {{
            agentsList.forEach(ag => {{
                const isJudge = ag.id === 'ARIF';
                const pos = ag.pos;

                const workstation = new THREE.Group();
                workstation.position.set(pos[0], pos[1], pos[2]);

                // 1. MEJA KERJA MODERN MINIMALIS (Sleek Wooden Desk with Chamfered Corners)
                const deskLength = isJudge ? 3.6 : 2.6;
                const deskDepth = isJudge ? 1.7 : 1.35;
                const deskTopMat = new THREE.MeshStandardMaterial({{
                    color: isJudge ? 0x271708 : 0x1e293b,
                    roughness: 0.35,
                    metalness: 0.1
                }});

                // Permukaan Atas Meja (Top Surface tepat di y = 1.36)
                const deskTop = new THREE.Mesh(new THREE.BoxGeometry(deskLength, 0.08, deskDepth), deskTopMat);
                deskTop.position.set(0, 1.32, 0);
                deskTop.castShadow = true;
                deskTop.receiveShadow = true;
                workstation.add(deskTop);

                // Kaki Meja Silinder Chrome Halus
                const chromeLegMat = new THREE.MeshStandardMaterial({{ color: 0x64748b, metalness: 0.9, roughness: 0.15 }});
                const leg1 = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 1.28, 16), chromeLegMat);
                leg1.position.set(-deskLength * 0.42, 0.64, -deskDepth * 0.35);
                leg1.castShadow = true;
                workstation.add(leg1);

                const leg2 = leg1.clone();
                leg2.position.set(deskLength * 0.42, 0.64, -deskDepth * 0.35);
                workstation.add(leg2);

                const leg3 = leg1.clone();
                leg3.position.set(-deskLength * 0.42, 0.64, deskDepth * 0.35);
                workstation.add(leg3);

                const leg4 = leg1.clone();
                leg4.position.set(deskLength * 0.42, 0.64, deskDepth * 0.35);
                workstation.add(leg4);

                // 2. DUAL MONITOR DI ATAS MEJA (Tepat Berdiri di Permukaan Meja)
                const monitorGroup = new THREE.Group();
                monitorGroup.position.set(0, 1.36, -0.32); // Berdiri kokoh di atas meja

                // Stand / Kaki Monitor Chrome di Atas Meja
                const standBase = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.26, 0.03, 24), chromeLegMat);
                standBase.position.set(0, 0.015, 0);
                standBase.castShadow = true;
                monitorGroup.add(standBase);

                // Tiang Monitor
                const standPole = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.55, 16), chromeLegMat);
                standPole.position.set(0, 0.28, 0);
                standPole.castShadow = true;
                monitorGroup.add(standPole);

                // Palang Gas-Spring Monitor
                const crossBar = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 1.2, 16), chromeLegMat);
                crossBar.rotation.z = Math.PI / 2;
                crossBar.position.set(0, 0.48, 0);
                monitorGroup.add(crossBar);

                // MONITOR UTAMA (Ultrawide 34" Display Menghadap ke Karyawan & Kamera)
                const mainFrameMat = new THREE.MeshStandardMaterial({{ color: 0x020617, metalness: 0.85, roughness: 0.2 }});
                const mainFrame = new THREE.Mesh(new THREE.BoxGeometry(1.35, 0.78, 0.05), mainFrameMat);
                mainFrame.position.set(-0.15, 0.55, 0.04);
                mainFrame.castShadow = true;
                monitorGroup.add(mainFrame);

                // Layar Monitor Utama (Glowing Chart Display)
                const screenColor = ag.status === 'WORKING' ? 0x10b981 : (ag.status === 'DECIDING' ? 0xc084fc : 0x06b6d4);
                const screenMat = new THREE.MeshStandardMaterial({{
                    color: screenColor,
                    emissive: screenColor,
                    emissiveIntensity: 0.6,
                    roughness: 0.2
                }});
                const mainScreen = new THREE.Mesh(new THREE.PlaneGeometry(1.28, 0.71), screenMat);
                mainScreen.position.set(-0.15, 0.55, 0.07);
                monitorGroup.add(mainScreen);

                // MONITOR KEDUA (Vertikal / Terminal Kode - Dimiringkan ke Dalam)
                const sideGroup = new THREE.Group();
                sideGroup.position.set(0.85, 0.55, 0.08);
                sideGroup.rotation.y = -0.38; // Miring menghadap wajah karyawan

                const sideFrame = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.85, 0.05), mainFrameMat);
                sideFrame.castShadow = true;
                sideGroup.add(sideFrame);

                const sideScreenMat = new THREE.MeshStandardMaterial({{
                    color: 0x0284c7,
                    emissive: 0x0284c7,
                    emissiveIntensity: 0.5,
                    roughness: 0.2
                }});
                const sideScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.59, 0.79), sideScreenMat);
                sideScreen.position.set(0, 0, 0.03);
                sideGroup.add(sideScreen);

                monitorGroup.add(sideGroup);
                workstation.add(monitorGroup);

                // KEYBOARD & MOUSE DI ATAS MEJA
                const kb = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.02, 0.24), new THREE.MeshStandardMaterial({{ color: 0x0f172a, roughness: 0.4 }}));
                kb.position.set(0, 1.37, 0.18);
                workstation.add(kb);

                const mouseMesh = new THREE.Mesh(new THREE.SphereGeometry(0.065, 16, 16), new THREE.MeshStandardMaterial({{ color: 0x334155, roughness: 0.3 }}));
                mouseMesh.scale.set(0.8, 0.45, 1.2);
                mouseMesh.position.set(0.55, 1.38, 0.18);
                workstation.add(mouseMesh);

                // CANGKIR KOPI KERAMIK DI ATAS MEJA
                const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.065, 0.16, 20), new THREE.MeshStandardMaterial({{ color: 0xf8fafc, roughness: 0.2 }}));
                mug.position.set(-0.7, 1.44, 0.2);
                workstation.add(mug);

                if (isJudge) {{
                    // Palu Sidang Kayu Ukir (Gavel) di Meja Chief Arthur
                    const gavelHead = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.3, 16), new THREE.MeshStandardMaterial({{ color: 0xb45309, roughness: 0.3 }}));
                    gavelHead.rotation.z = Math.PI / 2;
                    gavelHead.position.set(0.85, 1.42, 0.32);
                    workstation.add(gavelHead);
                }}

                // 3. KURSI KANTOR ERGONOMIS PUTAR (SLIM MODERN CHAIR)
                const chairMat = new THREE.MeshStandardMaterial({{ color: isJudge ? 0x2e1065 : 0x1e293b, roughness: 0.6 }});

                // Dudukan Kursi Membulat Lembut
                const seatCushion = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.36, 0.08, 24), chairMat);
                seatCushion.position.set(0, 0.88, 0.72);
                workstation.add(seatCushion);

                // Sandaran Punggung Slim Mesh (Tipis & Rapi di Belakang Punggung, TIDAK Menutupi Badan)
                const backCushion = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.62, 0.04), chairMat);
                backCushion.position.set(0, 1.4, 0.98);
                workstation.add(backCushion);

                // Tiang Sandaran Ramping
                const backBar = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.55, 12), chromeLegMat);
                backBar.position.set(0, 1.1, 0.96);
                workstation.add(backBar);

                // Tiang Hidrolik Kursi Bintang 5
                const hydPost = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.8, 16), chromeLegMat);
                hydPost.position.set(0, 0.4, 0.72);
                workstation.add(hydPost);

                // 4. KARAKTER KARYAWAN 3D HALUS & BERKELAS (Duduk Mengetik di Meja)
                const avatarGroup = new THREE.Group();
                avatarGroup.position.set(0, 0.88, 0.68);

                // Badan / Torso Silinder Tapered (Lebar di Bahu, Ramping di Pinggang)
                const bodyMat = new THREE.MeshStandardMaterial({{ color: ag.hex, roughness: 0.55, metalness: 0.05 }});
                const torso = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.24, 0.76, 24), bodyMat);
                torso.position.set(0, 0.46, 0);
                torso.castShadow = true;
                avatarGroup.add(torso);

                // Bahu Membulat (Shoulder Spheres)
                const shoulderL = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 16), bodyMat);
                shoulderL.position.set(-0.32, 0.74, 0);
                avatarGroup.add(shoulderL);

                const shoulderR = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 16), bodyMat);
                shoulderR.position.set(0.32, 0.74, 0);
                avatarGroup.add(shoulderR);

                // Leher Silinder Halus
                const skinMat = new THREE.MeshStandardMaterial({{ color: ag.skin_tone || 0xfed7aa, roughness: 0.85 }});
                const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.12, 0.18, 20), skinMat);
                neck.position.set(0, 0.86, 0.02);
                avatarGroup.add(neck);

                // Kepala Avatar Bulat Halus (Stylized Modern Head)
                const head = new THREE.Mesh(new THREE.SphereGeometry(0.26, 28, 28), skinMat);
                head.position.set(0, 1.08, 0.04);
                head.castShadow = true;
                avatarGroup.add(head);

                // Rambut Stylist Mengikuti Bentuk Kepala
                const hairMat = new THREE.MeshStandardMaterial({{ color: ag.hair_color || 0x1e293b, roughness: 0.9 }});
                const hair = new THREE.Mesh(new THREE.SphereGeometry(0.28, 28, 28, 0, Math.PI * 2, 0, Math.PI * 0.65), hairMat);
                hair.position.set(0, 1.13, 0.03);
                avatarGroup.add(hair);

                // Mata Stylist 3D Berkilau Menatap ke Monitor
                const eyeMat = new THREE.MeshBasicMaterial({{ color: 0x0f172a }});
                const eyeL = new THREE.Mesh(new THREE.SphereGeometry(0.03, 12, 12), eyeMat);
                eyeL.position.set(-0.08, 1.08, -0.24); // Menghadap ke arah monitor (-z)
                avatarGroup.add(eyeL);

                const eyeR = new THREE.Mesh(new THREE.SphereGeometry(0.03, 12, 12), eyeMat);
                eyeR.position.set(0.08, 1.08, -0.24);
                avatarGroup.add(eyeR);

                // Aksesori Khusus (Headset RGB untuk Scalper)
                if (ag.id === 'AI_1') {{
                    const band = new THREE.Mesh(new THREE.TorusGeometry(0.28, 0.03, 16, 32, Math.PI), new THREE.MeshStandardMaterial({{ color: 0x06b6d4, roughness: 0.2 }}));
                    band.rotation.z = Math.PI;
                    band.position.set(0, 1.18, 0.04);
                    avatarGroup.add(band);

                    const earcupL = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.06, 16), new THREE.MeshStandardMaterial({{ color: 0x0891b2 }}));
                    earcupL.rotation.z = Math.PI / 2;
                    earcupL.position.set(-0.28, 1.08, 0.04);
                    avatarGroup.add(earcupL);

                    const earcupR = earcupL.clone();
                    earcupR.position.set(0.28, 1.08, 0.04);
                    avatarGroup.add(earcupR);
                }}

                // Lengan Halus Sendi Silinder & Telapak Tangan (Tepat di Atas Keyboard)
                const armL = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.065, 0.45, 16), bodyMat);
                armL.position.set(-0.32, 0.46, -0.2);
                armL.rotation.x = Math.PI / 3;
                avatarGroup.add(armL);

                const handL = new THREE.Mesh(new THREE.SphereGeometry(0.07, 16, 16), skinMat);
                handL.position.set(-0.32, 0.28, -0.42);
                avatarGroup.add(handL);

                const armR = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.065, 0.45, 16), bodyMat);
                armR.position.set(0.32, 0.46, -0.2);
                armR.rotation.x = Math.PI / 3;
                avatarGroup.add(armR);

                const handR = new THREE.Mesh(new THREE.SphereGeometry(0.07, 16, 16), skinMat);
                handR.position.set(0.32, 0.28, -0.42);
                avatarGroup.add(handR);

                workstation.add(avatarGroup);

                // Metadata untuk Interaksi & Animasi
                workstation.userData = {{
                    agentId: ag.id,
                    agentData: ag,
                    armL: armL,
                    handL: handL,
                    armR: armR,
                    handR: handR,
                    head: head,
                    avatarGroup: avatarGroup,
                    mainScreen: mainScreen
                }};

                deskMeshes.push(deskTop);
                deskTop.userData = workstation.userData;

                characterGroups.push(workstation.userData);
                scene.add(workstation);

                createFloatingTag(ag);
            }});
        }}

        function createFloatingTag(ag) {{
            const tag = document.createElement('div');
            tag.className = 'agent-nametag';
            tag.id = `tag-${{ag.id}}`;

            const isBusy = ag.status === 'WORKING' || ag.status === 'DECIDING';
            const statusClass = isBusy ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50' : 'bg-slate-800/80 text-slate-300 border-slate-700';
            const dotClass = isBusy ? 'bg-emerald-400 animate-ping' : 'bg-slate-400';

            tag.innerHTML = `
                <div class="px-2.5 py-1 rounded-xl glass-panel border shadow-lg flex items-center gap-1.5 cursor-pointer pointer-events-auto transform hover:scale-105 transition" onclick="openDrawerById('${{ag.id}}')">
                    <span class="relative flex h-2 w-2">
                        <span class="${{dotClass}} absolute inline-flex h-full w-full rounded-full opacity-75"></span>
                        <span class="${{dotClass}} relative inline-flex rounded-full h-2 w-2"></span>
                    </span>
                    <span class="text-[11px] font-bold text-white">${{ag.name.split(' ')[0]}}</span>
                    <span class="text-[9px] px-1.5 py-0.2 rounded-full border font-mono font-bold ${{statusClass}}">${{ag.status}}</span>
                </div>
            `;
            document.getElementById('tags-container').appendChild(tag);
        }}

        function updateFloatingTagsPosition() {{
            initialAgents.forEach(ag => {{
                const tag = document.getElementById(`tag-${{ag.id}}`);
                if (!tag) return;

                // Tag melayang tinggi di atas monitor workstation, TIDAK menutupi badan karyawan
                const worldPos = new THREE.Vector3(ag.pos[0], ag.pos[1] + 3.8, ag.pos[2] - 0.25);
                worldPos.project(camera);

                if (worldPos.z > 1) {{
                    tag.style.display = 'none';
                    return;
                }}

                tag.style.display = 'block';
                const x = (worldPos.x * 0.5 + 0.5) * window.innerWidth;
                const y = (-(worldPos.y * 0.5) + 0.5) * window.innerHeight;
                tag.style.left = `${{x}}px`;
                tag.style.top = `${{y}}px`;
            }});
        }}

        function onWindowResize() {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }}

        function onCanvasClick(event) {{
            if (event.target.closest('button') || event.target.closest('a') || event.target.closest('#agent-drawer')) return;

            mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
            mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObjects(deskMeshes, true);

            if (intersects.length > 0) {{
                const hit = intersects[0].object;
                if (hit.userData && hit.userData.agentId) {{
                    openDrawerById(hit.userData.agentId);
                }}
            }}
        }}

        function openDrawerById(agentId) {{
            selectedAgentId = agentId;
            const ag = initialAgents.find(a => a.id === agentId);
            if (!ag) return;

            document.getElementById('drawer-name').innerText = ag.name;
            document.getElementById('drawer-role').innerText = ag.role;
            document.getElementById('drawer-model').innerText = ag.model;
            document.getElementById('drawer-speech').innerText = `"${{ag.speech}}"`;
            document.getElementById('drawer-task').innerText = ag.current_task;
            document.getElementById('drawer-cap-num').innerText = ag.capacity;
            document.getElementById('drawer-cap-bar').style.width = ag.capacity + '%';

            const badge = document.getElementById('drawer-status-badge');
            badge.innerText = ag.status;
            badge.className = ag.status === 'WORKING' || ag.status === 'DECIDING'
                ? 'px-2.5 py-0.5 rounded-full text-[10px] font-bold border bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                : 'px-2.5 py-0.5 rounded-full text-[10px] font-bold border bg-slate-800 text-slate-300 border-slate-700';

            document.getElementById('agent-drawer').classList.remove('translate-x-full');

            const targetPos = ag.pos;
            gsapCameraTo(targetPos[0] + 4.5, targetPos[1] + 3.8, targetPos[2] + 5.5, targetPos[0], targetPos[1] + 1.3, targetPos[2]);
        }}

        function closeDrawer() {{
            document.getElementById('agent-drawer').classList.add('translate-x-full');
            selectedAgentId = null;
        }}

        function setCameraView(viewName) {{
            closeDrawer();
            if (viewName === 'overview') {{
                gsapCameraTo(16, 13, 17, 0, 1.4, 0);
            }} else if (viewName === 'judge') {{
                gsapCameraTo(0, 4.5, 1.8, 0, 1.4, -3.8);
            }} else if (viewName === 'scalper') {{
                gsapCameraTo(-8.5, 4.5, 3.5, -4.5, 1.3, 0.5);
            }} else if (viewName === 'auditor') {{
                gsapCameraTo(8.5, 4.5, 3.5, 4.5, 1.3, 0.5);
            }}
        }}

        function gsapCameraTo(x, y, z, tx, ty, tz) {{
            const startPos = camera.position.clone();
            const endPos = new THREE.Vector3(x, y, z);
            const startTar = controls.target.clone();
            const endTar = new THREE.Vector3(tx, ty, tz);

            let t = 0;
            const anim = () => {{
                t += 0.04;
                camera.position.lerpVectors(startPos, endPos, easeInOutCubic(Math.min(t, 1)));
                controls.target.lerpVectors(startTar, endTar, easeInOutCubic(Math.min(t, 1)));
                if (t < 1) {{
                    requestAnimationFrame(anim);
                }}
            }};
            anim();
        }}

        function easeInOutCubic(x) {{
            return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
        }}

        function toggleAudio() {{
            if (!audioCtx) {{
                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }}
            if (audioCtx.state === 'suspended') {{
                audioCtx.resume();
            }}

            isAudioPlaying = !isAudioPlaying;
            const btn = document.getElementById('btn-audio');

            if (isAudioPlaying) {{
                btn.innerHTML = '🔊 <span class="hidden sm:inline">Suara Kantor: ON</span>';
                btn.classList.add('bg-cyan-500/20', 'text-cyan-400');
                audioInterval = setInterval(() => {{
                    playKeyClick();
                }}, 135);
            }} else {{
                btn.innerHTML = '🔇 <span class="hidden sm:inline">Suara Kantor</span>';
                btn.classList.remove('bg-cyan-500/20', 'text-cyan-400');
                clearInterval(audioInterval);
            }}
        }}

        function playKeyClick() {{
            if (!audioCtx) return;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(450 + Math.random() * 650, audioCtx.currentTime);
            gain.gain.setValueAtTime(0.015, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.035);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start();
            osc.stop(audioCtx.currentTime + 0.045);
        }}

        let clock = new THREE.Clock();
        function animate() {{
            requestAnimationFrame(animate);

            const elapsedTime = clock.getElapsedTime();

            // 1. Animasi Mengetik Alami & Menoleh Lembut
            characterGroups.forEach((cg, idx) => {{
                const isWorking = cg.agentData.status === 'WORKING' || cg.agentData.status === 'DECIDING';
                if (isWorking) {{
                    const speed = 11 + (idx % 3);
                    const tapL = Math.sin(elapsedTime * speed) * 0.12;
                    const tapR = Math.cos(elapsedTime * speed) * 0.12;

                    cg.armL.rotation.x = Math.PI / 3 + tapL;
                    cg.armR.rotation.x = Math.PI / 3 + tapR;
                    cg.handL.position.y = 0.28 + tapL * 0.25;
                    cg.handR.position.y = 0.28 + tapR * 0.25;

                    cg.head.rotation.y = Math.sin(elapsedTime * 1.4 + idx) * 0.14;
                    cg.head.position.y = 1.08 + Math.sin(elapsedTime * 3) * 0.01;
                }} else {{
                    cg.armL.rotation.x = Math.PI / 4;
                    cg.armR.rotation.x = Math.PI / 4;
                    cg.head.rotation.y = Math.sin(elapsedTime * 0.5 + idx) * 0.06;
                }}
            }});

            updateFloatingTagsPosition();

            controls.update();
            renderer.render(scene, camera);
        }}

        window.addEventListener('DOMContentLoaded', init3D);

        setInterval(async () => {{
            try {{
                const res = await fetch('/api/live');
                if (!res.ok) return;
                const data = await res.json();
                if (!data || !data.office_metrics) return;

                document.getElementById('stat-load-text').innerText = data.office_metrics.overall_load_pct + '%';
                document.getElementById('stat-load-bar').style.width = data.office_metrics.overall_load_pct + '%';
                document.getElementById('stat-busy-text').innerText = data.office_metrics.busy_agents;
                document.getElementById('stat-idle-text').innerText = data.office_metrics.idle_agents;

                if (data.agents) {{
                    data.agents.forEach(updatedAg => {{
                        const local = initialAgents.find(a => a.id === updatedAg.id);
                        if (local) {{
                            local.status = updatedAg.status;
                            local.capacity = updatedAg.capacity;
                            local.speech = updatedAg.speech;
                            local.current_task = updatedAg.current_task;

                            const tag = document.getElementById(`tag-${{local.id}}`);
                            if (tag) {{
                                const isBusy = local.status === 'WORKING' || local.status === 'DECIDING';
                                const badge = tag.querySelector('span.font-mono');
                                if (badge) {{
                                    badge.innerText = local.status;
                                    badge.className = isBusy
                                        ? 'text-[9px] px-2 py-0.5 rounded-full border font-mono font-bold bg-emerald-500/20 text-emerald-300 border-emerald-500/50'
                                        : 'text-[9px] px-2 py-0.5 rounded-full border font-mono font-bold bg-slate-800/80 text-slate-300 border-slate-700';
                                }}
                            }}

                            if (selectedAgentId === local.id) {{
                                document.getElementById('drawer-speech').innerText = `"${{local.speech}}"`;
                                document.getElementById('drawer-task').innerText = local.current_task;
                                document.getElementById('drawer-cap-num').innerText = local.capacity;
                                document.getElementById('drawer-cap-bar').style.width = local.capacity + '%';
                            }}
                        }}
                    }});
                }}
            }} catch(e) {{
                console.log('Sync err:', e);
            }}
        }}, 3000);
    </script>
</body>
</html>
"""
