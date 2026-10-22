import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
import pytz

import config


def generate_character_svg(agent: dict) -> str:
    """
    Menghasilkan ilustrasi SVG animasi vektor berkualitas tinggi:
    Karyawan AI duduk di meja kantor dengan dual monitor, keyboard, cangkir kopi,
    dan tangan yang mengetik secara aktif (jika sibuk) atau santai ngopi (jika kosong/idle).
    """
    aid = agent["id"]
    status = agent["status"]
    is_busy = status in ["WORKING", "DECIDING", "AUDITING"]
    shirt_color = agent.get("theme_color", "#06b6d4")
    accent_color = agent.get("accent_color", "#22d3ee")

    # Custom styling accessories per agent
    has_headphone = aid in ["AI_1", "AI_3"]
    has_glasses = aid in ["AI_2", "AI_5", "SARI"]
    has_tie = aid in ["AI_2", "HENDRA"]
    is_judge = aid == "ARIF"

    # Animasi CSS class
    type_l_class = "animate-typing-l" if is_busy else ""
    type_r_class = "animate-typing-r" if is_busy else ""
    screen_chart_class = "animate-chart-glow" if is_busy else "opacity-50"
    head_class = "animate-head-bob" if is_busy else "animate-head-idle"

    # SVG Chart bars untuk monitor utama
    chart_bars = ""
    bar_heights = [18, 28, 22, 35, 30, 42, 38, 50, 45, 58] if is_busy else [20, 22, 21, 24, 20, 22, 23, 21, 22, 20]
    for i, h in enumerate(bar_heights):
        x = 96 + (i * 7)
        y = 115 - h
        color = "#34d399" if i % 3 != 1 else "#f87171"
        chart_bars += f'<rect x="{x}" y="{y}" width="5" height="{h}" rx="1" fill="{color}" opacity="0.85" />'

    # Side monitor terminal lines
    term_lines = ""
    for i in range(5):
        y = 80 + (i * 7)
        w = 30 + ((i * 11) % 25)
        term_lines += f'<rect x="180" y="{y}" width="{w}" height="3" rx="1.5" fill="{accent_color}" opacity="0.75" />'

    # Aksesori khusus meja
    desk_accessory = ""
    if is_judge:
        # Palu Hakim (Gavel) di atas meja
        desk_accessory = """
        <!-- Palu Sidang Hakim Arif -->
        <g transform="translate(255, 142)">
            <rect x="0" y="8" width="22" height="6" rx="2" fill="#d97706" />
            <rect x="8" y="0" width="6" height="22" rx="2" fill="#92400e" transform="rotate(-25 11 11)" />
            <rect x="2" y="20" width="20" height="5" rx="1.5" fill="#78350f" />
        </g>
        """
    else:
        # Cangkir kopi kantor dengan asap mengepul
        steam_anim = """
        <path d="M 270 134 Q 272 128 269 122 Q 267 116 271 110" stroke="#94a3b8" stroke-width="1.5" fill="none" stroke-linecap="round" opacity="0.6">
            <animate attributeName="d" values="M 270 134 Q 272 128 269 122 Q 267 116 271 110; M 270 134 Q 267 128 271 122 Q 274 116 269 110; M 270 134 Q 272 128 269 122 Q 267 116 271 110" dur="2.5s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.2;0.7;0.2" dur="2.5s" repeatCount="indefinite" />
        </path>
        """ if not is_busy else ""

        desk_accessory = f"""
        <!-- Cangkir Kopi Karyawan -->
        <g transform="translate(262, 138)">
            <rect x="0" y="4" width="16" height="18" rx="3" fill="#f8fafc" />
            <rect x="2" y="7" width="12" height="12" rx="2" fill="#3b82f6" opacity="0.3" />
            <!-- Gagang cangkir -->
            <path d="M 16 7 Q 22 10 16 17" stroke="#f8fafc" stroke-width="2.5" fill="none" stroke-linecap="round" />
            {steam_anim}
        </g>
        """

    # Headset jika ada
    headphone_svg = ""
    if has_headphone:
        headphone_svg = """
        <!-- Headset Gaming / Call Center -->
        <path d="M 184 72 A 16 16 0 0 1 216 72" stroke="#38bdf8" stroke-width="3" fill="none" />
        <rect x="181" y="68" width="5" height="12" rx="2" fill="#0284c7" />
        <rect x="214" y="68" width="5" height="12" rx="2" fill="#0284c7" />
        <path d="M 215 76 Q 220 84 212 87" stroke="#38bdf8" stroke-width="1.5" fill="none" />
        <circle cx="211" cy="87" r="2" fill="#38bdf8" />
        """

    # Kacamata jika ada
    glasses_svg = ""
    if has_glasses:
        glasses_svg = """
        <!-- Kacamata Smart -->
        <g stroke="#38bdf8" stroke-width="1.5" fill="rgba(56, 189, 248, 0.15)">
            <rect x="190" y="72" width="8" height="6" rx="2" />
            <rect x="202" y="72" width="8" height="6" rx="2" />
            <line x1="198" y1="75" x2="202" y2="75" />
            <line x1="187" y1="74" x2="190" y2="74" />
            <line x1="210" y1="74" x2="213" y2="74" />
        </g>
        """

    # Dasi jika ada
    tie_svg = ""
    if has_tie:
        tie_svg = """
        <!-- Dasi Formal -->
        <polygon points="199,94 201,94 202,112 200,116 198,112" fill="#ef4444" />
        """

    # Jubah Hakim Arif jika Hakim
    robe_collar = ""
    if is_judge:
        robe_collar = """
        <!-- Kerah Jubah Hakim Emas -->
        <polygon points="192,92 200,105 208,92" fill="#fbbf24" opacity="0.9" />
        <circle cx="200" cy="107" r="2.5" fill="#f59e0b" />
        """

    # Posisi tangan (mengetik vs santai)
    if is_busy:
        hands_svg = f"""
        <!-- Tangan Mengetik di Keyboard (Aktif Bekerja) -->
        <g class="{type_l_class}">
            <!-- Lengan Kiri -->
            <path d="M 178 114 Q 165 132 154 148" stroke="{shirt_color}" stroke-width="8" stroke-linecap="round" fill="none" />
            <!-- Tangan Kiri di atas keyboard -->
            <ellipse cx="154" cy="148" rx="5" ry="4" fill="#fed7aa" />
        </g>
        <g class="{type_r_class}">
            <!-- Lengan Kanan -->
            <path d="M 222 114 Q 235 132 246 148" stroke="{shirt_color}" stroke-width="8" stroke-linecap="round" fill="none" />
            <!-- Tangan Kanan di atas keyboard/mouse -->
            <ellipse cx="246" cy="148" rx="5" ry="4" fill="#fed7aa" />
        </g>
        """
    else:
        hands_svg = f"""
        <!-- Tangan Santai (Mode Standby) -->
        <!-- Lengan Kiri rileks di paha / meja -->
        <path d="M 178 114 Q 170 135 165 150" stroke="{shirt_color}" stroke-width="8" stroke-linecap="round" fill="none" />
        <ellipse cx="165" cy="150" rx="5" ry="4" fill="#fed7aa" />
        <!-- Lengan Kanan memegang meja / dekat kopi -->
        <path d="M 222 114 Q 238 132 250 146" stroke="{shirt_color}" stroke-width="8" stroke-linecap="round" fill="none" />
        <ellipse cx="250" cy="146" rx="5" ry="4" fill="#fed7aa" />
        """

    svg = f"""
    <svg viewBox="0 0 400 220" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" class="select-none overflow-hidden rounded-xl">
        <defs>
            <!-- Gradasi Meja Kayu Premium -->
            <linearGradient id="deskWood_{aid}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#334155" />
                <stop offset="15%" stop-color="#1e293b" />
                <stop offset="100%" stop-color="#0f172a" />
            </linearGradient>

            <!-- Gradasi Cahaya Layar Monitor -->
            <linearGradient id="monitorGlow_{aid}" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#0284c7" stop-opacity="0.25" />
                <stop offset="100%" stop-color="{shirt_color}" stop-opacity="0.05" />
            </linearGradient>

            <!-- Bayangan Halus -->
            <filter id="softShadow_{aid}" x="-10%" y="-10%" width="120%" height="120%">
                <feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#000000" flood-opacity="0.6"/>
            </filter>
        </defs>

        <!-- 1. Dinding & Latar Belakang Ruang Kantor Modern -->
        <rect width="400" height="220" fill="#090d16" />
        <rect x="0" y="160" width="400" height="60" fill="#050811" />
        <!-- Garis partisi kantor minimalis -->
        <line x1="0" y1="160" x2="400" y2="160" stroke="#1e293b" stroke-width="1.5" />
        <!-- Lampu LED Ambient Backlight -->
        <ellipse cx="200" cy="95" rx="140" ry="70" fill="{accent_color}" opacity="0.08" />

        <!-- 2. Kursi Ergonomis Kantor (Mesh Swivel Chair) -->
        <g filter="url(#softShadow_{aid})">
            <!-- Sandaran Kepala Kursi -->
            <rect x="182" y="32" width="36" height="16" rx="6" fill="#1e293b" stroke="#334155" stroke-width="1.5" />
            <!-- Sandaran Punggung Kursi Mesh -->
            <path d="M 166 48 Q 200 45 234 48 L 230 115 Q 200 120 170 115 Z" fill="#1e293b" stroke="#334155" stroke-width="2" />
            <line x1="172" y1="65" x2="228" y2="65" stroke="#334155" stroke-dasharray="3,3" />
            <line x1="174" y1="85" x2="226" y2="85" stroke="#334155" stroke-dasharray="3,3" />
            <line x1="176" y1="105" x2="224" y2="105" stroke="#334155" stroke-dasharray="3,3" />
        </g>

        <!-- 3. Karakter Karyawan AI (Wujud Orang Sedang Duduk) -->
        <g id="employee-body" class="{head_class}">
            <!-- Pundak & Badan Karyawan -->
            <path d="M 162 115 Q 200 95 238 115 L 244 150 L 156 150 Z" fill="{shirt_color}" />
            <!-- Detail Jahitan Baju / Jas -->
            <path d="M 188 98 L 200 118 L 212 98" stroke="#ffffff" stroke-width="1.5" opacity="0.3" fill="none" />
            {robe_collar}
            {tie_svg}

            <!-- Leher -->
            <rect x="194" y="86" width="12" height="12" rx="2" fill="#fed7aa" />

            <!-- Kepala / Wajah Orang -->
            <ellipse cx="200" cy="74" rx="16" ry="18" fill="#fed7aa" />

            <!-- Rambut Stylist Kantor -->
            <path d="M 182 72 Q 183 54 200 54 Q 217 54 218 72 Q 208 64 200 64 Q 192 64 182 72 Z" fill="#1e293b" />

            <!-- Mata Karyawan -->
            <ellipse cx="194" cy="73" rx="2" ry="2.5" fill="#0f172a" />
            <ellipse cx="206" cy="73" rx="2" ry="2.5" fill="#0f172a" />
            <!-- Kacamata / Headphone jika ada -->
            {glasses_svg}
            {headphone_svg}

            <!-- Senyum ramah -->
            <path d="M 197 81 Q 200 84 203 81" stroke="#ea580c" stroke-width="1.2" fill="none" stroke-linecap="round" />
        </g>

        <!-- 4. Tangan Karyawan -->
        {hands_svg}

        <!-- 5. Meja Kerja Kantor (Perspective 3D Top Slabs) -->
        <g filter="url(#softShadow_{aid})">
            <!-- Permukaan Atas Meja -->
            <polygon points="50,150 350,150 375,185 25,185" fill="url(#deskWood_{aid})" stroke="#475569" stroke-width="1" />
            <!-- Sisi Depan Meja -->
            <polygon points="25,185 375,185 375,195 25,195" fill="#0f172a" stroke="#334155" stroke-width="1" />
            <!-- Kaki Meja Besi Minimalis -->
            <rect x="40" y="195" width="8" height="25" fill="#334155" />
            <rect x="352" y="195" width="8" height="25" fill="#334155" />
        </g>

        <!-- 6. Peralatan Kantor di Atas Meja -->
        <!-- Monitor Utama (Menampilkan Chart Saham / Analisis) -->
        <g transform="translate(85, 55)" filter="url(#softShadow_{aid})">
            <!-- Kaki Monitor -->
            <rect x="40" y="70" width="8" height="28" fill="#475569" />
            <rect x="30" y="96" width="28" height="4" rx="2" fill="#334155" />
            <!-- Bingkai Monitor -->
            <rect x="0" y="0" width="88" height="70" rx="4" fill="#0f172a" stroke="#334155" stroke-width="2" />
            <!-- Layar Monitor Nyala -->
            <rect x="3" y="3" width="82" height="64" rx="2" fill="#020617" />
            <!-- Chart Candlestick / Candlestick SVG di dalam Monitor -->
            <g class="{screen_chart_class}">
                {chart_bars}
                <!-- Garis Tren EMA -->
                <path d="M 98 105 Q 120 90 140 98 T 160 70" stroke="#38bdf8" stroke-width="1.5" fill="none" />
            </g>
            <!-- Logo Brand Monitor & LED power -->
            <circle cx="44" cy="67.5" r="1" fill="#38bdf8" />
        </g>

        <!-- Monitor Kedua (Side Monitor Vertikal / Terminal Kode) -->
        <g transform="translate(178, 62)" filter="url(#softShadow_{aid})">
            <rect x="0" y="0" width="46" height="62" rx="3" fill="#0f172a" stroke="#334155" stroke-width="1.5" />
            <rect x="2" y="2" width="42" height="58" rx="2" fill="#030712" />
            <!-- Baris teks data mengalir -->
            {term_lines}
        </g>

        <!-- Keyboard RGB Mekanikal -->
        <g transform="translate(142, 155)">
            <rect x="0" y="0" width="70" height="20" rx="3" fill="#1e293b" stroke="#475569" stroke-width="1" />
            <!-- Tombol keyboard menyala RGB -->
            <line x1="4" y1="5" x2="66" y2="5" stroke="{accent_color}" stroke-width="1.5" stroke-dasharray="4,2" opacity="0.8" />
            <line x1="4" y1="10" x2="66" y2="10" stroke="{shirt_color}" stroke-width="1.5" stroke-dasharray="3,2" opacity="0.8" />
            <line x1="4" y1="15" x2="66" y2="15" stroke="{accent_color}" stroke-width="1.5" stroke-dasharray="5,2" opacity="0.8" />
        </g>

        <!-- Mouse & Mousepad -->
        <g transform="translate(225, 156)">
            <rect x="0" y="0" width="28" height="22" rx="3" fill="#0f172a" stroke="#334155" stroke-width="0.8" />
            <ellipse cx="14" cy="11" rx="5" ry="8" fill="#334155" />
            <line x1="14" y1="5" x2="14" y2="9" stroke="{accent_color}" stroke-width="1" />
        </g>

        <!-- Nameplate Meja Kantor Karyawan -->
        <g transform="translate(48, 172)">
            <polygon points="0,0 75,0 72,10 -3,10" fill="#0f172a" stroke="#e2e8f0" stroke-width="0.6" />
            <text x="6" y="8" font-family="'JetBrains Mono', monospace" font-size="6.5" font-weight="bold" fill="#f8fafc">{aid} • {agent['name'].split()[1] if len(agent['name'].split()) > 1 else agent['name']}</text>
        </g>

        <!-- Aksesori Tambahan (Palu Hakim / Cangkir Kopi) -->
        {desk_accessory}

        <!-- Status Pill Mengambang di Atas Kepala Karakter -->
        <g transform="translate(145, 14)">
            <rect x="0" y="0" width="110" height="18" rx="9" fill="#0f172a" stroke="{'#10b981' if is_busy else '#64748b'}" stroke-width="1.5" filter="url(#softShadow_{aid})" />
            <circle cx="10" cy="9" r="3.5" fill="{'#10b981' if is_busy else '#94a3b8'}" class="{'animate-ping' if is_busy else ''}" />
            <circle cx="10" cy="9" r="3.5" fill="{'#10b981' if is_busy else '#94a3b8'}" />
            <text x="20" y="12.5" font-family="'Plus Jakarta Sans', sans-serif" font-size="8" font-weight="bold" fill="{'#34d399' if is_busy else '#cbd5e1'}">
                {'🔴 SIBUK BEKERJA' if is_busy else '🟢 STANDBY (KOSONG)'}
            </text>
        </g>
    </svg>
    """
    return svg


