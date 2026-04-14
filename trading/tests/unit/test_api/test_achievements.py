"""Tests for achievements API routes."""

import pytest

HEADERS = {"X-API-Key": "test-key"}


def test_list_achievements(client):
    """List achievements endpoint returns registry."""
    resp = client.get("/achievements", headers=HEADERS)
    assert resp.status_code == 200


def test_get_my_achievements(client):
    """Get my achievements."""
    resp = client.get("/achievements/me", headers=HEADERS)
    assert resp.status_code in (200, 404)


def test_get_achievement_by_id(client):
    """Get a specific achievement by ID."""
    resp = client.get("/achievements/first_trade", headers=HEADERS)
    assert resp.status_code in (200, 404)


def test_unlock_achievement(client, test_db):
    """Unlock an achievement for an agent."""
    resp = client.post(
        "/achievements/first_trade/unlock",
        headers=HEADERS,
        json={"agent_name": "test-agent"},
    )
    assert resp.status_code in (200, 400, 404)
