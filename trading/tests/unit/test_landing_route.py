from fastapi.testclient import TestClient
from api.app import create_app


def test_landing_route_returns_welcome_dict():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == "1.0"
    assert data["name"] == "agent-memory-unified"
    assert "docs" in data
    assert "for_agents" in data["docs"]
    assert "agents_manifest" in data["docs"]
    assert "openapi" in data["docs"]
    assert "rate_limits" in data
    assert data["rate_limits"]["anonymous"] == "10 req/min"
    assert "contact" in data
    assert "abuse" in data["contact"]
