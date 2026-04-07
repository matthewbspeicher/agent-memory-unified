"""Tests for CryptoBERT sentiment extraction."""

import pytest
from datetime import datetime

from learning.sentiment import (
    CryptoBERTClient,
    SentimentAggregator,
    SentimentResult,
)


class TestCryptoBERTClient:
    def test_client_init(self):
        client = CryptoBERTClient()
        assert client.model_name == "CryptoRAG/crypto-bert-sentiment"
        assert client.use_fallback is True

    def test_fallback_analyze_bullish(self):
        client = CryptoBERTClient(use_fallback=True)
        result = client.analyze("Bitcoin is bullish, heading to the moon!")

        assert result.sentiment > 0
        assert 0 <= result.confidence <= 1.0
        assert "BTC" in result.entities or "Bitcoin" in result.entities

    def test_fallback_analyze_bearish(self):
        client = CryptoBERTClient(use_fallback=True)
        result = client.analyze("Crypto market crashing, sell everything!")

        assert result.sentiment < 0
        assert 0 <= result.confidence <= 1.0

    def test_fallback_analyze_neutral(self):
        client = CryptoBERTClient(use_fallback=True)
        result = client.analyze("Bitcoin price is around $50,000 today.")

        # Should be near zero for neutral text
        assert -0.3 <= result.sentiment <= 0.3

    def test_entity_extraction(self):
        client = CryptoBERTClient(use_fallback=True)
        result = client.analyze("ETH and SOL are pumping while BTC lags.")

        assert "ETH" in result.entities
        assert "SOL" in result.entities
        assert "BTC" in result.entities

    def test_fallback_requires_flag(self):
        client = CryptoBERTClient(use_fallback=False)
        # Without fallback, should return zero sentiment if model fails
        result = client.analyze("Bitcoin to the moon!")
        assert result.sentiment == 0.0
        assert result.confidence == 0.0


class TestSentimentAggregator:
    def test_aggregator_init(self):
        agg = SentimentAggregator(decay=0.9)
        assert agg._sentiment_ema is None
        assert agg.decay == 0.9

    def test_update_first_value(self):
        agg = SentimentAggregator()
        result = SentimentResult(
            text="Test",
            sentiment=0.5,
            confidence=0.8,
            entities=["BTC"],
            timestamp=datetime.now(),
        )

        signal = agg.update(result)
        assert signal["sentiment"] == pytest.approx(0.4, rel=0.01)  # 0.5 * 0.8
        assert signal["confidence"] == 0.8

    def test_update_ema_smoothing(self):
        agg = SentimentAggregator(decay=0.9)

        # First update
        result1 = SentimentResult(
            text="Test 1",
            sentiment=1.0,
            confidence=1.0,
            entities=[],
            timestamp=datetime.now(),
        )
        agg.update(result1)

        # Second update
        result2 = SentimentResult(
            text="Test 2",
            sentiment=-1.0,
            confidence=1.0,
            entities=[],
            timestamp=datetime.now(),
        )
        signal = agg.update(result2)

        # Should be smoothed: 0.9 * 1.0 + 0.1 * (-1.0) = 0.8
        assert signal["sentiment"] == pytest.approx(0.8, rel=0.01)

    def test_get_signal(self):
        agg = SentimentAggregator()
        result = SentimentResult(
            text="Test",
            sentiment=0.5,
            confidence=0.9,
            entities=[],
            timestamp=datetime.now(),
        )
        agg.update(result)

        signal = agg.get_signal()
        assert signal["sentiment"] == pytest.approx(0.45, rel=0.01)
        assert signal["confidence"] == 0.9
        assert signal["last_update"] is not None

    def test_get_signal_before_update(self):
        agg = SentimentAggregator()
        signal = agg.get_signal()

        assert signal["sentiment"] == 0.0
        assert signal["confidence"] == 0.0
        assert signal["last_update"] is None
