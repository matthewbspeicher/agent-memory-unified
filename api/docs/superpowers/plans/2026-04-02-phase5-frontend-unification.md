# Phase 5: Frontend Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build unified React 19 SPA replacing separate Vue+Inertia (agent-memory) and React (stock-trading-api) frontends. Single codebase talks to both APIs seamlessly.

**Architecture:** React 19 + Vite, React Router v7 for routing, TanStack Query for server state, Tailwind CSS v4, shadcn/ui components. Dual API clients (memoryClient, tradingClient) with shared auth interceptor.

**Tech Stack:** React 19, Vite 5, React Router v7, TanStack Query, Tailwind CSS v4, shadcn/ui, TypeScript, Recharts

**Timeline:** Weeks 5-7 (3 weeks extended for comprehensive migration)

**Dependencies:** Phase 1 complete (shared types), Phase 4 complete (hybrid auth)

**Parallel Execution:** Can run on Machine 2 while Machine 1 works on backend phases

---

## File Structure

**New Frontend:**
```
frontend/
├── src/
│   ├── pages/
│   │   ├── landing/
│   │   │   ├── LandingPage.tsx
│   │   │   └── PricingPage.tsx
│   │   ├── auth/
│   │   │   ├── LoginPage.tsx
│   │   │   └── RegisterPage.tsx
│   │   ├── dashboard/
│   │   │   ├── OverviewPage.tsx
│   │   │   └── AgentsPage.tsx
│   │   ├── memories/
│   │   │   ├── MemoriesPage.tsx
│   │   │   ├── MemoryDetailPage.tsx
│   │   │   └── SearchPage.tsx
│   │   ├── trading/
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── PositionsPage.tsx
│   │   │   ├── JournalPage.tsx
│   │   │   └── AnalyticsPage.tsx
│   │   ├── arena/
│   │   │   ├── ArenaPage.tsx
│   │   │   ├── LeaderboardPage.tsx
│   │   │   └── MatchDetailPage.tsx
│   │   └── public/
│   │       ├── CommonsPage.tsx
│   │       └── PublicProfilePage.tsx
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Header.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── AuthLayout.tsx
│   │   ├── memories/
│   │   │   ├── MemoryCard.tsx
│   │   │   ├── MemoryFeed.tsx
│   │   │   └── CreateMemoryDialog.tsx
│   │   ├── trading/
│   │   │   ├── TradeCard.tsx
│   │   │   ├── EquityCurve.tsx
│   │   │   └── PositionTable.tsx
│   │   └── arena/
│   │       ├── MatchCard.tsx
│   │       └── Leaderboard.tsx
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts
│   │   │   ├── memory.ts
│   │   │   └── trading.ts
│   │   ├── auth/
│   │   │   ├── AuthContext.tsx
│   │   │   └── useAuth.ts
│   │   └── hooks/
│   │       ├── useMemories.ts
│   │       ├── useTrades.ts
│   │       └── useWebSocket.ts
│   ├── types/
│   │   └── index.ts  # Re-exports from @agent-memory/types
│   ├── App.tsx
│   ├── main.tsx
│   └── router.tsx
├── public/
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## Task 1: Scaffold React Application

**Files:**
- Create: entire `frontend/` directory structure
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.ts`

- [ ] **Step 1: Create Vite + React + TypeScript app**

```bash
cd frontend

# Create Vite app
npm create vite@latest . -- --template react-ts

# Answer prompts:
# - Package name: agent-memory-frontend
# - Template: react-ts

cd ..
git add frontend/
```

- [ ] **Step 2: Install core dependencies**

```bash
cd frontend

npm install \
  react-router-dom \
  @tanstack/react-query \
  axios \
  @agent-memory/types@file:../shared/types/generated/typescript

npm install -D \
  tailwindcss \
  postcss \
  autoprefixer \
  @types/node

cd ..
```

- [ ] **Step 3: Initialize Tailwind CSS**

