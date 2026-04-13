import os
import sys

# Prevent libomp fatal abort when hnswlib and torch (via sentence-transformers)
# both link duplicate OpenMP runtimes — standard macOS/Homebrew workaround.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# Add project root to path for 'shared' module imports
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)

# Set a test API key to silence "Running in paper mode without STA_API_KEY" warnings
os.environ.setdefault("STA_API_KEY", "test-key-for-unit-tests")

import pytest
import aiosqlite
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from broker.models import BrokerCapabilities

# Minimal DDL for all tables used by unit tests.
# Since init_db() is a no-op (Laravel owns DDL), tests using in-memory
# SQLite need table DDL provided explicitly.
_TEST_DDL = [
    """CREATE TABLE IF NOT EXISTS opportunities (
        id TEXT PRIMARY KEY, agent_name TEXT NOT NULL, symbol TEXT NOT NULL,
        signal TEXT NOT NULL, confidence REAL NOT NULL, reasoning TEXT NOT NULL,
        suggested_trade TEXT, status TEXT NOT NULL DEFAULT 'pending',
        expires_at TEXT, data TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT,
        order_result TEXT NOT NULL, risk_evaluation TEXT, agent_name TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS performance_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, agent_name TEXT NOT NULL,
        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        opportunities_generated INTEGER DEFAULT 0,
        opportunities_executed INTEGER DEFAULT 0,
        win_rate REAL DEFAULT 0, total_pnl TEXT DEFAULT '0',
        daily_pnl TEXT DEFAULT '0', daily_pnl_pct REAL DEFAULT 0,
        sharpe_ratio REAL, max_drawdown REAL,
        avg_win TEXT DEFAULT '0', avg_loss TEXT DEFAULT '0',
        profit_factor REAL, total_trades INTEGER DEFAULT 0,
        open_positions INTEGER DEFAULT 0,
        consecutive_losses INTEGER DEFAULT 0,
        max_consecutive_losses INTEGER DEFAULT 0,
        consecutive_wins INTEGER DEFAULT 0,
        max_consecutive_wins INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS tracked_positions (
        id TEXT PRIMARY KEY, opportunity_id TEXT, agent_name TEXT,
        symbol TEXT, side TEXT, quantity REAL, entry_price REAL,
        exit_price REAL, pnl REAL, status TEXT DEFAULT 'open',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        closed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS agent_registry (
        agent_name TEXT PRIMARY KEY, strategy TEXT, enabled INTEGER DEFAULT 1,
        config TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS risk_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
        details TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS trade_executions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, opportunity_id TEXT,
        order_result TEXT NOT NULL, risk_evaluation TEXT, agent_name TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
]


@pytest.fixture
async def test_db():
    """In-memory SQLite database with all test tables pre-created."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    for ddl in _TEST_DDL:
        await conn.execute(ddl)
    await conn.commit()
    yield conn
    await conn.close()


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.connection.connect = AsyncMock()
    broker.connection.disconnect = AsyncMock()
    broker.connection._reconnecting = False
    broker.capabilities.return_value = BrokerCapabilities(
        stocks=True,
        options=True,
        futures=True,
        forex=True,
        bonds=True,
        streaming=True,
    )
    return broker


@pytest.fixture
def client(mock_broker):
    os.environ["STA_API_KEY"] = "test-key"
    from api.auth import _get_settings

    _get_settings.cache_clear()
    from api.app import create_app

    app = create_app(mock_broker)
    # Provide mock Redis so kill-switch and other Redis-dependent deps don't 500
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    mock_redis.setex = AsyncMock()
    mock_redis.delete = AsyncMock()
    app.state.redis = mock_redis
    return TestClient(app)


@pytest.fixture
def postgres_dsn():
    """PostgreSQL DSN for integration tests."""
    return os.environ.get(
        "STA_DATABASE_URL", "postgresql://postgres:secret@localhost:5432/agent_memory"
    )
