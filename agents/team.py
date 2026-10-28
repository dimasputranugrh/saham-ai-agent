import json
from datetime import datetime
import pytz
from google import genai
from google.genai import types

import config
from agents.ai_panel import (
    FREE_REPLACEMENT_MODELS_CATALOG,
    format_panel_consensus_section,
    generate_weekly_ai_leaderboard_report,
    run_5_ai_panel_consensus,
)
from analyzer.technical import (
    TechnicalSnapshot,
    get_ihsg_overview,
    scan_watchlist_quant,
    analyze_ticker_quant,
    compute_sector_rotation_matrix,
)
from analyzer.news import (
    fetch_market_news_indonesia,
    fetch_ticker_news,
    scan_all_sectors_news_and_catalysts,
)
from memory.learning_loop import LearningLoopOrchestrator
from memory.performance import PerformanceAnalyzer


def _analyze_with_panel(
    orchestrator: LearningLoopOrchestrator,
    snap: TechnicalSnapshot,
    ihsg_info: dict,
    timeframe: str,
    horizon_bars: int,
    horizon_minutes: int,
    use_live_llm: bool,
    news_context: str = "",
) -> tuple[dict | None, dict | None]:
    """Single decision layer: panel runs first, then one immutable prediction is saved."""
    ctx = orchestrator.analyze_and_record_with_memory(
        ticker=snap.ticker,
        snap=snap,
        ihsg_info=ihsg_info,
        news_context=news_context,
        timeframe=timeframe,
        horizon_bars=horizon_bars,
        horizon_minutes=horizon_minutes,
        execution_mode=config.EXECUTION_MODE,
        save_prediction=False,
    )
    if ctx is None:
        return None, None

    try:
        panel = run_5_ai_panel_consensus(
            snap=snap,
            ihsg_info=ihsg_info,
            mem_ctx=ctx,
            db=orchestrator.db,
            use_live_llm=use_live_llm,
        )
    except Exception:
        panel = {
            "votes": [],
            "buy_count": 0,
            "total_ai": 0,
            "agreement_pct": 0.0,
            "works_pct": 0.0,
            "final_decision": "WAIT",
            "verdict_label": "⚠️ Panel AI gagal dijalankan; keputusan memakai filter kuantitatif.",
            "chief_summary": "Panel tidak tersedia, jadi guard kuantitatif/memori yang menentukan.",
            "debate": {},
        }

    base = str(ctx.get("final_direction", "WAIT"))
    panel_decision = str(panel.get("final_decision", "WAIT"))
    regime = str(ihsg_info.get("regime", "NEUTRAL")).upper()

    if regime in ("BEARISH_DOWNTREND", "BULLISH_PULLBACK") and (base == "BUY" or panel_decision == "BUY"):
        final_decision = "WAIT"
        panel["final_decision"] = "WAIT"
        panel["verdict_label"] = f"🔴 DITAHAN REZIM IHSG ({regime})"
        panel["chief_summary"] = (
            f"Kondisi IHSG ({regime}) memiliki win rate historis sangat rendah (<8%). "
            "Semua pembelian baru ditahan menjadi WAIT demi mengamankan modal Bos."
        )
    else:
        in_cd, cd_reason = orchestrator.db.is_ticker_in_cooldown(snap.ticker)
        if in_cd and (base == "BUY" or panel_decision == "BUY"):
            final_decision = "WAIT"
            panel["final_decision"] = "WAIT"
            panel["verdict_label"] = "🔴 DITAHAN COOLDOWN LOSS BERUNTUN"
            panel["chief_summary"] = (
                f"{cd_reason} Pembelian baru ditahan menjadi WAIT agar modal tidak tergerus saham yang sedang downtrend."
            )
        elif base == "AVOID":
            final_decision = "AVOID"
        elif base == "BUY" and panel_decision == "BUY":
            final_decision = "BUY"
        else:
            final_decision = "WAIT"

    if final_decision != panel_decision:
        panel["final_decision"] = final_decision
        panel["verdict_label"] = (
            f"🔴 DITAHAN OLEH FILTER KUANTITATIF/MEMORI "
            f"({panel['buy_count']}/{panel['total_ai']} AI Setuju — {panel['works_pct']:.1f}% Works)"
        )
        panel["chief_summary"] = (
            f"Panel ingin {panel_decision}, tetapi guard strategi/memori menetapkan {final_decision}. "
            "Keputusan yang disimpan adalah versi yang lebih konservatif."
        )

    ctx = orchestrator.record_final_prediction(ctx, final_decision, panel["votes"])
    return ctx, panel


def _get_gemini_client():
    api_key = config.GEMINI_API_KEY
    if not api_key or api_key.startswith("masukkan_"):
        return None
    try:
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=8000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    except Exception:
        return None


def _generate_with_gemini(contents: str, system_instruction: str, temperature: float = 0.2) -> str | None:
    """Memanggil Gemini AI dengan perpindahan instan antar-model (<0.5 detik) jika salah satu model sedang sibuk."""
    client = _get_gemini_client()
    if not client:
        return None
    models_to_try = [
        config.GEMINI_MODEL,
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.5-flash",
    ]
    seen = set()
    for model_name in models_to_try:
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                ),
            )
            if resp and resp.text:
                return resp.text.strip()
        except Exception:
            continue
    return None


def _fmt_rp(val: float, is_idx: bool = True) -> str:
    if is_idx:
        return f"Rp {val:,.0f}".replace(",", ".")
    return f"${val:,.2f}"