def get_live_office_data():
    """Mengambil status real-time aktivitas & kapasitas seluruh karyawan AI."""
    db_path = config.MEMORY_DB_PATH
    tz = pytz.timezone(config.TIMEZONE)
    now_dt = datetime.now(tz)
    now_wib = now_dt.strftime("%d %B %Y • %H:%M:%S WIB")

    # Daftar profil karyawan AI lengkap dengan tema warna dan wujud
    agents = [
        {
            "id": "AI_1",
            "name": "AI-1 Gemini Scalper",
            "role": "Volume & Momentum Scalper",
            "model": "Google Gemini 3.6 Flash",
            "avatar": "⚡",
            "theme_color": "#06b6d4",
            "accent_color": "#22d3ee",
            "desc": "Membaca lonjakan volume intraday 15m, posisi harga di atas VWAP, dan breakout cepat.",
            "status": "STANDBY",
            "capacity": 20,
            "current_task": "Menunggu radar lonjakan volume intraday & perintah /cek",
            "speech": "Radar volume intraday aktif. Belum ada lonjakan anomali di jam ini.",
            "total_tasks": 0,
            "desk_icon": "💻",
        },
        {
            "id": "AI_2",
            "name": "AI-2 OpenAI 120B Auditor",
            "role": "Risk & Trap Guard",
            "model": "OpenAI GPT-OSS 120B (Groq)",
            "avatar": "🛡️",
            "theme_color": "#f43f5e",
            "accent_color": "#fb7185",
            "desc": "Mencari potensi bull trap pucuk, spread mahal, dan alasan kuat menahan diri.",
            "status": "STANDBY",
            "capacity": 25,
            "current_task": "Audit risiko portofolio & spread order book",
            "speech": "Disiplin modal adalah nomor satu. Jangan beli di pucuk tanpa konfirmasi.",
            "total_tasks": 0,
            "desk_icon": "📊",
        },
        {
            "id": "AI_3",
            "name": "AI-3 Nemotron 550B Bandar",
            "role": "Smart Money & Flow Tracer",
            "model": "NVIDIA Nemotron 550B (OpenRouter)",
            "avatar": "🐋",
            "theme_color": "#10b981",
            "accent_color": "#34d399",
            "desc": "Menganalisis akumulasi bandar besar dan jejak transaksi institusi pasar modal.",
            "status": "STANDBY",
            "capacity": 30,
            "current_task": "Melacak jejak akumulasi bandar di saham likuid",
            "speech": "Mendeteksi aliran dana rahasia. Mengikuti jejak smart money institusi.",
            "total_tasks": 0,
            "desk_icon": "🖥️",
        },
        {
            "id": "AI_4",
            "name": "AI-4 Qwen 3.8 Trend Guard",
            "role": "Trend Alignment & Swing",
            "model": "Alibaba Qwen 3.8 27B (Groq)",
            "avatar": "📈",
            "theme_color": "#f59e0b",
            "accent_color": "#fbbf24",
            "desc": "Menjaga keselarasan tren EMA harian & rasio Risk/Reward minimal 1:2.",
            "status": "STANDBY",
            "capacity": 15,
            "current_task": "Menghitung jarak Support/Resistance & EMA harian",
            "speech": "Trend adalah sahabat kita. Jangan melawan arah arus besar IHSG.",
            "total_tasks": 0,
            "desk_icon": "📑",
        },
        {
            "id": "AI_5",
            "name": "AI-5 Quant Bayesian Engine",
            "role": "Bayesian Probability Math",
            "model": "Quant Bayesian v1 (Python)",
            "avatar": "🧮",
            "theme_color": "#3b82f6",
            "accent_color": "#60a5fa",
            "desc": "Kalkulasi statistik murni, potongan fee BEI 0.40%, dan probabilitas historis.",
            "status": "STANDBY",
            "capacity": 10,
            "current_task": "Kalibrasi data empiris & potongan fee BEI 0.40%",
            "speech": "Probabilitas matematika siap dikomputasi begitu ada ticker baru.",
            "total_tasks": 0,
            "desk_icon": "🗄️",
        },
        {
            "id": "ARIF",
            "name": "Hakim Ketua Arif",
            "role": "Chief Decider & Consensus",
            "model": "Ensemble Judge (>=3 Buy & >=60%)",
            "avatar": "⚖️",
            "theme_color": "#a855f7",
            "accent_color": "#c084fc",
            "desc": "Memimpin sidang 5 AI, memverifikasi konsensus, & mengetok palu BUY/WAIT.",
            "status": "STANDBY",
            "capacity": 15,
            "current_task": "Menunggu rekap suara 5 AI dari meja analis",
            "speech": "Palu sidang siap diketok. Sidang 5 AI akan dibuka jika ada perintah /cek.",
            "total_tasks": 0,
            "desk_icon": "🔨",
        },
        {
            "id": "BUDI",
            "name": "Budi (Macro & Berita)",
            "role": "News & Macro Hunter",
            "model": "Daily Standup Analyst",
            "avatar": "📰",
            "theme_color": "#0ea5e9",
            "accent_color": "#38bdf8",
            "desc": "Riset perbandingan 30+ artikel berita 7 sektor BEI & sentimen global.",
            "status": "STANDBY",
            "capacity": 35,
            "current_task": "Scanning berita Kontan, Bisnis, CNBC, & Investor.id",
            "speech": "Memantau katalis komoditas, BI rate, dan sentimen sektor.",
            "total_tasks": 0,
            "desk_icon": "☕",
        },
        {
            "id": "SARI",
            "name": "Sari (Screener Saham)",
            "role": "Technical Screener",
            "model": "Daily Standup Screener",
            "avatar": "🎯",
            "theme_color": "#14b8a6",
            "accent_color": "#2dd4bf",
            "desc": "Menyaring kandidat saham aktif dengan likuiditas tinggi.",
            "status": "STANDBY",
            "capacity": 25,
            "current_task": "Menjaga daftar pantau emiten potensial",
            "speech": "Daftar emiten LQ45 & Second Liner siap disaring.",
            "total_tasks": 0,
            "desk_icon": "📋",
        },
        {
            "id": "HENDRA",
            "name": "Hendra (Risk Manager)",
            "role": "Money Management Guard",
            "model": "Daily Standup Controller",
            "avatar": "💼",
            "theme_color": "#f97316",
            "accent_color": "#fb923c",
            "desc": "Memastikan batas alokasi modal simulasi & trailing stop disiplin.",
            "status": "STANDBY",
            "capacity": 15,
            "current_task": "Menjaga batas risiko portofolio simulasi Paper",
            "speech": "Portofolio Paper aman. Tidak ada batas risiko yang dilanggar.",
            "total_tasks": 0,
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
                    ag["capacity"] = min(95, 45 + (ag["total_tasks"] % 40))
                    ag["status"] = "WORKING" if lv["vote_direction"] == "BUY" else "AUDITING"

                elif sid == "ARIF":
                    ag["total_tasks"] = active_analyses_count
                    if last_analysis:
                        t_clean = (last_analysis["ticker"] or "").replace(".JK", "")
                        ag["current_task"] = f"Ketok Palu Sidang: {t_clean} -> {last_analysis['direction']}"
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
    """Merender HTML Virtual Office AI Agent secara visual interaktif, lengkap dengan wujud fisik orang di meja kerja."""
    data = get_live_office_data()
    metrics = data["office_metrics"]
    agents = data["agents"]
    logs = data["recent_logs"]

    # Buat kartu meja kantor + wujud visual orang untuk masing-masing agent
    agent_desks_html = ""
    for ag in agents:
        is_busy = ag["status"] in ["WORKING", "DECIDING", "AUDITING"]
        status_color = (
            "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
            if ag["status"] in ["WORKING", "DECIDING"]
            else ("bg-amber-500/20 text-amber-300 border-amber-500/40" if ag["status"] == "AUDITING" else "bg-slate-700/40 text-slate-300 border-slate-600/40")
        )
        status_dot = (
            "bg-emerald-400 animate-ping"
            if ag["status"] in ["WORKING", "DECIDING"]
            else ("bg-amber-400 animate-ping" if ag["status"] == "AUDITING" else "bg-slate-400")
        )

        cap_color = (
            "bg-gradient-to-r from-emerald-500 to-teal-400"
            if ag["capacity"] < 50
            else ("bg-gradient-to-r from-amber-500 to-orange-400" if ag["capacity"] < 80 else "bg-gradient-to-r from-rose-500 to-pink-500")
        )

        # Generate wujud visual SVG orang lagi kerja di meja!
        desk_svg = generate_character_svg(ag)

        agent_desks_html += f"""
        <div class="agent-desk relative rounded-2xl bg-slate-900/90 border border-slate-800 p-4 sm:p-5 shadow-2xl hover:border-cyan-500/60 transition-all duration-300 flex flex-col justify-between group overflow-hidden" data-agent-id="{ag['id']}">
            <!-- Glow Latar Belakang Meja -->
            <div class="absolute -right-8 -top-8 w-32 h-32 rounded-full blur-3xl opacity-20 pointer-events-none" style="background-color: {ag.get('theme_color', '#06b6d4')}"></div>

            <div>
                <!-- Header Kartu Karyawan -->
                <div class="flex items-start justify-between gap-3 mb-3">
                    <div class="flex items-center gap-3">
                        <div class="relative w-11 h-11 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-2xl shadow-inner group-hover:scale-110 transition-transform">
                            {ag['avatar']}
                            <!-- Active pulse dot -->
                            <span class="absolute -top-1 -right-1 flex h-3 w-3">
                                <span class="{status_dot} absolute inline-flex h-full w-full rounded-full opacity-75"></span>
                                <span class="{status_dot} relative inline-flex rounded-full h-3 w-3"></span>
                            </span>
                        </div>
                        <div>
                            <h3 class="text-sm font-bold text-white group-hover:text-cyan-300 transition-colors flex items-center gap-1.5">
                                {ag['name']}
                            </h3>
                            <div class="text-[11px] font-medium" style="color: {ag.get('accent_color', '#22d3ee')}">{ag['role']}</div>
                            <div class="text-[10px] text-slate-500 font-mono truncate max-w-[170px]">{ag['model']}</div>
                        </div>
                    </div>

                    <span class="px-2.5 py-1 rounded-full text-[10px] font-bold border tracking-wide uppercase {status_color}">
                        {ag['status']}
                    </span>
                </div>

                <!-- WUJUD VISUAL KARYAWAN DI MEJA (SVG ANIMASI) -->
                <div class="my-3 rounded-xl bg-slate-950/90 border border-slate-800/80 p-2 shadow-inner overflow-hidden relative group-hover:border-slate-700 transition-colors">
                    <div class="relative w-full aspect-[400/220] flex items-center justify-center">
                        {desk_svg}
                    </div>
                </div>

                <!-- Thought Bubble / Dialog Balon Berpikir -->
                <div class="relative my-2.5 p-3 rounded-xl bg-slate-950/70 border border-slate-800/90 text-xs text-slate-300 leading-relaxed font-sans shadow-inner">
                    <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                        <span>💬</span> <span>Aktivitas & Log Berpikir Terkini:</span>
                    </div>
                    <p class="italic text-slate-200 line-clamp-3 agent-speech">"{ag['speech']}"</p>
                </div>
            </div>

            <!-- Bottom: Capacity Meter & Desk Activity -->
            <div class="space-y-2 pt-2 border-t border-slate-800/80 mt-2">
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
                    <span class="text-slate-500 truncate max-w-[160px] flex items-center gap-1">
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
    <title>AI Virtual Office • Saham AI Agent (Live Realtime)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
        .font-mono {{ font-family: 'JetBrains Mono', monospace; }}

        /* Keyframes Animasi Tangan Mengetik Aktif */
        @keyframes typeLeft {{
            0%, 100% {{ transform: translateY(0); }}
            50% {{ transform: translateY(-3.5px); }}
        }}
        @keyframes typeRight {{
            0%, 100% {{ transform: translateY(-3.5px); }}
            50% {{ transform: translateY(0); }}
        }}
        .animate-typing-l {{
            animation: typeLeft 0.22s ease-in-out infinite;
        }}
        .animate-typing-r {{
            animation: typeRight 0.22s ease-in-out infinite 0.11s;
        }}

        /* Keyframes Animasi Kepala Fokus */
        @keyframes headBob {{
            0%, 100% {{ transform: translateY(0) rotate(0deg); }}
            50% {{ transform: translateY(-1.5px) rotate(0.4deg); }}
        }}
        @keyframes headIdle {{
            0%, 100% {{ transform: translateY(0); }}
            50% {{ transform: translateY(1.5px); }}
        }}
        .animate-head-bob {{
            animation: headBob 1.6s ease-in-out infinite;
        }}
        .animate-head-idle {{
            animation: headIdle 3s ease-in-out infinite;
        }}

        /* Keyframes Monitor Glow */
        @keyframes chartGlow {{
            0%, 100% {{ filter: drop-shadow(0 0 4px rgba(52, 211, 153, 0.4)); }}
            50% {{ filter: drop-shadow(0 0 10px rgba(56, 189, 248, 0.7)); }}
        }}
        .animate-chart-glow {{
            animation: chartGlow 2s ease-in-out infinite;
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
                        AI Virtual Office <span class="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-semibold border border-emerald-500/30 flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-emerald-400 animate-ping"></span> LIVE SAAS</span>
                    </h1>
                    <p class="text-xs text-slate-400">Monitoring Wujud Karyawan AI yang Sedang Bekerja • Render 24/7</p>
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
                        Ruang Kerja Digital Karyawan AI Saham
                    </div>
                    <h2 class="text-xl sm:text-2xl font-bold text-white mt-1">Virtual Floor: Meja & Wujud Karyawan AI</h2>
                    <p class="text-xs sm:text-sm text-slate-400 mt-1 max-w-2xl">
                        Setiap AI memiliki wujud visual duduk di mejanya masing-masing dengan dual monitor. Saat ada perintah analisis saham, tangan mereka mengetik cepat di keyboard dan monitor menyala aktif. Saat kosong, mereka santai di meja.
                    </p>
                </div>

                <div class="flex items-center gap-3">
                    <div class="px-4 py-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-right">
                        <div class="text-[11px] text-slate-400 font-medium">Beban Kantor Saat Ini</div>
                        <div class="text-xl font-bold font-mono text-cyan-400" id="stat-office-load">{metrics['overall_load_pct']}%</div>
                    </div>
                    <div class="px-4 py-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-right">
                        <div class="text-[11px] text-slate-400 font-medium">Karyawan Bekerja</div>
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
                <div class="text-[11px] text-emerald-400 font-medium mt-1">9 Meja Kerja Lengkap</div>
            </div>

            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-slate-400 flex items-center justify-between">
                    <span>Sedang Kerja (Penuh)</span>
                    <span class="text-emerald-400">💼</span>
                </div>
                <div class="text-2xl font-bold font-mono text-emerald-400 mt-1.5" id="card-busy-count">{metrics['busy_agents']} <span class="text-xs text-slate-500 font-sans">Agent</span></div>
                <div class="text-[11px] text-slate-400 font-medium mt-1">Mengetik & Analisis Pasar</div>
            </div>

            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-slate-400 flex items-center justify-between">
                    <span>Kosong (Standby)</span>
                    <span class="text-slate-400">☕</span>
                </div>
                <div class="text-2xl font-bold font-mono text-amber-300 mt-1.5" id="card-idle-count">{metrics['idle_agents']} <span class="text-xs text-slate-500 font-sans">Agent</span></div>
                <div class="text-[11px] text-slate-400 font-medium mt-1">Siap Menerima Tugas Baru</div>
            </div>

            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-slate-400 flex items-center justify-between">
                    <span>Total Tugas Selesai</span>
                    <span class="text-blue-400">🗳️</span>
                </div>
                <div class="text-2xl font-bold font-mono text-cyan-400 mt-1.5">{metrics['total_votes_cast']} <span class="text-xs text-slate-500 font-sans">Keputusan</span></div>
                <div class="text-[11px] text-slate-400 font-medium mt-1">Tersimpan di SQLite</div>
            </div>
        </div>

        <!-- Section: Wujud Visual Meja Kerja Karyawan Grid -->
        <div>
            <div class="flex justify-between items-center mb-3.5">
                <div>
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span>🪑 Wujud Visual Meja Kerja 9 Karyawan AI</span>
                    </h3>
                    <p class="text-xs text-slate-400">Perhatikan animasi tangan mengetik di keyboard dan chart monitor saat karyawan sedang bekerja</p>
                </div>
                <div class="text-xs font-mono text-slate-400 flex items-center gap-2">
                    <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> Auto-Sync: <span class="text-cyan-400" id="sync-counter">3s</span>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5" id="agent-desks-container">
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
                <span class="text-[11px] font-mono text-slate-500">Database: agent_memory.db</span>
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
        <div>AI Virtual Office SaaS • Saham AI Agent BEI • Render Cloud 24/7</div>
        <div class="text-[11px] text-slate-600">Dibuat khusus untuk Bos Dimas • UptimeRobot Keepalive Protected</div>
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

                const loadEl = document.getElementById('stat-office-load');
                if (loadEl) loadEl.innerText = data.office_metrics.overall_load_pct + '%';

                const busyEl = document.getElementById('stat-busy');
                if (busyEl) busyEl.innerText = data.office_metrics.busy_agents;

                const cardBusy = document.getElementById('card-busy-count');
                if (cardBusy) cardBusy.innerHTML = data.office_metrics.busy_agents + ' <span class="text-xs text-slate-500 font-sans">Agent</span>';

                const cardIdle = document.getElementById('card-idle-count');
                if (cardIdle) cardIdle.innerHTML = data.office_metrics.idle_agents + ' <span class="text-xs text-slate-500 font-sans">Agent</span>';

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
