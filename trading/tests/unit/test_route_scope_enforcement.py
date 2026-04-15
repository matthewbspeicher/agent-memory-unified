"""
Integration tests for scope enforcement on protected routes.

Tests that routes correctly enforce scope requirements.
"""

import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from api.identity.dependencies import Identity


class MockOrderResult:
    """Mock result object matching OrderResultSchema."""

    def __init__(
        self,
        order_id: str = "test-123",
        status: str = "SUBMITTED",
        filled_quantity: Decimal = Decimal("0"),
        avg_fill_price: Decimal | None = Decimal("100.0"),
        message: str | None = "OK",
    ):
        self.order_id = order_id
        self.status = MagicMock()
        self.status.value = status
        self.filled_quantity = filled_quantity
        self.avg_fill_price = avg_fill_price
        self.message = message

    def __getattr__(self, name):
        return MagicMock()


@pytest_asyncio.fixture
async def app_with_mocks():
    """Create minimal FastAPI app for scope enforcement tests."""
    from fastapi import FastAPI
    from api.routes.identity import router as identity_router
    from api.routes import orders, risk, agents
    from api.identity.dependencies import resolve_identity
    from unittest.mock import patch

    app = FastAPI()

    # Mock identity store
    mock_store = AsyncMock()
    mock_store.list_active = AsyncMock(return_value=[])
    app.state.identity_store = mock_store
    app.state.config = MagicMock()

    # Register identity routes
    app.include_router(identity_router)

    mock_broker = AsyncMock()
    mock_broker.orders.place_order = AsyncMock(return_value=MockOrderResult())
    mock_broker.orders.modify_order = AsyncMock(
        return_value=MockOrderResult(status="MODIFIED")
    )
    mock_broker.orders.cancel_order = AsyncMock(
        return_value=MockOrderResult(status="CANCELLED", avg_fill_price=None)
    )
    app.state.broker = mock_broker

    # Mock risk engine
    mock_risk_engine = MagicMock()
    mock_risk_engine.kill_switch = MagicMock()
    mock_risk_engine.kill_switch.is_enabled = False
    mock_risk_engine.kill_switch.reason = ""
    mock_risk_engine.kill_switch.toggle = MagicMock()
    app.state.risk_engine = mock_risk_engine

    # Mock redis
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.setex = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.delete = AsyncMock()
    app.state.redis = mock_redis

    # Mock agent runner
    mock_runner = AsyncMock()
    mock_runner.start_agent = AsyncMock()
    mock_runner.stop_agent = AsyncMock()
    mock_runner.run_once = AsyncMock(return_value=[])
    app.state.agent_runner = mock_runner

    # Mutable container for identity (so we can change it per test)
    _identity_container = {
        "current": Identity(
            name="anonymous",
            scopes=frozenset([]),
            tier="anonymous",
        )
    }

    # Override dependencies
    async def override_get_broker():
        return mock_broker

    async def override_get_risk_engine():
        return mock_risk_engine

    async def override_get_redis():
        return mock_redis

    async def override_get_agent_runner():
        return mock_runner

    async def override_check_kill_switch():
        return None

    async def override_resolve_identity(
        x_api_key=None,
        x_agent_token=None,
    ):
        return _identity_container["current"]

    from api.dependencies import get_broker, get_risk_engine, get_redis
    from api.deps import get_agent_runner
    from api.auth import verify_api_key

    app.dependency_overrides[get_broker] = override_get_broker
    app.dependency_overrides[get_risk_engine] = override_get_risk_engine
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_agent_runner] = override_get_agent_runner
    app.dependency_overrides[resolve_identity] = override_resolve_identity

    # Override verify_api_key to always pass (scope tests don't test API key validation)
    async def override_verify_api_key():
        return "test-api-key"

    app.dependency_overrides[verify_api_key] = override_verify_api_key

    orders._csv_logger = MagicMock()

    # Stores used by arena / competition / achievements / journal routes — the
    # scope-check is a dependency that runs BEFORE the handler, so we only need
    # enough state to stop the handler from erroring during FastAPI's dependency
    # resolution. Downstream handler errors are acceptable since the assertion
    # is `status_code != 403`, not `== 200`.
    mock_competition_store = AsyncMock()

    # `place_bet` must return something whose attributes are real strings so
    # Pydantic's BetResponse can serialize it — otherwise the handler raises
    # a ValidationError whose repr contains random mock IDs that happen to
    # include "403", which defeats the `"403" not in str(e)` guard used by
    # the correct-scope tests.
    class _FakeBet:
        id = "b1"
        match_id = "m1"
        predicted_winner = "a"
        amount = 100
        potential_payout = 200
        created_at = None

        class status:
            value = "open"

    mock_competition_store.place_bet.return_value = _FakeBet()

    class _FakeMatch:
        competitor_a_id = "a"
        competitor_b_id = "b"

    mock_competition_store.get_match.return_value = _FakeMatch()

    app.state.competition_store = mock_competition_store

    app.state.db = AsyncMock()
    app.state.default_agent = "default"
    app.state.shadow_execution_store = AsyncMock()
    app.state.opportunity_store = AsyncMock()
    app.state.health_engine = AsyncMock()
    app.state.data_bus = MagicMock()
    app.state.settings = MagicMock()

    app.include_router(orders.router, prefix="/api/v1")
    app.include_router(risk.router, prefix="/api/v1")
    app.include_router(agents.router, prefix="/api/v1")

    # Mount the routers needed for the extended per-scope-group tests. Each
    # maps to one line of the scope coverage table in the plan.
    from api.routes import (
        arena as arena_routes,
        competition as competition_routes,
        achievements as achievements_routes,
        opportunities as opportunities_routes,
    )

    app.include_router(arena_routes.router)
    app.include_router(competition_routes.router)
    app.include_router(achievements_routes.router, prefix="/api/v1")
    app.include_router(opportunities_routes.router, prefix="/api/v1")

    # get_current_user dep used by opportunities list route — stub to a
    # free-tier user so the scope-focused tests don't need to wire JWTs.
    from api.auth import get_current_user
    from models.user import User, PlatformTier

    async def override_get_current_user():
        return User(
            id="test-user",
            email="t@t.com",
            tier=PlatformTier.EXPLORER,
        )

    app.dependency_overrides[get_current_user] = override_get_current_user

    # Store reference for tests to modify identity
    app._identity_container = _identity_container
    app._set_test_identity = lambda identity: _identity_container.update(
        {"current": identity}
    )

    return app