def generate_morning_dsu_report(tickers: list[str] | None = None) -> str:
    """
    Menjalankan rapat pagi DSU (Daily Standup Update) dari 4 Karyawan AI:
    1. Bastian (Head of Macro & Sector Intel)
    2. Serena (VP of Technical Screener)
    3. Damian (Chief Risk Officer & Money Management)
    4. Chief Arthur (Supreme Decider / Kesimpulan Saham Pilihan Hari Ini)
    """
    watchlist = tickers or config.load_watchlist()
    orchestrator = LearningLoopOrchestrator()
    # Jalankan evaluasi atas prediksi sebelumnya yang sudah melewati horizon waktu
    try:
        orchestrator.run_evaluation_and_learning_cycle()
    except Exception:
        pass

    ihsg = get_ihsg_overview()
    snapshots = scan_watchlist_quant(watchlist)
    sector_matrix = compute_sector_rotation_matrix(snapshots)
    news_list = fetch_market_news_indonesia(max_items=12)
    sector_news_radar = scan_all_sectors_news_and_catalysts(articles_per_sector=5)
    try:
        orchestrator.db.save_sector_news_investigations(sector_news_radar)
    except Exception:
        pass
    wib_now = datetime.now(pytz.timezone("Asia/Jakarta")).strftime("%A, %d %b %Y - %H:%M WIB")

    top_picks = snapshots[:4]
    avoid_list = [s for s in snapshots if s.quant_score < 48][:2]

    # Rekam snapshot & prediksi awal ke database persistent memory + ambil memori relevan
    enriched_picks = []
    news_summary_str = "; ".join([n.get("title", "") for n in news_list[:3]])
    for s in top_picks:
        try:
            ctx, panel_res = _analyze_with_panel(
                orchestrator=orchestrator,
                snap=s,
                ihsg_info=ihsg,
                timeframe="15m",
                horizon_bars=16,
                horizon_minutes=240,
                use_live_llm=False,
                news_context=news_summary_str,
            )
            if ctx and panel_res:
                d_snap = s.to_dict()
                d_snap["final_direction"] = panel_res["final_decision"]
                d_snap["calibrated_confidence"] = ctx["calibrated_confidence"]
                d_snap["confidence_basis"] = ctx["confidence_basis"]
                d_snap["historical_memories"] = ctx["memory_bundle"]["memories"]
                d_snap["panel_5_ai_consensus"] = {
                    "suara_setuju_beli": f"{panel_res['buy_count']}/{panel_res['total_ai']} AI ({panel_res['agreement_pct']:.0f}%)",
                    "works_pct": panel_res["works_pct"],
                    "vonis_hakim_ketua": panel_res["verdict_label"],
                    "masukan_5_ai": [
                        f"{v['ai_name']}: {v['vote_direction']} ({v['confidence_pct']:.0f}%) - {v['reasoning_summary']}"
                        for v in panel_res["votes"]
                    ],
                }
                enriched_picks.append(d_snap)
            else:
                enriched_picks.append(s.to_dict())
        except Exception:
            enriched_picks.append(s.to_dict())

    if top_picks:
        prompt_data = {
            "waktu_rapat_wib": wib_now,
            "kondisi_ihsg": ihsg,
            "matriks_rotasi_sektor_panas_vs_dingin": sector_matrix[:5],
            "berita_pasar_hari_ini": news_list,
            "radar_perbandingan_berita_7_sektor_bei": sector_news_radar,
            "top_kandidat_saham_kuantitatif_dan_memori": enriched_picks,
            "saham_rawan_koreksi": [s.to_dict() for s in avoid_list],
        }
        system_instruction = (
            "Anda adalah sistem 4 Karyawan AI pribadi yang melapor ke Bos (pemula yang tidak mengerti istilah rumit saham).\n"
            "meskipun di belakang layar Anda memakai perhitungan matematika canggih (VWAP, RSI, MACD, ATR) dan Database Memori Historis, "
            "SAAT MELAPOR KE BOS GUNAKAN 'BAHASA BAYI' / BAHASA SEHARI-HARI YANG SUPER GAMPANG DIPAHAMI ANAK KECIL!\n\n"
            "Peran 4 Karyawan AI:\n"
            "1. 👨‍💻 *Bastian (Head of Macro & Berita Sektor)*: Jelaskan fakta terukur vs interpretasi pakai analogi sederhana. Sebutkan bukti pendukung, bukti penentang, serta hasil sidang 6 AI.\n"
            "2. 👩‍💼 *Serena (VP of Screener & Volume Radar)*: Bandingkan BANYAK artikel dari `radar_perbandingan_berita_7_sektor_bei` (jangan cuma 1-2 artikel!). Jelaskan hukum sebab-akibat berita hari ini ke berbagai sektor (misal: kebijakan cukai rokok -> HMSP/GGRM/WIIM, suku bunga -> bank, harga emas/batu bara -> tambang, insentif -> properti/konsumer).\n"
            "3. 🛡️ *Damian (Chief Risk Officer / Penjaga Modal)*: Kasih panduan super jelas untuk:\n"
            "   - ⚡ *Peluang Cepat (Scalping / Intraday Hari Ini)*\n"
            "   - 🌱 *Peluang Masa Depan (Swing / Tabungan Saham Mingguan-Bulanan dari Sektor yang Punya Katalis Bagus)*\n"
            "   - 🛒 *Beli di Harga Berapa:* (`entry_low` - `entry_high`)\n"
            "   - 💰 *Jual Ambil Untung (Cuan) di Harga Berapa:* (`take_profit_1` & `take_profit_2` beserta return bersih setelah fee)\n"
            "   - 🛑 *Rem Darurat / Pembatal Sinyal:* (`stop_loss` & `invalidation_conditions`)\n"
            "4. 🎯 *Chief Arthur (Supreme Decider / Kesimpulan)*: Kasih keputusan tegas (`BUY` atau `WAIT`) untuk jangka pendek (Scalping) dan jangka menengah/masa depan!\n\n"
            "ATURAN KERAS:\n"
            "- DILARANG MENGARANG ANGKA HARGA! Gunakan 100% angka Rupiah dari JSON.\n"
            "- Pisahkan fakta data nyata, interpretasi, dan asumsi biaya transaksi."
        )
        ai_text = _generate_with_gemini(
            contents=f"Buat laporan DSU (Daily Standup Update) pagi untuk Bos berdasarkan data kuantitatif & berita berikut:\n{json.dumps(prompt_data, ensure_ascii=False)}",
            system_instruction=system_instruction,
            temperature=0.2,
        )
        if ai_text:
            return ai_text

    # Fallback Kuantitatif Terstruktur (Tetap akurat 100% walau tanpa kuota/key LLM)
    lines = [
        "📋 *LAPORAN DSU (DAILY STANDUP UPDATE) TIM AI*",
        f"🕒 _{wib_now}_",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "👩‍💼 *1. SARI (Analis Makro & Berita Pasar):*",
        f"• *Kondisi Pasar:* {ihsg.get('summary', 'Data IHSG terpantau stabil')}",
    ]
    if news_list:
        lines.append("• *Highlight Berita Hari Ini:*")
        for n in news_list[:3]:
            lines.append(f"  ◦ _{n['title']}_")
    else:
        lines.append("• *Sentimen:* Fokus pada pergerakan teknikal & aliran volume intraday.")

    if sector_matrix:
        hot = sector_matrix[0]
        cold = sector_matrix[-1]
        lines.append(
            f"• *Rotasi Sektor:* Sektor Terpanas: *{hot['sector']}* ({hot['flow_status']}, CMF {hot['avg_cmf']:+.2f}) | "
            f"Sektor Terdingin: *{cold['sector']}* ({cold['flow_status']})"
        )

    lines.extend([
        "",
        "👨‍💻 *2. BUDI (Analis Teknikal & Kuantitatif):*",
        f"Sudah memindai *{len(snapshots)} saham* di watchlist Bos. Berikut saham dengan skor algoritma tertinggi hari ini:",
    ])

    for idx, s in enumerate(top_picks[:3], start=1):
        code = s.ticker.replace(".JK", "")
        lines.extend([
            f"\n*{idx}. {code}* — Skor: *{s.quant_score}/100* ({s.action_label})",
            f"   • Harga Terakhir: *{_fmt_rp(s.current_price, s.is_idx)}* ({s.change_pct:+.2f}%)",
            f"   • VWAP Intraday: {_fmt_rp(s.intraday_vwap, s.is_idx)} | RSI 15m: {s.intraday_rsi} | Vol Ratio: {max(s.daily_vol_ratio, s.intraday_vol_spike_ratio):.1f}x",
            f"   • Sinyal: {', '.join(s.signals_detected[:2])}",
        ])

    lines.extend([
        "",
        "🛡️ *3. HENDRA (Manajer Risiko & Jam Eksekusi):*",
    ])
    for s in top_picks[:3]:
        code = s.ticker.replace(".JK", "")
        lines.extend([
            f"📌 *Trading Plan {code}:*",
            f"   • 🛒 *Area Beli:* {_fmt_rp(s.entry_low, s.is_idx)} – {_fmt_rp(s.entry_high, s.is_idx)}",
            f"   • 🎯 *Target TP1 / TP2:* {_fmt_rp(s.take_profit_1, s.is_idx)} / {_fmt_rp(s.take_profit_2, s.is_idx)}",
            f"   • 🛑 *Cut Loss (SL):* < {_fmt_rp(s.stop_loss, s.is_idx)} (R/R 1:{s.reward_to_risk})",
            f"   • ⏰ *Jam Beli:* {s.best_execution_window}",
            f"   • 🔔 *Kapan/Jam Jual:* {s.best_sell_window}",
        ])

    lines.extend([
        "",
        "🎯 *4. ARIF (Kepala Riset / Kesimpulan Bos):*",
    ])
    if top_picks and top_picks[0].quant_score >= 65:
        best = top_picks[0].ticker.replace(".JK", "")
        lines.append(
            f"Bos, fokus utama hari ini ada pada *{best}* (Skor {top_picks[0].quant_score}/100). "
            "Disarankan tunggu 15 menit pertama setelah bursa buka (jam 09:15 WIB) untuk konfirmasi harga bertahan di atas VWAP sebelum masuk."
        )
    else:
        lines.append(
            "Bos, pasar saat ini cenderung konsolidasi. Disarankan disiplin *Buy on Weakness* di area Support yang sudah dihitung Hendra dan jangan FOMO."
        )

    return "\n".join(lines)


