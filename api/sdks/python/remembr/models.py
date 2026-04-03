from __future__ import annotations

from pydantic import BaseModel


class Memory(BaseModel):
    id: str
    key: str | None = None
    value: str
    summary: str | None = None
    type: str = "note"
    category: str | None = None
    visibility: str = "private"
    importance: int = 5
    confidence: float = 1.0
    access_count: int = 0
    useful_count: int = 0
    metadata: dict | None = None
    tags: list[str] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None


class SearchResult(BaseModel):
    memories: list[Memory]


class ExtractedMemory(BaseModel):
    value: str
    type: str
    key: str | None = None
    importance: int = 5
