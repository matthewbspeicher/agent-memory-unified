import httpx
from typing import Optional, Dict, Any, List

from .exceptions import RemembrException, AuthenticationException, MemoryNotFoundException

def _handle_error(response: httpx.Response):
    if response.status_code == 401:
        raise AuthenticationException("Unauthorized: Invalid agent token")
    elif response.status_code == 404:
        raise MemoryNotFoundException("Memory not found")
    else:
        try:
            msg = response.json().get("message", response.text)
        except Exception:
            msg = response.text
        raise RemembrException(f"API Error ({response.status_code}): {msg}")

class RemembrClient:
    """Synchronous client for Remembr.dev API."""

    def __init__(self, agent_token: str, base_url: str = "https://remembr.dev/api/v1"):
        self.agent_token = agent_token
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.agent_token}", "Accept": "application/json"}
        )

    @classmethod
    def register(cls, owner_token: str, name: str, description: Optional[str] = None, base_url: str = "https://remembr.dev/api/v1") -> Dict[str, Any]:
        """Register a new agent using an owner token."""
        url = f"{base_url.rstrip('/')}/agents/register"
        payload = {"owner_token": owner_token, "name": name}
        if description:
            payload["description"] = description
            
        with httpx.Client() as client:
            resp = client.post(url, json=payload, headers={"Accept": "application/json"})
            if resp.is_error:
                _handle_error(resp)
            return resp.json()

    def store(self, value: str, key: Optional[str] = None, visibility: str = "private", metadata: Optional[Dict] = None, expires_at: Optional[str] = None, ttl: Optional[str] = None, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Store or update a memory."""
        payload = {"value": value, "visibility": visibility}
        if key: payload["key"] = key
        if metadata: payload["metadata"] = metadata
        if expires_at: payload["expires_at"] = expires_at
        if ttl: payload["ttl"] = ttl
        if tags: payload["tags"] = tags
        
        resp = self.client.post("/memories", json=payload)
        if resp.is_error: _handle_error(resp)
        return resp.json()

    def get(self, key: str) -> Dict[str, Any]:
        """Retrieve a memory by key."""
        resp = self.client.get(f"/memories/{key}")
        if resp.is_error: _handle_error(resp)
        return resp.json()

    def delete(self, key: str) -> Dict[str, Any]:
        """Delete a memory by key."""
        resp = self.client.delete(f"/memories/{key}")
        if resp.is_error: _handle_error(resp)
        return resp.json()

    def list(self, page: int = 1, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """List all memories for this agent."""
        params = {"page": page}
        if tags: params["tags"] = ",".join(tags)
        resp = self.client.get("/memories", params=params)
        if resp.is_error: _handle_error(resp)
        return resp.json()

    def search(self, q: str, limit: int = 10, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Semantically search your own memories."""
        params = {"q": q, "limit": limit}
        if tags: params["tags"] = ",".join(tags)
        resp = self.client.get("/memories/search", params=params)
        if resp.is_error: _handle_error(resp)
        return resp.json().get("data", [])

    def search_commons(self, q: str, limit: int = 10, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Semantically search the public commons."""
        params = {"q": q, "limit": limit}
        if tags: params["tags"] = ",".join(tags)
        resp = self.client.get("/commons/search", params=params)
        if resp.is_error: _handle_error(resp)
        return resp.json().get("data", [])

    def share(self, key: str) -> Dict[str, Any]:
        """Share a private memory to the public commons."""
        resp = self.client.post(f"/memories/{key}/share")
        if resp.is_error: _handle_error(resp)
        return resp.json()

class AsyncRemembrClient:
    """Asynchronous client for Remembr.dev API."""

    def __init__(self, agent_token: str, base_url: str = "https://remembr.dev/api/v1"):
        self.agent_token = agent_token
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.agent_token}", "Accept": "application/json"}
        )

    @classmethod
    async def register(cls, owner_token: str, name: str, description: Optional[str] = None, base_url: str = "https://remembr.dev/api/v1") -> Dict[str, Any]:
        """Register a new agent using an owner token."""
        url = f"{base_url.rstrip('/')}/agents/register"
        payload = {"owner_token": owner_token, "name": name}
        if description:
            payload["description"] = description
            
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers={"Accept": "application/json"})
            if resp.is_error:
                _handle_error(resp)
            return resp.json()

    async def store(self, value: str, key: Optional[str] = None, visibility: str = "private", metadata: Optional[Dict] = None, expires_at: Optional[str] = None, ttl: Optional[str] = None, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Store or update a memory."""
        payload = {"value": value, "visibility": visibility}
        if key: payload["key"] = key
        if metadata: payload["metadata"] = metadata
        if expires_at: payload["expires_at"] = expires_at
        if ttl: payload["ttl"] = ttl
        if tags: payload["tags"] = tags
        
        resp = await self.client.post("/memories", json=payload)
        if resp.is_error: _handle_error(resp)
        return resp.json()

    async def get(self, key: str) -> Dict[str, Any]:
        """Retrieve a memory by key."""
        resp = await self.client.get(f"/memories/{key}")
        if resp.is_error: _handle_error(resp)
        return resp.json()

    async def delete(self, key: str) -> Dict[str, Any]:
        """Delete a memory by key."""
        resp = await self.client.delete(f"/memories/{key}")
        if resp.is_error: _handle_error(resp)
        return resp.json()

    async def list(self, page: int = 1, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """List all memories for this agent."""
        params = {"page": page}
        if tags: params["tags"] = ",".join(tags)
        resp = await self.client.get("/memories", params=params)
        if resp.is_error: _handle_error(resp)
        return resp.json()

    async def search(self, q: str, limit: int = 10, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Semantically search your own memories."""
        params = {"q": q, "limit": limit}
        if tags: params["tags"] = ",".join(tags)
        resp = await self.client.get("/memories/search", params=params)
        if resp.is_error: _handle_error(resp)
        return resp.json().get("data", [])

    async def search_commons(self, q: str, limit: int = 10, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Semantically search the public commons."""
        params = {"q": q, "limit": limit}
        if tags: params["tags"] = ",".join(tags)
        resp = await self.client.get("/commons/search", params=params)
        if resp.is_error: _handle_error(resp)
        return resp.json().get("data", [])

    async def share(self, key: str) -> Dict[str, Any]:
        """Share a private memory to the public commons."""
        resp = await self.client.post(f"/memories/{key}/share")
        if resp.is_error: _handle_error(resp)
        return resp.json()
