# Mission Control Shell & Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the frontend navigation, build the generic `<Drawer>` component, and implement the Status Bar + Infrastructure Panel.

**Architecture:** We will create a new grouped navigation sidebar separating "Ops", "Community", and "System". We will build a reusable overlay `<Drawer>` component to handle drill-downs without leaving the page. We will then implement the `/mission-control` route, starting with the Status Bar (KPIs) and the Infrastructure Panel.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, TanStack Query, React Router v7

---

### Task 1: Navigation Restructure

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx` (or equivalent navigation component)
- Modify: `frontend/src/routes.tsx` (to add `/mission-control`)

- [ ] **Step 1: Update Sidebar structure**
Update the navigation component to group links into Ops, Community, and System sections as defined in the spec. Ensure `/mission-control` is the default authenticated route.

- [ ] **Step 2: Add Route**
Ensure the `/mission-control` route is added to the application router, pointing to a placeholder `MissionControlPage` component.

- [ ] **Step 3: Verify functionality**
Run the frontend and verify the sidebar displays the new groupings and links correctly.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/components/layout/Sidebar.tsx frontend/src/routes.tsx
git commit -m "feat(ui): restructure navigation for mission control"
```

### Task 2: Build Generic `<Drawer>` Component

**Files:**
- Create: `frontend/src/components/ui/Drawer.tsx`

- [ ] **Step 1: Implement `<Drawer>` component**
Create a reusable React component that slides in from the right edge, covering 50-60% of the viewport, with a semi-transparent backdrop. It should accept `isOpen`, `onClose`, and `children` props.

- [ ] **Step 2: Add closing behaviors**
Ensure the drawer closes when the backdrop is clicked or the Escape key is pressed.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/components/ui/Drawer.tsx
git commit -m "feat(ui): add generic overlay Drawer component"
```

### Task 3: Status Bar & Infrastructure Panel

**Files:**
- Create: `frontend/src/pages/mission-control/MissionControlPage.tsx`
- Create: `frontend/src/pages/mission-control/StatusBar.tsx`
- Create: `frontend/src/pages/mission-control/panels/InfrastructurePanel.tsx`
- Create: `frontend/src/pages/mission-control/drawers/InfraDrawer.tsx`
- Create: `frontend/src/hooks/useInfraHealth.ts`
- Create: `frontend/src/hooks/useMissionControlStatus.ts`

- [ ] **Step 1: Implement hooks**
Implement the TanStack Query hooks to fetch data from the new `/api/health/services` and `/api/agents/status` endpoints (mocked for now if backend is not fully ready).

- [ ] **Step 2: Build Status Bar**
Implement the `StatusBar.tsx` component with 5 KPI tiles (System Status, Agents Active, Open Trades, Validator, Daily P&L).

- [ ] **Step 3: Build Infrastructure Panel (Collapsed)**
Implement the `InfrastructurePanel.tsx` showing the service health grid. Add a click handler to open the drawer.

- [ ] **Step 4: Build Infra Drawer (Expanded)**
Implement the `InfraDrawer.tsx` to show detailed service info, response times, and the manual refresh button.

- [ ] **Step 5: Assemble Mission Control Page**
Combine the Status Bar and Infrastructure Panel on the `MissionControlPage`, managing the drawer state.

- [ ] **Step 6: Commit**
```bash
git add frontend/src/pages/mission-control/ frontend/src/hooks/
git commit -m "feat(ui): implement mission control status bar and infra panel"
```
