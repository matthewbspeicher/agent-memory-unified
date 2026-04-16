"""Unit tests for the Stripe webhook handler (spec §6).

Covers the full behaviour matrix:
- Feature flag off -> 410 Gone (no signature verify, no side effects)
- Signature verification: valid event accepted; tampered payload 400'd
- Idempotency: duplicate event_id short-circuits without re-provisioning
- Event routing: checkout.session.completed -> provision,
  customer.subscription.deleted -> revoke,
  customer.subscription.updated -> acknowledged no-op,
  unknown event type -> recorded + 200 (no retry)
- Handler failure -> 500 (Stripe retries, event NOT marked processed)
- Missing event id -> 400 (malformed)

Uses an in-memory SQLite DB for the stripe_processed_events table and
a mocked IdentityStore / stripe_client.verify_and_parse_event so the
tests don't need a real Stripe webhook secret.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.billing import webhooks as webhook_route
from billing import stripe_client
from storage.db import init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


def _make_event(
    event_id: str = "evt_test_001",
    event_type: str = "checkout.session.completed",
    *,
    customer_id: str = "cus_test_123",
    email: str = "subscriber@example.com",
):
    """Build a Stripe-event-shaped dict matching the subset the handler
    cares about. Real Stripe events have many more fields; we only
    populate what the handler reads."""
    data_obj: dict
    if event_type == "checkout.session.completed":
        data_obj = {
            "customer": customer_id,
            "customer_details": {"email": email},
        }
    elif event_type.startswith("customer.subscription."):
        data_obj = {"customer": customer_id, "status": "active"}
    else:
        data_obj = {"customer": customer_id}
    return {
        "id": event_id,
        "type": event_type,
        "data": {"object": data_obj},
    }


def _build_app(
    db,
    *,
    identity_store=None,
    provision_result=None,
    revoke_result: bool = True,
):
    """Build a FastAPI app with the webhook router + dependency overrides.
    Tests substitute the verify + provision functions via monkeypatch.
    """
    app = FastAPI()
    app.state.db = db
    app.state.identity_store = identity_store or MagicMock()
    app.include_router(webhook_route.router)
    return app


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    def test_flag_off_returns_410(self, db, monkeypatch):
        monkeypatch.setenv("STA_STRIPE_ENABLED", "false")
        app = _build_app(db)
        client = TestClient(app)
        r = client.post(
            "/stripe/webhooks",
            content=b"{}",
            headers={"Stripe-Signature": "whatever"},
        )
        assert r.status_code == 410
        assert "disabled" in r.json()["detail"].lower()

    def test_flag_off_does_not_call_verify(self, db, monkeypatch):
        """Sanity: when flag is off, we must NOT reach the signature
        verify path. A stray call there with unset env vars would leak
        a misleading error."""
        monkeypatch.setenv("STA_STRIPE_ENABLED", "false")
        app = _build_app(db)
        client = TestClient(app)
        with patch.object(
            stripe_client, "verify_and_parse_event"
        ) as mock_verify:
            client.post(
                "/stripe/webhooks",
                content=b"{}",
                headers={"Stripe-Signature": "sig"},
            )
            mock_verify.assert_not_called()


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


class TestSignatureVerification:
    def test_bad_signature_returns_400(self, db, monkeypatch):
        monkeypatch.setenv("STA_STRIPE_ENABLED", "true")
        app = _build_app(db)
        client = TestClient(app)
        with patch.object(
            stripe_client,
            "verify_and_parse_event",
            side_effect=stripe_client.StripeSignatureInvalidError("bad sig"),
        ):
            r = client.post(
                "/stripe/webhooks",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=deadbeef"},
            )
        assert r.status_code == 400
        assert "signature" in r.json()["detail"]

    def test_missing_event_id_returns_400(self, db, monkeypatch):
        monkeypatch.setenv("STA_STRIPE_ENABLED", "true")
        app = _build_app(db)
        client = TestClient(app)
        with patch.object(
            stripe_client,
            "verify_and_parse_event",
            return_value={"type": "checkout.session.completed", "data": {}},
        ):
            r = client.post(
                "/stripe/webhooks",
                content=b"{}",
                headers={"Stripe-Signature": "sig"},
            )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Event routing
# ---------------------------------------------------------------------------


class TestEventRouting:
    def test_checkout_completed_invokes_provision(self, db, monkeypatch):
        monkeypatch.setenv("STA_STRIPE_ENABLED", "true")
        app = _build_app(db)
        client = TestClient(app)

        provision_mock = AsyncMock(
            return_value=SimpleNamespace(
                agent_name="feed_sub_cus_test_123",
                token="amu_feed_sub_cus_test_123.xyz",
                created=True,
            )
        )
        with patch.object(
            stripe_client,
            "verify_and_parse_event",
            return_value=_make_event(
                event_id="evt_001", event_type="checkout.session.completed"
            ),
        ), patch.object(webhook_route, "provision_subscriber", provision_mock):
            r = client.post(
                "/stripe/webhooks",
                content=b"{}",
                headers={"Stripe-Signature": "sig"},
            )
        assert r.status_code == 200
        assert r.json()["result"] == "provisioned_new"
        provision_mock.assert_awaited_once()
        kwargs = provision_mock.await_args.kwargs
        assert kwargs["stripe_customer_id"] == "cus_test_123"
        assert kwargs["contact_email"] == "subscriber@example.com"

    def test_subscription_deleted_invokes_revoke(self, db, monkeypatch):
        monkeypatch.setenv("STA_STRIPE_ENABLED", "true")
        app = _build_app(db)
        client = TestClient(app)

        revoke_mock = AsyncMock(return_value=True)
        with patch.object(
            stripe_client,
            "verify_and_parse_event",
            return_value=_make_event(
                event_id="evt_002", event_type="customer.subscription.deleted"
            ),
        ), patch.object(webhook_route, "revoke_subscriber", revoke_mock):
            r = client.post(
                "/stripe/webhooks",
                content=b"{}",
                headers={"Stripe-Signature": "sig"},
            )
        assert r.status_code == 200
        assert r.json()["result"] == "revoked"
        revoke_mock.assert_awaited_once()
        assert (
            revoke_mock.await_args.kwargs["stripe_customer_id"] == "cus_test_123"
        )

    def test_subscription_updated_is_noop(self, db, monkeypatch):
        monkeypatch.setenv("STA_STRIPE_ENABLED", "true")
        app = _build_app(db)
        client = TestClient(app)

        with patch.object(
            stripe_client,
            "verify_and_parse_event",
            return_value=_make_event(
                event_id="evt_003", event_type="customer.subscription.updated"
            ),
        ):
            r = client.post(
                "/stripe/webhooks",
                content=b"{}",
                headers={"Stripe-Signature": "sig"},
            )
        assert r.status_code == 200
        assert r.json()["result"] == "acknowledged_noop"

    def test_unknown_event_type_200_marked_unhandled(self, db, monkeypatch):
        """Stripe stops retrying on 200; marking unknown types unhandled
        prevents retry storms for event types we didn't subscribe to."""
        monkeypatch.setenv("STA_STRIPE_ENABLED", "true")
        app = _build_app(db)
        client = TestClient(app)

        with patch.object(
            stripe_client,
            "verify_and_parse_event",
            return_value={
                "id": "evt_unknown_001",
                "type": "invoice.paid",
                "data": {"object": {}},
            },
        ):
            r = client.post(
                "/stripe/webhooks",
                content=b"{}",
                headers={"Stripe-Signature": "sig"},
            )
        assert r.status_code == 200
        assert r.json()["status"] == "unhandled"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_duplicate_event_id_short_circuits(self, db, monkeypatch):
        """Stripe retries on network error; the same event_id can arrive
        twice. The second one must NOT re-provision."""
        monkeypatch.setenv("STA_STRIPE_ENABLED", "true")
        app = _build_app(db)
        client = TestClient(app)
        provision_mock = AsyncMock(
            return_value=SimpleNamespace(
                agent_name="feed_sub_cus_dup", token="amu_x", created=True
            )
        )
        event = _make_event(
            event_id="evt_dup", event_type="checkout.session.completed",
            customer_id="cus_dup",
        )
        with patch.object(
            stripe_client, "verify_and_parse_event", return_value=event
        ), patch.object(webhook_route, "provision_subscriber", provision_mock):
            # First delivery: 200 provisioned
            r1 = client.post(
                "/stripe/webhooks",
                content=b"{}",
                headers={"Stripe-Signature": "sig"},
            )
            # Second delivery (Stripe retry): 200 duplicate
            r2 = client.post(
                "/stripe/webhooks",
                content=b"{}",
                headers={"Stripe-Signature": "sig"},
            )

        assert r1.status_code == 200
        assert r1.json()["result"] == "provisioned_new"
        assert r2.status_code == 200
        assert r2.json()["status"] == "duplicate"
        # Only one provisioning call across both deliveries
        provision_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# Handler failure → 500 (Stripe retries)
