# api/routes/opportunities.py
from __future__ import annotations
import hashlib
import hmac as hmac_mod
import time
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agents.models import OpportunityStatus
from api.auth import verify_api_key, _get_settings, get_current_user
from api.identity.dependencies import require_scope
from models.user import User, PlatformTier
from api.deps import get_opportunity_store

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

_REFUSAL_STATUS = {"not_found": 404, "expired": 410}


async def _reject_pending(store, opportunity_id: str) -> dict:
    """Reject an Opportunity nobody has acted on; an acted-on one keeps its status."""
    opp = await store.get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if not await store.transition(
        opportunity_id, OpportunityStatus.PENDING, OpportunityStatus.REJECTED
    ):
        raise HTTPException(
            status_code=409, detail=f"Opportunity is {opp['status']}, not pending"
        )
    return {"id": opportunity_id, "status": "rejected"}


async def _approve_and_execute(request: Request, opportunity_id: str) -> dict:
    """Approve a pending Opportunity and report what its order did."""
    from agents.approval import ApprovalRefused

    approver = getattr(request.app.state, "opportunity_approver", None)
    if approver is None:
        raise HTTPException(status_code=503, detail="Approval is not available")
    try:
        outcome = await approver.approve(opportunity_id)
    except ApprovalRefused as refused:
        raise HTTPException(
            status_code=_REFUSAL_STATUS.get(refused.reason, 409), detail=refused.detail
        ) from refused
    return {
        "id": outcome.opportunity_id,
        "status": outcome.status.value,
        "detail": outcome.detail,
    }


def _verify_signature(
    api_key: str, opportunity_id: str, action: str, ts: str, sig: str
) -> bool:
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs(time.time() - ts_int) > 86400:
        return False
    expected = hmac_mod.new(
        api_key.encode(),
        f"{opportunity_id}:{action}:{ts_int}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac_mod.compare_digest(expected, sig)


@router.get("")
async def list_opportunities(
    agent_name: str | None = None,
    symbol: str | None = None,
    signal: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    store=Depends(get_opportunity_store),
):
    min_age_hours = 1 if user.tier == PlatformTier.EXPLORER else None
    return await store.list(
        agent_name=agent_name, symbol=symbol, signal=signal, limit=limit, min_age_hours=min_age_hours
    )


@router.get("/{opportunity_id}")
async def get_opportunity(
    opportunity_id: str,
    _: str = Depends(verify_api_key),
    store=Depends(get_opportunity_store),
):
    opp = await store.get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp


@router.post(
    "/{opportunity_id}/approve",
    dependencies=[Depends(require_scope("write:orders"))],
)
async def approve_opportunity(
    opportunity_id: str,
    request: Request,
    ts: str | None = Query(default=None),
    sig: str | None = Query(default=None),
):
    settings = _get_settings()
    if not (ts and sig):
        raise HTTPException(status_code=403, detail="Signature required")
    if not _verify_signature(settings.api_key, opportunity_id, "approve", ts, sig):
        raise HTTPException(status_code=403, detail="Invalid or expired signature")

    return await _approve_and_execute(request, opportunity_id)


@router.post(
    "/{opportunity_id}/reject",
    dependencies=[Depends(require_scope("write:orders"))],
)
async def reject_opportunity(
    opportunity_id: str,
    request: Request,
    ts: str | None = Query(default=None),
    sig: str | None = Query(default=None),
):
    settings = _get_settings()
    if ts and sig:
        if not _verify_signature(settings.api_key, opportunity_id, "reject", ts, sig):
            raise HTTPException(status_code=403, detail="Invalid or expired signature")
    else:
        raise HTTPException(status_code=403, detail="Signature required")

    return await _reject_pending(get_opportunity_store(request), opportunity_id)


@router.post(
    "/{opportunity_id}/approve-auth",
    dependencies=[Depends(require_scope("write:orders"))],
)
async def approve_opportunity_authenticated(
    opportunity_id: str,
    request: Request,
):
    return await _approve_and_execute(request, opportunity_id)


@router.post(
    "/{opportunity_id}/reject-auth",
    dependencies=[Depends(require_scope("write:orders"))],
)
async def reject_opportunity_authenticated(
    opportunity_id: str,
    store=Depends(get_opportunity_store),
):
    return await _reject_pending(store, opportunity_id)


@router.get("/{opportunity_id}/snapshot")
async def get_opportunity_snapshot(
    opportunity_id: str,
    _: str = Depends(verify_api_key),
    store=Depends(get_opportunity_store),
):
    snapshot = await store.get_snapshot(opportunity_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot


@router.get("/{opportunity_id}/consensus")
async def get_opportunity_consensus(
    opportunity_id: str,
    _: str = Depends(verify_api_key),
    store=Depends(get_opportunity_store),
):
    opp = await store.get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    settings = _get_settings()
    if not settings.remembr_agent_token:
        return {"status": "disabled", "data": []}

    ticker = opp.symbol.ticker if opp.symbol else ""
    if not ticker:
        return {"status": "ok", "data": []}

    import httpx

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{settings.remembr_base_url}/search",
                params={"q": ticker},
                headers={"Authorization": f"Bearer {settings.remembr_agent_token}"},
                timeout=settings.remembr_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"status": "ok", "data": data.get("results", [])}
        except httpx.HTTPError as e:
            return {"status": "error", "message": str(e), "data": []}
