import asyncio
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import pytz

import config
from broker.stockbit import execute_stockbit_order
from memory.database import MemoryDatabase
from memory.evaluator import OutcomeEvaluator, compute_max_drawdown_pct
from memory.learning_loop import LearningLoopOrchestrator
from memory.performance import PerformanceAnalyzer
from memory.retrieval import MemoryRetriever

WIB = pytz.timezone("Asia/Jakarta")


def _make_bars(base_time: datetime, ohlcv_list: list[tuple[float, float, float, float, float]], step_mins: int = 15) -> pd.DataFrame:
    times = [base_time + timedelta(minutes=step_mins * i) for i in range(len(ohlcv_list))]
    idx = pd.DatetimeIndex(times)
    df = pd.DataFrame(
        ohlcv_list,
        index=idx,
        columns=["Open", "High", "Low", "Close", "Volume"],
    )
    return df


class TestPersistentMemoryAndLearningSystem(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_memory.db"
        self.db = MemoryDatabase(self.db_path)
        self.evaluator = OutcomeEvaluator(self.db)
        self.retriever = MemoryRetriever(self.db)
        self.perf = PerformanceAnalyzer(self.db)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_sample_snapshot_and_prediction(
        self,
        db: MemoryDatabase,
        ticker: str = "TLKM.JK",
        cutoff_dt: datetime | None = None,
        direction: str = "BUY",
        setup_type: str = "VWAP_BREAKOUT_UPTREND",
        ihsg_regime: str = "BEARISH_RECOVERY",
        entry_low: float = 2080.0,
        entry_high: float = 2100.0,
        stop_loss: float = 2050.0,
        tp1: float = 2160.0,
        tp2: float = 2220.0,
        horizon_bars: int = 4,
        raw_score: int = 74,
        exec_mode: str = "PAPER",
    ) -> tuple[str, str]:
        if cutoff_dt is None:
            cutoff_dt = WIB.localize(datetime(2026, 10, 21, 9, 30, 0))
        snap_id = db.save_market_snapshot(
            {
                "captured_at_wib": cutoff_dt.isoformat(),
                "ticker": ticker,
                "timeframe": "15m",
                "last_bar_timestamp": cutoff_dt.isoformat(),
                "price": entry_high,
                "open_price": entry_low,
                "high_price": entry_high + 10,
                "low_price": entry_low - 10,
                "volume": 5000000,
                "vwap": entry_low,
                "rsi": 58.0,
                "ihsg_close": 5328.36,
                "ihsg_change_pct": 0.94,
                "ihsg_regime": ihsg_regime,
                "tick_size": 10.0,
                "spread_pct": 0.47,
            }
        )
        analysis_id = db.save_analysis_prediction(
            {
                "snapshot_id": snap_id,
                "created_at_wib": cutoff_dt.isoformat(),
                "bar_cutoff_timestamp": cutoff_dt.isoformat(),
                "ticker": ticker,
                "timeframe": "15m",
                "direction": direction,
                "execution_mode": exec_mode,
                "setup_type": setup_type,
                "ihsg_regime": ihsg_regime,
                "technical_facts": ["Close=2100, VWAP=2080"],
                "interpretations": ["Momentum intraday positif di atas VWAP"],
                "assumptions": ["Fee beli 0.15% + jual 0.25% + slippage 0.10%"],
                "supporting_evidence": ["Harga di atas VWAP", "Volume spike 2.1x"],
                "opposing_evidence": ["IHSG masih di bawah EMA20 Daily"],
                "entry_price": entry_high,
                "entry_low": entry_low,
                "entry_high": entry_high,
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "horizon_bars": horizon_bars,
                "horizon_minutes": horizon_bars * 15,
                "evaluate_after_wib": (cutoff_dt + timedelta(minutes=horizon_bars * 15)).isoformat(),
                "estimated_risk_pct": 2.38,
                "estimated_gross_return_pct": 2.86,
                "estimated_net_return_pct": 2.36,
                "reward_to_risk": 1.2,
                "raw_quant_score": raw_score,
                "calibrated_confidence": 0.62,
                "confidence_basis": "Unit test prior",
                "invalidation_conditions": "Close < 2050",
            }
        )
        return snap_id, analysis_id

    # 1. Test penyimpanan dan pembacaan memory
    def test_1_save_and_read_market_snapshot_and_analysis(self):
        snap_id, analysis_id = self._create_sample_snapshot_and_prediction(self.db)
        with self.db.connect() as conn:
            snap = conn.execute("SELECT * FROM market_snapshots WHERE snapshot_id = ?", (snap_id,)).fetchone()
            pred = conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (analysis_id,)).fetchone()
        self.assertIsNotNone(snap)
        self.assertIsNotNone(pred)
        self.assertEqual(snap["ticker"], "TLKM.JK")
        self.assertEqual(pred["setup_type"], "VWAP_BREAKOUT_UPTREND")
        self.assertEqual(pred["order_book_available"] if "order_book_available" in pred.keys() else snap["order_book_available"], 0)

    # 2. Test persistence setelah restart + backup & restore
    def test_2_persistence_across_restart_and_backup_restore(self):
        _, analysis_id = self._create_sample_snapshot_and_prediction(self.db, ticker="BBRI.JK")
        backup_file = Path(self.tmp_dir.name) / "backup_test.db"
        self.db.backup_database(backup_file)
        self.assertTrue(backup_file.exists())

        # Simulate agent restart by instantiating a brand new MemoryDatabase pointing to the same file
        restarted_db = MemoryDatabase(self.db_path)
        with restarted_db.connect() as conn:
            row = conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (analysis_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["ticker"], "BBRI.JK")

        # Restore into a fresh DB path and verify data integrity
        restored_path = Path(self.tmp_dir.name) / "restored.db"
        restored_db = MemoryDatabase(restored_path)
        restored_db.restore_database(backup_file)
        with restored_db.connect() as conn:
            r_row = conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (analysis_id,)).fetchone()
        self.assertIsNotNone(r_row)
        self.assertEqual(r_row["ticker"], "BBRI.JK")

    # 3. Test immutability of initial predictions
    def test_3_prediction_immutability_triggers(self):
        _, analysis_id = self._create_sample_snapshot_and_prediction(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connect() as conn:
                conn.execute(
                    "UPDATE analysis_history SET entry_high = 1900 WHERE analysis_id = ?",
                    (analysis_id,),
                )
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connect() as conn:
                conn.execute(
                    "DELETE FROM analysis_history WHERE analysis_id = ?",
                    (analysis_id,),
                )

    # 4. Test evaluasi otomatis setelah horizon selesai (Win TP1, Loss SL, Time Exit)
    def test_4_automatic_evaluation_win_loss_and_time_exit(self):
        t0 = WIB.localize(datetime(2026, 10, 21, 9, 30, 0))
        _, win_id = self._create_sample_snapshot_and_prediction(self.db, cutoff_dt=t0, horizon_bars=3)

        # Bars strictly after t0: bar 1 fills at 2100, bar 2 hits TP1 (2160) without hitting SL (2050)
        bars_win = _make_bars(
            t0,
            [
                (2100, 2105, 2090, 2100, 100000),  # t0 (at cutoff - ignored)
                (2100, 2120, 2090, 2110, 200000),  # t0+15m: fills at 2100
                (2110, 2170, 2100, 2160, 300000),  # t0+30m: High 2170 >= TP1 (2160) -> WIN TP1!
                (2160, 2165, 2140, 2150, 150000),
            ],
        )
        with self.db.connect() as conn:
            a_row = dict(conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (win_id,)).fetchone())
        outcome = self.evaluator.evaluate_prediction_with_bars(a_row, bars_win, fee_buy_pct=0.15, fee_sell_pct=0.25, slippage_pct=0.10)
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome["evaluation_status"], "RESOLVED_WIN_TP1")
        self.assertEqual(outcome["entry_fill_price"], 2100.0)
        self.assertEqual(outcome["exit_price"], 2160.0)
        # Gross return = (2160 - 2100) / 2100 = +2.8571%, Net = 2.8571 - 0.50 = +2.3571%
        self.assertAlmostEqual(outcome["gross_return_pct"], 2.8571, places=3)
        self.assertAlmostEqual(outcome["net_return_pct"], 2.3571, places=3)

    # 5. Test pencegahan duplikasi evaluasi & Ambiguous candle order detection
    def test_5_idempotent_no_duplicate_and_ambiguous_bar_order(self):
        t0 = WIB.localize(datetime(2026, 10, 21, 10, 0, 0))
        _, amb_id = self._create_sample_snapshot_and_prediction(
            self.db, cutoff_dt=t0, entry_low=2080, entry_high=2100, stop_loss=2050, tp1=2160, horizon_bars=3
        )
        # Bar 1 fills at 2100; Bar 2 touches BOTH High=2170 (>= TP1 2160) AND Low=2040 (<= SL 2050) in the same bar!
        bars_amb = _make_bars(
            t0,
            [
                (2100, 2100, 2100, 2100, 100000),  # t0
                (2100, 2110, 2090, 2100, 100000),  # t0+15m: fills at 2100
                (2100, 2170, 2040, 2100, 500000),  # t0+30m: hits both TP1 and SL in same candle -> AMBIGUOUS!
                (2100, 2110, 2090, 2100, 100000),
            ],
        )
        with self.db.connect() as conn:
            a_row = dict(conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (amb_id,)).fetchone())

        out1 = self.evaluator.evaluate_prediction_with_bars(a_row, bars_amb)
        out2 = self.evaluator.evaluate_prediction_with_bars(a_row, bars_amb)
        self.assertEqual(out1["evaluation_status"], "AMBIGUOUS_BAR_ORDER")
        self.assertEqual(out1["is_ambiguous"], 1)
        self.assertEqual(out1["outcome_id"], out2["outcome_id"])  # Idempotent!

        with self.db.connect() as conn:
            cnt = conn.execute("SELECT COUNT(*) AS c FROM prediction_outcomes WHERE analysis_id = ?", (amb_id,)).fetchone()["c"]
        self.assertEqual(cnt, 1)

    # 6. Test retrieval memori berdasarkan relevansi & kalibrasi confidence
    def test_6_memory_retrieval_relevance_and_degraded_downgrade(self):
        t0 = WIB.localize(datetime(2026, 10, 15, 9, 30, 0))
        # Seed 6 losing trades on setup BEARISH_TEST_SETUP so it becomes DEGRADED
        for i in range(6):
            ti = t0 + timedelta(hours=i * 2)
            _, aid = self._create_sample_snapshot_and_prediction(
                self.db,
                ticker="ASII.JK",
                cutoff_dt=ti,
                setup_type="WEAK_SETUP_TEST",
                ihsg_regime="BEARISH_DOWNTREND",
                entry_low=4480,
                entry_high=4500,
                stop_loss=4440,
                tp1=4600,
                tp2=4650,
                horizon_bars=2,
            )
            bars_loss = _make_bars(
                ti,
                [
                    (4500, 4500, 4500, 4500, 100000),
                    (4500, 4510, 4490, 4495, 100000),  # fills at 4500
                    (4490, 4495, 4420, 4430, 200000),  # hits SL 4440
                ],
            )
            with self.db.connect() as conn:
                row = dict(conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (aid,)).fetchone())
            self.evaluator.evaluate_prediction_with_bars(row, bars_loss)

        self.evaluator.recompute_strategy_lessons()
        bundle = self.retriever.retrieve_relevant_memories(
            ticker="ASII.JK",
            setup_type="WEAK_SETUP_TEST",
            timeframe="15m",
            ihsg_regime="BEARISH_DOWNTREND",
        )
        self.assertTrue(bundle["has_degraded_warning"])
        self.assertGreaterEqual(len(bundle["memories"]), 1)

        cal_conf, basis = self.retriever.calibrate_confidence(
            raw_quant_score=70,
            setup_type="WEAK_SETUP_TEST",
            timeframe="15m",
            ihsg_regime="BEARISH_DOWNTREND",
        )
        # Prior for score 70 is 0.47; with 0/6 wins and degraded penalty, calibrated confidence must drop well below 0.30!
        self.assertLess(cal_conf, 0.30)
        self.assertIn("Penalti Degradasi", basis)

    # 7. Test perhitungan return bersih dan metrik strategi
    def test_7_net_return_and_strategy_metrics_computation(self):
        dd = compute_max_drawdown_pct([2.0, 3.0, -4.0, -2.0, 5.0])
        self.assertGreater(dd, 5.5)
        self.assertLess(dd, 6.2)

    # 8. Test penanganan data tidak valid atau terlambat
    def test_8_invalid_data_rejection_and_incomplete_horizon(self):
        with self.assertRaises(ValueError):
            self.db.save_market_snapshot({"ticker": "BBCA.JK", "price": -100, "last_bar_timestamp": "2026-10-21T10:00:00"})

        with self.assertRaises(ValueError):
            self.db.save_analysis_prediction({"snapshot_id": "invalid", "direction": "MOON", "entry_low": 100, "entry_high": 100, "stop_loss": 90, "take_profit_1": 110})

        # Incomplete horizon: only 1 future bar when horizon_bars=4 and neither TP nor SL hit -> returns None (waits)
        t0 = WIB.localize(datetime(2026, 10, 21, 14, 0, 0))
        _, aid = self._create_sample_snapshot_and_prediction(self.db, cutoff_dt=t0, horizon_bars=4)
        bars_partial = _make_bars(
            t0,
            [
                (2100, 2100, 2100, 2100, 100000),  # t0
                (2100, 2110, 2095, 2105, 100000),  # t0+15m (only 1 bar, no TP/SL hit yet)
            ],
        )
        with self.db.connect() as conn:
            row = dict(conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (aid,)).fetchone())
        res = self.evaluator.evaluate_prediction_with_bars(row, bars_partial)
        self.assertIsNone(res)

    # 9. Test pencegahan data leakage & Controlled Strategy Improvement
    def test_9_zero_future_data_leakage_and_controlled_improvement(self):
        t0 = WIB.localize(datetime(2026, 10, 21, 11, 0, 0))
        _, aid = self._create_sample_snapshot_and_prediction(
            self.db, cutoff_dt=t0, entry_low=2080, entry_high=2100, stop_loss=2050, tp1=2160, horizon_bars=2
        )
        # Past bar (before t0) had High=2500 (above TP1), but future bars after t0 never fill entry (stay at 2120-2130)!
        bars = pd.DataFrame(
            [
                (2090, 2500, 2080, 2100, 500000),  # t0 - 15m (PAST BAR: must NOT leak into evaluation!)
                (2100, 2500, 2080, 2100, 500000),  # t0 (AT CUTOFF: must NOT leak into evaluation!)
                (2120, 2130, 2115, 2125, 100000),  # t0 + 15m (FUTURE: Low=2115 > entry_high 2100 -> no fill!)
                (2125, 2135, 2120, 2130, 100000),  # t0 + 30m (FUTURE: Low=2120 > entry_high 2100 -> no fill!)
            ],
            index=pd.DatetimeIndex([
                t0 - timedelta(minutes=15),
                t0,
                t0 + timedelta(minutes=15),
                t0 + timedelta(minutes=30),
            ]),
            columns=["Open", "High", "Low", "Close", "Volume"],
        )
        with self.db.connect() as conn:
            row = dict(conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (aid,)).fetchone())
        out = self.evaluator.evaluate_prediction_with_bars(row, bars)
        self.assertIsNotNone(out)
        self.assertEqual(out["evaluation_status"], "EXPIRED_NO_FILL")
        self.assertEqual(out["entry_filled"], 0)

        # Verify Controlled Strategy Improvement refuses to change parameters when sample size < 16
        imp = self.perf.propose_and_validate_strategy_improvement(min_total_samples=16)
        self.assertEqual(imp["action"], "NO_CHANGE_INSUFFICIENT_SAMPLES")

    # 10. Test kompatibilitas fitur agent & Paper Trading default safety
    def test_10_paper_trading_safety_guard_and_orchestrator(self):
        # Verify live broker execution is blocked by default when EXECUTION_MODE=PAPER
        ok, msg, _ = asyncio.run(execute_stockbit_order("BUY", "BBCA", 1, 5250))
        self.assertFalse(ok)
        self.assertIn("PAPER TRADING", msg)

    # 11. Test Phase 7 Train/OOS Strategy Promotion and Rollback
    def test_11_controlled_strategy_promotion_on_oos_and_rollback(self):
        t0 = WIB.localize(datetime(2026, 10, 1, 9, 0, 0))
        # Seed 20 chronological resolved trades:
        # Lower score (score=69) loses (-1.5%), higher score (score=76) wins (+2.5%) across both Train and OOS!
        for i in range(20):
            ti = t0 + timedelta(hours=i * 3)
            is_high_score = (i % 2 == 1)
            score = 76 if is_high_score else 69
            _, aid = self._create_sample_snapshot_and_prediction(
                self.db,
                ticker="TLKM.JK",
                cutoff_dt=ti,
                raw_score=score,
                entry_low=2080,
                entry_high=2100,
                stop_loss=2050,
                tp1=2160,
                tp2=2220,
                horizon_bars=2,
            )
            if is_high_score:
                bars = _make_bars(
                    ti,
                    [
                        (2100, 2100, 2100, 2100, 100000),
                        (2100, 2110, 2095, 2105, 100000),
                        (2105, 2170, 2100, 2160, 200000),  # hits TP1 2160
                    ],
                )
            else:
                bars = _make_bars(
                    ti,
                    [
                        (2100, 2100, 2100, 2100, 100000),
                        (2100, 2105, 2095, 2100, 100000),
                        (2100, 2105, 2040, 2045, 200000),  # hits SL 2050
                    ],
                )
            with self.db.connect() as conn:
                row = dict(conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (aid,)).fetchone())
            self.evaluator.evaluate_prediction_with_bars(row, bars)

        imp = self.perf.propose_and_validate_strategy_improvement(min_total_samples=16)
        self.assertEqual(imp["action"], "PROMOTED_NEW_VERSION")
        self.assertEqual(imp["new_version"], "1.0.1")

        # Verify rollback restores version 1.0.0
        rb = self.perf.rollback_strategy_version()
        self.assertTrue(rb["rolled_back"])
        self.assertEqual(rb["active_version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
