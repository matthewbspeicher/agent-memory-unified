def test_health_internal_no_auth(client):
    resp = client.get("/health-internal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "unhealthy")
