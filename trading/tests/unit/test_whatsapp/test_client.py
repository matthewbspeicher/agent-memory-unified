import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from whatsapp.client import WhatsAppClient


@pytest.fixture
def client():
    return WhatsAppClient(
        phone_id="123456",
        token="test-token",
        app_secret="test-secret",
    )


@pytest.mark.asyncio
async def test_send_text(client):
    with patch("whatsapp.client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=MagicMock(status_code=200))

        await client.send_text("15551234567", "Hello")

        mock_http.post.assert_called_once()
        call_kwargs = mock_http.post.call_args
        assert call_kwargs[1]["json"]["type"] == "text"
        assert call_kwargs[1]["json"]["text"]["body"] == "Hello"


@pytest.mark.asyncio
async def test_send_template(client):
    with patch("whatsapp.client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=MagicMock(status_code=200))

        await client.send_template(
            "15551234567", "opportunity_alert", ["RSI Agent", "AAPL", "BUY", "0.85"]
        )

        mock_http.post.assert_called_once()
        call_kwargs = mock_http.post.call_args
        assert call_kwargs[1]["json"]["type"] == "template"


@pytest.mark.asyncio
async def test_24h_window_freeform(client):
    client.record_inbound("15551234567")
    assert client.is_within_window("15551234567") is True


@pytest.mark.asyncio
async def test_24h_window_expired(client):
    client._sessions["15551234567"] = datetime.now(timezone.utc) - timedelta(hours=25)
    assert client.is_within_window("15551234567") is False


@pytest.mark.asyncio
async def test_mark_read(client):
    with patch("whatsapp.client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=MagicMock(status_code=200))

        await client.mark_read("msg-123")
        mock_http.post.assert_called_once()
