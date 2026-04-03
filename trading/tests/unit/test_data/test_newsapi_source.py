"""Unit tests for NewsAPISource."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestNewsSignalSchema:
    def test_news_signal_fields(self):
        from data.sources.newsapi import NewsSignal
        sig = NewsSignal(
            contract_ticker="MKT-001",
            headline="Fed raises rates",
            url="https://example.com/article",
            published_at=datetime(2026, 3, 27, tzinfo=timezone.utc),
            relevance=0.85,
            sentiment="bullish_yes",
            mispricing_score=0.42,
            scored_at=datetime(2026, 3, 27, tzinfo=timezone.utc),
        )
        assert sig.contract_ticker == "MKT-001"
        assert sig.relevance == 0.85
        assert sig.sentiment == "bullish_yes"
        assert sig.mispricing_score == 0.42

    def test_news_signal_sentiment_values(self):
        from data.sources.newsapi import NewsSignal
        for sentiment in ("bullish_yes", "bearish_yes", "neutral"):
            sig = NewsSignal(
                contract_ticker="X",
                headline="test",
                url="https://example.com",
                published_at=datetime.now(timezone.utc),
                relevance=0.5,
                sentiment=sentiment,
                mispricing_score=0.0,
                scored_at=datetime.now(timezone.utc),
            )
            assert sig.sentiment == sentiment


class TestNewsAPISourceFetch:
    @pytest.mark.asyncio
    async def test_fetch_headlines_returns_articles(self):
        from data.sources.newsapi import NewsAPISource

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "articles": [
                {
                    "title": "Fed raises rates sharply",
                    "url": "https://example.com/1",
                    "publishedAt": "2026-03-27T10:00:00Z",
                },
                {
                    "title": "Markets rally on news",
                    "url": "https://example.com/2",
                    "publishedAt": "2026-03-27T11:00:00Z",
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        source = NewsAPISource(api_key="test-key")

        with patch("httpx.AsyncClient", return_value=mock_client):
            articles = await source._fetch_headlines(query="economics")

        assert len(articles) == 2
        assert articles[0]["title"] == "Fed raises rates sharply"

    @pytest.mark.asyncio
    async def test_fetch_headlines_returns_empty_on_error(self):
        from data.sources.newsapi import NewsAPISource

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("network error"))

        source = NewsAPISource(api_key="test-key")

        with patch("httpx.AsyncClient", return_value=mock_client):
            articles = await source._fetch_headlines(query="economics")

        assert articles == []


class TestNewsAPISourceScoring:
    @pytest.mark.asyncio
    async def test_score_headline_returns_news_signal(self):
        from data.sources.newsapi import NewsAPISource, NewsSignal

        mock_llm = AsyncMock()
        mock_llm.score_headline = AsyncMock(return_value=MagicMock(relevance=0.9, sentiment="bullish_yes", mispricing_score=0.35))
        source = NewsAPISource(api_key="test-key", llm_client=mock_llm)

        signal = await source._score_headline(
            contract_ticker="MKT-001",
            contract_title="Will the Fed raise rates in 2026?",
            headline="Fed raises rates sharply",
            url="https://example.com",
            published_at=datetime(2026, 3, 27, tzinfo=timezone.utc),
        )

        assert isinstance(signal, NewsSignal)
        assert signal.contract_ticker == "MKT-001"
        assert signal.relevance == 0.9
        assert signal.sentiment == "bullish_yes"
        assert signal.mispricing_score == 0.35

    @pytest.mark.asyncio
    async def test_score_headline_returns_none_on_llm_error(self):
        from data.sources.newsapi import NewsAPISource

        mock_llm = AsyncMock()
        mock_llm.score_headline = AsyncMock(side_effect=Exception("LLM error"))
        source = NewsAPISource(api_key="test-key", llm_client=mock_llm)

        signal = await source._score_headline(
            contract_ticker="MKT-001",
            contract_title="Will X happen?",
            headline="Unrelated headline",
            url="https://example.com",
            published_at=datetime.now(timezone.utc),
        )

        assert signal is None
