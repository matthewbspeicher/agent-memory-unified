"""Paper startup remains readable on unsupported storage, without execution admission."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from api.startup.brokers import setup_brokers
from config import Config, BrokerConfig
from storage.paper import PaperStore


def config():
    return Config(paper_trading=True, worker_mode=True, broker=BrokerConfig(ib_host=""))


async def test_unsupported_paper_backend_keeps_startup_but_denies_risk_context(
    monkeypatch, caplog
):
    import storage.paper

    database = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    store = PaperStore(database)
    store.init_tables = AsyncMock()
    store.ensure_account = AsyncMock(
        side_effect=AssertionError("unsupported account initialization")
    )
    monkeypatch.setattr(storage.paper, "PaperStore", lambda db: store)
    primary, brokers, result_store = await setup_brokers(config(), database, None)
    assert primary is None and brokers == {} and result_store is store
    store.ensure_account.assert_not_awaited()
    assert "Paper execution unavailable" in caplog.text
    with pytest.raises(ValueError, match="supported transactional"):
        await store.get_risk_state("PAPER", None)
    await store.close()


async def test_new_sqlite_primary_and_prediction_accounts_have_coverage(tmp_path):
    async with aiosqlite.connect(tmp_path / "startup.db") as database:
        database.row_factory = aiosqlite.Row
        _, _, store = await setup_brokers(config(), database, None)
        try:
            assert await store._get_db() is not database
            for account in ("PAPER", "KALSHI_PAPER", "POLYMARKET_PAPER"):
                snapshot = await store.get_risk_state(account, None)
                assert snapshot.complete
                assert snapshot.epoch
                assert snapshot.context.daily_pnl == 0
                assert snapshot.context.daily_trade_count == 0
        finally:
            await store.close()
