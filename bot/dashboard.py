import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
import pytz

import config


def _resolve_db_path() -> Path | None:
    candidates = [
        Path(config.MEMORY_DB_PATH),
        config.BASE_DIR / "data" / "agent_memory.db",
        Path.cwd() / "data" / "agent_memory.db",
        Path("/app/data/agent_memory.db"),
    ]
    for p in candidates:
        try:
            if p.exists() and p.is_file() and p.stat().st_size > 1024:
                return p
        except Exception:
            continue
    return None


def get_dashboard_summary():
    """Mengambil data rekap harga dan analisis terkini dari SQLite agent_memory.db dengan fallback live scan."""
    db_path = _resolve_db_path()

    recap_items = []
    sectors = []
    buy_count = 0
    wait_count = 0

    if db_path is not None:
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # 1. Ambil rekap analisis terbaru per ticker
            sql_recap = """
            SELECT a.*, s.price as last_price, s.vwap, s.rsi, s.ihsg_regime
            FROM analysis_history a
            LEFT JOIN market_snapshots s ON a.snapshot_id = s.snapshot_id
            WHERE a.rowid IN (
                SELECT MAX(rowid) FROM analysis_history GROUP BY ticker
            )
            ORDER BY CASE WHEN a.direction = 'BUY' THEN 1 ELSE 2 END, a.rowid DESC
            """
            rows = cur.execute(sql_recap).fetchall()

            for r in rows:
                direction = r["direction"] or "WAIT"
                if direction == "BUY":
                    buy_count += 1
                else:
                    wait_count += 1

                entry = float(r["entry_price"] or 0)
                tp1 = float(r["take_profit_1"] or 0)
                tp2 = float(r["take_profit_2"] or 0)
                sl = float(r["stop_loss"] or 0)

                tp1_pct = ((tp1 - entry) / entry * 100) if entry > 0 else 0
                tp2_pct = ((tp2 - entry) / entry * 100) if entry > 0 else 0
                sl_pct = ((sl - entry) / entry * 100) if entry > 0 else 0

                # Waktu format WIB ramah manusia
                created_wib = r["created_at_wib"] or ""
                time_display = created_wib
                try:
                    if "T" in created_wib:
                        dt_obj = datetime.fromisoformat(created_wib)
                        time_display = dt_obj.strftime("%d %b, %H:%M WIB")
                except Exception:
                    pass

                recap_items.append({
                    "ticker": r["ticker"].replace(".JK", ""),
                    "full_ticker": r["ticker"],
                    "sector": r["sector"] or "UMUM",
                    "direction": direction,
                    "entry_price": f"Rp {entry:,.0f}".replace(",", "."),
                    "entry_num": entry,
                    "tp1": f"Rp {tp1:,.0f}".replace(",", ".") if tp1 > 0 else "-",
                    "tp1_pct": f"+{tp1_pct:.1f}%" if tp1 > 0 else "-",
                    "tp2": f"Rp {tp2:,.0f}".replace(",", ".") if tp2 > 0 else "-",
                    "tp2_pct": f"+{tp2_pct:.1f}%" if tp2 > 0 else "-",
                    "sl": f"Rp {sl:,.0f}".replace(",", ".") if sl > 0 else "-",
                    "sl_pct": f"{sl_pct:.1f}%" if sl > 0 else "-",
                    "confidence_pct": int((r["calibrated_confidence"] or 0.5) * 100),
                    "rsi": f"{r['rsi']:.1f}" if r["rsi"] else "-",
                    "time_display": time_display,
                })

            # 2. Ambil Radar Sektor
            sql_sectors = """
            SELECT sector_label, catalyst_direction, positive_signals, negative_signals, captured_at_wib
            FROM sector_news_investigations
            ORDER BY rowid DESC
            LIMIT 7
            """
            sec_rows = cur.execute(sql_sectors).fetchall()
            for s in sec_rows:
                sectors.append({
                    "label": s["sector_label"],
                    "direction": s["catalyst_direction"],
                    "pos": s["positive_signals"],
                    "neg": s["negative_signals"],
                })

            conn.close()
        except Exception:
            pass

    # Failsafe Live Fallback jika DB belum terisi / kosong di container cloud
    if not recap_items:
        try:
            from analyzer.technical import scan_watchlist_quant
            watchlist = config.load_watchlist()
            snapshots = scan_watchlist_quant(watchlist)
            for s in snapshots:
                code = s.ticker.replace(".JK", "")
                direction = s.direction or "WAIT"
                if direction == "BUY":
                    buy_count += 1
                else:
                    wait_count += 1
                entry = float(s.current_price or 0)
                tp1 = float(s.take_profit_1 or 0)
                tp2 = float(s.take_profit_2 or 0)
                sl = float(s.stop_loss or 0)
                tp1_pct = ((tp1 - entry) / entry * 100) if entry > 0 else 0
                tp2_pct = ((tp2 - entry) / entry * 100) if entry > 0 else 0
                sl_pct = ((sl - entry) / entry * 100) if entry > 0 else 0
                sec = config.SECTOR_MAP.get(s.ticker.upper(), "UMUM")
                recap_items.append({
                    "ticker": code,
                    "full_ticker": s.ticker,
                    "sector": sec,
                    "direction": direction,
                    "entry_price": f"Rp {entry:,.0f}".replace(",", "."),
                    "entry_num": entry,
                    "tp1": f"Rp {tp1:,.0f}".replace(",", ".") if tp1 > 0 else "-",
                    "tp1_pct": f"+{tp1_pct:.1f}%" if tp1 > 0 else "-",
                    "tp2": f"Rp {tp2:,.0f}".replace(",", ".") if tp2 > 0 else "-",
                    "tp2_pct": f"+{tp2_pct:.1f}%" if tp2 > 0 else "-",
                    "sl": f"Rp {sl:,.0f}".replace(",", ".") if sl > 0 else "-",
                    "sl_pct": f"{sl_pct:.1f}%" if sl > 0 else "-",
                    "confidence_pct": s.quant_score,
                    "rsi": f"{s.intraday_rsi:.1f}",
                    "time_display": "Live Scan",
                })
        except Exception:
            pass

    if not sectors:
        try:
            from analyzer.news import scan_all_sectors_news_and_catalysts
            sec_radar = scan_all_sectors_news_and_catalysts(articles_per_sector=2)
            for s in sec_radar:
                sectors.append({
                    "label": s.get("sector_label", s.get("sector_name", "")),
                    "direction": s.get("catalyst_direction", "NEUTRAL"),
                    "pos": s.get("positive_signals", 0),
                    "neg": s.get("negative_signals", 0),
                })
        except Exception:
            pass

    now_wib = datetime.now(pytz.timezone(config.TIMEZONE)).strftime("%d %B %Y • %H:%M:%S WIB")

    return {
        "recap_items": recap_items,
        "sectors": sectors,
        "stats": {
            "total": len(recap_items),
            "buy_count": buy_count,
            "wait_count": wait_count,
        },
        "last_updated": now_wib,
    }


