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


def test_public_agents_lists_internal_agents():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert isinstance(data["agents"], list)
    for agent in data["agents"]:
        assert "name" in agent
        assert "strategy" in agent
        assert "description" in agent
        forbidden = {"api_key", "token", "secret", "private_key", "internal_id"}
        assert not (forbidden & set(agent.keys()))


def test_public_arena_state_returns_safe_subset():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/arena/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "current_match" in data or data.get("note")
    assert "top_leaderboard" in data
    assert data["served_by"] == "agent-memory-unified"


def test_public_leaderboard_returns_top_50_or_fewer():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "leaderboard" in data
    assert len(data["leaderboard"]) <= 50
    assert "as_of" in data


def test_public_kg_entity_returns_facts():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/kg/entity/BTC")
    assert resp.status_code == 200
    data = resp.json()
    assert "entity" in data
    assert "facts" in data
    assert "count" in data


def test_public_kg_timeline_returns_chronological():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/kg/timeline?entity=BTC&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "timeline" in data


def test_public_milestones_returns_posted_entries():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/engine/v1/public/milestones")
    assert resp.status_code == 200
    data = resp.json()
    assert "milestones" in data
    assert isinstance(data["milestones"], list)
