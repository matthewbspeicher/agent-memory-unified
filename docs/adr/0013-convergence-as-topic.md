# ADR-0013: Agent Convergence as a SignalBus Topic

**Status**: accepted

**Date**: 2026-05-22
**Deciders**: matth

---

## Context

`WarRoomEngine` (`trading/warroom/engine.py`) detects when ≥2 agents independently flag the same `(symbol, direction)` within a time window and exposes the result via HTTP routes (`/warroom/convergences` and friends). Before this ADR, the only consumer of that signal was the operator dashboard — the convergence existed in the database but no agent could react to it programmatically.

Three concrete consumers want convergence as a first-class topic:

1. **`meta_agent`** — already applies confidence boost/suppression rules keyed on `signal_type`. "5 of 6 agents agree on AAPL long" should trigger an explicit boost.
2. **`PersonaPanelAgent`** (added 2026-05-22) — its judge could read recent convergence signals as additional context, weighing "the wider ensemble already agrees" against the panel's own verdict.
3. **Future ensemble logic** — any new strategy that wants to react to coalitions of agents rather than to single-agent opportunities.

The HTTP route is wrong for these consumers. They'd be polling, parsing JSON, and re-deriving freshness. The right shape is the same pattern ADR-0011 (`intel_sentiment`) established: publish to the SignalBus, let consumers subscribe or query.

## Decision

Add a new `agent_convergence` SignalBus topic. `WarRoomEngine` publishes a typed signal each time `detect_convergences()` produces a convergence the engine has not previously published.

### Payload contract

Defined in `trading/data/signal_types.py`:

```python
class AgentConvergencePayload(SignalPayload):
    convergence_id: str          # stable hash of symbol:direction:first_seen
    symbol: str
    direction: Literal["BUY", "SELL"]
    agents: list[str]
    opportunity_ids: list[str]
    avg_confidence: float        # 0..1
    first_seen: str              # ISO-8601 timestamp
    synthesis: str = ""          # populated lazily by get_synthesis()
```

Registered as `"agent_convergence"` in the global `SignalTypeRegistry`. Signals expire after 4 hours (matching the default convergence detection window).

### Publishing site

`WarRoomEngine.__init__` accepts an optional `signal_bus` parameter. When set, `detect_convergences()` publishes each newly-detected convergence as a side-effect — before returning the list to the HTTP caller.

Dedup is by `convergence_id`. The engine maintains an in-memory bounded set (`deque(maxlen=10_000)`) of previously-published IDs; convergences whose ID is already in the set are skipped. The bound is FIFO-evicted to keep memory predictable in long-running processes.

### Back-compat

`WarRoomEngine` works identically without a `signal_bus`. Existing callers that constructed it with just `(db, llm)` keep working — the topic publish is purely additive. Only `trading/api/app.py:_setup_operator_services` was updated to thread the bus through.

## Consequences

### Positive

- **Locality**: every change to convergence detection (window length, agent counting rules, normalization) lives in `warroom/`. Consumers know only the payload contract.
- **Leverage**: `meta_agent`, `PersonaPanelAgent`, and any future ensemble agent get convergence-aware signals for free via `signal_bus.query(signal_type="agent_convergence")`.
- **Mirrors ADR-0011**: same pattern (provider produces data → publish to typed topic → consumers poll the bus) keeps the cognitive load low for anyone reading the codebase.
- **Best-effort publish**: a malformed convergence (e.g. validation failure) logs a warning and never breaks detection. HTTP routes still get the full list.

### Negative

- Publishing is driven by `detect_convergences()` calls. If nobody calls that method, no signals fire. Today the HTTP routes drive it; a future cleanup might add a periodic task in `app.py` lifespan so the topic stays fresh even without dashboard traffic.
- The in-memory dedupe set resets on engine restart. After restart, the first call republishes recent convergences — fine for a topic (consumers should dedupe by `convergence_id`) but worth noting.

### Neutral

- One signal per new convergence, with a 4-hour TTL. Combined with the 1000-signal `MAX_SIGNALS` cap on `SignalBus`, impact on bus throughput is negligible.

## File Map

| File | Action | Description |
|------|--------|-------------|
| `trading/data/signal_types.py` | Modified | Added `AgentConvergencePayload`, registered `"agent_convergence"` |
| `trading/warroom/engine.py` | Modified | Optional `signal_bus` param; publish-on-detect with FIFO dedup |
| `trading/api/app.py` | Modified | Thread `signal_bus` through `_setup_operator_services` → `WarRoomEngine` |
| `trading/tests/unit/test_agent_convergence_topic.py` | New | Payload + publish + dedup tests |

## Follow-ups (not in this ADR)

- **Periodic detector task** in `app.py` lifespan to drive `detect_convergences()` on a schedule independent of HTTP traffic.
- **`meta_agent` consumer** that subscribes to `agent_convergence` and applies a confidence boost proportional to agent count + avg_confidence.
- **`PersonaPanelAgent` consumer** that reads recent convergences as judge-context: "the wider ensemble already agrees on this direction, weigh the panel's dissent accordingly."

## References

- `trading/warroom/engine.py:detect_convergences` — detection site
- `trading/data/signal_types.py:AgentConvergencePayload` — payload contract
- ADR-0011 — adjacent pattern (sentiment as a topic)
- ADR-0012 — clarifies that WarRoom is a *detector*, not a notifier; this ADR is the natural follow-up
