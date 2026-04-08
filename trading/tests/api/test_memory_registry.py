import pytest
from api.services.memory_registry import MemoryRegistry

def test_memory_registry():
    registry = MemoryRegistry()
    registry.register_client("agent1", "client1")
    assert registry.get_client("agent1") == "client1"
    
    registry.register_shared("shared_client")
    assert registry.get_shared() == "shared_client"
