import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from learning.agent_memory import AgentMemory, MemoryContext


class TestMemoryContext:
    def test_full_returns_empty_string_when_all_fields_empty(self):
        ctx = MemoryContext()
        assert ctx.full == ""

    def test_full_returns_single_section(self):
        ctx = MemoryContext(identity="I am RSI agent")
        assert ctx.full == "I am RSI agent"

    def test_full_joins_multiple_sections_with_double_newline(self):
        ctx = MemoryContext(
            identity="I am RSI agent",
            rules="Buy low, sell high",
            lessons="## Recent Lessons\n- Avoid FOMO",
        )
        parts = ctx.full.split("\n\n")
        assert len(parts) == 3
        assert "I am RSI agent" in parts[0]
        assert "Buy low, sell high" in parts[1]
        assert "Avoid FOMO" in parts[2]

    def test_full_skips_empty_sections(self):
        ctx = MemoryContext(
            identity="id",
            rules="",
            lessons="lsn",
            trade_memories="",
            shared_observations="",
        )
        parts = ctx.full.split("\n\n")
        assert len(parts) == 2
        assert parts[0] == "id"
        assert parts[1] == "lsn"

    def test_is_empty_true_when_all_defaults(self):
        ctx = MemoryContext()
        assert ctx.is_empty is True

    def test_is_empty_false_when_any_field_set(self):
        for field in [
            "identity",
            "rules",
            "lessons",
            "trade_memories",
            "shared_observations",
        ]:
            kwargs = {field: "x"}
            ctx = MemoryContext(**kwargs)
            assert ctx.is_empty is False, f"Setting {field} should make is_empty False"

    def test_is_empty_false_when_all_fields_set(self):
        ctx = MemoryContext(
            identity="id",
            rules="r",
            lessons="l",
            trade_memories="tm",
            shared_observations="so",
        )
        assert ctx.is_empty is False

    def test_full_preserves_section_order(self):
        ctx = MemoryContext(
            shared_observations="so",
            lessons="l",
            identity="id",
            rules="r",
            trade_memories="tm",
        )
        assert ctx.full.index("id") < ctx.full.index("r")
        assert ctx.full.index("r") < ctx.full.index("l")
        assert ctx.full.index("l") < ctx.full.index("tm")
        assert ctx.full.index("tm") < ctx.full.index("so")


