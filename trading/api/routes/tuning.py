from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.deps import get_agent_runner, get_opportunity_store, get_trade_store
from api.auth import verify_api_key, _get_settings
from agents.runner import AgentRunner
from agents.models import AgentStatus
from agents.tuning import AdaptiveTuner
from storage.opportunities import OpportunityStore
from storage.trades import TradeStore

router = APIRouter(
    prefix="/tuning", tags=["tuning"], dependencies=[Depends(verify_api_key)]
)


class TuningCycleResponse(BaseModel):
    status: str
    message: str
    new_overrides: dict


class RecommendationsResponse(BaseModel):
    agent_name: str
    recommendations: str


@router.post("/evolution/trigger")
async def trigger_evolution_cycle(
    request: Request,
    runner: AgentRunner = Depends(get_agent_runner),
):
    """Manually trigger the parameter exploration and evolution cycle for all agents.

    Gemini design §3.1: Allows Hermes to manually trigger strategy evolution.
    """
    from storage.performance import PerformanceStore
    from storage.opportunities import OpportunityStore
    from storage.trades import TradeStore
    from agents.tuning import AdaptiveTuner
    from backtesting.sandbox import BacktestSandbox
    from storage.agent_registry import AgentStore

    db = getattr(request.app.state, "db", None)
    data_bus = getattr(request.app.state, "data_bus", None)
    if not db or not data_bus:
        raise HTTPException(status_code=500, detail="Required services not available")

    perf_store = PerformanceStore(db)
    opp_store = OpportunityStore(db)
    trade_store = TradeStore(db)
    agent_store = AgentStore(db)
    settings = _get_settings()
    tuner = AdaptiveTuner(
        runner,
        opp_store,
        trade_store,
        anthropic_key=settings.anthropic_api_key,
        groq_key=settings.groq_api_key,
        ollama_url=settings.ollama_base_url,
    )
    sandbox = BacktestSandbox(data_bus=data_bus)

    agents = runner.list_agents()
    spawned = []

    for info in agents:
        if info.status != AgentStatus.RUNNING:
            continue

        # Check trailing performance
        history = await perf_store.get_history(info.name, limit=1)
        if not history:
            continue

        latest = history[0]
        # Allow evolution if Sharpe < 1.5 (Governor threshold)
        if latest.sharpe_ratio >= 1.5:
            continue

        config = info.config
        strategy = config.strategy
        base_params = config.parameters.copy()
        universe = (
            config.universe
            if isinstance(config.universe, list)
            else [config.universe]
            if isinstance(config.universe, str)
            else ["AAPL", "MSFT", "GOOGL"]
        )

        # Generate parameter variants via LLM
        snapshot = {
            "sharpe_ratio": latest.sharpe_ratio,
            "win_rate": latest.win_rate,
            "total_trades": latest.total_trades,
        }
        variants = await tuner.generate_parameter_variants(
            info.name, strategy, base_params, snapshot
        )
        if not variants:
            continue

        # Evaluate all variants
        results = await sandbox.evaluate_variants(
            strategy=strategy,
            base_parameters=base_params,
            variants=variants,
            symbols=universe[:10],
            period="6mo",
        )

        for variant, result in zip(variants, results):
            improvement = result.sharpe_ratio - latest.sharpe_ratio
            if improvement > 0.5:
                # Auto-spawn shadow variant
                evolved_name = f"{info.name}_v{int(datetime.now().timestamp()) % 10000}"
                spawn_data = {
                    "name": evolved_name,
                    "strategy": strategy,
                    "parent_name": info.name,
                    "parameters": variant["parameters"],
                    "universe": universe,
                    "creation_context": {
                        "reason": "manual_evolution_trigger",
                        "parent_sharpe": latest.sharpe_ratio,
                        "variant_sharpe": result.sharpe_ratio,
                        "improvement": improvement,
                    },
                }
                await agent_store.create_evolved_agent(**spawn_data)
                spawned.append(evolved_name)
                break  # Only spawn the best one

    return {
        "status": "ok",
        "message": f"Evolution cycle completed. Spawned {len(spawned)} shadow agent(s).",
        "spawned_agents": spawned,
    }


@router.post("/{agent_name}/cycle", response_model=TuningCycleResponse)
async def run_tuning_cycle(
    agent_name: str,
    runner: AgentRunner = Depends(get_agent_runner),
    opp_store: OpportunityStore = Depends(get_opportunity_store),
    trade_store: TradeStore = Depends(get_trade_store),
):
    agent_info = runner.get_agent_info(agent_name)
    if not agent_info:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    settings = _get_settings()
    tuner = AdaptiveTuner(
        runner,
        opp_store,
        trade_store,
        anthropic_key=settings.anthropic_api_key,
        groq_key=settings.groq_api_key,
        ollama_url=settings.ollama_base_url,
    )
    await tuner.tune_agent(agent_name)

    updated_info = runner.get_agent_info(agent_name)
    return {
        "status": "ok",
        "message": f"Tuning cycle completed for '{agent_name}'",
        "new_overrides": updated_info.config.runtime_overrides
        if updated_info is not None
        else {},
    }


