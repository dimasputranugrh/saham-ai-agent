import concurrent.futures
import json
import os
import re
from typing import Any, Optional
import requests
from google import genai
from google.genai import types

import config
from analyzer.technical import TechnicalSnapshot
from memory.database import MemoryDatabase

FREE_REPLACEMENT_MODELS_CATALOG = [
    ("gemini-3.6-flash", "Google Gemini 3.6 Flash (Cepat & Tajam untuk Intraday)"),
    ("groq:openai/gpt-oss-120b", "OpenAI GPT-OSS 120B via Groq (Model Raksasa 120 Miliar Parameter - Gratis)"),
    ("openrouter:nvidia/nemotron-3-ultra-550b-a55b:free", "NVIDIA Nemotron 3 Ultra 550B via OpenRouter (Raksasa 550B - 100% Gratis)"),
    ("groq:qwen/qwen3.8-27b", "Alibaba Qwen 3.8 27B via Groq (Kuat di Matematika & Tren Asia - Gratis)"),
    ("quant-bayesian-v1", "Mesin Matematika Quant + Memori Bayesian (Murni Rumus & Statistik)"),
    ("openrouter:minimax/minimax-m3.1-flash:free", "MiniMax M3.1 Flash via OpenRouter (100% Gratis)"),
    ("openrouter:nvidia/nemotron-3.5-lightning:free", "NVIDIA Nemotron 3.5 Lightning via OpenRouter (100% Gratis)"),
    ("gemma-4-26b-a4b-it", "Google Gemma 4 26B MoE Open-Weights (Kuat di Volume & Pola)"),
    ("gemini-3-flash-preview", "Google Gemini 3 Flash Preview (Analitis & Kritis)"),
    ("gemini-3.5-flash-lite", "Google Gemini 3.5 Flash Lite (Ringan, Konservatif & Stabil)"),
    ("groq:openai/gpt-oss-20b", "OpenAI GPT-OSS 20B via Groq (Super Cepat & Ringan - Gratis)"),
]


def _get_genai_client() -> Optional[genai.Client]:
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


def _parse_json_safely(raw_text: str) -> Optional[dict[str, Any]]:
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except Exception:
            pass
    return None


