"""FastAPI dependencies for identity resolution and scope checking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from .store import IdentityStore
from .tokens import verify_token


@dataclass(frozen=True)
class Identity:
    name: str
    scopes: frozenset[str]
    tier: str
    agent_id: str | None = None


ANONYMOUS_IDENTITY = Identity(
    name="anonymous",
    scopes=frozenset(["read:arena", "read:kg"]),
    tier="anonymous",
)


def _get_store(request: Request) -> IdentityStore:
    store = getattr(request.app.state, "identity_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="identity store not initialized")
    return store


def _get_master_api_key(request: Request) -> str | None:
    config = getattr(request.app.state, "config", None)
    if not config:
        return None
    return getattr(config, "api_key", None)


async def resolve_identity(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    x_agent_token: Annotated[str | None, Header()] = None,
) -> Identity:
    if x_agent_token:
        if not x_agent_token.startswith("amu_") or "." not in x_agent_token:
            raise HTTPException(status_code=401, detail="invalid X-Agent-Token format")
        
        try:
            agent_name = x_agent_token[4:].split(".", 1)[0]
        except ValueError:
            raise HTTPException(status_code=401, detail="invalid X-Agent-Token format")

        store = _get_store(request)
        agent = await store.get_by_name(agent_name)
        
        if agent and not agent.revoked_at:
            if verify_token(x_agent_token, agent.token_hash):
                return Identity(
                    name=agent.name,
                    scopes=frozenset(agent.scopes),
                    tier=agent.tier,
                    agent_id=agent.id,
                )
        raise HTTPException(status_code=401, detail="invalid X-Agent-Token")

    master_key = _get_master_api_key(request)
    if x_api_key and master_key and x_api_key == master_key:
        return Identity(
            name="master",
            scopes=frozenset(["admin", "*"]),
            tier="admin",
        )

    return ANONYMOUS_IDENTITY


def _stash_audit(request: Request, identity: Identity, scope_required: str) -> None:
    """Record the verified identity + declared scope on request.state so that
    AuditLogMiddleware can emit a structured ``audit.request`` event after the
    handler runs. Called before any 403 so rejections are also auditable."""
    request.state.identity_audit = {
        "agent_name": identity.name,
        "scope_required": scope_required,
        "tier": identity.tier,
        "agent_id": identity.agent_id,
    }


def require_scope(scope: str):
    async def checker(
        request: Request,
        identity: Annotated[Identity, Depends(resolve_identity)],
    ) -> Identity:
        _stash_audit(request, identity, scope)
        if "admin" in identity.scopes or "*" in identity.scopes:
            return identity
        if scope in identity.scopes:
            return identity
        raise HTTPException(
            status_code=403,
            detail=f"scope '{scope}' required (caller has: {sorted(identity.scopes)})",
        )

    return checker


def require_any_scope(*scopes: str):
    async def checker(
        request: Request,
        identity: Annotated[Identity, Depends(resolve_identity)],
    ) -> Identity:
        _stash_audit(request, identity, "|".join(scopes))
        if "admin" in identity.scopes or "*" in identity.scopes:
            return identity
        if any(s in identity.scopes for s in scopes):
            return identity
        raise HTTPException(
            status_code=403,
            detail=f"one of {list(scopes)} required (caller has: {sorted(identity.scopes)})",
        )

    return checker
