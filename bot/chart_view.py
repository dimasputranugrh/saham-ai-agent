import json
from datetime import datetime
from typing import Any, Optional
import pandas as pd
import pytz
import yfinance as yf

import config
from analyzer.technical import analyze_ticker_quant, compute_vwap, scan_watchlist_quant
from analyzer.bandarmologi import analyze_bandarmologi_footprint

WIB = pytz.timezone(config.TIMEZONE)

_PICKS_CACHE = {"timestamp": 0, "data": []}


def get_top_picks(force_refresh: bool = False) -> dict[str, Any]:
    """
    Memindai seluruh watchlist dan mengembalikan daftar saham yang sedang berstatus 'BUY'
    atau memiliki skor kuantitatif tertinggi beserta status bandarmologinya.
    """
    import time
    now = time.time()
    if not force_refresh and _PICKS_CACHE["data"] and (now - _PICKS_CACHE["timestamp"] < 60):
        return {
            "cached": True,
            "updated_at": datetime.fromtimestamp(_PICKS_CACHE["timestamp"], WIB).strftime("%H:%M:%S WIB"),
            "picks": _PICKS_CACHE["data"],
        }

    watchlist = config.load_watchlist()
    snaps = scan_watchlist_quant(watchlist)

    buy_signals = [s for s in snaps if s.direction == "BUY" and s.quant_score >= 60]
    buy_signals.sort(key=lambda x: (x.quant_score, x.reward_to_risk), reverse=True)

    if buy_signals:
        selected = buy_signals
    else:
        # Jika belum ada sinyal BUY murni (misal market libur/sideways),
        # ambil top 4 kandidat dengan skor tertinggi
        selected = snaps[:4] if snaps else []

    picks = []
    for s in selected:
        code = s.ticker.replace(".JK", "")
        picks.append({
            "ticker": code,
            "full_ticker": s.ticker,
            "quant_score": s.quant_score,
            "direction": s.direction,
            "action_label": s.action_label,
            "current_price": s.current_price,
            "change_pct": round(s.change_pct, 2),
            "is_buy": s.direction == "BUY" and s.quant_score >= 60,
            "setup_type": s.setup_type,
            "foreign_flow_status": s.foreign_flow_status,
        })

    _PICKS_CACHE["timestamp"] = now
    _PICKS_CACHE["data"] = picks

    return {
        "cached": False,
        "updated_at": datetime.now(WIB).strftime("%H:%M:%S WIB"),
        "picks": picks,
    }