@pytest_asyncio.fixture
async def app_anonymous(app_with_mocks):
    """App with anonymous identity (no scopes)."""
    app_with_mocks._set_test_identity(
        Identity(
            name="anonymous",
            scopes=frozenset([]),
            tier="anonymous",
        )
    )
    return app_with_mocks


@pytest_asyncio.fixture
async def app_wrong_scope(app_with_mocks):
    """App with identity that has wrong scope."""
    app_with_mocks._set_test_identity(
        Identity(
            name="trader-agent",
            scopes=frozenset(["read:arena", "read:kg"]),
            tier="public",
            agent_id="agent-1",
        )
    )
    return app_with_mocks


@pytest_asyncio.fixture
async def app_write_orders(app_with_mocks):
    """App with identity that has write:orders scope."""
    app_with_mocks._set_test_identity(
        Identity(
            name="trader-agent",
            scopes=frozenset(["write:orders", "read:arena"]),
            tier="premium",
            agent_id="agent-2",
        )
    )
    return app_with_mocks


@pytest_asyncio.fixture
async def app_control_agents(app_with_mocks):
    """App with identity that has control:agents scope."""
    app_with_mocks._set_test_identity(
        Identity(
            name="controller",
            scopes=frozenset(["control:agents"]),
            tier="admin",
            agent_id="agent-3",
        )
    )
    return app_with_mocks


@pytest_asyncio.fixture
async def app_risk_halt(app_with_mocks):
    """App with identity that has risk:halt scope."""
    app_with_mocks._set_test_identity(
        Identity(
            name="risk-manager",
            scopes=frozenset(["risk:halt", "write:orders"]),
            tier="admin",
            agent_id="agent-4",
        )
    )
    return app_with_mocks


@pytest_asyncio.fixture
async def app_admin(app_with_mocks):
    """App with admin identity (* scope)."""
    app_with_mocks._set_test_identity(
        Identity(
            name="admin",
            scopes=frozenset(["admin", "*"]),
            tier="admin",
        )
    )
    return app_with_mocks


@pytest_asyncio.fixture
async def app_participate_arena(app_with_mocks):
    """App with identity that has participate:arena scope."""
    app_with_mocks._set_test_identity(
        Identity(
            name="arena-player",
            scopes=frozenset(["participate:arena"]),
            tier="public",
            agent_id="agent-arena",
        )
    )
    return app_with_mocks


