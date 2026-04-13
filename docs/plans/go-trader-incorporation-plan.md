# go-trader Incorporation Plan

**Date**: 2026-04-10  
**Source**: Research synthesis from go-trader repo analysis  
**Status**: Implementation Plan (Reviewed & Fixed)  

## Executive Summary

Incorporating 8 key patterns from go-trader into our trading engine. Priority items (1-3) are risk management enhancements. Medium priority (4-6) are strategy improvements. Lower priority (7-8) are developer experience improvements.

### Review Fixes Applied
- **#1**: Added HWM persistence via `PortfolioStateStore` (was in-memory only)
- **#3**: Corrected DI pattern to match existing `load_risk_config()` signature
- **#4**: Confirmed "4h" timeframe supported by BitGet/IBKR adapters
- **#5**: Updated migration paths to `scripts/migrations/` directory
- **#7**: Added API endpoint specifications and rollback strategy

---

## 1. Portfolio-Level Kill Switch

**go-trader pattern**: 25% aggregate drawdown → force-close ALL positions, 24h cooldown  
**Current state**: We have portfolio-level KillSwitch but no automatic drawdown trigger  
**Issue found**: MaxDrawdownPct uses in-memory HWM only — lost on restart

### Implementation

**Files to create:**
- `trading/storage/portfolio_state.py` — Persist HWM and trigger state

**Files to modify:**
- `trading/risk/rules.py` — Add `PortfolioDrawdownKillSwitch` rule
- `trading/risk/config.py` — Register new rule, accept `portfolio_state_store` param
- `trading/api/container.py` — Wire PortfolioStateStore
- `trading/api/routes/risk.py` — Add portfolio drawdown status endpoint

**Step 1: Create PortfolioStateStore (persistence layer)**
```python
# trading/storage/portfolio_state.py

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncConnection

@dataclass
class PortfolioState:
    high_water_mark: Decimal
    triggered_at: datetime | None
    triggered: bool
    updated_at: datetime

class PortfolioStateStore:
    """Persists portfolio-level risk state across restarts."""
    
    def __init__(self, db: AsyncConnection) -> None:
        self._db = db
    
    async def initialize(self) -> None:
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_state (
                key TEXT PRIMARY KEY,
                high_water_mark TEXT NOT NULL,
                triggered INTEGER NOT NULL DEFAULT 0,
                triggered_at TEXT,
                updated_at TEXT NOT NULL
            )
        """)
    
    async def get_state(self, key: str = "default") -> PortfolioState | None:
        row = await self._db.fetch_one(
            "SELECT * FROM portfolio_state WHERE key = :key", {"key": key}
        )
        if not row:
            return None
        return PortfolioState(
            high_water_mark=Decimal(row["high_water_mark"]),
            triggered=bool(row["triggered"]),
            triggered_at=datetime.fromisoformat(row["triggered_at"]) if row["triggered_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
    
    async def save_state(self, state: PortfolioState, key: str = "default") -> None:
        await self._db.execute("""
            INSERT INTO portfolio_state (key, high_water_mark, triggered, triggered_at, updated_at)
            VALUES (:key, :hwm, :triggered, :triggered_at, :updated_at)
            ON CONFLICT(key) DO UPDATE SET
                high_water_mark = :hwm,
                triggered = :triggered,
                triggered_at = :triggered_at,
                updated_at = :updated_at
        """, {
            "key": key,
            "hwm": str(state.high_water_mark),
            "triggered": int(state.triggered),
            "triggered_at": state.triggered_at.isoformat() if state.triggered_at else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
```

