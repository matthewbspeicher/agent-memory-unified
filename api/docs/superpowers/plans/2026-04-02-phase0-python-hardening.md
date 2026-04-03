# Phase 0: Python Internal Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Python codebase from global singleton config to explicit dependency injection, preparing for monorepo integration.

**Architecture:** Replace `pydantic-settings` auto-loading with explicit `Config` class. Pass dependencies (db, redis, config) through constructors instead of importing globals. Makes testing easier and integration cleaner.

**Tech Stack:** Python 3.12, asyncpg, redis-py, pytest

**Timeline:** Week 1 (5-7 days)

**Context:** Execute in `stock-trading-api` repository (pre-monorepo migration)

---

## File Structure

**Modified Files:**
- `config.py` — Replace pydantic-settings with explicit Config class
- `storage/db.py` — Remove global settings import, accept db in constructors
- `storage/stores.py` — Accept db parameter in all store classes
- `agents/runner.py` — Accept config, db, redis as constructor params
- `agents/router.py` — Pass dependencies to AgentRunner
- `api/routes.py` — Use FastAPI Depends() for dependency injection
- `api/main.py` — Create lifespan context manager for shared resources
- `tests/conftest.py` — Update fixtures to use new DI pattern

**Test Files:**
- All existing test files updated to use fixtures

---

## Task 1: Create Explicit Config Class

**Files:**
- Modify: `config.py`
- Test: `tests/test_config.py` (new)

- [ ] **Step 1: Write test for Config class**

```python
# tests/test_config.py
import os
import pytest
from config import Config, load_config

def test_config_loads_from_env(monkeypatch):
    """Config reads environment variables."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:pass@localhost/testdb")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6380")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")

    config = load_config()

    assert config.database_url == "postgresql://test:pass@localhost/testdb"
    assert config.redis_url == "redis://localhost:6380"
    assert config.anthropic_api_key == "test-key-123"

def test_config_has_defaults():
    """Config provides sensible defaults for optional settings."""
    config = Config()

    assert config.database_url == "sqlite:///data.db"  # Default
    assert config.redis_url == "redis://localhost:6379"
    assert config.log_level == "INFO"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: `ModuleNotFoundError: No module named 'config'` or import errors

- [ ] **Step 3: Rewrite config.py with explicit Config class**

```python
# config.py
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # Database
    database_url: str = "sqlite:///data.db"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # LLM providers
    anthropic_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"

    # IBKR
    ib_host: str = "127.0.0.1"
    ib_port: int = 4002  # Paper trading
    ib_client_id: int = 1

    # Kalshi
    kalshi_key_id: Optional[str] = None
    kalshi_private_key_path: Optional[str] = None
    kalshi_demo: bool = True

    # Observability
    supabase_url: Optional[str] = None
    supabase_service_key: Optional[str] = None
    sentry_dsn: Optional[str] = None

    # App settings
    log_level: str = "INFO"
    environment: str = "development"

