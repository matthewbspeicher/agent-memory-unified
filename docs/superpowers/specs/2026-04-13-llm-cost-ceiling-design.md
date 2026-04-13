# LLM Cost Ceiling — Design Spec

**Date:** 2026-04-13
**Status:** Approved
**Audit Finding:** Red #8 — Per-agent resource limits (last remaining critical gap)

## Problem

The trading engine has 3 LLM-enabled agents (react_analyst, kalshi_news_arb, polymarket_news_arb) with no global cost ceiling. Per-scan call limits exist (default 5 calls/scan via `max_calls_per_scan`) but nothing prevents unbounded daily spend if agents run continuously or the fallback chain routes to paid providers.

The production fallback chain is `groq -> ollama -> anthropic -> rule-based`, so cost exposure is low in practice (Groq and Ollama/gemma4 are free). The ceiling is insurance against:
- Groq + Ollama both going down, pushing all traffic to Anthropic
- Future config changes that put paid providers first
- Misconfigured agents in tight loops

**Forward compatibility:** Any future agents added to `agents.yaml` that enable LLM features will automatically inherit this protection via the LLMClient-level guard.

## Design Overview

**Approach:** LLMClient-level guard (Approach A). Enforcement happens in `LLMClient._resolve_chain()` — the single chokepoint all agents pass through. When over budget, the chain is filtered to free providers only. Zero agent code changes required.

**Budget:** $5.00/day global default (configurable). Testing phase.

**Behavior when ceiling hit (Option C — Alert + Soft Stop):**
- Under 80% -> normal operation
- 80-100% -> WARNING alert, proceed normally
- 100%+ within 15-minute grace period -> CRITICAL alert, proceed (allows in-flight work to finish)
- 100%+ and grace expired -> block paid providers, fall back to free only (groq/ollama/rule-based)

## Component 1: CostLedger

Redis-backed cost tracker with in-memory fallback. Tracks spend per rolling 24h window.

### Redis Keys

| Key | Type | TTL | Description |
|-----|------|-----|-------------|
| `llm:cost:global` | float | 24h | Total spend in cents |
| `llm:cost:agent:{name}` | float | 24h | Per-agent spend in cents |
| `llm:cost:grace_deadline` | string | 24h | ISO timestamp when grace period expires |
| `llm:cost:alert:{event_type}:sent` | string | 24h | Dedup flag for alerts |

All keys auto-expire via Redis TTL. No cron needed.

### Cost Table

Nested dict keyed by `(provider, model)` with `"*"` wildcard fallback. JSON-serializable for config override.

```python
DEFAULT_COST_TABLE = {
    "anthropic": {
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
        "*": {"input": 0.80, "output": 4.00},
    },
    "bedrock": {
        "*": {"input": 0.25, "output": 1.25},
    },
    "groq": {
        "*": {"input": 0.0, "output": 0.0},
    },
    "ollama": {
        "*": {"input": 0.0, "output": 0.0},
    },
    "rule-based": {
        "*": {"input": 0.0, "output": 0.0},
    },
}
```

Lookup: `table.get(provider, {}).get(model) or table.get(provider, {}).get("*")`. Unknown providers default to `{"input": 0.0, "output": 0.0}` (safe fail-open).

Free providers derived dynamically from merged table (handles overrides):
```python
@staticmethod
def _derive_free_providers(cost_table: dict) -> set[str]:
    return {
        name for name, models in cost_table.items()
        if all(p["input"] == 0.0 and p["output"] == 0.0 for p in models.values())
    }
```

### Interface

