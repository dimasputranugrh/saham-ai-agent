import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytz

import config
from agents.ai_panel import _get_slot_accuracy_weights
from memory.database import MemoryDatabase
from memory.evaluator import OutcomeEvaluator
from memory.retrieval import MemoryRetriever

WIB = pytz.timezone("Asia/Jakarta")


def _bars(base_time, rows):
    idx = pd.DatetimeIndex([base_time + timedelta(minutes=15 * i) for i in range(len(rows))])
    return pd.DataFrame(rows, index=idx, columns=["Open", "High", "Low", "Close", "Volume"])


class TestIntegrityAndLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = MemoryDatabase(root / "memory.db")
        self.evaluator = OutcomeEvaluator(self.db)
        self.retriever = MemoryRetriever(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _prediction(self, cutoff, ticker="TLKM.JK"):
        snap_id = self.db.save_market_snapshot({
            "captured_at_wib": cutoff.isoformat(),
            "ticker": ticker,
            "timeframe": "15m",
            "last_bar_timestamp": cutoff.isoformat(),
            "price": 2100.0,
            "open_price": 2080.0,
            "high_price": 2110.0,
            "low_price": 2070.0,
            "volume": 5_000_000,
            "vwap": 2080.0,
            "ihsg_regime": "BEARISH_RECOVERY",
            "tick_size": 10.0,
            "spread_pct": 0.47,
        })
        return self.db.save_analysis_prediction({
            "snapshot_id": snap_id,
            "created_at_wib": cutoff.isoformat(),
            "bar_cutoff_timestamp": cutoff.isoformat(),
            "ticker": ticker,
            "timeframe": "15m",
            "direction": "BUY",
            "execution_mode": "BACKTEST",
            "setup_type": "VWAP_BREAKOUT_UPTREND",
            "ihsg_regime": "BEARISH_RECOVERY",
            "entry_price": 2100.0,
            "entry_low": 2080.0,
            "entry_high": 2100.0,
            "stop_loss": 2050.0,
            "take_profit_1": 2160.0,
            "take_profit_2": 2220.0,
            "horizon_bars": 2,
            "horizon_minutes": 30,
            "evaluate_after_wib": (cutoff + timedelta(minutes=30)).isoformat(),
            "raw_quant_score": 74,
            "calibrated_confidence": 0.62,
        })

    def test_retrieval_as_of_excludes_future_outcomes(self):
        t1 = WIB.localize(datetime(2026, 10, 21, 9, 30))
        t2 = WIB.localize(datetime(2026, 10, 21, 11, 0))
        a1 = self._prediction(t1)
        a2 = self._prediction(t2)
        for aid, start in ((a1, t1), (a2, t2)):
            bars = _bars(start, [
                (2100, 2100, 2100, 2100, 100_000),
                (2100, 2110, 2095, 2105, 100_000),
                (2105, 2170, 2100, 2160, 200_000),
            ])
            with self.db.connect() as conn:
                row = dict(conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (aid,)).fetchone())
            self.evaluator.evaluate_prediction_with_bars(row, bars)

        as_of = (t1 + timedelta(minutes=60)).isoformat()
        bundle = self.retriever.retrieve_relevant_memories(
            ticker="TLKM.JK",
            setup_type="VWAP_BREAKOUT_UPTREND",
            timeframe="15m",
            ihsg_regime="BEARISH_RECOVERY",
            execution_mode="BACKTEST",
            as_of=as_of,
        )
        self.assertTrue(bundle["memories"])
        for item in bundle["memories"]:
            self.assertLessEqual(str(item["timestamp"]), as_of)

    def test_prediction_and_snapshot_dedup_are_idempotent(self):
        cutoff = WIB.localize(datetime(2026, 10, 21, 9, 30))
        a1 = self._prediction(cutoff)
        a2 = self._prediction(cutoff)
        self.assertEqual(a1, a2)

        snap1 = self.db.save_market_snapshot({
            "ticker": "BBCA.JK", "timeframe": "15m",
            "last_bar_timestamp": cutoff.isoformat(), "price": 5000.0,
        })
        snap2 = self.db.save_market_snapshot({
            "ticker": "BBCA.JK", "timeframe": "15m",
            "last_bar_timestamp": cutoff.isoformat(), "price": 5050.0,
        })
        self.assertEqual(snap1, snap2)

    def test_deterministic_fallback_votes_excluded_from_accuracy(self):
        cutoff = WIB.localize(datetime(2026, 10, 21, 9, 30))
        real_id = self._prediction(cutoff)
        fallback_id = self._prediction(cutoff + timedelta(hours=1))
        real_votes = [{
            "slot_id": f"AI_{i}", "ai_name": f"AI-{i}", "provider": "gemini",
            "model_id": "real-model", "vote_direction": "BUY",
            "confidence_pct": 70, "reasoning_summary": "test",
        } for i in range(1, 7)]
        self.db.save_ai_panel_votes(real_id, "TLKM.JK", real_votes)
        with self.db.connect() as conn:
            conn.execute("UPDATE ai_panel_votes SET outcome_status = 'WRONG_BUY_LOSS' WHERE analysis_id = ?", (real_id,))
        weighted = _get_slot_accuracy_weights(self.db)
        self.assertLess(weighted["AI_1"], 1.0)

        fallback_votes = [{
            "slot_id": f"AI_{i}", "ai_name": f"AI-{i}", "provider": "deterministic",
            "model_id": "deterministic-v1", "vote_direction": "BUY",
            "confidence_pct": 90, "reasoning_summary": "fallback",
        } for i in range(1, 7)]
        self.db.save_ai_panel_votes(fallback_id, "TLKM.JK", fallback_votes)
        with self.db.connect() as conn:
            conn.execute("UPDATE ai_panel_votes SET outcome_status = 'CORRECT_BUY_WIN' WHERE analysis_id = ?", (fallback_id,))
        self.assertEqual(_get_slot_accuracy_weights(self.db)["AI_1"], weighted["AI_1"])

    def test_apply_trade_updates_cash_avg_price_and_realized_pnl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(config, "PORTFOLIO_FILE", root / "portfolio.json"), \
                 patch.object(config, "TRADE_LEDGER_FILE", root / "ledger.json"), \
                 patch.object(config, "PAPER_INITIAL_CASH", 500_000.0):
                config.apply_trade("BUY", "BBCA", 1, 1000)
                config.apply_trade("BUY", "BBCA", 1, 1100)
                portfolio = json.loads((root / "portfolio.json").read_text())
                self.assertEqual(portfolio["BBCA.JK"]["lots"], 2)
                self.assertAlmostEqual(portfolio["BBCA.JK"]["buy_price"], 1050.0)

                result = config.apply_trade("SELL", "BBCA", 2, 1200)
                self.assertNotIn("BBCA.JK", result["portfolio"])
                self.assertGreater(result["ledger"]["realized_pnl"], 29_000)
                self.assertLess(result["ledger"]["realized_pnl"], 30_000)
                self.assertGreater(result["ledger"]["cash"], 500_000)


if __name__ == "__main__":
    unittest.main()
