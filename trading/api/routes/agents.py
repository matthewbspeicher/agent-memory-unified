# api/routes/agents.py
import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Request

from agents.runner import AgentRunner
from agents.models import AgentInfo, Opportunity, AgentStatus
from agents.config import _STRATEGY_REGISTRY, _ensure_strategies_registered
from api.deps import get_agent_runner, check_kill_switch
from api.auth import verify_api_key, _get_settings
from api.identity.dependencies import require_scope
from utils.audit import audit_event

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents", tags=["agents"], dependencies=[Depends(verify_api_key)]
)


@router.get("", response_model=list[AgentInfo])
def list_agents(runner: AgentRunner = Depends(get_agent_runner)) -> list[AgentInfo]:
    return runner.list_agents()


@router.post("", status_code=201, dependencies=[Depends(check_kill_switch)])
@audit_event("agents.create")
async def create_agent(payload: dict, request: Request):
    """Create a new agent in the registry.

    Gemini design §1.1: Allows Hermes to autonomously spawn agents.
    Payload should match AgentStore.create() requirements.
    """
    from storage.agent_registry import AgentStore

    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    store = AgentStore(db)
    try:
        # Check if agent already exists
        existing = await store.get(payload["name"])
        if existing:
            raise HTTPException(
                status_code=409, detail=f"Agent '{payload['name']}' already exists"
            )

        # Create the agent
        created = await store.create(payload)
        return created
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required field: {e}")
    except Exception as e:
        logger.error("Failed to create agent: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def get_runner_status(runner: AgentRunner = Depends(get_agent_runner)):
    """Get high-level status of the AgentRunner and all agents."""
    agents = runner.list_agents()
    return {
        "agent_count": len(agents),
        "running_count": sum(1 for a in agents if a.status == AgentStatus.RUNNING),
        "stopped_count": sum(1 for a in agents if a.status == AgentStatus.STOPPED),
        "error_count": sum(1 for a in agents if a.status == AgentStatus.ERROR),
        "polling_active": runner._poll_task is not None
        and not runner._poll_task.done(),
        "agents": [
            {
                "name": a.name,
                "status": a.status,
                "last_run": a.last_run,
                "error_count": a.error_count,
                "shadow_mode": a.config.shadow_mode,
            }
            for a in agents
        ],
    }


@router.post("/sync")
async def sync_agents(runner: AgentRunner = Depends(get_agent_runner)):
    """Manually trigger reconciliation of running agents against the registry."""
    await runner._reconcile_registry()
    return {"status": "ok", "message": "Agent registry reconciliation completed"}


@router.get("/strategies")
async def list_strategies():
    """List all available strategies with their parameter schemas.

    Gemini design §2.1: Returns strategy names and PARAMETER_SCHEMA
    so Hermes can compose agents with valid parameters.
    """
    _ensure_strategies_registered()
    strategies = []
    for name, cls in _STRATEGY_REGISTRY.items():
        schema = getattr(cls, "PARAMETER_SCHEMA", {})
        strategies.append(
            {
                "name": name,
                "parameter_schema": schema,
            }
        )
    return strategies


@router.get("/me/graph")
async def get_agent_graph(request: Request):
    """Return the spatial knowledge graph for 3D visualization.
    Converts TradingKnowledgeGraph triples into nodes and links.
    """
    kg = getattr(request.app.state, "knowledge_graph", None)
    if not kg:
        # Fallback to empty graph if no KG
        return {"nodes": [], "links": []}

    try:
        # Get up to 500 recent facts to build the graph
        triples = await kg.timeline(limit=500)

        nodes_dict = {}
        links = []

        for t in triples:
            sub = t["subject"]
            obj = t["object"]
            rel = t["predicate"]

            if sub not in nodes_dict:
                nodes_dict[sub] = {
                    "id": sub,
                    "summary": sub.replace("_", " ").title(),
                    "type": "agent",
                }
            if obj not in nodes_dict:
                nodes_dict[obj] = {
                    "id": obj,
                    "summary": obj.replace("_", " ").title(),
                    "type": "memory",
                }

            links.append(
                {
                    "source": sub,
                    "target": obj,
                    "relation": rel,
                    "metadata": t.get("properties", {}),
                }
            )

        return {"nodes": list(nodes_dict.values()), "links": links}
    except Exception as e:
        logger.error(f"Failed to fetch 3D graph: {e}")
        return {"nodes": [], "links": []}


@router.get("/{name}", response_model=AgentInfo)
def get_agent(name: str, runner: AgentRunner = Depends(get_agent_runner)) -> AgentInfo:
    info = runner.get_agent_info(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return info


@router.patch("/{name}")
async def update_agent(name: str, payload: dict, request: Request):
    """Partially update an agent's configuration in the registry.

    Gemini design §1.1: Allows Hermes to tune or retire agents.
    """
    from storage.agent_registry import AgentStore

    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    store = AgentStore(db)
    try:
        updated = await store.update(name, payload)
        if not updated:
            raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
        return updated
    except Exception as e:
        logger.error("Failed to update agent '%s': %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{name}/start",
    dependencies=[Depends(check_kill_switch), Depends(require_scope("control:agents"))],
)
@audit_event("agents.start")
async def start_agent(
    name: str, request: Request, runner: AgentRunner = Depends(get_agent_runner)
):
    try:
        await runner.start_agent(name)
        return {"status": "ok", "message": f"Agent '{name}' started"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{name}/stop",
    dependencies=[Depends(check_kill_switch), Depends(require_scope("control:agents"))],
)
@audit_event("agents.stop")
async def stop_agent(
    name: str, request: Request, runner: AgentRunner = Depends(get_agent_runner)
):
    try:
        await runner.stop_agent(name)
        return {"status": "ok", "message": f"Agent '{name}' stopped"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{name}/scan",
    response_model=list[Opportunity],
    dependencies=[Depends(check_kill_switch), Depends(require_scope("control:agents"))],
)
@audit_event("agents.scan")
async def scan_agent(
    name: str, request: Request, runner: AgentRunner = Depends(get_agent_runner)
):
    try:
        return await runner.run_once(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{name}/evolve", dependencies=[Depends(require_scope("control:agents"))])
async def evolve_agent(
    name: str, request: Request, runner: AgentRunner = Depends(get_agent_runner)
):
    """Generate and evaluate parameter variants for an agent.

    Gemini design §3.1: Allows Hermes to explore strategy improvements.
    """
    from agents.tuning import AdaptiveTuner
    from storage.performance import PerformanceStore
    from storage.opportunities import OpportunityStore
    from storage.trades import TradeStore
    from backtesting.sandbox import BacktestSandbox

    db = getattr(request.app.state, "db", None)
    data_bus = getattr(request.app.state, "data_bus", None)
    if not db or not data_bus:
        raise HTTPException(status_code=500, detail="Required services not available")

    agent_info = runner.get_agent_info(name)
    if not agent_info:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    perf_store = PerformanceStore(db)
    opp_store = OpportunityStore(db)
    trade_store = TradeStore(db)
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

    # Get trailing performance
    history = await perf_store.get_history(name, limit=1)
    if not history:
        raise HTTPException(
            status_code=400, detail=f"No performance history for agent '{name}'"
        )

    latest = history[0]
    config = agent_info.config
    strategy = config.strategy
    base_params = config.parameters.copy()
    universe = config.universe
    symbols = (
        universe
        if isinstance(universe, list)
        else [universe]
        if isinstance(universe, str)
        else ["AAPL", "MSFT", "GOOGL"]
    )

    # Generate parameter variants via LLM
    snapshot = {
        "sharpe_ratio": latest.sharpe_ratio,
        "win_rate": latest.win_rate,
        "total_trades": latest.total_trades,
    }
    variants = await tuner.generate_parameter_variants(
        name, strategy, base_params, snapshot
    )
    if not variants:
        return {"agent_name": name, "variants": [], "message": "No variants generated"}

    # Evaluate all variants
    results = await sandbox.evaluate_variants(
        strategy=strategy,
        base_parameters=base_params,
        variants=variants,
        symbols=symbols[:10],
        period="6mo",
    )

    return {
        "agent_name": name,
        "current_sharpe": latest.sharpe_ratio,
        "variants": [r.to_dict() for r in results],
        "message": f"Generated and evaluated {len(results)} variants",
    }


@router.put("/{name}/remembr-token")
async def set_remembr_token(
    name: str,
    payload: dict,
    request: Request,
    runner: AgentRunner = Depends(get_agent_runner),
):
    from storage.agent_registry import AgentStore

    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    store = AgentStore(db)
    entry = await store.get(name)
    params = entry.get("runtime_overrides", {}) if entry else {}

    params["remembr_api_token"] = payload.get("token")
    await store.update(name, runtime_overrides=params)

    # Update running instance config dynamically
    agent = runner._agents.get(name)
    if agent:
        agent.config.remembr_api_token = payload.get("token")
        agent.config.runtime_overrides = params

    return {"status": "ok", "message": f"Token updated for agent {name}"}


@router.get("/{name}/lessons")
async def get_agent_lessons(name: str, request: Request):
    db = getattr(request.app.state, "db", None)
    if db is None:
        return []
    try:
        cursor = await db.execute(
            "SELECT category, lesson, applies_to, created_at FROM llm_lessons "
            "WHERE agent_name = ? ORDER BY created_at DESC LIMIT 20",
            (name,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
