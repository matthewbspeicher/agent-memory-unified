import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import PlainTextResponse
from api.middleware.gatekeeper import GatekeeperMiddleware
from models.user import PlatformTier

class MockUser:
    def __init__(self, tier):
        self.tier = tier

def create_test_app(tier=None):
    app = FastAPI()
    
    @app.middleware("http")
    async def mock_user_middleware(request: Request, call_next):
        if tier:
            request.state.user = MockUser(tier)
        return await call_next(request)
        
    app.add_middleware(GatekeeperMiddleware)
    
    @app.get("/test-json")
    async def test_json():
        return {
            "public_field": "visible",
            "whale_address": "0x123",
            "entry_price": 100.5,
            "nested": {
                "take_profit": 110.0,
                "other": "ok"
            },
            "list_data": [
                {"reasoning": "secret", "id": 1}
            ]
        }

    @app.get("/test-text")
    async def test_text():
        return PlainTextResponse("Hello World")
        
    return app

def test_gatekeeper_explorer():
    app = create_test_app(PlatformTier.EXPLORER)
    client = TestClient(app)
    
    response = client.get("/test-json")
    assert response.status_code == 200
    data = response.json()
    
    assert data["public_field"] == "visible"
    assert data["whale_address"] == "locked"
    assert data["entry_price"] == "locked"
    assert data["nested"]["take_profit"] == "locked"
    assert data["nested"]["other"] == "ok"
    assert data["list_data"][0]["reasoning"] == "locked"
    assert data["list_data"][0]["id"] == 1

def test_gatekeeper_trader():
    app = create_test_app(PlatformTier.TRADER)
    client = TestClient(app)
    
    response = client.get("/test-json")
    assert response.status_code == 200
    data = response.json()
    
    assert data["public_field"] == "visible"
    assert data["whale_address"] == "0x123"
    assert data["entry_price"] == 100.5
    assert data["nested"]["take_profit"] == 110.0
    assert data["nested"]["other"] == "ok"
    assert data["list_data"][0]["reasoning"] == "secret"
    assert data["list_data"][0]["id"] == 1

def test_gatekeeper_no_user():
    app = create_test_app(None)
    client = TestClient(app)
    
    response = client.get("/test-json")
    assert response.status_code == 200
    data = response.json()
    
    assert data["public_field"] == "visible"
    assert data["whale_address"] == "locked"

def test_gatekeeper_non_json():
    app = create_test_app(PlatformTier.EXPLORER)
    client = TestClient(app)
    
    response = client.get("/test-text")
    assert response.status_code == 200
    assert response.text == "Hello World"
