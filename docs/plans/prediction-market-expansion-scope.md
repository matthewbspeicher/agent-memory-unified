# Prediction Market Strategy Expansion — Scope Document

**Date:** 2026-04-14  
**Status:** Scoped — Awaiting implementation approval  
**Author:** Sisyphus  

---

## Executive Summary

Five new prediction market strategies to exploit information asymmetries, structural inefficiencies, and execution gaps. All strategies conform to the existing `Agent` / `StructuredAgent` base class, `Opportunity` model, `agents.yaml` registration pattern, and `DataBus` data source injection. Three are pure `scan()` agents (like existing strategies), one is a background service, and one modifies the execution layer.

| # | Strategy | Type | Estimated Edge | Legal Risk |
|---|----------|------|---------------|------------|
| 1 | Resolution Edge Engine | Scan agent | **Highest** (5–15¢ per contract) | None |
| 2 | Social Alpha Pipeline | Scan agent | Medium (2–8¢ via speed) | Low |
| 3 | New Market Sniping | Scan agent | Medium (3–10¢ via early entry) | None |
| 4 | Market Making (LP) | Background service | Steady (bid-ask spread) | Low |
| 5 | Slippage-Aware Execution | Execution layer mod | Amplifier for all above | None |

---

## Architecture Conventions (All Strategies)

Every strategy follows these existing patterns:

```python
# Pattern: All strategies extend Agent or StructuredAgent
class NewAgent(StructuredAgent):
    description = "..."
    
    async def scan(self, data: DataBus) -> list[Opportunity]:
        # Access injected data sources from DataBus
        source = getattr(data, "_<platform>_source", None)
        if not source:
            return []
        # ... logic ...
        return [Opportunity(...)]
```

```yaml
# Pattern: agents.yaml registration
- name: new_strategy_name
  strategy: new_strategy_module
  schedule: cron          # or "continuous"
  cron: "*/15 * * * *"
  action_level: suggest_trade  # or "auto_execute" when ready
  parameters:
    threshold_cents: 10
    # ...
```

```python
# Pattern: Broker routing via Opportunity.broker_id
opportunity = Opportunity(
    id=str(uuid4()),
    agent_name=self.name,
    symbol=Symbol(ticker=ticker, asset_type=AssetType.PREDICTION, exchange="polymarket"),
    signal="resolution_edge",
    confidence=0.92,
    reasoning="...",
    data={...},
    timestamp=datetime.now(timezone.utc),
    status=OpportunityStatus.PENDING,
    suggested_trade=LimitOrder(...),
    broker_id="polymarket",  # or "kalshi"
)
```

---

## 1. Resolution Edge Engine

### Concept

When a prediction market's **resolution source** has effectively decided the outcome, but the market price hasn't yet moved, there's a free-money window. Examples:

- AP calls the election → market still at 85¢ YES
- Fed releases FOMC statement → "rate hike" market still at 60¢
- Senate vote tally is final → market still at 75¢ YES

This is **the highest-edge, lowest-risk strategy** on prediction markets. The outcome is already known by the resolution source, but the market hasn't caught up.

### Implementation Scope

**New files:**
- `trading/strategies/resolution_edge.py` — ResolutionEdgeAgent (StructuredAgent)
- `trading/data/sources/resolution_monitor.py` — ResolutionSourceMonitor (DataSource)

**Modified files:**
- `trading/data/bus.py` — inject `_resolution_source` attribute
- `trading/api/startup/integrations.py` — wire up ResolutionSourceMonitor
- `trading/agents.yaml` — register agent

### ResolutionEdgeAgent Design

```python
class ResolutionEdgeAgent(StructuredAgent):
    """
    Detects markets where the resolution source has already decided the outcome
    but the market price hasn't converged.
    
    Sources monitored:
    - AP News (Election calls)
    - Federal Reserve (FOMC decisions)
    - C-SPAN (Vote tallies)
    - NOAA (Weather events)
    - Congressional Record (Bill passage)
    """
    description = "Exploits gap between resolution-source certainty and market price."
    
    async def scan(self, data: DataBus) -> list[Opportunity]:
        # 1. Get resolution events from monitor
        # 2. Match events to open markets (fuzzy title match)
        # 3. Calculate: if resolution_source says YES with certainty P>0.95,
        #    but market is at price < 0.90, that's a 5+ cent edge
        # 4. Emit Opportunity with confidence based on:
        #    - source reliability score
        #    - time since source confirmed
        #    - market liquidity (min_volume check)
        pass
```

