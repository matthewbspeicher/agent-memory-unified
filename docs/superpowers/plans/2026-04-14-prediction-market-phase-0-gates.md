# Prediction Market Expansion — Phase 0 Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## ✅ CLOSE-OUT 2026-04-15

All six Phase 0 tasks shipped. Reconciliation run on 2026-04-15 confirmed:

| Task | Status | Verification |
|------|--------|-------------|
| 1 — Orderbook-price gap in `CrossPlatformArbAgent` | ✅ Done | `cross_platform_arb.py:101-135` + 8 unit tests green (commits `1b28488`, `efa7262`, `f3a4e4c`) |
| 2 — Backtest harness (`backtest/metrics.py`, `prediction_market.py`) | ✅ Done | Modules present 2026-04-14; `tests/unit/test_backtest/` green |
| 3 — Per-agent LLM daily budget cap | ✅ Done | `CostLedger.check_agent_budget` + `LLMClient.for_agent`/`is_over_budget`/`set_agent_budgets`; `config.llm.agent_budgets` wired; `app.py:1086` lifespan call; 5 `test_cost_ledger_agent_cap.py` tests green (commit `bb05be1`) |
| 4 — ADR-0010 Strategy Graduation Gate | ✅ Done | `docs/adr/0010-strategy-graduation-gate.md` |
| 5 — `PortfolioCap` risk gate | ✅ Done | `trading/risk/portfolio_cap.py`; tests green |
| 6 — `KillSwitchGuard` in StructuredAgent base | ✅ Done | `trading/strategies/base_guards.py`; `test_base_guards.py` green |

Full unit suite: **2535 passed, 1 skipped, 0 failed** on 2026-04-15.

Phase 1 strategy plans (Resolution Edge, Social Alpha, New-Market Sniping) are now unblocked.

---

**Goal:** Land the six gating artifacts that any new prediction-market strategy requires — starting with closing the orderbook-price gap that is blocking the existing cross-platform arb from firing trades.

**Architecture:** Six independent tasks that each produce a working, committable change. No new strategies in this plan; those follow in Phase 1+ plans once Phase 0 is live. Every task follows TDD: failing test → minimal implementation → passing test → commit.

**Tech Stack:** Python 3.13 (trading engine), pytest, FastAPI, Redis (CostLedger), PostgreSQL (spread store / agent registry), SQLAlchemy, httpx (Kalshi + Polymarket clients), py-clob-client (Polymarket SDK).

**Prerequisite:** The in-flight arb-unblock commit (Kalshi `/events` + Polymarket `gamma-api` migration) must land on `main` before Task 1 starts. All task code assumes `CrossPlatformArbAgent.scan()` is already fetching events, not markets.

**Out of scope (explicitly deferred to follow-up plans):**
- Resolution Edge Engine, Social Alpha Pipeline, New Market Sniping (each needs its own plan post-backtest)
- Market Making (removed per review — needs 6+ months of live taker experience first, then separate proposal)
- SmartOrderRouter Phase 2/3 (depends on Phase 1 OrderSlicer landing first)

**Parent scope doc:** `docs/plans/prediction-market-expansion-scope.md`
**Review findings memory:** `project_prediction_market_expansion_scope.md`

---

## File Structure

```
trading/
├── strategies/
│   └── cross_platform_arb.py                  # MODIFY Task 1 — orderbook fetch
├── strategies/
│   └── base_guards.py                         # CREATE Task 6 — kill-switch gate
├── agents/
│   └── base.py                                # MODIFY Task 6 — wire guard into scan()
├── llm/
│   ├── cost_ledger.py                         # MODIFY Task 3 — per-agent cap
│   └── client.py                              # MODIFY Task 3 — for_agent honours cap
├── backtest/                                  # CREATE Task 2
│   ├── __init__.py
│   ├── prediction_market.py                   # historical replay engine
│   └── metrics.py                             # Sharpe/hit-rate/drawdown
├── risk/
│   └── portfolio_cap.py                       # CREATE Task 5
├── execution/
│   └── arbitrage.py                           # MODIFY Task 5 — call portfolio cap
├── config.py                                  # MODIFY Task 3+5 — new settings
└── tests/
    ├── unit/test_strategies/
    │   └── test_cross_platform_arb_orderbook.py   # CREATE Task 1
    ├── unit/test_backtest/
    │   ├── __init__.py
    │   ├── test_prediction_market.py              # CREATE Task 2
    │   └── test_metrics.py                        # CREATE Task 2
    ├── unit/test_llm/
    │   └── test_cost_ledger_agent_cap.py          # CREATE Task 3
    ├── unit/test_risk/
    │   └── test_portfolio_cap.py                  # CREATE Task 5
    └── unit/test_agents/
        └── test_base_guards.py                    # CREATE Task 6

docs/adr/
└── 0010-strategy-graduation-gate.md           # CREATE Task 4
```

---

## Task 1: Close the Orderbook-Price Gap in CrossPlatformArbAgent

**Context:** After the arb-unblock commit, `scan()` produces 183 match candidates but 0 opportunities. Root cause: `k_mkt.yes_ask` / `p_mkt.yes_bid` come from the nested-market payload which often has `None` prices (Polymarket `outcomePrices="[null,null]"`, Kalshi stale). Real prices live in the orderbook endpoint. Without this fix, every downstream Phase-0 artifact is unverifiable.

**Files:**
- Modify: `trading/strategies/cross_platform_arb.py:80-114`
- Test: `trading/tests/unit/test_strategies/test_cross_platform_arb_orderbook.py` (create)

