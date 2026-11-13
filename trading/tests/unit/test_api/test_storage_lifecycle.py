"""Application storage ownership and readiness without external startup clients."""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import aiosqlite
import pytest
from fastapi import FastAPI
from starlette.requests import Request

import api.app as app_module
from api.routes.health import readiness_probe
from api.startup.brokers import setup_brokers
from broker.paper import PaperBrokerConnection
from config import BrokerConfig, Config
from storage.paper import PaperStore
from storage.readiness import StorageSession


def _config():
    return Config(
        database_url=None,
        db_path=":memory:",
        redis_url="",
        paper_trading=False,
        broker=BrokerConfig(ib_host=""),
    )


def _app(*, managed=True):
    app = FastAPI()
    app.state.enable_agent_framework = managed
    app.state.config = _config()
    return app


async def _ready(app, expected_db):
    response = await readiness_probe(Request({"type": "http", "app": app}))
    expected_ready = expected_db is not False
    assert response.status_code == (200 if expected_ready else 503)
    assert json.loads(response.body) == {
        "ready": expected_ready,
        "checks": {"db": expected_db, "redis": None, "broker": None},
    }


@pytest.mark.parametrize(
    "failure",
    ["none", "startup", "serving", "startup_cancel", "serving_cancel", "storage"],
)
async def test_lifespan_closes_owned_database_after_every_exit(monkeypatch, failure):
    app = _app()
    acquired = []
    stopped = []
    cancel_point = asyncio.Event()

    async def stop():
        # Dependent resources must stop before the shared database closes.
        await acquired[0].execute("SELECT 1")
        stopped.append("streams")

    @asynccontextmanager
    async def startup(app):
        assert app.state.storage_managed is True
        session = await app.state._storage_stack.enter_async_context(
            StorageSession(app.state.config)
        )
        app.state.storage_session = session
        app.state.db = session.db
        acquired.append(session.db)
        app.state.streams_consumer = SimpleNamespace(stop=stop)
        if failure == "storage":
            await session.db.execute("DROP TABLE opportunities")
            await session.db.commit()
        await session.certify()
        if failure == "startup":
            raise RuntimeError("startup failed after storage acquisition")
        if failure == "startup_cancel":
            cancel_point.set()
            await asyncio.Event().wait()
        yield

    monkeypatch.setattr(app_module, "_startup_lifespan", startup)

    async def run():
        async with app_module.lifespan(app):
            await _ready(app, True)
            if failure == "serving":
                raise RuntimeError("serving failed")
            if failure == "serving_cancel":
                cancel_point.set()
                await asyncio.Event().wait()

    if "cancel" in failure:
        task = asyncio.create_task(run())
        await asyncio.wait_for(cancel_point.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif failure == "storage":
        with pytest.raises(RuntimeError, match="Required storage unavailable"):
            await run()
    elif failure != "none":
        with pytest.raises(RuntimeError, match="failed"):
            await run()
    else:
        await run()

    assert stopped == ["streams"]
    assert app.state.storage_managed is True
    with pytest.raises(ValueError, match="no active connection"):
        await acquired[0].execute("SELECT 1")
    await _ready(app, False)


@pytest.mark.parametrize("failing_cleanup", ["streams", "tasks", "paper"])
@pytest.mark.parametrize("startup_failure", [False, True])
async def test_cleanup_failure_does_not_skip_later_cleanup_or_database_close(
    monkeypatch, caplog, failing_cleanup, startup_failure
):
    app = _app()
    acquired = []
    cleanup_order = []

    def closer(name):
        async def close():
            await acquired[0].execute("SELECT 1")
            cleanup_order.append(name)
            if name == failing_cleanup:
                raise RuntimeError(f"{name} cleanup failed")

        return close

    @asynccontextmanager
    async def startup(app):
        session = await app.state._storage_stack.enter_async_context(
            StorageSession(app.state.config)
        )
        app.state.storage_session = session
        app.state.db = session.db
        acquired.append(session.db)
        await session.certify()
        app.state.streams_consumer = SimpleNamespace(stop=closer("streams"))
        app.state.task_manager = SimpleNamespace(shutdown=closer("tasks"))
        app.state.paper_store = SimpleNamespace(close=closer("paper"))
        app.state.redis = SimpleNamespace(aclose=closer("redis"))
        if startup_failure:
            raise RuntimeError("primary startup failure")
        yield

    monkeypatch.setattr(app_module, "_startup_lifespan", startup)

    async def run():
        async with app_module.lifespan(app):
            pass

    if startup_failure:
        with pytest.raises(RuntimeError, match="primary startup failure"):
            await run()
    else:
        await run()

    assert cleanup_order == ["streams", "tasks", "paper", "redis"]
    assert f"{failing_cleanup} cleanup failed" in caplog.text
    with pytest.raises(ValueError, match="no active connection"):
        await acquired[0].execute("SELECT 1")


async def test_unmanaged_lifespan_preserves_externally_owned_database(monkeypatch):
    app = _app(managed=False)
    async with aiosqlite.connect(":memory:") as database:
        app.state.db = database

        @asynccontextmanager
        async def startup(app):
            yield

        monkeypatch.setattr(app_module, "_startup_lifespan", startup)
        async with app_module.lifespan(app):
            await _ready(app, True)
        await database.execute("SELECT 1")


@pytest.mark.parametrize("state", ["missing", "pending", "missing_db", "mismatched"])
async def test_managed_readiness_fails_without_matching_certified_storage(state):
    app = _app()
    app.state.storage_managed = True
    if state == "missing":
        await _ready(app, False)
        return

    async with StorageSession(app.state.config) as session:
        app.state.storage_session = session
        if state != "missing_db":
            app.state.db = session.db
        if state != "pending":
            await session.certify()
        if state == "mismatched":
            async with aiosqlite.connect(":memory:") as other:
                app.state.db = other
                await _ready(app, False)
        else:
            await _ready(app, False)


async def test_managed_readiness_detects_unusable_schema_and_closed_session():
    app = _app()
    app.state.storage_managed = True
    async with StorageSession(app.state.config) as session:
        app.state.storage_session = session
        app.state.db = session.db
        await session.certify()
        await _ready(app, True)
        await session.db.execute("DROP TABLE opportunities")
        await session.db.commit()
        # A successful connectivity ping must not conceal broken required storage.
        await session.db.execute("SELECT 1")
        await _ready(app, False)
    await _ready(app, False)


async def test_unmanaged_readiness_remains_permissive_without_dependencies():
    app = _app(managed=False)
    await _ready(app, None)


@pytest.mark.parametrize(
    ("stage", "cancel"),
    [
        ("init", False),
        ("account", False),
        ("connect", False),
        ("init", True),
        ("account", True),
        ("connect", True),
        ("later_broker", True),
    ],
)
async def test_unreturned_paper_store_closes_dedicated_connection(
    monkeypatch, tmp_path, stage, cancel
):
    config = Config(
        database_url=None,
        db_path=str(tmp_path / "paper-startup.db"),
        redis_url="",
        paper_trading=True,
        worker_mode=stage != "later_broker",
        broker=BrokerConfig(
            ib_host="local-test-only" if stage == "later_broker" else ""
        ),
    )
    acquired = []
    reached_failure = asyncio.Event()
    original_error = RuntimeError("paper startup failed before ownership transfer")
    original_init = PaperStore.init_tables

    async def fail(*args, **kwargs):
        if cancel:
            reached_failure.set()
            await asyncio.Event().wait()
        raise original_error

    async with aiosqlite.connect(config.db_path) as shared:
        shared.row_factory = aiosqlite.Row

        async def initialize(store, **kwargs):
            await original_init(store, **kwargs)
            dedicated = await store._get_db()
            assert dedicated is not shared
            acquired.append(dedicated)
            if stage == "init":
                await fail()

        monkeypatch.setattr(PaperStore, "init_tables", initialize)
        if stage == "account":
            monkeypatch.setattr(PaperStore, "ensure_account", fail)
        elif stage == "connect":
            monkeypatch.setattr(PaperBrokerConnection, "connect", fail)
        elif stage == "later_broker":
            # Substitute the optional broker transport before its lazy import.
            # The real PaperStore has already acquired its dedicated connection.
            monkeypatch.setitem(
                sys.modules,
                "adapters.ibkr.adapter",
                SimpleNamespace(
                    IBKRBroker=lambda **kwargs: SimpleNamespace(
                        connection=SimpleNamespace(connect=fail)
                    )
                ),
            )

        if cancel:
            task = asyncio.create_task(setup_brokers(config, shared, None))
            try:
                await asyncio.wait_for(reached_failure.wait(), timeout=5)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        else:
            with pytest.raises(RuntimeError) as raised:
                await setup_brokers(config, shared, None)
            assert raised.value is original_error

        assert len(acquired) == 1
        with pytest.raises(ValueError, match="no active connection"):
            await acquired[0].execute("SELECT 1")
        await shared.execute("SELECT 1")


async def test_paper_store_cleanup_error_preserves_startup_failure(
    monkeypatch, tmp_path, caplog
):
    config = Config(
        database_url=None,
        db_path=str(tmp_path / "paper-cleanup.db"),
        paper_trading=True,
        worker_mode=True,
        broker=BrokerConfig(ib_host=""),
    )
    original_init = PaperStore.init_tables
    original_close = PaperStore.close
    original_error = RuntimeError("primary paper initialization failure")
    acquired = []

    async def initialize(store, **kwargs):
        await original_init(store, **kwargs)
        acquired.append(await store._get_db())
        raise original_error

    async def close(store):
        await original_close(store)
        raise RuntimeError("credential-bearing cleanup detail must stay private")

    monkeypatch.setattr(PaperStore, "init_tables", initialize)
    monkeypatch.setattr(PaperStore, "close", close)
    async with aiosqlite.connect(config.db_path) as shared:
        shared.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError) as raised:
            await setup_brokers(config, shared, None)
        assert raised.value is original_error
        assert "Paper startup cleanup failed (RuntimeError)" in caplog.text
        assert "credential-bearing" not in caplog.text
        with pytest.raises(ValueError, match="no active connection"):
            await acquired[0].execute("SELECT 1")
        await shared.execute("SELECT 1")


