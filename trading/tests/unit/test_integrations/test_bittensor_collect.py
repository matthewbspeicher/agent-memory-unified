from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


from integrations.bittensor.models import RawMinerForecast


def _make_forecast(
    hotkey: str, predictions: list[float], hash_verified: bool = True
) -> RawMinerForecast:
    return RawMinerForecast(
        window_id="w1",
        request_uuid="req1",
        collected_at=datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc),
        miner_uid=1,
        miner_hotkey=hotkey,
        stream_id="BTCUSD-5m",
        topic_id=1,
        schema_id=1,
        symbol="BTCUSD",
        timeframe="5m",
        feature_ids=[1, 2, 3, 4, 5],
        prediction_size=5,
        predictions=predictions,
        hashed_predictions="abc",
        hash_verified=hash_verified,
        incentive_score=0.5,
    )


async def test_collect_window_calls_adapter_twice():
    from integrations.bittensor.scheduler import TaoshiScheduler

    mock_adapter = MagicMock()
    mock_adapter.metagraph = MagicMock()
    mock_adapter.metagraph.uids = [0, 1]
    mock_adapter.metagraph.axons = [MagicMock(), MagicMock()]
    mock_adapter.metagraph.I = [0.5, 0.8]
    mock_adapter.refresh_metagraph = AsyncMock()
    mock_adapter.build_request = MagicMock(return_value=MagicMock())

    hash_forecasts = [_make_forecast("hk1", [100, 101, 102, 103, 104])]
    forward_forecasts = [_make_forecast("hk1", [100, 101, 102, 103, 104])]
    mock_adapter.query_miners = AsyncMock(
        side_effect=[hash_forecasts, forward_forecasts]
    )
    mock_adapter.verify_hash_commitment = MagicMock(return_value=True)
    mock_adapter.parse_stream_id = MagicMock(return_value=("BTCUSD", "5m"))

    mock_store = MagicMock()
    mock_store.save_raw_forecasts = AsyncMock()
    mock_store.save_derived_view = AsyncMock()

    mock_event_bus = MagicMock()
    mock_event_bus.publish = AsyncMock()

    scheduler = TaoshiScheduler(
        adapter=mock_adapter,
        store=mock_store,
        event_bus=mock_event_bus,
        selection_policy="all",
    )

    with patch(
        "integrations.bittensor.scheduler.asyncio.sleep", new_callable=AsyncMock
    ):
        await scheduler._collect_window()

    assert mock_adapter.query_miners.call_count == 2
    mock_store.save_raw_forecasts.assert_called_once()
    mock_store.save_derived_view.assert_called_once()


async def test_collect_window_updates_counters():
    from integrations.bittensor.scheduler import TaoshiScheduler

    mock_adapter = MagicMock()
    mock_adapter.metagraph = MagicMock()
    mock_adapter.metagraph.uids = [0]
    mock_adapter.metagraph.axons = [MagicMock()]
    mock_adapter.metagraph.I = [0.5]
    mock_adapter.refresh_metagraph = AsyncMock()
    mock_adapter.build_request = MagicMock(return_value=MagicMock())
    mock_adapter.query_miners = AsyncMock(
        return_value=[_make_forecast("hk1", [100, 101, 102, 103, 104])]
    )
    mock_adapter.verify_hash_commitment = MagicMock(return_value=True)
    mock_adapter.parse_stream_id = MagicMock(return_value=("BTCUSD", "5m"))

    mock_store = MagicMock()
    mock_store.save_raw_forecasts = AsyncMock()
    mock_store.save_derived_view = AsyncMock()

    mock_event_bus = MagicMock()
    mock_event_bus.publish = AsyncMock()

    scheduler = TaoshiScheduler(
        adapter=mock_adapter,
        store=mock_store,
        event_bus=mock_event_bus,
        selection_policy="all",
    )

    with patch(
        "integrations.bittensor.scheduler.asyncio.sleep", new_callable=AsyncMock
    ):
        await scheduler._collect_window()

    assert scheduler.windows_collected_total == 1
    assert scheduler.last_success_at is not None
    assert scheduler.last_window_miner_count == 1
    assert scheduler.last_window_responder_count >= 1
