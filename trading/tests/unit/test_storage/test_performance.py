from datetime import datetime, timezone
from decimal import Decimal
import aiosqlite
import pytest

from storage.db import init_db
from storage.performance import PerformanceSnapshot, PerformanceStore


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield PerformanceStore(db)
    await db.close()


def _base_snapshot(**kwargs) -> PerformanceSnapshot:
    defaults = dict(
        agent_name="test-agent",
        timestamp=datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc),
        opportunities_generated=10,
        opportunities_executed=7,
        win_rate=0.71,
    )
    defaults.update(kwargs)
    return PerformanceSnapshot(**defaults)


class TestPerformanceStore:
    async def test_save_enhanced_snapshot(self, store):
        snapshot = _base_snapshot(
            total_pnl=Decimal("1250.50"),
            daily_pnl=Decimal("320.75"),
            daily_pnl_pct=2.5,
            sharpe_ratio=1.8,
            max_drawdown=0.05,
            avg_win=Decimal("450.00"),
            avg_loss=Decimal("150.00"),
            profit_factor=3.0,
            total_trades=20,
            open_positions=3,
        )
        await store.save(snapshot)
        result = await store.get_latest("test-agent")
        assert result is not None
        assert result.total_pnl == Decimal("1250.50")
        assert result.daily_pnl == Decimal("320.75")
        assert result.daily_pnl_pct == 2.5
        assert result.sharpe_ratio == 1.8
        assert result.max_drawdown == 0.05
        assert result.avg_win == Decimal("450.00")
        assert result.avg_loss == Decimal("150.00")
        assert result.profit_factor == 3.0
        assert result.total_trades == 20
        assert result.open_positions == 3

    async def test_snapshot_defaults_for_new_fields(self, store):
        snapshot = _base_snapshot()
        await store.save(snapshot)
        result = await store.get_latest("test-agent")
        assert result is not None
        assert result.total_pnl == Decimal("0")
        assert result.daily_pnl == Decimal("0")
        assert result.daily_pnl_pct == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.max_drawdown == 0.0
        assert result.avg_win == Decimal("0")
        assert result.avg_loss == Decimal("0")
        assert result.profit_factor == 0.0
        assert result.total_trades == 0
        assert result.open_positions == 0