# ---------------------------------------------------------------------------


class TestHandlerFailure:
    def test_provision_failure_returns_500_and_does_not_mark_processed(
        self, db, monkeypatch
    ):
        """If the provisioning step raises, we must return 500 so Stripe
        retries, AND we must NOT mark the event processed (otherwise the
        retry would be short-circuited as duplicate)."""
        monkeypatch.setenv("STA_STRIPE_ENABLED", "true")
        app = _build_app(db)
        client = TestClient(app)

        provision_mock = AsyncMock(side_effect=RuntimeError("db down"))
        event = _make_event(
            event_id="evt_fail", event_type="checkout.session.completed"
        )
        with patch.object(
            stripe_client, "verify_and_parse_event", return_value=event
        ), patch.object(webhook_route, "provision_subscriber", provision_mock):
            r = client.post(
                "/stripe/webhooks",
                content=b"{}",
                headers={"Stripe-Signature": "sig"},
            )
        assert r.status_code == 500

        # stripe_processed_events must NOT have the row
        async def _check():
            cursor = await db.execute(
                "SELECT COUNT(*) AS n FROM stripe_processed_events "
                "WHERE event_id = ?",
                ("evt_fail",),
            )
            row = await cursor.fetchone()
            return int(row["n"])

        import asyncio

        assert asyncio.get_event_loop().run_until_complete(_check()) == 0