def analyze_single_stock_with_team(ticker_input: str) -> str:
    """
    Meminta ke-4 karyawan AI membedah 1 saham secara mendalam (Intraday + Swing + Berita + Jam Beli).
    """
    norm_ticker = config.normalize_ticker(ticker_input)
    snap = analyze_ticker_quant(norm_ticker)
    if snap is None:
        return (
            f"⚠️ Maaf Bos, data untuk kode saham *{ticker_input.upper()}* ({norm_ticker}) "
            "tidak ditemukan di Yahoo Finance. Pastikan kode saham benar (contoh: `/cek BBCA` atau `/cek ANTM`)."
        )

    news_items = fetch_ticker_news(norm_ticker, max_items=4)
    code = snap.ticker.replace(".JK", "")

    orchestrator = LearningLoopOrchestrator()
    try:
        orchestrator.run_evaluation_and_learning_cycle()
    except Exception:
        pass

    ihsg_info = get_ihsg_overview()
    news_str = "; ".join([n.get("title", "") for n in news_items[:3]])
    mem_ctx, panel_consensus = _analyze_with_panel(
        orchestrator=orchestrator,
        snap=snap,
        ihsg_info=ihsg_info,
        timeframe="15m",
        horizon_bars=16,
        horizon_minutes=240,
        use_live_llm=True,
        news_context=news_str,
    )
    if panel_consensus is None:
        panel_consensus = {
            "votes": [], "buy_count": 0, "total_ai": 0, "agreement_pct": 0.0,
            "works_pct": 0.0, "final_decision": snap.direction,
            "verdict_label": "⚠️ Panel AI tidak tersedia", "chief_summary": "",
            "debate": {},
        }
    panel_section_md = format_panel_consensus_section(panel_consensus)

    payload = {
        "data_teknikal_kuantitatif": snap.to_dict(),
        "berita_emiten_terbaru": news_items,
        "memori_pembelajaran_historis": mem_ctx["memory_bundle"] if mem_ctx else {},
        "calibrated_confidence": mem_ctx["calibrated_confidence"] if mem_ctx else 0.5,
        "confidence_basis": mem_ctx["confidence_basis"] if mem_ctx else "",
        "final_direction_after_memory": panel_consensus["final_decision"],
        "hasil_sidang_5_ai": {
            "suara_setuju_beli": f"{panel_consensus['buy_count']}/{panel_consensus['total_ai']} AI ({panel_consensus['agreement_pct']:.0f}%)",
            "persentase_works": f"{panel_consensus['works_pct']:.1f}%",
            "vonis_hakim_ketua": panel_consensus["verdict_label"],
            "detail_suara_5_ai": panel_consensus["votes"],
        },
    }
    sys_inst = (
        "Anda adalah tim 4 Karyawan AI saham pribadi untuk Bos yang pemula (tidak paham istilah rumit saham).\n"
        "Jawab dengan 'BAHASA BAYI' (bahasa sehari-hari yang super simpel, pakai perumpamaan belanja/pasar), "
        "NAMUN tetap jujur memisahkan Fakta Data, Interpretasi, Asumsi Biaya, Bukti Pendukung vs Penentang, dan Pengalaman Memori Historis.\n"
        "Susunan Laporan:\n"
        "1. 👨‍💻 *Bastian (Pemantau Harga, Bukti Pendukung vs Penentang, & Memori)*: Jelaskan fakta harga sekarang, bukti yang mendukung naik, bukti yang menentang/risiko (seperti spread atau posisi di bawah rata-rata), dan pelajaran dari `memori_pembelajaran_historis`.\n"
        "2. 👩‍💼 *Serena (Pemantau Gosip & Berita)*: Jelaskan berita terbaru saham ini dan cuaca IHSG dengan bahasa obrolan santai.\n"
        "3. 🛡️ *Damian (Penjaga Dompet Bos)*: Berikan contekan angka pasti dari JSON `data_teknikal_kuantitatif` (DILARANG MENGARANG ANGKA):\n"
        "   - 💵 *Harga Sekarang:* `current_price` (Waktu data: `last_bar_time`)\n"
        "   - 🛒 *Harga Beli (Cicil/Serok):* `entry_low` sampai `entry_high`\n"
        "   - 💰 *Target Jual Untung (Ambil Cuan):* `take_profit_1` & `take_profit_2` (Estimasi untung bersih setelah potongan biaya transaksi: `estimated_net_return_pct`%)\n"
        "   - 🛑 *Rem Darurat & Pembatal Sinyal:* `stop_loss` (`invalidation_conditions`)\n"
        "   - 🎯 *Tingkat Keyakinan Terkalibrasi:* `calibrated_confidence` (`confidence_basis`)\n"
        "4. 🎯 *Chief Arthur (Supreme Decider / Kesimpulan Jam Beli & Jam Jual)*: Gunakan keputusan dari `hasil_sidang_5_ai` (**BUY** atau **WAIT**) beserta **JAM BERAPA BELINYA** (`best_execution_window`) dan **KAPAN / JAM BERAPA HARUS JUALNYA** (`best_sell_window`)!"
    )
    ai_text = _generate_with_gemini(
        contents=f"Berikan laporan analisis untuk saham {code}:\n{json.dumps(payload, ensure_ascii=False)}",
        system_instruction=sys_inst,
        temperature=0.2,
    )
    if ai_text:
        return f"{ai_text}\n\n━━━━━━━━━━━━━━━━━━━━━━\n{panel_section_md}"

    # Fallback laporan presisi
    lines = [
        f"🔍 *BEDAH SAHAM {code} ({snap.ticker})*",
        f"🕒 _Data Candle Terakhir: {snap.last_bar_time}_",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Harga Saat Ini:* *{_fmt_rp(snap.current_price, snap.is_idx)}* ({snap.change_pct:+.2f}%)",
        f"📊 *Skor Kuantitatif AI:* *{snap.quant_score}/100* — *{snap.action_label}*",
        "",
        "👨‍💻 *BUDI (Analis Teknikal Intraday & Swing):*",
        f"• *Status Intraday (15m):* {snap.intraday_status}",
        f"• *VWAP Hari Ini:* {_fmt_rp(snap.intraday_vwap, snap.is_idx)} | EMA9: {_fmt_rp(snap.intraday_ema9, snap.is_idx)} | EMA21: {_fmt_rp(snap.intraday_ema21, snap.is_idx)}",
        f"• *Tren Harian (Swing):* {snap.daily_trend}",
        f"• *EMA20 / EMA50 Daily:* {_fmt_rp(snap.daily_ema20, snap.is_idx)} / {_fmt_rp(snap.daily_ema50, snap.is_idx)}",
        f"• *RSI (Daily / 15m):* {snap.daily_rsi} / {snap.intraday_rsi}",
        f"• *Lonjakan Volume:* {max(snap.daily_vol_ratio, snap.intraday_vol_spike_ratio):.2f}x rata-rata",
        "• *Sinyal Terdeteksi:*",
    ]
    for sig in snap.signals_detected:
        lines.append(f"  ✓ {sig}")

    lines.extend([
        "",
        "👩‍💼 *SARI (Analis Berita & Sentimen):*",
    ])
    if news_items:
        for n in news_items[:3]:
            lines.append(f"• _{n['title']}_")
    else:
        lines.append("• Belum ada rilis berita krusial baru dalam 7 hari terakhir; pergerakan murni didorong teknikal/bandarmologi.")

    lines.extend([
        "",
        "🛡️ *HENDRA (Manajer Risiko & Trading Plan):*",
        f"• 🧱 *Support 1 / 2:* {_fmt_rp(snap.support_1, snap.is_idx)} / {_fmt_rp(snap.support_2, snap.is_idx)}",
        f"• 🚧 *Resistance 1 / 2:* {_fmt_rp(snap.resistance_1, snap.is_idx)} / {_fmt_rp(snap.resistance_2, snap.is_idx)}",
        f"• 🛒 *Area Beli (Entry):* *{_fmt_rp(snap.entry_low, snap.is_idx)} – {_fmt_rp(snap.entry_high, snap.is_idx)}*",
        f"• 🎯 *Target Jual 1 (TP1):* *{_fmt_rp(snap.take_profit_1, snap.is_idx)}* (Kotor: +{snap.estimated_gross_return_pct:.1f}%, Bersih setelah fee: *+{snap.estimated_net_return_pct:.1f}%*)",
        f"• 🚀 *Target Jual 2 (TP2):* *{_fmt_rp(snap.take_profit_2, snap.is_idx)}* (+{((snap.take_profit_2 - snap.entry_high)/snap.entry_high*100):.1f}%)",
        f"• 🛑 *Batas Cut Loss (SL):* *< {_fmt_rp(snap.stop_loss, snap.is_idx)}* (-{snap.estimated_risk_pct:.1f}%)",
        f"• ⚖️ *Reward/Risk Ratio:* 1 : {snap.reward_to_risk} | *Spread 1 Tick:* {snap.spread_pct:.2f}%",
        f"• 🎲 *Keyakinan Terkalibrasi:* {(mem_ctx['calibrated_confidence']*100 if mem_ctx else 50.0):.1f}% ({mem_ctx['confidence_basis'] if mem_ctx else 'Prior'})",
        f"• ⚠️ *Pembatal Sinyal:* {snap.invalidation_conditions}",
        "",
        "🎯 *ARIF (Rekomendasi Jam Beli & Jam Jual):*",
        f"• 📌 *Keputusan Akhir:* *{mem_ctx['final_direction'] if mem_ctx else snap.direction}*",
        f"• ⏰ *Jam Beli:* {snap.best_execution_window}",
        f"• 🔔 *Waktu/Jam Jual:* {snap.best_sell_window}",
    ])
    if mem_ctx and mem_ctx["memory_bundle"]["memories"]:
        lines.extend(["", "🧠 *MEMORI PEMBELAJARAN HISTORIS TERKAIT:*"])
        for m in mem_ctx["memory_bundle"]["memories"][:2]:
            lines.append(f"• [{m['validity_level']}] {m['lesson']}")
    lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━━", panel_section_md])
    return "\n".join(lines)


