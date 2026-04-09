"""Tests for multi-subnet querier."""

import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


if "bittensor" not in sys.modules:
    # Lightweight shim so unit tests don't require the Bittensor dependency.
    mock_bt = types.ModuleType("bittensor")
    mock_bt.Wallet = type(
        "MockWallet", (), {"__init__": lambda self, *args, **kwargs: None}
    )
    mock_bt.Subtensor = lambda *args, **kwargs: MagicMock()
    mock_bt.Dendrite = lambda *args, **kwargs: MagicMock()
    mock_bt.Synapse = type("Synapse", (), {})
    sys.modules["bittensor"] = mock_bt

from integrations.bittensor.subnet_querier import SubnetQuerier, SubnetSignal


class TestSubnetSignal:
    def test_signal_creation(self):
        signal = SubnetSignal(
            subnet=28,
            hotkey="5DkVM4wyv4ZXGvb9ZmYafPiySbmWS4s2i5W37CNHuh4ggAha",
            signal_type="sp500",
            value=0.65,
            confidence=0.8,
            timestamp=1234567890.0,
        )
        assert signal.subnet == 28
        assert signal.signal_type == "sp500"
        assert signal.value == 0.65
        assert signal.confidence == 0.8


class TestSubnetQuerier:
    def test_signal_type_mapping(self):
        """Test that signal type mapping works."""
        querier = SubnetQuerier.__new__(SubnetQuerier)
        assert querier._get_signal_type(28) == "sp500"
        assert querier._get_signal_type(15) == "crypto_analysis"
        assert querier._get_signal_type(8) == "ptn"
        assert querier._get_signal_type(99) == "unknown"

    @pytest.mark.asyncio
    async def test_query_subnet_returns_list(self):
        """query_subnet parses only active miner responses."""
        querier = SubnetQuerier.__new__(SubnetQuerier)

        active_axon = SimpleNamespace(uid=0)
        inactive_axon = SimpleNamespace(uid=1)
        metagraph = SimpleNamespace(
            uids=[0, 1],
            axons=[active_axon, inactive_axon],
            S=[1.0, 0.0],
            neurons=[
                SimpleNamespace(stake=1.0),
                SimpleNamespace(stake=0.0),
            ],
        )

        querier._subtensor = MagicMock()
        querier._subtensor.metagraph = MagicMock(return_value=metagraph)
        querier._dendrite = AsyncMock(
            return_value=SimpleNamespace(
                neuron=SimpleNamespace(hotkey="hotkeyA", last_update=1234.0)
            )
        )

        signals = await querier.query_subnet(28)

        assert len(signals) == 1
        assert signals[0].subnet == 28
        assert signals[0].hotkey == "hotkeyA"
        assert signals[0].signal_type == "sp500"
        assert signals[0].timestamp == 1234.0
        querier._dendrite.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_all_collects_subnets(self):
        """query_all collects results for all configured subnet queries."""
        querier = SubnetQuerier.__new__(SubnetQuerier)
        querier.query_subnet = AsyncMock(
            side_effect=[
                [SubnetSignal(28, "hotkeyA", "sp500", 0.0, 1.0, 0.0)],
                [SubnetSignal(15, "hotkeyB", "crypto_analysis", 0.0, 1.0, 0.0)],
            ]
        )

        result = await querier.query_all()

        assert result["sp500"][0].hotkey == "hotkeyA"
        assert result["bitquant"][0].hotkey == "hotkeyB"


class TestCreateQuerier:
    def test_create_returns_none_without_hotkey(self, monkeypatch):
        import integrations.bittensor.subnet_querier as module

        class MockWallet:
            def __init__(self, *args, **kwargs):
                pass

            hotkey = ""

        # bt is lazily imported inside create_querier, so mock it via sys.modules
        import unittest.mock as um

        mock_bt = um.MagicMock()
        mock_bt.Wallet = MockWallet
        with um.patch.dict("sys.modules", {"bittensor": mock_bt}):
            assert module.create_querier() is None
