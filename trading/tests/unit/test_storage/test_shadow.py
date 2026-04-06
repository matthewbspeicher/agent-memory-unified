"""Unit tests for ShadowExecutionStore."""

from __future__ import annotations

import aiosqlite
import pytest

from storage.db import init_db
from storage.shadow import ShadowExecutionStore


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield ShadowExecutionStore(db)
    await db.close()


def _record(record_id: str = "shadow-001", **overrides) -> dict:
    record = {
        "id": record_id,
        "opportunity_id": "opp-001",
        "agent_name": "rsi_agent",
        "symbol": "AAPL",
        "side": "BUY",
        "action_level": "suggest_trade",
        "decision_status": "shadowed",
        "expected_entry_price": "150.25",
        "expected_quantity": "10",
        "expected_notional": "1502.50",
        "entry_price_source": "mid",
        "opportunity_snapshot": {"confidence": 0.82},
        "risk_snapshot": {"max_loss": "50.00"},
        "sizing_snapshot": {"shares": 10},
        "regime_snapshot": {"regime": "risk_on"},
        "health_snapshot": {"status": "normal"},
        "opened_at": "2026-04-01T10:00:00+00:00",
        "resolve_after": "2026-04-01T10:05:00+00:00",
        "resolved_at": None,
        "resolution_status": "open",
        "resolution_price": None,
        "pnl": None,
        "return_bps": None,
        "max_favorable_bps": None,
        "max_adverse_bps": None,
        "resolution_notes": None,
    }
    record.update(overrides)
    return record