**Step 2: Create PortfolioDrawdownKillSwitch rule**
```python
# trading/risk/rules.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import ClassVar

@dataclass
class PortfolioDrawdownKillSwitch(RiskRule):
    """Triggers kill switch when aggregate portfolio drawdown exceeds threshold.
    
    Persists high-water mark to survive restarts.
    """
    name: ClassVar[str] = "portfolio_drawdown_kill"
    
    max_drawdown_pct: float = 25.0
    cooldown_hours: int = 24
    state_store: Any = None  # PortfolioStateStore (injected)
    _state_key: str = "portfolio_drawdown"
    
    async def async_evaluate(self, trade: OrderBase, quote: Quote, ctx: PortfolioContext) -> RiskResult:
        # Load persisted state
        state = None
        if self.state_store:
            state = await self.state_store.get_state(self._state_key)
        
        hwm = state.high_water_mark if state else Decimal("0")
        triggered = state.triggered if state else False
        triggered_at = state.triggered_at if state else None
        
        # Check cooldown
        if triggered and triggered_at:
            cooldown_end = triggered_at + timedelta(hours=self.cooldown_hours)
            if datetime.now(timezone.utc) < cooldown_end:
                return RiskResult(
                    passed=False,
                    rule_name=self.name,
                    reason=f"Portfolio kill switch active (cooldown until {cooldown_end.isoformat()})"
                )
            else:
                # Cooldown expired, reset
                triggered = False
                triggered_at = None
        
        # Update HWM
        current_value = ctx.balance.net_liquidation
        if current_value > hwm:
            hwm = current_value
        
        # Check drawdown
        if hwm > 0:
            drawdown_pct = float((hwm - current_value) / hwm * 100)
            if drawdown_pct >= self.max_drawdown_pct:
                triggered = True
                triggered_at = datetime.now(timezone.utc)
                
                # Persist state
                if self.state_store:
                    await self.state_store.save_state(
                        PortfolioState(
                            high_water_mark=hwm,
                            triggered=triggered,
                            triggered_at=triggered_at,
                            updated_at=datetime.now(timezone.utc),
                        ),
                        key=self._state_key,
                    )
                
                return RiskResult(
                    passed=False,
                    rule_name=self.name,
                    reason=f"Portfolio drawdown {drawdown_pct:.1f}% >= {self.max_drawdown_pct}%"
                )
        
        # Persist updated HWM
        if self.state_store:
            await self.state_store.save_state(
                PortfolioState(
                    high_water_mark=hwm,
                    triggered=triggered,
                    triggered_at=triggered_at,
                    updated_at=datetime.now(timezone.utc),
                ),
                key=self._state_key,
            )
        
        return RiskResult(passed=True, rule_name=self.name)
    
    def evaluate(self, trade: OrderBase, quote: Quote, ctx: PortfolioContext) -> RiskResult:
        # Sync fallback (required by base class)
        return RiskResult(passed=True, rule_name=self.name, reason="Use async_evaluate")
```

**Step 3: Register in config.py**
```python
# trading/risk/config.py

def load_risk_config(
    path: str,
    leaderboard=None,
    tournament=None,
    perf_store=None,
    agent_store=None,
    settings=None,
    journal_manager=None,
    portfolio_state_store=None,  # NEW
    preloaded_data: dict | None = None,
) -> RiskEngine:
    # ... existing code ...
    
    # Portfolio drawdown kill switch (if store available)
    if portfolio_state_store:
        rules.append(PortfolioDrawdownKillSwitch(
            max_drawdown_pct=25.0,
            cooldown_hours=24,
            state_store=portfolio_state_store,
        ))
```

**Step 4: Wire in ServiceContainer**
```python
# trading/api/container.py

async def _init_execution_pipeline(self):
    # ... existing code ...
    
    # Initialize portfolio state store
    from storage.portfolio_state import PortfolioStateStore
    portfolio_state_store = PortfolioStateStore(self.db)
    await portfolio_state_store.initialize()
    
    self.risk_engine = load_risk_config(
        self._resolve_path("risk.yaml"),
        perf_store=self.perf_store,
        agent_store=self.agent_store,
        settings=self.settings,
        journal_manager=self.journal_manager,
        portfolio_state_store=portfolio_state_store,  # NEW
    )
```

**Step 5: Add API endpoint**
```python
# trading/api/routes/risk.py

@router.get("/portfolio-drawdown")
async def get_portfolio_drawdown_status():
    """Get portfolio drawdown status and HWM."""
    from storage.portfolio_state import PortfolioStateStore
    # Get store from container
    store = get_portfolio_state_store()
    state = await store.get_state("portfolio_drawdown")
    
    return {
        "high_water_mark": float(state.high_water_mark) if state else 0,
        "triggered": state.triggered if state else False,
        "triggered_at": state.triggered_at.isoformat() if state and state.triggered_at else None,
        "cooldown_hours": 24,
    }
```

**Database migration:**
```sql
-- scripts/migrations/add-portfolio-state.sql

CREATE TABLE IF NOT EXISTS portfolio_state (
    key TEXT PRIMARY KEY,
    high_water_mark TEXT NOT NULL,
    triggered INTEGER NOT NULL DEFAULT 0,
    triggered_at TEXT,
    updated_at TEXT NOT NULL
);
```