def render_dashboard_html():
    """Merender HTML halaman monitoring rekap harga saham yang responsif & modern."""
    data = get_dashboard_summary()
    items = data["recap_items"]
    stats = data["stats"]
    sectors = data["sectors"]

    # Table rows
    table_rows_html = ""
    for it in items:
        badge_class = (
            "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
            if it["direction"] == "BUY"
            else "bg-amber-500/20 text-amber-400 border-amber-500/40"
        )
        badge_icon = "🟢 BUY" if it["direction"] == "BUY" else "🟡 WAIT"

        table_rows_html += f"""
        <tr class="border-b border-slate-800 hover:bg-slate-800/40 transition-colors stock-row" data-direction="{it['direction']}">
            <td class="py-3 px-4 font-bold text-white flex items-center gap-2">
                <a href="/chart?ticker={it['ticker']}" class="text-base text-cyan-400 hover:text-cyan-300 hover:underline font-bold" title="Buka Chart {it['ticker']}">{it['ticker']}</a>
                <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400">{it['sector']}</span>
            </td>
            <td class="py-3 px-4 text-center">
                <span class="inline-block text-xs font-semibold px-2.5 py-1 rounded-full border {badge_class}">
                    {badge_icon}
                </span>
            </td>
            <td class="py-3 px-4 text-right font-mono font-medium text-slate-200">
                {it['entry_price']}
            </td>
            <td class="py-3 px-4 text-right font-mono text-emerald-400">
                {it['tp1']} <span class="text-xs font-sans text-emerald-500/80 font-bold">({it['tp1_pct']})</span>
            </td>
            <td class="py-3 px-4 text-right font-mono text-cyan-400">
                {it['tp2']} <span class="text-xs font-sans text-cyan-500/80 font-bold">({it['tp2_pct']})</span>
            </td>
            <td class="py-3 px-4 text-right font-mono text-rose-400">
                {it['sl']} <span class="text-xs font-sans text-rose-500/80 font-bold">({it['sl_pct']})</span>
            </td>
            <td class="py-3 px-4 text-center font-mono text-slate-300 text-xs">
                {it['rsi']}
            </td>
            <td class="py-3 px-4 text-center">
                <div class="w-full bg-slate-800 rounded-full h-2">
                    <div class="bg-cyan-500 h-2 rounded-full" style="width: {it['confidence_pct']}%"></div>
                </div>
                <span class="text-[10px] text-slate-400 font-mono mt-0.5 block">{it['confidence_pct']}%</span>
            </td>
            <td class="py-3 px-4 text-right text-xs text-slate-400 font-mono">
                {it['time_display']}
            </td>
            <td class="py-3 px-4 text-center">
                <a href="/chart?ticker={it['ticker']}" class="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500 hover:text-white text-emerald-400 text-xs font-semibold border border-emerald-500/30 transition inline-flex items-center gap-1 shadow-sm">
                    📊 Chart
                </a>
            </td>
        </tr>
        """

    # Sector cards
    sectors_html = ""
    for sec in sectors:
        is_pos = "POSITIF" in sec["direction"].upper()
        is_neg = "NEGATIF" in sec["direction"].upper() or "WASPADA" in sec["direction"].upper()
        color_class = "text-emerald-400 border-emerald-500/30 bg-emerald-500/5" if is_pos else (
            "text-rose-400 border-rose-500/30 bg-rose-500/5" if is_neg else "text-amber-300 border-amber-500/30 bg-amber-500/5"
        )
        sectors_html += f"""
        <div class="p-3 rounded-lg border {color_class}">
            <div class="text-xs font-semibold text-slate-300 truncate">{sec['label']}</div>
            <div class="text-[11px] font-bold mt-1">{sec['direction']}</div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Monitoring Saham AI Agent • Recap Harga</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
        .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
    <!-- Top Header -->
    <header class="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-50 px-4 py-3 sm:px-6">
        <div class="max-w-7xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-3">
            <div class="flex items-center gap-3">
                <div class="h-9 w-9 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white shadow-lg shadow-cyan-500/20">
                    📈
                </div>
                <div>
                    <h1 class="text-lg font-bold text-white flex items-center gap-2">
                        Saham AI Agent <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-semibold border border-emerald-500/30">● 24/7 LIVE</span>
                    </h1>
                    <p class="text-xs text-slate-400">Monitoring & Rekap Harga Saham BEI • 6 AI Ensemble</p>
                </div>
            </div>

            <div class="flex items-center gap-2.5 text-xs">
                <span class="text-slate-400 font-mono hidden md:inline">Terakhir Sync: <span class="text-slate-200">{data['last_updated']}</span></span>
                <!-- Tombol ke Halaman Terminal Chart AI (TradingView) -->
                <a href="/chart" class="px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold flex items-center gap-1.5 shadow-md shadow-emerald-600/30 transition-all">
                    📊 Terminal Chart AI
                </a>
                <!-- Tombol ke Halaman Live Virtual Office Karyawan AI -->
                <a href="/live" class="px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold flex items-center gap-1.5 shadow-md shadow-cyan-600/30 transition-all">
                    🏢 Kantor AI (Live)
                </a>
                <button onclick="location.reload()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-400 font-medium border border-slate-700 flex items-center gap-1.5 transition">
                    🔄 Refresh
                </button>
                <a href="https://t.me/Agent_d_saham_bot" target="_blank" class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium shadow transition">
                    Chat Telegram ↗
                </a>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 py-6 sm:px-6 space-y-6">
        <!-- Quick Stats Cards -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-slate-400">Total Saham Direkap</div>
                <div class="text-2xl font-bold font-mono text-white mt-1">{stats['total']} <span class="text-xs text-slate-500 font-sans">Emiten</span></div>
            </div>
            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-emerald-400">Sinyal BUY Aktif</div>
                <div class="text-2xl font-bold font-mono text-emerald-400 mt-1">{stats['buy_count']} <span class="text-xs text-slate-500 font-sans">Emiten</span></div>
            </div>
            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-amber-400">Sinyal WAIT (Wait & See)</div>
                <div class="text-2xl font-bold font-mono text-amber-400 mt-1">{stats['wait_count']} <span class="text-xs text-slate-500 font-sans">Emiten</span></div>
            </div>
            <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 shadow-sm">
                <div class="text-xs font-medium text-cyan-400">Mode Eksekusi</div>
                <div class="text-2xl font-bold font-mono text-cyan-400 mt-1">{config.EXECUTION_MODE} <span class="text-xs text-slate-500 font-sans">({'Aman' if config.EXECUTION_MODE == 'PAPER' else 'HATI-HATI'})</span></div>
            </div>
        </div>

        <!-- Main Monitoring Table Card -->
        <div class="rounded-xl bg-slate-900/80 border border-slate-800 overflow-hidden shadow-lg">
            <div class="p-4 sm:p-5 border-b border-slate-800 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                <div>
                    <h2 class="text-base font-bold text-white">Rekap Harga & Target Analisis Saham</h2>
                    <p class="text-xs text-slate-400 mt-0.5">Dihitung otomatis oleh 6 AI panel (Gemini, OpenAI, NVIDIA, Qwen, Quant-Bayesian, Pattern Master)</p>
                </div>

                <div class="flex items-center gap-2">
                    <button onclick="filterTable('ALL')" id="btn-all" class="filter-btn text-xs px-2.5 py-1 rounded bg-cyan-600 text-white font-medium">Semua</button>
                    <button onclick="filterTable('BUY')" id="btn-buy" class="filter-btn text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium">Hanya BUY</button>
                    <button onclick="filterTable('WAIT')" id="btn-wait" class="filter-btn text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium">Hanya WAIT</button>
                </div>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse text-sm">
                    <thead>
                        <tr class="border-b border-slate-800 bg-slate-950/50 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                            <th class="py-3 px-4">Saham</th>
                            <th class="py-3 px-4 text-center">Rekomendasi</th>
                            <th class="py-3 px-4 text-right">Harga Entry Rekap</th>
                            <th class="py-3 px-4 text-right">Target 1 (TP1)</th>
                            <th class="py-3 px-4 text-right">Target 2 (TP2)</th>
                            <th class="py-3 px-4 text-right">Stop Loss (SL)</th>
                            <th class="py-3 px-4 text-center">RSI</th>
                            <th class="py-3 px-4 text-center w-28">% Works</th>
                            <th class="py-3 px-4 text-right">Waktu Rekap</th>
                            <th class="py-3 px-4 text-center">Chart</th>
                        </tr>
                    </thead>
                    <tbody id="table-body">
                        {table_rows_html if table_rows_html else '<tr><td colspan="10" class="text-center py-8 text-slate-500">Belum ada data rekap tersimpan.</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- 7 Sectors Radar Card -->
        <div class="rounded-xl bg-slate-900/80 border border-slate-800 p-4 sm:p-5">
            <h3 class="text-sm font-bold text-white mb-1">Radar Sentimen & Berita 7 Sektor BEI</h3>
            <p class="text-xs text-slate-400 mb-3.5">Hasil investigasi perbandingan 30+ artikel berita keuangan nasional</p>
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
                {sectors_html}
            </div>
        </div>
    </main>

    <footer class="border-t border-slate-900 py-4 text-center text-xs text-slate-500">
        Saham AI Agent IDX/BEI • Dibuat khusus untuk Bos Dimas • Berjalan di Cloud 24/7
    </footer>

    <script>
        function filterTable(type) {{
            const rows = document.querySelectorAll('.stock-row');
            const btns = document.querySelectorAll('.filter-btn');
            btns.forEach(b => {{
                b.classList.remove('bg-cyan-600', 'text-white');
                b.classList.add('bg-slate-800', 'text-slate-300');
            }});

            const activeBtn = document.getElementById(type === 'ALL' ? 'btn-all' : (type === 'BUY' ? 'btn-buy' : 'btn-wait'));
            if (activeBtn) {{
                activeBtn.classList.remove('bg-slate-800', 'text-slate-300');
                activeBtn.classList.add('bg-cyan-600', 'text-white');
            }}

            rows.forEach(r => {{
                if (type === 'ALL' || r.getAttribute('data-direction') === type) {{
                    r.style.display = '';
                }} else {{
                    r.style.display = 'none';
                }}
            }});
        }}

        // Auto refresh setiap 60 detik jika halaman terbuka
        setTimeout(() => {{
            location.reload();
        }}, 60000);
    </script>
</body>
</html>
"""
