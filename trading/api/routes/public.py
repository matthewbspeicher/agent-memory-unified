"""Public router — curated read-only endpoints for external agents.

Every endpoint here is anonymous-allowed and rate-limited at the anonymous
tier (10 req/min) via the defensive_perimeter middleware. No mutation
methods may be called from this file. Enforced by test_public_surface_scoping.

See conductor/tracks/public_surface/spec.md for design.
"""

from __future__ import annotations

import time
from fastapi import APIRouter

router = APIRouter(prefix="/engine/v1/public", tags=["public"])

_STARTUP_TIME = time.time()


def _base_response() -> dict:
    """Common fields every public response includes."""
    return {
        "schema_version": "1.0",
        "name": "agent-memory-unified",
        "served_by": "agent-memory-unified",
        "docs": "/FOR_AGENTS.md",
    }


@router.get("/status")
async def public_status():
    return {
        **_base_response(),
        "version": "0.1.0",
        "uptime_seconds": int(time.time() - _STARTUP_TIME),
    }