**YAML config:**
```yaml
risk:
  rules:
    - type: portfolio_drawdown_kill
      params:
        max_drawdown_pct: 25.0
        cooldown_hours: 24
```

---

## 2. Consecutive Loss Circuit Breaker

**go-trader pattern**: 5 consecutive losses → 1h pause per strategy  
**Current state**: StrategyHealthEngine tracks win_rate but not consecutive loss streaks

### Implementation

**Files to modify:**
- `trading/storage/performance.py` — Add streak fields to PerformanceSnapshot
- `trading/agents/analytics.py` — Compute streaks from trade_analytics
- `trading/learning/strategy_health.py` — Add consecutive loss check
- `trading/learning/config.py` — Add config thresholds

**Files to create:**
- `scripts/migrations/add-streak-tracking.sql` — Database migration

**Step 1: Database migration**
```sql
-- scripts/migrations/add-streak-tracking.sql

ALTER TABLE performance_snapshots 
ADD COLUMN IF NOT EXISTS consecutive_losses INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS max_consecutive_losses INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS consecutive_wins INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS max_consecutive_wins INTEGER DEFAULT 0;
```

**Step 2: Extend PerformanceSnapshot**
```python
# trading/storage/performance.py

class PerformanceSnapshot(BaseModel):
    # ... existing fields ...
    consecutive_losses: int = 0
    max_consecutive_losses: int = 0
    consecutive_wins: int = 0
    max_consecutive_wins: int = 0
```

**Step 3: Compute streaks in AnalyticsAgent**
```python
# trading/agents/analytics.py

async def _compute_streaks(self, agent_name: str) -> dict[str, int]:
    """Compute consecutive win/loss streaks from recent trades."""
    trades = await self._trade_store.list_by_strategy(agent_name, limit=200)
    
    consecutive_losses = 0
    max_consecutive_losses = 0
    consecutive_wins = 0
    max_consecutive_wins = 0
    
    for trade in reversed(trades):
        outcome = trade.get("realized_outcome")
        if outcome == "loss":
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            consecutive_wins = 0
        elif outcome == "win":
            consecutive_wins += 1
            max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
            consecutive_losses = 0
    
    return {
        "consecutive_losses": consecutive_losses,
        "max_consecutive_losses": max_consecutive_losses,
        "consecutive_wins": consecutive_wins,
        "max_consecutive_wins": max_consecutive_wins,
    }

# In scan(), include in snapshot:
streaks = await self._compute_streaks(agent_info.name)
snapshot = PerformanceSnapshot(
    # ... existing fields ...
    **streaks,
)
```

**Step 4: Circuit breaker in StrategyHealthEngine**
```python
# trading/learning/strategy_health.py

@dataclass
class StrategyHealthConfig:
    # ... existing fields ...
    max_consecutive_losses: int = 5  # Circuit breaker threshold
    consecutive_loss_cooldown_hours: int = 48

class StrategyHealthEngine:
    async def _evaluate_internal(self, agent_name: str) -> StrategyHealthStatus:
        snapshot = await self._perf_store.get_latest(agent_name)
        if not snapshot:
            return StrategyHealthStatus.NORMAL
        
        # Existing checks...
        
        # NEW: Consecutive loss circuit breaker
        consecutive_losses = snapshot.consecutive_losses or 0
        if consecutive_losses >= self._cfg.max_consecutive_losses:
            await self._transition(
                agent_name=agent_name,
                old_status=current_status,
                new_status=StrategyHealthStatus.THROTTLED,
                reason=f"Circuit breaker: {consecutive_losses} consecutive losses >= {self._cfg.max_consecutive_losses}",
                metrics=metrics,
            )
            return StrategyHealthStatus.THROTTLED
        
        return target_status
```

**Step 5: Config**
```yaml
strategy_health:
  enabled: true
  max_consecutive_losses: 5
  consecutive_loss_cooldown_hours: 48
```

---

## 3. Correlation Enforcement in Risk Pipeline

**go-trader pattern**: Warns when >60% concentration in one asset or >75% same-direction strategies  
**Current state**: We have `StrategyCorrelationMonitor` and `CorrelationMonitor` but no risk gate

### Implementation (Corrected DI Pattern)

**Files to create:**
- `trading/risk/correlation_gate.py` — New risk rule

