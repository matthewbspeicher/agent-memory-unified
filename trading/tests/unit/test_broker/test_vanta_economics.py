import pytest
import aiosqlite
from decimal import Decimal
from broker.models import Position, Symbol, AssetType
from broker.paper import PaperAccountProvider
from storage.paper import PaperStore

@pytest.fixture
async def paper_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    store = PaperStore(db)
    await store.init_tables()
    # Provide initial balance to paper account
    await db.execute(
        """
        INSERT OR REPLACE INTO paper_accounts
            (account_id, net_liquidation, buying_power, cash, maintenance_margin)
        VALUES ('PAPER', 10000.0, 10000.0, 10000.0, 0.0)
        """
    )
    await db.commit()
    yield store
    await db.close()

@pytest.mark.asyncio
async def test_carry_fee_deduction(paper_store):
    # Setup mock account with $10k
    store = paper_store
    account = PaperAccountProvider(store)
    # Mock position held overnight
    pos = Position(
        symbol=Symbol(ticker="BTCUSD", asset_type=AssetType.CRYPTO),
        quantity=Decimal("1.0"),
        avg_cost=Decimal("50000"),
        market_value=Decimal("50000"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0")
    )
    # Trigger daily carry fee (e.g., 0.01% per day)
    fee_applied = await account.apply_carry_fees([pos])
    assert fee_applied == Decimal("5.0") # 50000 * 0.0001
