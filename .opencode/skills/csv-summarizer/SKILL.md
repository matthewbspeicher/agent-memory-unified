---
name: csv-summarizer
description: Automatically analyze CSV files and produce analytical insights and visualizations
version: 1.0.0
author: Coffee Fuel Bump
type: skill
category: data-science
tags:
  - csv
  - data-exploration
  - visualization
  - patterns
---

# CSV Data Summarizer

> **Purpose**: Quick exploratory analysis of financial datasets in CSV format.

---

## What I Do

Automatically examine CSV files and produce analytical insights:

### Intelligent Detection
- Data type identification (sales, customer, financial, time series)
- Pattern recognition (transaction data, price series, holdings)
- Adaptive analysis based on data type

### Comprehensive Analytics
- Descriptive statistics (mean, median, std dev, quartiles)
- Correlation analysis
- Distribution patterns (skewness, kurtosis)
- Trend identification

### Visual Output
- Time-series plots
- Correlation heatmaps
- Distribution histograms
- Categorical breakdowns

### Data Assessment
- Missing data identification
- Outlier detection
- Consistency validation
- Quality reporting

---

## Installation

```bash
git clone https://github.com/coffeefuelbump/csv-data-summarizer-claude-skill.git
cp -r csv-data-summarizer-claude-skill/csv-analyzer ~/.claude/skills/
```

---

## Usage

Simply upload a CSV file - skill activates automatically:

```plaintext
# Upload portfolio_returns.csv
# Automatically generates:
# - Summary statistics
# - Correlation matrix
# - Return distribution histogram
# - Drawdown visualization
# - Sharpe ratio calculation
```

---

## Supported Data Types

- Trading data
- Portfolio performance
- Risk metrics
- Financial statements
- Economic indicators
- Transaction records

---

## Works Well With

- Scientific skills (deeper analysis)
- Backtesting (historical data exploration)
- Data analysis (advanced visualization)
