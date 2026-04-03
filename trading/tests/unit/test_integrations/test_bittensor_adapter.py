from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.bittensor.adapter import TaoshiProtocolAdapter, HASH_WINDOWS, FORWARD_WINDOWS


def test_protocol_constants():
    assert HASH_WINDOWS == (0, 30)
    assert FORWARD_WINDOWS == (1, 2, 3, 31, 32, 33)


async def test_parse_stream_id():
    adapter = TaoshiProtocolAdapter.__new__(TaoshiProtocolAdapter)
    symbol, timeframe = adapter.parse_stream_id("BTCUSD-5m")
    assert symbol == "BTCUSD"
    assert timeframe == "5m"


async def test_parse_stream_id_with_dash_in_symbol():
    adapter = TaoshiProtocolAdapter.__new__(TaoshiProtocolAdapter)
    symbol, timeframe = adapter.parse_stream_id("BTC-USD-1h")
    assert symbol == "BTC-USD"
    assert timeframe == "1h"


async def test_validate_tensor_valid():
    adapter = TaoshiProtocolAdapter.__new__(TaoshiProtocolAdapter)
    predictions = [0.1] * 100
    assert adapter.validate_tensor(predictions, expected_size=100) is True


async def test_validate_tensor_wrong_size():
    adapter = TaoshiProtocolAdapter.__new__(TaoshiProtocolAdapter)
    predictions = [0.1] * 50
    assert adapter.validate_tensor(predictions, expected_size=100) is False


async def test_validate_tensor_with_nan():
    adapter = TaoshiProtocolAdapter.__new__(TaoshiProtocolAdapter)
    predictions = [0.1] * 99 + [float("nan")]
    assert adapter.validate_tensor(predictions, expected_size=100) is False


async def test_validate_tensor_with_inf():
    adapter = TaoshiProtocolAdapter.__new__(TaoshiProtocolAdapter)
    predictions = [0.1] * 99 + [float("inf")]
    assert adapter.validate_tensor(predictions, expected_size=100) is False


import hashlib
import json

from integrations.bittensor.adapter import TaoshiProtocolAdapter, FORWARD_DELAY_SECONDS


def test_forward_delay_constant():
    assert FORWARD_DELAY_SECONDS == 60


def test_build_request():
    adapter = TaoshiProtocolAdapter.__new__(TaoshiProtocolAdapter)
    req = adapter.build_request()
    assert req.stream_id == "BTCUSD-5m"
    assert req.prediction_size == 100
    assert req.feature_ids == [1, 2, 3, 4, 5]


def test_verify_hash_commitment_valid():
    predictions = [0.1, 0.2, 0.3]
    raw = json.dumps(predictions, separators=(",", ":"))
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    assert TaoshiProtocolAdapter.verify_hash_commitment(hashed, predictions) is True


def test_verify_hash_commitment_invalid():
    predictions = [0.1, 0.2, 0.3]
    assert TaoshiProtocolAdapter.verify_hash_commitment("wrong_hash", predictions) is False


def test_verify_hash_commitment_none():
    predictions = [0.1, 0.2, 0.3]
    assert TaoshiProtocolAdapter.verify_hash_commitment(None, predictions) is False


class TestGetIncentiveScores:
    def test_returns_scores_for_known_hotkeys(self):
        from unittest.mock import MagicMock
        adapter = TaoshiProtocolAdapter(
            network="finney", endpoint="ws://localhost:9944",
            wallet_name="w", hotkey_path="", hotkey="h", subnet_uid=8,
        )
        mg = MagicMock()
        mg.hotkeys = ["5Fhot1", "5Fhot2", "5Fhot3"]
        mg.I = [0.1, 0.5, 0.3]
        adapter._metagraph = mg

        scores = adapter.get_incentive_scores(["5Fhot1", "5Fhot3"])
        assert scores == {"5Fhot1": 0.1, "5Fhot3": 0.3}

    def test_missing_hotkey_returns_zero(self):
        from unittest.mock import MagicMock
        adapter = TaoshiProtocolAdapter(
            network="finney", endpoint="ws://localhost:9944",
            wallet_name="w", hotkey_path="", hotkey="h", subnet_uid=8,
        )
        mg = MagicMock()
        mg.hotkeys = ["5Fhot1"]
        mg.I = [0.5]
        adapter._metagraph = mg

        scores = adapter.get_incentive_scores(["5Fhot1", "5Funknown"])
        assert scores["5Fhot1"] == 0.5
        assert scores["5Funknown"] == 0.0

    def test_no_metagraph_returns_all_zeros(self):
        adapter = TaoshiProtocolAdapter(
            network="finney", endpoint="ws://localhost:9944",
            wallet_name="w", hotkey_path="", hotkey="h", subnet_uid=8,
        )
        adapter._metagraph = None
        scores = adapter.get_incentive_scores(["5Fhot1"])
        assert scores == {"5Fhot1": 0.0}
