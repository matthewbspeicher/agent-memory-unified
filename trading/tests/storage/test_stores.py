"""
Tests for storage stores - verifying they accept db parameter
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import aiosqlite

from config import Config
from storage.db import DatabaseConnection
from storage.trades import TradeStore
from storage.opportunities import OpportunityStore
from storage.performance import PerformanceStore
from storage.agent_registry import AgentStore
from storage.paper import PaperStore


class TestStoresAcceptDb:
    """Test that stores properly accept db parameter"""

    def test_trade_store_accepts_db(self):
        mock_db = MagicMock(spec=aiosqlite.Connection)
        store = TradeStore(mock_db)
        assert store._db == mock_db

    def test_opportunity_store_accepts_db(self):
        mock_db = MagicMock(spec=aiosqlite.Connection)
        store = OpportunityStore(mock_db)
        assert store._db == mock_db

    def test_performance_store_accepts_db(self):
        mock_db = MagicMock(spec=aiosqlite.Connection)
        store = PerformanceStore(mock_db)
        assert store._db == mock_db

    def test_agent_store_accepts_db(self):
        mock_db = MagicMock(spec=aiosqlite.Connection)
        store = AgentStore(mock_db)
        assert store._db == mock_db

    def test_paper_store_accepts_db(self):
        mock_db = MagicMock(spec=aiosqlite.Connection)
        store = PaperStore(mock_db)
        assert store._db == mock_db


class TestStoresWorkWithDatabaseConnection:
    """Test that stores work with DatabaseConnection"""

    @pytest.mark.asyncio
    async def test_stores_work_with_database_connection(self):
        """Test that stores can be initialized with db from DatabaseConnection"""
        from unittest.mock import patch

        config = Config(db_path=":memory:")
        db_conn = DatabaseConnection(config)

        with patch("storage.db.aiosqlite.connect", new_callable=AsyncMock) as mock_connect:
            mock_db = AsyncMock(spec=aiosqlite.Connection)
            mock_connect.return_value = mock_db

            with patch("storage.db.init_db", new_callable=AsyncMock):
                db = await db_conn.connect()

                # All stores should accept this db connection
                trade_store = TradeStore(db)
                opp_store = OpportunityStore(db)
                perf_store = PerformanceStore(db)
                agent_store = AgentStore(db)
                paper_store = PaperStore(db)

                assert trade_store._db == db
                assert opp_store._db == db
                assert perf_store._db == db
                assert agent_store._db == db
                assert paper_store._db == db