- [x] **Step 1: Write the failing test** — landed as `trading/tests/unit/test_strategies/test_cross_platform_arb_orderbook.py` (expanded to 8 cases covering native_market_id, dead-book zero-bid, event-bus publish/swallow, cached-price happy path).

```python
# trading/tests/unit/test_strategies/test_cross_platform_arb_orderbook.py
"""Verifies CrossPlatformArbAgent falls back to live orderbook when nested-market prices are null."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.models import AgentConfig
from strategies.cross_platform_arb import CrossPlatformArbAgent


class _FakeMatcher:
    def __init__(self, pairs):
        self._pairs = pairs

    def __call__(self, k_markets, p_markets, min_score):
        return self._pairs


@pytest.mark.asyncio
async def test_scan_fetches_orderbook_when_nested_prices_are_null(monkeypatch):
    # Kalshi nested market with null prices, orderbook has 55¢/57¢
    k_market = MagicMock(
        ticker="KTICK",
        yes_bid=None,
        yes_ask=None,
        title="US trade deficit for 2026",
        volume_usd_24h=Decimal("500"),
    )
    p_market = MagicMock(
        ticker="PTICK",
        yes_bid=None,
        yes_ask=None,
        title="US Trade Deficit in 2026",
        volume_usd_24h=Decimal("500"),
    )

    kalshi_ds = AsyncMock()
    kalshi_ds.get_markets.return_value = [k_market]
    kalshi_ds.get_quote.return_value = MagicMock(
        bid=Decimal("0.55"), ask=Decimal("0.57")
    )

    polymarket_ds = AsyncMock()
    polymarket_ds.get_markets.return_value = [p_market]
    polymarket_ds.get_quote.return_value = MagicMock(
        bid=Decimal("0.70"), ask=Decimal("0.72")
    )

    # One matched candidate
    candidate = MagicMock(
        kalshi_ticker="KTICK", poly_ticker="PTICK", final_score=1.0
    )
    monkeypatch.setattr(
        "strategies.cross_platform_arb.match_markets",
        _FakeMatcher([candidate]),
    )
    monkeypatch.setattr(
        "strategies.cross_platform_arb.normalize_contract",
        lambda m, platform: MagicMock(volume_usd_24h=Decimal("500")),
    )
    monkeypatch.setattr(
        "strategies.cross_platform_arb.compute_confidence",
        lambda **_: 0.8,
    )

    config = AgentConfig(
        name="cross_platform_arb",
        strategy="cross_platform_arb",
        parameters={"threshold_cents": 8, "min_match_similarity": 0.30},
    )
    agent = CrossPlatformArbAgent(
        config, kalshi_ds=kalshi_ds, polymarket_ds=polymarket_ds, spread_store=None
    )

    opps = await agent.scan(data=MagicMock())

    # Orderbook was consulted for both platforms
    assert kalshi_ds.get_quote.called, "expected live Kalshi orderbook fetch"
    assert polymarket_ds.get_quote.called, "expected live Polymarket orderbook fetch"
    # Gap = |55 - 70| = 15¢, above 8¢ threshold → one opportunity
    assert len(opps) == 1
    assert opps[0].data["gap_cents"] == 15
```

- [x] **Step 2: Run test to verify it fails** — skipped in close-out; implementation landed before this plan was written.

- [x] **Step 3: Modify `scan()` to fall back to the live orderbook** — shipped in commits `1b28488` (native_market_id + orderbook fallback) and `f3a4e4c` (dead-book filter: k_cents/p_cents ≤ 0 rejection + max_gap_cents guard). Current `scan()` at `trading/strategies/cross_platform_arb.py:101-135` covers a superset of the plan's prescribed patch.

Replace `trading/strategies/cross_platform_arb.py:89-93` with:

```python
            # Prefer nested-market cached prices, fall back to live orderbook
            # when either side is None (Polymarket outcomePrices=[null,null] etc.)
            k_cents = k_mkt.yes_ask if k_mkt.yes_ask is not None else k_mkt.yes_bid
            p_cents = p_mkt.yes_bid

            if k_cents is None:
                q = await self.kalshi_ds.get_quote(
                    Symbol(ticker=cand.kalshi_ticker, asset_type=AssetType.PREDICTION)
                )
                if q is not None and q.ask is not None:
                    k_cents = int(q.ask * 100)
            if p_cents is None:
                q = await self.polymarket_ds.get_quote(
                    Symbol(ticker=cand.poly_ticker, asset_type=AssetType.PREDICTION)
                )
                if q is not None and q.bid is not None:
                    p_cents = int(q.bid * 100)

            if k_cents is None or p_cents is None:
                logger.debug(
                    "cross_platform_arb: skipping %s/%s — no live price after orderbook fetch",
                    cand.kalshi_ticker, cand.poly_ticker,
                )
                continue
```

- [x] **Step 4: Run test to verify it passes** — 19/19 arb unit tests green on 2026-04-15 close-out.

- [x] **Step 5: Run full arb regression suite** — 190 passed, 11 skipped (integration), 0 failed on 2026-04-15.

- [x] **Step 6: Commit** — delivered across `1b28488`, `efa7262`, `f3a4e4c` on 2026-04-14/15.

```bash
git add trading/strategies/cross_platform_arb.py trading/tests/unit/test_strategies/test_cross_platform_arb_orderbook.py
git commit -m "fix(arb): fetch live orderbook when nested-market prices are null

Cross-platform arb produced 183 match candidates but 0 opportunities
because Polymarket outcomePrices often comes back [null,null] and
Kalshi nested yes_bid can be stale. Fall back to get_quote() for
either side when the cached price is missing, then filter pairs
that still lack a live price after the fetch."
```

