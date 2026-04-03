"""Unit tests for shared news models."""
from datetime import datetime, timezone


class TestNewsSignalImport:
    def test_import_from_models(self):
        from data.sources.models import NewsSignal
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

    def test_backward_compat_import_from_newsapi(self):
        from data.sources.newsapi import NewsSignal
        sig = NewsSignal(
            contract_ticker="X",
            headline="test",
            url="https://example.com",
            published_at=datetime.now(timezone.utc),
            relevance=0.5,
            sentiment="neutral",
            mispricing_score=0.0,
            scored_at=datetime.now(timezone.utc),
        )
        assert sig.sentiment == "neutral"
