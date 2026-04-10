# tests/unit/competition/test_registry.py
"""Tests for CompetitorRegistry -- uses a MockStore to track calls."""
from __future__ import annotations


import pytest

from competition.models import CompetitorCreate, CompetitorType, CompetitorRecord
from competition.registry import CompetitorRegistry, TRACKED_ASSETS


# ------------------------------------------------------------------
# MockStore
# ------------------------------------------------------------------


class MockStore:
    """Records upserted competitors and ensured ELO rows."""

    def __init__(self) -> None:
        self.upserted: list[CompetitorCreate] = []
        self.elo_ensured: list[tuple[str, str]] = []  # (competitor_id, asset)
        self._id_counter = 0
        self._ref_to_id: dict[tuple[str, str], str] = {}

    async def upsert_competitor(self, competitor: CompetitorCreate) -> str:
        self.upserted.append(competitor)
        key = (competitor.type.value, competitor.ref_id)
        if key not in self._ref_to_id:
            self._id_counter += 1
            self._ref_to_id[key] = f"id-{self._id_counter}"
        return self._ref_to_id[key]

    async def get_competitor_by_ref(
        self, comp_type: CompetitorType, ref_id: str
    ) -> CompetitorRecord | None:
        key = (comp_type.value, ref_id)
        cid = self._ref_to_id.get(key)
        if cid is None:
            return None
        return CompetitorRecord(
            id=cid,
            type=comp_type,
            name=ref_id,
            ref_id=ref_id,
            status="active",
        )

    async def ensure_elo_rating(self, competitor_id: str, asset: str) -> None:
        self.elo_ensured.append((competitor_id, asset))


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


SAMPLE_YAML = """\
agents:
  - name: rsi_scanner
    strategy: rsi
    schedule: continuous
  - name: volume_spike
    strategy: volume_spike
    schedule: continuous
"""


@pytest.fixture
def mock_store() -> MockStore:
    return MockStore()


@pytest.fixture
def registry(mock_store) -> CompetitorRegistry:
    return CompetitorRegistry(mock_store)


# ------------------------------------------------------------------
# Tests: register_agents_from_yaml_str
# ------------------------------------------------------------------


class TestRegisterAgents:
    @pytest.mark.asyncio
    async def test_agents_parsed_from_yaml(self, registry, mock_store):
        count = await registry.register_agents_from_yaml_str(SAMPLE_YAML)
        assert count == 2

        names = [c.name for c in mock_store.upserted]
        assert "rsi_scanner" in names
        assert "volume_spike" in names

    @pytest.mark.asyncio
    async def test_agents_have_correct_type(self, registry, mock_store):
        await registry.register_agents_from_yaml_str(SAMPLE_YAML)
        for comp in mock_store.upserted:
            assert comp.type == CompetitorType.AGENT

    @pytest.mark.asyncio
    async def test_agents_ref_id_matches_name(self, registry, mock_store):
        await registry.register_agents_from_yaml_str(SAMPLE_YAML)
        for comp in mock_store.upserted:
            assert comp.ref_id == comp.name

    @pytest.mark.asyncio
    async def test_agents_metadata_contains_strategy(self, registry, mock_store):
        await registry.register_agents_from_yaml_str(SAMPLE_YAML)
        rsi = next(c for c in mock_store.upserted if c.name == "rsi_scanner")
        assert rsi.metadata["strategy"] == "rsi"

    @pytest.mark.asyncio
    async def test_elo_ensured_for_tracked_assets(self, registry, mock_store):
        await registry.register_agents_from_yaml_str(SAMPLE_YAML)
        # 2 agents x 2 assets = 4 ELO ensure calls
        assert len(mock_store.elo_ensured) == 4
        assets_seen = {asset for _, asset in mock_store.elo_ensured}
        assert assets_seen == set(TRACKED_ASSETS)

    @pytest.mark.asyncio
    async def test_empty_yaml(self, registry, mock_store):
        count = await registry.register_agents_from_yaml_str("agents: []")
        assert count == 0
        assert len(mock_store.upserted) == 0

    @pytest.mark.asyncio
    async def test_skips_agents_without_name(self, registry, mock_store):
        yaml_str = """\
agents:
  - strategy: rsi
  - name: valid_agent
    strategy: volume
"""
        count = await registry.register_agents_from_yaml_str(yaml_str)
        assert count == 1
        assert mock_store.upserted[0].name == "valid_agent"


