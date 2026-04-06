import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from agents.models import Opportunity, OpportunityStatus, ActionLevel
from broker.models import Symbol, AssetType, MarketOrder, OrderSide
from decimal import Decimal
from notifications.whatsapp import WhatsAppNotifier


def _make_opportunity(needs_approval=False, auto_executed=False):
    opp = Opportunity(
        id="opp-1",
        agent_name="rsi-scanner",
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        signal="RSI_OVERSOLD",
        confidence=0.87,
        reasoning="RSI dropped below 30 on the daily chart for AAPL",
        data={},
        timestamp=datetime.now(timezone.utc),
        status=OpportunityStatus.EXECUTED
        if auto_executed
        else OpportunityStatus.PENDING,
    )
    if auto_executed:
        opp.suggested_trade = MarketOrder(
            symbol=opp.symbol,
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            account_id="U123",
        )
    return opp


@pytest.fixture
def notifier():
    client = AsyncMock()
    client.is_within_window = MagicMock(return_value=True)
    return WhatsAppNotifier(
        client=client,
        allowed_numbers=["15551234567"],
        action_level=ActionLevel.SUGGEST_TRADE,
    )


@pytest.mark.asyncio
async def test_sends_opportunity_alert(notifier):
    opp = _make_opportunity()
    await notifier.send(opp)
    notifier._client.send_text.assert_called_once()
    msg = notifier._client.send_text.call_args[0][1]
    assert "AAPL" in msg
    assert "rsi-scanner" in msg


@pytest.mark.asyncio
async def test_sends_approval_instructions(notifier):
    opp = _make_opportunity()
    await notifier.send(opp)
    msg = notifier._client.send_text.call_args[0][1]
    assert "APPROVE" in msg
    assert "opp-1" in msg


@pytest.mark.asyncio
async def test_uses_template_outside_window(notifier):
    notifier._client.is_within_window = MagicMock(return_value=False)
    opp = _make_opportunity()
    await notifier.send(opp)
    notifier._client.send_template.assert_called_once()


@pytest.mark.asyncio
async def test_skips_when_no_allowed_numbers():
    client = AsyncMock()
    n = WhatsAppNotifier(
        client=client, allowed_numbers=[], action_level=ActionLevel.NOTIFY
    )
    await n.send(_make_opportunity())
    client.send_text.assert_not_called()
    client.send_template.assert_not_called()


@pytest.mark.asyncio
async def test_send_text_calls_client():
    client = MagicMock()
    client.send_text = AsyncMock()
    from notifications.whatsapp import WhatsAppNotifier
    from agents.models import ActionLevel

    notifier = WhatsAppNotifier(
        client=client,
        allowed_numbers=["1234567890"],
        action_level=ActionLevel.NOTIFY,
    )
    await notifier.send_text("CRITICAL | test alert")
    client.send_text.assert_awaited()
    call_args = client.send_text.call_args
    assert "CRITICAL | test alert" in str(call_args)