### ResolutionSourceMonitor Design

```python
class ResolutionSourceMonitor(DataSource):
    """
    Monitors authoritative resolution sources for predetermined outcomes.
    
    Sources (ordered by reliability):
    1. AP Election Calls (RSS) — official election callers
    2. C-SPAN Transcript Parser — live vote tallies
    3. FOMC Statement Parser — Fed decisions
    4. NOAA Weather Alerts — weather markets
    5. Congress.gov API — bill status changes
    
    Each source gets a reliability_score (0-1) used to weight confidence.
    """
    
    async def get_resolution_events(self) -> list[ResolutionEvent]:
        """Returns events where resolution source has decided the outcome."""
        pass
    
    async def get_source_reliability(self, source: str) -> float:
        """Historical accuracy of each resolution source."""
        pass
```

### ResolutionEvent Model

```python
@dataclass
class ResolutionEvent:
    event_title: str           # "2024 Presidential Election"
    resolution_source: str     # "ap_election", "cspan_vote", "fomc", "noaa"
    resolution_value: str      # "YES" or "NO"
    certainty: float           # 0.0-1.0 (1.0 = source has called it)
    timestamp: datetime
    source_url: str | None
    related_keywords: list[str]  # for fuzzy matching to market titles
    reliability: float         # historical source accuracy
```

### agents.yaml Entry

```yaml
- name: resolution_edge
  strategy: resolution_edge
  schedule: cron
  cron: "*/5 * * * *"   # every 5 minutes — speed matters
  action_level: suggest_trade
  parameters:
    min_certainty: 0.90          # resolution source must be 90%+ certain
    min_edge_cents: 5             # minimum gap between source and market
    min_volume: 200
    max_markets_per_scan: 30
    source_reliability_min: 0.85  # only use sources with >85% historical accuracy
    resolution_sources:
      - ap_election
      - cspan_vote
      - fomc
      - noaa_weather
      - congress_bill
```

### Why This Works

- Resolution sources are **public information** — no insider trading concern
- The gap exists because most prediction market participants are retail and don't monitor resolution sources in real time
- The edge is time-decaying: early movers capture the most (hence the 5-minute scan interval)
- Resolution source reliability scoring prevents false positives from unreliable sources

### Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Source misreads event | Reliability scoring per source; require certainty > 0.90 |
| Market resolves differently than source suggests | This is extremely rare for official sources (AP, FOMC); fallback to human review for low-reliability sources |
| Fuzzy match matches wrong market | `min_match_similarity` threshold (0.75+); manual review for low-similarity matches |
| Speed competition from other bots | 5-minute scan is fast enough; most retail traders can't respond in this window |

---

## 2. Social Alpha Pipeline

### Concept

Public information that moves prediction markets is often available hours or days before the market reacts. Examples:

- Congressional stock trade disclosures (legally public, published on House/Senate websites)
- Lobbyist filings ( FEC.gov, Senate public records)
- Regulatory comment periods (Federal Register)
- Corporate earnings pre-announcements (SEC filings)
- Executive orders and agency rulemaking (Federal Register API)

The existing `social_alpha_scout.py` script is **not wired into the trading loop** — it's a standalone script that uses `opencli-rs` for Twitter sentiment. The Social Alpha Pipeline turns this into a fully integrated strategy agent with structured data sources.

### Implementation Scope

**New files:**
- `trading/strategies/social_alpha.py` — SocialAlphaAgent (StructuredAgent)
- `trading/data/sources/congressional_trades.py` — CongressionalTradeSource
- `trading/data/sources/federal_register.py` — FederalRegisterSource
- `trading/data/sources/sec_filings.py` — SECFilingsSource

