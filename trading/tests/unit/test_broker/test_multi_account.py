from unittest.mock import MagicMock
from broker.interfaces import MultiAccountBroker

def test_multi_account_routing():
    broker = MultiAccountBroker()
    mock_sub_broker = MagicMock()
    broker.register_account("ACC_1", mock_sub_broker)
    assert broker.get_broker("ACC_1") is mock_sub_broker
    assert broker.get_broker("UNKNOWN") is None
