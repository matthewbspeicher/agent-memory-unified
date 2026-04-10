# DESIGN.md Token Pipeline for Frontend

**Date:** 2026-04-10
**Status:** Approved — ready for implementation planning
**Author:** Claude Code (brainstorming session with mspeicher)
**Scope:** `frontend/` only
**External inspiration:** [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md)

---

## 1. Motivation

The frontend has a distinctive "Obsidian Neural" visual identity (dark `#050505` base, indigo/rose/emerald glows, glass-morphism panels, radial mesh grid) implemented across 20+ pages and 40+ components. Today that identity lives as scattered conventions in `tailwind.config.js`, `src/index.css`, and inline class usage — there is no canonical source of truth.

The `awesome-design-md` repository popularized a plain-markdown format (introduced by Google Stitch) for describing a brand's visual system in nine fixed sections, intended to be consumed by AI coding agents. A sibling effort (owned by **opencode**, not this Claude Code session) is authoring a canonical brand `DESIGN.md` for this project. When it lands, we need "one command coherent re-theme" — not a 20-page manual rewrite that leaves neural/obsidian residue behind.

This spec describes the infrastructure we build **now**, before the canonical brand file lands, so that dropping it in becomes a tractable operation instead of a multi-week refactor.

## 2. Goals and non-goals

### Goals

1. Establish `frontend/design/DESIGN.md` as the single source of truth for brand-level design tokens (colors, typography, elevation).
2. Build a parser that extracts those tokens into generated CSS custom properties and a Tailwind config module.
3. Refactor the existing component classes in `src/index.css` and the `tailwind.config.js` to consume the generated tokens, via CSS variables, so a swap of `DESIGN.md` propagates through the stylesheet without manual edits.
4. Ship an initial placeholder `DESIGN.md` equal to the current Obsidian Neural identity, so nothing visually changes at v1.
5. Provide CI enforcement that generated files cannot drift from `DESIGN.md`.
6. Document a narrow, actionable handoff workflow for when opencode's canonical brand file arrives, including rollback.

### Non-goals

- **Authoring a new canonical brand in Claude Code.** The brand is opencode's concern. We ship infrastructure + a placeholder.
- **Whole-codebase hardcoded-hex cleanup.** An audit is planned (see §12); cleanup is sized during implementation planning, not specified here.
- **Per-surface / per-page brand overrides.** A dual-layer canonical + per-surface model was explicitly rejected in favor of one coherent theme.
- **Dynamic brand switching at runtime.** The pipeline is a build-time transformation; runtime theming is out of scope.
- **Re-theming the trading engine, Taoshi validator, or any non-frontend surface.** This is a frontend-only concern.
- **Migrating `taoshi-vanta/` or anything mounted read-only.**

## 3. Architecture and file layout

```
frontend/
├── design/
│   ├── DESIGN.md                     # canonical source; placeholder = Obsidian Neural
│   ├── preview.html                  # dark-mode visual target (awesome-design-md convention)
│   ├── preview-dark.html             # alias of preview.html, kept for convention parity
│   ├── build-tokens.mjs              # parser + generator (pure Node, no npm deps)
│   ├── build-tokens.test.mjs         # parser unit tests (node:test)
│   ├── build-tokens.swap.test.mjs    # round-trip swap integration test
│   ├── schema.md                     # strict-mode grammar the parser accepts
│   └── README.md                     # how the pipeline works, brand swap procedure
├── src/
│   └── styles/
│       ├── tokens.generated.css      # GENERATED — CSS custom properties on :root
│       └── rarity.css                # game-theme carve-out (legendary/epic glows)
├── tailwind.tokens.generated.js      # GENERATED — imported by tailwind.config.js
├── tailwind.config.js                # MODIFIED — consumes generated module
├── src/index.css                     # MODIFIED — imports tokens.generated.css, classes rewritten
└── tests/visual/
    └── design-tokens.spec.ts         # Playwright visual regression baselines

docs/design/
└── design-bridge-workflow.md         # handoff doc for when opencode's brand lands

.github/workflows/
└── design-tokens-stale.yml           # CI drift check

CLAUDE.md                             # MODIFIED — new "Design System" section
```

**Layout rules:**

