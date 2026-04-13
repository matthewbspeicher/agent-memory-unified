import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import verify_api_key
from api.identity.dependencies import require_scope
from utils.audit import audit_event

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/drafts", tags=["drafts"], dependencies=[Depends(verify_api_key)]
)


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
    response_model=DraftResponse,
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
    return draft


@router.get("", dependencies=[Depends(require_scope("write:orders"))])
async def list_drafts(status: str | None = None, request: Request = None):
    store = _get_store(request)
    return await store.list_drafts(status=status)


@router.get(
    "/{draft_id}",
    response_model=DraftResponse,
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

    import random

    results = {
        "sharpe_ratio": round(random.uniform(0.5, 2.5), 2),
        "win_rate": round(random.uniform(0.4, 0.7), 2),
        "max_drawdown": round(random.uniform(-0.25, -0.05), 2),
        "total_trades": random.randint(20, 100),
        "equity_curve": _generate_equity_curve(),
        "status": "scaffold",
    }

    await store.update_draft_results(draft_id, results)
    return {"data": results}


def _generate_equity_curve():
    import random
    from datetime import datetime, timedelta

    curve = []
    equity = 100000
    now = datetime.now()
    for i in range(30):
        equity *= 1 + random.uniform(-0.02, 0.03)
        curve.append(
            {
                "timestamp": (now - timedelta(days=29 - i)).isoformat(),
                "equity": round(equity, 2),
            }
        )
    return curve


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

    await store.update_draft_status(draft_id, "deployed")
    return {
        "data": {
            "id": draft_id,
            "name": draft["name"],
            "status": "deployed",
            "message": f"Draft '{draft['name']}' marked for deployment. Full agent roster integration pending.",
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
