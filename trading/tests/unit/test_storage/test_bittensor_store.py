from __future__ import annotations
from datetime import datetime

import aiosqlite
import pytest

from integrations.bittensor.models import (
    DerivedBittensorView,
    MinerAccuracyRecord,
    RawMinerForecast,
    RealizedWindowSnapshot,
)
from storage.bittensor import BittensorStore
from storage.db import init_db


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    s = BittensorStore(db)
    yield s
    await db.close()


def _make_raw_forecast(
    window_id: str = "w1", miner_hotkey: str = "hk1"
) -> RawMinerForecast:
    return RawMinerForecast(
        window_id=window_id,
        request_uuid="req1",
        collected_at=datetime(2026, 3, 28, 12, 0),
        miner_uid=1,
        miner_hotkey=miner_hotkey,
        stream_id="BTCUSD-5m",
        topic_id=1,
        schema_id=1,
        symbol="BTCUSD",
        timeframe="5m",
        feature_ids=[1, 2, 3, 4, 5],
        prediction_size=100,
        predictions=[0.1] * 100,
        hashed_predictions="abc123",
        hash_verified=True,
        incentive_score=0.5,
        vtrust=0.9,
        stake_tao=1000.0,
        metagraph_block=100,
    )


def _make_derived_view(window_id: str = "w1") -> DerivedBittensorView:
    return DerivedBittensorView(
        symbol="BTCUSD",
        timeframe="5m",
        window_id=window_id,
        timestamp=datetime(2026, 3, 28, 12, 0),
        responder_count=5,
        bullish_count=3,
        bearish_count=1,
        flat_count=1,
        weighted_direction=0.4,
        weighted_expected_return=0.003,
        agreement_ratio=0.6,
        equal_weight_direction=0.35,
        equal_weight_expected_return=0.0025,
        is_low_confidence=False,
        derivation_version="v1",
    )


async def test_save_and_fetch_raw_forecasts(store: BittensorStore):
    forecast = _make_raw_forecast()
    await store.save_raw_forecasts([forecast])
    rows = await store.get_raw_forecasts_by_window("w1")
    assert len(rows) == 1
    assert rows[0].miner_hotkey == "hk1"
    assert rows[0].symbol == "BTCUSD"
    assert len(rows[0].predictions) == 100


async def test_save_raw_forecasts_is_idempotent(store: BittensorStore):
    forecast = _make_raw_forecast()
    await store.save_raw_forecasts([forecast])
    await store.save_raw_forecasts([forecast])
    rows = await store.get_raw_forecasts_by_window("w1")
    assert len(rows) == 1


async def test_save_and_fetch_derived_view(store: BittensorStore):
    view = _make_derived_view()
    await store.save_derived_view(view)
    result = await store.get_latest_view("BTCUSD", "5m")
    assert result is not None
    assert result.window_id == "w1"
    assert result.weighted_direction == 0.4
    assert result.is_low_confidence is False


async def test_get_latest_view_returns_newest(store: BittensorStore):
    v1 = _make_derived_view("w1")
    v2 = DerivedBittensorView(
        symbol="BTCUSD",
        timeframe="5m",
        window_id="w2",
        timestamp=datetime(2026, 3, 28, 12, 30),
        responder_count=5,
        bullish_count=4,
        bearish_count=0,
        flat_count=1,
        weighted_direction=0.8,
        weighted_expected_return=0.005,
        agreement_ratio=0.8,
        equal_weight_direction=0.7,
        equal_weight_expected_return=0.004,
        is_low_confidence=False,
        derivation_version="v1",
    )
    await store.save_derived_view(v1)
    await store.save_derived_view(v2)
    result = await store.get_latest_view("BTCUSD", "5m")
    assert result is not None
    assert result.window_id == "w2"


async def test_get_unevaluated_windows(store: BittensorStore):
    view = _make_derived_view("w1")
    await store.save_derived_view(view)
    now = datetime(2026, 3, 28, 22, 0)
    windows = await store.get_unevaluated_windows(
        now, delay_factor=1.2, prediction_size=100, timeframe_minutes=5
    )
    assert len(windows) == 1
    assert windows[0].window_id == "w1"


