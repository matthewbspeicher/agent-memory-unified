# Mission Control Frontend Redesign

## Overview

Redesign the frontend around a unified **Mission Control** dashboard that provides instant operational visibility into agents, infrastructure, validator, and trades — all from a single page. Paired with a navigation restructure that separates personal ops from community-facing pages.

**Audience:** Primary operator (personal ops dashboard). Community pages remain but are deprioritized in navigation.

**Approach:** Hybrid — dense Mission Control page with overlay drawer drill-downs. Every panel shows a compact summary; clicking expands a right-side drawer with full detail. You never leave the page.

## Navigation Restructure

Replace the current flat sidebar with a grouped structure:

**Ops** (top of nav, personal)
- **Mission Control** — `/mission-control` — the new home page for authenticated users
- **Bittensor** — `/bittensor` — existing, unchanged
- **Trades** — `/trades` — existing, unchanged
- **Agents** — `/agents` — existing directory, enhanced with status

**Community** (lower section, public-facing)
- **Arena** — `/arena`
- **Commons** — `/commons`
- **Leaderboard** — `/leaderboard`

**System** (collapsed/bottom)
- **Webhooks** — `/webhooks`
- **Workspaces** — `/workspaces`
- **Explorer** — `/explorer`

The landing page (`/`) remains the public entry for unauthenticated visitors. Authenticated users default to `/mission-control`.

## Mission Control Page

### Status Bar (Row 1)

Five KPI tiles across the top for instant health assessment:

| Tile | Source | States |
|------|--------|--------|
| System Status | Aggregated from all services | Green "All Clear" / Yellow "Degraded" / Red "Down" |
| Agents Active | `/api/agents/status` | Count: "11/13" with color |
| Open Trades | `/api/trades?status=open` | Count |
| Validator | `/api/bittensor/status` | Green "Healthy" / Yellow "Degraded" |
| Daily P&L | `/api/trades/summary` | Dollar amount, green/red |

### Agent Activity Panel (Row 2, Left)

The primary new feature — zero agent visibility today, full observability after.

**Collapsed view:**
- Live scrolling feed of agent events, most recent first
- Each line: timestamp, agent name (color-coded per agent), action summary
- Event types: `signal.received`, `signal.consensus`, `trade.decision`, `trade.executed`, `bridge.poll`, `error`
- Badge showing active vs total agents

**Drawer (expanded):**
- Full event log with filtering by agent name, event type, and time range
- Agent grid: all 13 agents as cards showing status (active/idle/error), last action timestamp, signals emitted today, success rate
- Click an agent card to see its individual event timeline
- Agents that haven't emitted events in an abnormal window are flagged with yellow indicator

**Data feed:** WebSocket for real-time streaming (reuses existing WS infrastructure from the current dashboard). Falls back to polling `/api/agents/activity` if WS unavailable.

### Infrastructure Panel (Row 2, Right)

**Collapsed view:**
- Service health grid, each service as a row: name + status indicator (green/yellow/red)

| Service | Health Check | Notes |
|---------|-------------|-------|
| Trading Engine | `GET /ready` | Existing endpoint |
| PostgreSQL | DB connection ping | Via health endpoint |
| Redis | Redis ping | Via health endpoint |
| Taoshi Bridge | Bridge polling status | Includes miner count |
| Railway | Railway API | Requires `RAILWAY_API_TOKEN` |
| IBKR Broker | Broker connection status | Special "offline (expected)" state — shows yellow, not red, when TWS is not running |

- p95 API latency as a single number

**Drawer (expanded):**
- Each service row expands to: status, uptime duration, last error message (if any), response time
- Sparkline for API latency over last hour
- Status change log ("Redis disconnected at 12:04, reconnected at 12:05")
- Railway deployment info: current deploy status, last deploy time
- Manual "refresh all" button

### Validator Panel (Row 3, Left)

**Collapsed view:**
- 2x2 metric grid: hash pass rate, total weight sets, top miner score, miner response rate
- Single healthy/degraded status indicator

**Drawer (expanded):**
- Reuses existing `BittensorNode` page components (scheduler, evaluator, weight setter cards, top miners table)
- The standalone `/bittensor` route remains for bookmarking/sharing

No new backend work — repackages existing `/api/bittensor/status` and `/api/bittensor/metrics` data.

### Open Trades Panel (Row 3, Right)

**Collapsed view:**
- List of open positions: ticker, direction (LONG/SHORT color-coded), unrealized P&L with green/red
- Total position count in header

**Drawer (expanded):**
- Full trade table: ticker, direction, entry price, current price, unrealized P&L, duration, originating agent
- Recent closed trades (last 24h) below active positions
- Reuses existing `TradeList` component logic

Minimal backend addition: ensure agent attribution is included in trade API responses.

## Overlay Drawer

**Behavior:**
- Slides in from right edge of viewport
- Width: 50-60% of viewport
- Semi-transparent backdrop dims Mission Control panels behind
- Close via: click backdrop, press Escape, or click X button
- Dashboard stays mounted underneath (no unmount/remount)
- Only one drawer open at a time — opening another closes the current one
- Smooth slide animation (200-300ms ease-out)