def _deterministic_slot_vote(
    slot_id: str,
    snap_dict: dict[str, Any],
    calibrated_conf: float,
    has_degraded_warning: bool,
) -> dict[str, Any]:
    """
    Deterministic fallback profile per AI slot if an external model is temporarily rate-limited (503/429),
    reflecting each AI's distinct analytical lens on the real market indicators.
    """
    score = int(snap_dict.get("quant_score", 50))
    price = float(snap_dict.get("current_price", 0))
    vwap = float(snap_dict.get("intraday_vwap", price))
    rsi = float(snap_dict.get("intraday_rsi", 50.0))
    vol_ratio = max(
        float(snap_dict.get("daily_vol_ratio", 1.0)),
        float(snap_dict.get("intraday_vol_spike_ratio", 1.0)),
    )
    spread_pct = float(snap_dict.get("spread_pct", 0.4))
    rr = float(snap_dict.get("reward_to_risk", 1.0))
    net_ret = float(snap_dict.get("estimated_net_return_pct", 1.0))
    daily_trend = str(snap_dict.get("daily_trend", ""))

    if slot_id == "AI_1":
        # Momentum Scalper: Focuses on VWAP & Volume spike
        is_buy = (price >= vwap) and (vol_ratio >= 1.30) and (45 <= rsi <= 72) and score >= 72
        conf = min(92.0, max(35.0, score + (8.0 if price >= vwap else -10.0) + (5.0 if vol_ratio >= 1.3 else 0.0)))
        reason = (
            f"Harga bertahan di atas rata-rata VWAP dengan volume {vol_ratio:.1f}x, dorongan pembeli kuat."
            if is_buy
            else f"Volume ({vol_ratio:.1f}x) atau posisi terhadap VWAP belum cukup kuat untuk scalping cepat."
        )
    elif slot_id == "AI_2":
        # Risk & Trap Auditor (Contrarian/Strict): Strict on spread, RSI overbought, and net return
        is_buy = (
            (spread_pct <= 0.50)
            and (rsi <= 63.0)
            and (net_ret >= 1.35)
            and (score >= 72)
            and not has_degraded_warning
        )
        conf = min(88.0, max(30.0, score - (spread_pct * 12.0) - (8.0 if rsi > 63 else 0.0)))
        reason = (
            f"Risiko aman: spread tipis ({spread_pct:.2f}%), RSI {rsi:.0f} belum pucuk, potensi bersih +{net_ret:.1f}%."
            if is_buy
            else f"Waspada risiko: spread {spread_pct:.2f}% / RSI {rsi:.0f} rawan koreksi atau potensi bersih tipis."
        )
    elif slot_id == "AI_3":
        # Gemma-4 OpenMoE Bandar & Flow: Focuses on accumulation & MACD/Volume
        macd_h = float(snap_dict.get("intraday_macd_hist", 0.0))
        is_buy = (vol_ratio >= 1.25) and (macd_h >= 0) and (score >= 72)
        conf = min(90.0, max(32.0, score + (6.0 if macd_h > 0 else -8.0)))
        reason = (
            f"Aliran akumulasi positif (MACD histogram naik & rasio volume {vol_ratio:.1f}x)."
            if is_buy
            else "Aliran dana bandar belum kompak akumulasi, lebih aman tunggu antrean bawah."
        )
    elif slot_id == "AI_4":
        # Trend & Swing Guard: Focuses on Daily Uptrend & Reward/Risk
        uptrend = "UPTREND" in daily_trend.upper() or "BULLISH" in daily_trend.upper()
        is_buy = uptrend and (rr >= 1.8) and (score >= 72)
        conf = min(90.0, max(35.0, score + (7.0 if uptrend else -10.0)))
        reason = (
            f"Tren besar searah naik ({daily_trend}) dengan rasio untung/rugi 1:{rr:.1f} yang sehat."
            if is_buy
            else f"Tren harian ({daily_trend}) atau rasio untung/rugi (1:{rr:.1f}) belum ideal."
        )
    elif slot_id == "AI_6":
        # Pattern & Reversal Master: Focuses on RSI oversold recovery, candle structure, and non-degraded signals
        rsi_rebound = (35 <= rsi <= 64)
        score_ok = score >= 68
        is_buy = rsi_rebound and score_ok and (vol_ratio >= 1.15) and not has_degraded_warning
        conf = min(92.0, max(35.0, score + (7.0 if rsi_rebound else -8.0)))
        reason = (
            f"Pola candlestick reversal terkonfirmasi (RSI {rsi:.0f} mantul dari bawah, struktur candle sehat)."
            if is_buy
            else f"Pola candlestick belum membentuk konfirmasi reversal kuat (RSI {rsi:.0f} / volume belum menopang)."
        )
    else:
        # AI_5: Pure Quant & Bayesian Memory Engine
        cal_pct = round(calibrated_conf * 100.0, 1)
        is_buy = (cal_pct >= 56.0) and (score >= 72) and (net_ret >= 1.35) and not has_degraded_warning
        conf = cal_pct
        reason = (
            f"Statistik memori & skor kuantitatif ({score}/100) mendukung peluang menang {cal_pct:.1f}% (net +{net_ret:.1f}%)."
            if is_buy
            else f"Probabilitas memori terkalibrasi ({cal_pct:.1f}%) belum melewati batas aman minimum."
        )

    return {
        "vote_direction": "BUY" if is_buy else "WAIT",
        "confidence_pct": round(conf, 1),
        "reasoning_summary": reason,
    }


