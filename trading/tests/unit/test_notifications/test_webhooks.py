import pytest
from unittest.mock import patch, AsyncMock
from agents.models import Opportunity
from broker.models import Symbol, AssetType
from datetime import datetime
from notifications.slack import SlackNotifier
from notifications.composite import CompositeNotifier

def _opp():
    return Opportunity(
        id="opp-123",
        agent_name="test-agent",
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        signal="BUY",
        confidence=0.9,
        reasoning="Test reasoning block",
        data={},
        timestamp=datetime.now()
    )

@pytest.mark.asyncio
async def test_slack_notifier():
    notifier = SlackNotifier(webhook_url="http://dummy/slack", api_base_url="http://localhost:8000", api_key="test-key")
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        await notifier.send(_opp())
        mock_post.assert_awaited_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://dummy/slack"
        payload = kwargs["json"]
        assert "blocks" in payload
        # Ensure buttons are appended
        actions = [b for b in payload["blocks"] if b.get("type") == "actions"]
        assert len(actions) == 1
        assert "http://localhost:8000/opportunities/opp-123/approve" in str(actions[0])

@pytest.mark.asyncio
async def test_slack_notifier_no_url():
    notifier = SlackNotifier(webhook_url="")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        await notifier.send(_opp())
        mock_post.assert_not_called()

@pytest.mark.asyncio
async def test_composite_notifier():
    mock1 = AsyncMock()
    mock2 = AsyncMock()

    class N1:
        async def send(self, opp): await mock1()
        
    class N2:
        async def send(self, opp): await mock2()

    notifier = CompositeNotifier([N1(), N2()])
    await notifier.send(_opp())
    
    mock1.assert_awaited_once()
    mock2.assert_awaited_once()
