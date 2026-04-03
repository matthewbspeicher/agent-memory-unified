"""
RemembrArenaSync — best-effort async sync to remembr.dev Arena API.

Fail-open: if remembr.dev is unreachable, sync is skipped silently.
Remembr.dev is authoritative for ELO, win_count, loss_count, streak.

When offline:
  - fetch_all_profiles() returns None
  - LeaderboardEngine returns cached data, no new matches run
  - Prevents split-brain (local state never diverges from authoritative)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from leaderboard.engine import AgentRanking, MatchResult

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://remembr.dev/api/v1"


class RemembrArenaSync:
    def __init__(
        self,
        token: str,
        db: aiosqlite.Connection,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 5,
    ) -> None:
        self._token = token
        self._db = db
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._agent_map_cache: dict[str, str] | None = None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    async def ensure_agents_registered(self, agent_names: list[str]) -> dict[str, str]:
        """Register trading agents on remembr.dev, return {name: remembr_id} map."""
        # mapping_ids: {name: id}, mapping_tokens: {name: token}
        mapping_ids: dict[str, str] = {}
        mapping_tokens: dict[str, str] = {}
        
        try:
            cursor = await self._db.execute("SELECT agent_name, remembr_agent_id, remembr_token FROM agent_remembr_map")
            rows = await cursor.fetchall()
            for row in rows:
                name = row["agent_name"]
                rid = row["remembr_agent_id"]
                token = row["remembr_token"]
                mapping_ids[name] = rid
                if token:
                    mapping_tokens[name] = token
        except Exception as e:
            logger.debug("Failed to load agent mapping from DB: %s", e)

        missing = [n for n in agent_names if n not in mapping_ids or n not in mapping_tokens]
        if not missing:
            return mapping_ids

        # Register missing agents on remembr.dev
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # 1. Try to find existing agents first (to get their IDs)
                resp = await client.get(
                    f"{self._base_url}/agents",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    existing = resp.json().get("data", [])
                    for agent in existing:
                        aname = agent["name"]
                        if aname in missing:
                            mapping_ids[aname] = agent["id"]
                            # Note: listing agents doesn't return their tokens for security
                            missing.remove(aname)

                # 2. Create any still-missing agents (this returns the agent_token)
                for name in missing:
                    resp = await client.post(
                        f"{self._base_url}/agents",
                        headers=self._headers(),
                        json={"name": name, "description": f"Trading agent: {name}"},
                    )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        # Support both direct and nested response formats
                        agent_data = data.get("agent", data)
                        rid = agent_data.get("id")
                        token = data.get("agent_token") or data.get("token")
                        
                        if rid:
                            mapping_ids[name] = rid
                        if token:
                            mapping_tokens[name] = token

                # 3. Persist to SQLite
                for name, rid in mapping_ids.items():
                    token = mapping_tokens.get(name)
                    if rid:
                        await self._db.execute(
                            "INSERT OR REPLACE INTO agent_remembr_map (agent_name, remembr_agent_id, remembr_token) VALUES (?, ?, ?)",
                            (name, rid, token),
                        )
                await self._db.commit()

        except Exception as exc:
            logger.warning("Failed to register agents on remembr.dev: %s", exc)

        return mapping_ids

    async def ensure_team_setup(self, team_name: str, agent_names: list[str]) -> None:
        """
        Ensure a team exists on remembr.dev and all agents are members.
        Requires owner token.
        """
        if not self._token:
            return

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # 1. Create or get team
                resp = await client.post(
                    f"{self._base_url}/teams",
                    headers=self._headers(),
                    json={"name": team_name, "description": "Automated Trading Team"},
                )
                team_id = None
                if resp.status_code in (200, 201):
                    team_id = resp.json().get("id")
                elif resp.status_code == 409: # Conflict - already exists
                    # Try to find it
                    teams_resp = await client.get(f"{self._base_url}/teams", headers=self._headers())
                    if teams_resp.status_code == 200:
                        for t in teams_resp.json().get("data", []):
                            if t["name"] == team_name:
                                team_id = t["id"]
                                break

                if not team_id:
                    logger.warning("Could not resolve team_id for %s", team_name)
                    return

                # 2. Get remembr IDs for all agents
                agent_map = await self.ensure_agents_registered(agent_names)
                
                # 3. Add agents to team
                for agent_name, rid in agent_map.items():
                    # Check membership first
                    mem_resp = await client.get(
                        f"{self._base_url}/teams/{team_id}/members",
                        headers=self._headers(),
                    )
                    is_member = False
                    if mem_resp.status_code == 200:
                        for m in mem_resp.json().get("data", []):
                            if m.get("agent_id") == rid:
                                is_member = True
                                break
                    
                    if not is_member:
                        await client.post(
                            f"{self._base_url}/teams/{team_id}/members",
                            headers=self._headers(),
                            json={"agent_id": rid, "role": "member"},
                        )
                        logger.info("Added agent %s to team %s", agent_name, team_name)

        except Exception as e:
            logger.warning("Failed to setup remembr team: %s", e)

    async def get_agent_tokens(self) -> dict[str, str]:
        """Return {agent_name: remembr_token} mapping from database."""
        tokens: dict[str, str] = {}
        try:
            cursor = await self._db.execute("SELECT agent_name, remembr_token FROM agent_remembr_map WHERE remembr_token IS NOT NULL")
            rows = await cursor.fetchall()
            for row in rows:
                tokens[row["agent_name"]] = row["remembr_token"]
        except Exception as e:
            logger.error("Failed to fetch agent tokens: %s", e)
        return tokens

    # ------------------------------------------------------------------
    # Profile sync (full metric block)
    # ------------------------------------------------------------------

    async def fetch_all_profiles(
        self, agent_id_map: dict[str, str],
    ) -> dict[str, AgentRanking] | None:
        """Fetch current profiles from remembr.dev in parallel. Returns None if unreachable."""
        import asyncio

        async def _fetch_one(client: httpx.AsyncClient, name: str, rid: str) -> tuple[str, AgentRanking | None]:
            try:
                resp = await client.get(
                    f"{self._base_url}/agents/{rid}/arena/profile",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                return name, AgentRanking(
                    agent_name=name,
                    sharpe_ratio=0.0,
                    total_pnl=0.0,
                    win_rate=0.0,
                    elo=data.get("global_elo", 1000),
                    win_count=data.get("win_count", 0),
                    loss_count=data.get("loss_count", 0),
                    streak=data.get("streak", 0),
                )
            except Exception:
                return name, None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                results = await asyncio.gather(
                    *[_fetch_one(client, n, r) for n, r in agent_id_map.items()]
                )
            profiles = {n: r for n, r in results if r is not None}
            # If ALL fetches failed, treat as offline (return None)
            return profiles if profiles else None
        except Exception as exc:
            logger.warning("Failed to fetch profiles from remembr.dev: %s", exc)
            return None

    async def push_profile(
        self,
        agent_name: str,
        ranking: AgentRanking,
        agent_id_map: dict[str, str],
    ) -> None:
        """Push full metric block to remembr.dev. Fail-open."""
        rid = agent_id_map.get(agent_name)
        if not rid:
            return
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.put(
                    f"{self._base_url}/agents/{rid}/arena/profile",
                    headers=self._headers(),
                    json={
                        "global_elo": ranking.elo,
                        "win_count": ranking.win_count,
                        "loss_count": ranking.loss_count,
                        "streak": ranking.streak,
                    },
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Failed to push profile for %s: %s", agent_name, exc)

    async def push_matches(
        self,
        matches: list[MatchResult],
        agent_id_map: dict[str, str],
    ) -> None:
        """Record matches on remembr.dev in parallel. Fail-open."""
        import asyncio

        async def _push_one(client: httpx.AsyncClient, m: MatchResult) -> None:
            winner_id = agent_id_map.get(m.winner)
            loser_id = agent_id_map.get(m.loser)
            if not winner_id or not loser_id:
                return
            resp = await client.post(
                f"{self._base_url}/arena/matches",
                headers=self._headers(),
                json={
                    "agent_1_id": winner_id,
                    "agent_2_id": loser_id,
                    "winner_id": winner_id,
                    "status": "completed",
                },
            )
            resp.raise_for_status()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                await asyncio.gather(
                    *[_push_one(client, m) for m in matches],
                    return_exceptions=True,
                )
        except Exception as exc:
            logger.warning("Failed to push matches to remembr.dev: %s", exc)