**Files to modify:**
- `trading/risk/config.py` — Register rule, accept `correlation_monitor` param
- `trading/api/container.py` — Wire CorrelationMonitor

**Step 1: Create CorrelationGate rule**
```python
# trading/risk/correlation_gate.py

from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar, Any

@dataclass
class CorrelationGate(RiskRule):
    """Reduces position size when portfolio correlation is high."""
    name: ClassVar[str] = "correlation_gate"
    
    # Dependencies (injected via constructor)
    correlation_monitor: Any = None
    
    # Thresholds
    high_correlation_threshold: float = 0.7
    critical_correlation_threshold: float = 0.85
    high_correlation_multiplier: float = 0.5
    critical_correlation_multiplier: float = 0.25
    
    async def async_evaluate(self, trade: OrderBase, quote: Quote, ctx: PortfolioContext) -> RiskResult:
        if not self.correlation_monitor:
            return RiskResult(passed=True, rule_name=self.name, reason="Correlation monitor not configured")
        
        snapshot = await self.correlation_monitor.get_latest_snapshot()
        if not snapshot:
            return RiskResult(passed=True, rule_name=self.name, reason="No correlation data")
        
        agent_name = getattr(trade, "agent_name", None)
        if not agent_name:
            return RiskResult(passed=True, rule_name=self.name, reason="Agent name not available")
        
        should_reduce, multiplier = self.correlation_monitor.should_reduce_position(
            agent_name, snapshot
        )
        
        if should_reduce:
            adjusted_qty = Decimal(str(float(trade.quantity) * multiplier))
            return RiskResult(
                passed=True,
                rule_name=self.name,
                adjusted_quantity=adjusted_qty,
                reason=f"Correlation gate: reducing size by {(1-multiplier)*100:.0f}%"
            )
        
        return RiskResult(passed=True, rule_name=self.name)
    
    def evaluate(self, trade: OrderBase, quote: Quote, ctx: PortfolioContext) -> RiskResult:
        return RiskResult(passed=True, rule_name=self.name, reason="Use async_evaluate")
```

**Step 2: Register in config.py (follows existing DI pattern)**
```python
# trading/risk/config.py

def load_risk_config(
    path: str,
    leaderboard=None,
    tournament=None,
    perf_store=None,
    agent_store=None,
    settings=None,
    journal_manager=None,
    portfolio_state_store=None,
    correlation_monitor=None,  # NEW - follows existing pattern
    preloaded_data: dict | None = None,
) -> RiskEngine:
    # ... existing code ...
    
    # Correlation gate (if monitor available)
    if correlation_monitor:
        from risk.correlation_gate import CorrelationGate
        rules.insert(0, CorrelationGate(
            correlation_monitor=correlation_monitor,
            high_correlation_threshold=0.7,
        ))
```

**Step 3: Wire in ServiceContainer**
```python
# trading/api/container.py

async def _init_execution_pipeline(self):
    # ... existing code ...
    
    # Initialize correlation monitor
    from storage.correlation import CorrelationStore
    from learning.correlation_monitor import CorrelationMonitor, CorrelationConfig
    
    corr_store = CorrelationStore(self.db)
    await corr_store.initialize()
    
    corr_config = CorrelationConfig(
        enabled=True,
        lookback_days=30,
        high_correlation_threshold=0.7,
    )
    correlation_monitor = CorrelationMonitor(
        perf_store=self.perf_store,
        correlation_store=corr_store,
        config=corr_config,
    )
    
    self.risk_engine = load_risk_config(
        self._resolve_path("risk.yaml"),
        perf_store=self.perf_store,
        agent_store=self.agent_store,
        settings=self.settings,
        journal_manager=self.journal_manager,
        portfolio_state_store=portfolio_state_store,
        correlation_monitor=correlation_monitor,  # NEW
    )
```

**YAML config:**
```yaml
risk:
  rules:
    - type: correlation_gate
      params:
        high_correlation_threshold: 0.7
        critical_correlation_threshold: 0.85
```

---

## 4. Higher-Timeframe (HTF) Trend Filter

**go-trader pattern**: Checks higher-timeframe trend before executing  
**Current state**: DataBus supports "4h" via BitGet/IBKR adapters (confirmed)

### Implementation