async def test_get_unevaluated_windows_retries_pending_window_after_realized_snapshot(
    store: BittensorStore,
):
    view = _make_derived_view("w-retry")
    await store.save_derived_view(view)
    await store.save_realized_window(
        RealizedWindowSnapshot(
            window_id="w-retry",
            symbol="BTCUSD",
            timeframe="5m",
            realized_path=[100.0, 101.0],
            realized_return=1.0,
            bars_used=2,
            source="coingecko",
            captured_at=datetime(2026, 3, 28, 12, 30),
        )
    )

    now = datetime(2026, 3, 28, 22, 0)
    windows = await store.get_unevaluated_windows(
        now, delay_factor=1.2, prediction_size=100, timeframe_minutes=5
    )
    assert len(windows) == 1
    assert windows[0].window_id == "w-retry"


async def test_save_accuracy_records_unique_constraint(store: BittensorStore):
    record = MinerAccuracyRecord(
        window_id="w1",
        miner_hotkey="hk1",
        symbol="BTCUSD",
        timeframe="5m",
        direction_correct=True,
        predicted_return=0.003,
        actual_return=0.002,
        magnitude_error=0.001,
        path_correlation=0.85,
        outcome_bars=100,
        scoring_version="v1",
        evaluated_at=datetime(2026, 3, 28, 20, 0),
    )
    await store.save_accuracy_records([record])
    await store.save_accuracy_records([record])
    rows = await store.get_accuracy_for_window("w1")
    assert len(rows) == 1


class TestGetAccuracyRollup:
    async def test_returns_empty_dict_for_no_data(self, store):
        result = await store.get_accuracy_rollup(["5Fhot1"], lookback=500)
        assert result == {}

    async def test_returns_aggregated_metrics(self, store):
        from integrations.bittensor.models import MinerAccuracyRecord
        from datetime import datetime

        records = [
            MinerAccuracyRecord(
                window_id=f"w{i}",
                miner_hotkey="5Fhot1",
                symbol="BTCUSD",
                timeframe="5m",
                direction_correct=(i < 2),
                predicted_return=0.01 * i,
                actual_return=0.005 * i,
                magnitude_error=0.005 * i,
                path_correlation=0.5 if i < 2 else None,
                outcome_bars=100,
                scoring_version="v1",
                evaluated_at=datetime(2026, 3, 31, i, 0, 0),
            )
            for i in range(3)
        ]
        await store.save_accuracy_records(records)
        result = await store.get_accuracy_rollup(["5Fhot1"], lookback=500)
        assert "5Fhot1" in result
        rollup = result["5Fhot1"]
        assert rollup["windows_evaluated"] == 3
        assert abs(rollup["direction_accuracy"] - 2 / 3) < 1e-9
        assert rollup["mean_magnitude_error"] is not None
        assert rollup["mean_path_correlation"] is not None

    async def test_respects_lookback_limit(self, store):
        from integrations.bittensor.models import MinerAccuracyRecord
        from datetime import datetime

        records = [
            MinerAccuracyRecord(
                window_id=f"w{i}",
                miner_hotkey="5Fhot1",
                symbol="BTCUSD",
                timeframe="5m",
                direction_correct=True,
                predicted_return=0.01,
                actual_return=0.01,
                magnitude_error=0.0,
                path_correlation=0.9,
                outcome_bars=100,
                scoring_version="v1",
                evaluated_at=datetime(2026, 3, 31, i, 0, 0),
            )
            for i in range(5)
        ]
        await store.save_accuracy_records(records)
        result = await store.get_accuracy_rollup(["5Fhot1"], lookback=2)
        assert result["5Fhot1"]["windows_evaluated"] == 2