# ------------------------------------------------------------------
# Tests: register_providers
# ------------------------------------------------------------------


class TestRegisterProviders:
    @pytest.mark.asyncio
    async def test_providers_registered_with_correct_type(self, registry, mock_store):
        count = await registry.register_providers(["sentiment", "on_chain"])
        assert count == 2
        for comp in mock_store.upserted:
            assert comp.type == CompetitorType.PROVIDER

    @pytest.mark.asyncio
    async def test_provider_ref_id_matches_name(self, registry, mock_store):
        await registry.register_providers(["sentiment"])
        assert mock_store.upserted[0].ref_id == "sentiment"

    @pytest.mark.asyncio
    async def test_elo_ensured_for_both_assets(self, registry, mock_store):
        await registry.register_providers(["sentiment"])
        assert len(mock_store.elo_ensured) == 2
        assets = {asset for _, asset in mock_store.elo_ensured}
        assert assets == {"BTC", "ETH"}


# ------------------------------------------------------------------
# Tests: register_miners
# ------------------------------------------------------------------


class TestRegisterMiners:
    @pytest.mark.asyncio
    async def test_miners_registered_with_correct_type(self, registry, mock_store):
        hotkeys = ["5DkVM4wyv4ZXGvb9ZmYafPiySbmWS4s2i5W37CNHuh4ggAha"]
        count = await registry.register_miners(hotkeys)
        assert count == 1
        assert mock_store.upserted[0].type == CompetitorType.MINER

    @pytest.mark.asyncio
    async def test_miner_name_uses_short_hotkey(self, registry, mock_store):
        hotkeys = ["5DkVM4wyv4ZXGvb9ZmYafPiySbmWS4s2i5W37CNHuh4ggAha"]
        await registry.register_miners(hotkeys)
        assert mock_store.upserted[0].name == "miner_5DkVM4wy"

    @pytest.mark.asyncio
    async def test_miner_ref_id_is_full_hotkey(self, registry, mock_store):
        hotkey = "5DkVM4wyv4ZXGvb9ZmYafPiySbmWS4s2i5W37CNHuh4ggAha"
        await registry.register_miners([hotkey])
        assert mock_store.upserted[0].ref_id == hotkey

    @pytest.mark.asyncio
    async def test_miner_metadata_has_hotkey(self, registry, mock_store):
        hotkey = "5DkVM4wyv4ZXGvb9ZmYafPiySbmWS4s2i5W37CNHuh4ggAha"
        await registry.register_miners([hotkey])
        assert mock_store.upserted[0].metadata["hotkey"] == hotkey

    @pytest.mark.asyncio
    async def test_elo_ensured_for_both_assets(self, registry, mock_store):
        await registry.register_miners(["5DkVM4wyv4ZXGvb9"])
        assert len(mock_store.elo_ensured) == 2
        assets = {asset for _, asset in mock_store.elo_ensured}
        assert assets == {"BTC", "ETH"}


# ------------------------------------------------------------------
# Tests: register_all
# ------------------------------------------------------------------


class TestRegisterAll:
    @pytest.mark.asyncio
    async def test_total_count(self, registry, mock_store, tmp_path):
        yaml_file = tmp_path / "agents.yaml"
        yaml_file.write_text(SAMPLE_YAML)

        count = await registry.register_all(
            agents_yaml_path=str(yaml_file),
            provider_names=["sentiment"],
            miner_hotkeys=["5DkVM4wyv4ZXGvb9"],
        )
        # 2 agents + 1 provider + 1 miner = 4
        assert count == 4

    @pytest.mark.asyncio
    async def test_missing_yaml_skipped(self, registry, mock_store):
        count = await registry.register_all(
            agents_yaml_path="/nonexistent/agents.yaml",
            provider_names=["sentiment"],
        )
        assert count == 1  # only the provider

    @pytest.mark.asyncio
    async def test_all_none(self, registry, mock_store):
        count = await registry.register_all()
        assert count == 0
