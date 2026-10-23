import json
import uuid
from datetime import datetime
from typing import Any, Optional
import numpy as np
import pandas as pd
import pytz
import yfinance as yf

import config
from memory.database import MemoryDatabase, now_wib_iso

WIB = pytz.timezone(config.TIMEZONE)


def _parse_ts(ts_str: str) -> pd.Timestamp:
    ts = pd.Timestamp(ts_str)
    if ts.tzinfo is None:
        return ts.tz_localize(WIB)
    return ts.tz_convert(WIB)


def compute_max_drawdown_pct(net_returns_pct: list[float]) -> float:
    """Computes chronological maximum drawdown (%) from a sequence of trade net returns (%)."""
    if not net_returns_pct:
        return 0.0
    equity = 100.0
    peak = 100.0
    max_dd = 0.0
    for r in net_returns_pct:
        equity = equity * (1.0 + (r / 100.0))
        if equity > peak:
            peak = equity
        dd = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 3)


class OutcomeEvaluator:
    """
    Chronological, idempotent, zero-leakage evaluator for stock predictions.
    - Never alters `analysis_history`.
    - Never evaluates bars at or before `bar_cutoff_timestamp`.
    - Marks outcomes as `AMBIGUOUS_BAR_ORDER` when both TP and SL (or uncertain entry+TP) occur in the same bar.
    - Deducts realistic transaction costs (buy fee + sell fee + slippage) for `net_return_pct`.
    """

    def __init__(self, db: Optional[MemoryDatabase] = None):
        self.db = db or MemoryDatabase()

    def evaluate_prediction_with_bars(
        self,
        analysis_row: dict[str, Any],
        df_bars: pd.DataFrame,
        fee_buy_pct: float = config.FEE_BUY_PCT,
        fee_sell_pct: float = config.FEE_SELL_PCT,
        slippage_pct: float = config.DEFAULT_SLIPPAGE_PCT,
    ) -> Optional[dict[str, Any]]:
        """
        Evaluates a single prediction record using a DataFrame of OHLCV bars.
        Strictly filters `df_bars` to timestamps > `bar_cutoff_timestamp` (Zero Data Leakage).
        Returns the outcome dictionary if ready to record, or None if insufficient future bars exist yet.
        """
        analysis_id = str(analysis_row["analysis_id"])

        # Idempotency check: if already evaluated in prediction_outcomes, return existing
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM prediction_outcomes WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
            if existing is not None:
                return dict(existing)

        direction = str(analysis_row["direction"]).upper()
        cutoff_ts = _parse_ts(str(analysis_row["bar_cutoff_timestamp"]))
        horizon_bars = int(analysis_row["horizon_bars"])

        if df_bars is None or df_bars.empty:
            return None

        df = df_bars.copy()
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize(WIB)
        else:
            df.index = df.index.tz_convert(WIB)

        # STRICT ZERO DATA LEAKAGE FILTER: only bars strictly AFTER bar_cutoff_timestamp
        future_bars = df[df.index > cutoff_ts].sort_index()
        if future_bars.empty:
            return None

        window_bars = future_bars.iloc[:horizon_bars]
        bars_count = len(window_bars)

        entry_low = float(analysis_row["entry_low"])
        entry_high = float(analysis_row["entry_high"])
        stop_loss = float(analysis_row["stop_loss"])
        tp1 = float(analysis_row["take_profit_1"])
        tp2 = float(analysis_row["take_profit_2"])

        actual_high = float(window_bars["High"].max())
        actual_low = float(window_bars["Low"].min())
        actual_close = float(window_bars["Close"].iloc[-1])

        # Case 1: WAIT or AVOID signal
        if direction in ("WAIT", "AVOID"):
            if bars_count < max(1, min(3, horizon_bars)):
                return None
            avoided_drop = actual_low <= stop_loss
            note = (
                f"WAIT/AVOID signal evaluated over {bars_count} future bars. "
                f"Range: Low={actual_low:.0f}, High={actual_high:.0f}, Close={actual_close:.0f}. "
                + ("Successfully avoided downside below SL." if avoided_drop else "Market remained above SL.")
            )
            return self._insert_outcome(
                analysis_id=analysis_id,
                evaluation_status="SKIPPED_WAIT",
                entry_filled=0,
                entry_fill_price=None,
                entry_fill_timestamp=None,
                exit_price=None,
                exit_timestamp=str(window_bars.index[-1].isoformat()),
                actual_high=actual_high,
                actual_low=actual_low,
                actual_close=actual_close,
                bars_evaluated=bars_count,
                gross_return_pct=0.0,
                net_return_pct=0.0,
                fee_buy_pct=fee_buy_pct,
                fee_sell_pct=fee_sell_pct,
                slippage_pct=slippage_pct,
                duration_minutes=0.0,
                is_ambiguous=0,
                resolution_notes=note,
            )

        # Case 2: BUY signal chronological bar-by-bar walk
        filled = False
        fill_price: Optional[float] = None
        fill_ts: Optional[pd.Timestamp] = None
        exit_price: Optional[float] = None
        exit_ts: Optional[pd.Timestamp] = None
        status = "PENDING"
        is_ambiguous = 0
        notes = ""
        current_sl = stop_loss
        trailing_locked = False

        total_cost_pct = fee_buy_pct + fee_sell_pct + slippage_pct

        for bar_ts, row in window_bars.iterrows():
            b_open = float(row["Open"])
            b_high = float(row["High"])
            b_low = float(row["Low"])
            b_close = float(row["Close"])

            if not filled:
                # Check if price enters the buy zone (b_low <= entry_high)
                if b_low <= entry_high:
                    filled = True
                    fill_ts = bar_ts
                    # Realistic fill price: if market opened below entry_high, fill at max(entry_low, b_open); else entry_high
                    fill_price = max(entry_low, min(b_open, entry_high))

                    # Check same-bar ambiguity on the entry bar itself:
                    hit_tp_same_bar = b_high >= tp1
                    hit_sl_same_bar = b_low <= stop_loss

                    if hit_tp_same_bar and hit_sl_same_bar:
                        status = "AMBIGUOUS_BAR_ORDER"
                        is_ambiguous = 1
                        exit_price = fill_price
                        exit_ts = bar_ts
                        notes = (
                            f"Ambiguous entry bar at {bar_ts.isoformat()}: High ({b_high:.0f}) >= TP1 ({tp1:.0f}) "
                            f"and Low ({b_low:.0f}) <= SL ({stop_loss:.0f}) occurred inside the same candle."
                        )
                        break
                    elif hit_tp_same_bar and b_open > entry_high:
                        # Price opened above entry_high and both dipped to entry_high AND hit TP1 in the same bar:
                        # We cannot know if it hit TP1 first before dipping to entry_high!
                        status = "AMBIGUOUS_BAR_ORDER"
                        is_ambiguous = 1
                        exit_price = fill_price
                        exit_ts = bar_ts
                        notes = (
                            f"Ambiguous entry/TP order at {bar_ts.isoformat()}: Bar opened at {b_open:.0f} (> entry_high {entry_high:.0f}), "
                            f"touched Low {b_low:.0f} and High {b_high:.0f} (>= TP1 {tp1:.0f}) in the same bar."
                        )
                        break
                    elif hit_sl_same_bar:
                        # Price entered at entry_high/open and dropped through stop_loss (< entry_low)
                        status = "RESOLVED_LOSS_SL"
                        exit_price = stop_loss
                        exit_ts = bar_ts
                        notes = f"Entry filled at {fill_price:.0f} and Stop Loss ({stop_loss:.0f}) breached on bar {bar_ts.isoformat()}."
                        break
                    elif hit_tp_same_bar and b_open <= entry_high:
                        # Opened at/below entry_high (immediate fill at open) and rallied to TP1 without touching SL
                        status = "RESOLVED_WIN_TP2" if b_high >= tp2 else "RESOLVED_WIN_TP1"
                        exit_price = tp2 if b_high >= tp2 else tp1
                        exit_ts = bar_ts
                        notes = f"Opened in buy zone ({fill_price:.0f}) and rallied to {exit_price:.0f} on bar {bar_ts.isoformat()}."
                        break
            else:
                # Already filled on a previous bar:
                # Check against TP and current_sl (established prior to this bar)
                hit_tp1 = b_high >= tp1
                hit_tp2 = b_high >= tp2
                hit_sl = b_low <= current_sl

                if hit_tp1 and b_low <= stop_loss:
                    # Touched BOTH TP1 and the original SL in the same candle
                    status = "AMBIGUOUS_BAR_ORDER"
                    is_ambiguous = 1
                    exit_price = fill_price
                    exit_ts = bar_ts
                    notes = (
                        f"Ambiguous bar at {bar_ts.isoformat()}: Both High ({b_high:.0f} >= TP1 {tp1:.0f}) "
                        f"and Low ({b_low:.0f} <= SL {stop_loss:.0f}) touched in the same candle."
                    )
                    break
                elif hit_tp2:
                    status = "RESOLVED_WIN_TP2"
                    exit_price = tp2
                    exit_ts = bar_ts
                    notes = f"Take Profit 2 ({tp2:.0f}) achieved on bar {bar_ts.isoformat()} (Bar High={b_high:.0f})."
                    break
                elif hit_tp1:
                    status = "RESOLVED_WIN_TP1"
                    exit_price = tp1
                    exit_ts = bar_ts
                    notes = f"Take Profit 1 ({tp1:.0f}) achieved on bar {bar_ts.isoformat()} (Bar High={b_high:.0f})."
                    break
                elif hit_sl:
                    if trailing_locked and current_sl > fill_price:
                        status = "RESOLVED_WIN_TRAILING_SL"
                        exit_price = current_sl
                        exit_ts = bar_ts
                        notes = (
                            f"Trailing Stop Loss ({current_sl:.0f}) mengunci profit di bar {bar_ts.isoformat()} "
                            f"(Cuan diamankan setelah sempat naik)."
                        )
                    else:
                        status = "RESOLVED_LOSS_SL"
                        exit_price = stop_loss
                        exit_ts = bar_ts
                        notes = f"Stop Loss ({stop_loss:.0f}) triggered on bar {bar_ts.isoformat()} (Bar Low={b_low:.0f})."
                    break

                # Freqtrade-inspired dynamic trailing stop: update current_sl for SUBSEQUENT bars
                gain_from_fill = ((b_high - fill_price) / fill_price) * 100.0 if fill_price > 0 else 0.0
                if gain_from_fill >= 1.5:
                    trailing_locked = True
                    # Lock in modal + fee broker (BEP + 0.50%)
                    current_sl = max(current_sl, fill_price * 1.005)
                    if gain_from_fill >= 2.5:
                        # Lock in +1.50% profit
                        current_sl = max(current_sl, fill_price * 1.015)

        # If not resolved by TP/SL/Ambiguous yet: check if full horizon has elapsed
        if status == "PENDING":
            if bars_count < horizon_bars:
                # Horizon not yet complete; wait for more bars before recording terminal outcome
                return None

            if not filled:
                status = "EXPIRED_NO_FILL"
                notes = (
                    f"Order expired after {bars_count} horizon bars without touching entry_high ({entry_high:.0f}). "
                    f"Lowest price in horizon was {actual_low:.0f}."
                )
                return self._insert_outcome(
                    analysis_id=analysis_id,
                    evaluation_status=status,
                    entry_filled=0,
                    entry_fill_price=None,
                    entry_fill_timestamp=None,
                    exit_price=None,
                    exit_timestamp=str(window_bars.index[-1].isoformat()),
                    actual_high=actual_high,
                    actual_low=actual_low,
                    actual_close=actual_close,
                    bars_evaluated=bars_count,
                    gross_return_pct=0.0,
                    net_return_pct=0.0,
                    fee_buy_pct=fee_buy_pct,
                    fee_sell_pct=fee_sell_pct,
                    slippage_pct=slippage_pct,
                    duration_minutes=0.0,
                    is_ambiguous=0,
                    resolution_notes=notes,
                )
            else:
                status = "RESOLVED_TIME_EXIT"
                exit_price = actual_close
                exit_ts = window_bars.index[-1]
                notes = f"Horizon of {bars_count} bars completed; time-exit at horizon close ({exit_price:.0f})."

        # Calculate duration & returns
        assert fill_price is not None and exit_price is not None and fill_ts is not None and exit_ts is not None
        duration_mins = max(0.0, (exit_ts - fill_ts).total_seconds() / 60.0)
        if is_ambiguous:
            gross_ret = 0.0
            net_ret = -total_cost_pct
        else:
            gross_ret = ((exit_price - fill_price) / fill_price) * 100.0
            net_ret = gross_ret - total_cost_pct

        return self._insert_outcome(
            analysis_id=analysis_id,
            evaluation_status=status,
            entry_filled=1,
            entry_fill_price=round(fill_price, 2),
            entry_fill_timestamp=str(fill_ts.isoformat()),
            exit_price=round(exit_price, 2),
            exit_timestamp=str(exit_ts.isoformat()),
            actual_high=actual_high,
            actual_low=actual_low,
            actual_close=actual_close,
            bars_evaluated=bars_count,
            gross_return_pct=round(gross_ret, 4),
            net_return_pct=round(net_ret, 4),
            fee_buy_pct=fee_buy_pct,
            fee_sell_pct=fee_sell_pct,
            slippage_pct=slippage_pct,
            duration_minutes=round(duration_mins, 1),
            is_ambiguous=is_ambiguous,
            resolution_notes=notes,
        )

    def _insert_outcome(
        self,
        analysis_id: str,
        evaluation_status: str,
        entry_filled: int,
        entry_fill_price: Optional[float],
        entry_fill_timestamp: Optional[str],
        exit_price: Optional[float],
        exit_timestamp: Optional[str],
        actual_high: float,
        actual_low: float,
        actual_close: float,
        bars_evaluated: int,
        gross_return_pct: float,
        net_return_pct: float,
        fee_buy_pct: float,
        fee_sell_pct: float,
        slippage_pct: float,
        duration_minutes: float,
        is_ambiguous: int,
        resolution_notes: str,
    ) -> dict[str, Any]:
        outcome_id = str(uuid.uuid4())
        evaluated_at = now_wib_iso()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO prediction_outcomes (
                    outcome_id, analysis_id, evaluated_at_wib, evaluation_status,
                    entry_filled, entry_fill_price, entry_fill_timestamp,
                    exit_price, exit_timestamp,
                    actual_high_in_horizon, actual_low_in_horizon, actual_close_at_horizon,
                    bars_evaluated, gross_return_pct, net_return_pct,
                    fee_buy_pct, fee_sell_pct, slippage_pct,
                    duration_minutes, is_ambiguous, resolution_notes
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?
                )
                """,
                (
                    outcome_id,
                    analysis_id,
                    evaluated_at,
                    evaluation_status,
                    entry_filled,
                    entry_fill_price,
                    entry_fill_timestamp,
                    exit_price,
                    exit_timestamp,
                    actual_high,
                    actual_low,
                    actual_close,
                    bars_evaluated,
                    gross_return_pct,
                    net_return_pct,
                    fee_buy_pct,
                    fee_sell_pct,
                    slippage_pct,
                    duration_minutes,
                    is_ambiguous,
                    resolution_notes,
                ),
            )
            row = conn.execute(
                "SELECT * FROM prediction_outcomes WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
            ah = conn.execute(
                "SELECT entry_high, take_profit_1, stop_loss FROM analysis_history WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
            res = dict(row)

        if ah:
            try:
                self.db.grade_ai_panel_votes_for_outcome(
                    analysis_id=analysis_id,
                    evaluation_status=evaluation_status,
                    net_return_pct=net_return_pct,
                    actual_high=actual_high,
                    actual_low=actual_low,
                    entry_high=float(ah["entry_high"]),
                    take_profit_1=float(ah["take_profit_1"]),
                    stop_loss=float(ah["stop_loss"]),
                )
            except Exception:
                pass
        return res

    def evaluate_pending_predictions(self) -> list[dict[str, Any]]:
        """
        Finds all predictions in `analysis_history` that do not yet have a record in `prediction_outcomes`,
        fetches actual market bars from `yfinance`, evaluates those whose horizon is available,
        and updates `strategy_lessons`.
        """
        with self.db.connect() as conn:
            pending_rows = conn.execute(
                """
                SELECT a.*
                FROM analysis_history a
                LEFT JOIN prediction_outcomes o ON a.analysis_id = o.analysis_id
                WHERE o.outcome_id IS NULL
                ORDER BY a.created_at_wib ASC
                """
            ).fetchall()

        if not pending_rows:
            return []

        # Group by (ticker, timeframe) to minimize API calls
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in pending_rows:
            d = dict(r)
            key = (str(d["ticker"]), str(d["timeframe"]))
            grouped.setdefault(key, []).append(d)

        newly_resolved: list[dict[str, Any]] = []
        for (ticker, timeframe), items in grouped.items():
            period = "5d" if timeframe in ("1m", "5m") else ("1mo" if timeframe == "15m" else "6mo")
            try:
                tk = yf.Ticker(ticker)
                df_bars = tk.history(period=period, interval=timeframe, auto_adjust=False)
            except Exception:
                continue
            if df_bars is None or df_bars.empty:
                continue

            for item in items:
                res = self.evaluate_prediction_with_bars(item, df_bars)
                if res is not None:
                    newly_resolved.append(res)

        if newly_resolved:
            self.recompute_strategy_lessons()
        return newly_resolved

    def recompute_strategy_lessons(self) -> list[dict[str, Any]]:
        """
        Aggregates all evaluated outcomes into `strategy_lessons` (both global `ticker_scope='ALL'`
        and ticker-specific lessons), strictly separating measured facts, testable hypotheses,
        and AI interpretations.
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.strategy_name,
                    a.strategy_version,
                    a.setup_type,
                    a.timeframe,
                    a.ihsg_regime,
                    a.ticker,
                    a.execution_mode,
                    a.bar_cutoff_timestamp,
                    o.evaluation_status,
                    o.entry_filled,
                    o.gross_return_pct,
                    o.net_return_pct,
                    o.is_ambiguous
                FROM analysis_history a
                INNER JOIN prediction_outcomes o ON a.analysis_id = o.analysis_id
                WHERE a.direction = 'BUY'
                ORDER BY a.bar_cutoff_timestamp ASC
                """
            ).fetchall()

        if not rows:
            return []

        buckets: dict[tuple[str, str, str, str, str, str, str], list[dict[str, Any]]] = {}
        for r in rows:
            d = dict(r)
            # 1. Global setup bucket across all tickers
            k_all = (
                d["strategy_name"],
                d["strategy_version"],
                d["setup_type"],
                d["timeframe"],
                d["ihsg_regime"],
                "ALL",
                d["execution_mode"],
            )
            buckets.setdefault(k_all, []).append(d)
            # 2. Ticker-specific setup bucket
            k_tk = (
                d["strategy_name"],
                d["strategy_version"],
                d["setup_type"],
                d["timeframe"],
                d["ihsg_regime"],
                d["ticker"],
                d["execution_mode"],
            )
            buckets.setdefault(k_tk, []).append(d)

        lessons_saved: list[dict[str, Any]] = []
        now_iso = now_wib_iso()

        with self.db.connect() as conn:
            for key, items in buckets.items():
                strat_name, strat_ver, setup_type, tf, regime, ticker_scope, exec_mode = key
                sample_size = len(items)
                ambiguous_count = sum(1 for x in items if x["is_ambiguous"] == 1 or x["evaluation_status"] == "AMBIGUOUS_BAR_ORDER")
                resolved = [
                    x for x in items
                    if x["entry_filled"] == 1
                    and x["is_ambiguous"] == 0
                    and x["evaluation_status"].startswith("RESOLVED_")
                ]
                resolved_count = len(resolved)
                net_returns = [float(x["net_return_pct"]) for x in resolved]
                wins = [r for r in net_returns if r > 0]
                losses = [r for r in net_returns if r <= 0]

                win_count = len(wins)
                loss_count = len(losses)
                win_rate = round(win_count / resolved_count, 4) if resolved_count > 0 else 0.0
                avg_win = round(float(np.mean(wins)), 4) if wins else 0.0
                avg_loss = round(float(np.mean(losses)), 4) if losses else 0.0
                expectancy = round(float(np.mean(net_returns)), 4) if net_returns else 0.0

                gross_profits = sum(wins)
                gross_losses = abs(sum(losses))
                if gross_losses > 0:
                    profit_factor = round(gross_profits / gross_losses, 3)
                elif gross_profits > 0:
                    profit_factor = 9.99
                else:
                    profit_factor = 0.0

                max_dd = compute_max_drawdown_pct(net_returns)
                cum_net = round(sum(net_returns), 4)

                if resolved_count < 10:
                    uncertainty = "HIGH_UNCERTAINTY_SMALL_SAMPLE (N < 10)"
                elif resolved_count < 30:
                    uncertainty = "MODERATE_UNCERTAINTY (10 <= N < 30)"
                else:
                    uncertainty = "LOW_STATISTICALLY_SIGNIFICANT (N >= 30)"

                if resolved_count < 5:
                    val_status = "CANDIDATE"
                elif expectancy > 0.15 and profit_factor >= 1.15 and win_rate >= 0.45:
                    val_status = "VALIDATED"
                elif resolved_count >= 5 and (expectancy < -0.15 or win_rate < 0.35):
                    val_status = "DEGRADED"
                else:
                    val_status = "CANDIDATE"

                measured_facts = {
                    "sample_size_total": sample_size,
                    "resolved_trades": resolved_count,
                    "ambiguous_trades": ambiguous_count,
                    "win_count": win_count,
                    "loss_count": loss_count,
                    "win_rate_pct": round(win_rate * 100, 1),
                    "avg_win_net_pct": avg_win,
                    "avg_loss_net_pct": avg_loss,
                    "expectancy_net_pct": expectancy,
                    "profit_factor": profit_factor,
                    "max_drawdown_pct": max_dd,
                    "cumulative_net_return_pct": cum_net,
                }

                if val_status == "VALIDATED":
                    hypothesis = (
                        f"Setup '{setup_type}' pada timeframe {tf} saat rezim IHSG '{regime}' ({ticker_scope}) "
                        f"menghasilkan nilai harapan bersih positif ({expectancy:+.2f}%/trade, PF={profit_factor:.2f}) setelah dikurangi biaya transaksi."
                    )
                    interpretation = (
                        f"GUNAKAN SETUP INI: Dari {resolved_count} transaksi terkonfirmasi, win rate mencapai {win_rate*100:.1f}%. "
                        f"Pertahankan disiplin entry di area VWAP/Support."
                    )
                elif val_status == "DEGRADED":
                    hypothesis = (
                        f"Setup '{setup_type}' pada timeframe {tf} saat rezim IHSG '{regime}' ({ticker_scope}) "
                        f"mengalami degradasi performa (Expectancy={expectancy:+.2f}%/trade, WinRate={win_rate*100:.1f}%)."
                    )
                    interpretation = (
                        f"PERINGATAN DEGRADASI: Jangan gunakan setup '{setup_type}' secara agresif pada kondisi '{regime}' "
                        f"karena rata-rata rugi bersih ({avg_loss:.2f}%) menggerus ekspektasi profit. Pilih WAIT atau perketat konfirmasi volume."
                    )
                else:
                    hypothesis = (
                        f"Setup '{setup_type}' ({tf}, {regime}, {ticker_scope}) masih dalam tahap pengumpulan sampel "
                        f"(N={resolved_count} resolved, Expectancy={expectancy:+.2f}%)."
                    )
                    interpretation = (
                        f"SAMPEL TERBATAS ({uncertainty}): Gunakan ukuran posisi konservatif dan jangan menganggap win rate {win_rate*100:.1f}% sebagai kepastian."
                    )

                lesson_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO strategy_lessons (
                        lesson_id, strategy_name, strategy_version, setup_type,
                        timeframe, ihsg_regime, ticker_scope, execution_mode,
                        sample_size, resolved_trades, ambiguous_trades,
                        win_count, loss_count, win_rate,
                        avg_win_net_pct, avg_loss_net_pct, expectancy_net_pct,
                        profit_factor, max_drawdown_pct, cumulative_net_return_pct,
                        uncertainty_level, measured_facts_json, hypothesis_text,
                        ai_interpretation_text, validation_status, evaluated_at_wib
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?
                    )
                    ON CONFLICT(strategy_name, strategy_version, setup_type, timeframe, ihsg_regime, ticker_scope, execution_mode)
                    DO UPDATE SET
                        sample_size = excluded.sample_size,
                        resolved_trades = excluded.resolved_trades,
                        ambiguous_trades = excluded.ambiguous_trades,
                        win_count = excluded.win_count,
                        loss_count = excluded.loss_count,
                        win_rate = excluded.win_rate,
                        avg_win_net_pct = excluded.avg_win_net_pct,
                        avg_loss_net_pct = excluded.avg_loss_net_pct,
                        expectancy_net_pct = excluded.expectancy_net_pct,
                        profit_factor = excluded.profit_factor,
                        max_drawdown_pct = excluded.max_drawdown_pct,
                        cumulative_net_return_pct = excluded.cumulative_net_return_pct,
                        uncertainty_level = excluded.uncertainty_level,
                        measured_facts_json = excluded.measured_facts_json,
                        hypothesis_text = excluded.hypothesis_text,
                        ai_interpretation_text = excluded.ai_interpretation_text,
                        validation_status = excluded.validation_status,
                        evaluated_at_wib = excluded.evaluated_at_wib
                    """,
                    (
                        lesson_id,
                        strat_name,
                        strat_ver,
                        setup_type,
                        tf,
                        regime,
                        ticker_scope,
                        exec_mode,
                        sample_size,
                        resolved_count,
                        ambiguous_count,
                        win_count,
                        loss_count,
                        win_rate,
                        avg_win,
                        avg_loss,
                        expectancy,
                        profit_factor,
                        max_dd,
                        cum_net,
                        uncertainty,
                        json.dumps(measured_facts, ensure_ascii=False),
                        hypothesis,
                        interpretation,
                        val_status,
                        now_iso,
                    ),
                )
                lessons_saved.append(measured_facts)

        return lessons_saved