---

## Task 2: Backtest Harness for Prediction-Market Strategies

**Context:** The parent scope doc claims 2-15¢ edges across five strategies with zero historical evidence. Before any new strategy ships, it must demonstrate Sharpe > 1.0 and hit rate > 55% on ≥12 months of historical data. This task builds the replay engine + metrics calculator. It does not include historical data ingestion — that's a follow-up.

**Files:**
- Create: `trading/backtest/__init__.py`
- Create: `trading/backtest/prediction_market.py`
- Create: `trading/backtest/metrics.py`
- Create: `trading/tests/unit/test_backtest/__init__.py`
- Create: `trading/tests/unit/test_backtest/test_prediction_market.py`
- Create: `trading/tests/unit/test_backtest/test_metrics.py`

- [ ] **Step 1: Write failing test for metrics calculator**

```python
# trading/tests/unit/test_backtest/test_metrics.py
from decimal import Decimal
import pytest
from backtest.metrics import BacktestMetrics, compute_metrics


def test_compute_metrics_all_winners():
    trades = [
        {"pnl_cents": 5, "entry_ts": 1, "exit_ts": 2},
        {"pnl_cents": 3, "entry_ts": 2, "exit_ts": 3},
        {"pnl_cents": 7, "entry_ts": 3, "exit_ts": 4},
    ]
    m = compute_metrics(trades, starting_capital_cents=1000)
    assert m.hit_rate == pytest.approx(1.0)
    assert m.total_pnl_cents == 15
    assert m.max_drawdown_cents == 0


def test_compute_metrics_mixed_with_drawdown():
    trades = [
        {"pnl_cents": 10, "entry_ts": 1, "exit_ts": 2},
        {"pnl_cents": -20, "entry_ts": 2, "exit_ts": 3},
        {"pnl_cents": 5, "entry_ts": 3, "exit_ts": 4},
    ]
    m = compute_metrics(trades, starting_capital_cents=1000)
    assert m.hit_rate == pytest.approx(2 / 3)
    assert m.total_pnl_cents == -5
    # Equity: 1000 → 1010 → 990 → 995; peak 1010, trough 990 → DD 20
    assert m.max_drawdown_cents == 20


def test_compute_metrics_empty_trades():
    m = compute_metrics([], starting_capital_cents=1000)
    assert m.hit_rate == 0.0
    assert m.total_pnl_cents == 0
    assert m.sharpe is None
```

- [ ] **Step 2: Run metrics test to verify it fails**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_backtest/test_metrics.py -v`
Expected: FAIL — `backtest.metrics` module does not exist.

- [ ] **Step 3: Implement metrics**

```python
# trading/backtest/__init__.py
"""Backtest harness for prediction-market strategies."""
```

```python
# trading/backtest/metrics.py
"""Backtest performance metrics (Sharpe, hit rate, drawdown, total P&L)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class BacktestMetrics:
    total_pnl_cents: int
    hit_rate: float
    sharpe: float | None
    max_drawdown_cents: int
    num_trades: int


def compute_metrics(
    trades: Iterable[dict], starting_capital_cents: int
) -> BacktestMetrics:
    trades = list(trades)
    if not trades:
        return BacktestMetrics(
            total_pnl_cents=0, hit_rate=0.0, sharpe=None,
            max_drawdown_cents=0, num_trades=0,
        )

    pnls = [int(t["pnl_cents"]) for t in trades]
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    hit_rate = wins / len(pnls)

    # Sharpe on per-trade returns (no annualization — that's the caller's job)
    if len(pnls) > 1:
        mean = sum(pnls) / len(pnls)
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        stdev = math.sqrt(var)
        sharpe = mean / stdev if stdev > 0 else None
    else:
        sharpe = None

    # Max drawdown on running equity curve
    equity = starting_capital_cents
    peak = equity
    max_dd = 0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)

    return BacktestMetrics(
        total_pnl_cents=total,
        hit_rate=hit_rate,
        sharpe=sharpe,
        max_drawdown_cents=max_dd,
        num_trades=len(pnls),
    )
```

- [ ] **Step 4: Run metrics test to verify it passes**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_backtest/test_metrics.py -v`
Expected: 3 passing.

- [ ] **Step 5: Write failing test for replay engine**

```python
# trading/tests/unit/test_backtest/test_prediction_market.py
from decimal import Decimal
import pytest
from backtest.prediction_market import PredictionMarketBacktest, HistoricalSnapshot


class _StubStrategy:
    """Emits a BUY opportunity at 55¢ whenever price < 60¢."""
    name = "stub"

    async def on_snapshot(self, snap: HistoricalSnapshot):
        if snap.yes_price_cents < 60:
            return [{"ticker": snap.ticker, "side": "BUY", "price_cents": 55, "size": 10}]
        return []


@pytest.mark.asyncio
async def test_replay_executes_strategy_orders_and_settles_at_resolution():
    snapshots = [
        HistoricalSnapshot(ticker="T1", ts=1, yes_price_cents=55),
        HistoricalSnapshot(ticker="T1", ts=2, yes_price_cents=65),
        HistoricalSnapshot(ticker="T1", ts=3, yes_price_cents=100, resolved=True, resolution="YES"),
    ]
    engine = PredictionMarketBacktest(
        strategy=_StubStrategy(),
        snapshots=snapshots,
        starting_capital_cents=1000,
        fee_cents_per_contract=1,
    )
    result = await engine.run()

    # Bought 10 contracts @ 55¢, paid 10 × 1¢ fee, YES resolves @ 100¢
    # P&L = (100 - 55) × 10 - 10 = 440
    assert result.metrics.num_trades == 1
    assert result.metrics.total_pnl_cents == 440
```

- [ ] **Step 6: Run replay test to verify it fails**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_backtest/test_prediction_market.py -v`
Expected: FAIL — `backtest.prediction_market` does not exist.

- [ ] **Step 7: Implement replay engine**

```python
# trading/backtest/prediction_market.py
"""Replay engine for prediction-market strategies against historical snapshots."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from backtest.metrics import BacktestMetrics, compute_metrics


