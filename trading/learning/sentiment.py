"""CryptoBERT sentiment extraction from news and social media.

Uses a pre-trained or fine-tuned crypto sentiment model to extract
sentiment signals from text sources. Feeds into ensemble as a feature
(not for direct trading decisions per research: LLMs lost 60%+ in live trading).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""

    text: str  # Source text
    sentiment: float  # -1 (bearish) to 1 (bullish)
    confidence: float  # 0-1 confidence
    entities: list[str]  # Extracted entities (BTC, ETH, etc.)
    timestamp: datetime


class CryptoBERTClient:
    """Client for CryptoBERT sentiment extraction.

    Uses a pre-trained crypto sentiment model to analyze text.
    Falls back to keyword-based scoring if model unavailable.
    """

    def __init__(
        self,
        model_name: str = "CryptoRAG/crypto-bert-sentiment",
        use_fallback: bool = True,
    ):
        self.model_name = model_name
        self.use_fallback = use_fallback
        self._model: Any | None = None
        self._tokenizer: Any | None = None

    def _load_model(self) -> bool:
        """Lazy load the model."""
        if self._model is not None:
            return True

        try:
            from importlib import import_module

            transformers = import_module("transformers")
            AutoModelForSequenceClassification = (
                transformers.AutoModelForSequenceClassification
            )
            AutoTokenizer = transformers.AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name
            )
            logger.info("CryptoBERT model loaded: %s", self.model_name)
            return True
        except Exception as e:
            logger.warning("Failed to load CryptoBERT model: %s", e)
            return False

    def analyze(self, text: str) -> SentimentResult:
        """Analyze sentiment of text.

        Args:
            text: Text to analyze (news headline, tweet, etc.)

        Returns:
            SentimentResult with sentiment score and entities
        """
        if (
            self._load_model()
            and self._model is not None
            and self._tokenizer is not None
        ):
            return self._analyze_with_model(text)
        elif self.use_fallback:
            return self._analyze_fallback(text)
        else:
            return SentimentResult(
                text=text,
                sentiment=0.0,
                confidence=0.0,
                entities=[],
                timestamp=datetime.now(),
            )

    def _analyze_with_model(self, text: str) -> SentimentResult:
        """Analyze using CryptoBERT model."""
        from importlib import import_module

        torch = import_module("torch")

        tokenizer = self._tokenizer
        model = self._model
        assert tokenizer is not None
        assert model is not None

        # Tokenize
        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )

        # Predict
        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1)
            pred = torch.argmax(probs, dim=1).item()

            # Model outputs: 0=bearish, 1=neutral, 2=bullish
            sentiment_map = {0: -1.0, 1: 0.0, 2: 1.0}
            sentiment = sentiment_map.get(pred, 0.0)
            confidence = probs[0, pred].item()

        # Extract entities (simple keyword matching)
        entities = self._extract_entities(text)

        return SentimentResult(
            text=text,
            sentiment=sentiment,
            confidence=confidence,
            entities=entities,
            timestamp=datetime.now(),
        )

    def _analyze_fallback(self, text: str) -> SentimentResult:
        """Fallback keyword-based sentiment analysis."""

        # Keywords
        bullish_words = {
            "bullish": 0.3,
            "moon": 0.4,
            "pump": 0.3,
            "buy": 0.2,
            "long": 0.2,
            "up": 0.1,
            "rise": 0.2,
            "gain": 0.2,
            "growth": 0.2,
            "surge": 0.3,
            "rally": 0.3,
            "high": 0.1,
            "all-time": 0.3,
            " ATH ": 0.3,
            "adoption": 0.2,
            "upgrade": 0.2,
        }
        bearish_words = {
            "bearish": -0.3,
            "dump": -0.4,
            "crash": -0.5,
            "sell": -0.2,
            "short": -0.2,
            "down": -0.1,
            "fall": -0.2,
            "loss": -0.3,
            "hack": -0.4,
            "scam": -0.4,
            "ban": -0.3,
            "regulation": -0.2,
            "fud": -0.2,
            "fear": -0.2,
            "drop": -0.2,
            "low": -0.1,
        }

        text_lower = text.lower()
        sentiment = 0.0
        count = 0

        for word, score in bullish_words.items():
            if word in text_lower:
                sentiment += score
                count += 1

        for word, score in bearish_words.items():
            if word in text_lower:
                sentiment += score
                count += 1

        # Normalize by count
        if count > 0:
            sentiment = sentiment / count

        # Extract entities
        entities = self._extract_entities(text)

        # Confidence based on keyword matches
        confidence = min(0.5 + count * 0.1, 0.95) if count > 0 else 0.3

        return SentimentResult(
            text=text,
            sentiment=sentiment,
            confidence=confidence,
            entities=entities,
            timestamp=datetime.now(),
        )

    def _extract_entities(self, text: str) -> list[str]:
        """Extract crypto entities from text."""
        entities = []
        crypto_keywords = {
            "BTC",
            "ETH",
            "Bitcoin",
            "Ethereum",
            "Solana",
            "SOL",
            "BNB",
            "XRP",
            "ADA",
            "DOGE",
            "DOT",
            "AVAX",
            "MATIC",
            "LINK",
            "UNI",
            "ATOM",
            "LTC",
            "BCH",
            "XLM",
            "ALGO",
        }

        text_upper = text.upper()
        for entity in crypto_keywords:
            if entity.upper() in text_upper:
                entities.append(entity)

        return entities


class SentimentAggregator:
    """Aggregate sentiment from multiple sources over time.

    Provides smoothed sentiment signals for the ensemble.
    """

    def __init__(self, decay: float = 0.9):
        self.decay = decay  # EMA decay factor
        self._sentiment_ema: float | None = None
        self._confidence_ema: float | None = None
        self._last_update: datetime | None = None

    def update(self, result: SentimentResult) -> dict[str, Any]:
        """Update with new sentiment result, return smoothed signal."""
        if self._sentiment_ema is None:
            self._sentiment_ema = result.sentiment * result.confidence
            self._confidence_ema = result.confidence
        else:
            # Confidence-weighted update
            confidence_ema = self._confidence_ema
            assert confidence_ema is not None
            weight = result.confidence
            self._sentiment_ema = (
                self.decay * self._sentiment_ema
                + (1 - self.decay) * result.sentiment * weight
            )
            self._confidence_ema = (
                self.decay * confidence_ema + (1 - self.decay) * weight
            )

        self._last_update = result.timestamp

        return {
            "sentiment": self._sentiment_ema,
            "confidence": self._confidence_ema,
            "last_update": self._last_update,
            "entity_count": len(result.entities),
        }

    def get_signal(self) -> dict[str, Any]:
        """Get current smoothed sentiment signal."""
        return {
            "sentiment": self._sentiment_ema or 0.0,
            "confidence": self._confidence_ema or 0.0,
            "last_update": self._last_update,
        }
