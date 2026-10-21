import json
from typing import Any, Optional

import config
from memory.database import MemoryDatabase


class MemoryRetriever:
    """
    Retrieves relevant historical experience, past mistakes, degraded/validated setups,
    and computes empirically calibrated confidence scores before each stock analysis.
    """

    def __init__(self, db: Optional[MemoryDatabase] = None):
        self.db = db or MemoryDatabase()

    def calibrate_confidence(
        self,
        raw_quant_score: int,
        setup_type: str,
        timeframe: str,
        ihsg_regime: str,
        ticker: Optional[str] = None,
    ) -> tuple[float, str]:
        """
        Computes a Bayesian-shrunk calibrated confidence score in [0.05, 0.92]
        combining a conservative quantitative prior with empirical win rates
        from resolved predictions in `prediction_outcomes`.
        """
        prior_p = max(0.15, min(0.75, 0.35 + (raw_quant_score - 50) * 0.006))
        prior_weight = 10.0  # Pseudo-count M = 10

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT o.net_return_pct, o.is_ambiguous, a.ticker
                FROM analysis_history a
                INNER JOIN prediction_outcomes o ON a.analysis_id = o.analysis_id
                WHERE a.setup_type = ?
                  AND a.timeframe = ?
                  AND o.entry_filled = 1
                  AND o.is_ambiguous = 0
                  AND o.evaluation_status LIKE 'RESOLVED_%'
                ORDER BY o.evaluated_at_wib DESC
                LIMIT 100
                """,
                (setup_type, timeframe),
            ).fetchall()

            degraded_row = conn.execute(
                """
                SELECT validation_status, expectancy_net_pct, resolved_trades
                FROM strategy_lessons
                WHERE setup_type = ? AND timeframe = ? AND ihsg_regime = ?
                  AND validation_status = 'DEGRADED'
                LIMIT 1
                """,
                (setup_type, timeframe, ihsg_regime),
            ).fetchone()

        n_samples = len(rows)
        wins = sum(1 for r in rows if float(r["net_return_pct"]) > 0)
        emp_win_rate = (wins / n_samples) if n_samples > 0 else prior_p

        calibrated = (prior_weight * prior_p + wins) / (prior_weight + n_samples)

        penalty_note = ""
        if degraded_row is not None:
            calibrated *= 0.80
            penalty_note = f" [Penalti Degradasi Setup -20%: Expectancy={degraded_row['expectancy_net_pct']:+.2f}%]"

        calibrated = round(max(0.05, min(0.92, calibrated)), 3)
        basis = (
            f"Bayesian Calibrated={calibrated:.1%} (Prior={prior_p:.1%} dari Skor={raw_quant_score}, "
            f"Empiris={emp_win_rate:.1%} dari N={n_samples} transaksi selesai pada setup '{setup_type}'/{timeframe})"
            + penalty_note
        )
        return calibrated, basis

    def retrieve_relevant_memories(
        self,
        ticker: str,
        setup_type: str,
        timeframe: str,
        ihsg_regime: str,
        max_items: int = 6,
    ) -> dict[str, Any]:
        """
        Queries structured database tables for relevant lessons, same-ticker history,
        comparable setup/regime history, and past mistakes.
        Caps output to `max_items` to keep LLM context compact and high-signal.
        """
        norm_ticker = config.normalize_ticker(ticker)
        memory_items: list[dict[str, Any]] = []
        memory_ids_used: list[str] = []
        has_degraded_warning = False
        degraded_reason = ""

        with self.db.connect() as conn:
            # 1. Validated or Degraded Strategy Lessons for this ticker or ALL
            lesson_rows = conn.execute(
                """
                SELECT *
                FROM strategy_lessons
                WHERE setup_type = ?
                  AND timeframe = ?
                  AND (ticker_scope = ? OR ticker_scope = 'ALL')
                ORDER BY
                    CASE WHEN ticker_scope = ? THEN 0 ELSE 1 END,
                    CASE validation_status
                        WHEN 'DEGRADED' THEN 0
                        WHEN 'VALIDATED' THEN 1
                        ELSE 2
                    END,
                    resolved_trades DESC
                LIMIT 3
                """,
                (setup_type, timeframe, norm_ticker, norm_ticker),
            ).fetchall()

            for row in lesson_rows:
                d = dict(row)
                lid = str(d["lesson_id"])
                memory_ids_used.append(lid)
                if d["validation_status"] == "DEGRADED":
                    has_degraded_warning = True
                    degraded_reason = d["ai_interpretation_text"]
                memory_items.append(
                    {
                        "memory_id": lid,
                        "type": "STRATEGY_LESSON",
                        "source": "strategy_lessons",
                        "timestamp": d["evaluated_at_wib"],
                        "scope": f"{d['ticker_scope']} | {d['setup_type']} ({d['timeframe']}) | IHSG={d['ihsg_regime']}",
                        "sample_size": int(d["resolved_trades"]),
                        "validity_level": f"{d['validation_status']} ({d['uncertainty_level']})",
                        "measured_facts": json.loads(d["measured_facts_json"]),
                        "hypothesis": d["hypothesis_text"],
                        "lesson": d["ai_interpretation_text"],
                    }
                )

            # 2. Same-ticker recent resolved outcomes (especially mistakes & wins)
            ticker_rows = conn.execute(
                """
                SELECT
                    a.analysis_id, a.ticker, a.setup_type, a.timeframe, a.ihsg_regime,
                    a.direction, a.entry_high, a.stop_loss, a.take_profit_1,
                    o.evaluated_at_wib, o.evaluation_status, o.net_return_pct, o.resolution_notes
                FROM analysis_history a
                INNER JOIN prediction_outcomes o ON a.analysis_id = o.analysis_id
                WHERE a.ticker = ?
                ORDER BY o.evaluated_at_wib DESC
                LIMIT 3
                """,
                (norm_ticker,),
            ).fetchall()

            for row in ticker_rows:
                if len(memory_items) >= max_items:
                    break
                d = dict(row)
                aid = str(d["analysis_id"])
                if aid in memory_ids_used:
                    continue
                memory_ids_used.append(aid)
                is_mistake = d["evaluation_status"] in ("RESOLVED_LOSS_SL", "AMBIGUOUS_BAR_ORDER") or float(d["net_return_pct"]) < 0
                memory_items.append(
                    {
                        "memory_id": aid,
                        "type": "PAST_MISTAKE_ON_TICKER" if is_mistake else "PAST_OUTCOME_ON_TICKER",
                        "source": "analysis_history+prediction_outcomes",
                        "timestamp": d["evaluated_at_wib"],
                        "scope": f"{d['ticker']} | {d['setup_type']} ({d['timeframe']}) | IHSG={d['ihsg_regime']}",
                        "sample_size": 1,
                        "validity_level": "VERIFIED_CHRONOLOGICAL_OUTCOME",
                        "outcome_status": d["evaluation_status"],
                        "net_return_pct": round(float(d["net_return_pct"]), 2),
                        "lesson": d["resolution_notes"],
                    }
                )

            # 3. Past mistakes on the same setup + IHSG regime across other tickers
            if len(memory_items) < max_items:
                mistake_rows = conn.execute(
                    """
                    SELECT
                        a.analysis_id, a.ticker, a.setup_type, a.timeframe, a.ihsg_regime,
                        o.evaluated_at_wib, o.evaluation_status, o.net_return_pct, o.resolution_notes
                    FROM analysis_history a
                    INNER JOIN prediction_outcomes o ON a.analysis_id = o.analysis_id
                    WHERE a.setup_type = ?
                      AND a.ihsg_regime = ?
                      AND (o.evaluation_status = 'RESOLVED_LOSS_SL' OR o.net_return_pct < -0.5)
                    ORDER BY o.evaluated_at_wib DESC
                    LIMIT 2
                    """,
                    (setup_type, ihsg_regime),
                ).fetchall()

                for row in mistake_rows:
                    if len(memory_items) >= max_items:
                        break
                    d = dict(row)
                    aid = str(d["analysis_id"])
                    if aid in memory_ids_used:
                        continue
                    memory_ids_used.append(aid)
                    memory_items.append(
                        {
                            "memory_id": aid,
                            "type": "SETUP_REGIME_MISTAKE_WARNING",
                            "source": "analysis_history+prediction_outcomes",
                            "timestamp": d["evaluated_at_wib"],
                            "scope": f"{d['ticker']} | {d['setup_type']} ({d['timeframe']}) | IHSG={d['ihsg_regime']}",
                            "sample_size": 1,
                            "validity_level": "VERIFIED_LOSS_CASE",
                            "outcome_status": d["evaluation_status"],
                            "net_return_pct": round(float(d["net_return_pct"]), 2),
                            "lesson": f"Kesalahan historis pada setup serupa ({d['ticker']}): {d['resolution_notes']}",
                        }
                    )

        return {
            "ticker": norm_ticker,
            "setup_type": setup_type,
            "timeframe": timeframe,
            "ihsg_regime": ihsg_regime,
            "has_degraded_warning": has_degraded_warning,
            "degraded_reason": degraded_reason,
            "memory_ids_used": memory_ids_used,
            "memories": memory_items[:max_items],
        }
