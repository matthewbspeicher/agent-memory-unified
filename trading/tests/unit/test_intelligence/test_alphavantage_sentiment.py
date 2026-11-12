import pytest
from unittest.mock import patch, AsyncMock
from intelligence.providers.sentiment import SentimentProvider


@pytest.mark.asyncio
async def test_alpha_vantage_sentiment():
    provider = SentimentProvider(alpha_vantage_key="TEST_KEY")

    with (
        patch.object(
            provider, "_fetch_fear_greed", new_callable=AsyncMock, return_value=50
        ) as mock_fg,
        patch.object(
            provider, "_fetch_av_sentiment", new_callable=AsyncMock
        ) as mock_fetch,
    ):
        mock_fetch.return_value = 0.8  # Bullish

        # Test analysis incorporating AV score
        report = await provider.analyze("AAPL")
        assert report is not None
        # Details should have AV score
        assert "av_sentiment_score" in report.details
        assert report.details["av_sentiment_score"] == 0.8
        assert report.score == pytest.approx(0.4)
        mock_fg.assert_awaited_once()
        mock_fetch.assert_awaited_once_with("AAPL")