class TestShadowExecutionStore:
    async def test_insert_and_get(self, store: ShadowExecutionStore):
        await store.save(_record())

        row = await store.get("shadow-001")

        assert row is not None
        assert row["id"] == "shadow-001"
        assert row["agent_name"] == "rsi_agent"
        assert row["opportunity_snapshot"] == {"confidence": 0.82}
        assert row["risk_snapshot"] == {"max_loss": "50.00"}

    async def test_save_upserts_existing_record(self, store: ShadowExecutionStore):
        await store.save(_record())
        await store.save(
            _record(
                expected_quantity="20",
                opportunity_snapshot={"confidence": 0.9},
            )
        )

        row = await store.get("shadow-001")

        assert row is not None
        assert row["expected_quantity"] == "20"
        assert row["opportunity_snapshot"] == {"confidence": 0.9}

    async def test_list_filters_and_limit(self, store: ShadowExecutionStore):
        await store.save(
            _record(
                "shadow-aapl-newest",
                agent_name="rsi_agent",
                symbol="AAPL",
                opened_at="2026-04-01T10:03:00+00:00",
                decision_status="allowed",
            )
        )
        await store.save(
            _record(
                "shadow-aapl-older",
                agent_name="rsi_agent",
                symbol="AAPL",
                opened_at="2026-04-01T10:02:00+00:00",
                decision_status="blocked_risk",
            )
        )
        await store.save(
            _record(
                "shadow-tsla",
                agent_name="macd_agent",
                symbol="TSLA",
                opened_at="2026-04-01T10:01:00+00:00",
                resolution_status="resolved",
            )
        )

        rows = await store.list(
            agent_name="rsi_agent",
            symbol="AAPL",
            limit=1,
        )

        assert [row["id"] for row in rows] == ["shadow-aapl-newest"]

        blocked = await store.list(decision_status="blocked_risk")
        assert [row["id"] for row in blocked] == ["shadow-aapl-older"]

        resolved = await store.list(resolution_status="resolved")
        assert [row["id"] for row in resolved] == ["shadow-tsla"]

    async def test_list_due_for_resolution(self, store: ShadowExecutionStore):
        await store.save(
            _record("shadow-due", resolve_after="2026-04-01T10:01:00+00:00")
        )
        await store.save(
            _record("shadow-later", resolve_after="2026-04-01T10:10:00+00:00")
        )
        await store.save(
            _record(
                "shadow-resolved",
                resolve_after="2026-04-01T10:00:30+00:00",
                resolution_status="resolved",
                resolved_at="2026-04-01T10:02:00+00:00",
            )
        )

        rows = await store.list_due_for_resolution(
            "2026-04-01T10:05:00+00:00", limit=10
        )

        assert [row["id"] for row in rows] == ["shadow-due"]

    async def test_mark_resolved(self, store: ShadowExecutionStore):
        await store.save(_record())

        await store.mark_resolved(
            "shadow-001",
            resolved_at="2026-04-01T10:06:00+00:00",
            resolution_status="resolved",
            resolution_price="151.00",
            pnl="7.50",
            return_bps=49.92,
            max_favorable_bps=80.0,
            max_adverse_bps=-20.0,
            resolution_notes={"reason": "time_exit"},
        )

        row = await store.get("shadow-001")

        assert row is not None
        assert row["resolved_at"] == "2026-04-01T10:06:00+00:00"
        assert row["resolution_status"] == "resolved"
        assert row["resolution_price"] == "151.00"
        assert row["pnl"] == "7.50"
        assert row["return_bps"] == pytest.approx(49.92)
        assert row["resolution_notes"] == {"reason": "time_exit"}

    async def test_json_none_round_trips(self, store: ShadowExecutionStore):
        await store.save(_record(opportunity_snapshot=None, resolution_notes=None))

        row = await store.get("shadow-001")

        assert row is not None
        assert row["opportunity_snapshot"] is None
        assert row["resolution_notes"] is None

    async def test_summary_by_agent(self, store: ShadowExecutionStore):
        await store.save(
            _record(
                "shadow-001",
                agent_name="rsi_agent",
                resolution_status="resolved",
                resolved_at="2026-04-01T10:06:00+00:00",
                pnl="7.50",
                return_bps=50.0,
            )
        )
        await store.save(
            _record(
                "shadow-002",
                agent_name="rsi_agent",
                opportunity_id="opp-002",
                symbol="MSFT",
                resolution_status="resolved",
                resolved_at="2026-04-01T10:07:00+00:00",
                pnl="-2.50",
                return_bps=-20.0,
            )
        )
        await store.save(
            _record(
                "shadow-003",
                agent_name="macd_agent",
                opportunity_id="opp-003",
                symbol="TSLA",
                resolution_status="open",
            )
        )

        summary = await store.summary_by_agent()

        assert len(summary) == 2
        rsi = next(row for row in summary if row["agent_name"] == "rsi_agent")
        macd = next(row for row in summary if row["agent_name"] == "macd_agent")

        assert rsi["total_count"] == 2
        assert rsi["resolved_count"] == 2
        assert rsi["pending_count"] == 0
        assert float(rsi["total_pnl"]) == pytest.approx(5.0)
        assert rsi["avg_return_bps"] == pytest.approx(15.0)

        assert macd["total_count"] == 1
        assert macd["resolved_count"] == 0
        assert macd["pending_count"] == 1

    async def test_summary_for_agent(self, store: ShadowExecutionStore):
        await store.save(
            _record(
                "shadow-001",
                agent_name="rsi_agent",
                decision_status="allowed",
                resolution_status="resolved",
                resolved_at="2026-04-01T10:06:00+00:00",
                pnl="7.50",
                return_bps=50.0,
                max_favorable_bps=80.0,
                max_adverse_bps=-10.0,
            )
        )
        await store.save(
            _record(
                "shadow-002",
                agent_name="rsi_agent",
                opportunity_id="opp-002",
                symbol="MSFT",
                decision_status="blocked_risk",
                resolution_status="open",
            )
        )
        await store.save(
            _record(
                "shadow-003",
                agent_name="macd_agent",
                opportunity_id="opp-003",
                symbol="TSLA",
                decision_status="allowed",
                resolution_status="resolved",
                resolved_at="2026-04-01T10:07:00+00:00",
                pnl="-2.50",
                return_bps=-20.0,
            )
        )

        # Test agent with data
        rsi_stats = await store.summary_for_agent("rsi_agent")
        assert rsi_stats is not None
        assert rsi_stats["total_count"] == 2
        assert rsi_stats["allowed_count"] == 1
        assert rsi_stats["blocked_count"] == 1
        assert rsi_stats["resolved_count"] == 1
        assert rsi_stats["pending_count"] == 1
        assert float(rsi_stats["total_pnl"]) == pytest.approx(7.50)
        assert rsi_stats["avg_return_bps"] == pytest.approx(50.0)
        assert rsi_stats["win_rate"] == pytest.approx(
            1.0
        )  # 1 winning trade out of 1 resolved

        # Test agent with losing trade
        macd_stats = await store.summary_for_agent("macd_agent")
        assert macd_stats is not None
        assert macd_stats["total_count"] == 1
        assert macd_stats["win_rate"] == pytest.approx(0.0)  # 0 winning trades

        # Test nonexistent agent
        missing = await store.summary_for_agent("nonexistent")
        assert missing is None

    async def test_shadow_store_jsonb_compatible(self):
        """Verify JSONB columns work with dict values (Postgres asyncpg style)."""

        # Mock db that returns dict rows (like asyncpg)
        class MockCursor:
            def __init__(self, rows):
                self._rows = rows
                self._index = 0

            async def fetchone(self):
                if self._index < len(self._rows):
                    row = self._rows[self._index]
                    self._index += 1
                    return row
                return None

            async def fetchall(self):
                remaining = self._rows[self._index :]
                self._index = len(self._rows)
                return remaining

        class MockDB:
            def __init__(self):
                self._rows = []

            async def execute(self, sql, params=None):
                # For SELECT * FROM shadow_executions WHERE id = ?
                # Return a cursor with a single row dict
                if sql.strip().startswith("SELECT"):
                    # Simulate returning a row with JSONB dict
                    self._rows = [
                        {
                            "id": "test-1",
                            "opportunity_id": "opp-1",
                            "agent_name": "test_agent",
                            "symbol": "AAPL",
                            "side": "buy",
                            "action_level": "suggest_trade",
                            "decision_status": "allowed",
                            "expected_entry_price": "150.00",
                            "expected_quantity": "10",
                            "expected_notional": "1500.00",
                            "entry_price_source": "ask",
                            "opportunity_snapshot": {
                                "symbol": {"ticker": "AAPL"},
                                "signal": 0.8,
                            },
                            "risk_snapshot": None,
                            "sizing_snapshot": None,
                            "regime_snapshot": None,
                            "health_snapshot": None,
                            "opened_at": "2026-04-01T12:00:00+00:00",
                            "resolve_after": "2026-04-01T13:00:00+00:00",
                            "resolved_at": None,
                            "resolution_status": "open",
                            "resolution_price": None,
                            "pnl": None,
                            "return_bps": None,
                            "max_favorable_bps": None,
                            "max_adverse_bps": None,
                            "resolution_notes": None,
                        }
                    ]
                return MockCursor(self._rows)

            async def commit(self):
                pass

        mock_db = MockDB()
        store = ShadowExecutionStore(mock_db)
        record = {
            "id": "test-1",
            "opportunity_id": "opp-1",
            "agent_name": "test_agent",
            "symbol": "AAPL",
            "side": "buy",
            "action_level": "suggest_trade",
            "decision_status": "allowed",
            "expected_entry_price": "150.00",
            "expected_quantity": "10",
            "expected_notional": "1500.00",
            "entry_price_source": "ask",
            "opportunity_snapshot": {"symbol": {"ticker": "AAPL"}, "signal": 0.8},
            "risk_snapshot": None,
            "sizing_snapshot": None,
            "regime_snapshot": None,
            "health_snapshot": None,
            "opened_at": "2026-04-01T12:00:00+00:00",
            "resolve_after": "2026-04-01T13:00:00+00:00",
            "resolved_at": None,
            "resolution_status": "open",
            "resolution_price": None,
            "pnl": None,
            "return_bps": None,
            "max_favorable_bps": None,
            "max_adverse_bps": None,
            "resolution_notes": None,
        }
        await store.save(record)
        fetched = await store.get("test-1")
        assert fetched is not None
        # Should handle dict (Postgres JSONB) or string (SQLite TEXT)
        snapshot = fetched["opportunity_snapshot"]
        assert isinstance(snapshot, dict) or isinstance(snapshot, str)
