from datetime import datetime, time as dt_time, timedelta
from typing import Any, Optional
import numpy as np
import pandas as pd
import pytz
import yfinance as yf

import config
from analyzer.technical import (
    TechnicalSnapshot,
    analyze_ticker_quant,
    compute_atr,
    compute_bollinger,
    compute_macd,
    compute_rsi,
    compute_vwap,
    get_idx_tick_size,
    get_ihsg_overview,
    get_ihsg_regime_as_of,
    round_idx_tick,
)
from memory.database import MemoryDatabase, now_wib_iso
from memory.evaluator import OutcomeEvaluator
from memory.performance import PerformanceAnalyzer
from memory.retrieval import MemoryRetriever

WIB = pytz.timezone(config.TIMEZONE)


def remaining_intraday_bars(
    after_ts: str | datetime | pd.Timestamp,
    timeframe: str = "15m",
    ticker: str = "",
) -> int:
    """Count remaining IDX session bars after `after_ts` until the 16:00 close.

    Lunch break (12:00-13:30) is skipped. Non-IDX symbols return a large number
    because they do not follow the IDX intraday session.
    """
    if not str(ticker).upper().endswith(".JK") or not str(timeframe).endswith("m"):
        return 10**6
    try:
        bar_minutes = int(str(timeframe)[:-1])
    except ValueError:
        return 10**6
    if bar_minutes <= 0:
        return 10**6

    ts = pd.Timestamp(after_ts)
    ts = ts.tz_localize(WIB) if ts.tzinfo is None else ts.tz_convert(WIB)
    day = ts.normalize()
    freq = f"{bar_minutes}min"
    morning = pd.date_range(day + pd.Timedelta(hours=9), day + pd.Timedelta(hours=12), freq=freq)
    afternoon = pd.date_range(day + pd.Timedelta(hours=13, minutes=30), day + pd.Timedelta(hours=16), freq=freq)
    return sum(
        1
        for bar in list(morning) + list(afternoon)
        if bar > ts and (bar.time() < dt_time(12, 0) or bar.time() >= dt_time(13, 30))
    )