```python
class CostLedger:
    def __init__(self, redis: Redis | None, config: LLMCostConfig):
        self._redis = redis          # None = in-memory fallback
        self._local: dict[str, float] = {}  # Fallback when Redis unavailable
        self._config = config
        self._cost_table = self._merge_cost_table(DEFAULT_COST_TABLE, config.cost_table_override)
        # Derive free providers from merged table (handles overrides)
        self._free_providers = self._derive_free_providers(self._cost_table)

    async def record(self, agent_name: str, provider: str, model: str,
                     input_tokens: int, output_tokens: int) -> float:
        """Record usage atomically. Returns cost in cents.
        Uses INCRBYFLOAT pipeline for atomicity."""

    async def get_global_spend(self) -> float:
        """Total spend in current 24h window (cents)."""

    async def get_agent_spend(self, agent_name: str) -> float:
        """Per-agent spend in current 24h window (cents)."""

    def get_cost(self, provider: str, model: str) -> dict[str, float]:
        """Look up per-1M-token cost for a provider/model pair.
        Returns {"input": 0.0, "output": 0.0} for unknown providers."""

    async def get_breakdown(self) -> tuple[str, float, dict[str, float]]:
        """Returns (top_agent_name, top_agent_spend, provider_spend_dict).
        Scans llm:cost:agent:* keys for top agent, aggregates provider costs."""

    async def should_block_paid(self) -> bool:
        """True if paid providers should be filtered from chain.
        Returns False during grace period."""

    async def check_thresholds(self) -> str | None:
        """Returns event type if a threshold was crossed, None otherwise.
        Handles 80% warning, 100% ceiling, grace expiry.
        Also sets grace deadline on first ceiling hit."""

    async def _get_grace_deadline(self) -> datetime | None:
        """Returns grace deadline datetime, or None if not set."""

    async def _maybe_set_grace_deadline(self, spend: float, budget: float) -> None:
        """Set grace deadline when ceiling is first hit (idempotent)."""

    @staticmethod
    def _derive_free_providers(cost_table: dict) -> set[str]:
        """Derive free providers from cost table (all costs = 0)."""

    @staticmethod
    def _merge_cost_table(base: dict, override_json: str | None) -> dict:
        """Merge DEFAULT_COST_TABLE with optional JSON override."""
```

### In-Memory Fallback

When Redis is unavailable: **fail open**. Track in `_local` dict (session-scoped, not 24h). Accept cost drift. The fallback chain already favors free providers, so the risk of significant untracked spend during a Redis outage is low.

No sync on Redis reconnect — the in-memory accumulator is conservative enough for a safety net.

### Atomicity

Record uses Redis pipeline with `INCRBYFLOAT`. Grace deadline is set idempotently on first ceiling hit:
```python
async def record(self, agent_name, provider, model, input_tokens, output_tokens):
    cost = self._calculate_cost(provider, model, input_tokens, output_tokens)
    if cost == 0.0:
        return 0.0
    if self._redis:
        pipe = self._redis.pipeline()
        pipe.incrbyfloat("llm:cost:global", cost)
        pipe.incrbyfloat(f"llm:cost:agent:{agent_name}", cost)
        await pipe.execute()
        # Ensure TTL on both keys (idempotent, race is benign)
        for key in ["llm:cost:global", f"llm:cost:agent:{agent_name}"]:
            if await self._redis.ttl(key) == -1:
                await self._redis.expire(key, 86400)
        # Set grace deadline on first ceiling hit
        await self._maybe_set_grace_deadline(
            await self.get_global_spend(), self._config.daily_budget_cents
        )
    else:
        self._local["global"] = self._local.get("global", 0.0) + cost
        self._local[agent_name] = self._local.get(agent_name, 0.0) + cost
    return cost

async def _maybe_set_grace_deadline(self, spend: float, budget: float) -> None:
    """Set grace deadline when ceiling is first hit (idempotent)."""
    if spend < budget:
        return
    deadline_key = "llm:cost:grace_deadline"
    if await self._redis.ttl(deadline_key) == -1:
        deadline = datetime.now(timezone.utc) + timedelta(
            minutes=self._config.grace_period_minutes
        )
        await self._redis.setex(deadline_key, 86400, deadline.isoformat())
```

### Threshold Checking