**Modified files:**
- `trading/data/bus.py` — inject `_congressional_source`, `_fed_register_source`, `_sec_source`
- `trading/api/startup/integrations.py` — wire up data sources
- `trading/agents.yaml` — register agent

### SocialAlphaAgent Design

```python
class SocialAlphaAgent(StructuredAgent):
    """
    Detects alpha from public-but-slow-to-propagate information sources.
    
    Each source monitors a specific public data stream:
    - Congressional stock trades (House/Senate disclosure feeds)
    - Federal Register (new rules, executive orders)
    - SEC filings (8-K, 10-K, 13-F)
    - Lobbyist registrations (OpenSecrets API)
    
    When information is found, the agent:
    1. Determines which prediction markets are affected
    2. Estimates the LLM-derived probability shift
    3. Compares to current market price
    4. Emits Opportunity if gap exceeds threshold
    """
    description = "Exploits slow diffusion of public information in prediction markets."
    
    async def scan(self, data: DataBus) -> list[Opportunity]:
        # 1. Gather fresh events from all configured sources
        # 2. For each event, use LLM to assess probability impact
        # 3. Fuzzy-match affected markets on Kalshi/Polymarket
        # 4. Compare LLM-derived probability to market price
        # 5. Emit Opportunity when gap > threshold
        pass
```

### Data Source Design

```python
class CongressionalTradeSource(DataSource):
    """
    Monitors congressional stock trade disclosures.
    
    Sources:
    - House: https://disclosures-clerk.house.gov/public_disc/financial-search
    - Senate: https://efd.senate.gov/search/
    - Capitol Trades API (if available)
    
    Key data: who traded, what asset, buy/sell, amount range, transaction date
    """
    async def get_recent_trades(self, hours: int = 24) -> list[CongressionalTrade]:
        pass

class FederalRegisterSource(DataSource):
    """
    Monitors Federal Register for new rules, executive orders, and agency actions.
    API: https://www.federalregister.gov/developers/api
    """
    async def get_recent_documents(self, hours: int = 24) -> list[FederalRegisterDoc]:
        pass

class SECFilingsSource(DataSource):
    """
    Monitors SEC EDGAR for 8-K, 10-K, 13-F filings.
    Uses SEC EDGAR full-text search API.
    """
    async def get_recent_filings(self, hours: int = 24, form_types: list[str] = None) -> list[SECFiling]:
        pass
```

### agents.yaml Entry

```yaml
- name: social_alpha
  strategy: social_alpha
  schedule: cron
  cron: "*/30 * * * *"   # every 30 minutes
  action_level: suggest_trade
  parameters:
    threshold_cents: 10
    min_confidence: 55
    min_volume: 200
    max_markets_per_scan: 20
    lookback_hours: 24
    sources:
      - congressional_trades
      - federal_register
      - sec_filings
    llm_model: claude-sonnet-4-6  # for probability assessment
    max_llm_calls_per_scan: 3
```

### Legal Assessment

All sources are **publicly available by law**:
- Congressional trades: Required by STOCK Act (2012), published on government websites
- Federal Register: Official government publication
- SEC filings: Public records by design
- Lobbyist registrations: Required public disclosures

**No insider trading concern.** This is information arbitrage — the same information is available to anyone, but most market participants aren't monitoring these sources systematically.

---

## 3. New Market Sniping

### Concept

When a new market opens on Kalshi or Polymarket, the initial price is set by the platform or early market makers. This price is often **significantly off** the true probability because:

1. No price discovery has occurred yet
2. Liquidity is thin — early orders determine the price
3. Early participants are often retail with less sophisticated models
4. The platform seed price is sometimes arbitrary

The strategy: detect newly opened markets within seconds/minutes, run a quick LLM probability assessment, and place early limit orders at favorable prices.

### Implementation Scope

**New files:**
- `trading/strategies/new_market_sniper.py` — NewMarketSniperAgent (StructuredAgent)
- `trading/data/market_watchdog.py` — MarketWatchdogService (background)

