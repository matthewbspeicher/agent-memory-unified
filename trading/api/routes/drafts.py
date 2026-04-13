import asyncio
import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import verify_api_key
from api.identity.dependencies import require_scope
from utils.audit import audit_event

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/drafts", tags=["drafts"], dependencies=[Depends(verify_api_key)]
)

_AGENTS_YAML = Path(__file__).parent.parent.parent / "agents.yaml"


class DraftCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    system_prompt: str = Field(min_length=1)
    model: str = "gpt-4o"
    hyperparameters: dict = {}


class DraftResponse(BaseModel):
    id: str
    name: str
    system_prompt: str
    model: str
    hyperparameters: dict
    status: str
    backtest_results: dict | None
    created_at: str | None
    updated_at: str | None


def _get_store(request: Request):
    store = getattr(request.app.state, "identity_store", None)
    if not store:
        raise HTTPException(status_code=500, detail="Identity store not available")
    return store


@router.post(
    "",
    dependencies=[Depends(require_scope("write:orders"))],
)
@audit_event("drafts.create")
async def create_draft(req: DraftCreateRequest, request: Request):
    store = _get_store(request)
    draft_id = await store.create_draft(
        name=req.name,
        system_prompt=req.system_prompt,
        model=req.model,
        hyperparameters=req.hyperparameters,
    )
    draft = await store.get_draft(draft_id)
    return {"data": draft}


@router.get("", dependencies=[Depends(require_scope("write:orders"))])
async def list_drafts(status: str | None = None, request: Request = None):
    store = _get_store(request)
    return await store.list_drafts(status=status)


@router.get(
    "/{draft_id}",
    dependencies=[Depends(require_scope("write:orders"))],
)
async def get_draft(draft_id: str, request: Request):
    store = _get_store(request)
    draft = await store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.post(
    "/{draft_id}/backtest", dependencies=[Depends(require_scope("write:orders"))]
)
@audit_event("drafts.backtest")
async def backtest_draft(draft_id: str, request: Request):
    store = _get_store(request)
    draft = await store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    from backtest.engine import run_backtest

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None,
        lambda: run_backtest(
            symbols=draft["hyperparameters"].get("symbols", ["BTC", "ETH"]),
            days=draft["hyperparameters"].get("backtest_days", 90),
            initial_capital=draft["hyperparameters"].get("initial_capital", 100_000),
        ),
    )

    await store.update_draft_results(draft_id, results)
    return {"data": results}


@router.post(
    "/{draft_id}/deploy", dependencies=[Depends(require_scope("control:agents"))]
)
@audit_event("drafts.deploy")
async def deploy_draft(draft_id: str, request: Request):
    store = _get_store(request)
    draft = await store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "tested":
        raise HTTPException(
            status_code=400,
            detail="Draft must be tested before deployment. Run backtest first.",
        )

    agent_name = draft["name"].lower().replace(" ", "_")

    # Build the agent entry for agents.yaml
    new_agent = {
        "name": agent_name,
        "strategy": "llm_analyst",
        "schedule": "on_demand",
        "action_level": "notify",
        "model": draft["model"],
        "system_prompt": draft["system_prompt"],
        "trust_level": "monitored",
        "parameters": {
            k: v
            for k, v in draft["hyperparameters"].items()
            if k not in ("symbols", "backtest_days", "initial_capital")
        },
    }

    # Append to agents.yaml
    if _AGENTS_YAML.exists():
        data = yaml.safe_load(_AGENTS_YAML.read_text()) or {}
    else:
        data = {}

    agents_list = data.get("agents", [])

    # Check for duplicate name
    if any(a.get("name") == agent_name for a in agents_list):
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{agent_name}' already exists in roster.",
        )

    agents_list.append(new_agent)
    data["agents"] = agents_list
    _AGENTS_YAML.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    logger.info("Deployed draft '%s' as agent '%s' to agents.yaml", draft["name"], agent_name)

    await store.update_draft_status(draft_id, "deployed")
    return {
        "data": {
            "id": draft_id,
            "name": agent_name,
            "status": "deployed",
            "message": f"Agent '{agent_name}' added to roster. Restart trading engine to activate.",
        }
    }


@router.delete("/{draft_id}", dependencies=[Depends(require_scope("control:agents"))])
@audit_event("drafts.delete")
async def delete_draft(draft_id: str, request: Request):
    store = _get_store(request)
    draft = await store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    await store.delete_draft(draft_id)
    return {"data": {"id": draft_id, "deleted": True}}
