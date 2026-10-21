import json
import math
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional
import pytz

import config

WIB = pytz.timezone(config.TIMEZONE)
VALID_DIRECTIONS = {"BUY", "SELL", "WAIT", "AVOID"}
VALID_EXECUTION_MODES = {"PAPER", "BACKTEST", "LIVE"}
VALID_EVAL_STATUSES = {
    "PENDING",
    "RESOLVED_WIN_TP1",
    "RESOLVED_WIN_TP2",
    "RESOLVED_LOSS_SL",
    "RESOLVED_TIME_EXIT",
    "AMBIGUOUS_BAR_ORDER",
    "EXPIRED_NO_FILL",
    "INSUFFICIENT_DATA",
    "SKIPPED_WAIT",
}


def now_wib_iso() -> str:
    return datetime.now(WIB).isoformat()


def _clean_float(val: Any, default: Optional[float] = 0.0) -> Optional[float]:
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


class MemoryDatabase:
    """
    Persistent SQLite database with WAL mode, schema migration tracking,
    immutability triggers on `analysis_history`, online backup/restore,
    and strict input validation.
    """

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path else config.MEMORY_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._apply_migrations()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _apply_migrations(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                """
            )
            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }

            if 1 not in applied:
                self._migration_v1(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (1, "initial_persistent_memory_and_learning_schema", now_wib_iso()),
                )

            if 2 not in applied:
                self._migration_v2_ai_panel(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (2, "multi_ai_panel_registry_and_votes", now_wib_iso()),
                )

            if 3 not in applied:
                self._migration_v3_news_and_conversation_memory(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (3, "sector_news_investigations_and_conversation_knowledge_log", now_wib_iso()),
                )

    def _migration_v1(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            -- 1. MARKET SNAPSHOTS
            CREATE TABLE IF NOT EXISTS market_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                captured_at_wib TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta',
                ticker TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                last_bar_timestamp TEXT NOT NULL,
                price REAL NOT NULL CHECK (price > 0),
                open_price REAL,
                high_price REAL,
                low_price REAL,
                volume REAL DEFAULT 0 CHECK (volume >= 0),
                vwap REAL,
                ema9 REAL,
                ema21 REAL,
                ema20 REAL,
                ema50 REAL,
                sma200 REAL,
                rsi REAL,
                macd_hist REAL,
                atr REAL,
                vol_ratio REAL,
                ihsg_close REAL,
                ihsg_change_pct REAL,
                ihsg_regime TEXT NOT NULL,
                sector TEXT NOT NULL,
                tick_size REAL NOT NULL CHECK (tick_size > 0),
                spread_pct REAL NOT NULL CHECK (spread_pct >= 0),
                order_book_available INTEGER NOT NULL DEFAULT 0,
                order_book_summary_json TEXT,
                data_source TEXT NOT NULL DEFAULT 'yfinance',
                data_updated_at TEXT NOT NULL,
                data_is_valid INTEGER NOT NULL DEFAULT 1,
                validation_notes TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_ticker_tf_time
                ON market_snapshots(ticker, timeframe, last_bar_timestamp);

            -- 2. ANALYSIS HISTORY (Immutable Initial Predictions)
            CREATE TABLE IF NOT EXISTS analysis_history (
                analysis_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL REFERENCES market_snapshots(snapshot_id),
                created_at_wib TEXT NOT NULL,
                bar_cutoff_timestamp TEXT NOT NULL,
                ticker TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                direction TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL', 'WAIT', 'AVOID')),
                execution_mode TEXT NOT NULL DEFAULT 'PAPER' CHECK (execution_mode IN ('PAPER', 'BACKTEST', 'LIVE')),
                strategy_name TEXT NOT NULL,
                setup_type TEXT NOT NULL,
                ihsg_regime TEXT NOT NULL,
                sector TEXT NOT NULL,
                technical_facts_json TEXT NOT NULL,
                interpretations_json TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                supporting_evidence_json TEXT NOT NULL,
                opposing_evidence_json TEXT NOT NULL,
                fundamental_news_context TEXT,
                entry_price REAL NOT NULL CHECK (entry_price > 0),
                entry_low REAL NOT NULL CHECK (entry_low > 0),
                entry_high REAL NOT NULL CHECK (entry_high >= entry_low),
                stop_loss REAL NOT NULL CHECK (stop_loss > 0),
                take_profit_1 REAL NOT NULL CHECK (take_profit_1 > 0),
                take_profit_2 REAL NOT NULL CHECK (take_profit_2 >= take_profit_1),
                horizon_bars INTEGER NOT NULL CHECK (horizon_bars > 0),
                horizon_minutes INTEGER NOT NULL CHECK (horizon_minutes > 0),
                evaluate_after_wib TEXT NOT NULL,
                estimated_risk_pct REAL NOT NULL,
                estimated_gross_return_pct REAL NOT NULL,
                estimated_net_return_pct REAL NOT NULL,
                reward_to_risk REAL NOT NULL,
                raw_quant_score INTEGER NOT NULL CHECK (raw_quant_score BETWEEN 0 AND 100),
                calibrated_confidence REAL NOT NULL CHECK (calibrated_confidence BETWEEN 0.0 AND 1.0),
                confidence_basis TEXT NOT NULL,
                invalidation_conditions TEXT NOT NULL,
                model_version TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                memory_ids_used_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_analysis_ticker_setup
                ON analysis_history(ticker, setup_type, timeframe, execution_mode);
            CREATE INDEX IF NOT EXISTS idx_analysis_eval_due
                ON analysis_history(evaluate_after_wib);

            -- IMMUTABILITY TRIGGERS ON analysis_history
            CREATE TRIGGER IF NOT EXISTS trg_analysis_history_immutable_update
            BEFORE UPDATE ON analysis_history
            BEGIN
                SELECT RAISE(ABORT, 'Immutable Audit Trail Violation: analysis_history records cannot be modified after creation.');
            END;

            CREATE TRIGGER IF NOT EXISTS trg_analysis_history_immutable_delete
            BEFORE DELETE ON analysis_history
            BEGIN
                SELECT RAISE(ABORT, 'Immutable Audit Trail Violation: analysis_history records cannot be deleted.');
            END;

            -- 3. PREDICTION OUTCOMES
            CREATE TABLE IF NOT EXISTS prediction_outcomes (
                outcome_id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL UNIQUE REFERENCES analysis_history(analysis_id),
                evaluated_at_wib TEXT NOT NULL,
                evaluation_status TEXT NOT NULL,
                entry_filled INTEGER NOT NULL DEFAULT 0,
                entry_fill_price REAL,
                entry_fill_timestamp TEXT,
                exit_price REAL,
                exit_timestamp TEXT,
                actual_high_in_horizon REAL,
                actual_low_in_horizon REAL,
                actual_close_at_horizon REAL,
                bars_evaluated INTEGER NOT NULL DEFAULT 0,
                gross_return_pct REAL NOT NULL DEFAULT 0.0,
                net_return_pct REAL NOT NULL DEFAULT 0.0,
                fee_buy_pct REAL NOT NULL,
                fee_sell_pct REAL NOT NULL,
                slippage_pct REAL NOT NULL,
                duration_minutes REAL NOT NULL DEFAULT 0.0,
                is_ambiguous INTEGER NOT NULL DEFAULT 0,
                resolution_notes TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_outcomes_status
                ON prediction_outcomes(evaluation_status);

            -- 4. STRATEGY LESSONS
            CREATE TABLE IF NOT EXISTS strategy_lessons (
                lesson_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                setup_type TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                ihsg_regime TEXT NOT NULL,
                ticker_scope TEXT NOT NULL DEFAULT 'ALL',
                execution_mode TEXT NOT NULL DEFAULT 'PAPER',
                sample_size INTEGER NOT NULL DEFAULT 0,
                resolved_trades INTEGER NOT NULL DEFAULT 0,
                ambiguous_trades INTEGER NOT NULL DEFAULT 0,
                win_count INTEGER NOT NULL DEFAULT 0,
                loss_count INTEGER NOT NULL DEFAULT 0,
                win_rate REAL NOT NULL DEFAULT 0.0,
                avg_win_net_pct REAL NOT NULL DEFAULT 0.0,
                avg_loss_net_pct REAL NOT NULL DEFAULT 0.0,
                expectancy_net_pct REAL NOT NULL DEFAULT 0.0,
                profit_factor REAL NOT NULL DEFAULT 0.0,
                max_drawdown_pct REAL NOT NULL DEFAULT 0.0,
                cumulative_net_return_pct REAL NOT NULL DEFAULT 0.0,
                uncertainty_level TEXT NOT NULL,
                measured_facts_json TEXT NOT NULL,
                hypothesis_text TEXT NOT NULL,
                ai_interpretation_text TEXT NOT NULL,
                validation_status TEXT NOT NULL CHECK (validation_status IN ('CANDIDATE', 'VALIDATED', 'DEGRADED', 'REJECTED')),
                evaluated_at_wib TEXT NOT NULL,
                UNIQUE(strategy_name, strategy_version, setup_type, timeframe, ihsg_regime, ticker_scope, execution_mode)
            );

            -- 5. STRATEGY VERSIONS (Controlled Improvement & Rollback)
            CREATE TABLE IF NOT EXISTS strategy_versions (
                version_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                version_tag TEXT NOT NULL,
                parent_version_tag TEXT,
                parameters_json TEXT NOT NULL,
                hypothesis TEXT NOT NULL,
                train_sample_size INTEGER NOT NULL DEFAULT 0,
                oos_sample_size INTEGER NOT NULL DEFAULT 0,
                baseline_expectancy_pct REAL NOT NULL DEFAULT 0.0,
                oos_expectancy_pct REAL NOT NULL DEFAULT 0.0,
                oos_max_drawdown_pct REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'PROPOSED', 'ROLLED_BACK', 'REJECTED')),
                created_at_wib TEXT NOT NULL,
                notes TEXT,
                UNIQUE(strategy_name, version_tag)
            );
            """
        )

        # Seed default baseline strategy version v1.0.0 if not exists
        default_params = {
            "min_intraday_score": 68,
            "min_volume_ratio": 1.3,
            "max_spread_pct": 0.65,
            "sl_atr_multiplier": 0.9,
            "tp1_rr_multiplier": 1.6,
            "tp2_rr_multiplier": 2.8,
            "require_above_vwap_for_strong_buy": True,
        }
        conn.execute(
            """
            INSERT OR IGNORE INTO strategy_versions (
                version_id, strategy_name, version_tag, parent_version_tag,
                parameters_json, hypothesis, train_sample_size, oos_sample_size,
                baseline_expectancy_pct, oos_expectancy_pct, oos_max_drawdown_pct,
                status, created_at_wib, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                config.DEFAULT_STRATEGY_NAME,
                config.DEFAULT_STRATEGY_VERSION,
                None,
                json.dumps(default_params),
                "Baseline hybrid VWAP + EMA + ATR strategy for IDX stocks.",
                0,
                0,
                0.0,
                0.0,
                0.0,
                "ACTIVE",
                now_wib_iso(),
                "Initial baseline strategy version.",
            ),
        )

    def save_market_snapshot(self, data: dict[str, Any]) -> str:
        """Validates and stores a market snapshot. Returns `snapshot_id`."""
        price = _clean_float(data.get("price"), None)
        if price is None or price <= 0:
            raise ValueError(f"Invalid snapshot price: {data.get('price')}")

        ticker = str(data.get("ticker", "")).strip().upper()
        if not ticker:
            raise ValueError("Ticker is required for market snapshot.")

        timeframe = str(data.get("timeframe", "15m")).strip()
        last_bar_ts = str(data.get("last_bar_timestamp", "")).strip()
        if not last_bar_ts:
            raise ValueError("last_bar_timestamp is required for market snapshot.")

        tick_size = _clean_float(data.get("tick_size"), 1.0)
        if not tick_size or tick_size <= 0:
            tick_size = 1.0
        spread_pct = _clean_float(data.get("spread_pct"), round((tick_size / price) * 100.0, 4))

        snapshot_id = str(data.get("snapshot_id") or uuid.uuid4())
        captured_at = str(data.get("captured_at_wib") or now_wib_iso())
        sector = str(data.get("sector") or config.SECTOR_MAP.get(ticker, "GENERAL_IDX"))
        ihsg_regime = str(data.get("ihsg_regime") or "NEUTRAL")
        data_is_valid = 1 if data.get("data_is_valid", True) else 0

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO market_snapshots (
                    snapshot_id, captured_at_wib, timezone, ticker, timeframe,
                    last_bar_timestamp, price, open_price, high_price, low_price,
                    volume, vwap, ema9, ema21, ema20, ema50, sma200, rsi,
                    macd_hist, atr, vol_ratio, ihsg_close, ihsg_change_pct,
                    ihsg_regime, sector, tick_size, spread_pct,
                    order_book_available, order_book_summary_json,
                    data_source, data_updated_at, data_is_valid, validation_notes
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    snapshot_id,
                    captured_at,
                    str(data.get("timezone", config.TIMEZONE)),
                    ticker,
                    timeframe,
                    last_bar_ts,
                    price,
                    _clean_float(data.get("open_price"), price),
                    _clean_float(data.get("high_price"), price),
                    _clean_float(data.get("low_price"), price),
                    max(0.0, _clean_float(data.get("volume"), 0.0) or 0.0),
                    _clean_float(data.get("vwap"), price),
                    _clean_float(data.get("ema9"), price),
                    _clean_float(data.get("ema21"), price),
                    _clean_float(data.get("ema20"), price),
                    _clean_float(data.get("ema50"), price),
                    _clean_float(data.get("sma200"), price),
                    _clean_float(data.get("rsi"), 50.0),
                    _clean_float(data.get("macd_hist"), 0.0),
                    _clean_float(data.get("atr"), price * 0.02),
                    _clean_float(data.get("vol_ratio"), 1.0),
                    _clean_float(data.get("ihsg_close"), None),
                    _clean_float(data.get("ihsg_change_pct"), None),
                    ihsg_regime,
                    sector,
                    tick_size,
                    max(0.0, spread_pct or 0.0),
                    1 if data.get("order_book_available") else 0,
                    json.dumps(data.get("order_book_summary") or {}),
                    str(data.get("data_source", "yfinance")),
                    str(data.get("data_updated_at") or captured_at),
                    data_is_valid,
                    str(data.get("validation_notes", "Valid OHLCV snapshot")),
                ),
            )
        return snapshot_id

    def save_analysis_prediction(self, record: dict[str, Any]) -> str:
        """
        Validates and saves an immutable initial prediction in `analysis_history`.
        Once saved, SQLite triggers prevent any modification or deletion.
        """
        direction = str(record.get("direction", "WAIT")).strip().upper()
        if direction not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid prediction direction: {direction}")

        exec_mode = str(record.get("execution_mode", config.EXECUTION_MODE)).strip().upper()
        if exec_mode not in VALID_EXECUTION_MODES:
            raise ValueError(f"Invalid execution mode: {exec_mode}")

        entry_low = _clean_float(record.get("entry_low"), None)
        entry_high = _clean_float(record.get("entry_high"), None)
        entry_price = _clean_float(record.get("entry_price"), entry_high)
        stop_loss = _clean_float(record.get("stop_loss"), None)
        tp1 = _clean_float(record.get("take_profit_1"), None)
        tp2 = _clean_float(record.get("take_profit_2"), tp1)

        if not all(x is not None and x > 0 for x in [entry_low, entry_high, entry_price, stop_loss, tp1, tp2]):
            raise ValueError("All price levels (entry, stop_loss, take_profit) must be positive numbers.")
        if entry_high < entry_low:
            entry_high = entry_low
        if tp2 < tp1:
            tp2 = tp1

        conf = _clean_float(record.get("calibrated_confidence"), 0.5)
        if conf is None or not (0.0 <= conf <= 1.0):
            raise ValueError(f"calibrated_confidence must be in [0.0, 1.0], got {conf}")

        analysis_id = str(record.get("analysis_id") or uuid.uuid4())
        created_at = str(record.get("created_at_wib") or now_wib_iso())
        bar_cutoff = str(record.get("bar_cutoff_timestamp") or created_at)
        ticker = str(record.get("ticker", "")).strip().upper()

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO analysis_history (
                    analysis_id, snapshot_id, created_at_wib, bar_cutoff_timestamp,
                    ticker, timeframe, direction, execution_mode,
                    strategy_name, setup_type, ihsg_regime, sector,
                    technical_facts_json, interpretations_json, assumptions_json,
                    supporting_evidence_json, opposing_evidence_json,
                    fundamental_news_context,
                    entry_price, entry_low, entry_high, stop_loss, take_profit_1, take_profit_2,
                    horizon_bars, horizon_minutes, evaluate_after_wib,
                    estimated_risk_pct, estimated_gross_return_pct, estimated_net_return_pct,
                    reward_to_risk, raw_quant_score, calibrated_confidence,
                    confidence_basis, invalidation_conditions,
                    model_version, prompt_version, strategy_version, memory_ids_used_json
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    analysis_id,
                    str(record["snapshot_id"]),
                    created_at,
                    bar_cutoff,
                    ticker,
                    str(record.get("timeframe", "15m")),
                    direction,
                    exec_mode,
                    str(record.get("strategy_name", config.DEFAULT_STRATEGY_NAME)),
                    str(record.get("setup_type", "GENERAL_SETUP")),
                    str(record.get("ihsg_regime", "NEUTRAL")),
                    str(record.get("sector") or config.SECTOR_MAP.get(ticker, "GENERAL_IDX")),
                    json.dumps(record.get("technical_facts") or [], ensure_ascii=False),
                    json.dumps(record.get("interpretations") or [], ensure_ascii=False),
                    json.dumps(record.get("assumptions") or [], ensure_ascii=False),
                    json.dumps(record.get("supporting_evidence") or [], ensure_ascii=False),
                    json.dumps(record.get("opposing_evidence") or [], ensure_ascii=False),
                    str(record.get("fundamental_news_context", "")),
                    entry_price,
                    entry_low,
                    entry_high,
                    stop_loss,
                    tp1,
                    tp2,
                    int(record.get("horizon_bars", 16)),
                    int(record.get("horizon_minutes", 240)),
                    str(record.get("evaluate_after_wib") or created_at),
                    _clean_float(record.get("estimated_risk_pct"), 0.0),
                    _clean_float(record.get("estimated_gross_return_pct"), 0.0),
                    _clean_float(record.get("estimated_net_return_pct"), 0.0),
                    _clean_float(record.get("reward_to_risk"), 1.0),
                    int(max(0, min(100, int(record.get("raw_quant_score", 50))))),
                    conf,
                    str(record.get("confidence_basis", "Empirical + Quantitative Score Calibration")),
                    str(record.get("invalidation_conditions", "Price closes below Stop Loss or VWAP.")),
                    str(record.get("model_version", config.GEMINI_MODEL)),
                    str(record.get("prompt_version", config.AGENT_PROMPT_VERSION)),
                    str(record.get("strategy_version", self.get_active_strategy_version(str(record.get("strategy_name", config.DEFAULT_STRATEGY_NAME)))["version_tag"])),
                    json.dumps(record.get("memory_ids_used") or []),
                ),
            )
        return analysis_id

    def get_active_strategy_version(self, strategy_name: str = config.DEFAULT_STRATEGY_NAME) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM strategy_versions
                WHERE strategy_name = ? AND status = 'ACTIVE'
                ORDER BY created_at_wib DESC LIMIT 1
                """,
                (strategy_name,),
            ).fetchone()
            if row:
                d = dict(row)
                d["parameters"] = json.loads(d["parameters_json"])
                return d
        return {
            "version_tag": config.DEFAULT_STRATEGY_VERSION,
            "parameters": {
                "min_intraday_score": config.MIN_INTRADAY_ALERT_SCORE,
                "min_volume_ratio": 1.3,
                "max_spread_pct": 0.65,
                "sl_atr_multiplier": 0.9,
                "tp1_rr_multiplier": 1.6,
                "tp2_rr_multiplier": 2.8,
                "require_above_vwap_for_strong_buy": True,
            },
        }

    def backup_database(self, backup_path: Optional[Path | str] = None) -> Path:
        """Creates a transactionally consistent online backup of the SQLite database."""
        config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        if backup_path is None:
            stamp = datetime.now(WIB).strftime("%Y%m%d_%H%M%S")
            target = config.BACKUP_DIR / f"agent_memory_backup_{stamp}.db"
        else:
            target = Path(backup_path)
            target.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(str(self.db_path)) as src_conn:
            with sqlite3.connect(str(target)) as dst_conn:
                src_conn.backup(dst_conn)
        return target

    def restore_database(self, backup_path: Path | str) -> None:
        """Restores the SQLite database from a backup file safely."""
        src = Path(backup_path)
        if not src.exists():
            raise FileNotFoundError(f"Backup file not found: {src}")
        with sqlite3.connect(str(src)) as src_conn:
            with sqlite3.connect(str(self.db_path)) as dst_conn:
                src_conn.backup(dst_conn)

    def _migration_v2_ai_panel(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            -- 6. AI PANEL REGISTRY (5 Configurable Free AI Slots)
            CREATE TABLE IF NOT EXISTS ai_panel_registry (
                slot_id TEXT PRIMARY KEY,
                ai_name TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'gemini',
                model_id TEXT NOT NULL,
                role_focus TEXT NOT NULL,
                temperature REAL NOT NULL DEFAULT 0.2,
                is_active INTEGER NOT NULL DEFAULT 1,
                updated_at_wib TEXT NOT NULL
            );

            -- 7. AI PANEL VOTES (Individual AI Predictions & Outcome Grading)
            CREATE TABLE IF NOT EXISTS ai_panel_votes (
                vote_id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL,
                created_at_wib TEXT NOT NULL,
                ticker TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                ai_name TEXT NOT NULL,
                provider TEXT NOT NULL,
                model_id TEXT NOT NULL,
                vote_direction TEXT NOT NULL CHECK (vote_direction IN ('BUY', 'WAIT')),
                confidence_pct REAL NOT NULL CHECK (confidence_pct >= 0.0 AND confidence_pct <= 100.0),
                reasoning_summary TEXT NOT NULL,
                outcome_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
                    outcome_status IN (
                        'PENDING',
                        'CORRECT_BUY_WIN',
                        'WRONG_BUY_LOSS',
                        'CORRECT_WAIT_SAVED',
                        'MISSED_WAIT_OPPORTUNITY',
                        'NEUTRAL'
                    )
                ),
                outcome_net_return_pct REAL DEFAULT 0.0,
                evaluated_at_wib TEXT,
                UNIQUE(analysis_id, slot_id),
                FOREIGN KEY (analysis_id) REFERENCES analysis_history(analysis_id)
            );

            CREATE INDEX IF NOT EXISTS idx_ai_votes_analysis
                ON ai_panel_votes(analysis_id);
            CREATE INDEX IF NOT EXISTS idx_ai_votes_slot_model
                ON ai_panel_votes(slot_id, model_id, outcome_status, created_at_wib DESC);
            """
        )
        self._seed_default_ai_panel(conn)

    def _seed_default_ai_panel(self, conn: sqlite3.Connection) -> None:
        now_iso = now_wib_iso()
        default_slots = [
            (
                "AI_1",
                "AI-1 (Momentum Scalper)",
                "gemini",
                "gemini-3.6-flash",
                "Fokus pada ledakan volume intraday, posisi harga di atas VWAP, dan momentum kenaikan cepat.",
                0.2,
            ),
            (
                "AI_2",
                "AI-2 (OpenAI 120B Risk Auditor)",
                "groq",
                "openai/gpt-oss-120b",
                "Fokus mencari bahaya jebakan pucuk (bull trap), spread mahal, kelemahan IHSG, dan alasan menahan diri.",
                0.15,
            ),
            (
                "AI_3",
                "AI-3 (NVIDIA Nemotron 550B Bandar)",
                "openrouter",
                "nvidia/nemotron-3-ultra-550b-a55b:free",
                "Fokus membaca akumulasi bandar, kekuatan aliran dana (volume spike), dan struktur candle.",
                0.25,
            ),
            (
                "AI_4",
                "AI-4 (Alibaba Qwen-3.8 Trend)",
                "groq",
                "qwen/qwen3.8-27b",
                "Fokus pada keselarasan tren harian (EMA20/EMA50), jarak ke Support/Resistance, dan rasio Risk/Reward.",
                0.2,
            ),
            (
                "AI_5",
                "AI-5 (Quant Bayesian Memory)",
                "quant",
                "quant-bayesian-v1",
                "Murni menghitung probabilitas matematika, biaya transaksi 0.40%, dan rekam jejak database memori historis.",
                0.0,
            ),
        ]
        for slot_id, ai_name, provider, model_id, role_focus, temp in default_slots:
            conn.execute(
                """
                INSERT OR IGNORE INTO ai_panel_registry (
                    slot_id, ai_name, provider, model_id, role_focus, temperature, is_active, updated_at_wib
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (slot_id, ai_name, provider, model_id, role_focus, temp, now_iso),
            )

    def get_ai_panel_registry(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ai_panel_registry WHERE is_active = 1 ORDER BY slot_id ASC"
            ).fetchall()
            if not rows:
                self._seed_default_ai_panel(conn)
                rows = conn.execute(
                    "SELECT * FROM ai_panel_registry WHERE is_active = 1 ORDER BY slot_id ASC"
                ).fetchall()
            return [dict(r) for r in rows]

    def reset_ai_panel_registry(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            conn.execute("DELETE FROM ai_panel_registry")
            self._seed_default_ai_panel(conn)
        return self.get_ai_panel_registry()

    def update_ai_panel_slot(
        self,
        slot_id: str,
        new_model_spec: str,
        custom_name: Optional[str] = None,
    ) -> dict[str, Any]:
        slot = slot_id.strip().upper()
        if not slot.startswith("AI_"):
            slot = f"AI_{slot}"
        if slot not in {"AI_1", "AI_2", "AI_3", "AI_4", "AI_5"}:
            raise ValueError(f"Slot tidak valid: {slot_id}. Pilih AI_1 sampai AI_5.")

        spec = new_model_spec.strip()
        if ":" in spec:
            provider, model_id = spec.split(":", 1)
            provider = provider.strip().lower()
            model_id = model_id.strip()
        elif spec.lower().startswith("quant"):
            provider = "quant"
            model_id = spec
        else:
            provider = "gemini"
            model_id = spec

        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM ai_panel_registry WHERE slot_id = ?", (slot,)
            ).fetchone()
            old_name = existing["ai_name"] if existing else slot
            new_name = custom_name or f"{slot.replace('_', '-')} ({model_id[:22]})"
            conn.execute(
                """
                UPDATE ai_panel_registry
                SET ai_name = ?, provider = ?, model_id = ?, updated_at_wib = ?
                WHERE slot_id = ?
                """,
                (new_name, provider, model_id, now_wib_iso(), slot),
            )
            row = conn.execute(
                "SELECT * FROM ai_panel_registry WHERE slot_id = ?", (slot,)
            ).fetchone()
            return dict(row) if row else {}

    def save_ai_panel_votes(self, analysis_id: str, ticker: str, votes: list[dict[str, Any]]) -> None:
        now_iso = now_wib_iso()
        norm_ticker = config.normalize_ticker(ticker)
        with self.connect() as conn:
            for v in votes:
                vote_dir = str(v.get("vote_direction", "WAIT")).upper()
                if vote_dir not in ("BUY", "WAIT"):
                    vote_dir = "WAIT"
                conf = max(0.0, min(100.0, _clean_float(v.get("confidence_pct"), 50.0) or 50.0))
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ai_panel_votes (
                        vote_id, analysis_id, created_at_wib, ticker,
                        slot_id, ai_name, provider, model_id,
                        vote_direction, confidence_pct, reasoning_summary,
                        outcome_status, outcome_net_return_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 0.0)
                    """,
                    (
                        str(uuid.uuid4()),
                        analysis_id,
                        now_iso,
                        norm_ticker,
                        str(v.get("slot_id", "AI_1")),
                        str(v.get("ai_name", "AI Panelist")),
                        str(v.get("provider", "gemini")),
                        str(v.get("model_id", config.GEMINI_MODEL)),
                        vote_dir,
                        conf,
                        str(v.get("reasoning_summary", "")),
                    ),
                )

    def grade_ai_panel_votes_for_outcome(
        self,
        analysis_id: str,
        evaluation_status: str,
        net_return_pct: float,
        actual_high: Optional[float],
        actual_low: Optional[float],
        entry_high: float,
        take_profit_1: float,
        stop_loss: float,
    ) -> int:
        """
        Grades each of the 5 AIs' votes once the real market outcome is known:
        - If price reached TP1 or net_return_pct >= 0.40%:
          * BUY vote -> CORRECT_BUY_WIN
          * WAIT vote -> MISSED_WAIT_OPPORTUNITY
        - If price hit Stop Loss or net_return_pct <= -0.40% or actual_low <= stop_loss:
          * BUY vote -> WRONG_BUY_LOSS
          * WAIT vote -> CORRECT_WAIT_SAVED
        - Otherwise -> NEUTRAL
        """
        with self.connect() as conn:
            votes = conn.execute(
                "SELECT * FROM ai_panel_votes WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchall()
            if not votes:
                return 0

            hit_tp = (
                evaluation_status in ("RESOLVED_WIN_TP1", "RESOLVED_WIN_TP2")
                or net_return_pct >= 0.40
                or (actual_high is not None and actual_high >= take_profit_1 and (actual_low is None or actual_low > stop_loss))
            )
            hit_sl = (
                evaluation_status == "RESOLVED_LOSS_SL"
                or net_return_pct <= -0.40
                or (actual_low is not None and actual_low <= stop_loss)
            )

            now_iso = now_wib_iso()
            updated = 0
            for v in votes:
                v_dir = str(v["vote_direction"]).upper()
                if hit_tp and not hit_sl:
                    status = "CORRECT_BUY_WIN" if v_dir == "BUY" else "MISSED_WAIT_OPPORTUNITY"
                elif hit_sl and not hit_tp:
                    status = "WRONG_BUY_LOSS" if v_dir == "BUY" else "CORRECT_WAIT_SAVED"
                else:
                    if net_return_pct > 0.15:
                        status = "CORRECT_BUY_WIN" if v_dir == "BUY" else "NEUTRAL"
                    elif net_return_pct < -0.15:
                        status = "WRONG_BUY_LOSS" if v_dir == "BUY" else "CORRECT_WAIT_SAVED"
                    else:
                        status = "NEUTRAL"

                conn.execute(
                    """
                    UPDATE ai_panel_votes
                    SET outcome_status = ?, outcome_net_return_pct = ?, evaluated_at_wib = ?
                    WHERE vote_id = ?
                    """,
                    (status, round(net_return_pct, 4), now_iso, v["vote_id"]),
                )
                updated += 1
            return updated

    def _migration_v3_news_and_conversation_memory(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            -- 8. SECTOR NEWS INVESTIGATIONS (Menyimpan hasil investigasi & perbandingan puluhan artikel berita)
            CREATE TABLE IF NOT EXISTS sector_news_investigations (
                investigation_id TEXT PRIMARY KEY,
                captured_at_wib TEXT NOT NULL,
                sector_key TEXT NOT NULL,
                sector_label TEXT NOT NULL,
                tickers_json TEXT NOT NULL,
                articles_compared_count INTEGER NOT NULL DEFAULT 0,
                media_sources_json TEXT NOT NULL,
                positive_signals INTEGER NOT NULL DEFAULT 0,
                negative_signals INTEGER NOT NULL DEFAULT 0,
                catalyst_direction TEXT NOT NULL,
                causal_logic TEXT NOT NULL,
                top_articles_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sector_news_key_time
                ON sector_news_investigations(sector_key, captured_at_wib DESC);

            -- 9. CONVERSATION & KNOWLEDGE LOG (Menyimpan semua arahan Bos, percakapan, & prinsip analisis)
            CREATE TABLE IF NOT EXISTS conversation_knowledge_log (
                knowledge_id TEXT PRIMARY KEY,
                created_at_wib TEXT NOT NULL,
                category TEXT NOT NULL,
                source TEXT NOT NULL,
                user_message TEXT NOT NULL,
                ai_lesson_extracted TEXT NOT NULL,
                related_tickers_json TEXT DEFAULT '[]',
                is_permanent_rule INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_conv_knowledge_time
                ON conversation_knowledge_log(is_permanent_rule DESC, created_at_wib DESC);
            """
        )
        now_iso = now_wib_iso()
        initial_rules = [
            (
                str(uuid.uuid4()),
                now_iso,
                "STRATEGI_MULTI_HORIZON",
                "DISKUSI_BOS_DIMAS",
                "Analisis tidak hanya untuk scalping harian, tetapi juga untuk investasi masa depan (Swing mingguan/bulanan) lintas seluruh sektor BEI.",
                "WAJIB membedakan 2 horizon peluang: (1) Scalping Cepat (Intraday 15m/VWAP/Volume) dan (2) Masa Depan / Swing (Tren Harian & Katalis Berita Sektor).",
                json.dumps(["ALL_IDX"]),
                1,
            ),
            (
                str(uuid.uuid4()),
                now_iso,
                "INVESTIGASI_BERITA_MULTI_SUMBER",
                "DISKUSI_BOS_DIMAS",
                "Jangan terpaku pada 1 atau 2 artikel berita saja; wajib membandingkan banyak artikel dari berbagai media setiap beberapa jam sekali.",
                "Setiap analisis wajib menggabungkan perbandingan puluhan artikel dari banyak media keuangan (Kontan, Bisnis, CNBC, Investor.id, Detik, dll.) dan mencari konsensus.",
                json.dumps(["ALL_IDX"]),
                1,
            ),
            (
                str(uuid.uuid4()),
                now_iso,
                "HUKUM_SEBAB_AKIBAT_SEKTORAL",
                "DISKUSI_BOS_DIMAS",
                "Contoh rokok: jika cukai rokok mau naik maka saham rokok (HMSP, GGRM, WIIM) tertekan/turun; jika cukai ditahan/batal naik maka saham rokok naik. Harus jeli di semua sektor.",
                "Gunakan logika sebab-akibat sektoral: Cukai Rokok -> HMSP/GGRM/WIIM; BI Rate -> BBCA/BBRI/BMRI/BBNI; Harga Batu Bara/Minyak -> ADRO/PTBA/ITMG/MEDC; Emas/Nikel -> ANTM/MDKA/AMMN/BRMS; Insentif PPN -> BSDE/CTRA/SMRA; Daya Beli/Makan Bergizi -> ICBP/INDF/AMRT/JPFA/CPIN.",
                json.dumps(["HMSP.JK", "GGRM.JK", "WIIM.JK", "BBCA.JK", "ADRO.JK", "ANTM.JK", "ICBP.JK", "BSDE.JK"]),
                1,
            ),
            (
                str(uuid.uuid4()),
                now_iso,
                "PANEL_5_AI_DAN_EVALUASI_MINGGUAN",
                "DISKUSI_BOS_DIMAS",
                "Gunakan 5 AI gratis lintas perusahaan (Google Gemini 3.6, OpenAI 120B via Groq, NVIDIA Nemotron 550B via OpenRouter, Alibaba Qwen 3.8 via Groq, dan Quant Bayesian) + 1 Hakim Ketua, lalu beri rapor mingguan AI terbaik vs terburuk.",
                "Setiap keputusan beli/tahan harus melalui persentase voting 5 AI (% Works) dan dievaluasi akurasinya setiap minggu agar AI yang jelek bisa diganti.",
                json.dumps(["ALL_IDX"]),
                1,
            ),
        ]
        for row in initial_rules:
            conn.execute(
                """
                INSERT INTO conversation_knowledge_log (
                    knowledge_id, created_at_wib, category, source,
                    user_message, ai_lesson_extracted, related_tickers_json, is_permanent_rule
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

    def save_sector_news_investigations(self, sector_results: list[dict[str, Any]]) -> int:
        """Menyimpan hasil investigasi perbandingan berita 7 sektor ke database agar AI terus belajar."""
        now_iso = now_wib_iso()
        saved = 0
        with self.connect() as conn:
            for s in sector_results:
                conn.execute(
                    """
                    INSERT INTO sector_news_investigations (
                        investigation_id, captured_at_wib, sector_key, sector_label,
                        tickers_json, articles_compared_count, media_sources_json,
                        positive_signals, negative_signals, catalyst_direction,
                        causal_logic, top_articles_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        now_iso,
                        str(s.get("sector_key", "GENERAL")),
                        str(s.get("label", "")),
                        json.dumps(s.get("tickers", []), ensure_ascii=False),
                        int(s.get("articles_compared_count", 0)),
                        json.dumps(s.get("media_sources", []), ensure_ascii=False),
                        int(s.get("positive_signals", 0)),
                        int(s.get("negative_signals", 0)),
                        str(s.get("catalyst_direction", "NETRAL")),
                        str(s.get("causal_logic", "")),
                        json.dumps(s.get("top_articles", []), ensure_ascii=False),
                    ),
                )
                saved += 1
        return saved

    def save_conversation_knowledge(
        self,
        category: str,
        source: str,
        user_message: str,
        ai_lesson_extracted: str,
        related_tickers: Optional[list[str]] = None,
        is_permanent_rule: bool = False,
    ) -> str:
        """Menyimpan percakapan, pertanyaan Bos, atau temuan baru ke database memori pengetahuan AI."""
        kid = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_knowledge_log (
                    knowledge_id, created_at_wib, category, source,
                    user_message, ai_lesson_extracted, related_tickers_json, is_permanent_rule
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kid,
                    now_wib_iso(),
                    category,
                    source,
                    user_message[:2000],
                    ai_lesson_extracted[:2000],
                    json.dumps(related_tickers or [], ensure_ascii=False),
                    1 if is_permanent_rule else 0,
                ),
            )
        return kid

    def get_recent_knowledge_and_sector_news(self, ticker: Optional[str] = None, limit: int = 5) -> dict[str, Any]:
        """Mengambil aturan permanen Bos, riwayat percakapan penting, dan investigasi berita sektor terbaru dari database."""
        with self.connect() as conn:
            rules = conn.execute(
                """
                SELECT category, user_message, ai_lesson_extracted, created_at_wib
                FROM conversation_knowledge_log
                ORDER BY is_permanent_rule DESC, created_at_wib DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            news_rows = conn.execute(
                """
                SELECT sector_key, sector_label, articles_compared_count, catalyst_direction, causal_logic, captured_at_wib
                FROM sector_news_investigations
                ORDER BY captured_at_wib DESC
                LIMIT 7
                """
            ).fetchall()

        return {
            "aturan_dan_percakapan_tersimpan": [dict(r) for r in rules],
            "investigasi_berita_sektor_terakhir": [dict(n) for n in news_rows],
        }
