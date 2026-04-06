from __future__ import annotations
from datetime import datetime, timezone, timedelta
import pytest
from broker.models import PredictionContract
from strategies.matching import extract_keywords, normalize_category, match_markets


def _contract(
    ticker: str, title: str, category: str = "politics", days: int = 30
) -> PredictionContract:
    close = datetime.now(timezone.utc) + timedelta(days=days)
    return PredictionContract(
        ticker=ticker, title=title, category=category, close_time=close
    )


class TestExtractKeywords:
    def test_removes_stop_words(self):
        kw = extract_keywords("Will the Fed raise rates in May")
        assert "the" not in kw
        assert "will" not in kw
        assert "in" not in kw

    def test_strips_trailing_s(self):
        kw = extract_keywords("Fed raises rates")
        assert "rates" not in kw or "rate" in kw  # stemmed

    def test_strips_trailing_ed(self):
        kw = extract_keywords("Fed raised rates")
        assert "raised" not in kw or "rais" in kw

    def test_returns_set(self):
        assert isinstance(extract_keywords("hello world"), set)

    def test_empty_string(self):
        assert extract_keywords("") == set()


class TestNormalizeCategory:
    def test_politics(self):
        assert normalize_category("politics") == "politics"

    def test_economics(self):
        assert normalize_category("Economics") == "economics"

    def test_polymarket_tag_crypto(self):
        assert normalize_category("Crypto") == "crypto"

    def test_unknown_maps_to_other(self):
        assert normalize_category("obscure-tag-xyz") == "other"

    def test_climate(self):
        assert normalize_category("climate") == "climate"


class TestMatchMarkets:
    def test_identical_title_scores_high(self):
        k = [_contract("K1", "Will the Fed raise interest rates in May 2026?")]
        p = [_contract("P1", "Will the Fed raise interest rates in May 2026?")]
        results = match_markets(k, p, min_score=0.0)
        assert len(results) == 1
        assert results[0].final_score > 0.9

    def test_min_score_filters(self):
        k = [_contract("K1", "football match results")]
        p = [_contract("P1", "completely unrelated topic about weather")]
        results = match_markets(k, p, min_score=0.5)
        assert results == []

    def test_category_bonus_applied(self):
        k = [_contract("K1", "Fed rate decision May", category="economics")]
        p = [_contract("P1", "Fed rate decision May", category="economics")]
        results_with = match_markets(k, p, min_score=0.0)
        assert results_with[0].category_bonus == pytest.approx(0.10)

    def test_category_mismatch_no_bonus(self):
        k = [_contract("K1", "Fed rate decision May", category="economics")]
        p = [_contract("P1", "Fed rate decision May", category="sports")]
        results = match_markets(k, p, min_score=0.0)
        assert results[0].category_bonus == 0.0

    def test_large_date_penalty(self):
        k = [_contract("K1", "inflation above target", days=10)]
        p = [_contract("P1", "inflation above target", days=200)]
        results = match_markets(k, p, min_score=0.0)
        assert results[0].date_penalty == pytest.approx(0.30)

    def test_small_date_no_penalty(self):
        k = [_contract("K1", "inflation above target", days=30)]
        p = [_contract("P1", "inflation above target", days=34)]
        results = match_markets(k, p, min_score=0.0)
        assert results[0].date_penalty == 0.0

    def test_deduplication_keeps_best(self):
        k = [
            _contract("K1", "Fed rate hike May"),
            _contract("K2", "Fed rate decision May"),
        ]
        p = [_contract("P1", "Fed rate hike May")]
        results = match_markets(k, p, min_score=0.0)
        poly_tickers = [r.poly_ticker for r in results]
        assert poly_tickers.count("P1") == 1

    def test_kalshi_deduplication_keeps_best(self):
        """One Kalshi ticker should match at most one Polymarket ticker."""
        k = [_contract("K1", "Will the Fed raise rates in May 2026")]
        p = [
            _contract("P1", "Will the Fed raise rates in May 2026"),
            _contract("P2", "Will the Fed raise interest rates May 2026"),
        ]
        results = match_markets(k, p, min_score=0.0)
        kalshi_tickers = [r.kalshi_ticker for r in results]
        assert kalshi_tickers.count("K1") == 1, "K1 matched more than one Poly ticker"

    def test_sorted_descending(self):
        k = [
            _contract("K1", "Bitcoin price above 100k"),
            _contract("K2", "completely unrelated"),
        ]
        p = [
            _contract("P1", "Bitcoin price above 100k"),
            _contract("P2", "somewhat similar stuff"),
        ]
        results = match_markets(k, p, min_score=0.0)
        scores = [r.final_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_date_penalty_fractional_days(self):
        """A 29.9-hour difference should not be treated as 1 day (within 7-day tolerance)."""
        from datetime import timedelta

        k = [_contract("K1", "Fed rate decision", days=0)]
        close_offset = timedelta(hours=29, minutes=54)
        p_close = datetime.now(timezone.utc) + close_offset
        p = [
            PredictionContract(
                ticker="P1",
                title="Fed rate decision",
                category="politics",
                close_time=p_close,
            )
        ]
        results = match_markets(k, p, min_score=0.0)
        assert results[0].date_penalty == 0.0
