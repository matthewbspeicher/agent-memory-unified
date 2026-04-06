# python/tests/unit/test_api/test_markets_browser.py
from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from broker.models import PredictionContract
from api.routes.markets_browser import router


def _contract(
    ticker: str, title: str = "Test", yes_bid: int = 50
) -> PredictionContract:
    return PredictionContract(
        ticker=ticker,
        title=title,
        category="politics",
        close_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        yes_bid=yes_bid,
        yes_ask=yes_bid + 4,
        yes_last=yes_bid,
        volume_24h=1000,
    )


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def client(app):
    import os

    os.environ["STA_API_KEY"] = "test-key"
    # Clear lru_cache so the test key takes effect
    from api.auth import _get_settings

    _get_settings.cache_clear()

    kalshi_source = AsyncMock()
    kalshi_source.get_markets = AsyncMock(
        return_value=[_contract("K1", "Fed rate hike May", 48)]
    )
    poly_source = AsyncMock()
    poly_source.get_markets = AsyncMock(
        return_value=[_contract("P1", "Fed rate hike May", 62)]
    )

    bus = MagicMock()
    bus._kalshi_source = kalshi_source
    bus._polymarket_source = poly_source

    app.state.data_bus = bus
    app.state.spread_store = None
    return TestClient(app)


class TestListMarkets:
    def test_basic_response(self, client):
        r = client.get("/markets", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert "kalshi" in data
        assert "polymarket" in data

    def test_include_matches_returns_matches(self, client):
        r = client.get("/markets?include_matches=true", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert "matches" in data
        assert isinstance(data["matches"], list)

    def test_include_matches_has_required_fields(self, client):
        r = client.get("/markets?include_matches=true", headers=HEADERS)
        data = r.json()
        if data["matches"]:
            m = data["matches"][0]
            assert "kalshi_ticker" in m
            assert "poly_ticker" in m
            assert "final_score" in m
            assert "gap_cents" in m

    def test_without_include_matches_no_matches_key(self, client):
        r = client.get("/markets", headers=HEADERS)
        data = r.json()
        assert "matches" not in data


class TestSpreadHistory:
    def test_returns_empty_without_spread_store(self, client, app):
        app.state.spread_store = None
        r = client.get(
            "/markets/spreads/history?kalshi_ticker=K1&poly_ticker=P1",
            headers=HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["observations"] == []

    def test_returns_history_from_store(self, client, app):
        from storage.spreads import SpreadObservation

        mock_store = AsyncMock()
        mock_store.get_history = AsyncMock(
            return_value=[
                SpreadObservation(
                    kalshi_ticker="K1",
                    poly_ticker="P1",
                    match_score=0.7,
                    kalshi_cents=48,
                    poly_cents=60,
                    gap_cents=12,
                    observed_at="2026-03-28T10:00:00+00:00",
                )
            ]
        )
        app.state.spread_store = mock_store
        r = client.get(
            "/markets/spreads/history?kalshi_ticker=K1&poly_ticker=P1&hours=24",
            headers=HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["observations"]) == 1
        assert data["max_gap"] == 12
        assert data["current_gap"] == 12


class TestTopSpreads:
    def test_returns_empty_without_store(self, client, app):
        app.state.spread_store = None
        r = client.get("/markets/spreads/top", headers=HEADERS)
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_top_spreads(self, client, app):
        mock_store = AsyncMock()
        mock_store.get_top_spreads = AsyncMock(
            return_value=[
                {
                    "kalshi_ticker": "K1",
                    "poly_ticker": "P1",
                    "gap_cents": 15,
                    "match_score": 0.8,
                    "kalshi_cents": 45,
                    "poly_cents": 60,
                    "observed_at": "2026-03-28T10:00:00+00:00",
                },
            ]
        )
        app.state.spread_store = mock_store
        r = client.get("/markets/spreads/top", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["gap_cents"] == 15
