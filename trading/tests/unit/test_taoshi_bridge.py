"""Unit tests for TaoshiBridge change detection logic."""

import json
import pytest
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from integrations.bittensor.taoshi_bridge import TaoshiBridge


def _make_position(uuid: str, orders: list[dict] | None = None) -> dict:
    """Helper to build a minimal Taoshi position dict."""
    if orders is None:
        orders = [
            {
                "order_type": "LONG",
                "leverage": 1.0,
                "price": 50000.0,
                "processed_ms": 1700000000000,
            }
        ]
    return {
        "position_uuid": uuid,
        "open_ms": 1700000000000,
        "orders": orders,
    }


def _write_position(
    base_dir: Path, hotkey: str, symbol: str, uuid: str, position: dict
) -> Path:
    """Write a position JSON file to the expected directory structure."""
    pos_dir = (
        base_dir / "validation" / "miners" / hotkey / "positions" / symbol / "open"
    )
    pos_dir.mkdir(parents=True, exist_ok=True)
    path = pos_dir / f"{uuid}.json"
    path.write_text(json.dumps(position))
    return path


def _remove_position(base_dir: Path, hotkey: str, symbol: str, uuid: str) -> None:
    """Remove a position file (simulating move to closed/)."""
    path = (
        base_dir
        / "validation"
        / "miners"
        / hotkey
        / "positions"
        / symbol
        / "open"
        / f"{uuid}.json"
    )
    if path.exists():
        path.unlink()


class TestHashPosition:
    """Tests for _hash_position static method."""

    def test_same_position_same_hash(self):
        pos = _make_position("abc")
        h1 = TaoshiBridge._hash_position(pos)
        h2 = TaoshiBridge._hash_position(pos)
        assert h1 == h2

    def test_different_order_count_different_hash(self):
        pos1 = _make_position(
            "abc",
            orders=[
                {
                    "order_type": "LONG",
                    "leverage": 1.0,
                    "price": 50000,
                    "processed_ms": 100,
                },
            ],
        )
        pos2 = _make_position(
            "abc",
            orders=[
                {
                    "order_type": "LONG",
                    "leverage": 1.0,
                    "price": 50000,
                    "processed_ms": 100,
                },
                {
                    "order_type": "LONG",
                    "leverage": 2.0,
                    "price": 51000,
                    "processed_ms": 200,
                },
            ],
        )
        assert TaoshiBridge._hash_position(pos1) != TaoshiBridge._hash_position(pos2)

    def test_different_leverage_different_hash(self):
        pos1 = _make_position(
            "abc",
            orders=[
                {
                    "order_type": "LONG",
                    "leverage": 1.0,
                    "price": 50000,
                    "processed_ms": 100,
                },
            ],
        )
        pos2 = _make_position(
            "abc",
            orders=[
                {
                    "order_type": "LONG",
                    "leverage": 5.0,
                    "price": 50000,
                    "processed_ms": 100,
                },
            ],
        )
        assert TaoshiBridge._hash_position(pos1) != TaoshiBridge._hash_position(pos2)

    def test_different_timestamp_different_hash(self):
        pos1 = _make_position(
            "abc",
            orders=[
                {
                    "order_type": "LONG",
                    "leverage": 1.0,
                    "price": 50000,
                    "processed_ms": 100,
                },
            ],
        )
        pos2 = _make_position(
            "abc",
            orders=[
                {
                    "order_type": "LONG",
                    "leverage": 1.0,
                    "price": 50000,
                    "processed_ms": 999,
                },
            ],
        )
        assert TaoshiBridge._hash_position(pos1) != TaoshiBridge._hash_position(pos2)

    def test_empty_orders(self):
        pos = _make_position("abc", orders=[])
        h = TaoshiBridge._hash_position(pos)
        assert isinstance(h, str) and len(h) > 0