**Files to modify:**
- `trading/data/bus.py` — Add HTF trend methods
- `trading/agents/models.py` — Add `htf_filter` to AgentConfig
- `trading/agents/router.py` — Add HTF check in execution pipeline

**Step 1: Add HTF methods to DataBus**
```python
# trading/data/bus.py

class DataBus:
    async def get_htf_trend(self, symbol: Symbol, htf: str = "4h") -> dict:
        """Get higher-timeframe trend direction.
        
        Note: "4h" is supported by BitGet and IBKR adapters.
        Falls back to "1d" if 4h unavailable.
        """
        try:
            bars = await self.get_historical(symbol, timeframe=htf, period="3mo")
        except Exception:
            # Fallback to daily if 4h not supported
            bars = await self.get_historical(symbol, timeframe="1d", period="3mo")
        
        if not bars or len(bars) < 50:
            return {"symbol": str(symbol), "htf": htf, "trend": "neutral", "confidence": 0.0}
        
        closes = [float(b.close) for b in bars]
        sma_20 = sum(closes[-20:]) / 20
        sma_50 = sum(closes[-50:]) / 50
        current = closes[-1]
        
        # Trend determination
        if sma_20 > sma_50 and current > sma_20:
            trend = "bullish"
        elif sma_20 < sma_50 and current < sma_20:
            trend = "bearish"
        else:
            trend = "neutral"
        
        separation = abs(sma_20 - sma_50) / sma_50
        confidence = min(1.0, separation * 10)
        
        return {
            "symbol": str(symbol),
            "htf": htf,
            "trend": trend,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "confidence": confidence,
        }
    
    async def check_htf_alignment(self, symbol: Symbol, side: str, htf: str = "4h") -> bool:
        """Check if trade direction aligns with HTF trend."""
        htf_data = await self.get_htf_trend(symbol, htf)
        
        if htf_data["confidence"] < 0.3:
            return True  # Low confidence = no filter
        
        if side == "BUY" and htf_data["trend"] == "bullish":
            return True
        elif side == "SELL" and htf_data["trend"] == "bearish":
            return True
        elif htf_data["trend"] == "neutral":
            return True
        
        return False
```

**Step 2: Add to AgentConfig**
```python
# trading/agents/models.py

@dataclass
class AgentConfig:
    # ... existing fields ...
    htf_filter: str | None = None  # e.g., "4h", "1d"
```

**Step 3: Add HTF check in router**
```python
# trading/agents/router.py

async def _check_htf_alignment(self, opportunity: Opportunity) -> str | None:
    """Check if trade aligns with higher-timeframe trend."""
    htf = opportunity.data.get("htf_filter") or getattr(
        self._get_agent_config(opportunity.agent_name), "htf_filter", None
    )
    
    if not htf:
        return None
    
    trade = opportunity.suggested_trade
    if not trade:
        return None
    
    symbol = trade.symbol
    side = trade.side.value if hasattr(trade.side, "value") else str(trade.side)
    
    aligned = await self._data_bus.check_htf_alignment(symbol, side, htf)
    
    if not aligned:
        htf_data = await self._data_bus.get_htf_trend(symbol, htf)
        return f"htf_filter: {side} rejected - HTF {htf} trend is {htf_data['trend']}"
    
    return None

# In _try_execute(), before risk evaluation:
htf_rejection = await self._check_htf_alignment(opportunity)
if htf_rejection:
    logger.info("HTF filter blocked trade: %s", htf_rejection)
    return
```

**YAML config:**
```yaml
agents:
  - name: momentum_trader
    strategy: momentum
    htf_filter: "4h"
```

---

## 5. Fee/Slippage Model per Broker

**go-trader pattern**: Comprehensive fee + slippage table per venue  
**Current state**: We have FidelityFeeModel and IBKRFeeModel

### Implementation

**Files to modify:**
- `trading/broker/models.py` — Add Kalshi/Polymarket/Binance fee models
- `trading/backtesting/models.py` — Add CommissionModel enum values
- `trading/backtesting/engine.py` — Wire new models

