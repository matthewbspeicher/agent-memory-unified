"""Tests for AuditLogMiddleware — per-request audit event emission."""

import json
import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.identity.dependencies import Identity, require_scope
from api.middleware.audit import AuditLogMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.state.identity_store = None
    app.state.config = type("Config", (), {"api_key": "test-key"})()
    app.add_middleware(AuditLogMiddleware)

    @app.post("/protected")
    async def protected(
        identity: Identity = Depends(require_scope("write:orders")),
    ):
        return {"ok": True}

    @app.get("/read")
    async def read():
        return {"read": True}

    @app.post("/unprotected")
    async def unprotected():
        return {"unprotected": True}

    return app


def _audit_records(caplog) -> list[dict]:
    """Extract audit.request records from caplog."""
    out: list[dict] = []
    for rec in caplog.records:
        if getattr(rec, "event_type", None) == "audit.request":
            data = getattr(rec, "event_data", None) or {}
            out.append({
                "msg": rec.getMessage(),
                "data": data,
            })
    return out


def test_audit_logs_master_key_mutation(caplog):
    app = _build_app()
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="api.middleware.audit"):
        resp = client.post("/protected", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200

    records = _audit_records(caplog)
    assert len(records) == 1
    data = records[0]["data"]
    assert data["method"] == "POST"
    assert data["path"] == "/protected"
    assert data["status_code"] == 200
    assert data["agent_name"] == "master"
    assert data["scope_required"] == "write:orders"
    assert data["tier"] == "admin"
    assert "duration_ms" in data


def test_audit_logs_anonymous_403(caplog):
    app = _build_app()
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="api.middleware.audit"):
        resp = client.post("/protected")  # no header = anonymous
    assert resp.status_code == 403

    records = _audit_records(caplog)
    assert len(records) == 1
    data = records[0]["data"]
    assert data["status_code"] == 403
    assert data["agent_name"] == "anonymous"
    assert data["scope_required"] == "write:orders"


def test_audit_skips_get_requests(caplog):
    app = _build_app()
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="api.middleware.audit"):
        resp = client.get("/read")
    assert resp.status_code == 200
    assert _audit_records(caplog) == []


def test_audit_logs_unmigrated_mutation_with_null_identity(caplog):
    """Mutation routes without require_scope should log with agent_name=None.

    This is intentional — it surfaces routes that haven't been migrated to
    require_scope yet. Greppable as `audit.request` + `agent_name=null`.
    """
    app = _build_app()
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="api.middleware.audit"):
        resp = client.post("/unprotected")
    assert resp.status_code == 200

    records = _audit_records(caplog)
    assert len(records) == 1
    data = records[0]["data"]
    assert data["method"] == "POST"
    assert data["path"] == "/unprotected"
    assert data["agent_name"] is None
    assert data["scope_required"] is None
