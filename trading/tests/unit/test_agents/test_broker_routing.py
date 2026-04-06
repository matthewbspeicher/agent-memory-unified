from __future__ import annotations
from unittest.mock import MagicMock

import pytest

from broker.models import AssetType, Symbol


def _mock_broker(name: str, connected: bool = True) -> MagicMock:
    broker = MagicMock()
    broker.connection.is_connected.return_value = connected
    broker._name = name
    return broker


def _mock_opportunity(
    ticker: str = "AAPL",
    asset_type: AssetType = AssetType.STOCK,
    broker_id: str | None = None,
):
    from agents.models import Opportunity

    opp = MagicMock(spec=Opportunity)
    opp.symbol = Symbol(ticker=ticker, asset_type=asset_type)
    opp.broker_id = broker_id
    opp.id = "opp1"
    opp.agent_name = "test"
    return opp


def test_resolve_by_broker_id():
    from agents.router import OpportunityRouter

    alpaca = _mock_broker("alpaca")
    tradier = _mock_broker("tradier")

    router = OpportunityRouter.__new__(OpportunityRouter)
    router._broker = alpaca
    router._brokers = {"alpaca": alpaca, "tradier": tradier}
    router._broker_routing = {}

    opp = _mock_opportunity(broker_id="tradier")
    resolved = router._resolve_broker(opp)
    assert resolved is tradier


def test_resolve_by_routing_config():
    from agents.router import OpportunityRouter

    alpaca = _mock_broker("alpaca")
    tradier = _mock_broker("tradier")

    router = OpportunityRouter.__new__(OpportunityRouter)
    router._broker = alpaca
    router._brokers = {"alpaca": alpaca, "tradier": tradier}
    router._broker_routing = {"OPTION": "tradier"}

    opp = _mock_opportunity(asset_type=AssetType.OPTION)
    resolved = router._resolve_broker(opp)
    assert resolved is tradier


def test_resolve_falls_back_to_primary():
    from agents.router import OpportunityRouter

    alpaca = _mock_broker("alpaca")

    router = OpportunityRouter.__new__(OpportunityRouter)
    router._broker = alpaca
    router._brokers = {"alpaca": alpaca}
    router._broker_routing = {}

    opp = _mock_opportunity()
    resolved = router._resolve_broker(opp)
    assert resolved is alpaca


def test_resolve_disconnected_broker_raises():
    from agents.router import OpportunityRouter

    tradier = _mock_broker("tradier", connected=False)
    alpaca = _mock_broker("alpaca")

    router = OpportunityRouter.__new__(OpportunityRouter)
    router._broker = alpaca
    router._brokers = {"alpaca": alpaca, "tradier": tradier}
    router._broker_routing = {}

    opp = _mock_opportunity(broker_id="tradier")
    with pytest.raises(RuntimeError, match="not connected"):
        router._resolve_broker(opp)


def test_resolve_unknown_broker_falls_back():
    from agents.router import OpportunityRouter

    alpaca = _mock_broker("alpaca")

    router = OpportunityRouter.__new__(OpportunityRouter)
    router._broker = alpaca
    router._brokers = {"alpaca": alpaca}
    router._broker_routing = {}

    opp = _mock_opportunity(broker_id="nonexistent")
    # Falls back to primary since nonexistent isn't in _brokers
    resolved = router._resolve_broker(opp)
    assert resolved is alpaca