**Modified files:**
- `trading/data/bus.py` — inject `_market_watchdog`
- `trading/api/startup/integrations.py` — wire up watchdog
- `trading/agents.yaml` — register agent

### NewMarketSniperAgent Design

```python
class NewMarketSniperAgent(StructuredAgent):
    """
    Detects newly opened markets and places early limit orders at favorable prices.
    
    Flow:
    1. MarketWatchdogService monitors for new market listings (via WebSocket or polling)
    2. On new market detection, agent is triggered
    3. LLM assesses probability based on market title and description
    4. If LLM probability differs from initial market price by > threshold:
       - Place limit order at favorable price
       - Set tight expiration (market may correct quickly)
    """
    description = "Snipes favorable prices on newly opened prediction markets."
    
    async def scan(self, data: DataBus) -> list[Opportunity]:
        # 1. Get recently opened markets from watchdog
        # 2. Evaluate each with LLM (fast model for speed)
        # 3. Compare LLM probability to current orderbook midpoint
        # 4. If gap > threshold, emit Opportunity with tight expiration
        pass
```

### MarketWatchdogService Design

```python
class MarketWatchdogService:
    """
    Background service that monitors for new market listings.
    
    Two detection modes:
    1. WebSocket (preferred) — Polymarket CLOB has real-time feeds
    2. Polling (fallback) — Poll Kalshi/Polymarket market lists every 60s
       and compare against known market set
    
    Emit events:
    - market.new_listed → triggers NewMarketSniperAgent
    """
    
    async def run(self) -> None:
        """Background loop. Started during app lifespan."""
        pass
    
    def get_new_markets(self, since: datetime) -> list[MarketListing]:
        """Returns markets opened since the given timestamp."""
        pass
```

### agents.yaml Entry

```yaml
- name: new_market_sniper
  strategy: new_market_sniper
  schedule: continuous    # triggered by watchdog events
  interval: 30
  action_level: suggest_trade
  parameters:
    threshold_cents: 10
    min_confidence: 65
    max_new_markets_per_scan: 10
    max_age_minutes: 30     # only snipe markets < 30 minutes old
    llm_model: claude-sonnet-4-6
    max_llm_calls_per_scan: 5
    order_ttl_minutes: 15    # limit orders expire in 15 minutes
    platforms:
      - polymarket
      - kalshi
```

### Key Design Decisions

1. **Speed vs. accuracy trade-off** — Use a fast LLM (Haiku/Sonnet) for probability assessment. A slightly-wrong early order at 60¢ is still profitable if the true probability is 80¢.
2. **Limit orders only** — Never market orders on new markets; the spread is too wide.
3. **Tight expiration** — Don't leave orders open; the market corrects quickly.
4. **Watchdog decoupling** — The detection service runs independently; the agent just queries `get_new_markets()`.

---

## 4. Market Making (Liquidity Provision)

### Concept

Instead of taking liquidity (current approach), provide it. On prediction markets, the bid-ask spread is the market maker's profit. Current spreads on Polymarket and Kalshi are often 2-5 cents wide — significant edge for automated market making.

The strategy:
1. Maintain a calibrated probability estimate for a set of markets
2. Place limit orders on both sides: BUY at (estimate - half_spread), SELL at (estimate + half_spread)
3. Collect the spread as profit
4. Rebalance as new information arrives

### Implementation Scope

**New files:**
- `trading/strategies/prediction_market_maker.py` — PredictionMarketMakerAgent (StructuredAgent)
- `trading/execution/market_making/manager.py` — MarketMakingManager (background service)
- `trading/execution/market_making/inventory_manager.py` — InventoryManager
- `trading/execution/market_making/spread_calculator.py` — SpreadCalculator

**Modified files:**
- `trading/api/startup/integrations.py` — start MarketMakingManager
- `trading/agents.yaml` — register agent

### PredictionMarketMakerAgent Design

