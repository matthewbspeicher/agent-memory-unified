import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
import aiosqlite
from storage.db import init_db
from storage.external import ExternalPortfolioStore
from api.routes.import_portfolio import create_import_router

SAMPLE_CSV = """"Brokerage"

"Account Name/Number","Symbol","Description","Quantity","Last Price","Current Value","Cost Basis Total","Cost Basis Per Share","Type"
"INDIVIDUAL - TOD X12345678","AAPL","APPLE INC","100","$187.50","$18,750.00","$15,000.00","$150.00","Cash"
"INDIVIDUAL - TOD X12345678","SPAXX**","FIDELITY GOVERNMENT MONEY MARKET","","$1.00","$5,000.00","--","--","Cash"

"Date downloaded 03/26/2026"
"""


@pytest.fixture
async def app():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    store = ExternalPortfolioStore(db)
    app = FastAPI()
    app.include_router(create_import_router(store))
    # Override auth for testing
    from api.auth import verify_api_key
    from api.identity.dependencies import resolve_identity, Identity

    app.dependency_overrides[verify_api_key] = lambda: "test-key"

    async def _override_resolve_identity():
        return Identity(name="master", scopes=frozenset(["admin", "*"]), tier="admin")

    app.dependency_overrides[resolve_identity] = _override_resolve_identity
    yield app
    await db.close()


@pytest.mark.asyncio
async def test_import_fidelity(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/import/fidelity",
            files={"file": ("positions.csv", SAMPLE_CSV, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accounts_imported"] == 1
        assert data["total_positions"] == 1  # SPAXX excluded


@pytest.mark.asyncio
async def test_get_external_portfolio(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/import/fidelity",
            files={"file": ("positions.csv", SAMPLE_CSV, "text/csv")},
        )
        resp = await client.get("/portfolio/external")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["positions"]) == 1
        assert data["positions"][0]["symbol"] == "AAPL"
