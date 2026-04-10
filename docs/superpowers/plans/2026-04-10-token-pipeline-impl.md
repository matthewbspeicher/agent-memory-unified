# Token Pipeline Integration Plan (REVISED)

> **Status:** Infrastructure exists. This plan covers integration into the build pipeline and component refactor.
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Connect the existing design token pipeline to Tailwind and component styles, establishing CSS variables as the single source of truth.

**Current State:**
- ✅ `frontend/design/DESIGN.md` — Obsidian Neural spec (17 color roles)
- ✅ `frontend/design/build-tokens.mjs` — Parser + generator (13 tests passing)
- ✅ `frontend/src/styles/tokens.generated.css` — 45 CSS variables generated
- ✅ `frontend/tailwind.tokens.generated.js` — designTokens export with semantic aliases
- ❌ `tailwind.config.js` — Does NOT import designTokens (hardcoded colors)
- ❌ `src/index.css` — Does NOT import tokens.generated.css (hardcoded hex)
- ❌ `package.json` — Missing design:build, design:check, test:design scripts

---

### Task 1: Add npm Scripts

**Files:**
- Modify: `frontend/package.json`

- [x] **Step 1: Add design scripts**
```json
{
  "scripts": {
    "design:build": "node design/build-tokens.mjs",
    "design:check": "node design/build-tokens.mjs --check",
    "test:design": "node --test design/build-tokens.test.mjs design/build-tokens.swap.test.mjs"
  }
}
```

- [x] **Step 2: Integrate into dev/build pipeline**
Update `dev` to prepend `design:build`, `build` to prepend `design:check`:
```json
{
  "dev": "npm run design:build && vite",
  "build": "npm run design:check && vite build"
}
```

- [x] **Step 3: Verify**
```bash
cd frontend && npm run design:build
cd frontend && npm run design:check
```

- [x] **Step 4: Commit**
```bash
git add frontend/package.json
git commit -m "feat(design): add npm scripts and integrate into build pipeline"
```

---

### Task 2: Import Tokens in Tailwind Config

**Files:**
- Modify: `frontend/tailwind.config.js`

- [x] **Step 1: Import designTokens**
Add at top:
```js
import { designTokens } from './tailwind.tokens.generated.js';
```

- [x] **Step 2: Extend theme with designTokens**
Replace hardcoded colors/shadows with generated tokens:
```js
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ...designTokens.colors,
        // Trading-specific (keep these)
        'trading-bg': '#0d1117',
        'trading-surface': '#161b22',
        'trading-elevated': '#21262d',
        'trading-border': '#30363d',
        gain: '#10b981',
        'gain-hover': '#34d399',
        loss: '#ef4444',
        'loss-hover': '#f87171',
        neutral: '#6b7280',
        accent: '#8b5cf6',
        'accent-hover': '#a78bfa',
        'accent-light': '#c4b5fd',
        success: '#10b981',
        warning: '#f59e0b',
        error: '#ef4444',
        info: '#3b82f6',
      },
      fontFamily: designTokens.fontFamily,
      borderRadius: {
        ...designTokens.borderRadius,
        DEFAULT: '0.5rem',
        sm: '0.25rem',
        md: '0.375rem',
        lg: '0.5rem',
        xl: '0.75rem',
        '2xl': '1rem',
        full: '9999px',
      },
      boxShadow: {
        ...designTokens.boxShadow,
        'card-hover': '0 10px 15px rgba(0, 0, 0, 0.5)',
        'modal': '0 20px 25px rgba(0, 0, 0, 0.6)',
      },
      // Keep animations
      animation: { /* existing */ },
      keyframes: { /* existing */ },
    },
  },
  plugins: [],
}
```

- [x] **Step 3: Verify**
```bash
cd frontend && npx tailwindcss --content ./src/components/**/*.tsx --output /dev/null
```

- [x] **Step 4: Commit**
```bash
git add frontend/tailwind.config.js
git commit -m "refactor(frontend): import designTokens into Tailwind config"
```

---

### Task 3: Import Tokens CSS in index.css

**Files:**
- Modify: `frontend/src/index.css`