class LearningLoopOrchestrator:
    """
    Phase 3 — Automatic Learning Loop Orchestrator:
    1. Fetches valid market data.
    2. Retrieves relevant historical memories & empirically calibrated confidence.
    3. Applies validated/degraded lessons to adjust signal direction & confidence.
    4. Records immutable market snapshot & initial prediction before outcome is known.
    5. Evaluates completed horizons idempotently with transaction costs.
    6. Updates strategy lessons & runs controlled out-of-sample strategy improvement.
    """

    def __init__(self, db: Optional[MemoryDatabase] = None):
        self.db = db or MemoryDatabase()
        self.retriever = MemoryRetriever(self.db)
        self.evaluator = OutcomeEvaluator(self.db)
        self.perf = PerformanceAnalyzer(self.db)

    def analyze_and_record_with_memory(
        self,
        ticker: str,
        snap: Optional[TechnicalSnapshot] = None,
        ihsg_info: Optional[dict[str, Any]] = None,
        news_context: str = "",
        timeframe: str = "15m",
        horizon_bars: int = 8,
        horizon_minutes: int = 120,
        execution_mode: str = config.EXECUTION_MODE,
        save_prediction: bool = True,
    ) -> Optional[dict[str, Any]]:
        """
        Executes Steps 1–5 of the Learning Loop for a single stock:
        - Retrieves relevant memories & calibrated confidence.
        - Applies learned lessons (downgrades BUY -> WAIT if setup is DEGRADED or below active strategy version threshold).
        - Saves snapshot & immutable prediction to SQLite.
        - Returns enriched context dict for the AI agents.
        """
        norm_ticker = config.normalize_ticker(ticker)
        if snap is None:
            snap = analyze_ticker_quant(norm_ticker)
        if snap is None:
            return None

        if ihsg_info is None:
            ihsg_info = get_ihsg_overview()
        ihsg_regime = str(ihsg_info.get("regime", "NEUTRAL"))

        # Check active strategy version parameters
        active_ver = self.db.get_active_strategy_version(config.DEFAULT_STRATEGY_NAME)
        strat_ver_tag = active_ver["version_tag"]
        strat_params = active_ver["parameters"]
        min_score_param = int(strat_params.get("min_intraday_score", config.MIN_INTRADAY_ALERT_SCORE))
        max_spread_param = float(strat_params.get("max_spread_pct", 0.65))
        bar_cutoff = snap.last_bar_iso or now_wib_iso()

        # Step 2: Retrieve relevant historical memories & calibrated confidence
        mem_bundle = self.retriever.retrieve_relevant_memories(
            ticker=norm_ticker,
            setup_type=snap.setup_type,
            timeframe=timeframe,
            ihsg_regime=ihsg_regime,
            max_items=5,
            execution_mode=execution_mode,
            strategy_version=strat_ver_tag,
            as_of=bar_cutoff,
        )
        calibrated_conf, conf_basis = self.retriever.calibrate_confidence(
            raw_quant_score=snap.quant_score,
            setup_type=snap.setup_type,
            timeframe=timeframe,
            ihsg_regime=ihsg_regime,
            ticker=norm_ticker,
            execution_mode=execution_mode,
            strategy_version=strat_ver_tag,
            as_of=bar_cutoff,
        )

        # Step 3: Apply learned lessons & active strategy guards to decision
        final_direction = snap.direction
        supporting_ev = list(snap.supporting_evidence)
        opposing_ev = list(snap.opposing_evidence)
        interpretations = list(snap.interpretations)

        if mem_bundle["has_degraded_warning"] and final_direction == "BUY":
            final_direction = "WAIT"
            opposing_ev.append(
                f"MEMORI HISTORIS (DEGRADED SETUP): {mem_bundle['degraded_reason']} -> Sinyal BUY ditahan menjadi WAIT."
            )
            interpretations.append(
                "Berdasarkan evaluasi historis di database memori, setup ini sedang mengalami penurunan performa (DEGRADED), sehingga agen memilih WAIT."
            )

        if snap.spread_pct > max_spread_param and final_direction == "BUY":
            final_direction = "WAIT"
            opposing_ev.append(
                f"Spread 1 tick ({snap.spread_pct:.2f}%) melebihi batas parameter strategi aktif ({max_spread_param:.2f}%)."
            )

        if final_direction == "BUY" and snap.quant_score < min_score_param:
            final_direction = "WAIT"
            opposing_ev.append(
                f"Skor kuantitatif ({snap.quant_score}) di bawah ambang minimal strategi v{strat_ver_tag} ({min_score_param})."
            )

        bars_left = remaining_intraday_bars(datetime.now(WIB), timeframe, snap.ticker)
        if final_direction == "BUY" and bars_left < int(horizon_bars):
            final_direction = "WAIT"
            opposing_ev.append(
                f"JENDELA INTRADAY TIDAK CUKUP: tersisa {bars_left} bar sebelum penutupan, "
                f"sedangkan horizon butuh {horizon_bars} bar. BUY ditahan agar tidak menjadi posisi overnight."
            )

        # Step 4: Save Market Snapshot
        snapshot_id = self.db.save_market_snapshot(
            {
                "ticker": snap.ticker,
                "timeframe": timeframe,
                "last_bar_timestamp": bar_cutoff,
                "price": snap.current_price,
                "open_price": snap.prev_close,
                "high_price": snap.day_high,
                "low_price": snap.day_low,
                "volume": snap.volume_shares,
                "vwap": snap.intraday_vwap,
                "ema9": snap.intraday_ema9,
                "ema21": snap.intraday_ema21,
                "ema20": snap.daily_ema20,
                "ema50": snap.daily_ema50,
                "sma200": snap.daily_sma200,
                "rsi": snap.intraday_rsi,
                "macd_hist": snap.intraday_macd_hist,
                "atr": snap.daily_atr,
                "vol_ratio": max(snap.daily_vol_ratio, snap.intraday_vol_spike_ratio),
                "ihsg_close": ihsg_info.get("last_close"),
                "ihsg_change_pct": ihsg_info.get("change_pct"),
                "ihsg_regime": ihsg_regime,
                "sector": config.SECTOR_MAP.get(snap.ticker, "GENERAL_IDX"),
                "tick_size": snap.tick_size,
                "spread_pct": snap.spread_pct,
                "order_book_available": False,
                "data_source": "yfinance",
                "data_is_valid": snap.data_is_valid,
                "validation_notes": snap.validation_notes,
            }
        )

        # Step 5: Build context; saving can be deferred until the AI panel decides.
        ctx = {
            "snapshot_id": snapshot_id,
            "snapshot": snap,
            "bar_cutoff": bar_cutoff,
            "ticker": snap.ticker,
            "timeframe": timeframe,
            "execution_mode": execution_mode,
            "strategy_name": config.DEFAULT_STRATEGY_NAME,
            "setup_type": snap.setup_type,
            "ihsg_regime": ihsg_regime,
            "sector": config.SECTOR_MAP.get(snap.ticker, "GENERAL_IDX"),
            "technical_facts": snap.technical_facts,
            "interpretations": interpretations,
            "assumptions": snap.assumptions,
            "supporting_evidence": supporting_ev,
            "opposing_evidence": opposing_ev,
            "fundamental_news_context": news_context,
            "entry_price": snap.entry_high,
            "entry_low": snap.entry_low,
            "entry_high": snap.entry_high,
            "stop_loss": snap.stop_loss,
            "take_profit_1": snap.take_profit_1,
            "take_profit_2": snap.take_profit_2,
            "horizon_bars": horizon_bars,
            "horizon_minutes": horizon_minutes,
            "estimated_risk_pct": snap.estimated_risk_pct,
            "estimated_gross_return_pct": snap.estimated_gross_return_pct,
            "estimated_net_return_pct": snap.estimated_net_return_pct,
            "reward_to_risk": snap.reward_to_risk,
            "raw_quant_score": snap.quant_score,
            "calibrated_confidence": calibrated_conf,
            "confidence_basis": conf_basis,
            "invalidation_conditions": snap.invalidation_conditions,
            "model_version": config.GEMINI_MODEL,
            "prompt_version": config.AGENT_PROMPT_VERSION,
            "strategy_version": strat_ver_tag,
            "memory_ids_used": mem_bundle["memory_ids_used"],
            "final_direction": final_direction,
            "memory_bundle": mem_bundle,
            "ihsg_info": ihsg_info,
        }
        if not save_prediction:
            return ctx
        return self.record_final_prediction(ctx, final_direction)

    def record_final_prediction(
        self,
        ctx: dict[str, Any],
        final_direction: str,
        panel_votes: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Persist one immutable decision, after the panel has spoken."""
        final_direction = str(final_direction).upper()
        if final_direction not in ("BUY", "SELL", "WAIT", "AVOID"):
            final_direction = "WAIT"
        eval_after_dt = datetime.now(WIB) + timedelta(minutes=int(ctx["horizon_minutes"]))
        analysis_id = self.db.save_analysis_prediction(
            {
                "snapshot_id": ctx["snapshot_id"],
                "bar_cutoff_timestamp": ctx["bar_cutoff"],
                "ticker": ctx["ticker"],
                "timeframe": ctx["timeframe"],
                "direction": final_direction,
                "execution_mode": ctx["execution_mode"],
                "strategy_name": ctx["strategy_name"],
                "setup_type": ctx["setup_type"],
                "ihsg_regime": ctx["ihsg_regime"],
                "sector": ctx["sector"],
                "technical_facts": ctx["technical_facts"],
                "interpretations": ctx["interpretations"],
                "assumptions": ctx["assumptions"],
                "supporting_evidence": ctx["supporting_evidence"],
                "opposing_evidence": ctx["opposing_evidence"],
                "fundamental_news_context": ctx["fundamental_news_context"],
                "entry_price": ctx["entry_price"],
                "entry_low": ctx["entry_low"],
                "entry_high": ctx["entry_high"],
                "stop_loss": ctx["stop_loss"],
                "take_profit_1": ctx["take_profit_1"],
                "take_profit_2": ctx["take_profit_2"],
                "horizon_bars": ctx["horizon_bars"],
                "horizon_minutes": ctx["horizon_minutes"],
                "evaluate_after_wib": eval_after_dt.isoformat(),
                "estimated_risk_pct": ctx["estimated_risk_pct"],
                "estimated_gross_return_pct": ctx["estimated_gross_return_pct"],
                "estimated_net_return_pct": ctx["estimated_net_return_pct"],
                "reward_to_risk": ctx["reward_to_risk"],
                "raw_quant_score": ctx["raw_quant_score"],
                "calibrated_confidence": ctx["calibrated_confidence"],
                "confidence_basis": ctx["confidence_basis"],
                "invalidation_conditions": ctx["invalidation_conditions"],
                "model_version": ctx["model_version"],
                "prompt_version": ctx["prompt_version"],
                "strategy_version": ctx["strategy_version"],
                "memory_ids_used": ctx["memory_ids_used"],
            }
        )
        ctx["analysis_id"] = analysis_id
        ctx["final_direction"] = final_direction
        if panel_votes:
            try:
                self.db.save_ai_panel_votes(
                    analysis_id=str(analysis_id),
                    ticker=str(ctx["ticker"]),
                    votes=panel_votes,
                )
            except Exception:
                pass
        return ctx

    def run_evaluation_and_learning_cycle(self) -> dict[str, Any]:
        """
        Executes Steps 6–11 of the Learning Loop:
        - Evaluates all pending predictions whose future horizon bars are available.
        - Updates `strategy_lessons`.
        - Checks if controlled out-of-sample strategy improvement is warranted.
        """
        resolved = self.evaluator.evaluate_pending_predictions()
        lessons = self.evaluator.recompute_strategy_lessons()
        active = self.db.get_active_strategy_version(config.DEFAULT_STRATEGY_NAME)
        improvement = self.perf.propose_and_validate_strategy_improvement(
            execution_mode=config.EXECUTION_MODE,
            strategy_version=str(active["version_tag"]),
        )
        return {
            "newly_evaluated_count": len(resolved),
            "lessons_updated_count": len(lessons),
            "strategy_improvement": improvement,
        }

    def run_walk_forward_backtest(
        self,
        tickers: Optional[list[str]] = None,
        timeframe: str = "15m",
        horizon_bars: int = 6,
    ) -> dict[str, Any]:
        """
        Runs a strict chronological Walk-Forward evaluation on historical intraday bars (`15m` or `5m`)
        with zero future data leakage (`execution_mode='BACKTEST'`).
        At each step `i`, only bars `<= i` are visible when generating the prediction;
        then `OutcomeEvaluator` evaluates the prediction using strictly bars `> i`,
        and updates `strategy_lessons` step-by-step so subsequent steps benefit from learned memory!
        """
        target_tickers = tickers or ["TLKM.JK", "BBRI.JK", "ASII.JK", "BMRI.JK", "ANTM.JK", "GOTO.JK"]
        try:
            ihsg_daily = yf.Ticker("^JKSE").history(period="3mo", interval="1d")
        except Exception:
            ihsg_daily = None
        active_ver = self.db.get_active_strategy_version(config.DEFAULT_STRATEGY_NAME)
        strat_ver_tag = str(active_ver["version_tag"])
        total_created = 0
        total_evaluated = 0

        for raw_t in target_tickers:
            ticker = config.normalize_ticker(raw_t)
            is_idx = ticker.endswith(".JK")
            try:
                tk = yf.Ticker(ticker)
                df = tk.history(period="1mo", interval=timeframe, auto_adjust=True)
            except Exception:
                continue
            if df is None or df.empty or len(df) < 45:
                continue

            df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
            if df.index.tzinfo is None:
                df.index = df.index.tz_localize(WIB)
            else:
                df.index = df.index.tz_convert(WIB)

            # Walk forward chronologically from bar 25 to len(df) - horizon_bars - 1, stepping by horizon_bars
            start_idx = max(25, len(df) - 65)
            end_idx = len(df) - horizon_bars - 1
            for idx in range(start_idx, end_idx, horizon_bars):
                # STRICT CAUSAL SLICE: only bars up to `idx` (inclusive) are visible!
                visible = df.iloc[: idx + 1].copy()
                cutoff_ts = visible.index[-1]
                # Only train on samples whose horizon fits inside the same IDX session.
                if remaining_intraday_bars(cutoff_ts, timeframe, ticker) < horizon_bars:
                    continue
                ihsg_info = get_ihsg_regime_as_of(cutoff_ts, ihsg_daily)
                ihsg_regime = str(ihsg_info.get("regime", "NEUTRAL"))
                as_of = cutoff_ts.isoformat()

                # Idempotent walk-forward: never create a second prediction for the same bar.
                with self.db.connect() as conn:
                    already = conn.execute(
                        """
                        SELECT analysis_id FROM analysis_history
                        WHERE ticker = ? AND timeframe = ? AND bar_cutoff_timestamp = ?
                          AND execution_mode = 'BACKTEST' AND strategy_version = ?
                        LIMIT 1
                        """,
                        (ticker, timeframe, as_of, strat_ver_tag),
                    ).fetchone()
                if already is not None:
                    continue

                c = visible["Close"]
                visible["VWAP"] = compute_vwap(visible)
                visible["EMA9"] = c.ewm(span=9, adjust=False).mean()
                visible["EMA21"] = c.ewm(span=21, adjust=False).mean()
                visible["RSI"] = compute_rsi(c, 14)
                visible["ATR"] = compute_atr(visible, 14)
                vol_ma = visible["Volume"].rolling(15).mean().replace(0, np.nan)
                visible["VOL_RATIO"] = (visible["Volume"] / vol_ma).fillna(1.0)

                last_bar = visible.iloc[-1]
                price = float(last_bar["Close"])
                vwap_val = float(last_bar["VWAP"]) if not np.isnan(last_bar["VWAP"]) else price
                ema9_val = float(last_bar["EMA9"])
                ema21_val = float(last_bar["EMA21"])
                rsi_val = float(last_bar["RSI"])
                atr_val = float(last_bar["ATR"]) if not np.isnan(last_bar["ATR"]) and last_bar["ATR"] > 0 else price * 0.015
                vol_ratio = float(last_bar["VOL_RATIO"])

                tick_sz = get_idx_tick_size(price, is_idx)
                spread_pct = round((tick_sz / price) * 100.0, 4)

                # Score calculation using only visible data at cutoff_ts
                score = 50
                if price >= vwap_val and ema9_val >= ema21_val:
                    score += 15
                    setup_type = "VWAP_BREAKOUT_UPTREND"
                elif price >= vwap_val and rsi_val < 48:
                    score += 12
                    setup_type = "OVERSOLD_VWAP_RECLAIM"
                elif price >= vwap_val:
                    score += 8
                    setup_type = "INTRADAY_VWAP_SUPPORT"
                else:
                    score -= 10
                    setup_type = "BEARISH_BELOW_VWAP"

                if vol_ratio >= 1.3:
                    score += 10
                if 45 <= rsi_val <= 68:
                    score += 6
                if spread_pct > 1.0:
                    score -= 20
                    setup_type = "HIGH_SPREAD_OR_LOW_NET_EDGE_WAIT"

                score = int(max(10, min(95, score)))

                # Retrieve memory learned up to this point in time
                mem_bundle = self.retriever.retrieve_relevant_memories(
                    ticker=ticker,
                    setup_type=setup_type,
                    timeframe=timeframe,
                    ihsg_regime=ihsg_regime,
                    max_items=4,
                    execution_mode="BACKTEST",
                    strategy_version=strat_ver_tag,
                    as_of=as_of,
                )
                cal_conf, conf_basis = self.retriever.calibrate_confidence(
                    raw_quant_score=score,
                    setup_type=setup_type,
                    timeframe=timeframe,
                    ihsg_regime=ihsg_regime,
                    ticker=ticker,
                    execution_mode="BACKTEST",
                    strategy_version=strat_ver_tag,
                    as_of=as_of,
                )

                direction = "BUY" if (score >= 62 and spread_pct <= 0.80 and not mem_bundle["has_degraded_warning"]) else "WAIT"

                entry_high = round_idx_tick(price, is_idx)
                entry_low = round_idx_tick(max(price - 0.3 * atr_val, price * 0.99), is_idx)
                if entry_low > entry_high:
                    entry_low = entry_high
                sl = round_idx_tick(min(entry_low - 1.0 * atr_val, entry_high * 0.985), is_idx)
                if sl >= entry_low:
                    sl = round_idx_tick(entry_low - tick_sz * 2, is_idx)
                risk_ps = max(entry_high - sl, tick_sz * 2)
                tp1 = round_idx_tick(entry_high + 1.6 * risk_ps, is_idx)
                tp2 = round_idx_tick(entry_high + 2.6 * risk_ps, is_idx)

                est_gross = round(((tp1 - entry_high) / entry_high) * 100.0, 2)
                est_net = round(est_gross - (config.FEE_BUY_PCT + config.FEE_SELL_PCT + config.DEFAULT_SLIPPAGE_PCT), 2)
                est_risk = round(((entry_high - sl) / entry_high) * 100.0, 2)
                rr = round((tp1 - entry_high) / risk_ps, 2)

                snap_id = self.db.save_market_snapshot(
                    {
                        "captured_at_wib": cutoff_ts.isoformat(),
                        "ticker": ticker,
                        "timeframe": timeframe,
                        "last_bar_timestamp": cutoff_ts.isoformat(),
                        "price": entry_high,
                        "open_price": float(last_bar["Open"]),
                        "high_price": float(last_bar["High"]),
                        "low_price": float(last_bar["Low"]),
                        "volume": float(last_bar["Volume"]),
                        "vwap": round_idx_tick(vwap_val, is_idx),
                        "ema9": round_idx_tick(ema9_val, is_idx),
                        "ema21": round_idx_tick(ema21_val, is_idx),
                        "rsi": round(rsi_val, 1),
                        "atr": round(atr_val, 2),
                        "vol_ratio": round(vol_ratio, 2),
                        "ihsg_close": ihsg_info.get("last_close"),
                        "ihsg_change_pct": ihsg_info.get("change_pct"),
                        "ihsg_regime": ihsg_regime,
                        "sector": config.SECTOR_MAP.get(ticker, "GENERAL_IDX"),
                        "tick_size": tick_sz,
                        "spread_pct": spread_pct,
                        "order_book_available": False,
                        "data_source": "yfinance_walk_forward",
                    }
                )

                analysis_id = self.db.save_analysis_prediction(
                    {
                        "snapshot_id": snap_id,
                        "created_at_wib": cutoff_ts.isoformat(),
                        "bar_cutoff_timestamp": cutoff_ts.isoformat(),
                        "ticker": ticker,
                        "timeframe": timeframe,
                        "direction": direction,
                        "execution_mode": "BACKTEST",
                        "strategy_name": config.DEFAULT_STRATEGY_NAME,
                        "setup_type": setup_type,
                        "ihsg_regime": ihsg_regime,
                        "sector": config.SECTOR_MAP.get(ticker, "GENERAL_IDX"),
                        "technical_facts": [f"Close={entry_high}, VWAP={vwap_val:.0f}, RSI={rsi_val:.1f}, VolRatio={vol_ratio:.2f}x"],
                        "interpretations": [f"Walk-forward step at {cutoff_ts.isoformat()} classified as {setup_type}"],
                        "assumptions": ["Walk-forward causal slice (only bars <= cutoff_ts visible)"],
                        "supporting_evidence": [f"Price >= VWAP ({vwap_val:.0f})" if price >= vwap_val else "Wait filter active"],
                        "opposing_evidence": [f"Spread={spread_pct:.2f}%"] if spread_pct > 0.8 else [],
                        "entry_price": entry_high,
                        "entry_low": entry_low,
                        "entry_high": entry_high,
                        "stop_loss": sl,
                        "take_profit_1": tp1,
                        "take_profit_2": tp2,
                        "horizon_bars": horizon_bars,
                        "horizon_minutes": horizon_bars * 15,
                        "evaluate_after_wib": (cutoff_ts + timedelta(minutes=horizon_bars * 15)).isoformat(),
                        "estimated_risk_pct": est_risk,
                        "estimated_gross_return_pct": est_gross,
                        "estimated_net_return_pct": est_net,
                        "reward_to_risk": rr,
                        "raw_quant_score": score,
                        "calibrated_confidence": cal_conf,
                        "confidence_basis": conf_basis,
                        "invalidation_conditions": f"Close < {sl:.0f}",
                        "memory_ids_used": mem_bundle["memory_ids_used"],
                        "strategy_version": strat_ver_tag,
                        "model_version": "walk_forward_engine",
                        "prompt_version": config.AGENT_PROMPT_VERSION,
                    }
                )
                total_created += 1

                # Immediately evaluate this step using strictly post-cutoff bars (> cutoff_ts)
                with self.db.connect() as conn:
                    a_row = dict(
                        conn.execute(
                            "SELECT * FROM analysis_history WHERE analysis_id = ?",
                            (analysis_id,),
                        ).fetchone()
                    )
                outcome = self.evaluator.evaluate_prediction_with_bars(a_row, df)
                if outcome is not None:
                    total_evaluated += 1
                    # Update lessons after each chronological outcome so the next step learns from it!
                    self.evaluator.recompute_strategy_lessons()

        improvement = self.perf.propose_and_validate_strategy_improvement(
            execution_mode="BACKTEST",
            strategy_version=strat_ver_tag,
        )
        return {
            "walk_forward_predictions_created": total_created,
            "walk_forward_outcomes_evaluated": total_evaluated,
            "strategy_improvement": improvement,
        }
