"""Unit tests for TradingKnowledgeGraph."""

import pytest

from storage.knowledge_graph import TradingKnowledgeGraph


@pytest.fixture
async def kg(tmp_path):
    """Create a knowledge graph with a temp DB for testing."""
    graph = TradingKnowledgeGraph(db_path=str(tmp_path / "test_kg.sqlite3"))
    await graph.connect()
    yield graph
    await graph.close()


class TestTradingKnowledgeGraph:
    """Tests for TradingKnowledgeGraph."""

    async def test_add_and_query_entity(self, kg):
        """Add a triple and query the subject entity to verify predicate/object."""
        await kg.add_triple("Bitcoin", "has_trend", "bullish")
        results = await kg.query_entity("Bitcoin")
        assert len(results) == 1
        assert results[0]["predicate"] == "has_trend"
        assert results[0]["object"] == "bullish"

    async def test_temporal_filter_excludes_expired(self, kg):
        """Two triples with different validity windows; query at two dates."""
        await kg.add_triple(
            "Bitcoin", "has_trend", "bullish",
            valid_from="2026-01-01", valid_to="2026-03-31",
        )
        await kg.add_triple(
            "Bitcoin", "has_trend", "bearish",
            valid_from="2026-04-01", valid_to="2026-06-30",
        )

        q1 = await kg.query_entity("Bitcoin", as_of="2026-02-15")
        assert len(q1) == 1
        assert q1[0]["object"] == "bullish"

        q2 = await kg.query_entity("Bitcoin", as_of="2026-05-01")
        assert len(q2) == 1
        assert q2[0]["object"] == "bearish"

    async def test_invalidate_sets_valid_to_and_reason(self, kg):
        """Invalidate a triple and verify valid_to and reason in timeline."""
        await kg.add_triple("Bitcoin", "has_trend", "bullish")
        await kg.invalidate(
            "Bitcoin", "has_trend", "bullish",
            ended="2026-04-01", reason="trend reversed",
        )

        timeline = await kg.timeline(entity_name="Bitcoin")
        assert len(timeline) == 1
        assert timeline[0]["valid_to"] == "2026-04-01"
        assert timeline[0]["invalidation_reason"] == "trend reversed"

    async def test_timeline_ordered_by_valid_from(self, kg):
        """Multiple triples should be ordered chronologically by valid_from."""
        await kg.add_triple("ETH", "price_above", "3000", valid_from="2026-03-01")
        await kg.add_triple("ETH", "price_above", "2000", valid_from="2026-01-01")
        await kg.add_triple("ETH", "price_above", "4000", valid_from="2026-06-01")

        timeline = await kg.timeline(entity_name="ETH")
        froms = [t["valid_from"] for t in timeline]
        assert froms == ["2026-01-01", "2026-03-01", "2026-06-01"]

    async def test_query_relationship(self, kg):
        """Multiple triples with the same predicate are returned."""
        await kg.add_triple("BTC", "correlated_with", "ETH")
        await kg.add_triple("BTC", "correlated_with", "SOL")
        await kg.add_triple("ETH", "correlated_with", "SOL")

        results = await kg.query_relationship("correlated_with")
        assert len(results) == 3

    async def test_stats(self, kg):
        """Verify entity/triple/expired/current counts."""
        await kg.add_triple("BTC", "has_trend", "bullish")
        await kg.add_triple("ETH", "has_trend", "bearish")
        await kg.invalidate("ETH", "has_trend", "bearish", ended="2026-04-01")

        s = await kg.stats()
        assert s["entities"] == 4  # BTC, bullish, ETH, bearish
        assert s["triples"] == 2
        assert s["current_facts"] == 1
        assert s["expired_facts"] == 1
        assert "has_trend" in s["relationship_types"]

    async def test_add_triple_with_properties(self, kg):
        """Add a triple with JSON properties and verify them on query."""
        props = {"timeframe": "4h", "indicator": "RSI"}
        await kg.add_triple(
            "BTC", "signal", "oversold",
            properties=props,
        )
        results = await kg.query_entity("BTC")
        assert len(results) == 1
        assert results[0]["properties"]["timeframe"] == "4h"
        assert results[0]["properties"]["indicator"] == "RSI"

    async def test_duplicate_triple_not_inserted(self, kg):
        """Same triple inserted twice should return same ID and count stays 1."""
        id1 = await kg.add_triple("BTC", "has_trend", "bullish")
        id2 = await kg.add_triple("BTC", "has_trend", "bullish")
        assert id1 == id2

        s = await kg.stats()
        assert s["triples"] == 1

    async def test_bidirectional_query(self, kg):
        """Query with direction='incoming' and 'both'."""
        await kg.add_triple("BTC", "influences", "ETH")
        await kg.add_triple("SOL", "influences", "ETH")

        incoming = await kg.query_entity("ETH", direction="incoming")
        assert len(incoming) == 2
        subjects = {r["subject"] for r in incoming}
        assert subjects == {"btc", "sol"}

        both = await kg.query_entity("ETH", direction="both")
        assert len(both) == 2  # ETH is only an object here

        # Add ETH as subject too
        await kg.add_triple("ETH", "influences", "AVAX")
        both2 = await kg.query_entity("ETH", direction="both")
        assert len(both2) == 3  # 2 incoming + 1 outgoing

    async def test_entity_id_normalization(self, kg):
        """Verify _entity_id handles spaces, apostrophes, case."""
        assert TradingKnowledgeGraph._entity_id("Bitcoin Cash") == "bitcoin_cash"
        assert TradingKnowledgeGraph._entity_id("O'Reilly") == "oreilly"
        assert TradingKnowledgeGraph._entity_id("UPPER CASE") == "upper_case"
        assert TradingKnowledgeGraph._entity_id("  extra  spaces  ") == "extra__spaces"
