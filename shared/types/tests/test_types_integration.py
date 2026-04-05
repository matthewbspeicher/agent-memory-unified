"""Integration test: Verify shared types work across services."""
import sys
from pathlib import Path

# Add shared types to path
types_path = Path(__file__).parent.parent.parent / "types-py"
sys.path.insert(0, str(types_path))

from shared_types import Agent, Memory, Trade, Event


def test_agent_serialization():
    """Test Agent DTO round-trip."""
    agent = Agent(
        id="550e8400-e29b-41d4-a716-446655440000",
        name="TestAgent",
        token_hash="a" * 64,  # SHA256 is 64 chars
        owner_id="660e8400-e29b-41d4-a716-446655440000",
        is_active=True,
        scopes=["memories:read", "memories:write"],  # Valid scope pattern
        created_at="2026-04-05T12:00:00Z",
        updated_at="2026-04-05T12:00:00Z",
    )

    # Serialize to dict
    data = agent.model_dump()
    assert data["name"] == "TestAgent"
    assert data["is_active"] is True

    # Deserialize from dict
    agent2 = Agent(**data)
    assert agent2.name == agent.name
    assert agent2.id == agent.id


def test_event_envelope():
    """Test Event wrapper for Redis Streams."""
    event = Event(
        id="770e8400-e29b-41d4-a716-446655440000",
        type="trade.opened",
        version="1.0",
        timestamp="2026-04-05T12:00:00Z",
        source="trading",
        payload={
            "trade_id": 123,
            "symbol": "AAPL",
            "side": "long",
        },
    )

    data = event.model_dump()
    assert data["type"] == "trade.opened"
    assert data["payload"]["symbol"] == "AAPL"


if __name__ == "__main__":
    test_agent_serialization()
    test_event_envelope()
    print("✅ All integration tests passed")
