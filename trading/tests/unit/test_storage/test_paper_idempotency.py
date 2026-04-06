"""Test PaperStore.record_binary_resolution() idempotency."""

from __future__ import annotations

import pytest
from decimal import Decimal
from broker.models import Symbol, AssetType, OrderSide


@pytest.fixture
async def paper_store(tmp_path):
    import aiosqlite

    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        from storage.paper import PaperStore

        store = PaperStore(db)
        await store.init_tables()
        yield store, db


@pytest.mark.asyncio
async def test_record_binary_resolution_idempotent(paper_store):
    store, db = paper_store
    sym = Symbol(ticker="KXBTCD-25MAR28", asset_type=AssetType.PREDICTION)

    # Seed a position
    await store.record_fill(
        account_id="KALSHI_PAPER",
        symbol=sym,
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        fill_price=Decimal("0.60"),
    )

    # First resolution
    await store.record_binary_resolution(
        account_id="KALSHI_PAPER",
        symbol=sym,
        quantity=Decimal("10"),
        entry_price=Decimal("0.60"),
        resolution="YES",
    )

    balance_after_first = await store.get_balance("KALSHI_PAPER")
    cash_after_first = balance_after_first.cash

    # Second resolution call — should be a no-op
    await store.record_binary_resolution(
        account_id="KALSHI_PAPER",
        symbol=sym,
        quantity=Decimal("10"),
        entry_price=Decimal("0.60"),
        resolution="YES",
    )

    balance_after_second = await store.get_balance("KALSHI_PAPER")
    assert balance_after_second.cash == cash_after_first