- All `*.generated.*` files are **committed**, not gitignored. Rationale: deterministic deploys, PR reviewability, faster CI builds (no generation step at deploy time). Drift is caught by CI, not by runtime generation.
- `DESIGN.md` lives under `frontend/design/`, not repo root. Rationale: it is a frontend concern; the trading engine has no interest in it. The path is documented in `CLAUDE.md` so any AI agent can find it.
- `tailwind.tokens.generated.js` sits at `frontend/` root (next to `tailwind.config.js`) because Tailwind's config resolution prefers local siblings.
- `src/styles/tokens.generated.css` is imported once at the very top of `index.css`, **before** any `@tailwind` directive, so custom properties are available in every layer.

## 4. `DESIGN.md` placeholder contents

Sections 1, 4, 5, 7, 8, 9 (Visual Theme, Component Stylings, Layout, Do's/Don'ts, Responsive, Agent Prompt Guide) are **prose only** — not parsed. They exist for humans and for the `design-bridge` agent. Their absence does not break the pipeline.

Sections 2, 3, 6 (Color Palette & Roles, Typography Rules, Depth & Elevation) are **machine-readable tables** in a strict format. The parser reads only these sections. The placeholder contains:

### 4.1 Color Palette & Roles — 17 semantic roles

| Role               | Hex     | Notes                                 |
|--------------------|---------|---------------------------------------|
| `bg.base`          | #050505 | Obsidian body background              |
| `bg.surface`       | #FFFFFF | White, used with 5% alpha for glass   |
| `border.subtle`    | #FFFFFF | White, used with 10% alpha            |
| `text.primary`     | #F3F4F6 | gray-100                              |
| `text.secondary`   | #9CA3AF | gray-400                              |
| `text.muted`       | #4B5563 | gray-600                              |
| `accent.primary`   | #6366F1 | indigo-500 (was indigo-glow)          |
| `accent.danger`    | #F43F5E | rose-500  (was rose-glow)             |
| `accent.warning`   | #F59E0B | amber-500 (new, used in trading)      |
| `accent.success`   | #10B981 | emerald-500 (was emerald-glow)        |
| `selection.bg`     | #6366F1 | used with 30% alpha                   |
| `selection.text`   | #C7D2FE | indigo-200                            |
| `chart.1`          | #6366F1 | series 1 — matches accent.primary     |
| `chart.2`          | #F43F5E | series 2 — matches accent.danger      |
| `chart.3`          | #10B981 | series 3 — matches accent.success     |
| `chart.4`          | #F59E0B | series 4 — matches accent.warning     |
| `chart.5`          | #8B5CF6 | series 5 — violet-500, also gradient mid |

### 4.2 Typography Rules

| Role | Family          | Fallback stack                                          |
|------|-----------------|---------------------------------------------------------|
| sans | Inter           | ui-sans-serif, system-ui, sans-serif                    |
| mono | JetBrains Mono  | ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas   |

### 4.3 Depth & Elevation

| Role                  | Value                                 |
|-----------------------|---------------------------------------|
| `radius.card`         | 1rem                                  |
| `shadow.card`         | 0 25px 50px -12px rgba(0,0,0,0.25)    |
| `shadow.glow.primary` | 0 0 20px rgba(99,102,241,0.15)        |
| `shadow.glow.danger`  | 0 0 20px rgba(244,63,94,0.15)         |
| `shadow.glow.warning` | 0 0 20px rgba(245,158,11,0.15)        |
| `shadow.glow.success` | 0 0 20px rgba(16,185,129,0.15)        |

The exact column schema (header names, column count, hex validation rule) is documented in `frontend/design/schema.md` and enforced by the parser.

## 5. Parser contract (`frontend/design/build-tokens.mjs`)

### 5.1 Dependencies

Pure Node, using only `node:fs`, `node:path`, and `node:process`. No npm dependencies. Rationale: adding a markdown parser for nine headings bloats `npm install`; the format is narrow enough to walk by hand.

### 5.2 CLI

```
node design/build-tokens.mjs           # generate outputs, writing only on change
node design/build-tokens.mjs --check   # dry-run; exit 1 on drift
node design/build-tokens.mjs --verbose # diagnostic logging
```

### 5.3 Inputs

- `frontend/design/DESIGN.md` (required). Absolute path resolved from the script location.

### 5.4 Outputs (when not in `--check`)