@pytest.mark.parametrize("cancelled_cleanup", ["streams", "tasks", "paper"])
@pytest.mark.parametrize("startup_failure", [False, True])
async def test_cancelled_cleanup_attempts_later_dependents_before_database_close(
    monkeypatch, cancelled_cleanup, startup_failure
):
    app = _app()
    acquired = []
    cleanup_order = []
    original_error = RuntimeError("primary startup failure before cancelled cleanup")

    def closer(name):
        async def close():
            await acquired[0].execute("SELECT 1")
            cleanup_order.append(name)
            if name == cancelled_cleanup:
                raise asyncio.CancelledError()

        return close

    @asynccontextmanager
    async def startup(app):
        session = await app.state._storage_stack.enter_async_context(
            StorageSession(app.state.config)
        )
        app.state.storage_session = session
        app.state.db = session.db
        acquired.append(session.db)
        await session.certify()
        app.state.streams_consumer = SimpleNamespace(stop=closer("streams"))
        app.state.task_manager = SimpleNamespace(shutdown=closer("tasks"))
        app.state.paper_store = SimpleNamespace(close=closer("paper"))
        app.state.redis = SimpleNamespace(aclose=closer("redis"))
        if startup_failure:
            raise original_error
        yield

    monkeypatch.setattr(app_module, "_startup_lifespan", startup)

    async def run():
        async with app_module.lifespan(app):
            pass

    if startup_failure:
        with pytest.raises(RuntimeError) as raised:
            await run()
        assert raised.value is original_error
    else:
        with pytest.raises(asyncio.CancelledError):
            await run()

    assert cleanup_order == ["streams", "tasks", "paper", "redis"]
    with pytest.raises(ValueError, match="no active connection"):
        await acquired[0].execute("SELECT 1")


async def test_outer_cancellation_waits_for_dependent_cleanup_before_database_close(
    monkeypatch,
):
    app = _app()
    acquired = []
    cleanup_entered = asyncio.Event()
    finish_cleanup = asyncio.Event()
    cleanup_completed = []

    async def stop():
        cleanup_entered.set()
        await finish_cleanup.wait()
        await acquired[0].execute("SELECT 1")
        cleanup_completed.append("streams")

    @asynccontextmanager
    async def startup(app):
        session = await app.state._storage_stack.enter_async_context(
            StorageSession(app.state.config)
        )
        app.state.storage_session = session
        app.state.db = session.db
        acquired.append(session.db)
        await session.certify()
        app.state.streams_consumer = SimpleNamespace(stop=stop)
        yield

    monkeypatch.setattr(app_module, "_startup_lifespan", startup)

    async def run():
        async with app_module.lifespan(app):
            pass

    task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(cleanup_entered.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        await acquired[0].execute("SELECT 1")
        finish_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        finish_cleanup.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert cleanup_completed == ["streams"]
    with pytest.raises(ValueError, match="no active connection"):
        await acquired[0].execute("SELECT 1")
