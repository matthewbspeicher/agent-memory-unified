"""Tests for PortfolioDrawdownKillSwitch and PortfolioStateStore."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from broker.models import AccountBalance, OrderBase, Quote, Symbol
from risk.rules import PortfolioContext, PortfolioDrawdownKillSwitch, RiskResult
from storage.portfolio_state import PortfolioState, PortfolioStateStore


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


@pytest.fixture
def sample_ctx():
    return PortfolioContext(
        positions=[],
        balance=AccountBalance(
            account_id="test_account",
            net_liquidation=Decimal("100000"),
            buying_power=Decimal("200000"),
            cash=Decimal("50000"),
            maintenance_margin=Decimal("0"),
        ),
    )


@pytest.fixture
def ctx_with_drawdown():
    """Context simulating 30% drawdown from 100k HWM."""
    return PortfolioContext(
        positions=[],
        balance=AccountBalance(
            account_id="test_account",
            net_liquidation=Decimal("70000"),  # 30% down from 100k
            buying_power=Decimal("140000"),
            cash=Decimal("30000"),
            maintenance_margin=Decimal("0"),
        ),
    )


class TestPortfolioStateStore:
    @pytest.mark.asyncio
    async def test_initialize_creates_table(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()

        # Verify table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='portfolio_state'"
        )
        row = await cursor.fetchone()
        assert row is not None
        await db.close()

    @pytest.mark.asyncio
    async def test_save_and_get_state(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()

        state = PortfolioState(
            high_water_mark=Decimal("100000"),
            triggered=False,
            triggered_at=None,
            updated_at=datetime.now(timezone.utc),
        )
        await store.save_state(state, key="test_key")

        retrieved = await store.get_state("test_key")
        assert retrieved is not None
        assert retrieved.high_water_mark == Decimal("100000")
        assert retrieved.triggered is False
        await db.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent_state_returns_none(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()

        result = await store.get_state("nonexistent")
        assert result is None
        await db.close()

    @pytest.mark.asyncio
    async def test_update_hwm(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()

        await store.update_hwm(Decimal("150000"), key="test_key")
        state = await store.get_state("test_key")
        assert state is not None
        assert state.high_water_mark == Decimal("150000")
        await db.close()

    @pytest.mark.asyncio
    async def test_set_triggered(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()

        await store.set_triggered(True, key="test_key")
        state = await store.get_state("test_key")
        assert state is not None
        assert state.triggered is True
        assert state.triggered_at is not None
        await db.close()

    @pytest.mark.asyncio
    async def test_reset(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()

        await store.set_triggered(True, key="test_key")
        await store.reset("test_key")
        state = await store.get_state("test_key")
        assert state is not None
        assert state.triggered is False
        assert state.high_water_mark == Decimal("0")
        await db.close()


class TestPortfolioDrawdownKillSwitch:
    @pytest.mark.asyncio
    async def test_passes_when_no_drawdown(
        self, sample_trade, sample_quote, sample_ctx
    ):
        rule = PortfolioDrawdownKillSwitch(max_drawdown_pct=25.0)
        result = await rule.async_evaluate(sample_trade, sample_quote, sample_ctx)
        assert result.passed is True
        assert result.rule_name == "portfolio_drawdown_kill"

    @pytest.mark.asyncio
    async def test_blocks_when_drawdown_exceeds_threshold(
        self, sample_trade, sample_quote, ctx_with_drawdown, tmp_path
    ):
        db_path = tmp_path / "test.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()

        # Pre-populate with HWM of 100k (current value is 70k = 30% drawdown)
        await store.save_state(
            PortfolioState(
                high_water_mark=Decimal("100000"),
                triggered=False,
                triggered_at=None,
                updated_at=datetime.now(timezone.utc),
            ),
            key="portfolio_drawdown",
        )

        rule = PortfolioDrawdownKillSwitch(max_drawdown_pct=25.0, state_store=store)
        result = await rule.async_evaluate(
            sample_trade, sample_quote, ctx_with_drawdown
        )
        assert result.passed is False
        assert "drawdown" in result.reason.lower()
        await db.close()

    @pytest.mark.asyncio
    async def test_persists_hwm_to_state_store(
        self, sample_trade, sample_quote, sample_ctx, tmp_path
    ):
        db_path = tmp_path / "test.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()

        rule = PortfolioDrawdownKillSwitch(max_drawdown_pct=25.0, state_store=store)
        await rule.async_evaluate(sample_trade, sample_quote, sample_ctx)

        state = await store.get_state("portfolio_drawdown")
        assert state is not None
        assert state.high_water_mark == Decimal("100000")
        await db.close()

    @pytest.mark.asyncio
    async def test_cooldown_prevents_retrigger(
        self, sample_trade, sample_quote, ctx_with_drawdown, tmp_path
    ):
        db_path = tmp_path / "test.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()

        # Pre-set triggered state
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
            max_drawdown_pct=25.0, cooldown_hours=24, state_store=store
        )
        result = await rule.async_evaluate(
            sample_trade, sample_quote, ctx_with_drawdown
        )
        assert result.passed is False
        assert "cooldown" in result.reason.lower()
        await db.close()

    @pytest.mark.asyncio
    async def test_cooldown_expires_after_timeout(
        self, sample_trade, sample_quote, ctx_with_drawdown, tmp_path
    ):
        db_path = tmp_path / "test.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()

        # Pre-set triggered state with expired cooldown
        await store.save_state(
            PortfolioState(
                high_water_mark=Decimal("100000"),
                triggered=True,
                triggered_at=datetime.now(timezone.utc) - timedelta(hours=25),
                updated_at=datetime.now(timezone.utc),
            ),
            key="portfolio_drawdown",
        )

        rule = PortfolioDrawdownKillSwitch(
            max_drawdown_pct=25.0, cooldown_hours=24, state_store=store
        )
        # After cooldown expires, should re-evaluate and trigger again (still in drawdown)
        result = await rule.async_evaluate(
            sample_trade, sample_quote, ctx_with_drawdown
        )
        assert result.passed is False  # Still in drawdown, so triggers again
        await db.close()

    def test_sync_evaluate_returns_pass(self, sample_trade, sample_quote, sample_ctx):
        rule = PortfolioDrawdownKillSwitch(max_drawdown_pct=25.0)
        result = rule.evaluate(sample_trade, sample_quote, sample_ctx)
        assert result.passed is True
        assert "async_evaluate" in result.reason


class TestPortfolioDrawdownBoundaries:
    """Boundary tests that catch off-by-one regressions on the drawdown threshold."""

    @pytest.mark.asyncio
    async def test_exact_threshold_trips(self, sample_trade, sample_quote, tmp_path):
        """25.0% drawdown at max_drawdown_pct=25.0 must trip (>= contract)."""
        db_path = tmp_path / "exact.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()
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
            max_drawdown_pct=25.0, state_store=store
        )
        # Exactly 25% drawdown: 100k → 75k
        ctx = PortfolioContext(
            positions=[],
            balance=AccountBalance(
                account_id="test_account",
                net_liquidation=Decimal("75000"),
                buying_power=Decimal("150000"),
                cash=Decimal("30000"),
                maintenance_margin=Decimal("0"),
            ),
        )
        result = await rule.async_evaluate(sample_trade, sample_quote, ctx)
        assert result.passed is False, (
            "25.0% drawdown must trip the kill switch at max_drawdown_pct=25.0"
        )
        await db.close()

    @pytest.mark.asyncio
    async def test_just_below_threshold_passes(
        self, sample_trade, sample_quote, tmp_path
    ):
        """24.9% drawdown must NOT trip — catches `>=` → `>` regression."""
        db_path = tmp_path / "just_below.db"
        db = await aiosqlite.connect(str(db_path))
        store = PortfolioStateStore(db)
        await store.initialize()
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
            max_drawdown_pct=25.0, state_store=store
        )
        # 24.9% drawdown: 100k → 75100
        ctx = PortfolioContext(
            positions=[],
            balance=AccountBalance(
                account_id="test_account",
                net_liquidation=Decimal("75100"),
                buying_power=Decimal("150200"),
                cash=Decimal("30000"),
                maintenance_margin=Decimal("0"),
            ),
        )
        result = await rule.async_evaluate(sample_trade, sample_quote, ctx)
        assert result.passed is True, (
            "24.9% drawdown tripped at max_drawdown_pct=25.0 — off-by-one regression"
        )
        await db.close()
