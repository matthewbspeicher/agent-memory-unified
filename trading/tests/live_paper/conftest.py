"""
Shared fixtures for live_paper tests.

All fixtures are session-scoped to minimise API calls and avoid rate-limiting.
Credentials are read from environment variables; tests skip cleanly when absent.
"""
from __future__ import annotations

import os

import aiosqlite
import pytest

# ---------------------------------------------------------------------------
# Skip markers — applied per-test in each test file
# ---------------------------------------------------------------------------

_kalshi_ready = bool(
    os.getenv("STA_KALSHI_KEY_ID") and os.getenv("STA_KALSHI_PRIVATE_KEY_PATH")
)
_polymarket_ready = bool(os.getenv("STA_POLYMARKET_PRIVATE_KEY"))

skip_no_kalshi = pytest.mark.skipif(
    not _kalshi_ready,
    reason="Kalshi credentials not set (STA_KALSHI_KEY_ID, STA_KALSHI_PRIVATE_KEY_PATH)",
)
skip_no_polymarket = pytest.mark.skipif(
    not _polymarket_ready,
    reason="Polymarket credentials not set (STA_POLYMARKET_PRIVATE_KEY)",
)


# ---------------------------------------------------------------------------
# Kalshi fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def kalshi_client():
    """Real KalshiClient pointed at demo-api.kalshi.co."""
    from adapters.kalshi.client import KalshiClient
    return KalshiClient(
        key_id=os.environ.get("STA_KALSHI_KEY_ID"),
        private_key_path=os.environ.get("STA_KALSHI_PRIVATE_KEY_PATH"),
        demo=True,
    )


@pytest.fixture(scope="session")
async def kalshi_paper_broker():
    """KalshiPaperBroker backed by an in-memory PaperStore."""
    from adapters.kalshi.paper import KalshiPaperBroker
    from storage.paper import PaperStore
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    store = PaperStore(db)
    await store.init_tables()
    broker = KalshiPaperBroker(store=store)
    await broker.connection.connect()
    yield broker
    await db.close()


# ---------------------------------------------------------------------------
# Polymarket fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def polymarket_client():
    """Real PolymarketClient in dry-run mode."""
    from adapters.polymarket.client import PolymarketClient
    return PolymarketClient(
        private_key=os.environ.get("STA_POLYMARKET_PRIVATE_KEY", "0x" + "0" * 64),
        rpc_url=os.getenv("STA_POLYMARKET_RPC_URL", "https://polygon-rpc.com"),
        dry_run=True,
    )


@pytest.fixture(scope="session")
async def polymarket_broker(polymarket_client):
    """PolymarketBroker wired with dry_run=True."""
    from adapters.polymarket.broker import PolymarketBroker
    from adapters.polymarket.data_source import PolymarketDataSource
    ds = PolymarketDataSource(polymarket_client)
    brk = PolymarketBroker(
        client=polymarket_client,
        data_source=ds,
        creds_path=os.getenv("STA_POLYMARKET_CREDS_PATH", "data/polymarket_creds.json"),
        dry_run=True,
    )
    await brk.connection.connect()
    yield brk
    await brk.connection.disconnect()


# ---------------------------------------------------------------------------
# Storage fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
async def live_db():
    """In-memory SQLite for pipeline tests — tables initialised via init_db."""
    from storage.db import init_db
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield db
    await db.close()
