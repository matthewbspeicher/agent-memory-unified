from fastapi import APIRouter

router = APIRouter()


@router.get("/", include_in_schema=False)
async def landing():
    return {
        "schema_version": "1.0",
        "name": "agent-memory-unified",
        "description": "Bittensor Subnet 8 validator + multi-agent trading engine",
        "docs": {
            "for_agents": "/FOR_AGENTS.md",
            "agents_manifest": "/.well-known/agents.json",
            "openapi": "/openapi.json",
            "swagger_ui": "/docs",
            "project_feed": "https://github.com/agent-memory-unified/agent-memory-unified/tree/main/project-feed",
            "audit": "https://github.com/agent-memory-unified/agent-memory-unified/blob/main/docs/superpowers/specs/2026-04-10-agent-readiness-audit.md",
        },
        "auth": {
            "public_endpoints": "no auth required",
            "private_endpoints": "X-API-Key header (contact abuse@agent-memory-unified.xyz for a verified agent key)",
        },
        "rate_limits": {
            "anonymous": "10 req/min",
            "moltbook-verified": "60 req/min",
            "registered": "300 req/min",
        },
        "contact": {
            "abuse": "abuse@agent-memory-unified.xyz",
            "moltbook": "@agent-memory-unified",
        },
    }
