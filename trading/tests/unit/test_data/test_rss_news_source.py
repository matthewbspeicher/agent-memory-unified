"""Unit tests for RSSNewsSource."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


SAMPLE_RSS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Fed raises rates sharply</title>
      <link>https://example.com/fed-rates</link>
      <pubDate>Tue, 01 Apr 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Markets rally on earnings</title>
      <link>https://example.com/markets-rally</link>
      <pubDate>Tue, 01 Apr 2026 09:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Feed</title>
  <entry>
    <title>Oil prices surge</title>
    <link href="https://example.com/oil-surge"/>
    <published>2026-04-01T08:00:00Z</published>
  </entry>
</feed>
"""


def _make_mock_response(text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


class TestRSSFetchAndParse:
    @pytest.mark.asyncio
    async def test_fetch_parses_rss_articles(self):
        from data.sources.rss_news import RSSNewsSource

        source = RSSNewsSource(feed_urls=["https://example.com/rss"])
        mock_response = _make_mock_response(SAMPLE_RSS_XML)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            articles = await source._fetch_all_feeds()

        assert len(articles) == 2
        titles = {a.title for a in articles}
        assert "Fed raises rates sharply" in titles
        assert "Markets rally on earnings" in titles
        assert all(a.url.startswith("https://example.com/") for a in articles)

    @pytest.mark.asyncio
    async def test_fetch_parses_atom_feed(self):
        from data.sources.rss_news import RSSNewsSource

        source = RSSNewsSource(feed_urls=["https://example.com/atom"])
        mock_response = _make_mock_response(SAMPLE_ATOM_XML)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            articles = await source._fetch_all_feeds()

        assert len(articles) == 1
        assert articles[0].title == "Oil prices surge"
        assert articles[0].url == "https://example.com/oil-surge"

    @pytest.mark.asyncio
    async def test_fetch_skips_failed_feeds(self):
        from data.sources.rss_news import RSSNewsSource

        source = RSSNewsSource(
            feed_urls=[
                "https://example.com/bad",
                "https://example.com/good",
            ]
        )

        ok_response = _make_mock_response(SAMPLE_RSS_XML)

        async def get_side_effect(url, **kwargs):
            if "bad" in url:
                raise Exception("connection refused")
            return ok_response

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=get_side_effect)

        with patch("httpx.AsyncClient", return_value=mock_client):
            articles = await source._fetch_all_feeds()

        # 2 articles from the good feed only
        assert len(articles) == 2

    @pytest.mark.asyncio
    async def test_published_at_is_utc(self):
        from data.sources.rss_news import RSSNewsSource

        source = RSSNewsSource(feed_urls=["https://example.com/rss"])
        mock_response = _make_mock_response(SAMPLE_RSS_XML)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            articles = await source._fetch_all_feeds()

        for article in articles:
            assert article.published_at.tzinfo is not None
            assert (
                article.published_at.tzinfo == timezone.utc
                or article.published_at.utcoffset() == timedelta(0)
            )


class TestDedup:
    @pytest.mark.asyncio
    async def test_dedup_filters_seen_articles(self):
        from data.sources.rss_news import Article, RSSNewsSource

        source = RSSNewsSource(feed_urls=["https://example.com/rss"])
        now = datetime.now(timezone.utc)
        article = Article(
            title="Duplicate",
            url="https://example.com/dup",
            published_at=now,
            source_name="Test",
        )

        # First pass — both should pass through
        result1 = source._dedup([article])
        assert len(result1) == 1

        # Second pass — same URL should be filtered
        result2 = source._dedup([article])
        assert len(result2) == 0

    @pytest.mark.asyncio
    async def test_dedup_evicts_old_entries(self):
        from data.sources.rss_news import Article, RSSNewsSource
        import hashlib

        source = RSSNewsSource(feed_urls=["https://example.com/rss"])
        url = "https://example.com/old-article"
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]

        # Manually insert an old entry (>24h ago)
        stale_time = datetime.now(timezone.utc) - timedelta(hours=25)
        source._seen_urls[url_hash] = stale_time

        now = datetime.now(timezone.utc)
        article = Article(
            title="Old article",
            url=url,
            published_at=now,
            source_name="Test",
        )

        # Evict stale entries, then dedup — article should pass through
        source._evict_stale()
        result = source._dedup([article])
        assert len(result) == 1


class TestGetHeadlines:
    @pytest.mark.asyncio
    async def test_get_headlines_returns_cached_articles(self):
        from data.sources.rss_news import Article, RSSNewsSource

        source = RSSNewsSource(feed_urls=["https://example.com/rss"])
        now = datetime.now(timezone.utc)
        source._latest_articles = [
            Article(
                title="Headline A",
                url="https://example.com/a",
                published_at=now,
                source_name="Reuters",
            ),
            Article(
                title="Headline B",
                url="https://example.com/b",
                published_at=now,
                source_name="BBC",
            ),
        ]

        headlines = await source.get_headlines()

        assert len(headlines) == 2
        assert headlines[0]["text"] == "Headline A"
        assert headlines[0]["url"] == "https://example.com/a"
        assert headlines[0]["source"] == "Reuters"
        assert headlines[0]["ticker"] is None

    @pytest.mark.asyncio
    async def test_get_headlines_respects_limit(self):
        from data.sources.rss_news import Article, RSSNewsSource

        source = RSSNewsSource(feed_urls=["https://example.com/rss"])
        now = datetime.now(timezone.utc)
        source._latest_articles = [
            Article(
                title=f"Headline {i}",
                url=f"https://example.com/{i}",
                published_at=now,
                source_name="Test",
            )
            for i in range(20)
        ]

        headlines = await source.get_headlines(limit=5)
        assert len(headlines) == 5

    @pytest.mark.asyncio
    async def test_get_headlines_empty_before_first_tick(self):
        from data.sources.rss_news import RSSNewsSource

        source = RSSNewsSource(feed_urls=["https://example.com/rss"])
        headlines = await source.get_headlines()
        assert headlines == []


class TestFailTracking:
    @pytest.mark.asyncio
    async def test_consecutive_failures_tracked(self):
        from data.sources.rss_news import RSSNewsSource

        feed_url = "https://example.com/failing-feed"
        source = RSSNewsSource(feed_urls=[feed_url])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))

        # Simulate two single-feed fetch failures
        await source._fetch_single_feed(mock_client, feed_url)
        assert source._fail_counts[feed_url] == 1

        await source._fetch_single_feed(mock_client, feed_url)
        assert source._fail_counts[feed_url] == 2

    @pytest.mark.asyncio
    async def test_fail_count_resets_on_success(self):
        from data.sources.rss_news import RSSNewsSource

        feed_url = "https://example.com/recover-feed"
        source = RSSNewsSource(feed_urls=[feed_url])
        source._fail_counts[feed_url] = 3

        mock_response = _make_mock_response(SAMPLE_RSS_XML)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        await source._fetch_single_feed(mock_client, feed_url)
        assert source._fail_counts[feed_url] == 0