```python
async def check_thresholds(self) -> str | None:
    spend = await self.get_global_spend()
    budget = self._config.daily_budget_cents
    pct = spend / budget if budget > 0 else 0.0

    if pct < self._config.warning_threshold_pct:
        return None

    if pct >= 1.0:
        deadline = await self._get_grace_deadline()
        if deadline and datetime.now(timezone.utc) > deadline:
            return "cost.paid_blocked"
        return "cost.ceiling_hit"

    return "cost.warning"

async def _get_grace_deadline(self) -> datetime | None:
    if not self._redis:
        return None
    raw = await self._redis.get("llm:cost:grace_deadline")
    if raw:
        return datetime.fromisoformat(raw)
    return None
```

### Breakdown Query

```python
async def get_breakdown(self) -> tuple[str, float, dict[str, float]]:
    """Returns (top_agent_name, top_agent_spend, provider_spend_dict)."""
    if not self._redis:
        top_agent = max(
            (k for k in self._local if k != "global"),
            key=lambda k: self._local.get(k, 0.0),
            default="unknown"
        )
        return top_agent, self._local.get(top_agent, 0.0), {}

    # Scan agent keys
    top_agent, top_spend = "unknown", 0.0
    cursor = 0
    while True:
        cursor, keys = await self._redis.scan(cursor, "llm:cost:agent:*", count=100)
        for key in keys:
            val = float(await self._redis.get(key) or 0.0)
            agent = key.split(":")[-1]
            if val > top_spend:
                top_agent, top_spend = agent, val
        if cursor == 0:
            break

    # Provider breakdown requires tracking; store separately or approximate from stats
    # For v1, return empty provider dict (can be enhanced with llm:cost:provider:{name} keys)
    return top_agent, top_spend, {}
```

## Component 2: LLMClient Integration

### Chain Filtering

Enforcement in `_resolve_chain()` — **must become async** since `should_block_paid()` requires Redis call:

```python
async def _resolve_chain(self) -> list[str]:
    # Step 1: Remove disabled providers (circuit breaker)
    chain = [p for p in self._chain if not self._is_disabled(p)]

    # Step 2: Remove paid providers if over budget (respects grace period)
    if self._cost_ledger and await self._cost_ledger.should_block_paid():
        chain = [p for p in chain if p in self._cost_ledger._free_providers]

    # Step 3: Always have at least rule-based
    return chain or ["rule-based"]
```

Order matters: disabled-first, then paid-filter. Reversing would be a bug (could re-enable a disabled paid provider as "free").

### Agent Name Propagation

Agent name is a **constructor parameter** on LLMClient, not per-call:

```python
class LLMClient:
    def __init__(self, ..., agent_name: str = "unknown",
                 cost_ledger: CostLedger | None = None):
        self._agent_name = agent_name
        self._cost_ledger = cost_ledger
```

Each agent already gets its own LLMClient instance (wired in `api/app.py`). Non-agent callers (e.g., trade reflector, intelligence layer) default to `"unknown"`.

### Cost Recording

Called in `LLMClient.complete()` and `LLMClient.chat()` after a successful provider call, separate from `LLMStatsCollector.record_call()` (single responsibility):

```python
# After successful call in complete()/chat():
collector.record_call(result, success=True)
if self._cost_ledger:
    await self._cost_ledger.record(
        self._agent_name, result.provider, result.model,
        result.input_tokens or 0, result.output_tokens or 0,
    )
```

### Threshold Checking

After recording, check thresholds and fire alerts if needed:

```python
event_type = await self._cost_ledger.check_thresholds()
if event_type:
    await notify_cost_event(event_type, self._cost_ledger, self._notifier)
```

## Component 3: Configuration

New fields on `LLMConfig` in `config.py`:

```python
class LLMConfig(BaseModel):
    # ... existing fields ...

    # Cost control
    daily_budget_cents: int = 500                # $5.00/day
    warning_threshold_pct: float = 0.80          # Alert at 80%
    grace_period_minutes: int = 15               # After ceiling hit
    cost_table_override: str | None = None       # JSON override
```

