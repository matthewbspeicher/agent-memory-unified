from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from integrations.bittensor.adapter import TaoshiProtocolAdapter


class TestAdapterRetry:
    @pytest.mark.asyncio
    async def test_connect_retries_on_failure(self):
        """connect() should retry up to max_retries on failure."""
        adapter = TaoshiProtocolAdapter(
            network="finney",
            endpoint="wss://fake:443",
            wallet_name="test",
            hotkey_path="/tmp",
            hotkey="test_hotkey",
            subnet_uid=8,
        )

        call_count = 0

        def mock_subtensor(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("chain unreachable")
            return MagicMock()

        with patch.dict("sys.modules", {"bittensor": MagicMock()}) as _:
            import sys

            mock_bt = sys.modules["bittensor"]
            mock_bt.subtensor = mock_subtensor
            mock_bt.wallet = MagicMock(return_value=MagicMock())
            mock_bt.dendrite = MagicMock(return_value=MagicMock())

            await adapter.connect(max_retries=3, retry_delay=0.01)

        assert call_count == 3
        assert adapter._subtensor is not None

    @pytest.mark.asyncio
    async def test_connect_raises_after_max_retries(self):
        adapter = TaoshiProtocolAdapter(
            network="finney",
            endpoint="wss://fake:443",
            wallet_name="test",
            hotkey_path="/tmp",
            hotkey="test_hotkey",
            subnet_uid=8,
        )

        with patch.dict("sys.modules", {"bittensor": MagicMock()}) as _:
            import sys

            mock_bt = sys.modules["bittensor"]
            mock_bt.subtensor = MagicMock(side_effect=ConnectionError("down"))

            with pytest.raises(ConnectionError, match="down"):
                await adapter.connect(max_retries=2, retry_delay=0.01)

    @pytest.mark.asyncio
    async def test_connect_succeeds_first_try(self):
        adapter = TaoshiProtocolAdapter(
            network="finney",
            endpoint="wss://fake:443",
            wallet_name="test",
            hotkey_path="/tmp",
            hotkey="test_hotkey",
            subnet_uid=8,
        )

        with patch.dict("sys.modules", {"bittensor": MagicMock()}) as _:
            import sys

            mock_bt = sys.modules["bittensor"]
            mock_bt.subtensor = MagicMock(return_value=MagicMock())
            mock_bt.wallet = MagicMock(return_value=MagicMock())
            mock_bt.dendrite = MagicMock(return_value=MagicMock())

            await adapter.connect(max_retries=3, retry_delay=0.01)

        assert adapter._subtensor is not None
        assert adapter._wallet is not None
        assert adapter._dendrite is not None
