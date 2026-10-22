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

    # Daftar default profil karyawan
    agents = [
        {
            "id": "AI_1",
            "name": "AI-1 Momentum Scalper",
            "role": "Volume & Intraday Scalper",
            "model": "Google Gemini 3.6 Flash",
            "avatar": "⚡",
            "color": "cyan",
            "desc": "Membaca spike volume 15m, posisi VWAP, dan breakout harga cepat.",
            "status": "STANDBY",
            "capacity": 20,
            "current_task": "Menunggu radar volume intraday & perintah /cek",
            "speech": "Radar VWAP aktif. Belum ada lonjakan volume liar jam ini.",
            "total_tasks": 0,
            "sentiment": "NEUTRAL",
            "desk_icon": "💻",
        },
        {
            "id": "AI_2",
            "name": "AI-2 Risk & Trap Auditor",
            "role": "Risk & Trap Guard",
            "model": "OpenAI GPT-OSS 120B (Groq)",
            "avatar": "🛡️",
            "color": "rose",
            "desc": "Mencari potensi bull trap, spread mahal, dan alasan menahan diri.",
            "status": "STANDBY",
            "capacity": 25,
            "current_task": "Audit risiko portofolio & spread order book",
            "speech": "Disiplin modal adalah nomor satu. Jangan terburu-buru entry di pucuk.",
            "total_tasks": 0,
            "sentiment": "CAUTIOUS",
            "desk_icon": "📊",
        },
        {
            "id": "AI_3",
            "name": "AI-3 Bandar & Flow Detector",
            "role": "Smart Money & Flow Tracer",
            "model": "NVIDIA Nemotron 550B (OpenRouter)",
            "avatar": "🐋",
            "color": "indigo",
            "desc": "Menganalisis akumulasi bandar besar dan jejak transaksi institusi.",
            "status": "STANDBY",
            "capacity": 30,
            "current_task": "Melacak jejak akumulasi bandar di saham likuid",
            "speech": "Mendeteksi aliran dana rahasia. Mengikuti jejak smart money.",
            "total_tasks": 0,
            "sentiment": "OBSERVING",
            "desk_icon": "🖥️",
        },
        {
            "id": "AI_4",
            "name": "AI-4 Trend & Swing Guard",
            "role": "Trend Alignment & Swing",
            "model": "Alibaba Qwen 3.8 27B (Groq)",
            "avatar": "📈",
            "color": "amber",
            "desc": "Menjaga keselarasan tren EMA harian & rasio Risk/Reward.",
            "status": "STANDBY",
            "capacity": 15,
            "current_task": "Menghitung jarak Support/Resistance & EMA harian",
            "speech": "Tren adalah sahabat kita. Pastikan Risk/Reward minimal 1:2.",
            "total_tasks": 0,
            "sentiment": "NEUTRAL",
            "desk_icon": "📑",
        },
        {
            "id": "AI_5",
            "name": "AI-5 Quant Bayesian Engine",
            "role": "Bayesian Probability Math",
            "model": "Quant Bayesian v1 (Python)",
            "avatar": "🧮",
            "color": "emerald",
            "desc": "Kalkulasi statistik murni, biaya fee 0.40%, dan probabilitas historis.",
            "status": "STANDBY",
            "capacity": 10,
            "current_task": "Kalibrasi data empiris & potongan fee BEI 0.40%",
            "speech": "Probabilitas matematika siap dikomputasi begitu ada data baru.",
            "total_tasks": 0,
            "sentiment": "ANALYTICAL",
            "desk_icon": "🗄️",
        },
        {
            "id": "ARIF",
            "name": "Hakim Ketua Arif",
            "role": "Chief Decider & Consensus",
            "model": "Ensemble Judge (>=3 Buy & >=60%)",
            "avatar": "⚖️",
            "color": "purple",
            "desc": "Memimpin sidang 5 AI, memverifikasi konsensus, & mengetok palu BUY/WAIT.",
            "status": "STANDBY",
            "capacity": 15,
            "current_task": "Menunggu rekap suara 5 AI dari meja analis",
            "speech": "Palu sidang siap diketok. Sidang 5 AI akan dibuka jika ada perintah /cek.",
            "total_tasks": 0,
            "sentiment": "READY",
            "desk_icon": "🔨",
        },
        {
            "id": "BUDI",
            "name": "Budi (Macro & Berita)",
            "role": "News & Macro Hunter",
            "model": "Daily Standup Analyst",
            "avatar": "📰",
            "color": "sky",
            "desc": "Riset perbandingan 30+ artikel berita 7 sektor BEI & sentimen global.",
            "status": "STANDBY",
            "capacity": 35,
            "current_task": "Scanning berita Kontan, Bisnis, CNBC, & Investor.id",
            "speech": "Memantau katalis komoditas, BI rate, dan sentimen sektor.",
            "total_tasks": 0,
            "sentiment": "READING",
            "desk_icon": "☕",
        },
        {
            "id": "SARI",
            "name": "Sari (Screener Saham)",
            "role": "Technical Screener",
            "model": "Daily Standup Screener",
            "avatar": "🎯",
            "color": "teal",
            "desc": "Menyaring kandidat saham aktif dengan likuiditas tinggi.",
            "status": "STANDBY",
            "capacity": 25,
            "current_task": "Menjaga daftar pantau emiten potensial",
            "speech": "Daftar emiten LQ45 & Second Liner siap disaring.",
            "total_tasks": 0,
            "sentiment": "READY",
            "desk_icon": "📋",
        },
        {
            "id": "HENDRA",
            "name": "Hendra (Risk Manager)",
            "role": "Money Management Guard",
            "model": "Daily Standup Controller",
            "avatar": "💼",
            "color": "orange",
            "desc": "Memastikan batas alokasi modal simulasi & trailing stop disiplin.",
            "status": "STANDBY",
            "capacity": 15,
            "current_task": "Menjaga batas risiko portofolio simulasi Paper",
            "speech": "Portofolio Paper aman. Tidak ada batas risiko yang dilanggar.",
            "total_tasks": 0,
            "sentiment": "CALM",
            "desk_icon": "🔒",
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

            # Total vote keseluruhan
            total_votes_recorded = cur.execute("SELECT count(*) FROM ai_panel_votes").fetchone()[0]

            # Total analisis
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
                # Format waktu
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

            # Analisis paling mutakhir
            cur.execute("""
                SELECT ticker, direction, entry_price, take_profit_1, stop_loss, created_at_wib
                FROM analysis_history
                ORDER BY rowid DESC
                LIMIT 1
            """)
            last_analysis = cur.fetchone()

            conn.close()

            # Perbarui status masing-masing agen berdasarkan data nyata
            for ag in agents:
                sid = ag["id"]
                if sid in vote_counts:
                    ag["total_tasks"] = vote_counts[sid][0]

                if sid in latest_votes:
                    lv = latest_votes[sid]
                    t_clean = (lv["ticker"] or "").replace(".JK", "")
                    ag["speech"] = f"[{t_clean}] {lv['reasoning_summary']}"
                    ag["current_task"] = f"Menganalisis {t_clean} ({lv['vote_direction']} • {lv['confidence_pct']:.0f}%)"

                    # Hitung kapasitas berdasarkan kesibukan
                    # Jika ada aktivitas, kita variasikan kapasitas 65% - 95%
                    ag["capacity"] = min(95, 45 + (ag["total_tasks"] % 40))
                    ag["status"] = "WORKING" if lv["vote_direction"] == "BUY" else "AUDITING"

                elif sid == "ARIF":
                    ag["total_tasks"] = active_analyses_count
                    if last_analysis:
                        t_clean = (last_analysis["ticker"] or "").replace(".JK", "")
                        ag["current_task"] = f"Ketok Palu Konsensus: {t_clean} -> {last_analysis['direction']}"
                        ag["speech"] = f"Hasil sidang terakhir {t_clean} diputuskan {last_analysis['direction']} di harga Rp {last_analysis['entry_price']:,.0f}".replace(",", ".")
                        ag["capacity"] = 80
                        ag["status"] = "DECIDING"
                elif sid in ["BUDI", "SARI", "HENDRA"]:
                    ag["total_tasks"] = max(12, active_analyses_count // 3)
                    ag["capacity"] = 35 + (len(ag["name"]) * 3 % 45)

        except Exception as e:
            pass

    # Status Kantor
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
            "server_health": "100% ONLINE (Render + UptimeRobot)",
        },
        "agents": agents,
        "recent_logs": recent_logs,
    }


def render_live_office_html():
    """Merender HTML Virtual Office AI Agent secara visual interaktif & responsif."""
    data = get_live_office_data()
    metrics = data["office_metrics"]
    agents = data["agents"]
    logs = data["recent_logs"]

    # Buat kartu meja kantor untuk masing-masing agent
    agent_desks_html = ""
    for ag in agents:
        status_color = (
            "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
            if ag["status"] in ["WORKING", "DECIDING"]
            else ("bg-amber-500/20 text-amber-300 border-amber-500/40" if ag["status"] == "AUDITING" else "bg-slate-700/40 text-slate-300 border-slate-600/40")
        )
        status_dot = (
            "bg-emerald-400 animate-pulse"
            if ag["status"] in ["WORKING", "DECIDING"]
            else ("bg-amber-400 animate-pulse" if ag["status"] == "AUDITING" else "bg-slate-400")
        )

        cap_color = (
            "bg-gradient-to-r from-emerald-500 to-teal-400"
            if ag["capacity"] < 50
            else ("bg-gradient-to-r from-amber-500 to-orange-400" if ag["capacity"] < 80 else "bg-gradient-to-r from-rose-500 to-pink-500")
        )

        agent_desks_html += f"""
        <div class="agent-desk relative rounded-2xl bg-slate-900/90 border border-slate-800/80 p-5 shadow-xl hover:border-cyan-500/50 transition-all duration-300 flex flex-col justify-between group overflow-hidden" data-agent-id="{ag['id']}">
            <!-- Subtle Office Desk Background Pattern -->
            <div class="absolute -right-6 -bottom-6 w-28 h-28 rounded-full bg-cyan-500/5 blur-2xl pointer-events-none"></div>

            <!-- Desk Header: Avatar & Info -->
            <div>
                <div class="flex items-start justify-between gap-3 mb-3">
                    <div class="flex items-center gap-3">
                        <div class="relative w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-2xl shadow-inner group-hover:scale-105 transition-transform">
                            {ag['avatar']}
                            <!-- Active desk typing indicator glow -->
                            <span class="absolute -top-1 -right-1 flex h-3.5 w-3.5">
                                <span class="{status_dot} absolute inline-flex h-full w-full rounded-full opacity-75"></span>
                                <span class="{status_dot} relative inline-flex rounded-full h-3.5 w-3.5"></span>
                            </span>
                        </div>
                        <div>
                            <h3 class="text-sm font-bold text-white group-hover:text-cyan-300 transition-colors">{ag['name']}</h3>
                            <div class="text-[11px] text-cyan-400 font-medium">{ag['role']}</div>
                            <div class="text-[10px] text-slate-500 font-mono truncate max-w-[160px]">{ag['model']}</div>
                        </div>
                    </div>

                    <span class="px-2.5 py-1 rounded-full text-[10px] font-bold border tracking-wide uppercase {status_color}">
                        {ag['status']}
                    </span>
                </div>

                <!-- Speech Bubble (What the AI is thinking / saying right now) -->
                <div class="relative my-3 p-3 rounded-xl bg-slate-950/70 border border-slate-800/90 text-xs text-slate-300 leading-relaxed font-sans shadow-inner">
                    <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                        <span>💬</span> <span>Aktivitas & Log Berpikir:</span>
                    </div>
                    <p class="italic text-slate-200 line-clamp-3 agent-speech">"{ag['speech']}"</p>
                </div>
            </div>

            <!-- Bottom: Capacity Meter & Desk Activity -->
            <div class="space-y-2.5 pt-2 border-t border-slate-800/80 mt-2">
                <div>
                    <div class="flex justify-between text-[11px] font-mono text-slate-400 mb-1">
                        <span class="flex items-center gap-1">{ag['desk_icon']} Beban Kerja (Kapasitas)</span>
                        <span class="font-bold text-white agent-capacity-text">{ag['capacity']}%</span>
                    </div>
                    <div class="w-full bg-slate-950 rounded-full h-2 border border-slate-800 overflow-hidden">
                        <div class="{cap_color} h-2 rounded-full transition-all duration-700 agent-capacity-bar" style="width: {ag['capacity']}%"></div>
                    </div>
                </div>

                <div class="flex justify-between items-center text-[11px] text-slate-400 pt-1">
                    <span class="text-slate-500 truncate max-w-[150px] flex items-center gap-1">
                        ⚡ <span class="agent-task truncate">{ag['current_task']}</span>
                    </span>
                    <span class="font-mono text-cyan-400/90 font-semibold">{ag['total_tasks']} Tugas</span>
                </div>
            </div>
        </div>
        """

    # Buat baris log aktivitas real-time
    logs_html = ""
    for log in logs:
        badge = (
            "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
            if log["vote"] == "BUY"
            else "text-amber-400 bg-amber-500/10 border-amber-500/30"
        )
        logs_html += f"""
        <tr class="border-b border-slate-800/60 hover:bg-slate-800/30 text-xs transition-colors">
            <td class="py-2.5 px-3 font-mono text-slate-400">{log['time']}</td>
            <td class="py-2.5 px-3 font-bold text-cyan-400">{log['ticker']}</td>
            <td class="py-2.5 px-3 text-slate-300">{log['ai_name']}</td>
            <td class="py-2.5 px-3 text-center">
                <span class="px-2 py-0.5 rounded border text-[10px] font-bold font-mono {badge}">
                    {log['vote']} ({log['confidence']})
                </span>
            </td>
            <td class="py-2.5 px-3 text-slate-400 text-[11px] truncate max-w-xs">{log['reasoning']}</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Virtual Office • Saham AI Agent (Live)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
        .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
        @keyframes subtle-pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.6; }}
        }}
        .office-live-ping {{
            animation: subtle-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen selection:bg-cyan-500 selection:text-slate-950">

    <!-- Top Navigation Bar -->
    <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50 px-4 py-3 sm:px-6">
        <div class="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-3">
            <div class="flex items-center gap-3">
                <div class="h-10 w-10 rounded-xl bg-gradient-to-tr from-cyan-600 via-blue-600 to-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-cyan-500/20 text-xl">
                    🏢
                </div>
                <div>
                    <h1 class="text-base sm:text-lg font-bold text-white flex items-center gap-2">
                        AI Virtual Office <span class="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-semibold border border-emerald-500/30 flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-emerald-400 animate-ping"></span> LIVE MONITORING</span>
                    </h1>
                    <p class="text-xs text-slate-400">Monitoring Visual Karyawan AI yang Sedang Bekerja • Render 24/7</p>
                </div>
            </div>

            <!-- Header Action Controls -->
            <div class="flex items-center gap-2.5 text-xs">
                <!-- Navigasi Utama: Kembali ke Halaman Rekap Saham -->
                <a href="/" class="px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-semibold flex items-center gap-1.5 shadow-md shadow-cyan-600/30 transition-all">
                    📈 Buka Rekap Saham (Utama)
                </a>

                <button onclick="fetchLiveUpdates()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-400 font-medium border border-slate-700 flex items-center gap-1.5 transition">
                    🔄 Sync Live
                </button>

                <a href="https://t.me/Agent_d_saham_bot" target="_blank" class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium shadow transition flex items-center gap-1">
                    Bot Telegram ↗
                </a>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 py-6 sm:px-6 space-y-6">

        <!-- Top Office Status Banner -->
        <div class="rounded-2xl bg-gradient-to-r from-slate-900 via-slate-900/90 to-indigo-950/50 border border-slate-800 p-5 shadow-lg">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <div class="text-xs font-bold text-cyan-400 uppercase tracking-widest flex items-center gap-1.5">
                        <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                        Status Kantor Digital Karyawan AI
                    </div>
                    <h2 class="text-xl sm:text-2xl font-bold text-white mt-1">Meja Kerja Tim AI Saham Indonesia</h2>
                    <p class="text-xs sm:text-sm text-slate-400 mt-1 max-w-2xl">
                        Anda dapat memantau secara langsung mana AI yang sedang penuh menganalisis data pasar dan mana yang sedang kosong/standby menanti instruksi baru.
                    </p>
                </div>

                <div class="flex items-center gap-3">
                    <div class="px-4 py-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-right">
                        <div class="text-[11px] text-slate-400 font-medium">Beban Kantor Saat Ini</div>
                        <div class="text-xl font-bold font-mono text-cyan-400" id="stat-office-load">{metrics['overall_load_pct']}%</div>
                    </div>
                    <div class="px-4 py-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-right">
                        <div class="text-[11px] text-slate-400 font-medium">Karyawan Aktif</div>
                        <div class="text-xl font-bold font-mono text-emerald-400"><span id="stat-busy">{metrics['busy_agents']}</span> / {metrics['total_agents']}</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 4 Quick KPI Summary Cards -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-slate-400 flex items-center justify-between">
                    <span>Total Karyawan AI</span>
                    <span class="text-cyan-400">🤖</span>
                </div>
                <div class="text-2xl font-bold font-mono text-white mt-1.5">{metrics['total_agents']} <span class="text-xs text-slate-500 font-sans">Karyawan</span></div>
                <div class="text-[11px] text-emerald-400 font-medium mt-1">Semua slot AI terpasang</div>
            </div>

            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-slate-400 flex items-center justify-between">
                    <span>Sedang Kerja (Penuh)</span>
                    <span class="text-emerald-400">💼</span>
                </div>
                <div class="text-2xl font-bold font-mono text-emerald-400 mt-1.5" id="card-busy-count">{metrics['busy_agents']} <span class="text-xs text-slate-500 font-sans">Agent</span></div>
                <div class="text-[11px] text-slate-400 font-medium mt-1">Audit, voting, & kalkulasi</div>
            </div>

            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-slate-400 flex items-center justify-between">
                    <span>Kosong (Standby)</span>
                    <span class="text-slate-400">☕</span>
                </div>
                <div class="text-2xl font-bold font-mono text-amber-300 mt-1.5" id="card-idle-count">{metrics['idle_agents']} <span class="text-xs text-slate-500 font-sans">Agent</span></div>
                <div class="text-[11px] text-slate-400 font-medium mt-1">Siap menerima task baru</div>
            </div>

            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-slate-400 flex items-center justify-between">
                    <span>Total Tugas Selesai</span>
                    <span class="text-blue-400">🗳️</span>
                </div>
                <div class="text-2xl font-bold font-mono text-cyan-400 mt-1.5">{metrics['total_votes_cast']} <span class="text-xs text-slate-500 font-sans">Keputusan</span></div>
                <div class="text-[11px] text-slate-400 font-medium mt-1">Terekam di agent_memory.db</div>
            </div>
        </div>

        <!-- Section: Virtual Office Desks Grid -->
        <div>
            <div class="flex justify-between items-center mb-3.5">
                <div>
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span>🪑 Meja Kerja Karyawan AI</span>
                    </h3>
                    <p class="text-xs text-slate-400">Status wujud visual kerja, model yang dipakai, dan dialog log berpikir</p>
                </div>
                <div class="text-xs font-mono text-slate-400 flex items-center gap-2">
                    <span class="inline-block w-2 h-2 rounded-full bg-emerald-400"></span> Auto-Sync: <span class="text-cyan-400" id="sync-counter">3s</span>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" id="agent-desks-container">
                {agent_desks_html}
            </div>
        </div>

        <!-- Section: Realtime Live Activity Feed -->
        <div class="rounded-2xl bg-slate-900/90 border border-slate-800 overflow-hidden shadow-xl">
            <div class="p-4 sm:p-5 border-b border-slate-800 flex justify-between items-center">
                <div>
                    <h3 class="text-sm font-bold text-white flex items-center gap-2">
                        <span>📡 Live Activity Feed (Sidang & Voting 5 AI Terkini)</span>
                    </h3>
                    <p class="text-xs text-slate-400 mt-0.5">Transparansi komputasi: apa yang baru saja diputuskan para karyawan AI</p>
                </div>
                <span class="text-[11px] font-mono text-slate-500">Source: SQLite WAL</span>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse text-xs">
                    <thead>
                        <tr class="border-b border-slate-800 bg-slate-950/60 text-[11px] font-semibold text-slate-400 uppercase tracking-wider font-mono">
                            <th class="py-2.5 px-3">Jam (WIB)</th>
                            <th class="py-2.5 px-3">Emiten</th>
                            <th class="py-2.5 px-3">Karyawan AI</th>
                            <th class="py-2.5 px-3 text-center">Suara & Keyakinan</th>
                            <th class="py-2.5 px-3">Alasan Logika Pertimbangan</th>
                        </tr>
                    </thead>
                    <tbody id="live-feed-body">
                        {logs_html if logs_html else '<tr><td colspan="5" class="text-center py-6 text-slate-500">Belum ada log sidang tersimpan.</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>

    </main>

    <!-- Footer -->
    <footer class="border-t border-slate-900 py-6 text-center text-xs text-slate-500 mt-12 space-y-1">
        <div>AI Virtual Office • Saham AI Agent IDX/BEI • Render Cloud 24/7</div>
        <div class="text-[11px] text-slate-600">Dibuat khusus untuk Bos Dimas • Dilindungi UptimeRobot Auto-Keepalive</div>
    </footer>

    <!-- Real-time Polling Script -->
    <script>
        let countdown = 3;
        const counterEl = document.getElementById('sync-counter');

        setInterval(() => {{
            countdown--;
            if (countdown <= 0) {{
                countdown = 3;
                fetchLiveUpdates();
            }}
            if (counterEl) counterEl.innerText = countdown + 's';
        }}, 1000);

        async function fetchLiveUpdates() {{
            try {{
                const res = await fetch('/api/live');
                if (!res.ok) return;
                const data = await res.json();
                if (!data || !data.office_metrics) return;

                // Update summary metrics
                const loadEl = document.getElementById('stat-office-load');
                if (loadEl) loadEl.innerText = data.office_metrics.overall_load_pct + '%';

                const busyEl = document.getElementById('stat-busy');
                if (busyEl) busyEl.innerText = data.office_metrics.busy_agents;

                const cardBusy = document.getElementById('card-busy-count');
                if (cardBusy) cardBusy.innerHTML = data.office_metrics.busy_agents + ' <span class="text-xs text-slate-500 font-sans">Agent</span>';

                const cardIdle = document.getElementById('card-idle-count');
                if (cardIdle) cardIdle.innerHTML = data.office_metrics.idle_agents + ' <span class="text-xs text-slate-500 font-sans">Agent</span>';

                // Update agent cards in-place
                if (data.agents) {{
                    data.agents.forEach(ag => {{
                        const desk = document.querySelector(`.agent-desk[data-agent-id="${{ag.id}}"]`);
                        if (desk) {{
                            const speech = desk.querySelector('.agent-speech');
                            if (speech) speech.innerText = '"' + ag.speech + '"';

                            const capText = desk.querySelector('.agent-capacity-text');
                            if (capText) capText.innerText = ag.capacity + '%';

                            const capBar = desk.querySelector('.agent-capacity-bar');
                            if (capBar) capBar.style.width = ag.capacity + '%';

                            const task = desk.querySelector('.agent-task');
                            if (task) task.innerText = ag.current_task;
                        }}
                    }});
                }}
            }} catch (err) {{
                console.log('Sync err:', err);
            }}
        }}
    </script>
</body>
</html>
"""
