from decimal import Decimal

import aiosqlite
import pytest

from storage.db import init_db
from storage.external import ExternalPortfolioStore


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield ExternalPortfolioStore(db)
    await db.close()


_POS1 = {
    "symbol": "AAPL",
    "description": "Apple Inc",
    "quantity": "100",
    "cost_basis": "14000",
    "current_value": "17500",
    "last_price": "175",
}
_POS2 = {
    "symbol": "MSFT",
    "description": "Microsoft",
    "quantity": "50",
    "cost_basis": None,
    "current_value": "19000",
    "last_price": "380",
}
_BAL = {"net_liquidation": "36500", "cash": "1000"}


class TestExternalPortfolioStore:
    async def test_import_and_get_positions(self, store):
        await store.import_positions(
            "fidelity", "ACC1", "Individual", [_POS1, _POS2], _BAL
        )
        positions = await store.get_positions(broker="fidelity")
        assert len(positions) == 2
        symbols = {p["symbol"] for p in positions}
        assert symbols == {"AAPL", "MSFT"}
        aapl = next(p for p in positions if p["symbol"] == "AAPL")
        assert aapl["account_id"] == "ACC1"
        assert aapl["account_name"] == "Individual"
        assert aapl["quantity"] == "100"
        assert aapl["current_value"] == "17500"
        assert aapl["broker"] == "fidelity"

    async def test_import_replaces_existing(self, store):
        await store.import_positions(
            "fidelity", "ACC1", "Individual", [_POS1, _POS2], _BAL
        )
        new_pos = [
            {
                "symbol": "GOOG",
                "description": "Alphabet",
                "quantity": "10",
                "cost_basis": "1500",
                "current_value": "1700",
                "last_price": "170",
            }
        ]
        new_bal = {"net_liquidation": "1700", "cash": "0"}
        await store.import_positions("fidelity", "ACC1", "Individual", new_pos, new_bal)
        positions = await store.get_positions(broker="fidelity", account_id="ACC1")
        assert len(positions) == 1
        assert positions[0]["symbol"] == "GOOG"
        balances = await store.get_balances(broker="fidelity")
        assert len(balances) == 1
        assert balances[0]["net_liquidation"] == "1700"

    async def test_get_positions_exclude_accounts(self, store):
        await store.import_positions("fidelity", "ACC1", "Individual", [_POS1], _BAL)
        await store.import_positions(
            "fidelity",
            "ACC2",
            "IRA",
            [_POS2],
            {"net_liquidation": "19000", "cash": "0"},
        )
        positions = await store.get_positions(exclude_accounts=["ACC2"])
        assert len(positions) == 1
        assert positions[0]["account_id"] == "ACC1"

    async def test_get_total_exposure_by_symbol(self, store):
        aapl_acc1 = {
            "symbol": "AAPL",
            "description": "",
            "quantity": "100",
            "cost_basis": None,
            "current_value": "17500",
            "last_price": "175",
        }
        aapl_acc2 = {
            "symbol": "AAPL",
            "description": "",
            "quantity": "50",
            "cost_basis": None,
            "current_value": "8750",
            "last_price": "175",
        }
        await store.import_positions(
            "fidelity", "ACC1", "Individual", [aapl_acc1], _BAL
        )
        await store.import_positions(
            "fidelity",
            "ACC2",
            "IRA",
            [aapl_acc2],
            {"net_liquidation": "8750", "cash": "0"},
        )
        exposure = await store.get_total_exposure_by_symbol()
        assert exposure["AAPL"] == Decimal("150")

    async def test_get_import_age(self, store):
        await store.import_positions("fidelity", "ACC1", "Individual", [_POS1], _BAL)
        age = await store.get_import_age("fidelity")
        assert age is not None
        assert 0 <= age < 0.01  # should be nearly 0 hours
