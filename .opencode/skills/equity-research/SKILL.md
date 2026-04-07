---
name: equity-research
description: Generate institutional-grade stock analysis reports with valuation, risk assessment, and trading recommendations
version: 1.0.0
author: Quant Sentiment AI
type: skill
category: finance
tags:
  - equity
  - stocks
  - valuation
  - fundamental-analysis
  - risk-assessment
---

# Claude Equity Research

> **Purpose**: Transform Claude into an equity research analyst that generates institutional-grade investment reports.

---

## What I Do

Generate comprehensive investment reports with:

### Fundamental Analysis
- Revenue growth trends
- Profit margin analysis
- Peer group comparisons
- Market position assessment

### Valuation Modeling
- Bull/base/bear scenarios
- Multiple valuation methods (DCF, comparables, precedent transactions)
- 12-month price targets
- Risk-adjusted expected returns

### Risk Assessment
- Position sizing (1-5% based on risk)
- Downside scenario analysis
- Key risk factors with likelihood scoring

### Technical Analysis
- Support/resistance levels
- Moving average analysis
- RSI, MACD indicators
- Entry/exit timing

### Enhanced Intelligence
- Options flow analysis
- Insider transaction monitoring
- Sector positioning

---

## Installation

```bash
/plugin marketplace add quant-sentiment-ai/claude-equity-research
/plugin install claude-equity-research@quant-sentiment-ai
```

**Prerequisites**: Claude Code CLI v2.0.11+, Claude paid subscription

---

## Usage

```plaintext
/trading-ideas AAPL
/trading-ideas NVDA --detailed
```

---

## Output

- Investment thesis with price target
- Bull/base/bear scenarios
- Risk factors with probability weights
- Position sizing recommendations
- Entry/exit points
