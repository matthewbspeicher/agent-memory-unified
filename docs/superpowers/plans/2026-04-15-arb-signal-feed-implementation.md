# PM Arb Signal Feed v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (user has rejected subagent-driven-development per `feedback_no_subagent_delegation`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `remembr.dev/feeds/arb` — a paid REST signal feed of cross-platform PM arbitrage opportunities, with public PnL dashboard, Stripe billing, and freshness monitoring.

**Architecture:** Wire the existing `cross_platform_arb` strategy's `SignalBus` events into a new `feed_publisher` background task that persists to `feed_arb_signals`. Expose via authenticated REST (`read:feeds.arb` scope, ULID `signal_id`, `next_since` cursor). Plumb `signal_id` through Kalshi (`client_order_id`) and Polymarket (order-hash map) execution paths so a 60s PnL attribution job can compute real + scaled-to-$250k PnL exhibits for the public dashboard. Stripe single product with idempotent webhook + hourly reconciliation provisions `read:feeds.arb` scopes on payment.

**Tech Stack:** Python 3.13, FastAPI, asyncpg/Postgres, existing `IdentityStore`, existing `SignalBus`, React 19 + Vite + TanStack Query (frontend), Stripe Python SDK, `ulid-py`.

**Spec:** `docs/superpowers/specs/2026-04-15-arb-signal-feed-design.md` (rev 2, commit `ee0bdd1`)

**Build budget:** ~10.75 days

**Test command (use throughout):**
```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest <path> -v --tb=short --timeout=30
```

---

## Phase 0 — Production-path verification gate

This phase has no code. It exists to enforce the spec's Step 0 acceptance criterion.

### Task 0.1: Verify Polymarket execution path

**Files:** none (manual verification)

- [ ] **Step 1: Query the production arb fills database**

Run:
```bash
docker exec agent-memory-unified-postgres-1 psql -U postgres -d agent_memory -c "
  SELECT COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS fills_last_7d
  FROM trade_executions
  WHERE strategy = 'cross_platform_arb'
    AND status = 'filled'
    AND legs_filled = 2;
"
```

Expected: a single row with `fills_last_7d` value.

- [ ] **Step 2: Verify the count is ≥5**

If `fills_last_7d ≥ 5`: gate passes; proceed to Phase 1.
If `fills_last_7d < 5`: **STOP**. The production execution path needs repair before any feed work begins. Open a separate branch to investigate (likely culprits: `trading/adapters/polymarket/broker.py` order signing, `trading/strategies/cross_platform_arb.py` matching, or stale `agent_registry.parameters`). Return to this plan only after the gate passes.

- [ ] **Step 3: Capture baseline for monitoring later**