```python
class PredictionMarketMakerAgent(StructuredAgent):
    """
    Provides liquidity on prediction markets by maintaining tight bid-ask spreads
    around calibrated probability estimates.
    
    Unlike taker strategies (news arb, calibration), this agent provides liquidity.
    Profit comes from the spread, not directional bets.
    
    Inventory management:
    - Tracks position sizes per market
    - Widens quotes when inventory is too large (adverse selection protection)
    - Skews quotes to reduce inventory (lean against position)
    """
    description = "Market making on prediction markets via calibrated spread provision."
    
    async def scan(self, data: DataBus) -> list[Opportunity]:
        # 1. Get markets where we want to provide liquidity
        # 2. For each, compute calibrated probability (LLM + calibration sources)
        # 3. Calculate optimal bid/ask prices around estimate
        # 4. Check inventory — widen/skew if position size exceeds limits
        # 5. Emit BOTH buy and sell Opportunities (market making is two-sided)
        pass
```

### SpreadCalculator Design

```python
class SpreadCalculator:
    """
    Computes optimal bid-ask spread based on:
    - Base spread (configurable, e.g. 2 cents)
    - Inventory risk premium (widen when position is large)
    - Market volatility (widen in volatile markets)
    - Competition ( tighten if other makers are present)
    """
    
    def compute_quotes(
        self,
        fair_value: Decimal,       # our probability estimate
        position: Decimal,         # current inventory (positive = long)
        max_position: Decimal,      # maximum desired position
        base_spread: Decimal,       # minimum spread (e.g., 2 cents)
        market_volatility: float,   # recent price volatility
        competition_spread: Decimal | None,  # best competing spread
    ) -> tuple[Decimal, Decimal]:
        """Returns (bid_price, ask_price)."""
        pass
```

### agents.yaml Entry

```yaml
- name: prediction_market_maker
  strategy: prediction_market_maker
  schedule: cron
  cron: "*/2 * * * *"    # every 2 minutes — market making needs frequent updates
  action_level: auto_execute   # market making requires auto-execution; no human review
  parameters:
    max_markets: 20
    base_spread_cents: 3
    min_spread_cents: 1
    max_position_per_market: 500    # max USD position per market
    max_total_position: 5000         # max total USD across all markets
    inventory_skew_factor: 0.5      # how much to skew when inventory > 50%
    min_volume: 200
    rebalance_threshold_pct: 10     # rebalance when price moves > 10% from quote
    platforms:
      - polymarket
      - kalshi
    use_calibration_sources: true    # use Metaculus/Manifold for fair value
```

### Key Design Decisions

1. **Start with `suggest_trade`**, graduate to `auto_execute` only after paper trading proves the P&L
2. **Inventory management is critical** — without it, you're just taking directional risk
3. **Two-sided Opportunities** — Market making emits both BUY and SELL opportunities for the same market
4. **Use existing calibration sources** (Metaculus/Manifold) for fair value estimation to avoid reinventing probability models

### Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Adverse selection (informed traders pick off stale quotes) | Inventory skew + position limits + rapid quote updates |
| Inventory buildup on one side | Max position per market; lean-against-position quote adjustment |
| Platform fees eat spread | CostModel already accounts for fees; `min_spread_cents` must exceed total taker fees |
| Regulatory concerns about market manipulation | Market making is explicitly encouraged by both Kalshi and Polymarket; it's provision of legitimate liquidity |

---

## 5. Slippage-Aware Execution

### Concept

Current execution uses `ArbCoordinator` for dual-leg arbitrage and direct `LimitOrder` placement for single-platform strategies. Neither optimizes for execution quality or minimizes market impact.

For prediction markets with thin orderbooks, a market order can move the price 5-10cents — destroying the edge entirely. This strategy modifies the execution layer to:

1. **Slice large orders** into smaller pieces across time and price levels
2. **Route to the venue with best liquidity** (Polymarket vs Kalshi for same-event markets)
3. **Use IOC (Immediate or Cancel)** for testing the book before committing
4. **Adapt order size** based on real-time orderbook depth

### Implementation Scope

**New files:**
- `trading/execution/smart_router.py` — SmartOrderRouter
- `trading/execution/order_slicer.py` — OrderSlicer

