def test_missing_api_key(client):
    resp = client.get("/health")
    assert resp.status_code in (401, 403)


def test_wrong_api_key(client):
    resp = client.get("/health", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_valid_api_key(client):
    resp = client.get("/health", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