**Step 1: Add fee models**
```python
# trading/broker/models.py

class KalshiFeeModel(FeeModel):
    """Kalshi: 2% taker, 0% maker."""
    TAKER_FEE_RATE = Decimal("0.02")
    
    def calculate(self, order: OrderBase, fill_price: Decimal) -> Decimal:
        notional = fill_price * order.quantity
        return (notional * self.TAKER_FEE_RATE).quantize(Decimal("0.01"))


class PolymarketFeeModel(FeeModel):
    """Polymarket: 2% taker, 1% maker."""
    TAKER_FEE_RATE = Decimal("0.02")
    
    def calculate(self, order: OrderBase, fill_price: Decimal) -> Decimal:
        notional = fill_price * order.quantity
        return (notional * self.TAKER_FEE_RATE).quantize(Decimal("0.01"))


class BinanceFeeModel(FeeModel):
    """Binance: 0.1% spot, 0.04%/0.02% futures."""
    SPOT_TAKER = Decimal("0.001")
    FUTURES_TAKER = Decimal("0.0004")
    
    def __init__(self, is_futures: bool = False):
        self.is_futures = is_futures
    
    def calculate(self, order: OrderBase, fill_price: Decimal) -> Decimal:
        notional = fill_price * order.quantity
        rate = self.FUTURES_TAKER if self.is_futures else self.SPOT_TAKER
        return (notional * rate).quantize(Decimal("0.0001"))
```

**Step 2: Add to CommissionModel enum**
```python
# trading/backtesting/models.py

class CommissionModel(str, Enum):
    # ... existing ...
    KALSHI = "kalshi"
    POLYMARKET = "polymarket"
    BINANCE_SPOT = "binance_spot"
    BINANCE_FUTURES = "binance_futures"
```

**Step 3: Wire into backtesting engine**
```python
# trading/backtesting/engine.py

def _get_commission_fn(model: CommissionModel, params: dict) -> Any:
    # ... existing cases ...
    
    elif model == CommissionModel.KALSHI:
        from broker.models import KalshiFeeModel
        fm = KalshiFeeModel()
        return lambda qty, price, symbol: fm.calculate(
            OrderBase(symbol=symbol, side=OrderSide.BUY, quantity=qty, account_id="backtest"),
            price
        )
    
    # Similar for POLYMARKET, BINANCE_SPOT, BINANCE_FUTURES
```

---

## 6. Theta Harvesting Exit Rules

**go-trader pattern**: Profit target (60% premium), stop loss (200%), min DTE floor  
**Current state**: We have StopLoss, TakeProfit, TimeExit but no theta-specific rules

### Implementation

**Files to modify:**
- `trading/exits/rules.py` — Add ThetaDecayExit rule
- `trading/exits/manager.py` — Update compute_default_exits for prediction markets

**New exit rule:**
```python
# trading/exits/rules.py

@dataclass
class ThetaDecayExit(ExitRule):
    """Exit when theta decay reaches target profit % or DTE threshold."""
    
    entry_price: Decimal
    profit_target_pct: float  # e.g., 0.50 = 50% profit
    stop_loss_pct: float = 2.0  # e.g., 2.0 = 200% loss
    min_dte: int = 1
    expires_at: datetime | None = None
    side: str = "BUY"
    
    @property
    def name(self) -> str:
        return "theta_decay_exit"
    
    def should_exit(
        self,
        current_price: Decimal,
        current_time: datetime | None = None,
        **kwargs: Any,
    ) -> bool:
        now = current_time or datetime.now(timezone.utc)
        
        # Profit check
        if self.side == "BUY":
            profit_pct = float((current_price - self.entry_price) / self.entry_price)
        else:
            profit_pct = float((self.entry_price - current_price) / self.entry_price)
        
        if profit_pct >= self.profit_target_pct:
            return True
        if profit_pct <= -self.stop_loss_pct:
            return True
        
        # DTE check
        if self.expires_at:
            expires = self.expires_at.replace(tzinfo=timezone.utc) if self.expires_at.tzinfo is None else self.expires_at
            days_remaining = (expires - now).total_seconds() / 86400
            if days_remaining <= self.min_dte:
                return True
        
        return False
    
    @property
    def exit_fraction(self) -> float:
        return 1.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "theta_decay_exit",
            "entry_price": str(self.entry_price),
            "profit_target_pct": self.profit_target_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "min_dte": self.min_dte,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "side": self.side,
        }
```

**Update parse_rule():**
```python
# trading/exits/rules.py

def parse_rule(d: dict[str, Any]) -> ExitRule:
    t = d["type"]
    # ... existing cases ...
    
    elif t == "theta_decay_exit":
        return ThetaDecayExit(
            entry_price=Decimal(d["entry_price"]),
            profit_target_pct=d["profit_target_pct"],
            stop_loss_pct=d.get("stop_loss_pct", 2.0),
            min_dte=d.get("min_dte", 1),
            expires_at=datetime.fromisoformat(d["expires_at"]) if d.get("expires_at") else None,
            side=d.get("side", "BUY"),
        )
```

