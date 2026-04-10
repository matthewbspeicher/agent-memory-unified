# Token Pipeline Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `DESIGN.md` parser to extract design tokens into CSS custom properties and a Tailwind config module, establishing a single source of truth for the frontend's visual identity.

**Architecture:** A pure Node.js script (`build-tokens.mjs`) reads `frontend/design/DESIGN.md`, parses markdown tables for colors, typography, and elevation, and generates `tokens.generated.css` and `tailwind.tokens.generated.js`. Tailwind and `index.css` are updated to consume these generated files.

**Tech Stack:** Node.js (no npm dependencies for the parser), CSS, Tailwind CSS.

---

### Task 1: Source of Truth (`DESIGN.md` & Schema)

**Files:**
- Create: `frontend/design/DESIGN.md`
- Create: `frontend/design/schema.md`

- [ ] **Step 1: Create the strict-mode schema documentation**
Create `frontend/design/schema.md` explaining the required sections (`Color Palette & Roles`, `Typography Rules`, `Depth & Elevation`) and column formats.

- [ ] **Step 2: Create the placeholder `DESIGN.md`**
Create `frontend/design/DESIGN.md` containing the "Obsidian Neural" visual identity in strict markdown tables, exactly as specified in the adoption spec. Include the 17 color roles, typography, and elevation shadows.

- [ ] **Step 3: Commit**
```bash
git add frontend/design/DESIGN.md frontend/design/schema.md
git commit -m "feat(design): add initial DESIGN.md and schema"
```

---

### Task 2: The Parser Script (`build-tokens.mjs`)

**Files:**
- Create: `frontend/design/build-tokens.mjs`

- [ ] **Step 1: Write the minimal CLI and file reading logic**
Implement argument parsing (`--check`, `--verbose`) and read `DESIGN.md` using `fs.readFileSync`.

- [ ] **Step 2: Implement the Markdown Table Parser**
Write the state machine to track `##` headings and extract rows from the first table in the required sections. Validate hex values (`/^#[0-9A-Fa-f]{6}$/`) and column counts. Throw clear errors on failure.

- [ ] **Step 3: Implement Code Generation**
Generate the CSS (`:root { ... }`) with hex values and RGB triples.
Generate the JS (`export const designTokens = { ... }`).
Add the header: `/* GENERATED — do not edit. Source: frontend/design/DESIGN.md */`.

- [ ] **Step 4: Implement Idempotency and `--check` mode**
Before writing, compare generated strings to existing file contents on disk. If `--check` is active, exit 1 on mismatch and print diff; otherwise write only if changed.

- [ ] **Step 5: Commit**
```bash
git add frontend/design/build-tokens.mjs
git commit -m "feat(design): implement build-tokens.mjs parser and generator"
```

---

### Task 3: Parser Tests

**Files:**
- Create: `frontend/design/build-tokens.test.mjs`
- Create: `frontend/design/build-tokens.swap.test.mjs`

- [ ] **Step 1: Write unit tests (`build-tokens.test.mjs`)**
Use `node:test`. Test happy path parsing, missing required section (throws), bad hex value (throws), and wrong column count (throws).

- [ ] **Step 2: Write integration swap test (`build-tokens.swap.test.mjs`)**
Test an end-to-end brand swap by creating a temporary "all red" `DESIGN.md`, running the parser, and asserting the output CSS contains the new red hex values and none of the placeholder values.

- [ ] **Step 3: Run tests to verify**
Run `node --test frontend/design/build-tokens.test.mjs frontend/design/build-tokens.swap.test.mjs`. Ensure PASS.

- [ ] **Step 4: Commit**
```bash
git add frontend/design/build-tokens.test.mjs frontend/design/build-tokens.swap.test.mjs
git commit -m "test(design): add parser unit and swap integration tests"
```

---

### Task 4: Tailwind & CSS Integration

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/index.css`
- Create: `frontend/src/styles/rarity.css`
- Modify: `frontend/package.json`

- [ ] **Step 1: Run the parser to generate initial tokens**
Run `node frontend/design/build-tokens.mjs` to create `tokens.generated.css` and `tailwind.tokens.generated.js`.

- [ ] **Step 2: Update `tailwind.config.js`**
Import `designTokens` from `./tailwind.tokens.generated.js` and extend `colors`, `fontFamily`, `borderRadius`, and `boxShadow`.

- [ ] **Step 3: Refactor `src/index.css`**
Import `./styles/tokens.generated.css` at the top. Carve out game-specific keyframes into `./styles/rarity.css` and import it. Rewrite base body styles and `.glass-panel`, `.neural-card`, `.neural-button` classes to use the new CSS variables (e.g., `bg-bg-base`, `text-text-primary`, `border-border-subtle`). Use the duplicated hover rules strategy (Option A) for legacy classes to avoid JSX churn.

- [ ] **Step 4: Update `package.json` scripts**
Add `"design:build": "node design/build-tokens.mjs"`, `"design:check": "node design/build-tokens.mjs --check"`, and `"test:design": "node --test design/build-tokens.test.mjs design/build-tokens.swap.test.mjs"`. Update `dev` to prepend `npm run design:build &&` and `build` to prepend `npm run design:check &&`.

- [ ] **Step 5: Verify build and Commit**
Run `cd frontend && npm run build` to ensure Tailwind compiles successfully.
```bash
git add frontend/
git commit -m "refactor(frontend): integrate design tokens into Tailwind and index.css"
```