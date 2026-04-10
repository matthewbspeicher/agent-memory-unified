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
