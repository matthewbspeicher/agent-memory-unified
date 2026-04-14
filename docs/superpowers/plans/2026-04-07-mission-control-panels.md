# Mission Control Agent & Trading Panels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement the Agent Activity Panel (with WS integration), Validator Panel, and Open Trades Panel for the Mission Control dashboard.

**Architecture:** We will build React components for each panel and its corresponding expanded drawer view. We will integrate WebSocket streaming for the Agent Activity feed.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, TanStack Query

---

### Task 1: Agent Activity Panel & WebSocket Integration

**Files:**
- Create: `frontend/src/hooks/useAgentActivity.ts`
- Create: `frontend/src/pages/mission-control/panels/AgentActivityPanel.tsx`
- Create: `frontend/src/pages/mission-control/drawers/AgentDrawer.tsx`

- [x] **Step 1: Implement `useAgentActivity` hook**
Create a custom hook that attempts a WebSocket connection for real-time agent events, and falls back to polling `/api/agents/activity` via TanStack Query.

- [x] **Step 2: Build Agent Activity Panel (Collapsed)**
Implement the live scrolling feed of agent events, showing timestamp, agent name, and action summary.

- [x] **Step 3: Build Agent Drawer (Expanded)**
Implement the full event log with filtering, and the 13-agent grid showing status cards.

- [x] **Step 4: Integrate into Page**
Add the Agent Activity Panel to the `MissionControlPage`.

- [x] **Step 5: Commit**
```bash
git add frontend/src/hooks/useAgentActivity.ts frontend/src/pages/mission-control/panels/AgentActivityPanel.tsx frontend/src/pages/mission-control/drawers/AgentDrawer.tsx
git commit -m "feat(ui): implement agent activity panel and drawer"
```

### Task 2: Validator Panel

**Files:**
- Create: `frontend/src/pages/mission-control/panels/ValidatorPanel.tsx`
- Create: `frontend/src/pages/mission-control/drawers/ValidatorDrawer.tsx`

- [x] **Step 1: Build Validator Panel (Collapsed)**
Implement the compact 2x2 metric grid (hash pass rate, total weight sets, top miner score, response rate).

- [x] **Step 2: Build Validator Drawer (Expanded)**
Reuse existing `BittensorNode` page components to show full validator details when the drawer is open.

- [x] **Step 3: Integrate into Page**
Add the Validator Panel to the `MissionControlPage`.

- [x] **Step 4: Commit**
```bash
git add frontend/src/pages/mission-control/panels/ValidatorPanel.tsx frontend/src/pages/mission-control/drawers/ValidatorDrawer.tsx
git commit -m "feat(ui): implement validator panel and drawer"
```

### Task 3: Open Trades Panel

**Files:**
- Create: `frontend/src/pages/mission-control/panels/TradesPanel.tsx`
- Create: `frontend/src/pages/mission-control/drawers/TradesDrawer.tsx`

- [x] **Step 1: Build Trades Panel (Collapsed)**
Implement the list of open positions (ticker, direction, unrealized P&L).

- [x] **Step 2: Build Trades Drawer (Expanded)**
Implement the full trade table, reusing logic from the existing `TradeList` component.

- [x] **Step 3: Integrate into Page**
Add the Trades Panel to the `MissionControlPage`.

- [x] **Step 4: Commit**
```bash
git add frontend/src/pages/mission-control/panels/TradesPanel.tsx frontend/src/pages/mission-control/drawers/TradesDrawer.tsx
git commit -m "feat(ui): implement open trades panel and drawer"
```