**Modified files:**
- `trading/execution/arb_executor.py` — use SmartOrderRouter instead of direct broker calls
- `trading/execution/arbitrage.py` — ArbCoordinator uses SmartOrderRouter for leg execution
- `trading/strategies/cross_platform_arb.py` — inject SmartOrderRouter

### SmartOrderRouter Design

```python
class SmartOrderRouter:
    """
    Intelligent order routing that minimizes market impact and slippage.
    
    Capabilities:
    1. Pre-trade analysis: estimate slippage from orderbook depth
    2. Order slicing: split large orders into smaller pieces
    3. Smart venue selection: route to the exchange with best liquidity
    4. Adaptive pacing: vary order timing based on market conditions
    5. Real-time fill tracking: adjust remaining slices based on fills
    
    Integrates with existing CostModel for fee-aware routing.
    """
    
    def __init__(
        self,
        brokers: dict[str, Broker],
        cost_model: CostModel,
        max_slice_pct: float = 0.10,      # each slice is ≤ 10% of available depth
        slice_interval_seconds: float = 2.0,  # wait between slices
        max_slippage_cents: float = 3.0,      # abort if slippage exceeds this
    ):
        pass
    
    async def execute(
        self,
        symbol: Symbol,
        side: OrderSide,
        quantity: Decimal,
        target_price: Decimal | None = None,  # our fair value; used for smart pricing
        urgency: str = "normal",   # "low" | "normal" | "high"
        venue_preference: str | None = None,   # force specific venue
    ) -> list[OrderResult]:
        """
        Execute an order with minimal market impact.
        
        Returns list of OrderResult from individual slices.
        If target_price is provided, will use limit orders near that price.
        If urgency is "high", executes faster with more aggressive pricing.
        """
        pass
    
    async def estimate_slippage(
        self,
        symbol: Symbol,
        side: OrderSide,
        quantity: Decimal,
        venue: str | None = None,
    ) -> SlippageEstimate:
        """
        Pre-trade slippage estimate based on orderbook depth.
        
        Returns:
        - expected_avg_price: weighted average fill price
        - expected_slippage_cents: difference from mid price
        - available_liquidity: total depth on relevant side
        - recommended_slice_count: how many slices to use
        """
        pass
```

### OrderSlicer Design

```python
class OrderSlicer:
    """
    Splits a large order into smaller slices that minimize market impact.
    
    Strategies:
    - TWAP (Time-Weighted Average Price): even slices over time
    - VWAP-alike: larger slices when book is deeper
    - Aggressive: faster execution for urgent orders
    """
    
    def compute_slices(
        self,
        total_quantity: Decimal,
        orderbook_depth: list[tuple[Decimal, Decimal]],  # [(price, size), ...]
        side: OrderSide,
        max_slice_pct: float = 0.10,    # each slice ≤ 10% of level depth
        urgency: str = "normal",
    ) -> list[OrderSlice]:
        """
        Compute optimal order slices based on orderbook depth.
        
        Each slice specifies:
        - quantity
        - limit_price (based on book level)
        - time_delay (seconds to wait before placing)
        """
        pass
```

### Integration Points

```python
# In ArbCoordinator — replace direct broker.submit_order()
# BEFORE:
result = await broker.submit_order(order)

# AFTER:
results = await self._smart_router.execute(
    symbol=order.symbol,
    side=order.side,
    quantity=order.quantity,
    target_price=trade.expected_entry_price,
    urgency="high",  # arb needs fast execution
)
```

### Not an agents.yaml entry

This is **not a separate agent** — it's an execution layer enhancement that all existing agents benefit from. The `SmartOrderRouter` is injected into `ArbCoordinator` and can be used by any strategy that places orders.

### Phased Implementation

| Phase | Scope | Impact |
|-------|-------|--------|
| Phase 1 | `OrderSlicer` only — static slicing with configurable slice count | Reduces slippage on large orders by 30-50% |
| Phase 2 | `SmartOrderRouter` — slippage estimation, venue selection, adaptive pacing | Full smart routing with pre-trade analysis |
| Phase 3 | Orderbook depth integration — real-time depth from Polymarket/Kalshi WebSocket feeds | Dynamic slicing based on live book state |

---