def generate_intraday_scanner_alert(min_score: int | None = None) -> tuple[list[TechnicalSnapshot], str]:
    """
    Memindai watchlist pada jam bursa untuk mencari saham yang layak dibeli JAM SEGINI.
    Mengembalikan (daftar kandidat lolos, pesan laporan Telegram).
    """
    threshold = min_score if min_score is not None else config.MIN_INTRADAY_ALERT_SCORE
    watchlist = config.load_watchlist()
    orchestrator = LearningLoopOrchestrator()
    try:
        orchestrator.run_evaluation_and_learning_cycle()
    except Exception:
        pass

    ihsg_info = get_ihsg_overview()
    snapshots = scan_watchlist_quant(watchlist)
    wib_now = datetime.now(pytz.timezone("Asia/Jakarta")).strftime("%H:%M WIB")

    qualified = [s for s in snapshots if s.quant_score >= threshold and s.direction == "BUY"]
    top_3 = qualified[:3] if qualified else snapshots[:3]

    panel_by_ticker: dict[str, dict] = {}
    for s in top_3:
        try:
            ctx, panel = _analyze_with_panel(
                orchestrator=orchestrator,
                snap=s,
                ihsg_info=ihsg_info,
                timeframe="15m",
                horizon_bars=16,
                horizon_minutes=240,
                use_live_llm=False,
            )
            if panel is not None:
                panel_by_ticker[s.ticker] = panel
        except Exception:
            pass

    header = (
        f"🚨 *INFO SAHAM BAGUS JAM INI ({wib_now})*\n"
        f"Bos! Ada *{len(qualified)} saham* yang lagi ramai diborong & bagus dipantau sekarang:"
        if qualified
        else f"📡 *PANTAUAN PASAR JAM INI ({wib_now})*\nBelum ada saham yang ngebut banget, tapi ini 3 saham paling mendingan saat ini:"
    )

    lines = [header, "━━━━━━━━━━━━━━━━━━━━━━"]
    for idx, s in enumerate(top_3, start=1):
        code = s.ticker.replace(".JK", "")
        tp1_pct = ((s.take_profit_1 - s.entry_high) / s.entry_high * 100) if s.entry_high > 0 else 0
        sl_pct = ((s.stop_loss - s.entry_high) / s.entry_high * 100) if s.entry_high > 0 else 0
        kondisi_simpel = (
            "Lagi ramai diborong di atas harga rata-rata hari ini 👍"
            if s.current_price >= s.intraday_vwap
            else "Harga lagi agak turun, tunggu antri murah di bawah 👇"
        )
        p_res = panel_by_ticker.get(s.ticker)
        voting_line = (
            f"   • 🗳️ *Suara 6 AI:* *{p_res['buy_count']}/{p_res['total_ai']} AI Setuju Beli* (*{p_res['works_pct']:.1f}% Works*) ➡️ {p_res['final_decision']}"
            if p_res
            else f"   • 🗳️ *Keputusan:* {s.direction}"
        )
        lines.extend([
            f"\n*{idx}. Saham {code}* — Nilai: *{s.quant_score}/100*",
            f"   • 💵 *Harga Sekarang:* *{_fmt_rp(s.current_price, s.is_idx)}* ({s.change_pct:+.2f}%)",
            voting_line,
            f"   • 👀 *Kondisi:* {kondisi_simpel}",
            f"   • 🛒 *Beli di Harga:* *{_fmt_rp(s.entry_low, s.is_idx)} – {_fmt_rp(s.entry_high, s.is_idx)}*",
            f"   • 💰 *Jual Untung (Cuan) di:* *{_fmt_rp(s.take_profit_1, s.is_idx)}* (+{tp1_pct:.1f}%) atau *{_fmt_rp(s.take_profit_2, s.is_idx)}*",
            f"   • 🛑 *Rem Darurat (Jual kalau turun ke):* *< {_fmt_rp(s.stop_loss, s.is_idx)}* ({sl_pct:.1f}%)",
            f"   • ⏰ *Kapan Beli:* {s.best_execution_window}",
            f"   • 🔔 *Kapan Jual:* {s.best_sell_window}",
        ])

    # Cek juga apakah ada saham yang sedang dipegang Bos yang sudah waktunya dijual!
    sell_alerts = evaluate_portfolio_sell_signals()
    if sell_alerts:
        lines.extend(["\n━━━━━━━━━━━━━━━━━━━━━━", sell_alerts])

    lines.append("\n💡 _Ketik `/beli KODE HARGA` (contoh: `/beli BBCA 5250`) kalau Bos sudah beli, nanti Damian & Chief Arthur yang pantau kapan harus jual!_")
    return qualified, "\n".join(lines)