**Update default exits for prediction markets:**
```python
# trading/exits/manager.py

def compute_default_exits(self, agent_config, entry_price, side, expires_at=None):
    is_prediction = any(
        kw in str(agent_config.universe).lower()
        for kw in ["kalshi", "polymarket", "prediction"]
    )
    
    if is_prediction and expires_at:
        return [{
            "type": "theta_decay_exit",
            "entry_price": str(entry_price),
            "profit_target_pct": 0.50,
            "stop_loss_pct": 2.0,
            "min_dte": 2,
            "expires_at": expires_at.isoformat(),
            "side": side,
        }]
    
    # ... existing equity defaults ...
```

---

## 7. Agent Concurrency Limits

**go-trader pattern**: Max 4 concurrent Python scripts, 30s timeout  
**Current state**: AgentRunner runs all agents in parallel with no limit

### Implementation (Verified: Health checks already run outside semaphore)

**Files to modify:**
- `trading/agents/runner.py` — Add semaphore and timeout
- `trading/agents/models.py` — Add scan_timeout to AgentConfig
- `trading/agents/config.py` — Add scan_timeout to schema

**Step 1: Add semaphore to AgentRunner**
```python
# trading/agents/runner.py

class AgentRunner:
    def __init__(
        self,
        data_bus: DataBus,
        router: OpportunityRouter,
        max_concurrent_scans: int = 5,
        default_scan_timeout: float = 120.0,
        # ... existing params ...
    ) -> None:
        # ... existing init ...
        self._scan_semaphore = asyncio.Semaphore(max_concurrent_scans)
        self._default_scan_timeout = default_scan_timeout
    
    async def _execute_scan(self, agent: Agent) -> list[Opportunity]:
        # Health check runs BEFORE semaphore (verified in codebase)
        # Lines 256-284: Early exit if RETIRED/SHADOW_ONLY
        
        # Memory consultation, session bias, TV context
        # Lines 286-371: Run outside semaphore
        
        # Acquire semaphore only for agent.scan()
        async with self._scan_semaphore:
            try:
                timeout = getattr(agent.config, "scan_timeout", None) or self._default_scan_timeout
                
                try:
                    opportunities = await asyncio.wait_for(
                        agent.scan(self._data_bus),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    logger.error("Agent %s scan timed out after %.1fs", agent.name, timeout)
                    self._error_counts[agent.name] += 1
                    self._last_errors[agent.name] = f"Scan timeout ({timeout}s)"
                    return []
                
                # ... rest of existing logic (routing, events) ...
```

**Step 2: Add scan_timeout to AgentConfig**
```python
# trading/agents/models.py

@dataclass
class AgentConfig:
    # ... existing fields ...
    scan_timeout: float = 120.0  # Seconds
```

**Step 3: Add to schema**
```python
# trading/agents/config.py

class AgentConfigSchema(BaseModel):
    # ... existing fields ...
    scan_timeout: float = Field(default=120.0, ge=1.0, le=600.0)
```

**YAML config:**
```yaml
agents:
  - name: llm_analyst
    strategy: llm
    scan_timeout: 300.0
  
  - name: rsi_scanner
    strategy: rsi
    scan_timeout: 30.0
```

---

## 8. Strategy Registry Decorator

**go-trader pattern**: `@register_strategy(name, desc, defaults)`  
**Current state**: Manual `register_strategy()` calls

### Implementation

**Files to create:**
- `trading/agents/decorators.py` — Decorator implementation

**Files to modify:**
- `trading/agents/config.py` — Update registration

**Step 1: Create decorator**
```python
# trading/agents/decorators.py

_decorated_strategies: list[tuple[str, type, dict]] = []

def strategy(
    name: str,
    description: str = "",
    timeout: float = 120.0,
    default_params: dict | None = None,
):
    """Decorator to register a strategy class."""
    def decorator(cls: type) -> type:
        cls._strategy_name = name
        cls._strategy_description = description
        cls._strategy_timeout = timeout
        cls._strategy_default_params = default_params or {}
        
        _decorated_strategies.append((name, cls, {
            "description": description,
            "timeout": timeout,
            "default_params": default_params,
        }))
        
        return cls
    return decorator

def register_decorated_strategies():
    """Register all decorated strategies."""
    from agents.config import register_strategy
    for name, cls, metadata in _decorated_strategies:
        register_strategy(name, cls)
```

