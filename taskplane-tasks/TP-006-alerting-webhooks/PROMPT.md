# Task: TP-006 - Alerting & Webhook Notifications

**Created:** 2026-04-07
**Size:** M

## Review Level: 1 (Plan Only)

**Assessment:** New feature, single service. Webhook/Discord integration with configurable triggers.
**Score:** 3/8 — Blast radius: 1, Pattern novelty: 1, Security: 1, Reversibility: 0

## Canonical Task Folder

```
taskplane-tasks/TP-006-alerting-webhooks/
```

## Mission

Add a notification system that sends alerts via Discord webhook (and generic webhook) when key events occur: bridge goes stale (no signals for N minutes), strategy emits a trade decision, errors spike, or consensus changes significantly.

## Dependencies

- **None**
- **None**

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:** `CLAUDE.md`

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading)

## File Scope

- `trading/notifications/` (new directory)
- `trading/notifications/webhook.py` (new)
- `trading/notifications/discord.py` (new)
- `trading/notifications/alerts.py` (new)
- `trading/config.py` (alert config)
- `trading/api/app.py` (wire alerts)
- `trading/tests/unit/test_notifications/` (new)

## Steps

### Step 0: Preflight
- [ ] Check if `trading/notifications/` or WhatsApp notification code already exists
- [ ] Read config.py for configuration patterns

### Step 1: Build Notification Infrastructure
- [ ] Create `trading/notifications/webhook.py` — generic webhook sender (async httpx)
- [ ] Create `trading/notifications/discord.py` — Discord embed formatter
- [ ] Create `trading/notifications/alerts.py` — alert manager with configurable triggers
- [ ] Add config: `STA_DISCORD_WEBHOOK_URL`, `STA_ALERT_STALE_MINUTES=10`, `STA_ALERTS_ENABLED=false`

### Step 2: Wire Alert Triggers
- [ ] Subscribe to SignalBus for trade decision events
- [ ] Add periodic check for bridge staleness (no signals in N minutes)
- [ ] Alert on strategy consensus changes (direction flip)
- [ ] Alert on error rate spikes (>5 errors in 1 minute)

### Step 3: Write Tests
- [ ] Test webhook formatting and sending (mock httpx)
- [ ] Test alert trigger conditions
- [ ] Test Discord embed generation

### Step 4: Testing & Verification
- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Fix all failures

### Step 5: Documentation & Delivery
- [ ] Document alert configuration in CLAUDE.md
- [ ] Discoveries logged

## Completion Criteria
- [ ] Alerts fire for configured triggers
- [ ] Discord webhook delivers formatted messages
- [ ] Alerts disabled by default (opt-in)

## Git Commit Convention
- `feat(TP-006): complete Step N — description`

## Do NOT
- Enable alerts by default
- Add paid notification services
- Block the main event loop with synchronous webhook calls

---

## Amendments (Added During Execution)
