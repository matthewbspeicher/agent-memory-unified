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
        store = _get_store(request)
        agents = await store.list_active()
        for agent in agents:
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


def require_scope(scope: str):
    async def checker(
        identity: Annotated[Identity, Depends(resolve_identity)],
    ) -> Identity:
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
        identity: Annotated[Identity, Depends(resolve_identity)],
    ) -> Identity:
        if "admin" in identity.scopes or "*" in identity.scopes:
            return identity
        if any(s in identity.scopes for s in scopes):
            return identity
        raise HTTPException(
            status_code=403,
            detail=f"one of {list(scopes)} required (caller has: {sorted(identity.scopes)})",
        )

    return checker
