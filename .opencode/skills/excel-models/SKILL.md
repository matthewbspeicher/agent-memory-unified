---
name: excel-models
description: Build error-free financial Excel models with formulas, formatting, and validation
version: 1.0.0
author: Tyler Friedel
type: skill
category: office
tags:
  - excel
  - financial-models
  - spreadsheets
  - formulas
  - office
---

# Claude Office Skills - Excel

> **Purpose**: Generate professional Excel financial models with zero errors.

---

## What I Do

Create Excel files with working formulas (not just static data):

### Formula-Based Models
- Complex financial functions (NPV, IRR, XNPV, XIRR)
- Logical operators
- Lookups (VLOOKUP, INDEX/MATCH)
- Array formulas

### Professional Formatting
- Color-coded inputs/formulas (blue for inputs, black for formulas)
- Custom number formats
- Conditional formatting
- Data validation rules

### Financial Model Standards
- Separation of assumptions, calculations, outputs
- Clear labeling and documentation
- Consistent formula structure

### Zero-Error Requirements
- No circular references
- No inconsistent formulas
- No hardcoded numbers in formula cells
- No broken cell references

---

## Installation

```bash
git clone https://github.com/tfriedel/claude-office-skills.git
cd claude-office-skills

# Install dependencies
venv/bin/pip install -r requirements.txt
npm install  # for html2pptx support

# Link skills
ln -s $(pwd)/skills/* ~/.claude/skills/
```

**Prerequisites**: Python 3.9+, Node.js, LibreOffice, Poppler, Pandoc

---

## Usage

```plaintext
Build a three-statement financial model for this company
Create an LBO model with sensitivity table for purchase price and exit multiple
Generate a waterfall chart showing revenue bridge from last year to this year
Build a cap table with dilution analysis for Series A funding
```

---

## Supported Models

- Three-statement models (Income, Balance Sheet, Cash Flow)
- LBO models
- M&A models
- DCF valuations
- Project finance models
- Cap tables
- Waterfall charts
- Sensitivity tables
