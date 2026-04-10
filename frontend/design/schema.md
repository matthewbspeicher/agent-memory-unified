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
