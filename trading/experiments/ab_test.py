from pydantic import BaseModel
import hashlib


class ExperimentConfig(BaseModel):
    name: str
    control_agent: str
    variant_agent: str
    variant_split: float = 0.5
    description: str | None = None
    is_arena: bool = False
    status: str = "running"
    started_at: str | None = None


class Experiment:
    def __init__(self, config: ExperimentConfig):
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def control_agent(self) -> str:
        return self.config.control_agent

    @property
    def variant_agent(self) -> str:
        return self.config.variant_agent

    @property
    def variant_split(self) -> float:
        return self.config.variant_split

    def get_assigned_agent(self, symbol: str) -> str:
        # Hash the symbol and experiment name to get a consistent float between 0 and 1
        h = hashlib.sha256(f"{self.name}:{symbol}".encode()).hexdigest()
        val = int(h[:8], 16) / 0xFFFFFFFF
        return self.variant_agent if val < self.variant_split else self.control_agent


class ExperimentManager:
    def __init__(self):
        self._experiments: dict[str, Experiment] = {}

    def add_experiment(self, config: ExperimentConfig) -> None:
        self._experiments[config.name] = Experiment(config)

    def remove_experiment(self, name: str) -> None:
        self._experiments.pop(name, None)

    def get_experiment(self, name: str) -> Experiment | None:
        return self._experiments.get(name)

    def get_all(self) -> list[Experiment]:
        return list(self._experiments.values())

    def should_allow_execution(self, agent_name: str, symbol: str) -> bool:
        """
        Returns True if the agent is allowed to execute for this symbol based on active A/B tests.
        If an agent is part of an experiment but not the assigned agent for the symbol, returns False.
        """
        for exp in self._experiments.values():
            if agent_name in (exp.control_agent, exp.variant_agent):
                assigned = exp.get_assigned_agent(symbol)
                if agent_name != assigned:
                    return False
        return True


_manager = ExperimentManager()


def get_experiment_manager() -> ExperimentManager:
    return _manager