- [x] **Step 1: Add import at top**
```css
@import './styles/tokens.generated.css';

@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [x] **Step 2: Refactor body styles to use CSS variables**
```css
@layer base {
    body {
        @apply antialiased;
        background-color: var(--color-bg-base);
        color: var(--color-text-primary);
        background-image: 
            radial-gradient(circle at 50% -20%, rgba(var(--color-accent-primary-rgb), 0.15), transparent 40%),
            radial-gradient(circle at 0% 0%, rgba(var(--color-accent-danger-rgb), 0.05), transparent 30%),
            radial-gradient(circle at 100% 100%, rgba(var(--color-accent-success-rgb), 0.05), transparent 30%);
        background-attachment: fixed;
        selection-bg: var(--color-selection-bg);
        selection-text: var(--color-selection-text);
    }
}
```

- [x] **Step 3: Refactor component classes to use CSS variables**
```css
@layer components {
    .glass-panel {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(24px);
        border: 1px solid rgba(var(--color-border-subtle-rgb), 0.1);
        border-radius: var(--radius-card);
        box-shadow: var(--shadow-card);
    }

    .neural-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(24px);
        border: 1px solid rgba(var(--color-border-subtle-rgb), 0.1);
        border-radius: var(--radius-card);
        box-shadow: var(--shadow-card);
        padding: 1.5rem;
        transition: all 0.5s;
    }
    .neural-card:hover {
        border-color: rgba(var(--color-border-subtle-rgb), 0.2);
    }

    .neural-card-indigo {
        /* ... use var(--shadow-glow-primary) ... */
    }

    .neural-card-rose {
        /* ... use var(--shadow-glow-danger) ... */
    }

    .neural-card-emerald {
        /* ... use var(--shadow-glow-success) ... */
    }

    .neural-button-primary {
        /* ... use var(--color-accent-primary) ... */
    }

    .neural-button-danger {
        /* ... use var(--color-accent-danger) ... */
    }
}
```

- [x] **Step 4: Keep rarity animations unchanged**
The `legendary-glow` and `epic-pulse` animations are game-theme, not brand-theme. Leave as-is.

- [x] **Step 5: Verify build**
```bash
cd frontend && npm run build
```

- [x] **Step 6: Commit**
```bash
git add frontend/src/index.css
git commit -m "refactor(frontend): use CSS variables in base styles and component classes"
```

---

### Task 4: Refactor Existing Arena Components

**Files:**
- Modify: `frontend/src/components/arena/ArenaMatchStream.tsx`
- Modify: `frontend/src/components/arena/ArenaBettingForm.tsx`

- [x] **Step 1: Refactor ArenaMatchStream.tsx**
Replace hardcoded hex values with token classes:
```tsx
// Before:
className="bg-[#050505] border border-[#1a1a1a]..."

// After:
className="bg-bg-base border border-border-subtle..."
```

Specific replacements:
| Before | After |
|--------|-------|
| `bg-[#050505]` | `bg-bg-base` |
| `bg-[#0a0a0a]` | `bg-bg-surface` |
| `border-[#1a1a1a]` | `border-border-subtle` |
| `border-[#111]` | `border-border-subtle/50` |
| `text-emerald-500` | `text-accent-success` |
| `text-rose-400` | `text-accent-danger` |
| `bg-emerald-500/10` | `bg-accent-success/10` |
| `border-emerald-500/20` | `border-accent-success/20` |

- [x] **Step 2: Refactor ArenaBettingForm.tsx**
Same pattern:
| Before | After |
|--------|-------|
| `bg-[#0a0a0a]` | `bg-bg-surface` |
| `border-[#1a1a1a]` | `border-border-subtle` |
| `bg-[#0d0d0d]` | `bg-bg-base` |
| `border-emerald-500` | `border-accent-success` |
| `bg-emerald-500/5` | `bg-accent-success/5` |
| `text-emerald-400` | `text-accent-success` |
| `text-emerald-500` | `text-accent-success` |
| `border-blue-500` | `border-accent-primary` |
| `text-blue-400` | `text-accent-primary` |

- [x] **Step 3: Verify**
```bash
cd frontend && npm run build
```

- [x] **Step 4: Commit**
```bash
git add frontend/src/components/arena/
git commit -m "refactor(arena): use design tokens in existing components"
```

---

### Task 5: CI Workflow for Stale Tokens

**Files:**
- Create: `.github/workflows/design-tokens-stale.yml`

- [x] **Step 1: Create workflow**
```yaml
name: Design Tokens Stale Check
on:
  pull_request:
    paths:
      - 'frontend/design/DESIGN.md'
      - 'frontend/tailwind.tokens.generated.js'
      - 'frontend/src/styles/tokens.generated.css'

jobs:
  check-tokens:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Check tokens are up to date
        working-directory: frontend
        run: |
          npm run design:build
          git diff --exit-code tailwind.tokens.generated.js src/styles/tokens.generated.css
```

- [x] **Step 2: Commit**
```bash
git add .github/workflows/design-tokens-stale.yml
git commit -m "ci(design): add stale token detection workflow"
```

---

### Verification Checklist

- [x] `npm run design:build` succeeds
- [x] `npm run design:check` exits 0 (idempotent)
- [x] `npm run test:design` passes (13 tests)
- [x] `npm run build` succeeds (Tailwind compiles)
- [x] No hardcoded `#[0-9A-Fa-f]{6}` in arena components
- [x] CSS variables resolve correctly in browser devtools