@dataclass(frozen=True)
class HistoricalSnapshot:
    ticker: str
    ts: int
    yes_price_cents: int
    resolved: bool = False
    resolution: str | None = None  # "YES" | "NO"


@dataclass
class BacktestResult:
    metrics: BacktestMetrics
    trades: list[dict] = field(default_factory=list)


class _StrategyLike(Protocol):
    name: str

    async def on_snapshot(self, snap: HistoricalSnapshot) -> list[dict]: ...


class PredictionMarketBacktest:
    """Feeds historical snapshots into a strategy and settles at resolution.

    Simplifications (v0.1):
    - One contract per ticker at any time (no pyramiding)
    - Fills at the snapshot's yes_price_cents (no slippage model yet)
    - YES resolves at 100¢, NO at 0¢
    - Fees applied per contract on entry only
    """

    def __init__(
        self,
        strategy: _StrategyLike,
        snapshots: list[HistoricalSnapshot],
        starting_capital_cents: int,
        fee_cents_per_contract: int = 1,
    ) -> None:
        self._strategy = strategy
        self._snapshots = snapshots
        self._starting = starting_capital_cents
        self._fee = fee_cents_per_contract

    async def run(self) -> BacktestResult:
        open_positions: dict[str, dict] = {}
        closed_trades: list[dict] = []

        for snap in self._snapshots:
            if snap.resolved:
                pos = open_positions.pop(snap.ticker, None)
                if pos is not None:
                    settle_cents = 100 if snap.resolution == "YES" else 0
                    gross = (settle_cents - pos["entry_cents"]) * pos["size"]
                    closed_trades.append({
                        "ticker": snap.ticker,
                        "entry_ts": pos["entry_ts"],
                        "exit_ts": snap.ts,
                        "pnl_cents": gross - pos["fees"],
                    })
                continue

            if snap.ticker in open_positions:
                continue

            orders = await self._strategy.on_snapshot(snap)
            for order in orders:
                if order.get("ticker") != snap.ticker:
                    continue
                size = int(order["size"])
                open_positions[snap.ticker] = {
                    "entry_ts": snap.ts,
                    "entry_cents": int(order["price_cents"]),
                    "size": size,
                    "fees": self._fee * size,
                }

        return BacktestResult(
            metrics=compute_metrics(closed_trades, self._starting),
            trades=closed_trades,
        )
```

- [ ] **Step 8: Run replay test to verify it passes**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_backtest/ -v`
Expected: 4 passing (3 metrics + 1 replay).

- [ ] **Step 9: Commit**

```bash
git add trading/backtest/ trading/tests/unit/test_backtest/
git commit -m "feat(backtest): prediction-market replay engine + metrics

v0.1 replay engine feeds historical snapshots into a strategy,
settles positions at resolution, and produces Sharpe/hit-rate/
drawdown metrics. Gate: any new PM strategy must show Sharpe > 1.0
and hit rate > 55% on 12+ months of data before merge."
```

---

## Task 3: Per-Agent LLM Daily Budget Cap

**Context:** Four of five proposed strategies fire LLM calls on a schedule. The global `CostLedger` already tracks spend, but there is no per-agent cap — a runaway Resolution Edge could starve every other agent. This task adds a per-agent daily cent cap that falls back to rule-based / free providers when hit.

**Files:**
- Modify: `trading/llm/cost_ledger.py` (add `check_agent_budget`)
- Modify: `trading/llm/client.py:247` (`for_agent` consults cap)
- Modify: `trading/config.py` (add `llm_agent_budgets: dict[str, int]`)
- Create: `trading/tests/unit/test_llm/test_cost_ledger_agent_cap.py`

- [ ] **Step 1: Write failing test for `check_agent_budget`**

```python
# trading/tests/unit/test_llm/test_cost_ledger_agent_cap.py
import pytest
from llm.cost_ledger import CostLedger, LLMCostConfig


@pytest.mark.asyncio
async def test_agent_under_cap_returns_ok():
    ledger = CostLedger(
        redis=None,
        config=LLMCostConfig(daily_budget_cents=10000),
    )
    ledger._local["llm:cost:agent:alpha"] = 50.0  # 50 cents spent
    ok = await ledger.check_agent_budget("alpha", cap_cents=100)
    assert ok is True


@pytest.mark.asyncio
async def test_agent_at_cap_returns_not_ok():
    ledger = CostLedger(
        redis=None,
        config=LLMCostConfig(daily_budget_cents=10000),
    )
    ledger._local["llm:cost:agent:alpha"] = 100.0  # 100 cents spent
    ok = await ledger.check_agent_budget("alpha", cap_cents=100)
    assert ok is False


@pytest.mark.asyncio
async def test_agent_without_cap_is_always_ok():
    ledger = CostLedger(
        redis=None,
        config=LLMCostConfig(daily_budget_cents=10000),
    )
    ledger._local["llm:cost:agent:alpha"] = 99999.0
    ok = await ledger.check_agent_budget("alpha", cap_cents=None)
    assert ok is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_llm/test_cost_ledger_agent_cap.py -v`
