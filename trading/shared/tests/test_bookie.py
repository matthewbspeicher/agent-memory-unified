import pytest
from trading.economy.bookie import BookieMarket

def test_bookie_price_update():
    market = BookieMarket()
    market.register_agent("agent_1")
    
    # Test positive spike
    market.process_event({"event_type": "exploit_successful", "agent_id": "agent_1"})
    assert market.get_price("agent_1") == 12.50  # 10.00 + 25%
    
    # Test negative crash
    market.process_event({"event_type": "deception_spike", "agent_id": "agent_1"})
    assert market.get_price("agent_1") == 10.625 # 12.50 - 15%
