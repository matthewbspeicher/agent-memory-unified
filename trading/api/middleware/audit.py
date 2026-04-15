"""Audit-log middleware for mutation requests.

Emits one structured ``audit.request`` event per POST/PUT/PATCH/DELETE, recording
the verified identity (set by ``require_scope`` / ``require_any_scope``), the
declared scope, status code, and duration. GET/HEAD/OPTIONS/TRACE are skipped —
the identity PR defers read-side scoping to its own track, so auditing reads
would produce mostly-empty records.

Records with ``agent_name=None`` indicate a mutation route that has not been
migrated to ``require_scope`` yet — grepping audit logs for those surfaces
remaining work.
"""

from __future__ import annotations

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from utils.logging import log_event

logger = logging.getLogger(__name__)

_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Log every mutation request with the verified identity + declared scope."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if request.method not in _MUTATION_METHODS:
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000.0

        audit = getattr(request.state, "identity_audit", None)
        data = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "agent_name": audit["agent_name"] if audit else None,
            "scope_required": audit["scope_required"] if audit else None,
            "tier": audit["tier"] if audit else None,
            "agent_id": audit["agent_id"] if audit else None,
        }
        log_event(
            logger,
            logging.INFO,
            "audit.request",
            f"{request.method} {request.url.path} -> {response.status_code}",
            data=data,
        )
        return response