1. `frontend/src/styles/tokens.generated.css` — `:root` block containing:
   - Hex custom properties: `--color-accent-primary: #6366F1;`
   - Space-separated RGB triples: `--color-accent-primary-rgb: 99 102 241;` (enables Tailwind's `rgb(var(--foo-rgb) / <alpha-value>)` opacity-modifier pattern)
   - Font families: `--font-sans`, `--font-mono`
   - Radii: `--radius-card`
   - Shadows: `--shadow-card`, `--shadow-glow-primary`, etc.
2. `frontend/tailwind.tokens.generated.js` — ES module exporting a `designTokens` object consumed by `tailwind.config.js` (see §6.1).

Both files are prepended with `/* GENERATED — do not edit. Source: frontend/design/DESIGN.md */`.

### 5.5 Parse algorithm (strict mode, v1)

1. Read file; split into lines.
2. Walk lines tracking the current `##` heading as `state.section`.
3. For each of the three required sections (`Color Palette & Roles`, `Typography Rules`, `Depth & Elevation`), collect the first markdown table encountered inside that section.
4. Parse rows by splitting on `|` and trimming; validate column count per section (3 for colors, 3 for typography, 2 for elevation).
5. Validate hex values against `/^#[0-9A-Fa-f]{6}$/`.
6. On any validation failure, throw with a message of the form:
   - `DESIGN.md:<line>: bad hex value in role '<role>'`
   - `DESIGN.md missing required section '<name>'`
   - `DESIGN.md:<line>: wrong column count in '<section>' (expected N, got M)`
7. No silent fallbacks. No tolerance for missing sections.
8. Write outputs **only if** they differ from what is currently on disk (idempotency).

### 5.6 `--check` mode

Runs the full parse + generation in memory, then compares byte-for-byte against the committed files. On mismatch: prints the diff and exits `1`. No writes.

### 5.7 Strictness and future tolerance (v2)

Strict parsing is the v1 rule. When opencode's canonical brand file arrives, if its formatting does not match the strict grammar, the `design-bridge` agent normalizes it (see §10) rather than the parser accepting prose. A tolerance layer is deferred to v2 and is out of scope here.

## 6. Token consumption and component refactor

### 6.1 `tailwind.config.js` (modified)

Becomes a thin consumer of the generated module:

```js
/** @type {import('tailwindcss').Config} */
import { designTokens } from './tailwind.tokens.generated.js';

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors:       designTokens.colors,
      fontFamily:   designTokens.fontFamily,
      borderRadius: designTokens.borderRadius,
      boxShadow:    designTokens.boxShadow,
    },
  },
  plugins: [],
};
```

### 6.2 Generated Tailwind token shape

```js
export const designTokens = {
  colors: {
    'bg-base':        'rgb(var(--color-bg-base-rgb) / <alpha-value>)',
    'bg-surface':     'rgb(var(--color-bg-surface-rgb) / <alpha-value>)',
    'border-subtle':  'rgb(var(--color-border-subtle-rgb) / <alpha-value>)',
    'text-primary':   'rgb(var(--color-text-primary-rgb) / <alpha-value>)',
    'text-secondary': 'rgb(var(--color-text-secondary-rgb) / <alpha-value>)',
    'text-muted':     'rgb(var(--color-text-muted-rgb) / <alpha-value>)',
    'accent-primary': 'rgb(var(--color-accent-primary-rgb) / <alpha-value>)',
    'accent-danger':  'rgb(var(--color-accent-danger-rgb)  / <alpha-value>)',
    'accent-warning': 'rgb(var(--color-accent-warning-rgb) / <alpha-value>)',
    'accent-success': 'rgb(var(--color-accent-success-rgb) / <alpha-value>)',
    'selection-bg':   'rgb(var(--color-selection-bg-rgb)   / <alpha-value>)',
    'selection-text': 'rgb(var(--color-selection-text-rgb) / <alpha-value>)',
    'chart-1':        'rgb(var(--color-chart-1-rgb) / <alpha-value>)',
    'chart-2':        'rgb(var(--color-chart-2-rgb) / <alpha-value>)',
    'chart-3':        'rgb(var(--color-chart-3-rgb) / <alpha-value>)',
    'chart-4':        'rgb(var(--color-chart-4-rgb) / <alpha-value>)',
    'chart-5':        'rgb(var(--color-chart-5-rgb) / <alpha-value>)',
    // Legacy aliases — preserved so existing bg-obsidian/bg-indigo-glow classes keep working:
    obsidian:       'rgb(var(--color-bg-base-rgb) / <alpha-value>)',
    'indigo-glow':  'rgb(var(--color-accent-primary-rgb) / <alpha-value>)',
    'rose-glow':    'rgb(var(--color-accent-danger-rgb)  / <alpha-value>)',
    'emerald-glow': 'rgb(var(--color-accent-success-rgb) / <alpha-value>)',
  },
  fontFamily: {
    sans: ['var(--font-sans)'],
    mono: ['var(--font-mono)'],
  },
  borderRadius: {
    card: 'var(--radius-card)',
  },
  boxShadow: {
    card:           'var(--shadow-card)',
    'glow-primary': 'var(--shadow-glow-primary)',
    'glow-danger':  'var(--shadow-glow-danger)',
    'glow-warning': 'var(--shadow-glow-warning)',
    'glow-success': 'var(--shadow-glow-success)',
  },
};
```

The four legacy aliases (`obsidian`, `indigo-glow`, `rose-glow`, `emerald-glow`) are what make "zero visual change at v1" honest. Any existing utility usage (`bg-obsidian`, `bg-indigo-glow/20`) resolves through the new CSS variables. When opencode's brand lands, the aliases map to the *new* accent hex values automatically; anything still using the legacy class name follows. The aliases are kept for this project's lifetime unless explicitly cleaned up in a v2 follow-up.

### 6.3 `src/index.css` refactor

Top of file:

```css
@import './styles/tokens.generated.css';
@import './styles/rarity.css';
@tailwind base;
@tailwind components;
@tailwind utilities;
```

Component classes rewritten:

```css
@layer base {
  body {
    @apply bg-bg-base text-text-primary antialiased
           selection:bg-selection-bg/30 selection:text-selection-text;
    background-image:
      radial-gradient(circle at 50% -20%, rgb(var(--color-accent-primary-rgb) / 0.15), transparent 40%),
      radial-gradient(circle at   0%   0%, rgb(var(--color-accent-danger-rgb)  / 0.05), transparent 30%),
      radial-gradient(circle at 100% 100%, rgb(var(--color-accent-success-rgb) / 0.05), transparent 30%);
    background-attachment: fixed;
  }
}

@layer components {
  .glass-panel {
    @apply bg-bg-surface/5 backdrop-blur-xl border border-border-subtle/10 rounded-card shadow-card;
  }
  .neural-card {
    @apply bg-bg-surface/5 backdrop-blur-xl border border-border-subtle/10 rounded-card shadow-card p-6
           transition-all duration-500 hover:border-border-subtle/20;
  }

  .neural-card-accent {
    @apply bg-bg-surface/5 backdrop-blur-xl border border-border-subtle/10 rounded-card shadow-card p-6
           transition-all duration-500;
  }
  .neural-card-accent[data-accent="primary"]:hover { @apply shadow-glow-primary border-accent-primary/30; }
  .neural-card-accent[data-accent="danger"]:hover  { @apply shadow-glow-danger  border-accent-danger/30;  }
  .neural-card-accent[data-accent="warning"]:hover { @apply shadow-glow-warning border-accent-warning/30; }
  .neural-card-accent[data-accent="success"]:hover { @apply shadow-glow-success border-accent-success/30; }

  /* Legacy classes — mechanism resolved at plan time; see "Legacy card aliases" note below */

  .neural-text-gradient {
    @apply text-transparent bg-clip-text bg-gradient-to-r from-accent-primary via-chart-5 to-accent-danger;
  }

  .neural-input {
    @apply w-full bg-black/40 border border-border-subtle/10 rounded-xl px-4 py-3 text-text-primary placeholder-text-muted
           focus:border-accent-primary/50 focus:ring-1 focus:ring-accent-primary/50 outline-none transition-all duration-300;
  }

  .neural-button          { @apply px-6 py-2.5 rounded-xl font-bold text-sm transition-all duration-300 active:scale-95 disabled:opacity-50; }
  .neural-button-primary  { @apply neural-button bg-accent-primary text-text-primary hover:shadow-glow-primary; }
  .neural-button-secondary{ @apply neural-button bg-bg-surface/5 border border-border-subtle/10 text-text-secondary hover:bg-bg-surface/10 hover:text-text-primary; }
  .neural-button-danger   { @apply neural-button bg-accent-danger/20 border border-accent-danger/30 text-accent-danger hover:bg-accent-danger/30; }
}
```

**Note on legacy card aliases.** The three classes `.neural-card-indigo`, `.neural-card-rose`, and `.neural-card-emerald` must keep working at v1 for zero JSX churn, but Tailwind's `@apply` does not cascade attribute selectors, so `.neural-card-indigo { @apply neural-card-accent; }` would drop the per-color hover glow. Two options the implementation plan will pick between at grep time:

- **(a) Duplicate hover rules.** Keep each legacy class as an independent selector with its own base + `:hover` rules that mirror the `neural-card-accent[data-accent="..."]` pair. More CSS, zero JSX touches.
- **(b) One-shot JSX migration.** Do a targeted sed over `frontend/src/components/**` and `frontend/src/pages/**` replacing `className="neural-card-indigo"` with `className="neural-card-accent" data-accent="primary"` (and rose→danger, emerald→success), then delete the legacy classes entirely. More JSX touches, cleaner CSS.

The grep count of legacy class usages during the plan phase decides which — fewer than ~15 call sites favors (b), more favors (a).

### 6.4 Rarity-tier animations — carve-out

`@keyframes legendary-glow` (amber) and `@keyframes epic-pulse` (purple) move from `index.css` into a new file:

```
frontend/src/styles/rarity.css
```

Header comment at the top:

```css
/*
 * Game-side theme — intentionally NOT driven by DESIGN.md.
 * Rarity tiers (legendary / epic / rare) are gameplay signals, not brand colors.
 * Legendary should always feel gold, epic should always feel purple, regardless
 * of which brand DESIGN.md is in effect.
 */
```

Imported in `index.css` after `tokens.generated.css`. Brand swaps do not touch this file.

### 6.5 Accepted visual tradeoff

`.neural-button-primary` currently uses `bg-indigo-600` (#4F46E5); after refactor it uses `bg-accent-primary` (#6366F1 = indigo-500). `.neural-button-danger` has a similar rose-600 → rose-500 shift. These are deliberate 1-shade changes on two button variants, accepted during design review (Section 3d of the brainstorming session) in exchange for not expanding the 17-token vocabulary to 19 just for pressed-state shades. An emphasis token (`accent.primary.emphasis`) can be added later if opencode's canonical brand requires one.

## 7. Build pipeline

`frontend/package.json` additions:

```json
{
  "scripts": {
    "dev":           "npm run design:build && vite --host 0.0.0.0 --port 3000",
    "build":         "npm run design:check && vite build",
    "design:build":  "node design/build-tokens.mjs",
    "design:check":  "node design/build-tokens.mjs --check",
    "test:design":   "node --test design/build-tokens.test.mjs design/build-tokens.swap.test.mjs"
  }
}
```

**Rationale for the split.** `dev` prepends `design:build` (write on change, idempotent no-op otherwise) so iterating on `DESIGN.md` during local development is frictionless. `build` prepends `design:check` (read-only drift check, hard fail) so deploys never silently regenerate committed files. Running the parser twice in CI is not a concern — the read is a few milliseconds.

**No pre-commit hook.** Local friction stays minimal. Enforcement lives in CI.

## 8. CI workflow

`.github/workflows/design-tokens-stale.yml`:

```yaml
name: design-tokens-stale
on:
  pull_request:
    paths:
      - 'frontend/design/**'
      - 'frontend/src/styles/tokens.generated.css'
      - 'frontend/tailwind.tokens.generated.js'
      - 'frontend/tailwind.config.js'
      - 'frontend/design/build-tokens.mjs'
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd frontend && npm ci
      - run: cd frontend && npm run design:check
      - run: cd frontend && npm run test:design
```

The `paths:` filter keeps the workflow scoped — unrelated PRs do not pay the cost.

## 9. Testing strategy — three layers

### 9.1 Layer 1: parser unit tests

`frontend/design/build-tokens.test.mjs`, using Node's built-in `node:test`. No new dependencies.

Test cases:
- **Happy path.** Parse a fixture DESIGN.md; assert expected token names and hex values in the generated output.
- **Missing required section.** Remove `## Color Palette & Roles`; assert the parser throws with a readable message.
- **Bad hex value.** Fixture with `#XYZ`; assert the thrown error names the line number and role.
- **Wrong column count.** Fixture with a malformed row; assert a clear error message.
- **`--check` mode — fresh.** After running `design:build`, `--check` exits 0.
- **`--check` mode — stale.** Manually mutate the generated file; assert `--check` exits 1 and prints a diff.
- **Idempotency.** Running `design:build` twice on unchanged input produces no writes (assert file `mtime` is unchanged on the second run).

### 9.2 Layer 2: round-trip swap integration test

`frontend/design/build-tokens.swap.test.mjs` — the *real* test that a brand swap works end-to-end before opencode's file lands.

Algorithm:
1. Snapshot the current `tokens.generated.css`.
2. Copy the current `DESIGN.md` to a temp path.
3. Write a synthetic "all red" brand fixture to a temp `DESIGN.md` location, with every color role set to a distinct red-family hex.
4. Run the parser against the temp path, writing to temp output paths.
5. Assert the generated CSS contains the new red hex values.
6. Assert the generated CSS contains **none** of the placeholder hex values.
7. Assert the semantic token names (`--color-accent-primary`, `--color-accent-primary-rgb`, etc.) are structurally identical — only hex values changed.
8. Clean up temp files; original files untouched.

### 9.3 Layer 3: Playwright visual regression

`frontend/tests/visual/design-tokens.spec.ts`. Playwright is already used in this project for e2e — no new dependency.

- Baselines are captured **on current `main` HEAD, before the index.css refactor lands**, as part of Commit 1.
- Asserts 0 pixel diff on five representative pages: `/`, `/leaderboard`, `/arena`, `/bittensor`, `/knowledge-graph`.
- In Commit 2, only pages containing the primary/danger buttons are expected to diff (the accepted 1-shade shift, §6.5). New baselines for those pages are regenerated in the same PR and reviewed manually.
- When opencode's brand lands later, **all** baselines are expected to diff; the swap PR regenerates them wholesale and review is entirely visual.

## 10. `design-bridge` agent handoff

The `design-bridge` agent (present in this environment) is purpose-built to translate a DESIGN.md into UI instructions. In this project its role is **narrower** than its default description: it is the **normalization + verification layer**, not the primary author. opencode authors, the agent normalizes into our strict grammar.

### Workflow when opencode's brand file arrives

0. **Create a git branch for the brand swap.** Brand swaps are high-visibility changes. If visual regression reveals unexpected diffs, `git checkout main` and debug on the branch before merging. Do not attempt brand swaps on `main` directly.
1. Drop opencode's output at `frontend/design/DESIGN.md`.
2. Run `npm run design:build`. If sections are malformed, the parser fails with line numbers pointing at the problem.
3. If it fails: invoke `design-bridge` agent with the prompt:
   > *"Normalize the current `frontend/design/DESIGN.md` into the strict table format described in `frontend/design/schema.md`. Preserve all semantic values. Do not invent new tokens."*
4. Re-run `npm run design:build`. Review the `tokens.generated.css` diff as a sanity check.
5. Run `npm run test:e2e -- visual/design-tokens.spec.ts`. Expect diffs on every captured page.
6. Review screenshots manually. If unexpected (layout breakage, illegible text, collapsed elements), stop and debug. If expected, update baselines with `playwright test --update-snapshots`.
7. Commit: `DESIGN.md` + generated files + updated Playwright baselines in a single commit with a clear message.

All eight steps (0–7) live in `docs/design/design-bridge-workflow.md`.

## 11. Documentation surfaces

| File                                      | Purpose                                                                                          |
|-------------------------------------------|--------------------------------------------------------------------------------------------------|
| `frontend/design/DESIGN.md`               | Source of truth. Placeholder = Obsidian Neural written in strict table format.                  |
| `frontend/design/README.md`               | Pipeline overview, brand swap local procedure, rarity-animation carve-out callout.               |
| `frontend/design/schema.md`               | Strict-mode grammar: required section names, expected column headers, validation rules.         |
| `docs/design/design-bridge-workflow.md`   | The brand-swap handoff procedure in §10 (steps 0–7, including rollback).                         |
| `CLAUDE.md`                               | New `## Design System` section: points at `frontend/design/DESIGN.md` and `npm run design:build`. |

The `CLAUDE.md` addition reads approximately:

```markdown
## Design System

Frontend design tokens live in `frontend/design/DESIGN.md` and are compiled
into CSS variables and Tailwind config by `npm run design:build`. After
editing `DESIGN.md`, run the build command or start `npm run dev`. CI
rejects PRs where generated files are stale. See
`docs/design/design-bridge-workflow.md` for brand swap procedure.
```

## 12. Open risk: hardcoded hex audit

The spec covers `tailwind.config.js` and `src/index.css` refactors. What it does **not** cover: hardcoded hex values or inline `rgba(...)` literals embedded directly in `frontend/src/components/**/*.tsx` and `frontend/src/pages/**/*.tsx` — e.g., `style={{ background: '#6366f1' }}`, `shadow-[0_0_15px_#6366f1]`, or literal `rgba(99,102,241,0.4)`. These would not flow through the token pipeline and would keep the old brand after a swap, undermining coherent re-theme.

**Plan.** During implementation planning (writing-plans skill, next step), run a targeted `grep` for hardcoded colors under `frontend/src/components/` and `frontend/src/pages/`, count hits, and size:

- **< 20 hits:** include the fixes in Commit 2 alongside the `index.css` refactor.
- **≥ 20 hits:** carve into a follow-up commit with a tracking task; do not block the token pipeline landing on audit completion.

This is a factual sizing question answered at plan time, not a design decision.

## 13. Migration commit plan

Three commits, in order, landing as a single PR:

### Commit 1 — `feat(frontend): add DESIGN.md token pipeline (no visual change)`

- `frontend/design/DESIGN.md` (Obsidian Neural placeholder, strict table format)
- `frontend/design/build-tokens.mjs`
- `frontend/design/build-tokens.test.mjs`
- `frontend/design/build-tokens.swap.test.mjs`
- `frontend/design/README.md`
- `frontend/design/schema.md`
- `frontend/src/styles/tokens.generated.css` (first generation)
- `frontend/tailwind.tokens.generated.js` (first generation)
- `frontend/tests/visual/design-tokens.spec.ts` + baselines captured against current `main` HEAD **before** the refactor

At this point, `tailwind.config.js` and `src/index.css` are unchanged. The site is visually identical. The parser and swap test are fully operational.

### Commit 2 — `refactor(frontend): consume design tokens in Tailwind + component classes`

- `tailwind.config.js` imports `designTokens` from the generated module.
- `src/index.css` component classes rewritten per §6.3.
- `src/styles/rarity.css` carved out; imported in `index.css` after `tokens.generated.css`.
- `.neural-card-indigo / -rose / -emerald` kept as legacy aliases (mechanism resolved during plan phase per §6.3 note).
- Hardcoded hex cleanup per §12 audit outcome, conditional on count.
- Playwright baselines for pages with primary/danger buttons regenerated and reviewed in the PR description.
- `npm run test:design` passes; visual regression passes on all non-button pages.

### Commit 3 — `ci(frontend): enforce design tokens are not stale + npm scripts`

- `package.json` — `design:build`, `design:check`, `test:design` scripts; `dev` prepends build, `build` prepends check.
- `.github/workflows/design-tokens-stale.yml`.
- `CLAUDE.md` — new Design System section.
- `docs/design/design-bridge-workflow.md`.

## 14. Out of scope / future work

- **v2 prose tolerance layer.** If opencode's brand format repeatedly fails strict parsing, build a normalization pre-pass instead of expecting human intervention every swap.
- **Emphasis tokens.** `accent.primary.emphasis` / `accent.danger.emphasis` for pressed/hover states, if a future brand demands pixel-matching.
- **Dark/light mode split.** Current placeholder is dark-only. Light mode adds a second `:root[data-theme="light"]` block in `tokens.generated.css` and a second DESIGN.md section; deferred.
- **`RARITY.md` spec.** If rarity-tier animations grow beyond legendary/epic/rare, give them their own markdown-driven config. Not needed today.
- **Dynamic runtime theming.** Swapping brands without a rebuild; requires a different architecture and is not a goal.
- **Automated TypeScript types for tokens.** A `tokens.generated.d.ts` with a literal union of token names, so `className="bg-accent-primary"` is type-checked. Nice-to-have in v2.
- **Repo-root symlink.** If opencode or another tool expects `DESIGN.md` at repo root, add a symlink in a follow-up. Not needed now.

## 15. References

- [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) — the repository this work is inspired by.
- `design-bridge` subagent (present in this environment) — normalization/verification agent for DESIGN.md files.
- `CLAUDE.md` — project-wide conventions and working boundaries.
- `frontend/tailwind.config.js`, `frontend/src/index.css` — current state of the identity that becomes the placeholder.
- Memory entries: `reference_awesome_design_md.md`, `project_design_md_workflow.md`.
