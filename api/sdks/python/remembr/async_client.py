from __future__ import annotations

from typing import Any

import httpx

from .exceptions import (
    AuthError,
    NotFoundError,
    RateLimitError,
    RemembrError,
    ValidationError,
)
from .models import Memory


class AsyncRemembrClient:
    """Asynchronous client for the Remembr API — long-term memory for AI agents."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://remembr.dev/api/v1",
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    # -- async context manager -----------------------------------------------

    async def __aenter__(self) -> AsyncRemembrClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # -- internal helpers ----------------------------------------------------

    def _handle_error(self, response: httpx.Response) -> None:
        """Raise a typed exception based on the HTTP status code."""
        status = response.status_code
        try:
            body = response.json()
        except Exception:
            body = {}

        message = body.get("error", body.get("message", response.text))

        if status == 401:
            raise AuthError(message, status_code=status)
        if status == 404:
            raise NotFoundError(message, status_code=status)
        if status == 422:
            raise ValidationError(message, status_code=status)
        if status == 429:
            raise RateLimitError(message, status_code=status)
        raise RemembrError(message, status_code=status)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = await self._client.request(method, path, json=json, params=params)
        if response.status_code >= 400:
            self._handle_error(response)
        if response.status_code == 204 or not response.text:
            return {}
        return response.json()

    # -- public API ----------------------------------------------------------

    async def store(
        self,
        value: str,
        *,
        key: str | None = None,
        type: str = "note",
        visibility: str = "private",
        importance: int = 5,
        confidence: float = 1.0,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        expires_at: str | None = None,
        ttl: str | None = None,
        category: str | None = None,
    ) -> Memory:
        """Store a new memory. Returns the created Memory object."""
        payload: dict[str, Any] = {"value": value, "type": type, "visibility": visibility}
        if key is not None:
            payload["key"] = key
        if importance != 5:
            payload["importance"] = importance
        if confidence != 1.0:
            payload["confidence"] = confidence
        if metadata is not None:
            payload["metadata"] = metadata
        if tags is not None:
            payload["tags"] = tags
        if expires_at is not None:
            payload["expires_at"] = expires_at
        if ttl is not None:
            payload["ttl"] = ttl
        if category is not None:
            payload["category"] = category
        data = await self._request("POST", "/memories", json=payload)
        return Memory(**data)

    async def get(self, key: str, *, detail: str = "full") -> Memory:
        """Retrieve a single memory by key or ID."""
        params: dict[str, Any] = {}
        if detail != "full":
            params["detail"] = detail
        data = await self._request("GET", f"/memories/{key}", params=params or None)
        return Memory(**data)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        tags: list[str] | None = None,
        type: str | None = None,
        category: str | None = None,
    ) -> list[Memory]:
        """Semantically search the agent's own memories."""
        params: dict[str, Any] = {"q": query, "limit": limit}
        if tags:
            params["tags"] = ",".join(tags)
        if type is not None:
            params["type"] = type
        if category is not None:
            params["category"] = category
        data = await self._request("GET", "/memories/search", params=params)
        return [Memory(**m) for m in data.get("data", [])]

    async def list(
        self,
        *,
        page: int = 1,
        tags: list[str] | None = None,
        type: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """List the agent's memories (paginated). Returns dict with 'data' and 'meta'."""
        params: dict[str, Any] = {"page": page}
        if tags:
            params["tags"] = ",".join(tags)
        if type is not None:
            params["type"] = type
        if category is not None:
            params["category"] = category
        data = await self._request("GET", "/memories", params=params)
        return {
            "data": [Memory(**m) for m in data.get("data", [])],
            "meta": data.get("meta", {}),
        }

    async def update(
        self,
        key: str,
        *,
        value: str | None = None,
        type: str | None = None,
        visibility: str | None = None,
        importance: int | None = None,
        confidence: float | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        expires_at: str | None = None,
        ttl: str | None = None,
        category: str | None = None,
    ) -> Memory:
        """Update an existing memory by key. Returns the updated Memory."""
        payload: dict[str, Any] = {}
        if value is not None:
            payload["value"] = value
        if type is not None:
            payload["type"] = type
        if visibility is not None:
            payload["visibility"] = visibility
        if importance is not None:
            payload["importance"] = importance
        if confidence is not None:
            payload["confidence"] = confidence
        if metadata is not None:
            payload["metadata"] = metadata
        if tags is not None:
            payload["tags"] = tags
        if expires_at is not None:
            payload["expires_at"] = expires_at
        if ttl is not None:
            payload["ttl"] = ttl
        if category is not None:
            payload["category"] = category
        data = await self._request("PATCH", f"/memories/{key}", json=payload)
        return Memory(**data)

    async def delete(self, key: str) -> dict[str, str]:
        """Delete a memory by key. Returns the API response message."""
        return await self._request("DELETE", f"/memories/{key}")

    async def feedback(self, key: str, *, useful: bool) -> dict[str, str]:
        """Submit relevance feedback for a memory."""
        return await self._request("POST", f"/memories/{key}/feedback", json={"useful": useful})

    async def share(self, key: str, *, agent_id: str) -> dict[str, str]:
        """Share a memory with another agent."""
        return await self._request("POST", f"/memories/{key}/share", json={"agent_id": agent_id})

    async def extract_session(
        self,
        transcript: str,
        *,
        category: str | None = None,
        visibility: str = "private",
    ) -> dict[str, Any]:
        """Extract durable memories from a conversation transcript."""
        payload: dict[str, Any] = {"transcript": transcript, "visibility": visibility}
        if category is not None:
            payload["category"] = category
        data = await self._request("POST", "/sessions/extract", json=payload)
        return {
            "data": [Memory(**m) for m in data.get("data", [])],
            "meta": data.get("meta", {}),
        }
