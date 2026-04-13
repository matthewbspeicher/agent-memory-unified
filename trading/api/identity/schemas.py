"""Pydantic request/response models for identity endpoints."""

from pydantic import BaseModel, Field


class AgentRegistrationRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=64)
    tier: str = Field(default="verified")
    scopes: list[str] | None = None
    contact_email: str | None = None
    moltbook_handle: str | None = None
    notes: str | None = None


class AgentRegistrationResponse(BaseModel):
    name: str
    id: str
    tier: str
    scopes: list[str]
    token: str
    warning: str


class AgentProfile(BaseModel):
    name: str
    scopes: list[str]
    tier: str


class RevocationRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
