import pytest
from decimal import Decimal

from agents.models import AgentConfig, ActionLevel
from broker.models import Symbol, OrderSide
from data.backtest import HistoricalDataSource, ReplayDataBus
from strategies.dsl import DSLAgent


class MockDataBus(ReplayDataBus):
    async def get_rsi(self, symbol: Symbol, period: int = 14) -> float:
        return 25.0

    async def get_sma(self, symbol: Symbol, period: int = 20) -> float:
        return 150.0


@pytest.mark.asyncio
async def test_dsl_conditions():
    bus = MockDataBus(
        historical_source=HistoricalDataSource({}), starting_balance=Decimal("1000")
    )

    config = AgentConfig(
        name="dsl_test",
        strategy="dsl",
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        universe=["AAPL"],
        parameters={
            "rules": [
                {
                    "conditions": [
                        {"indicator": "rsi", "operator": "<", "value": 30},
                        {"indicator": "sma", "operator": ">", "value": 100},
                    ],
                    "action": "BUY",
                    "quantity": 5,
                }
            ]
        },
    )

    agent = DSLAgent(config)
    opportunities = await agent.scan(bus)

    assert len(opportunities) == 1
    opp = opportunities[0]
    assert opp.symbol.ticker == "AAPL"
    assert opp.signal == "DSL_MATCH"
    assert opp.suggested_trade is not None
    assert opp.suggested_trade.side == OrderSide.BUY
    assert opp.suggested_trade.quantity == Decimal("5")


@pytest.mark.asyncio
async def test_dsl_conditions_unmatched():
    bus = MockDataBus(
        historical_source=HistoricalDataSource({}), starting_balance=Decimal("1000")
    )

    config = AgentConfig(
        name="dsl_test",
        strategy="dsl",
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        universe=["AAPL"],
        parameters={
            "rules": [
                {
                    "conditions": [
                        {
                            "indicator": "rsi",
                            "operator": "<",
                            "value": 20,
                        }  # Actual is 25, so this fails
                    ],
                    "action": "BUY",
                    "quantity": 5,
                }
            ]
        },
    )

    agent = DSLAgent(config)
    opportunities = await agent.scan(bus)

    assert len(opportunities) == 0
