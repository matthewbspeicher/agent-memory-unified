import pytest
from fastapi.testclient import TestClient
from api.app import create_app


@pytest.mark.integration
def test_anonymous_tier_rate_limit_on_public_status():
    """11 rapid requests from the same IP should see 10 x 200 and then 1 x 429."""
    app = create_app()
    client = TestClient(app)

    success_count = 0
    rate_limited_count = 0

    for _ in range(11):
        resp = client.get("/engine/v1/public/status")
        if resp.status_code == 200:
            success_count += 1
        elif resp.status_code == 429:
            rate_limited_count += 1
            assert "retry_after_seconds" in resp.json() or "retry-after" in resp.headers

    assert success_count == 10, f"Expected 10 x 200, got {success_count}"
    assert rate_limited_count == 1, f"Expected 1 x 429, got {rate_limited_count}"
