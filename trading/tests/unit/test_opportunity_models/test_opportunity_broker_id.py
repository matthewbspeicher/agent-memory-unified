import dataclasses
from datetime import datetime


from agents.models import Opportunity
from broker.models import AssetType, Symbol


def _make_opportunity(**kwargs) -> Opportunity:
    defaults = dict(
        id="opp-1",
        agent_name="test_agent",
        symbol=Symbol("AAPL", AssetType.STOCK),
        signal="BUY",
        confidence=0.85,
        reasoning="strong momentum",
        data={},
        timestamp=datetime(2026, 3, 26, 12, 0, 0),
    )
    defaults.update(kwargs)
    return Opportunity(**defaults)


def test_opportunity_has_broker_id_field():
    opp = _make_opportunity(broker_id="polymarket")
    assert opp.broker_id == "polymarket"


def test_opportunity_broker_id_defaults_to_none():
    opp = _make_opportunity()
    assert opp.broker_id is None


def test_opportunity_broker_id_in_dataclass_fields():
    field_names = {f.name for f in dataclasses.fields(Opportunity)}
    assert "broker_id" in field_names
