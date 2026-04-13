# DESIGN.md Token Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a build-time DESIGN.md → CSS variables + Tailwind tokens pipeline for `frontend/`, with an Obsidian Neural placeholder, so that when opencode's canonical brand DESIGN.md lands, a single `npm run design:build` re-themes the project's brand-aware surfaces.

**Architecture:** `frontend/design/DESIGN.md` is the source of truth. A pure-Node parser (`frontend/design/build-tokens.mjs`) reads three machine-readable tables (Color Palette & Roles, Typography Rules, Depth & Elevation) and emits two committed generated files: `frontend/src/styles/tokens.generated.css` (CSS custom properties, including `-rgb` triples for Tailwind opacity modifiers) and `frontend/tailwind.tokens.generated.js` (a `designTokens` object consumed by `tailwind.config.js`). Existing component classes in `src/index.css` (`glass-panel`, `neural-card*`, `neural-button*`, `neural-input`, `neural-text-gradient`) get rewritten to reference the generated tokens via CSS variables. Rarity-tier animations (`legendary-glow`, `epic-pulse`) carve out into `src/styles/rarity.css` as "game theme, not brand theme." Cyan/violet sub-identity pages (Landing, Login, CheckEmail, etc.) are **explicitly out of scope** for this PR — they become a documented follow-up because the audit found 132 call sites, well above the spec's 20-hit threshold for inclusion.

**Tech Stack:** Node 20+ (pure `node:*` modules, no deps), Tailwind 3.4, Vite 6, React 19, Playwright (already in the project), `node:test` for the parser unit tests, GitHub Actions for CI.

**Source spec:** `docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md` (commit `f2c0b47`).

## Deliberate deviations from spec

- **`preview.html` / `preview-dark.html`** (spec §3 layout table) are **not** created in this plan. The awesome-design-md convention uses them as static HTML mockups of the brand applied to a sample layout. For the Obsidian Neural *placeholder*, the entire live frontend already functions as the preview — a static mockup would be duplicative work. These files are deferred until opencode's canonical brand `DESIGN.md` arrives; at that point, the brand-swap procedure can include generating or receiving them. The parser does not read them and their absence has no functional impact.
- **Cyan/violet sub-identity migration** (spec §12 open risk) is carved out per the spec's ≥20-hit follow-up rule; the audit found 132 hits. Task 17 documents the follow-up; no task in this plan migrates those pages.

---

## Pre-Flight: Context the executing engineer needs

This project is a monorepo. Your work is **100% in `frontend/`** (React 19 + Vite + Tailwind). Do not touch `trading/`, `taoshi-vanta/`, or any backend code. Do not modify `CLAUDE.md` until Task 16.

**Audit findings that shape the plan** (already collected on 2026-04-10 during planning; re-verify if time has passed):
- **Legacy card alias call sites (`.neural-card-indigo/rose/emerald`):** 2 sites — `frontend/src/pages/ArenaGym.tsx:61` and `frontend/src/pages/ArenaEscapeRoom.tsx:259`. We migrate both and delete the legacy classes entirely.
- **Legacy Tailwind color aliases (`bg-obsidian`, etc.):** 5 sites in 3 files (`ArenaMatch.tsx`, `ArenaGym.tsx`, `ErrorBoundary.tsx`). We keep the aliases in the generated Tailwind config so these keep working with zero JSX edits.
- **Cyan/violet sub-identity (132 class occurrences across 32 files):** OUT OF SCOPE. Do not attempt to migrate Landing.tsx, Login.tsx, CheckEmail.tsx, Commons.tsx, Webhooks.tsx, MemoryList.tsx, WorkspaceList.tsx. These need their own token vocabulary or a wholesale rewrite when opencode's brand lands. The plan documents this as a follow-up in Task 17.

**Working boundaries (from `CLAUDE.md`):**
- Never use `git add -A` or `git add .` — stage explicit files.
- Never write to `.claude/` paths with Write/Edit tools.
- Never skip hooks (`--no-verify`) unless the user explicitly asks.
- Commit with HEREDOC messages; each commit ends with a `Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>` trailer.

**Baseline verification before starting:**

```bash
cd /opt/agent-memory-unified
git status --short                         # expect: existing uncommitted work; don't disturb it
git log -1 --format='%h %s' -- docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md
# expect: f2c0b47 docs(spec): add DESIGN.md token pipeline adoption spec
```

If the spec commit is missing, stop and ask — something is wrong with the working tree.

All file paths in this plan are relative to the repo root `/opt/agent-memory-unified/` unless otherwise noted.

---

# COMMIT 1 — Infrastructure + placeholder (zero visual change)

At the end of this section, `tailwind.config.js` and `src/index.css` are **unchanged** and the site is visually identical. The parser, tests, generated files, and baselines are in place.

---

### Task 1: Create the placeholder DESIGN.md and the schema reference

**Files:**
- Create: `frontend/design/DESIGN.md`
- Create: `frontend/design/schema.md`

- [x] **Step 1: Create `frontend/design/DESIGN.md`** with the full Obsidian Neural placeholder content

```markdown
# Obsidian Neural — DESIGN.md

> **Source of truth** for frontend design tokens. Parsed by `frontend/design/build-tokens.mjs` into `frontend/src/styles/tokens.generated.css` and `frontend/tailwind.tokens.generated.js`. After editing, run `npm run design:build`.

## 1. Visual Theme & Atmosphere

A dark, high-contrast "obsidian neural" aesthetic. Deep `#050505` body, glass-morphism panels (`bg-bg-surface/5 backdrop-blur-xl`), subtle white grid overlay with radial fade, and three accent glows (indigo primary, rose danger, emerald success). Motion is restrained — 300–500ms transitions, scale-95 on active. No heavy drop shadows; elevation is communicated through glow intensity and border brightness rather than shadow depth.

## 2. Color Palette & Roles

| Role             | Hex     | Notes                                   |
|------------------|---------|-----------------------------------------|
| bg.base          | #050505 | Obsidian body background                |
| bg.surface       | #FFFFFF | White, used with 5% alpha for glass     |
| border.subtle    | #FFFFFF | White, used with 10% alpha              |
| text.primary     | #F3F4F6 | gray-100                                |
| text.secondary   | #9CA3AF | gray-400                                |
| text.muted       | #4B5563 | gray-600                                |
| accent.primary   | #6366F1 | indigo-500                              |
| accent.danger    | #F43F5E | rose-500                                |
| accent.warning   | #F59E0B | amber-500                               |
| accent.success   | #10B981 | emerald-500                             |
| selection.bg     | #6366F1 | used with 30% alpha                     |
| selection.text   | #C7D2FE | indigo-200                              |
| chart.1          | #6366F1 | series 1 — matches accent.primary       |
| chart.2          | #F43F5E | series 2 — matches accent.danger        |
| chart.3          | #10B981 | series 3 — matches accent.success       |
| chart.4          | #F59E0B | series 4 — matches accent.warning       |
| chart.5          | #8B5CF6 | series 5 — violet-500, gradient mid-stop |

## 3. Typography Rules

| Role | Family         | Fallback                                                |
|------|----------------|---------------------------------------------------------|
| sans | Inter          | ui-sans-serif, system-ui, sans-serif                    |
| mono | JetBrains Mono | ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas   |

Weights: 400 (body), 600 (emphasis), 700 (heading), 900 (display). Tracking: normal for body, `tracking-widest` for uppercase labels, `tracking-[0.2em]` for small uppercase buttons.

## 4. Component Stylings

- **Glass panels** (`.glass-panel`, `.neural-card`): translucent white surface (5% alpha), subtle white border (10% alpha), `rounded-card` (1rem), `shadow-card`, backdrop blur.
- **Accent cards** (`.neural-card-accent[data-accent="..."]`): base is a glass panel; on hover, border brightens to `accent-{role}/30` and a `shadow-glow-{role}` appears.
- **Buttons** (`.neural-button-*`): base is 6px rounded, bold uppercase, `active:scale-95`. Primary fills with `accent.primary`; danger uses `accent.danger/20` bg + border.
- **Inputs** (`.neural-input`): `bg-black/40`, `border-border-subtle/10`, `rounded-xl`, focus ring in `accent.primary/50`.

## 5. Layout Principles

Generous whitespace (6–8 units between major sections), 2xl rounded containers, single-column at mobile, 2–3 column grids at desktop. Dashboard cards stack on mobile; arena grids collapse to carousels. Max content width 1440px with auto-margin. Sidebar is fixed 240px on desktop, drawer on mobile.

## 6. Depth & Elevation

| Role                | Value                                |
|---------------------|--------------------------------------|
| radius.card         | 1rem                                 |
| shadow.card         | 0 25px 50px -12px rgba(0,0,0,0.25)   |
| shadow.glow.primary | 0 0 20px rgba(99,102,241,0.15)       |
| shadow.glow.danger  | 0 0 20px rgba(244,63,94,0.15)        |
| shadow.glow.warning | 0 0 20px rgba(245,158,11,0.15)       |
| shadow.glow.success | 0 0 20px rgba(16,185,129,0.15)       |

Elevation hierarchy: flat body → glass cards (`shadow-card`) → hovered accent cards (adds `shadow-glow-*`). Legendary/epic rarity tiers have stronger glow animations but are intentionally NOT driven by this file — see `frontend/src/styles/rarity.css`.

## 7. Do's and Don'ts

- **Do** use semantic token names (`bg-accent-primary`, `text-text-muted`) in new code.
- **Do** keep the legacy aliases (`bg-obsidian`, `bg-indigo-glow`) working — they map through the same CSS variables.
- **Don't** hardcode hex values or `rgba(...)` literals in TSX files for brand-coupled surfaces. Use the tokens.
- **Don't** modify `rarity.css` in response to a brand swap — legendary/epic are gameplay signals, not brand colors.
- **Don't** add new colors without also adding a semantic role here first.

## 8. Responsive Behavior

- `sm` (≥640px): 2-column grids where appropriate, larger padding.
- `md` (≥768px): sidebar visible, 3-column grids.
- `lg` (≥1024px): dashboard expands to full grid, arena tournament brackets become side-by-side.
- `xl` (≥1280px): max content width kicks in.
- Motion is reduced at `prefers-reduced-motion: reduce`.

## 9. Agent Prompt Guide

