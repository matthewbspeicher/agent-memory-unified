"""
Integration test for TaoshiBridge persistence using BittensorStore.
"""

import pytest
import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from integrations.bittensor.taoshi_bridge import TaoshiBridge


@pytest.fixture
def mock_taoshi_root(tmp_path):
    """Create a mock Taoshi PTN directory structure."""
    root = tmp_path / "taoshi-ptn"
    miners_dir = root / "validation" / "miners"
    miner_dir = miners_dir / "hotkey123"
    positions_dir = miner_dir / "positions" / "BTCUSD" / "open"
    positions_dir.mkdir(parents=True)
    
    # Create a position file
    pos_data = {
        "position_uuid": "pos-123",
        "open_ms": 1712503800000,
        "orders": [{"order_type": "LONG", "leverage": 1.0, "price": 65000.0}]
    }
    (positions_dir / "pos-123.json").write_text(json.dumps(pos_data))
    
    return root


@pytest.mark.asyncio
async def test_taoshi_bridge_persistence_load_and_save(mock_taoshi_root):
    """Verify that TaoshiBridge loads existing UUIDs and saves new ones."""
    mock_store = AsyncMock()
    # Mock existing UUIDs in DB
    mock_store.get_processed_position_uuids.return_value = {"existing-uuid"}
    
    mock_signal_bus = AsyncMock()
    
    # Instantiate bridge with mock store
    bridge = TaoshiBridge(
        taoshi_root=mock_taoshi_root,
        store=mock_store,  # New parameter
        signal_bus=mock_signal_bus,
        poll_interval=0.1
    )
    
    # Verify load was called (should happen in run or init)
    # Let's assume it happens during the first poll or run startup
    
    # We need to trigger a poll
    # We can use a short run task
    task = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.3)
    bridge.stop()
    await task
    
    # 1. Check if get_processed_position_uuids was called
    mock_store.get_processed_position_uuids.assert_called_once()
    assert "existing-uuid" in bridge._seen_position_uuids
    
    # 2. Check if save_processed_position_uuid was called for the new position
    mock_store.save_processed_position_uuid.assert_called_with("pos-123", "hotkey123")
    assert "pos-123" in bridge._seen_position_uuids