class TestAgentMemoryRemember:
    @pytest.fixture
    def mock_reflector(self):
        r = MagicMock()
        r.query = AsyncMock(
            return_value=[
                {"value": "BTC breakout above 70k"},
                {"content": "ETH support at 3500"},
            ]
        )
        r.reflect = AsyncMock()
        return r

    @pytest.fixture
    def mock_client(self):
        c = MagicMock()
        c.search_both = AsyncMock(
            return_value=[
                {"value": "Market volatility increasing"},
            ]
        )
        c.store_shared = AsyncMock(return_value={"id": "s1"})
        c.store_private = AsyncMock(return_value={"id": "p1"})
        return c

    @pytest.fixture
    def mock_pstore(self):
        p = MagicMock()
        p.get_agent_context = MagicMock(return_value="I am a momentum agent")
        p.get_runtime_prompt = MagicMock(
            return_value="## Rules\n- Rule 1\n## Recent Lessons\n- Lesson 1"
        )
        p.generate_agent_context = AsyncMock()
        p.load = AsyncMock()
        return p

    @pytest.fixture
    def agent_config(self):
        cfg = MagicMock()
        cfg.name = "test_agent"
        return cfg

    async def test_remember_with_all_backends(
        self, mock_reflector, mock_client, mock_pstore, agent_config
    ):
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember(
            "test_agent", "BTC momentum", agent_config=agent_config
        )

        assert not ctx.is_empty
        assert ctx.identity == "I am a momentum agent"
        assert "Rule 1" in ctx.rules
        assert ctx.trade_memories.startswith("## Trade Memories")
        assert "BTC breakout" in ctx.trade_memories
        assert ctx.shared_observations.startswith("## Shared Market Observations")
        assert "volatility" in ctx.shared_observations
        assert "Recent Lessons" in ctx.lessons

    async def test_remember_no_backends(self):
        mem = AgentMemory()
        ctx = await mem.remember("test_agent", "query")
        assert ctx.is_empty is True
        assert ctx.full == ""

    async def test_remember_reflector_only(self, mock_reflector):
        mem = AgentMemory(trade_reflector=mock_reflector)
        ctx = await mem.remember("test_agent", "BTC signal")
        assert ctx.trade_memories != ""
        assert ctx.identity == ""
        assert ctx.rules == ""
        assert ctx.lessons == ""
        assert ctx.shared_observations == ""

    async def test_remember_client_only(self, mock_client, mock_pstore):
        mem = AgentMemory(memory_client=mock_client, prompt_store=mock_pstore)
        ctx = await mem.remember("test_agent", "ETH")
        assert ctx.shared_observations != ""
        assert ctx.trade_memories == ""

    async def test_remember_include_identity_false(
        self, mock_reflector, mock_client, mock_pstore, agent_config
    ):
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember(
            "test_agent", "query", agent_config=agent_config, include_identity=False
        )
        assert ctx.identity == ""
        mock_pstore.get_agent_context.assert_not_called()

    async def test_remember_include_rules_false(
        self, mock_reflector, mock_client, mock_pstore, agent_config
    ):
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember(
            "test_agent", "query", agent_config=agent_config, include_rules=False
        )
        assert ctx.rules == ""
        assert "Rules" not in ctx.rules

    async def test_remember_without_agent_config_skips_identity(
        self, mock_reflector, mock_client, mock_pstore
    ):
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember("test_agent", "query", agent_config=None)
        assert ctx.identity == ""

    async def test_remember_graceful_degradation_reflector_fails(
        self, mock_reflector, mock_client, mock_pstore, agent_config
    ):
        mock_reflector.query = AsyncMock(side_effect=RuntimeError("reflector down"))
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember("test_agent", "query", agent_config=agent_config)
        assert ctx.trade_memories == ""
        assert ctx.identity != ""
        assert ctx.rules != ""
        assert ctx.shared_observations != ""

    async def test_remember_graceful_degradation_client_fails(
        self, mock_reflector, mock_client, mock_pstore, agent_config
    ):
        mock_client.search_both = AsyncMock(side_effect=RuntimeError("client down"))
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember("test_agent", "query", agent_config=agent_config)
        assert ctx.shared_observations == ""
        assert ctx.trade_memories != ""

    async def test_remember_graceful_degradation_pstore_fails(
        self, mock_reflector, mock_client, agent_config
    ):
        failing_pstore = MagicMock()
        failing_pstore.get_agent_context = MagicMock(
            side_effect=RuntimeError("pstore down")
        )
        failing_pstore.get_runtime_prompt = MagicMock(
            side_effect=RuntimeError("pstore down")
        )
        failing_pstore.generate_agent_context = AsyncMock(
            side_effect=RuntimeError("pstore down")
        )

        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=failing_pstore,
        )
        ctx = await mem.remember("test_agent", "query", agent_config=agent_config)
        assert ctx.identity == ""
        assert ctx.rules == ""
        assert ctx.trade_memories != ""

    async def test_remember_top_k_limits_results(
        self, mock_reflector, mock_client, mock_pstore, agent_config
    ):
        many = [{"value": f"memory {i}"} for i in range(20)]
        mock_reflector.query = AsyncMock(return_value=many)
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember(
            "test_agent", "query", agent_config=agent_config, top_k=3
        )
        lines = [l for l in ctx.trade_memories.split("\n") if l.startswith("- ")]
        assert len(lines) == 3

    async def test_remember_empty_reflector_results(
        self, mock_reflector, mock_client, mock_pstore, agent_config
    ):
        mock_reflector.query = AsyncMock(return_value=[])
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember("test_agent", "query", agent_config=agent_config)
        assert ctx.trade_memories == ""

    async def test_remember_empty_client_results(
        self, mock_reflector, mock_client, mock_pstore, agent_config
    ):
        mock_client.search_both = AsyncMock(return_value=[])
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember("test_agent", "query", agent_config=agent_config)
        assert ctx.shared_observations == ""

    async def test_identity_generation_when_no_existing_context(
        self, mock_reflector, mock_client, agent_config
    ):
        pstore = MagicMock()
        pstore.get_agent_context = MagicMock(return_value=None)
        pstore.get_runtime_prompt = MagicMock(return_value="## Rules\n- R1")
        pstore.generate_agent_context = AsyncMock()
        pstore.load = AsyncMock()

        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=pstore,
        )
        ctx = await mem.remember("test_agent", "query", agent_config=agent_config)
        pstore.generate_agent_context.assert_awaited_once_with(
            agent_name="test_agent", agent_config=agent_config
        )

    async def test_identity_skips_generation_when_context_exists(
        self, mock_reflector, mock_client, agent_config
    ):
        pstore = MagicMock()
        pstore.get_agent_context = MagicMock(return_value="Existing context")
        pstore.get_runtime_prompt = MagicMock(return_value="## Rules")
        pstore.generate_agent_context = AsyncMock()
        pstore.load = AsyncMock()

        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=mock_client,
            prompt_store=pstore,
        )
        ctx = await mem.remember("test_agent", "query", agent_config=agent_config)
        pstore.generate_agent_context.assert_not_awaited()
        assert ctx.identity == "Existing context"

    async def test_lessons_extracts_recent_lessons_section(
        self, mock_reflector, mock_client, agent_config
    ):
        pstore = MagicMock()
        pstore.get_agent_context = MagicMock(return_value="id")
        pstore.get_runtime_prompt = MagicMock(
            return_value="## Rules\n- R1\n## Recent Lessons\n- L1\n- L2\n## Other\n- X"
        )
        pstore.generate_agent_context = AsyncMock()
        pstore.load = AsyncMock()

        mem = AgentMemory(memory_client=mock_client, prompt_store=pstore)
        ctx = await mem.remember("test_agent", "query", agent_config=agent_config)
        assert "Recent Lessons" in ctx.lessons
        assert "L1" in ctx.lessons
        assert "Rules" not in ctx.lessons

    async def test_lessons_empty_when_no_recent_lessons(
        self, mock_reflector, mock_client, agent_config
    ):
        pstore = MagicMock()
        pstore.get_agent_context = MagicMock(return_value="id")
        pstore.get_runtime_prompt = MagicMock(return_value="## Rules\n- R1")
        pstore.generate_agent_context = AsyncMock()
        pstore.load = AsyncMock()

        mem = AgentMemory(memory_client=mock_client, prompt_store=pstore)
        ctx = await mem.remember("test_agent", "query", agent_config=agent_config)
        assert ctx.lessons == ""

    async def test_trade_memories_uses_content_key_fallback(
        self, mock_client, mock_pstore, agent_config
    ):
        reflector = MagicMock()
        reflector.query = AsyncMock(
            return_value=[
                {"content": "memory via content key"},
            ]
        )
        mem = AgentMemory(
            trade_reflector=reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember("test_agent", "q", agent_config=agent_config)
        assert "memory via content key" in ctx.trade_memories

    async def test_trade_memories_plain_string_degrades_gracefully(
        self, mock_client, mock_pstore, agent_config
    ):
        reflector = MagicMock()
        reflector.query = AsyncMock(return_value=["plain string memory"])
        mem = AgentMemory(
            trade_reflector=reflector,
            memory_client=mock_client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember("test_agent", "q", agent_config=agent_config)
        assert ctx.trade_memories == ""

    async def test_shared_observations_uses_value_key(
        self, mock_reflector, mock_pstore, agent_config
    ):
        client = MagicMock()
        client.search_both = AsyncMock(
            return_value=[
                {"value": "obs via value key"},
            ]
        )
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember("test_agent", "q", agent_config=agent_config)
        assert "obs via value key" in ctx.shared_observations

    async def test_shared_observations_truncates_long_content(
        self, mock_reflector, mock_pstore, agent_config
    ):
        client = MagicMock()
        long_content = "x" * 300
        client.search_both = AsyncMock(return_value=[{"value": long_content}])
        mem = AgentMemory(
            trade_reflector=mock_reflector,
            memory_client=client,
            prompt_store=mock_pstore,
        )
        ctx = await mem.remember("test_agent", "q", agent_config=agent_config)
        for line in ctx.shared_observations.split("\n"):
            if line.startswith("- "):
                assert len(line) <= 202


class TestAgentMemoryStoreObservation:
    @pytest.fixture
    def mock_client(self):
        c = MagicMock()
        c.store_shared = AsyncMock(return_value={"id": "shared_1"})
        c.store_private = AsyncMock(return_value={"id": "private_1"})
        return c

    async def test_store_private_by_default(self, mock_client):
        mem = AgentMemory(memory_client=mock_client)
        result = await mem.store_observation("BTC rising", tags=["btc"])
        mock_client.store_private.assert_awaited_once_with(
            content="BTC rising", tags=["btc"]
        )
        assert result == {"id": "private_1"}

    async def test_store_shared_when_flag_set(self, mock_client):
        mem = AgentMemory(memory_client=mock_client)
        result = await mem.store_observation("ETH dropping", tags=["eth"], shared=True)
        mock_client.store_shared.assert_awaited_once_with(
            content="ETH dropping", tags=["eth"]
        )
        assert result == {"id": "shared_1"}

    async def test_store_observation_no_client_returns_empty(self):
        mem = AgentMemory()
        result = await mem.store_observation("orphan observation")
        assert result == {}

    async def test_store_observation_tags_default_none(self, mock_client):
        mem = AgentMemory(memory_client=mock_client)
        await mem.store_observation("content")
        mock_client.store_private.assert_awaited_once_with(content="content", tags=None)


class TestAgentMemoryReflectTrade:
    @pytest.fixture
    def mock_reflector(self):
        r = MagicMock()
        r.reflect = AsyncMock()
        return r

    async def test_reflect_trade_delegates(self, mock_reflector):
        mem = AgentMemory(trade_reflector=mock_reflector)
        trade = {"symbol": "BTC/USD", "side": "buy"}
        await mem.reflect_trade(trade, agent_name="rsi_agent")
        mock_reflector.reflect.assert_awaited_once_with(
            trade=trade, agent_name="rsi_agent"
        )

    async def test_reflect_trade_no_reflector_returns_none(self):
        mem = AgentMemory()
        result = await mem.reflect_trade({"symbol": "BTC"}, agent_name="test")
        assert result is None
