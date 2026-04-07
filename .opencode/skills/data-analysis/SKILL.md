---
name: data-analysis
description: End-to-end statistical analysis and reporting with 6 specialized sub-agents
version: 1.0.0
author: liangdabiao
type: skill
category: data-science
tags:
  - statistics
  - visualization
  - analysis
  - python
  - reporting
---

# Claude Data Analysis Assistant

> **Purpose**: Complete data analysis workflow from validation through insights generation.

---

## What I Do

Six specialized sub-agents for end-to-end analysis:

### 1. data-explorer
Statistical analysis and pattern discovery:
- Exploratory data analysis
- Summary statistics
- Correlation matrices
- Outlier detection

### 2. visualization-specialist
Chart and graph generation:
- Time series plots
- Histograms and box plots
- Heatmaps
- Scatter plots

### 3. code-generator
Production-ready analysis code:
- Python (pandas, NumPy, scikit-learn)
- R (tidyverse, ggplot2)
- SQL
- JavaScript

### 4. report-writer
Comprehensive documentation:
- Executive summaries
- Methodology descriptions
- Statistical evidence
- Recommendations

### 5. quality-assurance
Data validation:
- Missing data checks
- Data type validation
- Anomaly detection
- Statistical assumption verification

### 6. hypothesis-generator
Research insights:
- Statistical test suggestions
- Pattern identification
- Follow-up analysis proposals
- Testable hypotheses

---

## Installation

```bash
git clone https://github.com/liangdabiao/claude-data-analysis.git
cp -r claude-data-analysis/.claude/skills/* ~/.claude/skills/
```

---

## Usage

### Slash Commands

```plaintext
/analyze      # Run comprehensive analysis
/visualize    # Generate charts
/generate     # Create analysis code
/report       # Write documentation
/quality      # Validate data
/hypothesis   # Suggest research directions
```

### Examples

```plaintext
Analyze this portfolio returns dataset for statistical significance
Visualize the correlation structure of these market factors
Generate Python code for rolling regression analysis
Test the hypothesis that momentum predicts returns
```

---

## Activation

Automatically activates upon data upload. Runs quality checks first, then enables full analysis workflow.