@router.get("/{agent_name}/recommendations", response_model=RecommendationsResponse)
async def get_tuning_recommendations(
    agent_name: str,
    runner: AgentRunner = Depends(get_agent_runner),
    opp_store: OpportunityStore = Depends(get_opportunity_store),
    trade_store: TradeStore = Depends(get_trade_store),
):
    agent_info = runner.get_agent_info(agent_name)
    if not agent_info:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    settings = _get_settings()
    tuner = AdaptiveTuner(
        runner,
        opp_store,
        trade_store,
        anthropic_key=settings.anthropic_api_key,
        groq_key=settings.groq_api_key,
        ollama_url=settings.ollama_base_url,
    )
    execution_rate, _ = await tuner.get_agent_execution_rate(agent_name)
    perf_snapshot = {"execution_rate": execution_rate}

    recommendations = await tuner.generate_recommendations(agent_name, perf_snapshot)

    return {
        "agent_name": agent_name,
        "recommendations": recommendations,
    }


class GridSearchRequest(BaseModel):
    param_space: dict[str, list]


class GeneticOptimizeRequest(BaseModel):
    param_bounds: dict[str, tuple[float, float]]
    population_size: int = 20
    generations: int = 10
    mutation_rate: float = 0.1


@router.post("/{agent_name}/grid-search")
async def run_grid_search(
    agent_name: str,
    body: GridSearchRequest,
    request: Request,
    runner: AgentRunner = Depends(get_agent_runner),
    opp_store: OpportunityStore = Depends(get_opportunity_store),
    trade_store: TradeStore = Depends(get_trade_store),
):
    """Run grid search over parameter combinations."""
    from backtesting.sandbox import BacktestSandbox

    agent_info = runner.get_agent_info(agent_name)
    if not agent_info:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    db = getattr(request.app.state, "db", None)
    data_bus = getattr(request.app.state, "data_bus", None)
    if not db or not data_bus:
        raise HTTPException(status_code=500, detail="Required services not available")

    settings = _get_settings()
    tuner = AdaptiveTuner(
        runner,
        opp_store,
        trade_store,
        anthropic_key=settings.anthropic_api_key,
        groq_key=settings.groq_api_key,
        ollama_url=settings.ollama_base_url,
    )
    sandbox = BacktestSandbox(data_bus=data_bus)

    config = agent_info.config
    strategy = config.strategy
    universe = (
        config.universe if isinstance(config.universe, list) else [config.universe]
    )

    async def backtest_fn(params: dict) -> dict:
        results = await sandbox.evaluate(
            strategy=strategy,
            parameters=params,
            symbols=universe[:10],
            period="3mo",
        )
        return {
            "sharpe_ratio": results.sharpe_ratio,
            "win_rate": results.win_rate,
            "max_drawdown": results.max_drawdown_pct,
            "total_trades": results.total_trades,
        }

    results = await tuner.grid_search(agent_name, body.param_space, backtest_fn)

    return {
        "agent_name": agent_name,
        "results": results[:20],
        "total_tested": len(results),
    }


@router.post("/{agent_name}/genetic-optimize")
async def run_genetic_optimize(
    agent_name: str,
    body: GeneticOptimizeRequest,
    request: Request,
    runner: AgentRunner = Depends(get_agent_runner),
    opp_store: OpportunityStore = Depends(get_opportunity_store),
    trade_store: TradeStore = Depends(get_trade_store),
):
    """Run genetic algorithm for continuous parameter optimization."""
    from backtesting.sandbox import BacktestSandbox

    agent_info = runner.get_agent_info(agent_name)
    if not agent_info:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    db = getattr(request.app.state, "db", None)
    data_bus = getattr(request.app.state, "data_bus", None)
    if not db or not data_bus:
        raise HTTPException(status_code=500, detail="Required services not available")

    settings = _get_settings()
    tuner = AdaptiveTuner(
        runner,
        opp_store,
        trade_store,
        anthropic_key=settings.anthropic_api_key,
        groq_key=settings.groq_api_key,
        ollama_url=settings.ollama_base_url,
    )
    sandbox = BacktestSandbox(data_bus=data_bus)

    config = agent_info.config
    strategy = config.strategy
    universe = (
        config.universe if isinstance(config.universe, list) else [config.universe]
    )

    async def backtest_fn(params: dict) -> dict:
        results = await sandbox.evaluate(
            strategy=strategy,
            parameters=params,
            symbols=universe[:10],
            period="3mo",
        )
        return {"sharpe_ratio": results.sharpe_ratio}

    param_bounds: dict[str, tuple[float, float]] = {
        k: (v[0], v[1]) for k, v in body.param_bounds.items()
    }
    result = await tuner.genetic_optimize(
        agent_name,
        param_bounds,
        backtest_fn,
        population_size=body.population_size,
        generations=body.generations,
        mutation_rate=body.mutation_rate,
    )

    return result