def _call_single_panel_ai(
    slot_cfg: dict[str, Any],
    snap_dict: dict[str, Any],
    ihsg_info: dict[str, Any],
    calibrated_conf: float,
    has_degraded_warning: bool,
    memories_summary: str,
) -> dict[str, Any]:
    slot_id = str(slot_cfg["slot_id"])
    ai_name = str(slot_cfg["ai_name"])
    provider = str(slot_cfg["provider"]).lower()
    model_id = str(slot_cfg["model_id"])
    role_focus = str(slot_cfg["role_focus"])
    temp = float(slot_cfg.get("temperature", 0.2))

    # If AI_5 or provider == 'quant', run pure mathematical & Bayesian memory model directly
    if provider == "quant" or model_id.startswith("quant"):
        res = _deterministic_slot_vote(slot_id, snap_dict, calibrated_conf, has_degraded_warning)
        return {
            "slot_id": slot_id,
            "ai_name": ai_name,
            "provider": provider,
            "model_id": model_id,
            **res,
        }

    prompt_payload = {
        "ticker": snap_dict.get("ticker"),
        "current_price": snap_dict.get("current_price"),
        "change_pct": snap_dict.get("change_pct"),
        "intraday_vwap": snap_dict.get("intraday_vwap"),
        "intraday_rsi": snap_dict.get("intraday_rsi"),
        "daily_rsi": snap_dict.get("daily_rsi"),
        "daily_trend": snap_dict.get("daily_trend"),
        "vol_ratio": max(
            float(snap_dict.get("daily_vol_ratio", 1.0)),
            float(snap_dict.get("intraday_vol_spike_ratio", 1.0)),
        ),
        "spread_pct": snap_dict.get("spread_pct"),
        "reward_to_risk": snap_dict.get("reward_to_risk"),
        "estimated_net_return_pct": snap_dict.get("estimated_net_return_pct"),
        "quant_score": snap_dict.get("quant_score"),
        "calibrated_memory_win_prob_pct": round(calibrated_conf * 100.0, 1),
        "ihsg_regime": ihsg_info.get("regime", "NEUTRAL"),
        "memory_notes": memories_summary,
    }

    sys_prompt = (
        f"Anda adalah {ai_name} dalam Panel 6 Juri AI Saham Indonesia (BEI).\n"
        f"Fokus tugas Anda: {role_focus}\n"
        "Evaluasi data JSON saham ini secara objektif dan independen. "
        "Balas HANYA dalam format JSON valid persis seperti ini tanpa teks tambahan:\n"
        '{"vote_direction": "BUY" atau "WAIT", "confidence_pct": angka_0_sampai_100, '
        '"reasoning_summary": "1 kalimat singkat bahasa sehari-hari yang jelas kenapa pilih BUY atau WAIT"}'
    )
    user_msg = f"Data saham untuk dinilai:\n{json.dumps(prompt_payload, ensure_ascii=False)}"

    parsed = None
    try:
        if provider == "gemini":
            client = _get_genai_client()
            if client:
                # For Gemma models that don't take system_instruction separately, prepend sys_prompt
                if model_id.startswith("gemma"):
                    resp = client.models.generate_content(
                        model=model_id,
                        contents=f"{sys_prompt}\n\n{user_msg}",
                        config=types.GenerateContentConfig(temperature=temp),
                    )
                else:
                    resp = client.models.generate_content(
                        model=model_id,
                        contents=user_msg,
                        config=types.GenerateContentConfig(
                            system_instruction=sys_prompt,
                            temperature=temp,
                        ),
                    )
                if resp and resp.text:
                    parsed = _parse_json_safely(resp.text)

        elif provider in ("groq", "openrouter", "cerebras", "mistral"):
            key_map = {
                "groq": os.getenv("GROQ_API_KEY", "").strip(),
                "openrouter": os.getenv("OPENROUTER_API_KEY", "").strip(),
                "cerebras": os.getenv("CEREBRAS_API_KEY", "").strip(),
                "mistral": os.getenv("MISTRAL_API_KEY", "").strip(),
            }
            url_map = {
                "groq": "https://api.groq.com/openai/v1/chat/completions",
                "openrouter": "https://openrouter.ai/api/v1/chat/completions",
                "cerebras": "https://api.cerebras.ai/v1/chat/completions",
                "mistral": "https://api.mistral.ai/v1/chat/completions",
            }
            api_key = key_map.get(provider, "")
            url = url_map.get(provider, "")
            if api_key and url:
                r = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model_id,
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_msg},
                        ],
                        "temperature": temp,
                    },
                    timeout=8,
                )
                if r.status_code == 200:
                    content = r.json()["choices"][0]["message"]["content"]
                    parsed = _parse_json_safely(content)
    except Exception:
        parsed = None

    if parsed and str(parsed.get("vote_direction", "")).upper() in ("BUY", "WAIT"):
        v_dir = str(parsed["vote_direction"]).upper()
        try:
            conf = float(parsed.get("confidence_pct", 50.0))
        except Exception:
            conf = 50.0
        conf = max(10.0, min(98.0, conf))
        reason = str(parsed.get("reasoning_summary", "")).strip() or "Berdasarkan analisis indikator terkini."
        return {
            "slot_id": slot_id,
            "ai_name": ai_name,
            "provider": provider,
            "model_id": model_id,
            "vote_direction": v_dir,
            "confidence_pct": round(conf, 1),
            "reasoning_summary": reason,
        }

    # Instant deterministic fallback if the specific model endpoint returned 503/429
    fallback = _deterministic_slot_vote(slot_id, snap_dict, calibrated_conf, has_degraded_warning)
    return {
        "slot_id": slot_id,
        "ai_name": ai_name,
        "provider": "deterministic",
        "model_id": "deterministic-v1",
        "is_fallback": True,
        **fallback,
    }


