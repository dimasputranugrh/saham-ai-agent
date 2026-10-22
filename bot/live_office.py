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
            "pos": [0, 0, -3.5],  # Meja utama di depan ruang sidang
            "status": "DECIDING",
            "capacity": 85,
            "current_task": "Memimpin sidang konsensus 5 AI saham",
            "speech": "Sidang panel 5 AI dibuka. Semua rekomendasi wajib diuji % Works & konsensus.",
            "total_tasks": 0,
            "desk_type": "executive",
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
        },
        {
            "id": "AI_3",
            "name": "AI-3 Nemotron 550B Bandar",
            "role": "Smart Money & Flow Tracer",
            "model": "NVIDIA Nemotron 550B",
            "color": "#10b981",
            "hex": 0x10b981,
            "pos": [-1.8, 0, 2.5],
            "status": "WORKING",
            "capacity": 85,
            "current_task": "Melacak jejak akumulasi bandar & broker flow",
            "speech": "Terdeteksi akumulasi konsisten dari broker asing dan institusi.",
            "total_tasks": 0,
            "desk_type": "standard",
        },
        {
            "id": "BUDI",
            "name": "Bastian (Macro Intel)",
            "role": "Head of Macro & Sector Intel",
            "model": "Daily Standup Analyst",
            "color": "#0ea5e9",
            "hex": 0x0ea5e9,
            "pos": [1.8, 0, 2.5],
            "status": "STANDBY",
            "capacity": 30,
            "current_task": "Monitoring radar 30+ berita keuangan 7 sektor",
            "speech": "Sentimen komoditas dan arah suku bunga BI sedang dikompilasi.",
            "total_tasks": 0,
            "desk_type": "standard",
        },
        {
            "id": "SARI",
            "name": "Serena (Market Screener)",
            "role": "VP of Algorithmic Screener",
            "model": "Daily Standup Screener",
            "color": "#14b8a6",
            "hex": 0x14b8a6,
            "pos": [-1.8, 0, 5.5],
            "status": "STANDBY",
            "capacity": 25,
            "current_task": "Menyaring kandidat breakout emiten BEI",
            "speech": "Daftar pantau saham aktif hari ini sudah siap di meja.",
            "total_tasks": 0,
            "desk_type": "standard",
        },
        {
            "id": "HENDRA",
            "name": "Damian (Chief Risk Officer)",
            "role": "Chief Risk Officer & Capital Guard",
            "model": "Daily Standup Controller",
            "color": "#f97316",
            "hex": 0xf97316,
            "pos": [1.8, 0, 5.5],
            "status": "STANDBY",
            "capacity": 20,
            "current_task": "Menjaga batas risiko portofolio Paper Trading",
            "speech": "Semua posisi disiplin dalam batas toleransi drawdown 1.5%.",
            "total_tasks": 0,
            "desk_type": "standard",
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

            # Analisis mutakhir
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
                        ag["speech"] = f"Keputusan sidang {t_clean}: {last_analysis['direction']} (Rp {last_analysis['entry_price']:,.0f})".replace(",", ".")
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
    Merender Ruang Kantor Virtual 3D Realtime Interaktif.
    Bukan sekadar dashboard kartu biasa, melainkan simulasi ruang kantor 3D yang hidup:
    karyawan duduk di kursi, tangan mengetik di keyboard, monitor menyala, ada yang jalan santai ke dispenser kopi.
    """
    initial_data = get_live_office_data()
    agents_json = json.dumps(initial_data["agents"])

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>AI Virtual Office 3D • Saham AI Agent (Live SaaS)</title>
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
            background: #030712;
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
            transition: opacity 0.2s ease;
            z-index: 20;
            white-space: nowrap;
        }}

        /* Custom Glassmorphism */
        .glass-panel {{
            background: rgba(15, 23, 42, 0.75);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(51, 65, 85, 0.6);
        }}
    </style>
</head>
<body class="relative">

    <!-- Canvas 3D Three.js -->
    <div id="webgl-container"></div>

    <!-- UI Overlay: Top Navigation Bar -->
    <header class="absolute top-3 left-3 right-3 sm:top-5 sm:left-6 sm:right-6 z-30 flex justify-between items-center pointer-events-none">
        <div class="glass-panel px-4 py-2.5 rounded-2xl flex items-center gap-3 shadow-2xl pointer-events-auto">
            <div class="h-9 w-9 rounded-xl bg-gradient-to-tr from-cyan-500 via-blue-600 to-indigo-600 flex items-center justify-center font-bold text-white shadow-lg text-lg">
                🏢
            </div>
            <div>
                <h1 class="text-sm sm:text-base font-bold text-white flex items-center gap-2">
                    AI Virtual Office <span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40 flex items-center gap-1"><span class="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping"></span> 3D LIVE</span>
                </h1>
                <p class="text-[11px] text-slate-400 hidden sm:block">Simulasi Ruang Kantor 3D Karyawan AI Saham • Putar & Zoom Bebas</p>
            </div>
        </div>

        <!-- Action Controls -->
        <div class="flex items-center gap-2 pointer-events-auto">
            <button onclick="toggleAudio()" id="btn-audio" class="glass-panel px-3 py-2 rounded-xl text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/80 transition flex items-center gap-1.5 shadow-lg">
                🔇 <span class="hidden sm:inline">Suara Kantor</span>
            </button>

            <!-- Tombol Navigasi ke Web Rekap Saham Utama -->
            <a href="/" class="px-3.5 py-2 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-bold shadow-lg shadow-cyan-600/30 flex items-center gap-1.5 transition">
                📈 <span class="hidden sm:inline">Buka Rekap</span> Saham
            </a>
        </div>
    </header>

    <!-- UI Overlay: 3D Camera Angles Bar (Bottom Center) -->
    <div class="absolute bottom-4 left-1/2 -translate-x-1/2 z-30 pointer-events-none flex flex-wrap justify-center gap-1.5 sm:gap-2 px-3 max-w-full">
        <div class="glass-panel p-1.5 rounded-2xl flex items-center gap-1 shadow-2xl pointer-events-auto overflow-x-auto max-w-[94vw]">
            <button onclick="setCameraView('overview')" class="px-3 py-1.5 rounded-xl text-xs font-bold text-cyan-400 hover:bg-slate-800/90 transition flex items-center gap-1">
                🎥 Semua Meja
            </button>
            <button onclick="setCameraView('judge')" class="px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/90 transition flex items-center gap-1">
                ⚖️ Chief Arthur
            </button>
            <button onclick="setCameraView('scalper')" class="px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/90 transition flex items-center gap-1">
                ⚡ Scalper & Quant
            </button>
            <button onclick="setCameraView('auditor')" class="px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/90 transition flex items-center gap-1">
                🛡️ Tim Risiko
            </button>
            <button onclick="setCameraView('lounge')" class="px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/90 transition flex items-center gap-1">
                ☕ Coffee Bar
            </button>
        </div>
    </div>

    <!-- UI Overlay: Left Stats Pill (Quick Office Capacity) -->
    <div class="absolute bottom-4 left-4 z-30 hidden md:block pointer-events-none">
        <div class="glass-panel p-3.5 rounded-2xl space-y-1.5 shadow-2xl pointer-events-auto max-w-xs">
            <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center justify-between">
                <span>Kapasitas Kantor AI</span>
                <span class="text-cyan-400 font-mono" id="stat-load-text">{initial_data['office_metrics']['overall_load_pct']}%</span>
            </div>
            <div class="w-48 bg-slate-900 rounded-full h-1.5 overflow-hidden border border-slate-700/50">
                <div id="stat-load-bar" class="bg-gradient-to-r from-emerald-400 to-cyan-400 h-full transition-all duration-700" style="width: {initial_data['office_metrics']['overall_load_pct']}%"></div>
            </div>
            <div class="text-[11px] text-slate-300 flex justify-between pt-0.5">
                <span>🟢 <span id="stat-busy-text">{initial_data['office_metrics']['busy_agents']}</span> AI Bekerja</span>
                <span class="text-slate-500">☕ <span id="stat-idle-text">{initial_data['office_metrics']['idle_agents']}</span> Standby</span>
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
                        <div id="drawer-avatar" class="w-12 h-12 rounded-2xl bg-slate-800 flex items-center justify-center text-2xl shadow-inner border border-slate-700">
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
                    <div class="p-3 rounded-2xl bg-slate-950/80 border border-slate-800/80">
                        <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Model Engine:</div>
                        <div id="drawer-model" class="text-xs font-mono text-slate-200">Google Gemini 3.6 Flash</div>
                    </div>

                    <div class="p-3.5 rounded-2xl bg-slate-950/80 border border-slate-800/80">
                        <div class="flex justify-between items-center mb-1.5">
                            <span class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Status & Beban Kerja:</span>
                            <span id="drawer-status-badge" class="px-2 py-0.5 rounded-full text-[10px] font-bold border">WORKING</span>
                        </div>
                        <div class="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-800 mt-2">
                            <div id="drawer-cap-bar" class="bg-cyan-500 h-full rounded-full transition-all duration-500" style="width: 80%"></div>
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

                    <div class="p-3 rounded-2xl bg-slate-950/50 border border-slate-800 text-xs text-slate-400">
                        <span class="text-slate-500">Tugas Saat Ini:</span>
                        <div id="drawer-task" class="text-slate-200 font-medium mt-0.5">Audit order book</div>
                    </div>
                </div>
            </div>

            <!-- Tombol Interaksi -->
            <div class="pt-4 border-t border-slate-800 space-y-2">
                <a href="https://t.me/Agent_d_saham_bot" target="_blank" class="w-full py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-lg flex items-center justify-center gap-1.5 transition">
                    💬 Beri Tugas via Telegram ↗
                </a>
                <button onclick="closeDrawer()" class="w-full py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition">
                    Tutup Detail
                </button>
            </div>
        </div>
    </div>

    <!-- Container Floating 2D Tags over 3D coordinates -->
    <div id="tags-container" class="pointer-events-none absolute inset-0 z-20 overflow-hidden"></div>

    <!-- Script Utama Three.js 3D Virtual Office -->
    <script>
        const initialAgents = {agents_json};
        let scene, camera, renderer, controls;
        const deskMeshes = [];
        const characterGroups = [];
        const walkingHumans = [];
        let raycaster, mouse;
        let selectedAgentId = null;

        // Audio Ambience Kantor (Synthesized procedural keyboard typing clicks)
        let audioCtx = null;
        let isAudioPlaying = false;
        let audioInterval = null;

        function init3D() {{
            const container = document.getElementById('webgl-container');
            const width = window.innerWidth;
            const height = window.innerHeight;

            // 1. Scene
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x060913);
            scene.fog = new THREE.FogExp2(0x060913, 0.025);

            // 2. Camera (Isometric Perspective)
            camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
            camera.position.set(16, 14, 18);

            // 3. Renderer
            renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: false, powerPreference: "high-performance" }});
            renderer.setSize(width, height);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            renderer.shadowMap.enabled = true;
            renderer.shadowMap.type = THREE.PCFSoftShadowMap;
            container.appendChild(renderer.domElement);

            // 4. Orbit Controls (Bebas Rotasi & Zoom)
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;
            controls.maxPolarAngle = Math.PI / 2.15; // Mencegah tembus ke bawah lantai
            controls.minDistance = 5;
            controls.maxDistance = 45;
            controls.target.set(0, 1.5, 0);

            // 5. Pencahayaan Kantor (Lighting)
            setupLighting();

            // 6. Arsitektur Ruangan Kantor (Lantai, Dinding Kaca Skyline, Plafon)
            buildOfficeRoom();

            // 7. Meja Kerja & Karakter Karyawan AI 3D
            buildWorkstationsAndCharacters(initialAgents);

            // 8. Karyawan yang Berjalan di Koridor Kantor (Animasi Dinamis)
            buildWalkingOfficeEmployees();

            // Raycaster untuk Klik Meja di 3D
            raycaster = new THREE.Raycaster();
            mouse = new THREE.Vector2();

            window.addEventListener('resize', onWindowResize, false);
            window.addEventListener('pointerdown', onCanvasClick, false);

            animate();
        }}

        function setupLighting() {{
            // Ambient Light lembut
            const ambient = new THREE.AmbientLight(0x38bdf8, 0.45);
            scene.add(ambient);

            // Lampu Utama Kantor (Downlight hangat)
            const mainLight = new THREE.DirectionalLight(0xffffff, 0.85);
            mainLight.position.set(12, 20, 15);
            mainLight.castShadow = true;
            mainLight.shadow.mapSize.width = 2048;
            mainLight.shadow.mapSize.height = 2048;
            mainLight.shadow.camera.near = 0.5;
            mainLight.shadow.camera.far = 60;
            const d = 16;
            mainLight.shadow.camera.left = -d;
            mainLight.shadow.camera.right = d;
            mainLight.shadow.camera.top = d;
            mainLight.shadow.camera.bottom = -d;
            scene.add(mainLight);

            // Aksen Lampu Neon Cyan dari Langit-langit
            const cyanLight = new THREE.PointLight(0x06b6d4, 1.2, 25);
            cyanLight.position.set(-5, 6, 0);
            scene.add(cyanLight);

            // Aksen Lampu Neon Ungu di Meja Chief Arthur
            const purpleLight = new THREE.PointLight(0xa855f7, 1.4, 20);
            purpleLight.position.set(0, 5, -4);
            scene.add(purpleLight);
        }}

        function buildOfficeRoom() {{
            // Lantai Kantor Karpet Premium Dark Slate
            const floorGeo = new THREE.PlaneGeometry(32, 26);
            const floorMat = new THREE.MeshStandardMaterial({{
                color: 0x0f172a,
                roughness: 0.85,
                metalness: 0.15
            }});
            const floor = new THREE.Mesh(floorGeo, floorMat);
            floor.rotation.x = -Math.PI / 2;
            floor.receiveShadow = true;
            scene.add(floor);

            // Garis Grid Ubin Kantor Minimalis
            const gridHelper = new THREE.GridHelper(32, 32, 0x1e293b, 0x1e293b);
            gridHelper.position.y = 0.01;
            scene.add(gridHelper);

            // Dinding Kaca Belakang dengan Pemandangan Kota Malam (City Skyline)
            const wallMat = new THREE.MeshStandardMaterial({{ color: 0x090d16, roughness: 0.5 }});

            // Dinding Kiri
            const leftWallGeo = new THREE.BoxGeometry(0.5, 9, 26);
            const leftWall = new THREE.Mesh(leftWallGeo, wallMat);
            leftWall.position.set(-16, 4.5, 0);
            leftWall.receiveShadow = true;
            scene.add(leftWall);

            // Dinding Belakang (Kaca Panorama)
            const backWallGeo = new THREE.BoxGeometry(32, 9, 0.5);
            const backWall = new THREE.Mesh(backWallGeo, wallMat);
            backWall.position.set(0, 4.5, -13);
            backWall.receiveShadow = true;
            scene.add(backWall);

            // Whiteboard Saham di Dinding Kiri
            const wbGeo = new THREE.BoxGeometry(0.1, 4, 8);
            const wbMat = new THREE.MeshStandardMaterial({{ color: 0xf8fafc, roughness: 0.2 }});
            const wb = new THREE.Mesh(wbGeo, wbMat);
            wb.position.set(-15.7, 4.5, -2);
            scene.add(wb);

            // Server Rack AI 24/7 di Sudut Kantor dengan Lampu Blinking
            const rackGeo = new THREE.BoxGeometry(1.6, 6, 2.2);
            const rackMat = new THREE.MeshStandardMaterial({{ color: 0x020617, metalness: 0.8, roughness: 0.2 }});
            const rack = new THREE.Mesh(rackGeo, rackMat);
            rack.position.set(-14.5, 3, -11);
            rack.castShadow = true;
            scene.add(rack);

            // LED Blinking Server
            for (let i = 0; i < 6; i++) {{
                const ledGeo = new THREE.SphereGeometry(0.06, 8, 8);
                const ledMat = new THREE.MeshBasicMaterial({{ color: i % 2 === 0 ? 0x10b981 : 0x06b6d4 }});
                const led = new THREE.Mesh(ledGeo, ledMat);
                led.position.set(-13.65, 1.5 + (i * 0.7), -11.5 + (i % 3 * 0.4));
                scene.add(led);
            }}

            // Coffee & Water Dispenser Lounge Corner
            buildLoungeArea();
        }}

        function buildLoungeArea() {{
            // Meja Bar Kopi & Dispenser Air Galon
            const barGeo = new THREE.BoxGeometry(3, 1.8, 6);
            const barMat = new THREE.MeshStandardMaterial({{ color: 0x1e293b, roughness: 0.6 }});
            const bar = new THREE.Mesh(barGeo, barMat);
            bar.position.set(13.8, 0.9, -9);
            bar.castShadow = true;
            bar.receiveShadow = true;
            scene.add(bar);

            // Dispenser Galon Air Biru
            const dispBody = new THREE.Mesh(new THREE.BoxGeometry(0.8, 1.6, 0.8), new THREE.MeshStandardMaterial({{ color: 0xf8fafc }}));
            dispBody.position.set(13.8, 2.6, -11);
            scene.add(dispBody);

            const waterBottle = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.9, 16), new THREE.MeshStandardMaterial({{ color: 0x0284c7, transparent: true, opacity: 0.7 }}));
            waterBottle.position.set(13.8, 3.8, -11);
            scene.add(waterBottle);

            // Sofa Santai Karyawan
            const sofaGeo = new THREE.BoxGeometry(2.5, 1.2, 5);
            const sofaMat = new THREE.MeshStandardMaterial({{ color: 0x334155, roughness: 0.8 }});
            const sofa = new THREE.Mesh(sofaGeo, sofaMat);
            sofa.position.set(13.8, 0.6, -3);
            sofa.castShadow = true;
            scene.add(sofa);

            // Pot Tanaman Hias Hijau (Office Plant)
            const potMat = new THREE.MeshStandardMaterial({{ color: 0x475569 }});
            const plantMat = new THREE.MeshStandardMaterial({{ color: 0x15803d, roughness: 0.9 }});
            const pot1 = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.35, 1, 16), potMat);
            pot1.position.set(14, 0.5, 10);
            scene.add(pot1);
            const leaves1 = new THREE.Mesh(new THREE.DodecahedronGeometry(0.8), plantMat);
            leaves1.position.set(14, 1.4, 10);
            scene.add(leaves1);
        }}

        function buildWorkstationsAndCharacters(agentsList) {{
            agentsList.forEach(ag => {{
                const isJudge = ag.id === 'ARIF';
                const pos = ag.pos;

                // Group untuk seluruh unit workstation
                const deskGroup = new THREE.Group();
                deskGroup.position.set(pos[0], pos[1], pos[2]);

                // 1. Meja Kayu (Desk Slab)
                const deskWidth = isJudge ? 3.6 : 2.5;
                const deskDepth = isJudge ? 1.8 : 1.4;
                const deskTopMat = new THREE.MeshStandardMaterial({{
                    color: isJudge ? 0x451a03 : 0x1e293b,
                    roughness: 0.4,
                    metalness: 0.1
                }});
                const deskTop = new THREE.Mesh(new THREE.BoxGeometry(deskWidth, 0.12, deskDepth), deskTopMat);
                deskTop.position.set(0, 1.3, 0);
                deskTop.castShadow = true;
                deskTop.receiveShadow = true;
                deskGroup.add(deskTop);

                // Kaki Meja Besi
                const legMat = new THREE.MeshStandardMaterial({{ color: 0x0f172a, metalness: 0.8 }});
                const leg1 = new THREE.Mesh(new THREE.BoxGeometry(0.1, 1.3, deskDepth * 0.9), legMat);
                leg1.position.set(-deskWidth / 2 + 0.15, 0.65, 0);
                deskGroup.add(leg1);
                const leg2 = leg1.clone();
                leg2.position.set(deskWidth / 2 - 0.15, 0.65, 0);
                deskGroup.add(leg2);

                // 2. Dual Monitor Komputer di Meja
                const monitorGroup = new THREE.Group();
                monitorGroup.position.set(0, 1.36, -0.25);

                // Monitor Utama (Layar Chart)
                const monFrame = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.75, 0.06), new THREE.MeshStandardMaterial({{ color: 0x020617 }}));
                monFrame.position.set(0, 0.55, 0);
                monFrame.castShadow = true;
                monitorGroup.add(monFrame);

                // Layar Menyala Candlestick
                const screenMat = new THREE.MeshBasicMaterial({{ color: ag.status === 'WORKING' ? 0x10b981 : 0x0284c7 }});
                const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.12, 0.68), screenMat);
                screen.position.set(0, 0.55, 0.035);
                monitorGroup.add(screen);

                // Monitor Kedua (Vertikal / Terminal Kode)
                const monSideFrame = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.9, 0.06), new THREE.MeshStandardMaterial({{ color: 0x020617 }}));
                monSideFrame.position.set(0.95, 0.6, 0.15);
                monSideFrame.rotation.y = -0.35;
                monitorGroup.add(monSideFrame);

                const screenSide = new THREE.Mesh(new THREE.PlaneGeometry(0.58, 0.82), new THREE.MeshBasicMaterial({{ color: 0x06b6d4 }}));
                screenSide.position.set(0.95, 0.6, 0.185);
                screenSide.rotation.y = -0.35;
                monitorGroup.add(screenSide);

                // Tiang Monitor
                const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.4), legMat);
                stand.position.set(0, 0.2, 0);
                monitorGroup.add(stand);
                deskGroup.add(monitorGroup);

                // Keyboard RGB & Mouse
                const kb = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.03, 0.3), new THREE.MeshStandardMaterial({{ color: 0x0f172a }}));
                kb.position.set(0, 1.38, 0.25);
                deskGroup.add(kb);

                const mouseMesh = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.04, 0.18), new THREE.MeshStandardMaterial({{ color: 0x334155 }}));
                mouseMesh.position.set(0.55, 1.38, 0.25);
                deskGroup.add(mouseMesh);

                // Cangkir Kopi Karyawan
                const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.07, 0.15, 12), new THREE.MeshStandardMaterial({{ color: 0xf8fafc }}));
                mug.position.set(-0.7, 1.44, 0.25);
                deskGroup.add(mug);

                if (isJudge) {{
                    // Palu Hakim Kayu di Meja
                    const gavel = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.12, 0.12), new THREE.MeshStandardMaterial({{ color: 0xb45309 }}));
                    gavel.position.set(0.8, 1.42, 0.4);
                    deskGroup.add(gavel);
                }}

                // 3. Kursi Kantor Ergonomis (Swivel Chair)
                const chairMat = new THREE.MeshStandardMaterial({{ color: isJudge ? 0x1e1b4b : 0x1e293b, roughness: 0.7 }});
                const seat = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.12, 0.8), chairMat);
                seat.position.set(0, 0.9, 0.85);
                deskGroup.add(seat);

                const backrest = new THREE.Mesh(new THREE.BoxGeometry(0.85, 1.1, 0.12), chairMat);
                backrest.position.set(0, 1.5, 1.25);
                deskGroup.add(backrest);

                // 4. Karakter Karyawan AI 3D (Wujud Orang Duduk & Mengetik)
                const charGroup = new THREE.Group();
                charGroup.position.set(0, 0.9, 0.8);

                // Badan / Kemeja Karyawan
                const shirtMat = new THREE.MeshStandardMaterial({{ color: ag.hex, roughness: 0.6 }});
                const torso = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.75, 0.4), shirtMat);
                torso.position.set(0, 0.45, 0);
                torso.castShadow = true;
                charGroup.add(torso);

                // Kepala & Wajah
                const skinMat = new THREE.MeshStandardMaterial({{ color: 0xfed7aa, roughness: 0.8 }});
                const head = new THREE.Mesh(new THREE.SphereGeometry(0.24, 16, 16), skinMat);
                head.position.set(0, 1.05, 0.02);
                head.castShadow = true;
                charGroup.add(head);

                // Rambut Karyawan
                const hairMat = new THREE.MeshStandardMaterial({{ color: 0x1e293b, roughness: 0.9 }});
                const hair = new THREE.Mesh(new THREE.SphereGeometry(0.25, 16, 16, 0, Math.PI * 2, 0, Math.PI / 2), hairMat);
                hair.position.set(0, 1.12, 0.02);
                charGroup.add(hair);

                // Lengan Kiri & Kanan (Animated Typing)
                const armMat = shirtMat;
                const armL = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.5, 0.14), armMat);
                armL.position.set(-0.38, 0.35, -0.15);
                armL.rotation.x = -Math.PI / 3;
                charGroup.add(armL);

                const armR = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.5, 0.14), armMat);
                armR.position.set(0.38, 0.35, -0.15);
                armR.rotation.x = -Math.PI / 3;
                charGroup.add(armR);

                deskGroup.add(charGroup);

                // Metadata untuk interaksi klik
                deskGroup.userData = {{
                    agentId: ag.id,
                    agentData: ag,
                    armL: armL,
                    armR: armR,
                    head: head,
                    charGroup: charGroup,
                    screen: screen
                }};

                deskMeshes.push(deskTop); // Target click raycaster
                deskTop.userData = deskGroup.userData;

                characterGroups.push(deskGroup.userData);
                scene.add(deskGroup);

                // Buat 2D Floating Name Tag di atas meja
                createFloatingTag(ag);
            }});
        }}

        function buildWalkingOfficeEmployees() {{
            // Tambahkan 2 karakter karyawan yang berjalan santai di koridor kantor agar suasana ramai dan sibuk
            const walker1 = createWalkingHuman(0x38bdf8, [-8, 0, 8], [8, 0, 8]);
            scene.add(walker1.group);
            walkingHumans.push(walker1);

            const walker2 = createWalkingHuman(0xf43f5e, [13.5, 0, -2], [13.5, 0, -8]);
            scene.add(walker2.group);
            walkingHumans.push(walker2);
        }}

        function createWalkingHuman(shirtColor, startPos, endPos) {{
            const group = new THREE.Group();
            group.position.set(startPos[0], startPos[1], startPos[2]);

            const bodyMat = new THREE.MeshStandardMaterial({{ color: shirtColor }});
            const torso = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.7, 0.3), bodyMat);
            torso.position.y = 1.35;
            torso.castShadow = true;
            group.add(torso);

            const head = new THREE.Mesh(new THREE.SphereGeometry(0.2, 16, 16), new THREE.MeshStandardMaterial({{ color: 0xfed7aa }}));
            head.position.y = 1.9;
            group.add(head);

            // Kaki
            const legMat = new THREE.MeshStandardMaterial({{ color: 0x1e293b }});
            const legL = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.8, 0.16), legMat);
            legL.position.set(-0.16, 0.5, 0);
            group.add(legL);

            const legR = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.8, 0.16), legMat);
            legR.position.set(0.16, 0.5, 0);
            group.add(legR);

            return {{
                group: group,
                start: startPos,
                end: endPos,
                progress: 0,
                speed: 0.0035 + Math.random() * 0.002,
                legL: legL,
                legR: legR
            }};
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
                    <span class="text-[9px] px-1.5 py-0.2 rounded-full border font-mono ${{statusClass}}">${{ag.status}}</span>
                </div>
            `;
            document.getElementById('tags-container').appendChild(tag);
        }}

        function updateFloatingTagsPosition() {{
            initialAgents.forEach(ag => {{
                const tag = document.getElementById(`tag-${{ag.id}}`);
                if (!tag) return;

                const worldPos = new THREE.Vector3(ag.pos[0], ag.pos[1] + 2.7, ag.pos[2]);
                worldPos.project(camera);

                // Jika di belakang kamera, sembunyikan
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
            // Jangan trigger jika klik tombol UI
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
                ? 'px-2 py-0.5 rounded-full text-[10px] font-bold border bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                : 'px-2 py-0.5 rounded-full text-[10px] font-bold border bg-slate-800 text-slate-300 border-slate-700';

            document.getElementById('agent-drawer').classList.remove('translate-x-full');

            // Gerakkan kamera fokus ke meja karyawan
            const targetPos = ag.pos;
            gsapCameraTo(targetPos[0] + 5, targetPos[1] + 4, targetPos[2] + 6, targetPos[0], targetPos[1] + 1.2, targetPos[2]);
        }}

        function closeDrawer() {{
            document.getElementById('agent-drawer').classList.add('translate-x-full');
            selectedAgentId = null;
        }}

        function setCameraView(viewName) {{
            closeDrawer();
            if (viewName === 'overview') {{
                gsapCameraTo(16, 14, 18, 0, 1.5, 0);
            }} else if (viewName === 'judge') {{
                gsapCameraTo(0, 5, 2, 0, 1.5, -3.5);
            }} else if (viewName === 'scalper') {{
                gsapCameraTo(-9, 5, 4, -4.5, 1.3, 0.5);
            }} else if (viewName === 'auditor') {{
                gsapCameraTo(9, 5, 4, 4.5, 1.3, 0.5);
            }} else if (viewName === 'lounge') {{
                gsapCameraTo(16, 4, -5, 13.8, 1.5, -7);
            }}
        }}

        function gsapCameraTo(x, y, z, tx, ty, tz) {{
            // Smooth Camera Transition Manual (lerp loop)
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

        // Audio Ambience Keyboard Typing Kantor (Web Audio API Synthesizer)
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
                // Interval bunyi ketikan keyboard acak
                audioInterval = setInterval(() => {{
                    playKeyClick();
                }}, 140);
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
            // Frekuensi click ketikan mekanikal
            osc.frequency.setValueAtTime(400 + Math.random() * 600, audioCtx.currentTime);
            gain.gain.setValueAtTime(0.015, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.04);
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start();
            osc.stop(audioCtx.currentTime + 0.05);
        }}

        // Loop Animasi 3D (60 FPS)
        let clock = new THREE.Clock();
        function animate() {{
            requestAnimationFrame(animate);

            const elapsedTime = clock.getElapsedTime();

            // 1. Animasi Tangan Mengetik di Meja & Kepala Mengangguk
            characterGroups.forEach((cg, idx) => {{
                const isWorking = cg.agentData.status === 'WORKING' || cg.agentData.status === 'DECIDING';
                if (isWorking) {{
                    const speed = 12 + (idx % 4);
                    // Tangan mengetik bergantian
                    cg.armL.rotation.x = -Math.PI / 3 + Math.sin(elapsedTime * speed) * 0.12;
                    cg.armR.rotation.x = -Math.PI / 3 + Math.cos(elapsedTime * speed) * 0.12;
                    // Kepala fokus sedikit bergerak memantau layar
                    cg.head.rotation.y = Math.sin(elapsedTime * 1.5 + idx) * 0.15;
                    cg.head.position.y = 1.05 + Math.sin(elapsedTime * 4) * 0.01;
                }} else {{
                    // Mode Idle: Rileks
                    cg.armL.rotation.x = -Math.PI / 4;
                    cg.armR.rotation.x = -Math.PI / 4;
                    cg.head.rotation.y = Math.sin(elapsedTime * 0.6 + idx) * 0.08;
                }}
            }});

            // 2. Animasi Karyawan yang Berjalan di Koridor
            walkingHumans.forEach(w => {{
                w.progress += w.speed;
                if (w.progress > 1) {{
                    w.progress = 0;
                    // Tukar arah jalan bolak-balik
                    const tmp = w.start;
                    w.start = w.end;
                    w.end = tmp;
                }}
                w.group.position.x = w.start[0] + (w.end[0] - w.start[0]) * w.progress;
                w.group.position.z = w.start[2] + (w.end[2] - w.start[2]) * w.progress;

                // Ayunan kaki saat berjalan
                const legSwing = Math.sin(elapsedTime * 8) * 0.4;
                w.legL.rotation.x = legSwing;
                w.legR.rotation.x = -legSwing;
            }});

            // 3. Update Posisi Label 2D Nama di Layar
            updateFloatingTagsPosition();

            controls.update();
            renderer.render(scene, camera);
        }}

        // Inisialisasi 3D saat dokumen siap
        window.addEventListener('DOMContentLoaded', init3D);

        // Polling Real-time Update tiap 3 detik ke /api/live
        setInterval(async () => {{
            try {{
                const res = await fetch('/api/live');
                if (!res.ok) return;
                const data = await res.json();
                if (!data || !data.office_metrics) return;

                // Update metrik beban
                document.getElementById('stat-load-text').innerText = data.office_metrics.overall_load_pct + '%';
                document.getElementById('stat-load-bar').style.width = data.office_metrics.overall_load_pct + '%';
                document.getElementById('stat-busy-text').innerText = data.office_metrics.busy_agents;
                document.getElementById('stat-idle-text').innerText = data.office_metrics.idle_agents;

                // Update status karyawan
                if (data.agents) {{
                    data.agents.forEach(updatedAg => {{
                        const local = initialAgents.find(a => a.id === updatedAg.id);
                        if (local) {{
                            local.status = updatedAg.status;
                            local.capacity = updatedAg.capacity;
                            local.speech = updatedAg.speech;
                            local.current_task = updatedAg.current_task;

                            // Update live tag
                            const tag = document.getElementById(`tag-${{local.id}}`);
                            if (tag) {{
                                const isBusy = local.status === 'WORKING' || local.status === 'DECIDING';
                                const badge = tag.querySelector('span.font-mono');
                                if (badge) {{
                                    badge.innerText = local.status;
                                    badge.className = isBusy
                                        ? 'text-[9px] px-1.5 py-0.2 rounded-full border font-mono bg-emerald-500/20 text-emerald-300 border-emerald-500/50'
                                        : 'text-[9px] px-1.5 py-0.2 rounded-full border font-mono bg-slate-800/80 text-slate-300 border-slate-700';
                                }}
                            }}

                            // Update drawer jika sedang terbuka untuk agen ini
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
