from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from integrations.bittensor.adapter import TaoshiProtocolAdapter


def _make_adapter():
    return TaoshiProtocolAdapter(
        network="finney",
        endpoint="wss://fake:443",
        wallet_name="test",
        hotkey_path="/tmp",
        hotkey="test_hotkey",
        subnet_uid=8,
    )


class TestAdapterRetry:
    @pytest.mark.asyncio
    async def test_connect_retries_on_failure(self):
        """connect() should retry up to max_retries on failure."""
        adapter = _make_adapter()

        call_count = 0

        def mock_subtensor(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("chain unreachable")
            return MagicMock()

        mock_bt = MagicMock()
        # The adapter does getattr(bt, "Subtensor", None) — set capitalized attrs
        mock_bt.Subtensor = mock_subtensor
        mock_bt.Wallet = MagicMock(return_value=MagicMock())
        mock_bt.Dendrite = MagicMock(return_value=MagicMock())

        with patch.dict("sys.modules", {"bittensor": mock_bt}):
            await adapter.connect(max_retries=3, retry_delay=0.01)

        assert call_count == 3
        assert adapter._subtensor is not None

    @pytest.mark.asyncio
    async def test_connect_raises_after_max_retries(self):
        adapter = _make_adapter()

        mock_bt = MagicMock()
        mock_bt.Subtensor = MagicMock(side_effect=ConnectionError("down"))

        with patch.dict("sys.modules", {"bittensor": mock_bt}):
            with pytest.raises(ConnectionError, match="down"):
                await adapter.connect(max_retries=2, retry_delay=0.01)

    @pytest.mark.asyncio
    async def test_connect_succeeds_first_try(self):
        adapter = _make_adapter()

        mock_bt = MagicMock()
        mock_bt.Subtensor = MagicMock(return_value=MagicMock())
        mock_bt.Wallet = MagicMock(return_value=MagicMock())
        mock_bt.Dendrite = MagicMock(return_value=MagicMock())

        with patch.dict("sys.modules", {"bittensor": mock_bt}):
            await adapter.connect(max_retries=3, retry_delay=0.01)

        assert adapter._subtensor is not None
        assert adapter._wallet is not None
        assert adapter._dendrite is not None