def generate_bull_vs_bear_debate(snap_dict: dict[str, Any], ihsg_info: dict[str, Any]) -> dict[str, Any]:
    """
    Pola Debat Adversarial Banteng (Bull) vs Beruang (Bear) ala TradingAgents.
    Memaksa 1 AI Bull mencari katalis terbaik dan 1 AI Bear mencari celah risiko terburuk
    sebelum Chief Arthur (Hakim Ketua) membuat keputusan final.
    """
    ticker = snap_dict.get("ticker", "SAHAM")
    price = float(snap_dict.get("current_price", 0.0) or 0.0)
    vwap = float(snap_dict.get("intraday_vwap", price) or price)
    cmf = float(snap_dict.get("cmf_20", 0.0) or 0.0)
    vol_spike = float(snap_dict.get("intraday_vol_spike_ratio", 1.0) or 1.0)
    daily_trend = str(snap_dict.get("daily_trend", "SIDEWAYS"))
    ihsg_trend = str(ihsg_info.get("trend", "NEUTRAL"))
    spread_pct = float(snap_dict.get("spread_pct", 0.0) or 0.0)

    bull_points = []
    bear_points = []

    # Argumen Bull (Banteng)
    if price >= vwap:
        bull_points.append(f"Harga bertahan di atas VWAP (Rp {vwap:,.0f}), buyer menguasai harga rata-rata hari ini.")
    if vol_spike >= 1.25:
        bull_points.append(f"Lonjakan volume {vol_spike:.1f}x rata-rata membuktikan adanya akumulasi agresif.")
    if cmf > 0.02:
        bull_points.append(f"Chaikin Money Flow positif ({cmf:+.2f}), terdeteksi aliran dana institusi masuk.")
    if "UPTREND" in daily_trend:
        bull_points.append(f"Tren harian selaras ({daily_trend}), angin buritan mendukung kenaikan lanjutan.")
    if not bull_points:
        bull_points.append("Struktur harga berada dekat area support swing dengan potensi technical rebound.")

    # Argumen Bear (Beruang)
    if price < vwap:
        bear_points.append(f"Harga masih di bawah VWAP (Rp {vwap:,.0f}), tekanan jual intraday masih dominan.")
    if "DOWNTREND" in daily_trend or "BEARISH" in daily_trend:
        bear_points.append(f"Tren harian {daily_trend}, risiko tinggi melawan arah tren besar (pisau jatuh).")
    if cmf < -0.03:
        bear_points.append(f"Chaikin Money Flow negatif ({cmf:+.2f}), terdeteksi guyuran/distribusi dana institusi.")
    if spread_pct > 0.45:
        bear_points.append(f"Spread bid-offer {spread_pct:.2f}% menggerus margin keuntungan dan rawan slippage.")
    if "BEARISH" in ihsg_trend:
        bear_points.append(f"Kondisi indeks pasar ({ihsg_trend}) rawan aksi guyur mendadak di sesi siang/sore.")
    if not bear_points:
        bear_points.append("Kenaikan harga rawan terbentur resistance harian terdekat jika volume tidak bertambah.")

    return {
        "bull_agent": "AI-1 (Bull Advocate - Momentum & Flow)",
        "bull_arguments": bull_points[:2],
        "bear_agent": "AI-2 (Bear Skeptic - Risk & Trap Auditor)",
        "bear_arguments": bear_points[:2],
    }


