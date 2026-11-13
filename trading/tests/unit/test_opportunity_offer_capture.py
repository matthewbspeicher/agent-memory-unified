"""Capture exposes evidence in order; caller policy still decides its use."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from storage.opportunities import OpportunityStore, REVISION_KEY


@pytest.fixture
def store():
    return OpportunityStore(SimpleNamespace(execute=AsyncMock()))


@pytest.mark.asyncio
async def test_capture_preserves_two_observations_and_never_writes(store):
    calls = []
    offered_at = datetime.now(timezone.utc)
    opportunity = SimpleNamespace(data={REVISION_KEY: "replacement"})

    async def identity(oid):
        calls.append(("identity", oid))
        return "shown", offered_at

    async def load(oid):
        calls.append(("load", oid))
        return opportunity

    store.offer_identity = AsyncMock(side_effect=identity)
    store.load = AsyncMock(side_effect=load)
    capture = await store.capture_offer("offered-id")
    assert calls == [("identity", "offered-id"), ("load", "offered-id")]
    assert capture.opportunity is opportunity
    assert capture.offered_at is offered_at
    assert capture.offered_revision == "shown"
    assert capture.saved_revision == "replacement"
    store._db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["identity", "load"])
async def test_capture_propagates_read_errors_without_retry(store, stage):
    error = ConnectionError("read unavailable")
    store.offer_identity = AsyncMock(return_value=(None, None))
    store.load = AsyncMock(return_value=None)
    method = store.offer_identity if stage == "identity" else store.load
    method.side_effect = error
    with pytest.raises(ConnectionError) as raised:
        await store.capture_offer("id")
    assert raised.value is error
    store.offer_identity.assert_awaited_once_with("id")
    if stage == "identity":
        store.load.assert_not_awaited()
    else:
        store.load.assert_awaited_once_with("id")
    store._db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_capture_does_not_preempt_the_callers_revision_validation_point(store):
    class UnreadableRevision(dict):
        def get(self, key, *args):
            raise ValueError("revision should only be read after earlier guards")

    store.offer_identity = AsyncMock(return_value=(None, None))
    store.load = AsyncMock(return_value=SimpleNamespace(data=UnreadableRevision()))
    capture = await store.capture_offer("id")
    assert capture.opportunity is not None
    assert capture.offered_at is None
    with pytest.raises(ValueError, match="earlier guards"):
        _ = capture.saved_revision
