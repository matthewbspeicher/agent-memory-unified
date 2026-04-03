# Trading Vertical SDK — Design Spec

**Date:** 2026-03-31
**Status:** Draft
**Goal:** Design a Python SDK (`remembr_trading`) to streamline the integration of AI trading agents with the Remembr Trading Journal layer.

## Section 1: Architecture & Developer Experience

The SDK provides a `TradingJournal` class that wraps the underlying REST APIs, combining Memory creation and Trade execution into single, atomic-feeling operations. This removes boilerplate and encourages agents to consistently document their reasoning.

### Initialization
```python
from remembr_trading import TradingJournal, RetryPolicy

journal = TradingJournal(
    api_key="agent_key_...",
    paper=True, # Default to paper trading
    default_strategy="momentum_breakout",
    retry_policy=RetryPolicy(max_retries=3, backoff="exponential")
)
```

### Core Operations
```python
# Execute a new trade entry
entry_trade = journal.execute_trade(
    ticker="AAPL",
    direction="long",
    price=185.50,
    quantity=100,
    decision_reasoning="RSI crossed 30 and MACD is bullish. Entering long."
)

# Close a trade (partially or fully)
# Note: direction is implicitly inferred by the server to oppose the parent trade's direction.
exit_trade = journal.close_trade(
    parent_trade_id=entry_trade.id,
    price=192.30,
    quantity=100, # or 50 for a partial close
    outcome_reflection="Target hit. MACD started flattening, good exit."
)
```

## Section 2: Mechanics, State, & Error Handling

### 1. Stateless Architecture
The SDK is strictly stateless. All portfolio and position tracking relies on the server as the single source of truth. Queries inherit the journal's `paper` configuration but can override it per-call.

```python
# Returns list of Position objects (defaults to journal.paper)
open_aapl = journal.get_open_positions(ticker="AAPL") 

# Returns TradingStats object (explicit override)
stats = journal.get_portfolio_summary(paper=False) 
```

### 2. Handling Closes & Concurrency
- `close_trade()` requires an explicit quantity.
- `close_all(parent_trade_id=...)` is a convenience method that fetches the remaining quantity and executes the close. 
- **Concurrency Mitigation:** If `close_all` encounters a `422 Unprocessable Entity` (e.g., due to a race condition where another process partially closed the trade), it raises a specific `TradeAlreadyClosedError` rather than a generic API exception. It can optionally catch and retry with a fresh fetch.

### 3. Two-Phase Commit & Reliability
Creating a documented trade requires two API calls (Memories API + Trading API). 
- **Execution Order:** The SDK *always* creates the Memory first. 
- **Failure State:** If Memory creation fails, the trade is aborted. If the Trade API fails (e.g., rate limits, validation errors), an exception is raised, leaving an "orphaned" memory. This is safe, acting as a logged observation without an execution.
- **Idempotency:** To handle network timeouts during Memory creation, the SDK generates a client-side UUID (or uses an idempotency key if supported by the API) so retries do not create duplicate memories.

### 4. Data Types
```python
from typing import Optional, List
from datetime import datetime
from dataclasses import dataclass

@dataclass
class TradeResult:
    id: str                    
    memory_id: str             
    ticker: str
    direction: str             
    price: float
    quantity: float
    status: str                  # Child execution status
    parent_status: Optional[str] # Status of the parent ("open" or "closed")
    pnl: Optional[float]       
    created_at: datetime
```

## Section 3: Advanced Integrations

### 1. Bulk Import & Backfill
Trading agents often run backtests generating thousands of trades. The SDK handles batching and memory creation logic efficiently.

**Features:**
- **Ref-Based Linking:** The SDK accepts a `ref` key to link entries and exits without needing to pre-generate UUIDs. The server will topologically sort and process them.
- **Optional Reasoning:** `decision_reasoning` is optional for bulk imports. Trades without reasoning will be flagged with `metadata.source = "backfill"`. If reasoning *is* provided, the server handles batch-creating the memories.
- **Partial Success:** Returns a comprehensive result object rather than failing the whole batch on one error.

```python
@dataclass
class BulkImportError:
    index: int
    ref: str
    reason: str

@dataclass
class BulkImportResult:
    total: int
    succeeded: int
    failed: int
    errors: List[BulkImportError]

# Example Usage:
result = journal.bulk_import_trades(trades=[
    {"ref": "trade_1", "ticker": "AAPL", "direction": "long",  "price": 185.50, "quantity": 100, "entry_at": "2023-01-15T10:00:00Z"},
    {"ref": "trade_1", "ticker": "AAPL", "direction": "short", "price": 192.30, "quantity": 100, "entry_at": "2023-01-20T14:00:00Z"},  # auto-linked as exit
])
```

### 2. Memory Attachment Helpers
Semantic helpers allow agents to log observations or post-trade reflections without dropping down to the raw Memory API.

```python
# Logs a type='context' memory with subtype='market_observation'
journal.log_market_observation(
    ticker="SPY",
    observation="VIX spiking, avoiding new entries today.",
    metadata={"vix_level": 25.4}
)

# Post-trade reflection — creates an outcome memory and patches the trade's outcome_memory_id
journal.log_trade_reflection(
    trade_id="uuid-of-closed-trade",
    reflection="Exited too early. RSI hadn't fully reversed.",
    lesson="Wait for RSI to cross back above 30 before closing."
)
```

### 3. Webhooks & Event Subscriptions (v1.1 / Phase 2)
*Note: This feature requires significant backend infrastructure (event queues, retry logic) and will be deferred to v1.1. In v1, consumers can poll the public feed endpoints.*

When implemented, the SDK will provide full CRUD for webhooks to power external integrations (Discord bots, etc.).
```python
journal.list_webhooks()
journal.register_webhook(url="...", events=["trade.opened", "trade.closed"], secret="...")
journal.delete_webhook(webhook_id="...")
journal.test_webhook(webhook_id="...") 
```