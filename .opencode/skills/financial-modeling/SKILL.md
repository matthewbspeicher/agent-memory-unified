---
name: financial-modeling
description: Build institutional-grade DCF models, Monte Carlo simulations, and scenario-based valuations
version: 1.0.0
author: Anthropic
type: skill
category: finance
tags:
  - dcf
  - valuation
  - monte-carlo
  - sensitivity-analysis
  - financial-modeling
---

# Anthropic Financial Modeling Suite

> **Purpose**: Build production-ready DCF models, Monte Carlo simulations, and scenario-based valuations.

---

## What I Do

Guide Claude through four core financial analysis workflows:

### Discounted Cash Flow (DCF)
- Multiple growth scenarios
- Terminal value (perpetuity growth + exit multiple)
- WACC determination
- Enterprise/equity value outputs

### Sensitivity Analysis
- Multi-variable data tables
- Tornado charts
- Critical value driver identification

### Monte Carlo Simulation
- Thousands of probability scenarios
- Correlation modeling
- Confidence intervals (90%, 95%)
- VaR calculation

### Scenario Planning
- Best/base/worst cases
- Probability-weighted expected values
- Strategic alternative testing

---

## Installation

```bash
# Clone the cookbooks repository
git clone https://github.com/anthropics/claude-cookbooks.git

# Link the financial modeling skill
ln -s ~/claude-cookbooks/skills/custom_skills/creating-financial-models ~/.claude/skills/
```

---

## Usage

```plaintext
Build a DCF model for this SaaS company using the attached financials
Run a Monte Carlo simulation on this acquisition model with 5,000 iterations
Create sensitivity analysis showing impact of growth rate and WACC on valuation
Develop three scenarios for this expansion project with probability weights
```

---

## Model Types Supported

- Corporate valuation (mature, growth, turnaround)
- Project finance (infrastructure, real estate, energy)
- M&A analysis (acquisition, synergies, accretion/dilution)
- LBO models (IRR, MOIC, debt capacity)

---

## Features

- Generates complete Excel workbooks with formulas
- Professional formatting (color-coded inputs/formulas)
- Error checking and validation
- Balance sheet balancing
- Cash flow reconciliation