class TestWindowExpiry:
    async def test_expire_stale_windows(self, store):
        from integrations.bittensor.models import DerivedBittensorView
        from datetime import datetime

        old = datetime(2026, 3, 30, 10, 0, 0)
        view = DerivedBittensorView(
            window_id="w-old",
            symbol="BTCUSD",
            timeframe="5m",
            timestamp=old,
            responder_count=5,
            bullish_count=3,
            bearish_count=1,
            flat_count=1,
            weighted_direction=0.3,
            weighted_expected_return=0.01,
            agreement_ratio=0.6,
            equal_weight_direction=0.25,
            equal_weight_expected_return=0.008,
            is_low_confidence=False,
            derivation_version="v1",
        )
        await store.save_derived_view(view)

        now = datetime(2026, 3, 31, 15, 0, 0)
        count = await store.expire_stale_windows(now=now, ttl_hours=2)
        assert count == 1

    async def test_get_unevaluated_windows_excludes_expired(self, store):
        from integrations.bittensor.models import DerivedBittensorView
        from datetime import datetime

        old = datetime(2026, 3, 30, 10, 0, 0)
        view = DerivedBittensorView(
            window_id="w-expired",
            symbol="BTCUSD",
            timeframe="5m",
            timestamp=old,
            responder_count=5,
            bullish_count=3,
            bearish_count=1,
            flat_count=1,
            weighted_direction=0.3,
            weighted_expected_return=0.01,
            agreement_ratio=0.6,
            equal_weight_direction=0.25,
            equal_weight_expected_return=0.008,
            is_low_confidence=False,
            derivation_version="v1",
        )
        await store.save_derived_view(view)

        now_expire = datetime(2026, 3, 31, 15, 0, 0)
        await store.expire_stale_windows(now=now_expire, ttl_hours=2)

        now_query = datetime(2026, 3, 31, 16, 0, 0)
        windows = await store.get_unevaluated_windows(
            now=now_query,
            delay_factor=1.1,
            prediction_size=100,
            timeframe_minutes=5,
        )
        assert len(windows) == 0

    async def test_save_derived_view_preserves_evaluation_status(self, store):
        """Re-saving a derived view should NOT reset evaluation_status."""
        from integrations.bittensor.models import DerivedBittensorView
        from datetime import datetime

        view = DerivedBittensorView(
            window_id="w-status",
            symbol="BTCUSD",
            timeframe="5m",
            timestamp=datetime(2026, 3, 30, 10, 0, 0),
            responder_count=5,
            bullish_count=3,
            bearish_count=1,
            flat_count=1,
            weighted_direction=0.3,
            weighted_expected_return=0.01,
            agreement_ratio=0.6,
            equal_weight_direction=0.25,
            equal_weight_expected_return=0.008,
            is_low_confidence=False,
            derivation_version="v1",
        )
        await store.save_derived_view(view)
        await store.mark_window_evaluated("w-status")

        # Re-save same view — should NOT reset to 'pending'
        view.weighted_direction = 0.5
        await store.save_derived_view(view)

        # Verify status is still 'evaluated'
        cursor = await store._db.execute(
            "SELECT evaluation_status FROM bittensor_derived_views WHERE window_id = ?",
            ("w-status",),
        )
        row = await cursor.fetchone()
        assert dict(row)["evaluation_status"] == "evaluated"


