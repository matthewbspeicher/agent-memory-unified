"""Integration tests for Portfolio Kill Switch with DB persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import aiosqlite
import pytest

from broker.models import AccountBalance, OrderBase, Quote, Symbol
from risk.rules import PortfolioContext, PortfolioDrawdownKillSwitch
from storage.portfolio_state import PortfolioState, PortfolioStateStore


@pytest.fixture
async def db_with_state_store():
    """Create in-memory DB with portfolio_state table."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_state (
            key TEXT PRIMARY KEY,
            high_water_mark TEXT NOT NULL DEFAULT '0',
            triggered INTEGER NOT NULL DEFAULT 0,
            triggered_at TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    await db.commit()
    store = PortfolioStateStore(db)
    await store.initialize()
    yield db, store
    await db.close()


@pytest.fixture
def sample_trade():
    return OrderBase(
        symbol=Symbol(ticker="SPY", asset_type="STOCK"),
        quantity=Decimal("10"),
        side="BUY",
        account_id="test_account",
    )


@pytest.fixture
def sample_quote():
    return Quote(
        symbol=Symbol(ticker="SPY", asset_type="STOCK"),
        last=Decimal("450.00"),
        bid=Decimal("449.90"),
        ask=Decimal("450.10"),
    )


class TestPortfolioKillSwitchIntegration:
    """Integration tests for the full portfolio kill switch flow."""

    @pytest.mark.asyncio
    async def test_full_flow_no_drawdown(
        self, db_with_state_store, sample_trade, sample_quote
    ):
        """Test that trades pass when no drawdown exists."""
        db, store = db_with_state_store

        rule = PortfolioDrawdownKillSwitch(
            max_drawdown_pct=25.0,
            state_store=store,
        )

        ctx = PortfolioContext(
            positions=[],
            balance=AccountBalance(
                account_id="test_account",
                net_liquidation=Decimal("100000"),
                buying_power=Decimal("200000"),
                cash=Decimal("50000"),
                maintenance_margin=Decimal("0"),
            ),
        )

        result = await rule.async_evaluate(sample_trade, sample_quote, ctx)
        assert result.passed is True

        # Verify HWM was persisted
        state = await store.get_state("portfolio_drawdown")
        assert state is not None
        assert state.high_water_mark == Decimal("100000")
        assert state.triggered is False

    @pytest.mark.asyncio
    async def test_full_flow_triggers_on_drawdown(
        self, db_with_state_store, sample_trade, sample_quote
    ):
        """Test that trades are blocked when drawdown exceeds threshold."""
        db, store = db_with_state_store

        # Pre-populate with HWM of 100k
        await store.save_state(
            PortfolioState(
                high_water_mark=Decimal("100000"),
                triggered=False,
                triggered_at=None,
                updated_at=datetime.now(timezone.utc),
            ),
            key="portfolio_drawdown",
        )

        rule = PortfolioDrawdownKillSwitch(
            max_drawdown_pct=25.0,
            state_store=store,
        )

        # Current value is 70k = 30% drawdown
        ctx = PortfolioContext(
            positions=[],
            balance=AccountBalance(
                account_id="test_account",
                net_liquidation=Decimal("70000"),
                buying_power=Decimal("140000"),
                cash=Decimal("30000"),
                maintenance_margin=Decimal("0"),
            ),
        )

        result = await rule.async_evaluate(sample_trade, sample_quote, ctx)
        assert result.passed is False
        assert "drawdown" in result.reason.lower()

        # Verify triggered state was persisted
        state = await store.get_state("portfolio_drawdown")
        assert state is not None
        assert state.triggered is True
        assert state.triggered_at is not None

    @pytest.mark.asyncio
    async def test_cooldown_prevents_retrigger(
        self, db_with_state_store, sample_trade, sample_quote
    ):
        """Test that cooldown prevents immediate re-triggering."""
        db, store = db_with_state_store

        # Pre-set triggered state with recent trigger time
        await store.save_state(
            PortfolioState(
                high_water_mark=Decimal("100000"),
                triggered=True,
                triggered_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
            key="portfolio_drawdown",
        )

        rule = PortfolioDrawdownKillSwitch(
            max_drawdown_pct=25.0,
            cooldown_hours=24,
            state_store=store,
        )

        ctx = PortfolioContext(
            positions=[],
            balance=AccountBalance(
                account_id="test_account",
                net_liquidation=Decimal("70000"),
                buying_power=Decimal("140000"),
                cash=Decimal("30000"),
                maintenance_margin=Decimal("0"),
            ),
        )

        result = await rule.async_evaluate(sample_trade, sample_quote, ctx)
        assert result.passed is False
        assert "cooldown" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_hwm_updates_on_new_high(
        self, db_with_state_store, sample_trade, sample_quote
    ):
        """Test that HWM updates when portfolio reaches new high."""
        db, store = db_with_state_store

        # Start with HWM of 100k
        await store.save_state(
            PortfolioState(
                high_water_mark=Decimal("100000"),
                triggered=False,
                triggered_at=None,
                updated_at=datetime.now(timezone.utc),
            ),
            key="portfolio_drawdown",
        )

        rule = PortfolioDrawdownKillSwitch(
            max_drawdown_pct=25.0,
            state_store=store,
        )

        # Current value is 120k (new high)
        ctx = PortfolioContext(
            positions=[],
            balance=AccountBalance(
                account_id="test_account",
                net_liquidation=Decimal("120000"),
                buying_power=Decimal("240000"),
                cash=Decimal("60000"),
                maintenance_margin=Decimal("0"),
            ),
        )

        result = await rule.async_evaluate(sample_trade, sample_quote, ctx)
        assert result.passed is True

        # Verify HWM was updated
        state = await store.get_state("portfolio_drawdown")
        assert state is not None
        assert state.high_water_mark == Decimal("120000")