Environment variables (via `STA_` prefix + nested accessor):
- `STA_LLM_DAILY_BUDGET_CENTS=500`
- `STA_LLM_WARNING_THRESHOLD_PCT=0.80`
- `STA_LLM_GRACE_PERIOD_MINUTES=15`
- `STA_LLM_COST_TABLE_OVERRIDE='{"anthropic":{"*":{"input":1.0,"output":5.0}}}'`

> **Note:** Use single quotes around JSON values in shell to avoid escaping issues. In `.env` files, double-quote the value: `STA_LLM_COST_TABLE_OVERRIDE="{\"anthropic\":{\"*\":{\"input\":1.0,\"output\":5.0}}}"`

## Component 4: Alerting

### Event Types

| Event | Trigger | Log Level | Notification |
|-------|---------|-----------|--------------|
| `cost.warning` | 80% of daily budget | WARNING | All configured channels |
| `cost.ceiling_hit` | 100% — grace period starts | CRITICAL | All configured channels |
| `cost.paid_blocked` | Grace expired — paid providers blocked | CRITICAL | All configured channels |

### Alert Data

```python
@dataclass
class CostAlertData:
    global_spend_cents: float
    budget_cents: float
    percent_used: float                    # 0-100+
    top_agent: str
    top_agent_spend_cents: float
    provider_breakdown: dict[str, float]   # {"anthropic": 350.0, "bedrock": 100.0}
    grace_deadline: datetime | None
    window_reset_at: datetime              # When 24h TTL expires
```

### Notification Helper

New file: `notifications/cost.py`

```python
async def notify_cost_event(
    event_type: str,
    data: CostAlertData,
    notifier: Notifier | None = None,
) -> None:
    """Structured log + optional notification channel dispatch."""
    level = logging.WARNING if "warning" in event_type else logging.CRITICAL

    log_event(
        logger, level, event_type,
        f"LLM cost {event_type}: {data.percent_used:.1f}% of budget",
        data=asdict(data),
    )

    if notifier:
        msg = (
            f"LLM Cost Alert: {event_type}\n"
            f"Spend: ${data.global_spend_cents/100:.2f} / ${data.budget_cents/100:.2f}\n"
            f"Top agent: {data.top_agent} (${data.top_agent_spend_cents/100:.2f})\n"
            f"Window resets: {data.window_reset_at.isoformat()}"
        )
        await notifier.send_text(msg)
```

### Deduplication

Each event type fires at most once per 24h window. Redis key `llm:cost:alert:{event_type}:sent` with 24h TTL. Single CostLedger instance assumed (one per trading engine process).

## File Map

| File | Action | Description |
|------|--------|-------------|
| `trading/llm/cost_ledger.py` | **New** | CostLedger class, cost table, _FREE_PROVIDERS |
| `trading/llm/client.py` | **Modify** | Add cost_ledger + agent_name params, filter chain, record cost |
| `trading/config.py` | **Modify** | Add daily_budget_cents, warning_threshold_pct, grace_period_minutes, cost_table_override to LLMConfig |
| `trading/notifications/cost.py` | **New** | CostAlertData dataclass, notify_cost_event() helper |
| `trading/api/app.py` | **Modify** | Initialize CostLedger with Redis, pass to LLMClient instances |
| `trading/tests/unit/test_llm/test_cost_ledger.py` | **New** | Unit tests for CostLedger |
| `trading/tests/unit/test_llm/test_cost_integration.py` | **New** | Integration test: LLMClient + CostLedger chain filtering |

## Non-Goals

- Per-agent budget limits (global ceiling only for now; per-agent is reporting, not enforcement)
- Historical cost dashboards (stats.py handles session metrics; persistent analytics is a separate feature)
- Real-time pricing from provider APIs (hardcoded table is sufficient; update manually)
- Cost prediction / forecasting
