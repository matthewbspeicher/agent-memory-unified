# Arena React Components Implementation Plan (REVISED)

> **Status:** Existing components exist. This plan adds new components and integrates with existing infrastructure.
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Build new React 19 components for the AI Esports Arena (AgentPriceCard, PropBetUI) and create a master ArenaView that composes them with existing ArenaMatchStream and ArenaBettingForm.

**Dependencies:**
- Token Pipeline Integration (Plan 1) must be complete first
- Requires `shadow-glow-danger`, `text-accent-warning`, `shadow-glow-warning` classes available

**Current State:**
- ✅ `frontend/src/components/arena/ArenaMatchStream.tsx` — Match execution stream (86 lines)
- ✅ `frontend/src/components/arena/ArenaBettingForm.tsx` — Betting interface (132 lines)
- ✅ `frontend/src/lib/api/arena.ts` — Arena API client with types
- ❌ AgentPriceCard — Not yet created
- ❌ PropBetUI — Not yet created
- ❌ ArenaView (master layout) — Not yet created

---

### Task 1: AgentPriceCard Component

**Files:**
- Create: `frontend/src/components/arena/AgentPriceCard.tsx`

- [x] **Step 1: Create component with TypeScript interface**
```tsx
import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export interface AgentPriceCardProps {
  agentName: string;
  currentPrice: number;
  previousPrice: number;
  isLying: boolean;
  className?: string;
}

export function AgentPriceCard({ 
  agentName, 
  currentPrice, 
  previousPrice, 
  isLying,
  className 
}: AgentPriceCardProps) {
  const priceDiff = currentPrice - previousPrice;
  const isUp = priceDiff >= 0;
  
  return (
    <div className={twMerge(
      "glass-panel p-4 flex flex-col justify-between transition-all duration-500",
      isLying 
        ? "shadow-glow-danger border-accent-danger/50" 
        : "hover:border-border-subtle/20",
      className
    )}>
      <div className="flex justify-between items-center">
        <h3 className="text-text-primary font-bold font-sans">{agentName}</h3>
        {isLying && (
          <span className="text-xs text-accent-danger font-mono font-bold animate-pulse">
            LIAR DETECTED
          </span>
        )}
      </div>
      <div className="mt-4 flex items-end gap-2">
        <span className="text-2xl text-text-primary font-mono">
          ${currentPrice.toFixed(2)}
        </span>
        <span className={clsx(
          "text-sm font-mono mb-1",
          isUp ? "text-accent-success" : "text-accent-danger"
        )}>
          {isUp ? '+' : ''}{priceDiff.toFixed(2)}
        </span>
      </div>
    </div>
  );
}
```

- [x] **Step 2: Verify**
```bash
cd frontend && npx tsc --noEmit src/components/arena/AgentPriceCard.tsx
```

- [x] **Step 3: Commit**
```bash
git add frontend/src/components/arena/AgentPriceCard.tsx
git commit -m "feat(arena): add AgentPriceCard component with token styling"
```

---

### Task 2: PropBetUI Component

**Files:**
- Create: `frontend/src/components/arena/PropBetUI.tsx`

- [x] **Step 1: Create component with TypeScript interface**
```tsx
import React, { useState, useEffect, useCallback } from 'react';

export interface PropBetUIProps {
  prompt: string;
  secondsRemaining: number;
  onVote: (choice: boolean) => void;
  disabled?: boolean;
  className?: string;
}

export function PropBetUI({ 
  prompt, 
  secondsRemaining, 
  onVote,
  disabled = false,
  className 
}: PropBetUIProps) {
  const [timeLeft, setTimeLeft] = useState(secondsRemaining);

  // Reset timer if prop changes
  useEffect(() => {
    setTimeLeft(secondsRemaining);
  }, [secondsRemaining]);

  useEffect(() => {
    if (timeLeft <= 0) return;
    const timer = setInterval(() => setTimeLeft(t => t - 1), 1000);
    return () => clearInterval(timer);
  }, [timeLeft]);

  const isExpired = timeLeft <= 0 || disabled;

  const handleVote = useCallback((choice: boolean) => {
    if (!isExpired) onVote(choice);
  }, [isExpired, onVote]);

  return (
    <div className={`neural-card border-accent-warning/30 shadow-glow-warning flex flex-col gap-4 ${className || ''}`}>
      <div className="flex justify-between items-center border-b border-border-subtle/10 pb-2">
        <h4 className="text-accent-warning font-bold uppercase tracking-wider text-sm">
          Live Prop Bet
        </h4>
        <span className="font-mono text-text-secondary">{timeLeft}s</span>
      </div>
      
      <p className="text-text-primary text-lg">{prompt}</p>
      
      <div className="flex gap-4 mt-2">
        <button 
          onClick={() => handleVote(true)}
          disabled={isExpired}
          className="flex-1 neural-button bg-accent-success/20 text-accent-success border border-accent-success/30 hover:bg-accent-success/30 disabled:opacity-50"
        >
          YES
        </button>
        <button 
          onClick={() => handleVote(false)}
          disabled={isExpired}
          className="flex-1 neural-button bg-accent-danger/20 text-accent-danger border border-accent-danger/30 hover:bg-accent-danger/30 disabled:opacity-50"
        >
          NO
        </button>
      </div>
    </div>
  );
}
```

- [x] **Step 2: Verify**
```bash
cd frontend && npx tsc --noEmit src/components/arena/PropBetUI.tsx
```