def evaluate_portfolio_sell_signals(force_all: bool = False) -> str:
    """
    Mengecek daftar saham yang sedang dipegang Bos (dari perintah /beli)
    dan memberi tahu apakah JAM SEGINI sudah waktunya JUAL atau TAHAN DULU.
    """
    portfolio = config.load_portfolio()
    if not portfolio:
        if force_all:
            return (
                "💼 *Dompet Saham Bos Masih Kosong*\n\n"
                "Kalau Bos habis beli saham, lapor ke kami dengan ketik:\n"
                "👉 `/beli KODE HARGA_BELI` (Contoh: `/beli BBCA 5250`)\n\n"
                "Nanti setiap jam bursa, *Damian & Chief Arthur* akan otomatis memantau harganya dan memberi tahu di Telegram kalau sudah waktunya **JUAL AMBIL UNTUNG** atau **REM DARURAT**!"
            )
        return ""

    wib_now = datetime.now(pytz.timezone("Asia/Jakarta"))
    hour_float = wib_now.hour + wib_now.minute / 60.0
    lines = ["💼 *PANTAUAN WAKTU JUAL SAHAM BOS:*"]
    urgent_count = 0

    for norm_ticker, info in portfolio.items():
        snap = analyze_ticker_quant(norm_ticker)
        if not snap:
            continue
        code = norm_ticker.replace(".JK", "")
        buy_price = float(info.get("buy_price", snap.current_price))
        tp1 = float(info.get("tp1", snap.take_profit_1))
        tp2 = float(info.get("tp2", snap.take_profit_2))
        sl = float(info.get("sl", snap.stop_loss))
        cur = snap.current_price
        pnl_pct = ((cur - buy_price) / buy_price * 100.0) if buy_price > 0 else 0.0

        if cur >= tp2:
            urgent_count += 1
            status_jual = "🚀 *WAKTUNYA JUAL SEKARANG (Target Cuan Besar Tercapai!)*"
            saran = f"Harga sudah tembus Target 2 ({_fmt_rp(tp2, snap.is_idx)}). Segera buka aplikasi dan jual sekarang buat amankan untung *+{pnl_pct:.1f}%*!"
        elif cur >= tp1:
            urgent_count += 1
            status_jual = "💰 *WAKTUNYA JUAL AMBIL UNTUNG (Target 1 Tercapai!)*"
            saran = f"Harga sudah sampai target jual ({_fmt_rp(tp1, snap.is_idx)}). Boleh jual semua sekarang (untung *+{pnl_pct:.1f}%*) atau jual separuh!"
        elif pnl_pct >= 2.0:
            urgent_count += 1
            bep_price = round(buy_price * 1.005)
            status_jual = "🛡️ *KAWAL CUAN: NAIKKAN STOP LOSS KE BEP*"
            saran = (
                f"Bos sudah cuan *+{pnl_pct:.1f}%*! Segera geser Stop Loss ke harga modal "
                f"({_fmt_rp(bep_price, snap.is_idx)} / BEP +0.5%). Posisi sekarang sudah bebas risiko rugi!"
            )
        elif pnl_pct >= 2.5 and 15.25 <= hour_float <= 16.0:
            urgent_count += 1
            status_jual = "🔔 *JUAL SORE SEBELUM PASAR TUTUP (Amankan Uang Jajan!)*"
            saran = f"Sekarang sudah jam sore menjelang tutup pasar dan Bos sudah untung *+{pnl_pct:.1f}%*. Boleh bungkus untungnya sekarang (jam 15:30-15:45 WIB)!"
        elif cur <= sl:
            urgent_count += 1
            status_jual = "🛑 *PERINGATAN REM DARURAT! WAKTUNYA JUAL RUGI DIKIT*"
            saran = f"Harga turun ke {_fmt_rp(cur, snap.is_idx)} (melewati batas aman {_fmt_rp(sl, snap.is_idx)}). Jika sudah jam 15:30-15:45 WIB masih di bawah angka ini, wajib jual dulu biar modal tidak nyangkut dalam."
        else:
            status_jual = "⏳ *TAHAN / SIMPAN DULU (Belum Waktunya Jual)*"
            saran = (
                f"Pasang antrian jual otomatis di *{_fmt_rp(tp1, snap.is_idx)}*. "
                f"Biasanya harga naik kencang di jam *09:15-10:00 WIB* atau *14:30-15:45 WIB*. "
                f"Batas rem darurat di *{_fmt_rp(sl, snap.is_idx)}*."
            )

        lines.extend([
            f"\n📌 *{code}* (Modal Beli: {_fmt_rp(buy_price, snap.is_idx)} ➡️ Sekarang: *{_fmt_rp(cur, snap.is_idx)}* | *{pnl_pct:+.2f}%*)",
            f"   • Status: {status_jual}",
            f"   • Panduan Chief Arthur: {saran}",
        ])

    if not force_all and urgent_count == 0:
        return ""
    lines.append("\n_Ketik `/jual KODE` (contoh: `/jual BBCA`) jika sahamnya sudah Bos jual._")
    return "\n".join(lines)


