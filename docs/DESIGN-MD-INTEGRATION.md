# DESIGN.md Integration Guide

## Overview

The [awesome-design-md](https://github.com/VoltAgent/awesome-design-md) repository provides 62+ DESIGN.md files - markdown-based design systems that AI coding agents can read to generate consistent UI.

## What We Created

### 1. Trading Dashboard Design System
- **File**: `DESIGN-TRADING.md`
- **Purpose**: Custom design system for our investment dashboard
- **Combines patterns from**: Kraken (data-dense), Coinbase (trust), Sentry (alerts), Linear (minimal)

### 2. Coinbase Design System (Reference)
- **File**: `DESIGN.md`
- **Purpose**: Reference for clean, institutional fintech design
- **Key patterns**: 56px pill buttons, blue accent, alternating dark/light sections

## How to Use DESIGN.md

### For AI-Assisted Development

1. **Copy DESIGN.md to project root** (already done)
2. **Reference it when prompting AI agents**:

```
"Build a price ticker component using the DESIGN.md specifications.
Use JetBrains Mono for prices, green (#10b981) for gains, red (#ef4444) for losses."
```

3. **AI agents will generate UI that matches the design system**

### Integration with Our React Frontend

#### Option 1: CSS Variables (Recommended)
Convert DESIGN.md tokens to CSS custom properties:

```css
:root {
  /* Colors */
  --color-bg-dark: #0d1117;
  --color-surface-dark: #161b22;
  --color-gain: #10b981;
  --color-loss: #ef4444;
  --color-accent: #8b5cf6;
  
  /* Typography */
  --font-display: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  
  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  
  /* Shadows */
  --shadow-card: 0 4px 6px rgba(0, 0, 0, 0.3);
}
```

#### Option 2: Tailwind CSS Config
Extend Tailwind with DESIGN.md tokens:

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        'trading-bg': '#0d1117',
        'trading-surface': '#161b22',
        'gain': '#10b981',
        'loss': '#ef4444',
        'accent': '#8b5cf6',
      },
      fontFamily: {
        'display': ['Inter', 'sans-serif'],
        'mono': ['JetBrains Mono', 'monospace'],
      },
    },
  },
}
```

#### Option 3: Styled Components / Emotion
Create a theme object:

```javascript
const tradingTheme = {
  colors: {
    background: '#0d1117',
    surface: '#161b22',
    gain: '#10b981',
    loss: '#ef4444',
    accent: '#8b5cf6',
  },
  fonts: {
    display: 'Inter',
    mono: 'JetBrains Mono',
  },
  // ... more tokens
};
```

## Component Examples Using DESIGN.md

### Price Card Component

```jsx
// Using DESIGN.md specifications
const PriceCard = ({ symbol, price, change }) => (
  <div className="bg-trading-surface border border-gray-700 rounded-lg p-4">
    <h3 className="font-display text-lg font-semibold">{symbol}</h3>
    <p className="font-mono text-2xl font-semibold">
      ${price.toLocaleString()}
    </p>
    <p className={`font-mono text-sm ${change >= 0 ? 'text-gain' : 'text-loss'}`}>
      {change >= 0 ? '+' : ''}{change.toFixed(2)}%
    </p>
  </div>
);
```

### Buy/Sell Buttons

```jsx
const TradeButtons = () => (
  <div className="flex gap-4">
    <button className="bg-gain hover:bg-green-400 text-white font-semibold py-3 px-6 rounded-lg">
      Buy
    </button>
    <button className="bg-loss hover:bg-red-400 text-white font-semibold py-3 px-6 rounded-lg">
      Sell
    </button>
  </div>
);
```

## Available Design Systems

### For Trading Interfaces
| System | Best For | Access |
|--------|----------|--------|
| **Kraken** | Crypto trading, data-dense | `npx getdesign@latest add kraken` |
| **Coinbase** | Institutional, trust | `npx getdesign@latest add coinbase` |
| **Binance** | High-frequency trading | `npx getdesign@latest add binance` |
| **Stripe** | Payment/fintech | `npx getdesign@latest add stripe` |

### For Analytics Dashboards
| System | Best For | Access |
|--------|----------|--------|
| **Sentry** | Error monitoring, alerts | `npx getdesign@latest add sentry` |
| **PostHog** | Product analytics | `npx getdesign@latest add posthog` |
| **Linear** | Minimal, precise | `npx getdesign@latest add linear` |

## Next Steps

### Immediate Actions
1. ✅ Created `DESIGN-TRADING.md` with trading-specific patterns
2. ✅ Downloaded `DESIGN.md` (Coinbase) for reference
3. ⏳ Convert tokens to CSS variables in frontend
4. ⏳ Update React components to use design system

### Future Enhancements
1. Create preview.html visual catalog
2. Add dark/light theme toggle
3. Document animation patterns for real-time updates
4. Create component library with Storybook
5. Add accessibility audit checklist

## Resources

- **awesome-design-md**: https://github.com/VoltAgent/awesome-design-md
- **getdesign.md**: https://getdesign.md (browse all design systems)
- **Stitch DESIGN.md format**: https://stitch.withgoogle.com/docs/design-md/format/