@pytest_asyncio.fixture
async def app_bet_arena(app_with_mocks):
    """App with identity that has bet:arena scope."""
    app_with_mocks._set_test_identity(
        Identity(
            name="arena-bettor",
            scopes=frozenset(["bet:arena"]),
            tier="public",
            agent_id="agent-bet",
        )
    )
    return app_with_mocks


class TestScopeEnforcement:
    """Test scope enforcement on protected routes."""

    @pytest.mark.asyncio
    async def test_orders_post_anonymous_returns_403(self, app_anonymous):
        """Anonymous (no scope) should be rejected for POST /orders."""
        transport = ASGITransport(app=app_anonymous)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/orders",
                json={
                    "symbol": {
                        "ticker": "AAPL",
                        "asset_type": "STOCK",
                        "exchange": "NASDAQ",
                        "currency": "USD",
                    },
                    "side": "BUY",
                    "order_type": "MARKET",
                    "quantity": 1,
                    "time_in_force": "DAY",
                    "account_id": "test",
                },
            )
        assert response.status_code == 403, (
            f"Expected 403, got {response.status_code}: {response.json()}"
        )
        assert "write:orders" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_orders_post_wrong_scope_returns_403(self, app_wrong_scope):
        """Agent with wrong scope should be rejected for POST /orders."""
        transport = ASGITransport(app=app_wrong_scope)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/orders",
                json={
                    "symbol": {
                        "ticker": "AAPL",
                        "asset_type": "STOCK",
                        "exchange": "NASDAQ",
                        "currency": "USD",
                    },
                    "side": "BUY",
                    "order_type": "MARKET",
                    "quantity": 1,
                    "time_in_force": "DAY",
                    "account_id": "test",
                },
            )
        assert response.status_code == 403, (
            f"Expected 403, got {response.status_code}: {response.json()}"
        )
        assert "write:orders" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_orders_post_correct_scope_allowed(self, app_write_orders):
        """Agent with write:orders scope should pass scope check (not 403)."""
        transport = ASGITransport(app=app_write_orders)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.post(
                    "/api/v1/orders",
                    json={
                        "symbol": {
                            "ticker": "AAPL",
                            "asset_type": "STOCK",
                            "exchange": "NASDAQ",
                            "currency": "USD",
                        },
                        "side": "BUY",
                        "order_type": "MARKET",
                        "quantity": 1,
                        "time_in_force": "DAY",
                        "account_id": "test",
                    },
                )
                assert response.status_code != 403, f"Got 403: {response.json()}"
            except Exception as e:
                assert "403" not in str(e), f"Scope check failed: {e}"

    @pytest.mark.asyncio
    async def test_orders_post_admin_scope_allowed(self, app_admin):
        transport = ASGITransport(app=app_admin)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.post(
                    "/api/v1/orders",
                    json={
                        "symbol": {
                            "ticker": "AAPL",
                            "asset_type": "STOCK",
                            "exchange": "NASDAQ",
                            "currency": "USD",
                        },
                        "side": "BUY",
                        "order_type": "MARKET",
                        "quantity": 1,
                        "time_in_force": "DAY",
                        "account_id": "test",
                    },
                )
                assert response.status_code != 403, f"Got 403: {response.json()}"
            except Exception as e:
                assert "403" not in str(e), f"Scope check failed: {e}"

    @pytest.mark.asyncio
    async def test_agents_start_wrong_scope_returns_403(self, app_wrong_scope):
        """Agent without control:agents scope should be rejected for /agents/{name}/start."""
        transport = ASGITransport(app=app_wrong_scope)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/agents/test-agent/start")
        assert response.status_code == 403, (
            f"Expected 403, got {response.status_code}: {response.json()}"
        )
        assert "control:agents" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_agents_start_correct_scope_allowed(self, app_control_agents):
        """Agent with control:agents scope should be allowed for /agents/{name}/start."""
        transport = ASGITransport(app=app_control_agents)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/agents/test-agent/start")
        assert response.status_code != 403, f"Got 403: {response.json()}"

    @pytest.mark.asyncio
    async def test_risk_kill_switch_wrong_scope_returns_403(self, app_wrong_scope):
        """Agent without risk:halt scope should be rejected for /risk/kill-switch."""
        transport = ASGITransport(app=app_wrong_scope)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/risk/kill-switch",
                json={"enabled": True, "reason": "test"},
            )
        assert response.status_code == 403, (
            f"Expected 403, got {response.status_code}: {response.json()}"
        )
        assert "risk:halt" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_risk_kill_switch_correct_scope_allowed(self, app_risk_halt):
        """Agent with risk:halt scope should be allowed for /risk/kill-switch."""
        transport = ASGITransport(app=app_risk_halt)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/risk/kill-switch",
                json={"enabled": True, "reason": "test"},
            )
        assert response.status_code != 403, f"Got 403: {response.json()}"

    @pytest.mark.asyncio
    async def test_orders_patch_correct_scope_allowed(self, app_write_orders):
        transport = ASGITransport(app=app_write_orders)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.patch(
                    "/api/v1/orders/test-order-123",
                    json={"quantity": 5},
                )
                assert response.status_code != 403, f"Got 403: {response.json()}"
            except Exception as e:
                assert "403" not in str(e), f"Scope check failed: {e}"

    @pytest.mark.asyncio
    async def test_orders_delete_correct_scope_allowed(self, app_write_orders):
        transport = ASGITransport(app=app_write_orders)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.delete("/api/v1/orders/test-order-123")
                assert response.status_code != 403, f"Got 403: {response.json()}"
            except Exception as e:
                assert "403" not in str(e), f"Scope check failed: {e}"

    @pytest.mark.asyncio
    async def test_agents_stop_correct_scope_allowed(self, app_control_agents):
        """Agent with control:agents scope should be allowed for /agents/{name}/stop."""
        transport = ASGITransport(app=app_control_agents)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/agents/test-agent/stop")
        assert response.status_code != 403, f"Got 403: {response.json()}"

    @pytest.mark.asyncio
    async def test_agents_scan_correct_scope_allowed(self, app_control_agents):
        """Agent with control:agents scope should be allowed for /agents/{name}/scan."""
        transport = ASGITransport(app=app_control_agents)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/agents/test-agent/scan")
        assert response.status_code != 403, f"Got 403: {response.json()}"