@pytest.mark.asyncio
class TestBridgePoll:
    """Tests for the _poll change detection logic."""

    async def test_new_position_emits_signal(self, tmp_path):
        """First time seeing a UUID should emit with reason 'new_position'."""
        signal_bus = AsyncMock()
        bridge = TaoshiBridge(taoshi_root=tmp_path, signal_bus=signal_bus)

        pos = _make_position("uuid-001")
        _write_position(tmp_path, "hotkey1", "BTCUSD", "uuid-001", pos)

        await bridge._poll()

        assert signal_bus.publish.call_count == 1
        signal = signal_bus.publish.call_args[0][0]
        assert signal.payload["signal_reason"] == "new_position"
        assert signal.payload["order_count"] == 1
        assert bridge.signals_emitted == 1

    async def test_store_loaded_positions_do_not_emit(self, tmp_path):
        """Positions loaded from store should initialize without duplicate emission."""
        signal_bus = AsyncMock()

        bridge = TaoshiBridge(
            taoshi_root=tmp_path,
            signal_bus=signal_bus,
        )

        # Simulate warm-start state from prior run via store.
        bridge._initialized_from_store = {"uuid-001"}
        bridge._seen_positions["uuid-001"] = ""

        pos = _make_position("uuid-001")
        _write_position(tmp_path, "hotkey1", "BTCUSD", "uuid-001", pos)

        await bridge._poll()

        assert signal_bus.publish.call_count == 0
        assert bridge._seen_positions.get("uuid-001") == bridge._hash_position(pos)
        assert "uuid-001" not in bridge._initialized_from_store
        assert bridge.signals_emitted == 0

    async def test_unchanged_position_no_reemit(self, tmp_path):
        """Same position with no changes should NOT re-emit."""
        signal_bus = AsyncMock()
        bridge = TaoshiBridge(taoshi_root=tmp_path, signal_bus=signal_bus)

        pos = _make_position("uuid-001")
        _write_position(tmp_path, "hotkey1", "BTCUSD", "uuid-001", pos)

        await bridge._poll()
        assert signal_bus.publish.call_count == 1

        # Second poll — same data
        await bridge._poll()
        assert signal_bus.publish.call_count == 1  # no new call

    async def test_updated_position_emits_signal(self, tmp_path):
        """Position with a new order should re-emit with reason 'position_updated'."""
        signal_bus = AsyncMock()
        bridge = TaoshiBridge(taoshi_root=tmp_path, signal_bus=signal_bus)

        pos = _make_position("uuid-001")
        _write_position(tmp_path, "hotkey1", "BTCUSD", "uuid-001", pos)
        await bridge._poll()
        assert signal_bus.publish.call_count == 1

        # Add a second order
        pos["orders"].append(
            {
                "order_type": "LONG",
                "leverage": 2.0,
                "price": 52000.0,
                "processed_ms": 1700000060000,
            }
        )
        _write_position(tmp_path, "hotkey1", "BTCUSD", "uuid-001", pos)
        await bridge._poll()

        assert signal_bus.publish.call_count == 2
        signal = signal_bus.publish.call_args[0][0]
        assert signal.payload["signal_reason"] == "position_updated"
        assert signal.payload["order_count"] == 2
        assert bridge.updates_detected == 1

    async def test_closed_position_cleaned_from_tracking(self, tmp_path):
        """Position removed from disk should be cleaned from tracking dict."""
        signal_bus = AsyncMock()
        bridge = TaoshiBridge(taoshi_root=tmp_path, signal_bus=signal_bus)

        pos = _make_position("uuid-001")
        _write_position(tmp_path, "hotkey1", "BTCUSD", "uuid-001", pos)
        await bridge._poll()
        assert "uuid-001" in bridge._seen_positions

        # Remove position (simulating close)
        _remove_position(tmp_path, "hotkey1", "BTCUSD", "uuid-001")
        await bridge._poll()

        assert "uuid-001" not in bridge._seen_positions

    async def test_get_status_includes_updates_detected(self, tmp_path):
        """get_status() should report updates_detected counter."""
        bridge = TaoshiBridge(taoshi_root=tmp_path)
        status = bridge.get_status()
        assert "updates_detected" in status
        assert status["updates_detected"] == 0

    async def test_no_signal_bus_no_crash(self, tmp_path):
        """Bridge without signal_bus should not crash on emit."""
        bridge = TaoshiBridge(taoshi_root=tmp_path, signal_bus=None)
        pos = _make_position("uuid-001")
        _write_position(tmp_path, "hotkey1", "BTCUSD", "uuid-001", pos)
        await bridge._poll()  # Should not raise
        assert bridge.open_positions == 1
