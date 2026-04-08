from typing import Any

class MemoryRegistry:
    def __init__(self):
        self._clients: dict[str, Any] = {}
        self._shared: Any = None

    def register_client(self, agent_name: str, client: Any) -> None:
        self._clients[agent_name] = client

    def get_client(self, agent_name: str) -> Any | None:
        return self._clients.get(agent_name)

    def register_shared(self, client: Any) -> None:
        self._shared = client

    def get_shared(self) -> Any | None:
        return self._shared

# Global instance for DI
memory_registry = MemoryRegistry()
