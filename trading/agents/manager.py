from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

from agents.base import Agent
from agents.models import AgentConfig, AgentSignal, Opportunity


class ManagerAgent(Agent):
    """Manager agents monitor macro conditions and publish directives.
    They do not trade directly."""

    def __init__(self, config: AgentConfig, sub_agents: list[Agent] | None = None) -> None:
        super().__init__(config)
        self.sub_agents = sub_agents or []

    @abstractmethod
    async def evaluate_regime(self, data) -> dict[str, Any]:
        """Evaluate current market regime. Returns a state dictionary."""
        ...

    async def scan(self, data) -> list[Opportunity]:
        regime_state = await self.evaluate_regime(data)

        if self.signal_bus:
            sig = AgentSignal(
                source_agent=self.name,
                signal_type="regime_update",
                payload=regime_state,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
            )
            await self.signal_bus.publish(sig)

        return []
