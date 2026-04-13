"""Admin-only identity management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, HTTPException

from api.identity.dependencies import resolve_identity, require_scope, Identity
from api.identity.schemas import (
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    AgentProfile,
    RevocationRequest,
)
from api.identity.tokens import generate_token, hash_token
from api.identity.store import IdentityStore, DuplicateAgentError

router = APIRouter(prefix="/api/v1/identity", tags=["identity"])


def _get_store(request: Request) -> IdentityStore:
    store = getattr(request.app.state, "identity_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="identity store not initialized")
    return store


@router.post("/agents", response_model=AgentRegistrationResponse)
async def register_agent(
    req: AgentRegistrationRequest,
    request: Request,
    identity: Identity = Depends(require_scope("admin")),
):
    store = _get_store(request)
    token = generate_token()
    token_hash = hash_token(token)

    try:
        agent = await store.create(
            name=req.name,
            token_hash=token_hash,
            scopes=req.scopes or [],
            tier=req.tier,
            created_by=identity.name,
            contact_email=req.contact_email,
            moltbook_handle=req.moltbook_handle,
        )
    except DuplicateAgentError:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{req.name}' already exists",
        )

    await store.audit(
        event="created",
        agent_name=req.name,
        actor=identity.name,
        details={"tier": req.tier, "scopes": req.scopes or []},
    )

    return AgentRegistrationResponse(
        name=agent.name,
        id=agent.id,
        tier=agent.tier,
        scopes=agent.scopes,
        token=token,
        warning="Store this token securely. It will not be shown again.",
    )


@router.get("/me", response_model=AgentProfile)
async def get_my_profile(identity: Identity = Depends(resolve_identity)):
    return AgentProfile(
        name=identity.name,
        scopes=sorted(identity.scopes),
        tier=identity.tier,
    )


@router.post("/agents/{agent_name}/revoke")
async def revoke_agent(
    agent_name: str,
    req: RevocationRequest,
    request: Request,
    identity: Identity = Depends(require_scope("admin")),
):
    store = _get_store(request)
    agent = await store.get_by_name(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    await store.revoke(name=agent_name, reason=req.reason, actor=identity.name)
    await store.audit(
        event="revoked",
        agent_name=agent_name,
        actor=identity.name,
        details={"reason": req.reason},
    )

    return {"status": "revoked", "name": agent_name}


@router.post("/agents/{agent_name}/rotate")
async def rotate_token(
    agent_name: str,
    request: Request,
    identity: Identity = Depends(require_scope("admin")),
):
    store = _get_store(request)
    agent = await store.get_by_name(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    new_token = generate_token()
    new_hash = hash_token(new_token)
    await store.update_token_hash(name=agent_name, token_hash=new_hash)
    await store.audit(
        event="token_rotated",
        agent_name=agent_name,
        actor=identity.name,
        details={},
    )

    return {
        "name": agent_name,
        "token": new_token,
        "warning": "Store this token securely. It will not be shown again.",
    }
