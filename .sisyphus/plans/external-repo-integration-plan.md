# Implementation Plan: External Repo Learnings

## Overview

Incorporate lessons from `jackson-video-resources/claude-tradingview-mcp-trading` into the trading engine.

---

## 1. BitGet Broker Adapter (HIGH PRIORITY)

**Goal**: Add crypto exchange support via BitGet API

### Files to Create

```
trading/adapters/bitget/
├── __init__.py
├── adapter.py       # Main Broker implementation
├── client.py        # BitGet REST API wrapper (CCXT-style)
├── connection.py    # Connection management
├── order_manager.py # Place/modify/cancel orders
├── account.py       # AccountProvider implementation
├── market_data.py   # MarketDataProvider (quotes, historical)
└── models.py        # BitGet-specific models
```

### Implementation Steps

1. **Client** (`client.py`):
   - Implement BitGet REST API: https://bitget.github.io/docs/api/spot/v2
   - Authentication: HMAC-SHA256 signature (same as external repo)
   - Endpoints: /api/v2/spot/trade/placeOrder, /api/v2/spot/account/balance

2. **Order Manager** (`order_manager.py`):
   - Market/Limit orders
   - Order status polling
   - Fill tracking

3. **Market Data** (`market_data.py`):
   - `get_quote(symbol)` — current price
   - `get_historical(symbol, timeframe, period)` — klines/candles
   - Stream quotes via WebSocket (optional, can poll)

4. **Adapter** (`adapter.py`):
   - Implement `Broker` interface
   - Wire up all sub-components
   - Add to `trading/config.py` with `STA_BITGET_*` env vars

### Config Additions

```bash
# .env
STA_BITGET_ENABLED=true
STA_BITGET_API_KEY=...
STA_BITGET_SECRET_KEY=...
STA_BITGET_PASSPHRASE=...
STA_BITGET_TESTNET=false
```

---

## 2. Tax CSV Logging (HIGH PRIORITY)

**Goal**: Auto-generate tax-ready trade log after each execution

### Implementation

1. **Create** `trading/storage/trade_csv.py`:
   ```python
   class TradeCSVLogger:
       CSV_FILE = "trades.csv"
       HEADERS = ["Date", "Time (UTC)", "Exchange", "Symbol", "Side", 
                  "Quantity", "Price", "Total USD", "Fee (est.)", 
                  "Net Amount", "Order ID", "Mode", "Notes"]
       
       def log_trade(self, order_result: OrderResult, broker: str, mode: str):
           # Append row to CSV
   ```

2. **Integrate** into `agents/router.py`:
   - Call `TradeCSVLogger.log_trade()` after successful execution
   - Also log paper trades and blocked decisions (for audit)

3. **Add CLI**:
   - `python -m trading trade-csv --summary` — generate tax summary
   - Replicates `node bot.js --tax-summary` from external repo

---

## 3. Declarative Rules Engine / Safety Check (MEDIUM PRIORITY)

**Goal**: Add pre-trade validation layer matching external repo's safety check

### Files to Create/Modify

```
trading/
├── rules/
│   ├── __init__.py
│   ├── engine.py      # RulesEngine class
│   ├── models.py      # Rule, RuleSet, RuleResult
│   ├── conditions.py  # Built-in condition types
│   └── evaluators.py  # PriceEvaluator, IndicatorEvaluator
```

### Implementation

1. **Models** (`rules/models.py`):
   ```python
   class Rule:
       name: str
       condition: str  # "price_above", "rsi_below", etc.
       threshold: float
       enabled: bool
   
   class RuleSet:
       name: str
       entry_rules: list[Rule]
       exit_rules: list[Rule]
       risk_rules: list[Rule]
   ```

2. **Engine** (`rules/engine.py`):
   ```python
   class RulesEngine:
       def validate(self, rule_set: RuleSet, market_data: dict) -> RuleResult:
           # Check each rule, return pass/fail with actual values
           # Matches external repo's runSafetyCheck() pattern
   ```