def run_5_ai_panel_consensus(
    snap: TechnicalSnapshot,
    ihsg_info: dict[str, Any],
    mem_ctx: Optional[dict[str, Any]] = None,
    db: Optional[MemoryDatabase] = None,
    use_live_llm: bool = True,
) -> dict[str, Any]:
    """
    Menjalankan 6 AI Panelis secara paralel untuk memberi masukan masing-masing,
    lalu dihitung skor konsensus (% Works untuk Dibeli) oleh 1 Hakim Ketua (Arif),
    dan disimpan ke tabel `ai_panel_votes` untuk rapor mingguan!
    """
    db_inst = db or MemoryDatabase()
    panel_slots = db_inst.get_ai_panel_registry()
    snap_dict = snap.to_dict()

    calibrated_conf = float(mem_ctx["calibrated_confidence"]) if mem_ctx else 0.55
    has_degraded = bool(mem_ctx["memory_bundle"].get("has_degraded_warning")) if mem_ctx else False
    memories_list = mem_ctx["memory_bundle"].get("memories", []) if mem_ctx else []
    memories_summary = "; ".join([m.get("lesson", "") for m in memories_list[:2]]) or "Belum ada catatan buruk."

    votes: list[dict[str, Any]] = []
    if use_live_llm:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
        future_map = {
            executor.submit(
                _call_single_panel_ai,
                slot_cfg,
                snap_dict,
                ihsg_info,
                calibrated_conf,
                has_degraded,
                memories_summary,
            ): slot_cfg
            for slot_cfg in panel_slots
        }
        done, not_done = concurrent.futures.wait(future_map.keys(), timeout=9.0)
        for fut in done:
            try:
                votes.append(fut.result())
            except Exception:
                pass
        for fut in not_done:
            slot_cfg = future_map[fut]
            res = _deterministic_slot_vote(
                slot_cfg["slot_id"], snap_dict, calibrated_conf, has_degraded
            )
            votes.append(
                {
                    "slot_id": slot_cfg["slot_id"],
                    "ai_name": slot_cfg["ai_name"],
                    "provider": "deterministic",
                    "model_id": "deterministic-v1",
                    "is_fallback": True,
                    **res,
                }
            )
        executor.shutdown(wait=False, cancel_futures=True)
        votes.sort(key=lambda x: x["slot_id"])
    else:
        for slot_cfg in panel_slots:
            res = _deterministic_slot_vote(
                slot_cfg["slot_id"], snap_dict, calibrated_conf, has_degraded
            )
            votes.append(
                {
                    "slot_id": slot_cfg["slot_id"],
                    "ai_name": slot_cfg["ai_name"],
                    "provider": "deterministic",
                    "model_id": "deterministic-v1",
                    "is_fallback": True,
                    **res,
                }
            )

    # Ambil bobot akurasi historis tiap AI dari database agar AI yang sering benar punya bobot lebih tinggi
    stats_map = _get_slot_accuracy_weights(db_inst)

    buy_count = sum(1 for v in votes if v["vote_direction"] == "BUY")
    total_ai = max(1, len(votes))
    agreement_pct = round((buy_count / total_ai) * 100.0, 1)

    weighted_buy_score = 0.0
    total_weight = 0.0
    for v in votes:
        w = stats_map.get(v["slot_id"], 1.0)
        total_weight += w
        # WAIT is a veto, not a 50/50 buy probability. Only BUY votes contribute.
        if v["vote_direction"] == "BUY":
            weighted_buy_score += w * v["confidence_pct"]

    works_pct = round(weighted_buy_score / max(0.01, total_weight), 1)

    # Deteksi suara dari AI unggulan berakurasi tinggi (AI_6 & AI_5) untuk Veto Defense
    ai6_vote = next((v for v in votes if v.get("slot_id") == "AI_6"), None)
    ai5_vote = next((v for v in votes if v.get("slot_id") == "AI_5"), None)
    ai6_veto = (ai6_vote is not None and ai6_vote.get("vote_direction") == "WAIT" and float(ai6_vote.get("confidence_pct", 50)) >= 55.0)
    ai5_veto = (ai5_vote is not None and ai5_vote.get("vote_direction") == "WAIT" and float(ai5_vote.get("confidence_pct", 50)) >= 55.0)
    veto_active = ai6_veto or ai5_veto

    # Keputusan Chief Arthur (Supreme Decider) - Diperketat demi proteksi modal riil Bos
    if buy_count >= 5 and works_pct >= 72.0 and not has_degraded and not veto_active:
        final_decision = "BUY"
        verdict_label = f"🟢 SANGAT LAYAK BELI (KONSENSUS KUAT: {buy_count}/{total_ai} AI Setuju — {works_pct:.1f}% Works)"
        chief_summary = (
            f"Super-mayoritas ({buy_count} dari {total_ai} AI) solid merekomendasikan BELI dengan keyakinan tinggi ({works_pct:.1f}% Works). "
            f"Peluang menang terkonfirmasi sehat dan rasio Risk:Reward > 1:2 setelah dikurangi fee transaksi."
        )
    elif buy_count >= 4 and works_pct >= 67.0 and not has_degraded and not veto_active:
        final_decision = "BUY"
        verdict_label = f"🟢 LAYAK BELI SELEKTIF ({buy_count}/{total_ai} AI Setuju — {works_pct:.1f}% Works)"
        chief_summary = (
            f"Mayoritas kuat ({buy_count} dari {total_ai} AI) menyetujui BELI ({works_pct:.1f}% Works) tanpa veto AI unggulan. "
            f"Boleh antri beli bertahap di area bawah (entry low), dilarang kejar harga pucuk."
        )
    elif veto_active and buy_count >= 4:
        veto_ai = "AI_6" if ai6_veto else "AI_5"
        final_decision = "WAIT"
        verdict_label = f"🔴 VETO DEFENSE AKTIF: DITAHAN {veto_ai} ({buy_count}/{total_ai} AI Mau Beli Tapi Ditolak)"
        chief_summary = (
            f"{buy_count} dari {total_ai} AI menyarankan BUY, namun {veto_ai} (AI Akurasi Tertinggi) "
            f"mengaktifkan VETO DEFENSE dan menyarankan WAIT demi mencegah jebakan false breakout/nyangkut."
        )
    else:
        final_decision = "WAIT"
        verdict_label = f"🔴 JANGAN BELI DULU / WAIT ({buy_count}/{total_ai} AI Setuju — Cuma {works_pct:.1f}% Works)"
        chief_summary = (
            f"Hanya {buy_count} dari {total_ai} AI yang berani beli (skor kelayakan cuma {works_pct:.1f}%). "
            f"Chief Arthur memutuskan TAHAN DULU / WAIT demi menjaga modal Bos tetap utuh dan terhindar dari cut loss."
        )

    if mem_ctx and mem_ctx.get("analysis_id"):
        try:
            db_inst.save_ai_panel_votes(
                analysis_id=str(mem_ctx["analysis_id"]),
                ticker=snap.ticker,
                votes=votes,
            )
        except Exception:
            pass

    debate = generate_bull_vs_bear_debate(snap_dict, ihsg_info)

    return {
        "votes": votes,
        "buy_count": buy_count,
        "total_ai": total_ai,
        "agreement_pct": agreement_pct,
        "works_pct": works_pct,
        "final_decision": final_decision,
        "verdict_label": verdict_label,
        "chief_summary": chief_summary,
        "debate": debate,
    }