def get_candlestick_chart_data(ticker: str, timeframe: str = "15m") -> dict[str, Any]:
    """
    Mengambil data candlestick OHLCV historis dan menghitung garis level Entry, TP1, TP2, SL,
    serta VWAP untuk dirender pada TradingView Lightweight Charts.
    """
    clean_ticker = config.normalize_ticker(ticker)
    snap = analyze_ticker_quant(clean_ticker)

    candles = []
    volume_series = []
    vwap_series = []

    try:
        tk = yf.Ticker(clean_ticker)
        if timeframe == "1d":
            df = tk.history(period="6mo", interval="1d", auto_adjust=False)
        else:
            df = tk.history(period="5d", interval="15m", auto_adjust=False)

        if df is not None and not df.empty:
            df = df.dropna(subset=["Close", "High", "Low", "Open"]).copy()
            df["VWAP"] = compute_vwap(df) if timeframe != "1d" else df["Close"].rolling(20).mean()

            for ts, row in df.iterrows():
                if ts.tzinfo is not None:
                    ts_wib = ts.astimezone(WIB)
                else:
                    ts_wib = WIB.localize(ts)

                # Format time: UNIX timestamp in seconds
                unix_time = int(ts_wib.timestamp())
                open_p = float(row["Open"])
                high_p = float(row["High"])
                low_p = float(row["Low"])
                close_p = float(row["Close"])
                vol = float(row["Volume"])
                vwap_val = float(row["VWAP"]) if not pd.isna(row["VWAP"]) else close_p

                color = "#22c55e" if close_p >= open_p else "#ef4444"

                candles.append({
                    "time": unix_time,
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                })
                volume_series.append({
                    "time": unix_time,
                    "value": vol,
                    "color": color + "80",  # 50% opacity
                })
                vwap_series.append({
                    "time": unix_time,
                    "value": round(vwap_val, 1),
                })
    except Exception:
        pass

    levels = {}
    bandar_data = {}
    if snap:
        levels = {
            "current_price": snap.current_price,
            "entry_low": snap.entry_low,
            "entry_high": snap.entry_high,
            "take_profit_1": snap.take_profit_1,
            "take_profit_2": snap.take_profit_2,
            "stop_loss": snap.stop_loss,
            "reward_to_risk": snap.reward_to_risk,
            "quant_score": snap.quant_score,
            "action_label": snap.action_label,
            "setup_type": snap.setup_type,
            "direction": snap.direction,
            "cmf_20": snap.cmf_20,
            "foreign_flow_status": snap.foreign_flow_status,
            "recommended_lots": snap.recommended_lots,
            "trailing_stop_plan": snap.trailing_stop_plan,
        }
        try:
            tk_daily = yf.Ticker(clean_ticker).history(period="1mo", interval="1d")
            bandar_data = analyze_bandarmologi_footprint(clean_ticker, tk_daily, snap.cmf_20, snap.intraday_vol_spike_ratio)
        except Exception:
            pass

    return {
        "ticker": clean_ticker.replace(".JK", ""),
        "full_ticker": clean_ticker,
        "timeframe": timeframe,
        "candles": candles,
        "volumes": volume_series,
        "vwap": vwap_series,
        "levels": levels,
        "bandarmologi": bandar_data,
    }