def chat_with_ai_team(user_message: str) -> str:
    """
    Menjawab pertanyaan bebas dari Bos di Telegram (dengan konteks data watchlist terkini).
    """
    watchlist = config.load_watchlist()

    # Cek apakah user menyebut kode saham 4 huruf di pesannya
    words = [w.strip(".,?!").upper() for w in user_message.split()]
    mentioned_snapshots = []
    for w in words:
        if len(w) == 4 and w.isalpha() and w not in {"HARI", "SAYA", "BELI", "JUAL", "YANG", "MANA", "PAGI", "SORE", "JAM", "APA", "BISA", "DONG", "BANG", "KALO", "BUAT", "DARI", "SAMA", "ATAU"}:
            snap = analyze_ticker_quant(config.normalize_ticker(w))
            if snap:
                mentioned_snapshots.append(snap.to_dict())

    if not mentioned_snapshots:
        # Ambil ringkasan top 4 dari watchlist
        snaps = scan_watchlist_quant(watchlist[:6])
        mentioned_snapshots = [s.to_dict() for s in snaps[:4]]

    orchestrator = LearningLoopOrchestrator()
    knowledge_ctx = orchestrator.db.get_recent_knowledge_and_sector_news(limit=6)

    ai_text = _generate_with_gemini(
        contents=(
            f"Pesan dari Bos: {user_message}\n\n"
            f"Memori Pengetahuan, Aturan Bos & Investigasi Berita Sektor dari Database:\n{json.dumps(knowledge_ctx, ensure_ascii=False)}\n\n"
            f"Data Kuantitatif Real-Time Saham Terkait:\n{json.dumps(mentioned_snapshots, ensure_ascii=False)}"
        ),
        system_instruction=(
            "Anda adalah tim Karyawan AI Analis Saham pribadi (Bastian, Serena, Damian, Chief Arthur). "
            "Bos Anda masih pemula di saham dan minta dijelaskan pakai 'BAHASA BAYI' (bahasa sehari-hari yang super simpel, "
            "analogikan seperti belanja di pasar: harga diskon, lagi ramai pembeli, jual ambil untung, rem darurat biar nggak rugi dalam). "
            "Hindari istilah teknis yang membingungkan, tapi TETAP berikan angka harga Beli, harga Jual Untung, Rem Darurat, dan JAM BELI yang akurat sesuai data JSON!"
        ),
        temperature=0.3,
    )
    if ai_text:
        try:
            orchestrator.db.save_conversation_knowledge(
                category="TANYA_JAWAB_TELEGRAM",
                source="CHAT_BOS",
                user_message=user_message,
                ai_lesson_extracted=ai_text[:500],
                related_tickers=[str(s.get("ticker", "")) for s in mentioned_snapshots[:3]],
                is_permanent_rule=False,
            )
        except Exception:
            pass
        return ai_text

    if mentioned_snapshots:
        s = mentioned_snapshots[0]
        code = str(s.get("ticker", "")).replace(".JK", "")
        return (
            f"👨‍💼 *Tim AI Saham (Bahasa Simpel):*\n"
            f"Bos, untuk saham *{code}*, harga sekarang ada di *Rp {s.get('current_price', 0):,.0f}*.\n"
            f"• 🛒 *Saran Beli (Cicil):* Rp {s.get('entry_low', 0):,.0f} – Rp {s.get('entry_high', 0):,.0f}\n"
            f"• 💰 *Target Jual Untung:* Rp {s.get('take_profit_1', 0):,.0f} sampai Rp {s.get('take_profit_2', 0):,.0f}\n"
            f"• 🛑 *Rem Darurat (Jual kalau turun ke):* < Rp {s.get('stop_loss', 0):,.0f}\n"
            f"• ⏰ *Jam Beli:* {s.get('best_execution_window', '')}"
        ).replace(",", ".")
    return "👨‍💼 *Tim AI Saham:* Siap Bos! Ketik `/dsu`, `/scan`, atau `/cek BBCA` untuk pantauan saham hari ini."


