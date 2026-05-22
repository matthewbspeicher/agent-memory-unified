# ADR-0012: `whatsapp/` and `warroom/` are NOT shallow notification adapters

**Status**: accepted

**Date**: 2026-05-22
**Deciders**: matth

---

## Context

An architecture-review pass on 2026-05-22 flagged `trading/whatsapp/` (556 LOC) and `trading/warroom/` (199 LOC) as *candidate shallow adapters* on the basis that `trading/notifications/` already defines a `Notifier`/`CompositeNotifier` interface and these directories appeared to bypass it. The review proposed routing both through `Notifier`.

After deeper reading the premise didn't hold up. Recording the reasons here so future architecture reviews running the same LOC-based heuristic don't re-suggest the refactor.

## Decision

Leave `trading/whatsapp/` and `trading/warroom/` as standalone modules. Do not route them through `Notifier`.

### Why `warroom/` is not a notification adapter

`trading/warroom/engine.py` defines `WarRoomEngine` — a *convergence-detection engine*, not a sender:

- Reads recent opportunities from the DB (`opportunities` table).
- Groups by `(symbol, direction)` and detects when ≥2 agents independently converge.
- On request, generates an LLM synthesis combining each agent's reasoning into a single narrative (`get_synthesis`).
- Exposes a timeline view of recent opportunities (`get_timeline`).

It has no `send()` method, no recipients, no channel concept. Routing it through `Notifier` would be a category error: the `Notifier` interface is `send(opportunity) -> None`; `WarRoomEngine`'s interface is `detect_convergences() -> list[ConvergenceSignal]`. The visual coincidence of "lives near WhatsApp; deals with agent output" is misleading.

Future-proofing: `WarRoomEngine` outputs *could* be published as a SignalBus topic for consumption by alerting subscribers — that's a separate deepening opportunity (convergence-as-topic, analogous to ADR-0011's sentiment-as-topic), not a "route through Notifier" one.

### Why `whatsapp/` is not a shallow adapter of `Notifier`

The outbound `Opportunity` path is **already** routed through `notifications/whatsapp.py:WhatsAppNotifier(Notifier)`, wired into the `CompositeNotifier` in [`trading/api/app.py`](trading/api/app.py) alongside `SlackNotifier`, `DiscordNotifier`, and `LogNotifier`. The seam is healthy.

The 556 LOC under `trading/whatsapp/` are not duplicates of that seam — they implement a distinct *inbound + assistant* surface:

| File | Role | Notification-shaped? |
|------|------|----------------------|
| `client.py` | Low-level Meta Cloud API HTTP client | No — used by `WhatsAppNotifier` and the inbound paths alike |
| `webhook.py` | Receives inbound WhatsApp messages from Meta | No — inbound |
| `commands.py` | Parses `APPROVE`/`REJECT` text replies | No — inbound |
| `confirmation.py` | Tracks pending confirmations awaiting user reply | No — state machine |
| `assistant.py` | LLM-powered inbound Q&A handler | No — orchestrator |
| `charts.py` | Generates chart images for inbound replies | No — content generation |
| `proactive.py` | Hermes background loops: health alerts, briefings, autotune, shadow eval | *Borderline* (see below) |

`whatsapp/proactive.py:HermesProactiveOps._broadcast()` is the only outbound WhatsApp call site outside `WhatsAppNotifier`. It uses `self.wa._client.send_text(number, text)` directly. Two reasons not to route it through `Notifier.send_text`:

1. The messages are WhatsApp-specific in format (Markdown stars, emoji, code fences). Cross-channel routing would lose this on Slack/Discord/LogNotifier.
2. The recipient list (`allowed_numbers`) is WhatsApp-admin-specific. There is no current cross-channel admin-alert requirement.

If a cross-channel admin-alert requirement appears later — e.g. health alerts should also reach Slack — the right move is to add a generic `Notifier.send_admin_alert(...)` method or use `CompositeNotifier.send_text(...)` from the appropriate caller, not to back-port the Hermes proactive loops behind the existing `Notifier.send(opportunity)` interface.

## Consequences

### Positive

- Future architecture reviews running the same LOC-based heuristic will read this ADR before re-suggesting the refactor.
- The naming friction (`whatsapp/` next to `notifications/whatsapp.py`) is documented as intentional separation, not duplication.

### Negative

- The directory layout still looks coincidentally redundant to a first-time reader. Renaming `trading/whatsapp/` to `trading/hermes_inbound/` would communicate intent better, but is out of scope here.

### Neutral

- The genuine deepening opportunity adjacent to this — publishing `WarRoomEngine` convergences as a SignalBus topic — is captured as a follow-up, not blocked by this ADR.

## File Map

No file changes. This ADR exists to prevent the architecture-review heuristic from re-spending discovery cycles on a non-issue.

## Follow-ups

- **Convergence-as-topic**: publish `WarRoomEngine.detect_convergences()` results as a typed `agent_convergence` SignalBus signal so persona agents and the meta_agent can react. Distinct from notification routing.
- **Rename `trading/whatsapp/`** to something less easily confused with `trading/notifications/whatsapp.py` (e.g. `trading/hermes_inbound/`). Cosmetic but reduces first-read friction.

## References

- `trading/notifications/base.py` — `Notifier` ABC
- `trading/notifications/composite.py` — `CompositeNotifier`
- `trading/notifications/whatsapp.py` — `WhatsAppNotifier(Notifier)` (the actual outbound adapter)
- `trading/whatsapp/proactive.py:HermesProactiveOps._broadcast` — borderline non-routed sender (intentional)
- `trading/warroom/engine.py:WarRoomEngine` — convergence-detection engine, not a notifier
- `trading/api/app.py:1922` — `CompositeNotifier` wiring site
- ADR-0011 — adjacent pattern (publishing as a SignalBus topic) for the follow-up direction
