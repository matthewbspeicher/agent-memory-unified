import json
import logging
import time
import uuid
import functools
import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar, cast
from fastapi import Request
from asgi_correlation_id import correlation_id

from utils.logging import log_event

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Callable[..., Any])

SENSITIVE_KEYS = {"api_key", "token", "secret", "password", "private_key"}


def sanitize_payload(payload: Any) -> Any:
    """Recursively redact sensitive keys from a payload."""
    if isinstance(payload, dict):
        return {
            k: "[REDACTED]" if k.lower() in SENSITIVE_KEYS else sanitize_payload(v)
            for k, v in payload.items()
        }
    elif isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    return payload


def audit_event(action_name: str):
    """
    Decorator for auditing high-risk actions (routes or business logic).

    Emits a structured log event and persists to the audit_logs table.
    Uses verified identity from resolve_identity for accurate actor attribution.
    """

    def decorator(func: T) -> T:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            request_id = correlation_id.get() or str(uuid.uuid4())

            actor_id = "system"
            actor_type = "system"
            resource_id = None
            client_ip = None
            payload = {}

            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get("request")

            if request and isinstance(request, Request):
                client_ip = request.client.host if request.client else None

                try:
                    from api.identity.dependencies import resolve_identity

                    identity = await resolve_identity(
                        request,
                        x_api_key=request.headers.get("X-API-Key"),
                        x_agent_token=request.headers.get("X-Agent-Token"),
                    )
                    actor_id = identity.name
                    actor_type = (
                        "agent"
                        if identity.agent_id
                        else ("master" if identity.tier == "premium" else "anonymous")
                    )
                except Exception:
                    actor_id = request.headers.get(
                        "X-Agent-Token"
                    ) or request.headers.get("X-API-Key", "anonymous")
                    actor_type = (
                        "agent" if request.headers.get("X-Agent-Token") else "master"
                    )
                    if actor_id == "anonymous":
                        actor_type = "anonymous"

                payload = {
                    "method": request.method,
                    "url": str(request.url),
                    "path_params": request.path_params,
                    "query_params": dict(request.query_params),
                }

                resource_id = (
                    request.path_params.get("name")
                    or request.path_params.get("symbol")
                    or request.path_params.get("id")
                )

            # Fallback resource_id from kwargs
            if not resource_id:
                resource_id = (
                    kwargs.get("symbol")
                    or kwargs.get("agent_name")
                    or kwargs.get("ticker")
                )

            # Initial log
            log_event(
                logger,
                logging.INFO,
                f"{action_name}.initiated",
                f"Initiating {action_name} for {resource_id or 'global'}",
                data={"request_id": request_id, "actor_id": actor_id},
            )

            status = "success"
            error_detail = None
            result = None

            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "failed"
                error_detail = str(e)
                log_event(
                    logger,
                    logging.ERROR,
                    f"{action_name}.failed",
                    f"Failed {action_name}: {error_detail}",
                    data={"request_id": request_id, "error": error_detail},
                )
                raise
            finally:
                duration_ms = int((time.perf_counter() - start_time) * 1000)

                # Final structured log
                log_event(
                    logger,
                    logging.INFO,
                    f"{action_name}.{status}",
                    f"Completed {action_name} in {duration_ms}ms",
                    data={
                        "request_id": request_id,
                        "status": status,
                        "duration_ms": duration_ms,
                        "resource_id": resource_id,
                    },
                )

                # Persistence (Best-effort)
                try:
                    # Attempt to get DB from app state if available via request
                    db = None
                    if request and hasattr(request.app.state, "db"):
                        db = request.app.state.db

                    if db:
                        sanitized = sanitize_payload(payload)
                        await db.execute(
                            """INSERT INTO audit_logs 
                               (id, action_name, actor_id, actor_type, resource_id, status, 
                                duration_ms, request_id, payload, error_detail, client_ip)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                str(uuid.uuid4()),
                                action_name,
                                str(actor_id),
                                actor_type,
                                str(resource_id) if resource_id else None,
                                status,
                                duration_ms,
                                request_id,
                                json.dumps(sanitized),
                                error_detail,
                                client_ip,
                            ),
                        )
                        # We don't call commit() here because PostgresDB auto-commits
                        # and aiosqlite connection is usually managed elsewhere,
                        # but for safety in this decorator we might need a local commit
                        # if it's aiosqlite.
                        if hasattr(db, "commit"):
                            await db.commit()
                except Exception as audit_exc:
                    # Critical failure: could not persist audit log
                    logger.error(
                        f"AUDIT PERSISTENCE FAILURE for {action_name}: {audit_exc}"
                    )

        return cast(T, wrapper)

    return decorator