def get_performance_dashboard_report(execution_mode: str | None = None) -> str:
    """Menjalankan siklus evaluasi prediksi tertunda lalu menampilkan dashboard performa & self-learning."""
    orchestrator = LearningLoopOrchestrator()
    try:
        orchestrator.run_evaluation_and_learning_cycle()
    except Exception:
        pass
    perf = PerformanceAnalyzer(orchestrator.db)
    return perf.format_performance_report_markdown(execution_mode=execution_mode)


def get_ticker_memory_report(ticker_input: str) -> str:
    """Menampilkan memori pengalaman, riwayat evaluasi, dan kalibrasi setup untuk 1 saham."""
    norm = config.normalize_ticker(ticker_input)
    snap = analyze_ticker_quant(norm)
    ihsg = get_ihsg_overview()
    orchestrator = LearningLoopOrchestrator()
    setup_type = snap.setup_type if snap else "VWAP_BREAKOUT_UPTREND"
    score = snap.quant_score if snap else 60
    regime = str(ihsg.get("regime", "NEUTRAL"))

    bundle = orchestrator.retriever.retrieve_relevant_memories(
        ticker=norm,
        setup_type=setup_type,
        timeframe="15m",
        ihsg_regime=regime,
        max_items=6,
    )
    cal_conf, basis = orchestrator.retriever.calibrate_confidence(
        raw_quant_score=score,
        setup_type=setup_type,
        timeframe="15m",
        ihsg_regime=regime,
        ticker=norm,
    )
    lines = [
        f"🧠 *MEMORI & PENGALAMAN AI UNTUK {norm}*",
        f"• *Setup Saat Ini:* `{setup_type}` | *Rezim IHSG:* `{regime}`",
        f"• *Confidence Terkalibrasi:* *{cal_conf*100:.1f}%* ({basis})",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if not bundle["memories"]:
        lines.append("ℹ️ Belum ada riwayat evaluasi tersimpan untuk kombinasi saham/setup ini.")
    else:
        for idx, m in enumerate(bundle["memories"], start=1):
            lines.extend([
                f"\n*{idx}. [{m['type']}]* (`{m['validity_level']}`)",
                f"   • Cakupan: `{m['scope']}` | Sampel N={m['sample_size']} | Waktu: `{m['timestamp'][:16]}`",
                f"   • Pelajaran: {m['lesson']}",
            ])
    return "\n".join(lines)


def get_weekly_ai_report() -> str:
    """Menjalankan siklus evaluasi terbaru lalu menyusun Rapor Mingguan 6 AI."""
    orchestrator = LearningLoopOrchestrator()
    try:
        orchestrator.run_evaluation_and_learning_cycle()
    except Exception:
        pass
    return generate_weekly_ai_leaderboard_report(db=orchestrator.db)


def swap_panel_ai_model(args: list[str]) -> str:
    """
    Mengganti salah satu dari 6 AI di panel dengan model AI gratis lain,
    atau menampilkan daftar model jika dipanggil tanpa argumen.
    """
    orchestrator = LearningLoopOrchestrator()
    db = orchestrator.db

    if not args:
        slots = db.get_ai_panel_registry()
        lines = [
            "🤖 *SUSUNAN 6 AI PANELIS SAAT INI:*",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]
        for s in slots:
            lines.append(
                f"• `{s['slot_id']}` — *{s['ai_name']}*\n"
                f"  Model: `{s['provider']}:{s['model_id']}`\n"
                f"  Fokus: _{s['role_focus']}_"
            )
        lines.extend([
            "",
            "📦 *DAFTAR MODEL AI GRATIS PENGGANTI:*",
        ])
        for mod_spec, desc in FREE_REPLACEMENT_MODELS_CATALOG:
            lines.append(f"• `{mod_spec}` — {desc}")
        lines.extend([
            "",
            "🛠️ *CARA MENGGANTI AI YANG JELEK:*",
            "Ketik: `/ganti_ai <SLOT> <NAMA_MODEL>`",
            "Contoh:",
            "• `/ganti_ai AI_3 gemini-3.8-flash`",
            "• `/ganti_ai AI_2 gemma-4-26b-a4b-it`",
            "• `/ganti_ai AI_4 groq:llama-3.3-70b-versatile`",
            "• `/ganti_ai reset` _(kembalikan 6 AI ke setelan pabrik)_",
        ])
        return "\n".join(lines)

    first = args[0].strip().lower()
    if first == "reset":
        db.reset_ai_panel_registry()
        return "✅ *Berhasil!* Susunan ke-6 AI Panelis sudah dikembalikan ke setelan awal."

    if len(args) < 2:
        return "⚠️ Format kurang lengkap. Contoh: `/ganti_ai AI_3 gemini-3.8-flash` atau ketik `/ganti_ai` untuk melihat daftar model."

    slot_id = args[0].strip().upper()
    new_model = args[1].strip()
    custom_name = " ".join(args[2:]).strip() if len(args) > 2 else None
    try:
        updated = db.update_ai_panel_slot(slot_id, new_model, custom_name)
        return (
            f"✅ *BERHASIL MENGGANTI {updated['slot_id']}!*\n\n"
            f"• *Nama Baru:* *{updated['ai_name']}*\n"
            f"• *Provider & Model:* `{updated['provider']}:{updated['model_id']}`\n"
            f"• *Fokus Tugas:* _{updated['role_focus']}_\n\n"
            "Mulai analisis berikutnya (`/cek`, `/scan`, `/dsu`), AI baru ini langsung ikut memberikan suara dan dinilai di rapor mingguan `/rapor_ai`!"
        )
    except Exception as e:
        return f"⚠️ Gagal mengganti AI: {e}"


def generate_sectoral_news_catalyst_report() -> str:
    """
    Memindai puluhan artikel berita dari 7 Sektor Utama BEI (Rokok & Cukai, Bank, Energi/Batu Bara,
    Tambang Emas/Logam, Konsumer/Ritel/Poultry, Properti/Otomotif, Telko/EBT),
    membandingkan banyak sumber media, memetakan dampak sebab-akibat, dan mencari peluang:
    1) ⚡ Scalping / Jangka Pendek
    2) 🌱 Swing / Investasi Masa Depan (Mingguan-Bulanan)
    """
    wib_now = datetime.now(pytz.timezone("Asia/Jakarta")).strftime("%A, %d %b %Y - %H:%M WIB")
    ihsg = get_ihsg_overview()
    sector_radar = scan_all_sectors_news_and_catalysts(articles_per_sector=6)
    total_articles = sum(s["articles_compared_count"] for s in sector_radar)

    # Pilih emiten perwakilan dari 3 sektor paling aktif beritanya untuk dicek harga & tren nyatanya
    candidate_tickers: list[str] = []
    for sec in sector_radar[:4]:
        for t in sec["tickers"][:2]:
            if t not in candidate_tickers:
                candidate_tickers.append(t)

    snaps = scan_watchlist_quant(candidate_tickers[:6])
    orchestrator = LearningLoopOrchestrator()
    try:
        orchestrator.db.save_sector_news_investigations(sector_radar)
    except Exception:
        pass
    sector_stock_picks = []
    for s in snaps[:4]:
        try:
            ctx, panel = _analyze_with_panel(
                orchestrator=orchestrator,
                snap=s,
                ihsg_info=ihsg,
                timeframe="15m",
                horizon_bars=16,
                horizon_minutes=240,
                use_live_llm=False,
            )
            if panel is None:
                sector_stock_picks.append(s.to_dict())
                continue
            d = s.to_dict()
            d["panel_5_ai"] = f"{panel['buy_count']}/{panel['total_ai']} AI Setuju ({panel['works_pct']:.1f}% Works)"
            d["vonis_hakim"] = panel["verdict_label"]
            sector_stock_picks.append(d)
        except Exception:
            sector_stock_picks.append(s.to_dict())

    payload = {
        "waktu_scan_wib": wib_now,
        "total_artikel_dibandingkan": total_articles,
        "kondisi_ihsg": ihsg,
        "perbandingan_berita_7_sektor": sector_radar,
        "analisis_harga_emiten_terdampak": sector_stock_picks,
    }
    sys_inst = (
        "Anda adalah Tim Riset Lintas Sektor & Masa Depan (Serena, Bastian, Damian, Chief Arthur) untuk Bos yang pemula.\n"
        "Tugas Anda adalah membandingkan BANYAK berita lintas sektor dari JSON `perbandingan_berita_7_sektor` "
        "(seperti efek Cukai Rokok ke HMSP/GGRM/WIIM, Suku Bunga ke Bank, Harga Komoditas ke Tambang/Energi, Insentif ke Properti/Konsumer).\n"
        "Gunakan 'BAHASA BAYI' yang gampang dipahami, namun tajam membaca peluang:\n"
        "1. 📰 *Perbandingan Banyak Berita Lintas Sektor*: Sebutkan berapa total artikel & media yang dibandingkan, lalu jelaskan **Sebab ➡️ Akibat** pada tiap sektor penting.\n"
        "2. ⚡ *Peluang Jangka Pendek (Scalping / Harian)*: Saham sektor mana yang hari ini sedang ramai diborong.\n"
        "3. 🌱 *Peluang Masa Depan (Swing / Tabungan Mingguan-Bulanan)*: Saham sektor mana yang punya katalis berita bagus untuk disimpan beberapa minggu ke depan beserta harga Beli, Target Untung, dan Rem Daruratnya (100% dari angka JSON, DILARANG mengarang angka!)."
    )
    ai_text = _generate_with_gemini(
        contents=f"Susun Laporan Radar Berita Lintas Sektor & Peluang Masa Depan:\n{json.dumps(payload, ensure_ascii=False)}",
        system_instruction=sys_inst,
        temperature=0.2,
    )
    if ai_text:
        return ai_text

    lines = [
        "🌍 *RADAR BERITA LINTAS SEKTOR & PELUANG MASA DEPAN*",
        f"🕒 _{wib_now}_ | 📚 *Membandingkan {total_articles} Artikel Media Keuangan*",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for sec in sector_radar[:5]:
        media_str = ", ".join(sec["media_sources"][:4]) or "Berbagai Media"
        lines.extend([
            f"\n*{sec['label']}*",
            f"• 📊 *Arah Katalis:* *{sec['catalyst_direction']}* ({sec['articles_compared_count']} artikel dari _{media_str}_)",
            f"• 🔗 *Hukum Sebab-Akibat:*\n{sec['causal_logic']}",
        ])
        for art in sec["top_articles"][:2]:
            lines.append(f"  📰 _{art['title']}_ ({art['source']})")

    if sector_stock_picks:
        lines.extend([
            "\n━━━━━━━━━━━━━━━━━━━━━━",
            "🌱 *SAHAM SEKTORAL PILIHAN (SCALPING & MASA DEPAN):*",
        ])
        for sp in sector_stock_picks[:3]:
            code = str(sp.get("ticker", "")).replace(".JK", "")
            lines.extend([
                f"\n📌 *{code}* — Harga: *Rp {sp.get('current_price', 0):,.0f}* | Tren Harian: *{sp.get('daily_trend', '')}*",
                f"   • 🗳️ *Suara 6 AI:* {sp.get('panel_5_ai', '-')}",
                f"   • 🛒 *Area Cicil Beli:* Rp {sp.get('entry_low', 0):,.0f} – Rp {sp.get('entry_high', 0):,.0f}",
                f"   • 🎯 *Target Jual (TP1 / TP2):* Rp {sp.get('take_profit_1', 0):,.0f} / Rp {sp.get('take_profit_2', 0):,.0f}",
                f"   • 🛑 *Rem Darurat (SL):* < Rp {sp.get('stop_loss', 0):,.0f}",
            ])
    return "\n".join(lines).replace(",", ".")