def _get_slot_accuracy_weights(db: MemoryDatabase) -> dict[str, float]:
    """Menghitung bobot kepercayaan tiap AI berdasarkan akurasi tebakan sebelumnya (Bayesian laplace smoothing)."""
    weights = {f"AI_{i}": 1.0 for i in range(1, 7)}
    try:
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT slot_id,
                       COUNT(*) AS total_eval,
                       SUM(CASE WHEN outcome_status IN ('CORRECT_BUY_WIN', 'CORRECT_WAIT_SAVED') THEN 1 ELSE 0 END) AS correct_cnt
                FROM ai_panel_votes
                WHERE outcome_status != 'PENDING' AND outcome_status != 'NEUTRAL'
                  AND model_id != 'deterministic-v1'
                GROUP BY slot_id
                """
            ).fetchall()
            for r in rows:
                tot = int(r["total_eval"] or 0)
                corr = int(r["correct_cnt"] or 0)
                # Bayesian smoothing with prior 3/5 = 0.60
                acc = (corr + 3.0) / (tot + 5.0)
                weights[str(r["slot_id"])] = round(max(0.5, min(1.8, acc / 0.60)), 3)
    except Exception:
        pass
    return weights


def format_panel_consensus_section(consensus: dict[str, Any]) -> str:
    """Memformat kotak ringkasan debat Bull vs Bear + voting 6 AI + Keputusan Hakim Ketua untuk pesan Telegram."""
    lines = []
    deb = consensus.get("debate")
    if deb:
        lines.extend([
            "⚔️ *DEBAT ADVERSARIAL: BANTENG (BULL) vs BERUANG (BEAR)*",
            f"🐂 *{deb['bull_agent']}:*",
        ])
        for pt in deb.get("bull_arguments", []):
            lines.append(f"  • {pt}")
        lines.append(f"🐻 *{deb['bear_agent']}:*")
        for pt in deb.get("bear_arguments", []):
            lines.append(f"  • {pt}")
        lines.append("")

    lines.append("🗳️ *HASIL SIDANG PANEL 6 AI GRATIS (PERBANDINGAN SUARA):*")
    for v in consensus.get("votes", []):
        icon = "🟢 *BUY*" if v["vote_direction"] == "BUY" else "🔴 *WAIT*"
        lines.append(
            f"• *{v['ai_name']}* (`{v['model_id']}`): {icon} — _{v['confidence_pct']:.0f}%_\n"
            f"  💬 Masukan: _{v['reasoning_summary']}_"
        )
    lines.extend([
        "",
        "⚖️ *KEPUTUSAN CHIEF ARTHUR (SUPREME ARBITER):*",
        f"• *Suara Setuju Beli:* *{consensus['buy_count']} dari {consensus['total_ai']} AI ({consensus['agreement_pct']:.0f}%)*",
        f"• *Persentase Kelayakan Beli:* *{consensus['works_pct']:.1f}% Works*",
        f"• *Vonis Akhir:* *{consensus['verdict_label']}*",
        f"• *Alasan Chief Arthur:* {consensus['chief_summary']}",
    ])
    return "\n".join(lines)


def generate_weekly_ai_leaderboard_report(days: int = 7, db: Optional[MemoryDatabase] = None) -> str:
    """
    Menghasilkan Rapor Mingguan Performa 6 AI:
    - Mengurutkan AI dari yang paling akurat (#1 Terbaik) sampai yang paling buruk (#6).
    - Menunjukkan AI mana yang bagus dipertahankan dan AI mana yang jelek & layak diganti.
    """
    db_inst = db or MemoryDatabase()
    slots = {s["slot_id"]: s for s in db_inst.get_ai_panel_registry()}

    with db_inst.connect() as conn:
        rows = conn.execute(
            """
            SELECT slot_id,
                   COUNT(*) AS total_votes,
                   SUM(CASE WHEN outcome_status != 'PENDING' AND outcome_status != 'NEUTRAL' THEN 1 ELSE 0 END) AS graded_votes,
                   SUM(CASE WHEN outcome_status = 'CORRECT_BUY_WIN' THEN 1 ELSE 0 END) AS buy_wins,
                   SUM(CASE WHEN outcome_status = 'WRONG_BUY_LOSS' THEN 1 ELSE 0 END) AS buy_losses,
                   SUM(CASE WHEN outcome_status = 'CORRECT_WAIT_SAVED' THEN 1 ELSE 0 END) AS wait_saves,
                   SUM(CASE WHEN outcome_status = 'MISSED_WAIT_OPPORTUNITY' THEN 1 ELSE 0 END) AS wait_missed,
                   AVG(CASE WHEN vote_direction = 'BUY' AND outcome_status != 'PENDING' THEN outcome_net_return_pct ELSE NULL END) AS avg_buy_net_ret
            FROM ai_panel_votes
            WHERE model_id != 'deterministic-v1'
            GROUP BY slot_id
            """
        ).fetchall()

    stats_by_slot = {str(r["slot_id"]): dict(r) for r in rows}
    leaderboard = []
    for slot_id in sorted(slots.keys()):
        cfg = slots[slot_id]
        st = stats_by_slot.get(slot_id, {})
        graded = int(st.get("graded_votes") or 0)
        buy_wins = int(st.get("buy_wins") or 0)
        buy_losses = int(st.get("buy_losses") or 0)
        wait_saves = int(st.get("wait_saves") or 0)
        wait_missed = int(st.get("wait_missed") or 0)
        avg_ret = float(st.get("avg_buy_net_ret") or 0.0)

        total_correct = buy_wins + wait_saves
        accuracy_pct = round((total_correct / graded) * 100.0, 1) if graded > 0 else 0.0
        buy_total = buy_wins + buy_losses
        buy_win_rate = round((buy_wins / buy_total) * 100.0, 1) if buy_total > 0 else 0.0

        leaderboard.append(
            {
                "slot_id": slot_id,
                "ai_name": cfg["ai_name"],
                "provider": cfg["provider"],
                "model_id": cfg["model_id"],
                "graded": graded,
                "accuracy_pct": accuracy_pct,
                "buy_win_rate": buy_win_rate,
                "buy_wins": buy_wins,
                "buy_losses": buy_losses,
                "wait_saves": wait_saves,
                "wait_missed": wait_missed,
                "avg_ret": avg_ret,
            }
        )

    # Sort descending by overall accuracy_pct, then buy_win_rate
    leaderboard.sort(key=lambda x: (x["accuracy_pct"], x["buy_win_rate"]), reverse=True)

    lines = [
        "🏆 *RAPOR MINGGUAN 6 AI: SIAPA PALING JAGO vs SIAPA HARUS DIGANTI*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "_Setiap AI dinilai dari: seberapa sering tebakan BUY-nya cuan, dan seberapa sering tebakan WAIT-nya berhasil menyelamatkan Bos dari saham nyangkut._\n",
    ]

    for rank, item in enumerate(leaderboard, start=1):
        if rank == 1:
            badge = "🥇 *PERINGKAT 1 — AI TERBAIK (Pertahankan!)*"
        elif item["accuracy_pct"] >= 58.0:
            badge = f"🟢 *PERINGKAT {rank} — BAGUS & AKURAT*"
        elif item["accuracy_pct"] >= 48.0:
            badge = f"🟡 *PERINGKAT {rank} — LUMAYAN (Pantau Terus)*"
        else:
            badge = f"🔴 *PERINGKAT {rank} — KURANG AKURAT (Bisa Diganti!)*"

        lines.extend([
            f"{badge}",
            f"• *Slot & Nama:* `{item['slot_id']}` — *{item['ai_name']}*",
            f"• *Model Aktif:* `{item['provider']}:{item['model_id']}`",
            f"• *Skor Akurasi Total:* *{item['accuracy_pct']:.1f}%* (dari {item['graded']} ujian selesai)",
            f"• *Rekor Tebak Beli (BUY):* Menang *{item['buy_wins']}x* vs Meleset *{item['buy_losses']}x* (Win Rate BUY: *{item['buy_win_rate']:.1f}%*, Rata-rata Net: *{item['avg_ret']:+.2f}%*)",
            f"• *Rekor Cegah Rugi (WAIT):* Berhasil selamatkan modal *{item['wait_saves']}x* | Ketinggalan kereta *{item['wait_missed']}x*\n",
        ])

    worst = leaderboard[-1]
    best = leaderboard[0]
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━",
        "💡 *KESIMPULAN & SARAN EVALUASI AI MINGGU INI:*",
        f"• 🌟 *AI Paling Tajam:* `{best['slot_id']}` (*{best['model_id']}*) dengan akurasi *{best['accuracy_pct']:.1f}%*.",
        f"• ⚠️ *AI Paling Lemah Saat Ini:* `{worst['slot_id']}` (*{worst['model_id']}*) dengan akurasi *{worst['accuracy_pct']:.1f}%*.",
        "",
        "🔄 *CARA MENGGANTI AI YANG JELEK LEWAT TELEGRAM:*",
        f"Jika Bos ingin mengganti `{worst['slot_id']}` dengan model AI gratis lain, cukup ketik:",
        f"👉 `/ganti_ai {worst['slot_id']} gemini-3.8-flash`",
        f"👉 `/ganti_ai {worst['slot_id']} gemma-4-26b-a4b-it`",
        f"👉 `/ganti_ai {worst['slot_id']} groq:llama-3.3-70b-versatile`",
        "_(Ketik `/ganti_ai` saja untuk melihat daftar lengkap model AI gratis yang tersedia)_",
    ])
    return "\n".join(lines)
