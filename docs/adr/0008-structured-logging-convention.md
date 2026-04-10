# ADR-0008: Structured Logging Convention

**Status**: accepted

**Date**: 2026-04-10
**Deciders**: Backfilled from existing implementation in `trading/utils/logging.py`

---

## Context

The trading engine emits high-volume, latency-sensitive events from many sources: agent decisions, signal bus consensus, broker order lifecycle, the Bittensor TaoshiBridge poll loop, the validator's weight setter, and so on. Three needs were in tension:

1. **Operators tail logs in a terminal** during local dev and want to read them quickly, with the most useful field (the *event type*) prominent.
2. **Production needs machine-parseable logs** so we can ship them to log aggregators, query by event type, alert on patterns, and correlate with trade outcomes.
3. **Code needs to emit events with low ceremony** — if logging requires a struct definition or a 5-line block, developers will reach for `print()` or bare `logger.info(f"…")` and the structure will be lost.

We also had a separate constraint: importing `bittensor` v10 silently sets every existing logger to `CRITICAL`, so any logging setup has to be re-applied (or the bittensor import has to be carefully ordered) for our log output to survive.

## Decision

A single `trading/utils/logging.py` module owns all logging configuration, with two switchable output formats and a fixed taxonomy of event types.

### Two formats, one switch

Controlled by environment variables:

| Env Var | Values | Default | Purpose |
|---------|--------|---------|---------|
| `STA_LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` | `INFO` | Root log level |
| `STA_LOG_FORMAT` | `json` / `text` | `json` | Output format |

**`json` (default, machine-readable):**
```json
{"ts": "2026-04-07T12:00:00+00:00", "level": "INFO", "logger": "integrations.bittensor.taoshi_bridge", "msg": "TaoshiBridge: 3 new signals", "event_type": "bridge.poll", "data": {"new_signals": 3, "miners": 12}}
```

**`text` (human-readable):**
```
2026-04-07 12:00:00 INFO     [integrations.bittensor.taoshi_bridge] [bridge.poll] TaoshiBridge: 3 new signals
```

The text formatter inlines the `event_type` into the message so the human eye sees it immediately. The JSON formatter promotes it to a top-level key.

### Fixed event type taxonomy

The canonical event types are documented in the module docstring of `trading/utils/logging.py` and are intentionally narrow — adding a new one is a deliberate decision, not an ad-hoc choice:

- `signal.received` — external signal ingested
- `signal.consensus` — consensus formed across signals
- `trade.decision` — agent decided to trade (or not)
- `trade.executed` — order placed / confirmed
- `bridge.poll` — `TaoshiBridge` periodic scan
- `bridge.signal` — `TaoshiBridge` emitted a signal
- `error` — generic error envelope

### One helper for emitting events

```python
from trading.utils.logging import log_event
import logging

log_event(
    logger,
    logging.INFO,
    event_type="bridge.poll",
    msg="TaoshiBridge: 3 new signals",
    data={"new_signals": 3, "miners": 12},
)
```

`log_event` packs `event_type` and `data` into the `extra` dict on the `LogRecord`, where both formatters know how to extract them. Existing `logger.info("…")` calls without structure still work and just won't carry an event type.

### Setup is a single call

```python
from trading.utils.logging import setup_logging
setup_logging(level=os.environ.get("STA_LOG_LEVEL", "INFO"),
              fmt=os.environ.get("STA_LOG_FORMAT", "json"))
```

Called once during the FastAPI lifespan startup. It also pre-quiets known noisy third-party loggers (`urllib3`, `httpcore`, `httpx`, `asyncio`, `websockets`) to `WARNING`.

### Bittensor v10 interaction

Because `import bittensor` (v10) silently sets all existing loggers to `CRITICAL`, the trading engine's startup sequence calls `setup_logging` **after** the bittensor import (or explicitly re-asserts levels for trading-engine loggers immediately afterward). This is documented in CLAUDE.md "Working Boundaries" as a non-negotiable rule.

## Consequences

### Positive

- **One place to look** for all logging behavior — `trading/utils/logging.py`. New contributors don't have to hunt for handler config across modules.
- **Format switch is environment-controlled**, so dev can run `STA_LOG_FORMAT=text` for readable terminal output and prod can leave the JSON default for shipping to aggregators.
- **Structured data without ceremony.** `log_event(logger, INFO, "trade.executed", "filled", {...})` is one line and produces a queryable event.
- **Fixed taxonomy means alerts and dashboards are stable.** A grafana panel for "trade.decision count by hour" doesn't break when a developer invents a new event name.
- **Both formatters degrade gracefully** when `event_type` and `data` are absent — code that uses plain `logger.info(...)` still works and just emits a record without structured fields.

### Negative

- **The taxonomy is small.** Anything that doesn't fit one of the seven event types either has to use the generic `error` envelope or motivate adding a new event type — and adding one means updating the docstring, this ADR, and any downstream consumers.
- **The `extra` dict mechanism is not enforced** — a developer can still call `logger.info("important thing")` with no structure and it will compile and run. There's no static check.
- **Two formatters means two code paths to keep in sync** — a field added to one must be added to the other, or `text` and `json` will diverge.
- **The bittensor logger-kill workaround is fragile** — it depends on import ordering and a one-shot reset. A future bittensor upgrade could change the behavior again.

### Neutral

- Module location is `trading/utils/logging.py`; the trading engine package shadows the standard-library `logging` module unintentionally if imported via `from trading import logging`. We import via `from trading.utils import logging as trading_logging` or directly `from trading.utils.logging import log_event` to avoid the collision.
- The event type taxonomy lives in the module docstring rather than as an enum. Changing it is a documentation update plus a grep for usages.
- Third-party loggers are silenced to `WARNING` rather than removed; their warnings still surface.

---

## Alternatives Considered

| Alternative | Pros | Cons |
|-------------|------|------|
| **Use `structlog` library** | Mature, handles processors / context binding | Adds a dependency; the bittensor import-time logger kill still applies and would have to be worked around the same way; for our event volume the stdlib is enough |
| **Emit JSON only, format in dev with `jq`** | One code path | Local terminal usability is meaningfully worse; pretty-printing JSON in a fast-scrolling terminal is not the same as a clean text line |
| **Free-form `event_type` strings** | Flexibility | Dashboards and alerts break silently as new strings appear; observability gradually rots |
| **Class hierarchy for events** (`TradeDecisionEvent(...)`) | Type safety | Heavyweight; raises the bar for emitting an event so high that developers will route around it |
| **stdlib + custom JSONFormatter + StructuredTextFormatter + log_event helper (chosen)** | Zero new deps, low ceremony, format switch via env, fixed taxonomy preserves dashboards | Two formatters to keep in sync; taxonomy enforcement is convention, not type system |

---

## Notes

- Implementation: `trading/utils/logging.py`
- Setup is called from the FastAPI lifespan in `trading/api/app.py`
- Related operational rule: CLAUDE.md "Working Boundaries" → *Always do: restore app loggers immediately after `import bittensor`*
- Related memory: `feedback_bittensor_v10_logging.md`
- Adding a new event type: update the module docstring of `trading/utils/logging.py` and this ADR's taxonomy section in the same commit