Expected: FAIL — `check_agent_budget` does not exist.

- [ ] **Step 3: Implement `check_agent_budget` in `CostLedger`**

Append to `trading/llm/cost_ledger.py` (inside the `CostLedger` class):

```python
    async def check_agent_budget(
        self, agent_name: str, cap_cents: int | None
    ) -> bool:
        """Return True if the agent may spend more LLM dollars today.

        When cap_cents is None, no per-agent cap is enforced (always True).
        Consults Redis if available, falls back to in-memory dict.
        """
        if cap_cents is None:
            return True
        key = _KEY_AGENT.format(name=agent_name)
        spent = 0.0
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                spent = float(raw) if raw is not None else 0.0
            except Exception:
                logger.warning(
                    "CostLedger: Redis error during check_agent_budget(); "
                    "falling back to in-memory"
                )
                spent = self._local.get(key, 0.0)
        else:
            spent = self._local.get(key, 0.0)
        return spent < cap_cents
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_llm/test_cost_ledger_agent_cap.py -v`
Expected: 3 passing.

- [ ] **Step 5: Write failing test for `LLMClient.for_agent` carrying a cap**

Append to `trading/tests/unit/test_llm/test_cost_ledger_agent_cap.py`:

```python
@pytest.mark.asyncio
async def test_for_agent_is_over_budget_reflects_cap(monkeypatch):
    """for_agent() scopes the cap; is_over_budget() is the hook call-sites use."""
    from llm.client import LLMClient

    ledger = CostLedger(
        redis=None, config=LLMCostConfig(daily_budget_cents=10000)
    )
    ledger._local["llm:cost:agent:capped_agent"] = 200.0
    ledger._local["llm:cost:agent:under_agent"] = 10.0

    parent = LLMClient.__new__(LLMClient)
    parent._chain = []
    parent._agent_name = None
    parent._cost_ledger = ledger
    parent._notifier = None
    parent._fired_alerts = set()
    parent.registry = None
    parent._fail_counts = {}
    parent._disabled = {}
    parent._max_fails = 5
    parent._agent_budgets = {"capped_agent": 100, "under_agent": 100}

    capped = parent.for_agent("capped_agent")
    under = parent.for_agent("under_agent")
    unknown = parent.for_agent("no_cap_agent")

    assert await capped.is_over_budget() is True
    assert await under.is_over_budget() is False
    # Agent with no entry in agent_budgets has no per-agent cap → never over
    assert await unknown.is_over_budget() is False
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_llm/test_cost_ledger_agent_cap.py::test_for_agent_is_over_budget_reflects_cap -v`
Expected: FAIL — `_agent_budgets` / `is_over_budget()` don't exist.

- [ ] **Step 7: Extend `LLMClient.for_agent` and add `is_over_budget`**

Modify `trading/llm/client.py:247-263`. Replace the existing `for_agent` body with:

```python
    def for_agent(self, agent_name: str) -> "LLMClient":
        """Return a lightweight view that records cost under a different agent name.

        Shares the same registry, chain, circuit breakers, and cost_ledger
        as the parent — only _agent_name and the resolved per-agent cap differ.
        """
        proxy = object.__new__(LLMClient)
        proxy._chain = self._chain
        proxy._agent_name = agent_name
        proxy._cost_ledger = self._cost_ledger
        proxy._notifier = self._notifier
        proxy._fired_alerts = self._fired_alerts
        proxy.registry = self.registry
        proxy._fail_counts = self._fail_counts
        proxy._disabled = self._disabled
        proxy._max_fails = self._max_fails
        proxy._agent_budgets = getattr(self, "_agent_budgets", {})
        proxy._agent_cap_cents = proxy._agent_budgets.get(agent_name)
        return proxy

    async def is_over_budget(self) -> bool:
        """True when this agent has exceeded its per-agent daily LLM cap.

        Call-sites (strategy scan entry points) use this to short-circuit
        LLM-dependent scans when the cap is hit. No cap configured =>
        always False.
        """
        cap = getattr(self, "_agent_cap_cents", None)
        name = getattr(self, "_agent_name", None)
        if cap is None or name is None or self._cost_ledger is None:
            return False
        return not await self._cost_ledger.check_agent_budget(name, cap)
```

Also in the `LLMClient.__init__` (near where `_fail_counts` is initialised, around line 243), add:

```python
        self._agent_budgets: dict[str, int] = {}
```

And expose a setter called by the app startup after loading config:

```python
    def set_agent_budgets(self, budgets: dict[str, int]) -> None:
        """Called once at startup to install STA_LLM_AGENT_BUDGETS values."""
        self._agent_budgets = dict(budgets)
```

- [ ] **Step 8: Run LLM tests**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_llm/ -v`
Expected: All green, including the two new agent-cap tests.

- [ ] **Step 9: Add config wiring**

Modify `trading/config.py` `LLMConfig` dataclass — add:

```python
    # Per-agent daily LLM cap in cents. Keys are agent names from agents.yaml.
    # Unset agents have no per-agent cap (global budget still applies).
    agent_budgets: dict[str, int] = field(default_factory=dict)
