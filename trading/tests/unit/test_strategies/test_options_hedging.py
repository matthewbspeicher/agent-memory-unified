import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from agents.models import AgentConfig, ActionLevel
from broker.models import Symbol, AssetType, Position, OptionsChain, Quote
from data.bus import DataBus
from strategies.options_hedging import OptionsHedgingAgent


class MockBrokerMarketData:
    async def get_quote(self, symbol):
        return Quote(symbol=symbol, last=Decimal("150.0"))

    async def get_options_chain(self, symbol):
        now = datetime.now(timezone.utc).date()
        expiry = now + timedelta(days=35)
        return OptionsChain(
            symbol=symbol,
            expirations=[now + timedelta(days=10), expiry, now + timedelta(days=90)],
            strikes=[
                Decimal("130"),
                Decimal("140"),
                Decimal("150"),
                Decimal("160"),
                Decimal("170"),
            ],
        )

    async def get_contract_details(self, symbol):
        pass


class MockBrokerAccount:
    async def get_positions(self, account_id):
        return [
            Position(
                symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
                quantity=Decimal("100"),
                avg_cost=Decimal("140.0"),
                market_value=Decimal("15000.0"),
                unrealized_pnl=Decimal("1000.0"),
                realized_pnl=Decimal("0.0"),
            )
        ]


class MockBroker:
    @property
    def market_data(self):
        return MockBrokerMarketData()

    @property
    def account(self):
        return MockBrokerAccount()


@pytest.mark.asyncio
async def test_options_hedging_agent_collar():
    config = AgentConfig(
        name="test_hedge",
        strategy="options_hedging",
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        universe="PORTFOLIO",
        parameters={"strategy": "collar", "dte_min": 30, "dte_max": 45},
    )
    agent = OptionsHedgingAgent(config)

    bus = DataBus(broker=MockBroker(), account_id="PAPER")

    opportunities = await agent.scan(bus)
    assert len(opportunities) == 1

    opp = opportunities[0]
    assert opp.signal == "HEDGE_COLLAR"
    assert opp.symbol.ticker == "AAPL"

    trade = opp.suggested_trade
    assert trade is not None
    assert len(trade.legs) == 2

    put = [l for l in trade.legs if l.symbol.right.value == "PUT"][0]
    # 150 * 0.9 = 135 -> closest are 130 and 140.
    assert put.symbol.strike in (Decimal("130"), Decimal("140"))

    call = [l for l in trade.legs if l.symbol.right.value == "CALL"][0]
    assert call.symbol.strike in (Decimal("160"), Decimal("170"))


@pytest.mark.asyncio
async def test_options_hedging_agent_iron_condor():
    config = AgentConfig(
        name="test_hedge",
        strategy="options_hedging",
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        universe="PORTFOLIO",
        parameters={"strategy": "iron_condor"},
    )
    agent = OptionsHedgingAgent(config)
    bus = DataBus(broker=MockBroker(), account_id="PAPER")

    opts = await agent.scan(bus)
    assert len(opts) == 1
    trade = opts[0].suggested_trade
    assert len(trade.legs) == 4
