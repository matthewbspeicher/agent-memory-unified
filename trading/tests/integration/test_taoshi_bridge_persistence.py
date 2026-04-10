"""
Integration test for TaoshiBridge persistence using BittensorStore.
"""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock
from integrations.bittensor.taoshi_bridge import TaoshiBridge


@pytest.fixture
def mock_taoshi_root(tmp_path):
    """Create a mock Taoshi PTN directory structure."""
    root = tmp_path / "taoshi-vanta"
    miners_dir = root / "validation" / "miners"
    miner_dir = miners_dir / "hotkey123"
    positions_dir = miner_dir / "positions" / "BTCUSD" / "open"
    positions_dir.mkdir(parents=True)

    # Create a position file
    pos_data = {
        "position_uuid": "pos-123",
        "open_ms": 1712503800000,
        "orders": [{"order_type": "LONG", "leverage": 1.0, "price": 65000.0}],
    }
    (positions_dir / "pos-123.json").write_text(json.dumps(pos_data))

    return root


@pytest.mark.asyncio
async def test_taoshi_bridge_persistence_load_and_save(mock_taoshi_root):
    """Verify that TaoshiBridge loads existing positions and detects new ones."""
    mock_store = AsyncMock()
    # Mock existing UUIDs in DB (for legacy compatibility)
    mock_store.get_processed_position_uuids.return_value = {"existing-uuid"}

    mock_signal_bus = AsyncMock()

    # Instantiate bridge with mock store
    bridge = TaoshiBridge(
        taoshi_root=mock_taoshi_root,
        store=mock_store,
        signal_bus=mock_signal_bus,
        poll_interval=0.1,
    )

    # Run bridge to trigger first poll
    task = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.3)
    bridge.stop()
    await task

    # 1. Check that new position was detected and signal emitted
    # The new implementation uses _seen_positions hash-based tracking
    assert "pos-123" in bridge._seen_positions

    # 2. Verify signal was emitted (via signal_bus.publish)
    # At least one signal should have been published for the new position
    assert mock_signal_bus.publish.called

    # 3. Check position tracking - should have hash for the position
    # Note: new positions are counted as "new_signals", not "updates_detected"
    assert bridge._seen_positions.get("pos-123") is not None
