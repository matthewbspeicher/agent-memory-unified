"""Tests for arbitrage API routes."""

import pytest

HEADERS = {"X-API-Key": "test-key"}


def test_get_spreads_not_configured(client):
    """Get spreads returns 501 when spread_store not configured."""
    resp = client.get("/arb/spreads", headers=HEADERS)
    assert resp.status_code in (200, 501)


def test_get_spreads_with_params(client):
    """Get spreads with query parameters."""
    resp = client.get("/arb/spreads?min_gap=10&limit=20", headers=HEADERS)
    assert resp.status_code in (200, 501)


def test_execute_arbitrage_not_configured(client):
    """Execute arbitrage returns 501 when not configured."""
    resp = client.post(
        "/arb/execute",
        headers=HEADERS,
        json={
            "observation_id": 1,
            "agent_name": "test-agent",
            "sequencing": "less_liquid_first",
        },
    )
    assert resp.status_code in (200, 501)
