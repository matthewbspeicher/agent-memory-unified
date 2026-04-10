from importlib import import_module


def __getattr__(name: str):
    if name in {"BacktestEngine"}:
        return import_module("backtesting.engine").BacktestEngine
    if name in {"BacktestConfig", "BacktestResult"}:
        return getattr(import_module("backtesting.models"), name)
    if name in {"BacktestSandbox", "SandboxResult"}:
        return getattr(import_module("backtesting.sandbox"), name)
    if name in {"ConsensusSimulator", "ConsensusSimulationResult", "ConsensusMetrics"}:
        return getattr(import_module("backtesting.consensus_sim"), name)
    raise AttributeError(name)


__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "BacktestSandbox",
    "SandboxResult",
    "ConsensusSimulator",
    "ConsensusSimulationResult",
    "ConsensusMetrics",
]
