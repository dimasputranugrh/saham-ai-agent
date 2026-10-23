import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

from analyzer.technical import analyze_ticker_quant
from agents.ai_panel import run_5_ai_panel_consensus
from memory.database import MemoryDatabase


class TestTradingSafeguards(unittest.TestCase):
    """Pengujian filter proteksi modal: pisau jatuh, volatilitas liar, dan veto AI_6."""

    def test_downtrend_falling_knife_avoid(self):
        """Saham dalam downtrend (Close < EMA20 < EMA50) wajib diklasifikasikan sebagai AVOID."""
        dates = pd.date_range(end="2026-10-23", periods=60)
        df_daily = pd.DataFrame(
            {
                "Open": [5000 - i * 10 for i in range(60)],
                "High": [5050 - i * 10 for i in range(60)],
                "Low": [4950 - i * 10 for i in range(60)],
                "Close": [4980 - i * 10 for i in range(60)],
                "Volume": [1000000 for _ in range(60)],
            },
            index=dates,
        )

        mock_tk = MagicMock()
        mock_tk.history.side_effect = lambda period, interval, **kwargs: df_daily if interval == "1d" else None

        with patch("yfinance.Ticker", return_value=mock_tk):
            snap = analyze_ticker_quant("BBRI.JK")
            self.assertIsNotNone(snap)
            self.assertEqual(snap.setup_type, "DOWNTREND_FALLING_KNIFE_AVOID")
            self.assertIn("AVOID", snap.action_label)

    def test_extreme_volatility_or_spread_wait(self):
        """Saham dengan volatilitas ekstrem / spread liar wajib diklasifikasikan sebagai WAIT."""
        dates = pd.date_range(end="2026-10-23", periods=60)
        # Harga 50 (tick 1 -> spread 2.0% > 0.70%)
        df_daily = pd.DataFrame(
            {
                "Open": [50 for _ in range(60)],
                "High": [52 for _ in range(60)],
                "Low": [48 for _ in range(60)],
                "Close": [50 for _ in range(60)],
                "Volume": [1000000 for _ in range(60)],
            },
            index=dates,
        )

        mock_tk = MagicMock()
        mock_tk.history.side_effect = lambda period, interval, **kwargs: df_daily if interval == "1d" else None

        with patch("yfinance.Ticker", return_value=mock_tk):
            snap = analyze_ticker_quant("GOTO.JK")
            self.assertIsNotNone(snap)
            self.assertIn("WAIT", snap.action_label)
            self.assertEqual(snap.setup_type, "HIGH_SPREAD_OR_EXTREME_VOLATILITY_WAIT")

    def test_ai6_veto_defense(self):
        """Jika AI_6 (Akurasi 83%) menyarankan WAIT, konsensus BUY wajib di-veto menjadi WAIT."""
        db = MemoryDatabase("data/agent_memory.db")
        dates = pd.date_range(end="2026-10-23", periods=60)
        df_daily = pd.DataFrame(
            {
                "Open": [1000 + i * 10 for i in range(60)],
                "High": [1050 + i * 10 for i in range(60)],
                "Low": [980 + i * 10 for i in range(60)],
                "Close": [1040 + i * 10 for i in range(60)],
                "Volume": [5000000 for _ in range(60)],
            },
            index=dates,
        )
        mock_tk = MagicMock()
        mock_tk.history.side_effect = lambda period, interval, **kwargs: df_daily if interval == "1d" else None

        with patch("yfinance.Ticker", return_value=mock_tk):
            snap = analyze_ticker_quant("TLKM.JK")
            self.assertIsNotNone(snap)

        fake_votes = [
            {"slot_id": "AI_1", "ai_name": "AI-1", "vote_direction": "BUY", "confidence_pct": 75.0, "model_id": "m", "reasoning_summary": "ok"},
            {"slot_id": "AI_2", "ai_name": "AI-2", "vote_direction": "BUY", "confidence_pct": 70.0, "model_id": "m", "reasoning_summary": "ok"},
            {"slot_id": "AI_3", "ai_name": "AI-3", "vote_direction": "BUY", "confidence_pct": 70.0, "model_id": "m", "reasoning_summary": "ok"},
            {"slot_id": "AI_4", "ai_name": "AI-4", "vote_direction": "BUY", "confidence_pct": 70.0, "model_id": "m", "reasoning_summary": "ok"},
            {"slot_id": "AI_5", "ai_name": "AI-5", "vote_direction": "WAIT", "confidence_pct": 55.0, "model_id": "m", "reasoning_summary": "ok"},
            {"slot_id": "AI_6", "ai_name": "AI-6", "vote_direction": "WAIT", "confidence_pct": 65.0, "model_id": "m", "reasoning_summary": "jebakan volume"},
        ]

        with patch("agents.ai_panel._deterministic_slot_vote") as mock_vote:
            def side_effect(slot, *args, **kwargs):
                v = next(x for x in fake_votes if x["slot_id"] == slot)
                return {"vote_direction": v["vote_direction"], "confidence_pct": v["confidence_pct"], "reasoning_summary": v["reasoning_summary"]}
            mock_vote.side_effect = side_effect

            res = run_5_ai_panel_consensus(snap, {"trend": "NEUTRAL", "score": 50}, db=db, use_live_llm=False)
            self.assertEqual(res["final_decision"], "WAIT")
            self.assertIn("VETO DEFENSE", res["verdict_label"])
            # Verify debate presence
            self.assertIn("debate", res)
            self.assertGreaterEqual(len(res["debate"]["bull_arguments"]), 1)
            self.assertGreaterEqual(len(res["debate"]["bear_arguments"]), 1)

    def test_chaikin_money_flow_bank_avoid(self):
        """Saham Bank dengan CMF negatif masif wajib diblokir (INSTITUTIONAL_BANK_OUTFLOW_AVOID)."""
        dates = pd.date_range(end="2026-10-23", periods=60)
        # Close selalu di dekat Low -> CMF negatif kuat
        df_daily = pd.DataFrame(
            {
                "Open": [5000 for _ in range(60)],
                "High": [5100 for _ in range(60)],
                "Low": [4900 for _ in range(60)],
                "Close": [4910 for _ in range(60)],
                "Volume": [1000000 for _ in range(60)],
            },
            index=dates,
        )
        mock_tk = MagicMock()
        mock_tk.history.side_effect = lambda period, interval, **kwargs: df_daily if interval == "1d" else None

        with patch("yfinance.Ticker", return_value=mock_tk):
            snap = analyze_ticker_quant("BMRI.JK")
            self.assertIsNotNone(snap)
            self.assertEqual(snap.direction, "AVOID")
            self.assertIn("OUTFLOW", snap.setup_type)
            self.assertLess(snap.cmf_20, 0.0)

    def test_trailing_stop_loss_lock_profit(self):
        """Posisi yang sudah naik +2.0% lalu berbalik turun wajib mengunci profit via RESOLVED_WIN_TRAILING_SL."""
        import pytz
        import tempfile
        from pathlib import Path
        from datetime import datetime, timedelta
        from memory.evaluator import OutcomeEvaluator
        WIB = pytz.timezone("Asia/Jakarta")
        t0 = WIB.localize(datetime(2026, 10, 21, 9, 30, 0))

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_db = MemoryDatabase(Path(tmp_dir) / "test.db")
            evaluator = OutcomeEvaluator(tmp_db)

            snap_id = tmp_db.save_market_snapshot(
                {
                    "captured_at_wib": t0.isoformat(),
                    "ticker": "TLKM.JK",
                    "timeframe": "15m",
                    "last_bar_timestamp": t0.isoformat(),
                    "price": 2100.0,
                    "open_price": 2080.0,
                    "high_price": 2110.0,
                    "low_price": 2070.0,
                    "volume": 1000000,
                }
            )
            aid = tmp_db.save_analysis_prediction(
                {
                    "snapshot_id": snap_id,
                    "created_at_wib": t0.isoformat(),
                    "bar_cutoff_timestamp": t0.isoformat(),
                    "ticker": "TLKM.JK",
                    "timeframe": "15m",
                    "direction": "BUY",
                    "execution_mode": "PAPER",
                    "setup_type": "VWAP_BREAKOUT_UPTREND",
                    "entry_price": 2100.0,
                    "entry_low": 2080.0,
                    "entry_high": 2100.0,
                    "stop_loss": 2050.0,
                    "take_profit_1": 2180.0,
                    "take_profit_2": 2220.0,
                    "horizon_bars": 3,
                    "horizon_minutes": 45,
                    "evaluate_after_wib": (t0 + timedelta(minutes=45)).isoformat(),
                }
            )

            with tmp_db.connect() as conn:
                analysis_row = dict(conn.execute("SELECT * FROM analysis_history WHERE analysis_id = ?", (aid,)).fetchone())

            # Bar 1: Fills at 2100.
            # Bar 2: Rallies to High 2145 (gain +2.14% >= +1.5%), closes at 2140. Trailing SL locks to BEP + fee (2110).
            # Bar 3: Dips to Low 2105 (below trailing SL 2110, but above original SL 2050).
            times = [t0 + timedelta(minutes=15 * i) for i in range(1, 4)]
            bars = pd.DataFrame(
                [
                    (2100, 2110, 2095, 2105, 100000),  # Bar 1: fills at 2100
                    (2105, 2145, 2100, 2140, 200000),  # Bar 2: peak +2.14% -> activates trailing stop
                    (2140, 2140, 2105, 2110, 100000),  # Bar 3: drops to 2105 -> triggers trailing SL (locks profit!)
                ],
                index=pd.DatetimeIndex(times),
                columns=["Open", "High", "Low", "Close", "Volume"],
            )

            outcome = evaluator.evaluate_prediction_with_bars(analysis_row, bars)
            self.assertIsNotNone(outcome)
            self.assertEqual(outcome["evaluation_status"], "RESOLVED_WIN_TRAILING_SL")
            self.assertGreater(outcome["exit_price"], 2100.0)


if __name__ == "__main__":
    unittest.main()
