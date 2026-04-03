def test_health_connected(client):
    resp = client.get("/health", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "brokers" in data


def test_health_disconnected(client, mock_broker):
    mock_broker.connection.is_connected.return_value = False
    resp = client.get("/health", headers={"X-API-Key": "test-key"})
    data = resp.json()
    assert "brokers" in data
    # At least one broker should show disconnected
    ibkr = data["brokers"].get("ibkr", {})
    assert ibkr.get("connected") is False