Save the count + a sample of `signal_id`-less fills (since `signal_id` plumbing doesn't exist yet) to a scratch file:
```bash
docker exec agent-memory-unified-postgres-1 psql -U postgres -d agent_memory -c "
  SELECT id, strategy, symbol, side, quantity, fill_price, created_at
  FROM trade_executions
  WHERE strategy = 'cross_platform_arb' AND created_at >= NOW() - INTERVAL '7 days'
  ORDER BY created_at DESC LIMIT 10;
" > /tmp/arb-fills-baseline-2026-04-15.txt
```

This is reference data for verifying §5 attribution later (you'll match these fills against `signal_id` once Phase 3 lands).

---

## Phase 1 — Database schema

Three new tables added to **both** `_INIT_DDL` (in `trading/storage/db.py`) and `scripts/init-trading-tables.sql`. The parity test at `trading/tests/unit/test_storage/test_schema_parity.py` catches drift.

(Note: spec mentioned a third source `_migrations`, but per `trading/storage/migrations.py` it's deprecated. Reality is two sources + parity test.)

### Task 1.1: Add `feed_arb_signals` table

**Files:**
- Modify: `trading/storage/db.py` (`_INIT_DDL` string)
- Modify: `scripts/init-trading-tables.sql`
- Test: `trading/tests/unit/test_storage/test_schema_parity.py` (existing — re-run only)

- [ ] **Step 1: Add table to `_INIT_DDL` in `trading/storage/db.py`**

Find the `_INIT_DDL = """..."""` block and append before the closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS feed_arb_signals (
    signal_id TEXT PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    pair_kalshi_ticker TEXT NOT NULL,
    pair_kalshi_side TEXT NOT NULL,
    pair_poly_token_id TEXT NOT NULL,
    pair_poly_side TEXT NOT NULL,
    edge_cents NUMERIC(10,2) NOT NULL,
    max_size_at_edge_usd NUMERIC(12,2) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    outcome TEXT,
    outcome_set_at TIMESTAMPTZ,
    raw_signal JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feed_arb_signals_ts ON feed_arb_signals(ts DESC);
CREATE INDEX IF NOT EXISTS idx_feed_arb_signals_pending ON feed_arb_signals(ts) WHERE outcome IS NULL;
```

- [ ] **Step 2: Mirror the same SQL into `scripts/init-trading-tables.sql`**

Append the same `CREATE TABLE` + indexes verbatim.

- [ ] **Step 3: Run schema parity test**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/test_storage/test_schema_parity.py -v --tb=short --timeout=30
```

Expected: PASS. If FAIL, the two sources don't match — fix before commit.

- [ ] **Step 4: Commit**

```bash
git add trading/storage/db.py scripts/init-trading-tables.sql
git commit -m "feat(feeds): add feed_arb_signals table"
```

### Task 1.2: Add `feed_arb_pnl_rollup` table (real + scaled)

**Files:**
- Modify: `trading/storage/db.py` (`_INIT_DDL` string)
- Modify: `scripts/init-trading-tables.sql`

- [ ] **Step 1: Append to `_INIT_DDL`**

```sql
CREATE TABLE IF NOT EXISTS feed_arb_pnl_rollup (
    rollup_ts TIMESTAMPTZ PRIMARY KEY,
    realized_pnl_usd NUMERIC(12,2) NOT NULL,
    open_pnl_usd NUMERIC(12,2) NOT NULL,
    cumulative_pnl_usd NUMERIC(12,2) NOT NULL,
    open_position_count INT NOT NULL,
    closed_position_count INT NOT NULL,
    scaled_realized_pnl_usd NUMERIC(14,2) NOT NULL,
    scaled_open_pnl_usd NUMERIC(14,2) NOT NULL,
    scaled_cumulative_pnl_usd NUMERIC(14,2) NOT NULL,
    scaling_assumption TEXT NOT NULL
);
```

- [ ] **Step 2: Mirror into `scripts/init-trading-tables.sql`**

- [ ] **Step 3: Run schema parity test**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/test_storage/test_schema_parity.py -v --tb=short --timeout=30
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add trading/storage/db.py scripts/init-trading-tables.sql
git commit -m "feat(feeds): add feed_arb_pnl_rollup table (real + scaled)"
```

### Task 1.3: Add `stripe_processed_events` and `signal_order_map` tables

**Files:**
- Modify: `trading/storage/db.py`
- Modify: `scripts/init-trading-tables.sql`

- [ ] **Step 1: Append both tables to `_INIT_DDL`**

```sql
CREATE TABLE IF NOT EXISTS stripe_processed_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    result TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_order_map (
    order_hash TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    venue TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_signal_order_map_signal ON signal_order_map(signal_id);
```

- [ ] **Step 2: Mirror into `scripts/init-trading-tables.sql`**

- [ ] **Step 3: Run schema parity test**

Same command as Task 1.1 step 3. Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add trading/storage/db.py scripts/init-trading-tables.sql
git commit -m "feat(billing,feeds): add stripe_processed_events + signal_order_map tables"
```

### Task 1.4: Boot the trading container with new schema

**Files:** none (deployment verification)

- [ ] **Step 1: Restart trading service**

```bash
docker compose restart trading
```

Wait ~30s for startup.

- [ ] **Step 2: Verify tables exist in Postgres**

```bash
docker exec agent-memory-unified-postgres-1 psql -U postgres -d agent_memory -c "
  SELECT tablename FROM pg_tables
  WHERE tablename IN ('feed_arb_signals', 'feed_arb_pnl_rollup', 'stripe_processed_events', 'signal_order_map')
  ORDER BY tablename;
"
```

Expected: 4 rows returned.

- [ ] **Step 3: If <4 rows, check trading logs for `init_db_postgres` errors**

```bash
docker compose logs trading --tail 200 | grep -i "init_db\|create table\|error"
```

Common gotcha: SQLite-style syntax (e.g., `AUTOINCREMENT`) aborts asyncpg's `executescript` and silently drops subsequent tables (per `reference_init_db_postgres_ddl_abort`). The DDL above uses pure Postgres syntax, so this should not fire.

---

## Phase 2 — Scope vocabulary

Per CLAUDE.md: scope additions require updating `conductor/tracks/agent_identity/spec.md` §3.C **first**, before any code references the new scope.

### Task 2.1: Add `read:feeds.arb` scope to identity spec

**Files:**
- Modify: `conductor/tracks/agent_identity/spec.md` (§3.C scope vocabulary table)

- [ ] **Step 1: Open the spec, locate §3.C**

Read the file and find the scope table. Identify the row pattern (e.g., `| scope_name | description |`).

- [ ] **Step 2: Add row for `read:feeds.arb`**

Insert into the scope table:
```
| `read:feeds.arb` | Read access to `/api/v1/feeds/arb/signals` (PM arb signal feed subscription) |
```

If §3.C also documents a namespace convention, add a note (or a new subsection) declaring:
```
**Namespace `read:feeds.<feed_name>`:** read scopes for paid signal/data feeds. Future scopes follow this pattern (e.g., `read:feeds.sn8`, `read:feeds.arb.webhook`). A `read:feeds.*` wildcard is reserved for bundle tiers; not yet implemented.
```

- [ ] **Step 3: Commit**

```bash
git add conductor/tracks/agent_identity/spec.md
git commit -m "spec(identity): add read:feeds.arb scope + feeds.* namespace convention"
```

---

## Phase 3 — Signal ID plumbing

`signal_id` (ULID) flows from the strategy through both execution legs so PnL attribution can join fills back to the originating signal.

### Task 3.1: Add ULID generator utility

**Files:**
- Create: `trading/utils/ids.py`
- Test: `trading/tests/unit/utils/test_ids.py`

- [ ] **Step 1: Write the failing test**

Create `trading/tests/unit/utils/test_ids.py`:

```python
from trading.utils.ids import new_signal_id

def test_new_signal_id_is_26_chars():
    sid = new_signal_id()
    assert len(sid) == 26  # ULID is 26 chars in Crockford base32

def test_new_signal_id_is_unique():
    ids = {new_signal_id() for _ in range(1000)}
    assert len(ids) == 1000

def test_new_signal_ids_are_lexicographically_increasing():
    import time
    a = new_signal_id()
    time.sleep(0.001)
    b = new_signal_id()
    assert a < b  # ULID monotonicity
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/utils/test_ids.py -v --tb=short --timeout=30
```

Expected: FAIL with `ModuleNotFoundError: No module named 'trading.utils.ids'`.

- [ ] **Step 3: Add `ulid-py` dependency**

Modify `trading/pyproject.toml` — add `"ulid-py>=1.1"` to the `dependencies` array (alphabetical order). Then:

```bash
docker compose build trading
```

(`pip install` inside the container would also work, but a clean rebuild is the documented pattern per `reference_docker_restart_vs_build`.)

- [ ] **Step 4: Implement `trading/utils/ids.py`**

```python
"""ID generation utilities."""
from __future__ import annotations

import ulid


def new_signal_id() -> str:
    """Return a fresh ULID as a 26-char Crockford base32 string.

    ULIDs are lexicographically sortable by creation time and crash-safe to
    generate without coordination — suitable as opaque public signal_ids.
    """
    return str(ulid.new())
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/utils/test_ids.py -v --tb=short --timeout=30
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add trading/utils/ids.py trading/tests/unit/utils/test_ids.py trading/pyproject.toml
git commit -m "feat(utils): add ULID-based signal_id generator"
```

### Task 3.2: Plumb `client_order_id` through Kalshi client

**Files:**
- Modify: `trading/adapters/kalshi/client.py` (`create_order` method, ~line 160)
- Test: `trading/tests/unit/adapters/test_kalshi_client.py` (create if missing)

- [ ] **Step 1: Write the failing test**

Add to `trading/tests/unit/adapters/test_kalshi_client.py`:

```python
import pytest
from unittest.mock import AsyncMock
from trading.adapters.kalshi.client import KalshiClient

@pytest.mark.asyncio
async def test_create_order_includes_client_order_id_when_provided():
    client = KalshiClient(api_key="test", api_secret="test")
    client._post = AsyncMock(return_value={"order_id": "k_123"})

    await client.create_order(
        ticker="KXPRES-2024-DJT",
        side="yes",
        count=10,
        price=55,
        client_order_id="01HXX0K9TQVS5N7E2QF7P9V8XQ",
    )

    body = client._post.call_args.args[1]
    assert body["client_order_id"] == "01HXX0K9TQVS5N7E2QF7P9V8XQ"

@pytest.mark.asyncio
async def test_create_order_omits_client_order_id_when_absent():
    client = KalshiClient(api_key="test", api_secret="test")
    client._post = AsyncMock(return_value={"order_id": "k_123"})

    await client.create_order(ticker="KXTEST", side="yes", count=1, price=50)

    body = client._post.call_args.args[1]
    assert "client_order_id" not in body
```

- [ ] **Step 2: Run test, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/adapters/test_kalshi_client.py -v --tb=short --timeout=30
```

Expected: FAIL — `client_order_id` parameter doesn't exist on `create_order`.

- [ ] **Step 3: Modify `KalshiClient.create_order` signature and body**

In `trading/adapters/kalshi/client.py`, locate `create_order` (around line 160) and add the parameter + body field:

```python
async def create_order(
    self,
    ticker: str,
    side: str,
    count: int,
    price: int,
    order_type: str = "limit",
    expiration_ts: int | None = None,
    client_order_id: str | None = None,
) -> dict:
    body = {
        "ticker": ticker,
        "action": "buy",
        "side": side,
        "count": count,
        "type": order_type,
    }
    if order_type == "limit":
        body["yes_price"] = price if side == "yes" else (100 - price)
    if expiration_ts:
        body["expiration_ts"] = expiration_ts
    if client_order_id:
        body["client_order_id"] = client_order_id
    return await self._post("/portfolio/orders", body)
```

- [ ] **Step 4: Run tests, verify pass**

Same command as step 2. Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add trading/adapters/kalshi/client.py trading/tests/unit/adapters/test_kalshi_client.py
git commit -m "feat(kalshi): plumb optional client_order_id through create_order"
```

### Task 3.3: Polymarket order-hash → signal_id persistence

**Files:**
- Create: `trading/feeds/order_map.py`
- Test: `trading/tests/unit/feeds/test_order_map.py`

- [ ] **Step 1: Write the failing test**

Create `trading/tests/unit/feeds/test_order_map.py`:

```python
import pytest
from trading.feeds.order_map import OrderMap

@pytest.mark.asyncio
async def test_record_and_lookup(pg_pool):
    om = OrderMap(pg_pool)
    await om.record(order_hash="0xabc", signal_id="01HXXSIG", venue="polymarket")
    result = await om.lookup("0xabc")
    assert result == "01HXXSIG"

@pytest.mark.asyncio
async def test_lookup_missing_returns_none(pg_pool):
    om = OrderMap(pg_pool)
    assert await om.lookup("0xnonexistent") is None

@pytest.mark.asyncio
async def test_record_is_idempotent(pg_pool):
    om = OrderMap(pg_pool)
    await om.record(order_hash="0xdup", signal_id="sig1", venue="polymarket")
    # re-recording same hash with different signal_id is a no-op (first wins)
    await om.record(order_hash="0xdup", signal_id="sig2", venue="polymarket")
    assert await om.lookup("0xdup") == "sig1"
```

(Assumes `pg_pool` fixture exists in `trading/tests/conftest.py`. If not, the integration tests under `trading/tests/integration/` use it — copy the fixture pattern.)

- [ ] **Step 2: Run test, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/feeds/test_order_map.py -v --tb=short --timeout=30
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `trading/feeds/order_map.py`**

```python
"""Maps Polymarket order hashes back to originating signal_ids.

Polymarket EIP-712 orders do not round-trip a free-text identifier, so we
must persist the (order_hash → signal_id) mapping ourselves to attribute
fills back to the signal that produced them.
"""
from __future__ import annotations

import asyncpg


class OrderMap:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record(self, *, order_hash: str, signal_id: str, venue: str) -> None:
        """Persist an order_hash → signal_id mapping. First write wins (idempotent)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO signal_order_map (order_hash, signal_id, venue)
                VALUES ($1, $2, $3)
                ON CONFLICT (order_hash) DO NOTHING
                """,
                order_hash,
                signal_id,
                venue,
            )

    async def lookup(self, order_hash: str) -> str | None:
        """Return the signal_id for a given order_hash, or None if not mapped."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT signal_id FROM signal_order_map WHERE order_hash = $1",
                order_hash,
            )
            return row["signal_id"] if row else None
```

- [ ] **Step 4: Run tests, verify pass**

Same command as step 2. Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add trading/feeds/order_map.py trading/tests/unit/feeds/test_order_map.py
git commit -m "feat(feeds): add OrderMap for polymarket order_hash → signal_id"
```

### Task 3.4: Wire `signal_id` through cross_platform_arb strategy + Polymarket broker

**Files:**
- Modify: `trading/strategies/cross_platform_arb.py` (signal generation)
- Modify: `trading/adapters/polymarket/broker.py` (order_hash extraction)
- Test: `trading/tests/unit/strategies/test_cross_platform_arb_signal_id.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""Verify signal_id flows from strategy → both execution legs."""
from unittest.mock import AsyncMock, patch

import pytest

from trading.strategies.cross_platform_arb import CrossPlatformArbStrategy


@pytest.mark.asyncio
async def test_signal_carries_ulid_signal_id():
    strategy = CrossPlatformArbStrategy(parameters={"threshold_cents": 1})
    # mock the matching internals so we can inspect emitted signals
    with patch.object(strategy, "_find_arb_pairs", AsyncMock(return_value=[
        {
            "kalshi": {"ticker": "KXTEST", "side": "yes", "price_cents": 45},
            "polymarket": {"token_id": "0xtoken", "side": "no", "price_cents": 50},
            "edge_cents": 5.0,
            "max_size_at_edge_usd": 1500.0,
        }
    ])):
        signals = await strategy.generate_signals()

    assert len(signals) == 1
    sig = signals[0]
    assert "signal_id" in sig
    assert len(sig["signal_id"]) == 26  # ULID
```

- [ ] **Step 2: Run test, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/strategies/test_cross_platform_arb_signal_id.py -v --tb=short --timeout=30
```

Expected: FAIL — either `signal_id` missing or method name mismatch.

- [ ] **Step 3: Modify `cross_platform_arb.py` to attach `signal_id` to every emitted signal**

In `trading/strategies/cross_platform_arb.py`, locate the signal-emission code (likely a `generate_signals` method or similar) and import the ULID helper:

```python
from trading.utils.ids import new_signal_id
```

In the signal-construction code, add `signal_id`:
```python
signal = {
    "signal_id": new_signal_id(),
    "ts": datetime.now(timezone.utc).isoformat(),
    "pair": {...},
    "edge_cents": pair["edge_cents"],
    "max_size_at_edge_usd": pair["max_size_at_edge_usd"],
    "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
}
```

(Match the field names declared in spec §3.2 / §4.2.)

- [ ] **Step 4: Run test, verify pass**

Same command. Expected: 1 passed.

- [ ] **Step 5: In the strategy's executor section, pass `signal_id` to both legs**

When constructing the Kalshi order, pass `client_order_id=signal["signal_id"]`. When constructing the Polymarket order, pass `signal_id` to the broker so it can record the order-hash mapping.

For Polymarket — modify `trading/adapters/polymarket/broker.py` `place_order` (or equivalent):

```python
async def place_order(
    self,
    *,
    token_id: str,
    side: str,
    size: float,
    price: float,
    signal_id: str | None = None,
) -> dict:
    signed_order = self._client.create_order(...)  # existing EIP-712 signing
    order_hash = signed_order["order_hash"]  # field name per py_clob_client; verify
    if signal_id and self._order_map is not None:
        await self._order_map.record(
            order_hash=order_hash, signal_id=signal_id, venue="polymarket"
        )
    return await self._client.post_order(signed_order)
```

(`self._order_map` is the `OrderMap` instance; injected via constructor in step 6.)

- [ ] **Step 6: Inject `OrderMap` into PolymarketBroker constructor**

Modify `PolymarketBroker.__init__` to accept `order_map: OrderMap | None = None` and store it. Update construction sites (search for `PolymarketBroker(` in the codebase) to pass an `OrderMap(pg_pool)` instance.

- [ ] **Step 7: Verify the field name `order_hash` matches what `py_clob_client` actually returns**

```bash
docker exec agent-memory-unified-trading-1 trading/.venv/bin/python -c "
from py_clob_client.client import ClobClient
import inspect
print(inspect.getsource(ClobClient.create_order))
" 2>&1 | head -50
```

If the field is named differently (`hash`, `salt`, `signature`, etc.), update the `signed_order["order_hash"]` access in step 5 accordingly.

- [ ] **Step 8: Commit**

```bash
git add trading/strategies/cross_platform_arb.py trading/adapters/polymarket/broker.py trading/tests/unit/strategies/test_cross_platform_arb_signal_id.py
git commit -m "feat(arb): plumb signal_id through cross_platform_arb to both legs"
```

---

## Phase 4 — Feed publisher

`feed_publisher` subscribes to the `SignalBus`, persists each `cross_platform_arb` signal to `feed_arb_signals`, and is wired into the FastAPI lifespan as a long-running task.

### Task 4.1: Implement `FeedPublisher` class

**Files:**
- Create: `trading/feeds/publisher.py`
- Test: `trading/tests/unit/feeds/test_publisher.py`

- [ ] **Step 1: Write the failing test**

```python
import json

import pytest

from trading.data.signal_bus import SignalBus
from trading.feeds.publisher import FeedPublisher


@pytest.mark.asyncio
async def test_publisher_persists_arb_signals(pg_pool):
    bus = SignalBus()
    publisher = FeedPublisher(bus=bus, pool=pg_pool)
    await publisher.start()

    signal = {
        "strategy": "cross_platform_arb",
        "signal_id": "01HXXSIG000000000000000001",
        "ts": "2026-04-15T14:32:00+00:00",
        "pair": {
            "kalshi": {"ticker": "KXTEST", "side": "yes"},
            "polymarket": {"token_id": "0xabc", "side": "no"},
        },
        "edge_cents": 4.2,
        "max_size_at_edge_usd": 1500.0,
        "expires_at": "2026-04-15T14:37:00+00:00",
    }
    await bus.publish(signal)

    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM feed_arb_signals WHERE signal_id = $1",
            signal["signal_id"],
        )

    assert row is not None
    assert row["edge_cents"] == 4.2
    assert row["pair_kalshi_ticker"] == "KXTEST"
    assert row["outcome"] is None  # pending


@pytest.mark.asyncio
async def test_publisher_ignores_non_arb_signals(pg_pool):
    bus = SignalBus()
    publisher = FeedPublisher(bus=bus, pool=pg_pool)
    await publisher.start()

    await bus.publish({"strategy": "snapback_scalper", "signal_id": "nope"})

    async with pg_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM feed_arb_signals WHERE signal_id = 'nope'"
        )
    assert count == 0
```

- [ ] **Step 2: Run test, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/feeds/test_publisher.py -v --tb=short --timeout=30
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `trading/feeds/publisher.py`**

```python
"""Persist cross_platform_arb signals from the SignalBus into feed_arb_signals.

This is the source-of-truth feed table behind both the public dashboard and
the paid subscriber API.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import asyncpg

from trading.data.signal_bus import SignalBus

logger = logging.getLogger(__name__)


class FeedPublisher:
    def __init__(self, *, bus: SignalBus, pool: asyncpg.Pool) -> None:
        self._bus = bus
        self._pool = pool

    async def start(self) -> None:
        """Subscribe to the SignalBus. Idempotent: safe to call multiple times."""
        self._bus.subscribe(self._on_signal)
        logger.info("FeedPublisher subscribed to SignalBus")

    async def _on_signal(self, signal: dict[str, Any]) -> None:
        if signal.get("strategy") != "cross_platform_arb":
            return
        try:
            await self._persist(signal)
        except Exception:  # noqa: BLE001
            logger.exception("FeedPublisher failed to persist signal_id=%s", signal.get("signal_id"))

    async def _persist(self, signal: dict[str, Any]) -> None:
        pair = signal["pair"]
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feed_arb_signals (
                    signal_id, ts, pair_kalshi_ticker, pair_kalshi_side,
                    pair_poly_token_id, pair_poly_side, edge_cents,
                    max_size_at_edge_usd, expires_at, raw_signal
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (signal_id) DO NOTHING
                """,
                signal["signal_id"],
                datetime.fromisoformat(signal["ts"]),
                pair["kalshi"]["ticker"],
                pair["kalshi"]["side"],
                pair["polymarket"]["token_id"],
                pair["polymarket"]["side"],
                signal["edge_cents"],
                signal["max_size_at_edge_usd"],
                datetime.fromisoformat(signal["expires_at"]),
                json.dumps(signal),
            )
```

(Note `datetime.fromisoformat(...)` not the raw string — per `reference_asyncpg_datetime` rule, asyncpg wants datetime objects.)

- [ ] **Step 4: Run tests, verify pass**

Same command. Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add trading/feeds/publisher.py trading/tests/unit/feeds/test_publisher.py
git commit -m "feat(feeds): add FeedPublisher subscribing arb signals to feed_arb_signals"
```

### Task 4.2: Wire `FeedPublisher` into FastAPI lifespan

**Files:**
- Modify: `trading/api/app.py` (lifespan function)

- [ ] **Step 1: Locate the lifespan setup**

Find the `lifespan` async context manager in `trading/api/app.py`. Identify where the `SignalBus` is constructed (search for `SignalBus(`) and where `task_mgr.create_task(...)` is called for other background tasks.

- [ ] **Step 2: Add publisher startup after SignalBus + DB pool are ready**

After the lines that initialize `signal_bus` and the asyncpg pool (referenced as `app.state.pg_pool` or similar — verify), add:

```python
from trading.feeds.publisher import FeedPublisher

feed_publisher = FeedPublisher(bus=signal_bus, pool=app.state.pg_pool)
await feed_publisher.start()
app.state.feed_publisher = feed_publisher
log_event(logger, logging.INFO, "feeds.publisher.started", "FeedPublisher subscribed to SignalBus")
```

(`feed_publisher` does not need its own background task — it's purely a subscription. The bus drives it.)

- [ ] **Step 3: Restart trading container and verify startup log**

```bash
docker compose restart trading
sleep 5
docker compose logs trading --tail 100 | grep -i "feedpublisher\|feeds.publisher"
```

Expected: log line "FeedPublisher subscribed to SignalBus".

- [ ] **Step 4: Smoke test — emit a fake arb signal, verify it lands in the table**

```bash
docker exec agent-memory-unified-trading-1 trading/.venv/bin/python -c "
import asyncio
from trading.api.app import app
async def main():
    await app.state.signal_bus.publish({
        'strategy': 'cross_platform_arb',
        'signal_id': '01HXXSMOKETEST000000000000',
        'ts': '2026-04-15T15:00:00+00:00',
        'pair': {
            'kalshi': {'ticker': 'KXSMOKE', 'side': 'yes'},
            'polymarket': {'token_id': '0xsmoke', 'side': 'no'},
        },
        'edge_cents': 1.5,
        'max_size_at_edge_usd': 100.0,
        'expires_at': '2026-04-15T15:05:00+00:00',
    })
asyncio.run(main())
"

docker exec agent-memory-unified-postgres-1 psql -U postgres -d agent_memory -c "
  SELECT signal_id, edge_cents FROM feed_arb_signals WHERE signal_id = '01HXXSMOKETEST000000000000';
"
```

Expected: 1 row with `edge_cents = 1.50`. (If the smoke-test row doesn't appear, the lifespan didn't actually wire the publisher. Re-check step 2.)

- [ ] **Step 5: Clean up smoke-test row + commit**

```bash
docker exec agent-memory-unified-postgres-1 psql -U postgres -d agent_memory -c "
  DELETE FROM feed_arb_signals WHERE signal_id = '01HXXSMOKETEST000000000000';
"
git add trading/api/app.py
git commit -m "feat(feeds): wire FeedPublisher into FastAPI lifespan"
```

---

## Phase 5 — Subscriber API

REST endpoint behind `read:feeds.arb` scope, with `next_since` cursor and 600/hr rate limit tier.

### Task 5.1: Add `feed_subscriber` rate-limit tier

**Files:**
- Modify: `trading/api/middleware/limiter.py`
- Test: `trading/tests/unit/api/middleware/test_limiter_tiers.py` (create)

- [ ] **Step 1: Write the failing test**

```python
from trading.api.middleware.limiter import _resolve_identity_for_tier  # adjust if name differs


def test_feed_subscriber_tier_limit():
    """feed_subscriber tier returns 600/hour limit."""
    # construct a fake identity / agent record with tier='feed_subscriber'
    # and assert _resolve returns the right limit
    from types import SimpleNamespace
    agent = SimpleNamespace(name="sub_test", tier="feed_subscriber")
    result = _resolve_identity_for_tier(agent)
    assert result.limit == "600/hour"
    assert "feed_subscriber" in result.key
```

(The exact helper name in `limiter.py` may differ — read the file first to identify the resolution function. If `_resolve_identity` is private and complex, write the test against the public middleware instead.)

- [ ] **Step 2: Run test, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/api/middleware/test_limiter_tiers.py -v --tb=short --timeout=30
```

Expected: FAIL — tier branch doesn't exist.

- [ ] **Step 3: Add `feed_subscriber` branch in `_resolve_identity`**

In `trading/api/middleware/limiter.py`, in the function that maps an agent record to a `RateLimitIdentity`, add:

```python
if agent and agent.tier == "feed_subscriber":
    return RateLimitIdentity(
        key=f"tier:feed_subscriber:{agent.name}",
        limit="600/hour",
    )
```

Place it adjacent to the existing tier branches, before the generic fallback.

- [ ] **Step 4: Run test, verify pass**

Same command. Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add trading/api/middleware/limiter.py trading/tests/unit/api/middleware/test_limiter_tiers.py
git commit -m "feat(api): add feed_subscriber rate-limit tier (600/hour)"
```

### Task 5.2: Implement subscriber API route

**Files:**
- Create: `trading/api/routes/feeds.py`
- Test: `trading/tests/unit/api/routes/test_feeds_signals.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from fastapi.testclient import TestClient

from trading.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_signals_route_requires_scope(client, identity_without_feed_scope):
    """Without read:feeds.arb scope, returns 403."""
    response = client.get(
        "/api/v1/feeds/arb/signals",
        params={"since": "2026-04-15T00:00:00Z"},
        headers={"X-API-Key": identity_without_feed_scope.token},
    )
    assert response.status_code == 403


def test_signals_route_returns_signals_with_scope(client, identity_with_feed_scope, seeded_signal):
    """With scope, returns matching signals + cursor."""
    response = client.get(
        "/api/v1/feeds/arb/signals",
        params={"since": "2026-04-15T00:00:00Z", "limit": 100},
        headers={"X-API-Key": identity_with_feed_scope.token},
    )
    assert response.status_code == 200
    body = response.json()
    assert "signals" in body
    assert "next_since" in body
    assert "truncated" in body
    assert any(s["signal_id"] == seeded_signal["signal_id"] for s in body["signals"])


def test_cursor_paginates_when_truncated(client, identity_with_feed_scope, seed_n_signals):
    """Emit 600 signals, request limit=500, get truncated=True + next_since."""
    seed_n_signals(600)
    r1 = client.get(
        "/api/v1/feeds/arb/signals",
        params={"since": "2026-04-15T00:00:00Z", "limit": 500},
        headers={"X-API-Key": identity_with_feed_scope.token},
    )
    assert r1.json()["truncated"] is True
    assert len(r1.json()["signals"]) == 500
    next_since = r1.json()["next_since"]

    r2 = client.get(
        "/api/v1/feeds/arb/signals",
        params={"since": next_since, "limit": 500},
        headers={"X-API-Key": identity_with_feed_scope.token},
    )
    assert r2.json()["truncated"] is False
    assert len(r2.json()["signals"]) == 100
```

(The `identity_with_feed_scope` and `seed_n_signals` fixtures need to live in `trading/tests/conftest.py` — add them there if they don't exist. Pattern: `IdentityStore.create(name="test_sub", token_hash=..., scopes=["read:feeds.arb"], tier="feed_subscriber")`.)

- [ ] **Step 2: Run test, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/api/routes/test_feeds_signals.py -v --tb=short --timeout=30
```

Expected: FAIL — 404 (route doesn't exist).

- [ ] **Step 3: Implement `trading/api/routes/feeds.py`**

```python
"""Public + subscriber feed routes for /api/v1/feeds/arb/*"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from trading.api.identity.dependencies import Identity, require_scope

router = APIRouter(prefix="/api/v1/feeds/arb", tags=["feeds"])


class SignalPair(BaseModel):
    kalshi: dict
    polymarket: dict


class SignalOut(BaseModel):
    signal_id: str
    ts: str
    pair: SignalPair
    edge_cents: float
    max_size_at_edge_usd: float
    expires_at: str


class SignalsResponse(BaseModel):
    signals: list[SignalOut]
    next_since: str
    truncated: bool


@router.get(
    "/signals",
    response_model=SignalsResponse,
    dependencies=[Depends(require_scope("read:feeds.arb"))],
)
async def get_signals(
    request: Request,
    since: Annotated[datetime, Query(description="ISO-8601 timestamp")],
    limit: int = Query(100, ge=1, le=500),
) -> SignalsResponse:
    pool = request.app.state.pg_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT signal_id, ts, pair_kalshi_ticker, pair_kalshi_side,
                   pair_poly_token_id, pair_poly_side, edge_cents,
                   max_size_at_edge_usd, expires_at
            FROM feed_arb_signals
            WHERE ts >= $1
            ORDER BY ts ASC
            LIMIT $2
            """,
            since,
            limit + 1,  # +1 to detect truncation
        )

    truncated = len(rows) > limit
    rows = rows[:limit]

    signals = [
        SignalOut(
            signal_id=r["signal_id"],
            ts=r["ts"].isoformat(),
            pair=SignalPair(
                kalshi={"ticker": r["pair_kalshi_ticker"], "side": r["pair_kalshi_side"]},
                polymarket={"token_id": r["pair_poly_token_id"], "side": r["pair_poly_side"]},
            ),
            edge_cents=float(r["edge_cents"]),
            max_size_at_edge_usd=float(r["max_size_at_edge_usd"]),
            expires_at=r["expires_at"].isoformat(),
        )
        for r in rows
    ]

    if truncated:
        next_since = rows[-1]["ts"].isoformat()
    elif rows:
        next_since = rows[-1]["ts"].isoformat()
    else:
        next_since = since.isoformat()

    return SignalsResponse(signals=signals, next_since=next_since, truncated=truncated)
```

- [ ] **Step 4: Mount the router in `trading/api/app.py`**

Find where other routers are included (search for `app.include_router(`) and add:

```python
from trading.api.routes import feeds
app.include_router(feeds.router)
```

- [ ] **Step 5: Run tests, verify pass**

Same command as step 2. Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add trading/api/routes/feeds.py trading/api/app.py trading/tests/unit/api/routes/test_feeds_signals.py trading/tests/conftest.py
git commit -m "feat(api): add /api/v1/feeds/arb/signals subscriber route + cursor"
```

### Task 5.3: Implement `/api/v1/feeds/arb/public` (no auth, CORS pinned)

**Files:**
- Modify: `trading/api/routes/feeds.py` (add second route)
- Modify: `trading/api/app.py` (CORS config)
- Test: extend `test_feeds_signals.py`

- [ ] **Step 1: Write the failing test**

Add to the existing `test_feeds_signals.py`:

```python
def test_public_route_requires_no_auth(client, seeded_signal, seeded_pnl_rollup):
    response = client.get("/api/v1/feeds/arb/public")
    assert response.status_code == 200
    body = response.json()
    assert "recent_signals" in body
    assert "pnl" in body
    assert "real" in body["pnl"]
    assert "scaled" in body["pnl"]


def test_public_route_cors_allows_remembr_dev(client):
    response = client.options(
        "/api/v1/feeds/arb/public",
        headers={"Origin": "https://remembr.dev", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert "remembr.dev" in response.headers.get("access-control-allow-origin", "")


def test_public_route_cors_rejects_other_origins(client):
    response = client.options(
        "/api/v1/feeds/arb/public",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    # rejected origin should not echo back in allow-origin header
    assert "evil.example" not in response.headers.get("access-control-allow-origin", "")
```

- [ ] **Step 2: Run, verify failure**

Same command. Expected: 3 failures (route 404 + CORS not configured).

- [ ] **Step 3: Add the public route to `feeds.py`**

```python
class PublicPnL(BaseModel):
    real: dict
    scaled: dict


class PublicResponse(BaseModel):
    recent_signals: list[SignalOut]
    pnl: PublicPnL
    backtest_envelope: list[dict]
    last_updated: str


@router.get("/public", response_model=PublicResponse)
async def get_public(request: Request) -> PublicResponse:
    pool = request.app.state.pg_pool
    async with pool.acquire() as conn:
        signal_rows = await conn.fetch(
            """
            SELECT signal_id, ts, pair_kalshi_ticker, pair_kalshi_side,
                   pair_poly_token_id, pair_poly_side, edge_cents,
                   max_size_at_edge_usd, expires_at, outcome
            FROM feed_arb_signals
            ORDER BY ts DESC LIMIT 50
            """
        )
        pnl_row = await conn.fetchrow(
            "SELECT * FROM feed_arb_pnl_rollup ORDER BY rollup_ts DESC LIMIT 1"
        )

    signals = [
        SignalOut(
            signal_id=r["signal_id"],
            ts=r["ts"].isoformat(),
            pair=SignalPair(
                kalshi={"ticker": r["pair_kalshi_ticker"], "side": r["pair_kalshi_side"]},
                polymarket={"token_id": r["pair_poly_token_id"], "side": r["pair_poly_side"]},
            ),
            edge_cents=float(r["edge_cents"]),
            max_size_at_edge_usd=float(r["max_size_at_edge_usd"]),
            expires_at=r["expires_at"].isoformat(),
        )
        for r in signal_rows
    ]

    if pnl_row:
        pnl = PublicPnL(
            real={
                "realized_usd": float(pnl_row["realized_pnl_usd"]),
                "open_usd": float(pnl_row["open_pnl_usd"]),
                "cumulative_usd": float(pnl_row["cumulative_pnl_usd"]),
                "open_positions": pnl_row["open_position_count"],
                "closed_positions": pnl_row["closed_position_count"],
            },
            scaled={
                "realized_usd": float(pnl_row["scaled_realized_pnl_usd"]),
                "open_usd": float(pnl_row["scaled_open_pnl_usd"]),
                "cumulative_usd": float(pnl_row["scaled_cumulative_pnl_usd"]),
                "scaling_assumption": pnl_row["scaling_assumption"],
            },
        )
        last_updated = pnl_row["rollup_ts"].isoformat()
    else:
        pnl = PublicPnL(real={}, scaled={})
        last_updated = ""

    return PublicResponse(
        recent_signals=signals,
        pnl=pnl,
        backtest_envelope=[],  # populated by Phase 6 follow-up; empty for now
        last_updated=last_updated,
    )
```

- [ ] **Step 4: Configure CORS in `trading/api/app.py`**

Find existing `CORSMiddleware` configuration. Update `allow_origins` to include `https://remembr.dev`. If a stricter per-route policy is needed, use FastAPI's per-route response middleware. Simplest: add `https://remembr.dev` and `http://localhost:3000` to the global allow-list.

- [ ] **Step 5: Run tests, verify pass**

Same command. Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add trading/api/routes/feeds.py trading/api/app.py trading/tests/unit/api/routes/test_feeds_signals.py
git commit -m "feat(api): add public /api/v1/feeds/arb/public + CORS pinning"
```

---

## Phase 6 — PnL attribution

60-second job that pulls fills, joins to `signal_id`, computes real + scaled PnL, writes to `feed_arb_pnl_rollup`, and updates `outcome` on signals.

### Task 6.1: Implement real-PnL attribution

**Files:**
- Create: `trading/feeds/pnl_attribution.py`
- Test: `trading/tests/unit/feeds/test_pnl_attribution.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from datetime import datetime, timezone

from trading.feeds.pnl_attribution import compute_real_pnl


def test_realized_pnl_from_closed_pair():
    """A closed Kalshi+Polymarket pair: realized = entry_cost - exit_proceeds (signed)."""
    fills = [
        {"signal_id": "sig1", "venue": "kalshi", "side": "buy", "qty": 10, "price_cents": 45, "ts": "2026-04-15T14:32:00Z"},
        {"signal_id": "sig1", "venue": "polymarket", "side": "buy", "qty": 10, "price_cents": 50, "ts": "2026-04-15T14:32:01Z"},
        # at close (yes resolved at 100, no resolved at 0):
        {"signal_id": "sig1", "venue": "kalshi", "side": "sell", "qty": 10, "price_cents": 100, "ts": "2026-04-15T15:00:00Z"},
        {"signal_id": "sig1", "venue": "polymarket", "side": "sell", "qty": 10, "price_cents": 0, "ts": "2026-04-15T15:00:01Z"},
    ]
    pnl = compute_real_pnl(fills, marks={})
    assert pnl["realized_usd"] == pytest.approx(0.50)  # (100-45) - (50-0) = 5 cents/share × 10 = $0.50
    assert pnl["open_usd"] == 0.0
    assert pnl["closed_position_count"] == 1


def test_open_pnl_marked_to_market():
    """An open pair with current marks computes open_pnl as mark - entry."""
    fills = [
        {"signal_id": "sig2", "venue": "kalshi", "side": "buy", "qty": 5, "price_cents": 40, "ts": "2026-04-15T14:00:00Z"},
        {"signal_id": "sig2", "venue": "polymarket", "side": "buy", "qty": 5, "price_cents": 55, "ts": "2026-04-15T14:00:01Z"},
    ]
    marks = {"kalshi:KXTEST:yes": 50, "polymarket:0xtok:no": 60}
    # signal needs venue+symbol info; for test, encode via marks dict
    pnl = compute_real_pnl(
        fills,
        marks=marks,
        symbol_lookup={"sig2": {"kalshi": "KXTEST:yes", "polymarket": "0xtok:no"}},
    )
    # open: kalshi (50-40) + polymarket (60-55) = 15 cents × 5 = $0.75
    assert pnl["open_usd"] == pytest.approx(0.75)
    assert pnl["realized_usd"] == 0.0
    assert pnl["open_position_count"] == 1
```

- [ ] **Step 2: Run, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/feeds/test_pnl_attribution.py -v --tb=short --timeout=30
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `compute_real_pnl`**

Create `trading/feeds/pnl_attribution.py`:

```python
"""PnL attribution: join fills to signals, compute realized + open PnL."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def compute_real_pnl(
    fills: list[dict[str, Any]],
    marks: dict[str, int] | None = None,
    symbol_lookup: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Compute realized + open PnL from a list of fills grouped by signal_id.

    Args:
        fills: list of fill dicts with keys signal_id, venue, side, qty, price_cents
        marks: dict of "venue:symbol:side" -> current mid price in cents (for open positions)
        symbol_lookup: dict of signal_id -> {venue: "symbol:side"} for mark lookup

    Returns:
        dict with realized_usd, open_usd, cumulative_usd, open_position_count,
        closed_position_count.
    """
    marks = marks or {}
    symbol_lookup = symbol_lookup or {}

    # group fills by signal_id and venue; track running net qty per (signal, venue)
    by_signal: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for f in fills:
        by_signal[f["signal_id"]][f["venue"]].append(f)

    realized_cents = 0
    open_cents = 0
    open_count = 0
    closed_count = 0

    for sig_id, by_venue in by_signal.items():
        # a "closed" pair = both Kalshi and Polymarket legs have net qty == 0
        # (i.e., entries matched by exits)
        is_closed = True
        for venue, vfills in by_venue.items():
            net_qty = sum(f["qty"] if f["side"] == "buy" else -f["qty"] for f in vfills)
            if net_qty != 0:
                is_closed = False

        if is_closed:
            closed_count += 1
            # realized = sum of (sell_proceeds - buy_costs) across both legs
            for venue, vfills in by_venue.items():
                for f in vfills:
                    sign = +1 if f["side"] == "sell" else -1
                    realized_cents += sign * f["qty"] * f["price_cents"]
        else:
            open_count += 1
            # open: net entry cost vs current mark (if available)
            for venue, vfills in by_venue.items():
                net_qty = sum(f["qty"] if f["side"] == "buy" else -f["qty"] for f in vfills)
                avg_entry_cents = (
                    sum(f["qty"] * f["price_cents"] for f in vfills if f["side"] == "buy")
                    / sum(f["qty"] for f in vfills if f["side"] == "buy")
                ) if any(f["side"] == "buy" for f in vfills) else 0
                mark_key = f"{venue}:{symbol_lookup.get(sig_id, {}).get(venue, '')}"
                mark = marks.get(mark_key)
                if mark is not None:
                    open_cents += net_qty * (mark - avg_entry_cents)

    return {
        "realized_usd": realized_cents / 100.0,
        "open_usd": open_cents / 100.0,
        "cumulative_usd": (realized_cents + open_cents) / 100.0,
        "open_position_count": open_count,
        "closed_position_count": closed_count,
    }
```

- [ ] **Step 4: Run tests, verify pass**

Same command. Expected: 2 passed. (If math is off, debug — the test values are based on the algebraic identity stated in the docstring.)

- [ ] **Step 5: Commit**

```bash
git add trading/feeds/pnl_attribution.py trading/tests/unit/feeds/test_pnl_attribution.py
git commit -m "feat(feeds): compute_real_pnl — realized + open from fills"
```

### Task 6.2: Implement scaled-PnL projection

**Files:**
- Modify: `trading/feeds/pnl_attribution.py` (add `compute_scaled_pnl`)
- Test: extend `test_pnl_attribution.py`

- [ ] **Step 1: Write the failing test**

```python
def test_scaled_pnl_linear_to_target_capped_by_depth():
    """Scaled to $250k: each fill scaled proportionally, capped by orderbook depth."""
    fills = [
        {"signal_id": "sig1", "venue": "kalshi", "side": "buy", "qty": 10, "price_cents": 45, "ts": "..."},
        {"signal_id": "sig1", "venue": "polymarket", "side": "buy", "qty": 10, "price_cents": 50, "ts": "..."},
        {"signal_id": "sig1", "venue": "kalshi", "side": "sell", "qty": 10, "price_cents": 100, "ts": "..."},
        {"signal_id": "sig1", "venue": "polymarket", "side": "sell", "qty": 10, "price_cents": 0, "ts": "..."},
    ]
    # signal had max_size_at_edge_usd = 1500, so scaling factor at $250k is min(250000/sleeve_size, 1500/observed_size)
    # observed entry cost = 10 × 95 cents = $9.50; sleeve_size assumption $11000
    # naive scale factor = 250000 / 11000 = ~22.7×
    # capped by depth: max additional notional = 1500/9.50 = ~157× (no cap binds)
    # so scaled = 22.7 × $0.50 ≈ $11.36
    scaled = compute_scaled_pnl(
        fills,
        signal_max_size={"sig1": 1500.0},
        sleeve_size_usd=11000.0,
        target_notional_usd=250000.0,
    )
    assert scaled["realized_usd"] == pytest.approx(11.36, abs=0.05)
    assert scaled["scaling_assumption"].startswith("linear-to-250k")
```

- [ ] **Step 2: Run, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/feeds/test_pnl_attribution.py::test_scaled_pnl_linear_to_target_capped_by_depth -v --tb=short --timeout=30
```

Expected: FAIL — function doesn't exist.

- [ ] **Step 3: Implement `compute_scaled_pnl`**

Add to `trading/feeds/pnl_attribution.py`:

```python
def compute_scaled_pnl(
    fills: list[dict[str, Any]],
    signal_max_size: dict[str, float],
    sleeve_size_usd: float,
    target_notional_usd: float,
    marks: dict[str, int] | None = None,
    symbol_lookup: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Project real-sleeve PnL to a larger notional book, capped by orderbook depth.

    Each signal's PnL is scaled by min(target/sleeve, signal_max_size / observed_size).
    The depth cap prevents over-projecting against thin books.
    """
    real = compute_real_pnl(fills, marks=marks, symbol_lookup=symbol_lookup)

    # naive scale factor
    naive_factor = target_notional_usd / sleeve_size_usd if sleeve_size_usd > 0 else 0

    # per-signal depth-capped factor
    by_signal_observed_usd: dict[str, float] = defaultdict(float)
    for f in fills:
        if f["side"] == "buy":
            by_signal_observed_usd[f["signal_id"]] += f["qty"] * f["price_cents"] / 100.0

    # weight: signals with tighter depth caps contribute their capped factor
    weighted_factor_sum = 0.0
    weight_sum = 0.0
    for sig_id, observed_usd in by_signal_observed_usd.items():
        max_size = signal_max_size.get(sig_id, observed_usd * naive_factor)
        depth_factor = max_size / observed_usd if observed_usd > 0 else naive_factor
        capped_factor = min(naive_factor, depth_factor)
        weighted_factor_sum += capped_factor * observed_usd
        weight_sum += observed_usd

    effective_factor = (weighted_factor_sum / weight_sum) if weight_sum > 0 else naive_factor

    return {
        "realized_usd": real["realized_usd"] * effective_factor,
        "open_usd": real["open_usd"] * effective_factor,
        "cumulative_usd": real["cumulative_usd"] * effective_factor,
        "scaling_assumption": (
            f"linear-to-{int(target_notional_usd/1000)}k-with-observed-slippage-v1; "
            f"effective_factor={effective_factor:.2f}; sleeve=${sleeve_size_usd:.0f}"
        ),
    }
```

- [ ] **Step 4: Run tests, verify pass**

Same command. Expected: 1 passed (or fix the math if the assertion is off — the depth-cap logic above is the spec interpretation).

- [ ] **Step 5: Commit**

```bash
git add trading/feeds/pnl_attribution.py trading/tests/unit/feeds/test_pnl_attribution.py
git commit -m "feat(feeds): compute_scaled_pnl — linear-to-target with depth cap"
```

### Task 6.3: Outcome tagging

**Files:**
- Modify: `trading/feeds/pnl_attribution.py` (add `update_signal_outcomes`)
- Test: extend `test_pnl_attribution.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_signal_outcome_set_to_filled_when_both_legs_fill(pg_pool, seeded_signal):
    from trading.feeds.pnl_attribution import update_signal_outcomes
    fills = [
        {"signal_id": seeded_signal["signal_id"], "venue": "kalshi", "side": "buy", "qty": 10, "price_cents": 45},
        {"signal_id": seeded_signal["signal_id"], "venue": "polymarket", "side": "buy", "qty": 10, "price_cents": 50},
    ]
    await update_signal_outcomes(pg_pool, fills=fills, now_iso="2026-04-15T14:33:00+00:00")

    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT outcome FROM feed_arb_signals WHERE signal_id = $1",
            seeded_signal["signal_id"],
        )
    assert row["outcome"] == "filled"


@pytest.mark.asyncio
async def test_signal_outcome_set_to_missed_when_expired_with_no_fills(pg_pool, seeded_expired_signal):
    from trading.feeds.pnl_attribution import update_signal_outcomes
    await update_signal_outcomes(pg_pool, fills=[], now_iso="2026-04-15T16:00:00+00:00")

    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT outcome FROM feed_arb_signals WHERE signal_id = $1",
            seeded_expired_signal["signal_id"],
        )
    assert row["outcome"] == "missed"
```

- [ ] **Step 2: Run, verify failure**

Same command. Expected: FAIL.

- [ ] **Step 3: Implement `update_signal_outcomes`**

Add to `trading/feeds/pnl_attribution.py`:

```python
from datetime import datetime

import asyncpg


async def update_signal_outcomes(
    pool: asyncpg.Pool,
    *,
    fills: list[dict[str, Any]],
    now_iso: str,
) -> None:
    """Set outcome on pending signals.

    - filled: both legs (kalshi + polymarket) have at least one fill
    - missed: signal expired (now > expires_at) with <2 legs filled
    - dead_book_skipped: set by executor at decision time, not here

    Pending signals (within expires_at, no fills yet) are left as NULL.
    """
    now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))

    # tally fills per signal/venue
    legs_filled: dict[str, set[str]] = defaultdict(set)
    for f in fills:
        legs_filled[f["signal_id"]].add(f["venue"])

    async with pool.acquire() as conn:
        # mark filled
        for sig_id, venues in legs_filled.items():
            if "kalshi" in venues and "polymarket" in venues:
                await conn.execute(
                    """
                    UPDATE feed_arb_signals
                    SET outcome = 'filled', outcome_set_at = $2
                    WHERE signal_id = $1 AND outcome IS NULL
                    """,
                    sig_id,
                    now,
                )
        # mark missed (expired pending)
        await conn.execute(
            """
            UPDATE feed_arb_signals
            SET outcome = 'missed', outcome_set_at = $1
            WHERE outcome IS NULL AND expires_at < $1
            """,
            now,
        )
```

- [ ] **Step 4: Run tests, verify pass**

Same command. Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add trading/feeds/pnl_attribution.py trading/tests/unit/feeds/test_pnl_attribution.py
git commit -m "feat(feeds): outcome tagging (filled/missed) for feed_arb_signals"
```

### Task 6.4: Wire attribution job into lifespan (60s tick)

**Files:**
- Modify: `trading/feeds/pnl_attribution.py` (add `run_attribution_loop`)
- Modify: `trading/api/app.py` (lifespan)

- [ ] **Step 1: Add the loop driver to `pnl_attribution.py`**

```python
import asyncio
import logging

from trading.feeds.order_map import OrderMap

logger = logging.getLogger(__name__)


async def run_attribution_loop(
    *,
    pool: asyncpg.Pool,
    order_map: OrderMap,
    fill_fetcher,  # callable: async () -> list[fill_dict]; injected for testability
    mark_fetcher,  # callable: async () -> dict[str, int]
    sleeve_size_usd: float = 11000.0,
    target_notional_usd: float = 250000.0,
    interval_seconds: int = 60,
) -> None:
    """Run the PnL attribution loop forever."""
    while True:
        try:
            await _run_one_tick(
                pool=pool,
                order_map=order_map,
                fill_fetcher=fill_fetcher,
                mark_fetcher=mark_fetcher,
                sleeve_size_usd=sleeve_size_usd,
                target_notional_usd=target_notional_usd,
            )
        except Exception:  # noqa: BLE001
            logger.exception("PnL attribution tick failed; skipping rollup write")
        await asyncio.sleep(interval_seconds)


async def _run_one_tick(*, pool, order_map, fill_fetcher, mark_fetcher,
                         sleeve_size_usd, target_notional_usd) -> None:
    fills = await fill_fetcher()
    marks = await mark_fetcher()

    # join fills to signal_id (Kalshi: client_order_id; Polymarket: order_map lookup)
    enriched = []
    for f in fills:
        if f["venue"] == "kalshi" and f.get("client_order_id"):
            f["signal_id"] = f["client_order_id"]
        elif f["venue"] == "polymarket" and f.get("order_hash"):
            sig = await order_map.lookup(f["order_hash"])
            if sig is None:
                logger.warning(
                    "attribution.unmatched_fill venue=polymarket hash=%s",
                    f["order_hash"],
                )
                continue
            f["signal_id"] = sig
        else:
            continue
        enriched.append(f)

    real = compute_real_pnl(enriched, marks=marks)

    # signal_max_size lookup for scaling
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT signal_id, max_size_at_edge_usd FROM feed_arb_signals "
            "WHERE signal_id = ANY($1::text[])",
            list({f["signal_id"] for f in enriched}),
        )
    signal_max_size = {r["signal_id"]: float(r["max_size_at_edge_usd"]) for r in rows}

    scaled = compute_scaled_pnl(
        enriched,
        signal_max_size=signal_max_size,
        sleeve_size_usd=sleeve_size_usd,
        target_notional_usd=target_notional_usd,
        marks=marks,
    )

    # write rollup
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO feed_arb_pnl_rollup (
                rollup_ts, realized_pnl_usd, open_pnl_usd, cumulative_pnl_usd,
                open_position_count, closed_position_count,
                scaled_realized_pnl_usd, scaled_open_pnl_usd, scaled_cumulative_pnl_usd,
                scaling_assumption
            ) VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            real["realized_usd"],
            real["open_usd"],
            real["cumulative_usd"],
            real["open_position_count"],
            real["closed_position_count"],
            scaled["realized_usd"],
            scaled["open_usd"],
            scaled["cumulative_usd"],
            scaled["scaling_assumption"],
        )

    await update_signal_outcomes(pool, fills=enriched, now_iso=datetime.now().isoformat())
```

- [ ] **Step 2: Wire into lifespan in `trading/api/app.py`**

After SignalBus + pool + OrderMap are ready:

```python
from trading.feeds.pnl_attribution import run_attribution_loop
from trading.feeds.order_map import OrderMap
from trading.adapters.kalshi.fills import fetch_recent_fills as kalshi_fetch_fills
from trading.adapters.polymarket.fills import fetch_recent_fills as poly_fetch_fills
from trading.adapters.kalshi.marks import fetch_marks as kalshi_marks
from trading.adapters.polymarket.marks import fetch_marks as poly_marks

order_map = OrderMap(app.state.pg_pool)
app.state.order_map = order_map

async def _fetch_all_fills():
    return (await kalshi_fetch_fills()) + (await poly_fetch_fills())

async def _fetch_all_marks():
    return {**(await kalshi_marks()), **(await poly_marks())}

task_mgr.create_task(
    run_attribution_loop(
        pool=app.state.pg_pool,
        order_map=order_map,
        fill_fetcher=_fetch_all_fills,
        mark_fetcher=_fetch_all_marks,
    ),
    name="pnl_attribution_loop",
)
```

(`fetch_recent_fills` and `fetch_marks` adapters may need to be created if they don't exist. Check `trading/adapters/kalshi/` and `trading/adapters/polymarket/` first; if absent, write thin wrappers around the existing client/broker classes that return the canonical fill-dict shape `{venue, signal_id?, side, qty, price_cents, client_order_id?, order_hash?, ts}`.)

- [ ] **Step 3: Restart trading and verify the loop logs ticks**

```bash
docker compose restart trading
sleep 90  # wait for at least one full tick
docker compose logs trading --tail 200 | grep -i "pnl_attribution\|rollup"
```

Expected: at least one rollup write log, no "tick failed" exceptions. (If failures: investigate the fill/mark fetchers — most likely culprit is missing adapter functions.)

- [ ] **Step 4: Verify a rollup row exists**

```bash
docker exec agent-memory-unified-postgres-1 psql -U postgres -d agent_memory -c "
  SELECT rollup_ts, realized_pnl_usd, scaled_realized_pnl_usd, scaling_assumption
  FROM feed_arb_pnl_rollup ORDER BY rollup_ts DESC LIMIT 3;
"
```

Expected: ≥1 row.

- [ ] **Step 5: Commit**

```bash
git add trading/feeds/pnl_attribution.py trading/api/app.py trading/adapters/
git commit -m "feat(feeds): wire 60s PnL attribution loop into lifespan"
```

---

## Phase 7 — Stripe integration

Single product, single recurring price, idempotent webhook with `stripe_processed_events` table, hourly reconciliation, manual escape-hatch endpoint.

### Task 7.1: Add Stripe SDK + config

**Files:**
- Modify: `trading/pyproject.toml`
- Modify: `trading/config.py`
- Modify: `trading/.env.example` (if it exists, add the new vars)

- [ ] **Step 1: Add `stripe` to dependencies**

In `trading/pyproject.toml`, add `"stripe>=8.0"` to the `dependencies` array.

- [ ] **Step 2: Add config fields**

In `trading/config.py`, add to the config dataclass:

```python
stripe_secret_key: str | None = None
stripe_webhook_secret: str | None = None
stripe_price_id_default: str | None = None
stripe_price_id_founding: str | None = None
```

(`load_config()` strips the `STA_` prefix automatically per `reference_sta_env_var_convention`.)

- [ ] **Step 3: Rebuild and verify import**

```bash
docker compose build trading && docker compose up -d trading
sleep 10
docker exec agent-memory-unified-trading-1 trading/.venv/bin/python -c "import stripe; print(stripe.__version__)"
```

Expected: prints a version string ≥ 8.0.

- [ ] **Step 4: Commit**

```bash
git add trading/pyproject.toml trading/config.py trading/.env.example
git commit -m "feat(billing): add Stripe SDK + STA_STRIPE_* config fields"
```

### Task 7.2: Stripe checkout endpoint

**Files:**
- Create: `trading/api/routes/billing/checkout.py`
- Modify: `trading/api/routes/billing/__init__.py` (router include)
- Test: `trading/tests/unit/api/routes/test_billing_checkout.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from trading.api.app import app


def test_create_checkout_returns_url():
    client = TestClient(app)
    fake_session = MagicMock(url="https://checkout.stripe.com/test_xyz")
    with patch("stripe.checkout.Session.create", return_value=fake_session):
        response = client.post(
            "/api/v1/billing/stripe/checkout",
            json={"plan": "default"},
        )
    assert response.status_code == 200
    assert response.json()["url"] == "https://checkout.stripe.com/test_xyz"


def test_create_checkout_rejects_unknown_plan():
    client = TestClient(app)
    response = client.post(
        "/api/v1/billing/stripe/checkout",
        json={"plan": "platinum"},
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/api/routes/test_billing_checkout.py -v --tb=short --timeout=30
```

Expected: FAIL — 404.

- [ ] **Step 3: Implement the checkout route**

Create `trading/api/routes/billing/checkout.py`:

```python
"""Stripe checkout session creation."""
from __future__ import annotations

import stripe
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from trading.config import load_config

router = APIRouter(prefix="/api/v1/billing/stripe", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan: str  # "default" or "founding"


class CheckoutResponse(BaseModel):
    url: str


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(payload: CheckoutRequest, request: Request) -> CheckoutResponse:
    cfg = load_config()
    stripe.api_key = cfg.stripe_secret_key

    if payload.plan == "default":
        price_id = cfg.stripe_price_id_default
    elif payload.plan == "founding":
        price_id = cfg.stripe_price_id_founding
    else:
        raise HTTPException(status_code=400, detail=f"unknown plan: {payload.plan}")

    if not price_id:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url="https://remembr.dev/feeds/arb/welcome?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://remembr.dev/feeds/arb",
        allow_promotion_codes=True,
    )
    return CheckoutResponse(url=session.url)
```

- [ ] **Step 4: Mount the router in `trading/api/app.py`**

```python
from trading.api.routes.billing import checkout as billing_checkout
app.include_router(billing_checkout.router)
```

- [ ] **Step 5: Run tests, verify pass**

Same command. Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add trading/api/routes/billing/checkout.py trading/api/app.py trading/tests/unit/api/routes/test_billing_checkout.py
git commit -m "feat(billing): add /api/v1/billing/stripe/checkout endpoint"
```

### Task 7.3: Stripe webhook with idempotency

**Files:**
- Create: `trading/api/routes/billing/webhook.py` (or extend existing `webhooks.py`)
- Test: `trading/tests/unit/api/routes/test_billing_webhook.py`
- Test fixtures: `trading/tests/fixtures/stripe/checkout_completed.json`

- [ ] **Step 1: Capture a Stripe test event fixture**

```bash
mkdir -p /opt/agent-memory-unified/trading/tests/fixtures/stripe
```

Manually craft `trading/tests/fixtures/stripe/checkout_completed.json` (Stripe's test-event payload format — capture from `stripe-cli trigger` if available, or hand-write minimal valid payload):

```json
{
  "id": "evt_test_001",
  "type": "checkout.session.completed",
  "data": {
    "object": {
      "id": "cs_test_001",
      "subscription": "sub_test_001",
      "customer": "cus_test_001",
      "customer_email": "alice@example.com",
      "metadata": {}
    }
  }
}
```

- [ ] **Step 2: Write the failing test**

```python
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from trading.api.app import app

FIXTURE = Path(__file__).parent.parent.parent.parent / "fixtures/stripe/checkout_completed.json"


def _post_webhook(client, payload, signature="t=1,v1=test_sig"):
    return client.post(
        "/api/v1/billing/stripe/webhook",
        data=json.dumps(payload),
        headers={"stripe-signature": signature, "content-type": "application/json"},
    )


@pytest.mark.asyncio
async def test_webhook_provisions_scope_on_checkout_completed(monkeypatch, pg_pool, identity_store):
    monkeypatch.setattr("stripe.Webhook.construct_event", lambda body, sig, secret: json.loads(body))
    payload = json.loads(FIXTURE.read_text())
    client = TestClient(app)

    response = _post_webhook(client, payload)
    assert response.status_code == 200

    # verify identity provisioned
    agent = await identity_store.get_by_name("sub_sub_test_001")
    assert agent is not None
    assert "read:feeds.arb" in agent.scopes
    assert agent.tier == "feed_subscriber"


@pytest.mark.asyncio
async def test_webhook_idempotent_on_replay(monkeypatch, pg_pool):
    monkeypatch.setattr("stripe.Webhook.construct_event", lambda body, sig, secret: json.loads(body))
    payload = json.loads(FIXTURE.read_text())
    client = TestClient(app)

    r1 = _post_webhook(client, payload)
    r2 = _post_webhook(client, payload)
    assert r1.status_code == 200
    assert r2.status_code == 200

    async with pg_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM stripe_processed_events WHERE event_id = $1",
            payload["id"],
        )
    assert count == 1  # only stored once
```

- [ ] **Step 3: Run, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/api/routes/test_billing_webhook.py -v --tb=short --timeout=30
```

Expected: FAIL — route 404 or scope provisioning missing.

- [ ] **Step 4: Implement the webhook**

Create `trading/api/routes/billing/webhook.py`:

```python
"""Stripe webhook handler — idempotent provisioning."""
from __future__ import annotations

import hashlib
import logging
import secrets

import stripe
from fastapi import APIRouter, HTTPException, Header, Request

from trading.config import load_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/billing/stripe", tags=["billing"])


@router.post("/webhook")
async def webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    cfg = load_config()
    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            body, stripe_signature, cfg.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="invalid signature")

    pool = request.app.state.pg_pool

    # Idempotency check
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO stripe_processed_events (event_id, event_type, result) "
                "VALUES ($1, $2, 'pending')",
                event["id"],
                event["type"],
            )
        except Exception as e:  # asyncpg.UniqueViolationError
            if "stripe_processed_events_pkey" in str(e):
                logger.info("stripe.webhook.duplicate event_id=%s", event["id"])
                return {"received": True, "duplicate": True}
            raise

    try:
        result = await _handle_event(event, request.app)
    except Exception:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE stripe_processed_events SET result = 'error' WHERE event_id = $1",
                event["id"],
            )
        raise
    else:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE stripe_processed_events SET result = $2 WHERE event_id = $1",
                event["id"],
                result,
            )

    return {"received": True}


async def _handle_event(event: dict, app) -> str:
    if event["type"] == "checkout.session.completed":
        return await _provision_subscription(event["data"]["object"], app)
    elif event["type"] == "customer.subscription.deleted":
        return await _revoke_subscription(event["data"]["object"], app)
    elif event["type"] == "customer.subscription.updated":
        return "noop"  # no-op for v1 (no plan changes supported)
    return "noop"


async def _provision_subscription(session: dict, app) -> str:
    sub_id = session["subscription"]
    customer_id = session["customer"]
    email = session.get("customer_email", "")
    agent_name = f"sub_{sub_id}"

    # generate API key (token) and hash for storage
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    identity_store = app.state.identity_store
    await identity_store.create(
        name=agent_name,
        token_hash=token_hash,
        scopes=["read:feeds.arb"],
        tier="feed_subscriber",
        contact_email=email,
        metadata={"stripe_customer_id": customer_id, "stripe_subscription_id": sub_id},
    )

    # log to dedicated channel for manual emailing (per spec §6.1)
    logger.info(
        "billing.new_subscription email=%s sub_id=%s api_key=%s "
        "agent_name=%s — *** EMAIL THIS KEY MANUALLY ***",
        email, sub_id, raw_token, agent_name,
    )
    return "ok"


async def _revoke_subscription(subscription: dict, app) -> str:
    sub_id = subscription["id"]
    agent_name = f"sub_{sub_id}"
    identity_store = app.state.identity_store
    try:
        await identity_store.revoke(name=agent_name, reason="stripe_cancellation", actor="stripe_webhook")
    except Exception:
        logger.warning("billing.revoke_failed agent_name=%s — already revoked or missing", agent_name)
    return "ok"
```

- [ ] **Step 5: Mount the webhook router**

In `trading/api/app.py`:
```python
from trading.api.routes.billing import webhook as billing_webhook
app.include_router(billing_webhook.router)
```

- [ ] **Step 6: Run tests, verify pass**

Same command. Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add trading/api/routes/billing/webhook.py trading/api/app.py trading/tests/unit/api/routes/test_billing_webhook.py trading/tests/fixtures/stripe/
git commit -m "feat(billing): idempotent Stripe webhook provisioning read:feeds.arb"
```

### Task 7.4: Hourly reconciliation + manual endpoint

**Files:**
- Create: `trading/billing/reconciliation.py`
- Create: `trading/api/routes/billing/admin.py`
- Test: `trading/tests/unit/billing/test_reconciliation.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import patch, AsyncMock

from trading.billing.reconciliation import reconcile_subscriptions


@pytest.mark.asyncio
async def test_reconcile_provisions_missing_scope(pg_pool, identity_store):
    """Active Stripe sub with no identity → identity provisioned."""
    fake_subs = [{"id": "sub_orphan_1", "customer": "cus_1", "status": "active"}]
    with patch("stripe.Subscription.list") as mock_list:
        mock_list.return_value.auto_paging_iter.return_value = iter(fake_subs)
        result = await reconcile_subscriptions(pool=pg_pool, identity_store=identity_store)
    assert result["provisioned"] == 1

    agent = await identity_store.get_by_name("sub_sub_orphan_1")
    assert agent is not None
    assert "read:feeds.arb" in agent.scopes


@pytest.mark.asyncio
async def test_reconcile_revokes_orphaned_scope(pg_pool, identity_store):
    """Identity with read:feeds.arb but no active Stripe sub → revoked."""
    await identity_store.create(
        name="sub_sub_zombie", token_hash="x", scopes=["read:feeds.arb"], tier="feed_subscriber",
    )
    with patch("stripe.Subscription.list") as mock_list:
        mock_list.return_value.auto_paging_iter.return_value = iter([])
        result = await reconcile_subscriptions(pool=pg_pool, identity_store=identity_store)
    assert result["revoked"] == 1

    agent = await identity_store.get_by_name("sub_sub_zombie")
    assert agent.revoked_at is not None
```

- [ ] **Step 2: Run, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/billing/test_reconciliation.py -v --tb=short --timeout=30
```

Expected: FAIL.

- [ ] **Step 3: Implement reconciliation**

Create `trading/billing/reconciliation.py`:

```python
"""Hourly Stripe reconciliation: catch missed webhooks."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets

import asyncpg
import stripe

from trading.api.identity.store import IdentityStore
from trading.config import load_config

logger = logging.getLogger(__name__)


async def reconcile_subscriptions(
    *, pool: asyncpg.Pool, identity_store: IdentityStore,
) -> dict[str, int]:
    cfg = load_config()
    stripe.api_key = cfg.stripe_secret_key

    active_subs = list(stripe.Subscription.list(status="active").auto_paging_iter())
    active_sub_ids = {s["id"] for s in active_subs}

    provisioned = 0
    revoked = 0

    # provision missing
    for sub in active_subs:
        agent_name = f"sub_{sub['id']}"
        existing = await identity_store.get_by_name(agent_name)
        if existing is None or existing.revoked_at is not None:
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            await identity_store.create(
                name=agent_name, token_hash=token_hash,
                scopes=["read:feeds.arb"], tier="feed_subscriber",
                metadata={"stripe_subscription_id": sub["id"], "reconciled": True},
            )
            logger.info(
                "reconciliation.provisioned agent=%s api_key=%s — *** EMAIL MANUALLY ***",
                agent_name, raw_token,
            )
            provisioned += 1

    # revoke orphans
    async with pool.acquire() as conn:
        zombie_rows = await conn.fetch(
            "SELECT name FROM identity.agents "
            "WHERE 'read:feeds.arb' = ANY(scopes) AND revoked_at IS NULL"
        )
    for row in zombie_rows:
        agent_name = row["name"]
        sub_id = agent_name.replace("sub_", "", 1)
        if sub_id not in active_sub_ids:
            await identity_store.revoke(
                name=agent_name, reason="reconciliation_orphan", actor="reconciliation_job",
            )
            revoked += 1

    return {"provisioned": provisioned, "revoked": revoked}


async def run_reconciliation_loop(*, pool, identity_store, interval_seconds: int = 3600) -> None:
    while True:
        try:
            result = await reconcile_subscriptions(pool=pool, identity_store=identity_store)
            logger.info("reconciliation.tick %s", result)
        except Exception:
            logger.exception("reconciliation tick failed")
        await asyncio.sleep(interval_seconds)
```

- [ ] **Step 4: Add admin endpoint**

Create `trading/api/routes/billing/admin.py`:

```python
"""Admin escape-hatch endpoint for manual reconciliation."""
from fastapi import APIRouter, Depends, Request

from trading.api.identity.dependencies import require_scope
from trading.billing.reconciliation import reconcile_subscriptions

router = APIRouter(prefix="/api/v1/admin/billing", tags=["admin"])


@router.post("/reconcile", dependencies=[Depends(require_scope("admin"))])
async def manual_reconcile(request: Request):
    return await reconcile_subscriptions(
        pool=request.app.state.pg_pool,
        identity_store=request.app.state.identity_store,
    )
```

- [ ] **Step 5: Wire reconciliation loop + admin router**

In `trading/api/app.py`:
```python
from trading.billing.reconciliation import run_reconciliation_loop
from trading.api.routes.billing import admin as billing_admin

task_mgr.create_task(
    run_reconciliation_loop(pool=app.state.pg_pool, identity_store=app.state.identity_store),
    name="stripe_reconciliation",
)
app.include_router(billing_admin.router)
```

- [ ] **Step 6: Run tests, verify pass**

Same command. Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add trading/billing/reconciliation.py trading/api/routes/billing/admin.py trading/api/app.py trading/tests/unit/billing/
git commit -m "feat(billing): hourly Stripe reconciliation + manual /admin/billing/reconcile"
```

---

## Phase 8 — Frontend dashboard + landing page

React 19 + Vite + TanStack Query, modeled on existing Mission Control patterns.

### Task 8.1: API client for feeds

**Files:**
- Create: `frontend/src/lib/api/feeds.ts`

- [ ] **Step 1: Implement the client**

```typescript
import { tradingApi } from './tradingApi';  // existing axios instance

export interface ArbSignal {
  signal_id: string;
  ts: string;
  pair: {
    kalshi: { ticker: string; side: string };
    polymarket: { token_id: string; side: string };
  };
  edge_cents: number;
  max_size_at_edge_usd: number;
  expires_at: string;
  outcome?: 'filled' | 'missed' | 'dead_book_skipped' | null;
}

export interface PublicPnL {
  real: {
    realized_usd: number;
    open_usd: number;
    cumulative_usd: number;
    open_positions: number;
    closed_positions: number;
  };
  scaled: {
    realized_usd: number;
    open_usd: number;
    cumulative_usd: number;
    scaling_assumption: string;
  };
}

export interface PublicResponse {
  recent_signals: ArbSignal[];
  pnl: PublicPnL;
  backtest_envelope: any[];
  last_updated: string;
}

export async function fetchPublicArbFeed(): Promise<PublicResponse> {
  const { data } = await tradingApi.get<PublicResponse>('/api/v1/feeds/arb/public');
  return data;
}
```

- [ ] **Step 2: Commit (no test — pure type/client glue, covered by integration tests in Task 8.4)**

```bash
git add frontend/src/lib/api/feeds.ts
git commit -m "feat(frontend): add feeds API client + types"
```

### Task 8.2: TanStack Query hook

**Files:**
- Create: `frontend/src/hooks/useFeedArb.ts`

- [ ] **Step 1: Implement the hook**

```typescript
import { useQuery } from '@tanstack/react-query';
import { fetchPublicArbFeed, PublicResponse } from '@/lib/api/feeds';

export function useFeedArb() {
  return useQuery<PublicResponse>({
    queryKey: ['feeds', 'arb', 'public'],
    queryFn: fetchPublicArbFeed,
    refetchInterval: 10_000,  // 10s per spec §3.1
    staleTime: 5_000,
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useFeedArb.ts
git commit -m "feat(frontend): add useFeedArb TanStack Query hook"
```

### Task 8.3: Public dashboard page

**Files:**
- Create: `frontend/src/pages/FeedArbLive.tsx`
- Modify: `frontend/src/App.tsx` (route)

- [ ] **Step 1: Implement the page**

```tsx
import { useFeedArb } from '@/hooks/useFeedArb';

export default function FeedArbLive() {
  const { data, isLoading, error } = useFeedArb();

  if (isLoading) return <div>Loading…</div>;
  if (error) return <div>Failed to load feed</div>;
  if (!data) return null;

  const stale = data.last_updated
    ? Date.now() - new Date(data.last_updated).getTime() > 5 * 60_000
    : true;

  return (
    <div className="container">
      <h1>remembr.dev — PM Arb Live Feed</h1>
      {stale && <div className="stale-warning">⚠ Data stale (last updated {data.last_updated})</div>}

      <section className="pnl-exhibits">
        <PnlExhibit
          title="Real (sleeve: $11k)"
          realized={data.pnl.real.realized_usd}
          open={data.pnl.real.open_usd}
          cumulative={data.pnl.real.cumulative_usd}
        />
        <PnlExhibit
          title="Scaled to $250k notional (model projection)"
          realized={data.pnl.scaled.realized_usd}
          open={data.pnl.scaled.open_usd}
          cumulative={data.pnl.scaled.cumulative_usd}
          subtitle={data.pnl.scaled.scaling_assumption}
        />
        <BacktestEnvelope data={data.backtest_envelope} />
      </section>

      <section className="signal-stream">
        <h2>Recent signals</h2>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Kalshi</th>
              <th>Polymarket</th>
              <th>Edge (¢)</th>
              <th>Max Size ($)</th>
              <th>Outcome</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_signals.map((s) => (
              <tr key={s.signal_id}>
                <td>{new Date(s.ts).toLocaleTimeString()}</td>
                <td>{s.pair.kalshi.ticker} ({s.pair.kalshi.side})</td>
                <td>{s.pair.polymarket.token_id.slice(0, 8)}… ({s.pair.polymarket.side})</td>
                <td>{s.edge_cents.toFixed(2)}</td>
                <td>${s.max_size_at_edge_usd.toFixed(0)}</td>
                <td><OutcomeBadge outcome={s.outcome} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function PnlExhibit({ title, realized, open, cumulative, subtitle }: {
  title: string; realized: number; open: number; cumulative: number; subtitle?: string;
}) {
  return (
    <div className="pnl-exhibit">
      <h3>{title}</h3>
      {subtitle && <p className="subtitle">{subtitle}</p>}
      <dl>
        <dt>Realized</dt><dd>${realized.toFixed(2)}</dd>
        <dt>Open</dt><dd>${open.toFixed(2)}</dd>
        <dt>Cumulative</dt><dd>${cumulative.toFixed(2)}</dd>
      </dl>
    </div>
  );
}

function BacktestEnvelope({ data }: { data: any[] }) {
  return (
    <div className="pnl-exhibit">
      <h3>Backtest envelope (90d)</h3>
      <p>Coming soon.</p>
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: ArbSignal['outcome'] }) {
  if (!outcome) return <span className="badge pending">pending</span>;
  return <span className={`badge ${outcome}`}>{outcome}</span>;
}
```

- [ ] **Step 2: Add route in `frontend/src/App.tsx`**

Find the route definitions (likely a `<Routes>` block) and add:

```tsx
<Route path="/feeds/arb/live" element={<FeedArbLive />} />
```

Add the corresponding import.

- [ ] **Step 3: Manually verify in browser**

```bash
cd frontend && npx vite --host 0.0.0.0 --port 3000
```

Open `http://localhost:3000/feeds/arb/live` — verify the page renders with PnL exhibits and the recent-signals table. If `recent_signals` is empty (no signals yet), the table headers should still render.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/FeedArbLive.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add /feeds/arb/live public dashboard"
```

### Task 8.4: Landing page

**Files:**
- Create: `frontend/src/pages/FeedArbLanding.tsx`
- Modify: `frontend/src/App.tsx` (route)

- [ ] **Step 1: Implement the landing page**

```tsx
import { useFeedArb } from '@/hooks/useFeedArb';

export default function FeedArbLanding() {
  const { data } = useFeedArb();
  const samples = data?.recent_signals.slice(0, 5) ?? [];

  return (
    <div className="container">
      <header>
        <h1>Cross-platform PM arbitrage signals</h1>
        <p>Real-time edge between Kalshi and Polymarket. Verifiable PnL on every signal.</p>
      </header>

      <section className="pricing">
        <div className="price-card">
          <h2>$500 / month</h2>
          <ul>
            <li>30-second-fresh REST signal feed</li>
            <li>600 requests/hour</li>
            <li>Public PnL dashboard you can audit</li>
            <li>Cancel anytime</li>
          </ul>
          <p className="founding">Founding-member promo: <strong>$300/mo locked 12 months</strong> (limited)</p>
        </div>
      </section>

      <section className="design-partners">
        <h2>Apply for free 60-day access</h2>
        <p>We're onboarding 5 design partners ahead of paid launch (week 11). In exchange for weekly feedback, you get the feed free for 60 days and lock the $300/mo founding rate.</p>
        <p>Email <a href="mailto:matthew.speicher@scala.com">matthew.speicher@scala.com</a> with your book size and a short note on what you'd integrate against.</p>
      </section>

      <section className="sample-signals">
        <h2>Recent signals</h2>
        {samples.length === 0 ? <p>No signals yet.</p> : (
          <ul>
            {samples.map((s) => (
              <li key={s.signal_id}>
                <code>{s.pair.kalshi.ticker}</code> vs <code>{s.pair.polymarket.token_id.slice(0,8)}</code> — {s.edge_cents.toFixed(2)}¢ edge, ${s.max_size_at_edge_usd.toFixed(0)} depth
              </li>
            ))}
          </ul>
        )}
        <p><a href="/feeds/arb/live">See the full live dashboard →</a></p>
      </section>

      <footer className="disclaimer">
        <small>
          For informational purposes only. Not investment advice. Past performance does not
          guarantee future results. Trading prediction markets carries risk including total
          loss of capital.
        </small>
      </footer>
    </div>
  );
}
```

- [ ] **Step 2: Add route in `App.tsx`**

```tsx
<Route path="/feeds/arb" element={<FeedArbLanding />} />
```

- [ ] **Step 3: Verify in browser**

Open `http://localhost:3000/feeds/arb` — pricing card, design-partner CTA, sample signals, disclaimer all visible.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/FeedArbLanding.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add /feeds/arb landing page"
```

---

## Phase 9 — Monitoring + alerting

Freshness SLI for publisher write-rate and rollup-gap detector. Wires into the existing alerting infrastructure.

### Task 9.1: Publisher freshness monitor

**Files:**
- Create: `trading/feeds/monitoring.py`
- Test: `trading/tests/unit/feeds/test_monitoring.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from datetime import datetime, timedelta, timezone
from trading.feeds.monitoring import detect_publisher_stall


@pytest.mark.asyncio
async def test_no_alert_when_publisher_writes_recently(pg_pool):
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO feed_arb_signals (signal_id, ts, pair_kalshi_ticker, pair_kalshi_side, "
            "pair_poly_token_id, pair_poly_side, edge_cents, max_size_at_edge_usd, expires_at, raw_signal) "
            "VALUES ('recent', NOW(), 'k', 'yes', 'p', 'no', 1.0, 100.0, NOW() + INTERVAL '5 min', '{}')"
        )
    result = await detect_publisher_stall(pool=pg_pool, threshold_minutes=15)
    assert result["alert"] is False


@pytest.mark.asyncio
async def test_alert_when_no_writes_for_threshold(pg_pool):
    # ensure no recent writes
    async with pg_pool.acquire() as conn:
        await conn.execute("DELETE FROM feed_arb_signals WHERE ts > NOW() - INTERVAL '1 hour'")
    result = await detect_publisher_stall(pool=pg_pool, threshold_minutes=15)
    assert result["alert"] is True
    assert "no signals" in result["reason"].lower()
```

- [ ] **Step 2: Run, verify failure**

```bash
cd /opt/agent-memory-unified && PYTHONPATH=.:trading trading/.venv/bin/python -m pytest trading/tests/unit/feeds/test_monitoring.py -v --tb=short --timeout=30
```

Expected: FAIL.

- [ ] **Step 3: Implement monitoring**

Create `trading/feeds/monitoring.py`:

```python
"""Freshness monitoring for the arb feed pipeline."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import asyncpg

logger = logging.getLogger(__name__)


async def detect_publisher_stall(*, pool: asyncpg.Pool, threshold_minutes: int = 15) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    async with pool.acquire() as conn:
        latest = await conn.fetchval("SELECT MAX(ts) FROM feed_arb_signals")
    if latest is None or latest < cutoff:
        return {
            "alert": True,
            "reason": f"No signals written in the last {threshold_minutes} minutes (latest={latest})",
            "latest_ts": latest.isoformat() if latest else None,
        }
    return {"alert": False, "latest_ts": latest.isoformat()}


async def detect_rollup_gap(*, pool: asyncpg.Pool, threshold_minutes: int = 5) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    async with pool.acquire() as conn:
        latest = await conn.fetchval("SELECT MAX(rollup_ts) FROM feed_arb_pnl_rollup")
    if latest is None or latest < cutoff:
        return {
            "alert": True,
            "reason": f"PnL rollup gap > {threshold_minutes} min (latest={latest})",
            "latest_ts": latest.isoformat() if latest else None,
        }
    return {"alert": False, "latest_ts": latest.isoformat()}


async def run_monitoring_loop(*, pool: asyncpg.Pool, interval_seconds: int = 60) -> None:
    """Run all monitors on an interval. Logs alerts; integrates with existing alerting infra."""
    while True:
        try:
            for name, check in [
                ("publisher_stall", detect_publisher_stall(pool=pool)),
                ("rollup_gap", detect_rollup_gap(pool=pool)),
            ]:
                result = await check
                if result["alert"]:
                    logger.error(
                        "feeds.monitoring.alert check=%s reason=%s",
                        name, result["reason"],
                    )
        except Exception:
            logger.exception("monitoring loop tick failed")
        await asyncio.sleep(interval_seconds)
```

- [ ] **Step 4: Wire monitoring loop into lifespan**

In `trading/api/app.py`:
```python
from trading.feeds.monitoring import run_monitoring_loop
task_mgr.create_task(
    run_monitoring_loop(pool=app.state.pg_pool),
    name="feeds_monitoring",
)
```

- [ ] **Step 5: Run tests, verify pass**

Same command. Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add trading/feeds/monitoring.py trading/api/app.py trading/tests/unit/feeds/test_monitoring.py
git commit -m "feat(feeds): publisher stall + rollup gap monitoring"
```

---

## Phase 10 — Live smoke + week-10 checklist

Manual verification before paid-tier launch. These are not code tasks but are required to pass success criteria.

### Task 10.1: Live Stripe test-mode smoke

**Files:** none (manual checklist)

- [ ] **Step 1: Configure `.env` with Stripe test-mode keys**

In `trading/.env`:
```
STA_STRIPE_SECRET_KEY=sk_test_...
STA_STRIPE_WEBHOOK_SECRET=whsec_test_...
STA_STRIPE_PRICE_ID_DEFAULT=price_test_default_id
STA_STRIPE_PRICE_ID_FOUNDING=price_test_founding_id
```

- [ ] **Step 2: Forward webhooks locally**

```bash
stripe listen --forward-to localhost:8080/api/v1/billing/stripe/webhook
```

(Capture the displayed `whsec_*` and update `.env` if it doesn't match.)

- [ ] **Step 3: Trigger checkout**

```bash
curl -X POST http://localhost:8080/api/v1/billing/stripe/checkout \
  -H 'Content-Type: application/json' \
  -d '{"plan": "default"}'
```

Open the returned URL, complete checkout with test card `4242 4242 4242 4242`.

- [ ] **Step 4: Verify provisioning + check the manual-email log**

```bash
docker compose logs trading --tail 50 | grep "billing.new_subscription"
```

Expected: log line containing `email=`, `sub_id=`, `api_key=`. Copy the api_key.

- [ ] **Step 5: Curl the subscriber endpoint with the new key**

```bash
curl -H "X-API-Key: <the_api_key>" \
  "http://localhost:8080/api/v1/feeds/arb/signals?since=2026-04-15T00:00:00Z"
```

Expected: 200 with `{"signals": [...], "next_since": "...", "truncated": false}`.

- [ ] **Step 6: Cancel via Stripe customer portal**

Use Stripe dashboard test mode → subscriptions → cancel. Verify within 60 min:

```bash
curl -H "X-API-Key: <the_api_key>" \
  "http://localhost:8080/api/v1/feeds/arb/signals?since=2026-04-15T00:00:00Z"
```

Expected: 403 (scope revoked). If still 200, manually trigger reconciliation:

```bash
curl -X POST -H "X-API-Key: <admin_key>" \
  http://localhost:8080/api/v1/admin/billing/reconcile
```

### Task 10.2: Week-10 compliance review checklist

**Files:** none (external checklist)

- [ ] Schedule one-hour consultation with a securities lawyer (~$500–1500). Specifically ask: are we an "advisor" (need registration?), "data provider," or neither? Are the disclaimers in `FeedArbLanding.tsx` sufficient?
- [ ] Review the latest Kalshi ToS for redistribution-of-derived-signals language.
- [ ] Review Polymarket ToS likewise.
- [ ] Decide entity structure (sole prop fine for v1; LLC if scaling to #5).
- [ ] If lawyer flags issues: amend disclaimers in `FeedArbLanding.tsx` before paid tier opens.

### Task 10.3: Pre-launch monitoring verification

**Files:** none (manual)

- [ ] Trigger publisher stall: stop `cross_platform_arb` agent for 20 minutes, verify alert log fires.
- [ ] Trigger rollup gap: stop `pnl_attribution_loop` task for 10 minutes, verify alert log fires.
- [ ] Restart both, verify alerts clear.
- [ ] Confirm alerts route to whatever existing channel (Slack/email) is configured. If none configured, decide before launch.

---

## Self-Review

**Spec coverage:** Each spec section maps to plan tasks:
- §3.1 public dashboard → Tasks 5.3, 8.3
- §3.2 subscriber API → Tasks 5.1, 5.2
- §3.3 landing page → Task 8.4
- §4.2 schema (3 tables → 4 incl. signal_order_map) → Tasks 1.1–1.4
- §4.3 namespaced scope → Task 2.1
- §5.1 signal_id plumbing → Tasks 3.1–3.4
- §5.2 attribution job → Tasks 6.1–6.4
- §6 Stripe → Tasks 7.1–7.4
- §6.1 manual email → Task 7.3 step 4 (logged for manual sending)
- §10.0 Step 0 gate → Task 0.1
- §10.2 compliance → Task 10.2
- §11 monitoring → Task 9.1

**Type consistency:** `signal_id` is a 26-char ULID throughout (Task 3.1 → publisher → API → frontend types). `read:feeds.arb` scope used identically in spec, identity-store provisioning, route dependency, and test fixtures. Agent name `sub_<stripe_subscription_id>` used in webhook (Task 7.3) and reconciliation (Task 7.4).

**Placeholder scan:** No `TBD` or `TODO` left in tasks. The `BacktestEnvelope` component renders "Coming soon" — that's an explicit out-of-scope choice for v1 (the backtest envelope data is post-v1 per spec §3.1; the slot is reserved in the response shape so it doesn't break the API contract when added later). All other "out of scope" items are not referenced in tasks.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-15-arb-signal-feed-implementation.md`.

Per `feedback_no_subagent_delegation` (user rejected subagent-driven-development on 2026-04-14), execution will use **superpowers:executing-plans** inline with TDD and batch checkpoints — not the per-task subagent dispatch flow.
