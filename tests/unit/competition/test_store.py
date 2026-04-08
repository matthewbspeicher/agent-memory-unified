# tests/unit/competition/test_store.py
from __future__ import annotations

import pytest
import pytest_asyncio
from competition.models import CompetitorCreate, CompetitorType, Tier
from competition.store import CompetitionStore


class MockDB:
    """In-memory mock for PostgresDB — stores rows as dicts."""

    def __init__(self):
        self._tables: dict[str, list[dict]] = {}
        self._id_counter = 0
        self._last_sql = ""
        self._last_params: list | None = None

    async def execute(self, sql: str, params: list | None = None):
        """Minimal mock: tracks calls, returns mock cursor for SELECTs."""
        self._last_sql = sql
        self._last_params = params
        return _MockCtx(self, sql, params)


class _MockCursor:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    async def fetchone(self) -> dict | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[dict]:
        return self._rows


class _MockCtx:
    def __init__(self, db: MockDB, sql: str, params):
        self._db = db
        self._sql = sql
        self._params = params

    async def __aenter__(self):
        return _MockCursor([])

    async def __aexit__(self, *args):
        pass

    def __await__(self):
        async def _noop():
            return None

        return _noop().__await__()


@pytest.fixture
def mock_db():
    return MockDB()


@pytest.fixture
def store(mock_db):
    return CompetitionStore(mock_db)


class TestCompetitionStoreUpsertCompetitor:
    @pytest.mark.asyncio
    async def test_upsert_builds_correct_sql(self, store, mock_db):
        competitor = CompetitorCreate(
            type=CompetitorType.AGENT, name="rsi_scanner", ref_id="rsi_scanner"
        )
        await store.upsert_competitor(competitor)
        assert "INSERT INTO competitors" in mock_db._last_sql
        assert "ON CONFLICT" in mock_db._last_sql

    @pytest.mark.asyncio
    async def test_upsert_passes_correct_params(self, store, mock_db):
        competitor = CompetitorCreate(
            type=CompetitorType.MINER,
            name="miner_5DkVM",
            ref_id="5DkVM4w",
            metadata={"uid": 144},
        )
        await store.upsert_competitor(competitor)
        assert mock_db._last_params[0] == "miner"
        assert mock_db._last_params[1] == "miner_5DkVM"
        assert mock_db._last_params[2] == "5DkVM4w"


class TestCompetitionStoreGetLeaderboard:
    @pytest.mark.asyncio
    async def test_leaderboard_query_includes_joins(self, store, mock_db):
        await store.get_leaderboard(asset="BTC")
        assert "elo_ratings" in mock_db._last_sql
        assert "competitors" in mock_db._last_sql
        assert "ORDER BY" in mock_db._last_sql
