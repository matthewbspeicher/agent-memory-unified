import httpx
from typing import Optional, Dict, Any, List

from .exceptions import (
    RemembrException,
    AuthenticationException,
    MemoryNotFoundException,
)


def _handle_error(response: httpx.Response):
    if response.status_code == 401:
        raise AuthenticationException("Unauthorized: Invalid agent token")
    elif response.status_code == 404:
        try:
            msg = response.json().get("message", "Not found")
        except Exception:
            msg = "Not found"
        raise MemoryNotFoundException(msg)
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
            headers={
                "Authorization": f"Bearer {self.agent_token}",
                "Accept": "application/json",
            },
        )

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        resp = self.client.request(method, path, **kwargs)
        if resp.is_error:
            _handle_error(resp)
        return resp.json()

    @classmethod
    def register(
        cls,
        owner_token: str,
        name: str,
        description: Optional[str] = None,
        base_url: str = "https://remembr.dev/api/v1",
    ) -> Dict[str, Any]:
        """Register a new agent using an owner token."""
        url = f"{base_url.rstrip('/')}/agents/register"
        payload = {"owner_token": owner_token, "name": name}
        if description:
            payload["description"] = description
        with httpx.Client() as client:
            resp = client.post(
                url, json=payload, headers={"Accept": "application/json"}
            )
            if resp.is_error:
                _handle_error(resp)
            return resp.json()

    # --- Memory CRUD ---

    def store(
        self,
        value: str,
        key: Optional[str] = None,
        visibility: str = "private",
        metadata: Optional[Dict] = None,
        ttl: Optional[str] = None,
        expires_at: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Store or update a memory."""
        payload: Dict[str, Any] = {"value": value, "visibility": visibility}
        if key:
            payload["key"] = key
        if metadata:
            payload["metadata"] = metadata
        if ttl:
            payload["ttl"] = ttl
        if expires_at:
            payload["expires_at"] = expires_at
        if tags:
            payload["tags"] = tags
        return self._request("POST", "/memories", json=payload)

    def get(self, key: str) -> Dict[str, Any]:
        """Retrieve a memory by key."""
        return self._request("GET", f"/memories/{key}")

    def delete(self, key: str) -> Dict[str, Any]:
        """Delete a memory by key."""
        return self._request("DELETE", f"/memories/{key}")

    def list(self, page: int = 1, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """List all memories for this agent."""
        params: Dict[str, Any] = {"page": page}
        if tags:
            params["tags"] = ",".join(tags)
        return self._request("GET", "/memories", params=params)

    def search(
        self, q: str, limit: int = 10, tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Semantically search your own memories."""
        params: Dict[str, Any] = {"q": q, "limit": limit}
        if tags:
            params["tags"] = ",".join(tags)
        return self._request("GET", "/memories/search", params=params).get("data", [])

    def search_commons(
        self, q: str, limit: int = 10, tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Semantically search the public commons."""
        params: Dict[str, Any] = {"q": q, "limit": limit}
        if tags:
            params["tags"] = ",".join(tags)
        return self._request("GET", "/commons/search", params=params).get("data", [])

    def share(self, key: str) -> Dict[str, Any]:
        """Share a private memory to the public commons."""
        return self._request("POST", f"/memories/{key}/share")

    def compact(self, keys: List[str], summary_key: str) -> Dict[str, Any]:
        """Compact multiple memories into a single summary."""
        payload = {"keys": keys, "summary_key": summary_key}
        return self._request("POST", "/memories/compact", json=payload)

    # --- Webhooks ---

    def register_webhook(
        self, url: str, events: List[str], semantic_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Register a semantic webhook."""
        payload = {"url": url, "events": events}
        if semantic_query:
            payload["semantic_query"] = semantic_query
        return self._request("POST", "/webhooks", json=payload)

    def list_webhooks(self) -> List[Dict[str, Any]]:
        """List all webhooks for this agent."""
        return self._request("GET", "/webhooks").get("data", [])

    def delete_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Delete a webhook."""
        return self._request("DELETE", f"/webhooks/{webhook_id}")

    def test_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Send a test ping to a webhook."""
        return self._request("POST", f"/webhooks/{webhook_id}/test")

    # --- Arena ---

    def get_arena_profile(self) -> Dict[str, Any]:
        """Get the agent's arena profile."""
        return self._request("GET", "/arena/profile")

    def update_arena_profile(
        self,
        bio: Optional[str] = None,
        avatar_url: Optional[str] = None,
        personality_tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update the agent's arena profile."""
        payload = {}
        if bio:
            payload["bio"] = bio
        if avatar_url:
            payload["avatar_url"] = avatar_url
        if personality_tags:
            payload["personality_tags"] = personality_tags
        return self._request("PATCH", "/arena/profile", json=payload)

    def list_gyms(self) -> List[Dict[str, Any]]:
        """List all available arena gyms."""
        return self._request("GET", "/arena/gyms").get("data", [])

    def get_gym(self, gym_id: str) -> Dict[str, Any]:
        """Get details for a specific gym."""
        return self._request("GET", f"/arena/gyms/{gym_id}").get("data", {})

    def start_arena_session(self, challenge_id: str) -> Dict[str, Any]:
        """Start a new arena challenge session."""
        return self._request("POST", f"/arena/challenges/{challenge_id}/start")

    def submit_arena_turn(self, session_id: str, input_text: str) -> Dict[str, Any]:
        """Submit an answer or move for an arena session."""
        return self._request(
            "POST", f"/arena/sessions/{session_id}/submit", json={"input": input_text}
        )

    # --- Presence ---

    def heartbeat(
        self, workspace_id: str, status: str = "online", metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send a heartbeat to update presence."""
        payload: Dict[str, Any] = {"status": status}
        if metadata:
            payload["metadata"] = metadata
        return self._request(
            "POST", f"/workspaces/{workspace_id}/presence/heartbeat", json=payload
        )

    def set_offline(self, workspace_id: str) -> Dict[str, Any]:
        """Set agent presence to offline."""
        return self._request("POST", f"/workspaces/{workspace_id}/presence/offline")

    def list_presences(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        include_offline: bool = False,
    ) -> List[Dict[str, Any]]:
        """List all presences in a workspace."""
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        if include_offline:
            params["include_offline"] = "true"
        return self._request(
            "GET", f"/workspaces/{workspace_id}/presence", params=params
        ).get("data", [])

    def get_presence(self, workspace_id: str, agent_id: str) -> Dict[str, Any]:
        """Get presence for a specific agent."""
        return self._request("GET", f"/workspaces/{workspace_id}/presence/{agent_id}")

    # --- Event Subscriptions ---

    def subscribe(
        self,
        workspace_id: str,
        event_types: List[str],
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Subscribe to workspace events."""
        payload: Dict[str, Any] = {"event_types": event_types}
        if callback_url:
            payload["callback_url"] = callback_url
        return self._request(
            "POST", f"/workspaces/{workspace_id}/subscriptions", json=payload
        )

    def list_subscriptions(self, workspace_id: str) -> List[Dict[str, Any]]:
        """List subscriptions for a workspace."""
        return self._request("GET", f"/workspaces/{workspace_id}/subscriptions").get(
            "data", []
        )

    def update_subscription(
        self,
        workspace_id: str,
        subscription_id: str,
        event_types: Optional[List[str]] = None,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a subscription."""
        payload: Dict[str, Any] = {}
        if event_types:
            payload["event_types"] = event_types
        if callback_url is not None:
            payload["callback_url"] = callback_url
        return self._request(
            "PUT",
            f"/workspaces/{workspace_id}/subscriptions/{subscription_id}",
            json=payload,
        )

    def unsubscribe(self, workspace_id: str, subscription_id: str) -> Dict[str, Any]:
        """Delete a subscription."""
        return self._request(
            "DELETE", f"/workspaces/{workspace_id}/subscriptions/{subscription_id}"
        )

    def poll_events(
        self, workspace_id: str, cursor: Optional[str] = None, limit: int = 20
    ) -> Dict[str, Any]:
        """Poll for new workspace events."""
        params: Dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", f"/workspaces/{workspace_id}/events", params=params)

    # --- Mentions ---

    def mention_agent(
        self,
        workspace_id: str,
        target_agent_id: str,
        message: str,
        memory_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a @mention to another agent."""
        payload: Dict[str, Any] = {
            "target_agent_id": target_agent_id,
            "message": message,
        }
        if memory_id:
            payload["memory_id"] = memory_id
        if task_id:
            payload["task_id"] = task_id
        return self._request(
            "POST", f"/workspaces/{workspace_id}/mentions", json=payload
        )

    def get_mentions(self, workspace_id: str) -> List[Dict[str, Any]]:
        """List all mentions (sent and received) in workspace."""
        return self._request("GET", f"/workspaces/{workspace_id}/mentions").get(
            "data", []
        )

    def get_received_mentions(self, workspace_id: str) -> List[Dict[str, Any]]:
        """List received mentions."""
        return self._request(
            "GET", f"/workspaces/{workspace_id}/mentions/received"
        ).get("data", [])

    def respond_to_mention(
        self, workspace_id: str, mention_id: str, response: str
    ) -> Dict[str, Any]:
        """Respond to a mention (accepted/declined/completed)."""
        return self._request(
            "PUT",
            f"/workspaces/{workspace_id}/mentions/{mention_id}/respond",
            json={"response": response},
        )

    def get_mention(self, workspace_id: str, mention_id: str) -> Dict[str, Any]:
        """Get a specific mention."""
        return self._request("GET", f"/workspaces/{workspace_id}/mentions/{mention_id}")

    # --- Tasks ---

    def create_task(
        self,
        workspace_id: str,
        title: str,
        description: Optional[str] = None,
        priority: str = "medium",
        due_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new task."""
        payload: Dict[str, Any] = {"title": title, "priority": priority}
        if description:
            payload["description"] = description
        if due_at:
            payload["due_at"] = due_at
        return self._request("POST", f"/workspaces/{workspace_id}/tasks", json=payload)

    def list_tasks(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        assigned_agent_id: Optional[str] = None,
        created_by_agent_id: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """List tasks in a workspace."""
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if assigned_agent_id:
            params["assigned_agent_id"] = assigned_agent_id
        if created_by_agent_id:
            params["created_by_agent_id"] = created_by_agent_id
        if priority:
            params["priority"] = priority
        return self._request("GET", f"/workspaces/{workspace_id}/tasks", params=params)

    def get_task(self, workspace_id: str, task_id: str) -> Dict[str, Any]:
        """Get a specific task."""
        return self._request("GET", f"/workspaces/{workspace_id}/tasks/{task_id}")

    def update_task(
        self, workspace_id: str, task_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a task."""
        return self._request(
            "PUT", f"/workspaces/{workspace_id}/tasks/{task_id}", json=data
        )

    def assign_task(
        self, workspace_id: str, task_id: str, agent_id: str
    ) -> Dict[str, Any]:
        """Assign a task to an agent."""
        return self._request(
            "PUT",
            f"/workspaces/{workspace_id}/tasks/{task_id}/assign",
            json={"agent_id": agent_id},
        )

    def update_task_status(
        self, workspace_id: str, task_id: str, status: str
    ) -> Dict[str, Any]:
        """Update a task's status."""
        return self._request(
            "PUT",
            f"/workspaces/{workspace_id}/tasks/{task_id}/status",
            json={"status": status},
        )

    def delete_task(self, workspace_id: str, task_id: str) -> Dict[str, Any]:
        """Delete a task."""
        return self._request("DELETE", f"/workspaces/{workspace_id}/tasks/{task_id}")


class AsyncRemembrClient:
    """Asynchronous client for Remembr.dev API."""

    def __init__(self, agent_token: str, base_url: str = "https://remembr.dev/api/v1"):
        self.agent_token = agent_token
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.agent_token}",
                "Accept": "application/json",
            },
        )

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        resp = await self.client.request(method, path, **kwargs)
        if resp.is_error:
            _handle_error(resp)
        return resp.json()

    @classmethod
    async def register(
        cls,
        owner_token: str,
        name: str,
        description: Optional[str] = None,
        base_url: str = "https://remembr.dev/api/v1",
    ) -> Dict[str, Any]:
        url = f"{base_url.rstrip('/')}/agents/register"
        payload = {"owner_token": owner_token, "name": name}
        if description:
            payload["description"] = description
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url, json=payload, headers={"Accept": "application/json"}
            )
            if resp.is_error:
                _handle_error(resp)
            return resp.json()

    async def store(
        self,
        value: str,
        key: Optional[str] = None,
        visibility: str = "private",
        metadata: Optional[Dict] = None,
        ttl: Optional[str] = None,
        expires_at: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"value": value, "visibility": visibility}
        if key:
            payload["key"] = key
        if metadata:
            payload["metadata"] = metadata
        if ttl:
            payload["ttl"] = ttl
        if expires_at:
            payload["expires_at"] = expires_at
        if tags:
            payload["tags"] = tags
        return await self._request("POST", "/memories", json=payload)

    async def get(self, key: str) -> Dict[str, Any]:
        return await self._request("GET", f"/memories/{key}")

    async def delete(self, key: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/memories/{key}")

    async def list(
        self, page: int = 1, tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"page": page}
        if tags:
            params["tags"] = ",".join(tags)
        return await self._request("GET", "/memories", params=params)

    async def search(
        self, q: str, limit: int = 10, tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"q": q, "limit": limit}
        if tags:
            params["tags"] = ",".join(tags)
        return (await self._request("GET", "/memories/search", params=params)).get(
            "data", []
        )

    async def search_commons(
        self, q: str, limit: int = 10, tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"q": q, "limit": limit}
        if tags:
            params["tags"] = ",".join(tags)
        return (await self._request("GET", "/commons/search", params=params)).get(
            "data", []
        )

    async def share(self, key: str) -> Dict[str, Any]:
        return await self._request("POST", f"/memories/{key}/share")

    async def compact(self, keys: List[str], summary_key: str) -> Dict[str, Any]:
        """Compact multiple memories into a single summary."""
        payload = {"keys": keys, "summary_key": summary_key}
        return await self._request("POST", "/memories/compact", json=payload)

    # --- Webhooks ---

    async def register_webhook(
        self, url: str, events: List[str], semantic_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Register a semantic webhook."""
        payload = {"url": url, "events": events}
        if semantic_query:
            payload["semantic_query"] = semantic_query
        return await self._request("POST", "/webhooks", json=payload)

    async def list_webhooks(self) -> List[Dict[str, Any]]:
        """List all webhooks for this agent."""
        return (await self._request("GET", "/webhooks")).get("data", [])

    async def delete_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Delete a webhook."""
        return await self._request("DELETE", f"/webhooks/{webhook_id}")

    async def test_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Send a test ping to a webhook."""
        return await self._request("POST", f"/webhooks/{webhook_id}/test")

    # --- Arena ---

    async def get_arena_profile(self) -> Dict[str, Any]:
        """Get the agent's arena profile."""
        return await self._request("GET", "/arena/profile")

    async def update_arena_profile(
        self,
        bio: Optional[str] = None,
        avatar_url: Optional[str] = None,
        personality_tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update the agent's arena profile."""
        payload = {}
        if bio:
            payload["bio"] = bio
        if avatar_url:
            payload["avatar_url"] = avatar_url
        if personality_tags:
            payload["personality_tags"] = personality_tags
        return await self._request("PATCH", "/arena/profile", json=payload)

    async def list_gyms(self) -> List[Dict[str, Any]]:
        """List all available arena gyms."""
        return (await self._request("GET", "/arena/gyms")).get("data", [])

    async def get_gym(self, gym_id: str) -> Dict[str, Any]:
        """Get details for a specific gym."""
        return (await self._request("GET", f"/arena/gyms/{gym_id}")).get("data", {})

    async def start_arena_session(self, challenge_id: str) -> Dict[str, Any]:
        """Start a new arena challenge session."""
        return await self._request("POST", f"/arena/challenges/{challenge_id}/start")

    async def submit_arena_turn(
        self, session_id: str, input_text: str
    ) -> Dict[str, Any]:
        """Submit an answer or move for an arena session."""
        return await self._request(
            "POST", f"/arena/sessions/{session_id}/submit", json={"input": input_text}
        )

    # --- Presence ---
    async def heartbeat(
        self, workspace_id: str, status: str = "online", metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"status": status}
        if metadata:
            payload["metadata"] = metadata
        return await self._request(
            "POST", f"/workspaces/{workspace_id}/presence/heartbeat", json=payload
        )

    async def set_offline(self, workspace_id: str) -> Dict[str, Any]:
        return await self._request(
            "POST", f"/workspaces/{workspace_id}/presence/offline"
        )

    async def list_presences(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        include_offline: bool = False,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        if include_offline:
            params["include_offline"] = "true"
        return (
            await self._request(
                "GET", f"/workspaces/{workspace_id}/presence", params=params
            )
        ).get("data", [])

    async def get_presence(self, workspace_id: str, agent_id: str) -> Dict[str, Any]:
        return await self._request(
            "GET", f"/workspaces/{workspace_id}/presence/{agent_id}"
        )

    # --- Subscriptions ---
    async def subscribe(
        self,
        workspace_id: str,
        event_types: List[str],
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"event_types": event_types}
        if callback_url:
            payload["callback_url"] = callback_url
        return await self._request(
            "POST", f"/workspaces/{workspace_id}/subscriptions", json=payload
        )

    async def list_subscriptions(self, workspace_id: str) -> List[Dict[str, Any]]:
        return (
            await self._request("GET", f"/workspaces/{workspace_id}/subscriptions")
        ).get("data", [])

    async def update_subscription(
        self,
        workspace_id: str,
        subscription_id: str,
        event_types: Optional[List[str]] = None,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if event_types:
            payload["event_types"] = event_types
        if callback_url is not None:
            payload["callback_url"] = callback_url
        return await self._request(
            "PUT",
            f"/workspaces/{workspace_id}/subscriptions/{subscription_id}",
            json=payload,
        )

    async def unsubscribe(
        self, workspace_id: str, subscription_id: str
    ) -> Dict[str, Any]:
        return await self._request(
            "DELETE", f"/workspaces/{workspace_id}/subscriptions/{subscription_id}"
        )

    async def poll_events(
        self, workspace_id: str, cursor: Optional[str] = None, limit: int = 20
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._request(
            "GET", f"/workspaces/{workspace_id}/events", params=params
        )

    # --- Mentions ---
    async def mention_agent(
        self,
        workspace_id: str,
        target_agent_id: str,
        message: str,
        memory_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "target_agent_id": target_agent_id,
            "message": message,
        }
        if memory_id:
            payload["memory_id"] = memory_id
        if task_id:
            payload["task_id"] = task_id
        return await self._request(
            "POST", f"/workspaces/{workspace_id}/mentions", json=payload
        )

    async def get_mentions(self, workspace_id: str) -> List[Dict[str, Any]]:
        return (await self._request("GET", f"/workspaces/{workspace_id}/mentions")).get(
            "data", []
        )

    async def get_received_mentions(self, workspace_id: str) -> List[Dict[str, Any]]:
        return (
            await self._request("GET", f"/workspaces/{workspace_id}/mentions/received")
        ).get("data", [])

    async def respond_to_mention(
        self, workspace_id: str, mention_id: str, response: str
    ) -> Dict[str, Any]:
        return await self._request(
            "PUT",
            f"/workspaces/{workspace_id}/mentions/{mention_id}/respond",
            json={"response": response},
        )

    async def get_mention(self, workspace_id: str, mention_id: str) -> Dict[str, Any]:
        return await self._request(
            "GET", f"/workspaces/{workspace_id}/mentions/{mention_id}"
        )

    # --- Tasks ---
    async def create_task(
        self,
        workspace_id: str,
        title: str,
        description: Optional[str] = None,
        priority: str = "medium",
        due_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"title": title, "priority": priority}
        if description:
            payload["description"] = description
        if due_at:
            payload["due_at"] = due_at
        return await self._request(
            "POST", f"/workspaces/{workspace_id}/tasks", json=payload
        )

    async def list_tasks(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        assigned_agent_id: Optional[str] = None,
        created_by_agent_id: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if assigned_agent_id:
            params["assigned_agent_id"] = assigned_agent_id
        if created_by_agent_id:
            params["created_by_agent_id"] = created_by_agent_id
        if priority:
            params["priority"] = priority
        return await self._request(
            "GET", f"/workspaces/{workspace_id}/tasks", params=params
        )

    async def get_task(self, workspace_id: str, task_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/workspaces/{workspace_id}/tasks/{task_id}")

    async def update_task(
        self, workspace_id: str, task_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        return await self._request(
            "PUT", f"/workspaces/{workspace_id}/tasks/{task_id}", json=data
        )

    async def assign_task(
        self, workspace_id: str, task_id: str, agent_id: str
    ) -> Dict[str, Any]:
        return await self._request(
            "PUT",
            f"/workspaces/{workspace_id}/tasks/{task_id}/assign",
            json={"agent_id": agent_id},
        )

    async def update_task_status(
        self, workspace_id: str, task_id: str, status: str
    ) -> Dict[str, Any]:
        return await self._request(
            "PUT",
            f"/workspaces/{workspace_id}/tasks/{task_id}/status",
            json={"status": status},
        )

    async def delete_task(self, workspace_id: str, task_id: str) -> Dict[str, Any]:
        return await self._request(
            "DELETE", f"/workspaces/{workspace_id}/tasks/{task_id}"
        )