When asked to build a new page in this project:
1. Use `.neural-card` or `.glass-panel` as the default container.
2. Use `bg-accent-primary` for primary CTAs, `bg-accent-danger/20` for destructive ones.
3. Gradient text should use `from-accent-primary via-chart-5 to-accent-danger`.
4. Never inline `style={{ background: '#...' }}` — go through Tailwind tokens.
5. For charts, rotate through `chart.1` → `chart.5` for series colors.
6. Respect the rarity-tier carve-out — do not touch `rarity.css` when re-theming.
```

- [x] **Step 2: Create `frontend/design/schema.md`** documenting the strict parser grammar

```markdown
# DESIGN.md Parser Schema (strict mode v1)

`build-tokens.mjs` reads three `##` sections from `DESIGN.md` and ignores everything else. All three sections are **required**. All parsing is strict — no silent fallbacks.

## Required sections

The parser matches section headings case-insensitively. These exact names are required:

| Heading                   | Content             |
|---------------------------|---------------------|
| `## Color Palette & Roles`| Colors table (below)|
| `## Typography Rules`     | Typography table    |
| `## Depth & Elevation`    | Elevation table     |

## Section 2 — Color Palette & Roles

The parser reads the **first markdown table** inside this section. Required columns (in order):

| Role | Hex | Notes |
|------|-----|-------|

- **Role** — dot-delimited semantic name matching `/^[a-z][a-z0-9]*(\.[a-z0-9]+)*$/`. Examples: `bg.base`, `accent.primary`, `chart.1`.
- **Hex** — 6-digit hex matching `/^#[0-9A-Fa-f]{6}$/`. Shorthand `#FFF` is rejected.
- **Notes** — free text, not parsed.

Required roles (all 17 must appear):

```
bg.base, bg.surface, border.subtle,
text.primary, text.secondary, text.muted,
accent.primary, accent.danger, accent.warning, accent.success,
selection.bg, selection.text,
chart.1, chart.2, chart.3, chart.4, chart.5
```

## Section 3 — Typography Rules

First markdown table inside this section. Required columns:

| Role | Family | Fallback |
|------|--------|----------|

- **Role** — exactly `sans` or `mono`. Both must appear.
- **Family** — font family name; no quoting in the source.
- **Fallback** — comma-separated fallback stack; parsed verbatim.

## Section 6 — Depth & Elevation

First markdown table inside this section. Required columns:

| Role | Value |
|------|-------|

Required roles:

```
radius.card,
shadow.card,
shadow.glow.primary, shadow.glow.danger, shadow.glow.warning, shadow.glow.success
```

Values are parsed verbatim and emitted as-is into the generated CSS.

## Error messages

All errors include the source line number and a pointer to the failing row:

- `DESIGN.md:<line>: missing required section '<name>'`
- `DESIGN.md:<line>: required section '<name>' has no table`
- `DESIGN.md:<line>: wrong column count in '<section>' (expected N, got M)`
- `DESIGN.md:<line>: bad hex value '<value>' in role '<role>'`
- `DESIGN.md:<line>: unknown role '<role>' in '<section>'`
- `DESIGN.md: missing required role '<role>' in '<section>'`

## Not parsed (prose-only sections)

Sections 1, 4, 5, 7, 8, 9 (Visual Theme, Component Stylings, Layout, Do's/Don'ts, Responsive, Agent Prompt Guide) are ignored by the parser. They exist for humans and for the `design-bridge` agent.
```

- [x] **Step 3: Verify both files were written correctly**

```bash
ls -la frontend/design/DESIGN.md frontend/design/schema.md
wc -l frontend/design/DESIGN.md frontend/design/schema.md
grep -c '^##' frontend/design/DESIGN.md    # expect: 9
```

Expected: both files exist; DESIGN.md has 9 `##` headings.

- [x] **Step 4: Do not commit yet** — commit happens at the end of Task 8 when the full Commit 1 payload is staged together.

---

### Task 2: Build the parser — happy-path color table parsing (TDD)

**Files:**
- Create: `frontend/design/build-tokens.mjs`
- Create: `frontend/design/build-tokens.test.mjs`
- Create: `frontend/design/fixtures/minimal-valid.md`

- [x] **Step 1: Create the minimal-valid fixture** — a DESIGN.md with only the required tables, used by multiple tests

```markdown
# Test Fixture

## Color Palette & Roles

| Role             | Hex     | Notes |
|------------------|---------|-------|
| bg.base          | #000000 | t     |
| bg.surface       | #FFFFFF | t     |
| border.subtle    | #FFFFFF | t     |
| text.primary     | #F3F4F6 | t     |
| text.secondary   | #9CA3AF | t     |
| text.muted       | #4B5563 | t     |
| accent.primary   | #6366F1 | t     |
| accent.danger    | #F43F5E | t     |
| accent.warning   | #F59E0B | t     |
| accent.success   | #10B981 | t     |
| selection.bg     | #6366F1 | t     |
| selection.text   | #C7D2FE | t     |
| chart.1          | #111111 | t     |
| chart.2          | #222222 | t     |
| chart.3          | #333333 | t     |
| chart.4          | #444444 | t     |
| chart.5          | #555555 | t     |

## Typography Rules

| Role | Family         | Fallback                      |
|------|----------------|-------------------------------|
| sans | Inter          | ui-sans-serif, system-ui      |
| mono | JetBrains Mono | ui-monospace, Menlo           |

## Depth & Elevation

| Role                | Value                              |
|---------------------|------------------------------------|
| radius.card         | 1rem                               |
| shadow.card         | 0 25px 50px -12px rgba(0,0,0,0.25) |
| shadow.glow.primary | 0 0 20px rgba(99,102,241,0.15)     |
| shadow.glow.danger  | 0 0 20px rgba(244,63,94,0.15)      |
| shadow.glow.warning | 0 0 20px rgba(245,158,11,0.15)     |
| shadow.glow.success | 0 0 20px rgba(16,185,129,0.15)     |
```

- [x] **Step 2: Write the failing test** — create `frontend/design/build-tokens.test.mjs`

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { parseDesignMd } from './build-tokens.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MINIMAL = resolve(__dirname, 'fixtures/minimal-valid.md');

test('parseDesignMd: happy path — returns the 17 color roles with hex values', async () => {
  const tokens = await parseDesignMd(MINIMAL);
  assert.equal(tokens.colors['bg.base'],        '#000000');
  assert.equal(tokens.colors['bg.surface'],     '#FFFFFF');
  assert.equal(tokens.colors['accent.primary'], '#6366F1');
  assert.equal(tokens.colors['accent.warning'], '#F59E0B');
  assert.equal(tokens.colors['chart.5'],        '#555555');
  assert.equal(Object.keys(tokens.colors).length, 17);
});
```

- [x] **Step 3: Run the test and verify it fails**

```bash
cd frontend && node --test design/build-tokens.test.mjs
```

Expected: FAIL with `Cannot find module './build-tokens.mjs'` or similar.

- [x] **Step 4: Create `frontend/design/build-tokens.mjs`** with the minimal parser to make the happy-path test pass

```js
// frontend/design/build-tokens.mjs
// GENERATED DESCRIPTIONS: see frontend/design/schema.md for the strict grammar.
import { readFile } from 'node:fs/promises';

const REQUIRED_COLOR_ROLES = [
  'bg.base', 'bg.surface', 'border.subtle',
  'text.primary', 'text.secondary', 'text.muted',
  'accent.primary', 'accent.danger', 'accent.warning', 'accent.success',
  'selection.bg', 'selection.text',
  'chart.1', 'chart.2', 'chart.3', 'chart.4', 'chart.5',
];

const HEX_RE = /^#[0-9A-Fa-f]{6}$/;

/**
 * Parse a DESIGN.md file into a structured tokens object.
 * Strict mode: throws on missing sections, bad hex values, missing roles.
 */
export async function parseDesignMd(path) {
  const source = await readFile(path, 'utf8');
  const lines = source.split('\n');

  const colorTable = extractSectionTable(lines, 'Color Palette & Roles', 3, path);
  const colors = {};
  for (const { cells, lineNo } of colorTable) {
    const [role, hex] = cells;
    if (!HEX_RE.test(hex)) {
      throw new Error(`${path}:${lineNo}: bad hex value '${hex}' in role '${role}'`);
    }
    colors[role] = hex;
  }
  for (const role of REQUIRED_COLOR_ROLES) {
    if (!(role in colors)) {
      throw new Error(`${path}: missing required role '${role}' in 'Color Palette & Roles'`);
    }
  }

  return { colors };
}

/**
 * Find a `##` section by heading, then return the rows of the first markdown
 * table inside it. Each row is `{ cells: string[], lineNo: number }`.
 */
function extractSectionTable(lines, headingName, expectedCols, path) {
  const headingRe = new RegExp(`^##\\s+${escapeRe(headingName)}\\s*$`, 'i');
  let inSection = false;
  let sectionLine = -1;
  let inTable = false;
  let headerSeen = false;
  const rows = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNo = i + 1;

    if (headingRe.test(line)) {
      inSection = true;
      sectionLine = lineNo;
      continue;
    }
    if (inSection && /^##\s+/.test(line)) {
      break; // next section — stop
    }
    if (!inSection) continue;

    const isTableRow = /^\|.*\|\s*$/.test(line);
    if (!inTable && isTableRow) {
      inTable = true;
      headerSeen = false;
    }
    if (inTable && !isTableRow) {
      inTable = false;
      continue;
    }
    if (!inTable) continue;

    // Separator row like `|---|---|`
    if (/^\|\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|\s*$/.test(line)) {
      continue;
    }
    const cells = line.slice(1, -1).split('|').map((c) => c.trim());
    if (!headerSeen) {
      headerSeen = true;
      if (cells.length !== expectedCols) {
        throw new Error(
          `${path}:${lineNo}: wrong column count in '${headingName}' header (expected ${expectedCols}, got ${cells.length})`
        );
      }
      continue;
    }
    if (cells.length !== expectedCols) {
      throw new Error(
        `${path}:${lineNo}: wrong column count in '${headingName}' (expected ${expectedCols}, got ${cells.length})`
      );
    }
    rows.push({ cells, lineNo });
  }

  if (sectionLine === -1) {
    throw new Error(`${path}: missing required section '${headingName}'`);
  }
  if (rows.length === 0) {
    throw new Error(`${path}:${sectionLine}: required section '${headingName}' has no table`);
  }
  return rows;
}