**Step 2: Update config.py**
```python
# trading/agents/config.py

def _ensure_strategies_registered() -> None:
    global _STRATEGIES_REGISTERED
    if _STRATEGIES_REGISTERED:
        return
    
    # ... existing imports ...
    
    # NEW: Register decorated strategies
    from agents.decorators import register_decorated_strategies
    register_decorated_strategies()
    
    _STRATEGIES_REGISTERED = True
```

**Usage example:**
```python
# trading/strategies/rsi.py

from agents.decorators import strategy

@strategy(
    name="rsi",
    description="RSI mean reversion strategy",
    timeout=30.0,
    default_params={"rsi_period": 14, "oversold": 30, "overbought": 70}
)
class RSIAgent(StructuredAgent):
    # ... implementation ...
```

---

## Implementation Order

### Phase 1: Risk Management (High Priority)
1. **Portfolio-Level Kill Switch** — 3-4 hours (includes persistence layer)
2. **Consecutive Loss Circuit Breaker** — 3-4 hours (includes DB migration)
3. **Correlation Enforcement** — 2-3 hours

### Phase 2: Strategy Enhancements (Medium Priority)
4. **Theta Harvesting Exit Rules** — 2-3 hours
5. **Fee/Slippage Models** — 1-2 hours
6. **HTF Trend Filter** — 3-4 hours

### Phase 3: Developer Experience (Lower Priority)
7. **Agent Concurrency Limits** — 1-2 hours
8. **Strategy Registry Decorator** — 2-3 hours

**Total estimated effort: 17-26 hours**

---

## Testing Strategy

Each feature includes:
1. **Unit tests** — Isolated class/function tests
2. **Integration tests** — With mock dependencies
3. **E2E tests** — Full flow (Phase 1 items)

Test files:
- `trading/tests/unit/test_risk/test_portfolio_drawdown.py`
- `trading/tests/unit/test_risk/test_correlation_gate.py`
- `trading/tests/unit/test_learning/test_consecutive_losses.py`
- `trading/tests/unit/test_exits/test_theta_decay.py`
- `trading/tests/unit/test_agents/test_concurrency.py`

---

## Rollback Strategy

All features are **opt-in via YAML config**. To disable:

1. **Remove from risk.yaml**:
   ```yaml
   risk:
     rules:
       # - type: portfolio_drawdown_kill  # Comment out to disable
       # - type: correlation_gate
   ```

2. **Remove from agents.yaml**:
   ```yaml
   agents:
     - name: momentum_trader
       # htf_filter: "4h"  # Comment out to disable
   ```

3. **Database rollback** (if needed):
   ```sql
   ALTER TABLE performance_snapshots 
   DROP COLUMN IF EXISTS consecutive_losses,
   DROP COLUMN IF EXISTS max_consecutive_losses,
   DROP COLUMN IF EXISTS consecutive_wins,
   DROP COLUMN IF EXISTS max_consecutive_wins;
   
   DROP TABLE IF EXISTS portfolio_state;
   ```

4. **Feature flag** (alternative):
   ```yaml
   features:
     portfolio_kill_switch: false
     correlation_gate: false
     htf_filter: false
   ```

---

## Migration Files

All migrations go in `scripts/migrations/`:
- `add-portfolio-state.sql` — Portfolio state persistence table
- `add-streak-tracking.sql` — Consecutive loss/win tracking columns

Run migrations:
```bash
docker exec agent-memory-unified-postgres-1 psql -U postgres -d agent_memory < scripts/migrations/add-portfolio-state.sql
docker exec agent-memory-unified-postgres-1 psql -U postgres -d agent_memory < scripts/migrations/add-streak-tracking.sql
```

---

## References

- go-trader repo: https://github.com/richkuo/go-trader
- Current RiskEngine: `trading/risk/engine.py`
- Current StrategyHealth: `trading/learning/strategy_health.py`
- Current ExitRules: `trading/exits/rules.py`
- Current DataBus: `trading/data/bus.py`
- Current AgentRunner: `trading/agents/runner.py`
- ServiceContainer: `trading/api/container.py`
