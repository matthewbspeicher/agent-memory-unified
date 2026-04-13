from fastapi.testclient import TestClient
from api.app import create_app


def test_public_status_returns_version_and_served_by():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "1.0"
    assert data["name"] == "agent-memory-unified"
    assert "version" in data
    assert "uptime_seconds" in data
    assert data["served_by"] == "agent-memory-unified"
    assert data["docs"] == "/FOR_AGENTS.md"
