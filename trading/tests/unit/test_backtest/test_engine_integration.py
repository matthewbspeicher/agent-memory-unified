import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from agents.base import Agent
from agents.models import AgentConfig, ActionLevel, Opportunity
from broker.models import Bar, Symbol, OrderSide, MarketOrder
from data.backtest import HistoricalDataSource, ReplayDataBus, BacktestEngine

class DummyAgent(Agent):
    def description(self) -> str:
        return "Dummy"
        
    async def scan(self, data: ReplayDataBus) -> list[Opportunity]:
        quote = await data.get_quote(Symbol("AAPL"))
        # Buy if price < 150, Sell if price > 160
        price = quote.last
        if price < Decimal("150"):
            return [
                Opportunity(
                    id="opp1",
                    agent_name=self.name,
                    symbol=Symbol("AAPL"),
                    signal="BUY_DIP",
                    confidence=0.9,
                    reasoning="Price low",
                    data={},
                    timestamp=quote.timestamp,
                    suggested_trade=MarketOrder(
                        symbol=Symbol("AAPL"),
                        side=OrderSide.BUY,
                        quantity=Decimal("10"),
                        account_id="backtest",
                    )
                )
            ]
        elif price > Decimal("160"):
            return [
                Opportunity(
                    id="opp2",
                    agent_name=self.name,
                    symbol=Symbol("AAPL"),
                    signal="SELL_HIGH",
                    confidence=0.9,
                    reasoning="Price high",
                    data={},
                    timestamp=quote.timestamp,
                    suggested_trade=MarketOrder(
                        symbol=Symbol("AAPL"),
                        side=OrderSide.SELL,
                        quantity=Decimal("10"),
                        account_id="backtest",
                    )
                )
            ]
        return []

@pytest.fixture
def sample_bars():
    base_time = datetime(2023, 1, 1, 10, 0)
    bars = []
    prices = [145.0, 148.0, 155.0, 165.0, 162.0]
    for i, p in enumerate(prices):
        bars.append(Bar(
            symbol=Symbol("AAPL"),
            close=Decimal(str(p)),
            timestamp=base_time + timedelta(days=i)
        ))
    return {"AAPL": bars}

async def test_replay_data_bus(sample_bars):
    source = HistoricalDataSource(bars=sample_bars)
    bus = ReplayDataBus(historical_source=source, starting_balance=Decimal("10000.0"))
    
    # Test setting time to day 0
    t0 = sample_bars["AAPL"][0].timestamp
    bus.advance_time(t0)
    
    quote = await bus.get_quote(Symbol("AAPL"))
    assert quote.last == Decimal("145.0")
    
    hist = await bus.get_historical(Symbol("AAPL"))
    assert len(hist) == 1
    
    # Advance to day 2
    t2 = sample_bars["AAPL"][2].timestamp
    bus.advance_time(t2)
    hist2 = await bus.get_historical(Symbol("AAPL"))
    assert len(hist2) == 3
    assert hist2[-1].close == Decimal("155.0")

async def test_backtest_engine(sample_bars):
    source = HistoricalDataSource(bars=sample_bars)
    bus = ReplayDataBus(historical_source=source, starting_balance=Decimal("10000.0"))
    
    agent_config = AgentConfig(
        name="dummy",
        strategy="dummy",
        schedule="on_demand",
        action_level=ActionLevel.AUTO_EXECUTE
    )
    agent = DummyAgent(agent_config)
    engine = BacktestEngine(bus=bus, agents=[agent])
    
    times = [b.timestamp for b in sample_bars["AAPL"]]
    
    res = await engine.run(times)
    
    assert res["initial_equity"] == Decimal("10000.0")
    # Day 0: Price 145 -> Buys 10 * 145 = 1450. Cash = 8550. Pos = 10 AAPL @ 145
    # Day 1: Price 148 -> Buys 10 * 148 = 1480. Cash = 7070. Pos = 20 AAPL
    # Day 2: Price 155 -> Holds. Pos = 20 AAPL
    # Day 3: Price 165 -> Sells 10 * 165 = 1650. Cash = 8720. Pos = 10 AAPL
    # Day 4: Price 162 -> Sells 10 * 162 = 1620. Cash = 10340. Pos = 0 AAPL
    
    assert res["final_equity"] == Decimal("10340.0")
    assert len(res["snapshots"]) == 5
    assert res["snapshots"][0]["executed"] == 1
    assert res["snapshots"][3]["executed"] == 1
