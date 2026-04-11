import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add trading dir to path
sys.path.append(str(Path(__file__).parent.parent))

from storage.memory import LocalMemoryStore
from storage.knowledge_graph import TradingKnowledgeGraph
from learning.prompt_store import SqlPromptStore
from config import Config
from agents.models import AgentConfig, ActionLevel

async def verify_wal_mode():
    print("--- Verifying WAL Mode ---")
    store = LocalMemoryStore(db_path="data/test_verify.db")
    await store.connect()
    async with store._db.execute("PRAGMA journal_mode") as cur:
        row = await cur.fetchone()
        journal_mode = row[0]
        print(f"Journal mode: {journal_mode}")
        assert journal_mode.lower() == "wal"
    await store.close()
    if os.path.exists("data/test_verify.db"):
        os.remove("data/test_verify.db")
    print("✅ WAL Mode verified")

async def verify_content_hash_dedup():
    print("\n--- Verifying Content-Hash Deduplication ---")
    store = LocalMemoryStore(db_path="data/test_dedup.db")
    await store.connect()
    
    # Store first time
    m1 = await store.store(
        key="test_key",
        value="identical content",
        agent_id="test_agent",
        category="test"
    )
    print(f"First write ID: {m1['id']}")
    
    # Store second time (identical content)
    m2 = await store.store(
        key="test_key",
        value="identical content",
        agent_id="test_agent",
        category="test"
    )
    print(f"Second write ID: {m2['id']}")
    assert m1['id'] == m2['id']
    assert m2.get('deduplicated') is True
    
    await store.close()
    if os.path.exists("data/test_dedup.db"):
        os.remove("data/test_dedup.db")
    print("✅ Content-hash deduplication verified")

async def verify_kg_schema_and_sweep():
    print("\n--- Verifying KG Schema and Sweep ---")
    kg = TradingKnowledgeGraph(db_path="data/test_kg.db")
    await kg.connect()
    
    # Add entity and triple
    await kg.add_entity("BTC", entity_type="asset")
    await kg.add_triple(
        "BTC", "has_price", "60000",
        valid_to=(datetime.now(timezone.utc)).isoformat() # expires now
    )
    
    stats = await kg.stats()
    print(f"Stats before sweep: {stats}")
    assert stats['triples'] == 1
    
    # Wait a tiny bit to ensure valid_to < now
    await asyncio.sleep(0.1)
    
    swept = await kg.sweep_expired()
    print(f"Swept {swept} triples")
    assert swept == 1
    
    stats_after = await kg.stats()
    print(f"Stats after sweep: {stats_after}")
    assert stats_after['triples'] == 0
    
    await kg.close()
    if os.path.exists("data/test_kg.db"):
        os.remove("data/test_kg.db")
    print("✅ KG schema and sweep verified")

async def verify_l0_l1_context():
    print("\n--- Verifying L0/L1 Context Generation ---")
    import aiosqlite
    db = await aiosqlite.connect(":memory:")
    await db.execute("CREATE TABLE agent_context_cache (agent_name TEXT PRIMARY KEY, l0_text TEXT, l1_text TEXT, generated_at TEXT, trade_count INTEGER)")
    
    store = SqlPromptStore(db)
    config = AgentConfig(
        name="TrendFollower",
        strategy="momentum",
        schedule="continuous",
        action_level=ActionLevel.AUTO_EXECUTE,
        universe=["BTC", "ETH"]
    )
    
    # Mock some trade memories
    memories = [
        {"value": "Great win on BTC long", "importance": 0.9},
        {"value": "Bad loss on ETH short", "importance": 0.8}
    ]
    
    await store.generate_agent_context(
        agent_name="TrendFollower",
        agent_config=config,
        trade_memories=memories
    )
    
    context = store.get_agent_context("TrendFollower")
    print(f"Generated context preview:\n{context[:200]}...")
    
    assert "## Identity" in context
    assert "Agent: TrendFollower" in context
    assert "## Recent Performance" in context
    assert "Great win on BTC long" in context
    
    await db.close()
    print("✅ L0/L1 context generation verified")

async def verify_entity_extraction():
    print("\n--- Verifying Entity Extraction ---")
    from knowledge.extractor import EntityExtractor
    extractor = EntityExtractor()
    
    text = "BTC surges as Microsoft announces partnership with Ethereum"
    entities = extractor.extract_entities(text)
    print(f"Extracted entities: {entities}")
    
    entity_ids = [e['id'] for e in entities]
    assert "BTC" in entity_ids
    assert "microsoft" in entity_ids
    assert "ethereum" in entity_ids
    
    triples = extractor.extract_triples(text)
    print(f"Extracted triples: {triples}")
    
    preds = [t['predicate'] for t in triples]
    assert "partnership" in preds
    
    # Single ticker sentiment
    sentiment_text = "BTC is looking very bullish today"
    s_triples = extractor.extract_triples(sentiment_text)
    print(f"Sentiment triples: {s_triples}")
    assert s_triples[0]['predicate'] == "has_sentiment"
    assert s_triples[0]['object'] == "bullish"
    
    print("✅ Entity extraction verified")

async def main():
    try:
        await verify_wal_mode()
        await verify_content_hash_dedup()
        await verify_kg_schema_and_sweep()
        await verify_l0_l1_context()
        await verify_entity_extraction()
        print("\n✨ ALL VERIFICATIONS PASSED ✨")
    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