```

Env var: `STA_LLM_AGENT_BUDGETS` as JSON, e.g. `'{"resolution_edge":50,"social_alpha":75}'`. In `load_config()`, parse with `json.loads(os.environ.get("STA_LLM_AGENT_BUDGETS", "{}"))` and populate the field.

Then in `trading/api/app.py` lifespan, after the LLMClient is constructed, call:

```python
llm_client.set_agent_budgets(config.llm.agent_budgets)
```

- [ ] **Step 10: Commit**

```bash
git add trading/llm/cost_ledger.py trading/llm/client.py trading/config.py trading/tests/unit/test_llm/test_cost_ledger_agent_cap.py
git commit -m "feat(llm): per-agent daily budget cap with free-provider fallback

Four of the proposed new strategies fire LLM calls on a schedule.
Without a per-agent cap, one runaway agent can drain the global
budget and starve every other. Adds check_agent_budget() to the
ledger and filters paid providers from LLMClient.for_agent()
when the cap is hit. Configured via STA_LLM_AGENT_BUDGETS JSON."
```

---

## Task 4: ADR-0010 — Strategy Graduation Gate

**Context:** `agents.paper.yaml` and `agents.yaml` already exist, but there is no written criteria for promoting a strategy from paper → live. This ADR codifies it so Phase 1+ strategies have a hard gate to clear.

**Files:**
- Create: `docs/adr/0010-strategy-graduation-gate.md`

- [ ] **Step 1: Check the next ADR number is still 0010**

Run: `ls docs/adr/ | sort`
Expected: Highest existing ADR is `0009-*.md`. If not, bump the number in this task.

- [ ] **Step 2: Write the ADR**

```markdown
<!-- docs/adr/0010-strategy-graduation-gate.md -->
# ADR-0010 — Strategy Graduation Gate (Paper → Live)

## Status

Accepted — 2026-04-14

## Context

Strategies in `trading/agents.paper.yaml` run with `action_level: auto_execute` against paper brokers. Strategies in `trading/agents.yaml` can run against live brokers (Kalshi, Polymarket, IBKR). There was no written criteria for promoting a strategy from paper to live.

Absent a gate, strategies graduate based on intuition. The 2026-04-14 prediction-market expansion review surfaced five proposed new strategies with claimed 2-15¢ edges and no backtest evidence — this ADR exists to make that kind of jump impossible going forward.

## Decision

Before a strategy may be added to `trading/agents.yaml` (or have its `action_level` raised to `auto_execute` there), it must satisfy **all** of:

1. **Backtest gate (offline evidence):**
   - ≥12 months of historical data
   - Sharpe ≥ 1.0 (per-trade, not annualised)
   - Hit rate ≥ 55%
   - Max drawdown ≤ 20% of deployed capital
   - Backtest notebook checked into `trading/backtest/notebooks/<strategy>.ipynb`

2. **Paper gate (live-market evidence):**
   - ≥30 calendar days in `agents.paper.yaml` with `action_level: auto_execute`
   - ≥50 filled paper trades
   - Paper Sharpe within 50% of backtest Sharpe (i.e. no severe live degradation)
   - Zero unexplained errors for the last 7 days

3. **Ops gate (risk plumbing):**
   - Strategy calls `KillSwitchRegistry.is_enabled` in `scan()` via the base guard (Task 6)
   - Position sizing honours `STA_PORTFOLIO_MAX_POSITION_USD` (Task 5)
   - Per-agent LLM cap set in `STA_LLM_AGENT_BUDGETS` if the strategy calls the LLM
   - Audit-log event fires on every emitted Opportunity

4. **Review gate:**
   - Written graduation request (ticket or PR description) lists backtest stats, paper stats, and ops-gate checkboxes
   - Reviewed by repo owner before merge

## Consequences

- Strategy proposals that can't pass the backtest gate never get built. This is intentional: the expansion review found multiple proposals (Congressional-trade alpha, Resolution Edge at 5-min polling, Market Making on thin PM books) whose claimed edges don't survive contact with historical data.
- The gate extends delivery time for new strategies by ~30 days (the paper-trading window). This is the point.
- Existing strategies on `agents.yaml` as of 2026-04-14 are grandfathered; the gate applies to new additions and to action-level promotions.

## Related

- `docs/plans/prediction-market-expansion-scope.md` — the proposal that motivated this ADR
- `docs/superpowers/plans/2026-04-14-prediction-market-phase-0-gates.md` — Phase 0 plan including this ADR
- `trading/backtest/prediction_market.py` — backtest harness (Task 2)
- `trading/risk/portfolio_cap.py` — portfolio cap (Task 5)
- `trading/strategies/base_guards.py` — kill-switch guard (Task 6)
```

- [ ] **Step 3: Commit**

```bash
git add docs/adr/0010-strategy-graduation-gate.md
git commit -m "docs(adr): 0010 — strategy graduation gate (paper → live)

Codifies the four-gate promotion criteria for moving a strategy
from agents.paper.yaml to agents.yaml: backtest evidence, paper
evidence, risk-plumbing checks, written review. Motivated by
the prediction-market expansion review which surfaced multiple
proposals with claimed edges unsupported by historical data."
```

---

## Task 5: Portfolio-Level Position Cap

**Context:** Individual strategies already respect `max_position_usd`, but there is no portfolio-level ceiling. Memory pegs personal brokerage at ~$11k; the scope doc proposes $5k MM position alone — half of total capital on an untested strategy. This task wires a portfolio cap into `ArbCoordinator` that every strategy's execution must clear.

**Files:**
- Create: `trading/risk/__init__.py`
- Create: `trading/risk/portfolio_cap.py`
- Modify: `trading/execution/arbitrage.py` (call cap before leg 1)
- Modify: `trading/config.py` (add `portfolio_max_position_usd`)
- Create: `trading/tests/unit/test_risk/__init__.py`
- Create: `trading/tests/unit/test_risk/test_portfolio_cap.py`

- [ ] **Step 1: Write failing test for `PortfolioCap.check`**

```python
# trading/tests/unit/test_risk/test_portfolio_cap.py
from decimal import Decimal
import pytest
from risk.portfolio_cap import PortfolioCap, PortfolioCapExceeded


