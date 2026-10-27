import json
import uuid
from datetime import datetime
from typing import Any, Optional
import numpy as np
import pandas as pd
import yfinance as yf

import config
from memory.database import MemoryDatabase, now_wib_iso
from memory.evaluator import compute_max_drawdown_pct


class PerformanceAnalyzer:
    """
    Phase 6 & Phase 7:
    - Generates comprehensive, auditable performance reports (separated by PAPER, BACKTEST, LIVE).
    - Computes Win Rate, Avg Win/Loss, Expectancy, Profit Factor, Max Drawdown, Net Return,
      per-ticker/timeframe/setup/regime breakdowns, and Confidence Calibration (Brier Score).
    - Implements Controlled Strategy Improvement with chronological Train / Out-Of-Sample (OOS)
      split, baseline comparison, versioning, and instant rollback.
    """

    def __init__(self, db: Optional[MemoryDatabase] = None):
        self.db = db or MemoryDatabase()

    def _compute_bucket_metrics(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        total_evaluated = len(rows)
        ambiguous = sum(1 for r in rows if r["is_ambiguous"] == 1 or r["evaluation_status"] == "AMBIGUOUS_BAR_ORDER")
        no_fill = sum(1 for r in rows if r["evaluation_status"] == "EXPIRED_NO_FILL")
        skipped_wait = sum(1 for r in rows if r["evaluation_status"] == "SKIPPED_WAIT")

        resolved = [
            r for r in rows
            if r["direction"] == "BUY"
            and r["entry_filled"] == 1
            and r["is_ambiguous"] == 0
            and str(r["evaluation_status"]).startswith("RESOLVED_")
        ]
        n_res = len(resolved)
        net_rets = [float(r["net_return_pct"]) for r in resolved]
        gross_rets = [float(r["gross_return_pct"]) for r in resolved]

        wins = [x for x in net_rets if x > 0]
        losses = [x for x in net_rets if x <= 0]

        win_rate = round((len(wins) / n_res) * 100.0, 2) if n_res > 0 else 0.0
        avg_win = round(float(np.mean(wins)), 3) if wins else 0.0
        avg_loss = round(float(np.mean(losses)), 3) if losses else 0.0
        expectancy = round(float(np.mean(net_rets)), 3) if net_rets else 0.0

        sum_wins = sum(wins)
        sum_losses = abs(sum(losses))
        if sum_losses > 0:
            pf = round(sum_wins / sum_losses, 3)
        elif sum_wins > 0:
            pf = 9.99
        else:
            pf = 0.0

        max_dd = compute_max_drawdown_pct(net_rets)
        cum_net = round(sum(net_rets), 3)
        cum_gross = round(sum(gross_rets), 3)

        sharpe = 0.0
        sortino = 0.0
        if n_res > 1:
            mean_ret = float(np.mean(net_rets))
            std_ret = float(np.std(net_rets, ddof=1))
            downside = [r for r in net_rets if r < 0]
            downside_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
            sharpe = round(mean_ret / std_ret, 3) if std_ret > 0 else 0.0
            sortino = round(mean_ret / downside_std, 3) if downside_std > 0 else 0.0

        return {
            "total_evaluated": total_evaluated,
            "resolved_trades": n_res,
            "ambiguous_trades": ambiguous,
            "expired_no_fill": no_fill,
            "skipped_wait": skipped_wait,
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate_pct": win_rate,
            "avg_win_net_pct": avg_win,
            "avg_loss_net_pct": avg_loss,
            "expectancy_net_pct": expectancy,
            "profit_factor": pf,
            "max_drawdown_pct": max_dd,
            "sharpe_per_trade": sharpe,
            "sortino_per_trade": sortino,
            "cumulative_gross_return_pct": cum_gross,
            "cumulative_net_return_pct": cum_net,
        }

    def _benchmark_comparison(
        self, rows: list[dict[str, Any]], overall: dict[str, Any]
    ) -> dict[str, Any]:
        """Best-effort alpha vs IHSG over the same first/last prediction window."""
        if not rows:
            return {}
        try:
            starts = sorted(str(r["bar_cutoff_timestamp"]) for r in rows)
            start = pd.Timestamp(starts[0]).date().isoformat()
            end = (pd.Timestamp.now() + pd.Timedelta(days=1)).date().isoformat()
            df = yf.Ticker("^JKSE").history(start=start, end=end, interval="1d", auto_adjust=True)
            if df is None or df.empty or len(df) < 2:
                return {"symbol": "^JKSE", "note": "Data benchmark tidak tersedia"}
            bench_ret = ((float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0])) - 1.0) * 100.0
            strat_ret = float(overall.get("cumulative_net_return_pct", 0.0))
            return {
                "symbol": "^JKSE",
                "start": start,
                "end": str(df.index[-1].date()),
                "benchmark_return_pct": round(bench_ret, 2),
                "strategy_return_pct": round(strat_ret, 2),
                "alpha_pct": round(strat_ret - bench_ret, 2),
                "note": "Perbandingan sederhana, bukan beta-adjusted.",
            }
        except Exception:
            return {"symbol": "^JKSE", "note": "Gagal memuat benchmark"}

    def get_performance_summary(self, execution_mode: Optional[str] = None) -> dict[str, Any]:
        """Returns structured performance metrics across modes, tickers, setups, regimes, and versions."""
        with self.db.connect() as conn:
            total_predictions = conn.execute("SELECT COUNT(*) AS cnt FROM analysis_history").fetchone()["cnt"]
            query = """
                SELECT
                    a.analysis_id, a.ticker, a.timeframe, a.direction, a.execution_mode,
                    a.strategy_name, a.strategy_version, a.setup_type, a.ihsg_regime,
                    a.calibrated_confidence, a.bar_cutoff_timestamp, a.sector,
                    o.evaluation_status, o.entry_filled, o.gross_return_pct,
                    o.net_return_pct, o.is_ambiguous, o.evaluated_at_wib
                FROM analysis_history a
                INNER JOIN prediction_outcomes o ON a.analysis_id = o.analysis_id
            """
            params: tuple[Any, ...] = ()
            if execution_mode:
                query += " WHERE a.execution_mode = ?"
                params = (execution_mode.upper(),)
            query += " ORDER BY a.bar_cutoff_timestamp ASC"
            all_rows = [dict(r) for r in conn.execute(query, params).fetchall()]

        by_mode: dict[str, dict[str, Any]] = {}
        for mode in ("PAPER", "BACKTEST", "LIVE"):
            m_rows = [r for r in all_rows if r["execution_mode"] == mode]
            if m_rows or execution_mode == mode:
                by_mode[mode] = self._compute_bucket_metrics(m_rows)

        # Breakdowns for the requested mode (or all rows if None)
        overall = self._compute_bucket_metrics(all_rows)

        def _group_metrics(field: str) -> dict[str, dict[str, Any]]:
            grouped: dict[str, list[dict[str, Any]]] = {}
            for r in all_rows:
                grouped.setdefault(str(r[field]), []).append(r)
            return {k: self._compute_bucket_metrics(v) for k, v in grouped.items()}

        by_ticker = _group_metrics("ticker")
        by_timeframe = _group_metrics("timeframe")
        by_setup = _group_metrics("setup_type")
        by_regime = _group_metrics("ihsg_regime")
        by_version = _group_metrics("strategy_version")
        by_sector = _group_metrics("sector")
        sector_exposure_pct: dict[str, float] = {}
        if all_rows:
            sector_counts: dict[str, int] = {}
            for r in all_rows:
                key = str(r.get("sector") or "UNKNOWN")
                sector_counts[key] = sector_counts.get(key, 0) + 1
            sector_exposure_pct = {
                k: round(v / len(all_rows) * 100.0, 1) for k, v in sector_counts.items()
            }

        benchmark = self._benchmark_comparison(all_rows, overall)

        # Confidence Calibration Analysis (Brier Score & Bucket Comparison)
        resolved_buy = [
            r for r in all_rows
            if r["direction"] == "BUY"
            and r["entry_filled"] == 1
            and r["is_ambiguous"] == 0
            and str(r["evaluation_status"]).startswith("RESOLVED_")
        ]
        calibration_buckets: dict[str, dict[str, Any]] = {}
        brier_score = None
        if resolved_buy:
            sq_errors = []
            bucket_defs = [
                ("Low (<45%)", 0.0, 0.45),
                ("Medium (45%-60%)", 0.45, 0.60),
                ("High (>60%)", 0.60, 1.01),
            ]
            for label, lo, hi in bucket_defs:
                b_items = [
                    r for r in resolved_buy
                    if lo <= float(r["calibrated_confidence"]) < hi
                ]
                if b_items:
                    pred_avg = float(np.mean([float(x["calibrated_confidence"]) for x in b_items])) * 100.0
                    actual_wr = (sum(1 for x in b_items if float(x["net_return_pct"]) > 0) / len(b_items)) * 100.0
                    calibration_buckets[label] = {
                        "count": len(b_items),
                        "avg_predicted_confidence_pct": round(pred_avg, 1),
                        "actual_realized_win_rate_pct": round(actual_wr, 1),
                        "calibration_gap_pct": round(actual_wr - pred_avg, 1),
                    }
            for r in resolved_buy:
                outcome_bin = 1.0 if float(r["net_return_pct"]) > 0 else 0.0
                p_conf = float(r["calibrated_confidence"])
                sq_errors.append((p_conf - outcome_bin) ** 2)
            brier_score = round(float(np.mean(sq_errors)), 4)

        return {
            "total_predictions_recorded": total_predictions,
            "overall": overall,
            "by_execution_mode": by_mode,
            "by_ticker": by_ticker,
            "by_timeframe": by_timeframe,
            "by_setup_type": by_setup,
            "by_ihsg_regime": by_regime,
            "by_strategy_version": by_version,
            "by_sector": by_sector,
            "sector_exposure_pct": sector_exposure_pct,
            "benchmark": benchmark,
            "confidence_calibration": {
                "brier_score": brier_score,
                "buckets": calibration_buckets,
            },
        }

    def format_performance_report_markdown(self, execution_mode: Optional[str] = None) -> str:
        """Formats the performance evaluation dashboard for Telegram & CLI."""
        summary = self.get_performance_summary(execution_mode)
        ov = summary["overall"]
        lines = [
            "📊 *LAPORAN EVALUASI PERFORMA & SELF-LEARNING AI*",
            f"• *Total Analisis Tercatat:* {summary['total_predictions_recorded']}",
            f"• *Total Selesai Dievaluasi:* {ov['total_evaluated']} (Transaksi Terisi & Valid: *{ov['resolved_trades']}*, Ambigu: *{ov['ambiguous_trades']}*, Tunggu/Wait: *{ov['skipped_wait']}*)",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if ov["resolved_trades"] == 0:
            lines.append(
                "ℹ️ _Belum ada transaksi BUY yang selesai melewati horizon evaluasi. "
                "Sistem tidak mengklaim profitabilitas sebelum ada sampel evaluasi yang cukup._"
            )
            return "\n".join(lines)

        lines.extend([
            "📈 *Metrik Utama (Setelah Biaya Transaksi & Slippage):*",
            f"• *Win Rate:* {ov['win_rate_pct']:.1f}% ({ov['win_count']} Menang / {ov['loss_count']} Kalah)",
            f"• *Average Win / Loss (Bersih):* {ov['avg_win_net_pct']:+.2f}% / {ov['avg_loss_net_pct']:+.2f}%",
            f"• *Expectancy per Transaksi:* *{ov['expectancy_net_pct']:+.2f}%*",
            f"• *Profit Factor:* {ov['profit_factor']:.2f}",
            f"• *Sharpe / Sortino (per trade):* {ov.get('sharpe_per_trade', 0.0):.2f} / {ov.get('sortino_per_trade', 0.0):.2f}",
            f"• *Maximum Drawdown:* {ov['max_drawdown_pct']:.2f}%",
            f"• *Total Return Bersih Kumulatif:* *{ov['cumulative_net_return_pct']:+.2f}%* (Kotor: {ov['cumulative_gross_return_pct']:+.2f}%)",
        ])

        if summary["by_execution_mode"]:
            lines.append("\n🗂️ *Pemisahan Mode Eksekusi (Paper vs Backtest vs Live):*")
            for m_name, m_stat in summary["by_execution_mode"].items():
                if m_stat["total_evaluated"] > 0:
                    lines.append(
                        f"• *{m_name}:* N={m_stat['resolved_trades']} | WR={m_stat['win_rate_pct']:.1f}% | "
                        f"Exp={m_stat['expectancy_net_pct']:+.2f}% | Net={m_stat['cumulative_net_return_pct']:+.2f}% | MaxDD={m_stat['max_drawdown_pct']:.2f}%"
                    )

        if summary["by_setup_type"]:
            lines.append("\n🛠️ *Performa per Setup Strategi:*")
            for st_name, st_stat in summary["by_setup_type"].items():
                if st_stat["resolved_trades"] > 0:
                    lines.append(
                        f"• `{st_name}` (N={st_stat['resolved_trades']}): WR={st_stat['win_rate_pct']:.1f}%, "
                        f"Exp={st_stat['expectancy_net_pct']:+.2f}%, PF={st_stat['profit_factor']:.2f}"
                    )

        if summary["by_ihsg_regime"]:
            lines.append("\n🌤️ *Performa per Kondisi Pasar (IHSG):*")
            for rg_name, rg_stat in summary["by_ihsg_regime"].items():
                if rg_stat["resolved_trades"] > 0:
                    lines.append(
                        f"• `{rg_name}` (N={rg_stat['resolved_trades']}): WR={rg_stat['win_rate_pct']:.1f}%, "
                        f"Exp={rg_stat['expectancy_net_pct']:+.2f}%"
                    )

        if len(summary["by_strategy_version"]) > 1:
            lines.append("\n🔄 *Perbandingan Versi Strategi (Before vs After):*")
            for v_tag, v_stat in summary["by_strategy_version"].items():
                lines.append(
                    f"• *v{v_tag}* (N={v_stat['resolved_trades']}): WR={v_stat['win_rate_pct']:.1f}%, "
                    f"Exp={v_stat['expectancy_net_pct']:+.2f}%, MaxDD={v_stat['max_drawdown_pct']:.2f}%"
                )

        if summary.get("sector_exposure_pct"):
            exposure = ", ".join(
                f"{k}={v:.0f}%" for k, v in sorted(summary["sector_exposure_pct"].items(), key=lambda x: -x[1])
            )
            lines.append(f"\n🏭 *Eksposur Sektor (berdasarkan jumlah prediksi):* {exposure}")

        bench = summary.get("benchmark") or {}
        if bench.get("benchmark_return_pct") is not None:
            lines.append(
                f"\n📊 *Benchmark IHSG:* {bench['benchmark_return_pct']:+.2f}% | "
                f"Strategi: {bench['strategy_return_pct']:+.2f}% | Alpha: *{bench['alpha_pct']:+.2f}%*"
            )

        cal = summary["confidence_calibration"]
        if cal["brier_score"] is not None:
            lines.append(f"\n🎯 *Kalibrasi Confidence (Brier Score = {cal['brier_score']:.4f}):*")
            for b_label, b_val in cal["buckets"].items():
                lines.append(
                    f"• {b_label} (N={b_val['count']}): Prediksi={b_val['avg_predicted_confidence_pct']:.1f}% vs Aktual={b_val['actual_realized_win_rate_pct']:.1f}%"
                )

        if ov["resolved_trades"] < 20:
            lines.append(
                f"\n⚠️ _Catatan Statistik: Jumlah sampel transaksi selesai saat ini N={ov['resolved_trades']} (< 20). "
                "Secara kuantitatif masih terdapat tingkat ketidakpastian sampel; belum boleh diklaim menguntungkan secara permanen._"
            )
        return "\n".join(lines)

    # =========================================================================
    # PHASE 7: CONTROLLED STRATEGY IMPROVEMENT (TRAIN / OOS VALIDATION & ROLLBACK)
    # =========================================================================

    def propose_and_validate_strategy_improvement(
        self,
        strategy_name: str = config.DEFAULT_STRATEGY_NAME,
        min_total_samples: int = 16,
        execution_mode: Optional[str] = None,
        strategy_version: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Evaluates whether a controlled parameter improvement is justified by historical data:
        1. Splits chronological resolved trades into In-Sample Train (first 60%) and Out-Of-Sample OOS (last 40%).
        2. Refuses to alter parameters if sample size < `min_total_samples` (prevents knee-jerk changes on a few losses).
        3. Forms a hypothesis on the Train split (e.g., raising `min_intraday_score` threshold if lower-score trades have negative net expectancy).
        4. Tests the hypothesis strictly on the unseen OOS split and compares OOS Net Expectancy & Max Drawdown against baseline.
        5. Creates a versioned record in `strategy_versions` (`ACTIVE` if OOS validated, `REJECTED` otherwise).
        """
        active_ver = self.db.get_active_strategy_version(strategy_name)
        current_tag = active_ver["version_tag"]
        current_params = dict(active_ver["parameters"])

        where = [
            "a.strategy_name = ?",
            "a.direction = 'BUY'",
            "o.entry_filled = 1",
            "o.is_ambiguous = 0",
            "o.evaluation_status LIKE 'RESOLVED_%'",
        ]
        params: list[Any] = [strategy_name]
        if execution_mode:
            where.append("a.execution_mode = ?")
            params.append(execution_mode.upper())
        if strategy_version:
            where.append("a.strategy_version = ?")
            params.append(strategy_version)

        with self.db.connect() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    f"""
                    SELECT
                        a.analysis_id, a.raw_quant_score, a.setup_type, a.ihsg_regime,
                        a.bar_cutoff_timestamp, a.execution_mode, a.strategy_version,
                        o.net_return_pct, o.is_ambiguous, o.entry_filled, o.evaluation_status
                    FROM analysis_history a
                    INNER JOIN prediction_outcomes o ON a.analysis_id = o.analysis_id
                    WHERE {' AND '.join(where)}
                    ORDER BY a.bar_cutoff_timestamp ASC
                    """,
                    tuple(params),
                ).fetchall()
            ]

        n_total = len(rows)
        if n_total < min_total_samples:
            return {
                "action": "NO_CHANGE_INSUFFICIENT_SAMPLES",
                "reason": (
                    f"Jumlah sampel transaksi selesai (N={n_total}) belum mencapai batas minimal "
                    f"validasi statistik (N >= {min_total_samples}). Parameter strategi v{current_tag} dipertahankan."
                ),
                "active_version": current_tag,
            }

        split_idx = int(n_total * 0.60)
        train_rows = rows[:split_idx]
        oos_rows = rows[split_idx:]

        if len(train_rows) < 8 or len(oos_rows) < 5:
            return {
                "action": "NO_CHANGE_INSUFFICIENT_SPLIT",
                "reason": "Sampel Train atau Out-of-Sample terlalu kecil.",
                "active_version": current_tag,
            }

        cur_min_score = int(current_params.get("min_intraday_score", 68))

        # Analyze Train split to form hypothesis without touching OOS split
        low_score_train = [float(r["net_return_pct"]) for r in train_rows if int(r["raw_quant_score"]) < cur_min_score + 4]
        high_score_train = [float(r["net_return_pct"]) for r in train_rows if int(r["raw_quant_score"]) >= cur_min_score + 4]

        if not high_score_train or not low_score_train:
            return {
                "action": "NO_CHANGE_NO_BETTER_HYPOTHESIS",
                "reason": "Tidak ditemukan perbedaan signifikan antar ambang skor pada data Train.",
                "active_version": current_tag,
            }

        cand_min_score = min(78, cur_min_score + 4)
        hypothesis = (
            f"Menikkan ambang `min_intraday_score` dari {cur_min_score} ke {cand_min_score} "
            f"karena pada data Train (N={len(train_rows)}), sinyal dengan skor < {cand_min_score} "
            f"memiliki rata-rata return bersih {float(np.mean(low_score_train)):+.2f}% sedangkan skor >= {cand_min_score} "
            f"menghasilkan {float(np.mean(high_score_train)):+.2f}%."
        )

        # Evaluate strictly on unseen Out-Of-Sample (OOS) split
        baseline_oos_rets = [float(r["net_return_pct"]) for r in oos_rows if int(r["raw_quant_score"]) >= cur_min_score]
        candidate_oos_rets = [float(r["net_return_pct"]) for r in oos_rows if int(r["raw_quant_score"]) >= cand_min_score]

        if len(candidate_oos_rets) < 3:
            return {
                "action": "REJECTED_TOO_FEW_OOS_TRADES",
                "hypothesis": hypothesis,
                "reason": "Filter kandidat menyisakan terlalu sedikit transaksi pada data Out-Of-Sample.",
                "active_version": current_tag,
            }

        base_exp = round(float(np.mean(baseline_oos_rets)), 3) if baseline_oos_rets else 0.0
        cand_exp = round(float(np.mean(candidate_oos_rets)), 3)
        base_dd = compute_max_drawdown_pct(baseline_oos_rets)
        cand_dd = compute_max_drawdown_pct(candidate_oos_rets)

        parts = [int(x) for x in current_tag.split(".")]
        new_version_tag = f"{parts[0]}.{parts[1]}.{parts[2] + 1}"
        new_params = dict(current_params)
        new_params["min_intraday_score"] = cand_min_score

        passed_oos = (cand_exp > base_exp + 0.05) and (cand_dd <= base_dd + 0.5)
        new_status = "ACTIVE" if passed_oos else "REJECTED"

        with self.db.connect() as conn:
            if passed_oos:
                conn.execute(
                    "UPDATE strategy_versions SET status = 'PROPOSED' WHERE strategy_name = ? AND status = 'ACTIVE'",
                    (strategy_name,),
                )
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_versions (
                    version_id, strategy_name, version_tag, parent_version_tag,
                    parameters_json, hypothesis, train_sample_size, oos_sample_size,
                    baseline_expectancy_pct, oos_expectancy_pct, oos_max_drawdown_pct,
                    status, created_at_wib, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    strategy_name,
                    new_version_tag,
                    current_tag,
                    json.dumps(new_params),
                    hypothesis,
                    len(train_rows),
                    len(oos_rows),
                    base_exp,
                    cand_exp,
                    cand_dd,
                    new_status,
                    now_wib_iso(),
                    f"OOS Expectancy: {cand_exp:+.2f}% vs Baseline {base_exp:+.2f}%; OOS MaxDD: {cand_dd:.2f}% vs {base_dd:.2f}%",
                ),
            )

        return {
            "action": "PROMOTED_NEW_VERSION" if passed_oos else "REJECTED_ON_OOS",
            "previous_version": current_tag,
            "new_version": new_version_tag if passed_oos else current_tag,
            "candidate_version": new_version_tag,
            "hypothesis": hypothesis,
            "train_sample_size": len(train_rows),
            "oos_sample_size": len(oos_rows),
            "baseline_oos_expectancy_pct": base_exp,
            "candidate_oos_expectancy_pct": cand_exp,
            "baseline_oos_max_dd_pct": base_dd,
            "candidate_oos_max_dd_pct": cand_dd,
        }

    def rollback_strategy_version(self, strategy_name: str = config.DEFAULT_STRATEGY_NAME) -> dict[str, Any]:
        """Rolls back the active strategy version to its `parent_version_tag`."""
        active = self.db.get_active_strategy_version(strategy_name)
        parent_tag = active.get("parent_version_tag")
        if not parent_tag:
            return {
                "rolled_back": False,
                "reason": f"Versi aktif {active['version_tag']} adalah versi baseline awal (tidak memiliki parent version).",
                "active_version": active["version_tag"],
            }

        with self.db.connect() as conn:
            parent_row = conn.execute(
                "SELECT * FROM strategy_versions WHERE strategy_name = ? AND version_tag = ?",
                (strategy_name, parent_tag),
            ).fetchone()
            if not parent_row:
                return {
                    "rolled_back": False,
                    "reason": f"Parent version {parent_tag} tidak ditemukan.",
                    "active_version": active["version_tag"],
                }

            conn.execute(
                "UPDATE strategy_versions SET status = 'ROLLED_BACK' WHERE strategy_name = ? AND version_tag = ?",
                (strategy_name, active["version_tag"]),
            )
            conn.execute(
                "UPDATE strategy_versions SET status = 'ACTIVE' WHERE strategy_name = ? AND version_tag = ?",
                (strategy_name, parent_tag),
            )

        return {
            "rolled_back": True,
            "from_version": active["version_tag"],
            "active_version": parent_tag,
        }
