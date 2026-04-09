import pytest
from fastapi.testclient import TestClient
from api.app import create_app

app = create_app()
client = TestClient(app)

def test_get_thoughts():
    response = client.get("/api/v1/agents/test_agent/thoughts?limit=5")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_copilot_chat():
    payload = {
        "message": "Why did VWAP fail?",
        "thought_id": "00000000-0000-0000-0000-000000000000"
    }
    response = client.post("/api/v1/agents/copilot/chat", json=payload)
    assert response.status_code == 200
    assert "response" in response.json()