class _FakeBroker:
    def __init__(self, positions_usd: Decimal):
        self._positions_usd = positions_usd

    async def total_position_usd(self) -> Decimal:
        return self._positions_usd


@pytest.mark.asyncio
async def test_allows_trade_within_cap():
    cap = PortfolioCap(
        max_usd=Decimal("10000"),
        brokers={"kalshi": _FakeBroker(Decimal("2000")),
                 "polymarket": _FakeBroker(Decimal("3000"))},
    )
    # 5000 existing + 1000 proposed = 6000 < 10000
    await cap.check(additional_usd=Decimal("1000"))  # no exception


@pytest.mark.asyncio
async def test_rejects_trade_that_would_exceed_cap():
    cap = PortfolioCap(
        max_usd=Decimal("10000"),
        brokers={"kalshi": _FakeBroker(Decimal("6000")),
                 "polymarket": _FakeBroker(Decimal("4500"))},
    )
    # 10500 existing + 1 proposed = 10501 > 10000
    with pytest.raises(PortfolioCapExceeded):
        await cap.check(additional_usd=Decimal("1"))


@pytest.mark.asyncio
async def test_cap_of_zero_disables_check():
    cap = PortfolioCap(
        max_usd=Decimal("0"),
        brokers={"kalshi": _FakeBroker(Decimal("999999"))},
    )
    await cap.check(additional_usd=Decimal("1000000"))  # no exception
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_risk/test_portfolio_cap.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `PortfolioCap`**

```python
# trading/risk/__init__.py
"""Cross-cutting risk primitives (portfolio cap, kill-switch guards)."""
```

```python
# trading/risk/portfolio_cap.py
"""Portfolio-level position ceiling enforced before any new trade."""
from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class _BrokerLike(Protocol):
    async def total_position_usd(self) -> Decimal: ...


class PortfolioCapExceeded(Exception):
    """Raised when a proposed trade would push portfolio exposure over cap."""


class PortfolioCap:
    """Enforces a single USD ceiling across every wired broker.

    A cap of 0 disables the check (useful for backtests / paper).
    """

    def __init__(
        self, max_usd: Decimal, brokers: dict[str, _BrokerLike]
    ) -> None:
        self._max = max_usd
        self._brokers = brokers

    async def check(self, additional_usd: Decimal) -> None:
        if self._max <= 0:
            return
        total = Decimal("0")
        for b in self._brokers.values():
            total += await b.total_position_usd()
        if total + additional_usd > self._max:
            raise PortfolioCapExceeded(
                f"would push portfolio to ${total + additional_usd} "
                f"(cap ${self._max})"
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_risk/test_portfolio_cap.py -v`
Expected: 3 passing.

- [ ] **Step 5: Wire the cap into `ArbCoordinator.execute_trade`**

In `trading/execution/arbitrage.py`, locate the entry point that starts leg 1 (look for the first `broker.submit_order` call in `execute_trade` / `_execute_leg_1`). Before the submission, add:

```python
from risk.portfolio_cap import PortfolioCap, PortfolioCapExceeded

# At class init:
self._portfolio_cap: PortfolioCap | None = portfolio_cap

# Before leg 1 submission:
if self._portfolio_cap is not None:
    try:
        await self._portfolio_cap.check(
            additional_usd=Decimal(str(trade.leg_1.notional_usd))
        )
    except PortfolioCapExceeded as exc:
        logger.warning(
            "ArbCoordinator: portfolio cap rejected trade %s: %s",
            trade.id, exc,
        )
        trade.state = ArbState.REJECTED
        trade.error_message = f"portfolio_cap: {exc}"
        await self._publish_state(trade)
        return
```

Add `portfolio_cap: PortfolioCap | None = None` to the constructor signature.

- [ ] **Step 6: Add config entry**