function escapeRe(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
```

- [x] **Step 5: Run the test and verify it passes**

```bash
cd frontend && node --test design/build-tokens.test.mjs
```

Expected: PASS (1 test passed).

- [x] **Step 6: Do not commit yet** — Commit 1 is staged at the end of Task 8.

---

### Task 3: Parser — typography and elevation tables (TDD)

**Files:**
- Modify: `frontend/design/build-tokens.mjs`
- Modify: `frontend/design/build-tokens.test.mjs`

- [x] **Step 1: Add failing tests for typography and elevation**

Append to `frontend/design/build-tokens.test.mjs`:

```js
test('parseDesignMd: typography — sans and mono families with fallbacks', async () => {
  const tokens = await parseDesignMd(MINIMAL);
  assert.equal(tokens.typography.sans.family, 'Inter');
  assert.equal(tokens.typography.sans.fallback, 'ui-sans-serif, system-ui');
  assert.equal(tokens.typography.mono.family, 'JetBrains Mono');
  assert.equal(tokens.typography.mono.fallback, 'ui-monospace, Menlo');
});

test('parseDesignMd: elevation — radius, card shadow, 4 glow shadows', async () => {
  const tokens = await parseDesignMd(MINIMAL);
  assert.equal(tokens.elevation['radius.card'],         '1rem');
  assert.equal(tokens.elevation['shadow.card'],         '0 25px 50px -12px rgba(0,0,0,0.25)');
  assert.equal(tokens.elevation['shadow.glow.primary'], '0 0 20px rgba(99,102,241,0.15)');
  assert.equal(tokens.elevation['shadow.glow.danger'],  '0 0 20px rgba(244,63,94,0.15)');
  assert.equal(tokens.elevation['shadow.glow.warning'], '0 0 20px rgba(245,158,11,0.15)');
  assert.equal(tokens.elevation['shadow.glow.success'], '0 0 20px rgba(16,185,129,0.15)');
});
```

- [x] **Step 2: Run the tests and verify the new ones fail**

```bash
cd frontend && node --test design/build-tokens.test.mjs
```

Expected: 1 pass (color) + 2 fails (typography, elevation).

- [x] **Step 3: Implement typography and elevation parsing in `build-tokens.mjs`**

Add to the top-level constants:

```js
const REQUIRED_TYPO_ROLES = ['sans', 'mono'];
const REQUIRED_ELEVATION_ROLES = [
  'radius.card', 'shadow.card',
  'shadow.glow.primary', 'shadow.glow.danger',
  'shadow.glow.warning', 'shadow.glow.success',
];
```

Extend `parseDesignMd` to parse both new sections:

```js
export async function parseDesignMd(path) {
  const source = await readFile(path, 'utf8');
  const lines = source.split('\n');

  // Colors
  const colorTable = extractSectionTable(lines, 'Color Palette & Roles', 3, path);
  const colors = {};
  for (const { cells, lineNo } of colorTable) {
    const [role, hex] = cells;
    if (!HEX_RE.test(hex)) {
      throw new Error(`${path}:${lineNo}: bad hex value '${hex}' in role '${role}'`);
    }
    colors[role] = hex;
  }
  for (const role of REQUIRED_COLOR_ROLES) {
    if (!(role in colors)) {
      throw new Error(`${path}: missing required role '${role}' in 'Color Palette & Roles'`);
    }
  }

  // Typography
  const typoTable = extractSectionTable(lines, 'Typography Rules', 3, path);
  const typography = {};
  for (const { cells, lineNo } of typoTable) {
    const [role, family, fallback] = cells;
    if (!REQUIRED_TYPO_ROLES.includes(role)) {
      throw new Error(`${path}:${lineNo}: unknown role '${role}' in 'Typography Rules'`);
    }
    typography[role] = { family, fallback };
  }
  for (const role of REQUIRED_TYPO_ROLES) {
    if (!(role in typography)) {
      throw new Error(`${path}: missing required role '${role}' in 'Typography Rules'`);
    }
  }

  // Elevation
  const elevTable = extractSectionTable(lines, 'Depth & Elevation', 2, path);
  const elevation = {};
  for (const { cells, lineNo } of elevTable) {
    const [role, value] = cells;
    elevation[role] = value;
  }
  for (const role of REQUIRED_ELEVATION_ROLES) {
    if (!(role in elevation)) {
      throw new Error(`${path}: missing required role '${role}' in 'Depth & Elevation'`);
    }
  }

  return { colors, typography, elevation };
}
```

- [x] **Step 4: Run the tests and verify all three pass**

```bash
cd frontend && node --test design/build-tokens.test.mjs
```

Expected: 3 passes.

---

### Task 4: Parser — error handling (TDD)

**Files:**
- Modify: `frontend/design/build-tokens.test.mjs`
- Create: `frontend/design/fixtures/missing-section.md`
- Create: `frontend/design/fixtures/bad-hex.md`
- Create: `frontend/design/fixtures/wrong-columns.md`

- [x] **Step 1: Create the `missing-section.md` fixture** — copy of minimal-valid.md with the Color Palette section removed (delete the `## Color Palette & Roles` heading and its table rows). Start the file with `# Test` and go straight to `## Typography Rules`.

```markdown
# Test Fixture — missing Color Palette

## Typography Rules

| Role | Family         | Fallback                      |
|------|----------------|-------------------------------|
| sans | Inter          | ui-sans-serif, system-ui      |
| mono | JetBrains Mono | ui-monospace, Menlo           |

## Depth & Elevation

| Role                | Value                              |
|---------------------|------------------------------------|
| radius.card         | 1rem                               |
| shadow.card         | 0 25px 50px -12px rgba(0,0,0,0.25) |
| shadow.glow.primary | 0 0 20px rgba(99,102,241,0.15)     |
| shadow.glow.danger  | 0 0 20px rgba(244,63,94,0.15)      |
| shadow.glow.warning | 0 0 20px rgba(245,158,11,0.15)     |
| shadow.glow.success | 0 0 20px rgba(16,185,129,0.15)     |
```

- [x] **Step 2: Create the `bad-hex.md` fixture** — copy of `minimal-valid.md` but with one color row set to `| accent.primary   | #XYZ    | t     |`.

Use the same file structure as `minimal-valid.md` but replace the `accent.primary` row's hex with `#XYZ`.

- [x] **Step 3: Create the `wrong-columns.md` fixture** — copy of `minimal-valid.md` but delete the `Notes` column from the `## Color Palette & Roles` header and from one data row (leaving 2 columns in the header, 3 in most rows — this will fail on the row that has 3 when the header has 2).

Header becomes:

```markdown
| Role             | Hex     |
|------------------|---------|
| bg.base          | #000000 | t     |
```

- [x] **Step 4: Add failing tests for error cases**

Append to `build-tokens.test.mjs`:

```js
const MISSING  = resolve(__dirname, 'fixtures/missing-section.md');
const BAD_HEX  = resolve(__dirname, 'fixtures/bad-hex.md');
const WRONG_CO = resolve(__dirname, 'fixtures/wrong-columns.md');

test('parseDesignMd: throws on missing required section', async () => {
  await assert.rejects(
    () => parseDesignMd(MISSING),
    /missing required section 'Color Palette & Roles'/
  );
});

test('parseDesignMd: throws on bad hex value with line number', async () => {
  await assert.rejects(
    () => parseDesignMd(BAD_HEX),
    /bad hex value '#XYZ' in role 'accent\.primary'/
  );
});

test('parseDesignMd: throws on wrong column count', async () => {
  await assert.rejects(
    () => parseDesignMd(WRONG_CO),
    /wrong column count/
  );
});
```

- [x] **Step 5: Run the tests and verify they pass**

```bash
cd frontend && node --test design/build-tokens.test.mjs
```

Expected: 6 passes. The error-handling paths in the parser were already implemented in Task 2 (they just had no test coverage); these tests lock in the error message shapes.

---

### Task 5: Generator — tokens.generated.css + tailwind.tokens.generated.js (TDD)

**Files:**
- Modify: `frontend/design/build-tokens.mjs`
- Modify: `frontend/design/build-tokens.test.mjs`

- [x] **Step 1: Add failing tests for the generator functions**

Append to `build-tokens.test.mjs`:

```js
import { generateCss, generateTailwindJs } from './build-tokens.mjs';

test('generateCss: emits :root block with hex and -rgb variants', async () => {
  const tokens = await parseDesignMd(MINIMAL);
  const css = generateCss(tokens);
  assert.match(css, /^\/\* GENERATED/);
  assert.match(css, /:root \{/);
  assert.match(css, /--color-bg-base:\s+#000000;/);
  assert.match(css, /--color-bg-base-rgb:\s+0 0 0;/);
  assert.match(css, /--color-accent-primary:\s+#6366F1;/);
  assert.match(css, /--color-accent-primary-rgb:\s+99 102 241;/);
  assert.match(css, /--color-chart-5-rgb:\s+85 85 85;/);
  assert.match(css, /--font-sans:\s+'Inter', ui-sans-serif, system-ui;/);
  assert.match(css, /--font-mono:\s+'JetBrains Mono', ui-monospace, Menlo;/);
  assert.match(css, /--radius-card:\s+1rem;/);
  assert.match(css, /--shadow-card:\s+0 25px 50px -12px rgba\(0,0,0,0\.25\);/);
  assert.match(css, /--shadow-glow-warning:\s+0 0 20px rgba\(245,158,11,0\.15\);/);
});

test('generateTailwindJs: exports designTokens object with semantic + legacy color names', async () => {
  const tokens = await parseDesignMd(MINIMAL);
  const js = generateTailwindJs(tokens);
  assert.match(js, /^\/\* GENERATED/);
  assert.match(js, /export const designTokens = \{/);
  assert.match(js, /'bg-base':\s+'rgb\(var\(--color-bg-base-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'accent-primary':\s+'rgb\(var\(--color-accent-primary-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'accent-warning':\s+'rgb\(var\(--color-accent-warning-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'chart-5':\s+'rgb\(var\(--color-chart-5-rgb\) \/ <alpha-value>\)'/);
  // Legacy aliases
  assert.match(js, /obsidian:\s+'rgb\(var\(--color-bg-base-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'indigo-glow':\s+'rgb\(var\(--color-accent-primary-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'rose-glow':\s+'rgb\(var\(--color-accent-danger-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /'emerald-glow':\s+'rgb\(var\(--color-accent-success-rgb\) \/ <alpha-value>\)'/);
  assert.match(js, /sans:\s+\['var\(--font-sans\)'\]/);
  assert.match(js, /card:\s+'var\(--radius-card\)'/);
  assert.match(js, /'glow-primary':\s+'var\(--shadow-glow-primary\)'/);
  assert.match(js, /'glow-warning':\s+'var\(--shadow-glow-warning\)'/);
});
```

- [x] **Step 2: Run tests and verify the new ones fail**

```bash
cd frontend && node --test design/build-tokens.test.mjs
```

Expected: 6 passes + 2 fails (`generateCss is not a function`, `generateTailwindJs is not a function`).

- [x] **Step 3: Implement `generateCss` and `generateTailwindJs` in `build-tokens.mjs`**

Add to `build-tokens.mjs`:

```js
const GEN_HEADER = '/* GENERATED — do not edit. Source: frontend/design/DESIGN.md */';

/**
 * Convert a dotted role name like 'accent.primary' to a CSS custom property
 * suffix like 'accent-primary'.
 */
function roleToKebab(role) {
  return role.replace(/\./g, '-');
}

/** '#6366F1' → '99 102 241' (space-separated, for rgb(var(--x) / alpha)) */
function hexToRgbTriple(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r} ${g} ${b}`;
}

