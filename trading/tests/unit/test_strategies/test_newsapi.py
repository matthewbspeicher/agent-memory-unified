"""Tests for NewsAPI wiring in kalshi_news_arb and polymarket_news_arb (Task 3)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.models import AgentConfig, ActionLevel


def _make_config(strategy: str, **params) -> AgentConfig:
    return AgentConfig(
        name=f"test_{strategy}",
        strategy=strategy,
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        parameters=params,
    )


# ---------------------------------------------------------------------------
# _fetch_newsapi_headlines (module-level helper in kalshi_news_arb)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kalshi_fetch_newsapi_headlines_returns_titles():
    from strategies.kalshi_news_arb import _fetch_newsapi_headlines

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "articles": [
            {"title": "Headline One", "description": "..."},
            {"title": "Headline Two", "description": "..."},
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await _fetch_newsapi_headlines("finance", "test-key", page_size=5)

    assert result == ["Headline One", "Headline Two"]


@pytest.mark.asyncio
async def test_kalshi_fetch_newsapi_headlines_returns_empty_on_error():
    from strategies.kalshi_news_arb import _fetch_newsapi_headlines

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("network error"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await _fetch_newsapi_headlines("finance", "test-key")

    assert result == []


# ---------------------------------------------------------------------------
# KalshiNewsArbAgent — NewsAPI preference over RSS
# ---------------------------------------------------------------------------


class TestKalshiNewsArbNewsAPI:
    def _agent(self, **params):
        from strategies.kalshi_news_arb import KalshiNewsArbAgent

        defaults = dict(
            threshold_cents=15, min_volume=100, max_markets_per_scan=5, rss_feeds=[]
        )
        cfg = _make_config("kalshi_news_arb", **{**defaults, **params})
        return KalshiNewsArbAgent(cfg)

    @pytest.mark.asyncio
    async def test_uses_newsapi_when_key_in_params(self):
        """With newsapi_key in params, _fetch_newsapi_headlines is called (not RSS)."""
        agent = self._agent(newsapi_key="news-key", rss_feeds=["http://rss.feed"])
        bus = MagicMock()
        bus._kalshi_source = AsyncMock()
        bus._kalshi_source.get_markets.return_value = []
        bus._settings = None
        bus._anthropic_key = "sk-test"

        with (
            patch(
                "strategies.kalshi_news_arb._fetch_newsapi_headlines",
                new=AsyncMock(return_value=["NewsAPI headline"]),
            ) as mock_newsapi,
            patch(
                "strategies.kalshi_news_arb._fetch_headlines",
                new=AsyncMock(return_value=["RSS headline"]),
            ) as mock_rss,
        ):
            await agent.scan(bus)

        mock_newsapi.assert_awaited_once()
        mock_rss.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_to_rss_when_no_newsapi_key(self):
        """Without newsapi_key, RSS fetching is used."""
        agent = self._agent(rss_feeds=["http://rss.feed"])
        bus = MagicMock()
        bus._kalshi_source = AsyncMock()
        bus._kalshi_source.get_markets.return_value = []
        bus._settings = None
        bus._anthropic_key = "sk-test"

        with (
            patch(
                "strategies.kalshi_news_arb._fetch_newsapi_headlines",
                new=AsyncMock(return_value=[]),
            ) as mock_newsapi,
            patch(
                "strategies.kalshi_news_arb._fetch_headlines",
                new=AsyncMock(return_value=["RSS headline"]),
            ) as mock_rss,
        ):
            await agent.scan(bus)

        mock_newsapi.assert_not_awaited()
        mock_rss.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_newsapi_key_falls_back_from_settings(self):
        """newsapi_key is picked up from bus._settings when not in agent params."""
        agent = self._agent(rss_feeds=[])
        bus = MagicMock()
        bus._kalshi_source = AsyncMock()
        bus._kalshi_source.get_markets.return_value = []
        settings = MagicMock()
        settings.newsapi_key = "settings-news-key"
        bus._settings = settings
        bus._anthropic_key = "sk-test"

        with patch(
            "strategies.kalshi_news_arb._fetch_newsapi_headlines",
            new=AsyncMock(return_value=["NewsAPI headline from settings"]),
        ) as mock_newsapi:
            await agent.scan(bus)

        mock_newsapi.assert_awaited_once()


# ---------------------------------------------------------------------------
# PolymarketNewsArbAgent — NewsAPI preference over RSS
# ---------------------------------------------------------------------------


class TestPolymarketNewsArbNewsAPI:
    def _agent(self, settings=None, **params):
        from strategies.polymarket_news_arb import PolymarketNewsArbAgent

        defaults = dict(
            threshold_cents=15, min_volume=100, max_markets_per_scan=5, rss_feeds=[]
        )
        cfg = _make_config("polymarket_news_arb", **{**defaults, **params})
        return PolymarketNewsArbAgent(cfg, settings=settings)

    @pytest.mark.asyncio
    async def test_uses_newsapi_when_key_configured(self):
        """_fetch_newsapi_headlines is called when newsapi_key is set."""
        agent = self._agent(newsapi_key="news-key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"articles": [{"title": "NewsAPI Headline"}]}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            headlines = await agent._fetch_recent_headlines()

        assert headlines == ["NewsAPI Headline"]

    @pytest.mark.asyncio
    async def test_falls_back_to_rss_when_no_newsapi_key(self):
        """Without newsapi_key, _fetch_recent_headlines uses RSS feeds."""

        agent = self._agent(rss_feeds=["http://rss.feed"])
        assert agent.newsapi_key is None

        rss_xml = """<?xml version="1.0"?>
        <rss><channel>
          <item><title>RSS Headline 1</title></item>
          <item><title>RSS Headline 2</title></item>
        </channel></rss>"""

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = rss_xml

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            headlines = await agent._fetch_recent_headlines()

        assert "RSS Headline 1" in headlines
        assert "RSS Headline 2" in headlines

    def test_newsapi_key_from_settings(self):
        settings = MagicMock()
        settings.newsapi_key = "settings-key"
        agent = self._agent(settings=settings)
        assert agent.newsapi_key == "settings-key"

    def test_newsapi_key_params_takes_priority(self):
        settings = MagicMock()
        settings.newsapi_key = "settings-key"
        agent = self._agent(settings=settings, newsapi_key="param-key")
        assert agent.newsapi_key == "param-key"