def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        database_url=os.getenv("DATABASE_URL", "sqlite:///data.db"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ib_host=os.getenv("IB_HOST", "127.0.0.1"),
        ib_port=int(os.getenv("IB_PORT", "4002")),
        ib_client_id=int(os.getenv("IB_CLIENT_ID", "1")),
        kalshi_key_id=os.getenv("KALSHI_KEY_ID"),
        kalshi_private_key_path=os.getenv("KALSHI_PRIVATE_KEY_PATH"),
        kalshi_demo=os.getenv("KALSHI_DEMO", "true").lower() == "true",
        supabase_url=os.getenv("SUPABASE_URL"),
        supabase_service_key=os.getenv("SUPABASE_SERVICE_KEY"),
        sentry_dsn=os.getenv("SENTRY_DSN"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        environment=os.getenv("ENVIRONMENT", "development"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (both tests green)

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "refactor: replace pydantic-settings with explicit Config class

- Config class uses dataclass for simplicity
- load_config() reads from environment variables
- No global singleton, explicit instantiation required
- Prepares for monorepo dependency injection pattern"
```

---

## Task 2: Refactor Database Connection Layer

**Files:**
- Modify: `storage/db.py`
- Test: `tests/storage/test_db.py` (new)

- [ ] **Step 1: Write test for database connection**

```python
# tests/storage/test_db.py
import pytest
import asyncpg
from storage.db import create_connection, DatabaseConnection
from config import Config

@pytest.mark.asyncio
async def test_create_connection_postgresql():
    """create_connection returns asyncpg connection for PostgreSQL URLs."""
    config = Config(database_url="postgresql://user:pass@localhost/testdb")

    # Mock asyncpg.connect
    class MockConnection:
        async def close(self):
            pass

    async def mock_connect(dsn):
        assert dsn == "postgresql://user:pass@localhost/testdb"
        return MockConnection()

    conn = await create_connection(config, connect_fn=mock_connect)
    assert isinstance(conn, MockConnection)
    await conn.close()

@pytest.mark.asyncio
async def test_database_connection_context_manager(monkeypatch):
    """DatabaseConnection manages connection lifecycle."""
    config = Config(database_url="postgresql://localhost/test")

    opened = []
    closed = []

    class MockConn:
        async def close(self):
            closed.append(True)

    async def mock_connect(dsn):
        opened.append(True)
        return MockConn()

    async with DatabaseConnection(config, connect_fn=mock_connect) as conn:
        assert len(opened) == 1
        assert len(closed) == 0

    assert len(closed) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_db.py -v`
Expected: ImportError or function not found

- [ ] **Step 3: Rewrite storage/db.py**

```python
# storage/db.py
import asyncpg
import aiosqlite
from typing import Union
from config import Config

async def create_connection(config: Config, connect_fn=None) -> Union[asyncpg.Connection, aiosqlite.Connection]:
    """
    Create database connection based on config.database_url.

    Supports PostgreSQL (asyncpg) and SQLite (aiosqlite).
    """
    if config.database_url.startswith("postgresql://"):
        fn = connect_fn or asyncpg.connect
        return await fn(config.database_url)
    elif config.database_url.startswith("sqlite://"):
        db_path = config.database_url.replace("sqlite:///", "")
        fn = connect_fn or aiosqlite.connect
        return await fn(db_path)
    else:
        raise ValueError(f"Unsupported database URL: {config.database_url}")

class DatabaseConnection:
    """Async context manager for database connections."""

    def __init__(self, config: Config, connect_fn=None):
        self.config = config
        self.connect_fn = connect_fn
        self.conn = None

    async def __aenter__(self):
        self.conn = await create_connection(self.config, self.connect_fn)
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            await self.conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/storage/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add storage/db.py tests/storage/test_db.py
git commit -m "refactor: database connection accepts Config parameter

- create_connection(config) replaces global settings import
- DatabaseConnection context manager for lifecycle
- Supports both PostgreSQL and SQLite
- Testable with dependency injection"
```

---

## Task 3: Refactor Storage Stores

**Files:**
- Modify: `storage/stores.py`
- Test: `tests/storage/test_stores.py`

- [ ] **Step 1: Write test for TradeStore with injected db**

```python
# tests/storage/test_stores.py
import pytest
from storage.stores import TradeStore
from datetime import datetime

@pytest.mark.asyncio
async def test_trade_store_create(mock_db):
    """TradeStore.create inserts trade record."""
    store = TradeStore(mock_db)

    trade_data = {
        "agent_id": "test-agent",
        "ticker": "AAPL",
        "direction": "long",
        "entry_price": 185.50,
        "quantity": 100,
        "paper": True,
    }

    trade = await store.create(trade_data)

    assert trade["ticker"] == "AAPL"
    assert trade["direction"] == "long"
    assert mock_db.execute_called

@pytest.mark.asyncio
async def test_trade_store_find_by_agent(mock_db):
    """TradeStore.find_by_agent queries by agent_id."""
    mock_db.return_rows = [
        {"id": "1", "ticker": "AAPL", "status": "open"},
        {"id": "2", "ticker": "MSFT", "status": "closed"},
    ]

    store = TradeStore(mock_db)
    trades = await store.find_by_agent("agent-123", status="open")

    assert len(trades) == 2
    assert mock_db.last_query.startswith("SELECT")
    assert "agent_id = $1" in mock_db.last_query
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_stores.py::test_trade_store_create -v`
Expected: FAIL (TradeStore doesn't accept db parameter yet)

- [ ] **Step 3: Update TradeStore to accept db in constructor**

```python
# storage/stores.py
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class TradeStore:
    """Manages trade records in the database."""

    def __init__(self, db):
        """
        Initialize TradeStore with database connection.

        Args:
            db: asyncpg.Connection or aiosqlite.Connection
        """
        self.db = db

    async def create(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new trade record."""
        trade_id = str(uuid.uuid4())

        query = """
            INSERT INTO trades (
                id, agent_id, ticker, direction, entry_price, quantity,
                entry_at, status, paper, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
        """

        row = await self.db.fetchrow(
            query,
            trade_id,
            trade_data["agent_id"],
            trade_data["ticker"],
            trade_data["direction"],
            trade_data["entry_price"],
            trade_data["quantity"],
            datetime.utcnow(),
            "open",
            trade_data.get("paper", True),
            trade_data.get("metadata", {}),
        )

        return dict(row)

    async def find_by_agent(
        self,
        agent_id: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Find trades for an agent, optionally filtered by status."""
        if status:
            query = "SELECT * FROM trades WHERE agent_id = $1 AND status = $2"
            rows = await self.db.fetch(query, agent_id, status)
        else:
            query = "SELECT * FROM trades WHERE agent_id = $1"
            rows = await self.db.fetch(query, agent_id)

        return [dict(row) for row in rows]

    async def update_status(
        self,
        trade_id: str,
        status: str,
        exit_price: Optional[float] = None,
        pnl: Optional[float] = None
    ):
        """Update trade status and exit details."""
        query = """
            UPDATE trades
            SET status = $1, exit_at = $2, exit_price = $3, pnl = $4
            WHERE id = $5
        """
        await self.db.execute(
            query,
            status,
            datetime.utcnow() if status == "closed" else None,
            exit_price,
            pnl,
            trade_id
        )


class PositionStore:
    """Manages current positions in the database."""

    def __init__(self, db):
        self.db = db

    async def get(self, agent_id: str, ticker: str, paper: bool = True) -> Optional[Dict]:
        """Get current position for agent/ticker."""
        query = "SELECT * FROM positions WHERE agent_id = $1 AND ticker = $2 AND paper = $3"
        row = await self.db.fetchrow(query, agent_id, ticker, paper)
        return dict(row) if row else None

    async def update(self, position_data: Dict[str, Any]):
        """Upsert position record."""
        query = """
            INSERT INTO positions (agent_id, ticker, paper, quantity, avg_entry_price, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (agent_id, ticker, paper)
            DO UPDATE SET quantity = $4, avg_entry_price = $5, updated_at = $6
        """
        await self.db.execute(
            query,
            position_data["agent_id"],
            position_data["ticker"],
            position_data["paper"],
            position_data["quantity"],
            position_data["avg_entry_price"],
            datetime.utcnow(),
        )


class StatsStore:
    """Manages trading statistics in the database."""

    def __init__(self, db):
        self.db = db

    async def get(self, agent_id: str, paper: bool = True) -> Dict:
        """Get stats for an agent."""
        query = "SELECT * FROM trading_stats WHERE agent_id = $1 AND paper = $2"
        row = await self.db.fetchrow(query, agent_id, paper)
        return dict(row) if row else self._empty_stats(agent_id, paper)

    async def update(self, stats_data: Dict[str, Any]):
        """Upsert stats record."""
        query = """
            INSERT INTO trading_stats (
                agent_id, paper, total_trades, win_count, loss_count,
                win_rate, total_pnl, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (agent_id, paper)
            DO UPDATE SET
                total_trades = $3, win_count = $4, loss_count = $5,
                win_rate = $6, total_pnl = $7, updated_at = $8
        """
        await self.db.execute(
            query,
            stats_data["agent_id"],
            stats_data["paper"],
            stats_data["total_trades"],
            stats_data["win_count"],
            stats_data["loss_count"],
            stats_data["win_rate"],
            stats_data["total_pnl"],
            datetime.utcnow(),
        )

    def _empty_stats(self, agent_id: str, paper: bool) -> Dict:
        return {
            "agent_id": agent_id,
            "paper": paper,
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/storage/test_stores.py -v`
Expected: PASS (all store tests green)

- [ ] **Step 5: Commit**

```bash
git add storage/stores.py tests/storage/test_stores.py
git commit -m "refactor: storage stores accept db via constructor

- TradeStore, PositionStore, StatsStore take db parameter
- Removed global settings imports
- All database queries use injected connection
- Tests validate dependency injection pattern"
```

---

## Self-Review Checklist

**Spec Coverage:**
- ✅ Explicit Config class created
- ✅ Database connection layer refactored
- ✅ Storage stores accept db parameter
- ✅ All tests written first (TDD)

**Timeline:** 3 tasks complete, 5 more to go. Continuing with remaining tasks...