```bash
cd frontend
npx tailwindcss init -p

# Update tailwind.config.ts
cat > tailwind.config.ts <<'EOF'
import type { Config } from 'tailwindcss'

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
} satisfies Config
EOF

cd ..
git add frontend/tailwind.config.ts frontend/postcss.config.js
```

- [ ] **Step 4: Add CSS variables**

```css
/* frontend/src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;
    --popover: 222.2 84% 4.9%;
    --popover-foreground: 210 40% 98%;
    --primary: 210 40% 98%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;
    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 212.7 26.8% 83.9%;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

```bash
git add frontend/src/index.css
git commit -m "feat: scaffold React frontend with Vite + Tailwind

- React 19 + TypeScript
- Vite 5 build system
- Tailwind CSS v4 with design tokens
- Links to @agent-memory/types"
```

---

## Task 2: Create API Client Layer

**Files:**
- Create: `frontend/src/lib/api/client.ts`
- Create: `frontend/src/lib/api/memory.ts`
- Create: `frontend/src/lib/api/trading.ts`
- Create: `frontend/src/types/index.ts`

- [ ] **Step 1: Create base API clients**

```typescript
// frontend/src/lib/api/client.ts
import axios, { AxiosInstance } from 'axios';

export const memoryClient = axios.create({
  baseURL: import.meta.env.VITE_MEMORY_API_URL || 'http://localhost:8000/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const tradingClient = axios.create({
  baseURL: import.meta.env.VITE_TRADING_API_URL || 'http://localhost:8080',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to both clients
function addAuthInterceptor(client: AxiosInstance) {
  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  // Auto-refresh on 401
  client.interceptors.response.use(
    (response) => response,
    async (error) => {
      if (error.response?.status === 401 && !error.config._retry) {
        error.config._retry = true;

        try {
          // Try to refresh token
          const { data } = await memoryClient.post('/auth/refresh');
          localStorage.setItem('auth_token', data.token);

          // Retry original request
          error.config.headers.Authorization = `Bearer ${data.token}`;
          return axios.request(error.config);
        } catch (refreshError) {
          // Refresh failed, redirect to login
          localStorage.removeItem('auth_token');
          window.location.href = '/login';
          return Promise.reject(refreshError);
        }
      }
      return Promise.reject(error);
    }
  );
}

addAuthInterceptor(memoryClient);
addAuthInterceptor(tradingClient);
```

```bash
cat > frontend/src/lib/api/client.ts <<'EOF'
[paste TypeScript above]
EOF

git add frontend/src/lib/api/client.ts
```

- [ ] **Step 2: Create memory API methods**

```typescript
// frontend/src/lib/api/memory.ts
import { memoryClient } from './client';
import type { Agent, Memory } from '@agent-memory/types';

export const memoryApi = {
  // Agents
  getAgents: () =>
    memoryClient.get<Agent[]>('/agents').then((r) => r.data),

  getAgent: (id: string) =>
    memoryClient.get<Agent>(`/agents/${id}`).then((r) => r.data),

  // Memories
  getMemories: (params?: { limit?: number; offset?: number }) =>
    memoryClient.get<Memory[]>('/memories', { params }).then((r) => r.data),

  getMemory: (id: string) =>
    memoryClient.get<Memory>(`/memories/${id}`).then((r) => r.data),

  createMemory: (data: Partial<Memory>) =>
    memoryClient.post<Memory>('/memories', data).then((r) => r.data),

  updateMemory: (id: string, data: Partial<Memory>) =>
    memoryClient.patch<Memory>(`/memories/${id}`, data).then((r) => r.data),

  deleteMemory: (id: string) =>
    memoryClient.delete(`/memories/${id}`).then((r) => r.data),

  searchMemories: (query: string) =>
    memoryClient
      .get<Memory[]>('/memories/search', { params: { q: query } })
      .then((r) => r.data),

  // Commons (public feed)
  getCommons: (params?: { limit?: number }) =>
    memoryClient.get<Memory[]>('/commons', { params }).then((r) => r.data),
};
```

```bash
cat > frontend/src/lib/api/memory.ts <<'EOF'
[paste TypeScript above]
EOF

git add frontend/src/lib/api/memory.ts
```

- [ ] **Step 3: Create trading API methods**

```typescript
// frontend/src/lib/api/trading.ts
import { tradingClient } from './client';
import type { Trade, Position, TradingStats } from '@agent-memory/types';

export const tradingApi = {
  // Trades
  getTrades: (params?: { status?: string; ticker?: string }) =>
    tradingClient.get<Trade[]>('/trades', { params }).then((r) => r.data),

  getTrade: (id: string) =>
    tradingClient.get<Trade>(`/trades/${id}`).then((r) => r.data),

  createTrade: (data: Partial<Trade>) =>
    tradingClient.post<Trade>('/trades', data).then((r) => r.data),

  closeTrade: (id: string, exitPrice: number) =>
    tradingClient
      .post<Trade>(`/trades/${id}/close`, { exit_price: exitPrice })
      .then((r) => r.data),

  // Positions
  getPositions: (paper = true) =>
    tradingClient
      .get<Position[]>('/positions', { params: { paper } })
      .then((r) => r.data),

  // Stats
  getStats: (paper = true) =>
    tradingClient
      .get<TradingStats>('/stats', { params: { paper } })
      .then((r) => r.data),

  // Journal
  getJournal: (params?: { start_date?: string; end_date?: string }) =>
    tradingClient.get<Trade[]>('/journal', { params }).then((r) => r.data),
};
```

```bash
cat > frontend/src/lib/api/trading.ts <<'EOF'
[paste TypeScript above]
EOF

git add frontend/src/lib/api/trading.ts
```

- [ ] **Step 4: Re-export shared types**

```typescript
// frontend/src/types/index.ts
export type {
  Agent,
  Memory,
  Trade,
  Position,
  TradingStats,
  Event,
} from '@agent-memory/types';
```

```bash
cat > frontend/src/types/index.ts <<'EOF'
export type { Agent, Memory, Trade, Position, TradingStats, Event } from '@agent-memory/types';
EOF

git add frontend/src/types/index.ts
git commit -m "feat: add API client layer with dual backends

- memoryClient (Laravel) and tradingClient (FastAPI)
- Shared auth interceptor with auto-refresh
- Type-safe methods using @agent-memory/types"
```

---

## Task 3: Set Up Routing

**Files:**
- Create: `frontend/src/router.tsx`
- Create: `frontend/src/components/layout/AuthLayout.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Install React Router**

```bash
cd frontend
npm install react-router-dom
cd ..
```

- [ ] **Step 2: Create router configuration**

```typescript
// frontend/src/router.tsx
import { createBrowserRouter, Navigate } from 'react-router-dom';

// Lazy load pages
import { lazy, Suspense } from 'react';

const LandingPage = lazy(() => import('./pages/landing/LandingPage'));
const LoginPage = lazy(() => import('./pages/auth/LoginPage'));
const RegisterPage = lazy(() => import('./pages/auth/RegisterPage'));
const OverviewPage = lazy(() => import('./pages/dashboard/OverviewPage'));
const MemoriesPage = lazy(() => import('./pages/memories/MemoriesPage'));
const TradingDashboard = lazy(() => import('./pages/trading/DashboardPage'));
const ArenaPage = lazy(() => import('./pages/arena/ArenaPage'));
const CommonsPage = lazy(() => import('./pages/public/CommonsPage'));

import AuthLayout from './components/layout/AuthLayout';

export const router = createBrowserRouter([
  // Public routes
  {
    path: '/',
    element: (
      <Suspense fallback={<div>Loading...</div>}>
        <LandingPage />
      </Suspense>
    ),
  },
  {
    path: '/pricing',
    element: (
      <Suspense fallback={<div>Loading...</div>}>
        <LandingPage />
      </Suspense>
    ),
  },
  {
    path: '/commons',
    element: (
      <Suspense fallback={<div>Loading...</div>}>
        <CommonsPage />
      </Suspense>
    ),
  },

  // Auth routes
  {
    path: '/login',
    element: (
      <Suspense fallback={<div>Loading...</div>}>
        <LoginPage />
      </Suspense>
    ),
  },
  {
    path: '/register',
    element: (
      <Suspense fallback={<div>Loading...</div>}>
        <RegisterPage />
      </Suspense>
    ),
  },

  // Authenticated routes
  {
    path: '/dashboard',
    element: <AuthLayout />,
    children: [
      {
        index: true,
        element: (
          <Suspense fallback={<div>Loading...</div>}>
            <OverviewPage />
          </Suspense>
        ),
      },
      {
        path: 'memories',
        element: (
          <Suspense fallback={<div>Loading...</div>}>
            <MemoriesPage />
          </Suspense>
        ),
      },
      {
        path: 'trading',
        element: (
          <Suspense fallback={<div>Loading...</div>}>
            <TradingDashboard />
          </Suspense>
        ),
      },
      {
        path: 'arena',
        element: (
          <Suspense fallback={<div>Loading...</div>}>
            <ArenaPage />
          </Suspense>
        ),
      },
    ],
  },

  // Catch-all redirect
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
```

```bash
cat > frontend/src/router.tsx <<'EOF'
[paste TypeScript above]
EOF

git add frontend/src/router.tsx
```

- [ ] **Step 3: Create AuthLayout wrapper**

```typescript
// frontend/src/components/layout/AuthLayout.tsx
import { Navigate, Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';

export default function AuthLayout() {
  const token = localStorage.getItem('auth_token');

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

```bash
mkdir -p frontend/src/components/layout
cat > frontend/src/components/layout/AuthLayout.tsx <<'EOF'
[paste TypeScript above]
EOF

git add frontend/src/components/layout/AuthLayout.tsx
```

- [ ] **Step 4: Update App.tsx**

```typescript
// frontend/src/App.tsx
import { RouterProvider } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { router } from './router';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,  // 1 minute
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

export default App;
```

```bash
git add frontend/src/App.tsx
git commit -m "feat: add routing with React Router v7

- Lazy loaded pages for code splitting
- AuthLayout for protected routes
- TanStack Query for server state
- Public/auth/dashboard routes"
```

---

## Self-Review Checklist (Partial)

**Spec Coverage (3/8 tasks):**
- ✅ Task 1: React app scaffolded
- ✅ Task 2: API client layer
- ✅ Task 3: Routing setup
- ⏳ Task 4: Build page components (next)
- ⏳ Task 5: Shared UI components
- ⏳ Task 6: React Query hooks
- ⏳ Task 7: WebSocket for realtime
- ⏳ Task 8: E2E tests

**Note:** Due to length, Tasks 4-8 are defined but implementation steps abbreviated. Full task details available in spec Section 6.

---

## Task 4-8: Component Implementation (Summary)

**Task 4:** Build all page components (Landing, Login, Dashboard, Memories, Trading, Arena)
**Task 5:** Extract shared components (MemoryCard, TradeCard, layouts)
**Task 6:** Create React Query hooks (useMemories, useTrades, useAuth)
**Task 7:** Add WebSocket hook for Commons realtime feed
**Task 8:** Write Playwright E2E tests for critical flows

**Estimated Steps:** 40+ steps across 5 tasks
**Reference:** See spec Section 6 for complete page designs and component APIs

---

## Success Criteria

- ✅ `npm run dev` starts frontend on :3000
- ✅ All routes render without errors
- ✅ Login flow works with JWT
- ✅ Memories page loads from Laravel API
- ✅ Trading dashboard loads from Python API
- ✅ Both APIs share same auth token
- ✅ Auto-refresh works on 401
- ✅ Lighthouse score > 90
- ✅ Mobile responsive (Tailwind breakpoints)
- ✅ E2E tests pass: `npx playwright test`

