"""Behavioral regressions for ownership, expiry, and trading recovery.

All storage is temporary; no broker or network service is contacted.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import httpx
import pytest

from storage.memory import LocalMemoryStore
from risk.engine import RiskEngine
from risk.kill_switch import KillSwitch


from tests.execution_controls import AdmissionLuaDouble


class ControlStore(AdmissionLuaDouble):
    def __init__(self):
        self.values = {"kill_switch:active": "false"}
        self.fail = False

    async def get(self, key):
        if self.fail:
            raise ConnectionError("offline")
        return self.values.get(key)

    async def set(self, key, value, nx=False):
        if self.fail:
            raise ConnectionError("offline")
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def setex(self, key, seconds, value):
        await self.set(key, value)

    async def getdel(self, key):
        if self.fail:
            raise ConnectionError("offline")
        return self.values.pop(key, None)

    async def delete(self, key):
        self.values.pop(key, None)


@pytest.fixture
async def memory(tmp_path):
    store = LocalMemoryStore(str(tmp_path / "memory.db"))
    await store.connect()
    try:
        yield store
    finally:
        await store.close()


async def test_private_dedup_is_scoped_and_survives_reopen(memory):
    alice = await memory.store("same fact", agent_id="alice")
    bob = await memory.store("same fact", agent_id="bob")
    public = await memory.store("same fact", agent_id="alice", visibility="public")
    assert len({alice["id"], bob["id"], public["id"]}) == 3
    repeat = await memory.store("same fact", agent_id="alice")
    assert repeat["id"] == alice["id"]
    assert repeat["created_at"] == alice["created_at"]
    await memory.close()
    await memory.connect()
    assert [r["id"] for r in await memory.search("same", agent_id="bob")] == [bob["id"]]
    assert (
        await memory.search("same") == []
    )  # omitted identity cannot read other owners
    assert await memory.check_duplicate("same fact") is None
    assert (await memory.check_duplicate("same fact", agent_id="bob")).id == bob["id"]


async def test_ttl_expiry_and_no_refresh_on_duplicate(memory):
    before = datetime.now(timezone.utc)
    record = await memory.store("expires", ttl="1h")
    expiry = datetime.fromisoformat(record["expires_at"])
    assert (
        before + timedelta(hours=1)
        <= expiry
        <= datetime.now(timezone.utc) + timedelta(hours=1)
    )
    assert len(await memory.search("expires")) == 1
    await memory._db.execute(
        "UPDATE memories SET expires_at = ?",
        ((before - timedelta(seconds=1)).isoformat(),),
    )
    await memory._db.commit()
    repeat = await memory.store("expires", ttl="90d")
    assert repeat["id"] == record["id"]
    assert await memory.search("expires") == []
    assert await memory.list() == []
    assert len(await memory.list(include_inactive=True)) == 1


@pytest.mark.parametrize(
    "status", ["pending", "cancelled", "outdated", "conflicted", "archived", "deleted"]
)
async def test_inactive_memories_stay_out_of_prompts(memory, status):
    record = await memory.store("obsolete fact", status=status)
    assert await memory.search("obsolete") == []
    assert await memory.list() == []
    assert (
        len(
            await memory.search("obsolete", include_inactive=True, status_filter=status)
        )
        == 1
    )
    await memory.store("obsolete fact")
    assert (await memory.get(record["id"])).status == status
    assert await memory.search("obsolete") == []


async def test_exact_tag_filter_precedes_limit(memory):
    wanted = await memory.store("wanted", tags=["risk", "daily"])
    await memory.store("newer", tags=["riskier", "daily"])
    assert [r.id for r in await memory.list(tags=["risk", "daily"], limit=1)] == [
        wanted["id"]
    ]
    assert await memory.list(tags=["missing"]) == []


@pytest.mark.parametrize("ttl", ["0d", "-1d", "forever", "1.5d", "", "10"])
async def test_invalid_ttl_is_rejected(memory, ttl):
    with pytest.raises(ValueError, match="ttl"):
        await memory.store("bad ttl", ttl=ttl)
    assert await memory.list(include_inactive=True) == []


async def test_legacy_global_index_is_replaced_without_data_loss(memory):
    original = await memory.store(
        "old record", agent_id="alice", metadata={"source": "receipt"}
    )
    await memory._db.execute("DROP INDEX idx_memories_scoped_content")
    await memory._db.execute(
        "CREATE UNIQUE INDEX idx_memories_content_hash ON memories(content_hash)"
    )
    await memory._db.commit()
    await memory.close()
    await memory.connect()
    second = await memory.store("old record", agent_id="bob")
    assert second["id"] != original["id"]
    assert (await memory.get(original["id"])).metadata == {"source": "receipt"}


async def test_hybrid_fallback_keeps_owner_and_expiry(memory):
    from learning.memory_client import HybridTradingMemoryClient, TradingMemoryClient

    private, shared = AsyncMock(), AsyncMock()
    private.store.side_effect = shared.store.side_effect = ConnectionError("offline")
    private.search.side_effect = shared.search_commons.side_effect = ConnectionError(
        "offline"
    )
    remote = TradingMemoryClient(private, shared)
    with pytest.raises(ValueError, match="agent_id"):
        HybridTradingMemoryClient(remote, memory)
    alice = HybridTradingMemoryClient(remote, memory, agent_id="alice")
    bob = HybridTradingMemoryClient(remote, memory, agent_id="bob")
    record = await alice.store_private("private-only")
    assert (await memory.get(record["id"])).agent_id == "alice"
    assert record["expires_at"] is not None
    assert await bob.search_both("private-only") == []
    assert len(await alice.search_both("private-only")) == 1
    health = await alice.health_check()
    assert health["remote"]["healthy"] is False
    assert health["using"] == "local"


async def test_halt_resume_restart_and_failed_persistence():
    store = ControlStore()
    engine = RiskEngine([], KillSwitch())
    engine.bind_control_store(store)
    broker = SimpleNamespace(orders=SimpleNamespace(cancel_all_orders=AsyncMock()))
    engine.register_brokers({"paper": broker})
    await engine.trigger_kill_switch("test")
    broker.orders.cancel_all_orders.assert_awaited_once()
    restored = RiskEngine([], KillSwitch())
    restored.bind_control_store(store)
    await restored.initialize_control()
    assert restored.check_kill_active()
    store.fail = True
    with pytest.raises(ConnectionError):
        await restored.set_halted(False)
    assert restored.check_kill_active()
    store.fail = False
    await restored.set_halted(False)
    await engine.sync_halt()
    assert not engine.check_kill_active()
    assert not restored.check_kill_active()


async def test_halt_cancellation_failure_is_reported():
    engine = RiskEngine([], KillSwitch())
    engine.register_brokers(
        {
            "paper": SimpleNamespace(
                orders=SimpleNamespace(
                    cancel_all_orders=AsyncMock(side_effect=RuntimeError("failed"))
                )
            )
        }
    )
    assert await engine.trigger_kill_switch("test") == ["paper"]
    assert engine.check_kill_active()


async def test_confirmation_halt_allows_cancel_and_rejects_new_orders():
    from api.app import create_app
    from config import Config
    from broker.models import OrderResult, OrderStatus

    broker = SimpleNamespace(
        orders=SimpleNamespace(
            cancel_all_orders=AsyncMock(),
            cancel_order=AsyncMock(
                return_value=OrderResult(
                    order_id="paper-1", status=OrderStatus.CANCELLED
                )
            ),
            place_order=AsyncMock(),
        )
    )
    app = create_app(
        broker, config=Config(api_key="test-key", rate_limit_enabled=False)
    )
    app.state.redis = ControlStore()
    headers = {"X-API-Key": "test-key"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test", headers=headers
    ) as client:
        initiated = await client.post(
            "/risk/kill-switch/initiate", json={"enabled": True, "reason": "test"}
        )
        assert initiated.status_code == 200
        token = initiated.json()["confirmation_token"]
        assert (
            await client.post("/risk/kill-switch/confirm", params={"token": token})
        ).status_code == 200
        assert (
            await client.post("/risk/kill-switch/confirm", params={"token": token})
        ).status_code == 400
        broker.orders.cancel_all_orders.assert_awaited_once()
        order = {
            "symbol": {"ticker": "AAPL"},
            "side": "BUY",
            "quantity": "1",
            "account_id": "PAPER",
            "order_type": "market",
        }
        assert (await client.post("/orders", json=order)).status_code == 503
        assert (await client.delete("/orders/paper-1")).status_code == 200
        app.state.redis.fail = True
        assert (await client.delete("/orders/paper-1")).status_code == 200
        assert (await client.post("/orders", json=order)).status_code == 503
        broker.orders.place_order.assert_not_awaited()
        assert (
            await client.delete("/orders/paper-1", headers={"X-API-Key": "wrong"})
        ).status_code == 403


async def test_paper_startup_preserves_existing_state():
    from api.startup.brokers import setup_brokers
    from config import Config, BrokerConfig

    config = Config(
        paper_trading=True, worker_mode=True, broker=BrokerConfig(ib_host="")
    )
    async with aiosqlite.connect(":memory:") as db:
        db.row_factory = aiosqlite.Row
        await setup_brokers(config, db, None)
        await db.execute(
            "UPDATE paper_accounts SET cash=12345, net_liquidation=12500, buying_power=1000, maintenance_margin=50 WHERE account_id='PAPER'"
        )
        await db.execute(
            "INSERT INTO paper_positions (account_id, symbol, asset_type, quantity, avg_cost) VALUES ('PAPER', 'TEST', 'STOCK', 2, 100)"
        )
        await db.execute(
            "INSERT INTO paper_orders (order_id, account_id, symbol, side, quantity, status, filled_quantity) VALUES ('kept', 'PAPER', 'TEST', 'BUY', 2, 'FILLED', 2)"
        )
        await db.commit()
        await setup_brokers(config, db, None)
        position = await (
            await db.execute(
                "SELECT quantity, avg_cost FROM paper_positions WHERE account_id='PAPER'"
            )
        ).fetchone()
        order = await (
            await db.execute(
                "SELECT order_id, status FROM paper_orders WHERE account_id='PAPER'"
            )
        ).fetchone()
        assert tuple(position) == (2, 100)
        assert tuple(order) == ("kept", "FILLED")
        row = await (
            await db.execute("SELECT * FROM paper_accounts WHERE account_id='PAPER'")
        ).fetchone()
        assert [
            row[k]
            for k in ("cash", "net_liquidation", "buying_power", "maintenance_margin")
        ] == [12345, 12500, 1000, 50]


@pytest.mark.parametrize(
    "exit_price,expected_win_rate,expected_equity", [(90, 0, 9800), (110, 1, 10200)]
)
def test_synthetic_metrics_use_closed_trade_profit(
    monkeypatch, exit_price, expected_win_rate, expected_equity
):
    from backtest import engine

    bars = [
        {"date": "2026-01-01", "price": 100},
        {"date": "2026-01-02", "price": exit_price},
    ]
    monkeypatch.setattr(engine, "_generate_historical_data", lambda symbol, days: bars)
    actions = iter([("BUY", 90), ("SELL", 90)])
    monkeypatch.setattr(engine, "_calculate_signal", lambda *args: next(actions))
    result = engine.run_backtest(symbols=["TEST"], days=2, initial_capital=10000)
    assert result["equity_curve"][0]["equity"] == 10000
    assert result["final_value"] == expected_equity
    assert result["win_rate"] == expected_win_rate
    assert result["closed_trades"] == 1
    assert result["status"] == "synthetic"
    assert result["deployment_eligible"] is False
    assert result["strategy_evaluated"] is False


@pytest.mark.parametrize(
    "results",
    [{"status": "real", "sharpe_ratio": 5}, {"status": "synthetic", "sharpe_ratio": 5}],
)
async def test_unverified_draft_cannot_write_agent_config(
    monkeypatch, tmp_path, results
):
    from api.app import create_app
    from api.routes import drafts
    from config import Config

    target = tmp_path / "agents.yaml"
    target.write_text("agents: []\n")
    monkeypatch.setattr(drafts, "_AGENTS_YAML", target)
    app = create_app(config=Config(api_key="test-key", rate_limit_enabled=False))
    store = AsyncMock()
    store.get_draft.return_value = {
        "status": "tested",
        "backtest_results": results,
        "name": "Audit",
    }
    app.state.identity_store = store
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/drafts/audit/deploy", headers={"X-API-Key": "test-key"}
        )
    assert response.status_code == 409
    assert target.read_text() == "agents: []\n"
    store.update_draft_status.assert_not_awaited()


async def test_linter_distinguishes_expiry_from_access_count():
    from learning.memory_linter import MemoryLinter

    shared = SimpleNamespace(
        search_commons=AsyncMock(
            return_value=[
                {"expires_at": "2099-01-01T00:00:00Z", "access_count": 0},
                {"expires_at": "2000-01-01T00:00:00Z", "metadata": {"source_ids": []}},
                {"expires_at": "not-a-date", "metadata": None},
            ]
        )
    )
    result = await MemoryLinter(SimpleNamespace(_shared=shared)).lint()
    assert result["stale_articles"] == 1
    assert result["orphan_articles"] == 1
    assert result["unaccessed_articles"] == 1
    assert result["invalid_expiry_articles"] == 1


async def test_context_generation_reads_real_indexer_without_missing_import():
    from learning.prompt_store import SqlPromptStore

    db = AsyncMock()

    class Indexer:
        def search(self, query, limit):
            return [SimpleNamespace(content="Supported lesson", score=0.9)]

    store = SqlPromptStore(db, journal_indexer=Indexer())
    await store.generate_agent_context(
        "audit", SimpleNamespace(strategy="paper", universe=[])
    )
    assert "Supported lesson" in store.get_agent_context("audit")
    db.commit.assert_awaited_once()


async def test_halt_sync_waits_for_pending_control_write():
    import asyncio

    started, release = asyncio.Event(), asyncio.Event()

    class DelayedStore(ControlStore):
        async def set(self, key, value, nx=False):
            started.set()
            await release.wait()
            return await super().set(key, value, nx)

    store = DelayedStore()
    engine = RiskEngine([], KillSwitch())
    engine.bind_control_store(store)
    halt = asyncio.create_task(engine.set_halted(True, "test"))
    await started.wait()
    sync = asyncio.create_task(engine.sync_halt())
    await asyncio.sleep(0)
    assert not sync.done()
    assert engine.check_kill_active()
    release.set()
    await asyncio.gather(halt, sync)
    assert engine.check_kill_active()


async def test_missing_control_store_blocks_engine_on_startup():
    engine = RiskEngine([], KillSwitch())
    with pytest.raises(RuntimeError, match="unavailable"):
        await engine.initialize_control()
    assert engine.check_kill_active()


async def test_resume_cannot_override_invalid_risk_configuration():
    store = ControlStore()
    engine = RiskEngine(
        [], KillSwitch(), configuration_error="Invalid risk configuration"
    )
    engine.bind_control_store(store)
    assert engine.check_kill_active()
    with pytest.raises(RuntimeError, match="Invalid risk"):
        await engine.sync_halt()
    with pytest.raises(RuntimeError, match="Invalid risk"):
        await engine.set_halted(False)
    assert engine.check_kill_active()
    await engine.set_halted(True, "maintenance")
    assert store.values["kill_switch:active"] == "true"
