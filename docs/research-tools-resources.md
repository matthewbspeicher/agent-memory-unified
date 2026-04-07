# Research: Tools, Libraries & Resources for Project Improvement

**Date**: 2026-04-07
**Purpose**: Identify tools and resources to improve development workflow and trading capabilities

---

## Table of Contents

1. [Backtesting Libraries](#1-backtesting-libraries)
2. [Quantitative Finance Frameworks](#2-quantitative-finance-frameworks)
3. [Testing Tools](#3-testing-tools)
4. [Code Quality Tools](#4-code-quality-tools)
5. [Financial Data APIs](#5-financial-data-apis)
6. [Bittensor Development](#6-bittensor-development)
7. [VS Code Extensions](#7-vs-code-extensions)
8. [Recommendations](#8-recommendations)

---

## 1. Backtesting Libraries

### Top Recommendations

| Library | Stars | Best For | License |
|---------|-------|----------|---------|
| **Backtesting.py** | 8K+ | Easy-to-use, web UI | MIT |
| **VectorBT** | 3K+ | High-performance, pandas-based | Apache 2.0 |
| **Backtrader** | 21K+ | Feature-rich, extensibility | GPL-3 |
| **bt** | - | Flexible, algorithm-centric | MIT |

### Analysis

- **VectorBT** is fastest due to Numba JIT compilation — good for parameter scanning
- **Backtesting.py** has built-in web UI for interactive exploration
- **Backtrader** is most mature but slower
- Our current backtesting is in `trading/backtesting/` — could integrate these

### Install

```bash
pip install backtesting  # Backtesting.py
pip install vectorbt     # VectorBT
pip install backtrader   # Backtrader
```

---

## 2. Quantitative Finance Frameworks

### FinRL-X (v1.0.0 released March 2026)
- **URL**: https://github.com/AI4Finance-Foundation/FinRL-Trading
- **Stars**: 3K+
- AI-native modular infrastructure for quantitative trading
- Deep reinforcement learning for trading
- Worth monitoring for future integration

### QuantPy
- **URL**: https://github.com/jsmidt/QuantPy
- Framework for quantitative finance in Python

### Nexus (Anagatam)
- Institutional portfolio risk framework
- VaR, CVaR, Tail Gini with CVXPY integration
- Could complement our RiskAnalytics module

---

## 3. Testing Tools

### Property-Based Testing

**Hypothesis** — Already in our project! ✅
- Uses property-based testing to find edge cases
- Already configured in `pytest.ini`
- Can expand to test trading strategy edge cases

```python
from hypothesis import given, strategies as st

@given(st.lists(st.floats(min_value=-1, max_value=1)))
def test_var_always_positive(returns):
    var = calculate_var(returns)
    assert var >= 0
```

### Mutation Testing

**mutmut** — Tests test quality
```bash
pip install mutmut
mutmut run
```

---

## 4. Code Quality Tools

### Ruff (Recommended)

The **2026 standard** for Python linting + formatting:

```bash
pip install ruff
```

**Why Ruff:**
- 10-100x faster than flake8 (written in Rust)
- Replaces: flake8, isort, black, pyupgrade, many plugins
- Single tool for linting + formatting

**Usage:**
```bash
ruff check .          # Lint
ruff format .         # Format
```

### mypy

Type checking — already partially in project

```bash
pip install mypy
mypy trading/         # Type check
```

### Recommendation

Add to `trading/pyproject.toml` or create `ruff.toml`:
```toml
[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP"]
ignore = ["E501"]  # Line too long (handled by formatter)

[tool.ruff.format]
quote-style = "double"
```

---

## 5. Financial Data APIs

### Free Options

| API | Free Tier | Notes |
|-----|-----------|-------|
| **EODHD** | 20 calls/day | 30+ years historical |
| **Alpha Vantage** | 25 calls/day | Good for US stocks |
| **Yahoo Finance** | Unlimited (yfinance) | via `yfinance` library |
| **Eulerpool** | 100K+ securities | Research-focused |

### Python Libraries

```bash
pip install yfinance          # Yahoo Finance
pip install alpha-vantage     # Alpha Vantage
pip install eodhistoricaldata  # EODHD
```

### Already in Project

- `trading/data/sources/yahoo.py` — Uses yfinance ✅
- Multiple broker adapters (IBKR, Alpaca, etc.)

---

## 6. Bittensor Development

### SDK Updates

- **bittensor v10.2.0** (PyPI)
- Subnet 8 (PTN) is active
- docs.bittensor.com has latest API reference

### Tools

- **subtensor** — Blockchain interaction
- **wandb** — Logging for training (already in project)

### Official Resources
- https://docs.learnbittensor.org/
- https://docs.bittensor.com/

---

## 7. VS Code Extensions

### Recommended Extensions

| Extension | Purpose | Install |
|-----------|---------|---------|
| **Pylance** | Type checking, IntelliSense | Built-in |
| **Ruff** | Linting + formatting | `ms-python Ruff` |
| **Python Test Explorer** | Test runner UI | `ms-python.python` |
| **GitLens** | Git history | `eamodio.gitlens` |
| **Error Lens** | Inline errors | `usernamehw.errorlens` |

### Research Tools

| Extension | Purpose |
|-----------|---------|
| **vscode-reveal** | Markdown presentations |
| **Live Server** | Frontend dev |
| **Docker** | Container management |

---

## 8. Recommendations

### Immediate Actions (This Session)

1. **Add Ruff to project**
   ```bash
   pip install ruff
   ruff check trading/ --fix
   ruff format trading/
   ```

2. **Add type hints with mypy**
   - Focus on `trading/risk/` module first
   - Generate stubs for broker interfaces

3. **Expand Hypothesis tests**
   - Add property-based tests for VaR calculations
   - Test strategy parameter bounds

### Future Enhancements

1. **Integrate Backtesting.py or VectorBT**
   - Compare against current backtest implementation
   - Use for parameter optimization

2. **Add mutation testing**
   ```bash
   pip install mutmut
   ```

3. **Monitor FinRL-X**
   - Check for RL-based strategy integration

---

## Summary

| Category | Status | Action |
|----------|--------|--------|
| Backtesting | Have basic | Evaluate VectorBT |
| Testing | Hypothesis ✓ | Expand PBT |
| Linting | Partial | Add Ruff |
| Types | Partial | Add mypy |
| Data | yfinance ✓ | Consider EODHD |
| Bittensor | Subnet 8 ✓ | Monitor updates |

---

## Resources

- Ruff: https://docs.astral.sh/ruff/
- mypy: https://mypy.readthedocs.io/
- VectorBT: https://vectorbt.dev/
- Backtesting.py: https://kernc.github.io/backtesting.py/
- FinRL-X: https://github.com/AI4Finance-Foundation/FinRL-Trading