class TestGetAccuracyForMiner:
    async def test_returns_records_for_hotkey(self, store):
        records = [
            MinerAccuracyRecord(
                window_id=f"w{i}",
                miner_hotkey="hk1",
                symbol="BTCUSD",
                timeframe="5m",
                direction_correct=True,
                predicted_return=0.01,
                actual_return=0.01,
                magnitude_error=0.0,
                path_correlation=0.9,
                outcome_bars=100,
                scoring_version="v1",
                evaluated_at=datetime(2026, 3, 31, i, 0, 0),
            )
            for i in range(3)
        ]
        await store.save_accuracy_records(records)
        result = await store.get_accuracy_for_miner("hk1")
        assert len(result) == 3
        assert all(r.miner_hotkey == "hk1" for r in result)

    async def test_returns_newest_first(self, store):
        records = [
            MinerAccuracyRecord(
                window_id=f"w{i}",
                miner_hotkey="hk1",
                symbol="BTCUSD",
                timeframe="5m",
                direction_correct=True,
                predicted_return=0.01,
                actual_return=0.01,
                magnitude_error=0.0,
                path_correlation=0.9,
                outcome_bars=100,
                scoring_version="v1",
                evaluated_at=datetime(2026, 3, 31, i, 0, 0),
            )
            for i in range(3)
        ]
        await store.save_accuracy_records(records)
        result = await store.get_accuracy_for_miner("hk1")
        assert result[0].evaluated_at > result[1].evaluated_at

    async def test_filters_by_hotkey(self, store):
        records = [
            MinerAccuracyRecord(
                window_id=f"w{i}",
                miner_hotkey=f"hk{i}",
                symbol="BTCUSD",
                timeframe="5m",
                direction_correct=True,
                predicted_return=0.01,
                actual_return=0.01,
                magnitude_error=0.0,
                path_correlation=0.9,
                outcome_bars=100,
                scoring_version="v1",
                evaluated_at=datetime(2026, 3, 31, i, 0, 0),
            )
            for i in range(3)
        ]
        await store.save_accuracy_records(records)
        result = await store.get_accuracy_for_miner("hk1")
        assert len(result) == 1
        assert result[0].miner_hotkey == "hk1"

    async def test_empty_for_unknown_hotkey(self, store):
        result = await store.get_accuracy_for_miner("unknown_hotkey")
        assert result == []


class TestGetRecentViews:
    async def test_returns_views_for_symbol(self, store):
        for i in range(3):
            view = DerivedBittensorView(
                window_id=f"w{i}",
                symbol="BTCUSD",
                timeframe="5m",
                timestamp=datetime(2026, 3, 31, i, 0, 0),
                responder_count=5,
                bullish_count=3,
                bearish_count=1,
                flat_count=1,
                weighted_direction=0.4,
                weighted_expected_return=0.003,
                agreement_ratio=0.6,
                equal_weight_direction=0.35,
                equal_weight_expected_return=0.0025,
                is_low_confidence=False,
                derivation_version="v1",
            )
            await store.save_derived_view(view)
        result = await store.get_recent_views("BTCUSD", "5m")
        assert len(result) == 3
        assert all(r["symbol"] == "BTCUSD" for r in result)

    async def test_returns_newest_first(self, store):
        for i in range(3):
            view = DerivedBittensorView(
                window_id=f"w{i}",
                symbol="BTCUSD",
                timeframe="5m",
                timestamp=datetime(2026, 3, 31, i, 0, 0),
                responder_count=5,
                bullish_count=3,
                bearish_count=1,
                flat_count=1,
                weighted_direction=0.4,
                weighted_expected_return=0.003,
                agreement_ratio=0.6,
                equal_weight_direction=0.35,
                equal_weight_expected_return=0.0025,
                is_low_confidence=False,
                derivation_version="v1",
            )
            await store.save_derived_view(view)
        result = await store.get_recent_views("BTCUSD", "5m")
        assert result[0]["timestamp"] > result[1]["timestamp"]

    async def test_filters_by_symbol(self, store):
        for symbol, wid in [("BTCUSD", "w1"), ("ETHUSD", "w2")]:
            view = DerivedBittensorView(
                window_id=wid,
                symbol=symbol,
                timeframe="5m",
                timestamp=datetime(2026, 3, 31, 10, 0, 0),
                responder_count=5,
                bullish_count=3,
                bearish_count=1,
                flat_count=1,
                weighted_direction=0.4,
                weighted_expected_return=0.003,
                agreement_ratio=0.6,
                equal_weight_direction=0.35,
                equal_weight_expected_return=0.0025,
                is_low_confidence=False,
                derivation_version="v1",
            )
            await store.save_derived_view(view)
        result = await store.get_recent_views("BTCUSD", "5m")
        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSD"