export function generateCss(tokens) {
  const lines = [GEN_HEADER, ':root {'];
  for (const [role, hex] of Object.entries(tokens.colors)) {
    const k = roleToKebab(role);
    lines.push(`  --color-${k}: ${hex};`);
    lines.push(`  --color-${k}-rgb: ${hexToRgbTriple(hex)};`);
  }
  lines.push(`  --font-sans: '${tokens.typography.sans.family}', ${tokens.typography.sans.fallback};`);
  lines.push(`  --font-mono: '${tokens.typography.mono.family}', ${tokens.typography.mono.fallback};`);
  for (const [role, value] of Object.entries(tokens.elevation)) {
    const k = roleToKebab(role);
    lines.push(`  --${k}: ${value};`);
  }
  lines.push('}', '');
  return lines.join('\n');
}

const LEGACY_COLOR_ALIASES = {
  'obsidian':     'bg.base',
  'indigo-glow':  'accent.primary',
  'rose-glow':    'accent.danger',
  'emerald-glow': 'accent.success',
};

export function generateTailwindJs(tokens) {
  const lines = [
    GEN_HEADER,
    'export const designTokens = {',
    '  colors: {',
  ];
  for (const role of Object.keys(tokens.colors)) {
    const k = roleToKebab(role);
    lines.push(`    '${k}': 'rgb(var(--color-${k}-rgb) / <alpha-value>)',`);
  }
  for (const [alias, sourceRole] of Object.entries(LEGACY_COLOR_ALIASES)) {
    const k = roleToKebab(sourceRole);
    const key = alias.includes('-') ? `'${alias}'` : alias;
    lines.push(`    ${key}: 'rgb(var(--color-${k}-rgb) / <alpha-value>)',`);
  }
  lines.push('  },');
  lines.push('  fontFamily: {');
  lines.push("    sans: ['var(--font-sans)'],");
  lines.push("    mono: ['var(--font-mono)'],");
  lines.push('  },');
  lines.push('  borderRadius: {');
  lines.push("    card: 'var(--radius-card)',");
  lines.push('  },');
  lines.push('  boxShadow: {');
  lines.push("    card: 'var(--shadow-card)',");
  lines.push("    'glow-primary': 'var(--shadow-glow-primary)',");
  lines.push("    'glow-danger':  'var(--shadow-glow-danger)',");
  lines.push("    'glow-warning': 'var(--shadow-glow-warning)',");
  lines.push("    'glow-success': 'var(--shadow-glow-success)',");
  lines.push('  },');
  lines.push('};', '');
  return lines.join('\n');
}
```

- [x] **Step 4: Run tests and verify all 8 pass**

```bash
cd frontend && node --test design/build-tokens.test.mjs
```

Expected: 8 passes.

---

### Task 6: Parser CLI — `--check` mode and idempotent writes (TDD)

**Files:**
- Modify: `frontend/design/build-tokens.mjs`
- Modify: `frontend/design/build-tokens.test.mjs`

- [x] **Step 1: Add failing tests for `buildTokens` (write mode) and `checkTokens` (dry-run mode)**

Append to `build-tokens.test.mjs`:

```js
import { buildTokens, checkTokens } from './build-tokens.mjs';
import { mkdtemp, rm, writeFile, readFile, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

test('buildTokens: writes both generated files on first run', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dt-'));
  try {
    const cssPath = join(dir, 'tokens.generated.css');
    const jsPath  = join(dir, 'tailwind.tokens.generated.js');
    const result = await buildTokens({
      source: MINIMAL,
      cssOut: cssPath,
      jsOut:  jsPath,
    });
    assert.equal(result.cssWritten, true);
    assert.equal(result.jsWritten,  true);
    const css = await readFile(cssPath, 'utf8');
    const js  = await readFile(jsPath,  'utf8');
    assert.match(css, /--color-accent-primary:\s+#6366F1;/);
    assert.match(js,  /'accent-primary':/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('buildTokens: idempotent — second run with unchanged source performs no writes', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dt-'));
  try {
    const cssPath = join(dir, 'tokens.generated.css');
    const jsPath  = join(dir, 'tailwind.tokens.generated.js');
    await buildTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    const statBefore = await stat(cssPath);
    // Small delay so mtime would differ if a write happened
    await new Promise((r) => setTimeout(r, 20));
    const result = await buildTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    assert.equal(result.cssWritten, false);
    assert.equal(result.jsWritten,  false);
    const statAfter = await stat(cssPath);
    assert.equal(statBefore.mtimeMs, statAfter.mtimeMs);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('checkTokens: returns {ok: true} when generated files match expected output', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dt-'));
  try {
    const cssPath = join(dir, 'tokens.generated.css');
    const jsPath  = join(dir, 'tailwind.tokens.generated.js');
    await buildTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    const result = await checkTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    assert.equal(result.ok, true);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('checkTokens: returns {ok: false, diff} when CSS is stale', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dt-'));
  try {
    const cssPath = join(dir, 'tokens.generated.css');
    const jsPath  = join(dir, 'tailwind.tokens.generated.js');
    await buildTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    await writeFile(cssPath, '/* tampered */\n');
    const result = await checkTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    assert.equal(result.ok, false);
    assert.match(result.reason, /tokens\.generated\.css/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
```

- [x] **Step 2: Run tests and verify the new ones fail**

```bash
cd frontend && node --test design/build-tokens.test.mjs
```

Expected: 8 passes + 4 fails (`buildTokens is not a function`, etc.).

- [x] **Step 3: Implement `buildTokens`, `checkTokens`, and the CLI entry point in `build-tokens.mjs`**

Append to `build-tokens.mjs`:

```js
import { writeFile, readFile as readFileFs } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve as resolvePath } from 'node:path';
import process from 'node:process';

async function readOrNull(path) {
  try {
    return await readFileFs(path, 'utf8');
  } catch (e) {
    if (e.code === 'ENOENT') return null;
    throw e;
  }
}

/**
 * Parse DESIGN.md, generate CSS and JS, write ONLY if contents changed.
 * Returns { cssWritten, jsWritten } reporting whether each file was touched.
 */
export async function buildTokens({ source, cssOut, jsOut }) {
  const tokens = await parseDesignMd(source);
  const cssExpected = generateCss(tokens);
  const jsExpected  = generateTailwindJs(tokens);
  const [cssCurrent, jsCurrent] = await Promise.all([readOrNull(cssOut), readOrNull(jsOut)]);

  let cssWritten = false;
  let jsWritten  = false;
  if (cssCurrent !== cssExpected) {
    await writeFile(cssOut, cssExpected, 'utf8');
    cssWritten = true;
  }
  if (jsCurrent !== jsExpected) {
    await writeFile(jsOut, jsExpected, 'utf8');
    jsWritten = true;
  }
  return { cssWritten, jsWritten };
}

/**
 * Parse DESIGN.md, generate CSS and JS in memory, compare to committed files.
 * Returns { ok: true } when both match, { ok: false, reason } otherwise.
 */
export async function checkTokens({ source, cssOut, jsOut }) {
  const tokens = await parseDesignMd(source);
  const cssExpected = generateCss(tokens);
  const jsExpected  = generateTailwindJs(tokens);
  const [cssCurrent, jsCurrent] = await Promise.all([readOrNull(cssOut), readOrNull(jsOut)]);

  if (cssCurrent === null) return { ok: false, reason: `${cssOut} missing` };
  if (jsCurrent  === null) return { ok: false, reason: `${jsOut} missing` };
  if (cssCurrent !== cssExpected) {
    return { ok: false, reason: `${cssOut} is stale — run: npm run design:build` };
  }
  if (jsCurrent !== jsExpected) {
    return { ok: false, reason: `${jsOut} is stale — run: npm run design:build` };
  }
  return { ok: true };
}

// CLI entry point — run only when invoked directly
const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const here = dirname(fileURLToPath(import.meta.url));
  const frontend = resolvePath(here, '..');
  const paths = {
    source: resolvePath(here, 'DESIGN.md'),
    cssOut: resolvePath(frontend, 'src/styles/tokens.generated.css'),
    jsOut:  resolvePath(frontend, 'tailwind.tokens.generated.js'),
  };
  const isCheck = process.argv.includes('--check');
  try {
    if (isCheck) {
      const result = await checkTokens(paths);
      if (!result.ok) {
        console.error(`design:check failed: ${result.reason}`);
        process.exit(1);
      }
      console.log('design:check ok');
    } else {
      const result = await buildTokens(paths);
      const touched = [
        result.cssWritten ? 'tokens.generated.css' : null,
        result.jsWritten  ? 'tailwind.tokens.generated.js' : null,
      ].filter(Boolean);
      console.log(touched.length ? `design:build wrote ${touched.join(', ')}` : 'design:build no-op');
    }
  } catch (e) {
    console.error(String(e.message ?? e));
    process.exit(1);
  }
}
```

- [x] **Step 4: Run tests and verify all 12 pass**

```bash
cd frontend && node --test design/build-tokens.test.mjs
```

Expected: 12 passes.

- [x] **Step 5: Run the CLI directly against the real placeholder to sanity-check**

```bash
cd frontend && node design/build-tokens.mjs
```

Expected: writes `src/styles/tokens.generated.css` and `tailwind.tokens.generated.js` (first run). Prints `design:build wrote tokens.generated.css, tailwind.tokens.generated.js`.

- [x] **Step 6: Run it a second time — confirm idempotent no-op**

```bash
cd frontend && node design/build-tokens.mjs
```

Expected: `design:build no-op`.

- [x] **Step 7: Run `--check` against the fresh state**

```bash
cd frontend && node design/build-tokens.mjs --check
```

Expected: `design:check ok`, exit 0.

---

### Task 7: Swap integration test + Playwright baselines

**Files:**
- Create: `frontend/design/build-tokens.swap.test.mjs`
- Create: `frontend/design/fixtures/all-red.md`
- Create: `frontend/tests/visual/design-tokens.spec.ts`

- [x] **Step 1: Create the `all-red.md` fixture** — a DESIGN.md where every color role is a distinct red-family hex, so the swap test can verify tokens rotated through the pipeline correctly

Copy the `minimal-valid.md` structure, then set every color row:

```markdown
| bg.base          | #1A0000 | red 1 |
| bg.surface       | #2A0000 | red 2 |
| border.subtle    | #3A0000 | red 3 |
| text.primary     | #4A0000 | red 4 |
| text.secondary   | #5A0000 | red 5 |
| text.muted       | #6A0000 | red 6 |
| accent.primary   | #7A0000 | red 7 |
| accent.danger    | #8A0000 | red 8 |
| accent.warning   | #9A0000 | red 9 |
| accent.success   | #AA0000 | red A |
| selection.bg     | #BA0000 | red B |
| selection.text   | #CA0000 | red C |
| chart.1          | #DA0000 | red D |
| chart.2          | #EA0000 | red E |
| chart.3          | #FA0000 | red F |
| chart.4          | #FB0000 | red G |
| chart.5          | #FC0000 | red H |
```

Keep typography and elevation identical to `minimal-valid.md`.

- [x] **Step 2: Write the swap test**

```js
// frontend/design/build-tokens.swap.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, join } from 'node:path';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { buildTokens } from './build-tokens.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MINIMAL = resolve(__dirname, 'fixtures/minimal-valid.md');
const ALL_RED = resolve(__dirname, 'fixtures/all-red.md');

test('swap: red fixture produces only red hex values; none of minimal survive', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dt-swap-'));
  try {
    const cssPath = join(dir, 'tokens.generated.css');
    const jsPath  = join(dir, 'tailwind.tokens.generated.js');

    // 1. Build with minimal (baseline)
    await buildTokens({ source: MINIMAL, cssOut: cssPath, jsOut: jsPath });
    const cssBefore = await readFile(cssPath, 'utf8');
    // Sanity: minimal's distinctive indigo is present
    assert.match(cssBefore, /#6366F1/);

    // 2. Rebuild with all-red — same paths, overwrites
    await buildTokens({ source: ALL_RED, cssOut: cssPath, jsOut: jsPath });
    const cssAfter = await readFile(cssPath, 'utf8');

    // 3. All red hex values present
    for (const hex of ['#1A0000','#7A0000','#AA0000','#FC0000']) {
      assert.ok(cssAfter.includes(hex), `expected ${hex} in generated CSS`);
    }

    // 4. NONE of the minimal fixture's distinctive colors remain
    assert.equal(cssAfter.includes('#6366F1'), false, 'indigo must be gone');
    assert.equal(cssAfter.includes('#F43F5E'), false, 'rose must be gone');
    assert.equal(cssAfter.includes('#10B981'), false, 'emerald must be gone');

    // 5. Semantic token names are structurally identical — same set of CSS variables
    const varsBefore = [...cssBefore.matchAll(/--color-[a-z0-9-]+(?:-rgb)?:/g)].map((m) => m[0]).sort();
    const varsAfter  = [...cssAfter .matchAll(/--color-[a-z0-9-]+(?:-rgb)?:/g)].map((m) => m[0]).sort();
    assert.deepEqual(varsBefore, varsAfter, 'token name set must be unchanged across swap');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
```

- [x] **Step 3: Run the swap test and verify it passes**

```bash
cd frontend && node --test design/build-tokens.swap.test.mjs
```

Expected: 1 pass.

- [x] **Step 4: Run both test files together to verify the combined suite**

```bash
cd frontend && node --test design/build-tokens.test.mjs design/build-tokens.swap.test.mjs
```

Expected: 13 passes total (12 from build-tokens.test.mjs + 1 from swap).

- [x] **Step 5: Create the Playwright visual baseline spec**

Create `frontend/tests/visual/design-tokens.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

/**
 * Visual regression baselines for the DESIGN.md token pipeline rollout.
 *
 * Commit 1 captures these baselines against the CURRENT (pre-refactor) main.
 * Commit 2 regenerates baselines for pages containing primary/danger buttons
 * (the accepted 1-shade shift documented in
 * docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md §6.5).
 * Future brand swaps regenerate all baselines wholesale and review visually.
 */

const ROUTES = [
  { name: 'dashboard',       path: '/' },
  { name: 'leaderboard',     path: '/leaderboard' },
  { name: 'arena',           path: '/arena' },
  { name: 'bittensor',       path: '/bittensor' },
  { name: 'knowledge-graph', path: '/knowledge-graph' },
];

for (const { name, path } of ROUTES) {
  test(`design-tokens baseline: ${name}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    // Wait a touch longer for glow animations to settle into a stable frame
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot(`${name}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.001,
    });
  });
}
```

- [x] **Step 6: Start the dev server so Playwright can hit it**

```bash
cd frontend && npm run dev &
sleep 5
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000
```

Expected: `200`.

- [x] **Step 7: Capture baselines (first run always fails — it's recording)**

```bash
cd frontend && npx playwright test tests/visual/design-tokens.spec.ts --update-snapshots
```

Expected: 5 baseline PNGs written under `frontend/tests/visual/design-tokens.spec.ts-snapshots/`.

- [x] **Step 8: Run the spec a second time to confirm baselines are stable**

```bash
cd frontend && npx playwright test tests/visual/design-tokens.spec.ts
```

Expected: 5 passes.

- [x] **Step 9: Stop the dev server**

```bash
pkill -f 'vite.*3000' || true
```

---

### Task 8: Create design/README.md and land Commit 1

**Files:**
- Create: `frontend/design/README.md`

- [x] **Step 1: Write `frontend/design/README.md`**

```markdown
# frontend/design

This directory holds the frontend's design token source of truth and the
tooling that compiles it into CSS custom properties + a Tailwind config module.

## Files

| File                      | Purpose                                                     |
|---------------------------|-------------------------------------------------------------|
| `DESIGN.md`               | Canonical source. 9 sections; 3 are machine-readable tables.|
| `schema.md`               | Strict grammar the parser accepts (start here if confused). |
| `build-tokens.mjs`        | Pure-Node parser + generator + CLI.                         |
| `build-tokens.test.mjs`   | Parser unit tests (`node:test`, no deps).                   |
| `build-tokens.swap.test.mjs` | Round-trip brand-swap integration test.                  |
| `fixtures/`               | Test fixtures. `minimal-valid.md` is the reference shape.   |

## Generated outputs (committed, not gitignored)

| Path                                    | What it contains                          |
|-----------------------------------------|-------------------------------------------|
| `../src/styles/tokens.generated.css`    | `:root` CSS custom properties + `-rgb` triples. |
| `../tailwind.tokens.generated.js`       | `designTokens` object imported by `tailwind.config.js`. |

## Commands

```bash
npm run design:build   # regenerate from DESIGN.md (idempotent no-op if unchanged)
npm run design:check   # dry-run; exit 1 on drift. CI uses this.
npm run test:design    # parser unit tests + swap integration test
```

`npm run dev` prepends `design:build` automatically. `npm run build` prepends
`design:check` so deploys never silently regenerate committed files.

## Brand swap procedure

When opencode's canonical brand `DESIGN.md` arrives, follow
`docs/design/design-bridge-workflow.md`. Summary:

1. `git checkout -b swap-brand-<name>` (rollback-friendly).
2. Drop the new file at `frontend/design/DESIGN.md`.
3. `npm run design:build` — parser fails loudly on malformed tables.
4. If parsing fails, invoke the `design-bridge` agent to normalize to strict grammar.
5. Review the `tokens.generated.*` diffs.
6. Run visual regression — expect diffs; review each manually.
7. Update Playwright baselines and commit.

## Rarity animations carve-out

`src/styles/rarity.css` (legendary-glow, epic-pulse) is **game theme, not brand theme**.
It is intentionally NOT driven by `DESIGN.md`. Legendary should always feel gold
and epic should always feel purple regardless of the current brand.
```

- [x] **Step 2: Verify the full set of Commit 1 files is in place**

```bash
cd /opt/agent-memory-unified
ls frontend/design/DESIGN.md frontend/design/schema.md frontend/design/README.md \
   frontend/design/build-tokens.mjs frontend/design/build-tokens.test.mjs \
   frontend/design/build-tokens.swap.test.mjs \
   frontend/design/fixtures/minimal-valid.md frontend/design/fixtures/missing-section.md \
   frontend/design/fixtures/bad-hex.md frontend/design/fixtures/wrong-columns.md \
   frontend/design/fixtures/all-red.md \
   frontend/src/styles/tokens.generated.css \
   frontend/tailwind.tokens.generated.js \
   frontend/tests/visual/design-tokens.spec.ts
find frontend/tests/visual/design-tokens.spec.ts-snapshots -type f
```

Expected: all listed files present; 5 PNG snapshots present.

- [x] **Step 3: Re-run the full parser test suite one more time**

```bash
cd frontend && node --test design/build-tokens.test.mjs design/build-tokens.swap.test.mjs
```

Expected: 13 passes.

- [x] **Step 4: Verify site still renders unchanged** — start dev server, visit `/`, confirm no console errors

```bash
cd frontend && npm run dev &
sleep 5
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000
pkill -f 'vite.*3000' || true
```

Expected: `200`. At this point `tailwind.config.js` and `src/index.css` are still unchanged, so the site is visually identical.

- [x] **Step 5: Stage and commit**

```bash
cd /opt/agent-memory-unified
git add \
  frontend/design/DESIGN.md \
  frontend/design/schema.md \
  frontend/design/README.md \
  frontend/design/build-tokens.mjs \
  frontend/design/build-tokens.test.mjs \
  frontend/design/build-tokens.swap.test.mjs \
  frontend/design/fixtures/minimal-valid.md \
  frontend/design/fixtures/missing-section.md \
  frontend/design/fixtures/bad-hex.md \
  frontend/design/fixtures/wrong-columns.md \
  frontend/design/fixtures/all-red.md \
  frontend/src/styles/tokens.generated.css \
  frontend/tailwind.tokens.generated.js \
  frontend/tests/visual/design-tokens.spec.ts \
  frontend/tests/visual/design-tokens.spec.ts-snapshots

git commit -m "$(cat <<'EOF'
feat(frontend): add DESIGN.md token pipeline (no visual change)

Introduces frontend/design/DESIGN.md as the canonical source of truth for
brand-level design tokens, with a pure-Node parser + generator producing
src/styles/tokens.generated.css (CSS custom properties) and
tailwind.tokens.generated.js (a designTokens module).

Placeholder DESIGN.md captures the current Obsidian Neural identity
verbatim — no visual change at this commit. tailwind.config.js and
index.css remain untouched; Commit 2 wires them in.

Includes 12 parser unit tests, a round-trip swap integration test, and
Playwright visual baselines for 5 representative pages captured on
pre-refactor HEAD for use as zero-diff regression targets in Commit 2.

Spec: docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
git log -1 --format='%h %s'
```

Expected: new commit hash printed; summary shows ~14 files changed.

---

# COMMIT 2 — Consume tokens in Tailwind + component classes (narrow scope)

At the end of this section, `tailwind.config.js` imports the generated module, `src/index.css` component classes reference semantic tokens via CSS variables, rarity animations live in `src/styles/rarity.css`, and the 2 legacy card alias call sites are migrated. The cyan/violet sub-identity pages are deliberately untouched.

---

### Task 9: Update `tailwind.config.js` to consume generated tokens

**Files:**
- Modify: `frontend/tailwind.config.js`

- [x] **Step 1: Read the current file to confirm its exact shape**

```bash
cd /opt/agent-memory-unified && cat frontend/tailwind.config.js
```

Expected: the 22-line config with inline `obsidian`, `indigo-glow`, `rose-glow`, `emerald-glow` color definitions.

- [x] **Step 2: Rewrite `frontend/tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
import { designTokens } from './tailwind.tokens.generated.js';

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
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

- [x] **Step 3: Sanity-check that Tailwind still picks up the config** — start dev server

```bash
cd frontend && npm run dev &
sleep 5
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000
```

Expected: `200`.

- [x] **Step 4: Smoke test utility resolution** — hit one page that uses `bg-obsidian` (ArenaMatch) and one that uses a legacy glow (`bg-indigo-glow` if any)

```bash
curl -s http://localhost:3000/arena | head -50
pkill -f 'vite.*3000' || true
```

Expected: HTML returned without 500s. The `bg-obsidian` class still resolves because the legacy alias is in the generated Tailwind config.

- [x] **Step 5: Do not commit yet** — commit is at Task 13.

---

### Task 10: Carve out rarity animations into `src/styles/rarity.css`

**Files:**
- Create: `frontend/src/styles/rarity.css`
- Modify: `frontend/src/index.css`

- [x] **Step 1: Read the current `src/index.css` to locate the rarity animations**

```bash
cd /opt/agent-memory-unified && cat frontend/src/index.css
```

Look for `@keyframes legendary-glow` and `@keyframes epic-pulse` in the `@layer utilities` block.

- [x] **Step 2: Create `frontend/src/styles/rarity.css`** with the extracted animations

```css
/*
 * Game-side theme — intentionally NOT driven by DESIGN.md.
 * Rarity tiers (legendary / epic / rare) are gameplay signals, not brand colors.
 * Legendary should always feel gold, epic should always feel purple, regardless
 * of which brand DESIGN.md is in effect.
 *
 * If rarity tiers proliferate, consider giving them their own markdown-driven
 * config in a follow-up (see spec §14).
 */

@layer utilities {
  @keyframes legendary-glow {
    0%, 100% {
      box-shadow:
        0 0 20px rgba(251, 191, 36, 0.4),
        0 0 40px rgba(251, 191, 36, 0.2),
        inset 0 0 20px rgba(251, 191, 36, 0.1);
    }
    50% {
      box-shadow:
        0 0 30px rgba(251, 191, 36, 0.6),
        0 0 60px rgba(251, 191, 36, 0.3),
        inset 0 0 30px rgba(251, 191, 36, 0.15);
    }
  }

  .animate-legendary-glow {
    animation: legendary-glow 2s ease-in-out infinite;
  }

  @keyframes epic-pulse {
    0%, 100% {
      box-shadow: 0 0 25px rgba(168, 85, 247, 0.5);
    }
    50% {
      box-shadow: 0 0 35px rgba(168, 85, 247, 0.7);
    }
  }

  .animate-epic-pulse {
    animation: epic-pulse 1.5s ease-in-out infinite;
  }
}
```

- [x] **Step 3: Remove the rarity animations from `src/index.css`** and add the new imports at the top. After the edit, the `@layer utilities` block in `index.css` is gone entirely.

Replace the entire contents of `frontend/src/index.css` with:

```css
@import './styles/tokens.generated.css';
@import './styles/rarity.css';
@tailwind base;
@tailwind components;
@tailwind utilities;

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

    body::before {
        content: "";
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-image:
            linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
        background-size: 40px 40px;
        pointer-events: none;
        z-index: -1;
        -webkit-mask-image: radial-gradient(ellipse at center, black, transparent 80%);
        mask-image: radial-gradient(ellipse at center, black, transparent 80%);
    }
}

@layer components {
    .glass-panel {
        @apply bg-bg-surface/5 backdrop-blur-xl border border-border-subtle/10 rounded-card shadow-card;
    }

    .neural-card {
        @apply bg-bg-surface/5 backdrop-blur-xl border border-border-subtle/10 rounded-card shadow-card p-6 transition-all duration-500 hover:border-border-subtle/20;
    }

    .neural-card-accent {
        @apply bg-bg-surface/5 backdrop-blur-xl border border-border-subtle/10 rounded-card shadow-card p-6 transition-all duration-500;
    }
    .neural-card-accent[data-accent="primary"]:hover { @apply shadow-glow-primary border-accent-primary/30; }
    .neural-card-accent[data-accent="danger"]:hover  { @apply shadow-glow-danger  border-accent-danger/30;  }
    .neural-card-accent[data-accent="warning"]:hover { @apply shadow-glow-warning border-accent-warning/30; }
    .neural-card-accent[data-accent="success"]:hover { @apply shadow-glow-success border-accent-success/30; }

    .neural-text-gradient {
        @apply text-transparent bg-clip-text bg-gradient-to-r from-accent-primary via-chart-5 to-accent-danger;
    }

    .neural-input {
        @apply w-full bg-black/40 border border-border-subtle/10 rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:border-accent-primary/50 focus:ring-1 focus:ring-accent-primary/50 outline-none transition-all duration-300;
    }

    .neural-button {
        @apply px-6 py-2.5 rounded-xl font-bold text-sm transition-all duration-300 active:scale-95 disabled:opacity-50;
    }
    .neural-button-primary   { @apply neural-button bg-accent-primary text-text-primary hover:shadow-glow-primary; }
    .neural-button-secondary { @apply neural-button bg-bg-surface/5 border border-border-subtle/10 text-text-secondary hover:bg-bg-surface/10 hover:text-text-primary; }
    .neural-button-danger    { @apply neural-button bg-accent-danger/20 border border-accent-danger/30 text-accent-danger hover:bg-accent-danger/30; }
}
```

Notes on this edit:
- The old `bg-obsidian` in `body` becomes `bg-bg-base` (semantic), but the alias still exists for any direct `bg-obsidian` usage elsewhere in components.
- The three old `.neural-card-indigo/rose/emerald` classes are **deleted**. Their call sites are migrated in Task 11.
- The old `@layer utilities` block with rarity animations is **gone** — lives in `rarity.css` now.

- [x] **Step 4: Start the dev server and verify no console errors and no build errors**

```bash
cd frontend && npm run dev &
sleep 6
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000
pkill -f 'vite.*3000' || true
```

Expected: `200`. Tailwind should compile with no warnings about unknown classes (`bg-bg-base`, `rounded-card`, `shadow-glow-primary` all resolve through the generated config).

If Tailwind warns "unknown class `bg-bg-base`," the generated config was not picked up — re-run `npm run design:build` from the frontend dir and restart dev server.

---

### Task 11: Migrate the 2 legacy card alias call sites

**Files:**
- Modify: `frontend/src/pages/ArenaGym.tsx`
- Modify: `frontend/src/pages/ArenaEscapeRoom.tsx`

- [x] **Step 1: Read `ArenaGym.tsx:61`** and confirm the exact class usage

```bash
cd /opt/agent-memory-unified && sed -n '58,65p' frontend/src/pages/ArenaGym.tsx
```

Expected output includes: `className="neural-card-indigo group !p-8 transition-all duration-500"`.

- [x] **Step 2: Migrate ArenaGym.tsx**

In `frontend/src/pages/ArenaGym.tsx` line 61, replace:

```tsx
className="neural-card-indigo group !p-8 transition-all duration-500">
```

with:

```tsx
className="neural-card-accent group !p-8 transition-all duration-500" data-accent="primary">
```

- [x] **Step 3: Read `ArenaEscapeRoom.tsx:259`** and confirm the exact class usage

```bash
cd /opt/agent-memory-unified && sed -n '256,262p' frontend/src/pages/ArenaEscapeRoom.tsx
```

Expected output includes: `className="neural-card-indigo group !p-6 cursor-pointer"`.

- [x] **Step 4: Migrate ArenaEscapeRoom.tsx**

In `frontend/src/pages/ArenaEscapeRoom.tsx` line 259, replace:

```tsx
className="neural-card-indigo group !p-6 cursor-pointer"
```

with:

```tsx
className="neural-card-accent group !p-6 cursor-pointer" data-accent="primary"
```

- [x] **Step 5: Confirm no `neural-card-indigo/rose/emerald` usages remain**

```bash
cd /opt/agent-memory-unified
grep -rn 'neural-card-\(indigo\|rose\|emerald\)' frontend/src/ || echo "none remaining"
```

Expected: `none remaining`.

- [x] **Step 6: Sanity-render ArenaGym and ArenaEscapeRoom in dev**

```bash
cd frontend && npm run dev &
sleep 6
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/arena/gym
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/arena/escape-room
pkill -f 'vite.*3000' || true
```

Expected: `200` on both. If either route is parameterized differently, adjust the URL — the goal is a successful render.

---

### Task 12: Run visual regression, accept button-page diffs, update baselines

**Files:**
- Modify: `frontend/tests/visual/design-tokens.spec.ts-snapshots/*.png` (updates for pages containing primary/danger buttons)

- [x] **Step 1: Start the dev server**

```bash
cd frontend && npm run dev &
sleep 6
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000
```

Expected: `200`.

- [x] **Step 2: Run visual regression — expect diffs on button-containing pages**

```bash
cd frontend && npx playwright test tests/visual/design-tokens.spec.ts
```

Expected outcomes by route:
- `dashboard`: likely diff (has primary buttons); might also show body background shift (gradient uses semantic tokens now, should be identical hex values)
- `leaderboard`: 0 diff expected
- `arena`: possible diff (uses neural-card-accent now)
- `bittensor`: likely 0 diff
- `knowledge-graph`: likely 0 diff

Inspect any diffs via Playwright's HTML report:

```bash
cd frontend && npx playwright show-report
```

For each failing page, confirm the only visible change is:
- Button fills 1 shade lighter (indigo-500 vs indigo-600) — this is the accepted §6.5 shift.
- No layout changes, no missing elements, no color regressions elsewhere.

**If you see unexpected changes** (elements missing, colors other than buttons shifted, layout breakage): STOP. Do not update baselines. Debug — something in `index.css` rewrote incorrectly.

- [x] **Step 3: Once diffs are confirmed to only be the accepted button shift, update baselines**

```bash
cd frontend && npx playwright test tests/visual/design-tokens.spec.ts --update-snapshots
```

- [x] **Step 4: Re-run the suite to confirm all 5 pass**

```bash
cd frontend && npx playwright test tests/visual/design-tokens.spec.ts
```

Expected: 5 passes.

- [x] **Step 5: Stop the dev server**

```bash
pkill -f 'vite.*3000' || true
```

---

### Task 13: Land Commit 2

- [x] **Step 1: Re-run the parser + swap tests**

```bash
cd frontend && node --test design/build-tokens.test.mjs design/build-tokens.swap.test.mjs
```

Expected: 13 passes.

- [x] **Step 2: Re-run `design:check`** to confirm generated files still match DESIGN.md

```bash
cd frontend && node design/build-tokens.mjs --check
```

Expected: `design:check ok`.

- [x] **Step 3: Stage and commit**

```bash
cd /opt/agent-memory-unified
git add \
  frontend/tailwind.config.js \
  frontend/src/index.css \
  frontend/src/styles/rarity.css \
  frontend/src/pages/ArenaGym.tsx \
  frontend/src/pages/ArenaEscapeRoom.tsx \
  frontend/tests/visual/design-tokens.spec.ts-snapshots

git commit -m "$(cat <<'EOF'
refactor(frontend): consume design tokens in Tailwind + component classes

Wires tailwind.config.js to import the generated designTokens module,
rewrites src/index.css component classes to reference semantic tokens
(bg-bg-base, bg-accent-primary, shadow-glow-primary, etc.) via CSS
variables, and carves rarity-tier animations into src/styles/rarity.css
as game theme — intentionally not brand-coupled.

Legacy .neural-card-indigo/rose/emerald classes deleted; their 2 call
sites (ArenaGym, ArenaEscapeRoom) migrated to the new data-accent
attribute pattern.

Legacy Tailwind color aliases (bg-obsidian, bg-indigo-glow, etc.) remain
in the generated config to keep existing usages working with zero JSX
churn.

Pages containing primary/danger buttons show a deliberate 1-shade shift
(indigo-500 vs indigo-600); baselines updated per spec §6.5. All other
visual baselines unchanged.

SCOPE NOTE: The cyan/violet sub-identity pages (Landing, Login,
CheckEmail, Commons, Webhooks, MemoryList, WorkspaceList) are NOT
touched in this PR — audit found 132+ call sites using Tailwind
defaults not in the 17-token vocabulary. Tracked as a follow-up in
the plan's Task 17.

Spec: docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
git log -1 --format='%h %s'
```

Expected: new commit hash.

---

# COMMIT 3 — CI enforcement + npm scripts + docs

At the end of this section, CI rejects stale generated files, `npm run dev`/`build` wire in the pipeline, and `CLAUDE.md` + a workflow doc point new contributors at the system.

---

### Task 14: Add npm scripts to `frontend/package.json`

**Files:**
- Modify: `frontend/package.json`

- [x] **Step 1: Read the current scripts block**

```bash
cd /opt/agent-memory-unified && cat frontend/package.json
```

- [x] **Step 2: Replace the `scripts` block** with the expanded set. Only the `scripts` block changes — leave `dependencies` and `devDependencies` alone.

Replace:

```json
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test:e2e": "playwright test",
    "test:e2e:prod": "playwright test tests/e2e/production.spec.ts",
    "test:chaos": "playwright test tests/e2e/chaos.spec.ts"
  },
```

with:

```json
  "scripts": {
    "dev": "npm run design:build && vite",
    "build": "npm run design:check && vite build",
    "preview": "vite preview",
    "design:build": "node design/build-tokens.mjs",
    "design:check": "node design/build-tokens.mjs --check",
    "test:design": "node --test design/build-tokens.test.mjs design/build-tokens.swap.test.mjs",
    "test:e2e": "playwright test",
    "test:e2e:prod": "playwright test tests/e2e/production.spec.ts",
    "test:chaos": "playwright test tests/e2e/chaos.spec.ts"
  },
```

- [x] **Step 3: Verify JSON is valid**

```bash
cd frontend && node -e 'JSON.parse(require("node:fs").readFileSync("package.json", "utf8")); console.log("ok")'
```

Expected: `ok`.

- [x] **Step 4: Smoke test each new script**

```bash
cd frontend && npm run design:build
cd /opt/agent-memory-unified/frontend && npm run design:check
cd /opt/agent-memory-unified/frontend && npm run test:design
```

Expected:
- `design:build` → `design:build no-op`
- `design:check` → `design:check ok`
- `test:design` → 13 passes

- [x] **Step 5: Confirm `npm run dev` still works** (runs design:build automatically)

```bash
cd frontend && npm run dev &
sleep 5
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000
pkill -f 'vite.*3000' || true
```

Expected: `200`.

---

### Task 15: Add the CI staleness workflow

**Files:**
- Create: `.github/workflows/design-tokens-stale.yml`

- [x] **Step 1: Create the workflow file**

```yaml
name: design-tokens-stale

on:
  pull_request:
    paths:
      - 'frontend/design/**'
      - 'frontend/src/styles/tokens.generated.css'
      - 'frontend/tailwind.tokens.generated.js'
      - 'frontend/tailwind.config.js'
      - 'frontend/package.json'

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install frontend deps
        working-directory: frontend
        run: npm ci

      - name: Check design tokens are not stale
        working-directory: frontend
        run: npm run design:check

      - name: Run parser tests
        working-directory: frontend
        run: npm run test:design
```

- [x] **Step 2: Verify the YAML parses**

```bash
cd /opt/agent-memory-unified && python3 -c 'import yaml, sys; yaml.safe_load(open(".github/workflows/design-tokens-stale.yml")); print("ok")'
```

Expected: `ok`. (If `python3` isn't available, use `node -e 'require("js-yaml")'` or simply visually inspect; this is a format sanity check.)

---

### Task 16: Add CLAUDE.md Design System section + docs/design/design-bridge-workflow.md

**Files:**
- Modify: `CLAUDE.md`
- Create: `docs/design/design-bridge-workflow.md`

- [x] **Step 1: Locate a good insertion point in `CLAUDE.md`**

```bash
cd /opt/agent-memory-unified && grep -n '^## ' CLAUDE.md
```

Look for a natural spot. A good choice is right before `## Common Tasks` (the last section).

- [x] **Step 2: Insert the new section in `CLAUDE.md`** immediately before the `## Common Tasks` heading

```markdown
## Design System

Frontend design tokens live in `frontend/design/DESIGN.md` and are compiled
into CSS custom properties (`frontend/src/styles/tokens.generated.css`) and a
Tailwind config module (`frontend/tailwind.tokens.generated.js`) by
`npm run design:build`. After editing `DESIGN.md`, run the build command — or
just start `npm run dev`, which prepends it automatically.

CI (`.github/workflows/design-tokens-stale.yml`) rejects PRs whose generated
files are stale. The legacy Tailwind aliases (`bg-obsidian`, `bg-indigo-glow`,
`bg-rose-glow`, `bg-emerald-glow`) keep working through the generated config.

When a new canonical brand `DESIGN.md` arrives from an external source, follow
`docs/design/design-bridge-workflow.md` for the rollback-safe swap procedure.

Rarity-tier animations (`legendary-glow`, `epic-pulse`) live in
`frontend/src/styles/rarity.css` and are intentionally NOT driven by
`DESIGN.md` — they are gameplay signals, not brand colors.

```

- [x] **Step 3: Create `docs/design/design-bridge-workflow.md`**

```bash
mkdir -p /opt/agent-memory-unified/docs/design
```

Then write `docs/design/design-bridge-workflow.md`:

```markdown
# Brand Swap Workflow

How to safely replace `frontend/design/DESIGN.md` when a new canonical brand
file lands from an external source (e.g. opencode).

## Prerequisites

- The new `DESIGN.md` ideally uses the strict table format documented in
  `frontend/design/schema.md`. If it doesn't, Step 3 normalizes it.
- You have the `design-bridge` agent available in your Claude Code environment.
- Playwright is installed (`cd frontend && npx playwright install --with-deps`
  the first time).

## Procedure

### Step 0 — Branch for safety (required)

Brand swaps are high-visibility changes. Work on a branch so rollback is trivial.

```bash
git checkout -b swap-brand-<brand-name>
```

If anything goes wrong partway through, `git checkout main` and the previous
brand is restored instantly.

### Step 1 — Drop the new file

```bash
cp /path/to/new-design.md frontend/design/DESIGN.md
```

### Step 2 — Build

```bash
cd frontend && npm run design:build
```

**If this fails** (missing required section, bad hex, wrong column count),
the parser prints the source line number and the problem. Proceed to Step 3.

**If this succeeds,** skip to Step 4.

### Step 3 — Normalize via the design-bridge agent

Invoke the `design-bridge` agent with:

> "Normalize the current `frontend/design/DESIGN.md` into the strict table
> format described in `frontend/design/schema.md`. Preserve all semantic values.
> Do not invent new tokens. Do not edit any other file."

The agent rewrites `DESIGN.md` in place. Re-run Step 2. It should now pass.

### Step 4 — Review generated diffs

```bash
git diff frontend/src/styles/tokens.generated.css frontend/tailwind.tokens.generated.js
```

Sanity-check that the hex values and CSS variable names match what you'd expect.

### Step 5 — Run visual regression

```bash
cd frontend && npx playwright test tests/visual/design-tokens.spec.ts
```

Expect diffs on every captured page — that's the point. Open the HTML report:

```bash
cd frontend && npx playwright show-report
```

### Step 6 — Review screenshots manually

Look at each page's before/after. Flag anything that looks like breakage
(illegible text, collapsed elements, missing CTAs, contrast failures) as a
reason to **stop**, `git checkout main`, and debug.

### Step 7 — Update baselines and commit

Once you're happy with the swap:

```bash
cd frontend && npx playwright test tests/visual/design-tokens.spec.ts --update-snapshots

cd /opt/agent-memory-unified
git add frontend/design/DESIGN.md \
        frontend/src/styles/tokens.generated.css \
        frontend/tailwind.tokens.generated.js \
        frontend/tests/visual/design-tokens.spec.ts-snapshots
git commit -m "feat(frontend): swap brand to <brand-name>"
```

Push the branch and open a PR. The CI staleness check will pass because the
generated files match the new DESIGN.md.

## Troubleshooting

- **Parser error on a row that looks fine:** check for trailing spaces or
  smart-quote hex values (e.g., `'#FFFFFF'` with smart quotes). The parser
  expects plain ASCII `#RRGGBB`.
- **Tailwind says "unknown class `bg-bg-base`":** the generated `tailwind.tokens.generated.js`
  didn't regenerate. Run `npm run design:build` and restart the dev server.
- **Visual regression shows unexpected color on a page nobody should have
  touched:** look for hardcoded hex or `rgba()` in that page's TSX. The token
  pipeline can't reach inline style literals. See the hardcoded-hex audit
  follow-up in the spec.
```

- [x] **Step 4: Verify files exist**

```bash
grep -c '^## Design System' CLAUDE.md         # expect: 1
ls docs/design/design-bridge-workflow.md
```

---

### Task 17: Final verification + land Commit 3

- [x] **Step 1: Run the full test suite**

```bash
cd /opt/agent-memory-unified/frontend
npm run test:design
npm run design:check
```

Expected: tests pass, check passes.

- [x] **Step 2: Simulate what CI will do** (the same commands in `.github/workflows/design-tokens-stale.yml`)

```bash
cd /opt/agent-memory-unified/frontend
npm run design:check
npm run test:design
```

Expected: both succeed.

- [x] **Step 3: Do a full local build**

```bash
cd frontend && npm run build
```

Expected: Vite build succeeds. `design:check` runs first (part of the new `build` script), then `vite build`.

- [x] **Step 4: Stage and commit**

```bash
cd /opt/agent-memory-unified
git add \
  frontend/package.json \
  .github/workflows/design-tokens-stale.yml \
  CLAUDE.md \
  docs/design/design-bridge-workflow.md

git commit -m "$(cat <<'EOF'
ci(frontend): enforce design tokens are not stale + npm scripts

Adds npm scripts (design:build, design:check, test:design), wires them
into dev (build prepended) and build (check prepended), and introduces
.github/workflows/design-tokens-stale.yml which runs design:check and
test:design on any PR touching the pipeline's input files.

Also documents the system:
- CLAUDE.md gains a Design System section pointing new contributors
  and future AI agents at frontend/design/DESIGN.md and the build
  command.
- docs/design/design-bridge-workflow.md describes the 8-step (0-7)
  rollback-safe brand-swap procedure used when opencode's canonical
  brand file lands.

Spec: docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
git log --oneline -4
```

Expected: four recent commits visible, ending with the three new ones (`feat(frontend): add DESIGN.md token pipeline`, `refactor(frontend): consume design tokens`, `ci(frontend): enforce design tokens are not stale`) on top of the existing HEAD.

- [x] **Step 5: Push and open a PR** (only if the user explicitly asks you to push)

Do not `git push` without explicit user instruction — per `CLAUDE.md` working boundaries. If the user asks, use:

```bash
git push -u origin HEAD
gh pr create --title "feat(frontend): DESIGN.md token pipeline" --body "$(cat <<'EOF'
## Summary
- Infrastructure for a DESIGN.md-driven token pipeline (Approach B per spec)
- Commit 1: placeholder + parser + tests + baselines (zero visual change)
- Commit 2: Tailwind + index.css refactor + rarity.css carve-out (1-shade shift on buttons)
- Commit 3: npm scripts + CI staleness check + docs

## Out of scope (tracked follow-up)
- Cyan/violet sub-identity pages (Landing, Login, CheckEmail, Commons, Webhooks, MemoryList, WorkspaceList) — 132+ call sites, needs separate token vocabulary or wholesale rewrite when opencode's brand lands

## Test plan
- [x] `npm run test:design` passes (13 tests)
- [x] `npm run design:check` passes
- [x] `npm run build` succeeds end-to-end
- [x] Playwright visual regression — 3 zero-diff, 2 baseline-updated for accepted 1-shade button shift
- [x] Dev server boots and `/`, `/arena`, `/bittensor`, `/leaderboard`, `/knowledge-graph` all render

Spec: docs/superpowers/specs/2026-04-10-awesome-design-md-adoption.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Follow-up — NOT part of this PR

**Cyan/violet sub-identity migration.** The audit on 2026-04-10 found 132 class occurrences of `bg-cyan-X` / `bg-violet-X` / `bg-amber-X` / `bg-slate-X` across 32 files, plus 79 arbitrary `shadow-[…]` values embedding raw `rgba()`, concentrated in Landing, Login, CheckEmail, Commons, Webhooks, MemoryList, and WorkspaceList. These pages form a distinct "Cyberpunk Cyan/Violet" sub-identity that is not covered by the 17-token vocabulary. The spec's §12 threshold rule (≥20 hits → follow-up) applies; this PR deliberately leaves those pages alone.

**Two options for the follow-up work, to decide later:**

- **(A) Expand the token vocabulary.** Add `accent.cyan`, `accent.violet`, and possibly a `surface.slate` role; regenerate tokens; migrate the 32 files to the new semantic classes. Preserves the current cyan/violet look. Requires the placeholder DESIGN.md to grow beyond 17 roles.
- **(B) Unify under the existing palette.** Migrate those pages to use `accent.primary` (indigo in place of cyan), `chart.5` (violet), and `accent.warning` (amber) — accepting visual changes on the auth/marketing surface. Keeps the vocabulary minimal; matches opencode's brand when it lands.

Either way, **defer this decision until opencode's brand arrives**, since the brand might force a particular choice.

---

## Self-Review

### Spec coverage

- §2 Goals — Tasks 1–17 cover all 6 goals. Non-goals respected (no runtime theming, no cyan/violet migration, frontend-only).
- §3 Layout — Tasks 1, 7, 10 create every file in the layout table.
- §4 Placeholder (17 roles) — Task 1.
- §5 Parser contract — Tasks 2–6 implement the happy path, typography, elevation, error handling, generator, CLI with `--check` and idempotency, matching every §5 requirement.
- §6 Token consumption + refactor — Tasks 9, 10, 11 cover tailwind.config.js, index.css, rarity.css, legacy card migration.
- §7 Build pipeline — Task 14.
- §8 CI — Task 15.
- §9 Testing (3 layers) — Tasks 2–6 (unit), Task 7 (swap + Playwright baselines), Task 12 (visual regression verification).
- §10 Agent handoff (with Step 0 rollback) — Task 16 (`docs/design/design-bridge-workflow.md`).
- §11 Documentation surfaces — Tasks 1, 8, 16 cover all 5 surfaces.
- §12 Hardcoded hex audit — completed during planning; result (132 hits ≫ 20) carved into follow-up in Task 17 and documented in Commit 2's message.
- §13 Migration commit plan — Task 8 = Commit 1, Task 13 = Commit 2, Task 17 = Commit 3.
- §14 Out of scope — honored; Task 17 documents the cyan/violet follow-up that the spec anticipated as §12 risk.

### Placeholder scan

- No "TBD", "implement later", or "add appropriate X" phrases.
- Every code step shows the full code it emits.
- Every shell command has an expected output.
- Every file path is absolute or explicitly relative to `/opt/agent-memory-unified/`.

### Type consistency

- `parseDesignMd`, `generateCss`, `generateTailwindJs`, `buildTokens`, `checkTokens` — same names used across Tasks 2, 3, 5, 6, 7.
- `tokens.colors[role] = hex` return shape consistent with `generateCss(tokens)` consumer in Task 5.
- `buildTokens({source, cssOut, jsOut}) → {cssWritten, jsWritten}` consistent across Task 6 (test + impl) and Task 7 (swap test consumer).
- `checkTokens(...) → {ok, reason}` consistent in Task 6.
- Class names in `index.css` (Task 10) use the same semantic tokens (`bg-bg-base`, `accent-primary`, `shadow-glow-primary`) that the generator emits (Task 5) and Tailwind consumes (Task 9).
- The data-attribute migration (Task 11) targets the `.neural-card-accent[data-accent="primary"]` selector defined in Task 10.
