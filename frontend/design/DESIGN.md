# Obsidian Neural — DESIGN.md

> **Source of truth** for frontend design tokens. Parsed by `frontend/design/build-tokens.mjs` into `frontend/src/styles/tokens.generated.css` and `frontend/tailwind.tokens.generated.js`. After editing, run `npm run design:build`.

## Visual Theme & Atmosphere

A dark, high-contrast "obsidian neural" aesthetic. Deep `#050505` body, glass-morphism panels (`bg-bg-surface/5 backdrop-blur-xl`), subtle white grid overlay with radial fade, and three accent glows (indigo primary, rose danger, emerald success). Motion is restrained — 300–500ms transitions, scale-95 on active. No heavy drop shadows; elevation is communicated through glow intensity and border brightness rather than shadow depth.

## Color Palette & Roles

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

## Typography Rules

| Role | Family         | Fallback                                                |
|------|----------------|---------------------------------------------------------|
| sans | Inter          | ui-sans-serif, system-ui, sans-serif                    |
| mono | JetBrains Mono | ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas   |

Weights: 400 (body), 600 (emphasis), 700 (heading), 900 (display). Tracking: normal for body, `tracking-widest` for uppercase labels, `tracking-[0.2em]` for small uppercase buttons.

## Component Stylings

- **Glass panels** (`.glass-panel`, `.neural-card`): translucent white surface (5% alpha), subtle white border (10% alpha), `rounded-card` (1rem), `shadow-card`, backdrop blur.
- **Accent cards** (`.neural-card-accent[data-accent="..."]`): base is a glass panel; on hover, border brightens to `accent-{role}/30` and a `shadow-glow-{role}` appears.
- **Buttons** (`.neural-button-*`): base is 6px rounded, bold uppercase, `active:scale-95`. Primary fills with `accent.primary`; danger uses `accent.danger/20` bg + border.
- **Inputs** (`.neural-input`): `bg-black/40`, `border-border-subtle/10`, `rounded-xl`, focus ring in `accent.primary/50`.

## Layout Principles

Generous whitespace (6–8 units between major sections), 2xl rounded containers, single-column at mobile, 2–3 column grids at desktop. Dashboard cards stack on mobile; arena grids collapse to carousels. Max content width 1440px with auto-margin. Sidebar is fixed 240px on desktop, drawer on mobile.

## Depth & Elevation

| Role                | Value                                |
|---------------------|--------------------------------------|
| radius.card         | 1rem                                 |
| shadow.card         | 0 25px 50px -12px rgba(0,0,0,0.25)   |
| shadow.glow.primary | 0 0 20px rgba(99,102,241,0.15)       |
| shadow.glow.danger  | 0 0 20px rgba(244,63,94,0.15)        |
| shadow.glow.warning | 0 0 20px rgba(245,158,11,0.15)       |
| shadow.glow.success | 0 0 20px rgba(16,185,129,0.15)       |

Elevation hierarchy: flat body → glass cards (`shadow-card`) → hovered accent cards (adds `shadow-glow-*`). Legendary/epic rarity tiers have stronger glow animations but are intentionally NOT driven by this file — see `frontend/src/styles/rarity.css`.

## Do's and Don'ts

- **Do** use semantic token names (`bg-accent-primary`, `text-text-muted`) in new code.
- **Do** keep the legacy aliases (`bg-obsidian`, `bg-indigo-glow`) working — they map through the same CSS variables.
- **Don't** hardcode hex values or `rgba(...)` literals in TSX files for brand-coupled surfaces. Use the tokens.
- **Don't** modify `rarity.css` in response to a brand swap — legendary/epic are gameplay signals, not brand colors.
- **Don't** add new colors without also adding a semantic role here first.

## Responsive Behavior

- `sm` (≥640px): 2-column grids where appropriate, larger padding.
- `md` (≥768px): sidebar visible, 3-column grids.
- `lg` (≥1024px): dashboard expands to full grid, arena tournament brackets become side-by-side.
- `xl` (≥1280px): max content width kicks in.
- Motion is reduced at `prefers-reduced-motion: reduce`.

## Agent Prompt Guide

When asked to build a new page in this project:
1. Use `.neural-card` or `.glass-panel` as the default container.
2. Use `bg-accent-primary` for primary CTAs, `bg-accent-danger/20` for destructive ones.
3. Gradient text should use `from-accent-primary via-chart-5 to-accent-danger`.
4. Never inline `style={{ background: '#...' }}` — go through Tailwind tokens.
5. For charts, rotate through `chart.1` → `chart.5` for series colors.
6. Respect the rarity-tier carve-out — do not touch `rarity.css` when re-theming.
