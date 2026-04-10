from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SearchTuningConfig:
    """Search tuning parameters (MemClaw-compatible)."""

    top_k: int = 5
    min_similarity: float = 0.3
    fts_weight: float = 0.3
    freshness_floor: float = 0.0
    freshness_decay_days: int = 30
    graph_max_hops: int = 1
    similarity_blend: float = 0.7


class MemoryRegistry:
    def __init__(self):
        self._clients: dict[str, Any] = {}
        self._shared: Any | None = None
        self._tuning_configs: dict[str, SearchTuningConfig] = {}

    def register_client(self, agent_name: str, client: Any) -> None:
        self._clients[agent_name] = client

    def get_client(self, agent_name: str) -> Any | None:
        return self._clients.get(agent_name)

    def register_shared(self, client: Any) -> None:
        self._shared = client

    def get_shared(self) -> Any | None:
        return self._shared

    def get_tuning_config(self, agent_name: str) -> SearchTuningConfig:
        """Get tuning config for agent, creating default if not exists."""
        if agent_name not in self._tuning_configs:
            self._tuning_configs[agent_name] = SearchTuningConfig()
        return self._tuning_configs[agent_name]

    def set_tuning_config(self, agent_name: str, config: SearchTuningConfig) -> None:
        """Set tuning config for agent."""
        self._tuning_configs[agent_name] = config


# Global instance for DI
memory_registry = MemoryRegistry()