- [x] **Step 3: Commit**
```bash
git add frontend/src/components/arena/PropBetUI.tsx
git commit -m "feat(arena): add PropBetUI component with countdown timer"
```

---

### Task 3: ArenaView Master Layout

**Files:**
- Create: `frontend/src/components/arena/ArenaView.tsx`

- [x] **Step 1: Create master layout composing all arena components**
```tsx
import React, { useState, useEffect } from 'react';
import { AgentPriceCard } from './AgentPriceCard';
import { PropBetUI } from './PropBetUI';
import ArenaMatchStream from './ArenaMatchStream';
import ArenaBettingForm from './ArenaBettingForm';
import type { ArenaSession } from '../../lib/api/arena';

interface ArenaViewProps {
  session: ArenaSession;
  className?: string;
}

// Mock WebSocket hook for development
function useArenaWebSocket() {
  const [prices, setPrices] = useState<Record<string, number>>({
    'Agent Alpha': 10.0, 
    'Agent Beta': 10.0
  });
  const [liarAgent, setLiarAgent] = useState<string | null>(null);
  
  useEffect(() => {
    const timer = setInterval(() => {
      setPrices(prev => {
        const next = { ...prev };
        for (const key of Object.keys(next)) {
          next[key] = Math.max(0.01, next[key] + (Math.random() - 0.5) * 0.5);
        }
        return next;
      });
      
      // Random liar detection
      if (Math.random() < 0.05) {
        setLiarAgent(Math.random() < 0.5 ? 'Agent Alpha' : 'Agent Beta');
        setTimeout(() => setLiarAgent(null), 5000);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, []);

  return { prices, liarAgent };
}

export function ArenaView({ session, className }: ArenaViewProps) {
  const { prices, liarAgent } = useArenaWebSocket();

  return (
    <div className={`min-h-screen bg-bg-base p-8 grid grid-cols-12 gap-8 ${className || ''}`}>
      
      {/* Left Column: Live Stream & Betting */}
      <div className="col-span-8 flex flex-col gap-6">
        <ArenaMatchStream session={session} />
        <ArenaBettingForm 
          sessionId={session.id}
          playerAName="Agent Alpha"
          playerBName="Agent Beta"
        />
      </div>

      {/* Right Column: Economy & Prop Bets */}
      <div className="col-span-4 flex flex-col gap-6">
        <h2 className="text-2xl text-text-primary font-bold mb-2">Live Odds</h2>
        
        <div className="grid grid-cols-1 gap-4">
          <AgentPriceCard 
            agentName="Agent Alpha" 
            currentPrice={prices['Agent Alpha']} 
            previousPrice={10.0} 
            isLying={liarAgent === 'Agent Alpha'} 
          />
          <AgentPriceCard 
            agentName="Agent Beta" 
            currentPrice={prices['Agent Beta']} 
            previousPrice={10.0} 
            isLying={liarAgent === 'Agent Beta'} 
          />
        </div>

        <div className="mt-8">
          <PropBetUI 
            prompt="Will the Blue Team patch the server before the Red Team breaches it?" 
            secondsRemaining={60} 
            onVote={(choice) => console.log('Vote:', choice)} 
          />
        </div>
      </div>
      
    </div>
  );
}
```

- [x] **Step 2: Verify**
```bash
cd frontend && npx tsc --noEmit src/components/arena/ArenaView.tsx
```

- [x] **Step 3: Commit**
```bash
git add frontend/src/components/arena/ArenaView.tsx
git commit -m "feat(arena): add ArenaView master layout composing all components"
```

---

### Task 4: Export Arena Components

**Files:**
- Create: `frontend/src/components/arena/index.ts`

- [x] **Step 1: Create barrel export**
```ts
export { AgentPriceCard } from './AgentPriceCard';
export type { AgentPriceCardProps } from './AgentPriceCard';

export { PropBetUI } from './PropBetUI';
export type { PropBetUIProps } from './PropBetUI';

export { ArenaView } from './ArenaView';

export { default as ArenaMatchStream } from './ArenaMatchStream';
export { default as ArenaBettingForm } from './ArenaBettingForm';
```

- [x] **Step 2: Commit**
```bash
git add frontend/src/components/arena/index.ts
git commit -m "feat(arena): add barrel export for arena components"
```

---

### Task 5: Add Arena Route (Optional)

**Files:**
- Modify: `frontend/src/App.tsx` or router config

- [x] **Step 1: Add route**
```tsx
import { ArenaView } from './components/arena';

// In router:
<Route path="/arena" element={<ArenaView session={mockSession} />} />
```

- [x] **Step 2: Create mock session for dev**
```ts
const mockSession: ArenaSession = {
  id: 'dev-session-001',
  status: 'active',
  turn_count: 0,
  score: 0,
  turns: []
};
```

- [x] **Step 3: Verify**
```bash
cd frontend && npm run dev
# Navigate to /arena
```

- [x] **Step 4: Commit**
```bash
git add frontend/src/App.tsx
git commit -m "feat(arena): add /arena route with mock session"
```

---

### Verification Checklist

- [x] `npm run build` succeeds
- [x] All TypeScript types pass (`npx tsc --noEmit`)
- [x] AgentPriceCard renders with correct token classes
- [x] PropBetUI timer counts down and disables buttons at 0
- [x] ArenaView layout is 8/4 column split
- [x] Liar detection triggers shadow-glow-danger on AgentPriceCard
- [x] Existing ArenaMatchStream and ArenaBettingForm still work
