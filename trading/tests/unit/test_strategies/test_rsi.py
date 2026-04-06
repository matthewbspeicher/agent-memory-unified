from unittest.mock import AsyncMock, MagicMock

from agents.models import ActionLevel, AgentConfig
from broker.models import Symbol
from strategies.rsi import RSIAgent


def _make_config(**overrides):
    defaults = dict(
        name="rsi-test",
        strategy="rsi",
        schedule="on_demand",
        action_level=ActionLevel.NOTIFY,
        universe=["AAPL", "MSFT"],
        parameters={"period": 14, "oversold": 30, "overbought": 70},
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


class TestRSIAgent:
    def test_description(self):
        agent = RSIAgent(config=_make_config())
        assert "RSI" in agent.description

    async def test_scan_oversold(self):
        bus = MagicMock()
        bus.get_universe = MagicMock(
            return_value=[Symbol(ticker="AAPL"), Symbol(ticker="MSFT")]
        )
        bus.get_rsi = AsyncMock(side_effect=[25.0, 55.0])  # AAPL oversold, MSFT normal
        bus.get_quote = AsyncMock(return_value=MagicMock(last=150))

        agent = RSIAgent(config=_make_config())
        opps = await agent.scan(bus)

        assert len(opps) == 1
        assert opps[0].symbol.ticker == "AAPL"
        assert opps[0].signal == "RSI_OVERSOLD"
        assert opps[0].confidence > 0

    async def test_scan_overbought(self):
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
        bus.get_rsi = AsyncMock(return_value=80.0)
        bus.get_quote = AsyncMock(return_value=MagicMock(last=150))

        agent = RSIAgent(config=_make_config())
        opps = await agent.scan(bus)

        assert len(opps) == 1
        assert opps[0].signal == "RSI_OVERBOUGHT"

    async def test_scan_no_signals(self):
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
        bus.get_rsi = AsyncMock(return_value=50.0)

        agent = RSIAgent(config=_make_config())
        opps = await agent.scan(bus)
        assert len(opps) == 0

    async def test_scan_handles_error_gracefully(self):
        bus = MagicMock()
        bus.get_universe = MagicMock(return_value=[Symbol(ticker="AAPL")])
        bus.get_rsi = AsyncMock(side_effect=Exception("data unavailable"))

        agent = RSIAgent(config=_make_config())
        opps = await agent.scan(bus)
        assert len(opps) == 0  # errors logged, not raised