## Implementation Priority

Based on edge magnitude × implementation complexity × legal risk:

| Priority | Strategy | Rationale |
|----------|----------|-----------|
| **P0** | Resolution Edge Engine | Highest edge, lowest risk, builds on existing patterns. Fastest to implement (2 new files). |
| **P1** | Slippage-Aware Execution (Phase 1) | Force multiplier for ALL existing strategies. Phase 1 (OrderSlicer only) is simple and immediately useful. |
| **P2** | Social Alpha Pipeline | Medium edge, medium complexity. Requires 3 new data sources. Legal green light on all sources. |
| **P3** | New Market Sniping | Medium edge, requires WebSocket/polling infrastructure. Watchdog service adds complexity. |
| **P4** | Market Making | Highest complexity (inventory management, two-sided quoting, position limits). Start with paper trading only. |
| **P5** | Slippage-Aware Execution (Phase 2-3) | Full smart router with orderbook integration. Depends on Phase 1 being live. |

## Dependency Map

```
Resolution Edge ──────────────────────────────────→ Independent
Social Alpha Pipeline ────────────────────────────→ Independent
New Market Sniping ──→ MarketWatchdogService ────→ Independent
Market Making ────────→ SpreadCalculator ─────────→ Independent
                                                      │
Slippage-Aware (Phase 1) ──→ OrderSlicer ────────────→ Independent
Slippage-Aware (Phase 2) ──→ SmartOrderRouter ──────→ Needs Phase 1
Slippage-Aware (Phase 3) ──→ Orderbook integration → Needs Phase 2 + WS feeds
```

## New Files Summary

| Strategy | New Files | Modified Files |
|----------|-----------|---------------|
| Resolution Edge | `strategies/resolution_edge.py`, `data/sources/resolution_monitor.py` | `data/bus.py`, `api/startup/integrations.py`, `agents.yaml` |
| Social Alpha | `strategies/social_alpha.py`, `data/sources/congressional_trades.py`, `data/sources/federal_register.py`, `data/sources/sec_filings.py` | `data/bus.py`, `api/startup/integrations.py`, `agents.yaml` |
| Market Sniping | `strategies/new_market_sniper.py`, `data/market_watchdog.py` | `data/bus.py`, `api/startup/integrations.py`, `agents.yaml` |
| Market Making | `strategies/prediction_market_maker.py`, `execution/market_making/manager.py`, `execution/market_making/inventory_manager.py`, `execution/market_making/spread_calculator.py` | `api/startup/integrations.py`, `agents.yaml` |
| Slippage-Aware | `execution/smart_router.py`, `execution/order_slicer.py` | `execution/arb_executor.py`, `execution/arbitrage.py`, `strategies/cross_platform_arb.py` |

## Total Estimated Effort

| Strategy | New LOC | Complexity | Days |
|----------|---------|-----------|------|
| Resolution Edge | ~400 | Medium | 3-4 |
| Social Alpha Pipeline | ~600 | Medium-High | 5-7 |
| New Market Sniping | ~350 | Medium | 3-4 |
| Market Making | ~800 | High | 7-10 |
| Slippage-Aware (Phase 1) | ~250 | Medium | 2-3 |
| Slippage-Aware (Phase 2-3) | ~500 | High | 5-7 |
| **Total** | **~2,900** | | **25-35** |

---

## Legal & Compliance Notes

All five strategies use **publicly available information only**:

1. **Resolution sources** — AP, C-SPAN, FOMC, NOAA, Congress.gov are all public by law
2. **Social alpha** — Congressional trades (STOCK Act), Federal Register, SEC filings are legally public
3. **Market sniping** — No privileged access; just fast detection of public market listings
4. **Market making** — Explicitly encouraged by both Kalshi and Polymarket
5. **Slippage-aware execution** — Pure execution optimization, no information advantage

**Nothing in this scope constitutes insider trading or market manipulation.** The CFTC has clear guidance that using publicly available information to trade event contracts is legal. Market making is a regulated activity that both platforms explicitly encourage through maker rebates (Polymarket) and reduced fees (Kalshi).