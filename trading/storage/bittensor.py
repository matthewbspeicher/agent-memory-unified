from __future__ import annotations
import json
from datetime import datetime, timedelta

import aiosqlite

from integrations.bittensor.models import (
    BittensorEvaluationWindow,
    DerivedBittensorView,
    MinerAccuracyRecord,
    MinerRanking,
    RawMinerForecast,
    RealizedWindowSnapshot,
)


class BittensorStore:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Raw forecasts
    # ------------------------------------------------------------------

    async def save_raw_forecasts(self, rows: list[RawMinerForecast]) -> None:
        for r in rows:
            await self._db.execute(
                """INSERT INTO bittensor_raw_forecasts
                   (window_id, request_uuid, collected_at, stream_id, topic_id, schema_id,
                    symbol, timeframe, feature_ids, prediction_size, miner_uid, miner_hotkey,
                    predictions, hashed_predictions, hash_verified, incentive_score, vtrust,
                    stake_tao, metagraph_block)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(window_id, miner_hotkey, request_uuid) DO UPDATE SET
                       collected_at = excluded.collected_at,
                       stream_id = excluded.stream_id,
                       topic_id = excluded.topic_id,
                       schema_id = excluded.schema_id,
                       symbol = excluded.symbol,
                       timeframe = excluded.timeframe,
                       feature_ids = excluded.feature_ids,
                       prediction_size = excluded.prediction_size,
                       miner_uid = excluded.miner_uid,
                       predictions = excluded.predictions,
                       hashed_predictions = excluded.hashed_predictions,
                       hash_verified = excluded.hash_verified,
                       incentive_score = excluded.incentive_score,
                       vtrust = excluded.vtrust,
                       stake_tao = excluded.stake_tao,
                       metagraph_block = excluded.metagraph_block""",
                (
                    r.window_id,
                    r.request_uuid,
                    r.collected_at.isoformat(),
                    r.stream_id,
                    r.topic_id,
                    r.schema_id,
                    r.symbol,
                    r.timeframe,
                    json.dumps(r.feature_ids),
                    r.prediction_size,
                    r.miner_uid,
                    r.miner_hotkey,
                    json.dumps(r.predictions),
                    r.hashed_predictions,
                    int(r.hash_verified),
                    r.incentive_score,
                    r.vtrust,
                    r.stake_tao,
                    r.metagraph_block,
                ),
            )
        await self._db.commit()

    async def get_raw_forecasts_by_window(
        self, window_id: str
    ) -> list[RawMinerForecast]:
        cursor = await self._db.execute(
            "SELECT * FROM bittensor_raw_forecasts WHERE window_id = ?",
            (window_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_raw_forecast(row) for row in rows]

    @staticmethod
    def _row_to_raw_forecast(row: aiosqlite.Row) -> RawMinerForecast:
        r = dict(row)
        return RawMinerForecast(
            window_id=r["window_id"],
            request_uuid=r["request_uuid"],
            collected_at=datetime.fromisoformat(r["collected_at"]),
            miner_uid=r["miner_uid"],
            miner_hotkey=r["miner_hotkey"],
            stream_id=r["stream_id"],
            topic_id=r["topic_id"],
            schema_id=r["schema_id"],
            symbol=r["symbol"],
            timeframe=r["timeframe"],
            feature_ids=json.loads(r["feature_ids"]),
            prediction_size=r["prediction_size"],
            predictions=json.loads(r["predictions"]),
            hashed_predictions=r["hashed_predictions"],
            hash_verified=bool(r["hash_verified"]),
            incentive_score=r["incentive_score"],
            vtrust=r["vtrust"],
            stake_tao=r["stake_tao"],
            metagraph_block=r["metagraph_block"],
        )

    # ------------------------------------------------------------------
    # Derived views
    # ------------------------------------------------------------------

    async def save_derived_view(self, view: DerivedBittensorView) -> None:
        await self._db.execute(
            """INSERT INTO bittensor_derived_views
               (window_id, symbol, timeframe, timestamp, responder_count, bullish_count,
                bearish_count, flat_count, weighted_direction, weighted_expected_return,
                agreement_ratio, equal_weight_direction, equal_weight_expected_return,
                is_low_confidence, derivation_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(window_id) DO UPDATE SET
                symbol = excluded.symbol,
                timeframe = excluded.timeframe,
                timestamp = excluded.timestamp,
                responder_count = excluded.responder_count,
                bullish_count = excluded.bullish_count,
                bearish_count = excluded.bearish_count,
                flat_count = excluded.flat_count,
                weighted_direction = excluded.weighted_direction,
                weighted_expected_return = excluded.weighted_expected_return,
                agreement_ratio = excluded.agreement_ratio,
                equal_weight_direction = excluded.equal_weight_direction,
                equal_weight_expected_return = excluded.equal_weight_expected_return,
                is_low_confidence = excluded.is_low_confidence,
                derivation_version = excluded.derivation_version""",
            (
                view.window_id,
                view.symbol,
                view.timeframe,
                view.timestamp.isoformat(),
                view.responder_count,
                view.bullish_count,
                view.bearish_count,
                view.flat_count,
                view.weighted_direction,
                view.weighted_expected_return,
                view.agreement_ratio,
                view.equal_weight_direction,
                view.equal_weight_expected_return,
                int(view.is_low_confidence),
                view.derivation_version,
            ),
        )
        await self._db.commit()

    async def expire_stale_windows(self, now: datetime, ttl_hours: int = 2) -> int:
        """Mark pending derived views older than ttl_hours as expired."""
        cutoff = now - timedelta(hours=ttl_hours)
        cursor = await self._db.execute(
            """UPDATE bittensor_derived_views
               SET evaluation_status = 'expired'
               WHERE evaluation_status = 'pending'
                 AND timestamp <= ?""",
            (cutoff.isoformat(),),
        )
        await self._db.commit()
        return getattr(cursor, "rowcount", 0)

    async def mark_window_evaluated(self, window_id: str) -> None:
        """Mark a derived view as evaluated after successful scoring."""
        await self._db.execute(
            "UPDATE bittensor_derived_views SET evaluation_status = 'evaluated' WHERE window_id = ?",
            (window_id,),
        )
        await self._db.commit()

    async def get_latest_view(
        self, symbol: str, timeframe: str
    ) -> DerivedBittensorView | None:
        cursor = await self._db.execute(
            """SELECT * FROM bittensor_derived_views
               WHERE symbol = ? AND timeframe = ?
               ORDER BY timestamp DESC LIMIT 1""",
            (symbol, timeframe),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_derived_view(row)

    async def get_view_history(
        self, symbol: str, timeframe: str, since: datetime
    ) -> list[DerivedBittensorView]:
        cursor = await self._db.execute(
            """SELECT * FROM bittensor_derived_views
               WHERE symbol = ? AND timeframe = ? AND timestamp >= ?
               ORDER BY timestamp ASC""",
            (symbol, timeframe, since.isoformat()),
        )
        rows = await cursor.fetchall()
        return [self._row_to_derived_view(row) for row in rows]

    @staticmethod
    def _row_to_derived_view(row: aiosqlite.Row) -> DerivedBittensorView:
        r = dict(row)
        return DerivedBittensorView(
            window_id=r["window_id"],
            symbol=r["symbol"],
            timeframe=r["timeframe"],
            timestamp=datetime.fromisoformat(r["timestamp"]),
            responder_count=r["responder_count"],
            bullish_count=r["bullish_count"],
            bearish_count=r["bearish_count"],
            flat_count=r["flat_count"],
            weighted_direction=r["weighted_direction"],
            weighted_expected_return=r["weighted_expected_return"],
            agreement_ratio=r["agreement_ratio"],
            equal_weight_direction=r["equal_weight_direction"],
            equal_weight_expected_return=r["equal_weight_expected_return"],
            is_low_confidence=bool(r["is_low_confidence"]),
            derivation_version=r["derivation_version"],
        )

    # ------------------------------------------------------------------
    # Unevaluated windows
    # ------------------------------------------------------------------

    async def get_unevaluated_windows(
        self,
        now: datetime,
        delay_factor: float,
        prediction_size: int,
        timeframe_minutes: int,
    ) -> list[BittensorEvaluationWindow]:
        """Return derived views that have no realized window yet and are old enough
        that the prediction horizon has elapsed (with a safety delay_factor buffer)."""
        maturity_seconds = prediction_size * timeframe_minutes * 60 * delay_factor
        cutoff = datetime(
            now.year, now.month, now.day, now.hour, now.minute, now.second
        ) - timedelta(seconds=maturity_seconds)
        # asyncpg requires a datetime instance for TIMESTAMP params; SQLite
        # TEXT-affinity columns need the ISO string with T-separator to compare
        # correctly against stored values written by .isoformat(). Branch.
        from storage.postgres import PostgresDB

        cutoff_param = cutoff if isinstance(self._db, PostgresDB) else cutoff.isoformat()
        cursor = await self._db.execute(
            """SELECT dv.window_id, dv.symbol, dv.timeframe, dv.timestamp,
                      rf.prediction_size
               FROM bittensor_derived_views dv
               LEFT JOIN (
                   SELECT window_id, MAX(prediction_size) AS prediction_size
                   FROM bittensor_raw_forecasts
                   GROUP BY window_id
               ) rf ON rf.window_id = dv.window_id
               WHERE dv.evaluation_status = 'pending'
                 AND dv.timestamp <= ?
               ORDER BY dv.timestamp ASC""",
            (cutoff_param,),
        )
        rows = await cursor.fetchall()
        result: list[BittensorEvaluationWindow] = []
        for row in rows:
            r = dict(row)
            result.append(
                BittensorEvaluationWindow(
                    window_id=r["window_id"],
                    symbol=r["symbol"],
                    timeframe=r["timeframe"],
                    collected_at=datetime.fromisoformat(r["timestamp"]),
                    prediction_size=r["prediction_size"]
                    if r["prediction_size"] is not None
                    else prediction_size,
                )
            )
        return result

    # ------------------------------------------------------------------
    # Realized windows
    # ------------------------------------------------------------------

    async def save_realized_window(self, realized: RealizedWindowSnapshot) -> None:
        await self._db.execute(
            """INSERT OR REPLACE INTO bittensor_realized_windows
               (window_id, symbol, timeframe, realized_path, realized_return,
                bars_used, source, captured_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                realized.window_id,
                realized.symbol,
                realized.timeframe,
                json.dumps(realized.realized_path),
                realized.realized_return,
                realized.bars_used,
                realized.source,
                realized.captured_at.isoformat(),
            ),
        )
        await self._db.commit()

    @staticmethod
    def _row_to_realized_window(row: aiosqlite.Row) -> RealizedWindowSnapshot:
        r = dict(row)
        return RealizedWindowSnapshot(
            window_id=r["window_id"],
            symbol=r["symbol"],
            timeframe=r["timeframe"],
            realized_path=json.loads(r["realized_path"]),
            realized_return=r["realized_return"],
            bars_used=r["bars_used"],
            source=r["source"],
            captured_at=datetime.fromisoformat(r["captured_at"]),
        )

    # ------------------------------------------------------------------
    # Accuracy records
    # ------------------------------------------------------------------

    async def save_accuracy_records(self, rows: list[MinerAccuracyRecord]) -> None:
        for rec in rows:
            await self._db.execute(
                """INSERT OR REPLACE INTO bittensor_accuracy_records
                   (window_id, miner_hotkey, symbol, timeframe, direction_correct,
                    predicted_return, actual_return, magnitude_error, path_correlation,
                    outcome_bars, scoring_version, evaluated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec.window_id,
                    rec.miner_hotkey,
                    rec.symbol,
                    rec.timeframe,
                    int(rec.direction_correct),
                    rec.predicted_return,
                    rec.actual_return,
                    rec.magnitude_error,
                    rec.path_correlation,
                    rec.outcome_bars,
                    rec.scoring_version,
                    rec.evaluated_at.isoformat(),
                ),
            )
        await self._db.commit()

    async def get_accuracy_for_window(
        self, window_id: str
    ) -> list[MinerAccuracyRecord]:
        cursor = await self._db.execute(
            "SELECT * FROM bittensor_accuracy_records WHERE window_id = ?",
            (window_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_accuracy_record(row) for row in rows]

    async def get_accuracy_rollup(
        self,
        hotkeys: list[str],
        lookback: int,
        symbol: str | None = None,
    ) -> dict[str, dict]:
        """Return one aggregate record per miner from their most recent accuracy records.

        Returns dict keyed by miner_hotkey with values:
            windows_evaluated: int
            direction_accuracy: float
            mean_magnitude_error: float
            mean_path_correlation: float | None
        """
        if not hotkeys:
            return {}

        placeholders = ", ".join("?" for _ in hotkeys)
        where_clause = f"WHERE miner_hotkey IN ({placeholders})"
        params = [*hotkeys]
        if symbol and symbol != "aggregate":
            where_clause += " AND symbol = ?"
            params.append(symbol)
        
        params.append(lookback)

        cursor = await self._db.execute(
            f"""SELECT miner_hotkey,
                       COUNT(*) AS windows_evaluated,
                       AVG(direction_correct) AS direction_accuracy,
                       AVG(magnitude_error) AS mean_magnitude_error,
                       AVG(CASE WHEN path_correlation IS NOT NULL THEN path_correlation END) AS mean_path_correlation
                FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY miner_hotkey ORDER BY evaluated_at DESC
                    ) AS rn
                    FROM bittensor_accuracy_records
                    {where_clause}
                ) sub
                WHERE rn <= ?
                GROUP BY miner_hotkey""",
            tuple(params),
        )
        rows = await cursor.fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            r = dict(row)
            result[r["miner_hotkey"]] = {
                "windows_evaluated": r["windows_evaluated"],
                "direction_accuracy": r["direction_accuracy"],
                "mean_magnitude_error": r["mean_magnitude_error"],
                "mean_path_correlation": r["mean_path_correlation"],
            }
        return result

    async def get_accuracy_for_miner(
        self, hotkey: str, limit: int = 50
    ) -> list[MinerAccuracyRecord]:
        """Return recent accuracy records for a single miner, newest first."""
        cursor = await self._db.execute(
            """SELECT * FROM bittensor_accuracy_records
               WHERE miner_hotkey = ?
               ORDER BY evaluated_at DESC
               LIMIT ?""",
            (hotkey, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_accuracy_record(row) for row in rows]

    async def get_miner_max_drawdown(
        self, hotkey: str, limit: int = 50, symbol: str | None = None
    ) -> float:
        """Return the maximum magnitude_error (proxy for drawdown) for a miner."""
        where_clause = "WHERE miner_hotkey = ?"
        params = [hotkey]
        if symbol and symbol != "aggregate":
            where_clause += " AND symbol = ?"
            params.append(symbol)
        params.append(limit)

        cursor = await self._db.execute(
            f"""SELECT MAX(magnitude_error) AS max_drawdown
               FROM (
                   SELECT magnitude_error
                   FROM bittensor_accuracy_records
                   {where_clause}
                   ORDER BY evaluated_at DESC
                   LIMIT ?
               )""",
            tuple(params),
        )
        row = await cursor.fetchone()
        if row is None or row[0] is None:
            return 0.0
        return float(row[0])

    async def get_miner_max_drawdowns(
        self, hotkeys: list[str], limit: int = 50, symbol: str | None = None
    ) -> dict[str, float]:
        """Return max magnitude_error for each hotkey."""
        if not hotkeys:
            return {}
        result = {}
        for hotkey in hotkeys:
            result[hotkey] = await self.get_miner_max_drawdown(hotkey, limit, symbol)
        return result

    async def get_distinct_symbols(self) -> list[str]:
        """Return all symbols present in accuracy records."""
        cursor = await self._db.execute(
            "SELECT DISTINCT symbol FROM bittensor_accuracy_records"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_recent_views(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[dict]:
        """Return recent derived views for a symbol/timeframe, newest first."""
        cursor = await self._db.execute(
            """SELECT * FROM bittensor_derived_views
               WHERE symbol = ? AND timeframe = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (symbol, timeframe, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _row_to_accuracy_record(row: aiosqlite.Row) -> MinerAccuracyRecord:
        r = dict(row)
        return MinerAccuracyRecord(
            window_id=r["window_id"],
            miner_hotkey=r["miner_hotkey"],
            symbol=r["symbol"],
            timeframe=r["timeframe"],
            direction_correct=bool(r["direction_correct"]),
            predicted_return=r["predicted_return"],
            actual_return=r["actual_return"],
            magnitude_error=r["magnitude_error"],
            path_correlation=r["path_correlation"],
            outcome_bars=r["outcome_bars"],
            scoring_version=r["scoring_version"],
            evaluated_at=datetime.fromisoformat(r["evaluated_at"]),
        )

    # ------------------------------------------------------------------
    # Miner hotkeys and incentive scores
    # ------------------------------------------------------------------

    async def get_distinct_miner_hotkeys(self) -> list[str]:
        """Return distinct miner hotkeys from accuracy records."""
        cursor = await self._db.execute(
            "SELECT DISTINCT miner_hotkey FROM bittensor_accuracy_records"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_latest_incentive_scores(self, hotkeys: list[str]) -> dict[str, float]:
        """Return the most recent incentive_score for each hotkey.

        Returns dict mapping hotkey -> incentive_score (0.0 if not found).
        """
        if not hotkeys:
            return {}
        placeholders = ",".join("?" * len(hotkeys))
        cursor = await self._db.execute(
            f"""SELECT miner_hotkey, incentive_score
                FROM bittensor_raw_forecasts
                WHERE miner_hotkey IN ({placeholders})
                ORDER BY collected_at DESC""",
            tuple(hotkeys),
        )
        rows = await cursor.fetchall()
        result: dict[str, float] = {}
        for hotkey, incentive in rows:
            if hotkey not in result:
                result[hotkey] = incentive if incentive is not None else 0.0
        return result

    # ------------------------------------------------------------------
    # Miner rankings
    # ------------------------------------------------------------------

    async def update_miner_ranking(self, ranking: MinerRanking) -> None:
        """Upsert a miner's ranking metrics for a specific symbol."""
        await self._db.execute(
            """INSERT OR REPLACE INTO bittensor_miner_rankings
               (miner_hotkey, symbol, windows_evaluated, direction_accuracy, mean_magnitude_error,
                mean_path_correlation, internal_score, latest_incentive_score, hybrid_score,
                alpha_used, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ranking.miner_hotkey,
                ranking.symbol,
                ranking.windows_evaluated,
                ranking.direction_accuracy,
                ranking.mean_magnitude_error,
                ranking.mean_path_correlation,
                ranking.internal_score,
                ranking.latest_incentive_score,
                ranking.hybrid_score,
                ranking.alpha_used,
                ranking.updated_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def get_miner_rankings(
        self, limit: int = 50, symbol: str | None = None
    ) -> list[MinerRanking]:
        """Fetch top miner rankings, optionally filtered by symbol."""
        if symbol:
            cursor = await self._db.execute(
                """SELECT * FROM bittensor_miner_rankings
                   WHERE symbol = ?
                   ORDER BY hybrid_score DESC LIMIT ?""",
                (symbol, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM bittensor_miner_rankings ORDER BY hybrid_score DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [self._row_to_miner_ranking(row) for row in rows]

    @staticmethod
    def _row_to_miner_ranking(row: aiosqlite.Row) -> MinerRanking:
        r = dict(row)
        return MinerRanking(
            miner_hotkey=r["miner_hotkey"],
            symbol=r.get("symbol", "aggregate"),
            windows_evaluated=r["windows_evaluated"],
            direction_accuracy=r["direction_accuracy"],
            mean_magnitude_error=r["mean_magnitude_error"],
            mean_path_correlation=r["mean_path_correlation"],
            internal_score=r["internal_score"],
            latest_incentive_score=r["latest_incentive_score"],
            hybrid_score=r["hybrid_score"],
            alpha_used=r["alpha_used"],
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )

    # ------------------------------------------------------------------
    # Processed positions (for TaoshiBridge persistence)
    # ------------------------------------------------------------------

    async def get_processed_position_uuids(self) -> set[str]:
        """Return all position UUIDs already processed by TaoshiBridge."""
        cursor = await self._db.execute(
            "SELECT position_uuid FROM bittensor_processed_positions"
        )
        rows = await cursor.fetchall()
        return {row[0] for row in rows}

    async def save_processed_position_uuid(self, uuid: str, hotkey: str) -> None:
        """Mark a position UUID as processed."""
        await self._db.execute(
            "INSERT OR IGNORE INTO bittensor_processed_positions (position_uuid, miner_hotkey) VALUES (?, ?)",
            (uuid, hotkey),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Weight-set audit log
    # ------------------------------------------------------------------

    async def save_weight_set_log(
        self,
        *,
        attempted_at: datetime,
        status: str,
        skip_reason: str | None,
        uid_count: int,
        weights_payload: list[tuple[int, float]] | None,
        block: int | None,
        error_detail: str | None,
    ) -> None:
        """Persist a single weight-set attempt.

        status is one of "success", "skipped", "failed". weights_payload is
        the (uid, weight) list that was submitted (or would have been) —
        stored as JSON for post-hoc analysis.
        """
        payload_json = (
            json.dumps([[int(u), float(w)] for u, w in weights_payload])
            if weights_payload
            else None
        )
        await self._db.execute(
            """INSERT INTO bittensor_weight_set_log
               (attempted_at, status, skip_reason, uid_count, weights_payload, block, error_detail)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                attempted_at.isoformat(),
                status,
                skip_reason,
                uid_count,
                payload_json,
                block,
                error_detail,
            ),
        )
        await self._db.commit()

    async def get_recent_weight_set_logs(self, limit: int = 50) -> list[dict]:
        """Return the N most recent weight-set attempts."""
        cursor = await self._db.execute(
            """SELECT id, attempted_at, status, skip_reason, uid_count,
                      weights_payload, block, error_detail
               FROM bittensor_weight_set_log
               ORDER BY id DESC
               LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "id": row[0],
                    "attempted_at": row[1],
                    "status": row[2],
                    "skip_reason": row[3],
                    "uid_count": row[4],
                    "weights_payload": json.loads(row[5]) if row[5] else None,
                    "block": row[6],
                    "error_detail": row[7],
                }
            )
        return out
