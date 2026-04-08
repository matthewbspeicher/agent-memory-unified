# trading/competition/registry.py
"""Competitor registry -- auto-registers agents, miners, providers on startup."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from competition.models import CompetitorCreate, CompetitorType
from competition.store import CompetitionStore

logger = logging.getLogger(__name__)

TRACKED_ASSETS = ["BTC", "ETH"]


class CompetitorRegistry:
    """Discovers and registers all competitors into the competition store."""

    def __init__(self, store: CompetitionStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------

    async def register_all(
        self,
        agents_yaml_path: str | Path | None = None,
        provider_names: list[str] | None = None,
        miner_hotkeys: list[str] | None = None,
    ) -> int:
        """Register all competitor sources.  Returns total count registered."""
        count = 0

        if agents_yaml_path is not None:
            path = Path(agents_yaml_path)
            if path.exists():
                yaml_str = path.read_text()
                count += await self.register_agents_from_yaml_str(yaml_str)
            else:
                logger.warning("agents.yaml not found at %s", path)

        if provider_names:
            count += await self.register_providers(provider_names)

        if miner_hotkeys:
            count += await self.register_miners(miner_hotkeys)

        logger.info("CompetitorRegistry: registered %d competitors total", count)
        return count

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    async def register_agents_from_yaml_str(self, yaml_str: str) -> int:
        """Parse agents YAML and upsert each agent as a competitor."""
        data = yaml.safe_load(yaml_str)
        agents = data.get("agents", []) if data else []
        count = 0
        for agent in agents:
            name = agent.get("name", "")
            if not name:
                continue
            comp = CompetitorCreate(
                type=CompetitorType.AGENT,
                name=name,
                ref_id=name,
                metadata={
                    "strategy": agent.get("strategy", ""),
                    "schedule": agent.get("schedule", ""),
                },
            )
            await self._store.upsert_competitor(comp)
            await self._ensure_elo(CompetitorType.AGENT, name)
            count += 1
        logger.info("Registered %d agents from YAML", count)
        return count

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------

    async def register_providers(self, names: list[str]) -> int:
        """Register data-provider competitors."""
        count = 0
        for name in names:
            comp = CompetitorCreate(
                type=CompetitorType.PROVIDER,
                name=name,
                ref_id=name,
            )
            await self._store.upsert_competitor(comp)
            await self._ensure_elo(CompetitorType.PROVIDER, name)
            count += 1
        logger.info("Registered %d providers", count)
        return count

    # ------------------------------------------------------------------
    # Miners
    # ------------------------------------------------------------------

    async def register_miners(self, miners: list[str]) -> int:
        """Register Bittensor miner competitors by hotkey."""
        count = 0
        for hotkey in miners:
            short_name = f"miner_{hotkey[:8]}"
            comp = CompetitorCreate(
                type=CompetitorType.MINER,
                name=short_name,
                ref_id=hotkey,
                metadata={"hotkey": hotkey},
            )
            await self._store.upsert_competitor(comp)
            await self._ensure_elo(CompetitorType.MINER, hotkey)
            count += 1
        logger.info("Registered %d miners", count)
        return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _ensure_elo(self, comp_type: CompetitorType, ref_id: str) -> None:
        """After upsert, ensure ELO rows exist for all tracked assets."""
        record = await self._store.get_competitor_by_ref(comp_type, ref_id)
        if record is None:
            return
        for asset in TRACKED_ASSETS:
            await self._store.ensure_elo_rating(record.id, asset)
