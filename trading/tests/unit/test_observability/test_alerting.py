import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from observability.alerting import AlertRouter


def _make_notifier():
    n = MagicMock()
    n.send_text = AsyncMock()
    return n


@pytest.mark.asyncio
async def test_critical_fires_immediately():
    notifier = _make_notifier()
    router = AlertRouter(notifier=notifier)
    await router.fire("critical", "kill_switch_triggered", "Kill switch hit", {})
    notifier.send_text.assert_awaited_once()
    call_msg = notifier.send_text.call_args[0][0]
    assert "CRITICAL" in call_msg
    assert "Kill switch hit" in call_msg


@pytest.mark.asyncio
async def test_info_does_not_notify():
    notifier = _make_notifier()
    router = AlertRouter(notifier=notifier)
    await router.fire("info", "trade_executed", "Trade done", {})
    notifier.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_warning_buffered_not_immediate():
    notifier = _make_notifier()
    router = AlertRouter(notifier=notifier)
    await router.fire("warning", "slippage_elevated", "Slippage high", {})
    notifier.send_text.assert_not_awaited()
    assert len(router._warning_buffer) == 1


@pytest.mark.asyncio
async def test_warning_flush_sends_digest():
    notifier = _make_notifier()
    router = AlertRouter(notifier=notifier)
    await router.fire("warning", "slippage_elevated", "Slippage high on AAPL", {})
    await router.fire("warning", "fill_rate_degrading", "Fill rate low", {})
    await router.flush_warnings()
    notifier.send_text.assert_awaited_once()
    msg = notifier.send_text.call_args[0][0]
    assert "WARNING DIGEST" in msg
    assert "Slippage high on AAPL" in msg
    assert "Fill rate low" in msg
    assert len(router._warning_buffer) == 0
