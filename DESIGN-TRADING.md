# Trading Dashboard Design System

## 1. Visual Theme & Atmosphere

A professional, data-dense trading interface that balances real-time market data with clear action signals. The design prioritizes readability during extended trading sessions with a dark-first approach, using emerald green for gains and crimson red for losses as universal trading conventions. Purple accents convey premium fintech quality while maintaining trust.

**Key Characteristics:**
- Dark background (#0d1117) reduces eye strain during long sessions
- Emerald green (#10b981) for gains, Crimson red (#ef4444) for losses
- Purple accent (#8b5cf6) for premium fintech feel
- Monospace fonts for prices and numbers (JetBrains Mono)
- High contrast for critical data (4.5:1 minimum)
- Real-time update animations (pulse, flash)

## 2. Color Palette & Roles

### Primary
- **Background Dark** (#0d1117): Main background
- **Surface Dark** (#161b22): Card/panel backgrounds
- **Border Dark** (#30363d): Subtle borders

### Trading Colors
- **Gain Green** (#10b981): Positive price changes, profits
- **Loss Red** (#ef4444): Negative price changes, losses
- **Neutral Gray** (#6b7280): Unchanged, pending states

### Accent
- **Purple Primary** (#8b5cf6): CTAs, primary actions
- **Purple Hover** (#a78bfa): Button hover state
- **Purple Light** (#c4b5fd): Subtle highlights

### Text
- **Text Primary** (#f0f6fc): Headlines, important data
- **Text Secondary** (#8b949e): Labels, metadata
- **Text Muted** (#6e7681): Placeholder, disabled

### Status
- **Success** (#10b981): Buy signals, positive alerts
- **Warning** (#f59e0b): Caution, medium confidence
- **Error** (#ef4444): Sell signals, critical alerts
- **Info** (#3b82f6): Informational, neutral alerts

## 3. Typography Rules

### Font Families
- **Display**: Inter - Headlines, hero sections
- **Body**: Inter - UI text, descriptions
- **Monospace**: JetBrains Mono - Prices, numbers, code

### Hierarchy

| Role | Font | Size | Weight | Line Height | Notes |
|------|------|------|--------|-------------|-------|
| Display Hero | Inter | 36px | 700 | 1.2 | Page titles |
| Display Secondary | Inter | 24px | 600 | 1.3 | Section headers |
| Heading | Inter | 20px | 600 | 1.4 | Card titles |
| Body | Inter | 14px | 400 | 1.5 | Standard text |
| Body Small | Inter | 12px | 400 | 1.5 | Labels, metadata |
| Price Large | JetBrains Mono | 24px | 600 | 1.2 | Current prices |
| Price Medium | JetBrains Mono | 16px | 500 | 1.3 | Historical prices |
| Price Small | JetBrains Mono | 12px | 400 | 1.4 | Price changes |
| Code | JetBrains Mono | 13px | 400 | 1.5 | Code snippets |

## 4. Component Stylings

### Buttons

**Primary CTA (Buy/Sell)**
- Background: #8b5cf6 (purple)
- Text: #ffffff (white)
- Radius: 8px
- Padding: 12px 24px
- Font: Inter 14px 600
- Hover: #a78bfa (lighter purple)
- Active: #7c3aed (darker purple)
- Disabled: #30363d (gray)

**Buy Button**
- Background: #10b981 (green)
- Hover: #34d399

**Sell Button**
- Background: #ef4444 (red)
- Hover: #f87171

**Secondary**
- Background: transparent
- Border: 1px solid #30363d
- Text: #f0f6fc
- Hover: #30363d background

### Cards & Panels

**Dashboard Card**
- Background: #161b22
- Border: 1px solid #30363d
- Radius: 12px
- Padding: 20px
- Shadow: 0 4px 6px rgba(0, 0, 0, 0.3)

**Price Card**
- Background: #161b22
- Border: 1px solid #30363d
- Radius: 8px
- Padding: 16px
- Contains: Symbol, Price, Change%, Sparkline

**Alert Card**
- Left border: 4px colored (green/red/yellow/blue)
- Background: #161b22
- Radius: 8px
- Padding: 12px 16px

### Tables

**Data Table**
- Header background: #21262d
- Row background: #161b22
- Row hover: #1c2128
- Border: 1px solid #30363d
- Cell padding: 12px 16px
- Font: Inter 13px

**Price Table**
- Monospace font for numbers (JetBrains Mono)
- Right-aligned numeric columns
- Color-coded changes (green/red)

### Navigation

**Sidebar**
- Width: 240px
- Background: #0d1117
- Border-right: 1px solid #30363d
- Item height: 40px
- Active indicator: Left border (purple)

**Top Navigation**
- Height: 56px
- Background: #161b22
- Border-bottom: 1px solid #30363d

### Forms

**Input Fields**
- Background: #0d1117
- Border: 1px solid #30363d
- Radius: 6px
- Padding: 10px 12px
- Focus: Border color #8b5cf6
- Error: Border color #ef4444

**Select Dropdown**
- Same as input
- Dropdown background: #161b22
- Option hover: #21262d

## 5. Layout Principles

### Spacing System
- Base: 4px
- Scale: 4px, 8px, 12px, 16px, 20px, 24px, 32px, 40px, 48px, 64px

### Grid System
- 12-column grid
- Max width: 1440px
- Gutter: 24px
- Margin: 24px

### Border Radius Scale
- Small (4px): Inputs, tags
- Medium (6px): Buttons, small cards
- Large (8px): Cards, modals
- XL (12px): Dashboard panels
- XXL (16px): Hero sections

## 6. Depth & Elevation

### Shadow System
- **Level 1**: 0 1px 2px rgba(0, 0, 0, 0.3) - Subtle cards
- **Level 2**: 0 4px 6px rgba(0, 0, 0, 0.4) - Elevated cards
- **Level 3**: 0 10px 15px rgba(0, 0, 0, 0.5) - Modals, dropdowns
- **Level 4**: 0 20px 25px rgba(0, 0, 0, 0.6) - Overlays

### Surface Hierarchy
- Background: #0d1117 (lowest)
- Surface: #161b22 (cards, panels)
- Elevated: #21262d (dropdowns, popovers)
- Overlay: rgba(0, 0, 0, 0.7) (modals)

## 7. Do's and Don'ts

### Do
- Use monospace fonts for all price/number displays
- Apply green (#10b981) for gains, red (#ef4444) for losses
- Maintain high contrast (4.5:1) for critical data
- Use consistent spacing (4px base unit)
- Animate real-time updates (pulse, flash)
- Provide clear visual hierarchy

### Don't
- Don't use green/red for non-trading contexts
- Don't mix monospace and sans-serif for numbers
- Don't use low contrast for price data
- Don't overcrowd dashboards - use whitespace
- Don't animate excessively - respect prefers-reduced-motion
- Don't use decorative gradients on data displays

## 8. Responsive Behavior

### Breakpoints
- Mobile: 320px - 640px
- Tablet: 641px - 1024px
- Desktop: 1025px - 1440px
- Large: 1441px+

### Mobile Strategy
- Single column layout
- Collapsible navigation (hamburger)
- Simplified data cards
- Touch targets: 44px minimum
- Bottom sheet for actions

### Tablet Strategy
- 2-column grid
- Collapsible sidebar
- Balanced data density

### Desktop Strategy
- Full 12-column grid
- Persistent sidebar
- Maximum data density
- Multi-panel layouts

## 9. Agent Prompt Guide

### Quick Color Reference
- Background: #0d1117
- Surface: #161b22
- Gain: #10b981
- Loss: #ef4444
- Accent: #8b5cf6
- Text: #f0f6fc

### Example Component Prompts
- "Create price card: dark surface (#161b22), JetBrains Mono 24px for price, green/red for change%, 8px radius."
- "Build buy button: green (#10b981) background, white text, 8px radius, hover #34d399."
- "Design alert card: left border colored by severity, dark surface, Inter 13px body text."
- "Create data table: dark rows (#161b22), header (#21262d), monospace numbers, right-aligned."
