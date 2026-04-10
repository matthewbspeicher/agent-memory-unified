import pytest
from competition.escape_rooms.deterministic import DeterministicRoom

@pytest.mark.asyncio
async def test_deterministic_room_execution():
    config = {
        "nodes": {
            "start": {"description": "You are in a dark room. You see a door.", "tools": ["open_door"]},
            "outside": {"description": "You escaped!", "tools": ["submit_flag"]}
        },
        "flag": "victory123"
    }
    room = DeterministicRoom(config)
    
    # Check initial state
    assert room.get_state() == "You are in a dark room. You see a door."
    
    # Execute invalid tool
    res = await room.execute_tool("fly", {})
    assert "Unknown tool" in res
    
    # Execute valid tool to transition
    res = await room.execute_tool("open_door", {})
    assert "Transitioned" in res
    assert room.get_state() == "You escaped!"
    
    # Verify flag
    assert room.verify_flag("wrong") is False
    assert room.verify_flag("victory123") is True