class TestMigratedRouteScopes:
    """Coverage for the 37 mutation routes migrated from verify_api_key to
    require_scope. One wrong-scope 403 + one correct-scope non-403 per scope
    group (per the plan's scope-coverage table), with anonymous and admin
    (wildcard) checks for each group.
    """

    # ------------------------------------------------------------------
    # control:agents — agents create, tuning cycle, memory tune, etc.
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_agents_create_anonymous_403(self, app_anonymous):
        transport = ASGITransport(app=app_anonymous)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/agents", json={"name": "x"})
        assert response.status_code == 403
        assert "control:agents" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_agents_create_admin_allowed(self, app_admin):
        transport = ASGITransport(app=app_admin)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/agents", json={"name": "x"})
        assert response.status_code != 403

    @pytest.mark.asyncio
    async def test_agents_patch_wrong_scope_403(self, app_wrong_scope):
        transport = ASGITransport(app=app_wrong_scope)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch("/api/v1/agents/x", json={})
        assert response.status_code == 403
        assert "control:agents" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_agents_sync_correct_scope_allowed(self, app_control_agents):
        transport = ASGITransport(app=app_control_agents)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/agents/sync")
        assert response.status_code != 403

    # ------------------------------------------------------------------
    # participate:arena — arena sessions, competition loadout, missions
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_arena_session_start_anonymous_403(self, app_anonymous):
        transport = ASGITransport(app=app_anonymous)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/engine/v1/arena/sessions",
                json={"challenge_id": "c", "agent_id": "a"},
            )
        assert response.status_code == 403
        assert "participate:arena" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_arena_session_start_wrong_scope_403(self, app_wrong_scope):
        transport = ASGITransport(app=app_wrong_scope)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/engine/v1/arena/sessions",
                json={"challenge_id": "c", "agent_id": "a"},
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_arena_session_start_correct_scope_allowed(
        self, app_participate_arena
    ):
        transport = ASGITransport(app=app_participate_arena)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.post(
                    "/engine/v1/arena/sessions",
                    json={"challenge_id": "c", "agent_id": "a"},
                )
                assert response.status_code != 403, f"Got 403: {response.json()}"
            except Exception as e:
                assert "403" not in str(e), f"Scope check failed: {e}"

    @pytest.mark.asyncio
    async def test_arena_session_start_admin_allowed(self, app_admin):
        transport = ASGITransport(app=app_admin)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.post(
                    "/engine/v1/arena/sessions",
                    json={"challenge_id": "c", "agent_id": "a"},
                )
                assert response.status_code != 403, f"Got 403: {response.json()}"
            except Exception as e:
                assert "403" not in str(e), f"Scope check failed: {e}"

    @pytest.mark.asyncio
    async def test_competition_loadout_equip_wrong_scope_403(self, app_wrong_scope):
        transport = ASGITransport(app=app_wrong_scope)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/engine/v1/competition/competitors/c1/loadout/equip",
                json={"trait": "x"},
            )
        assert response.status_code == 403
        assert "participate:arena" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_competition_mission_claim_correct_scope_allowed(
        self, app_participate_arena
    ):
        transport = ASGITransport(app=app_participate_arena)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/engine/v1/competition/competitors/c1/missions/m1/claim"
            )
        assert response.status_code != 403

    # ------------------------------------------------------------------
    # bet:arena — competition match bets
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_competition_bet_anonymous_403(self, app_anonymous):
        transport = ASGITransport(app=app_anonymous)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/engine/v1/competition/matches/m1/bet",
                json={"predicted_winner": "a", "amount": 100},
            )
        assert response.status_code == 403
        assert "bet:arena" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_competition_bet_participate_scope_403(self, app_participate_arena):
        """participate:arena is NOT sufficient for bet:arena routes."""
        transport = ASGITransport(app=app_participate_arena)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/engine/v1/competition/matches/m1/bet",
                json={"predicted_winner": "a", "amount": 100},
            )
        assert response.status_code == 403
        assert "bet:arena" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_competition_bet_correct_scope_allowed(self, app_bet_arena):
        transport = ASGITransport(app=app_bet_arena)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.post(
                    "/engine/v1/competition/matches/m1/bet",
                    json={"predicted_winner": "a", "amount": 100},
                )
                assert response.status_code != 403, f"Got 403: {response.json()}"
            except Exception as e:
                assert "403" not in str(e), f"Scope check failed: {e}"

    @pytest.mark.asyncio
    async def test_competition_bet_admin_allowed(self, app_admin):
        transport = ASGITransport(app=app_admin)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.post(
                    "/engine/v1/competition/matches/m1/bet",
                    json={"predicted_winner": "a", "amount": 100},
                )
                assert response.status_code != 403, f"Got 403: {response.json()}"
            except Exception as e:
                assert "403" not in str(e), f"Scope check failed: {e}"

    # ------------------------------------------------------------------
    # admin — tournament run, competition settle, achievements unlock
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_competition_settle_anonymous_403(self, app_anonymous):
        transport = ASGITransport(app=app_anonymous)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/engine/v1/competition/matches/m1/settle?winner_id=a"
            )
        assert response.status_code == 403
        assert "admin" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_competition_settle_wrong_scope_403(self, app_bet_arena):
        """bet:arena can place bets but cannot settle — admin-only."""
        transport = ASGITransport(app=app_bet_arena)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/engine/v1/competition/matches/m1/settle?winner_id=a"
            )
        assert response.status_code == 403
        assert "admin" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_competition_settle_admin_allowed(self, app_admin):
        transport = ASGITransport(app=app_admin)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.post(
                    "/engine/v1/competition/matches/m1/settle?winner_id=a"
                )
                assert response.status_code != 403, f"Got 403: {response.json()}"
            except Exception as e:
                assert "403" not in str(e), f"Scope check failed: {e}"

    @pytest.mark.asyncio
    async def test_achievements_unlock_wrong_scope_403(self, app_control_agents):
        """control:agents is NOT admin — unlock route gates on admin only."""
        transport = ASGITransport(app=app_control_agents)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/achievements/ach-1/unlock")
        assert response.status_code == 403
        assert "admin" in response.json()["detail"]

    # ------------------------------------------------------------------
    # write:orders — opportunities approve, already covered broadly; here we
    # pin the newly-migrated approve route specifically.
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_opportunities_approve_auth_anonymous_403(self, app_anonymous):
        transport = ASGITransport(app=app_anonymous)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/opportunities/opp-1/approve-auth")
        assert response.status_code == 403
        assert "write:orders" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_opportunities_approve_auth_wrong_scope_403(self, app_wrong_scope):
        transport = ASGITransport(app=app_wrong_scope)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/opportunities/opp-1/approve-auth")
        assert response.status_code == 403
        assert "write:orders" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_opportunities_approve_auth_correct_scope_allowed(
        self, app_write_orders
    ):
        transport = ASGITransport(app=app_write_orders)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/opportunities/opp-1/approve-auth")
        assert response.status_code != 403
