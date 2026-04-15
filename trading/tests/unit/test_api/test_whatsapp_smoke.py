import pytest
from unittest.mock import AsyncMock
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from api.routes.test import create_test_router
from api.auth import verify_api_key
from api.identity.dependencies import resolve_identity, Identity


async def _admin_identity():
    return Identity(name="master", scopes=frozenset(["admin", "*"]), tier="admin")


@pytest.fixture
def mock_wa_client():
    client = AsyncMock()
    client.send_text = AsyncMock(return_value=None)
    return client


@pytest.fixture
def app(mock_wa_client):
    app = FastAPI()
    router = create_test_router(wa_client=mock_wa_client, allowed_numbers="15551234567")
    app.include_router(router)
    app.dependency_overrides[verify_api_key] = lambda: "test-key"
    app.dependency_overrides[resolve_identity] = _admin_identity
    return app


@pytest.mark.asyncio
async def test_whatsapp_smoke_sends_message(app, mock_wa_client):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/test/whatsapp")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sent"] is True
        assert data["to"] == "15551234567"
        mock_wa_client.send_text.assert_called_once()


@pytest.mark.asyncio
async def test_whatsapp_smoke_no_client():
    app = FastAPI()
    router = create_test_router(wa_client=None, allowed_numbers=None)
    app.include_router(router)
    app.dependency_overrides[verify_api_key] = lambda: "test-key"
    app.dependency_overrides[resolve_identity] = _admin_identity
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/test/whatsapp")
        assert resp.status_code == 400
        assert "not configured" in resp.json()["detail"]
