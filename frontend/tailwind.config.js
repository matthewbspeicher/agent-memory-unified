import { designTokens } from './tailwind.tokens.generated.js';

/**
 * Tailwind config — Obsidian Neural + Trading Terminal (dual identity).
 *
 * Design tokens are generated from frontend/design/DESIGN.md via
 * `node frontend/design/build-tokens.mjs`. Do not edit generated values.
 *
 * Legacy aliases (for backward compatibility with pre-token code):
 *   obsidian     → bg-base
 *   indigo-glow  → accent-primary
 *   rose-glow    → accent-danger
 *   emerald-glow → accent-success
 *
 * Trading Terminal colors (GitHub-dark style) override generated tokens
 * for text-primary/secondary/muted and add trading-* namespace.
 *
 * @see frontend/design/README.md for brand swap procedure
 */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
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
      animation: {
        'pulse-gain': 'pulse-gain 1s ease-in-out',
        'pulse-loss': 'pulse-loss 1s ease-in-out',
        'flash': 'flash 0.5s ease-out',
      },
      keyframes: {
        'pulse-gain': {
          '0%, 100%': { backgroundColor: 'rgba(16, 185, 129, 0)' },
          '50%': { backgroundColor: 'rgba(16, 185, 129, 0.2)' },
        },
        'pulse-loss': {
          '0%, 100%': { backgroundColor: 'rgba(239, 68, 68, 0)' },
          '50%': { backgroundColor: 'rgba(239, 68, 68, 0.2)' },
        },
        'flash': {
          '0%': { opacity: '1' },
          '100%': { opacity: '0.7' },
        },
      },
    },
  },
  plugins: [],
}
