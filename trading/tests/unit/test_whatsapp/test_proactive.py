import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from whatsapp.proactive import HermesProactiveOps


@pytest.fixture
def mock_assistant():
    assistant = MagicMock()
    assistant._client = MagicMock()
    assistant._client.send_text = AsyncMock()
    assistant._broker = MagicMock()
    assistant._broker.connection.is_connected = MagicMock(return_value=True)
    assistant._broker.check_health = AsyncMock(return_value=True)

    assistant._db = MagicMock()
    assistant._brief_generator = MagicMock()
    assistant._brief_generator.get_or_generate = AsyncMock(
        return_value={"date": "2023-10-10", "brief": "Market is up!"}
    )

    assistant._runner = MagicMock()
    assistant._opp_store = MagicMock()
    assistant._journal_service = MagicMock()

    return assistant


@pytest.mark.asyncio
async def test_health_monitor_healthy(mock_assistant):
    ops = HermesProactiveOps(mock_assistant, ["+1234567890"])

    # We shouldn't send anything if it's healthy
    # Quick loop execution by mocking sleep to cancel the task
    async def mock_sleep_cancel(*args, **kwargs):
        raise asyncio.CancelledError()

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_sleep.side_effect = mock_sleep_cancel
        ops._running = True
        await ops._health_monitor_loop()

    mock_assistant._client.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_health_monitor_unhealthy(mock_assistant):
    ops = HermesProactiveOps(mock_assistant, ["+1234567890"])

    # Simulate DB/broker failure
    mock_assistant._broker.connection.is_connected.return_value = False

    # Mock subprocess execution
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"Error details in log", b""))

    async def mock_sleep_series(*args, **kwargs):
        # Allow the first sleep, then cancel on the second backoff sleep
        if mock_sleep_series.call_count == 0:
            mock_sleep_series.call_count += 1
            return
        raise asyncio.CancelledError()

    mock_sleep_series.call_count = 0

    with (
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch(
            "asyncio.create_subprocess_shell", AsyncMock(return_value=mock_proc)
        ) as mock_shell,
    ):
        mock_sleep.side_effect = mock_sleep_series
        ops._running = True
        await ops._health_monitor_loop()

        mock_shell.assert_called_once()
        mock_assistant._client.send_text.assert_called_once()

        call_arg = mock_assistant._client.send_text.call_args[0][1]
        assert "Error details in log" in call_arg
        assert "Hermes Health Alert" in call_arg


@pytest.mark.asyncio
async def test_daily_briefing(mock_assistant):
    ops = HermesProactiveOps(mock_assistant, ["+1234567890"])

    async def mock_sleep_series(*args, **kwargs):
        if mock_sleep_series.call_count == 0:
            mock_sleep_series.call_count += 1
            return
        raise asyncio.CancelledError()

    mock_sleep_series.call_count = 0

    mock_now = MagicMock()
    mock_now.hour = 8
    mock_now.minute = 30
    mock_now.strftime.return_value = "2023-10-10"

    with (
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("whatsapp.proactive.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = mock_now

        mock_sleep.side_effect = mock_sleep_series
        ops._running = True
        await ops._daily_briefing_loop()

        mock_assistant._brief_generator.get_or_generate.assert_called_once()
        mock_assistant._client.send_text.assert_called_once()
        call_arg = mock_assistant._client.send_text.call_args[0][1]
        assert "Morning Brief" in call_arg
