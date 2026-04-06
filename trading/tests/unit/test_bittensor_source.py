from __future__ import annotations
from datetime import datetime, timedelta

import aiosqlite
import pytest

from data.bittensor_source import BittensorDataSource
from integrations.bittensor.models import DerivedBittensorView
from storage.bittensor import BittensorStore
from storage.db import init_db


@pytest.fixture
async def source():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    store = BittensorStore(db)
    ds = BittensorDataSource(store)
    yield ds
    await db.close()


async def test_get_latest_signal_returns_none_when_empty(source: BittensorDataSource):
    result = await source.get_latest_signal("BTCUSD", "5m")
    assert result is None


async def test_get_latest_signal_returns_stored_view(source: BittensorDataSource):
    view = DerivedBittensorView(
        symbol="BTCUSD",
        timeframe="5m",
        window_id="w1",
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
    await source._store.save_derived_view(view)
    result = await source.get_latest_signal("BTCUSD", "5m")
    assert result is not None
    assert result.window_id == "w1"


async def test_get_signal_history(source: BittensorDataSource):
    for i, wid in enumerate(["w1", "w2", "w3"]):
        view = DerivedBittensorView(
            symbol="BTCUSD",
            timeframe="5m",
            window_id=wid,
            timestamp=datetime(2026, 3, 28, 12, 0) + timedelta(hours=i),
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
        await source._store.save_derived_view(view)
    history = await source.get_signal_history("BTCUSD", "5m", hours=24)
    assert len(history) == 3