3. **YAML Integration**:
   - Support loading rules from YAML (like `rules.json` format)
   - Agent config can reference rule sets

4. **Integration Point**:
   - Call `RulesEngine.validate()` in `OpportunityRouter` before execution
   - Block trade if any rule fails, log which rule failed and actual value

---

## 4. Binance Market Data Source (MEDIUM PRIORITY)

**Goal**: Add free market data for backtesting (mirrors external repo's cloud mode)

### Files to Create

```
trading/data/sources/
├── binance.py  # BinanceDataSource
```

### Implementation

```python
class BinanceDataSource(MarketDataProvider):
    """Free public API for historical candles - no auth required"""
    
    BASE_URL = "https://api.binance.com/api/v3"
    
    async def get_historical(self, symbol: str, timeframe: str, period: str):
        # GET /klines?symbol=BTCUSDT&interval=4h&limit=500
    
    async def get_quote(self, symbol: str):
        # GET /ticker/price?symbol=BTCUSDT
```

### Usage

- Backtesting: use Binance as data source for strategy validation
- Live trading: optional supplement to broker market data
- Add to `trading/config.py`: `STA_BINANCE_ENABLED=true`

---

## 5. rules.json Schema for Agent Strategy Config (LOW PRIORITY)

**Goal**: Adopt external repo's declarative strategy format

### Schema Design

```json
// strategies/momentum-vwap.json
{
  "strategy": {
    "name": "VWAP + RSI + EMA Strategy",
    "description": "Three indicators for trend, bias, timing",
    "version": "1.0"
  },
  "indicators": {
    "ema_8": "Trend direction",
    "vwap": "Session bias",
    "rsi_3": "Entry timing"
  },
  "bias_criteria": {
    "bullish": ["price > vwap", "price > ema8"],
    "bearish": ["price < vwap", "price < ema8"]
  },
  "entry_rules": {
    "long": ["price > vwap", "price > ema8", "rsi3 < 30"],
    "short": ["price < vwap", "price < ema8", "rsi3 > 70"]
  },
  "risk_rules": [
    "max_1pct_portfolio",
    "max_3_trades_per_day",
    "no_trade_if_overextended_1.5pct"
  ],
  "exit_rules": [
    "rsi3 crosses 50",
    "0.3pct hard stop",
    "vwap touch exit"
  ]
}
```

### Implementation

1. **Create** `trading/strategies/schemas/rule_schema.py`:
   - Pydantic models matching schema above

2. **Add loader** `trading/strategies/loader.py`:
   - Load from YAML/JSON files
   - Convert to RulesEngine format

3. **Agent config update**:
   - `agents.yaml` → add `strategy_file` field
   - Agent references strategy file instead of hardcoded logic

---

## Implementation Order

```
Phase 1 (Week 1):
├── 1.1 BitGet client + basic order placement
├── 1.2 BitGet adapter integration
└── 1.3 Config + startup wiring

Phase 2 (Week 2):
├── 2.1 TradeCSVLogger implementation
├── 2.2 Router integration
└── 2.3 CLI command

Phase 3 (Week 3):
├── 3.1 Rules models + engine
├── 3.2 Pre-execution validation
└── 3.3 Rules failure logging

Phase 4 (Week 4):
├── 4.1 Binance data source
├── 4.2 Backtest integration
└── 4.3 Strategy file format
```

---

## Dependencies

- **CCXT**: For BitGet (or custom implementation like external repo)
- **python-binance**: Optional, for Binance data source
- **PyYAML**: For strategy file parsing

---

## Testing Strategy

1. **BitGet**: 
   - Paper trading first (simulated orders)
   - Then small live orders
   - Verify fills match expected

2. **Tax CSV**: 
   - Unit test row generation
   - Integration test with paper broker

3. **Rules Engine**: 
   - Test each condition type
   - Test rule set validation

4. **Binance**: 
   - Compare with known data sources
   - Verify timeframe mapping