**Implementation:**
- Single `<Drawer>` component at the Mission Control page level
- Panel components pass their drawer content as children
- Drawer state managed via React state (open panel ID + null for closed)
- URL hash optional (`#agents`, `#infra`) for deep-linking into a specific drawer

## Data Refresh Strategy

| Source | Method | Interval |
|--------|--------|----------|
| Agent Activity feed | WebSocket | Real-time |
| Status bar KPIs | Polling | 30 seconds |
| Infrastructure health | Polling | 30 seconds |
| Validator metrics | Polling | 30 seconds (existing) |
| Open trades | Polling | 30 seconds |

- Each panel shows a subtle "last updated" timestamp
- Manual "refresh all" button in the status bar for on-demand re-check
- All polling uses TanStack Query with `refetchInterval: 30_000` (consistent with existing pattern)

## Alert / Degraded States

- Any service going red flips the "System Status" KPI to yellow or red immediately
- Agent with no events in an abnormal window gets yellow indicator
- IBKR broker uses "offline (expected)" state — yellow indicator, not red, when TWS is not running
- No notification/toast system for now — the status bar is the alert surface
- Push notifications can be added later if needed

## New Backend Endpoints

### `GET /api/agents/activity`

Returns recent structured log events from the agent framework.

```json
{
  "events": [
    {
      "timestamp": "2026-04-07T12:31:00Z",
      "agent": "trend-follower",
      "event_type": "signal.received",
      "message": "BTC/USD LONG signal (confidence: 0.82)",
      "data": { "pair": "BTC/USD", "direction": "long", "confidence": 0.82 }
    }
  ],
  "total": 247
}
```

Query params: `?agent=<name>&event_type=<type>&since=<iso8601>&limit=50`

Source: Structured logging events (`utils.logging.log_event`) already emit these event types. Endpoint needs to collect from an in-memory ring buffer or recent log tail.

### `GET /api/agents/status`

Returns per-agent health and activity summary.

```json
{
  "agents": [
    {
      "name": "trend-follower",
      "status": "active",
      "last_event": "2026-04-07T12:31:00Z",
      "signals_today": 14,
      "errors_today": 0
    }
  ],
  "active": 11,
  "total": 13
}
```

Source: Derived from `agents.yaml` config (total list) + agent activity data (last seen, counts).

### `GET /api/health/services`

Aggregated health check across all monitored services.

```json
{
  "status": "healthy",
  "services": [
    { "name": "trading_engine", "status": "healthy", "latency_ms": 2, "uptime": "3d 14h" },
    { "name": "postgresql", "status": "healthy", "latency_ms": 5 },
    { "name": "redis", "status": "healthy", "latency_ms": 1 },
    { "name": "taoshi_bridge", "status": "healthy", "miners": 12, "last_poll": "2026-04-07T12:30:30Z" },
    { "name": "railway", "status": "healthy", "deploy_status": "active", "last_deploy": "2026-04-07T10:00:00Z" },
    { "name": "ibkr_broker", "status": "offline_expected", "message": "TWS not running" }
  ],
  "api_latency_p95_ms": 42
}
```

Source: Internal health checks (DB ping, Redis ping, broker status) + Railway API call. The existing `/ready` and `/health-internal` endpoints provide some of this already.

**Important Implementation Details:**
*   **Health Endpoint Latency:** External health checks (such as the Railway API) MUST be executed asynchronously in a background task and their results cached. The `GET /api/health/services` endpoint must return immediately using the cached data to prevent timeouts when polled every 30 seconds.
*   **IBKR Broker Status:** To reliably distinguish between an intentional shutdown of TWS and a crash (the "offline (expected)" state), the API must check a configuration flag (e.g., `IBKR_EXPECTED_OFFLINE` or trading schedule config) rather than just failing the ping.

## Component Architecture

```
MissionControl/
├── MissionControlPage.tsx        — layout grid + drawer state
├── StatusBar.tsx                  — 5 KPI tiles
├── panels/
│   ├── AgentActivityPanel.tsx     — collapsed feed view
│   ├── InfrastructurePanel.tsx    — service health grid
│   ├── ValidatorPanel.tsx         — compact 2x2 metrics
│   └── TradesPanel.tsx            — open positions list
├── drawers/
│   ├── AgentDrawer.tsx            — full agent console
│   ├── InfraDrawer.tsx            — service details + sparklines
│   ├── ValidatorDrawer.tsx        — reuses BittensorNode components
│   └── TradesDrawer.tsx           — full trade table
├── Drawer.tsx                     — generic overlay drawer shell
└── hooks/
    ├── useAgentActivity.ts        — WS + polling for agent events
    ├── useInfraHealth.ts          — polling /api/health/services
    └── useMissionControlStatus.ts — aggregated status bar data
```

## Out of Scope

- Community page improvements (arena, commons, leaderboard) — future phase
- Push notifications / toast alerts
- Supabase-specific health checks (can be added to `/api/health/services` later)
- Mobile responsive layout (ops dashboard is desktop-first)
- Customizable panel layout / drag-and-drop reordering