In `trading/config.py`, append to `RiskConfig` (or create it if it doesn't already exist):

```python
    # Portfolio-level USD ceiling across all brokers. 0 disables.
    portfolio_max_position_usd: Decimal = Decimal("0")
```

Env var: `STA_RISK_PORTFOLIO_MAX_POSITION_USD`.

- [ ] **Step 7: Run full trading test suite**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/ --tb=short --timeout=30`
Expected: All green.

- [ ] **Step 8: Commit**

```bash
git add trading/risk/ trading/execution/arbitrage.py trading/config.py trading/tests/unit/test_risk/
git commit -m "feat(risk): portfolio-level position cap across all brokers

Per-strategy max_position_usd isn't enough when multiple strategies
can trade the same capital pool. Portfolio cap sums live positions
across every wired broker and rejects trades that would push
exposure over STA_RISK_PORTFOLIO_MAX_POSITION_USD. Cap of 0
disables (backtests / paper). ArbCoordinator calls it before
leg 1."
```

---

## Task 6: Kill-Switch Guard in StructuredAgent Base

**Context:** Per CLAUDE.md working boundaries, `risk:halt` is a load-bearing scope. But strategies call their own `scan()` — nothing stops a strategy from emitting Opportunities while the kill-switch is active. This task wires a base-class guard so every strategy's `scan()` returns `[]` when halted, without per-strategy opt-in.

**Files:**
- Create: `trading/strategies/base_guards.py`
- Modify: `trading/agents/base.py` (call guard from `StructuredAgent.scan_with_guards`)
- Create: `trading/tests/unit/test_agents/test_base_guards.py`

- [ ] **Step 1: Write failing test for guard**

```python
# trading/tests/unit/test_agents/test_base_guards.py
import pytest
from strategies.base_guards import KillSwitchGuard


class _ActiveKillSwitch:
    is_enabled = True
    reason = "manual halt"


class _InactiveKillSwitch:
    is_enabled = False
    reason = None


@pytest.mark.asyncio
async def test_guard_blocks_when_kill_switch_enabled():
    guard = KillSwitchGuard(_ActiveKillSwitch())
    allowed = await guard.allow_scan("any_agent")
    assert allowed is False


@pytest.mark.asyncio
async def test_guard_allows_when_kill_switch_inactive():
    guard = KillSwitchGuard(_InactiveKillSwitch())
    allowed = await guard.allow_scan("any_agent")
    assert allowed is True


@pytest.mark.asyncio
async def test_guard_without_kill_switch_defaults_to_allow():
    guard = KillSwitchGuard(None)
    assert await guard.allow_scan("any_agent") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_agents/test_base_guards.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the guard**

```python
# trading/strategies/base_guards.py
"""Base-class guards that every StructuredAgent runs before scan()."""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class _KillSwitchLike(Protocol):
    is_enabled: bool
    reason: str | None


class KillSwitchGuard:
    """Blocks scan() when the risk kill-switch is active."""

    def __init__(self, kill_switch: _KillSwitchLike | None) -> None:
        self._ks = kill_switch

    async def allow_scan(self, agent_name: str) -> bool:
        if self._ks is None:
            return True
        if getattr(self._ks, "is_enabled", False):
            logger.info(
                "agent.scan_blocked agent=%s reason=%s",
                agent_name, getattr(self._ks, "reason", None),
            )
            return False
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_agents/test_base_guards.py -v`
Expected: 3 passing.

- [ ] **Step 5: Wire the guard into `StructuredAgent`**

In `trading/agents/base.py`, locate `StructuredAgent` (or the closest base). Add:

```python
from strategies.base_guards import KillSwitchGuard


class StructuredAgent(Agent):
    # ... existing code ...

    def _build_guard(self) -> KillSwitchGuard:
        # Subclasses may override; default pulls from self._engine or self._kill_switch
        ks = getattr(self, "_kill_switch", None) or getattr(
            getattr(self, "_engine", None), "kill_switch", None
        )
        return KillSwitchGuard(ks)

    async def scan_with_guards(self, data) -> list:
        guard = self._build_guard()
        if not await guard.allow_scan(self.name):
            return []
        return await self.scan(data)
```

Update the runner (search for callers of `agent.scan(data)` in `trading/agents/runner.py`) to call `scan_with_guards` instead. Keep `scan()` callable directly for tests.

- [ ] **Step 6: Run full agent test suite**

Run: `cd trading && .venv/bin/python -m pytest tests/unit/test_agents/ --tb=short --timeout=30`
Expected: All green. If any test calls `agent.scan()` directly and expects guard behaviour, update to call `scan_with_guards`.

- [ ] **Step 7: Commit**

```bash
git add trading/strategies/base_guards.py trading/agents/base.py trading/agents/runner.py trading/tests/unit/test_agents/test_base_guards.py
git commit -m "feat(agents): kill-switch guard in StructuredAgent base

Every strategy now returns [] from scan_with_guards() when the
risk:halt kill-switch is active. Guard lives in the base so
strategies can't forget to wire it. Runner invokes
scan_with_guards; direct scan() remains available for unit tests."
```

---

## Phase 0 Exit Criteria

All six tasks merged to `main`. Verify:

- [ ] `cd trading && .venv/bin/python -m pytest tests/unit/ --tb=short --timeout=30` → green
- [ ] Smoke-run the arb agent and confirm `opportunities > 0`:
  ```bash
  curl -sS -H "X-API-Key: $STA_API_KEY" -X POST \
    http://localhost:8080/engine/v1/agents/cross_platform_arb/scan | jq '.opportunities | length'
  ```
  Expected: non-zero (Task 1 verified).
- [ ] `docs/adr/0010-strategy-graduation-gate.md` is present and linked from `docs/adr/README.md` (if that index exists — otherwise skip).
- [ ] `STA_RISK_PORTFOLIO_MAX_POSITION_USD` is set in `trading/.env` (production value tbd by user; reasonable default $5000 for a $11k book).
- [ ] `STA_LLM_AGENT_BUDGETS` is set (empty JSON `{}` is fine until Phase 1).

## Follow-up Plans (Not In This Plan)

Once Phase 0 ships, create these separately and gate each on ADR-0010:

1. `2026-04-XX-smart-order-router-phase-1.md` — OrderSlicer scoped to arb-leg execution.
2. `2026-04-XX-resolution-edge-v0-1.md` — Push-driven (AP API, C-SPAN), no LLM in hot path, per-agent LLM cap already wired from Task 3.
3. (Conditional on backtest showing edge) `2026-04-XX-social-alpha-pipeline.md` — only after backtest demonstrates Sharpe > 1.0 on 12 months.
4. (Conditional on backtest) `2026-04-XX-new-market-sniper.md`.
5. **Market Making is not planned.** Per the review, it needs 6+ months of live taker experience first and a standalone proposal; reassess in Q4 2026.