def render_tradingview_chart_html(default_ticker: str = "BBCA") -> str:
    """Menghasilkan halaman web interaktif lengkap dengan TradingView Lightweight Charts & integrasi TWA."""
    clean_t = default_ticker.upper().replace(".JK", "")
    watchlist = [t.replace(".JK", "") for t in config.load_watchlist()]
    if clean_t not in watchlist:
        watchlist.insert(0, clean_t)
    buttons_html = "\n".join([
        f'            <button onclick="switchTicker(\'{t}\')" class="t-btn px-2.5 py-1 text-xs rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 font-mono transition whitespace-nowrap">{t}</button>'
        for t in watchlist
    ])

    return f"""<!DOCTYPE html>
<html lang="id" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>TradingView Terminal AI • {clean_t}</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    colors: {{
                        idx: {{
                            dark: '#0b0f19',
                            card: '#111827',
                            border: '#1f2937',
                            green: '#22c55e',
                            red: '#ef4444',
                            cyan: '#06b6d4',
                            gold: '#f59e0b',
                            purple: '#a855f7'
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <style>
        body {{
            background-color: #0b0f19;
            color: #f3f4f6;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            overflow-x: hidden;
        }}
        .glass-panel {{
            background: rgba(17, 24, 39, 0.75);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
    </style>
</head>
<body class="p-2 sm:p-4 min-h-screen flex flex-col">

    <!-- Top Bar & Ticker Selector -->
    <header class="glass-panel rounded-xl p-3 mb-3 flex flex-wrap items-center justify-between gap-2 shadow-lg">
        <div class="flex items-center gap-2">
            <span class="inline-block w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
            <h1 class="text-lg sm:text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                TradingView Terminal AI
            </h1>
            <span id="headerTickerBadge" class="text-xs px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-800 text-cyan-300 font-mono font-bold">
                {clean_t}
            </span>
            <button onclick="buyCurrentDemoStock()" id="btnBuyDemoHeader" class="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition shadow-md active:scale-95 cursor-pointer ml-1">
                <span>🛒 Beli Demo (10 Lot)</span>
            </button>
        </div>

        <!-- Search Bar Input Emiten Bebas -->
        <form onsubmit="event.preventDefault(); searchTicker();" class="flex items-center gap-1.5">
            <input type="text" id="tickerSearchInput" placeholder="Ketik kode (cth: BRMS)..." class="bg-gray-900 border border-gray-700 text-gray-200 text-xs px-2.5 py-1 rounded-lg uppercase font-mono focus:outline-none focus:border-cyan-500 w-32 sm:w-44 placeholder-gray-500" />
            <button type="submit" class="bg-cyan-600 hover:bg-cyan-500 text-white text-xs px-2.5 py-1 rounded-lg font-semibold transition">Cari</button>
        </form>

        <!-- Watchlist Buttons Slider (Semua Watchlist) -->
        <div class="flex items-center gap-1.5 overflow-x-auto py-1 max-w-full w-full opacity-80 hover:opacity-100 transition">
            <span class="text-[11px] text-gray-400 font-semibold uppercase shrink-0 mr-1">Semua:</span>
{buttons_html}
        </div>
    </header>

    <!-- Tab Saham Lagi Bagus (Picks) & Tombol Refresh -->
    <div class="glass-panel rounded-xl p-3 mb-3 flex flex-wrap items-center justify-between gap-3 shadow-lg border border-emerald-500/20 bg-gradient-to-r from-emerald-950/20 via-gray-900/60 to-cyan-950/20">
        <div class="flex items-center gap-2 overflow-x-auto py-1 max-w-full flex-1">
            <div class="flex items-center gap-1.5 shrink-0 pr-2 border-r border-gray-800">
                <span class="inline-block w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
                <span class="text-xs font-bold text-emerald-400">🔥 Saham Lagi Bagus:</span>
            </div>
            <div id="topPicksContainer" class="flex items-center gap-2 overflow-x-auto">
                <span class="text-xs text-gray-500 italic py-1">Memindai rekomendasi terbaik...</span>
            </div>
        </div>

        <div class="flex items-center gap-2 shrink-0">
            <button id="btnRefreshPicks" onclick="refreshTopPicks(true)" class="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-md hover:shadow-emerald-500/20 transition active:scale-95 cursor-pointer">
                <span id="refreshIcon" class="inline-block">🔄</span>
                <span>Refresh Saham Bagus</span>
            </button>
            <span id="picksUpdatedTime" class="text-[10px] text-gray-400 font-mono hidden sm:inline"></span>
        </div>
    </div>

    <!-- Key Metrics & Bandarmologi Strip -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        <div class="glass-panel rounded-xl p-2.5">
            <div class="text-[10px] text-gray-400 font-semibold uppercase">Vonis 6 AI</div>
            <div id="metricVonis" class="text-xs sm:text-sm font-bold text-amber-400 mt-0.5 truncate">Memuat...</div>
        </div>
        <div class="glass-panel rounded-xl p-2.5">
            <div class="text-[10px] text-gray-400 font-semibold uppercase">Bandarmologi (Top 3)</div>
            <div id="metricBandar" class="text-xs sm:text-sm font-bold text-emerald-400 mt-0.5 truncate">Memuat...</div>
        </div>
        <div class="glass-panel rounded-xl p-2.5">
            <div class="text-[10px] text-gray-400 font-semibold uppercase">Chaikin Money Flow</div>
            <div id="metricCMF" class="text-xs sm:text-sm font-bold text-cyan-400 mt-0.5 truncate">Memuat...</div>
        </div>
        <div class="glass-panel rounded-xl p-2.5">
            <div class="text-[10px] text-gray-400 font-semibold uppercase">Trailing Stop Plan</div>
            <div id="metricTrailing" class="text-xs sm:text-sm font-bold text-purple-400 mt-0.5 truncate">Memuat...</div>
        </div>
    </div>

    <!-- TradingView Chart Container -->
    <div class="glass-panel rounded-xl p-2 sm:p-3 relative flex-1 min-h-[420px] flex flex-col shadow-2xl">
        <!-- Chart Controls -->
        <div class="flex items-center justify-between pb-2 border-b border-gray-800 text-xs">
            <div class="flex items-center gap-2">
                <span class="text-gray-400 font-medium">Timeframe:</span>
                <button id="tf15m" onclick="switchTimeframe('15m')" class="px-2 py-0.5 rounded bg-cyan-600 text-white font-semibold">15m</button>
                <button id="tf1d" onclick="switchTimeframe('1d')" class="px-2 py-0.5 rounded bg-gray-800 text-gray-300 hover:bg-gray-700">1D Daily</button>
            </div>
            <!-- Legend Indicators -->
            <div class="hidden sm:flex items-center gap-3 text-[11px] font-mono">
                <span class="flex items-center gap-1"><span class="w-2.5 h-0.5 bg-emerald-400 inline-block"></span> TP1 & TP2</span>
                <span class="flex items-center gap-1"><span class="w-2.5 h-0.5 bg-cyan-400 inline-block"></span> Entry</span>
                <span class="flex items-center gap-1"><span class="w-2.5 h-0.5 bg-rose-500 inline-block"></span> Stop Loss</span>
                <span class="flex items-center gap-1"><span class="w-2.5 h-0.5 bg-purple-400 inline-block"></span> VWAP</span>
            </div>
        </div>

        <!-- The Canvas -->
        <div id="chartContainer" class="w-full flex-1 min-h-[360px] mt-1 relative">
            <div id="chartLoader" class="absolute inset-0 flex items-center justify-center bg-gray-950/60 backdrop-blur-sm z-10 text-cyan-400 text-sm font-semibold">
                ⏳ Memuat Candlestick & Garis Level AI...
            </div>
        </div>
    </div>

    <!-- Footer / Navigation -->
    <footer class="mt-3 flex items-center justify-between text-xs text-gray-400">
        <a href="/live" class="hover:text-cyan-400 flex items-center gap-1 transition">
            🏢 <span>Ke Kantor 3D (/live)</span>
        </a>
        <a href="/" class="hover:text-cyan-400 flex items-center gap-1 transition">
            📊 <span>Dashboard Rekap (/)</span>
        </a>
    </footer>

    <script>
        let currentTicker = '{clean_t}';
        let currentTimeframe = '15m';
        let chart = null;
        let candleSeries = null;
        let volumeSeries = null;
        let vwapSeries = null;
        let priceLines = [];

        // Inisialisasi Telegram WebApp SDK jika dibuka via Telegram
        if (window.Telegram && window.Telegram.WebApp) {{
            window.Telegram.WebApp.ready();
            window.Telegram.WebApp.expand();
        }}

        function initChart() {{
            const container = document.getElementById('chartContainer');
            container.innerHTML = '<div id="chartLoader" class="absolute inset-0 flex items-center justify-center bg-gray-950/60 backdrop-blur-sm z-10 text-cyan-400 text-sm font-semibold">⏳ Memuat Candlestick & Garis Level AI...</div>';

            chart = LightweightCharts.createChart(container, {{
                layout: {{
                    background: {{ color: '#0b0f19' }},
                    textColor: '#9ca3af',
                }},
                grid: {{
                    vertLines: {{ color: '#1f2937' }},
                    horzLines: {{ color: '#1f2937' }},
                }},
                crosshair: {{
                    mode: LightweightCharts.CrosshairMode.Normal,
                }},
                rightPriceScale: {{
                    borderColor: '#374151',
                    scaleMargins: {{
                        top: 0.1,
                        bottom: 0.25,
                    }},
                }},
                timeScale: {{
                    borderColor: '#374151',
                    timeVisible: true,
                    secondsVisible: false,
                }},
            }});

            candleSeries = chart.addCandlestickSeries({{
                upColor: '#22c55e',
                downColor: '#ef4444',
                borderVisible: false,
                wickUpColor: '#22c55e',
                wickDownColor: '#ef4444',
            }});

            volumeSeries = chart.addHistogramSeries({{
                color: '#26a69a',
                priceFormat: {{
                    type: 'volume',
                }},
                priceScaleId: '',
                scaleMargins: {{
                    top: 0.8,
                    bottom: 0,
                }},
            }});

            vwapSeries = chart.addLineSeries({{
                color: '#c084fc',
                lineWidth: 1.5,
                title: 'VWAP',
            }});

            window.addEventListener('resize', () => {{
                if (chart) {{
                    chart.applyOptions({{
                        width: container.clientWidth,
                        height: container.clientHeight,
                    }});
                }}
            }});
        }}

        async function loadData() {{
            const loader = document.getElementById('chartLoader');
            if (loader) loader.style.display = 'flex';

            try {{
                const res = await fetch(`/api/chart?ticker=${{currentTicker}}&timeframe=${{currentTimeframe}}`);
                const data = await res.json();

                if (data.candles && data.candles.length > 0) {{
                    candleSeries.setData(data.candles);
                    volumeSeries.setData(data.volumes || []);
                    if (data.vwap && data.vwap.length > 0) {{
                        vwapSeries.setData(data.vwap);
                    }}
                    chart.timeScale().fitContent();
                }}

                // Update Level Overlays
                clearPriceLines();
                const lvl = data.levels || {{}};
                if (lvl.entry_high) {{
                    addPriceLine(lvl.entry_high, '#06b6d4', `Area Beli (Rp ${{lvl.entry_high}})`);
                }}
                if (lvl.take_profit_1) {{
                    addPriceLine(lvl.take_profit_1, '#22c55e', `TP1 (Rp ${{lvl.take_profit_1}})`);
                }}
                if (lvl.take_profit_2) {{
                    addPriceLine(lvl.take_profit_2, '#16a34a', `TP2 (Rp ${{lvl.take_profit_2}})`);
                }}
                if (lvl.stop_loss) {{
                    addPriceLine(lvl.stop_loss, '#ef4444', `Cut Loss (Rp ${{lvl.stop_loss}})`);
                }}

                // Update Top Strips
                document.getElementById('headerTickerBadge').textContent = data.ticker;
                const vonisEl = document.getElementById('metricVonis');
                const vonisText = lvl.action_label || 'WAIT & SEE';
                vonisEl.textContent = vonisText;
                if (vonisText.includes('BUY')) {{
                    vonisEl.className = 'text-xs sm:text-sm font-bold text-emerald-400 mt-0.5 truncate';
                }} else if (vonisText.includes('AVOID') || vonisText.includes('CUT') || vonisText.includes('DOWNTREND')) {{
                    vonisEl.className = 'text-xs sm:text-sm font-bold text-red-400 mt-0.5 truncate';
                }} else {{
                    vonisEl.className = 'text-xs sm:text-sm font-bold text-amber-400 mt-0.5 truncate';
                }}

                document.getElementById('metricCMF').textContent = lvl.cmf_20 !== undefined ? `${{lvl.cmf_20 > 0 ? '+' : ''}}${{lvl.cmf_20}}` : '-';
                document.getElementById('metricTrailing').textContent = lvl.trailing_stop_plan || 'Lock BEP (+0.5%)';

                const bnd = data.bandarmologi || {{}};
                document.getElementById('metricBandar').textContent = bnd.bandar_action || (lvl.foreign_flow_status || 'Netral');

            }} catch (err) {{
                console.error("Gagal load chart:", err);
            }} finally {{
                if (loader) loader.style.display = 'none';
            }}
        }}

        function addPriceLine(price, color, title) {{
            if (!candleSeries) return;
            const line = candleSeries.createPriceLine({{
                price: price,
                color: color,
                lineWidth: 1.5,
                lineStyle: LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: title,
            }});
            priceLines.push(line);
        }}

        function clearPriceLines() {{
            if (!candleSeries) return;
            priceLines.forEach(l => candleSeries.removePriceLine(l));
            priceLines = [];
        }}

        function switchTicker(t) {{
            currentTicker = t.toUpperCase().replace('.JK', '');
            loadData();
            loadTopPicks(false);
        }}

        function searchTicker() {{
            const input = document.getElementById('tickerSearchInput');
            if (input && input.value) {{
                const val = input.value.trim().toUpperCase().replace('.JK', '');
                if (val) {{
                    switchTicker(val);
                    input.value = '';
                }}
            }}
        }}

        async function loadTopPicks(force = false) {{
            const container = document.getElementById('topPicksContainer');
            const refreshBtn = document.getElementById('btnRefreshPicks');
            const refreshIcon = document.getElementById('refreshIcon');
            const timeLabel = document.getElementById('picksUpdatedTime');

            if (force && refreshIcon) refreshIcon.classList.add('animate-spin');
            if (force && refreshBtn) refreshBtn.disabled = true;

            try {{
                const res = await fetch(`/api/picks?refresh=${{force ? '1' : '0'}}`);
                const data = await res.json();
                const picks = data.picks || [];

                if (timeLabel && data.updated_at) {{
                    timeLabel.textContent = `Update: ${{data.updated_at}}`;
                }}

                if (picks.length === 0) {{
                    container.innerHTML = '<span class="text-xs text-amber-400 py-1 font-medium">⚠️ Belum ada saham berstatus BUY kuat saat ini</span>';
                    return;
                }}

                container.innerHTML = picks.map(p => {{
                    const isCurrent = p.ticker === currentTicker;
                    const isBuy = p.is_buy;
                    const badgeBg = isBuy ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300' : 'bg-gray-800 border-gray-700 text-gray-300';
                    const activeRing = isCurrent ? 'ring-2 ring-cyan-400 shadow-md shadow-cyan-500/20 scale-105' : 'hover:border-cyan-600';
                    const icon = isBuy ? '🟢' : '🟡';

                    return `
                        <button onclick="switchTicker('${{p.ticker}}')" class="flex items-center gap-1.5 px-3 py-1 rounded-lg border text-xs font-mono font-bold transition shadow-sm ${{badgeBg}} ${{activeRing}} whitespace-nowrap cursor-pointer">
                            <span>${{icon}} ${{p.ticker}}</span>
                            <span class="text-[10px] px-1.5 py-0.2 rounded bg-black/50 text-cyan-300">${{p.quant_score}} pts</span>
                            <span class="text-[10px] ${{p.change_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}}">${{p.change_pct >= 0 ? '+' : ''}}${{p.change_pct}}%</span>
                        </button>
                    `;
                }}).join('');

            }} catch (err) {{
                console.error("Gagal load saham bagus:", err);
            }} finally {{
                if (refreshIcon) refreshIcon.classList.remove('animate-spin');
                if (refreshBtn) refreshBtn.disabled = false;
            }}
        }}

        function refreshTopPicks(force = true) {{
            loadTopPicks(force);
        }}

        function switchTimeframe(tf) {{
            currentTimeframe = tf;
            document.getElementById('tf15m').className = tf === '15m' ? 'px-2 py-0.5 rounded bg-cyan-600 text-white font-semibold' : 'px-2 py-0.5 rounded bg-gray-800 text-gray-300 hover:bg-gray-700';
            document.getElementById('tf1d').className = tf === '1d' ? 'px-2 py-0.5 rounded bg-cyan-600 text-white font-semibold' : 'px-2 py-0.5 rounded bg-gray-800 text-gray-300 hover:bg-gray-700';
            loadData();
        }}

        async function buyCurrentDemoStock() {{
            const btn = document.getElementById('btnBuyDemoHeader');
            if (btn) btn.innerHTML = '⏳ Membeli...';
            try {{
                const res = await fetch(`/api/portfolio/buy-demo?ticker=${{currentTicker}}&lots=10`);
                const data = await res.json();
                if (data.status === 'ok') {{
                    alert(`✅ BERHASIL BELI DEMO ${{data.ticker}} (10 Lot @ Rp ${{Number(data.price).toLocaleString()}})!\n\n🎯 Damian & Chief Arthur otomatis mengawal:\n• Target TP1: Rp ${{Number(data.tp1).toLocaleString()}}\n• Target TP2: Rp ${{Number(data.tp2).toLocaleString()}}\n• Rem Cut Loss: Rp ${{Number(data.sl).toLocaleString()}}\n\nNotifikasi akan dikirim ke Telegram saat target tercapai!`);
                }}
            }} catch (e) {{
                alert('Gagal mencatat beli demo');
            }} finally {{
                if (btn) btn.innerHTML = '🛒 Beli Demo (10 Lot)';
            }}
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            initChart();
            loadData();
            loadTopPicks(false);
        }});
    </script>
</body>
</html>
"""
